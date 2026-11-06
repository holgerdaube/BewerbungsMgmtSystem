"""Sprache der Konsolenmeldungen des Servers (P2-95).

Der Server läuft im Terminalfenster des Starts. Seine `print`-Zeilen folgen der Sprache des Betriebssystems
und nicht der Oberflächensprache aus `sprache.py`: Wer ein deutsches System hat, liest Deutsch, alle anderen
lesen Englisch (British English). Weitere Sprachen gibt es nicht.

Erkennung, immer in dieser Reihenfolge:
1. Umgebungsvariable `BMS_TERMINAL_SPRACHE` (`de` oder `en`),
2. macOS: erster Eintrag von `defaults read -g AppleLanguages`, sonst `AppleLocale`;
   Windows: `GetUserDefaultUILanguage`; sonst `LC_ALL`, `LC_MESSAGES`, `LANG`,
3. beginnt der Wert mit `de`, gilt Deutsch; alles andere und jeder Fehler ergibt Englisch.

Reine Standardbibliothek, kein Import aus `app`: Das Modul läuft auch aus dem Selbsttest und vor der Datenbank.
Der Katalog (`texte/en_terminal.json`) ist absichtlich nicht `en.json`, weil diese Zeilen nicht der Oberfläche
folgen. Fehlt ein Eintrag, kommt der deutsche Text, nichts bricht.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ENV_NAME = "BMS_TERMINAL_SPRACHE"
_KATALOG_DATEI = Path(__file__).resolve().parent / "texte" / "en_terminal.json"

_sprache: str | None = None
_katalog: dict[str, str] | None = None


def _aus_wert(wert: str | None) -> str | None:
    """`de` oder `en` für einen Sprach- oder Locale-Wert, None wenn er leer ist."""
    wert = (wert or "").strip().strip('"').lower()
    if not wert:
        return None
    return "de" if wert.startswith("de") else "en"


def _macos() -> str | None:
    try:
        r = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True, text=True,
                           timeout=3)
        if r.returncode == 0:
            m = re.search(r'\(\s*"?([A-Za-z0-9_@=.\-]+)', r.stdout)
            if m:
                return _aus_wert(m.group(1))
    except Exception:  # noqa: BLE001 -- jeder Fehler führt zum nächsten Weg
        pass
    try:
        r = subprocess.run(["defaults", "read", "-g", "AppleLocale"], capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            return _aus_wert(r.stdout)
    except Exception:  # noqa: BLE001
        pass
    return None


def _windows() -> str | None:
    try:
        import ctypes
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore[attr-defined]
        return "de" if (lang_id & 0x3FF) == 0x07 else "en"   # 0x07 = LANG_GERMAN
    except Exception:  # noqa: BLE001
        return None


def _umgebung() -> str | None:
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        wert = os.environ.get(name, "").strip()
        if wert:
            return _aus_wert(wert)
    return None


def _erkennen() -> str:
    try:
        vorgabe = os.environ.get(ENV_NAME, "").strip().lower()
        if vorgabe in ("de", "en"):
            return vorgabe
        gefunden = None
        if sys.platform == "darwin":
            gefunden = _macos()
        elif sys.platform == "win32":
            gefunden = _windows()
        return gefunden or _umgebung() or "en"
    except Exception:  # noqa: BLE001 -- die Erkennung darf nie einen Start aufhalten
        return "en"


def sprache() -> str:
    """`de` oder `en`, einmal je Prozess ermittelt."""
    global _sprache
    if _sprache is None:
        _sprache = _erkennen()
    return _sprache


def zuruecksetzen() -> None:
    """Verwirft die gemerkte Sprache und den Katalog (für Tests)."""
    global _sprache, _katalog
    _sprache = None
    _katalog = None


def _laden() -> dict[str, str]:
    global _katalog
    if _katalog is None:
        try:
            _katalog = json.loads(_KATALOG_DATEI.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"[terminal] WARNUNG: {_KATALOG_DATEI.name} nicht lesbar: {exc}", flush=True)
            _katalog = {}
    return _katalog


def tt(deutsch: str, /, **werte) -> str:
    """Konsolentext in der Terminal-Sprache, Platzhalter im Stil `{name}`. Nur mit Literal aufrufen, sonst
    findet der Wächtertest den Text nicht. Deutsch bleibt unverändert, Englisch kommt aus dem Katalog. Wirft nie."""
    text = deutsch if sprache() == "de" else _laden().get(deutsch, deutsch)
    if not werte:
        return text
    try:
        return text.format(**werte)
    except (KeyError, IndexError, ValueError):
        try:
            return deutsch.format(**werte)
        except (KeyError, IndexError, ValueError):
            return text
