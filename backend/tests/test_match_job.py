"""Kontrakt-Tests fuer pipeline/gmail_ingest.py::_match_job (Phase 61A -- P0-1-Fix aus
tasks/code_review_2026-07-25.md).

Ein Test je Zeile der Zielverhalten-Tabelle aus tasks/spec_phase61_mail_zuordnung.md, plus der
echte Kollisionsfall aus dem Review als Regression -- mit SYNTHETISCHEN Firmen-/Jobnamen
nachgebaut (M4/T3, keinerlei Bezug zu echten Daten). Anders als in test_fuzzy_company.py
braucht es HIER keinen modul-weiten, einmalig angelegten Bestand: `_match_job` filtert immer
nach `company_id`, jeder Test legt daher seine EIGENE, unabhaengige Firma an (keine Gefahr
gegenseitiger Verfaelschung in der session-weiten tmp-DB). Muster trotzdem uebernommen:
App-Importe NUR innerhalb der Testfunktionen, nie auf Modulebene (s. conftest.py-Docstring).

Alle Aehnlichkeits-Scores unten sind VOR dem Schreiben mit dem echten titel_aehnlichkeit()
verifiziert (venv-REPL, s. Abschlussbericht Phase 61A) -- keine geratenen Zahlen, keine
zufaelligen Grenzfaelle.
"""


def test_firma_ohne_jobs_liefert_none(session):
    """Firma existiert, hat aber keinen einzigen Job -> None (erster Guard in _match_job)."""
    from app.models import Company
    from pipeline.gmail_ingest import _match_job

    comp = Company(name="Ohnejob Retail GmbH")
    session.add(comp)
    session.commit()
    session.refresh(comp)

    assert _match_job(session, comp, "Irgendein Titel") is None


def test_ohne_firma_liefert_none(session):
    """comp=None (Firma konnte nicht aufgeloest/angelegt werden) -> None, kein Crash."""
    from pipeline.gmail_ingest import _match_job

    assert _match_job(session, None, "Irgendein Titel") is None


def test_kein_kandidat_mit_titel_ohne_treffer(session):
    """Zielverhalten-Tabelle Zeile 'Kein Kandidat': Titel gegeben, aber kein Job der Firma
    aehnelt ihm auch nur annaehernd (Score 0.0, weit unter der Schwelle 0.5) -> None, der
    Aufrufer legt einen neuen Job an (unveraenderte Philosophie)."""
    from app.models import Company, Job
    from pipeline.gmail_ingest import _match_job

    comp = Company(name="Bergfeld Software AG")
    session.add(comp)
    session.commit()
    session.refresh(comp)
    session.add(Job(company_id=comp.id, company_name=comp.name,
                     title="Head of Partner Success EMEA", status="Beworben",
                     found_date="2026-07-01", dedup_key="synthetic|bergfeld|1"))
    session.commit()

    treffer = _match_job(session, comp, "Director Cloud Platform Engineering (m/f/d)")
    assert treffer is None


def test_genau_ein_kandidat_ueber_fuzzy_schwelle(session):
    """Zielverhalten-Tabelle Zeile 'Genau ein Kandidat': der Job wird zurueckgegeben. Bewusst
    ueber den FUZZY-Pfad getestet (eingehender Titel ohne Gender-Suffix, Score exakt 0.5 --
    Grenzfall der Schwelle inklusive '>='), nicht ueber den trivialen exakten ct_key-Treffer."""
    from app.models import Company, Job
    from pipeline.gmail_ingest import _match_job

    comp = Company(name="Kieselstein Digital GmbH")
    session.add(comp)
    session.commit()
    session.refresh(comp)
    job = Job(company_id=comp.id, company_name=comp.name,
              title="Service Delivery Manager (m/w/d)", status="Beworben",
              found_date="2026-07-01", dedup_key="synthetic|kieselstein|1")
    session.add(job)
    session.commit()
    session.refresh(job)

    treffer = _match_job(session, comp, "Service Delivery Manager")
    assert treffer is not None and treffer.id == job.id


def test_mehrdeutigkeit_bei_zwei_gleichwertigen_kandidaten(session):
    """Zielverhalten-Tabelle Zeile 'Mehrere Kandidaten': ZWEI Kandidaten gleichermassen ueber
    der Schwelle -> _MEHRDEUTIG, kein Raten. Zwei GLEICHRANGIGE Geschwister-Stellen (nicht das
    Basis+Zusatz-Muster der Review-Regression unten): 'Cloud Operations' vs.
    'Platform Operations', der eingehende (unvollstaendig extrahierte) Titel nennt nur
    'Operations' -- beide Stellen sind gleich plausibel, keine ist bevorzugt richtig
    (q-vs-c1 = 0.857, q-vs-c2 = 0.857 -- exakt gleich, echtes Patt)."""
    from app.models import Company, Job
    from pipeline.gmail_ingest import _MEHRDEUTIG, _match_job

    comp = Company(name="Rautenberg Systems Inc.")
    session.add(comp)
    session.commit()
    session.refresh(comp)
    session.add(Job(company_id=comp.id, company_name=comp.name,
                     title="Senior Manager Cloud Operations (m/w/d)", status="Interview",
                     found_date="2026-07-01", dedup_key="synthetic|rautenberg|1"))
    session.add(Job(company_id=comp.id, company_name=comp.name,
                     title="Senior Manager Platform Operations (m/w/d)", status="Beworben",
                     found_date="2026-07-01", dedup_key="synthetic|rautenberg|2"))
    session.commit()

    treffer = _match_job(session, comp, "Senior Manager Operations (m/w/d)")
    assert treffer is _MEHRDEUTIG


def test_regression_review_basis_plus_zusatz_liefert_mehrdeutig(session):
    """Regression fuer P0-1 (tasks/code_review_2026-07-25.md): der Review belegt das
    Schadensmuster 'Firma hat zwei Stellen, eine ist Basistitel + Zusatz' am REALEN Beispiel
    einer Firma ('Basistitel (m/f/d)' vs. '... - Zusatz (m/f/d)') -- hier STRUKTURGLEICH mit synthetischen Namen nachgebaut (T3:
    keine echten Firmen-/Jobdaten im Repo). Der alte 20-Zeichen-Praefix-Fallback haette hier
    den ERSTEN DB-Treffer genommen und damit ggf. den Status der falschen Stelle ueberschrieben;
    die neue Fuzzy-Schwelle erkennt stattdessen Mehrdeutigkeit (qb-vs-c1b = 0.857,
    qb-vs-c2b = 0.875, beide >= 0.5)."""
    from app.models import Company, Job
    from pipeline.gmail_ingest import _MEHRDEUTIG, _match_job

    comp = Company(name="Nordlicht Consulting GmbH")
    session.add(comp)
    session.commit()
    session.refresh(comp)
    session.add(Job(company_id=comp.id, company_name=comp.name,
                     title="Service Delivery Manager (m/w/d)", status="Interview",
                     found_date="2026-07-01", dedup_key="synthetic|nordlicht|1"))
    session.add(Job(company_id=comp.id, company_name=comp.name,
                     title="Service Delivery Manager – Kundenintegration & Rollout (m/w/d)",
                     status="Beworben", found_date="2026-07-01",
                     dedup_key="synthetic|nordlicht|2"))
    session.commit()

    # Eingehender (unvollstaendig aus dem Betreff extrahierter) Titel: Basis + abgeschnittener
    # Zusatz -- aehnelt BEIDEN Stellen ueber der Schwelle, keine ist eindeutig bevorzugt.
    treffer = _match_job(session, comp, "Service Delivery Manager – Kundenintegration (m/w/d)")
    assert treffer is _MEHRDEUTIG


def test_mehrere_exakte_ctkey_treffer_liefert_ebenfalls_mehrdeutig(session):
    """Spec Stufe 61A Schritt 3: auch der EXAKTE ct_key-Vergleich raet nicht, wenn er mehrere
    Treffer liefert (hier: zwei Jobs mit identischem Titeltext, z. B. ein nicht deduplizierter
    Repost). Dieser Fall darf NIE einfach den ersten DB-Treffer gewinnen lassen."""
    from app.models import Company, Job
    from pipeline.gmail_ingest import _MEHRDEUTIG, _match_job

    comp = Company(name="Torfmoor Analytics KG")
    session.add(comp)
    session.commit()
    session.refresh(comp)
    session.add(Job(company_id=comp.id, company_name=comp.name,
                     title="Support Engineer (m/w/d)", status="Neu",
                     found_date="2026-07-01", dedup_key="synthetic|torfmoor|1"))
    session.add(Job(company_id=comp.id, company_name=comp.name,
                     title="Support Engineer (m/w/d)", status="Geparkt",
                     found_date="2026-07-02", dedup_key="synthetic|torfmoor|2"))
    session.commit()

    treffer = _match_job(session, comp, "Support Engineer (m/w/d)")
    assert treffer is _MEHRDEUTIG


def test_ohne_titel_ein_job_liefert_ihn(session):
    """Zielverhalten-Tabelle Zeile 'Ohne Titel, 1 Job': kein Titel im Record, Firma hat genau
    einen Job -> dieser wird zurueckgegeben (unveraendertes Verhalten). Sowohl None als auch
    leerer String zaehlen als 'kein Titel'."""
    from app.models import Company, Job
    from pipeline.gmail_ingest import _match_job

    comp = Company(name="Wiesengrund Consulting GmbH")
    session.add(comp)
    session.commit()
    session.refresh(comp)
    job = Job(company_id=comp.id, company_name=comp.name,
              title="Irrelevanter Titel", status="Beworben",
              found_date="2026-07-01", dedup_key="synthetic|wiesengrund|1")
    session.add(job)
    session.commit()
    session.refresh(job)

    treffer = _match_job(session, comp, None)
    assert treffer is not None and treffer.id == job.id
    treffer_leer = _match_job(session, comp, "")
    assert treffer_leer is not None and treffer_leer.id == job.id


def test_ohne_titel_mehrere_jobs_liefert_none_nicht_mehrdeutig(session):
    """Zielverhalten-Tabelle Zeile 'Ohne Titel, mehrere Jobs': None (unveraendert!) -- NICHT
    _MEHRDEUTIG. Ohne jeden Titel gibt es keine Grundlage fuer eine Aehnlichkeits-Entscheidung;
    das bleibt bewusst der alte 'kein Kandidat'-Pfad (s. Spec-Tabelle, Begruendungsspalte)."""
    from app.models import Company, Job
    from pipeline.gmail_ingest import _MEHRDEUTIG, _match_job

    comp = Company(name="Ahornweg Trading GmbH")
    session.add(comp)
    session.commit()
    session.refresh(comp)
    session.add(Job(company_id=comp.id, company_name=comp.name, title="Rolle A",
                     status="Beworben", found_date="2026-07-01", dedup_key="synthetic|ahorn|1"))
    session.add(Job(company_id=comp.id, company_name=comp.name, title="Rolle B",
                     status="Beworben", found_date="2026-07-01", dedup_key="synthetic|ahorn|2"))
    session.commit()

    treffer = _match_job(session, comp, None)
    assert treffer is None
    assert treffer is not _MEHRDEUTIG


def test_geloeschter_job_ohne_aktive_alternative_liefert_none(session):
    """Zielverhalten-Tabelle Zeile 'Gelöschte Jobs': ein Tombstone (deleted_at gesetzt) ist NIE
    Kandidat -- selbst wenn sein Titel exakt passt und es die einzige 'passende' Stelle waere."""
    from app.models import Company, Job
    from pipeline.gmail_ingest import _match_job

    comp = Company(name="Schattental Robotics GmbH")
    session.add(comp)
    session.commit()
    session.refresh(comp)
    session.add(Job(company_id=comp.id, company_name=comp.name,
                     title="Geisterstelle (m/w/d)", status="Absage",
                     found_date="2026-06-01", dedup_key="synthetic|schattental|1",
                     deleted_at="2026-06-15T09:00:00"))
    session.commit()

    treffer = _match_job(session, comp, "Geisterstelle (m/w/d)")
    assert treffer is None


def test_geloeschter_job_wird_bei_aktiver_alternative_uebersprungen(session):
    """Ergaenzung zu 'Gelöschte Jobs': Firma hat EINEN geloeschten UND einen aktiven Job mit
    identischem Titel (z. B. geloescht und identisch neu ausgeschrieben) -- der Tombstone darf
    den sauberen Treffer auf den aktiven Job weder verhindern noch zu _MEHRDEUTIG verfaelschen."""
    from app.models import Company, Job
    from pipeline.gmail_ingest import _MEHRDEUTIG, _match_job

    comp = Company(name="Lindenhof Systems AG")
    session.add(comp)
    session.commit()
    session.refresh(comp)
    session.add(Job(company_id=comp.id, company_name=comp.name,
                     title="Onboarding Specialist (m/w/d)", status="Absage",
                     found_date="2026-06-01", dedup_key="synthetic|lindenhof|1",
                     deleted_at="2026-06-20T09:00:00"))
    aktiv = Job(company_id=comp.id, company_name=comp.name,
                title="Onboarding Specialist (m/w/d)", status="Neu",
                found_date="2026-07-01", dedup_key="synthetic|lindenhof|2")
    session.add(aktiv)
    session.commit()
    session.refresh(aktiv)

    treffer = _match_job(session, comp, "Onboarding Specialist (m/w/d)")
    assert treffer is not _MEHRDEUTIG
    assert treffer is not None and treffer.id == aktiv.id


# ── Aufrufer-Ebene: ingest_emails() darf bei _MEHRDEUTIG keinen dritten Job anlegen ─────────

def test_ingest_emails_bei_mehrdeutigkeit_kein_neuer_job(session):
    """Stufe 61A Schritt 4: der Aufrufer (ingest_emails) legt bei _MEHRDEUTIG KEINEN dritten Job
    an, aendert KEINEN der beiden bestehenden Job-Status und zaehlt den Fall separat im
    Rueckgabe-Dict -- die Mail bleibt firmenbezogen ohne Stelle (bestehender 'Ohne Stelle'-Pfad,
    job_id=None). Das ist der eigentliche P0-1-Schaden: OHNE den Fix haette der 20-Zeichen-
    Fallback hier den ERSTEN Job getroffen und dessen Status auf 'Absage' ueberschrieben."""
    from sqlmodel import select
    from app.models import Company, Email, Job
    from pipeline.gmail_ingest import ingest_emails

    comp = Company(name="Feldweg Analytics GmbH")
    session.add(comp)
    session.commit()
    session.refresh(comp)
    session.add(Job(company_id=comp.id, company_name=comp.name,
                     title="Senior Manager Cloud Operations (m/w/d)", status="Interview",
                     found_date="2026-07-01", dedup_key="synthetic|feldweg|1"))
    session.add(Job(company_id=comp.id, company_name=comp.name,
                     title="Senior Manager Platform Operations (m/w/d)", status="Beworben",
                     found_date="2026-07-01", dedup_key="synthetic|feldweg|2"))
    session.commit()

    result = ingest_emails([{
        "gmail_message_id": "synthetic-mehrdeutig-1",
        "direction": "incoming", "from_addr": "recruiting@feldweg-example.test",
        "subject": "Update zu Ihrer Bewerbung", "received_at": "2026-07-20T10:00:00Z",
        "category": "Absage", "company": "Feldweg Analytics GmbH",
        "job_title": "Senior Manager Operations (m/w/d)", "job_status": "Absage",
    }])

    assert result["mehrdeutig"] == 1
    assert result["new"] == 1

    jobs = session.exec(select(Job).where(Job.company_id == comp.id)).all()
    assert len(jobs) == 2  # kein dritter Job angelegt
    assert sorted(j.status for j in jobs) == ["Beworben", "Interview"]  # kein Status ueberschrieben

    email = session.exec(
        select(Email).where(Email.gmail_message_id == "synthetic-mehrdeutig-1")
    ).first()
    assert email is not None
    assert email.job_id is None
    assert email.company_id == comp.id


def test_ingest_emails_ohne_kandidat_legt_weiterhin_neuen_job_an(session):
    """Gegenprobe: 'kein Kandidat' (nicht mehrdeutig) legt WEITERHIN einen neuen Job an -- das
    ist die bestehende, unveraenderte Philosophie (Zielverhalten-Tabelle Zeile 'Kein
    Kandidat') und darf durch den Phase-61A-Fix nicht angetastet werden."""
    from sqlmodel import select
    from app.models import Company, Job
    from pipeline.gmail_ingest import ingest_emails

    comp = Company(name="Talblick Ventures GmbH")
    session.add(comp)
    session.commit()
    session.refresh(comp)

    result = ingest_emails([{
        "gmail_message_id": "synthetic-keinkandidat-1",
        "direction": "incoming", "from_addr": "recruiting@talblick-example.test",
        "subject": "Ihre Bewerbung", "received_at": "2026-07-20T10:00:00Z",
        "category": "Eingangsbestätigung", "company": "Talblick Ventures GmbH",
        "job_title": "Head of Revenue Enablement (m/w/d)", "job_status": "Beworben",
    }])

    assert result["mehrdeutig"] == 0
    assert result["new"] == 1

    jobs = session.exec(select(Job).where(Job.company_id == comp.id)).all()
    assert len(jobs) == 1
    assert jobs[0].title == "Head of Revenue Enablement (m/w/d)"
