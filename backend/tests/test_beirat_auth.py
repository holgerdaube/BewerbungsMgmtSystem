"""Phase 77 — Headless-Auth vereinheitlicht: Beirat nutzt das Runner-Token + Vorwärm-Schleuse
gegen Refresh-Races (Fall A, 07.08.2026, 09:16: zwei Tasks "beirat-stellen-check"
scheiterten binnen 2s mit "Failed to authenticate: OAuth session expired and could not be
refreshed", während parallele Runner-Läufe [firma-pruefen] unberührt durchliefen — die
Keychain-Abo-Session war danach GLOBAL kaputt). Details: tasks/spec_phase77_beirat_auth.md.

Wie in conftest.py/test_beirat_fehler.py beschrieben: KEINE app.*/pipeline.*-Importe auf
Modulebene, nur in Testfunktionen (gilt auch für `beirat_engine` selbst). Rein synthetische
Daten, KEIN echter CLI-Aufruf -- jeder Test unten mockt entweder die reinen Hilfsfunktionen
direkt oder ersetzt `beirat_engine._turn`/`beirat_engine._turn_anthropic`/
`asyncio.create_subprocess_exec` durch Fakes. Token-/Key-WERTE in diesen Tests sind
ausnahmslos synthetisch (Kennzeichnung "synthetisch"/"testwert") -- niemals ein echtes Token.

Testfälle folgen Stufe D der Spec:
  1. Turn-Env (_turn_env): agent.env-Token landet im Subprozess-Env; keys.json-Key gewinnt;
     weder/noch -> Keychain-Fall (kein CLAUDE_CODE_OAUTH_TOKEN im Env).
  2. CLAUDE*-Stripping bleibt wirksam (eine fremde CLAUDE_CODE_SESSION_ID erreicht den Turn nicht).
  3. Vorwärm-Schleuse: zwei parallele Debatten im Keychain-Fall -> genau EIN Vorwärm-Aufruf
     (Lock+Cache); Fehlschlag wird nicht gecacht; im Token-Fall findet KEINE Vorwärmung statt;
     ein Vorwärm-Fehlschlag verhindert den Persona-Fan-out.
  4. Fehlerübersetzung: roher "Failed to authenticate..."-Text -> Klartext-Meldung je Auth-Weg.
"""
import asyncio
import json

import pytest


# ── Testfall 1: Turn-Env (_turn_env) ─────────────────────────────────────────────────────────

def test_turn_env_mit_agent_env_token_landet_im_subprocess_env(monkeypatch, tmp_path):
    """Stufe D.1: agent.env-Token vorhanden (kein keys.json-Key) -> landet als
    CLAUDE_CODE_OAUTH_TOKEN im zurückgegebenen Env, kein ANTHROPIC_API_KEY gesetzt."""
    import beirat_engine as be
    from app import agent_runner

    env_file = tmp_path / "agent.env"
    env_file.write_text('CLAUDE_CODE_OAUTH_TOKEN="oat01-testwert-synthetisch"\n')
    monkeypatch.setattr(agent_runner, "ENV_FILE", env_file)
    monkeypatch.setattr(be, "keys_lesen", lambda: {})

    env, auth_weg = be._turn_env(None)

    assert auth_weg == "agent.env-Token"
    assert env.get("CLAUDE_CODE_OAUTH_TOKEN") == "oat01-testwert-synthetisch"
    assert "ANTHROPIC_API_KEY" not in env


def test_turn_env_keys_json_key_gewinnt_ueber_agent_env_token(monkeypatch, tmp_path):
    """Stufe D.1: keys.json-Key vorhanden -> ANTHROPIC_API_KEY gewinnt (Entscheidung 1a
    bleibt unverändert Vorrang), das agent.env-Token bleibt UNGENUTZT im Env (Token wird
    trotzdem nicht geloggt -- s. separate Log-Grep-Verifikation am Ende der Datei)."""
    import beirat_engine as be
    from app import agent_runner

    env_file = tmp_path / "agent.env"
    env_file.write_text("CLAUDE_CODE_OAUTH_TOKEN=oat01-sollte-nicht-verwendet-werden\n")
    monkeypatch.setattr(agent_runner, "ENV_FILE", env_file)
    monkeypatch.setattr(be, "keys_lesen", lambda: {"anthropic": "api-echterkeytest-synthetisch"})

    env, auth_weg = be._turn_env(None)

    assert auth_weg == "keys.json"
    assert env.get("ANTHROPIC_API_KEY") == "api-echterkeytest-synthetisch"
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env


def test_turn_env_ohne_key_und_ohne_token_ist_keychain_fall(monkeypatch, tmp_path):
    """Stufe D.1: weder keys.json-Key noch agent.env-Token -> Auth-Weg c) Keychain, KEIN
    CLAUDE_CODE_OAUTH_TOKEN im Env (der Aufrufer fällt dann auf die Abo-Session zurück)."""
    import beirat_engine as be
    from app import agent_runner

    monkeypatch.setattr(agent_runner, "ENV_FILE", tmp_path / "agent_env_existiert_nicht")
    monkeypatch.setattr(be, "keys_lesen", lambda: {})

    env, auth_weg = be._turn_env(None)

    assert auth_weg == "keychain"
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert "ANTHROPIC_API_KEY" not in env


def test_headless_token_ignoriert_kommentar_und_leerzeilen(monkeypatch, tmp_path):
    """_headless_token() übernimmt das Parsing-Muster aus agent_runner._child_env(): Kommentar-/
    Leerzeilen überspringen, Anführungszeichen um den Wert strippen."""
    import beirat_engine as be
    from app import agent_runner

    env_file = tmp_path / "agent.env"
    env_file.write_text(
        "# Kommentarzeile, wird ignoriert\n\n"
        "CLAUDE_CODE_OAUTH_TOKEN='oat01-mit-single-quotes-synthetisch'\n"
    )
    monkeypatch.setattr(agent_runner, "ENV_FILE", env_file)

    assert be._headless_token() == "oat01-mit-single-quotes-synthetisch"


def test_headless_token_fehlende_datei_liefert_none(monkeypatch, tmp_path):
    import beirat_engine as be
    from app import agent_runner

    monkeypatch.setattr(agent_runner, "ENV_FILE", tmp_path / "existiert_nicht.env")
    assert be._headless_token() is None


# ── Testfall 2: CLAUDE*-Stripping bleibt wirksam ─────────────────────────────────────────────

def test_turn_env_strippt_fremde_claude_variablen(monkeypatch, tmp_path):
    """Stufe D.2: eine fremde CLAUDE_CODE_SESSION_ID aus dem Server-Env (der Server läuft selbst
    als Kindprozess einer laufenden Claude-Code-Session) erreicht den Turn NICHT -- das
    Stripping ist die bestehende Identitäts-Trennung und bleibt durch Phase 77 unangetastet."""
    import beirat_engine as be
    from app import agent_runner

    monkeypatch.setattr(agent_runner, "ENV_FILE", tmp_path / "agent_env_existiert_nicht")
    monkeypatch.setattr(be, "keys_lesen", lambda: {})
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "fremde-session-synthetisch")
    monkeypatch.setenv("CLAUDE_IRGENDWAS_ANDERES", "sollte-auch-verschwinden")

    env, _ = be._turn_env(None)

    assert "CLAUDE_CODE_SESSION_ID" not in env
    assert "CLAUDE_IRGENDWAS_ANDERES" not in env
    assert not any(k.startswith("CLAUDE") for k in env)


# ── Testfall 3: Vorwärm-Schleuse ──────────────────────────────────────────────────────────────

def test_vorwaermung_laeuft_bei_zwei_parallelen_debatten_genau_einmal(monkeypatch):
    """Stufe D.3: zwei gleichzeitig gestartete Vorwärmungen (Keychain-Fall) -> wegen
    Lock+5-Minuten-Erfolgscache läuft der zugrundeliegende Mini-Turn nur EINMAL; die zweite
    Debatte trifft den frisch gesetzten Cache. Ein künstlicher sleep() im Fake erzwingt eine
    ECHTE Überlappung -- ohne den Lock würde der zweite Aufruf den Cache noch leer vorfinden
    und ebenfalls einen Turn auslösen."""
    import beirat_engine as be

    monkeypatch.setattr(be, "_vorwaerm_ok_bis", 0.0)
    aufrufe = {"n": 0}

    async def fake_turn_anthropic(system_prompt, user_prompt, model, on_delta,
                                  task_id=None, timeout=None):
        aufrufe["n"] += 1
        assert user_prompt == "Antworte nur: OK"
        assert model == "haiku"
        assert timeout == 30
        await asyncio.sleep(0.05)
        return "OK", 0.001

    monkeypatch.setattr(be, "_turn_anthropic", fake_turn_anthropic)

    async def _zwei_parallel():
        return await asyncio.gather(be._keychain_vorwaermen(), be._keychain_vorwaermen())

    ergebnisse = asyncio.run(_zwei_parallel())

    assert aufrufe["n"] == 1
    assert all(fehler is None for fehler, _ in ergebnisse)


def test_vorwaermung_fehlschlag_wird_nicht_gecacht(monkeypatch):
    """Stufe D.3: ein Auth-Fehlschlag der Vorwärmung darf NICHT gecacht werden (Entscheidung 2)
    -- der nächste Versuch (z. B. die nächste Debatte) probiert es erneut, statt für 5 Minuten
    denselben (evtl. inzwischen behobenen) Fehler zu wiederholen."""
    import beirat_engine as be

    monkeypatch.setattr(be, "_vorwaerm_ok_bis", 0.0)
    aufrufe = {"n": 0}

    async def fake_turn_anthropic(system_prompt, user_prompt, model, on_delta,
                                  task_id=None, timeout=None):
        aufrufe["n"] += 1
        ex = RuntimeError("Failed to authenticate: OAuth session expired and could not be refreshed")
        ex.kosten_usd = 0.0
        raise ex

    monkeypatch.setattr(be, "_turn_anthropic", fake_turn_anthropic)

    fehler1, kosten1 = asyncio.run(be._keychain_vorwaermen())
    fehler2, kosten2 = asyncio.run(be._keychain_vorwaermen())

    assert fehler1 is not None and fehler2 is not None
    assert aufrufe["n"] == 2   # kein Erfolgscache nach Fehlschlag -- jeder Versuch zählt neu
    assert "claude" in fehler1.lower() and "/login" in fehler1
    assert kosten1 == 0.0 and kosten2 == 0.0


def _minimale_frei_debatte(monkeypatch, tmp_path, be, *, min_beitraege=2):
    """Gemeinsamer Aufbau (Muster _neue_test_debatte aus test_beirat_fehler.py): DATEN_DIR auf
    tmp umbiegen, minimale Debatte im Modus 'frei' anlegen. lade_mitglieder()/
    modell_fuer_beirat() laufen ECHT (lesen nur lokale Personas-Markdown/tmp-DB), starten
    keinen Subprozess."""
    monkeypatch.setattr(be, "DATEN_DIR", tmp_path / "beirat_test")
    d = be.Debatte(
        thema="Testfrage fuer den Beirat (synthetisch)", kontext="", min_beitraege=min_beitraege,
        teilnehmer_ids=None, provider="anthropic", openai_model="gpt-4o-mini", modus="frei",
    )
    assert d.task_id is None
    return d


def _fake_turn_reihe(d, *, dispatch_kosten=0.01, beitrag_text="Beitrag (synthetisch)."):
    """Minimaler fake_turn: schließt nach min_beitraege ab, sonst dispatcht immer an Brandt."""
    async def fake_turn(provider, openai_model, system_prompt, user_prompt, persona_model,
                        on_delta, task_id=None):
        if user_prompt.startswith("DEBATTEN-STEUERUNG."):
            if len(d.beitraege) >= d.min_beitraege:
                return json.dumps({"aktion": "abschluss", "begruendung": "genug fuer den Test"}), dispatch_kosten
            return json.dumps({"aktion": "dispatch", "kopf": "beirat-vera-brandt",
                               "frage": "Testfrage?"}), dispatch_kosten
        if user_prompt.startswith("Die Debatte ist beendet"):
            return "Synthesetext (synthetisch).", 0.01
        return beitrag_text, 0.02
    return fake_turn


def test_debatte_ruft_keine_vorwaermung_auf_wenn_agent_env_token_vorhanden(monkeypatch, tmp_path, _db_ready):
    """Stufe D.3 / Abnahme "Negativ-Beleg": vorhandenes agent.env-Token -> Auth-Weg b), die
    Vorwärm-Schleuse wird gar nicht erst aufgerufen (Spy-Zähler bleibt 0)."""
    import beirat_engine as be
    from app import agent_runner

    d = _minimale_frei_debatte(monkeypatch, tmp_path, be)
    env_file = tmp_path / "agent.env"
    env_file.write_text("CLAUDE_CODE_OAUTH_TOKEN=oat01-vorhanden-synthetisch\n")
    monkeypatch.setattr(agent_runner, "ENV_FILE", env_file)
    monkeypatch.setattr(be, "keys_lesen", lambda: {})

    vorwaerm_aufrufe = {"n": 0}

    async def spy_vorwaermen(task_id=None):
        vorwaerm_aufrufe["n"] += 1
        return None, 0.0

    monkeypatch.setattr(be, "_keychain_vorwaermen", spy_vorwaermen)
    monkeypatch.setattr(be, "_turn", _fake_turn_reihe(d))

    asyncio.run(d.laufen())

    assert d.status == "fertig"
    assert vorwaerm_aufrufe["n"] == 0


def test_debatte_ruft_vorwaermung_auf_im_keychain_fall(monkeypatch, tmp_path, _db_ready):
    """Gegenprobe: weder Key noch Token -> die Vorwärmung wird GENAU EINMAL aufgerufen, bevor
    der erste Dispatch-Turn läuft."""
    import beirat_engine as be
    from app import agent_runner

    d = _minimale_frei_debatte(monkeypatch, tmp_path, be)
    monkeypatch.setattr(agent_runner, "ENV_FILE", tmp_path / "kein_agent_env")
    monkeypatch.setattr(be, "keys_lesen", lambda: {})

    vorwaerm_aufrufe = {"n": 0}

    async def spy_vorwaermen(task_id=None):
        vorwaerm_aufrufe["n"] += 1
        return None, 0.0

    monkeypatch.setattr(be, "_keychain_vorwaermen", spy_vorwaermen)
    monkeypatch.setattr(be, "_turn", _fake_turn_reihe(d))

    asyncio.run(d.laufen())

    assert d.status == "fertig"
    assert vorwaerm_aufrufe["n"] == 1


def test_debatte_bricht_sofort_ab_wenn_vorwaermung_scheitert(monkeypatch, tmp_path, _db_ready):
    """Stufe D.3 / Abnahme "Keychain-Fallback gemockt belegt": ein Auth-Fehlschlag der
    Vorwärmung beendet die Debatte SOFORT (status='fehler', Klartext-Meldung) -- OHNE
    Persona-Fan-out (kein Dispatch-Turn erreicht `_turn`, s. persona_aufrufe['n'] == 0) und
    ohne Retry-Gewitter (die Vorwärmung selbst läuft nur einmal, s. vorwaerm_aufrufe)."""
    import beirat_engine as be
    from app import agent_runner

    d = _minimale_frei_debatte(monkeypatch, tmp_path, be)
    monkeypatch.setattr(agent_runner, "ENV_FILE", tmp_path / "kein_agent_env")
    monkeypatch.setattr(be, "keys_lesen", lambda: {})
    monkeypatch.setattr(be, "_vorwaerm_ok_bis", 0.0)

    vorwaerm_aufrufe = {"n": 0}

    async def fake_keychain_vorwaermen(task_id=None):
        vorwaerm_aufrufe["n"] += 1
        return ("Claude-Abo-Login abgelaufen — im Terminal `claude` öffnen und per /login neu "
                "anmelden, dann den Check erneut starten."), 0.0

    monkeypatch.setattr(be, "_keychain_vorwaermen", fake_keychain_vorwaermen)

    persona_aufrufe = {"n": 0}
    async def fake_turn(provider, openai_model, system_prompt, user_prompt, persona_model,
                        on_delta, task_id=None):
        persona_aufrufe["n"] += 1
        return "sollte nie erreicht werden", 0.0

    monkeypatch.setattr(be, "_turn", fake_turn)

    asyncio.run(d.laufen())

    assert d.status == "fehler"
    assert d.fehler is not None
    assert "claude" in d.fehler.lower() and "/login" in d.fehler
    assert len(d.beitraege) == 0
    assert vorwaerm_aufrufe["n"] == 1     # GENAU EIN Vorwärm-Versuch, kein Retry-Gewitter
    assert persona_aufrufe["n"] == 0      # kein Fan-out -- Debatte endet VOR dem ersten Turn


# ── Testfall 4: Fehlerübersetzung (_auth_fehler_uebersetzen) ────────────────────────────────

def test_auth_fehler_uebersetzung_keychain():
    import beirat_engine as be

    text = be._auth_fehler_uebersetzen(
        "Failed to authenticate: OAuth session expired and could not be refreshed", "keychain")

    assert text is not None
    assert "claude" in text.lower()
    assert "/login" in text


def test_auth_fehler_uebersetzung_agent_env_token(monkeypatch, tmp_path):
    import beirat_engine as be
    from app import agent_runner

    env_file = tmp_path / "agent.env"
    monkeypatch.setattr(agent_runner, "ENV_FILE", env_file)

    text = be._auth_fehler_uebersetzen("OAuth session expired and could not be refreshed",
                                       "agent.env-Token")

    assert text is not None
    assert str(env_file) in text
    assert "setup-token" in text


def test_auth_fehler_uebersetzung_erkennt_case_insensitiv():
    import beirat_engine as be

    text = be._auth_fehler_uebersetzen("API-Fehler: FAILED TO AUTHENTICATE (synthetisch)",
                                       "keychain")
    assert text is not None


def test_auth_fehler_uebersetzung_ignoriert_andere_fehler():
    """Kein Auth-Fehler (z. B. Rate-Limit) -> None, der Aufrufer behält den rohen Text
    (unverändertes Verhalten wie vor Phase 77)."""
    import beirat_engine as be

    text = be._auth_fehler_uebersetzen("API-Fehler 429: Rate-Limit erreicht (synthetisch)",
                                       "keychain")
    assert text is None


def test_turn_anthropic_uebersetzt_auth_fehler_im_keychain_fall(monkeypatch, tmp_path):
    """Wiring-Nachweis: nicht nur die reine Übersetzungsfunktion, sondern auch der tatsächliche
    Turn-Fehlerpfad in _turn_anthropic() nutzt sie -- ein per stream-json simulierter
    is_error-Turn ("Failed to authenticate…") kommt beim Aufrufer bereits als Klartext an.
    Subprozess-Erzeugung gemockt (KEIN echter CLI-Aufruf), WORK_DIR auf tmp umgebogen."""
    import beirat_engine as be
    from app import agent_runner

    monkeypatch.setattr(agent_runner, "ENV_FILE", tmp_path / "kein_agent_env")
    monkeypatch.setattr(be, "keys_lesen", lambda: {})
    monkeypatch.setattr(be, "WORK_DIR", tmp_path / "work")

    result_zeile = (json.dumps({
        "type": "result", "is_error": True, "api_error_status": None,
        "result": "Failed to authenticate: OAuth session expired and could not be refreshed",
        "total_cost_usd": 0.0,
    }) + "\n").encode("utf-8")

    class _FakeStdout:
        def __init__(self, zeilen):
            self._zeilen = list(zeilen)

        async def readline(self):
            return self._zeilen.pop(0) if self._zeilen else b""

    class _FakeProc:
        def __init__(self, zeilen):
            self.stdout = _FakeStdout(zeilen)
            self.returncode = 0

        def kill(self):
            pass

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return _FakeProc([result_zeile])

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    async def _nix(_):
        return

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(be._turn_anthropic("Systemtext", "Nutzertext", "haiku", _nix))

    text = str(exc_info.value)
    assert "claude" in text.lower() and "/login" in text
    assert "OAuth session expired" not in text   # roher CLI-Text wurde übersetzt, nicht durchgereicht


# ── Kein Token-/Key-Wert in Logzeilen oder Fehlermeldungen (Fallstrick-Verifikation) ─────────

def test_auth_log_text_enthaelt_keine_werte():
    """Die drei Log-Texte (Entscheidung 1, s. Aufgabenstellung) sind reine Schlüssel-Namen ohne
    Wert -- Grep-Verifikation, dass niemand versehentlich einen Platzhalter für den echten
    Token-/Key-Wert eingebaut hat."""
    import beirat_engine as be

    for text in be._AUTH_WEG_LOG_TEXT.values():
        assert text.startswith("Auth: ")
        assert "sk-ant" not in text
        assert len(text) < 60   # reine Kurz-Kennzeichnung, kein eingebetteter Wert möglich
