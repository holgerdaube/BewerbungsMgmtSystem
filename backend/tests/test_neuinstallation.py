"""Tests für Phase 100 — die zwei Stolpersteine einer FRISCHEN Installation
(s. tasks/todo.md, Phase 100; Anleitung: docs/INSTALLATION.md).

Beide Befunde stammen aus der Vorbereitung der Windows-Neuinstallation und waren real
reproduzierbar, nicht theoretisch:

  1. **Kein `data/` nach `git clone`.** Das Verzeichnis ist per .gitignore ausgeschlossen,
     und SQLite legt zwar die DB-DATEI, nicht aber ihr VERZEICHNIS an. Der allererste
     Serverstart einer frischen Installation endete deshalb mit
     `sqlite3.OperationalError: unable to open database file` — eine Meldung, die den
     fehlenden Ordner nicht nennt. `app/db.py` legt `DATA_DIR` jetzt beim Import an.

  2. **Claude-CLI im Beirat nur unter `~/.local/bin/claude`.** Diesen Pfad gibt es auf einer
     Windows-Installation nie (dort liegt die CLI nach `npm install -g` als `claude.cmd` im
     PATH), ein Env-Override fehlte — der Beirat meldete dauerhaft `cli_verfuegbar: False`.
     `beirat_engine._claude_bin_ermitteln()` prüft jetzt Env → PATH → alter Festpfad.

Der `data/`-Teil läuft bewusst in einem SUBPROZESS: `DATA_DIR` wird zur Importzeit aus der
Umgebung gebildet, und `app.db` ist im laufenden Testprozess längst importiert (an das
tmp-Verzeichnis aus conftest.py gebunden). Nur ein echter Neu-Import mit eigener Umgebung
beweist das Verhalten einer frischen Installation — `monkeypatch.setattr` auf die fertige
Konstante würde genau die Stelle überspringen, um die es geht. Gleiches Muster wie in
`test_log_pfade.py` für `BMS_LOG_DIR`.

Diese Tests sind absichtlich NICHT POSIX-abhängig (kein `chmod`, kein `killpg`, keine Shebang-
Ausführung): Sie müssen gerade unter Windows laufen, denn dort sind beide Fehler aufgetreten.

App-Importe ausschließlich innerhalb der Testfunktionen (Konvention aus conftest.py). Echte
Dateien werden nicht angefasst: alle Pfade sind `tmp_path`-Pfade, und der Key-Store des
Beirats (`~/.bewerbung_beirat/keys.json`) wird per `monkeypatch.setattr` umgebogen, bevor
`keys_status()` ihn liest.
"""
import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _im_subprozess(code: str, data_dir: Path):
    """Führt `code` in einem frischen Python mit eigenem BMS_DATA_DIR aus (cwd = backend/)."""
    umgebung = dict(os.environ, BMS_DATA_DIR=str(data_dir))
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(BACKEND_DIR), env=umgebung,
        capture_output=True, text=True, timeout=120,
    )


# ── 1. Frische Installation: `data/` fehlt ───────────────────────────────────────────

def test_data_verzeichnis_wird_beim_import_angelegt(tmp_path):
    """Der Import von `app.db` legt das Datenverzeichnis an — auch mehrstufig (parents=True)."""
    ziel = tmp_path / "frische_installation" / "data"
    assert not ziel.exists(), "Vorbedingung: Verzeichnis darf noch nicht existieren"

    lauf = _im_subprozess("import app.db as db; print(db.DATA_DIR)", ziel)

    assert lauf.returncode == 0, f"Import scheiterte:\n{lauf.stderr}"
    assert ziel.is_dir(), "DATA_DIR wurde beim Import nicht angelegt"


def test_erststart_legt_datenbank_an_statt_zu_scheitern(tmp_path):
    """Der eigentliche Regressionsfall: `init_db()` auf einer Installation ohne `data/`.

    Vor Phase 100 warf genau dieser Aufruf `unable to open database file`.
    """
    ziel = tmp_path / "frisch" / "data"
    lauf = _im_subprozess(
        "from app.db import init_db, DB_PATH; init_db(); print('DB_DA:', DB_PATH.exists())",
        ziel,
    )

    assert lauf.returncode == 0, f"init_db() scheiterte auf frischer Installation:\n{lauf.stderr}"
    assert "DB_DA: True" in lauf.stdout, lauf.stdout
    assert (ziel / "bewerbung.sqlite").is_file()


def test_vorhandenes_data_verzeichnis_bleibt_unangetastet(tmp_path):
    """exist_ok: ein bereits befülltes `data/` darf beim Import nicht angefasst werden."""
    ziel = tmp_path / "data"
    ziel.mkdir()
    (ziel / "schon_da.txt").write_text("unverändert")

    lauf = _im_subprozess("import app.db as db; print(db.DATA_DIR)", ziel)

    assert lauf.returncode == 0, lauf.stderr
    assert (ziel / "schon_da.txt").read_text() == "unverändert"


# ── 2. Frische Installation: `config/suchprofile.yaml` fehlt ─────────────────────────
#
# Alle Tests hier rufen `sicherstellen()` mit einem EXPLIZITEN tmp_path auf. Der Default-
# Parameter zeigt auf die echte `config/suchprofile.yaml` — die Funktion würde sie zwar nie
# überschreiben (sie legt nur an, was fehlt), aber der explizite Pfad macht das unmissverständlich.

def test_suchprofile_wird_angelegt_wenn_sie_fehlt(tmp_path):
    from pipeline import suchprofil

    ziel = tmp_path / "config" / "suchprofile.yaml"
    assert suchprofil.sicherstellen(ziel) is True
    assert ziel.is_file()


def test_vorhandene_suchprofile_wird_nie_ueberschrieben(tmp_path):
    from pipeline import suchprofil

    ziel = tmp_path / "suchprofile.yaml"
    ziel.write_text("mein: bestand\n", encoding="utf-8")

    assert suchprofil.sicherstellen(ziel) is False
    assert ziel.read_text(encoding="utf-8") == "mein: bestand\n"


def test_angelegte_datei_ist_fuer_die_einstellungen_lesbar(tmp_path):
    """`seed_aus_yaml()` ist der Pfad hinter `GET /api/einstellungen` — vorher: 500er."""
    from pipeline import suchprofil

    ziel = tmp_path / "suchprofile.yaml"
    suchprofil.sicherstellen(ziel)

    seed = suchprofil.seed_aus_yaml(ziel)
    assert [p["plan"] for p in seed["plaene"]] == ["A", "B", "C"]
    assert seed["portale"], "Portale dürfen nicht leer sein, sonst sucht die App nirgends"
    assert seed["min_mitarbeiter"] == 100


def test_angelegte_datei_traegt_den_marker_und_ist_speicherbar(tmp_path):
    """Ohne MARKER bräche jedes spätere Speichern in /einstellungen mit RuntimeError ab."""
    from pipeline import suchprofil

    ziel = tmp_path / "suchprofile.yaml"
    suchprofil.sicherstellen(ziel)
    assert suchprofil.MARKER in ziel.read_text(encoding="utf-8")

    managed = suchprofil.baue_managed(
        250,
        {"remote": {"aktiv": True}, "deutschlandweit": {"aktiv": False},
         "umkreis": {"aktiv": False, "stadt": "", "umkreis_km": 100}},
        [{"plan": "A", "label": "Plan A", "aktiv": True, "prioritaet": 1,
          "titel": ["Head of Delivery"], "senioritaet": ["Head"], "branche": ["SaaS"]},
         {"plan": "B", "label": "Plan B", "aktiv": False, "prioritaet": 2,
          "titel": [], "senioritaet": [], "branche": []},
         {"plan": "C", "label": "Plan C", "aktiv": False, "prioritaet": 3,
          "titel": [], "senioritaet": [], "branche": []}],
        list(suchprofil.PORTALE_DEFAULT),
    )
    suchprofil.schreibe_suchprofile(managed, ziel)          # darf nicht werfen

    danach = suchprofil.seed_aus_yaml(ziel)
    assert danach["min_mitarbeiter"] == 250, "Der Save muss im Kopf ankommen"
    assert suchprofil.MARKER in ziel.read_text(encoding="utf-8"), "Rumpf muss erhalten bleiben"


def test_angelegte_datei_erlaubt_den_job_ingest(tmp_path, monkeypatch):
    """`dedup_text.konfiguration()` läuft bei JEDEM Ingest — vorher: SystemExit, kein Job."""
    from pipeline import dedup_text, suchprofil

    ziel = tmp_path / "suchprofile.yaml"
    suchprofil.sicherstellen(ziel)
    monkeypatch.setattr(dedup_text, "CONFIG_FILE", ziel)

    cfg = dedup_text.konfiguration()                        # darf nicht mit SystemExit enden
    assert cfg["schwelle"] > 0 and cfg["min_text_zeichen"] > 0


def test_angelegte_datei_nennt_mail_alert_absender(tmp_path):
    """Ohne mindestens einen Absender beendet sich `mail-jobsuche` sofort."""
    import yaml
    from pipeline import suchprofil

    ziel = tmp_path / "suchprofile.yaml"
    suchprofil.sicherstellen(ziel)

    daten = yaml.safe_load(ziel.read_text(encoding="utf-8"))
    assert daten["mail_alerts"]["absender"], "mail_alerts.absender darf nicht leer sein"


def test_angelegte_plaene_haben_keine_erfundenen_titel(tmp_path):
    """Bewusste Entscheidung: lieber leer als eine Zielrolle, die niemand gewählt hat."""
    import yaml
    from pipeline import suchprofil

    ziel = tmp_path / "suchprofile.yaml"
    suchprofil.sicherstellen(ziel)

    daten = yaml.safe_load(ziel.read_text(encoding="utf-8"))
    assert all(p["titel"] == [] for p in daten["plaene"])


# ── 3. Claude-CLI-Auflösung im Beirat ────────────────────────────────────────────────

def test_claude_bin_env_override_gewinnt(monkeypatch):
    """`CLAUDE_BIN` schlägt alles — gleicher Env-Name wie in `agent_runner`."""
    import beirat_engine as be

    monkeypatch.setenv("CLAUDE_BIN", r"C:\Tools\claude.cmd")
    assert be._claude_bin_ermitteln() == r"C:\Tools\claude.cmd"


def test_claude_bin_aus_dem_pfad(monkeypatch):
    """Ohne Env-Override zählt der PATH — das ist der Windows-Normalfall (npm-Installation)."""
    import beirat_engine as be

    monkeypatch.delenv("CLAUDE_BIN", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "/opt/bin/claude" if name == "claude" else None)
    assert be._claude_bin_ermitteln() == "/opt/bin/claude"


def test_claude_bin_faellt_auf_alten_festpfad_zurueck(monkeypatch):
    """Ohne Env und ohne PATH-Treffer bleibt es beim bisherigen Verhalten (~/.local/bin/claude)."""
    import beirat_engine as be

    monkeypatch.delenv("CLAUDE_BIN", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)

    ermittelt = Path(be._claude_bin_ermitteln())
    assert ermittelt == Path.home() / ".local" / "bin" / "claude"


def test_cli_verfuegbar_erkennt_blossen_befehlsnamen(monkeypatch, tmp_path):
    """`cli_verfuegbar` darf nicht mehr an einem PATH-Namen scheitern.

    Vor Phase 100 prüfte die Statuszeile `Path(CLAUDE_BIN).exists()` — bei `CLAUDE_BIN=claude`
    (Befehlsname statt Pfad) ist das immer False, obwohl die CLI aufrufbar ist.
    """
    import beirat_engine as be

    monkeypatch.setattr(be, "KEY_PFAD", tmp_path / "keys.json")   # echten Key-Store nicht lesen
    monkeypatch.setattr(be, "CLAUDE_BIN", "claude")
    monkeypatch.setattr("shutil.which", lambda name: "/opt/bin/claude" if name == "claude" else None)

    assert be.keys_status()["cli_verfuegbar"] is True


def test_cli_verfuegbar_meldet_ehrlich_false(monkeypatch, tmp_path):
    """Gegenprobe: ohne auffindbare CLI bleibt die Anzeige rot."""
    import beirat_engine as be

    monkeypatch.setattr(be, "KEY_PFAD", tmp_path / "keys.json")
    monkeypatch.setattr(be, "CLAUDE_BIN", str(tmp_path / "gibt_es_nicht" / "claude"))
    monkeypatch.setattr("shutil.which", lambda name: None)

    assert be.keys_status()["cli_verfuegbar"] is False
