"""Pfad-Wächter für Hintergrund-Läufe (P2-38).

Anlass: Fund der Datei `Bewerbung_Mgmt_System_inspect.py` unter iCloud Drive/40_Claude/ —
geschrieben von einem headless cv-match-Lauf, der beim Pfad-Zusammenbau `10_aktive_Projekte/`
ausließ und aus `/` ein `_` machte. Kein BMS-Code nutzt diesen falschen Pfad — die KI erzeugt ihn
selbst in Hintergrund-Läufen: gemessen 109 von rund 880 geloggten Läufen seit 13.08., quer durch
acht Skills. Meist harmlos (`cd <alt> 2>/dev/null; cd <neu>`), aber 18 Write/Edit-Aufrufe landeten
tatsächlich außerhalb des Projekts. Nichts hielt sie auf: `automation/agent_settings.json` erlaubte
Write/Edit bislang ohne jede Pfadbeschränkung.

Verhalten: Dieses Skript läuft als PreToolUse-Hook für Write/Edit/MultiEdit/NotebookEdit, eingetragen
ausschließlich in `automation/agent_settings.json` — geladen wird diese Datei nur vom Agent-Runner
(`claude --settings automation/agent_settings.json`, s. `backend/app/agent_runner.py`). Interaktive
Sitzungen sind davon nicht betroffen. Der Hook bekommt JSON auf stdin (u. a.
`tool_name`, `tool_input`, `cwd`), ermittelt daraus das Schreibziel und sperrt (stderr-Meldung,
Exit-Code 2 — Claude Code bricht den Aufruf ab und reicht die Meldung an die KI zur Korrektur
weiter), wenn das Ziel weder innerhalb der Projektwurzel noch innerhalb einer bekannten Temp-Wurzel
liegt. Sonst Exit 0.

Erlaubt sind:
  - die Projektwurzel — abgeleitet aus dem Ort DIESES Skripts (`Path(__file__).resolve().parents[1]`),
    kein persönlicher Pfad im Repo (Phase 71: Repo bleibt personendatenfrei).
  - bekannte Temp-Wurzeln: `tempfile.gettempdir()`, `/tmp`, `/private/tmp`, `/var/folders`,
    `/private/var/folders`.
Ausnahme im Projekt (P2-53): `backend/data/` ist gesperrt. Der Ordner gehört zu keinem Code, Läufe
landen dort nur durch ein nachwirkendes `cd backend`; die Meldung nennt den richtigen Ort.

„Innerhalb“ heißt echter Pfadvergleich (`os.path.commonpath`), keine Zeichenketten-Präfixprüfung —
ein Nachbarordner wie `Bewerbung_Mgmt_System_alt/` darf NICHT als „im Projekt“ durchgehen.
Pfad-Traversal (`<projekt>/../x.py`) löst `os.path.realpath` vorher auf und wird damit erkannt.

Fail-open (bewusst): leere oder unlesbare Eingabe, kein erkennbares Ziel, ein anderes Tool oder ein
unerwarteter interner Fehler führen zu Exit 0 ohne Ausgabe. Dieser Wächter ist ein Sicherheitsnetz
gegen Fehlgriffe, kein Pflichtweg für jeden Schreibzugriff — ein Fehler im Wächter selbst darf
keinen Skill-Lauf lahmlegen.

Grenze (ehrlich dokumentiert statt verschwiegen): Schreibwege über Bash (Python-Heredocs mit
`open(...)`, Shell-Redirects `>`) deckt dieser Wächter NICHT ab — er prüft nur die Werkzeuge
Write/Edit/MultiEdit/NotebookEdit. Gemessen liefen alle 18 Fehlgriffe aus diesem Fund über genau
diese Werkzeuge; wiederholtes `cd`/`cp`/`ls` außerhalb des Arbeitsordners blockt Claude Code bereits
selbst (empirisch belegt). Seit P2-53 prüft er zusätzlich EIN Bash-Muster (eigener Matcher `Bash` in
`agent_settings.json`): ein relatives `data/tmp` aus einem Arbeitsordner unter `backend/`, s.
`_bash_pruefen`. Alle anderen Bash-Schreibwege bleiben ungeprüft.

Details und Testabdeckung: `tasks/spec_p2-38_pfad_waechter.md`, `backend/tests/test_pfad_waechter.py`.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

# Aus dem Ort DIESES Skripts abgeleitet — automation/pfad_waechter.py liegt eine Ebene unter der
# Projektwurzel. Bewusst kein persönlicher Pfad im Repo (Phase 71).
_PROJEKTWURZEL = Path(__file__).resolve().parents[1]

# Wurzeln, unter denen Hilfsdateien unkritisch sind (s. Moduldocstring, §2 der Spec).
_STANDARD_TEMP_WURZELN: tuple[str, ...] = (
    tempfile.gettempdir(),
    "/tmp",
    "/private/tmp",
    "/var/folders",
    "/private/var/folders",
)

_GEPRUEFTE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")

_SPERRTEXT_VORLAGE = (
    "Pfad-Wächter: Schreiben außerhalb des Projekts ist in Hintergrund-Läufen gesperrt: {ziel}. "
    "Projektwurzel: {wurzel} — Hilfsdateien nach {wurzel}/data/tmp/ schreiben, sonst relative "
    "Pfade ab der Projektwurzel verwenden."
)

# P2-53: `backend/data/` ist nie ein richtiger Ort (liegt im Projekt, fiel deshalb bisher durch).
# Dorthin geraten Läufe, weil ein `cd backend` in Claude Code für alle FOLGENDEN Befehle gilt.
_SPERRTEXT_BACKEND_DATA = (
    "Pfad-Wächter: {ziel} liegt unter backend/data/, dem falschen Ort. Zwischendateien gehören "
    "nach {wurzel}/data/tmp/. Vermutlich gilt noch ein früheres `cd backend`."
)
_SPERRTEXT_BASH_CWD = (
    "Pfad-Wächter: Dein Arbeitsordner ist {cwd}, ein früheres `cd backend` gilt weiter. Ein "
    "relatives data/tmp/… landet von dort in backend/data/tmp/, dem falschen Ort, und aus dem "
    "Projekt-Root findest du die Datei nicht wieder. Schreib ../data/tmp/… oder den absoluten "
    "Pfad {wurzel}/data/tmp/…, oder wechsle im selben Befehl zuerst mit cd in die Projektwurzel."
)
# Ein RELATIVES data/tmp: nicht Teil eines längeren Pfads wie ../data/tmp, /…/data/tmp oder
# backend/data/tmp, und nicht der Anfang eines längeren Namens wie data/tmpx.
_RELATIVES_DATA_TMP = re.compile(r"(?<![\w./~-])data/tmp(?![\w-])")


def _innerhalb(ziel: Path, wurzel: Path) -> bool:
    """True, wenn `ziel` unterhalb `wurzel` liegt — echter Pfadvergleich über
    `os.path.commonpath`, KEIN Zeichenketten-Präfixvergleich (`startswith`). Ein Nachbarordner
    wie `<wurzel>_alt/x.py` hat zwar den String `<wurzel>` als Präfix, aber einen anderen
    gemeinsamen Pfad (den jeweiligen Elternordner) — `commonpath` erkennt den Unterschied,
    `startswith` würde ihn übersehen (genau der Echtfall aus der Diagnose)."""
    try:
        return os.path.commonpath([str(wurzel), str(ziel)]) == str(wurzel)
    except ValueError:
        # z. B. unterschiedliche Laufwerke unter Windows — sicherheitshalber "nicht innerhalb".
        return False


def entscheiden(eingabe: dict, projektwurzel: Path, temp_wurzeln: tuple[str, ...] | None = None) -> str | None:
    """Reine Funktion: `None` = Schreibziel erlaubt, sonst der Sperrtext (für stderr bestimmt).

    `temp_wurzeln=None` verwendet die Standardliste aus dem Moduldocstring. Der Parameter ist
    bewusst injizierbar: Die Testumgebung selbst liegt unter einem Temp-Ordner (`tmp_path`) — ohne
    Injektion wäre in Tests jedes Ziel automatisch „erlaubt“, egal was geprüft werden soll."""
    tool_name = eingabe.get("tool_name")
    if tool_name == "Bash":
        return _bash_pruefen(eingabe, projektwurzel)
    if tool_name not in _GEPRUEFTE_TOOLS:
        return None

    tool_input = eingabe.get("tool_input") or {}
    ziel_roh = tool_input.get("notebook_path") if tool_name == "NotebookEdit" else tool_input.get("file_path")
    if not ziel_roh:
        return None

    ziel_pfad = Path(ziel_roh)
    if not ziel_pfad.is_absolute():
        cwd = eingabe.get("cwd") or os.getcwd()
        ziel_pfad = Path(cwd) / ziel_pfad

    ziel = Path(os.path.realpath(str(ziel_pfad)))
    wurzel_projekt = Path(os.path.realpath(str(projektwurzel)))

    if _innerhalb(ziel, wurzel_projekt / "backend" / "data"):
        return _SPERRTEXT_BACKEND_DATA.format(ziel=ziel, wurzel=wurzel_projekt)
    if _innerhalb(ziel, wurzel_projekt):
        return None

    for roh in (_STANDARD_TEMP_WURZELN if temp_wurzeln is None else temp_wurzeln):
        temp_wurzel = Path(os.path.realpath(str(roh)))
        if _innerhalb(ziel, temp_wurzel):
            return None

    return _SPERRTEXT_VORLAGE.format(ziel=ziel, wurzel=wurzel_projekt)


def _bash_pruefen(eingabe: dict, projektwurzel: Path) -> str | None:
    """Bash (P2-53), bewusst nur EIN Muster: Der Arbeitsordner liegt in `backend/` (ein früheres
    `cd backend` wirkt nach) und der Befehl nennt ein relatives `data/tmp`. Genau so entstand
    `backend/data/tmp/` (ein Lauf vom 28.09.2026: `cd backend` in Schritt 16, `cat > data/tmp/…`
    in Schritt 26, danach acht Schritte Suche nach der eigenen Datei). Beginnt der Befehl mit `cd`,
    beziehen sich seine relativen Pfade auf das neue Ziel: dann keine Prüfung. Ohne `cwd` in der
    Hook-Eingabe: fail-open wie überall."""
    befehl = (eingabe.get("tool_input") or {}).get("command")
    cwd = eingabe.get("cwd")
    if not befehl or not cwd:
        return None
    wurzel_projekt = Path(os.path.realpath(str(projektwurzel)))
    cwd_real = Path(os.path.realpath(str(cwd)))
    if not _innerhalb(cwd_real, wurzel_projekt / "backend"):
        return None
    if befehl.lstrip().startswith("cd ") or not _RELATIVES_DATA_TMP.search(befehl):
        return None
    return _SPERRTEXT_BASH_CWD.format(cwd=cwd_real, wurzel=wurzel_projekt)


def main() -> int:
    """Liest das Hook-JSON von stdin, entscheidet gegen die Projektwurzel aus dem Skript-Ort und
    meldet eine Sperre auf stderr mit Exit 2 — sonst Exit 0. Fail-open bei jedem Fehler (kaputtes
    JSON, unerwartete Struktur, u. Ä.): der Wächter darf einen Skill-Lauf nie lahmlegen."""
    try:
        rohdaten = sys.stdin.read()
        eingabe = json.loads(rohdaten) if rohdaten.strip() else {}
        if not isinstance(eingabe, dict):
            return 0
        sperrtext = entscheiden(eingabe, _PROJEKTWURZEL)
    except Exception:
        return 0

    if sperrtext is None:
        return 0
    print(sperrtext, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
