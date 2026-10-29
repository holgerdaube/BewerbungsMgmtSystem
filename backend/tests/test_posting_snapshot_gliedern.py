"""Tests für `pipeline/posting_snapshot.py::gliedern()` (Phase 79 Stufe E — Backfill „gliedern",
s. `tasks/spec_phase79_snapshot_render_full.md`, Spec-Entscheidung 7).

Stufe E zieht Bestands-Snapshots nach, die VOR Stufe A entstanden — das Modell schrieb das HTML
damals freihändig (eigene `<h2 class="sec">`-Abschnitte mit 25+ Namensvarianten, s. Spec-Befund 2)
statt über das jetzige deterministische `render_full()`. Zwei Wege, EIN CLI-Einstieg:
  E1 — Gruppe B: eigene Abschnitte samt Inhalt vorhanden, nur abweichend benannt -> Überschrift
       aufs Kanon-Mapping abbilden, Inhalt UNVERÄNDERT übernehmen (verlustfrei).
  E2 — Gruppe C + Container-Fälle: keine (verwertbaren) eigenen Abschnitte -> den konservierten
       Volltext per DE/EN-Überschriften-Heuristik teilen.
„Ehrlichkeit vor Vollständigkeit" (Spec-Entscheidung 7): erkennt keiner der beiden Wege etwas
Belastbares, bleibt die Datei UNANGETASTET — der Job wird als „nicht gliederbar" gemeldet.

Pflicht-Abdeckung laut Bau-Auftrag:
  1. E1 benennt korrekt um und verliert keine Inhalte.
  2. E2 gliedert einen synthetischen Volltext.
  3. „nicht gliederbar" lässt die Datei unverändert.
  4. `quelle` wird aus dem alten Snapshot-Kopf übernommen — amber bleibt amber (nie zu grün
     „verbessert").
  5. `--dry-run` (`dry_run=True`) schreibt nichts.

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention) — alle Importe funktions-
lokal. `_SNAPSHOT_DIR` wird je Test per `monkeypatch` auf `tmp_path` gelegt (Muster
`tests/test_posting_snapshot_full.py::_neuer_job`), damit kein Test das echte `data/`
berührt — die T1-Isolation selbst kommt ohnehin schon aus `conftest.py`/`BMS_DATA_DIR`.
"""
import uuid
from datetime import date
from pathlib import Path

import pytest


def _neuer_job(session, url=None):
    """Frischer Job mit EINDEUTIGEM Status (uuid-Suffix) — Muster `test_posting_snapshot_full.py`
    (UNIQUE-Index auf `Job.url`, session-weit akkumulierende tmp-DB)."""
    from app.models import Job

    status = f"Phase79Gliedern-{uuid.uuid4().hex[:8]}"
    if url is None:
        url = f"https://example.invalid/stelle/{status}"
    job = Job(company_name=f"Phase79Gliedern GmbH {status}", title="Director Professional Services",
              status=status, found_date=date.today().isoformat(),
              dedup_key=f"phase79-gliedern-test|{status}", url=url)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def _firma_pruefen_abgeschlossen(session, job) -> None:
    """`gliedern()` findet Jobs ausschließlich über abgeschlossene `firma-pruefen`-AgentTasks
    (dasselbe Auswahlmuster wie `pruefen()`) — ohne diesen Eintrag ignoriert der Backfill den
    Job vollständig."""
    from app.models import AgentTask

    session.add(AgentTask(kind="firma-pruefen", job_id=job.id, status="done"))
    session.commit()


def _datei_schreiben(tmp_path, job, name: str, html: str) -> None:
    """Simuliert einen FRÜHEREN, freihändig geschriebenen Snapshot (vor Stufe A) direkt im
    (gemonkeypatchten) Snapshot-Ordner — `job.posting_snapshot_path` zeigt danach darauf, wie
    bei einem echten Bestands-Job."""
    (tmp_path / name).write_text(html, encoding="utf-8")
    job.posting_snapshot_path = f"data/job_postings/{name}"


# ── Feste HTML-Bausteine, 1:1 an den echten Bestandsformaten orientiert (empirisch gegen die
# ECHTEN Snapshots mehrerer Stellen geprüft — nur lesend, s. Abschlussbericht) ────────
_KOPF_GRUEN = """<div><p class="k">Quelle</p><p class="v">grün — Original beim Firma-Prüfungslauf abgerufen</p></div>"""
_KOPF_AMBER = """<div><p class="k">Quellen-Badge</p><p class="v">amber — Teilquelle, nur Zusammenfassung verfügbar</p></div>"""


def _alte_snapshot_html(kopf_zeile: str, koerper: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="de"><head><title>Alter Snapshot</title></head>
<body>
<div class="wrap">
  <header class="head">
    <h1>Director Professional Services</h1>
    <div class="meta">
      {kopf_zeile}
    </div>
  </header>
  {koerper}
</div>
</body>
</html>
"""


# ── 1. E1: Umbenennen, verlustfrei ──────────────────────────────────────────────────────────
def test_gliedern_e1_benennt_um_und_verliert_keine_inhalte(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job = _neuer_job(session)

    koerper = """
  <h2 class="sec">Aufgaben (Key Responsibilities)</h2>
  <div class="card"><ul class="clean"><li>Team von 8 Consultants führen</li><li>Budgetverantwortung für das EMEA-Portfolio</li></ul></div>

  <h2 class="sec">Anforderungen (Requirements)</h2>
  <div class="card"><ul class="clean"><li>8+ Jahre Erfahrung im Consulting</li><li>Verhandlungssicheres Englisch</li></ul></div>

  <h2 class="sec">Volltext</h2>
  <div class="card"><pre>Der komplette Original-Anzeigentext, wörtlich erfasst und nie verändert.</pre></div>
"""
    html = _alte_snapshot_html(_KOPF_GRUEN, koerper)
    _datei_schreiben(tmp_path, job, "alt_e1.html", html)
    session.add(job)
    session.commit()
    session.refresh(job)
    _firma_pruefen_abgeschlossen(session, job)

    ergebnis = posting_snapshot.gliedern(dry_run=False, job_id=job.id)
    assert ergebnis["e1"] == 1
    assert ergebnis["e2"] == 0
    assert ergebnis["nicht_gliederbar"] == []

    session.refresh(job)
    neues_html = (tmp_path / Path(job.posting_snapshot_path).name).read_text(encoding="utf-8")

    # Kanon-Überschriften statt der alten Varianten
    assert '<h2 class="sec">Aufgaben</h2>' in neues_html
    assert '<h2 class="sec">Anforderungen</h2>' in neues_html
    assert "Aufgaben (Key Responsibilities)" not in neues_html
    assert "Anforderungen (Requirements)" not in neues_html

    # Verlustfrei: jeder einzelne Original-Punkt steht wörtlich weiterhin drin
    assert "Team von 8 Consultants führen" in neues_html
    assert "Budgetverantwortung für das EMEA-Portfolio" in neues_html
    assert "8+ Jahre Erfahrung im Consulting" in neues_html
    assert "Verhandlungssicheres Englisch" in neues_html

    # Der alte „Volltext"-Block landet im NEUEN, zugeklappten <details>-Volltext (nicht verloren)
    assert '<details class="volltext">' in neues_html
    assert "Der komplette Original-Anzeigentext, wörtlich erfasst und nie verändert." in neues_html

    # Footer meldet den geprüften/gegliederten Zustand (Entscheidung 4 der Spec)
    assert "Bei der Firma-Prüfung geprüft und gegliedert" in neues_html


# ── 2. E2: synthetischer Volltext wird per Überschriften-Heuristik gegliedert ───────────────
def test_gliedern_e2_gliedert_synthetischen_volltext(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job = _neuer_job(session)

    volltext = (
        "Wir suchen eine erfahrene Führungskraft für unser Customer-Success-Team.\n\n"
        "Aufgaben\n"
        "- Team von 6 Personen führen\n"
        "- Kundenbindung strategisch ausbauen\n\n"
        "Anforderungen\n"
        "- 5+ Jahre Erfahrung im Customer Success\n"
        "- Verhandlungssichere Deutsch- und Englischkenntnisse\n\n"
        "Benefits\n"
        "- 30 Tage Urlaub\n"
        "- Firmenwagen\n\n"
        "Über uns\n"
        "Ein wachsendes Unternehmen im Bereich Cloud-Software."
    )
    # render_basis() (Stufe A, unverändert) erzeugt exakt das Gruppe-C-Ausgangsbild: KEINE
    # eigenen Abschnitte, nur die Anzeigentext-Karte -- der reguläre Ausgangszustand, den E2
    # bedient.
    posting_snapshot.render_basis(job, text=volltext)
    session.add(job)
    session.commit()
    session.refresh(job)
    _firma_pruefen_abgeschlossen(session, job)

    ergebnis = posting_snapshot.gliedern(dry_run=False, job_id=job.id)
    assert ergebnis["e1"] == 0
    assert ergebnis["e2"] == 1
    assert ergebnis["nicht_gliederbar"] == []

    session.refresh(job)
    neues_html = (tmp_path / Path(job.posting_snapshot_path).name).read_text(encoding="utf-8")

    assert '<h2 class="sec">Aufgaben</h2>' in neues_html
    assert '<h2 class="sec">Anforderungen</h2>' in neues_html
    assert '<h2 class="sec">Benefits</h2>' in neues_html
    assert '<h2 class="sec">Über das Unternehmen</h2>' in neues_html
    assert "Team von 6 Personen führen" in neues_html
    assert "5+ Jahre Erfahrung im Customer Success" in neues_html
    assert "Firmenwagen" in neues_html
    assert "Ein wachsendes Unternehmen im Bereich Cloud-Software." in neues_html
    # Der komplette Rohtext bleibt weiterhin im Volltext-Block erhalten
    assert "Wir suchen eine erfahrene Führungskraft" in neues_html


# ── 3. „nicht gliederbar" lässt die Datei UNVERÄNDERT ───────────────────────────────────────
def test_gliedern_nicht_gliederbar_laesst_datei_unveraendert(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job = _neuer_job(session)

    # Container-Fall (Spec-Entscheidung 7): generische Sammel-Überschrift OHNE erkennbare
    # Aufgaben/Anforderungen-Trennung, KEIN separater Volltext-Block, KEINE Anzeigentext-Karte --
    # weder E1 noch E2 finden etwas Belastbares.
    koerper = """
  <h2 class="sec">Strukturierte Wiedergabe</h2>
  <div class="card"><p>Eine allgemeine Beschreibung der Rolle ohne klare Gliederung in einzelne Kategorien oder Aufzählungen.</p></div>
"""
    html = _alte_snapshot_html(_KOPF_GRUEN, koerper)
    _datei_schreiben(tmp_path, job, "alt_nicht_gliederbar.html", html)
    session.add(job)
    session.commit()
    session.refresh(job)
    _firma_pruefen_abgeschlossen(session, job)

    vorher = (tmp_path / "alt_nicht_gliederbar.html").read_text(encoding="utf-8")

    ergebnis = posting_snapshot.gliedern(dry_run=False, job_id=job.id)
    assert ergebnis["e1"] == 0
    assert ergebnis["e2"] == 0
    befund_ids = {jid for jid, _ in ergebnis["nicht_gliederbar"]}
    assert job.id in befund_ids

    session.refresh(job)
    assert job.posting_snapshot_path == "data/job_postings/alt_nicht_gliederbar.html", (
        "nicht gliederbarer Job darf nicht plötzlich einen anderen Dateinamen bekommen")
    nachher = (tmp_path / "alt_nicht_gliederbar.html").read_text(encoding="utf-8")
    assert vorher == nachher, "Datei wurde trotz 'nicht gliederbar' verändert"


# ── 4. `quelle` wird übernommen — amber bleibt amber ────────────────────────────────────────
def test_gliedern_uebernimmt_amber_faerbt_nicht_gruen(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job = _neuer_job(session)

    koerper = """
  <h2 class="sec">Aufgaben / Responsibilities</h2>
  <div class="card"><ul class="clean"><li>Kunden betreuen</li></ul></div>

  <h2 class="sec">Anforderungen / Qualifications</h2>
  <div class="card"><ul class="clean"><li>Erfahrung im B2B-Vertrieb</li></ul></div>
"""
    html = _alte_snapshot_html(_KOPF_AMBER, koerper)
    _datei_schreiben(tmp_path, job, "alt_amber.html", html)
    session.add(job)
    session.commit()
    session.refresh(job)
    _firma_pruefen_abgeschlossen(session, job)

    ergebnis = posting_snapshot.gliedern(dry_run=False, job_id=job.id)
    assert ergebnis["e1"] == 1

    session.refresh(job)
    neues_html = (tmp_path / Path(job.posting_snapshot_path).name).read_text(encoding="utf-8")

    assert "amber — Teilquelle beim Firma-Prüfungslauf (kein wörtlicher Originaltext)" in neues_html
    assert "grün — Original beim Firma-Prüfungslauf abgerufen" not in neues_html, (
        "Backfill darf aus amber NIE grün machen (Badge-Ehrlichkeit)")


# ── 5. `--dry-run` schreibt NICHTS ──────────────────────────────────────────────────────────
def test_gliedern_dry_run_schreibt_nichts(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job = _neuer_job(session)

    koerper = """
  <h2 class="sec">Aufgaben (wörtlich)</h2>
  <div class="card"><ul class="clean"><li>Projekte leiten</li></ul></div>

  <h2 class="sec">Anforderungen (wörtlich)</h2>
  <div class="card"><ul class="clean"><li>Studium abgeschlossen</li></ul></div>
"""
    html = _alte_snapshot_html(_KOPF_GRUEN, koerper)
    _datei_schreiben(tmp_path, job, "alt_dryrun.html", html)
    session.add(job)
    session.commit()
    session.refresh(job)
    _firma_pruefen_abgeschlossen(session, job)

    dateien_vorher = sorted(p.name for p in tmp_path.glob("*"))
    inhalt_vorher = (tmp_path / "alt_dryrun.html").read_text(encoding="utf-8")
    pfad_vorher = job.posting_snapshot_path

    ergebnis = posting_snapshot.gliedern(dry_run=True, job_id=job.id)
    assert ergebnis["dry_run"] is True
    # Die Vorschau erkennt den Fall trotzdem korrekt (E1) -- nur geschrieben wird nichts.
    assert ergebnis["e1"] == 1
    assert any(jid == job.id for jid, *_ in ergebnis["vorschau"])

    session.refresh(job)
    assert job.posting_snapshot_path == pfad_vorher, "Trockenlauf darf den DB-Pfad nicht ändern"

    dateien_nachher = sorted(p.name for p in tmp_path.glob("*"))
    assert dateien_nachher == dateien_vorher, "Trockenlauf darf KEINE neuen/zusätzlichen Dateien anlegen"
    inhalt_nachher = (tmp_path / "alt_dryrun.html").read_text(encoding="utf-8")
    assert inhalt_vorher == inhalt_nachher, "Trockenlauf darf die bestehende Datei nicht verändern"
