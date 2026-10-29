"""Die Zustandsfarben des BMS in Python — EINE Tabelle (P2-72, Vertrag R).

Status, Score und die Schrift darauf tragen Bedeutung, nicht Marke (Leitentscheidung 2): „Beworben“
bleibt cyan, auch wenn ein Design Orange als Aktionsfarbe mitbringt. Sie hängen an keiner Rolle der
Design-Datei (`pipeline/design.py`) und ändern sich mit einem anderen Design nicht.

VORHER stand dieselbe Tabelle in `frontend/src/components/ui.tsx` und dazu viermal in Python
(`digest.py`, `coach_export.py`, `export_excel.py`, `beirat_engine.py`), in drei Schreibweisen
(`#0B1F3A`, `#0b1f3a`, `0B1F3A`). JETZT gibt es in Python diese Datei. Die Tabellen in `ui.tsx` und
hier sind gleich; `tests/test_zustandsfarben.py` liest `ui.tsx` und vergleicht sie.

SCHREIBWEISE: `#RRGGBB`, so, wie `ui.tsx` sie schreibt (auch die Groß-/Kleinschreibung: Weiß auf einer
Zustandsfläche steht dort als `#ffffff`). Die Ausgaben, die diese Werte ins HTML schreiben (Digest,
Coach-Site), bleiben dadurch byte-gleich zum Stand vor P2-72. Wer die Form ohne Raute braucht (Excel
schreibt `0B1F3A`), nimmt `ohne_raute()`.

Nur Standardbibliothek. Das Modul importiert weder die FastAPI-App noch die Datenbank: Der Excel-Export
läuft auch als Kommandozeile (`python -m pipeline.export_excel`) und soll dafür nicht die ganze App laden.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping, Tuple

# Schrift auf den Zustandsflächen (Status, Score, Situation, Tier, Szenario). Auf Kontrast geprüft
# (18.8), hängt an keiner Markenrolle. Gleicher Name und gleicher Wert wie `TEXT_AUF_ZUSTAND` in ui.tsx.
TEXT_AUF_ZUSTAND = "#0B1F3A"
_WEISS = "#ffffff"

Farbpaar = Tuple[str, str]      # (Fläche, Schrift)

# Statusfarben (Style Guide 18.3/18.7), Wert für Wert wie `STATUS_FARBEN` in ui.tsx.
STATUS_FARBEN: Mapping[str, Farbpaar] = MappingProxyType({
    "Neu": ("#94A3B8", TEXT_AUF_ZUSTAND),
    "Prüfen": ("#5B61E6", _WEISS),
    "Beworben": ("#00B4D8", TEXT_AUF_ZUSTAND),
    "Interview": ("#7C4DFF", _WEISS),
    "Angebot": ("#18A957", TEXT_AUF_ZUSTAND),
    "Absage": ("#E5484D", _WEISS),
    "Keine Rückmeldung": ("#7A5C5C", _WEISS),
    "Kein Match": ("#64748B", _WEISS),
    "Beirat abgelehnt": ("#D97706", TEXT_AUF_ZUSTAND),
    "Nicht verfügbar": ("#A8B4C4", TEXT_AUF_ZUSTAND),
    "Geparkt": ("#E4A11B", TEXT_AUF_ZUSTAND),
})
# Rückfall für einen Status, den die Tabelle nicht kennt (`STATUS_FARBE_UNBEKANNT` in ui.tsx).
STATUS_FARBE_UNBEKANNT: Farbpaar = ("#94A3B8", TEXT_AUF_ZUSTAND)

# Zielstellen-Fit 1 bis 5 (`SCORE_COLORS` und `SCORE_TEXT` in ui.tsx). Nur Score 1 verträgt weiße Schrift.
SCORE_FARBEN: Mapping[int, Farbpaar] = MappingProxyType({
    5: ("#18A957", TEXT_AUF_ZUSTAND),
    4: ("#84C83D", TEXT_AUF_ZUSTAND),
    3: ("#E8B319", TEXT_AUF_ZUSTAND),
    2: ("#F07C24", TEXT_AUF_ZUSTAND),
    1: ("#D9364F", _WEISS),
})
# „Nicht bewertet“ (`SCORE_NONE` in ui.tsx, Schrift darauf `TEXT_AUF_ZUSTAND`). Gilt auch für jeden
# Score, den die Tabelle nicht kennt.
SCORE_NICHT_BEWERTET: Farbpaar = ("#94A3B8", TEXT_AUF_ZUSTAND)

# Erste Stufe des Trichters („Gesichtet“): eine Bedeutung der Trichter-Grafik (Start), keine Markenfarbe.
# Sie ist heute zufällig Navy mit weißer Schrift. Die Stufen 2 bis 5 sind Statusfarben (Prüfen, Beworben,
# Geparkt, Angebot), siehe `export_excel.FUNNEL_FARBEN`. Gleicher Wert wie die erste Stufe von
# `FUNNEL_FARBEN` in Dashboard.tsx.
TRICHTER_START: Farbpaar = ("#0B1F3A", _WEISS)


def status_farbe(status) -> Farbpaar:
    """(Fläche, Schrift) des Status; ein unbekannter oder leerer Status bekommt den Rückfall."""
    return STATUS_FARBEN.get(status or "", STATUS_FARBE_UNBEKANNT)


def score_farbe(score) -> Farbpaar:
    """(Fläche, Schrift) des Zielstellen-Fits; leer, 0 oder unbekannt heißt „nicht bewertet“."""
    return SCORE_FARBEN.get(score, SCORE_NICHT_BEWERTET)


def ohne_raute(farbe: str) -> str:
    """"#0B1F3A" -> "0B1F3A", GROSS: die Form, die openpyxl (Excel) verlangt."""
    return farbe.lstrip("#").upper()
