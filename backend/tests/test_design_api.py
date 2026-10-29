"""P2-72 (Vertrag Q) — Schnittstelle zur Oberfläche: `app/routes_design.py`.

  GET /api/design              JSON: name, produktname, quelle, warnungen
  GET /api/design.css          text/css: ein :root-Block mit allen Rollen
  GET /api/design/icon/32|180  das geltende Icon als PNG, jede andere Größe 404

Deckt ab: die vier Aufrufe, die Kanäle in `design.css` gegen die Hex-Werte, `Cache-Control: no-cache`
und ETag, 304 bei passendem
`If-None-Match` (auch in der schwachen Schreibweise, als Liste und mit `*`), ein ETag, der sich mit
der Überschreibung ändert, und dass eine Überschreibung unter dem Datenordner sofort gilt (ohne
Neustart, ohne Neubau).

Die Überschreibung liegt immer unter `tmp_path`: Der Datenordner wird nur für den einzelnen Test
umgelenkt (`monkeypatch`), nie wird `data/` des Projekts gelesen oder geschrieben. App-Module nur
funktionslokal importieren (conftest.py).
"""
import json
import re
import struct
import zlib

import pytest

ADRESSEN = ["/api/design", "/api/design.css", "/api/design/icon/32", "/api/design/icon/180"]


def png(breite=32):
    def block(typ, daten):
        return struct.pack(">I", len(daten)) + typ + daten + struct.pack(">I", zlib.crc32(typ + daten))

    bild = zlib.compress((b"\x00" + b"\x30\x20\x10" * breite) * breite)
    return (b"\x89PNG\r\n\x1a\n" + block(b"IHDR", struct.pack(">IIBBBBB", breite, breite, 8, 2, 0, 0, 0))
            + block(b"IDAT", bild) + block(b"IEND", b""))


class Ueberschreibung:
    """Der Ordner `<Datenordner>/design/` eines Tests."""

    def __init__(self, ordner):
        self.ordner = ordner

    def schreibe(self, **teile):
        self.ordner.mkdir(parents=True, exist_ok=True)
        (self.ordner / "design.json").write_text(json.dumps({"format": 1, **teile}), encoding="utf-8")

    def icon(self, name, daten):
        self.ordner.mkdir(parents=True, exist_ok=True)
        (self.ordner / name).write_bytes(daten)


@pytest.fixture()
def ueberschreibung(client, tmp_path, monkeypatch):
    """Lenkt den Datenordner für diesen Test um (`client` zuerst: Die App und ihre Datenbank sind
    dann schon an den Wegwerf-Ordner der Sitzung gebunden) und räumt den Zwischenspeicher auf."""
    from pipeline import design

    monkeypatch.setenv("BMS_DATA_DIR", str(tmp_path / "daten"))
    design.zwischenspeicher_leeren()
    yield Ueberschreibung(tmp_path / "daten" / "design")
    design.zwischenspeicher_leeren()


def css_werte(text):
    """{variable: wert} aus dem :root-Block."""
    return dict(re.findall(r"^\s+(--[\w-]+):\s*(.+?);$", text, re.MULTILINE))


# ── Die vier Aufrufe ──────────────────────────────────────────────────────────────────────────
def test_auskunft_mit_der_vorgabe(client, ueberschreibung):
    antwort = client.get("/api/design")

    assert antwort.status_code == 200
    assert antwort.headers["content-type"] == "application/json"
    assert antwort.json() == {"name": "Standard", "produktname": "Bewerbungs-Management-System",
                              "quelle": "vorgabe", "warnungen": []}


def test_das_css_ist_ein_root_block_als_text_css(client, ueberschreibung):
    antwort = client.get("/api/design.css")

    assert antwort.status_code == 200
    assert antwort.headers["content-type"] == "text/css; charset=utf-8"
    assert antwort.text.startswith(":root {") and antwort.text.rstrip().endswith("}")


def test_die_kanaele_im_css_stimmen_mit_den_hex_werten_ueberein(client, ueberschreibung):
    from pipeline import design

    werte = css_werte(client.get("/api/design.css").text)
    vorgabe = design.vorgabe().farben

    assert len(vorgabe) == 13
    for rolle, farbe in vorgabe.items():
        name = "--" + rolle.replace("_", "-")
        assert werte[f"{name}-farbe"] == farbe, rolle
        r, g, b = (int(farbe[i:i + 2], 16) for i in (1, 3, 5))
        assert werte[name] == f"{r} {g} {b}", rolle
    assert werte["--marke"] == "11 31 58" and werte["--marke-farbe"] == "#0B1F3A"
    assert werte["--schrift-ueberschrift"] == "'Montserrat', 'Poppins', Arial, sans-serif"
    assert werte["--schrift-text"] == "'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif"
    assert len(werte) == 13 * 2 + 2


@pytest.mark.parametrize("groesse, original", [("32", "icon-32.png"), ("180", "icon-180.png")])
def test_das_icon_ist_ein_png_und_die_datei_der_vorgabe(client, ueberschreibung, groesse, original):
    from pipeline import design

    antwort = client.get(f"/api/design/icon/{groesse}")

    assert antwort.status_code == 200
    assert antwort.headers["content-type"] == "image/png"
    assert antwort.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert antwort.content == (design.PROJEKT_ROOT / "assets" / "design" / original).read_bytes()


@pytest.mark.parametrize("groesse", ["16", "64", "512", "0", "1", "-32", "abc", "032", "32.0", "3 2",
                                     "32%20", "%2e%2e", "32x32", "180180", "ALL"])
def test_jede_andere_groesse_ist_404(client, ueberschreibung, groesse):
    antwort = client.get(f"/api/design/icon/{groesse}")

    assert antwort.status_code == 404


def test_die_routen_sind_eingebunden(client):
    from app.main import app

    pfade = app.openapi()["paths"]

    for pfad in ("/api/design", "/api/design.css", "/api/design/icon/{groesse}"):
        assert list(pfade[pfad]) == ["get"], pfad


@pytest.mark.parametrize("methode", ["post", "put", "patch", "delete"])
def test_die_schnittstelle_ist_nur_lesend(client, ueberschreibung, methode):
    for adresse in ADRESSEN:
        assert client.request(methode, adresse).status_code == 405, (methode, adresse)


# ── Cache-Control und ETag ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("adresse", ADRESSEN)
def test_jede_antwort_traegt_no_cache_und_einen_etag(client, ueberschreibung, adresse):
    antwort = client.get(adresse)

    assert antwort.headers["cache-control"] == "no-cache"
    assert re.fullmatch(r'"[0-9a-f]{20}"', antwort.headers["etag"])


def test_der_etag_ist_bei_unveraendertem_design_stabil(client, ueberschreibung):
    erster = client.get("/api/design").headers["etag"]

    assert client.get("/api/design").headers["etag"] == erster
    assert client.get("/api/design.css").headers["etag"] == erster       # ein Stand für alle drei


@pytest.mark.parametrize("adresse", ADRESSEN)
def test_passender_etag_ergibt_304_ohne_inhalt(client, ueberschreibung, adresse):
    etag = client.get(adresse).headers["etag"]

    antwort = client.get(adresse, headers={"If-None-Match": etag})

    assert antwort.status_code == 304
    assert antwort.content == b""
    assert antwort.headers["etag"] == etag and antwort.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("form", ["genau", "schwach", "liste", "liste_schwach", "stern", "mit_rand"])
def test_if_none_match_in_allen_ueblichen_schreibweisen(client, ueberschreibung, form):
    etag = client.get("/api/design.css").headers["etag"]
    kopf = {"genau": etag, "schwach": f"W/{etag}", "liste": f'"abc", {etag}, "def"',
            "liste_schwach": f'"abc",W/{etag}', "stern": "*", "mit_rand": f"  {etag}  "}[form]

    assert client.get("/api/design.css", headers={"If-None-Match": kopf}).status_code == 304


@pytest.mark.parametrize("kopf", ['"abc"', '"0123456789abcdef0123"', "", "unquoted", 'W/"x"',
                                  '"a" "b"', "None"])
def test_ein_fremder_etag_ergibt_die_volle_antwort(client, ueberschreibung, kopf):
    antwort = client.get("/api/design.css", headers={"If-None-Match": kopf})

    assert antwort.status_code == 200 and antwort.text.startswith(":root")


def test_der_etag_aendert_sich_mit_der_ueberschreibung(client, ueberschreibung):
    vorher = {a: client.get(a).headers["etag"] for a in ADRESSEN}
    ueberschreibung.schreibe(farben={"spur": "#101010"})
    nachher = {a: client.get(a).headers["etag"] for a in ADRESSEN}

    for adresse in ADRESSEN:
        assert nachher[adresse] != vorher[adresse], adresse
    # Der alte ETag bekommt nun die neue Antwort statt eines 304.
    alt = client.get("/api/design.css", headers={"If-None-Match": vorher["/api/design.css"]})
    assert alt.status_code == 200 and "--spur-farbe: #101010;" in alt.text
    neu = client.get("/api/design.css", headers={"If-None-Match": nachher["/api/design.css"]})
    assert neu.status_code == 304


def test_der_etag_aendert_sich_auch_wenn_nur_ein_icon_getauscht_wird(client, ueberschreibung):
    ueberschreibung.icon("logo.png", png(32))
    ueberschreibung.schreibe(icon={"32": "logo.png"})
    erster = client.get("/api/design/icon/32").headers["etag"]
    ueberschreibung.icon("logo.png", png(48))           # dieselbe JSON-Datei, anderes Bild

    zweiter = client.get("/api/design/icon/32")

    assert zweiter.headers["etag"] != erster and zweiter.content == png(48)


def test_der_etag_gehoert_zum_inhalt_nicht_zur_datei(client, ueberschreibung):
    """Dieselben Werte in einer neu geschriebenen Datei ändern den ETag nicht: Der Browser behält
    seinen Zwischenspeicher."""
    import os

    ueberschreibung.schreibe(farben={"spur": "#101010"})
    erster = client.get("/api/design.css").headers["etag"]
    ueberschreibung.schreibe(farben={"spur": "#101010"})
    os.utime(ueberschreibung.ordner / "design.json", ns=(1_900_000_000_000_000_000,) * 2)

    assert client.get("/api/design.css").headers["etag"] == erster


# ── Eine Überschreibung gilt sofort ───────────────────────────────────────────────────────────
def test_die_ueberschreibung_unter_dem_datenordner_gilt_in_allen_aufrufen(client, ueberschreibung):
    ueberschreibung.icon("mein-32.png", png(32))
    ueberschreibung.icon("mein-180.png", png(180))
    ueberschreibung.schreibe(
        name="Beispiel Orange",
        farben={"marke": "#3A1F0B", "auf_marke": "#FFF3E0", "aktion": "#E65100", "auf_aktion": "#000000",
                "aktion_hover": "#BF360C"},
        schriften={"ueberschrift": "Inter", "text": "System"},
        icon={"32": "mein-32.png", "180": "mein-180.png"})

    auskunft = client.get("/api/design").json()
    css = client.get("/api/design.css").text
    werte = css_werte(css)

    assert auskunft == {"name": "Beispiel Orange", "produktname": "Bewerbungs-Management-System",
                        "quelle": "ueberschreibung", "warnungen": []}
    assert werte["--marke-farbe"] == "#3A1F0B" and werte["--marke"] == "58 31 11"
    assert werte["--aktion-farbe"] == "#E65100" and werte["--aktion"] == "230 81 0"
    assert werte["--auf-aktion-farbe"] == "#000000" and werte["--auf-aktion"] == "0 0 0"
    assert werte["--aktion-hover"] == "191 54 12"
    assert werte["--spur-farbe"] == "#EAF0F6"                  # nicht genannt: Vorgabe
    assert werte["--schrift-ueberschrift"] == "'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif"
    assert werte["--schrift-text"] == "system-ui, -apple-system, 'Segoe UI', sans-serif"
    assert "#0B1F3A" not in css.replace("--text-farbe: #0B1F3A;", "")   # nur `text` bleibt Navy
    assert client.get("/api/design/icon/32").content == png(32)
    assert client.get("/api/design/icon/180").content == png(180)


def test_eine_geaenderte_ueberschreibung_gilt_beim_naechsten_aufruf_ohne_neustart(client, ueberschreibung):
    ueberschreibung.schreibe(name="Erster Name")
    assert client.get("/api/design").json()["name"] == "Erster Name"

    ueberschreibung.schreibe(name="Zweiter Name, länger")

    assert client.get("/api/design").json()["name"] == "Zweiter Name, länger"


def test_der_produktname_bleibt_auch_mit_einer_ueberschreibung(client, ueberschreibung):
    """Vorgabe vom 14.10.2026: Der Name bleibt „Bewerbungs-Management-System“, auch mit einem anderen
    Design. Die Auskunft nennt den festen Namen und warnt."""
    ueberschreibung.schreibe(produktname="Beispiel Karriere-Plattform", farben={"spur": "#101010"})

    auskunft = client.get("/api/design").json()

    assert auskunft["produktname"] == "Bewerbungs-Management-System"
    assert auskunft["quelle"] == "ueberschreibung"
    assert len(auskunft["warnungen"]) == 1 and "Produktname ist fest" in auskunft["warnungen"][0]


def test_wird_die_ueberschreibung_geloescht_gilt_wieder_die_vorgabe(client, ueberschreibung):
    ueberschreibung.schreibe(name="Nur kurz")
    assert client.get("/api/design").json()["quelle"] == "ueberschreibung"

    (ueberschreibung.ordner / "design.json").unlink()

    assert client.get("/api/design").json()["quelle"] == "vorgabe"


def test_abgelehnte_werte_stehen_als_warnungen_in_der_auskunft(client, ueberschreibung):
    ueberschreibung.schreibe(produktname="x", farben={"spur": "grün", "marke": "#FFFFFF"},
                             schriften={"text": "Papyrus"}, icon={"32": "../x.png"})

    auskunft = client.get("/api/design").json()
    css = client.get("/api/design.css").text

    assert auskunft["produktname"] == "Bewerbungs-Management-System"
    assert auskunft["quelle"] == "vorgabe"
    assert len(auskunft["warnungen"]) == 5
    for stichwort in ("Produktname", "spur", "marke/auf_marke", "Papyrus", "Icon 32"):
        assert any(stichwort in satz for satz in auskunft["warnungen"]), stichwort
    assert "--spur-farbe: #EAF0F6;" in css and "--marke-farbe: #0B1F3A;" in css


def test_eine_kaputte_ueberschreibung_macht_keine_antwort_kaputt(client, ueberschreibung):
    ueberschreibung.ordner.mkdir(parents=True)
    (ueberschreibung.ordner / "design.json").write_bytes(b"\xff\xfe{kaputt")

    for adresse in ADRESSEN:
        assert client.get(adresse).status_code == 200, adresse
    auskunft = client.get("/api/design").json()
    assert auskunft["quelle"] == "vorgabe" and len(auskunft["warnungen"]) == 1


def test_ein_icon_mit_pfadanteil_liefert_nie_eine_fremde_datei(client, ueberschreibung, tmp_path):
    (tmp_path / "daten").mkdir(exist_ok=True)
    (tmp_path / "daten" / "geheim.png").write_bytes(png(32) + b"GEHEIM")      # eine Ebene über dem Ordner
    ueberschreibung.schreibe(icon={"32": "../geheim.png"})

    antwort = client.get("/api/design/icon/32")

    assert antwort.status_code == 200 and b"GEHEIM" not in antwort.content
    assert antwort.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_eine_beschaedigte_vorgabe_ist_eine_verstaendliche_500(client, ueberschreibung, tmp_path,
                                                              monkeypatch):
    from pipeline import design

    monkeypatch.setattr(design, "VORGABE_DATEI", tmp_path / "fehlt" / "standard.json")

    for adresse in ADRESSEN:
        antwort = client.get(adresse)
        assert antwort.status_code == 500, adresse
        assert "Design-Vorgabe" in antwort.json()["detail"]
        assert str(tmp_path) not in antwort.json()["detail"]        # kein Pfad der Installation nach außen
    assert client.get("/api/design/icon/64").status_code == 404      # die Größe wird zuerst geprüft
