"""Tests für `pipeline/profil_datei.py` (P2-69, Vertrag F): Zerlegen, Lesen und Schreiben der Profil-Datei
für die Karte „Identität und Suchstrategie“.

Kernregel ist die Verlustfreiheit (Leitentscheidung 1): Zerlegen + unverändertes Zusammensetzen ist für
JEDE Eingabe byte-gleich, und ein Speichern ohne Änderung in der Maske ergibt dieselbe Datei. Geprüft
mit der Vorlage, der Beispiel-Datei, einer erfundenen umfangreichen Datei (Zusatzabschnitte, ###,
Leerzeilen, Kommentarzeilen, CRLF, ohne Schluss-Zeilenende) und einem kleinen Zufallstest.

Isolation: Jeder Test patcht `user_profile._PROFIL_MD` und den Papierkorb (`app.db.DATA_DIR`) auf
`tmp_path` (autouse-Fixture `_profil_pfade`, die auch nachprüft, dass beide wirklich unter `tmp_path`
liegen). Die echte `config/profil.md` wird nie gelesen oder geschrieben. App-/Pipeline-Module
werden nur in Fixtures und Tests importiert (conftest-Regel). Beispiele: nur Max Mustermann /
Musterstadt."""
import difflib
import os
import random
import re
import stat

import pytest

ZIELROLLE_STANDARD = ["Ebene", "Funktion Plan A", "Funktion Plan B", "Branche", "Region", "Zieltermin"]

# Vorlage aus der Anleitung (früher `BMS_Install.md`, heute `BMS_Install_MAC.md` bzw.
# `BMS_Install_Windows.md`; Abschnitt „Einrichten: Das BMS lernt Sie kennen“, dort „Ihr Profil:
# Identität und Suchstrategie“; Stand vor P2-69), mit Max Mustermann.
VORLAGE_INSTALL = """# Kandidatenprofil: Max Mustermann

## Identität
- **Name:** Max Mustermann
- **Positionierung:** Service Delivery Leader, DACH
- **Standort:** Musterweg 3, 12345 Musterstadt
- **Kontakt:** max.mustermann@example.com · +49 170 1234567
- **LinkedIn:** https://www.linkedin.com/in/max-mustermann/
- **Aktuell:** Manager Professional Services bei der Beispiel GmbH, seit 2024

## Kurzprofil
Zwei bis vier Sätze über Sie. Das BMS nutzt sie als Tonvorlage für Ihre Anschreiben.

## Zielrolle
- **Ebene:** Director oder Head of
- **Funktion Plan A:** Leitung Professional Services oder Service Delivery
- **Funktion Plan B:** Head of Customer Success
- **Branche:** Enterprise Software, IT-Dienstleistungen
- **Region:** DACH
- **Zieltermin:** neue Rolle bis 31.12.2026

## Harte Rahmenbedingungen
- Kein Umzug, kein dauerhafter Zweitwohnsitz.
- Mindestens 100 Mitarbeiter beim Zielunternehmen.

## Sprachen / CV-Fassungen
- **Deutsch:** `data/cv_basis/base_de.docx`
- **Englisch:** `data/cv_basis/base_en.docx`

## Bekannte Skill-Gaps / Red Flags
- (noch keine)

## Empirie aus dem Bewerbungsverlauf
- (pflegt das BMS selbst, bitte die Überschrift unverändert lassen)
"""

# Erfundene, umfangreiche Datei: alles, was die Maske NICHT kennt, muss unberührt bleiben.
UMFANGREICH = """<!-- Persönliche Notizen vor der Überschrift, bitte stehen lassen -->
Dieses Profil pflegt Max Mustermann von Hand.

# Kandidatenprofil: Max Mustermann


## Identität
<!-- Kommentar im Abschnitt -->
- **Name:**    Max Mustermann§
- **Positionierung:** Service Delivery Leader, DACH
- **Standort:** Musterweg 3, 12345 Musterstadt (Rhein-Main)
* **Kontakt:** max.mustermann@example.com | +49 170 1234567
- **Telefon privat:** 030 1234567
  - **Hobby:** Wandern
Eine freie Zeile mitten in der Identität.
- **Aktuell:** Manager Professional Services bei der Beispiel GmbH, seit 2024


## Kurzprofil


Erste Zeile des Kurzprofils.

Zweiter Absatz mit Umlauten: äöüß – und Gedankenstrich.§
### Eine Unterüberschrift im Kurzprofil
Letzte Zeile.


## Netzwerk
- Ansprechpartner: Erika Musterfrau
- **Quelle:** Messe

## Zielrolle
- **Ebene:** Director oder Head of
### Unterüberschrift in der Zielrolle
- **Funktion Plan A:** Leitung Professional Services
- **Funktion Plan B:** Head of Customer Success
- **Funktion Plan C:** Beratung
<!-- Branche kommt gleich -->
- **Branche:** Enterprise Software
- **Region:** DACH

## Harte Rahmenbedingungen
- Kein Umzug.

- Mindestens 100 Mitarbeiter.
	- Eingerückt mit Tabulator.

## Sprachen / CV-Fassungen
- **Deutsch:** `data/cv_basis/base_de.docx`
- Englisch: Grundkenntnisse

## Bekannte Skill-Gaps / Red Flags
- Noch wenig Erfahrung im Vertrieb.

## Notizen
Leerzeilen am Ende folgen.

## Empirie aus dem Bewerbungsverlauf
- Absagen: 3 von 10
| Kanal | Antwort |
|---|---|
| Portal | keine |


""".replace("§", "   ")   # § steht für Leerzeichen am Zeilenende (Editoren schneiden sie sonst ab)

UMFANGREICH_CRLF = UMFANGREICH.replace("\n", "\r\n")
UMFANGREICH_OHNE_SCHLUSS = UMFANGREICH.rstrip("\n")
UMFANGREICH_GEMISCHT = UMFANGREICH.replace("\n", "\r\n", 12)   # überwiegend LF, einige CRLF

VOLL = {
    "identitaet": {"name": "Max Mustermann", "positionierung": "Service Delivery Leader, DACH",
                   "anschrift": "Musterweg 3, 12345 Musterstadt", "email": "max.mustermann@example.com",
                   "telefon": "+49 170 1234567", "linkedin": "https://www.linkedin.com/in/max-mustermann/",
                   "aktuell": "Manager Professional Services bei der Beispiel GmbH, seit 2024",
                   "weitere": []},
    "kurzprofil": "Zwei Sätze über mich.",
    "zielrolle": [{"schluessel": k, "wert": f"Wert {k}"} for k in ZIELROLLE_STANDARD],
    "rahmenbedingungen": "- Kein Umzug.\n- Vollzeit.",
    "skill_gaps": "- Noch wenig Erfahrung im Vertrieb.",
}


@pytest.fixture(autouse=True)
def _profil_pfade(tmp_path, monkeypatch):
    """Pfad der Profil-Datei und Papierkorb auf `tmp_path` umlenken (nie die echte Datei) und
    nachprüfen, dass beide wirklich dort liegen."""
    from app import db
    from pipeline import profil_datei, user_profile

    projekt = tmp_path / "projekt"
    monkeypatch.setattr(user_profile, "_PROFIL_MD", projekt / "config" / "profil.md")
    monkeypatch.setattr(db, "DATA_DIR", projekt / "data")

    wurzel = user_profile.PROJECT_ROOT.resolve()
    for pfad in (user_profile._PROFIL_MD, profil_datei._papierkorb_ordner()):
        aufgeloest = pfad.resolve()
        assert tmp_path.resolve() in aufgeloest.parents, f"Test zeigt nicht auf tmp_path: {pfad}"
        assert wurzel not in aufgeloest.parents, f"Test zeigt in die echte Installation: {pfad}"
    yield projekt


@pytest.fixture()
def pd():
    from pipeline import profil_datei
    return profil_datei


@pytest.fixture()
def datei(_profil_pfade):
    from pipeline import user_profile
    return user_profile._PROFIL_MD


def _schreibe(datei, text, newline=""):
    """Datei als Bytes anlegen (kein Zeilenende-Umbau)."""
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_bytes(text.encode("utf-8"))


def _papierkorb_dateien(pd):
    ordner = pd._papierkorb_ordner()
    return sorted(ordner.iterdir()) if ordner.exists() else []


def _diff(alt, neu):
    """(entfernte, hinzugefügte) Zeilen samt Zeilenende."""
    entfernt, neu_z = [], []
    for z in difflib.ndiff(alt.splitlines(keepends=True), neu.splitlines(keepends=True)):
        if z.startswith("- "):
            entfernt.append(z[2:])
        elif z.startswith("+ "):
            neu_z.append(z[2:])
    return entfernt, neu_z


def _mit(basis, **aenderungen):
    """Kopie der Maskendaten (tief) mit Änderungen: `identitaet={...}` wird in die Identität gemischt."""
    import copy
    d = copy.deepcopy(basis)
    ident = aenderungen.pop("identitaet", None)
    if ident:
        d["identitaet"].update(ident)
    d.update(aenderungen)
    return d


@pytest.fixture(params=["vorlage_install", "vorlage_erzeugt", "beispiel", "umfangreich", "umfangreich_crlf",
                        "umfangreich_ohne_schluss", "umfangreich_gemischt", "minimal"])
def text(request, pd):
    from app import beispieldaten

    wahl = request.param
    if wahl == "vorlage_install":
        return VORLAGE_INSTALL
    if wahl == "vorlage_erzeugt":
        return pd.anwenden(None, VOLL)
    if wahl == "beispiel":
        return beispieldaten._profil_md_text()
    if wahl == "umfangreich":
        return UMFANGREICH
    if wahl == "umfangreich_crlf":
        return UMFANGREICH_CRLF
    if wahl == "umfangreich_ohne_schluss":
        return UMFANGREICH_OHNE_SCHLUSS
    if wahl == "umfangreich_gemischt":
        return UMFANGREICH_GEMISCHT
    return "## Identität\n- **Name:** Max Mustermann"


# ── Verlustfreiheit ──────────────────────────────────────────────────────────────────────────────
def test_zerlegen_und_zusammensetzen_ist_bytegleich(pd, text):
    assert pd.zusammensetzen(pd.zerlegen(text)) == text


def test_speichern_ohne_aenderung_ergibt_dieselbe_datei(pd, text):
    assert pd.anwenden(text, pd.lesen_aus_text(text)) == text


def test_speichern_ohne_aenderung_schreibt_weder_datei_noch_papierkorb(pd, datei, text):
    _schreibe(datei, text)
    vorher = datei.stat().st_mtime_ns
    daten = pd.lesen()

    ergebnis = pd.schreiben(daten, daten["stand"])

    assert ergebnis == {"geschrieben": False, "papierkorb": None, "hinweise": ergebnis["hinweise"]}
    assert datei.read_bytes() == text.encode("utf-8")
    assert datei.stat().st_mtime_ns == vorher
    assert _papierkorb_dateien(pd) == []


@pytest.mark.parametrize("roh", [
    "", "\n", "\r\n", "\n\n\n", "ohne Zeilenende", "# Nur Kopf\n", "## Identität", "## Identität\n",
    "## Identität\r\n- **Name:** Max\r\n", "﻿# Kopf mit Bytemarke\n## Identität\n- **Name:** Max\n",
    "a\rb\r\n", "## Kurzprofil\n\n\n\n", "## Zielrolle\n- **Ebene:** x\n\n## Empirie",
])
def test_zerlegen_ist_fuer_beliebige_eingaben_bytegleich(pd, roh):
    assert pd.zusammensetzen(pd.zerlegen(roh)) == roh


def _zufallstext(rnd):
    bausteine = [
        "", "", "   ", "\t", "# Kandidatenprofil: Max Mustermann", "<!-- Kommentar -->", "### Unterüberschrift",
        "Freitext ohne Besonderheit.", "Freitext mit Leerraum am Ende   ", "- Aufzählung ohne Feld",
        "  - eingerückter Punkt", "- **Positionierung:** Leitung DACH", "- **Standort:** Musterweg 3, 12345 Musterstadt",
        "- **Kontakt:** max@example.com · +49 170 1", "- **LinkedIn:** ", "- **Aktuell:**", "* **Hobby:** Wandern",
        "- **Name:** Zweitname", "- **name:** klein", "- **Ebene:** Director", "- **Region:** DACH",
        "- **Ebene:** Doppelt", "| a | b |", "Umlaute: äöüß – €",
        "## Kurzprofil", "## Zielrolle", "## Harte Rahmenbedingungen", "## Bekannte Skill-Gaps / Red Flags",
        "## Sprachen / CV-Fassungen", "## Identität", "## Netzwerk", "## Empirie aus dem Bewerbungsverlauf",
    ]
    zeilen = ["## Identität", "- **Name:** Max Mustermann"]
    zeilen += [rnd.choice(bausteine) for _ in range(rnd.randint(0, 40))]
    if rnd.random() < 0.3:
        zeilen.insert(0, "Kopfzeile vor allem")
    ende = rnd.choice(["\n", "\r\n"])
    text = "".join(z + (ende if rnd.random() < 0.9 else rnd.choice(["\n", "\r\n"])) for z in zeilen)
    if rnd.random() < 0.3:
        text = text.rstrip("\r\n")
    return text


def test_zufallsdateien_bleiben_bytegleich(pd):
    """Kleiner Property-Test: 400 erzeugte Dateien mit gemischten Zeilenenden, Leerzeilen, doppelten
    Abschnitten und Feldern. Zerlegen und Speichern ohne Änderung müssen jede Datei byte-gleich lassen."""
    rnd = random.Random(20261011)
    for _ in range(400):
        t = _zufallstext(rnd)
        assert pd.zusammensetzen(pd.zerlegen(t)) == t, repr(t)
        assert pd.anwenden(t, pd.lesen_aus_text(t)) == t, repr(t)


def test_zufallsdateien_geaenderter_name_aendert_nur_eine_zeile(pd):
    rnd = random.Random(7)
    for _ in range(150):
        t = _zufallstext(rnd)
        daten = pd.lesen_aus_text(t)
        daten["identitaet"]["name"] = "Erika Musterfrau"
        neu = pd.anwenden(t, daten)
        entfernt, hinzu = _diff(t, neu)
        assert len(entfernt) == 1 and len(hinzu) == 1, repr(t)
        assert hinzu[0].rstrip("\r\n") == entfernt[0].rstrip("\r\n").replace("Max Mustermann", "Erika Musterfrau")
        assert hinzu[0][len(hinzu[0].rstrip("\r\n")):] == entfernt[0][len(entfernt[0].rstrip("\r\n")):]


def test_bytemarke_am_dateianfang_bleibt(pd, datei):
    roh = "﻿# Kandidatenprofil: Max Mustermann\n\n## Identität\n- **Name:** Max Mustermann\n".encode("utf-8")
    datei.parent.mkdir(parents=True)
    datei.write_bytes(roh)
    daten = pd.lesen()
    assert daten["identitaet"]["name"] == "Max Mustermann"

    pd.schreiben(_mit(daten, identitaet={"name": "Erika Musterfrau"}), daten["stand"])

    assert datei.read_bytes() == roh.replace(b"Max Mustermann\n\n##", b"Max Mustermann\n\n##").replace(
        b"- **Name:** Max Mustermann", b"- **Name:** Erika Musterfrau")
    assert datei.read_bytes().startswith(b"\xef\xbb\xbf")


# ── Lesen ────────────────────────────────────────────────────────────────────────────────────────
def test_lesen_ohne_datei_liefert_leere_werte_und_standard_schluessel(pd):
    d = pd.lesen()

    assert d["vorhanden"] is False and d["stand"] == ""
    assert d["identitaet"] == {"name": "", "positionierung": "", "anschrift": "", "email": "", "telefon": "",
                               "linkedin": "", "aktuell": "", "weitere": []}
    assert d["zielrolle"] == [{"schluessel": k, "wert": ""} for k in ZIELROLLE_STANDARD]
    assert d["kurzprofil"] == d["rahmenbedingungen"] == d["skill_gaps"] == ""
    assert d["unveraendert"] == [] and d["hinweise"] == []
    assert list(d) == ["vorhanden", "stand", "identitaet", "kurzprofil", "zielrolle", "rahmenbedingungen",
                       "skill_gaps", "unveraendert", "hinweise"]


def test_lesen_der_umfangreichen_datei(pd, datei):
    _schreibe(datei, UMFANGREICH)

    d = pd.lesen()

    assert d["vorhanden"] is True
    assert d["stand"] == __import__("hashlib").sha256(UMFANGREICH.encode("utf-8")).hexdigest()
    ident = d["identitaet"]
    assert ident["name"] == "Max Mustermann"                                  # getrimmt
    assert ident["anschrift"] == "Musterweg 3, 12345 Musterstadt (Rhein-Main)"
    assert (ident["email"], ident["telefon"]) == ("max.mustermann@example.com", "+49 170 1234567")
    assert ident["weitere"] == [{"schluessel": "Telefon privat", "wert": "030 1234567"},
                                {"schluessel": "Hobby", "wert": "Wandern"}]
    assert d["kurzprofil"].startswith("Erste Zeile des Kurzprofils.\n\nZweiter Absatz")
    assert d["kurzprofil"].endswith("### Eine Unterüberschrift im Kurzprofil\nLetzte Zeile.")
    # Alle Feldzeilen der Zielrolle, dazu die fehlenden Standard-Schlüssel (leer) -- Plan C steht in der Datei
    assert [e["schluessel"] for e in d["zielrolle"]] == [
        "Ebene", "Funktion Plan A", "Funktion Plan B", "Funktion Plan C", "Branche", "Region", "Zieltermin"]
    assert d["zielrolle"][-1] == {"schluessel": "Zieltermin", "wert": ""}
    assert d["rahmenbedingungen"] == "- Kein Umzug.\n\n- Mindestens 100 Mitarbeiter.\n\t- Eingerückt mit Tabulator."
    assert d["skill_gaps"] == "- Noch wenig Erfahrung im Vertrieb."
    assert d["unveraendert"] == ["Netzwerk", "Sprachen / CV-Fassungen", "Notizen",
                                 "Empirie aus dem Bewerbungsverlauf"]


def test_lesen_der_beispiel_datei(pd, datei):
    from app import beispieldaten
    _schreibe(datei, beispieldaten._profil_md_text())

    d = pd.lesen()

    assert d["identitaet"]["name"] == beispieldaten.NAME
    assert d["identitaet"]["anschrift"] == beispieldaten._ANSCHRIFT
    assert d["identitaet"]["email"] == beispieldaten._MAIL and d["identitaet"]["telefon"] == beispieldaten._TELEFON
    assert d["unveraendert"] == ["Sprachen / CV-Fassungen", "Empirie aus dem Bewerbungsverlauf"]
    assert d["hinweise"] == []


def test_abschnitte_werden_ohne_rücksicht_auf_gross_kleinschreibung_erkannt(pd):
    t = "## IDENTITÄT\n- **Name:** Max\n\n## kurzprofil (lang)\nText\n\n## HARTE rahmenbedingungen\n- x\n"
    d = pd.lesen_aus_text(t)
    assert d["identitaet"]["name"] == "Max" and d["kurzprofil"] == "Text" and d["rahmenbedingungen"] == "- x"
    assert d["unveraendert"] == []


def test_zweiter_abschnitt_gleichen_namens_bleibt_unveraendert(pd):
    t = "## Identität\n- **Name:** Max\n\n## Kurzprofil\nErster\n\n## Kurzprofil\nZweiter\n"
    d = pd.lesen_aus_text(t)
    assert d["kurzprofil"] == "Erster" and d["unveraendert"] == ["Kurzprofil"]
    d["kurzprofil"] = "Neu"
    assert pd.anwenden(t, d) == "## Identität\n- **Name:** Max\n\n## Kurzprofil\nNeu\n\n## Kurzprofil\nZweiter\n"


def test_unterueberschrift_mit_drei_rauten_beginnt_keinen_abschnitt(pd):
    t = "## Kurzprofil\nText\n### Unter\nmehr\n## Zielrolle\n- **Ebene:** x\n"
    d = pd.lesen_aus_text(t)
    assert d["kurzprofil"] == "Text\n### Unter\nmehr" and d["unveraendert"] == []


def test_nicht_utf8_datei_wird_nicht_angefasst(pd, datei):
    datei.parent.mkdir(parents=True)
    roh = b"## Identit\xe4t\n- **Name:** Max M\xfcller\n"      # Latin-1
    datei.write_bytes(roh)

    with pytest.raises(pd.DateiNichtLesbar) as fehler:
        pd.lesen()
    assert "UTF-8" in str(fehler.value)
    stand = pd.stand_von(roh)
    with pytest.raises(pd.DateiNichtLesbar):
        pd.schreiben(VOLL, stand)
    assert datei.read_bytes() == roh
    assert _papierkorb_dateien(pd) == []


# ── Kontakt ──────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("wert,erwartet", [
    ("max@example.com · +49 170 1", ("max@example.com", "+49 170 1")),
    ("max@example.com | +49 170 1", ("max@example.com", "+49 170 1")),
    ("max@example.com|+49 170 1", ("max@example.com", "+49 170 1")),
    ("+49 170 1 · max@example.com", ("max@example.com", "+49 170 1")),
    ("max@example.com", ("max@example.com", "")),
    ("+49 170 1", ("", "+49 170 1")),
    ("", ("", "")),
    ("max@example.com · +49 170 1 · +49 30 2", ("max@example.com", "+49 170 1 · +49 30 2")),
    ("a@b.de · c@d.de", ("a@b.de", "c@d.de")),      # nur der erste Teil mit @ ist die E-Mail
])
def test_kontakt_teilen(pd, wert, erwartet):
    assert pd.kontakt_teilen(wert) == erwartet


@pytest.mark.parametrize("email,telefon,erwartet", [
    ("max@example.com", "+49 170 1", "max@example.com · +49 170 1"),
    ("max@example.com", "", "max@example.com"),
    ("", "+49 170 1", "+49 170 1"),
    ("", "", ""),
    ("  max@example.com ", " +49 170 1  ", "max@example.com · +49 170 1"),
])
def test_kontakt_zusammensetzen(pd, email, telefon, erwartet):
    assert pd.kontakt_zusammensetzen(email, telefon) == erwartet


def test_kontakt_zeile_mit_senkrechtem_strich_bleibt_wenn_unveraendert(pd):
    t = "## Identität\n- **Name:** Max\n- **Kontakt:** max@example.com | +49 170 1\n"
    d = pd.lesen_aus_text(t)
    assert pd.anwenden(t, d) == t

    d["identitaet"]["telefon"] = "+49 30 2"
    assert pd.anwenden(t, d) == "## Identität\n- **Name:** Max\n- **Kontakt:** max@example.com · +49 30 2\n"


def test_kontakt_nur_email_aendern_laesst_telefon_stehen(pd):
    t = "## Identität\n- **Name:** Max\n- **Kontakt:** max@example.com · +49 170 1\n"
    neu = pd.anwenden(t, {"identitaet": {"name": "Max", "email": "erika@example.com"}})
    assert neu == "## Identität\n- **Name:** Max\n- **Kontakt:** erika@example.com · +49 170 1\n"


def test_kontakt_wird_zur_zeile_mit_e_mail_und_telefon(pd):
    t = "## Identität\n- **Name:** Max\n"
    neu = pd.anwenden(t, _mit(VOLL, identitaet={"positionierung": "", "linkedin": "", "aktuell": ""},
                              kurzprofil=None, zielrolle=None, rahmenbedingungen=None, skill_gaps=None))
    assert neu == ("## Identität\n- **Name:** Max Mustermann\n- **Standort:** Musterweg 3, 12345 Musterstadt\n"
                   "- **Kontakt:** max.mustermann@example.com · +49 170 1234567\n")


# ── Änderungen: genau eine Zeile ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("feld,wert,alte_zeile,neue_zeile", [
    ("name", "Erika Musterfrau", "- **Name:**    Max Mustermann   ", "- **Name:**    Erika Musterfrau"),
    ("positionierung", "Head of Delivery", "- **Positionierung:** Service Delivery Leader, DACH",
     "- **Positionierung:** Head of Delivery"),
    ("anschrift", "Beispielweg 5, 54321 Musterstadt", "- **Standort:** Musterweg 3, 12345 Musterstadt (Rhein-Main)",
     "- **Standort:** Beispielweg 5, 54321 Musterstadt"),
    ("aktuell", "Selbstständig", "- **Aktuell:** Manager Professional Services bei der Beispiel GmbH, seit 2024",
     "- **Aktuell:** Selbstständig"),
])
@pytest.mark.parametrize("variante", ["lf", "crlf", "ohne_schluss"])
def test_geaendertes_identitaetsfeld_aendert_genau_eine_zeile(pd, feld, wert, alte_zeile, neue_zeile, variante):
    basis = {"lf": UMFANGREICH, "crlf": UMFANGREICH_CRLF, "ohne_schluss": UMFANGREICH_OHNE_SCHLUSS}[variante]
    daten = pd.lesen_aus_text(basis)
    daten["identitaet"][feld] = wert

    neu = pd.anwenden(basis, daten)

    entfernt, hinzu = _diff(basis, neu)
    ende = "\r\n" if variante == "crlf" else "\n"
    if feld == "name":
        # Abnahme P2-69: Die Titelzeile `# Kandidatenprofil: <Name>` im Dateikopf zieht mit.
        assert entfernt == ["# Kandidatenprofil: Max Mustermann" + ende, alte_zeile + ende]
        assert hinzu == ["# Kandidatenprofil: " + wert + ende, neue_zeile + ende]
    else:
        assert entfernt == [alte_zeile + ende] and hinzu == [neue_zeile + ende]


def test_geaendertes_zielrolle_feld_aendert_genau_eine_zeile(pd):
    daten = pd.lesen_aus_text(UMFANGREICH)
    daten["zielrolle"][1]["wert"] = "Leitung Service Delivery"

    neu = pd.anwenden(UMFANGREICH, daten)

    assert _diff(UMFANGREICH, neu) == (["- **Funktion Plan A:** Leitung Professional Services\n"],
                                       ["- **Funktion Plan A:** Leitung Service Delivery\n"])


def test_geaenderte_weitere_zeile_aendert_genau_eine_zeile_und_behaelt_einrueckung(pd):
    daten = pd.lesen_aus_text(UMFANGREICH)
    daten["identitaet"]["weitere"][1]["wert"] = "Radfahren"

    neu = pd.anwenden(UMFANGREICH, daten)

    assert _diff(UMFANGREICH, neu) == (["  - **Hobby:** Wandern\n"], ["  - **Hobby:** Radfahren\n"])


def test_geaendertes_freitextfeld_aendert_nur_den_rumpf_und_behaelt_leerzeilen(pd):
    daten = pd.lesen_aus_text(UMFANGREICH)
    daten["rahmenbedingungen"] = "- Kein Umzug.\n- Vollzeit."

    neu = pd.anwenden(UMFANGREICH, daten)

    alt_abschnitt = ("## Harte Rahmenbedingungen\n- Kein Umzug.\n\n- Mindestens 100 Mitarbeiter.\n"
                     "\t- Eingerückt mit Tabulator.\n\n## Sprachen")
    neu_abschnitt = "## Harte Rahmenbedingungen\n- Kein Umzug.\n- Vollzeit.\n\n## Sprachen"
    assert alt_abschnitt in UMFANGREICH
    assert neu == UMFANGREICH.replace(alt_abschnitt, neu_abschnitt)


def test_kurzprofil_aendern_behaelt_die_leerzeilen_davor_und_danach(pd):
    """Im Beispiel stehen zwei Leerzeilen vor und zwei nach dem Rumpf."""
    daten = pd.lesen_aus_text(UMFANGREICH)
    daten["kurzprofil"] = "Nur noch eine Zeile."

    neu = pd.anwenden(UMFANGREICH, daten)

    assert "## Kurzprofil\n\n\nNur noch eine Zeile.\n\n\n## Netzwerk\n" in neu
    # alles davor und danach unverändert
    kopf_alt, _, rest_alt = UMFANGREICH.partition("## Kurzprofil\n")
    kopf_neu, _, rest_neu = neu.partition("## Kurzprofil\n")
    assert kopf_alt == kopf_neu
    assert rest_alt[rest_alt.index("## Netzwerk"):] == rest_neu[rest_neu.index("## Netzwerk"):]


def test_freitext_mit_crlf_behaelt_zeilenenden_und_neue_zeilen_sind_crlf(pd):
    daten = pd.lesen_aus_text(UMFANGREICH_CRLF)
    daten["skill_gaps"] = "- Erste Lücke.\n- Zweite Lücke.\n- Dritte Lücke."

    neu = pd.anwenden(UMFANGREICH_CRLF, daten)

    assert "## Bekannte Skill-Gaps / Red Flags\r\n- Erste Lücke.\r\n- Zweite Lücke.\r\n- Dritte Lücke.\r\n\r\n## Notizen" in neu
    assert "\n" not in neu.replace("\r\n", "")
    assert [z for z in neu.split("\r\n")].count("") == [z for z in UMFANGREICH_CRLF.split("\r\n")].count("")


def test_freitext_kommt_mit_browser_zeilenenden_und_umgebenden_leerzeilen_zurueck(pd):
    """Ein Textfeld schickt `\\r\\n`/`\\n` und oft Leerzeilen am Ende: Das gilt als unverändert."""
    daten = pd.lesen_aus_text(UMFANGREICH)
    daten["kurzprofil"] = "\r\n" + daten["kurzprofil"].replace("\n", "\r\n") + "\r\n\r\n"
    daten["rahmenbedingungen"] = daten["rahmenbedingungen"] + "   \n"
    assert pd.anwenden(UMFANGREICH, daten) == UMFANGREICH


def test_freitext_leeren_laesst_ueberschrift_und_leerzeilen_stehen(pd):
    daten = pd.lesen_aus_text(UMFANGREICH)
    daten["skill_gaps"] = ""

    neu = pd.anwenden(UMFANGREICH, daten)

    assert _diff(UMFANGREICH, neu) == (["- Noch wenig Erfahrung im Vertrieb.\n"], [])
    assert "## Bekannte Skill-Gaps / Red Flags\n\n## Notizen" in neu


def test_leerer_freitext_abschnitt_wird_direkt_unter_der_ueberschrift_gefuellt(pd):
    t = "## Identität\n- **Name:** Max\n\n## Kurzprofil\n\n## Zielrolle\n"
    neu = pd.anwenden(t, {"identitaet": {"name": "Max"}, "kurzprofil": "Neu"})
    assert neu == "## Identität\n- **Name:** Max\n\n## Kurzprofil\nNeu\n\n## Zielrolle\n"


def test_freitext_am_dateiende_ohne_zeilenende(pd):
    t = "## Identität\n- **Name:** Max\n\n## Kurzprofil\nAlt"
    neu = pd.anwenden(t, {"identitaet": {"name": "Max"}, "kurzprofil": "Neu\nzweite Zeile"})
    assert neu == "## Identität\n- **Name:** Max\n\n## Kurzprofil\nNeu\nzweite Zeile"       # weiter ohne Schluss


def test_neue_zeile_am_dateiende_ohne_zeilenende_haengt_sauber_an(pd):
    t = "## Identität\n- **Name:** Max"
    neu = pd.anwenden(t, {"identitaet": {"name": "Max", "linkedin": "https://example.com/in/max"}})
    assert neu == "## Identität\n- **Name:** Max\n- **LinkedIn:** https://example.com/in/max"


def test_wert_einer_leeren_zeile_bekommt_einen_abstand(pd):
    t = "## Identität\n- **Name:** Max\n- **Aktuell:**\n- **Standort:**   \n"
    daten = pd.lesen_aus_text(t)
    daten["identitaet"]["aktuell"] = "Zusteller"
    daten["identitaet"]["anschrift"] = "Musterweg 3, 12345 Musterstadt"
    assert pd.anwenden(t, daten) == ("## Identität\n- **Name:** Max\n- **Aktuell:** Zusteller\n"
                                     "- **Standort:**   Musterweg 3, 12345 Musterstadt\n")


# ── Optionale Felder: entfernen und anlegen ──────────────────────────────────────────────────────
@pytest.mark.parametrize("feld,zeile", [
    ("positionierung", "- **Positionierung:** Service Delivery Leader, DACH\n"),
    ("aktuell", "- **Aktuell:** Manager Professional Services bei der Beispiel GmbH, seit 2024\n"),
])
def test_optionale_identitaetsfelder_entfallen_bei_leerem_wert(pd, feld, zeile):
    daten = pd.lesen_aus_text(UMFANGREICH)
    daten["identitaet"][feld] = ""

    neu = pd.anwenden(UMFANGREICH, daten)

    assert _diff(UMFANGREICH, neu) == ([zeile], [])


def test_linkedin_entfernen_und_wieder_anlegen(pd):
    t = VORLAGE_INSTALL
    daten = pd.lesen_aus_text(t)
    daten["identitaet"]["linkedin"] = ""
    ohne = pd.anwenden(t, daten)
    assert _diff(t, ohne) == (["- **LinkedIn:** https://www.linkedin.com/in/max-mustermann/\n"], [])

    daten = pd.lesen_aus_text(ohne)
    assert daten["identitaet"]["linkedin"] == ""
    daten["identitaet"]["linkedin"] = "https://www.linkedin.com/in/max-mustermann/"
    wieder = pd.anwenden(ohne, daten)
    # Neue Zeile kommt HINTER die letzte Feldzeile des Abschnitts (hinter Aktuell), nicht an die alte Stelle.
    assert wieder == t.replace("- **LinkedIn:** https://www.linkedin.com/in/max-mustermann/\n", "").replace(
        "seit 2024\n", "seit 2024\n- **LinkedIn:** https://www.linkedin.com/in/max-mustermann/\n")


def test_neues_feld_kommt_hinter_die_letzte_feldzeile_vor_freien_zeilen(pd):
    daten = pd.lesen_aus_text(UMFANGREICH)
    daten["identitaet"]["linkedin"] = "https://example.com/in/max"

    neu = pd.anwenden(UMFANGREICH, daten)

    assert _diff(UMFANGREICH, neu) == ([], ["- **LinkedIn:** https://example.com/in/max\n"])
    zeilen = neu.splitlines()
    i = zeilen.index("- **LinkedIn:** https://example.com/in/max")
    assert zeilen[i - 1].startswith("- **Aktuell:**") and zeilen[i + 1] == ""


def test_neues_feld_in_crlf_datei_bekommt_crlf(pd):
    daten = pd.lesen_aus_text(UMFANGREICH_CRLF)
    daten["identitaet"]["linkedin"] = "https://example.com/in/max"
    neu = pd.anwenden(UMFANGREICH_CRLF, daten)
    assert _diff(UMFANGREICH_CRLF, neu) == ([], ["- **LinkedIn:** https://example.com/in/max\r\n"])


def test_neues_feld_mit_leerem_wert_wird_nicht_angelegt(pd):
    t = "## Identität\n- **Name:** Max\n"
    daten = pd.lesen_aus_text(t)
    daten["identitaet"].update(linkedin="", positionierung="  ", aktuell="")
    assert pd.anwenden(t, daten) == t


def test_vorhandenes_zielrolle_feld_mit_leerem_wert_behaelt_seine_zeile(pd):
    daten = pd.lesen_aus_text(UMFANGREICH)
    daten["zielrolle"][5]["wert"] = ""          # Region

    neu = pd.anwenden(UMFANGREICH, daten)

    assert _diff(UMFANGREICH, neu) == (["- **Region:** DACH\n"], ["- **Region:**\n"])


def test_fehlender_standard_schluessel_der_zielrolle_wird_angelegt(pd):
    daten = pd.lesen_aus_text(UMFANGREICH)
    assert daten["zielrolle"][-1] == {"schluessel": "Zieltermin", "wert": ""}
    daten["zielrolle"][-1]["wert"] = "bis 31.12.2026"

    neu = pd.anwenden(UMFANGREICH, daten)

    assert _diff(UMFANGREICH, neu) == ([], ["- **Zieltermin:** bis 31.12.2026\n"])
    zeilen = neu.splitlines()
    assert zeilen[zeilen.index("- **Zieltermin:** bis 31.12.2026") - 1] == "- **Region:** DACH"


def test_standard_schluessel_wird_ohne_beachtung_der_schreibweise_zugeordnet(pd):
    t = "## Identität\n- **Name:** Max\n\n## Zielrolle\n- **ebene:** alt\n"
    neu = pd.anwenden(t, {"identitaet": {"name": "Max"}, "zielrolle": [{"schluessel": "Ebene", "wert": "neu"}]})
    assert neu == "## Identität\n- **Name:** Max\n\n## Zielrolle\n- **ebene:** neu\n"


def test_doppelter_schluessel_wird_der_reihe_nach_zugeordnet(pd):
    t = "## Identität\n- **Name:** Max\n\n## Zielrolle\n- **Ebene:** eins\n- **Ebene:** zwei\n"
    d = pd.lesen_aus_text(t)
    assert [e["wert"] for e in d["zielrolle"][:2]] == ["eins", "zwei"]
    assert pd.anwenden(t, d) == t
    d["zielrolle"][1]["wert"] = "zwei neu"
    assert pd.anwenden(t, d) == t.replace("zwei", "zwei neu")


def test_nicht_genannte_zeilen_bleiben_bei_unvollstaendiger_liste_stehen(pd):
    daten = pd.lesen_aus_text(UMFANGREICH)
    daten["zielrolle"] = [daten["zielrolle"][0]]
    daten["identitaet"]["weitere"] = []
    assert pd.anwenden(UMFANGREICH, daten) == UMFANGREICH


def test_fehlende_schluessel_in_der_eingabe_lassen_die_datei_unberuehrt(pd):
    """Nur der Name ist Pflicht; was die Eingabe nicht nennt, bleibt, wie es ist."""
    assert pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max Mustermann"}}) == UMFANGREICH


def test_standort_und_kontakt_entfallen_bei_leerem_wert_weil_der_leser_sonst_die_naechste_zeile_nimmt(pd, datei):
    """Begründung der Abweichung von der Spec: `user_profile` liest mit `\\*\\*Standort:\\*\\*\\s*(.+)`,
    `\\s*` überspringt den Zeilenumbruch. Eine leere Zeile ließe die FOLGENDE Zeile zur Anschrift werden."""
    from pipeline import user_profile
    leer = "## Identität\n- **Name:** Max Mustermann\n- **Standort:**\n- **Kontakt:** max@example.com\n"
    _schreibe(datei, leer)
    assert user_profile.anschrift() == "- **Kontakt:** max@example.com"      # der Leser-Fehler, hier belegt

    voll = ("## Identität\n- **Name:** Max Mustermann\n- **Standort:** Musterweg 3, 12345 Musterstadt\n"
            "- **Kontakt:** max@example.com · +49 170 1\n- **Aktuell:** Zusteller\n")
    daten = pd.lesen_aus_text(voll)
    daten["identitaet"].update(anschrift="", email="", telefon="")
    neu = pd.anwenden(voll, daten)

    assert neu == "## Identität\n- **Name:** Max Mustermann\n- **Aktuell:** Zusteller\n"
    _schreibe(datei, neu)
    assert user_profile.anschrift() == "" and user_profile.briefkopf() == "Max Mustermann"


def test_leere_zeile_aus_von_hand_bearbeiteter_datei_bleibt_bei_unveraendertem_speichern(pd):
    """Verlustfrei: Was die Maske nicht ändert, fasst sie nicht an -- auch keine leere Standort-Zeile."""
    leer = "## Identität\n- **Name:** Max Mustermann\n- **Standort:**\n- **Kontakt:** max@example.com\n"
    assert pd.anwenden(leer, pd.lesen_aus_text(leer)) == leer


# ── Abschnitte, die es nicht gibt ────────────────────────────────────────────────────────────────
def test_fehlender_bekannter_abschnitt_wird_nur_mit_inhalt_vor_empirie_angelegt(pd):
    t = "## Identität\n- **Name:** Max\n\n## Sprachen / CV-Fassungen\n- **Deutsch:** `x`\n\n## Empirie aus dem Bewerbungsverlauf\n- a\n"
    d = pd.lesen_aus_text(t)
    assert pd.anwenden(t, d) == t                               # ohne Inhalt: nichts angelegt

    d["kurzprofil"] = "Zwei Sätze."
    d["rahmenbedingungen"] = "- Kein Umzug."
    neu = pd.anwenden(t, d)

    assert neu == ("## Identität\n- **Name:** Max\n\n## Sprachen / CV-Fassungen\n- **Deutsch:** `x`\n\n"
                   "## Kurzprofil\nZwei Sätze.\n\n## Harte Rahmenbedingungen\n- Kein Umzug.\n\n"
                   "## Empirie aus dem Bewerbungsverlauf\n- a\n")


def test_fehlender_abschnitt_ohne_empirie_kommt_ans_dateiende(pd):
    t = "## Identität\n- **Name:** Max\n"
    d = pd.lesen_aus_text(t)
    d["kurzprofil"] = "Zwei Sätze."
    d["zielrolle"][0]["wert"] = "Director"

    neu = pd.anwenden(t, d)

    assert neu == ("## Identität\n- **Name:** Max\n\n## Kurzprofil\nZwei Sätze.\n\n"
                   "## Zielrolle\n- **Ebene:** Director\n")


def test_fehlender_abschnitt_am_ende_einer_datei_ohne_zeilenende(pd):
    t = "## Identität\n- **Name:** Max"
    neu = pd.anwenden(t, {"identitaet": {"name": "Max"}, "kurzprofil": "Text"})
    assert neu == "## Identität\n- **Name:** Max\n\n## Kurzprofil\nText"


def test_fehlende_identitaet_wird_angelegt(pd):
    t = "# Eigene Datei\n\n## Kurzprofil\nText\n"
    neu = pd.anwenden(t, {"identitaet": {"name": "Max Mustermann"}})
    assert neu == "# Eigene Datei\n\n## Kurzprofil\nText\n\n## Identität\n- **Name:** Max Mustermann\n"
    assert pd.lesen_aus_text(neu)["identitaet"]["name"] == "Max Mustermann"


def test_leere_datei_wird_zur_identitaet(pd):
    assert pd.anwenden("", {"identitaet": {"name": "Max"}}) == "## Identität\n- **Name:** Max\n"


# ── Fehlende Datei → Vorlage ─────────────────────────────────────────────────────────────────────
def test_fehlende_datei_ergibt_die_vorlage_und_die_leser_liefern_die_eingaben(pd, datei):
    from pipeline import user_profile
    daten = pd.lesen()
    daten["identitaet"].update(name="Max Mustermann", anschrift="Musterweg 3, 12345 Musterstadt",
                               email="max.mustermann@example.com", telefon="+49 170 1234567",
                               linkedin="https://www.linkedin.com/in/max-mustermann/")
    daten["kurzprofil"] = "Zwei Sätze über Max."
    daten["rahmenbedingungen"] = "- Kein Umzug."
    daten["zielrolle"][0]["wert"] = "Director oder Head of"
    daten["zielrolle"][5]["wert"] = "neue Rolle bis 31.12.2026"

    ergebnis = pd.schreiben(daten, "")

    assert ergebnis["geschrieben"] is True and ergebnis["papierkorb"] is None
    assert datei.read_text(encoding="utf-8") == """# Kandidatenprofil: Max Mustermann

## Identität
- **Name:** Max Mustermann
- **Standort:** Musterweg 3, 12345 Musterstadt
- **Kontakt:** max.mustermann@example.com · +49 170 1234567
- **LinkedIn:** https://www.linkedin.com/in/max-mustermann/

## Kurzprofil
Zwei Sätze über Max.

## Zielrolle
- **Ebene:** Director oder Head of
- **Zieltermin:** neue Rolle bis 31.12.2026

## Harte Rahmenbedingungen
- Kein Umzug.

## Sprachen / CV-Fassungen
- **Deutsch:** `data/cv_basis/base_de.docx`
- **Englisch:** `data/cv_basis/base_en.docx`

## Bekannte Skill-Gaps / Red Flags

## Empirie aus dem Bewerbungsverlauf
- (pflegt das BMS selbst, bitte die Überschrift unverändert lassen)
"""
    assert user_profile.user_name() == "Max Mustermann"
    assert user_profile.user_first_name() == "Max"
    assert user_profile.anschrift() == "Musterweg 3, 12345 Musterstadt"
    assert user_profile.briefkopf_ort() == "Musterstadt"
    assert user_profile.briefkopf() == ("Max Mustermann\nMusterweg 3, 12345 Musterstadt\n"
                                        "max.mustermann@example.com | +49 170 1234567\n"
                                        "LinkedIn: https://www.linkedin.com/in/max-mustermann/")


def test_vorlage_mit_nur_dem_namen(pd, datei):
    from pipeline import user_profile
    pd.schreiben({"identitaet": {"name": "Max Mustermann"}}, "")
    text = datei.read_text(encoding="utf-8")
    assert text.startswith("# Kandidatenprofil: Max Mustermann\n\n## Identität\n- **Name:** Max Mustermann\n\n## Kurzprofil\n\n## Zielrolle\n")
    assert user_profile.user_name() == "Max Mustermann" and user_profile.anschrift() == ""
    # und die erzeugte Datei ist selbst ein Rundweg-Fall
    assert pd.anwenden(text, pd.lesen_aus_text(text)) == text


def test_vorlage_wird_durch_die_leser_der_beispieldatei_gleich_gelesen(pd):
    """Aufbau wie `beispieldaten._profil_md_text()`: dieselben Abschnitte in derselben Reihenfolge."""
    from app import beispieldaten
    vorlage = pd.anwenden(None, VOLL)
    ueberschriften = lambda t: [z for z in t.splitlines() if z.startswith("## ")]
    erwartet = [u for u in ueberschriften(beispieldaten._profil_md_text())]
    assert ueberschriften(vorlage) == erwartet


def test_weitere_felder_ohne_datei_sind_nicht_erlaubt(pd):
    with pytest.raises(ValueError, match="gibt es in Ihrer Profil-Datei nicht"):
        pd.anwenden(None, {"identitaet": {"name": "Max", "weitere": [{"schluessel": "Hobby", "wert": "x"}]}})


# ── Unberührtes ──────────────────────────────────────────────────────────────────────────────────
def test_empirie_und_unbekannte_abschnitte_bleiben_bytegleich(pd):
    daten = pd.lesen_aus_text(UMFANGREICH_CRLF)
    daten["identitaet"].update(name="Erika Musterfrau", anschrift="Beispielweg 5, 54321 Musterstadt",
                               linkedin="https://example.com/in/erika")
    daten["kurzprofil"] = "Ganz neu."
    daten["zielrolle"][0]["wert"] = "Head of"
    daten["rahmenbedingungen"] = "- Neu."
    daten["skill_gaps"] = "- Neu."

    neu = pd.anwenden(UMFANGREICH_CRLF, daten)

    def abschnitt(text, titel):
        start = text.index("## " + titel)
        ende = text.find("\r\n## ", start + 1)
        return text[start:] if ende < 0 else text[start:ende + 2]

    for titel in ("Netzwerk", "Sprachen / CV-Fassungen", "Notizen", "Empirie aus dem Bewerbungsverlauf"):
        assert abschnitt(neu, titel) == abschnitt(UMFANGREICH_CRLF, titel), titel
    # Dateikopf (alles vor der ersten Überschrift) unverändert bis auf die Titelzeile, die dem
    # neuen Namen folgt (Abnahme P2-69)
    kopf = UMFANGREICH_CRLF[:UMFANGREICH_CRLF.index("## Identität")]
    assert "# Kandidatenprofil: Max Mustermann\r\n" in kopf
    assert neu.startswith(kopf.replace("# Kandidatenprofil: Max Mustermann\r\n",
                                       "# Kandidatenprofil: Erika Musterfrau\r\n"))
    # Kommentar, Unterüberschriften und freie Zeilen in bekannten Abschnitten bleiben
    for zeile in ("<!-- Kommentar im Abschnitt -->", "Eine freie Zeile mitten in der Identität.",
                  "### Unterüberschrift in der Zielrolle", "<!-- Branche kommt gleich -->",
                  "- **Funktion Plan C:** Beratung", "- **Telefon privat:** 030 1234567"):
        assert zeile + "\r\n" in neu, zeile


def test_unbekannte_feldzeilen_in_bekannten_abschnitten_bleiben(pd):
    daten = pd.lesen_aus_text(UMFANGREICH)
    daten["identitaet"]["name"] = "Erika Musterfrau"
    neu = pd.anwenden(UMFANGREICH, daten)
    assert "- **Telefon privat:** 030 1234567\n  - **Hobby:** Wandern\n" in neu
    assert "* **Kontakt:** max.mustermann@example.com | +49 170 1234567\n" in neu     # `*`-Aufzählung und `|` bleiben


# ── Prüfungen ────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ident", [{}, {"name": None}, {"name": ""}, {"name": "   "}])
def test_name_ist_pflicht(pd, ident):
    with pytest.raises(ValueError) as fehler:
        pd.anwenden(UMFANGREICH, {"identitaet": ident})
    assert "Namen" in str(fehler.value) and "Sie" in str(fehler.value)


def test_name_ist_pflicht_auch_ohne_identitaet_und_bei_nicht_dict(pd):
    for daten in ({}, {"kurzprofil": "x"}, {"identitaet": None}):
        with pytest.raises(ValueError, match="Namen"):
            pd.anwenden(UMFANGREICH, daten)
    for daten in (None, [], "x"):
        with pytest.raises(ValueError, match="unerwartetes Format"):
            pd.anwenden(UMFANGREICH, daten)


@pytest.mark.parametrize("feld", ["name", "positionierung", "anschrift", "email", "telefon", "linkedin", "aktuell"])
@pytest.mark.parametrize("umbruch", ["\n", "\r\n", "\r", " "])
def test_einzeilige_felder_enthalten_keinen_zeilenumbruch(pd, feld, umbruch):
    ident = {"name": "Max Mustermann", feld: f"Erste{umbruch}Zweite"}
    with pytest.raises(ValueError, match="nur eine Zeile"):
        pd.anwenden(UMFANGREICH, {"identitaet": ident})


def test_wert_von_zielrolle_und_weitere_enthaelt_keinen_zeilenumbruch(pd):
    with pytest.raises(ValueError, match="nur eine Zeile"):
        pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max"}, "zielrolle": [{"schluessel": "Ebene", "wert": "a\nb"}]})
    with pytest.raises(ValueError, match="nur eine Zeile"):
        pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max", "weitere": [{"schluessel": "Hobby", "wert": "a\nb"}]}})


def test_schluessel_muessen_in_der_datei_stehen_oder_standard_sein(pd):
    with pytest.raises(ValueError, match="‚Erfunden‘ gibt es in Ihrer Profil-Datei nicht"):
        pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max", "weitere": [{"schluessel": "Erfunden", "wert": "x"}]}})
    with pytest.raises(ValueError, match="‚Erfunden‘ gibt es in Ihrer Profil-Datei nicht"):
        pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max"}, "zielrolle": [{"schluessel": "Erfunden", "wert": "x"}]})
    # auch mit leerem Wert: keine frei erfundenen Schlüssel über die API
    with pytest.raises(ValueError, match="Erfunden"):
        pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max"}, "zielrolle": [{"schluessel": "Erfunden", "wert": ""}]})
    # Die Schlüssel der Identität gehören zu den Maskenfeldern, nicht zu `weitere`
    with pytest.raises(ValueError, match="‚LinkedIn‘ gibt es"):
        pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max", "weitere": [{"schluessel": "LinkedIn", "wert": "x"}]}})
    # Standard-Schlüssel dürfen neu entstehen; ein Identitätsschlüssel nicht über die Zielrolle
    ok = pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max Mustermann"},
                                   "zielrolle": [{"schluessel": "zieltermin", "wert": "bald"}]})
    assert "- **Zieltermin:** bald\n" in ok


def test_listeneintraege_brauchen_schluessel_und_wert(pd):
    for eintrag in ({"wert": "x"}, {"schluessel": "", "wert": "x"}, {"schluessel": "Ebene"}, "Ebene", None,
                    {"schluessel": 5, "wert": "x"}, {"schluessel": "Ebene", "wert": 5}):
        with pytest.raises(ValueError, match="unerwartetes Format"):
            pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max"}, "zielrolle": [eintrag]})
    with pytest.raises(ValueError, match="unerwartetes Format"):
        pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max"}, "zielrolle": "Ebene"})
    with pytest.raises(ValueError, match="unerwartetes Format"):
        pd.anwenden(UMFANGREICH, {"identitaet": {"name": 5}})
    with pytest.raises(ValueError, match="unerwartetes Format"):
        pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max"}, "kurzprofil": 5})


def test_laengen_einzeilig_hoechstens_300_freitext_hoechstens_5000(pd):
    ok = pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max", "aktuell": "x" * 300}})
    assert "- **Aktuell:** " + "x" * 300 + "\n" in ok
    with pytest.raises(ValueError, match="zu lang.*300"):
        pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max", "aktuell": "x" * 301}})
    with pytest.raises(ValueError, match="zu lang.*300"):
        pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max", "linkedin": "x" * 301}})   # neues Feld
    with pytest.raises(ValueError, match="zu lang.*300"):
        pd.anwenden(UMFANGREICH, {"identitaet": {"name": "M" * 301}})
    with pytest.raises(ValueError, match="zu lang.*300"):
        pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max"}, "zielrolle": [{"schluessel": "Ebene", "wert": "x" * 301}]})
    with pytest.raises(ValueError, match="zu lang.*300"):
        pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max", "email": "a@" + "x" * 300}})

    assert "x" * 5000 in pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max"}, "kurzprofil": "x" * 5000})
    for feld in ("kurzprofil", "rahmenbedingungen", "skill_gaps"):
        with pytest.raises(ValueError, match="zu lang.*5000"):
            pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max"}, feld: "x" * 5001})


def test_unveraenderte_lange_werte_aus_der_datei_blockieren_das_speichern_nicht(pd):
    t = "## Identität\n- **Name:** Max\n- **Aktuell:** " + "x" * 400 + "\n\n## Kurzprofil\n" + "y" * 6000 + "\n"
    assert pd.anwenden(t, pd.lesen_aus_text(t)) == t


@pytest.mark.parametrize("feld", ["kurzprofil", "rahmenbedingungen", "skill_gaps"])
def test_freitext_zeile_darf_nicht_mit_zwei_rauten_und_leerzeichen_beginnen(pd, feld):
    for text in ("## Neuer Abschnitt", "Erste Zeile\n## Empirie aus dem Bewerbungsverlauf\nDritte", "x\r\n## y"):
        with pytest.raises(ValueError, match="‚## ‘"):
            pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max"}, feld: text})
    # erlaubt: ### und ##ohne Leerzeichen, Raute im Text
    ok = pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max Mustermann"}, feld: "### Unter\n##Eng\nPunkt # eins\n x ## y"})
    d = pd.lesen_aus_text(ok)
    assert d[feld] == "### Unter\n##Eng\nPunkt # eins\n x ## y"
    assert d["unveraendert"] == pd.lesen_aus_text(UMFANGREICH)["unveraendert"]       # kein neuer Abschnitt entstanden


def test_abschnitts_injektion_ueber_einzeilige_felder_ist_unmoeglich(pd):
    neu = pd.anwenden(UMFANGREICH, {"identitaet": {"name": "Max Mustermann", "aktuell": "## Empirie", "linkedin": "## x"}})
    assert pd.lesen_aus_text(neu)["unveraendert"] == pd.lesen_aus_text(UMFANGREICH)["unveraendert"]
    assert "\n- **Aktuell:** ## Empirie\n" in neu


# ── Hinweise ─────────────────────────────────────────────────────────────────────────────────────
ORTSZEILE = "Die Ortszeile Ihrer Anschreiben entsteht aus ‚Straße Nr, PLZ Ort‘."


@pytest.mark.parametrize("anschrift,hinweis", [
    ("Musterweg 3, 12345 Musterstadt", False),
    ("Musterweg 3, 12345 Musterstadt (Rhein-Main)", False),
    ("Musterweg 3, 1010 Wien", False),
    ("Musterweg 3 12345 Musterstadt", True),           # ohne Komma
    ("Musterweg 3, Musterstadt", True),                # ohne Postleitzahl
    ("Musterstadt", True),
    ("Musterstadt (Rhein-Main)", True),
    ("Musterweg 3, 123456 Musterstadt", True),         # keine gültige Postleitzahl
    ("", False),                                       # leer: kein Hinweis
])
def test_hinweis_zur_anschrift(pd, anschrift, hinweis):
    d = pd.lesen_aus_text(f"## Identität\n- **Name:** Max\n- **Standort:** {anschrift}\n" if anschrift else "## Identität\n- **Name:** Max\n")
    assert pd.hinweise_fuer(d) == ([ORTSZEILE] if hinweis else [])


def test_hinweis_zur_e_mail_ohne_at_nur_aus_der_eingabe(pd, datei):
    """Beim erneuten Lesen landet ein Wert ohne `@` im Telefon -- der Hinweis kommt deshalb aus der Eingabe."""
    assert pd.hinweise_fuer({"identitaet": {"anschrift": "", "email": "max.example.com"}}) == [
        "Die E-Mail-Adresse enthält kein ‚@‘. Bitte prüfen Sie die Schreibweise."]
    daten = pd.lesen()
    daten["identitaet"].update(name="Max Mustermann", email="max.example.com", anschrift="Musterstadt")

    ergebnis = pd.schreiben(daten, "")

    assert ergebnis["hinweise"] == [ORTSZEILE, "Die E-Mail-Adresse enthält kein ‚@‘. Bitte prüfen Sie die Schreibweise."]
    gelesen = pd.lesen()
    assert gelesen["identitaet"]["email"] == "" and gelesen["identitaet"]["telefon"] == "max.example.com"
    assert gelesen["hinweise"] == [ORTSZEILE]


# ── Datei: stand, Papierkorb, atomar ─────────────────────────────────────────────────────────────
def test_stand_ist_sha256_der_bytes_und_leer_ohne_datei(pd, datei):
    assert pd.lesen()["stand"] == "" and pd.stand_von(None) == ""
    _schreibe(datei, UMFANGREICH_CRLF)
    erwartet = __import__("hashlib").sha256(UMFANGREICH_CRLF.encode("utf-8")).hexdigest()
    assert pd.lesen()["stand"] == erwartet == pd.stand_von(UMFANGREICH_CRLF.encode("utf-8"))
    # schon ein einzelnes Byte ändert den Stand (CRLF → LF)
    assert pd.stand_von(UMFANGREICH.encode("utf-8")) != erwartet


def test_veralteter_stand_wird_abgelehnt_und_die_datei_bleibt(pd, datei):
    _schreibe(datei, UMFANGREICH)
    daten = pd.lesen()
    # ein Skill ersetzt inzwischen die Empirie
    datei.write_bytes(UMFANGREICH.replace("Absagen: 3 von 10", "Absagen: 4 von 10").encode("utf-8"))
    stand_nachher = datei.read_bytes()

    with pytest.raises(pd.StandVeraltet) as fehler:
        pd.schreiben(_mit(daten, identitaet={"name": "Erika Musterfrau"}), daten["stand"])

    assert str(fehler.value) == ("Die Profil-Datei wurde inzwischen geändert. Bitte laden Sie die Karte neu und "
                                 "tragen Sie Ihre Änderung noch einmal ein.")
    assert datei.read_bytes() == stand_nachher
    assert _papierkorb_dateien(pd) == []
    assert not isinstance(fehler.value, ValueError)


def test_stand_leer_bei_vorhandener_datei_und_stand_bei_fehlender_datei_sind_veraltet(pd, datei):
    with pytest.raises(pd.StandVeraltet):
        pd.schreiben(VOLL, "abc")                                   # Datei fehlt, aber Stand behauptet eine
    assert not datei.exists()
    _schreibe(datei, UMFANGREICH)
    with pytest.raises(pd.StandVeraltet):
        pd.schreiben(VOLL, "")                                      # Datei existiert, Stand leer
    assert datei.read_bytes() == UMFANGREICH.encode("utf-8")


def test_stand_wird_vor_der_eingabepruefung_geprueft(pd, datei):
    _schreibe(datei, UMFANGREICH)
    with pytest.raises(pd.StandVeraltet):
        pd.schreiben({"identitaet": {"name": ""}}, "alt")


def test_ungueltige_eingabe_aendert_nichts(pd, datei):
    _schreibe(datei, UMFANGREICH)
    stand = pd.lesen()["stand"]
    with pytest.raises(ValueError):
        pd.schreiben({"identitaet": {"name": ""}}, stand)
    assert datei.read_bytes() == UMFANGREICH.encode("utf-8")
    assert _papierkorb_dateien(pd) == []


def test_papierkorb_kopie_mit_dem_alten_inhalt(pd, datei):
    _schreibe(datei, UMFANGREICH_CRLF)
    daten = pd.lesen()

    ergebnis = pd.schreiben(_mit(daten, identitaet={"name": "Anna Beispiel"}), daten["stand"])

    kopien = _papierkorb_dateien(pd)
    assert len(kopien) == 1
    assert re.fullmatch(r"\d{8}_profil\.md", kopien[0].name)
    assert kopien[0].read_bytes() == UMFANGREICH_CRLF.encode("utf-8")           # byte-gleich, auch CRLF
    assert ergebnis["geschrieben"] is True and ergebnis["papierkorb"] == f"data/papierkorb/{kopien[0].name}"
    assert b"Anna Beispiel" in datei.read_bytes() and b"Anna Beispiel" not in kopien[0].read_bytes()


def test_papierkorb_kopie_ohne_vorhandene_datei_entfaellt(pd):
    ergebnis = pd.schreiben({"identitaet": {"name": "Max Mustermann"}}, "")
    assert ergebnis["papierkorb"] is None and _papierkorb_dateien(pd) == []


def test_zweites_speichern_am_selben_tag_ueberschreibt_keine_papierkorb_kopie(pd, datei):
    _schreibe(datei, UMFANGREICH)
    namen = []
    for neuer_name in ("Anna Beispiel", "Karl Muster", "Lena Probe"):
        daten = pd.lesen()
        namen.append(pd.schreiben(_mit(daten, identitaet={"name": neuer_name}), daten["stand"])["papierkorb"])
    assert len(set(namen)) == 3 and all(namen)
    kopien = _papierkorb_dateien(pd)
    assert [k.name for k in kopien][1:] == [kopien[0].stem + "_2.md", kopien[0].stem + "_3.md"]
    assert b"Max Mustermann" in kopien[0].read_bytes() and b"Anna Beispiel" in kopien[1].read_bytes()
    assert b"Karl Muster" in kopien[2].read_bytes() and b"Lena Probe" not in kopien[2].read_bytes()


def test_scheitert_die_papierkorb_kopie_bleibt_die_datei_unveraendert(pd, datei, monkeypatch):
    _schreibe(datei, UMFANGREICH)
    daten = pd.lesen()

    def kaputt(*a, **k):
        raise OSError("Platte voll")
    monkeypatch.setattr(pd.shutil, "copy2", kaputt)

    with pytest.raises(OSError, match="Platte voll"):
        pd.schreiben(_mit(daten, identitaet={"name": "Erika Musterfrau"}), daten["stand"])
    assert datei.read_bytes() == UMFANGREICH.encode("utf-8")


def test_atomar_fehler_beim_ersetzen_laesst_die_alte_datei_stehen(pd, datei, monkeypatch):
    _schreibe(datei, UMFANGREICH)
    daten = pd.lesen()
    echtes_replace = os.replace

    def kaputt(quelle, ziel):
        if str(ziel) == str(datei):
            raise OSError("Ersetzen verweigert")
        return echtes_replace(quelle, ziel)
    monkeypatch.setattr(os, "replace", kaputt)

    with pytest.raises(OSError, match="Ersetzen verweigert"):
        pd.schreiben(_mit(daten, identitaet={"name": "Erika Musterfrau"}), daten["stand"])

    assert datei.read_bytes() == UMFANGREICH.encode("utf-8")
    assert sorted(p.name for p in datei.parent.iterdir()) == ["profil.md"]       # keine Temp-Datei übrig


def test_atomar_schreibt_ueber_temp_datei_im_selben_ordner(pd, datei, monkeypatch):
    _schreibe(datei, UMFANGREICH)
    daten = pd.lesen()
    gesehen = []
    echtes_replace = os.replace

    def merke(quelle, ziel):
        gesehen.append((os.path.dirname(quelle), str(ziel)))
        return echtes_replace(quelle, ziel)
    monkeypatch.setattr(os, "replace", merke)

    pd.schreiben(_mit(daten, identitaet={"name": "Erika Musterfrau"}), daten["stand"])

    assert gesehen == [(str(datei.parent), str(datei))]
    assert sorted(p.name for p in datei.parent.iterdir()) == ["profil.md"]


@pytest.mark.skipif(os.name == "nt", reason="Dateirechte sind unter Windows nicht aussagekräftig")
def test_zugriffsrechte_der_alten_datei_bleiben(pd, datei):
    _schreibe(datei, UMFANGREICH)
    datei.chmod(0o640)
    daten = pd.lesen()
    pd.schreiben(_mit(daten, identitaet={"name": "Erika Musterfrau"}), daten["stand"])
    assert stat.S_IMODE(datei.stat().st_mode) == 0o640


def test_neuer_config_ordner_wird_angelegt(pd, datei):
    assert not datei.parent.exists()
    pd.schreiben({"identitaet": {"name": "Max Mustermann"}}, "")
    assert datei.is_file()


def test_geschriebene_datei_ist_utf8_und_bytegleich_zum_berechneten_text(pd, datei):
    _schreibe(datei, UMFANGREICH_CRLF)
    daten = pd.lesen()
    daten["kurzprofil"] = "Äußerst überzeugend – mit Umlauten."
    erwartet = pd.anwenden(UMFANGREICH_CRLF, daten).encode("utf-8")

    pd.schreiben(daten, daten["stand"])

    assert datei.read_bytes() == erwartet
    assert b"\r\n" in erwartet and b"\n" not in erwartet.replace(b"\r\n", b"")


def test_kein_test_zeigt_auf_die_echte_installation(pd, datei):
    from pipeline import user_profile
    echt = user_profile.PROJECT_ROOT.resolve()
    assert echt not in datei.resolve().parents
    assert echt not in pd._papierkorb_ordner().resolve().parents
    assert datei == user_profile._PROFIL_MD and pd._pfad() == datei


# ── Abnahme P2-69: Titelzeile folgt dem Namen ────────────────────────────────────────────────────
def _nur_name(pd, text: str, name: str) -> str:
    daten = pd.lesen_aus_text(text)
    daten["identitaet"]["name"] = name
    return pd.anwenden(text, daten)


def test_titelzeile_folgt_einer_namensaenderung(pd):
    alt = "# Kandidatenprofil: Max Mustermann\n\n## Identität\n- **Name:** Max Mustermann\n\n## Kurzprofil\nText.\n"
    neu = _nur_name(pd, alt, "Erika Musterfrau")
    assert neu == alt.replace("Max Mustermann", "Erika Musterfrau")


def test_titelzeile_mit_crlf_behaelt_ihr_zeilenende(pd):
    alt = "# Kandidatenprofil: Max Mustermann\r\n\r\n## Identität\r\n- **Name:** Max Mustermann\r\n"
    assert _nur_name(pd, alt, "Erika Musterfrau") == alt.replace("Max Mustermann", "Erika Musterfrau")


def test_eigener_titel_bleibt_bei_namensaenderung_unveraendert(pd):
    alt = "# Mein Profil (Max Mustermann)\n\n## Identität\n- **Name:** Max Mustermann\n"
    neu = _nur_name(pd, alt, "Erika Musterfrau")
    assert neu.splitlines()[0] == "# Mein Profil (Max Mustermann)"
    assert "- **Name:** Erika Musterfrau" in neu


def test_titel_mit_anderem_namen_bleibt_unveraendert(pd):
    """Nur der Titel mit dem BISHERIGEN Namen zieht mit, kein fremder."""
    alt = "# Kandidatenprofil: Jemand Anderes\n\n## Identität\n- **Name:** Max Mustermann\n"
    assert _nur_name(pd, alt, "Erika Musterfrau").splitlines()[0] == "# Kandidatenprofil: Jemand Anderes"


def test_ohne_namensaenderung_bleibt_der_titel_bytegleich(pd):
    alt = "# Kandidatenprofil: Max Mustermann   \n\n## Identität\n- **Name:** Max Mustermann\n- **Aktuell:** a\n"
    daten = pd.lesen_aus_text(alt)
    daten["identitaet"]["aktuell"] = "b"
    assert pd.anwenden(alt, daten).splitlines(keepends=True)[0] == "# Kandidatenprofil: Max Mustermann   \n"
