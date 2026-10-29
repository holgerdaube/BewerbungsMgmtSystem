"""Tests für den Favicon-Data-URI in `pipeline/coach_export.py` (Phase 82, Wunsch
12.08.: "Zusätzlich benötigt die Webseite natürlich auch ein Favicon"). Das App-Icon (seit P2-72
das Icon des geltenden Designs, Vorgabe `assets/design/icon-32.png`) landet als Base64-Data-URI im `<head>` jeder generierten
Seite UND jedes kopierten Artefakts — bewusst OHNE zusätzliche Datei im Export, damit die
Whitelist-Regex in `test_coach_export_sperrliste.py` unangetastet bleibt (I3); diese Datei
prüft NUR den Favicon-Mechanismus, nicht die Sperrliste selbst (die Abnahme läuft beide Dateien
zusammen, s. Bau-Spec Abschnitt 3.4).

Fixture-Muster aus `test_coach_export_sperrliste.py` übernommen (eigene, schlankere Variante
hier — nur was für den Favicon-Nachweis nötig ist). Kein app.*/pipeline.*-Import auf
Modulebene (conftest-Konvention); `_EXPORT_DIR` je Test per monkeypatch auf tmp_path."""
import uuid
from datetime import date


def _fixture(session, tmp_path, monkeypatch):
    from app.db import DATA_DIR
    from app.models import Company, CVVersion, Job
    from pipeline import coach_export

    monkeypatch.setattr(coach_export, "_EXPORT_DIR", tmp_path / "coach_site")

    (DATA_DIR / "company_fit").mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex[:8]

    # CompanyFit-Report MIT <head> — bekommt beim Kopieren den Favicon-Link eingesetzt.
    fit = DATA_DIR / "company_fit" / f"2026_08_12_CompanyFit_FaviconTest_{suffix}.html"
    fit.write_text(
        "<html><head><title>CompanyFit</title></head><body>Inhalt</body></html>",
        encoding="utf-8")
    # Match-Report OHNE echtes <head> — enthält bewusst "<header class=\"head\">" im Body
    # (Regressionsfall: eine naive Regex "<head[^>]*>" würde DAS fälschlich als <head>-Tag
    # erkennen, weil "<head" ein reiner Textpräfix von "<header" ist). Muss byte-identisch
    # bleiben.
    match = DATA_DIR / "company_fit" / f"2026_08_12_Match_FaviconTest_{suffix}.html"
    match.write_text(
        '<html><body><header class="head">Kopfzeile</header>'
        "<p>Nur Body, kein echtes head-Tag.</p></body></html>",
        encoding="utf-8")

    comp = Company(name=f"FaviconTest AG {suffix}", fit_analysis_path=f"data/company_fit/{fit.name}")
    session.add(comp)
    session.commit()
    session.refresh(comp)

    job = Job(company_name=f"FaviconTest AG {suffix}", title="Director PS", status="Beworben",
              found_date=date.today().isoformat(), dedup_key=f"favicon|{suffix}",
              url=f"https://example.invalid/{uuid.uuid4().hex[:6]}",
              company_id=comp.id, match_score=5)
    session.add(job)
    session.commit()
    session.refresh(job)

    session.add(CVVersion(job_id=job.id, match_dashboard_path=f"data/company_fit/{match.name}"))
    session.commit()
    return coach_export, fit, match


def test_favicon_in_den_drei_generierten_seiten(session, monkeypatch, tmp_path):
    coach_export, *_ = _fixture(session, tmp_path, monkeypatch)
    coach_export.export()
    ordner = tmp_path / "coach_site"
    for name in ("index.html", "stellen.html", "absagen.html"):
        text = (ordner / name).read_text(encoding="utf-8")
        assert text.count("data:image/png;base64,") == 1, f"{name}: erwartet genau EIN Favicon-Icon"
        assert '<link rel="icon" type="image/png" href="data:image/png;base64,' in text
        # Spec 3.3: der Link steht VOR <title> im <head>.
        assert text.index("data:image/png;base64,") < text.index("<title>")


def test_favicon_in_kopierter_artefakt_seite(session, monkeypatch, tmp_path):
    coach_export, fit, _match = _fixture(session, tmp_path, monkeypatch)
    coach_export.export()
    kopie = tmp_path / "coach_site" / "artefakte" / fit.name
    assert kopie.is_file()
    text = kopie.read_text(encoding="utf-8")
    assert text.count("data:image/png;base64,") == 1
    assert "<title>CompanyFit</title>" in text  # Ursprungsinhalt bleibt vollständig erhalten


def test_artefakt_ohne_head_bleibt_byte_identisch(session, monkeypatch, tmp_path):
    coach_export, _fit, match = _fixture(session, tmp_path, monkeypatch)
    coach_export.export()
    kopie = tmp_path / "coach_site" / "artefakte" / match.name
    assert kopie.is_file()
    assert kopie.read_bytes() == match.read_bytes()
    assert "data:image/png;base64," not in kopie.read_text(encoding="utf-8")
