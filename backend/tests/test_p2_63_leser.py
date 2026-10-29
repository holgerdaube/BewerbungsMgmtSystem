"""P2-63 (01.10.2026): Leser und Weichen nach der Kürzung der Dateinamen.

Datum `JJJJMMTT` (neu) und `JJJJ_MM_TT` (Bestand) müssen überall gelesen werden, wo Namen
ausgewertet werden: Papierkorb-Alter (`cleanup`), `migrate_reports`. Der Papierkorb vergibt das
neue Präfix. Die Re-Export-Weichen in `cv_export` erkennen auch den Namen derselben Stelle nach der
alten Konvention als eigenen, damit beim erneuten Export kein Waise entsteht. Alle Firmen und
Rollen sind erfunden. App-Importe in den Testfunktionen (conftest-Konvention).
"""
import datetime
import os
import time

from tests.test_cv_export import _docx_mit_text, _fake_to_pdf, _patch_project_root


# ── Papierkorb-Alter (cleanup) ──────────────────────────────────────────────────────────────
def _vor_tagen(n):
    return datetime.date.today() - datetime.timedelta(days=n)


def test_papierkorb_alter_neues_format(tmp_path):
    from pipeline import cleanup

    p = tmp_path / f"{_vor_tagen(40):%Y%m%d}_Bericht.html"
    p.write_text("x")
    assert cleanup._papierkorb_alter_tage(p) == 40


def test_papierkorb_alter_altes_format(tmp_path):
    from pipeline import cleanup

    p = tmp_path / f"{_vor_tagen(40):%Y_%m_%d}_Bericht.html"
    p.write_text("x")
    # mtime bewusst frisch: ohne Präfix-Auswertung käme 0 heraus (Gegenprobe zur Kernregel)
    assert cleanup._papierkorb_alter_tage(p) == 40


def test_papierkorb_alter_ohne_praefix_faellt_auf_mtime_zurueck(tmp_path):
    from pipeline import cleanup

    p = tmp_path / "Ohne_Datum.html"
    p.write_text("x")
    alt = time.time() - 12 * 86400
    os.utime(p, (alt, alt))
    assert cleanup._papierkorb_alter_tage(p) == 12
    # unmögliches Datum im Präfix zählt als "kein Präfix"
    q = tmp_path / "20261399_Kaputt.html"
    q.write_text("x")
    os.utime(q, (alt, alt))
    assert cleanup._papierkorb_alter_tage(q) == 12


def test_cleanup_papierkorb_vergibt_neues_praefix(tmp_path, monkeypatch):
    from pipeline import cleanup

    monkeypatch.setattr(cleanup, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cleanup, "PAPIERKORB", tmp_path / "data" / "papierkorb")
    quelle = tmp_path / "outputs" / "cv" / "CV_Test.pdf"
    quelle.parent.mkdir(parents=True)
    quelle.write_bytes(b"%PDF")
    ziel = cleanup._in_papierkorb("outputs/cv/CV_Test.pdf")
    assert ziel == f"data/papierkorb/{datetime.date.today():%Y%m%d}_CV_Test.pdf"
    assert (tmp_path / ziel).is_file()
    # und das Alter dieses Namens ist 0 Tage (neues Format wird gelesen)
    assert cleanup._papierkorb_alter_tage(tmp_path / ziel) == 0


def test_main_papierkorb_vergibt_neues_praefix(tmp_path, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)
    quelle = tmp_path / "data" / "company_fit" / "20261001_CompanyFit_Muster.html"
    quelle.parent.mkdir(parents=True)
    quelle.write_text("<html></html>")
    ziel = main._in_papierkorb("data/company_fit/20261001_CompanyFit_Muster.html")
    assert ziel == f"data/papierkorb/{datetime.date.today():%Y%m%d}_20261001_CompanyFit_Muster.html"
    assert not quelle.exists() and (tmp_path / ziel).is_file()


# ── migrate_reports ─────────────────────────────────────────────────────────────────────────
def test_migrate_reports_erkennt_beide_datumsformate_und_typ_woerter():
    from pipeline.migrate_reports import _TRANSCRIPT_OK_RE, _date_from_filename, _is_already_new

    for name in ["20261001_Match_Muster_Lead.html", "2026_10_01_Match_Muster_Lead.html",
                 "20261001_Anzeige_Muster.html", "20261001_Auswertung_Muster_R2.html",
                 "20261001_Beirat_Muster.html", "2026_10_01_Stellenausschreibung_Muster.html"]:
        assert _is_already_new(name), name
    # Gegenproben: Job-ID im Namen, unbekannter Typ, kein Datum
    assert not _is_already_new("20261001_Briefing_Job12_R1_Muster.html")
    assert not _is_already_new("20261001_Unbekannt_Muster.html")
    assert not _is_already_new("Match_Muster.html")

    assert _TRANSCRIPT_OK_RE.match("Transkript_20261001_Anna_Muster_Lead.md")
    assert _TRANSCRIPT_OK_RE.match("Debrief_2026_10_01_Anna_Muster_Lead.md")
    assert not _TRANSCRIPT_OK_RE.match("Transkript_Job12_R1.md")

    soll = datetime.date(2026, 10, 1)
    assert _date_from_filename("20261001_Analyse_Absagen.html") == soll
    assert _date_from_filename("2026_10_01_Analyse_Absagen.html") == soll
    assert _date_from_filename("Analyse_Absagen.html") is None


# ── Re-Export-Weichen in cv_export ──────────────────────────────────────────────────────────
def _stelle(session, firma, titel, dedup):
    from app.models import Company, Job

    company = Company(name=firma)
    session.add(company)
    session.commit()
    session.refresh(company)
    job = Job(company_id=company.id, company_name=company.name, title=titel, status="Beworben",
              found_date="2026-10-01", dedup_key=dedup)
    session.add(job)
    session.commit()
    session.refresh(job)
    return company, job


def test_cv_weiche_altname_derselben_stelle_wird_umgestellt(session, tmp_path, monkeypatch):
    from app import naming
    from app.models import CVVersion

    cv_export, cleanup = _patch_project_root(monkeypatch, tmp_path)
    monkeypatch.setattr(cv_export, "to_pdf", _fake_to_pdf)
    company, job = _stelle(session, "Muster Beratung GmbH (Klient: internationale Bank)",
                           "Director Professional Services Delivery Europe West", "p263|cv1")

    alt = naming.cv_filename_alt(company.name, job.title, "DE")
    neu = naming.cv_filename(company.name, job.title, "DE")
    assert alt != neu
    ordner = tmp_path / "outputs" / "cv"
    _docx_mit_text(ordner / f"{alt}.docx", ["Max Muster", "EXECUTIVE SUMMARY"])
    (ordner / f"{alt}.pdf").write_bytes(b"%PDF-1.4 ALT\n")
    cv = CVVersion(job_id=job.id, language="DE", kind="tailored", status="fertig",
                   file_path=f"outputs/cv/{alt}.docx", pdf_path=f"outputs/cv/{alt}.pdf")
    session.add(cv)
    session.commit()
    session.refresh(cv)

    out = cv_export.export(cv.id)

    # eigene Datei: genau der neue Name, kein "_2", kein Waise unter dem alten Namen
    assert out["docx"] == f"outputs/cv/{neu}.docx" and out["pdf"] == f"outputs/cv/{neu}.pdf"
    assert sorted(p.name for p in ordner.iterdir()) == [f"{neu}.docx", f"{neu}.pdf"]
    assert any(alt in p.name for p in cleanup.PAPIERKORB.glob("*"))   # alte PDF im Papierkorb


def test_cv_weiche_gegenprobe_neuer_name_bleibt(session, tmp_path, monkeypatch):
    from app import naming
    from app.models import CVVersion

    cv_export, _ = _patch_project_root(monkeypatch, tmp_path)
    monkeypatch.setattr(cv_export, "to_pdf", _fake_to_pdf)
    company, job = _stelle(session, "Muster Beratung GmbH", "Director Professional Services Delivery Europe",
                           "p263|cv2")
    neu = naming.cv_filename(company.name, job.title, "DE")
    ordner = tmp_path / "outputs" / "cv"
    _docx_mit_text(ordner / f"{neu}.docx", ["Max Muster", "EXECUTIVE SUMMARY"])
    cv = CVVersion(job_id=job.id, language="DE", kind="tailored", status="fertig",
                   file_path=f"outputs/cv/{neu}.docx")
    session.add(cv)
    session.commit()
    session.refresh(cv)
    assert cv_export.export(cv.id)["docx"] == f"outputs/cv/{neu}.docx"      # unverändert, kein _2


def test_anschreiben_weiche_altname_derselben_stelle_wird_umgestellt(session, tmp_path, monkeypatch):
    from app import naming
    from app.models import Application

    cv_export, cleanup = _patch_project_root(monkeypatch, tmp_path)
    monkeypatch.setattr(cv_export, "to_pdf", _fake_to_pdf)
    company, job = _stelle(session, "Beispiel Systeme GmbH & Co. KG", "Senior Customer Success Manager Enterprise",
                           "p263|cl1")
    alt = naming.cover_letter_filename_alt(company.name, job.title, "DE")
    neu = naming.cover_letter_filename(company.name, job.title, "DE")
    assert alt != neu
    ordner = tmp_path / "outputs" / "anschreiben"
    _docx_mit_text(ordner / f"{alt}.docx", ["Max Muster", "Mit freundlichen Grüßen,"])
    (ordner / f"{alt}.pdf").write_bytes(b"%PDF-1.4 ALT\n")
    app = Application(job_id=job.id, status="Beworben", cover_letter_language="DE",
                      cover_letter_path=f"outputs/anschreiben/{alt}.docx",
                      cover_letter_pdf_path=f"outputs/anschreiben/{alt}.pdf")
    session.add(app)
    session.commit()
    session.refresh(app)

    out = cv_export.export_cover_letter(app.id)

    assert out["docx"] == f"outputs/anschreiben/{neu}.docx" and out["pdf"] == f"outputs/anschreiben/{neu}.pdf"
    assert sorted(p.name for p in ordner.iterdir()) == [f"{neu}.docx", f"{neu}.pdf"]
    assert any(alt in p.name for p in cleanup.PAPIERKORB.glob("*"))
