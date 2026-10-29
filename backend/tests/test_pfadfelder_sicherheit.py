"""P2-56: Dateipfade, die ein Client setzen kann, und alles, was gespeicherte Pfade verschiebt
oder überschreibt, bleiben in der Positivliste.

Befund (Review zu P2-54, 28.09.2026, vorbestehend): `PATCH /api/interviews/{id}` übernahm
`prep_path` ungeprüft. Das Löschen des Briefings (`DELETE /api/files/virtual/interview/{id}/prep`)
oder der Stelle (`DELETE /api/jobs/{id}`) gab diesen Pfad an `main._in_papierkorb`, und das
verschob jede Datei unter data/ oder outputs/ in den Papierkorb, auch data/bewerbung.sqlite und
die Sicherungen. Im LAN-Modus (start_lan.command, ohne Anmeldung) reichten dafür zwei Aufrufe aus
demselben Netz. `pipeline/cv_export.py` verschob bzw. überschrieb die Datei hinter einem
gespeicherten Entwurfspfad ebenfalls ungeprüft (diese Felder setzen heute nur Skills).

Seit P2-56:
- `PATCH /api/interviews/{id}` nimmt als `prep_path` nur ein Briefing an (data/interview_prep,
  .html) oder leert das Feld; sonst 422, und der PATCH ändert nichts.
- `main._in_papierkorb` verschiebt nur Dateien aus der Positivliste `_ARTEFAKT_ORDNER` (dieselbe
  Prüfung wie /api/artifact) und wirft sonst OSError, bevor es etwas anfasst. Die Lösch-Endpunkte
  zählen das wie jeden Verschiebe-Fehler als `dateien_fehlgeschlagen`.
- `cv_export` verschiebt und überschreibt nur Entwürfe aus den CV- bzw. Anschreiben-Ordnern, eine
  alte PDF wandert nur aus dem Zielordner in den Papierkorb.
- `cleanup._in_papierkorb` verlässt data/ und outputs/ nicht mehr (P3-1, bisher nur in main.py).

Isolation wie test_artifact_security.py: `main._PROJECT_ROOT` (bzw. `cv_export.PROJECT_ROOT`,
`cleanup.PROJECT_ROOT`/`PAPIERKORB`) zeigt auf ein tmp-Verzeichnis, dort liegen echte Dateien.
Die Sperrfälle arbeiten mit EXISTIERENDEN Dateien, sonst bewiese „nicht verschoben“ nur, dass
nichts da war. Angelegt wird per pathlib, angefragt mit Posix-Pfaden wie in der DB; damit prüft
der Windows-Job (backend-windows) dieselben Fälle.

App-Module nur funktionslokal importieren (s. conftest.py).
"""
import json
import os
import uuid

import pytest


# ── Helfer ────────────────────────────────────────────────────────────────────────────────
_HTML = b'<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>ok</body></html>'
_DB_INHALT = b"SQLite format 3\x00 pytest-attrappe"


def _anlegen(wurzel, rel, inhalt=b"x"):
    ziel = wurzel.joinpath(*rel.split("/"))
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(inhalt)
    return ziel


def _papierkorb_inhalt(wurzel):
    korb = wurzel / "data" / "papierkorb"
    return sorted(p.name for p in korb.iterdir()) if korb.is_dir() else []


def _setze(model, pk, **werte):
    """Schreibt Werte direkt in die DB, z. B. einen Altwert aus der Zeit vor P2-56."""
    from sqlmodel import Session
    from app.db import engine

    with Session(engine) as s:
        row = s.get(model, pk)
        for k, v in werte.items():
            setattr(row, k, v)
        s.add(row)
        s.commit()


def _lies(model, pk):
    from sqlmodel import Session
    from app.db import engine

    with Session(engine) as s:
        return s.get(model, pk)


def _stelle(session, prep_path=None):
    """Firma, Stelle und ein Interview. Gibt nur Zahlen zurück (s. test_loeschen_reihenfolge.py,
    WICHTIGER BEFUND 2: nach dem Löschen keine ORM-Objekte mehr anfassen)."""
    from app.models import Company, Interview, Job

    suffix = uuid.uuid4().hex[:8]
    company = Company(name=f"Pfadfeld GmbH {suffix}")
    session.add(company)
    session.commit()
    session.refresh(company)
    company_id = company.id

    job = Job(company_id=company_id, company_name=company.name, title="Head of Delivery",
              status="Interview", found_date="2026-09-28", dedup_key=f"p2-56|{suffix}")
    session.add(job)
    session.commit()
    session.refresh(job)
    job_id = job.id

    iv = Interview(job_id=job_id, company_id=company_id, runde=1, status="Geplant",
                   prep_path=prep_path)
    session.add(iv)
    session.commit()
    session.refresh(iv)
    return {"company_id": company_id, "job_id": job_id, "interview_id": iv.id}


@pytest.fixture()
def projekt(tmp_path, monkeypatch):
    import app.main as main

    wurzel = tmp_path / "projekt"
    wurzel.mkdir()
    monkeypatch.setattr(main, "_PROJECT_ROOT", wurzel)
    # delete_profil_file schreibt danach config/profil_struktur.md über eine beim Import
    # gebundene Konstante (test_loeschen_reihenfolge.py, WICHTIGER BEFUND 3).
    monkeypatch.setattr(main, "_PROFIL_STRUKTUR_PATH", tmp_path / "profil_struktur.md")
    return wurzel


# ═══════════════════════════════════════════════════════════════════════════════════════════
# A — PATCH /api/interviews/{id}: prep_path nur als Briefing
# ═══════════════════════════════════════════════════════════════════════════════════════════
_BRIEFING = "data/interview_prep/2026_09_28_Briefing_Firma_R1.html"


def test_patch_prep_path_auf_die_datenbank_wird_abgewiesen(client, session, projekt):
    """Der erste der beiden Angriffsaufrufe aus dem Befund."""
    from app.models import Interview

    _anlegen(projekt, "data/bewerbung.sqlite", _DB_INHALT)
    ids = _stelle(session, prep_path=_BRIEFING)

    r = client.patch(f"/api/interviews/{ids['interview_id']}",
                     json={"prep_path": "data/bewerbung.sqlite"})

    assert r.status_code == 422
    assert "prep_path" in r.text
    assert _lies(Interview, ids["interview_id"]).prep_path == _BRIEFING


# Jede Datei existiert im Test (Anlage in der Testfunktion). 422 heißt also: die Regel greift.
UNGUELTIGE_BRIEFING_PFADE = [
    "data/bewerbung.sqlite-journal",
    "data/backups/bewerbung_backup_20260908_101500.sqlite",
    "data/backups/auto/bewerbung_2026-09-28_164620.zip",
    "data/updates/2026-09-28_120000_1.0.0_zu_1.1.0/datenbank.sqlite",
    "data/sicherung.json",
    "data/interview_prep/../bewerbung.sqlite",          # Umweg aus dem Briefing-Ordner
    "data/interview_prep/bewerbung.sqlite",             # richtiger Ordner, falscher Typ
    "data/interview_prep/fragenbank.md",                # richtiger Ordner, interne Datei
    "data/company_fit/2026_09_28_CompanyFit_Firma.html",   # Dokument, aber kein Briefing
    "data/cv_basis/base_de.docx",
    "outputs/cv/CV_Name_Firma_Position.docx",
    "data/papierkorb/2026_09_28_Briefing_alt.html",
    "config/profil.md",
    "../ausserhalb.html",
]


@pytest.mark.parametrize("pfad", UNGUELTIGE_BRIEFING_PFADE)
def test_patch_prep_path_ausserhalb_der_briefings_wird_abgewiesen(client, session, projekt, pfad):
    from app.models import Interview

    if not pfad.startswith(".."):
        _anlegen(projekt, pfad)
    ids = _stelle(session, prep_path=_BRIEFING)

    r = client.patch(f"/api/interviews/{ids['interview_id']}", json={"prep_path": pfad})

    assert r.status_code == 422
    assert _lies(Interview, ids["interview_id"]).prep_path == _BRIEFING


@pytest.mark.parametrize("wert", [123, True, ["data/interview_prep/x.html"], {"pfad": "x"}])
def test_patch_prep_path_ohne_text_wird_abgewiesen(client, session, projekt, wert):
    ids = _stelle(session)
    r = client.patch(f"/api/interviews/{ids['interview_id']}", json={"prep_path": wert})
    assert r.status_code == 422


def test_patch_prep_path_absoluter_pfad_zur_datenbank_wird_abgewiesen(client, session, projekt):
    datei = _anlegen(projekt, "data/bewerbung.sqlite", _DB_INHALT)
    ids = _stelle(session)
    r = client.patch(f"/api/interviews/{ids['interview_id']}", json={"prep_path": str(datei)})
    assert r.status_code == 422


def test_patch_prep_path_netzpfad_wird_abgewiesen(client, session, projekt):
    """UNC-Pfad (Windows): abgewiesen, bevor irgendetwas aufgelöst wird (P2-54, `_netzpfad`).
    Unter macOS und Linux ist der Text ein Dateiname im Projektordner und fällt ebenso durch."""
    ids = _stelle(session)
    r = client.patch(f"/api/interviews/{ids['interview_id']}",
                     json={"prep_path": "\\\\server\\freigabe\\Briefing.html"})
    assert r.status_code == 422


def test_patch_ungueltiger_prep_path_aendert_auch_die_anderen_felder_nicht(client, session, projekt):
    from app.models import Interview

    ids = _stelle(session)
    r = client.patch(f"/api/interviews/{ids['interview_id']}",
                     json={"status": "Absolviert", "prep_path": "data/sicherung.json"})

    assert r.status_code == 422
    iv = _lies(Interview, ids["interview_id"])
    assert iv.status == "Geplant"
    assert iv.prep_path is None


def test_patch_prep_path_briefing_wird_gespeichert(client, session, projekt):
    from app.models import Interview

    _anlegen(projekt, _BRIEFING, _HTML)
    ids = _stelle(session)

    r = client.patch(f"/api/interviews/{ids['interview_id']}", json={"prep_path": _BRIEFING})

    assert r.status_code == 200, r.text
    assert r.json()["prep_path"] == _BRIEFING
    assert _lies(Interview, ids["interview_id"]).prep_path == _BRIEFING
    # und die Oberfläche kann es öffnen (dieselbe Positivliste)
    assert client.get("/api/artifact", params={"path": _BRIEFING}).status_code == 200


def test_patch_prep_path_absolut_im_briefing_ordner_wird_gespeichert(client, session, projekt):
    """Wie /api/artifact: ein absoluter Pfad in einem erlaubten Ordner geht durch (Altbestand
    aus `_rel()`, P2-54). Gespeichert wird die kanonische relative Form."""
    from app.models import Interview

    datei = _anlegen(projekt, _BRIEFING, _HTML)
    ids = _stelle(session)
    r = client.patch(f"/api/interviews/{ids['interview_id']}", json={"prep_path": str(datei)})
    assert r.status_code == 200, r.text
    assert _lies(Interview, ids["interview_id"]).prep_path == _BRIEFING


@pytest.mark.parametrize("form", [
    "data//interview_prep/2026_09_28_Briefing_Firma_R1.html",
    "./data/interview_prep/2026_09_28_Briefing_Firma_R1.html",
    "data/interview_prep/./2026_09_28_Briefing_Firma_R1.html",
    "data/interview_prep/../interview_prep/2026_09_28_Briefing_Firma_R1.html",
    "data/interview_prep/2026_09_28_Briefing_Firma_R1.html/",
])
def test_patch_prep_path_wird_kanonisch_gespeichert(client, session, projekt, form):
    """Review-Befund: Solche Formen lösen richtig auf, als Text aber fänden Suchindex
    (`artefakt_pfad`) und Waisen-Abgleich (`cleanup`) das Briefing nicht; `data//…` hätte
    `cleanup apply` das lebende Briefing als Waise in den Papierkorb legen lassen."""
    from app.models import Interview

    _anlegen(projekt, _BRIEFING, _HTML)
    ids = _stelle(session)
    r = client.patch(f"/api/interviews/{ids['interview_id']}", json={"prep_path": form})
    assert r.status_code == 200, r.text
    assert _lies(Interview, ids["interview_id"]).prep_path == _BRIEFING


def test_patch_prep_path_ohne_vorhandenes_briefing_wird_abgewiesen(client, session, projekt):
    """Richtiger Ordner, richtiger Typ, aber keine Datei: 422 wie jeder andere ungültige Wert."""
    from app.models import Interview

    ids = _stelle(session, prep_path=_BRIEFING)
    r = client.patch(f"/api/interviews/{ids['interview_id']}",
                     json={"prep_path": "data/interview_prep/gibt_es_nicht.html"})
    assert r.status_code == 422
    assert _lies(Interview, ids["interview_id"]).prep_path == _BRIEFING


def test_patch_prep_path_ueberlanger_name_wird_abgewiesen(client, session, projekt):
    """Review-Befund: Ein überlanger Name im Briefing-Ordner löste auf und wäre gespeichert
    worden; danach hätte `Path.is_file()` (Suchindex-Neuaufbau, Cleanup-Scan) mit
    „File name too long“ abgebrochen. Jetzt 422, ohne 500."""
    ids = _stelle(session)
    r = client.patch(f"/api/interviews/{ids['interview_id']}",
                     json={"prep_path": "data/interview_prep/" + "x" * 300 + ".html"})
    assert r.status_code == 422


@pytest.mark.parametrize("wert", [None, ""])
def test_patch_prep_path_leeren(client, session, projekt, wert):
    from app.models import Interview

    ids = _stelle(session, prep_path=_BRIEFING)
    r = client.patch(f"/api/interviews/{ids['interview_id']}", json={"prep_path": wert})
    assert r.status_code == 200, r.text
    assert _lies(Interview, ids["interview_id"]).prep_path is None


def test_patch_ohne_prep_path_wie_bisher(client, session, projekt):
    """Die Oberfläche schickt nur status, gegenueber und vor_ort (JobDetail.tsx)."""
    from app.models import Interview

    ids = _stelle(session, prep_path=_BRIEFING)
    r = client.patch(f"/api/interviews/{ids['interview_id']}",
                     json={"status": "Absolviert", "gegenueber": "Recruiter", "vor_ort": True})
    assert r.status_code == 200, r.text
    iv = _lies(Interview, ids["interview_id"])
    assert (iv.status, iv.gegenueber, iv.vor_ort, iv.prep_path) == ("Absolviert", "Recruiter", True, _BRIEFING)


# ═══════════════════════════════════════════════════════════════════════════════════════════
# B — der gemeldete Angriff Ende zu Ende
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_briefing_loeschen_verschiebt_die_datenbank_nicht(client, session, projekt):
    """Aufruf 1 (PATCH) scheitert jetzt. Für einen Altwert aus der Zeit davor greift die zweite
    Linie: `_in_papierkorb` fasst die Datei nicht an, das Löschen des Briefings meldet sie als
    fehlgeschlagen, und das Feld ist trotzdem leer (DB zuerst, Phase 64A)."""
    from app.models import Interview

    db_datei = _anlegen(projekt, "data/bewerbung.sqlite", _DB_INHALT)
    ids = _stelle(session)

    assert client.patch(f"/api/interviews/{ids['interview_id']}",
                        json={"prep_path": "data/bewerbung.sqlite"}).status_code == 422

    _setze(Interview, ids["interview_id"], prep_path="data/bewerbung.sqlite")   # Altwert
    r = client.delete(f"/api/files/virtual/interview/{ids['interview_id']}/prep")

    assert r.status_code == 200
    assert r.json() == {"ok": True, "papierkorb": None, "dateien_fehlgeschlagen": 1}
    assert db_datei.read_bytes() == _DB_INHALT
    assert _papierkorb_inhalt(projekt) == []
    assert _lies(Interview, ids["interview_id"]).prep_path is None


def test_stelle_loeschen_verschiebt_die_datenbank_nicht(client, session, projekt):
    """Derselbe Altwert beim Löschen der ganzen Stelle: Die Stellenausschreibung wandert wie
    bisher in den Papierkorb, die Datenbank bleibt liegen."""
    from app.models import Job

    db_datei = _anlegen(projekt, "data/bewerbung.sqlite", _DB_INHALT)
    snapshot_rel = "data/job_postings/2026_09_28_Stellenausschreibung_Firma.html"
    snapshot = _anlegen(projekt, snapshot_rel, _HTML)
    ids = _stelle(session, prep_path="data/bewerbung.sqlite")
    _setze(Job, ids["job_id"], posting_snapshot_path=snapshot_rel)

    r = client.delete(f"/api/jobs/{ids['job_id']}")

    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["dateien"] == 1
    assert body["dateien_fehlgeschlagen"] == 1
    assert db_datei.read_bytes() == _DB_INHALT
    assert not snapshot.exists()
    assert len(_papierkorb_inhalt(projekt)) == 1


# ═══════════════════════════════════════════════════════════════════════════════════════════
# C — main._in_papierkorb: nur Dateien aus der Positivliste
# ═══════════════════════════════════════════════════════════════════════════════════════════
NICHT_VERSCHIEBEN = [
    # Datenbank samt Begleitdateien, Sicherungen, Updates, Einstellungen
    "data/bewerbung.sqlite",
    "data/bewerbung.sqlite-wal",
    "data/bewerbung.sqlite-shm",
    "data/bewerbung.sqlite-journal",
    "data/backups/bewerbung_backup_20260908_101500.sqlite",
    "data/backups/auto/bewerbung_2026-09-28_164620.zip",
    "data/updates/2026-09-28_120000_1.0.0_zu_1.1.0/datenbank.sqlite",
    "data/sicherung.json",
    # Datenbank-Kopie in einem erlaubten Ordner: der Ordner allein reicht nicht
    "data/company_fit/bewerbung.sqlite",
    "data/tmp/bewerbung.sqlite",
    # Ordner und Dateien, die keine Artefakte sind
    "data/papierkorb/2026_09_28_CV_Firma.pdf",
    "data/agent_logs/task_1.jsonl",
    "data/mail_alerts/2026_09_28_Mail_Alerts.json",
    "data/exports/coach_site/.htpasswd",
    "data/interview_prep/fragenbank.md",
    "data/beirat/2026_09_28_debatte.json",
    "outputs/kundenpaket/BMS_1.0.0.zip",
    "data/probe.html",
    "outputs/probe.pdf",
    # außerhalb von data/ und outputs/
    "config/profil.md",
    "README.md",
]


@pytest.mark.parametrize("pfad", NICHT_VERSCHIEBEN)
def test_in_papierkorb_verschiebt_nichts_ausserhalb_der_positivliste(projekt, pfad):
    import app.main as main

    datei = _anlegen(projekt, pfad)
    vorher = _papierkorb_inhalt(projekt)

    with pytest.raises(OSError):
        main._in_papierkorb(pfad)

    assert datei.is_file()
    assert _papierkorb_inhalt(projekt) == vorher


ARTEFAKTE = [
    "data/company_fit/2026_09_28_CompanyFit_Firma.html",
    "data/job_postings/2026_09_28_Stellenausschreibung_Firma.html",
    "data/interview_prep/2026_09_28_Briefing_Firma_R1.html",
    "data/beirat/2026_09_28_BeiratsCheck_Firma.html",
    "data/analysen/2026_09_28_Analyse_Absagen.html",
    "data/transcripts/2026_09_28_TranskriptReport_Firma.html",
    "data/transcripts/2026_09_28_Transkript_Firma.md",
    "data/job_files/job_7/2026_09_28_Stellenbeschreibung.pdf",
    "data/job_files/job_7/2026_09_28_Transkript_Gespraech.vtt",
    "data/profil/dateien/2026_09_28_Zeugnis.pdf",
    "data/cv_basis/base_de.docx",
    "data/cv_basis/base_de.pdf",
    "data/cv_basis/entwuerfe/CV_Entwurf_Firma.docx",
    "data/tmp/CV_Name_Firma_Entwurf.docx",
    "outputs/cv/CV_Name_Firma_Position.docx",
    "outputs/cv/CV_Name_Firma_Position.pdf",
    "outputs/cv_entwuerfe/CV_Name_Entwurf.docx",
    "outputs/anschreiben/Anschreiben_Name_Firma.docx",
    "outputs/anschreiben/Anschreiben_Name_Firma.pdf",
]


@pytest.mark.parametrize("pfad", ARTEFAKTE)
def test_in_papierkorb_verschiebt_artefakte_wie_bisher(projekt, pfad):
    import app.main as main

    datei = _anlegen(projekt, pfad)
    ergebnis = main._in_papierkorb(pfad)

    assert ergebnis is not None and ergebnis.startswith("data/papierkorb/")
    assert not datei.exists()
    assert (projekt / ergebnis).is_file()


@pytest.mark.parametrize("umweg", [
    "data/company_fit/../bewerbung.sqlite",
    "outputs/../data/bewerbung.sqlite",
    "data/transcripts/../../data/backups/auto/bewerbung_2026-09-28_164620.zip",
])
def test_in_papierkorb_umwege_ueber_punkte(projekt, umweg):
    import app.main as main

    db = _anlegen(projekt, "data/bewerbung.sqlite", _DB_INHALT)
    sicherung = _anlegen(projekt, "data/backups/auto/bewerbung_2026-09-28_164620.zip")

    with pytest.raises(OSError):
        main._in_papierkorb(umweg)

    assert db.is_file() and sicherung.is_file()
    assert _papierkorb_inhalt(projekt) == []


def test_in_papierkorb_absoluter_pfad(projekt):
    """Absolute Pfade (Altbestand aus `_rel()`) zählen wie ihre relative Form."""
    import app.main as main

    db = _anlegen(projekt, "data/bewerbung.sqlite", _DB_INHALT)
    with pytest.raises(OSError):
        main._in_papierkorb(str(db))
    assert db.is_file()

    fit = _anlegen(projekt, "data/company_fit/2026_09_28_CompanyFit_Firma.html", _HTML)
    assert main._in_papierkorb(str(fit)).startswith("data/papierkorb/")
    assert not fit.exists()


def test_in_papierkorb_symlink_auf_die_datenbank(projekt):
    import app.main as main

    db = _anlegen(projekt, "data/bewerbung.sqlite", _DB_INHALT)
    link = projekt / "data" / "company_fit" / "2026_09_28_CompanyFit_Firma.html"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(db, link)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks sind hier nicht erlaubt (Windows ohne Entwicklermodus)")

    with pytest.raises(OSError):
        main._in_papierkorb("data/company_fit/2026_09_28_CompanyFit_Firma.html")

    assert db.read_bytes() == _DB_INHALT
    assert link.is_symlink()


def test_erlaubter_artefakt_teilliste(projekt):
    """`ordner` grenzt ein, und eine leere Teilliste erlaubt nichts (nicht still die ganze
    Positivliste, wie es ein `ordner or _ARTEFAKT_ORDNER` täte)."""
    import app.main as main

    briefing = _anlegen(projekt, _BRIEFING, _HTML)
    _anlegen(projekt, "data/company_fit/2026_09_28_CompanyFit_Firma.html", _HTML)

    assert main._erlaubter_artefakt(_BRIEFING, main._BRIEFING_ORDNER) == briefing.resolve()
    assert main._erlaubter_artefakt("data/company_fit/2026_09_28_CompanyFit_Firma.html",
                                    main._BRIEFING_ORDNER) is None
    assert main._erlaubter_artefakt(_BRIEFING, {}) is None
    assert main._erlaubter_artefakt(_BRIEFING) == briefing.resolve()


def test_in_papierkorb_leere_und_fehlende_pfade(projekt):
    """Unverändert: kein Pfad oder eine fehlende Datei in einem erlaubten Ordner ergibt None.
    Ein gesperrter Pfad wirft auch ohne Datei (Prüfung vor der Existenz, wie /api/artifact)."""
    import app.main as main

    assert main._in_papierkorb(None) is None
    assert main._in_papierkorb("") is None
    assert main._in_papierkorb("data/company_fit/gibt_es_nicht.html") is None
    with pytest.raises(OSError):
        main._in_papierkorb("data/backups/gibt_es_nicht.sqlite")


# ═══════════════════════════════════════════════════════════════════════════════════════════
# D — jeder Lösch-Endpunkt mit einem Altwert auf die Datenbank
# ═══════════════════════════════════════════════════════════════════════════════════════════
# (quelle, slot) aus main._VIRT_SLOTS; der Abgleich unten hält die Liste vollständig.
VIRT_SLOTS = [
    ("job", "posting"), ("company", "fit"),
    ("cv", "docx"), ("cv", "pdf"), ("cv", "match"), ("cv", "ats"),
    ("app", "cover"), ("app", "coverpdf"),
    ("interview", "prep"),
    ("transcript", "debrief"), ("transcript", "report"),
]


def test_virt_slots_liste_ist_vollstaendig():
    import app.main as main

    assert sorted(VIRT_SLOTS) == sorted((q, s) for q, slots in main._VIRT_SLOTS.items() for s in slots)


def _zeile_fuer_slot(session, quelle, slot, pfad):
    """Legt die Zeile an, die `main._VIRT_SLOTS[quelle][slot]` löscht, mit `pfad` im Feld."""
    import app.main as main
    from app.models import Application, CVVersion, Transcript

    ids = _stelle(session)
    model, feld = main._VIRT_SLOTS[quelle][slot]
    if quelle == "job":
        pk = ids["job_id"]
    elif quelle == "company":
        pk = ids["company_id"]
    elif quelle == "interview":
        pk = ids["interview_id"]
    else:
        row = {"cv": lambda: CVVersion(job_id=ids["job_id"], language="DE", kind="tailored"),
               "app": lambda: Application(job_id=ids["job_id"], status="Beworben"),
               "transcript": lambda: Transcript(job_id=ids["job_id"], title="Gespräch")}[quelle]()
        session.add(row)
        session.commit()
        session.refresh(row)
        pk = row.id
    _setze(model, pk, **{feld: pfad})
    return pk


@pytest.mark.parametrize("quelle, slot", VIRT_SLOTS)
def test_artefakt_loeschen_verschiebt_die_datenbank_nicht(client, session, projekt, quelle, slot):
    db = _anlegen(projekt, "data/bewerbung.sqlite", _DB_INHALT)
    pk = _zeile_fuer_slot(session, quelle, slot, "data/bewerbung.sqlite")

    r = client.delete(f"/api/files/virtual/{quelle}/{pk}/{slot}")

    assert r.status_code == 200
    assert r.json()["dateien_fehlgeschlagen"] == 1
    assert db.read_bytes() == _DB_INHALT
    assert _papierkorb_inhalt(projekt) == []


def test_job_datei_loeschen_verschiebt_die_datenbank_nicht(client, session, projekt):
    from app.models import JobFile

    db = _anlegen(projekt, "data/bewerbung.sqlite", _DB_INHALT)
    ids = _stelle(session)
    jf = JobFile(job_id=ids["job_id"], kind="Sonstiges", filename="x.pdf",
                 file_path="data/bewerbung.sqlite")
    session.add(jf)
    session.commit()
    session.refresh(jf)

    r = client.delete(f"/api/files/{jf.id}")

    assert r.status_code == 200
    assert r.json() == {"ok": True, "dateien_fehlgeschlagen": 1}
    assert db.read_bytes() == _DB_INHALT


def test_transkript_loeschen_verschiebt_die_datenbank_nicht(client, session, projekt):
    from app.models import Transcript

    db = _anlegen(projekt, "data/bewerbung.sqlite", _DB_INHALT)
    sicherung = _anlegen(projekt, "data/sicherung.json", b"{}")
    ids = _stelle(session)
    t = Transcript(job_id=ids["job_id"], title="Gespräch", file_path="data/bewerbung.sqlite",
                   report_path="data/sicherung.json")
    session.add(t)
    session.commit()
    session.refresh(t)

    r = client.delete(f"/api/transcripts/{t.id}")

    assert r.status_code == 200
    assert r.json() == {"ok": True, "dateien_fehlgeschlagen": 2}
    assert db.read_bytes() == _DB_INHALT
    assert sicherung.is_file()


def test_firma_loeschen_verschiebt_die_datenbank_nicht(client, session, projekt):
    from app.models import Company

    db = _anlegen(projekt, "data/bewerbung.sqlite", _DB_INHALT)
    company = Company(name=f"Ohne Stellen GmbH {uuid.uuid4().hex[:8]}",
                      fit_analysis_path="data/bewerbung.sqlite")
    session.add(company)
    session.commit()
    session.refresh(company)

    r = client.delete(f"/api/companies/{company.id}")

    assert r.status_code == 200
    assert r.json() == {"ok": True, "dateien_fehlgeschlagen": 1}
    assert db.read_bytes() == _DB_INHALT


def test_profil_datei_loeschen_verschiebt_die_datenbank_nicht(client, session, projekt):
    from app.models import ProfileFile

    db = _anlegen(projekt, "data/bewerbung.sqlite", _DB_INHALT)
    pf = ProfileFile(kind="Zeugnis", filename="z.pdf", file_path="data/bewerbung.sqlite")
    session.add(pf)
    session.commit()
    session.refresh(pf)

    r = client.delete(f"/api/profil/dateien/{pf.id}")

    assert r.status_code == 200
    assert r.json() == {"ok": True, "dateien_fehlgeschlagen": 1}
    assert db.read_bytes() == _DB_INHALT


# ═══════════════════════════════════════════════════════════════════════════════════════════
# E — Wächter: kein weiteres Pfadfeld aus dem Request, keine neue Dateioperation in der HTTP-Schicht
# ═══════════════════════════════════════════════════════════════════════════════════════════
def _pfadfelder():
    """Alle Spalten der Tabellen-Modelle, die einen Dateipfad halten (Namenskonvention *_path)."""
    import app.models as models
    from sqlmodel import SQLModel

    felder = set()
    for obj in vars(models).values():
        if isinstance(obj, type) and issubclass(obj, SQLModel) and hasattr(obj, "__table__"):
            felder |= {name for name in obj.model_fields if name.endswith("_path")}
    return felder


def _routen_module():
    """main.py und alle per include_router eingebundenen Router (app/routes_*.py)."""
    import importlib
    from pathlib import Path

    import app.main as main

    namen = sorted(p.stem for p in Path(main.__file__).parent.glob("routes_*.py"))
    return [main] + [importlib.import_module(f"app.{n}") for n in namen]


def _baum(modul):
    import ast
    from pathlib import Path

    return ast.parse(Path(modul.__file__).read_text(encoding="utf-8"))


def _ist_route(dekorator):
    import ast

    return (isinstance(dekorator, ast.Call) and isinstance(dekorator.func, ast.Attribute)
            and isinstance(dekorator.func.value, ast.Name)
            and dekorator.func.value.id in ("app", "router")
            and dekorator.func.attr in ("get", "post", "put", "patch", "delete"))


def _request_zugriffe(modul, pfadfelder):
    """(Funktion, Zeile, Beschreibung) für jede Stelle, an der ein Handler ein Pfadfeld aus dem
    Request übernehmen könnte:
    - ein Mengen-Literal oder `set(…)`/`frozenset(…)` mit einem Pfadfeld, egal unter welchem
      Namen und auch inline (die Feldmengen heißen hier `editable`, `editierbar`, `erlaubt`,
      `fields`, `_…_EDITABLE`, `_EDITIERBARE_FELDER`);
    - `x["…_path"]` und `x.get("…_path")`;
    - eine Zuweisung `obj.…_path = <Wert>`, außer `= None` (Löschen nullt Felder);
    - ein Parameter einer Route (`@app.…`/`@router.…`) mit dem Namen eines Pfadfelds (Query-,
      Formular- oder Pfadparameter).
    Nicht erkannt: zusammengesetzte oder berechnete Schlüssel (`"cover_letter" + "_path"`),
    `setattr` mit variablem Feldnamen, `**payload` in einen Modell-Konstruktor. Das sind keine
    Muster dieses Projekts; wer sie einführt, muss die Prüfung selbst mitbringen."""
    import ast

    funde = []

    def texte(knoten):
        return {k.value for k in ast.walk(knoten) if isinstance(k, ast.Constant) and isinstance(k.value, str)}

    def besuche(knoten, funktion):
        for kind in ast.iter_child_nodes(knoten):
            if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if any(_ist_route(d) for d in kind.decorator_list):
                    for arg in kind.args.args + kind.args.kwonlyargs:
                        if arg.arg in pfadfelder:
                            funde.append((kind.name, kind.lineno, f"Parameter {arg.arg}"))
                besuche(kind, kind.name)
                continue
            if isinstance(kind, ast.Set) or (
                    isinstance(kind, ast.Call) and isinstance(kind.func, ast.Name)
                    and kind.func.id in ("set", "frozenset") and kind.args):
                for feld in sorted(texte(kind) & pfadfelder):
                    funde.append((funktion, kind.lineno, f"Menge enthält {feld}"))
            if isinstance(kind, ast.Subscript) and isinstance(kind.slice, ast.Constant) \
                    and kind.slice.value in pfadfelder:
                funde.append((funktion, kind.lineno, f"[{kind.slice.value!r}]"))
            if (isinstance(kind, ast.Call) and isinstance(kind.func, ast.Attribute)
                    and kind.func.attr == "get" and kind.args
                    and isinstance(kind.args[0], ast.Constant) and kind.args[0].value in pfadfelder):
                funde.append((funktion, kind.lineno, f".get({kind.args[0].value!r})"))
            if isinstance(kind, ast.Assign) and not (isinstance(kind.value, ast.Constant)
                                                     and kind.value.value is None):
                for ziel in kind.targets:
                    if isinstance(ziel, ast.Attribute) and ziel.attr in pfadfelder:
                        funde.append((funktion, kind.lineno, f".{ziel.attr} = …"))
            besuche(kind, funktion)

    besuche(_baum(modul), "<modul>")
    return funde


def test_kein_endpunkt_uebernimmt_ein_pfadfeld_ungeprueft():
    """Wächter für die Quelle (P2-56): Alle Leser gespeicherter Pfade (Suchindex, Beirat,
    Anschreiben-Text, Coach-Export, Papierkorb, cv_export) vertrauen darauf, dass nur Server und
    Skills Pfade schreiben. Der einzige Pfad, den ein Client setzen darf, ist `prep_path` in
    `update_interview`, und dort nur hinter `_briefing_pfad`. Übernimmt ein Handler in main.py
    oder einem Router ein weiteres Pfadfeld, schlägt dieser Test an: dann den Wert gegen die
    Positivliste prüfen (`_erlaubter_artefakt` mit dem passenden Ordner, Muster
    `_briefing_pfad`) und die Stelle hier eintragen. Was erkannt wird und was nicht, steht bei
    `_request_zugriffe`."""
    pfadfelder = _pfadfelder()
    assert {"prep_path", "file_path", "report_path", "posting_snapshot_path"} <= pfadfelder

    from collections import Counter

    funde = []
    for modul in _routen_module():
        funde += [(modul.__name__, *f) for f in _request_zugriffe(modul, pfadfelder)]

    # Zahlgenau, nicht je Funktion: Eine zweite, ungeprüfte Zuweisung in update_interview (etwa
    # ein setattr mit payload["prep_path"] nach der Schleife) fiele sonst nicht auf.
    bekannt = Counter({
        ("app.main", "update_interview", "['prep_path']"): 2,        # Ziel und Argument der Prüfung
        ("app.main", "update_interview", "Menge enthält prep_path"): 1,
    })
    gefunden = Counter((modul, funktion, beschreibung) for modul, funktion, _, beschreibung in funde)
    assert gefunden == bekannt, f"Pfadfeld aus dem Request ohne Prüfung: {sorted(funde)}"


def test_update_interview_prueft_prep_path_vor_dem_speichern():
    """Gegenstück zum Wächter: In `update_interview` ersetzt `_briefing_pfad` den gesendeten
    Wert (`payload["prep_path"] = _briefing_pfad(payload["prep_path"])`), BEVOR die
    setattr-Schleife läuft. Ein Aufruf irgendwo in der Funktion reicht nicht; er muss den Wert
    absichern, der gespeichert wird."""
    import ast
    import inspect

    import app.main as main

    baum = ast.parse(inspect.getsource(main.update_interview))

    def ist_prep(k):
        return (isinstance(k, ast.Subscript) and isinstance(k.slice, ast.Constant)
                and k.slice.value == "prep_path")

    pruefungen = [k.lineno for k in ast.walk(baum)
                  if isinstance(k, ast.Assign) and len(k.targets) == 1 and ist_prep(k.targets[0])
                  and isinstance(k.value, ast.Call) and isinstance(k.value.func, ast.Name)
                  and k.value.func.id == "_briefing_pfad" and k.value.args and ist_prep(k.value.args[0])]
    schleifen = [k.lineno for k in ast.walk(baum) if isinstance(k, ast.For)
                 and any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                         and c.func.id == "setattr" for c in ast.walk(k))]
    assert len(pruefungen) == 1, "prep_path wird nicht (genau einmal) über _briefing_pfad ersetzt"
    assert schleifen and pruefungen[0] < min(schleifen), "Prüfung steht nicht vor der setattr-Schleife"


def _dateioperationen(modul):
    """(Funktion, Aufruf) für jede Stelle, die eine Datei schreibt, verschiebt, kopiert, verlinkt
    oder löscht: `shutil.*`/`os.*`-Aufrufe dieser Art, die Path-Methoden `write_text`,
    `write_bytes`, `unlink`, `rename`, `rmdir`, `hardlink_to`, `symlink_to` und `replace` mit
    genau einem Argument (`str.replace` hat zwei, `datetime.replace` nur Schlüsselwörter),
    `open(…)` mit einem anderen Modus als Lesen, und Import-Aliase für shutil/os, über die ein
    Aufruf unerkannt bliebe. Nicht erkannt: Dateioperationen in anderen Modulen, die ein Handler
    aufruft (pipeline/…), und Umwege über getattr/eval."""
    import ast

    qualifiziert = {"shutil.move", "shutil.copy", "shutil.copy2", "shutil.copyfile",
                    "shutil.copytree", "shutil.copyfileobj", "shutil.rmtree", "os.replace",
                    "os.rename", "os.renames", "os.remove", "os.unlink", "os.rmdir",
                    "os.removedirs", "os.truncate", "os.link", "os.symlink"}
    methoden = {"write_text", "write_bytes", "unlink", "rename", "rmdir", "hardlink_to", "symlink_to"}
    funde = set()

    def besuche(knoten, funktion):
        for kind in ast.iter_child_nodes(knoten):
            if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef)):
                besuche(kind, kind.name)
                continue
            if isinstance(kind, ast.ImportFrom) and kind.module in ("shutil", "os"):
                funde.add((funktion, f"from {kind.module} import"))
            if isinstance(kind, ast.Import):
                for name in kind.names:
                    if name.name in ("shutil", "os") and name.asname:
                        funde.add((funktion, f"import {name.name} as {name.asname}"))
            if isinstance(kind, ast.Call):
                f = kind.func
                if isinstance(f, ast.Attribute):
                    if isinstance(f.value, ast.Name) and f"{f.value.id}.{f.attr}" in qualifiziert:
                        funde.add((funktion, f"{f.value.id}.{f.attr}"))
                    elif f.attr in methoden:
                        funde.add((funktion, f".{f.attr}"))
                    elif f.attr == "replace" and len(kind.args) == 1 and not kind.keywords:
                        funde.add((funktion, ".replace"))
                elif isinstance(f, ast.Name) and f.id == "open":
                    modus = kind.args[1] if len(kind.args) > 1 else next(
                        (k.value for k in kind.keywords if k.arg == "mode"), None)
                    if modus is not None and not (isinstance(modus, ast.Constant)
                                                  and modus.value in ("r", "rb", "rt")):
                        funde.add((funktion, "open (schreibend)"))
            besuche(kind, funktion)

    besuche(_baum(modul), "<modul>")
    return funde


def test_http_schicht_schreibt_verschiebt_und_loescht_nur_an_bekannten_stellen():
    """Wächter für die Senke (P2-56): Jede Stelle in main.py und den Routern, die eine Datei
    anfasst, steht hier mit ihrem Grund. Gespeicherte Pfade verschiebt nur `_in_papierkorb`
    (Positivliste); alle anderen schreiben in Pfade, die der Server selbst baut. Kommt eine neue
    Stelle dazu, schlägt dieser Test an: dann klären, woher der Pfad kommt, einen Pfad aus DB
    oder Request gegen die Positivliste prüfen (`_erlaubter_artefakt`) und die Stelle eintragen.
    Was erkannt wird und was nicht, steht bei `_dateioperationen`."""
    erwartet = {
        "app.main": {
            ("_in_papierkorb", "shutil.move"),                   # Positivliste
            ("upload_cv_basis", ".write_bytes"),                 # data/cv_basis/base_<xx>.docx.neu
            ("upload_cv_basis", "os.replace"),
            ("upload_cv_basis", ".unlink"),
            ("upload_job_file", ".write_bytes"),                 # data/job_files/job_<id>/<bereinigt>
            ("upload_profil_file", ".write_bytes"),              # data/profil/dateien/<bereinigt>
            ("_speichere_transkript_und_report", ".write_text"),  # data/transcripts/<Konvention>.md
            ("_profil_struktur_schreiben", ".write_text"),       # config/profil_struktur.md
        },
    }
    for modul in _routen_module():
        assert _dateioperationen(modul) == erwartet.get(modul.__name__, set()), modul.__name__


# ═══════════════════════════════════════════════════════════════════════════════════════════
# F — cv_export: nur Entwürfe aus den CV- und Anschreiben-Ordnern
# ═══════════════════════════════════════════════════════════════════════════════════════════
def _fake_to_pdf(docx_path, pdf_path):
    from pathlib import Path

    Path(pdf_path).parent.mkdir(parents=True, exist_ok=True)
    Path(pdf_path).write_bytes(b"%PDF-1.4 dummy\n")
    return True, None


def _docx(wurzel, rel, text="Berufserfahrung"):
    from docx import Document

    ziel = wurzel.joinpath(*rel.split("/"))
    ziel.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    doc.add_paragraph(text)
    doc.save(str(ziel))
    return ziel


@pytest.fixture()
def cv_projekt(tmp_path, monkeypatch):
    """cv_export und cleanup auf dasselbe tmp-Projekt (cleanup bindet PAPIERKORB beim Import,
    s. test_cv_export.py). to_pdf ohne LibreOffice."""
    from pipeline import cleanup, cv_export

    wurzel = tmp_path / "projekt"
    wurzel.mkdir()
    monkeypatch.setattr(cv_export, "PROJECT_ROOT", wurzel)
    monkeypatch.setattr(cleanup, "PROJECT_ROOT", wurzel)
    monkeypatch.setattr(cleanup, "PAPIERKORB", wurzel / "data" / "papierkorb")
    monkeypatch.setattr(cv_export, "to_pdf", _fake_to_pdf)
    return wurzel


def _stelle_mit_cv(session, **felder):
    from app.models import CVVersion

    ids = _stelle(session)
    cv = CVVersion(job_id=ids["job_id"], language="DE", kind="tailored", status="entwurf", **felder)
    session.add(cv)
    session.commit()
    session.refresh(cv)
    return cv.id


def _stelle_mit_anschreiben(session, **felder):
    from app.models import Application

    ids = _stelle(session)
    app_row = Application(job_id=ids["job_id"], status="Beworben", cover_letter_language="DE",
                          **felder)
    session.add(app_row)
    session.commit()
    session.refresh(app_row)
    return app_row.id


FREMDE_QUELLEN = [
    "data/bewerbung.sqlite",
    "data/sicherung.json",
    "data/cv_basis/base_de.docx",                 # Basis-CV: kein Entwurf
    "data/job_files/job_7/Lebenslauf_alt.docx",   # Datei an einer Stelle
    "outputs/anschreiben/Anschreiben_Name_Firma.docx",
    "config/vorlage.docx",
]


@pytest.mark.parametrize("quelle", FREMDE_QUELLEN)
def test_export_nimmt_keine_quelle_ausserhalb_der_cv_ordner(session, cv_projekt, quelle):
    from pipeline import cv_export

    datei = _anlegen(cv_projekt, quelle, b"nicht anfassen")
    cv_id = _stelle_mit_cv(session, file_path=quelle)

    with pytest.raises(SystemExit):
        cv_export.export(cv_id)

    assert datei.read_bytes() == b"nicht anfassen"
    assert not (cv_projekt / "outputs" / "cv").exists()


@pytest.mark.parametrize("entwurf", [
    "data/cv_basis/entwuerfe/CV_Entwurf_Firma.docx",
    "data/tmp/CV_Entwurf_Firma.docx",
    "outputs/cv_entwuerfe/CV_Entwurf_Firma.docx",
])
def test_export_nimmt_entwuerfe_aus_den_cv_ordnern(session, cv_projekt, entwurf):
    from pipeline import cv_export

    quelle = _docx(cv_projekt, entwurf)
    cv_id = _stelle_mit_cv(session, file_path=entwurf)

    ergebnis = cv_export.export(cv_id)

    assert ergebnis["docx"].startswith("outputs/cv/")
    assert not quelle.exists()
    assert (cv_projekt / ergebnis["docx"]).is_file()
    assert ergebnis["pdf"] and (cv_projekt / ergebnis["pdf"]).is_file()


def test_entwurf_anwenden_ueberschreibt_keinen_basis_cv(session, cv_projekt):
    """`entwurf_anwenden` schreibt den Entwurfstext in die Datei hinter `file_path`. Zeigte der
    auf den Basis-CV, wäre die Vorlage aller Skills überschrieben."""
    from pipeline import cv_export

    basis = _docx(cv_projekt, "data/cv_basis/base_de.docx", "Original-Basis")
    vorher = basis.read_bytes()
    cv_id = _stelle_mit_cv(session, file_path="data/cv_basis/base_de.docx",
                           entwurf_text=json.dumps([{"text": "überschrieben"}]))

    with pytest.raises(SystemExit):
        cv_export.entwurf_anwenden(cv_id)

    assert basis.read_bytes() == vorher


@pytest.mark.parametrize("quelle", [
    "data/bewerbung.sqlite",
    "data/cv_basis/base_de.docx",
    "outputs/cv/CV_Name_Firma_Position.docx",
])
def test_export_cover_letter_nimmt_keine_fremde_quelle(session, cv_projekt, quelle):
    from pipeline import cv_export

    datei = _anlegen(cv_projekt, quelle, b"nicht anfassen")
    app_id = _stelle_mit_anschreiben(session, cover_letter_path=quelle)

    with pytest.raises(SystemExit):
        cv_export.export_cover_letter(app_id)

    assert datei.read_bytes() == b"nicht anfassen"


# Die alte PDF geht nur in den Papierkorb, wenn keine ANDERE Zeile sie noch nennt
# (`_noch_referenziert`, über die ganze Test-DB). Deshalb trägt jeder Pfad hier eine eigene
# Kennung: Ein Pfad, den ein anderer Test in die gemeinsame DB geschrieben hat, würde die Datei
# sonst schützen und den Test grundlos grün machen (so geschehen beim ersten Lauf gegen den alten
# Code, s. tasks/spec_p2-56_pfadfelder_absichern.md).
@pytest.mark.parametrize("fremde_pdf", [
    "data/job_files/job_7/Stellenbeschreibung_{k}.pdf",   # Dokument einer Stelle
    "data/cv_basis/base_{k}.pdf",
    "data/sicherung_{k}.json",
])
def test_export_legt_keine_fremde_alte_pdf_in_den_papierkorb(session, cv_projekt, fremde_pdf):
    """P2-10 räumt die alte PDF weg, wenn sich der Zielname ändert. Zeigt `pdf_path` (Altwert)
    auf eine Datei außerhalb von outputs/cv, bleibt sie liegen."""
    from pipeline import cv_export

    k = uuid.uuid4().hex[:8]
    fremde_pdf = fremde_pdf.format(k=k)
    entwurf = f"data/cv_basis/entwuerfe/CV_Entwurf_{k}.docx"
    fremd = _anlegen(cv_projekt, fremde_pdf, b"%PDF fremd")
    _docx(cv_projekt, entwurf)
    cv_id = _stelle_mit_cv(session, file_path=entwurf, pdf_path=fremde_pdf)

    ergebnis = cv_export.export(cv_id)

    assert ergebnis["pdf"].startswith("outputs/cv/")
    assert fremd.read_bytes() == b"%PDF fremd"
    assert _papierkorb_inhalt(cv_projekt) == []


def test_export_cover_letter_legt_keine_fremde_alte_pdf_in_den_papierkorb(session, cv_projekt):
    from pipeline import cv_export

    k = uuid.uuid4().hex[:8]
    fremde_pdf = f"data/job_files/job_7/Stellenbeschreibung_{k}.pdf"
    fremd = _anlegen(cv_projekt, fremde_pdf, b"%PDF fremd")
    _docx(cv_projekt, f"outputs/anschreiben/_raw_{k}.docx", "Sehr geehrte Damen und Herren")
    app_id = _stelle_mit_anschreiben(session, cover_letter_path=f"outputs/anschreiben/_raw_{k}.docx",
                                     cover_letter_pdf_path=fremde_pdf)

    ergebnis = cv_export.export_cover_letter(app_id)

    assert ergebnis["pdf"].startswith("outputs/anschreiben/")
    assert fremd.read_bytes() == b"%PDF fremd"
    assert _papierkorb_inhalt(cv_projekt) == []


def test_export_legt_die_eigene_alte_pdf_weiter_in_den_papierkorb(session, cv_projekt):
    """Gegenprobe zu P2-10: Die alte PDF aus outputs/cv wandert weiter in den Papierkorb."""
    from pipeline import cv_export

    k = uuid.uuid4().hex[:8]
    alt = _anlegen(cv_projekt, f"outputs/cv/CV_Alter_Name_{k}.pdf", b"%PDF alt")
    _docx(cv_projekt, f"data/cv_basis/entwuerfe/CV_Entwurf_{k}.docx")
    cv_id = _stelle_mit_cv(session, file_path=f"data/cv_basis/entwuerfe/CV_Entwurf_{k}.docx",
                           pdf_path=f"outputs/cv/CV_Alter_Name_{k}.pdf")

    cv_export.export(cv_id)

    assert not alt.exists()
    assert len(_papierkorb_inhalt(cv_projekt)) == 1


def test_cv_quellordner_liegen_in_der_positivliste():
    """Was cv_export als Quelle annimmt, muss die Oberfläche auch öffnen können
    (`main._ARTEFAKT_ORDNER`), sonst entstünde ein Entwurf, den niemand ansehen kann."""
    import app.main as main
    from pipeline import cv_export

    for ordner in cv_export._CV_QUELLEN + cv_export._ANSCHREIBEN_QUELLEN:
        passend = [o for o, endungen in main._ARTEFAKT_ORDNER.items()
                   if (ordner == o or ordner.startswith(o + "/")) and ".docx" in endungen]
        assert passend, f"{ordner} fehlt in main._ARTEFAKT_ORDNER"


# ═══════════════════════════════════════════════════════════════════════════════════════════
# G — cleanup._in_papierkorb: bleibt in data/ und outputs/
# ═══════════════════════════════════════════════════════════════════════════════════════════
@pytest.fixture()
def cleanup_projekt(tmp_path, monkeypatch):
    from pipeline import cleanup

    wurzel = tmp_path / "projekt"
    wurzel.mkdir()
    monkeypatch.setattr(cleanup, "PROJECT_ROOT", wurzel)
    monkeypatch.setattr(cleanup, "PAPIERKORB", wurzel / "data" / "papierkorb")
    return wurzel


@pytest.mark.parametrize("pfad", ["config/geheim.txt", "data/../config/geheim.txt", "README.md"])
def test_cleanup_in_papierkorb_verlaesst_data_und_outputs_nicht(cleanup_projekt, pfad):
    from pipeline import cleanup

    geheim = _anlegen(cleanup_projekt, "config/geheim.txt")
    readme = _anlegen(cleanup_projekt, "README.md")

    with pytest.raises(OSError):
        cleanup._in_papierkorb(pfad)

    assert geheim.is_file() and readme.is_file()
    assert _papierkorb_inhalt(cleanup_projekt) == []


@pytest.mark.parametrize("pfad", [
    "data/backups/bewerbung_backup_20260101_000000.sqlite",   # Rotation alter Sicherungen
    "data/mail_alerts/2026_07_01_Mail_Alerts.json",            # Rotation Rohdaten
    "data/company_fit/2026_07_01_CompanyFit_Waise.html",       # Waise
    "outputs/cv/CV_Alter_Name.pdf",                            # alte PDF aus cv_export
])
def test_cleanup_in_papierkorb_rotation_und_waisen_wie_bisher(cleanup_projekt, pfad):
    from pipeline import cleanup

    datei = _anlegen(cleanup_projekt, pfad)
    ergebnis = cleanup._in_papierkorb(pfad)

    assert ergebnis.startswith("data/papierkorb/")
    assert not datei.exists()
