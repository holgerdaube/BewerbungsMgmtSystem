"""Seitenumbruch-Schutz setzt die „keep“-Flags neu statt sie anzuhäufen (P2-47, 25.09.2026).

Fall A (Rückmeldung): „da ist zuviel auf die zweite Seite gerutscht. Ist das ein
neuer Bug oder wo kommt der Fehler her?" Gemessen an den echten Dateien trug der CV nach dem
ZWEITEN `cv-erstellen` 109 statt 87 Absätze mit `keep_with_next`, darunter der letzte Absatz
jeder Station und die Listen „Zertifikate“/„Vorträge“ außerhalb aller Stationen. Verkettete
Stationen kann Word nicht umbrechen — der ganze Block rutscht auf die Folgeseite, davor bleibt
eine Lücke.

HERKUNFT: `_bullet_gruppe_anwenden()` klont für neue Bullets einen bestehenden Bullet-Absatz per
`copy.deepcopy` — mitsamt `pPr` und damit den Flags des vorigen Laufs (`_bullet_vorlage` liefert
den ersten Bullet des Dokuments, der mitten in Station 1 steht). `_seitenumbrueche_schuetzen`
setzte Flags bis dahin nur und löschte nie, also überlebten die geerbten.

Die Tests bauen ihre Dokumente selbst (python-docx, keine Fixture-Datei) — geprüft wird die reine
Formatier-Logik, nicht der Export-Pfad.
"""
import pytest


def _dokument():
    """Minimal-CV im v9-Format: Überschrift, zwei Stationen mit Tab-Anker, danach eine Liste
    außerhalb jeder Station (Muster „Zertifikate“)."""
    import docx

    d = docx.Document()
    d.add_paragraph("BERUFSERFAHRUNG", style="Heading 1")
    for firma, jahr in (("Alpha GmbH", "2020 – heute"), ("Beta AG", "2015 – 2020")):
        d.add_paragraph("Titel der Rolle")
        d.add_paragraph(f"{firma}\t{jahr}")
        for i in range(3):
            d.add_paragraph(f"Aufgabe {i} bei {firma}", style="List Paragraph")
    d.add_paragraph("ZERTIFIKATE", style="Heading 1")
    for i in range(3):
        d.add_paragraph(f"Zertifikat {i}", style="List Paragraph")
    return d


def _flags(doc):
    return [(bool(p.paragraph_format.keep_with_next), bool(p.paragraph_format.keep_together))
            for p in doc.paragraphs]


def test_schutz_ist_stabil_wenn_er_zweimal_laeuft():
    """Grundfall (galt schon vorher): zweimal anwenden ändert nichts."""
    from pipeline.cv_export import _seitenumbrueche_schuetzen

    d = _dokument()
    _seitenumbrueche_schuetzen(d)
    einmal = _flags(d)
    _seitenumbrueche_schuetzen(d)

    assert _flags(d) == einmal


def test_geerbte_flags_werden_entfernt():
    """Der eigentliche P2-47-Fix: Flags, die NICHT von dieser Funktion stammen (hier simuliert
    wie beim Klonen eines Bullets), verschwinden. Ohne das Zurücksetzen bliebe die Verkettung
    über die Stationsgrenze hinweg bestehen."""
    from pipeline.cv_export import _seitenumbrueche_schuetzen

    d = _dokument()
    sauber = _seitenumbrueche_schuetzen(d) and _flags(d)

    schmutzig = _dokument()
    for p in schmutzig.paragraphs:                 # jeder Absatz trägt fremde Flags
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.keep_together = True
    _seitenumbrueche_schuetzen(schmutzig)

    assert _flags(schmutzig) == sauber


def test_letzter_absatz_einer_station_haengt_nicht_am_naechsten():
    """Genau das Symptom aus dem Echtfall: Der letzte Bullet einer Station darf die Folgestation
    nicht an sich binden, sonst werden beide zu einem unteilbaren Block."""
    from pipeline.cv_export import _seitenumbrueche_schuetzen, _stationsgrenzen

    d = _dokument()
    for p in d.paragraphs:                          # Ausgangslage wie nach einem Vorlauf
        p.paragraph_format.keep_with_next = True
    _seitenumbrueche_schuetzen(d)

    ps = d.paragraphs
    grenzen = _stationsgrenzen(ps)
    assert len(grenzen) == 2, "Testdokument muss zwei Stationen haben"
    # Der Absatz VOR einer Stationsgrenze schließt die vorige Station ab und darf die nächste
    # nicht an sich binden. (Die Grenze selbst ist je nach CV-Format die Titel- oder die
    # Tab-Zeile — deshalb wird hier über `_stationsgrenzen` gerechnet, nicht über feste Indizes.)
    vor_der_zweiten = grenzen[1] - 1
    assert ps[vor_der_zweiten].paragraph_format.keep_with_next is not True


def test_liste_ausserhalb_der_stationen_bleibt_frei():
    """Die Zertifikats-Liste hinter der letzten Station gehört zu keiner Station — sie darf nach
    einem Lauf keine Flags tragen (im Echtfall trug sie welche und wanderte als Block)."""
    from pipeline.cv_export import _seitenumbrueche_schuetzen

    d = _dokument()
    for p in d.paragraphs:
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.keep_together = True
    _seitenumbrueche_schuetzen(d)

    zertifikate = [p for p in d.paragraphs if p.text.startswith("Zertifikat ")]
    assert len(zertifikate) == 3
    for p in zertifikate:
        assert p.paragraph_format.keep_with_next is not True
        assert p.paragraph_format.keep_together is not True


def test_ueberschrift_haelt_weiter_am_folgeabsatz():
    """Gegenprobe: Das Zurücksetzen darf den eigentlichen Zweck nicht wegnehmen."""
    from pipeline.cv_export import _ist_ueberschrift, _seitenumbrueche_schuetzen

    d = _dokument()
    _seitenumbrueche_schuetzen(d)

    ueberschriften = [p for p in d.paragraphs if _ist_ueberschrift(p)]
    assert ueberschriften
    for p in ueberschriften:
        assert p.paragraph_format.keep_with_next is True
