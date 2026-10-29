"""API-Tests für `app/routes_mail_settings.py` (Phase 71F): `GET`/`PUT`/`POST /test` unter
`/api/settings/mail`.

Nutzt die `client`-Fixture aus `conftest.py` (FastAPI-`TestClient`, DB-isoliert). Die
Settings-Datei selbst liegt NICHT in der DB — `pipeline.imap_mail.SETTINGS_FILE` wird je Test
per `monkeypatch` auf `tmp_path` umgelenkt (Muster `test_secrets_pfade.py`), das echte
`~/.bewerbung_mgmt_secrets/mail_settings.json` wird von diesen Tests NIE angefasst — auch
nicht indirekt, weil `monkeypatch` beim Teardown automatisch zurücksetzt.

IMAP-/Gmail-Netzzugriffe im `/test`-Endpunkt werden auf Modulebene gemockt
(`imap_mail.test_connection` bzw. `gmail_client._creds`/`_client`/`_get`) — dieselbe Grenze
gilt hier wie in den anderen 71F-Tests: kein echter Server.
"""
import json
import os
import stat

import pytest


@pytest.fixture()
def settings_file(tmp_path, monkeypatch):
    import pipeline.imap_mail as imap_mail

    pfad = tmp_path / "mail_settings.json"
    monkeypatch.setattr(imap_mail, "SETTINGS_FILE", pfad)
    return pfad


IMAP_PAYLOAD = {
    "provider": "imap", "host": "imap.gmx.net", "port": 993, "security": "ssl",
    "username": "ich@gmx.de", "password": "app-passwort-123", "drafts_folder": "Entwürfe",
}


# ── GET ──────────────────────────────────────────────────────────────────────────────────
def test_get_ohne_datei_liefert_gmail_default_ohne_passwort(settings_file, client):
    assert not settings_file.exists()
    r = client.get("/api/settings/mail")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "gmail"
    assert body["password_set"] is False
    assert "password" not in body


# ── PUT ──────────────────────────────────────────────────────────────────────────────────
def test_put_imap_schreibt_600er_datei_und_liefert_password_set_true(settings_file, client):
    r = client.put("/api/settings/mail", json=IMAP_PAYLOAD)
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "imap"
    assert body["host"] == "imap.gmx.net"
    assert body["drafts_folder"] == "Entwürfe"
    assert body["password_set"] is True
    assert "password" not in body

    assert settings_file.exists()
    if os.name != "nt":   # NTFS bildet POSIX-Modi nicht ab (s. docs/SETUP-WINDOWS.md)
        mode = stat.S_IMODE(settings_file.stat().st_mode)
        assert mode == 0o600, f"erwarte chmod 600, gefunden {oct(mode)}"

    auf_platte = json.loads(settings_file.read_text(encoding="utf-8"))
    assert auf_platte["password"] == "app-passwort-123"   # Datei selbst darf das Passwort tragen


def test_put_leeres_passwort_behaelt_vorhandenes(settings_file, client):
    r1 = client.put("/api/settings/mail", json=IMAP_PAYLOAD)
    assert r1.status_code == 200

    ohne_passwort = {**IMAP_PAYLOAD, "password": "", "host": "imap.gmx.net", "username": "ich@gmx.de"}
    r2 = client.put("/api/settings/mail", json=ohne_passwort)
    assert r2.status_code == 200
    assert r2.json()["password_set"] is True

    auf_platte = json.loads(settings_file.read_text(encoding="utf-8"))
    assert auf_platte["password"] == "app-passwort-123"   # unverändert


def test_put_fehlende_pflichtfelder_liefert_422_mit_klartext(settings_file, client):
    r = client.put("/api/settings/mail", json={"provider": "imap"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "host" in detail and "username" in detail and "drafts_folder" in detail


def test_put_ungueltiger_provider_liefert_422(settings_file, client):
    r = client.put("/api/settings/mail", json={"provider": "outlook"})
    assert r.status_code == 422
    assert "provider" in r.json()["detail"]


def test_put_ungueltige_sicherheitsoption_liefert_422(settings_file, client):
    payload = {**IMAP_PAYLOAD, "security": "tls-irgendwas"}
    r = client.put("/api/settings/mail", json=payload)
    assert r.status_code == 422
    assert "security" in r.json()["detail"]


def test_put_neues_imap_ohne_passwort_liefert_422(settings_file, client):
    payload = {k: v for k, v in IMAP_PAYLOAD.items() if k != "password"}
    r = client.put("/api/settings/mail", json=payload)
    assert r.status_code == 422
    assert "password" in r.json()["detail"]


def test_put_unbekanntes_feld_liefert_422(settings_file, client):
    r = client.put("/api/settings/mail", json={"provider": "gmail", "unfug": 1})
    assert r.status_code == 422
    assert "unfug" in r.json()["detail"]


def test_put_zurueck_zu_gmail_verwirft_imap_felder(settings_file, client):
    client.put("/api/settings/mail", json=IMAP_PAYLOAD)
    r = client.put("/api/settings/mail", json={"provider": "gmail"})
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "gmail"
    assert body["password_set"] is False

    auf_platte = json.loads(settings_file.read_text(encoding="utf-8"))
    assert auf_platte == {"provider": "gmail"}


# ── POST /test ───────────────────────────────────────────────────────────────────────────
def test_post_test_imap_erfolg(settings_file, client, monkeypatch):
    import pipeline.imap_mail as imap_mail

    client.put("/api/settings/mail", json=IMAP_PAYLOAD)
    aufrufe = []

    def _fake_test_connection(settings):
        aufrufe.append(settings)
        return {"ok": True, "meldung": "IMAP-Verbindung erfolgreich: ich@gmx.de @ imap.gmx.net"}

    monkeypatch.setattr(imap_mail, "test_connection", _fake_test_connection)

    r = client.post("/api/settings/mail/test", json={})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert len(aufrufe) == 1
    assert aufrufe[0]["host"] == "imap.gmx.net"
    assert aufrufe[0]["password"] == "app-passwort-123"


def test_post_test_imap_nutzt_ungespeicherte_formulardaten_vor_dem_speichern(settings_file, client, monkeypatch):
    """Kernanforderung UX: 'Verbindung testen' soll VOR 'Speichern' funktionieren."""
    import pipeline.imap_mail as imap_mail

    assert not settings_file.exists()
    aufrufe = []
    monkeypatch.setattr(imap_mail, "test_connection",
                         lambda settings: aufrufe.append(settings) or {"ok": True, "meldung": "ok"})

    r = client.post("/api/settings/mail/test", json=IMAP_PAYLOAD)
    assert r.status_code == 200
    assert aufrufe[0]["host"] == "imap.gmx.net"
    assert aufrufe[0]["password"] == "app-passwort-123"
    assert not settings_file.exists()   # /test speichert NICHTS


def test_post_test_imap_fehlschlag_liefert_400_mit_klartext(settings_file, client, monkeypatch):
    import pipeline.imap_mail as imap_mail

    def _fake_fail(settings):
        imap_mail._die("IMAP-Login fuer 'ich@gmx.de' fehlgeschlagen: bad credentials")

    monkeypatch.setattr(imap_mail, "test_connection", _fake_fail)

    r = client.post("/api/settings/mail/test", json=IMAP_PAYLOAD)
    assert r.status_code == 400
    assert "bad credentials" in r.json()["detail"]


def test_post_test_gmail_erfolg(settings_file, client, monkeypatch):
    import pipeline.gmail_client as gmail_client

    monkeypatch.setattr(gmail_client, "_creds", lambda: object())

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(gmail_client, "_client", lambda creds: _FakeClient())
    monkeypatch.setattr(gmail_client, "_get", lambda cl, path: {"emailAddress": "ich@beispiel.de"})

    r = client.post("/api/settings/mail/test", json={"provider": "gmail"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "ich@beispiel.de" in r.json()["meldung"]


def test_post_test_gmail_fehlschlag_liefert_400_mit_klartext(settings_file, client, monkeypatch):
    import pipeline.gmail_client as gmail_client

    def _boom():
        gmail_client._die("Token ungueltig und nicht erneuerbar.")

    monkeypatch.setattr(gmail_client, "_creds", _boom)

    r = client.post("/api/settings/mail/test", json={"provider": "gmail"})
    assert r.status_code == 400
    assert "Token ungueltig" in r.json()["detail"]


def test_post_test_ohne_body_testet_gespeicherte_konfiguration(settings_file, client, monkeypatch):
    import pipeline.imap_mail as imap_mail

    client.put("/api/settings/mail", json=IMAP_PAYLOAD)
    aufrufe = []
    monkeypatch.setattr(imap_mail, "test_connection",
                         lambda settings: aufrufe.append(settings) or {"ok": True, "meldung": "ok"})

    r = client.post("/api/settings/mail/test")
    assert r.status_code == 200
    assert aufrufe[0]["host"] == "imap.gmx.net"
