#!/usr/bin/env python3
"""Struktur-Umbau der Basis-CVs auf „v10 ATS" (07.08.2026, Vorgabe beim echten
Bewerben mit v9): je Berufsstation zuerst die FIRMA, dann die ROLLE, dann die Aufgaben —
plus deutlicher Abstand (~2 Leerzeilen) vor jeder Station, „sonst kann ein Mensch das
nicht lesen".

    v9:   TITEL (bold 11pt) → Firma\tZeitraum → Beschreibung (kursiv) → Bullets
    v10:  Firma\tZeitraum → TITEL (bold 11pt) → Beschreibung (kursiv) → Bullets
          + space_before ≈ 2 Leerzeilen auf der Firma-Zeile jeder Berufsstation

Bewusste Abweichung vom alten v7 (dort stand die Beschreibung ZWISCHEN Firma und Titel):
genau diese Zwischenzeile war die Ursache des Workday-Titel-Verrutschens (Phase 76).
In v10 bleiben Firma und Titel direkt benachbart — Mensch-Lesereihenfolge wie gewünscht,
Parser-Pairing bleibt intakt. Der Abstand kommt als `space_before` (typografisch sauber,
für Text-Extraktion/ATS unsichtbar), nicht als leere Geister-Absätze.

cv_export braucht KEINEN Umbau: `_stationsgrenzen()` (Phase 76) behandelt eine Tab-Zeile
ohne Titel davor bereits als Stationsgrenze (Alt-Format-Zweig) — die keep-Kette beginnt
an der Firma-Zeile und endet vor der nächsten; der Titel liegt in v10 IN der Station.

Sicherheit wie beim v9-Skript: Backup (data/cv_basis/backup_v9/), harter Abbruch bei
Musterabweichung, atomares Speichern, Read-back-Validierung, idempotent.

Aufruf:
    ~/.bewerbung_mgmt_venv/bin/python scripts/cv_basis_umbau_v10.py
"""
import os
import shutil
import sys
from pathlib import Path

from docx import Document
from docx.shared import Pt

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASIS_DIR = PROJECT_ROOT / "data" / "cv_basis"
BACKUP_DIR = BASIS_DIR / "backup_v9"

RUBRIK = {"base_de.docx": "BERUFSERFAHRUNG", "base_en.docx": "PROFESSIONAL EXPERIENCE"}
ABSTAND = Pt(26)   # ≈ 2 Leerzeilen bei 10,5-pt-Grundschrift


def _ist_heading(p):
    return bool(p.style) and p.style.name.startswith("Heading")


def _ist_tab_anker(p):
    return bool(p.style) and p.style.name == "Normal" and "\t" in p.text and p.text.strip()


def _ist_titel(p):
    if not (bool(p.style) and p.style.name == "Normal" and p.text.strip() and "\t" not in p.text):
        return False
    return any(r.bold for r in p.runs)


def _berufs_bereich(absaetze, rubrik):
    start = None
    for i, p in enumerate(absaetze):
        if _ist_heading(p) and p.text.strip().upper() == rubrik:
            start = i + 1
        elif start is not None and _ist_heading(p):
            return start, i
    if start is None:
        raise SystemExit(f"ABBRUCH: Abschnitt {rubrik!r} nicht gefunden")
    return start, len(absaetze)


def _validieren(doc, rubrik, erwartete_stationen, erwartete_absaetze):
    """v10: je Anker folgt DIREKT der Titel (bold, 11pt), dann die kursive Beschreibung;
    Anker trägt den Stations-Abstand. Wirft SystemExit bei Verstoß."""
    absaetze = doc.paragraphs
    if len(absaetze) != erwartete_absaetze:
        raise SystemExit(f"ABBRUCH Validierung: {len(absaetze)} Absätze statt {erwartete_absaetze}")
    start, ende = _berufs_bereich(absaetze, rubrik)
    anker = [i for i in range(start, ende) if _ist_tab_anker(absaetze[i])]
    if len(anker) != erwartete_stationen:
        raise SystemExit(f"ABBRUCH Validierung: {len(anker)} Stationen statt {erwartete_stationen}")
    for i in anker:
        titel = absaetze[i + 1]
        if not _ist_titel(titel):
            raise SystemExit(f"ABBRUCH Validierung: kein Titel nach Anker {i} ({absaetze[i].text[:40]!r})")
        if not all(r.font.size == Pt(11) for r in titel.runs if r.text.strip()):
            raise SystemExit(f"ABBRUCH Validierung: Titel {titel.text!r} ohne 11pt")
        if not any(r.italic for r in absaetze[i + 2].runs):
            raise SystemExit(f"ABBRUCH Validierung: keine kursive Beschreibung nach Titel (Anker {i})")
        if absaetze[i].paragraph_format.space_before != ABSTAND:
            raise SystemExit(f"ABBRUCH Validierung: Anker {i} ohne Stations-Abstand")


def _umbauen(pfad: Path, rubrik: str) -> None:
    doc = Document(str(pfad))
    absaetze = doc.paragraphs
    n_vorher = len(absaetze)
    start, ende = _berufs_bereich(absaetze, rubrik)
    anker = [i for i in range(start, ende) if _ist_tab_anker(absaetze[i])]
    print(f"  {len(anker)} Berufsstationen im Bereich {start}–{ende}")

    # Idempotenz: folgt auf den ERSTEN Anker bereits direkt ein Titel → schon v10.
    if anker and _ist_titel(absaetze[anker[0] + 1]):
        print("  bereits v10 — nur Abstände sicherstellen")
        for i in anker:
            absaetze[i].paragraph_format.space_before = ABSTAND
        _validieren(doc, rubrik, len(anker), n_vorher)
        tmp = pfad.with_suffix(".docx.neu")
        doc.save(str(tmp))
        os.replace(tmp, pfad)
        return

    # Vorflug: je Anker muss der Titel im v9-Format DIREKT DAVOR stehen.
    plaene = []
    for i in anker:
        titel = absaetze[i - 1]
        if not _ist_titel(titel):
            raise SystemExit(f"ABBRUCH: vor Anker {i} ({absaetze[i].text[:50]!r}) steht kein "
                             f"v9-Titel — Muster prüfen, nichts gespeichert")
        plaene.append(i)

    # Umbau: Tab-Zeile VOR ihren Titel schieben (ein lxml-Move je Station — die
    # Beschreibung, die in v9 hinter der Tab-Zeile lag, rutscht damit automatisch
    # hinter den Titel). Rückwärts wie im v9-Skript.
    for i in reversed(plaene):
        tab_p = absaetze[i]
        titel_p = absaetze[i - 1]
        titel_p._p.addprevious(tab_p._p)
        tab_p.paragraph_format.space_before = ABSTAND

    absaetze = doc.paragraphs  # Reihenfolge hat sich geändert — frisch lesen
    _validieren(doc, rubrik, len(anker), n_vorher)
    tmp = pfad.with_suffix(".docx.neu")
    doc.save(str(tmp))
    os.replace(tmp, pfad)
    _validieren(Document(str(pfad)), rubrik, len(anker), n_vorher)
    print(f"  gespeichert + Read-back-Validierung ok ({n_vorher} Absätze unverändert)")


def main() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for name, rubrik in RUBRIK.items():
        pfad = BASIS_DIR / name
        print(f"== {name}")
        if not pfad.is_file() or pfad.stat().st_size == 0:
            raise SystemExit(f"ABBRUCH: {pfad} fehlt oder ist leer (iCloud-Download prüfen)")
        backup = BACKUP_DIR / name
        if backup.exists():
            print(f"  Backup existiert bereits: {backup.name} (wird NICHT überschrieben)")
        else:
            shutil.copy2(pfad, backup)
            print(f"  Backup: {backup}")
        _umbauen(pfad, rubrik)
    print("Fertig — beide Basis-CVs auf v10 ATS.")


if __name__ == "__main__":
    sys.exit(main())
