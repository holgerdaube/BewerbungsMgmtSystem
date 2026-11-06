"""FastAPI backend for the Bewerbungs-Management-System.

Cockpit over the SQLite single-source-of-truth. The agentic engine (search, scoring,
CV tailoring, Gmail analysis) runs Claude-in-the-loop and writes into the same DB;
this API reads/serves it and handles manual edits (status changes, notes, triage).
"""
import asyncio
import ipaddress
import json
import os
import re
import uuid
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, func, or_, select

from app.db import engine, flush_or_duplicate, get_session, init_db

from app import agent_runner, favicon, ki_anbieter, zeit
from app.models import (AgentTask, ApiCost, Application, BudgetLimit, CareerEntry, Company, Contact,
                        CVVersion, Email, Headhunter, Interview, Job, JobChat, JobFile, JobLog,
                        NetworkContact, NetzwerkGespraech, Outreach, OutreachLog, Profile, ProfileFile,
                        ProfileSkill, Run, SuchEinstellung, TargetCompany, Transcript)
from app.routes_mail_settings import router as mail_settings_router
from app.routes_coach_settings import router as coach_settings_router
from app.routes_version import router as version_router
from app.routes_sicherung import router as sicherung_router
from app.routes_doku import router as doku_router
from app.routes_beispieldaten import router as beispieldaten_router
from app.routes_netzwerk_import import router as netzwerk_import_router
from app.routes_profil_identitaet import router as profil_identitaet_router
from app.routes_design import router as design_router
from app.routes_sprache import router as sprache_router
from app.sprache import aktuell as sprache_aktuell, datum as sprach_datum, tx, uebersetzt
from app.terminal import tt
from app.version import version_text
from pipeline import bewerbungssprache
from pipeline import posting_snapshot

app = FastAPI(title="Bewerbungs-Management-System", version=version_text())

# P2-55: bewusst KEINE CORS-Freigabe. Bis P2-55 stand hier CORSMiddleware mit allow_origins,
# allow_methods und allow_headers auf "*": Jede Webseite im selben Browser durfte die API lesen
# und nach bestandenem Preflight auch beschreiben (KI-Läufe starten, Stellen löschen). Gebraucht
# hat das kein Aufrufer: Die Oberfläche kommt vom selben Server (auch im LAN-Modus), der
# Vite-Dev-Server leitet /api per Proxy weiter, Skills und Skripte nutzen curl oder Python.
# Eine künftige Freigabe nur einzeln je Herkunft, nie "*", und nur zusammen mit
# tests/test_keine_cors_freigabe.py (Beleg je Aufrufer: tasks/spec_p2-55_keine_cors_freigabe.md).

# P2-57: Host- und Herkunftsprüfung vor jeder Route (tasks/spec_p2-57_herkunftspruefung.md).
# Ohne CORS-Freigabe liest keine fremde Seite die API. Einfache Anfragen (POST ohne Inhalt, als
# Formular oder Upload) schickt der Browser aber trotzdem ab, nur die Antwort bleibt verborgen:
# 21 Routen, darunter `discard` (jede Stelle auf „Kein Match“), der Basis-CV-Upload mit
# `overwrite` und der ZIP-Import (startet `skills-sortieren`). Und nach DNS-Rebinding ist eine
# fremde Domain, die auf 127.0.0.1 zeigt, für den Browser derselbe Ursprung: Sie liest alles und
# schreibt mit passendem Origin. Deshalb zwei Prüfungen:
# 1. Host (jede Anfrage): nur Namen, die sich aus dem Internet nicht umbiegen lassen (IP-Adresse,
#    localhost, *.local, Name ohne Punkt), oder was BMS_HOSTS freigibt.
# 2. Origin (alles außer GET/HEAD/OPTIONS): gleicher Host und Port wie die Anfrage, oder der
#    Vite-Dev-Server über seinen Proxy. Ohne Origin (curl, Skills, Skripte) frei, `null` gesperrt.
# Reine ASGI-Middleware: liest nur den Scope, fasst Inhalt und SSE-Streams nicht an. WebSocket-
# Routen gibt es nicht; wer eine einführt, erweitert die Prüfung auf scope type "websocket".
# Vertrag: tests/test_herkunftspruefung.py (mit Wächter über alle Routen) und die legitimen Wege
# in tests/test_keine_cors_freigabe.py.
_LESENDE_METHODEN = frozenset({"GET", "HEAD", "OPTIONS"})
# Vite (frontend/vite.config.ts): Die Proxy-Kurzform bedeutet changeOrigin: true, das Backend sieht
# Host localhost:8000 und den Origin des Browsers. Die Ausnahme gilt deshalb nur an Host localhost
# und nur mit Sec-Fetch-Site same-origin (über den Proxy immer so) oder ohne diesen Header (ältere
# Browser): Ein anderes Projekt auf localhost:5173, das :8000 direkt anspricht, meldet same-site.
# Die Bindung an localhost ist nötig, weil Browser Sec-Fetch-Site nur an vertrauenswürdige Ziele
# schicken (https, localhost, Loopback-IP): An <mac>.local oder eine LAN-IP käme dieselbe fremde
# Seite ohne den Header an, und macOS löst den eigenen .local-Namen auch auf 127.0.0.1 auf.
_VITE_DEV_HERKUNFT = "http://localhost:5173"
_STANDARDPORT = {"http": 80, "https": 443}
# Nur, was ein Browser als Host schicken kann: Buchstaben, Ziffern, Punkt, Bindestrich, Unterstrich
# (Unicode-Namen kommen als Punycode) oder eine IPv6-Adresse in Klammern, ohne Zonen-ID.
_HOST_RE = re.compile(r"(\[[0-9a-f:.]+\]|[a-z0-9._-]+)(?::(\d{1,5}))?", re.IGNORECASE)


def _host_teile(wert: str) -> Optional[tuple[str, Optional[int]]]:
    """(Name klein, Port oder None) aus `name[:port]` bzw. `[IPv6][:port]`; None, wenn unlesbar
    (Zeichen, die kein Browser im Host schickt, Pfad, Benutzerteil, eine Klammer ohne gültige
    IPv6-Adresse)."""
    treffer = _HOST_RE.fullmatch(wert)
    if not treffer:
        return None
    name, port = treffer.group(1).lower(), treffer.group(2)
    if name.startswith("["):
        try:
            ipaddress.IPv6Address(name[1:-1])
        except ValueError:
            return None
    return name, int(port) if port else None


def _origin_teile(origin: str) -> Optional[tuple[str, str, int]]:
    """(Schema, Name, Port) aus einem Origin `http(s)://host[:port]`, fehlender Port nach Schema;
    None für `null` und alles andere (fremdes Schema, Pfad, Benutzerteil)."""
    treffer = re.fullmatch(r"(https?)://(.*)", origin, re.IGNORECASE)
    teile = _host_teile(treffer.group(2)) if treffer else None
    if teile is None:
        return None
    schema = treffer.group(1).lower()
    return schema, teile[0], teile[1] if teile[1] is not None else _STANDARDPORT[schema]


def _weitere_hosts() -> set[str]:
    """Namen aus BMS_HOSTS (Komma oder Leerzeichen getrennt; Port und abschließender Punkt zählen
    nicht). Zur Laufzeit gelesen, damit Tests die Variable setzen können."""
    namen = set()
    for eintrag in re.split(r"[\s,]+", os.environ.get("BMS_HOSTS", "")):
        teile = _host_teile(eintrag) if eintrag else None
        if teile:
            namen.add(teile[0].removesuffix("."))
    return namen


def _host_erlaubt(name: str) -> bool:
    """Ob der Server unter diesem Namen (aus `_host_teile`, ohne Port) antwortet. Erlaubt ist nur,
    was eine fremde Domain nicht per DNS-Rebinding vortäuschen kann: eine IP-Adresse (der Browser
    schickt sie nur, wenn er genau diese Adresse ohne DNS angesprochen hat), `localhost` (lösen
    Browser selbst auf), `*.local` (mDNS, nur im lokalen Netz) und Namen ohne Punkt (Hosts-Datei,
    NetBIOS/LLMNR, Suchdomäne; auch Windows-Rechnernamen und `testserver` der Tests). Router-Namen
    wie `mac.fritz.box` gehen über das normale DNS und brauchen BMS_HOSTS."""
    name = name.removesuffix(".")
    if not name:
        return False
    if name.startswith("["):
        return True                          # IPv6, von `_host_teile` geprüft
    try:
        ipaddress.IPv4Address(name)
        return True
    except ValueError:
        pass
    if name == "localhost" or name.endswith(".local") or "." not in name:
        return True
    return name in _weitere_hosts()


def _herkunft_erlaubt(origin: str, host: Optional[str], sec_fetch_site: Optional[str]) -> bool:
    """Ob eine schreibende Anfrage mit diesem Origin angenommen wird: Host und Port wie im
    Host-Header, Groß- und Kleinschreibung egal. Fehlt im Host-Header der Port, gilt der
    Standardport des Origin-Schemas; das Schema selbst zählt nicht, damit ein Proxy mit TLS davor
    funktioniert (Browser: https, Backend: http). Dazu die Vite-Ausnahme, nur an Host localhost
    (s. `_VITE_DEV_HERKUNFT`)."""
    teile = _origin_teile(origin)
    ziel = _host_teile(host) if host else None
    if (origin == _VITE_DEV_HERKUNFT and ziel is not None and ziel[0] == "localhost"
            and sec_fetch_site in (None, "same-origin")):
        return True
    if teile is None or ziel is None:
        return False
    schema, name, port = teile
    return (name, port) == (ziel[0], ziel[1] if ziel[1] is not None else _STANDARDPORT[schema])


def _abweisung(scope) -> Optional[str]:
    """Meldung, wenn die Anfrage abgewiesen wird, sonst None. Fehlt der Host-Header, geht die
    Anfrage durch: Browser schicken ihn immer, Rebinding braucht einen Browser."""
    kopf = {}
    for schluessel, wert in scope["headers"]:
        kopf.setdefault(schluessel, wert.decode("latin-1"))
    host = kopf.get(b"host")
    if host:
        teile = _host_teile(host)
        if teile is None or not _host_erlaubt(teile[0]):
            return (tx("Adresse nicht freigegeben: {host}. Das BMS antwortet nur unter localhost, "
                       "einer IP-Adresse, einem Namen auf .local oder einem Rechnernamen ohne "
                       "Punkt. Öffnen Sie es über die Adresse aus dem Startfenster; weitere Namen "
                       "gibt die Umgebungsvariable BMS_HOSTS frei.", host=host))
    origin = kopf.get(b"origin")
    if origin is not None and scope["method"] not in _LESENDE_METHODEN:
        sec_fetch_site = kopf.get(b"sec-fetch-site")
        if not _herkunft_erlaubt(origin, host, sec_fetch_site.lower() if sec_fetch_site else None):
            return (tx("Schreibzugriff abgelehnt: Die Anfrage kommt nicht von der BMS-Oberfläche "
                       "(Origin: {origin}).", origin=origin))
    return None


class _Herkunftspruefung:
    """P2-57: weist Anfragen mit fremdem Host oder fremder Herkunft mit 403 ab, bevor eine Route
    läuft (Regeln s. Kommentar oben)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            grund = _abweisung(scope)
            if grund:
                await JSONResponse({"detail": grund}, status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)


app.add_middleware(_Herkunftspruefung)  # P2-57: Host- und Herkunftsprüfung vor jeder Route

# Phase 71F — Mail-Provider-Abstraktion: eigener Router statt neuer @app.*-Routen hier, s.
# app/routes_mail_settings.py.
app.include_router(mail_settings_router)
app.include_router(coach_settings_router)  # Phase 82, s. app/routes_coach_settings.py
app.include_router(version_router)  # P2-51, s. app/routes_version.py
app.include_router(sicherung_router)  # P2-52, s. app/routes_sicherung.py
app.include_router(doku_router)  # P2-59, s. app/routes_doku.py
app.include_router(beispieldaten_router)  # P2-59, s. app/routes_beispieldaten.py
app.include_router(netzwerk_import_router)  # P2-62, s. app/routes_netzwerk_import.py
app.include_router(profil_identitaet_router)  # P2-69, s. app/routes_profil_identitaet.py
app.include_router(design_router)  # P2-72, s. app/routes_design.py
app.include_router(sprache_router)  # P2-88, s. app/routes_sprache.py

# Endstatus: hier ist ein Follow-up gegenstandslos (kein aktiver Vorgang mehr).
# Phase 85: "Keine Rückmeldung" (Ghosting-Endstatus, manuell gesetzt) ergänzt — kein Follow-up
# mehr nötig, genau wie bei Absage/Kein Match. NICHT in gesamtprozess._NICHT_RELEVANT_STATUS
# aufgenommen (s. dortigen Kommentar): die Stelle WAR relevant und wurde beworben.
TERMINAL_STATUSES = {"Absage", "Kein Match", "Nicht verfügbar", "Beirat abgelehnt", "Keine Rückmeldung"}

# P2-6 (Phase 67F): feste, erlaubte Wertemenge für Job.status — PATCH akzeptierte bisher JEDEN
# String; ein Tippfehler/Fremdwert fiel dann still aus TERMINAL_STATUSES, dem Dashboard-Funnel
# und der Button-Anzeige heraus (ununterscheidbar von einem bewussten neuen Status). Quelle der
# Wahrheit ist die UI selbst (frontend/src/pages/JobDetail.tsx, Konstante `STATUSES`) — NICHT
# `normalize.norm_status()`: der deckt nur 8 der 10 Werte ab (kein "Interview"/"Angebot", die
# beide NUR über die JobDetail-Buttons per PATCH gesetzt werden, nie über die Normalisierung).
# Read-only-Bestandsprüfung (26.07.2026): fast alle Werte kommen in der Live-DB bereits vor;
# "Angebot" hatte zum Prüfzeitpunkt keine Zeile, ist aber ein AKTIVER Automatisierungs-Auslöser
# (Skill angebot-vergleich fragt `GET /api/jobs?status=Angebot` ab) — deshalb trotz seltener
# Nutzung in der Menge belassen. Ändert sich die UI-Liste, MUSS diese Menge mitgezogen werden
# (sonst bricht die UI selbst an ihrer eigenen Status-Auswahl).
ALLOWED_JOB_STATUSES = {
    "Neu", "Prüfen", "Beworben", "Interview", "Angebot", "Absage",
    "Kein Match", "Beirat abgelehnt", "Nicht verfügbar", "Geparkt",
    "Keine Rückmeldung",  # Phase 85: Ghosting-Endstatus, manuell gesetzt
}

# P2-6: Interview.status — EIGENE, kleinere Wertemenge (NICHT identisch mit Job.status!).
# Entspricht dem Default in app/models.py::Interview.status und den einzigen Buttons, die
# frontend/src/pages/JobDetail.tsx anbietet (Zeile ~1408-1409: "Absolviert"/"Abgesagt"; "Geplant"
# ist der Anlage-Default aus create_interview/interview-vorbereiten-Skill).
ALLOWED_INTERVIEW_STATUSES = {"Geplant", "Absolviert", "Abgesagt"}

# Phase 69 (Stufe B) — Interview.gegenueber / NetzwerkGespraech.gegenueber: dieselbe Werteliste
# wie in app/gesamtprozess.py::_GEGENUEBER_BUCKETS + Sammel-Bucket, s. dortigen Docstring.
# NetzwerkGespraech erlaubt zusätzlich "Netzwerk" (reiner Netzwerk-Kontakt, kein Recruiter/HM/
# Headhunter) — Interview (verlangt zwingend eine Stelle) kennt diesen Wert NICHT.
ALLOWED_GEGENUEBER = {"Recruiter", "Hiring Manager", "Fachbereich", "Headhunter", "Sonstige"}
ALLOWED_GEGENUEBER_NETZWERK = ALLOWED_GEGENUEBER | {"Netzwerk"}

# Phase 74 — Beworben-Check (wöchentliche Verfügbarkeitsprüfung): Job.availability_status, feste
# Wertemenge wie ALLOWED_JOB_STATUSES oben, geprüft über dasselbe generische _validiere_status()
# unten. AVAILABILITY_LABELS sind die deutschen Anzeige-Labels — Backend-Log (update_job) UND
# Frontend nutzen exakt dieselben Texte, damit Log-Einträge und UI-Badges nie auseinanderdriften.
ALLOWED_AVAILABILITY = {"offen", "karriereseite_offen", "offline", "unklar"}
AVAILABILITY_LABELS = {
    "offen": "noch ausgeschrieben",
    "karriereseite_offen": "Portal zu, Karriereseite offen",
    "offline": "nicht mehr ausgeschrieben",
    "unklar": "unklar",
}


def _validiere_status(status, erlaubt: set, feldname: str = "status") -> None:
    """Gemeinsamer Validator für Job- und Interview-Status (Muster `update_einstellungen`s
    `_validiere_*`-Familie): 422 bei Abweichung von der festen Menge, NICHT stillschweigend
    übernehmen. Wird nur aufgerufen, wenn das Feld überhaupt im Payload steht."""
    if status not in erlaubt:
        raise HTTPException(
            422, tx("Ungültiger {feldname}: {status}. Erlaubt: {liste}", feldname=feldname, status=repr(status), liste=', '.join(sorted(erlaubt))))


def _normalisiere_portal_closed(wert) -> int:
    """Robuste 0/1-Normalisierung für Job.portal_closed (Phase 73) — akzeptiert Python-bool,
    int 0/1 und die String-Varianten "0"/"1"/"true"/"false" (case-insensitive). Jeder andere Wert:
    422 (Muster `_validiere_status` — fester Wertebereich statt stillschweigender Übernahme)."""
    if isinstance(wert, bool):
        return int(wert)
    if isinstance(wert, int) and wert in (0, 1):
        return wert
    if isinstance(wert, str):
        normalisiert = wert.strip().lower()
        if normalisiert in ("1", "true"):
            return 1
        if normalisiert in ("0", "false"):
            return 0
    raise HTTPException(422, tx("Ungültiger Wert für portal_closed: {wert}. Erlaubt: 0/1/true/false", wert=repr(wert)))


def _date_sort_key(s: Optional[str]) -> str:
    """Datums-String in vergleichbaren ISO-Schlüssel (YYYY-MM-DD) normalisieren.
    Der Tracker enthält gemischte Formate (TT.MM.JJJJ und JJJJ-MM-TT); als Rohstring
    sortieren die nicht chronologisch. Unparsbares → '' (landet im reverse-Sort am Ende)."""
    if not s:
        return ""
    s = s.strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":   # bereits YYYY-MM-DD
        return s[:10]
    if "." in s:                                        # TT.MM.JJJJ oder TT.MM.JJ
        parts = s.split(".")
        if len(parts) == 3:
            d, m, y = (p.strip() for p in parts)
            if len(y) == 2:
                y = "20" + y
            if y.isdigit() and m.isdigit() and d.isdigit():
                return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    return ""


@app.on_event("startup")
def _startup():
    # P2-59: VOR init_db() feststellen, ob es die Datenbank schon gab, denn init_db() legt sie an.
    # Nur der allererste Start einer Installation bekommt Beispieldaten (s. app/beispieldaten.py).
    from app import db
    db_war_da = db.DB_PATH.exists()
    init_db()
    # Phase 100: `config/suchprofile.yaml` ist Startvoraussetzung (Einstellungen-Seite,
    # Job-Ingest), liegt aber nicht im Repo — nach einem frischen Klon fehlt sie. Hier statt
    # beim ersten GET, damit auch ein Skill-Lauf vor dem ersten Seitenaufruf eine Datei
    # vorfindet. Legt nichts an, wenn die Datei existiert.
    from pipeline import suchprofil
    suchprofil.sicherstellen()
    # P2-73: abgelöste Standard-Adressen der Suchportale ersetzen (Datenbank und Kopf der
    # Suchprofil-Datei). Hier, weil ein Update nur über einen Neustart wirksam wird und die
    # Such-Skills die Datei lesen, nicht die Datenbank. Der Start darf daran nie scheitern.
    try:
        umgestellt = _portal_adressen_nachziehen()
        if umgestellt:
            print(tt("[einstellungen] Portal-Adressen auf den aktuellen Standard umgestellt: {liste}", liste=", ".join(umgestellt)), flush=True)
    except Exception as exc:  # noqa: BLE001 -- der Start darf daran nie scheitern
        print(tt("[einstellungen] WARNUNG: Portal-Adressen nicht umgestellt: {fehler}", fehler=exc), flush=True)
    # P2-59: Beispieldaten einer frischen Paket-Installation. Die Funktion prüft alle Bedingungen
    # selbst und wirft nie; die abgeleitete Profil-Struktur folgt den neuen Skills und dem Werdegang.
    from app import beispieldaten
    # P2-90: Die englische Installationsanleitung legt `data/startsprache` an. Vor den Beispieldaten, damit sie gleich englisch sind.
    beispieldaten.startsprache_uebernehmen()
    if beispieldaten.einspielen_falls_neu(db_war_da):
        try:
            with Session(engine) as session:
                _profil_struktur_schreiben(session)
        except Exception as exc:  # noqa: BLE001 -- der Start darf daran nie scheitern
            print(tt("[beispieldaten] WARNUNG: Profil-Struktur nicht geschrieben: {fehler}", fehler=exc), flush=True)
    # P2-83: `config/profil_struktur.md` ist abgeleitet und nicht im Git, jede Installation erzeugt
    # sie selbst. Fehlt sie (frischer Klon, erster Start nach dem Update), wird sie jetzt aus der
    # Datenbank geschrieben, damit die Skills sie finden. Eine vorhandene Datei bleibt unberührt.
    try:
        if not _PROFIL_STRUKTUR_PATH.is_file():
            with Session(engine) as session:
                _profil_struktur_schreiben(session)
    except Exception as exc:  # noqa: BLE001 -- der Start darf daran nie scheitern
        print(tt("[profil] WARNUNG: Profil-Struktur nicht geschrieben: {fehler}", fehler=exc), flush=True)
    agent_runner.start_workers()
    # P2-52: täglicher Sicherungstakt (erste Prüfung nach 60 s, die Arbeit läuft in einem
    # Thread, blockiert den Start also nicht). Tests laufen ohne Lifespan und starten ihn nie.
    from app import sicherung
    sicherung.starten()


@app.on_event("shutdown")
def _shutdown():
    # Phase 65 (P1-6): eigene Kindprozesse (claude-p-Skills, lokale Schritte) beim Beenden des
    # Servers MITNEHMEN, statt sie verwaist weiterlaufen zu lassen — konsistent zum Startup-Hook
    # oben. Warum hier KEINE Identitätsprüfung wie beim Start nötig ist (Asymmetrie bewusst,
    # s. agent_runner.shutdown_kill_all()-Docstring für die volle Begründung): dieser Server-
    # Prozess hält hier ausschließlich Handles, die er selbst in DIESEM Lauf gestartet hat.
    agent_runner.shutdown_kill_all()


# ── Health ───────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok"}


# ── Volltextsuche (Phase 25) ────────────────────────────────────────────────────
@app.get("/api/search")
def search(q: str, limit: int = 30, session: Session = Depends(get_session)):
    if len(q.strip()) < 2:
        raise HTTPException(422, tx("Suchbegriff braucht mindestens 2 Zeichen"))
    from pipeline import search_index
    res = search_index.query(q, limit=limit)
    for e in res["ergebnisse"]:
        job = session.get(Job, e["job_id"])
        e["job"] = {
            "id": job.id, "company_name": job.company_name, "title": job.title,
            "status": job.status, "match_score": job.match_score, "location": job.location,
            "follow_up_date": job.follow_up_date,
        } if job and not job.deleted_at else None
    res["ergebnisse"] = [e for e in res["ergebnisse"] if e["job"]]   # verwaiste Index-Einträge raus
    return res


@app.post("/api/search/rebuild")
def search_rebuild():
    from pipeline import search_index
    return search_index.rebuild()


@app.get("/api/search/meta")
def search_meta():
    from pipeline import search_index
    return search_index.meta()   # {built_at, dokumente, hinweis}


# ── Dashboard KPIs ─────────────────────────────────────────────────────────────
@app.get("/api/dashboard")
def dashboard(session: Session = Depends(get_session)):
    jobs = session.exec(select(Job).where(Job.deleted_at.is_(None))).all()
    companies = session.exec(select(Company)).all()
    apps = session.exec(select(Application)).all()
    emails = session.exec(select(Email)).all()

    situ_by_company = {c.id: c.situation for c in companies}

    by_status = Counter(j.status or "Neu" for j in jobs)
    by_score = Counter(str(j.match_score) if j.match_score else "—" for j in jobs)
    by_portal = Counter(j.portal or "Unbekannt" for j in jobs)
    by_tab = Counter(j.tab or "—" for j in jobs)
    by_situation = Counter((situ_by_company.get(j.company_id) or "UNKLAR") for j in jobs)

    # Situation je Suchplan (Phase 51) — dieselbe situ_by_company-Map, nur nach norm_plan()
    # aufgeteilt. Feste Reihenfolge (_SITUATION_PRIORITY + UNKLAR) statt most_common(), sonst
    # wäre jede Plan-Karte anders sortiert und nicht zeilenweise vergleichbar; 0-Einträge raus.
    from app import normalize as N
    plan_buckets = {"A": [], "B": [], "C": [], "ohne": []}
    for j in jobs:
        plan_buckets[N.norm_plan(j.plan_ab) or "ohne"].append(j)
    _situ_order = N._SITUATION_PRIORITY + ["UNKLAR"]

    def _verteilung(js):
        c = Counter((situ_by_company.get(j.company_id) or "UNKLAR") for j in js)
        return {code: c[code] for code in _situ_order if c[code] > 0}

    by_situation_plan = {k: _verteilung(js) for k, js in plan_buckets.items()}

    # Response Rate / Ø Antwortzeit: EINZIGE Berechnung in app.response_metrics (Phase 67B,
    # P2-7) — export_excel.py::build_workbook() ruft dieselbe Funktion auf. NICHT hier lokal
    # nachbauen, sonst driftet die Formel wieder auseinander (genau das war der Befund).
    from app.response_metrics import response_kpis
    resp_kpis = response_kpis(emails, apps)

    # Pipeline-Funnel über die aktiven Stufen
    funnel = {stage: by_status.get(stage, 0)
              for stage in ["Neu", "Prüfen", "Beworben", "Interview", "Angebot", "Absage"]}

    # Aktive „laufende Bewerbungen" = beworben/im Gespräch, noch keine Absage.
    active_stages = ("Beworben", "Interview", "Angebot")
    active_applications = sum(by_status.get(s, 0) for s in active_stages)

    # Phase 74 — Beworben-Check: laufende Bewerbungen (Beworben/Interview — NICHT Angebot, s.
    # Design-Entscheidung 3 der Spec), deren letzte Verfügbarkeitsprüfung "offline" ergab.
    applied_offline = sum(
        1 for j in jobs if j.status in ("Beworben", "Interview") and j.availability_status == "offline"
    )

    # Follow-ups: Jobs mit Fälligkeitsdatum, die noch aktiv sind.
    today = date.today().isoformat()
    fu_jobs = [j for j in jobs if j.follow_up_date and j.status not in TERMINAL_STATUSES]
    followups_overdue = sum(1 for j in fu_jobs if j.follow_up_date <= today)
    followups_open = len(fu_jobs)
    # Netzwerk-Aktionen mit gesetztem Fälligkeitsdatum (Phase 22).
    ncs_fu = [n for n in session.exec(
        select(NetworkContact).where(NetworkContact.deleted_at.is_(None))).all()
        if n.next_action_date]
    netzwerk_overdue = sum(1 for n in ncs_fu if n.next_action_date[:10] <= today)
    netzwerk_open = len(ncs_fu)

    # Gesamtprozess seit Beginn (Phase 69, Stufe B) — EINZIGE Berechnung in app.gesamtprozess
    # (Stufe A, Muster response_metrics.py): export_excel.py (Stufe C) ruft dieselben vier
    # Funktionen auf derselben Datengrundlage auf, damit Web-Dashboard und Excel-Export niemals
    # auseinanderdriften (genau der Befund, den response_metrics schon einmal gelöst hat).
    from app.gesamtprozess import (
        absagen_kpi, bewerbungen_kpi, funnel_kpi, gespraeche_kpi, keine_reaktion_kpi,
    )
    outreach_rows = session.exec(select(Outreach)).all()
    interview_rows = session.exec(select(Interview)).all()
    netzwerkgespraeche_rows = session.exec(select(NetzwerkGespraech)).all()

    bew_kpi = bewerbungen_kpi(apps, outreach_rows)
    ges_kpi = gespraeche_kpi(interview_rows, netzwerkgespraeche_rows)
    abs_kpi = absagen_kpi(jobs, outreach_rows)
    kr_kpi = keine_reaktion_kpi(jobs, emails, apps, outreach_rows)

    # `rows` nur bei "Keine Reaktion" mitliefern (fürs Aufrollen in der UI) — bei den anderen
    # drei KPIs hielte das den Payload unnötig groß, s. Auftrag Stufe B.
    gesamtprozess = {
        "bewerbungen": {"wert": bew_kpi["wert"], "splits": bew_kpi["splits"]},
        "gespraeche": {"wert": ges_kpi["wert"], "splits": ges_kpi["splits"]},
        "absagen": {"wert": abs_kpi["wert"], "splits": abs_kpi["splits"]},
        "keine_reaktion": {"wert": kr_kpi["wert"], "splits": kr_kpi["splits"], "rows": kr_kpi["rows"]},
        # Phase 70, Stufe A — der Gesamtprozess als 5-stufiger Trichter (Gesichtet -> Relevant ->
        # Beworben -> Antworten -> Interviews). ADDITIV zu den vier KPIs oben, EINE Berechnung
        # (app.gesamtprozess.funnel_kpi) für Web UND Excel-Export (pipeline/export_excel.py).
        # Lebt bewusst unter gesamtprozess.funnel, NICHT auf Top-Level — "funnel" dort ist
        # bereits der Pipeline-Funnel (aktive Stellen je Status, s. oben).
        "funnel": funnel_kpi(jobs, apps, emails, outreach_rows, interview_rows,
                              netzwerkgespraeche_rows),
    }

    return {
        "totals": {
            "jobs": len(jobs),
            "companies": len(companies),
            "radar_companies": sum(1 for c in companies if c.is_radar),
            "applications": len(apps),
            "active_applications": active_applications,
            "applied_offline": applied_offline,   # Phase 74: Beworben-Check
            # P2-52: archivierte Mails ohne Stelle zaehlen hier nicht mehr mit. `emails` selbst
            # bleibt UNGEFILTERT (response_kpis/gesamtprozess oben lesen dieselbe Liste) — die
            # Kennzahlen sehen archivierte Mails ohnehin nie, sie haben nie eine application_id.
            "emails": sum(1 for e in emails if not e.archived_at),
            "responses": resp_kpis["responses"],
            "avg_response_hours": resp_kpis["avg_response_hours"],
            "response_rate": resp_kpis["response_rate"],
            "top_matches": sum(1 for j in jobs if (j.match_score or 0) >= 4),
            "followups_overdue": followups_overdue,
            "followups_open": followups_open,
            "netzwerk_overdue": netzwerk_overdue,
            "netzwerk_open": netzwerk_open,
        },
        "by_status": dict(by_status),
        "by_score": dict(sorted(by_score.items())),
        "by_portal": dict(by_portal.most_common()),
        "by_tab": dict(by_tab),
        "by_situation": dict(by_situation.most_common()),
        "by_situation_plan": by_situation_plan,
        "funnel": funnel,
        "gesamtprozess": gesamtprozess,
    }


# ── Jobs ─────────────────────────────────────────────────────────────────────
@app.get("/api/jobs")
def list_jobs(
    session: Session = Depends(get_session),
    status: Optional[str] = None,
    statuses: Optional[str] = None,
    tab: Optional[str] = None,
    portal: Optional[str] = None,
    score: Optional[str] = None,
    situation: Optional[str] = None,
    plan: Optional[str] = None,
    min_score: Optional[int] = None,
    q: Optional[str] = None,
    availability_status: Optional[str] = None,   # Phase 74: Beworben-Check-Drilldown
    sort: str = Query("score", pattern="^(score|found|company|status)$"),
):
    jobs = session.exec(select(Job).where(Job.deleted_at.is_(None))).all()
    if status:
        jobs = [j for j in jobs if j.status == status]
    if statuses:  # kommagetrennte Mehrfachauswahl, z. B. laufende Bewerbungen
        wanted = {s.strip() for s in statuses.split(",") if s.strip()}
        jobs = [j for j in jobs if j.status in wanted]
    if tab:
        jobs = [j for j in jobs if j.tab == tab]
    if portal:  # "Unbekannt" = Jobs ohne Portal (wie die Dashboard-Zählung)
        jobs = [j for j in jobs if (not j.portal if portal == "Unbekannt" else j.portal == portal)]
    if score:  # exakter Score fürs Dashboard-Drill-down; "none" = ohne Bewertung ("—")
        if score in ("none", "—"):
            jobs = [j for j in jobs if j.match_score is None]
        elif score.isdigit():
            jobs = [j for j in jobs if j.match_score == int(score)]
    if situation:  # Firmen-Situation, UNKLAR schließt Firmen ohne Wert ein (wie Dashboard)
        situ = {c.id: c.situation for c in session.exec(select(Company)).all()}
        jobs = [j for j in jobs if (situ.get(j.company_id) or "UNKLAR") == situation]
    if plan:  # Suchplan A/B/C (Phase 51); "none" = Jobs ohne erkennbaren Plan
        from app import normalize as N
        wanted_plan = "ohne" if plan == "none" else plan.upper()
        jobs = [j for j in jobs if (N.norm_plan(j.plan_ab) or "ohne") == wanted_plan]
    if min_score:
        jobs = [j for j in jobs if (j.match_score or 0) >= min_score]
    if q:
        ql = q.lower()
        jobs = [j for j in jobs if ql in (j.title or "").lower() or ql in (j.company_name or "").lower()]
    if availability_status:   # Phase 74: Beworben-Check-Drilldown, z. B. "offline"
        jobs = [j for j in jobs if j.availability_status == availability_status]

    keyfns = {
        "score": lambda j: (-(j.match_score or 0), (j.company_name or "").lower()),
        "found": lambda j: _date_sort_key(j.found_date),
        "company": lambda j: (j.company_name or "").lower(),
        "status": lambda j: (j.status or ""),
    }
    reverse = sort == "found"
    jobs.sort(key=keyfns[sort], reverse=reverse)

    return [
        {
            "id": j.id, "company_name": j.company_name, "title": j.title,
            "seniority": j.seniority, "location": j.location, "work_model": j.work_model,
            "tab": j.tab, "plan_ab": j.plan_ab, "portal": j.portal, "url": j.url,
            "match_score": j.match_score, "status": j.status, "next_step": j.next_step,
            "found_date": j.found_date, "salary": j.salary, "follow_up_date": j.follow_up_date,
            "verified_at": j.verified_at, "verify_note": j.verify_note,
            "availability_status": j.availability_status,          # Phase 74: Beworben-Check
            "availability_checked_at": j.availability_checked_at,
        }
        for j in jobs
    ]


def _manuelle_dublette(session, url, name, title):
    """Aktive Stelle zu einem manuellen Eintrag: `("url" | "firma_titel", Job)` oder None. Die URL geht vor,
    Firma+Titel nutzt die bereinigten Schlüssel des Ingests (Rechtsform und Gender-Zusatz zählen nicht).
    Gelöschte Stellen zählen nicht: Wer eine Stelle von Hand wieder anlegt, will sie zurück. Der Ingest
    behandelt sie weiter als Tombstone, damit die Suche sie nicht von selbst wieder hereinholt."""
    from app import normalize as N
    aktive = session.exec(select(Job).where(Job.deleted_at.is_(None))).all()
    url_wert = N.url_vergleich(url)
    if url_wert:
        for j in aktive:
            if N.url_vergleich(j.url) == url_wert:
                return "url", j
    if name and title:
        schluessel = (N.firma_key(name), N.rollen_schluessel(title))
        for j in aktive:
            if (N.firma_key(j.company_name), N.rollen_schluessel(j.title)) == schluessel:
                return "firma_titel", j
    return None


@app.get("/api/jobs/dublette")
def job_dublette(url: str = "", company_name: str = "", title: str = "", session: Session = Depends(get_session)):
    """Vorab-Warnung im Formular „Neue Stelle“, sobald URL, Firma oder Titel ausgefüllt sind."""
    treffer = _manuelle_dublette(session, url.strip(), company_name.strip(), title.strip())
    if not treffer:
        return {"art": None, "job": None}
    art, j = treffer
    return {"art": art, "job": {"id": j.id, "company_name": j.company_name, "title": j.title, "status": j.status}}


@app.post("/api/jobs")
def create_job(payload: dict, session: Session = Depends(get_session)):
    """Stelle manuell anlegen (Formular „+ Stelle anlegen" auf /jobs).
    Gibt es schon eine aktive Stelle mit dieser URL oder Firma+Titel, wird sie gemeldet statt angelegt."""
    name = (payload.get("company_name") or "").strip()
    title = (payload.get("title") or "").strip()
    if not name or not title:
        raise HTTPException(422, tx("company_name und title sind Pflicht"))

    treffer = _manuelle_dublette(session, payload.get("url"), name, title)
    if treffer:
        return {"existing": True, "art": treffer[0], "job": treffer[1]}

    comp = next((c for c in session.exec(select(Company)).all() if _norm_name(c.name) == name.lower()), None)
    if not comp:
        neue_comp = Company(name=name, notes=tx("Manuell angelegt"))
        # `session.add(neue_comp)` bewusst ERST im Callback — s. Docstring von flush_or_duplicate
        # (begin_nested() autoflusht sonst vorher pending Änderungen AUSSERHALB der Savepoint-
        # Absicherung).
        if flush_or_duplicate(session, lambda: session.add(neue_comp)):
            comp = neue_comp
        else:
            # P2-3 (Phase 67F): echte Race (zwei fast gleichzeitige Anfragen legen dieselbe
            # Firma an) — die jetzt existierende Zeile nachschlagen statt mit 500 zu crashen.
            comp = next((c for c in session.exec(select(Company)).all() if _norm_name(c.name) == name.lower()), None)

    fields = {"seniority", "location", "work_model", "tab", "plan_ab", "portal", "url", "salary",
              "published_date", "match_score", "notes", "next_step", "follow_up_date"}
    data = {k: v for k, v in payload.items() if k in fields and v not in (None, "")}
    if "tab" in data:
        # P2-51 (V7): eine mitgeschickte, aber inzwischen umbenannte Umkreis-Bezeichnung landet
        # auf der aktuellen statt einer zweiten, veralteten Kennung (Muster `pipeline.ingest`).
        from pipeline import suchprofil
        normalisiert = suchprofil.tab_normalisieren(data["tab"], suchprofil.aktuelles_umkreis_label(session))
        if normalisiert is None:
            data.pop("tab")
        else:
            data["tab"] = normalisiert
    status = payload.get("status") or "Prüfen"
    # Eine gelöschte Stelle behält ihren Schlüssel und ihre URL als Tombstone, beide Indizes sind UNIQUE.
    # Der Schlüssel bekommt eine laufende Nummer (nur Tombstones zählen, damit ein Doppelklick weiter
    # kollidiert). Die URL wandert auf die neue Stelle, so bleibt sie für den Ingest bekannt.
    basis_key = f"manuell|{name.lower()}|{title.lower()}"
    belegt = set(session.exec(select(Job.dedup_key).where(
        Job.dedup_key.startswith(basis_key, autoescape=True), Job.deleted_at.is_not(None))).all())
    if data.get("url"):
        data["url"] = data["url"].strip()
        for tombstone in session.exec(select(Job).where(Job.url == data["url"], Job.deleted_at.is_not(None))).all():
            tombstone.url = None
    dedup_key, nummer = basis_key, 1
    while dedup_key in belegt:
        nummer += 1
        dedup_key = f"{basis_key}|{nummer}"
    job = Job(
        company_id=comp.id if comp else None,
        company_name=comp.name if comp else name,
        title=title,
        status=status,
        found_date=date.today().isoformat(),
        dedup_key=dedup_key,
        source_note=tx("Manuell eingetragen"),
        **data,
    )
    if not flush_or_duplicate(session, lambda: session.add(job)):
        # P2-3: derselbe manuelle Job wurde (Race, z. B. Doppelklick) gerade eben von einer
        # anderen Anfrage angelegt — wie den Vorab-Dublettencheck oben behandeln: bestehenden
        # Job melden statt 500.
        vorhanden = session.exec(select(Job).where(Job.dedup_key == dedup_key)).first()
        if vorhanden:
            return {"existing": True, "art": "firma_titel", "job": vorhanden}
        raise HTTPException(409, tx("Job konnte wegen einer Dublette nicht angelegt werden"))
    # Schon beworben? Dann die Bewerbung gleich mit anlegen (wie beim Gmail-Ingest).
    if status == "Beworben":
        session.add(Application(
            job_id=job.id, status="Beworben",
            applied_date=(payload.get("applied_date") or date.today().isoformat()),
            channel=payload.get("channel") or None,
        ))
    session.commit()
    session.refresh(job)
    return {"existing": False, "job": job}


def _artefakt_iso(v):
    """datetime → ISO-String; Strings/None unverändert (für einheitliche Sortierung)."""
    if v is None:
        return None
    return zeit.iso_utc(v) if hasattr(v, "isoformat") else str(v)


def _datei_sortkey(item):
    """Sortier-Schlüssel für die gemischte Datei-Liste (echte JobFile-Rows + virtuelle Dicts)."""
    c = item.get("created_at") if isinstance(item, dict) else getattr(item, "created_at", None)
    return c.isoformat() if hasattr(c, "isoformat") else (str(c) if c else "")


def _virtuelle_dateien(job, company, cvs, application, interviews, transcripts):
    """Registrierte Artefakt-Pfade als VIRTUELLE Datei-Einträge (Phase 16) — für „Dateien &
    Dokumente" ohne Doppel-Buchführung. Nicht löschbar (string-id, virtual=True). Transkript-
    Uploads bleiben außen vor (haben eigene Liste/echte Rows)."""
    out = []

    def add(quelle, pk, slot, kind, path, created_at, note):
        if not path:
            return
        out.append({
            "id": f"virt-{quelle}-{pk}-{slot}",
            "virtual": True,
            "kind": kind,
            "filename": str(path).rsplit("/", 1)[-1],
            "file_path": path,
            "created_at": _artefakt_iso(created_at),
            "note": note,
        })

    if job:
        add("job", job.id, "posting", "Stellenausschreibung", job.posting_snapshot_path,
            job.updated_at or job.created_at, tx("Anzeige-Kopie"))
    if company:
        add("company", company.id, "fit", tx("Analyse"), company.fit_analysis_path,
            company.updated_at or company.created_at, tx("Company-Fit-Dashboard"))
    for c in cvs or []:
        lang = (c.language or "").upper()
        cv_note = f"CV {lang}".strip()
        add("cv", c.id, "docx", "CV (.docx)", c.file_path, c.created_at, cv_note)
        add("cv", c.id, "pdf", "CV (.pdf)", c.pdf_path, c.created_at, cv_note)
        add("cv", c.id, "match", tx("Analyse"), c.match_dashboard_path, c.created_at, tx("Match-Dashboard"))
        add("cv", c.id, "ats", tx("Analyse"), c.ats_scan_path, c.created_at, tx("ATS-Scan"))
    if application:
        add("app", application.id, "cover", tx("Anschreiben (.docx)"),
            application.cover_letter_path, application.created_at, tx("Anschreiben"))
        # cover_letter_pdf_path kommt in Stufe D — getattr bleibt vorwärtskompatibel.
        add("app", application.id, "coverpdf", tx("Anschreiben (.pdf)"),
            getattr(application, "cover_letter_pdf_path", None), application.created_at, tx("Anschreiben"))
    for iv in interviews or []:
        add("interview", iv.id, "prep", "Briefing", iv.prep_path, iv.created_at, tx("Runde {runde}", runde=iv.runde))
    for t in transcripts or []:
        add("transcript", t.id, "debrief", "Debrief", t.debrief_path, t.created_at, "Debrief")
        # Phase 30: neuer Transkript-Report (Basis/Vollversion) — Altbestand ohne report_path zeigt
        # weiter nur den Debrief-Eintrag oben (add() überspringt leere Pfade selbst).
        add("transcript", t.id, "report", tx("Transkript-Report"), t.report_path, t.created_at, tx("Transkript-Report"))
    return out


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(404, tx("Job nicht gefunden"))
    company = session.get(Company, job.company_id) if job.company_id else None
    contacts = session.exec(select(Contact).where(Contact.job_id == job_id)).all()
    if company:
        contacts = list(contacts) + [c for c in session.exec(select(Contact).where(Contact.company_id == company.id)).all() if c.job_id is None]
    cvs = session.exec(select(CVVersion).where(CVVersion.job_id == job_id)).all()
    application = session.exec(select(Application).where(Application.job_id == job_id)).first()
    emails = []
    if application:
        emails = session.exec(select(Email).where(Email.application_id == application.id)).all()
    interviews = session.exec(select(Interview).where(Interview.job_id == job_id)).all()
    interviews = sorted(interviews, key=lambda i: (i.runde, i.scheduled_at or ""))
    transcripts = session.exec(select(Transcript).where(Transcript.job_id == job_id)).all()
    transcripts = sorted(transcripts, key=lambda t: (t.recorded_at or "", t.id), reverse=True)
    real_files = session.exec(select(JobFile).where(JobFile.job_id == job_id)).all()
    # Union aus echten Uploads + virtuellen Einträgen aus registrierten Artefakt-Pfaden (Phase 16).
    files = list(real_files) + _virtuelle_dateien(job, company, cvs, application, interviews, transcripts)
    files = sorted(files, key=_datei_sortkey, reverse=True)
    return {
        "job": job,
        "company": company,
        "contacts": contacts,
        "cv_versions": cvs,
        "application": application,
        "emails": emails,
        "interviews": interviews,
        "transcripts": transcripts,
        "files": files,
    }


# ── CV-Editier-Checkpoint (Phase 46 Stufe B) ────────────────────────────────────────────
@app.get("/api/jobs/{job_id}/cv-entwurf")
def cv_entwurf(job_id: int, session: Session = Depends(get_session)):
    """Jüngste CVVersion MIT entwurf_text für diesen Job — bewusst NICHT auf status=entwurf
    gefiltert (Design-Entscheidung 6 wörtlich: „mit entwurf_text"): `cv-erstellen` braucht
    dieselbe Row auch für ein „erneut erstellen" auf einer bereits status=fertig-Version (der
    gespeicherte Entwurf bleibt erhalten, ein erneuter Lauf ist idempotent — s.
    `cv_export.entwurf_zurueckschreiben`/`export`). `null`, wenn noch kein CV-Match lief."""
    if not session.get(Job, job_id):
        raise HTTPException(404, tx("Job nicht gefunden"))
    return session.exec(
        select(CVVersion).where(CVVersion.job_id == job_id, CVVersion.entwurf_text.is_not(None))
        .order_by(CVVersion.created_at.desc())
    ).first()


@app.patch("/api/cv-versions/{cv_id}/entwurf")
def update_cv_entwurf(cv_id: int, payload: dict, session: Session = Depends(get_session)):
    """Absatz-Edits des Nutzers am Entwurf speichern — in JEDEM Status (P2-45, 25.09.2026).

    Bis dahin sperrte ein 409 alles außer `status=entwurf`, mit der Begründung, nach
    „CV erstellen“ sei die Entwurfs-`.docx` umbenannt und ein Edit liefe ins Leere. Das trifft
    nicht zu: `cv_export.entwurf_anwenden()` schreibt in `cv.file_path`, und der zeigt nach dem
    Export auf die FERTIGE Datei; `export()` erkennt seinen eigenen Zielnamen
    (`_ist_eigener_zielname`) und ist damit idempotent. `GET /api/jobs/{id}/cv-entwurf` liefert
    die Row ohnehin statusunabhängig, und `cv-erstellen/SKILL.md` Schritt 1 nennt „erneut
    erstellen auf einer bereits fertigen Version" als vorgesehenen Fall.

    Anlass (Rückmeldung vom 25.09.): „Ich benötige dieses Fenster, um Änderungen zu machen.“ Damit ist
    der CV-Editor so frei wie der Anschreiben-Editor darunter, der nie ein Status-Gate hatte.

    Geschrieben wird NUR `entwurf_text` — Dateien fasst dieser Endpunkt nicht an. Word, PDF und
    ATS-Scan entstehen erst beim nächsten `cv-erstellen`-Lauf, den der Nutzer bewusst auslöst."""
    cv = session.get(CVVersion, cv_id)
    if not cv:
        raise HTTPException(404, tx("CV-Version nicht gefunden"))
    entwurf_text = payload.get("entwurf_text")
    if entwurf_text is None:
        raise HTTPException(422, tx("entwurf_text fehlt"))
    cv.entwurf_text = json.dumps(entwurf_text, ensure_ascii=False)
    session.add(cv)
    session.commit()
    session.refresh(cv)
    return cv


@app.patch("/api/applications/{application_id}")
def update_application(application_id: int, payload: dict, session: Session = Depends(get_session)):
    """Anschreiben-Inline-Editor (Phase 48 Stufe A): speichert `cover_letter_text`. Anders als
    beim CV-Entwurf kein Status-Gate — das Anschreiben ist freier Text, jederzeit editierbar,
    auch nachdem Word/PDF schon erzeugt wurden (erneutes „Word + PDF erzeugen" holt den Stand nach)."""
    application = session.get(Application, application_id)
    if not application:
        raise HTTPException(404, tx("Bewerbung nicht gefunden"))
    editable = {"cover_letter_text"}
    for k, v in payload.items():
        if k in editable:
            setattr(application, k, v)
    session.add(application)
    session.commit()
    session.refresh(application)
    return application


@app.get("/api/applications/{application_id}/cover-letter-text-from-docx")
def cover_letter_text_from_docx(application_id: int, session: Session = Depends(get_session)):
    """Fallback „Text aus vorhandener .docx laden" — für Bestandsanschreiben ohne cover_letter_text.
    Rein lesend, kein State-Change (der Nutzer übernimmt/speichert den Text erst bewusst per PATCH)."""
    from pipeline.cover_letter_render import extract_text_from_docx

    application = session.get(Application, application_id)
    if not application:
        raise HTTPException(404, tx("Bewerbung nicht gefunden"))
    if not application.cover_letter_path:
        raise HTTPException(422, tx("Kein Anschreiben-Dokument vorhanden"))
    docx_path = (_PROJECT_ROOT / application.cover_letter_path).resolve()
    if not docx_path.exists():
        raise HTTPException(404, tx("Anschreiben-Datei fehlt auf der Platte"))
    return {"text": extract_text_from_docx(docx_path)}


# Job-Status, die auch eine BEWERBUNG beschreiben koennen — dieselbe Menge, die der Mail-Ingest
# setzt (`gmail_ingest`: Absage→Absage, Einladung→Interview, Angebot→Angebot,
# Eingangsbestaetigung→Beworben). „Kein Match“, „Geparkt“ oder „Nicht verfuegbar“ beschreiben
# dagegen die STELLE; sie auf die Bewerbung zu schreiben waere eine neue Sorte Unsinn.
_APP_STATUS_UEBERNAHME = {"Beworben", "Interview", "Angebot", "Absage"}

_JOB_LOG_LABELS = {"status": "Status", "follow_up_date": "Fällig am", "salary": "Gehalt", "url": "URL",
                   "career_url": "Karriereseite", "portal_closed": "Portal geschlossen",   # Phase 73
                   "availability_status": "Verfügbarkeit"}   # Phase 74
_JOB_LOG_FIELDS = {"next_step", "follow_up_date", "notes", "status", "salary", "url",
                   "career_url", "portal_closed",   # Phase 73
                   "availability_status"}   # Phase 74 — availability_checked_at BEWUSST NICHT drin
                                             # (reines Systemdatum, s. Design-Entscheidung 4 der Spec:
                                             # ein wöchentlicher Re-Check ohne Statuswechsel loggt nicht)


@app.patch("/api/jobs/{job_id}")
def update_job(job_id: int, payload: dict, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(404, tx("Job nicht gefunden"))
    if "status" in payload:
        _validiere_status(payload["status"], ALLOWED_JOB_STATUSES)
    if "portal_closed" in payload:
        # Phase 73: VOR dem generischen setattr-Loop robust auf 0/1 casten, damit sowohl der
        # Log-Diff unten als auch setattr() mit dem sauberen Wert arbeiten (Muster seniority/
        # work_model direkt darunter).
        payload["portal_closed"] = _normalisiere_portal_closed(payload["portal_closed"])
    if "availability_status" in payload and payload["availability_status"] is not None:
        # None bleibt erlaubt (Rückbau/Reset des Systemwerts) — nur ein gesetzter Fremdwert
        # außerhalb der Wertemenge löst den 422 aus (Muster status/portal_closed).
        _validiere_status(payload["availability_status"], ALLOWED_AVAILABILITY, "availability_status")
    from app import normalize as N
    editable = {"status", "next_step", "plan_ab", "match_score", "match_rationale",
                "source_note", "follow_up_date", "notes", "gut_feeling",
                "url", "verified_at", "verify_note",    # Phase 14 D: URL/Verify korrigierbar
                "salary",                               # Phase 19 B: Gehalt-Rückfluss aus der Anzeige
                "seniority", "work_model", "relocation_needed", "tab", "portal",  # Phase 20: Eckdaten-Edit
                "published_date", "found_date", "status_raw",
                "career_url", "portal_closed",          # Phase 73: Karriereseiten-Fallback
                "availability_status", "availability_checked_at"}   # Phase 74: Beworben-Check

    # Normalisierte Paare konsistent halten (Projekt-Konvention norm + *_raw) — vor dem generischen Loop.
    if "seniority" in payload:
        norm, raw = N.norm_seniority(payload["seniority"])
        job.seniority = norm or payload["seniority"]
        job.seniority_raw = raw or payload["seniority"]
        payload.pop("seniority")
    if "work_model" in payload:
        job.work_model = N.norm_work_model(payload["work_model"]) or payload["work_model"]
        payload.pop("work_model")
    if "tab" in payload:
        # P2-51 (V7): Freitext/eine veraltete Umkreis-Bezeichnung auf die aktuelle abbilden
        # (Muster seniority/work_model oben) — greift auch, wenn ein Client noch das alte Label
        # sendet (z. B. eine offene Job-Detail-Seite von vor einer Umbenennung).
        from pipeline import suchprofil
        job.tab = suchprofil.tab_normalisieren(payload["tab"], suchprofil.aktuelles_umkreis_label(session))
        payload.pop("tab")
    # Verifikation zurücksetzen, wenn die URL sich MANUELL ändert (Phase 20, Design 2). ABER nicht,
    # wenn der Payload eigene verify-Felder mitbringt — der Skill-Pfad (Phase 14 D) korrigiert url +
    # verify_note gemeinsam; sonst würde das „✓ geprüft"-Badge nach einer manuellen URL-Änderung lügen.
    if "url" in payload and payload["url"] != job.url and "verify_note" not in payload:
        job.verified_at = None
        job.verify_note = None

    # Phase 24 A: Änderungen an next_step/follow_up_date/notes/status/salary/url automatisch ins
    # Job-Log schreiben (EIN Eintrag je PATCH, Muster OutreachLog/update_outreach) — vor dem Setzen
    # vergleichen, damit der alte Wert noch verfügbar ist.
    changes = []
    for k, v in payload.items():
        if k in _JOB_LOG_FIELDS:
            old = getattr(job, k)
            if (old or "") != (v or ""):
                if k == "notes":
                    changes.append(tx("Notizen aktualisiert"))
                elif k == "next_step":
                    changes.append(tx("Nächster Schritt: „{v}“", v=v) if v
                               else tx("Nächster Schritt entfernt"))
                elif k == "portal_closed":
                    # Phase 73, Design-Entscheidung 5: Ja/Nein im Log, NICHT die rohen 0/1-Werte.
                    changes.append(f"{uebersetzt(_JOB_LOG_LABELS[k])}: {tx('Ja') if old else tx('Nein')} → "
                                   f"{tx('Ja') if v else tx('Nein')}")
                elif k == "availability_status":
                    # Phase 74, Design-Entscheidung 4: Anzeige-Labels im Log, NICHT die rohen Codes;
                    # None (noch nie geprüft) → „—" (Muster AVAILABILITY_LABELS.get-Fallback).
                    changes.append(f"{uebersetzt(_JOB_LOG_LABELS[k])}: "
                                   f"{uebersetzt(AVAILABILITY_LABELS.get(old, '—'))} → "
                                   f"{uebersetzt(AVAILABILITY_LABELS.get(v, '—'))}")
                else:
                    changes.append(f"{uebersetzt(_JOB_LOG_LABELS[k])}: {old or '—'} → {v or '—'}")

    for k, v in payload.items():
        if k in editable:
            setattr(job, k, v)
    from datetime import datetime
    job.updated_at = datetime.utcnow()

    # Bewerbungsstatus mitziehen (P2-29). Bis hierher setzte ihn AUSSCHLIESSLICH der Mail-Ingest
    # (`gmail_ingest`: `app.status = rec["job_status"]`); im Frontend ist er reine Anzeige, und
    # `PATCH /api/applications` kann ihn bewusst nicht. Wer eine Absage-Mail erst nachtraeglich
    # ueber „Stelle zuordnen" verknuepfte und dann den dort vorgeschlagenen Job-Status uebernahm,
    # liess die Bewerbung auf „Beworben" stehen — ein Bestandsabgleich vom 08.09.2026 zeigte
    # mehrere solche Faelle, die in jeder Auswertung als laufend mitzaehlten.
    #
    # Nur bei `_APP_STATUS_UEBERNAHME` und nur, wenn der Wert wirklich abweicht — sonst entstuende
    # bei jedem PATCH ein Log-Eintrag ohne Aussage.
    if "status" in payload and payload["status"] in _APP_STATUS_UEBERNAHME:
        bewerbung = session.exec(
            select(Application).where(Application.job_id == job_id)
        ).first()
        if bewerbung and bewerbung.status != payload["status"]:
            changes.append(tx("Bewerbung: {alt} → {neu}", alt=bewerbung.status or '—', neu=payload['status']))
            bewerbung.status = payload["status"]
            session.add(bewerbung)

    if changes:
        session.add(JobLog(job_id=job_id, eintrag=" · ".join(changes), art="auto"))
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: int, session: Session = Depends(get_session)):
    """Soft-Delete (Phase 32 B): `deleted_at` setzen, die Row bleibt als DEDUP-TOMBSTONE erhalten
    (Muster Phase 28 A) — dedup_key/URL/Firma+Titel wirken weiter gegen Wieder-Ingest desselben
    Treffers (`pipeline.ingest` filtert NICHT nach deleted_at, s. dort). Alle Artefakt-Dateien des
    Jobs wandern in den Papierkorb; Kinder-Rows (Application/Interview/Transcript/JobLog/JobFile/
    CVVersion/JobChat) werden hart gelöscht. Emails BLEIBEN (Postfach-Historie/Antwortquoten-
    Statistik) — nur job_id/application_id auf NULL. AgentTask-Rows bleiben unverändert (Kosten-
    Historie im Task-Center, tote Job-Links sind dort tolerant — get_job liefert Gelöschte weiter
    aus). Company-Fit der Firma bleibt unangetastet (gehört der Firma, andere Jobs nutzen ihn)."""
    from datetime import datetime
    job = session.get(Job, job_id)
    if not job or job.deleted_at:
        raise HTTPException(404, tx("Stelle nicht gefunden oder bereits gelöscht"))

    application = session.exec(select(Application).where(Application.job_id == job_id)).first()
    interviews = session.exec(select(Interview).where(Interview.job_id == job_id)).all()
    transcripts = session.exec(select(Transcript).where(Transcript.job_id == job_id)).all()
    cvversions = session.exec(select(CVVersion).where(CVVersion.job_id == job_id)).all()
    jobfiles = session.exec(select(JobFile).where(JobFile.job_id == job_id)).all()
    joblogs = session.exec(select(JobLog).where(JobLog.job_id == job_id)).all()
    jobchats = session.exec(select(JobChat).where(JobChat.job_id == job_id)).all()

    # Artefakt-Pfade VORAB einsammeln — verschoben wird ERST NACH dem Commit (weiter unten).
    # Phase 64A / P1-7: Reihenfolge bewusst DB-zuerst-dann-Move (vorher war es umgekehrt).
    # Begründung (nicht zurückdrehen, ohne das neu zu bewerten): Committet die DB zuerst,
    # erzeugt ein späterer Move-Fehlschlag eine VERWAISTE DATEI (Datei bleibt liegen, DB sagt
    # korrekt „gelöscht") statt einer TOTEN DB-REFERENZ (Job weiterhin sichtbar, Datei schon
    # weg). Verwaiste Dateien fließen bereits in die Alarmschwelle des Cleanups ein
    # (cleanup.py::orphans, Schwelle 10) — tote Referenzen taten das bisher nicht (jetzt durch
    # dieselbe Phase ergänzt, s. cleanup.py::scan). Der umgekehrte Fehlerfall (Move zuerst) wäre
    # unsichtbar: die DB-Zeile bliebe eine Karteileiche, ohne dass ein Werkzeug sie meldet.
    pfade = []
    if application:
        pfade += [application.cover_letter_path, application.cover_letter_pdf_path]
    pfade += [iv.prep_path for iv in interviews]
    pfade += [p for t in transcripts for p in (t.file_path, t.debrief_path, t.report_path)]
    pfade += [p for cv in cvversions
              for p in (cv.file_path, cv.pdf_path, cv.match_dashboard_path, cv.ats_scan_path)]
    pfade += [jf.file_path for jf in jobfiles]
    # job.posting_snapshot_path überlebt (die Job-Row bleibt als Tombstone) — Pfad vorab merken
    # (Move erst nach dem Commit), NULLEN passiert schon jetzt als Teil der DB-Änderung unten
    # (Design-Entscheidung 1: das Feld soll nach dem Löschen nicht ins Leere zeigen).
    pfade.append(job.posting_snapshot_path)
    job.posting_snapshot_path = None

    # Emails BEHALTEN — nur entkoppeln (Postfach-Historie/Antwortquoten-Statistik bleiben intakt).
    app_ids = [application.id] if application else []
    emails = session.exec(
        select(Email).where(or_(Email.job_id == job_id, Email.application_id.in_(app_ids)))
    ).all()
    for e in emails:
        e.job_id = None
        e.application_id = None
        session.add(e)

    for row in jobchats:
        session.delete(row)
    for row in joblogs:
        session.delete(row)
    for row in jobfiles:
        session.delete(row)
    for row in transcripts:
        session.delete(row)
    for row in interviews:
        session.delete(row)
    for row in cvversions:
        session.delete(row)
    if application:
        session.delete(application)

    job.deleted_at = datetime.utcnow().isoformat()
    job.updated_at = datetime.utcnow()
    session.add(job)
    session.commit()

    # Erst NACH dem Commit verschieben (Begründung s. Kommentar oben). Jede Datei EINZELN
    # abgesichert (F4/F5): ein Fehlschlag bei Datei 3 von 5 darf Dateien 4+5 nicht verhindern —
    # vorher riss eine ungefangene Exception aus `_in_papierkorb` die ganze Schleife ab.
    dateien_verschoben = 0
    dateien_fehlgeschlagen = 0
    for p in pfade:
        try:
            if _in_papierkorb(p):
                dateien_verschoben += 1
        except OSError as exc:
            dateien_fehlgeschlagen += 1
            print(tt("[papierkorb] FEHLER beim Verschieben von '{pfad}' (Job {job_id}, delete_job): {fehler}", pfad=p, job_id=job_id, fehler=exc), flush=True)

    return {
        "ok": True,
        "counts": {
            "dateien": dateien_verschoben,
            "interviews": len(interviews),
            "transkripte": len(transcripts),
            "cv_versionen": len(cvversions),
            "jobfiles": len(jobfiles),
            "emails_entkoppelt": len(emails),
        },
        "dateien_fehlgeschlagen": dateien_fehlgeschlagen,
    }


@app.get("/api/jobs/{job_id}/log")
def job_log(job_id: int, session: Session = Depends(get_session)):
    """Notizen-/Änderungs-Verlauf eines Jobs, neueste zuerst."""
    return session.exec(select(JobLog).where(JobLog.job_id == job_id)
                        .order_by(JobLog.created_at.desc(), JobLog.id.desc())).all()


@app.post("/api/jobs/{job_id}/log")
def job_log_add(job_id: int, payload: dict, session: Session = Depends(get_session)):
    """Manuellen Notiz-Eintrag anfügen."""
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(404, tx("Job nicht gefunden"))
    eintrag = (payload.get("eintrag") or "").strip()
    if not eintrag:
        raise HTTPException(422, tx("eintrag fehlt"))
    row = JobLog(job_id=job_id, eintrag=eintrag, art="manuell")
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@app.patch("/api/companies/{company_id}")
def update_company(company_id: int, payload: dict, session: Session = Depends(get_session)):
    """Phase 20: Situation (+ Notizen) editierbar — fürs Situation-Feld der Eckdaten-Karte.
    Bewusst kleines editable-Set. `situation` läuft durch norm_situation (norm + raw-Paar)."""
    comp = session.get(Company, company_id)
    if not comp:
        raise HTTPException(404, tx("Firma nicht gefunden"))
    from app import normalize as N
    if "situation" in payload:
        norm, raw = N.norm_situation(payload["situation"])
        comp.situation = norm
        comp.situation_raw = raw or payload["situation"]
    if "notes" in payload:
        comp.notes = payload["notes"]
    from datetime import datetime
    comp.updated_at = datetime.utcnow()
    session.add(comp)
    session.commit()
    session.refresh(comp)
    return comp


# ── Follow-ups (fällige nächste Schritte) ──────────────────────────────────────
@app.get("/api/followups")
def followups(session: Session = Depends(get_session)):
    """Fällige Aktionen — zweiteilig (Phase 22): `jobs` (Fälligkeitsdatum, aktiv) UND `netzwerk`
    (Netzwerk-Kontakte mit next_action_date). Beide aufsteigend; `overdue` = Datum ≤ heute."""
    today = date.today().isoformat()
    jobs = [j for j in session.exec(select(Job)).all()
            if j.follow_up_date and j.status not in TERMINAL_STATUSES and not j.deleted_at]
    jobs.sort(key=lambda j: (j.follow_up_date, (j.company_name or "").lower()))
    job_out = [
        {
            "id": j.id, "company_name": j.company_name, "title": j.title,
            "status": j.status, "match_score": j.match_score,
            "next_step": j.next_step, "notes": j.notes,
            "follow_up_date": j.follow_up_date, "overdue": j.follow_up_date <= today,
        }
        for j in jobs
    ]
    ncs = [n for n in session.exec(
        select(NetworkContact).where(NetworkContact.deleted_at.is_(None))).all()
        if n.next_action_date]
    ncs.sort(key=lambda n: (n.next_action_date, (n.name or "").lower()))
    nc_out = [
        {
            "id": n.id, "name": n.name, "unternehmen": n.unternehmen,
            "next_action": n.next_action, "next_action_date": n.next_action_date,
            "overdue": n.next_action_date[:10] <= today,
        }
        for n in ncs
    ]
    return {"jobs": job_out, "netzwerk": nc_out}


# ── Agent-Tasks (Skills headless aus der Web-App starten, Phase 8) ─────────────
def _task_dto(t: AgentTask, log: Optional[list] = None, job: Optional[Job] = None) -> dict:
    d = {
        "id": t.id, "kind": t.kind, "job_id": t.job_id, "status": t.status,
        # Firma/Titel statt der internen Job-Id in der Task-Center-Anzeige (Vorgabe vom 11.07.2026).
        "company_name": job.company_name if job else None,
        "job_title": job.title if job else None,
        "prompt": t.prompt, "error": t.error, "exit_code": t.exit_code,
        "duration_s": t.duration_s, "num_turns": t.num_turns, "cost_usd": t.cost_usd, "tokens": t.tokens,
        "chain_id": t.chain_id, "chain_label": uebersetzt(t.chain_label), "chain_pos": t.chain_pos,
        "depends_on": t.depends_on,
        "retry_count": t.retry_count or 0,
        "max_retries": agent_runner.MAX_RETRIES if agent_runner.PROMPTS.get(t.kind, {}).get("retryable") else 0,
        "label": uebersetzt(agent_runner.PROMPTS.get(t.kind, {}).get("label", t.kind)),
        # P2-20: iso_utc statt isoformat — ein handgebautes dict geht am UtcZeit-Mixin
        # vorbei, ohne diesen Aufruf blieben die Zeiten im Task-Center ohne Zeitzone.
        "created_at": zeit.iso_utc(t.created_at),
        "started_at": zeit.iso_utc(t.started_at),
        "finished_at": zeit.iso_utc(t.finished_at),
        "log_path": t.log_path,
        "result": None,
    }
    if t.result_json:                       # Kurz-Ergebnis des Laufs für die UI
        try:
            d["result"] = json.loads(t.result_json).get("result")
        except json.JSONDecodeError:
            pass
    if log is not None:
        d["log"] = log
    return d


@app.get("/api/task-kinds")
def task_kinds():
    """Alle Task-Arten inkl. der NICHT headless-fähigen (mit Begründung) — für die UI."""
    kinds = [{"kind": k, "label": uebersetzt(v["label"]), "needs_job": v.get("needs_job", False),
              "needs_params": list(v.get("needs_params", ())),
              "headless": bool(v.get("headless")), "reason": uebersetzt(v.get("reason"))}
             for k, v in agent_runner.PROMPTS.items()]
    recipes = [{"kind": k, "label": uebersetzt(v["label"]), "needs_job": v.get("needs_job", False),
                "steps": v["steps"], "headless": True, "is_recipe": True,
                # P2-41: optionale Bausteine als Task-Art-Liste — leer für Rezepte ohne
                # optional-Block (z. B. tageslauf).
                "optional": list(v.get("optional", {}).values())}
               for k, v in agent_runner.RECIPES.items()]
    return {"kinds": kinds, "recipes": recipes}


@app.get("/api/agent-status")
def agent_status(session: Session = Depends(get_session)):
    """Guardrail-Stand für die UI: heute verbraucht, Limits, Parallelität."""
    return agent_runner.budget_status(session)


def _guard_doppellauf(session: Session, kinds: list, job_id) -> None:
    aktiv = session.exec(
        select(AgentTask).where(AgentTask.kind.in_(kinds), AgentTask.job_id == job_id,
                                AgentTask.status.in_(("queued", "running")))
    ).first()
    if aktiv:
        raise HTTPException(409, tx("'{kind}' läuft für diesen Job bereits (Task {id})", kind=aktiv.kind, id=aktiv.id))


def _guard_tagesbudget(session: Session) -> None:
    """Tages-Notbremse (Phase 8.4). Blockt nur NEUE Läufe — laufende bleiben unangetastet.

    409 wie beim Doppellauf: das ist ein Zustandskonflikt, kein Eingabefehler.
    """
    grund = agent_runner.budget_ueberschritten(session)
    if grund:
        raise HTTPException(409, grund)


# Unterlagen-Arten mit Human-in-the-Loop-Guard bei niedrigem Match (27.07.2026). Echtfall:
# eine Parallel-Session erzeugte per Batch volle Unterlagen (Company-Fit → Beirat → CV →
# Anschreiben) für Match-1-Vertriebsrollen — die Triage war übersprungen.
# „beirat-stellen-check" bleibt bewusst frei: der Beirat IST das Werkzeug, solche Stellen zu
# bewerten und auszusortieren (Phase 40).
# NUR Einzel-Task-Arten (aus `agent_runner.PROMPTS`) gehören hier rein — KEINE Ketten-Namen aus
# `RECIPES`: `create_task()` löst ein Rezept vorher in `RECIPES[kind]["steps"]` auf und prüft die
# Schritte, die ohnehin unten stehen. Ein Rezept-Name wäre wirkungslos (Phase 83: „job-deepdive"
# stand hier tot — die Kette heißt „deepdive").
LOW_MATCH_KINDS = {"firma-pruefen", "cv-match", "cv-erstellen", "anschreiben-erstellen"}
LOW_MATCH_SCHWELLE = 2


def _guard_low_match(job, kinds: set, params: dict) -> None:
    """409 mit Marker „LOW_MATCH", wenn ein Unterlagen-Lauf eine Stelle mit Zielstellen-Fit ≤ 2
    trifft und kein ausdrückliches Override mitkommt (`params.low_match_ok=true`) — Warnung mit
    Ausweg, kein Verbot: `AgentTaskButton` fragt nach und wiederholt mit Override.
    Unbewertete Jobs (match_score None) bleiben frei — es gibt keine Bewertung zu
    überstimmen. Gilt für Einzel-Tasks UND Ketten (betroffene Schritt-Menge).
    Marker und Feldname bleiben `LOW_MATCH`/`match_score` (API- und DB-Kontrakt, Phase 84) —
    umbenannt wurde nur, was der Nutzer liest."""
    if job is None or not (kinds & LOW_MATCH_KINDS):
        return
    if job.match_score is None or job.match_score > LOW_MATCH_SCHWELLE:
        return
    if (params or {}).get("low_match_ok"):
        return
    grund = tx(" — Bewertung: „{wert}…“", wert=job.match_rationale[:100]) if job.match_rationale else ""
    raise HTTPException(409, (
        tx("LOW_MATCH: Zielstellen-Fit {match_score}/5{grund} Unterlagen-Lauf für diese Stelle "
           "nur mit ausdrücklicher Bestätigung (params.low_match_ok=true).", match_score=job.match_score, grund=grund)
    ))


# P2-75: Unterlagen-Arten, die den Anzeigentext der Stelle brauchen. Bewusst dieselbe Menge wie
# LOW_MATCH_KINDS, aber eine eigene Konstante: der Zweck ist ein anderer (Anzeigentext statt
# Zielstellen-Fit), und die beiden Mengen dürfen künftig auseinanderlaufen. Auch hier nur
# Einzel-Task-Arten, keine Ketten-Namen — `create_task()` übergibt die aufgelöste Schrittmenge.
ANZEIGE_KINDS = {"firma-pruefen", "cv-match", "cv-erstellen", "anschreiben-erstellen"}


async def _guard_anzeigentext(job, kinds: set, params: dict, session: Session) -> None:
    """P2-75: 409 mit Marker „ANZEIGE_FEHLT“, wenn ein Unterlagen-Lauf startet, obwohl der
    Anzeigentext der Stelle nicht vorliegt und das BMS ihn auch nicht nachholen konnte.
    Ablauf: erst `posting_snapshot.anzeigentext_sichern()` (nichts zu tun, wenn der Snapshot schon
    Text hat, sonst ein Nachhol-Abruf mit Wiederholung), dann nur bei `fehlt` der Halt. Der Halt
    kommt beim Start, nicht im Lauf: kein Claude-Lauf, keine Kosten, der Nutzer entscheidet sofort.
    Ausweg wie bei LOW_MATCH: `params.ohne_anzeigentext_ok=true` (dann auch kein Netzabruf).
    Der Abruf kann mit Pausen gut 30 s dauern und läuft deshalb im Threadpool — synchron würde er
    den ganzen Server anhalten. `anzeigentext_sichern` öffnet seine eigene Session; die hier
    geladene Stelle wird danach neu gelesen (der Snapshot-Pfad kann sich geändert haben).
    Zur Aufrufzeit über das Modulattribut aufgerufen, damit Tests es ersetzen können."""
    if job is None or not (kinds & ANZEIGE_KINDS):
        return
    if (params or {}).get("ohne_anzeigentext_ok"):
        return
    try:
        erg = await run_in_threadpool(posting_snapshot.anzeigentext_sichern, job.id)
    except Exception as e:                  # noqa: BLE001 — Rückfrage statt 500, der Nutzer entscheidet
        print(tt("[anzeigentext] Job {job_id}: {art}: {fehler}", job_id=job.id, art=type(e).__name__, fehler=e), flush=True)
        erg = {"status": "fehlt", "grund": tx("Der Abruf der Anzeige ist fehlgeschlagen.")}
    session.refresh(job)
    if erg.get("status") != "fehlt":
        return
    grund = (erg.get("grund") or "").strip()
    grund_teil = f"{grund} " if grund else ""
    raise HTTPException(409, (
        tx("ANZEIGE_FEHLT: Der Anzeigentext dieser Stelle liegt nicht vor. {grund_teil}Ohne ihn "
           "arbeiten Firma-Prüfung, CV-Match, CV und Anschreiben nur mit Titel und Firma. "
           "(params.ohne_anzeigentext_ok=true)", grund_teil=grund_teil)
    ))


@app.post("/api/tasks")
async def create_task(payload: dict, session: Session = Depends(get_session)):
    """Einzel-Task oder Kette („Rezept") einreihen. Doppelläufe je Job werden geblockt (409)."""
    kind = (payload.get("kind") or "").strip()
    job_id = payload.get("job_id")
    params = payload.get("params") or {}
    job = session.get(Job, job_id) if job_id is not None else None
    if job_id is not None and not job:
        raise HTTPException(404, tx("Job nicht gefunden"))
    _guard_tagesbudget(session)     # gilt für Einzel-Tasks wie für Ketten
    # P2-41: Rezepte tragen jetzt optionale Bausteine (z. B. „anschreiben“ im Bewerbungspaket) —
    # die tatsächliche Schrittfolge hängt vom Param `mit_<baustein>` bzw. dem Standardwert aus
    # den Einstellungen ab, deshalb hier über `rezept_aufloesen()` auflösen statt den rohen
    # `RECIPES[kind]["steps"]` zu nehmen. Einmal aufgelöst, unten für Guard UND Kettenbau
    # wiederverwendet (kein zweiter Einstellungen-Read).
    if kind in agent_runner.RECIPES:
        schritte, ketten_label = agent_runner.rezept_aufloesen(
            kind, params, _unterlagen_standard(_einstellungen_singleton(session)))
    else:
        schritte, ketten_label = [kind], None
    _guard_low_match(job, set(schritte), params)
    await _guard_anzeigentext(job, set(schritte), params, session)      # P2-75

    # ── Beirats-Stellen-Check: läuft über die ENGINE, nicht den Runner (Phase 42 Stufe B,
    #    Design-Entscheidung 5 — „Erneut" im Task-Center trifft hier auf dieselbe Weiche wie
    #    der dedizierte Endpunkt POST /api/beirat/stellen-check; „beirat-debatte" hat bewusst
    #    KEINE Weiche — fällt unten in die normale PROMPTS-Prüfung und scheitert dort mit
    #    erklärendem 422, freie Debatten startet man auf /beirat).
    #    _guard_tagesbudget() oben (Zeile 767) läuft hier bereits; _beirat_stellen_check_starten()
    #    prüft ihn (Phase 62A) NOCHMAL selbst, damit der dedizierte Endpunkt denselben Schutz
    #    hat — absichtliche Doppelprüfung, s. deren Docstring, kein Bug.
    if kind == "beirat-stellen-check":
        if not job:
            raise HTTPException(422, tx("'beirat-stellen-check' braucht eine job_id"))
        d, _ = _beirat_stellen_check_starten(job, session, int(params.get("min_beitraege") or 8))
        return _task_dto(session.get(AgentTask, d.task_id), job=job)

    # ── Kette ────────────────────────────────────────────────────────────────
    if kind in agent_runner.RECIPES:
        rec = agent_runner.RECIPES[kind]
        if rec.get("needs_job") and not job_id:
            raise HTTPException(422, tx("'{kind}' braucht eine job_id", kind=kind))
        # `schritte`/`ketten_label` kommen bereits oben aus `rezept_aufloesen()` (P2-41) —
        # dieselbe aufgelöste Schrittfolge, die auch der Low-Match-Guard geprüft hat.
        _guard_doppellauf(session, schritte, job_id)
        try:
            prompts = [agent_runner.build_prompt(s, job_id, params) for s in schritte]
        except agent_runner.PromptError as e:
            raise HTTPException(422, str(e))

        chain_id = uuid.uuid4().hex[:12]
        vorher = None
        erstellt = []
        for pos, (step, prompt) in enumerate(zip(schritte, prompts), start=1):
            t = AgentTask(kind=step, job_id=job_id, prompt=prompt,
                          chain_id=chain_id, chain_label=ketten_label, chain_pos=pos,
                          depends_on=vorher,
                          params_json=json.dumps(params, ensure_ascii=False) if params else None)
            session.add(t)
            session.commit()
            session.refresh(t)
            erstellt.append(t)
            vorher = t.id
        agent_runner.enqueue(erstellt[0].id)          # Folgeschritte weckt der Vorgänger
        return {"chain_id": chain_id, "label": uebersetzt(ketten_label),
                "tasks": [_task_dto(t, job=job) for t in erstellt]}

    # ── Einzel-Task ──────────────────────────────────────────────────────────
    try:
        prompt = agent_runner.build_prompt(kind, job_id, params)
    except agent_runner.PromptError as e:
        raise HTTPException(422, str(e))
    _guard_doppellauf(session, [kind], job_id)

    t = AgentTask(kind=kind, job_id=job_id, prompt=prompt,
                  params_json=json.dumps(params, ensure_ascii=False) if params else None)
    session.add(t)
    session.commit()
    session.refresh(t)
    agent_runner.enqueue(t.id)
    return _task_dto(t, job=job)


@app.get("/api/tasks")
def list_tasks(job_id: Optional[int] = None, status: Optional[str] = None,
               kinds: Optional[str] = None, limit: int = 50,
               session: Session = Depends(get_session)):
    q = select(AgentTask)
    if job_id is not None:
        q = q.where(AgentTask.job_id == job_id)
    if status:
        q = q.where(AgentTask.status == status)
    if kinds:                                    # Phase 23: kind-Filter (kommagetrennt), inkl. Ketten-Schritte
        wanted = [k.strip() for k in kinds.split(",") if k.strip()]
        if wanted:
            q = q.where(AgentTask.kind.in_(wanted))
    tasks = session.exec(q.order_by(AgentTask.id.desc()).limit(limit)).all()
    # Batch-Lookup statt N+1: alle betroffenen Jobs in einer Query holen.
    job_ids = {t.job_id for t in tasks if t.job_id is not None}
    jobs_by_id = {j.id: j for j in session.exec(select(Job).where(Job.id.in_(job_ids))).all()} if job_ids else {}
    return [_task_dto(t, job=jobs_by_id.get(t.job_id)) for t in tasks]


@app.get("/api/tasks/summen")
def task_summen(session: Session = Depends(get_session)):
    """Kennzahlen über ALLE Läufe für die Kacheln im Task-Center. Die Liste `/api/tasks` liefert nur die letzten Läufe,
    Summen daraus blieben bei 100 stehen. Steht vor `/api/tasks/{task_id}`, sonst fiele `summen` dort als ID durch."""
    gesamt, kosten, token = session.exec(
        select(func.count(AgentTask.id), func.coalesce(func.sum(AgentTask.cost_usd), 0.0),
               func.coalesce(func.sum(AgentTask.tokens), 0))).one()
    fehlgeschlagen = session.exec(select(func.count(AgentTask.id)).where(AgentTask.status == "failed")).one()
    return {"gesamt": gesamt, "fehlgeschlagen": fehlgeschlagen, "kosten_usd": kosten, "token": token}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: int, tail: int = 200, session: Session = Depends(get_session)):
    t = session.get(AgentTask, task_id)
    if not t:
        raise HTTPException(404, tx("Task nicht gefunden"))
    job = session.get(Job, t.job_id) if t.job_id else None
    return _task_dto(t, log=agent_runner.log_tail(t, tail), job=job)


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: int, session: Session = Depends(get_session)):
    t = session.get(AgentTask, task_id)
    if not t:
        raise HTTPException(404, tx("Task nicht gefunden"))
    if t.kind.startswith("beirat-"):
        # Cancel-Weiche (Phase 42 Stufe B, Design-Entscheidung 4): In-Server-Engine statt
        # Runner-Prozess — der bestehende „Abbrechen"-Button im Task-Center bleibt derselbe.
        import beirat_engine as be
        params = json.loads(t.params_json or "{}")
        debatte_id = params.get("debatte_id")
        ok = be.stop(debatte_id) if debatte_id else False
    else:
        ok = await agent_runner.cancel(task_id)
    if not ok:
        raise HTTPException(409, tx("Task ist bereits '{status}'", status=t.status))
    return {"ok": True}


# ── KI-Chat am Job-Detail (Phase 28 D) ──────────────────────────────────────────
@app.get("/api/jobs/{job_id}/chat")
def job_chat_list(job_id: int, session: Session = Depends(get_session)):
    """Chat-Verlauf eines Jobs, chronologisch aufsteigend (klein, kein Paging nötig)."""
    if not session.get(Job, job_id):
        raise HTTPException(404, tx("Job nicht gefunden"))
    return session.exec(select(JobChat).where(JobChat.job_id == job_id)
                        .order_by(JobChat.created_at, JobChat.id)).all()


@app.post("/api/jobs/{job_id}/chat")
async def job_chat_ask(job_id: int, payload: dict, session: Session = Depends(get_session)):
    """Frage stellen: legt die user-Row an und startet kind=job-frage über den bestehenden
    Task-Pfad (Guards — Doppellauf je Job, Tagesbudget — greifen dadurch automatisch, s.
    create_task). Guards laufen VOR der user-Row: ein 409 soll keine verwaiste Frage ohne
    kommende Antwort hinterlassen (create_task() unten prüft dieselben Guards zwar redundant
    nochmal — billige SELECTs, kein Problem — statt eine eigene Kopie der Guard-Logik zu pflegen)."""
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(404, tx("Job nicht gefunden"))
    frage = (payload.get("frage") or "").strip()
    if not frage:
        raise HTTPException(422, tx("frage fehlt"))
    if len(frage) > 2000:
        raise HTTPException(422, tx("frage zu lang (max. 2000 Zeichen)"))
    _guard_tagesbudget(session)
    _guard_doppellauf(session, ["job-frage"], job_id)
    user_row = JobChat(job_id=job_id, rolle="user", text=frage)
    session.add(user_row)
    session.commit()
    session.refresh(user_row)
    # Snapshot VOR create_task(): dessen interner commit() expired user_row (SQLAlchemy
    # expire_on_commit), sonst serialisiert FastAPI die Row als {} statt mit echten Feldern.
    user_row_out = {"id": user_row.id, "job_id": user_row.job_id, "rolle": user_row.rolle,
                     "text": user_row.text, "task_id": user_row.task_id,
                     "created_at": zeit.iso_utc(user_row.created_at)}
    task_dto = await create_task({"kind": "job-frage", "job_id": job_id, "params": {"frage": frage}}, session)
    return {"user_row": user_row_out, "task": task_dto}


# ── Budget: Reporting + Steuerung (Phase 10) ───────────────────────────────────
# Reporting liest ApiCost (sync/metered) + config/budgets.yaml (Fixkosten).
# Steuerung lebt in BudgetLimit (DB) — die App ändert sie per PATCH; durchgesetzt
# wird sie zentral in pipeline.budget.ensure_budget(), das JEDER kostenpflichtige
# Client vor dem Geldausgeben aufruft.
@app.get("/api/budget")
def budget_report():
    from pipeline import budget as B
    return B.report()


@app.patch("/api/budget/limits/{provider}")
def update_budget_limit(provider: str, payload: dict, session: Session = Depends(get_session)):
    """Die Steuerungs-Schnittstelle der App. Nur bekannte (geseedete) Dienste sind steuerbar."""
    from pipeline import budget as B
    B.seed_limits()
    lim = session.exec(select(BudgetLimit).where(BudgetLimit.provider == provider)).first()
    if not lim:
        raise HTTPException(404, tx("Kein Budget-Dienst '{provider}' — steuerbar sind nur "
                                    "bekannte Dienste", provider=provider))

    editierbar = {"daily_limit_usd", "monthly_limit_usd", "enforcement", "active", "label",
                 "max_runs_per_day"}
    unbekannt = set(payload) - editierbar
    if unbekannt:
        raise HTTPException(422, tx("Nicht editierbare Felder: {liste}", liste=', '.join(sorted(unbekannt))))

    if "enforcement" in payload and payload["enforcement"] not in ("hart", "weich"):
        raise HTTPException(422, tx("enforcement muss 'hart' oder 'weich' sein"))

    for feld in ("daily_limit_usd", "monthly_limit_usd"):
        if feld in payload and payload[feld] is not None:
            try:
                wert = float(payload[feld])
            except (TypeError, ValueError):
                raise HTTPException(422, tx("{feld} muss eine Zahl oder null sein", feld=feld))
            if wert < 0:
                raise HTTPException(422, tx("{feld} darf nicht negativ sein", feld=feld))
            payload[feld] = wert

    if "max_runs_per_day" in payload and payload["max_runs_per_day"] is not None:
        try:
            wert = int(payload["max_runs_per_day"])
        except (TypeError, ValueError):
            raise HTTPException(422, tx("max_runs_per_day muss eine ganze Zahl oder null sein"))
        if wert < 0:
            raise HTTPException(422, tx("max_runs_per_day darf nicht negativ sein"))
        payload["max_runs_per_day"] = wert

    # Plausibilität gegen den ZUKÜNFTIGEN Zustand prüfen, nicht gegen den alten.
    neu_tag = payload.get("daily_limit_usd", lim.daily_limit_usd)
    neu_monat = payload.get("monthly_limit_usd", lim.monthly_limit_usd)
    if neu_tag is not None and neu_monat is not None and neu_tag > neu_monat:
        raise HTTPException(422, tx("Tageslimit (${neu_tag}) darf nicht über dem Monatslimit "
                                    "(${neu_monat}) liegen", neu_tag=format(neu_tag, '.2f'), neu_monat=format(neu_monat, '.2f')))

    for k, v in payload.items():
        setattr(lim, k, v)
    from datetime import datetime           # lokal, wie in den übrigen PATCH-Handlern dieser Datei
    lim.updated_at = datetime.utcnow()
    session.add(lim)
    session.commit()
    session.refresh(lim)
    return {"provider": lim.provider, "label": uebersetzt(lim.label), "daily_limit_usd": lim.daily_limit_usd,
            "monthly_limit_usd": lim.monthly_limit_usd, "enforcement": lim.enforcement,
            "active": lim.active, "max_runs_per_day": lim.max_runs_per_day}


@app.get("/api/budget/check/{provider}")
def budget_check(provider: str, estimated: float = 0.0):
    """Dünner Wrapper um ensure_budget — für Runner/Skills, die per HTTP prüfen."""
    from pipeline import budget as B
    return B.ensure_budget(provider, estimated)


@app.post("/api/budget/sync")
def budget_sync():
    """Apify-Verbrauch ziehen. Fehlender Token ist kein 500, sondern eine Meldung."""
    from pipeline import budget as B
    return B.sync_apify()


# ── Sucheinstellungen (Phase 49) ────────────────────────────────────────────────
# Grundsätzliche Jobsuche-Parameter (Pläne A/B/C + globaler Suchbereich/Firmengröße), editierbar
# über /einstellungen. DB ist die Quelle der Wahrheit (Muster BudgetLimit); config/suchprofile.yaml
# wird bei jedem Save daraus regeneriert (pipeline/suchprofil.py), bleibt aber der VERTRAG zur
# Jobsuche — 9 unabhängige Stellen (Skills + Python-Loader) lesen ausschließlich die YAML, nie
# die DB direkt.
# Phase 50 — Modellwahl je Funktion lebt auf DERSELBEN Einstellungen-Seite, ist aber KEIN
# Such-Parameter (kein YAML-Touch): 6 Kern-Funktionen = die 5 agent_runner-Funktionen aus
# FUNKTION_KINDS + "beirat" (eigener Aufrufpfad über beirat_engine.py, kein agent_runner-kind).
_MODELLE_FUNKTIONEN = tuple(agent_runner.FUNKTION_KINDS) + ("beirat",)

# P2-41 — Standardumfang des Bewerbungspakets (Einstellungen-Karte „Bewerbungspaket —
# Standardumfang“): die Baustein-Namen kommen DIREKT aus dem Rezept — eine Wahrheitsquelle,
# ein neuer optionaler Baustein in `agent_runner.RECIPES["bewerbungspaket"]["optional"]` ist
# damit automatisch auch in den Einstellungen bekannt. Kein YAML-Touch (wie `modelle`) —
# `unterlagen` steuert nur die Vorbelegung des Häkchens am Job-Detail, kein Such-Parameter.
_UNTERLAGEN_BAUSTEINE = tuple(agent_runner.RECIPES["bewerbungspaket"]["optional"])


def _einstellungen_singleton(session: Session) -> SuchEinstellung:
    e = session.get(SuchEinstellung, 1)
    if not e:
        from pipeline import suchprofil
        seed = suchprofil.seed_aus_yaml(suchprofil.SUCHPROFILE_PATH)
        e = SuchEinstellung(
            id=1,
            min_mitarbeiter=seed["min_mitarbeiter"],
            suchbereich_json=json.dumps(seed["suchbereich"], ensure_ascii=False),
            plaene_json=json.dumps(seed["plaene"], ensure_ascii=False),
            modelle_json=json.dumps({fn: agent_runner.MODELL_STANDARD for fn in _MODELLE_FUNKTIONEN}),
            # Phase 87 — `seed["portale"]` kommt aus `PORTALE_DEFAULT` (nicht aus der YAML,
            # s. suchprofil.seed_aus_yaml-Docstring), damit die allererste Zeile direkt die
            # sechs Standard-Portale + zwei Freizeilen trägt statt einer leeren Liste.
            portale_json=json.dumps(seed["portale"], ensure_ascii=False),
            # P2-41 — Standard „aus“ für alle Bausteine (Entscheidung Spec Abschnitt 1: das
            # Anschreiben startet NICHT automatisch im Bewerbungspaket mit).
            unterlagen_json=json.dumps({b: False for b in _UNTERLAGEN_BAUSTEINE}),
        )
        session.add(e)
        session.commit()
        session.refresh(e)
    return e


def _unterlagen_standard(e: SuchEinstellung) -> dict:
    """Standardumfang des Bewerbungspakets (P2-41): {Baustein: bool}, fehlende Bausteine mit
    False aufgefüllt, fremde Schlüssel (Altbestand, z. B. `unterlagen_json == '{}'` nach dem
    `ALTER TABLE`-Default) ignoriert.

    **Für Lese- UND Schreibpfad verwenden** — Lehre aus `_portale_liste()`: ein Merge in
    `update_einstellungen()` gegen den ROHEN DB-Wert statt gegen diese aufgefüllte Form würde
    bei einer Alt-Zeile ohne den Schlüssel wieder denselben Datenverlust riskieren, der dort
    schon einmal aufgetreten ist."""
    roh = json.loads(e.unterlagen_json) if e.unterlagen_json else {}
    return {b: bool(roh.get(b, False)) for b in _UNTERLAGEN_BAUSTEINE}


def _portale_liste(e: SuchEinstellung) -> list[dict]:
    """Die gespeicherte Portal-Liste — bei leerem Feld die acht Standard-/Frei-Zeilen.

    Phase 87: Eine Alt-Zeile aus Phase 49/50 hat `portale_json == '[]'` (das `ALTER TABLE` in
    `app/db.py::_ADD_COLUMNS` befüllt die neue Spalte nur mit dem SQL-Default) — die Defaults
    entstehen also erst hier, nicht in der DB.

    **Warum gemeinsam für Lese- UND Schreibpfad** (Fund in der echten Abnahme 21.08.2026): Die
    Auffüllung stand zuerst nur in `_einstellungen_out()`. Der Merge in `update_einstellungen()`
    las dagegen roh aus `portale_json` — bei der Alt-Zeile also aus einer LEEREN Liste. Ein Save
    einer einzelnen Zeile (genau das, was die Karte beim Ändern eines Portals schickt) hatte
    damit nichts zum Mergen und schrieb die restlichen sieben Portale weg: Die Oberfläche zeigte
    acht Zeilen, die DB kannte danach eine. Aufgefallen ist das nur, weil die Abnahme am echten
    Bestand lief — im Test war die Zeile immer schon gefüllt.
    """
    from pipeline import suchprofil
    gespeichert = json.loads(e.portale_json) if e.portale_json else []
    return gespeichert or [dict(p) for p in suchprofil.PORTALE_DEFAULT]


def _portal_adressen_nachziehen() -> list[str]:
    """P2-73 — ersetzt beim Start abgelöste Standard-Adressen in den gespeicherten Einstellungen.

    Ohne diesen Schritt bliebe ein neuer Wert in `suchprofil.PORTALE_DEFAULT` für jede bestehende
    Installation wirkungslos: Die Portal-Liste liegt dort bereits in `portale_json` und im Kopf
    der Suchprofil-Datei. Ersetzt wird nur, was wörtlich einer früheren Standard-Adresse
    entspricht (`suchprofil.standard_adressen_nachziehen`); eine vom Nutzer geänderte Adresse
    bleibt stehen.

    Legt die Einstellungs-Zeile NICHT an, wenn es sie noch nicht gibt: Das Anlegen samt Seed
    gehört dem ersten GET, und der seedet ohnehin aus den heutigen Standards. Die Datei wird
    neu geschrieben, wenn sich die Zeile geändert hat ODER im Kopf noch eine abgelöste Adresse
    steht (Zeile mit leerer Portal-Liste, s. `suchprofil.kopf_hat_fruehere_standardadresse`).
    Gibt die Schlüssel der betroffenen Portale zurück, leer heißt „nichts zu tun“."""
    from pipeline import suchprofil
    with Session(engine) as session:
        e = session.get(SuchEinstellung, 1)
        if not e:
            return []
        try:
            gespeichert = json.loads(e.portale_json) if e.portale_json else []
        except ValueError:
            gespeichert = []
        geaendert: list[str] = []
        if isinstance(gespeichert, list) and gespeichert:
            neu, geaendert = suchprofil.standard_adressen_nachziehen(gespeichert)
            if geaendert:
                e.portale_json = json.dumps(neu, ensure_ascii=False)
                session.add(e)
                session.commit()
                session.refresh(e)
        kopf_veraltet = suchprofil.kopf_hat_fruehere_standardadresse()
        if geaendert or kopf_veraltet:
            suchprofil.regenerieren(e)
        return geaendert or (["Suchprofil-Datei"] if kopf_veraltet else [])


def _einstellungen_out(e: SuchEinstellung) -> dict:
    modelle = json.loads(e.modelle_json) if e.modelle_json else {}
    # P2-59: die WIRKSAMEN Werte zeigen, nicht die gespeicherten. Eine früher gespeicherte, inzwischen
    # gesperrte Wahl (Fable, s. agent_runner.GESPERRTE_MODELLE) stünde sonst in der Auswahl als Wert,
    # den es dort nicht mehr gibt; die Karte zeigt so genau das Modell, mit dem der Lauf startet.
    # Fehlende Funktionen füllt `wirksames_modell` mit dem Standardmodell auf (z. B. eine
    # Phase-49-Zeile ohne modelle_json-Wert).
    modelle = {fn: agent_runner.wirksames_modell(modelle.get(fn)) for fn in _MODELLE_FUNKTIONEN}
    portale = _portale_liste(e)
    from pipeline import suchprofil
    suchbereich = json.loads(e.suchbereich_json)
    return {"min_mitarbeiter": e.min_mitarbeiter,
            "suchbereich": suchbereich,
            "plaene": json.loads(e.plaene_json),
            "modelle": modelle,
            "portale": portale,
            "unterlagen": _unterlagen_standard(e),   # P2-41
            # P2-51 (V6/V7): aktuelle Umkreis-Bezeichnung bzw. verfügbare Modelle — künftig NUR
            # noch hier gepflegt, die Oberfläche hält dazu keine eigene Kopie mehr.
            "umkreis_label": suchprofil.umkreis_label(suchbereich.get("umkreis") or {}),
            # P2-86: Stufen-Namen bleiben gespeichert, die Beschriftung kommt vom gewählten Anbieter.
            "ki_anbieter": e.ki_anbieter if e.ki_anbieter in ki_anbieter.LABEL else ki_anbieter.STANDARD,
            "ki_anbieter_optionen": [{"wert": k, "label": v} for k, v in ki_anbieter.LABEL.items()],
            "modell_optionen": ki_anbieter.modell_optionen(e.ki_anbieter, agent_runner.MODELLE),
            "modell_standard": agent_runner.MODELL_STANDARD}


@app.post("/api/intern/pdf")
def intern_pdf(payload: dict):
    """Word nach PDF für Läufe in der Sandbox von Codex, in der LibreOffice nicht startet (`cv_export._pdf_ueber_server`).
    Nur Word-Dateien aus Programm- und Datenordner, das PDF landet ebenfalls nur dort."""
    from app.db import DATA_DIR
    from pipeline import cv_export
    wurzeln = (_PROJECT_ROOT.resolve(), Path(DATA_DIR).resolve())
    docx, pdf = (Path(str(payload.get(k) or "")).resolve() for k in ("docx", "pdf"))
    for pfad, endung in ((docx, ".docx"), (pdf, ".pdf")):
        if pfad.suffix.lower() != endung or not any(pfad.is_relative_to(w) for w in wurzeln):
            raise HTTPException(422, tx("Pfad außerhalb des Programms oder falsche Endung: {name}", name=pfad.name))
    if not docx.is_file():
        raise HTTPException(422, tx("Datei nicht gefunden: {name}", name=docx.name))
    ok, fehler = cv_export._to_pdf_soffice(str(docx), str(pdf))
    return {"ok": ok, "fehler": fehler}


@app.get("/api/ki-status")
def get_ki_status():
    """Für die KI-Karte der Einstellungen: installiert und angemeldet je Anbieter. Getrennt von `/api/einstellungen`,
    weil dafür ein Programm gestartet wird. Liest nie einen Schlüssel aus."""
    return ki_anbieter.status(agent_runner.CLAUDE_BIN, agent_runner.SECRETS_DIR)


@app.get("/api/einstellungen")
def get_einstellungen(session: Session = Depends(get_session)):
    """Legt die Singleton-Row beim ALLERERSTEN Aufruf lazy an und seedet sie aus den heutigen
    `suchprofile.yaml`-Werten (Design-Entscheidung 5) — schreibt dabei NIE die YAML (nur PATCH
    tut das)."""
    return _einstellungen_out(_einstellungen_singleton(session))


_PLAN_PFLICHTFELDER = {"plan", "label", "aktiv", "prioritaet", "titel", "senioritaet", "branche"}


def _validiere_plaene(plaene) -> None:
    if not isinstance(plaene, list) or len(plaene) > 3:
        raise HTTPException(422, tx("plaene muss eine Liste mit höchstens 3 Einträgen sein"))
    gesehen = set()
    for p in plaene:
        if not isinstance(p, dict):
            raise HTTPException(422, tx("jeder Plan-Eintrag muss ein Objekt sein"))
        fehlend = _PLAN_PFLICHTFELDER - set(p)
        if fehlend:
            raise HTTPException(422, tx("Plan-Eintrag fehlt Felder: {liste}", liste=', '.join(sorted(fehlend))))
        if p["plan"] not in ("A", "B", "C"):
            raise HTTPException(422, tx("plan muss A, B oder C sein, nicht {plan}", plan=repr(p['plan'])))
        if p["plan"] in gesehen:
            raise HTTPException(422, tx("Plan {plan} mehrfach angegeben", plan=p['plan']))
        gesehen.add(p["plan"])
        if not isinstance(p["aktiv"], bool):
            raise HTTPException(422, tx("aktiv muss ein Boolean sein"))
        if not isinstance(p["prioritaet"], int):
            raise HTTPException(422, tx("prioritaet muss eine Zahl sein"))
        for feld in ("titel", "senioritaet", "branche"):
            if not isinstance(p[feld], list) or not all(isinstance(x, str) for x in p[feld]):
                raise HTTPException(422, tx("{feld} muss eine Liste von Texten sein", feld=feld))


def _validiere_suchbereich(suchbereich) -> None:
    if not isinstance(suchbereich, dict):
        raise HTTPException(422, tx("suchbereich muss ein Objekt sein"))
    for key in ("remote", "deutschlandweit"):
        if key in suchbereich:
            if not isinstance(suchbereich[key], dict) or not isinstance(suchbereich[key].get("aktiv"), bool):
                raise HTTPException(422, tx("suchbereich.{key}.aktiv muss ein Boolean sein", key=key))
    if "umkreis" in suchbereich:
        u = suchbereich["umkreis"]
        if not isinstance(u, dict):
            raise HTTPException(422, tx("suchbereich.umkreis muss ein Objekt sein"))
        if "aktiv" in u and not isinstance(u["aktiv"], bool):
            raise HTTPException(422, tx("suchbereich.umkreis.aktiv muss ein Boolean sein"))
        if "stadt" in u and not isinstance(u["stadt"], str):
            raise HTTPException(422, tx("suchbereich.umkreis.stadt muss Text sein"))
        if "umkreis_km" in u and not isinstance(u["umkreis_km"], int):
            raise HTTPException(422, tx("suchbereich.umkreis.umkreis_km muss eine Zahl sein"))


def _modell_aliase_text() -> str:
    """„opus, sonnet oder haiku“ — für die 422-Meldung unten (P2-51): baut sich aus
    `agent_runner.MODELL_ALIASE` auf, damit ein künftiges neues Modell nicht an zwei Stellen
    gepflegt werden muss. Gesperrte Modelle (P2-59, `agent_runner.GESPERRTE_MODELLE`) stehen nicht
    in MODELL_ALIASE und tauchen deshalb weder hier noch in der Auswahl auf."""
    aliase = list(agent_runner.MODELL_ALIASE)
    if len(aliase) <= 1:
        return aliase[0] if aliase else ""
    return ", ".join(aliase[:-1]) + tx(" oder ") + aliase[-1]


def _validiere_modelle(modelle) -> None:
    if not isinstance(modelle, dict):
        raise HTTPException(422, tx("modelle muss ein Objekt sein"))
    unbekannt = set(modelle) - set(_MODELLE_FUNKTIONEN)
    if unbekannt:
        raise HTTPException(422, tx("Unbekannte Funktion(en) in modelle: {liste}", liste=', '.join(sorted(unbekannt))))
    for fn, alias in modelle.items():
        # P2-59: Erlaubnisliste ist MODELL_ALIASE, nicht „alles außer GESPERRTE_MODELLE“. Ein
        # gesperrtes Modell (Fable) fällt damit wie jeder unbekannte Wert durch, und ein neues,
        # nie geprüftes Modell kommt nicht stillschweigend hinein.
        if alias not in agent_runner.MODELL_ALIASE:
            raise HTTPException(422, tx("modelle.{fn} muss {wert} sein, nicht {alias}", fn=fn, wert=_modell_aliase_text(), alias=repr(alias)))


def _validiere_unterlagen(unterlagen) -> None:
    """P2-41 — Muster `_validiere_modelle`: Objekt, Schlüssel ⊆ `_UNTERLAGEN_BAUSTEINE`, Werte
    echte Booleans."""
    if not isinstance(unterlagen, dict):
        raise HTTPException(422, tx("unterlagen muss ein Objekt sein"))
    unbekannt = set(unterlagen) - set(_UNTERLAGEN_BAUSTEINE)
    if unbekannt:
        raise HTTPException(422, tx("Unbekannter Baustein in unterlagen: {liste}", liste=', '.join(sorted(unbekannt))))
    for name, wert in unterlagen.items():
        if not isinstance(wert, bool):
            raise HTTPException(422, tx("unterlagen.{name} muss ein Boolean sein, nicht {wert}", name=name, wert=repr(wert)))


# Phase 87 — Pflichtfelder je Portal-Eintrag; `standard` gehört bewusst NICHT dazu (s.
# _validiere_portale-Docstring: der Server berechnet es selbst aus dem `key`, damit ein Client,
# der das Feld vergisst oder falsch schickt, die Darstellungs-Logik nicht verfälschen kann).
_PORTAL_PFLICHTFELDER = {"key", "name", "url", "zugriff", "aktiv"}
_PORTAL_FREI_KEYS = {"frei1", "frei2"}


def _validiere_portale(portale) -> None:
    """Nach dem Muster von `_validiere_plaene`: Liste, höchstens 8 Einträge (6 Standard +
    `frei1`/`frei2`), `key` eindeutig und aus der bekannten Menge (`suchprofil.PORTALE_DEFAULT`
    — EINE Quelle der Wahrheit für die bekannten Schlüssel, kein zweiter, drift-anfälliger
    Satz hier in main.py). URL-Regel (Bau-Spec Stufe B2): leer ist nur bei `frei1`/`frei2`
    erlaubt, und dann muss `aktiv` false sein — sonst müsste die Suche eine leere URL abrufen.
    Eine nicht-leere URL muss mit http:// oder https:// beginnen (schützt vor z. B. `ftp://`,
    das der Prüf-Endpunkt ohnehin ablehnen würde, s. B4)."""
    if not isinstance(portale, list) or len(portale) > 8:
        raise HTTPException(422, tx("portale muss eine Liste mit höchstens 8 Einträgen sein"))
    from pipeline import suchprofil
    bekannte_keys = {p["key"] for p in suchprofil.PORTALE_DEFAULT}
    gesehen = set()
    for p in portale:
        if not isinstance(p, dict):
            raise HTTPException(422, tx("jeder Portal-Eintrag muss ein Objekt sein"))
        fehlend = _PORTAL_PFLICHTFELDER - set(p)
        if fehlend:
            raise HTTPException(422, tx("Portal-Eintrag fehlt Felder: {liste}", liste=', '.join(sorted(fehlend))))
        key = p["key"]
        if key not in bekannte_keys:
            raise HTTPException(422, tx("Unbekannter Portal-key: {key}", key=repr(key)))
        if key in gesehen:
            raise HTTPException(422, tx("Portal-key {key} mehrfach angegeben", key=key))
        gesehen.add(key)
        if not isinstance(p["name"], str):
            raise HTTPException(422, tx("name muss Text sein"))
        if not isinstance(p["url"], str):
            raise HTTPException(422, tx("url muss Text sein"))
        if p["zugriff"] not in ("websearch", "fetch"):
            raise HTTPException(422, tx("zugriff muss websearch oder fetch sein, nicht {zugriff}", zugriff=repr(p['zugriff'])))
        if not isinstance(p["aktiv"], bool):
            raise HTTPException(422, tx("aktiv muss ein Boolean sein"))
        url = p["url"].strip()
        if not url:
            if key not in _PORTAL_FREI_KEYS:
                raise HTTPException(422, tx("url darf bei {key} nicht leer sein", key=key))
            if p["aktiv"]:
                raise HTTPException(422, tx("{key} ohne url kann nicht aktiv sein", key=key))
        elif not (url.startswith("http://") or url.startswith("https://")):
            raise HTTPException(422, tx("url muss mit http:// oder https:// beginnen, nicht {url}", url=repr(p['url'])))


@app.patch("/api/einstellungen")
def update_einstellungen(payload: dict, session: Session = Depends(get_session)):
    """Steuerungs-Schnittstelle der Jobsuche-Parameter (Muster PATCH /api/budget/limits/{provider}).
    `plaene` wird PER PLAN upgesert (nach `plan`-Schlüssel gemergt, Reihenfolge A→B→C stabil
    gehalten) — ein Save, das nur EINEN Plan schickt (Muster „Speichern-Button je Karte"),
    darf die anderen beiden nicht löschen. `suchbereich` wird pro Unterschlüssel (remote/
    deutschlandweit/umkreis) flach gemergt, damit z. B. nur `umkreis.aktiv` togglen nicht
    `stadt`/`umkreis_km` verwirft. `portale` wird PER KEY upgesert (Muster `plaene`, Reihenfolge
    stabil nach `suchprofil.PORTALE_DEFAULT`) — ein Save mit nur EINEM geänderten Portal darf
    die übrigen sieben nicht löschen; `standard` wird dabei server-seitig aus dem `key`
    neu berechnet statt aus dem Payload übernommen (steuert nur die Darstellung, s.
    `_validiere_portale`-Docstring — kein Nutzer-Eingabefeld). `unterlagen` wird flach gemergt
    (Muster `modelle`, P2-41) — Standardumfang des Bewerbungspakets, KEIN Such-Parameter, also
    ohne YAML-Regenerierung. Regeneriert nach jedem erfolgreichen Save `config/suchprofile.yaml`
    (der Vertrag zur Jobsuche bleibt unverändert lesbar — nur der verwaltete Kopf ändert sich,
    s. `pipeline/suchprofil.py`).

    P2-51 (V7): Ändert der Umkreis-Bezeichner sich durch diesen Save (Stadt und/oder Radius),
    wird JEDE Stelle/Firma mit der BISHERIGEN Bezeichnung in DERSELBEN Transaktion auf die neue
    umgestellt (auch Stellen im Papierkorb — deren `tab` bliebe sonst dauerhaft an einer toten
    Bezeichnung hängen) — die Bezeichnung bleibt so die KENNUNG (Design-Entscheidung 5), ohne
    dass ein Nutzer beim Umziehen still seinen Bestand verliert."""
    e = _einstellungen_singleton(session)
    editierbar = {"min_mitarbeiter", "suchbereich", "plaene", "modelle", "portale", "unterlagen", "ki_anbieter"}
    unbekannt = set(payload) - editierbar
    if unbekannt:
        raise HTTPException(422, tx("Nicht editierbare Felder: {liste}", liste=', '.join(sorted(unbekannt))))

    if "min_mitarbeiter" in payload:
        try:
            wert = int(payload["min_mitarbeiter"])
        except (TypeError, ValueError):
            raise HTTPException(422, tx("min_mitarbeiter muss eine Zahl sein"))
        if wert < 0:
            raise HTTPException(422, tx("min_mitarbeiter darf nicht negativ sein"))
        e.min_mitarbeiter = wert

    label_vorher = label_nachher = None
    if "suchbereich" in payload:
        _validiere_suchbereich(payload["suchbereich"])
        from pipeline import suchprofil
        bestehend = json.loads(e.suchbereich_json)
        label_vorher = suchprofil.umkreis_label(bestehend.get("umkreis") or {})
        for key, wert in payload["suchbereich"].items():
            if isinstance(wert, dict) and isinstance(bestehend.get(key), dict):
                bestehend[key] = {**bestehend[key], **wert}
            else:
                bestehend[key] = wert
        umkreis_nachher = bestehend.get("umkreis") or {}
        # V6 PATCH-Prüfung: Ist der Umkreis NACH dem Zusammenführen aktiv, braucht er eine Stadt
        # und einen plausiblen Radius — sonst entstünde ein Bucket, den `baue_managed` beim
        # Regenerieren stillschweigend wieder verwirft (kein Fehler, aber ein Save, der scheinbar
        # nichts bewirkt hätte).
        if umkreis_nachher.get("aktiv"):
            if not (umkreis_nachher.get("stadt") or "").strip():
                raise HTTPException(422, tx("Für den Umkreis fehlt die Stadt."))
            km = umkreis_nachher.get("umkreis_km")
            if not isinstance(km, int) or isinstance(km, bool) or not (1 <= km <= 1000):
                raise HTTPException(422, tx("Der Umkreis-Radius muss zwischen 1 und 1000 km liegen."))
        e.suchbereich_json = json.dumps(bestehend, ensure_ascii=False)
        label_nachher = suchprofil.umkreis_label(umkreis_nachher)

    if "plaene" in payload:
        _validiere_plaene(payload["plaene"])
        bestehend_plaene = {p["plan"]: p for p in json.loads(e.plaene_json)}
        for p in payload["plaene"]:
            bestehend_plaene[p["plan"]] = p
        e.plaene_json = json.dumps([bestehend_plaene[k] for k in ("A", "B", "C") if k in bestehend_plaene],
                                    ensure_ascii=False)

    if "ki_anbieter" in payload:
        if payload["ki_anbieter"] not in ki_anbieter.LABEL:
            raise HTTPException(422, tx("ki_anbieter muss {liste} sein", liste=tx(" oder ").join(ki_anbieter.LABEL)))
        e.ki_anbieter = payload["ki_anbieter"]

    if "modelle" in payload:
        _validiere_modelle(payload["modelle"])
        # Flach mergen (Muster suchbereich): ein Save mit nur EINER geänderten Funktion darf die
        # übrigen fünf nicht auf "sonnet" zurücksetzen.
        bestehend_modelle = json.loads(e.modelle_json) if e.modelle_json else {}
        bestehend_modelle.update(payload["modelle"])
        e.modelle_json = json.dumps(bestehend_modelle, ensure_ascii=False)

    if "portale" in payload:
        _validiere_portale(payload["portale"])
        from pipeline import suchprofil
        # Gegen die AUFGEFÜLLTE Liste mergen, nicht gegen den rohen DB-Wert — sonst löscht der
        # erste Teil-Save einer Alt-Zeile die übrigen sieben Portale (s. `_portale_liste`).
        bestehend_portale = {p["key"]: p for p in _portale_liste(e)}
        for p in payload["portale"]:
            # `standard` server-seitig berechnen (s. Docstring oben) — nicht aus dem Payload
            # übernehmen, damit ein Client, der das Feld weglässt oder falsch setzt, die
            # Darstellungs-Unterscheidung Standard/Frei nicht verfälschen kann.
            bestehend_portale[p["key"]] = {**p, "standard": p["key"] not in _PORTAL_FREI_KEYS}
        e.portale_json = json.dumps(
            [bestehend_portale[d["key"]] for d in suchprofil.PORTALE_DEFAULT if d["key"] in bestehend_portale],
            ensure_ascii=False)

    if "unterlagen" in payload:
        _validiere_unterlagen(payload["unterlagen"])
        # Flach mergen gegen die AUFGEFÜLLTE Form (Muster modelle/portale, s.
        # `_unterlagen_standard`-Docstring) — kein YAML-Touch: `unterlagen` ist kein
        # Such-Parameter, `suchprofil.regenerieren()` unten liest das Feld nicht.
        bestehend_unterlagen = _unterlagen_standard(e)
        bestehend_unterlagen.update(payload["unterlagen"])
        e.unterlagen_json = json.dumps(bestehend_unterlagen, ensure_ascii=False)

    # P2-51 (V7): Umkreis-Umbenennung — beide Label gesetzt UND verschieden heißt, die Stadt
    # und/oder der Radius haben sich gerade geändert. `job.tab`/`company.region` VOR dem Commit
    # von `e` umstellen, damit beides in DERSELBEN Transaktion landet (kein Zwischenzustand, in
    # dem die Einstellung schon die neue Bezeichnung trägt, der Bestand aber noch die alte).
    # OHNE Papierkorb-Filter: eine gelöschte Stelle mit der alten Bezeichnung bliebe sonst
    # dauerhaft daran hängen, auch wenn sie später wiederhergestellt wird.
    umbenennung = None
    if label_vorher and label_nachher and label_vorher != label_nachher:
        jobs_betroffen = session.exec(select(Job).where(Job.tab == label_vorher)).all()
        for j in jobs_betroffen:
            j.tab = label_nachher
            session.add(j)
        firmen_betroffen = session.exec(select(Company).where(Company.region == label_vorher)).all()
        for c in firmen_betroffen:
            c.region = label_nachher
            session.add(c)
        umbenennung = {"von": label_vorher, "nach": label_nachher,
                       "jobs": len(jobs_betroffen), "firmen": len(firmen_betroffen)}

    from datetime import datetime         # lokal, wie in den übrigen PATCH-Handlern dieser Datei
    e.updated_at = datetime.utcnow()
    session.add(e)
    session.commit()
    session.refresh(e)

    from pipeline import suchprofil
    suchprofil.regenerieren(e)

    ausgabe = _einstellungen_out(e)
    if umbenennung:
        ausgabe["umbenennung"] = umbenennung
    return ausgabe


# ── Portal-Prüfung (Phase 87, Stufe B4) ─────────────────────────────────────────
# Live gemessen 21.08.2026 (Browser-User-Agent, Query "Director Professional Services", s.
# Bau-Spec Phase 87): LinkedIn (200/269 KB), Xing (200/401 KB), Nejo (200/597 KB) und
# Arbeitsagentur (200/294 KB) sind grün. Indeed antwortet mit HTTP 403 (Bot-Schutz) und
# StepStone mit HTTP 200 aber nur ~2 KB (vermutlich JS-Rendering) — eine binäre Ja/Nein-Ampel
# würde beide als "kaputt" zeigen, obwohl beide als Websuche-Kanal (statt Direktabruf, s.
# `zugriff`) weiterhin funktionieren. Deshalb die dreistufige Bewertung unten.
_PORTAL_CHECK_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
_PORTAL_CHECK_HEADERS = {"User-Agent": _PORTAL_CHECK_UA, "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"}
_PORTAL_CHECK_PLATZHALTER = {
    "$QUERY": "Director Professional Services",
    "$LOCATION": "Deutschland",
    "$PAGE": "1",
}
_PORTAL_CHECK_MAX_BYTES = 2 * 1024 * 1024   # 2 MB — Leitplanke gegen eine endlos streamende Seite
_PORTAL_CHECK_GRUEN_MIN_BYTES = 20 * 1024   # 20 KB, s. Bewertungstabelle Bau-Spec
_PORTAL_CHECK_AMBER_CODES = {401, 403, 405, 429, 999}


def _portal_url_auffuellen(url: str) -> str:
    """$QUERY/$LOCATION/$PAGE URL-kodiert ersetzen — sonst prüft man eine URL, die es in der
    echten Suche nie gibt (Platzhalter bleiben sonst wörtlich in der Anfrage stehen)."""
    from urllib.parse import quote
    ergebnis = url
    for platzhalter, wert in _PORTAL_CHECK_PLATZHALTER.items():
        ergebnis = ergebnis.replace(platzhalter, quote(wert))
    return ergebnis


def _portal_ziel_privat(host: str) -> bool:
    """SSRF-Schutz-Kern: löst `host` auf und meldet True, wenn IRGENDEINE aufgelöste Adresse
    privat/loopback/link-local/reserviert/Multicast ist. Der Prüf-Endpunkt nimmt beliebige vom
    Nutzer eingetragene URLs entgegen — das Backend darf damit NICHT als Sprungbrett ins lokale
    Netz dienen (Bau-Spec Stufe B4, Pflicht). IPv4-mapped IPv6-Adressen (`::ffff:127.0.0.1`)
    werden zusätzlich auf ihre eingebettete IPv4-Adresse geprüft, ein DNS-Fehler verweigert
    sicherheitshalber (führt ohnehin zu "rot")."""
    import ipaddress
    import socket
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    for info in infos:
        roh_ip = info[4][0].split("%")[0]   # IPv6-Zone-ID (z. B. "fe80::1%eth0") abtrennen
        try:
            addr = ipaddress.ip_address(roh_ip)
        except ValueError:
            return True
        kandidaten = [addr]
        mapped = getattr(addr, "ipv4_mapped", None)
        if mapped:
            kandidaten.append(mapped)
        for kandidat in kandidaten:
            if (kandidat.is_private or kandidat.is_loopback or kandidat.is_link_local
                    or kandidat.is_reserved or kandidat.is_multicast or kandidat.is_unspecified):
                return True
    return False


def _portal_ziel_erlaubt(url: str):
    """Gibt eine Klartext-Fehlermeldung zurück, wenn `url` NICHT geprüft werden darf, sonst
    None. Nur http/https (kein file://, ftp://, ...), Host muss auflösbar UND öffentlich sein."""
    from urllib.parse import urlsplit
    teile = urlsplit(url)
    if teile.scheme not in ("http", "https"):
        return tx("nicht erlaubtes Protokoll: {scheme}", scheme=teile.scheme or tx("(keins)"))
    if not teile.hostname:
        return tx("keine gültige URL")
    if _portal_ziel_privat(teile.hostname):
        return tx("Zieladresse ist privat/lokal — aus Sicherheitsgründen gesperrt")
    return None


class _PortalPruefungVerweigert(Exception):
    """Internes Signal: ein Redirect-Ziel ist SSRF-gesperrt — der Abruf bricht sofort ab,
    OHNE dieses Ziel anzufragen (s. `_portal_abrufen`)."""

    def __init__(self, meldung: str, url: str):
        super().__init__(meldung)
        self.meldung = meldung
        self.url = url


def _portal_abrufen(client, url: str, max_redirects: int = 5):
    """Folgt Redirects MANUELL (statt `follow_redirects=True`) — jedes Redirect-Ziel muss VOR
    dem nächsten Abruf denselben SSRF-Check durchlaufen (Bau-Spec: „auch nach Redirects“); ein
    automatischer Redirect-Follow würde diesen Check nach dem ERSTEN grünen Ziel umgehen. Liest
    den Body gestreamt und bricht bei `_PORTAL_CHECK_MAX_BYTES` ab (Leitplanke gegen eine Seite,
    die unbegrenzt Daten liefert) — der Body selbst wird NIE zurückgegeben, nur seine Länge."""
    from urllib.parse import urljoin

    aktuelle_url = url
    for _ in range(max_redirects + 1):
        fehler = _portal_ziel_erlaubt(aktuelle_url)
        if fehler:
            raise _PortalPruefungVerweigert(fehler, aktuelle_url)
        with client.stream("GET", aktuelle_url) as resp:
            if resp.is_redirect:
                aktuelle_url = urljoin(aktuelle_url, resp.headers.get("location", ""))
                continue
            groesse = 0
            for chunk in resp.iter_bytes():
                groesse += len(chunk)
                if groesse >= _PORTAL_CHECK_MAX_BYTES:
                    break
            return resp.status_code, groesse, str(resp.url)
    raise _PortalPruefungVerweigert(tx("zu viele Weiterleitungen"), aktuelle_url)


def _portal_anderer_host(start_url, final_url: str):
    """Der Host, auf dem die Antwort am Ende lag, falls er vom angefragten abweicht, sonst None.
    Verglichen wird der ganze Hostname (ohne Groß-/Kleinschreibung), nicht nur die Domain: Genau
    so entscheidet auch der Abruf der Such-Agenten, ob er einer Umleitung selbst folgt."""
    from urllib.parse import urlsplit
    if not start_url:
        return None
    start = (urlsplit(start_url).hostname or "").lower()
    ziel = (urlsplit(final_url).hostname or "").lower()
    return ziel if start and ziel and start != ziel else None


def _portal_bewerten(http_status: int, groesse: int, final_url: str, start_url: str = None) -> dict:
    """Dreistufige Bewertung, s. Modulkommentar oben + Bau-Spec-Tabelle: grün = 2xx UND
    ≥20 KB; amber = Bot-Schutz-Codes (401/403/405/429/999) ODER 2xx mit <20 KB; rot = alles
    andere (404, 5xx, unerwartete Codes). Verbindungsfehler/Timeouts/SSRF-Sperren laufen NICHT
    über diese Funktion (die kennen keinen `http_status`), sondern werden im Endpunkt direkt
    als "rot" mit Klartext-Ursache beantwortet.

    P2-73: Liegt der Inhalt erst nach einer Umleitung auf einen ANDEREN Host vor, ist das amber
    statt grün. Die Prüfung hier folgt Umleitungen, der Abruf der Such-Agenten tut das über
    Host-Grenzen nicht: Er meldet die Umleitung und braucht einen zweiten Versuch. Ein Portal ist
    so drei Wochen lang unbemerkt umgezogen gewesen, während diese Prüfung grün zeigte."""
    kb = groesse / 1024
    if http_status in _PORTAL_CHECK_AMBER_CODES:
        return {"status": "amber", "http": http_status, "bytes": groesse, "final_url": final_url,
                "meldung": (tx("erreichbar, aber Zugriff eingeschränkt (Bot-Schutz, HTTP "
                               "{http_status}) — als Websuche-Kanal weiterhin nutzbar", http_status=http_status))}
    if 200 <= http_status < 300:
        if groesse >= _PORTAL_CHECK_GRUEN_MIN_BYTES:
            anderer_host = _portal_anderer_host(start_url, final_url)
            if anderer_host:
                return {"status": "amber", "http": http_status, "bytes": groesse, "final_url": final_url,
                        "meldung": (tx("antwortet, leitet aber auf {anderer_host} um (HTTP "
                                       "{http_status}, {kb} KB) — bitte die neue Adresse "
                                       "eintragen, sonst braucht die Suche für jeden Abruf zwei "
                                       "Versuche", anderer_host=anderer_host, http_status=http_status, kb=format(kb, '.0f')))}
            return {"status": "gruen", "http": http_status, "bytes": groesse, "final_url": final_url,
                    "meldung": tx("antwortet, liefert Inhalt (HTTP {http_status}, {kb} KB)", http_status=http_status, kb=format(kb, '.0f'))}
        return {"status": "amber", "http": http_status, "bytes": groesse, "final_url": final_url,
                "meldung": (tx("antwortet, liefert aber kaum Inhalt (HTTP {http_status}, {kb} KB) "
                               "— vermutlich JS-Seite oder Weiterleitung", http_status=http_status, kb=format(kb, '.0f')))}
    if http_status == 404:
        return {"status": "rot", "http": http_status, "bytes": groesse, "final_url": final_url,
                "meldung": tx("Seite nicht gefunden (HTTP 404)")}
    if 500 <= http_status < 600:
        return {"status": "rot", "http": http_status, "bytes": groesse, "final_url": final_url,
                "meldung": tx("Server-Fehler (HTTP {http_status})", http_status=http_status)}
    return {"status": "rot", "http": http_status, "bytes": groesse, "final_url": final_url,
            "meldung": tx("unerwarteter Status (HTTP {http_status})", http_status=http_status)}


@app.post("/api/einstellungen/portale/pruefen")
def portal_pruefen(payload: dict):
    """Prüft eine Portal-URL: erreichbar? liefert sie Inhalt? Bewertet dreistufig, weil ein
    403 bei Indeed oder eine 2-KB-Antwort bei StepStone NICHT bedeutet, dass der Kanal
    unbrauchbar ist — beide laufen über die Websuche (Messung 21.08.2026, s. Spec Phase 87):
    LinkedIn (200, 269 KB), Xing (200, 401 KB), Nejo (200, 597 KB) und Arbeitsagentur
    (200, 294 KB) sind grün; Indeed liefert HTTP 403 (Bot-Schutz) und StepStone HTTP 200 mit
    nur 2 KB (vermutlich JS-Rendering) — beide amber, weil ihr tatsächlicher Suchkanal die
    Websuche ist, nicht der Direktabruf. SSRF-Schutz ist Pflicht (s. `_portal_ziel_erlaubt`):
    nur http/https, keine private/loopback/link-local/reservierte Ziel-IP, auch nicht nach
    einem Redirect. Der Antwortkörper wird NIE gespeichert/zurückgegeben, nur Länge und
    Status (Muster `agent_runner.HEADLESS_SUFFIX`-Begründung: Fremdtext bleibt draußen)."""
    url = payload.get("url")
    if not isinstance(url, str) or not url.strip():
        raise HTTPException(422, tx("url ist erforderlich"))

    ziel = _portal_url_auffuellen(url.strip())
    fehler = _portal_ziel_erlaubt(ziel)
    if fehler:
        return {"status": "rot", "http": None, "bytes": 0,
                "meldung": tx("Prüfung verweigert: {fehler}", fehler=fehler), "final_url": ziel}

    import httpx
    try:
        with httpx.Client(headers=_PORTAL_CHECK_HEADERS, timeout=20) as client:
            http_status, groesse, final_url = _portal_abrufen(client, ziel)
    except _PortalPruefungVerweigert as e:
        return {"status": "rot", "http": None, "bytes": 0,
                "meldung": tx("Prüfung verweigert: {meldung}", meldung=e.meldung), "final_url": e.url}
    except httpx.TimeoutException:
        return {"status": "rot", "http": None, "bytes": 0,
                "meldung": tx("Zeitüberschreitung (Timeout nach 20 s)"), "final_url": ziel}
    except httpx.ConnectError as e:
        return {"status": "rot", "http": None, "bytes": 0,
                "meldung": tx("Verbindung fehlgeschlagen: {e}", e=e), "final_url": ziel}
    except httpx.HTTPError as e:
        return {"status": "rot", "http": None, "bytes": 0,
                "meldung": tx("Fehler beim Abruf: {art}", art=type(e).__name__), "final_url": ziel}

    return _portal_bewerten(http_status, groesse, final_url, ziel)


# ── Anstehende Gespräche (für /followups) ──────────────────────────────────────
@app.get("/api/upcoming-interviews")
def upcoming_interviews(session: Session = Depends(get_session)):
    """Geplante Gespräche (Interview-Status 'Geplant'), nächster Termin zuerst; ohne Termin am Ende."""
    out = []
    for iv in session.exec(select(Interview).where(Interview.status == "Geplant")).all():
        job = session.get(Job, iv.job_id)
        if job and job.deleted_at:     # gelöschte Stelle — Interview-Row wurde eigentlich mit-gelöscht,
            continue                    # defensiver Filter falls doch mal stehen geblieben (Spec-Vorgabe)
        out.append({
            "id": iv.id, "job_id": iv.job_id, "runde": iv.runde, "art": iv.art,
            "scheduled_at": iv.scheduled_at, "interviewer": iv.interviewer, "prep_path": iv.prep_path,
            "company_name": job.company_name if job else None,
            "title": job.title if job else None,
            "location": job.location if job else None,
        })
    out.sort(key=lambda x: (x["scheduled_at"] is None, x["scheduled_at"] or ""))
    return out


# ── Interviews & Transkripte ───────────────────────────────────────────────────
@app.post("/api/jobs/{job_id}/interviews")
def create_interview(job_id: int, payload: dict, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(404, tx("Job nicht gefunden"))
    application = session.exec(select(Application).where(Application.job_id == job_id)).first()
    # "gegenueber"/"vor_ort" (Phase 69, Stufe B) — Gesamtprozess-KPI "Gespräche gesamt".
    fields = {"runde", "art", "scheduled_at", "interviewer", "status", "notes", "gegenueber", "vor_ort"}
    data = {k: v for k, v in payload.items() if k in fields}
    # P2-6 Schwesterstelle: dieselbe Wertemenge wie update_interview — sonst könnte NUR die
    # Anlage (POST) einen Wildwuchs-Status erzeugen, den die PATCH-Validierung direkt daneben
    # bereits verhindert (identischer Fehler an derselben Tabelle/demselben Feld, Muster Q1).
    if "status" in data:
        _validiere_status(data["status"], ALLOWED_INTERVIEW_STATUSES)
    if data.get("gegenueber"):
        _validiere_status(data["gegenueber"], ALLOWED_GEGENUEBER, "gegenueber")
    if not data.get("runde"):
        existing = session.exec(select(Interview).where(Interview.job_id == job_id)).all()
        data["runde"] = max((i.runde for i in existing), default=0) + 1
    iv = Interview(
        job_id=job_id,
        company_id=job.company_id,
        application_id=application.id if application else None,
        **data,
    )
    session.add(iv)
    session.commit()
    session.refresh(iv)
    return iv


@app.patch("/api/interviews/{interview_id}")
def update_interview(interview_id: int, payload: dict, session: Session = Depends(get_session)):
    iv = session.get(Interview, interview_id)
    if not iv:
        raise HTTPException(404, tx("Interview nicht gefunden"))
    if "status" in payload:
        _validiere_status(payload["status"], ALLOWED_INTERVIEW_STATUSES)
    if payload.get("gegenueber"):
        _validiere_status(payload["gegenueber"], ALLOWED_GEGENUEBER, "gegenueber")
    if "prep_path" in payload:
        # P2-56: nur ein Briefing oder leer, geprüft vor dem ersten setattr (s. `_briefing_pfad`).
        payload["prep_path"] = _briefing_pfad(payload["prep_path"])
    # "gegenueber"/"vor_ort" (Phase 69, Stufe B) — Pflege-UI Job-Detail-Interviewformular.
    editable = {"runde", "art", "scheduled_at", "interviewer", "status", "notes", "prep_path",
                "gegenueber", "vor_ort"}
    for k, v in payload.items():
        if k in editable:
            setattr(iv, k, v)
    from datetime import datetime
    iv.updated_at = datetime.utcnow()
    session.add(iv)
    session.commit()
    session.refresh(iv)
    return iv


@app.delete("/api/interviews/{interview_id}")
def delete_interview(interview_id: int, session: Session = Depends(get_session)):
    iv = session.get(Interview, interview_id)
    if not iv:
        raise HTTPException(404, tx("Interview nicht gefunden"))
    # Zugehörige Transkripte NICHT löschen, nur die Verknüpfung lösen.
    for t in session.exec(select(Transcript).where(Transcript.interview_id == interview_id)).all():
        t.interview_id = None
        session.add(t)
    session.delete(iv)
    session.commit()
    return {"ok": True}


# ── Transkript anlegen: Text (JSON) ODER Datei (multipart) — teilen sich einen Kern (Phase 30) ──
# Gemeinsamer Ablauf: Rohtext-Datei nach data/transcripts/ schreiben (Namenskonvention
# app/naming.py::transcript_filename — Gesprächsdatum, Teilnehmer, Firma, Position; NICHT die
# internen Job-/Runden-IDs), Transcript-Row anlegen, SOFORT den deterministischen Basis-Report
# erzeugen (pipeline.transcript_report.render_basis — kein LLM nötig, Report existiert damit ab
# der ersten Sekunde). Ein Fehler beim Report-Rendern darf das Anlegen des Transkripts nie
# verhindern — der Report lässt sich jederzeit per CLI nachrüsten.
def _speichere_transkript_und_report(session, job, content, title, source, kontakt, recorded_at,
                                     language, interview, application, summary=None) -> "Transcript":
    from app.naming import transcript_filename
    from pipeline import transcript_report

    base = transcript_filename("Transkript", recorded_at, kontakt, job.company_name, job.title,
                               runde=interview.runde if interview else None)
    tdir = _PROJECT_ROOT / "data" / "transcripts"
    tdir.mkdir(parents=True, exist_ok=True)
    fname = _freier_name(tdir, f"{base}.md")

    titel_anzeige = title or "Transkript"
    header = (
        f"# {titel_anzeige}\n\n"
        f"Job: {job.title} (#{job.id})\n"
        f"Firma: {job.company_name or '–'}\n"
        f"Teilnehmer: {kontakt or '–'}\n"
        f"Datum: {recorded_at or '–'}\n"
        f"Quelle: {source}\n\n"
    )
    (tdir / fname).write_text(header + content, encoding="utf-8")

    row = Transcript(
        job_id=job.id,
        interview_id=interview.id if interview else None,
        application_id=application.id if application else None,
        source=source,
        title=title,
        file_path=f"data/transcripts/{fname}",
        summary=summary,
        recorded_at=recorded_at,
        language=language,
        kontakt=kontakt,
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    try:
        transcript_report.render_basis(row.id)
        session.refresh(row)          # eigene Session in render_basis → report_path nachladen
    except Exception:                  # noqa: BLE001 — Transkript bleibt gültig, Report fehlt dann nur
        pass
    return row


@app.post("/api/jobs/{job_id}/transcripts")
def create_transcript(job_id: int, payload: dict, session: Session = Depends(get_session)):
    """Transkript als JSON-Text — Copy-Paste bleibt der Schnellweg (Datei-Upload s.
    POST .../transcripts/upload weiter unten). Delegiert an _speichere_transkript_und_report."""
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(404, tx("Job nicht gefunden"))
    content = (payload.get("content") or "").strip()
    if not content:
        raise HTTPException(422, tx("content (Transkript-Text) fehlt"))

    interview_id = payload.get("interview_id")
    interview = session.get(Interview, interview_id) if interview_id else None
    application = session.exec(select(Application).where(Application.job_id == job_id)).first()

    return _speichere_transkript_und_report(
        session, job, content, payload.get("title"), payload.get("source", "manuell"),
        payload.get("kontakt"), payload.get("recorded_at"), payload.get("language"),
        interview, application, summary=payload.get("summary"),
    )


_TRANSCRIPT_UPLOAD_EXT = {"txt", "md", "vtt"}
_TRANSCRIPT_MAX_UPLOAD = 5 * 1024 * 1024   # 5 MB (Spec Phase 30 Stufe C Punkt 8)
_VTT_TS_RE = re.compile(r"\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}.*")


def _strip_vtt(text: str) -> str:
    """WEBVTT-Zeitstempel-Zeilen entfernen (Teams-/Zoom-Untertitel-Export) — übrig bleibt reiner
    Sprechertext. Kopfzeile 'WEBVTT', Timecode-Zeilen ('00:00:01.000 --> 00:00:04.000 …') und reine
    Cue-Nummern raus; alles andere (Sprechertext, ggf. 'Name: Text') bleibt unverändert erhalten."""
    zeilen = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.upper() == "WEBVTT" or s.isdigit() or _VTT_TS_RE.fullmatch(s):
            continue
        zeilen.append(line)
    return "\n".join(zeilen).strip()


@app.post("/api/jobs/{job_id}/transcripts/upload")
async def upload_transcript(job_id: int,
                            file: UploadFile = File(...),
                            kontakt: str = Form(None),
                            recorded_at: str = Form(None),
                            interview_id: int = Form(None),
                            title: str = Form(None),
                            language: str = Form(None),
                            session: Session = Depends(get_session)):
    """Transkript per Datei-Upload (multipart) — NEBEN dem JSON-Endpunkt oben (der bleibt). Akzeptiert
    .txt/.md/.vtt (Teams/Zoom-Untertitel; VTT-Zeitstempel werden beim Einlesen gestrippt), max. 5 MB.
    KEIN .docx (binär, python-docx-Abhängigkeit — bewusst raus, ehrliche Grenze, s. Spec Phase 30).
    Teilt sich den Kern mit create_transcript (_speichere_transkript_und_report)."""
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(404, tx("Job nicht gefunden"))

    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext not in _TRANSCRIPT_UPLOAD_EXT:
        raise HTTPException(422, tx("Dateityp '.{ext}' nicht erlaubt für Transkripte. Erlaubt: {liste}", ext=ext or '?', liste=', '.join(sorted(_TRANSCRIPT_UPLOAD_EXT))))

    stuecke, groesse = [], 0
    while True:
        block = await file.read(1024 * 1024)
        if not block:
            break
        groesse += len(block)
        if groesse > _TRANSCRIPT_MAX_UPLOAD:
            raise HTTPException(422, tx("Datei größer als {mb} MB", mb=_TRANSCRIPT_MAX_UPLOAD // 1024 // 1024))
        stuecke.append(block)
    if not stuecke:
        raise HTTPException(422, tx("Datei ist leer"))

    text = b"".join(stuecke).decode("utf-8", errors="replace")
    if ext == "vtt":
        text = _strip_vtt(text)
    text = text.strip()
    if not text:
        raise HTTPException(422, tx("Datei enthält keinen verwertbaren Text"))

    interview = session.get(Interview, interview_id) if interview_id else None
    application = session.exec(select(Application).where(Application.job_id == job_id)).first()

    return _speichere_transkript_und_report(
        session, job, text, title or (file.filename or "Transkript"), "upload",
        kontakt, recorded_at, language, interview, application,
    )


@app.delete("/api/transcripts/{transcript_id}")
def delete_transcript(transcript_id: int, session: Session = Depends(get_session)):
    """Orphan-frei (Phase 32 Entscheidung 6): file_path + debrief_path/report_path wandern in
    den Papierkorb; eine auf dieselbe Datei zeigende JobFile-Row (Upload-Pfad kind='Transkript',
    s. upload_job_file) wird mitgelöscht — Umkehrung der dortigen Kopplung (jf.file_path ist dort
    IMMER identisch zu t.file_path, deshalb wird jf hier nie separat verschoben — unverändert
    seit vor Phase 64A)."""
    t = session.get(Transcript, transcript_id)
    if not t:
        raise HTTPException(404, tx("Transkript nicht gefunden"))

    # Pfade vorab merken — verschoben wird ERST NACH dem Commit (Phase 64A Stufe 2 / P1-7;
    # Begründung s. Kommentar in delete_job: ein späterer Move-Fehlschlag erzeugt eine verwaiste
    # Datei statt einer toten DB-Referenz).
    pfade = (t.file_path, t.debrief_path, t.report_path)

    jf = session.exec(select(JobFile).where(JobFile.transcript_id == transcript_id)).first()
    if jf:
        session.delete(jf)
    session.delete(t)
    session.commit()

    dateien_fehlgeschlagen = 0
    for p in pfade:
        try:
            _in_papierkorb(p)
        except OSError as exc:
            dateien_fehlgeschlagen += 1
            print(tt("[papierkorb] FEHLER beim Verschieben von '{pfad}' (Transcript {transcript_id}, delete_transcript): {fehler}", pfad=p, transcript_id=transcript_id, fehler=exc), flush=True)
    return {"ok": True, "dateien_fehlgeschlagen": dateien_fehlgeschlagen}


# ── Dateien am Job: Upload / Löschen (Phase 11) ────────────────────────────────
# Eine generische JobFile-Row je Datei. kind="Transkript" erzeugt zusätzlich eine
# verknüpfte Transcript-Row auf DIESELBE Datei — der Debrief-Skill und die bestehende
# Section „Interviews & Gespräche" arbeiten damit unverändert weiter.
_FILE_EXT = {"pdf", "pptx", "ppt", "docx", "doc", "txt", "md", "vtt", "srt", "rtf",
             "csv", "xlsx", "png", "jpg", "jpeg"}
_FILE_KINDS = {"Transkript", "Stellenbeschreibung", "Präsentation", "Sonstiges"}
_MAX_UPLOAD = 25 * 1024 * 1024        # 25 MB


def _freier_name(ordner: Path, fname: str) -> str:
    """Kollision → _2, _3 … (Muster aus create_transcript)."""
    if not (ordner / fname).exists():
        return fname
    stem, punkt, ext = fname.rpartition(".")
    n = 2
    while (ordner / f"{stem}_{n}{punkt}{ext}").exists():
        n += 1
    return f"{stem}_{n}{punkt}{ext}"


# ── Zentraler Papierkorb (Phase 32 A) ───────────────────────────────────────────
# Alle Löschpfade (Job-Datei-Upload, generierte Artefakte, Job-/Firma-Löschen, Transkripte)
# verschieben hierher statt hart zu löschen — „Keine Orphans" heißt: keine Datei ohne DB-Referenz
# AUSSERHALB des Papierkorbs, kein DB-Pfad, der ins Leere zeigt. Endgültiges Leeren ist Sache des
# Cleanups (Phase 33) bzw. des Nutzers — die App löscht nie endgültig. Der alte Ordner
# `data/job_files/_geloescht/` bleibt unangetastet liegen (Altbestand, kein Verweis mehr aktiv).
# _PROJECT_ROOT ist erst weiter unten im Modul definiert (Deep-Dive-Artefakte-Sektion) — bewusst
# NICHT hier auf Modulebene ausgewertet (liefe beim Import auf einen NameError), sondern lazy
# beim ersten Aufruf innerhalb der Funktion.
def _in_papierkorb(rel_path: Optional[str]) -> Optional[str]:
    """Verschiebt die Datei unter `rel_path` (projekt-root-relativ) in den zentralen Papierkorb —
    Muster `_freier_name` + `dated_filename`-Präfix (JJJJMMTT_, seit P2-63; Altbestand JJJJ_MM_TT_). Fehlende/leere Pfade werden
    still ignoriert (kein Crash) → Rückgabe None. Bei Erfolg: neuer projekt-root-relativer Pfad
    (für die `{papierkorb: …}`-Antwort der Lösch-Endpunkte).

    Scheitert `shutil.move` (z. B. Berechtigung, Plattenplatz), wirft diese Funktion `OSError`
    NACH OBEN durch — sie fängt bewusst nichts selbst (bleibt für alle Aufrufer ein einfacher
    Baustein). Endpunkte, die mehrere Dateien verarbeiten und einen Einzelfehlschlag überleben
    müssen (Phase 64A / P1-7: `delete_job`, `delete_job_file`, `delete_virtual_file`), fangen
    `OSError` selbst pro Aufruf ab, protokollieren laut und zählen weiter.

    P2-56: Verschoben wird nur eine Datei aus der Positivliste `_ARTEFAKT_ORDNER`, geprüft mit
    `_erlaubter_artefakt` (dieselbe Prüfung wie /api/artifact) am aufgelösten Pfad, BEVOR
    irgendetwas angefasst wird. Vorher galt seit P3-1 (Code-Review 2026-07-25) „irgendwo unter
    data/ oder outputs/“, in der Annahme, alle Aufrufer übergäben nur sichere Pfade aus der DB.
    Das stimmte nicht: `prep_path` ließ sich per PATCH frei setzen, und das Löschen des Briefings
    schob so data/bewerbung.sqlite oder die Sicherungen in den Papierkorb. Die gespeicherten
    Pfade der Live-DB lagen am 28.09.2026 alle in der Positivliste (2410 von 2410, nur lesend
    geprüft). Die Ordner entstehen bei jedem Aufruf frisch aus `_PROJECT_ROOT` (s. Kommentar
    oberhalb), damit Tests die Wurzel auf ein tmp-Verzeichnis umbinden können
    (test_loeschen_reihenfolge.py). Ein gesperrter Pfad wird als `OSError` geworfen (dieselbe
    Familie wie ein `shutil.move`-Fehlschlag): Die Lösch-Endpunkte mit Pfaden aus der DB fangen
    ihn über ihr eigenes `except OSError`, protokollieren laut und melden ihn als
    `dateien_fehlgeschlagen`; die Datei bleibt liegen. Die Basis-CV-Endpunkte übergeben nur
    selbst gebaute Pfade in data/cv_basis/."""
    if not rel_path:
        return None
    import shutil
    from app.naming import dated_filename

    if _erlaubter_artefakt(rel_path) is None:
        raise OSError(f"Keine Datei der Positivliste, bleibt liegen: {rel_path}")
    quelle = _PROJECT_ROOT / rel_path
    if not quelle.is_file():
        return None
    papierkorb = _PROJECT_ROOT / "data" / "papierkorb"
    papierkorb.mkdir(parents=True, exist_ok=True)
    name = quelle.name
    stem, ext = (name.rsplit(".", 1) + [""])[:2] if "." in name else (name, "")
    basis = dated_filename(stem, ext) if ext else f"{date.today():%Y%m%d}_{stem}"
    ziel_name = _freier_name(papierkorb, basis)
    shutil.move(str(quelle), str(papierkorb / ziel_name))
    return f"data/papierkorb/{ziel_name}"


@app.post("/api/jobs/{job_id}/files")
async def upload_job_file(job_id: int,
                          file: UploadFile = File(...),
                          kind: str = Form("Sonstiges"),
                          note: str = Form(None),
                          interview_id: int = Form(None),
                          kontakt: str = Form(None),
                          gespraechsart: str = Form(None),
                          recorded_at: str = Form(None),
                          language: str = Form(None),
                          session: Session = Depends(get_session)):
    import re
    from app.naming import dated_filename, transcript_filename

    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(404, tx("Job nicht gefunden"))

    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext not in _FILE_EXT:
        raise HTTPException(422, tx("Dateityp '.{ext}' nicht erlaubt. Erlaubt: {liste}", ext=ext or '?', liste=', '.join(sorted(_FILE_EXT))))

    # Stückweise lesen und bei Überschreitung abbrechen — eine 2-GB-Datei soll nicht erst
    # komplett in den RAM wandern, nur um dann abgelehnt zu werden.
    stuecke, groesse = [], 0
    while True:
        block = await file.read(1024 * 1024)
        if not block:
            break
        groesse += len(block)
        if groesse > _MAX_UPLOAD:
            raise HTTPException(413, tx("Datei größer als {mb} MB", mb=_MAX_UPLOAD // 1024 // 1024))
        stuecke.append(block)
    inhalt = b"".join(stuecke)
    if not inhalt:
        raise HTTPException(422, tx("Datei ist leer"))

    if kind not in _FILE_KINDS:
        kind = "Sonstiges"

    interview = session.get(Interview, interview_id) if interview_id else None
    ordner = _PROJECT_ROOT / "data" / "job_files" / f"job_{job_id}"
    ordner.mkdir(parents=True, exist_ok=True)

    if kind == "Transkript":
        # Namenskonvention (Vorgabe vom 11.07.2026): Gesprächsdatum, Teilnehmer, Firma, Position —
        # NICHT die internen Job-/Runden-IDs, weder auf der Platte noch in der Anzeige.
        base = transcript_filename("Transkript", recorded_at, kontakt, job.company_name, job.title,
                                   runde=interview.runde if interview else None)
        fname = _freier_name(ordner, f"{base}.{ext}")
    else:
        stem = re.sub(r"[^A-Za-z0-9_-]", "_", (file.filename or "datei").rsplit(".", 1)[0])[:60] or "datei"
        fname = _freier_name(ordner, dated_filename(stem, ext))
    (ordner / fname).write_bytes(inhalt)
    rel = f"data/job_files/job_{job_id}/{fname}"

    transcript_id = None
    if kind == "Transkript":
        application = session.exec(select(Application).where(Application.job_id == job_id)).first()
        titel = (tx("{art} mit {kontakt}", art=gespraechsart or tx("Gespräch"), kontakt=kontakt)
                 if kontakt else (file.filename or "Transkript"))
        t = Transcript(job_id=job_id,
                       interview_id=interview.id if interview else None,
                       application_id=application.id if application else None,
                       source="upload", title=titel, file_path=rel,
                       recorded_at=recorded_at, language=language,
                       kontakt=kontakt, gespraechsart=gespraechsart)
        session.add(t)
        session.flush()
        transcript_id = t.id

    # Angezeigter Name: bei Transkripten die systematische Konvention (deckt sich mit der Datei
    # auf der Platte); sonst wie gehabt der Original-Uploadname (aussagekräftiger für den Menschen).
    row = JobFile(job_id=job_id, transcript_id=transcript_id, kind=kind,
                  filename=fname if kind == "Transkript" else (file.filename or fname), file_path=rel,
                  mime=file.content_type, size_bytes=groesse, note=note)
    session.add(row)
    session.commit()
    session.refresh(row)
    return {"file": row, "transcript_id": transcript_id}


@app.delete("/api/files/{file_id}")
def delete_job_file(file_id: int, session: Session = Depends(get_session)):
    """Reversibel: die Datei wandert in den zentralen Papierkorb (Phase 32 A), sie wird nie
    gelöscht. Vormals eigener `data/job_files/_geloescht/`-Ordner — der bleibt als Altbestand
    liegen, neue Löschungen laufen über `_in_papierkorb`."""
    f = session.get(JobFile, file_id)
    if not f:
        raise HTTPException(404, tx("Datei nicht gefunden"))

    # Pfad vorab merken — verschoben wird ERST NACH dem Commit (Phase 64A / P1-7; Begründung
    # s. Kommentar in delete_job: ein späterer Move-Fehlschlag erzeugt eine verwaiste Datei
    # statt einer toten DB-Referenz).
    pfad = f.file_path

    if f.transcript_id:                       # verknüpftes Transkript zeigt auf dieselbe Datei
        t = session.get(Transcript, f.transcript_id)
        if t:
            session.delete(t)
    session.delete(f)
    session.commit()

    dateien_fehlgeschlagen = 0
    try:
        _in_papierkorb(pfad)
    except OSError as exc:
        dateien_fehlgeschlagen = 1
        print(tt("[papierkorb] FEHLER beim Verschieben von '{pfad}' (JobFile {file_id}, delete_job_file): {fehler}", pfad=pfad, file_id=file_id, fehler=exc), flush=True)
    return {"ok": True, "dateien_fehlgeschlagen": dateien_fehlgeschlagen}


# ── Generierte Artefakte einzeln löschen (Phase 32 A) ───────────────────────────
# Spiegelbildlich zu `_virtuelle_dateien` oben: gleiche (quelle, slot) → (Model, Feld). NUR diese
# Slots sind löschbar (Whitelist) — 404 bei allem anderen. Ablauf je Slot: Datei → Papierkorb,
# DB-Pfadfeld → NULL. Company-Fit (`quelle=company, slot=fit`) hängt an der FIRMA, nicht am Job —
# betrifft alle Stellen dieser Firma (Design-Entscheidung 5, UI warnt entsprechend vor dem Klick).
_VIRT_SLOTS: dict = {
    "job": {"posting": (Job, "posting_snapshot_path")},
    "company": {"fit": (Company, "fit_analysis_path")},
    "cv": {
        "docx": (CVVersion, "file_path"),
        "pdf": (CVVersion, "pdf_path"),
        "match": (CVVersion, "match_dashboard_path"),
        "ats": (CVVersion, "ats_scan_path"),
    },
    "app": {
        "cover": (Application, "cover_letter_path"),
        "coverpdf": (Application, "cover_letter_pdf_path"),
    },
    "interview": {"prep": (Interview, "prep_path")},
    "transcript": {
        "debrief": (Transcript, "debrief_path"),
        "report": (Transcript, "report_path"),   # Phase 30 — Transkript-Report
    },
}


@app.delete("/api/files/virtual/{quelle}/{pk}/{slot}")
def delete_virtual_file(quelle: str, pk: int, slot: str, session: Session = Depends(get_session)):
    mapping = _VIRT_SLOTS.get(quelle, {}).get(slot)
    if not mapping:
        raise HTTPException(404, tx("Unbekannter Slot '{quelle}/{slot}'", quelle=quelle, slot=slot))
    model, feld = mapping
    row = session.get(model, pk)
    if not row:
        raise HTTPException(404, tx("{quelle} #{pk} nicht gefunden", quelle=quelle, pk=pk))

    # Pfad vorab merken — verschoben wird ERST NACH dem Commit (Phase 64A / P1-7; Begründung
    # s. Kommentar in delete_job: ein späterer Move-Fehlschlag erzeugt eine verwaiste Datei
    # statt einer toten DB-Referenz). Das DB-Feld wird bereits jetzt genullt.
    pfad = getattr(row, feld, None)
    setattr(row, feld, None)
    session.add(row)
    session.commit()

    dateien_fehlgeschlagen = 0
    try:
        papierkorb = _in_papierkorb(pfad)   # None bei fehlendem Pfad/fehlender Datei — kein Crash
    except OSError as exc:
        papierkorb = None
        dateien_fehlgeschlagen = 1
        print(tt("[papierkorb] FEHLER beim Verschieben von '{pfad}' ({quelle}/{slot} #{pk}, delete_virtual_file): {fehler}", pfad=pfad, quelle=quelle, slot=slot, pk=pk, fehler=exc), flush=True)
    return {"ok": True, "papierkorb": papierkorb, "dateien_fehlgeschlagen": dateien_fehlgeschlagen}


# ── Review (neue Treffer aus der Jobsuche-Pipeline) ────────────────────────────
@app.get("/api/review")
def review_queue(session: Session = Depends(get_session)):
    """Neue, noch nicht gesichtete Stellen (Status 'Neu'), beste zuerst."""
    jobs = session.exec(select(Job).where(Job.status == "Neu", Job.deleted_at.is_(None))).all()
    jobs.sort(key=lambda j: (-(j.match_score or 0), (j.company_name or "").lower()))
    return [
        {
            "id": j.id, "company_name": j.company_name, "title": j.title,
            "seniority": j.seniority, "location": j.location, "work_model": j.work_model,
            "tab": j.tab, "plan_ab": j.plan_ab, "portal": j.portal, "url": j.url,
            "match_score": j.match_score, "match_rationale": j.match_rationale,
            "salary": j.salary, "found_date": j.found_date, "next_step": j.next_step,
            "verified_at": j.verified_at, "verify_note": j.verify_note,
        }
        for j in jobs
    ]


def _set_status(session, job_id, status, next_step=None):
    from datetime import datetime
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(404, tx("Job nicht gefunden"))
    alt = job.status
    job.status = status
    if next_step is not None:
        job.next_step = next_step
    job.updated_at = datetime.utcnow()
    # 27.07.2026: Dieser Pfad (Review ✓/✕) war der EINZIGE Status-Weg ohne JobLog —
    # mehrere Stellen standen dadurch kommentarlos auf „Prüfen".
    # Format wie update_job (Phase 24), Zusatz „(Review)" für die Herkunft.
    if alt != status:
        session.add(JobLog(job_id=job_id, art="auto",
                           eintrag=f"Status: {alt or '—'} → {status} (Review)"))
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


@app.post("/api/jobs/{job_id}/approve")
def approve_job(job_id: int, session: Session = Depends(get_session)):
    """Treffer annehmen → in die aktive Prüfung übernehmen."""
    return _set_status(session, job_id, "Prüfen")


@app.post("/api/jobs/{job_id}/discard")
def discard_job(job_id: int, session: Session = Depends(get_session)):
    """Treffer verwerfen → als 'Kein Match' markieren (bleibt für Dedup erhalten)."""
    return _set_status(session, job_id, "Kein Match")


# ── Companies / Contacts / Emails ──────────────────────────────────────────────
@app.get("/api/companies")
def list_companies(radar: Optional[bool] = None, session: Session = Depends(get_session)):
    comps = session.exec(select(Company)).all()
    if radar is not None:
        comps = [c for c in comps if c.is_radar == radar]
    comps.sort(key=lambda c: (c.name or "").lower())
    return comps


@app.get("/api/companies/{company_id}")
def get_company(company_id: int, session: Session = Depends(get_session)):
    comp = session.get(Company, company_id)
    if not comp:
        raise HTTPException(404, tx("Firma nicht gefunden"))
    jobs = session.exec(select(Job).where(Job.company_id == company_id)).all()
    contacts = session.exec(select(Contact).where(Contact.company_id == company_id)).all()
    return {"company": comp, "jobs": jobs, "contacts": contacts}


@app.delete("/api/companies/{company_id}")
def delete_company(company_id: int, session: Session = Depends(get_session)):
    """Löschen nur OHNE aktive (nicht gelöschte) Jobs — sonst 409 mit deren Liste im Detail-Text
    (Design-Entscheidung 3). Sonst: Company-Fit-Datei in den Papierkorb, Contacts der Firma
    gelöscht, email.company_id auf NULL, Company-Row hart gelöscht — Firmen haben keinen
    Dedup-Zwang (entstehen beim nächsten Ingest einfach neu). Hartes Löschen (kein Soft-Delete
    wie bei Job) ändert an der Reihenfolge-Begründung nichts: die Row ist nach dem Commit
    komplett weg, ein späterer Move-Fehlschlag kann also ohnehin keine tote Referenz mehr
    erzeugen — nur eine verwaiste Datei (s. Kommentar in delete_job).

    P3-6 (Code-Review 2026-07-25): Die 409-Prüfung oben zählt bewusst NUR aktive Jobs — eine
    Firma mit ausschließlich soft-gelöschten (Tombstone-)Jobs bleibt löschbar. Ohne
    Gegenmaßnahme behielten diese Tombstones danach eine `company_id`, die ins Leere zeigt (die
    Company-Row ist ja weg) — ein stiller toter Verweis, auch wenn nichts crasht (Anzeige/Dedup
    funktionieren über das denormalisierte `Job.company_name` weiter). Fix: dieselbe Technik wie
    bei `Email.company_id` direkt unten — auf NULL setzen, NICHT die 409-Prüfung auf Tombstones
    ausweiten. Begründung: `pipeline.ingest._get_or_create_company`/der Dedup-Pfad (`seen_ct` in
    `ingest_records`) lesen ausschließlich `Job.company_name` (denormalisiert) und legen bei
    Bedarf eine neue Company-Row an — sie fragen `Job.company_id` oder die `Company`-Tabelle nie
    ab. Eine Firma für immer unlöschbar zu machen, sobald sie irgendwann (und sei es nur kurz)
    einen Job hatte, widerspräche außerdem der bestehenden Prämisse „Firmen haben keinen
    Dedup-Zwang" oben."""
    comp = session.get(Company, company_id)
    if not comp:
        raise HTTPException(404, tx("Firma nicht gefunden"))

    aktive_jobs = session.exec(
        select(Job).where(Job.company_id == company_id, Job.deleted_at.is_(None))
    ).all()
    if aktive_jobs:
        liste = "; ".join(f"{j.title} (#{j.id})" for j in aktive_jobs[:15])
        raise HTTPException(409, tx("Erst {anzahl} Stelle(n) löschen: {liste}", anzahl=len(aktive_jobs), liste=liste))

    # Pfad vorab merken — verschoben wird ERST NACH dem Commit (Phase 64A Stufe 2 / P1-7).
    pfad = comp.fit_analysis_path

    for c in session.exec(select(Contact).where(Contact.company_id == company_id)).all():
        session.delete(c)
    emails = session.exec(select(Email).where(Email.company_id == company_id)).all()
    for e in emails:
        e.company_id = None
        session.add(e)

    # P3-6: An dieser Stelle können nur noch Tombstones übrig sein (aktive Jobs wurden oben
    # bereits per 409 ausgeschlossen) — deren company_id würde sonst lautlos ins Leere zeigen.
    # company_name (denormalisiert) bleibt unangetastet, Anzeige und Dedup-Pfad brauchen nur ihn.
    tombstones = session.exec(
        select(Job).where(Job.company_id == company_id, Job.deleted_at.is_not(None))
    ).all()
    for j in tombstones:
        j.company_id = None
        session.add(j)

    session.delete(comp)
    session.commit()

    dateien_fehlgeschlagen = 0
    try:
        _in_papierkorb(pfad)
    except OSError as exc:
        dateien_fehlgeschlagen = 1
        print(tt("[papierkorb] FEHLER beim Verschieben von '{pfad}' (Company {company_id}, delete_company): {fehler}", pfad=pfad, company_id=company_id, fehler=exc), flush=True)
    return {"ok": True, "dateien_fehlgeschlagen": dateien_fehlgeschlagen}


@app.get("/api/contacts")
def list_contacts(session: Session = Depends(get_session)):
    return session.exec(select(Contact)).all()


@app.get("/api/emails")
def list_emails(session: Session = Depends(get_session)):
    return session.exec(select(Email).order_by(Email.received_at)).all()


@app.get("/api/emails/{email_id}/body")
def email_body(email_id: int, session: Session = Depends(get_session)):
    """Volltext LIVE aus Gmail (Phase 27) — keine body-Spalte, Gmail bleibt Quelle der Wahrheit.
    Latenz ~1s (echter API-Call), synchron ok für On-demand-Aufklappen. Gmail-Fehler (Token
    abgelaufen, Mail gelöscht) werden NIE zu einem 500 — gmail_client._die() druckt auf stderr und
    wirft SystemExit; das fangen wir ab und liefern den Klartext als lesbaren Hinweis."""
    e = session.get(Email, email_id)
    if not e:
        raise HTTPException(404, tx("E-Mail nicht gefunden"))
    if not e.gmail_message_id:
        return {"body": None, "hinweis": tx("keine Gmail-Zuordnung")}
    import contextlib
    import io
    from pipeline import gmail_client
    stderr_puffer = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr_puffer):
            rec = gmail_client.cmd_get(e.gmail_message_id)
    except SystemExit:
        hinweis = stderr_puffer.getvalue().strip() or tx("Gmail-Fehler (unbekannt)")
        return {"body": None, "hinweis": hinweis}
    except Exception as ex:                  # noqa: BLE001 — nie 500, immer lesbarer Hinweis
        return {"body": None, "hinweis": tx("Gmail-Fehler: {ex}", ex=ex)}
    return {"body": rec.get("body"), "from": rec.get("from_addr"), "subject": rec.get("subject")}


@app.patch("/api/emails/{email_id}")
def update_email(email_id: int, payload: dict, session: Session = Depends(get_session)):
    """Bewusst minimal (Phase 27): NUR reply_draft_at/needs_reply — kein genereller Email-Edit."""
    e = session.get(Email, email_id)
    if not e:
        raise HTTPException(404, tx("E-Mail nicht gefunden"))
    editable = {"reply_draft_at", "needs_reply"}
    for k, v in payload.items():
        if k in editable:
            setattr(e, k, v)
    session.add(e)
    session.commit()
    session.refresh(e)
    return e


@app.post("/api/emails/{email_id}/assign")
def assign_email(email_id: int, payload: dict, session: Session = Depends(get_session)):
    """Ordnet eine E-Mail nachträglich einer Stelle zu, oder löst die Zuordnung (job_id: null) —
    für Mails, denen der email-check-Lauf keine Firma/Stelle zuordnen konnte (Phase 36).
    Ändert NIE den Job-Status selbst — die Antwort enthält nur einen Vorschlag (`hinweis`),
    der Nutzer entscheidet über den bestehenden PATCH /api/jobs-Weg."""
    from pipeline.gmail_ingest import RESPONSE_CATS, bewerbungs_anker, response_time_hours as _rt

    e = session.get(Email, email_id)
    if not e:
        raise HTTPException(404, tx("E-Mail nicht gefunden"))

    job_id = payload.get("job_id")
    if job_id is None:
        old_job = session.get(Job, e.job_id) if e.job_id else None
        e.job_id = None
        e.company_id = None
        e.application_id = None
        e.response_time_hours = None
        session.add(e)
        if old_job:
            betreff = e.subject or tx("(kein Betreff)")
            datum = sprach_datum(e.received_at) if e.received_at else "?"
            session.add(JobLog(job_id=old_job.id, art="auto",
                               eintrag=tx("E-Mail-Zuordnung gelöst: „{betreff}“ ({kategorie}, {datum})",
                                          betreff=betreff, kategorie=uebersetzt(e.category or "Sonstige"),
                                          datum=datum)))
        session.commit()
        session.refresh(e)
        return {"email": e, "hinweis": None}

    job = session.get(Job, job_id)
    if not job or job.deleted_at:
        raise HTTPException(404, tx("Stelle nicht gefunden"))

    e.job_id = job.id
    e.company_id = job.company_id
    app_row = session.exec(select(Application).where(Application.job_id == job.id)).first()
    e.application_id = app_row.id if app_row else None
    e.archived_at = None   # P2-52: Zuordnen holt automatisch aus dem Archiv (Invariante V6)

    # P2-17: Anker aus DERSELBEN Quelle wie der Batch-Ingest (`bewerbungs_anker`) — bis dahin
    # rechnete dieser Weg allein gegen `applied_date` und lieferte für dieselbe Mail eine andere
    # Zahl als der Lauf, sobald das Feld leer war (bei 83 von 106 Bewerbungen).
    rt = None
    is_resp = e.direction == "incoming" and e.category in RESPONSE_CATS
    if is_resp and app_row:
        rt = _rt(e.received_at, bewerbungs_anker(session).get(app_row.id))
    e.response_time_hours = rt

    session.add(e)
    betreff = e.subject or tx("(kein Betreff)")
    datum = sprach_datum(e.received_at) if e.received_at else "?"
    session.add(JobLog(job_id=job.id, art="auto",
                       eintrag=tx("E-Mail zugeordnet: „{betreff}“ ({kategorie}, {datum})",
                                  betreff=betreff, kategorie=uebersetzt(e.category or "Sonstige"),
                                  datum=datum)))
    session.commit()
    session.refresh(e)

    hinweis = None
    if e.category == "Absage":
        hinweis = tx("Kategorie Absage — Job-Status auf „Absage“ setzen? (Absagegrund lässt sich "
                     "in der Bewerbung ergänzen.)")
    elif e.category == "Angebot":
        hinweis = tx("Kategorie Angebot — Job-Status auf „Angebot“ setzen?")
    elif e.category == "Einladung":
        hinweis = tx("Kategorie Einladung — Job-Status auf „Interview“ setzen? Ggf. "
                     "Interview-Termin anlegen.")
    return {"email": e, "hinweis": hinweis}


@app.post("/api/emails/{email_id}/archive")
def archive_email(email_id: int, session: Session = Depends(get_session)):
    """Archiviert eine Mail OHNE Stelle in der App (P2-52) — Gmail bleibt unberührt.

    `archived_at` ist ein Tombstone gegen Neu-Import beim nächsten Mail-Check, kein Lösch-Vorgang
    (die Row bleibt, `gmail_ingest.seen_mid` sieht sie weiter). Nur Mails ohne Stelle dürfen
    archiviert werden — für zugeordnete Mails gäbe es sonst zwei widersprüchliche Ablagen
    (Job-Historie UND Archiv)."""
    e = session.get(Email, email_id)
    if not e:
        raise HTTPException(404, tx("E-Mail nicht gefunden"))
    if e.job_id or e.application_id:
        raise HTTPException(409, tx("Nur Mails ohne Stelle lassen sich archivieren. Lösen Sie "
                                    "zuerst die Zuordnung."))
    if not e.archived_at:
        e.archived_at = zeit.jetzt_utc().isoformat()   # naives UTC wie deleted_at, ohne utcnow()
        session.add(e)
        session.commit()
        session.refresh(e)
    return {"ok": True, "archived_at": e.archived_at}


@app.post("/api/emails/{email_id}/restore")
def restore_email(email_id: int, session: Session = Depends(get_session)):
    """Holt eine archivierte Mail zurück in die Inbox (P2-52) — Gegenstück zu archive_email."""
    e = session.get(Email, email_id)
    if not e:
        raise HTTPException(404, tx("E-Mail nicht gefunden"))
    if not e.archived_at:
        raise HTTPException(404, tx("E-Mail ist nicht archiviert"))
    e.archived_at = None
    session.add(e)
    session.commit()
    return {"ok": True}


@app.get("/api/inbox")
def inbox(session: Session = Depends(get_session), archived: bool = False):
    """E-Mails mit Firma/Job-Bezug, neueste zuerst — für die Inbox-Ansicht.

    `archived` (Standard False) trennt Inbox und Archiv (P2-52): Phase 36 hatte für diese Liste
    bewusst entschieden „kein neues Flag-Feld, kein gelesen-Status" — `archived_at` ist aber kein
    Review-/Gelesen-Status, sondern ein Tombstone gegen Neu-Import für Mails ohne Stelle, die
    der Nutzer aus der Ansicht räumen will (Gmail bleibt unberührt, s. archive_email). Bewusste
    Revision der Phase-36-Entscheidung auf Wunsch (28.09.2026)."""
    if archived:
        emails = session.exec(select(Email).where(Email.archived_at.is_not(None))).all()
    else:
        emails = session.exec(select(Email).where(Email.archived_at.is_(None))).all()
    emails.sort(key=lambda e: (e.received_at or __import__("datetime").datetime.min), reverse=True)
    out = []
    for e in emails:
        comp = session.get(Company, e.company_id) if e.company_id else None
        job = session.get(Job, e.job_id) if e.job_id else None
        out.append({
            "id": e.id, "direction": e.direction, "category": e.category,
            "from_addr": e.from_addr, "to_addr": e.to_addr, "subject": e.subject,
            "snippet": e.snippet, "received_at": zeit.iso_utc(e.received_at),
            "is_response": e.is_response, "response_time_hours": e.response_time_hours,
            "needs_reply": e.needs_reply, "reply_draft_at": e.reply_draft_at,
            "company_name": comp.name if comp else None,
            "job_id": e.job_id, "job_title": job.title if job else None,
            "job_status": job.status if job else None,
            "ohne_stelle": e.job_id is None and e.application_id is None,
            "archived_at": e.archived_at,
        })
    return out


@app.get("/api/runs")
def list_runs(session: Session = Depends(get_session)):
    return session.exec(select(Run).order_by(Run.started_at.desc())).all()


# ── Deep-Dive-Artefakte ausliefern (Positivliste P2-54; Phase 56D1: vormals cv/) ─────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# Typen, die der Browser selbst anzeigen kann → inline statt Zwangs-Download (Phase 11).
_INLINE_TYPEN = {".html": "text/html", ".htm": "text/html", ".pdf": "application/pdf",
                 ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

# P2-58: HTML-Berichte und der Tages-Digest laufen im Browser in einem eigenen, undurchsichtigen
# Ursprung (`null`) statt in dem der API. Ihr Inhalt stammt zum Teil aus KI-Läufen über
# Stellenanzeigen, Firmenseiten und Mails; ein Skript darin (Prompt-Injection, ausbrechendes
# Attribut) liefe sonst same-origin, läse die ganze API und schriebe mit passendem Origin an der
# Herkunftsprüfung vorbei. In der Sandbox scheitert Lesen an der fehlenden CORS-Freigabe (P2-55)
# und Schreiben an der Herkunftsprüfung (`Origin: null` → 403, P2-57).
# allow-scripts: 71 ältere Berichte (bis 08.08.2026) bauen ihren Inhalt per Skript auf.
# allow-popups + allow-popups-to-escape-sandbox: Quellen und Original-Anzeige öffnen in einem
# neuen Tab, und der ist eine normale Seite (ohne escape liefe etwa LinkedIn selbst in der Sandbox).
# Bewusst nicht: allow-same-origin (höbe den Schutz auf), allow-forms, allow-modals (auch
# `window.print()`; Drucken über das Browsermenü geht ohne), allow-downloads, allow-top-navigation.
# Nur für HTML: Eine PDF zeigt der Browser in seinem eigenen Betrachter, Bilder führen nichts aus.
# Die Oberfläche selbst (index.html, /assets) bleibt ohne Sandbox. Vertrag:
# tests/test_bericht_sandbox.py; Bestandsaufnahme: tasks/spec_p2-58_bericht_sandbox.md.
_BERICHT_SANDBOX = "sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox"
# `no-cache` dazu: FileResponse sendet Last-Modified, der Browser darf einen früher geöffneten
# Bericht deshalb heuristisch aus dem Cache zeigen, samt der Header von damals. In Chrome 154
# gemessen: Nach dem Einschalten der Sandbox kam ein zuvor geöffneter Bericht per Link weiter ohne
# Sandbox aus dem Festplatten-Cache. Mit no-cache fragt der Browser bei jedem Öffnen nach.
_BERICHT_KOPF = {"Content-Security-Policy": _BERICHT_SANDBOX, "Cache-Control": "no-cache"}

# P2-54: Nur diese Ordner und Dateitypen liefert /api/artifact aus. Abgeleitet aus dem, was die
# Oberfläche tatsächlich öffnet (alle Pfadspalten der DB, die drei URL-Bauer im Frontend, die
# Skills mit /api/artifact-Verweis; Bestandsaufnahme in tasks/spec_p2-54_artefakt_positivliste.md).
# Alles andere unter data/ und outputs/ bleibt gesperrt: Datenbank, Sicherungen (auch
# backups/auto), Updates, sicherung.json, Rohdaten, Papierkorb. Das zählt vor allem im LAN-Modus
# (start_lan.command), der ohne Anmeldung läuft. Ein neuer Artefakt-Ordner muss hier eingetragen
# werden, sonst liefert der Endpunkt 403.
_BERICHT = frozenset({".html"})
_WORD_PDF = frozenset({".docx", ".pdf"})
_HOCHGELADEN = frozenset(f".{e}" for e in _FILE_EXT)   # was Job- und Profil-Upload annehmen
_ARTEFAKT_ORDNER = {
    "data/company_fit": _BERICHT,               # Company-Fit, Match-Dashboard, ATS-Scan
    "data/job_postings": _BERICHT,              # Stellenausschreibungen (Snapshots)
    "data/interview_prep": _BERICHT,            # Call-Briefings (fragenbank.md bleibt intern)
    "data/beirat": _BERICHT,                    # Beirats-Checks (Debatten-JSON bleibt intern)
    "data/analysen": _BERICHT,                  # absagen-analyse, angebot-vergleich
    "data/transcripts": _BERICHT | {".md"},     # Transkript-Report und Rohtext
    "data/job_files": _HOCHGELADEN,             # Dateien am Job, auch Transkript-Uploads
    "data/profil/dateien": _HOCHGELADEN,        # Dateien im Profil
    "data/cv_basis": _WORD_PDF,                 # Basis-CVs und entwuerfe/
    "data/tmp": _WORD_PDF,                      # CV-Entwürfe aus Skill-Läufen, sonst Ablage
    "outputs/cv": _WORD_PDF,
    "outputs/cv_entwuerfe": _WORD_PDF,
    "outputs/anschreiben": _WORD_PDF,
}

# P2-56: Ein Client darf genau ein Pfadfeld setzen, `Interview.prep_path` per PATCH, und nur auf
# ein Briefing. Die Oberfläche schickt das Feld nie; der Skill interview-vorbereiten registriert
# es über pipeline.interview.register. Vorher nahm der PATCH jeden Text an, und das Löschen des
# Briefings oder der Stelle schob die Datei dahinter in den Papierkorb, auch die Live-DB.
_BRIEFING_ORDNER = {"data/interview_prep": _BERICHT}


def _erlaubter_artefakt(path: str, ordner: Optional[dict] = None) -> Optional[Path]:
    """Die Prüfung der Positivliste ohne Fehlerantwort: der aufgelöste Pfad, wenn `path`
    (projekt-relativ wie in der DB, oder absolut) in einem Ordner von `ordner` liegt und dessen
    Dateityp hat, sonst None. `ordner` ist `_ARTEFAKT_ORDNER` (Vorgabe) oder ein Teil davon.
    Jeder Aufrufer antwortet selbst: `_artefakt_datei` mit 403, `_in_papierkorb` mit OSError, der
    PATCH für Interviews mit 422 (P2-56).

    Geprüft wird der AUFGELÖSTE Pfad: `..`, Symlinks und Backslashes (Windows) landen dort, wo
    sie wirklich hinzeigen. Die Ordner entstehen bei jedem Aufruf frisch aus `_PROJECT_ROOT`
    (Muster `_in_papierkorb`), damit Tests die Wurzel auf ein tmp-Verzeichnis umbinden können.
    Die Existenz prüft erst der Aufrufer: Ein gesperrter Pfad bleibt gesperrt, ob es die Datei
    gibt oder nicht.

    P3-1 (Code-Review 2026-07-25): Der Vergleich läuft STRUKTURELL über Pfadsegmente
    (`ordner in p.parents`), nicht per String-Präfix. `str(p).startswith(str(ordner))` hätte einen
    Geschwisterordner wie `data/company_fit_alt/` als "innerhalb von data/company_fit"
    durchgelassen. Auf macOS und Linux ist der Vergleich case-sensitiv: `data/BACKUPS/…` trifft
    keinen Eintrag, obwohl das Dateisystem auf dem Mac die Datei findet (fail closed)."""
    ziel = _PROJECT_ROOT / path
    if _netzpfad(ziel):
        return None
    try:
        p = ziel.resolve()
    except (OSError, RuntimeError, ValueError):   # Nullbyte, Symlink-Schleife, Windows-Sondernamen
        return None
    for name, endungen in (_ARTEFAKT_ORDNER if ordner is None else ordner).items():
        if p.suffix.lower() in endungen and (_PROJECT_ROOT / name).resolve() in p.parents:
            return p
    return None


def _artefakt_datei(path: str) -> Path:
    """Aufgelöster Dateipfad für /api/artifact, wenn `path` in der Positivliste liegt; sonst 403
    (Prüfung s. `_erlaubter_artefakt`)."""
    p = _erlaubter_artefakt(path)
    if p is None:
        raise HTTPException(403, tx("Pfad nicht erlaubt"))
    return p


def _briefing_pfad(wert):
    """Wert für `Interview.prep_path` aus einem PATCH (P2-56). Leer (None oder "") leert das Feld;
    sonst muss er auf ein VORHANDENES Briefing zeigen (`_BRIEFING_ORDNER`), wie es
    interview-vorbereiten ablegt. Alles andere ist 422, und der PATCH ändert dann nichts.

    Gespeichert wird die kanonische Form `data/interview_prep/<datei>.html`, nicht der gesendete
    Text: `data//interview_prep/x.html` oder ein absoluter Pfad lösen zwar richtig auf, aber
    `app.db.artefakt_pfad` (Suchindex, Beirat) und der Waisen-Abgleich in `cleanup` arbeiten mit
    dem Text und hätten das echte Briefing nicht gefunden bzw. als Waise gemeldet. Die
    Existenzprüfung weist auch überlange Namen ab: `os.path.isfile` meldet dort False, ein
    gespeicherter Wert hätte später jedes `Path.is_file()` mit OSError abgebrochen (Suchindex-
    Neuaufbau, Cleanup-Scan). Außerhalb und nicht vorhanden bekommen dieselbe Antwort, der
    PATCH verrät also nicht, ob es eine Datei gibt."""
    if wert is None or wert == "":
        return None
    p = _erlaubter_artefakt(wert, _BRIEFING_ORDNER) if isinstance(wert, str) else None
    if p is not None and os.path.isfile(p):
        for ordner in _BRIEFING_ORDNER:
            basis = (_PROJECT_ROOT / ordner).resolve()
            if basis in p.parents:
                return f"{ordner}/{p.relative_to(basis).as_posix()}"
    raise HTTPException(422, tx("prep_path muss auf ein vorhandenes Briefing in "
                                "data/interview_prep/ zeigen (.html)"))


def _netzpfad(pfad: Path) -> bool:
    """Windows: UNC- und Gerätepfade (sie beginnen mit zwei Backslashes, etwa ein Freigabepfad
    auf einem anderen Rechner). Schon `resolve()` oder `stat()` spräche diesen Rechner per SMB an
    und versuchte sich dort anzumelden, bevor die Eingrenzung ablehnt. Deshalb wird so ein Pfad
    vorher abgewiesen. Unter macOS und Linux ist `drive` immer leer."""
    return pfad.drive.startswith("\\\\")


@app.get("/api/artifact")
def artifact(path: str, download: bool = False):
    """Liefert die Dokumente aus, die die Oberfläche öffnet (Positivliste `_ARTEFAKT_ORDNER`,
    P2-54; vorher alles unter data/ und outputs/, auch die Datenbank und die Sicherungen).
    `X-Content-Type-Options: nosniff` (P2-14, Code-Review 2026-07-25) verhindert, dass der
    Browser eine ausgelieferte Datei abweichend vom gesetzten Content-Type interpretiert —
    Verteidigung in der Tiefe NEBEN dem Report-HTML-Whitelist-Sanitizer
    (pipeline/transcript_report.py::_sanitiere_html), nicht dessen Ersatz. HTML zur Anzeige
    bekommt dazu `_BERICHT_KOPF` (Sandbox und no-cache, P2-58), auf allen drei Rückgabewegen
    unten."""
    from urllib.parse import unquote
    p = _artefakt_datei(unquote(path))
    # P2-96: Alte Beirats-Berichte haben eine englische Fassung im Unterordner `en`, das Original bleibt.
    if p.parent.name == "beirat" and sprache_aktuell() == "en" and os.path.isfile(p.parent / "en" / p.name):
        p = p.parent / "en" / p.name
    if not os.path.isfile(p):       # anders als Path.is_file() ohne 500 bei überlangem Namen
        raise HTTPException(404, tx("Datei nicht gefunden"))
    headers = {"X-Content-Type-Options": "nosniff"}
    typ = _INLINE_TYPEN.get(p.suffix.lower())
    if typ and not download:
        # Favicon nachsetzen (28.08.2026): Berichte, die vor dieser Umstellung entstanden sind
        # — über 800 Stück — tragen kein Icon in der Datei. Beim Ausliefern kostet das Ergänzen
        # nichts und deckt sie alle sofort ab. `mit_favicon` ist idempotent; wer das Icon schon
        # hat, wird nicht angefasst. Nur für HTML, und nur bei der Inline-Anzeige: ein Download
        # soll die Datei unverändert liefern.
        if p.suffix.lower() in (".html", ".htm"):
            headers.update(_BERICHT_KOPF)
            try:
                roh = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                return FileResponse(str(p), media_type=typ, headers=headers)
            ergaenzt = favicon.mit_favicon(roh)
            if ergaenzt != roh:
                return HTMLResponse(ergaenzt, headers=headers)
        return FileResponse(str(p), media_type=typ, headers=headers)
    return FileResponse(str(p), filename=p.name, media_type="application/octet-stream", headers=headers)


# ── Export & Digest ────────────────────────────────────────────────────────────
@app.get("/api/export/excel")
def export_excel():
    """Excel-Tracker (generierte Ansicht) aus der DB bauen und als Download liefern."""
    from pipeline.export_excel import build_workbook
    path = build_workbook()
    return FileResponse(
        str(path), filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/api/digest")
def digest():
    """Tages-Digest als HTML, in derselben Sandbox wie die Berichte (P2-58): Er zeigt fremden
    Text (Absender und Betreff von Mails, Titel aus den Portalen) und braucht weder Skript noch
    den Ursprung der API. Oben links führt ein Link zurück zum Dashboard, das den Digest öffnet."""
    from pipeline.digest import build_digest_html
    return HTMLResponse(build_digest_html(zurueck_zu="/"), headers=_BERICHT_KOPF)


@app.get("/api/absagen-analyse")
def absagen_analyse_stand():
    """P2-79: Stand der Lost-Order-Analyse für die Dashboard-Kopfzeile: der neueste Bericht mit
    Datum und Link, oder `{"datei": null}`. Das Datum kommt aus dem Dateinamen (dieselbe Quelle
    wie der Rhythmus im Tageslauf und die Coach-Site, `pipeline.absagen_bericht.neuester`).
    Der Link geht wie alle Bericht-Links der App über `/api/artifact` (Positivliste
    `data/analysen`)."""
    from urllib.parse import quote
    from pipeline import absagen_bericht
    bericht = absagen_bericht.neuester()
    if bericht is None:
        return {"datei": None}
    pfad, datum = bericht
    return {"datei": pfad.name, "datum": datum.isoformat(),
            "url": "/api/artifact?path=" + quote(f"data/analysen/{pfad.name}", safe="/")}


# ── Outreach-Tracker (gespiegelt aus Google-Drive-Datei) ───────────────────────
@app.get("/api/outreach")
def list_outreach(session: Session = Depends(get_session)):
    return session.exec(select(Outreach).order_by(Outreach.id)).all()


_OUTREACH_LABELS = {"status": "Status", "next_step": "Nächster Schritt", "next_action_datum": "Fällig am",
                    "antwort": "Antwort", "kanal": "Kanal", "typ": "Typ", "position": "Position",
                    "bewerbung_datum": "Beworben am"}  # Phase 69 — Netzwerk-Bewerbung, s. gesamtprozess.py


@app.patch("/api/outreach/{oid}")
def update_outreach(oid: int, payload: dict, session: Session = Depends(get_session)):
    """Felder ändern + Änderungen automatisch ins Aktivitäten-Log schreiben (ein Eintrag je PATCH)."""
    o = session.get(Outreach, oid)
    if not o:
        raise HTTPException(404, tx("Outreach-Eintrag nicht gefunden"))
    # "bewerbung_datum" (Phase 69) additiv aufgenommen — trägt außerdem die Wiedervorlage-
    # Funktion des Dashboards ("+7 Tage" schreibt hier next_action_datum über denselben PATCH).
    editable = {"status", "next_step", "next_action_datum", "notizen", "antwort", "kanal", "typ",
                "position", "bewerbung_datum"}
    changes = []
    for k, v in payload.items():
        if k in editable:
            old = getattr(o, k)
            if (old or "") != (v or ""):
                if k == "notizen":
                    changes.append(tx("Notizen aktualisiert"))
                elif k == "next_step":
                    changes.append(tx("Nächster Schritt: „{v}“", v=v) if v
                               else tx("Nächster Schritt entfernt"))
                else:
                    changes.append(f"{uebersetzt(_OUTREACH_LABELS[k])}: {old or '—'} → {v or '—'}")
            setattr(o, k, v)
    from datetime import datetime
    o.updated_at = datetime.utcnow()
    if changes:
        session.add(OutreachLog(outreach_id=oid, eintrag=" · ".join(changes), art="auto"))
    session.add(o)
    session.commit()
    session.refresh(o)
    return o


@app.get("/api/outreach/{oid}/log")
def outreach_log(oid: int, session: Session = Depends(get_session)):
    """Aktivitäten-Log eines Outreach-Kontakts, neueste zuerst."""
    return session.exec(select(OutreachLog).where(OutreachLog.outreach_id == oid)
                        .order_by(OutreachLog.created_at.desc(), OutreachLog.id.desc())).all()


@app.post("/api/outreach/{oid}/log")
def outreach_log_add(oid: int, payload: dict, session: Session = Depends(get_session)):
    """Manuellen Log-Eintrag anfügen (z. B. „Telefonat — meldet sich nächste Woche")."""
    o = session.get(Outreach, oid)
    if not o:
        raise HTTPException(404, tx("Outreach-Eintrag nicht gefunden"))
    eintrag = (payload.get("eintrag") or "").strip()
    if not eintrag:
        raise HTTPException(422, tx("eintrag fehlt"))
    row = OutreachLog(outreach_id=oid, eintrag=eintrag, art="manuell")
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


# ── Netzwerk-Gespräche ohne Stelle (Phase 69, Stufe B) ─────────────────────────
# Pendant zu /api/jobs/{job_id}/interviews, das zwingend eine Stelle verlangt — schließt die
# Datenlücke "Netzwerk-Calls/Headhunter-Gespräche ohne Ausschreibung zählen nirgends als
# Gespräch" (s. tasks/spec_phase69_gesamtprozess_kpis.md, Datenlücke 2). KEIN Soft-Delete
# (Spec-Entscheidung 3, s. models.py::NetzwerkGespraech) — ein geführtes Gespräch ist ein Fakt.
@app.get("/api/netzwerk-gespraeche")
def list_netzwerkgespraeche(
    outreach_id: Optional[int] = None, headhunter_id: Optional[int] = None,
    session: Session = Depends(get_session),
):
    """Gespräche ohne Stelle — optional nach Outreach- ODER Headhunter-Bezug gefiltert
    (für die Anzeige je Outreach-/Headhunter-Zeile), sonst alle. Neueste zuerst."""
    q = select(NetzwerkGespraech)
    if outreach_id is not None:
        q = q.where(NetzwerkGespraech.outreach_id == outreach_id)
    if headhunter_id is not None:
        q = q.where(NetzwerkGespraech.headhunter_id == headhunter_id)
    return session.exec(q.order_by(NetzwerkGespraech.datum.desc(), NetzwerkGespraech.id.desc())).all()


@app.post("/api/netzwerk-gespraeche")
def create_netzwerkgespraech(payload: dict, session: Session = Depends(get_session)):
    """Gespräch ohne Stelle erfassen — Button „🎙 Gespräch erfassen" an Outreach- UND
    Headhunter-Zeile (Mini-Form: Datum, Person, Gegenüber, vor Ort, Notiz)."""
    datum = (payload.get("datum") or "").strip()
    if not datum:
        raise HTTPException(422, tx("datum ist Pflicht"))
    if payload.get("gegenueber"):
        _validiere_status(payload["gegenueber"], ALLOWED_GEGENUEBER_NETZWERK, "gegenueber")
    outreach_id = payload.get("outreach_id")
    if outreach_id is not None and not session.get(Outreach, outreach_id):
        raise HTTPException(404, tx("Outreach-Eintrag nicht gefunden"))
    headhunter_id = payload.get("headhunter_id")
    if headhunter_id is not None and not session.get(Headhunter, headhunter_id):
        raise HTTPException(404, tx("Headhunter nicht gefunden"))
    ng = NetzwerkGespraech(
        datum=datum,
        person=payload.get("person") or None,
        unternehmen=payload.get("unternehmen") or None,
        gegenueber=payload.get("gegenueber") or None,
        vor_ort=bool(payload.get("vor_ort")),
        outreach_id=outreach_id,
        headhunter_id=headhunter_id,
        notiz=payload.get("notiz") or None,
    )
    session.add(ng)
    session.commit()
    session.refresh(ng)
    return ng


@app.delete("/api/netzwerk-gespraeche/{ng_id}")
def delete_netzwerkgespraech(ng_id: int, session: Session = Depends(get_session)):
    """Hartes Löschen (KEIN Soft-Delete, Spec-Entscheidung 3) — nur für echte Fehleinträge,
    über das bestehende Bestätigungs-UI-Muster (window.confirm vor dem Aufruf)."""
    ng = session.get(NetzwerkGespraech, ng_id)
    if not ng:
        raise HTTPException(404, tx("Gespräch nicht gefunden"))
    session.delete(ng)
    session.commit()
    return {"ok": True}


@app.get("/api/target-companies")
def list_target_companies(session: Session = Depends(get_session)):
    return session.exec(select(TargetCompany).where(TargetCompany.deleted_at.is_(None))
                        .order_by(TargetCompany.tier, TargetCompany.company)).all()


_TC_EDITABLE = {"company", "industry", "size_ma", "revenue", "location_hq", "ownership", "tier",
                "scenario", "key_contact", "connection_status", "website", "einschaetzung"}


@app.post("/api/target-companies")
def create_target_company(payload: dict, session: Session = Depends(get_session)):
    """Zielfirma manuell anlegen (Phase 24 B). dedup_key = derselbe Slug wie import_lists —
    additiv-sicher, ein erneuter Drive-Import überschreibt eine App-Anlage nicht (Phase 22 Design).
    Kollidiert der Slug mit einem Tombstone (Phase 28 A, gelöscht), wird dieser reaktiviert statt
    einen 409 zu werfen — „neu anlegen nach Löschen" soll einfach funktionieren."""
    from app import normalize as N
    from datetime import date, datetime

    company = (payload.get("company") or "").strip()
    if not company:
        raise HTTPException(422, tx("Firma ist Pflicht"))
    key = N.slug_parts(company)
    fields = {k: (payload.get(k) or None) for k in _TC_EDITABLE}
    fields["company"] = company
    existing = session.exec(select(TargetCompany).where(TargetCompany.dedup_key == key)).first()
    if existing:
        if existing.deleted_at is None:
            raise HTTPException(409, tx("Zielfirma existiert bereits: {company}", company=company))
        for k, v in fields.items():
            setattr(existing, k, v)
        existing.deleted_at = None
        existing.last_update = date.today().isoformat()
        existing.updated_at = datetime.utcnow()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing
    tc = TargetCompany(dedup_key=key, last_update=date.today().isoformat(), **fields)
    if not flush_or_duplicate(session, lambda: session.add(tc)):
        # P2-3 (Phase 67F): echte Race (zwei fast gleichzeitige Anfragen legen dieselbe
        # Zielfirma an) — dieselbe Antwort wie der reguläre Dublettencheck oben, nicht 500.
        raise HTTPException(409, tx("Zielfirma existiert bereits: {company}", company=company))
    session.commit()
    session.refresh(tc)
    return tc


@app.patch("/api/target-companies/{tc_id}")
def update_target_company(tc_id: int, payload: dict, session: Session = Depends(get_session)):
    """Volles Zeilen-Edit (Phase 26 B, Muster update_network_contact) + Sweep-Schreibweg
    (karriere_url/last_career_check — vom zielfirmen-sweep-Skill genutzt, im UI nur read-only
    angezeigt, s. Netzwerk.tsx)."""
    from app import normalize as N
    tc = session.get(TargetCompany, tc_id)
    if not tc:
        raise HTTPException(404, tx("Zielfirma nicht gefunden"))
    editable = _TC_EDITABLE | {"karriere_url", "last_career_check"}
    for k, v in payload.items():
        if k in editable:
            setattr(tc, k, v)
    neuer_dedup_key = None
    if "company" in payload:
        neu = N.slug_parts(tc.company)
        if neu != tc.dedup_key:
            other = session.exec(select(TargetCompany).where(TargetCompany.dedup_key == neu)).first()
            if other and other.id != tc.id:
                raise HTTPException(409, tx("Zielfirma existiert bereits: {company}", company=tc.company))
            neuer_dedup_key = neu
    from datetime import datetime
    tc.updated_at = datetime.utcnow()
    session.add(tc)

    # Die eigentliche dedup_key-Änderung bewusst ERST im Callback (nicht davor!) — s. Docstring
    # von flush_or_duplicate. Die übrigen Feld-Änderungen oben dürfen vorher pending sein (sie
    # können den UNIQUE-Index nicht verletzen).
    def _dedup_key_setzen():
        if neuer_dedup_key is not None:
            tc.dedup_key = neuer_dedup_key

    if not flush_or_duplicate(session, _dedup_key_setzen):
        # P2-3 (Phase 67F): Schwesterstelle zum Check oben — schließt die Race zwischen dem
        # `other =`-Check und dem Commit (dieselbe 409-Meldung, nicht 500).
        raise HTTPException(409, tx("Zielfirma existiert bereits: {company}", company=tc.company))
    session.commit()
    session.refresh(tc)
    return tc


@app.delete("/api/target-companies/{tc_id}")
def delete_target_company(tc_id: int, session: Session = Depends(get_session)):
    """Soft-Delete (Phase 28 A): deleted_at setzen, Row bleibt als Tombstone — kein Kaskadieren,
    Jobs/Outreach dieser Firma bleiben unberührt. Ein erneuter Drive-Import belebt sie nicht
    wieder (import_lists._upsert überspringt Rows mit deleted_at)."""
    from datetime import datetime
    tc = session.get(TargetCompany, tc_id)
    if not tc or tc.deleted_at:
        raise HTTPException(404, tx("Zielfirma nicht gefunden"))
    tc.deleted_at = datetime.utcnow().isoformat()
    tc.updated_at = datetime.utcnow()
    session.add(tc)
    session.commit()
    return {"ok": True}


@app.post("/api/target-companies/{tc_id}/restore")
def restore_target_company(tc_id: int, session: Session = Depends(get_session)):
    """Netzwerk-Papierkorb (17.07.2026): Soft-Delete rückgängig — Gegenstück zu delete_target_company."""
    from datetime import datetime
    tc = session.get(TargetCompany, tc_id)
    if not tc or not tc.deleted_at:
        raise HTTPException(404, tx("Zielfirma nicht im Papierkorb"))
    tc.deleted_at = None
    tc.updated_at = datetime.utcnow()
    session.add(tc)
    session.commit()
    return {"ok": True}


@app.get("/api/headhunters")
def list_headhunters(session: Session = Depends(get_session)):
    """Headhunter-Blatt + Outreach-Kontakte mit Typ 'Headhunter' (verknüpfte Ansicht). Nur die
    Blatt-Zeilen (echte Headhunter-Table-Rows) werden auf deleted_at gefiltert — die
    Outreach-Merge-Zeilen sind eine andere Tabelle, dort greift kein Soft-Delete (Phase 28 A)."""
    out = []
    for h in session.exec(select(Headhunter).where(Headhunter.deleted_at.is_(None))
                          .order_by(Headhunter.firma)).all():
        out.append({
            "id": f"hh{h.id}", "real_id": h.id, "source": "Blatt",
            "firma": h.firma, "ansprechpartner": h.ansprechpartner, "fokus": h.fokus,
            "region": h.region, "kanal": h.kanal, "letzter_kontakt": h.letzter_kontakt,
            "status": h.status, "notizen": h.notizen, "webseite": h.webseite,
            "karriere_url": h.karriere_url, "last_career_check": h.last_career_check,
        })
    for o in session.exec(select(Outreach).where(Outreach.typ.like("%Headhunter%"))).all():
        notiz = " · ".join(x for x in [o.next_step, o.notizen] if x)
        out.append({
            "id": f"or{o.id}", "real_id": None, "source": "Outreach",
            "firma": o.unternehmen, "ansprechpartner": o.kontakt, "fokus": o.position or o.typ,
            "region": None, "kanal": o.kanal, "letzter_kontakt": o.datum,
            "status": o.status, "notizen": notiz, "webseite": None,
            "karriere_url": None, "last_career_check": None,
        })
    return out


_HH_EDITABLE = {"ansprechpartner", "fokus", "region", "kanal", "letzter_kontakt", "status", "notizen",
                 "webseite"}


@app.post("/api/headhunters")
def create_headhunter(payload: dict, session: Session = Depends(get_session)):
    """Headhunter manuell anlegen (Phase 24 C). dedup_key = derselbe Slug wie import_lists
    (firma+ansprechpartner) — additiv-sicher. Erscheint in list_headhunters automatisch mit
    Quelle 'Blatt'; Outreach-basierte Headhunter entstehen weiter über /outreach. Kollidiert der
    Slug mit einem Tombstone (Phase 28 A), wird dieser reaktiviert statt 409."""
    from app import normalize as N
    from datetime import datetime

    firma = (payload.get("firma") or "").strip()
    if not firma:
        raise HTTPException(422, tx("Firma ist Pflicht"))
    ansprechpartner = payload.get("ansprechpartner") or None
    key = N.slug_parts(firma, ansprechpartner)
    fields = {k: (payload.get(k) or None) for k in _HH_EDITABLE}
    fields["firma"] = firma
    existing = session.exec(select(Headhunter).where(Headhunter.dedup_key == key)).first()
    if existing:
        if existing.deleted_at is None:
            raise HTTPException(409, tx("Headhunter existiert bereits: {firma}", firma=firma)
                                 + (f" ({ansprechpartner})" if ansprechpartner else ""))
        for k, v in fields.items():
            setattr(existing, k, v)
        existing.deleted_at = None
        existing.updated_at = datetime.utcnow()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing
    hh = Headhunter(dedup_key=key, **fields)
    if not flush_or_duplicate(session, lambda: session.add(hh)):
        # P2-3 (Phase 67F): echte Race (zwei fast gleichzeitige Anfragen legen denselben
        # Headhunter an) — dieselbe Antwort wie der reguläre Dublettencheck oben, nicht 500.
        raise HTTPException(409, tx("Headhunter existiert bereits: {firma}", firma=firma)
                             + (f" ({ansprechpartner})" if ansprechpartner else ""))
    session.commit()
    session.refresh(hh)
    return hh


@app.patch("/api/headhunters/{hh_id}")
def update_headhunter(hh_id: int, payload: dict, session: Session = Depends(get_session)):
    """Volles Zeilen-Edit für Blatt-Headhunter (Phase 26 A, Muster update_network_contact —
    kein Log). Nur echte Headhunter-Rows (nicht die Outreach-Merge-Zeilen, die haben keine
    eigene id in dieser Tabelle und laufen weiter über /outreach)."""
    from app import normalize as N
    hh = session.get(Headhunter, hh_id)
    if not hh:
        raise HTTPException(404, tx("Headhunter nicht gefunden"))
    editable = _HH_EDITABLE | {"firma", "karriere_url", "last_career_check"}
    for k, v in payload.items():
        if k in editable:
            setattr(hh, k, v)
    # dedup_key neu berechnen, wenn firma/ansprechpartner sich geändert haben — Kollision → 409
    neuer_dedup_key = None
    if "firma" in payload or "ansprechpartner" in payload:
        neu = N.slug_parts(hh.firma, hh.ansprechpartner)
        if neu != hh.dedup_key:
            other = session.exec(select(Headhunter).where(Headhunter.dedup_key == neu)).first()
            if other and other.id != hh.id:
                raise HTTPException(409, tx("Headhunter existiert bereits: {firma}", firma=hh.firma)
                                     + (f" ({hh.ansprechpartner})" if hh.ansprechpartner else ""))
            neuer_dedup_key = neu
    from datetime import datetime
    hh.updated_at = datetime.utcnow()
    session.add(hh)

    # Die eigentliche dedup_key-Änderung bewusst ERST im Callback — s. Docstring von
    # flush_or_duplicate (begin_nested() autoflusht sonst vorher pending Änderungen AUSSERHALB
    # der Savepoint-Absicherung).
    def _dedup_key_setzen():
        if neuer_dedup_key is not None:
            hh.dedup_key = neuer_dedup_key

    if not flush_or_duplicate(session, _dedup_key_setzen):
        # P2-3 (Phase 67F): Schwesterstelle zum Check oben — schließt die Race zwischen dem
        # `other =`-Check und dem Commit (dieselbe 409-Meldung, nicht 500).
        raise HTTPException(409, tx("Headhunter existiert bereits: {firma}", firma=hh.firma)
                             + (f" ({hh.ansprechpartner})" if hh.ansprechpartner else ""))
    session.commit()
    session.refresh(hh)
    return hh


@app.delete("/api/headhunters/{hh_id}")
def delete_headhunter(hh_id: int, session: Session = Depends(get_session)):
    """Soft-Delete (Phase 28 A). Nur echte Blatt-Zeilen — Outreach-Merge-Zeilen laufen über
    /outreach und haben keine eigene id in dieser Tabelle."""
    from datetime import datetime
    hh = session.get(Headhunter, hh_id)
    if not hh or hh.deleted_at:
        raise HTTPException(404, tx("Headhunter nicht gefunden"))
    hh.deleted_at = datetime.utcnow().isoformat()
    hh.updated_at = datetime.utcnow()
    session.add(hh)
    session.commit()
    return {"ok": True}


@app.post("/api/headhunters/{hh_id}/restore")
def restore_headhunter(hh_id: int, session: Session = Depends(get_session)):
    """Netzwerk-Papierkorb (17.07.2026): Soft-Delete rückgängig — Gegenstück zu delete_headhunter."""
    from datetime import datetime
    hh = session.get(Headhunter, hh_id)
    if not hh or not hh.deleted_at:
        raise HTTPException(404, tx("Headhunter nicht im Papierkorb"))
    hh.deleted_at = None
    hh.updated_at = datetime.utcnow()
    session.add(hh)
    session.commit()
    return {"ok": True}


@app.get("/api/network-contacts")
def list_network_contacts(session: Session = Depends(get_session)):
    return session.exec(select(NetworkContact).where(NetworkContact.deleted_at.is_(None))
                        .order_by(NetworkContact.name)).all()


def _plus_werktage(n, start=None):
    """`start` (Default heute) + n Werktage (Mo–Fr; Sa/So übersprungen, Feiertage bewusst
    ignoriert — Phase 22, Design 2). Rückgabe ISO YYYY-MM-DD."""
    from datetime import date as _date, timedelta
    d = start or _date.today()
    added = 0
    while added < n:
        d = d + timedelta(days=1)
        if d.weekday() < 5:                 # 0=Mo … 4=Fr, 5/6 = Sa/So
            added += 1
    return d.isoformat()


@app.post("/api/network-contacts")
def create_network_contact(payload: dict, session: Session = Depends(get_session)):
    """Kollidiert der Slug mit einem Tombstone (Phase 28 A), wird dieser reaktiviert statt 409."""
    from app import normalize as N
    from datetime import datetime
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(422, tx("Name ist Pflicht"))
    key = N.slug_parts(name, payload.get("unternehmen"))
    nad = (payload.get("next_action_date") or "").strip() or _plus_werktage(10)   # Standardfrist
    fields = dict(
        name=name, beziehung=payload.get("beziehung"), unternehmen=payload.get("unternehmen"),
        rolle=payload.get("rolle"), letzter_kontakt=payload.get("letzter_kontakt"),
        kanal=payload.get("kanal"), prioritaet=payload.get("prioritaet"),
        notizen=payload.get("notizen"), next_action=payload.get("next_action"),
        next_action_date=nad,
    )
    existing = session.exec(select(NetworkContact).where(NetworkContact.dedup_key == key)).first()
    if existing:
        if existing.deleted_at is None:
            raise HTTPException(409, tx("Kontakt existiert bereits: {name} ({wert})", name=name, wert=payload.get('unternehmen') or '—'))
        for k, v in fields.items():
            setattr(existing, k, v)
        existing.deleted_at = None
        existing.updated_at = datetime.utcnow()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing
    nc = NetworkContact(dedup_key=key, **fields)
    if not flush_or_duplicate(session, lambda: session.add(nc)):
        # P2-3 (Phase 67F): echte Race (zwei fast gleichzeitige Anfragen legen denselben
        # Kontakt an) — dieselbe Antwort wie der reguläre Dublettencheck oben, nicht 500.
        raise HTTPException(409, tx("Kontakt existiert bereits: {name} ({wert})", name=name, wert=payload.get('unternehmen') or '—'))
    session.commit()
    session.refresh(nc)
    return nc


@app.patch("/api/network-contacts/{nc_id}")
def update_network_contact(nc_id: int, payload: dict, session: Session = Depends(get_session)):
    from app import normalize as N
    nc = session.get(NetworkContact, nc_id)
    if not nc:
        raise HTTPException(404, tx("Netzwerk-Kontakt nicht gefunden"))
    editable = {"name", "beziehung", "unternehmen", "rolle", "letzter_kontakt",
                "kanal", "prioritaet", "notizen", "next_action", "next_action_date"}
    for k, v in payload.items():
        if k in editable:
            setattr(nc, k, v)
    # dedup_key neu berechnen, wenn name/unternehmen sich geändert haben — Kollision → 409 (nichts ändern)
    neuer_dedup_key = None
    if "name" in payload or "unternehmen" in payload:
        neu = N.slug_parts(nc.name, nc.unternehmen)
        if neu != nc.dedup_key:
            other = session.exec(select(NetworkContact).where(NetworkContact.dedup_key == neu)).first()
            if other and other.id != nc.id:
                raise HTTPException(409, tx("Kontakt existiert bereits: {name} ({unternehmen})", name=nc.name, unternehmen=nc.unternehmen or '—'))
            neuer_dedup_key = neu
    from datetime import datetime
    nc.updated_at = datetime.utcnow()
    session.add(nc)

    # Die eigentliche dedup_key-Änderung bewusst ERST im Callback — s. Docstring von
    # flush_or_duplicate (begin_nested() autoflusht sonst vorher pending Änderungen AUSSERHALB
    # der Savepoint-Absicherung).
    def _dedup_key_setzen():
        if neuer_dedup_key is not None:
            nc.dedup_key = neuer_dedup_key

    if not flush_or_duplicate(session, _dedup_key_setzen):
        # P2-3 (Phase 67F): Schwesterstelle zum Check oben — schließt die Race zwischen dem
        # `other =`-Check und dem Commit (dieselbe 409-Meldung, nicht 500).
        raise HTTPException(409, tx("Kontakt existiert bereits: {name} ({unternehmen})", name=nc.name, unternehmen=nc.unternehmen or '—'))
    session.commit()
    session.refresh(nc)
    return nc


@app.delete("/api/network-contacts/{nc_id}")
def delete_network_contact(nc_id: int, session: Session = Depends(get_session)):
    """Soft-Delete (Phase 28 A): deleted_at setzen, Row bleibt als Tombstone."""
    from datetime import datetime
    nc = session.get(NetworkContact, nc_id)
    if not nc or nc.deleted_at:
        raise HTTPException(404, tx("Netzwerk-Kontakt nicht gefunden"))
    nc.deleted_at = datetime.utcnow().isoformat()
    nc.updated_at = datetime.utcnow()
    session.add(nc)
    session.commit()
    return {"ok": True}


@app.post("/api/network-contacts/{nc_id}/restore")
def restore_network_contact(nc_id: int, session: Session = Depends(get_session)):
    """Netzwerk-Papierkorb (17.07.2026): Soft-Delete rückgängig — Gegenstück zu delete_network_contact."""
    from datetime import datetime
    nc = session.get(NetworkContact, nc_id)
    if not nc or not nc.deleted_at:
        raise HTTPException(404, tx("Netzwerk-Kontakt nicht im Papierkorb"))
    nc.deleted_at = None
    nc.updated_at = datetime.utcnow()
    session.add(nc)
    session.commit()
    return {"ok": True}


@app.get("/api/netzwerk/papierkorb")
def netzwerk_papierkorb(session: Session = Depends(get_session)):
    """Netzwerk-Papierkorb (17.07.2026): die Soft-Delete-Tombstones aus Phase 28 A sichtbar machen —
    gelöschte Zielfirmen/Headhunter/Netzwerk-Kontakte, neueste zuerst. Analog zum Datei-Papierkorb
    (Phase 32): nur anzeigen + wiederherstellen. Endgültiges Entfernen bleibt bewusst beim Cleanup
    (Phase 33) — die Tombstones sichern das Import-Dedup (import_lists belebt sie nie wieder)."""
    def _rows(model, label, detail):
        out = []
        for r in session.exec(select(model).where(model.deleted_at.is_not(None))).all():
            out.append({"id": r.id, "label": label(r) or "–", "detail": detail(r),
                        "deleted_at": r.deleted_at})
        out.sort(key=lambda x: x["deleted_at"] or "", reverse=True)
        return out
    return {
        "zielfirmen": _rows(TargetCompany, lambda r: r.company, lambda r: r.industry),
        "headhunter": _rows(Headhunter,
                            lambda r: (r.firma or "") + (f" ({r.ansprechpartner})" if r.ansprechpartner else ""),
                            lambda r: r.fokus),
        "kontakte": _rows(NetworkContact, lambda r: r.name,
                          lambda r: " · ".join(p for p in [r.unternehmen, r.rolle] if p) or None),
    }


# ── Initiativbewerbungen & Netzwerk-Check ──────────────────────────────────────
def _norm_name(s) -> str:
    return (s or "").strip().lower()


@app.get("/api/network-check")
def network_check(company: str, session: Session = Depends(get_session)):
    """Warme Pfade zu einer Firma: Netzwerk-Kontakte, Outreach-Historie, Headhunter,
    bestehende Kontakte und der Zielfirmen-Eintrag (fuzzy Namensabgleich in beide Richtungen)."""
    q = _norm_name(company)
    if len(q) < 3:
        raise HTTPException(422, tx("company zu kurz (min. 3 Zeichen)"))

    def hit(v) -> bool:
        n = _norm_name(v)
        return bool(n) and (q in n or n in q)

    ncs = [n for n in session.exec(select(NetworkContact).where(NetworkContact.deleted_at.is_(None))).all()
           if hit(n.unternehmen)]
    ors = [o for o in session.exec(select(Outreach)).all() if hit(o.unternehmen)]
    hhs = [h for h in session.exec(select(Headhunter).where(Headhunter.deleted_at.is_(None))).all()
           if hit(h.firma) or hit(h.fokus)]
    comps = [c for c in session.exec(select(Company)).all() if hit(c.name)]
    contacts = []
    for co in comps:
        contacts += session.exec(select(Contact).where(Contact.company_id == co.id)).all()
    tcs = [t for t in session.exec(select(TargetCompany).where(TargetCompany.deleted_at.is_(None))).all()
           if hit(t.company)]
    return {
        "company": company,
        # warm = echte Beziehung (Netzwerk/Outreach/Kontakt). Ein Key-Contact im Zielfirmen-Blatt ist nur
        # ein kuratierter Name ohne Beziehung — er steht in target_entry, zählt aber nicht als warm.
        "warm": bool(ncs or ors or contacts),
        "network_contacts": ncs,
        "outreach": ors,
        "headhunters": hhs,
        "contacts": contacts,
        "target_entry": tcs,
    }


@app.post("/api/initiativ")
def create_initiativ(payload: dict, session: Session = Depends(get_session)):
    """Initiativ-Stelle anlegen (kein öffentliches Stellenangebot) — aus Zielfirmen-/Radar-Liste
    oder frei. Wiederverwendet einen noch aktiven Initiativ-Job derselben Firma statt zu doppeln."""
    name = (payload.get("company") or "").strip()
    if not name:
        raise HTTPException(422, tx("company fehlt"))
    title = (payload.get("title") or "").strip() or tx("Head / Director Professional Services "
                                                       "(Initiativ)")
    q = name.lower()

    for j in session.exec(select(Job).where(Job.portal == "Initiativ")).all():
        if _norm_name(j.company_name) == q and j.status not in TERMINAL_STATUSES:
            return {"existing": True, "job": j}

    comp = next((c for c in session.exec(select(Company)).all() if _norm_name(c.name) == q), None)
    tc = next((t for t in session.exec(select(TargetCompany).where(TargetCompany.deleted_at.is_(None))).all()
               if _norm_name(t.company) and (_norm_name(t.company) in q or q in _norm_name(t.company))), None)
    if not comp:
        neue_comp = Company(
            name=name,
            industry=tc.industry if tc else None,
            region=tc.location_hq if tc else None,
            notes=tx("Aus Initiativ-Workflow angelegt"),
        )
        # `session.add(neue_comp)` bewusst ERST im Callback — s. Docstring von flush_or_duplicate.
        if flush_or_duplicate(session, lambda: session.add(neue_comp)):
            comp = neue_comp
        else:
            # P2-3 (Phase 67F): echte Race (zwei fast gleichzeitige Anfragen legen dieselbe
            # Firma an) — die jetzt existierende Zeile nachschlagen statt mit 500 zu crashen.
            comp = next((c for c in session.exec(select(Company)).all() if _norm_name(c.name) == q), None)

    signal = " · ".join(x for x in [(tc.scenario if tc else None), (tc.wachstumssignal if tc else None)] if x)
    dedup_key = f"initiativ|{q}|{title.lower()}"
    job = Job(
        company_id=comp.id if comp else None,
        company_name=comp.name if comp else name,
        title=title,
        portal="Initiativ",
        status="Prüfen",
        plan_ab=payload.get("plan_ab"),
        location=payload.get("location") or (tc.location_hq if tc else None),
        found_date=date.today().isoformat(),
        dedup_key=dedup_key,
        source_note=tx("Initiativbewerbung — kein öffentliches Stellenangebot")
                    + (f" · Signal: {signal}" if signal else ""),
        next_step=tx("Firma prüfen → Entscheider recherchieren → Anschreiben"),
        notes=payload.get("notes"),
    )
    if not flush_or_duplicate(session, lambda: session.add(job)):
        # P2-3: dedup_key existiert schon — entweder eine echte Race, ODER (hier plausibler,
        # da der Vorab-Check oben bewusst NUR nicht-terminale Jobs als "existing" zurückgibt,
        # s. Docstring) ein FRÜHERER Initiativ-Versuch bei derselben Firma+Titel, der inzwischen
        # terminal ist (Absage/Kein Match/...). Beide Fälle: den vorhandenen Job melden statt
        # mit 500 zu crashen — ob er reaktiviert wird, ist die Entscheidung des Nutzers, nicht diese
        # Funktion trifft sie automatisch.
        vorhanden = session.exec(select(Job).where(Job.dedup_key == dedup_key)).first()
        if vorhanden:
            return {"existing": True, "job": vorhanden}
        raise HTTPException(409, tx("Initiativ-Stelle konnte wegen einer Dublette nicht angelegt werden"))
    session.commit()
    session.refresh(job)
    return {"existing": False, "job": job}


@app.get("/api/export/outreach")
def export_outreach():
    """Aktuellen Outreach-Stand in die Original-Datei füllen (Format unverändert) und liefern."""
    from pipeline.export_outreach import build
    path = build()
    return FileResponse(
        str(path), filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ── Profil (Phase 45 Stufe A) ───────────────────────────────────────────────────
# Kandidaten-Substanz für Matching/Anschreiben — getrennt von config/profil.md (Such-Strategie).
# `config/profil_struktur.md` (Stufe D) ist die abgeleitete, skill-lesbare Sicht auf diese Tabellen.
def _profil_singleton(session: Session) -> Profile:
    p = session.get(Profile, 1)
    if not p:
        p = Profile(id=1)
        session.add(p)
        session.commit()
        session.refresh(p)
    return p


_PROFIL_STRUKTUR_PATH = _PROJECT_ROOT / "config" / "profil_struktur.md"


def _profil_struktur_schreiben(session: Session) -> None:
    """Stufe D (Phase 45, Design-Entscheidung 3): additive, skill-lesbare Ableitung aus den
    Profil-Tabellen — Muster abgeleitete Sicht wie Excel-Export/Tages-Digest (refresh_views):
    komplett NEU erzeugt bei jedem Aufruf, nicht gepatcht. Wird nach JEDEM schreibenden
    Profil-Endpunkt gerufen und beim Start, wenn die Datei fehlt (P2-83: nicht im Git).
    Rührt `config/profil.md` NICHT an (das bleibt Zuständigkeit von
    absagen-analyse & Co. — Design-Entscheidung 2, klare Grenze Such-Strategie vs.
    Kandidaten-Substanz)."""
    from datetime import datetime
    profile = session.get(Profile, 1)
    skills = session.exec(select(ProfileSkill)
                          .order_by(ProfileSkill.bereich, ProfileSkill.sort_order, ProfileSkill.id)).all()
    werdegang = session.exec(select(CareerEntry)
                             .order_by(CareerEntry.art, CareerEntry.sort_order, CareerEntry.id)).all()
    dateien = session.exec(select(ProfileFile).order_by(ProfileFile.created_at.desc())).all()

    z = ["# Profil-Struktur",
        "",
        "Automatisch aus der Profil-Seite erzeugt — NICHT von Hand editieren (wird beim "
        "nächsten Save überschrieben). Ergänzt `config/profil.md` (Such-Strategie) um die "
        "Kandidaten-Substanz für Matching/Anschreiben.",
        f"Stand: {datetime.utcnow().isoformat()}Z",
        "",
        "## Positionierung",
        (profile.positionierung if profile and profile.positionierung else "_(noch nicht erfasst)_"),
        "",
        "## Skills"]
    if not skills:
        z.append("_(noch keine erfasst)_")
    else:
        gruppen: dict = {}
        for s in skills:
            gruppen.setdefault(s.bereich, []).append(s)
        for bereich, items in gruppen.items():
            z.append(f"### {bereich}")
            for s in items:
                z.append(f"- {s.name}" + (f" ({s.note})" if s.note else ""))
            z.append("")
    z.append("## Werdegang")
    any_werdegang = False
    for art in ("Beruf", "Ausbildung", "Zertifizierung", "Projekt", "Sonstiges"):
        eintraege = [w for w in werdegang if w.art == art]
        if not eintraege:
            continue
        any_werdegang = True
        z.append(f"### {art}")
        for w in eintraege:
            zeit = " – ".join(x for x in (w.von, w.bis) if x)
            kopf = " · ".join(x for x in (w.rolle, w.firma, zeit) if x) or "–"
            z.append(f"- **{kopf}**")
            if w.beschreibung:
                z.append(f"  {w.beschreibung}")
            if w.referenzgeber or w.referenzdatum:
                z.append(f"  Referenz: {', '.join(x for x in (w.referenzgeber, w.referenzdatum) if x)}")
            if w.notiz:
                z.append(f"  Notiz: {w.notiz}")
        z.append("")
    if not any_werdegang:
        z.append("_(noch keine Einträge)_")
        z.append("")
    z.append("## Zertifikate und Zeugnisse (Dateien)")
    if not dateien:
        z.append("_(noch keine angehängt)_")
    else:
        for f in dateien:
            z.append(f"- [{f.kind}] {f.filename}" + (f" — {f.note}" if f.note else "")
                     + f" (`{f.file_path}`)")

    _PROFIL_STRUKTUR_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PROFIL_STRUKTUR_PATH.write_text("\n".join(z) + "\n", encoding="utf-8")


@app.get("/api/profil")
def get_profil(session: Session = Depends(get_session)):
    profile = _profil_singleton(session)
    skills = session.exec(select(ProfileSkill)
                          .order_by(ProfileSkill.bereich, ProfileSkill.sort_order, ProfileSkill.id)).all()
    gruppiert: dict = {}
    for s in skills:
        gruppiert.setdefault(s.bereich, []).append(s)
    werdegang = session.exec(select(CareerEntry)
                             .order_by(CareerEntry.art, CareerEntry.sort_order, CareerEntry.id)).all()
    dateien = session.exec(select(ProfileFile).order_by(ProfileFile.created_at.desc())).all()
    from pipeline.user_profile import anschrift, user_name
    # name stammt aus config/profil.md, nicht aus der Profile-Tabelle (die haelt bewusst nur
    # LinkedIn-Substanz) — Quelle der Kopfzeilen-Anzeige seit Phase 71.
    prof = profile.model_dump()
    prof["name"] = user_name()
    # P2-50 (Kundenpaket): Startpunkt der Routenplanung zu Vorstellungsgesprächen kam bisher aus
    # einer festen Adresse im Frontend — jetzt aus config/profil.md (s. pipeline/user_profile.py).
    prof["adresse"] = anschrift()
    return {"profile": prof, "skills": gruppiert, "werdegang": werdegang, "dateien": dateien}


@app.patch("/api/profil")
def update_profil(payload: dict, session: Session = Depends(get_session)):
    from datetime import datetime
    profile = _profil_singleton(session)
    editable = {"linkedin_url", "headline", "standort", "positionierung"}
    for k, v in payload.items():
        if k in editable:
            setattr(profile, k, v)
    profile.updated_at = datetime.utcnow()
    session.add(profile)
    session.commit()
    session.refresh(profile)
    _profil_struktur_schreiben(session)
    return profile


@app.post("/api/profil/skills")
def create_profil_skill(payload: dict, session: Session = Depends(get_session)):
    name = (payload.get("name") or "").strip()
    bereich = (payload.get("bereich") or "").strip()
    if not name or not bereich:
        raise HTTPException(422, tx("name und bereich sind Pflicht"))
    s = ProfileSkill(name=name, bereich=bereich, note=payload.get("note"),
                     quelle=payload.get("quelle") or "manuell")
    session.add(s)
    session.commit()
    session.refresh(s)
    _profil_struktur_schreiben(session)
    return s


@app.patch("/api/profil/skills/{skill_id}")
def update_profil_skill(skill_id: int, payload: dict, session: Session = Depends(get_session)):
    s = session.get(ProfileSkill, skill_id)
    if not s:
        raise HTTPException(404, tx("Skill nicht gefunden"))
    editable = {"name", "bereich", "note", "sort_order"}
    for k, v in payload.items():
        if k in editable:
            setattr(s, k, v)
    session.add(s)
    session.commit()
    session.refresh(s)
    _profil_struktur_schreiben(session)
    return s


@app.delete("/api/profil/skills/{skill_id}")
def delete_profil_skill(skill_id: int, session: Session = Depends(get_session)):
    s = session.get(ProfileSkill, skill_id)
    if not s:
        raise HTTPException(404, tx("Skill nicht gefunden"))
    session.delete(s)
    session.commit()
    _profil_struktur_schreiben(session)
    return {"ok": True}


@app.post("/api/profil/werdegang")
def create_career_entry(payload: dict, session: Session = Depends(get_session)):
    editable = {"art", "firma", "rolle", "ort", "von", "bis", "beschreibung",
               "referenzgeber", "referenzdatum", "notiz", "quelle", "sort_order"}
    fields = {k: v for k, v in payload.items() if k in editable}
    fields.setdefault("art", "Beruf")
    if not fields["art"]:
        fields["art"] = "Beruf"
    c = CareerEntry(**fields)
    session.add(c)
    session.commit()
    session.refresh(c)
    _profil_struktur_schreiben(session)
    return c


@app.patch("/api/profil/werdegang/{entry_id}")
def update_career_entry(entry_id: int, payload: dict, session: Session = Depends(get_session)):
    c = session.get(CareerEntry, entry_id)
    if not c:
        raise HTTPException(404, tx("Werdegang-Eintrag nicht gefunden"))
    editable = {"art", "firma", "rolle", "ort", "von", "bis", "beschreibung",
               "referenzgeber", "referenzdatum", "notiz", "sort_order"}
    for k, v in payload.items():
        if k in editable:
            setattr(c, k, v)
    session.add(c)
    session.commit()
    session.refresh(c)
    _profil_struktur_schreiben(session)
    return c


@app.delete("/api/profil/werdegang/{entry_id}")
def delete_career_entry(entry_id: int, session: Session = Depends(get_session)):
    c = session.get(CareerEntry, entry_id)
    if not c:
        raise HTTPException(404, tx("Werdegang-Eintrag nicht gefunden"))
    session.delete(c)
    session.commit()
    _profil_struktur_schreiben(session)
    return {"ok": True}


_PROFIL_FILE_KINDS = {"Zeugnis", "Zertifikat", "Sonstiges"}


@app.post("/api/profil/dateien")
async def upload_profil_file(file: UploadFile = File(...), kind: str = Form("Sonstiges"),
                             note: str = Form(None), session: Session = Depends(get_session)):
    """Muster `upload_job_file`: Ext-Whitelist + MAX-Cap aus der Job-Datei-Sektion wiederverwendet
    (dieselben erlaubten Typen passen für Zeugnisse/Zertifikate — kein zweites Regelwerk)."""
    import re as _re
    from app.naming import dated_filename

    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext not in _FILE_EXT:
        raise HTTPException(422, tx("Dateityp '.{ext}' nicht erlaubt. Erlaubt: {liste}", ext=ext or '?', liste=', '.join(sorted(_FILE_EXT))))

    stuecke, groesse = [], 0
    while True:
        block = await file.read(1024 * 1024)
        if not block:
            break
        groesse += len(block)
        if groesse > _MAX_UPLOAD:
            raise HTTPException(413, tx("Datei größer als {mb} MB", mb=_MAX_UPLOAD // 1024 // 1024))
        stuecke.append(block)
    inhalt = b"".join(stuecke)
    if not inhalt:
        raise HTTPException(422, tx("Datei ist leer"))

    if kind not in _PROFIL_FILE_KINDS:
        kind = "Sonstiges"

    ordner = _PROJECT_ROOT / "data" / "profil" / "dateien"
    ordner.mkdir(parents=True, exist_ok=True)
    stem = _re.sub(r"[^A-Za-z0-9_-]", "_", (file.filename or "datei").rsplit(".", 1)[0])[:60] or "datei"
    fname = _freier_name(ordner, dated_filename(stem, ext))
    (ordner / fname).write_bytes(inhalt)

    row = ProfileFile(kind=kind, filename=file.filename or fname,
                      file_path=f"data/profil/dateien/{fname}", mime=file.content_type,
                      size_bytes=groesse, note=note)
    session.add(row)
    session.commit()
    session.refresh(row)
    _profil_struktur_schreiben(session)
    return row


@app.delete("/api/profil/dateien/{file_id}")
def delete_profil_file(file_id: int, session: Session = Depends(get_session)):
    """Reversibel: Datei wandert in den zentralen Papierkorb (Phase 32 A), nie hart gelöscht —
    exakt dasselbe Muster wie `delete_job_file`."""
    f = session.get(ProfileFile, file_id)
    if not f:
        raise HTTPException(404, tx("Datei nicht gefunden"))

    # Pfad vorab merken — verschoben wird ERST NACH dem Commit (Phase 64A Stufe 2 / P1-7;
    # Begründung s. Kommentar in delete_job).
    pfad = f.file_path
    session.delete(f)
    session.commit()
    _profil_struktur_schreiben(session)   # liest die DB frisch — Reihenfolge zum Move ist egal

    dateien_fehlgeschlagen = 0
    try:
        _in_papierkorb(pfad)
    except OSError as exc:
        dateien_fehlgeschlagen = 1
        print(tt("[papierkorb] FEHLER beim Verschieben von '{pfad}' (ProfileFile {file_id}, delete_profil_file): {fehler}", pfad=pfad, file_id=file_id, fehler=exc), flush=True)
    return {"ok": True, "dateien_fehlgeschlagen": dateien_fehlgeschlagen}


# ── Profil — Basis-CVs hochladen (P2-27) ────────────────────────────────────────
# Keine Datenbank: die Basis-CVs (`data/cv_basis/base_<sprache>.docx`) sind reine Dateien, die
# fuenf Aufrufer namentlich anfassen (beirat_engine.py, agent_runner.py, die Skills cv-match /
# job-deepdive / anschreiben-erstellen / interview-vorbereiten) — der Dateiname ist ein Vertrag,
# der sich durch diesen Upload-Weg nicht aendern darf.
_CV_BASIS_DIR_REL = "data/cv_basis"
_CV_SPRACH_RE = re.compile(r"^[a-z]{2}$")   # ISO-639-1, zweistellig
# Diese sechs zieht das System von selbst heran, passend zur Sprache der Anzeige
# (beirat_engine._cv_text und die Skills cv-match / job-deepdive / anschreiben-erstellen /
# interview-vorbereiten; Tabelle der Sprachen: pipeline/bewerbungssprache.py). Alles andere
# kann hochgeladen werden, wird aber nur manuell genutzt — die Oberflaeche sagt das.
_CV_AUTOMATISCH = {c.lower() for c in bewerbungssprache.CODES}
_CV_LABELS = {"de": "Deutsch", "en": "Englisch", "fr": "Französisch", "es": "Spanisch",
              "it": "Italienisch", "nl": "Niederländisch", "pt": "Portugiesisch",
              "pl": "Polnisch", "da": "Dänisch", "sv": "Schwedisch"}


def _cv_struktur(quelle):
    """(Anzahl erkannter Stationen, Warnung) — dieselbe Zaehlung, die auch der
    Seitenumbruch-Schutz benutzt.

    WOFUER: `cv_export._seitenumbrueche_schuetzen` buendelt jede Station als `keep_with_next`-Kette
    und meldet 0, wenn es keine erkennt — dann bleibt der Schutz wirkungslos und der fertige CV
    reisst an beliebiger Stelle um. Diese Zahl beim Upload zu zeigen, macht aus einem stillen
    Folgefehler eine sofortige Rueckmeldung: Die beiden gepflegten Basis-CVs haben je 14 Stationen
    (Stand 08.09.2026); wer eine Fassung hochlaedt, bei der 0 steht, sieht das, bevor der erste
    tailored CV daraus entsteht.

    KEIN Ablehnungsgrund: Ein CV mit abweichender Struktur ist nicht ungueltig, nur schlechter
    geschuetzt. Der Upload gelingt, die Warnung steht daneben.

    `quelle` ist entweder ein Path (GET-Liste, von der Platte) oder `bytes` (POST-Upload, die
    Oeffnen-Probe im Speicher) — python-docx nimmt beides ueber `Document(...)`. Schlaegt das
    Oeffnen fehl, gibt diese Funktion `(None, <Warnung>)` zurueck statt zu werfen — Aufrufer
    duerfen daran nicht scheitern (die GET-Liste muss auch bei einer kaputten Datei 200 bleiben)."""
    import io as _io

    from docx import Document
    from pipeline import cv_export

    try:
        if isinstance(quelle, (bytes, bytearray)):
            doc = Document(_io.BytesIO(quelle))
        else:
            doc = Document(str(quelle))
    except Exception:
        return None, tx("Datei ist kein lesbares Word-Dokument — Stationen konnten nicht gezaehlt "
                        "werden.")

    absaetze = doc.paragraphs
    stationen = len(cv_export._stationsgrenzen(absaetze))

    # ZWEITE PRUEFUNG (P2-32, nach einem echten Schaden am 08.09.2026): Es genuegt nicht zu
    # zaehlen, DASS Stationen erkannt werden — es kommt darauf an, WIE sie gebaut sind. Der Nutzer
    # lud an diesem Tag CVs hoch, in denen die Firmenbeschreibung wieder zwischen Firmenzeile und
    # Jobtitel stand (das alte v7-Muster). Erkannt wurden trotzdem 14 Stationen, also blieb die
    # erste Pruefung stumm — und genau diese Zwischenzeile ist die Ursache dafuer, dass der
    # Workday-Parser den Titel mit der NAECHSTEN Station paart (Phase 76).
    #
    # Geprueft wird der Anteil: Steht bei weniger als der Haelfte der Firmenzeilen der Titel
    # direkt dahinter, ist die Datei im falschen Muster. Bewusst ein Anteil und keine
    # Abschnitts-Erkennung ueber „BERUFSERFAHRUNG“/„PROFESSIONAL EXPERIENCE“: Die Abschnittsnamen sind
    # sprachabhaengig, ein franzoesischer Lebenslauf faende gar keine. Die Ausbildungszeilen
    # (zwei von vierzehn) tragen nie einen Titel — bei einer sauberen v10-Datei sind es 12 von 14
    # und damit weit ueber der Schwelle, bei einer v7-Datei 0 von 14.
    tab_zeilen = [i for i, p in enumerate(absaetze) if cv_export._ist_stationsstart(p)]
    mit_titel = sum(1 for i in tab_zeilen
                    if i + 1 < len(absaetze) and cv_export._ist_stationstitel(absaetze[i + 1]))

    warnung = None
    if stationen == 0:
        warnung = (tx("Keine Stationen erkannt — der Seitenumbruch-Schutz greift bei diesem CV "
                      "nicht. Aufbau je Station: Firma<Tab>Zeitraum, dann der Jobtitel."))
    elif tab_zeilen and mit_titel * 2 < len(tab_zeilen):
        warnung = (tx("{anzahl} Stationen erkannt, aber nur bei {mit_titel} steht der Jobtitel "
                      "direkt hinter der Firmenzeile. Das ist das alte v7-Muster: Der "
                      "Workday-Parser paart den Titel dann mit der naechsten Station. "
                      "`scripts/cv_basis_umbau_v10.py` bringt die Datei in die richtige Form.", anzahl=len(tab_zeilen), mit_titel=mit_titel))
    return stationen, warnung


def _cv_basis_dto(pfad: Path) -> dict:
    """Baut das Antwort-DTO fuer EINE Basis-CV-Datei aus ihrem Platten-Stand — kein DB-Zugriff,
    `updated_at` kommt aus `st_mtime` (Muster wie die Dokumente-Liste an anderer Stelle)."""
    from datetime import datetime   # lokal, wie in den übrigen Stellen dieser Datei

    sprache = pfad.stem.split("_", 1)[1] if "_" in pfad.stem else pfad.stem
    st = pfad.stat()
    stationen, warnung = _cv_struktur(pfad)
    return {
        "sprache": sprache,
        "label": uebersetzt(_CV_LABELS.get(sprache, sprache.upper())),
        "automatisch": sprache in _CV_AUTOMATISCH,
        "filename": pfad.name,
        "path": f"{_CV_BASIS_DIR_REL}/{pfad.name}",
        "size_bytes": st.st_size,
        "updated_at": zeit.iso_utc(datetime.utcfromtimestamp(st.st_mtime)),
        "stationen": stationen,
        "warnung": warnung,
    }


@app.get("/api/profil/cv-basis")
def list_cv_basis():
    """Listet, was im Ordner liegt — reine Dateisystem-Sicht, keine Datenbank. `de`/`en` zuerst,
    danach alphabetisch. Eine einzelne unlesbare Datei darf die ganze Liste nicht zu Fall bringen —
    `_cv_struktur` faengt das ab, `stationen` wird `null`."""
    ordner = _PROJECT_ROOT / _CV_BASIS_DIR_REL
    if not ordner.is_dir():
        return []
    dateien = sorted(ordner.glob("base_??.docx"),
                     key=lambda p: (p.stem not in ("base_de", "base_en"), p.stem))
    return [_cv_basis_dto(p) for p in dateien]


@app.post("/api/profil/cv-basis")
async def upload_cv_basis(file: UploadFile = File(...), sprache: str = Form(...),
                          overwrite: str = Form("false")):
    """Reihenfolge ist verbindlich — erst pruefen, dann schreiben. Ein kaputter Upload darf den
    vorhandenen CV nicht beschaedigen:
    1. Sprachcode gegen `_CV_SPRACH_RE` — DIE Sicherheitsgrenze. Der Sprachcode landet im
       Dateinamen; ohne diese Pruefung waere `../../etc/passwd` ein gueltiger „Sprachcode" und
       der Upload ein Pfad-Traversal. Zwei Kleinbuchstaben, nichts sonst.
    2. Endung muss .docx sein — bewusst enger als `_FILE_EXT`: Die gesamte CV-Pipeline
       (`cv_export`, python-docx) liest ausschliesslich .docx. Ein hochgeladenes PDF saehe aus
       wie ein Erfolg und waere fuer jeden Skill unbrauchbar.
    3. Inhalt gestueckelt lesen mit `_MAX_UPLOAD`-Deckel (Muster woertlich aus
       `upload_profil_file`); leer → 422.
    4. Oeffnen-Probe im Speicher (`Document(io.BytesIO(...))` via `_cv_struktur`) — schlaegt sie
       fehl, wurde noch NICHTS auf die Platte geschrieben.
    5. Existiert die Zieldatei schon und `overwrite` ist nicht "true" → 409 mit dem tatsaechlichen
       Stand im Body, damit die Oberflaeche eine informierte Rueckfrage stellen kann (Kernwunsch
       des Nutzers) — das macht die Rueckfrage serverseitig erzwungen, nicht nur UI-Kosmetik.
    6. Vorhandene Datei → Papierkorb, nie hart geloescht.
    7. Atomar schreiben (`.neu` + `os.replace`): Das Projekt liegt in iCloud, ein direktes
       Ueberschreiben kann einen halb geschriebenen Stand synchronisieren (Muster wie
       `scripts/cv_basis_umbau_v10.py`). Schlaegt das Schreiben fehl, raeumt `finally` die
       `.neu`-Datei auf.
    8. Ein verwaistes PDF (`base_<sprache>.pdf`) wandert mit in den Papierkorb — es ist, wenn es
       nicht mehr zur neuen .docx passt, schlimmer als keins (die Datei, die man versehentlich
       verschickt). Kein automatisches Neu-Erzeugen: `to_pdf` braucht LibreOffice und Zeit."""
    import os

    if not _CV_SPRACH_RE.match(sprache or ""):
        raise HTTPException(422, tx("Sprachcode muss aus zwei Kleinbuchstaben bestehen (z. B. de, "
                                    "en, fr)"))

    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext != "docx":
        raise HTTPException(422, tx("Nur .docx wird als Basis-CV akzeptiert"))

    stuecke, groesse = [], 0
    while True:
        block = await file.read(1024 * 1024)
        if not block:
            break
        groesse += len(block)
        if groesse > _MAX_UPLOAD:
            raise HTTPException(413, tx("Datei größer als {mb} MB", mb=_MAX_UPLOAD // 1024 // 1024))
        stuecke.append(block)
    inhalt = b"".join(stuecke)
    if not inhalt:
        raise HTTPException(422, tx("Datei ist leer"))

    stationen, warnung = _cv_struktur(inhalt)
    if stationen is None:
        raise HTTPException(422, tx("Datei ist kein lesbares Word-Dokument"))

    ordner = _PROJECT_ROOT / _CV_BASIS_DIR_REL
    ordner.mkdir(parents=True, exist_ok=True)
    ziel = ordner / f"base_{sprache}.docx"
    ziel_rel = f"{_CV_BASIS_DIR_REL}/{ziel.name}"

    if ziel.exists() and (overwrite or "").lower() != "true":
        bestehend = _cv_basis_dto(ziel)
        raise HTTPException(409, {
            "grund": "existiert", "sprache": sprache, "filename": bestehend["filename"],
            "size_bytes": bestehend["size_bytes"], "updated_at": bestehend["updated_at"],
            "stationen": bestehend["stationen"],
        })

    # REIHENFOLGE: erst die neue Fassung vollstaendig auf die Platte, dann die alte in den
    # Papierkorb, dann tauschen. Andersherum (Papierkorb zuerst) waere der Bestand bei einem
    # Schreibfehler — voller Datentraeger ist der realistische Fall — kurzzeitig GANZ ohne
    # Basis-CV: Die alte Datei laege im Papierkorb, die neue nirgends. Wiederherstellbar waere
    # das zwar, aber jeder Skill, der dazwischen laeuft, faende keine Datei vor.
    neu = ordner / f"base_{sprache}.docx.neu"
    papierkorb_pfad = None
    try:
        neu.write_bytes(inhalt)
        if ziel.exists():
            papierkorb_pfad = _in_papierkorb(ziel_rel)
        # `os.replace` ist auf demselben Dateisystem atomar — es gibt keinen Moment, in dem eine
        # halb geschriebene Datei unter dem Namen steht, den fuenf Aufrufer lesen. Genau darauf
        # kommt es in iCloud an (Muster wie `scripts/cv_basis_umbau_v10.py`).
        os.replace(neu, ziel)
    finally:
        if neu.exists():
            neu.unlink()

    # Verwaistes PDF (§2.6): passt nach dem Upload nicht mehr zur .docx, sonst ist es die Datei,
    # die versehentlich verschickt wird.
    pdf_papierkorb = None
    pdf_pfad = ordner / f"base_{sprache}.pdf"
    if pdf_pfad.exists():
        pdf_papierkorb = _in_papierkorb(f"{_CV_BASIS_DIR_REL}/{pdf_pfad.name}")

    dto = _cv_basis_dto(ziel)
    dto["papierkorb"] = papierkorb_pfad
    dto["pdf_papierkorb"] = pdf_papierkorb
    return dto


@app.delete("/api/profil/cv-basis/{sprache}")
def delete_cv_basis(sprache: str):
    """Ohne Loeschen waere ein versehentlich hochgeladenes `base_xx.docx` dauerhaft in der Liste
    und in keiner Weise mehr zu entfernen — eine Sackgasse, die man nur ueber den Finder
    verlaesst. Auch hier gilt der Papierkorb, kein hartes Loeschen."""
    if not _CV_SPRACH_RE.match(sprache or ""):
        raise HTTPException(422, tx("Sprachcode muss aus zwei Kleinbuchstaben bestehen (z. B. de, "
                                    "en, fr)"))

    ordner = _PROJECT_ROOT / _CV_BASIS_DIR_REL
    ziel = ordner / f"base_{sprache}.docx"
    if not ziel.exists():
        raise HTTPException(404, tx("Basis-CV nicht gefunden"))

    papierkorb = _in_papierkorb(f"{_CV_BASIS_DIR_REL}/{ziel.name}")
    return {"ok": True, "papierkorb": papierkorb}


# ── Profil (Phase 45 Stufe C) — LinkedIn-Einlesen ───────────────────────────────
@app.post("/api/profil/import-zip")
async def profil_import_zip(file: UploadFile = File(...), session: Session = Depends(get_session)):
    """Robuster Weg (Design-Entscheidung 4a): LinkedIn-Datenexport-ZIP → additiv in die
    Profil-Tabellen, deterministisch, kein LLM (s. `pipeline/linkedin_import.py`).
    Stufe B (Phase 47): löst danach automatisch die Themenbereich-Sortierung der neu
    importierten Skills als headless Task aus."""
    from pipeline import linkedin_import

    inhalt = await file.read()
    if len(inhalt) > _MAX_UPLOAD:
        raise HTTPException(413, tx("Datei größer als {mb} MB", mb=_MAX_UPLOAD // 1024 // 1024))
    try:
        ergebnis = linkedin_import.importiere_zip(inhalt, session)
    except linkedin_import.LinkedinImportError as e:
        raise HTTPException(422, str(e))
    return await _nach_linkedin_import(ergebnis, session)


async def _nach_linkedin_import(ergebnis: dict, session: Session) -> dict:
    """Nach ZIP-Import und übernommenem Textvorschlag: Struktur-Datei neu schreiben, neue Skills einsortieren."""
    _profil_struktur_schreiben(session)
    ergebnis["task_id"] = None
    if ergebnis["skills_neu"] > 0:
        try:
            task_dto = await create_task({"kind": "skills-sortieren"}, session)
            ergebnis["task_id"] = task_dto["id"]
        except HTTPException as e:
            if e.status_code != 409:
                raise
            # Tagesbudget/Doppellauf blockiert nur den Folge-Task — der Import selbst ist bereits
            # committet und bleibt ein Erfolg; Auto-Sortierung kann manuell nachgeholt werden
            # (Button „Skills neu einsortieren" in der Profil-Seite).
    return ergebnis


@app.post("/api/profil/linkedin-einlesen")
async def profil_linkedin_einlesen(text: str = Form(""), file: Optional[UploadFile] = File(None),
                                   session: Session = Depends(get_session)):
    """Profil aus eingefügtem Text oder PDF: Eingabe zwischenspeichern und den Lauf `profil-einlesen` starten.
    Gespeichert wird erst nach der Vorschau (`pipeline/linkedin_text.py`)."""
    from pipeline import linkedin_text
    try:
        if file is not None:
            inhalt = await file.read()
            if len(inhalt) > _MAX_UPLOAD:
                raise HTTPException(413, tx("Datei größer als {mb} MB", mb=_MAX_UPLOAD // 1024 // 1024))
            text = linkedin_text.pdf_zu_text(inhalt)
        linkedin_text.eingabe_speichern(text)
    except linkedin_text.EingabeFehler as e:
        raise HTTPException(422, str(e))
    task_dto = await create_task({"kind": "profil-einlesen"}, session)
    return {"task_id": task_dto["id"], "task": task_dto}


@app.get("/api/profil/linkedin-eingabe")
def profil_linkedin_eingabe():
    """Für den Lauf `profil-einlesen`: der zu strukturierende Profiltext."""
    from pipeline import linkedin_text
    text = linkedin_text.eingabe_lesen()
    if text is None:
        raise HTTPException(404, tx("Es liegt kein Profiltext vor."))
    return {"text": text}


@app.post("/api/profil/linkedin-vorschlag")
def profil_linkedin_vorschlag_speichern(payload: dict):
    """Für den Lauf `profil-einlesen`: der strukturierte Vorschlag. Noch nichts am Profil ändert sich."""
    from pipeline import linkedin_text
    try:
        vorschlag = linkedin_text.vorschlag_speichern(payload)
    except linkedin_text.EingabeFehler as e:
        raise HTTPException(422, str(e))
    return {"ok": True, "skills": len(vorschlag["skills"]), "werdegang": len(vorschlag["werdegang"])}


@app.get("/api/profil/linkedin-vorschlag")
def profil_linkedin_vorschau(session: Session = Depends(get_session)):
    from pipeline import linkedin_text
    vorschlag = linkedin_text.vorschlag_lesen()
    return linkedin_text.vorschau(vorschlag, session) if vorschlag else {"vorhanden": False}


@app.post("/api/profil/linkedin-vorschlag/uebernehmen")
async def profil_linkedin_uebernehmen(session: Session = Depends(get_session)):
    from pipeline import linkedin_text
    vorschlag = linkedin_text.vorschlag_lesen()
    if not vorschlag:
        raise HTTPException(404, tx("Es liegt kein Vorschlag vor."))
    ergebnis = linkedin_text.uebernehmen(vorschlag, session)
    return await _nach_linkedin_import(ergebnis, session)


@app.delete("/api/profil/linkedin-vorschlag")
def profil_linkedin_verwerfen():
    from pipeline import linkedin_text
    linkedin_text.verwerfen()
    return {"ok": True}


# ── Bewerbungs-Beirat (18.07.2026) — live orchestrierte Debatten, s. backend/beirat_engine.py ──
# Async-Endpunkte, weil die Engine im Event-Loop des Servers läuft (SSE + Hintergrund-Task).
# Personas = .claude/agents/beirat-*.md (dieselben wie der interaktive /beirat-basis-Command).

_BEIRAT_FELDER = ("id", "anzeige", "beschreibung", "perspektive", "farbe", "model", "vorsitz")


def _beirat_dto(m: dict) -> dict:
    """Antwortfelder eines Beiratsplatzes. Die gekürzte `beschreibung` (Tooltip) folgt der Sprache;
    `perspektive` ist der bearbeitbare Originaltext der Persona-Datei und bleibt, wie er gespeichert ist."""
    d = {k: m[k] for k in _BEIRAT_FELDER}
    d["beschreibung"] = uebersetzt(d["beschreibung"])
    return d


@app.get("/api/beirat/mitglieder")
def beirat_mitglieder():
    import beirat_engine as be
    return [_beirat_dto(m) for m in be.lade_mitglieder()]


@app.patch("/api/beirat/mitglieder/{platz_id}")
def beirat_mitglied_patch(platz_id: str, payload: dict):
    """Metadaten EINES Beiratsplatzes ändern (Phase 90, B2) — Farbe, Vorsitz-Markierung,
    Perspektive (`description`) und Anzeigename. Schreibt NUR das Frontmatter der Datei neu,
    der Body (der 8-KB-Persona-Text) bleibt byte-genau erhalten; einzige Ausnahme ist die
    Body-Zeile „Du bist **<Name>**“ beim Umbenennen (s. `beirat_engine.aktualisiere_mitglied()`).
    Nicht erlaubte Payload-Schlüssel werden stillschweigend ignoriert (Whitelist statt 422 auf
    unbekannte Felder — das Frontend schickt hier nur den geänderten Kartenzustand, kein
    beliebiges Objekt)."""
    import beirat_engine as be
    erlaubt = {"anzeige", "perspektive", "farbe", "vorsitz"}
    felder = {k: v for k, v in (payload or {}).items() if k in erlaubt}
    try:
        m = be.aktualisiere_mitglied(platz_id, felder)
    except be.MitgliedNichtGefunden as e:
        raise HTTPException(404, str(e))
    except be.MitgliedFehler as e:
        raise HTTPException(422, str(e))
    return _beirat_dto(m)


@app.post("/api/beirat/mitglieder/{platz_id}/neu-besetzen")
async def beirat_mitglied_neu_besetzen(platz_id: str, payload: dict, session: Session = Depends(get_session)):
    """Startet den Skill-Lauf, der einen Beiratsplatz KOMPLETT neu besetzt (Phase 90, B3+C) —
    Name und Perspektive kommen aus dem Formular, den 8-KB-Persona-Text erzeugt erst der Lauf
    (Design-Entscheidung 3: „Der Persona-Text wird nie im Browser getippt“). Muster wie
    `POST /api/profil/einlesen`: `create_task()` direkt mit `params` aufrufen — Guards
    (Tagesbudget/Doppellauf) laufen dort automatisch mit."""
    import beirat_engine as be
    name = (payload.get("name") or "").strip()
    perspektive = (payload.get("perspektive") or "").strip()
    if not name:
        raise HTTPException(422, tx("name ist Pflicht"))
    if not perspektive:
        raise HTTPException(422, tx("perspektive ist Pflicht"))
    if platz_id not in {m["id"] for m in be.lade_mitglieder()}:
        raise HTTPException(404, tx("Beiratsplatz nicht gefunden"))
    task_dto = await create_task(
        {"kind": "beirat-persona",
         "params": {"platz_id": platz_id, "name": name, "perspektive": perspektive}},
        session)
    return {"task_id": task_dto["id"], "task": task_dto}


@app.post("/api/beirat/mitglieder/{platz_id}/uebernehmen")
def beirat_neubesetzung_uebernehmen(platz_id: str):
    """Übernimmt die Ergebnisse eines `beirat-persona`-Laufs nach `.claude/agents/` (Phase 90-
    Nachtrag). Der Lauf selbst kann das nicht: Die Sandbox verweigert jeden Schreibzugriff auf
    `.claude/` (Selbstmodifikations-Schutz), belegt im Testlauf 1162 vom 23.08.2026 — er legt
    seine Dateien deshalb unter `data/tmp/beirat_neubesetzung/` ab und ruft danach diesen
    Endpunkt. Die Validierung sitzt in `beirat_engine.uebernehme_neubesetzung()`: nur
    vollständige Personas für BESTEHENDE Plätze, alles-oder-nichts."""
    import beirat_engine as be
    try:
        return be.uebernehme_neubesetzung(platz_id)
    except be.MitgliedNichtGefunden as e:
        raise HTTPException(404, str(e))
    except be.MitgliedFehler as e:
        raise HTTPException(422, str(e))


@app.get("/api/beirat/keys")
def beirat_keys_status():
    """Nur Status/Maske — die Schlüssel selbst verlassen ~/.bewerbung_beirat/keys.json nie."""
    import beirat_engine as be
    return be.keys_status()


@app.post("/api/beirat/keys")
def beirat_keys_setzen(payload: dict):
    """anthropic/openai: fehlend = unverändert, "" = löschen, sonst setzen. Lokal, chmod 600,
    außerhalb von Projekt & iCloud — nie hartkodiert, nie im Repo."""
    import beirat_engine as be
    be.keys_schreiben(payload.get("anthropic"), payload.get("openai"))
    return be.keys_status()


@app.get("/api/beirat/debatten")
def beirat_debatten():
    import beirat_engine as be
    return be.debatten_liste()


@app.get("/api/beirat/debatten/{debatte_id}")
def beirat_debatte(debatte_id: str):
    import beirat_engine as be
    d = be.debatte_lesen(debatte_id)
    if not d:
        raise HTTPException(404, tx("Debatte nicht gefunden"))
    return d


@app.post("/api/beirat/debatten")
async def beirat_debatte_starten(payload: dict, session: Session = Depends(get_session)):
    """Startet eine Debatte als Hintergrund-Task; live mitlesen über …/{id}/stream (SSE).

    Reihenfolge bewusst gewählt (Phase 62A, P1-5): erst die billigen Eingabe-Validierungen
    (Thema/Provider/Key) und der bestehende Lauf-Konflikt (409, „läuft bereits") — DANACH erst
    der Budget-Guard unmittelbar vor dem eigentlichen Engine-Start. Ein Tippfehler im Thema
    soll als 422 sichtbar werden, nicht hinter einem 409 „Budget" verschwinden; ist das Thema
    dagegen gültig, ist ein 409 „Tagesbudget"/Not-Aus die nützlichere Meldung als ein blinder
    Start, der sofort wieder abbricht.
    """
    import beirat_engine as be
    thema = (payload.get("thema") or "").strip()
    if not thema:
        raise HTTPException(422, tx("Thema ist Pflicht"))
    provider = payload.get("provider") or "anthropic"
    if provider not in ("anthropic", "openai"):
        raise HTTPException(422, tx("provider muss anthropic oder openai sein"))
    if provider == "openai" and not be.keys_status()["openai_gesetzt"]:
        raise HTTPException(422, tx("Für OpenAI zuerst einen Key hinterlegen (Beirat → Schlüssel)"))
    laufende = [d for d in be.DEBATTEN.values() if d.status == "läuft"]
    if laufende:
        raise HTTPException(409, tx("Es läuft bereits eine Debatte — erst beenden oder stoppen"))
    _guard_tagesbudget(session)  # Tagesbudget + Not-Aus (Phase 62A) — unmittelbar vor dem Start
    d = be.debatte_starten(
        thema=thema, kontext=payload.get("kontext") or "",
        min_beitraege=int(payload.get("min_beitraege") or 10),
        teilnehmer_ids=payload.get("teilnehmer") or None,
        provider=provider, openai_model=payload.get("openai_model") or "gpt-4o")
    return {"id": d.id, "min_beitraege": d.min_beitraege, "max_beitraege": d.max_beitraege,
            "teilnehmer": [m["id"] for m in d.teilnehmer]}


def _beirat_stellen_check_starten(job: Job, session: Session, min_beitraege: int = 8):
    """Gemeinsamer Kern für den dedizierten Endpunkt UND die Erneut-Weiche in create_task()
    (Phase 42 Stufe B, Design-Entscheidung 5) — EINE Stelle, die den Kontext/Thema baut und
    die Engine startet, damit beide Einstiege nicht auseinanderdriften können.

    Guard (Phase 62A, P1-5): Tagesbudget + Not-Aus werden HIER geprüft — genau der Sinn dieser
    gemeinsamen Stelle, s. Docstring oben. Reihenfolge: der bestehende Job-Konflikt-Check
    zuerst (billiger Dict-Lookup), dann der Guard, DANACH erst der Kontextaufbau (liest CV/
    Company-Fit-Dateien) und der eigentliche Engine-Start — ein bereits laufender Check für
    denselben Job oder ein Budget-Block sollen nicht erst die Kontext-Dateien lesen, bevor sie
    abbrechen.
    ACHTUNG bei künftigen Aufräumarbeiten: Über create_task() (Zeile ~767, `_guard_tagesbudget`
    in der „beirat-stellen-check"-Weiche) wird der Guard dadurch ZWEIMAL geprüft, wenn dieser
    Pfad genommen wird. Das ist beabsichtigt und unschädlich (reine Lesekontrolle ohne
    Nebenwirkung, kein doppelter Verbrauch) — NICHT als vermeintliches Duplikat entfernen: der
    dedizierte Endpunkt POST /api/beirat/stellen-check ruft NUR diese Funktion auf und hat
    sonst gar keinen Guard.
    """
    import beirat_engine as be
    from pipeline.user_profile import user_first_name
    if be.laufende_stellen_check_fuer_job(job.id):
        raise HTTPException(409, tx("Für diese Stelle läuft bereits ein Beirats-Check"))
    _guard_tagesbudget(session)
    company = session.get(Company, job.company_id) if job.company_id else None
    kontext, company_fit_fehlt = be.sammle_stellen_kontext(job, company)
    thema = tx("Stellen-Check: Soll sich {name} auf „{titel}“ bei {firma} bewerben? (Job {job_id})",
              name=user_first_name(), titel=job.title, firma=job.company_name or tx("der Firma"), job_id=job.id)
    d = be.debatte_starten(
        thema=thema, kontext=kontext, min_beitraege=min_beitraege,
        teilnehmer_ids=None, provider="anthropic", openai_model="gpt-4o",
        modus="stellen_check", job_id=job.id, job_titel=job.title,
        job_firma=job.company_name or "", company_fit_fehlt=company_fit_fehlt)
    return d, company_fit_fehlt


@app.post("/api/beirat/stellen-check")
async def beirat_stellen_check(payload: dict, session: Session = Depends(get_session)):
    """Startet den Charta-Stellen-Check für EINEN Job (Phase 40): deterministischer Kontext
    (Anzeigentext/CV/Company-Fit/verify_note) → moderierte Debatte → Abstimmung aller 7 Köpfe →
    deterministische Entscheidung → Vorsitz-Synthese → Dashboard-HTML + JobFile-Registrierung.
    Live-Verfolgung über den bestehenden SSE-Stream …/debatten/{id}/stream."""
    job_id = payload.get("job_id")
    job = session.get(Job, job_id) if job_id else None
    if not job or job.deleted_at:
        raise HTTPException(404, tx("Stelle nicht gefunden"))
    d, company_fit_fehlt = _beirat_stellen_check_starten(
        job, session, int(payload.get("min_beitraege") or 8))
    return {"id": d.id, "min_beitraege": d.min_beitraege, "max_beitraege": d.max_beitraege,
            "company_fit_fehlt": company_fit_fehlt}


@app.post("/api/beirat/debatten/{debatte_id}/stop")
def beirat_debatte_stoppen(debatte_id: str):
    """Sanfter Stopp: nach dem laufenden Beitrag geht es direkt in die Synthese."""
    import beirat_engine as be
    d = be.DEBATTEN.get(debatte_id)
    if not d:
        raise HTTPException(404, tx("Debatte nicht (mehr) aktiv"))
    d.stop_gewuenscht = True
    return {"ok": True}


@app.get("/api/beirat/debatten/{debatte_id}/stream")
async def beirat_debatte_stream(debatte_id: str):
    """SSE-Live-Strom der Debatte (Moderation, Beitrag-Start, Token-Deltas, Synthese)."""
    import beirat_engine as be
    from fastapi.responses import StreamingResponse

    d = be.DEBATTEN.get(debatte_id)
    if not d:
        gespeichert = be.debatte_lesen(debatte_id)
        if not gespeichert:
            raise HTTPException(404, tx("Debatte nicht gefunden"))

        async def _abgeschlossen():
            yield f"data: {json.dumps({'typ': 'archiv', 'debatte': gespeichert}, ensure_ascii=False)}\n\n"
        return StreamingResponse(_abgeschlossen(), media_type="text/event-stream")

    async def _strom():
        # Einstieg mitten in einer laufenden Debatte: erst den bisherigen Stand liefern
        yield f"data: {json.dumps({'typ': 'stand', 'debatte': d.als_dict()}, ensure_ascii=False)}\n\n"
        while True:
            try:
                ev = await asyncio.wait_for(d.queue.get(), timeout=25)
            except asyncio.TimeoutError:
                yield ": ping\n\n"          # Keep-Alive
                continue
            if ev is None:
                break
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(_strom(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Serve built frontend in production (single-process deployment) ─────────────
# The SPA uses client-side routing, so unknown non-/api paths fall back to index.html.
_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
# P2-64: Was `spa` ausliefert, trägt `no-cache`: index.html und die Dateien direkt in dist (Icons).
# Ihre Namen bleiben über einen Build gleich, der Inhalt nicht. FileResponse sendet nur
# Last-Modified und ETag, der Browser schätzt die Frische dann selbst: In Chrome 154 gemessen ein
# Zehntel des Dateialters, ein zehn Tage alter Build gilt also einen Tag lang ohne Nachfrage. Eine
# schon besuchte Adresse zeigte so nach `frontend/build.sh` oder einem Update weiter die alte
# index.html, deren Bundle gelöscht ist: leere Seite, oder die alte Oberfläche am neuen Server,
# solange das alte Bundle noch im Cache liegt. Mit no-cache fragt der
# Browser bei jedem Aufruf nach; index.html kommt dann ganz (FileResponse kennt kein 304), gut
# 500 Bytes, und Klicks innerhalb der Oberfläche laden sie gar nicht. /assets bleibt ohne: Der
# Hash im Namen ändert sich mit dem Inhalt, und StaticFiles beantwortet Nachfragen mit 304.
_OBERFLAECHE_KOPF = {"Cache-Control": "no-cache"}


def spa(full_path: str):
    """P2-54: liefert nur Dateien INNERHALB von frontend/dist. Vorher reichte `_DIST / full_path`
    jeden Pfad durch, den der Aufrufer per `%2e%2e` oder `%2F` hineinschrieb: `GET
    /%2e%2e/%2e%2e/README.md` lieferte die Projektdatei, `GET /%2Fetc%2Fhosts` eine Systemdatei,
    also auch data/bewerbung.sqlite und ~/.bewerbung_mgmt_secrets an /api/artifact vorbei. Alles,
    was nicht in dist liegt, bekommt index.html wie jede Client-Route. Jede Antwort trägt
    `_OBERFLAECHE_KOPF` (P2-64). Modulfunktion, damit die Tests sie ohne gebautes Frontend prüfen
    können (tests/test_spa_fallback.py)."""
    if full_path.startswith("api"):
        raise HTTPException(404, tx("Unbekannter API-Endpunkt"))
    dist = _DIST.resolve()
    ziel = dist / full_path
    kandidat = dist                        # Ausgangswert: index.html
    if not _netzpfad(ziel):
        try:
            kandidat = ziel.resolve()
        except (OSError, RuntimeError, ValueError):   # Nullbyte, Symlink-Schleife, Sondernamen
            pass
    if dist in kandidat.parents and os.path.isfile(kandidat):
        return FileResponse(str(kandidat), headers=_OBERFLAECHE_KOPF)
    return FileResponse(str(dist / "index.html"), headers=_OBERFLAECHE_KOPF)


def _oberflaeche_einhaengen(ziel: FastAPI, dist: Path) -> None:
    """Hängt die gebaute Oberfläche an: /assets per StaticFiles, alles Übrige per `spa`. Eigene
    Funktion, damit tests/test_spa_fallback.py die echte Verdrahtung prüft, nicht eine Kopie."""
    if (dist / "assets").exists():
        ziel.mount("/assets", StaticFiles(directory=str(dist / "assets")), name="assets")
    ziel.get("/{full_path:path}")(spa)


if _DIST.exists():
    _oberflaeche_einhaengen(app, _DIST)
