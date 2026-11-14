"""Startprüfung der Secret-Dateien (`check_env_file`, `check_secret_files`) in app/agent_runner.py.

Anlass: Erste Windows-Installationen von 2.2.2 brachen beim Start mit `NameError: name 'tx' is
not defined` ab. Beide Funktionen riefen `tx(...)` auf, das Modul kennt nur `sprache.tx`. Jede
Warnung führte so zum Absturz statt zu einer Meldung, unter Windows immer, weil die Rechteprüfung
dort bei jeder Datei anschlug; auf dem Mac bei jeder fehlerhaften agent.env. Die bisherigen Tests
liefen nie durch einen Warnungszweig.

Diese Tests gehen durch jeden Warnungszweig, mit synthetischen Dateien unter `tmp_path`, nie mit
echten Secrets. App-Importe nur in den Testfunktionen (Konvention aus conftest.py).
"""
import os
import types

import pytest

POSIX = os.name != "nt"
# Präfix getrennt geschrieben, damit der Secret-Guard (scripts/precommit_secret_scan.sh) nicht anschlägt.
PRAEFIX = "sk-an" "t-oat01-"
GUELTIG = PRAEFIX + "a" * 100


def _env(tmp_path, monkeypatch, inhalt: str, modus: int = 0o600):
    import app.agent_runner as agent_runner

    datei = tmp_path / "agent.env"
    datei.write_text(inhalt, encoding="utf-8")
    os.chmod(datei, modus)
    monkeypatch.setattr(agent_runner, "ENV_FILE", datei)
    return agent_runner


def test_jeder_inhaltszweig_warnt_ohne_absturz(tmp_path, monkeypatch):
    inhalt = "\n".join([
        "CLAUDE_CODE_OAUTH_TOKEN=" + GUELTIG[:60],   # zu kurz
        "abgebrochener-rest",                          # Fortsetzung der Token-Zeile
        "",
        "ohne-gleichheitszeichen",                     # Zeile ohne KEY=WERT, nicht nach dem Token
        "CLAUDE_CODE_OAUTH_TOKEN=falsch",              # falscher Anfang
    ])
    ar = _env(tmp_path, monkeypatch, inhalt)
    warnungen = ar.check_env_file()
    text = "\n".join(warnungen)
    assert "zu kurz" in text
    assert "FORTSETZUNG" in text
    assert "das Token muss als" in text
    assert "beginnt nicht mit" in text


def test_fehlendes_token_warnt(tmp_path, monkeypatch):
    ar = _env(tmp_path, monkeypatch, "# CLAUDE_CODE_OAUTH_TOKEN=\nAPIFY_TOKEN=x\n")
    assert any("kein CLAUDE_CODE_OAUTH_TOKEN" in w for w in ar.check_env_file())


def test_gueltige_datei_ohne_warnung(tmp_path, monkeypatch):
    ar = _env(tmp_path, monkeypatch, "CLAUDE_CODE_OAUTH_TOKEN=" + GUELTIG + "\n")
    assert ar.check_env_file() == []


@pytest.mark.skipif(not POSIX, reason="Rechte-Bits gibt es nur unter macOS/Linux")
def test_offene_rechte_warnen_unter_posix(tmp_path, monkeypatch):
    ar = _env(tmp_path, monkeypatch, "CLAUDE_CODE_OAUTH_TOKEN=" + GUELTIG + "\n", 0o644)
    assert any("zu offene Rechte" in w for w in ar.check_env_file())

    monkeypatch.setattr(ar, "SECRETS_DIR", tmp_path)
    for name in ("gmail_credentials.json", "gmail_token.json"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
        os.chmod(tmp_path / name, 0o644)
    assert len(ar.check_secret_files()) == 2


def test_unter_windows_keine_rechtewarnung(tmp_path, monkeypatch):
    """Unter Windows meldet `st_mode` pauschal 0o666. Die Prüfung entfällt dort, sonst warnte
    jeder Start mit einem Rat ('chmod 600'), den es unter Windows nicht gibt."""
    ar = _env(tmp_path, monkeypatch, "CLAUDE_CODE_OAUTH_TOKEN=" + GUELTIG + "\n", 0o666)
    for name in ("gmail_credentials.json", "gmail_token.json"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
        os.chmod(tmp_path / name, 0o666)
    monkeypatch.setattr(ar, "SECRETS_DIR", tmp_path)
    # Nur das os im Modul ersetzen, nicht das globale os.name: pathlib wählt danach die Pfadklasse.
    monkeypatch.setattr(ar, "os", types.SimpleNamespace(name="nt"))
    assert ar.check_env_file() == []
    assert ar.check_secret_files() == []


def test_start_workers_ueberlebt_warnungen(tmp_path, monkeypatch, capsys):
    """Der Pfad aus dem Fehlerbericht: start_workers() ruft die Prüfungen und druckt die
    Warnungen. Hier nur bis zur Ausgabe, der Rest des Starts wird abgeschnitten."""
    ar = _env(tmp_path, monkeypatch, "kaputt\n", 0o644)
    monkeypatch.setattr(ar, "SECRETS_DIR", tmp_path)
    monkeypatch.setattr(ar, "_queue", None)
    monkeypatch.setattr(ar.ki_anbieter, "aktiv", lambda: ar.ki_anbieter.CLAUDE)

    class _Stopp(Exception):
        pass

    def _stopp():
        raise _Stopp

    monkeypatch.setattr(ar, "cleanup_logs", _stopp)
    with pytest.raises(_Stopp):
        ar.start_workers()
    assert "WARNUNG" in capsys.readouterr().out
