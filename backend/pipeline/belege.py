#!/usr/bin/env python3
"""Belegprüfung (P2-97 Stufe A): Steht ein Zitat wörtlich in einem Text?

Hintergrund: Beirat und `cv-erstellen` sollen Aussagen über den Nutzer mit wörtlichen Zitaten aus dem
CV belegen. Ob ein Zitat wirklich im CV steht, entscheidet diese Funktion, nicht das Modell. Sie ist
rein deterministisch (kein LLM, keine Kosten) und bewusst streng: kein unscharfer Abgleich, lieber ein
ehrliches „nicht gefunden“ als ein falscher Treffer.

Was die Normalisierung ausgleicht (gleich auf Zitat und Quelltext angewandt): Groß- und Kleinschreibung,
Zeilenumbrüche und mehrfache Leerzeichen, typografische Anführungszeichen (sie fallen ganz weg),
Gedankenstriche, weiches Trennzeichen, Unicode-Varianten (NFKC, z. B. geschütztes Leerzeichen).
Eine Auslassung (`…`, `...`, `[...]`) teilt das Zitat; jeder Teil muss dann in Reihenfolge vorkommen.
Jeder Teil braucht mindestens `MIN_ZEICHEN` Zeichen, damit ein einzelnes Wort nicht zufällig trifft.

CLI (die Ausgabe liest die KI, deshalb Deutsch, siehe P2-95):
    cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.belege pruefen --datei <.docx|.txt> --zitat "<text>"
Exit-Code 0 = gefunden, 1 = nicht gefunden, 2 = Datei fehlt oder nicht lesbar.
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path

MIN_ZEICHEN = 12

_ANFUEHRUNGSZEICHEN = "\"'„“”‟«»‹›‚‘’‛`´"
_STRICHE = "‐‑‒–—―−"
_AUSLASSUNG = re.compile(r"\[?\s*\.{3,}\s*\]?")
_RAND = " .,;:!?-()[]"


def normalisieren(text: str) -> str:
    """Vergleichsform eines Textes. Gleiche Regeln für Zitat und Quelltext, sonst stimmt der Vergleich nicht."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)      # „…“ wird zu „...“, geschütztes Leerzeichen zu Leerzeichen
    t = t.replace("­", "")                   # weiches Trennzeichen
    t = t.translate({ord(z): None for z in _ANFUEHRUNGSZEICHEN})
    t = t.translate({ord(z): "-" for z in _STRICHE})
    t = t.casefold()
    return re.sub(r"\s+", " ", t).strip()


def _teile(zitat: str) -> list[str]:
    """Zitat an Auslassungen teilen, Satzzeichen am Rand je Teil abschneiden, leere Teile verwerfen."""
    return [s for s in (teil.strip(_RAND) for teil in _AUSLASSUNG.split(normalisieren(zitat))) if s]


def zitat_belegt(zitat: str, quelltext: str) -> bool:
    """True, wenn das Zitat (nach Normalisierung) wörtlich im Quelltext steht.

    Mit Auslassung: alle Teile in dieser Reihenfolge. Ein Teil unter `MIN_ZEICHEN` Zeichen macht das
    ganze Zitat ungültig, auch wenn er zufällig vorkommt."""
    teile = _teile(zitat or "")
    if not teile or any(len(t) < MIN_ZEICHEN for t in teile):
        return False
    quelle = normalisieren(quelltext or "")
    pos = 0
    for teil in teile:
        fund = quelle.find(teil, pos)
        if fund < 0:
            return False
        pos = fund + len(teil)
    return True


def _inhalt_texte(behaelter) -> list[str]:
    """Absätze und Tabellen in Dokumentreihenfolge, Tabellen rekursiv (auch verschachtelt)."""
    from docx.table import Table

    texte = []
    for block in behaelter.iter_inner_content():
        if isinstance(block, Table):
            for zeile in block.rows:
                for zelle in zeile.cells:
                    texte.extend(_inhalt_texte(zelle))
        else:
            texte.append(block.text)
    return texte


def docx_text(pfad) -> str:
    """Text einer .docx aus Absätzen und Tabellenzellen, ein Absatz je Zeile."""
    from docx import Document

    return "\n".join(_inhalt_texte(Document(str(pfad))))


def datei_text(pfad) -> str:
    """Text einer .docx oder einer Textdatei (UTF-8)."""
    p = Path(pfad)
    if p.suffix.lower() == ".docx":
        return docx_text(p)
    return p.read_text(encoding="utf-8")


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(prog="pipeline.belege", description="Prüft, ob ein Zitat wörtlich in einer Datei steht.")
    unter = parser.add_subparsers(dest="befehl", required=True)
    pruefen = unter.add_parser("pruefen", help="Zitat gegen eine .docx oder Textdatei prüfen")
    pruefen.add_argument("--datei", required=True)
    pruefen.add_argument("--zitat", required=True)
    args = parser.parse_args(argv)

    try:
        text = datei_text(args.datei)
    except Exception as ex:                       # fehlt, kein gültiges docx, falsche Kodierung
        print(f"FEHLER: Datei nicht lesbar: {args.datei} ({type(ex).__name__})")
        return 2
    if zitat_belegt(args.zitat, text):
        print("GEFUNDEN: Das Zitat steht wörtlich in der Datei.")
        return 0
    teile = _teile(args.zitat)
    if not teile or any(len(t) < MIN_ZEICHEN for t in teile):
        print(f"NICHT GEFUNDEN: Zitat oder ein Teil davon ist kürzer als {MIN_ZEICHEN} Zeichen.")
    else:
        print("NICHT GEFUNDEN: Das Zitat steht nicht wörtlich in der Datei.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
