"""Tests für Phase 64A (P1-7 aus dem Code-Review, s. tasks/spec_phase64_fehlerpfade.md, Stufe
64A + die vom Orchestrator freigegebene Scope-Erweiterung „Stufe 2"): Löschen committet die
DB-Änderung ZUERST, Dateien wandern ERST DANACH in den Papierkorb — und ein einzelner
Move-Fehlschlag darf weder die übrigen Dateien noch den bereits erfolgten DB-Commit rückgängig
machen. Stufe 2 zieht dasselbe Muster für die drei zunächst bewusst ausgesparten Endpunkte nach
(`delete_transcript`, `delete_company`, `delete_profil_file` — Fälle 8-13 unten).

Phase 68B (P3-1, P3-6 aus dem Code-Review 2026-07-25) ergänzt Fall 14 (`_in_papierkorb`s neue
Wurzel-Prüfung) und Fall 15 (`delete_company` nullt `company_id` an Tombstone-Jobs) — s. dort.

P2-56 (28.09.2026): `_in_papierkorb` verschiebt nur noch Dateien aus der Positivliste
`_ARTEFAKT_ORDNER` (Tests dazu in test_pfadfelder_sicherheit.py). Drei Fälle hier nutzten
Ablageorte, die die App nie beschreibt: Anschreiben-PDFs in `data/cover/` (Fälle 1+2, echt:
`outputs/anschreiben/`), ein `.vtt` in `data/transcripts/` (Fälle 8+9, echt: hochgeladen am Job
unter `data/job_files/job_<id>/`, getippt als `.md` in `data/transcripts/`) und `data/cv/`
(Fall 14b, gibt es nicht; Lebensläufe liegen in `outputs/cv/`). Sie liegen jetzt am echten Ort; die Prüfungen selbst
sind unverändert.

15 Fälle:
  1. Normalfall `delete_job` — Dateien werden verschoben UND die DB wird aktualisiert (F3-Beweis:
     das Erfolgsverhalten bleibt exakt wie vorher, nur die interne Reihenfolge hat sich gedreht).
  2. Fehlerfall `delete_job` (drei Dateien) — `shutil.move` wirft per Monkeypatch für GENAU eine
     Datei → die DB-Änderung ist TROTZDEM committet (kein Rollback, keine tote Referenz — die
     referenzierenden Rows werden ohnehin hart gelöscht), der Fehlschlag wird gezählt/gemeldet,
     UND die übrigen zwei Dateien werden trotzdem verschoben (Beweis: ein Einzel-Fehlschlag
     bricht die Schleife nicht ab). Die kaputte Datei wird zur VERWAISTEN DATEI (bleibt an ihrem
     Original-Ort liegen), nicht zur toten DB-Referenz.
  3.+4. Normal-/Fehlerfall `delete_job_file` — dieselbe Reihenfolge-Umkehr an einem zweiten
     Endpunkt, inkl. Beweis "kein 500 trotz Move-Fehler".
  5.+6. Normal-/Fehlerfall `delete_virtual_file` — F3-Beweis für das bestehende `papierkorb`-Feld
     (bleibt im Erfolgsfall gefüllt, wird im Fehlerfall None statt eines 500ers) plus das neue
     `dateien_fehlgeschlagen`-Feld.
  7. Alarmschwelle `pipeline.cleanup.scan` — genügend synthetische tote Referenzen (Pfadfeld
     zeigt auf eine nie existierende Datei) heben `ergebnis["auffaellig"]` auf True.
  8.+9. Normal-/Fehlerfall `delete_transcript` — drei Pfade (file_path/debrief_path/report_path)
     plus die gekoppelte JobFile-Row (dieselbe physische Datei, s. upload_job_file) werden beim
     Reordering korrekt mitbehandelt.
  10.+11. Normal-/Fehlerfall `delete_company` — HARTES Löschen (kein Soft-Delete wie bei Job);
     Beweis, dass die Reihenfolge-Umkehr trotzdem greift (Row ist nach Commit komplett weg, ein
     späterer Move-Fehlschlag kann keine tote Referenz mehr erzeugen) UND dass Contacts/E-Mail-
     Entkopplung unverändert funktionieren.
  12.+13. Normal-/Fehlerfall `delete_profil_file` — s. WICHTIGER BEFUND 3 unten (`_profil_struk
     tur_schreiben` schreibt in einen zur Import-Zeit eingefrorenen Pfad, NICHT über `_PROJECT_
     ROOT` zur Laufzeit).

WICHTIGER BEFUND 1 (empirisch, wie schon in test_artifact_security.py/test_log_pfade.py für
verwandte Fälle dokumentiert): `app.main._PROJECT_ROOT` wird beim Modul-Import HART gebunden
(`Path(__file__).resolve().parent.parent.parent`) und reagiert NICHT auf `BMS_DATA_DIR`. Die
Lösch-Endpunkte (über `_in_papierkorb`) würden also ohne Gegenmaßnahme in den ECHTEN
`data/papierkorb/`-Ordner schreiben. Die Tests 1-6 unten binden `app.main._PROJECT_ROOT` deshalb
per `monkeypatch.setattr` auf ein pytest-`tmp_path`-Verzeichnis um — exakt das in
`test_log_pfade.py` für `agent_runner.LOG_DIR` bewährte Muster. `_in_papierkorb` liest
`_PROJECT_ROOT` bei JEDEM Aufruf frisch aus dem Modul-Namespace (kein zur Import-Zeit
eingefrorener Wert wie bis P2-54 `_ALLOWED_ROOTS` im Artifact-Endpoint) — die
Umbindung wirkt daher zuverlässig, ganz ohne echte Dateien im echten Projekt anzufassen.

WICHTIGER BEFUND 2 (beim Schreiben dieser Tests aufgefallen): Die `session`-Fixture committet
mehrfach (Company → Job → Application → JobFile). SQLAlchemy expired bei JEDEM `commit()` ALLE
bereits geladenen Objekte der Session (Default `expire_on_commit=True`), nicht nur die gerade
committeten. Greift ein Test NACH dem `client.delete(...)`-Aufruf noch auf `.id` eines dieser
älteren Objekte zu, während dessen zugehörige Row inzwischen von der (anderen) Endpunkt-Session
hart gelöscht wurde, löst SQLAlchemy beim impliziten Refresh `ObjectDeletedError` aus, statt
einfach den zwischengespeicherten Wert zu liefern — auch wenn nur die numerische ID gebraucht
wird. Deshalb werden IDs unten IMMER direkt nach `session.refresh(...)` in eine einfache
Python-`int`-Variable kopiert und NIE wieder über das ORM-Objekt gelesen.

WICHTIGER BEFUND 3 (Stufe 2, beim Prüfen von `delete_profil_file` auf Besonderheiten gefunden —
genau die vom Orchestrator angemahnte Einzelfallprüfung): Der Endpunkt ruft nach dem Commit
`_profil_struktur_schreiben(session)`, und die schreibt in `main._PROFIL_STRUKTUR_PATH`. Diese
Konstante wird — anders als `_in_papierkorb`s Nachschlagen von `_PROJECT_ROOT` — beim Modul-
Import EINMALIG aus `_PROJECT_ROOT` gebildet (`_PROFIL_STRUKTUR_PATH = _PROJECT_ROOT / "config"
/ "profil_struktur.md"`, main.py Zeile ~2496) und danach NIE wieder neu berechnet — exakt das
Muster, das bis P2-54 auch `_ALLOWED_ROOTS` im Artifact-Endpoint hatte. Ein alleiniges
`monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)` hätte diesen Schreibzugriff NICHT
umgeleitet — der Test hätte die echte `config/profil_struktur.md` mit dem Inhalt der leeren
tmp-Test-DB überschrieben (klarer T1/F1-Verstoß). Die `delete_profil_file`-Tests unten setzen
deshalb ZUSÄTZLICH `monkeypatch.setattr(main, "_PROFIL_STRUKTUR_PATH", tmp_path / …)` und prüfen
zur Sicherheit per `os.path.getmtime` VOR/NACH, dass die echte Datei unangetastet bleibt — auch
falls die Umleitung aus irgendeinem Grund nicht greifen sollte, schlägt der Test dann laut fehl,
statt still die echte Datei zu überschreiben.

Test 7 verzichtet bewusst auf echte Dateien: tote Referenzen sind frei erfundene, garantiert nie
existierende Pfad-Strings (T3). `pipeline.cleanup.scan(html=False)` scannt Orphans/Rotation zwar
weiterhin gegen die echten Projekt-Ordner (rein lesend, `html=False` unterdrückt den einzigen
Schreibzugriff — den HTML-Report), das ist für die hier geprüfte Eigenschaft aber unschädlich:
die Prüfung ist eine EINSEITIGE Implikation (genug tote Referenzen ⇒ auffaellig=True; die
Schwelle wird per Vorher/Nachher-Delta sicher überschritten), die unabhängig vom sonstigen
Orphan-/Rotations-Zustand des echten Projekts gilt (Oder-Verknüpfung in der Alarmschwelle).

App-Importe ausschließlich innerhalb der Testfunktionen (Konvention aus conftest.py).
"""
import uuid


def _neue_datei(ordner, name, inhalt="phase64a pytest probe — sicher loeschbar\n"):
    """Legt eine echte Wegwerf-Datei unter `ordner` (ein tmp_path-Unterpfad, s. Moduldocstring)
    an und gibt den Path zurück."""
    ordner.mkdir(parents=True, exist_ok=True)
    pfad = ordner / name
    pfad.write_text(inhalt, encoding="utf-8")
    return pfad


# ── Fall 1: Normalfall delete_job — F3-Beweis ───────────────────────────────────────────────
def test_delete_job_normalfall_verschiebt_dateien_und_committed_db(client, session, tmp_path, monkeypatch):
    import app.main as main
    from app.db import engine
    from app.models import Application, Company, Job, JobFile
    from sqlmodel import Session as _Session

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)

    suffix = uuid.uuid4().hex[:8]
    company = Company(name=f"Normalfall GmbH {suffix}")
    session.add(company)
    session.commit()
    session.refresh(company)
    company_id = company.id

    job = Job(company_id=company_id, company_name=company.name, title="Test Rolle Normalfall",
              status="Beworben", found_date="2026-07-01", dedup_key=f"p64a-normal|{suffix}")
    session.add(job)
    session.commit()
    session.refresh(job)
    job_id = job.id

    cover_pfad = _neue_datei(tmp_path / "outputs" / "anschreiben", f"cover_{suffix}.pdf")
    application = Application(job_id=job_id, status="Beworben", applied_date="2026-07-01",
                              channel="E-Mail",
                              cover_letter_pdf_path=f"outputs/anschreiben/cover_{suffix}.pdf")
    session.add(application)
    session.commit()
    session.refresh(application)
    application_id = application.id

    jf_pfad = _neue_datei(tmp_path / "data" / "job_files" / f"job_{job_id}", f"anhang_{suffix}.pdf")
    jobfile = JobFile(job_id=job_id, kind="Sonstiges", filename=f"anhang_{suffix}.pdf",
                      file_path=f"data/job_files/job_{job_id}/anhang_{suffix}.pdf")
    session.add(jobfile)
    session.commit()
    session.refresh(jobfile)
    jobfile_id = jobfile.id

    assert cover_pfad.is_file() and jf_pfad.is_file()

    r = client.delete(f"/api/jobs/{job_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["counts"]["dateien"] == 2          # F3: bestehendes Feld, unverändertes Verhalten
    assert body["counts"]["jobfiles"] == 1
    assert body["dateien_fehlgeschlagen"] == 0      # neues Feld, rein additiv

    # Dateien physisch verschoben, Original weg:
    assert not cover_pfad.is_file()
    assert not jf_pfad.is_file()
    papierkorb_dateien = sorted((tmp_path / "data" / "papierkorb").iterdir())
    assert len(papierkorb_dateien) == 2
    namen = {p.name for p in papierkorb_dateien}
    assert any(f"cover_{suffix}" in n for n in namen)
    assert any(f"anhang_{suffix}" in n for n in namen)

    # DB aktualisiert — frische, unabhängige Session (die Identity-Map der Fixture-`session`
    # ist nach mehreren commits expired, s. Moduldocstring „Wichtiger Befund 2").
    with _Session(engine) as verify:
        db_job = verify.get(Job, job_id)
        assert db_job is not None and db_job.deleted_at is not None    # Soft-Delete-Tombstone
        assert db_job.posting_snapshot_path is None
        assert verify.get(Application, application_id) is None         # hart gelöscht
        assert verify.get(JobFile, jobfile_id) is None                 # hart gelöscht


# ── Fall 2: Fehlerfall delete_job — Kernbeweis von P1-7 ─────────────────────────────────────
def test_delete_job_move_fehler_db_committet_trotzdem_und_uebrige_dateien_verschoben(
    client, session, tmp_path, monkeypatch
):
    """`shutil.move` scheitert für GENAU eine von drei Dateien → (a) die DB-Änderung ist
    TROTZDEM committet (kein Rollback — der Job bleibt gelöscht, es entsteht keine tote
    Referenz, weil die referenzierenden Rows ohnehin hart gelöscht werden), (b) der Fehlschlag
    wird gezählt und laut gemeldet (kein 500), (c) die ÜBRIGEN zwei Dateien werden trotzdem
    verschoben."""
    import shutil
    import app.main as main
    from app.db import engine
    from app.models import Application, Company, Job, JobFile
    from sqlmodel import Session as _Session

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)

    echter_move = shutil.move

    def kaputter_move(src, dst, *a, **kw):
        if "kaputt" in str(src):
            raise OSError("Simulierter Plattenfehler (pytest, gezielt für Datei 'kaputt')")
        return echter_move(src, dst, *a, **kw)

    monkeypatch.setattr(shutil, "move", kaputter_move)

    suffix = uuid.uuid4().hex[:8]
    company = Company(name=f"Fehlerfall GmbH {suffix}")
    session.add(company)
    session.commit()
    session.refresh(company)
    company_id = company.id

    job = Job(company_id=company_id, company_name=company.name, title="Test Rolle Fehlerfall",
              status="Beworben", found_date="2026-07-01", dedup_key=f"p64a-fehler|{suffix}")
    session.add(job)
    session.commit()
    session.refresh(job)
    job_id = job.id

    cover_pfad = _neue_datei(tmp_path / "outputs" / "anschreiben", f"cover_{suffix}.pdf")
    application = Application(job_id=job_id, status="Beworben", applied_date="2026-07-01",
                              channel="E-Mail",
                              cover_letter_pdf_path=f"outputs/anschreiben/cover_{suffix}.pdf")
    session.add(application)
    session.commit()
    session.refresh(application)
    application_id = application.id

    ok_pfad = _neue_datei(tmp_path / "data" / "job_files" / f"job_{job_id}", f"ok_{suffix}.pdf")
    jf_ok = JobFile(job_id=job_id, kind="Sonstiges", filename=f"ok_{suffix}.pdf",
                    file_path=f"data/job_files/job_{job_id}/ok_{suffix}.pdf")
    session.add(jf_ok)

    kaputt_pfad = _neue_datei(tmp_path / "data" / "job_files" / f"job_{job_id}", f"kaputt_{suffix}.pdf")
    jf_kaputt = JobFile(job_id=job_id, kind="Sonstiges", filename=f"kaputt_{suffix}.pdf",
                        file_path=f"data/job_files/job_{job_id}/kaputt_{suffix}.pdf")
    session.add(jf_kaputt)
    session.commit()
    session.refresh(jf_ok)
    session.refresh(jf_kaputt)
    jf_ok_id = jf_ok.id
    jf_kaputt_id = jf_kaputt.id

    r = client.delete(f"/api/jobs/{job_id}")
    assert r.status_code == 200, r.text     # KEIN 500 — der Fehlschlag wird gemeldet, nicht geworfen
    body = r.json()
    assert body["ok"] is True
    assert body["counts"]["dateien"] == 2          # cover + ok — "kaputt" zählt NICHT mit
    assert body["dateien_fehlgeschlagen"] == 1      # genau der eine erzwungene Fehlschlag

    # (a) DB TROTZDEM committet — kein Rollback, keine tote Referenz (Rows sind hart gelöscht):
    with _Session(engine) as verify:
        db_job = verify.get(Job, job_id)
        assert db_job is not None and db_job.deleted_at is not None   # Job bleibt gelöscht
        assert verify.get(Application, application_id) is None
        assert verify.get(JobFile, jf_ok_id) is None
        assert verify.get(JobFile, jf_kaputt_id) is None               # Row weg trotz Move-Fehler

    # (b)+(c) Die ÜBRIGEN Dateien wurden trotzdem verschoben:
    assert not cover_pfad.is_file()
    assert not ok_pfad.is_file()
    papierkorb_dateien = list((tmp_path / "data" / "papierkorb").iterdir())
    assert len(papierkorb_dateien) == 2
    namen = {p.name for p in papierkorb_dateien}
    assert any(f"cover_{suffix}" in n for n in namen)
    assert any(f"ok_{suffix}" in n for n in namen)
    assert not any(f"kaputt_{suffix}" in n for n in namen)

    # Die kaputte Datei ist jetzt eine VERWAISTE DATEI (bleibt an ihrem Original-Ort liegen,
    # obwohl die zugehörige DB-Row weg ist) — exakt der von P1-7 gewünschte Fehlerfall-Tausch:
    # Orphan statt toter Referenz.
    assert kaputt_pfad.is_file()


# ── Fall 3+4: delete_job_file — Normal-/Fehlerfall ──────────────────────────────────────────
def test_delete_job_file_normalfall(client, session, tmp_path, monkeypatch):
    import app.main as main
    from app.db import engine
    from app.models import Company, Job, JobFile
    from sqlmodel import Session as _Session

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)
    suffix = uuid.uuid4().hex[:8]

    company = Company(name=f"DJF Normalfall GmbH {suffix}")
    session.add(company)
    session.commit()
    session.refresh(company)
    company_id = company.id

    job = Job(company_id=company_id, company_name=company.name, title="Rolle",
              status="Beworben", found_date="2026-07-01", dedup_key=f"p64a-djf-normal|{suffix}")
    session.add(job)
    session.commit()
    session.refresh(job)
    job_id = job.id

    pfad = _neue_datei(tmp_path / "data" / "job_files" / f"job_{job_id}", f"datei_{suffix}.pdf")
    jf = JobFile(job_id=job_id, kind="Sonstiges", filename=f"datei_{suffix}.pdf",
                file_path=f"data/job_files/job_{job_id}/datei_{suffix}.pdf")
    session.add(jf)
    session.commit()
    session.refresh(jf)
    jf_id = jf.id

    r = client.delete(f"/api/files/{jf_id}")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "dateien_fehlgeschlagen": 0}   # F3: "ok" unverändert + neues Feld

    assert not pfad.is_file()
    papierkorb_dateien = list((tmp_path / "data" / "papierkorb").iterdir())
    assert len(papierkorb_dateien) == 1
    assert f"datei_{suffix}" in papierkorb_dateien[0].name

    with _Session(engine) as verify:
        assert verify.get(JobFile, jf_id) is None


def test_delete_job_file_move_fehler_wird_gemeldet_ohne_500(client, session, tmp_path, monkeypatch):
    import shutil
    import app.main as main
    from app.db import engine
    from app.models import Company, Job, JobFile
    from sqlmodel import Session as _Session

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)

    def kaputter_move(src, dst, *a, **kw):
        raise OSError("Simulierter Plattenfehler (pytest)")

    monkeypatch.setattr(shutil, "move", kaputter_move)

    suffix = uuid.uuid4().hex[:8]
    company = Company(name=f"DJF Fehlerfall GmbH {suffix}")
    session.add(company)
    session.commit()
    session.refresh(company)
    company_id = company.id

    job = Job(company_id=company_id, company_name=company.name, title="Rolle",
              status="Beworben", found_date="2026-07-01", dedup_key=f"p64a-djf-fehler|{suffix}")
    session.add(job)
    session.commit()
    session.refresh(job)
    job_id = job.id

    pfad = _neue_datei(tmp_path / "data" / "job_files" / f"job_{job_id}", f"datei_{suffix}.pdf")
    jf = JobFile(job_id=job_id, kind="Sonstiges", filename=f"datei_{suffix}.pdf",
                file_path=f"data/job_files/job_{job_id}/datei_{suffix}.pdf")
    session.add(jf)
    session.commit()
    session.refresh(jf)
    jf_id = jf.id

    r = client.delete(f"/api/files/{jf_id}")
    assert r.status_code == 200, r.text     # kein 500 trotz Move-Fehler
    assert r.json() == {"ok": True, "dateien_fehlgeschlagen": 1}

    # DB trotzdem committet (Row weg — keine tote Referenz), Datei bleibt liegen (Orphan):
    with _Session(engine) as verify:
        assert verify.get(JobFile, jf_id) is None
    assert pfad.is_file()


# ── Fall 5+6: delete_virtual_file — Normal-/Fehlerfall (F3: "papierkorb"-Feld) ──────────────
def test_delete_virtual_file_normalfall_papierkorb_feld(client, session, tmp_path, monkeypatch):
    import app.main as main
    from app.db import engine
    from app.models import Company
    from sqlmodel import Session as _Session

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)
    suffix = uuid.uuid4().hex[:8]

    pfad = _neue_datei(tmp_path / "data" / "company_fit", f"fit_{suffix}.html")
    company = Company(name=f"DVF Normalfall GmbH {suffix}",
                      fit_analysis_path=f"data/company_fit/fit_{suffix}.html")
    session.add(company)
    session.commit()
    session.refresh(company)
    company_id = company.id

    r = client.delete(f"/api/files/virtual/company/{company_id}/fit")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["dateien_fehlgeschlagen"] == 0                     # neues Feld
    assert body["papierkorb"].startswith("data/papierkorb/")       # F3: bestehendes Feld gefüllt
    assert f"fit_{suffix}" in body["papierkorb"]

    assert not pfad.is_file()
    ziel = tmp_path / body["papierkorb"]
    assert ziel.is_file()

    with _Session(engine) as verify:
        db_company = verify.get(Company, company_id)
        assert db_company.fit_analysis_path is None


def test_delete_virtual_file_move_fehler_feld_bleibt_genullt_papierkorb_none(
    client, session, tmp_path, monkeypatch
):
    import shutil
    import app.main as main
    from app.db import engine
    from app.models import Company
    from sqlmodel import Session as _Session

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)

    def kaputter_move(src, dst, *a, **kw):
        raise OSError("Simulierter Plattenfehler (pytest)")

    monkeypatch.setattr(shutil, "move", kaputter_move)

    suffix = uuid.uuid4().hex[:8]
    pfad = _neue_datei(tmp_path / "data" / "company_fit", f"fit_{suffix}.html")
    company = Company(name=f"DVF Fehlerfall GmbH {suffix}",
                      fit_analysis_path=f"data/company_fit/fit_{suffix}.html")
    session.add(company)
    session.commit()
    session.refresh(company)
    company_id = company.id

    r = client.delete(f"/api/files/virtual/company/{company_id}/fit")
    assert r.status_code == 200, r.text     # kein 500 trotz Move-Fehler
    assert r.json() == {"ok": True, "papierkorb": None, "dateien_fehlgeschlagen": 1}

    # DB-Feld ist UNABHÄNGIG vom Move-Ergebnis bereits genullt+committet — keine tote Referenz:
    with _Session(engine) as verify:
        db_company = verify.get(Company, company_id)
        assert db_company.fit_analysis_path is None
    # Die Datei bleibt liegen (Orphan), weil der Move fehlschlug:
    assert pfad.is_file()


# ── Fall 7: Alarmschwelle pipeline.cleanup.scan ─────────────────────────────────────────────
def test_scan_dangling_referenzen_ueber_schwelle_setzt_auffaellig(session):
    """dangling_referenzen floss bisher NICHT in ergebnis['auffaellig'] ein. Beweis als
    EINSEITIGE Implikation (genug tote Referenzen ⇒ auffaellig=True), s. Moduldocstring."""
    from pipeline import cleanup
    from app.models import Job

    vorher = cleanup.scan(html=False)["dangling_referenzen"]["anzahl"]

    suffix = uuid.uuid4().hex[:8]
    for i in range(5):    # Schwelle ist > 3 → 5 tote Referenzen überschreiten sie mit Marge
        job = Job(title=f"Dangling-Probe {i}", status="Neu", found_date="2026-07-01",
                  dedup_key=f"p64a-dangling|{suffix}|{i}",
                  posting_snapshot_path=f"data/job_postings/nie_vorhanden_{suffix}_{i}.html")
        session.add(job)
    session.commit()

    nachher = cleanup.scan(html=False)
    assert nachher["dangling_referenzen"]["anzahl"] >= vorher + 5
    assert nachher["dangling_referenzen"]["anzahl"] > 3
    assert nachher["auffaellig"] is True


# ── Fall 8+9: delete_transcript — Normal-/Fehlerfall ────────────────────────────────────────
def test_delete_transcript_normalfall(client, session, tmp_path, monkeypatch):
    """Drei Pfade (file_path/debrief_path/report_path) UND die gekoppelte JobFile-Row (dieselbe
    physische Datei, s. upload_job_file) werden beim Reordering korrekt mitbehandelt."""
    import app.main as main
    from app.db import engine
    from app.models import Company, Job, JobFile, Transcript
    from sqlmodel import Session as _Session

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)
    suffix = uuid.uuid4().hex[:8]

    company = Company(name=f"DT Normalfall GmbH {suffix}")
    session.add(company)
    session.commit()
    session.refresh(company)
    company_id = company.id

    job = Job(company_id=company_id, company_name=company.name, title="Rolle",
              status="Beworben", found_date="2026-07-01", dedup_key=f"p64a2-dt-normal|{suffix}")
    session.add(job)
    session.commit()
    session.refresh(job)
    job_id = job.id

    datei_pfad = _neue_datei(tmp_path / "data" / "job_files" / f"job_{job_id}", f"transkript_{suffix}.vtt")
    debrief_pfad = _neue_datei(tmp_path / "data" / "transcripts", f"debrief_{suffix}.html")
    report_pfad = _neue_datei(tmp_path / "data" / "transcripts", f"report_{suffix}.html")
    transcript = Transcript(job_id=job_id, source="manuell", title="Test-Transkript",
                            file_path=f"data/job_files/job_{job_id}/transkript_{suffix}.vtt",
                            debrief_path=f"data/transcripts/debrief_{suffix}.html",
                            report_path=f"data/transcripts/report_{suffix}.html")
    session.add(transcript)
    session.commit()
    session.refresh(transcript)
    transcript_id = transcript.id

    # Gekoppelte JobFile-Row — zeigt (wie bei einem echten Transkript-Upload) auf DIESELBE Datei
    # wie transcript.file_path (s. upload_job_file, gemeinsame Variable `rel`).
    jobfile = JobFile(job_id=job_id, transcript_id=transcript_id, kind="Transkript",
                      filename=f"transkript_{suffix}.vtt",
                      file_path=f"data/job_files/job_{job_id}/transkript_{suffix}.vtt")
    session.add(jobfile)
    session.commit()
    session.refresh(jobfile)
    jobfile_id = jobfile.id

    r = client.delete(f"/api/transcripts/{transcript_id}")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "dateien_fehlgeschlagen": 0}   # F3: "ok" unverändert + neues Feld

    assert not datei_pfad.is_file() and not debrief_pfad.is_file() and not report_pfad.is_file()
    papierkorb_dateien = sorted((tmp_path / "data" / "papierkorb").iterdir())
    assert len(papierkorb_dateien) == 3     # NICHT 4 — jobfile.file_path ist dieselbe Datei wie
                                             # transcript.file_path, wird nicht doppelt verschoben

    with _Session(engine) as verify:
        assert verify.get(Transcript, transcript_id) is None
        assert verify.get(JobFile, jobfile_id) is None


def test_delete_transcript_move_fehler_db_committet_trotzdem_und_uebrige_verschoben(
    client, session, tmp_path, monkeypatch
):
    import shutil
    import app.main as main
    from app.db import engine
    from app.models import Company, Job, Transcript
    from sqlmodel import Session as _Session

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)

    echter_move = shutil.move

    def kaputter_move(src, dst, *a, **kw):
        if "kaputt" in str(src):
            raise OSError("Simulierter Plattenfehler (pytest, gezielt für 'kaputt')")
        return echter_move(src, dst, *a, **kw)

    monkeypatch.setattr(shutil, "move", kaputter_move)

    suffix = uuid.uuid4().hex[:8]
    company = Company(name=f"DT Fehlerfall GmbH {suffix}")
    session.add(company)
    session.commit()
    session.refresh(company)
    company_id = company.id

    job = Job(company_id=company_id, company_name=company.name, title="Rolle",
              status="Beworben", found_date="2026-07-01", dedup_key=f"p64a2-dt-fehler|{suffix}")
    session.add(job)
    session.commit()
    session.refresh(job)
    job_id = job.id

    datei_pfad = _neue_datei(tmp_path / "data" / "transcripts", f"transkript_{suffix}.md")
    kaputt_pfad = _neue_datei(tmp_path / "data" / "transcripts", f"kaputt_debrief_{suffix}.html")
    report_pfad = _neue_datei(tmp_path / "data" / "transcripts", f"report_{suffix}.html")
    transcript = Transcript(job_id=job_id, source="manuell", title="Test-Transkript",
                            file_path=f"data/transcripts/transkript_{suffix}.md",
                            debrief_path=f"data/transcripts/kaputt_debrief_{suffix}.html",
                            report_path=f"data/transcripts/report_{suffix}.html")
    session.add(transcript)
    session.commit()
    session.refresh(transcript)
    transcript_id = transcript.id

    r = client.delete(f"/api/transcripts/{transcript_id}")
    assert r.status_code == 200, r.text     # kein 500 trotz Move-Fehler
    assert r.json() == {"ok": True, "dateien_fehlgeschlagen": 1}

    with _Session(engine) as verify:
        assert verify.get(Transcript, transcript_id) is None   # DB committet, kein Rollback

    assert not datei_pfad.is_file()
    assert not report_pfad.is_file()
    assert kaputt_pfad.is_file()      # Orphan — bleibt an seinem Original-Ort liegen
    papierkorb_dateien = list((tmp_path / "data" / "papierkorb").iterdir())
    assert len(papierkorb_dateien) == 2


# ── Fall 10+11: delete_company — Normal-/Fehlerfall (hartes Löschen) ────────────────────────
def test_delete_company_normalfall(client, session, tmp_path, monkeypatch):
    import app.main as main
    from app.db import engine
    from app.models import Company, Contact, Email
    from sqlmodel import Session as _Session

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)
    suffix = uuid.uuid4().hex[:8]

    pfad = _neue_datei(tmp_path / "data" / "company_fit", f"fit_{suffix}.html")
    company = Company(name=f"DC Normalfall GmbH {suffix}",
                      fit_analysis_path=f"data/company_fit/fit_{suffix}.html")
    session.add(company)
    session.commit()
    session.refresh(company)
    company_id = company.id

    contact = Contact(company_id=company_id, name="Test Kontakt")
    session.add(contact)
    email = Email(company_id=company_id, subject="Test Mail")
    session.add(email)
    session.commit()
    session.refresh(contact)
    session.refresh(email)
    contact_id = contact.id
    email_id = email.id

    r = client.delete(f"/api/companies/{company_id}")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "dateien_fehlgeschlagen": 0}   # F3: "ok" unverändert + neues Feld

    assert not pfad.is_file()
    papierkorb_dateien = list((tmp_path / "data" / "papierkorb").iterdir())
    assert len(papierkorb_dateien) == 1
    assert f"fit_{suffix}" in papierkorb_dateien[0].name

    with _Session(engine) as verify:
        assert verify.get(Company, company_id) is None                # hart gelöscht
        assert verify.get(Contact, contact_id) is None                 # hart gelöscht (unverändert)
        db_email = verify.get(Email, email_id)
        assert db_email is not None and db_email.company_id is None    # nur entkoppelt (unverändert)


def test_delete_company_move_fehler_hartes_loeschen_bleibt_trotzdem(
    client, session, tmp_path, monkeypatch
):
    """delete_company löscht die Row HART (kein Soft-Delete-Tombstone wie bei Job) — Beweis,
    dass die Reihenfolge-Umkehr trotzdem greift: die Row ist nach dem Commit komplett weg, ein
    späterer Move-Fehlschlag kann strukturell KEINE tote Referenz mehr erzeugen (es gibt gar
    keine Row mehr, die auf den Pfad zeigen könnte) — nur eine verwaiste Datei."""
    import shutil
    import app.main as main
    from app.db import engine
    from app.models import Company, Contact
    from sqlmodel import Session as _Session

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)

    def kaputter_move(src, dst, *a, **kw):
        raise OSError("Simulierter Plattenfehler (pytest)")

    monkeypatch.setattr(shutil, "move", kaputter_move)

    suffix = uuid.uuid4().hex[:8]
    pfad = _neue_datei(tmp_path / "data" / "company_fit", f"fit_{suffix}.html")
    company = Company(name=f"DC Fehlerfall GmbH {suffix}",
                      fit_analysis_path=f"data/company_fit/fit_{suffix}.html")
    session.add(company)
    session.commit()
    session.refresh(company)
    company_id = company.id
    contact = Contact(company_id=company_id, name="Test Kontakt")
    session.add(contact)
    session.commit()
    session.refresh(contact)
    contact_id = contact.id

    r = client.delete(f"/api/companies/{company_id}")
    assert r.status_code == 200, r.text     # kein 500 trotz Move-Fehler
    assert r.json() == {"ok": True, "dateien_fehlgeschlagen": 1}

    with _Session(engine) as verify:
        assert verify.get(Company, company_id) is None    # trotzdem hart gelöscht — kein Rollback
        assert verify.get(Contact, contact_id) is None

    assert pfad.is_file()    # Orphan — bleibt liegen, weil der Move fehlschlug


# ── Fall 12+13: delete_profil_file — Normal-/Fehlerfall (s. WICHTIGER BEFUND 3) ─────────────
def test_delete_profil_file_normalfall(client, session, tmp_path, monkeypatch):
    import os
    import app.main as main
    from app.db import engine
    from app.models import ProfileFile
    from sqlmodel import Session as _Session

    # ECHTEN Pfad + mtime VOR jeder Umleitung festhalten (Sicherheitsnetz, s. Moduldocstring
    # WICHTIGER BEFUND 3) — main._PROFIL_STRUKTUR_PATH wird gleich monkeypatcht.
    echte_struktur_pfad = main._PROFIL_STRUKTUR_PATH
    mtime_vorher = os.path.getmtime(echte_struktur_pfad) if echte_struktur_pfad.exists() else None

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)
    fake_struktur_pfad = tmp_path / "config" / "profil_struktur.md"
    monkeypatch.setattr(main, "_PROFIL_STRUKTUR_PATH", fake_struktur_pfad)

    suffix = uuid.uuid4().hex[:8]
    pfad = _neue_datei(tmp_path / "data" / "profil" / "dateien", f"zeugnis_{suffix}.pdf")
    pf = ProfileFile(kind="Zeugnis", filename=f"zeugnis_{suffix}.pdf",
                     file_path=f"data/profil/dateien/zeugnis_{suffix}.pdf")
    session.add(pf)
    session.commit()
    session.refresh(pf)
    pf_id = pf.id

    r = client.delete(f"/api/profil/dateien/{pf_id}")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "dateien_fehlgeschlagen": 0}   # F3: "ok" unverändert + neues Feld

    assert not pfad.is_file()
    papierkorb_dateien = list((tmp_path / "data" / "papierkorb").iterdir())
    assert len(papierkorb_dateien) == 1
    assert f"zeugnis_{suffix}" in papierkorb_dateien[0].name

    with _Session(engine) as verify:
        assert verify.get(ProfileFile, pf_id) is None

    # _profil_struktur_schreiben lief — aber NUR gegen die umgeleitete tmp-Datei:
    assert fake_struktur_pfad.is_file()

    # Sicherheitsnetz: die ECHTE Datei ist unangetastet geblieben.
    mtime_nachher = os.path.getmtime(echte_struktur_pfad) if echte_struktur_pfad.exists() else None
    assert mtime_nachher == mtime_vorher, (
        "config/profil_struktur.md wurde real veraendert -- die _PROFIL_STRUKTUR_PATH-Umleitung "
        "hat NICHT gegriffen!"
    )


def test_delete_profil_file_move_fehler_wird_gemeldet_ohne_500(client, session, tmp_path, monkeypatch):
    import os
    import shutil
    import app.main as main
    from app.db import engine
    from app.models import ProfileFile
    from sqlmodel import Session as _Session

    echte_struktur_pfad = main._PROFIL_STRUKTUR_PATH
    mtime_vorher = os.path.getmtime(echte_struktur_pfad) if echte_struktur_pfad.exists() else None

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)
    fake_struktur_pfad = tmp_path / "config" / "profil_struktur.md"
    monkeypatch.setattr(main, "_PROFIL_STRUKTUR_PATH", fake_struktur_pfad)

    def kaputter_move(src, dst, *a, **kw):
        raise OSError("Simulierter Plattenfehler (pytest)")

    monkeypatch.setattr(shutil, "move", kaputter_move)

    suffix = uuid.uuid4().hex[:8]
    pfad = _neue_datei(tmp_path / "data" / "profil" / "dateien", f"zeugnis_{suffix}.pdf")
    pf = ProfileFile(kind="Zeugnis", filename=f"zeugnis_{suffix}.pdf",
                     file_path=f"data/profil/dateien/zeugnis_{suffix}.pdf")
    session.add(pf)
    session.commit()
    session.refresh(pf)
    pf_id = pf.id

    r = client.delete(f"/api/profil/dateien/{pf_id}")
    assert r.status_code == 200, r.text     # kein 500 trotz Move-Fehler
    assert r.json() == {"ok": True, "dateien_fehlgeschlagen": 1}

    with _Session(engine) as verify:
        assert verify.get(ProfileFile, pf_id) is None    # trotzdem committet — kein Rollback

    assert pfad.is_file()    # Orphan — bleibt liegen, weil der Move fehlschlug

    mtime_nachher = os.path.getmtime(echte_struktur_pfad) if echte_struktur_pfad.exists() else None
    assert mtime_nachher == mtime_vorher, (
        "config/profil_struktur.md wurde real veraendert -- die _PROFIL_STRUKTUR_PATH-Umleitung "
        "hat NICHT gegriffen!"
    )


# ── Fall 14: _in_papierkorb blockt Pfade ausserhalb data/ und outputs/ (P3-1) ───────────────
def test_in_papierkorb_blockt_pfad_ausserhalb_erlaubter_wurzeln(tmp_path, monkeypatch):
    """P3-1 (Code-Review 2026-07-25): `_in_papierkorb` verliess sich bisher VOLLSTAENDIG darauf,
    dass Aufrufer bereits sichere (projekt-root-relative, faktisch immer data/- oder outputs/-
    interne) Pfade uebergeben -- keine eigene Wurzel-Pruefung. Eine Datei ausserhalb von data/
    und outputs/ (hier: unter config/, ein echter, aber NICHT erlaubter Top-Level-Ordner dieses
    Projekts) wurde bisher anstandslos in den Papierkorb verschoben. Nach dem Fix wirft die
    Funktion OSError, BEVOR irgendetwas angefasst wird -- die Datei bleibt an ihrem Original-Ort
    liegen, der Papierkorb bleibt leer. Dieser Test schlaegt ohne den P3-1-Fix fehl (kein
    OSError, Datei wird verschoben).

    `_PROJECT_ROOT` wird wie in allen Faellen oben per monkeypatch auf `tmp_path` umgebunden
    (WICHTIGER BEFUND 1 im Moduldocstring) -- die neue Wurzel-Pruefung MUSS deshalb ihre eigenen
    "erlaubten Wurzeln" ebenfalls frisch aus dem (ggf. umgebundenen) `_PROJECT_ROOT` bilden,
    nicht aus einer beim Modul-Import eingefrorenen Liste (wie bis P2-54 `main._ALLOWED_ROOTS`,
    die auf die ECHTEN data/- und outputs/-Ordner zeigte) -- sonst wuerde JEDER Aufruf in
    JEDEM der Fälle 1-13 oben faelschlich als "ausserhalb der erlaubten Wurzeln" abgelehnt, weil
    `tmp_path` strukturell nirgends unter dem echten Projekt-Root liegt. Die Gesamt-Testsuite bleibt grün
    ist der empirische Beweis, dass diese Falle hier nicht zugeschlagen hat."""
    import app.main as main

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)

    ausserhalb = _neue_datei(tmp_path / "config", "geheim.txt")
    assert ausserhalb.is_file()

    import pytest
    with pytest.raises(OSError):
        main._in_papierkorb("config/geheim.txt")

    assert ausserhalb.is_file()          # unangetastet -- kein Move vor dem Wurf
    papierkorb = tmp_path / "data" / "papierkorb"
    assert not papierkorb.exists() or not list(papierkorb.iterdir())


def test_in_papierkorb_erlaubt_weiterhin_data_und_outputs(tmp_path, monkeypatch):
    """Gegenprobe zu oben: legitime Pfade unter data/ UND outputs/ funktionieren nach dem Fix
    unveraendert (outputs/ wird von keinem der Faelle 1-13 oben abgedeckt, s. cv_export.py:
    CV/Anschreiben-Dateien landen dort -- ohne diesen Test wuerde ein zu enger Fix (nur data/
    erlaubt) unbemerkt durchrutschen). Seit P2-56 zaehlen nur Artefakt-Ordner der Positivliste,
    deshalb liegt die data/-Datei in data/job_files/ statt im erfundenen data/cv/."""
    import app.main as main

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)

    in_data = _neue_datei(tmp_path / "data" / "job_files" / "job_1", "lebenslauf.pdf")
    in_outputs = _neue_datei(tmp_path / "outputs" / "cv", "lebenslauf.pdf")

    ergebnis_data = main._in_papierkorb("data/job_files/job_1/lebenslauf.pdf")
    assert ergebnis_data is not None and ergebnis_data.startswith("data/papierkorb/")
    assert not in_data.is_file()

    ergebnis_outputs = main._in_papierkorb("outputs/cv/lebenslauf.pdf")
    assert ergebnis_outputs is not None and ergebnis_outputs.startswith("data/papierkorb/")
    assert not in_outputs.is_file()


# ── Fall 15: delete_company nullt company_id an Tombstone-Jobs (P3-6) ───────────────────────
def test_delete_company_nullt_company_id_an_tombstone_jobs(client, session, tmp_path, monkeypatch):
    """P3-6 (Code-Review 2026-07-25): Die 409-Schranke in `delete_company` zaehlt bewusst nur
    AKTIVE (nicht-geloeschte) Jobs -- eine Firma mit ausschliesslich soft-geloeschten
    (Tombstone-)Jobs bleibt loeschbar (Dedup-Tombstones sollen genau das). Ohne Gegenmassnahme
    behielte der Tombstone danach eine `company_id`, die ins Leere zeigt (die Company-Row ist ja
    weg) -- ein stiller toter Verweis. Beweis: Tombstone-Job VOR dem Löschen mit `company_id`
    gesetzt; nach dem Löschen der Firma muss `company_id` None sein, `company_name`
    (denormalisiert, das einzige, was Anzeige UND Dedup-Pfad `pipeline.ingest` tatsächlich lesen)
    bleibt dagegen UNVERAENDERT. Dieser Test schlägt ohne den P3-6-Fix fehl (`company_id` bliebe
    auf die geloeschte Company-Row gesetzt)."""
    import app.main as main
    from app.db import engine
    from app.models import Company, Job
    from sqlmodel import Session as _Session

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)
    suffix = uuid.uuid4().hex[:8]

    company = Company(name=f"Tombstone GmbH {suffix}")
    session.add(company)
    session.commit()
    session.refresh(company)
    company_id = company.id
    company_name = company.name

    tombstone = Job(company_id=company_id, company_name=company_name,
                    title="Laengst abgesagte Rolle", status="Absage",
                    found_date="2026-01-01", dedup_key=f"p68b-tombstone|{suffix}",
                    deleted_at="2026-02-01T00:00:00")
    session.add(tombstone)
    session.commit()
    session.refresh(tombstone)
    tombstone_id = tombstone.id

    # Vorbedingung, die den Befund erst ermoeglicht: KEINE aktiven Jobs mehr -- die 409-Schranke
    # darf nicht greifen, die Firma muss loeschbar sein.
    r = client.delete(f"/api/companies/{company_id}")
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "dateien_fehlgeschlagen": 0}   # F3: Response-Form unveraendert

    with _Session(engine) as verify:
        assert verify.get(Company, company_id) is None            # hart gelöscht (unveraendert)
        db_tombstone = verify.get(Job, tombstone_id)
        assert db_tombstone is not None                            # Tombstone bleibt erhalten
        assert db_tombstone.company_id is None                     # P3-6: nicht mehr ins Leere zeigend
        assert db_tombstone.company_name == company_name           # denormalisiert unveraendert


def test_delete_company_mit_aktivem_job_weiterhin_409_trotz_tombstone_fix(
    client, session, tmp_path, monkeypatch
):
    """Gegenprobe zu Fall 15: Die 409-Schranke selbst bleibt unveraendert -- eine Firma mit
    MINDESTENS EINEM aktiven Job ist weiterhin nicht loeschbar, auch wenn sie zusaetzlich
    Tombstones hat. Ohne diesen Test koennte eine ueberschiessende Korrektur (z. B. die
    409-Pruefung versehentlich auf ALLE Jobs statt nur aktive auszuweiten) unbemerkt bleiben."""
    import app.main as main
    from app.models import Company, Job

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)
    suffix = uuid.uuid4().hex[:8]

    company = Company(name=f"Gemischt GmbH {suffix}")
    session.add(company)
    session.commit()
    session.refresh(company)
    company_id = company.id

    aktiv = Job(company_id=company_id, company_name=company.name, title="Aktive Rolle",
               status="Beworben", found_date="2026-01-01", dedup_key=f"p68b-aktiv|{suffix}")
    tombstone = Job(company_id=company_id, company_name=company.name, title="Tote Rolle",
                    status="Absage", found_date="2026-01-01",
                    dedup_key=f"p68b-gemischt-tombstone|{suffix}",
                    deleted_at="2026-02-01T00:00:00")
    session.add(aktiv)
    session.add(tombstone)
    session.commit()

    r = client.delete(f"/api/companies/{company_id}")
    assert r.status_code == 409
    assert "Aktive Rolle" in r.text
