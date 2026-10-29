"""Späte „Eingangsbestätigung" am Volltext gegenprüfen (P2-48, 25.09.2026).

Fall A (Rückmeldung aus dem Betrieb): „prüfe mal wieder, wieso du die Absage aus der eMail zum Job
bei der Beispiel GmbH nicht erkannt hast." Die Bewerbung lief am 24.07., am 25.09. kam eine Mail mit dem
Betreff „Zukunft gestalten - Ihre Bewerbung bei der Beispiel GmbH"; Betreff und Gmail-Vorschau lasen sich wie
eine Eingangsbestätigung, der Absagesatz stand erst in Absatz 2 („Leider können wir auch Sie im
weiteren Auswahlprozess nicht berücksichtigen."). Der Lauf stufte sie als Eingangsbestätigung ein,
die Stelle blieb auf „Beworben".

Die Regel dafür stand seit dem Fall vom 30.07.2026 in `email-check/SKILL.md` — Volltext
ist Pflicht, u. a. wenn die Mail später als 7 Tage nach der Bewerbung kommt — und wurde übergangen.
Deshalb hier deterministisch im Code.

MESSUNGEN, auf denen die Schwellen beruhen (25.09.2026, echter Bestand):
- Von 154 Eingangsbestätigungen kam GENAU EINE mehr als 7 Tage nach der Bewerbung: die Mail aus Fall A.
- Die Musterliste lief gegen 18 echte Volltexte: 0 Fehlalarme bei 10 Eingangsbestätigungen,
  6 von 7 bekannten Absagen erkannt, Fall A erkannt.

Kein echter Gmail-Zugriff in den Tests: `_volltext` wird gepatcht.
"""
import datetime
import uuid

import pytest


# ── Wortliste ───────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "Leider können wir auch Sie im weiteren Auswahlprozess nicht berücksichtigen.",
    "Wir haben uns leider für einen anderen Bewerber entschieden.",
    "We regret to inform you that we will not be moving forward with your application.",
    "Unfortunately, we have decided to proceed with other candidates.",
    "Ihre Bewerbung konnte nicht in die engere Wahl kommen.",
])
def test_absage_formulierungen_werden_erkannt(text):
    from pipeline.gmail_ingest import absage_im_volltext

    assert absage_im_volltext(text) is True


@pytest.mark.parametrize("text", [
    "Vielen Dank für Ihre Bewerbung. Wir prüfen Ihre Unterlagen und melden uns in Kürze.",
    "Ihre Bewerbung ist bei uns eingegangen und wird nun gesichtet.",
    # Bedingungssätze stehen so in ECHTEN Eingangsbestätigungen — ohne den Vorlauf-Check
    # (`_BEDINGUNG_RE`) hätten beide als Absage angeschlagen.
    "Sollten wir Sie nicht berücksichtigen können, melden wir uns innerhalb von 14 Tagen.",
    "Falls wir Sie nicht weiter berücksichtigen, erhalten Sie eine Nachricht von uns.",
    "",
])
def test_harmlose_bestaetigungen_schlagen_nicht_an(text):
    from pipeline.gmail_ingest import absage_im_volltext

    assert absage_im_volltext(text) is False


# ── Die drei Bedingungen ────────────────────────────────────────────────────────────────────
def _zeit(tage_nach):
    beworben = datetime.datetime(2026, 7, 24, 9, 0)
    return beworben, beworben + datetime.timedelta(days=tage_nach)


def _volltext_verboten(monkeypatch):
    """Der Volltext darf nur im seltenen Verdachtsfall geladen werden — sonst kostet jede Mail
    einen Gmail-Aufruf. Der Patch macht einen Aufruf tödlich."""
    import pipeline.gmail_ingest as gi

    def _nie(_mid):
        raise AssertionError("Volltext darf hier nicht geladen werden")

    monkeypatch.setattr(gi, "_volltext", _nie)


def test_fall_a_wird_erkannt(monkeypatch):
    import pipeline.gmail_ingest as gi

    beworben, empfangen = _zeit(63)
    monkeypatch.setattr(gi, "_volltext", lambda _mid: (
        "vielen Dank für Ihre Bewerbung bei der Beispiel GmbH … Leider können wir auch Sie im weiteren "
        "Auswahlprozess nicht berücksichtigen."))

    assert gi.spaete_absage_erkennen("msg-1", "Eingangsbestätigung", empfangen, beworben) is True


def test_bestaetigung_kurz_nach_der_bewerbung_bleibt_unberuehrt(monkeypatch):
    """Sieben Tage sind die Grenze aus der SKILL.md-Regel — darunter wird nicht nachgeladen."""
    import pipeline.gmail_ingest as gi

    _volltext_verboten(monkeypatch)
    beworben, empfangen = _zeit(3)

    assert gi.spaete_absage_erkennen("msg-1", "Eingangsbestätigung", empfangen, beworben) is False


@pytest.mark.parametrize("kategorie", ["Absage", "Einladung", "Angebot", "Rückfrage", "Sonstige"])
def test_andere_kategorien_werden_nicht_angefasst(monkeypatch, kategorie):
    """Das Netz stuft nur „Eingangsbestätigung" herauf — es entscheidet nie gegen den Lauf."""
    import pipeline.gmail_ingest as gi

    _volltext_verboten(monkeypatch)
    beworben, empfangen = _zeit(63)

    assert gi.spaete_absage_erkennen("msg-1", kategorie, empfangen, beworben) is False


def test_spaete_bestaetigung_ohne_absagesatz_bleibt_bestaetigung(monkeypatch):
    import pipeline.gmail_ingest as gi

    beworben, empfangen = _zeit(63)
    monkeypatch.setattr(gi, "_volltext", lambda _mid: "Ihre Bewerbung ist weiterhin im Prozess.")

    assert gi.spaete_absage_erkennen("msg-1", "Eingangsbestätigung", empfangen, beworben) is False


def test_ohne_ladbaren_volltext_bleibt_es_bei_der_einstufung(monkeypatch):
    """Kein Netz, Mail gelöscht: lieber die Einstufung des Laufs behalten als raten."""
    import pipeline.gmail_ingest as gi

    beworben, empfangen = _zeit(63)
    monkeypatch.setattr(gi, "_volltext", lambda _mid: None)

    assert gi.spaete_absage_erkennen("msg-1", "Eingangsbestätigung", empfangen, beworben) is False


def test_ohne_bewerbungszeitpunkt_kein_verdacht(monkeypatch):
    """Ohne Anker (Stelle ohne Bewerbungsdatum) fehlt die Grundlage — dann greift das Netz nicht."""
    import pipeline.gmail_ingest as gi

    _volltext_verboten(monkeypatch)
    _, empfangen = _zeit(63)

    assert gi.spaete_absage_erkennen("msg-1", "Eingangsbestätigung", empfangen, None) is False


# ── Gesamter Ingest-Durchlauf ───────────────────────────────────────────────────────────────
def test_ingest_traegt_die_absage_nach(session, monkeypatch):
    """Ende zu Ende: Aus der als Eingangsbestätigung gemeldeten Mail wird eine Absage — in der
    Mail-Zeile, am Job, an der Bewerbung, im Verlauf und in der Zusammenfassung des Laufs."""
    from sqlmodel import select
    import pipeline.gmail_ingest as gi
    from app.models import Application, Company, Email, Job, JobLog

    comp = Company(name=f"Waermedienst {uuid.uuid4().hex[:6]}")
    session.add(comp)
    session.commit()
    session.refresh(comp)
    job = Job(company_id=comp.id, company_name=comp.name, title="Head of IT Infrastructure",
              status="Beworben", found_date="2026-07-24", dedup_key=uuid.uuid4().hex)
    session.add(job)
    session.commit()
    session.refresh(job)
    session.add(Application(job_id=job.id, status="Beworben", applied_date="2026-07-24"))
    session.commit()

    monkeypatch.setattr(gi, "_volltext", lambda _mid: (
        "Guten Tag, vielen Dank für Ihre Bewerbung. Leider können wir auch Sie im weiteren "
        "Auswahlprozess nicht berücksichtigen. Freundliche Grüße, Ihr HR Team"))

    mid = f"synthetisch-p248-{uuid.uuid4().hex[:8]}"
    ergebnis = gi.ingest_emails([{
        "gmail_message_id": mid, "direction": "incoming",
        "from_addr": "karriere@waermedienst.example", "subject": "Ihre Bewerbung bei uns",
        "snippet": "vielen Dank für Ihre Bewerbung", "received_at": "2026-09-25T13:05:48Z",
        "category": "Eingangsbestätigung", "company": comp.name,
        "job_title": job.title, "job_status": "Beworben",
    }])

    assert ergebnis["spaete_absagen"] == 1
    session.expire_all()
    mail = session.exec(select(Email).where(Email.gmail_message_id == mid)).one()
    assert mail.category == "Absage"
    assert mail.job_id == job.id
    assert session.get(Job, job.id).status == "Absage"
    assert session.exec(select(Application).where(Application.job_id == job.id)).one().status == "Absage"
    eintraege = session.exec(select(JobLog).where(JobLog.job_id == job.id)).all()
    assert any("Absage aus dem Mail-Volltext erkannt" in (e.eintrag or "") for e in eintraege), eintraege


def test_ingest_laesst_eine_frische_bestaetigung_in_ruhe(session, monkeypatch):
    """Gegenprobe: dieselbe Mail drei Tage nach der Bewerbung bleibt Eingangsbestätigung — und
    der Volltext wird gar nicht erst geladen."""
    from sqlmodel import select
    import pipeline.gmail_ingest as gi
    from app.models import Application, Company, Email, Job

    comp = Company(name=f"Frischfall {uuid.uuid4().hex[:6]}")
    session.add(comp)
    session.commit()
    session.refresh(comp)
    job = Job(company_id=comp.id, company_name=comp.name, title="Head of Delivery",
              status="Beworben", found_date="2026-09-22", dedup_key=uuid.uuid4().hex)
    session.add(job)
    session.commit()
    session.refresh(job)
    session.add(Application(job_id=job.id, status="Beworben", applied_date="2026-09-22"))
    session.commit()
    _volltext_verboten(monkeypatch)

    mid = f"synthetisch-p248-{uuid.uuid4().hex[:8]}"
    ergebnis = gi.ingest_emails([{
        "gmail_message_id": mid, "direction": "incoming",
        "from_addr": "karriere@frischfall.example", "subject": "Ihre Bewerbung bei uns",
        "snippet": "vielen Dank", "received_at": "2026-09-25T13:05:48Z",
        "category": "Eingangsbestätigung", "company": comp.name,
        "job_title": job.title, "job_status": "Beworben",
    }])

    assert ergebnis["spaete_absagen"] == 0
    session.expire_all()
    assert session.exec(select(Email).where(Email.gmail_message_id == mid)).one().category == "Eingangsbestätigung"
    assert session.get(Job, job.id).status == "Beworben"
