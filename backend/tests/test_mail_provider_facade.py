"""Fassaden-Dispatch von `pipeline.gmail_client` (Phase 71F): `cmd_search`/`cmd_get`/
`cmd_draft` bleiben in Signatur UND Ausgabeformat identisch, dispatchen intern aber nach
`mail_settings.json` an `pipeline.imap_mail`.

Zwei Kernaussagen, je mit eigenem Test:
  1. Fehlt `mail_settings.json` (oder ist provider nicht gesetzt/kaputt) → Provider "gmail",
     Bestandsverhalten unangetastet (KEIN Aufruf von `imap_mail`).
  2. Ist `provider: "imap"` konfiguriert → die drei Verben delegieren an `pipeline.imap_mail`,
     OHNE den Gmail-Codepfad (`_creds()`/`_client()`) überhaupt zu berühren.

App-/Pipeline-Importe bewusst innerhalb der Testfunktionen (Konvention aus conftest.py).
Kein Netz, kein echtes Secrets-Verzeichnis -- `SETTINGS_FILE` wird je Test auf `tmp_path`
umgelenkt (Muster `test_secrets_pfade.py`).
"""
import pytest


@pytest.fixture()
def tmp_settings_file(tmp_path, monkeypatch):
    import pipeline.imap_mail as imap_mail
    import pipeline.gmail_client as gmail_client   # noqa: F401 -- nur um sicherzustellen, dass beide importierbar sind

    pfad = tmp_path / "mail_settings.json"
    monkeypatch.setattr(imap_mail, "SETTINGS_FILE", pfad)
    return pfad


def test_default_provider_ist_gmail_bei_fehlender_datei(tmp_settings_file):
    import pipeline.gmail_client as gmail_client

    assert not tmp_settings_file.exists()
    assert gmail_client._provider() == "gmail"


def test_default_provider_ist_gmail_bei_datei_ohne_provider_feld(tmp_settings_file):
    import json
    import pipeline.gmail_client as gmail_client

    tmp_settings_file.write_text(json.dumps({"host": "irrelevant"}), encoding="utf-8")
    assert gmail_client._provider() == "gmail"


def test_default_provider_ist_gmail_bei_kaputtem_json(tmp_settings_file):
    import pipeline.gmail_client as gmail_client

    tmp_settings_file.write_text("{kaputt", encoding="utf-8")
    assert gmail_client._provider() == "gmail"


def test_provider_imap_wird_aus_datei_gelesen(tmp_settings_file):
    import pipeline.imap_mail as imap_mail
    import pipeline.gmail_client as gmail_client

    imap_mail.save_settings({"provider": "imap", "host": "h", "username": "u",
                              "password": "p", "drafts_folder": "Drafts"})
    assert gmail_client._provider() == "imap"


def _sperre_gmail_pfad(monkeypatch):
    """Lässt `gmail_client._creds()` mit einer klaren Assertion scheitern, falls der
    Gmail-Codepfad trotz `provider: imap` versehentlich doch aufgerufen würde."""
    import pipeline.gmail_client as gmail_client

    def _boom():
        raise AssertionError("Gmail-Codepfad (_creds) wurde trotz provider=imap aufgerufen")

    monkeypatch.setattr(gmail_client, "_creds", _boom)


def test_cmd_search_dispatcht_zu_imap_ohne_gmail_codepfad(tmp_settings_file, monkeypatch):
    import pipeline.imap_mail as imap_mail
    import pipeline.gmail_client as gmail_client

    imap_mail.save_settings({"provider": "imap", "host": "h", "username": "u",
                              "password": "p", "drafts_folder": "Drafts"})
    _sperre_gmail_pfad(monkeypatch)

    sentinel = [{"gmail_message_id": "<x@beispiel.de>"}]
    aufrufe = []

    def _fake_search(query, max_results):
        aufrufe.append((query, max_results))
        return sentinel

    monkeypatch.setattr(imap_mail, "cmd_search", _fake_search)

    out = gmail_client.cmd_search("from:foo", 25)
    assert out is sentinel
    assert aufrufe == [("from:foo", 25)]


def test_cmd_get_dispatcht_zu_imap_ohne_gmail_codepfad(tmp_settings_file, monkeypatch):
    import pipeline.imap_mail as imap_mail
    import pipeline.gmail_client as gmail_client

    imap_mail.save_settings({"provider": "imap", "host": "h", "username": "u",
                              "password": "p", "drafts_folder": "Drafts"})
    _sperre_gmail_pfad(monkeypatch)

    sentinel = {"gmail_message_id": "<x@beispiel.de>", "body": "Text"}
    monkeypatch.setattr(imap_mail, "cmd_get", lambda message_id: sentinel)

    out = gmail_client.cmd_get("<x@beispiel.de>")
    assert out is sentinel


def test_cmd_draft_dispatcht_zu_imap_ohne_gmail_codepfad(tmp_settings_file, monkeypatch):
    import pipeline.imap_mail as imap_mail
    import pipeline.gmail_client as gmail_client

    imap_mail.save_settings({"provider": "imap", "host": "h", "username": "u",
                              "password": "p", "drafts_folder": "Drafts"})
    _sperre_gmail_pfad(monkeypatch)

    sentinel = {"ok": True, "draft_id": None, "thread_id": None, "hinweis": "…"}
    aufrufe = []

    def _fake_draft(to, subject, body, in_reply_to=None):
        aufrufe.append((to, subject, body, in_reply_to))
        return sentinel

    monkeypatch.setattr(imap_mail, "cmd_draft", _fake_draft)

    out = gmail_client.cmd_draft("a@b.de", "Betreff", "Text", in_reply_to="<parent@beispiel.de>")
    assert out is sentinel
    assert aufrufe == [("a@b.de", "Betreff", "Text", "<parent@beispiel.de>")]


def test_cmd_search_leere_query_bricht_VOR_dispatch_ab(tmp_settings_file, monkeypatch):
    """Die Pflichtfeld-Prüfung gilt providerunabhängig -- sie darf nicht erst im IMAP-Zweig
    passieren, sonst würde ein Gmail-Nutzer ohne mail_settings.json eine andere Fehlermeldung
    bekommen als ein IMAP-Nutzer."""
    import pipeline.imap_mail as imap_mail
    import pipeline.gmail_client as gmail_client

    imap_mail.save_settings({"provider": "imap", "host": "h", "username": "u",
                              "password": "p", "drafts_folder": "Drafts"})

    def _boom(*a, **kw):
        raise AssertionError("imap_mail.cmd_search haette bei leerer Query nie aufgerufen werden duerfen")

    monkeypatch.setattr(imap_mail, "cmd_search", _boom)

    with pytest.raises(SystemExit) as exc_info:
        gmail_client.cmd_search("   ", 10)
    assert exc_info.value.code == 2


def test_cmd_draft_ohne_empfaenger_bricht_VOR_dispatch_ab(tmp_settings_file, monkeypatch):
    import pipeline.imap_mail as imap_mail
    import pipeline.gmail_client as gmail_client

    imap_mail.save_settings({"provider": "imap", "host": "h", "username": "u",
                              "password": "p", "drafts_folder": "Drafts"})

    def _boom(*a, **kw):
        raise AssertionError("imap_mail.cmd_draft haette ohne Empfaenger nie aufgerufen werden duerfen")

    monkeypatch.setattr(imap_mail, "cmd_draft", _boom)

    with pytest.raises(SystemExit):
        gmail_client.cmd_draft("", "S", "T")
