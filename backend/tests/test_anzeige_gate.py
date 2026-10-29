"""P2-75, Vertrag C — Halt beim Start, wenn der Anzeigentext einer Stelle fehlt
(tasks/spec_p2-75_anzeigentext_sichern.md).

`create_task` ruft vor dem Einreihen `_guard_anzeigentext()` auf (direkt nach `_guard_low_match`,
mit derselben aufgelösten Schrittmenge). Der Guard holt über `posting_snapshot.anzeigentext_sichern()`
fehlenden Anzeigentext nach und liefert bei `status == "fehlt"` ein 409 mit Marker `ANZEIGE_FEHLT`;
`params.ohne_anzeigentext_ok=true` überspringt Prüfung UND Netzabruf.

Muster: test_low_match_gate.py. Die Gegenseite (Paket B) wird hier gepatcht: Jeder Test setzt
seine eigene Attrappe für `posting_snapshot.anzeigentext_sichern` (`raising=False`, falls die echte
Funktion noch fehlt), die ihre Aufrufe mitschreibt. Es entsteht nie ein Netzabruf. Die autouse-
Attrappe aus conftest.py („vorhanden“) liegt darunter und wird vom Test-inneren setattr überstimmt.

Dass angelegte Tasks nicht loslaufen: `agent_runner.enqueue` ist hier ersetzt (keine Queue, kein
Worker), die Task-Zeilen bleiben `queued`. Jeder Test legt eine eigene Stelle an, weil die
tmp-DB sitzungsweit gilt (kein Rollback) und der Doppellauf-Guard je Job und Art prüft.

Wie in conftest.py beschrieben: KEINE app.*-Importe auf Modulebene, nur in Testfunktionen."""
import asyncio
import threading
import uuid

import pytest

ARTEN = ["anschreiben-erstellen", "cv-erstellen", "cv-match", "firma-pruefen"]
GRUND = "Das Portal blockiert automatische Abrufe."


class _Attrappe:
    """Ersatz für `posting_snapshot.anzeigentext_sichern`: liefert den eingestellten Status und
    schreibt Aufrufe (Job-ID und Thread) mit."""

    def __init__(self, status="fehlt", grund=GRUND, wirkung=None):
        self.status = status
        self.grund = grund
        self.wirkung = wirkung
        self.aufrufe = []
        self.threads = []

    def __call__(self, job_id):
        self.aufrufe.append(job_id)
        self.threads.append(threading.current_thread())
        if self.wirkung:
            self.wirkung(job_id)
        return {"job_id": job_id, "status": self.status, "grund": self.grund, "befund": None,
                "versuche": 1, "posting_snapshot_path": None}


@pytest.fixture(autouse=True)
def _isoliert(tmp_path, monkeypatch):
    """Keine echten Läufe und nie die echte `config/`: `enqueue` ist ein No-op, und das Anlegen
    einer Kette löst `_einstellungen_singleton()` auf, die bei fehlender Zeile aus
    `config/suchprofile.yaml` seedet — dafür bekommt jeder Test eine tmp-Kopie (Muster
    test_bewerbungspaket_optional.py)."""
    from app import agent_runner
    from pipeline import suchprofil

    pfad = tmp_path / "suchprofile.yaml"
    pfad.write_text(suchprofil.MARKER + "\nportale_technik: {}\n", encoding="utf-8")
    monkeypatch.setattr(suchprofil, "SUCHPROFILE_PATH", pfad)
    monkeypatch.setattr(agent_runner, "enqueue", lambda task_id: None)


@pytest.fixture()
def attrappe(monkeypatch):
    """Setzt die Attrappe „fehlt“ (Normalfall dieser Datei) und gibt sie zurück; Tests, die einen
    anderen Status brauchen, ändern `attrappe.status`."""
    from pipeline import posting_snapshot

    a = _Attrappe()
    monkeypatch.setattr(posting_snapshot, "anzeigentext_sichern", a, raising=False)
    return a


def _job_anlegen(session, match_score=4, status="Prüfen"):
    from app.models import Job
    j = Job(company_name=f"Anzeige AG {uuid.uuid4().hex[:8]}", title="Teststelle",
            match_score=match_score, match_rationale="Passt zum Zielprofil",
            status=status, dedup_key=uuid.uuid4().hex)
    session.add(j)
    session.commit()
    session.refresh(j)
    return j


def _tasks_der_stelle(session, job_id):
    from sqlmodel import select
    from app.models import AgentTask
    session.expire_all()
    return session.exec(select(AgentTask).where(AgentTask.job_id == job_id)).all()


# ── Konstante ────────────────────────────────────────────────────────────────────────────────

def test_anzeige_kinds_sind_die_vier_unterlagen_arten_und_echte_task_arten():
    from app import agent_runner
    from app.main import ANZEIGE_KINDS, LOW_MATCH_KINDS
    assert ANZEIGE_KINDS == set(ARTEN)
    assert ANZEIGE_KINDS <= set(agent_runner.PROMPTS)      # nur echte Task-Arten, keine Ketten
    assert ANZEIGE_KINDS is not LOW_MATCH_KINDS             # bewusst eine eigene Konstante


# ── Halt: 409 ANZEIGE_FEHLT ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("art", ARTEN)
def test_jede_unterlagen_art_ohne_anzeigentext_liefert_409_und_keine_task_zeile(
        client, session, attrappe, art):
    j = _job_anlegen(session)
    resp = client.post("/api/tasks", json={"kind": art, "job_id": j.id})
    assert resp.status_code == 409, art
    detail = resp.json()["detail"]
    assert detail.startswith("ANZEIGE_FEHLT: "), detail
    assert GRUND in detail                                  # der Grund aus dem Nachholen kommt mit
    assert detail.endswith("(params.ohne_anzeigentext_ok=true)")
    assert attrappe.aufrufe == [j.id]                       # genau ein Nachhol-Versuch
    assert _tasks_der_stelle(session, j.id) == []           # Halt VOR dem Anlegen der Zeile


def test_fehlertext_wortlaut_wie_in_vertrag_c(client, session, attrappe):
    j = _job_anlegen(session)
    resp = client.post("/api/tasks", json={"kind": "cv-match", "job_id": j.id})
    assert resp.status_code == 409
    assert resp.json()["detail"] == (
        f"ANZEIGE_FEHLT: Der Anzeigentext dieser Stelle liegt nicht vor. {GRUND} "
        "Ohne ihn arbeiten Firma-Prüfung, CV-Match, CV und Anschreiben nur mit Titel und Firma. "
        "(params.ohne_anzeigentext_ok=true)")


def test_ausnahme_beim_nachholen_wird_rueckfrage_statt_500(client, session, monkeypatch):
    """Wirft das Nachholen unerwartet, bekommt der Nutzer die normale Rückfrage (409) mit Grund,
    keinen Serverfehler — „Trotzdem starten“ bleibt so erreichbar."""
    from pipeline import posting_snapshot

    def _wirft(job_id):
        raise OSError("Snapshot nicht lesbar")

    monkeypatch.setattr(posting_snapshot, "anzeigentext_sichern", _wirft, raising=False)
    j = _job_anlegen(session)
    resp = client.post("/api/tasks", json={"kind": "cv-match", "job_id": j.id})
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail.startswith("ANZEIGE_FEHLT: ")
    assert "Der Abruf der Anzeige ist fehlgeschlagen." in detail
    assert _tasks_der_stelle(session, j.id) == []


def test_fehlertext_ohne_grund_hat_keine_doppelten_leerzeichen(client, session, attrappe):
    attrappe.grund = None
    j = _job_anlegen(session)
    resp = client.post("/api/tasks", json={"kind": "firma-pruefen", "job_id": j.id})
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "  " not in detail
    assert detail.startswith("ANZEIGE_FEHLT: Der Anzeigentext dieser Stelle liegt nicht vor. Ohne ihn")


# ── Ausweg: Override und Text vorhanden ──────────────────────────────────────────────────────

@pytest.mark.parametrize("art", ARTEN)
def test_override_startet_und_ruft_die_attrappe_gar_nicht_auf(client, session, attrappe, art):
    j = _job_anlegen(session)
    resp = client.post("/api/tasks", json={"kind": art, "job_id": j.id,
                                           "params": {"ohne_anzeigentext_ok": True}})
    assert resp.status_code == 200, (art, resp.text)
    assert attrappe.aufrufe == []                           # Override = auch kein Netzabruf
    assert [t.kind for t in _tasks_der_stelle(session, j.id)] == [art]


@pytest.mark.parametrize("status", ["vorhanden", "nachgeholt"])
def test_vorhanden_und_nachgeholt_lassen_den_lauf_durch(client, session, attrappe, status):
    attrappe.status = status
    attrappe.grund = None
    j = _job_anlegen(session)
    resp = client.post("/api/tasks", json={"kind": "cv-match", "job_id": j.id})
    assert resp.status_code == 200, resp.text
    assert attrappe.aufrufe == [j.id]                       # geprüft wird immer, auch bei Erfolg
    assert [t.kind for t in _tasks_der_stelle(session, j.id)] == ["cv-match"]


# ── Ketten und freie Arten ───────────────────────────────────────────────────────────────────

def test_kette_bewerbungspaket_wird_ueber_ihre_schritte_gehalten(client, session, attrappe):
    """„bewerbungspaket“ ist ein Rezept, keine Task-Art: der Halt greift über die aufgelöste
    Schrittmenge (firma-pruefen, cv-match, cv-erstellen). Keine einzige Kettenzeile entsteht."""
    j = _job_anlegen(session)
    resp = client.post("/api/tasks", json={"kind": "bewerbungspaket", "job_id": j.id})
    assert resp.status_code == 409
    assert resp.json()["detail"].startswith("ANZEIGE_FEHLT: ")
    assert attrappe.aufrufe == [j.id]                       # EIN Abruf für die ganze Kette
    assert _tasks_der_stelle(session, j.id) == []


def test_kette_bewerbungspaket_mit_override_startet_alle_schritte(client, session, attrappe):
    j = _job_anlegen(session)
    resp = client.post("/api/tasks", json={"kind": "bewerbungspaket", "job_id": j.id,
                                           "params": {"ohne_anzeigentext_ok": True}})
    assert resp.status_code == 200, resp.text
    assert [t["kind"] for t in resp.json()["tasks"]] == ["firma-pruefen", "cv-match", "cv-erstellen"]
    assert attrappe.aufrufe == []


def test_tageslauf_und_freie_art_werden_nicht_geprueft(client, session, attrappe):
    """Weder die Kette „tageslauf“ (reine Ingest-Schritte) noch eine Art außerhalb von
    ANZEIGE_KINDS lösen Prüfung oder Nachhol-Abruf aus — auch nicht, wenn eine Stelle mitkommt."""
    j = _job_anlegen(session)
    r1 = client.post("/api/tasks", json={"kind": "tageslauf", "job_id": j.id})
    assert r1.status_code == 200, r1.text
    j2 = _job_anlegen(session)
    r2 = client.post("/api/tasks", json={"kind": "entscheider-recherche", "job_id": j2.id})
    assert r2.status_code == 200, r2.text
    assert attrappe.aufrufe == []


# ── Zusammenspiel mit LOW_MATCH ──────────────────────────────────────────────────────────────

def test_low_match_kommt_zuerst_dann_anzeige_fehlt_dann_start(client, session, attrappe):
    """Zielstellen-Fit ≤ 2 UND kein Anzeigentext: erst LOW_MATCH (der Nachhol-Abruf wird dafür gar
    nicht erst gemacht), mit `low_match_ok` dann ANZEIGE_FEHLT, mit beiden Overrides startet der
    Lauf. Genau diese Reihenfolge fährt die Oberfläche beim Sammeln der Bestätigungen."""
    j = _job_anlegen(session, match_score=1)

    r1 = client.post("/api/tasks", json={"kind": "firma-pruefen", "job_id": j.id})
    assert r1.status_code == 409 and r1.json()["detail"].startswith("LOW_MATCH:")
    assert attrappe.aufrufe == []

    r2 = client.post("/api/tasks", json={"kind": "firma-pruefen", "job_id": j.id,
                                         "params": {"low_match_ok": True}})
    assert r2.status_code == 409 and r2.json()["detail"].startswith("ANZEIGE_FEHLT: ")
    assert attrappe.aufrufe == [j.id]
    assert _tasks_der_stelle(session, j.id) == []

    r3 = client.post("/api/tasks", json={"kind": "firma-pruefen", "job_id": j.id,
                                         "params": {"low_match_ok": True,
                                                    "ohne_anzeigentext_ok": True}})
    assert r3.status_code == 200, r3.text
    assert attrappe.aufrufe == [j.id]                       # unverändert: Override ruft nicht auf
    assert [t.kind for t in _tasks_der_stelle(session, j.id)] == ["firma-pruefen"]


# ── Guard als Einheit ────────────────────────────────────────────────────────────────────────

def test_guard_ohne_job_ohne_schnittmenge_und_mit_override_tut_nichts(session, attrappe):
    from app.main import _guard_anzeigentext
    j = _job_anlegen(session)
    asyncio.run(_guard_anzeigentext(None, {"cv-match"}, {}, session))                    # kein Job
    asyncio.run(_guard_anzeigentext(j, {"jobsuche", "views-refresh"}, {}, session))      # keine Art
    asyncio.run(_guard_anzeigentext(j, set(), {}, session))                              # leer
    asyncio.run(_guard_anzeigentext(j, {"cv-match"}, {"ohne_anzeigentext_ok": True}, session))
    asyncio.run(_guard_anzeigentext(j, {"cv-match"}, {"ohne_anzeigentext_ok": 1}, session))   # truthy
    assert attrappe.aufrufe == []


def test_guard_laeuft_im_threadpool_und_liest_die_stelle_danach_neu(session, attrappe):
    """Vertrag C: der Abruf darf nie synchron im Event-Loop laufen (er kann mit Pausen gut 30 s
    dauern und würde den ganzen Server anhalten) — er läuft in einem Worker-Thread. Danach wird
    die Stelle mit `session.refresh(job)` neu gelesen: Die Attrappe schreibt den Snapshot-Pfad
    über eine EIGENE Session, wie es die echte Funktion tut; ohne refresh sähe `job` den alten
    Stand."""
    from sqlmodel import Session
    from app.db import engine
    from app.main import _guard_anzeigentext
    from app.models import Job

    j = _job_anlegen(session)
    assert j.posting_snapshot_path is None

    def _schreibt_pfad(job_id):
        with Session(engine) as s:
            fremd = s.get(Job, job_id)
            fremd.posting_snapshot_path = "data/job_postings/attrappe.html"
            s.add(fremd)
            s.commit()

    attrappe.status = "nachgeholt"
    attrappe.wirkung = _schreibt_pfad
    asyncio.run(_guard_anzeigentext(j, {"cv-match"}, {}, session))

    assert attrappe.aufrufe == [j.id]
    assert attrappe.threads[0] is not threading.current_thread()    # Worker-Thread, nicht Loop
    assert j.posting_snapshot_path == "data/job_postings/attrappe.html"   # neu gelesen


def test_guard_hebt_bei_fehlt_409_und_liest_trotzdem_neu(session, attrappe):
    from fastapi import HTTPException
    from sqlmodel import Session
    from app.db import engine
    from app.main import _guard_anzeigentext
    from app.models import Job

    j = _job_anlegen(session)

    def _schreibt_pfad(job_id):
        with Session(engine) as s:
            fremd = s.get(Job, job_id)
            fremd.posting_snapshot_path = "data/job_postings/versuch.html"
            s.add(fremd)
            s.commit()

    attrappe.wirkung = _schreibt_pfad
    with pytest.raises(HTTPException) as e:
        asyncio.run(_guard_anzeigentext(j, {"cv-erstellen"}, {}, session))
    assert e.value.status_code == 409 and str(e.value.detail).startswith("ANZEIGE_FEHLT: ")
    assert j.posting_snapshot_path == "data/job_postings/versuch.html"
