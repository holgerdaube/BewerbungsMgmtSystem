"""Tests für Phase 65 (P1-6 aus tasks/code_review_2026-07-25.md, s.
tasks/spec_phase65_prozess_tracking.md) — verwaiste Skill-Prozesse überleben einen
Server-Neustart nicht mehr unbemerkt.

Kernstück ist der FREMDPROZESS-SCHUTZ (P1, die härteste Regel dieser Phase, wörtlich aus der
Spec): eine gespeicherte PID ist KEIN dauerhafter Ausweis — nach einem Neustart kann dieselbe
Nummer längst einem fremden Programm auf dem Rechner gehören. Ein `kill` ohne Prüfung wäre ein
Fremdprozess-Killer, schlimmer als der Befund, den diese Phase behebt. Getestet werden die vier
Fälle aus `agent_runner._running_wiederherstellen()` EINZELN, dazu Migration und Shutdown-Hook.

B1/P2 (kein echter Skill-Lauf, kostet Geld): wo ein "lebender Prozess" gebraucht wird, ist es ein
echter, aber harmloser Wegwerf-Prozess (`sleep`) — nie ein echter `claude`-Aufruf. Der Fall
"bestätigte Identität" nutzt `sleep` PLUS einen Monkeypatch auf `CLAUDE_BIN` ("sleep" statt
"claude"), damit der ECHTE (nicht gemockte) Identitäts-Check aus `_ist_unser_prozess()` läuft,
inklusive echtem `os.killpg` am Ende — ohne echte Kosten zu verursachen.

Isolation: eigene throwaway-SQLite-Datei je Test (Muster aus test_db_migration.py/
test_fehlerpfade.py::_frischer_engine) statt der geteilten conftest.py-DB — die Recovery-Tests
wollen GENAU die eine 'running'-Zeile sehen, die sie selbst anlegen, nicht auch noch Altlasten
aus anderen Testdateien (test_log_pfade.py::test_cleanup_logs_laesst_noch_laufende_tasks_
unangetastet lässt bewusst eine 'running'-Zeile ohne PID in der GETEILTEN Session-DB stehen).
Testdateien importieren laut Konvention nicht voneinander, deshalb hier eine lokale Kopie von
`_frischer_engine` (hier: erledigt zusätzlich gleich das `init_db()`, das bei allen sieben Tests
unten ohnehin gebraucht wird — kleine, bewusste Abweichung vom Vorbild, um die Wiederholung zu
sparen). `app.*`/`sqlmodel`-Importe bleiben wie überall in dieser Suite funktionslokal.
"""
import contextlib
import datetime
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX-only: echte sleep-Prozessgruppen + ps/killpg (Windows-Grenze, s. docs/SETUP-WINDOWS.md)",
)
import signal
import subprocess
import types


def _frischer_engine(tmp_path, monkeypatch):
    """Baut eine leere throwaway-SQLite-Datei + eigenen Engine, hängt ihn anstelle von
    app.db.engine ein und initialisiert das volle (moderne) Schema darauf — inkl. der neuen
    `pid`-Spalte (additive Migration, s. app/db.py::_ADD_COLUMNS)."""
    from sqlmodel import create_engine
    import app.db as db_modul

    db_path = tmp_path / "isoliert_p65.sqlite"
    ersatz_engine = create_engine(f"sqlite:///{db_path}", echo=False,
                                  connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_modul, "engine", ersatz_engine)
    db_modul.init_db()
    return ersatz_engine, db_path


def _aufraeumen(proc: subprocess.Popen) -> None:
    """Wegwerf-Prozess am Testende garantiert beenden — egal ob _kill() ihn im Test bereits
    erwischt hat oder nicht (P2-Vorgabe der Spec: 'Prozess am Ende sauber aufräumen')."""
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════════════════════════════════
# Migration
# ═══════════════════════════════════════════════════════════════════════════════════════════

def test_migration_pid_spalte_existiert_nach_init_db(tmp_path, monkeypatch):
    """Spec Schritt 5, erster Punkt: Spalte `pid` existiert nach init_db() — additive Migration
    über das bestehende _ADD_COLUMNS-Muster, kein Handumbruch am Schema."""
    import sqlite3

    _engine, db_path = _frischer_engine(tmp_path, monkeypatch)

    conn = sqlite3.connect(str(db_path))
    try:
        spalten = {r[1] for r in conn.execute("PRAGMA table_info(agenttask)")}
    finally:
        conn.close()
    assert "pid" in spalten


# ═══════════════════════════════════════════════════════════════════════════════════════════
# Fall 1 — keine PID hinterlegt (Altbestand / beirat_engine)
# ═══════════════════════════════════════════════════════════════════════════════════════════

def test_keine_pid_hinterlegt_altes_verhalten_mit_meldung(tmp_path, monkeypatch, capsys):
    """Fall 1: keine PID hinterlegt (Altbestand vor Phase 65, oder ein Schreiber wie
    beirat_engine, der bewusst nie eine PID setzt) — unverändertes Verhalten: die Zeile landet
    auf 'failed', mit einer Meldung, die klarstellt, dass NICHT geprüft werden konnte."""
    from sqlmodel import Session
    from app.models import AgentTask
    import app.agent_runner as ar

    engine, _ = _frischer_engine(tmp_path, monkeypatch)
    with Session(engine) as s:
        t = AgentTask(kind="firma-pruefen", status="running", prompt="Testprompt (pytest)",
                     started_at=datetime.datetime.utcnow(), pid=None)
        s.add(t)
        s.commit()
        s.refresh(t)
        task_id = t.id

    with Session(engine) as s:
        ar._running_wiederherstellen(s)

    with Session(engine) as s:
        t = s.get(AgentTask, task_id)
        assert t.status == "failed"
        assert t.pid is None

    out = capsys.readouterr().out
    assert f"Task {task_id}" in out
    assert "ohne hinterlegte PID" in out
    assert "konnte nicht geprüft werden" in out


# ═══════════════════════════════════════════════════════════════════════════════════════════
# Fall 2 — PID nicht mehr am Leben (Normalfall, ruhig)
# ═══════════════════════════════════════════════════════════════════════════════════════════

def test_tote_pid_wird_failed_ohne_kill_versuch(tmp_path, monkeypatch, capsys):
    """Fall 2: PID nicht mehr am Leben (`os.kill(pid, 0)` wirft) — ruhiger Normalfall: failed,
    KEINE Alarmierung nötig (der Prozess ist bereits weg, es gibt nichts zu beenden)."""
    from sqlmodel import Session
    from app.models import AgentTask
    import app.agent_runner as ar

    # Echter, aber garantiert bereits toter PID: kurz spawnen, sofort abwarten+reapen — die Zahl
    # gehört danach keinem laufenden Prozess mehr.
    proc = subprocess.Popen(["sleep", "0"])
    proc.wait(timeout=60)  # P2-19: Notbremse gegen Haengen, keine Laufzeitzusage
    tote_pid = proc.pid

    engine, _ = _frischer_engine(tmp_path, monkeypatch)
    with Session(engine) as s:
        t = AgentTask(kind="firma-pruefen", status="running", prompt="Testprompt (pytest)",
                     started_at=datetime.datetime.utcnow(), pid=tote_pid)
        s.add(t)
        s.commit()
        s.refresh(t)
        task_id = t.id

    with Session(engine) as s:
        ar._running_wiederherstellen(s)

    with Session(engine) as s:
        t = s.get(AgentTask, task_id)
        assert t.status == "failed"
        assert t.pid is None

    out = capsys.readouterr().out
    assert f"Task {task_id}" in out
    assert str(tote_pid) in out
    assert "bereits" in out and "beendet" in out
    assert "WARNUNG" not in out          # ruhiger Normalfall — keine Alarmierung nötig


# ═══════════════════════════════════════════════════════════════════════════════════════════
# Fall 3 — DER zentrale Test: Fremdprozess-Schutz (P1)
# ═══════════════════════════════════════════════════════════════════════════════════════════

def test_fremdprozess_schutz_lebender_prozess_wird_nicht_beendet(tmp_path, monkeypatch, capsys):
    """DER zentrale Test dieser Phase (P1): ein echter, harmloser Wegwerf-Prozess (`sleep`) läuft
    noch, seine PID steht in einer 'running'-Zeile — die Recovery MUSS ihn NICHT beenden, obwohl
    "PID passt zu einer Zeile" auf den ersten Blick verlockend aussieht. `sleep`s Kommandozeile
    enthält nirgends "claude" — der ECHTE (nicht gemockte) Identitäts-Check schlägt also
    berechtigterweise fehl. Eigene Prozessgruppe (start_new_session=True) wie im echten
    agent_runner-Spawn, damit auch ein eventueller (hier NICHT gewollter) Kill realistisch wäre.

    Beweis: (1) der Prozess LEBT danach noch, (2) die Zeile ist 'failed', (3) eine LAUTE Meldung
    mit PID + Kommandozeile ist erschienen. Prozess wird am Ende in jedem Fall aufgeräumt."""
    from sqlmodel import Session
    from app.models import AgentTask
    import app.agent_runner as ar

    monkeypatch.setattr(ar, "CLAUDE_BIN", "claude")   # deterministisch, unabhängig von der Umgebung
    proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
    try:
        engine, _ = _frischer_engine(tmp_path, monkeypatch)
        with Session(engine) as s:
            t = AgentTask(kind="firma-pruefen", status="running", prompt="Testprompt (pytest)",
                         started_at=datetime.datetime.utcnow(), pid=proc.pid)
            s.add(t)
            s.commit()
            s.refresh(t)
            task_id = t.id

        with Session(engine) as s:
            ar._running_wiederherstellen(s)

        # Kernbeweis 1: der Prozess LEBT noch (weder poll() noch os.kill(pid, 0) zeigen ein Ende).
        assert proc.poll() is None
        os.kill(proc.pid, 0)          # wirft NICHT, wenn er noch lebt — sonst platzt der Test

        with Session(engine) as s:
            t = s.get(AgentTask, task_id)
            assert t.status == "failed"
            assert t.pid is None

        out = capsys.readouterr().out
        assert f"Task {task_id}" in out
        assert str(proc.pid) in out
        assert "WARNUNG" in out
        assert "NICHT beendet" in out
    finally:
        _aufraeumen(proc)


# ═══════════════════════════════════════════════════════════════════════════════════════════
# Fall 4 — bestätigte Identität: Waise wird beendet
# ═══════════════════════════════════════════════════════════════════════════════════════════

def test_bestaetigte_identitaet_waise_wird_beendet(tmp_path, monkeypatch, capsys):
    """Fall 4: Kommandozeile UND Startzeitpunkt bestätigen den Prozess als unseren — die
    Recovery beendet ihn WIRKLICH, über den echten (nicht gemockten) `_kill()`/os.killpg-Pfad.
    `CLAUDE_BIN` wird auf "sleep" umgebogen (P2: kein echter `claude`-Prozess) — damit läuft der
    ECHTE Identitäts-Check aus `_ist_unser_prozess()` (Kommandozeilen- UND Zeitvergleich), nicht
    nur eine gemockte Kurzschluss-Antwort."""
    from sqlmodel import Session
    from app.models import AgentTask
    import app.agent_runner as ar

    monkeypatch.setattr(ar, "CLAUDE_BIN", "sleep")
    # started_at bewusst VOR dem tatsächlichen Prozessstart erfasst — exakt wie im echten Ablauf:
    # _run_task() committet started_at, BEVOR der Subprozess gespawnt wird (s. dortiger Kommentar).
    vor_dem_start = datetime.datetime.utcnow()
    proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
    try:
        engine, _ = _frischer_engine(tmp_path, monkeypatch)
        with Session(engine) as s:
            t = AgentTask(kind="firma-pruefen", status="running", prompt="Testprompt (pytest)",
                         started_at=vor_dem_start, pid=proc.pid)
            s.add(t)
            s.commit()
            s.refresh(t)
            task_id = t.id

        with Session(engine) as s:
            ar._running_wiederherstellen(s)

        # Kernbeweis: der Prozess wurde WIRKLICH beendet — per echtem SIGKILL über os.killpg,
        # nicht nur behauptet. rc == -SIGKILL beweist die Signal-Ursache präzise (kein normaler
        # Exit, kein anderes Signal).
        rc = proc.wait(timeout=60)  # P2-19: Notbremse gegen Haengen, keine Laufzeitzusage
        assert rc == -signal.SIGKILL

        with Session(engine) as s:
            t = s.get(AgentTask, task_id)
            assert t.status == "failed"
            assert t.pid is None

        out = capsys.readouterr().out
        assert f"Task {task_id}" in out
        assert str(proc.pid) in out
        assert "gefunden und beendet" in out
    finally:
        _aufraeumen(proc)


# ═══════════════════════════════════════════════════════════════════════════════════════════
# Shutdown-Hook
# ═══════════════════════════════════════════════════════════════════════════════════════════

def test_shutdown_kill_all_beendet_alle_verzeichneten_prozesse_und_meldet(monkeypatch, capsys):
    """Shutdown-Hook (main.py::_shutdown → agent_runner.shutdown_kill_all()): jeder in `_procs`
    verzeichnete Prozess wird über `_kill()` beendet UND laut gemeldet. `_kill` selbst wird
    gemonkeypatcht (P2 — kein echter Subprozess nötig, `shutdown_kill_all()` braucht von `proc`
    nur das `.pid`-Attribut, ein `SimpleNamespace` genügt als Stand-in)."""
    import app.agent_runner as ar

    beendete_pids = []
    monkeypatch.setattr(ar, "_kill", lambda pid: beendete_pids.append(pid))
    erste, zweite = 7, 8
    fake_procs = {erste: types.SimpleNamespace(pid=5001), zweite: types.SimpleNamespace(pid=5002)}
    monkeypatch.setattr(ar, "_procs", fake_procs)

    ar.shutdown_kill_all()

    assert sorted(beendete_pids) == [5001, 5002]
    out = capsys.readouterr().out
    assert f"Task {erste}" in out and "5001" in out
    assert f"Task {zweite}" in out and "5002" in out


def test_shutdown_kill_all_ohne_laufende_prozesse_tut_nichts(monkeypatch, capsys):
    """P4-Geschwister für den Shutdown-Pfad (die Spec verlangt P4 explizit nur für den
    Start-Fall, aber dieselbe Ruhe gilt sinngemäß auch hier): ist nichts (mehr) in `_procs`
    verzeichnet, passiert nichts und es erscheint keine Meldung."""
    import app.agent_runner as ar

    aufrufe = []
    monkeypatch.setattr(ar, "_kill", lambda pid: aufrufe.append(pid))
    monkeypatch.setattr(ar, "_procs", {})

    ar.shutdown_kill_all()

    assert aufrufe == []
    assert capsys.readouterr().out == ""
