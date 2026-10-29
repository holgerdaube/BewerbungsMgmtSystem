"""Tests für automation/pfad_waechter.py (P2-38, Pfad-Wächter für Hintergrund-Läufe).

Das Skript liegt bewusst außerhalb von backend/ (kein App-/Pipeline-Modul — reine
Standardbibliothek, läuft als eigenständiger Hook-Prozess) — Import hier über `importlib`, gleiches
Muster wie `test_outbound_check.py` für `scripts/outbound_check.py`. Kein `app.*`/`pipeline.*`-Import
auf Modulebene (Konvention aus conftest.py) — hier ohnehin nicht nötig, das Skript importiert selbst
nichts aus `app`/`pipeline`.

Alle synthetischen Pfade liegen unter `tmp_path` und werden NIE tatsächlich angelegt (Ausnahme: das
Proben-Ziel im Home-Ordner in `test_hook_vertrag_...` wird nur GEPRÜFT, nie geschrieben — Vorgabe der
Spec, Abschnitt 3.3 Punkt 9). `temp_wurzeln=()` schaltet die Standard-Temp-Wurzeln in den meisten
Tests bewusst ab: `tmp_path` selbst liegt unter einem Temp-Ordner (macOS: `/private/var/folders/…`),
ohne diese Abschaltung wäre in den Tests jedes Ziel automatisch „erlaubt“.
"""
import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "automation" / "pfad_waechter.py"
_PROJEKTWURZEL_ECHT = _SCRIPT_PATH.parent.parent


def _load_module():
    spec = importlib.util.spec_from_file_location("pfad_waechter", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def pw():
    return _load_module()


# ── 1. Fall A ────────────────────────────────────────────────────────────────────
def test_fall_a_wird_gesperrt(pw, tmp_path):
    """Der real gefundene Fehlgriff: Projektwurzel und Ziel weichen genau um das fehlende
    `10_aktive_Projekte/`-Segment und ein `_` statt `/` voneinander ab."""
    projektwurzel = tmp_path / "CloudDocs" / "10_aktive_Projekte" / "40_Claude" / "Bewerbung_Mgmt_System"
    ziel = tmp_path / "CloudDocs" / "40_Claude" / "Bewerbung_Mgmt_System_inspect.py"
    eingabe = {"tool_name": "Write", "tool_input": {"file_path": str(ziel)}}

    sperrtext = pw.entscheiden(eingabe, projektwurzel, temp_wurzeln=())

    assert sperrtext is not None
    assert "Pfad-Wächter" in sperrtext
    assert str(Path(str(ziel)).resolve()) in sperrtext
    assert str(Path(str(projektwurzel)).resolve()) in sperrtext


# ── 2. Ziel im Projekt: absolut, relativ, unter data/tmp/ ───────────────────────────────────
def test_ziel_im_projekt_ist_in_allen_formen_erlaubt(pw, tmp_path):
    projektwurzel = tmp_path / "Bewerbung_Mgmt_System"

    ziel_absolut = projektwurzel / "backend" / "app" / "main.py"
    eingabe_absolut = {"tool_name": "Write", "tool_input": {"file_path": str(ziel_absolut)}}
    assert pw.entscheiden(eingabe_absolut, projektwurzel, temp_wurzeln=()) is None

    eingabe_relativ = {
        "tool_name": "Edit",
        "tool_input": {"file_path": "backend/app/main.py"},
        "cwd": str(projektwurzel),
    }
    assert pw.entscheiden(eingabe_relativ, projektwurzel, temp_wurzeln=()) is None

    ziel_data_tmp = projektwurzel / "data" / "tmp" / "hilfsdatei.json"
    eingabe_data_tmp = {"tool_name": "Write", "tool_input": {"file_path": str(ziel_data_tmp)}}
    assert pw.entscheiden(eingabe_data_tmp, projektwurzel, temp_wurzeln=()) is None


# ── 3. Nachbar-Präfix ────────────────────────────────────────────────────────────────────────
def test_nachbarordner_mit_praefix_gilt_nicht_als_im_projekt(pw, tmp_path):
    """`Bewerbung_Mgmt_System_alt/` hat den String `Bewerbung_Mgmt_System` als Präfix, ist aber ein
    eigener, gleichrangiger Ordner — genau der Fall, den `commonpath` von `startswith` unterscheidet."""
    projektwurzel = tmp_path / "Bewerbung_Mgmt_System"
    ziel = tmp_path / "Bewerbung_Mgmt_System_alt" / "x.py"
    eingabe = {"tool_name": "Write", "tool_input": {"file_path": str(ziel)}}

    assert pw.entscheiden(eingabe, projektwurzel, temp_wurzeln=()) is not None


# ── 4. Traversal ─────────────────────────────────────────────────────────────────────────────
def test_pfad_traversal_ueber_die_projektwurzel_hinaus_wird_gesperrt(pw, tmp_path):
    projektwurzel = tmp_path / "Bewerbung_Mgmt_System"
    ziel = f"{projektwurzel}/../ausserhalb.py"
    eingabe = {"tool_name": "Write", "tool_input": {"file_path": ziel}}

    assert pw.entscheiden(eingabe, projektwurzel, temp_wurzeln=()) is not None


# ── 5. Injizierte Temp-Wurzel ────────────────────────────────────────────────────────────────
def test_ziel_unter_injizierter_temp_wurzel_ist_erlaubt(pw, tmp_path):
    projektwurzel = tmp_path / "Bewerbung_Mgmt_System"
    fake_temp = tmp_path / "fake_temp"
    ziel = fake_temp / "hilfsdatei.py"
    eingabe = {"tool_name": "Write", "tool_input": {"file_path": str(ziel)}}

    assert pw.entscheiden(eingabe, projektwurzel, temp_wurzeln=(str(fake_temp),)) is None


# ── 6. NotebookEdit ───────────────────────────────────────────────────────────────────────────
def test_notebookedit_ausserhalb_wird_gesperrt(pw, tmp_path):
    projektwurzel = tmp_path / "Bewerbung_Mgmt_System"
    ziel = tmp_path / "irgendwo" / "analyse.ipynb"
    eingabe = {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": str(ziel)}}

    assert pw.entscheiden(eingabe, projektwurzel, temp_wurzeln=()) is not None


# ── 7. Andere Tools ──────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("tool_name", ["Read", "Bash", None])
def test_andere_tools_werden_nicht_geprueft(pw, tmp_path, tool_name):
    projektwurzel = tmp_path / "Bewerbung_Mgmt_System"
    ziel = tmp_path / "ausserhalb.py"
    eingabe = {"tool_name": tool_name, "tool_input": {"file_path": str(ziel)}}

    assert pw.entscheiden(eingabe, projektwurzel, temp_wurzeln=()) is None


# ── 8. main() ist fail-open ──────────────────────────────────────────────────────────────────
def test_main_ist_fail_open_bei_leerer_kaputter_oder_zielloser_eingabe(pw, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert pw.main() == 0

    monkeypatch.setattr(sys, "stdin", io.StringIO("{das ist kein gueltiges JSON"))
    assert pw.main() == 0

    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_name": "Write", "tool_input": {}})))
    assert pw.main() == 0

    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(["kein", "dict"])))
    assert pw.main() == 0


# ── 9. Echter Hook-Vertrag per Subprozess ────────────────────────────────────────────────────
def test_hook_vertrag_per_subprozess_blockt_ausserhalb_und_erlaubt_im_projekt():
    """Kein Mocking — echter Subprozess-Aufruf wie ihn Claude Code als PreToolUse-Hook macht:
    JSON auf stdin, Auswertung von Exit-Code und stderr. `sys.executable` ist hier dieselbe
    venv-Python-Installation, mit der die Testsuite laut Vorgabe gestartet wird."""
    ziel_ausserhalb = Path.home() / "__bms_pfadwaechter_probe__" / "x.py"  # wird NICHT angelegt
    eingabe_ausserhalb = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(ziel_ausserhalb)}})

    ergebnis = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH)],
        input=eingabe_ausserhalb, capture_output=True, text=True, timeout=10,
    )
    assert ergebnis.returncode == 2
    assert "Pfad-Wächter" in ergebnis.stderr
    assert not ziel_ausserhalb.exists()

    ziel_im_projekt = _PROJEKTWURZEL_ECHT / "automation" / "pfad_waechter.py"
    eingabe_im_projekt = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(ziel_im_projekt)}})

    ergebnis_ok = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH)],
        input=eingabe_im_projekt, capture_output=True, text=True, timeout=10,
    )
    assert ergebnis_ok.returncode == 0
    assert ergebnis_ok.stderr == ""


# ── 10. agent_settings.json: Hook eingetragen, permissions unangetastet ─────────────────────
def test_agent_settings_json_hat_hook_und_unveraenderte_permissions():
    settings_pfad = _PROJEKTWURZEL_ECHT / "automation" / "agent_settings.json"
    with open(settings_pfad, encoding="utf-8") as f:
        daten = json.load(f)

    pre_tool_use = daten.get("hooks", {}).get("PreToolUse", [])
    treffer = [h for h in pre_tool_use if h.get("matcher") == "Write|Edit|MultiEdit|NotebookEdit"]
    assert treffer, "PreToolUse-Hook mit dem erwarteten Matcher fehlt"

    befehl = treffer[0]["hooks"][0]["command"]
    assert "$CLAUDE_PROJECT_DIR/automation/pfad_waechter.py" in befehl
    assert _SCRIPT_PATH.exists()

    assert "Write" in daten["permissions"]["allow"]
    assert "Edit" in daten["permissions"]["allow"]
    assert "Bash(rm:*)" in daten["permissions"]["deny"]


# ── 11. Keine "/Users/"-Literale im Skript ───────────────────────────────────────────────────
def test_kein_absoluter_users_pfad_im_skriptquelltext():
    quelltext = _SCRIPT_PATH.read_text(encoding="utf-8")
    assert "/Users/" not in quelltext


# ── 12. P2-53: backend/data/ und nachwirkendes `cd backend` ──────────────────────────────────
def test_write_nach_backend_data_wird_mit_richtigem_ort_gesperrt(pw, tmp_path):
    projektwurzel = tmp_path / "Bewerbung_Mgmt_System"
    ziel = projektwurzel / "backend" / "data" / "tmp" / "skript.py"
    eingabe = {"tool_name": "Write", "tool_input": {"file_path": str(ziel)}}

    sperrtext = pw.entscheiden(eingabe, projektwurzel, temp_wurzeln=())

    assert sperrtext is not None
    assert "backend/data/" in sperrtext
    assert os.path.realpath(projektwurzel) + "/data/tmp/" in sperrtext


def test_write_nach_data_tmp_bleibt_erlaubt(pw, tmp_path):
    projektwurzel = tmp_path / "Bewerbung_Mgmt_System"
    ziel = projektwurzel / "data" / "tmp" / "skript.py"
    eingabe = {"tool_name": "Write", "tool_input": {"file_path": str(ziel)}}

    assert pw.entscheiden(eingabe, projektwurzel, temp_wurzeln=()) is None


@pytest.mark.parametrize("befehl", [
    "cat > data/tmp/entwurf.json << 'EOF'",
    "mkdir -p data/tmp",
    "~/.bewerbung_mgmt_venv/bin/python -c \"open('data/tmp/a.json')\"",
])
def test_bash_aus_backend_mit_relativem_data_tmp_wird_gesperrt(pw, tmp_path, befehl):
    """Der Fehlgriff aus dem Lauf vom 28.09.: Arbeitsordner noch `backend/`, Pfad relativ."""
    projektwurzel = tmp_path / "Bewerbung_Mgmt_System"
    (projektwurzel / "backend").mkdir(parents=True)
    eingabe = {"tool_name": "Bash", "tool_input": {"command": befehl},
               "cwd": str(projektwurzel / "backend")}

    sperrtext = pw.entscheiden(eingabe, projektwurzel, temp_wurzeln=())

    assert sperrtext is not None
    assert "../data/tmp/" in sperrtext


@pytest.mark.parametrize("im_backend, befehl", [
    (True, "~/.bewerbung_mgmt_venv/bin/python -m pipeline.ingest ../data/tmp/x.json"),
    (True, "cd .. && ~/.bewerbung_mgmt_venv/bin/python data/tmp/x.py"),
    (True, "cat {wurzel}/data/tmp/x.json"),
    (True, "ls data/tmpx"),
    (True, "echo ok"),
    (False, "cat > data/tmp/x.json"),
])
def test_bash_ohne_fehlgriff_bleibt_frei(pw, tmp_path, im_backend, befehl):
    projektwurzel = tmp_path / "Bewerbung_Mgmt_System"
    (projektwurzel / "backend").mkdir(parents=True)
    cwd = projektwurzel / "backend" if im_backend else projektwurzel
    eingabe = {"tool_name": "Bash", "tool_input": {"command": befehl.format(wurzel=projektwurzel)},
               "cwd": str(cwd)}

    assert pw.entscheiden(eingabe, projektwurzel, temp_wurzeln=()) is None


def test_bash_ohne_cwd_ist_fail_open(pw, tmp_path):
    eingabe = {"tool_name": "Bash", "tool_input": {"command": "cat > data/tmp/x.json"}}

    assert pw.entscheiden(eingabe, tmp_path / "Bewerbung_Mgmt_System", temp_wurzeln=()) is None


def test_agent_settings_json_hat_bash_hook_fuer_den_cd_fehlgriff():
    with open(_PROJEKTWURZEL_ECHT / "automation" / "agent_settings.json", encoding="utf-8") as f:
        daten = json.load(f)

    treffer = [h for h in daten["hooks"]["PreToolUse"] if h.get("matcher") == "Bash"]

    assert treffer, "PreToolUse-Hook mit Matcher 'Bash' fehlt"
    assert "$CLAUDE_PROJECT_DIR/automation/pfad_waechter.py" in treffer[0]["hooks"][0]["command"]
