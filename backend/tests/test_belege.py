"""Belegprüfung `pipeline/belege.py` (P2-97 Stufe A).

Geprüft wird:
  * `zitat_belegt`: wörtlicher Treffer trotz Groß/klein, Zeilenumbruch, typografischer Zeichen und
    weichem Trennzeichen; Auslassung nur in Reihenfolge; zu kurze Zitate und Teile zählen nie;
    Umschreibungen und leere Eingaben zählen nie;
  * `docx_text`: Absätze und Tabellenzellen (auch verschachtelt) in Dokumentreihenfolge;
  * CLI `pruefen`: Exit 0, 1, 2 und eine Zeile auf Deutsch.
Alle Texte, Firmen und Namen sind erfunden.
"""
import pytest

from pipeline import belege

CV = (
    "Berufserfahrung\n"
    "Leiter Professional Services, Beispiel GmbH, 2019–2024\n"
    "Aufbau eines Delivery-Teams von 4 auf 18 Beratende in drei Jahren\n"
    "Verantwortung für einen Projekt-Backlog von 6,5 Mio. EUR\n"
    "Einführung eines „Customer First“-Programms mit NPS +22\n"
    "Kenntnisse: Stakeholder Management, P&L, Presales"
)


# ── zitat_belegt ────────────────────────────────────────────────────────────────────────────

def test_woertliches_zitat_trifft():
    assert belege.zitat_belegt("Aufbau eines Delivery-Teams von 4 auf 18 Beratende", CV)


def test_gross_klein_und_rand_satzzeichen_egal():
    assert belege.zitat_belegt("aufbau eines DELIVERY-teams von 4 auf 18 beratende.", CV)


def test_zeilenumbruch_und_mehrfache_leerzeichen_egal():
    quelle = "Verantwortung für einen\nProjekt-Backlog   von 6,5 Mio. EUR"
    assert belege.zitat_belegt("Verantwortung für einen Projekt-Backlog von 6,5 Mio. EUR", quelle)


def test_typografische_zeichen_werden_ausgeglichen():
    # Zitat mit geraden Anführungszeichen, CV mit typografischen; Gedankenstrich gegen Bindestrich
    assert belege.zitat_belegt('Einführung eines "Customer First"-Programms', CV)
    assert belege.zitat_belegt("Beispiel GmbH, 2019-2024", CV)


def test_weiches_trennzeichen_und_geschuetztes_leerzeichen():
    quelle = "Projekt­Backlog von 6,5 Mio. EUR verantwortet"
    assert belege.zitat_belegt("ProjektBacklog von 6,5 Mio. EUR", quelle)


@pytest.mark.parametrize("auslassung", ["…", "...", "[...]", " [ … ] "])
def test_auslassung_in_reihenfolge_trifft(auslassung):
    zitat = f"Leiter Professional Services{auslassung}Projekt-Backlog von 6,5 Mio. EUR"
    assert belege.zitat_belegt(zitat, CV)


def test_auslassung_in_falscher_reihenfolge_trifft_nicht():
    assert not belege.zitat_belegt("Projekt-Backlog von 6,5 Mio. EUR … Leiter Professional Services", CV)


def test_zu_kurzes_zitat_zaehlt_nie():
    assert "presales" in belege.normalisieren(CV)
    assert not belege.zitat_belegt("Presales", CV)


def test_zu_kurzer_teil_nach_auslassung_macht_zitat_ungueltig():
    assert not belege.zitat_belegt("Aufbau eines Delivery-Teams … P&L", CV)


def test_umschreibung_ist_kein_beleg():
    assert not belege.zitat_belegt("Delivery-Team von 4 auf 18 Personen ausgebaut", CV)


def test_erfundene_zahl_ist_kein_beleg():
    assert not belege.zitat_belegt("Verantwortung für einen Projekt-Backlog von 8 Mio. EUR", CV)


@pytest.mark.parametrize("zitat, quelle", [("", CV), (None, CV), ("…", CV),
                                           ("Aufbau eines Delivery-Teams", ""),
                                           ("Aufbau eines Delivery-Teams", None)])
def test_leere_eingaben(zitat, quelle):
    assert not belege.zitat_belegt(zitat, quelle)


# ── docx_text ───────────────────────────────────────────────────────────────────────────────

def _docx_mit_tabelle(pfad):
    from docx import Document

    doc = Document()
    doc.add_paragraph("Profil: Leitung von Delivery-Organisationen")
    tabelle = doc.add_table(rows=1, cols=2)
    tabelle.cell(0, 0).text = "Beispiel GmbH, 2019–2024"
    zelle = tabelle.cell(0, 1)
    zelle.text = "Aufbau eines Delivery-Teams von 4 auf 18 Beratende"
    innen = zelle.add_table(rows=1, cols=1)
    innen.cell(0, 0).text = "Verschachtelt: Projekt-Backlog von 6,5 Mio. EUR"
    doc.add_paragraph("Ausbildung: Diplom-Kaufmann")
    doc.save(str(pfad))
    return pfad


def test_docx_text_mit_tabellen_in_reihenfolge(tmp_path):
    text = belege.docx_text(_docx_mit_tabelle(tmp_path / "cv.docx"))
    for teil in ("Profil: Leitung", "Beispiel GmbH, 2019–2024", "Aufbau eines Delivery-Teams",
                 "Verschachtelt: Projekt-Backlog", "Ausbildung: Diplom-Kaufmann"):
        assert teil in text
    assert text.index("Profil:") < text.index("Beispiel GmbH") < text.index("Verschachtelt") < text.index("Ausbildung")
    assert belege.zitat_belegt("Profil: Leitung von Delivery-Organisationen … Ausbildung: Diplom-Kaufmann", text)


# ── CLI ─────────────────────────────────────────────────────────────────────────────────────

def test_cli_gefunden(tmp_path, capsys):
    pfad = _docx_mit_tabelle(tmp_path / "cv.docx")
    assert belege.main(["pruefen", "--datei", str(pfad), "--zitat", "Projekt-Backlog von 6,5 Mio. EUR"]) == 0
    assert capsys.readouterr().out.startswith("GEFUNDEN")


def test_cli_nicht_gefunden_und_zu_kurz(tmp_path, capsys):
    pfad = tmp_path / "cv.txt"
    pfad.write_text(CV, encoding="utf-8")
    assert belege.main(["pruefen", "--datei", str(pfad), "--zitat", "Team von 30 Beratenden geführt"]) == 1
    assert "steht nicht wörtlich" in capsys.readouterr().out
    assert belege.main(["pruefen", "--datei", str(pfad), "--zitat", "P&L"]) == 1
    assert "kürzer als 12 Zeichen" in capsys.readouterr().out


@pytest.mark.parametrize("name, inhalt", [("fehlt.docx", None), ("kaputt.docx", b"kein zip")])
def test_cli_datei_fehlt_oder_kaputt(tmp_path, capsys, name, inhalt):
    pfad = tmp_path / name
    if inhalt is not None:
        pfad.write_bytes(inhalt)
    assert belege.main(["pruefen", "--datei", str(pfad), "--zitat", "Aufbau eines Delivery-Teams"]) == 2
    assert capsys.readouterr().out.startswith("FEHLER")
