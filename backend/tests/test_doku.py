"""P2-59 (Paket D): Dokumentationsseite. Deckt `app/doku.py` (Katalog, Auflösung, Rendern) und
`app/routes_doku.py` (`GET /api/doku`, `GET /api/doku/{name}`) ab.

  1. Katalog: Form, Reihenfolge, Eindeutigkeit; Kunden- und interne Dokumente gegen
     `pipeline.kundenpaket` (intern darf nie ins Kundenpaket).
  2. `verfuegbar`: nur vorhandene Dateien; ohne die internen Dateien (so sieht es im Kundenpaket
     aus) gibt es keine interne Gruppe.
  3. `eintrag_fuer`: Kennung oder Dateiname, ohne Unterscheidung von Groß- und Kleinschreibung;
     jeder Fremdname ist unbekannt, AUCH wenn die Datei existiert (der Katalog ist die einzige
     Quelle, nie das Dateisystem).
  3a. Reiter „Installation & Updates“ (P2-71): `BMS_Install_Windows.md` unter Windows, sonst
     `BMS_Install_MAC.md`; beide Namen führen auf den Reiter, die früheren (`BMS_Install.md`,
     `BMS_Install_Auto.md`) nicht mehr. Das System ist ein Parameter (`systemname`), `os.name`
     wird nie umgebogen (Lehre aus Phase 71D).
  4. `rendern`: Titel der Datei, externe Links im neuen Tab, leerer Abschnitt „Unveröffentlicht“.
  5. Router auf eigener `FastAPI()`-App: Antwortform, Kopf exakt wie `main._BERICHT_KOPF`, 404.
  6. Die echten Dokumente des Projekts lassen sich rendern, und der Rahmen der Oberfläche bleibt
     in der Sandbox.

main.py bindet den Router zum Zeitpunkt von Paket D noch nicht ein (das macht die Hauptsession).
Die Router-Tests hängen ihn deshalb selbst in eine eigene `FastAPI()`-Instanz und bleiben nach der
Einbindung unverändert gültig (Muster `test_sicherung_api.py`).

Isolation: Der Projekt-Root ist ein tmp-Ordner (Parameter `projekt_root` bzw. `monkeypatch` auf
`doku.PROJECT_ROOT`). Die Fremdnamen-Fälle arbeiten mit EXISTIERENDEN Dateien, auch außerhalb des
Projekt-Roots, sonst bewiese ein „unbekannt“ nur, dass nichts da war. App-Module nur funktionslokal
importieren (s. conftest.py). Dateien per pathlib angelegt, damit derselbe Test unter Windows läuft.
"""
import re
from pathlib import PurePosixPath

import pytest

SOLL_IDS = ["version", "funktionen", "anleitung", "installation", "email", "windows",
            "coach-site", "beirat", "technik", "automatik", "release", "entwicklung"]
SOLL_TITEL = {
    "version": "Version", "funktionen": "Funktionen", "anleitung": "Anleitung",
    "installation": "Installation & Updates", "email": "E-Mail einrichten", "windows": "Windows",
    "coach-site": "Coach-Site", "beirat": "Beirat", "technik": "Technik",
    "automatik": "Automatik", "release": "Release", "entwicklung": "Entwickler-Installation",
}
INTERN = ["technik", "automatik", "release", "entwicklung"]


# ── Helfer ────────────────────────────────────────────────────────────────────────────────
def _datei(root, rel, text):
    ziel = root.joinpath(*rel.split("/"))
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(text, encoding="utf-8", newline="\n")
    return ziel


def _seite(titel, rest=""):
    return f"# {titel}\n\nEinleitung zu {titel}.\n\n## Abschnitt\n\nText zu {titel}.\n{rest}"


def _projekt(tmp_path, gruppen=("kunde", "intern"), ohne=()):
    """Ein Projekt-Root mit je einer Datei pro Katalogeintrag (Titel „Seite <id>“) und einigen
    Dateien, die NICHT im Katalog stehen, darunter eine außerhalb des Roots."""
    from app import doku

    root = tmp_path / "projekt"
    root.mkdir(exist_ok=True)
    for e in doku.KATALOG:
        if e["gruppe"] in gruppen and e["id"] not in ohne:
            if e["id"] == "installation":     # P2-71: beide Anleitungen, der Text nennt die Datei
                for datei in doku.INSTALLATIONSDATEIEN:
                    _datei(root, datei, _seite("Seite installation", f"\nAnleitung {datei}\n"))
            else:
                _datei(root, e["datei"], _seite(f"Seite {e['id']}"))
    _datei(root, "docs/GEHEIM.md", "# Geheim\n\n## Abschnitt\n\nnicht im Katalog\n")
    _datei(root, "docs/COACH_SITE.md", "# Coach intern\n\n## Abschnitt\n\nnicht im Katalog\n")
    _datei(root, "docs/BEIRAT-PERSONA-TEMPLATE.md", "# Vorlage\n\n## Abschnitt\n\nnicht im Katalog\n")
    # P2-82: Der Reiter „Lizenz“ ist ausgebaut. Eine Datei, die in einer alten Installation noch
    # liegt, ist deshalb eine Datei ohne Katalogeintrag wie jede andere (s. FREMDNAMEN).
    _datei(root, "docs/LIZENZ.md", "# Lizenz\n\n## Abschnitt\n\nnicht im Katalog\n")
    _datei(root, "README.md", "# Readme\n\n## Abschnitt\n\nnicht im Katalog\n")
    _datei(tmp_path, "ausserhalb.md", "# Ausserhalb\n\n## Abschnitt\n\nnicht im Projekt\n")
    return root


def _client(monkeypatch, root):
    """Eigene App nur mit dem Doku-Router. Der Router ruft `doku` ohne Root auf, also zeigt
    `PROJECT_ROOT` auf den tmp-Ordner."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app import doku
    from app.routes_doku import router

    monkeypatch.setattr(doku, "PROJECT_ROOT", root)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 1 — Katalog
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_katalog_hat_reihenfolge_titel_und_form_der_spec():
    from app import doku

    assert [e["id"] for e in doku.KATALOG] == SOLL_IDS
    assert {e["id"]: e["titel"] for e in doku.KATALOG} == SOLL_TITEL
    for e in doku.KATALOG:
        assert set(e) == {"id", "titel", "gruppe", "datei"}
        assert e["gruppe"] in ("kunde", "intern")
    # Die Kundengruppe steht komplett vor der internen: Die Oberfläche setzt dazwischen den Trenner.
    gruppen = [e["gruppe"] for e in doku.KATALOG]
    assert set(gruppen[gruppen.index("intern"):]) == {"intern"}
    assert [e["id"] for e in doku.KATALOG if e["gruppe"] == "intern"] == INTERN


def test_kein_reiter_lizenz_im_katalog():
    """P2-82: Die Lizenzpflicht ist ausgebaut, der Reiter „Lizenz“ und `docs/LIZENZ.md` gibt es nicht
    mehr. Weder Katalog noch Kundenpaket kennen sie, und auch ein Rest im echten Projektordner (eine
    alte Installation) löst nicht auf. Die Open-Source-Lizenz steht unter „Rechtliches“, nicht hier."""
    from app import doku
    from pipeline import kundenpaket

    assert "lizenz" not in {e["id"] for e in doku.KATALOG}
    assert not [e for e in doku.KATALOG if "LIZENZ" in e["datei"].upper()]
    assert "LIZENZ" not in kundenpaket.DOKU_ERLAUBT
    assert "docs/LIZENZ.md" not in kundenpaket.PFLICHTDATEIEN
    for name in ("lizenz", "LIZENZ.md", "LIZENZ.html"):
        assert doku.eintrag_fuer(name) is None, name


def test_katalog_dateien_sind_relative_markdown_pfade():
    from app import doku

    for e in doku.KATALOG:
        datei = e["datei"]
        assert datei.endswith(".md"), datei
        assert not datei.startswith("/") and "\\" not in datei, datei
        assert ".." not in datei.split("/"), datei
        assert len(datei.split("/")) <= 2, datei        # Paket-Root oder docs/, sonst nichts


def test_kennungen_und_dateinamen_verwechseln_sich_nie():
    """Eine Kennung hat keinen Punkt, ein Dateiname immer, und beide sind eindeutig: Nur so löst
    `eintrag_fuer` nie in den falschen Eintrag auf."""
    from app import doku

    kennungen = [e["id"] for e in doku.KATALOG]
    dateien = [d for e in doku.KATALOG
               for d in (doku.INSTALLATIONSDATEIEN if e["id"] == "installation" else (e["datei"],))]
    stamme = [PurePosixPath(d).stem.lower() for d in dateien]
    assert len(set(kennungen)) == len(kennungen)
    assert len(set(stamme)) == len(stamme)
    for k in kennungen:
        assert k.isascii() and k == k.lower() and "." not in k, k


def test_interne_dokumente_gehen_nie_ins_kundenpaket():
    """Die Gruppe „intern“ lebt davon, dass das Kundenpaket diese Dateien nicht enthält. Stünde
    eine davon in DOKU_ERLAUBT, sähe jeder Kunde den Tab."""
    from app import doku
    from pipeline import kundenpaket

    for e in doku.KATALOG:
        if e["gruppe"] == "intern":
            assert PurePosixPath(e["datei"]).stem not in kundenpaket.DOKU_ERLAUBT, e["datei"]
            assert e["datei"] not in kundenpaket.PFLICHTDATEIEN, e["datei"]


def test_beide_installationsanleitungen_liegen_im_kundenpaket():
    """Der Reiter „Installation & Updates“ zeigt die Anleitung des Systems. Fehlte eine der beiden
    im Paket, bliebe der Reiter bei den Kunden dieses Systems leer: Beide sind Pflichtdateien, und
    die alten Namen stehen nicht mehr dort."""
    from app import doku
    from pipeline import kundenpaket

    assert doku.INSTALLATIONSDATEIEN == ("BMS_Install_MAC.md", "BMS_Install_Windows.md")
    for datei in doku.INSTALLATIONSDATEIEN:
        assert datei in kundenpaket.PFLICHTDATEIEN, datei
    assert "BMS_Install.md" not in kundenpaket.PFLICHTDATEIEN
    assert "BMS_Install_Auto.md" not in kundenpaket.PFLICHTDATEIEN


def test_kundendokumente_aus_docs_liegen_im_kundenpaket():
    """Ein Kunden-Tab, dessen Datei das Paket nicht enthält, bliebe beim Kunden leer. Für Dateien,
    die es im Repository gibt (FUNKTIONEN entsteht erst im Doku-Paket), muss der Stamm in
    DOKU_ERLAUBT stehen."""
    from app import doku
    from pipeline import kundenpaket

    for e in doku.KATALOG:
        if e["gruppe"] == "kunde" and e["datei"].startswith("docs/") \
                and doku.PROJECT_ROOT.joinpath(*e["datei"].split("/")).is_file():
            assert PurePosixPath(e["datei"]).stem in kundenpaket.DOKU_ERLAUBT, e["datei"]


def test_jedes_ausgelieferte_kundendokument_hat_einen_tab():
    """Gegenstück: Kommt ein Dokument in DOKU_ERLAUBT, soll es in der Oberfläche stehen. Die
    Persona-Vorlage ist zum Kopieren gedacht und kein Lesetext."""
    from app import doku
    from pipeline import kundenpaket

    stamme = {PurePosixPath(e["datei"]).stem for e in doku.KATALOG}
    ausnahmen = {"BEIRAT-PERSONA-TEMPLATE"}
    assert not (kundenpaket.DOKU_ERLAUBT - stamme - ausnahmen), (
        "Dokument im Kundenpaket ohne Katalogeintrag in app/doku.py")


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 2 — verfuegbar
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_verfuegbar_listet_nur_vorhandene_dateien_in_katalog_reihenfolge(tmp_path):
    from app import doku

    fehlt = ("funktionen", "beirat", "automatik")
    root = _projekt(tmp_path, ohne=fehlt)

    assert [e["id"] for e in doku.verfuegbar(root)] == [i for i in SOLL_IDS if i not in fehlt]


def test_ohne_die_internen_dateien_gibt_es_keine_interne_gruppe(tmp_path):
    """So sieht eine Kundeninstallation aus: Das Paket enthält die internen Dokumente nicht."""
    from app import doku

    root = _projekt(tmp_path, gruppen=("kunde",))

    eintraege = doku.verfuegbar(root)
    assert {e["gruppe"] for e in eintraege} == {"kunde"}
    assert [e["id"] for e in eintraege] == [i for i in SOLL_IDS if i not in INTERN]
    for kennung in INTERN:
        assert doku.eintrag_fuer(kennung, root) is None


def test_funktionen_erscheint_erst_mit_der_datei(tmp_path):
    """docs/FUNKTIONEN.md entsteht erst im Doku-Paket: Bis dahin blendet der Katalog den Tab aus."""
    from app import doku

    root = _projekt(tmp_path, ohne=("funktionen",))
    assert "funktionen" not in [e["id"] for e in doku.verfuegbar(root)]
    assert doku.eintrag_fuer("FUNKTIONEN.md", root) is None

    _datei(root, "docs/FUNKTIONEN.md", _seite("Funktionen"))

    assert "funktionen" in [e["id"] for e in doku.verfuegbar(root)]
    assert doku.eintrag_fuer("FUNKTIONEN.md", root)["id"] == "funktionen"


def test_ein_ordner_statt_einer_datei_zaehlt_als_fehlend(tmp_path):
    from app import doku

    root = _projekt(tmp_path, ohne=("anleitung",))
    (root / "docs" / "ANLEITUNG.md").mkdir()

    assert "anleitung" not in [e["id"] for e in doku.verfuegbar(root)]
    assert doku.eintrag_fuer("anleitung", root) is None


def test_leerer_projektordner_liefert_nichts(tmp_path):
    from app import doku

    assert doku.verfuegbar(tmp_path) == []
    assert doku.eintrag_fuer("version", tmp_path) is None


def test_verfuegbar_und_eintrag_fuer_geben_kopien_zurueck(tmp_path):
    from app import doku

    root = _projekt(tmp_path)
    doku.verfuegbar(root)[0]["datei"] = "geaendert"
    doku.eintrag_fuer("anleitung", root)["datei"] = "geaendert"

    assert doku.KATALOG[0]["datei"] == "CHANGELOG.md"
    assert doku.eintrag_fuer("anleitung", root)["datei"] == "docs/ANLEITUNG.md"


def test_standard_root_wird_beim_aufruf_aufgeloest(tmp_path, monkeypatch):
    """Ohne Parameter gilt der Root zum Zeitpunkt des Aufrufs, nicht der beim Import (Lehre aus
    Phase 87: ein beim Import gebundener Standardwert wird in Tests zur Falle)."""
    from app import doku

    root = _projekt(tmp_path, gruppen=("kunde",), ohne=("funktionen",))
    monkeypatch.setattr(doku, "PROJECT_ROOT", root)

    assert [e["id"] for e in doku.verfuegbar()] == [
        i for i in SOLL_IDS if i not in INTERN and i != "funktionen"]
    eintrag = doku.eintrag_fuer("anleitung")
    assert eintrag["datei"] == "docs/ANLEITUNG.md"
    assert "Seite anleitung" in doku.rendern(eintrag)


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 3 — eintrag_fuer: Kennung, Dateiname, Fremdnamen
# ═══════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("name, erwartet", [
    # Kennung, Groß- und Kleinschreibung egal
    ("version", "version"), ("Version", "version"), ("VERSION", "version"),
    ("anleitung", "anleitung"), ("coach-site", "coach-site"), ("COACH-SITE", "coach-site"),
    # Dateiname, mit .md und mit .html (relative Links in einer gerenderten Doku)
    ("ANLEITUNG.html", "anleitung"), ("ANLEITUNG.md", "anleitung"),
    ("anleitung.HTML", "anleitung"), ("Anleitung.Md", "anleitung"),
    ("CHANGELOG.md", "version"), ("changelog.html", "version"),
    ("BMS_Install_MAC.md", "installation"), ("BMS_Install_MAC.html", "installation"),
    ("bms_install_mac.MD", "installation"), ("BMS_Install_Windows.md", "installation"),
    ("BMS_Install_Windows.html", "installation"), ("bms_install_windows.HTML", "installation"),
    ("SETUP-EMAIL.html", "email"), ("SETUP-WINDOWS.md", "windows"),
    ("ANLEITUNG_COACH_SITE.html", "coach-site"), ("BEIRAT-CHARTA.md", "beirat"),
    ("FUNKTIONEN.md", "funktionen"),
    ("DOKUMENTATION.md", "technik"), ("AUTOMATION.html", "automatik"), ("RELEASE.md", "release"),
    # „installation“ ist die Kennung der Installationsanleitung (BMS_Install_MAC.md bzw.
    # BMS_Install_Windows.md). INSTALLATION.md ist die Entwickler-Installation: Der Punkt trennt
    # Kennung und Dateiname.
    ("installation", "installation"), ("INSTALLATION", "installation"),
    ("INSTALLATION.md", "entwicklung"), ("installation.html", "entwicklung"),
])
def test_aufloesung_ueber_kennung_und_dateiname(tmp_path, name, erwartet):
    from app import doku

    root = _projekt(tmp_path)

    eintrag = doku.eintrag_fuer(name, root)

    assert eintrag is not None, name
    assert eintrag["id"] == erwartet
    assert eintrag in doku.KATALOG


def test_jeder_katalogeintrag_ist_ueber_kennung_und_beide_dateinamen_erreichbar(tmp_path):
    from app import doku

    root = _projekt(tmp_path)
    for e in doku.KATALOG:
        dateiname = PurePosixPath(e["datei"]).name
        html = PurePosixPath(e["datei"]).with_suffix(".html").name
        for name in (e["id"], dateiname, html, dateiname.upper(), html.lower()):
            assert doku.eintrag_fuer(name, root) == e, (e["id"], name)


# ── Reiter „Installation & Updates“ je System (P2-71, Paket K) ───────────────────────────────
# Das System kommt als Parameter (`systemname`, ein Wert von `os.name`): Beide Fälle laufen auf
# jedem Rechner, ohne `os.name` umzubiegen (pathlib verzweigt selbst darauf, s. Phase 71D).
MAC_DATEI = "BMS_Install_MAC.md"
WINDOWS_DATEI = "BMS_Install_Windows.md"
SYSTEME = [pytest.param("nt", WINDOWS_DATEI, id="windows"),
           pytest.param("posix", MAC_DATEI, id="macos-linux"),
           pytest.param("java", MAC_DATEI, id="sonstiges")]


@pytest.mark.parametrize("system, erwartet", SYSTEME)
def test_installation_zeigt_die_anleitung_des_systems(tmp_path, system, erwartet):
    from app import doku

    root = _projekt(tmp_path)

    assert doku.installationsdatei(system) == erwartet
    eintrag = doku.eintrag_fuer("installation", root, system)
    assert eintrag == {"id": "installation", "titel": "Installation & Updates",
                       "gruppe": "kunde", "datei": erwartet}
    liste = {e["id"]: e for e in doku.verfuegbar(root, system)}
    assert liste["installation"] == eintrag
    # Die Seite kommt aus der Datei dieses Systems (die Testdatei nennt ihren Namen im Text).
    seite = doku.rendern(eintrag, root)
    andere = WINDOWS_DATEI if erwartet == MAC_DATEI else MAC_DATEI
    assert f"Anleitung {erwartet}" in seite and f"Anleitung {andere}" not in seite


def test_nur_der_installationsreiter_unterscheidet_die_systeme(tmp_path):
    from app import doku

    root = _projekt(tmp_path)
    unter_windows = doku.verfuegbar(root, "nt")
    unter_mac = doku.verfuegbar(root, "posix")

    assert [e["id"] for e in unter_windows] == [e["id"] for e in unter_mac] == SOLL_IDS
    abweichend = [(w["id"], w["datei"], m["datei"]) for w, m in zip(unter_windows, unter_mac) if w != m]
    assert abweichend == [("installation", WINDOWS_DATEI, MAC_DATEI)]


def test_ohne_angabe_gilt_das_laufende_system(tmp_path):
    """Ohne `systemname` entscheidet `os.name` beim Aufruf. Hier wird er nur gelesen."""
    import os

    from app import doku

    root = _projekt(tmp_path)
    erwartet = WINDOWS_DATEI if os.name == "nt" else MAC_DATEI

    assert doku.installationsdatei() == erwartet
    assert doku.eintrag_fuer("installation", root)["datei"] == erwartet
    assert {e["id"]: e["datei"] for e in doku.verfuegbar(root)}["installation"] == erwartet
    assert {e["id"]: e["datei"] for e in doku.KATALOG}["installation"] == erwartet


@pytest.mark.parametrize("system, erwartet", SYSTEME)
@pytest.mark.parametrize("name", [
    "BMS_Install_MAC.md", "BMS_Install_MAC.html", "bms_install_mac.MD", "BMS_INSTALL_MAC.Html",
    "BMS_Install_Windows.md", "BMS_Install_Windows.html", "bms_install_windows.HTML",
])
def test_beide_anleitungen_fuehren_in_jedem_system_auf_den_reiter(tmp_path, name, system, erwartet):
    """Ein Link auf die Anleitung des anderen Systems (etwa aus der Windows-Doku) löst nicht ins
    Leere auf, sondern zeigt den Reiter mit der Anleitung dieses Systems."""
    from app import doku

    root = _projekt(tmp_path)

    eintrag = doku.eintrag_fuer(name, root, system)

    assert eintrag is not None, name
    assert eintrag["id"] == "installation" and eintrag["datei"] == erwartet


@pytest.mark.parametrize("system", ["nt", "posix"])
@pytest.mark.parametrize("name", [
    "BMS_Install.md", "BMS_Install.html", "bms_install.MD", "BMS_Install_Auto.md",
    "BMS_Install_Auto.html", "BMS_INSTALL_AUTO.Md",
    # ohne Endung ist es weder Kennung noch Dateiname
    "BMS_Install", "BMS_Install_Auto", "BMS_Install_MAC", "BMS_Install_Windows",
])
def test_alte_anleitungsnamen_loesen_nicht_mehr_auf(tmp_path, name, system):
    """Die früheren Namen sind unbekannt, AUCH wenn die Dateien noch im Ordner liegen (ein Kunde
    mit einer alten Installation hat sie bis zum Update): Aufgelöst wird nur über den Katalog."""
    from app import doku

    root = _projekt(tmp_path)
    _datei(root, "BMS_Install.md", _seite("Alt"))
    _datei(root, "BMS_Install_Auto.md", _seite("Alt Auto"))

    assert doku.eintrag_fuer(name, root, system) is None


def test_fehlt_die_datei_des_systems_ist_der_reiter_dort_unbekannt(tmp_path):
    from app import doku

    root = _projekt(tmp_path)
    root.joinpath(WINDOWS_DATEI).unlink()

    assert doku.eintrag_fuer("installation", root, "nt") is None
    assert doku.eintrag_fuer(WINDOWS_DATEI, root, "nt") is None
    assert "installation" not in [e["id"] for e in doku.verfuegbar(root, "nt")]
    # Das andere System ist davon nicht betroffen, und der Windows-Name führt dort auf dessen Reiter.
    assert doku.eintrag_fuer("installation", root, "posix")["datei"] == MAC_DATEI
    assert doku.eintrag_fuer("BMS_Install_Windows.html", root, "posix")["datei"] == MAC_DATEI


def test_rendern_nimmt_die_eintraege_beider_systeme_und_nichts_anderes(tmp_path):
    from app import doku

    root = _projekt(tmp_path)
    _datei(root, "BMS_Install.md", _seite("Alt"))
    for system, datei in (("nt", WINDOWS_DATEI), ("posix", MAC_DATEI)):
        assert f"Anleitung {datei}" in doku.rendern(doku.eintrag_fuer("installation", root, system), root)

    for gefaelscht in ({"id": "installation", "titel": "Installation & Updates", "gruppe": "kunde",
                        "datei": "BMS_Install.md"},
                       {"id": "installation", "titel": "Installation & Updates", "gruppe": "kunde",
                        "datei": "../BMS_Install_MAC.md"}):
        with pytest.raises(ValueError):
            doku.rendern(gefaelscht, root)


FREMDNAMEN = [
    pytest.param("", id="leer"),
    pytest.param(" ", id="leerzeichen"),
    ".", "..", "...",
    "../CHANGELOG.md", "../ausserhalb.md", "..\\ausserhalb.md", "..%2fausserhalb.md",
    "docs/ANLEITUNG.md", "docs\\ANLEITUNG.md", "/docs/ANLEITUNG.md", "./ANLEITUNG.md",
    "ANLEITUNG.md/", "/etc/passwd", "C:\\Windows\\win.ini", "%2e%2e",
    "ANLEITUNG.txt", "ANLEITUNG.pdf", "ANLEITUNG.md.bak", "ANLEITUNG.", ".md", "ANLEITUNG .md",
    " anleitung", "anleitung ", "anleitung\n", "anleitung\x00", "anleitung\x00.md",
    "unbekannt", "technik.md", "email.html",
    # Dateien, die im Projekt liegen, aber nicht im Katalog stehen
    "GEHEIM.md", "geheim", "COACH_SITE.md", "COACH_SITE.html", "README.md", "README",
    "BEIRAT-PERSONA-TEMPLATE.md", "WAS_IST_NEU.html", "ausserhalb.md",
    # der ausgebaute Reiter „Lizenz“ (P2-82): Kennung und Dateiname, auch wenn docs/LIZENZ.md noch liegt
    "lizenz", "Lizenz", "LIZENZ.md", "LIZENZ.html", "lizenz.MD",
    # die früheren Anleitungsnamen (P2-71): nur der Katalog gilt, auch wenn Dateien so heißen
    "BMS_Install.md", "BMS_Install.html", "BMS_Install_Auto.md", "BMS_Install_Auto.html",
    # Nicht-ASCII: Das Kleinschreiben würde sonst einen Treffer erzeugen (Kelvin-Zeichen wird k)
    pytest.param("technik".replace("k", "\u212a"), id="kelvin-zeichen"),
    pytest.param("RELEA\u017fE", id="langes-s"),
    pytest.param("\uff21\uff2e\uff2c\uff25\uff29\uff34\uff35\uff2e\uff27.md", id="vollbreite"),
    pytest.param("ANLEITUNG" + "x" * 5000, id="sehr-lang"),
]


@pytest.mark.parametrize("name", FREMDNAMEN)
def test_fremdnamen_sind_unbekannt_auch_wenn_die_datei_existiert(tmp_path, name):
    """Auflösung nur über die Katalogliste: Kein Name wird je als Pfad benutzt."""
    from app import doku

    root = _projekt(tmp_path)

    assert doku.eintrag_fuer(name, root) is None


@pytest.mark.parametrize("name", [None, 42, b"anleitung", ["anleitung"]])
def test_namen_die_keine_zeichenkette_sind_bleiben_unbekannt(tmp_path, name):
    from app import doku

    assert doku.eintrag_fuer(name, _projekt(tmp_path)) is None


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 4 — rendern
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_rendern_liefert_eine_vollstaendige_seite_mit_dem_titel_der_datei(tmp_path):
    from app import doku

    root = _projekt(tmp_path)
    eintraege = doku.verfuegbar(root)
    assert len(eintraege) == len(SOLL_IDS)
    for e in eintraege:
        seite = doku.rendern(e, root)
        assert seite.startswith("<!doctype html>"), e["id"]
        assert f"<h1>Seite {e['id']}</h1>" in seite, e["id"]
        assert f"<title>Seite {e['id']}</title>" in seite, e["id"]
        assert f"Text zu Seite {e['id']}." in seite, e["id"]


def test_rendern_liest_nur_katalogeintraege(tmp_path):
    from app import doku

    root = _projekt(tmp_path)
    anleitung = doku.eintrag_fuer("anleitung", root)
    fremd = {"id": "geheim", "titel": "Geheim", "gruppe": "kunde", "datei": "docs/GEHEIM.md"}
    umgebogen = dict(anleitung, datei="docs/GEHEIM.md")
    ausserhalb = dict(anleitung, datei="../ausserhalb.md")
    mit_zusatz = dict(anleitung, zusatz="x")

    for eintrag in (fremd, umgebogen, ausserhalb, mit_zusatz, {}):
        with pytest.raises(ValueError):
            doku.rendern(eintrag, root)
    # Der unveränderte Eintrag geht
    assert "Seite anleitung" in doku.rendern(anleitung, root)


def test_rendern_wirft_oserror_wenn_die_datei_fehlt(tmp_path):
    from app import doku

    with pytest.raises(OSError):
        doku.rendern(dict(doku.KATALOG[2]), tmp_path)


def test_externe_links_oeffnen_im_neuen_tab_alle_anderen_nicht(tmp_path):
    """Ein Klick auf eine Webadresse lädt sonst die fremde Seite in den Rahmen der Dokumentation,
    und viele Seiten verbieten das Einbetten. Relative Links auf andere Dokumente, Sprünge
    innerhalb der Seite und Mail-Adressen bleiben unberührt."""
    from app import doku

    root = _projekt(tmp_path)
    _datei(root, "docs/ANLEITUNG.md", "# Links\n\n## Abschnitt\n\n"
           "[Python](https://www.python.org/downloads/) und [Alt](http://beispiel.de/x?a=1&b=2), "
           "<https://example.org/auto>, [Eigenes Ziel](https://example.com/z){: target=\"_self\" }.\n\n"
           "[Anleitung](SETUP-EMAIL.html), [Datei](BMS_Install_MAC.md), [Sprung](#abschnitt), "
           "[Mail](mailto:info@example.com).\n")

    seite = doku.rendern(doku.eintrag_fuer("anleitung", root), root)
    anker = re.findall(r"<a\b[^>]*>", seite)

    extern = [a for a in anker if re.search(r'href="https?://', a)]
    intern = [a for a in anker if a not in extern]
    assert len(extern) == 4 and len(intern) == 4, anker
    for a in extern:
        assert a.count("target=") == 1, a
    unveraendert = [a for a in extern if 'target="_self"' in a]
    assert len(unveraendert) == 1 and "_blank" not in unveraendert[0], "vorhandenes Ziel bleibt"
    for a in (x for x in extern if x not in unveraendert):
        assert 'target="_blank"' in a and 'rel="noopener noreferrer"' in a, a
    for a in intern:
        assert "target=" not in a and "rel=" not in a, a


CHANGELOG_LEER = ("# Änderungen\n\nEinleitung.\n\n## Unveröffentlicht\n\n"
                  "## 1.1.3 (29.09.2026)\n\n- Punkt A.\n\n## 1.0.0 (28.09.2026)\n\n- Punkt B.\n")
CHANGELOG_OFFEN = CHANGELOG_LEER.replace("## Unveröffentlicht\n\n", "## Unveröffentlicht\n\n- Neuer Punkt.\n\n")


def test_leerer_abschnitt_unveroeffentlicht_steht_nicht_als_leere_karte_da(tmp_path):
    """Nach jeder Freigabe bleibt „Unveröffentlicht“ als leere Überschrift im CHANGELOG. Der
    Renderer machte daraus eine leere Karte an erster Stelle, die jeder Kunde zuerst sähe."""
    from app import doku

    root = _projekt(tmp_path)
    _datei(root, "CHANGELOG.md", CHANGELOG_LEER)

    seite = doku.rendern(doku.eintrag_fuer("version", root), root)

    assert "Unveröffentlicht" not in seite
    assert seite.count('<section class="card">') == 2
    assert seite.index("1.1.3 (29.09.2026)") < seite.index("1.0.0 (28.09.2026)")
    assert "Punkt A." in seite and "Punkt B." in seite and "Einleitung." in seite


def test_unveroeffentlicht_am_ende_der_datei_wird_ebenfalls_entfernt(tmp_path):
    from app import doku

    root = _projekt(tmp_path)
    _datei(root, "CHANGELOG.md", "# Änderungen\n\n## 1.0.0 (28.09.2026)\n\n- Punkt B.\n\n## Unveröffentlicht\n")

    seite = doku.rendern(doku.eintrag_fuer("version", root), root)

    assert "Unveröffentlicht" not in seite and "Punkt B." in seite


def test_gefuellter_abschnitt_unveroeffentlicht_bleibt_zuerst(tmp_path):
    """In der Entwicklungsinstallation steht dort, was mit der nächsten Freigabe kommt."""
    from app import doku

    root = _projekt(tmp_path)
    _datei(root, "CHANGELOG.md", CHANGELOG_OFFEN)

    seite = doku.rendern(doku.eintrag_fuer("version", root), root)

    assert seite.index("Unveröffentlicht") < seite.index("Neuer Punkt.") < seite.index("1.1.3 (29.09.2026)")
    assert seite.count('<section class="card">') == 3


def test_nur_das_changelog_verliert_einen_leeren_abschnitt(tmp_path):
    from app import doku

    root = _projekt(tmp_path)
    _datei(root, "docs/ANLEITUNG.md", "# Anleitung\n\n## Unveröffentlicht\n\n## Weiter\n\nText.\n")

    seite = doku.rendern(doku.eintrag_fuer("anleitung", root), root)

    assert "<h2>Unveröffentlicht</h2>" in seite


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 5 — Router
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_liste_hat_genau_kennung_titel_und_gruppe(tmp_path, monkeypatch):
    root = _projekt(tmp_path, ohne=("funktionen",))
    client = _client(monkeypatch, root)

    antwort = client.get("/api/doku")

    assert antwort.status_code == 200
    eintraege = antwort.json()
    assert [e["id"] for e in eintraege] == [i for i in SOLL_IDS if i != "funktionen"]
    for e in eintraege:
        assert set(e) == {"id", "titel", "gruppe"}, "keine Dateipfade nach außen"
        assert e["titel"] == SOLL_TITEL[e["id"]]
        assert e["gruppe"] == ("intern" if e["id"] in INTERN else "kunde")


def test_liste_ohne_interne_dateien_hat_nur_kundentabs(tmp_path, monkeypatch):
    client = _client(monkeypatch, _projekt(tmp_path, gruppen=("kunde",)))

    gruppen = {e["gruppe"] for e in client.get("/api/doku").json()}

    assert gruppen == {"kunde"}


def test_seite_ist_html_mit_dem_titel_der_datei(tmp_path, monkeypatch):
    client = _client(monkeypatch, _projekt(tmp_path))

    antwort = client.get("/api/doku/anleitung")

    assert antwort.status_code == 200
    assert antwort.headers["content-type"].startswith("text/html")
    assert "<h1>Seite anleitung</h1>" in antwort.text
    assert "<title>Seite anleitung</title>" in antwort.text


def test_seite_traegt_genau_den_berichtskopf_von_main(tmp_path, monkeypatch):
    """Dieselbe Sandbox wie die Berichte (P2-58), aus derselben Quelle: `main._BERICHT_KOPF`. Der
    Test prüft Gleichheit je Header und Einmaligkeit, nicht bloß Anwesenheit (Lektion P2-44)."""
    import app.main as main

    client = _client(monkeypatch, _projekt(tmp_path))
    assert set(main._BERICHT_KOPF) == {"Content-Security-Policy", "Cache-Control"}

    antwort = client.get("/api/doku/anleitung")

    assert antwort.status_code == 200
    for name, wert in main._BERICHT_KOPF.items():
        assert antwort.headers.get_list(name) == [wert], name
    teile = antwort.headers["content-security-policy"].split()
    assert teile[0] == "sandbox" and "allow-same-origin" not in teile


@pytest.mark.parametrize("name", ["version", "ANLEITUNG.html", "ANLEITUNG.md", "BMS_Install_MAC.md",
                                  "BMS_Install_Windows.html", "installation", "INSTALLATION.html",
                                  "technik", "Release"])
def test_jede_aufloesbare_form_traegt_den_kopf(tmp_path, monkeypatch, name):
    import app.main as main

    client = _client(monkeypatch, _projekt(tmp_path))

    antwort = client.get(f"/api/doku/{name}")

    assert antwort.status_code == 200, name
    assert antwort.headers.get_list("content-security-policy") == [main._BERICHT_SANDBOX]
    assert antwort.headers.get_list("cache-control") == ["no-cache"]


def test_dateiname_und_kennung_liefern_dieselbe_seite(tmp_path, monkeypatch):
    """Relative Links innerhalb einer gerenderten Doku (`SETUP-EMAIL.html`) lösen zu
    /api/doku/SETUP-EMAIL.html auf und müssen dieselbe Seite zeigen wie der Tab."""
    client = _client(monkeypatch, _projekt(tmp_path))

    ueber_kennung = client.get("/api/doku/email").text

    for name in ("SETUP-EMAIL.html", "SETUP-EMAIL.md", "setup-email.HTML"):
        assert client.get(f"/api/doku/{name}").text == ueber_kennung, name
    # INSTALLATION.html ist die Entwickler-Installation, die Kennung „installation“ die Anleitung
    # des laufenden Systems (BMS_Install_MAC.md bzw. BMS_Install_Windows.md), unter beiden Namen.
    assert "Seite entwicklung" in client.get("/api/doku/INSTALLATION.html").text
    ueber_kennung = client.get("/api/doku/installation").text
    assert "Seite installation" in ueber_kennung
    for name in ("BMS_Install_MAC.html", "BMS_Install_MAC.md", "BMS_Install_Windows.html",
                 "bms_install_windows.MD"):
        assert client.get(f"/api/doku/{name}").text == ueber_kennung, name


@pytest.mark.parametrize("name", ["BMS_Install.md", "BMS_Install.html", "BMS_Install_Auto.md",
                                  "BMS_Install_Auto.html"])
def test_alte_anleitungsnamen_antworten_404_auch_wenn_die_datei_noch_da_liegt(tmp_path, monkeypatch, name):
    root = _projekt(tmp_path)
    _datei(root, "BMS_Install.md", _seite("Alt"))
    _datei(root, "BMS_Install_Auto.md", _seite("Alt Auto"))
    client = _client(monkeypatch, root)

    assert client.get(f"/api/doku/{name}").status_code == 404


@pytest.mark.parametrize("name", [
    "unbekannt", "GEHEIM.md", "geheim", "COACH_SITE.html", "README.md", "BEIRAT-PERSONA-TEMPLATE.md",
    "lizenz", "LIZENZ.md", "LIZENZ.html",
    "technik.md", "ANLEITUNG.txt", "ANLEITUNG.md.bak", "ausserhalb.md",
    "%2e%2e", "..%2fausserhalb.md", "..%5causserhalb.md", "docs%2fANLEITUNG.md", "%2fetc%2fpasswd",
    "docs/ANLEITUNG.md", "anleitung%00", "anleitung%0a", "anleitung%20",
    pytest.param("ANLEITUNG" + "x" * 3000, id="sehr-lang"),
])
def test_fremde_namen_antworten_404_und_nie_mit_einem_dokument(tmp_path, monkeypatch, name):
    """Die Dateien liegen im tmp-Projekt (auch eine außerhalb des Roots): Sie sind da, aber nicht
    im Katalog, also gibt es sie nicht."""
    client = _client(monkeypatch, _projekt(tmp_path))

    antwort = client.get(f"/api/doku/{name}")

    assert antwort.status_code == 404, name
    assert antwort.headers["content-type"].startswith("application/json")
    assert "content-security-policy" not in antwort.headers
    assert "nicht im Katalog" not in antwort.text and "nicht im Projekt" not in antwort.text


def test_unbekannter_name_nennt_den_kundentext(tmp_path, monkeypatch):
    client = _client(monkeypatch, _projekt(tmp_path))

    assert client.get("/api/doku/unbekannt").json() == {"detail": "Dokument nicht gefunden"}
    assert client.get("/api/doku/GEHEIM.md").json() == {"detail": "Dokument nicht gefunden"}


def test_interner_eintrag_ohne_datei_antwortet_404(tmp_path, monkeypatch):
    """Im Kundenpaket fehlen die internen Dateien: Der Tab steht nicht in der Liste, und die
    Adresse antwortet 404 statt eines Fehlers."""
    client = _client(monkeypatch, _projekt(tmp_path, gruppen=("kunde",)))

    for kennung in INTERN:
        assert client.get(f"/api/doku/{kennung}").status_code == 404, kennung
    assert client.get("/api/doku/DOKUMENTATION.md").status_code == 404
    assert client.get("/api/doku/anleitung").status_code == 200


def test_datei_zwischen_pruefung_und_lesen_verschwunden_antwortet_404(tmp_path, monkeypatch):
    from app import doku

    client = _client(monkeypatch, _projekt(tmp_path))

    def weg(eintrag, projekt_root=None):
        raise FileNotFoundError("weg")

    monkeypatch.setattr(doku, "rendern", weg)

    antwort = client.get("/api/doku/anleitung")

    assert antwort.status_code == 404
    assert antwort.json() == {"detail": "Dokument nicht gefunden"}


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 6 — echte Dokumente, Rahmen der Oberfläche
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_echte_dokumente_des_projekts_lassen_sich_rendern():
    """Alle Katalogdateien, die es im Repository gibt, sind UTF-8 und werden zu einer Seite. Die
    Kerndokumente müssen da sein: Verschwindet eines (umbenannt, verschoben), fehlte sein Tab still."""
    from app import doku

    echte = doku.verfuegbar()
    assert {"version", "anleitung", "installation", "email", "windows", "coach-site",
            "beirat"} <= {e["id"] for e in echte}
    for e in echte:
        seite = doku.rendern(e)
        assert seite.startswith("<!doctype html>"), e["id"]
        assert re.search(r"<h1>.+</h1>", seite), e["id"]
        assert re.search(r"<title>.+</title>", seite), e["id"]
        assert "<section class=\"card\">" in seite, e["id"]


def test_echte_webadressen_in_den_dokumenten_oeffnen_im_neuen_tab():
    """Die Windows-Anleitung verlinkt mehrere Webseiten (python.org, nodejs.org, ...)."""
    from app import doku

    eintrag = doku.eintrag_fuer("windows")
    assert eintrag is not None
    anker = re.findall(r"<a\b[^>]*>", doku.rendern(eintrag))
    extern = [a for a in anker if re.search(r'href="https?://', a)]

    assert extern
    for a in extern:
        assert 'target="_blank"' in a and 'rel="noopener noreferrer"' in a, a


def test_rahmen_der_oberflaeche_bleibt_in_der_sandbox():
    """Die Seite wird in einem iframe gezeigt. Ein `allow-same-origin` zusammen mit Skripten
    höbe die Sandbox auf (das Dokument bekäme den Ursprung der API zurück): Die Liste der Rechte
    ist deshalb genau festgelegt, und der Rahmen zeigt nur auf /api/doku/."""
    from app import doku

    quelle = doku.PROJECT_ROOT.joinpath("frontend", "src", "pages", "Dokumentation.tsx").read_text(encoding="utf-8")

    rahmen = re.findall(r"<iframe\b[^>]*>", quelle)
    assert len(rahmen) == 1, "genau ein Rahmen in der Dokumentationsseite"
    sandbox = re.search(r'sandbox="([^"]*)"', rahmen[0])
    assert sandbox, "der Rahmen braucht ein sandbox-Attribut"
    assert set(sandbox.group(1).split()) == {"allow-popups", "allow-popups-to-escape-sandbox"}
    assert "/api/doku/" in rahmen[0]


def test_router_ist_in_der_app_eingebunden(client):
    """Verdrahtung in `main.py` (P2-59): Die echte App beantwortet `/api/doku*` selbst. Fehlte
    `include_router`, fiele `/api/doku/<name>` an den Catch-all der Oberfläche und käme als
    index.html mit 200 zurück, ohne Sandbox-Kopf."""
    import app.main as main

    liste = client.get("/api/doku")
    assert liste.status_code == 200
    assert "anleitung" in {e["id"] for e in liste.json()}

    seite = client.get("/api/doku/anleitung")
    assert seite.status_code == 200
    assert seite.headers["content-type"].startswith("text/html")
    for name, wert in main._BERICHT_KOPF.items():
        assert seite.headers[name] == wert

    assert client.get("/api/doku/unbekannt").status_code == 404
