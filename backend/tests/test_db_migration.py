"""Kontrakt-Tests fuer app/db.py::init_db/_ensure_columns/_ensure_indexes (Phase 57 Stufe E1.4,
erweitert Phase 67F um P2-2/P2-3).

Nutzt eine EIGENE, throwaway SQLite-Datei je Test (pytest-eigenes `tmp_path`) statt der
geteilten Session-tmp-DB aus conftest.py::_db_ready -- diese Tests manipulieren rohes Schema
(Tabellen droppen/neu anlegen), das wuerde die geteilte DB fuer andere Testdateien im selben
Lauf durcheinanderbringen. Isolation ueber `monkeypatch.setattr(db_modul, "engine", ...)`:
`init_db()`/`_ensure_columns()` lesen `engine` als Modul-Global ERST ZUR AUFRUFZEIT, der Tausch
wirkt deshalb ohne Re-Import. `app.db` wird -- wie ueberall in dieser Suite -- nur innerhalb von
Testfunktionen importiert, nie auf Modulebene.
"""
import sqlite3

import pytest


def _frischer_engine(tmp_path, monkeypatch):
    """Baut eine leere throwaway-SQLite-Datei + eigenen Engine und haengt ihn ANSTELLE von
    app.db.engine ein (nur fuer die Dauer des Tests -- monkeypatch macht das automatisch
    rueckgaengig)."""
    from sqlmodel import create_engine
    import app.db as db_modul

    db_path = tmp_path / "isoliert.sqlite"
    ersatz_engine = create_engine(f"sqlite:///{db_path}", echo=False,
                                  connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_modul, "engine", ersatz_engine)
    return db_modul, db_path


def test_init_db_erstellt_kerntabellen_auf_leerer_db(tmp_path, monkeypatch):
    db_modul, db_path = _frischer_engine(tmp_path, monkeypatch)
    assert not db_path.exists()

    db_modul.init_db()

    assert db_path.exists()
    conn = sqlite3.connect(str(db_path))
    try:
        tabellen = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    for kern in ("job", "company", "application", "cvversion", "agenttask", "transcript"):
        assert kern in tabellen, f"Kerntabelle '{kern}' fehlt nach init_db(): {sorted(tabellen)}"


def test_init_db_zweiter_lauf_ist_idempotent(tmp_path, monkeypatch):
    db_modul, db_path = _frischer_engine(tmp_path, monkeypatch)

    db_modul.init_db()
    conn = sqlite3.connect(str(db_path))
    schema_vorher = sorted(conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall())
    conn.close()

    db_modul.init_db()   # zweiter Lauf -- darf keine Exception werfen und nichts veraendern

    conn = sqlite3.connect(str(db_path))
    schema_nachher = sorted(conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall())
    conn.close()
    assert schema_vorher == schema_nachher


def test_ensure_columns_migriert_alt_schema_cvversion_status(tmp_path, monkeypatch):
    """Alt-Schema-Simulation: cvversion OHNE status-Spalte + 1 Bestandszeile -> _ensure_columns()
    -> Spalte existiert, Bestandszeile hat 'fertig' (SQL-DEFAULT-Verhalten aus Phase 46 B, NICHT
    nur ein Python-Field-Default -- SQLite befuellt bestehende Zeilen beim ALTER TABLE ... ADD
    COLUMN ... DEFAULT automatisch, s. app/db.py::_ADD_COLUMNS)."""
    db_modul, db_path = _frischer_engine(tmp_path, monkeypatch)

    db_modul.init_db()   # volles modernes Schema anlegen ...

    # ... dann cvversion durch ein Alt-Schema OHNE status ersetzen (minimal, wie vor Phase 46 B).
    conn = sqlite3.connect(str(db_path))
    conn.execute("DROP TABLE cvversion")
    conn.execute("CREATE TABLE cvversion (id INTEGER PRIMARY KEY, job_id INTEGER, language TEXT)")
    conn.execute("INSERT INTO cvversion (id, job_id, language) VALUES (1, 1, 'DE')")
    conn.commit()
    spalten_vorher = {r[1] for r in conn.execute("PRAGMA table_info(cvversion)")}
    conn.close()
    assert "status" not in spalten_vorher

    db_modul._ensure_columns()

    conn = sqlite3.connect(str(db_path))
    try:
        spalten_nachher = {r[1] for r in conn.execute("PRAGMA table_info(cvversion)")}
        assert "status" in spalten_nachher
        zeile = conn.execute("SELECT status FROM cvversion WHERE id = 1").fetchone()
    finally:
        conn.close()
    assert zeile == ("fertig",)


# ── P2-2 (Phase 67F): expliziter busy_timeout ──────────────────────────────────────────────────
def test_engine_hat_expliziten_busy_timeout_von_15_sekunden():
    """Ohne den Fix bringt der Python-sqlite3-Treiber zufaellig ~5s Retry mit (nicht bewusst
    gewaehlt); die `sqlite3`-CLI hat 0. CONNECT_ARGS macht die Grenze explizit und pruefbar,
    ohne in SQLAlchemy-/sqlite3-Interna graben zu muessen (`Connection.timeout` ist in Python
    nicht auslesbar -- schreib-only bei `sqlite3.connect()`)."""
    from app.db import CONNECT_ARGS

    assert CONNECT_ARGS["timeout"] == 15
    assert CONNECT_ARGS["check_same_thread"] is False   # bestehendes Verhalten bleibt unangetastet


# ── P2-3 (Phase 67F): UNIQUE-Indizes ────────────────────────────────────────────────────────────
_ALLE_INDEX_NAMEN = ("ux_job_dedup_key", "ux_company_name_nocase", "ux_outreach_dedup_key",
                     "ux_targetcompany_dedup_key", "ux_headhunter_dedup_key",
                     "ux_networkcontact_dedup_key")


def test_ensure_indexes_legt_alle_sechs_indizes_an(tmp_path, monkeypatch):
    db_modul, db_path = _frischer_engine(tmp_path, monkeypatch)
    db_modul.init_db()

    conn = sqlite3.connect(str(db_path))
    try:
        namen = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        conn.close()
    for erwartet in _ALLE_INDEX_NAMEN:
        assert erwartet in namen, f"Index '{erwartet}' fehlt nach init_db(): {sorted(namen)}"


def test_ensure_indexes_zweiter_lauf_ist_idempotent(tmp_path, monkeypatch):
    db_modul, db_path = _frischer_engine(tmp_path, monkeypatch)
    db_modul.init_db()

    db_modul._ensure_indexes()   # zweiter Lauf -- darf keine Exception werfen

    conn = sqlite3.connect(str(db_path))
    try:
        namen = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        conn.close()
    for erwartet in _ALLE_INDEX_NAMEN:
        assert erwartet in namen


def test_ensure_indexes_verhindert_dublette_auf_job_dedup_key(tmp_path, monkeypatch):
    from sqlmodel import Session
    from sqlalchemy.exc import IntegrityError
    from app.models import Job

    db_modul, db_path = _frischer_engine(tmp_path, monkeypatch)
    db_modul.init_db()
    with Session(db_modul.engine) as s:
        s.add(Job(title="Erster", dedup_key="dupkey|x", found_date="2026-01-01"))
        s.commit()
        s.add(Job(title="Zweiter", dedup_key="dupkey|x", found_date="2026-01-01"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_ensure_indexes_verhindert_dublette_auf_company_name_case_insensitive(tmp_path, monkeypatch):
    """Der Index normalisiert wie main.py::_norm_name (`.strip().lower()`) -- andere Schreibweise
    UND umgebende Leerzeichen muessen als dieselbe Firma erkannt werden."""
    from sqlmodel import Session
    from sqlalchemy.exc import IntegrityError
    from app.models import Company

    db_modul, db_path = _frischer_engine(tmp_path, monkeypatch)
    db_modul.init_db()
    with Session(db_modul.engine) as s:
        s.add(Company(name="SAP AG"))
        s.commit()
        s.add(Company(name="  sap ag  "))
        with pytest.raises(IntegrityError):
            s.commit()


@pytest.mark.parametrize("model_name", ["Outreach", "TargetCompany", "Headhunter", "NetworkContact"])
def test_ensure_indexes_verhindert_dublette_bei_outreach_familie(tmp_path, monkeypatch, model_name):
    """Die vier weiteren, vom Orchestrator noch zu pruefenden dedup_key-Felder (Q-Vorgabe Stufe
    67F) -- 0 Kollisionen im read-only-Bestandscheck, hier je Modell isoliert nachgewiesen."""
    from sqlmodel import Session
    from sqlalchemy.exc import IntegrityError
    import app.models as models_modul

    Model = getattr(models_modul, model_name)
    db_modul, db_path = _frischer_engine(tmp_path, monkeypatch)
    db_modul.init_db()
    with Session(db_modul.engine) as s:
        s.add(Model(dedup_key="dupkey|y"))
        s.commit()
        s.add(Model(dedup_key="dupkey|y"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_ensure_indexes_job_url_ist_seit_der_dubletten_entscheidung_unique(tmp_path, monkeypatch):
    """P2-3, Stand 26.07.2026 — GEGENTEIL des urspruenglichen Tests, bewusst umgedreht:

    In Phase 67F bekam `job.url` KEINEN UNIQUE-Index, weil der Bestand eine Kollision trug
    (zwei Stellen mit identischer URL aus einem frueheren Import). Das Zusammenfuehren
    war ausdruecklich eine fachliche Entscheidung, nicht die des Codes.
    Am 26.07.2026 wurde entschieden: die erste Stelle bleibt, die zweite ist die Dublette (jetzt Tombstone
    mit geleerter URL, Original-URL in dessen `source_note`). Damit ist der Bestand
    kollisionsfrei und der Index nachgezogen -- eine zweite Zeile mit derselben URL muss jetzt
    abgewiesen werden, statt still ein Duplikat anzulegen.

    NULL bleibt erlaubt (SQLite laesst beliebig viele NULLs in einem UNIQUE-Index zu) -- Jobs
    ohne URL sind ein Normalfall (Initiativbewerbungen u. ae.), der Index darf sie nicht blocken.
    """
    import pytest
    from sqlalchemy.exc import IntegrityError
    from sqlmodel import Session, select
    from app.models import Job

    db_modul, db_path = _frischer_engine(tmp_path, monkeypatch)
    db_modul.init_db()

    with Session(db_modul.engine) as s:
        s.add(Job(title="A", dedup_key="k1", url="https://example.com/job/1", found_date="2026-01-01"))
        s.commit()
        s.add(Job(title="B", dedup_key="k2", url="https://example.com/job/1", found_date="2026-01-01"))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()

    # Gegenprobe 1: genau EINE Zeile mit dieser URL ist durchgekommen.
    with Session(db_modul.engine) as s:
        treffer = s.exec(select(Job).where(Job.url == "https://example.com/job/1")).all()
    assert len(treffer) == 1, "der UNIQUE-Index auf job.url greift nicht"

    # Gegenprobe 2: mehrere Jobs OHNE URL bleiben erlaubt (sonst waere der Index schaedlich).
    with Session(db_modul.engine) as s:
        s.add(Job(title="C", dedup_key="k3", url=None, found_date="2026-01-01"))
        s.add(Job(title="D", dedup_key="k4", url=None, found_date="2026-01-01"))
        s.commit()   # darf NICHT werfen
        ohne_url = s.exec(select(Job).where(Job.url.is_(None))).all()
    assert len(ohne_url) == 2, "Jobs ohne URL duerfen sich nicht gegenseitig blocken"


def test_ensure_indexes_bei_bestandskollision_meldet_laut_und_erstellt_uebrige_indizes_trotzdem(
        tmp_path, monkeypatch, capsys):
    """P2-19-Lehre auf P2-3 uebertragen: eine Kollision im Bestand (Muster zwei Stellen mit gleicher URL, hier auf
    dedup_key simuliert, damit der Test nicht vom realen Altbestand abhaengt) darf NICHT die
    GESAMTE Index-Migration zum Schweigen bringen. _ensure_indexes() muss (a) nicht werfen,
    (b) den Fehlschlag laut melden, (c) die uebrigen fuenf Indizes trotzdem anlegen."""
    db_modul, db_path = _frischer_engine(tmp_path, monkeypatch)
    db_modul.init_db()   # Bestand ist hier noch leer -- alle sechs Indizes entstehen normal

    # Index wieder entfernen und zwei kollidierende Zeilen ROH einschleusen -- simuliert exakt
    # die reale Situation "Duplikat entstand VOR jeder Index-Existenz" (einmaliger Excel-Import).
    conn = sqlite3.connect(str(db_path))
    conn.execute("DROP INDEX ux_job_dedup_key")
    conn.execute("INSERT INTO job (title, dedup_key, found_date, created_at, updated_at) "
                 "VALUES ('A', 'kollision', '2026-01-01', '2026-01-01T00:00:00', '2026-01-01T00:00:00')")
    conn.execute("INSERT INTO job (title, dedup_key, found_date, created_at, updated_at) "
                 "VALUES ('B', 'kollision', '2026-01-01', '2026-01-01T00:00:00', '2026-01-01T00:00:00')")
    conn.commit()
    conn.close()

    capsys.readouterr()   # bisherige Ausgabe verwerfen
    db_modul._ensure_indexes()   # darf NICHT werfen
    ausgabe = capsys.readouterr().out
    assert "ux_job_dedup_key" in ausgabe and "WARNUNG" in ausgabe, (
        f"kein lauter Hinweis auf den Fehlschlag in der Ausgabe: {ausgabe!r}")

    conn = sqlite3.connect(str(db_path))
    try:
        namen = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        conn.close()
    assert "ux_job_dedup_key" not in namen, "Index haette wegen der Kollision NICHT entstehen duerfen"
    for erwartet in ("ux_company_name_nocase", "ux_outreach_dedup_key", "ux_targetcompany_dedup_key",
                     "ux_headhunter_dedup_key", "ux_networkcontact_dedup_key"):
        assert erwartet in namen, f"Index '{erwartet}' fehlt trotz unabhaengiger Kollision bei job.dedup_key"
