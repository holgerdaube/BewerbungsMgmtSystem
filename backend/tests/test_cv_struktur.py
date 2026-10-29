"""Tests für Phase 76 — Workday-optimierte Stationsstruktur „v9 ATS" der Basis-CVs und die
angepasste Ketten-Logik in `pipeline/cv_export.py` (`_stationsgrenzen`,
`_seitenumbrueche_schuetzen`, 0-Stationen-Warnung).

Wie in conftest.py vorgesehen: KEINE app.*/pipeline.*-Importe auf Modulebene. Die Tests gegen
die ECHTEN Basis-CVs (`data/cv_basis/base_*.docx`) laufen nur lokal — `data/` ist gitignored,
in CI existieren die Dateien nicht → `skipif` (sichtbar geskippt statt falsch-grün). Die
Ketten-Logik selbst wird CI-fähig gegen synthetische Mini-docx belegt."""
from pathlib import Path

import pytest

_BASIS_DIR = Path(__file__).resolve().parents[2] / "data" / "cv_basis"


# ── synthetischer Stations-Builder ──────────────────────────────────────────────────────────
def _station_v9(doc, titel, firma_zeile, beschreibung, bullets):
    """Eine Station im v9-Format (Phase 76): Titel (Normal, bold) → „Firma\\tZeitraum" →
    kursive Beschreibung → Bullets (List Paragraph)."""
    p = doc.add_paragraph()
    p.add_run(titel).bold = True
    doc.add_paragraph(firma_zeile)
    b = doc.add_paragraph()
    b.add_run(beschreibung).italic = True
    for text in bullets:
        doc.add_paragraph(text, style="List Bullet")


def _docx_v9(pfad, stationen, mit_heading=True):
    from docx import Document

    doc = Document()
    if mit_heading:
        doc.add_heading("BERUFSERFAHRUNG", level=1)
    for s in stationen:
        _station_v9(doc, *s)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(pfad))
    return pfad


# ── Ketten-Logik synthetisch (CI-fähig) ─────────────────────────────────────────────────────
def test_v9_kette_beginnt_am_titel_und_endet_vor_dem_fremden_titel(tmp_path):
    """Der Regressionsfall aus der Planung: Nach dem v9-Umbau muss die keep-Kette von Station 1
    an deren TITEL beginnen und VOR dem Titel von Station 2 enden — sonst strandet der Titel
    allein auf der Vorseite bzw. klebt der fremde Titel am letzten Bullet der Vorgängerin."""
    from docx import Document
    from pipeline import cv_export

    pfad = _docx_v9(tmp_path / "v9.docx", [
        ("Manager Musterdienste EMEA", "Beispiel GmbH\tNov. 2024 – heute",
         "Ausgründung aus einem Konzern.", ["Bullet A1", "Bullet A2"]),
        ("Consulting Delivery Manager", "Muster AG\tFeb. 2017 – Feb. 2020",
         "Globaler Anbieter von IT-Infrastruktur.", ["Bullet B1"]),
    ])
    doc = Document(str(pfad))
    stationen = cv_export._seitenumbrueche_schuetzen(doc)
    assert stationen == 2

    absaetze = doc.paragraphs
    # Layout: 0=Heading, 1=Titel_A, 2=Tab_A, 3=Beschr_A, 4=BulletA1, 5=BulletA2,
    #         6=Titel_B, 7=Tab_B, 8=Beschr_B, 9=BulletB1
    assert absaetze[1].paragraph_format.keep_with_next is True      # Titel A kettet zur Firma
    assert absaetze[2].paragraph_format.keep_with_next is True
    assert absaetze[5].paragraph_format.keep_with_next is not True  # Kette endet VOR Titel B
    assert absaetze[6].paragraph_format.keep_with_next is True      # Titel B beginnt Kette B
    assert absaetze[9].paragraph_format.keep_with_next is not True  # letzter Absatz offen


def test_altformat_tab_zeile_ohne_titel_verhaelt_sich_wie_bisher(tmp_path):
    """Alt-Format (bis v7) / Ausbildungszeilen: Tab-Anker ohne bold-Titel davor — die Kette
    beginnt wie vor Phase 76 an der Tab-Zeile selbst."""
    from docx import Document
    from pipeline import cv_export

    pfad = tmp_path / "alt.docx"
    doc = Document()
    doc.add_heading("AUSBILDUNG", level=1)
    doc.add_paragraph("Bankkaufmann – Muster Bank AG\t1996")
    doc.add_paragraph("Abitur – Beispiel-Gymnasium\t1993")
    doc.save(str(pfad))

    doc = Document(str(pfad))
    stationen = cv_export._seitenumbrueche_schuetzen(doc)
    assert stationen == 2
    absaetze = doc.paragraphs
    # Zwei EINZELNE Stationen: die erste Tab-Zeile darf NICHT an die zweite gekettet werden
    # (jede Grenze beendet die Kette der Vorgängerin).
    assert absaetze[1].paragraph_format.keep_together is True
    assert absaetze[1].paragraph_format.keep_with_next is not True


def test_null_stationen_erzeugen_warnung_statt_stillem_ausfall(tmp_path, monkeypatch):
    """Explorations-Befund Phase 76: eine Vorlage ohne Tab-Ankerzeilen ließ den
    Seitenumbruch-Schutz bisher STILL ins Leere laufen (export meldete „ok"). Jetzt liefert
    `_nachbearbeiten` eine Warnung."""
    from docx import Document
    from pipeline import cv_export, user_profile

    monkeypatch.setattr(user_profile, "user_name", lambda: "Testname")
    pfad = tmp_path / "ohne_stationen.docx"
    doc = Document()
    doc.add_heading("EXECUTIVE SUMMARY", level=1)
    doc.add_paragraph("Nur Fließtext, keine Stationen.")
    doc.save(str(pfad))

    fehler, warnung = cv_export._nachbearbeiten(pfad)
    assert fehler is None
    assert warnung is not None and "0 Stationen" in warnung


def test_v9_dokument_erzeugt_keine_warnung(tmp_path, monkeypatch):
    from pipeline import cv_export, user_profile

    monkeypatch.setattr(user_profile, "user_name", lambda: "Testname")
    pfad = _docx_v9(tmp_path / "v9_ok.docx", [
        ("Titelzeile", "Firma GmbH\tJan. 2020 – heute", "Beschreibung.", ["Bullet"]),
    ])
    fehler, warnung = cv_export._nachbearbeiten(pfad)
    assert fehler is None
    assert warnung is None


# ── Echte Basis-CVs (nur lokal — data/ ist gitignored, CI skippt sichtbar) ──────────────────
@pytest.mark.skipif(not (_BASIS_DIR / "base_de.docx").exists(),
                    reason="Basis-CVs nicht vorhanden (data/ ist gitignored — lokal-only Test)")
@pytest.mark.parametrize("datei,rubrik", [("base_de.docx", "BERUFSERFAHRUNG"),
                                          ("base_en.docx", "PROFESSIONAL EXPERIENCE")])
def test_basis_cv_hat_v10_struktur(datei, rubrik):
    """v10 (07.08.2026, Lesbarkeits-Vorgabe): je Berufsstation Firma\\tZeitraum →
    Titel (Normal+bold+11pt, KEIN Heading) DIREKT danach → kursive Beschreibung → Bullets;
    die Firma-Zeile trägt den Stations-Abstand (~2 Leerzeilen als space_before). Die
    Beschreibung steht bewusst NICHT zwischen Firma und Titel (Workday-Lehre Phase 76).
    Die 2 Ausbildungszeilen bleiben einzeilig."""
    from docx import Document
    from docx.shared import Pt
    from pipeline import cv_export

    doc = Document(str(_BASIS_DIR / datei))
    absaetze = doc.paragraphs

    heads = [i for i, p in enumerate(absaetze) if cv_export._ist_ueberschrift(p)]
    beruf_start = next(i for i in heads if absaetze[i].text.strip().upper() == rubrik)
    beruf_ende = next((i for i in heads if i > beruf_start), len(absaetze))

    tab_zeilen = [i for i in range(beruf_start + 1, beruf_ende)
                  if cv_export._ist_stationsstart(absaetze[i])]
    assert len(tab_zeilen) == 12, f"{datei}: erwartete 12 Berufsstationen, fand {len(tab_zeilen)}"

    for i in tab_zeilen:
        titel = absaetze[i + 1]
        assert cv_export._ist_stationstitel(titel), \
            f"{datei}: nach Tab-Zeile {i} ({absaetze[i].text[:40]!r}) steht kein Titel"
        assert titel.style.name == "Normal"  # nie Heading (Frontend-Editor-Kontrakt)
        assert all(r.font.size == Pt(11) for r in titel.runs if r.text.strip()), \
            f"{datei}: Titel {titel.text!r} ohne 11pt"
        beschreibung = absaetze[i + 2]
        assert any(r.italic for r in beschreibung.runs), \
            f"{datei}: nach Titel (Tab-Zeile {i}) keine kursive Beschreibung"
        assert (absaetze[i].paragraph_format.space_before or Pt(0)) >= Pt(20), \
            f"{datei}: Tab-Zeile {i} ohne Stations-Abstand (~2 Leerzeilen)"

    # Ausbildung: genau 2 Tab-Zeilen NACH dem Berufserfahrungs-Abschnitt, ohne Titel davor.
    ausbildung = [i for i in range(beruf_ende, len(absaetze))
                  if cv_export._ist_stationsstart(absaetze[i])]
    assert len(ausbildung) == 2, f"{datei}: erwartete 2 Ausbildungszeilen, fand {len(ausbildung)}"


@pytest.mark.skipif(not (_BASIS_DIR / "base_de.docx").exists(),
                    reason="Basis-CVs nicht vorhanden (data/ ist gitignored — lokal-only Test)")
@pytest.mark.parametrize("datei", ["base_de.docx", "base_en.docx"])
def test_basis_cv_kette_erkennt_14_stationen(datei):
    """Der Umbruch-Schutz erkennt am echten Dokument 14 Stationen (12 Beruf + 2 Ausbildung)."""
    from docx import Document
    from pipeline import cv_export

    doc = Document(str(_BASIS_DIR / datei))
    assert cv_export._seitenumbrueche_schuetzen(doc) == 14
