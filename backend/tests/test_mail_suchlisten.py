"""P2-80 — Suchlisten für Schritt 1b des Gmail-Checks (`pipeline/mail_suchlisten.py`) und die
Kontakt-Ergänzung beim Einspielen (`gmail_ingest._upsert_contact`).

Anlass: Eine Absage kam persönlich vom Recruiter einer Firma, bei der ein Gespräch lief. Betreff ohne
Stichwort, Absender ohne ATS-Muster, der Recruiter stand ohne Adresse in der DB, die Firmendomain
wurde nur für Personalberater durchsucht. Die Mail fiel durch beide Netze.

Die Test-DB gilt sitzungsweit (kein Rollback): Jeder Test legt eigene Firmen mit eindeutigen
Domains an und prüft nur auf „enthalten / nicht enthalten“. Keine app.*-Importe auf Modulebene.
"""
import uuid


def _firma(session, name=None):
    from app.models import Company
    c = Company(name=name or f"Beispiel {uuid.uuid4().hex[:8]}")
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def _stelle(session, firma, status):
    from app.models import Job
    j = Job(company_id=firma.id, company_name=firma.name, title="Teststelle", status=status,
            dedup_key=uuid.uuid4().hex)
    session.add(j)
    session.commit()
    session.refresh(j)
    return j


def _mail(session, job, absender):
    """Eigener Betreff und Empfangszeit: Die Test-DB ist geteilt, andere Tests suchen Mails über
    Betreffe wie „Ihre Bewerbung“ und erwarten eine Empfangszeit."""
    import datetime
    from app.models import Email
    session.add(Email(job_id=job.id, company_id=job.company_id, direction="incoming",
                      from_addr=absender, subject=f"Suchlisten-Probe {uuid.uuid4().hex[:6]}",
                      received_at=datetime.datetime(2026, 10, 19, 8, 0),
                      gmail_message_id=f"p280-{uuid.uuid4().hex[:10]}", is_response=False,
                      needs_reply=False))
    session.commit()


def _kontakt(session, job, name, email=None, rolle=None):
    from app.models import Contact
    session.add(Contact(company_id=job.company_id, job_id=job.id, name=name, email=email, role=rolle))
    session.commit()


def _domain():
    return f"firma-{uuid.uuid4().hex[:8]}.example"


def test_domain_einer_laufenden_bewerbung_kommt_in_die_suche(session):
    """Der Anlass: Interview läuft, Recruiter ohne Adresse, bisher nur eine Mail von careers@ —
    deren Domain fängt jetzt auch die persönliche Post."""
    from pipeline.mail_suchlisten import suchlisten
    d = _domain()
    job = _stelle(session, _firma(session), "Interview")
    _mail(session, job, f"Beispiel Careers <careers@{d}>")
    _kontakt(session, job, "Erika Musterfrau", rolle="Senior Talent Acquisition Partner")
    listen = suchlisten()
    assert d in listen["domains"]
    assert "Erika Musterfrau" in listen["ohne_mail"]


def test_beworben_und_angebot_zaehlen_als_laufend(session):
    from pipeline.mail_suchlisten import suchlisten
    d1, d2 = _domain(), _domain()
    _mail(session, _stelle(session, _firma(session), "Beworben"), f"hr@{d1}")
    _mail(session, _stelle(session, _firma(session), "Angebot"), f"Personal <personal@{d2}>")
    assert {d1, d2} <= set(suchlisten()["domains"])


def test_terminale_und_noch_nicht_beworbene_stellen_bleiben_draussen(session):
    from pipeline.mail_suchlisten import suchlisten
    d_absage, d_pruefen = _domain(), _domain()
    _mail(session, _stelle(session, _firma(session), "Absage"), f"hr@{d_absage}")
    _mail(session, _stelle(session, _firma(session), "Prüfen"), f"hr@{d_pruefen}")
    domains = suchlisten()["domains"]
    assert d_absage not in domains
    assert d_pruefen not in domains


def test_portale_und_ats_bleiben_gesperrt(session):
    """Eine LinkedIn-Bestätigung an einer laufenden Bewerbung darf nicht die ganze LinkedIn-Post
    in die Suche holen; ATS und Freemail ebenso wenig."""
    from pipeline.mail_suchlisten import suchlisten
    job = _stelle(session, _firma(session), "Beworben")
    for absender in ("LinkedIn <jobs-noreply@linkedin.com>", "noreply@myworkday.com",
                     "jemand@gmail.com", "Portal <info@mail.stepstone.de>"):
        _mail(session, job, absender)
    domains = suchlisten()["domains"]
    for gesperrt in ("linkedin.com", "myworkday.com", "gmail.com", "mail.stepstone.de"):
        assert gesperrt not in domains


def test_kontaktadresse_einer_laufenden_bewerbung_liefert_auch_die_domain(session):
    from pipeline.mail_suchlisten import suchlisten
    d = _domain()
    job = _stelle(session, _firma(session), "Interview")
    _kontakt(session, job, "Max Mustermann", email=f"max.mustermann@{d}", rolle="Hiring Manager")
    listen = suchlisten()
    assert f"max.mustermann@{d}" in listen["adressen"]
    assert d in listen["domains"]


def test_berater_regeln_aus_phase_80_bleiben(session):
    """Unverändert: Berater-Adresse und -Domain auch an einer terminalen Stelle; ein Nicht-Berater
    an einer terminalen Stelle fällt heraus."""
    from pipeline.mail_suchlisten import suchlisten
    d_berater, d_sachb = _domain(), _domain()
    job = _stelle(session, _firma(session), "Absage")
    _kontakt(session, job, "Berta Beraterin", email=f"berta@{d_berater}", rolle="Personalberaterin")
    _kontakt(session, job, "Sven Sachbearbeiter", email=f"sven@{d_sachb}", rolle="Sachbearbeitung")
    listen = suchlisten()
    assert f"berta@{d_berater}" in listen["adressen"]
    assert d_berater in listen["domains"]
    assert f"sven@{d_sachb}" not in listen["adressen"]
    assert d_sachb not in listen["domains"]


def test_domain_von_liest_auch_name_und_spitze_klammern():
    from pipeline.mail_suchlisten import domain_von
    assert domain_von("Beispiel Careers <careers@Beispiel.Example>") == "beispiel.example"
    assert domain_von("a.b+c@x-y.example.de") == "x-y.example.de"
    assert domain_von("keine adresse") is None
    assert domain_von(None) is None


def test_cli_druckt_die_drei_beschrifteten_zeilen(session, capsys):
    from pipeline import mail_suchlisten
    mail_suchlisten.main()
    zeilen = capsys.readouterr().out.splitlines()
    assert [z.split(":", 1)[0] for z in zeilen] == ["ADRESSEN", "DOMAINS", "OHNE_MAIL"]
    domains = zeilen[1].split(":", 1)[1].strip()
    assert all(t == "OR" or t.startswith("@") for t in domains.split())


def test_ingest_traegt_die_adresse_am_vorhandenen_kontakt_nach(session):
    """Kontakt ohne Adresse, gleicher Name, gleiche Firma → Adresse nachgetragen, keine Dublette."""
    from sqlmodel import select
    import pipeline.gmail_ingest as gi
    from app.models import Contact
    d = _domain()
    firma = _firma(session)
    job = _stelle(session, firma, "Interview")
    _kontakt(session, job, "Erika  Musterfrau", rolle="Recruiter")
    gi.ingest_emails([{
        "gmail_message_id": f"p280-{uuid.uuid4().hex[:10]}", "direction": "incoming",
        "from_addr": f"erika.musterfrau@{d}", "subject": f"{firma.name} - Teststelle",
        "snippet": "Danke für das Gespräch", "received_at": "2026-10-19T08:57:38Z",
        "category": "Sonstige", "company": firma.name, "job_title": job.title,
        "contact": {"name": "erika musterfrau", "email": f"erika.musterfrau@{d}"},
    }])
    session.expire_all()
    kontakte = session.exec(select(Contact).where(Contact.company_id == firma.id)).all()
    assert len(kontakte) == 1
    assert kontakte[0].email == f"erika.musterfrau@{d}"
    assert kontakte[0].role == "Recruiter"


def test_ingest_legt_bei_anderem_namen_weiter_einen_neuen_kontakt_an(session):
    from sqlmodel import select
    import pipeline.gmail_ingest as gi
    from app.models import Contact
    d = _domain()
    firma = _firma(session)
    job = _stelle(session, firma, "Interview")
    _kontakt(session, job, "Erika Musterfrau", rolle="Recruiter")
    gi.ingest_emails([{
        "gmail_message_id": f"p280-{uuid.uuid4().hex[:10]}", "direction": "incoming",
        "from_addr": f"max@{d}", "subject": "Termin", "snippet": "Terminvorschlag",
        "received_at": "2026-10-19T09:00:00Z", "category": "Sonstige",
        "company": firma.name, "job_title": job.title,
        "contact": {"name": "Max Mustermann", "email": f"max@{d}"},
    }])
    session.expire_all()
    kontakte = session.exec(select(Contact).where(Contact.company_id == firma.id)).all()
    assert sorted((k.name, k.email) for k in kontakte) == [
        ("Erika Musterfrau", None), ("Max Mustermann", f"max@{d}")]
