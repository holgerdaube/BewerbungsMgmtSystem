"""Tests für P2-59, Paket B: Beispieldaten („Benno Bewerbaer“) einer frischen Paket-Installation.

Alles läuft unter `tmp_path`: eigener Projekt-Root (`config/`, `data/`), eigener Datenordner und eine
eigene SQLite-Datei je Test (Fixture `umgebung`). Die Funktionen bekommen Projekt-Root, Datenordner
und Engine ausdrücklich übergeben, nichts davon zeigt auf die echte Installation. Die Router-Tests
biegen `app.db.*` und `main._PROFIL_STRUKTUR_PATH` per `monkeypatch` um, denn der Router ruft die
Funktionen ohne Parameter auf und schreibt danach `config/profil_struktur.md`. Der Erst-Start-Pfad
läuft im Subprozess (Muster `test_neuinstallation.py`), weil `app.db` den Datenordner beim Import
bindet.

Zeitzonen: Die Tests laufen mit fester „jetzt“-Zeit und vergleichen nur lokale Werte oder Werte, die sie
mit denselben Funktionen nachrechnen wie der Mail-Ingest, also unabhängig von der Zeitzone des Rechners.

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention). Windows-CI: pathlib, Verbindungen
werden vor dem Aufräumen geschlossen (`engine.dispose()`), keine Rechte-Prüfungen.
"""
import ast
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJEKT_DIR = BACKEND_DIR.parent
JETZT = datetime(2026, 10, 1, 9, 30)

SICHERUNG_LAEUFT_TEXT = "Es läuft gerade eine Sicherung. Bitte versuchen Sie es gleich noch einmal."
KEINE_BEISPIELDATEN_TEXT = "Es sind keine Beispieldaten vorhanden, die entfernt werden könnten."


# ── Fixtures und Helfer ──────────────────────────────────────────────────────────────────────
@pytest.fixture()
def umgebung(tmp_path, monkeypatch):
    """Eigene Paket-Installation: Projekt-Root mit Manifest (Installationsart `paket`), Datenordner,
    leere Datenbank mit allen Tabellen und denselben UNIQUE-Indizes wie `init_db()`."""
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


def _einspielen(u, db_war_da=False):
    from app import beispieldaten

    return beispieldaten.einspielen_falls_neu(
        db_war_da, projekt_root=u.projekt, daten_dir=u.daten, jetzt=u.jetzt, engine=u.engine)


def _entfernen(u, **kwargs):
    from app import beispieldaten

    return beispieldaten.entfernen(
        projekt_root=u.projekt, daten_dir=u.daten, engine=u.engine, jetzt=u.jetzt, **kwargs)


@pytest.fixture()
def angelegt(umgebung):
    assert _einspielen(umgebung) is True
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
    return sorted(p.name for p in ordner.iterdir()) if ordner.is_dir() else []


TABELLEN = ("company", "job", "application", "email", "interview", "contact", "networkcontact",
            "profileskill", "careerentry", "joblog")


def _nichts_angelegt(u, markierung_erwartet=False):
    for tabelle in TABELLEN:
        assert _anzahl(u, tabelle) == 0, tabelle
    assert (u.daten / "beispieldaten.json").exists() is markierung_erwartet
    assert not (u.projekt / "config" / "profil.md").exists()
    assert not (u.projekt / "data" / "cv_basis" / "base_de.docx").exists()


def _eigene_daten(u):
    """Daten des Kunden NEBEN den Beispieldaten: eigene Firma, Stelle, Bewerbung und Mails, dazu eine
    eigene Mail, die an einer Beispielstelle hängt, ein eigener Skill, Werdegang und Netzwerk-Kontakt."""
    from sqlmodel import Session, select
    from app.models import (Application, CareerEntry, Company, Email, Job, NetworkContact,
                            ProfileSkill)

    with Session(u.engine) as session:
        beispielstelle = session.exec(select(Job).where(Job.title.like("Kurierfahrer%"))).one()
        beispielbewerbung = session.exec(
            select(Application).where(Application.job_id == beispielstelle.id)).one()
        firma = Company(name="Eigene Firma GmbH")
        session.add(firma)
        session.flush()
        job = Job(company_id=firma.id, company_name=firma.name, title="Eigene Stelle",
                  dedup_key="manuell|eigene firma gmbh|eigene stelle", status="Beworben")
        session.add(job)
        session.flush()
        bewerbung = Application(job_id=job.id, status="Beworben", applied_date="2026-09-01")
        session.add(bewerbung)
        session.flush()
        eigene_mail = Email(subject="Eigene Mail", job_id=job.id, application_id=bewerbung.id,
                            company_id=firma.id)
        lose_mail = Email(subject="Lose eigene Mail")
        angehaengt = Email(subject="Eigene Mail an der Beispielstelle", job_id=beispielstelle.id,
                           application_id=beispielbewerbung.id, company_id=beispielstelle.company_id)
        skill = ProfileSkill(bereich="Eigen", name="Eigener Skill", quelle="manuell")
        werdegang = CareerEntry(art="Beruf", firma="Eigene Firma GmbH", rolle="Eigene Rolle")
        netzwerk = NetworkContact(name="Eigene Person", dedup_key="manuell|eigene person")
        session.add_all([eigene_mail, lose_mail, angehaengt, skill, werdegang, netzwerk])
        session.commit()
        return SimpleNamespace(
            firma_id=firma.id, job_id=job.id, bewerbung_id=bewerbung.id, mail_id=eigene_mail.id,
            lose_mail_id=lose_mail.id, angehaengte_mail_id=angehaengt.id, skill_id=skill.id,
            werdegang_id=werdegang.id, netzwerk_id=netzwerk.id, beispielstelle_id=beispielstelle.id)


def _sicherungen(u):
    ordner = u.daten / "backups" / "auto"
    return sorted(p.name for p in ordner.glob("*.zip")) if ordner.is_dir() else []


# ── 1. Wann angelegt wird ────────────────────────────────────────────────────────────────────
def test_datenbank_war_schon_da_legt_nichts_an(umgebung):
    """Gegenprobe zur wichtigsten Bedingung: Eine bestehende Installation (Datenbank vorhanden) bekommt
    nie Beispieldaten, auch wenn Tabellen leer sind."""
    assert _einspielen(umgebung, db_war_da=True) is False
    _nichts_angelegt(umgebung)


def test_vorhandene_markierung_verhindert_die_neuanlage(umgebung):
    """Auch „entfernt“ zählt: Entfernte Beispieldaten kommen nie wieder."""
    (umgebung.daten / "beispieldaten.json").write_text('{"status": "entfernt"}', encoding="utf-8")
    assert _einspielen(umgebung) is False
    _nichts_angelegt(umgebung, markierung_erwartet=True)


def test_git_installation_ohne_variable_legt_nichts_an(umgebung):
    (umgebung.projekt / "bms_manifest.json").unlink()
    (umgebung.projekt / ".git").mkdir()
    assert _einspielen(umgebung) is False
    _nichts_angelegt(umgebung)


def test_git_installation_mit_variable_legt_an(umgebung, monkeypatch):
    (umgebung.projekt / "bms_manifest.json").unlink()
    (umgebung.projekt / ".git").mkdir()
    monkeypatch.setenv("BMS_BEISPIELDATEN", "1")
    assert _einspielen(umgebung) is True
    assert _anzahl(umgebung, "job") == 5


def test_unbekannte_installation_ohne_variable_legt_nichts_an(umgebung):
    (umgebung.projekt / "bms_manifest.json").unlink()
    assert _einspielen(umgebung) is False
    _nichts_angelegt(umgebung)


@pytest.mark.parametrize("wert", ["0", "true", "ja", ""])
def test_nur_der_wert_1_schaltet_die_variable_ein(umgebung, monkeypatch, wert):
    (umgebung.projekt / "bms_manifest.json").unlink()
    monkeypatch.setenv("BMS_BEISPIELDATEN", wert)
    assert _einspielen(umgebung) is False


def test_paket_legt_an_und_schreibt_die_markierung(umgebung):
    from app import beispieldaten

    assert _einspielen(umgebung) is True
    markierung = _markierung(umgebung)
    assert markierung["status"] == "vorhanden"
    assert markierung["name"] == "Benno Bewerbaer"
    assert markierung["angelegt_am"] == "2026-10-01T09:30:00"
    assert set(markierung["dateien"]) == {"config/profil.md", "data/cv_basis/base_de.docx"}
    assert all(len(h) == 64 for h in markierung["dateien"].values())
    assert beispieldaten.status(umgebung.daten)["status"] == "vorhanden"


@pytest.mark.parametrize("tabelle", ["company", "job", "email", "application"])
def test_nicht_leere_tabellen_verhindern_die_neuanlage(umgebung, tabelle):
    """Gürtel zu den Hosenträgern: Steht schon etwas in einer der vier Tabellen, wird nichts angelegt."""
    from sqlmodel import Session
    from app.models import Application, Company, Email, Job

    zeile = {"company": lambda: Company(name="Vorhandene Firma"),
             "job": lambda: Job(title="Vorhandene Stelle", dedup_key="manuell|x|y"),
             "email": lambda: Email(subject="Vorhandene Mail"),
             "application": lambda: Application(job_id=1)}[tabelle]()
    with Session(umgebung.engine) as session:
        session.add(zeile)
        session.commit()
    assert _einspielen(umgebung) is False
    assert not (umgebung.daten / "beispieldaten.json").exists()
    assert _anzahl(umgebung, "profileskill") == 0


def test_ohne_tabellen_wirft_nichts(tmp_path, umgebung):
    """Wirft nie: Eine Datenbank ohne Tabellen (init_db lief nicht) ergibt `False` und keine Spur."""
    from sqlmodel import create_engine
    from app import beispieldaten, db

    leer = create_engine(f"sqlite:///{tmp_path / 'leer.sqlite'}", connect_args=db.CONNECT_ARGS)
    try:
        assert beispieldaten.einspielen_falls_neu(
            False, projekt_root=umgebung.projekt, daten_dir=umgebung.daten, jetzt=JETZT, engine=leer) is False
    finally:
        leer.dispose()
    assert not (umgebung.daten / "beispieldaten.json").exists()
    assert not (umgebung.projekt / "config" / "profil.md").exists()


def test_fehler_mitten_im_anlegen_hinterlaesst_nichts_halbes(umgebung):
    """EINE Transaktion: Scheitert der LETZTE Eintrag (ein Netzwerk-Kontakt mit demselben Schlüssel
    existiert schon, die Tabelle gehört nicht zur Leer-Prüfung), sind Firmen, Stellen und Mails vorher
    schon in der Session. Danach darf davon nichts in der Datenbank stehen, und es gibt weder
    Markierung noch Dateien."""
    from sqlmodel import Session
    from app import normalize as N
    from app.models import NetworkContact

    with Session(umgebung.engine) as session:
        session.add(NetworkContact(name="Vorhanden",
                                   dedup_key=N.slug_parts("Paul Paket", "Blitzpaket Zustelldienst GmbH")))
        session.commit()

    assert _einspielen(umgebung) is False
    for tabelle in ("company", "job", "application", "email", "interview", "contact", "profileskill",
                    "careerentry", "joblog", "profile"):
        assert _anzahl(umgebung, tabelle) == 0, tabelle
    assert _anzahl(umgebung, "networkcontact") == 1
    assert not (umgebung.daten / "beispieldaten.json").exists()
    assert not (umgebung.projekt / "config" / "profil.md").exists()
    assert not (umgebung.projekt / "data" / "cv_basis" / "base_de.docx").exists()


def test_scheitert_eine_datei_wird_die_markierung_trotzdem_geschrieben(umgebung, monkeypatch):
    """Die Zeilen stehen dann schon in der Datenbank. Ohne Markierung ließen sie sich nie mehr entfernen."""
    from app import beispieldaten

    def kaputt(jetzt):
        raise RuntimeError("Lebenslauf kaputt (Test)")

    monkeypatch.setattr(beispieldaten, "_basis_cv_bytes", kaputt)

    assert _einspielen(umgebung) is True
    assert _markierung(umgebung)["dateien"].keys() == {"config/profil.md"}
    assert not (umgebung.projekt / "data" / "cv_basis" / "base_de.docx").exists()
    assert beispieldaten.status(umgebung.daten)["anzahl"]["dateien"] == 1


# ── 2. Was angelegt wird ─────────────────────────────────────────────────────────────────────
def test_anzahlen_je_art_stimmen_mit_der_markierung_ueberein(angelegt):
    erwartet = {"company": 6, "job": 5, "application": 3, "email": 5, "interview": 1, "contact": 1,
                "networkcontact": 1, "profileskill": 14, "careerentry": 5}
    ids = _markierung(angelegt)["ids"]
    for tabelle, anzahl in erwartet.items():
        assert _anzahl(angelegt, tabelle) == anzahl, tabelle
        assert len(ids[tabelle]) == anzahl, tabelle
    assert _anzahl(angelegt, "joblog") == len(ids["joblog"]) > 0


def test_status_vielfalt_und_werte_gehoeren_zu_den_wertemengen_der_app(angelegt):
    """Die Beispieldaten benutzen nur Werte, die die App selbst kennt (sonst bricht die Oberfläche an
    ihrer eigenen Auswahl)."""
    from app.main import ALLOWED_GEGENUEBER, ALLOWED_INTERVIEW_STATUSES, ALLOWED_JOB_STATUSES
    from app.models import Application, Interview, Job

    stellen = _alle(angelegt, Job)
    assert {j.status for j in stellen} == {"Neu", "Prüfen", "Beworben", "Interview", "Absage"}
    assert {j.status for j in stellen} <= ALLOWED_JOB_STATUSES
    assert {a.status for a in _alle(angelegt, Application)} == {"Beworben", "Interview", "Absage"}
    for gespraech in _alle(angelegt, Interview):
        assert gespraech.status in ALLOWED_INTERVIEW_STATUSES
        assert gespraech.gegenueber in ALLOWED_GEGENUEBER


def test_stellen_tragen_die_markierung_und_plausible_werte(angelegt):
    from app.models import Company, Job

    for stelle in _alle(angelegt, Job):
        assert stelle.dedup_key.startswith("beispiel|")
        assert stelle.source_note == "Beispieldaten"
        assert stelle.tab == "Deutschlandweit"
        assert 3 <= stelle.match_score <= 5
        assert stelle.found_date and stelle.deleted_at is None
    assert {f.notes for f in _alle(angelegt, Company)} == {"Beispieldaten"}
    assert {f.name for f in _alle(angelegt, Company)} == {
        "Blitzpaket Zustelldienst GmbH", "Grünwald Logistik GmbH", "Kurierdienst Krause GmbH",
        "Stadtpost Musterstadt GmbH", "Pedalkurier Musterstadt GbR", "Spedition Sonnenschein AG"}


def test_keine_url_und_keine_webseite_an_firmen_und_stellen(angelegt):
    """Sonst riefe ein Hintergrund-Lauf (Verifikation, Beworben-Check) erfundene Adressen ab."""
    from app.models import Company, Job

    for stelle in _alle(angelegt, Job):
        assert stelle.url is None and stelle.career_url is None
        assert stelle.posting_snapshot_path is None
    for firma in _alle(angelegt, Company):
        assert firma.domain is None and firma.fit_analysis_path is None
    assert _anzahl(angelegt, "targetcompany") == 0 and _anzahl(angelegt, "headhunter") == 0
    assert _anzahl(angelegt, "cvversion") == 0 and _anzahl(angelegt, "sucheinstellung") == 0


def test_genau_eine_mail_ohne_stelle_und_keine_gmail_kennung(angelegt):
    from app.models import Email

    mails = _alle(angelegt, Email)
    assert all(m.gmail_message_id is None and m.gmail_thread_id is None for m in mails)
    ohne_stelle = [m for m in mails if m.job_id is None]
    assert len(ohne_stelle) == 1
    mail = ohne_stelle[0]
    assert mail.subject == "Gartenfreunde Musterstadt: Einladung zum Herbstfest"
    assert mail.category == "Sonstige"
    assert mail.application_id is None and mail.company_id is None and mail.archived_at is None
    assert mail.is_response is False
    for m in mails:
        adresse = m.from_addr.split("<")[-1].rstrip(">")
        assert adresse.endswith(".beispiel.de"), adresse


def test_gespraechstermin_liegt_in_der_zukunft(angelegt):
    from app.models import Interview, Job

    (gespraech,) = _alle(angelegt, Interview)
    assert datetime.fromisoformat(gespraech.scheduled_at) > JETZT
    assert gespraech.scheduled_at.endswith("T10:00")
    assert (gespraech.runde, gespraech.art, gespraech.gegenueber, gespraech.status) == (
        1, "HR-Screen", "Recruiter", "Geplant")
    stelle = next(j for j in _alle(angelegt, Job) if j.id == gespraech.job_id)
    assert stelle.status == "Interview" and stelle.title.startswith("Kurierfahrer")


def test_kontakt_und_netzwerk_kontakt(angelegt):
    from app.models import Contact, NetworkContact

    (kontakt,) = _alle(angelegt, Contact)
    assert (kontakt.name, kontakt.role) == ("Karla Kurier", "Recruiterin")
    assert kontakt.email == "karla.kurier@krause.beispiel.de"
    (netzwerk,) = _alle(angelegt, NetworkContact)
    assert (netzwerk.name, netzwerk.kanal, netzwerk.prioritaet) == ("Paul Paket", "Persönlich", "Mittel")
    assert "Blitzpaket" in netzwerk.unternehmen
    assert date.fromisoformat(netzwerk.next_action_date) == date(2026, 10, 6)


def test_antwortkennzahlen_und_gesamtprozess_zeigen_werte(angelegt):
    """Die Mails sind Antworten mit Antwortzeit (wie der Ingest sie rechnet), damit Dashboard und
    Funnel Werte zeigen. Die Stelle ohne Mail zählt als „Keine Reaktion“."""
    from app.gesamtprozess import absagen_kpi, bewerbungen_kpi, funnel_kpi, keine_reaktion_kpi
    from app.models import Application, Email, Interview, Job
    from app.response_metrics import response_kpis
    from pipeline.gmail_ingest import RESPONSE_CATS, response_time_hours

    mails, bewerbungen = _alle(angelegt, Email), _alle(angelegt, Application)
    stellen, gespraeche = _alle(angelegt, Job), _alle(angelegt, Interview)

    kennzahlen = response_kpis(mails, bewerbungen)
    assert kennzahlen["responses"] == 2
    assert kennzahlen["response_rate"] == 67
    assert kennzahlen["avg_response_hours"] > 0

    applied = {b.id: b.applied_date for b in bewerbungen}
    for mail in mails:
        assert mail.is_response == (mail.category in RESPONSE_CATS)
        if mail.application_id is not None:
            anker = datetime.combine(date.fromisoformat(applied[mail.application_id]), time.min)
            assert mail.response_time_hours == response_time_hours(mail.received_at, anker)
            assert mail.response_time_hours > 0

    keine_reaktion = keine_reaktion_kpi(stellen, mails, bewerbungen, [], heute=JETZT.date())
    assert keine_reaktion["wert"] == 1
    assert keine_reaktion["rows"][0]["label"] == "Grünwald Logistik GmbH"
    assert keine_reaktion["rows"][0]["tage"] == 20
    assert bewerbungen_kpi(bewerbungen, [])["wert"] == 3
    assert absagen_kpi(stellen, [])["wert"] == 1
    trichter = funnel_kpi(stellen, bewerbungen, mails, [], gespraeche, [])
    assert [s["anzahl"] for s in trichter["stufen"]] == [5, 5, 3, 2, 1]


def test_joblog_folgt_dem_format_der_app(angelegt):
    """Der Statuswechsel auf „Beworben“ steht im Verlauf wie beim echten PATCH (`Status: alt → neu`):
    Der Mail-Ingest nutzt genau diese Marke als Bewerbungszeitpunkt."""
    from app.models import Job, JobLog
    from pipeline.gmail_ingest import BEWORBEN_MARKE

    eintraege = _alle(angelegt, JobLog)
    beworben = {j.id for j in _alle(angelegt, Job) if j.status in ("Beworben", "Interview", "Absage")}
    mit_marke = {e.job_id for e in eintraege if BEWORBEN_MARKE in e.eintrag}
    assert mit_marke == beworben
    assert {e.art for e in eintraege} == {"auto", "manuell"}


def test_profil_skills_und_werdegang(angelegt):
    from app.models import CareerEntry, Profile, ProfileSkill

    (profil,) = _alle(angelegt, Profile)
    assert profil.id == 1
    assert profil.headline == "Postbote mit 5 Jahren Erfahrung in der Paketzustellung"
    assert profil.standort == "Musterstadt"
    assert 2 <= profil.positionierung.count(". ") + 1 <= 3

    skills = _alle(angelegt, ProfileSkill)
    assert {s.quelle for s in skills} == {"beispiel"}
    assert {s.bereich for s in skills} == {"Zustellung", "Fahrzeuge", "Lager", "Persönlich", "Sprachen"}
    namen = {s.name: s.note for s in skills}
    assert namen["Deutsch"] == "Muttersprache" and namen["Englisch"] == "Grundkenntnisse"
    assert {"Paketzustellung", "Staplerschein", "Lastenrad", "Wetterfestigkeit"} <= set(namen)

    werdegang = _alle(angelegt, CareerEntry)
    assert {w.quelle for w in werdegang} == {"beispiel"}
    beruf = sorted((w for w in werdegang if w.art == "Beruf"), key=lambda w: w.sort_order)
    assert [(w.firma, w.rolle, w.von, w.bis) for w in beruf] == [
        ("Blitzpaket Zustelldienst GmbH", "Paketzusteller", "04/2021", "heute"),
        ("Lagerhaus Grünwald KG", "Lagerhelfer", "08/2019", "03/2021")]
    assert [w.rolle for w in werdegang if w.art == "Zertifizierung"] == ["Führerschein Klasse B", "Staplerschein"]
    (ausbildung,) = [w for w in werdegang if w.art == "Ausbildung"]
    assert ausbildung.rolle == "Fachkraft für Kurier-, Express- und Postdienstleistungen"
    assert (ausbildung.firma, ausbildung.von, ausbildung.bis) == ("Berufsschule Musterstadt", "2017", "2019")


def test_vorhandene_profilwerte_werden_nicht_ueberschrieben(umgebung):
    from sqlmodel import Session
    from app.models import Profile

    with Session(umgebung.engine) as session:
        session.add(Profile(id=1, headline="Mein eigener Titel"))
        session.commit()
    assert _einspielen(umgebung) is True

    (profil,) = _alle(umgebung, Profile)
    assert profil.headline == "Mein eigener Titel"
    assert profil.standort == "Musterstadt"
    assert set(_markierung(umgebung)["profil_werte"]) == {"standort", "positionierung"}


def test_profil_md_ist_fuer_den_profil_leser_lesbar(angelegt, monkeypatch):
    """Aufbau wie die Vorlage in `BMS_Install_MAC.md` bzw. `BMS_Install_Windows.md` (Abschnitt
    „Einrichten: Das BMS lernt Sie kennen“, dort „Ihr Profil: Identität und Suchstrategie“): Name,
    Standort und Kontakt erkennt `pipeline/user_profile.py` an der Fettschrift der Feldnamen."""
    from pipeline import user_profile

    pfad = angelegt.projekt / "config" / "profil.md"
    monkeypatch.setattr(user_profile, "_PROFIL_MD", pfad)

    assert user_profile.user_name() == "Benno Bewerbaer"
    assert user_profile.anschrift() == "Musterweg 7, 12345 Musterstadt"
    assert user_profile.briefkopf_ort() == "Musterstadt"
    assert user_profile.briefkopf() == (
        "Benno Bewerbaer\nMusterweg 7, 12345 Musterstadt\nbenno.bewerbaer@beispiel.de | +49 170 1234567")
    text = pfad.read_text(encoding="utf-8")
    for abschnitt in ("## Identität", "## Kurzprofil", "## Zielrolle", "## Harte Rahmenbedingungen",
                      "## Sprachen / CV-Fassungen", "## Bekannte Skill-Gaps / Red Flags",
                      "## Empirie aus dem Bewerbungsverlauf"):
        assert abschnitt in text, abschnitt
    assert "30 km" in text and "Vollzeit" in text and "Englisch: Grundkenntnisse" in text
    assert text.endswith("(pflegt das BMS selbst, bitte die Überschrift unverändert lassen)\n")


def test_vorhandene_dateien_werden_nie_ueberschrieben(umgebung):
    profil = umgebung.projekt / "config" / "profil.md"
    cv = umgebung.projekt / "data" / "cv_basis" / "base_de.docx"
    profil.parent.mkdir(parents=True)
    cv.parent.mkdir(parents=True)
    profil.write_text("# Mein eigenes Profil\n", encoding="utf-8")
    cv.write_bytes(b"mein eigener Lebenslauf")

    assert _einspielen(umgebung) is True

    assert profil.read_text(encoding="utf-8") == "# Mein eigenes Profil\n"
    assert cv.read_bytes() == b"mein eigener Lebenslauf"
    assert _markierung(umgebung)["dateien"] == {}
    # Und weil sie nicht angelegt wurden, fasst das Entfernen sie später nicht an.
    _entfernen(umgebung)
    assert profil.exists() and cv.exists() and _papierkorb(umgebung) == []


def test_basis_cv_hat_den_v10_aufbau_den_cv_export_erwartet(angelegt, tmp_path):
    """Station: `Firma<TAB>Zeitraum`, Titel, EINE kursive Beschreibung, Aufzählungen mit Nummerierung.
    Geprüft mit den Erkennungsfunktionen von `cv_export` und mit dem Struktur-Check der App."""
    import app.main as main
    from docx import Document
    from docx.shared import Pt
    from pipeline import cv_export

    pfad = angelegt.projekt / "data" / "cv_basis" / "base_de.docx"
    doc = Document(str(pfad))
    absaetze = doc.paragraphs

    ueberschriften = [p for p in absaetze if cv_export._ist_ueberschrift(p)]
    assert [p.text for p in ueberschriften] == [
        "KURZPROFIL", "BERUFSERFAHRUNG", "AUSBILDUNG", "KENNTNISSE", "SPRACHEN"]
    assert all(p.style.name == "Heading 1" for p in ueberschriften)

    positionen = {p.text: i for i, p in enumerate(absaetze) if cv_export._ist_ueberschrift(p)}
    beruf_von, beruf_bis = positionen["BERUFSERFAHRUNG"], positionen["AUSBILDUNG"]
    stationen = [i for i in range(beruf_von + 1, beruf_bis) if cv_export._ist_stationsstart(absaetze[i])]
    assert len(stationen) == 2
    for i in stationen:
        anker, titel, beschreibung = absaetze[i], absaetze[i + 1], absaetze[i + 2]
        assert anker.style.name == "Normal" and all(r.bold for r in anker.runs if r.text.strip())
        assert all(r.font.size == Pt(11) for r in anker.runs if r.text.strip())
        assert anker.paragraph_format.space_before == Pt(26)
        assert cv_export._ist_stationstitel(titel) and titel.style.name == "Normal"
        assert all(r.font.size == Pt(11) for r in titel.runs if r.text.strip())
        assert any(r.italic for r in beschreibung.runs) and "\t" not in beschreibung.text
        aufzaehlung = []
        for p in absaetze[i + 3:beruf_bis]:
            if p.style.name != "List Paragraph":
                break
            aufzaehlung.append(p)
        assert len(aufzaehlung) >= 3
        for p in aufzaehlung:
            assert p._p.pPr.numPr is not None and p._p.pPr.numPr.numId.val == 1   # Nummerierung (Punkte)

    # Der Tabulator steht nur an den Stationsankern und in der einen Ausbildungszeile.
    tab_zeilen = [i for i, p in enumerate(absaetze) if "\t" in p.text]
    assert tab_zeilen == stationen + [positionen["AUSBILDUNG"] + 1]
    ausbildung = absaetze[positionen["AUSBILDUNG"] + 1]
    assert ausbildung.text.endswith("2017 bis 2019") and positionen["KENNTNISSE"] == positionen["AUSBILDUNG"] + 2
    # Übrige Rubriken trennen mit „•“, ohne Aufzählungsabsätze.
    uebrige = absaetze[positionen["KENNTNISSE"] + 1:]
    assert uebrige and all(p.style.name != "List Paragraph" for p in uebrige)
    assert any("•" in p.text for p in uebrige)

    # Wie der Seitenumbruch-Schutz und der Upload-Check zählen: 2 Berufs- plus 1 Ausbildungsstation.
    assert len(cv_export._stationsgrenzen(absaetze)) == 3
    assert cv_export._seitenumbrueche_schuetzen(Document(str(pfad))) == 3
    assert main._cv_struktur(pfad) == (3, None)

    entwurf = cv_export.entwurf_extrahieren(pfad)
    bullets = [e for e in entwurf if e["ist_bullet"]]
    assert len(bullets) == 7 and all(e["style"] == "List Paragraph" for e in bullets)

    # Der Entwurfs-Editor klont einen vorhandenen Aufzählungsabsatz samt Nummerierung: Das muss mit
    # dieser Datei funktionieren, sonst wäre der Basis-CV im Editor nicht zu bearbeiten.
    kopie = tmp_path / "kopie.docx"
    shutil.copy(pfad, kopie)
    erste_beschreibung = stationen[0] + 2
    assert cv_export.entwurf_zurueckschreiben(
        kopie, [{"anchor_i": erste_beschreibung, "bullet_texte": ["Neu eins", "Neu zwei"]}]) == 1
    neu = Document(str(kopie)).paragraphs
    assert [p.text for p in neu[erste_beschreibung + 1:erste_beschreibung + 3]] == ["Neu eins", "Neu zwei"]
    assert all(p._p.pPr.numPr is not None for p in neu[erste_beschreibung + 1:erste_beschreibung + 3])


# ── 3. Entfernen ─────────────────────────────────────────────────────────────────────────────
def test_entfernen_sichert_vorher_und_raeumt_nur_markiertes_weg(angelegt):
    from app.models import (Application, CareerEntry, Company, Email, Interview, Job, NetworkContact,
                            Profile, ProfileSkill)

    eigene = _eigene_daten(angelegt)
    markierung = _markierung(angelegt)

    ergebnis = _entfernen(angelegt)

    # Antwort
    assert ergebnis["ok"] is True
    assert ergebnis["entfernt"] == {
        "stellen": 5, "firmen": 6, "bewerbungen": 3, "mails": 5, "gespraeche": 1, "kontakte": 1,
        "netzwerk": 1, "skills": 14, "werdegang": 5, "dateien": 2}
    assert ergebnis["geloest"] == {"mails": 1, "aufgaben": 0}
    assert ergebnis["behalten"] == []
    assert ergebnis["status"]["status"] == "entfernt"
    assert ergebnis["status"]["entfernt_am"] == "2026-10-01T09:30:00"

    # Sicherung: eine Datei in der Reihe der automatischen Sicherungen, mit dem Stand VOR dem Entfernen.
    assert _sicherungen(angelegt) == [ergebnis["sicherung"]]
    entpackt = angelegt.projekt.parent / "gesichert.sqlite"
    with zipfile.ZipFile(angelegt.daten / "backups" / "auto" / ergebnis["sicherung"]) as zf:
        entpackt.write_bytes(zf.read("bewerbung.sqlite"))
    verbindung = sqlite3.connect(str(entpackt))
    try:
        assert verbindung.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 6
        assert verbindung.execute("SELECT COUNT(*) FROM company").fetchone()[0] == 7
    finally:
        verbindung.close()

    # Markierte Zeilen sind weg, in jeder Tabelle.
    for tabelle, ids in markierung["ids"].items():
        assert ids, tabelle
        liste = ",".join(str(i) for i in ids)
        with angelegt.engine.connect() as verbindung:
            rest = verbindung.exec_driver_sql(f"SELECT COUNT(*) FROM {tabelle} WHERE id IN ({liste})").scalar()
        assert rest == 0, tabelle

    # Eigene Zeilen bleiben, auch die an der Beispielstelle hängende Mail (nur gelöst).
    assert [j.id for j in _alle(angelegt, Job)] == [eigene.job_id]
    assert [f.id for f in _alle(angelegt, Company)] == [eigene.firma_id]
    assert [a.id for a in _alle(angelegt, Application)] == [eigene.bewerbung_id]
    assert [s.id for s in _alle(angelegt, ProfileSkill)] == [eigene.skill_id]
    assert [w.id for w in _alle(angelegt, CareerEntry)] == [eigene.werdegang_id]
    assert [n.id for n in _alle(angelegt, NetworkContact)] == [eigene.netzwerk_id]
    assert _anzahl(angelegt, "interview") == 0 and _anzahl(angelegt, "contact") == 0
    mails = {m.id: m for m in _alle(angelegt, Email)}
    assert set(mails) == {eigene.mail_id, eigene.lose_mail_id, eigene.angehaengte_mail_id}
    assert mails[eigene.mail_id].job_id == eigene.job_id
    angehaengt = mails[eigene.angehaengte_mail_id]
    assert (angehaengt.job_id, angehaengt.application_id, angehaengt.company_id) == (None, None, None)

    # Profil: Beispielwerte geleert (sie waren unverändert).
    (profil,) = _alle(angelegt, Profile)
    assert (profil.headline, profil.standort, profil.positionierung) == (None, None, None)

    # Dateien: unverändert, also im Papierkorb mit Datumspräfix, am alten Ort weg.
    assert _papierkorb(angelegt) == ["20261001_base_de.docx", "20261001_profil.md"]
    assert not (angelegt.projekt / "config" / "profil.md").exists()
    assert not (angelegt.projekt / "data" / "cv_basis" / "base_de.docx").exists()

    # Markierung
    nachher = _markierung(angelegt)
    assert nachher["status"] == "entfernt" and nachher["sicherung"] == ergebnis["sicherung"]
    assert nachher["entfernt_am"] == "2026-10-01T09:30:00" and nachher["ids"] == {}


def test_entfernen_loescht_keine_eigene_stelle(angelegt):
    """Gegenprobe für die Kernregel „nur markierte Zeilen“: Auch eine eigene Stelle bei einer eigenen
    Firma samt Bewerbung und Mail bleibt vollständig erhalten."""
    from app.models import Job

    eigene = _eigene_daten(angelegt)
    _entfernen(angelegt)

    (stelle,) = _alle(angelegt, Job)
    assert stelle.id == eigene.job_id and stelle.title == "Eigene Stelle"
    assert _anzahl(angelegt, "company") == 1 and _anzahl(angelegt, "application") == 1
    assert _anzahl(angelegt, "email") == 3


def test_wiederverwendete_ids_loeschen_keine_eigenen_zeilen(angelegt):
    """SQLite vergibt die Id einer gelöschten Zeile mit der höchsten Id neu. Löscht ein Kunde zum Beispiel
    den zuletzt angelegten Beispiel-Skill von Hand und trägt danach einen eigenen ein, trägt dieser
    dieselbe Id wie in der Markierung. Das Entfernen prüft deshalb zusätzlich ein Merkmal der
    Beispielzeile (Quelle, Schlüssel, Firmenname, Absender) und lässt die eigene Zeile stehen."""
    from sqlmodel import Session
    from app.models import CareerEntry, Company, Contact, Email, Job, NetworkContact, ProfileSkill

    hoechste = {tabelle: max(_markierung(angelegt)["ids"][tabelle]) for tabelle in (
        "profileskill", "careerentry", "company", "email", "networkcontact", "contact", "job")}
    with angelegt.engine.begin() as verbindung:
        for tabelle, id_ in hoechste.items():
            verbindung.exec_driver_sql(f"DELETE FROM {tabelle} WHERE id = {id_}")
    eigene = [ProfileSkill(bereich="Eigen", name="Eigener Skill", quelle="manuell"),
              CareerEntry(art="Beruf", firma="Eigene Firma", quelle="manuell"),
              Company(name="Eigene Firma GmbH"),
              Email(subject="Eigene Mail", from_addr="Eigener Absender <a@example.com>"),
              NetworkContact(name="Eigene Person", dedup_key="manuell|eigene person"),
              Contact(name="Eigene Ansprechperson", email="x@example.com"),
              Job(title="Eigene Stelle", dedup_key="manuell|eigene firma|eigene stelle", status="Neu")]
    with Session(angelegt.engine) as session:
        session.add_all(eigene)
        session.commit()
        neue_ids = {type(zeile).__tablename__: zeile.id for zeile in eigene}
    assert neue_ids == hoechste, "Voraussetzung: SQLite hat die Ids der gelöschten Zeilen wiederverwendet"

    _entfernen(angelegt)

    for tabelle, id_ in hoechste.items():
        assert _anzahl(angelegt, tabelle) == 1, tabelle
        with angelegt.engine.connect() as verbindung:
            assert verbindung.exec_driver_sql(f"SELECT COUNT(*) FROM {tabelle} WHERE id = {id_}").scalar() == 1
    assert _alle(angelegt, ProfileSkill)[0].name == "Eigener Skill"
    assert _alle(angelegt, Job)[0].title == "Eigene Stelle"
    assert _alle(angelegt, Company)[0].name == "Eigene Firma GmbH"


def test_gewohnte_bearbeitung_macht_beispielzeilen_nicht_zu_eigenen(angelegt):
    """Wer eine Beispielzeile in der Oberfläche bearbeitet (Notiz, Status, Wiedervorlage), ändert damit
    nichts an ihrer Herkunft: Sie wird beim Entfernen trotzdem mitgenommen. Der Netzwerk-Kontakt ist der
    heikle Fall, denn die App berechnet seinen Schlüssel bei JEDEM Speichern aus Name und Unternehmen
    neu (`update_network_contact`), und der Schlüssel verliert dabei das Präfix der Beispieldaten."""
    from app import normalize as N

    with angelegt.engine.begin() as verbindung:
        verbindung.exec_driver_sql(
            "UPDATE networkcontact SET notizen = 'Meine Notiz', dedup_key = ?",
            (N.slug_parts("Paul Paket", "Blitzpaket Zustelldienst GmbH"),))
        verbindung.exec_driver_sql("UPDATE job SET status = 'Geparkt', notes = 'Meine Notiz'")
        verbindung.exec_driver_sql("UPDATE company SET notes = 'Meine Notiz', situation = 'BUILD'")
        verbindung.exec_driver_sql("UPDATE profileskill SET note = 'Meine Notiz'")
        verbindung.exec_driver_sql("UPDATE careerentry SET beschreibung = 'Meine Notiz'")

    ergebnis = _entfernen(angelegt)

    assert ergebnis["entfernt"]["netzwerk"] == 1 and ergebnis["entfernt"]["stellen"] == 5
    for tabelle in TABELLEN:
        assert _anzahl(angelegt, tabelle) == 0, tabelle


def test_umbenannter_netzwerk_kontakt_gehoert_dem_kunden(angelegt):
    with angelegt.engine.begin() as verbindung:
        verbindung.exec_driver_sql("UPDATE networkcontact SET name = 'Paula Paket'")

    ergebnis = _entfernen(angelegt)

    assert ergebnis["entfernt"]["netzwerk"] == 0
    assert _anzahl(angelegt, "networkcontact") == 1


def test_geaenderte_dateien_bleiben_erhalten(angelegt):
    """Nur Dateien, deren SHA-256 noch dem angelegten Stand entspricht, wandern in den Papierkorb."""
    profil = angelegt.projekt / "config" / "profil.md"
    cv = angelegt.projekt / "data" / "cv_basis" / "base_de.docx"
    profil.write_text(profil.read_text(encoding="utf-8") + "- Eigene Ergänzung\n", encoding="utf-8")

    ergebnis = _entfernen(angelegt)

    assert ergebnis["behalten"] == ["config/profil.md"]
    assert ergebnis["entfernt"]["dateien"] == 1
    assert profil.is_file() and "Eigene Ergänzung" in profil.read_text(encoding="utf-8")
    assert not cv.exists() and _papierkorb(angelegt) == ["20261001_base_de.docx"]


def test_ersetzter_lebenslauf_bleibt_erhalten(angelegt):
    """Wer den Beispiel-Lebenslauf über die Profil-Seite durch den eigenen ersetzt hat, behält ihn."""
    cv = angelegt.projekt / "data" / "cv_basis" / "base_de.docx"
    cv.write_bytes(b"mein eigener Lebenslauf")

    ergebnis = _entfernen(angelegt)

    assert ergebnis["behalten"] == ["data/cv_basis/base_de.docx"]
    assert cv.read_bytes() == b"mein eigener Lebenslauf"


def test_fehlende_dateien_sind_kein_fehler(angelegt):
    (angelegt.projekt / "config" / "profil.md").unlink()
    ergebnis = _entfernen(angelegt)
    assert ergebnis["behalten"] == [] and ergebnis["entfernt"]["dateien"] == 1


def test_profilwerte_werden_nur_geleert_wenn_sie_unveraendert_sind(angelegt):
    from sqlmodel import Session
    from app.models import Profile

    with Session(angelegt.engine) as session:
        profil = session.get(Profile, 1)
        profil.headline = "Mein eigener Titel"
        session.add(profil)
        session.commit()

    _entfernen(angelegt)

    (profil,) = _alle(angelegt, Profile)
    assert profil.headline == "Mein eigener Titel"
    assert profil.standort is None and profil.positionierung is None


def test_zweites_entfernen_scheitert_und_legt_keine_zweite_sicherung_an(angelegt):
    _entfernen(angelegt)
    assert len(_sicherungen(angelegt)) == 1

    with pytest.raises(ValueError) as fehler:
        _entfernen(angelegt)

    assert str(fehler.value) == KEINE_BEISPIELDATEN_TEXT
    assert len(_sicherungen(angelegt)) == 1


def test_entfernen_ohne_beispieldaten_scheitert(umgebung):
    with pytest.raises(ValueError) as fehler:
        _entfernen(umgebung)
    assert str(fehler.value) == KEINE_BEISPIELDATEN_TEXT
    assert _sicherungen(umgebung) == []


def test_nach_dem_entfernen_wird_nie_erneut_angelegt(angelegt):
    """Die Tabellen sind danach wieder leer, die Datenbank-Datei gab es aber schon: Die Markierung
    „entfernt“ allein verhindert die Neuanlage, auch wenn jemand `db_war_da=False` übergibt."""
    _entfernen(angelegt)
    assert _einspielen(angelegt, db_war_da=False) is False
    assert _anzahl(angelegt, "job") == 0
    assert not (angelegt.projekt / "config" / "profil.md").exists()


def test_laeuft_eine_sicherung_bleibt_alles_unveraendert(angelegt, monkeypatch):
    from app import sicherung

    def laeuft(*args, **kwargs):
        raise sicherung.SicherungLaeuft("Es läuft bereits eine Sicherung.")

    monkeypatch.setattr(sicherung, "anlegen", laeuft)

    with pytest.raises(ValueError) as fehler:
        _entfernen(angelegt)

    assert str(fehler.value) == SICHERUNG_LAEUFT_TEXT
    assert _anzahl(angelegt, "job") == 5 and _markierung(angelegt)["status"] == "vorhanden"
    assert (angelegt.projekt / "config" / "profil.md").exists()


def test_scheitert_die_sicherung_bleibt_alles_unveraendert(angelegt, monkeypatch):
    """Ohne Sicherung wird nichts gelöscht."""
    from app import sicherung

    def kaputt(*args, **kwargs):
        raise OSError("Platte voll (Test)")

    monkeypatch.setattr(sicherung, "anlegen", kaputt)

    with pytest.raises(RuntimeError) as fehler:
        _entfernen(angelegt)

    assert "Die Sicherung vor dem Entfernen ist fehlgeschlagen" in str(fehler.value)
    assert "Platte voll" in str(fehler.value)
    assert _anzahl(angelegt, "job") == 5 and _anzahl(angelegt, "company") == 6
    assert _markierung(angelegt)["status"] == "vorhanden"
    assert (angelegt.projekt / "data" / "cv_basis" / "base_de.docx").exists()


def test_laufende_aufgabe_an_einer_beispielstelle_verhindert_das_entfernen(angelegt):
    """Eine Aufgabe würde nach dem Löschen Zeilen an eine Stelle schreiben, die es nicht mehr gibt. Eine
    beendete Aufgabe bleibt als Kosten-Historie, nur ohne Verweis auf die Stelle."""
    from sqlmodel import Session
    from app.models import AgentTask, Job

    stelle = next(j for j in _alle(angelegt, Job) if j.status == "Interview")
    with Session(angelegt.engine) as session:
        aufgabe = AgentTask(kind="firma-pruefen", job_id=stelle.id, status="running", cost_usd=0.4)
        session.add(aufgabe)
        session.commit()
        aufgabe_id = aufgabe.id

    with pytest.raises(ValueError) as fehler:
        _entfernen(angelegt)

    assert "läuft gerade eine Aufgabe" in str(fehler.value)
    assert _anzahl(angelegt, "job") == 5 and _sicherungen(angelegt) == []

    with Session(angelegt.engine) as session:
        session.get(AgentTask, aufgabe_id).status = "done"
        session.commit()
    ergebnis = _entfernen(angelegt)

    assert ergebnis["geloest"]["aufgaben"] == 1
    (aufgabe,) = _alle(angelegt, AgentTask)
    assert aufgabe.job_id is None and aufgabe.cost_usd == 0.4 and aufgabe.status == "done"


def test_laeuft_das_entfernen_schon_wird_ein_zweiter_aufruf_hoeflich_abgewiesen(angelegt):
    from app import beispieldaten

    assert beispieldaten._LOCK.acquire(blocking=False)
    try:
        with pytest.raises(ValueError) as fehler:
            _entfernen(angelegt)
    finally:
        beispieldaten._LOCK.release()
    assert "gerade entfernt" in str(fehler.value)
    assert _anzahl(angelegt, "job") == 5


def test_artefakte_an_beispielstellen_wandern_in_den_papierkorb(angelegt):
    """Hat der Nutzer an einer Beispielstelle etwas erzeugt (Lebenslauf, Anhang, Firmen-Bericht), geht
    die Datei mit den Zeilen in den Papierkorb. Eigene Dateien, Pfade außerhalb von `data/` und
    `outputs/` sowie Basis-Lebensläufe bleiben liegen, auch bei `..` im gespeicherten Pfad."""
    from sqlmodel import Session
    from app.models import Company, CVVersion, Job, JobFile

    root = angelegt.projekt
    dateien = {
        "outputs/cv/CV_Beispiel.docx": b"cv", "data/job_files/job_x/anhang.pdf": b"pdf",
        "data/company_fit/bericht.html": b"<html></html>", "outputs/cv/eigene_datei.docx": b"eigen",
        "config/andere.md": b"config", "data/cv_basis/base_en.docx": b"englisch"}
    for rel, inhalt in dateien.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(inhalt)
    eigene = _eigene_daten(angelegt)

    with Session(angelegt.engine) as session:
        stelle = session.get(Job, eigene.beispielstelle_id)
        firma = session.get(Company, stelle.company_id)
        firma.fit_analysis_path = "data/company_fit/bericht.html"
        session.add_all([
            CVVersion(job_id=stelle.id, file_path="outputs/cv/CV_Beispiel.docx"),
            JobFile(job_id=stelle.id, filename="anhang.pdf", file_path="data/job_files/job_x/anhang.pdf"),
            CVVersion(job_id=stelle.id, file_path="data/../config/andere.md"),       # Umweg über `..`
            CVVersion(job_id=stelle.id, file_path="data/cv_basis/base_en.docx"),       # Basis-Lebenslauf
            CVVersion(job_id=eigene.job_id, file_path="outputs/cv/eigene_datei.docx"),
            firma])
        session.commit()

    ergebnis = _entfernen(angelegt)

    assert ergebnis["entfernt"]["dateien"] == 5       # profil.md, base_de.docx und drei Artefakte
    assert _papierkorb(angelegt) == [
        "20261001_CV_Beispiel.docx", "20261001_anhang.pdf", "20261001_base_de.docx",
        "20261001_bericht.html", "20261001_profil.md"]
    for rel in ("outputs/cv/eigene_datei.docx", "config/andere.md", "data/cv_basis/base_en.docx"):
        assert (root / rel).is_file(), rel
    assert _anzahl(angelegt, "cvversion") == 1 and _anzahl(angelegt, "jobfile") == 0


def test_status_form(umgebung):
    from app import beispieldaten

    keine = beispieldaten.status(umgebung.daten)
    assert keine == {"status": "keine", "name": None, "angelegt_am": None, "entfernt_am": None, "anzahl": {}}

    _einspielen(umgebung)
    vorhanden = beispieldaten.status(umgebung.daten)
    assert vorhanden["status"] == "vorhanden" and vorhanden["name"] == "Benno Bewerbaer"
    assert vorhanden["angelegt_am"] == "2026-10-01T09:30:00" and vorhanden["entfernt_am"] is None
    assert vorhanden["anzahl"] == {
        "stellen": 5, "firmen": 6, "bewerbungen": 3, "mails": 5, "gespraeche": 1, "kontakte": 1,
        "netzwerk": 1, "skills": 14, "werdegang": 5, "dateien": 2}

    _entfernen(umgebung)
    entfernt = beispieldaten.status(umgebung.daten)
    assert entfernt["status"] == "entfernt" and entfernt["entfernt_am"] == "2026-10-01T09:30:00"
    assert entfernt["anzahl"] == {}


def test_unlesbare_markierung_ist_kein_absturz(umgebung):
    from app import beispieldaten

    (umgebung.daten / "beispieldaten.json").write_text("{kaputt", encoding="utf-8")
    assert beispieldaten.status(umgebung.daten)["status"] == "keine"
    assert _einspielen(umgebung) is False          # Die Datei existiert: nie zweimal


# ── 4. Router (eigene FastAPI-App) ───────────────────────────────────────────────────────────
@pytest.fixture()
def router_client(angelegt, monkeypatch):
    """Nur der Beispieldaten-Router in einer eigenen App. Er ruft die Funktionen ohne Parameter auf und
    schreibt danach `config/profil_struktur.md`: Alles, was er dafür auflöst, zeigt auf `tmp_path`."""
    import app.main as main
    from app import db
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes_beispieldaten import router

    monkeypatch.setattr(db, "DATA_DIR", angelegt.daten)
    monkeypatch.setattr(db, "DB_PATH", angelegt.daten / "bewerbung.sqlite")
    monkeypatch.setattr(db, "PROJECT_ROOT", angelegt.projekt)
    monkeypatch.setattr(db, "engine", angelegt.engine)
    struktur = angelegt.projekt / "config" / "profil_struktur.md"
    monkeypatch.setattr(main, "_PROFIL_STRUKTUR_PATH", struktur)
    assert str(main._PROFIL_STRUKTUR_PATH).startswith(str(angelegt.projekt))

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    client.profil_struktur = struktur
    return client


def test_router_get_liefert_den_status(router_client, angelegt):
    r = router_client.get("/api/beispieldaten")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "vorhanden" and body["name"] == "Benno Bewerbaer"
    assert body["anzahl"]["stellen"] == 5 and body["anzahl"]["dateien"] == 2


def test_router_get_ohne_markierung_meldet_keine(router_client, angelegt):
    (angelegt.daten / "beispieldaten.json").unlink()
    assert router_client.get("/api/beispieldaten").json()["status"] == "keine"


def test_router_entfernen_ergebnis_und_profil_struktur(router_client, angelegt):
    assert not router_client.profil_struktur.exists()

    r = router_client.post("/api/beispieldaten/entfernen")

    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"ok", "entfernt", "geloest", "behalten", "sicherung", "status"}
    assert body["ok"] is True and body["entfernt"]["stellen"] == 5
    assert body["sicherung"].startswith("bewerbung_") and body["sicherung"].endswith(".zip")
    assert body["status"]["status"] == "entfernt"
    assert _anzahl(angelegt, "job") == 0
    # Die abgeleitete Profil-Struktur wurde neu geschrieben, jetzt ohne die Beispiel-Skills.
    assert router_client.profil_struktur.is_file()
    assert "Paketzustellung" not in router_client.profil_struktur.read_text(encoding="utf-8")

    assert router_client.get("/api/beispieldaten").json()["status"] == "entfernt"


def test_router_zweites_entfernen_gibt_409(router_client, angelegt):
    assert router_client.post("/api/beispieldaten/entfernen").status_code == 200
    r = router_client.post("/api/beispieldaten/entfernen")
    assert r.status_code == 409
    assert r.json()["detail"] == KEINE_BEISPIELDATEN_TEXT


def test_router_laeuft_eine_sicherung_gibt_409_mit_kundentext(router_client, angelegt, monkeypatch):
    from app import sicherung

    def laeuft(*args, **kwargs):
        raise sicherung.SicherungLaeuft("Es läuft bereits eine Sicherung.")

    monkeypatch.setattr(sicherung, "anlegen", laeuft)
    r = router_client.post("/api/beispieldaten/entfernen")
    assert r.status_code == 409 and r.json()["detail"] == SICHERUNG_LAEUFT_TEXT
    assert _anzahl(angelegt, "job") == 5


def test_router_gescheiterte_sicherung_gibt_500_und_aendert_nichts(router_client, angelegt, monkeypatch):
    from app import sicherung

    monkeypatch.setattr(sicherung, "anlegen", lambda *a, **k: (_ for _ in ()).throw(OSError("voll")))
    r = router_client.post("/api/beispieldaten/entfernen")
    assert r.status_code == 500
    assert r.json()["detail"].startswith("Die Sicherung vor dem Entfernen ist fehlgeschlagen")
    assert _anzahl(angelegt, "job") == 5 and _markierung(angelegt)["status"] == "vorhanden"


# ── 5. Erst-Start im Subprozess ──────────────────────────────────────────────────────────────
def _im_subprozess(code: str, data_dir: Path):
    umgebung = dict(os.environ, BMS_DATA_DIR=str(data_dir))
    umgebung.pop("BMS_BEISPIELDATEN", None)
    return subprocess.run([sys.executable, "-c", code], cwd=str(BACKEND_DIR), env=umgebung,
                          capture_output=True, text=True, timeout=180)


def _ergebnis(lauf) -> dict:
    assert lauf.returncode == 0, f"Subprozess scheiterte:\n{lauf.stderr}"
    zeilen = [z for z in lauf.stdout.splitlines() if z.startswith("ERGEBNIS:")]
    assert len(zeilen) == 1, lauf.stdout
    return json.loads(zeilen[0][len("ERGEBNIS:"):])


def test_erststart_legt_einmal_an_und_beim_neustart_nichts_nach(tmp_path):
    """Der Ablauf, den `main._startup()` bekommt: `DB_PATH.exists()` VOR `init_db()`, danach
    `einspielen_falls_neu`. Der volle Import von `app.main` legt dabei keine Datenbank-Datei an (sonst
    wäre `db_war_da` auf einer frischen Installation immer wahr). Projekt-Root ist ein Wegwerf-Ordner
    mit Manifest, nie die echte Installation. Der Neustart läuft als zweiter Prozess."""
    projekt = tmp_path / "projekt"
    projekt.mkdir()
    (projekt / "bms_manifest.json").write_text("{}", encoding="utf-8")
    daten = tmp_path / "frisch" / "daten"

    erster = (
        "import json\n"
        "from pathlib import Path\n"
        "import app.main\n"
        "from app.db import DB_PATH, init_db\n"
        "db_war_da = DB_PATH.exists()\n"
        "init_db()\n"
        "from app import beispieldaten\n"
        f"angelegt = beispieldaten.einspielen_falls_neu(db_war_da, projekt_root=Path({str(projekt)!r}))\n"
        "print('ERGEBNIS:' + json.dumps({'db_war_da': db_war_da, 'angelegt': angelegt,\n"
        "                                'status': beispieldaten.status()['status']}))\n")
    ergebnis = _ergebnis(_im_subprozess(erster, daten))
    assert ergebnis == {"db_war_da": False, "angelegt": True, "status": "vorhanden"}

    verbindung = sqlite3.connect(str(daten / "bewerbung.sqlite"))
    try:
        zahlen = {t: verbindung.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("job", "company", "application", "email", "profileskill")}
    finally:
        verbindung.close()
    assert zahlen == {"job": 5, "company": 6, "application": 3, "email": 5, "profileskill": 14}
    assert (projekt / "config" / "profil.md").is_file()
    assert (projekt / "data" / "cv_basis" / "base_de.docx").is_file()
    markierung = (daten / "beispieldaten.json").read_text(encoding="utf-8")

    zweiter = (
        "import json\n"
        "from pathlib import Path\n"
        "from app.db import DB_PATH, init_db\n"
        "db_war_da = DB_PATH.exists()\n"
        "init_db()\n"
        "from app import beispieldaten\n"
        f"angelegt = beispieldaten.einspielen_falls_neu(db_war_da, projekt_root=Path({str(projekt)!r}))\n"
        "print('ERGEBNIS:' + json.dumps({'db_war_da': db_war_da, 'angelegt': angelegt}))\n")
    assert _ergebnis(_im_subprozess(zweiter, daten)) == {"db_war_da": True, "angelegt": False}
    assert (daten / "beispieldaten.json").read_text(encoding="utf-8") == markierung
    verbindung = sqlite3.connect(str(daten / "bewerbung.sqlite"))
    try:
        assert verbindung.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 5
    finally:
        verbindung.close()



def _startup_skript(projekt: Path) -> str:
    """Ruft den ECHTEN `main._startup()` auf. Alles, was dabei an den Projekt-Root ginge, zeigt auf
    den Wegwerf-Ordner: `db.PROJECT_ROOT` (Profil-Datei, Basis-Lebenslauf, Installationsart) und
    `main._PROFIL_STRUKTUR_PATH`; `suchprofil.sicherstellen` bindet seinen Pfad schon beim Import und
    wird deshalb ersetzt. Worker und Sicherungstakt starten nicht."""
    return (
        "import json\n"
        "from pathlib import Path\n"
        "import app.main as main\n"
        "from app import agent_runner, beispieldaten, db, sicherung\n"
        "from pipeline import suchprofil\n"
        f"projekt = Path({str(projekt)!r})\n"
        "db.PROJECT_ROOT = projekt\n"
        "main._PROFIL_STRUKTUR_PATH = projekt / 'config' / 'profil_struktur.md'\n"
        "suchprofil.sicherstellen = lambda *a, **k: False\n"
        "agent_runner.start_workers = lambda: None\n"
        "sicherung.starten = lambda: None\n"
        "db_vorher = db.DB_PATH.exists()\n"
        "main._startup()\n"
        "print('ERGEBNIS:' + json.dumps({'db_vorher': db_vorher, 'status': beispieldaten.status()['status']}))\n")


def test_echter_startup_legt_beispieldaten_an_und_beim_neustart_nichts_nach(tmp_path):
    """Verdrahtung in `main._startup()` (Hauptsession P2-59): `db_war_da` wird VOR `init_db()`
    festgestellt, die Beispieldaten entstehen, und die Profil-Struktur folgt ihnen. Ein zweiter Start
    legt keine Beispieldaten nach; nur die abgeleitete Profil-Struktur wird neu geschrieben, wenn sie
    fehlt (P2-83). Projekt-Root mit Manifest (Paket-Installation), nie die echte Installation."""
    projekt = tmp_path / "projekt"
    (projekt / "config").mkdir(parents=True)
    (projekt / "bms_manifest.json").write_text("{}", encoding="utf-8")
    daten = tmp_path / "daten"

    assert _ergebnis(_im_subprozess(_startup_skript(projekt), daten)) == {
        "db_vorher": False, "status": "vorhanden"}
    struktur = (projekt / "config" / "profil_struktur.md").read_text(encoding="utf-8")
    assert "Paketzustellung" in struktur and "Blitzpaket Zustelldienst GmbH" in struktur
    assert (projekt / "config" / "profil.md").is_file()
    assert (projekt / "data" / "cv_basis" / "base_de.docx").is_file()

    (projekt / "config" / "profil_struktur.md").unlink()
    assert _ergebnis(_im_subprozess(_startup_skript(projekt), daten)) == {
        "db_vorher": True, "status": "vorhanden"}
    # P2-83: Die abgeleitete Datei entsteht bei jedem Start neu, wenn sie fehlt ...
    nachgeschrieben = (projekt / "config" / "profil_struktur.md").read_text(encoding="utf-8")
    assert "Paketzustellung" in nachgeschrieben
    # ... Beispieldaten werden dagegen nicht nachgelegt:
    verbindung = sqlite3.connect(str(daten / "bewerbung.sqlite"))
    try:
        assert verbindung.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 5
    finally:
        verbindung.close()


def test_beworben_check_laesst_die_beispielstellen_aus(angelegt):
    """Der Tageslauf startet den Beworben-Check. Die Beispielstellen im Status Beworben und Interview
    haben keine Anzeige und erfundene Firmen: Ohne Filter liefe eine bezahlte Suche nach ihren
    Karriereseiten. Beide Seiten des Vertrags: Die Beispielstellen tragen `portal` „Beispieldaten“,
    und der Skill filtert in Prüfmenge und Skip-Check genau darauf (Abnahme P2-59)."""
    skill = (PROJEKT_DIR / ".claude" / "skills" / "beworben-check" / "SKILL.md").read_text(encoding="utf-8")
    assert skill.count("if j.get('portal') != 'Beispieldaten'") == 2
    with angelegt.engine.connect() as verbindung:
        portale = {zeile[0] for zeile in verbindung.exec_driver_sql(
            "SELECT portal FROM job WHERE status IN ('Beworben', 'Interview')")}
    assert portale == {"Beispieldaten"}


def test_beispiel_kontakt_traegt_den_schluessel_der_app(angelegt):
    """Der Netzwerk-Kontakt der Beispieldaten trägt denselben Schlüssel, den die App beim Anlegen
    vergibt. Mit dem früheren „beispiel|paul-paket“ legte der Datei-Import (P2-62) beim Rundweg über
    den Excel-Export den Kontakt doppelt an (Fund der P2-62-Abnahme am Probeserver)."""
    from app import normalize as N

    with angelegt.engine.connect() as verbindung:
        schluessel = verbindung.exec_driver_sql(
            "SELECT dedup_key FROM networkcontact WHERE name = 'Paul Paket'").scalar_one()
    assert schluessel == N.slug_parts("Paul Paket", "Blitzpaket Zustelldienst GmbH")

# ── 6. Paketregeln und Schreibweise ──────────────────────────────────────────────────────────
def _alle_texte(u) -> str:
    """Jeder Text, den die Beispieldaten erzeugen: alle Textwerte der angelegten Zeilen, die
    Profil-Datei und der Text des Lebenslaufs."""
    from docx import Document

    zeilen = []
    with u.engine.connect() as verbindung:
        for tabelle in TABELLEN + ("profile",):
            for zeile in verbindung.exec_driver_sql(f"SELECT * FROM {tabelle}").fetchall():
                zeilen.extend(str(wert) for wert in zeile if isinstance(wert, str))
    zeilen.append((u.projekt / "config" / "profil.md").read_text(encoding="utf-8"))
    zeilen.extend(p.text for p in Document(str(u.projekt / "data" / "cv_basis" / "base_de.docx")).paragraphs)
    return "\n".join(zeilen)


def test_alle_erzeugten_texte_bestehen_die_paketregeln(angelegt):
    """Mail nur unter beispiel.de, Telefon nur die Beispielnummer, keine Muster wie Stellen- oder
    Mailnummern, kein Name des Nutzers (die Muster dafür kommen aus den lokalen Quellen der
    Personendaten-Prüfung), keine Gedankenstriche: Das verlangt die Paketprüfung für jeden
    ausgelieferten Text (`pipeline/kundenpaket.py`)."""
    from pipeline import kundenpaket

    text = _alle_texte(angelegt)
    assert kundenpaket.pruefen_eintraege([kundenpaket.Eintrag("beispieldaten/texte.txt", 0o644,
                                                               text.encode("utf-8"))]) == []
    assert "—" not in text and "–" not in text
    assert "+49 170 1234567" in text and "@beispiel.de" in text


@pytest.mark.parametrize("pfad", ["backend/app/beispieldaten.py", "backend/app/routes_beispieldaten.py",
                                  "frontend/src/pages/Einstellungen.tsx", "frontend/src/pages/Dashboard.tsx"])
def test_ausgelieferte_dateien_bestehen_die_paketregeln(pfad):
    """Die Python-Module tragen die Texte als String-Konstanten (auch die prüft die Paketprüfung), die
    beiden Oberflächen-Dateien enthalten die neue Karte und den Hinweis."""
    from pipeline import kundenpaket

    inhalt = (PROJEKT_DIR / pfad).read_bytes()
    assert kundenpaket.pruefen_eintraege([kundenpaket.Eintrag(pfad, 0o644, inhalt)]) == []


@pytest.mark.parametrize("pfad", ["backend/app/beispieldaten.py", "backend/app/routes_beispieldaten.py"])
def test_python_module_ohne_gedankenstriche_im_programmtext(pfad):
    quelltext = (PROJEKT_DIR / pfad).read_text(encoding="utf-8")
    assert "—" not in quelltext and "–" not in quelltext
    konstanten = [k.value for k in ast.walk(ast.parse(quelltext))
                  if isinstance(k, ast.Constant) and isinstance(k.value, str)]
    assert konstanten
