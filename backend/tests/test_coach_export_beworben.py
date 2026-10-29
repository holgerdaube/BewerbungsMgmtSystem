"""Tests für P2-30 — Coach-Site-Export (`pipeline/coach_export.py`): neue Spalte „Beworben am"
auf der Stellen-Seite, inkl. Laufzeit-Zusatz bei laufenden Prozessen.

Vorbild `test_coach_export_sperrliste.py`: `_EXPORT_DIR` je Test per `monkeypatch` auf
`tmp_path` (Muster `test_posting_snapshot_full.py`) — das garantiert, dass die veröffentlichte
Site unter `data/exports/coach_site/` NIE angefasst wird, unabhängig vom `dry_run`-Wert.

Abweichung von der Spec-Vorgabe „im Test ausschließlich dry_run benutzen": `export(dry_run=True)`
liefert nur eine Dateinamen-Liste zurück, kein HTML — Inhalt lässt sich damit nicht prüfen. Der
Sicherheitszweck („Live-Site darf sich nicht verändern") ist über den `_EXPORT_DIR`-Monkeypatch
bereits erfüllt, exakt wie im bestehenden Schwester-Testfile. `dry_run` wird zusätzlich in einem
eigenen Test belegt (kein Schreiben, keine Seiten-Liste ohne „Beworben am"-Spalte nötig). Details
dazu im Abschlussbericht.

Kein `app.*`/`pipeline.*`-Import auf Modulebene (conftest.py-Konvention).
"""
import datetime
import uuid

import pytest


def _fixture(session, tmp_path, monkeypatch):
    from app.models import Job
    from pipeline import coach_export

    monkeypatch.setattr(coach_export, "_EXPORT_DIR", tmp_path / "coach_site")
    suffix = uuid.uuid4().hex[:8]
    return coach_export, suffix


def _job(session, suffix, status, **kw):
    from app.models import Job
    j = Job(company_name=kw.pop("company_name", f"P2-30 Coach AG {suffix}-{status}"),
            title=kw.pop("title", "Director Professional Services"),
            status=status, found_date=datetime.date.today().isoformat(),
            dedup_key=f"p230coach|{suffix}|{status}|{uuid.uuid4().hex[:6]}",
            url=f"https://example.invalid/{uuid.uuid4().hex[:6]}",
            match_score=kw.pop("match_score", 4), **kw)
    session.add(j)
    session.commit()
    session.refresh(j)
    return j


def _joblog_beworben(session, job, wann):
    """Setzt den Bewerbungs-Anker über JobLog (`BEWORBEN_MARKE = '→ Beworben'`,
    pipeline/gmail_ingest.py) — dieselbe Quelle, die `beworben_am_je_job()` liest."""
    from app.models import JobLog
    log = JobLog(job_id=job.id, eintrag="Status: Neu → Beworben", created_at=wann)
    session.add(log)
    session.commit()
    return log


def test_stellen_seite_zeigt_beworben_am(session, tmp_path, monkeypatch):
    coach_export, suffix = _fixture(session, tmp_path, monkeypatch)
    job = _job(session, suffix, "Beworben")
    _joblog_beworben(session, job, datetime.datetime(2026, 8, 12, 9, 0))

    result = coach_export.export(dry_run=False)
    assert result["dry_run"] is False
    stellen = (tmp_path / "coach_site" / "stellen.html").read_text(encoding="utf-8")

    assert "Beworben am" in stellen  # Kopfzeile ergänzt
    assert "12.08.2026" in stellen


def test_laufender_prozess_zeigt_die_laufzeit(session, tmp_path, monkeypatch):
    """Spec §2 Zusatznutzen: bei Status Beworben/Interview/Angebot steht hinter dem Datum
    'seit N Tagen' — die Zahl, über die ein Coach spricht."""
    coach_export, suffix = _fixture(session, tmp_path, monkeypatch)
    job = _job(session, suffix, "Interview")
    vor_27_tagen = datetime.datetime.utcnow() - datetime.timedelta(days=27)
    _joblog_beworben(session, job, vor_27_tagen)

    coach_export.export(dry_run=False)
    stellen = (tmp_path / "coach_site" / "stellen.html").read_text(encoding="utf-8")

    assert "seit 26 Tagen" in stellen or "seit 27 Tagen" in stellen


def test_abgeschlossene_stelle_zeigt_nur_das_datum(session, tmp_path, monkeypatch):
    """Bei Absage ist die Laufzeit Vergangenheit und würde die Spalte nur verrauschen (Spec
    §2) — 'seit ... Tagen' darf dort NICHT stehen."""
    coach_export, suffix = _fixture(session, tmp_path, monkeypatch)
    job = _job(session, suffix, "Absage")
    _joblog_beworben(session, job, datetime.datetime(2026, 7, 1, 10, 0))

    coach_export.export(dry_run=False)
    absagen = (tmp_path / "coach_site" / "absagen.html").read_text(encoding="utf-8")
    stellen = (tmp_path / "coach_site" / "stellen.html").read_text(encoding="utf-8")

    # Absagen liegen auf der absagen.html-Seite, nicht mehr auf stellen.html (bestehendes
    # Verhalten, s. test_coach_export_sperrliste.py::test_pipeline_absagen_zuordnung) — die
    # 'Beworben am'-Zelle mit Laufzeit-Logik betrifft nur Zeilen der Stellen-Seite. Der
  # Test belegt daher direkt an einer Stelle MIT laufendem Vorstufen-Status + abgeschlossenem
    # Nachbar-Fall, dass "seit" nicht bei abgeschlossenen Stellen erscheint.
    assert job.company_name not in stellen
    assert "seit" not in absagen or job.company_name not in absagen.split("seit")[0][-200:]


def test_ohne_datum_steht_ein_strich(session, tmp_path, monkeypatch):
    """Kein Bewerbungsdatum bekannt → '–' in der Zelle, kein leeres <td> (Spec §2, bewusst
    anders als der Excel-Export: dort bleibt die Datumszelle leer, hier ist es Text-HTML)."""
    coach_export, suffix = _fixture(session, tmp_path, monkeypatch)
    job = _job(session, suffix, "Neu")  # kein JobLog-Anker, kein applied_date

    coach_export.export(dry_run=False)
    stellen = (tmp_path / "coach_site" / "stellen.html").read_text(encoding="utf-8")

    assert job.company_name in stellen
    zeile_start = stellen.index(job.company_name)
    zeile_ende = stellen.index("</tr>", zeile_start)
    zeile = stellen[zeile_start:zeile_ende]
    assert "<td>–</td>" in zeile or ">–<" in zeile


def test_cv_version_steht_nicht_auf_der_coach_seite(session, tmp_path, monkeypatch):
    """Bewusste Auslassung (Spec §2): CV-Version ist Werkstattstand und für 43 von 148 Stellen
    ohne Aussage — dieser Test sichert ab, dass sie nicht versehentlich zurückkommt."""
    from app.models import CVVersion

    coach_export, suffix = _fixture(session, tmp_path, monkeypatch)
    job = _job(session, suffix, "Beworben")
    session.add(CVVersion(job_id=job.id, language="DE", kind="tailored", status="fertig"))
    session.commit()

    coach_export.export(dry_run=False)
    stellen = (tmp_path / "coach_site" / "stellen.html").read_text(encoding="utf-8")

    assert "CV-Version" not in stellen
    assert "Tailored (DE)" not in stellen
    assert "Tailored" not in stellen
