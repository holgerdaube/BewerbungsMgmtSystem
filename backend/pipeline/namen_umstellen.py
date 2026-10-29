#!/usr/bin/env python3
"""P2-63 (Vertrag U) — Umbenennung des Dateibestands auf die kurze Namenskonvention.

Einmal-Werkzeug. Quelle der Wahrheit ist die DB: Für jedes Pfadfeld wird der Zielname mit den
Helfern aus `app.naming` gebildet (nie eigene Namenslogik, damit Werkzeug und Code dieselben Namen
erzeugen). Gekoppelt umbenannt werden CV und Anschreiben (.docx + .pdf), der Beirats-Check
(HTML + `<stamm>_rohdaten.json` + JobFile + `dashboard_pfad` in den Debatten-JSON) und der
Transkript-Upload (JobFile UND Transcript zeigen auf dieselbe Datei). Uploads, Analysen, Exporte
und Digests bekommen nur das neue Datumsformat (`JJJJ_MM_TT_` -> `JJJJMMTT_`). Links in HTML auf
alte Pfade (auch `/api/artifact?path=` URL-kodiert) werden ersetzt.

NIE angefasst: Papierkorb, Sicherungen, Migrationsarchive, tmp, cv_basis, CV-Entwürfe,
Persona-Backups, Agent-Logs, Namen der Debatten-JSON. Nicht umgeschrieben (Historie):
AgentTask.result_json/prompt, JobChat, JobLog, Notizen.

CLI (im Ordner backend):
    python -m pipeline.namen_umstellen --probe [--bericht <pfad.json>]
    python -m pipeline.namen_umstellen --ausfuehren
    python -m pipeline.namen_umstellen --zurueck <protokoll.json>
Optional `--projekt-root` und `--daten-dir` (Standard: Werte aus app.db, im Rumpf aufgelöst).
Exit 0 = ok, 1 = Fehler (mit vollständiger Rücknahme), 2 = Abbruch vor dem ersten Eingriff.
"""
import argparse
import datetime
import json
import os
import posixpath
import re
import shutil
import sqlite3
import sys
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote

# ── Konfiguration ────────────────────────────────────────────────────────────────────────
# Ordner (projekt-relativ, "data/…" liegt unter dem Datenordner, alles andere unter dem Projekt-
# Root), in denen DB-Referenzen umbenannt werden dürfen.
ARTEFAKT_WURZELN = (
    "data/company_fit", "data/job_postings", "data/interview_prep", "data/beirat",
    "data/analysen", "data/transcripts", "data/job_files", "data/profil/dateien",
    "outputs/cv", "outputs/anschreiben",
)
# Ordner, deren Dateien auch OHNE DB-Bezug nur das Datumsformat bekommen.
DATUM_WURZELN = (
    "data/analysen", "data/digests", "data/exports", "outputs/exports", "data/mail_alerts",
)
# Ordner, in denen HTML-Links auf alte Pfade ersetzt werden.
LINK_WURZELN = (
    "data/company_fit", "data/job_postings", "data/interview_prep", "data/beirat",
    "data/analysen", "data/transcripts", "data/digests", "data/exports", "outputs/exports",
)
# Nie anfassen (Präfix-Vergleich auf dem projekt-relativen Pfad).
AUSGENOMMEN = (
    "data/papierkorb", "data/backups", "data/_migration_", "data/tmp", "data/cv_basis",
    # Abnahme P2-63: Kopien für die Coach-Site, verlinkt über den blanken Namen; jeder Export
    # erzeugt den Ordner neu, Umbenennen hier ließe nur die Links der lokalen Kopie ins Leere zeigen.
    "data/exports/coach_site",
    "outputs/cv_entwuerfe", "data/beirat/personas_backup", "data/agent_logs",
    "data/job_files/_geloescht",
)

_ALTES_DATUM_RE = re.compile(r"^(\d{4})_(\d{2})_(\d{2})_(.+)$", re.S)
_DATUM_ALT_RE = re.compile(r"(?<!\d)(\d{4})_(\d{2})_(\d{2})(?!\d)")
_DATUM_NEU_RE = re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)")
_LINK_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:data|outputs)(?:/|%2[Ff])[^\"'<>\s]*?"
    r"\.[A-Za-z0-9]{2,5}(?![A-Za-z0-9_\-.])"
)
_LINK_DATEIEN = (".html", ".htm")
_STAMM_SICHERUNG = "vor_p2-63_"
_STAMM_PROTOKOLL = "namen_p2-63_"
_MAX_KOLLISION = 500


# ── Pfad-Helfer ──────────────────────────────────────────────────────────────────────────
def _norm(rel) -> str:
    s = str(rel or "").strip().replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return s.lstrip("/")


def _abs(rel: str, root: Path, daten: Path) -> Path:
    """Wie app.db.artefakt_pfad, aber mit den übergebenen Wurzeln (nie die globalen)."""
    if rel.startswith("data/"):
        return daten / rel[len("data/"):]
    return root / rel


def _rel(p: Path, root: Path, daten: Path) -> Optional[str]:
    try:
        return "data/" + p.relative_to(daten).as_posix()
    except ValueError:
        pass
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        return None


def _ausgenommen(rel: str) -> bool:
    return any(rel == a or rel.startswith(a + "/") or (a.endswith("_") and rel.startswith(a))
               for a in AUSGENOMMEN)


def _wurzel(rel: str) -> Optional[str]:
    for w in ARTEFAKT_WURZELN + DATUM_WURZELN:
        if rel.startswith(w + "/"):
            return w
    return None


def _datum_ok(j, m, t) -> Optional[datetime.date]:
    try:
        return datetime.date(int(j), int(m), int(t))
    except ValueError:
        return None


def _datum_aus_name(name: str) -> Optional[datetime.date]:
    """Datum aus dem alten ODER neuen Namen (beide Formate), sonst None."""
    for rx in (_DATUM_ALT_RE, _DATUM_NEU_RE):
        m = rx.search(name)
        if m:
            d = _datum_ok(*m.groups())
            if d:
                return d
    return None


def _datum_aus_text(s) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(str(s or "").strip()[:10])
    except ValueError:
        return None


def _datum_kurz(name: str) -> str:
    """Reine Datumsumstellung `JJJJ_MM_TT_rest` -> `JJJJMMTT_rest`; ohne Datumspräfix unverändert."""
    m = _ALTES_DATUM_RE.match(name)
    if m and _datum_ok(*m.groups()[:3]):
        return f"{m.group(1)}{m.group(2)}{m.group(3)}_{m.group(4)}"
    return name


def _suffix(name: str) -> str:
    return Path(name).suffix


def _name_n(base: str, rest: str, n: int) -> str:
    return base + ("" if n == 1 else f"_{n}") + rest


# ── Plan ─────────────────────────────────────────────────────────────────────────────────
class _Plan:
    """Berechnet alle Umbenennungen, DB-Änderungen und Link-Ersetzungen, ohne etwas zu ändern."""

    def __init__(self, con: sqlite3.Connection, root: Path, daten: Path):
        self.con, self.root, self.daten = con, root, daten
        self.refs = []            # (tabelle, id, feld, roh, rel)
        self.gruppen = []         # {"ordner", "mitglieder": [(rel, base, rest)]}
        self.gruppe_von = {}      # rel -> Gruppenindex
        self.fehlend, self.ausgenommen, self.mehrfach = [], [], []
        self.kollisionen = []
        self.umbenennungen = []   # {"von","nach","quelle"}
        self.endname = {}         # rel -> neues rel (nur Änderungen)
        self.quelle = {}          # rel -> Beschreibung
        self.db = []              # {"tabelle","id","feld","alt","neu"}
        self._vorhanden_cache = {}

    # -- Eingabe -----------------------------------------------------------------------
    def tabelle(self, name: str) -> dict:
        try:
            self.con.row_factory = sqlite3.Row
            return {r["id"]: dict(r) for r in self.con.execute(f"SELECT * FROM {name} ORDER BY id")}
        except sqlite3.Error:
            return {}

    def _pruefe(self, tab, pk, feld, roh) -> Optional[str]:
        rel = _norm(roh)
        if not rel:
            return None
        if _ausgenommen(rel) or _wurzel(rel) is None:
            self.ausgenommen.append({"tabelle": tab, "id": pk, "feld": feld, "pfad": rel})
            return None
        if not _abs(rel, self.root, self.daten).is_file():
            self.fehlend.append({"tabelle": tab, "id": pk, "feld": feld, "pfad": rel})
            return None
        return rel

    def gruppiere(self, tab, pk, eintraege, quelle):
        """eintraege: [(feld, roh, base, rest)] eines Datensatzes; Mitglieder je Ordner gruppiert
        (gemeinsamer Stamm, gemeinsame Kollisionsnummer)."""
        je_ordner = {}
        for feld, roh, base, rest in eintraege:
            rel = self._pruefe(tab, pk, feld, roh)
            if rel is None:
                continue
            self.refs.append((tab, pk, feld, roh, rel))
            if rel in self.gruppe_von:
                self.mehrfach.append({"pfad": rel, "tabelle": tab, "id": pk, "feld": feld})
                continue
            je_ordner.setdefault(posixpath.dirname(rel), []).append((rel, base, rest))
        for ordner, mitglieder in je_ordner.items():
            self._neue_gruppe(ordner, mitglieder, quelle)

    def _neue_gruppe(self, ordner, mitglieder, quelle):
        idx = len(self.gruppen)
        self.gruppen.append({"ordner": ordner, "mitglieder": mitglieder, "quelle": quelle})
        for rel, _b, _r in mitglieder:
            self.gruppe_von[rel] = idx
            self.quelle[rel] = quelle

    # -- Namensvergabe -----------------------------------------------------------------
    def _vorhanden(self, ordner_rel: str) -> set:
        if ordner_rel not in self._vorhanden_cache:
            p = _abs(ordner_rel, self.root, self.daten)
            self._vorhanden_cache[ordner_rel] = (
                {n.name.casefold() for n in p.iterdir() if n.is_file()} if p.is_dir() else set())
        return self._vorhanden_cache[ordner_rel]

    def vergeben(self):
        reserviert = {}                       # ordner -> casefold-Namen
        bleiber, wanderer = [], []
        for idx, g in enumerate(self.gruppen):
            n_ok = next((n for n in range(1, _MAX_KOLLISION)
                         if all(_name_n(b, r, n) == posixpath.basename(rel)
                                for rel, b, r in g["mitglieder"])), None)
            (bleiber if n_ok else wanderer).append((idx, n_ok))
        for idx, n in bleiber:
            g = self.gruppen[idx]
            res = reserviert.setdefault(g["ordner"], set())
            for rel, b, r in g["mitglieder"]:
                res.add(_name_n(b, r, n).casefold())
        quellen = {}
        for idx, _n in wanderer:
            g = self.gruppen[idx]
            q = quellen.setdefault(g["ordner"], set())
            for rel, _b, _r in g["mitglieder"]:
                q.add(posixpath.basename(rel).casefold())
        for idx, _n in wanderer:
            g = self.gruppen[idx]
            ordner = g["ordner"]
            res = reserviert.setdefault(ordner, set())
            gesperrt_platte = self._vorhanden(ordner) - quellen.get(ordner, set())
            for n in range(1, _MAX_KOLLISION):
                namen = [_name_n(b, r, n) for _rel, b, r in g["mitglieder"]]
                if all(x.casefold() not in res and x.casefold() not in gesperrt_platte for x in namen):
                    break
            else:
                raise RuntimeError(f"Keine freie Namensnummer in {ordner}")
            for x in namen:
                res.add(x.casefold())
            for (rel, b, r), neu in zip(g["mitglieder"], namen):
                neu_rel = posixpath.join(ordner, neu)
                if neu_rel != rel:
                    self.endname[rel] = neu_rel
                    self.umbenennungen.append({"von": rel, "nach": neu_rel, "quelle": g["quelle"]})
                    if n > 1:
                        self.kollisionen.append({"alt": rel, "nach": neu_rel, "nummer": n})

    # -- DB-Änderungen -----------------------------------------------------------------
    def db_aenderungen(self, zeilen):
        gesehen = set()
        for tab, pk, feld, roh, rel in self.refs:
            neu = self.endname.get(rel)
            if not neu:
                continue
            if (tab, pk, feld) not in gesehen:
                gesehen.add((tab, pk, feld))
                self.db.append({"tabelle": tab, "id": pk, "feld": feld, "alt": roh, "neu": neu})
            if tab in ("jobfile", "profilefile"):
                fn = zeilen[tab][pk].get("filename")
                if fn == posixpath.basename(rel) and (tab, pk, "filename") not in gesehen:
                    gesehen.add((tab, pk, "filename"))
                    self.db.append({"tabelle": tab, "id": pk, "feld": "filename",
                                    "alt": fn, "neu": posixpath.basename(neu)})

    def karte(self) -> dict:
        return dict(self.endname)


def _firma(job: dict, firmen: dict) -> str:
    return (job.get("company_name") or (firmen.get(job.get("company_id")) or {}).get("name") or "")


def _plan_bauen(con, root: Path, daten: Path) -> _Plan:
    from app.naming import (cover_letter_filename, cv_filename, report_filename,
                            transcript_filename)

    p = _Plan(con, root, daten)
    firmen = p.tabelle("company")
    jobs = p.tabelle("job")
    bewerbungen = p.tabelle("application")
    cvs = p.tabelle("cvversion")
    gespraeche = p.tabelle("interview")
    transkripte = p.tabelle("transcript")
    jobfiles = p.tabelle("jobfile")
    profilfiles = p.tabelle("profilefile")

    def datum(roh, *fallbacks) -> datetime.date:
        d = _datum_aus_name(posixpath.basename(_norm(roh)))
        for f in fallbacks:
            if d:
                break
            d = _datum_aus_text(f)
        if d:
            return d
        pfad = _abs(_norm(roh), root, daten)
        try:
            return datetime.date.fromtimestamp(pfad.stat().st_mtime)
        except OSError:
            return datetime.date.today()

    def bericht(tab, row, feld, typ, job, runde=None, mit_rolle=True, *dbdatum):
        roh = row.get(feld)
        if not roh:
            return
        d = datum(roh, *dbdatum)
        base = report_filename(typ, _firma(job, firmen), job.get("title") if mit_rolle else None,
                               when=d, runde=runde)
        p.gruppiere(tab, row["id"], [(feld, roh, base, _suffix(roh))], f"{tab}.{feld}")

    for c in firmen.values():
        roh = c.get("fit_analysis_path")
        if roh:
            d = datum(roh, c.get("created_at"))
            base = report_filename("CompanyFit", c.get("name") or "", None, when=d)
            p.gruppiere("company", c["id"], [("fit_analysis_path", roh, base, _suffix(roh))],
                        "company.fit_analysis_path")

    for j in jobs.values():
        bericht("job", j, "posting_snapshot_path", "Anzeige", j, None, True, j.get("created_at"))

    for a in bewerbungen.values():
        job = jobs.get(a.get("job_id"))
        if not job:
            continue
        paare = []
        stamm = None
        for feld in ("cover_letter_path", "cover_letter_pdf_path"):
            roh = a.get(feld)
            if roh:
                if stamm is None:
                    stamm = cover_letter_filename(_firma(job, firmen), job.get("title") or "",
                                                  a.get("cover_letter_language"))
                paare.append((feld, roh, stamm, _suffix(roh)))
        if paare:
            p.gruppiere("application", a["id"], paare, "application.cover_letter")

    for v in cvs.values():
        job = jobs.get(v.get("job_id"))
        if not job:
            continue
        stamm = cv_filename(_firma(job, firmen), job.get("title") or "", v.get("language"))
        paare = [(f, v[f], stamm, _suffix(v[f])) for f in ("file_path", "pdf_path") if v.get(f)]
        if paare:
            p.gruppiere("cvversion", v["id"], paare, "cvversion.cv")
        bericht("cvversion", v, "match_dashboard_path", "Match", job, None, True, v.get("created_at"))
        bericht("cvversion", v, "ats_scan_path", "ATSscan", job, None, True, v.get("created_at"))

    for i in gespraeche.values():
        job = jobs.get(i.get("job_id"))
        if job:
            bericht("interview", i, "prep_path", "Briefing", job, i.get("runde"), True,
                    i.get("created_at"))

    for t in transkripte.values():
        job = jobs.get(t.get("job_id"))
        if not job:
            continue
        iv = gespraeche.get(t.get("interview_id")) or {}
        runde = iv.get("runde") if iv else None
        roh = t.get("file_path")
        if roh:
            d = datum(roh, t.get("recorded_at"), t.get("created_at"))
            base = transcript_filename("Transkript", d.isoformat(), t.get("kontakt"),
                                       _firma(job, firmen), job.get("title") or "", runde=runde)
            p.gruppiere("transcript", t["id"], [("file_path", roh, base, _suffix(roh))],
                        "transcript.file_path")
        for feld, typ in (("debrief_path", "Debrief"), ("report_path", "Auswertung")):
            bericht("transcript", t, feld, typ, job, runde, True, t.get("recorded_at"),
                    t.get("created_at"))

    for f in jobfiles.values():
        roh = f.get("file_path")
        if not roh:
            continue
        rel0 = _norm(roh)
        job = jobs.get(f.get("job_id")) or {}
        if rel0 in p.gruppe_von:                      # z. B. Transkript-Upload: Transcript war zuerst
            p.refs.append(("jobfile", f["id"], "file_path", roh, rel0))
            continue
        if f.get("kind") == "Beirats-Check" or rel0.startswith("data/beirat/"):
            d = datum(roh, f.get("created_at"))
            base = report_filename("Beirat", _firma(job, firmen), job.get("title"), when=d)
            rel = p._pruefe("jobfile", f["id"], "file_path", roh)
            if rel is None:
                continue
            mitglieder = [("file_path", roh, base, _suffix(roh))]
            p.gruppiere("jobfile", f["id"], mitglieder, "jobfile.beirat")
            # Rohdaten gehören zur HTML und ziehen mit (kein DB-Feld).
            idx = p.gruppe_von.get(rel)
            roh_rel = posixpath.splitext(rel)[0] + "_rohdaten.json"
            if idx is not None and _abs(roh_rel, root, daten).is_file() and roh_rel not in p.gruppe_von:
                p.gruppen[idx]["mitglieder"].append((roh_rel, base, "_rohdaten.json"))
                p.gruppe_von[roh_rel] = idx
                p.quelle[roh_rel] = "jobfile.beirat_rohdaten"
            continue
        name = posixpath.basename(rel0)
        kurz = _datum_kurz(name)
        p.gruppiere("jobfile", f["id"], [("file_path", roh, posixpath.splitext(kurz)[0], _suffix(kurz))],
                    "jobfile.upload")

    for f in profilfiles.values():
        roh = f.get("file_path")
        if roh:
            kurz = _datum_kurz(posixpath.basename(_norm(roh)))
            p.gruppiere("profilefile", f["id"],
                        [("file_path", roh, posixpath.splitext(kurz)[0], _suffix(kurz))],
                        "profilefile.upload")

    # Dateien ohne DB-Bezug: nur Datumsformat.
    bekannt = {rel for _t, _i, _f, _r, rel in p.refs} | set(p.gruppe_von)
    for w in DATUM_WURZELN:
        basis = _abs(w, root, daten)
        if not basis.is_dir():
            continue
        for f in sorted(basis.rglob("*")):
            if not f.is_file() or f.name.startswith("."):
                continue
            rel = _rel(f, root, daten)
            if not rel or _ausgenommen(rel) or rel in bekannt:
                continue
            kurz = _datum_kurz(f.name)
            if kurz == f.name:
                continue
            p._neue_gruppe(posixpath.dirname(rel),
                           [(rel, posixpath.splitext(kurz)[0], _suffix(kurz))], f"ordner.{w}")

    p.vergeben()
    p.db_aenderungen({"jobfile": jobfiles, "profilefile": profilfiles})
    return p


# ── Links ────────────────────────────────────────────────────────────────────────────────
def _link_dateien(root: Path, daten: Path):
    """Alle Textdateien, in denen Links ersetzt werden: HTML unter den Artefakt-Ordnern und die
    Debatten-JSON (Beirat, nur oberste Ebene, ohne `_rohdaten`)."""
    out = []
    for w in LINK_WURZELN:
        basis = _abs(w, root, daten)
        if not basis.is_dir():
            continue
        for f in sorted(basis.rglob("*")):
            rel = _rel(f, root, daten)
            if not f.is_file() or not rel or _ausgenommen(rel):
                continue
            if f.suffix.lower() in _LINK_DATEIEN:
                out.append((rel, f))
            elif (w == "data/beirat" and f.suffix == ".json" and f.parent == basis
                  and not f.name.endswith("_rohdaten.json")):
                out.append((rel, f))
    return out


def _ersetze(text: str, karte: dict):
    """Ersetzt alle Pfad-Vorkommen, die in `karte` stehen; Schreibweise (roh / %2F-kodiert /
    nur Leerzeichen kodiert) des Vorkommens bleibt erhalten. -> (neuer Text, Anzahl)."""
    zaehler = [0]

    def f(m):
        tok = m.group(0)
        alt = unquote(tok)
        neu = karte.get(alt)
        if not neu:
            return tok
        zaehler[0] += 1
        if re.search(r"%2[Ff]", tok):
            return quote(neu, safe="")
        if "%" in tok:
            return quote(neu, safe="/")
        return neu

    return _LINK_RE.sub(f, text), zaehler[0]


def _links(root: Path, daten: Path, karte: dict, schreiben=False, sichern=None) -> dict:
    """Probe (schreiben=False) oder Ersetzung (True). `sichern(rel, pfad)` legt vor dem
    Überschreiben eine Kopie ab (Rücknahme)."""
    details, gesamt = [], 0
    if not karte:
        return {"dateien": 0, "ersetzungen": 0, "details": []}
    for rel, pfad in _link_dateien(root, daten):
        try:
            text = pfad.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        neu, n = _ersetze(text, karte)
        if not n:
            continue
        gesamt += n
        details.append({"pfad": rel, "ersetzungen": n})
        if schreiben:
            if sichern:
                sichern(rel, pfad)
            pfad.write_text(neu, encoding="utf-8")
    return {"dateien": len(details), "ersetzungen": gesamt, "details": details}


# ── Bericht ──────────────────────────────────────────────────────────────────────────────
def _summen(p: _Plan) -> dict:
    s = {}
    for u in p.umbenennungen:
        w = _wurzel(u["von"]) or posixpath.dirname(u["von"])
        s[w] = s.get(w, 0) + 1
    return s


def _bericht(p: _Plan, links: dict) -> dict:
    return {
        "erzeugt": datetime.datetime.now().isoformat(timespec="seconds"),
        "umbenennungen": [{"alt": u["von"], "neu": u["nach"], "quelle": u["quelle"]}
                          for u in p.umbenennungen],
        "db_aenderungen": p.db,
        "kollisionen": p.kollisionen,
        "fehlend": p.fehlend,
        "ausgenommen": p.ausgenommen,
        "mehrfach_referenziert": p.mehrfach,
        "links": links,
        "summen_je_ordner": _summen(p),
    }


def _zusammenfassung(b: dict) -> str:
    return (f"{len(b['umbenennungen'])} Dateien umzubenennen, {len(b['db_aenderungen'])} DB-Felder, "
            f"{len(b['kollisionen'])} Kollisionen, {len(b['fehlend'])} fehlende Dateien, "
            f"{b['links']['ersetzungen']} Link-Ersetzungen in {b['links']['dateien']} Dateien.")


def _wurzeln_aufloesen(projekt_root, daten_dir):
    from app import db
    root = Path(projekt_root) if projekt_root else Path(db.PROJECT_ROOT)
    daten = Path(daten_dir) if daten_dir else Path(db.DATA_DIR)
    return root, daten


def probe(projekt_root=None, daten_dir=None, bericht=None) -> dict:
    """Ändert nichts: DB nur lesend (`mode=ro`), kein Schreibzugriff ausser dem optionalen Bericht."""
    root, daten = _wurzeln_aufloesen(projekt_root, daten_dir)
    db_pfad = daten / "bewerbung.sqlite"
    con = sqlite3.connect(f"file:{db_pfad}?mode=ro", uri=True)
    try:
        p = _plan_bauen(con, root, daten)
    finally:
        con.close()
    b = _bericht(p, _links(root, daten, p.karte()))
    if bericht:
        Path(bericht).write_text(json.dumps(b, ensure_ascii=False, indent=1), encoding="utf-8")
    return b


# ── Ausführen ────────────────────────────────────────────────────────────────────────────
class _Protokoll:
    def __init__(self, pfad: Path, kopf: dict):
        self.pfad = pfad
        self.d = {**kopf, "status": "laeuft", "umbenennungen": [], "textdateien": [], "db": []}

    def speichern(self):
        tmp = self.pfad.with_name(self.pfad.name + ".tmp")
        tmp.write_text(json.dumps(self.d, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.pfad)


def _umbenennen(von: Path, nach: Path) -> None:
    """Einzelne Umbenennung (eigene Funktion, damit Tests einen Fehler mitten im Lauf einschleusen)."""
    os.replace(von, nach)


def _db_schreiben(con: sqlite3.Connection, aenderungen: list) -> None:
    for a in aenderungen:
        cur = con.execute(f"UPDATE {a['tabelle']} SET {a['feld']}=? WHERE id=? AND {a['feld']}=?",
                          (a["neu"], a["id"], a["alt"]))
        if cur.rowcount != 1:
            raise RuntimeError(f"DB-Feld nicht aktualisierbar: {a['tabelle']}#{a['id']}.{a['feld']}")


def _reihenfolge(umb: list, root: Path, daten: Path):
    """Ziele, die gerade noch von einer anderen Umbenennung belegt sind, kommen später; echte
    Zyklen laufen über einen Zwischennamen. Liefert Schritte (von_rel, nach_rel)."""
    offen = [(u["von"], u["nach"]) for u in umb]
    schritte = []
    while offen:
        quellen = {v.casefold() for v, _ in offen}
        fertig = [(v, n) for v, n in offen
                  if n.casefold() not in quellen or n.casefold() == v.casefold()]
        if not fertig:
            v, n = offen[0]
            tmp = v + ".p263tmp"
            schritte.append((v, tmp))
            offen[0] = (tmp, n)
            continue
        schritte.extend(fertig)
        offen = [x for x in offen if x not in fertig]
    return schritte


def _offene_aufgaben(con) -> int:
    try:
        return con.execute("SELECT COUNT(*) FROM agenttask WHERE status IN ('queued','running')").fetchone()[0]
    except sqlite3.Error:
        return 0


def _zip_sichern(ziel: Path, wurzeln: set, root: Path, daten: Path) -> int:
    n = 0
    with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as z:
        for w in sorted(wurzeln):
            basis = _abs(w, root, daten)
            if not basis.is_dir():
                continue
            for f in sorted(basis.rglob("*")):
                rel = _rel(f, root, daten)
                if f.is_file() and rel and not _ausgenommen(rel):
                    z.write(f, rel)
                    n += 1
    return n


def _rueckgaengig(prot: dict, root: Path, daten: Path, backup_ordner: Path) -> list:
    """Spielt ein Protokoll rückwärts ab: Textdateien aus den Kopien, Umbenennungen in umgekehrter
    Reihenfolge. DB-Felder macht der Aufrufer (eigene Transaktion). -> Liste von Warnungen."""
    warn = []
    for t in reversed(prot.get("textdateien", [])):
        ziel = _abs(t["pfad"], root, daten)
        kopie = backup_ordner / t["kopie"]
        try:
            shutil.copyfile(kopie, ziel)
        except OSError as e:
            warn.append(f"Textdatei nicht zurückgestellt: {t['pfad']} ({e})")
    for u in reversed(prot.get("umbenennungen", [])):
        von, nach = _abs(u["von"], root, daten), _abs(u["nach"], root, daten)
        if nach.is_file() and not von.exists():
            os.replace(nach, von)
        elif not nach.exists() and von.exists():
            continue                     # nie ausgeführt (Absturz vor dem Umbenennen)
        else:
            warn.append(f"Umbenennung nicht rückgängig: {u['von']} <- {u['nach']}")
    return warn


def _db_zurueck(con, db_liste: list) -> int:
    n = 0
    for a in reversed(db_liste):
        cur = con.execute(f"UPDATE {a['tabelle']} SET {a['feld']}=? WHERE id=? AND {a['feld']}=?",
                          (a["alt"], a["id"], a["neu"]))
        n += cur.rowcount
    return n


def ausfuehren(projekt_root=None, daten_dir=None, jetzt: Optional[datetime.datetime] = None) -> dict:
    root, daten = _wurzeln_aufloesen(projekt_root, daten_dir)
    jetzt = jetzt or datetime.datetime.now()
    stempel = jetzt.strftime("%Y%m%d_%H%M%S")
    db_pfad = daten / "bewerbung.sqlite"
    con = sqlite3.connect(db_pfad, isolation_level=None, timeout=15)
    try:
        offen = _offene_aufgaben(con)
        if offen:
            return {"abgebrochen": True, "grund": f"{offen} Aufgabe(n) queued/running — erst abwarten oder Server stoppen."}
        p = _plan_bauen(con, root, daten)
        links_vorab = _links(root, daten, p.karte())
        if not p.umbenennungen and not p.db and not links_vorab["ersetzungen"]:
            return {"abgebrochen": False, "geaendert": 0, "fehlend": p.fehlend,
                    "meldung": "Nichts zu tun (0 Änderungen)."}

        # (b) Sicherung: DB über sicherung.anlegen, ZIP aller betroffenen Ordner
        from app import sicherung
        db_sicherung = sicherung.anlegen(daten, db_pfad)
        backups = daten / "backups"
        backups.mkdir(parents=True, exist_ok=True)
        wurzeln = {_wurzel(u["von"]) for u in p.umbenennungen}
        wurzeln |= {_wurzel(d["pfad"]) or posixpath.dirname(d["pfad"]) for d in links_vorab["details"]}
        wurzeln.discard(None)
        zip_pfad = backups / f"{_STAMM_SICHERUNG}{stempel}.zip"
        zip_n = _zip_sichern(zip_pfad, wurzeln, root, daten)

        # (c) Protokoll + Umbenennungen
        prot = _Protokoll(backups / f"{_STAMM_PROTOKOLL}{stempel}.json",
                          {"erzeugt": jetzt.isoformat(timespec="seconds"),
                           "db_sicherung": str(db_sicherung), "zip": str(zip_pfad)})
        texte_ordner = backups / f"{_STAMM_PROTOKOLL}{stempel}_texte"
        prot.d["db"] = p.db
        prot.speichern()
        link_ergebnis = {"dateien": 0, "ersetzungen": 0, "details": []}
        try:
            for von, nach in _reihenfolge(p.umbenennungen, root, daten):
                prot.d["umbenennungen"].append({"von": von, "nach": nach})
                prot.speichern()
                _umbenennen(_abs(von, root, daten), _abs(nach, root, daten))
            # (d) DB in EINER Transaktion, (e) Links davor/darin, Commit erst am Ende
            con.execute("BEGIN IMMEDIATE")
            _db_schreiben(con, p.db)

            def sichern(rel, pfad):
                texte_ordner.mkdir(parents=True, exist_ok=True)
                kopie = f"{len(prot.d['textdateien']):06d}.bak"
                shutil.copyfile(pfad, texte_ordner / kopie)
                prot.d["textdateien"].append({"pfad": rel, "kopie": f"{texte_ordner.name}/{kopie}"})
                prot.speichern()

            link_ergebnis = _links(root, daten, p.karte(), schreiben=True, sichern=sichern)
            con.execute("COMMIT")
        except BaseException as exc:
            try:
                con.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            warn = _rueckgaengig(prot.d, root, daten, backups)
            prot.d["status"] = "fehlgeschlagen_zurueckgenommen"
            prot.d["fehler"] = f"{type(exc).__name__}: {exc}"
            prot.speichern()
            return {"fehler": prot.d["fehler"], "protokoll": str(prot.pfad), "warnungen": warn}
        prot.d["status"] = "fertig"
        prot.speichern()
        return {"abgebrochen": False, "geaendert": len(p.umbenennungen),
                "db_felder": len(p.db), "links": link_ergebnis, "fehlend": p.fehlend,
                "kollisionen": p.kollisionen, "protokoll": str(prot.pfad),
                "zip": str(zip_pfad), "zip_dateien": zip_n, "db_sicherung": str(db_sicherung)}
    finally:
        con.close()


def zurueck(protokoll, projekt_root=None, daten_dir=None) -> dict:
    """Spielt ein Protokoll rückwärts ab: Dateien, Textdateien UND DB-Felder."""
    root, daten = _wurzeln_aufloesen(projekt_root, daten_dir)
    pfad = Path(protokoll)
    prot = json.loads(pfad.read_text(encoding="utf-8"))
    con = sqlite3.connect(daten / "bewerbung.sqlite", isolation_level=None, timeout=15)
    try:
        con.execute("BEGIN IMMEDIATE")
        try:
            n_db = _db_zurueck(con, prot.get("db", []))
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
    finally:
        con.close()
    warn = _rueckgaengig(prot, root, daten, pfad.parent)
    prot["status"] = "zurueckgenommen"
    pfad.write_text(json.dumps(prot, ensure_ascii=False), encoding="utf-8")
    return {"db_felder": n_db, "umbenennungen": len(prot.get("umbenennungen", [])),
            "textdateien": len(prot.get("textdateien", [])), "warnungen": warn}


# ── CLI ──────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="P2-63: Dateibestand auf kurze Namen umstellen.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--probe", action="store_true", help="nur lesen, Bericht zeigen")
    g.add_argument("--ausfuehren", action="store_true", help="umbenennen (mit Sicherung)")
    g.add_argument("--zurueck", metavar="PROTOKOLL", help="Protokoll rückwärts abspielen")
    ap.add_argument("--bericht", help="Probe: Bericht als JSON schreiben")
    ap.add_argument("--projekt-root")
    ap.add_argument("--daten-dir")
    a = ap.parse_args(argv)
    try:
        if a.probe:
            b = probe(a.projekt_root, a.daten_dir, a.bericht)
            print("Probe (nichts geändert): " + _zusammenfassung(b))
            if a.bericht:
                print(f"Bericht: {a.bericht}")
            return 0
        if a.ausfuehren:
            r = ausfuehren(a.projekt_root, a.daten_dir)
            if r.get("abgebrochen"):
                print(f"Abbruch: {r['grund']}")
                return 2
            if r.get("fehler"):
                print(f"FEHLER, alles zurückgenommen: {r['fehler']} (Protokoll: {r['protokoll']})")
                return 1
            if not r.get("geaendert"):
                print(r.get("meldung", "Nichts zu tun."))
                return 0
            print(f"Fertig: {r['geaendert']} Dateien umbenannt, {r['db_felder']} DB-Felder, "
                  f"{r['links']['ersetzungen']} Links ersetzt. Protokoll: {r['protokoll']}")
            return 0
        r = zurueck(a.zurueck, a.projekt_root, a.daten_dir)
        print(f"Zurückgenommen: {r['umbenennungen']} Umbenennungen, {r['db_felder']} DB-Felder, "
              f"{r['textdateien']} Textdateien." + (f" Warnungen: {len(r['warnungen'])}" if r["warnungen"] else ""))
        return 1 if r["warnungen"] else 0
    except Exception as e:  # noqa: BLE001 — CLI: kurze Meldung statt Traceback
        print(f"FEHLER: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
