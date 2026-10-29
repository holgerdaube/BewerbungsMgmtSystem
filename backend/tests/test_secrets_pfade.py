"""Tests für Phase 63A (P1-2 aus dem Code-Review): Gmail-Secrets und `agent.env` liegen
AUSSERHALB von Projekt & iCloud (s. tasks/spec_phase63_datenschutz.md, Stufe 63A Schritt 6).

Drei Fälle:
  1. Die vier Pfad-Konstanten (gmail_client.CRED_FILE/TOKEN_FILE, agent_runner.ENV_FILE,
     apify_client.ENV_FILE) liegen STRUKTURELL nicht unter dem Projekt-Root — Vergleich über
     `Path.is_relative_to`, kein String-Match (ein Teilstring-Treffer wäre durch einen
     zufälligen Ordnernamen täuschbar, z. B. ein Projekt unter ".../automation-tools/...").
  2. Der Override `BMS_SECRETS_DIR` wirkt — geprüft über ein ECHTES Neu-Einlesen des
     Environments (Modul-Reload NACH `os.environ`-Änderung), nicht nur über
     `monkeypatch.setattr` auf die fertige Konstante — sonst prüfte der Test nur sich selbst
     statt der Produktionszeile `os.environ.get("BMS_SECRETS_DIR", ...)`.
  3. Eine fehlende Secret-Datei erzeugt eine verständliche Fehlermeldung (`SystemExit`,
     Klartext auf stderr) — kein rohes Stacktrace-Modul, kein Secret-WERT im Text (nur
     Dateiname/Pfad sind laut D5 erlaubt).

App-Importe ausschließlich innerhalb der Testfunktionen (Konvention aus conftest.py — siehe
dessen Docstring). Es werden NIRGENDS echte Secrets angelegt oder gelesen — ausschließlich
tmp-Pfade (pytest `tmp_path`), die real nie existieren. Die echten Dateien unter
`~/.bewerbung_mgmt_secrets/` werden von diesen Tests nicht angefasst.
"""
import importlib
import os
from contextlib import contextmanager

import pytest


# ── Fall 1: strukturell außerhalb des Projekt-Root ──────────────────────────────────────
def test_secrets_konstanten_liegen_nicht_unter_projekt_root():
    import app.agent_runner as agent_runner
    import pipeline.apify_client as apify_client
    import pipeline.gmail_client as gmail_client

    konstanten = {
        "gmail_client.CRED_FILE": (gmail_client.CRED_FILE, gmail_client.PROJECT_ROOT),
        "gmail_client.TOKEN_FILE": (gmail_client.TOKEN_FILE, gmail_client.PROJECT_ROOT),
        "agent_runner.ENV_FILE": (agent_runner.ENV_FILE, agent_runner.PROJECT_ROOT),
        "apify_client.ENV_FILE": (apify_client.ENV_FILE, apify_client.PROJECT_ROOT),
    }
    for name, (pfad, projekt_root) in konstanten.items():
        assert not pfad.is_relative_to(projekt_root), (
            f"{name} ({pfad}) liegt noch strukturell unter dem Projekt-Root ({projekt_root}) "
            "— Secrets müssen außerhalb von Projekt & iCloud liegen (P1-2)."
        )


# ── Fall 2: BMS_SECRETS_DIR-Override wirkt ──────────────────────────────────────────────
@contextmanager
def _mit_bms_secrets_dir(modul_name: str, ziel_dir):
    """Setzt `BMS_SECRETS_DIR` WIRKLICH im Environment und liest das Modul per
    `importlib.reload` neu ein, damit die Produktionszeile
    `os.environ.get("BMS_SECRETS_DIR", ...)` selbst läuft (nicht nur eine per
    `monkeypatch.setattr` aufgeklebte Konstante). Stellt Environment UND Modulzustand beim
    Verlassen zuverlässig wieder her — auch wenn die Assertion im `with`-Block fehlschlägt —,
    damit kein nachfolgender Test den überschriebenen Zustand erbt."""
    modul = importlib.import_module(modul_name)
    alt = os.environ.get("BMS_SECRETS_DIR")
    os.environ["BMS_SECRETS_DIR"] = str(ziel_dir)
    try:
        importlib.reload(modul)
        yield modul
    finally:
        if alt is None:
            os.environ.pop("BMS_SECRETS_DIR", None)
        else:
            os.environ["BMS_SECRETS_DIR"] = alt
        importlib.reload(modul)


def test_bms_secrets_dir_override_wirkt_gmail_client(tmp_path):
    with _mit_bms_secrets_dir("pipeline.gmail_client", tmp_path) as modul:
        assert modul.SECRETS_DIR == tmp_path
        assert modul.CRED_FILE == tmp_path / "gmail_credentials.json"
        assert modul.TOKEN_FILE == tmp_path / "gmail_token.json"


def test_bms_secrets_dir_override_wirkt_agent_runner(tmp_path):
    with _mit_bms_secrets_dir("app.agent_runner", tmp_path) as modul:
        assert modul.SECRETS_DIR == tmp_path
        assert modul.ENV_FILE == tmp_path / "agent.env"


def test_bms_secrets_dir_override_wirkt_apify_client(tmp_path):
    with _mit_bms_secrets_dir("pipeline.apify_client", tmp_path) as modul:
        assert modul.SECRETS_DIR == tmp_path
        assert modul.ENV_FILE == tmp_path / "agent.env"


# ── Fall 3: fehlende Datei → verständliche Fehlermeldung, kein Stacktrace, kein Secret ───
def test_fehlender_gmail_token_ergibt_klare_fehlermeldung_ohne_stacktrace(tmp_path, monkeypatch, capsys):
    """`_creds()` ist die Funktion, über die Stufe 63A Schritt 3d/3f verifiziert (D1) — sie
    muss bei fehlendem Token sauber abbrechen, nie mit einer rohen Exception."""
    import pipeline.gmail_client as gmail_client

    monkeypatch.setattr(gmail_client, "TOKEN_FILE", tmp_path / "nicht_vorhanden.json")

    with pytest.raises(SystemExit) as exc_info:
        gmail_client._creds()

    assert exc_info.value.code == 2
    meldung = capsys.readouterr().err
    assert meldung.strip(), "erwarte eine Klartext-Fehlermeldung auf stderr"
    assert "Traceback" not in meldung
    assert "nicht_vorhanden.json" in meldung   # Dateiname/Pfad sind laut D5 erlaubt
    assert "sk-ant" not in meldung             # kein Claude-Token-Präfix im Text
    assert "ya29." not in meldung              # kein Google-Access-Token-Präfix im Text


def test_fehlender_apify_token_ergibt_klare_fehlermeldung_ohne_stacktrace(tmp_path, monkeypatch, capsys):
    import pipeline.apify_client as apify_client

    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    monkeypatch.setattr(apify_client, "ENV_FILE", tmp_path / "nicht_vorhanden.env")

    with pytest.raises(SystemExit) as exc_info:
        apify_client._token()

    assert exc_info.value.code == 1
    meldung = capsys.readouterr().err
    assert meldung.strip(), "erwarte eine Klartext-Fehlermeldung auf stderr"
    assert "Traceback" not in meldung
    assert "APIFY_TOKEN" in meldung
    assert "nicht_vorhanden.env" in meldung    # Dateiname/Pfad sind laut D5 erlaubt
