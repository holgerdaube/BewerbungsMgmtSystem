"""Tests für P2-30 — Excel-Export (`pipeline/export_excel.py`): Blatt „Stellen" bekommt die
Spalten L „Beworben am" / M „CV-Version", plus das neue Blatt „Referenzen".

Vorbild `test_export_excel_funnel.py` (Aufbau, `EXPORT_DIR`-Monkeypatch auf `tmp_path`, echte
`build_workbook()` + openpyxl-Read-Beleg). Kein `app.*`/`pipeline.*`-Import auf Modulebene
(conftest.py-Konvention).

Diese Datei ist gegen die SPEC geschrieben (`tasks/spec_p2-30_export_stellen_referenzen.md`),
nicht gegen den Code, den zwei parallele Agenten zeitgleich an `export_excel.py` bauen — ein
roter Test entscheidet zugunsten der Spec.

Zwei Tests mit besonderem Gewicht:
- `test_ohne_bewerbungsdatum_bleibt_die_zelle_leer`: Ein „–" in einer Datumsspalte ist Text
  und zerstört die Sortierung nach Prozesslaufzeit — genau dafür gibt es die Spalte.
- `test_cv_version_dropdown_erlaubt_freien_text`: `showErrorMessage=False` ist das „weich" aus
  dem Auftrag. Ein hartes Dropdown wäre eine andere Funktion als die bestellte.
"""
import datetime
import uuid

import pytest


def _firma(session, suffix):
    from app.models import Company
    c = Company(name=f"P2-30 Test AG {suffix}")
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def _job(session, suffix, **kw):
    from app.models import Job
    j = Job(company_name=kw.pop("company_name", f"P2-30 Test AG {suffix}"),
            title=kw.pop("title", "Director Professional Services"),
            status=kw.pop("status", "Beworben"),
            found_date=kw.pop("found_date", datetime.date.today().isoformat()),
            dedup_key=f"p230|{suffix}|{uuid.uuid4().hex[:8]}",
            url=f"https://example.invalid/{uuid.uuid4().hex[:6]}",
            match_score=kw.pop("match_score", 4), **kw)
    session.add(j)
    session.commit()
    session.refresh(j)
    return j


def _joblog_beworben(session, job, wann):
    """Setzt den Bewerbungs-Zeitpunkt über den JobLog-Anker, den `beworben_am_je_job()` liest
    (Marke `BEWORBEN_MARKE = "→ Beworben"`, s. pipeline/gmail_ingest.py) — dieselbe Quelle,
    über die 98 der 125 bekannten Bewerbungsdaten laufen (Spec §0), NICHT über
    `application.applied_date` (nur 23 von 148)."""
    from app.models import JobLog
    log = JobLog(job_id=job.id, eintrag="Status: Neu → Beworben", created_at=wann)
    session.add(log)
    session.commit()
    return log


def _workbook(tmp_path, monkeypatch):
    from pipeline import export_excel
    monkeypatch.setattr(export_excel, "EXPORT_DIR", tmp_path)
    pfad = export_excel.build_workbook()
    import openpyxl
    return openpyxl.load_workbook(pfad), export_excel


def test_stellen_blatt_hat_beworben_am_und_cv_version(session, seed, tmp_path, monkeypatch):
    wb, export_excel = _workbook(tmp_path, monkeypatch)
    ws = wb["Stellen"]
    headers = list(export_excel.JOB_HEADERS)
    assert headers[-2] == "Beworben am"
    assert headers[-1] == "CV-Version"
    idx_beworben = headers.index("Beworben am") + 1
    idx_cv = headers.index("CV-Version") + 1
    assert ws.cell(row=1, column=idx_beworben).value == "Beworben am"
    assert ws.cell(row=1, column=idx_cv).value == "CV-Version"


def test_beworben_am_ist_ein_echtes_datum(session, seed, tmp_path, monkeypatch):
    """Spec §1.1: echtes Datum (`datetime.date`), Zahlenformat DD.MM.YYYY — der Nutzer muss danach
    sortieren/filtern können, kein String."""
    suffix = uuid.uuid4().hex[:8]
    job = _job(session, suffix, status="Beworben")
    wann = datetime.datetime(2026, 8, 12, 9, 30)
    _joblog_beworben(session, job, wann)

    wb, export_excel = _workbook(tmp_path, monkeypatch)
    ws = wb["Stellen"]
    idx_beworben = export_excel.JOB_HEADERS.index("Beworben am") + 1

    gefunden = None
    for row in ws.iter_rows(min_row=2):
        if row[0].value == job.company_name:
            gefunden = row[idx_beworben - 1]
            break
    assert gefunden is not None, "Job-Zeile nicht im Stellen-Blatt gefunden"
    assert isinstance(gefunden.value, (datetime.date, datetime.datetime)), (
        f"Beworben-am-Zelle ist {type(gefunden.value)}, erwartet date/datetime (kein String)")
    assert not isinstance(gefunden.value, str)
    assert gefunden.number_format.upper().replace("YYYY", "YYYY") in (
        "DD.MM.YYYY", "TT.MM.JJJJ") or "DD" in gefunden.number_format.upper()


def test_ohne_bewerbungsdatum_bleibt_die_zelle_leer(session, seed, tmp_path, monkeypatch):
    """Kein Bewerbungsdatum bekannt → Zelle bleibt LEER (None), kein „–". Ein Textwert in einer
    Datumsspalte sortiert falsch (Strings vs. Daten) und zerstört genau das, wofür die
    Spalte gedacht ist: sehen, wie lange ein Prozess wirklich läuft."""
    suffix = uuid.uuid4().hex[:8]
    job = _job(session, suffix, status="Neu")  # kein JobLog-Anker, kein applied_date

    wb, export_excel = _workbook(tmp_path, monkeypatch)
    ws = wb["Stellen"]
    idx_beworben = export_excel.JOB_HEADERS.index("Beworben am") + 1

    gefunden = None
    for row in ws.iter_rows(min_row=2):
        if row[0].value == job.company_name:
            gefunden = row[idx_beworben - 1]
            break
    assert gefunden is not None, "Job-Zeile nicht im Stellen-Blatt gefunden"
    assert gefunden.value is None
    assert gefunden.value != "–"


def test_cv_version_wird_aus_der_fertigen_cvversion_vorbefuellt(session, seed, tmp_path, monkeypatch):
    """Jüngste CVVersion mit status='fertig' → 'Tailored (DE)'/'Tailored (EN)', Sprache
    case-egal (Bestand mischt de/DE/en/EN, Spec §1.1)."""
    from app.models import CVVersion

    suffix = uuid.uuid4().hex[:8]
    job = _job(session, suffix, status="Beworben")
    session.add(CVVersion(job_id=job.id, language="DE", kind="tailored", status="fertig"))
    session.commit()

    wb, export_excel = _workbook(tmp_path, monkeypatch)
    ws = wb["Stellen"]
    idx_cv = export_excel.JOB_HEADERS.index("CV-Version") + 1

    gefunden = None
    for row in ws.iter_rows(min_row=2):
        if row[0].value == job.company_name:
            gefunden = row[idx_cv - 1]
            break
    assert gefunden is not None
    assert gefunden.value == "Tailored (DE)"


def test_cv_version_dropdown_erlaubt_freien_text(session, seed, tmp_path, monkeypatch):
    """`showErrorMessage=False` ist das „weich" aus dem Auftrag: die Liste ist ein
    Vorschlag, freies Tippen bleibt erlaubt. Ein hartes Dropdown (showErrorMessage=True) wäre
    eine andere, nicht bestellte Funktion."""
    wb, export_excel = _workbook(tmp_path, monkeypatch)
    ws = wb["Stellen"]

    assert len(ws.data_validations.dataValidation) >= 1
    idx_cv = export_excel.JOB_HEADERS.index("CV-Version") + 1
    from openpyxl.utils import get_column_letter
    spalte = get_column_letter(idx_cv)

    treffer = [dv for dv in ws.data_validations.dataValidation
               if dv.type == "list" and any(spalte in teil for teil in dv.sqref.ranges.__str__().split())]
    # Fallback: manche openpyxl-Versionen geben sqref direkt als String-repräsentierbar zurück.
    if not treffer:
        treffer = [dv for dv in ws.data_validations.dataValidation
                   if dv.type == "list" and spalte in str(dv.sqref)]
    assert treffer, f"Keine DataValidation(list) über Spalte {spalte} (CV-Version) gefunden"
    for dv in treffer:
        assert dv.showErrorMessage is False


def test_farbband_der_statusgruppe_reicht_bis_spalte_m(session, seed, tmp_path, monkeypatch):
    """Die Status-Trennzeilen mergen über `len(JOB_HEADERS)` — mit L/M zieht sich das Band
    automatisch bis Spalte M mit (Spec §1.2)."""
    wb, export_excel = _workbook(tmp_path, monkeypatch)
    ws = wb["Stellen"]
    n = len(export_excel.JOB_HEADERS)
    assert n == 13  # A..M

    merged_voll = [rng for rng in ws.merged_cells.ranges
                   if rng.min_col == 1 and rng.max_col == n]
    assert merged_voll, f"Keine Trennzeile gefunden, die bis Spalte {n} (M) mergt"


def test_referenzen_blatt_existiert_mit_kopfzeile(session, seed, tmp_path, monkeypatch):
    wb, _ = _workbook(tmp_path, monkeypatch)
    assert "Referenzen" in wb.sheetnames
    ws = wb["Referenzen"]
    erwartete_header = ["Name", "Rolle / Position", "Firma", "Zeitraum gemeinsam", "Kategorie",
                        "Kontakt", "Zugesagt", "Zuletzt kontaktiert", "Notiz"]
    header_zeile = [ws.cell(row=1, column=c).value for c in range(1, len(erwartete_header) + 1)]
    assert header_zeile == erwartete_header
    # nur Kopfzeile, sonst leer (Spec: "aktuell leer")
    assert ws.max_row == 1 or all(
        all(ws.cell(row=r, column=c).value in (None, "") for c in range(1, len(erwartete_header) + 1))
        for r in range(2, ws.max_row + 1))


def test_referenzen_dropdowns_sind_weich(session, seed, tmp_path, monkeypatch):
    """Kategorie- und Zugesagt-Dropdown auf Zeile 2-200, beide `showErrorMessage=False` —
    dieselbe Haltung wie bei CV-Version: Vorschlag, kein Zwang (Spec §1.3)."""
    wb, _ = _workbook(tmp_path, monkeypatch)
    ws = wb["Referenzen"]
    dvs = ws.data_validations.dataValidation
    listen_dvs = [dv for dv in dvs if dv.type == "list"]
    assert len(listen_dvs) >= 2, "Erwarte mindestens zwei Dropdown-Validierungen (Kategorie, Zugesagt)"
    for dv in listen_dvs:
        assert dv.showErrorMessage is False
        sqref_text = str(dv.sqref)
        assert "2" in sqref_text and "200" in sqref_text, (
            f"Dropdown-Bereich {sqref_text!r} deckt nicht Zeile 2-200 ab")

    formeln = [dv.formula1 for dv in listen_dvs]
    kategorie_formel = next((f for f in formeln if "Ehemaliger Chef" in (f or "")), None)
    zugesagt_formel = next((f for f in formeln if "Ausstehend" in (f or "")), None)
    assert kategorie_formel is not None, "Kategorie-Dropdown fehlt oder Werte weichen ab"
    for wert in ("Ehemaliger Chef", "Peer", "Direct Report", "Kunde", "Sonstige"):
        assert wert in kategorie_formel
    assert zugesagt_formel is not None, "Zugesagt-Dropdown fehlt oder Werte weichen ab"
    for wert in ("Ja", "Nein", "Ausstehend"):
        assert wert in zugesagt_formel


def test_blattreihenfolge(session, seed, tmp_path, monkeypatch):
    """Referenzen liegt nach 'Aussortiert', vor 'Kontakte' — thematisch bei den
    Bewerbungsunterlagen, nicht bei den Netzwerklisten (Spec §1.3)."""
    wb, _ = _workbook(tmp_path, monkeypatch)
    namen = wb.sheetnames
    assert "Aussortiert" in namen and "Referenzen" in namen and "Kontakte" in namen
    i_aussortiert = namen.index("Aussortiert")
    i_referenzen = namen.index("Referenzen")
    i_kontakte = namen.index("Kontakte")
    assert i_aussortiert < i_referenzen < i_kontakte
