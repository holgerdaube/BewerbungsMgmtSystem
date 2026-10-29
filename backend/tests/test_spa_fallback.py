"""P2-54 — Der SPA-Fallback (`main.spa`) liefert nur Dateien aus frontend/dist aus.

Befund 28.09.2026: Der Fallback baute `_DIST / full_path` ohne Eingrenzung. Im Worktree
nachgestellt: `GET /%2e%2e/%2e%2e/README.md` lieferte die Projektdatei, `GET /%2Fetc%2Fhosts`
eine Systemdatei. Im LAN-Modus (ohne Anmeldung) wären so die Datenbank, die Sicherungen und
~/.bewerbung_mgmt_secrets an /api/artifact vorbei abrufbar gewesen.

P2-64 (01.10.2026): Was `spa` ausliefert, trägt `Cache-Control: no-cache`. Ohne den Header
zeigte der Browser eine schon besuchte Adresse nach einem Build weiter mit der alten index.html,
deren Bundle gelöscht war. /assets (StaticFiles, gehashte Namen) bleibt zwischenspeicherbar.

Die echte Route gibt es nur, wenn frontend/dist beim Import existiert, in der CI also nicht. Die
Tests hängen `main.spa` deshalb an eine eigene Mini-App und binden `main._DIST` auf ein
tmp-Verzeichnis um; die Cache-Tests nehmen die echte Verdrahtung (`_oberflaeche_einhaengen`).
Die Anfragen laufen trotzdem durch Starlette, also mit derselben URL-Dekodierung wie im
Betrieb. App-Module nur funktionslokal importieren (s. conftest.py).
"""
from urllib.parse import quote

import pytest

INDEX = "<!doctype html><title>BMS</title>"
GEHEIM = "SQLite format 3 geheim"


@pytest.fixture()
def projekt(tmp_path, monkeypatch):
    import app.main as main

    dist = tmp_path / "frontend" / "dist"
    # assets/ wie im echten Build: Fehlt der Ordner, scheitert `assets/..` schon am Dateisystem,
    # und der Ausbruchstest über /assets/ bewiese nichts.
    (dist / "assets").mkdir(parents=True)
    (dist / "assets" / "app.js").write_text("//", encoding="utf-8")
    (dist / "index.html").write_text(INDEX, encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    db = tmp_path / "data" / "bewerbung.sqlite"
    db.parent.mkdir(parents=True)
    db.write_text(GEHEIM, encoding="utf-8")
    monkeypatch.setattr(main, "_DIST", dist)
    return tmp_path


@pytest.fixture()
def spa_client(projekt):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import app.main as main

    mini = FastAPI()
    mini.get("/{full_path:path}")(main.spa)
    return TestClient(mini)


@pytest.fixture()
def oberflaeche_client(projekt):
    """Wie im Betrieb: /assets per StaticFiles, alles Übrige per `spa`."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import app.main as main

    mini = FastAPI()
    main._oberflaeche_einhaengen(mini, projekt / "frontend" / "dist")
    return TestClient(mini)


@pytest.mark.parametrize("adresse, inhalt", [("/favicon.svg", "<svg/>"), ("/assets/app.js", "//")])
def test_datei_aus_dist_wird_ausgeliefert(spa_client, adresse, inhalt):
    r = spa_client.get(adresse)
    assert r.status_code == 200
    assert r.text == inhalt


@pytest.mark.parametrize("adresse", ["/", "/jobs/12", "/einstellungen"])
def test_client_route_bekommt_index(spa_client, adresse):
    r = spa_client.get(adresse)
    assert r.status_code == 200
    assert r.text == INDEX


def test_api_praefix_bleibt_404(spa_client):
    assert spa_client.get("/api/gibt-es-nicht").status_code == 404


@pytest.mark.parametrize("adresse", [
    "/%2e%2e/%2e%2e/data/bewerbung.sqlite",
    "/..%2f..%2fdata%2fbewerbung.sqlite",
    "/assets/%2e%2e/%2e%2e/%2e%2e/data/bewerbung.sqlite",
    "/%2e%2e%5c%2e%2e%5cdata%5cbewerbung.sqlite",   # Backslash-Trenner, greift unter Windows
])
def test_ausbruch_aus_dist_liefert_index(spa_client, adresse):
    r = spa_client.get(adresse)
    assert r.status_code == 200
    assert r.text == INDEX
    assert GEHEIM not in r.text


def test_absoluter_pfad_liefert_index(spa_client, projekt):
    """`/%2F…` (macOS, Linux) bzw. `/C%3A%5C…` (Windows) wird nach dem Dekodieren ein absoluter
    Pfad, den `_DIST / full_path` früher unverändert übernahm."""
    db = projekt / "data" / "bewerbung.sqlite"

    r = spa_client.get("/" + quote(str(db), safe=""))
    assert r.status_code == 200
    assert r.text == INDEX


def test_symlink_schleife_liefert_index(spa_client, projekt):
    """`resolve()` wirft bei einer Schleife unter Python 3.12 einen RuntimeError; kein 500."""
    schleife = projekt / "frontend" / "dist" / "schleife.js"
    try:
        schleife.symlink_to(schleife)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks lassen sich hier nicht anlegen (Windows ohne Entwicklermodus)")

    r = spa_client.get("/schleife.js")
    assert r.status_code == 200
    assert r.text == INDEX


def test_ueberlanger_name_liefert_index(spa_client):
    """`Path.is_file()` wirft bei einem Namen über 255 Zeichen, `os.path.isfile` nicht."""
    r = spa_client.get("/" + "A" * 300)
    assert r.status_code == 200
    assert r.text == INDEX


def test_unc_pfad_erreicht_das_dateisystem_nicht(spa_client, monkeypatch):
    """Windows: Ein Pfad mit zwei Backslashes am Anfang spräche schon beim Auflösen einen fremden
    Rechner per SMB an (s. test_artifact_security.py, gleicher Wächter). Unter macOS und Linux
    läuft der Test mit, beweist aber erst im Job backend-windows etwas."""
    import os

    original = os.path.realpath

    def waechter(pfad, *args, **kwargs):
        assert not str(pfad).startswith("\\\\"), f"UNC-Pfad erreichte resolve(): {pfad}"
        return original(pfad, *args, **kwargs)

    monkeypatch.setattr(os.path, "realpath", waechter)
    r = spa_client.get("/%5C%5Cbms-test.invalid%5Cfreigabe%5Cbericht.html")
    assert r.status_code == 200
    assert r.text == INDEX


# ── P2-64: Cache-Control ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("adresse", [
    "/", "/outreach", "/jobs/12", "/index.html", "/gibt-es-nicht.png",
    "/%2e%2e/%2e%2e/data/bewerbung.sqlite",
])
def test_index_wird_auf_jedem_weg_nachgefragt(oberflaeche_client, adresse):
    """Client-Route, direkter Aufruf und Rückfall: Ohne den Header schätzt der Browser die Frische
    aus Last-Modified und zeigt nach einem Build die alte index.html."""
    r = oberflaeche_client.get(adresse)
    assert r.status_code == 200
    assert r.text == INDEX
    assert r.headers["cache-control"] == "no-cache"


def test_datei_direkt_in_dist_wird_nachgefragt(oberflaeche_client):
    """Icons aus frontend/public heißen nach jedem Build wie vorher."""
    r = oberflaeche_client.get("/favicon.svg")
    assert r.status_code == 200
    assert r.text == "<svg/>"
    assert r.headers["cache-control"] == "no-cache"


def test_assets_bleiben_zwischenspeicherbar(oberflaeche_client):
    """Gehashte Namen dürfen im Cache bleiben. Die 304 belegt zugleich, dass /assets über
    StaticFiles läuft: `spa` (FileResponse) beantwortet Nachfragen immer mit der ganzen Datei."""
    r = oberflaeche_client.get("/assets/app.js")
    assert r.status_code == 200
    assert r.text == "//"
    kopf = r.headers.get("cache-control", "")
    assert "no-cache" not in kopf and "no-store" not in kopf

    nachfrage = oberflaeche_client.get("/assets/app.js", headers={"If-None-Match": r.headers["etag"]})
    assert nachfrage.status_code == 304
