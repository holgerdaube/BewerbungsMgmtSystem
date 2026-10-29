"""CV-Entwurf: Absätze mit weichem Zeilenumbruch (P2-35, 10.09.2026).

Fall A (Rückmeldung): Ein Nutzer trug im CV-Entwurf eine einzige Zeile nach
(„- Sprachzertifikat Level3") und bekam beim Speichern

    Überschrift-Markierung „### " fehlt vor „AI Systems: ChatGPT, Claude, Perplexity, …"

Die Meldung zeigte auf eine Stelle, an der nichts falsch war. URSACHE:
`base_en.docx` führt „Operating Systems: …" und „AI Systems: …" in EINEM Absatz, getrennt durch
einen weichen Umbruch (Shift+Enter, `<w:br/>`). python-docx liefert diesen Absatz als EINEN Block,
dessen `text` ein `\\n` enthält. Der Editor zeigt ihn dadurch über zwei Zeilen — der Parser im
Frontend nahm aber pro Fixed-Block **genau eine** Zeile. Ab dieser Stelle war er eine Zeile voraus
und traf mit dem nächsten Block (Überschrift „LANGUAGES") auf die Zeile „AI Systems: …".

Der Fehler hing NICHT an der Änderung des Nutzers: Ein Round-Trip ohne jede Bearbeitung scheiterte
genauso — **9 von 89 Entwürfen** waren betroffen, alle mit demselben Absatz.

DIESE DATEI sichert die Backend-Hälfte der Kette: Kommt ein mehrzeiliger Text zurück, muss der
weiche Umbruch als `<w:br/>` erhalten bleiben und darf nicht als Literal oder Absatzwechsel enden.
Die Frontend-Hälfte (`JobDetail.tsx::textZuEntwurf` zählt die Zeilen des Blocks) lässt sich hier
nicht testen — im Projekt gibt es keine TS-Tests; sie wurde gegen alle 89 echten Entwürfe
durchgespielt (0 Fehler, 0 Textverlust).

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention).
"""
import pytest


def _docx_mit_weichem_umbruch(pfad, erste="Operating Systems: Windows", zweite="AI Systems: ChatGPT"):
    """Ein Dokument, dessen Absatz 1 zwei Zeilen in EINEM Absatz führt — wie base_en.docx."""
    from docx import Document

    d = Document()
    d.add_paragraph("TECHNICAL SKILLS", style="Heading 1")
    p = d.add_paragraph()
    r = p.add_run(erste)
    r.add_break()
    p.add_run(zweite)
    d.add_paragraph("LANGUAGES", style="Heading 1")
    d.save(str(pfad))
    return pfad


def test_absatz_mit_weichem_umbruch_kommt_als_eine_zeile_mit_n(tmp_path):
    """Die Prämisse des ganzen Falls, festgehalten: python-docx macht daraus EINEN Block.

    Fällt dieser Test, hat sich das Verhalten der Bibliothek geändert — dann gehört der
    Zeilen-Zähler im Frontend überprüft."""
    from docx import Document

    pfad = _docx_mit_weichem_umbruch(tmp_path / "cv.docx")
    absaetze = Document(str(pfad)).paragraphs

    assert absaetze[1].text == "Operating Systems: Windows\nAI Systems: ChatGPT"
    assert len(absaetze) == 3, "zwei Überschriften und EIN Absatz dazwischen"


def test_rueckschreiben_erhaelt_den_weichen_umbruch(tmp_path):
    """DER Kernfall: Der Editor liefert den Block mit `\\n` zurück — daraus muss wieder ein
    weicher Umbruch werden, kein Literal und kein zweiter Absatz.

    Ginge das schief, wäre der Speicher-Fix schlimmer als der Fehler: Die Zeile „AI Systems"
    landete als sichtbares `\\n` im fertigen CV oder risse den Absatz auseinander."""
    from docx import Document

    from pipeline.cv_export import entwurf_zurueckschreiben

    pfad = _docx_mit_weichem_umbruch(tmp_path / "cv.docx")
    neuer_text = "Operating Systems: Windows, Linux\nAI Systems: ChatGPT, Claude, Perplexity"

    entwurf_zurueckschreiben(pfad, [{"i": 1, "text": neuer_text}])

    absaetze = Document(str(pfad)).paragraphs
    assert absaetze[1].text == neuer_text
    assert len(absaetze) == 3, "der Absatz darf nicht in zwei zerfallen"
    xml = absaetze[1]._p.xml
    assert "<w:br/>" in xml or "<w:br />" in xml, "der weiche Umbruch fehlt im XML"
    assert "\\n" not in xml, "der Umbruch darf nicht als Literal im Text stehen"


def test_unveraenderter_absatz_bleibt_voellig_unangetastet(tmp_path):
    """`entwurf_zurueckschreiben` überspringt Absätze, deren Text gleich geblieben ist. Genau
    deshalb hat der Fehler nie Daten beschädigt — er verhinderte nur das Speichern."""
    from docx import Document

    from pipeline.cv_export import entwurf_zurueckschreiben

    pfad = _docx_mit_weichem_umbruch(tmp_path / "cv.docx")
    vorher = Document(str(pfad)).paragraphs[1]._p.xml

    geaendert = entwurf_zurueckschreiben(
        pfad, [{"i": 1, "text": "Operating Systems: Windows\nAI Systems: ChatGPT"}])

    assert geaendert == 0, "gleicher Text → kein Schreibvorgang"
    assert Document(str(pfad)).paragraphs[1]._p.xml == vorher


@pytest.mark.parametrize("zeilen", [1, 2, 3])
def test_beliebig_viele_zeilen_im_selben_absatz(tmp_path, zeilen):
    """Zwei Zeilen sind der reale Fall, aber die Regel darf nicht daran hängen — ein Absatz kann
    beliebig viele weiche Umbrüche tragen."""
    from docx import Document

    from pipeline.cv_export import entwurf_zurueckschreiben

    pfad = _docx_mit_weichem_umbruch(tmp_path / "cv.docx")
    text = "\n".join(f"Zeile {n}" for n in range(zeilen))

    entwurf_zurueckschreiben(pfad, [{"i": 1, "text": text}])

    assert Document(str(pfad)).paragraphs[1].text == text
