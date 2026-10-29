"""Tests für P2-81 — Excel-Export (`pipeline/export_excel.py`): Blatt „Bewerbungen" mit Fit,
Match-100, ATS, Gefunden am, Beworben am, den Gesprächsrunden 1–6 und dem Absagedatum.

Aufbau wie `test_export_excel_stellen.py`: `EXPORT_DIR` auf `tmp_path`, echte `build_workbook()`,
Beleg über openpyxl. Die Test-DB teilen sich alle Tests, deshalb sucht jeder Test nur seine eigenen
Zeilen (eindeutiger Firmenname). Kein `app.*`/`pipeline.*`-Import auf Modulebene (conftest.py).
"""
import datetime
import uuid
from types import SimpleNamespace


def _job(session, **kw):
    from app.models import Job
    suffix = uuid.uuid4().hex[:8]
    j = Job(company_name=kw.pop("company_name", f"P2-81 Test AG {suffix}"),
            title=kw.pop("title", "Director Professional Services"),
            status=kw.pop("status", "Beworben"),
            found_date=kw.pop("found_date", "2026-08-01"),
            dedup_key=f"p281|{suffix}",
            match_score=kw.pop("match_score", 4), **kw)
    session.add(j)
    session.commit()
    session.refresh(j)
    return j


def _add(session, *rows):
    for r in rows:
        session.add(r)
    session.commit()
    return rows[0] if len(rows) == 1 else rows


def _blatt(tmp_path, monkeypatch):
    from pipeline import export_excel
    monkeypatch.setattr(export_excel, "EXPORT_DIR", tmp_path)
    import openpyxl
    wb = openpyxl.load_workbook(export_excel.build_workbook())
    return wb, wb["Bewerbungen"], export_excel.BEWERBUNGEN_HEADERS


def _zeile(ws, headers, job):
    """Header -> Zelle der Zeile dieser Stelle, oder None, wenn die Stelle fehlt."""
    for row in ws.iter_rows(min_row=2):
        if row[0].value == job.company_name:
            return dict(zip(headers, row))
    return None


def test_blatt_steht_nach_stellen_mit_der_bestellten_kopfzeile(session, seed, tmp_path, monkeypatch):
    wb, ws, headers = _blatt(tmp_path, monkeypatch)
    namen = wb.sheetnames
    assert namen.index("Bewerbungen") == namen.index("Stellen") + 1
    erwartet = (["Firma", "Bezeichnung", "Fit", "Match-100", "ATS", "Gefunden am", "Beworben am"]
                + [f"Runde {n}" for n in range(1, 7)] + ["Absage am"])
    assert list(headers) == erwartet
    assert [ws.cell(row=1, column=c).value for c in range(1, len(erwartet) + 1)] == erwartet
    assert ws.auto_filter.ref and ws.auto_filter.ref.startswith("A1:N")


def test_welche_stellen_eine_zeile_bekommen(session, seed, tmp_path, monkeypatch):
    """Bewerbungsstatus, Bewerbungsdatum aus dem Verlauf oder eine echte Bewerbungszeile reichen.
    „Vorbereitet" (nur Anschreiben angelegt) und eine Stelle ohne Bewerbung zählen nicht."""
    from app.models import Application, JobLog

    beworben = _job(session, status="Beworben")
    absage_ohne_alles = _job(session, status="Absage")
    geparkt_nach_bewerbung = _job(session, status="Geparkt")
    _add(session, JobLog(job_id=geparkt_nach_bewerbung.id, eintrag="Status: Prüfen → Beworben",
                         created_at=datetime.datetime(2026, 9, 2, 8, 0)))
    offline_mit_bewerbung = _job(session, status="Nicht verfügbar")
    _add(session, Application(job_id=offline_mit_bewerbung.id, status="Beworben"))
    nur_vorbereitet = _job(session, status="Geparkt")
    _add(session, Application(job_id=nur_vorbereitet.id, status="Vorbereitet"))
    neu = _job(session, status="Neu")

    _, ws, headers = _blatt(tmp_path, monkeypatch)
    for job in (beworben, absage_ohne_alles, geparkt_nach_bewerbung, offline_mit_bewerbung):
        assert _zeile(ws, headers, job) is not None, f"{job.status} fehlt im Blatt"
    assert _zeile(ws, headers, nur_vorbereitet) is None
    assert _zeile(ws, headers, neu) is None


def test_kennzahlen_und_daten_der_zeile(session, seed, tmp_path, monkeypatch):
    """Fit aus der Stelle (farbig wie im Blatt „Stellen"), Match-100 und ATS aus der neuesten
    CV-Version, Gefunden am und Beworben am als echte Daten."""
    from app.models import Application, CVVersion

    job = _job(session, status="Beworben", match_score=5, found_date="2026-08-03")
    _add(session, CVVersion(job_id=job.id, language="DE", kind="tailored", ats_score=88,
                            match_score100=76),
         Application(job_id=job.id, status="Beworben", applied_date="2026-08-06"))

    _, ws, headers = _blatt(tmp_path, monkeypatch)
    from pipeline.export_excel import SCORE_FARBEN
    z = _zeile(ws, headers, job)
    assert z["Bezeichnung"].value == "Director Professional Services"
    assert z["Fit"].value == 5
    assert z["Fit"].fill.fgColor.rgb[-6:] == SCORE_FARBEN[5][0]
    assert z["Match-100"].value == 76
    assert z["ATS"].value == 88
    assert z["Gefunden am"].value.date() == datetime.date(2026, 8, 3)
    assert z["Beworben am"].value.date() == datetime.date(2026, 8, 6)
    for spalte in ("Gefunden am", "Beworben am", "Runde 1", "Absage am"):
        assert z[spalte].number_format == "DD.MM.YYYY"


def test_gespraechsrunden_mit_datum_ersatzdatum_und_luecken(session, seed, tmp_path, monkeypatch):
    """Runde 1 mit Termin, Runde 2 nur mit Transkript-Datum, Runde 3 abgesagt (zählt nicht),
    Runde 4 ohne jedes Datum (leer mit Kommentar), Runde 7 jenseits der sechs Spalten."""
    from app.models import Interview, Transcript

    job = _job(session, status="Interview")
    _add(session, Interview(job_id=job.id, runde=1, scheduled_at="2026-08-25T11:00", status="Absolviert"))
    r2 = _add(session, Interview(job_id=job.id, runde=2, status="Absolviert"))
    _add(session, Transcript(job_id=job.id, interview_id=r2.id, recorded_at="2026-09-01"),
         Interview(job_id=job.id, runde=3, scheduled_at="2026-09-10T09:00", status="Abgesagt"),
         Interview(job_id=job.id, runde=4, status="Geplant"),
         Interview(job_id=job.id, runde=7, scheduled_at="2026-10-01T09:00", status="Absolviert"))

    _, ws, headers = _blatt(tmp_path, monkeypatch)
    z = _zeile(ws, headers, job)
    assert z["Runde 1"].value.date() == datetime.date(2026, 8, 25)
    assert z["Runde 2"].value.date() == datetime.date(2026, 9, 1)
    assert z["Runde 3"].value is None and z["Runde 3"].comment is None
    assert z["Runde 4"].value is None
    assert z["Runde 4"].comment is not None and "Datum fehlt" in z["Runde 4"].comment.text
    assert z["Runde 5"].value is None and z["Runde 6"].value is None
    assert z["Runde 1"].comment is None


def test_absage_am_mail_vor_verlauf_und_nur_bei_status_absage(session, seed, tmp_path, monkeypatch):
    """Die Absage-Mail ist das Ereignis und schlägt den späteren Statuswechsel. Ohne Mail springt
    der Verlauf ein. Ohne Status „Absage" bleibt die Zelle leer, auch wenn eine Absage-Mail hängt.
    Erwartet wird der lokale Kalendertag (Zeitstempel sind naives UTC), deshalb über app.zeit."""
    from app import zeit
    from app.models import Email, JobLog

    mail_zeit = datetime.datetime(2026, 9, 3, 22, 30)      # in Deutschland schon der 4.
    mit_mail = _job(session, status="Absage")
    _add(session,
         Email(job_id=mit_mail.id, direction="incoming", category="Absage", received_at=mail_zeit),
         Email(job_id=mit_mail.id, direction="incoming", category="Absage",
               received_at=datetime.datetime(2026, 9, 8, 9, 0)),
         JobLog(job_id=mit_mail.id, eintrag="Status: Beworben → Absage",
                created_at=datetime.datetime(2026, 9, 20, 9, 0)))
    nur_verlauf = _job(session, status="Absage")
    _add(session, JobLog(job_id=nur_verlauf.id, eintrag="Status: Interview → Absage",
                         created_at=datetime.datetime(2026, 9, 15, 12, 0)))
    noch_offen = _job(session, status="Beworben")
    _add(session, Email(job_id=noch_offen.id, direction="incoming", category="Absage",
                        received_at=datetime.datetime(2026, 9, 5, 9, 0)))

    _, ws, headers = _blatt(tmp_path, monkeypatch)
    assert _zeile(ws, headers, mit_mail)["Absage am"].value.date() == zeit.lokales_datum(mail_zeit)
    assert _zeile(ws, headers, nur_verlauf)["Absage am"].value.date() == datetime.date(2026, 9, 15)
    assert _zeile(ws, headers, noch_offen)["Absage am"].value is None


def test_neueste_bewerbung_zuerst_ohne_datum_am_ende(session, seed, tmp_path, monkeypatch):
    from app.models import Application

    alt = _job(session, status="Absage")
    neu = _job(session, status="Beworben")
    ohne_datum = _job(session, status="Keine Rückmeldung")
    _add(session, Application(job_id=alt.id, status="Absage", applied_date="2026-07-01"),
         Application(job_id=neu.id, status="Beworben", applied_date="2026-10-01"))

    _, ws, headers = _blatt(tmp_path, monkeypatch)
    firmen = [ws.cell(row=r, column=1).value for r in range(2, ws.max_row + 1)]
    assert firmen.index(neu.company_name) < firmen.index(alt.company_name) < firmen.index(ohne_datum.company_name)
    # Alles ohne Bewerbungsdatum steht hinter allem mit Datum
    spalte = headers.index("Beworben am") + 1
    werte = [ws.cell(row=r, column=spalte).value for r in range(2, ws.max_row + 1)]
    erste_luecke = next((i for i, w in enumerate(werte) if w is None), len(werte))
    assert all(w is None for w in werte[erste_luecke:])


def test_gefunden_am_liest_auch_das_deutsche_format(session, seed, tmp_path, monkeypatch):
    """Ältere Stellen tragen das Funddatum als „01.07.2026" statt ISO; auch das wird ein Datum."""
    job = _job(session, status="Absage", found_date="01.07.2026")

    _, ws, headers = _blatt(tmp_path, monkeypatch)
    assert _zeile(ws, headers, job)["Gefunden am"].value.date() == datetime.date(2026, 7, 1)


def test_gespraechsrunden_frueheres_datum_je_runde():
    """Zwei Gespräche derselben Runde: das frühere Datum gilt, ein Gespräch ohne Datum verdrängt
    keins mit Datum."""
    from pipeline.export_excel import _gespraechsrunden

    def iv(id_, runde, wann, status="Absolviert"):
        return SimpleNamespace(id=id_, job_id=1, runde=runde, scheduled_at=wann, status=status)

    runden = _gespraechsrunden(
        [iv(1, 1, "2026-08-20T10:00"), iv(2, 1, "2026-08-18T10:00"), iv(3, 2, None),
         iv(4, 2, "2026-08-30T10:00"), iv(5, 3, "2026-09-05T10:00"), iv(6, 3, None)], [])
    assert runden[1] == {1: datetime.date(2026, 8, 18), 2: datetime.date(2026, 8, 30),
                         3: datetime.date(2026, 9, 5)}
