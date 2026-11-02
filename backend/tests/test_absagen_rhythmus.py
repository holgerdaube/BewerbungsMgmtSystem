"""Tests für P2-79 Paket B: die Lost-Order-Analyse läuft wöchentlich im Tageslauf und per Button.

Was hier festgehalten wird:

  1. Kette: `absagen-analyse` steht im Tageslauf zwischen `email-check` und `views-refresh`, und die
     Beobachtungsliste des Tageslauf-Knopfs im Frontend (`SCHRITTE`) führt dieselben Schritte.
  2. Vorprüfung ohne Modellstart (`in_kette_nur_wenn`): Als Kettenschritt fragt der Runner vor dem
     Start die Prüffunktion. Nicht fällig → `done` mit der Begründung, kein Subprozess, die
     Nachfolger werden eingereiht. Fällig → normaler Start. Ein Start von Hand (ohne `chain_id`)
     prüft nie. Eine werfende, fehlende oder unsinnig antwortende Prüffunktion heißt „läuft“.
  3. Nicht-kritischer Schritt (`kette_weiter_bei_fehler`): `failed` lässt die Nachfolger laufen
     (auch nach Timeout und erst nach dem einen Retry), Arten ohne den Schlüssel brechen weiter ab,
     `cancelled` bricht immer ab. Dasselbe gilt für den Neustart-Pfad in `start_workers()`.
  4. Endpunkt `GET /api/absagen-analyse`: neuester Bericht mit Datum aus dem Dateinamen und Link,
     oder `{"datei": null}`.

Kein echter Skill-Lauf und kein Netz: der Subprozess ist eine Attrappe, die jeden Aufruf aufschreibt
und `FileNotFoundError` wirft (so endet ein Lauf mit fehlender Binary als `failed`). Der Runner läuft
auf einer eigenen Wegwerf-Datenbank (`agent_runner.engine` umgebunden) und `enqueue` schreibt nur auf.
Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention).
"""
import asyncio
import json
import os
import re
import time
from pathlib import Path

import pytest

PROJEKT = Path(__file__).resolve().parents[2]


# ── Hilfen ────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture()
def runner_db(tmp_path, monkeypatch):
    """Eigene Datenbank für den Runner (`agent_runner.engine` umgebunden), damit Ketten und
    Wiedereinreihungen nicht in der gemeinsamen Test-DB landen. Die Log-Rotation nach jedem
    Abschluss ist abgeschaltet: sie hätte hier nichts zu tun, griffe aber auf Ordner des
    Projekts zu (`cleanup_tmp`)."""
    from sqlmodel import SQLModel, create_engine
    import app.agent_runner as ar
    from app import models  # noqa: F401  (Modelle registrieren)

    engine = create_engine(f"sqlite:///{tmp_path / 'rhythmus.sqlite'}",
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(ar, "engine", engine)
    monkeypatch.setattr(ar, "_cleanup_logs_gedrosselt", lambda: None)
    return engine


@pytest.fixture()
def spawn(monkeypatch):
    """Ersetzt `asyncio.create_subprocess_exec` durch eine Attrappe, die jeden Aufruf aufschreibt
    und `FileNotFoundError` wirft. Die Liste der Aufrufe ist die Prüfgröße „wurde ein Modell
    gestartet?“. `_child_env` liest hier keine Secrets."""
    import app.agent_runner as ar

    aufrufe = []

    async def attrappe(*argv, **kwargs):
        aufrufe.append(argv)
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(ar.asyncio, "create_subprocess_exec", attrappe)
    monkeypatch.setattr(ar, "_child_env", lambda kind, anbieter=None: ({}, None))
    return aufrufe


@pytest.fixture()
def eingereiht(monkeypatch):
    """`enqueue` schreibt nur auf, welche Task-IDs der Runner an die Warteschlange gibt."""
    import app.agent_runner as ar

    ids = []
    monkeypatch.setattr(ar, "enqueue", ids.append)
    return ids


@pytest.fixture()
def pruefung(monkeypatch):
    """Ersetzt `pipeline.absagen_bericht.faellig` durch eine Attrappe. Der Runner löst die Funktion
    erst beim Aufruf über „modul:funktion“ auf, greift also auf diese Attrappe zu. Gibt ein Objekt
    mit `.antwort` (Rückgabewert oder eine Exception, die geworfen wird) und `.aufrufe` zurück."""
    from pipeline import absagen_bericht

    class _Pruefung:
        antwort = (False, "Übersprungen: Test-Grund")
        aufrufe = 0

    p = _Pruefung()

    def faellig(*args, **kwargs):
        p.aufrufe += 1
        if isinstance(p.antwort, Exception):
            raise p.antwort
        return p.antwort

    monkeypatch.setattr(absagen_bericht, "faellig", faellig)
    return p


def _aufgabe(engine, **felder) -> int:
    from sqlmodel import Session
    from app.models import AgentTask

    with Session(engine) as s:
        t = AgentTask(**{"kind": "absagen-analyse", "status": "queued", "prompt": "Absagen-Analyse",
                         **felder})
        s.add(t)
        s.commit()
        s.refresh(t)
        return t.id


def _zeile(engine, task_id):
    from sqlmodel import Session
    from app.models import AgentTask

    with Session(engine) as s:
        t = s.get(AgentTask, task_id)
        s.expunge(t)
        return t


def _kette(engine, erste_art="absagen-analyse", folge_art="views-refresh", chain_id="wk1",
           status="queued"):
    """Zwei Kettenglieder: der erste Schritt und sein Nachfolger (wartet auf den ersten)."""
    erster = _aufgabe(engine, kind=erste_art, chain_id=chain_id, chain_pos=1, status=status)
    zweiter = _aufgabe(engine, kind=folge_art, chain_id=chain_id, chain_pos=2, depends_on=erster)
    return erster, zweiter


# ── 1. Kette ─────────────────────────────────────────────────────────────────────────────────
def test_tageslauf_fuehrt_die_absagen_analyse_zwischen_postfach_und_ansichten():
    from app import agent_runner as ar

    schritte = ar.RECIPES["tageslauf"]["steps"]

    assert schritte == ["jobsuche", "mail-jobsuche", "zielfirmen-sweep", "headhunter-suche",
                        "beworben-check", "email-check", "absagen-analyse", "views-refresh",
                        "coach-site"]
    # nach dem Postfach (neue Absagen drin), vor den Ansichten (Favicon-Nachrüstung) und vor dem
    # Coach-Upload (der Coach hat den Bericht am selben Tag)
    assert schritte.index("email-check") + 1 == schritte.index("absagen-analyse")
    assert schritte.index("absagen-analyse") + 1 == schritte.index("views-refresh")
    assert schritte.index("absagen-analyse") < schritte.index("coach-site")


def test_tageslauf_label_und_aufloesung_bleiben_bis_auf_den_schritt_gleich():
    from app import agent_runner as ar

    schritte, label = ar.rezept_aufloesen("tageslauf", {}, {})

    assert label == "Tageslauf (Jobsuche + Sweeps + Postfach + Gmail + Ansichten)"
    assert schritte == ar.RECIPES["tageslauf"]["steps"]


def test_tageslauf_knopf_beobachtet_dieselben_schritte_wie_die_kette():
    """Fehlt ein Schritt in `SCHRITTE`, meldet der Knopf „fertig“, während die Kette noch läuft."""
    from app import agent_runner as ar

    quelle = (PROJEKT / "frontend" / "src" / "components" / "TageslaufButton.tsx").read_text(
        encoding="utf-8")
    treffer = re.search(r"const SCHRITTE = \[(.*?)\]", quelle, re.S)
    assert treffer, "SCHRITTE in TageslaufButton.tsx nicht gefunden"

    assert re.findall(r"'([a-z-]+)'", treffer.group(1)) == ar.RECIPES["tageslauf"]["steps"]


def test_absagen_analyse_eintrag_traegt_die_neuen_schluessel_und_den_laengeren_timeout():
    import importlib
    from app import agent_runner as ar

    eintrag = ar.PROMPTS["absagen-analyse"]

    assert eintrag["in_kette_nur_wenn"] == "pipeline.absagen_bericht:faellig"
    assert eintrag["kette_weiter_bei_fehler"] is True
    assert eintrag["retryable"] is True
    assert ar._timeout_for("absagen-analyse") == 2400
    modul, funktion = eintrag["in_kette_nur_wenn"].split(":")
    assert callable(getattr(importlib.import_module(modul), funktion))     # löst wirklich auf


def test_kein_anderer_task_traegt_die_neuen_schluessel():
    """Beide Schlüssel sind opt-in: für alle anderen Arten bleibt das Verhalten unverändert."""
    from app import agent_runner as ar

    andere = {kind for kind, e in ar.PROMPTS.items() if kind != "absagen-analyse"
              and ("in_kette_nur_wenn" in e or "kette_weiter_bei_fehler" in e)}

    assert andere == set()


# ── 2. Vorprüfung ohne Modellstart ───────────────────────────────────────────────────────────
def test_kettenschritt_nicht_faellig_endet_done_ohne_subprozess_und_reicht_weiter(
        runner_db, spawn, eingereiht, pruefung):
    import app.agent_runner as ar

    erster, zweiter = _kette(runner_db)
    pruefung.antwort = (False, "Übersprungen: Der Bericht dieser Woche liegt vor (Stand 12.10.2026).")

    asyncio.run(ar._run_task(erster))

    assert pruefung.aufrufe == 1
    assert spawn == []                                  # kein Modell, kein Subprozess
    t = _zeile(runner_db, erster)
    assert t.status == "done"
    assert t.exit_code == 0 and t.error is None
    assert t.num_turns == 0 and t.cost_usd == 0.0
    assert t.started_at is not None and t.finished_at is not None and t.duration_s is not None
    assert t.log_path is None and t.pid is None         # keine Log-Datei, kein Prozess
    assert t.retry_count == 0
    ergebnis = json.loads(t.result_json)
    assert ergebnis["subtype"] == "success"
    assert ergebnis["result"] == "Übersprungen: Der Bericht dieser Woche liegt vor (Stand 12.10.2026)."
    # der Nachfolger läuft wie nach jedem erfolgreichen Schritt an
    assert eingereiht == [zweiter]
    assert _zeile(runner_db, zweiter).status == "queued"


def test_kettenschritt_faellig_startet_den_subprozess(runner_db, spawn, eingereiht, pruefung):
    """Gegenkontrolle zum Test oben: derselbe Aufbau, nur „fällig“ — jetzt erreicht der Lauf den Spawn."""
    import app.agent_runner as ar

    erster, _ = _kette(runner_db)
    pruefung.antwort = (True, "Letzter Bericht vom 05.10.2026.")

    asyncio.run(ar._run_task(erster))

    assert pruefung.aufrufe == 1
    assert len(spawn) == 1


def test_start_von_hand_prueft_nie(runner_db, spawn, eingereiht, pruefung):
    """Ohne `chain_id` (Dashboard-Knopf, Chat) läuft der Skill immer, auch wenn die Prüfung
    „nicht fällig“ sagen würde — und die Prüffunktion wird gar nicht erst gefragt."""
    import app.agent_runner as ar

    task_id = _aufgabe(runner_db)                      # chain_id leer
    pruefung.antwort = (False, "Übersprungen: Test-Grund")

    asyncio.run(ar._run_task(task_id))

    assert pruefung.aufrufe == 0
    assert len(spawn) == 1


def test_werfende_pruefung_heisst_normaler_start_und_steht_im_log(
        runner_db, spawn, eingereiht, pruefung, capsys):
    import app.agent_runner as ar

    erster, _ = _kette(runner_db)
    pruefung.antwort = RuntimeError("Datenbank gesperrt (pytest)")

    asyncio.run(ar._run_task(erster))

    assert pruefung.aufrufe == 1
    assert len(spawn) == 1                              # lieber einmal zu viel ausgewertet
    out = capsys.readouterr().out
    assert "Vorprüfung" in out and "Datenbank gesperrt (pytest)" in out and f"Task {erster}" in out


@pytest.mark.parametrize("antwort", [False, None, (True,), "fällig"],
                         ids=["bool", "none", "ein-element", "text"])
def test_unsinnige_antwort_der_pruefung_heisst_normaler_start(
        runner_db, spawn, eingereiht, pruefung, antwort):
    import app.agent_runner as ar

    erster, _ = _kette(runner_db)
    pruefung.antwort = antwort

    asyncio.run(ar._run_task(erster))

    assert len(spawn) == 1


@pytest.mark.parametrize("spec", ["pipeline.gibt_es_nicht:faellig", "pipeline.absagen_bericht:gibt_es_nicht",
                                  "ohne_doppelpunkt", ":"],
                         ids=["modul-fehlt", "funktion-fehlt", "ohne-doppelpunkt", "leer"])
def test_kaputte_angabe_modul_funktion_heisst_normaler_start(
        runner_db, spawn, eingereiht, monkeypatch, spec):
    import app.agent_runner as ar

    monkeypatch.setitem(ar.PROMPTS, "absagen-analyse",
                        {**ar.PROMPTS["absagen-analyse"], "in_kette_nur_wenn": spec})
    erster, _ = _kette(runner_db)

    asyncio.run(ar._run_task(erster))

    assert len(spawn) == 1


def test_art_ohne_schluessel_wird_in_der_kette_nicht_geprueft(runner_db, spawn, eingereiht, pruefung):
    import app.agent_runner as ar

    erster, _ = _kette(runner_db, erste_art="email-check")

    asyncio.run(ar._run_task(erster))

    assert pruefung.aufrufe == 0
    assert len(spawn) == 1


def test_echte_pruefung_ueberspringt_den_schritt_wenn_nichts_auszuwerten_ist(
        runner_db, spawn, eingereiht, monkeypatch):
    """Ohne Attrappe: Der Runner löst „pipeline.absagen_bericht:faellig“ wirklich auf. Nur die
    Zählung der auszuwertenden Stellen ist ersetzt (0), alles andere ist der echte Code."""
    import app.agent_runner as ar
    from pipeline import absagen_bericht

    monkeypatch.setattr(absagen_bericht, "anzahl_auswertbar", lambda: 0)
    erster, zweiter = _kette(runner_db)

    asyncio.run(ar._run_task(erster))

    assert spawn == []
    t = _zeile(runner_db, erster)
    assert t.status == "done"
    assert json.loads(t.result_json)["result"].startswith("Übersprungen: keine Absagen")
    assert eingereiht == [zweiter]


# ── 3. Nicht-kritischer Kettenschritt ────────────────────────────────────────────────────────
def test_failed_mit_schluessel_laesst_die_nachfolger_laufen(runner_db, spawn, eingereiht, pruefung):
    import app.agent_runner as ar

    erster, zweiter = _kette(runner_db)
    pruefung.antwort = (True, "Noch kein Bericht vorhanden.")

    asyncio.run(ar._run_task(erster))                   # Attrappe wirft FileNotFoundError → failed

    t = _zeile(runner_db, erster)
    assert t.status == "failed" and "nicht gefunden" in t.error
    assert eingereiht == [zweiter]                      # Nachfolger werden eingereiht
    nachfolger = _zeile(runner_db, zweiter)
    assert nachfolger.status == "queued" and nachfolger.error is None


def test_failed_ohne_schluessel_bricht_die_kette_weiter_ab(runner_db, spawn, eingereiht):
    """Bestehendes Verhalten: Die Art `email-check` trägt den Schlüssel nicht."""
    import app.agent_runner as ar

    erster, zweiter = _kette(runner_db, erste_art="email-check")

    asyncio.run(ar._run_task(erster))

    assert _zeile(runner_db, erster).status == "failed"
    assert eingereiht == []
    nachfolger = _zeile(runner_db, zweiter)
    assert nachfolger.status == "cancelled"
    assert "Kette abgebrochen" in nachfolger.error


def test_cancelled_bricht_auch_mit_schluessel_ab(runner_db, eingereiht):
    import app.agent_runner as ar

    erster, zweiter = _kette(runner_db, status="running")
    ar._finish(erster, ar._now(), "cancelled", error="Vom Nutzer abgebrochen")

    assert _zeile(runner_db, erster).status == "cancelled"
    assert eingereiht == []
    nachfolger = _zeile(runner_db, zweiter)
    assert nachfolger.status == "cancelled" and "Kette abgebrochen" in nachfolger.error


def test_abbrechen_eines_wartenden_schritts_bricht_auch_mit_schluessel_ab(runner_db, eingereiht):
    import app.agent_runner as ar

    erster, zweiter = _kette(runner_db)

    assert asyncio.run(ar.cancel(erster)) is True

    assert _zeile(runner_db, erster).status == "cancelled"
    assert _zeile(runner_db, zweiter).status == "cancelled"
    assert eingereiht == []


def test_retry_reicht_noch_nicht_weiter_erst_der_endgueltige_fehlschlag(
        runner_db, eingereiht, pruefung, monkeypatch):
    """Der eine Versuch mehr gehört dem Schritt: Nach dem ersten Fehlschlag wird er neu eingereiht
    und der Nachfolger bleibt unberührt. Erst der zweite Fehlschlag gibt die Kette frei."""
    import app.agent_runner as ar

    aufrufe = []

    async def abstuerzender_start(*argv, **kwargs):
        aufrufe.append(argv)
        raise RuntimeError("Absturz beim Start")        # nicht FileNotFoundError → Wiederholung

    monkeypatch.setattr(ar.asyncio, "create_subprocess_exec", abstuerzender_start)
    monkeypatch.setattr(ar, "_child_env", lambda kind, anbieter=None: ({}, None))
    erster, zweiter = _kette(runner_db)
    pruefung.antwort = (True, "Noch kein Bericht vorhanden.")

    asyncio.run(ar._run_task(erster))                   # erster Versuch

    t = _zeile(runner_db, erster)
    assert t.status == "queued" and t.retry_count == 1
    assert eingereiht == [erster]                       # nur er selbst, der Nachfolger noch nicht
    assert _zeile(runner_db, zweiter).status == "queued"

    asyncio.run(ar._run_task(erster))                   # zweiter Versuch, endgültig

    assert len(aufrufe) == 2
    assert _zeile(runner_db, erster).status == "failed"
    assert eingereiht == [erster, zweiter]
    assert _zeile(runner_db, zweiter).status == "queued"


def test_timeout_mit_schluessel_laesst_die_nachfolger_laufen(
        runner_db, eingereiht, pruefung, monkeypatch):
    import app.agent_runner as ar

    class _Haengender:
        pid = 2_000_000_000
        stdout = None

        async def wait(self):
            return -9

    async def start(*argv, **kwargs):
        return _Haengender()

    async def haengt(proc, log_file, auswertung=None):
        await asyncio.sleep(3600)

    monkeypatch.setattr(ar.asyncio, "create_subprocess_exec", start)
    monkeypatch.setattr(ar, "_child_env", lambda kind, anbieter=None: ({}, None))
    monkeypatch.setattr(ar, "_drain", haengt)
    monkeypatch.setattr(ar, "_kill", lambda pid: None)
    monkeypatch.setattr(ar, "_timeout_for", lambda kind: 0.05)
    erster, zweiter = _kette(runner_db)
    pruefung.antwort = (True, "Noch kein Bericht vorhanden.")

    asyncio.run(ar._run_task(erster))

    t = _zeile(runner_db, erster)
    assert t.status == "failed" and t.error.startswith("Timeout nach")
    assert eingereiht == [zweiter]
    assert _zeile(runner_db, zweiter).status == "queued"


# ── 3b. Neustart-Pfad (start_workers) ────────────────────────────────────────────────────────
def _start_workers_und_warteschlange(monkeypatch):
    """Ruft `start_workers()` ohne Nebenwirkungen auf (keine Worker, keine Aufräumarbeiten) und gibt
    zurück, welche Task-IDs die Wiedereinreihung in die Warteschlange gelegt hat."""
    import app.agent_runner as ar

    async def kein_worker():
        return None

    monkeypatch.setattr(ar, "_queue", None)
    monkeypatch.setattr(ar, "_workers", [])
    monkeypatch.setattr(ar, "_worker", kein_worker)
    monkeypatch.setattr(ar, "cleanup_logs", lambda: 0)
    monkeypatch.setattr(ar, "cleanup_tmp", lambda *a, **k: 0)
    monkeypatch.setattr(ar, "_backup_hinweis", lambda: "")
    monkeypatch.setattr(ar, "check_env_file", lambda: [])
    monkeypatch.setattr(ar, "check_secret_files", lambda: [])

    async def szenario():
        ar.start_workers()
        return [ar._queue.get_nowait() for _ in range(ar._queue.qsize())]

    return asyncio.run(szenario())


@pytest.mark.parametrize("art, status, laeuft_weiter", [
    pytest.param("absagen-analyse", "failed", True, id="schluessel-failed-weiter"),
    pytest.param("absagen-analyse", "done", True, id="schluessel-done-weiter"),
    pytest.param("absagen-analyse", "cancelled", False, id="schluessel-cancelled-bricht-ab"),
    pytest.param("email-check", "failed", False, id="ohne-schluessel-failed-bricht-ab"),
    pytest.param("email-check", "done", True, id="ohne-schluessel-done-weiter"),
    pytest.param("email-check", "cancelled", False, id="ohne-schluessel-cancelled-bricht-ab"),
])
def test_neustart_pfad_entscheidet_nach_art_und_endstatus(runner_db, monkeypatch, art, status,
                                                           laeuft_weiter):
    erster, zweiter = _kette(runner_db, erste_art=art, status=status)

    eingereiht = _start_workers_und_warteschlange(monkeypatch)

    nachfolger = _zeile(runner_db, zweiter)
    if laeuft_weiter:
        assert eingereiht == [zweiter]
        assert nachfolger.status == "queued"
    else:
        assert eingereiht == []
        assert nachfolger.status == "cancelled"
        assert "Kette abgebrochen: Vorgänger" in nachfolger.error


def test_neustart_waehrend_die_analyse_lief_gibt_die_kette_frei(runner_db, monkeypatch):
    """Der Server startet neu, während die Analyse lief: die Crash-Recovery markiert sie als
    `failed` ("Server wurde neu gestartet"), und weil sie nicht-kritisch ist, laufen Digest, Excel
    und Coach-Upload des Tages danach trotzdem an."""
    erster, zweiter = _kette(runner_db, status="running")

    eingereiht = _start_workers_und_warteschlange(monkeypatch)

    assert _zeile(runner_db, erster).status == "failed"
    assert eingereiht == [zweiter]
    assert _zeile(runner_db, zweiter).status == "queued"


# ── 4. Endpunkt GET /api/absagen-analyse ─────────────────────────────────────────────────────
@pytest.fixture()
def analysen_ordner(tmp_path, monkeypatch):
    """Ein leerer Ordner `data/analysen` unter einer tmp-Projektwurzel. `ordner()` des Berichts-
    Moduls und die Wurzel von `/api/artifact` zeigen darauf, die Live-Daten bleiben unberührt."""
    import app.main as main_modul
    from pipeline import absagen_bericht

    ordner = tmp_path / "data" / "analysen"
    ordner.mkdir(parents=True)
    monkeypatch.setattr(absagen_bericht, "ordner", lambda: ordner)
    monkeypatch.setattr(main_modul, "_PROJECT_ROOT", tmp_path)
    return ordner


def test_endpunkt_ohne_bericht_liefert_datei_null(client, analysen_ordner):
    antwort = client.get("/api/absagen-analyse")

    assert antwort.status_code == 200
    assert antwort.json() == {"datei": None}


def test_endpunkt_liefert_den_neuesten_bericht_nach_dem_datum_im_dateinamen(client, analysen_ordner):
    alt = analysen_ordner / "20260709_Analyse_Absagen.html"
    neu = analysen_ordner / "20261012_Analyse_Absagen.html"
    alt.write_text("<html><body>alt</body></html>", encoding="utf-8")
    neu.write_text("<html><body>neu</body></html>", encoding="utf-8")
    # Der ältere Bericht ist zuletzt angefasst worden (Favicon-Nachrüstung): zählen darf der Name.
    jetzt = time.time()
    os.utime(neu, (jetzt - 86400, jetzt - 86400))
    os.utime(alt, (jetzt, jetzt))

    antwort = client.get("/api/absagen-analyse")

    assert antwort.status_code == 200
    assert antwort.json() == {
        "datei": "20261012_Analyse_Absagen.html",
        "datum": "2026-10-12",
        "url": "/api/artifact?path=data/analysen/20261012_Analyse_Absagen.html",
    }


def test_link_des_endpunkts_oeffnet_den_bericht_ueber_api_artifact(client, analysen_ordner):
    (analysen_ordner / "20261012_Analyse_Absagen.html").write_text(
        "<html><body><p>Muster-Bericht</p></body></html>", encoding="utf-8")

    url = client.get("/api/absagen-analyse").json()["url"]
    bericht = client.get(url)

    assert bericht.status_code == 200
    assert "text/html" in bericht.headers["content-type"]
    assert "Muster-Bericht" in bericht.text
