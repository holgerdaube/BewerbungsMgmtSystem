"""Job-Status ändern zieht den Bewerbungsstatus mit (P2-29, 08.09.2026).

ANLASS: Beim Aufräumen eines Duplikats (P2-28) fiel auf, dass `Application.status` gar
keinen Bedienweg hat. Gesetzt hat ihn ausschließlich der Mail-Ingest
(`gmail_ingest`: `app.status = rec["job_status"]`); im Job-Detail ist er reine Anzeige
(`JobDetail.tsx:1570`), und `PATCH /api/applications/{id}` erlaubt bewusst nur
`cover_letter_text`.

Die Lücke traf genau den Weg, den der Nutzer geht, wenn eine Mail NICHT automatisch zugeordnet wurde:
Mail über „Stelle zuordnen" verknüpfen (`/assign` ändert bewusst keine Status, es schlägt nur
vor) → Job-Status auf „Absage" setzen → **die Bewerbung blieb auf „Beworben"**. Im Bestand vom
08.09.2026 standen so dreizehn Bewerbungen an abgesagten Stellen weiter als laufend.

WARUM NUR VIER STATUS: `_APP_STATUS_UEBERNAHME` ist dieselbe Menge, die der Ingest setzt.
„Kein Match", „Geparkt" oder „Nicht verfügbar" beschreiben die STELLE, nicht die Bewerbung —
sie dorthin zu schreiben wäre eine neue Sorte Unsinn und hätte den Bestand nur anders kaputt
gemacht.

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention).
"""
import datetime
import itertools

import pytest

# Die Suite teilt sich EINE Datenbank (conftest `_db_ready`, scope="session") und `company.name`
# traegt einen UNIQUE-Index — ohne eindeutige Namen kollidiert der zweite Test mit dem ersten.
_ZAEHLER = itertools.count(1)


def _job_mit_bewerbung(session, *, job_status="Beworben", app_status="Beworben", firma=None):
    """Stelle + Bewerbung anlegen und die IDs zurückgeben."""
    from app.models import Application, Company, Job

    firma = firma or f"Beispiel AG {next(_ZAEHLER)}"

    c = Company(name=firma)
    session.add(c)
    session.commit()
    session.refresh(c)

    j = Job(company_id=c.id, company_name=firma, title="Director Services", portal="LinkedIn",
            status=job_status, found_date=str(datetime.date.today()),
            dedup_key=f"{firma}|director-services-{datetime.datetime.utcnow().timestamp()}".lower())
    session.add(j)
    session.commit()
    session.refresh(j)

    a = Application(job_id=j.id, status=app_status)
    session.add(a)
    session.commit()
    session.refresh(a)
    return j.id, a.id


def _status(session, app_id):
    from app.models import Application

    session.expire_all()
    return session.get(Application, app_id).status


def test_absage_am_job_zieht_die_bewerbung_mit(client, session):
    """DER Kernfall: Genau der Weg, den der Nutzer nach einer nachträglich zugeordneten Absage geht."""
    job_id, app_id = _job_mit_bewerbung(session)

    antwort = client.patch(f"/api/jobs/{job_id}", json={"status": "Absage"})

    assert antwort.status_code == 200
    assert _status(session, app_id) == "Absage"


def test_interview_und_angebot_ziehen_ebenfalls(client, session):
    """Nicht nur Absagen — der Ingest setzt dieselben vier Status, hier gilt dasselbe."""
    job_id, app_id = _job_mit_bewerbung(session)

    client.patch(f"/api/jobs/{job_id}", json={"status": "Interview"})
    assert _status(session, app_id) == "Interview"

    client.patch(f"/api/jobs/{job_id}", json={"status": "Angebot"})
    assert _status(session, app_id) == "Angebot"


def test_stellen_status_fasst_die_bewerbung_nicht_an(client, session):
    """`Kein Match`, `Geparkt` und `Nicht verfügbar` beschreiben die STELLE.

    Sie auf die Bewerbung zu schreiben, hätte den Bestand nur anders kaputt gemacht — eine
    Bewerbung ist nie „Kein Match"."""
    for stellen_status in ("Kein Match", "Geparkt", "Nicht verfügbar"):
        job_id, app_id = _job_mit_bewerbung(session)

        client.patch(f"/api/jobs/{job_id}", json={"status": stellen_status})

        assert _status(session, app_id) == "Beworben", stellen_status


def test_ohne_bewerbung_bleibt_alles_ruhig(client, session):
    """Die meisten Stellen haben gar keine Bewerbung — der PATCH darf daran nicht scheitern."""
    from app.models import Company, Job

    c = Company(name=f"Ohne Bewerbung GmbH {next(_ZAEHLER)}")
    session.add(c)
    session.commit()
    session.refresh(c)
    j = Job(company_id=c.id, company_name=c.name, title="Rolle", portal="LinkedIn",
            status="Prüfen", found_date=str(datetime.date.today()),
            dedup_key=f"ohne|bewerbung|{datetime.datetime.utcnow().timestamp()}")
    session.add(j)
    session.commit()
    session.refresh(j)

    assert client.patch(f"/api/jobs/{j.id}", json={"status": "Absage"}).status_code == 200


def test_gleicher_wert_erzeugt_keinen_log_eintrag(client, session):
    """Steht die Bewerbung schon richtig, darf kein Verlaufseintrag ohne Aussage entstehen —
    sonst wächst das Job-Log bei jedem PATCH um eine Zeile, die nichts sagt."""
    from sqlmodel import select

    from app.models import JobLog

    job_id, _ = _job_mit_bewerbung(session, app_status="Absage")

    client.patch(f"/api/jobs/{job_id}", json={"status": "Absage"})

    logs = session.exec(select(JobLog).where(JobLog.job_id == job_id)).all()
    assert not [l for l in logs if "Bewerbung:" in l.eintrag]


def test_die_aenderung_steht_im_job_log(client, session):
    """Nachvollziehbarkeit: Wer später fragt, warum die Bewerbung abgesagt ist, findet es im
    Verlauf — zusammen mit der Status-Änderung, die es ausgelöst hat."""
    from sqlmodel import select

    from app.models import JobLog

    job_id, _ = _job_mit_bewerbung(session)

    client.patch(f"/api/jobs/{job_id}", json={"status": "Absage"})

    logs = session.exec(select(JobLog).where(JobLog.job_id == job_id)).all()
    treffer = [l for l in logs if "Bewerbung: Beworben → Absage" in l.eintrag]
    assert treffer, [l.eintrag for l in logs]
    assert "Status: Beworben → Absage" in treffer[0].eintrag, "beides gehört in denselben Eintrag"
