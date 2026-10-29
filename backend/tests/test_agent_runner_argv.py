"""Tests für Phase 86 Stufe C (`_argv()`-Startballast) und die HEADLESS_SUFFIX-Ergänzungen aus
Stufe A2/B1 (s. tasks/spec_phase86_tageslauf_bereinigung.md).

Anlass: Ein Leerlauf-Lauf (`claude -p "Antworte ausschliesslich mit: OK"`) kostet 48.500 Tokens
Startkontext, davon nur ~6,5k Projekt-Inhalt. `--strict-mcp-config` UND die BALLAST_TOOLS-Sperre
zusammen senken das auf ≈ 35.200 (−29 %, gemessen 21.08.2026). Diese Tests prüfen NUR die
gebauten `argv`/Prompt-Strings (das testbare Artefakt) — kein LLM-Verhalten.

App-Importe ausschließlich innerhalb der Testfunktionen (Konvention aus conftest.py — siehe
dessen Docstring zur Import-Reihenfolge; Muster übernommen aus test_agent_runner_prompts.py).
"""


def test_argv_enthaelt_strict_mcp_config():
    """C1: --strict-mcp-config muss in JEDEM Lauf stehen (kein MCP-Server hat einen
    Aufrufpfad in einem Skill dieses Projekts, s. Befund 4 der Spec)."""
    from app.agent_runner import _argv

    argv = _argv("x", "jobsuche")

    assert "--strict-mcp-config" in argv


def test_argv_disallowed_tools_greift_auch_ohne_eigene_sperrliste():
    """C2-Regression: vor Phase 86 lief der --disallowed-tools-Block nur, wenn
    PROMPTS[kind]['disallowed_tools'] gesetzt war — dann griff BALLAST_TOOLS nur bei
    email-check. 'jobsuche' hat KEINE eigene Sperrliste und muss die Ballast-Tools trotzdem
    bekommen."""
    from app.agent_runner import BALLAST_TOOLS, _argv

    argv = _argv("x", "jobsuche")

    assert "--disallowed-tools" in argv
    idx = argv.index("--disallowed-tools")
    gesperrt = argv[idx + 1].split(",")
    assert "Workflow" in gesperrt
    assert set(BALLAST_TOOLS).issubset(set(gesperrt))


def test_argv_disallowed_tools_ist_additiver_merge_fuer_email_check():
    """C2-Kernregel: additiv, nicht ersetzend. email-check hat in PROMPTS eine eigene
    Sperrliste (WebSearch/WebFetch) — die muss NEBEN den Ballast-Tools stehen, nicht
    stattdessen."""
    from app.agent_runner import _argv

    argv = _argv("x", "email-check")

    idx = argv.index("--disallowed-tools")
    gesperrt = argv[idx + 1].split(",")
    assert "WebSearch" in gesperrt
    assert "WebFetch" in gesperrt
    assert "Workflow" in gesperrt


def test_argv_sperrt_niemals_die_vier_augen_und_kern_werkzeuge():
    """Fallstrick aus der Spec: Task/Agent, ToolSearch, Skill, Bash dürfen NIE in der
    Sperrliste landen — sonst bricht die Vier-Augen-Verifikation bzw. das Nachladen von
    WebFetch/WebSearch über ToolSearch weg."""
    from app.agent_runner import _argv

    for kind in ("jobsuche", "email-check"):
        argv = _argv("x", kind)
        idx = argv.index("--disallowed-tools")
        gesperrt = argv[idx + 1].split(",")
        for werkzeug in ("Task", "Agent", "ToolSearch", "Skill", "Bash"):
            assert werkzeug not in gesperrt, f"{werkzeug} darf für {kind} nicht gesperrt sein"


def test_build_prompt_enthaelt_data_tmp_hinweis():
    """A2: der neue Zwischendateien-Absatz muss im fertigen Prompt stehen."""
    from app.agent_runner import build_prompt

    prompt = build_prompt("jobsuche", None)

    assert "data/tmp/" in prompt


def test_build_prompt_enthaelt_shell_stil_hinweis():
    """B1: der neue Shell-Stil-Absatz muss im fertigen Prompt stehen."""
    from app.agent_runner import build_prompt

    prompt = build_prompt("jobsuche", None)

    assert "KEINE Shell-Schleifen" in prompt


def test_buendelungs_regel_ist_bewusst_nicht_mehr_im_prompt():
    """P2-23 (28.08.2026): Phase 88 hatte hier eine Regel „Tool-Aufrufe bündeln" verankert —
    Hypothese: Die Kette verliert Zeit, weil jede Antwort nur EINEN Aufruf absetzt.

    Gemessen am Tageslauf vom 28.08., bei dem die Regel nachweislich im Prompt stand (ein Lauf im Bestand):
    Die Quote blieb bei exakt 1,00 Aufrufen je Antwort. Unabhängig gegengeprüft am Rohlog —
    128 Antworten, jede mit genau einem Aufruf, kein einziges Mal zwei. Die Regel hat nichts
    bewirkt und ist deshalb entfernt worden, statt als Deko stehen zu bleiben.

    Dieser Test hält den Befund fest: Wer sie wieder einbaut, soll vorher eine Messung haben,
    die eine Wirkung zeigt."""
    from app.agent_runner import build_prompt

    prompt = build_prompt("jobsuche", None)

    assert "Tool-Aufrufe bündeln" not in prompt
    # Die übrigen Regeln des Suffixes bleiben davon unberührt.
    assert "Zwischendateien" in prompt and "Shell-Stil" in prompt
