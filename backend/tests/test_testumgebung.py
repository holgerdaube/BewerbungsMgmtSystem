"""P2-65: Die Testumgebung wartet nicht auf die Platte, die App schon.

Anlass (01.10.2026): Der Windows-CI-Job riss zweimal sein Zeitlimit von 15 Minuten. Gemessen im
Probelauf 36893114358: Auf dem Windows-Runner liegt `%TEMP%` auf C:, der Systemplatte (fsync 4 bis
10 ms je nach Runner, auf D: 0,5 ms). Dort liegen pytest-`tmp_path` und die Test-Datenbank, und
SQLite wartet bei jedem Commit und jeder CREATE-Anweisung auf die Platte. Das waren 70 bis 85 % der
Windows-Testzeit. Zwei Maßnahmen, je ein Wächter:

  1. `conftest.py::_sqlite_ohne_plattenbestaetigung` gibt jeder SQLAlchemy-Verbindung im
     Testprozess `PRAGMA synchronous=OFF`. Die App selbst bleibt bei der SQLite-Voreinstellung.
  2. `.github/workflows/ci.yml` legt im Windows-Testschritt TEMP/TMP auf `runner.temp` (D:).

Kein app.*-Import auf Modulebene (conftest.py-Konvention). Windows-tauglich: pathlib, Subprozess
ohne Shell.
"""
import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
CI_YML = BACKEND_DIR.parent / ".github" / "workflows" / "ci.yml"


def test_testverbindungen_warten_nicht_auf_die_platte(tmp_path, _db_ready):
    """Eine im Test neu gebaute Engine (Muster der Fixtures mit eigenem Schema) und die Engine der
    App auf der Test-Datenbank verbinden beide mit synchronous=OFF (0)."""
    from sqlalchemy import create_engine
    from app import db

    eigene = create_engine(f"sqlite:///{tmp_path / 'eigene.sqlite'}", connect_args=db.CONNECT_ARGS)
    try:
        with eigene.connect() as verbindung:
            assert verbindung.exec_driver_sql("PRAGMA synchronous").scalar() == 0
    finally:
        eigene.dispose()
    with db.engine.connect() as verbindung:
        assert verbindung.exec_driver_sql("PRAGMA synchronous").scalar() == 0


def test_app_ohne_conftest_bleibt_bei_der_sqlite_voreinstellung(tmp_path):
    """Die Lockerung gilt nur in Tests: In einem eigenen Prozess (ohne conftest.py, wie beim echten
    Start) verbindet die Engine der App mit derselben Stufe wie eine rohe sqlite3-Verbindung, und
    die ist nicht OFF."""
    skript = "\n".join([
        "import sqlite3, sys",
        "from app import db",
        "with db.engine.connect() as verbindung:",
        "    app_stufe = verbindung.exec_driver_sql('PRAGMA synchronous').scalar()",
        "roh = sqlite3.connect(sys.argv[1])",
        "voreinstellung = roh.execute('PRAGMA synchronous').fetchone()[0]",
        "roh.close()",
        "db.engine.dispose()",
        "print(app_stufe, voreinstellung)",
    ])
    umgebung = dict(os.environ, BMS_DATA_DIR=str(tmp_path / "daten"), BMS_LOG_DIR=str(tmp_path / "logs"))
    lauf = subprocess.run(
        [sys.executable, "-c", skript, str(tmp_path / "roh.sqlite")],
        cwd=str(BACKEND_DIR), env=umgebung, capture_output=True, text=True, timeout=120,
    )

    assert lauf.returncode == 0, f"Subprozess scheiterte:\n{lauf.stderr}"
    app_stufe, voreinstellung = lauf.stdout.split()
    assert app_stufe == voreinstellung, "die App darf die synchronous-Stufe nicht selbst setzen"
    assert app_stufe != "0"


def test_windows_testschritt_legt_temp_auf_runner_temp():
    """Ohne TEMP/TMP auf runner.temp liegen tmp_path und Test-Datenbank auf C:, und der Windows-Job
    braucht je nach Runner 5 bis 11 statt knapp 2 Minuten (Probelauf 36893114358)."""
    import yaml

    workflow = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    schritte = workflow["jobs"]["backend-windows"]["steps"]
    testschritte = [s for s in schritte if "pytest" in s.get("run", "")]

    assert len(testschritte) == 1, f"genau ein pytest-Schritt erwartet, gefunden: {len(testschritte)}"
    env = testschritte[0].get("env") or {}
    assert env.get("TEMP") == "${{ runner.temp }}"
    assert env.get("TMP") == "${{ runner.temp }}"
