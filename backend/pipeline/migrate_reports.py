#!/usr/bin/env python3
"""Phase 31 — EINMALIGES Migrations-Skript: Bestandsdokumente (vor Phase 30 erzeugt) auf die
neue Namenskonvention `JJJJMMTT_<Typ>_<Firma>[_<Rolle>][_Rn]` (seit P2-63; Leser verstehen auch JJJJ_MM_TT) (naming.report_filename) heben und
— wo mechanisch sicher möglich — auf den Phase-30-Report-Style (assets/report_theme_bms.html)
umstellen. Deterministisch, KEIN LLM-Lauf (Design-Entscheidung 4 der Spec).

Externe Dateien (CV .docx/.pdf, Anschreiben) sind NICHT im Scope — nur:
    data/company_fit/  data/interview_prep/  data/transcripts/  data/job_postings/  data/analysen/

Re-Wrap-Strategie ("Shell-Swap", s. Bericht an den Auftraggeber): alte Datei behält ihren KOMPLETTEN
Body-Inhalt wortwörtlich (kein Parsen einzelner Abschnitte — das wäre fehleranfällig); nur Kopf-
und Fußzeile werden durch die Phase-30-Konvention ersetzt (Firma/Rolle/Datum aus der DB, NIE aus
dem alten Dateinamen geraten). Das alte `<style>` wird nach dem neuen `data/templates/
report_theme_bms.html`-CSS angehängt, damit alte Klassennamen (z. B. Briefing/Analysen mit
eigenem Stil) weiter korrekt aussehen, während neuer Kopf/Fuß bereits im neuen Look erscheinen.

CompanyFit bleibt IMMER nur umbenannt (Veto-Punkt der Spec — Company-Fit ist zu 100% JS-DATA-
getrieben: leerer <div id="root">, Inhalt kommt erst durch <script>const DATA=…</script> zur
Laufzeit; ein Re-Wrap fände im statischen HTML nichts). Für alte Match/ATS-Paare hat dieses Skript
per echtem Body-Textlängen-Check (nicht geraten) verifiziert, dass sie — anders als in der Spec
unter "JS-DATA-Dashboards" mit CompanyFit gruppiert — TATSÄCHLICH bereits substanziellen
statischen Inhalt im Body tragen (kein <script>const DATA=…>, echte sichtbare Textmenge). Sie
werden daher hier NICHT pauschal wie CompanyFit behandelt, sondern regulär für Re-Wrap versucht
(gleiche Sicherheitsschwelle wie alle anderen Kandidaten: Body-Text < MIN_TEXT_LEN → automatischer
Fallback auf reines Umbenennen, im Bericht klar ausgewiesen). Das ist eine bewusste, im
Dry-Run-Bericht ausgewiesene Abweichung von der wörtlichen Spec-Gruppierung — der Nutzer entscheidet
beim GO, ob er das so will (Alternativ-Fallback: REWRAP_MATCH_ATS unten auf False setzen).

CLI:
    cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.migrate_reports --dry-run
    cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.migrate_reports --apply
"""
import argparse
import datetime
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import Company, CVVersion, Interview, Job, Transcript
from app import naming
from app.naming import report_filename, transcript_filename
from pipeline import transcript_report as TR
from app.favicon import favicon_link     # P2-72: Icon des geltenden Designs, je Aufruf gelesen

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Bewerbung_Mgmt_System/
DATA = PROJECT_ROOT / "data"
ARCHIVE_DIR = DATA / "_migration_archiv_phase31"

SCOPE_DIRS = {
    "company_fit": DATA / "company_fit",
    "interview_prep": DATA / "interview_prep",
    "transcripts": DATA / "transcripts",
    "job_postings": DATA / "job_postings",
    "analysen": DATA / "analysen",
}

# Dateien, die NIE angefasst/gemeldet werden — explizit von der Spec ausgenommen bzw. kein Report.
NEVER_TOUCH_NAMES = {"fragenbank.md"}
NEVER_TOUCH_SUFFIXES = {".txt", ".md"}  # .md hier = _draft_*.txt-artige Nicht-Report-Dateien in
# interview_prep; die ECHTEN Transkript-.md-Dateien in data/transcripts/ werden NICHT über den
# Verzeichnis-Scan gefunden, sondern gezielt über Transcript.file_path (eigene Funktion unten) —
# der pauschale .md-Ausschluss gilt nur für den generischen Verzeichnis-Scan (Orphan-Suche).

REWRAP_MATCH_ATS = False  # s. Moduldoc — visuell geprüft (Screenshot 16.07.): alte Match/ATS-Dateien
# haben ein EIGENES dunkles Farbschema (body{background:#0B1F3A}), das beim CSS-Merge den hellen
# report_theme_bms-Seitenhintergrund überschreibt — Inhalt bleibt korrekt, aber die Seite wirkt
# durchgängig dunkel statt hell wie alle anderen migrierten Reports (kein einheitliches Bild mehr,
# das eigentliche Ziel von Phase 30). Deshalb Default auf False (= Spec-Lesart, nur umbenennen wie
# CompanyFit) — auf True setzen, falls der dunkle Look für diese beiden Reporttypen akzeptabel ist.
MIN_TEXT_LEN = 200        # Body-Text (ohne Tags) kürzer → gilt als JS-getrieben/leer → nur umbenennen

# P2-63: beide Datumsformate (JJJJMMTT neu, JJJJ_MM_TT Bestand) und alte wie neue Typ-Wörter.
NEW_FORMAT_RE = re.compile(
    r"^(?:\d{4}_\d{2}_\d{2}|\d{8})_(CompanyFit|Match|ATSscan|Briefing|Debrief|TranskriptReport|"
    r"Transkript|Stellenausschreibung|Analyse|Anzeige|Auswertung|Beirat|BeiratsCheck)_"
)
# Interne Job-/Transkript-IDs, die im FRÜHEREN Namensschema öfter vorkamen (z. B.
# "..._Briefing_Job12_R1_..."), dürfen NIE im neuen Schema stehen (Phase-30-Vorgabe: "Job-ID raus
# aus dem Namen — steht in der DB"). Bug gefunden beim Dry-Run-Review: NEW_FORMAT_RE prüft nur das
# Datums-Präfix, nicht den Rest — ein Name wie "2026_07_13_Briefing_Job12_R1_Beispiel.html" MATCHT
# das Präfix, ist aber eindeutig NICHT migriert (Job-ID noch drin). Ohne diesen Zusatz-Check hätte
# das Skript alle 4 Alt-Briefings fälschlich als "schon neu" übersprungen (0 Treffer in der
# Kategorie, statt der tatsächlich 4).
_JOBID_LEAK_RE = re.compile(r"Job\d+")
# Roh-Transkript-.md folgt NICHT report_filename's Schema, sondern weiterhin naming.transcript_
# filename(): "<Kind>_<JJJJ_MM_TT>_…" — Kind-Präfix ZUERST, danach das Datum (umgekehrt zu allen
# anderen Report-Typen dieses Skripts).
_TRANSCRIPT_OK_RE = re.compile(r"^(Transkript|Debrief)_(?:\d{4}_\d{2}_\d{2}|\d{8})_")


def _is_already_new(name: str) -> bool:
    return bool(NEW_FORMAT_RE.match(name)) and not _JOBID_LEAK_RE.search(name)


_DATE_RE = naming.DATUM_RE      # P2-63: beide Datumsformate
_STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.S)
_BODY_RE = re.compile(r"<body[^>]*>(.*)</body>", re.S)
_HEADER_HERO_RE = re.compile(r"<header[^>]*class=\"hero\"[^>]*>.*?</header>", re.S)
_FOOTER_TAG_RE = re.compile(r"<footer[^>]*>.*?</footer>", re.S)
_FOOT_DIV_RE = re.compile(r'<div class="foot">.*?</div>\s*(?=(</div>\s*)*</body>)', re.S)
_TAGS_RE = re.compile(r"<[^>]+>")


def _esc(s) -> str:
    return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _date_from_filename(name: str) -> Optional[datetime.date]:
    return naming.datum_aus_name(name)


def _resolve_date(old_path: Path) -> datetime.date:
    """Design-Entscheidung 1: Datum aus dem alten Namen, sonst File-mtime — NIE erraten."""
    return _date_from_filename(old_path.name) or datetime.date.fromtimestamp(old_path.stat().st_mtime)


class Namer:
    """Reserviert Zieldateinamen je Ordner — verhindert Kollisionen sowohl mit real vorhandenen
    (nicht selbst wegziehenden) Dateien als auch zwischen mehreren Items desselben Laufs. Gleiches
    Kollisions-Schema wie main.py::_freier_name (_2, _3, …)."""

    def __init__(self):
        self._reserved = {}

    def claim(self, dir_path: Path, base_name: str, moving_away: set) -> str:
        key = str(dir_path)
        reserved = self._reserved.setdefault(key, set())
        existing = {p.name for p in dir_path.iterdir() if p.is_file()} if dir_path.is_dir() else set()
        blocked = (existing - moving_away) | reserved
        name = base_name
        if name in blocked:
            stem, dot, ext = base_name.rpartition(".")
            n = 2
            while f"{stem}_{n}{dot}{ext}" in blocked:
                n += 1
            name = f"{stem}_{n}{dot}{ext}"
        reserved.add(name)
        return name


def _extract_shell(html: str) -> Optional[dict]:
    """Zerlegt eine alte Report-HTML in (style, content, text_len). `content` = kompletter
    Body-Inhalt OHNE die alte header.hero-Kopfzeile und OHNE die alte Fußzeile — wörtlich, keine
    Abschnitts-Interpretation. None, wenn kein <body> gefunden wird."""
    body_m = _BODY_RE.search(html)
    if not body_m:
        return None
    style_m = _STYLE_RE.search(html)
    content = _HEADER_HERO_RE.sub("", body_m.group(1), count=1)
    content = _FOOTER_TAG_RE.sub("", content)
    content = _FOOT_DIV_RE.sub("", content)
    text_len = len(_TAGS_RE.sub(" ", content).strip())
    return {"style": style_m.group(1) if style_m else "", "content": content.strip(), "text_len": text_len}


def _render_rewrap(typ: str, firma: str, rolle: Optional[str], datum: datetime.date, shell: dict,
                   zusatz_kopf: str = "", zusatz_fuss: str = "") -> str:
    css = TR._css() + "\n/* --- Alte Klassen (Altbestand, Phase 31 migriert) --- */\n" + shell["style"]
    rolle_zeile = f'<span><b>Rolle:</b> {_esc(rolle)}</span>&nbsp;·&nbsp;' if rolle else ""
    header = f"""<header class="hero">
    <div>
      <p class="eyebrow">{_esc(typ)}{zusatz_kopf}</p>
      <h1>{_esc(firma)}</h1>
      <div class="meta">{rolle_zeile}<span><b>Stand:</b> {datum:%Y-%m-%d}</span></div>
    </div>
  </header>"""
    footer = f"""<div class="foot">
    <span>Bewerbungs-Mgmt · migriert am {datetime.date.today():%Y-%m-%d} (Phase 31, Original-Datum {datum:%Y-%m-%d})</span>
    <span>Inhalt automatisch aus dem Altbestand übernommen, unverändert{zusatz_fuss}</span>
  </div>"""
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">{favicon_link()}
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(typ)} · {_esc(firma)}</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
  {header}
  {shell['content']}
  {footer}
</div>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Item-Erfassung je Kategorie. Jedes Item: alle Felder, die dry_run/apply brauchen.
# ─────────────────────────────────────────────────────────────────────────────

def _mk_item(kategorie, old_path, new_dir, new_stem, aktion, db_updates, hinweis="", rolle=None,
            zusatz_kopf="", zusatz_fuss="", extra_write=None):
    return {
        "kategorie": kategorie, "old_path": old_path, "new_dir": new_dir, "new_stem": new_stem,
        "aktion": aktion,          # rename | rewrap | rewrap_fallback_rename | missing
        "db_updates": db_updates,  # [(ModelClass, pk, feldname, wert_platzhalter)]
        "hinweis": hinweis, "rolle": rolle, "zusatz_kopf": zusatz_kopf, "zusatz_fuss": zusatz_fuss,
        "extra_write": extra_write,  # optionale Zusatzdatei (alter Debrief -> Archiv), (src,dst)
    }


def collect_company_fit(session):
    items = []
    for c in session.exec(select(Company).where(Company.fit_analysis_path.is_not(None))).all():
        old_rel = c.fit_analysis_path
        old_path = PROJECT_ROOT / old_rel
        if _is_already_new(old_path.name):
            continue
        if not old_path.is_file():
            items.append(_mk_item("CompanyFit", old_path, None, None, "missing",
                                  [(Company, c.id, "fit_analysis_path", None)],
                                  hinweis=f"Datei fehlt: {old_rel}"))
            continue
        when = _resolve_date(old_path)
        stem = report_filename("CompanyFit", c.name, when=when)
        items.append(_mk_item("CompanyFit", old_path, SCOPE_DIRS["company_fit"], stem, "rename",
                              [(Company, c.id, "fit_analysis_path", None)]))
    return items


def collect_match_ats(session):
    items = []
    for cv in session.exec(select(CVVersion).where(CVVersion.match_dashboard_path.is_not(None))).all():
        job = session.get(Job, cv.job_id)
        firma = job.company_name if job else "Firma"
        rolle = job.title if job else None
        # Datum: erst aus dem alten Dateinamen (Design-Entscheidung 1), sonst NICHT File-mtime
        # (iCloud-Sync verfälscht mtimes bekanntermaßen, s. docs/AUTOMATION.md-Lehre) — stattdessen
        # CVVersion.created_at, EIN zuverlässiger DB-Zeitstempel, der für Match+ATS desselben
        # Laufs identisch ist (hält das Paar konsistent). Nur wenn beides fehlt: File-mtime als
        # letzter Ausweg. Abweichung von der Spec-Formulierung, im Dry-Run-Bericht ausgewiesen.
        pair_when_fallback = cv.created_at.date() if cv.created_at else None
        pair = [("Match", cv.match_dashboard_path, "match_dashboard_path"),
                ("ATSscan", cv.ats_scan_path, "ats_scan_path")]
        for typ, old_rel, feld in pair:
            if not old_rel:
                continue
            old_path = PROJECT_ROOT / old_rel
            if _is_already_new(old_path.name):
                continue
            if not old_path.is_file():
                items.append(_mk_item(typ, old_path, None, None, "missing",
                                      [(CVVersion, cv.id, feld, None)], hinweis=f"Datei fehlt: {old_rel}"))
                continue
            when = _date_from_filename(old_path.name) or pair_when_fallback or _resolve_date(old_path)
            stem = report_filename(typ, firma, rolle, when=when)
            aktion = "rewrap" if REWRAP_MATCH_ATS else "rename"
            items.append(_mk_item(typ, old_path, SCOPE_DIRS["company_fit"], stem, aktion,
                                  [(CVVersion, cv.id, feld, None)], rolle=rolle))
    return items


def collect_briefings(session):
    items = []
    for iv in session.exec(select(Interview).where(Interview.prep_path.is_not(None))).all():
        old_rel = iv.prep_path
        old_path = PROJECT_ROOT / old_rel
        if _is_already_new(old_path.name):
            continue
        job = session.get(Job, iv.job_id)
        firma = job.company_name if job else "Firma"
        rolle = job.title if job else None
        if not old_path.is_file():
            items.append(_mk_item("Briefing", old_path, None, None, "missing",
                                  [(Interview, iv.id, "prep_path", None)], hinweis=f"Datei fehlt: {old_rel}"))
            continue
        when = _resolve_date(old_path)
        stem = report_filename("Briefing", firma, rolle, when=when, runde=iv.runde)
        items.append(_mk_item("Briefing", old_path, SCOPE_DIRS["interview_prep"], stem, "rewrap",
                              [(Interview, iv.id, "prep_path", None)], rolle=rolle))
    return items


def collect_postings(session):
    items = []
    for job in session.exec(select(Job).where(Job.posting_snapshot_path.is_not(None))).all():
        old_rel = job.posting_snapshot_path
        old_path = PROJECT_ROOT / old_rel
        if _is_already_new(old_path.name):
            continue
        if not old_path.is_file():
            items.append(_mk_item("Stellenausschreibung", old_path, None, None, "missing",
                                  [(Job, job.id, "posting_snapshot_path", None)],
                                  hinweis=f"Datei fehlt: {old_rel}"))
            continue
        when = _resolve_date(old_path)
        stem = report_filename("Stellenausschreibung", job.company_name, job.title, when=when)
        items.append(_mk_item("Stellenausschreibung", old_path, SCOPE_DIRS["job_postings"], stem,
                              "rewrap", [(Job, job.id, "posting_snapshot_path", None)], rolle=job.title))
    return items


def collect_transcripts_md(session):
    """Roh-Transkript-.md — nur Umbenennen (kein HTML, kein Re-Wrap nötig/möglich). WICHTIG:
    nutzt `naming.transcript_filename()` (mit Teilnehmer-Slot), NICHT `report_filename()` —
    Transkript-Rohdateien folgen weiterhin dem etablierten `<Kind>_<Datum>_<Teilnehmer>_<Firma>_
    <Position>[_Rn]`-Schema (Vorgabe vom 11.07.2026, s. naming.py-Kommentar), report_filename()
    hat gar keinen Teilnehmer-Slot — Verwechslung hätte den Kontaktnamen aus dem Dateinamen
    gelöscht. Teilnehmer kommt aus Transcript.kontakt (DB), NICHT aus dem alten Dateinamen."""
    items = []
    for t in session.exec(select(Transcript).where(Transcript.file_path.is_not(None))).all():
        old_rel = t.file_path
        old_path = PROJECT_ROOT / old_rel
        # Erkennung "schon neu" = Typ-Präfix ("Transkript_"/"Debrief_") GEFOLGT vom Datum — NICHT
        # datumsvoran (transcript_filename() erzeugt "<Kind>_<Datum>_…", Kind zuerst!) — UND kein
        # "Job<digits>" im Namen. Bug beim Review gefunden: erste Fassung prüfte fälschlich auf
        # Datum-zuerst (rückwärts) und hätte 5 von 7 bereits korrekte Dateien unnötig angefasst.
        if _TRANSCRIPT_OK_RE.match(old_path.name) and not _JOBID_LEAK_RE.search(old_path.name):
            continue
        if not old_path.is_file():
            items.append(_mk_item("Transkript-Rohdatei", old_path, None, None, "missing",
                                  [(Transcript, t.id, "file_path", None)], hinweis=f"Datei fehlt: {old_rel}"))
            continue
        job = session.get(Job, t.job_id)
        firma = job.company_name if job else "Firma"
        rolle = job.title if job else None
        iv = session.get(Interview, t.interview_id) if t.interview_id else None
        stem = transcript_filename("Transkript", t.recorded_at, t.kontakt, firma, rolle,
                                   runde=iv.runde if iv else None)
        items.append(_mk_item("Transkript-Rohdatei", old_path, SCOPE_DIRS["transcripts"], stem,
                              "rename", [(Transcript, t.id, "file_path", None)], rolle=rolle))
    return items


def collect_debrief_to_report(session):
    """Design-Entscheidung 2: Alt-Debrief -> Transkript-Report (report_path setzen, debrief_path
    NULL, alte Debrief-Datei ins Archiv). Nutzt tatsächlich dieselbe CSS/HTML-Bau-Logik wie neu
    erzeugte Reports (pipeline.transcript_report), damit migrierte und neue Reports identisch
    aussehen — kein eigenes Template."""
    items = []
    for t in session.exec(select(Transcript).where(Transcript.debrief_path.is_not(None))).all():
        old_rel = t.debrief_path
        old_path = PROJECT_ROOT / old_rel
        job = session.get(Job, t.job_id)
        iv = session.get(Interview, t.interview_id) if t.interview_id else None
        firma = job.company_name if job else "Firma"
        rolle = job.title if job else None
        if not old_path.is_file():
            items.append(_mk_item("Debrief->TranskriptReport", old_path, None, None, "missing",
                                  [(Transcript, t.id, "debrief_path", None)], hinweis=f"Datei fehlt: {old_rel}"))
            continue
        when = t.recorded_at or _resolve_date(old_path)
        stem = report_filename("TranskriptReport", firma, rolle, when=when, runde=iv.runde if iv else None)
        item = _mk_item("Debrief->TranskriptReport", old_path, SCOPE_DIRS["transcripts"], stem,
                        "debrief_convert",
                        [(Transcript, t.id, "report_path", None), (Transcript, t.id, "debrief_path", "")],
                        rolle=rolle)
        item["_transcript_id"] = t.id
        item["_summary"] = t.summary
        item["_raw_file_path"] = t.file_path
        item["_job"] = job
        item["_iv"] = iv
        item["_t"] = t
        items.append(item)
    return items


def collect_analysen():
    """Absagen-Analyse (kein DB-Pfadfeld — Design: nur verlinkt/über FTS auffindbar). Erkennung
    über Dateinamen-Muster ('Absagen_Analyse' alte Reihenfolge, oder generisch: irgendeine .html
    unterhalb data/analysen, die nicht bereits im neuen Schema UND nicht selbst ein Migrations-
    Ergebnis ist)."""
    items = []
    d = SCOPE_DIRS["analysen"]
    if not d.is_dir():
        return items
    for p in sorted(d.iterdir()):
        if not p.is_file() or p.suffix != ".html" or _is_already_new(p.name):
            continue
        when = _resolve_date(p)
        # Typ aus dem alten Namen ableiten (nur für den <Firma>-Slot von report_filename
        # zweckentfremdet — Analysen sind nicht firmenbezogen, s. Phase-30-Konvention
        # "JJJJ_MM_TT_Analyse_Absagen"): den Namensteil NACH dem Datum nehmen, "_Analyse"/"Analyse_"
        # entfernen.
        rest = _DATE_RE.sub("", p.stem, count=1).strip("_")
        rest = re.sub(r"(^|_)Analyse($|_)", "_", rest, flags=re.IGNORECASE).strip("_") or "Bericht"
        stem = report_filename("Analyse", rest, when=when)
        items.append(_mk_item("Analyse", p, d, stem, "rewrap", []))
    return items


def collect_all(session):
    return {
        "CompanyFit": collect_company_fit(session),
        "Match/ATS": collect_match_ats(session),
        "Briefing": collect_briefings(session),
        "Stellenausschreibung": collect_postings(session),
        "Transkript-Rohdatei": collect_transcripts_md(session),
        "Debrief->TranskriptReport": collect_debrief_to_report(session),
        "Analyse": collect_analysen(),
    }


def collect_orphans(session, items_by_cat):
    """Dateien in den Scope-Ordnern, die (a) von KEINEM aktuellen DB-Pfadfeld referenziert werden,
    (b) NICHT Ziel eines Migrations-Items sind (z. B. Analysen — die haben laut Design GAR KEIN
    DB-Feld, s. Phase 30 'nur verlinkt') UND (c) NICHT schon im neuen Namensschema vorliegen
    (Analysen-Dateien wie Cleanup-Berichte, die nie ein Item werden, weil `collect_analysen()`
    sie bereits als aktuell überspringt) — erst wenn KEINS der drei zutrifft, gilt eine Datei als
    wirklich verwaist. Wird NICHT angefasst, nur gemeldet."""
    referenced = set()
    for items in items_by_cat.values():
        for it in items:
            if it["old_path"] is not None:
                referenced.add(str(it["old_path"]))
    for c in session.exec(select(Company)).all():
        if c.fit_analysis_path:
            referenced.add(str(PROJECT_ROOT / c.fit_analysis_path))
    for cv in session.exec(select(CVVersion)).all():
        if cv.match_dashboard_path:
            referenced.add(str(PROJECT_ROOT / cv.match_dashboard_path))
        if cv.ats_scan_path:
            referenced.add(str(PROJECT_ROOT / cv.ats_scan_path))
    for iv in session.exec(select(Interview)).all():
        if iv.prep_path:
            referenced.add(str(PROJECT_ROOT / iv.prep_path))
    for job in session.exec(select(Job)).all():
        if job.posting_snapshot_path:
            referenced.add(str(PROJECT_ROOT / job.posting_snapshot_path))
    for t in session.exec(select(Transcript)).all():
        for f in (t.file_path, t.debrief_path, t.report_path):
            if f:
                referenced.add(str(PROJECT_ROOT / f))
    # 'missing' Items (DB verweist auf eine nicht mehr existierende Datei) taugen nicht als
    # Referenz für eine tatsächlich vorhandene, gleichnamige Datei — kommt praktisch nicht vor,
    # aber sauber ausschließen: kein Sonderfall nötig, `referenced` enthält nur DB-Werte.
    orphans = []
    for name, d in SCOPE_DIRS.items():
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if not p.is_file() or p.name in NEVER_TOUCH_NAMES:
                continue
            if p.suffix.lower() in NEVER_TOUCH_SUFFIXES:
                continue
            if str(p) in referenced:
                continue
            if _is_already_new(p.name):
                continue  # schon im neuen Schema (z. B. Analysen ohne DB-Feld) — kein Waisenkind
            orphans.append(str(p.relative_to(PROJECT_ROOT)))
    return orphans


# ─────────────────────────────────────────────────────────────────────────────
# Dry-Run
# ─────────────────────────────────────────────────────────────────────────────

def dry_run():
    init_db()
    with Session(engine) as session:
        items_by_cat = collect_all(session)
        orphans = collect_orphans(session, items_by_cat)

        namer = Namer()
        moving_away_by_dir = {}
        for items in items_by_cat.values():
            for it in items:
                if it["new_dir"] is None:
                    continue
                key = str(it["new_dir"])
                moving_away_by_dir.setdefault(key, set()).add(it["old_path"].name)

        print("=" * 88)
        print("PHASE 31 — REPORT-MIGRATION — DRY RUN (nichts wird verändert)")
        print("=" * 88)
        total_rename = total_rewrap = total_missing = total_fallback = 0
        for kategorie, items in items_by_cat.items():
            if not items:
                continue
            print(f"\n### {kategorie}  ({len(items)} Datei(en))")
            for it in items:
                old_rel = it["old_path"].relative_to(PROJECT_ROOT) if it["old_path"] else "?"
                if it["aktion"] == "missing":
                    total_missing += 1
                    print(f"  [FEHLT]   {old_rel}  —  {it['hinweis']}")
                    continue
                ext = ".html" if kategorie != "Transkript-Rohdatei" else it["old_path"].suffix
                base_name = f"{it['new_stem']}{ext}"
                new_name = namer.claim(it["new_dir"], base_name, moving_away_by_dir.get(str(it["new_dir"]), set()))
                new_rel = it["new_dir"].relative_to(PROJECT_ROOT) / new_name
                aktion_anzeige = it["aktion"]
                if it["aktion"] == "rewrap":
                    shell = _extract_shell(it["old_path"].read_text(encoding="utf-8", errors="replace"))
                    if not shell or shell["text_len"] < MIN_TEXT_LEN:
                        aktion_anzeige = "rename (Rewrap-Fallback: kein/zu wenig statischer Inhalt)"
                        total_fallback += 1
                    else:
                        total_rewrap += 1
                elif it["aktion"] == "debrief_convert":
                    total_rewrap += 1
                else:
                    total_rename += 1
                print(f"  [{aktion_anzeige:>45}]  {old_rel}")
                print(f"  {'':>49}→ {new_rel}")

        print(f"\n{'-'*88}")
        print(f"Zusammenfassung: {total_rename} umbenannt · {total_rewrap} re-wrapped · "
              f"{total_fallback} Rewrap->Fallback-Umbenennen · {total_missing} fehlende Dateien")
        print(f"\nVerwaiste Dateien (keine DB-Referenz — werden NICHT angefasst, nur gemeldet): {len(orphans)}")
        for o in orphans:
            print(f"  - {o}")
        print(f"\nSteuerbar: REWRAP_MATCH_ATS = {REWRAP_MATCH_ATS} (s. Moduldoc — alte Match/ATS-Paare "
              f"sind laut Body-Text-Check KEIN reines JS-DATA wie CompanyFit; auf False setzen für die "
              f"wörtliche Spec-Lesart 'nur umbenennen').")
        print("\nNächster Schritt: Backup + `--apply` erst nach ausdrücklichem GO.")


# ─────────────────────────────────────────────────────────────────────────────
# Apply
# ─────────────────────────────────────────────────────────────────────────────

def _backup():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    (DATA / "backups").mkdir(parents=True, exist_ok=True)
    db_backup = DATA / "backups" / f"bewerbung_backup_{ts}_vor_phase31_migration.sqlite"
    shutil.copy2(DATA / "bewerbung.sqlite", db_backup)
    data_backup = DATA / f"_migration_backup_{ts}"
    data_backup.mkdir(parents=True, exist_ok=True)
    for name, d in SCOPE_DIRS.items():
        if d.is_dir():
            shutil.copytree(d, data_backup / name)
    print(f"Backup: {db_backup.relative_to(PROJECT_ROOT)}")
    print(f"Backup: {data_backup.relative_to(PROJECT_ROOT)}/")
    return db_backup, data_backup


def apply():
    init_db()
    with Session(engine) as session:
        items_by_cat = collect_all(session)

    print("Backup wird erstellt …")
    _backup()

    namer = Namer()
    moving_away_by_dir = {}
    for items in items_by_cat.values():
        for it in items:
            if it["new_dir"] is None:
                continue
            key = str(it["new_dir"])
            moving_away_by_dir.setdefault(key, set()).add(it["old_path"].name)

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    ergebnis = {"umbenannt": [], "rewrapped": [], "rewrap_fallback": [], "fehlend": [], "fehler": []}

    with Session(engine) as session:
        for kategorie, items in items_by_cat.items():
            for it in items:
                try:
                    if it["aktion"] == "missing":
                        ergebnis["fehlend"].append({"kategorie": kategorie, "hinweis": it["hinweis"]})
                        for model, pk, feld, _ in it["db_updates"]:
                            row = session.get(model, pk)
                            if row is not None:
                                setattr(row, feld, None)
                                session.add(row)
                        continue

                    old_path = it["old_path"]
                    ext = ".html" if kategorie != "Transkript-Rohdatei" else old_path.suffix
                    base_name = f"{it['new_stem']}{ext}"
                    new_name = namer.claim(it["new_dir"], base_name, moving_away_by_dir.get(str(it["new_dir"]), set()))
                    new_path = it["new_dir"] / new_name
                    new_rel = str(new_path.relative_to(PROJECT_ROOT))

                    if kategorie == "Debrief->TranskriptReport":
                        t = session.get(Transcript, it["_transcript_id"])
                        job = it["_job"]
                        iv = it["_iv"]
                        old_html = old_path.read_text(encoding="utf-8", errors="replace")
                        shell = _extract_shell(old_html)
                        summary_html = f'<p>{_esc(it["_summary"] or "(keine Zusammenfassung im Altbestand hinterlegt)")}</p>'
                        sections_html = f'<h2 class="sec">Zusammenfassung</h2>\n<div class="card">{summary_html}</div>'
                        if shell and shell["text_len"] >= MIN_TEXT_LEN:
                            sections_html += "\n" + shell["content"]
                        rohtext = TR._lies_rohtext(it["_raw_file_path"])
                        html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">{favicon_link()}
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transkript-Report · {_esc(job.company_name if job else '')}</title>
<style>{TR._css()}\n/* --- Alte Debrief-Klassen (Phase 31 migriert) --- */\n{(shell or {}).get('style', '')}</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <div>
      <p class="eyebrow">Transkript-Report</p>
      <h1>{_esc(job.company_name if job else 'Unbekannte Firma')}</h1>
      <div class="meta">
        <span><b>Rolle:</b> {_esc(job.title if job else '')}</span> &nbsp;·&nbsp;
        <span><b>Gesprächsdatum:</b> {_esc(t.recorded_at or '')}</span>
      </div>
      <div class="badges">{''.join(f'<span class="pill">{_esc(b)}</span>' for b in TR._badges(job, iv, t))}</div>
    </div>
  </header>

  {sections_html}

  <h2 class="sec">Volltext</h2>
  <details class="volltext">
    <summary>Original-Transkript-Text anzeigen/verbergen</summary>
    <pre>{_esc(rohtext)}</pre>
  </details>

  <div class="foot">
    <span>Bewerbungs-Mgmt · migriert am {datetime.date.today():%Y-%m-%d} (Phase 31, ehem. Debrief-HTML)</span>
    <span>Debrief abgeschlossen (aus Altbestand migriert)</span>
  </div>
</div>
</body>
</html>
"""
                        new_path.write_text(html, encoding="utf-8")
                        archiv_ziel = ARCHIVE_DIR / old_path.name
                        if archiv_ziel.exists():
                            archiv_ziel = ARCHIVE_DIR / f"{old_path.stem}_{it['_transcript_id']}{old_path.suffix}"
                        shutil.move(str(old_path), str(archiv_ziel))
                        t.report_path = new_rel
                        t.debrief_path = None
                        session.add(t)
                        ergebnis["rewrapped"].append({"kategorie": kategorie, "alt": str(old_path.relative_to(PROJECT_ROOT)),
                                                     "neu": new_rel, "archiv": str(archiv_ziel.relative_to(PROJECT_ROOT))})
                        continue

                    if it["aktion"] == "rewrap":
                        old_html = old_path.read_text(encoding="utf-8", errors="replace")
                        shell = _extract_shell(old_html)
                        if shell and shell["text_len"] >= MIN_TEXT_LEN:
                            when = _resolve_date(old_path)
                            html = _render_rewrap(kategorie, _firma_aus_item(session, it, kategorie),
                                                  it["rolle"], when, shell)
                            new_path.write_text(html, encoding="utf-8")
                            old_path.unlink()
                            ergebnis["rewrapped"].append({"kategorie": kategorie,
                                                         "alt": str(old_path.relative_to(PROJECT_ROOT)), "neu": new_rel})
                        else:
                            shutil.move(str(old_path), str(new_path))
                            ergebnis["rewrap_fallback"].append({"kategorie": kategorie,
                                                               "alt": str(old_path.relative_to(PROJECT_ROOT)), "neu": new_rel})
                    else:
                        shutil.move(str(old_path), str(new_path))
                        ergebnis["umbenannt"].append({"kategorie": kategorie,
                                                     "alt": str(old_path.relative_to(PROJECT_ROOT)), "neu": new_rel})

                    for model, pk, feld, _ in it["db_updates"]:
                        row = session.get(model, pk)
                        if row is not None:
                            setattr(row, feld, new_rel if feld != "debrief_path" else None)
                            session.add(row)

                except Exception as e:  # noqa: BLE001 — ein Fehler darf den restlichen Lauf nicht stoppen
                    ergebnis["fehler"].append({"kategorie": kategorie,
                                              "alt": str(it["old_path"].relative_to(PROJECT_ROOT)) if it["old_path"] else "?",
                                              "fehler": str(e)})

        session.commit()

    print(json.dumps({k: len(v) for k, v in ergebnis.items()}, ensure_ascii=False, indent=2))
    return ergebnis


def _firma_aus_item(session, it, kategorie) -> str:
    for model, pk, feld, _ in it["db_updates"]:
        if model is Company:
            c = session.get(Company, pk)
            return c.name if c else "Firma"
        if model is CVVersion:
            cv = session.get(CVVersion, pk)
            job = session.get(Job, cv.job_id) if cv else None
            return job.company_name if job else "Firma"
        if model is Job:
            job = session.get(Job, pk)
            return job.company_name if job else "Firma"
        if model is Interview:
            iv = session.get(Interview, pk)
            job = session.get(Job, iv.job_id) if iv else None
            return job.company_name if job else "Firma"
    if kategorie == "Analyse":
        return it["new_stem"].split("_Analyse_", 1)[-1].replace("_", " ") if "_Analyse_" in it["new_stem"] else "Analyse"
    return "Firma"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true")
    grp.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.dry_run:
        dry_run()
    else:
        apply()
