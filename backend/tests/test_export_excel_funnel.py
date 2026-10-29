"""Tests für Phase 70, Stufe A — Blatt „Funnel" im Excel-Export (`pipeline/export_excel.py`).

Wie in conftest.py vorgesehen: KEINE app.*-Importe auf Modulebene. Muster
`test_response_rate_dedup.py` (Ebene 3): `EXPORT_DIR` wird auf `tmp_path` gepatcht (NIE in
echte outputs/exports schreiben, T1), danach `build_workbook()` end-to-end + openpyxl-Read-
Beleg. Der Zahlen-Identitäts-Beweis (Excel == `funnel_kpi()`) läuft gegen dieselbe DB-Session
wie `build_workbook()` selbst liest — EINE Berechnung, kein separat nachgerechneter Erwartungswert."""


def test_funnel_blatt_liegt_an_position_2(session, seed, tmp_path, monkeypatch):
    from pipeline import export_excel

    monkeypatch.setattr(export_excel, "EXPORT_DIR", tmp_path)
    pfad = export_excel.build_workbook()

    import openpyxl
    wb = openpyxl.load_workbook(pfad)

    assert wb.sheetnames[0] == "Dashboard"
    assert wb.sheetnames[1] == "Funnel"


def test_funnel_blatt_tabelle_stimmt_mit_funnel_kpi_ueberein(session, seed, tmp_path, monkeypatch):
    """Zahlen-Identitäts-Beleg: die Tabellenzahlen im Blatt „Funnel" sind exakt die Werte, die
    `app.gesamtprozess.funnel_kpi()` auf DERSELBEN Datengrundlage liefert (identisch zu dem, was
    `/api/dashboard` unter gesamtprozess.funnel zurückgäbe — EINE Berechnung, s. Moduldocstring)."""
    import openpyxl
    from sqlmodel import select
    from app.gesamtprozess import funnel_kpi
    from app.models import Application, Email, Interview, Job, NetzwerkGespraech, Outreach
    from pipeline import export_excel

    monkeypatch.setattr(export_excel, "EXPORT_DIR", tmp_path)
    pfad = export_excel.build_workbook()
    wb = openpyxl.load_workbook(pfad)
    ws = wb["Funnel"]

    # Erwartungswert: dieselbe Funktion, dieselbe (isolierte Test-)DB, frisch gelesen.
    jobs = session.exec(select(Job).where(Job.deleted_at.is_(None))).all()
    apps = session.exec(select(Application)).all()
    emails = session.exec(select(Email)).all()
    outreach = session.exec(select(Outreach)).all()
    interviews = session.exec(select(Interview)).all()
    ng = session.exec(select(NetzwerkGespraech)).all()
    erwartet = funnel_kpi(jobs, apps, emails, outreach, interviews, ng)

    assert ws["A3"].value == "Stufe"
    assert ws["B3"].value == "Anzahl"

    def _de_pct(p):
        if p is None:
            return "—"
        return f"{p:.1f}".replace(".", ",") + "%"

    for i, stufe in enumerate(erwartet["stufen"]):
        r = 4 + i
        assert ws.cell(row=r, column=1).value == f"{i + 1} · {stufe['stufe']}"
        assert ws.cell(row=r, column=2).value == stufe["anzahl"]
        assert ws.cell(row=r, column=3).value == _de_pct(stufe["vs_vorstufe"])
        assert ws.cell(row=r, column=4).value == _de_pct(stufe["vs_start"])
        assert ws.cell(row=r, column=5).value == stufe["kommentar"]


def test_funnel_blatt_groesster_verlust_zeile_ist_rot_und_fett(session, seed, tmp_path, monkeypatch):
    import openpyxl
    from sqlmodel import select
    from app.gesamtprozess import funnel_kpi
    from app.models import Application, Email, Interview, Job, NetzwerkGespraech, Outreach
    from pipeline import export_excel

    monkeypatch.setattr(export_excel, "EXPORT_DIR", tmp_path)
    pfad = export_excel.build_workbook()
    wb = openpyxl.load_workbook(pfad)
    ws = wb["Funnel"]

    jobs = session.exec(select(Job).where(Job.deleted_at.is_(None))).all()
    apps = session.exec(select(Application)).all()
    emails = session.exec(select(Email)).all()
    outreach = session.exec(select(Outreach)).all()
    interviews = session.exec(select(Interview)).all()
    ng = session.exec(select(NetzwerkGespraech)).all()
    erwartet = funnel_kpi(jobs, apps, emails, outreach, interviews, ng)
    gv_text = erwartet["engstellen"]["groesster_verlust"]["text"]

    # Der Text taucht irgendwo in den Engstellen-Zeilen (18-21) auf, rot (E5484D) + fett.
    gefunden = False
    for r in range(18, 22):
        cell = ws.cell(row=r, column=1)
        if cell.value == gv_text:
            gefunden = True
            assert cell.font.bold is True
            assert cell.font.color.rgb.endswith("E5484D")
    assert gefunden, f"Groesster-Verlust-Text {gv_text!r} nicht im Engstellen-Block gefunden"


def test_funnel_blatt_trichter_zeilen_haben_die_farbleiter():
    """Reiner Konstanten-Beleg (keine DB nötig): die fünf Trichter-Farben sind EXAKT die
    vorhandenen App-Token (STATUS_FARBEN/NAVY) — keine neuen Hex-Werte, s. Spec-Fallstrick."""
    from pipeline.export_excel import FUNNEL_FARBEN, NAVY, STATUS_FARBEN

    assert FUNNEL_FARBEN[0] == (NAVY, "FFFFFF")
    assert FUNNEL_FARBEN[1] == STATUS_FARBEN["Prüfen"]
    assert FUNNEL_FARBEN[2] == STATUS_FARBEN["Beworben"]
    assert FUNNEL_FARBEN[3] == STATUS_FARBEN["Geparkt"]
    assert FUNNEL_FARBEN[4] == STATUS_FARBEN["Angebot"]


def test_dashboard_blatt_hat_kompakt_trichter(session, seed, tmp_path, monkeypatch):
    """Phase-70-Nachtrag (29.07.): der Trichter steht AUCH kompakt auf dem
    Dashboard-Blatt (Spalten L..AO neben dem unteren Spaltenblock) — Titel, 5 Balkenzeilen
    mit den Stufen-Anzahlen, Größter-Verlust-Satz in Rot.

    Fixture-Fix (Phase 81, 10.08.2026): Dieser Test lief ohne `session`/`seed` und ohne
    EXPORT_DIR-Patch — er hing damit unbemerkt an der DB-Initialisierung FRÜHERER Tests und
    kippte, sobald neue Testdateien die Verteilung verschoben („no such table: company" beim
    Solo-Lauf schon immer). Zusätzlich prüfte er MONOTONIE der Stufen — das ist eine
    Eigenschaft der DATEN, nicht des Layouts, und in der über alle Tests akkumulierenden
    Suite-DB nicht garantiert (z. B. Interviews ohne Antwort-Mails). Jetzt wie die
    Nachbartests: Zahlen-Identität gegen `funnel_kpi()` auf derselben Datengrundlage."""
    import openpyxl
    from sqlmodel import select
    from app.gesamtprozess import funnel_kpi
    from app.models import Application, Email, Interview, Job, NetzwerkGespraech, Outreach
    from pipeline import export_excel
    from pipeline.export_excel import build_workbook

    monkeypatch.setattr(export_excel, "EXPORT_DIR", tmp_path)
    wb = openpyxl.load_workbook(build_workbook())
    ws = wb["Dashboard"]
    # Titel in Zeile 16, Spalte L
    assert ws.cell(row=16, column=12).value == "Funnel — vom Sichten zum Interview"

    erwartet = funnel_kpi(
        session.exec(select(Job).where(Job.deleted_at.is_(None))).all(),
        session.exec(select(Application)).all(),
        session.exec(select(Email)).all(),
        session.exec(select(Outreach)).all(),
        session.exec(select(Interview)).all(),
        session.exec(select(NetzwerkGespraech)).all(),
    )
    # 5 Balkenzeilen (17-21): je genau EIN Anzahl-Wert irgendwo im Streifen L..AO,
    # und zwar EXAKT die funnel_kpi()-Stufenzahl (eine Berechnung, kein Nachrechnen)
    for i, stufe in enumerate(erwartet["stufen"]):
        r = 17 + i
        werte = [ws.cell(row=r, column=c).value for c in range(12, 42)
                 if isinstance(ws.cell(row=r, column=c).value, int)]
        assert len(werte) == 1, f"Zeile {r}: erwartete genau einen Balkenwert, fand {werte}"
        assert werte[0] == stufe["anzahl"], f"Zeile {r}: {werte[0]} != funnel_kpi {stufe['anzahl']}"
    # Größter-Verlust-Satz in Zeile 23, rot + fett
    gl = ws.cell(row=23, column=12)
    assert isinstance(gl.value, str) and gl.value.startswith("Größter Verlust:")
    assert gl.font.bold and gl.font.color.rgb.endswith("E5484D")


def test_export_laeuft_auch_ohne_stellen(tmp_path, monkeypatch):
    """Eine frische Installation (oder eine nach „Beispieldaten entfernen“, P2-59) hat keine Stellen:
    `funnel_kpi()` liefert dann `groesster_verlust = None`. Das Funnel-Blatt fing das schon ab, der
    kompakte Trichter auf dem Dashboard-Blatt nicht, und der ganze Export (Knopf „Excel-Export“,
    Schritt „Ansichten aktualisieren“ im Tageslauf) brach mit einem TypeError ab (Fund P2-62)."""
    import openpyxl
    from sqlmodel import SQLModel, create_engine

    from app import models  # noqa: F401  (alle Tabellen registrieren)
    from pipeline import export_excel

    leer = create_engine(f"sqlite:///{tmp_path / 'leer.sqlite'}")
    SQLModel.metadata.create_all(leer)
    monkeypatch.setattr(export_excel, "engine", leer)
    monkeypatch.setattr(export_excel, "EXPORT_DIR", tmp_path)
    try:
        pfad = export_excel.build_workbook()
    finally:
        leer.dispose()

    wb = openpyxl.load_workbook(pfad)
    assert wb.sheetnames[:2] == ["Dashboard", "Funnel"]
    wb.close()
