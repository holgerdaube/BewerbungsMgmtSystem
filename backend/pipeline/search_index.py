#!/usr/bin/env python3
"""Volltextsuche über das gesamte BMS (Phase 25). Ergebnis ist immer eine STELLE.

Der Index ist eine ABGELEITETE SICHT — kein Write-Trigger an zehn Stellen, sondern komplett neu
baubar (`rebuild`), deterministisch und idempotent. `built_at` macht Staleness sichtbar statt sie
zu verstecken. Ein Dokument je (job_id × Quelle): stelle, stellenbeschreibung, company-fit,
transkript, debrief, briefing, match, ats, verlauf. Company-Fit wird je Firma EINMAL gelesen/
gestrippt, aber auf jeden Job der Firma abgebildet (Duplikat-Dokumente sind ok, Datenmenge winzig).

BEWUSST NICHT indexiert: .docx-Inhalte (CV/Anschreiben, binär), Netzwerk/Kontakte/Outreach
(Ergebnis der Suche soll eine Stelle sein — deren Suche wäre ein anderes Feature).

CLI (aus backend/):
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.search_index rebuild
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.search_index query "frankfurt saas"   # Debug
"""
import datetime
import json
import re
import sys
import time
from pathlib import Path

from sqlmodel import Session, select

from app.db import artefakt_pfad, engine
from app.models import Company, CVVersion, Interview, Job, JobLog, Transcript
from app.naming import _TRANSLIT
from pipeline.htmltext import entkleiden

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Bewerbung_Mgmt_System/

_STELLE_FELDER = [
    ("Firma", "company_name"), ("Titel", "title"), ("Ort", "location"),
    ("Seniorität", "seniority_raw"), ("Status", "status"), ("Gehalt", "salary"),
    ("Bewertung", "match_rationale"), ("Notizen", "notes"), ("Nächster Schritt", "next_step"),
    ("Quelle", "source_note"), ("Verifikation", "verify_note"),
]


def _init(conn) -> None:
    """Virtuelle FTS5-Tabelle + Meta-Tabelle anlegen. NICHT in db.py::init_db — gehört diesem
    Modul (Kommentar dort, damit niemand die Tabelle „vermisst")."""
    conn.exec_driver_sql(
        "CREATE VIRTUAL TABLE IF NOT EXISTS suchindex USING fts5("
        "inhalt, quelle UNINDEXED, job_id UNINDEXED, "
        "tokenize='unicode61 remove_diacritics 2')"
    )
    conn.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS suchindex_meta ("
        "id INTEGER PRIMARY KEY CHECK (id=1), built_at TEXT, dokumente INTEGER, hinweis TEXT)"
    )


_JS_STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _js_strings(html_text: str) -> str:
    """Fallback für clientseitig gerenderte Dashboards: der `company-fit-analysis`-Skill (anders
    als die Phase-24/25-Artefakte briefing/snapshot/debrief, die statisches HTML schreiben)
    rendert den GESAMTEN Inhalt aus einem <script>const DATA = {...}</script>-Objekt in ein
    leeres <div id="root"> — entkleiden() entfernt <script> komplett (richtig für Gmail-Bodies,
    wo Script = Tracking-Müll), liefert hier also NICHTS (verifiziert: alle 24 vorhandenen
    Company-Fit-Dashboards nutzen dieses Muster). Deshalb zusätzlich alle String-Literale aus
    <script>-Blöcken ziehen (das JS-Objekt ist kein strict JSON — unquotete Keys — aber die WERTE
    sind doppelt gequotete Strings). Ein paar CSS-Klassennamen als Rauschen im Index sind
    unkritisch; eine komplett fehlende Dashboard-Analyse wäre der eigentliche Fehler."""
    teile = []
    for block in re.findall(r"(?is)<script\b[^>]*>(.*?)</script>", html_text):
        for m in _JS_STRING_RE.finditer(block):
            s = m.group(1)
            if len(s) < 3:
                continue
            s = s.replace('\\"', '"').replace("\\n", " ").replace("\\/", "/").replace("\\\\", "\\")
            teile.append(s)
    return "\n".join(teile)


def _lies_html(rel_path: str) -> str:
    p = artefakt_pfad(rel_path)
    # Phase 79: gemeinsame Auflösung (data/ → aktive Datenwurzel) statt PROJECT_ROOT — s. app/db.py::artefakt_pfad
    if not p.is_file():
        return ""
    raw = p.read_text(encoding="utf-8", errors="replace")
    text = entkleiden(raw)
    js = _js_strings(raw)
    if js:
        text = f"{text}\n{js}".strip() if text else js
    return text


def _lies_text(rel_path: str) -> str:
    p = artefakt_pfad(rel_path)
    # Phase 79: gemeinsame Auflösung (data/ → aktive Datenwurzel) statt PROJECT_ROOT — s. app/db.py::artefakt_pfad
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


# ß-Faltung (Phase 67B, P2-11): FTS5 läuft mit `remove_diacritics 2` — das faltet Kombinations-
# zeichen (ä/ö/ü → a/o/u), aber ß ist ein EIGENSTÄNDIGES Unicode-Zeichen (kein Grundbuchstabe +
# Kombinationszeichen) und bleibt unangetastet. „Großkunden" und „Grosskunden" landen deshalb
# heute als zwei verschiedene Tokens im Index — eine Suche nach dem einen findet das andere
# nicht. Fix: dieselbe ß→ss-Abbildung wie bei Dateinamen (naming._TRANSLIT — hier bewusst NUR
# das ß-Paar genutzt, nicht die volle Umlaut-Transliteration, die ist ein anderes Thema) auf
# den Text VOR dem Indexieren UND auf die Nutzereingabe VOR dem Suchen anwenden. Beides ist
# nötig: nur beim Indexieren zu falten hilft ausschließlich Anfragen mit "ss"; nur beim Suchen
# zu falten hilft ausschließlich, wenn der Index noch echtes ß enthält. Nebeneffekt (bewusst in
# Kauf genommen, kein Bug): Snippets für ß-Wörter zeigen danach "ss" statt "ß" — ein kleiner,
# gut lesbarer Kompromiss (identisch zur Schweizer Rechtschreibung) für eine funktionierende
# Suche in beide Richtungen, ohne ein zweites FTS5-Spalten-Schema einzuführen.
_ESZETT = _TRANSLIT["ß"]  # "ss" — aus naming.py übernommen statt dupliziert


def _fold_esszett(text: str) -> str:
    if "ß" not in text and "ẞ" not in text:
        return text
    return text.replace("ß", _ESZETT).replace("ẞ", _ESZETT.upper())


def _insert(conn, quelle: str, job_id: int, inhalt: str) -> None:
    """EINZIGE Stelle, die in den Suchindex schreibt (P2-11) — alle neun Aufrufer in
    `rebuild()` gehen hierüber, damit keiner die ß-Faltung vergessen kann."""
    conn.exec_driver_sql(
        "INSERT INTO suchindex (inhalt, quelle, job_id) VALUES (?, ?, ?)",
        (_fold_esszett(inhalt), quelle, job_id),
    )


def rebuild() -> dict:
    """Index komplett neu bauen (Sekunden bei ~200 Jobs). Fehlende Dateien überspringen,
    aber zählen — niemals crashen, nur weniger indexieren."""
    start = time.time()
    dokumente = 0
    fehlende_dateien = 0
    company_fit_cache: dict[int, str] = {}   # company_id -> gestrippter Text (einmal je Firma)

    with Session(engine) as s:
        conn = s.connection()   # Session hat KEIN exec_driver_sql, nur Connection — raw SQL läuft
                                 # hierüber, ORM-Reads über s.exec(select(...)), eine Transaktion.
        _init(conn)
        conn.exec_driver_sql("DELETE FROM suchindex")

        jobs = s.exec(select(Job).where(Job.deleted_at.is_(None))).all()   # Phase 32 B — Tombstones nicht indexieren
        for job in jobs:
            company = s.get(Company, job.company_id) if job.company_id else None

            # ── stelle ──────────────────────────────────────────────────────────────
            zeilen = []
            for label, feld in _STELLE_FELDER:
                wert = getattr(job, feld, None)
                if wert:
                    zeilen.append(f"{label}: {wert}")
            if zeilen:
                _insert(conn, "stelle", job.id, "\n".join(zeilen))
                dokumente += 1

            # ── stellenbeschreibung ─────────────────────────────────────────────────
            text = ""
            if job.posting_snapshot_path:
                text = _lies_html(job.posting_snapshot_path)
                if not text:
                    fehlende_dateien += 1
            if not text and job.raw_json:
                text = job.raw_json          # Fallback: Roh-Record der Suche (Evidence-Text)
            if text:
                _insert(conn, "stellenbeschreibung", job.id, text)
                dokumente += 1

            # ── company-fit (je Firma einmal gelesen, auf jeden ihrer Jobs abgebildet) ─
            if company and company.fit_analysis_path:
                if company.id not in company_fit_cache:
                    txt = _lies_html(company.fit_analysis_path)
                    if not txt:
                        fehlende_dateien += 1
                    company_fit_cache[company.id] = txt
                txt = company_fit_cache[company.id]
                if txt:
                    _insert(conn, "company-fit", job.id, txt)
                    dokumente += 1

            # ── transkript + debrief (mehrere Transkripte je Job → je Quelle EIN Dokument) ─
            transkripte = s.exec(select(Transcript).where(Transcript.job_id == job.id)).all()
            tk_teile, db_teile = [], []
            for t in transkripte:
                if t.file_path:
                    txt = _lies_text(t.file_path)
                    if txt:
                        tk_teile.append(txt)
                    else:
                        fehlende_dateien += 1
                # report_path (Phase 30, Transkript-Report) nur als Quelle 'debrief' mitindexieren,
                # wenn debrief_path FEHLT — sonst doppelt (Alt-Debriefs behalten debrief_path, neue
                # Transkripte haben nur report_path; beide bilden dieselbe Auswertungs-Quelle ab).
                debrief_quelle = t.debrief_path or t.report_path
                if debrief_quelle:
                    txt = _lies_html(debrief_quelle)
                    if txt:
                        db_teile.append(txt)
                    else:
                        fehlende_dateien += 1
            if tk_teile:
                _insert(conn, "transkript", job.id, "\n\n".join(tk_teile))
                dokumente += 1
            if db_teile:
                _insert(conn, "debrief", job.id, "\n\n".join(db_teile))
                dokumente += 1

            # ── briefing (mehrere Interviews je Job möglich) ───────────────────────────
            interviews = s.exec(select(Interview).where(Interview.job_id == job.id)).all()
            br_teile = []
            for iv in interviews:
                if iv.prep_path:
                    txt = _lies_html(iv.prep_path)
                    if txt:
                        br_teile.append(txt)
                    else:
                        fehlende_dateien += 1
            if br_teile:
                _insert(conn, "briefing", job.id, "\n\n".join(br_teile))
                dokumente += 1

            # ── match/ats (CV-Match-Dashboard + ATS-Scan, mehrere CV-Versionen je Job möglich;
            # Phase 30 — bisher NICHT indexiert gewesen, Lücke geschlossen: Stufe-B-Verifikation der
            # Spec verlangt explizit FTS-Auffindbarkeit für neu erzeugte Match-/ATS-Reports) ────────
            cvversions = s.exec(select(CVVersion).where(CVVersion.job_id == job.id)).all()
            match_teile, ats_teile = [], []
            for cv in cvversions:
                if cv.match_dashboard_path:
                    txt = _lies_html(cv.match_dashboard_path)
                    if txt:
                        match_teile.append(txt)
                    else:
                        fehlende_dateien += 1
                if cv.ats_scan_path:
                    txt = _lies_html(cv.ats_scan_path)
                    if txt:
                        ats_teile.append(txt)
                    else:
                        fehlende_dateien += 1
            if match_teile:
                _insert(conn, "match", job.id, "\n\n".join(match_teile))
                dokumente += 1
            if ats_teile:
                _insert(conn, "ats", job.id, "\n\n".join(ats_teile))
                dokumente += 1

            # ── verlauf (JobLog, Phase 24 — falls Tabelle fehlt: Quelle einfach auslassen) ─
            try:
                logs = s.exec(select(JobLog).where(JobLog.job_id == job.id)).all()
            except Exception:                # noqa: BLE001 — Tabelle evtl. noch nicht migriert
                logs = []
            if logs:
                inhalt = "\n".join(l.eintrag for l in logs if l.eintrag)
                if inhalt:
                    _insert(conn, "verlauf", job.id, inhalt)
                    dokumente += 1

        built_at = datetime.datetime.utcnow().isoformat() + "Z"
        conn.exec_driver_sql(
            "INSERT INTO suchindex_meta (id, built_at, dokumente, hinweis) VALUES (1, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET built_at=excluded.built_at, dokumente=excluded.dokumente, "
            "hinweis=excluded.hinweis",
            (built_at, dokumente, None),
        )
        s.commit()

    return {
        "jobs": len(jobs), "dokumente": dokumente, "fehlende_dateien": fehlende_dateien,
        "dauer_s": round(time.time() - start, 2), "built_at": built_at,
    }


def _escape_query(q: str) -> str:
    """Nutzereingabe FTS5-sicher machen: jedes Wort als escapte Phrase (Anführungszeichen im Wort
    verdoppeln), Wörter implizit UND-verknüpft (FTS5-Default bei Leerzeichen), Präfix-Match (`*`)
    nur am letzten Wort — tippfreundlich für die Live-Suche. Macht Sonderzeichen/Operatoren
    (AND OR NOT ( ) : *) IMMER zu literalem Text, nie zu FTS5-Syntax → kein Crash, keine Injektion."""
    woerter = [w for w in re.split(r"\s+", q.strip()) if w]
    if not woerter:
        return ""
    terme = [f'"{w.replace(chr(34), chr(34) * 2)}"' for w in woerter]
    terme[-1] += "*"
    return " ".join(terme)


def meta() -> dict:
    with Session(engine) as s:
        conn = s.connection()
        _init(conn)
        row = conn.exec_driver_sql(
            "SELECT built_at, dokumente, hinweis FROM suchindex_meta WHERE id=1"
        ).first()
    if not row:
        return {"built_at": None, "dokumente": 0, "hinweis": "Index noch nicht gebaut"}
    return {"built_at": row[0], "dokumente": row[1], "hinweis": row[2]}


def query(q: str, limit: int = 30) -> dict:
    """Treffer nach Job gruppiert, bester bm25-Score zuerst, je Job max. 3 Quellen-Snippets."""
    m = meta()
    if not m["built_at"]:
        return {"q": q, "built_at": None, "ergebnisse": [], "hinweis": m["hinweis"]}

    # ß-Faltung (P2-11) — dieselbe Abbildung wie beim Indexieren (_insert), sonst hilft die
    # Index-seitige Faltung nur einer Richtung. `q` selbst bleibt unangetastet (Echo im Ergebnis
    # soll zeigen, was der Nutzer wirklich eingegeben hat).
    fts_q = _escape_query(_fold_esszett(q))
    if not fts_q:
        return {"q": q, "built_at": m["built_at"], "ergebnisse": []}

    with Session(engine) as s:
        conn = s.connection()
        try:
            rows = conn.exec_driver_sql(
                "SELECT job_id, quelle, "
                "snippet(suchindex, 0, '<mark>', '</mark>', '…', 12) AS snip, "
                "bm25(suchindex) AS score "
                "FROM suchindex WHERE suchindex MATCH ? "
                "ORDER BY score LIMIT 500",
                (fts_q,),
            ).all()
        except Exception as e:                # noqa: BLE001 — FTS5-Syntaxfehler nie crashen lassen
            return {"q": q, "built_at": m["built_at"], "ergebnisse": [], "fehler": str(e)}

    je_job: dict[int, dict] = {}
    for job_id, quelle, snip, score in rows:
        eintrag = je_job.setdefault(job_id, {"job_id": job_id, "score": score, "treffer": []})
        eintrag["score"] = min(eintrag["score"], score)
        if len(eintrag["treffer"]) < 3:
            eintrag["treffer"].append({"quelle": quelle, "snippet": snip})

    geordnet = sorted(je_job.values(), key=lambda e: e["score"])[:limit]
    return {"q": q, "built_at": m["built_at"], "ergebnisse": geordnet}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Nutzung: python -m pipeline.search_index rebuild | query \"<begriff>\"")
    cmd = sys.argv[1]
    if cmd == "rebuild":
        print(json.dumps(rebuild(), ensure_ascii=False, indent=2))
    elif cmd == "query":
        if len(sys.argv) < 3:
            sys.exit("Nutzung: python -m pipeline.search_index query \"<begriff>\"")
        print(json.dumps(query(sys.argv[2]), ensure_ascii=False, indent=2))
    else:
        sys.exit(f"Unbekanntes Kommando: {cmd}")
