"""Sicherheitstests für GET /api/artifact: Phase 57 E1.4 (Traversal, absolute Pfade), P3-1
(struktureller Ordnervergleich statt String-Präfix), P2-14 (nosniff) und P2-54 (Positivliste).

P2-54 (28.09.2026): Der Endpunkt lieferte jede Datei unter data/ und outputs/ aus, auch
data/bewerbung.sqlite, data/backups/auto/*.zip und data/sicherung.json. Im LAN-Modus
(start_lan.command, ohne Anmeldung) konnte damit jeder im selben Netz die ganze Datenbank laden.
Seitdem gilt `main._ARTEFAKT_ORDNER`: nur die Ordner und Dateitypen, die die Oberfläche
tatsächlich öffnet (Bestandsaufnahme in tasks/spec_p2-54_artefakt_positivliste.md).

Isolation: Der Endpunkt liest `main._PROJECT_ROOT` bei jedem Aufruf. Die Fixture `projekt`
bindet es auf `tmp_path/projekt` um und legt dort echte Dateien an, `tmp_path` selbst dient als
„außerhalb des Projekts". So prüfen die 403-Fälle mit EXISTIERENDEN Dateien (403 kommt von der
Regel, nicht von einer fehlenden Datei), und kein Test fasst das echte data/ oder outputs/ an (bis
P2-54 schrieben zwei Tests hier Probedateien ins echte outputs/). Angelegt wird per pathlib,
angefragt mit Posix-Pfaden wie in der DB; damit prüft der Windows-Job (backend-windows)
dieselben Fälle.

App-Module nur funktionslokal importieren (s. conftest.py).
"""
import uuid

import pytest


def _anlegen(wurzel, rel, inhalt=b"x"):
    ziel = wurzel.joinpath(*rel.split("/"))
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(inhalt)
    return ziel


@pytest.fixture()
def projekt(tmp_path, monkeypatch):
    import app.main as main

    wurzel = tmp_path / "projekt"
    wurzel.mkdir()
    monkeypatch.setattr(main, "_PROJECT_ROOT", wurzel)
    return wurzel


_HTML = b'<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>ok</body></html>'

# Jeder Ordner der Positivliste mit den Dateitypen, die die Oberfläche von dort öffnet, und dem
# Content-Type der Inline-Anzeige (octet-stream = Browser lädt herunter).
ERLAUBT = [
    ("data/company_fit/2026_09_28_CompanyFit_Firma.html", "text/html"),
    ("data/company_fit/2026_09_28_Match_Firma.html", "text/html"),
    ("data/job_postings/2026_09_28_Stellenausschreibung_Firma.html", "text/html"),
    ("data/interview_prep/2026_09_28_Briefing_Firma_R1.html", "text/html"),
    ("data/beirat/2026_09_28_BeiratsCheck_Firma.html", "text/html"),
    ("data/analysen/2026_09_28_Analyse_Absagen.html", "text/html"),
    ("data/transcripts/2026_09_28_TranskriptReport_Firma.html", "text/html"),
    ("data/transcripts/2026_09_28_Transkript_Firma.md", "application/octet-stream"),
    ("data/job_files/job_7/2026_09_28_Stellenbeschreibung.pdf", "application/pdf"),
    ("data/job_files/job_7/2026_09_28_Praesentation.pptx", "application/octet-stream"),
    ("data/job_files/job_7/2026_09_28_Screenshot.png", "image/png"),
    ("data/job_files/job_7/2026_09_28_Transkript_Gespraech.vtt", "application/octet-stream"),
    ("data/profil/dateien/2026_09_28_Zeugnis.pdf", "application/pdf"),
    ("data/cv_basis/base_de.docx", "application/octet-stream"),
    ("data/cv_basis/entwuerfe/CV_Entwurf_Firma.docx", "application/octet-stream"),
    ("data/tmp/CV_Name_Firma_Entwurf.docx", "application/octet-stream"),
    ("outputs/cv/CV_Name_Firma_Position.docx", "application/octet-stream"),
    ("outputs/cv/CV_Name_Firma_Position.pdf", "application/pdf"),
    ("outputs/cv_entwuerfe/CV_Name_Entwurf.docx", "application/octet-stream"),
    ("outputs/anschreiben/Anschreiben_Name_Firma.docx", "application/octet-stream"),
    ("outputs/anschreiben/Anschreiben_Name_Firma.pdf", "application/pdf"),
]


@pytest.mark.parametrize("pfad, typ", ERLAUBT)
def test_erlaubte_dokumente_werden_ausgeliefert(client, projekt, pfad, typ):
    _anlegen(projekt, pfad, _HTML if pfad.endswith(".html") else b"inhalt")

    anzeige = client.get("/api/artifact", params={"path": pfad})
    assert anzeige.status_code == 200
    assert anzeige.headers["content-type"].startswith(typ)

    download = client.get("/api/artifact", params={"path": pfad, "download": "true"})
    assert download.status_code == 200
    assert "attachment" in download.headers.get("content-disposition", "")


# Jede dieser Dateien EXISTIERT im Test. 403 heißt also: die Regel greift, nicht „nicht gefunden".
GESPERRT = [
    # Datenbank samt Begleitdateien
    "data/bewerbung.sqlite",
    "data/bewerbung.sqlite-wal",
    "data/bewerbung.sqlite-shm",
    "data/bewerbung.sqlite-journal",
    # Sicherungen, Updates, Einstellungen
    "data/backups/bewerbung_backup_20260908_101500.sqlite",
    "data/backups/auto/bewerbung_2026-09-28_164620.zip",
    "data/updates/2026-09-28_120000_1.0.0_zu_1.1.0/datenbank.sqlite",
    "data/updates/2026-09-28_120000_1.0.0_zu_1.1.0/bericht.json",
    "data/sicherung.json",
    # eine Datenbank-Kopie in einem freigegebenen Ordner: der Ordner allein reicht nicht
    "data/company_fit/bewerbung.sqlite",
    "data/job_files/job_7/bewerbung.sqlite",
    "data/tmp/bewerbung.sqlite",
    # Ordner, die die Oberfläche nie öffnet
    "data/papierkorb/2026_09_28_CV_Firma.pdf",
    "data/mail_alerts/2026_09_28_Mail_Alerts.json",
    "data/arbeitsagentur/20260928_suche.json",
    "data/apify/suche.json",
    "data/agent_logs/task_1.jsonl",
    "data/digests/2026_09_28_Bewerbungs-Digest.html",
    "data/exports/coach_site/.htpasswd",
    "data/templates/vorlage.xlsx",
    "outputs/exports/2026_09_28_Bewerbungs-Stand.xlsx",
    "outputs/kundenpaket/BMS_1.0.0.zip",
    # freigegebener Ordner, aber ein Dateityp, den die Oberfläche von dort nie öffnet
    "data/tmp/company_fit_7.json",
    "data/tmp/skript.py",
    "data/tmp/anschreiben_7.txt",
    "data/beirat/2026_09_28_debatte.json",
    "data/interview_prep/fragenbank.md",
    "data/company_fit/.deepdive_7.json",
    "data/job_files/job_7/seite.html",
    "data/job_files/job_7/archiv.zip",
    # direkt in der Wurzel
    "data/probe.html",
    "outputs/probe.pdf",
]


@pytest.mark.parametrize("pfad", GESPERRT)
def test_gesperrte_dateien_403(client, projekt, pfad):
    _anlegen(projekt, pfad)

    assert client.get("/api/artifact", params={"path": pfad}).status_code == 403
    assert client.get("/api/artifact", params={"path": pfad, "download": "true"}).status_code == 403


def test_gesperrt_bleibt_403_auch_ohne_datei(client, projekt):
    """Kein Existenz-Orakel: Ob es eine Sicherung gibt, verrät der Endpunkt nicht."""
    r = client.get("/api/artifact", params={"path": "data/backups/auto/gibt_es_nicht.zip"})
    assert r.status_code == 403


def test_fehlende_datei_in_freigegebenem_ordner_404(client, projekt):
    r = client.get("/api/artifact", params={"path": "data/company_fit/gibt_es_nicht.html"})
    assert r.status_code == 404


@pytest.mark.parametrize("pfad", [
    "outputs/../data/bewerbung.sqlite",     # bis P2-54 kam das durch (zwischen zwei Wurzeln)
    "data/company_fit/../bewerbung.sqlite",
    "data/company_fit/../backups/auto/bewerbung_2026-09-28_164620.zip",
    "data/tmp/../../outputs/kundenpaket/BMS_1.0.0.zip",
    "./data/bewerbung.sqlite",
    "data//bewerbung.sqlite",
    "data\\backups\\auto\\bewerbung_2026-09-28_164620.zip",   # Trenner unter Windows
    "data/BACKUPS/auto/bewerbung_2026-09-28_164620.zip",      # macOS und Windows finden die Datei
])
def test_umwege_zu_gesperrten_dateien_403(client, projekt, pfad):
    _anlegen(projekt, "data/bewerbung.sqlite")
    _anlegen(projekt, "data/backups/auto/bewerbung_2026-09-28_164620.zip")
    _anlegen(projekt, "outputs/kundenpaket/BMS_1.0.0.zip")

    assert client.get("/api/artifact", params={"path": pfad}).status_code == 403


def test_doppelt_kodierte_punkte_403(client, projekt):
    """Starlette dekodiert den Query-Parameter, der Endpunkt ruft danach noch einmal `unquote`
    auf. Aus `%252e%252e` wird so erst `%2e%2e`, dann `..`. Geprüft wird nach beiden Schritten.
    Die Query steht deshalb fertig in der URL (nicht über `params=`, das würde neu kodieren)."""
    _anlegen(projekt, "data/bewerbung.sqlite")

    r = client.get("/api/artifact?path=data%2Fcompany_fit%2F%252e%252e%2Fbewerbung.sqlite")
    assert r.status_code == 403


def test_symlink_in_freigegebenem_ordner_auf_die_datenbank_403(client, projekt):
    """Die Prüfung sieht den aufgelösten Pfad, nicht den Namen des Links."""
    db = _anlegen(projekt, "data/bewerbung.sqlite")
    link = projekt / "data" / "company_fit" / "bericht.html"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(db)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks lassen sich hier nicht anlegen (Windows ohne Entwicklermodus)")

    assert client.get("/api/artifact", params={"path": "data/company_fit/bericht.html"}).status_code == 403


def test_symlink_schleife_403_statt_500(client, projekt):
    """`resolve()` wirft bei einer Schleife unter Python 3.12 einen RuntimeError."""
    schleife = projekt / "data" / "company_fit" / "schleife.html"
    schleife.parent.mkdir(parents=True, exist_ok=True)
    try:
        schleife.symlink_to(schleife)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks lassen sich hier nicht anlegen (Windows ohne Entwicklermodus)")

    assert client.get("/api/artifact", params={"path": "data/company_fit/schleife.html"}).status_code == 403


def test_ueberlanger_dateiname_404_statt_500(client, projekt):
    """`Path.is_file()` wirft bei einem Namen über 255 Zeichen (ENAMETOOLONG), `os.path.isfile`
    nicht. Der Ordner muss existieren, sonst scheitert `stat` schon an ihm (ENOENT)."""
    (projekt / "data" / "company_fit").mkdir(parents=True)

    r = client.get("/api/artifact", params={"path": "data/company_fit/" + "A" * 300 + ".html"})
    assert r.status_code == 404


def test_absoluter_pfad_in_freigegebenem_ordner_200(client, projekt):
    """Ältere Einträge können absolute Pfade tragen (`_rel()` in deepdive, interview und cv_export
    speichert, was ein Skill übergibt). Liegt die Datei in einem freigegebenen Ordner, gilt sie."""
    bericht = _anlegen(projekt, "data/company_fit/2026_09_28_CompanyFit_Firma.html", _HTML)

    assert client.get("/api/artifact", params={"path": str(bericht)}).status_code == 200


@pytest.mark.parametrize("pfad, erwartet", [
    (r"\\rechner\freigabe\bericht.html", True),
    ("//rechner/freigabe/bericht.html", True),
    (r"\\?\C:\BMS\data\company_fit\bericht.html", True),
    (r"\\.\PhysicalDrive0", True),
    (r"C:\BMS\data\company_fit\bericht.html", False),
    ("data/company_fit/bericht.html", False),
])
def test_netzpfad_erkennt_unc_und_geraetepfade(pfad, erwartet):
    """Mit Windows-Semantik (PureWindowsPath) und damit auf jedem Betriebssystem aussagekräftig."""
    from pathlib import PureWindowsPath
    from app.main import _netzpfad

    assert _netzpfad(PureWindowsPath(pfad)) is erwartet


def test_unc_pfad_erreicht_das_dateisystem_nicht(client, projekt, monkeypatch):
    """Windows: Ein Pfad mit zwei Backslashes am Anfang (Freigabe auf einem anderen Rechner) ersetzt
    beim Zusammensetzen die Projektwurzel. Schon `resolve()` spräche diesen Rechner per SMB an, samt
    Anmeldeversuch, bevor die Eingrenzung ablehnt. Der Wächter schlägt an, falls so ein Pfad
    `os.path.realpath` erreicht. Unter macOS und Linux ist das nur ein seltsamer Dateiname; der
    Test läuft dort mit, beweist aber erst im Job backend-windows etwas."""
    import os

    original = os.path.realpath

    def waechter(pfad, *args, **kwargs):
        assert not str(pfad).startswith("\\\\"), f"UNC-Pfad erreichte resolve(): {pfad}"
        return original(pfad, *args, **kwargs)

    monkeypatch.setattr(os.path, "realpath", waechter)
    r = client.get("/api/artifact", params={"path": r"\\bms-test.invalid\freigabe\bericht.html"})
    assert r.status_code == 403


def test_nicht_freigegebener_projektordner_403(client, projekt):
    _anlegen(projekt, "backend/app/main.py")

    assert client.get("/api/artifact", params={"path": "backend/app/main.py"}).status_code == 403


def test_absoluter_pfad_ausserhalb_des_projekts_403(client, projekt, tmp_path):
    ausserhalb = _anlegen(tmp_path, "ausserhalb.pdf")

    assert client.get("/api/artifact", params={"path": str(ausserhalb)}).status_code == 403


def test_traversal_verlaesst_das_projekt_403(client, projekt):
    r = client.get("/api/artifact", params={"path": "../../../../../../../../etc/passwd"})
    assert r.status_code == 403


def test_traversal_ein_level_hoch_dann_data_403(client, projekt, tmp_path):
    """`../data/bewerbung.sqlite` landet im ELTERN-Ordner des Projekts. Die Datei existiert dort."""
    _anlegen(tmp_path, "data/bewerbung.sqlite")

    assert client.get("/api/artifact", params={"path": "../data/bewerbung.sqlite"}).status_code == 403


def test_prozent_kodierte_traversal_403(client, projekt, tmp_path):
    """`%2e%2e` in der rohen Query (fertig in der URL, damit httpx nichts umkodiert)."""
    _anlegen(tmp_path, "data/bewerbung.sqlite")

    assert client.get("/api/artifact?path=%2e%2e%2Fdata%2Fbewerbung.sqlite").status_code == 403


def test_geschwisterordner_mit_gleichem_praefix_kein_string_bypass(client, projekt):
    """P3-1: Ein reiner String-Präfix-Vergleich hielte `data/company_fit_alt/` für einen Teil von
    `data/company_fit/` und `data_<uuid>/` für einen Teil von `data/`. Beide Dateien existieren."""
    _anlegen(projekt, "data/company_fit_alt/bericht.html", _HTML)
    geschwister = f"data_{uuid.uuid4().hex}/bericht.html"
    _anlegen(projekt, geschwister, _HTML)

    assert client.get("/api/artifact", params={"path": "data/company_fit_alt/bericht.html"}).status_code == 403
    assert client.get("/api/artifact", params={"path": geschwister}).status_code == 403


def test_nosniff_header_gesetzt_inline_und_download(client, projekt):
    """P2-14: Der Browser soll eine ausgelieferte Datei nicht abweichend vom Content-Type deuten."""
    pfad = "data/company_fit/2026_09_28_CompanyFit_Firma.html"
    _anlegen(projekt, pfad, _HTML)

    r_inline = client.get("/api/artifact", params={"path": pfad})
    assert r_inline.status_code == 200
    assert r_inline.headers.get("x-content-type-options") == "nosniff"

    r_download = client.get("/api/artifact", params={"path": pfad, "download": "true"})
    assert r_download.status_code == 200
    assert r_download.headers.get("x-content-type-options") == "nosniff"
