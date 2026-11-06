#!/usr/bin/env python3
"""Englische Fassungen der Dokumente aktuell halten (P2-91).

Die deutsche Fassung ist die Quelle. Für jede englische Datei steht in `docs/en/quellen.json` die Prüfsumme
der deutschen Fassung, aus der sie stammt. Ändert sich die Quelle, ist die Übersetzung veraltet, bis sie
nachgezogen und bestätigt ist. Die Prüfsummen liegen nicht in den Dokumenten, weil der Doku-Renderer rohes HTML
escaped und ein Kommentar dort sichtbar wäre.

Dazu eine Strukturprüfung, die echte Übersetzungsfehler fängt: gleiche Zahl von Überschriften je Ebene, gleiche
Befehlsblöcke, gleiche Webadressen. Die Gruppe „technik“ prüft nur die Freigabe (`pipeline.release`), weil sich die
Technik-Doku mit fast jeder Phase ändert. „anwender“ und „recht“ prüft jeder CI-Lauf (tests/test_uebersetzung.py).

CLI:
    python -m pipeline.uebersetzung --pruefen [--alle]
    python -m pipeline.uebersetzung --bestaetigen docs/en/ANLEITUNG.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
QUELLEN_DATEI = "docs/en/quellen.json"
GRUPPEN = ("anwender", "recht", "technik")

_ANWENDER = ("ANLEITUNG", "ANLEITUNG_COACH_SITE", "BEIRAT-CHARTA", "BEIRAT-PERSONA-TEMPLATE", "FUNKTIONEN", "SETUP-EMAIL",
             "SETUP-WINDOWS")
_TECHNIK = ("DOKUMENTATION", "RELEASE", "INSTALLATION", "WAS_IST_NEU", "AUTOMATION", "COACH_SITE", "GMAIL-STRATEGIE")


@dataclass(frozen=True)
class Paar:
    quelle: str
    ziel: str
    gruppe: str


PAARE: tuple[Paar, ...] = (
    *(Paar(f"docs/{n}.md", f"docs/en/{n}.md", "anwender") for n in _ANWENDER),
    Paar("BMS_Install_MAC.md", "BMS_Install_MAC.en.md", "anwender"),
    Paar("BMS_Install_Windows.md", "BMS_Install_Windows.en.md", "anwender"),
    Paar("CHANGELOG.md", "CHANGELOG.en.md", "anwender"),
    # P2-92: Auf GitHub trägt die englische Fassung den Standardnamen, die Quelle bleibt Deutsch.
    Paar("README.de.md", "README.md", "anwender"),
    Paar("CONTRIBUTING.de.md", "CONTRIBUTING.md", "anwender"),
    Paar("SECURITY.de.md", "SECURITY.md", "anwender"),
    Paar("frontend/src/rechtliches/ueber.md", "frontend/src/rechtliches/ueber.en.md", "recht"),
    Paar("frontend/src/rechtliches/lizenz.md", "frontend/src/rechtliches/lizenz.en.md", "recht"),
    Paar("frontend/src/rechtliches/datenschutz.md", "frontend/src/rechtliches/datenschutz.en.md", "recht"),
    *(Paar(f"docs/{n}.md", f"docs/en/{n}.md", "technik") for n in _TECHNIK),
)

# Blöcke, die in der englischen Fassung bewusst anders aussehen dürfen, weil sie Text für Menschen enthalten oder den
# Dateinamen der englischen Fassung nennen. Schlüssel: Ziel-Datei. Wert: Teiltexte; ein Block mit einem davon zählt nicht.
_BLOCK_AUSNAHMEN: dict[str, tuple[str, ...]] = {
    "BMS_Install_MAC.en.md": ("startsprache",),
    "BMS_Install_Windows.en.md": ("startsprache",),
}

_ZAUN_RE = re.compile(r"^(```|~~~)[^\n]*\n(.*?)^\1[ \t]*$", re.S | re.M)
_URL_RE = re.compile(r"https?://[^\s)\"'<>`]+")


def _hash(pfad: Path) -> str:
    return hashlib.sha256(pfad.read_bytes()).hexdigest()


def _laden(root: Path) -> dict[str, str]:
    pfad = root / QUELLEN_DATEI
    return json.loads(pfad.read_text(encoding="utf-8")) if pfad.is_file() else {}


def _bloecke(text: str) -> list[str]:
    return [m.group(2).strip() for m in _ZAUN_RE.finditer(text)]


def _ueberschriften(text: str) -> dict[int, int]:
    ohne_bloecke = _ZAUN_RE.sub("", text)
    zaehler: dict[int, int] = {}
    for m in re.finditer(r"^(#{1,6}) \S", ohne_bloecke, re.M):
        zaehler[len(m.group(1))] = zaehler.get(len(m.group(1)), 0) + 1
    return zaehler


def _urls(text: str) -> set[str]:
    return {u.rstrip(".,;:") for u in _URL_RE.findall(_ZAUN_RE.sub("", text))}


def struktur_funde(quelle: str, ziel: str, name: str = "") -> list[str]:
    """Abweichungen in der Struktur. Webadressen: Englisch darf die englische Fassung einer Seite verlinken, deshalb
    zählt nur, dass nichts wegfällt, abgesehen vom Sprachpfad `/de/` und `/en/`."""
    funde = []
    if _ueberschriften(quelle) != _ueberschriften(ziel):
        funde.append(f"{name}: Überschriften {_ueberschriften(quelle)} gegen {_ueberschriften(ziel)}")
    ausnahmen = _BLOCK_AUSNAHMEN.get(name, ())
    q = [b for b in _bloecke(quelle) if not any(a in b for a in ausnahmen)]
    z = [b for b in _bloecke(ziel) if not any(a in b for a in ausnahmen)]
    if len(q) != len(z):
        funde.append(f"{name}: {len(q)} Befehlsblöcke gegen {len(z)}")
    norm = lambda u: u.replace("/de/", "/en/")  # noqa: E731
    fehlend = {norm(u) for u in _urls(quelle)} - {norm(u) for u in _urls(ziel)}
    if fehlend:
        funde.append(f"{name}: Webadressen fehlen: {sorted(fehlend)[:3]}")
    return funde


def pruefen(root: Path = PROJECT_ROOT, gruppen: tuple[str, ...] = ("anwender", "recht")) -> list[str]:
    """Alle Funde als lesbare Zeilen. Ohne `quellen.json` (Testaufbau) gibt es nichts zu prüfen."""
    if not (root / QUELLEN_DATEI).is_file():
        return []
    stand = _laden(root)
    funde = []
    for p in PAARE:
        if p.gruppe not in gruppen:
            continue
        quelle, ziel = root / p.quelle, root / p.ziel
        if not ziel.is_file():
            funde.append(f"{p.ziel}: fehlt")
            continue
        if not quelle.is_file():
            funde.append(f"{p.ziel}: Quelle {p.quelle} fehlt")
            continue
        if stand.get(p.ziel) != _hash(quelle):
            funde.append(f"{p.ziel}: veraltet, {p.quelle} wurde geändert")
        funde += struktur_funde(quelle.read_text(encoding="utf-8"), ziel.read_text(encoding="utf-8"), p.ziel)
    return funde


def bestaetigen(root: Path, ziel: str) -> None:
    """Trägt die aktuelle Prüfsumme der Quelle ein. `ziel` ist der Pfad der englischen Datei."""
    paar = next((p for p in PAARE if p.ziel == ziel), None)
    if paar is None:
        raise ValueError(f"Unbekannte Übersetzung: {ziel}")
    stand = _laden(root)
    stand[ziel] = _hash(root / paar.quelle)
    pfad = root / QUELLEN_DATEI
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(stand, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline.uebersetzung", description=__doc__.split("\n")[0])
    ap.add_argument("--pruefen", action="store_true")
    ap.add_argument("--alle", action="store_true", help="auch die Technik-Doku")
    ap.add_argument("--bestaetigen", metavar="ZIEL")
    args = ap.parse_args(argv)
    if args.bestaetigen:
        bestaetigen(PROJECT_ROOT, args.bestaetigen)
        print(f"bestätigt: {args.bestaetigen}")
        return 0
    funde = pruefen(PROJECT_ROOT, GRUPPEN if args.alle else ("anwender", "recht"))
    for f in funde:
        print(f)
    print("Alles aktuell." if not funde else f"{len(funde)} Fund(e).")
    return 1 if funde else 0


if __name__ == "__main__":
    sys.exit(main())
