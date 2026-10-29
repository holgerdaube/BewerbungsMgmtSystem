"""Tests für `pipeline/company_fit.py::render_full()` (Design-Review 10.08.2026 — deterministisches
Company-Fit-Layout statt freihändig vom Modell geschriebenem HTML; Drift-Fall 09.–10.08.2026,
14 Dateien, Root Cause: Plugin-Skill headless nie verfügbar + Selbstfortpflanzung über
„neueste Datei als Vorlage").

Abgedeckt:
  1. Happy Path: alle Bausteine → Referenz-Struktur (header.head, .bluf, table.score mit
     pos/neu/neg-Badges, 4 Arbeitgeber-Karten, Chancen/Risiken-Grid, .caveat, .sources, .foot)
     in fester Reihenfolge; Rückgabe listet die erkannten Bausteine.
  2. Leere/fehlende Abschnitte werden weggelassen (kein „–"-Füller, keine leere Karte).
  3. Unbekannte Schlüssel / ungültige Ampel / ungültiger Einfluss-Wert → ValueError.
  4. Neue Datei je Lauf (Phase-30-Regel) + Kollisionssuffix _2 am selben Tag.
  5. Reparatur-Modus `out_path` ersetzt exakt die bestehende Datei (kein neuer Name);
     nicht existierender out_path → SystemExit.
  6. `_esc()` auf Modell-Inhalten (Fremdtext = Daten).

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention) — alle Importe
funktionslokal. `_FIT_DIR` je Test per `monkeypatch` auf `tmp_path` (Muster
`test_posting_snapshot_full.py`)."""
import uuid
from datetime import date
from pathlib import Path

import pytest


def _neuer_job(session, firma=None):
    from app.models import Job

    status = f"CFitTest-{uuid.uuid4().hex[:8]}"
    job = Job(company_name=firma or f"CFitTest GmbH {status}",
              title="Director Professional Services", status=status,
              found_date=date.today().isoformat(),
              dedup_key=f"cfit-test|{status}", url=f"https://example.invalid/{status}")
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def _voll_payload():
    return dict(
        sub="Branche · Rolle · Situation PE/RESTRUCT",
        fit_ampel="gelb",
        fit_text="starker Fit, zwei Vorbehalte",
        bluf="Kernaussage: passt gut, aber <Vorbehalt> bleibt.",
        abschnitte={
            "geschaeftsmodell_was": {"Kerngeschäft": "Buy-Improve-Sell.",
                                     "Wachstum & Finanzlage": "Rekordjahr 2025."},
            "geschaeftsmodell_wettbewerber": ["Aurelius", "Orlando"],
            "ki_disruption": "Wenig automatisierbar.",
            "arbeitgeber_realitaet": {"bewertungen": "Glassdoor 4,3/5.",
                                      "modern": "IFRS-Zahlen vs. BaFin-Feststellung.",
                                      "aktivitaet": "Mehrere offene Rollen.",
                                      "entwicklung": "Umsatz wächst."},
            "chancen": ["Echte Wertschöpfungsrolle"],
            "risiken": [{"label": "Reisebelastung", "text": "bis 4 Tage/Woche"}],
        },
        rollen_einfluss=[
            {"faktor": "Hebel", "wert": "pos", "warum": "Kern des Geschäftsmodells",
             "relevanz": "Direkter Ergebnishebel"},
            {"faktor": "Vergütung", "wert": "neu", "warum": "Nicht genannt", "relevanz": "Offen"},
            {"faktor": "Reise", "wert": "neg", "warum": "4 Tage/Woche", "relevanz": "Belastung"},
        ],
        klaerungsfrage="Wie viele Portfoliounternehmen parallel?",
        quellen=[{"label": "Original-Anzeige", "url": "https://example.invalid/anzeige"},
                 {"label": "WebSearch Umsatz 2025"}],
        markt_segment="Special Situations",
        quellen_kurz="career.example.com, Glassdoor",
    )


# ── 1. Happy Path: Referenz-Struktur + Reihenfolge ─────────────────────────────────────────
def test_render_full_referenz_struktur_und_reihenfolge(session, monkeypatch, tmp_path):
    from pipeline import company_fit

    monkeypatch.setattr(company_fit, "_FIT_DIR", tmp_path)
    job = _neuer_job(session, firma="Beispiel Test SE")
    ergebnis = company_fit.render_full(job.id, **_voll_payload())

    assert ergebnis["abschnitte"] == ["bluf", "geschaeftsmodell", "ki_disruption",
                                     "rollen_einfluss", "arbeitgeber_realitaet",
                                     "chancen_risiken", "klaerungsfrage", "quellen"]
    html = (tmp_path / Path(ergebnis["company_fit_path"]).name).read_text(encoding="utf-8")

    # Kopf + Meta-Grid mit Ampel-Dot
    assert '<header class="head">' in html
    assert '<p class="eyebrow">Company-Fit</p>' in html
    assert "<h1>Beispiel Test SE</h1>" in html
    assert '<span class="dot amber"></span>Gelb · starker Fit, zwei Vorbehalte' in html
    # Referenz-Bausteine
    assert '<p class="fitlabel">Kernaussage in einem Satz</p>' in html
    assert '<h3>Was &amp; für wen</h3>' in html and '<p class="kv">Kerngeschäft</p>' in html
    assert '<h3>Wettbewerber &amp; Marktstellung</h3>' in html
    assert '<table class="score">' in html
    assert '<span class="badge pos">+</span>' in html
    assert '<span class="badge neu">0</span>' in html
    assert '<span class="badge neg">−</span>' in html
    assert html.count('<div class="card">\n      <h3>') >= 6  # 2 GM + 4 AG-Realität
    assert '<h3>Glassdoor / kununu</h3>' in html
    assert '<h3>Geschäftsentwicklung &amp; Tarifbindung</h3>' in html
    assert '<b>Reisebelastung:</b> bis 4 Tage/Woche' in html
    assert '<div class="caveat"><b>Klärungsfrage fürs Gespräch:</b>' in html
    assert '<div class="sources">' in html
    assert 'href="https://example.invalid/anzeige"' in html
    assert '<div class="foot">' in html and "Bewerbungs-Mgmt · erzeugt am" in html
    # Reihenfolge (Indizes streng aufsteigend)
    marker = ['<header class="head">', 'class="bluf"', 'Geschäftsmodell &amp; Marktposition',
              'KI-/Digital-Disruption', 'Einfluss dieser Rolle', 'Arbeitgeber-Realität',
              'Chancen &amp; Risiken', 'class="caveat"', 'class="sources"', 'class="foot"']
    positionen = [html.index(m) for m in marker]
    assert positionen == sorted(positionen)
    # _esc auf Modell-Inhalt
    assert "&lt;Vorbehalt&gt;" in html and "<Vorbehalt>" not in html


# ── 2. Leere Abschnitte weggelassen ────────────────────────────────────────────────────────
def test_render_full_leere_abschnitte_weggelassen(session, monkeypatch, tmp_path):
    from pipeline import company_fit

    monkeypatch.setattr(company_fit, "_FIT_DIR", tmp_path)
    job = _neuer_job(session)
    ergebnis = company_fit.render_full(
        job.id, sub="", fit_ampel="gruen", fit_text="", bluf="Nur die Kernaussage.",
        abschnitte={"ki_disruption": "Nur dieser Abschnitt.", "chancen": [], "risiken": [""]},
        rollen_einfluss=[], klaerungsfrage=None, quellen=[])
    assert ergebnis["abschnitte"] == ["bluf", "ki_disruption"]
    html = (tmp_path / Path(ergebnis["company_fit_path"]).name).read_text(encoding="utf-8")
    for verboten in ("Geschäftsmodell &amp; Marktposition", "table class=\"score\"",
                     "Arbeitgeber-Realität", "Chancen &amp; Risiken", "class=\"caveat\"",
                     "class=\"sources\"", "<p class=\"sub\">"):
        assert verboten not in html
    assert "Nur dieser Abschnitt." in html


# ── 3. Validierung: Tippfehler knallen ─────────────────────────────────────────────────────
def test_render_full_validierung_value_errors(session, monkeypatch, tmp_path):
    from pipeline import company_fit

    monkeypatch.setattr(company_fit, "_FIT_DIR", tmp_path)
    job = _neuer_job(session)
    basis = _voll_payload()

    with pytest.raises(ValueError, match="fit_ampel"):
        company_fit.render_full(job.id, **{**basis, "fit_ampel": "grün"})  # Umlaut = falsch
    with pytest.raises(ValueError, match="abschnitte"):
        company_fit.render_full(job.id, **{**basis,
                                           "abschnitte": {**basis["abschnitte"], "tippfehler": "x"}})
    with pytest.raises(ValueError, match="arbeitgeber_realitaet"):
        company_fit.render_full(job.id, **{**basis,
                                           "abschnitte": {**basis["abschnitte"],
                                                          "arbeitgeber_realitaet": {"kununu": "x"}}})
    with pytest.raises(ValueError, match="rollen_einfluss.wert"):
        company_fit.render_full(job.id, **{**basis,
                                           "rollen_einfluss": [{"faktor": "F", "wert": "plus",
                                                                "warum": "w", "relevanz": "r"}]})
    with pytest.raises(ValueError, match="rollen_einfluss"):
        company_fit.render_full(job.id, **{**basis,
                                           "rollen_einfluss": [{"faktor": "F", "wert": "pos",
                                                                "warum": "w", "relevanz": "r",
                                                                "extra": "x"}]})
    with pytest.raises(ValueError, match="quellen"):
        company_fit.render_full(job.id, **{**basis, "quellen": [{"label": "L", "link": "x"}]})


# ── 4. Neue Datei je Lauf + Kollisionssuffix ───────────────────────────────────────────────
def test_render_full_neue_datei_und_kollisionssuffix(session, monkeypatch, tmp_path):
    from pipeline import company_fit

    monkeypatch.setattr(company_fit, "_FIT_DIR", tmp_path)
    job = _neuer_job(session, firma="Doppellauf AG")
    erster = company_fit.render_full(job.id, **_voll_payload())
    zweiter = company_fit.render_full(job.id, **_voll_payload())
    assert erster["company_fit_path"] != zweiter["company_fit_path"]
    assert zweiter["company_fit_path"].endswith("_2.html")
    assert (tmp_path / Path(erster["company_fit_path"]).name).is_file()
    assert (tmp_path / Path(zweiter["company_fit_path"]).name).is_file()


# ── 5. Reparatur-Modus out_path ────────────────────────────────────────────────────────────
def test_render_full_out_path_ersetzt_bestehende_datei(session, monkeypatch, tmp_path):
    from pipeline import company_fit

    monkeypatch.setattr(company_fit, "_FIT_DIR", tmp_path)
    job = _neuer_job(session, firma="Reparatur GmbH")
    alt = tmp_path / "2026_08_10_CompanyFit_Reparatur_GmbH.html"
    alt.write_text("<html>gedriftet</html>", encoding="utf-8")

    ergebnis = company_fit.render_full(job.id, **_voll_payload(), out_path=str(alt))
    html = alt.read_text(encoding="utf-8")
    assert "gedriftet" not in html
    assert '<header class="head">' in html and '<table class="score">' in html
    assert ergebnis["company_fit_path"].endswith("2026_08_10_CompanyFit_Reparatur_GmbH.html")
    # keine zweite Datei entstanden
    assert len(list(tmp_path.glob("*.html"))) == 1

    with pytest.raises(SystemExit):
        company_fit.render_full(job.id, **_voll_payload(),
                                out_path=str(tmp_path / "gibt_es_nicht.html"))
