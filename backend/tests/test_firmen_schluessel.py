"""Firmen-Schlüssel über verschiedene Schreibweisen hinweg (P2-39, 12.09.2026).

Fall A (Rückmeldung aus dem Betrieb): Eine neue Stelle wurde im Tageslauf nicht als Dublette
einer bestehenden erkannt. Die bestehende Stelle (Status Interview) hängt an der Firma
„Musterwerk“, die neue an „Musterwerk GmbH“ — zwei Firmen-Rows für denselben Arbeitgeber. JEDE Dublettenstufe beginnt mit dem Firmennamen
(`dedup_key`, der Firma+Titel-Schlüssel, der Textvergleichs-Pool) — die beiden Schreibweisen
landeten deshalb nie im selben Vergleich.

`normalize.firma_key()` bereinigt den Firmenteil um Rechtsform-/Regionszusätze (Messung
12.09.2026, read-only, 470 Firmen/548 aktive Stellen, s. tasks/spec_p2-39_firmen_schluessel.md
§2: 15 Firmen-Gruppen fallen zusammen, 5 Stellen-Gruppen kommen neu zusammen, 0 Fehlalarme).
Verwendet in `ingest._stellen_schluessel`, dem Textvergleichs-Pool (`ingest.py` UND
`dedup_text._aktive_jobs_je_firma`) und `ingest._get_or_create_company`. `ct_key`/`dedup_key`
bleiben bewusst roh (s. deren Kommentare in normalize.py) — `gmail_ingest._match_job` braucht
die exakte, unbereinigte Firma+Titel-Zuordnung für die Mail→Stelle-Zuordnung.

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention).
"""
import uuid


def _mit_synthetischer_leerer_config(monkeypatch, tmp_path):
    """s. tests/test_ingest_repost_selber_lauf.py::_mit_synthetischer_leerer_config — identisches
    Muster: `dedup_text.konfiguration()` (von `ingest_records()` IMMER aufgerufen) würde ohne
    Patch mit SystemExit abbrechen, weil `config/suchprofile.yaml` gitignored ist und in CI
    fehlt."""
    import pipeline.dedup_text as dedup_text

    leere_config = tmp_path / "suchprofile.yaml"
    leere_config.write_text("dedup_text: {}\n", encoding="utf-8")
    monkeypatch.setattr(dedup_text, "CONFIG_FILE", leere_config)


def _verifikation(beleg: str) -> dict:
    return {"status": "BESTÄTIGT", "beleg": beleg, "geprueft_am": "2026-09-12"}


def _neue_url() -> str:
    return f"https://example.test/job/{uuid.uuid4().hex[:8]}"


def _firma_mit_namen(session, name: str):
    """Company MIT dem exakt übergebenen Namen anlegen (kein Auto-Suffix) — die Tests hier
    brauchen volle Kontrolle über die Basis-Schreibweise, um daraus gezielt eine zweite,
    bereinigt-gleiche Schreibweise abzuleiten (z. B. `basis` und `f"{basis} GmbH"`).
    `company.name` trägt einen UNIQUE-Index, deshalb ruft jeder Test mit einem eigenen,
    per-uuid eindeutigen `name` (die Suite teilt sich eine session-weite tmp-DB)."""
    from app.models import Company

    comp = Company(name=name)
    session.add(comp)
    session.commit()
    session.refresh(comp)
    return comp


def _job_anlegen(session, comp, *, title, status="Prüfen", found_date="2026-08-23", url=None):
    """Job DIREKT über die Session anlegen (Muster test_ingest_neuausschreibung.py::
    _job_anlegen) — simuliert einen BESTEHENDEN Job, der NICHT über `ingest_records()`
    eingeliefert wird."""
    from app.models import Job
    from app import normalize as N

    job = Job(company_id=comp.id, company_name=comp.name, title=title, status=status,
              portal="LinkedIn", found_date=found_date, url=url,
              dedup_key=N.dedup_key(comp.name, title))
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


# Anzeigentext wie ihn zwei Anzeigen derselben Rolle teilen würden (>= 400 Zeichen, die
# dedup_text.konfiguration()-Default-Schranke `min_text_zeichen`) — Muster
# test_ingest_repost_selber_lauf.py::_ANZEIGENTEXT, hier unabhängig dupliziert (kein
# app.*/pipeline.*-Import auf Modulebene, deshalb keine Konstante aus dem anderen Testmodul
# importiert).
_ANZEIGENTEXT = (
    "Wir suchen eine erfahrene Führungskraft für den Bereich Professional Services. Sie "
    "verantworten den Aufbau eines internationalen Delivery-Teams, steuern die Cloud-Operations-"
    "Strategie und arbeiten eng mit Vertrieb und Produkt zusammen. Erfahrung im Lösungsvertrieb "
    "sowie im Aufbau skalierbarer Prozesse ist erforderlich. Sie berichten direkt an die "
    "Geschäftsführung und verantworten ein Budget von mehreren Millionen Euro jährlich in einem "
    "wachsenden internationalen Markt mit hoher Wettbewerbsdynamik und komplexen Kundenprojekten."
)
assert len(_ANZEIGENTEXT) >= 400


# ── 1. firma_key: bekannte Gruppen aus der Messung (§2 der Spec) fallen zusammen ────────────
def test_firma_key_gleiche_firma_verschiedene_schreibweisen():
    from app.normalize import firma_key

    paare = [
        ("Musterwerk", "Musterwerk GmbH"),
        ("Softkern", "Softkern SE"),
        ("Alpha", "Alpha Deutschland"),
        ("Sonnenwerk", "Sonnenwerk EMEA"),
        ("Kontor", "Kontor SE"),
        # Seitenzusätze (26.10.2026): Stellenseite eines Vermittlers auf LinkedIn
        ("Beispiel | Talente", "Beispiel | Talente Jobs"),
        ("Beispiel", "Beispiel Careers"),
        ("Beispiel", "Beispiel Karriere"),
    ]
    for kurz, lang in paare:
        assert firma_key(kurz) == firma_key(lang), (kurz, lang, firma_key(kurz), firma_key(lang))


# ── 2. firma_key trennt weiterhin echte Namensbestandteile ─────────────────────────────────
def test_firma_key_trennt_echte_namensbestandteile():
    from app.normalize import firma_key

    assert firma_key("Beta") != firma_key("Beta Consulting")
    assert firma_key("Gamma Data") != firma_key("Gamma Security")


# ── 3. Rückfall: Name besteht nur aus Zusatzwörtern -> unbereinigter Slug, nie leer ─────────
def test_firma_key_rueckfall_nur_zusatzwoerter_liefert_unbereinigten_slug():
    from app.normalize import firma_key, _slug

    for name in ("SE Group", "GmbH", "AG International", "Holding", "Jobs"):
        erwartet = _slug(name)
        assert erwartet, f"Testvoraussetzung verletzt: {name!r} slugifiziert zu leer"
        assert firma_key(name) == erwartet, (name, firma_key(name), erwartet)
    assert firma_key("") == ""
    assert firma_key(None) == ""


# ── 4. Fall A: laufende Stelle unter anderer Schreibweise -> Dublette ─────────────
def test_fall_a_laufende_stelle_wird_ueber_schreibweise_hinweg_dublette(
    session, monkeypatch, tmp_path
):
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from pipeline.ingest import ingest_records, _stellen_schluessel

    suffix = uuid.uuid4().hex[:8]
    titel = "Director Musterdienste (m/w/x)"
    basis = f"Musterwerk {suffix}"
    lang = f"{basis} GmbH"

    # Stellen-Schlüssel identisch trotz abweichender Firmen-Schreibweise (bereinigter Firmenteil,
    # Titel unverändert) — genau das, was die alte, rohe ct_key-Prüfung verfehlte.
    assert _stellen_schluessel(basis, titel) == _stellen_schluessel(lang, titel)

    alt_comp = _firma_mit_namen(session, basis)
    _job_anlegen(session, alt_comp, title=titel, status="Interview", found_date="2026-08-31")

    rec = {"company": lang, "title": titel, "url": _neue_url(),
           "verifikation": _verifikation("Live gesehen — Recruitee 12.09.")}
    result = ingest_records([rec])

    assert result["dup"] == 1, result
    assert result["new"] == 0, result


# ── 5. Fall-A-Variante mit Endstatus -> Neuausschreibung über Schreibweisen hinweg ────────
def test_fall_a_endstatus_wird_ueber_schreibweise_hinweg_neuausschreibung(
    session, monkeypatch, tmp_path
):
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from sqlmodel import select
    from app.models import Job
    from pipeline.ingest import ingest_records

    suffix = uuid.uuid4().hex[:8]
    titel = "Director Musterdienste (m/w/x)"
    basis = f"Musterwerk-Neu {suffix}"
    lang = f"{basis} GmbH"

    alt_comp = _firma_mit_namen(session, basis)
    alt = _job_anlegen(session, alt_comp, title=titel, status="Kein Match", found_date="2026-08-31")

    url = _neue_url()
    rec = {"company": lang, "title": titel, "url": url,
           "verifikation": _verifikation("Live gesehen — Recruitee 12.09.")}
    result = ingest_records([rec])

    assert result["new"] == 1, result
    assert result["neuausschreibungen"] == 1, result

    neu = session.exec(select(Job).where(Job.url == url)).one()
    assert f"NEUAUSSCHREIBUNG? Job {alt.id}" in (neu.verify_note or ""), neu.verify_note
    assert "Kein Match" in (neu.verify_note or ""), neu.verify_note


# ── 6. _get_or_create_company: eine Row bei einem Treffer, keine bei Mehrdeutigkeit ─────────
def test_get_or_create_company_findet_bestehende_firma_ueber_firma_key(session):
    from pipeline.ingest import _get_or_create_company
    from sqlmodel import select
    from app.models import Company

    suffix = uuid.uuid4().hex[:8]
    basis = f"Musterwerk-GOC {suffix}"
    bestehend = _firma_mit_namen(session, basis)

    gefunden = _get_or_create_company(session, {}, f"{basis} GmbH")

    assert gefunden is not None
    assert gefunden.id == bestehend.id, "Record 'Musterwerk GmbH' haette die bestehende 'Musterwerk'-Row finden muessen"

    alle = [c for c in session.exec(select(Company)).all() if c.name.startswith(basis)]
    assert len(alle) == 1, f"es darf KEINE zweite Firmen-Row entstanden sein: {[c.name for c in alle]}"


def test_get_or_create_company_bei_zwei_treffern_wird_keine_gewaehlt_neue_row(session):
    """Mehrdeutigkeit gehört an den Menschen, nicht an eine Heuristik (Muster `_MEHRDEUTIG` in
    `gmail_ingest._match_job`) — bei ZWEI bestehenden Firmen mit demselben bereinigten
    Schlüssel wird keine automatisch gewählt, es entsteht eine neue (dritte) Row."""
    from pipeline.ingest import _get_or_create_company
    from sqlmodel import select
    from app.models import Company

    suffix = uuid.uuid4().hex[:8]
    basis = f"Musterwerk-Mehrdeutig {suffix}"
    a = _firma_mit_namen(session, f"{basis} GmbH")
    b = _firma_mit_namen(session, f"{basis} AG")

    ergebnis = _get_or_create_company(session, {}, basis)

    assert ergebnis is not None
    assert ergebnis.id not in (a.id, b.id), (
        "bei zwei bestehenden Firmen mit gleichem bereinigten Schluessel darf keine automatisch "
        "gewaehlt werden"
    )

    alle = [c for c in session.exec(select(Company)).all() if c.name.startswith(basis)]
    assert len(alle) == 3, f"erwartet 3 Firmen-Rows (2 bestehende + 1 neue): {[c.name for c in alle]}"


# ── 7. Textvergleich-Pool: zwei Schreibweisen derselben Firma landen im selben Pool ─────────
def test_textvergleich_pool_ueber_firmen_schreibweisen_hinweg(session, monkeypatch, tmp_path):
    """Muster test_ingest_repost_selber_lauf.py: zwei Records mit (nahezu) identischem
    Anzeigentext + ähnlichem Titel, aber verschiedener Firmen-SCHREIBWEISE (nicht nur
    Groß-/Kleinschreibung wie im slug_parts-Regressionstest dort, sondern ein echter
    Rechtsform-Zusatz) — ohne den P2-39-Fix landen beide Records in getrennten Pool-Fächern
    und der Repost-Verdacht bliebe stumm."""
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from pipeline.ingest import ingest_records

    suffix = uuid.uuid4().hex[:8]
    basis = f"Musterwerk-Pool {suffix}"
    url_a = _neue_url()
    url_b = _neue_url()
    rec_a = {"company": basis, "title": "Senior Manager Customer Success", "url": url_a,
             "verifikation": _verifikation("Live gesehen — Portal A")}
    rec_b = {"company": f"{basis} GmbH", "title": "Senior Manager Customer Success EMEA",
             "url": url_b, "verifikation": _verifikation("Live gesehen — Portal B")}

    result = ingest_records([rec_a, rec_b], texte={url_a: _ANZEIGENTEXT, url_b: _ANZEIGENTEXT})

    assert result["new"] == 2, f"beide Records sollten als neu angelegt werden: {result}"
    assert result["dup"] == 0, f"kein mechanischer Dublette-Treffer erwartet: {result}"
    assert result["dubletten_verdacht"] == 1, (
        "zwei Schreibweisen derselben Firma muessen im selben Textvergleich-Pool landen "
        f"(Verdacht darf nicht uebersehen werden): {result}"
    )

    from sqlmodel import select
    from app.models import Job, JobLog

    job_b = session.exec(select(Job).where(Job.url == url_b)).one()
    assert "DUBLETTE?" in (job_b.verify_note or ""), job_b.verify_note

    logs = session.exec(select(JobLog).where(JobLog.job_id == job_b.id)).all()
    assert any("DUBLETTE?" in (l.eintrag or "") for l in logs), logs


# ── 8. Regression: ct_key/dedup_key bleiben roh, unveraendert durch firma_key ───────────────
def test_ct_key_und_dedup_key_bleiben_roh_unveraendert():
    """`ct_key`/`dedup_key` dürfen NICHT über `firma_key` laufen — sonst würde
    `gmail_ingest._match_job` zwei tatsächlich verschiedene Firmen mit gemeinsamem bereinigten
    Schlüssel (z. B. „Beta“/„Beta Consulting“) fälschlich für dieselbe halten. Literale Werte
    wie vor P2-39 (reiner Slug, KEINE Rechtsform-/Regionsbereinigung)."""
    from app import normalize as N

    assert N.ct_key("Musterwerk", "Director X") == "musterwerk|directorx"
    assert N.ct_key("Musterwerk GmbH", "Director X") == "musterwerkgmbh|directorx"
    assert N.ct_key("Musterwerk", "Director X") != N.ct_key("Musterwerk GmbH", "Director X"), (
        "ct_key muss zwei Firmen-Schreibweisen weiterhin auseinanderhalten (roh, s. Kommentar "
        "an ct_key in normalize.py)"
    )

    assert N.dedup_key("Musterwerk", "Director X", "Berlin") == "musterwerk|directorx|berlin"
    assert (N.dedup_key("Musterwerk", "Director X", "Berlin")
            != N.dedup_key("Musterwerk GmbH", "Director X", "Berlin")), (
        "dedup_key muss zwei Firmen-Schreibweisen weiterhin auseinanderhalten (roh)"
    )
