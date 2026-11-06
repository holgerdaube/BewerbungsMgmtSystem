"""Sprache der Oberfläche und der Berichte für den Nutzer (P2-88).

Die Sprache liegt zentral in der Datenbank (`SuchEinstellung.sprache`) und nicht im Browser, weil auch
Hintergrundläufe und Kommandozeilen sie brauchen. Getrennt davon: Lebenslauf, Anschreiben und Mails folgen
der Stellenanzeige beziehungsweise der Mail, nie dieser Einstellung.

Kein Zwischenspeicher im Prozess: Server und Kommandozeilen sind getrennte Prozesse, die Zeile ist schnell
gelesen.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from sqlmodel import Session

from app.db import engine
from app.models import SuchEinstellung
from app.terminal import tt

SPRACHEN = ("de", "en")
STANDARD = "de"


def gespeichert() -> str:
    """Der Rohwert der Einstellung, "" wenn noch nie eine Sprache gewählt wurde. Wirft nie: Eine fehlende
    Tabelle oder eine gesperrte Datenbank darf weder den Start noch einen Lauf aufhalten."""
    try:
        with Session(engine) as s:
            e = s.get(SuchEinstellung, 1)
            return (getattr(e, "sprache", "") or "") if e else ""
    except Exception:  # noqa: BLE001 -- bewusst breit, s. Docstring
        return ""


def aktuell() -> str:
    """Immer eine gültige Sprache: die gespeicherte, sonst der Standard."""
    wert = gespeichert()
    return wert if wert in SPRACHEN else STANDARD


# ── Texte des Servers ─────────────────────────────────────────────────────────────────────────────
# Quelle und Schlüssel ist der deutsche Text: Er bleibt im Code lesbar, und Deutsch braucht keinen Katalog.
# `en.json` hält die Übersetzungen der `tx()`-Aufrufe, `en_daten.json` die von Texten, die nicht als Literal
# im Code stehen (etwa die Beschreibungen der Beiratsköpfe). test_texte.py hält beide vollständig.
_TEXTE_DIR = Path(__file__).resolve().parent / "texte"
_katalog: dict[str, str] | None = None


def _laden() -> dict[str, str]:
    global _katalog
    if _katalog is None:
        geladen: dict[str, str] = {}
        for name in ("en.json", "en_daten.json"):
            try:
                geladen.update(json.loads((_TEXTE_DIR / name).read_text(encoding="utf-8")))
            except (OSError, ValueError) as exc:
                print(tt("[sprache] WARNUNG: {name} nicht lesbar: {fehler}", name=name, fehler=exc), flush=True)
        _katalog = geladen
    return _katalog


def uebersetzt(deutsch: str) -> str:
    """Text in der aktuellen Sprache. Fehlt die Übersetzung, kommt der deutsche Text, nichts bricht."""
    if aktuell() == "de":
        return deutsch
    return _laden().get(deutsch, deutsch)


def tx(deutsch: str, /, **werte) -> str:
    """Text in der aktuellen Sprache, mit Platzhaltern im Stil `{name}`. Nur mit Literal aufrufen, sonst
    findet test_texte.py den Text nicht; für Daten gibt es `uebersetzt()`. Wirft nie."""
    text = uebersetzt(deutsch)
    if not werte:
        return text
    try:
        return text.format(**werte)
    except (KeyError, IndexError, ValueError) as exc:
        print(tt("[sprache] WARNUNG: Platzhalter passen nicht in {text!r}: {fehler}", text=deutsch, fehler=exc), flush=True)
        return text


def datum(wert) -> str:
    """Datum für Fließtext und Berichte: de `TT.MM.JJJJ`, en `TT/MM/JJJJ`. Nimmt date, datetime oder einen
    ISO-Text. Dateinamen und ISO-Felder gehen nicht hier durch. Unlesbares kommt unverändert zurück."""
    if wert is None or wert == "":
        return ""
    if isinstance(wert, str):
        try:
            wert = datetime.date.fromisoformat(wert[:10])
        except ValueError:
            return wert
    muster = "%d/%m/%Y" if aktuell() == "en" else "%d.%m.%Y"
    return wert.strftime(muster)


def html_lang() -> str:
    return aktuell()
