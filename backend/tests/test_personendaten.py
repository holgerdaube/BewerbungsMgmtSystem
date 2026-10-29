"""Tests für `pipeline/personendaten.py` (P2-83, Vertrag P): die Personendaten-Prüfung mit Mustern aus
lokalen Quellen (Profil, Datenbank, Musterdatei) in den Umfängen „paket“ und „oeffentlich“.

NUR ERFUNDENE DATEN: Profil „Max Mustermann“, Datenbank und `pruefmuster.txt` entstehen in `tmp_path`.
Diese Datei wird mit dem öffentlichen Baum geprüft (Umfang oeffentlich), deshalb steht hier kein Text, den
die Regeln selbst melden würden: Beispiele für verbotene Mailadressen, Telefonnummern, Bestands-IDs und
Benutzerpfade werden zur Laufzeit zusammengesetzt (`_mail`, `_tel`, `_id`, `_benutzerpfad`).

Aufbau: Muster laden (Quellen, fehlende Quellen, Musterdatei, nur lesend) -> je Regel ein Fund und eine
Gegenprobe in beiden Umfängen -> Name des Nutzers (Zuschreibungsliste, Marke, Repo-Name) -> Ausnahmen je
Pfad -> Firmennamen -> nur im öffentlichen Umfang (Benutzerpfad, Dateipfad).

App-/Pipeline-Importe nie auf Modulebene (conftest-Regel), nur über die Fixture `pd`. Kein Test liest
oder schreibt `data/`, `outputs/`, `config/profil.md` oder den echten Secrets-Ordner: Umgebung und alle
Quellen liegen in `tmp_path`."""
import hashlib
import sqlite3

import pytest

UMFAENGE = ("paket", "oeffentlich")

PROFIL = """# Kandidatenprofil: Max Mustermann

## Identität
- **Name:** Max Mustermann
- **Positionierung:** Service Delivery Leader, DACH
- **Standort:** Musterweg 1, 12345 Musterstadt (Rhein-Main)
- **Kontakt:** max@beispiel.de · 069 5550123
- **LinkedIn:** https://www.linkedin.com/in/max-mustermann/
- **Aktuell:** Manager Professional Services bei der Beispiel GmbH, seit 2024

## Kurzprofil
Ein Satz.
"""

MUSTERDATEI = """# Frühere Anschriften und Namen, die nirgends sonst stehen
Altweg
80331
Hans Altmeier
alte.adresse@beispiel.de

xy
   # eingerückter Kommentar
"""


# ── Hilfen ──────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def pd():
    from pipeline import personendaten
    return personendaten


@pytest.fixture(autouse=True)
def _lokale_quellen_isolieren(tmp_path, monkeypatch):
    """Datenbank-Ordner und Secrets-Ordner zeigen ins Leere: kein Test sieht die Quellen des Rechners."""
    monkeypatch.setenv("BMS_SECRETS_DIR", str(tmp_path / "secrets_leer"))
    monkeypatch.setenv("BMS_DATA_DIR", str(tmp_path / "daten_leer"))


def _mail(lokal, domain):
    return f"{lokal}@{domain}"


def _tel(rest):
    return "+49" + rest


def _id(wort, nummer):
    return f"{wort} {nummer}"


def _benutzerpfad(konto):
    return "/Users/" + konto + "/projekt"


def _projekt(tmp_path, profil=PROFIL):
    wurzel = tmp_path / "projekt"
    (wurzel / "config").mkdir(parents=True, exist_ok=True)
    if profil is not None:
        (wurzel / "config" / "profil.md").write_text(profil, encoding="utf-8")
    return wurzel


def _db(tmp_path, *, company=(), job=(), targetcompany=(), headhunter=(), contact=(),
        dateiname="test.sqlite"):
    """Erfundene SQLite mit den Spalten, die `muster_laden` liest (models.py: Company.name,
    Job.company_name, TargetCompany.company, Headhunter.firma, Contact.name)."""
    pfad = tmp_path / dateiname
    conn = sqlite3.connect(pfad)
    conn.execute("CREATE TABLE company (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE job (id INTEGER PRIMARY KEY, company_name TEXT)")
    conn.execute("CREATE TABLE targetcompany (id INTEGER PRIMARY KEY, company TEXT)")
    conn.execute("CREATE TABLE headhunter (id INTEGER PRIMARY KEY, firma TEXT)")
    conn.execute("CREATE TABLE contact (id INTEGER PRIMARY KEY, name TEXT)")
    for tabelle, spalte, werte in (("company", "name", company), ("job", "company_name", job),
                                    ("targetcompany", "company", targetcompany),
                                    ("headhunter", "firma", headhunter), ("contact", "name", contact)):
        conn.executemany(f"INSERT INTO {tabelle} ({spalte}) VALUES (?)", [(w,) for w in werte])
    conn.commit()
    conn.close()
    return pfad


@pytest.fixture
def quellen(tmp_path):
    """(Projektwurzel, Datenbank, Musterdatei) mit erfundenem Inhalt."""
    wurzel = _projekt(tmp_path)
    db = _db(
        tmp_path,
        company=["Nordfeld Systeme GmbH", "AB GmbH", "Google"],
        job=["Nordfeld Systeme"],
        targetcompany=["Silberkiel Consulting AG"],
        headhunter=["Rautental Mandate"],
        contact=["Anna Beispiel", "Recruiting Team", "Karl", "Max Mustermann", "bernd klein",
                 "Dr. Carla Muster-Lindner (HR)", "Jobs Karriere", "Erwin Zeller 2"],
    )
    extra = tmp_path / "pruefmuster.txt"
    extra.write_text(MUSTERDATEI, encoding="utf-8")
    return wurzel, db, extra


@pytest.fixture
def muster(pd, quellen):
    wurzel, db, extra = quellen
    return pd.muster_laden(wurzel, db_pfad=db, extra=extra)


def _funde(pd, muster, pfad, text, umfang="paket", modus=0o644):
    return pd.pruefen([pd.Eintrag(pfad, modus, text.encode("utf-8"))], muster, umfang=umfang)


def _regeln(pd, muster, pfad, text, umfang="paket"):
    return {f.regel for f in _funde(pd, muster, pfad, text, umfang)}


# ── Muster laden: die drei Quellen ──────────────────────────────────────────────────────────────

def test_muster_laden_liest_profil_datenbank_und_musterdatei(muster):
    assert muster.vollstaendig and muster.profil_gelesen and muster.datenbank_gelesen
    assert muster.extra_gelesen and muster.hinweise == ()

    # Profil: Name, Anschrift als Straße und PLZ (die Stadt allein ist kein Muster), Kontakt, LinkedIn
    assert muster.namen == ("Max", "Mustermann")
    assert muster.konten == ("maxmustermann",)
    assert "Musterweg" in muster.anschrift and "12345" in muster.anschrift
    assert "Musterstadt" not in muster.anschrift and "Rhein-Main" not in muster.anschrift
    assert _mail("max", "beispiel.de") in muster.kontakt
    assert "max@" in muster.kontakt and "Max.Mustermann@" in muster.kontakt
    assert "linkedin.com/in/max-mustermann" in muster.kontakt
    assert muster.telefon == ("069 5550123",)

    # Datenbank: Firmennamen als Kernform (Rechtsform ab, zu kurz und „Google“ als erlaubte Nennung raus) ...
    assert set(muster.firmen) == {"Nordfeld Systeme", "Silberkiel Consulting", "Rautental Mandate"}
    # ... und Kontaktnamen mit mindestens zwei Wörtern, die nach einem Personennamen aussehen
    assert "Anna Beispiel" in muster.dritte
    assert "Dr. Carla Muster-Lindner" in muster.dritte            # „(HR)“ am Ende entfällt
    for kein_name in ("Recruiting Team", "Jobs Karriere", "Karl", "bernd klein", "Max Mustermann",
                      "Erwin Zeller 2"):
        assert kein_name not in muster.dritte, kein_name

    # Musterdatei: je nach Form Anschrift (Ziffer oder Straßen-Endung), Kontakt (@) oder Dritte; Kurzes zählt nicht
    assert "Altweg" in muster.anschrift and "80331" in muster.anschrift
    assert "alte.adresse@beispiel.de" in muster.kontakt
    assert "Hans Altmeier" in muster.dritte
    assert not any("xy" == b or "Kommentar" in b for b in muster.anschrift + muster.kontakt + muster.dritte)


def test_muster_repr_nennt_kein_muster(muster):
    text = repr(muster) + str(muster)
    for geheim in ("Mustermann", "Musterweg", "12345", "beispiel.de", "Nordfeld", "Anna", "Altmeier"):
        assert geheim not in text
    assert "vollstaendig=True" in text


def test_strasse_wird_mit_schreibvarianten_gesucht(pd, tmp_path):
    wurzel = _projekt(tmp_path, PROFIL.replace("Musterweg 1", "Beispielstraße 12a"))
    m = pd.muster_laden(wurzel, db_pfad=_db(tmp_path), extra=tmp_path / "gibt_es_nicht.txt")
    assert {"Beispielstraße", "Beispielstrasse", "Beispielstr"} <= set(m.anschrift)
    for schreibweise in ("Beispielstraße 12a", "Beispielstrasse 3", "Beispielstr. 4", "BEISPIELSTR 9"):
        assert "Anschrift" in _regeln(pd, m, "docs/x.md", f"Adresse: {schreibweise}"), schreibweise
    assert "Anschrift" not in _regeln(pd, m, "docs/x.md", "Die Beispielstraßenbahn fährt.")


def test_ohne_strasse_und_plz_ergibt_die_anschrift_keine_muster(pd, tmp_path):
    wurzel = _projekt(tmp_path, PROFIL.replace("Musterweg 1, 12345 Musterstadt (Rhein-Main)", "Musterstadt"))
    m = pd.muster_laden(wurzel, db_pfad=_db(tmp_path), extra=tmp_path / "gibt_es_nicht.txt")
    assert m.anschrift == ()
    assert m.vollstaendig


def test_quellen_ueber_die_umgebung(pd, tmp_path, monkeypatch):
    """Ohne Parameter: Datenbank unter `BMS_DATA_DIR`, Musterdatei unter `BMS_SECRETS_DIR` (zur
    Laufzeit gelesen), Profil unter `<projekt_root>/config`."""
    wurzel = _projekt(tmp_path)
    daten = tmp_path / "daten"
    daten.mkdir()
    (daten / "bewerbung.sqlite").write_bytes(_db(tmp_path, company=["Nordfeld Systeme"]).read_bytes())
    geheim = tmp_path / "geheim"
    geheim.mkdir()
    (geheim / "pruefmuster.txt").write_text("Hans Altmeier\n", encoding="utf-8")
    monkeypatch.setenv("BMS_DATA_DIR", str(daten))
    monkeypatch.setenv("BMS_SECRETS_DIR", str(geheim))

    m = pd.muster_laden(wurzel)

    assert m.vollstaendig and m.extra_gelesen
    assert m.firmen == ("Nordfeld Systeme",) and m.dritte == ("Hans Altmeier",)
    assert pd.datenbank_pfad(wurzel) == daten / "bewerbung.sqlite"
    assert pd.pruefmuster_pfad() == geheim / "pruefmuster.txt"

    # Ohne die Umgebungsvariablen: data/ im Projekt und der Ordner im Home
    monkeypatch.delenv("BMS_DATA_DIR")
    monkeypatch.delenv("BMS_SECRETS_DIR")
    assert pd.datenbank_pfad(wurzel) == wurzel / "data" / "bewerbung.sqlite"
    assert pd.pruefmuster_pfad().name == "pruefmuster.txt"
    assert pd.pruefmuster_pfad().parent.name == ".bewerbung_mgmt_secrets"


def test_datenbank_wird_nur_lesend_geoeffnet(pd, quellen):
    wurzel, db, extra = quellen
    vorher = (hashlib.sha256(db.read_bytes()).hexdigest(), sorted(p.name for p in db.parent.iterdir()))

    pd.muster_laden(wurzel, db_pfad=db, extra=extra)

    nachher = (hashlib.sha256(db.read_bytes()).hexdigest(), sorted(p.name for p in db.parent.iterdir()))
    assert nachher == vorher                       # kein Byte geändert, kein Journal daneben


def test_datenbank_pfad_mit_leerzeichen_und_sonderzeichen(pd, tmp_path):
    ordner = tmp_path / "Mobile Documents" / "Ordner %20 #1"
    ordner.mkdir(parents=True)
    db = _db(ordner, company=["Nordfeld Systeme"])
    m = pd.muster_laden(_projekt(tmp_path), db_pfad=db, extra=tmp_path / "gibt_es_nicht.txt")
    assert m.datenbank_gelesen and m.firmen == ("Nordfeld Systeme",)


# ── Fehlende Quellen: still aus, vollstaendig falsch ────────────────────────────────────────────

def test_ohne_profil_entfallen_die_profilregeln_still(pd, tmp_path):
    wurzel = _projekt(tmp_path, None)
    db = _db(tmp_path, company=["Nordfeld Systeme"], contact=["Anna Beispiel"])
    m = pd.muster_laden(wurzel, db_pfad=db, extra=tmp_path / "gibt_es_nicht.txt")

    assert not m.vollstaendig and not m.profil_gelesen and m.datenbank_gelesen
    assert m.namen == () and m.anschrift == () and m.kontakt == () and m.konten == ()
    assert any("Profil" in h for h in m.hinweise)
    # Datenbank-Regeln laufen weiter
    assert "Dritte Personen" in _regeln(pd, m, "docs/x.md", "Danke an Anna Beispiel.")
    assert _regeln(pd, m, "docs/x.md", "Max Mustermann wohnt im Musterweg 1.") == set()


def test_ohne_datenbank_entfallen_firmen_und_dritte_still(pd, tmp_path):
    wurzel = _projekt(tmp_path)
    m = pd.muster_laden(wurzel, db_pfad=tmp_path / "fehlt.sqlite", extra=tmp_path / "gibt_es_nicht.txt")

    assert not m.vollstaendig and m.profil_gelesen and not m.datenbank_gelesen
    assert m.firmen == () and m.dritte == () and m.db_pfad is None
    assert any("Datenbank" in h for h in m.hinweise)
    assert "Anschrift" in _regeln(pd, m, "docs/x.md", "Im Musterweg.")           # Profilregeln laufen


def test_ohne_alles_laufen_nur_die_allgemeinen_regeln(pd, tmp_path):
    m = pd.muster_laden(tmp_path / "leer", db_pfad=tmp_path / "fehlt.sqlite", extra=tmp_path / "x.txt")

    assert not m.vollstaendig and len(m.hinweise) == 2
    text = ("Max Mustermann, Musterweg 1, 12345 Musterstadt, Anna Beispiel, "
            + _mail("max", "beispiel.de"))
    assert _regeln(pd, m, "docs/x.md", text) == set()
    # allgemeine Regeln gelten weiter
    assert _regeln(pd, m, "docs/x.md", _mail("jemand", "fremde-firma.de")) == {"E-Mail-Adressen"}
    assert _regeln(pd, m, "docs/x.md", _id("Job", 498)) == {"Bestands-IDs"}


@pytest.mark.parametrize("inhalt", [b"das ist keine sqlite-datei", b""])
def test_unlesbare_datenbank_ist_nicht_gelesen(pd, tmp_path, inhalt):
    db = tmp_path / "kaputt.sqlite"
    db.write_bytes(inhalt)
    m = pd.muster_laden(_projekt(tmp_path), db_pfad=db, extra=tmp_path / "gibt_es_nicht.txt")
    assert not m.vollstaendig and not m.datenbank_gelesen and m.profil_gelesen
    assert any("Datenbank" in h for h in m.hinweise)


def test_datenbank_ohne_bms_tabellen_ist_nicht_gelesen(pd, tmp_path):
    db = tmp_path / "fremd.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE etwas_anderes (x TEXT)")
    conn.commit()
    conn.close()
    m = pd.muster_laden(_projekt(tmp_path), db_pfad=db, extra=tmp_path / "gibt_es_nicht.txt")
    assert not m.datenbank_gelesen and not m.vollstaendig


def test_aeltere_datenbank_ohne_kontakttabelle_wird_gelesen(pd, tmp_path):
    db = tmp_path / "alt.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE company (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO company (name) VALUES ('Nordfeld Systeme GmbH')")
    conn.commit()
    conn.close()
    m = pd.muster_laden(_projekt(tmp_path), db_pfad=db, extra=tmp_path / "gibt_es_nicht.txt")
    assert m.datenbank_gelesen and m.vollstaendig and m.firmen == ("Nordfeld Systeme",) and m.dritte == ()


def test_profil_ohne_namen_zaehlt_nicht_als_gelesen(pd, tmp_path):
    profil = PROFIL.replace("- **Name:** Max Mustermann", "- **Name:**")
    m = pd.muster_laden(_projekt(tmp_path, profil), db_pfad=_db(tmp_path), extra=tmp_path / "x.txt")
    assert not m.vollstaendig and not m.profil_gelesen and m.namen == ()
    assert any("Namen" in h for h in m.hinweise)
    assert "Musterweg" in m.anschrift                       # der Rest des Profils wird trotzdem genutzt


def test_profil_mit_ungueltiger_kodierung_ist_nicht_gelesen(pd, tmp_path):
    wurzel = _projekt(tmp_path, None)
    (wurzel / "config" / "profil.md").write_bytes(b"\xff\xfe\x00 kein utf-8 \x80")
    m = pd.muster_laden(wurzel, db_pfad=_db(tmp_path), extra=tmp_path / "x.txt")
    assert not m.profil_gelesen and not m.vollstaendig


def test_musterdatei_ist_freiwillig_und_aendert_vollstaendig_nicht(pd, quellen):
    wurzel, db, _extra = quellen
    ohne = pd.muster_laden(wurzel, db_pfad=db, extra=wurzel / "nicht_da.txt")
    assert ohne.vollstaendig and not ohne.extra_gelesen
    assert "Hans Altmeier" not in ohne.dritte


def test_telefon_beispielnummer_und_zu_kurzes_zaehlt_nicht(pd, tmp_path):
    db = _db(tmp_path)
    for kontakt in (_tel(" 170 1234567"), "0170 1234567", "12 34"):
        profil = PROFIL.replace("069 5550123", kontakt)
        m = pd.muster_laden(_projekt(tmp_path, profil), db_pfad=db, extra=tmp_path / "x.txt")
        assert m.telefon == (), kontakt


def test_support_adresse_des_herausgebers_ist_kein_privates_muster(pd, tmp_path):
    profil = PROFIL.replace(_mail("max", "beispiel.de"), "info@daube.tech")
    m = pd.muster_laden(_projekt(tmp_path, profil), db_pfad=_db(tmp_path), extra=tmp_path / "x.txt")
    assert "info@daube.tech" not in m.kontakt and "info@" not in m.kontakt


# ── Regeln mit Mustern: je ein Fund und eine Gegenprobe, in beiden Umfängen ─────────────────────

@pytest.mark.parametrize("umfang", UMFAENGE)
def test_regel_anschrift(pd, muster, umfang):
    assert "Anschrift" in _regeln(pd, muster, "docs/ANLEITUNG.md", "Wohnhaft im Musterweg seit Jahren.", umfang)
    assert "Anschrift" in _regeln(pd, muster, "docs/ANLEITUNG.md", "Postleitzahl 12345 in der Mitte", umfang)
    assert "Anschrift" in _regeln(pd, muster, "docs/ANLEITUNG.md", "früher im ALTWEG 3", umfang)      # Musterdatei
    # auch in den Rechtstexten, ohne Ausnahme
    assert "Anschrift" in _regeln(pd, muster, "frontend/src/rechtliches/ueber.md", "Musterweg 1", umfang)
    # Gegenproben: nur ganze Wörter und ganze Zahlen
    for text in ("Der Musterwegweiser steht dort.", "Nummer 123456 und 912345", "Ein Musterhaus."):
        assert "Anschrift" not in _regeln(pd, muster, "docs/ANLEITUNG.md", text, umfang), text


@pytest.mark.parametrize("umfang", UMFAENGE)
def test_regel_private_kontaktdaten(pd, muster, umfang):
    kontakt = lambda text: "Private Kontaktdaten" in _regeln(pd, muster, "docs/ANLEITUNG.md", text, umfang)

    assert kontakt("Kontakt: " + _mail("MAX", "BEISPIEL.DE"))                       # Schreibweise egal
    assert kontakt("Kontakt: " + _mail("max", "anbieter.example.com"))              # Vorderteil, andere Domain
    assert kontakt("Kontakt: " + _mail("max.mustermann", "anbieter.example.com"))   # vorname.nachname@
    assert kontakt("Profil: https://www.linkedin.com/in/max-mustermann-4711")       # Profil-Pfad als Anfang
    assert kontakt("Frühere Adresse " + _mail("alte.adresse", "beispiel.de"))       # aus der Musterdatei
    assert kontakt("Ordner " + _benutzerpfad("maxmustermann"))                      # Kontoname
    assert kontakt("Tel. 069 5550123") and kontakt("Tel. 069/55 50 123")           # Profil-Telefon, jede Schreibweise
    assert kontakt("Tel. " + _tel(" 69 5550123"))

    # Gegenproben
    assert not kontakt("Kontakt: info@daube.tech")                                 # Support-Adresse
    assert not kontakt("Kontakt: " + _mail("climax", "beispiel.de"))               # Vorderteil mitten im Namen
    assert not kontakt("Profil: https://www.linkedin.com/in/jemand-anderes")
    assert not kontakt("Datei CV_MaxMustermann_Firma_DE.docx")                     # Kontoname nur klein
    assert not kontakt("Tel. " + _tel(" 170 1234567"))                             # Beispielnummer
    assert not kontakt("Nummer 0695550123456 ist länger")


@pytest.mark.parametrize("umfang", UMFAENGE)
def test_regel_dritte_personen(pd, muster, umfang):
    dritte = lambda text: "Dritte Personen" in _regeln(pd, muster, "docs/ANLEITUNG.md", text, umfang)

    assert dritte("Danke an Anna Beispiel für den Tipp.")
    assert dritte("Danke an ANNA   BEISPIEL für den Tipp.")                         # Schreibweise, Leerraum
    assert dritte("Annas Freund ist Anna Beispiels Chef.")                          # Genitiv-s
    assert dritte("Mail von Hans Altmeier")                                         # aus der Musterdatei
    assert not dritte("Danke an das Team für den Tipp.")
    assert not dritte("Anna Beispielhaft schrieb.")                                 # Buchstaben dahinter
    assert not dritte("Mehr zu Recruiting Team und Jobs Karriere.")                 # keine Personennamen
    assert not dritte("Eine Banna Beispiel gibt es nicht.")                         # Buchstaben davor


@pytest.mark.parametrize("umfang", UMFAENGE)
def test_regel_email_erlaubte_adresse_ok_fremde_adresse_fund(pd, muster, umfang):
    email = lambda text: "E-Mail-Adressen" in _regeln(pd, muster, "docs/ANLEITUNG.md", text, umfang)

    assert not email("Support: info@daube.tech")
    assert not email("Beispiel: " + _mail("berater", "personalberatung.example.de"))
    assert not email("Beispiel: " + _mail("a", "b.de") + " und " + _mail("ich", "gmx.de"))
    assert not email(_mail("jobalerts-noreply", "linkedin.com"))
    # für Beispiele reservierte Namen (RFC 2606) sind nie echt
    for domain in ("example.net", "dienst.example", "mail.invalid", "host.test", "rechner.localhost"):
        assert not email("Beispiel: " + _mail("jemand", domain)), domain
    assert email("Kontakt: " + _mail("jemand", "fremde-firma.de"))
    assert email("Kontakt: " + _mail("jemand", "test.de")) and email("Kontakt: " + _mail("jemand", "example.test.de"))
    assert email("Kontakt: " + _mail("jemand", "example.de.boese.com"))              # Endung täuscht nur


@pytest.mark.parametrize("umfang", UMFAENGE)
def test_regel_telefon_beispielnummer_ok_andere_nummer_fund(pd, muster, umfang):
    tel = lambda text: "Telefonnummern" in _regeln(pd, muster, "BMS_Install_MAC.md", text, umfang)

    assert not tel("Kontakt: " + _mail("max.mustermann", "example.com") + " · " + _tel(" 170 1234567"))
    assert tel("Kontakt: " + _tel(" 69 87654321"))
    assert tel("Kontakt: " + _tel("69/8765-4321"))
    assert tel("Kontakt: " + _tel(" 30 1234"))                                      # sechs Ziffern nach +49
    assert tel("Kontakt: " + _tel(" 170 12345678"))                                 # länger als die Beispielnummer

    # Gegenproben: Platzhalter mit weniger als sechs Ziffern und die Beispielnummer in anderer Schreibweise
    for platzhalter in (" 170 1", " 30 2", "-170-1", " 30 123"):
        assert not tel("Kontakt: " + _tel(platzhalter)), platzhalter
    for schreibweise in (" 170 1234567", "-170-1234567", "1701234567", " 170/1234567"):
        assert not tel("Kontakt: " + _tel(schreibweise)), schreibweise


@pytest.mark.parametrize("umfang", UMFAENGE)
def test_regel_bestands_ids_ueberall_und_alle_formen(pd, muster, umfang):
    ids = lambda pfad, text: "Bestands-IDs" in _regeln(pd, muster, pfad, text, umfang)

    assert not ids(".claude/skills/jobsuche/SKILL.md", "Beispiel: eine Stelle ohne Nummer.")
    assert ids("docs/ANLEITUNG.md", "Siehe " + _id("Job", 498) + " als Beispiel.")    # in jeder Textdatei
    for wort, nummer in (("Job", "498"), ("Jobs", "106/202"), ("Task", "1746"), ("Tasks", "685/686"),
                         ("Mail", "255"), ("Mails", "47, 72"), ("Lauf", "1058"), ("Läufe", "12")):
        assert ids(".claude/skills/jobsuche/SKILL.md", f"{wort} {nummer}"), wort
    assert ids("x.md", "Siehe " + "Job" + "118" + " an.")                            # ohne Leerzeichen
    assert not ids("x.md", "Job 7 reicht nicht")                                     # einstellig


def test_regel_zeilenenden_nur_im_paket(pd):
    """`.bat` braucht CRLF, `.command`/`.sh`/`.py` dürfen kein CR enthalten -- Sache des Kundenpakets.
    Im öffentlichen Umfang entfällt die Regel (Git erledigt die Zeilenenden über `.gitattributes`)."""
    leer = pd.Muster()

    def regeln(pfad, inhalt, umfang="paket"):
        return {f.regel for f in pd.pruefen([pd.Eintrag(pfad, 0o644, inhalt)], leer, umfang=umfang)}

    assert regeln("update_windows.bat", b"@echo off\r\necho hi\r\n") == set()
    assert regeln("update_windows.bat", b"@echo off\r\necho hi\n") == {"Zeilenende"}
    assert regeln("update.command", b"#!/bin/zsh\necho hi\n") == set()
    assert regeln("update.command", b"#!/bin/zsh\r\necho hi\r\n") == {"Zeilenende"}
    assert regeln("scripts/refresh_views.sh", b"#!/bin/sh\r\n") == {"Zeilenende"}
    assert regeln("backend/app/selbsttest.py", b"import app.main\r\n") == {"Zeilenende"}
    assert regeln("docs/ANLEITUNG.md", b"Text mit \r Wagenruecklauf\n") == set()      # andere Endung
    assert regeln("update_windows.bat", b"@echo off\r\necho hi\n", "oeffentlich") == set()


@pytest.mark.parametrize("umfang", UMFAENGE)
def test_binaerdateien_werden_nur_auf_zeilenenden_geprueft(pd, muster, umfang):
    inhalt = b"\xff\xfe\x00\x01 Musterweg " + _mail("jemand", "fremde-firma.de").encode()
    assert _funde(pd, muster, "assets/bild.png", inhalt.decode("latin-1"), umfang) != []   # als Text gelesen
    f = pd.pruefen([pd.Eintrag("assets/bild.png", 0o644, inhalt)], muster, umfang=umfang)
    assert f == []                                                                         # echte Binärdatei


def test_ausschnitt_zeigt_die_originalzeile_gekuerzt(pd, muster):
    zeile = "x " * 200 + "Musterweg"
    f = _funde(pd, muster, "docs/x.md", f"erste Zeile\n{zeile}\n")
    assert [(g.zeile, g.regel) for g in f] == [(2, "Anschrift")]
    assert len(f[0].ausschnitt) <= 160 and f[0].ausschnitt.endswith("…")
    assert f[0].ausschnitt.startswith("x x x")


def test_unbekannter_umfang_ist_ein_fehler(pd, muster):
    with pytest.raises(ValueError):
        pd.pruefen([], muster, umfang="alles")


# ── Name des Nutzers ────────────────────────────────────────────────────────────────────────────

def test_name_im_paket_nur_kundentexte_und_programmtext(pd, muster):
    """Umfang paket: Kundentext-Pfade (Zeilen), Strings in Python-Dateien (ohne Docstrings), TS/TSX-Code
    (ohne Kommentare). Kommentare und Docstrings dürfen den Namen nennen, andere Dateien auch."""
    name = lambda pfad, text: {f.regel for f in _funde(pd, muster, pfad, text) if f.regel.startswith("Name")}

    assert name("docs/ANLEITUNG.md", "Max Mustermann hat das System gebaut.") == {"Name des Nutzers in Kundentexten"}
    assert name("README.md", "von Mustermann") == {"Name des Nutzers in Kundentexten"}
    assert name(".claude/skills/x/SKILL.md", "Frau MUSTERMANN") == {"Name des Nutzers in Kundentexten"}
    assert name("docs/ANLEITUNG.md", "Mustermanns Sicht") == {"Name des Nutzers in Kundentexten"}   # Genitiv
    assert name("docs/ANLEITUNG.md", "Das Mustermannsche Prinzip") == set()                       # Buchstaben dahinter
    assert name("backend/app/sonstiges.py", "# Kommentar von Max Mustermann\n") == set()          # kein Kundentext
    assert name("backend/app/sonstiges.py", '"""Modul für Mustermann."""\nx = 1\n') == set()       # Docstring

    assert name("backend/pipeline/beispiel.py", 'NAME = "Mustermann"\n') == {"Name des Nutzers im Python-Programmtext"}
    assert name("backend/pipeline/beispiel.py", 'NAME = f"Hallo {x} Max"\n') == {"Name des Nutzers im Python-Programmtext"}
    assert name("backend/pipeline/beispiel.py", "def f(:\n  Mustermann") == set()                 # kein gültiges Python

    assert name("frontend/src/Beispiel.tsx", "// Kommentar über Mustermann\nconst x = 1;\n") == set()
    assert name("frontend/src/Beispiel.tsx", "/* Mustermann */\nconst x = 1;\n") == set()
    assert name("frontend/src/Beispiel.tsx", "const x = <div>Mustermann</div>;\n") == {
        "Name des Nutzers im TS/TSX-Programmtext"}
    assert name("frontend/src/Beispiel.ts", "const x = 'Max';\n") == {"Name des Nutzers im TS/TSX-Programmtext"}
    # Dateinamen-Beispiele mit zusammengeschriebenem Namen sind kein Wort des Namens
    assert name("docs/ANLEITUNG.md", "Datei CV_MaxMustermann_Firma_DE.docx") == set()


@pytest.mark.parametrize("pfad, text", [
    ("backend/app/sonstiges.py", "# Kommentar von Max Mustermann"),
    ("backend/app/sonstiges.py", '"""Modul für Mustermann."""'),
    ("frontend/src/Beispiel.tsx", "// Kommentar über Mustermann"),
    ("tasks/notiz.md", "Mustermann schrieb"),
    ("docs/ANLEITUNG.md", "Frau Mustermann sagt"),
    ("backend/tests/test_x.py", 'ABSENDER = "Max"'),
    ("scripts/x.sh", "# von Max"),
    ("README.md", "Gebaut von Max Mustermann"),           # README ausserhalb der Abschnitte zu Autor und Lizenz
    ("CHANGELOG.md", "Dank an Mustermann"),
])
def test_name_im_oeffentlichen_umfang_ueberall_ein_fund(pd, muster, pfad, text):
    assert "Name des Nutzers" in _regeln(pd, muster, pfad, text, "oeffentlich"), pfad


def test_name_zuschreibungsliste_nur_fuer_den_namen(pd, muster):
    name = lambda pfad, text: [f for f in _funde(pd, muster, pfad, text, "oeffentlich") if f.regel == "Name des Nutzers"]
    text = "Copyright 2026 Max Mustermann"

    for pfad in ("NOTICE", "LICENSE", "frontend/src/rechtliches/ueber.md"):
        assert name(pfad, text) == [], pfad
    assert name("NOTICE.txt", text) != [] and name("docs/NOTICE", text) != []                    # exakte Pfade

    # In der Zuschreibungsliste laufen alle ANDEREN Regeln weiter
    regeln = _regeln(pd, muster, "NOTICE", text + ", Musterweg 1, " + _mail("max", "beispiel.de"), "oeffentlich")
    assert {"Anschrift", "Private Kontaktdaten"} <= regeln and "Name des Nutzers" not in regeln

    # Im Paket-Umfang gibt es die Liste nicht, dort gilt der Name nur in den Kundentext-Pfaden
    assert _regeln(pd, muster, "NOTICE", text, "paket") == set()


def test_name_im_readme_nur_in_den_abschnitten_zu_autor_und_lizenz(pd, muster):
    readme = "\n".join([
        "# Programm",                                   # 1
        "Gebaut von Max Mustermann.",                   # 2  Fund (Einleitung)
        "## Installation",                              # 3
        "Dazu fragt Mustermann nach.",                  # 4  Fund
        "## Autor",                                     # 5
        "Max Mustermann, www.beispiel.de",              # 6  erlaubt
        "### Kontakt zum Autor",                        # 7
        "Mustermann per Brief.",                        # 8  erlaubt (Unterabschnitt)
        "## Mitmachen",                                 # 9
        "Fragen an Mustermann.",                        # 10 Fund
        "## Lizenz und Haftung",                        # 11
        "```",                                          # 12
        "# Kein Abschnitt, nur ein Kommentar im Codeblock",   # 13
        "```",                                          # 14
        "Lizenz: Apache-2.0, Copyright Mustermann",     # 15 erlaubt
        "# Anhang",                                     # 16
        "Noch einmal Mustermann.",                      # 17 Fund
    ])
    zeilen = {f.zeile for f in _funde(pd, muster, "README.md", readme, "oeffentlich") if f.regel == "Name des Nutzers"}
    assert zeilen == {2, 4, 10, 17}

    # Dieselbe Ausnahme gilt nur für README.md, nicht für andere Markdown-Dateien
    zeilen2 = {f.zeile for f in _funde(pd, muster, "docs/README.md", readme, "oeffentlich")
               if f.regel == "Name des Nutzers"}
    assert zeilen2 == {2, 4, 6, 8, 10, 15, 17}


def test_name_marke_und_domain_des_herausgebers_zaehlen_nicht(pd):
    """Der Nachname eines Herausgebers kann zugleich seine Marke sein. Die Marke (`MARKE`) zählt nicht
    als Nachname, in keiner Schreibweise mit Trenner; ein echtes Vorkommen des Nachnamens schon."""
    nachname = pd.MARKE.split(".")[0]
    m = pd.Muster(namen=("Anna", nachname))
    marke = pd.MARKE
    harmlos = (f"Mehr unter {marke}", f"https://{marke.lower()}/impressum.html", f"Support: info@{marke.lower()}",
               f"{marke.replace('.', '-')} und {marke.replace('.', '_')} und {marke.replace('.', ' ')}",
               f"{nachname}{marke.split('.')[1]} ohne Trenner", f"Pfad assets/{marke.lower().replace('.', '-')}-logo.png")
    for text in harmlos:
        for umfang in UMFAENGE:
            assert _regeln(pd, m, "docs/ANLEITUNG.md", text, umfang) == set(), (text, umfang)

    assert "Name des Nutzers" in _regeln(pd, m, "docs/ANLEITUNG.md", f"Frau {nachname} schrieb.", "oeffentlich")
    assert "Name des Nutzers" in _regeln(pd, m, "docs/ANLEITUNG.md", f"{marke} von Anna {nachname}", "oeffentlich")
    assert "Name des Nutzers" in _regeln(pd, m, "docs/ANLEITUNG.md", f"Herr {nachname}, {marke}", "oeffentlich")


# ── Der Name des öffentlichen Repos ist die einzige erlaubte Form des Kontonamens ───────────────

def _repo_teile(pd):
    konto, name = pd.OEFFENTLICHES_REPO.split("/")
    return pd.OEFFENTLICHES_REPO, konto, name


def test_oeffentliches_repo_konstante_ist_der_gewollte_name(pd):
    konto, name = pd.OEFFENTLICHES_REPO.split("/")
    assert konto and name == "BewerbungsMgmtSystem"


@pytest.mark.parametrize("umfang", UMFAENGE)
def test_oeffentliches_repo_ist_kein_fund(pd, umfang):
    repo, konto, _name = _repo_teile(pd)
    m = pd.Muster(konten=(konto,))
    erlaubt = [
        ("BMS_Install_MAC.md", f"Neue Versionen: https://github.com/{repo}/releases"),
        ("BMS_Install_MAC.md", f"und lädt von https://github.com/{repo}/releases/latest."),
        ("BMS_Install_Windows.md", f"Melden Sie ein Anliegen unter https://github.com/{repo}/issues ein."),
        ("BMS_Install_MAC.md", f'curl -sS "https://api.github.com/repos/{repo}/releases/latest"'),
        ("BMS_Install_Windows.md",
         f'curl.exe -fsSL -o "ZIP" "https://github.com/{repo}/releases/download/vVERSION/BMS_VERSION.zip"'),
        ("docs/ANLEITUNG.md", f"Das Repository heißt `{repo}`."),
        ("docs/ANLEITUNG.md", f"Repository: {repo}."),
        ("docs/ANLEITUNG.md", f"(github.com/{repo})"),
        ("backend/app/update_pruefen.py", f'GITHUB_REPO = "{repo}"'),
        ("backend/app/update_pruefen.py", f"# Quelle: https://github.com/{repo}/releases/latest"),
        ("frontend/src/pages/Einstellungen.tsx", f"const REPO = '{repo}'"),
        ("docs/ANLEITUNG.md", f"https://github.com/{repo} und {repo}"),       # zweimal in einer Zeile
    ]
    for pfad, text in erlaubt:
        assert pd.pruefen([pd.Eintrag(pfad, 0o644, text.encode())], m, umfang=umfang) == [], text


@pytest.mark.parametrize("umfang", UMFAENGE)
def test_oeffentliches_repo_ausnahme_ist_eng_alles_andere_bleibt_fund(pd, umfang):
    repo, konto, name = _repo_teile(pd)
    m = pd.Muster(konten=(konto,))
    fund = [
        "venv unter `" + _benutzerpfad(konto) + "`",                                     # Benutzerpfad
        f"Ordner /Users/{konto}/{name}",                                                  # Pfad mit Repo-Namen
        f"~/{konto}/{name}",
        f"Quelle: https://github.com/{konto}/bewerbung-mgmt-system",                      # das private Repo
        f"https://github.com/{konto}/bewerbung-mgmt-system/issues",
        f"{konto}/{name}X",                                                               # längerer Name
        f"https://github.com/{konto}/{name}Xreleases",
        f"{repo}-alt", f"{repo}_alt", f"{repo}.alt",
        f"{konto}/{name.lower()}",                                                        # andere Schreibweise
        f"https://github.com/{konto}/{name.lower()}/releases",
        f"{konto}/{name.upper()}",
        f"x{repo}",                                                                       # fremdes Konto
        f"https://github.com/x{repo}",
        f"https://evilgithub.com/{repo}",                                                 # fremder Host
        f"https://example.com/{repo}",
        f"{repo} und /Users/{konto}/x",                                                   # Repo + Pfad
        f"https://linkedin.com/in/{konto}-123",
    ]
    for text in fund:
        funde = pd.pruefen([pd.Eintrag("docs/ANLEITUNG.md", 0o644, text.encode())], m, umfang=umfang)
        assert any(f.regel == "Private Kontaktdaten" for f in funde), text
        # Der Ausschnitt zeigt die ORIGINALzeile, nicht die für die Suche bereinigte.
        assert all(text.strip()[:50] in f.ausschnitt for f in funde if f.regel == "Private Kontaktdaten")


def test_oeffentliches_repo_python_string_literal(pd):
    """Im Paket-Umfang prüft die Namensregel String-Literale: Der Name des öffentlichen Repos ist dort
    erlaubt (bloß, als URL, im f-String), jeder andere Wert mit dem Kontonamen nicht."""
    repo, konto, name = _repo_teile(pd)
    m = pd.Muster(konten=(konto,), namen=(konto,))

    def funde(quelltext):
        return pd.pruefen([pd.Eintrag("backend/app/beispiel.py", 0o644, quelltext.encode())], m, umfang="paket")

    for quelltext in (f'GITHUB_REPO = "{repo}"\n',
                      f'SEITE = "https://github.com/{repo}/releases/"\n',
                      'url = f"https://github.com/' + repo + '/releases/download/v{version}/"\n',
                      f'url = f"https://api.github.com/repos/{repo}/releases/latest"\n'):
        assert funde(quelltext) == [], quelltext
    for quelltext in (f'PFAD = "/Users/{konto}/{name}"\n', f'PFAD = "/Users/{konto}/x"\n',
                      f'REPO = "https://github.com/{konto}/bewerbung-mgmt-system"\n',
                      f'REPO = "{konto}/{name}X"\n', f'REPO = "x{repo}"\n'):
        regeln = {f.regel for f in funde(quelltext)}
        assert "Private Kontaktdaten" in regeln, quelltext

    # Der Kontoname ist nur als Konto-Schreibweise ausgenommen: steht im selben Literal noch ein
    # Wort des Namens, bleibt das ein Fund der Namensregel.
    mit_name = pd.Muster(konten=(konto,), namen=("Beispielname",))
    f = pd.pruefen([pd.Eintrag("backend/app/beispiel.py", 0o644,
                                f'TEXT = "{repo} von Beispielname"\n'.encode())], mit_name, umfang="paket")
    assert [g.regel for g in f] == ["Name des Nutzers im Python-Programmtext"]


def test_oeffentliches_repo_ausnahme_gilt_nur_fuer_kontakt_und_namensregel(pd):
    """Neben dem Repo-Namen bleiben Anschrift, fremde Adresse und Dritte ein Fund."""
    repo, konto, _name = _repo_teile(pd)
    m = pd.Muster(konten=(konto,), anschrift=("Musterweg",), dritte=("Anna Beispiel",))
    zeile = f"https://github.com/{repo}/issues, Musterweg 1, {_mail('jemand', 'fremde-firma.de')}, Anna Beispiel"
    for umfang in UMFAENGE:
        regeln = _regeln(pd, m, "docs/ANLEITUNG.md", zeile, umfang)
        assert {"Anschrift", "E-Mail-Adressen", "Dritte Personen"} <= regeln
        assert "Private Kontaktdaten" not in regeln


# ── Pfadgebundene Ausnahme: fremder Wortlaut ────────────────────────────────────────────────────

TEXTE = "frontend/src/rechtliches/drittlizenzen_texte.txt"


def test_fremder_wortlaut_konstante(pd):
    assert pd._FREMDER_WORTLAUT == (TEXTE,)


@pytest.mark.parametrize("umfang", UMFAENGE)
def test_fremder_wortlaut_email_firma_und_name_entfallen(pd, muster, umfang, monkeypatch):
    """P2-77: In der Wortlaut-Datei bleibt eine Autoren-Adresse, eine Copyright-Zeile mit Firmennamen und
    ein Autor mit dem Namen des Nutzers unverändert. Dieselben Zeilen in der Übersicht, der Nachbardatei
    oder einer anderen Datei bleiben Funde -- die Ausnahme gilt für genau einen Pfad."""
    autor = "Copyright (c) 2019 Beispiel-Autorin <" + _mail("autorin", "lizenzgeber-projekt.net") + ">"
    firma = "Copyright (c) 2020 Nordfeld Systeme, alle Rechte vorbehalten."
    person = "Copyright (c) 2018 Max Mustermann"

    for zeile in (autor, firma, person):
        assert _regeln(pd, muster, TEXTE, zeile, umfang) == set(), zeile

    for andere in ("frontend/src/rechtliches/drittlizenzen.md",         # die Übersicht, voll geprüft
                   "frontend/src/rechtliches/drittlizenzen_texte.txt.bak",   # kein Muster, exakter Pfad
                   "frontend/src/rechtliches/eula.md", "docs/ANLEITUNG.md"):
        assert "E-Mail-Adressen" in _regeln(pd, muster, andere, autor, umfang), andere
        assert "Firmennamen aus dem Bewerbungsverlauf" in _regeln(pd, muster, andere, firma, umfang), andere
    assert "Name des Nutzers" in _regeln(pd, muster, "docs/ANLEITUNG.md", person, "oeffentlich")

    # Gegenprobe: ohne die Konstante ist es auch in der Wortlaut-Datei ein Fund
    monkeypatch.setattr(pd, "_FREMDER_WORTLAUT", ())
    assert _regeln(pd, muster, TEXTE, autor, umfang) == {"E-Mail-Adressen"}
    assert _regeln(pd, muster, TEXTE, firma, umfang) == {"Firmennamen aus dem Bewerbungsverlauf"}


@pytest.mark.parametrize("umfang", UMFAENGE)
def test_fremder_wortlaut_uebrige_regeln_bleiben(pd, muster, umfang):
    """Kontaktdaten, Dritte Personen, Telefon, Bestands-IDs und Anschrift schlagen auch dort an."""
    regeln = lambda text: _regeln(pd, muster, TEXTE, text, umfang)

    assert regeln("Copyright (c) 2021 " + _mail("max", "fremde-firma.de")) == {"Private Kontaktdaten"}
    assert "Private Kontaktdaten" in regeln("Quelle liegt unter " + _benutzerpfad("maxmustermann"))
    assert regeln("Danke an Anna Beispiel für den Beitrag.") == {"Dritte Personen"}
    assert regeln("Rückfragen unter " + _tel(" 69 87654321")) == {"Telefonnummern"}
    assert regeln("Siehe " + _id("Job", 498) + " als Beispiel.") == {"Bestands-IDs"}
    assert regeln("Wohnhaft im Musterweg") == {"Anschrift"}


# ── Firmennamen aus dem Bewerbungsverlauf ───────────────────────────────────────────────────────

FIRMA = "Firmennamen aus dem Bewerbungsverlauf"


@pytest.mark.parametrize("umfang", UMFAENGE)
def test_firmennamen_regel_rechtsform_mindestlaenge_erlaubte_liste_schreibweise(pd, muster, umfang):
    firma = lambda pfad, text: FIRMA in _regeln(pd, muster, pfad, text, umfang)

    # Treffer: Kernform nach Abtrennen der Rechtsform, GROSS-/KLEINSCHREIBUNGS-GENAU, ganzes Wort
    assert firma("docs/ANLEITUNG.md", "Absage von Nordfeld Systeme kam schnell.")
    assert firma("docs/ANLEITUNG.md", "(Nordfeld Systeme)")
    assert not firma("docs/ANLEITUNG.md", "absage von nordfeld systeme kam schnell.")       # andere Schreibweise
    assert not firma("docs/ANLEITUNG.md", "Nordfeld Systemen und Nordfeld Systemeinheit")   # kein ganzes Wort
    assert not firma("docs/ANLEITUNG.md", "Die Firma AB war schnell.")                      # unter der Mindestlänge
    # funktionale Nennung (Infrastruktur): in der Datenbank, aber erlaubt
    assert not firma("backend/pipeline/user_profile.py", "# Google Drive Export, s. models.py")
    # alle vier Tabellen werden gelesen
    assert firma("x.md", "Kontakt bei Silberkiel Consulting notiert.")                      # targetcompany
    assert firma("x.md", "Mandat über Rautental Mandate gemeldet.")                         # headhunter
    assert firma("x.md", "Stelle bei Nordfeld Systeme")                                     # company und job


def test_firmennamen_regel_ohne_datenbank_uebersprungen(pd):
    eintraege = [pd.Eintrag("x.md", 0o644, b"Nordfeld Systeme hat abgesagt.\n")]
    assert pd.pruefen(eintraege, pd.Muster(), umfang="paket") == []


def test_firmennamen_regel_unbekannt_und_leere_werte(pd, tmp_path):
    db = _db(tmp_path, company=["Unbekannt", "", "  ", "Nordfeld Systeme GmbH"], job=["Unbekannt"])
    m = pd.muster_laden(_projekt(tmp_path), db_pfad=db, extra=tmp_path / "x.txt")
    assert m.firmen == ("Nordfeld Systeme",)


@pytest.mark.parametrize("umfang", UMFAENGE)
def test_firmennamen_regel_pfadgebundene_ausnahme_nur_in_persona_dateien(pd, tmp_path, umfang):
    """Ein Firmenname kann zufällig auch der Nachname einer fiktiven Beirats-Persona sein -- dann bleibt er
    NUR in den Persona-/Charta-Dateien erlaubt, überall sonst weiter ein Fund. Der Persona-Nachname kommt
    aus dem Dateinamen `beirat-<vorname>-<nachname>.md` unter den geprüften Dateien."""
    db = _db(tmp_path, company=["Nordwind GmbH"])
    m = pd.muster_laden(_projekt(tmp_path), db_pfad=db, extra=tmp_path / "x.txt")
    assert m.firmen == ("Nordwind",)

    def e(pfad, text):
        return pd.Eintrag(pfad, 0o644, text.encode())

    persona = e(".claude/agents/beirat-erika-nordwind.md", "Du bist **Nordwind**, eine erfundene Beiratsfigur.\n")
    andere = [
        e("docs/BEIRAT-CHARTA.md", "- **Erika Nordwind** — erfundene Figur\n"),
        e(".claude/commands/beirat-basis.md", "- **Erika Nordwind** (beirat-erika-nordwind)\n"),
        e("backend/pipeline/irgendwas.py", "# Absage von Nordwind kam schnell.\n"),
        e(".claude/agents/beirat-erika-nordwind.txt", "Du bist **Nordwind**.\n"),       # nicht *.md
        e("docs/ANLEITUNG.md", "Nordwind kam vor.\n"),
    ]
    funde = pd.pruefen([persona] + andere, m, umfang=umfang)
    pfade = {f.pfad for f in funde if f.regel == FIRMA}
    assert pfade == {"backend/pipeline/irgendwas.py", ".claude/agents/beirat-erika-nordwind.txt",
                     "docs/ANLEITUNG.md"}

    # Ohne die Persona-Datei in der Liste gibt es keine Ausnahme
    ohne = pd.pruefen(andere[:2], m, umfang=umfang)
    assert {f.pfad for f in ohne if f.regel == FIRMA} == {"docs/BEIRAT-CHARTA.md", ".claude/commands/beirat-basis.md"}


# ── Nur im öffentlichen Umfang: Benutzerpfad und Dateipfad ──────────────────────────────────────

def test_regel_absoluter_benutzerpfad_nur_oeffentlich(pd):
    leer = pd.Muster()
    pfad = lambda text, umfang="oeffentlich": [f.regel for f in _funde(pd, leer, "docs/x.md", text, umfang)]

    fremd = ("Ordner " + _benutzerpfad("jemand"), "Ordner /home/" + "jemand/x", "Pfad C:" + "\\Users\\" + "jemand\\x",
             "Pfad C:/Users/" + "jemand/x", 'json "C:' + '\\\\Users\\\\' + 'jemand\\\\x"')
    for text in fremd:
        assert pfad(text) == ["Absoluter Benutzerpfad"], text
        assert pfad(text, "paket") == [], text
    harmlos = ("Ordner /Users/<name>/projekt", "Ordner /Users/Name/projekt", "Pfad C:" + "\\Users\\Name\\x",
               "Ordner /Users/$USER/x", "Ordner /Users/%USERNAME%/x", "Ordner ~/projekt und $HOME/projekt",
               "Muster /Users/|/home/", "Runner /home/runner/work", "Ordner /Users/Shared/x",
               "x /Users/... und /Users/{konto}", "https://example.com/Users", "Ordner /Users/")
    for text in harmlos:
        assert pfad(text) == [], text


def test_regel_dateipfad_nur_oeffentlich(pd, muster):
    """Auch der Dateiname darf nichts Persönliches tragen; der Fund steht auf Zeile 0 mit dem Pfad."""
    pfade = ("docs/Max_Mustermann_Lebenslauf.md", "docs/Anna_Beispiel_Notiz.md", "docs/Musterweg_Plan.md",
             "docs/Nordfeld Systeme Dossier.md", "assets/maxmustermann.png")
    for pfad in pfade:
        f = pd.pruefen([pd.Eintrag(pfad, 0o644, b"harmlos")], muster, umfang="oeffentlich")
        assert [(g.pfad, g.zeile) for g in f] == [(pfad, 0)], pfad
        assert "(Dateipfad)" in f[0].regel and f[0].ausschnitt == pfad
        assert pd.pruefen([pd.Eintrag(pfad, 0o644, b"harmlos")], muster, umfang="paket") == [], pfad
    assert pd.pruefen([pd.Eintrag("docs/Anleitung.md", 0o644, b"harmlos")], muster, umfang="oeffentlich") == []


def test_oeffentlicher_umfang_prueft_alle_dateien_ohne_pfadausnahme(pd, muster):
    """Dieselbe Anschrift in Dateien, die das Paket ausnimmt (Tests, tasks, Einmal-Skripte): im
    öffentlichen Umfang ein Fund, und zwar in jeder."""
    for pfad in ("tasks/todo.md", "backend/tests/test_x.py", "scripts/einmal.py", ".github/workflows/ci.yml",
                 "frontend/src/rechtliches/ueber.md", "NOTICE"):
        f = pd.pruefen([pd.Eintrag(pfad, 0o644, b"Wohnhaft im Musterweg\n")], muster, umfang="oeffentlich")
        assert [(g.pfad, g.regel) for g in f] == [(pfad, "Anschrift")]
