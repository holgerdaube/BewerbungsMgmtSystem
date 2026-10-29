#!/usr/bin/env python3
"""Schreibt das App-Icon in HTML-Dateien, denen es fehlt — idempotent.

WOFÜR (28.08.2026): Die Python-Erzeuger binden das Icon seit dieser Phase selbst ein, und
`/api/artifact` setzt es beim Ausliefern nach. Zwei Lücken bleiben, die nur dieses Skript
schliesst:

  1. **Der Bestand.** Über 800 Berichte in `data/` sind vor der Umstellung entstanden. Aus der
     App zeigen sie das Icon (Nachsetzen beim Ausliefern), beim Öffnen aus dem Finder nicht.
  2. **Berichte aus Skill-Läufen.** Die schreibt ein Modell direkt auf die Platte, an jedem
     Python-Code vorbei. Die Report-Vorlage trägt das Icon zwar, aber darauf allein sollte sich
     niemand verlassen — ein Lauf, der die Vorlage kürzt, fiele sonst durch alle Netze.

Deshalb läuft dieses Skript im `refresh_views.sh` mit, also bei jedem Tageslauf. Es ist
deterministisch (kein LLM, keine Kosten) und ändert nur Dateien, deren Icon fehlt ODER nicht
unseres ist (P2-44: 26 Skill-Berichte trugen ein selbst geschriebenes, teils abgeschnittenes
Icon — s. `app/favicon.py::mit_favicon`).

    cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.favicon_nachruesten [--trocken]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.favicon import favicon_link, hat_bms_favicon, hat_favicon, mit_favicon  # noqa: E402

PROJEKT_ROOT = Path(__file__).resolve().parents[2]
# `outputs/` enthaelt Bewerbungsunterlagen (docx/pdf) — HTML liegt dort praktisch nie, wird aber
# mitgenommen, damit kuenftige Ablagen nicht vergessen werden.
ORDNER = ["data", "outputs"]
# Der Papierkorb bleibt aussen vor: Was dort liegt, ist verworfen und soll unveraendert bleiben,
# damit ein Zurueckholen exakt den alten Stand liefert.
AUSGENOMMEN = {"papierkorb", "backups", "node_modules", "__pycache__"}


def _kandidaten():
    for ordner in ORDNER:
        wurzel = PROJEKT_ROOT / ordner
        if not wurzel.is_dir():
            continue
        for pfad in wurzel.rglob("*.html"):
            if AUSGENOMMEN & set(pfad.relative_to(wurzel).parts):
                continue
            yield pfad


def main(argv: list) -> int:
    trocken = "--trocken" in argv
    if not favicon_link():     # P2-72: das Icon kommt aus dem Design, zur Laufzeit gelesen
        print("Kein Favicon verfuegbar (das Icon des Designs ist nicht lesbar) — nichts zu tun.")
        return 0

    geprueft = ergaenzt = korrigiert = schon_gut = unlesbar = 0
    for pfad in _kandidaten():
        geprueft += 1
        try:
            text = pfad.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            unlesbar += 1
            continue
        if hat_bms_favicon(text):
            schon_gut += 1
            continue
        fremdes_icon = hat_favicon(text)     # P2-44: Icon da, aber nicht unseres
        neu = mit_favicon(text)
        if neu == text:          # kein <head> — Fragment, kein vollstaendiges Dokument
            continue
        if fremdes_icon:
            korrigiert += 1
        else:
            ergaenzt += 1
        if not trocken:
            pfad.write_text(neu, encoding="utf-8")

    print("HTML-Dateien geprueft :", geprueft)
    print("  hatten schon ein Icon:", schon_gut)
    print("  Icon ergaenzt        :", ergaenzt, "(Trockenlauf)" if trocken else "")
    print("  fremdes Icon ersetzt :", korrigiert, "(Trockenlauf)" if trocken else "")
    if unlesbar:
        print("  nicht als UTF-8 lesbar:", unlesbar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
