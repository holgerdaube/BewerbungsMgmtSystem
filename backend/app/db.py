"""Database engine + session helpers. SQLite is the single source of truth."""
import os
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, create_engine

BACKEND_DIR = Path(__file__).resolve().parent.parent   # .../backend
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = Path(os.environ.get("BMS_DATA_DIR", PROJECT_ROOT / "data"))
DB_PATH = DATA_DIR / "bewerbung.sqlite"


def artefakt_pfad(rel_path) -> Path:
    """Löst einen in der DB gespeicherten, projekt-relativen Artefakt-Pfad zu einem echten
    Dateipfad auf (z. B. `job.posting_snapshot_path` = "data/job_postings/x.html",
    `CVVersion.file_path` = "outputs/cv/y.docx").

    Phase 79 (08.08.2026): Die Schreiber legen Artefakte unter `DATA_DIR` ab, die gespeicherten
    Pfade beginnen aber mit dem LITERAL "data/" — solange `DATA_DIR == PROJECT_ROOT/"data"` ist
    (Produktion), fällt das nicht auf. Unter Test-Isolation (`BMS_DATA_DIR` zeigt auf ein
    tmp-Verzeichnis) zeigen beide Wurzeln auf verschiedene Orte: ein Leser, der stur
    `PROJECT_ROOT / rel_path` bildet, findet die gerade geschriebene Datei nicht — oder,
    schlimmer, er findet die ECHTE Datei der Entwicklungsinstallation (genau dieses Leck ließ Testläufe bis Phase 79
    in `data/job_postings/` schreiben, 265 Artefakte). Deshalb hier EINE gemeinsame Auflösung
    für alle Leser (dedup_text, search_index, beirat_engine, transcript_report):
    `data/`-Pfade gegen die AKTIVE Datenwurzel, alles andere (outputs/, config/, assets/) wie
    bisher gegen den Projekt-Root — `outputs/` ist bewusst NICHT isoliert (die Nutzerdokumente
    liegen dort, Tests fassen sie ohnehin nicht an)."""
    rel = str(rel_path).lstrip("/")
    if rel.startswith("data/"):
        return DATA_DIR / rel[len("data/"):]
    return PROJECT_ROOT / rel

# P2-2 (Phase 67F): expliziter busy_timeout statt des zufälligen Python-Default-Verhaltens.
# Der Python-sqlite3-Treiber setzt ohne eigenes Zutun bereits ~5 s Retry, die `sqlite3`-CLI
# dagegen 0 (sofortiges "database is locked"). 15 s ist bewusst GROSSZÜGIG gewählt: der
# gemessene kritische Schreibvorgang (search_index.rebuild()) dauert real nur 0,38 s, ein
# Vielfaches an Reserve kostet im Erfolgsfall nichts (die Wartezeit endet, sobald die Sperre
# frei wird) und schützt gegen einen zufällig längeren Ausreißer (Spotlight/iCloud-Sync-Zugriff
# auf dieselbe Datei). WAL ist bewusst NICHT aktiviert (Sidecar-Dateien -wal/-shm vertragen sich
# schlecht mit iCloud-Sync) — s. tasks/code_review_2026-07-25.md P2-2 + Empfehlung am Dateiende.
# Als benannte Konstante (statt Inline-Dict) ausgelagert, damit ein Test den gewählten Wert
# direkt prüfen kann, ohne in SQLAlchemy-/sqlite3-Interna zu graben (`Connection.timeout` ist in
# Python nicht auslesbar — schreib-only bei `sqlite3.connect()`).
CONNECT_ARGS = {"check_same_thread": False, "timeout": 15}
# Phase 100: SQLite legt die DB-DATEI selbst an, das VERZEICHNIS aber nicht — und `data/` ist
# per .gitignore ausgeschlossen. Auf einer frischen Installation (git clone, noch kein `data/`)
# scheiterte der erste Serverstart deshalb mit „unable to open database file", ohne dass die
# Meldung den fehlenden Ordner genannt hätte. Hier statt in `init_db()`, weil auch Einstiegspunkte
# ohne Startup-Hook (Skripte, `python -m pipeline.…`) über dieselbe Engine gehen.
DATA_DIR.mkdir(parents=True, exist_ok=True)
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    connect_args=CONNECT_ARGS,
)

# Leichte Auto-Migration: fehlende Spalten additiv ergänzen (SQLite ALTER TABLE ADD COLUMN).
_ADD_COLUMNS = {
    "company": [
        ("fit_ampel", "TEXT"),      # gruen|gelb|rot — Phase 24 F, gesetzt von firma-pruefen
    ],
    "email": [
        ("reply_draft_at", "TEXT"),  # Phase 27 — Antwort-Entwurf liegt in Gmail seit …
        ("archived_at", "TEXT"),     # P2-52 — Tombstone: Mail ohne Stelle in der App archiviert
    ],
    "headhunter": [
        ("webseite", "TEXT"),           # Phase 26 A
        ("karriere_url", "TEXT"),       # Phase 26 B — gecachter Karriere-/Jobs-Link
        ("last_career_check", "TEXT"),  # Phase 26 B — Rotation: NULL zuerst, dann aufsteigend
        ("deleted_at", "TEXT"),         # Phase 28 A — Soft-Delete-Tombstone
    ],
    "targetcompany": [
        ("karriere_url", "TEXT"),       # Phase 26 B
        ("last_career_check", "TEXT"),  # Phase 26 B
        ("deleted_at", "TEXT"),         # Phase 28 A — Soft-Delete-Tombstone
    ],
    "cvversion": [
        ("match_score100", "INTEGER"),
        ("match_dashboard_path", "TEXT"),
        ("ats_scan_path", "TEXT"),
        ("pdf_path", "TEXT"),
        # Phase 46 Stufe B — SQL-DEFAULT (nicht nur Python-Field-Default!), damit SQLite
        # bestehende Zeilen beim ALTER TABLE automatisch mit 'fertig' befüllt (Altbestand
        # durchlief immer den kompletten Ein-Klick-Flow → rückwirkend korrekt "fertig").
        ("status", "TEXT DEFAULT 'fertig'"),
        ("entwurf_text", "TEXT"),
        ("keywords_json", "TEXT"),  # Phase 55 — Keyword-Protokoll Methodik v2, aus cv-match
    ],
    "job": [
        ("follow_up_date", "TEXT"),
        ("notes", "TEXT"),
        ("gut_feeling", "INTEGER"),
        ("verified_at", "TEXT"),
        ("verify_note", "TEXT"),
        ("posting_snapshot_path", "TEXT"),
        ("deleted_at", "TEXT"),         # Phase 32 B — Soft-Delete-Tombstone (Dedup bleibt wirksam)
        ("career_url", "TEXT"),         # Phase 73 — Karriereseiten-Fallback bei geschlossenem Portal
        ("portal_closed", "INTEGER DEFAULT 0"),  # Phase 73 — 1 = Portal nimmt keine Bewerbungen mehr an
        ("availability_status", "TEXT"),        # Phase 74 — Beworben-Check (offen/karriereseite_offen/offline/unklar)
        ("availability_checked_at", "TEXT"),    # Phase 74 — ISO-Datum der letzten Verfügbarkeitsprüfung
    ],
    "application": [
        ("rejection_reason", "TEXT"),
        ("cover_letter_pdf_path", "TEXT"),
        ("cover_letter_language", "TEXT"),
        ("cover_letter_text", "TEXT"),
    ],
    "agenttask": [
        ("tokens", "INTEGER"),  # P2-86
        ("chain_id", "TEXT"),
        ("chain_label", "TEXT"),
        ("chain_pos", "INTEGER"),
        ("depends_on", "INTEGER"),
        ("retry_count", "INTEGER DEFAULT 0"),
        # Phase 65 (P1-6): PID des laufenden Subprozesses — gesetzt direkt nach dem Start,
        # geleert bei Abschluss. Überlebt einen Server-Neustart NUR über diese Spalte (das
        # In-Memory-_procs-Dict in agent_runner.py stirbt mit dem Prozess) — Grundlage für die
        # Crash-Recovery in agent_runner._running_wiederherstellen(). S. dort für die
        # Sicherheitsregel (PID-Wiederverwendung) vor jeder Verwendung dieses Werts.
        ("pid", "INTEGER"),
    ],
    "transcript": [
        ("kontakt", "TEXT"),
        ("gespraechsart", "TEXT"),
        ("debrief_path", "TEXT"),
        ("report_path", "TEXT"),     # Phase 30 — Transkript-Report (Basis/Vollversion)
    ],
    "networkcontact": [
        ("next_action", "TEXT"),
        ("next_action_date", "TEXT"),
        ("deleted_at", "TEXT"),         # Phase 28 A — Soft-Delete-Tombstone
    ],
    "sucheinstellung": [
        # P2-86 — bestehende Installationen bleiben bei Claude.
        ("ki_anbieter", "TEXT DEFAULT 'claude'"),
        # Phase 50 — SQL-DEFAULT, damit die bestehende Singleton-Zeile (id=1, seit Phase 49)
        # beim ALTER TABLE automatisch mit '{}' befüllt wird statt NULL zu bleiben.
        ("modelle_json", "TEXT DEFAULT '{}'"),
        # Phase 87 — dieselbe SQL-DEFAULT-Logik für die Suchportale-Liste: die bestehende
        # Singleton-Zeile bekommt beim ALTER TABLE automatisch '[]' statt NULL, main.py::
        # _einstellungen_out() füllt eine leere Liste danach aus PORTALE_DEFAULT auf.
        ("portale_json", "TEXT DEFAULT '[]'"),
        # P2-41 — dasselbe Muster für den Standardumfang des Bewerbungspakets: eine bestehende
        # Singleton-Zeile bekommt beim ALTER TABLE automatisch '{}' statt NULL, main.py::
        # _unterlagen_standard() füllt fehlende Bausteine danach mit False auf.
        ("unterlagen_json", "TEXT DEFAULT '{}'"),
    ],
    "budgetlimit": [
        ("max_runs_per_day", "INTEGER"),  # Phase 54 — nur provider="claude" relevant
    ],
    "outreach": [
        ("bewerbung_datum", "TEXT"),  # Phase 69 — Netzwerk-Bewerbung, s. models.py::Outreach
    ],
    "interview": [
        ("gegenueber", "TEXT"),                    # Phase 69 — Recruiter/Hiring Manager/…
        ("vor_ort", "INTEGER DEFAULT 0"),          # Phase 69 — SQL-DEFAULT: Altbestand = nicht vor Ort
    ],
}


def _ensure_columns() -> None:
    with engine.connect() as conn:
        for table, cols in _ADD_COLUMNS.items():
            try:
                existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            except Exception as e:
                # P2-19: vorher `except Exception: continue` OHNE jede Ausgabe — die komplette
                # Spalten-Migration DIESER EINEN Tabelle verschwand spurlos; ein Tage später
                # auftretendes "no such column" war dann nicht mehr zuordenbar. Jetzt laut:
                # Tabellenname + Fehler auf stdout. Weiter zur nächsten Tabelle (ein kaputter
                # PRAGMA-Aufruf für EINE Tabelle darf die Migration der übrigen nicht verhindern).
                print(f"[db] WARNUNG: Spalten-Migration für Tabelle '{table}' übersprungen "
                      f"(PRAGMA table_info fehlgeschlagen): {type(e).__name__}: {e}", flush=True)
                continue
            if not existing:
                continue
            for name, typ in cols:
                if name in existing:
                    continue
                try:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
                except Exception as e:
                    # SQLite kennt kein "ADD COLUMN IF NOT EXISTS". Seit Phase 63 startet jeder
                    # Skill-Lauf init_db() in einem eigenen Subprozess (s. tasks/spec_phase64_
                    # fehlerpfade.md) — zwei fast gleichzeitig gestartete Prozesse können beide
                    # dieselbe Spalte in PRAGMA als fehlend sehen und beide ALTER TABLE versuchen;
                    # der zweite bekommt "duplicate column name" vom jeweils anderen Prozess, der
                    # zuerst fertig wurde. Das ist harmlos (die Spalte existiert danach so oder
                    # so) und darf leise übergangen werden. JEDER ANDERE Fehler (Disk voll,
                    # gesperrte DB, falscher Typ, ...) MUSS laut sein (F4).
                    if "duplicate column" in str(e).lower():
                        continue
                    print(f"[db] WARNUNG: Spalte '{name}' auf Tabelle '{table}' konnte nicht "
                          f"ergänzt werden: {type(e).__name__}: {e}", flush=True)
        conn.commit()


# P2-3 (Phase 67F): UNIQUE-Indizes gegen Dubletten auf DB-Ebene — NUR für Felder, deren Bestand
# read-only nachweislich sauber ist (Kollisionstabelle im Phase-67F-Baubericht). Bewusst NICHT
# in dieser Liste: `Job.url` — ein Alt-Duplikat (aus einem einmaligen Excel-Import, keine
# Race) würde JEDEN künftigen Programmstart mit „UNIQUE constraint failed" scheitern lassen,
# solange die beiden Zeilen nicht zusammengeführt sind. Das Zusammenführen ist eine fachliche
# Entscheidung des Nutzers (welcher der beiden Jobs ist der „richtige"?), keine technische — bewusst
# nicht Teil dieser Phase.
# `LOWER(TRIM(name))` für Company: dieselbe Normalisierung wie `main.py::_norm_name`
# (`.strip().lower()`) — SQLites `LOWER()` faltet nur ASCII a-z/A-Z, KEINE Umlaute; das macht den
# DB-Index nur GLEICH ODER LOCKERER als den Python-Check, nie strenger (jede Kollision, die die
# DB sieht, sieht `_norm_name` also auch) — kein falscher UNIQUE-Fehlschlag durch diese Asymmetrie.
#
# JEDE Insert-/Update-Stelle für eines dieser Felder MUSS seit dieser Phase `flush_or_duplicate()`
# (unten) statt eines nackten `session.flush()`/`session.commit()` nutzen — sonst wird aus einer
# echten (wenn auch seltenen) Dublette ein 500er statt eines sauber gezählten Dubletten-Treffers
# (s. pipeline/ingest.py, pipeline/gmail_ingest.py, app/main.py, import_lists.py,
# import_outreach.py, migrate_tracker.py).
_UNIQUE_INDEXES = [
    # (Index-Name, Tabelle, Spalten-Ausdruck)
    ("ux_job_dedup_key", "job", "dedup_key"),
    ("ux_company_name_nocase", "company", "LOWER(TRIM(name))"),
    ("ux_outreach_dedup_key", "outreach", "dedup_key"),
    ("ux_targetcompany_dedup_key", "targetcompany", "dedup_key"),
    ("ux_headhunter_dedup_key", "headhunter", "dedup_key"),
    ("ux_networkcontact_dedup_key", "networkcontact", "dedup_key"),
    # 26.07.2026 nachgezogen: In Phase 67F bewusst WEGGELASSEN, weil der Bestand eine Kollision
    # trug (zwei Jobs, identische URL — aus dem einmaligen Excel-Import, keine Race).
    # Der Nutzer hat entschieden: einer bleibt, der andere ist die Dublette → dieser ist jetzt Tombstone mit geleerter
    # URL (Original-URL steht in dessen `source_note`), Bestand kollisionsfrei. NULL ist hier
    # unkritisch: SQLite lässt in einem UNIQUE-Index beliebig viele NULLs zu (14 Jobs ohne URL),
    # Leerstrings gäbe es dagegen nur einmal — geprüft: aktuell 0.
    ("ux_job_url", "job", "url"),
]


def _ensure_indexes() -> None:
    """Additive Index-Migration — Gegenstück zu `_ensure_columns()`, gleiches Muster: idempotent
    (`CREATE UNIQUE INDEX IF NOT EXISTS`), jeder Fehlschlag laut auf stdout (P2-19-Lehre: NIE ein
    stilles `except: continue`) und ein kaputter/nicht anlegbarer Index (z. B. weil der Bestand
    doch eine Kollision enthält) darf die Migration der ÜBRIGEN Indizes nicht verhindern."""
    with engine.connect() as conn:
        for name, table, expr in _UNIQUE_INDEXES:
            try:
                conn.exec_driver_sql(f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON {table}({expr})")
            except Exception as e:
                print(f"[db] WARNUNG: UNIQUE-Index '{name}' auf '{table}({expr})' konnte nicht "
                      f"angelegt werden (vermutlich Kollision im Bestand): {type(e).__name__}: {e}",
                      flush=True)
        conn.commit()


def flush_or_duplicate(session: Session, aendern) -> bool:
    """Führt `aendern()` (ein parameterloses Callable) in einem SAVEPOINT (`Session.
    begin_nested()`) aus und fängt eine UNIQUE-Verletzung (`IntegrityError`) ab, statt sie
    weiterzuwerfen.

    P2-3 (Phase 67F): seit `_ensure_indexes()` echte UNIQUE-Indizes anlegt, MUSS jede Insert-/
    Update-Stelle für eines dieser Felder (Company.name, Job.dedup_key, *.dedup_key der vier
    Outreach-Familie-Modelle) diese Funktion statt eines nackten `flush()`/`commit()` nutzen —
    sonst wird aus einer echten (wenn auch seltenen) Dublette ein 500er statt eines sauber
    gezählten Dubletten-Treffers.

    ⚠️ KRITISCHER Aufrufer-Vertrag (empirisch gefunden 26.07.2026, s. tests/
    test_unique_constraints.py für den Beleg): die riskante Änderung — `session.add(neues_objekt)`
    bei einem Insert, ein Attribut-Set (z. B. `tc.dedup_key = neu`) bei einem Rename — MUSS
    INNERHALB von `aendern()` passieren, NICHT vorher. Grund: `Session.begin_nested()` autoflusht
    beim EINTRITT selbst bereits anhängige (pending) Änderungen, um seinen eigenen Snapshot zu
    bilden — bereits VOR dem Aufrufer-Callback und damit VOR dem eigentlichen Savepoint. Wäre die
    riskante Änderung schon vorher anhängig, würde genau DIESER Auto-Flush (nicht der `flush()`
    unten) die Verletzung auslösen — außerhalb der Savepoint-Absicherung, in der ÄUSSEREN
    Transaktion. Die Session bleibt dann bis zu einem expliziten `session.rollback()` (der aber
    auch bereits erfolgreich geflushte Geschwister-Zeilen mit zurückrollen würde) im Zustand
    `PendingRollbackError` gefangen. `aendern()` garantiert, dass NICHTS Riskantes anhängig ist,
    bevor der Savepoint aktiv ist.

    Rückgabe True: `aendern()` + Flush geglückt, die Zeile/Änderung hängt jetzt in der äußeren
    Transaktion (der reguläre `session.commit()` des Aufrufers macht sie dauerhaft). Rückgabe
    False: ein IntegrityError wurde abgefangen — NUR dieser eine Savepoint wurde zurückgerollt,
    bereits vorher in DERSELBEN Session geflushte Geschwister-Zeilen (z. B. frühere Records
    desselben Ingest-Batches) bleiben unangetastet. Was „Dublette" für den Aufrufer bedeutet
    (Zähler hochzählen, 409, bestehende Zeile zurückgeben, …) entscheidet dieser selbst — diese
    Funktion trifft dazu keine Aussage.
    """
    try:
        with session.begin_nested():
            aendern()
            session.flush()
        return True
    except IntegrityError:
        return False


def init_db() -> None:
    """Create all tables if they don't exist, then apply additive column/index migrations.

    Fehlt hier absichtlich: die FTS5-Volltextsuche-Tabelle `suchindex` (Phase 25) — virtuell,
    nicht SQLModel-mapbar, gehört `pipeline/search_index.py` (eigene `_init()`, per `rebuild`
    komplett neu baubar statt migriert). Nicht „vermissen" — das ist Absicht.
    """
    from app import models  # noqa: F401  (register models on metadata)
    SQLModel.metadata.create_all(engine)
    _ensure_columns()
    _ensure_indexes()


def get_session():
    with Session(engine) as session:
        yield session
