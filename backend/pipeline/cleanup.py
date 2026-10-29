#!/usr/bin/env python3
"""System-Cleanup — Orphans, Dangling-Referenzen, Rotation, Papierkorb-Endleerung (Phase 33).

Deterministisches Aufräum-Kommando, kein LLM. Strikt Dry-Run-First:

    scan     — ändert NICHTS. Druckt einen Bericht (JSON) und schreibt
               data/analysen/JJJJ_MM_TT_Analyse_Cleanup.html (Phase-30-Report-Style).
    apply    — führt scan intern erneut aus (druckt den Plan), fragt dann nach (--ja
               überspringt die Rückfrage) und verschiebt Orphan-Dateien + Rotations-
               Kandidaten in den zentralen Papierkorb (`data/papierkorb/`, s. Phase 32 A) —
               NIE endgültig. Dangling-Referenzen (DB-Pfad zeigt ins Leere) werden nur mit
               --fix genullt; Run-/AgentTask-Rows über --row-days werden von Großfeldern
               befreit (Rows bleiben, s. u.).
    leeren   — der EINZIGE endgültig löschende Befehl im ganzen System. Verweigert ohne
               --older-days bzw. bei --older-days < 30. Danach VACUUM + FTS-Rebuild.

CLI (aus backend/):
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.cleanup scan [--rotate-days 60] [--row-days 90]
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.cleanup apply [--ja] [--fix]
        [--rotate-days 60] [--row-days 90] [--skip-orphans] [--skip-rotation]
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.cleanup leeren --older-days 90 [--ja]

Referenz-Sammlung (Spec-Vorgabe: „EINE Funktion, die ALLE Pfadfelder liefert“, deckungsgleich
mit main.py::_virtuelle_dateien / main.py::_VIRT_SLOTS, gegengeprüft 16.07.2026):
    Company.fit_analysis_path · Job.posting_snapshot_path ·
    CVVersion.{file_path,pdf_path,match_dashboard_path,ats_scan_path} ·
    Application.{cover_letter_path,cover_letter_pdf_path} · Interview.prep_path ·
    Transcript.{file_path,debrief_path,report_path} · JobFile.file_path
Alle Rows werden UNABHÄNGIG von deleted_at gelesen — verifiziert gegen main.py::delete_job (dort
werden Kinder-Rows beim Soft-Delete hart gelöscht, posting_snapshot_path zusätzlich genullt), die
Sammlung braucht daher keine eigene Tombstone-Sonderbehandlung.

Pipeline-Module importieren main.py laut bestehendem Stil NICHT (kein anderes pipeline/*.py tut
das — main.py zieht das komplette FastAPI-Setup mit). `_in_papierkorb`/`_freier_name` sind daher
aus app/main.py gespiegelt, nicht importiert; die Eingrenzung von `_in_papierkorb` ist bewusst
weiter als dort (data/ und outputs/ statt Positivliste, s. dort).

iCloud-Falle: Dateien können „evicted“ sein (Platzhalter). `is_file()` reicht als Existenz-Check —
Größe wird NIE als „kaputt“-Signal gewertet (nur zur Anzeige im Bericht genutzt).
"""
import argparse
import json
import re
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app.db import DB_PATH, engine, init_db
from app.models import (
    AgentTask, AlertMail, Application, Company, CVVersion, Interview, Job, JobFile, Run, Transcript,
)
from app import naming
from app.naming import dated_filename
from app.favicon import favicon_link
from pipeline.bericht_stil import DRUCK_SEITENFARBE_BEHALTEN, bericht_css

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Bewerbung_Mgmt_System/
DATA = PROJECT_ROOT / "data"
OUTPUTS = PROJECT_ROOT / "outputs"  # Phase 56D1 (vormals cv/)
PAPIERKORB = DATA / "papierkorb"
BACKUPS = DATA / "backups"  # Phase 56A — DB-Backups liegen jetzt hier (vorher im backend/-Ordner)

_DEFAULT_ROTATE_DAYS = 60
_DEFAULT_ROW_DAYS = 90
_MIN_LEEREN_DAYS = 30

# ── Ordner-Whitelists (Spec „Leitplanken“) ──────────────────────────────────────────────
# Orphan-Scan: Artefakt-Ordner, deren Dateien gegen die DB-Referenzmenge geprüft werden.
_ORPHAN_DIRS: dict = {
    "data/company_fit": DATA / "company_fit",
    "data/interview_prep": DATA / "interview_prep",
    "data/transcripts": DATA / "transcripts",
    "data/job_postings": DATA / "job_postings",
    "data/job_files": DATA / "job_files",
    "outputs/cv": OUTPUTS / "cv",
    "outputs/anschreiben": OUTPUTS / "anschreiben",
    "data/beirat": DATA / "beirat",   # Phase 68A / P3-7 — s. _beirat_ausnahme() unten
}
# Innerhalb der Orphan-Ordner: einzelne Dateien/Unterordner, die NIE als Orphan gelten.
_ORPHAN_DATEI_AUSNAHMEN = {"data/interview_prep/fragenbank.md"}
_ORPHAN_UNTERORDNER_AUSNAHMEN = {"data/job_files/_geloescht"}


def _beirat_ausnahme(p: Path) -> bool:
    """Phase 68A / P3-7: `data/beirat` enthält NEBEN dem per JobFile referenzierten Dashboard-
    HTML (kind='Beirats-Check', s. beirat_engine.py::_jobfile_registrieren) zwei weitere
    Dateiarten, die NIE per DB-Pfadfeld referenziert werden und die generische „referenziert-
    oder-Orphan"-Prüfung (unten, referenz_menge) deshalb fälschlich als Orphan lesen würde.
    ACHTUNG: das ist eine bewusste Abweichung vom Review-Vorschlag, den Ordner „analog
    data/agent_logs" in die altersbasierte ROTATION zu nehmen — falsch, weil data/beirat auch
    die per JobFile verlinkten Dashboards enthält; eine Alters-Löschung würde funktionierende
    Links zerstören. Der Orphan-Scan (DB-Referenz statt Alter) ist deshalb der richtige
    Mechanismus, aber er braucht diese zwei Sonderfälle:

      (a) "<...>_rohdaten.json" — Rohdaten-Zwilling GENAU EINES Dashboard-HTML, geschrieben von
          beirat_engine.py::_dashboard_speichern ("Nachvollziehbarkeit/Verifikation"), aber nie
          selbst registriert. Sein Lebenszyklus soll dem Geschwister-HTML folgen: exempt NUR
          solange dieses HTML noch im selben Ordner liegt. Verschwindet das HTML (Job gelöscht →
          JobFile-Zeile weg, Datei wandert in main.py::delete_job in den Papierkorb), erkennt der
          NÄCHSTE Scan die Rohdaten-Datei korrekt als Orphan (ein Lauf Verzögerung, nie ein
          Risiko für eine noch lebende Datei).
      (b) Das reine Debatten-Zustandsjournal "<debatte_id>.json" (JEDE Debatte, Modus „frei" wie
          „stellen_check", s. beirat_engine.py::Debatte._speichern) — bewusst OHNE eigene
          DB-Tabelle (s. beirat_engine.py Kopfkommentar: „Persistenz als JSON ... bewusst KEINE
          DB-Tabelle"). Kann strukturell NIE referenziert sein und hat auch keinen Löschpfad
          (kein DELETE-Endpunkt für Debatten) — ohne diese Ausnahme wäre JEDE dieser Dateien für
          immer ein Orphan-Fehlalarm, nie ein echter Fund.
    """
    if p.suffix != ".json":
        return False
    if p.name.endswith("_rohdaten.json"):
        geschwister_html = p.with_name(p.name[: -len("_rohdaten.json")] + ".html")
        return geschwister_html.is_file()
    return True  # bare "<debatte_id>.json" — permanente Ausnahme, s. Docstring oben


# Rotation: rein alters-basiert, bewusst NICHT gegen DB-Referenzen geprüft (das sind DB-lose
# Exporte/Logs — Spec nennt sie explizit als Orphan-Whitelist, s. o. — die hier trotzdem altern).
_ROTATIONS_DIRS: dict = {
    "data/agent_logs": DATA / "agent_logs",
    "data/apify": DATA / "apify",
    "data/mail_alerts": DATA / "mail_alerts",
    "data/exports": DATA / "exports",
    "data/digests": DATA / "digests",
}

_MODELS = {
    "Company": Company, "Job": Job, "CVVersion": CVVersion, "Application": Application,
    "Interview": Interview, "Transcript": Transcript, "JobFile": JobFile,
}


# ── Referenz-Sammlung (zentral, s. Modul-Docstring) ─────────────────────────────────────
def _norm(pfad) -> Optional[str]:
    if not pfad:
        return None
    return str(pfad).strip().lstrip("./").replace("\\", "/")


def _alle_referenzen(session: Session) -> list:
    """(modell, id, feldname, pfad) für JEDES gesetzte Pfadfeld — einzige Quelle, aus der sowohl
    die Referenz-Menge (Orphan-Scan) als auch die Dangling-Prüfung abgeleitet werden."""
    out = []

    def add(modell, row, feld):
        wert = getattr(row, feld, None)
        if wert:
            out.append((modell, row.id, feld, _norm(wert)))

    for row in session.exec(select(Company)):
        add("Company", row, "fit_analysis_path")
    for row in session.exec(select(Job)):
        add("Job", row, "posting_snapshot_path")
    for row in session.exec(select(CVVersion)):
        for feld in ("file_path", "pdf_path", "match_dashboard_path", "ats_scan_path"):
            add("CVVersion", row, feld)
    for row in session.exec(select(Application)):
        for feld in ("cover_letter_path", "cover_letter_pdf_path"):
            add("Application", row, feld)
    for row in session.exec(select(Interview)):
        add("Interview", row, "prep_path")
    for row in session.exec(select(Transcript)):
        for feld in ("file_path", "debrief_path", "report_path"):
            add("Transcript", row, feld)
    for row in session.exec(select(JobFile)):
        add("JobFile", row, "file_path")
    return out


def _dangling(referenzen: list) -> list:
    out = []
    for modell, pk, feld, pfad in referenzen:
        if not (PROJECT_ROOT / pfad).is_file():
            out.append({"modell": modell, "id": pk, "feld": feld, "pfad": pfad})
    return out


# ── Orphan-Scan ──────────────────────────────────────────────────────────────────────────
def _orphan_kandidaten(referenz_menge: set) -> list:
    heute = date.today()
    out = []
    for label, ordner in _ORPHAN_DIRS.items():
        if not ordner.is_dir():
            continue
        for p in sorted(ordner.rglob("*")):
            if not p.is_file() or p.name.startswith("."):
                continue
            rel = p.relative_to(PROJECT_ROOT).as_posix()
            if rel in _ORPHAN_DATEI_AUSNAHMEN:
                continue
            if any(rel.startswith(u + "/") for u in _ORPHAN_UNTERORDNER_AUSNAHMEN):
                continue
            if label == "data/beirat" and _beirat_ausnahme(p):
                continue
            if rel in referenz_menge:
                continue
            try:
                st = p.stat()
                groesse = st.st_size
                alter_tage = (heute - date.fromtimestamp(st.st_mtime)).days
            except OSError:
                groesse, alter_tage = 0, None
            out.append({"pfad": rel, "ordner": label, "groesse_bytes": groesse, "alter_tage": alter_tage})
    return out


# ── Rotation ─────────────────────────────────────────────────────────────────────────────
def _aeltere_dateien(ordner: Path, tage: int) -> list:
    if not ordner.is_dir():
        return []
    grenze = datetime.now().timestamp() - tage * 86400
    out = []
    for p in sorted(ordner.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        try:
            if p.stat().st_mtime < grenze:
                out.append(p)
        except OSError:
            continue
    return out


def _mail_alerts_verarbeitet(pfad: Path, session: Session) -> bool:
    """Nur VERARBEITETE Mail-Alert-Digests rotieren (Spec: „verarbeitete data/mail_alerts/*.json“).
    Eine Digest-Datei bündelt mehrere gmail_message_id (s. pipeline.mail_alerts) — erst wenn JEDE
    zugehörige AlertMail-Row `processed_at` gesetzt hat, gilt die Datei als abgeschlossen.
    Unlesbare/fremde Dateien werden defensiv NICHT rotiert (Sicherheit vor Tempo)."""
    try:
        inhalt = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(inhalt, list):
        return False
    ids = [e.get("gmail_message_id") for e in inhalt if isinstance(e, dict) and e.get("gmail_message_id")]
    if not ids:
        return False
    rows = session.exec(select(AlertMail).where(AlertMail.gmail_message_id.in_(ids))).all()
    gefunden = {r.gmail_message_id: r.processed_at for r in rows}
    return all(gefunden.get(i) is not None for i in ids)


def _backup_dateien(tage: int) -> list:
    """DB-Backups (`data/backups/bewerbung_backup_*.sqlite`, Phase 56A — vormals `backend/`) —
    eigener Ort außerhalb der übrigen `data/`-Rotationsordner, gleiche Alters-Regel. Sicherheitsregel
    (aus dem Spec-Geist „Sicherheit vor Tempo“ abgeleitet, nicht wörtlich in der Spec): das NEUESTE
    Backup wird NIE rotiert, egal wie alt — sonst könnte ein länger ruhendes Projekt am Ende
    komplett ohne DB-Backup dastehen."""
    alle = sorted((p for p in BACKUPS.glob("bewerbung_backup_*.sqlite") if not p.name.startswith(".")),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    rotierbar = alle[1:] if len(alle) > 1 else []
    grenze = datetime.now().timestamp() - tage * 86400
    return [p for p in rotierbar if p.stat().st_mtime < grenze]


def _rotation_kandidaten(session: Session, tage: int) -> dict:
    je_ordner = {}
    dateien = []
    for label, ordner in _ROTATIONS_DIRS.items():
        treffer = _aeltere_dateien(ordner, tage)
        if label == "data/mail_alerts":
            treffer = [p for p in treffer if p.suffix == ".json" and _mail_alerts_verarbeitet(p, session)]
        groesse = sum(p.stat().st_size for p in treffer)
        je_ordner[label] = {"anzahl": len(treffer), "groesse_bytes": groesse}
        for p in treffer:
            dateien.append({"pfad": p.relative_to(PROJECT_ROOT).as_posix(), "ordner": label,
                            "groesse_bytes": p.stat().st_size})

    backup_treffer = _backup_dateien(tage)
    label = "data/backups/bewerbung_backup_*.sqlite"
    je_ordner[label] = {"anzahl": len(backup_treffer),
                        "groesse_bytes": sum(p.stat().st_size for p in backup_treffer)}
    for p in backup_treffer:
        dateien.append({"pfad": p.relative_to(PROJECT_ROOT).as_posix(), "ordner": label,
                        "groesse_bytes": p.stat().st_size})

    gesamt_bytes = sum(d["groesse_bytes"] for d in dateien)
    return {"schwelle_tage": tage, "anzahl": len(dateien), "groesse_bytes": gesamt_bytes,
            "groesse_mb": round(gesamt_bytes / 1_000_000, 2), "je_ordner": je_ordner, "dateien": dateien}


# ── Run-/AgentTask-Pflege (Großfelder leeren, Rows bleiben — Kosten-Historie) ───────────────
_AGENTTASK_ABGESCHLOSSEN = {"done", "failed", "cancelled"}


def _row_pflege_kandidaten(session: Session, tage: int) -> dict:
    grenze = datetime.utcnow() - timedelta(days=tage)
    tasks = session.exec(select(AgentTask).where(AgentTask.status.in_(_AGENTTASK_ABGESCHLOSSEN))).all()
    task_ids = [t.id for t in tasks
               if t.created_at and t.created_at < grenze
               and (t.prompt or t.result_json or t.error or t.params_json)]
    runs = session.exec(select(Run)).all()
    run_ids = [r.id for r in runs if r.started_at and r.started_at < grenze and r.summary]
    return {"schwelle_tage": tage, "agenttask_ids": task_ids, "run_ids": run_ids}


def _row_pflege_ausfuehren(session: Session, tage: int) -> dict:
    kandidaten = _row_pflege_kandidaten(session, tage)
    for tid in kandidaten["agenttask_ids"]:
        t = session.get(AgentTask, tid)
        if t:
            t.prompt = t.result_json = t.error = t.params_json = None
            session.add(t)
    for rid in kandidaten["run_ids"]:
        r = session.get(Run, rid)
        if r:
            r.summary = None
            session.add(r)
    session.commit()
    return {"schwelle_tage": tage, "agenttask_bereinigt": len(kandidaten["agenttask_ids"]),
            "run_bereinigt": len(kandidaten["run_ids"])}


# ── Papierkorb ───────────────────────────────────────────────────────────────────────────
def _papierkorb_uebersicht() -> dict:
    if not PAPIERKORB.is_dir():
        return {"anzahl": 0, "groesse_mb": 0.0}
    dateien = [p for p in PAPIERKORB.rglob("*") if p.is_file() and not p.name.startswith(".")]
    groesse = sum(p.stat().st_size for p in dateien)
    return {"anzahl": len(dateien), "groesse_mb": round(groesse / 1_000_000, 2)}


def _freier_name(ordner: Path, fname: str) -> str:
    """Kollision → _2, _3 … (identisches Muster wie app/main.py::_freier_name)."""
    if not (ordner / fname).exists():
        return fname
    stem, punkt, ext = fname.rpartition(".")
    n = 2
    while (ordner / f"{stem}_{n}{punkt}{ext}").exists():
        n += 1
    return f"{stem}_{n}{punkt}{ext}"


def _in_papierkorb(rel_path: Optional[str]) -> Optional[str]:
    """Gespiegelt aus app/main.py::_in_papierkorb (s. Modul-Docstring: Pipeline-Module
    importieren main.py laut bestehendem Stil nicht). Verschiebt die Datei unter `rel_path`
    (projekt-root-relativ) in den zentralen Papierkorb, Namenspräfix = LÖSCH-Datum (heute) via
    `dated_filename` — das ist wichtig für `leeren`, s. `_papierkorb_alter_tage` unten.

    Eingrenzung (P2-56): nur innerhalb von data/ oder outputs/, geprüft am aufgelösten Pfad,
    sonst OSError, bevor etwas angefasst wird (`apply` fängt das je Datei). Das ist die
    P3-1-Prüfung aus main.py, die hier bis P2-56 fehlte. Enger als main.py (Positivliste) geht es
    nicht, weil `apply` auch Rohdaten und alte Sicherungen rotiert. Einziger Aufrufer mit einem
    Pfad aus der DB ist cv_export (alte PDF); er grenzt selbst auf seinen Zielordner ein."""
    if not rel_path:
        return None
    quelle = PROJECT_ROOT / rel_path
    try:
        aufgeloest = quelle.resolve()
    except (RuntimeError, ValueError) as exc:     # Symlink-Schleife, Nullbyte
        raise OSError(f"Pfad nicht auflösbar: {rel_path}") from exc
    wurzeln = ((PROJECT_ROOT / "data").resolve(), (PROJECT_ROOT / "outputs").resolve())
    if not any(w in aufgeloest.parents for w in wurzeln):
        raise OSError(f"Pfad außerhalb von data/ und outputs/: {rel_path}")
    if not quelle.is_file():
        return None
    PAPIERKORB.mkdir(parents=True, exist_ok=True)
    name = quelle.name
    stem, ext = (name.rsplit(".", 1) + [""])[:2] if "." in name else (name, "")
    basis = dated_filename(stem, ext) if ext else f"{date.today():%Y%m%d}_{stem}"
    ziel_name = _freier_name(PAPIERKORB, basis)
    shutil.move(str(quelle), str(PAPIERKORB / ziel_name))
    return f"data/papierkorb/{ziel_name}"


# P2-63: Papierkorb-Präfix ist seit der Umstellung JJJJMMTT_, der Bestand trägt noch JJJJ_MM_TT_ —
# BEIDE Formate müssen das Alter liefern, sonst wirkt der Altbestand wie "heute" (mtime) bzw. die
# Leerung greift falsch. Parser zentral in app.naming.
_DATE_PREFIX_RE = naming.DATUM_PRAEFIX_RE


def _papierkorb_alter_tage(p: Path) -> int:
    """Alter = Zeit SEIT DEM LÖSCHEN, nicht Alter der Original-Datei: `_in_papierkorb` verschiebt
    per `shutil.move` — das behält die ORIGINAL-mtime der Quelldatei bei, NICHT den Verschiebe-
    Zeitpunkt. Der Dateiname trägt aber das Löschdatum als Präfix (dated_filename() oben), darum
    wird das geparst; Fallback auf mtime nur, wenn kein Präfix erkennbar ist (z. B. Dateien, die
    von Hand in den Papierkorb gelegt wurden)."""
    d = naming.datum_aus_praefix(p.name)
    if d:
        return (date.today() - d).days
    try:
        return (date.today() - date.fromtimestamp(p.stat().st_mtime)).days
    except OSError:
        return 0


def _backup_db() -> str:
    """SQLite-Backup vor jedem apply/leeren (Muster `backup_JJJJMMTT_HHMMSS`, Projektkonvention)."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    BACKUPS.mkdir(parents=True, exist_ok=True)
    ziel = BACKUPS / f"bewerbung_backup_{ts}_vor_cleanup.sqlite"
    shutil.copy2(DB_PATH, ziel)
    return ziel.relative_to(PROJECT_ROOT).as_posix()


# ── HTML-Report (Phase-30-Style; statischer Generator ohne LLM wie pipeline/transcript_report.py).
# CSS: das gemeinsame Thema kommt aus `pipeline/bericht_stil.py` (P2-72), mit den Werten des
# geltenden Designs. Hier steht nur, worin der Aufräum-Bericht davon abweicht — so, dass er genauso
# aussieht wie vor der Umstellung (Leitentscheidung 8: nichts „bereinigen“). ───────────────────
#   * `.card table/th/td`, `ul.clean code` und das allgemeine `.kv` (12 px, gedämpft) gibt es nur hier,
#   * die Vorlage hat `.card p` (14 px, Abstand) und `.card .kv` (Großbuchstaben, fett): Der Bericht
#     setzt in Karten nackte `<p>` und `<span class="kv">` und sah immer ungestaltet aus. `revert` macht
#     diese Regeln für ihn wieder unsichtbar (Wert wie ohne Regel), `.kv` behält seine 12 px.
_CSS_ZUSATZ = """
.card table{font-size:13.5px} .card th{padding:4px 8px 8px 0} .card td{padding:3px 8px 3px 0}
ul.clean code{font-size:12.5px;background:var(--spur);padding:1px 5px;border-radius:4px}
.kv{font-size:12px;color:var(--muted)}
.card p{margin:revert;font-size:revert;color:revert}
.card p:last-child{margin-bottom:revert}
.card .kv{font-size:12px;font-weight:revert;text-transform:revert;letter-spacing:revert;margin:revert}
""" + DRUCK_SEITENFARBE_BEHALTEN + "\n"


def _css() -> str:
    """Das CSS des Berichts, bei jedem Aufruf mit dem Design, das gerade gilt."""
    return bericht_css(_CSS_ZUSATZ)


def _esc(s) -> str:
    return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _liste_html(eintraege, formatter, leer_text, limit=25) -> str:
    if not eintraege:
        return f"<p>{leer_text}</p>"
    zeilen = "".join(f"<li>{formatter(e)}</li>" for e in eintraege[:limit])
    rest = len(eintraege) - limit
    mehr = f"<li><i>… und {rest} weitere</i></li>" if rest > 0 else ""
    return f'<ul class="clean">{zeilen}{mehr}</ul>'


def _build_html(ergebnis: dict) -> str:
    erzeugt = ergebnis["erzeugt_am"][:16].replace("T", " ")
    orphans_html = _liste_html(
        ergebnis["orphans"]["dateien"],
        lambda o: (f'{_esc(o["pfad"])} <span class="kv">({_esc(o["ordner"])}, '
                  f'{o["groesse_bytes"] // 1024} KB, {o["alter_tage"]} Tage)</span>'),
        "Keine Orphan-Dateien gefunden.")
    dangling_html = _liste_html(
        ergebnis["dangling_referenzen"]["eintraege"],
        lambda d: f'{d["modell"]}#{d["id"]}.{d["feld"]} → <code>{_esc(d["pfad"])}</code> (Datei fehlt)',
        "Keine toten Referenzen gefunden.")
    rot_zeilen = "".join(
        f'<tr><td>{_esc(ordner)}</td><td>{info["anzahl"]}</td>'
        f'<td>{round(info["groesse_bytes"] / 1_000_000, 2)} MB</td></tr>'
        for ordner, info in ergebnis["rotation"]["je_ordner"].items()
    )
    meta_html = (
        f'<div><p class="k">Orphans</p><p class="v">{ergebnis["orphans"]["anzahl"]}</p></div>'
        f'<div><p class="k">Tote Referenzen</p><p class="v">{ergebnis["dangling_referenzen"]["anzahl"]}</p></div>'
        f'<div><p class="k">Rotierbar</p><p class="v">{ergebnis["rotation"]["anzahl"]}</p></div>'
        f'<div><p class="k">Im Papierkorb</p><p class="v">{ergebnis["papierkorb"]["anzahl"]}</p></div>'
        f'<div><p class="k">Datum</p><p class="v">{_esc(erzeugt)}</p></div>'
    )
    auffaellig_hinweis = (
        '<div class="caveat"><b>Auffällig:</b> Schwellenwert überschritten (&gt;50 MB rotierbar '
        'oder &gt;10 Orphans) — der Tageslauf würde das kurz erwähnen (löscht aber nie selbst).</div>'
        if ergebnis["auffaellig"] else ""
    )
    _FAVICON = favicon_link()      # P2-72: Icon des geltenden Designs, bei jedem Bericht frisch
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">{_FAVICON}
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>System-Cleanup · Analyse</title>
<style>{_css()}</style>
</head>
<body>
<div class="wrap">
  <header class="head">
    <p class="eyebrow">Analyse</p>
    <h1>System-Cleanup</h1>
    <p class="sub">scan · Ändert nichts — reiner Bericht (dry-run)</p>
    <div class="meta">{meta_html}</div>
  </header>

  {auffaellig_hinweis}

  <h2 class="sec">Orphan-Dateien ({ergebnis["orphans"]["anzahl"]} · {ergebnis["orphans"]["groesse_mb"]} MB)</h2>
  <div class="card">{orphans_html}</div>

  <h2 class="sec">Dangling-Referenzen ({ergebnis["dangling_referenzen"]["anzahl"]})</h2>
  <div class="card">{dangling_html}</div>

  <h2 class="sec">Rotation (Schwelle {ergebnis["rotation"]["schwelle_tage"]} Tage ·
    {ergebnis["rotation"]["anzahl"]} Dateien · {ergebnis["rotation"]["groesse_mb"]} MB)</h2>
  <div class="card">
    <table style="width:100%;border-collapse:collapse">
      <tr style="text-align:left;color:var(--muted)"><th>Ordner</th><th>Anzahl</th><th>Größe</th></tr>
      {rot_zeilen}
    </table>
  </div>

  <h2 class="sec">DB-Pflege (Schwelle {ergebnis["row_pflege"]["schwelle_tage"]} Tage)</h2>
  <div class="card"><p>{ergebnis["row_pflege"]["agenttask_kandidaten"]} AgentTask-Rows,
    {ergebnis["row_pflege"]["run_kandidaten"]} Run-Rows mit großen Feldern zu leeren
    (Rows selbst bleiben erhalten — Kosten-Historie).</p></div>

  <h2 class="sec">Papierkorb</h2>
  <div class="card"><p>{ergebnis["papierkorb"]["anzahl"]} Dateien · {ergebnis["papierkorb"]["groesse_mb"]} MB
    — läuft nie automatisch leer, s. <code>cleanup leeren</code>.</p></div>

  <div class="foot">
    <span>Bewerbungs-Mgmt · System-Cleanup · erzeugt am {erzeugt}</span>
    <span>scan — read-only, kein Löschen/Verschieben</span>
  </div>
</div>
</body>
</html>
"""


def _schreibe_html_report(ergebnis: dict) -> str:
    ordner = DATA / "analysen"
    ordner.mkdir(parents=True, exist_ok=True)
    # Bewusst KEINE Kollisions-Nummerierung (anders als Job-/Firma-Artefakte): ein erneuter
    # Scan am selben Tag überschreibt den Bericht des Tages (idempotent, kein Datei-Wildwuchs
    # bei mehreren Testläufen), analog dem bestehenden `2026_07_09_Absagen_Analyse.html`-Muster.
    fname = dated_filename("Analyse_Cleanup", "html")
    (ordner / fname).write_text(_build_html(ergebnis), encoding="utf-8")
    return f"data/analysen/{fname}"


# ── scan ─────────────────────────────────────────────────────────────────────────────────
def scan(rotate_days: int = _DEFAULT_ROTATE_DAYS, row_days: int = _DEFAULT_ROW_DAYS,
         html: bool = True) -> dict:
    init_db()
    with Session(engine) as session:
        referenzen = _alle_referenzen(session)
        referenz_menge = {pfad for (_, _, _, pfad) in referenzen}
        orphans = _orphan_kandidaten(referenz_menge)
        dangling = _dangling(referenzen)
        rotation = _rotation_kandidaten(session, rotate_days)
        row_pflege = _row_pflege_kandidaten(session, row_days)

    orphans_bytes = sum(o["groesse_bytes"] for o in orphans)
    ergebnis = {
        "erzeugt_am": datetime.utcnow().isoformat() + "Z",
        "orphans": {"anzahl": len(orphans), "groesse_bytes": orphans_bytes,
                   "groesse_mb": round(orphans_bytes / 1_000_000, 2), "dateien": orphans},
        "dangling_referenzen": {"anzahl": len(dangling), "eintraege": dangling},
        "rotation": rotation,
        "row_pflege": {"schwelle_tage": row_days,
                      "agenttask_kandidaten": len(row_pflege["agenttask_ids"]),
                      "run_kandidaten": len(row_pflege["run_ids"])},
        "papierkorb": _papierkorb_uebersicht(),
    }
    # Phase 64A / P1-7: dangling_referenzen fließt jetzt in die Alarmschwelle ein — das
    # Erkennungswerkzeug (_dangling oben) existierte bereits, wurde hier aber bisher nicht
    # ausgewertet. Schwelle bewusst NIEDRIGER als die 10 der Orphans: eine tote Referenz (DB
    # zeigt auf eine Datei, die es nicht mehr gibt — kaputte Oberfläche) ist sowohl seltener als
    # auch schwerer als eine verwaiste Datei (nur verschwendeter Speicher, DB bleibt korrekt).
    # Live-Bestand laut P1-7-Review: 0 von 455 verfolgten Pfadfeldern — schon eine kleine Anzahl
    # ist also anomal. > 3 (ab 4 Alarm) statt Zero-Tolerance, damit ein einzelner isolierter
    # Ausreißer nicht sofort den Tageslauf als „auffällig" markiert.
    ergebnis["auffaellig"] = (ergebnis["rotation"]["groesse_mb"] > 50
                              or ergebnis["orphans"]["anzahl"] > 10
                              or ergebnis["dangling_referenzen"]["anzahl"] > 3)
    if html:
        ergebnis["html_report"] = _schreibe_html_report(ergebnis)
    return ergebnis


# ── apply ────────────────────────────────────────────────────────────────────────────────
def apply(rotate_days: int = _DEFAULT_ROTATE_DAYS, row_days: int = _DEFAULT_ROW_DAYS,
         fix: bool = False, ja: bool = False, skip_orphans: bool = False,
         skip_rotation: bool = False) -> dict:
    """scan läuft IMMER zuerst (erzwungen, s. Modul-Docstring) — der Plan wird vor jeder
    Rückfrage gedruckt. Ohne --ja: interaktives y/N (nur im TTY möglich, sonst Abbruch)."""
    plan = scan(rotate_days=rotate_days, row_days=row_days, html=False)

    if not ja:
        if not sys.stdin.isatty():
            return {"abgebrochen": True, "plan": plan,
                    "grund": "apply braucht --ja (nicht-interaktiv) oder eine y/N-Bestätigung "
                             "im Terminal."}
        print(json.dumps(plan, ensure_ascii=False, indent=2, default=str))
        frage = (f"\n{plan['orphans']['anzahl']} Orphans, {plan['rotation']['anzahl']} "
                f"Rotations-Kandidaten{', Dangling-Fix aktiv' if fix else ''} → wirklich in den "
                f"Papierkorb verschieben (nie endgültig)? [y/N] ")
        if input(frage).strip().lower() != "y":
            return {"abgebrochen": True, "grund": "nicht bestätigt", "plan": plan}

    backup = _backup_db()
    ergebnis = {"backup": backup, "plan": plan}

    verschoben, fehler = [], []
    if not skip_orphans:
        for o in plan["orphans"]["dateien"]:
            try:
                ziel = _in_papierkorb(o["pfad"])
                if ziel:
                    verschoben.append({"von": o["pfad"], "papierkorb": ziel, "art": "orphan"})
            except OSError as e:
                fehler.append({"pfad": o["pfad"], "fehler": str(e)})
    if not skip_rotation:
        for d in plan["rotation"]["dateien"]:
            try:
                ziel = _in_papierkorb(d["pfad"])
                if ziel:
                    verschoben.append({"von": d["pfad"], "papierkorb": ziel, "art": "rotation"})
            except OSError as e:
                fehler.append({"pfad": d["pfad"], "fehler": str(e)})
    ergebnis["verschoben"] = verschoben
    if fehler:
        ergebnis["fehler"] = fehler

    with Session(engine) as session:
        if fix:
            referenzen = _alle_referenzen(session)
            dangling = _dangling(referenzen)
            for d in dangling:
                row = session.get(_MODELS[d["modell"]], d["id"])
                if row:
                    setattr(row, d["feld"], None)
                    session.add(row)
            session.commit()
            ergebnis["dangling_gefixt"] = len(dangling)
        if not skip_rotation:
            ergebnis["row_pflege"] = _row_pflege_ausfuehren(session, row_days)
    return ergebnis


# ── leeren ───────────────────────────────────────────────────────────────────────────────
def leeren(older_days: Optional[int], ja: bool = False) -> dict:
    """Der EINZIGE endgültig löschende Befehl im System. Rückfrage-Sperre: ohne --older-days
    oder mit --older-days < 30 wird NICHTS gelöscht (spec-hart, kein Default-Wert)."""
    init_db()
    if older_days is None:
        return {"verweigert": True,
               "grund": "--older-days ist Pflicht (kein Default) — ohne Angabe wird NICHTS gelöscht."}
    if older_days < _MIN_LEEREN_DAYS:
        return {"verweigert": True,
               "grund": f"--older-days muss >= {_MIN_LEEREN_DAYS} sein (übergeben: {older_days}) — "
                        "endgültiges Löschen braucht einen Sicherheitsabstand."}
    if not PAPIERKORB.is_dir():
        return {"geloescht": 0, "freigegeben_mb": 0.0, "hinweis": "Papierkorb existiert nicht (leer)."}

    kandidaten = sorted(p for p in PAPIERKORB.rglob("*")
                        if p.is_file() and not p.name.startswith(".")
                        and _papierkorb_alter_tage(p) > older_days)
    if not kandidaten:
        return {"geloescht": 0, "freigegeben_mb": 0.0,
               "hinweis": f"Keine Papierkorb-Datei älter als {older_days} Tage."}

    gesamt_bytes = sum(p.stat().st_size for p in kandidaten)
    if not ja:
        if not sys.stdin.isatty():
            return {"abgebrochen": True,
                   "grund": "leeren braucht --ja (nicht-interaktiv) oder eine y/N-Bestätigung im Terminal.",
                   "kandidaten": [p.relative_to(PROJECT_ROOT).as_posix() for p in kandidaten]}
        print(f"{len(kandidaten)} Dateien ({round(gesamt_bytes / 1_000_000, 2)} MB) älter als "
             f"{older_days} Tage werden ENDGÜLTIG gelöscht:")
        for p in kandidaten:
            print(f"  - {p.relative_to(PROJECT_ROOT).as_posix()}")
        if input("\nWirklich endgültig löschen (nicht umkehrbar)? [y/N] ").strip().lower() != "y":
            return {"abgebrochen": True, "grund": "nicht bestätigt"}

    backup = _backup_db()
    for p in kandidaten:
        p.unlink()

    with engine.connect() as conn:
        conn.exec_driver_sql("VACUUM")
        conn.commit()
    try:
        from pipeline import search_index
        fts_ergebnis = search_index.rebuild()
    except Exception as e:  # noqa: BLE001 — Leeren ist bereits erfolgreich, FTS-Rebuild ist Kür
        fts_ergebnis = {"fehler": str(e)}

    return {"geloescht": len(kandidaten), "freigegeben_mb": round(gesamt_bytes / 1_000_000, 2),
           "backup": backup, "vacuum": True, "fts_rebuild": fts_ergebnis}


# ── CLI ──────────────────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(prog="pipeline.cleanup")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_s = sub.add_parser("scan", help="Bericht, ändert nichts")
    p_s.add_argument("--rotate-days", type=int, default=_DEFAULT_ROTATE_DAYS)
    p_s.add_argument("--row-days", type=int, default=_DEFAULT_ROW_DAYS)
    p_s.add_argument("--no-html", action="store_true", help="keinen HTML-Report schreiben")

    p_a = sub.add_parser("apply", help="Orphans+Rotation → Papierkorb; Dangling nur mit --fix")
    p_a.add_argument("--ja", action="store_true", help="ohne interaktive Rückfrage ausführen")
    p_a.add_argument("--fix", action="store_true", help="Dangling-Pfadfelder zusätzlich nullen")
    p_a.add_argument("--rotate-days", type=int, default=_DEFAULT_ROTATE_DAYS)
    p_a.add_argument("--row-days", type=int, default=_DEFAULT_ROW_DAYS)
    p_a.add_argument("--skip-orphans", action="store_true")
    p_a.add_argument("--skip-rotation", action="store_true")

    p_l = sub.add_parser("leeren", help="Papierkorb ENDGÜLTIG leeren (einziger harter Löschbefehl)")
    p_l.add_argument("--older-days", type=int, default=None, help="Pflicht, muss >= 30 sein")
    p_l.add_argument("--ja", action="store_true")

    a = ap.parse_args()
    if a.cmd == "scan":
        out = scan(rotate_days=a.rotate_days, row_days=a.row_days, html=not a.no_html)
    elif a.cmd == "apply":
        out = apply(rotate_days=a.rotate_days, row_days=a.row_days, fix=a.fix, ja=a.ja,
                   skip_orphans=a.skip_orphans, skip_rotation=a.skip_rotation)
    else:
        out = leeren(a.older_days, ja=a.ja)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    if isinstance(out, dict) and out.get("verweigert"):
        raise SystemExit(2)   # klarer Exit-Code für Skripte/Tageslauf: "verweigert", kein Crash


if __name__ == "__main__":
    main()
