"""API-Tests für `app/routes_sicherung.py` (P2-52, Paket S1): `GET`/`POST /api/sicherung` und
`PATCH /api/sicherung/einstellungen`.

WICHTIG: main.py bindet diesen Router zu diesem Zeitpunkt (Paket S1) noch NICHT ein (das macht
die Hauptsession, s. Bau-Spec Abschnitt „Hauptsession"). Diese Tests hängen den Router deshalb
selbst in eine EIGENE `FastAPI()`-Instanz (`sicherung_client`-Fixture unten) statt die
`client`-Fixture aus `conftest.py` (die auf `app.main.app` aufsetzt) zu verwenden -- dadurch
laufen sie unabhängig von main.py und bleiben auch nach dessen Anbindung unverändert gültig
(Muster `test_coach_settings_api.py`).

Isolation: `app.db.DATA_DIR`/`DB_PATH` werden je Test per `monkeypatch` auf `tmp_path`
umgebogen -- `app/sicherung.py` löst ohne eigene Parameter (Router ruft es genau so auf) IMMER
darüber auf. Die autouse-Fixture setzt zusätzlich die modul-globalen Laufzeitwerte
(`_letzter_fehler`/`_takt_start`/`_task`/`_LOCK`) vor und nach jedem Test zurück -- dasselbe
Modulobjekt wie in `test_sicherung.py`, beide Dateien dürfen sich nicht gegenseitig
beeinflussen."""
import sqlite3
import threading
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _sicherung_globaler_zustand_isoliert():
    import app.sicherung as sicherung

    sicherung._letzter_fehler = None
    sicherung._takt_start = None
    sicherung._task = None
    sicherung._LOCK = threading.Lock()
    yield
    sicherung._letzter_fehler = None
    sicherung._takt_start = None
    sicherung._task = None
    sicherung._LOCK = threading.Lock()


def _kleine_db(pfad: Path, zeilen=("Erste Firma", "Zweite Firma")) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(pfad))
    conn.execute("CREATE TABLE company (id INTEGER PRIMARY KEY, name TEXT)")
    conn.executemany("INSERT INTO company (name) VALUES (?)", [(z,) for z in zeilen])
    conn.commit()
    conn.close()


@pytest.fixture()
def sicherung_client(tmp_path, monkeypatch):
    """Eigene, isolierte FastAPI-Instanz NUR mit dem Sicherung-Router (s. Moduldocstring)."""
    from app import db

    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "bewerbung.sqlite")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes_sicherung import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ── GET /api/sicherung ──────────────────────────────────────────────────────────────────────
def test_get_liefert_status_form_ohne_jede_sicherung(sicherung_client):
    r = sicherung_client.get("/api/sicherung")

    assert r.status_code == 200
    body = r.json()
    for feld in ("aktiv", "taeglich", "woechentlich", "monatlich", "ordner", "letzte", "anzahl",
                 "gesamtgroesse", "weitere", "laeuft", "letzter_fehler", "warnung"):
        assert feld in body
    assert body["letzte"] is None
    assert body["anzahl"] == 0
    assert body["laeuft"] is False
    assert body["letzter_fehler"] is None


def test_get_bleibt_200_auch_nach_fehlgeschlagenem_post(sicherung_client, tmp_path, monkeypatch):
    """`_als_zip_packen` (nicht `anlegen` selbst) wird kaputt gemacht -- so durchläuft der
    ECHTE `anlegen()`-Fehlerpfad (der `letzter_fehler` setzt), statt ihn durch einen Stub zu
    umgehen."""
    from app import db, sicherung

    _kleine_db(db.DB_PATH)

    def _kaputt(*args, **kwargs):
        raise RuntimeError("kaputt (Test)")

    monkeypatch.setattr(sicherung, "_als_zip_packen", _kaputt)
    sicherung_client.post("/api/sicherung")   # 500, hier bewusst ignoriert

    r = sicherung_client.get("/api/sicherung")

    assert r.status_code == 200
    assert r.json()["letzter_fehler"] is not None
    assert r.json()["warnung"] is not None


# ── POST /api/sicherung ("Jetzt sichern") ───────────────────────────────────────────────────
def test_post_legt_sicherung_an_und_liefert_neu(sicherung_client, tmp_path):
    from app import db

    _kleine_db(db.DB_PATH)

    r = sicherung_client.post("/api/sicherung")

    assert r.status_code == 200
    body = r.json()
    assert body["neu"]["datei"].startswith("bewerbung_")
    assert body["neu"]["datei"].endswith(".zip")
    assert body["neu"]["groesse"] > 0
    assert body["neu"]["zeitpunkt"]
    assert body["entfernt"] == []
    assert body["status"]["anzahl"] == 1
    assert body["status"]["letzte"]["datei"] == body["neu"]["datei"]
    assert body["status"]["letzter_fehler"] is None

    ordner = tmp_path / "backups" / "auto"
    assert (ordner / body["neu"]["datei"]).is_file()


def test_post_funktioniert_auch_bei_ausgeschalteter_automatik(sicherung_client, tmp_path):
    from app import db

    _kleine_db(db.DB_PATH)
    sicherung_client.patch("/api/sicherung/einstellungen", json={"aktiv": False})

    r = sicherung_client.post("/api/sicherung")

    assert r.status_code == 200
    assert r.json()["neu"]["datei"].startswith("bewerbung_")


def test_post_bei_belegter_sperre_ergibt_409(sicherung_client, tmp_path):
    from app import db, sicherung

    _kleine_db(db.DB_PATH)
    sicherung._LOCK.acquire()
    try:
        r = sicherung_client.post("/api/sicherung")
    finally:
        sicherung._LOCK.release()

    assert r.status_code == 409
    assert r.json()["detail"] == "Es läuft bereits eine Sicherung."


def test_post_bei_fehler_ergibt_500_mit_meldung_und_setzt_letzten_fehler(sicherung_client, tmp_path,
                                                                          monkeypatch):
    from app import db, sicherung

    _kleine_db(db.DB_PATH)

    def _kaputt(*args, **kwargs):
        raise RuntimeError("Testfehler beim Anlegen")

    monkeypatch.setattr(sicherung, "anlegen", _kaputt)

    r = sicherung_client.post("/api/sicherung")

    assert r.status_code == 500
    assert "Sicherung fehlgeschlagen" in r.json()["detail"]
    assert "Testfehler beim Anlegen" in r.json()["detail"]


# ── PATCH /api/sicherung/einstellungen ──────────────────────────────────────────────────────
def test_patch_einstellungen_speichert_und_liefert_status(sicherung_client):
    r = sicherung_client.patch("/api/sicherung/einstellungen",
                                json={"taeglich": 3, "aktiv": False})

    assert r.status_code == 200
    body = r.json()
    assert body["taeglich"] == 3
    assert body["aktiv"] is False
    assert body["woechentlich"] == 4   # unverändert (Teil-Speichern)


def test_patch_einstellungen_ungueltiger_wert_ergibt_422_mit_lesbarer_meldung(sicherung_client):
    r = sicherung_client.patch("/api/sicherung/einstellungen", json={"taeglich": 0})

    assert r.status_code == 422
    assert r.json()["detail"]


def test_patch_einstellungen_unbekannter_schluessel_ergibt_422(sicherung_client):
    r = sicherung_client.patch("/api/sicherung/einstellungen", json={"unbekannt": True})

    assert r.status_code == 422


def test_post_meldet_erfolg_auch_wenn_nur_das_ausduennen_scheitert(sicherung_client, monkeypatch):
    """Die Sicherung steht, nur das Ausdünnen danach scheitert: die Antwort darf nicht
    „fehlgeschlagen" lauten, sonst hält der Nutzer eine vorhandene Sicherung für verloren."""
    from app import db, sicherung

    _kleine_db(db.DB_PATH)

    def kaputt(*args, **kwargs):
        raise RuntimeError("Ausdünnen kaputt")

    monkeypatch.setattr(sicherung, "rotieren", kaputt)

    r = sicherung_client.post("/api/sicherung")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["neu"]["datei"].startswith("bewerbung_")
    assert body["entfernt"] == []


def test_patch_meldung_nennt_keinen_internen_schluessel(sicherung_client):
    r = sicherung_client.patch("/api/sicherung/einstellungen", json={"taeglich": 0})

    assert r.status_code == 422
    assert r.json()["detail"] == "Die Zahl der täglichen Sicherungen muss eine ganze Zahl zwischen 1 und 60 sein."
