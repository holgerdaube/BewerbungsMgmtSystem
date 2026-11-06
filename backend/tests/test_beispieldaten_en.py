"""Tests: Beispieldaten („Benno Bewerbaer“) in zwei Sprachen und die Startsprache.

Muster wie `test_beispieldaten.py`: Alles läuft unter `tmp_path` (eigener Projekt-Root, Datenordner und
SQLite-Datei je Test), die Funktionen bekommen Pfade und Engine ausdrücklich übergeben. Die Sprache setzen
die Tests über `sprache_code=` oder, wo der Weg über die Oberfläche zählt, indem sie `app.sprache.aktuell`
auf die Test-Datenbank umlenken.

Der Test „Deutsch unverändert“ vergleicht gegen Prüfsummen, die mit dem Stand VOR der Mehrsprachigkeit
berechnet wurden (gleiche Funktionen, alter Modulstand).

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention).
"""
import hashlib
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

JETZT = datetime(2026, 10, 1, 9, 30)

# Prüfsummen des deutschen Ergebnisses vor der Mehrsprachigkeit (siehe Modulkopf).
GOLDEN_TEXTSPALTEN = "4e0a6e50d9e6fa0152276383e2f8f91d13ecb00214f35bb13b69ba135dbdfa34"
GOLDEN_PROFIL_MD = "b0029c1fc46f27b95729d0455db04f1acf738dff0f7f2b1423f85c77abcf7672"
GOLDEN_CV_DOKUMENT = "51054dc5e5a16c1728521a96cb4e15bbde2308346a8dfaecae653cce18f45249"


# ── Fixtures und Helfer ──────────────────────────────────────────────────────────────────────
@pytest.fixture()
def umgebung(tmp_path, monkeypatch):
    """Eigene Paket-Installation: Projekt-Root mit Manifest, Datenordner, leere Datenbank."""
    from sqlmodel import SQLModel, create_engine
    from app import db, models  # noqa: F401  (registriert alle Tabellen)

    monkeypatch.delenv("BMS_BEISPIELDATEN", raising=False)
    projekt = tmp_path / "projekt"
    daten = tmp_path / "daten"
    projekt.mkdir()
    daten.mkdir()
    (projekt / "bms_manifest.json").write_text("{}", encoding="utf-8")
    engine = create_engine(f"sqlite:///{daten / 'bewerbung.sqlite'}", connect_args=db.CONNECT_ARGS)
    SQLModel.metadata.create_all(engine)
    with engine.connect() as verbindung:
        for name, tabelle, ausdruck in db._UNIQUE_INDEXES:
            verbindung.exec_driver_sql(f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON {tabelle}({ausdruck})")
        verbindung.commit()
    yield SimpleNamespace(projekt=projekt, daten=daten, engine=engine, jetzt=JETZT)
    engine.dispose()


def _einspielen(u, sprache_code=None):
    from app import beispieldaten

    return beispieldaten.einspielen_falls_neu(
        False, projekt_root=u.projekt, daten_dir=u.daten, jetzt=u.jetzt, engine=u.engine,
        sprache_code=sprache_code)


def _entfernen(u):
    from app import beispieldaten

    return beispieldaten.entfernen(projekt_root=u.projekt, daten_dir=u.daten, engine=u.engine, jetzt=u.jetzt)


@pytest.fixture()
def en(umgebung):
    assert _einspielen(umgebung, "en") is True
    return umgebung


def _alle(u, modell):
    from sqlmodel import Session, select

    with Session(u.engine, expire_on_commit=False) as session:
        return session.exec(select(modell)).all()


def _anzahl(u, tabelle):
    with u.engine.connect() as verbindung:
        return verbindung.exec_driver_sql(f"SELECT COUNT(*) FROM {tabelle}").scalar()


def _markierung(u):
    return json.loads((u.daten / "beispieldaten.json").read_text(encoding="utf-8"))


def _papierkorb(u):
    ordner = u.projekt / "data" / "papierkorb"
    return sorted(p.name.split("_", 1)[1] for p in ordner.iterdir()) if ordner.is_dir() else []


def _textspalten_pruefsumme(engine) -> str:
    """SHA-256 über alle Textspalten aller Tabellen (Zeitstempel sind keine Textspalten). Dieselbe Funktion
    lief gegen den Stand vor der Mehrsprachigkeit und lieferte `GOLDEN_TEXTSPALTEN`."""
    from sqlalchemy import String
    from sqlmodel import SQLModel

    tabellen = ("company", "job", "application", "email", "interview", "contact", "networkcontact",
                "profileskill", "careerentry", "joblog", "profile")
    inhalt = {}
    with engine.connect() as verbindung:
        for name in tabellen:
            tabelle = SQLModel.metadata.tables[name]
            spalten = [s for s in tabelle.c if isinstance(s.type, String)]
            zeilen = verbindung.execute(
                tabelle.select().order_by(tabelle.c.id)).mappings().all()
            inhalt[name] = [[str(z[s.name]) for s in spalten] for z in zeilen]
    return hashlib.sha256(json.dumps(inhalt, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _flach(wert):
    """Alle Texte einer verschachtelten Struktur."""
    if isinstance(wert, str):
        yield wert
    elif isinstance(wert, dict):
        for v in wert.values():
            yield from _flach(v)
    elif isinstance(wert, (list, tuple)):
        for v in wert:
            yield from _flach(v)


def _form(wert):
    """Aufbau ohne Inhalt: gleiche Schlüssel und gleiche Längen heißt gleiche Form."""
    if isinstance(wert, dict):
        return {k: _form(v) for k, v in wert.items()}
    if isinstance(wert, (list, tuple)):
        return [_form(v) for v in wert]
    return None


# ── 1. Englische Anlage ──────────────────────────────────────────────────────────────────────
def test_englische_anlage_zaehlt_wie_die_deutsche(en):
    erwartet = {"company": 6, "job": 5, "application": 3, "email": 5, "interview": 1, "contact": 1,
                "networkcontact": 1, "profileskill": 14, "careerentry": 5}
    for tabelle, anzahl in erwartet.items():
        assert _anzahl(en, tabelle) == anzahl, tabelle
    assert _markierung(en)["status"] == "vorhanden"


def test_sprache_kommt_aus_der_oberflaeche_wenn_nichts_uebergeben_wird(umgebung, monkeypatch):
    from app import sprache

    monkeypatch.setattr(sprache, "aktuell", lambda: "en")
    assert _einspielen(umgebung) is True
    assert (umgebung.projekt / "data" / "cv_basis" / "base_en.docx").is_file()
    assert not (umgebung.projekt / "data" / "cv_basis" / "base_de.docx").exists()
    from app.models import Job
    assert "Express Courier Driver" in {j.title for j in _alle(umgebung, Job)}


def test_unbekannte_sprache_faellt_auf_deutsch_zurueck(umgebung):
    assert _einspielen(umgebung, "fr") is True
    assert (umgebung.projekt / "data" / "cv_basis" / "base_de.docx").is_file()
    from app.models import Job
    assert "Kurierfahrer/in Express (m/w/d)" in {j.title for j in _alle(umgebung, Job)}


# ── 2. Inhalte englisch ──────────────────────────────────────────────────────────────────────
def test_stellen_sind_englisch_und_ohne_gender_zusatz(en):
    from app.models import Job

    titel = {j.title for j in _alle(en, Job)}
    assert titel == {"Letter and Parcel Delivery Driver", "Cargo Bike Courier", "Local Delivery Driver (7.5 t)",
                     "Express Courier Driver", "Dispatcher, Route Planning"}
    assert not any("(m/w/d)" in t or "/in" in t for t in titel)
    for job in _alle(en, Job):
        assert job.match_rationale and re.search(r"[a-z]", job.match_rationale)
        assert "Sie " not in (job.next_step or "") and "ä" not in job.match_rationale


def test_profil_firmen_skills_werdegang_netzwerk_mails_sind_englisch(en):
    from sqlmodel import Session

    from app.models import (CareerEntry, Company, Contact, Email, Interview, NetworkContact, Profile,
                            ProfileSkill)

    with Session(en.engine) as s:
        profil = s.get(Profile, 1)
    assert profil.headline == "Postman with 5 years of experience in parcel delivery"
    assert profil.positionierung.startswith("Reliable postman")
    assert profil.standort == "Musterstadt"

    assert {f.industry for f in _alle(en, Company)} == {
        "Parcel delivery", "Logistics", "Courier service", "Letter and parcel delivery",
        "Cargo bike courier", "Freight forwarding"}
    skills = {(s.bereich, s.name, s.note) for s in _alle(en, ProfileSkill)}
    assert ("Delivery", "Parcel delivery", None) in skills
    assert ("Languages", "German", "Native language") in skills
    werdegang = {(e.rolle, e.von, e.bis) for e in _alle(en, CareerEntry)}
    assert ("Parcel Courier", "04/2021", "present") in werdegang
    assert ("Warehouse Assistant", "08/2019", "03/2021") in werdegang

    kontakt = _alle(en, NetworkContact)[0]
    assert (kontakt.beziehung, kontakt.rolle) == ("Former colleague", "Delivery driver")
    assert kontakt.next_action == "Ask whether he knows anyone at Stadtpost."
    assert _alle(en, Contact)[0].role == "Recruiter"
    gespraech = _alle(en, Interview)[0]
    assert gespraech.interviewer == "Karla Kurier, recruiter"
    assert gespraech.notes == "Phone call, about 30 minutes."

    einladung = next(m for m in _alle(en, Email) if m.category == "Einladung")
    assert einladung.subject == "Invitation to a phone call"
    termin = en.jetzt.date().toordinal() + 3
    assert f"{datetime.fromordinal(termin):%d/%m/%Y} at 10:00" in einladung.snippet


def test_verlauf_nennt_den_termin_im_englischen_datumsformat(en):
    from app.models import JobLog

    eintrag = next(l.eintrag for l in _alle(en, JobLog) if l.art == "manuell")
    assert eintrag == f"Phone call arranged for {datetime.fromordinal(en.jetzt.date().toordinal() + 3):%d/%m/%Y} at 10:00."


def test_erfundene_angaben_bleiben_erfunden(en):
    """Mailadressen nur unter beispiel.de, nur die Beispielnummer, keine Paket- oder Phasennummern."""
    from app import beispieldaten
    from app.models import Contact, Email

    texte = list(_flach(beispieldaten._TEXT_EN)) + [(en.projekt / "config" / "profil.md").read_text(encoding="utf-8")]
    for text in texte:
        for adresse in re.findall(r"[\w.+-]+@[\w.-]+", text):
            assert adresse.endswith("beispiel.de"), adresse
        assert not re.search(r"\bP2-\d+|\bPhase \d+|Paket [A-Z]\b", text), text
    profil = texte[-1]
    assert re.findall(r"\+\d[\d ]{6,}", profil) == ["+49 170 1234567"]
    for mail in _alle(en, Email):
        assert mail.from_addr.rstrip(">").endswith("beispiel.de")
    assert all(k.email.endswith("beispiel.de") for k in _alle(en, Contact))


def test_beide_sprachen_haben_denselben_aufbau():
    """Eine neue Zeile in einer Sprache ohne die andere fiele sonst erst bei der Anlage auf."""
    from app import beispieldaten

    assert _form(beispieldaten._TEXT_EN) == _form(beispieldaten._TEXT_DE)
    assert set(beispieldaten._TEXTE) == {"de", "en"}
    for code in ("de", "en"):
        schluessel = {s["schluessel"] for s in beispieldaten._STELLEN}
        assert set(beispieldaten._TEXTE[code]["stellen"]) == schluessel
        assert set(beispieldaten._TEXTE[code]["branchen"]) == {f[0] for f in beispieldaten._FIRMEN}
    de_platzhalter = [re.findall(r"\{\w+\}", m[1]) for m in beispieldaten._TEXT_DE["mails"]]
    en_platzhalter = [re.findall(r"\{\w+\}", m[1]) for m in beispieldaten._TEXT_EN["mails"]]
    assert de_platzhalter == en_platzhalter


def test_englische_texte_haben_keine_umlaute_ausser_in_erfundenen_namen(en):
    from app import beispieldaten

    erfunden = ("Grünwald",)
    for text in _flach(beispieldaten._TEXT_EN):
        for name in erfunden:
            text = text.replace(name, "")
        assert not re.search(r"[äöüÄÖÜß]", text), text


# ── 3. Maschinenwerte bleiben deutsch ────────────────────────────────────────────────────────
def test_maschinenwerte_bleiben_deutsch(en):
    from app.models import Application, CareerEntry, Email, Interview, Job, JobLog, NetworkContact

    assert {j.status for j in _alle(en, Job)} == {"Neu", "Prüfen", "Beworben", "Interview", "Absage"}
    assert {j.tab for j in _alle(en, Job)} == {"Deutschlandweit"}
    assert {j.portal for j in _alle(en, Job)} == {"Beispieldaten"}      # Marke, die absagen_bericht liest
    assert {j.work_model for j in _alle(en, Job)} == {"Onsite"}
    assert {a.channel for a in _alle(en, Application)} == {"E-Mail"}
    assert {a.status for a in _alle(en, Application)} == {"Beworben", "Interview", "Absage"}
    assert {m.category for m in _alle(en, Email)} == {"Eingangsbestätigung", "Einladung", "Absage", "Sonstige"}
    assert {e.art for e in _alle(en, CareerEntry)} == {"Beruf", "Ausbildung", "Zertifizierung"}
    gespraech = _alle(en, Interview)[0]
    assert (gespraech.art, gespraech.status, gespraech.gegenueber) == ("HR-Screen", "Geplant", "Recruiter")
    kontakt = _alle(en, NetworkContact)[0]
    assert (kontakt.kanal, kontakt.prioritaet) == ("Persönlich", "Mittel")
    assert "Status: Neu → Prüfen" in {l.eintrag for l in _alle(en, JobLog)}


# ── 4. Basis-CV ──────────────────────────────────────────────────────────────────────────────
def test_basis_cv_englisch_liest_sich_mit_python_docx(en):
    from docx import Document

    from pipeline import cv_export

    pfad = en.projekt / "data" / "cv_basis" / "base_en.docx"
    assert pfad.is_file() and not (pfad.parent / "base_de.docx").exists()
    doc = Document(str(pfad))
    rubriken = [p.text for p in doc.paragraphs if p.style.name == "Heading 1"]
    assert rubriken == ["SUMMARY", "PROFESSIONAL EXPERIENCE", "EDUCATION", "SKILLS", "LANGUAGES"]
    stationen = [p.text for p in doc.paragraphs if "\t" in p.text]
    assert stationen == ["Blitzpaket Zustelldienst GmbH\t04/2021 to present",
                         "Lagerhaus Grünwald KG\t08/2019 to 03/2021",
                         "Courier, Express and Postal Services Specialist, Musterstadt Vocational School"
                         "\t2017 to 2019"]
    # Dieselben Erkennungsmerkmale wie beim deutschen CV: Tab-Anker mit Titelzeile davor.
    assert len(cv_export._stationsgrenzen(doc.paragraphs)) == 3
    assert sum(1 for p in doc.paragraphs if p.style.name == "List Paragraph") == 7
    assert doc.core_properties.title == "CV Benno Bewerbaer" and doc.core_properties.comments == "Sample data"
    assert "Parcel Courier" in {p.text for p in doc.paragraphs}


def test_basis_cv_deutsch_hat_weiter_die_deutschen_rubriken(umgebung):
    from docx import Document

    assert _einspielen(umgebung, "de") is True
    doc = Document(str(umgebung.projekt / "data" / "cv_basis" / "base_de.docx"))
    assert [p.text for p in doc.paragraphs if p.style.name == "Heading 1"] == [
        "KURZPROFIL", "BERUFSERFAHRUNG", "AUSBILDUNG", "KENNTNISSE", "SPRACHEN"]


# ── 5. Profil-Datei ──────────────────────────────────────────────────────────────────────────
def test_profil_datei_ueberschriften_deutsch_inhalt_englisch(umgebung, tmp_path):
    from app import beispieldaten
    from pipeline import user_profile

    de = beispieldaten._profil_md_text("de")
    text = beispieldaten._profil_md_text("en")
    kopf = lambda t: [z for z in t.splitlines() if z.startswith(("#", "- **Name:", "- **Positionierung:",
                                                                 "- **Standort:", "- **Kontakt:", "- **Aktuell:",
                                                                 "- **Zieltermin:"))]
    gerippe = lambda t: [re.match(r"(#+ [^:]*|- \*\*[^*]+\*\*)", z).group(1) for z in kopf(t)]
    assert gerippe(text) == gerippe(de)
    assert "## Identität" in text and "## Sprachen / CV-Fassungen" in text
    assert "Postman with 5 years" in text and "Postbote" not in text

    # Das Programm liest die englische Datei wie die deutsche.
    datei = tmp_path / "profil.md"
    datei.write_text(text, encoding="utf-8")
    assert user_profile._NAME_RE.search(text).group(1).strip() == "Benno Bewerbaer"
    assert "Musterstadt" in user_profile._STANDORT_RE.search(text).group(1)
    assert user_profile._KONTAKT_RE.search(text).group(1).startswith("benno.bewerbaer@beispiel.de")

    abschnitt = text.split("## Sprachen / CV-Fassungen")[1].split("##")[0]
    assert "data/cv_basis/base_en.docx" in abschnitt and "base_de.docx" not in abschnitt


def test_profil_datei_wird_in_der_aktuellen_sprache_angelegt(en):
    text = (en.projekt / "config" / "profil.md").read_text(encoding="utf-8")
    assert "- **Zieltermin:** new job by the end of the year" in text
    assert _markierung(en)["dateien"].keys() == {"config/profil.md", "data/cv_basis/base_en.docx"}


# ── 6. Entfernen ─────────────────────────────────────────────────────────────────────────────
def test_entfernen_raeumt_die_englische_fassung_auf(en):
    ergebnis = _entfernen(en)
    assert ergebnis["ok"] is True and ergebnis["behalten"] == []
    assert ergebnis["entfernt"]["dateien"] == 2
    for tabelle in ("company", "job", "application", "email", "interview", "contact", "networkcontact",
                    "profileskill", "careerentry", "joblog"):
        assert _anzahl(en, tabelle) == 0, tabelle
    assert not (en.projekt / "config" / "profil.md").exists()
    assert not (en.projekt / "data" / "cv_basis" / "base_en.docx").exists()
    assert _papierkorb(en) == ["base_en.docx", "profil.md"]
    assert _markierung(en)["status"] == "entfernt"


def test_entfernen_laesst_eigene_dateien_stehen(en):
    """Ein eigener deutscher CV daneben und ein vom Kunden geänderter englischer bleiben liegen."""
    eigener_cv_de = en.projekt / "data" / "cv_basis" / "base_de.docx"
    eigener_cv_de.write_bytes(b"mein eigener deutscher CV")
    (en.projekt / "data" / "cv_basis" / "base_en.docx").write_bytes(b"mein geaenderter CV")

    ergebnis = _entfernen(en)
    assert ergebnis["behalten"] == ["data/cv_basis/base_en.docx"]
    assert eigener_cv_de.read_bytes() == b"mein eigener deutscher CV"
    assert (en.projekt / "data" / "cv_basis" / "base_en.docx").read_bytes() == b"mein geaenderter CV"
    assert _papierkorb(en) == ["profil.md"]


def test_erlaubte_dateien_nennen_beide_fassungen():
    from app import beispieldaten

    assert set(beispieldaten._ERLAUBTE_DATEIEN) == {
        "config/profil.md", "data/cv_basis/base_de.docx", "data/cv_basis/base_en.docx"}


def test_verbogener_markierungseintrag_verschiebt_nichts_fremdes(en):
    markierung = _markierung(en)
    markierung["dateien"]["config/anderes.md"] = "0" * 64
    (en.projekt / "config" / "anderes.md").write_text("eigen", encoding="utf-8")
    (en.daten / "beispieldaten.json").write_text(json.dumps(markierung), encoding="utf-8")

    _entfernen(en)
    assert (en.projekt / "config" / "anderes.md").read_text(encoding="utf-8") == "eigen"


# ── 7. Startsprache ──────────────────────────────────────────────────────────────────────────
def _einstellung_holen(session):
    """Ersatz für `main._einstellungen_singleton`: legt die Zeile an, wie das Programm es täte."""
    from app.models import SuchEinstellung

    zeile = SuchEinstellung(id=1)
    session.add(zeile)
    session.commit()
    session.refresh(zeile)
    return zeile


def _sprache_lesen(u) -> str:
    from sqlmodel import Session

    from app.models import SuchEinstellung

    with Session(u.engine) as s:
        zeile = s.get(SuchEinstellung, 1)
        return zeile.sprache if zeile else "<keine Zeile>"


def _startsprache(u, **kwargs):
    from app import beispieldaten

    return beispieldaten.startsprache_uebernehmen(
        u.daten, engine=u.engine, einstellung_holen=kwargs.pop("einstellung_holen", _einstellung_holen),
        **kwargs)


@pytest.mark.parametrize("inhalt, erwartet", [("en", "en"), ("de\n", "de"), ("  EN  \r\n", "en")])
def test_startsprache_wird_gesetzt_und_die_datei_geloescht(umgebung, inhalt, erwartet):
    datei = umgebung.daten / "startsprache"
    datei.write_text(inhalt, encoding="utf-8")

    assert _startsprache(umgebung) is True
    assert _sprache_lesen(umgebung) == erwartet
    assert not datei.exists()


def test_startsprache_nutzt_eine_vorhandene_zeile_und_legt_keine_zweite_an(umgebung):
    from sqlmodel import Session

    from app.models import SuchEinstellung

    with Session(umgebung.engine) as s:
        s.add(SuchEinstellung(id=1, min_mitarbeiter=123))
        s.commit()
    (umgebung.daten / "startsprache").write_text("en", encoding="utf-8")

    def nie(session):
        raise AssertionError("die Zeile gibt es schon")

    assert _startsprache(umgebung, einstellung_holen=nie) is True
    assert _anzahl(umgebung, "sucheinstellung") == 1
    with Session(umgebung.engine) as s:
        zeile = s.get(SuchEinstellung, 1)
        assert (zeile.sprache, zeile.min_mitarbeiter) == ("en", 123)


@pytest.mark.parametrize("gewaehlt", ["de", "en"])
def test_startsprache_ueberschreibt_keine_gewaehlte_sprache(umgebung, gewaehlt):
    from sqlmodel import Session

    from app.models import SuchEinstellung

    with Session(umgebung.engine) as s:
        s.add(SuchEinstellung(id=1, sprache=gewaehlt))
        s.commit()
    datei = umgebung.daten / "startsprache"
    datei.write_text("en" if gewaehlt == "de" else "de", encoding="utf-8")

    assert _startsprache(umgebung) is False
    assert _sprache_lesen(umgebung) == gewaehlt
    assert datei.exists()


@pytest.mark.parametrize("inhalt", ["fr", "", "english"])
def test_startsprache_mit_unbrauchbarem_inhalt_aendert_nichts(umgebung, inhalt):
    datei = umgebung.daten / "startsprache"
    datei.write_text(inhalt, encoding="utf-8")

    assert _startsprache(umgebung) is False
    assert _sprache_lesen(umgebung) == "<keine Zeile>"
    assert datei.exists()


def test_startsprache_ohne_datei_tut_nichts(umgebung):
    assert _startsprache(umgebung) is False
    assert _sprache_lesen(umgebung) == "<keine Zeile>"


def test_startsprache_wirft_nie(umgebung):
    (umgebung.daten / "startsprache").write_text("en", encoding="utf-8")

    def kaputt(session):
        raise RuntimeError("Einstellung nicht lesbar (Test)")

    assert _startsprache(umgebung, einstellung_holen=kaputt) is False
    assert (umgebung.daten / "startsprache").exists()          # nicht verbraucht: nächster Start versucht es erneut
    assert _startsprache(umgebung, einstellung_holen=_einstellung_holen) is True


def test_startsprache_mit_unbekanntem_datenordner_wirft_nicht(tmp_path, umgebung):
    from app import beispieldaten

    assert beispieldaten.startsprache_uebernehmen(tmp_path / "gibt-es-nicht", engine=umgebung.engine) is False


def test_startsprache_dann_beispieldaten_ergibt_die_englische_fassung(umgebung, monkeypatch):
    """Der Weg beim ersten Start: Datei, dann Einstellung, dann Beispieldaten ohne ausdrückliche Sprache."""
    from app import sprache

    (umgebung.daten / "startsprache").write_text("en", encoding="utf-8")
    monkeypatch.setattr(sprache, "aktuell", lambda: _sprache_lesen(umgebung) or "de")

    assert _startsprache(umgebung) is True
    assert _einspielen(umgebung) is True
    assert (umgebung.projekt / "data" / "cv_basis" / "base_en.docx").is_file()
    from app.models import Job
    assert "Cargo Bike Courier" in {j.title for j in _alle(umgebung, Job)}


def test_ohne_startsprache_bleibt_es_deutsch(umgebung, monkeypatch):
    from app import sprache

    monkeypatch.setattr(sprache, "aktuell", lambda: _sprache_lesen(umgebung) or "de")
    assert _startsprache(umgebung) is False
    assert _einspielen(umgebung) is True
    assert (umgebung.projekt / "data" / "cv_basis" / "base_de.docx").is_file()
    from app.models import Job
    assert "Lastenradkurier/in (m/w/d)" in {j.title for j in _alle(umgebung, Job)}


# ── 8. Deutsch unverändert ───────────────────────────────────────────────────────────────────
def test_deutsche_fassung_ist_unveraendert(umgebung):
    assert _einspielen(umgebung, "de") is True

    assert _textspalten_pruefsumme(umgebung.engine) == GOLDEN_TEXTSPALTEN
    profil = (umgebung.projekt / "config" / "profil.md").read_bytes()
    assert hashlib.sha256(profil).hexdigest() == GOLDEN_PROFIL_MD
    with zipfile.ZipFile(umgebung.projekt / "data" / "cv_basis" / "base_de.docx") as z:
        assert hashlib.sha256(z.read("word/document.xml")).hexdigest() == GOLDEN_CV_DOKUMENT
    assert _markierung(umgebung)["dateien"].keys() == {"config/profil.md", "data/cv_basis/base_de.docx"}
    assert sorted(p.name for p in umgebung.daten.iterdir()) == ["beispieldaten.json", "bewerbung.sqlite"]


def test_ohne_angabe_und_ohne_gewaehlte_sprache_ist_es_deutsch(umgebung, monkeypatch):
    """Der Standard, wenn die Einstellung leer ist: dasselbe Ergebnis wie ausdrücklich `de`."""
    from app import sprache

    monkeypatch.setattr(sprache, "aktuell", lambda: _sprache_lesen(umgebung) or "de")
    assert _einspielen(umgebung) is True
    assert _textspalten_pruefsumme(umgebung.engine) == GOLDEN_TEXTSPALTEN
