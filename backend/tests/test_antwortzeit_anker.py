"""Regressionstest für P2-17 (Phase 92): Antwortzeit gegen die RICHTIGE Bewerbung.

Fall A (aufgefallen am 26.08.2026 bei der Aufarbeitung von P2-16):
Es gab zwei Bewerbungen bei derselben Firma — im Juli auf „Division Lead Musterbereich"
(Stelle A) und am 23.08. auf „Team Lead Musterbereich" (Stelle B). Die Absage zur zweiten
Bewerbung kam am 26.08., also nach rund 72 Stunden. In der DB stand sie mit **1358,9 h**.

Ursache: `applied_at` in `gmail_ingest.py` war allein nach FIRMENNAMEN verschlüsselt und nahm
das Minimum — also die früheste Bewerbung bei dieser Firma. Jede Antwort auf eine spätere
Bewerbung wurde damit gegen die erste gerechnet. Betroffen ist jede mehrfach angeschriebene
Firma; der Effekt zieht die Durchschnitts-Antwortzeit (pipeline/digest.py, app/response_metrics.py)
systematisch nach oben.

Zweiter Befund: `POST /api/emails/{id}/assign` (app/main.py) rechnete schon immer gegen die
Bewerbung selbst. Vor der Umstellung lieferten die beiden Wege für dieselbe Mail unterschiedliche
Zahlen — je nachdem, ob sie im Lauf oder von Hand zugeordnet wurde. `test_beide_wege_*` hält fest,
dass das nicht wieder auseinanderläuft.

Der Firmen-Anker bleibt bewusst als Rückfallebene für Mails ohne Stellenzuordnung
(`test_ohne_stellenzuordnung_*`) — für die gibt es keine Bewerbung, an der sie hängen könnten.

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention).
"""
import datetime


def _dt(tag: str) -> datetime.datetime:
    return datetime.datetime.strptime(tag, "%Y-%m-%d")


def test_anker_nimmt_die_eigene_bewerbung_nicht_die_frueheste_der_firma():
    """DER Kernfall, direkt am Helfer: zwei Bewerbungen bei derselben Firma, die Antwort gehört
    zur zweiten. Ohne den Fix käme der Juli-Termin heraus (die 1358,9-h-Rechnung)."""
    from pipeline.gmail_ingest import anker_fuer_antwortzeit

    je_bewerbung = {25: _dt("2026-07-01"), 120: _dt("2026-08-23")}
    je_firma = {"beispiel analytics": _dt("2026-07-01")}

    assert anker_fuer_antwortzeit(je_bewerbung, je_firma, 120, "beispiel analytics") == _dt("2026-08-23")


def test_ohne_stellenzuordnung_bleibt_der_firmen_anker():
    """Rückfallebene: Eine Absage ohne erkennbaren Stellenbezug hat keine Bewerbung — für sie
    ist die früheste Bewerbung bei der Firma weiterhin die beste verfügbare Schätzung."""
    from pipeline.gmail_ingest import anker_fuer_antwortzeit

    je_firma = {"beispiel analytics": _dt("2026-07-01")}

    assert anker_fuer_antwortzeit({}, je_firma, None, "beispiel analytics") == _dt("2026-07-01")


def test_bewerbung_ohne_datum_faellt_auf_die_firma_zurueck():
    """Eine Bewerbung ohne `applied_date` (kommt vor, wenn der Lauf sie selbst anlegt) darf die
    Antwortzeit nicht verschlucken — dann greift der Firmen-Anker."""
    from pipeline.gmail_ingest import anker_fuer_antwortzeit

    je_firma = {"buchi": _dt("2026-08-09")}

    assert anker_fuer_antwortzeit({95: None}, je_firma, 95, "buchi") == _dt("2026-08-09")


def test_ohne_jeden_anker_keine_antwortzeit():
    from pipeline.gmail_ingest import anker_fuer_antwortzeit

    assert anker_fuer_antwortzeit({}, {}, 7, "unbekannt") is None
    assert anker_fuer_antwortzeit({}, {}, None, None) is None


def test_ingest_rechnet_die_zweite_bewerbung_gegen_ihr_eigenes_datum(session):
    """Der Kernfall durch den ECHTEN Ingest — Nachbau der Lage aus Fall A.

    Zwei Stellen derselben Firma mit eigener Bewerbung (Juli und 23.08.), dann die Absage vom
    26.08. zur zweiten Stelle. Erwartet werden rund 72 Stunden, nicht die 1358,9 h ab der
    Juli-Bewerbung.
    """
    from sqlmodel import select

    from app.models import Application, Company, Email, Job
    from pipeline.gmail_ingest import ingest_emails

    firma = Company(name="Beispiel Analytics")
    session.add(firma)
    session.commit()
    session.refresh(firma)

    for titel, datum in (("Division Lead Musterbereich", "2026-07-01"),
                         ("Team Lead Musterbereich", "2026-08-23")):
        job = Job(company_id=firma.id, company_name=firma.name, title=titel,
                  portal="LinkedIn", status="Beworben", found_date=datum,
                  dedup_key="beispiel-" + titel.lower().replace(" ", "-"))
        session.add(job)
        session.commit()
        session.refresh(job)
        session.add(Application(job_id=job.id, status="Beworben", applied_date=datum,
                                channel="E-Mail"))
    session.commit()

    ingest_emails([{
        "gmail_message_id": "test-absage-beispiel",
        "gmail_thread_id": "test-absage-beispiel",
        "direction": "incoming",
        "from_addr": "LinkedIn <jobs-noreply@linkedin.com>",
        "subject": "Your application to Team Lead Musterbereich at Beispiel Analytics",
        "received_at": "2026-08-26T14:54:11Z",
        "company": "Beispiel Analytics",
        "job_title": "Team Lead Musterbereich",
        "category": "Absage",
    }])

    mail = session.exec(select(Email).where(Email.gmail_message_id == "test-absage-beispiel")).one()
    assert mail.response_time_hours is not None, "Antwortzeit muss berechnet sein"
    assert 60 < mail.response_time_hours < 90, (
        "erwartet werden rund 72 h ab der Bewerbung vom 23.08., bekam "
        f"{mail.response_time_hours} h — bei ~1359 h wird wieder gegen die Juli-Bewerbung "
        "derselben Firma gerechnet")


def test_beide_wege_liefern_dieselbe_antwortzeit(session, client):
    """`assign_email` rechnete schon immer gegen die Bewerbung selbst, der Ingest gegen die
    Firma. Für dieselbe Mail kamen so je nach Weg verschiedene Zahlen heraus. Dieser Test hält
    fest, dass Lauf und Hand-Zuordnung übereinstimmen."""
    from sqlmodel import select

    from app.models import Application, Company, Email, Job
    from pipeline.gmail_ingest import ingest_emails

    firma = Company(name="Doppelbewerber GmbH")
    session.add(firma)
    session.commit()
    session.refresh(firma)

    jobs = []
    for titel, datum in (("Erste Rolle", "2026-06-01"), ("Zweite Rolle", "2026-08-20")):
        job = Job(company_id=firma.id, company_name=firma.name, title=titel, portal="LinkedIn",
                  status="Beworben", found_date=datum, dedup_key="doppel-" + titel.lower())
        session.add(job)
        session.commit()
        session.refresh(job)
        session.add(Application(job_id=job.id, status="Beworben", applied_date=datum,
                                channel="E-Mail"))
        jobs.append(job)
    session.commit()

    ingest_emails([{
        "gmail_message_id": "test-doppel-absage",
        "gmail_thread_id": "test-doppel-absage",
        "direction": "incoming", "from_addr": "hr@doppelbewerber.example",
        "subject": "Ihre Bewerbung", "received_at": "2026-08-25T09:00:00Z",
        "company": "Doppelbewerber GmbH", "job_title": "Zweite Rolle", "category": "Absage",
    }])

    mail = session.exec(select(Email).where(Email.gmail_message_id == "test-doppel-absage")).one()
    aus_dem_lauf = mail.response_time_hours

    # Dieselbe Mail von Hand derselben Stelle zuordnen — der Endpunkt rechnet neu.
    antwort = client.post(f"/api/emails/{mail.id}/assign", json={"job_id": jobs[1].id})
    assert antwort.status_code == 200, antwort.text

    assert antwort.json()["email"]["response_time_hours"] == aus_dem_lauf, (
        "Lauf und Hand-Zuordnung müssen dieselbe Antwortzeit ergeben")


def test_joblog_liefert_den_anker_wenn_applied_date_fehlt(session):
    """DER eigentliche Fall A: Die Bewerbung hat KEIN `applied_date` — wie die Mehrzahl der
    Bewerbungen im Bestand. Ohne die JobLog-Stufe fiele die Rechnung auf den Firmen-Anker
    zurück und bliebe bei den 1358,9 h; die Umstellung wäre für genau den auslösenden Fall wirkungslos.

    Das JobLog protokolliert den Statuswechsel automatisch bei jedem PATCH — für Stelle B steht
    dort der 23.08.2026, dasselbe Datum, das LinkedIn im Mailtext nennt ("Applied on Aug 23").
    """
    import datetime as dt

    from app.models import Application, Company, Job, JobLog
    from pipeline.gmail_ingest import bewerbungs_anker

    firma = Company(name="Ankerlos GmbH")
    session.add(firma)
    session.commit()
    session.refresh(firma)

    job = Job(company_id=firma.id, company_name=firma.name, title="Zweite Rolle",
              portal="LinkedIn", status="Beworben", found_date="2026-08-22",
              dedup_key="ankerlos-zweite")
    session.add(job)
    session.commit()
    session.refresh(job)

    app_ohne_datum = Application(job_id=job.id, status="Beworben", applied_date=None,
                                 channel="E-Mail")
    session.add(app_ohne_datum)
    session.add(JobLog(job_id=job.id, art="auto", eintrag="Status: Prüfen → Beworben",
                       created_at=dt.datetime(2026, 8, 23, 9, 37)))
    # Ein späterer Wechsel WEG von Beworben darf den Anker nicht verschieben.
    session.add(JobLog(job_id=job.id, art="auto", eintrag="Status: Beworben → Absage",
                       created_at=dt.datetime(2026, 8, 26, 16, 1)))
    session.commit()
    session.refresh(app_ohne_datum)

    anker = bewerbungs_anker(session)

    assert anker.get(app_ohne_datum.id) == dt.datetime(2026, 8, 23, 9, 37), (
        "ohne die JobLog-Stufe bleibt diese Bewerbung ankerlos und fällt auf die Firma zurück")


def test_applied_date_schlaegt_das_joblog(session):
    """Rangfolge: Ein von Hand gepflegtes `applied_date` ist die verlässlichere Angabe und geht
    dem automatischen Logeintrag vor."""
    import datetime as dt

    from app.models import Application, Company, Job, JobLog
    from pipeline.gmail_ingest import bewerbungs_anker

    firma = Company(name="Rangfolge AG")
    session.add(firma)
    session.commit()
    session.refresh(firma)
    job = Job(company_id=firma.id, company_name=firma.name, title="Rolle", portal="LinkedIn",
              status="Beworben", found_date="2026-07-01", dedup_key="rangfolge-rolle")
    session.add(job)
    session.commit()
    session.refresh(job)
    app_mit_datum = Application(job_id=job.id, status="Beworben", applied_date="2026-07-05",
                                channel="E-Mail")
    session.add(app_mit_datum)
    session.add(JobLog(job_id=job.id, art="auto", eintrag="Status: Prüfen → Beworben",
                       created_at=dt.datetime(2026, 7, 20, 8, 0)))
    session.commit()
    session.refresh(app_mit_datum)

    assert bewerbungs_anker(session).get(app_mit_datum.id) == dt.datetime(2026, 7, 5)
