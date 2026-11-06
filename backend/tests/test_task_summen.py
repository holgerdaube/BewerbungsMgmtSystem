"""Die Kacheln im Task-Center zählen alle Läufe, nicht die letzten 100 der Liste.

Vorher rechnete die Seite „Läufe gesamt“, „Fehlgeschlagen“ und die Kosten aus `/api/tasks?limit=100`, die Anzeige blieb bei
100 stehen, obwohl die Datenbank über 3000 Läufe hielt. EIGENE DATENBANK JE TEST, damit die Summen genau prüfbar sind.

Kein app.*-Import auf Modulebene (conftest.py-Konvention).
"""
import pytest


@pytest.fixture()
def api(tmp_path):
    from fastapi.testclient import TestClient
    from sqlmodel import Session, SQLModel, create_engine

    import app.main as main
    from app.db import get_session

    eng = create_engine("sqlite:///" + str(tmp_path / "t.sqlite"))
    SQLModel.metadata.create_all(eng)

    def _session():
        with Session(eng) as s:
            yield s

    main.app.dependency_overrides[get_session] = _session
    with Session(eng) as s:
        yield TestClient(main.app), s
    main.app.dependency_overrides.pop(get_session, None)


def _lauf(s, status="done", kosten=None, token=None):
    from app.models import AgentTask

    s.add(AgentTask(kind="jobsuche", status=status, prompt="p", cost_usd=kosten, tokens=token))


def test_leere_datenbank_liefert_nullen(api):
    client, _ = api
    assert client.get("/api/tasks/summen").json() == {"gesamt": 0, "fehlgeschlagen": 0, "kosten_usd": 0, "token": 0}


def test_summen_gehen_ueber_das_limit_der_liste_hinaus(api):
    client, s = api
    for _ in range(120):
        _lauf(s, kosten=0.5, token=10)
    for _ in range(3):
        _lauf(s, status="failed", kosten=None, token=None)
    s.commit()

    assert len(client.get("/api/tasks?limit=100").json()) == 100
    assert client.get("/api/tasks/summen").json() == {"gesamt": 123, "fehlgeschlagen": 3, "kosten_usd": 60.0, "token": 1200}


def test_adresse_faellt_nicht_in_die_einzelabfrage(api):
    """`/api/tasks/{task_id}` erwartet eine Zahl. Stünde die Summen-Route dahinter, käme hier 422."""
    client, _ = api
    assert client.get("/api/tasks/summen").status_code == 200
