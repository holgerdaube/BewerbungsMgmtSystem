"""Tests fuer backend/app/selbsttest.py (P2-51, Update-Werkzeug Schritt 12).

`app.selbsttest` MUSS als eigener Subprozess mit eigener Umgebung laufen: `app.db` (und
`app.agent_runner`) binden ihre Datenpfade beim IMPORT an BMS_DATA_DIR/BMS_LOG_DIR/
BMS_SECRETS_DIR (s. deren Docstrings) -- ein einfacher In-Process-Aufruf wuerde an die
SESSION-WEITE tmp-DB aus conftest.py binden, nicht an eine isolierte Testdatenbank je Test.

Die Ausgangs-Datenbank fuer jeden Test wird deshalb VOR dem Subprozess-Aufruf mit einem
eigenen, throwaway-Engine gebaut (gleiches Muster wie tests/test_db_migration.py::
_frischer_engine) und erst DANACH liest der Subprozess sie ueber BMS_DATA_DIR. App-Importe
bleiben, wie ueberall in dieser Suite, funktionslokal (s. conftest.py-Docstring).
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _frische_db_datei(ziel_ordner: Path, monkeypatch) -> Path:
    """Baut das volle, aktuelle Schema (SQLModel.metadata + _ensure_columns/_ensure_indexes)
    in eine throwaway-SQLite-Datei unter `ziel_ordner` -- wie test_db_migration.py::
    _frischer_engine, hier gebraucht als Ausgangsstand fuer den Selbsttest-Subprozess."""
    from sqlmodel import create_engine
    import app.db as db_modul

    db_pfad = ziel_ordner / "bewerbung.sqlite"
    ersatz_engine = create_engine(f"sqlite:///{db_pfad}", echo=False,
                                  connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_modul, "engine", ersatz_engine)
    db_modul.init_db()
    return db_pfad


def _selbsttest_subprozess(data_dir: Path, log_dir: Path, secrets_dir: Path) -> subprocess.CompletedProcess:
    umgebung = dict(os.environ)
    umgebung["BMS_DATA_DIR"] = str(data_dir)
    umgebung["BMS_LOG_DIR"] = str(log_dir)
    umgebung["BMS_SECRETS_DIR"] = str(secrets_dir)
    return subprocess.run([sys.executable, "-m", "app.selbsttest"], cwd=str(BACKEND_DIR),
                           env=umgebung, capture_output=True, text=True, timeout=90)


def test_selbsttest_bestanden_bei_frischer_datenbank(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _frische_db_datei(data_dir, monkeypatch)
    log_dir, secrets_dir = tmp_path / "logs", tmp_path / "secrets"
    log_dir.mkdir()
    secrets_dir.mkdir()

    ergebnis = _selbsttest_subprozess(data_dir, log_dir, secrets_dir)

    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert "Selbsttest bestanden" in ergebnis.stdout


def test_selbsttest_meldet_fehlende_spalte_ausserhalb_add_columns(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_pfad = _frische_db_datei(data_dir, monkeypatch)

    # "industry" ist ein echtes Company-Modellfeld (app/models.py), aber NICHT Teil von
    # app.db._ADD_COLUMNS["company"] (dort steht nur "fit_ampel") -- _ensure_columns() kann sie
    # also nicht automatisch nachziehen. Tabelle ohne diese Spalte neu anlegen, wie von der
    # Bau-Spec verlangt ("Tabelle ohne diese Spalte neu anlegen").
    conn = sqlite3.connect(str(db_pfad))
    conn.execute("ALTER TABLE company RENAME TO company_alt")
    conn.execute(
        "CREATE TABLE company (id INTEGER PRIMARY KEY, name TEXT NOT NULL, created_at TEXT, updated_at TEXT)"
    )
    conn.execute("INSERT INTO company (id, name) SELECT id, name FROM company_alt")
    conn.execute("DROP TABLE company_alt")
    conn.commit()
    spalten = {row[1] for row in conn.execute("PRAGMA table_info(company)")}
    conn.close()
    assert "industry" not in spalten

    log_dir, secrets_dir = tmp_path / "logs", tmp_path / "secrets"
    log_dir.mkdir()
    secrets_dir.mkdir()

    ergebnis = _selbsttest_subprozess(data_dir, log_dir, secrets_dir)

    assert ergebnis.returncode == 1, ergebnis.stdout + ergebnis.stderr
    assert "company.industry" in ergebnis.stdout
