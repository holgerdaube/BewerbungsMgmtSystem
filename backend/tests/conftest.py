"""Gemeinsame pytest-Fixtures — Isolation gegen die LIVE-DB (Phase 57 Stufe E1, Invariante T1).

KRITISCHE IMPORT-REIHENFOLGE: `app/db.py` bindet `DATA_DIR`/`DB_PATH` BEIM MODUL-IMPORT
(`Path(os.environ.get("BMS_DATA_DIR", PROJECT_ROOT / "data"))`); seit Phase 63B bindet
`app/agent_runner.py` genauso `LOG_DIR` (`Path(os.environ.get("BMS_LOG_DIR", ...))`). Wird
irgendein `app.*`/`pipeline.*`-Modul importiert, BEVOR `BMS_DATA_DIR`/`BMS_LOG_DIR` gesetzt
sind, bindet es sich an die ECHTEN Pfade (`data/bewerbung.sqlite` bzw.
`~/.bewerbung_mgmt_logs/`) — unumkehrbar für den Rest des Prozesses (Re-Import cached das
Modul). Deshalb:
  1. `BMS_DATA_DIR` UND `BMS_LOG_DIR` werden ganz oben auf MODULEBENE dieser Datei gesetzt
     (Python führt Module genau einmal aus, vor jeder Fixture/jedem Test) — VOR jedem
     `app.*`/`pipeline.*`-Import.
  2. Diese Datei importiert selbst NICHTS aus `app.*`/`pipeline.*` auf Modulebene — nur
     Stdlib + pytest. Alle App-Importe passieren funktionslokal in den Fixtures unten.
  3. Testdateien halten sich an dieselbe Regel (siehe deren Docstrings): App-Module NIE auf
     Modulebene importieren, nur in Testfunktionen/Fixtures.

Da pytest sein eingebautes `tmp_path` erst JE TEST anlegt (zu spät — wir brauchen den Pfad schon
beim Modul-Import), bauen wir das Isolationsverzeichnis selbst mit `tempfile.mkdtemp()` und räumen
es am Interpreter-Ende über `atexit` auf.
"""
import atexit
import os
import shutil
import tempfile

import pytest

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="bms_pytest_data_")
os.environ["BMS_DATA_DIR"] = _TMP_DATA_DIR
atexit.register(shutil.rmtree, _TMP_DATA_DIR, True)

# Phase 63B (P1-3): agent_runner.LOG_DIR liegt seit dieser Phase außerhalb von data/ (eigener
# Override BMS_LOG_DIR, s. app/agent_runner.py) — braucht dieselbe Vorflug-Isolation wie
# BMS_DATA_DIR oben, sonst würde ein Test, der den FastAPI-Lifespan bzw. cleanup_logs()
# auslöst, gegen das ECHTE ~/.bewerbung_mgmt_logs/ laufen (T1-Verstoß).
_TMP_LOG_DIR = tempfile.mkdtemp(prefix="bms_pytest_logs_")
os.environ["BMS_LOG_DIR"] = _TMP_LOG_DIR
atexit.register(shutil.rmtree, _TMP_LOG_DIR, True)


@pytest.fixture(scope="session")
def _headless_token_datei(tmp_path_factory):
    """Session-weit EINE synthetische agent.env — bewusst in einem EIGENEN tmp-Verzeichnis
    (`tmp_path_factory`), NICHT im Test-`tmp_path`: Tests wie
    test_outbound_check::test_scan_liest_niemals_… erwarten ihr `tmp_path` leer."""
    env_datei = tmp_path_factory.mktemp("bms_auth") / "agent.env"
    env_datei.write_text("CLAUDE_CODE_OAUTH_TOKEN=oat01-conftest-synthetisch\n", encoding="utf-8")
    return env_datei


@pytest.fixture(autouse=True)
def _headless_token_deterministisch(monkeypatch, _headless_token_datei):
    """Phase 77, CI-Fund 07.08.2026 (Run 31220328925): Seit die Beirats-Turns die Auth-Priorität
    keys.json > agent.env-Token > Keychain kennen, hängt JEDER Test, der `Debatte.laufen()` bzw.
    `_turn_env()` erreicht, am Host-Zustand — auf einer eingerichteten Installation existiert das echte
    `~/.bewerbung_mgmt_secrets/agent.env` (Token-Weg, alles grün), in der CI nicht (Keychain-Fall
    → die Vorwärm-Schleuse versucht die ECHTE claude-CLI zu starten, die Debatten-Tests aus
    test_beirat_fehler.py brachen vor dem ersten Dispatch ab). Deshalb hier autouse: JEDER Test
    sieht dasselbe tmp-`agent.env` mit synthetischem Token — Auth-Weg deterministisch
    „agent.env-Token", host-unabhängig, keine Vorwärmung. Tests, die einen anderen Auth-Zustand
    brauchen (Keychain-Fall, eigenes Parsing), setzen `agent_runner.ENV_FILE` danach selbst per
    monkeypatch — der Test-innere setattr gewinnt gegen diese Fixture. Wert ist reine
    Kleinbuchstaben-Wortkette (bewusst OHNE das Präfix echter Anthropic-Tokens —
    Secret-Guard-/gitleaks-kompatibel, s. .gitleaks.toml-Allowlist)."""
    from app import agent_runner

    monkeypatch.setattr(agent_runner, "ENV_FILE", _headless_token_datei)


@pytest.fixture(autouse=True)
def _anzeigentext_attrappe(request, monkeypatch):
    """P2-75: `create_task` ruft vor jedem Unterlagen-Lauf (firma-pruefen, cv-match, cv-erstellen,
    anschreiben-erstellen und alle Ketten damit, z. B. bewerbungspaket) `posting_snapshot.
    anzeigentext_sichern()` auf. Bei einer Stelle ohne Anzeigentext im Snapshot würde das einen
    ECHTEN Nachhol-Abruf ins Netz auslösen oder, wenn er scheitert, ein 409 ANZEIGE_FEHLT liefern.
    Deshalb meldet für JEDEN Test die Attrappe „vorhanden“ (Text liegt vor, kein Netzabruf, nichts
    wird geschrieben) — so bleiben alle Tests, die per POST /api/tasks Unterlagen-Läufe einreihen
    (test_bewerbungspaket_optional.py u. a.), deterministisch und netzfrei. Ausgenommen ist nur
    `test_posting_snapshot_nachholen`: dort wird die echte Funktion geprüft (ihr `check_url` ist
    dort selbst gepatcht). `test_anzeige_gate.py` setzt seine eigene Attrappe darüber (der
    Test-innere setattr gewinnt gegen diese Fixture). `raising=False`, weil das Attribut erst mit
    dem Nachhol-Paket in `posting_snapshot` steht. Import funktionslokal (conftest-Regel)."""
    if request.module.__name__.rsplit(".", 1)[-1] == "test_posting_snapshot_nachholen":
        return
    import pipeline.posting_snapshot as posting_snapshot

    def _vorhanden(job_id):
        return {"job_id": job_id, "status": "vorhanden", "grund": None, "befund": None,
                "versuche": 0, "posting_snapshot_path": None}

    monkeypatch.setattr(posting_snapshot, "anzeigentext_sichern", _vorhanden, raising=False)


@pytest.fixture(scope="session", autouse=True)
def _sqlite_ohne_plattenbestaetigung():
    """P2-65: Jede SQLite-Verbindung, die im Testprozess über SQLAlchemy entsteht, läuft mit
    `PRAGMA synchronous=OFF`: SQLite wartet nach einem Commit nicht mehr, bis die Platte das
    Schreiben bestätigt. Inhalt, Sichtbarkeit für andere Verbindungen und Prozesse und die Sperren
    bleiben gleich; es entfällt nur der Schutz bei Stromausfall, den kein Test prüft.

    Warum: Viele Tests bauen ein eigenes Schema, je Lauf rund 10.800 CREATE-Anweisungen, jede ein
    eigener Commit. Ein Schema kostete auf dem Windows-Runner 1,2–2,8 s (`%TEMP%` auf C:), mit OFF
    0,16–0,29 s; unter Linux 25 statt 89 ms (Probelauf 36893114358). Die App selbst bleibt bei der
    SQLite-Voreinstellung; das und die Fixture prüft `test_testumgebung.py`. Subprozesse (Erst-
    Start, Selbsttest) laden diese Datei nicht und laufen wie die App. Autouse und sitzungsweit,
    damit die Fixture vor jeder Engine-Verbindung steht; der Import bleibt funktionslokal
    (Modulebene nur Stdlib + pytest, s. oben)."""
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    def _pragma(dbapi_verbindung, _eintrag):
        cursor = dbapi_verbindung.cursor()
        cursor.execute("PRAGMA synchronous=OFF")
        cursor.close()

    event.listen(Engine, "connect", _pragma)
    yield
    event.remove(Engine, "connect", _pragma)


@pytest.fixture(scope="session")
def _db_ready():
    """Erst-Import von `app.db` NACH dem Env-Override (s. Moduldocstring) + Sicherheitsnetz:
    `DB_PATH` MUSS unter dem tmp-Verzeichnis liegen. Andernfalls hat irgendein Modul `app.db`
    bereits vorher importiert (z. B. über eine versehentliche Modulebene-Import-Kette) und an die
    ECHTE `data/bewerbung.sqlite` gebunden — dann ABBRECHEN statt weiterzulaufen (T1)."""
    from app.db import DB_PATH, init_db

    assert str(DB_PATH).startswith(_TMP_DATA_DIR), (
        f"SICHERHEITSNETZ ausgelöst: app.db.DB_PATH ({DB_PATH}) liegt NICHT unter dem "
        f"pytest-tmp-Verzeichnis ({_TMP_DATA_DIR}). Das bedeutet, ein app.*/pipeline.*-Modul "
        f"wurde VOR dem BMS_DATA_DIR-Override importiert und hat sich an die echte Live-DB "
        f"gebunden. ABBRUCH — Tests dürfen NIE gegen data/bewerbung.sqlite laufen (Invariante T1)."
    )
    init_db()
    return DB_PATH


@pytest.fixture()
def session(_db_ready):
    """SQLModel-Session auf der tmp-DB (nach init_db())."""
    from sqlmodel import Session
    from app.db import engine

    with Session(engine) as s:
        yield s


@pytest.fixture()
def client(_db_ready):
    """FastAPI-TestClient — App-Import bewusst hier (Fixture), nicht auf Modulebene.

    BEWUSST OHNE `with TestClient(app) as c:` — der `with`-Block triggert den ASGI-Lifespan
    (FastAPI-`startup`-Event `app.main._startup()`), der wiederum `agent_runner.start_workers()`
    aufruft (u. a. `cleanup_logs()`). Bis Phase 63B war das ein echter T1-Verstoß: `LOG_DIR`
    wurde HART über `PROJECT_ROOT / "data"` gebaut und reagierte auf KEINEN Env-Override — ein
    Lifespan-Start in Tests hätte also ECHTE Dateien im echten `data/agent_logs/` gelöscht
    (s. Report Phase 57 E1, Abschnitt „Nebenfix"). Seit Phase 63B liegt `LOG_DIR` ohnehin
    außerhalb von `data/` und liest `BMS_LOG_DIR` (oben auf Modulebene wie `BMS_DATA_DIR` auf
    ein tmp-Verzeichnis gesetzt) — der akute Risikopfad ist damit geschlossen. `with` bleibt
    trotzdem aus: keiner der hier getesteten Endpunkte (health/jobs/dashboard/artifact)
    braucht die Worker-Queue, ein inaktiver Lifespan ist schlicht die einfachere Ausgangslage
    (empirisch geprüft: 0 Aufrufe von `start_workers()` ohne `with`, 1 Aufruf mit `with`).
    """
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def seed(session):
    """Synthetische Minimal-Welt (T3 — NIE echte Live-Daten): 2 Companies, 2 Jobs,
    1 Application, 1 CVVersion. Jeder Aufruf bekommt einen eindeutigen Suffix, damit mehrere
    Tests, die `seed` nutzen, sich in der session-weiten tmp-DB nicht gegenseitig verfälschen
    (keine Transaktions-Rollbacks zwischen Tests vorgesehen — Assertions arbeiten deshalb gegen
    die hier zurückgegebenen, garantiert eindeutigen Namen statt gegen Tabellen-Gesamtzahlen)."""
    import uuid
    from datetime import date
    from app.models import Application, Company, CVVersion, Job

    suffix = uuid.uuid4().hex[:8]
    firma_a = f"Musterfirma GmbH {suffix}"
    firma_b = f"Test AG {suffix}"

    c1 = Company(name=firma_a)
    c2 = Company(name=firma_b)
    session.add(c1)
    session.add(c2)
    session.commit()
    session.refresh(c1)
    session.refresh(c2)

    j1 = Job(company_id=c1.id, company_name=c1.name, title="Head of Customer Success",
             status="Beworben", found_date=date.today().isoformat(),
             dedup_key=f"seed|{suffix}|1", match_score=4)
    j2 = Job(company_id=c2.id, company_name=c2.name, title="Director Professional Services",
             status="Neu", found_date=date.today().isoformat(),
             dedup_key=f"seed|{suffix}|2", match_score=3)
    session.add(j1)
    session.add(j2)
    session.commit()
    session.refresh(j1)
    session.refresh(j2)

    application = Application(job_id=j1.id, status="Beworben",
                              applied_date=date.today().isoformat(), channel="E-Mail")
    session.add(application)
    cv_version = CVVersion(job_id=j1.id, language="DE", kind="tailored", status="fertig")
    session.add(cv_version)
    session.commit()
    session.refresh(application)
    session.refresh(cv_version)

    return {
        "suffix": suffix,
        "companies": [c1, c2],
        "jobs": [j1, j2],
        "application": application,
        "cv_version": cv_version,
    }
