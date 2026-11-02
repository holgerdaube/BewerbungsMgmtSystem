"""P2-86 — Beirat unter ChatGPT: Abo-Motor über `codex exec` statt `claude -p`.

Ist in den Einstellungen ChatGPT gewählt, wird aus dem Motor "anthropic" (Abo, so heißt er in Formular und API)
der Motor "codex": `beirat_engine._turn_codex`, ein Text-Turn ohne Werkzeuge. Unter Claude ändert sich nichts
(die übrigen `test_beirat_*` bleiben unverändert grün).

B1 (wie in test_beirat_fehler.py): kein echter KI-Lauf. `ki_anbieter.CODEX_BIN` zeigt auf eine Attrappe (ein
Python-Skript, Muster `_attrappe` aus test_ki_anbieter.py), die Eingabe und Umgebung aufzeichnet und je nach
Aufgabe eine feste Antwort liefert. `claude` darf in diesen Tests nie starten: `_turn_anthropic` und die
Keychain-Vorwärmung brechen mit einer Assertion ab. `DATEN_DIR`, `_REPORT_DIR` und `WORK_DIR` liegen in tmp.

Wie in conftest.py beschrieben: keine app.*/pipeline.*-Importe auf Modulebene.
"""
import asyncio
import glob
import json
import stat
import sys
from pathlib import Path

import pytest

ATTRAPPE = r'''#!__PYTHON__
import json, os, re, sys, time

modus = os.environ.get("ATTRAPPE_MODUS", "ok")
if modus == "laut":                      # füllt den stderr-Puffer, BEVOR die Eingabe gelesen wird
    sys.stderr.write("x" * 200_000 + "\n")
    sys.stderr.flush()
prompt = sys.stdin.read()
with open(os.path.join(os.environ["ATTRAPPE_ORDNER"], "aufruf_%d.json" % os.getpid()), "w", encoding="utf-8") as f:
    json.dump({"argv": sys.argv[1:], "prompt": prompt, "cwd": os.getcwd(), "pfad_da": "PATH" in os.environ,
               "gesetzt": [n for n in ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_SESSION_ID", "ANTHROPIC_API_KEY",
                                       "OPENAI_API_KEY", "CODEX_API_KEY") if n in os.environ]}, f)

if modus == "haengt":
    time.sleep(60)
if modus == "abbruch":                   # endet ohne Turn, die letzte Zeile sagt warum
    sys.stderr.write("codex: boom\n")
    sys.exit(1)
if modus == "stumm":                     # endet ohne jede Ausgabe
    sys.exit(0)
if modus == "limit":
    print(json.dumps({"type": "turn.failed", "error": {"message": "You've hit your usage limit"}}))
    sys.exit(1)
if modus == "login":
    print(json.dumps({"type": "error", "message": "Not logged in"}))
    sys.exit(1)

if "DEBATTEN-STEUERUNG." in prompt:
    ziel = "abschluss" if "ist ERREICHT" in prompt else "dispatch"
    antwort = json.dumps({"aktion": ziel, "kopf": "beirat-vera-brandt", "frage": "Testfrage?", "begruendung": "genug"})
elif "BEREITS BERECHNETE ENTSCHEIDUNG" in prompt:
    ids = re.findall(r"(beirat-[a-z-]+) =", prompt)
    antwort = json.dumps({
        "begruendung": "Einordnung (synthetisch).", "bedingt_bedingungen": [],
        "risiko_board": [{"risiko": "Erstes Risiko", "schwere": "hoch", "status": "ungeklaert", "naechster_schritt": "klären"},
                         {"risiko": "Zweites Risiko", "schwere": "mittel", "status": "in_klaerung", "naechster_schritt": "prüfen"}],
        "kern_je_kopf": [{"kopf": i, "kern": "Kern (synthetisch)."} for i in ids],
        "empfehlung": "Empfehlung (synthetisch)."})
elif "Vergib jetzt unabhängig Bewertungen" in prompt:
    antwort = json.dumps({"scores": {b: 8 for b in ("rollenfit", "cv_ergebnisse", "unternehmen", "uebertragbarkeit",
                                                    "karrierewirkung", "interview_chance")},
                          "votum": "Bewerben", "begruendung": "Begründung (synthetisch)."})
elif "Die Debatte ist beendet" in prompt:
    antwort = "Synthesetext (synthetisch)."
else:
    antwort = "Beitrag (synthetisch)."

print(json.dumps({"type": "thread.started"}))
print(json.dumps({"type": "turn.started"}))
print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": antwort}}))
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 10}}))
'''

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Attrappe ist ein Shebang-Skript")


@pytest.fixture
def attrappe(tmp_path, monkeypatch):
    """Die Codex-Attrappe als `ki_anbieter.CODEX_BIN`, dazu ein harmloses Umfeld: eigener Arbeitsordner, Aufzeichnung
    der Aufrufe in `ordner`, gesetzte Claude-/Anthropic-/OpenAI-Schlüssel (dürfen nie bei Codex ankommen)."""
    import beirat_engine as be
    from app import ki_anbieter as ki

    programm = tmp_path / "codex_attrappe"
    programm.write_text(ATTRAPPE.replace("__PYTHON__", sys.executable), encoding="utf-8")
    programm.chmod(programm.stat().st_mode | stat.S_IEXEC)
    ordner = tmp_path / "aufrufe"
    ordner.mkdir()
    monkeypatch.setattr(ki, "CODEX_BIN", str(programm))
    monkeypatch.setenv("ATTRAPPE_ORDNER", str(ordner))
    monkeypatch.delenv("ATTRAPPE_MODUS", raising=False)
    for name in ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_SESSION_ID", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY"):
        monkeypatch.setenv(name, "synthetisch")
    monkeypatch.setattr(be, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(be, "DATEN_DIR", tmp_path / "beirat_test")
    monkeypatch.setattr(be, "_REPORT_DIR", tmp_path / "berichte")
    monkeypatch.setattr(be, "_jobfile_registrieren", lambda d: None)

    class _Attrappe:
        def aufrufe(self):
            return [json.loads(Path(p).read_text(encoding="utf-8")) for p in sorted(glob.glob(str(ordner / "aufruf_*.json")))]
    return _Attrappe()


@pytest.fixture
def kein_claude(tmp_path, monkeypatch):
    """Unter ChatGPT startet nichts von Claude: weder ein Turn noch die Keychain-Vorwärmung."""
    import beirat_engine as be
    from app import agent_runner

    def _nie(*args, **kwargs):
        raise AssertionError("Unter ChatGPT darf kein Claude-Turn und keine Keychain-Vorwärmung laufen")

    monkeypatch.setattr(be, "_turn_anthropic", _nie)
    monkeypatch.setattr(be, "_keychain_vorwaermen", _nie)
    monkeypatch.setattr(be, "CLAUDE_BIN", str(tmp_path / "kein_claude"))
    # Keychain-Fall: weder Key noch Token. Unter Claude würde jetzt vorgewärmt (test_beirat_auth.py).
    monkeypatch.setattr(agent_runner, "ENV_FILE", tmp_path / "kein_agent_env")
    monkeypatch.setattr(be, "keys_lesen", lambda: {})


@pytest.fixture
def chatgpt(client):
    """ChatGPT als gewählte KI, danach zurück auf Claude (die Einstellung liegt in der gemeinsamen tmp-DB)."""
    assert client.patch("/api/einstellungen", json={"ki_anbieter": "chatgpt"}).status_code == 200
    yield
    assert client.patch("/api/einstellungen", json={"ki_anbieter": "claude"}).status_code == 200


async def _nie_delta(_):
    raise AssertionError("Codex liefert keine Teil-Ausgabe, on_delta darf nicht aufgerufen werden")


# ── Ein Turn ─────────────────────────────────────────────────────────────────────────────────────

def test_turn_aufruf_eingabe_umgebung_und_kosten(attrappe, tmp_path):
    import beirat_engine as be
    from app import ki_anbieter as ki

    text, kosten = asyncio.run(be._turn("codex", "gpt-4o", "SYSTEMTEXT-EINS", "NUTZERTEXT-ZWEI", "opus", _nie_delta))

    assert text == "Beitrag (synthetisch)." and kosten == 0.0
    (aufruf,) = attrappe.aufrufe()
    argv = aufruf["argv"]
    assert argv[:2] == ["exec", "--json"] and argv[-1] == "-"
    assert {"--skip-git-repo-check", "--ignore-user-config", "--ephemeral"} <= set(argv)
    assert argv[argv.index("-s") + 1] == "read-only"
    assert 'web_search="disabled"' in argv
    assert argv[argv.index("-m") + 1] == ki.CODEX_MODELL["opus"]
    assert "SYSTEMTEXT-EINS" in aufruf["prompt"] and "NUTZERTEXT-ZWEI" in aufruf["prompt"]
    assert aufruf["prompt"].index("SYSTEMTEXT-EINS") < aufruf["prompt"].index("NUTZERTEXT-ZWEI")
    assert aufruf["gesetzt"] == [] and aufruf["pfad_da"] is True      # Anmeldung des Rechners, kein Schlüssel
    assert aufruf["cwd"] == str((tmp_path / "work").resolve())        # leerer Ordner, kein Projektkontext


def test_modell_folgt_der_stufe_des_turns(attrappe):
    import beirat_engine as be
    from app import ki_anbieter as ki

    asyncio.run(be._turn("codex", "gpt-4o", "S", "U", "haiku", _nie_delta))
    asyncio.run(be._turn("codex", "gpt-4o", "S", "U", "sonnet", _nie_delta))
    modelle = [a["argv"][a["argv"].index("-m") + 1] for a in attrappe.aufrufe()]
    assert sorted(modelle) == sorted([ki.CODEX_MODELL["haiku"], ki.CODEX_MODELL["sonnet"]])


def test_unbekannte_stufe_faellt_auf_die_beiratswahl(attrappe, _db_ready):
    import beirat_engine as be
    from app import agent_runner, ki_anbieter as ki

    asyncio.run(be._turn("codex", "gpt-4o", "S", "U", "fable", _nie_delta))
    (aufruf,) = attrappe.aufrufe()
    assert aufruf["argv"][aufruf["argv"].index("-m") + 1] == ki.CODEX_MODELL[agent_runner.modell_fuer_beirat()]


def test_ohne_system_text_steht_nur_die_aufgabe_da(attrappe):
    import beirat_engine as be

    asyncio.run(be._turn("codex", "gpt-4o", "", "NUR-AUFGABE", "sonnet", _nie_delta))
    (aufruf,) = attrappe.aufrufe()
    assert "NUR-AUFGABE" in aufruf["prompt"] and "ANWEISUNG" not in aufruf["prompt"]


def test_rohe_zeilen_landen_im_task_log(attrappe):
    import beirat_engine as be

    asyncio.run(be._turn("codex", "gpt-4o", "S", "U", "sonnet", _nie_delta, task_id=987654))
    log = (be.AGENT_LOG_DIR / "task_987654.jsonl").read_text(encoding="utf-8")
    assert "Motor: ChatGPT-Abo (Codex)" in log and '"type": "turn.completed"' in log


def test_viel_stderr_und_grosse_eingabe_blockieren_nicht(attrappe, monkeypatch):
    """Muster test_beirat_stderr_deadlock.py: Die Attrappe füllt stderr, bevor sie die Eingabe liest. Wer erst die
    Eingabe schreibt und dann liest (oder stderr getrennt lässt), hängt dauerhaft."""
    import beirat_engine as be

    monkeypatch.setenv("ATTRAPPE_MODUS", "laut")
    text, _ = asyncio.run(be._turn_codex("S", "U" * 400_000, "sonnet", _nie_delta, timeout=60))
    assert text == "Beitrag (synthetisch)."


@pytest.mark.parametrize("modus,erwartet", [
    ("limit", "Nutzungslimit Ihres ChatGPT-Abos"),
    ("login", "codex login"),
    ("abbruch", "codex: boom"),
    ("stumm", "Leerer ChatGPT-Turn (exit 0)"),
])
def test_fehler_kommen_als_klartext(attrappe, monkeypatch, modus, erwartet):
    import beirat_engine as be

    monkeypatch.setenv("ATTRAPPE_MODUS", modus)
    with pytest.raises(RuntimeError) as fehler:
        asyncio.run(be._turn("codex", "gpt-4o", "S", "U", "sonnet", _nie_delta))
    assert erwartet in str(fehler.value)


def test_zeitlimit_ist_eine_klare_meldung(attrappe, monkeypatch):
    import beirat_engine as be

    monkeypatch.setenv("ATTRAPPE_MODUS", "haengt")
    with pytest.raises(RuntimeError) as fehler:
        asyncio.run(be._turn_codex("S", "U", "sonnet", _nie_delta, timeout=1))
    assert "Zeitlimit" in str(fehler.value)


def test_fehlendes_programm_ist_eine_klare_meldung(tmp_path, monkeypatch):
    import beirat_engine as be
    from app import ki_anbieter as ki

    monkeypatch.setattr(ki, "CODEX_BIN", str(tmp_path / "gibtsnicht"))
    with pytest.raises(RuntimeError) as fehler:
        asyncio.run(be._turn("codex", "gpt-4o", "S", "U", "sonnet", _nie_delta))
    assert "gibtsnicht" in str(fehler.value) and "codex login" in str(fehler.value)


# ── Welcher Motor läuft ──────────────────────────────────────────────────────────────────────────

def test_unter_claude_bleibt_der_abo_motor_anthropic(client):
    import beirat_engine as be

    assert client.get("/api/einstellungen").json()["ki_anbieter"] == "claude"
    assert be._wirksamer_motor("anthropic") == "anthropic"
    assert be._wirksamer_motor("openai") == "openai"


def test_unter_chatgpt_wird_aus_dem_abo_motor_codex_und_der_api_weg_bleibt(chatgpt):
    import beirat_engine as be

    assert be._wirksamer_motor("anthropic") == "codex"
    assert be._wirksamer_motor("openai") == "openai"      # API-Schlüssel-Weg bleibt Option der freien Debatte


def test_motor_wird_beim_start_festgelegt(client, tmp_path, monkeypatch):
    """Ein Wechsel der KI mitten in einer Debatte ändert deren Motor nicht."""
    import beirat_engine as be

    monkeypatch.setattr(be, "DATEN_DIR", tmp_path / "beirat_test")
    d = be.Debatte("Testfrage (synthetisch)", "", 2, None, "anthropic", "gpt-4o-mini")
    assert d.provider == "anthropic"
    client.patch("/api/einstellungen", json={"ki_anbieter": "chatgpt"})
    try:
        assert d.provider == "anthropic"
        assert be.Debatte("Testfrage (synthetisch)", "", 2, None, "anthropic", "gpt-4o-mini").provider == "codex"
    finally:
        client.patch("/api/einstellungen", json={"ki_anbieter": "claude"})


def test_statusanzeige_prueft_unter_chatgpt_das_codex_programm(attrappe, chatgpt, tmp_path, monkeypatch):
    import beirat_engine as be
    from app import ki_anbieter as ki

    monkeypatch.setattr(be, "CLAUDE_BIN", str(tmp_path / "kein_claude"))      # Claude fehlt, Codex ist da
    assert be.keys_status()["cli_verfuegbar"] is True
    monkeypatch.setattr(ki, "CODEX_BIN", str(tmp_path / "kein_codex"))
    monkeypatch.setattr(be, "CLAUDE_BIN", sys.executable)                      # Claude da, Codex fehlt
    assert be.keys_status()["cli_verfuegbar"] is False


def test_statusanzeige_unter_claude_ignoriert_codex(client, tmp_path, monkeypatch):
    import beirat_engine as be
    from app import ki_anbieter as ki

    monkeypatch.setattr(be, "KEY_PFAD", tmp_path / "keys.json")
    monkeypatch.setattr(ki, "CODEX_BIN", sys.executable)                       # Codex da, Claude fehlt
    monkeypatch.setattr(be, "CLAUDE_BIN", str(tmp_path / "kein_claude"))
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert be.keys_status()["cli_verfuegbar"] is False


# ── Ganze Läufe ──────────────────────────────────────────────────────────────────────────────────

def _ereignisse(d) -> list[dict]:
    aus = []
    while not d.queue.empty():
        e = d.queue.get_nowait()
        if e is not None:
            aus.append(e)
    return aus


def test_freie_debatte_unter_chatgpt(attrappe, kein_claude, chatgpt):
    import beirat_engine as be

    d = be.Debatte("Testfrage fuer den Beirat (synthetisch)", "", 2, None, "anthropic", "gpt-4o-mini")
    assert d.provider == "codex"
    asyncio.run(d.laufen())

    assert d.status == "fertig" and d.fehler is None
    assert len(d.beitraege) == 2 and d.synthese == "Synthesetext (synthetisch)."
    assert d.kosten_usd == 0.0
    aufrufe = attrappe.aufrufe()
    assert aufrufe and len(aufrufe) == d.num_turns                 # jeder Turn ging an Codex, keiner an Claude
    assert all(a["gesetzt"] == [] for a in aufrufe)               # nie ein Claude-, Anthropic- oder OpenAI-Schlüssel
    typen = [e["typ"] for e in _ereignisse(d)]
    assert "delta" not in typen                                    # kein vorgetäuschtes Streaming
    assert typen.count("beitrag_start") == typen.count("beitrag_ende") == 2
    assert "synthese_ende" in typen and typen[-1] == "fertig"


def test_stellen_check_unter_chatgpt(attrappe, kein_claude, chatgpt, tmp_path):
    import beirat_engine as be

    d = be.Debatte("Stellen-Check: Testrolle (synthetisch)", "Kontext (synthetisch)", 2, None, "anthropic",
                   "gpt-4o-mini", modus="stellen_check", job_titel="Testrolle", job_firma="Testfirma")
    asyncio.run(d.laufen())

    assert d.status == "fertig" and d.fehler is None
    assert d.entscheidung["ampel"] == "Bewerben" and d.entscheidung["stimmen"]["Bewerben"] == 7
    assert d.synthese_fehler is None and d.check_synthese["empfehlung"] == "Empfehlung (synthetisch)."
    assert (tmp_path / "berichte" / Path(d.dashboard_pfad).name).is_file()
    aufrufe = attrappe.aufrufe()
    assert len(aufrufe) == d.num_turns == 13                      # 3 Dispatch, 2 Beiträge, 7 Voten, 1 Synthese
    assert all(a["gesetzt"] == [] for a in aufrufe)
    assert d.kosten_usd == 0.0
    assert "delta" not in [e["typ"] for e in _ereignisse(d)]


def test_abo_limit_beendet_die_debatte_mit_klarer_meldung(attrappe, kein_claude, chatgpt, monkeypatch):
    import beirat_engine as be

    monkeypatch.setenv("ATTRAPPE_MODUS", "limit")
    d = be.Debatte("Testfrage fuer den Beirat (synthetisch)", "", 2, None, "anthropic", "gpt-4o-mini")
    asyncio.run(d.laufen())

    assert d.status == "fehler" and "Nutzungslimit Ihres ChatGPT-Abos" in d.fehler
    assert len(attrappe.aufrufe()) == 2                            # Dispatch: 1 Versuch + 1 Retry, dann Abbruch
    assert d.beitraege == []
