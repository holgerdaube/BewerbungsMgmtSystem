"""Tests für Phase 63B (P1-3 aus dem Code-Review): Agent-Task-Logs liegen AUSSERHALB von
Projekt & iCloud (s. tasks/spec_phase63_datenschutz.md, Stufe 63B Schritt 5).

Fünf Pflicht-Fälle laut Spec, plus ein paar ergänzende Varianten für dieselben Mechanismen:
  1. `resolve_log_path()` findet die Datei am NEUEN Ort (LOG_DIR).
  2. `resolve_log_path()` findet einen Altbestands-Wert am früheren, projekt-relativen Ort
     (Fallback) — UND bevorzugt den neuen Ort, falls an beiden Orten eine Datei liegt.
  3. Eine fehlende Datei ergibt ein sauberes `None`/`[]`, nie einen Crash.
  4. `neue_log_datei()` (genutzt von `_run_task()` UND `beirat_engine._log_zeile()`) vergibt
     Verzeichnis-Rechte 700 und Datei-Rechte 600.
  5. `cleanup_logs()` löscht nur Logs älter als die Aufbewahrungsgrenze, lässt neuere UND noch
     laufende Tasks unangetastet.

Dazu (wie schon in `test_secrets_pfade.py` für Phase 63A): die Konstante `LOG_DIR` liegt
STRUKTURELL außerhalb des Projekt-Root, und der Override `BMS_LOG_DIR` wirkt wirklich (über
ein echtes Neu-Einlesen des Environments, nicht nur `monkeypatch.setattr` auf die fertige
Konstante).

App-Importe ausschließlich innerhalb der Testfunktionen (Konvention aus conftest.py — siehe
dessen Docstring). Alle Log-Dateien/-Verzeichnisse in diesen Tests sind `tmp_path`-Pfade, die
real nie existieren — die echten Logs unter `~/.bewerbung_mgmt_logs/` (und die alten unter
`data/agent_logs/`) werden von diesen Tests nicht angefasst (`monkeypatch.setattr` auf die
Modul-Konstanten, kein Zugriff auf die echten Pfade).
"""
import importlib
import os
import time
from contextlib import contextmanager

import pytest


# ── LOG_DIR liegt strukturell außerhalb des Projekt-Root (D6, mirror von test_secrets_pfade) ──
def test_log_dir_liegt_nicht_unter_projekt_root():
    import app.agent_runner as agent_runner

    assert not agent_runner.LOG_DIR.is_relative_to(agent_runner.PROJECT_ROOT), (
        f"agent_runner.LOG_DIR ({agent_runner.LOG_DIR}) liegt noch strukturell unter dem "
        f"Projekt-Root ({agent_runner.PROJECT_ROOT}) — Logs müssen außerhalb von Projekt & "
        "iCloud liegen (P1-3)."
    )


# ── BMS_LOG_DIR-Override wirkt wirklich (echtes Modul-Reload, s. test_secrets_pfade.py) ──────
@contextmanager
def _mit_bms_log_dir(ziel_dir):
    modul = importlib.import_module("app.agent_runner")
    alt = os.environ.get("BMS_LOG_DIR")
    os.environ["BMS_LOG_DIR"] = str(ziel_dir)
    try:
        importlib.reload(modul)
        yield modul
    finally:
        if alt is None:
            os.environ.pop("BMS_LOG_DIR", None)
        else:
            os.environ["BMS_LOG_DIR"] = alt
        importlib.reload(modul)


def test_bms_log_dir_override_wirkt(tmp_path):
    with _mit_bms_log_dir(tmp_path) as modul:
        assert modul.LOG_DIR == tmp_path


# ── Fall 1: Auflösung findet die Datei am NEUEN Ort ──────────────────────────────────────────
def test_resolve_log_path_findet_datei_am_neuen_ort(tmp_path, monkeypatch):
    import app.agent_runner as agent_runner

    neu_dir = tmp_path / "neu"
    neu_dir.mkdir()
    monkeypatch.setattr(agent_runner, "LOG_DIR", neu_dir)
    monkeypatch.setattr(agent_runner, "PROJECT_ROOT", tmp_path / "projekt_ohne_datei")

    (neu_dir / "task_999.jsonl").write_text('{"type": "system"}\n', encoding="utf-8")

    ergebnis = agent_runner.resolve_log_path("task_999.jsonl")
    assert ergebnis == neu_dir / "task_999.jsonl"


# ── Fall 2: Fallback auf den alten, projekt-relativen Ort ────────────────────────────────────
def test_resolve_log_path_fallback_auf_altem_projekt_relativen_ort(tmp_path, monkeypatch):
    import app.agent_runner as agent_runner

    neu_dir = tmp_path / "neu"          # existiert, aber LEER — Datei fehlt hier
    neu_dir.mkdir()
    alt_root = tmp_path / "projekt"
    alt_agent_logs = alt_root / "data" / "agent_logs"
    alt_agent_logs.mkdir(parents=True)
    monkeypatch.setattr(agent_runner, "LOG_DIR", neu_dir)
    monkeypatch.setattr(agent_runner, "PROJECT_ROOT", alt_root)

    (alt_agent_logs / "task_42.jsonl").write_text('{"type": "system"}\n', encoding="utf-8")

    # Altbestand (D3): der gespeicherte Wert ist der wörtliche, projekt-relative Pfad.
    ergebnis = agent_runner.resolve_log_path("data/agent_logs/task_42.jsonl")
    assert ergebnis == alt_agent_logs / "task_42.jsonl"


def test_resolve_log_path_bevorzugt_neuen_ort_wenn_beide_existieren(tmp_path, monkeypatch):
    """Migrations-Reihenfolge: liegt eine Datei (z. B. durch die Verschiebe-Migration) an
    BEIDEN Orten, gewinnt der neue — nie der alte Fallback-Pfad."""
    import app.agent_runner as agent_runner

    neu_dir = tmp_path / "neu"
    neu_dir.mkdir()
    alt_root = tmp_path / "projekt"
    alt_agent_logs = alt_root / "data" / "agent_logs"
    alt_agent_logs.mkdir(parents=True)
    monkeypatch.setattr(agent_runner, "LOG_DIR", neu_dir)
    monkeypatch.setattr(agent_runner, "PROJECT_ROOT", alt_root)

    (neu_dir / "task_7.jsonl").write_text("NEU\n", encoding="utf-8")
    (alt_agent_logs / "task_7.jsonl").write_text("ALT\n", encoding="utf-8")

    ergebnis = agent_runner.resolve_log_path("data/agent_logs/task_7.jsonl")
    assert ergebnis == neu_dir / "task_7.jsonl"
    assert ergebnis.read_text(encoding="utf-8") == "NEU\n"


# ── Fall 3: fehlende Datei → sauberes Ergebnis, kein Crash ───────────────────────────────────
def test_resolve_log_path_fehlende_oder_leere_werte_geben_none_ohne_crash(tmp_path, monkeypatch):
    import app.agent_runner as agent_runner

    monkeypatch.setattr(agent_runner, "LOG_DIR", tmp_path / "neu_leer")
    monkeypatch.setattr(agent_runner, "PROJECT_ROOT", tmp_path / "projekt_leer")

    assert agent_runner.resolve_log_path("task_777.jsonl") is None
    assert agent_runner.resolve_log_path("data/agent_logs/task_777.jsonl") is None
    assert agent_runner.resolve_log_path(None) is None
    assert agent_runner.resolve_log_path("") is None


def test_log_tail_liefert_leer_ohne_crash_wenn_datei_fehlt(tmp_path, monkeypatch):
    """log_tail() ist der eigentliche Leser hinter GET /api/tasks/{id}?tail=… — muss densel-
    ben sauberen Leerlauf zeigen wie resolve_log_path() selbst."""
    import app.agent_runner as agent_runner
    from app.models import AgentTask

    monkeypatch.setattr(agent_runner, "LOG_DIR", tmp_path / "leer")
    monkeypatch.setattr(agent_runner, "PROJECT_ROOT", tmp_path / "leeres_projekt")

    task = AgentTask(kind="firma-pruefen", log_path="task_nichtvorhanden.jsonl")
    assert agent_runner.log_tail(task) == []

    task_ohne_log = AgentTask(kind="firma-pruefen", log_path=None)
    assert agent_runner.log_tail(task_ohne_log) == []


def test_log_tail_liest_ueber_resolve_log_path_vom_neuen_ort(tmp_path, monkeypatch):
    import app.agent_runner as agent_runner
    from app.models import AgentTask

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(agent_runner, "LOG_DIR", log_dir)
    (log_dir / "task_55.jsonl").write_text("zeile1\nzeile2\n", encoding="utf-8")

    task = AgentTask(kind="firma-pruefen", log_path="task_55.jsonl")
    assert agent_runner.log_tail(task) == ["zeile1", "zeile2"]


# ── Fall 4: neu angelegtes Log hat Modus 600 (Verzeichnis 700) ───────────────────────────────
@pytest.mark.skipif(os.name == "nt", reason="POSIX-Rechte: NTFS bildet chmod 600/700 nicht ab (s. docs/SETUP-WINDOWS.md)")
def test_neue_log_datei_hat_modus_600(tmp_path, monkeypatch):
    import app.agent_runner as agent_runner

    monkeypatch.setattr(agent_runner, "LOG_DIR", tmp_path / "logs")

    log_filename, log_path = agent_runner.neue_log_datei(4242)

    assert log_filename == "task_4242.jsonl"
    assert log_path == tmp_path / "logs" / "task_4242.jsonl"
    assert log_path.is_file()
    datei_modus = log_path.stat().st_mode & 0o777
    assert datei_modus == 0o600, f"erwarte Datei-Modus 600, war {oct(datei_modus)}"
    verzeichnis_modus = (tmp_path / "logs").stat().st_mode & 0o777
    assert verzeichnis_modus == 0o700, f"erwarte Verzeichnis-Modus 700, war {oct(verzeichnis_modus)}"


@pytest.mark.skipif(os.name == "nt", reason="POSIX-Rechte: NTFS bildet chmod 600/700 nicht ab (s. docs/SETUP-WINDOWS.md)")
def test_neue_log_datei_setzt_rechte_auch_bei_bereits_vorhandener_datei(tmp_path, monkeypatch):
    """beirat_engine._log_zeile() ruft neue_log_datei() bei JEDEM Append erneut auf (Datei
    existiert dann schon) — muss trotzdem 600 halten, selbst wenn sie zwischenzeitlich zu
    offen war (z. B. durch ein Backup-Tool)."""
    import app.agent_runner as agent_runner

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(agent_runner, "LOG_DIR", log_dir)

    bestehende = log_dir / "task_10.jsonl"
    bestehende.write_text("erste zeile\n", encoding="utf-8")
    os.chmod(bestehende, 0o644)                       # absichtlich zu offen

    log_filename, log_path = agent_runner.neue_log_datei(10)

    assert log_filename == "task_10.jsonl"
    assert log_path.read_text(encoding="utf-8") == "erste zeile\n"   # Inhalt bleibt erhalten
    assert (log_path.stat().st_mode & 0o777) == 0o600


# ── Fall 5: Rotation löscht nur Altes, lässt Neues (und Laufendes) stehen ────────────────────
def test_cleanup_logs_loescht_nur_aelteres_als_die_grenze_laesst_neues_stehen(
    tmp_path, monkeypatch, session
):
    import app.agent_runner as agent_runner
    from app.models import AgentTask

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(agent_runner, "LOG_DIR", log_dir)
    monkeypatch.setattr(agent_runner, "LOG_RETENTION_DAYS", 30)

    alt_task = AgentTask(kind="firma-pruefen", status="done")
    neu_task = AgentTask(kind="firma-pruefen", status="done")
    session.add(alt_task)
    session.add(neu_task)
    session.commit()
    session.refresh(alt_task)
    session.refresh(neu_task)

    alt_datei = log_dir / f"task_{alt_task.id}.jsonl"
    neu_datei = log_dir / f"task_{neu_task.id}.jsonl"
    alt_datei.write_text("alt\n", encoding="utf-8")
    neu_datei.write_text("neu\n", encoding="utf-8")
    alt_task.log_path = f"task_{alt_task.id}.jsonl"
    neu_task.log_path = f"task_{neu_task.id}.jsonl"
    session.add(alt_task)
    session.add(neu_task)
    session.commit()

    alte_zeit = time.time() - 40 * 86400        # 40 Tage > 30-Tage-Grenze
    os.utime(alt_datei, (alte_zeit, alte_zeit))
    # neu_datei behält die aktuelle mtime (gerade erst geschrieben)

    geloescht = agent_runner.cleanup_logs()

    assert geloescht == 1
    assert not alt_datei.exists()
    assert neu_datei.exists()

    session.refresh(alt_task)
    session.refresh(neu_task)
    assert alt_task.log_path is None            # genullt, s. cleanup_logs()-Docstring
    assert neu_task.log_path == f"task_{neu_task.id}.jsonl"


def test_cleanup_logs_laesst_noch_laufende_tasks_unangetastet(tmp_path, monkeypatch, session):
    import app.agent_runner as agent_runner
    from app.models import AgentTask

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(agent_runner, "LOG_DIR", log_dir)
    monkeypatch.setattr(agent_runner, "LOG_RETENTION_DAYS", 30)

    laufender_task = AgentTask(kind="firma-pruefen", status="running")
    session.add(laufender_task)
    session.commit()
    session.refresh(laufender_task)

    datei = log_dir / f"task_{laufender_task.id}.jsonl"
    datei.write_text("laeuft noch\n", encoding="utf-8")
    laufender_task.log_path = f"task_{laufender_task.id}.jsonl"
    session.add(laufender_task)
    session.commit()

    alte_zeit = time.time() - 40 * 86400
    os.utime(datei, (alte_zeit, alte_zeit))     # Datei selbst ist alt, Task aber noch aktiv

    geloescht = agent_runner.cleanup_logs()

    assert geloescht == 0
    assert datei.exists()
    session.refresh(laufender_task)
    assert laufender_task.log_path == f"task_{laufender_task.id}.jsonl"   # nicht genullt


def test_cleanup_logs_ignoriert_fremde_dateien_im_log_dir(tmp_path, monkeypatch):
    """Eine Datei, deren Name nicht zu `task_<id>.jsonl` passt (z. B. ein fremdes Artefakt),
    wird NIE angefasst — auch nicht, wenn sie uralt ist (s. Kommentar „fremde Datei — nicht
    anfassen" in cleanup_logs())."""
    import app.agent_runner as agent_runner

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(agent_runner, "LOG_DIR", log_dir)
    monkeypatch.setattr(agent_runner, "LOG_RETENTION_DAYS", 30)

    fremd = log_dir / "task_ohnenummer.jsonl"
    fremd.write_text("kein gueltiger task-name\n", encoding="utf-8")
    alte_zeit = time.time() - 100 * 86400
    os.utime(fremd, (alte_zeit, alte_zeit))

    geloescht = agent_runner.cleanup_logs()

    assert geloescht == 0
    assert fremd.exists()


# ── Rotation im Betrieb: Zeitsperre („höchstens 1x/Stunde") ──────────────────────────────────
def test_cleanup_logs_gedrosselt_laeuft_nicht_zweimal_innerhalb_der_stunde(tmp_path, monkeypatch):
    import app.agent_runner as agent_runner

    aufrufe = []
    monkeypatch.setattr(agent_runner, "cleanup_logs", lambda: aufrufe.append(1) or 0)
    monkeypatch.setattr(agent_runner, "_LETZTE_ROTATION", time.time())  # "gerade erst gelaufen"

    agent_runner._cleanup_logs_gedrosselt()
    assert aufrufe == [], "sollte innerhalb der Stunde NICHT erneut laufen"


def test_cleanup_logs_gedrosselt_laeuft_nach_ablauf_der_stunde(tmp_path, monkeypatch):
    import app.agent_runner as agent_runner

    aufrufe = []
    monkeypatch.setattr(agent_runner, "cleanup_logs", lambda: aufrufe.append(1) or 0)
    monkeypatch.setattr(agent_runner, "_LETZTE_ROTATION",
                         time.time() - agent_runner._ROTATION_INTERVALL_S - 1)

    agent_runner._cleanup_logs_gedrosselt()
    assert aufrufe == [1], "sollte nach Ablauf der Zeitsperre wieder laufen"
