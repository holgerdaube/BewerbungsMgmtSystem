"""P2-41 — Bewerbungspaket: Beirats-Check und Anschreiben optional (Bau-Spec
tasks/spec_p2-41_bewerbungspaket_optional.md, Abschnitt 4.5).

Deckt ab:
  1.–4. `agent_runner.rezept_aufloesen()` als reine Funktion: Pflichtkern ohne Baustein, Baustein
     per Param aktiviert, Standardwert aus den Einstellungen greift (und ein ausdrücklicher
     Param schlägt ihn), Rezepte ohne optional-Block (`tageslauf`) bleiben unverändert.
  5.–7. `POST /api/tasks` mit `kind="bewerbungspaket"`: Standard aus liefert die 3 Kern-Tasks,
     `params.mit_anschreiben=true` liefert 4 (mit `depends_on`-Kette), ein in den Einstellungen
     auf `True` gesetzter Standard wirkt genauso ohne expliziten Param.
  8.–10. `GET`/`PATCH /api/einstellungen`: frische wie alte Zeile liefern `unterlagen ==
     {"anschreiben": False}`, PATCH speichert und übersteht ein PATCH auf ein anderes Feld,
     PATCH validiert unbekannte Bausteine und Nicht-Booleans mit 422.
  11. `GET /api/task-kinds`: kein Rezept „deepdive“ mehr, `bewerbungspaket` trägt die
     `optional`-Liste der Task-Arten.

WICHTIG — Test-Isolation (PFLICHT, Bau-Spec Abschnitt 4.5): `PATCH /api/einstellungen` ruft
`suchprofil.regenerieren(e)` und schreibt damit die echte `config/suchprofile.yaml`. Das
autouse-Fixture unten ist 1:1 aus `test_einstellungen_portale.py` (Z. 44 ff.) übernommen — JEDER
Test in dieser Datei bekommt automatisch eine tmp-Kopie, auch die Tests, die nur lesen (`GET`)
oder eine Kette starten (`POST /api/tasks` löst intern `_einstellungen_singleton()` auf, die bei
einer fehlenden Zeile aus derselben YAML seedet).

`SuchEinstellung` ist wie in `test_einstellungen_portale.py` ein echter Singleton (id=1) über die
GANZE session-weite tmp-DB hinweg (conftest.py::_db_ready, scope="session") — KEIN Rollback
zwischen Tests. Jeder Test, der eine bestimmte Ausgangslage braucht, setzt sie deshalb selbst
über `_reset_einstellungen()`.

App-Module werden — wie in der gesamten Suite — NIE auf Modulebene importiert, nur innerhalb der
Testfunktionen/Fixtures."""
import json
import uuid

import pytest


@pytest.fixture(autouse=True)
def _suchprofile_yaml_isoliert(tmp_path, monkeypatch):
    """PFLICHT (übernommen 1:1 aus test_einstellungen_portale.py, s. Moduldocstring): niemals die
    echte config/suchprofile.yaml lesen oder beschreiben. Jeder Test bekommt automatisch eine
    eigene, minimale YAML-Kopie in `tmp_path` statt der echten Datei."""
    from pipeline import suchprofil

    pfad = tmp_path / "suchprofile.yaml"
    pfad.write_text(suchprofil.MARKER + "\nportale_technik: {}\n", encoding="utf-8")
    monkeypatch.setattr(suchprofil, "SUCHPROFILE_PATH", pfad)
    return pfad


def _reset_einstellungen(session):
    """Löscht die Singleton-Zeile (falls vorhanden) — macht jeden Test unabhängig von der
    Ausführungsreihenfolge innerhalb dieser Datei (s. Moduldocstring)."""
    from app.models import SuchEinstellung

    vorhanden = session.get(SuchEinstellung, 1)
    if vorhanden:
        session.delete(vorhanden)
        session.commit()


def _job_anlegen(session, match_score=None, status="Neu"):
    """Muster `test_low_match_gate.py::_job_anlegen` — Standard `match_score=None`: unbewertete
    Jobs lösen den Low-Match-Guard NIE aus (s. `main.py::_guard_low_match`), die Kettentests
    hier prüfen die Schritt-/Label-Auflösung, nicht den Guard."""
    from app.models import Job

    j = Job(company_name=f"P241 AG {uuid.uuid4().hex[:8]}", title="Teststelle",
            match_score=match_score, status=status, dedup_key=uuid.uuid4().hex)
    session.add(j)
    session.commit()
    session.refresh(j)
    return j


# ── 1.–4. rezept_aufloesen() als reine Funktion ─────────────────────────────────────────────
def test_rezept_aufloesen_kern_ohne_baustein():
    from app import agent_runner

    schritte, label = agent_runner.rezept_aufloesen("bewerbungspaket", {}, {})
    assert schritte == ["firma-pruefen", "cv-match", "cv-erstellen"]
    assert label == "Bewerbungspaket (Firma + CV)"


def test_rezept_aufloesen_mit_anschreiben_per_param():
    from app import agent_runner

    schritte, label = agent_runner.rezept_aufloesen("bewerbungspaket", {"mit_anschreiben": True}, {})
    assert schritte == ["firma-pruefen", "cv-match", "cv-erstellen", "anschreiben-erstellen"]
    assert label == "Bewerbungspaket (Firma + CV + Anschreiben)"


def test_rezept_aufloesen_standard_greift_und_param_schlaegt_ihn():
    from app import agent_runner

    # Param fehlt -> der Standard aus den Einstellungen entscheidet.
    schritte_standard, _ = agent_runner.rezept_aufloesen(
        "bewerbungspaket", {}, {"anschreiben": True})
    assert schritte_standard == ["firma-pruefen", "cv-match", "cv-erstellen", "anschreiben-erstellen"]

    # Ausdrücklicher Param False schlägt den Standard True.
    schritte_param, _ = agent_runner.rezept_aufloesen(
        "bewerbungspaket", {"mit_anschreiben": False}, {"anschreiben": True})
    assert schritte_param == ["firma-pruefen", "cv-match", "cv-erstellen"]


def test_rezept_aufloesen_tageslauf_unveraendert():
    from app import agent_runner

    rec = agent_runner.RECIPES["tageslauf"]
    schritte, label = agent_runner.rezept_aufloesen("tageslauf", {"mit_irgendwas": True}, {})
    assert schritte == rec["steps"]
    assert label == rec["label"]


# ── 5.–7. POST /api/tasks mit kind="bewerbungspaket" ────────────────────────────────────────
def test_post_tasks_bewerbungspaket_ohne_param_liefert_drei_kettenglieder(session, client):
    _reset_einstellungen(session)      # frische Zeile -> Standard aus
    j = _job_anlegen(session)

    r = client.post("/api/tasks", json={"kind": "bewerbungspaket", "job_id": j.id})

    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "Bewerbungspaket (Firma + CV)"
    assert [t["kind"] for t in body["tasks"]] == ["firma-pruefen", "cv-match", "cv-erstellen"]
    assert [t["chain_pos"] for t in body["tasks"]] == [1, 2, 3]

    # enqueue() ist ohne laufenden Worker (kein FastAPI-Lifespan im TestClient, s. conftest.py)
    # ein No-op — die Zeilen bleiben "queued" und lassen sich normal über GET /api/tasks lesen.
    gelistet = client.get(f"/api/tasks?job_id={j.id}").json()
    assert len(gelistet) == 3
    assert all(t["chain_label"] == "Bewerbungspaket (Firma + CV)" for t in gelistet)
    assert all(t["status"] == "queued" for t in gelistet)


def test_post_tasks_bewerbungspaket_mit_anschreiben_liefert_vier_kettenglieder(session, client):
    _reset_einstellungen(session)
    j = _job_anlegen(session)

    r = client.post("/api/tasks", json={
        "kind": "bewerbungspaket", "job_id": j.id, "params": {"mit_anschreiben": True},
    })

    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "Bewerbungspaket (Firma + CV + Anschreiben)"
    tasks = body["tasks"]
    assert [t["kind"] for t in tasks] == [
        "firma-pruefen", "cv-match", "cv-erstellen", "anschreiben-erstellen"]
    assert tasks[3]["depends_on"] == tasks[2]["id"]


def test_post_tasks_bewerbungspaket_nutzt_standard_aus_einstellungen(session, client):
    from app.models import SuchEinstellung

    _reset_einstellungen(session)
    # Standard in den Einstellungen auf "an" — ohne expliziten Param muss das genauso wirken
    # wie params.mit_anschreiben=true oben.
    session.add(SuchEinstellung(id=1, unterlagen_json=json.dumps({"anschreiben": True})))
    session.commit()
    j = _job_anlegen(session)

    r = client.post("/api/tasks", json={"kind": "bewerbungspaket", "job_id": j.id})

    assert r.status_code == 200
    assert [t["kind"] for t in r.json()["tasks"]] == [
        "firma-pruefen", "cv-match", "cv-erstellen", "anschreiben-erstellen"]


# ── 8.–10. GET/PATCH /api/einstellungen — Feld unterlagen ───────────────────────────────────
def test_get_liefert_unterlagen_false_bei_frischer_und_bei_altzeile(session, client):
    from app.models import SuchEinstellung

    _reset_einstellungen(session)
    r_frisch = client.get("/api/einstellungen")
    assert r_frisch.status_code == 200
    assert r_frisch.json()["unterlagen"] == {"anschreiben": False}

    # Alt-Zeile (Zustand nach ALTER TABLE ... DEFAULT '{}', s. app/db.py::_ADD_COLUMNS) — die
    # Auffüllung muss auch greifen, wenn die Zeile bereits existiert und nicht neu geseedet wird.
    _reset_einstellungen(session)
    session.add(SuchEinstellung(id=1, unterlagen_json="{}"))
    session.commit()
    r_alt = client.get("/api/einstellungen")
    assert r_alt.status_code == 200
    assert r_alt.json()["unterlagen"] == {"anschreiben": False}


def test_patch_unterlagen_speichert_und_uebersteht_anderes_patch(session, client):
    _reset_einstellungen(session)

    r1 = client.patch("/api/einstellungen", json={"unterlagen": {"anschreiben": True}})
    assert r1.status_code == 200
    assert r1.json()["unterlagen"] == {"anschreiben": True}
    assert client.get("/api/einstellungen").json()["unterlagen"] == {"anschreiben": True}

    # Ein Save eines ANDEREN Feldes darf den gespeicherten Standard nicht zurücksetzen (Muster
    # modelle/portale, s. update_einstellungen-Docstring).
    r2 = client.patch("/api/einstellungen", json={"modelle": {"cv-match": "opus"}})
    assert r2.status_code == 200
    assert r2.json()["unterlagen"] == {"anschreiben": True}


def test_patch_unterlagen_validiert_schluessel_und_typ(session, client):
    _reset_einstellungen(session)

    r1 = client.patch("/api/einstellungen", json={"unterlagen": {"beirat": True}})
    assert r1.status_code == 422

    r2 = client.patch("/api/einstellungen", json={"unterlagen": {"anschreiben": "ja"}})
    assert r2.status_code == 422

    # Beide Fehlversuche dürfen nichts verändert haben.
    assert client.get("/api/einstellungen").json()["unterlagen"] == {"anschreiben": False}


# ── 11. GET /api/task-kinds ──────────────────────────────────────────────────────────────────
def test_task_kinds_ohne_deepdive_bewerbungspaket_traegt_optional_liste(client):
    r = client.get("/api/task-kinds")
    assert r.status_code == 200
    recipes = {rec["kind"]: rec for rec in r.json()["recipes"]}
    assert "deepdive" not in recipes
    assert recipes["bewerbungspaket"]["optional"] == ["anschreiben-erstellen"]
