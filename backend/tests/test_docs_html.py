"""Tests für `pipeline/docs_render.py` (Phase 83 Arbeitspaket D1) — Markdown ist die Quelle,
`docs/*.html` wird generiert, nie von Hand gepflegt. Auslöser war `docs/DOKUMENTATION.html`:
zwei Wochen lang handgebaut parallel zur `.md` gepflegt, unbemerkt auseinandergelaufen (trug
noch die alten Farben `#0aa7c2` statt dem §18-Cyan `#00B4D8`).

Deckt vier Dinge ab:
  1. Renderer-Grundfälle (Tabelle, Codeblock, verschachtelte Liste, Blockquote, Umlaute,
     XSS-Sicherheit) + Determinismus — ausschließlich in `tmp_path` bzw. rein im Speicher.
  2. Liste direkt nach Absatz ohne Leerzeile (Nachtrag 12.08.2026, s. Abschnitt weiter unten) —
     `_leerzeile_vor_listen_einfuegen()` normalisiert das VOR dem Parsen; Fortsetzungszeilen und
     Codezaun-Inhalt bleiben dabei unangetastet.
  3. Der `--pruefen`-Guard erkennt fehlende/veraltete HTML zuverlässig und benennt die Datei.
     Nachtrag 12.08.2026: `_guard_meldung()` vergleicht seither das GESAMTE gerenderte Ergebnis
     byte-genau statt nur einen im HTML hinterlegten Quell-Hash — ein reiner Hash-Vergleich
     erkennt eine geänderte `.md` zuverlässig, bleibt aber blind für einen geänderten RENDERER
     (genau das passierte: die Listen-Vorverarbeitung machte alle 12 docs/*.html veraltet, ohne
     dass sich eine einzige .md änderte, der Hash-Guard blieb fälschlich grün). Der Kommentar
     `<!-- docs_render … sha256=… -->` bleibt im HTML erhalten, dient aber nur noch der
     Rückverfolgbarkeit, nicht mehr der Prüfung selbst.
  4. Der ECHTE `docs/`-Ordner ist paarig (jede `.md` hat eine inhaltsgleiche, aktuelle `.html`).
     Dieser eine Test schlägt jetzt ERWARTUNGSGEMÄSS fehl — die auf der Platte liegenden HTMLs
     stammen vom alten Renderer-Stand (vor dem Ergebnis-Vergleich-Nachtrag), die Hauptsession
     rendert im Anschluss neu. Er ist ein reiner Lesetest und schreibt NICHTS in `docs/`.

Kein app.*/pipeline.*-Import auf Modulebene (conftest-Konvention, s. tests/conftest.py) — auch
wenn `pipeline.docs_render` weder DATA_DIR noch LOG_DIR bindet, bleibt die Datei konsistent mit
den Nachbartests (test_coach_export_*.py)."""


def _render(quelltext: str, dateiname: str = "TEST.md") -> str:
    from pipeline import docs_render
    return docs_render.render_markdown(quelltext, dateiname)


# ── Renderer-Grundfälle ──────────────────────────────────────────────────────────────────

def test_tabelle_wird_zu_html_tabelle():
    html_out = _render("# T\n\n## Abschnitt\n\n| A | B |\n|---|---|\n| 1 | 2 |\n")
    assert "<table>" in html_out
    assert "<th>A</th>" in html_out and "<th>B</th>" in html_out
    assert "<td>1</td>" in html_out and "<td>2</td>" in html_out
    # Spec: breite Tabellen bekommen einen scrollbaren Container.
    assert '<div class="tablewrap"><table>' in html_out


def test_code_block_bleibt_formatiert_und_wird_escaped():
    quelltext = "# T\n\n## Abschnitt\n\n```python\nprint('<b>x</b>')\n```\n"
    html_out = _render(quelltext)
    assert "<pre>" in html_out and '<code class="language-python">' in html_out
    # Inhalt korrekt escaped (fenced_code escaped < > & " selbst, NICHT das Anführungszeichen ').
    assert "print('&lt;b&gt;x&lt;/b&gt;')" in html_out
    # Darf NIEMALS als echtes <b>-Tag im Dokument landen.
    assert "<b>x</b>" not in html_out


def test_verschachtelte_liste_wird_korrekt_geschachtelt():
    quelltext = "# T\n\n## Abschnitt\n\n- a\n    - a1\n    - a2\n- b\n\n1. eins\n    1. eins-a\n2. zwei\n"
    html_out = _render(quelltext)
    assert html_out.count("<ul>") == 2  # äußere + eine verschachtelte Liste
    assert "<li>a<ul>" in html_out
    assert "<li>a1</li>" in html_out and "<li>a2</li>" in html_out
    assert "<li>eins<ol>" in html_out  # ol-in-ol genauso verschachtelt


# ── Liste direkt nach Absatz, ohne Leerzeile (Python-Markdown ↔ CommonMark/GitHub) ────────
# Nachtrag zur Abnahme 12.08.2026: Python-Markdown erkennt (anders als CommonMark/GitHub) eine
# Liste NICHT, wenn sie ohne Leerzeile direkt auf einen Textabsatz folgt -- die Zeilen landen als
# Fließtext mit sichtbaren Bindestrichen/Ziffern statt als <ul>/<ol>. Fund: 195 Stellen in 11 von
# 12 docs/*.md folgen diesem (auf GitHub korrekt gerenderten) Muster. Die .md-Quellen sind NICHT
# falsch -- render_markdown() normalisiert das selbst (_leerzeile_vor_listen_einfuegen()).

def test_liste_direkt_nach_absatz_ohne_leerzeile_wird_ul():
    quelltext = ("# T\n\n## Abschnitt\n\n**Was dein Coach sieht:**\n"
                 "- Eine Übersicht mit Kennzahlen\n"
                 "- Die Liste deiner Stellen\n")
    html_out = _render(quelltext)
    assert "<ul>" in html_out
    assert "<li>Eine Übersicht mit Kennzahlen</li>" in html_out
    assert "<li>Die Liste deiner Stellen</li>" in html_out
    # Der ursprüngliche Bug: Bindestrich-Zeilen blieben Teil DESSELBEN <p> wie der Absatz davor.
    assert "- Eine Übersicht mit Kennzahlen</p>" not in html_out


def test_ordered_liste_direkt_nach_absatz_ohne_leerzeile_wird_ol():
    quelltext = "# T\n\n## Abschnitt\n\nSchritte:\n1. Erstens\n2. Zweitens\n"
    html_out = _render(quelltext)
    assert "<ol>" in html_out
    assert "<li>Erstens</li>" in html_out and "<li>Zweitens</li>" in html_out


def test_fortsetzungszeile_bleibt_kompakt_kein_p_im_li():
    """Fortsetzungszeile (eingerückter Text nach einem Listenpunkt) darf KEINE Leerzeile
    bekommen -- sonst wird aus einer kompakten eine lose Liste (jedes <li> ein eigenes <p>)."""
    quelltext = ("# T\n\n## Abschnitt\n\nText davor.\n"
                 "- Punkt eins\n  Fortsetzung des Punktes\n- Punkt zwei\n")
    html_out = _render(quelltext)
    assert "<li>Punkt eins\n  Fortsetzung des Punktes</li>" in html_out
    assert "<li>Punkt zwei</li>" in html_out
    # Kompakte Liste: kein <p> innerhalb eines <li>.
    section = html_out[html_out.index("<ul>"):html_out.index("</ul>") + 5]
    assert "<p>" not in section


def test_bindestrich_zeile_im_codeblock_bleibt_unveraendert():
    """Eine Bindestrich-/Ziffern-Zeile INNERHALB eines Codezauns ist Text, keine Liste -- die
    Vorverarbeitung darf dort keine Leerzeile einfügen (würde den Codeblock aufspalten/verändern)."""
    quelltext = ("# T\n\n## Abschnitt\n\nBeispielausgabe:\n"
                 "```\n- nicht anfassen\n- bleibt Text\n1. auch das bleibt Text\n```\n")
    html_out = _render(quelltext)
    assert "<pre>" in html_out
    assert "<code>- nicht anfassen\n- bleibt Text\n1. auch das bleibt Text\n</code>" in html_out


def test_liste_nach_ueberschrift_tabelle_zitat_bekommt_keine_zusaetzliche_leerzeile():
    """Vorzeile Überschrift/Tabelle/Zitat: keine Einfügung (Absatz-Vorlauf-Problem betrifft nur
    echte Fließtext-Absätze; bei '>' würde eine nackte Leerzeile das Zitat sogar vorzeitig
    beenden, bei '|' eine Tabelle zerreißen)."""
    from pipeline import docs_render

    nach_ueberschrift = docs_render._leerzeile_vor_listen_einfuegen("## Überschrift\n- item\n")
    assert nach_ueberschrift == "## Überschrift\n- item\n"

    nach_tabelle = docs_render._leerzeile_vor_listen_einfuegen("| A | B |\n|---|---|\n- item\n")
    assert nach_tabelle == "| A | B |\n|---|---|\n- item\n"

    nach_zitat = docs_render._leerzeile_vor_listen_einfuegen("> Zitat\n- item\n")
    assert nach_zitat == "> Zitat\n- item\n"


def test_verschachtelte_liste_nach_absatz_bekommt_nur_eine_leerzeile():
    quelltext = "# T\n\n## Abschnitt\n\nText.\n- a\n    - a1\n    - a2\n- b\n"
    html_out = _render(quelltext)
    assert html_out.count("<ul>") == 2
    assert "<li>a<ul>" in html_out


def test_tabelle_in_liste_bricht_listenkontext_naechster_punkt_bleibt_erkennbar():
    """Regressionsfall docs/SETUP-EMAIL.md: Python-Markdowns `tables`-Extension schließt eine
    offene Liste vorzeitig, sobald eine (auch eingerückte) Tabelle folgt -- der Absatz danach
    zählt für den Parser nicht mehr als Listen-Fortsetzung. Ohne das Zurücksetzen des
    Listenkontexts bei einer Tabellenzeile würde der übernächste Listenpunkt fälschlich als
    Fließtext hinter diesem Absatz landen (exakt der gemeldete Bug, nur zwei Schritte
    versetzt)."""
    quelltext = ("# T\n\n## Abschnitt\n\n"
                 "2. Zweiter Punkt:\n\n"
                 "   | A | B |\n   |---|---|\n   | 1 | 2 |\n\n"
                 "   Text nach der Tabelle.\n"
                 "3. Dritter Punkt.\n")
    html_out = _render(quelltext)
    assert "<li>Dritter Punkt.</li>" in html_out
    # Der ursprüngliche Bug: "3. Dritter Punkt." blieb Text IM SELBEN <p> wie der Absatz davor.
    assert "Text nach der Tabelle.\n3. Dritter Punkt." not in html_out


def test_blockquote_wird_als_hinweisbox_gerendert():
    quelltext = "# T\n\n## Abschnitt\n\n> Hinweis: das ist **wichtig**.\n> Zweite Zeile.\n"
    html_out = _render(quelltext)
    assert "<blockquote>" in html_out
    assert "Hinweis: das ist <strong>wichtig</strong>." in html_out
    # Es gibt tatsächlich eine eigene Hinweis-Box-Optik dafür (kein nackter Browser-Default).
    assert "blockquote{background:" in html_out


def test_umlaute_bleiben_erhalten():
    quelltext = "# Übermäßig große Prüfung\n\n## Abschnitt\n\nÄÖÜäöüß bleiben, köstlich.\n"
    html_out = _render(quelltext)
    assert "Übermäßig große Prüfung" in html_out
    assert "ÄÖÜäöüß bleiben, köstlich." in html_out


def test_rohes_inline_html_wird_escaped_kein_xss_loch():
    quelltext = ("# T\n\n## Abschnitt\n\n"
                 "Platzhalter ohne Codeauszeichnung: <DEIN-API-KEY>.\n\n"
                 "Beispiel-Markup direkt im Fließtext: <script>alert(1)</script>\n")
    html_out = _render(quelltext)
    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_out
    assert "<DEIN-API-KEY>" not in html_out
    assert "&lt;DEIN-API-KEY&gt;" in html_out


def test_block_level_rohes_html_wird_escaped():
    quelltext = ('# T\n\n## Abschnitt\n\nText davor.\n\n'
                 '<div onclick="alert(1)">Block</div>\n\nText danach.\n')
    html_out = _render(quelltext)
    assert '<div onclick="alert(1)">' not in html_out
    assert "&lt;div onclick=" in html_out


def test_seite_ist_self_contained_ohne_externe_ressourcen():
    html_out = _render("# T\n\n## Abschnitt\n\nInhalt.\n")
    assert "http://" not in html_out
    assert "https://" not in html_out
    assert "<script" not in html_out


def test_ueberschrift_in_codezaun_wird_nicht_als_abschnitt_missverstanden():
    """Regressionsfall docs/BEIRAT-PERSONA-TEMPLATE.md: eine Beispiel-Überschrift INNERHALB
    eines Codezauns darf keine neue Karte erzeugen."""
    quelltext = ("# T\n\n## Echter Abschnitt\n\nText.\n\n"
                 "```markdown\n# Vorlagen-Überschrift\n## Noch eine\n```\n\n"
                 "Text danach.\n")
    html_out = _render(quelltext)
    assert html_out.count('<section class="card">') == 1
    assert "# Vorlagen-Überschrift" in html_out  # blieb als Text im Codeblock erhalten


# ── Determinismus ────────────────────────────────────────────────────────────────────────

def test_determinismus_zweimal_rendern_byte_identisch(tmp_path):
    from pipeline import docs_render

    quelltext = (
        "# Übung — Determinismus\n\n*Stand: 12.08.2026*\n\n---\n\n"
        "## Erster Abschnitt\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n"
        "> Hinweis: wichtig.\n\n- a\n    - a1\n- b\n\n"
        "```sh\necho 'Ärger <> Freude'\n```\n\n"
        "Liste ohne Leerzeile davor:\n- x\n- y\n\n"  # exerciert _leerzeile_vor_listen_einfuegen()
        "## Zweiter Abschnitt\n\nÄÖÜ Text.\n")
    md_pfad = tmp_path / "DET.md"
    md_pfad.write_text(quelltext, encoding="utf-8")

    ziel1 = docs_render.render_und_schreiben(md_pfad)
    bytes1 = ziel1.read_bytes()
    ziel2 = docs_render.render_und_schreiben(md_pfad)
    bytes2 = ziel2.read_bytes()
    assert bytes1 == bytes2


# ── Guard (--pruefen): Ergebnis-Vergleich, nicht nur Quell-Hash ──────────────────────────

def test_guard_fehlt_dann_aktuell_nach_dem_rendern(tmp_path):
    from pipeline import docs_render

    md_pfad = tmp_path / "G.md"
    md_pfad.write_text("# G\n\n## A\n\nInhalt.\n", encoding="utf-8")

    fehler = docs_render.pruefen([md_pfad])
    assert len(fehler) == 1
    assert "G.html" in fehler[0] and "fehlt" in fehler[0]
    assert "scripts/docs_html.sh" in fehler[0]

    docs_render.render_und_schreiben(md_pfad)
    assert docs_render.pruefen([md_pfad]) == []


def test_guard_erkennt_veraenderten_rumpf_trotz_passendem_quell_hash(tmp_path):
    """DER Fall, der beim reinen Hash-Vergleich durchgerutscht wäre (Nachtrag 12.08.2026): die
    .md-Quelle ist unverändert (der Hash-Kommentar im HTML passt also weiterhin zu ihr), aber
    der gerenderte RUMPF weicht ab -- simuliert exakt "Renderer hat sich geändert, Quelle
    nicht". Ein Guard, der nur den Kommentar prüft, hätte das übersehen; der Ergebnis-Vergleich
    (voller Byte-für-Byte-Abgleich) muss anschlagen."""
    from pipeline import docs_render

    md_pfad = tmp_path / "R.md"
    md_pfad.write_text("# R\n\n## A\n\nInhalt.\n", encoding="utf-8")
    ziel = docs_render.render_und_schreiben(md_pfad)
    assert docs_render.pruefen([md_pfad]) == []

    # Nur den RUMPF manipulieren, der (weiterhin gültige) Hash-Kommentar am Dateiende bleibt
    # unangetastet -- genau das hätte ein Hash-only-Vergleich als "aktuell" durchgewunken.
    manipuliert = ziel.read_text(encoding="utf-8").replace("Inhalt.", "Anderer Inhalt.", 1)
    assert manipuliert != ziel.read_text(encoding="utf-8")  # Testfixture-Sicherheitsnetz
    ziel.write_text(manipuliert, encoding="utf-8")

    fehler = docs_render.pruefen([md_pfad])
    assert len(fehler) == 1
    assert "R.html" in fehler[0] and "veraltet" in fehler[0]
    assert "scripts/docs_html.sh" in fehler[0]


def test_guard_schlaegt_bei_geaenderter_quelle_an_und_nennt_datei(tmp_path):
    from pipeline import docs_render

    md_pfad = tmp_path / "G.md"
    md_pfad.write_text("# G\n\n## A\n\nInhalt.\n", encoding="utf-8")
    docs_render.render_und_schreiben(md_pfad)
    assert docs_render.pruefen([md_pfad]) == []

    md_pfad.write_text("# G\n\n## A\n\nInhalt geändert.\n", encoding="utf-8")
    fehler = docs_render.pruefen([md_pfad])
    assert len(fehler) == 1
    assert "G.html" in fehler[0]
    assert "veraltet" in fehler[0]
    assert "scripts/docs_html.sh" in fehler[0]

    # Erneut rendern macht es wieder grün.
    docs_render.render_und_schreiben(md_pfad)
    assert docs_render.pruefen([md_pfad]) == []


def test_cli_pruefen_exit_codes(tmp_path):
    from pipeline import docs_render

    md_pfad = tmp_path / "C.md"
    md_pfad.write_text("# C\n\n## A\n\nx\n", encoding="utf-8")

    assert docs_render.main(["--pruefen", "--datei", str(md_pfad)]) == 1
    docs_render.render_und_schreiben(md_pfad)
    assert docs_render.main(["--pruefen", "--datei", str(md_pfad)]) == 0


def test_cli_rendert_einzelne_datei(tmp_path):
    from pipeline import docs_render

    md_pfad = tmp_path / "E.md"
    md_pfad.write_text("# E\n\n## A\n\nInhalt.\n", encoding="utf-8")
    rc = docs_render.main(["--datei", str(md_pfad)])
    assert rc == 0
    assert (tmp_path / "E.html").is_file()


# ── Paarigkeit im echten docs/-Ordner ────────────────────────────────────────────────────

def test_paarigkeit_im_echten_docs_ordner():
    """Zu jeder echten docs/*.md muss eine gleichnamige .html existieren, deren Inhalt BYTE-
    GENAU dem entspricht, was der AKTUELLE Renderer aus der AKTUELLEN Quelle erzeugen würde.
    Reiner Lesetest (docs_render.pruefen() schreibt nie etwas) -- schlägt an, solange die HTMLs
    noch fehlen, ihre Quelle sich seither geändert hat ODER der Renderer sich geändert hat, und
    sagt in der Fehlermeldung, was zu tun ist."""
    from pipeline import docs_render

    md_dateien = sorted(docs_render._DOCS_DIR.glob("*.md"))
    assert md_dateien, "keine docs/*.md gefunden — Projektstruktur/PROJECT_ROOT geprüft?"

    fehler = docs_render.pruefen(md_dateien)
    assert not fehler, (
        "docs/*.html ist nicht (mehr) vollständig aktuell — vom Projekt-Root "
        "`scripts/docs_html.sh` ausführen, um alle docs/*.md neu zu rendern. Details:\n"
        + "\n".join(fehler))


def test_geschriebene_html_hat_immer_lf_zeilenenden(tmp_path):
    """Die Ausgabe muss auf JEDER Plattform byte-gleich sein — sonst schlägt der
    Ergebnis-Vergleich in `pruefen()` grundlos an.

    CI-Fund 12.08.2026 (Job `backend-windows`): ohne `newline="\\n"` übersetzt Python beim
    Schreiben in die Zeilenenden-Konvention des Betriebssystems, auf Windows also CRLF. Der
    Guard verglich dann eine CRLF-Datei gegen frisch gerendertes LF und meldete jede Doku-Seite
    als „veraltet"; ein Windows-Lauf von `scripts/docs_html.sh` hätte zudem alle 12 Dateien
    scheinbar geändert. Zweite Hälfte der Absicherung ist `.gitattributes` (`* text=auto eol=lf`),
    damit der Checkout die Dateien gar nicht erst umschreibt."""
    from pipeline import docs_render

    md = tmp_path / "ZEILENENDEN.md"
    md.write_text("# Titel\n\nEin Absatz\n\n- Punkt eins\n- Punkt zwei\n", encoding="utf-8")

    ziel = docs_render.render_und_schreiben(md)
    rohbytes = ziel.read_bytes()

    assert b"\r\n" not in rohbytes, "HTML enthält CRLF — write_text ohne newline='\\n'?"
    assert b"\n" in rohbytes
    # Und der Guard ist mit der eben geschriebenen Datei zufrieden (Gegenprobe auf derselben
    # Plattform — genau das schlug auf Windows fehl).
    assert docs_render.pruefen([md]) == []
