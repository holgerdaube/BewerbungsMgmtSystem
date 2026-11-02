"""Welche KI die headless-Läufe ausführt: Claude (`claude -p`) oder ChatGPT (`codex exec`), P2-86.

Queue, Ketten, Timeout und Abbruch bleiben in `agent_runner` und sind für beide gleich. Hier steht nur, was sich
unterscheidet: Aufruf, Umgebung und Auswertung des Ausgabestroms. Claude Code bleibt der Standard und läuft
unverändert über `agent_runner._argv`.

ChatGPT: Die Läufe nutzen die Anmeldung des Rechners (`codex login`), keinen API-Schlüssel. Skills bleiben eine
Quelle: `.claude/skills` wird vor jedem Lauf nach `.agents/skills` gespiegelt, dort sucht Codex. Die Spiegelung ist
nicht versioniert. `AGENTS.md` im Projekt übersetzt die Werkzeugnamen der Skills.

Eine Budgetgrenze je Lauf gibt es bei Codex nicht, und Kosten in USD meldet es nicht. Schutz sind das Zeitlimit des
Laufs und die Grenzen des Abos; `AgentTask.tokens` hält den Verbrauch fest.
"""
from __future__ import annotations

import filecmp
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

from sqlalchemy.exc import OperationalError
from sqlmodel import Session

from app.db import DATA_DIR, engine
from app.models import SuchEinstellung

CLAUDE = "claude"
CHATGPT = "chatgpt"
STANDARD = CLAUDE
LABEL = {CLAUDE: "Claude", CHATGPT: "ChatGPT"}

CODEX_BIN = os.environ.get("CODEX_BIN", "codex")

# Die gespeicherten Modellwerte bleiben die Stufen-Namen aus `agent_runner.MODELLE`: So überlebt die Wahl je Funktion
# einen Wechsel der KI. Fable-Regel gilt unverändert, die Stufen gibt es nur hier und in `MODELLE`.
CODEX_MODELL = {"opus": "gpt-6.1-sol", "sonnet": "gpt-6.1-terra", "haiku": "gpt-6-luna"}
CODEX_MODELL_OPTIONEN = [
    {"alias": "opus", "label": "GPT-6.1 Sol (stark, verbraucht das Abo am schnellsten)"},
    {"alias": "sonnet", "label": "GPT-6.1 Terra"},
    {"alias": "haiku", "label": "GPT-6 Luna (sparsam)"},
]

# Diese Läufe erneuern das Gmail-Token, sie müssen im Ordner der Zugangsdaten schreiben dürfen.
_MAIL_LAEUFE = {"email-check", "mail-antwort", "nachfass-mail", "gespraech-debrief", "mail-jobsuche"}
# Würde Codex auf einen getrennt abgerechneten API-Schlüssel umstellen statt auf das Abo.
_API_SCHLUESSEL = ("OPENAI_API_KEY", "CODEX_API_KEY")
_ABO_LIMIT_RE = re.compile(r"usage limit|rate limit|quota|too many requests|\b429\b", re.I)
_ANMELDUNG_RE = re.compile(r"not logged in|log ?in|unauthorized|\b401\b|authentication", re.I)

_SPIEGEL_LOCK = threading.Lock()


def aktiv(session: Optional[Session] = None) -> str:
    """Der gewählte Anbieter. Fehlt die Einstellung oder ist sie unbekannt, gilt der Standard."""
    def _lesen(s: Session) -> str:
        e = s.get(SuchEinstellung, 1)
        wert = getattr(e, "ki_anbieter", None) if e else None
        return wert if wert in LABEL else STANDARD
    if session is not None:
        return _lesen(session)
    try:
        with Session(engine) as s:
            return _lesen(s)
    except OperationalError:    # Tabelle oder Spalte noch nicht da: Der Runner darf daran nie scheitern
        return STANDARD


def modell_optionen(anbieter: str, claude_optionen: list) -> list:
    return CODEX_MODELL_OPTIONEN if anbieter == CHATGPT else claude_optionen


def _programm(name: str) -> Optional[str]:
    return shutil.which(name) or (name if Path(name).is_file() else None)


def codex_angemeldet() -> Optional[bool]:
    """True oder False, None wenn Codex fehlt oder keine Antwort gibt. Liest nie ein Token."""
    programm = _programm(CODEX_BIN)
    if not programm:
        return None
    try:
        r = subprocess.run([programm, "login", "status"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.returncode == 0 and "logged in" in (r.stdout + r.stderr).lower()


def status(claude_bin: str, secrets_dir: Path) -> dict:
    """Für die Karte in den Einstellungen: installiert und angemeldet, je Anbieter."""
    claude_da = bool(_programm(claude_bin))
    env_datei = secrets_dir / "agent.env"
    try:
        schluessel = env_datei.exists() and "CLAUDE_CODE_OAUTH_TOKEN=" in env_datei.read_text(encoding="utf-8")
    except OSError:
        schluessel = False
    return {
        CLAUDE: {"label": LABEL[CLAUDE], "installiert": claude_da, "angemeldet": True if schluessel else None},
        CHATGPT: {"label": LABEL[CHATGPT], "installiert": bool(_programm(CODEX_BIN)), "angemeldet": codex_angemeldet()},
    }


def skills_spiegeln(projekt: Path) -> None:
    """`.claude/skills` nach `.agents/skills`: fehlende und geänderte Dateien kopieren, Überzähliges entfernen."""
    quelle, ziel = projekt / ".claude" / "skills", projekt / ".agents" / "skills"
    if not quelle.is_dir():
        return
    with _SPIEGEL_LOCK:
        soll = {p.relative_to(quelle) for p in quelle.rglob("*") if p.is_file()}
        for rel in soll:
            q, z = quelle / rel, ziel / rel
            if not z.exists() or not filecmp.cmp(q, z, shallow=False):
                z.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(q, z)
        if ziel.is_dir():
            for p in sorted(ziel.rglob("*"), reverse=True):
                rel = p.relative_to(ziel)
                if p.is_file() and rel not in soll:
                    p.unlink()
                elif p.is_dir() and not any(p.iterdir()):
                    p.rmdir()


def codex_argv(kind: str, spec: dict, modell_alias: Optional[str], standard_alias: str, projekt: Path,
               log_dir: Path, secrets_dir: Path) -> list[str]:
    """Aufruf von `codex exec`. Der Prompt kommt über die Standardeingabe (`-`), auf Windows sind Längen und
    Zeilenumbrüche in Argumenten heikel. Die Sandbox begrenzt das Schreiben auf das Projekt plus die Ordner hier."""
    alias = modell_alias or spec.get("model") or standard_alias
    modell = CODEX_MODELL.get(alias, CODEX_MODELL[standard_alias])
    gesperrt = set(spec.get("disallowed_tools") or ())
    web = "disabled" if {"WebSearch", "WebFetch"} <= gesperrt else "live"
    argv = [
        _programm(CODEX_BIN) or CODEX_BIN, "exec", "--json", "--skip-git-repo-check", "--ignore-user-config",
        "-s", "workspace-write",
        "-c", "sandbox_workspace_write.network_access=true",   # lokale API und Bibliotheken wie apify_client
        "-c", f'web_search="{web}"',
        # Sonst filtert Codex alles mit KEY, SECRET oder TOKEN im Namen aus den Befehlen, auch APIFY_TOKEN.
        "-c", "shell_environment_policy.ignore_default_excludes=true",
        "-C", str(projekt), "-m", modell,
    ]
    if spec.get("effort"):
        argv += ["-c", f'model_reasoning_effort="{spec["effort"]}"']
    weitere = [log_dir]
    if kind in _MAIL_LAEUFE:
        weitere.append(secrets_dir)
    daten = Path(DATA_DIR)
    if not daten.resolve().is_relative_to(projekt.resolve()):
        weitere.append(daten)
    for ordner in weitere:
        if Path(ordner).is_dir():
            argv += ["--add-dir", str(ordner)]
    return argv + ["-"]


def codex_prompt(prompt: str, kind: str, spec: dict) -> str:
    """Nennt den Skill ausdrücklich: Ein Auslöser-Satz allein ist unter Codex nicht zuverlässig."""
    skill = spec.get("skill") or kind
    return f"Verwende den Skill ${skill}: Lies zuerst .agents/skills/{skill}/SKILL.md und folge ihm. Auftrag: {prompt}"


def codex_umgebung(env: dict) -> dict:
    env = dict(env)
    for name in _API_SCHLUESSEL + ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
        env.pop(name, None)
    env["BMS_PDF_UEBER_SERVER"] = "1"      # LibreOffice läuft nicht in der Sandbox, s. cv_export._pdf_ueber_server
    return env


class CodexAuswertung:
    """Macht aus dem JSONL-Strom von `codex exec` das Ergebnis, das der Runner von `claude -p` kennt."""

    def __init__(self) -> None:
        self.letzte_nachricht = ""
        self.fehler = ""
        self.turns = 0
        self.neue_token = 0
        self.turn_fertig = False

    def ereignis(self, ev: dict) -> None:
        typ = ev.get("type")
        if typ == "item.completed":
            item = ev.get("item") or {}
            if item.get("type") == "agent_message" and item.get("text"):
                self.letzte_nachricht = item["text"]
        elif typ == "turn.completed":
            self.turns += 1
            self.turn_fertig = True
            self.fehler = ""        # Vorübergehende `error`-Ereignisse (etwa Verbindungsaufbau) sind damit überholt
            u = ev.get("usage") or {}
            self.neue_token += (u.get("input_tokens") or 0) - (u.get("cached_input_tokens") or 0) + (u.get("output_tokens") or 0)
        elif typ == "turn.failed":
            self.fehler = ((ev.get("error") or {}).get("message") or "Lauf fehlgeschlagen")
        elif typ == "error":
            self.fehler = ev.get("message") or "Fehler"

    def ergebnis(self, rohzeile: str = "") -> dict:
        fehler = self.fehler or ("" if self.turn_fertig else rohzeile)
        subtype = "success"
        if fehler:
            if _ABO_LIMIT_RE.search(fehler):
                subtype = "abo_limit"
                fehler = f"Das Nutzungslimit Ihres ChatGPT-Abos ist erreicht. Später erneut starten. ({fehler[:200]})"
            elif _ANMELDUNG_RE.search(fehler):
                subtype = "anmeldung"
                fehler = f"Die ChatGPT-Anmeldung fehlt oder ist abgelaufen: im Terminal `codex login`. ({fehler[:200]})"
            else:
                subtype = "error"
        return {"type": "result", "subtype": subtype, "is_error": bool(fehler),
                "result": fehler or self.letzte_nachricht, "num_turns": self.turns,
                "total_cost_usd": 0.0, "tokens": self.neue_token}
