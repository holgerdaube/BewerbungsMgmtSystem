"""Kontrakt-Tests fuer pipeline/report_check.py (Phase 57 Stufe E1.4).

Reine Funktion (`pruefe`, HTML-String rein -> Liste von Beanstandungen raus), kein DB-/App-
Zugriff. Der "Chip-Fall" (23.07.2026, s. Moduldocstring von report_check.py): `.chip.pos`/
`.chip.neg` im Markup benutzt, aber nicht im <style> definiert -- Chips erschienen grau statt
gruen/rot. Diese Tests frieren genau dieses Verhalten als eingefrorene Regression ein.
"""

_KONFORMES_HTML = """
<html><head><style>
.chip { padding: 2px; }
.chip.pos { color: green; }
.chip.neg { color: red; }
</style></head>
<body>
<span class="chip pos">Python</span>
<span class="chip neg">Java</span>
</body></html>
"""

# Manipuliert nach dem Chip-Muster: .chip existiert, die bedeutungstragenden Modifikatoren
# .pos/.neg fehlen im <style> -- genau der Fehler, den report_check aufdecken soll.
_MANIPULIERTES_HTML = """
<html><head><style>
.chip { padding: 2px; color: grey; }
</style></head>
<body>
<span class="chip pos">Python</span>
<span class="chip neg">Java</span>
</body></html>
"""


def test_konformes_html_wird_nicht_beanstandet():
    from pipeline.report_check import pruefe

    assert pruefe(_KONFORMES_HTML) == []


def test_manipuliertes_html_wird_beanstandet_kroll_fall():
    from pipeline.report_check import pruefe

    fehler = pruefe(_MANIPULIERTES_HTML)
    assert len(fehler) == 2
    assert any("chip pos" in f and ".pos" in f for f in fehler)
    assert any("chip neg" in f and ".neg" in f for f in fehler)


def test_html_ohne_style_block_wird_beanstandet():
    from pipeline.report_check import pruefe

    fehler = pruefe('<html><body><span class="chip pos">X</span></body></html>')
    assert len(fehler) == 1
    assert "style" in fehler[0].lower()


def test_template_literal_im_class_attribut_wird_nicht_faelschlich_beanstandet():
    """JS-Template-Literale, die (z. B. durch einen Renderer) direkt im class-Attribut LANDEN
    (`class="${badgeClass(r.score)} badge"`), sind keine echten Klassen -- duerfen keinen
    Fehlalarm ausloesen (Moduldocstring: mehrere Company-Fit-Reports bauen Badges per JS
    zusammen). Bewusst NICHT in einem <script>-Block plaziert: der wuerde von
    `_markup_ohne_code()` ohnehin komplett rausgeschnitten, noch bevor die class-Attribute
    ueberhaupt gescannt werden -- das testete dann den falschen Codepfad (Script-Stripping statt
    des `"${" in attr`-Guards in `pruefe()`)."""
    from pipeline.report_check import pruefe

    html = ('<html><head><style>.badge { color: grey; }</style></head>'
            '<body><span class="${badgeClass(r.score)} badge">X</span></body></html>')
    assert pruefe(html) == []
