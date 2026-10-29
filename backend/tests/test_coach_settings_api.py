"""API-Tests für `app/routes_coach_settings.py` (Phase 82, Arbeitspaket A1): `GET`/`PUT`/
`POST /test`/`POST /serverpfad` unter `/api/settings/coach`.

WICHTIG: `app/main.py` bindet diesen Router zum jetzigen Zeitpunkt (Arbeitspaket A1) noch
NICHT ein (das macht die Hauptsession, s. Bau-Spec Abschnitt 6). Diese Tests hängen den Router
deshalb selbst in eine EIGENE `FastAPI()`-Instanz (`coach_client`-Fixture unten) statt die
`client`-Fixture aus `conftest.py` (die auf `app.main.app` aufsetzt) zu verwenden — dadurch
laufen sie unabhängig von main.py und bleiben auch nach dessen Anbindung unverändert gültig.

SICHERHEITSREGEL: wie in `test_coach_settings.py` werden `SETTINGS_FILE`/`ENV_FILE`/
`HTPASSWD_FILE` je Test per `monkeypatch` auf `tmp_path` umgelenkt — das echte
`~/.bewerbung_mgmt_secrets/` wird NIE angefasst.

lftp-/httpx-Netzzugriffe (`POST /test`, `POST /serverpfad`) werden auf Modulebene gemockt
(`pipeline.coach_settings.sftp_lauf` bzw. `httpx.get`) — dieselbe Grenze wie in den
IMAP-/Gmail-Tests aus `test_mail_settings_api.py`: kein echter Server, kein echtes lftp.
"""
import pytest


@pytest.fixture()
def coach_client(tmp_path, monkeypatch):
    """Eigene, isolierte FastAPI-Instanz NUR mit dem Coach-Settings-Router — s. Moduldocstring.
    Alle drei SECRETS_DIR-Konstanten werden auf `tmp_path` umgelenkt (Muster
    `test_coach_settings.py::coach_secrets`)."""
    import pipeline.coach_settings as coach_settings

    monkeypatch.setattr(coach_settings, "SETTINGS_FILE", tmp_path / "coach_settings.json")
    monkeypatch.setattr(coach_settings, "ENV_FILE", tmp_path / "coach_sftp.env")
    monkeypatch.setattr(coach_settings, "HTPASSWD_FILE", tmp_path / "coach_htpasswd")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes_coach_settings import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


PAYLOAD_VOLLSTAENDIG = {
    "aktiv": True,
    "site_url": "https://coach.meine-domain.de",
    "sftp_host": "access-xyz.webspace-host.com",
    "sftp_user": "u1234567",
    "sftp_password": "geheimes-sftp-passwort",
    "sftp_dir": "/coach",
    "authuserfile": "/srv/www/coach/.htpasswd",
    "coach_user": "berater",
    # Dummy-Werte bewusst OHNE Ziffern/Großbuchstaben: "coach-passwort-123" schlug im
    # gitleaks-Secret-Scan der CI als generic-api-key an (Entropie 3,6 — Fund 12.08.2026).
    # Lieber harmlose Testdaten als eine Ausnahme in .gitleaks.toml, die den Scan aufweicht.
    "coach_password": "coach-passwort",
}


class _FakeResponse:
    """Winziger httpx.Response-Ersatz -- `serverpfad_ermitteln` liest nur `.text`."""

    def __init__(self, text):
        self.text = text


def _fake_sftp_lauf(aufrufe, verzeichnis_inhalt="", scheitere_bei=None):
    """Baut einen Mock fuer `coach_settings.sftp_lauf`, der jeden Aufruf (Kommandoliste)
    protokolliert -- damit Tests die AUFRUF-REIHENFOLGE pruefen koennen (Guard -> Upload ->
    Loeschen). `scheitere_bei` laesst den Aufruf, dessen erstes Kommando diesen Teilstring
    enthaelt, mit RuntimeError scheitern (simuliert einen lftp-Fehlschlag an genau dieser
    Stelle, z. B. beim Upload)."""

    def _fake(data, befehle, timeout=60):
        aufrufe.append(list(befehle))
        befehl = befehle[0]
        if scheitere_bei and scheitere_bei in befehl:
            raise RuntimeError(f"lftp-Fehler bei: {befehl}")
        if befehl.startswith("cls -1 -a"):
            return verzeichnis_inhalt
        return ""

    return _fake


# ── 6. GET liefert nie Passwoerter, *_set-Flags korrekt ─────────────────────────────────
def test_get_ohne_konfiguration_liefert_exakte_leer_antwort(coach_client):
    r = coach_client.get("/api/settings/coach")
    assert r.status_code == 200
    assert r.json() == {
        "aktiv": False, "site_url": "", "sftp_host": "", "sftp_user": "", "sftp_dir": "",
        "authuserfile": "", "coach_user": "",
        "sftp_password_set": False, "coach_password_set": False, "quelle": "leer",
    }


def test_get_liefert_nie_passwoerter_aber_set_flags_korrekt(coach_client):
    r_put = coach_client.put("/api/settings/coach", json=PAYLOAD_VOLLSTAENDIG)
    assert r_put.status_code == 200

    r = coach_client.get("/api/settings/coach")
    assert r.status_code == 200
    body = r.json()
    assert "sftp_password" not in body
    assert "coach_password" not in body
    assert body["sftp_password_set"] is True
    assert body["coach_password_set"] is True
    assert body["quelle"] == "settings"


# ── 7. PUT-Validierung ────────────────────────────────────────────────────────────────────
def test_put_unbekanntes_feld_liefert_422(coach_client):
    r = coach_client.put("/api/settings/coach", json={"unfug": 1})
    assert r.status_code == 422
    assert "unfug" in r.json()["detail"]


def test_put_http_url_liefert_422(coach_client):
    r = coach_client.put("/api/settings/coach", json={"site_url": "http://unsicher.example"})
    assert r.status_code == 422
    assert "https://" in r.json()["detail"]


def test_put_relativer_sftp_dir_liefert_422(coach_client):
    r = coach_client.put("/api/settings/coach", json={"sftp_dir": "coach"})
    assert r.status_code == 422
    assert "sftp_dir" in r.json()["detail"]


def test_put_relativer_authuserfile_liefert_422(coach_client):
    r = coach_client.put("/api/settings/coach", json={"authuserfile": "home/coach/.htpasswd"})
    assert r.status_code == 422
    assert "authuserfile" in r.json()["detail"]


def test_put_site_url_trailing_slash_wird_abgeschnitten(coach_client):
    r = coach_client.put("/api/settings/coach", json={"site_url": "https://coach.example/"})
    assert r.status_code == 200
    assert r.json()["site_url"] == "https://coach.example"


def test_put_leeres_sftp_passwort_behaelt_gespeichertes(coach_client):
    import pipeline.coach_settings as coach_settings

    basis = {"aktiv": False, "sftp_host": "host.example", "sftp_user": "u1",
             "sftp_password": "erstes-passwort", "sftp_dir": "/coach"}
    r1 = coach_client.put("/api/settings/coach", json=basis)
    assert r1.status_code == 200
    assert r1.json()["sftp_password_set"] is True

    r2 = coach_client.put("/api/settings/coach", json={**basis, "sftp_password": ""})
    assert r2.status_code == 200
    assert r2.json()["sftp_password_set"] is True
    assert coach_settings.load_settings()["sftp_password"] == "erstes-passwort"


def test_put_aktiv_true_unvollstaendig_liefert_422_mit_feldliste(coach_client):
    r = coach_client.put("/api/settings/coach",
                          json={"aktiv": True, "site_url": "https://coach.example"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "Zum Aktivieren fehlen noch" in detail
    assert "sftp_host" in detail
    assert "Coach-Passwort" in detail


def test_put_vollstaendige_konfiguration_aktiv_true_geht_durch(coach_client):
    r = coach_client.put("/api/settings/coach", json=PAYLOAD_VOLLSTAENDIG)
    assert r.status_code == 200
    body = r.json()
    assert body["aktiv"] is True
    assert body["site_url"] == "https://coach.meine-domain.de"
    assert body["sftp_password_set"] is True
    assert body["coach_password_set"] is True
    assert body["coach_user"] == "berater"
    assert body["quelle"] == "settings"


# ── 8. coach_user geaendert ohne coach_password ──────────────────────────────────────────
def test_put_coach_user_geaendert_ohne_passwort_liefert_422(coach_client):
    r1 = coach_client.put("/api/settings/coach",
                           json={"aktiv": False, "coach_user": "erst",
                                 "coach_password": "start-passwort"})
    assert r1.status_code == 200

    r2 = coach_client.put("/api/settings/coach", json={"aktiv": False, "coach_user": "geaendert"})
    assert r2.status_code == 422
    assert "Benutzername geändert" in r2.json()["detail"]


def test_put_coach_user_unveraendert_ohne_passwort_ist_ok(coach_client):
    r1 = coach_client.put("/api/settings/coach",
                           json={"aktiv": False, "coach_user": "gleich",
                                 "coach_password": "start-passwort"})
    assert r1.status_code == 200

    # gleicher Benutzername, andere Felder aendern, KEIN neues Passwort -- darf NICHT scheitern:
    r2 = coach_client.put("/api/settings/coach",
                           json={"aktiv": False, "coach_user": "gleich", "sftp_host": "neu.example"})
    assert r2.status_code == 200
    assert r2.json()["sftp_host"] == "neu.example"
    assert r2.json()["coach_user"] == "gleich"


def test_put_coach_password_zu_lang_liefert_422(coach_client):
    r = coach_client.put("/api/settings/coach",
                          json={"aktiv": False, "coach_user": "berater",
                                "coach_password": "x" * 73})
    assert r.status_code == 422


# ── 9. POST /test ─────────────────────────────────────────────────────────────────────────
def test_post_test_erfolg_meldet_anzahl_eintraege(coach_client, monkeypatch):
    import pipeline.coach_settings as coach_settings

    monkeypatch.setattr(coach_settings, "sftp_lauf",
                         lambda data, befehle, timeout=60: "a.txt\nb.txt\nc.txt")

    r = coach_client.post("/api/settings/coach/test", json={
        "sftp_host": "host.example", "sftp_user": "u1", "sftp_password": "pw", "sftp_dir": "/coach",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "3 Einträge" in body["meldung"]
    assert "/coach" in body["meldung"]


def test_post_test_leeres_verzeichnis_meldet_leer(coach_client, monkeypatch):
    import pipeline.coach_settings as coach_settings

    monkeypatch.setattr(coach_settings, "sftp_lauf", lambda data, befehle, timeout=60: "")

    r = coach_client.post("/api/settings/coach/test", json={
        "sftp_host": "host.example", "sftp_user": "u1", "sftp_password": "pw", "sftp_dir": "/coach",
    })
    assert r.status_code == 200
    assert "(leer)" in r.json()["meldung"]


def test_post_test_nutzt_gespeicherte_werte_wenn_payload_leer(coach_client, monkeypatch):
    import pipeline.coach_settings as coach_settings

    r_put = coach_client.put("/api/settings/coach", json={
        "aktiv": False, "sftp_host": "gespeichert.example", "sftp_user": "u-gespeichert",
        "sftp_password": "pw-gespeichert", "sftp_dir": "/coach",
    })
    assert r_put.status_code == 200

    aufrufe = []
    monkeypatch.setattr(coach_settings, "sftp_lauf",
                         lambda data, befehle, timeout=60: aufrufe.append(dict(data)) or "")

    r = coach_client.post("/api/settings/coach/test", json={})
    assert r.status_code == 200
    assert aufrufe[0]["sftp_host"] == "gespeichert.example"
    assert aufrufe[0]["sftp_password"] == "pw-gespeichert"


def test_post_test_ohne_sftp_dir_liefert_400(coach_client):
    r = coach_client.post("/api/settings/coach/test", json={"sftp_host": "h", "sftp_user": "u"})
    assert r.status_code == 400


def test_post_test_fehlschlag_liefert_400_gefiltert_ohne_leak(coach_client, monkeypatch):
    import pipeline.coach_settings as coach_settings

    def _boom(data, befehle, timeout=60):
        raise RuntimeError(
            "cd sftp://u1:geheimespasswort@host.example: Login failed\n"
            "Verbindung zum Server fehlgeschlagen."
        )
    monkeypatch.setattr(coach_settings, "sftp_lauf", _boom)

    r = coach_client.post("/api/settings/coach/test", json={
        "sftp_host": "host.example", "sftp_user": "u1",
        "sftp_password": "geheimespasswort", "sftp_dir": "/coach",
    })
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "sftp://" not in detail
    assert "geheimespasswort" not in detail
    assert "Verbindung zum Server fehlgeschlagen." in detail


# ── 9. POST /serverpfad ───────────────────────────────────────────────────────────────────
SERVERPFAD_PAYLOAD = {
    "site_url": "https://coach.example.de", "sftp_host": "h", "sftp_user": "u",
    "sftp_password": "pw", "sftp_dir": "/coach",
}


def test_post_serverpfad_erfolg(coach_client, monkeypatch):
    import httpx
    import pipeline.coach_settings as coach_settings

    aufrufe = []
    monkeypatch.setattr(coach_settings, "sftp_lauf", _fake_sftp_lauf(aufrufe))
    monkeypatch.setattr(
        httpx, "get",
        lambda url, timeout=15, follow_redirects=True:
            _FakeResponse("davor BMSPFAD:/srv/www/coach:ENDE danach"),
    )

    r = coach_client.post("/api/settings/coach/serverpfad", json=SERVERPFAD_PAYLOAD)
    assert r.status_code == 200
    assert r.json() == {"authuserfile": "/srv/www/coach/.htpasswd", "serverpfad": "/srv/www/coach"}

    # Aufruf-Reihenfolge: Guard (cls -1 -a) -> Upload (put) -> Loeschen (rm -f):
    assert aufrufe[0][0].startswith("cls -1 -a")
    assert aufrufe[1][0].startswith("put ")
    assert aufrufe[2][0].startswith("rm -f")


def test_post_serverpfad_verzeichnis_nicht_leer_liefert_409(coach_client, monkeypatch):
    import pipeline.coach_settings as coach_settings

    aufrufe = []
    monkeypatch.setattr(
        coach_settings, "sftp_lauf",
        _fake_sftp_lauf(aufrufe, verzeichnis_inhalt=".\n..\nirgendeine-datei.txt"),
    )

    r = coach_client.post("/api/settings/coach/serverpfad", json=SERVERPFAD_PAYLOAD)
    assert r.status_code == 409
    assert "bereits Dateien" in r.json()["detail"]
    assert len(aufrufe) == 1   # nur der Guard -- kein Upload, kein rm -f noetig


def test_post_serverpfad_kein_php_liefert_400_und_loescht_probe_datei_trotzdem(coach_client, monkeypatch):
    import httpx
    import pipeline.coach_settings as coach_settings

    aufrufe = []
    monkeypatch.setattr(coach_settings, "sftp_lauf", _fake_sftp_lauf(aufrufe))
    monkeypatch.setattr(
        httpx, "get",
        lambda url, timeout=15, follow_redirects=True:
            _FakeResponse("keine PHP-Ausfuehrung, nur der Quelltext ohne Marker"),
    )

    r = coach_client.post("/api/settings/coach/serverpfad", json=SERVERPFAD_PAYLOAD)
    assert r.status_code == 400
    assert "manuell eintragen" in r.json()["detail"]
    # Probe-Datei wird AUCH im Fehlerfall geloescht (finally-Block in serverpfad_ermitteln):
    assert len(aufrufe) == 3
    assert aufrufe[-1][0].startswith("rm -f")


def test_post_serverpfad_upload_fehler_versucht_trotzdem_aufzuraeumen(coach_client, monkeypatch):
    import pipeline.coach_settings as coach_settings

    aufrufe = []
    monkeypatch.setattr(coach_settings, "sftp_lauf",
                         _fake_sftp_lauf(aufrufe, scheitere_bei="put "))

    r = coach_client.post("/api/settings/coach/serverpfad", json=SERVERPFAD_PAYLOAD)
    assert r.status_code == 400

    # Aufrufe: Guard (ok), Upload (wirft), Loeschen (wird TROTZDEM versucht):
    assert aufrufe[0][0].startswith("cls -1 -a")
    assert aufrufe[1][0].startswith("put ")
    assert aufrufe[-1][0].startswith("rm -f")


# ── 10. Regressionstest: niemals sftp:// in einer Fehlermeldung (Leak 10.08.2026) ────────
def test_fehlermeldungen_enthalten_niemals_sftp_url_oder_passwort(coach_client, monkeypatch):
    import pipeline.coach_settings as coach_settings

    def _boom(data, befehle, timeout=60):
        raise RuntimeError(
            "lftp: cd sftp://geheimerbenutzer:geheimespasswort@bad.example.com: "
            "Connection refused\nkeine weitere Information."
        )
    monkeypatch.setattr(coach_settings, "sftp_lauf", _boom)

    r_test = coach_client.post("/api/settings/coach/test", json={
        "sftp_host": "bad.example.com", "sftp_user": "geheimerbenutzer",
        "sftp_password": "geheimespasswort", "sftp_dir": "/coach",
    })
    assert r_test.status_code == 400
    assert "sftp://" not in r_test.json()["detail"]
    assert "geheimespasswort" not in r_test.json()["detail"]

    r_pfad = coach_client.post("/api/settings/coach/serverpfad", json={
        "site_url": "https://coach.example.de", "sftp_host": "bad.example.com",
        "sftp_user": "geheimerbenutzer", "sftp_password": "geheimespasswort", "sftp_dir": "/coach",
    })
    assert r_pfad.status_code == 400
    assert "sftp://" not in r_pfad.json()["detail"]
    assert "geheimespasswort" not in r_pfad.json()["detail"]
