"""P2-72 (Vertrag Q) — `pipeline/design.py`: das Design des BMS aus einer Quelle.

Deckt ab:
  1. Die Vorgabe (`assets/design/standard.json`) entspricht einer im Test festgeschriebenen Tabelle
     der heutigen Werte. Wer die Vorgabe ändert, ändert bewusst auch diese Tabelle. Dazu: Die
     Vorgabe wird trotz Kontrast 2,5:1 (Weiß auf Cyan, Leitentscheidung 3) nie abgelehnt, die zwei
     Icons sind die heutigen Dateien, eine beschädigte Vorgabe ist ein `DesignFehler`.
  2. Überschreibung Rolle für Rolle (alle 13 Farben, Schriften, Name, Produktname, Icons).
  3. Jede Ablehnung ergibt die Vorgabe und eine Warnung, nie eine Ausnahme: ungültige Farbe, kaputtes
     JSON, falsches Format, unbekannte Felder, Datei statt Objekt, unbrauchbarer Name, Schrift
     außerhalb der Liste, Icon (zu groß, nicht quadratisch, kein PNG, Pfadanteil im Namen, ...).
  4. Paarregel und Kontrast samt Grenzfall (#767676 auf Weiß: 4,54:1, #777777: 4,48:1), halbe Paare,
     der gemeinsame `text` von `flaeche` und `karte`.
  5. Zwischenspeicher bemerkt eine geänderte Datei (Größe oder Änderungszeit, auch ein Icon).
  6. CSS, Kanäle und Stand-Kennzeichen; `zeigen` gibt das Design ohne Ausnahme aus.

Pfade nur unter `tmp_path`: Die Vorgabe wird in einen Wegwerf-Ordner kopiert, die Überschreibung liegt
unter einem Wegwerf-Datenordner. Nie `data/` des Projekts. App-Module nur funktionslokal importieren
(conftest.py); `pipeline.design` selbst braucht keine App, folgt der Regel aber trotzdem.
"""
import hashlib
import json
import logging
import os
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJEKT_DIR = BACKEND_DIR.parent
ASSETS_DESIGN = PROJEKT_DIR / "assets" / "design"

# Die heutigen Werte (Leitentscheidung 1, geprüft gegen tailwind.config.js und das Berichts-Thema).
HEUTIGE_FARBEN = {
    "marke": "#0B1F3A", "auf_marke": "#DCE4EE",
    "aktion": "#00B4D8", "aktion_hover": "#0096C7", "auf_aktion": "#FFFFFF",
    "stahl": "#BFC7D5", "flaeche": "#F4F7FB", "karte": "#FFFFFF", "rahmen": "#DCE4EE",
    "spur": "#EAF0F6", "text": "#0B1F3A", "text_gedaempft": "#5F6F84", "trenner": "#2A3F5F",
}
HEUTIGE_SCHRIFTEN = {"ueberschrift": "Montserrat", "text": "Inter"}
HEUTIGER_PRODUKTNAME = "Bewerbungs-Management-System"
HEUTIGE_STAPEL = {
    "ueberschrift": "'Montserrat', 'Poppins', Arial, sans-serif",
    "text": "'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif",
}
# SHA-256 der heutigen Icons (`favicon-32.png` und `apple-touch-icon.png` unter frontend/public).
# Paket O entfernt die Originale; dann gilt weiter dieser Fingerabdruck.
HEUTIGE_ICON_SHA256 = {
    "32": "ee30554183c03b4c1cff8b01b7d458ef6b1f2299e7db0854f22616d92b2dc40b",
    "180": "fc4b1d615defccb2ce8b53eb52d7b18bd3e65253f3fc2279d9186d6da21e2d0d",
}

# Eine gültige Farbe je Rolle, die sich von der Vorgabe unterscheidet UND als einzige Änderung den
# Kontrast gegen die Vorgabe-Hälfte des Paares besteht.
ANDERE_FARBE = {
    "marke": "#1A2B4C", "auf_marke": "#FFFFFF",
    "aktion": "#005F73", "aktion_hover": "#FF6600", "auf_aktion": "#001F2D",
    "stahl": "#889988", "flaeche": "#FFFFFF", "karte": "#FAFAFA", "rahmen": "#C0C0C0",
    "spur": "#E0E0E0", "text": "#000000", "text_gedaempft": "#666666", "trenner": "#334455",
}


# ── Hilfen ────────────────────────────────────────────────────────────────────────────────────
def png(breite=32, hoehe=None, mit_bild=True, laenge=None):
    """Ein echtes, kleines PNG (Farbe 8 Bit RGB). `mit_bild=False` lässt die Bilddaten weg (nur
    Kopf und Ende: für große Kantenlängen ohne Speicherverbrauch). `laenge`: die Datei wird mit
    einem Textblock auf genau diese Länge aufgefüllt."""
    hoehe = breite if hoehe is None else hoehe

    def block(typ, daten):
        return struct.pack(">I", len(daten)) + typ + daten + struct.pack(">I", zlib.crc32(typ + daten))

    kopf = b"\x89PNG\r\n\x1a\n" + block(b"IHDR", struct.pack(">IIBBBBB", breite, hoehe, 8, 2, 0, 0, 0))
    bild = block(b"IDAT", zlib.compress((b"\x00" + b"\x10\x20\x30" * breite) * hoehe)) if mit_bild else b""
    ende = block(b"IEND", b"")
    ergebnis = kopf + bild + ende
    if laenge is not None:
        fehlt = laenge - len(ergebnis) - 12
        assert fehlt >= 0
        ergebnis = kopf + bild + block(b"tEXt", b"x" * fehlt) + ende
        assert len(ergebnis) == laenge
    return ergebnis


@pytest.fixture()
def design():
    """Das Modul, mit leerem Zwischenspeicher davor und danach."""
    from pipeline import design as modul

    modul.zwischenspeicher_leeren()
    yield modul
    modul.zwischenspeicher_leeren()


class Werkstatt:
    """Eine Wegwerf-Installation: Vorgabe (Kopie von `assets/design`) und Überschreibung."""

    def __init__(self, tmp_path, design):
        self.design = design
        self.vorgabe_ordner = tmp_path / "programm" / "assets" / "design"
        shutil.copytree(ASSETS_DESIGN, self.vorgabe_ordner)
        self.vorgabe = self.vorgabe_ordner / "standard.json"
        self.ordner = tmp_path / "daten" / "design"
        self.datei = self.ordner / "design.json"

    def schreibe(self, inhalt):
        """`dict` als JSON, `str`/`bytes` unverändert."""
        self.ordner.mkdir(parents=True, exist_ok=True)
        if isinstance(inhalt, dict):
            inhalt = json.dumps(inhalt)
        if isinstance(inhalt, str):
            inhalt = inhalt.encode("utf-8")
        self.datei.write_bytes(inhalt)

    def ueberschreibe(self, **teile):
        self.schreibe({"format": 1, **teile})

    def icon(self, name, daten):
        self.ordner.mkdir(parents=True, exist_ok=True)
        (self.ordner / name).write_bytes(daten)

    def laden(self):
        return self.design.laden(self.vorgabe, self.datei)


@pytest.fixture()
def w(tmp_path, design):
    return Werkstatt(tmp_path, design)


def ist_vorgabe(d, ausser=()):
    """Alle Werte außer den genannten Rollen sind die der Vorgabe."""
    farben = {r: v for r, v in HEUTIGE_FARBEN.items() if r not in ausser}
    assert {r: d.farben[r] for r in farben} == farben
    if "schriften" not in ausser:
        assert dict(d.schriften) == HEUTIGE_SCHRIFTEN
    if "produktname" not in ausser:
        assert d.produktname == HEUTIGER_PRODUKTNAME


# ── 1. Die Vorgabe ────────────────────────────────────────────────────────────────────────────
def test_die_vorgabe_entspricht_der_tabelle_der_heutigen_werte(design):
    d = design.vorgabe()

    assert dict(d.farben) == HEUTIGE_FARBEN
    assert list(d.farben) == list(HEUTIGE_FARBEN)          # Reihenfolge der Rollen
    assert dict(d.schriften) == HEUTIGE_SCHRIFTEN
    assert d.produktname == HEUTIGER_PRODUKTNAME
    assert d.name == "Standard"
    assert d.quelle == "vorgabe"
    assert d.warnungen == ()
    assert sorted(d.icons) == ["180", "32"]


def test_die_vorgabedatei_hat_genau_das_format_aus_vertrag_q():
    roh = (ASSETS_DESIGN / "standard.json").read_bytes()
    daten = json.loads(roh.decode("utf-8"))

    assert b"\r" not in roh and roh.endswith(b"\n")
    assert list(daten) == ["format", "name", "farben", "schriften", "produktname", "icon"]
    assert daten["format"] == 1
    assert daten["farben"] == HEUTIGE_FARBEN
    assert daten["schriften"] == HEUTIGE_SCHRIFTEN
    assert daten["produktname"] == HEUTIGER_PRODUKTNAME
    assert daten["icon"] == {"32": "icon-32.png", "180": "icon-180.png"}


def test_die_vorgabe_hat_dreizehn_farbrollen_und_vier_paare(design):
    assert design.FARBROLLEN == tuple(HEUTIGE_FARBEN)
    assert len(design.FARBROLLEN) == 13
    assert design.FARBPAARE == (("marke", "auf_marke"), ("aktion", "auf_aktion"),
                                ("flaeche", "text"), ("karte", "text"))
    assert design.KONTRAST_MIN == 4.5


def test_die_vorgabe_wird_trotz_kontrast_2_5_zu_1_nicht_abgelehnt(design):
    """Weiß auf Cyan ist gewollt (Leitentscheidung 3). Die Kontrastregel gilt nur für Werte der
    Überschreibung; die Vorgabe wird nie daran gemessen."""
    d = design.vorgabe()

    verhaeltnis = design.kontrast(d.farben["aktion"], d.farben["auf_aktion"])
    assert 2.4 < verhaeltnis < 2.6 < design.KONTRAST_MIN
    assert d.farben["aktion"] == "#00B4D8" and d.farben["auf_aktion"] == "#FFFFFF"
    assert d.warnungen == ()
    assert d.quelle == "vorgabe"


def test_die_icons_der_vorgabe_sind_die_heutigen_dateien():
    for groesse, name, original in (("32", "icon-32.png", "favicon-32.png"),
                                    ("180", "icon-180.png", "apple-touch-icon.png")):
        inhalt = (ASSETS_DESIGN / name).read_bytes()
        assert hashlib.sha256(inhalt).hexdigest() == HEUTIGE_ICON_SHA256[groesse]
        alt = PROJEKT_DIR / "frontend" / "public" / original
        if alt.exists():                 # die Kopien unter frontend/public sind mit P2-72 entfernt
            assert inhalt == alt.read_bytes(), name


def test_die_icons_der_vorgabe_werden_geliefert(design):
    d = design.vorgabe()

    assert d.icon(32) == ASSETS_DESIGN / "icon-32.png" and d.icon("32") == d.icon(32)
    assert d.icon(180) == ASSETS_DESIGN / "icon-180.png"
    assert d.icon(64) is None
    assert hashlib.sha256(d.icon_bytes(32)).hexdigest() == HEUTIGE_ICON_SHA256["32"]
    assert hashlib.sha256(d.icon_bytes("180")).hexdigest() == HEUTIGE_ICON_SHA256["180"]
    assert d.icon_bytes(64) is None


def test_das_design_ist_unveraenderlich(design):
    d = design.vorgabe()

    with pytest.raises(Exception):
        d.produktname = "x"
    with pytest.raises(TypeError):
        d.farben["marke"] = "#000000"
    with pytest.raises(TypeError):
        d.schriften["text"] = "System"
    with pytest.raises(TypeError):
        d.icons["32"] = Path("x")
    assert isinstance(d.warnungen, tuple)
    assert hash(d) == hash(design.vorgabe())


@pytest.mark.parametrize("fall", ["fehlt", "kaputt", "kein_objekt", "format", "rolle_fehlt",
                                  "farbe_ungueltig", "icon_fehlt", "unbekanntes_feld"])
def test_eine_beschaedigte_vorgabe_ist_ein_designfehler(w, design, fall):
    """Die Vorgabe ist Teil des Programms; ist sie kaputt, ist die Installation beschädigt. Das ist
    der einzige Fall, in dem `laden()` wirft (und es gibt keinen eingebauten Notfall-Satz Farben)."""
    daten = json.loads(w.vorgabe.read_text(encoding="utf-8"))
    if fall == "fehlt":
        w.vorgabe.unlink()
    elif fall == "kaputt":
        w.vorgabe.write_text("{nicht json", encoding="utf-8")
    elif fall == "kein_objekt":
        w.vorgabe.write_text("[]", encoding="utf-8")
    else:
        if fall == "format":
            daten["format"] = 2
        elif fall == "rolle_fehlt":
            del daten["farben"]["spur"]
        elif fall == "farbe_ungueltig":
            daten["farben"]["marke"] = "dunkelblau"
        elif fall == "icon_fehlt":
            (w.vorgabe_ordner / "icon-32.png").unlink()
        elif fall == "unbekanntes_feld":
            daten["extra"] = 1
        w.vorgabe.write_text(json.dumps(daten), encoding="utf-8")

    with pytest.raises(design.DesignFehler):
        w.laden()
    with pytest.raises(design.DesignFehler):
        design.vorgabe(w.vorgabe)


def test_die_vorgabe_wird_nicht_am_kontrast_gemessen_auch_nicht_in_einer_kopie(w, design):
    """Ein Nutzer kopiert `standard.json` als Anfang einer Überschreibung: Das Paar aktion/auf_aktion hat
    2,5:1, ist aber wörtlich die Vorgabe und bekommt keine Warnung."""
    w.ordner.mkdir(parents=True)
    for datei in w.vorgabe_ordner.iterdir():        # standard.json und die zwei Icons daneben
        shutil.copy(datei, w.ordner / ("design.json" if datei.name == "standard.json" else datei.name))

    d = w.laden()

    assert d.warnungen == ()
    assert dict(d.farben) == HEUTIGE_FARBEN
    assert d.quelle == "ueberschreibung"        # die Datei wurde gelesen und gilt, Wert für Wert
    assert d.icon(32) == w.ordner / "icon-32.png"


def test_eine_kopie_von_standard_json_ohne_die_icons_meldet_nur_die_fehlenden_icons(w):
    w.ordner.mkdir(parents=True)
    shutil.copy(w.vorgabe, w.datei)

    d = w.laden()

    assert dict(d.farben) == HEUTIGE_FARBEN and d.icon(32) == w.vorgabe_ordner / "icon-32.png"
    assert len(d.warnungen) == 2 and all("fehlt" in satz for satz in d.warnungen)
    assert not any("aktion" in satz for satz in d.warnungen)       # kein Kontrast-Alarm


# ── Kontrast ──────────────────────────────────────────────────────────────────────────────────
def test_kontrast_schwarz_weiss_ist_21_und_gleiche_farben_sind_1(design):
    assert design.kontrast("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert design.kontrast("#FFFFFF", "#000000") == pytest.approx(21.0)
    assert design.kontrast("#336699", "#336699") == pytest.approx(1.0)


def test_kontrast_grenzfall_767676_besteht_777777_nicht(design):
    """Das bekannte Paar der WCAG-Beispiele: Grau auf Weiß, 4,54:1 gegen 4,48:1."""
    assert design.kontrast("#767676", "#FFFFFF") >= 4.5 > design.kontrast("#777777", "#FFFFFF")
    assert design.kontrast("#767676", "#FFFFFF") == pytest.approx(4.54, abs=0.01)
    assert design.kontrast("#777777", "#FFFFFF") == pytest.approx(4.48, abs=0.01)


def test_kanaele(design):
    assert design.kanaele("#0B1F3A") == "11 31 58"
    assert design.kanaele("#FFFFFF") == "255 255 255"
    assert design.kanaele("#000000") == "0 0 0"


@pytest.mark.parametrize("wert, ok", [
    ("#000000", True), ("#ffffff", True), ("#0b1F3a", True), ("#00B4D8", True),
    ("000000", False), ("#FFF", False), ("#FFFFFFF", False), ("#GGGGGG", False), ("#12345", False),
    ("#0B1F3A\n", False), (" #0B1F3A", False), ("#0B1F3A ", False), ("rgb(0,0,0)", False),
    ("red", False), ("", False), ("#", False), ("＃000000", False), ("#٠٠٠٠٠٠", False),
    (None, False), (123, False), (["#000000"], False), (True, False),
])
def test_ist_farbe(design, wert, ok):
    assert design.ist_farbe(wert) is ok


# ── 2. Überschreibung Rolle für Rolle ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("rolle", list(HEUTIGE_FARBEN))
def test_ueberschreibung_einer_farbrolle(w, rolle):
    w.ueberschreibe(farben={rolle: ANDERE_FARBE[rolle]})

    d = w.laden()

    assert d.farben[rolle] == ANDERE_FARBE[rolle] != HEUTIGE_FARBEN[rolle]
    ist_vorgabe(d, ausser=(rolle,))
    assert d.warnungen == ()
    assert d.quelle == "ueberschreibung"


def test_farben_werden_intern_gross_geschrieben(w):
    w.ueberschreibe(farben={"trenner": "#aabbcc", "spur": "#0f0F0f"})

    d = w.laden()

    assert d.farben["trenner"] == "#AABBCC" and d.farben["spur"] == "#0F0F0F"
    assert d.warnungen == ()


def test_alle_dreizehn_farben_zugleich(w):
    alle = {**ANDERE_FARBE, "auf_aktion": "#FFFFFF"}      # dunkle Aktionsfarbe mit heller Schrift
    w.ueberschreibe(farben=alle)

    d = w.laden()

    assert dict(d.farben) == alle
    assert d.warnungen == ()


def test_ueberschreibung_der_schriften(w):
    w.ueberschreibe(schriften={"ueberschrift": "Inter", "text": "System"})

    d = w.laden()

    assert dict(d.schriften) == {"ueberschrift": "Inter", "text": "System"}
    assert d.warnungen == ()


def test_eine_schrift_allein(w):
    w.ueberschreibe(schriften={"text": "Montserrat"})

    d = w.laden()

    assert dict(d.schriften) == {"ueberschrift": "Montserrat", "text": "Montserrat"}


@pytest.mark.parametrize("schrift", ["Comic Sans MS", "inter", "INTER", "Inter, serif", "", None, 7,
                                     ["Inter"], "Inter\n", "'Inter'; } body { display:none"])
def test_eine_schrift_ausserhalb_der_liste_ergibt_die_vorgabe_und_eine_warnung(w, schrift):
    w.ueberschreibe(schriften={"ueberschrift": schrift, "text": "System"})

    d = w.laden()

    assert d.schriften["ueberschrift"] == "Montserrat"
    assert d.schriften["text"] == "System"          # die gültige Rolle daneben gilt trotzdem
    assert len(d.warnungen) == 1 and "ueberschrift" in d.warnungen[0]


def test_der_name_des_designs_gilt_der_produktname_bleibt(w):
    """Vorgabe vom 14.10.2026: Der Produktname bleibt, auch mit einem anderen Design. Der Name des
    Designs selbst (nur Auskunft) darf sich ändern."""
    w.ueberschreibe(name="Rot und Gold", produktname="Beispiel Karriere-Plattform")

    d = w.laden()

    assert d.name == "Rot und Gold"
    assert d.produktname == HEUTIGER_PRODUKTNAME
    assert len(d.warnungen) == 1 and "Produktname ist fest" in d.warnungen[0]
    assert d.quelle == "ueberschreibung"            # der Name des Designs gilt
    ist_vorgabe(d)


@pytest.mark.parametrize("name", ["abc", "a" * 40, "Müller & Söhne – Karriere", "Zwei  Leerzeichen",
                                  "  Mein Produkt \t", HEUTIGER_PRODUKTNAME + " "])
def test_auch_ein_brauchbarer_produktname_der_ueberschreibung_gilt_nicht(w, name):
    w.ueberschreibe(produktname=name)

    d = w.laden()

    assert d.produktname == HEUTIGER_PRODUKTNAME
    assert len(d.warnungen) == 1 and "Produktname ist fest" in d.warnungen[0]
    assert d.quelle == "vorgabe"


def test_derselbe_produktname_wie_in_der_vorgabe_bleibt_ohne_warnung(w):
    """Eine unveränderte Kopie von `standard.json` als Überschreibung warnt nicht (wie bei den Farben)."""
    w.ueberschreibe(produktname=HEUTIGER_PRODUKTNAME, farben={"spur": "#101010"})

    d = w.laden()

    assert d.produktname == HEUTIGER_PRODUKTNAME and d.warnungen == ()
    assert d.farben["spur"] == "#101010"


@pytest.mark.parametrize("name", [
    "", "ab", "a" * 41, "   ", "Zeile eins\nZeile zwei", "Zeile\r\nzwei", "Tab\there", "\x00Name",
    "Name\x1b[31m", "Zeilentrenner\u2028Name", "Absatz\u2029Name", "Rechts\u202eLinks", "Null\u200bBreite",
    "Name\x7f", 5, None, ["Name"], {"a": 1}, True,
])
def test_ein_unbrauchbarer_produktname_ergibt_die_vorgabe_und_eine_warnung(w, name):
    """Wie jeder Produktname der Überschreibung: Vorgabe und genau eine Warnung, auch bei Steuerzeichen
    maskiert."""
    w.ueberschreibe(produktname=name)

    d = w.laden()

    assert d.produktname == HEUTIGER_PRODUKTNAME
    assert len(d.warnungen) == 1 and "Produktname" in d.warnungen[0]
    assert "\n" not in d.warnungen[0] and "\x1b" not in d.warnungen[0]    # maskiert für das Log
    assert d.quelle == "vorgabe"


def test_ein_unbrauchbarer_designname_ergibt_die_vorgabe_und_eine_warnung(w):
    w.ueberschreibe(name="zwei\nZeilen")

    d = w.laden()

    assert d.name == "Standard" and len(d.warnungen) == 1 and "Name" in d.warnungen[0]


# ── 3. Ablehnungen: Vorgabe und Warnung, nie eine Ausnahme ────────────────────────────────────
@pytest.mark.parametrize("wert", [
    "red", "#FFF", "#12345G", "#1234567", "0B1F3A", "rgb(1,2,3)", "", "#", " #0B1F3A", "#0B1F3A\n",
    123, None, True, ["#000000"], {"r": 0},
])
def test_eine_ungueltige_farbe_ergibt_die_vorgabe_und_eine_warnung(w, wert):
    w.ueberschreibe(farben={"spur": wert, "trenner": "#112233"})

    d = w.laden()

    assert d.farben["spur"] == HEUTIGE_FARBEN["spur"]
    assert d.farben["trenner"] == "#112233"           # die gültige Rolle daneben gilt trotzdem
    assert len(d.warnungen) == 1 and "spur" in d.warnungen[0]
    assert d.quelle == "ueberschreibung"


KAPUTTE_DATEIEN = [
    b"", b"{nicht json", b'{"format": 1,', b"[]", b"[1, 2]", b"42", b'"text"', b"null", b"true",
    b"\xff\xfe\x00{", b"\x89PNG\r\n\x1a\n\x00\x00", b"[" * 5000, b"{" * 5000, b"\x00" * 100,
]


@pytest.mark.parametrize("inhalt", KAPUTTE_DATEIEN)
def test_eine_kaputte_datei_ergibt_die_vorgabe_und_eine_warnung(w, inhalt):
    w.schreibe(inhalt)

    d = w.laden()

    assert dict(d.farben) == HEUTIGE_FARBEN and d.quelle == "vorgabe"
    ist_vorgabe(d)
    assert len(d.warnungen) == 1 and d.warnungen[0].startswith("Überschreibung")


def test_eine_datei_mit_bom_gilt(w):
    w.schreibe(b"\xef\xbb\xbf" + json.dumps({"format": 1, "farben": {"spur": "#101010"}}).encode())

    d = w.laden()

    assert d.farben["spur"] == "#101010" and d.warnungen == ()


def test_eine_zu_grosse_datei_wird_nicht_gelesen(w):
    w.schreibe(json.dumps({"format": 1, "name": "x" * 70_000}))

    d = w.laden()

    assert d.quelle == "vorgabe" and len(d.warnungen) == 1 and "größer" in d.warnungen[0]


def test_ein_verzeichnis_statt_einer_datei_ist_eine_warnung_und_kein_fehler(w):
    w.datei.mkdir(parents=True)

    d = w.laden()

    assert d.quelle == "vorgabe" and len(d.warnungen) == 1
    ist_vorgabe(d)


def test_ohne_ueberschreibung_gibt_es_keine_warnung(w):
    assert not w.datei.exists()

    d = w.laden()

    assert d.quelle == "vorgabe" and d.warnungen == ()
    ist_vorgabe(d)


@pytest.mark.parametrize("format_", [2, 0, -1, "1", True, False, 1.0, 1.5, None, [1], {"v": 1}])
def test_ein_falsches_format_ergibt_die_vorgabe_und_eine_warnung(w, format_):
    w.schreibe({"format": format_, "farben": {"spur": "#101010"}, "produktname": "Anders"})

    d = w.laden()

    assert d.farben["spur"] == HEUTIGE_FARBEN["spur"] and d.produktname == HEUTIGER_PRODUKTNAME
    assert d.quelle == "vorgabe"
    assert len(d.warnungen) == 1 and "Format" in d.warnungen[0]


def test_ohne_format_gilt_die_datei_nicht(w):
    w.schreibe({"farben": {"spur": "#101010"}})

    d = w.laden()

    assert d.farben["spur"] == HEUTIGE_FARBEN["spur"] and len(d.warnungen) == 1


def test_unbekannte_felder_werden_ignoriert_mit_warnung(w):
    w.ueberschreibe(zusatz=1, farben={"neon": "#00FF00", "spur": "#101010"},
                    schriften={"fett": "Inter", "text": "System"}, icon={"64": "x.png"})

    d = w.laden()

    assert d.farben["spur"] == "#101010"            # Bekanntes daneben gilt
    assert d.schriften["text"] == "System"
    assert len(d.warnungen) == 4
    for stichwort in ("zusatz", "neon", "fett", "64"):
        assert any(stichwort in satz for satz in d.warnungen), stichwort
    assert "neon" not in d.farben


@pytest.mark.parametrize("feld", ["farben", "schriften", "icon"])
@pytest.mark.parametrize("wert", [[], "text", 5, None])
def test_ein_unterobjekt_das_keins_ist_ergibt_die_vorgabe_und_eine_warnung(w, feld, wert):
    w.ueberschreibe(**{feld: wert}, name="Anderer Name")

    d = w.laden()

    assert d.name == "Anderer Name"                 # der Rest der Datei gilt
    ist_vorgabe(d)
    assert len(d.warnungen) == 1 and feld in d.warnungen[0]


def test_ein_leeres_objekt_aendert_nichts(w):
    w.ueberschreibe()

    d = w.laden()

    assert d.warnungen == () and dict(d.farben) == HEUTIGE_FARBEN
    assert d.quelle == "vorgabe"           # kein Wert stammt aus der Datei


def test_jede_ablehnung_steht_im_log(w, caplog):
    w.ueberschreibe(farben={"spur": "nein"})

    with caplog.at_level(logging.WARNING, logger="pipeline.design"):
        d = w.laden()
        w.laden()                 # zweiter Aufruf: aus dem Zwischenspeicher, kein zweiter Eintrag

    protokoll = [r for r in caplog.records if r.name == "pipeline.design"]
    assert len(protokoll) == 1 and protokoll[0].levelno == logging.WARNING
    assert "spur" in protokoll[0].getMessage()
    assert d.warnungen[0] in protokoll[0].getMessage()


# ── 4. Paarregel und Kontrast ─────────────────────────────────────────────────────────────────
def test_ein_paar_mit_ausreichendem_kontrast_gilt_gemeinsam(w):
    w.ueberschreibe(farben={"marke": "#102030", "auf_marke": "#FFFFFF"})

    d = w.laden()

    assert d.farben["marke"] == "#102030" and d.farben["auf_marke"] == "#FFFFFF"
    assert d.warnungen == ()


def test_ein_paar_mit_zu_schwachem_kontrast_faellt_als_ganzes_auf_die_vorgabe(w):
    w.ueberschreibe(farben={"marke": "#336699", "auf_marke": "#3366AA", "spur": "#101010"})

    d = w.laden()

    assert d.farben["marke"] == "#0B1F3A" and d.farben["auf_marke"] == "#DCE4EE"
    assert d.farben["spur"] == "#101010"              # Rollen außerhalb des Paares sind nicht betroffen
    assert len(d.warnungen) == 1
    assert "marke/auf_marke" in d.warnungen[0] and "4,5:1" in d.warnungen[0]


def test_grenzfall_4_54_gilt_und_4_48_nicht(w):
    w.ueberschreibe(farben={"marke": "#767676", "auf_marke": "#FFFFFF"})
    knapp_drueber = w.laden()
    w.ueberschreibe(farben={"marke": "#777777", "auf_marke": "#FFFFFF"})
    os.utime(w.datei, ns=(2_000_000_000_000_000_000, 2_000_000_000_000_000_000))   # Änderungszeit sicher neu
    knapp_drunter = w.laden()

    assert knapp_drueber.farben["marke"] == "#767676" and knapp_drueber.warnungen == ()
    assert knapp_drunter.farben["marke"] == "#0B1F3A" and knapp_drunter.farben["auf_marke"] == "#DCE4EE"
    assert len(knapp_drunter.warnungen) == 1 and "4,47:1" in knapp_drunter.warnungen[0]   # abgerundet


def test_nur_eine_haelfte_wird_gegen_die_andere_aus_der_vorgabe_geprueft(w):
    """`auf_marke` allein: Weiß auf der Vorgabe-Marke (Navy) hat guten Kontrast und gilt."""
    w.ueberschreibe(farben={"auf_marke": "#FFFFFF"})

    d = w.laden()

    assert d.farben["auf_marke"] == "#FFFFFF" and d.farben["marke"] == "#0B1F3A"
    assert d.warnungen == ()


def test_nur_eine_haelfte_mit_zu_schwachem_kontrast_gegen_die_vorgabe_wird_abgelehnt(w):
    """`marke` allein, Weiß: gegen die Vorgabe-Schrift #DCE4EE kaum zu lesen. Das Paar gilt nur
    gemeinsam, also bleibt die Marke, wie sie war."""
    w.ueberschreibe(farben={"marke": "#FFFFFF"})

    d = w.laden()

    assert d.farben["marke"] == "#0B1F3A" and d.farben["auf_marke"] == "#DCE4EE"
    assert len(d.warnungen) == 1 and "marke/auf_marke" in d.warnungen[0]


def test_eine_neue_aktionsfarbe_ohne_passende_schrift_wird_abgelehnt(w):
    """Orange als Aktionsfarbe mit der Vorgabe-Schrift Weiß hat unter 3:1. Wer die Aktionsfarbe
    ändert, bringt `auf_aktion` mit (Grenzen: Schriftrollen passend mitliefern)."""
    w.ueberschreibe(farben={"aktion": "#F57C00"})
    ohne = w.laden()
    w.ueberschreibe(farben={"aktion": "#F57C00", "auf_aktion": "#000000"})
    os.utime(w.datei, ns=(2_000_000_000_000_000_000, 2_000_000_000_000_000_000))
    mit = w.laden()

    assert ohne.farben["aktion"] == "#00B4D8" and len(ohne.warnungen) == 1
    assert "aktion/auf_aktion" in ohne.warnungen[0]
    assert mit.farben["aktion"] == "#F57C00" and mit.farben["auf_aktion"] == "#000000"
    assert mit.warnungen == ()


def test_die_aktionsfarbe_der_vorgabe_mit_dunkler_schrift_gilt(w):
    """Die Umstellung auf den Wert des Brand-Kits (Navy statt Weiß) ist eine Zeile."""
    w.ueberschreibe(farben={"auf_aktion": "#0B1F3A"})

    d = w.laden()

    assert d.farben["auf_aktion"] == "#0B1F3A" and d.warnungen == ()


def test_auch_das_zweite_paar_aus_flaeche_und_text_braucht_kontrast(w):
    w.ueberschreibe(farben={"flaeche": "#101820", "text": "#102030"})

    d = w.laden()

    assert d.farben["flaeche"] == "#F4F7FB" and d.farben["text"] == "#0B1F3A"
    assert len(d.warnungen) == 1 and "flaeche/text" in d.warnungen[0]


def test_text_gilt_nur_wenn_beide_paare_bestehen_fall_flaeche(w):
    """#767676 hat auf Weiß (karte) 4,54:1, auf der Vorgabe-Fläche #F4F7FB nur 4,23:1. `text` gehört
    zu beiden Paaren; fällt eines durch, gilt die Vorgabe-Schrift, und das andere Paar wird gegen sie
    erneut geprüft (hier: wörtlich die Vorgabe, also gut)."""
    w.ueberschreibe(farben={"text": "#767676"})

    d = w.laden()

    assert d.farben["text"] == "#0B1F3A"
    assert len(d.warnungen) == 1 and "flaeche/text" in d.warnungen[0]


def test_text_gilt_wenn_beide_paare_bestehen(w):
    w.ueberschreibe(farben={"text": "#222222", "flaeche": "#FFFFFF", "karte": "#F8F8F8"})

    d = w.laden()

    assert (d.farben["text"], d.farben["flaeche"], d.farben["karte"]) == ("#222222", "#FFFFFF", "#F8F8F8")
    assert d.warnungen == ()


def test_faellt_ein_text_paar_durch_wird_das_andere_gegen_die_vorgabe_schrift_neu_geprueft(w):
    w.ueberschreibe(farben={"flaeche": "#101820", "karte": "#182028", "text": "#F0F0F0"})
    gut = w.laden()           # helle Schrift auf zwei dunklen Flächen: beide Paare bestehen
    w.ueberschreibe(farben={"flaeche": "#101820", "karte": "#F0F0F0", "text": "#F0F0F0"})
    os.utime(w.datei, ns=(2_000_000_000_000_000_000, 2_000_000_000_000_000_000))
    schlecht = w.laden()

    assert (gut.farben["flaeche"], gut.farben["karte"], gut.farben["text"]) == ("#101820", "#182028", "#F0F0F0")
    assert gut.warnungen == ()
    # karte/text = #F0F0F0 auf #F0F0F0 fällt durch. Danach gilt für text und karte die Vorgabe, und
    # flaeche (#101820) wird gegen die Vorgabe-Schrift Navy erneut geprüft und fällt ebenfalls durch.
    assert (schlecht.farben["flaeche"], schlecht.farben["karte"], schlecht.farben["text"]) == (
        "#F4F7FB", "#FFFFFF", "#0B1F3A")
    assert len(schlecht.warnungen) == 2
    assert "karte/text" in schlecht.warnungen[0] and "flaeche/text" in schlecht.warnungen[1]


def test_das_ergebnis_haengt_nicht_von_der_reihenfolge_in_der_datei_ab(w, design):
    farben = {"karte": "#F0F0F0", "text": "#F0F0F0", "flaeche": "#101820", "marke": "#777777",
              "auf_marke": "#FFFFFF", "spur": "#222222"}
    w.ueberschreibe(farben=farben)
    vorwaerts = w.laden()
    design.zwischenspeicher_leeren()
    w.ueberschreibe(farben=dict(reversed(list(farben.items()))))
    rueckwaerts = w.laden()

    assert dict(vorwaerts.farben) == dict(rueckwaerts.farben)
    assert vorwaerts.warnungen == rueckwaerts.warnungen
    assert vorwaerts.stand == rueckwaerts.stand


def test_eine_halbe_ungueltige_farbe_im_paar_wird_wie_nicht_genannt_behandelt(w):
    w.ueberschreibe(farben={"marke": "#102030", "auf_marke": "weiss"})

    d = w.laden()

    # `auf_marke` ist ungültig und kommt aus der Vorgabe (#DCE4EE): Navy-Schwarz #102030 darauf ist gut.
    assert d.farben["marke"] == "#102030" and d.farben["auf_marke"] == "#DCE4EE"
    assert len(d.warnungen) == 1 and "auf_marke" in d.warnungen[0]


# ── 3b. Icons ─────────────────────────────────────────────────────────────────────────────────
def test_gueltige_icons_der_ueberschreibung_gelten(w):
    w.icon("mein-32.png", png(32))
    w.icon("mein-180.png", png(180))
    w.ueberschreibe(icon={"32": "mein-32.png", "180": "mein-180.png"})

    d = w.laden()

    assert d.icon(32) == w.ordner / "mein-32.png" and d.icon(180) == w.ordner / "mein-180.png"
    assert d.icon_bytes(32) == png(32)
    assert d.warnungen == () and d.quelle == "ueberschreibung"


def test_ein_icon_nur_einer_groesse_laesst_die_andere_aus_der_vorgabe(w):
    w.icon("neu.png", png(64))
    w.ueberschreibe(icon={"180": "neu.png"})

    d = w.laden()

    assert d.icon(180) == w.ordner / "neu.png"
    assert d.icon(32) == w.vorgabe_ordner / "icon-32.png"
    assert d.warnungen == ()


def test_ein_icon_genau_an_der_grenze_von_200_kb_gilt_ein_byte_mehr_nicht(w, design):
    w.icon("grenze.png", png(8, laenge=design.ICON_MAX_BYTES))
    w.icon("drueber.png", png(8, laenge=design.ICON_MAX_BYTES + 1))
    w.ueberschreibe(icon={"32": "grenze.png", "180": "drueber.png"})

    d = w.laden()

    assert d.icon(32) == w.ordner / "grenze.png"
    assert d.icon(180) == w.vorgabe_ordner / "icon-180.png"
    assert len(d.warnungen) == 1 and "180" in d.warnungen[0] and "200 KB" in d.warnungen[0]
    assert design.ICON_MAX_BYTES == 200 * 1024


@pytest.mark.parametrize("inhalt, stichwort", [
    (png(32, 16), "quadratisch"), (png(16, 32), "quadratisch"), (png(32, 31), "quadratisch"),
    (png(2000, mit_bild=False), "quadratisch"), (png(0, mit_bild=False), "quadratisch"),
    (b"\xff\xd8\xff\xe0" + b"\x00" * 100, "kein PNG"), (b"GIF89a" + b"\x00" * 100, "kein PNG"),
    (b"", "kein PNG"), (b"\x89PNG\r\n\x1a\n", "kein PNG"), (b"{}" * 50, "kein PNG"),
    (png(32)[:20], "kein PNG"),                                    # abgeschnitten im Kopf
    (png(32)[:8] + b"\x00\x00\x00\x0dIDAT" + png(32)[16:], "kein PNG"),   # erster Block ist kein IHDR
    (png(32)[:29] + b"\x00\x00\x00\x00" + png(32)[33:], "kein PNG"),      # Prüfsumme des Kopfes falsch
    (b"GIF89a\x00\x00" + png(32)[8:], "kein PNG"),    # Kopf-Chunk in Ordnung, Signatur falsch
    (b"\x89PNG\r\n\x1a\x0b" + png(32)[8:], "kein PNG"),  # Signatur um ein Byte daneben
])
def test_ein_unbrauchbares_icon_ergibt_das_icon_der_vorgabe_und_eine_warnung(w, inhalt, stichwort):
    w.icon("x.png", inhalt)
    w.ueberschreibe(icon={"32": "x.png"})

    d = w.laden()

    assert d.icon(32) == w.vorgabe_ordner / "icon-32.png"
    assert len(d.warnungen) == 1 and stichwort in d.warnungen[0]
    assert d.quelle == "vorgabe"


@pytest.mark.parametrize("name", [
    "../x.png", "..\\x.png", "unter/x.png", "unter\\x.png", "/abs/x.png", "C:\\x.png", "C:x.png",
    "x.png:strom", ".", "..", "", " ", " x.png", "x.png ", "x\n.png", "x\x00.png", "a" * 101 + ".png",
    5, None, ["x.png"], True,
])
def test_ein_dateiname_mit_pfadanteil_ergibt_das_icon_der_vorgabe_und_eine_warnung(w, tmp_path, name):
    """Auch wenn hinter dem Pfad eine gültige PNG-Datei läge: Sie wird nie gelesen."""
    (tmp_path / "x.png").write_bytes(png(32))             # liegt EINEN Ordner über der Überschreibung
    (tmp_path / "daten" / "x.png").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "daten" / "x.png").write_bytes(png(32))
    w.icon("x.png", png(32))
    w.ueberschreibe(icon={"32": name})

    d = w.laden()

    assert d.icon(32) == w.vorgabe_ordner / "icon-32.png"
    assert len(d.warnungen) == 1 and "Dateiname ohne Pfad" in d.warnungen[0]


def test_eine_fehlende_icondatei_ergibt_das_icon_der_vorgabe_und_eine_warnung(w):
    w.ueberschreibe(icon={"32": "gibt-es-nicht.png"})

    d = w.laden()

    assert d.icon(32) == w.vorgabe_ordner / "icon-32.png"
    assert len(d.warnungen) == 1 and "fehlt" in d.warnungen[0]


def test_ein_verzeichnis_als_icon_ergibt_das_icon_der_vorgabe(w):
    (w.ordner / "ordner.png").mkdir(parents=True)
    w.ueberschreibe(icon={"32": "ordner.png"})

    d = w.laden()

    assert d.icon(32) == w.vorgabe_ordner / "icon-32.png" and len(d.warnungen) == 1


def test_ein_symlink_aus_dem_ordner_heraus_wird_nicht_gelesen(w, tmp_path):
    ausserhalb = tmp_path / "woanders.png"
    ausserhalb.write_bytes(png(32))
    w.ordner.mkdir(parents=True)
    try:
        os.symlink(ausserhalb, w.ordner / "link.png")
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks hier nicht möglich")
    w.ueberschreibe(icon={"32": "link.png"})

    d = w.laden()

    assert d.icon(32) == w.vorgabe_ordner / "icon-32.png"
    assert len(d.warnungen) == 1 and "nicht im Ordner" in d.warnungen[0]


def test_die_icons_der_vorgabe_liegen_im_ordner_der_vorgabe(w):
    d = w.laden()

    assert d.icon(32).parent == w.vorgabe_ordner and d.icon(180).parent == w.vorgabe_ordner


# ── 5. Zwischenspeicher ───────────────────────────────────────────────────────────────────────
def test_der_zwischenspeicher_gibt_dasselbe_objekt_zurueck(w):
    w.ueberschreibe(farben={"spur": "#101010"})

    assert w.laden() is w.laden()


def test_der_zwischenspeicher_bemerkt_eine_geaenderte_datei_mit_anderer_groesse(w):
    w.ueberschreibe(farben={"spur": "#101010"})
    erstes = w.laden()
    w.ueberschreibe(farben={"spur": "#101010", "trenner": "#202020"})
    zweites = w.laden()

    assert erstes.farben["trenner"] == "#2A3F5F" and zweites.farben["trenner"] == "#202020"
    assert zweites is not erstes


def test_der_zwischenspeicher_bemerkt_eine_geaenderte_aenderungszeit_bei_gleicher_groesse(w):
    w.ueberschreibe(farben={"spur": "#101010"})
    os.utime(w.datei, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
    erstes = w.laden()
    w.ueberschreibe(farben={"spur": "#202020"})            # gleich lang
    os.utime(w.datei, ns=(1_700_000_001_000_000_000, 1_700_000_001_000_000_000))
    zweites = w.laden()

    assert erstes.farben["spur"] == "#101010" and zweites.farben["spur"] == "#202020"


def test_der_zwischenspeicher_bemerkt_eine_neue_und_eine_geloeschte_ueberschreibung(w):
    ohne = w.laden()
    w.ueberschreibe(name="Neuer Name")
    mit = w.laden()
    w.datei.unlink()
    wieder_ohne = w.laden()

    assert ohne.name == "Standard" and mit.name == "Neuer Name"
    assert wieder_ohne.name == "Standard" and wieder_ohne.quelle == "vorgabe"


def test_der_zwischenspeicher_bemerkt_eine_geaenderte_vorgabe(w):
    erstes = w.laden()
    daten = json.loads(w.vorgabe.read_text(encoding="utf-8"))
    daten["produktname"] = "Vorgabe geändert"
    w.vorgabe.write_text(json.dumps(daten, ensure_ascii=False, indent=4), encoding="utf-8")

    assert w.laden().produktname == "Vorgabe geändert" and erstes.produktname == HEUTIGER_PRODUKTNAME


def test_der_zwischenspeicher_bemerkt_ein_geaendertes_icon_bei_gleicher_json_datei(w):
    w.icon("a.png", png(32))
    w.ueberschreibe(icon={"32": "a.png"})
    erstes = w.laden()
    w.icon("a.png", png(48))                               # andere Größe, andere Bytes
    zweites = w.laden()

    assert zweites is not erstes and zweites.stand != erstes.stand
    assert zweites.icon_bytes(32) == png(48)


def test_ein_vorher_fehlendes_icon_wird_bemerkt_sobald_es_da_ist(w):
    w.ueberschreibe(icon={"32": "spaeter.png"})
    davor = w.laden()
    w.icon("spaeter.png", png(32))
    danach = w.laden()

    assert len(davor.warnungen) == 1 and davor.icon(32) == w.vorgabe_ordner / "icon-32.png"
    assert danach.warnungen == () and danach.icon(32) == w.ordner / "spaeter.png"


def test_zwischenspeicher_leeren_erzwingt_neues_lesen(w, design):
    erstes = w.laden()
    design.zwischenspeicher_leeren()

    zweites = w.laden()

    assert zweites is not erstes and zweites == erstes


def test_vorgabe_und_laden_haben_getrennte_zwischenspeicher(w):
    w.ueberschreibe(name="Andere Firma")

    assert w.laden().name == "Andere Firma"
    assert w.design.vorgabe(w.vorgabe).name == "Standard"


# ── 6. Datenordner, CSS, Stand ────────────────────────────────────────────────────────────────
def test_der_datenordner_wird_bei_jedem_aufruf_neu_gelesen(design, tmp_path, monkeypatch):
    monkeypatch.setenv("BMS_DATA_DIR", str(tmp_path / "a"))
    erster = design.ueberschreibung_pfad()
    monkeypatch.setenv("BMS_DATA_DIR", str(tmp_path / "b"))
    zweiter = design.ueberschreibung_pfad()
    monkeypatch.delenv("BMS_DATA_DIR")
    ohne = design.ueberschreibung_pfad()

    assert erster == tmp_path / "a" / "design" / "design.json"
    assert zweiter == tmp_path / "b" / "design" / "design.json"
    assert ohne == design.PROJEKT_ROOT / "data" / "design" / "design.json"


def test_im_test_zeigt_der_datenordner_auf_den_wegwerf_ordner_der_sitzung(design):
    """Sicherheitsnetz wie bei `app.db`: Ohne Umlenkung läse `laden()` das echte `data/design/`."""
    assert design.datenordner() == Path(os.environ["BMS_DATA_DIR"])
    assert design.PROJEKT_ROOT / "data" not in design.ueberschreibung_pfad().parents


def test_laden_ohne_argumente_nimmt_vorgabe_und_datenordner_aus_der_umgebung(design, tmp_path,
                                                                           monkeypatch):
    monkeypatch.setenv("BMS_DATA_DIR", str(tmp_path))
    (tmp_path / "design").mkdir()
    (tmp_path / "design" / "design.json").write_text(
        json.dumps({"format": 1, "name": "Aus dem Datenordner"}), encoding="utf-8")

    d = design.laden()

    assert d.name == "Aus dem Datenordner" and d.quelle == "ueberschreibung"
    assert d.icon(32) == ASSETS_DESIGN / "icon-32.png"


def test_das_css_traegt_alle_rollen_kanaele_und_schriftstapel(design):
    css = design.css_oberflaeche(design.vorgabe())

    zeilen = css.splitlines()
    assert zeilen[0] == ":root {" and zeilen[-1] == "}" and css.endswith("}\n")
    for rolle, farbe in HEUTIGE_FARBEN.items():
        name = "--" + rolle.replace("_", "-")
        kanaele = " ".join(str(int(farbe[i:i + 2], 16)) for i in (1, 3, 5))
        assert f"  {name}: {kanaele};" in zeilen, rolle
        assert f"  {name}-farbe: {farbe};" in zeilen, rolle
    assert f"  --schrift-ueberschrift: {HEUTIGE_STAPEL['ueberschrift']};" in zeilen
    assert f"  --schrift-text: {HEUTIGE_STAPEL['text']};" in zeilen
    assert len(zeilen) == 2 + 13 * 2 + 2
    assert "--marke: 11 31 58;" in css and "--marke-farbe: #0B1F3A;" in css


def test_das_css_folgt_dem_geltenden_design(w, design):
    w.ueberschreibe(farben={"aktion_hover": "#FF6600"}, schriften={"text": "System"})

    css = design.css_oberflaeche(w.laden())

    assert "  --aktion-hover: 255 102 0;" in css and "  --aktion-hover-farbe: #FF6600;" in css
    assert "  --schrift-text: system-ui, -apple-system, 'Segoe UI', sans-serif;" in css
    assert "--schrift-ueberschrift: 'Montserrat'" in css


def test_das_css_enthaelt_nie_texte_des_designs(w, design):
    w.ueberschreibe(name="*/ body{display:none} /*", produktname="</style><script>alert(1)</script>")

    css = design.css_oberflaeche(w.laden())

    for verboten in ("body", "script", "alert", "display", "</style>", "*/"):
        assert verboten not in css


def test_alle_schriftstapel_sind_vollstaendig(design):
    assert set(design.SCHRIFTEN) == {"Inter", "Montserrat", "System"}
    assert design.SCHRIFTEN["Montserrat"] == HEUTIGE_STAPEL["ueberschrift"]
    assert design.SCHRIFTEN["Inter"] == HEUTIGE_STAPEL["text"]
    for stapel in design.SCHRIFTEN.values():
        assert stapel.endswith("sans-serif")


def test_der_stand_haengt_am_inhalt_nicht_an_der_datei(w, design, tmp_path):
    w.ueberschreibe(farben={"spur": "#101010"})
    erster = w.laden()
    design.zwischenspeicher_leeren()
    os.utime(w.datei, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))   # nur die Zeit ändert sich
    zweiter = w.laden()

    assert erster is not zweiter and erster.stand == zweiter.stand
    assert len(erster.stand) == 20 and set(erster.stand) <= set("0123456789abcdef")


@pytest.mark.parametrize("aenderung", [
    {"farben": {"spur": "#101011"}}, {"produktname": "Anderer Name"}, {"name": "Anderes Design"},
    {"schriften": {"text": "System"}},
    {"zusatz": 1},          # ändert keinen Wert, nur die Warnungen (die `/api/design` mitliefert)
])
def test_der_stand_aendert_sich_mit_jedem_wert_und_jeder_warnung(w, aenderung):
    basis = {"format": 1, "farben": {"spur": "#101010"}, "produktname": "Basis Name",
             "name": "Basisdesign", "schriften": {"text": "Inter"}}
    w.schreibe(basis)
    davor = w.laden()
    w.schreibe({**basis, **aenderung})
    os.utime(w.datei, ns=(2_000_000_000_000_000_000, 2_000_000_000_000_000_000))
    danach = w.laden()

    assert davor.stand != danach.stand


def test_der_stand_aendert_sich_mit_den_bytes_eines_icons(w):
    w.icon("a.png", png(32))
    w.ueberschreibe(icon={"32": "a.png"})
    davor = w.laden()
    w.icon("a.png", png(32, laenge=len(png(32)) + 40))
    danach = w.laden()

    assert davor.stand != danach.stand


# ── Kommandozeile ─────────────────────────────────────────────────────────────────────────────
def _kind_umgebung(tmp_path):
    daten, geheim, log = tmp_path / "daten", tmp_path / "geheim", tmp_path / "log"
    for ordner in (daten, geheim, log):
        ordner.mkdir(exist_ok=True)
    umgebung = dict(os.environ, BMS_DATA_DIR=str(daten), BMS_SECRETS_DIR=str(geheim),
                    BMS_LOG_DIR=str(log), PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    umgebung.pop("CLAUDE_BIN", None)
    return umgebung, daten, geheim


def _kind(argv, umgebung):
    return subprocess.run([sys.executable, "-m", "pipeline.design", *argv], cwd=str(BACKEND_DIR),
                          env=umgebung, capture_output=True, text=True, encoding="utf-8", timeout=60)


def test_zeigen_gibt_das_design_aus(tmp_path):
    umgebung, daten, _ = _kind_umgebung(tmp_path)

    lauf = _kind(["zeigen"], umgebung)

    assert lauf.returncode == 0, lauf.stderr
    assert lauf.stderr == ""                        # keine Meldung, keine Ausnahme, kein Log
    for erwartet in ("Geltendes Design: Standard", "Quelle:           vorgabe",
                     f"Produktname:      {HEUTIGER_PRODUKTNAME}", "#0B1F3A", "#00B4D8",
                     "Montserrat", "Inter", "Warnungen: keine", "icon-32.png", "icon-180.png",
                     "keine Datei"):
        assert erwartet in lauf.stdout, erwartet
    assert "Traceback" not in lauf.stdout
    assert not (daten / "bewerbung.sqlite").exists()   # nichts angelegt


def test_zeigen_nennt_ueberschreibung_und_warnungen_ohne_ausnahme(tmp_path):
    umgebung, daten, _ = _kind_umgebung(tmp_path)
    (daten / "design").mkdir()
    (daten / "design" / "design.json").write_text(json.dumps({
        "format": 1, "name": "Beispiel Karriere", "farben": {"spur": "grün", "trenner": "#112233"},
        "schriften": {"text": "Papyrus"}}), encoding="utf-8")

    lauf = _kind(["zeigen"], umgebung)

    assert lauf.returncode == 0 and lauf.stderr == "", lauf.stderr
    assert "Quelle:           ueberschreibung" in lauf.stdout
    assert "Beispiel Karriere" in lauf.stdout and "#112233" in lauf.stdout
    assert "Warnungen (2):" in lauf.stdout and "spur" in lauf.stdout and "Papyrus" in lauf.stdout
    assert "keine Datei" not in lauf.stdout


def test_zeigen_mit_kaputter_ueberschreibung_gibt_keine_ausnahme_aus(tmp_path):
    umgebung, daten, _ = _kind_umgebung(tmp_path)
    (daten / "design").mkdir()
    (daten / "design" / "design.json").write_bytes(b"\xff{kaputt")

    lauf = _kind(["zeigen"], umgebung)

    assert lauf.returncode == 0 and lauf.stderr == "", lauf.stderr
    assert "Quelle:           vorgabe" in lauf.stdout and "Warnungen (1):" in lauf.stdout
    assert "Traceback" not in lauf.stdout


@pytest.mark.parametrize("argv", [[], ["aendern"], ["zeigen", "extra"], ["css"], ["--hilfe"]])
def test_ein_anderer_unterbefehl_gibt_nur_die_nutzung_aus(tmp_path, argv):
    umgebung, _, _ = _kind_umgebung(tmp_path)

    lauf = _kind(argv, umgebung)

    assert lauf.returncode == 2 and lauf.stdout == ""
    assert "Nutzung: python -m pipeline.design zeigen" in lauf.stderr
    assert "Traceback" not in lauf.stderr


def test_zeigen_im_prozess_gibt_nichts_auf_den_log_aus(design, tmp_path, monkeypatch, capsys, caplog):
    monkeypatch.setenv("BMS_DATA_DIR", str(tmp_path))
    (tmp_path / "design").mkdir()
    (tmp_path / "design" / "design.json").write_text('{"format": 1, "produktname": "x"}', encoding="utf-8")

    assert design.main(["zeigen"]) == 0

    ausgabe = capsys.readouterr()
    assert "Warnungen (1):" in ausgabe.out and ausgabe.err == ""
    assert not any(h for h in logging.getLogger("pipeline.design").handlers
                   if isinstance(h, logging.NullHandler))      # der Handler gilt nur für den Lauf


def test_zeigen_bei_beschaedigter_vorgabe_meldet_es_ohne_traceback(design, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(design, "VORGABE_DATEI", tmp_path / "fehlt.json")
    monkeypatch.setenv("BMS_DATA_DIR", str(tmp_path))

    assert design.main(["zeigen"]) == 1

    ausgabe = capsys.readouterr()
    assert "unbrauchbar" in ausgabe.err and "fehlt.json" in ausgabe.err and ausgabe.out == ""


# ── Kundenpaket ───────────────────────────────────────────────────────────────────────────────
def test_die_neuen_dateien_gehen_ins_kundenpaket():
    """`assets/` wird ganz ausgeliefert; `kundenpaket.py` braucht keinen Eintrag. Dieser Test hält
    es fest und prüft, dass die Personendaten-Regeln für die neuen Dateien nichts finden."""
    from pipeline.kundenpaket import Eintrag, ausschliessen, pruefen_eintraege

    pfade = ["assets/design/standard.json", "assets/design/icon-32.png", "assets/design/icon-180.png",
             "backend/pipeline/design.py", "backend/app/routes_design.py"]
    eintraege = [Eintrag(p, 0o644, (PROJEKT_DIR / p).read_bytes()) for p in pfade]

    behalten, ausgeschlossen = ausschliessen(eintraege)

    assert ausgeschlossen == [] and [e.pfad for e in behalten] == pfade
    assert pruefen_eintraege(eintraege) == []
