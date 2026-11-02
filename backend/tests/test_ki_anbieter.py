"""P2-86: KI-Anbieter wählbar. Aufruf und Auswertung von `codex exec`, Spiegelung der Skills, Einstellung, Lauf mit Attrappe."""
import asyncio
import json
import stat
import sys
import textwrap

import pytest

from app import agent_runner as ar
from app import ki_anbieter as ki
from app.models import AgentTask, SuchEinstellung


def _argv(kind="firma-pruefen", spec=None, alias=None, tmp=None):
    return ki.codex_argv(kind, spec if spec is not None else ar.PROMPTS[kind], alias, "sonnet", tmp, tmp / "logs", tmp / "secrets")


def test_aufruf_nutzt_abo_sandbox_und_standardmodell(tmp_path):
    argv = _argv(tmp=tmp_path)
    assert argv[1:3] == ["exec", "--json"] and argv[-1] == "-"
    assert "--ignore-user-config" in argv and "--skip-git-repo-check" in argv
    assert argv[argv.index("-s") + 1] == "workspace-write"
    assert argv[argv.index("-C") + 1] == str(tmp_path)
    assert argv[argv.index("-m") + 1] == ki.CODEX_MODELL["sonnet"]
    assert "sandbox_workspace_write.network_access=true" in argv
    assert 'web_search="live"' in argv
    assert "shell_environment_policy.ignore_default_excludes=true" in argv


def test_jede_stufe_hat_ein_codex_modell_und_fable_bleibt_draussen():
    assert set(ki.CODEX_MODELL) == set(ar.MODELL_ALIASE)
    assert {m["alias"] for m in ki.CODEX_MODELL_OPTIONEN} == set(ar.MODELL_ALIASE)
    assert not set(ki.CODEX_MODELL) & set(ar.GESPERRTE_MODELLE)


def test_gewaehltes_modell_und_effort(tmp_path):
    argv = _argv(alias="opus", tmp=tmp_path)
    assert argv[argv.index("-m") + 1] == ki.CODEX_MODELL["opus"]
    argv = _argv("job-frage", tmp=tmp_path)       # feste Wahl im PROMPTS-Eintrag: sonnet, high
    assert argv[argv.index("-m") + 1] == ki.CODEX_MODELL["sonnet"]
    assert 'model_reasoning_effort="high"' in argv


def test_web_aus_wenn_beide_werkzeuge_gesperrt(tmp_path):
    assert 'web_search="disabled"' in _argv("profil-einlesen", tmp=tmp_path)
    assert 'web_search="live"' in _argv("x", {"disallowed_tools": ["WebSearch"]}, tmp=tmp_path)


def test_zugangsdaten_nur_fuer_mail_laeufe_schreibbar(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "secrets").mkdir()
    assert str(tmp_path / "secrets") not in _argv(tmp=tmp_path)
    mail = _argv("email-check", tmp=tmp_path)
    assert mail[mail.index(str(tmp_path / "secrets")) - 1] == "--add-dir"
    assert str(tmp_path / "logs") in mail


def test_prompt_nennt_den_skill():
    assert ki.codex_prompt("Auftrag", "firma-pruefen", {}).startswith("Verwende den Skill $firma-pruefen: Lies zuerst .agents/skills/firma-pruefen/SKILL.md")
    assert "$jobsuche:" in ki.codex_prompt("x", "jobsuche-apify", ar.PROMPTS["jobsuche-apify"])


def test_jede_headless_art_mit_ki_hat_einen_skill():
    skills = {p.parent.name for p in ar.PROJECT_ROOT.glob(".claude/skills/*/SKILL.md")}
    for kind, spec in ar.PROMPTS.items():
        if spec.get("headless") and not spec.get("local_cmd") and not kind.startswith("beirat-") or kind == "beirat-persona":
            assert (spec.get("skill") or kind) in skills, kind


def test_umgebung_ohne_claude_token_und_api_schluessel():
    env = ki.codex_umgebung({"PATH": "/x", "CLAUDE_CODE_OAUTH_TOKEN": "a", "OPENAI_API_KEY": "b", "CODEX_API_KEY": "c", "APIFY_TOKEN": "d"})
    assert env == {"PATH": "/x", "APIFY_TOKEN": "d", "BMS_PDF_UEBER_SERVER": "1"}


def test_child_env_chatgpt_gibt_den_claude_token_nicht_weiter(tmp_path, monkeypatch):
    datei = tmp_path / "agent.env"
    datei.write_text("CLAUDE_CODE_OAUTH_TOKEN=geheim\nAPIFY_TOKEN=apify\n", encoding="utf-8")
    monkeypatch.setattr(ar, "ENV_FILE", datei)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    env, hinweis = ar._child_env("jobsuche-apify", ki.CHATGPT)
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env and "OPENAI_API_KEY" not in env and env["APIFY_TOKEN"] == "apify"
    assert hinweis is None
    env, _ = ar._child_env("jobsuche-apify", ki.CLAUDE)
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "geheim"


# ── Auswertung ──────────────────────────────────────────────────────────────────────────────────
def _lauf(*ereignisse):
    a = ki.CodexAuswertung()
    for ev in ereignisse:
        a.ereignis(ev)
    return a


def test_auswertung_erfolg_mit_letzter_nachricht_und_token():
    e = _lauf({"type": "item.completed", "item": {"type": "agent_message", "text": "eins"}},
              {"type": "item.completed", "item": {"type": "command_execution"}},
              {"type": "item.completed", "item": {"type": "agent_message", "text": "Fertig."}},
              {"type": "turn.completed", "usage": {"input_tokens": 1000, "cached_input_tokens": 800, "output_tokens": 50}}).ergebnis()
    assert e["is_error"] is False and e["subtype"] == "success" and e["result"] == "Fertig."
    assert e["tokens"] == 250 and e["num_turns"] == 1 and e["total_cost_usd"] == 0.0


@pytest.mark.parametrize("meldung,subtype,text", [
    ("You've hit your usage limit", "abo_limit", "Nutzungslimit"),
    ("429 Too Many Requests", "abo_limit", "Nutzungslimit"),
    ("Not logged in", "anmeldung", "codex login"),
    ("401 Unauthorized", "anmeldung", "codex login"),
    ("Modell nicht verfügbar", "error", "Modell nicht verfügbar"),
])
def test_auswertung_fehlerarten(meldung, subtype, text):
    e = _lauf({"type": "turn.failed", "error": {"message": meldung}}).ergebnis()
    assert e["is_error"] is True and e["subtype"] == subtype and text in e["result"]


def test_voruebergehender_fehler_vor_erfolgreichem_turn_zaehlt_nicht():
    e = _lauf({"type": "error", "message": "Reconnecting... 1/5"},
              {"type": "item.completed", "item": {"type": "agent_message", "text": "Fertig."}},
              {"type": "turn.completed", "usage": {}}).ergebnis()
    assert e["is_error"] is False and e["result"] == "Fertig."


def test_abbruch_ohne_turn_ist_ein_fehler_mit_der_letzten_zeile():
    e = _lauf().ergebnis("codex: command failed")
    assert e["is_error"] is True and "command failed" in e["result"]


# ── Spiegel ─────────────────────────────────────────────────────────────────────────────────────
def test_skills_spiegeln(tmp_path):
    quelle = tmp_path / ".claude" / "skills" / "a"
    quelle.mkdir(parents=True)
    (quelle / "SKILL.md").write_text("eins", encoding="utf-8")
    (quelle / "references").mkdir()
    (quelle / "references" / "x.md").write_text("x", encoding="utf-8")
    ki.skills_spiegeln(tmp_path)
    ziel = tmp_path / ".agents" / "skills" / "a"
    assert (ziel / "SKILL.md").read_text(encoding="utf-8") == "eins" and (ziel / "references" / "x.md").exists()

    (quelle / "SKILL.md").write_text("zwei", encoding="utf-8")
    (quelle / "references" / "x.md").unlink()
    (quelle / "references").rmdir()
    weg = tmp_path / ".agents" / "skills" / "alt"
    weg.mkdir()
    (weg / "SKILL.md").write_text("alt", encoding="utf-8")
    ki.skills_spiegeln(tmp_path)
    assert (ziel / "SKILL.md").read_text(encoding="utf-8") == "zwei"
    assert not (ziel / "references").exists() and not weg.exists()


def test_spiegel_ohne_quelle_tut_nichts(tmp_path):
    ki.skills_spiegeln(tmp_path)
    assert not (tmp_path / ".agents").exists()


# ── Einstellung ─────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def zurueck_auf_claude(client):
    yield
    assert client.patch("/api/einstellungen", json={"ki_anbieter": "claude"}).status_code == 200


def test_einstellung_standard_wechsel_und_modelloptionen(client, zurueck_auf_claude):
    d = client.get("/api/einstellungen").json()
    assert d["ki_anbieter"] == "claude" and d["modell_optionen"] == ar.MODELLE
    assert {o["wert"] for o in d["ki_anbieter_optionen"]} == {"claude", "chatgpt"}

    gemischt = client.patch("/api/einstellungen", json={"ki_anbieter": "chatgpt"}).json()
    assert gemischt["ki_anbieter"] == "chatgpt" and gemischt["modell_optionen"] == ki.CODEX_MODELL_OPTIONEN
    assert ki.aktiv() == "chatgpt"
    # Die Modellwahl je Funktion übersteht den Wechsel: Gespeichert sind die Stufen
    assert client.patch("/api/einstellungen", json={"modelle": {"cv-match": "opus"}}).status_code == 200
    assert client.get("/api/einstellungen").json()["modelle"]["cv-match"] == "opus"
    assert client.patch("/api/einstellungen", json={"modelle": {"cv-match": "fable"}}).status_code == 422
    assert client.patch("/api/einstellungen", json={"modelle": {"cv-match": "sonnet"}}).status_code == 200


def test_patch_trifft_nie_die_echte_suchprofil_datei(client, zurueck_auf_claude):
    """Wache für die Umleitung in conftest.py: Die echte Datei gehört dem Nutzer."""
    from pipeline import suchprofil
    assert suchprofil.SUCHPROFILE_PATH != suchprofil.PROJECT_ROOT / "config" / "suchprofile.yaml"
    assert client.patch("/api/einstellungen", json={"ki_anbieter": "chatgpt"}).status_code == 200
    assert suchprofil.SUCHPROFILE_PATH.exists()


def test_pdf_laeuft_in_der_sandbox_ueber_den_server(monkeypatch, tmp_path):
    from pipeline import cv_export
    aufrufe = []

    class Antwort:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, *a): return json.dumps({"ok": True, "fehler": None}).encode()

    def urlopen(anfrage, timeout):
        aufrufe.append((anfrage.full_url, json.loads(anfrage.data)))
        return Antwort()

    monkeypatch.setattr(cv_export.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(cv_export, "_to_pdf_soffice", lambda *a: pytest.fail("LibreOffice darf in der Sandbox nicht starten"))
    monkeypatch.setenv("BMS_PDF_UEBER_SERVER", "1")
    monkeypatch.setenv("PORT", "18999")
    assert cv_export.to_pdf(tmp_path / "a.docx", tmp_path / "a.pdf") == (True, None)
    assert aufrufe[0][0] == "http://127.0.0.1:18999/api/intern/pdf"
    assert aufrufe[0][1]["pdf"].endswith("a.pdf")


def test_pdf_route_nimmt_nur_dateien_aus_dem_programm_und_den_daten(client, monkeypatch, tmp_path):
    from app import main
    from pipeline import cv_export
    gestartet = []
    monkeypatch.setattr(cv_export, "_to_pdf_soffice", lambda d, p: (gestartet.append((d, p)), (True, None))[1])
    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)
    (tmp_path / "outputs").mkdir()
    (tmp_path / "outputs" / "a.docx").write_bytes(b"x")
    gut = {"docx": str(tmp_path / "outputs" / "a.docx"), "pdf": str(tmp_path / "outputs" / "a.pdf")}
    assert client.post("/api/intern/pdf", json=gut).json() == {"ok": True, "fehler": None}
    assert len(gestartet) == 1
    for schlecht in ({**gut, "docx": "/etc/passwd"}, {**gut, "pdf": "/tmp/fremd/a.pdf"}, {**gut, "pdf": str(tmp_path / "outputs" / "a.txt")},
                     {**gut, "docx": str(tmp_path / "outputs" / "fehlt.docx")}, {}):
        assert client.post("/api/intern/pdf", json=schlecht).status_code == 422
    assert len(gestartet) == 1


def test_einstellung_unbekannter_anbieter(client):
    assert client.patch("/api/einstellungen", json={"ki_anbieter": "gemini"}).status_code == 422


def test_status_ohne_programme(tmp_path, monkeypatch):
    monkeypatch.setattr(ki, "CODEX_BIN", str(tmp_path / "fehlt"))
    s = ki.status(str(tmp_path / "auchnicht"), tmp_path)
    assert s["chatgpt"] == {"label": "ChatGPT", "installiert": False, "angemeldet": None}
    assert s["claude"]["installiert"] is False


# ── Lauf mit Attrappe ───────────────────────────────────────────────────────────────────────────
ATTRAPPE = """\
    #!{python}
    import json, os, sys
    ziel = os.environ["ATTRAPPE_ZIEL"]
    open(ziel, "w", encoding="utf-8").write(json.dumps({{"argv": sys.argv[1:], "prompt": sys.stdin.read(),
        "claude": os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")}}))
    print(json.dumps({{"type": "thread.started"}}))
    print(json.dumps({{"type": "item.completed", "item": {{"type": "agent_message", "text": "Alles erledigt."}}}}))
    print(json.dumps({{"type": "turn.completed", "usage": {{"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 10}}}}))
    sys.exit({rc})
"""


def _attrappe(tmp_path, monkeypatch, rc=0):
    programm = tmp_path / "codex_attrappe"
    programm.write_text(textwrap.dedent(ATTRAPPE).format(python=sys.executable, rc=rc), encoding="utf-8")
    programm.chmod(programm.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(ki, "CODEX_BIN", str(programm))
    monkeypatch.setenv("ATTRAPPE_ZIEL", str(tmp_path / "aufruf.json"))
    projekt = tmp_path / "projekt"
    (projekt / ".claude" / "skills" / "firma-pruefen").mkdir(parents=True)
    (projekt / ".claude" / "skills" / "firma-pruefen" / "SKILL.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr(ar, "PROJECT_ROOT", projekt)
    return projekt


def _laeuft_durch(session, kind="firma-pruefen"):
    from sqlmodel import Session
    from app.db import engine
    task = AgentTask(kind=kind, prompt="Firma prüfen für Job 1", status="queued")
    session.add(task)
    session.commit()
    session.refresh(task)
    asyncio.run(ar._run_task(task.id))
    with Session(engine) as s:
        return s.get(AgentTask, task.id)


@pytest.mark.skipif(sys.platform == "win32", reason="Attrappe ist ein Shebang-Skript")
def test_lauf_unter_chatgpt(client, session, tmp_path, monkeypatch, zurueck_auf_claude):
    projekt = _attrappe(tmp_path, monkeypatch)
    client.patch("/api/einstellungen", json={"ki_anbieter": "chatgpt"})

    t = _laeuft_durch(session)

    assert t.status == "done" and t.tokens == 70 and t.cost_usd == 0.0 and t.num_turns == 1
    assert json.loads(t.result_json)["result"] == "Alles erledigt."
    aufruf = json.loads((tmp_path / "aufruf.json").read_text(encoding="utf-8"))
    assert aufruf["prompt"].startswith("Verwende den Skill $firma-pruefen") and "Firma prüfen für Job 1" in aufruf["prompt"]
    assert aufruf["claude"] is None and aufruf["argv"][0] == "exec"
    assert (projekt / ".agents" / "skills" / "firma-pruefen" / "SKILL.md").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="Attrappe ist ein Shebang-Skript")
def test_lauf_unter_chatgpt_mit_fehler_wird_nicht_als_erfolg_gewertet(client, session, tmp_path, monkeypatch, zurueck_auf_claude):
    _attrappe(tmp_path, monkeypatch, rc=1)
    client.patch("/api/einstellungen", json={"ki_anbieter": "chatgpt"})
    t = _laeuft_durch(session)      # firma-pruefen darf einmal wiederholt werden
    assert t.status != "done" and t.error


def test_fehlendes_programm_ist_eine_klare_meldung(client, session, tmp_path, monkeypatch, zurueck_auf_claude):
    monkeypatch.setattr(ki, "CODEX_BIN", str(tmp_path / "gibtsnicht"))
    monkeypatch.setattr(ar, "PROJECT_ROOT", tmp_path)
    client.patch("/api/einstellungen", json={"ki_anbieter": "chatgpt"})
    t = _laeuft_durch(session)
    assert t.status == "failed" and "gibtsnicht" in t.error


def test_claude_aufruf_bleibt_unberuehrt(client, zurueck_auf_claude):
    argv = ar._argv("Auftrag", "firma-pruefen", "sonnet")
    assert argv[1:3] == ["-p", "Auftrag"] and "--max-budget-usd" in argv and "--strict-mcp-config" in argv
