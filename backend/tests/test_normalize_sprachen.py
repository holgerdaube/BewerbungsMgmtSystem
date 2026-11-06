"""Erfassen und Dubletten in FR, IT, ES, PT: Gender-Zusatz, Rechtsformen, Arbeitsmodell, Seniorität.

Deutsch und Englisch bleiben gleich: Die Fälle ohne romanische Schreibweise stehen als
Gegenprobe daneben. Kein app.*-Import auf Modulebene außer `normalize` (conftest.py-Konvention).
"""
import pytest

from app import normalize as N


# ── Fix 6: Gender-Zusatz ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("titel,erwartet", [
    # Aus dem Prüfbericht (öffentliche Anzeigen)
    ("Livreur H/F", "Livreur"),
    ("Livreur - F/H", "Livreur"),
    ("CHAUFFEUR / LIVREUR PL F/H", "CHAUFFEUR / LIVREUR PL"),
    ("Chauffeur SPL H/F (H/F)", "Chauffeur SPL"),
    ("autista consegnatario patente b (f/m/nb)", "autista consegnatario patente b"),
    ("Chauffeur (H/F)", "Chauffeur"),
    ("Chauffeur (M/F/X)", "Chauffeur"),
    # Alle sechs Paare, jede Schreibweise
    ("Fahrer M/F", "Fahrer"), ("Fahrer F/M", "Fahrer"), ("Fahrer H/M", "Fahrer"),
    ("Fahrer M/H", "Fahrer"), ("Fahrer f/h", "Fahrer"), ("Fahrer h / f", "Fahrer"),
    # Klammer mit zweistelligem Teil
    ("Operator (m/f/xy)", "Operator"), ("Operator (NB/M/F)", "Operator"), ("Operator (m:w:nb)", "Operator"),
])
def test_gender_zusatz_faellt_weg(titel, erwartet):
    assert N.titel_ohne_gender(titel) == erwartet


@pytest.mark.parametrize("titel", [
    "Repartidor/a", "Conductor/a de reparto", "Chauffeur/Livreur", "Chauffeur / Livreur", "Head of IT/OT",
    "Ingeniero B/C", "Operario B/C", "Site Manager B/C",
    # Wortgrenze: das Paar klebt an einem Wort
    "Teamleiter HR/F", "Teamleiter AM/F", "Manager FM/H",
    # nicht am Titelende
    "Manager M/F Berlin", "H/F Spezialist Lager",
    # Paare außerhalb der Liste
    "Fahrer W/M", "Support D/F", "Teamleiter X/Y",
    # Klammer mit anderem Inhalt
    "Berater (Senior)", "Entwickler (DE/EN)", "Manager (Nachtschicht)",
])
def test_titel_ohne_gender_bleibt_stehen(titel):
    assert N.titel_ohne_gender(titel) == titel


@pytest.mark.parametrize("titel,erwartet", [
    # Bisherige Klammer-Schreibweisen unverändert
    ("Manager (m/f/d)", "Manager"), ("Consultant (w/m/d)", "Consultant"), ("Berater (m/w/d)", "Berater"),
    ("Engineer (all genders)", "Engineer"), ("Engineer (f/m/x)", "Engineer"), ("Engineer (m|f|d)", "Engineer"),
    ("Engineer (m:w:d)", "Engineer"), ("Mitarbeiter (m/w/*)", "Mitarbeiter (m/w/*)"),
    ("Lead (d*)", "Lead"), ("Sales Manager - DACH", "Sales Manager - DACH"),
])
def test_deutsch_und_englisch_gleich(titel, erwartet):
    assert N.titel_ohne_gender(titel) == erwartet


def test_rollen_schluessel_gleiche_rolle_mit_und_ohne_zusatz():
    assert N.rollen_schluessel("Livreur H/F") == N.rollen_schluessel("Livreur (H/F)") == N.rollen_schluessel("Livreur")
    assert N.rollen_schluessel("Repartidor/a") != N.rollen_schluessel("Repartidor")


def test_dateinamen_aus_dem_pruefbericht_sind_sauber():
    from app.naming import _rolle_kurz
    assert _rolle_kurz("Livreur H/F", 35) == "Livreur"
    assert _rolle_kurz("Livreur - F/H", 35) == "Livreur"
    assert _rolle_kurz("CHAUFFEUR / LIVREUR PL F/H", 35) == "CHAUFFEUR_LIVREUR_PL"
    assert _rolle_kurz("Chauffeur SPL H/F (H/F)", 35) == "Chauffeur_SPL"
    assert _rolle_kurz("autista consegnatario patente b (f/m/nb)", 35) == "autista_consegnatario_patente_b"
    # Aus der neutralen Klammer wird keine weibliche Form
    assert _rolle_kurz("Motorista Entregador(a)", 35) == "Motorista_Entregador"
    assert "Entregadora" not in _rolle_kurz("Motorista Entregador(a)", 35)


# ── Fix 7: Rechtsformen ──────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("schreibweise", [
    "Beispiel", "Beispiel SARL", "Beispiel S.A.R.L.", "Beispiel SAS", "Beispiel S.A.S.", "Beispiel SA",
    "Beispiel S.A.", "Beispiel S/A", "Beispiel SpA", "Beispiel S.p.A.", "Beispiel Srl", "Beispiel S.r.l.",
    "Beispiel SL", "Beispiel S.L.", "Beispiel SLU", "Beispiel S.L.U.", "Beispiel Lda", "Beispiel Lda.",
    "Beispiel Ltda", "Beispiel Ltda.", "Beispiel, S.L.", "BEISPIEL S.A. España",
])
def test_rechtsformen_fallen_weg(schreibweise):
    erwartet = "beispiel" if "España" not in schreibweise else "beispielespaa"
    assert N.firma_key(schreibweise) == erwartet


def test_ibererische_rechtsform_nur_am_ende_und_nie_allein():
    # nur als eigenes letztes Wort
    assert N.firma_key("Sl Beispiel") == "slbeispiel"
    assert N.firma_key("Beispiel Sl Werke") == "beispielslwerke"
    assert N.firma_key("Lda Beispiel") == "ldabeispiel"
    # nie ein leerer Schlüssel
    assert N.firma_key("SL") == "sl"
    assert N.firma_key("S.L.") == "sl"
    assert N.firma_key("Lda.") == "lda"
    # mit anderem Zusatz davor bleibt der Name übrig
    assert N.firma_key("Beispiel SL Group") == "beispiel"
    assert N.firma_key("Beispiel Lda Ltda") == "beispiel"


def test_punkte_nur_zwischen_einzelbuchstaben():
    assert N.firma_key("Beispiel Co. Ltd.") == N.firma_key("Beispiel Co Ltd")
    # normale Abkürzungen mit Punkt bleiben Teil des Namens (nur Sonderzeichen werden getilgt)
    assert N.firma_key("St. Beispiel S.A.") == "stbeispiel"
    assert N.firma_key("Dr. Beispiel") == "drbeispiel"
    # Deutsche Schreibweisen mit Punkten fallen jetzt ebenfalls zusammen
    assert N.firma_key("Beispiel e.V.") == N.firma_key("Beispiel") == "beispiel"
    assert N.firma_key("Beispiel G.m.b.H.") == N.firma_key("Beispiel GmbH") == "beispiel"


def test_bisherige_firmenschluessel_unveraendert():
    assert N.firma_key("Beispiel GmbH") == "beispiel"
    assert N.firma_key("Beispiel Consulting") == "beispielconsulting"
    assert N.firma_key("Beispiel Security") != N.firma_key("Beispiel Data")
    assert N.firma_key("SE Group") == "segroup"
    assert N.firma_key("") == ""
    assert N.firma_key("Beispiel Jobs") == "beispiel"


# ── Fix 11: Arbeitsmodell ────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("roh,erwartet", [
    ("télétravail", "Remote"), ("Télétravail complet", "Remote"), ("teletravail", "Remote"),
    ("teletrabajo", "Remote"), ("Teletrabajo", "Remote"), ("da remoto", "Remote"), ("Smart working", "Remote"),
    ("Remoto", "Remote"), ("Trabalho remoto", "Remote"),
    ("hybride", "Hybrid"), ("Híbrido", "Hybrid"), ("hibrido", "Hybrid"), ("Ibrido", "Hybrid"),
    ("Híbrido (remoto 2 dias)", "Hybrid"), ("Télétravail partiel", "Hybrid"), ("Teletrabajo parcial", "Hybrid"),
    ("Remoto parziale", "Hybrid"),
    ("présentiel", "Onsite"), ("Sur site", "Onsite"), ("Presencial", "Onsite"), ("In sede", "Onsite"),
])
def test_arbeitsmodell_romanisch(roh, erwartet):
    assert N.norm_work_model(roh) == erwartet


@pytest.mark.parametrize("roh,erwartet", [
    ("Remote", "Remote"), ("100% Remote", "Remote"), ("Remote / Hybrid", "Hybrid"), ("Hybrid", "Hybrid"),
    ("Vor Ort", "Onsite"), ("onsite", "Onsite"), ("On-site", "Onsite"), ("Büro", "Onsite"), ("Field", "Onsite"),
    ("Unklar", "Unklar"), ("Homeoffice möglich", "Homeoffice möglich"), (" ", None), (None, None),
    ("Deutschlandweit", "Deutschlandweit"),
])
def test_arbeitsmodell_deutsch_englisch_gleich(roh, erwartet):
    assert N.norm_work_model(roh) == erwartet


# ── Fix 11: Seniorität ───────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("roh,erwartet", [
    ("Directeur", "Director"), ("Directrice commerciale", "Director"), ("Direttore", "Director"),
    ("Diretor", "Director"), ("Diretora de operações", "Director"), ("Director", "Director"),
    ("Stagiaire", "Praktikant"), ("Stagista", "Praktikant"), ("Becario", "Praktikant"),
    ("Becaria", "Praktikant"), ("Estagiário", "Praktikant"), ("estagiario", "Praktikant"),
    # mehrdeutig: nicht abbilden
    ("Responsable", "Sonstige"), ("Responsable d'équipe", "Sonstige"), ("Jefe", "Sonstige"),
    ("Gerente", "Sonstige"), ("Jefe de equipo", "Sonstige"),
])
def test_senioritaet_romanisch(roh, erwartet):
    assert N.norm_seniority(roh)[0] == erwartet


@pytest.mark.parametrize("roh,erwartet", [
    ("Praktikum", "Praktikant"), ("Internship", "Praktikant"), ("Director", "Director"),
    ("Managing Director", "Director"), ("Senior Director", "Senior Director"), ("Head of IT", "Head"),
    ("International Sales", "Sonstige"), ("Stage Manager", "Manager"),
])
def test_senioritaet_deutsch_englisch_gleich(roh, erwartet):
    assert N.norm_seniority(roh)[0] == erwartet
