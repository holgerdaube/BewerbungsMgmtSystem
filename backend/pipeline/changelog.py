"""`CHANGELOG.md` lesen und bei einer Freigabe fortschreiben (P2-51).

Die Datei liegt im Projekt-Root, wird mit dem Kundenpaket ausgeliefert und ist Kundentext
(Sie-Form). Aufbau:

    # Änderungen

    <Einleitung>

    ## Unveröffentlicht

    - Punkt, der mit der nächsten Freigabe ausgeliefert wird

    ## 1.2.0 (28.09.2026)

    - Punkt

Zwei Leser, ein Format: `pipeline/release.py` macht bei einer Freigabe aus „Unveröffentlicht"
den Versionsabschnitt, die App (`app/version.py`) zeigt den Abschnitt der installierten Version
in den Einstellungen. Nur Kopfzeilen, die exakt dem Muster entsprechen, zählen als Abschnitt —
`pruefen()` meldet jede andere `## `-Zeile, damit sich kein Tippfehler in eine Freigabe schleicht.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

UNVEROEFFENTLICHT = "Unveröffentlicht"

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_KOPF_RE = re.compile(
    r"^## (?:(?P<offen>Unveröffentlicht)|(?P<version>\d+\.\d+\.\d+) \((?P<datum>\d{2}\.\d{2}\.\d{4})\))[ \t]*$",
    re.MULTILINE,
)
_ZWEITE_EBENE_RE = re.compile(r"^## .*$", re.MULTILINE)


class ChangelogFehler(ValueError):
    """Das CHANGELOG lässt die verlangte Operation nicht zu (Meldung ist für Menschen)."""


@dataclass(frozen=True)
class Abschnitt:
    version: Optional[str]  # None = „Unveröffentlicht"
    datum: Optional[str]    # TT.MM.JJJJ, None bei „Unveröffentlicht"
    inhalt: str             # ohne Kopfzeile, Leerzeilen am Rand entfernt
    start: int              # Offset der Kopfzeile im Text
    ende: int               # Offset hinter dem Abschnitt (Beginn des nächsten oder Textende)


def version_tupel(version: str) -> tuple[int, int, int]:
    """„1.2.3" → (1, 2, 3). Alles andere ist ein Fehler (kein „v", keine Zusätze)."""
    m = _VERSION_RE.match(version.strip())
    if not m:
        raise ChangelogFehler(f"„{version}“ ist keine Version im Format MAJOR.MINOR.PATCH.")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def abschnitte(text: str) -> list[Abschnitt]:
    koepfe = list(_KOPF_RE.finditer(text))
    ergebnis = []
    for i, m in enumerate(koepfe):
        ende = koepfe[i + 1].start() if i + 1 < len(koepfe) else len(text)
        ergebnis.append(Abschnitt(
            version=m.group("version"),
            datum=m.group("datum"),
            inhalt=text[m.end():ende].strip("\n").strip(),
            start=m.start(),
            ende=ende,
        ))
    return ergebnis


def abschnitt(text: str, version: Optional[str]) -> Optional[str]:
    """Inhalt des Abschnitts zu `version` (None = „Unveröffentlicht"), leer/fehlend → None."""
    for a in abschnitte(text):
        if a.version == version:
            return a.inhalt or None
    return None


def pruefen(text: str) -> list[str]:
    """Formfehler als lesbare Meldungen (leer = in Ordnung)."""
    fehler = []
    gueltig = {m.start() for m in _KOPF_RE.finditer(text)}
    for m in _ZWEITE_EBENE_RE.finditer(text):
        if m.start() not in gueltig:
            fehler.append(f"Kopfzeile im falschen Format: „{m.group(0)}“ "
                          "(erlaubt: „## Unveröffentlicht“ oder „## 1.2.3 (TT.MM.JJJJ)“).")
    gesehen = set()
    for a in abschnitte(text):
        schluessel = a.version or UNVEROEFFENTLICHT
        if schluessel in gesehen:
            fehler.append(f"Abschnitt „{schluessel}“ steht doppelt.")
        gesehen.add(schluessel)
    return fehler


def freigeben(text: str, version: str, datum: date) -> str:
    """Macht aus „Unveröffentlicht" den Abschnitt `version` und legt darüber einen neuen, leeren
    „Unveröffentlicht"-Abschnitt an. Verweigert, wenn es nichts freizugeben gibt."""
    version_tupel(version)
    fehler = pruefen(text)
    if fehler:
        raise ChangelogFehler(" ".join(fehler))
    teile = abschnitte(text)
    offen = next((a for a in teile if a.version is None), None)
    if offen is None:
        raise ChangelogFehler("Im CHANGELOG fehlt der Abschnitt „## Unveröffentlicht“.")
    if not any(z.lstrip().startswith("- ") for z in offen.inhalt.splitlines()):
        raise ChangelogFehler("Der Abschnitt „Unveröffentlicht“ ist leer: Es gibt nichts freizugeben.")
    if any(a.version == version for a in teile):
        raise ChangelogFehler(f"Version {version} steht schon im CHANGELOG.")
    kopf = f"## {version} ({datum.strftime('%d.%m.%Y')})"
    neu = f"## {UNVEROEFFENTLICHT}\n\n{kopf}\n\n{offen.inhalt}\n"
    rest = text[offen.ende:]
    return text[:offen.start] + neu + ("\n" + rest.lstrip("\n") if rest.strip() else "")
