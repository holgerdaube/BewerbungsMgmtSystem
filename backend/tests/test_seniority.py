"""Senioritätsstufen: Normalisierung und Gleichlauf mit der Auswahl im Formular."""
import re
from pathlib import Path

import pytest

from app import normalize as N


@pytest.mark.parametrize("stufe", N.SENIORITAETEN)
def test_jede_stufe_bleibt_sie_selbst(stufe):
    assert N.norm_seniority(stufe) == (stufe, stufe)


@pytest.mark.parametrize("roh,erwartet", [
    # LinkedIn-Stufen
    ("Internship", "Praktikant"), ("Entry level", "Berufseinsteiger"), ("Associate", "Angestellter"),
    ("Mid-Senior level", "Erfahrener Mitarbeiter"), ("Director", "Director"), ("Executive", "C-Level"),
    # Deutsche und englische Schreibweisen
    ("Praktikum", "Praktikant"), ("Working Student", "Werkstudent"), ("Ausbildung", "Auszubildender"),
    ("Junior Consultant", "Berufseinsteiger"), ("Ohne Berufserfahrung", "Berufseinsteiger"),
    ("Mit Berufserfahrung", "Erfahrener Mitarbeiter"), ("Senior Consultant", "Erfahrener Mitarbeiter"),
    ("Principal Consultant", "Experte"), ("Mitarbeiter", "Angestellter"), ("Geschäftsführung", "C-Level"),
    ("CEO", "C-Level"), ("Abteilungsleiter", "Head"),
    # Bisherige Stufen bleiben, wie sie waren
    ("VP Sales", "VP"), ("Senior Director", "Senior Director"), ("Managing Director", "Director"),
    ("Head of Delivery", "Head"), ("Sr Manager", "Senior Manager"), ("Teamleiter", "Teamlead"),
    # Fallen: Wortteile dürfen keine Stufe auslösen
    ("International Sales", "Sonstige"), ("Account Executive", "Sonstige"), ("Sonstwas", "Sonstige"),
])
def test_schreibweisen(roh, erwartet):
    assert N.norm_seniority(roh)[0] == erwartet


def test_leer_bleibt_leer():
    assert N.norm_seniority(None) == (None, None)
    assert N.norm_seniority("  ") == (None, None)


def test_formular_zeigt_dieselbe_liste():
    quelle = Path(__file__).resolve().parents[2] / "frontend" / "src" / "senioritaet.ts"
    block = re.search(r"SENIORITAETEN = \[(.*?)\]", quelle.read_text(encoding="utf-8"), re.S).group(1)
    assert tuple(re.findall(r"'([^']+)'", block)) == N.SENIORITAETEN
