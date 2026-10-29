"""Tests für Phase 66A (Zusatzfund zu P1-1 aus dem Code-Review): `_child_env(kind)` reicht pro
Skill-Subprozess nur noch die für DIESE Art freigegebenen Secrets aus `agent.env` weiter, statt
wie bisher jeden vorhandenen Schlüssel an JEDEN Subprozess durchzureichen (s.
tasks/spec_phase66_sandbox.md, Stufe 66A Schritt 3).

**Das ist Schadensbegrenzung, KEINE Sicherheitsgrenze** (S4 der Spec — "die ehrliche
Ausgangslage"): `Bash(python:*)` bleibt uneingeschränkt erlaubt, ein Subprozess kann `agent.env`
grundsätzlich selbst von der Platte lesen. Diese Tests prüfen nur die FUNKTION der neuen
Zuordnungslogik, nicht eine Sicherheitsgarantie.

Fälle (Spec Stufe 66A Schritt 5):
  1. Eine Art MIT dokumentiertem Zusatzbedarf (`jobsuche-apify`) bekommt ihren Zusatzschlüssel.
  2. Eine Art OHNE Zusatzbedarf (`firma-pruefen`) bekommt ihn NICHT — auch nicht die
     eng verwandte, aber bewusst andere Art `jobsuche` (ohne "-apify").
  3. `CLAUDE_CODE_OAUTH_TOKEN` ist bei JEDER Art dabei — die eine universelle Ausnahme.
  4. Eine unbekannte/künftige Art bekommt nur den Minimalsatz (Fall 3), sonst nichts.
  5. Zurückgehaltene Schlüssel erzeugen die laute Meldung (Rückgabewert `hinweis`) — mit dem
     Schlüssel-NAMEN, nie dem Wert; kein Zurückhalten → `hinweis is None`.
  6. `SECRET_KEYS_BY_KIND` selbst bleibt ein Regressions-Anker: wächst die Tabelle unbedacht,
     schlägt dieser Test sichtbar an (S1 — jede Erweiterung soll eine bewusste Entscheidung sein).

Mit einer SYNTHETISCHEN `agent.env` unter `tmp_path` — niemals die echten Secrets, keine
echten Werte im Testcode (die Fake-Strings sind als Test klar erkennbar und technisch ungültig).

App-Importe ausschließlich innerhalb der Testfunktionen (Konvention aus conftest.py — siehe
dessen Docstring). `_child_env()` selbst liest nur `ENV_FILE` (per `monkeypatch.setattr` auf
einen `tmp_path`-Pfad umgelenkt, Muster aus `test_secrets_pfade.py`) — die echte Datei unter
`~/.bewerbung_mgmt_secrets/agent.env` wird von diesen Tests nicht angefasst.
"""
import pytest

# Bewusst OHNE die realen Provider-Präfixe der beiden Secrets aus SECRET_KEYS_BY_KIND UND OHNE
# jede Ziffer: der lokale Secret-Guard (scripts/precommit_secret_scan.sh, prüft nur die beiden
# Präfixe) UND gitleaks' Default-Regel "generic-api-key" (Entropie-Schwelle 3.5; deren eigene
# Allowlist lässt einen erkannten Wert aber automatisch durch, wenn er AUSSCHLIESSLICH aus
# Buchstaben/Unterstrich/Punkt/Bindestrich besteht — belegt gegen die echte Regel geprüft,
# `raw.githubusercontent.com/gitleaks/gitleaks/master/config/gitleaks.toml`, Rule-ID
# "generic-api-key") würden sonst anschlagen, auch bei einem klar erkennbaren Test-Platzhalter.
# `_child_env()` behandelt den Wert ohnehin als opaken String (kein Format-Check) — diese Tests
# brauchen keine token-förmigen Werte, nur eindeutig unterscheidbare Fake-Strings.
FAKE_OAUTH_TOKEN = "testwert-oauth-niemals-echt-teststring"
FAKE_APIFY_TOKEN = "testwert-apify-niemals-echt-teststring"
FAKE_ZUKUNFTS_TOKEN = "testwert-zukunft-niemals-echt-teststring"


def _schreibe_env(pfad, **kv):
    pfad.write_text("\n".join(f"{k}={v}" for k, v in kv.items()) + "\n", encoding="utf-8")


# ── Fall 6: Regressions-Anker — die Tabelle wächst nur bewusst ──────────────────────────────
def test_secret_keys_by_kind_ist_aktuell_minimal_und_bewusst():
    """Schlägt an, sobald jemand SECRET_KEYS_BY_KIND erweitert — das ist Absicht (S1): jede
    neue Zeile soll eine bewusste, im Report/Commit begründete Entscheidung sein, kein
    versehentlicher Nebeneffekt eines anderen Changes."""
    import app.agent_runner as agent_runner

    assert agent_runner.SECRET_KEYS_BY_KIND == {"jobsuche-apify": {"APIFY_TOKEN"}}


# ── Fall 1+2: gezielte Zuordnung ──────────────────────────────────────────────────────────────
def test_art_mit_zusatzbedarf_bekommt_apify_token(tmp_path, monkeypatch):
    import app.agent_runner as agent_runner

    env_datei = tmp_path / "agent.env"
    _schreibe_env(env_datei, CLAUDE_CODE_OAUTH_TOKEN=FAKE_OAUTH_TOKEN, APIFY_TOKEN=FAKE_APIFY_TOKEN)
    monkeypatch.setattr(agent_runner, "ENV_FILE", env_datei)

    env, hinweis = agent_runner._child_env("jobsuche-apify")

    assert env["APIFY_TOKEN"] == FAKE_APIFY_TOKEN
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == FAKE_OAUTH_TOKEN
    assert hinweis is None    # jobsuche-apify braucht beides — nichts wird zurückgehalten


@pytest.mark.parametrize("kind", ["firma-pruefen", "jobsuche", "email-check", "cv-match"])
def test_art_ohne_zusatzbedarf_bekommt_apify_token_nicht(tmp_path, monkeypatch, kind):
    """`jobsuche` (OHNE "-apify") ist der wichtigste Fall hier: derselbe Skill-Ordner, aber eine
    andere `kind` — der Trigger-Satz von "jobsuche" verlangt nie Apify (S1-Beleg:
    jobsuche/SKILL.md Schritt 2b, „nur auf ausdrücklichen Wunsch"), nur "jobsuche-apify" soll
    den Token bekommen."""
    import app.agent_runner as agent_runner

    env_datei = tmp_path / "agent.env"
    _schreibe_env(env_datei, CLAUDE_CODE_OAUTH_TOKEN=FAKE_OAUTH_TOKEN, APIFY_TOKEN=FAKE_APIFY_TOKEN)
    monkeypatch.setattr(agent_runner, "ENV_FILE", env_datei)

    env, hinweis = agent_runner._child_env(kind)

    assert "APIFY_TOKEN" not in env
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == FAKE_OAUTH_TOKEN
    assert hinweis is not None
    assert "APIFY_TOKEN" in hinweis
    assert kind in hinweis


# ── Fall 3: OAuth-Token ist bei JEDER Art dabei ──────────────────────────────────────────────
@pytest.mark.parametrize("kind", ["firma-pruefen", "jobsuche-apify", "email-check",
                                   "eine-art-die-es-noch-nicht-gibt"])
def test_oauth_token_ist_immer_dabei(tmp_path, monkeypatch, kind):
    import app.agent_runner as agent_runner

    env_datei = tmp_path / "agent.env"
    _schreibe_env(env_datei, CLAUDE_CODE_OAUTH_TOKEN=FAKE_OAUTH_TOKEN)
    monkeypatch.setattr(agent_runner, "ENV_FILE", env_datei)

    env, hinweis = agent_runner._child_env(kind)

    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == FAKE_OAUTH_TOKEN
    assert hinweis is None    # einzig vorhandener Schlüssel ist erlaubt -> nichts zurückgehalten


# ── Fall 4: unbekannte Art → nur der Minimalsatz ─────────────────────────────────────────────
def test_unbekannte_art_bekommt_nur_minimalsatz(tmp_path, monkeypatch):
    import app.agent_runner as agent_runner

    env_datei = tmp_path / "agent.env"
    _schreibe_env(env_datei, CLAUDE_CODE_OAUTH_TOKEN=FAKE_OAUTH_TOKEN, APIFY_TOKEN=FAKE_APIFY_TOKEN,
                  FAKE_ZUKUNFTS_SCHLUESSEL=FAKE_ZUKUNFTS_TOKEN)
    monkeypatch.setattr(agent_runner, "ENV_FILE", env_datei)

    env, hinweis = agent_runner._child_env("eine-art-die-es-noch-nicht-gibt")

    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == FAKE_OAUTH_TOKEN
    assert "APIFY_TOKEN" not in env
    assert "FAKE_ZUKUNFTS_SCHLUESSEL" not in env
    assert hinweis is not None
    assert "APIFY_TOKEN" in hinweis
    assert "FAKE_ZUKUNFTS_SCHLUESSEL" in hinweis


# ── Fall 5: die Meldung selbst — Inhalt, Werte-Ausschluss, Abwesenheit bei Nicht-Bedarf ──────
def test_hinweis_nennt_nur_schluesselnamen_nie_werte(tmp_path, monkeypatch):
    import app.agent_runner as agent_runner

    env_datei = tmp_path / "agent.env"
    _schreibe_env(env_datei, CLAUDE_CODE_OAUTH_TOKEN=FAKE_OAUTH_TOKEN, APIFY_TOKEN=FAKE_APIFY_TOKEN)
    monkeypatch.setattr(agent_runner, "ENV_FILE", env_datei)

    _, hinweis = agent_runner._child_env("firma-pruefen")

    assert hinweis is not None
    assert FAKE_APIFY_TOKEN not in hinweis     # der WERT darf nie im Log landen
    assert FAKE_OAUTH_TOKEN not in hinweis
    assert "APIFY_TOKEN" in hinweis            # der NAME darf/soll


def test_kein_hinweis_wenn_nichts_zurueckgehalten_wird(tmp_path, monkeypatch):
    import app.agent_runner as agent_runner

    env_datei = tmp_path / "agent.env"
    _schreibe_env(env_datei, CLAUDE_CODE_OAUTH_TOKEN=FAKE_OAUTH_TOKEN)
    monkeypatch.setattr(agent_runner, "ENV_FILE", env_datei)

    _, hinweis = agent_runner._child_env("firma-pruefen")

    assert hinweis is None


def test_kein_hinweis_wenn_env_datei_fehlt(tmp_path, monkeypatch):
    """Fehlt die Datei ganz (z. B. auf einem frischen Rechner ohne agent.env), gibt es nichts
    zurückzuhalten — kein Hinweis, kein erfundener Wert."""
    import app.agent_runner as agent_runner

    monkeypatch.setattr(agent_runner, "ENV_FILE", tmp_path / "existiert_nicht.env")

    env, hinweis = agent_runner._child_env("firma-pruefen")

    assert hinweis is None
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env


# ── Server-Environment bleibt für JEDE Art vollständig erhalten (nur ENV_FILE wird gefiltert) ──
def test_server_environment_bleibt_fuer_jede_art_erhalten(tmp_path, monkeypatch):
    import app.agent_runner as agent_runner

    monkeypatch.setenv("BMS_TEST_MARKER_66A", "vorhanden")
    monkeypatch.setattr(agent_runner, "ENV_FILE", tmp_path / "existiert_nicht.env")

    env, _ = agent_runner._child_env("firma-pruefen")

    assert env.get("BMS_TEST_MARKER_66A") == "vorhanden"
