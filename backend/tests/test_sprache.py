"""P2-88: Sprache der Oberfläche. Bestand bleibt Deutsch, eine neue Datenbank gilt als „noch nie gewählt“,
und der Endpunkt lässt die Suchprofil-Datei in Ruhe.

App-Module nur funktionslokal importieren (s. conftest.py).
"""
import pytest
from sqlalchemy import create_engine, text
from sqlmodel import Session, SQLModel


@pytest.fixture
def leer():
    """Tabelle ohne Zeile, wie nach dem ersten Start. Andere Tests dürfen keine Sprache hinterlassen."""
    from app.db import engine, init_db
    from app.models import SuchEinstellung
    init_db()
    with Session(engine) as s:
        e = s.get(SuchEinstellung, 1)
        vorher = e.sprache if e else None
        if e:
            e.sprache = ""
            s.add(e)
            s.commit()
    yield
    with Session(engine) as s:
        e = s.get(SuchEinstellung, 1)
        if e and vorher is not None:
            e.sprache = vorher
            s.add(e)
            s.commit()


def _client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def _alte_datenbank(pfad):
    """`sucheinstellung` ohne Spalte `sprache`, mit einer vorhandenen Zeile (Stand vor P2-88)."""
    eng = create_engine(f"sqlite:///{pfad}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE sucheinstellung (id INTEGER PRIMARY KEY, min_mitarbeiter INTEGER)"))
        c.execute(text("INSERT INTO sucheinstellung (id, min_mitarbeiter) VALUES (1, 100)"))
    return eng


def test_bestand_bleibt_deutsch(tmp_path, monkeypatch):
    from app import db
    eng = _alte_datenbank(tmp_path / "alt.sqlite")
    monkeypatch.setattr(db, "engine", eng)
    db._ensure_columns()
    with eng.connect() as c:
        assert c.execute(text("SELECT sprache FROM sucheinstellung WHERE id = 1")).scalar() == "de"


def test_neue_datenbank_gilt_als_nicht_gewaehlt(tmp_path, monkeypatch):
    from app import models, sprache
    eng = create_engine(f"sqlite:///{tmp_path / 'neu.sqlite'}")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(models.SuchEinstellung(id=1))
        s.commit()
    monkeypatch.setattr(sprache, "engine", eng)
    assert sprache.gespeichert() == ""
    assert sprache.aktuell() == "de"


def test_aktuell_wirft_nie_ohne_tabelle(tmp_path, monkeypatch):
    from app import sprache
    monkeypatch.setattr(sprache, "engine", create_engine(f"sqlite:///{tmp_path / 'leer.sqlite'}"))
    assert sprache.gespeichert() == ""
    assert sprache.aktuell() == "de"


def test_unbekannter_wert_in_der_datenbank_gilt_als_standard(leer):
    from app import sprache
    from app.db import engine
    from app.main import _einstellungen_singleton
    with Session(engine) as s:
        e = _einstellungen_singleton(s)
        e.sprache = "xx"
        s.add(e)
        s.commit()
    assert sprache.aktuell() == "de"


def test_get_ohne_wahl(leer):
    antwort = _client().get("/api/sprache").json()
    assert antwort == {"sprache": "de", "gewaehlt": False, "angebot": ["de", "en"]}


def test_put_setzt_die_sprache(leer):
    client = _client()
    assert client.put("/api/sprache", json={"sprache": "en"}).json()["sprache"] == "en"
    antwort = client.get("/api/sprache").json()
    assert antwort["sprache"] == "en" and antwort["gewaehlt"] is True


@pytest.mark.parametrize("wert", ["fr", "", None, "EN"])
def test_put_lehnt_unbekannte_sprache_ab(leer, wert):
    assert _client().put("/api/sprache", json={"sprache": wert}).status_code == 422


def test_put_laesst_die_suchprofil_datei_unberuehrt(leer):
    from pipeline import suchprofil
    pfad = suchprofil.SUCHPROFILE_PATH
    client = _client()
    client.get("/api/einstellungen")       # legt Zeile und Datei an, falls beides fehlt
    vorher = pfad.read_bytes() if pfad.exists() else None
    stand = pfad.stat().st_mtime_ns if pfad.exists() else None
    assert client.put("/api/sprache", json={"sprache": "en"}).status_code == 200
    assert (pfad.read_bytes() if pfad.exists() else None) == vorher
    assert (pfad.stat().st_mtime_ns if pfad.exists() else None) == stand
