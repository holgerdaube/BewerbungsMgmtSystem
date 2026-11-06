#!/usr/bin/env python3
"""Deep-Dive-Artefakte an eine Stelle anbinden.

Claude-in-the-Loop erzeugt die Artefakte mit den bestehenden Skills
(company-fit-analysis → Firmen-Dashboard HTML, cv-job-match → angepasste .docx +
Match-Dashboard + ATS-Scan). Dieser Modul registriert sie deterministisch in der DB,
sodass die Web-App sie am Job-Detail verlinkt.

CLI:
    cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.deepdive <deepdive.json>

deepdive.json:
    {
      "job_id": 1,
      "company_fit_path": "data/company_fit/beispiel_gmbh.html",       # optional
      "fit_ampel": "gruen",                                    # optional, nur mit company_fit_path (gruen|gelb|rot)
      "cv": {                                                  # optional
        "language": "EN", "kind": "tailored",
        "file_path": "outputs/cv/2026_CV_MaxMustermann_v8_EN_Beispiel.docx",
        "ats_score": 92, "match_score100": 78,
        "match_dashboard_path": "data/company_fit/beispiel_gmbh_match.html",
        "ats_scan_path": "data/company_fit/beispiel_gmbh_ats.html"
      },
      "posting_path": "data/job_postings/Stellenausschreibung_2026_07_11_beispiel_gmbh_….html",  # optional (Phase 18)
      "next_step": "Bewerben – CV liegt bereit"                # optional
    }
"""
import datetime
import json
import sys
from pathlib import Path

from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import Company, CVVersion, Job
from pipeline import bewerbungssprache

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Bewerbung_Mgmt_System/


def _rel(path):
    """Pfad relativ zum Projekt-Root speichern (portabel)."""
    if not path:
        return None
    p = Path(path)
    if p.is_absolute():
        try:
            return str(p.relative_to(PROJECT_ROOT))
        except ValueError:
            return str(p)
    return str(path)


_FIT_AMPEL_WERTE = {"gruen", "gelb", "rot"}


def _sprache(language):
    """`CVVersion.language` einheitlich in Großbuchstaben (`FR`, `en-US` → `EN`). Das Modell setzt das Kürzel
    mal klein, mal groß; Anzeige, Dateiname und Fußzeile vertragen beides, ein einheitlicher Wert hält
    Auswertungen einfach. Fehlt die Angabe, bleibt sie leer (Altbestand), Altwerte werden nicht migriert."""
    return bewerbungssprache.normiere_code(language)


def register(job_id, company_fit_path=None, cv=None, next_step=None, posting_path=None, fit_ampel=None):
    if fit_ampel and fit_ampel not in _FIT_AMPEL_WERTE:
        raise ValueError(f"fit_ampel muss gruen|gelb|rot sein, nicht {fit_ampel!r}")
    init_db()
    out = {"job_id": job_id}
    cv_row_id = None
    with Session(engine) as s:
        job = s.get(Job, job_id)
        if not job:
            raise SystemExit(f"Job {job_id} nicht gefunden")

        # Snapshot der Stellenausschreibung (Phase 18) — Feld am JOB, nicht an der Company
        # (die Anzeige gehört zur Stelle). Erneuter Lauf → neue Datei, Feld zeigt auf die neueste.
        if posting_path:
            job.posting_snapshot_path = _rel(posting_path)
            out["posting_snapshot"] = job.posting_snapshot_path

        if company_fit_path and job.company_id:
            comp = s.get(Company, job.company_id)
            comp.fit_analysis_path = _rel(company_fit_path)
            if fit_ampel:                    # Phase 24 F: nur zusammen mit company_fit_path sinnvoll
                comp.fit_ampel = fit_ampel
                out["fit_ampel"] = fit_ampel
            comp.updated_at = datetime.datetime.utcnow()
            s.add(comp)
            out["company_fit"] = comp.fit_analysis_path

        if cv:
            row = CVVersion(
                job_id=job_id,
                language=_sprache(cv.get("language")),
                kind=cv.get("kind", "tailored"),
                file_path=_rel(cv.get("file_path")),
                ats_score=cv.get("ats_score"),
                match_score100=cv.get("match_score100"),
                match_dashboard_path=_rel(cv.get("match_dashboard_path")),
                ats_scan_path=_rel(cv.get("ats_scan_path")),
            )
            s.add(row)
            s.flush()
            cv_row_id = row.id
            out["cv_version_id"] = cv_row_id

        if next_step:
            job.next_step = next_step
        job.updated_at = datetime.datetime.utcnow()
        s.add(job)
        s.commit()

    # CV-Export (Umbenennung nach Konvention + PDF) NACH commit und AUSSERHALB der
    # Session: cv_export.export() öffnet eine eigene Session — so ist die neue Row
    # sichtbar und es gibt keinen SQLite-Schreib-Lock-Deadlock. Export-Fehler dürfen
    # die Registrierung NIE abbrechen.
    if cv_row_id is not None:
        try:
            from pipeline import cv_export
            out["export"] = cv_export.export(cv_row_id)
        except Exception as e:  # noqa: BLE001 — Registrierung bleibt gültig
            out["export_fehler"] = str(e)
    return out


# --- Editier-Checkpoint (Phase 46 Stufe B) ─────────────────────────────────────────────────
# `register()` oben bleibt UNVERÄNDERT (job-deepdive/firma-pruefen nutzen weiter den kompletten
# Ein-Klick-Flow) — die beiden Funktionen hier sind der GESPLITTETE Weg für cv-match/cv-erstellen.
def register_entwurf(job_id, cv: dict) -> dict:
    """cv-match: legt eine ENTWURF-CVVersion an (status=entwurf) — Match-Dashboard ist fertig,
    aber NOCH KEIN `cv_export.export()` (kein Umbenennen, kein PDF, s. Design-Entscheidung 3 —
    das passiert erst bei `cv_fertigstellen`/cv-erstellen). `entwurf_text` wird HIER aus der
    (noch beliebig benannten) `.docx` extrahiert (`cv_export.entwurf_extrahieren`)."""
    init_db()
    with Session(engine) as s:
        job = s.get(Job, job_id)
        if not job:
            raise SystemExit(f"Job {job_id} nicht gefunden")

        from pipeline import cv_export
        docx_path = (PROJECT_ROOT / _rel(cv["file_path"])).resolve()
        if not docx_path.exists():
            raise SystemExit(f"Entwurfsdatei fehlt: {cv['file_path']}")
        entwurf_text = cv_export.entwurf_extrahieren(docx_path)

        # Phase 55 — Keyword-Protokoll Methodik v2: optional, aus cv-match Schritt 1d. Fehlt es
        # (Alt-Aufrufer, z. B. job-deepdive/register() über den ungesplitteten Weg) → Row ohne,
        # kein Fehler; cv-erstellen greift dann auf den Fallback (Entscheidung 5) zurück.
        keywords_json = cv.get("keywords_json")

        row = CVVersion(
            job_id=job_id,
            language=_sprache(cv.get("language")),
            kind=cv.get("kind", "tailored"),
            file_path=_rel(cv.get("file_path")),
            match_score100=cv.get("match_score100"),
            match_dashboard_path=_rel(cv.get("match_dashboard_path")),
            status="entwurf",
            entwurf_text=json.dumps(entwurf_text, ensure_ascii=False),
            keywords_json=json.dumps(keywords_json, ensure_ascii=False) if keywords_json is not None else None,
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        return {"job_id": job_id, "cv_version_id": row.id,
               "match_dashboard": row.match_dashboard_path, "absaetze": len(entwurf_text)}


def cv_fertigstellen(cv_version_id, ats_score=None, ats_scan_path=None) -> dict:
    """cv-erstellen Schritt 3 (NACH `entwurf_anwenden()` + `cv_export.export()` bereits gelaufen
    sind — export() hat schon umbenannt + Stufe-A-Nachbearbeitung + PDF erzeugt): ATS-Werte
    eintragen und status=fertig setzen. Kein Aufruf von export() hier — das ist bewusst Aufgabe
    des vorherigen Schritts (Reihenfolge aus Design-Entscheidung 3: Entwurf zurückschreiben →
    export() → DANACH ATS-Scan → fertigstellen)."""
    init_db()
    with Session(engine) as s:
        cv = s.get(CVVersion, cv_version_id)
        if not cv:
            raise SystemExit(f"CVVersion {cv_version_id} nicht gefunden")
        cv.status = "fertig"
        if ats_score is not None:
            cv.ats_score = ats_score
        if ats_scan_path:
            cv.ats_scan_path = _rel(ats_scan_path)
        s.add(cv)
        s.commit()
        s.refresh(cv)
        return {"cv_version_id": cv.id, "status": cv.status,
               "ats_score": cv.ats_score, "ats_scan_path": cv.ats_scan_path}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Nutzung: python -m pipeline.deepdive <deepdive.json>  |  "
                 "entwurf <entwurf.json>  |  "
                 "fertigstellen <cv_version_id> [--ats-score N] [--ats-scan-path <pfad>]")
    if sys.argv[1] == "entwurf":
        if len(sys.argv) < 3:
            sys.exit("Nutzung: python -m pipeline.deepdive entwurf <entwurf.json>")
        with open(sys.argv[2], encoding="utf-8") as fh:
            d = json.load(fh)
        print(json.dumps(register_entwurf(d["job_id"], d["cv"]), ensure_ascii=False))
    elif sys.argv[1] == "fertigstellen":
        import argparse
        ap = argparse.ArgumentParser(prog="pipeline.deepdive fertigstellen")
        ap.add_argument("cv_version_id", type=int)
        ap.add_argument("--ats-score", type=int, default=None)
        ap.add_argument("--ats-scan-path", default=None)
        a = ap.parse_args(sys.argv[2:])
        print(json.dumps(cv_fertigstellen(a.cv_version_id, a.ats_score, a.ats_scan_path), ensure_ascii=False))
    else:
        with open(sys.argv[1], encoding="utf-8") as fh:
            d = json.load(fh)
        print(json.dumps(register(d["job_id"], d.get("company_fit_path"), d.get("cv"),
                                  d.get("next_step"), d.get("posting_path"), d.get("fit_ampel")),
                         ensure_ascii=False))
