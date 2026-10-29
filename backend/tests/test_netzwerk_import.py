"""Tests für P2-62, Paket I: Netzwerk-Listen per Datei importieren (`app/netzwerk_import.py`,
`app/routes_netzwerk_import.py`).

Alles läuft unter `tmp_path`: eigene SQLite-Datei je Test mit denselben UNIQUE-Indizes wie `init_db()`
und ein eigener Datenordner für die Sicherung. `app.db.engine`, `DATA_DIR` und `DB_PATH` werden per
`monkeypatch` umgebogen, denn die Sicherung und der Router lösen sie erst zur Laufzeit auf; so läuft
keine Sicherung gegen echte Pfade. Excel-Dateien entstehen im Test mit openpyxl. Beispieldaten sind
erfunden (Mailadressen nur unter beispiel.de, keine echten Firmen oder Personen).

Die Tests sind gegen den Vertrag der Bau-Spec (`tasks/spec_p2-62_netzwerk_import.md`, V1 bis V7)
geschrieben: Ein roter Test entscheidet zugunsten der Spec. Drei Regeln tragen besonderes Gewicht und
haben je einen Test, der ohne sie rot wird: in der App gelöschte Einträge bleiben gelöscht, gefüllte
Felder werden nie überschrieben, und der Import setzt kein `next_action_date`.

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention). Windows-CI: pathlib,
Verbindungen werden geschlossen (`engine.dispose()`), keine Rechte-Prüfungen.
"""
import ast
import io
import re
import sqlite3
import zipfile
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJEKT_DIR = BACKEND_DIR.parent

MB5 = 5 * 1024 * 1024
SICHERUNG_LAEUFT_TEXT = "Es läuft gerade eine Sicherung. Bitte versuchen Sie es gleich noch einmal."
FIRMA_FEHLT_TEXT = "Keine Spalte für die Firma gefunden. Erwartet wird zum Beispiel „Firma“."
HEADHUNTER_SPALTE_FEHLT_TEXT = ("Keine Spalte für die Firma oder den Ansprechpartner gefunden. Erwartet "
                                "wird zum Beispiel „Firma“ oder „Ansprechpartner“.")
NAME_FEHLT_TEXT = ("Keine Spalte für den Namen gefunden. Erwartet wird zum Beispiel „Name“ oder "
                   "„Vorname“ und „Nachname“.")
LINKEDIN_HINWEIS = ("LinkedIn-Exporte enthalten alle Verbindungen. Die Liste Netzwerk-Kontakte ist für "
                    "Kontakte gedacht, die Sie aktiv pflegen. Löschen Sie vorher Zeilen, die Sie dort "
                    "nicht brauchen.")

# Vertrag V4 (Spalten je Liste), Reihenfolge wie in der Spec: erster Name = Name in der Vorlage.
V4 = {
    "zielfirmen": {
        "company": ("Firma", "Company", "Unternehmen", "Zielfirma", "Name"),
        "industry": ("Branche", "Industry"),
        "size_ma": ("Größe (MA)", "Mitarbeiter", "Größe", "Size", "Employees"),
        "revenue": ("Umsatz", "Revenue"),
        "location_hq": ("HQ", "Hauptsitz", "Standort", "Location", "Ort"),
        "ownership": ("Eigentümer", "Ownership", "Eigentum"),
        "tier": ("Tier", "Stufe"),
        "scenario": ("Szenario", "Scenario"),
        "key_contact": ("Key Contact", "Ansprechpartner", "Kontakt"),
        "connection_status": ("Status", "Connection Status", "Verbindung"),
        "website": ("Webseite", "Website", "Homepage", "URL"),
        "karriere_url": ("Karriereseite", "Karriere-URL", "Career URL", "Jobs"),
        "wachstumssignal": ("Wachstumssignal", "Growth Signal"),
        "ki_readiness": ("KI-Readiness", "AI Readiness"),
        "einschaetzung": ("Einschätzung", "Bewertung", "Assessment"),
        "ranking": ("Ranking", "Rang"),
        "last_update": ("Letzte Aktualisierung", "Last Update", "Stand"),
    },
    "headhunter": {
        "firma": ("Firma", "Company", "Unternehmen", "Agentur", "Personalberatung"),
        "ansprechpartner": ("Ansprechpartner", "Kontakt", "Name", "Contact", "Berater"),
        "fokus": ("Fokus", "Focus", "Schwerpunkt"),
        "region": ("Region",),
        "kanal": ("Kanal", "Channel"),
        "linkedin_gefolgt": ("LinkedIn gefolgt", "LinkedIn"),
        "letzter_kontakt": ("Letzter Kontakt", "Last Contact"),
        "status": ("Status",),
        "webseite": ("Webseite", "Website", "URL", "Homepage"),
        "notizen": ("Notizen", "Notes", "Notiz", "Bemerkung"),
    },
    "kontakte": {
        "name": ("Name", "Full Name", "Kontakt"),
        "vorname": ("Vorname", "First Name"),
        "nachname": ("Nachname", "Last Name"),
        "beziehung": ("Beziehung", "Relationship"),
        "unternehmen": ("Unternehmen", "Firma", "Company", "Arbeitgeber"),
        "rolle": ("Rolle", "Position", "Funktion", "Title", "Job Title"),
        "prioritaet": ("Priorität", "Priority"),
        "letzter_kontakt": ("Letzter Kontakt", "Last Contact"),
        "kanal": ("Kanal", "Channel"),
        "next_action": ("Nächste Aktion", "Next Action"),
        "next_action_date": ("Fällig am", "Fällig", "Next Action Date", "Due"),
        "notizen": ("Notizen", "Notes", "Notiz", "Bemerkung"),
    },
}
# Spaltennamen der Vorlagen (V1): nur Felder mit Vorlagen-Namen, Pflichtspalten zuerst.
VORLAGE_KOPF = {
    "zielfirmen": ["Firma", "Branche", "Größe (MA)", "Umsatz", "HQ", "Eigentümer", "Tier", "Szenario",
                   "Key Contact", "Status", "Webseite", "Karriereseite", "Wachstumssignal",
                   "KI-Readiness", "Einschätzung", "Ranking", "Letzte Aktualisierung"],
    "headhunter": ["Firma", "Ansprechpartner", "Fokus", "Region", "Kanal", "LinkedIn gefolgt",
                   "Letzter Kontakt", "Status", "Webseite", "Notizen"],
    "kontakte": ["Name", "Beziehung", "Unternehmen", "Rolle", "Priorität", "Letzter Kontakt", "Kanal",
                 "Nächste Aktion", "Fällig am", "Notizen"],
}
DATEINAME = {"zielfirmen": "Zielfirmen", "headhunter": "Headhunter", "kontakte": "Netzwerk-Kontakte"}
MODELL = {"zielfirmen": "TargetCompany", "headhunter": "Headhunter", "kontakte": "NetworkContact"}
# Kopfzeilen der drei Export-Blätter von `pipeline/export_excel.py` (Ausgangslage der Spec).
EXPORT_KOEPFE = {
    "kontakte": ["Name", "Beziehung", "Unternehmen", "Rolle", "Priorität", "Letzter Kontakt", "Kanal",
                 "Nächste Aktion", "Fällig am", "Notizen"],
    "headhunter": ["Firma", "Ansprechpartner", "Fokus", "Region", "Status", "Letzter Kontakt",
                   "Webseite", "Notizen"],
    "zielfirmen": ["Company", "Branche", "Größe (MA)", "HQ", "Tier", "Szenario", "Key Contact",
                   "Status", "Karriereseite", "Wachstumssignal", "Einschätzung"],
}
EXPORT_BLATT = {"kontakte": "Netzwerk", "headhunter": "Headhunter", "zielfirmen": "Zielfirmen"}


# ── Fixtures und Helfer ──────────────────────────────────────────────────────────────────────
@pytest.fixture()
def ni():
    from app import netzwerk_import

    return netzwerk_import


@pytest.fixture(scope="module")
def _schema_vorlage(tmp_path_factory):
    """Das leere Schema EINMAL je Modul als Datei; jeder Test kopiert sie. Vorher baute jeder der
    rund 340 Tests das Schema selbst: Unter Windows schreibt jede CREATE-Anweisung einzeln auf die
    Platte (und der Virenscanner prüft jede neue Datei), der CI-Job brauchte dadurch rund 8 Minuten
    für diese Datei und lief in sein 15-Minuten-Limit (Abnahme P2-62). Lokal 7 s."""
    from sqlmodel import SQLModel, create_engine
    from app import db, models  # noqa: F401  (registriert alle Tabellen)

    pfad = tmp_path_factory.mktemp("schema") / "vorlage.sqlite"
    engine = create_engine(f"sqlite:///{pfad}", connect_args=db.CONNECT_ARGS)
    SQLModel.metadata.create_all(engine)
    with engine.connect() as verbindung:
        for name, tabelle, ausdruck in db._UNIQUE_INDEXES:
            verbindung.exec_driver_sql(f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON {tabelle}({ausdruck})")
        verbindung.commit()
    engine.dispose()
    return pfad


@pytest.fixture()
def umgebung(tmp_path, monkeypatch, _schema_vorlage):
    """Eigene Datenbank und eigener Datenordner je Test (Kopie der Schema-Vorlage). `app.db` zeigt für
    die Dauer des Tests darauf: Router (`get_session`) und Sicherung (`DATA_DIR`) lösen beides erst
    beim Aufruf auf."""
    import shutil

    from sqlmodel import create_engine
    from app import db

    daten = tmp_path / "daten"
    daten.mkdir()
    shutil.copyfile(_schema_vorlage, daten / "bewerbung.sqlite")
    engine = create_engine(f"sqlite:///{daten / 'bewerbung.sqlite'}", connect_args=db.CONNECT_ARGS)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "DATA_DIR", daten)
    monkeypatch.setattr(db, "DB_PATH", daten / "bewerbung.sqlite")
    yield SimpleNamespace(daten=daten, engine=engine, tmp=tmp_path)
    engine.dispose()


@pytest.fixture()
def sitzung(umgebung):
    from sqlmodel import Session

    with Session(umgebung.engine) as s:
        yield s


def _csv(*zeilen, trenner=";", kodierung="utf-8-sig", ende="\r\n"):
    return ende.join(trenner.join(z) for z in zeilen).encode(kodierung)


def _xlsx(blaetter: dict) -> bytes:
    """Arbeitsmappe aus {Blattname: [Zeilen]}; eine leere Liste als Zeile ergibt eine Leerzeile."""
    import openpyxl

    arbeitsmappe = openpyxl.Workbook()
    arbeitsmappe.remove(arbeitsmappe.active)
    for name, zeilen in blaetter.items():
        blatt = arbeitsmappe.create_sheet(name)
        for zeile in zeilen:
            blatt.append(zeile)
    puffer = io.BytesIO()
    arbeitsmappe.save(puffer)
    return puffer.getvalue()


def _alle(u, modell):
    from sqlmodel import Session, select
    from app import models

    with Session(u.engine, expire_on_commit=False) as s:
        return s.exec(select(getattr(models, modell))).all()


def _stand(u):
    """Alles in den drei Listen, samt Zeitstempeln: Zwei gleiche Stände heißen, dass nichts geschrieben wurde."""
    return {m: sorted((z.model_dump() for z in _alle(u, m)), key=lambda d: d["id"]) for m in MODELL.values()}


def _anzahl(u, modell):
    return len(_alle(u, modell))


def _kontakt(u, name):
    treffer = [k for k in _alle(u, "NetworkContact") if k.name == name]
    assert len(treffer) == 1, f"{name}: {len(treffer)} Treffer"
    return treffer[0]


def _anlegen(u, modell, **felder):
    """Legt eine Zeile mit demselben Schlüssel an wie die Anlege-Endpunkte (`slug_parts`)."""
    from sqlmodel import Session
    from app import models
    from app.normalize import slug_parts

    teile = {"TargetCompany": ("company",), "Headhunter": ("firma", "ansprechpartner"),
             "NetworkContact": ("name", "unternehmen")}[modell]
    zeile = getattr(models, modell)(dedup_key=slug_parts(*(felder.get(t) for t in teile)), **felder)
    with Session(u.engine, expire_on_commit=False) as s:
        s.add(zeile)
        s.commit()
        s.refresh(zeile)
    return zeile


def _sicherungen(u):
    ordner = u.daten / "backups" / "auto"
    return sorted(p.name for p in ordner.glob("*.zip")) if ordner.is_dir() else []


def _tabelle_in_sicherung(u, dateiname, tabelle):
    """Anzahl der Zeilen einer Tabelle in der Sicherungsdatei (zeigt den Stand VOR dem Import)."""
    with zipfile.ZipFile(u.daten / "backups" / "auto" / dateiname) as archiv:
        ziel = u.tmp / f"entpackt_{dateiname}.sqlite"
        ziel.write_bytes(archiv.read("bewerbung.sqlite"))
    verbindung = sqlite3.connect(str(ziel))
    try:
        return verbindung.execute(f"SELECT COUNT(*) FROM {tabelle}").fetchone()[0]
    finally:
        verbindung.close()


# ── 1. Vertrag V4: Spalten und Konfiguration ─────────────────────────────────────────────────
def test_spaltenkonfiguration_entspricht_dem_vertrag_v4(ni):
    assert set(ni.LISTEN) == {"zielfirmen", "headhunter", "kontakte"}
    for kennung, erwartet in V4.items():
        ist = {f.name: (f.vorlage, *f.synonyme) for f in ni.LISTEN[kennung].felder}
        assert list(ist) == list(erwartet), kennung
        assert ist == erwartet, kennung


def test_kein_spaltenname_gehoert_zwei_feldern_derselben_liste(ni):
    for liste in ni.LISTEN.values():
        felder = liste.felder + (ni._LINKEDIN_ZUSATZ if liste.kennung == "kontakte" else ())
        gesehen = {}
        for feld in felder:
            for name in (feld.vorlage, *feld.synonyme):
                schluessel = ni._schluessel(name)
                assert schluessel not in gesehen, f"{liste.kennung}: {name} bei {feld.name} und {gesehen.get(schluessel)}"
                gesehen[schluessel] = feld.name


@pytest.mark.parametrize("text, erwartet", [
    ("Größe (MA)", "groessema"), ("GRÖSSE (MA)", "groessema"), ("Straße", "strasse"),
    ("Priorität", "prioritaet"), ("Nächste Aktion", "naechsteaktion"), ("KI-Readiness", "kireadiness"),
    ("Fällig am", "faelligam"), ("  Key   Contact ", "keycontact"), ("E-Mail", "email"),
    # „ü“ aus „u“ und Trema (macOS-Dateinamen und -Exporte)
    ("Eigentu\u0308mer", "eigentuemer"), (None, ""), ("###", ""),
])
def test_spaltenschluessel_normalisiert_wie_v4(ni, text, erwartet):
    assert ni._schluessel(text) == erwartet


def _spalten_test_daten():
    fälle = []
    for kennung, felder in V4.items():
        for feld, namen in felder.items():
            for name in namen:
                fälle.append((kennung, feld, name))
    return fälle


@pytest.mark.parametrize("kennung, feld, name", _spalten_test_daten())
def test_jedes_synonym_wird_erkannt_auch_in_anderer_schreibweise(ni, sitzung, kennung, feld, name):
    pflicht = ni.LISTEN[kennung].pflicht_spalten
    pflicht_spalte = {"zielfirmen": "Firma", "headhunter": "Firma", "kontakte": "Name"}[kennung]
    for variante in (name, name.upper(), name.lower(), name.replace(" ", "")):
        kopf = [variante] if feld in pflicht else [pflicht_spalte, variante]
        wert = "x Beispiel" if len(kopf) == 1 else "Beispiel"
        v = ni.vorschau(kennung, "datei.csv", _csv(kopf, [wert] * len(kopf)), session=sitzung)
        erkannt = {s["spalte"]: s["feld"] for s in v["spalten"]["erkannt"]}
        assert erkannt.get(variante) == feld, (kennung, feld, variante, v["spalten"])


@pytest.mark.parametrize("kennung, schreibweise, feld", [
    ("zielfirmen", "GROESSE (MA)", "size_ma"), ("zielfirmen", "groesse", "size_ma"),
    ("zielfirmen", "Eigentuemer", "ownership"), ("zielfirmen", "EINSCHÄTZUNG", "einschaetzung"),
    ("zielfirmen", "Einschaetzung", "einschaetzung"), ("zielfirmen", "ki readiness", "ki_readiness"),
    ("kontakte", "Prioritaet", "prioritaet"), ("kontakte", "Faellig", "next_action_date"),
    ("kontakte", "naechste aktion", "next_action"), ("kontakte", "FÄLLIG AM", "next_action_date"),
])
def test_umlaute_und_ersatzschreibweisen_in_der_kopfzeile(ni, sitzung, kennung, schreibweise, feld):
    pflicht_spalte = {"zielfirmen": "Firma", "kontakte": "Name"}[kennung]
    v = ni.vorschau(kennung, "d.csv", _csv([pflicht_spalte, schreibweise], ["Beispiel", "1"]), session=sitzung)
    assert {"spalte": schreibweise, "feld": feld} in [
        {"spalte": s["spalte"], "feld": s["feld"]} for s in v["spalten"]["erkannt"]]


def test_unbekannte_und_doppelte_spalten_landen_in_ignoriert(ni, sitzung):
    daten = _csv(["Firma", "Name", "Foo", "", "Branche", "Company"],
                 ["Muster GmbH", "anderer Name", "x", "y", "Handel", "noch ein Name"])
    v = ni.vorschau("zielfirmen", "z.csv", daten, session=sitzung)
    assert v["spalten"]["erkannt"] == [
        {"spalte": "Firma", "feld": "company", "label": "Firma"},
        {"spalte": "Branche", "feld": "industry", "label": "Branche"},
    ]
    # Zweite und dritte Spalte für dasselbe Feld und Spalten ohne Zuordnung; die leere Überschrift fehlt.
    assert v["spalten"]["ignoriert"] == ["Name", "Foo", "Company"]
    assert v["zeilen"][0]["anzeige"] == "Muster GmbH"


def test_erkannte_spalten_tragen_spalte_feld_und_label(ni, sitzung):
    v = ni.vorschau("zielfirmen", "z.csv", _csv(["company", "GRÖSSE", "karriere-url"], ["A", "B", "C"]),
                    session=sitzung)
    assert v["spalten"]["erkannt"] == [
        {"spalte": "company", "feld": "company", "label": "Firma"},
        {"spalte": "GRÖSSE", "feld": "size_ma", "label": "Größe (MA)"},
        {"spalte": "karriere-url", "feld": "karriere_url", "label": "Karriereseite"},
    ]


# ── 2. CSV: Kodierung, Trennzeichen, Zeilennummern ───────────────────────────────────────────
def test_csv_semikolon_utf8_mit_bom(ni, sitzung):
    daten = _csv(["Name", "Unternehmen", "Rolle"], ["Max Muster", "Muster GmbH", "Leiter"])
    assert daten.startswith(b"\xef\xbb\xbf")
    v = ni.vorschau("kontakte", "k.csv", daten, session=sitzung)
    assert v["liste"] == "kontakte" and v["format"] == "csv" and v["blatt"] is None
    assert [s["feld"] for s in v["spalten"]["erkannt"]] == ["name", "unternehmen", "rolle"]
    assert v["anzahl"] == {"zeilen": 1, "neu": 1, "ergaenzt": 0, "unveraendert": 0, "geloescht": 0, "fehler": 0}


def test_csv_utf8_ohne_bom_komma(ni, sitzung):
    daten = _csv(["Name", "Unternehmen", "Rolle"], ["Max Muster", "Muster GmbH", "Leiter"],
                 trenner=",", kodierung="utf-8")
    assert not daten.startswith(b"\xef\xbb\xbf")
    v = ni.vorschau("kontakte", "k.csv", daten, session=sitzung)
    assert [s["feld"] for s in v["spalten"]["erkannt"]] == ["name", "unternehmen", "rolle"]
    assert v["anzahl"]["neu"] == 1


def test_csv_tabulator(ni, sitzung):
    daten = _csv(["Name", "Unternehmen"], ["Max Muster", "Muster GmbH"], trenner="\t", kodierung="utf-8")
    v = ni.vorschau("kontakte", "k.csv", daten, session=sitzung)
    assert [s["feld"] for s in v["spalten"]["erkannt"]] == ["name", "unternehmen"]


def test_csv_cp1252_mit_umlauten_wird_gelesen_und_gespeichert(ni, sitzung, umgebung):
    daten = _csv(["Firma", "Branche", "Eigentümer"], ["Müller & Söhne GmbH", "Bäckerei", "Familienunternehmen"],
                 kodierung="cp1252")
    with pytest.raises(UnicodeDecodeError):
        daten.decode("utf-8")
    v = ni.vorschau("zielfirmen", "z.csv", daten, session=sitzung)
    assert [s["feld"] for s in v["spalten"]["erkannt"]] == ["company", "industry", "ownership"]
    assert v["zeilen"][0]["anzeige"] == "Müller & Söhne GmbH"
    ni.importieren("zielfirmen", "z.csv", daten, session=sitzung)
    firma = _alle(umgebung, "TargetCompany")[0]
    assert (firma.company, firma.industry, firma.ownership) == ("Müller & Söhne GmbH", "Bäckerei", "Familienunternehmen")


def test_csv_utf16_mit_bom_wie_excel_unicode_text(ni, sitzung):
    daten = "Name\tUnternehmen\r\nMax Muster\tMüller GmbH\r\n".encode("utf-16")
    assert daten[:2] in (b"\xff\xfe", b"\xfe\xff")
    v = ni.vorschau("kontakte", "k.txt", daten, session=sitzung)
    assert [s["feld"] for s in v["spalten"]["erkannt"]] == ["name", "unternehmen"]
    assert v["zeilen"][0]["anzeige"] == "Max Muster · Müller GmbH"


@pytest.mark.parametrize("name, format_erwartet", [("liste.txt", "csv"), ("LISTE.CSV", "csv"), ("a\\b\\liste.Csv", "csv")])
def test_endungen_txt_und_grossschreibung(ni, sitzung, name, format_erwartet):
    v = ni.vorschau("zielfirmen", name, _csv(["Firma"], ["Muster GmbH"]), session=sitzung)
    assert v["format"] == format_erwartet and v["anzahl"]["neu"] == 1


def test_felder_in_anfuehrungszeichen_mit_trennzeichen_und_zeilenumbruch(ni, sitzung, umgebung):
    text = 'Name;Notizen;Unternehmen\r\n"Muster, Max";"Zeile eins\r\nZeile zwei; mit Semikolon";Muster GmbH\r\nErika Beispiel;;\r\n'
    v = ni.vorschau("kontakte", "k.csv", text.encode("utf-8"), session=sitzung)
    # Zeilennummer = Datensatz wie in Excel, der Umbruch im Feld verschiebt nichts.
    assert [z["nr"] for z in v["zeilen"]] == [2, 3]
    ni.importieren("kontakte", "k.csv", text.encode("utf-8"), session=sitzung)
    kontakt = _kontakt(umgebung, "Muster, Max")
    assert kontakt.notizen == "Zeile eins\r\nZeile zwei; mit Semikolon"


@pytest.mark.parametrize("ende", ["\r\n", "\n", "\r"])
def test_zeilenenden(ni, sitzung, ende):
    daten = _csv(["Firma", "Branche"], ["Muster GmbH", "Handel"], ["Beispiel AG", "Technik"], ende=ende)
    v = ni.vorschau("zielfirmen", "z.csv", daten, session=sitzung)
    assert v["anzahl"]["zeilen"] == 2 and [z["nr"] for z in v["zeilen"]] == [2, 3]


def test_dezimalkomma_in_den_daten_verwirrt_die_trennzeichenwahl_nicht(ni, sitzung):
    daten = _csv(["Firma", "Umsatz", "Mitarbeiter"], ["Muster GmbH", "1,5 Mio", "2,5"], ["Beispiel AG", "2,25 Mio", "3,5"])
    v = ni.vorschau("zielfirmen", "z.csv", daten, session=sitzung)
    assert [s["feld"] for s in v["spalten"]["erkannt"]] == ["company", "revenue", "size_ma"]


def test_einspaltige_datei_mit_komma_im_wert(ni, sitzung, umgebung):
    daten = _csv(["Firma"], ["Muster, Beispiel & Co."], ["Beispiel AG"])
    ni.importieren("zielfirmen", "z.csv", daten, session=sitzung)
    assert sorted(f.company for f in _alle(umgebung, "TargetCompany")) == ["Beispiel AG", "Muster, Beispiel & Co."]


def test_zeilennummern_zaehlen_kopfzeile_und_leerzeilen_mit(ni, sitzung):
    text = "\r\n;;;\r\nFirma;Branche\r\nMuster GmbH;Handel\r\n\r\n;;\r\nBeispiel AG;Technik\r\n"
    v = ni.vorschau("zielfirmen", "z.csv", text.encode("utf-8"), session=sitzung)
    assert v["anzahl"]["zeilen"] == 2
    assert [(z["nr"], z["anzeige"]) for z in v["zeilen"]] == [(4, "Muster GmbH"), (7, "Beispiel AG")]


def test_komplett_leere_zeilen_werden_still_uebersprungen(ni, sitzung):
    v = ni.vorschau("zielfirmen", "z.csv", _csv(["Firma", "Branche"], ["", ""], ["", ""], ["Muster GmbH", ""]),
                    session=sitzung)
    assert v["anzahl"] == {"zeilen": 1, "neu": 1, "ergaenzt": 0, "unveraendert": 0, "geloescht": 0, "fehler": 0}


def test_zellen_werden_getrimmt_und_leer_wird_nicht_geschrieben(ni, sitzung, umgebung):
    ni.importieren("zielfirmen", "z.csv", _csv(["Firma", "Branche", "Umsatz"], ["  Muster GmbH \u00a0", "  ", "10 Mio"]),
                   session=sitzung)
    firma = _alle(umgebung, "TargetCompany")[0]
    assert firma.company == "Muster GmbH" and firma.industry is None and firma.revenue == "10 Mio"


# ── 3. Fehler beim Lesen (V3) ────────────────────────────────────────────────────────────────
def test_pflichtspalte_fehlt_gibt_400_mit_dem_text_der_spec(ni, sitzung):
    for liste, kopf, text in (
            ("zielfirmen", ["Branche", "Ort"], FIRMA_FEHLT_TEXT),
            ("headhunter", ["Fokus", "Region"], HEADHUNTER_SPALTE_FEHLT_TEXT),
            ("kontakte", ["Rolle", "Unternehmen"], NAME_FEHLT_TEXT)):
        with pytest.raises(ni.ImportFehler) as fehler:
            ni.vorschau(liste, "d.csv", _csv(kopf, ["a", "b"]), session=sitzung)
        assert (fehler.value.status, fehler.value.text) == (400, text), liste


def test_headhunter_braucht_nur_eine_der_beiden_pflichtspalten(ni, sitzung):
    for kopf in (["Ansprechpartner", "Fokus"], ["Firma", "Fokus"]):
        v = ni.vorschau("headhunter", "h.csv", _csv(kopf, ["Eins", "Zwei"]), session=sitzung)
        assert v["anzahl"]["neu"] == 1


def test_kontakte_nur_vorname_oder_nur_nachname_reicht(ni, sitzung):
    for kopf in (["Vorname"], ["Nachname"], ["First Name"], ["Last Name"]):
        assert ni.vorschau("kontakte", "k.csv", _csv(kopf, ["Eins"]), session=sitzung)["anzahl"]["neu"] == 1


def test_keine_kopfzeile_und_leere_datei(ni, sitzung):
    with pytest.raises(ni.ImportFehler) as fehler:
        ni.vorschau("zielfirmen", "z.csv", b"", session=sitzung)
    assert (fehler.value.status, fehler.value.text) == (400, "Die Datei ist leer.")
    for inhalt in (b"\r\n\r\n", b";;;\r\n;;;\r\n", "   \n".encode()):
        with pytest.raises(ni.ImportFehler) as fehler:
            ni.vorschau("zielfirmen", "z.csv", inhalt, session=sitzung)
        assert fehler.value.status == 400 and "keine Kopfzeile" in fehler.value.text


def test_endungen_xls_und_fremde_werden_abgewiesen(ni, sitzung):
    with pytest.raises(ni.ImportFehler) as fehler:
        ni.vorschau("zielfirmen", "alt.xls", b"\xd0\xcf\x11\xe0irgendwas", session=sitzung)
    assert fehler.value.status == 400
    assert ".xls" in fehler.value.text and "als .xlsx oder .csv" in fehler.value.text
    for name in ("liste.pdf", "liste", "liste.xlsm", "liste.ods", ""):
        with pytest.raises(ni.ImportFehler) as fehler:
            ni.vorschau("zielfirmen", name, _csv(["Firma"], ["Muster GmbH"]), session=sitzung)
        assert fehler.value.status == 400 and ".csv, .txt oder .xlsx" in fehler.value.text, name


def test_unbekannte_liste_gibt_404(ni, sitzung):
    for aufruf in (lambda: ni.vorschau("anders", "z.csv", b"x", session=sitzung),
                   lambda: ni.importieren("anders", "z.csv", b"x", session=sitzung),
                   lambda: ni.vorlage("anders", "csv")):
        with pytest.raises(ni.ImportFehler) as fehler:
            aufruf()
        assert fehler.value.status == 404


def test_binaerdatei_als_csv_ist_unlesbar(ni, sitzung):
    for inhalt in (b"PK\x03\x04\x00\x00\x00\x00binaer", "Name".encode("utf-16-le") + b"\x00\x00"):
        with pytest.raises(ni.ImportFehler) as fehler:
            ni.vorschau("kontakte", "k.csv", inhalt, session=sitzung)
        assert fehler.value.status == 400


def test_mehr_als_5_mb_gibt_413_und_fasst_die_datenbank_nicht_an(ni, sitzung, umgebung):
    vorher = _stand(umgebung)
    zu_gross = b"Firma\r\n" + b"a" * (MB5 + 1)
    for aufruf in (ni.vorschau, ni.importieren):
        with pytest.raises(ni.ImportFehler) as fehler:
            aufruf("zielfirmen", "z.csv", zu_gross, session=sitzung)
        assert (fehler.value.status, fehler.value.text) == (
            413, "Die Datei ist größer als 5 MB. Bitte teilen Sie sie in mehrere Dateien auf.")
    assert _stand(umgebung) == vorher and _sicherungen(umgebung) == []


def test_genau_5000_zeilen_gehen_5001_nicht(ni, sitzung):
    zeilen = [f"Testfirma {i}" for i in range(5001)]
    ok = ni.vorschau("zielfirmen", "z.csv", ("Firma\r\n" + "\r\n".join(zeilen[:5000])).encode(), session=sitzung)
    assert ok["anzahl"]["zeilen"] == 5000 and ok["anzahl"]["neu"] == 5000
    with pytest.raises(ni.ImportFehler) as fehler:
        ni.vorschau("zielfirmen", "z.csv", ("Firma\r\n" + "\r\n".join(zeilen)).encode(), session=sitzung)
    assert fehler.value.status == 400 and "5.000" in fehler.value.text


def test_leerzeilen_zaehlen_nicht_zu_den_5000(ni, sitzung):
    zeilen = ["Muster GmbH", ""] * 2600
    v = ni.vorschau("zielfirmen", "z.csv", ("Firma\r\n" + "\r\n".join(zeilen)).encode(), session=sitzung)
    # 5200 Zeilen, davon 2600 mit Inhalt (alle derselbe Eintrag): Leerzeilen zählen nicht zum Limit.
    assert v["anzahl"]["zeilen"] == 2600


def test_ueberlanges_feld_ist_ein_kundenfehler_kein_absturz(ni, sitzung):
    with pytest.raises(ni.ImportFehler) as fehler:
        ni.vorschau("zielfirmen", "z.csv", b"Firma;Notizen\r\nMuster GmbH;" + b"a" * 200_000, session=sitzung)
    assert fehler.value.status == 400


# ── 4. XLSX ──────────────────────────────────────────────────────────────────────────────────
def test_xlsx_mit_mehreren_blaettern_nimmt_das_passende(ni, sitzung):
    # „Kontakte“ (Stellen-Kontakte im Export) steht vor „Netzwerk“: Es zählt die Rangfolge der Namen, nicht die Blattreihenfolge.
    daten = _xlsx({
        "Hinweise": [["Text"]],
        "Kontakte": [["Name", "Rolle", "Firma", "Stelle", "E-Mail"], ["Falsche Person", "x", "y", "z", "q"]],
        "Netzwerk": [["Name", "Unternehmen"], ["Max Muster", "Muster GmbH"]],
    })
    v = ni.vorschau("kontakte", "k.xlsx", daten, session=sitzung)
    assert v["format"] == "xlsx" and v["blatt"] == "Netzwerk"
    assert v["zeilen"][0]["anzeige"] == "Max Muster · Muster GmbH"
    assert any("mehrere" in h and "Netzwerk" in h for h in v["hinweise"])


@pytest.mark.parametrize("liste, blaetter, erwartet", [
    ("zielfirmen", ["Notizen", "Target Companies"], "Target Companies"),
    ("zielfirmen", ["Notizen", "ZIELFIRMEN"], "ZIELFIRMEN"),
    ("headhunter", ["Notizen", "Headhunters"], "Headhunters"),
    ("kontakte", ["Notizen", "Network Contacts"], "Network Contacts"),
    ("kontakte", ["Notizen", "netzwerk kontakte"], "netzwerk kontakte"),
    ("kontakte", ["Notizen", "Kontakte"], "Kontakte"),
    ("zielfirmen", ["Erstes", "Zweites"], "Erstes"),      # kein passender Name: das erste Blatt
])
def test_xlsx_blattwahl_nach_listenname(ni, sitzung, liste, blaetter, erwartet):
    kopf = {"zielfirmen": ["Firma"], "headhunter": ["Firma"], "kontakte": ["Name"]}[liste]
    daten = _xlsx({name: [kopf, ["Beispiel"]] for name in blaetter})
    assert ni.vorschau(liste, "d.xlsx", daten, session=sitzung)["blatt"] == erwartet


def test_xlsx_ein_blatt_ohne_hinweis_auf_mehrere(ni, sitzung):
    v = ni.vorschau("zielfirmen", "z.xlsx", _xlsx({"Tabelle1": [["Firma"], ["Muster GmbH"]]}), session=sitzung)
    assert v["blatt"] == "Tabelle1" and v["hinweise"] == []


def test_xlsx_datum_ganze_zahlen_und_wahrheitswerte(ni, sitzung, umgebung):
    import datetime

    daten = _xlsx({"Netzwerk": [
        ["Name", "Unternehmen", "Rolle", "Letzter Kontakt", "Fällig am", "Notizen", "Beziehung"],
        ["Max Muster", "Muster GmbH", 12.0, datetime.datetime(2026, 9, 1, 14, 30), datetime.date(2026, 11, 5), 3.5, True],
        ["Erika Beispiel", "Beispiel AG", 7, "12.09.2026", "5.10.26", 0, False],
    ]})
    ni.importieren("kontakte", "k.xlsx", daten, session=sitzung)
    max_, erika = _kontakt(umgebung, "Max Muster"), _kontakt(umgebung, "Erika Beispiel")
    assert (max_.rolle, max_.letzter_kontakt, max_.next_action_date, max_.notizen, max_.beziehung) == (
        "12", "2026-09-01", "2026-11-05", "3.5", "Ja")
    assert (erika.rolle, erika.letzter_kontakt, erika.next_action_date, erika.notizen, erika.beziehung) == (
        "7", "2026-09-12", "2026-10-05", "0", "Nein")


def test_xlsx_kopfzeile_nicht_in_der_ersten_zeile_zeilennummern_wie_in_excel(ni, sitzung):
    daten = _xlsx({"Netzwerk": [[], [], ["Name", "Unternehmen"], ["Max Muster", "Muster GmbH"], [], [],
                                 ["Erika Beispiel", "Beispiel AG"], [None, None]]})
    v = ni.vorschau("kontakte", "k.xlsx", daten, session=sitzung)
    assert v["anzahl"]["zeilen"] == 2
    assert [(z["nr"], z["anzeige"]) for z in v["zeilen"]] == [(4, "Max Muster · Muster GmbH"), (7, "Erika Beispiel · Beispiel AG")]


def test_xlsx_mit_falscher_dimensionsangabe_wird_vollstaendig_gelesen(ni, sitzung):
    """Manche Programme schreiben `<dimension ref="A1"/>`; ohne `reset_dimensions` bliebe nur Zelle A1."""
    original = _xlsx({"Netzwerk": [["Name", "Unternehmen", "Rolle"], ["Max Muster", "Muster GmbH", "Leiter"],
                                   ["Erika Beispiel", "Beispiel AG", "CTO"]]})
    puffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as lesen, zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as schreiben:
        for info in lesen.infolist():
            inhalt = lesen.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                text = inhalt.decode("utf-8")
                assert re.search(r"<dimension[^>]*/>", text)
                inhalt = re.sub(r"<dimension[^>]*/>", '<dimension ref="A1"/>', text).encode("utf-8")
            schreiben.writestr(info, inhalt)
    v = ni.vorschau("kontakte", "k.xlsx", puffer.getvalue(), session=sitzung)
    assert [s["feld"] for s in v["spalten"]["erkannt"]] == ["name", "unternehmen", "rolle"]
    assert v["anzahl"]["zeilen"] == 2


def test_xlsx_ohne_inhalt_und_defekte_xlsx(ni, sitzung):
    with pytest.raises(ni.ImportFehler) as fehler:
        ni.vorschau("zielfirmen", "z.xlsx", _xlsx({"Leer": []}), session=sitzung)
    assert fehler.value.status == 400 and "keine Kopfzeile" in fehler.value.text
    for inhalt in (b"das ist keine Excel-Datei", b"PK\x03\x04kaputt"):
        with pytest.raises(ni.ImportFehler) as fehler:
            ni.vorschau("zielfirmen", "z.xlsx", inhalt, session=sitzung)
        assert fehler.value.status == 400 and "Excel-Datei konnte nicht gelesen werden" in fehler.value.text


def test_xlsx_mit_riesiger_entpackter_groesse_wird_abgewiesen(ni, sitzung, monkeypatch):
    monkeypatch.setattr(ni, "_MAX_ENTPACKT", 100)
    with pytest.raises(ni.ImportFehler) as fehler:
        ni.vorschau("zielfirmen", "z.xlsx", _xlsx({"Z": [["Firma"], ["Muster GmbH"]]}), session=sitzung)
    assert fehler.value.status == 400 and "zu umfangreich" in fehler.value.text


def test_xlsx_5001_zeilen_gibt_400(ni, sitzung):
    daten = _xlsx({"Zielfirmen": [["Firma"]] + [[f"Testfirma {i}"] for i in range(5001)]})
    with pytest.raises(ni.ImportFehler) as fehler:
        ni.vorschau("zielfirmen", "z.xlsx", daten, session=sitzung)
    assert fehler.value.status == 400 and "5.000" in fehler.value.text


# ── 5. LinkedIn (`Connections.csv`) ──────────────────────────────────────────────────────────
LINKEDIN_DATEI = (
    'Notes:\n'
    '"When exporting your connection data, you may notice that some of the email addresses are missing. '
    'You will only see email addresses for connections who have allowed their connections to see or '
    'download their email address."\n'
    '\n'
    'First Name,Last Name,URL,Email Address,Company,Position,Connected On\n'
    'Jana,Beispiel,https://www.linkedin.com/in/jana-beispiel-x,jana@beispiel.de,Beispiel AG,Leiterin Vertrieb,12 Sep 2023\n'
    'Tom,Muster,https://www.linkedin.com/in/tom-muster-y,,,Berater,05 Jan 2024\n'
    ',,https://www.linkedin.com/in/ohne-namen,,Muster GmbH,Inhaber,01 Feb 2024\n'
    'Erika,Muster,,,Muster GmbH,,\n'
).encode("utf-8")


def test_linkedin_datei_wird_als_linkedin_erkannt_und_abgebildet(ni, sitzung, umgebung):
    v = ni.vorschau("kontakte", "Connections.csv", LINKEDIN_DATEI, session=sitzung)
    assert v["format"] == "linkedin" and v["blatt"] is None
    assert v["anzahl"] == {"zeilen": 4, "neu": 3, "ergaenzt": 0, "unveraendert": 0, "geloescht": 0, "fehler": 1}
    assert LINKEDIN_HINWEIS in v["hinweise"]
    # Hinweiszeilen davor: Notes (1), Absatz (2), Leerzeile (3), Kopfzeile (4).
    assert [(z["nr"], z["aktion"]) for z in v["zeilen"]] == [(5, "neu"), (6, "neu"), (7, "fehler"), (8, "neu")]
    assert v["zeilen"][2]["meldung"] == "Es fehlt der Name."
    assert [s["feld"] for s in v["spalten"]["erkannt"]] == [
        "vorname", "nachname", "li_url", "li_email", "unternehmen", "rolle", "li_seit"]

    ni.importieren("kontakte", "Connections.csv", LINKEDIN_DATEI, session=sitzung)
    jana = _kontakt(umgebung, "Jana Beispiel")
    assert (jana.unternehmen, jana.rolle, jana.kanal) == ("Beispiel AG", "Leiterin Vertrieb", "LinkedIn")
    assert jana.notizen == ("LinkedIn: https://www.linkedin.com/in/jana-beispiel-x · E-Mail: jana@beispiel.de "
                            "· verbunden seit 12.09.2023")
    tom = _kontakt(umgebung, "Tom Muster")
    assert tom.unternehmen is None and tom.kanal == "LinkedIn"
    assert tom.notizen == "LinkedIn: https://www.linkedin.com/in/tom-muster-y · verbunden seit 05.01.2024"
    erika = _kontakt(umgebung, "Erika Muster")
    assert erika.notizen is None and erika.kanal == "LinkedIn"
    # beziehung, letzter_kontakt, prioritaet, next_action und next_action_date bleiben leer (V6).
    for kontakt in _alle(umgebung, "NetworkContact"):
        assert (kontakt.beziehung, kontakt.letzter_kontakt, kontakt.prioritaet, kontakt.next_action,
                kontakt.next_action_date) == (None, None, None, None, None)


def test_linkedin_mit_windows_zeilenenden_und_bom(ni, sitzung):
    daten = LINKEDIN_DATEI.decode("utf-8").replace("\n", "\r\n").encode("utf-8-sig")
    v = ni.vorschau("kontakte", "Connections.csv", daten, session=sitzung)
    assert v["format"] == "linkedin" and v["anzahl"]["neu"] == 3 and v["anzahl"]["fehler"] == 1
    assert [z["nr"] for z in v["zeilen"]] == [5, 6, 7, 8]


def test_linkedin_ohne_hinweiszeilen_und_mit_komma_im_namen(ni, sitzung):
    text = 'First Name,Last Name,URL,Email Address,Company,Position,Connected On\r\nAnna,"Beispiel, Dr.",,,Beispiel AG,CEO,01 Mar 2022\r\n'
    v = ni.vorschau("kontakte", "Connections.csv", text.encode("utf-8"), session=sitzung)
    assert v["format"] == "linkedin" and v["zeilen"][0]["anzeige"] == "Anna Beispiel, Dr. · Beispiel AG"


def test_linkedin_erkennung_braucht_connected_on_oder_url(ni, sitzung):
    # Ohne beide Spalten ist es eine gewöhnliche CSV, die Namen kommen aus First Name und Last Name.
    text = "Notes:\n\nFirst Name,Last Name,Company,Position\nJana,Beispiel,Beispiel AG,Leiterin\n"
    v = ni.vorschau("kontakte", "k.csv", text.encode(), session=sitzung)
    assert v["format"] == "csv" and v["hinweise"] == []
    assert v["zeilen"][0]["anzeige"] == "Jana Beispiel · Beispiel AG" and v["zeilen"][0]["nr"] == 4
    # Nur URL genügt neben den Namensspalten.
    text = "First Name,Last Name,URL\nJana,Beispiel,https://www.linkedin.com/in/jana-beispiel-x\n"
    assert ni.vorschau("kontakte", "k.csv", text.encode(), session=sitzung)["format"] == "linkedin"


def test_linkedin_datei_bei_zielfirmen_und_headhunter_ist_eine_gewoehnliche_csv(ni, sitzung):
    # Die erste Zeile ist „Notes:“, dort fehlt die Pflichtspalte: 400 statt eines Fehlimports.
    for liste, text in (("zielfirmen", FIRMA_FEHLT_TEXT), ("headhunter", HEADHUNTER_SPALTE_FEHLT_TEXT)):
        with pytest.raises(ni.ImportFehler) as fehler:
            ni.vorschau(liste, "Connections.csv", LINKEDIN_DATEI, session=sitzung)
        assert (fehler.value.status, fehler.value.text) == (400, text), liste


def test_linkedin_eine_zweite_datei_ergaenzt_nur_leere_felder(ni, sitzung, umgebung):
    ni.importieren("kontakte", "Connections.csv", LINKEDIN_DATEI, session=sitzung)
    v = ni.importieren("kontakte", "Connections.csv", LINKEDIN_DATEI, session=sitzung)
    assert v["anzahl"]["unveraendert"] == 3 and v["anzahl"]["neu"] == 0 and v["sicherung"] is None


def test_linkedin_auch_als_xlsx_gespeichert(ni, sitzung):
    """Abnahme P2-62: Der LinkedIn-Hinweis rät, die Datei vorher zu kürzen; wer das in Excel tut,
    speichert oft als .xlsx, und Excel hat „Connected On“ dabei in ein echtes Datum verwandelt. Auch
    dann gelten Kanal und Notizen wie bei der CSV."""
    import datetime
    from app.models import NetworkContact
    from sqlmodel import select

    daten = _xlsx({"Connections": [["First Name", "Last Name", "URL", "Company", "Position", "Connected On"],
                                   ["Jana", "Beispiel", "https://example.com/jana", "Beispiel AG", "Leiterin",
                                    datetime.datetime(2023, 9, 12)]]})
    v = ni.vorschau("kontakte", "Connections.xlsx", daten, session=sitzung)
    assert v["format"] == "linkedin" and v["blatt"] == "Connections"
    assert v["zeilen"][0]["anzeige"] == "Jana Beispiel · Beispiel AG"
    assert v["spalten"]["ignoriert"] == []
    assert any("LinkedIn-Exporte" in h for h in v["hinweise"])
    ni.importieren("kontakte", "Connections.xlsx", daten, session=sitzung)
    kontakt = sitzung.exec(select(NetworkContact).where(NetworkContact.name == "Jana Beispiel")).one()
    assert kontakt.kanal == "LinkedIn" and kontakt.next_action_date is None
    assert kontakt.notizen == "LinkedIn: https://example.com/jana · verbunden seit 12.09.2023"


# ── 6. Werte (V6) ────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text, erwartet", [
    ("2026-10-05", "2026-10-05"), ("2026-1-5", "2026-01-05"), ("2026-10-05T00:00:00", "2026-10-05"),
    ("2026-10-05 14:30:00", "2026-10-05"), ("05.10.2026", "2026-10-05"), ("5.10.2026", "2026-10-05"),
    ("5.10.26", "2026-10-05"), ("5. 10. 2026", "2026-10-05"), ("31.12.99", "2099-12-31"),
    ("12 Sep 2023", "2023-09-12"), ("5 January 2024", "2024-01-05"), ("05 Jan 2024", "2024-01-05"),
    ("3. Mär 2025", "2025-03-03"), ("3. März 2025", "2025-03-03"), ("7 Okt. 2025", "2025-10-07"),
    ("7 Dec 2025", "2025-12-07"),
    ("30.02.2026", None), ("2026-02-30", None), ("0.0.0", None), ("morgen", None), ("KW 40", None),
    ("12 Foo 2023", None), ("2026", None), ("", None),
])
def test_datum_wird_iso_oder_gilt_als_nicht_lesbar(ni, text, erwartet):
    assert ni._datum_iso(text) == erwartet


@pytest.mark.parametrize("text, erwartet", [
    ("hoch", "Hoch"), ("HOCH", "Hoch"), ("High", "Hoch"), ("mittel", "Mittel"), ("Medium", "Mittel"),
    ("niedrig", "Niedrig"), ("LOW", "Niedrig"), ("sehr wichtig", "sehr wichtig"), ("A", "A"),
])
def test_prioritaet_wird_normalisiert_unbekanntes_bleibt(ni, text, erwartet):
    assert ni._prioritaet(text) == erwartet


@pytest.mark.parametrize("text, erwartet", [
    ("linkedin", "LinkedIn"), ("LinkedIn", "LinkedIn"), ("email", "E-Mail"), ("E-Mail", "E-Mail"),
    ("Mail", "E-Mail"), ("phone", "Telefon"), ("Telefon", "Telefon"), ("in person", "Persönlich"),
    ("persönlich", "Persönlich"), ("Persoenlich", "Persönlich"), ("Xing", "Xing"), ("Messe", "Messe"),
])
def test_kanal_wird_normalisiert_unbekanntes_bleibt(ni, text, erwartet):
    assert ni._kanal(text) == erwartet


@pytest.mark.parametrize("text, erwartet", [
    ("1", "1"), ("1.0", "1"), ("1,0", "1"), ("Tier 1", "1"), ("tier1", "1"), ("TIER 2", "2"), ("03", "3"),
    ("Top", "Top"), ("1.5", "1.5"), ("Tier 1 plus", "Tier 1 plus"),
])
def test_tier_wird_normalisiert(ni, text, erwartet):
    assert ni._tier(text) == erwartet


@pytest.mark.parametrize("text, erwartet", [
    ("a", "A"), ("B", "B"), ("c", "C"), ("a/b", "A/B"), ("Aufbau", "Aufbau"), ("Plan a", "Plan a"),
])
def test_szenario_wird_grossbuchstabe(ni, text, erwartet):
    assert ni._szenario(text) == erwartet


def test_werte_gelangen_normalisiert_in_die_datenbank(ni, sitzung, umgebung):
    daten = _csv(["Name", "Priorität", "Kanal", "Letzter Kontakt", "Fällig am"],
                 ["Eins Muster", "high", "email", "5.10.26", "31.12.2026"],
                 ["Zwei Muster", "LOW", "in person", "irgendwann im Herbst", "12 Sep 2023"],
                 ["Drei Muster", "Mittel", "Messe", "2026-9-1", ""])
    v = ni.importieren("kontakte", "k.csv", daten, session=sitzung)
    assert v["anzahl"]["neu"] == 3
    eins, zwei, drei = (_kontakt(umgebung, n) for n in ("Eins Muster", "Zwei Muster", "Drei Muster"))
    assert (eins.prioritaet, eins.kanal, eins.letzter_kontakt, eins.next_action_date) == (
        "Hoch", "E-Mail", "2026-10-05", "2026-12-31")
    # Nicht lesbarer „Letzter Kontakt“ bleibt als Text, „Fällig am“ wird iso, wenn es sich lesen lässt.
    assert (zwei.prioritaet, zwei.kanal, zwei.letzter_kontakt, zwei.next_action_date) == (
        "Niedrig", "Persönlich", "irgendwann im Herbst", "2023-09-12")
    assert (drei.prioritaet, drei.kanal, drei.letzter_kontakt, drei.next_action_date) == (
        "Mittel", "Messe", "2026-09-01", None)


def test_nicht_lesbares_faelligkeitsdatum_bleibt_leer_und_die_zeile_bekommt_eine_meldung(ni, sitzung, umgebung):
    daten = _csv(["Name", "Fällig am", "Rolle"], ["Eins Muster", "bald", "Leiter"], ["Zwei Muster", "5.10.2026", "CTO"])
    v = ni.vorschau("kontakte", "k.csv", daten, session=sitzung)
    assert v["zeilen"][0]["aktion"] == "neu"
    assert v["zeilen"][0]["meldung"] == ("Das Datum in der Spalte „Fällig am“ ist nicht lesbar und wurde nicht "
                                          "übernommen. Erwartet wird zum Beispiel 31.12.2026.")
    assert v["zeilen"][1]["meldung"] is None
    ni.importieren("kontakte", "k.csv", daten, session=sitzung)
    assert _kontakt(umgebung, "Eins Muster").next_action_date is None
    assert _kontakt(umgebung, "Eins Muster").rolle == "Leiter"


def test_zielfirma_tier_und_szenario_werden_normalisiert(ni, sitzung, umgebung):
    daten = _csv(["Firma", "Tier", "Szenario"], ["Muster GmbH", "Tier 1", "a"], ["Beispiel AG", "2.0", "B"])
    ni.importieren("zielfirmen", "z.csv", daten, session=sitzung)
    firmen = {f.company: f for f in _alle(umgebung, "TargetCompany")}
    assert (firmen["Muster GmbH"].tier, firmen["Muster GmbH"].scenario) == ("1", "A")
    assert (firmen["Beispiel AG"].tier, firmen["Beispiel AG"].scenario) == ("2", "B")


def test_zielfirma_last_update_ist_dateiwert_oder_heute(ni, sitzung, umgebung, monkeypatch):
    monkeypatch.setattr(ni, "_heute", lambda: date(2026, 10, 1))
    daten = _csv(["Firma", "Letzte Aktualisierung"], ["Eins GmbH", "15.09.2026"], ["Zwei GmbH", ""], ["Drei GmbH", "Herbst"])
    ni.importieren("zielfirmen", "z.csv", daten, session=sitzung)
    firmen = {f.company: f.last_update for f in _alle(umgebung, "TargetCompany")}
    assert firmen == {"Eins GmbH": "2026-09-15", "Zwei GmbH": "2026-10-01", "Drei GmbH": "Herbst"}


def test_zielfirma_ohne_spalte_last_update_bekommt_heute_nur_bei_neuen_eintraegen(ni, sitzung, umgebung, monkeypatch):
    monkeypatch.setattr(ni, "_heute", lambda: date(2026, 10, 1))
    _anlegen(umgebung, "TargetCompany", company="Alt GmbH")           # ohne last_update
    ni.importieren("zielfirmen", "z.csv", _csv(["Firma", "Branche"], ["Neu GmbH", "Handel"], ["Alt GmbH", "Technik"]), session=sitzung)
    firmen = {f.company: f for f in _alle(umgebung, "TargetCompany")}
    assert firmen["Neu GmbH"].last_update == "2026-10-01"
    assert firmen["Alt GmbH"].last_update is None and firmen["Alt GmbH"].industry == "Technik"


def test_zweite_zeile_kann_den_standardwert_noch_liefern(ni, sitzung, umgebung, monkeypatch):
    monkeypatch.setattr(ni, "_heute", lambda: date(2026, 10, 1))
    daten = _csv(["Firma", "Letzte Aktualisierung"], ["Muster GmbH", ""], ["Muster GmbH", "15.09.2026"])
    ni.importieren("zielfirmen", "z.csv", daten, session=sitzung)
    assert _alle(umgebung, "TargetCompany")[0].last_update == "2026-09-15"


# ── 7. Kein automatisches next_action_date (V6, Gegenprobe 3) ────────────────────────────────
def test_der_import_setzt_kein_next_action_date(ni, sitzung, umgebung):
    csv_daten = _csv(["Name", "Unternehmen", "Rolle"], ["Eins Muster", "Muster GmbH", "Leiter"], ["Zwei Muster", "", ""])
    xlsx_daten = _xlsx({"Netzwerk": [["Name"], ["Drei Muster"], ["Vier Muster"]]})
    ni.importieren("kontakte", "k.csv", csv_daten, session=sitzung)
    ni.importieren("kontakte", "k.xlsx", xlsx_daten, session=sitzung)
    ni.importieren("kontakte", "Connections.csv", LINKEDIN_DATEI, session=sitzung)
    kontakte = _alle(umgebung, "NetworkContact")
    assert len(kontakte) == 2 + 2 + 3
    assert [k.name for k in kontakte if k.next_action_date is not None] == []


def test_ein_vorhandener_kontakt_ohne_termin_bekommt_auch_keinen(ni, sitzung, umgebung):
    _anlegen(umgebung, "NetworkContact", name="Max Muster", unternehmen="Muster GmbH")
    v = ni.importieren("kontakte", "k.csv", _csv(["Name", "Unternehmen", "Rolle"], ["Max Muster", "Muster GmbH", "Leiter"]),
                       session=sitzung)
    assert v["anzahl"]["ergaenzt"] == 1
    assert _kontakt(umgebung, "Max Muster").next_action_date is None


def test_ein_angegebenes_faelligkeitsdatum_wird_uebernommen(ni, sitzung, umgebung):
    ni.importieren("kontakte", "k.csv", _csv(["Name", "Fällig am"], ["Max Muster", "31.12.2026"]), session=sitzung)
    assert _kontakt(umgebung, "Max Muster").next_action_date == "2026-12-31"


# ── 8. Regeln gegen die Datenbank (V7) ───────────────────────────────────────────────────────
def test_neue_eintraege_werden_angelegt_mit_schluessel_und_zeitstempel(ni, sitzung, umgebung):
    from app.normalize import slug_parts

    v = ni.importieren("kontakte", "k.csv", _csv(["Name", "Unternehmen", "Rolle"], ["Max Muster", "Muster GmbH", "Leiter"]),
                       session=sitzung)
    assert v["anzahl"] == {"zeilen": 1, "neu": 1, "ergaenzt": 0, "unveraendert": 0, "geloescht": 0, "fehler": 0}
    kontakt = _kontakt(umgebung, "Max Muster")
    assert kontakt.dedup_key == slug_parts("Max Muster", "Muster GmbH") == "maxmustermustergmbh"
    assert kontakt.deleted_at is None and kontakt.created_at and kontakt.updated_at


def test_vorhandene_eintraege_bekommen_nur_leere_felder_ergaenzt(ni, sitzung, umgebung):
    """Gegenprobe 2 (Überschreiben): Gefüllte Felder bleiben, wie sie sind."""
    # Feste alte Zeitstempel: Die Uhr unter Windows löst grob auf, ein Vergleich mit „jetzt“ wäre unsicher.
    alt = _anlegen(umgebung, "NetworkContact", name="Max Muster", unternehmen="Muster GmbH", rolle="Leiter",
                   notizen="meine Notiz", prioritaet="Hoch", created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1))
    daten = _csv(["Name", "Unternehmen", "Rolle", "Priorität", "Notizen", "Kanal", "Beziehung"],
                 ["Max Muster", "Muster GmbH", "Geschäftsführer", "niedrig", "andere Notiz", "email", "Kollege"])
    v = ni.vorschau("kontakte", "k.csv", daten, session=sitzung)
    assert v["anzahl"] == {"zeilen": 1, "neu": 0, "ergaenzt": 1, "unveraendert": 0, "geloescht": 0, "fehler": 0}
    assert v["zeilen"][0]["aktion"] == "ergaenzt"
    assert v["zeilen"][0]["felder_ergaenzt"] == ["beziehung", "kanal"]       # Reihenfolge der Felder in der Konfiguration
    ni.importieren("kontakte", "k.csv", daten, session=sitzung)
    kontakt = _kontakt(umgebung, "Max Muster")
    assert (kontakt.id, kontakt.rolle, kontakt.notizen, kontakt.prioritaet) == (alt.id, "Leiter", "meine Notiz", "Hoch")
    assert (kontakt.kanal, kontakt.beziehung) == ("E-Mail", "Kollege")
    assert kontakt.updated_at > alt.updated_at and kontakt.created_at == alt.created_at
    assert _anzahl(umgebung, "NetworkContact") == 1


def test_leere_zellen_in_der_datei_loeschen_nichts(ni, sitzung, umgebung):
    _anlegen(umgebung, "NetworkContact", name="Max Muster", unternehmen="Muster GmbH", rolle="Leiter")
    v = ni.importieren("kontakte", "k.csv", _csv(["Name", "Unternehmen", "Rolle"], ["Max Muster", "Muster GmbH", ""]), session=sitzung)
    assert v["anzahl"]["unveraendert"] == 1 and _kontakt(umgebung, "Max Muster").rolle == "Leiter"


def test_ein_leeres_feld_aus_nur_leerzeichen_zaehlt_als_leer(ni, sitzung, umgebung):
    _anlegen(umgebung, "NetworkContact", name="Max Muster", unternehmen="Muster GmbH", rolle="   ", notizen="")
    v = ni.importieren("kontakte", "k.csv", _csv(["Name", "Unternehmen", "Rolle", "Notizen"],
                                                  ["Max Muster", "Muster GmbH", "Leiter", "Notiz"]), session=sitzung)
    assert v["anzahl"]["ergaenzt"] == 1
    kontakt = _kontakt(umgebung, "Max Muster")
    assert (kontakt.rolle, kontakt.notizen) == ("Leiter", "Notiz")


def test_unveraenderte_zeilen_werden_gezaehlt_und_nichts_wird_geschrieben(ni, sitzung, umgebung):
    _anlegen(umgebung, "NetworkContact", name="Max Muster", unternehmen="Muster GmbH", rolle="Leiter")
    vorher = _stand(umgebung)
    v = ni.importieren("kontakte", "k.csv", _csv(["Name", "Unternehmen", "Rolle"], ["Max Muster", "Muster GmbH", "Leiter"]),
                       session=sitzung)
    assert v == {"anzahl": {"zeilen": 1, "neu": 0, "ergaenzt": 0, "unveraendert": 1, "geloescht": 0, "fehler": 0},
                 "sicherung": None}
    assert _stand(umgebung) == vorher


def test_geloeschte_eintraege_bleiben_geloescht(ni, sitzung, umgebung):
    """Gegenprobe 1 (Tombstone-Regel): übersprungen, nicht neu belebt, nicht befüllt, kein zweiter Eintrag."""
    _anlegen(umgebung, "NetworkContact", name="Max Muster", unternehmen="Muster GmbH",
             deleted_at="2026-09-01T10:00:00")
    vorher = _stand(umgebung)
    daten = _csv(["Name", "Unternehmen", "Rolle", "Notizen"], ["Max Muster", "Muster GmbH", "Leiter", "Neue Notiz"])
    v = ni.vorschau("kontakte", "k.csv", daten, session=sitzung)
    assert v["anzahl"] == {"zeilen": 1, "neu": 0, "ergaenzt": 0, "unveraendert": 0, "geloescht": 1, "fehler": 0}
    assert v["zeilen"][0]["aktion"] == "geloescht"
    assert "gelöscht" in v["zeilen"][0]["meldung"] and "Papierkorb" in v["zeilen"][0]["meldung"]
    ergebnis = ni.importieren("kontakte", "k.csv", daten, session=sitzung)
    assert ergebnis["sicherung"] is None and ergebnis["anzahl"]["geloescht"] == 1
    assert _stand(umgebung) == vorher
    kontakt = _alle(umgebung, "NetworkContact")[0]
    assert kontakt.deleted_at == "2026-09-01T10:00:00" and kontakt.rolle is None and kontakt.notizen is None


@pytest.mark.parametrize("liste, kopf, zeile, modell, anlage", [
    ("zielfirmen", ["Firma", "Branche"], ["Muster GmbH", "Handel"], "TargetCompany", {"company": "Muster GmbH"}),
    ("headhunter", ["Firma", "Ansprechpartner", "Fokus"], ["Muster Partner", "Max Muster", "IT"], "Headhunter",
     {"firma": "Muster Partner", "ansprechpartner": "Max Muster"}),
    ("kontakte", ["Name", "Unternehmen", "Rolle"], ["Max Muster", "Muster GmbH", "Leiter"], "NetworkContact",
     {"name": "Max Muster", "unternehmen": "Muster GmbH"}),
])
def test_geloeschte_eintraege_bleiben_in_allen_drei_listen_geloescht(ni, sitzung, umgebung, liste, kopf, zeile, modell, anlage):
    _anlegen(umgebung, modell, deleted_at="2026-09-01T10:00:00", **anlage)
    vorher = _stand(umgebung)
    v = ni.importieren(liste, "d.csv", _csv(kopf, zeile), session=sitzung)
    assert v["anzahl"]["geloescht"] == 1 and v["anzahl"]["neu"] == 0 and v["sicherung"] is None
    assert _stand(umgebung) == vorher


def test_dubletten_in_der_datei_wirken_auf_die_erste_zeile(ni, sitzung, umgebung):
    daten = _csv(["Name", "Unternehmen", "Rolle", "Notizen"],
                 ["Max Muster", "Muster GmbH", "", "erste Notiz"],      # 2: neu
                 ["max  muster", "MUSTER GMBH", "Leiter", "zweite"],    # 3: füllt die Rolle der ersten
                 ["Max Muster", "Muster GmbH", "CTO", "dritte"],        # 4: nichts Leeres mehr
                 ["Erika Beispiel", "", "", ""])                        # 5: neu
    v = ni.vorschau("kontakte", "k.csv", daten, session=sitzung)
    assert v["anzahl"] == {"zeilen": 4, "neu": 2, "ergaenzt": 1, "unveraendert": 1, "geloescht": 0, "fehler": 0}
    zeilen = {z["nr"]: z for z in v["zeilen"]}
    assert (zeilen[2]["aktion"], zeilen[2]["meldung"]) == ("neu", None)
    assert (zeilen[3]["aktion"], zeilen[3]["felder_ergaenzt"], zeilen[3]["meldung"]) == (
        "ergaenzt", ["rolle"], "Doppelt in der Datei, siehe Zeile 2.")
    assert (zeilen[4]["aktion"], zeilen[4]["felder_ergaenzt"], zeilen[4]["meldung"]) == (
        "unveraendert", [], "Doppelt in der Datei, siehe Zeile 2.")
    ni.importieren("kontakte", "k.csv", daten, session=sitzung)
    assert _anzahl(umgebung, "NetworkContact") == 2
    kontakt = _kontakt(umgebung, "Max Muster")
    assert (kontakt.rolle, kontakt.notizen) == ("Leiter", "erste Notiz")


def test_dublette_eines_vorhandenen_eintrags_in_der_datei(ni, sitzung, umgebung):
    _anlegen(umgebung, "NetworkContact", name="Max Muster", unternehmen="Muster GmbH")
    daten = _csv(["Name", "Unternehmen", "Rolle", "Kanal"], ["Max Muster", "Muster GmbH", "Leiter", ""],
                 ["Max Muster", "Muster GmbH", "CTO", "phone"])
    v = ni.vorschau("kontakte", "k.csv", daten, session=sitzung)
    assert [(z["aktion"], z["felder_ergaenzt"]) for z in v["zeilen"]] == [("ergaenzt", ["rolle"]), ("ergaenzt", ["kanal"])]
    ni.importieren("kontakte", "k.csv", daten, session=sitzung)
    kontakt = _kontakt(umgebung, "Max Muster")
    assert (kontakt.rolle, kontakt.kanal) == ("Leiter", "Telefon") and _anzahl(umgebung, "NetworkContact") == 1


def test_dublette_eines_geloeschten_eintrags_in_der_datei(ni, sitzung, umgebung):
    _anlegen(umgebung, "NetworkContact", name="Max Muster", unternehmen="Muster GmbH", deleted_at="2026-09-01T10:00:00")
    v = ni.vorschau("kontakte", "k.csv", _csv(["Name", "Unternehmen"], ["Max Muster", "Muster GmbH"], ["Max Muster", "Muster GmbH"]),
                    session=sitzung)
    assert v["anzahl"]["geloescht"] == 2 and v["zeilen"][1]["meldung"].startswith("Doppelt in der Datei, siehe Zeile 2.")


def test_gleicher_schluessel_wie_der_einzel_endpunkt_kontakte(ni, sitzung, umgebung):
    from fastapi import HTTPException
    import app.main as main

    main.create_network_contact({"name": "Max Muster", "unternehmen": "Muster GmbH", "rolle": "Leiter"}, session=sitzung)
    v = ni.importieren("kontakte", "k.csv", _csv(["Name", "Unternehmen", "Rolle", "Kanal"],
                                                   ["MAX MUSTER", "muster gmbh", "CTO", "linkedin"]), session=sitzung)
    assert v["anzahl"]["neu"] == 0 and v["anzahl"]["ergaenzt"] == 1 and _anzahl(umgebung, "NetworkContact") == 1
    # Umgekehrt: ein Importierter Eintrag blockiert den Einzel-Endpunkt mit 409.
    ni.importieren("kontakte", "k2.csv", _csv(["Name", "Unternehmen"], ["Erika Beispiel", "Beispiel AG"]), session=sitzung)
    with pytest.raises(HTTPException) as fehler:
        main.create_network_contact({"name": "Erika Beispiel", "unternehmen": "Beispiel AG"}, session=sitzung)
    assert fehler.value.status_code == 409


def test_gleicher_schluessel_wie_der_einzel_endpunkt_zielfirmen(ni, sitzung, umgebung):
    from fastapi import HTTPException
    import app.main as main

    main.create_target_company({"company": "Muster GmbH", "industry": "Handel"}, session=sitzung)
    v = ni.importieren("zielfirmen", "z.csv", _csv(["Firma", "Branche", "Umsatz"], ["muster  gmbh", "Technik", "10 Mio"]),
                       session=sitzung)
    assert v["anzahl"]["neu"] == 0 and v["anzahl"]["ergaenzt"] == 1 and _anzahl(umgebung, "TargetCompany") == 1
    firma = _alle(umgebung, "TargetCompany")[0]
    assert (firma.industry, firma.revenue) == ("Handel", "10 Mio")
    ni.importieren("zielfirmen", "z2.csv", _csv(["Firma"], ["Beispiel AG"]), session=sitzung)
    with pytest.raises(HTTPException) as fehler:
        main.create_target_company({"company": "Beispiel AG"}, session=sitzung)
    assert fehler.value.status_code == 409


def test_gleicher_schluessel_wie_der_einzel_endpunkt_headhunter(ni, sitzung, umgebung):
    from fastapi import HTTPException
    import app.main as main

    main.create_headhunter({"firma": "Muster Partner", "ansprechpartner": "Max Muster", "fokus": "IT"}, session=sitzung)
    v = ni.importieren("headhunter", "h.csv", _csv(["Firma", "Ansprechpartner", "Region"],
                                                   ["Muster Partner", "Max Muster", "DACH"],
                                                   ["Muster Partner", "Erika Beispiel", "DACH"]), session=sitzung)
    # Gleiche Firma, anderer Ansprechpartner: ein eigener Eintrag (Schlüssel aus beiden Teilen).
    assert v["anzahl"]["neu"] == 1 and v["anzahl"]["ergaenzt"] == 1 and _anzahl(umgebung, "Headhunter") == 2
    with pytest.raises(HTTPException) as fehler:
        main.create_headhunter({"firma": "Muster Partner", "ansprechpartner": "Erika Beispiel"}, session=sitzung)
    assert fehler.value.status_code == 409


def test_schluessel_je_liste(ni, sitzung, umgebung):
    ni.importieren("zielfirmen", "z.csv", _csv(["Firma"], ["Müller & Söhne GmbH"]), session=sitzung)
    ni.importieren("headhunter", "h.csv", _csv(["Firma", "Ansprechpartner"], ["Muster Partner", "Max Muster"], ["Nur Firma", ""]),
                   session=sitzung)
    ni.importieren("kontakte", "k.csv", _csv(["Name", "Unternehmen"], ["Max Muster", "Muster GmbH"], ["Erika Beispiel", ""]),
                   session=sitzung)
    # `slug_parts` lässt alles außer a bis z und 0 bis 9 weg, also auch Umlaute: wie bei den Anlege-Endpunkten.
    assert [z.dedup_key for z in _alle(umgebung, "TargetCompany")] == ["mllershnegmbh"]
    assert sorted(z.dedup_key for z in _alle(umgebung, "Headhunter")) == ["musterpartnermaxmuster", "nurfirma"]
    assert sorted(z.dedup_key for z in _alle(umgebung, "NetworkContact")) == ["erikabeispiel", "maxmustermustergmbh"]


def test_pflichtwert_fehlt_gibt_eine_fehlerzeile_ohne_dass_die_uebrigen_leiden(ni, sitzung, umgebung):
    daten = _csv(["Firma", "Branche"], ["Muster GmbH", "Handel"], ["", "Technik"], ["???", "Technik"], ["Beispiel AG", ""])
    v = ni.vorschau("zielfirmen", "z.csv", daten, session=sitzung)
    assert v["anzahl"] == {"zeilen": 4, "neu": 2, "ergaenzt": 0, "unveraendert": 0, "geloescht": 0, "fehler": 2}
    fehler = [z for z in v["zeilen"] if z["aktion"] == "fehler"]
    assert [z["nr"] for z in fehler] == [3, 4]
    assert fehler[0]["meldung"] == "Es fehlt die Firma." and fehler[0]["anzeige"] == "(ohne Angabe)"
    assert fehler[1]["meldung"] == ("Die Firma enthält keine lateinischen Buchstaben oder Ziffern und kann "
                                    "nicht angelegt werden.")
    ni.importieren("zielfirmen", "z.csv", daten, session=sitzung)
    assert sorted(f.company for f in _alle(umgebung, "TargetCompany")) == ["Beispiel AG", "Muster GmbH"]


def test_headhunter_zeile_braucht_firma_oder_ansprechpartner(ni, sitzung, umgebung):
    daten = _csv(["Firma", "Ansprechpartner", "Fokus"], ["", "Max Muster", "IT"], ["Muster Partner", "", "Finanzen"],
                 ["", "", "Technik"])
    v = ni.vorschau("headhunter", "h.csv", daten, session=sitzung)
    assert v["anzahl"] == {"zeilen": 3, "neu": 2, "ergaenzt": 0, "unveraendert": 0, "geloescht": 0, "fehler": 1}
    assert [z["anzeige"] for z in v["zeilen"]] == ["Max Muster", "Muster Partner", "(ohne Angabe)"]
    assert v["zeilen"][2]["meldung"] == "Es fehlen Firma und Ansprechpartner."


def test_kontakt_name_aus_vorname_und_nachname(ni, sitzung, umgebung):
    daten = _csv(["Vorname", "Nachname", "Unternehmen"], ["Max", "Muster", "Muster GmbH"], ["Erika", "", ""],
                 ["", "Beispiel", ""], ["", "", "Muster GmbH"])
    v = ni.vorschau("kontakte", "k.csv", daten, session=sitzung)
    assert [z["anzeige"] for z in v["zeilen"]] == ["Max Muster · Muster GmbH", "Erika", "Beispiel", "Muster GmbH"]
    assert v["anzahl"]["neu"] == 3 and v["anzahl"]["fehler"] == 1
    assert v["zeilen"][3]["meldung"] == "Es fehlt der Name."
    ni.importieren("kontakte", "k.csv", daten, session=sitzung)
    assert sorted(k.name for k in _alle(umgebung, "NetworkContact")) == ["Beispiel", "Erika", "Max Muster"]


def test_kontakt_spalte_name_gewinnt_gegen_vorname_und_nachname(ni, sitzung, umgebung):
    daten = _csv(["Name", "Vorname", "Nachname"], ["Dr. Max Muster", "Max", "Muster"], ["", "Erika", "Beispiel"])
    ni.importieren("kontakte", "k.csv", daten, session=sitzung)
    assert sorted(k.name for k in _alle(umgebung, "NetworkContact")) == ["Dr. Max Muster", "Erika Beispiel"]


def test_vorschau_zeigt_alle_auffaelligen_zeilen_und_hoechstens_100_uebrige(ni, sitzung, umgebung):
    _anlegen(umgebung, "TargetCompany", company="Geloescht GmbH", deleted_at="2026-09-01T10:00:00")
    _anlegen(umgebung, "TargetCompany", company="Vorhanden GmbH", industry="Handel")
    zeilen = [["Vorhanden GmbH", "Handel"]] + [[f"Testfirma {i}", "x"] for i in range(250)]
    zeilen += [["Geloescht GmbH", "y"], ["", "kaputt"], ["Testfirma 300", "x"]]
    v = ni.vorschau("zielfirmen", "z.csv", _csv(["Firma", "Branche"], *zeilen), session=sitzung)
    assert v["anzahl"] == {"zeilen": 254, "neu": 251, "ergaenzt": 0, "unveraendert": 1, "geloescht": 1, "fehler": 1}
    assert v["zeilen_gekuerzt"] is True
    aktionen = [z["aktion"] for z in v["zeilen"]]
    assert aktionen.count("fehler") == 1 and aktionen.count("geloescht") == 1
    assert len(v["zeilen"]) == 102                                        # alle auffälligen plus 100 übrige
    nummern = [z["nr"] for z in v["zeilen"]]
    assert nummern == sorted(nummern) and len(set(nummern)) == len(nummern)
    # Die ersten 100 übrigen in Dateireihenfolge: Zeile 2 bis 101; die auffälligen stehen an ihrer Stelle.
    assert nummern[:100] == list(range(2, 102)) and nummern[100:] == [253, 254]


def test_vorschau_ohne_auslassung_meldet_nicht_gekuerzt(ni, sitzung):
    v = ni.vorschau("zielfirmen", "z.csv", _csv(["Firma"], *[[f"Testfirma {i}"] for i in range(100)]), session=sitzung)
    assert v["zeilen_gekuerzt"] is False and len(v["zeilen"]) == 100


def test_zahlen_in_der_vorschau_stimmen_mit_den_zeilen_ueberein(ni, sitzung, umgebung):
    _anlegen(umgebung, "NetworkContact", name="Vorhanden Muster", unternehmen="Muster GmbH", rolle="Leiter")
    _anlegen(umgebung, "NetworkContact", name="Geloescht Muster", deleted_at="2026-09-01T10:00:00")
    daten = _csv(["Name", "Unternehmen", "Rolle"], ["Neu Muster", "Muster GmbH", "x"], ["Vorhanden Muster", "Muster GmbH", "Leiter"],
                 ["Vorhanden Muster", "Muster GmbH", "Leiter"], ["Geloescht Muster", "", "x"], ["", "", "x"],
                 ["Neu Muster", "Muster GmbH", "y"])
    v = ni.vorschau("kontakte", "k.csv", daten, session=sitzung)
    anzahl = v["anzahl"]
    assert anzahl["zeilen"] == sum(anzahl[k] for k in ("neu", "ergaenzt", "unveraendert", "geloescht", "fehler")) == 6
    assert {z["aktion"] for z in v["zeilen"]} == {"neu", "unveraendert", "geloescht", "fehler"}


# ── 9. Vorschau, Sicherung, Transaktion (V2, V3) ─────────────────────────────────────────────
def test_vorschau_schreibt_nichts(ni, sitzung, umgebung):
    _anlegen(umgebung, "NetworkContact", name="Max Muster", unternehmen="Muster GmbH")
    vorher = _stand(umgebung)
    daten = _csv(["Name", "Unternehmen", "Rolle"], ["Max Muster", "Muster GmbH", "Leiter"], ["Erika Beispiel", "", "CTO"])
    v = ni.vorschau("kontakte", "k.csv", daten, session=sitzung)
    assert v["anzahl"]["neu"] == 1 and v["anzahl"]["ergaenzt"] == 1
    assert _stand(umgebung) == vorher
    assert not sitzung.new and not sitzung.dirty
    assert _sicherungen(umgebung) == [] and not (umgebung.daten / "backups").exists()


def test_import_legt_die_sicherung_vorher_an_und_nennt_sie(ni, sitzung, umgebung):
    _anlegen(umgebung, "NetworkContact", name="Vorhanden Muster", unternehmen="Muster GmbH")
    v = ni.importieren("kontakte", "k.csv", _csv(["Name", "Unternehmen"], ["Neu Eins", "A"], ["Neu Zwei", "B"]), session=sitzung)
    assert v["anzahl"]["neu"] == 2 and _anzahl(umgebung, "NetworkContact") == 3
    assert v["sicherung"] in _sicherungen(umgebung) and re.fullmatch(r"bewerbung_.*\.zip", v["sicherung"])
    assert set(v) == {"anzahl", "sicherung"}
    # Die Sicherung zeigt den Stand VOR dem Import.
    assert _tabelle_in_sicherung(umgebung, v["sicherung"], "networkcontact") == 1


def test_import_ohne_etwas_zu_schreiben_legt_keine_sicherung_an(ni, sitzung, umgebung):
    _anlegen(umgebung, "NetworkContact", name="Max Muster", unternehmen="Muster GmbH", rolle="Leiter")
    _anlegen(umgebung, "NetworkContact", name="Geloescht Muster", deleted_at="2026-09-01T10:00:00")
    vorher = _stand(umgebung)
    daten = _csv(["Name", "Unternehmen", "Rolle"], ["Max Muster", "Muster GmbH", "Leiter"], ["Geloescht Muster", "", "x"],
                 ["", "", "kein Name"])
    v = ni.importieren("kontakte", "k.csv", daten, session=sitzung)
    assert v["sicherung"] is None
    assert v["anzahl"] == {"zeilen": 3, "neu": 0, "ergaenzt": 0, "unveraendert": 1, "geloescht": 1, "fehler": 1}
    assert _stand(umgebung) == vorher and not (umgebung.daten / "backups").exists()


def test_import_zweimal_hintereinander_zweites_mal_nur_unveraendert(ni, sitzung, umgebung):
    daten = _csv(["Firma", "Branche", "Tier"], ["Muster GmbH", "Handel", "1"], ["Beispiel AG", "Technik", "2"])
    erst = ni.importieren("zielfirmen", "z.csv", daten, session=sitzung)
    nach_erstem = _stand(umgebung)
    zweit = ni.importieren("zielfirmen", "z.csv", daten, session=sitzung)
    assert erst["anzahl"]["neu"] == 2 and erst["sicherung"]
    assert zweit["anzahl"] == {"zeilen": 2, "neu": 0, "ergaenzt": 0, "unveraendert": 2, "geloescht": 0, "fehler": 0}
    assert zweit["sicherung"] is None and _stand(umgebung) == nach_erstem and len(_sicherungen(umgebung)) == 1


def test_sicherung_laeuft_gibt_409_und_nichts_wird_geaendert(ni, sitzung, umgebung):
    from app import sicherung

    vorher = _stand(umgebung)
    assert sicherung._LOCK.acquire(blocking=False)         # die echte Sperre, wie bei einer laufenden Sicherung
    try:
        with pytest.raises(ni.ImportFehler) as fehler:
            ni.importieren("kontakte", "k.csv", _csv(["Name"], ["Max Muster"]), session=sitzung)
    finally:
        sicherung._LOCK.release()
    assert (fehler.value.status, fehler.value.text) == (409, SICHERUNG_LAEUFT_TEXT)
    assert _stand(umgebung) == vorher and _sicherungen(umgebung) == []


def test_gescheiterte_sicherung_gibt_500_und_nichts_wird_geaendert(ni, sitzung, umgebung, monkeypatch):
    from app import sicherung

    def kaputt(*args, **kwargs):
        raise OSError("Platte voll (Test)")

    monkeypatch.setattr(sicherung, "anlegen", kaputt)
    vorher = _stand(umgebung)
    with pytest.raises(ni.ImportFehler) as fehler:
        ni.importieren("kontakte", "k.csv", _csv(["Name"], ["Max Muster"]), session=sitzung)
    assert fehler.value.status == 500
    assert fehler.value.text == ("Die Sicherung vor dem Import ist fehlgeschlagen, es wurde nichts importiert. "
                                 "Grund: Platte voll (Test)")
    assert _stand(umgebung) == vorher


def test_sicherung_bekommt_datenordner_und_datenbank_der_sitzung(ni, sitzung, umgebung, monkeypatch):
    from app import sicherung

    gesehen = {}

    def merken(daten_dir=None, db_pfad=None, jetzt=None):
        gesehen.update(daten_dir=daten_dir, db_pfad=db_pfad)
        return umgebung.daten / "backups" / "auto" / "bewerbung_test.zip"

    monkeypatch.setattr(sicherung, "anlegen", merken)
    ni.importieren("kontakte", "k.csv", _csv(["Name"], ["Max Muster"]), session=sitzung)
    assert gesehen["daten_dir"] is None                                    # wird erst in der Sicherung aufgelöst
    assert gesehen["db_pfad"] == umgebung.daten / "bewerbung.sqlite"
    ni.importieren("kontakte", "k2.csv", _csv(["Name"], ["Erika Beispiel"]), session=sitzung, daten_dir=umgebung.tmp / "anders")
    assert gesehen["daten_dir"] == umgebung.tmp / "anders"


def test_eine_transaktion_fehler_mitten_im_schreiben_schreibt_nichts(ni, sitzung, umgebung, monkeypatch):
    """Ohne ausdrückliches BEGIN committet das RELEASE des ersten SAVEPOINT (pysqlite): Dann blieben
    die beiden ersten Zeilen stehen (Gegenprobe 4)."""
    from app import db

    echt = db.flush_or_duplicate
    aufrufe = []

    def scheitert_beim_dritten(session, aendern):
        aufrufe.append(1)
        if len(aufrufe) == 3:
            raise RuntimeError("Platte voll (Test)")
        return echt(session, aendern)

    monkeypatch.setattr(db, "flush_or_duplicate", scheitert_beim_dritten)
    vorher = _stand(umgebung)
    daten = _csv(["Name"], ["Eins Muster"], ["Zwei Muster"], ["Drei Muster"], ["Vier Muster"])
    with pytest.raises(ni.ImportFehler) as fehler:
        ni.importieren("kontakte", "k.csv", daten, session=sitzung)
    assert len(aufrufe) == 3
    assert fehler.value.status == 500
    assert fehler.value.text == "Der Import ist fehlgeschlagen, es wurde nichts importiert. Grund: Platte voll (Test)"
    assert _stand(umgebung) == vorher and _anzahl(umgebung, "NetworkContact") == 0
    # Die Sitzung ist danach wieder benutzbar, und ein zweiter Versuch ohne Fehler klappt vollständig.
    monkeypatch.setattr(db, "flush_or_duplicate", echt)
    assert ni.importieren("kontakte", "k.csv", daten, session=sitzung)["anzahl"]["neu"] == 4
    assert _anzahl(umgebung, "NetworkContact") == 4


def test_flush_or_duplicate_allein_ist_unter_pysqlite_nicht_atomar(umgebung):
    """Belegt die Annahme hinter dem ausdrücklichen `BEGIN IMMEDIATE` im Modul: Das RELEASE des
    äußersten SAVEPOINT committet, ein späteres `rollback()` nimmt die Zeilen nicht mehr zurück.
    Schlägt dieser Test einmal an, hat sich das Verhalten von Python oder SQLAlchemy geändert und die
    Vorkehrung im Modul ist überholt (der Test ist dann nicht falsch)."""
    from sqlmodel import Session, select
    from app.db import flush_or_duplicate
    from app.models import NetworkContact

    with Session(umgebung.engine) as s:
        s.exec(select(NetworkContact)).all()
        for i in range(3):
            eintrag = NetworkContact(name=f"Zeile {i}", dedup_key=f"zeile{i}")
            assert flush_or_duplicate(s, lambda eintrag=eintrag: s.add(eintrag))
        s.rollback()
    assert _anzahl(umgebung, "NetworkContact") == 3


def test_fehler_beim_ergaenzen_nimmt_auch_die_bereits_ergaenzten_zurueck(ni, sitzung, umgebung, monkeypatch):
    from app import db

    _anlegen(umgebung, "NetworkContact", name="Alt Muster", unternehmen="Muster GmbH")
    echt = db.flush_or_duplicate

    def scheitert(session, aendern):
        raise RuntimeError("Fehler (Test)")

    monkeypatch.setattr(db, "flush_or_duplicate", scheitert)
    vorher = _stand(umgebung)
    daten = _csv(["Name", "Unternehmen", "Rolle"], ["Alt Muster", "Muster GmbH", "Leiter"], ["Neu Muster", "", "CTO"])
    with pytest.raises(ni.ImportFehler):
        ni.importieren("kontakte", "k.csv", daten, session=sitzung)
    assert _stand(umgebung) == vorher
    monkeypatch.setattr(db, "flush_or_duplicate", echt)


def test_vorschau_und_import_zaehlen_gleich(ni, sitzung, umgebung):
    _anlegen(umgebung, "NetworkContact", name="Vorhanden Muster", unternehmen="Muster GmbH", rolle="Leiter")
    _anlegen(umgebung, "NetworkContact", name="Teil Muster", unternehmen="Muster GmbH")
    _anlegen(umgebung, "NetworkContact", name="Geloescht Muster", deleted_at="2026-09-01T10:00:00")
    daten = _csv(["Name", "Unternehmen", "Rolle"], ["Neu Muster", "Muster GmbH", "x"], ["Vorhanden Muster", "Muster GmbH", "Leiter"],
                 ["Teil Muster", "Muster GmbH", "CTO"], ["Geloescht Muster", "", "x"], ["", "", "kein Name"],
                 ["Neu Muster", "Muster GmbH", "y"])
    vorschau = ni.vorschau("kontakte", "k.csv", daten, session=sitzung)["anzahl"]
    assert vorschau == {"zeilen": 6, "neu": 1, "ergaenzt": 1, "unveraendert": 2, "geloescht": 1, "fehler": 1}
    assert ni.importieren("kontakte", "k.csv", daten, session=sitzung)["anzahl"] == vorschau


def test_dublette_beim_schreiben_wirkt_wie_eine_ergaenzung(ni, sitzung, umgebung, monkeypatch):
    """Ein gleichzeitiger Import hat den Schlüssel zwischen Planung und Einfügen angelegt: wie bei jedem
    Upsert im Projekt wird ergänzt statt abgebrochen, und die Zahlen stimmen mit der Datenbank."""
    from app import db

    echt = db.flush_or_duplicate
    zustand = {"erledigt": False}

    def mit_konkurrenz(session, aendern):
        if not zustand["erledigt"]:
            zustand["erledigt"] = True
            session.connection().exec_driver_sql(
                "INSERT INTO networkcontact (name, unternehmen, dedup_key, created_at, updated_at) "
                "VALUES ('Eins Muster', 'Muster GmbH', 'einsmustermustergmbh', '2026-09-01 10:00:00', '2026-09-01 10:00:00')")
        return echt(session, aendern)

    monkeypatch.setattr(db, "flush_or_duplicate", mit_konkurrenz)
    daten = _csv(["Name", "Unternehmen", "Rolle"], ["Eins Muster", "Muster GmbH", "Leiter"], ["Zwei Muster", "Muster GmbH", "CTO"])
    v = ni.importieren("kontakte", "k.csv", daten, session=sitzung)
    assert v["anzahl"] == {"zeilen": 2, "neu": 1, "ergaenzt": 1, "unveraendert": 0, "geloescht": 0, "fehler": 0}
    assert _anzahl(umgebung, "NetworkContact") == 2
    assert _kontakt(umgebung, "Eins Muster").rolle == "Leiter" and _kontakt(umgebung, "Zwei Muster").rolle == "CTO"


def test_belegte_datenbank_gibt_409_statt_eines_haengenden_imports(ni, umgebung, monkeypatch):
    """Ein anderer Schreiber hält die Sperre: `BEGIN IMMEDIATE` scheitert nach der Wartezeit mit einem
    Kundentext. Eigene Engine mit kurzer Wartezeit, damit der Test nicht 15 Sekunden braucht."""
    from sqlmodel import Session, create_engine
    from app import sicherung

    monkeypatch.setattr(sicherung, "anlegen", lambda *a, **k: umgebung.daten / "bewerbung_test.zip")
    schnell = create_engine(f"sqlite:///{umgebung.daten / 'bewerbung.sqlite'}",
                            connect_args={"check_same_thread": False, "timeout": 0.2})
    fremd = sqlite3.connect(str(umgebung.daten / "bewerbung.sqlite"))
    try:
        fremd.execute("BEGIN IMMEDIATE")
        with Session(schnell) as session:
            with pytest.raises(ni.ImportFehler) as fehler:
                ni.importieren("kontakte", "k.csv", _csv(["Name"], ["Max Muster"]), session=session)
    finally:
        fremd.rollback()
        fremd.close()
        schnell.dispose()
    assert fehler.value.status == 409
    assert fehler.value.text == "Die Datenbank ist gerade belegt. Bitte versuchen Sie es gleich noch einmal."
    assert _anzahl(umgebung, "NetworkContact") == 0


def test_geschrieben_wird_gegen_den_stand_nach_der_sicherung(ni, sitzung, umgebung, monkeypatch):
    """Zwischen der ersten Planung und dem Schreiben liegt die Sicherung. Füllt in dieser Zeit jemand
    anderes dasselbe Feld, darf der Import den Wert nicht mit dem Stand der ersten Planung überschreiben:
    Die Sitzung hält die Zeile aus der ersten Planung, ohne `expire_all` sähe die zweite sie veraltet."""
    from sqlmodel import Session, select
    from app import sicherung
    from app.models import NetworkContact

    _anlegen(umgebung, "NetworkContact", name="Max Muster", unternehmen="Muster GmbH")
    echt = sicherung.anlegen

    def mit_dazwischenschreiber(*args, **kwargs):
        with Session(umgebung.engine) as andere:
            zeile = andere.exec(select(NetworkContact)).one()
            zeile.rolle = "Direktor"
            andere.add(zeile)
            andere.commit()
        return echt(*args, **kwargs)

    monkeypatch.setattr(sicherung, "anlegen", mit_dazwischenschreiber)
    daten = _csv(["Name", "Unternehmen", "Rolle", "Kanal"], ["Max Muster", "Muster GmbH", "Leiter", "email"])
    v = ni.importieren("kontakte", "k.csv", daten, session=sitzung)
    kontakt = _kontakt(umgebung, "Max Muster")
    assert (kontakt.rolle, kontakt.kanal) == ("Direktor", "E-Mail")      # nur das noch leere Feld wird ergänzt
    assert v["anzahl"]["ergaenzt"] == 1 and v["sicherung"] in _sicherungen(umgebung)


# ── 10. Vorlagen (V1) ────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("liste", ["zielfirmen", "headhunter", "kontakte"])
def test_vorlage_csv_mit_bom_semikolon_und_nur_der_kopfzeile(ni, liste):
    inhalt, name, media = ni.vorlage(liste, "csv")
    assert inhalt.startswith(b"\xef\xbb\xbf")
    assert name == f"Vorlage_{DATEINAME[liste]}.csv" and media == "text/csv; charset=utf-8"
    text = inhalt.decode("utf-8-sig")
    assert text.rstrip("\r\n") == ";".join(VORLAGE_KOPF[liste]) and text.count("\n") == 1
    assert "\r\n" in text and text.endswith("\r\n")


def test_vorlagen_dateinamen_und_media_type(ni):
    assert [ni.vorlage(liste, "xlsx")[1:] for liste in ("zielfirmen", "headhunter", "kontakte")] == [
        ("Vorlage_Zielfirmen.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("Vorlage_Headhunter.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("Vorlage_Netzwerk-Kontakte.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")]
    assert ni.vorlage("zielfirmen", " XLSX ")[1] == "Vorlage_Zielfirmen.xlsx"            # Schreibweise des Formats egal


@pytest.mark.parametrize("liste", ["zielfirmen", "headhunter", "kontakte"])
def test_vorlage_xlsx_hat_listenblatt_mit_fetter_kopfzeile_und_blatt_hinweise(ni, liste):
    import openpyxl

    inhalt, _name, _media = ni.vorlage(liste, "xlsx")
    mappe = openpyxl.load_workbook(io.BytesIO(inhalt))
    assert mappe.sheetnames == [DATEINAME[liste], "Hinweise"]
    blatt = mappe[DATEINAME[liste]]
    assert [z.value for z in blatt[1]] == VORLAGE_KOPF[liste]
    assert all(z.font.bold for z in blatt[1]) and blatt.max_row == 1
    hinweise = mappe["Hinweise"]
    kopf = [z.value for z in hinweise[1]]
    assert kopf == ["Spalte", "Pflicht", "Erlaubte Werte und Format", "Weitere erkannte Spaltennamen"]
    je_spalte = {z[0].value: [c.value for c in z] for z in hinweise.iter_rows(min_row=2, max_row=1 + len(VORLAGE_KOPF[liste]))}
    assert list(je_spalte) == VORLAGE_KOPF[liste]
    assert all(zeile[2] for zeile in je_spalte.values())                  # zu jeder Spalte steht ein Hinweis
    mappe.close()


def test_vorlage_xlsx_nennt_erlaubte_werte_und_datumsformate(ni):
    import openpyxl

    def hinweise(liste):
        mappe = openpyxl.load_workbook(io.BytesIO(ni.vorlage(liste, "xlsx")[0]))
        ergebnis = {z[0].value: " ".join(str(c.value) for c in z if c.value) for z in mappe["Hinweise"].iter_rows(min_row=2)}
        mappe.close()
        return ergebnis

    kontakte = hinweise("kontakte")
    assert "Hoch, Mittel oder Niedrig" in kontakte["Priorität"]
    assert "LinkedIn, E-Mail, Telefon oder Persönlich" in kontakte["Kanal"]
    assert "TT.MM.JJJJ" in kontakte["Fällig am"] and "TT.MM.JJJJ" in kontakte["Letzter Kontakt"]
    zielfirmen = hinweise("zielfirmen")
    assert "1, 2 oder 3" in zielfirmen["Tier"] and "A, B oder C" in zielfirmen["Szenario"]
    assert "TT.MM.JJJJ" in zielfirmen["Letzte Aktualisierung"]
    assert "TT.MM.JJJJ" in hinweise("headhunter")["Letzter Kontakt"]
    assert "Ja" in zielfirmen["Firma"] and "Ja" in kontakte["Name"]


def test_vorlage_unbekanntes_format_gibt_422(ni):
    for art in ("pdf", "", "xls", "csv;"):
        with pytest.raises(ni.ImportFehler) as fehler:
            ni.vorlage("zielfirmen", art)
        assert fehler.value.status == 422


@pytest.mark.parametrize("liste", ["zielfirmen", "headhunter", "kontakte"])
@pytest.mark.parametrize("format_", ["csv", "xlsx"])
def test_eine_leere_vorlage_importiert_null_zeilen_ohne_fehler(ni, sitzung, umgebung, liste, format_):
    inhalt, name, _media = ni.vorlage(liste, format_)
    v = ni.vorschau(liste, name, inhalt, session=sitzung)
    assert v["format"] == format_ and v["blatt"] == (DATEINAME[liste] if format_ == "xlsx" else None)
    assert v["anzahl"] == {"zeilen": 0, "neu": 0, "ergaenzt": 0, "unveraendert": 0, "geloescht": 0, "fehler": 0}
    assert v["zeilen"] == [] and v["zeilen_gekuerzt"] is False and v["spalten"]["ignoriert"] == []
    # Jede Spalte der Vorlage wird erkannt, mit dem Vorlagen-Namen als Label.
    assert [s["label"] for s in v["spalten"]["erkannt"]] == VORLAGE_KOPF[liste]
    assert "nur eine Kopfzeile" in v["hinweise"][-1]
    assert ni.importieren(liste, name, inhalt, session=sitzung) == {
        "anzahl": v["anzahl"], "sicherung": None}
    assert _stand(umgebung) == {m: [] for m in MODELL.values()}


@pytest.mark.parametrize("liste", ["zielfirmen", "headhunter", "kontakte"])
@pytest.mark.parametrize("format_", ["csv", "xlsx"])
def test_ausgefuellte_vorlage_wird_importiert(ni, sitzung, umgebung, liste, format_):
    import openpyxl

    zeile = {"zielfirmen": ["Muster GmbH", "Handel", "5000", "10 Mio", "Berlin", "Familie", "1", "a", "Max Muster",
                            "Kein Kontakt", "https://www.muster.example", "https://www.muster.example/karriere", "stark",
                            "hoch", "gut", "3", "05.09.2026"],
             "headhunter": ["Muster Partner", "Max Muster", "IT", "DACH", "LinkedIn", "Ja", "05.09.2026", "offen",
                            "https://partner.example", "Notiz"],
             "kontakte": ["Max Muster", "Kollege", "Muster GmbH", "Leiter", "hoch", "05.09.2026", "email", "anrufen",
                          "01.12.2026", "Notiz"]}[liste]
    inhalt, name, _media = ni.vorlage(liste, format_)
    if format_ == "csv":
        daten = inhalt + (";".join(zeile) + "\r\n").encode("utf-8")
    else:
        mappe = openpyxl.load_workbook(io.BytesIO(inhalt))
        mappe[DATEINAME[liste]].append(zeile)
        puffer = io.BytesIO()
        mappe.save(puffer)
        daten = puffer.getvalue()
    v = ni.importieren(liste, name, daten, session=sitzung)
    assert v["anzahl"]["neu"] == 1 and v["anzahl"]["fehler"] == 0
    gespeichert = _alle(umgebung, MODELL[liste])[0]
    kopf = V4[liste]
    felder = [f for f in kopf if f not in ("vorname", "nachname")]
    for feld, wert in zip(felder, zeile):
        erwartet = {"05.09.2026": "2026-09-05", "01.12.2026": "2026-12-01", "hoch": "Hoch", "email": "E-Mail", "a": "A"}.get(wert, wert)
        if feld in ("ki_readiness", "wachstumssignal", "einschaetzung"):
            erwartet = wert
        assert getattr(gespeichert, feld) == erwartet, feld


# ── 11. Round-Trip mit dem Excel-Export ──────────────────────────────────────────────────────
@pytest.mark.parametrize("liste", ["zielfirmen", "headhunter", "kontakte"])
def test_kopfzeilen_der_export_blaetter_werden_voll_erkannt(ni, sitzung, liste):
    daten = _xlsx({EXPORT_BLATT[liste]: [EXPORT_KOEPFE[liste]]})
    v = ni.vorschau(liste, "export.xlsx", daten, session=sitzung)
    assert v["spalten"]["ignoriert"] == []
    assert [s["spalte"] for s in v["spalten"]["erkannt"]] == EXPORT_KOEPFE[liste]


def _export_daten_anlegen(u):
    """Zeilen, wie die Seiten sie füllen: mit Karriereseite, nur mit Webseite, ohne beides, dazu je ein
    gelöschter Eintrag (steht nicht im Export). Dazu eine Stelle: Auf einer Datenbank ganz ohne Stellen
    scheitert `export_excel._dashboard_funnel_block` (`groesster_verlust` ist dann None), das ist
    unabhängig vom Netzwerk-Import."""
    from sqlmodel import Session
    from app.models import Job

    with Session(u.engine) as s:
        s.add(Job(company_name="Muster GmbH", title="Leiter Beispiel", status="Neu",
                  found_date=date.today().isoformat(), dedup_key="export|stelle|1"))
        s.commit()
    _anlegen(u, "TargetCompany", company="Muster GmbH", industry="Handel", size_ma="5000", location_hq="Berlin",
             tier="1", scenario="A", key_contact="Max Muster", connection_status="Kein Kontakt",
             karriere_url="https://www.muster.example/karriere", website="https://www.muster.example",
             wachstumssignal="stark", einschaetzung="gut", last_update="2026-09-01")
    _anlegen(u, "TargetCompany", company="Beispiel AG", tier="2", website="https://www.beispiel.example/")
    _anlegen(u, "TargetCompany", company="Leer AG")
    _anlegen(u, "TargetCompany", company="Geloescht AG", website="https://geloescht.example", deleted_at="2026-09-01T10:00:00")
    _anlegen(u, "Headhunter", firma="Muster Partner", ansprechpartner="Max Muster", fokus="IT", region="DACH",
             status="offen", letzter_kontakt="2026-08-15", webseite="https://partner.example", notizen="Notiz")
    _anlegen(u, "Headhunter", firma="Nur Firma", webseite="partner2.example")
    _anlegen(u, "Headhunter", firma="Geloescht Partner", deleted_at="2026-09-01T10:00:00")
    _anlegen(u, "NetworkContact", name="Max Muster", unternehmen="Muster GmbH", rolle="Leiter", beziehung="Kollege",
             prioritaet="Hoch", letzter_kontakt="2026-08-15", kanal="E-Mail", next_action="anrufen",
             next_action_date="2026-10-20", notizen="Notiz")
    _anlegen(u, "NetworkContact", name="Erika Beispiel", prioritaet="Mittel", letzter_kontakt="vor Weihnachten")
    _anlegen(u, "NetworkContact", name="Nur Name")
    _anlegen(u, "NetworkContact", name="Geloescht Muster", deleted_at="2026-09-01T10:00:00")


def test_export_wieder_einlesen_ergibt_nur_unveraendert(ni, sitzung, umgebung, monkeypatch):
    """Round-Trip mit dem echten Export (`pipeline.export_excel`): jede Liste aus der vollständigen
    Arbeitsmappe, die mehrere Blätter hat (darunter „Kontakte“ vor „Netzwerk“). Alles ist schon
    vorhanden, also darf nichts geschrieben werden, auch keine Sicherung."""
    from pipeline import export_excel

    _export_daten_anlegen(umgebung)
    monkeypatch.setattr(export_excel, "engine", umgebung.engine)
    monkeypatch.setattr(export_excel, "EXPORT_DIR", umgebung.tmp / "export")
    pfad = export_excel.build_workbook()
    daten = pfad.read_bytes()
    vorher = _stand(umgebung)

    erwartet = {"zielfirmen": 3, "headhunter": 2, "kontakte": 3}
    for liste, anzahl in erwartet.items():
        v = ni.vorschau(liste, pfad.name, daten, session=sitzung)
        assert v["blatt"] == EXPORT_BLATT[liste], liste
        assert v["spalten"]["ignoriert"] == [], liste
        assert v["anzahl"] == {"zeilen": anzahl, "neu": 0, "ergaenzt": 0, "unveraendert": anzahl, "geloescht": 0,
                               "fehler": 0}, liste
        assert ni.importieren(liste, pfad.name, daten, session=sitzung)["sicherung"] is None
    assert _stand(umgebung) == vorher and _sicherungen(umgebung) == []


def test_export_in_eine_leere_installation_legt_alles_an(ni, sitzung, umgebung, monkeypatch):
    """Der Export lässt sich auch in eine frische Installation einlesen (Umzug auf einen anderen Rechner)."""
    from pipeline import export_excel

    _export_daten_anlegen(umgebung)
    monkeypatch.setattr(export_excel, "engine", umgebung.engine)
    monkeypatch.setattr(export_excel, "EXPORT_DIR", umgebung.tmp / "export")
    daten = export_excel.build_workbook().read_bytes()
    from sqlmodel import Session, SQLModel, create_engine, select
    from app import db, models

    neu_pfad = umgebung.tmp / "neu"
    neu_pfad.mkdir()
    engine = create_engine(f"sqlite:///{neu_pfad / 'bewerbung.sqlite'}", connect_args=db.CONNECT_ARGS)
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as frisch:
            for liste in ("zielfirmen", "headhunter", "kontakte"):
                assert ni.importieren(liste, "export.xlsx", daten, session=frisch, daten_dir=neu_pfad)["anzahl"]["fehler"] == 0
            kontakt = frisch.exec(select(models.NetworkContact).where(models.NetworkContact.name == "Max Muster")).one()
            assert (kontakt.rolle, kontakt.prioritaet, kontakt.next_action_date, kontakt.kanal) == (
                "Leiter", "Hoch", "2026-10-20", "E-Mail")
            firma = frisch.exec(select(models.TargetCompany).where(models.TargetCompany.company == "Muster GmbH")).one()
            assert (firma.tier, firma.scenario, firma.karriere_url) == ("1", "A", "https://www.muster.example/karriere")
            namen = {f.company for f in frisch.exec(select(models.TargetCompany)).all()}
            assert namen == {"Muster GmbH", "Beispiel AG", "Leer AG"}            # der gelöschte Eintrag war nicht im Export
    finally:
        engine.dispose()


def test_karriereseite_die_nur_die_webseite_ist_wird_nicht_als_karriereseite_uebernommen(ni, sitzung, umgebung):
    """Der Export schreibt ersatzweise die Webseite in „Karriereseite“; der Sweep hielte sie sonst für einen geprüften Treffer."""
    _anlegen(umgebung, "TargetCompany", company="Muster GmbH", website="https://www.muster.example/")
    for karriere in ("https://www.muster.example/", "muster.example", "HTTP://MUSTER.EXAMPLE", "http://www.muster.example"):
        v = ni.vorschau("zielfirmen", "z.csv", _csv(["Firma", "Karriereseite"], ["Muster GmbH", karriere]), session=sitzung)
        assert v["anzahl"]["unveraendert"] == 1, karriere
    v = ni.importieren("zielfirmen", "z.csv", _csv(["Firma", "Karriereseite"], ["Muster GmbH", "https://www.muster.example/jobs"]),
                       session=sitzung)
    assert v["anzahl"]["ergaenzt"] == 1
    assert _alle(umgebung, "TargetCompany")[0].karriere_url == "https://www.muster.example/jobs"


def test_neue_firma_mit_gleicher_webseite_und_karriereseite_behaelt_beide(ni, sitzung, umgebung):
    ni.importieren("zielfirmen", "z.csv", _csv(["Firma", "Webseite", "Karriereseite"],
                                               ["Muster GmbH", "https://www.muster.example", "https://www.muster.example"]),
                   session=sitzung)
    firma = _alle(umgebung, "TargetCompany")[0]
    assert (firma.website, firma.karriere_url) == ("https://www.muster.example", "https://www.muster.example")


# ── 12. Router ───────────────────────────────────────────────────────────────────────────────
@pytest.fixture()
def client(umgebung):
    """Nur der Netzwerk-Import-Router in einer eigenen App; `app.db` zeigt über `umgebung` auf tmp_path."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes_netzwerk_import import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _hochladen(client, pfad, name, inhalt, media="text/csv"):
    return client.post(pfad, files={"datei": (name, inhalt, media)})


def test_router_vorlage_csv_und_xlsx_zum_herunterladen(client, ni):
    r = client.get("/api/netzwerk-import/kontakte/vorlage", params={"format": "csv"})
    assert r.status_code == 200
    assert r.headers["content-disposition"] == 'attachment; filename="Vorlage_Netzwerk-Kontakte.csv"'
    assert r.headers["content-type"].startswith("text/csv")
    assert r.content == ni.vorlage("kontakte", "csv")[0]
    r = client.get("/api/netzwerk-import/zielfirmen/vorlage", params={"format": "xlsx"})
    assert r.status_code == 200
    assert r.headers["content-disposition"] == 'attachment; filename="Vorlage_Zielfirmen.xlsx"'
    assert r.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert r.content[:2] == b"PK"
    # Ohne Angabe gilt csv.
    assert client.get("/api/netzwerk-import/headhunter/vorlage").headers["content-disposition"].endswith('.csv"')


def test_router_vorlage_unbekanntes_format_422_unbekannte_liste_404(client):
    r = client.get("/api/netzwerk-import/zielfirmen/vorlage", params={"format": "pdf"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)
    r = client.get("/api/netzwerk-import/anders/vorlage", params={"format": "csv"})
    assert r.status_code == 404 and isinstance(r.json()["detail"], str)


def test_router_vorschau_antwortform(client, umgebung):
    daten = _csv(["Name", "Unternehmen", "Foo"], ["Max Muster", "Muster GmbH", "x"])
    r = _hochladen(client, "/api/netzwerk-import/kontakte/vorschau", "k.csv", daten)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "liste": "kontakte", "format": "csv", "blatt": None,
        "spalten": {"erkannt": [{"spalte": "Name", "feld": "name", "label": "Name"},
                                {"spalte": "Unternehmen", "feld": "unternehmen", "label": "Unternehmen"}],
                    "ignoriert": ["Foo"]},
        "anzahl": {"zeilen": 1, "neu": 1, "ergaenzt": 0, "unveraendert": 0, "geloescht": 0, "fehler": 0},
        "zeilen": [{"nr": 2, "aktion": "neu", "anzeige": "Max Muster · Muster GmbH", "felder_ergaenzt": [], "meldung": None}],
        "zeilen_gekuerzt": False, "hinweise": [],
    }
    assert _anzahl(umgebung, "NetworkContact") == 0 and _sicherungen(umgebung) == []


def test_router_import_schreibt_und_nennt_die_sicherung(client, umgebung):
    daten = _csv(["Firma", "Branche"], ["Muster GmbH", "Handel"], ["Beispiel AG", "Technik"])
    r = _hochladen(client, "/api/netzwerk-import/zielfirmen", "z.csv", daten)
    assert r.status_code == 200, r.text
    antwort = r.json()
    assert set(antwort) == {"anzahl", "sicherung"}
    assert antwort["anzahl"] == {"zeilen": 2, "neu": 2, "ergaenzt": 0, "unveraendert": 0, "geloescht": 0, "fehler": 0}
    assert antwort["sicherung"] in _sicherungen(umgebung)
    assert _anzahl(umgebung, "TargetCompany") == 2
    zweit = _hochladen(client, "/api/netzwerk-import/zielfirmen", "z.csv", daten).json()
    assert zweit["sicherung"] is None and zweit["anzahl"]["unveraendert"] == 2


def test_router_xlsx_und_linkedin(client):
    daten = _xlsx({"Zielfirmen": [["Firma"], ["Muster GmbH"]]})
    r = _hochladen(client, "/api/netzwerk-import/zielfirmen/vorschau", "z.xlsx", daten,
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert r.status_code == 200 and r.json()["format"] == "xlsx" and r.json()["blatt"] == "Zielfirmen"
    r = _hochladen(client, "/api/netzwerk-import/kontakte/vorschau", "Connections.csv", LINKEDIN_DATEI)
    assert r.status_code == 200 and r.json()["format"] == "linkedin"


def test_router_fehler_haben_detail_als_text(client, umgebung, monkeypatch):
    from app import sicherung

    r = _hochladen(client, "/api/netzwerk-import/zielfirmen/vorschau", "z.csv", _csv(["Branche"], ["x"]))
    assert (r.status_code, r.json()) == (400, {"detail": FIRMA_FEHLT_TEXT})
    r = _hochladen(client, "/api/netzwerk-import/zielfirmen/vorschau", "alt.xls", b"x")
    assert r.status_code == 400 and "als .xlsx oder .csv" in r.json()["detail"]
    r = _hochladen(client, "/api/netzwerk-import/anders/vorschau", "z.csv", b"x")
    assert r.status_code == 404 and isinstance(r.json()["detail"], str)
    r = _hochladen(client, "/api/netzwerk-import/anders", "z.csv", b"x")
    assert r.status_code == 404
    r = client.post("/api/netzwerk-import/zielfirmen/vorschau")
    assert (r.status_code, r.json()) == (400, {"detail": "Bitte wählen Sie eine Datei aus."})

    monkeypatch.setattr(sicherung, "anlegen", lambda *a, **k: (_ for _ in ()).throw(sicherung.SicherungLaeuft("läuft")))
    r = _hochladen(client, "/api/netzwerk-import/kontakte", "k.csv", _csv(["Name"], ["Max Muster"]))
    assert (r.status_code, r.json()) == (409, {"detail": SICHERUNG_LAEUFT_TEXT})
    monkeypatch.setattr(sicherung, "anlegen", lambda *a, **k: (_ for _ in ()).throw(OSError("voll")))
    r = _hochladen(client, "/api/netzwerk-import/kontakte", "k.csv", _csv(["Name"], ["Max Muster"]))
    assert r.status_code == 500 and r.json()["detail"].startswith(
        "Die Sicherung vor dem Import ist fehlgeschlagen, es wurde nichts importiert. Grund: ")
    assert _anzahl(umgebung, "NetworkContact") == 0


def test_router_mehr_als_5_mb_gibt_413_vor_dem_parsen(client, ni, monkeypatch):
    def nie(*args, **kwargs):
        raise AssertionError("darf bei einer zu großen Datei nicht aufgerufen werden")

    monkeypatch.setattr(ni, "vorschau", nie)
    monkeypatch.setattr(ni, "importieren", nie)
    zu_gross = b"Firma\r\n" + b"a" * MB5
    for pfad in ("/api/netzwerk-import/zielfirmen/vorschau", "/api/netzwerk-import/zielfirmen"):
        r = _hochladen(client, pfad, "z.csv", zu_gross)
        assert r.status_code == 413, pfad
        assert r.json() == {"detail": "Die Datei ist größer als 5 MB. Bitte teilen Sie sie in mehrere Dateien auf."}


def test_router_genau_5_mb_werden_noch_gelesen(client):
    """Viele Zeilen mit langen Notizen statt eines einzigen Riesenfelds (das scheitert am Feldlimit von csv)."""
    kopf = b"Firma;Notizen\r\n"
    anfaenge = [f"Testfirma {i};".encode() for i in range(4800)]
    je_zeile, rest = divmod(MB5 - len(kopf) - sum(len(a) + 2 for a in anfaenge), len(anfaenge))
    inhalt = kopf + b"".join(a + b"x" * (je_zeile + (i < rest)) + b"\r\n" for i, a in enumerate(anfaenge))
    assert len(inhalt) == MB5
    r = _hochladen(client, "/api/netzwerk-import/zielfirmen/vorschau", "z.csv", inhalt)
    assert r.status_code == 200 and r.json()["anzahl"]["neu"] == 4800


# ── 13. Paketregeln und Stil der Kundentexte ─────────────────────────────────────────────────
APP_DATEIEN = ["backend/app/netzwerk_import.py", "backend/app/routes_netzwerk_import.py"]


def _kundentexte(ni, umgebung, sitzung):
    """Alles, was ein Kunde lesen kann: Fehlertexte, Meldungen, Hinweise, Vorlagen (CSV und das Blatt „Hinweise“)."""
    import openpyxl

    texte = []

    def fehler_text(aufruf):
        with pytest.raises(ni.ImportFehler) as fehler:
            aufruf()
        texte.append(fehler.value.text)

    for liste in ("zielfirmen", "headhunter", "kontakte"):
        fehler_text(lambda: ni.vorschau(liste, "d.csv", _csv(["Bla"], ["x"]), session=sitzung))
        fehler_text(lambda: ni.vorschau(liste, "d.csv", b"", session=sitzung))
        fehler_text(lambda: ni.vorschau(liste, "d.csv", b"\r\n", session=sitzung))
        fehler_text(lambda: ni.vorschau(liste, "d.xls", b"x", session=sitzung))
        fehler_text(lambda: ni.vorschau(liste, "d.pdf", b"x", session=sitzung))
        fehler_text(lambda: ni.vorschau(liste, "d.xlsx", b"x", session=sitzung))
        fehler_text(lambda: ni.vorschau(liste, "d.csv", b"x" * (MB5 + 1), session=sitzung))
        fehler_text(lambda: ni.vorschau(liste, "d.csv", b"PK\x00\x00", session=sitzung))
        fehler_text(lambda: ni.vorlage(liste, "pdf"))
        texte.append(ni.vorlage(liste, "csv")[0].decode("utf-8-sig"))
        mappe = openpyxl.load_workbook(io.BytesIO(ni.vorlage(liste, "xlsx")[0]))
        texte += [str(z.value) for blatt in mappe for zeile in blatt.iter_rows() for z in zeile if z.value]
        mappe.close()
    fehler_text(lambda: ni.vorschau("anders", "d.csv", b"x", session=sitzung))
    fehler_text(lambda: ni.vorschau("zielfirmen", "d.csv", ("Firma\r\n" + "\r\n".join("a" * 3 + str(i) for i in range(5001))).encode(),
                                    session=sitzung))

    # Meldungen und Hinweise aus der Vorschau
    _anlegen(umgebung, "TargetCompany", company="Geloescht GmbH", deleted_at="2026-09-01T10:00:00")
    for liste, daten in (
            ("zielfirmen", _csv(["Firma", "Foo"], ["", "x"], ["???", "x"], ["Geloescht GmbH", ""], ["Muster GmbH", ""], ["Muster GmbH", "y"])),
            ("headhunter", _csv(["Firma", "Ansprechpartner"], ["", ""], ["", "###"])),
            ("kontakte", _csv(["Name", "Fällig am"], ["", ""], ["Max Muster", "bald"], ["Max Muster", ""])),
            ("kontakte", LINKEDIN_DATEI),
            ("kontakte", _csv(["Name"]))):
        v = ni.vorschau(liste, "d.csv", daten, session=sitzung)
        texte += v["hinweise"] + [z["meldung"] for z in v["zeilen"] if z["meldung"]]
    mehrere = _xlsx({"Netzwerk": [["Name"], ["Max Muster"]], "Zweites": [["Name"]]})
    texte += ni.vorschau("kontakte", "d.xlsx", mehrere, session=sitzung)["hinweise"]
    return texte


def test_alle_kundentexte_bestehen_die_paketregeln(ni, umgebung, sitzung):
    """Mail nur unter beispiel.de, keine Muster wie Stellen- oder Mailnummern, kein Name des Nutzers (Muster
    aus den lokalen Quellen der Personendaten-Prüfung) und keine
    Gedankenstriche (`pipeline/kundenpaket.py`); dazu Sie-Form."""
    from pipeline import kundenpaket

    texte = _kundentexte(ni, umgebung, sitzung)
    assert len(texte) > 40
    gesamt = "\n".join(texte)
    assert kundenpaket.pruefen_eintraege([kundenpaket.Eintrag("netzwerk_import/texte.txt", 0o644, gesamt.encode("utf-8"))]) == []
    assert "\u2014" not in gesamt and "\u2013" not in gesamt
    assert not re.search(r"\b(?:du|dich|dir|dein\w*|euch|euer\w*)\b", gesamt, re.IGNORECASE)
    assert re.search(r"\b(?:Sie|Ihre?[nms]?)\b", gesamt)


@pytest.mark.parametrize("pfad", APP_DATEIEN)
def test_ausgelieferte_dateien_bestehen_die_paketregeln(pfad):
    from pipeline import kundenpaket

    inhalt = (PROJEKT_DIR / pfad).read_bytes()
    assert kundenpaket.pruefen_eintraege([kundenpaket.Eintrag(pfad, 0o644, inhalt)]) == []


@pytest.mark.parametrize("pfad", APP_DATEIEN)
def test_python_module_ohne_gedankenstriche_im_programmtext(pfad):
    quelltext = (PROJEKT_DIR / pfad).read_text(encoding="utf-8")
    assert "\u2014" not in quelltext and "\u2013" not in quelltext
    konstanten = [k.value for k in ast.walk(ast.parse(quelltext)) if isinstance(k, ast.Constant) and isinstance(k.value, str)]
    assert konstanten


def test_das_modul_importiert_kein_internes_skript():
    """Die Excel-Einmalimporte (`import_lists`, `import_outreach`, `migrate_tracker`) sind aus dem Projekt entfernt: Kein Import davon."""
    for pfad in APP_DATEIEN:
        baum = ast.parse((PROJEKT_DIR / pfad).read_text(encoding="utf-8"))
        importiert = {n.module for n in ast.walk(baum) if isinstance(n, ast.ImportFrom) and n.module}
        importiert |= {a.name for n in ast.walk(baum) if isinstance(n, ast.Import) for a in n.names}
        assert not {m for m in importiert if m.split(".")[0] in ("import_lists", "import_outreach", "migrate_tracker")}, pfad


def test_router_ist_in_der_app_eingebunden(_db_ready):
    """Verdrahtung in `main.py` (Hauptsession P2-62): Die echte App beantwortet die Import-Pfade
    selbst. Ohne `include_router` fiele die Vorlage an den Catch-all der Oberfläche (index.html).
    Bewusst die ECHTE `app.main.app`: Das Fixture `client` dieser Datei baut eine eigene App mit
    dem Router und überdeckt das gleichnamige aus conftest.py (ohne Lifespan, wie dort)."""
    from fastapi.testclient import TestClient

    import app.main as main

    client = TestClient(main.app)
    antwort = client.get("/api/netzwerk-import/kontakte/vorlage?format=csv")
    assert antwort.status_code == 200
    assert "attachment" in antwort.headers["content-disposition"]
    assert antwort.content.startswith(b"\xef\xbb\xbf")          # UTF-8 mit BOM (V1)
    assert client.get("/api/netzwerk-import/unbekannt/vorlage?format=csv").status_code == 404
