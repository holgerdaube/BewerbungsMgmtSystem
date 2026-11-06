"""Excel-Export „Bewerbungs-Stand" (Phase 53): Cockpit + Listen-Blätter aus der SQLite-DB.

Die Excel-Datei ist bewusst ein *View*, keine Quelle — bei jedem Export neu aus der DB gebaut.
Struktur nach dem Vorbild von Claudias Job-Search-Tracker: Dashboard-Cockpit vorne, dahinter
Stellen (pro Status gruppiert), Bewerbungen (P2-81), Aussortiert, Kontakte, Netzwerk, Headhunter,
Zielfirmen, Outreach. Farben = Dashboard-Farbmodell V2 aus frontend/src/components/ui.tsx (Style Guide
v5.0 §18) — Status- und Score-Farben identisch zur App.

P2-72 (Design aus einer Quelle): Die Markenfarben (Kopfzeile, Überschriften, Zelltext) kommen aus dem
geltenden Design (`pipeline/design.py`), bei jedem Export frisch gelesen, nie beim Import festgehalten. Die
Zustandsfarben (Status, Score, Trichter) stehen in `pipeline/zustandsfarben.py` und sind kein Design.
Mit der Vorgabe entsteht dieselbe Datei wie vorher.
"""
import datetime
import re
from collections import Counter
from pathlib import Path

import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from sqlmodel import Session, select

from app import zeit
from app.db import engine
from app.sprache import aktuell, datum, tx, uebersetzt


def _wert(wert):
    """Maschinenwert aus der Datenbank (Priorität, Kanal, Status) in der Sprache der Ausgabe; leer bleibt leer."""
    return uebersetzt(wert) if wert else wert

from pipeline import bewerbungssprache
from app.gesamtprozess import (
    absagen_kpi, bewerbungen_kpi, funnel_kpi, gespraeche_kpi, keine_reaktion_kpi,
)
from app.models import (
    Application, Company, Contact, CVVersion, Email, Headhunter, Interview, Job, JobFile,
    JobLog, NetworkContact, NetzwerkGespraech, Outreach, TargetCompany, Transcript,
)
from app.naming import dated_filename
from app.normalize import norm_plan
from app.response_metrics import response_kpis
from pipeline import design, zustandsfarben
from pipeline.zustandsfarben import ohne_raute

EXPORT_DIR = Path(__file__).resolve().parent.parent.parent / "outputs" / "exports"  # Phase 56D1 (vormals data/exports)

# P2-72: Die Zustandsfarben kommen aus `pipeline/zustandsfarben.py` (EINE Tabelle, gleich der in ui.tsx),
# hier in der Schreibweise ohne Raute, die openpyxl verlangt: (Fläche, Schrift) je Status bzw. Score.
STATUS_FARBEN = {status: (ohne_raute(flaeche), ohne_raute(schrift))
                 for status, (flaeche, schrift) in zustandsfarben.STATUS_FARBEN.items()}
# NUR Score 1 verträgt weiße Schrift (§18.8)
SCORE_FARBEN = {score: (ohne_raute(flaeche), ohne_raute(schrift))
                for score, (flaeche, schrift) in zustandsfarben.SCORE_FARBEN.items()}
# Spiegel von app.main.TERMINAL_STATUSES — bewusst nicht importiert, sonst zöge der
# CLI-Lauf (refresh_views.sh: python -m pipeline.export_excel) die ganze FastAPI-App.
# Phase 85: "Keine Rückmeldung" ergänzt (Ghosting-Endstatus).
TERMINAL_STATUSES = {"Absage", "Kein Match", "Nicht verfügbar", "Beirat abgelehnt", "Keine Rückmeldung"}
AUSSORTIERT = ["Kein Match", "Nicht verfügbar", "Beirat abgelehnt"]
# Heiß zuerst — leere Status werden beim Rendern übersprungen.
# Phase 85: "Keine Rückmeldung" steht hier (Blatt "Stellen") und NICHT in AUSSORTIERT — es ist
# das Ergebnis einer ERFOLGTEN Bewerbung, wie "Absage". Das Aussortiert-Blatt beantwortet dagegen
# "warum wurde die Stelle aussortiert?" (Spalte "Grund", s. _grund()) und sammelt Stellen, auf die
# nie beworben wurde; für einen Ghosting-Fall stünde dort sinnlos "Begründung offen", und die
# Zeile ginge zwischen den Kein-Match-Zeilen unter. Der Kanban (Pipeline.tsx) führt den Status
# bewusst ANDERS — dort ist er archiviert, weil das Board den Handlungsbedarf zeigt, nicht die
# Auswertung.
PIPELINE_ORDER = ["Angebot", "Interview", "Beworben", "Prüfen", "Neu", "Geparkt", "Absage",
                  "Keine Rückmeldung"]



def _marke() -> str:
    """Markenfarbe des GELTENDEN Designs, ohne Raute (P2-72). Bei jedem Aufruf frisch: `design.laden()` ist
    zwischengespeichert und merkt eine geänderte Design-Datei ohne Neustart."""
    return ohne_raute(design.laden().farben["marke"])


def _text() -> str:
    """Textfarbe des GELTENDEN Designs, ohne Raute (P2-72)."""
    return ohne_raute(design.laden().farben["text"])


def _header_fill():
    return PatternFill("solid", fgColor=_marke())      # Kopfzeile aller Blätter = Markenfläche


# Schrift auf der Kopfzeile: fest Weiß. Keine Rolle der Vorgabe trifft den Wert (`auf_marke` ist DCE4EE), und
# P2-72 ändert an der Vorgabe nichts Sichtbares. Bei sehr heller Markenfarbe eines anderen Designs ist die
# Kopfzeile damit schlecht lesbar (bekannte Grenze, gehört zu Schritt 3 des Partnermodells).
HEADER_FONT = Font(color="FFFFFF", bold=True, size=10)
# Nebentext und Beschriftungen: Slate-500 / Slate-400, Neutralgrau ohne Rolle (nicht `text_gedaempft`, das ist
# ein anderer Wert) und ohne Zustand, deshalb fest.
LABEL_FONT = Font(color="64748B", size=9)


def _kpi_font():
    return Font(color=_marke(), bold=True, size=18)    # große Kennzahl wie eine Überschrift


# Kleine Split-Beschriftung unter dem KPI-Wert (Phase 69, Stufe C) — Vorbild
# Dashboard.tsx::GesamtprozessSection ("text-slate-400"), gleicher Grauton.
SPLIT_FONT = Font(color="94A3B8", size=8)
LINK_FONT = Font(color="0563C1", underline="single")
THIN_BOTTOM = Border(bottom=Side(style="thin", color="D8E0EA"))

# „Fit" = Zielstellen-Fit 1–5 (Stelle gegen Zielprofil, gleiche Kurzform wie die Spalte in der
# App); „Match-100" = CV-Match-Score 0–100 (Dokument gegen Anzeige). Zwei verschiedene Maße —
# vor dem 13.08.2026 hießen beide „Match" und wurden regelmäßig verwechselt.
JOB_HEADERS = ["Firma", "Bezeichnung", "Fit", "Match-100", "ATS", "Beirat", "Quelle / Link",
               "Nächster Schritt", "Fällig am", "Plan", "Standort", "Beworben am", "CV-Version"]
JOB_WIDTHS = [24, 40, 7, 10, 6, 8, 14, 42, 11, 6, 20, 12, 16]
# CV-Version (P2-30): NUR die weiche Vorschlagsliste, KEINE Versionsnummer — die Basis-CVs
# wandern (v8 → v10 am 07.08.2026, s. Spec §0), eine Versionsnummer im Dropdown veraltet
# garantiert. „Master" ist ein Handeintrag, `CVVersion.kind` kennt in der DB nur „tailored".
CV_VERSION_OPTIONEN = '"Master DE,Master EN,Tailored (DE),Tailored (EN)"'
# Aussortiert (Phase 75): „Nächster Schritt"/„Fällig am" entfallen — beide sind dort wegen der
# Terminal-Regel (s. _job_zeile) strukturell IMMER leer. Stattdessen „Grund" (s. _grund()).
AUSSORTIERT_HEADERS = ["Status", "Firma", "Bezeichnung", "Fit", "Match-100", "ATS", "Beirat",
                       "Quelle / Link", "Grund", "Plan", "Standort"]
AUSSORTIERT_WIDTHS = [16, 24, 40, 7, 10, 6, 8, 14, 42, 6, 20]

# Blatt „Bewerbungen" (P2-81): eine Zeile je Stelle, auf die beworben wurde, mit dem Verlauf als
# Daten. Status, aus denen eine Bewerbung hervorgeht; „Absage" und „Keine Rückmeldung" sind Ausgänge
# einer erfolgten Bewerbung (s. PIPELINE_ORDER).
BEWERBUNGS_STATUS = {"Beworben", "Interview", "Angebot", "Absage", "Keine Rückmeldung"}
GESPRAECHSRUNDEN = 6     # Vorgabe; spätere Runden zeigt das Blatt nicht
BEWERBUNGEN_HEADERS = (["Firma", "Bezeichnung", "Fit", "Match-100", "ATS", "Gefunden am", "Beworben am"]
                       + [f"Runde {n}" for n in range(1, GESPRAECHSRUNDEN + 1)] + ["Absage am"])
BEWERBUNGEN_WIDTHS = [24, 40, 7, 10, 6, 13, 13] + [11] * GESPRAECHSRUNDEN + [11]
# Statuswechsel auf „Absage" im Verlauf — Schwester von gmail_ingest.BEWORBEN_MARKE
ABSAGE_MARKE = "→ Absage"

# Beirat-Zelle als Ampel-Zahl (Phase 75): parst das note-Format aus
# beirat_engine._jobfile_registrieren() — f"{emoji} {zahl_mit_komma} · {stimmen}/7 {label}",
# z. B. "🟡 6,1 · 0/7 Bedingt Bewerben". Format-Drift dort degradiert hier sanft zum
# bisherigen Rohtext ohne Färbung (kein Crash) — Quer-Verweis auch an der Quelle.
_BEIRAT_NOTE_RE = re.compile(r"^([🟢🟡🔴])\s*(\d+(?:,\d+)?)\s*·")
# Ampel → (bg, text) über die vorhandenen Score-Töne (KEINE neuen Hex-Werte, Spec-Regel
# Phase 53) — die Beirat-Ampel ist semantisch eine Score-Ampel neben der Match-Zelle.
BEIRAT_AMPEL_FARBEN = {"🟢": SCORE_FARBEN[5], "🟡": SCORE_FARBEN[3], "🔴": SCORE_FARBEN[1]}

# ── Blatt "Funnel" (Phase 70, Stufe A) ──────────────────────────────────────────────────────
# Farbleiter für den Trichter — DIESELBEN fünf App-Farben wie STATUS_FARBEN und die Startfarbe der
# Trichter-Grafik, nur in Trichter-Reihenfolge zusammengestellt (KEINE neuen Hex-Werte, s. Spec-Fallstrick
# „vorhandene App-Token"). (bg, text) je Stufe — Kontrastregel §18.8: Weiß nur auf Navy/Violett, sonst Navy.
# P2-72: Alle fünf sind Zustandsfarben (Bedeutung), keine Markenfarben; sie hängen an keiner Designrolle.
# Navy der ersten Trichterstufe. Das ist Bedeutung (Start der Grafik), NICHT die Markenfarbe: Der Name bleibt,
# weil ihn Tests und Leser kennen; die Markenfarbe der Kopfzeile und der Überschriften ist `_marke()`.
NAVY = ohne_raute(zustandsfarben.TRICHTER_START[0])
FUNNEL_FARBEN = [
    (NAVY, ohne_raute(zustandsfarben.TRICHTER_START[1])),            # Stufe 1 Gesichtet (Bedeutung: Start)
    STATUS_FARBEN["Prüfen"],                                         # Stufe 2 Relevant
    STATUS_FARBEN["Beworben"],                                       # Stufe 3 Beworben
    STATUS_FARBEN["Geparkt"],                                        # Stufe 4 Antworten
    STATUS_FARBEN["Angebot"],                                        # Stufe 5 Interviews
]
FUNNEL_ROT = STATUS_FARBEN["Absage"][0]      # für den „größter Verlust"-Satz und überfällige Aktionen
FUNNEL_TRICHTER_START_COL = 7    # Spalte G — eigener Bereich, unabhängig von der Tabelle A:E
FUNNEL_TRICHTER_SPAN = 30

# Je Nicht-Gewinner-Stufe (Stufe 2-5) der Satzbaustein fürs Engstellen-Panel — dieselbe Wortwahl
# wie das zugehörige `groesster_verlust.text` aus `gesamtprozess.funnel_kpi()` (dort NICHT
# importierbar, weil modulprivat — bewusst hier dupliziert statt ins Frontend-lastige Rückgabe-
# Format gezwängt, s. Spec: nur `groesster_verlust.text` ist Teil des Vertrags, die anderen vier
# Zeilen formatiert jeder Konsument [Excel hier, Dashboard in Stufe B] selbst — dieselbe
# Arbeitsteilung wie bei den rohen vs_vorstufe/vs_start-Prozenten).
def _engstellen_zeilen():
    """(Stufe, Position in `stufen`, Schlüssel in `engstellen`, Satzbaustein) je Stufe 2 bis 5, mit den Texten der
    Sprache, die beim Export gilt. Die Position (nicht der Stufenname) verbindet die Zeile mit `funnel["stufen"]`,
    denn der Name kommt von `gesamtprozess` und kann in der Sprache des Servers stehen."""
    def antwortquote(p, basis):
        # Deutsch schreibt auch „1 Bewerbungen“ und bleibt so; der zweite Schlüssel (anderer Platzhalter, gleicher
        # deutscher Text) lässt Englisch den Singular richtig schreiben.
        if basis == 1:
            return tx("Antwortquote {p} auf {eine} Bewerbungen", p=p, eine=basis)
        return tx("Antwortquote {p} auf {basis} Bewerbungen", p=p, basis=basis)

    return [
        ("Relevant", 1, "screening",
         lambda p, basis: tx("Screening: nur {p} der gesichteten Stellen sind relevant", p=p)),
        ("Beworben", 2, "bewerbungsquote",
         lambda p, basis: tx("Bewerbungsquote: {p} der relevanten Stellen wurden beworben", p=p)),
        ("Antworten", 3, "antwortquote", antwortquote),
        ("Interviews", 4, "interview_konversion",
         lambda p, basis: tx("Interview-Konversion: {p} der Antworten führten zum Interview", p=p)),
    ]


def _fill(hexcode):
    return PatternFill("solid", fgColor=hexcode)


def _de_pct_tabelle(p):
    """'38,3%' (KEIN Leerzeichen) — Tabellenzellen-Konvention, deutsches Komma wie überall im
    Export (Spec-Fallstrick); Englisch '38.3%'. None (Basis 0) -> Gedankenstrich."""
    if p is None:
        return "—"
    zahl = f"{p:.1f}"
    return (zahl.replace(".", ",") if aktuell() == "de" else zahl) + "%"


def _de_pct_prosa(p):
    """'38,3 %' (MIT Leerzeichen) — Fließtext-Konvention fürs Engstellen-Panel; Englisch '38.3%'."""
    if p is None:
        return "—"
    zahl = f"{p:.1f}"
    return zahl.replace(".", ",") + " %" if aktuell() == "de" else zahl + "%"


def _n_stellen(n):
    """„12 Stellen“; Deutsch schreibt auch „1 Stellen“ und bleibt so, Englisch bekommt den Singular über den zweiten
    Schlüssel (anderer Platzhalter, gleicher deutscher Text)."""
    return tx("{eine} Stellen", eine=n) if n == 1 else tx("{anzahl} Stellen", anzahl=n)


def _n_interviews(n):
    return tx("{eins} Interviews", eins=n) if n == 1 else tx("{anzahl} Interviews", anzahl=n)


def _funnel_sheet(wb, funnel):
    """Blatt „Funnel" an Position 2 (direkt nach „Dashboard") — Tabelle + Zell-Balken-Trichter +
    Engstellen-Panel, alles aus `funnel` (= `gesamtprozess.funnel_kpi()`-Rückgabe, EINE
    Berechnung identisch zu `/api/dashboard`, s. Moduldocstring-Prinzip „View, keine Quelle").
    """
    stufen = funnel["stufen"]
    engstellen = funnel["engstellen"]

    ws = wb.create_sheet(tx("Funnel"), 1)
    ws.sheet_view.showGridLines = False

    ws.merge_cells("A1:E1")
    ws["A1"] = tx("Funnel — von der Stellenansicht zum Interview")
    ws["A1"].font = Font(color=_marke(), bold=True, size=14)

    # ── Tabelle (Zeile 3 Kopf, Zeilen 4-8 die fünf Stufen) ─────────────────────────────────
    kopf_row = 3
    for i, h in enumerate([tx("Stufe"), tx("Anzahl"), tx("vs. Vorstufe"), tx("vs. Start"), tx("Kommentar")], start=1):
        c = ws.cell(row=kopf_row, column=i, value=h)
        c.fill = _header_fill()
        c.font = HEADER_FONT
        c.alignment = Alignment(vertical="center")

    for i, stufe in enumerate(stufen):
        r = kopf_row + 1 + i
        ws.cell(row=r, column=1, value=f"{i + 1} · {uebersetzt(stufe['stufe'])}").font = Font(color=_text(), size=10)
        anzahl_cell = ws.cell(row=r, column=2, value=stufe["anzahl"])
        anzahl_cell.font = Font(color=_text(), bold=True, size=11)
        ws.cell(row=r, column=3, value=_de_pct_tabelle(stufe["vs_vorstufe"])).font = Font(color=_text(), size=10)
        ws.cell(row=r, column=4, value=_de_pct_tabelle(stufe["vs_start"])).font = Font(color=_text(), size=10)
        kommentar_cell = ws.cell(row=r, column=5, value=stufe["kommentar"])
        kommentar_cell.font = Font(color=_text(), size=10)
        kommentar_cell.alignment = Alignment(wrap_text=True, vertical="top")

    _set_widths(ws, [22, 8, 12, 10, 56])

    # ── Trichter-Grafik als Zell-Balken (Zeilen 11-15) — bewusst KEIN openpyxl-BarChart, dessen
    # per-Punkt-Farben sind fragil (Spec-Vorgabe). Eigener Spaltenbereich G..AJ (30 schmale
    # Spalten), unabhängig von der Tabellenbreite A:E oben. ─────────────────────────────────
    ws.cell(row=10, column=1, value=tx("Trichter")).font = Font(color=_marke(), bold=True, size=12)
    for c in range(FUNNEL_TRICHTER_START_COL, FUNNEL_TRICHTER_START_COL + FUNNEL_TRICHTER_SPAN):
        ws.column_dimensions[get_column_letter(c)].width = 1.2

    stufe1_anzahl = stufen[0]["anzahl"]
    trichter_row0 = 11
    for i, stufe in enumerate(stufen):
        if stufe1_anzahl:
            breite = max(1, min(FUNNEL_TRICHTER_SPAN, round(stufe["anzahl"] / stufe1_anzahl * 30)))
        else:
            breite = 1
        offset = (FUNNEL_TRICHTER_SPAN - breite) // 2
        start_col = FUNNEL_TRICHTER_START_COL + offset
        end_col = start_col + breite - 1
        r = trichter_row0 + i

        ws.merge_cells(start_row=r, start_column=start_col, end_row=r, end_column=end_col)
        bg, txt = FUNNEL_FARBEN[i]
        for c in range(start_col, end_col + 1):
            ws.cell(row=r, column=c).fill = _fill(bg)
        mitte_cell = ws.cell(row=r, column=start_col, value=stufe["anzahl"])
        mitte_cell.font = Font(color=txt, bold=True, size=11)
        mitte_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[r].height = 18
        ws.cell(row=r, column=1, value=f"{i + 1} · {uebersetzt(stufe['stufe'])}").font = Font(color=_text(), size=9)

    # ── Engstellen im Funnel (ab Zeile 17) — 5 Zeilen, größter Verlust rot+fett, Ende-zu-Ende
    # gedämpft grau (Spec-Vorgabe). ─────────────────────────────────────────────────────────
    engstellen_kopf_row = trichter_row0 + len(stufen) + 1   # = 17
    ws.cell(row=engstellen_kopf_row, column=1, value=tx("Engstellen im Funnel")).font = Font(color=_marke(), bold=True, size=12)

    groesster_verlust = engstellen.get("groesster_verlust")
    gv_stufe = groesster_verlust["stufe"] if groesster_verlust else None

    r = engstellen_kopf_row + 1
    for stufe_name, idx, key, textfn in _engstellen_zeilen():
        p = engstellen[key]
        if stufen[idx]["stufe"] == gv_stufe:
            text = groesster_verlust["text"]
            font = Font(color=FUNNEL_ROT, bold=True, size=10)
        elif p is None:
            text = tx("{stufe}: keine Daten", stufe=uebersetzt(stufe_name))
            font = Font(color=_text(), size=10)
        else:
            basis = stufen[idx - 1]["anzahl"]
            text = textfn(_de_pct_prosa(p), basis)
            font = Font(color=_text(), size=10)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
        cell = ws.cell(row=r, column=1, value=text)
        cell.font = font
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        r += 1

    # Ende-zu-Ende — immer gedämpft grau, ist NIE `groesster_verlust`-Kandidat (Spec: nur
    # Stufe 2-5 vs_vorstufe kommen dafür infrage, Ende-zu-Ende ist vs_start der letzten Stufe).
    eze_text = tx("Ende-zu-Ende: {prozent} — {stellen} → {interviews}", prozent=_de_pct_prosa(engstellen['ende_zu_ende']),
                  stellen=_n_stellen(stufen[0]['anzahl']), interviews=_n_interviews(stufen[4]['anzahl']))
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    eze_cell = ws.cell(row=r, column=1, value=eze_text)
    eze_cell.font = Font(color="94A3B8", italic=True, size=10)
    eze_cell.alignment = Alignment(wrap_text=True, vertical="center")

    return ws


def _style_header(ws, ncols, autofilter=True):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = _header_fill()
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center")
    ws.freeze_panes = "A2"
    if autofilter:
        ws.auto_filter.ref = f"A1:{get_column_letter(ncols)}{ws.max_row}"


def _datumsformat() -> str:
    """Datumsformat der Zellen: Deutsch TT.MM.JJJJ, Englisch TT/MM/JJJJ (wie `sprache.datum`)."""
    return "DD.MM.YYYY" if aktuell() == "de" else "DD/MM/YYYY"


def _set_widths(ws, widths):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _breite_fuer_kopf(ws):
    """Englische Spaltenköpfe sind oft länger als die deutschen; ihre Spalte wird so breit, dass der Kopf passt.
    Deutsch bleibt unberührt (die festen Breiten oben sind darauf abgestimmt)."""
    if aktuell() == "de":
        return
    for c in range(1, ws.max_column + 1):
        kopf = ws.cell(row=1, column=c).value
        if kopf is None:
            continue
        buchstabe = get_column_letter(c)
        noetig = len(str(kopf)) + 3
        if (ws.column_dimensions[buchstabe].width or 0) < noetig:
            ws.column_dimensions[buchstabe].width = noetig


def _grund(j, grund_manuell):
    """Warum wurde die Stelle aussortiert (Phase 75)? Kaskade: (1) manuelle Einträge
    aus „Notizen & Verlauf" (joblog art='manuell'), chronologisch mit „ · " verbunden — mehrere
    ergänzen sich (Echtfall: „…kein Match" + „Zusätzlich: Not accepting applications");
    (2) sonst die Bewertungsbegründung `match_rationale`, auf ~200 Zeichen gekürzt;
    (3) sonst das Literal „Begründung offen" (Vorgabe vom 06.08.)."""
    eintraege = grund_manuell.get(j.id)
    if eintraege:
        return " · ".join(eintraege)
    if j.match_rationale and j.match_rationale.strip():
        r = j.match_rationale.strip()
        return r if len(r) <= 200 else r[:200].rstrip() + "…"
    return tx("Begründung offen")


def _fit_faerben(cell, score):
    """Fit-Zelle in der Score-Farbe wie in der App; ohne Score bleibt sie ungefärbt."""
    if score in SCORE_FARBEN:
        bg, txt = SCORE_FARBEN[score]
        cell.fill = _fill(bg)
        cell.font = Font(color=txt, bold=True)
        cell.alignment = Alignment(horizontal="center")


def _job_zeile(ws, j, ats, beirat, match100, grund_manuell, status=None,
               beworben_am=None, cv_version=None):
    """Eine Stellen-Zeile (Blatt 2/3). Bei terminalem Status werden next_step/follow_up_date
    nur im EXPORT geleert (Entscheidung 3, 23.07.) — die DB bleibt unangetastet. Das gilt nur
    noch fürs Stellen-Blatt (dort steht „Absage" als terminale Gruppe); das Aussortiert-Blatt
    (status gesetzt) führt die beiden Spalten seit Phase 75 gar nicht mehr, sondern „Grund".

    `beworben_am`/`cv_version` (P2-30) nur auf dem Stellen-Blatt befüllt (Aussortiert-Blatt hat
    weder Bewerbungsdatum noch CV — dort wurde ja nie beworben) — Aufrufer lässt sie dort weg."""
    beirat_note = beirat.get(j.id)
    kopf = [
        j.company_name, j.title, j.match_score, match100.get(j.id), ats.get(j.id), beirat_note,
        uebersetzt(j.portal) if j.portal else ("Link" if j.url else None),
    ]
    offset = 0
    if status is not None:  # Aussortiert-Blatt: Status vorne, „Grund" statt Schritt/Fällig
        werte = [uebersetzt(status)] + kopf + [_grund(j, grund_manuell), norm_plan(j.plan_ab), j.location]
        offset = 1
    else:
        terminal = j.status in TERMINAL_STATUSES
        werte = kopf + [
            None if terminal else j.next_step, None if terminal else j.follow_up_date,
            norm_plan(j.plan_ab), j.location, beworben_am, cv_version,
        ]
    ws.append(werte)
    r = ws.max_row
    if status is not None:
        bg, txt = STATUS_FARBEN[status]
        sc = ws.cell(row=r, column=1)
        sc.value = uebersetzt(status)
        sc.fill = _fill(bg)
        sc.font = Font(color=txt, size=9)
    else:
        for c in range(1, len(JOB_HEADERS) + 1):
            ws.cell(row=r, column=c).border = THIN_BOTTOM
    _fit_faerben(ws.cell(row=r, column=offset + 3), j.match_score)
    ws.cell(row=r, column=offset + 4).alignment = Alignment(horizontal="center")  # Match-100
    # Beirat: Ampel-Zahl (Phase 75) — bei parsebarem note echte Zahl + Ampelfarbe (Muster der
    # Match-Zelle), sonst Rohtext wie vor Phase 75.
    m = _BEIRAT_NOTE_RE.match(beirat_note) if beirat_note else None
    if m:
        bg, txt = BEIRAT_AMPEL_FARBEN[m.group(1)]
        cell = ws.cell(row=r, column=offset + 6)
        cell.value = float(m.group(2).replace(",", "."))
        cell.number_format = "0.0"
        cell.fill = _fill(bg)
        cell.font = Font(color=txt, bold=True)
        cell.alignment = Alignment(horizontal="center")
    if j.url:
        link = ws.cell(row=r, column=offset + 7)
        link.hyperlink = j.url
        link.font = LINK_FONT
    ws.cell(row=r, column=offset + 2).alignment = Alignment(wrap_text=True, vertical="top")
    ws.cell(row=r, column=offset + 8).alignment = Alignment(wrap_text=True, vertical="top")
    if status is None:
        # Echtes Datum, kein String (P2-30) — der Nutzer will danach sortieren/filtern können; ein
        # Textwert wie „–“ würde in dieser Spalte die Sortierung zerstören, s. Spec §1.1. Format
        # gilt auch bei leerer Zelle (kein Bewerbungsdatum bekannt) — schadet dort nicht.
        ws.cell(row=r, column=offset + 12).number_format = _datumsformat()


def _datum_aus_text(wert):
    """Kalendertag aus einem Datumstext, sonst None: ISO („2026-07-16", „2026-07-16T10:00") oder
    deutsch („16.07.2026", so steht das Funddatum älterer Stellen in der DB). Solche Felder sind
    lokale Angaben, keine UTC-Zeitstempel (s. app/zeit.py)."""
    text = (wert or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def _gespraechsrunden(interviews, transcripts) -> dict:
    """`job_id` -> {runde: Datum oder None}; None heißt: Gespräch erfasst, aber ohne Datum (P2-81).

    Das Datum kommt aus `scheduled_at`, fehlt es, aus dem frühesten Transkript des Gesprächs
    (`recorded_at`). Abgesagte Gespräche haben nicht stattgefunden und zählen nicht. Haben zwei
    Gespräche dieselbe Runde, gilt das frühere Datum."""
    mitschrift = {}
    for t in transcripts:
        d = _datum_aus_text(t.recorded_at)
        if t.interview_id and d and (t.interview_id not in mitschrift or d < mitschrift[t.interview_id]):
            mitschrift[t.interview_id] = d
    runden: dict = {}
    for i in interviews:
        if (i.status or "") == "Abgesagt" or not 1 <= (i.runde or 0) <= GESPRAECHSRUNDEN:
            continue
        d = _datum_aus_text(i.scheduled_at) or mitschrift.get(i.id)
        je_job = runden.setdefault(i.job_id, {})
        bisher = je_job.get(i.runde)
        if i.runde not in je_job or (d and (bisher is None or d < bisher)):
            je_job[i.runde] = d
    return runden


def _absage_am(jobs, emails, absage_logs) -> dict:
    """`job_id` -> Kalendertag der Absage, nur für Stellen mit Status „Absage" (P2-81).

    Erste Quelle ist die früheste eingehende Absage-Mail an der Stelle: Sie ist das Ereignis. Der
    Statuswechsel im Verlauf liegt am selben Tag oder später (Bestand Oktober 2026: bis 44 Tage) und
    springt nur ein, wenn keine Absage-Mail an der Stelle hängt, etwa nach einer Absage am Telefon.
    Beide Zeitpunkte sind naives UTC und werden auf den lokalen Kalendertag umgerechnet."""
    abgesagt = {j.id for j in jobs if j.status == "Absage"}
    aus_mail, aus_log = {}, {}
    for e in emails:
        if (e.job_id in abgesagt and e.category == "Absage" and e.direction == "incoming"
                and e.received_at and (e.job_id not in aus_mail or e.received_at < aus_mail[e.job_id])):
            aus_mail[e.job_id] = e.received_at
    for l in absage_logs:
        if l.job_id in abgesagt and l.created_at and (l.job_id not in aus_log or l.created_at < aus_log[l.job_id]):
            aus_log[l.job_id] = l.created_at
    return {jid: zeit.lokales_datum(dt) for jid, dt in {**aus_log, **aus_mail}.items()}


def _bewerbungen_sheet(wb, jobs, apps, interviews, ats, match100, beworben_am, runden, absage_am):
    """Blatt „Bewerbungen" (P2-81): eine Zeile je Stelle mit Bewerbung, flach und filterbar.

    Dazu zählt eine Stelle mit Bewerbungsstatus, mit bekanntem Bewerbungsdatum, mit einer
    Bewerbungszeile außer „Vorbereitet" (dieselbe Regel wie die KPI „Bewerbungen gesamt") oder mit
    einem erfassten Gespräch. „Vorbereitet" heißt nur, dass ein Anschreiben angelegt wurde. Alle
    Datumsspalten tragen echte Daten oder bleiben leer, nie Text (P2-30, Sortierung)."""
    mit_bewerbung = (set(beworben_am) | {i.job_id for i in interviews}
                     | {a.job_id for a in apps if (a.status or "") != "Vorbereitet"})
    zeilen = [j for j in jobs if (j.status or "Neu") in BEWERBUNGS_STATUS or j.id in mit_bewerbung]
    # Neueste Bewerbung zuerst, ohne Datum ans Ende; bei gleichem Datum nach Firma (stabile Sortierung)
    zeilen.sort(key=lambda j: (j.company_name or "").lower())
    zeilen.sort(key=lambda j: beworben_am.get(j.id) or datetime.date.min, reverse=True)

    ws = wb.create_sheet(tx("Bewerbungen"))
    ws.append([uebersetzt(h) for h in BEWERBUNGEN_HEADERS])
    erste_datumsspalte = BEWERBUNGEN_HEADERS.index("Gefunden am") + 1
    erste_runde = BEWERBUNGEN_HEADERS.index("Runde 1") + 1
    datumsformat = _datumsformat()
    for j in zeilen:
        je_runde = runden.get(j.id, {})
        ws.append([j.company_name, j.title, j.match_score, match100.get(j.id), ats.get(j.id),
                   _datum_aus_text(j.found_date), beworben_am.get(j.id)]
                  + [je_runde.get(n) for n in range(1, GESPRAECHSRUNDEN + 1)]
                  + [absage_am.get(j.id)])
        r = ws.max_row
        _fit_faerben(ws.cell(row=r, column=3), j.match_score)
        ws.cell(row=r, column=4).alignment = Alignment(horizontal="center")  # Match-100
        ws.cell(row=r, column=2).alignment = Alignment(wrap_text=True, vertical="top")
        for c in range(erste_datumsspalte, len(BEWERBUNGEN_HEADERS) + 1):
            ws.cell(row=r, column=c).number_format = datumsformat
        # Gespräch ohne Datum: Zelle bleibt leer, der Kommentar zeigt, dass die Runde stattfand
        for n, d in je_runde.items():
            if d is None:
                ws.cell(row=r, column=erste_runde + n - 1).comment = Comment(
                    tx("Gespräch erfasst, Datum fehlt in der App"), "BMS")
    _set_widths(ws, BEWERBUNGEN_WIDTHS)
    _breite_fuer_kopf(ws)
    _style_header(ws, len(BEWERBUNGEN_HEADERS))
    return ws


# Kompakt-Trichter fürs Dashboard-Blatt (Phase-70-Nachtrag, 29.07.): eigener schmaler
# Spaltenstreifen RECHTS neben dem bestehenden A–J-Layout — kollidiert mit nichts, sitzt wie
# im Web-Dashboard oben neben den KPI-Reihen. Details/Engstellen bleiben auf dem Blatt „Funnel".
DASH_FUNNEL_START_COL = 12   # Spalte L
DASH_FUNNEL_SPAN = 30


def _dashboard_funnel_block(ws, funnel):
    """Zell-Balken-Trichter kompakt auf dem Dashboard-Blatt (Zeilen 3–8, Spalten L..AO) —
    dieselbe Technik und Farbleiter wie `_funnel_sheet`, plus Stufen-Label und Konversion
    rechts vom Streifen und der „größter Verlust"-Satz in Rot darunter."""
    for c in range(DASH_FUNNEL_START_COL, DASH_FUNNEL_START_COL + DASH_FUNNEL_SPAN):
        ws.column_dimensions[get_column_letter(c)].width = 1.2

    # Zeilenbereich 16–21: neben dem unteren Spaltenblock (r0=16 in build_workbook) — dort sind
    # alle Zeilenhöhen einheitlich (die KPI-Wertzeilen 5/8/12 oben sind 26 pt hoch, Balken in
    # diesem Bereich wären ungleich dick).
    ws.cell(row=16, column=DASH_FUNNEL_START_COL,
            value=tx("Funnel — vom Sichten zum Interview")).font = Font(color=_marke(), bold=True, size=12)

    stufen = funnel["stufen"]
    stufe1_anzahl = stufen[0]["anzahl"]
    for i, stufe in enumerate(stufen):
        r = 17 + i
        if stufe1_anzahl:
            breite = max(1, min(DASH_FUNNEL_SPAN, round(stufe["anzahl"] / stufe1_anzahl * DASH_FUNNEL_SPAN)))
        else:
            breite = 1
        start_col = DASH_FUNNEL_START_COL + (DASH_FUNNEL_SPAN - breite) // 2
        end_col = start_col + breite - 1
        ws.merge_cells(start_row=r, start_column=start_col, end_row=r, end_column=end_col)
        bg, txt = FUNNEL_FARBEN[i]
        for c in range(start_col, end_col + 1):
            ws.cell(row=r, column=c).fill = _fill(bg)
        mitte = ws.cell(row=r, column=start_col, value=stufe["anzahl"])
        mitte.font = Font(color=txt, bold=True, size=10)
        mitte.alignment = Alignment(horizontal="center", vertical="center")
        # Label + Konversion rechts vom Streifen (Stufe 1 zeigt 100 % statt „—")
        pct = _de_pct_prosa(stufe["vs_vorstufe"] if i else 100.0)
        ws.cell(row=r, column=DASH_FUNNEL_START_COL + DASH_FUNNEL_SPAN + 1,
                value=f"{uebersetzt(stufe['stufe'])} · {pct}").font = Font(color="64748B", size=9)

    # Ohne Stellen gibt es keinen größten Verlust (None), wie im Funnel-Blatt oben; ohne die Prüfung
    # brach der ganze Export einer frischen Installation hier ab (P2-62).
    groesster_verlust = funnel["engstellen"].get("groesster_verlust")
    if groesster_verlust:
        ws.cell(row=17 + len(stufen) + 1, column=DASH_FUNNEL_START_COL,
                value=groesster_verlust["text"]).font = Font(color=FUNNEL_ROT, bold=True, size=9)


def build_workbook() -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    heute = datetime.date.today().isoformat()

    with Session(engine) as s:
        companies = {c.id: c for c in s.exec(select(Company)).all()}
        jobs = s.exec(select(Job).where(Job.deleted_at.is_(None))).all()
        apps = s.exec(select(Application)).all()
        emails = s.exec(select(Email)).all()
        contacts = s.exec(select(Contact)).all()
        netz = s.exec(select(NetworkContact).where(NetworkContact.deleted_at.is_(None))).all()
        hh = s.exec(select(Headhunter).where(Headhunter.deleted_at.is_(None))).all()
        ziele = s.exec(select(TargetCompany).where(TargetCompany.deleted_at.is_(None))).all()
        outreach = s.exec(select(Outreach)).all()
        # Phase 69, Stufe C — Zusatz-Rows für die Gesamtprozess-KPI-Reihe (Interview/
        # NetzwerkGespraech), s. app.gesamtprozess.
        interviews = s.exec(select(Interview)).all()
        netzwerkgespraeche = s.exec(select(NetzwerkGespraech)).all()
        # ATS + Match-100: neuester Wert je Job (Phase 75: eine Schleife für beide Dicts);
        # Beirat: neuester Beirats-Check je Job. Aufsteigend sortiert, spätere überschreiben.
        ats = {}
        match100 = {}
        for cv in sorted(s.exec(select(CVVersion)).all(), key=lambda c: c.created_at):
            if not cv.job_id:
                continue
            if cv.ats_score is not None:
                ats[cv.job_id] = cv.ats_score
            if cv.match_score100 is not None:
                match100[cv.job_id] = cv.match_score100
        beirat = {}
        for f in sorted(s.exec(select(JobFile).where(JobFile.kind == "Beirats-Check")).all(),
                        key=lambda f: f.created_at):
            if f.note:
                beirat[f.job_id] = f.note
        # Grund-Quelle fürs Aussortiert-Blatt (Phase 75): manuelle Einträge aus
        # „Notizen & Verlauf", chronologisch je Job — Auswertung in _grund().
        grund_manuell: dict = {}
        for l in sorted(s.exec(select(JobLog).where(JobLog.art == "manuell")).all(),
                        key=lambda l: l.created_at):
            if l.job_id and l.eintrag and l.eintrag.strip():
                grund_manuell.setdefault(l.job_id, []).append(l.eintrag.strip())
        # „Beworben am" (P2-30, Spalte L) — FERTIGE Funktion, nicht nachbauen (Spec §0/§4.4):
        # zwei Quellen (applied_date + JobLog-Statuswechsel), s. Docstring dort. Datum → .date(),
        # weil die Spalte ein reines Datumsformat trägt, keine Uhrzeit.
        from pipeline.gmail_ingest import beworben_am_je_job
        beworben_am = {jid: dt.date() for jid, dt in beworben_am_je_job(s).items()}
        # „CV-Version" (P2-30, Spalte M) — jüngste FERTIGE CVVersion je Job. „Fertig" (nicht
        # „entwurf", s. CVVersion.status Phase 46 Stufe B), weil ein Entwurf noch kein Dokument
        # ist, das der Nutzer tatsächlich verschickt hat.
        cv_version = {}
        for cv in sorted(s.exec(select(CVVersion)).all(), key=lambda c: c.created_at):
            if not cv.job_id or cv.status != "fertig" or not cv.language:
                continue
            sprache = cv.language.strip().upper()
            if sprache in bewerbungssprache.CODES:
                cv_version[cv.job_id] = f"Tailored ({sprache})"
        # Blatt „Bewerbungen" (P2-81): Datum je Gesprächsrunde und Absagedatum je Stelle
        runden = _gespraechsrunden(interviews, s.exec(select(Transcript)).all())
        absage_am = _absage_am(
            jobs, emails, s.exec(select(JobLog).where(JobLog.eintrag.contains(ABSAGE_MARKE))).all())

    # ── Blatt 1: Dashboard (Cockpit) — Kennzahlen identisch zu /api/dashboard ──
    ws = wb.active
    ws.title = "Dashboard"
    ws.sheet_view.showGridLines = False

    by_status = Counter((j.status or "Neu") for j in jobs)
    # Response Rate / Ø Antwortzeit: EINZIGE Berechnung in app.response_metrics (Phase 67B,
    # P2-7) — /api/dashboard (app/main.py) ruft dieselbe Funktion auf. NICHT hier lokal
    # nachbauen, sonst driftet die Formel wieder auseinander (genau das war der Befund).
    resp_kpis = response_kpis(emails, apps)
    avg_resp = resp_kpis["avg_response_hours"]
    response_rate = resp_kpis["response_rate"]
    active_apps = sum(by_status.get(st, 0) for st in ("Beworben", "Interview", "Angebot"))
    fu_jobs = [j for j in jobs if j.follow_up_date and (j.status or "Neu") not in TERMINAL_STATUSES]
    fu_overdue = sum(1 for j in fu_jobs if j.follow_up_date <= heute)
    nc_fu = [n for n in netz if n.next_action_date]
    nc_overdue = sum(1 for n in nc_fu if n.next_action_date[:10] <= heute)
    top_matches = sum(1 for j in jobs if (j.match_score or 0) >= 4)

    ws.merge_cells("A1:J1")
    ws["A1"] = tx("Bewerbungs-Management — Stand")
    ws["A1"].font = Font(color=_marke(), bold=True, size=20)
    from pipeline.user_profile import user_name
    ws.merge_cells("A2:H2")
    ws["A2"] = tx("{name} · Export aus dem Bewerbungs-Mgmt-System", name=user_name())
    ws["A2"].font = LABEL_FONT
    ws["J2"] = datum(datetime.date.today())
    ws["J2"].font = Font(color=_text(), bold=True, size=11)
    ws["J2"].alignment = Alignment(horizontal="right")

    kpis1 = [(tx("Aktive Stellen"), len(jobs)), (tx("Laufende Bewerbungen"), active_apps),
             (tx("Bewerbungen gesamt"), len(apps)), (tx("Antworten"), resp_kpis["responses"]),
             (tx("Response Rate"), tx("{wert} %", wert=response_rate) if response_rate is not None else "—")]
    kpis2 = [(tx("Top-Zielstellen (≥4)"), top_matches), (tx("Follow-ups fällig"), fu_overdue),
             (tx("Follow-ups offen"), len(fu_jobs)), (tx("Netzwerk-Aktionen fällig"), nc_overdue),
             (tx("Ø Antwortzeit (h)"), avg_resp if avg_resp is not None else "—")]
    for base_row, kpis in ((4, kpis1), (7, kpis2)):
        for i, (label, wert) in enumerate(kpis):
            col = 1 + i * 2
            ws.cell(row=base_row, column=col, value=label).font = LABEL_FONT
            ws.cell(row=base_row + 1, column=col, value=wert).font = _kpi_font()
    ws.row_dimensions[5].height = 26
    ws.row_dimensions[8].height = 26

    # ── Dritte KPI-Reihe „Gesamtprozess seit Beginn" (Phase 69, Stufe C) ──────────────────
    # EINZIGE Berechnung über app.gesamtprozess (Stufe A) — identisch zu /api/dashboard
    # (Stufe B, app/main.py::get_dashboard). Cent-genau dieselbe Datengrundlage (apps/jobs/
    # emails/outreach/interviews/netzwerkgespraeche aus derselben Session oben), NICHT hier
    # lokal nachgebaut — genau der Fehler, den response_metrics.py schon einmal behoben hat.
    bew_kpi = bewerbungen_kpi(apps, outreach)
    ges_kpi = gespraeche_kpi(interviews, netzwerkgespraeche)
    abs_kpi = absagen_kpi(jobs, outreach)
    kr_kpi = keine_reaktion_kpi(jobs, emails, apps, outreach)

    ws.cell(row=10, column=1, value=tx("Gesamtprozess seit Beginn")).font = Font(color=_marke(), bold=True, size=12)
    # Layout-Muster von kpis1/kpis2 exakt übernommen (Label klein grau, Wert groß fett Navy),
    # zusätzlich je Karte 1-2 kleine graue Split-Zeilen — Vorbild Dashboard.tsx::
    # GesamtprozessSection, gleiche Beschriftungen/Reihenfolge wie dort.
    kpis3 = [
        (tx("Bewerbungen gesamt"), bew_kpi["wert"],
         [tx("davon Ausschreibungen {ausschreibungen} · Netzwerk {netzwerk}",
             ausschreibungen=bew_kpi['splits'].get('Positionsausschreibungen', 0),
             netzwerk=bew_kpi['splits'].get('Netzwerk', 0))]),
        (tx("Gespräche gesamt"), ges_kpi["wert"],
         [tx("Headhunter {headhunter} · Recruiter {recruiter} · Hiring Manager {manager} · "
             "Fachbereich/Sonstige {fachbereich}",
             headhunter=ges_kpi['splits'].get('Headhunter', 0),
             recruiter=ges_kpi['splits'].get('Recruiter (Firma)', 0),
             manager=ges_kpi['splits'].get('Hiring Manager', 0),
             fachbereich=ges_kpi['splits'].get('Fachbereich/Sonstige', 0)),
          tx("davon vor Ort {anzahl}", anzahl=ges_kpi['splits'].get('davon_vor_Ort', 0))]),
        (tx("Absagen gesamt"), abs_kpi["wert"],
         [tx("davon Ausschreibungen {ausschreibungen} · Netzwerk {netzwerk}",
             ausschreibungen=abs_kpi['splits'].get('Ausschreibungen', 0),
             netzwerk=abs_kpi['splits'].get('Netzwerk', 0))]),
        (tx("Keine Reaktion"), kr_kpi["wert"], []),
    ]
    for i, (label, wert, split_lines) in enumerate(kpis3):
        col = 1 + i * 2
        ws.cell(row=11, column=col, value=label).font = LABEL_FONT
        ws.cell(row=12, column=col, value=wert).font = _kpi_font()
        for k, line in enumerate(split_lines):
            ws.cell(row=13 + k, column=col, value=line).font = SPLIT_FONT
    ws.row_dimensions[12].height = 26

    # Drei Spaltenblöcke: Pipeline je Status · Suchplan A/B/C · Top-Portale
    r0 = 16
    ws.cell(row=r0, column=1, value=tx("Pipeline — Stellen je Status")).font = Font(color=_marke(), bold=True, size=12)
    r = r0 + 1
    for status in PIPELINE_ORDER + AUSSORTIERT:
        n = by_status.get(status, 0)
        if not n:
            continue
        bg, txt = STATUS_FARBEN[status]
        c = ws.cell(row=r, column=1, value=uebersetzt(status))
        c.fill = _fill(bg)
        c.font = Font(color=txt, bold=True, size=10)
        ws.cell(row=r, column=2, value=n).font = Font(color=_text(), bold=True, size=11)
        r += 1

    by_plan = Counter(norm_plan(j.plan_ab) or "ohne" for j in jobs)
    ws.cell(row=r0, column=4, value=tx("Stellen je Suchplan")).font = Font(color=_marke(), bold=True, size=12)
    for i, plan in enumerate(["A", "B", "C", "ohne"]):
        ws.cell(row=r0 + 1 + i, column=4,
                value=tx("Plan {plan}", plan=plan) if plan != "ohne" else tx("ohne Plan")).font = Font(color=_text(), size=10)
        ws.cell(row=r0 + 1 + i, column=5, value=by_plan.get(plan, 0)).font = Font(color=_text(), bold=True, size=11)

    by_portal = Counter((j.portal or tx("Unbekannt")) for j in jobs)
    ws.cell(row=r0, column=7, value=tx("Top-Portale")).font = Font(color=_marke(), bold=True, size=12)
    for i, (portal, n) in enumerate(by_portal.most_common(7)):
        ws.cell(row=r0 + 1 + i, column=7, value=uebersetzt(portal)).font = Font(color=_text(), size=10)
        ws.cell(row=r0 + 1 + i, column=8, value=n).font = Font(color=_text(), bold=True, size=11)

    _set_widths(ws, [17, 6, 3, 14, 6, 3, 16, 6, 3, 10])

    # EINE Berechnung (funnel_kpi) identisch zu /api/dashboard (gesamtprozess.funnel) — speist
    # den Kompakt-Trichter auf DIESEM Blatt UND das Detail-Blatt „Funnel".
    funnel = funnel_kpi(jobs, apps, emails, outreach, interviews, netzwerkgespraeche)
    _dashboard_funnel_block(ws, funnel)

    # ── Blatt „Funnel" an Position 2 (Phase 70, Stufe A). `create_sheet(.., 1)` schiebt alle
    # danach erzeugten Blätter (Stellen, Aussortiert, …) automatisch auf Position 3+.
    _funnel_sheet(wb, funnel)

    # ── Blatt 2: Stellen — pro Status gruppiert, farbige Trennzeilen ───────────
    ws2 = wb.create_sheet(tx("Stellen"))
    ws2.sheet_view.showGridLines = False
    ws2.append([uebersetzt(h) for h in JOB_HEADERS])
    for status in PIPELINE_ORDER:
        gruppe = [j for j in jobs if (j.status or "Neu") == status]
        if not gruppe:
            continue
        gruppe.sort(key=lambda j: (-(j.match_score or 0), (j.company_name or "").lower()))
        r = ws2.max_row + 1
        ws2.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(JOB_HEADERS))
        bg, txt = STATUS_FARBEN[status]
        for c in range(1, len(JOB_HEADERS) + 1):
            ws2.cell(row=r, column=c).fill = _fill(bg)
        kopf = ws2.cell(row=r, column=1, value=f"{uebersetzt(status)}  ({len(gruppe)})")
        kopf.font = Font(color=txt, bold=True, size=11)
        ws2.row_dimensions[r].height = 20
        for j in gruppe:
            _job_zeile(ws2, j, ats, beirat, match100, grund_manuell,
                       beworben_am=beworben_am.get(j.id), cv_version=cv_version.get(j.id))
    _set_widths(ws2, JOB_WIDTHS)
    _breite_fuer_kopf(ws2)
    _style_header(ws2, len(JOB_HEADERS), autofilter=False)  # Trennzeilen würden mitfiltern
    # CV-Version-Dropdown (P2-30, Spalte M) — WEICH: showErrorMessage=False lässt freies Tippen
    # zu, die Liste ist nur ein Vorschlag. BEWUSST ohne Versionsnummer (s. CV_VERSION_OPTIONEN).
    # Bewerbungsdatum ist automatisch aus beworben_am_je_job() vorbefüllt (Spalte L); die
    # CV-Version dagegen NUR zu einem Teil (s. Spec §0) — deshalb hier zusätzlich ein
    # Dropdown zum Nachschärfen von Hand. WICHTIG: der Export läuft täglich neu (dated_filename),
    # jede Handeintragung in dieser Spalte ist beim nächsten Lauf weg — die automatische
    # Vorbefüllung aus CVVersion ist der eigentliche Wert der Spalte, das Dropdown nur die
    # Werkstatt-Hilfe für die aktuelle Kopie. NICHT „aufräumen".
    dv_cv = DataValidation(type="list", formula1=CV_VERSION_OPTIONEN, showErrorMessage=False)
    ws2.add_data_validation(dv_cv)
    dv_cv.add(f"M2:M{max(ws2.max_row, 2)}")   # ohne Stellen sonst „M2:M1“, ungültig (P2-62)

    # ── Blatt „Bewerbungen" (P2-81) — direkt nach „Stellen", vor „Aussortiert"
    _bewerbungen_sheet(wb, jobs, apps, interviews, ats, match100, beworben_am, runden, absage_am)

    # ── Blatt 3: Aussortiert — flach, filterbar ────────────────────────────────
    ws3 = wb.create_sheet(tx("Aussortiert"))
    ws3.append([uebersetzt(h) for h in AUSSORTIERT_HEADERS])
    for status in AUSSORTIERT:
        gruppe = [j for j in jobs if (j.status or "Neu") == status]
        gruppe.sort(key=lambda j: (-(j.match_score or 0), (j.company_name or "").lower()))
        for j in gruppe:
            _job_zeile(ws3, j, ats, beirat, match100, grund_manuell, status=status)
    _set_widths(ws3, AUSSORTIERT_WIDTHS)
    _breite_fuer_kopf(ws3)
    _style_header(ws3, len(AUSSORTIERT_HEADERS))

    # ── Blatt „Referenzen" (P2-30) — bewusst NACH Aussortiert, VOR Kontakte: gehört inhaltlich
    # zu den Bewerbungsunterlagen (wer bürgt für mich), nicht zu den Netzwerklisten. Leer außer
    # Kopfzeile (Vorgabe) — die beiden Dropdowns liegen aber schon auf Zeile 2–200, damit
    # sie beim Befüllen von Hand sofort da sind.
    ws_ref = wb.create_sheet(tx("Referenzen"))
    REFERENZEN_HEADERS = [tx("Name"), tx("Rolle / Position"), tx("Firma"), tx("Zeitraum gemeinsam"), tx("Kategorie"),
                          tx("Kontakt"), tx("Zugesagt"), tx("Zuletzt kontaktiert"), tx("Notiz")]
    REFERENZEN_WIDTHS = [24, 26, 22, 18, 18, 28, 14, 16, 46]
    ws_ref.append(REFERENZEN_HEADERS)
    _set_widths(ws_ref, REFERENZEN_WIDTHS)
    _breite_fuer_kopf(ws_ref)
    _style_header(ws_ref, len(REFERENZEN_HEADERS))
    # Kategorie (Spalte E) — weich, dieselbe Haltung wie CV-Version oben: Vorschlag, kein Zwang.
    # „Kunde"/„Sonstige" ergänzt (der ursprüngliche Dreiervorschlag reicht in der Praxis nicht, Spec §1.3).
    dv_kategorie = DataValidation(
        type="list",
        formula1='"' + ",".join([tx("Ehemaliger Chef"), tx("Peer"), tx("Direct Report"), tx("Kunde"), tx("Sonstige")]) + '"',
        showErrorMessage=False)
    ws_ref.add_data_validation(dv_kategorie)
    dv_kategorie.add("E2:E200")
    # Zugesagt (Spalte G) — ebenso weich.
    dv_zugesagt = DataValidation(type="list", formula1='"' + ",".join([tx("Ja"), tx("Nein"), tx("Ausstehend")]) + '"',
                                 showErrorMessage=False)
    ws_ref.add_data_validation(dv_zugesagt)
    dv_zugesagt.add("G2:G200")

    # ── Blatt 4: Kontakte (Stellen-Kontakte) ───────────────────────────────────
    ws4 = wb.create_sheet(tx("Kontakte"))
    ws4.append([tx("Name"), tx("Rolle"), tx("Firma"), tx("Stelle"), tx("E-Mail"), tx("Telefon"), "LinkedIn", tx("Notizen")])
    job_by_id = {j.id: j for j in jobs}
    for k in sorted(contacts, key=lambda k: ((companies.get(k.company_id).name if companies.get(k.company_id) else "").lower(), (k.name or "").lower())):
        comp = companies.get(k.company_id)
        j = job_by_id.get(k.job_id)
        ws4.append([k.name, _wert(k.role), comp.name if comp else None, j.title if j else None,
                    k.email, k.phone, k.linkedin_url, k.notes])
    _set_widths(ws4, [24, 22, 24, 36, 30, 16, 40, 50])
    _breite_fuer_kopf(ws4)
    _style_header(ws4, 8)

    # ── Blatt 5: Netzwerk ──────────────────────────────────────────────────────
    ws5 = wb.create_sheet(tx("Netzwerk"))
    ws5.append([tx("Name"), tx("Beziehung"), tx("Unternehmen"), tx("Rolle"), tx("Priorität"), tx("Letzter Kontakt"),
                tx("Kanal"), tx("Nächste Aktion"), tx("Fällig am"), tx("Notizen")])
    for n in sorted(netz, key=lambda n: ((n.prioritaet or "z"), (n.name or "").lower())):
        ws5.append([n.name, n.beziehung, n.unternehmen, n.rolle, _wert(n.prioritaet),
                    n.letzter_kontakt, _wert(n.kanal), n.next_action, n.next_action_date, n.notizen])
        if n.next_action_date and n.next_action_date[:10] <= heute:
            ws5.cell(row=ws5.max_row, column=9).font = Font(color=FUNNEL_ROT, bold=True)
    _set_widths(ws5, [22, 16, 24, 26, 10, 14, 12, 34, 11, 46])
    _breite_fuer_kopf(ws5)
    _style_header(ws5, 10)

    # ── Blatt 6: Headhunter ────────────────────────────────────────────────────
    ws6 = wb.create_sheet(tx("Headhunter"))
    ws6.append([tx("Firma"), tx("Ansprechpartner"), tx("Fokus"), tx("Region"), tx("Status"), tx("Letzter Kontakt"),
                tx("Webseite"), tx("Notizen")])
    for h in sorted(hh, key=lambda h: (h.firma or "").lower()):
        ws6.append([h.firma, h.ansprechpartner, h.fokus, h.region, _wert(h.status),
                    h.letzter_kontakt, h.webseite, h.notizen])
        if h.webseite:
            link = ws6.cell(row=ws6.max_row, column=7)
            link.hyperlink = h.webseite if h.webseite.startswith("http") else f"https://{h.webseite}"
            link.font = LINK_FONT
    _set_widths(ws6, [24, 24, 28, 14, 16, 14, 30, 50])
    _breite_fuer_kopf(ws6)
    _style_header(ws6, 8)

    # ── Blatt 7: Zielfirmen ────────────────────────────────────────────────────
    ws7 = wb.create_sheet(tx("Zielfirmen"))
    ws7.append([tx("Company"), tx("Branche"), tx("Größe (MA)"), "HQ", "Tier", tx("Szenario"), tx("Key Contact"),
                tx("Status"), tx("Karriereseite"), tx("Wachstumssignal"), tx("Einschätzung")])
    for z in sorted(ziele, key=lambda z: ((z.tier or "9"), (z.company or "").lower())):
        url = z.karriere_url or z.website
        ws7.append([z.company, z.industry, z.size_ma, z.location_hq, z.tier, z.scenario,
                    z.key_contact, _wert(z.connection_status), url, z.wachstumssignal, z.einschaetzung])
        if url:
            link = ws7.cell(row=ws7.max_row, column=9)
            link.hyperlink = url if url.startswith("http") else f"https://{url}"
            link.font = LINK_FONT
    _set_widths(ws7, [26, 26, 12, 18, 8, 10, 30, 18, 30, 40, 24])
    _breite_fuer_kopf(ws7)
    _style_header(ws7, 11)

    # ── Blatt 8: Outreach (Spiegel des Drive-Trackers) ─────────────────────────
    ws8 = wb.create_sheet(tx("Outreach"))
    ws8.append([tx("Datum"), tx("Kontakt"), tx("Unternehmen"), tx("Typ"), tx("Kanal"), tx("Antwort"), tx("Antwort-Datum"),
                tx("Nächster Schritt"), tx("Next-Action"), tx("Status"), tx("Notizen")])
    for o in sorted(outreach, key=lambda o: o.datum or "", reverse=True):
        ws8.append([o.datum, o.kontakt, o.unternehmen, _wert(o.typ), _wert(o.kanal), _wert(o.antwort),
                    o.antwort_datum, o.next_step, o.next_action_datum, _wert(o.status), o.notizen])
    _set_widths(ws8, [11, 22, 24, 16, 14, 8, 12, 36, 11, 14, 50])
    _breite_fuer_kopf(ws8)
    _style_header(ws8, 11)

    out = EXPORT_DIR / dated_filename("Bewerbungs-Stand", "xlsx")
    wb.save(out)
    return out


if __name__ == "__main__":
    print("Gespeichert:", build_workbook())
