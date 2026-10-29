"""Tests für `pipeline/posting_snapshot.py::render_full()` (Phase 79 — deterministisches
Voll-Layout statt freihändig vom Modell geschriebenem HTML, s. tasks/spec_phase79_snapshot_
render_full.md, Fall A, 08.08.2026).

Bau-Auftrag Stufe D, Punkte 1–6 + der `pruefen`-CLI-Modus-Test (Entscheidung 4):
  1. Alle Abschnitte → feste Reihenfolge, Listen als `<ul><li>`, Volltext in `<details>`.
  2. Leere/fehlende Abschnitte werden weggelassen (kein „–"-Füller).
  3. Unbekannter Schlüssel / ungültige `quelle` → `ValueError`.
  4. Dateiname bleibt stabil: `render_basis` → `render_full` → derselbe Pfad, kein `_2`.
  5. `_esc()` auf Abschnitts-Inhalten UND auf dem übernommenen Anzeigentext (Fremdtext = Daten,
     Phase 66B).
  6. Regressionsschutz: `render_basis()` (= `_build_html()` mit `abschnitte=None`, dem Default)
     bleibt strukturell unverändert (Anzeigentext-Karte + Erfassungs-Kontext, kein Phase-79-
     Voll-Layout-Element). Empirisch vor der Änderung gegen den unveränderten Code
     gegengeprüft — außerhalb des gemeinsamen `<style>`-Blocks (der jetzt zusätzlich die für
     `<details class="volltext">`/`<ul class="clean">` nötigen, im Basis-Layout dormant
     bleibenden CSS-Regeln trägt) ist die Ausgabe byte-identisch.
  7. `pruefen()`: Job mit `firma-pruefen`-Lauf + ungegliedertem Snapshot → Befund; Job mit
     `firma-pruefen`-Lauf + gegliedertem Snapshot → kein Befund.

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention) — alle Importe funktions-
lokal. `_SNAPSHOT_DIR` wird je Test per `monkeypatch` auf `tmp_path` gelegt (Muster
`tests/test_posting_badge_ehrlichkeit.py`), damit parallele/Folge-Tests sich nicht über
kollidierende Dateinamen in die Quere kommen — die T1-Isolation selbst (kein Zugriff auf
das echte `data/`) ist ohnehin schon über `conftest.py`/`BMS_DATA_DIR` sichergestellt
(s. `tests/test_daten_pfade.py`).
"""
import re
import uuid
from datetime import date
from pathlib import Path

import pytest


def _neuer_job(session, url=None):
    """Frischer Job mit EINDEUTIGEM Status (uuid-Suffix), Muster `test_posting_badge_
    ehrlichkeit.py::_neuer_job` — die session-weit akkumulierende tmp-DB verlangt eindeutige
    `url`/`status`-Werte (UNIQUE-Index auf `Job.url`), damit sich Tests dieser Datei nicht
    gegenseitig verfälschen."""
    from app.models import Job

    status = f"Phase79Test-{uuid.uuid4().hex[:8]}"
    if url is None:
        url = f"https://example.invalid/stelle/{status}"
    job = Job(company_name=f"Phase79Test GmbH {status}", title="Director Professional Services",
              status=status, found_date=date.today().isoformat(),
              dedup_key=f"phase79-test|{status}", url=url)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job, status


def _html_fuer(tmp_path, rel_path: str) -> str:
    return (tmp_path / Path(rel_path).name).read_text(encoding="utf-8")


# ── 1. Feste Reihenfolge, Listen als <ul><li>, Volltext in <details> ───────────────────────
def test_render_full_alle_abschnitte_feste_reihenfolge_listen_volltext_details(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job, _ = _neuer_job(session)
    posting_snapshot.render_basis(job, text="Der Original-Anzeigentext, wörtlich erfasst.")
    session.add(job)
    session.commit()
    session.refresh(job)

    abschnitte = {
        "aufgaben": ["Team führen", "Budget verantworten"],
        "anforderungen": ["5+ Jahre Erfahrung", "Verhandlungssicheres Englisch"],
        "benefits": ["Firmenwagen"],
        "ueber_das_unternehmen": "Ein wachsendes Unternehmen im Bereich Cloud-Software.",
        "kontext": "Neu geschaffene Rolle wegen internationaler Expansion.",
    }
    ergebnis = posting_snapshot.render_full(job.id, abschnitte, "gruen")
    assert ergebnis["abschnitte"] == ["aufgaben", "anforderungen", "benefits", "ueber_das_unternehmen", "kontext"]

    html = _html_fuer(tmp_path, ergebnis["posting_snapshot_path"])

    # Feste Reihenfolge (Entscheidung 1 der Spec)
    kanon_titel = ("Aufgaben", "Anforderungen", "Benefits", "Über das Unternehmen", "Kontext")
    positionen = [html.index(f'<h2 class="sec">{titel}</h2>') for titel in kanon_titel]
    assert positionen == sorted(positionen), "Kanon-Abschnitte stehen nicht in der vorgeschriebenen Reihenfolge"

    # Listen als <ul class="clean"><li>…</li></ul>
    assert '<ul class="clean"><li>Team führen</li><li>Budget verantworten</li></ul>' in html
    assert '<ul class="clean"><li>5+ Jahre Erfahrung</li><li>Verhandlungssicheres Englisch</li></ul>' in html

    # String-Abschnitte als Absatz
    assert "<p>Ein wachsendes Unternehmen im Bereich Cloud-Software.</p>" in html
    assert "<p>Neu geschaffene Rolle wegen internationaler Expansion.</p>" in html

    # Volltext im zugeklappten <details>-Block, NACH den Kanon-Abschnitten
    assert '<details class="volltext">' in html
    assert "<summary>Volltext (unbereinigt)</summary>" in html
    assert "Der Original-Anzeigentext, wörtlich erfasst." in html
    volltext_pos = html.index("<summary>Volltext (unbereinigt)</summary>")
    assert volltext_pos > positionen[-1]

    # Footer meldet den geprüften/gegliederten Zustand sichtbar (Entscheidung 4)
    assert "Bei der Firma-Prüfung geprüft und gegliedert" in html


# ── 2. Leere/fehlende Abschnitte werden weggelassen ─────────────────────────────────────────
def test_render_full_leere_und_fehlende_abschnitte_werden_weggelassen(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job, _ = _neuer_job(session)

    abschnitte = {
        "aufgaben": ["Ein Punkt"],
        "anforderungen": [],              # leere Liste
        "benefits": None,                 # explizit None
        "ueber_das_unternehmen": "   ",   # nur Whitespace
        # "kontext" fehlt komplett im Dict
    }
    ergebnis = posting_snapshot.render_full(job.id, abschnitte, "amber")
    assert ergebnis["abschnitte"] == ["aufgaben"]

    html = _html_fuer(tmp_path, ergebnis["posting_snapshot_path"])
    assert '<h2 class="sec">Aufgaben</h2>' in html
    for titel in ("Anforderungen", "Benefits", "Über das Unternehmen", "Kontext"):
        assert f'<h2 class="sec">{titel}</h2>' not in html, f"Leerer Abschnitt {titel!r} wurde trotzdem gerendert"


# ── 3. Unbekannter Schlüssel / ungültige quelle → ValueError ───────────────────────────────
def test_render_full_unbekannter_abschnitts_schluessel_wirft_valueerror(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job, _ = _neuer_job(session)

    with pytest.raises(ValueError):
        posting_snapshot.render_full(job.id, {"aufgaebn": ["Tippfehler"]}, "gruen")

    session.refresh(job)
    assert job.posting_snapshot_path is None, "bei ungültigem Aufruf darf NICHTS geschrieben werden"


def test_render_full_ungueltige_quelle_wirft_valueerror(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job, _ = _neuer_job(session)

    with pytest.raises(ValueError):
        posting_snapshot.render_full(job.id, {"aufgaben": ["x"]}, "gelb")  # nur gruen|amber|rot

    session.refresh(job)
    assert job.posting_snapshot_path is None


# ── 4. Dateiname bleibt stabil ──────────────────────────────────────────────────────────────
def test_render_full_ersetzt_dieselbe_datei_kein_zweiter_name(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job, _ = _neuer_job(session)

    rel_basis = posting_snapshot.render_basis(job, text="Anzeigentext.")
    session.add(job)
    session.commit()
    session.refresh(job)
    assert job.posting_snapshot_path == rel_basis

    ergebnis = posting_snapshot.render_full(job.id, {"aufgaben": ["x"]}, "gruen")
    assert ergebnis["posting_snapshot_path"] == rel_basis
    # Der Duplikat-Zähler hängt IMMER direkt vor der Endung (`_eindeutig()`: f"{stem}_{n}.{ext}"),
    # deshalb hier mit Anker am Dateiende prüfen. Die frühere Fassung suchte `"_2" not in name`
    # und war damit vom Kalenderdatum abhängig: der Dateiname trägt das Datum (`2026_08_21_…`),
    # also war der Test an jedem 2., 20.–29. eines Monats rot, ohne dass am Code etwas fehlte
    # (aufgefallen am 21.08.2026). Datumsabhängige Zusicherungen gehören nie in einen Test.
    assert not re.search(r"_\d+\.[A-Za-z]+$", Path(ergebnis["posting_snapshot_path"]).name)

    session.refresh(job)
    assert job.posting_snapshot_path == rel_basis

    # Nur EINE Datei für diesen Job im (isolierten) Snapshot-Ordner
    treffer = [p for p in tmp_path.glob("*") if p.name == Path(rel_basis).name]
    assert len(treffer) == 1


# ── 5. _esc() auf Fremdtext (Abschnitte UND übernommener Anzeigentext) ─────────────────────
def test_render_full_esc_auf_abschnitts_inhalt(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job, _ = _neuer_job(session)
    boese = "<script>alert(1)</script>"

    ergebnis = posting_snapshot.render_full(job.id, {"aufgaben": [boese]}, "gruen")
    html = _html_fuer(tmp_path, ergebnis["posting_snapshot_path"])

    assert boese not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_render_full_esc_script_im_uebernommenen_anzeigentext_bleibt_escaped(session, monkeypatch, tmp_path):
    """Spec-Wortlaut Stufe D.5: „<script> im Anzeigentext landet escaped im HTML" — der
    Anzeigentext wird von `render_basis()` konserviert und von `render_full()` unverändert in
    den Volltext-<details>-Block übernommen (`_lese_vorhandenen_volltext()`); auch dieser Pfad
    muss escapen, nicht nur frisch übergebene `abschnitte`-Inhalte."""
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job, _ = _neuer_job(session)
    boese_anzeige = "Wir suchen dich. <script>alert(1)</script> Jetzt bewerben."
    posting_snapshot.render_basis(job, text=boese_anzeige)
    session.add(job)
    session.commit()
    session.refresh(job)

    ergebnis = posting_snapshot.render_full(job.id, {"aufgaben": ["Team leiten"]}, "gruen")
    html = _html_fuer(tmp_path, ergebnis["posting_snapshot_path"])

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert '<details class="volltext">' in html  # landet im Volltext-Block, nicht als offene Karte


# ── 6. Regressionsschutz Basis-Layout ───────────────────────────────────────────────────────
def test_render_basis_struktur_unveraendert_wie_vor_phase_79(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job, _ = _neuer_job(session)
    posting_snapshot.render_basis(job, text="Zeile eins.\n\nZweiter Absatz.")
    session.add(job)
    session.commit()
    session.refresh(job)

    html = _html_fuer(tmp_path, job.posting_snapshot_path)

    assert '<h2 class="sec">Anzeigentext (automatisch extrahiert, unbereinigt)</h2>' in html
    assert '<h2 class="sec">Erfassungs-Kontext</h2>' in html
    assert "Automatisch bei Erfassung gesichert — Firma-Prüfung ausstehend" in html

    # Keines der Phase-79-Voll-Layout-Elemente taucht im Basis-Snapshot auf
    assert '<details class="volltext">' not in html
    assert 'class="clean"' not in html
    assert '<h2 class="sec">Aufgaben</h2>' not in html
    assert "Bei der Firma-Prüfung geprüft und gegliedert" not in html


def test_render_basis_ohne_text_struktur_unveraendert(session, monkeypatch, tmp_path):
    """Zweites Basis-Szenario (kein Anzeigentext, nur Metadaten) — deckt den anderen Zweig von
    `_build_html()`s Basis-Pfad ab (kein `text` → keine Anzeigentext-Karte)."""
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job, _ = _neuer_job(session)
    posting_snapshot.render_basis(job, text=None)
    session.add(job)
    session.commit()
    session.refresh(job)

    html = _html_fuer(tmp_path, job.posting_snapshot_path)
    assert '<h2 class="sec">Anzeigentext (automatisch extrahiert, unbereinigt)</h2>' not in html
    assert '<h2 class="sec">Erfassungs-Kontext</h2>' in html
    assert '<details class="volltext">' not in html


# ── pruefen()-CLI-Modus (Entscheidung 4) ────────────────────────────────────────────────────
def test_pruefen_meldet_ungegliederten_snapshot_ignoriert_gegliederten(session, monkeypatch, tmp_path):
    from app.models import AgentTask
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)

    # Job C: abgeschlossener firma-pruefen-Lauf, aber Snapshot bleibt reine Basis-Version.
    job_c, _ = _neuer_job(session)
    posting_snapshot.render_basis(job_c, text="Anzeigentext, nie gegliedert.")
    session.add(job_c)
    session.commit()
    session.refresh(job_c)
    session.add(AgentTask(kind="firma-pruefen", job_id=job_c.id, status="done"))
    session.commit()

    # Job A: abgeschlossener firma-pruefen-Lauf UND sauber gegliederter Snapshot.
    job_a, _ = _neuer_job(session)
    posting_snapshot.render_basis(job_a, text="Anzeigentext, wird gegliedert.")
    session.add(job_a)
    session.commit()
    session.refresh(job_a)
    posting_snapshot.render_full(job_a.id, {"aufgaben": ["x"], "anforderungen": ["y"]}, "gruen")
    session.add(AgentTask(kind="firma-pruefen", job_id=job_a.id, status="done"))
    session.commit()

    ergebnis = posting_snapshot.pruefen()
    befund_ids = {b[0] for b in ergebnis["befunde"]}

    assert job_c.id in befund_ids, "Job mit ungegliedertem Snapshot trotz firma-pruefen-Lauf fehlt im Befund"
    assert job_a.id not in befund_ids, "sauber gegliederter Job wurde fälschlich gemeldet"
