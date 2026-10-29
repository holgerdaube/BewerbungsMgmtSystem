"""Tests für Phase 64B (P2-1, P2-19, P2-20 aus tasks/code_review_2026-07-25.md, s.
tasks/spec_phase64_fehlerpfade.md Stufe 64B) — drei stille Fehlschläge im FEHLERPFAD selbst
werden hörbar gemacht. Leitsatz der Phase: ein Fehler darf laut sein, er darf abbrechen — aber er
darf nicht unsichtbar sein und nichts dauerhaft lähmen. Genau diese Fehlerpfade waren bisher
ungetestet (F5) — hier werden sie es.

  1. `agent_runner._worker()` — die `while True`-Schleife überlebt eine Exception, die aus
     `_run_task()` entkommt (P2-1). Zusätzlich: `_update()` selbst schluckt einen gescheiterten
     DB-Commit und meldet ihn laut, statt ihn weiterzuwerfen (die zweite Verteidigungslinie
     desselben Befunds).
  2. `db._ensure_columns()` — ein fehlgeschlagener `PRAGMA table_info`-Aufruf meldet den
     Tabellennamen (P2-19), UND der abgesicherte `ALTER TABLE`-Zweig unterscheidet "duplicate
     column" (harmlos, leise) von echten Fehlern (laut).
  3. `beirat_engine.Debatte.laufen()` — scheitert `_task_abschliessen()` im `finally`-Block, wird
     das laut gemeldet, UND das SSE-Ende-Signal (`queue.put(None)`) läuft trotzdem (P2-20).

B1/F2 (kein echter Beirats-/Skill-Lauf, kostet Geld): jede externe Aktion ist gefaked/gemonkey-
patcht — kein Subprozess, kein API-Call. Wie in conftest.py beschrieben: KEINE app.*/
pipeline.*-Importe auf Modulebene, nur in Testfunktionen. Helper-Funktionen (`_frischer_engine`,
`_neue_test_debatte`) sind bewusste lokale Kopien der Muster aus test_db_migration.py bzw.
test_beirat_fehler.py — Testdateien importieren laut Konvention nicht voneinander.
"""
import asyncio
import contextlib
import sqlite3


# ═══════════════════════════════════════════════════════════════════════════════════════════
# P2-1 — agent_runner._worker() überlebt, _update() schluckt einen gescheiterten Commit
# ═══════════════════════════════════════════════════════════════════════════════════════════

def test_worker_ueberlebt_exception_aus_run_task_und_verarbeitet_naechsten_task(monkeypatch, _db_ready):
    """Kernbeweis von P2-1: `_run_task()` wirft beim ERSTEN Task (Monkeypatch) — das simuliert
    den Fall, dass sogar `_run_task`s eigener catch-all nicht mehr greift (z. B. weil einer der
    Fehlerpfad-Helfer selbst eine Exception wirft). VORHER hätte genau das die `while True`-
    Schleife in `_worker()` für immer beendet: alle künftigen Tasks blieben ab da "queued", ohne
    jede Logzeile (`_workers` wird nach dem Start nie wieder gelesen, kein Supervisor). Der
    Beweis, dass die Schleife überlebt: ein ZWEITER, nach dem Fehlschlag eingereihter Task wird
    trotzdem verarbeitet. Async ohne neue Abhängigkeit: `asyncio.run(...)` in einer normalen
    Testfunktion (F5, KEIN pytest-asyncio), Worker-Task am Ende sauber gecancelt."""
    import app.agent_runner as ar

    verarbeitet = []

    async def fake_run_task(task_id):
        if task_id == 1:
            raise RuntimeError("Simulierter Totalausfall (pytest) — z. B. ein DB-Commit, der "
                                "selbst im Fehlerpfad noch wirft")
        verarbeitet.append(task_id)

    monkeypatch.setattr(ar, "_run_task", fake_run_task)
    monkeypatch.setattr(ar, "_queue", asyncio.Queue())

    async def szenario():
        worker = asyncio.create_task(ar._worker())
        ar._queue.put_nowait(1)          # stirbt (simuliert) — darf die Schleife NICHT beenden
        ar._queue.put_nowait(2)          # MUSS trotzdem verarbeitet werden
        # P2-19: Notbremse gegen Haengen, keine Laufzeitzusage
        await asyncio.wait_for(ar._queue.join(), timeout=60)
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker

    asyncio.run(szenario())

    assert verarbeitet == [2]            # Beweis: die Schleife lebt nach dem ersten Fehlschlag weiter


def test_worker_meldet_verlorenen_task_laut(monkeypatch, _db_ready, capsys):
    """F4: der neue except-Block in `_worker()` muss laut sein (Task-ID + Fehler auf stdout),
    nicht nur schweigend weiterlaufen. Gleicher Aufbau wie oben, hier auf die Meldung selbst
    geprüft."""
    import app.agent_runner as ar

    TASK_ID = 7

    async def fake_run_task(task_id):
        raise RuntimeError("Simulierter Totalausfall (pytest)")

    monkeypatch.setattr(ar, "_run_task", fake_run_task)
    monkeypatch.setattr(ar, "_queue", asyncio.Queue())

    async def szenario():
        worker = asyncio.create_task(ar._worker())
        ar._queue.put_nowait(TASK_ID)
        # P2-19: Notbremse gegen Haengen, keine Laufzeitzusage
        await asyncio.wait_for(ar._queue.join(), timeout=60)
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker

    asyncio.run(szenario())

    out = capsys.readouterr().out
    assert f"Task {TASK_ID}" in out
    assert "Simulierter Totalausfall" in out
    assert "[agent-runner]" in out


def test_update_db_fehler_wird_laut_gemeldet_statt_geworfen(monkeypatch, capsys, session):
    """Zweite Verteidigungslinie desselben Befunds (P2-1): `_update()` — von `_fehlschlag()` und
    `_finish()` im Fehlerpfad aufgerufen — darf einen gescheiterten Commit selbst NICHT nach oben
    werfen, sonst reißt sie ihren Aufrufer mit (bis hinauf zu `_worker()`s Schleife, s. Test
    oben). Erzwungen über einen Monkeypatch auf `Session.commit` (dieselbe Klasse, die
    `agent_runner._update()` über `from sqlmodel import Session` verwendet)."""
    import app.agent_runner as ar
    from sqlmodel import Session as SM_Session
    from app.models import AgentTask

    task = AgentTask(kind="firma-pruefen", status="queued", prompt="Testprompt (pytest)")
    session.add(task)
    session.commit()
    session.refresh(task)
    task_id = task.id     # sofort in int kopieren (s. test_loeschen_reihenfolge.py-Konvention)

    def kaputter_commit(self):
        raise RuntimeError("Simulierter DB-Fehler beim Commit (pytest, z. B. 'database is locked')")

    monkeypatch.setattr(SM_Session, "commit", kaputter_commit)

    ar._update(task_id, status="running")   # darf NICHT werfen

    out = capsys.readouterr().out
    assert "_update" in out
    assert f"Task {task_id}" in out
    assert "Simulierter DB-Fehler" in out


# ═══════════════════════════════════════════════════════════════════════════════════════════
# P2-19 — db._ensure_columns() meldet PRAGMA-Fehlschläge, ALTER TABLE ist idempotent abgesichert
# ═══════════════════════════════════════════════════════════════════════════════════════════

def _frischer_engine(tmp_path, monkeypatch):
    """Eigene, isolierte SQLite-Datei + Engine anstelle von `app.db.engine` (lokale Kopie des
    Musters aus test_db_migration.py::_frischer_engine — Testdateien importieren laut
    conftest.py-Konvention nicht voneinander)."""
    from sqlmodel import create_engine
    import app.db as db_modul

    db_path = tmp_path / "isoliert_p64b.sqlite"
    ersatz_engine = create_engine(f"sqlite:///{db_path}", echo=False,
                                  connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_modul, "engine", ersatz_engine)
    return db_modul


def test_ensure_columns_pragma_fehler_wird_laut_gemeldet_mit_tabellenname(tmp_path, monkeypatch, capsys):
    """Kernbeweis von P2-19: `PRAGMA table_info(job)` wirft (Monkeypatch) — vorher
    `except Exception: continue` OHNE jede Ausgabe, die Migration dieser EINEN Tabelle
    verschwand spurlos. Jetzt: Tabellenname + Fehler landen auf stdout, UND `_ensure_columns()`
    wirft trotzdem nicht (die übrigen Tabellen werden weiter migriert)."""
    import sqlalchemy
    db_modul = _frischer_engine(tmp_path, monkeypatch)
    db_modul.init_db()      # volles modernes Schema — alle Spalten existieren bereits

    orig_exec = sqlalchemy.engine.Connection.exec_driver_sql

    def kaputtes_pragma(self, sql, *a, **kw):
        if "PRAGMA table_info(job)" in sql:
            raise sqlite3.OperationalError("simulierter PRAGMA-Fehler (pytest)")
        return orig_exec(self, sql, *a, **kw)

    monkeypatch.setattr(sqlalchemy.engine.Connection, "exec_driver_sql", kaputtes_pragma)

    db_modul._ensure_columns()      # darf NICHT werfen

    out = capsys.readouterr().out
    assert "job" in out
    assert "simulierter PRAGMA-Fehler" in out


def test_ensure_columns_alter_table_duplicate_column_bleibt_leise(tmp_path, monkeypatch, capsys):
    """P2-19-Zusatz: SQLite kennt kein "ADD COLUMN IF NOT EXISTS". Seit Phase 63 startet jeder
    Skill-Lauf `init_db()` in einem eigenen Subprozess — zwei fast gleichzeitig gestartete
    Prozesse könnten beide dieselbe fehlende Spalte sehen und beide `ALTER TABLE` versuchen; der
    zweite bekommt "duplicate column name" vom jeweils anderen Prozess, der zuerst fertig wurde.
    Das ist harmlos (die Spalte existiert danach so oder so) und MUSS leise übergangen werden —
    keine Meldung, kein Crash."""
    import sqlalchemy
    db_modul = _frischer_engine(tmp_path, monkeypatch)
    db_modul.init_db()      # Kernschema — "wettlauf_spalte" ist KEIN echtes Modellfeld

    monkeypatch.setattr(db_modul, "_ADD_COLUMNS", {"job": [("wettlauf_spalte", "TEXT")]})

    orig_exec = sqlalchemy.engine.Connection.exec_driver_sql

    def wettlauf_simuliert(self, sql, *a, **kw):
        if "ALTER TABLE job ADD COLUMN wettlauf_spalte" in sql:
            # Simuliert: ein ZWEITER, fast gleichzeitig gestarteter Prozess hat dieselbe Spalte
            # gerade eben schon angelegt (Race, s. Docstring).
            raise sqlite3.OperationalError("duplicate column name: wettlauf_spalte")
        return orig_exec(self, sql, *a, **kw)

    monkeypatch.setattr(sqlalchemy.engine.Connection, "exec_driver_sql", wettlauf_simuliert)

    db_modul._ensure_columns()      # darf NICHT werfen

    out = capsys.readouterr().out
    assert out == ""                # "duplicate column" ist die bewusste Ausnahme von F4 — leise


def test_ensure_columns_alter_table_anderer_fehler_wird_laut_gemeldet(tmp_path, monkeypatch, capsys):
    """Gegenprobe zum Duplicate-Column-Fall: JEDER ANDERE `ALTER TABLE`-Fehler (Disk voll,
    gesperrte DB, falscher Typ, ...) MUSS laut sein (F4) — er darf nicht in derselben stillen
    Behandlung wie eine harmlose Wettlauf-Dublette verschwinden."""
    import sqlalchemy
    db_modul = _frischer_engine(tmp_path, monkeypatch)
    db_modul.init_db()

    monkeypatch.setattr(db_modul, "_ADD_COLUMNS", {"job": [("kaputte_spalte", "TEXT")]})

    orig_exec = sqlalchemy.engine.Connection.exec_driver_sql

    def anderer_fehler(self, sql, *a, **kw):
        if "ALTER TABLE job ADD COLUMN kaputte_spalte" in sql:
            raise sqlite3.OperationalError("disk I/O error")     # KEIN "duplicate column"
        return orig_exec(self, sql, *a, **kw)

    monkeypatch.setattr(sqlalchemy.engine.Connection, "exec_driver_sql", anderer_fehler)

    db_modul._ensure_columns()      # darf NICHT werfen — aber MUSS laut sein

    out = capsys.readouterr().out
    assert "job" in out
    assert "kaputte_spalte" in out
    assert "disk I/O error" in out


# ═══════════════════════════════════════════════════════════════════════════════════════════
# P2-20 — beirat_engine: _task_abschliessen()-Fehler blockiert das SSE-Ende-Signal nicht mehr
# ═══════════════════════════════════════════════════════════════════════════════════════════

def _neue_test_debatte(monkeypatch, tmp_path, *, min_beitraege=2):
    """Minimale Debatte im Modus "frei" (kein Stellen-Check, keine 7-köpfige Abstimmung nötig).
    `DATEN_DIR` wird auf ein tmp-Verzeichnis umgebogen, damit `Debatte._speichern()` (im
    `finally`-Block von `laufen()` aufgerufen) NIEMALS in das echte `data/beirat/` schreibt —
    lokale Kopie des Musters aus test_beirat_fehler.py::_neue_test_debatte."""
    import beirat_engine

    monkeypatch.setattr(beirat_engine, "DATEN_DIR", tmp_path / "beirat_test")
    d = beirat_engine.Debatte(
        thema="Testfrage für P2-20 (synthetisch)", kontext="", min_beitraege=min_beitraege,
        teilnehmer_ids=None, provider="anthropic", openai_model="gpt-4o-mini", modus="frei",
    )
    assert d.task_id is None    # Sicherheitsnetz: kein echtes AgentTask/Log beim Direkt-Konstruieren
    return d, beirat_engine


def test_task_abschliessen_fehler_wird_laut_gemeldet_und_ende_signal_kommt_trotzdem(
    monkeypatch, tmp_path, _db_ready, capsys
):
    """Kernbeweis von P2-20: `_task_abschliessen()` wirft (Monkeypatch) — VORHER hätte das den
    kompletten `finally`-Block von `laufen()` an dieser Stelle abgerissen: die AgentTask-Zeile
    wäre auf "running" hängen geblieben (blockiert den Doppellauf-Guard bis zum Serverneustart)
    UND das SSE-Ende-Signal (`queue.put(None)`) hätte die Oberfläche nie erreicht (hängende
    "lädt…"-Anzeige). Schnellster Weg in den `finally`-Block: der Dispatch-Turn schlägt zweimal
    fehl (1 Versuch + 1 Retry, dann ehrlicher Abbruch — Muster aus
    test_beirat_fehler.py::test_dispatch_bricht_ehrlich_ab_nach_erschoepftem_retry). Der
    eigentliche Prüfgegenstand ist NICHT dieser Dispatch-Fehler, sondern dass
    `_task_abschliessen()` danach laut scheitert, OHNE `queue.put(None)` zu verhindern (B1: kein
    echter Beirats-Lauf — `_turn` ist komplett gefaked, keine echte API wird angefasst)."""
    d, be = _neue_test_debatte(monkeypatch, tmp_path)

    async def fake_turn(provider, openai_model, system_prompt, user_prompt, persona_model,
                        on_delta, task_id=None):
        raise RuntimeError("Dispatch-Fehler (synthetisch, für den Test)")

    def kaputtes_abschliessen(debatte):
        raise RuntimeError("Simulierter DB-Fehler beim Abschließen (pytest)")

    monkeypatch.setattr(be, "_turn", fake_turn)
    monkeypatch.setattr(be, "_task_abschliessen", kaputtes_abschliessen)

    asyncio.run(d.laufen())

    assert d.status == "fehler"     # unverändertes Verhalten des Dispatch-Fehlerpfads (F3)

    out = capsys.readouterr().out
    assert "_task_abschliessen" in out
    assert "Simulierter DB-Fehler" in out

    # Kernbeweis: das SSE-Ende-Signal kam TROTZDEM an.
    ereignisse = []
    while not d.queue.empty():
        ereignisse.append(d.queue.get_nowait())
    assert ereignisse[-1] is None
