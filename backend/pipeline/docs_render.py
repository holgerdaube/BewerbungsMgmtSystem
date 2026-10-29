#!/usr/bin/env python3
"""Docs-Renderer (Phase 83 Arbeitspaket D1) — Markdown ist die Quelle, HTML wird ERZEUGT.

Auslöser: die Doku hinkte zwei Wochen hinterher, weil `docs/DOKUMENTATION.html` handgebaut
gepflegt wurde — parallel zur `.md`, garantiert irgendwann inkonsistent (sie trug noch die
alten Farben `#0aa7c2` statt dem §18-Cyan `#00B4D8`, s. Bau-Spec Phase 83 D1). Deshalb jetzt
Doppelpflege-Verbot: `docs/*.md` bleibt die einzige Quelle der Wahrheit, `docs/*.html` wird
IMMER aus ihr generiert (deterministisch, ohne LLM, Vorbild `pipeline/coach_export.py`) —
und `--pruefen` macht eine vergessene Neu-Erzeugung testbar rot, statt still zu veralten.

DESIGN: §18-Token-Look angelehnt an `docs/ANLEITUNG_COACH_SITE.html` (bestes vorhandenes
Muster) — Navy-Kopfbanner mit dem H1-Titel der Datei, danach je `##`-Abschnitt eine weiße
Karte. Self-contained (kein externes CSS/JS/Bild/Webfont), neutral (kein Logo, kein
Firmenname), Favicon als Data-URI (`app/favicon.py`).

P2-72 (Design aus einer Quelle): Die Markenwerte im CSS (Farben, Icon) kommen aus `pipeline/design.py`,
bei jedem Aufruf frisch gelesen, nie beim Import. Die mitgelieferten `docs/*.html` und ihre Prüfung
(`render_datei`, `render_und_schreiben`, `pruefen`) rendern IMMER mit der Vorgabe (`design.vorgabe()`),
damit der Vergleich mit den eingecheckten Dateien stabil bleibt, egal welches Design bei einem Kunden
gilt. Die Doku-Ansicht in der App (`app/doku.py`) übergibt das geltende Design (`design.laden()`).
Mit der Vorgabe entsteht byte-genau das HTML von vorher.

ABSCHNITTS-ZERLEGUNG: Wir schneiden NICHT den Markdown-Quelltext an `^## `-Zeilen (fragil:
ein Dokument KANN eine Beispiel-Überschrift in einem Codezaun enthalten — genau das tut
`docs/BEIRAT-PERSONA-TEMPLATE.md` in seiner Kopiervorlage). Stattdessen wird einmal komplett
zu HTML gerendert und ERST DANN an den `<h1>`/`<h2>`-Tags geschnitten (`_zerlege`). Das ist
robust, weil `PrettifyTreeprocessor` jede Top-Level-Überschrift garantiert bei Spaltenposition
0 in eigener Zeile ausgibt — Überschriften in Zitaten (brauchen ein `>`-Präfix) oder Listen
(brauchen Einrückung) sind zwangsläufig NICHT auf Spalte 0, und Überschriften in Codezäunen
sind zu diesem Zeitpunkt bereits reiner Text innerhalb von `<pre><code>` (fenced_code stasht
seinen fertigen, selbst-escapten Block VOR jeder Block-Erkennung, Priorität 25 vs. 20).

XSS/PLATZHALTER-FALLE: Python-Markdown gibt roh erkanntes HTML per Design UNVERÄNDERT durch
(Kernfeature, kein Bug — Markdown erlaubt eingebettetes HTML). Für Dokumentation, die Platz-
haltertexte wie `<DEIN-API-KEY>` oder Beispiel-Markup wie `<script>` enthalten KANN, ist das
zweierlei: ein XSS-Loch UND ein Korrektheits-Bug (der Platzhalter würde als unbekanntes Tag
verschluckt statt sichtbar zu bleiben). Deshalb werden die beiden Erkenner für rohes HTML
(`html_block`-Preprocessor, `html`-Inlinepattern) abgeschaltet — Fließtext-HTML landet dann
ganz normal als Textknoten im Baum und wird beim Serialisieren escaped, exakt wie jeder andere
Text. Fenced-Code-Blöcke sind davon NICHT betroffen (eigener Preprocessor, s. o.), Tabellen/
verschachtelte Listen/attr_list auch nicht (die bauen echte Baumknoten, kein HTML-Stash).

CLI (aus backend/):
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.docs_render                     # alle docs/*.md
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.docs_render --pruefen           # nur prüfen
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.docs_render --datei docs/X.md   # eine Datei
Bequemer Aufruf vom Projekt-Root: `scripts/docs_html.sh` (reicht Argumente 1:1 durch).
"""
import argparse
import hashlib
import html as html_lib
import re
from pathlib import Path
from string import Template

import markdown
from app import favicon
from pipeline import design as design_modul

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DOCS_DIR = PROJECT_ROOT / "docs"

_EXTENSIONS = ["tables", "fenced_code", "sane_lists", "attr_list"]

# Kommentarformat, das render_markdown() als letzte Zeile anhängt — bewusst KEIN Zeitstempel:
# sonst bekäme dieselbe Datei bei jedem Lauf andere Bytes, und der Ergebnis-Vergleich in
# _guard_meldung() (s. dort) würde JEDE Datei als veraltet melden, selbst wenn sich weder
# Quelle noch Renderer geändert haben — Determinismus ist hier Voraussetzung, nicht nur ein
# nettes Extra. Der Kommentar dient NUR NOCH der Rückverfolgbarkeit (welcher Quelltext hat
# dieses HTML erzeugt) — er ist NICHT mehr das Prüfkriterium: --pruefen verglich ursprünglich
# nur diesen Hash gegen den aktuellen Quelltext, das erkannte zuverlässig eine geänderte .md,
# blieb aber blind für einen geänderten RENDERER (Nachtrag 12.08.2026: die Listen-Vorverarbei-
# tung machte alle 12 docs/*.html veraltet, ohne dass sich eine einzige .md änderte — der
# Hash-Guard blieb fälschlich grün). Seither vergleicht _guard_meldung() das GESAMTE Ergebnis.

# Top-Level-Überschriften stehen nach dem Rendern IMMER bei Spalte 0 in eigener Zeile (s.
# Moduldoc) — der Anker "^" (mit re.MULTILINE) ist deshalb kollisionsfrei gegenüber Zitaten/
# Listen/Codezäunen. re.DOTALL erlaubt Inline-Elemente, die selbst einen Zeilenumbruch
# enthalten (z. B. ein manuelles <br> in der Überschrift) -- harmlos, macht den Regex robuster.
_H1_RE = re.compile(r"^<h1(?:\s[^>]*)?>(.*?)</h1>\s*$", re.MULTILINE | re.DOTALL)
_H2_RE = re.compile(r"^<h2(?:\s[^>]*)?>(.*?)</h2>\s*$", re.MULTILINE | re.DOTALL)
_TABLE_RE = re.compile(r"<table>.*?</table>", re.DOTALL)
_TRAILING_HR_RE = re.compile(r"(<hr\s*/?>\s*)+$")

# Für _leerzeile_vor_listen_einfuegen() (Vorverarbeitung des ROHEN Markdown-Quelltexts, s. dort):
# Codezaun-Erkennung (gleiches Muster wie fenced_code.py: 3+ Backticks/Tilden am Zeilenanfang)
# und Listenzeilen-Erkennung (Marker + mindestens ein Leerzeichen + Inhalt, jede Einrückung).
_FENCE_ZEILE_RE = re.compile(r"^(`{3,}|~{3,})")
_LISTEN_ZEILE_RE = re.compile(r"^\s*([-*+]|\d+[.)])\s+\S")


# P2-22: Favicon-Logik zentral in `app/favicon.py` (siehe dort). P2-72: Das Icon des Designs wird je Seite
# zur Laufzeit gelesen (`favicon.favicon_link(d)`), nicht beim Import festgehalten.

# P2-72: Die Markenwerte stehen als `$rolle`-Platzhalter im CSS (`_css()` setzt sie aus dem Design ein).
# Fest bleiben: das Amber und die Cremetöne der Hinweisbox (Bedeutung), das Weiß auf dem Kopfbanner (keine
# Rolle der Vorgabe trifft es: `auf_marke` ist #DCE4EE), die Seitenfarbe im Druck (Papier) und der Schatten.
# `--ink` ist in der Vorgabe Text- UND Markenfarbe (gleicher Wert). Die Variable trägt die Rolle `text`;
# weicht `marke` von `text` ab, setzt `_css()` die Markenfläche des Kopfbanners mit einer Zusatzregel. So
# bleiben die eingecheckten docs/*.html mit der Vorgabe byte-gleich.
_CSS_VORLAGE = Template("""
:root{
  --ink:$text;
  --paper:$flaeche;
  --card:$karte;
  --line:$rahmen;
  --muted:$text_gedaempft;
  --accent:$aktion;
  --amber:#E4A11B;
  --radius:14px;
  --shadow:0 1px 2px rgba(16,26,40,.06),0 8px 24px rgba(16,26,40,.06);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  background:var(--paper);
  color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  line-height:1.6;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:880px;margin:0 auto;padding:32px 20px 72px}

header.head{background:var(--ink);color:#fff;border-radius:var(--radius);padding:28px 30px;
  box-shadow:var(--shadow);margin-bottom:22px}
header.head h1{font-size:26px;line-height:1.3;margin:0;font-weight:700;letter-spacing:-.01em}
header.head h1 code{background:rgba(255,255,255,.16);color:#fff}
header.head .intro{margin-top:10px;font-size:14.5px;color:$stahl;max-width:65ch}
header.head .intro p{margin:0 0 6px}
header.head .intro p:last-child{margin-bottom:0}
header.head .intro a{color:#fff}
header.head .intro code{background:rgba(255,255,255,.16);color:#fff}
/* Ein Zitat (Hinweis-Box) KANN vor der ersten ##-Überschrift stehen und landet dann im Intro
   des dunklen Banners -- seine eigene helle Cremefläche braucht dunkle Schrift, sonst macht die
   helle ".intro code/a"-Regel (höhere Selektor-Spezifität wegen zweier Klassen) Inline-Code/
   Links darin fast unsichtbar (weiß auf Creme). Deshalb hier gezielt zurückgesetzt. */
header.head .intro blockquote{color:#5F4A1F}
header.head .intro blockquote a{color:var(--accent)}
header.head .intro blockquote code{background:rgba($text_rgb,.08);color:#5F4A1F}

section.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:18px 22px 22px;box-shadow:var(--shadow);margin-bottom:16px}
section.card:last-child{margin-bottom:0}
section.card>h2:first-child{margin-top:0}
section.card h2{font-size:18px;margin:0 0 14px;font-weight:700;letter-spacing:-.01em;
  padding-bottom:10px;border-bottom:2px solid var(--accent)}
section.card h3{font-size:15.5px;margin:20px 0 8px;font-weight:700}
section.card h3:first-child{margin-top:0}
section.card h4{font-size:13px;margin:16px 0 6px;font-weight:700;color:var(--muted);
  text-transform:uppercase;letter-spacing:.05em}
section.card p{margin:0 0 12px;font-size:14.5px}
section.card p:last-child{margin-bottom:0}
section.card ul,section.card ol{margin:0 0 12px;padding-left:22px;font-size:14.5px}
section.card ul ul,section.card ol ol,section.card ul ol,section.card ol ul{margin:4px 0}
section.card li{margin-bottom:5px}
section.card li:last-child{margin-bottom:0}
section.card a{color:var(--accent);text-decoration:none;font-weight:600}
section.card a:hover{text-decoration:underline}
section.card hr{border:none;border-top:1px solid var(--line);margin:18px 0}

code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.92em}
:not(pre)>code{background:$spur;border-radius:4px;padding:1px 6px;color:var(--ink)}
pre{background:var(--ink);color:$spur;border-radius:10px;padding:14px 16px;overflow-x:auto;
  font-size:13px;margin:0 0 14px;line-height:1.5}
section.card pre:last-child{margin-bottom:0}
pre code{background:none;padding:0;color:inherit;font-size:inherit}

.tablewrap{overflow-x:auto;margin:0 0 14px}
section.card .tablewrap:last-child{margin-bottom:0}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;background:$spur;color:var(--ink);font-weight:700;padding:8px 12px;
  border:1px solid var(--line);white-space:nowrap}
td{padding:8px 12px;border:1px solid var(--line);vertical-align:top}

blockquote{background:#FBF3E6;border:1px solid #ECD9B3;border-left:4px solid var(--amber);
  border-radius:10px;padding:10px 16px;margin:0 0 14px;color:#5F4A1F;font-size:14px}
section.card blockquote:last-child{margin-bottom:0}
blockquote p{margin:0 0 6px;color:inherit;font-size:inherit}
blockquote p:last-child{margin-bottom:0}
blockquote code{background:rgba($text_rgb,.08)}

@media (max-width:640px){
  .wrap{padding:20px 14px 48px}
  header.head{padding:20px 22px}
}
@media print{
  body{background:#fff}
  .wrap{max-width:100%;padding:10px 6px}
  header.head,section.card{box-shadow:none}
  section.card{page-break-inside:avoid;border-color:#ccc}
  pre{white-space:pre-wrap;word-break:break-word}
  a{color:inherit;text-decoration:none}
}
""")


def _css(d) -> str:
    """Das CSS der Doku-Seiten mit den Werten des Designs `d` (P2-72)."""
    werte = dict(d.farben)
    werte["text_rgb"] = ",".join(str(int(d.farben["text"][i:i + 2], 16)) for i in (1, 3, 5))
    css = _CSS_VORLAGE.substitute(werte)
    if d.farben["marke"] != d.farben["text"]:
        css += f"header.head{{background:{d.farben['marke']}}}\n"
    return css


def _leerzeile_vor_listen_einfuegen(quelltext: str) -> str:
    """Fügt vor einer Listenzeile eine Leerzeile ein, wenn sie OHNE Trennung direkt auf einen
    normalen Textabsatz folgt. Gegenmaßnahme zu einem ECHTEN, dokumentierten Unterschied
    zwischen Python-Markdown und CommonMark/GitHub — NICHT „aufräumen", falls das hier mal
    jemandem überflüssig vorkommt:

        **Was dein Coach sieht:**
        - Eine Übersicht ...

    CommonMark (und damit GitHub) erlaubt, dass eine Liste einen Absatz OHNE Leerzeile
    unterbricht („a list can interrupt a paragraph"). Python-Markdowns Paragraph-Blockprocessor
    kennt diese Regel nicht: Er behandelt die Listenzeilen als lose Fortsetzung DESSELBEN
    Absatzes, sie landen als Fließtext mit sichtbaren Bindestrichen/Ziffern statt als <ul>/<ol>.
    Fund bei der Abnahme 12.08.2026: 195 Stellen in 11 von 12 docs/*.md folgen genau diesem auf
    GitHub korrekt gerenderten, in Python-Markdown aber falsch interpretierten Muster — die
    .md-Quellen sind NICHT falsch, deshalb wird hier am Renderer korrigiert statt an den
    Quellen (die Hauptsession pflegt die Doku, keine Formatierungs-Konvention für sie).

    Bewusst NUR eine Leerzeile vor dem ERSTEN Element einer NEUEN Liste, nie sonst:
      - Codezäune (``` / ~~~) bleiben komplett unangetastet (Zustand `in_fence` unten) —
        eine Bindestrich-Zeile in einem Codebeispiel ist Text, keine Liste.
      - Fortsetzungszeilen INNERHALB einer Liste (eingerückter Text nach einem Listenpunkt,
        z. B. ein zweizeiliger Punkt) bekommen KEINE Leerzeile — sonst würde aus einer
        kompakten eine lose Liste (jedes <li> bekäme ein <p>, sichtbar andere Optik). Erkannt
        über `listenkontext`: bleibt aktiv, solange die vorherige nicht-leere Zeile selbst eine
        Listenzeile ODER eine eingerückte Fortsetzung einer aktiven Liste war.
      - Ist die Vorzeile eine Tabellenzeile (|), ein Zitat (>) oder eine Überschrift (#), wird
        NICHT eingefügt: eine nackte Leerzeile direkt nach '>' würde das Zitat vorzeitig
        beenden, nach '|' eine Tabelle zerreißen; Überschriften brauchen den Trick ohnehin
        nicht (eigene, einzeilige Blockerkennung ohne das Absatz-Vorlauf-Problem). Listen
        INNERHALB von Zitaten bleiben dadurch bewusst außen vor (out of scope laut Auftrag).
      - Eine Tabellenzeile BEENDET den Listenkontext (auch eingerückt/in einer Liste
        verschachtelt) — empirisch verifiziert (Regressionsfall docs/SETUP-EMAIL.md, Schritt
        „In der App eintragen"): Python-Markdowns `tables`-Extension schließt eine offene Liste
        vorzeitig, SOBALD eine Tabelle folgt (unabhängig von deren Einrückung; die Tabelle
        selbst rendert korrekt, aber Text danach zählt für den Parser nicht mehr als
        Listen-Fortsetzung). Ohne dieses Zurücksetzen hier würde der übernächste Listenpunkt
        (nach einem Absatz NACH der Tabelle) fälschlich als „noch im Listenkontext" gelten und
        keine Leerzeile bekommen — obwohl Python-Markdown genau dort ebenfalls ins Fließtext-
        Muster zurückfällt.

    Rein zeilenbasierte Heuristik, kein vollständiger Parser — ausreichend robust für unsere
    eigenen, handgeschriebenen Dokumente (kein adversarial Input). Wirkt nur auf die Kopie, die
    an den Markdown-Konverter geht; der Hash in render_markdown() bleibt über den ORIGINAL-
    Quelltext berechnet (die Datei auf der Platte wird durch diese Funktion nicht verändert)."""
    zeilen = quelltext.split("\n")
    ergebnis = []
    in_fence = False
    fence_zeichen = ""
    vorherige_nichtleer = ""
    listenkontext = False

    for zeile in zeilen:
        stripped = zeile.strip()

        fence_treffer = _FENCE_ZEILE_RE.match(zeile)
        if fence_treffer:
            zeichen = fence_treffer.group(1)[0]
            if not in_fence:
                in_fence, fence_zeichen = True, zeichen
            elif zeichen == fence_zeichen:
                in_fence = False
            ergebnis.append(zeile)
            vorherige_nichtleer = zeile
            listenkontext = False
            continue
        if in_fence:
            ergebnis.append(zeile)
            continue
        if not stripped:
            ergebnis.append(zeile)
            continue

        ist_listenzeile = bool(_LISTEN_ZEILE_RE.match(zeile))
        ist_tabellenzeile = stripped.startswith("|")
        ist_eingerueckt = zeile[:1] in (" ", "\t")

        if ist_listenzeile and not listenkontext and vorherige_nichtleer:
            vorzeile = vorherige_nichtleer.strip()
            if not (vorzeile.startswith("|") or vorzeile.startswith(">")
                    or vorzeile.startswith("#")):
                if ergebnis and ergebnis[-1].strip():  # keine zweite Leerzeile obendrauf
                    ergebnis.append("")

        ergebnis.append(zeile)
        vorherige_nichtleer = zeile
        if ist_tabellenzeile:
            listenkontext = False
        else:
            listenkontext = ist_listenzeile or (ist_eingerueckt and listenkontext)

    return "\n".join(ergebnis)


def _markdown_konverter() -> markdown.Markdown:
    """Frisches `Markdown()`-Objekt je Konvertierung — bewusst KEINE Wiederverwendung über
    mehrere `.convert()`-Aufrufe hinweg (die Bibliothek verlangt dafür explizites `.reset()`
    zwischen Aufrufen, sonst ist z. B. der HTML-Stash-Zustand nicht dokumentiert sauber; eine
    frische Instanz ist die einfachste korrekte Lösung, die Dokumente sind klein genug, dass
    das nicht ins Gewicht fällt). `html_block`/`html` abgeschaltet: Begründung im Moduldoc."""
    md = markdown.Markdown(extensions=_EXTENSIONS, output_format="html")
    md.preprocessors.deregister("html_block")
    md.inlinePatterns.deregister("html")
    return md


def _hash(quelltext: str) -> str:
    return hashlib.sha256(quelltext.encode("utf-8")).hexdigest()


def _innentext_fuer_title(inner_html: str) -> str:
    """<title>-taugliche Klartext-Version einer (ggf. inline-formatierten) Überschrift: Tags
    raus, Entities einmal aufgelöst und für den <title>-Kontext neu escaped — robust auch bei
    Emphase/Code/Et-Zeichen in der Überschrift selbst."""
    ohne_tags = re.sub(r"<[^>]+>", "", inner_html)
    return html_lib.escape(html_lib.unescape(ohne_tags)).strip()


def _mit_tabellen_wrapper(body: str) -> str:
    """Bettet jede <table> in einen horizontal scrollbaren Container — die Doku enthält
    breite Tabellen (z. B. DOKUMENTATION.md, Architektur-Übersicht), die sonst auf schmalen
    Bildschirmen oder im Ausdruck die Karte sprengen würden."""
    return _TABLE_RE.sub(lambda m: f'<div class="tablewrap">{m.group(0)}</div>', body)


def _zerlege(body: str) -> tuple:
    """Zerlegt bereits gerendertes HTML in (Titel-Innen-HTML|None, Intro-HTML, [(Abschnitts-
    Innen-HTML, Abschnitts-Körper-HTML), ...]). Siehe Moduldoc für die Sicherheitsbegründung
    der spaltenverankerten Regexe. Inhalt VOR einem gefundenen H1 wird verworfen (alle
    docs/*.md beginnen mit ihrer H1 als erster Zeile — ein abweichendes Dokument wäre
    pathologisch; das Verwerfen ist einfacher und ebenso sicher wie ein Verschmelzen der
    Teiltexte)."""
    m1 = _H1_RE.search(body)
    if m1:
        titel_html = m1.group(1).strip()
        rest = body[m1.end():]
    else:
        titel_html = None
        rest = body

    grenzen = list(_H2_RE.finditer(rest))
    if not grenzen:
        return titel_html, rest.strip(), []

    intro = rest[:grenzen[0].start()].strip()
    abschnitte = []
    for i, m in enumerate(grenzen):
        start = m.end()
        ende = grenzen[i + 1].start() if i + 1 < len(grenzen) else len(rest)
        abschnitte.append((m.group(1).strip(), rest[start:ende].strip()))
    return titel_html, intro, abschnitte


def _seite(titel_html: str, titel_text: str, intro_html: str, abschnitte: list, d) -> str:
    if abschnitte:
        intro_block = f'<div class="intro">{intro_html}</div>' if intro_html else ""
        karten = "".join(
            f'<section class="card"><h2>{ueberschrift}</h2>{koerper}</section>'
            for ueberschrift, koerper in abschnitte)
    else:
        # Kein ##-Abschnitt gefunden (kurzes/flaches Dokument) -- der komplette Rumpf wird EINE
        # Karte statt in den dunklen Banner gequetscht zu werden (Lesbarkeit).
        intro_block = ""
        karten = f'<section class="card">{intro_html}</section>' if intro_html else ""

    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">{favicon.favicon_link(d)}
<title>{titel_text}</title>
<style>{_css(d)}</style></head><body><div class="wrap">
<header class="head"><h1>{titel_html}</h1>{intro_block}</header>
{karten}
</div></body></html>"""


def render_markdown(quelltext: str, dateiname: str, geltend=None) -> str:
    """Kernrenderer: kompletter Markdown-Quelltext einer Doku-Datei -> fertiges, eigenständiges
    HTML-Dokument im §18-Look samt Hash-Kommentar als letzter Zeile.

    `geltend` (P2-72) ist das `Design`, mit dem gerendert wird. Ohne Angabe gilt die VORGABE
    (`design.vorgabe()`): Alles, was die mitgelieferten `docs/*.html` erzeugt oder prüft, soll nie vom Design
    eines Kunden abhängen. Die Doku-Ansicht in der App übergibt `design.laden()`. Das Icon im Kopf stammt aus
    demselben Design (`favicon.favicon_link(geltend)`): bei den mitgelieferten Seiten das der Vorgabe.

    `dateiname` ist NUR der Basisname (z. B. 'ANLEITUNG.md') und landet unverändert im Kommentar — der dient seit dem
    Nachtrag 12.08.2026 nur noch der Rückverfolgbarkeit im Dokument selbst (welcher Quelltext
    hat DIESES HTML erzeugt), NICHT mehr als Prüfkriterium: --pruefen (s. _guard_meldung()
    weiter unten) rendert dafür jede .md frisch und vergleicht das Ergebnis byte-genau mit der
    vorhandenen .html — das erkennt zuverlässig sowohl eine geänderte Quelle als auch einen
    geänderten Renderer, ein reiner Quell-Hash-Vergleich erkannte nur Ersteres."""
    geltend = geltend if geltend is not None else design_modul.vorgabe()
    md = _markdown_konverter()
    normalisiert = _leerzeile_vor_listen_einfuegen(quelltext)
    body = _mit_tabellen_wrapper(md.convert(normalisiert))
    titel_html, intro_html, abschnitte = _zerlege(body)
    if titel_html is None:
        # Kein H1 gefunden (sollte bei den echten docs/*.md nicht vorkommen) -- Ersatztitel aus
        # dem Dateinamen, damit die Seite trotzdem nutzbar bleibt statt abzustürzen.
        ersatz = re.sub(r"[_-]+", " ", Path(dateiname).stem).strip()
        titel_html = html_lib.escape(ersatz or dateiname)
    titel_text = _innentext_fuer_title(titel_html)
    intro_html = _TRAILING_HR_RE.sub("", intro_html).strip()

    seite = _seite(titel_html, titel_text, intro_html, abschnitte, geltend)
    kommentar = f"<!-- docs_render quelle={dateiname} sha256={_hash(quelltext)} -->"
    return f"{seite}\n{kommentar}\n"


def render_datei(md_pfad: Path) -> str:
    """Liest eine .md-Datei und liefert den fertigen HTML-Seitentext."""
    return render_markdown(md_pfad.read_text(encoding="utf-8"), md_pfad.name)


def ziel_fuer(md_pfad: Path) -> Path:
    return md_pfad.with_suffix(".html")


def render_und_schreiben(md_pfad: Path) -> Path:
    """Rendert eine .md-Datei und schreibt die gleichnamige .html daneben. Gibt den Zielpfad
    zurück.

    `newline="\\n"` ist Pflicht, kein Stilfrage: Ohne das übersetzt Python die Zeilenenden beim
    Schreiben in die Konvention des Betriebssystems — auf Windows also `\\r\\n`. Folge (CI-Fund
    12.08.2026, Job `backend-windows`): Der Byte-Vergleich in `_guard_meldung()` verglich
    CRLF-Datei gegen frisch gerenderten LF-Text und meldete jede Datei als „veraltet"; ein
    Windows-Nutzer hätte beim Rendern zudem alle 12 HTML-Dateien scheinbar geändert (Riesen-Diff
    ohne inhaltliche Änderung). Zusammen mit `.gitattributes` (`*.html eol=lf`) bleiben die
    Dateien auf jeder Plattform byte-gleich."""
    ziel = ziel_fuer(md_pfad)
    ziel.write_text(render_datei(md_pfad), encoding="utf-8", newline="\n")
    return ziel


def _lesbarer_pfad(p: Path) -> str:
    """Projekt-relativ, wenn möglich (kürzere Meldungen) -- Tests, die außerhalb von
    PROJECT_ROOT in tmp_path arbeiten, bekommen sauber den vollen Pfad statt eines
    ValueError."""
    try:
        return str(p.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(p)


def _guard_meldung(md_pfad: Path) -> str | None:
    """None = die zugehörige .html entspricht BYTE-GENAU dem, was der AKTUELLE Renderer aus der
    AKTUELLEN Quelle erzeugen würde. Sonst eine Klartext-Meldung, WELCHE Datei betroffen ist und
    WAS zu tun ist (Spec: die Meldung muss zum Handeln anleiten).

    Vergleicht das ERGEBNIS, nicht (mehr) nur einen Quell-Hash: Der Ursprungsentwurf verglich
    ausschließlich `sha256(quelltext)` gegen den im HTML hinterlegten Hash — das erkennt
    zuverlässig eine geänderte .md-Datei, bleibt aber blind für einen geänderten RENDERER.
    Genau dieser Fall trat am 12.08.2026 ein: die neue Listen-Vorverarbeitung
    (`_leerzeile_vor_listen_einfuegen`) machte alle 12 docs/*.html veraltet, ohne dass sich
    auch nur eine .md-Quelle änderte — der Hash-Guard blieb fälschlich grün, ausgerechnet beim
    Renderer-Update blind. Der Ergebnis-Vergleich hier führt den Renderer bei JEDEM
    --pruefen-Lauf tatsächlich aus und deckt dadurch beide Fälle (geänderte Quelle UND
    geänderter Renderer) einheitlich ab. Das setzt Determinismus voraus (zweimal rendern muss
    byte-identisch sein, s. test_determinismus_zweimal_rendern_byte_identisch) — ohne den wäre
    dieser Vergleich sinnlos instabil."""
    hinweis = "-> scripts/docs_html.sh ausführen"
    ziel = ziel_fuer(md_pfad)
    if not ziel.is_file():
        return f"{_lesbarer_pfad(ziel)} fehlt {hinweis}"
    erwartet = render_datei(md_pfad).encode("utf-8")
    vorhanden = ziel.read_bytes()
    if vorhanden != erwartet:
        return (f"{_lesbarer_pfad(ziel)} ist veraltet (Quelle oder Renderer haben sich "
                 f"geändert) {hinweis}")
    return None


def pruefen(md_dateien: list) -> list:
    """Prüft Paarigkeit + Ergebnis-Gleichheit für die gegebenen .md-Dateien (s. _guard_meldung),
    OHNE etwas zu schreiben. Leere Rückgabeliste = alles aktuell."""
    return [m for m in (_guard_meldung(p) for p in md_dateien) if m]


def _ziel_dateien(datei_arg) -> list:
    if datei_arg:
        p = Path(datei_arg)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return [p]
    return sorted(_DOCS_DIR.glob("*.md"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline.docs_render", description=__doc__.split("\n")[0])
    ap.add_argument("--pruefen", action="store_true",
                     help="nur prüfen (nichts schreiben); Exit 1 bei fehlender/veralteter HTML")
    ap.add_argument("--datei",
                     help="nur eine Datei, z. B. docs/ANLEITUNG.md "
                          "(Pfad relativ zu PROJECT_ROOT oder absolut)")
    args = ap.parse_args(argv)
    md_dateien = _ziel_dateien(args.datei)

    if args.pruefen:
        fehler = pruefen(md_dateien)
        for f in fehler:
            print(f)
        if fehler:
            return 1
        print(f"Alles aktuell ({len(md_dateien)} Datei(en) geprüft).")
        return 0

    for md_pfad in md_dateien:
        ziel = render_und_schreiben(md_pfad)
        print(f"geschrieben: {_lesbarer_pfad(ziel)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
