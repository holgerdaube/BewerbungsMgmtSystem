"""Tests für Phase 67C (P2-9, P2-10, P2-18 aus tasks/code_review_2026-07-25.md, s.
tasks/spec_phase67_p2_befunde.md, Abschnitt "Stufe 67C").

P2-9: `export_cover_letter()` fiel bei fehlender `cover_letter_language` still auf "DE" zurück
— die alte Heuristik prüfte den Namen der IMMER GLEICHEN Zwischendatei (`_raw_<id>.docx`, von
`cover_letter_render` unmittelbar davor gesetzt), die "_EN" strukturell nie enthalten kann. Fix:
Sprache aus dem TATSÄCHLICHEN Text ableiten (`cv_export._sprache_aus_text`).

P2-10: `export()`/`export_cover_letter()` ließen beim Umbenennen (Titel-/Firmenkorrektur) die
ALTE PDF unreferenziert mit veraltetem Inhalt liegen. Fix: alten Pfad vor dem Zurücksetzen
merken, in den Papierkorb verschieben (NIE hart löschen) — außer eine ANDERE Zeile referenziert
ihn noch (`cv_export._noch_referenziert`).

P2-18: `_to_pdf_soffice()` killte beim subprocess-Timeout nur die Top-Level-PID; soffice spawnt
bekanntlich Kindprozesse, die als Waisen weiterlaufen konnten. Fix: eigene Prozessgruppe
(`start_new_session=True`) + `os.killpg` beim Timeout (Muster `agent_runner._kill()`, Phase 65).

Isolation (Falle laut tasks/lessons.md: aus PROJECT_ROOT abgeleitete Modulkonstanten werden beim
Import eingefroren): `cv_export.PROJECT_ROOT` wird INLINE in `export()`/`export_cover_letter()`
bei jedem Aufruf frisch aus dem Modul-Attribut gelesen — ein Monkeypatch auf
`cv_export.PROJECT_ROOT` reicht dafür aus. `cleanup.py` dagegen berechnet `PAPIERKORB`/`DATA`/
`OUTPUTS` beim IMPORT einmalig aus `cleanup.PROJECT_ROOT` — hier müssen `PROJECT_ROOT` UND
`PAPIERKORB` einzeln gepatcht werden (Muster wie `test_response_rate_dedup.py` mit
`export_excel.EXPORT_DIR`), sonst würde ein Test versehentlich in den echten
`data/papierkorb/` schreiben. Niemals echte Dateien unter `outputs/` anfassen — jeder Test
arbeitet ausschließlich auf `tmp_path` als Fake-Projekt-Root.

`to_pdf()` wird in den P2-9/P2-10-Tests auf einen Dummy-Stub gemonkeypatcht (kein echtes
LibreOffice nötig, hier nicht Gegenstand des Tests). Der P2-18-Test braucht ebenfalls KEINEN
echten LibreOffice-Lauf: er erzwingt den Timeout-Pfad per Monkeypatch auf `subprocess.Popen`,
spawnt aber einen ECHTEN Eltern+Kind-Prozessbaum (Python-Subprozesse), damit `os.killpg`
etwas Reales zu killen hat — nur so beweist der Test, dass wirklich die GANZE Gruppe stirbt,
nicht nur, dass irgendeine Kill-Funktion aufgerufen wurde.

App-Module (app.*/pipeline.*) werden laut conftest.py-Konvention NIE auf Modulebene importiert.
"""
import os
import subprocess
import sys
import time

import pytest


# ── gemeinsame Test-Helfer ───────────────────────────────────────────────────────────────────
def _docx_mit_text(pfad, absaetze):
    """Minimal-valide .docx mit den gegebenen Absätzen (für Text-/Sprach-Erkennung, P2-9/P2-10)."""
    from docx import Document

    doc = Document()
    for text in absaetze:
        doc.add_paragraph(text)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(pfad))


def _fake_to_pdf(docx_path, pdf_path):
    """Ersetzt `cv_export.to_pdf()` in P2-9/P2-10-Tests: kein echtes LibreOffice nötig, legt nur
    eine Dummy-PDF an derselben Stelle ab und meldet Erfolg. Das eigentliche PDF-Erzeugen ist
    P2-18s eigener, separat getesteter Code — hier soll er nicht mitlaufen (Isolation/Tempo)."""
    from pathlib import Path

    Path(pdf_path).parent.mkdir(parents=True, exist_ok=True)
    Path(pdf_path).write_bytes(b"%PDF-1.4 dummy\n")
    return True, None


def _patch_project_root(monkeypatch, tmp_path):
    """cv_export UND cleanup auf denselben Fake-Root umbiegen (s. Moduldocstring — cleanup
    friert PAPIERKORB/DATA beim Import ein, PROJECT_ROOT allein zu patchen reicht dort NICHT)."""
    from pipeline import cleanup, cv_export

    monkeypatch.setattr(cv_export, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cleanup, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cleanup, "PAPIERKORB", tmp_path / "data" / "papierkorb")
    return cv_export, cleanup


# ═══════════════════════════════════════════════════════════════════════════════════════════
# P2-9 — Anschreiben-Sprache aus dem TATSÄCHLICHEN Text
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_export_cover_letter_erkennt_englisch_ohne_gesetzte_sprache(session, tmp_path, monkeypatch):
    """DER Kernbeweis von P2-9: Der Nutzer nutzt den Inline-Editor (setzt `cover_letter_language`
    NIE) für ein tatsächlich englisches Anschreiben. Die alte Heuristik prüfte nur den Namen der
    Zwischendatei (`_raw_<id>.docx`, NIE "_EN") -> wäre IMMER "DE" gewesen, Datei UND DB dauerhaft
    falsch beschriftet. OHNE den Fix schlägt dieser Test fehl (lang=="DE", Dateiname endet auf
    "_DE.docx")."""
    from app.models import Application, Company, Job

    cv_export, _cleanup = _patch_project_root(monkeypatch, tmp_path)
    monkeypatch.setattr(cv_export, "to_pdf", _fake_to_pdf)

    company = Company(name="Anglo Corp P2-9")
    session.add(company)
    session.commit()
    session.refresh(company)
    job = Job(company_id=company.id, company_name=company.name, title="Head of CS",
              status="Beworben", found_date="2026-07-26", dedup_key="p2-9|1")
    session.add(job)
    session.commit()
    session.refresh(job)

    englischer_text = (
        "Max Mustermann\nMusterstr. 1, 12345 Musterstadt\n\n"
        "Musterstadt, 26 July 2026\n\n"
        "Application as Head of Customer Success\n\n"
        "Dear Hiring Team,\n\n"
        "I am writing to apply for this role.\n\n"
        "Kind regards,\nMax Mustermann"
    )
    application = Application(job_id=job.id, status="Beworben", cover_letter_text=englischer_text)
    session.add(application)
    session.commit()
    session.refresh(application)

    # Mirror des echten Ablaufs (cover_letter_render.render_and_export): die Zwischendatei heißt
    # IMMER "_raw_<id>.docx" -- das ist die exakte Ursache des Bugs (nie "_EN" im Namen).
    raw_path = tmp_path / "outputs" / "anschreiben" / f"_raw_{application.id}.docx"
    _docx_mit_text(raw_path, englischer_text.split("\n\n"))
    application.cover_letter_path = f"outputs/anschreiben/_raw_{application.id}.docx"
    application.cover_letter_language = None     # Inline-Editor setzt sie NIE
    session.add(application)
    session.commit()

    result = cv_export.export_cover_letter(application.id)   # KEIN language-Parameter

    assert result["docx"].endswith("_EN.docx"), f"Dateiname muss auf _EN.docx enden: {result['docx']}"
    session.refresh(application)
    assert application.cover_letter_language == "EN"


def test_export_cover_letter_liest_sprache_aus_docx_wenn_kein_textfeld(session, tmp_path, monkeypatch):
    """P2-9-Ergänzung: ein ALTES Anschreiben ohne `cover_letter_text` (vor Phase 48) hat keinen
    Text im DB-Feld — die Erkennung muss dann auf den tatsächlichen Absatztext der .docx
    ausweichen, statt sofort (mangels Textfeld) auf "DE" zu geben."""
    from app.models import Application, Company, Job

    cv_export, _cleanup = _patch_project_root(monkeypatch, tmp_path)
    monkeypatch.setattr(cv_export, "to_pdf", _fake_to_pdf)

    company = Company(name="Altbestand Ltd P2-9")
    session.add(company)
    session.commit()
    session.refresh(company)
    job = Job(company_id=company.id, company_name=company.name, title="Director",
              status="Beworben", found_date="2026-07-26", dedup_key="p2-9|2")
    session.add(job)
    session.commit()
    session.refresh(job)

    application = Application(job_id=job.id, status="Beworben")   # KEIN cover_letter_text
    session.add(application)
    session.commit()
    session.refresh(application)

    raw_path = tmp_path / "outputs" / "anschreiben" / f"_raw_{application.id}.docx"
    _docx_mit_text(raw_path, ["Max Mustermann", "Dear Sir or Madam,", "Body text.", "Best regards,"])
    application.cover_letter_path = f"outputs/anschreiben/_raw_{application.id}.docx"
    session.add(application)
    session.commit()

    result = cv_export.export_cover_letter(application.id)

    assert result["docx"].endswith("_EN.docx")


def test_export_cover_letter_bleibt_ohne_indiz_bei_deutsch(session, tmp_path, monkeypatch):
    """Erfolgsfall/Q5-Gegenprobe: OHNE jedes Sprachindiz (kein Parameter, kein DB-Feld, deutsche
    Grußformel im Text) bleibt der Default weiterhin "DE" — der Fix darf den bisherigen
    Normalfall nicht verändern."""
    from app.models import Application, Company, Job

    cv_export, _cleanup = _patch_project_root(monkeypatch, tmp_path)
    monkeypatch.setattr(cv_export, "to_pdf", _fake_to_pdf)

    company = Company(name="Deutsch GmbH P2-9")
    session.add(company)
    session.commit()
    session.refresh(company)
    job = Job(company_id=company.id, company_name=company.name, title="Head of CS",
              status="Beworben", found_date="2026-07-26", dedup_key="p2-9|3")
    session.add(job)
    session.commit()
    session.refresh(job)

    deutscher_text = (
        "Max Mustermann\nMusterstr. 1, 12345 Musterstadt\n\n"
        "Musterstadt, 26. Juli 2026\n\n"
        "Bewerbung als Head of Customer Success\n\n"
        "Sehr geehrte Damen und Herren,\n\n"
        "hiermit bewerbe ich mich auf die ausgeschriebene Stelle.\n\n"
        "Mit freundlichen Grüßen,\nMax Mustermann"
    )
    application = Application(job_id=job.id, status="Beworben", cover_letter_text=deutscher_text)
    session.add(application)
    session.commit()
    session.refresh(application)

    raw_path = tmp_path / "outputs" / "anschreiben" / f"_raw_{application.id}.docx"
    _docx_mit_text(raw_path, deutscher_text.split("\n\n"))
    application.cover_letter_path = f"outputs/anschreiben/_raw_{application.id}.docx"
    application.cover_letter_language = None
    session.add(application)
    session.commit()

    result = cv_export.export_cover_letter(application.id)

    assert result["docx"].endswith("_DE.docx")
    session.refresh(application)
    assert application.cover_letter_language == "DE"


# ═══════════════════════════════════════════════════════════════════════════════════════════
# P2-10 — verwaiste alte PDF aufräumen (Papierkorb, nicht hart löschen)
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_export_cover_letter_raeumt_alte_pdf_in_papierkorb_bei_umbenennung(session, tmp_path, monkeypatch):
    """DER Kernbeweis von P2-10 (Anschreiben-Seite): eine Titelkorrektur ändert den
    Ziel-Dateinamen — die ALTE PDF darf danach nicht mehr unreferenziert mit veraltetem Inhalt
    in outputs/anschreiben/ liegen bleiben. OHNE den Fix bliebe die alte PDF-Datei unverändert an
    ihrem alten Pfad stehen (dieser Test schlägt dann bei der ersten Assertion fehl)."""
    from app import naming
    from app.models import Application, Company, Job

    cv_export, cleanup = _patch_project_root(monkeypatch, tmp_path)
    monkeypatch.setattr(cv_export, "to_pdf", _fake_to_pdf)

    company = Company(name="Rename Corp P2-10")
    session.add(company)
    session.commit()
    session.refresh(company)
    job = Job(company_id=company.id, company_name=company.name, title="Alter Titel",
              status="Beworben", found_date="2026-07-26", dedup_key="p2-10|1")
    session.add(job)
    session.commit()
    session.refresh(job)

    # "Vorher"-Zustand: als wäre bereits einmal erfolgreich exportiert worden.
    alter_wunsch = naming.cover_letter_filename(company.name, job.title, "DE")
    cover_dir = tmp_path / "outputs" / "anschreiben"
    alte_docx = cover_dir / f"{alter_wunsch}.docx"
    alte_pdf = cover_dir / f"{alter_wunsch}.pdf"
    _docx_mit_text(alte_docx, ["Max Mustermann", "Mit freundlichen Grüßen,"])
    alte_pdf.parent.mkdir(parents=True, exist_ok=True)
    alte_pdf.write_bytes(b"%PDF-1.4 ALTE VERSION\n")

    application = Application(
        job_id=job.id, status="Beworben", cover_letter_language="DE",
        cover_letter_path=f"outputs/anschreiben/{alter_wunsch}.docx",
        cover_letter_pdf_path=f"outputs/anschreiben/{alter_wunsch}.pdf",
    )
    session.add(application)
    session.commit()
    session.refresh(application)

    # Der Nutzer korrigiert den Jobtitel -> neuer Ziel-Dateiname beim nächsten Export.
    job.title = "Neuer Titel"
    session.add(job)
    session.commit()

    result = cv_export.export_cover_letter(application.id)

    neuer_wunsch = naming.cover_letter_filename(company.name, "Neuer Titel", "DE")
    assert neuer_wunsch != alter_wunsch, "Testaufbau fehlerhaft: Titeländerung muss den Zieldateinamen ändern"
    assert result["pdf"] == f"outputs/anschreiben/{neuer_wunsch}.pdf"

    # Kernbeweis: die ALTE PDF liegt NICHT mehr an ihrem alten Ort ...
    assert not alte_pdf.exists()
    # ... sondern im (gepatchten) Papierkorb, NICHT hart gelöscht.
    papierkorb_dateien = list(cleanup.PAPIERKORB.glob("*"))
    assert any(alter_wunsch in p.name for p in papierkorb_dateien), (
        f"Alte PDF nicht im Papierkorb gefunden: {papierkorb_dateien}"
    )


def test_export_raeumt_alte_pdf_in_papierkorb_bei_umbenennung(session, tmp_path, monkeypatch):
    """P2-10-Geschwisterstelle: identischer Befund/Fix auf der CV-Seite (`export()`, nicht
    `export_cover_letter()`) — der Befund nennt ausdrücklich BEIDE Funktionen."""
    from app import naming
    from app.models import Company, CVVersion, Job

    cv_export, cleanup = _patch_project_root(monkeypatch, tmp_path)
    monkeypatch.setattr(cv_export, "to_pdf", _fake_to_pdf)

    company = Company(name="Rename CV Corp P2-10")
    session.add(company)
    session.commit()
    session.refresh(company)
    job = Job(company_id=company.id, company_name=company.name, title="Alter CV Titel",
              status="Beworben", found_date="2026-07-26", dedup_key="p2-10|cv-1")
    session.add(job)
    session.commit()
    session.refresh(job)

    alter_wunsch = naming.cv_filename(company.name, job.title, "DE")
    tailored_dir = tmp_path / "outputs" / "cv"
    alte_docx = tailored_dir / f"{alter_wunsch}.docx"
    alte_pdf = tailored_dir / f"{alter_wunsch}.pdf"
    _docx_mit_text(alte_docx, ["Max Mustermann", "EXECUTIVE SUMMARY"])
    alte_pdf.parent.mkdir(parents=True, exist_ok=True)
    alte_pdf.write_bytes(b"%PDF-1.4 ALTE CV VERSION\n")

    cv = CVVersion(job_id=job.id, language="DE", kind="tailored", status="fertig",
                  file_path=f"outputs/cv/{alter_wunsch}.docx", pdf_path=f"outputs/cv/{alter_wunsch}.pdf")
    session.add(cv)
    session.commit()
    session.refresh(cv)

    job.title = "Neuer CV Titel"
    session.add(job)
    session.commit()

    result = cv_export.export(cv.id)

    neuer_wunsch = naming.cv_filename(company.name, "Neuer CV Titel", "DE")
    assert neuer_wunsch != alter_wunsch
    assert result["pdf"] == f"outputs/cv/{neuer_wunsch}.pdf"
    assert not alte_pdf.exists()
    papierkorb_dateien = list(cleanup.PAPIERKORB.glob("*"))
    assert any(alter_wunsch in p.name for p in papierkorb_dateien)


def test_noch_referenziert_verhindert_papierkorb_verschiebung(session, tmp_path, monkeypatch):
    """Sicherheitsnetz-Beweis für `_noch_referenziert`: referenziert eine ANDERE Zeile denselben
    alten PDF-Pfad noch (Stand-in für eine Dublette/manuelle DB-Änderung), darf das P2-10-Aufräumen
    ihn NICHT in den Papierkorb verschieben — sonst würde eine noch gebrauchte Datei unter den
    Füßen weggezogen."""
    from app import naming
    from app.models import Company, CVVersion, Job

    cv_export, cleanup = _patch_project_root(monkeypatch, tmp_path)
    monkeypatch.setattr(cv_export, "to_pdf", _fake_to_pdf)

    company = Company(name="Shared Pdf Corp P2-10")
    session.add(company)
    session.commit()
    session.refresh(company)
    job = Job(company_id=company.id, company_name=company.name, title="Alter Titel Shared",
              status="Beworben", found_date="2026-07-26", dedup_key="p2-10|shared-1")
    session.add(job)
    session.commit()
    session.refresh(job)

    alter_wunsch = naming.cv_filename(company.name, job.title, "DE")
    tailored_dir = tmp_path / "outputs" / "cv"
    alte_docx = tailored_dir / f"{alter_wunsch}.docx"
    alte_pdf = tailored_dir / f"{alter_wunsch}.pdf"
    _docx_mit_text(alte_docx, ["Max Mustermann"])
    alte_pdf.parent.mkdir(parents=True, exist_ok=True)
    alte_pdf.write_bytes(b"%PDF-1.4 GETEILTE VERSION\n")

    cv = CVVersion(job_id=job.id, language="DE", kind="tailored", status="fertig",
                  file_path=f"outputs/cv/{alter_wunsch}.docx", pdf_path=f"outputs/cv/{alter_wunsch}.pdf")
    # Künstliche Fremdreferenz: eine ANDERE CVVersion-Zeile "braucht" denselben alten PDF-Pfad
    # noch (nur die DB-Referenz zählt für _noch_referenziert, die Datei muss dafür nicht existieren).
    fremd = CVVersion(job_id=job.id, language="EN", kind="tailored", status="fertig",
                      file_path=f"outputs/cv/{alter_wunsch}_fremd.docx",
                      pdf_path=f"outputs/cv/{alter_wunsch}.pdf")
    session.add(cv)
    session.add(fremd)
    session.commit()
    session.refresh(cv)

    job.title = "Neuer Titel Shared"
    session.add(job)
    session.commit()

    cv_export.export(cv.id)

    # Die alte PDF darf NICHT verschoben worden sein -- die fremde Zeile braucht sie noch.
    assert alte_pdf.exists()
    assert not cleanup.PAPIERKORB.exists() or not list(cleanup.PAPIERKORB.glob("*"))


# ═══════════════════════════════════════════════════════════════════════════════════════════
# P2-18 — soffice-Timeout killt die GANZE Prozessgruppe, keine Waisen
# ═══════════════════════════════════════════════════════════════════════════════════════════
class _FakeSofficeProc:
    """Stand-in für das `Popen`-Objekt, das `_to_pdf_soffice()` normalerweise von
    `subprocess.Popen(...)` bekäme. `pid` zeigt auf einen ECHTEN (Test-)Prozess, `communicate()`
    simuliert den Timeout sofort (kein 180-s-Warten nötig, Q3)."""

    def __init__(self, echter_proc):
        self.pid = echter_proc.pid
        self._echter_proc = echter_proc

    def communicate(self, timeout=None):
        raise subprocess.TimeoutExpired(cmd="soffice", timeout=timeout)

    def wait(self):
        return self._echter_proc.wait()


def _warte_bis_tot(pid: int, timeout: float = 3.0) -> bool:
    """Bounded Poll: True, sobald `pid` nicht mehr existiert. Kein fixes `sleep` — SIGKILL an
    eine Prozessgruppe trifft alle Mitglieder quasi gleichzeitig, aber das tatsächliche Einsammeln
    eines (durch den Tod seines eigenen Elternprozesses) verwaisten Kindes durch launchd kann ein
    paar Millisekunden brauchen. Ein knapper, wiederholter Check ist robuster als ein einzelner
    Check direkt nach dem Kill."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.02)
    return False


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only: killpg-Prozessgruppen-Beweis (Timeout-Kill-Pfad ist unter Windows offene Grenze, s. docs/SETUP-WINDOWS.md)")
def test_to_pdf_soffice_timeout_killt_die_gesamte_prozessgruppe(monkeypatch, tmp_path):
    """DER Kernbeweis von P2-18: soffice spawnt Kindprozesse — ein Timeout darf nur die
    Top-Level-PID ODER die ganze Gruppe killen. Wir bauen einen ECHTEN Eltern+Kind-Prozessbaum
    (zwei Python-Subprozesse; das Kind bleibt bewusst OHNE eigenes `start_new_session` in der
    Prozessgruppe des Elternprozesses, exakt wie ein von soffice selbst gestarteter Helfer) und
    erzwingen den Timeout-Pfad per Monkeypatch auf `subprocess.Popen` (Q3 — kein echtes
    LibreOffice nötig). OHNE den Fix (altes `subprocess.run(..., timeout=180)`, das nur die
    Top-Level-PID killt) würde der Kindprozess als Waise weiterlaufen — `_warte_bis_tot(kind_pid)`
    schlüge dann nach 3 s fehl."""
    from pipeline import cv_export

    eltern_script = tmp_path / "eltern.py"
    eltern_script.write_text(
        "import subprocess, sys, time\n"
        "kind = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "print(kind.pid, flush=True)\n"
        "time.sleep(60)\n"
    )

    real_popen = subprocess.Popen
    gespawnt = {}

    def fake_popen(*args, **kwargs):
        # _to_pdf_soffice ruft Popen mit dem soffice-Kommando auf -- das ignorieren wir bewusst
        # und spawnen stattdessen unseren eigenen, kontrollierten Eltern+Kind-Baum, DAMIT
        # os.killpg() etwas Reales zu killen hat. start_new_session=True hier ist exakt die
        # Eigenschaft, die der echte Code jetzt auch beim soffice-Spawn setzt.
        eltern = real_popen(
            [sys.executable, str(eltern_script)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=True,
        )
        kind_pid = int(eltern.stdout.readline().strip())
        gespawnt["eltern_pid"] = eltern.pid
        gespawnt["kind_pid"] = kind_pid
        gespawnt["eltern_proc"] = eltern
        return _FakeSofficeProc(eltern)

    monkeypatch.setattr(cv_export.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cv_export, "_soffice_bin", lambda: "/fake/soffice/bin")

    try:
        ok, err = cv_export._to_pdf_soffice(str(tmp_path / "in.docx"), str(tmp_path / "out.pdf"))

        # Die Timeout-Fehlermeldung MUSS wortgleich bleiben (ausdrückliche Vorgabe der Aufgabe).
        assert ok is False
        assert err == "LibreOffice-Konvertierung nach 180 s abgebrochen (Timeout)."

        # Kernbeweis: NICHT nur der Eltern-, sondern auch der (von ihm gestartete) Kindprozess
        # ist tot -- das ist genau der Unterschied zwischen "Top-Level-PID killen" (alt, Waise
        # möglich) und "Prozessgruppe killen" (neu, P2-18).
        assert _warte_bis_tot(gespawnt["eltern_pid"]), "Elternprozess lebt noch"
        assert _warte_bis_tot(gespawnt["kind_pid"]), "Kindprozess lebt noch -- Waise trotz Fix!"
    finally:
        # Aufräumen, auch falls eine Assertion oben fehlschlägt (Muster test_prozess_tracking.py).
        for pid in (gespawnt.get("eltern_pid"), gespawnt.get("kind_pid")):
            if pid:
                try:
                    os.kill(pid, 9)
                except (ProcessLookupError, PermissionError):
                    pass
        if gespawnt.get("eltern_proc"):
            try:
                gespawnt["eltern_proc"].wait(timeout=5)
            except Exception:
                pass


def test_to_pdf_soffice_erfolgsfall_bleibt_unveraendert(monkeypatch, tmp_path):
    """Q5-Gegenprobe: der Normalfall (soffice läuft durch, kein Timeout) muss nach der
    Popen-Umstellung IDENTISCH funktionieren wie vorher — echte Konvertierung über den echten
    `to_pdf()`-Pfad wird separat im PDF-Smoke-Test (Nicht-pytest, s. Abschlussbericht) bewiesen;
    hier wird nur die Popen-Steuerungslogik selbst (Rückgabewerte, kein Hängenbleiben) mit einem
    gefakten, aber sofort erfolgreichen Prozess geprüft."""
    from pipeline import cv_export

    monkeypatch.setattr(cv_export, "_soffice_bin", lambda: "/fake/soffice/bin")

    def fake_popen(args, **kwargs):
        outdir = args[args.index("--outdir") + 1]
        docx_abs = args[-1]
        produced = __import__("pathlib").Path(outdir) / (
            __import__("pathlib").Path(docx_abs).stem + ".pdf"
        )
        produced.write_bytes(b"%PDF-1.4 erfolgreich\n")

        class _Erfolg:
            pid = 999999
            returncode = 0

            def communicate(self, timeout=None):
                return "", ""

            def wait(self):
                return 0

        return _Erfolg()

    monkeypatch.setattr(cv_export.subprocess, "Popen", fake_popen)

    docx = tmp_path / "input.docx"
    docx.write_bytes(b"dummy docx")
    pdf = tmp_path / "output.pdf"

    ok, err = cv_export._to_pdf_soffice(str(docx), str(pdf))

    assert ok is True
    assert err is None
    assert pdf.exists()
    assert pdf.read_bytes() == b"%PDF-1.4 erfolgreich\n"


# ═══════════════════════════════════════════════════════════════════════════════════════════
# Phase 71A (Name aus dem Profil) — Fußzeile nutzt jetzt pipeline.user_profile.user_name()
# statt einer eigenen, jetzt entfernten _name_aus_profil()-Kopie ("ein Leser, eine Wahrheit").
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_nachbearbeiten_fusszeile_nutzt_user_profile_user_name(tmp_path, monkeypatch):
    """Beweis der Verdrahtung: ein gemockter Name aus pipeline.user_profile.user_name() landet
    wortwörtlich in der Fußzeile. _nachbearbeiten() hängt an keiner Stelle mehr von einer
    eigenen Profil-Leselogik ab (die alte _name_aus_profil() wurde ersatzlos entfernt)."""
    from pipeline import cv_export, user_profile
    from docx import Document

    monkeypatch.setattr(user_profile, "user_name", lambda: "Testname Mock")

    docx_path = tmp_path / "kandidat.docx"
    _docx_mit_text(docx_path, ["EXECUTIVE SUMMARY", "Ein Beispieltext."])

    fehler, warnung = cv_export._nachbearbeiten(docx_path)  # Phase 76: (fehler, warnung)-Tupel
    assert fehler is None
    # Die synthetische Zwei-Absatz-docx hat keine Tab-Ankerzeilen → die neue Warnung greift.
    assert warnung is not None and "0 Stationen" in warnung

    doc = Document(str(docx_path))
    fusszeile_text = doc.sections[0].footer.paragraphs[0].text
    assert "Testname Mock" in fusszeile_text
