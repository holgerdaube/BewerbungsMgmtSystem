#!/usr/bin/env python3
"""Das CSS aller Berichte der Themen-Familie aus EINER Funktion (P2-72, Vertrag R).

VORHER: Fünf Renderer (`company_fit`, `transcript_report`, `posting_snapshot`, `cleanup`,
`beirat_engine`) trugen je eine eigene Konstante `_CSS` mit eigenem `:root`, dazu die Vorlage
`assets/report_theme_bms.html` und die Stücke, die Modelle in den Skills abtippten. Die Kopien
wichen voneinander ab (`.dot` 14 gegen 10 px, `.bluf` mit anderem Rand, ein `:root` ohne drei
Variablen) und kannten kein gemeinsames Design.

JETZT: `bericht_css(zusatz, design)` liefert das vollständige CSS. Die Renderer reichen nur noch
ihre eigenen Regeln als `zusatz` mit. Jede Abweichung, die man sieht, bleibt erhalten (Leitentscheidung
8: es wird nichts „bereinigt“) und steht als Zusatz im jeweiligen Renderer, mit einem Satz, warum.

WERTE: Im `:root` stehen die Werte des geltenden Designs AUSGESCHRIEBEN (Berichte sind eigenständige
Dateien, sie werden aus dem Finder geöffnet, verschickt und auf die Coach-Site kopiert, kein Verweis
nach außen). Das Design wird bei jedem Aufruf gelesen (`design.laden()` ist zwischengespeichert und
merkt Änderungen der Dateien), nie beim Import festgehalten. Die Variablennamen des Themas bleiben,
damit vorhandenes Markup und die Skills weiter passen:

    --ink      marke            --paper    flaeche         --accent  aktion
    --line     trenner          --paper-2  karte           --muted   text_gedaempft
    --text     text             --rahmen   rahmen          --spur    spur
    --stahl    stahl            --auf-ink  Schrift auf der Markenfläche (s. u.)

BEDEUTUNG IST KEIN DESIGN (Leitentscheidung 2): Zustandsfarben (`--green`, `--amber`, `--red`,
`--pos`, `--neu`, `--neg`), die Pastelle (Hinweiskasten, Ampel-Banner, Bedeutungs-Chips, Pastell des
Abgedeckt/Nicht-abgedeckt-Chips) und die Schrift auf diesen Flächen bleiben feste Werte und hängen an
keiner Markenrolle. `pipeline/zustandsfarben.py` (Paket A) kann die Konstanten `ZUSTAND` später
ablösen; bis dahin ist dies die einzige Stelle der Themen-Familie.

SCHRIFT AUF DER MARKENFLÄCHE (`--auf-ink`): Der Berichtskopf zeigt heute Weiß auf Navy, die Rolle
`auf_marke` der Vorgabe ist aber `#DCE4EE`. Damit die Vorgabe genau wie vorher aussieht, bleibt es bei
Weiß, solange Weiß auf der Markenfarbe lesbar ist (Kontrast mindestens 4,5:1). Bringt ein Design eine
helle Markenfarbe mit, gilt stattdessen seine Rolle `auf_marke` (die Design-Prüfung garantiert dort den
Kontrast). So bleibt der Kopf lesbar, ohne dass die Vorgabe sich ändert.

REGELN DER MODELL-BERICHTE: Fünf Berichtsarten schreibt ein Modell (Match, ATS-Scan, Briefing,
Absagen-Analyse, Angebotsvergleich). Die Skills schreiben nur HTML mit Klassen und kein CSS; alles, was
`cv-match` und `cv-erstellen` früher selbst mitbrachten (Vorher/Nachher-Karten `.cmp`, Red-Flag-Zeile,
dritte Chip-Gruppe `.chip.warn`), steht jetzt in `_REGELN`. Meldet `einsetzen` trotzdem eine Klasse ohne
Regel, ersetzt das Modell sie durch eine aus der Vorlage. Kein Skill und keine Vorlage leitet zu eigenen
Regeln an.

AUFFANGLÖSUNG `<style data-zusatz>…</style>`: Ein Bericht kann eigene Regeln in einem zweiten Block tragen.
`einsetzen` ersetzt nur den Block ohne dieses Attribut und lässt jeden Zusatzblock unangetastet (er steht
hinter dem Themenblock, seine Regeln gewinnen bei gleicher Gewichtung), damit der Befehl nichts zerstört,
was in einem Bericht steht. Empfohlen wird der Weg nirgends. `report_check` zählt Klassen aus beiden
Blöcken als definiert.

Kommandozeile (aus backend/):
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.bericht_stil einsetzen <bericht.html> [...]
        ersetzt den <style>-Block (genau einen; fehlt er, wird er im <head> angelegt; mehrere werden zu
        einem; ein `<style/>` entfällt) durch `bericht_css()` und setzt das Icon des geltenden Designs
        (`app/favicon.py`).
        Sonst bleibt das Dokument byte-genau, wie es war; zweimal angewandt gleich einmal; atomar
        geschrieben. Meldet Klassen ohne Regel wie `report_check`.
        Exit 0 = ok, 2 = Nutzung/Datei unbrauchbar, 3 = Klassen ohne Regel (Datei ist trotzdem
        geschrieben).
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.bericht_stil vorlage [--pruefen]
        erzeugt den <style>-Block von `assets/report_theme_bms.html` neu (mit der Vorgabe, nie mit einer
        Überschreibung); mit --pruefen nur vergleichen (Exit 1 bei Abweichung).
"""
from __future__ import annotations

import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pipeline import design as design_modul

PROJEKT_ROOT = Path(__file__).resolve().parents[2]
VORLAGE = PROJEKT_ROOT / "assets" / "report_theme_bms.html"

EXIT_OK = 0
EXIT_VORLAGE_ABWEICHT = 1
EXIT_FEHLER = 2
EXIT_KLASSEN_OHNE_REGEL = 3

# ── Feste Werte: Bedeutung, kein Design (Leitentscheidung 2) ──────────────────────────────────
# Ampel- und Score-Farben der Berichte. Hängen an keiner Markenrolle: „Beworben“ bleibt cyan, auch
# wenn ein Design Orange als Aktionsfarbe mitbringt.
ZUSTAND = {
    "green": "#18A957", "amber": "#E4A11B", "red": "#E5484D",
    "pos": "#18A957", "neu": "#94A3B8", "neg": "#E5484D",
}
_RADIUS = "14px"
_SCHATTEN = "0 1px 2px rgba(16,26,40,.06),0 8px 24px rgba(16,26,40,.06)"
_WEISS = "#FFFFFF"


def schrift_auf_marke(farben) -> str:
    """Schriftfarbe auf der Markenfläche der Berichte (`--auf-ink`): Weiß, solange es auf `marke`
    lesbar ist (4,5:1), sonst die Rolle `auf_marke`. Mit der Vorgabe ist das Weiß wie bisher."""
    if design_modul.kontrast(_WEISS, farben["marke"]) >= design_modul.KONTRAST_MIN:
        return _WEISS
    return farben["auf_marke"]


def _wurzel(d) -> str:
    """Der `:root`-Block mit den ausgeschriebenen Werten des Designs `d`."""
    f = d.farben
    z = ZUSTAND
    return (
        ":root{\n"
        f"  --ink:{f['marke']};--line:{f['trenner']};--paper:{f['flaeche']};--paper-2:{f['karte']};"
        f"--muted:{f['text_gedaempft']};--text:{f['text']};--accent:{f['aktion']};\n"
        f"  --rahmen:{f['rahmen']};--spur:{f['spur']};--stahl:{f['stahl']};"
        f"--auf-ink:{schrift_auf_marke(f)};\n"
        f"  --green:{z['green']};--amber:{z['amber']};--red:{z['red']};--pos:{z['pos']};"
        f"--neu:{z['neu']};--neg:{z['neg']};\n"
        f"  --radius:{_RADIUS};--shadow:{_SCHATTEN}\n"
        "}"
    )


# ── Die Regeln der Themen-Familie ─────────────────────────────────────────────────────────────
# Inhalt wie die bisherige Vorlage `assets/report_theme_bms.html` (die Obermenge aller Renderer),
# nur dass Rahmen, Spur, Steel, Trenner und Navy jetzt Variablen sind. Reihenfolge und Gewichtung der
# Regeln sind unverändert. Kommentare stehen hier, nicht im ausgelieferten CSS (jeder Bericht trägt es).
# Bedeutungs-Chips (`.chip .tag`, `.card .flag.na`) und Pastelle behalten feste Werte, auch dort, wo sie
# zufällig einem Rollenwert gleichen.
#
# P2-72 Paket S: Dazu kommen die Regeln, die `cv-match` und `cv-erstellen` bisher selbst im Skill-Text trugen
# (die Modelle tippten sie in jeden Bericht ab): `.chip.warn`, `tr.redflag td` und die Vorher/Nachher-Karten
# `.cmp …`. Die Werte sind die, die die Skills nannten. Fest stehen die Pastelle der Bedeutung (Red Flag,
# vorher/nachher, Markierung, "abdeckbar, aber nicht eingearbeitet") und zwei Werte aus der Palette von vor
# der letzten Umstellung, die keiner Rolle entsprechen (Rand der `.cmp`-Karte `#e6e9e4`, Blau der
# `.pill2`-Chips). Marke zeigen dort nur `var(--paper-2)`, `--shadow`, `--ink` und `--muted`. Was `cv-match`
# für `.chip`, `.chip .tag.direkt|indirekt`, `.chip span` und `.chip.pos|neg` mit anderem Inhalt trug, ist
# NICHT übernommen: Für diese Selektoren gilt die Fassung der Vorlage. Der Skill verwies für die Detailwerte
# selbst auf die Vorlage, seine eigenen Werte stammten aus der Palette von vor der letzten Umstellung, und
# das Keyword-Protokoll sieht so im Match-Dashboard aus wie im ATS-Scan.
_REGELN = """\
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--paper);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:1040px;margin:0 auto;padding:32px 20px 72px}
header.head{background:var(--ink);color:var(--auf-ink);border-radius:var(--radius);padding:28px 30px;box-shadow:var(--shadow)}
.head .eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--stahl);font-weight:700;margin:0 0 8px}
.head h1{font-size:26px;line-height:1.2;margin:0 0 4px;font-weight:700;letter-spacing:-.01em}
.head h1 a{color:inherit;text-decoration:none;border-bottom:1px solid var(--line)}
.head .sub{font-size:15px;color:var(--stahl);margin:0 0 16px;font-weight:600}
.head .meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px 22px;border-top:1px solid rgba(255,255,255,.14);padding-top:16px}
.head .meta .k{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--stahl);margin:0 0 2px}
.head .meta .v{font-size:14px;color:var(--auf-ink)}
.head .badges{margin-top:14px;display:flex;flex-wrap:wrap;gap:8px}
.head .badges .pill{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.04em;padding:4px 10px;border-radius:999px;background:var(--line);color:var(--stahl);border:1px solid var(--line)}
.gauge{display:flex;flex-direction:column;align-items:center;justify-content:center;min-width:150px;padding:14px 18px;border-radius:12px;background:#0a121e;border:1px solid #22344c}
.lamp{width:54px;height:54px;border-radius:50%;position:relative;margin-bottom:10px}
.lamp::after{content:"";position:absolute;inset:0;border-radius:50%;box-shadow:0 0 0 6px rgba(255,255,255,.04)}
.lamp.green{background:radial-gradient(circle at 35% 30%,#4fd48a,var(--green));box-shadow:0 0 22px rgba(24,169,87,.6)}
.lamp.amber{background:radial-gradient(circle at 35% 30%,#f2b752,var(--amber));box-shadow:0 0 22px rgba(228,161,27,.6)}
.lamp.red{background:radial-gradient(circle at 35% 30%,#e57366,var(--red));box-shadow:0 0 22px rgba(229,72,77,.6)}
.gauge .verdict{font-size:13px;letter-spacing:.12em;text-transform:uppercase;font-weight:700}
.gauge .verdict.green{color:#5fe0a0}
.gauge .verdict.amber{color:#f2c069}
.gauge .verdict.red{color:#ef8577}
.dot{display:inline-block;width:14px;height:14px;border-radius:50%;vertical-align:middle;margin-right:6px}
.dot.green{background:#18A957} .dot.amber{background:#E4A11B} .dot.red{background:#E5484D} .dot.grau{background:#94A3B8}
.bluf{margin-top:16px;background:var(--paper-2);border:1px solid var(--rahmen);border-left:4px solid var(--accent);border-radius:12px;padding:18px 20px;box-shadow:var(--shadow)}
.bluf .fitlabel{font-size:13px;font-weight:600;color:var(--muted);margin:0 0 6px}
.bluf p{margin:0;font-size:15.5px}
h2.sec{font-size:13px;letter-spacing:.13em;text-transform:uppercase;color:var(--muted);margin:34px 0 12px;font-weight:700;display:flex;align-items:center;gap:10px}
h2.sec::before{content:"";width:22px;height:2px;background:var(--accent);display:inline-block}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}
.card{background:var(--paper-2);border:1px solid var(--rahmen);border-radius:12px;padding:16px 18px;box-shadow:var(--shadow)}
.card h3{margin:0 0 8px;font-size:15px;font-weight:700}
.card p{margin:0 0 10px;font-size:14px;color:var(--text)}
.card p:last-child{margin-bottom:0}
.card .kv{font-size:13px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.05em;margin:0 0 2px}
.card .flag{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;border-radius:6px;margin-bottom:8px}
.card .flag.na{background:#EAF0F6;color:#94A3B8}
ul.clean{margin:6px 0 0;padding-left:18px}
ul.clean li{font-size:14px;margin-bottom:6px}
table.score{width:100%;border-collapse:collapse;background:var(--paper-2);border:1px solid var(--rahmen);border-radius:12px;overflow:hidden;box-shadow:var(--shadow);font-size:14px}
table.score th{text-align:left;background:var(--spur);color:var(--muted);font-size:11px;letter-spacing:.08em;text-transform:uppercase;padding:11px 14px;border-bottom:1px solid var(--rahmen)}
table.score td{padding:12px 14px;border-bottom:1px solid var(--spur);vertical-align:top}
table.score tr:last-child td{border-bottom:none}
tr.redflag td{background:#fdeceb}
.badge{display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:7px;font-weight:800;font-size:15px;color:#fff}
.badge.pos{background:var(--pos)} .badge.neu{background:var(--neu)} .badge.neg{background:var(--neg)}
td.factor{font-weight:600;width:210px}
td.rel{color:var(--muted)}
.comp{display:flex;flex-wrap:wrap;gap:10px}
.chip{background:var(--paper-2);border:1px solid var(--rahmen);border-radius:10px;padding:10px 13px;font-size:13.5px;box-shadow:var(--shadow);max-width:320px}
.chip .tag{display:inline-block;font-size:10px;letter-spacing:.08em;text-transform:uppercase;font-weight:700;padding:2px 7px;border-radius:5px;margin-bottom:5px}
.chip .tag.direkt{background:#BFECF5;color:#0B1F3A}
.chip .tag.indirekt{background:#EAF0F6;color:#5F6F84}
.chip b{display:block;font-size:14px;margin-bottom:2px}
.chip span{color:var(--muted)}
.chip.pos{background:#e5f6ec;border-color:#bfe4cd}
.chip.neg{background:#fbe9e7;border-color:#f0c4bc}
.chip.warn{background:#fdf3e0;border-color:#eed9a8}
ol.iq{counter-reset:q;list-style:none;margin:0;padding:0}
ol.iq li{background:var(--paper-2);border:1px solid var(--rahmen);border-radius:10px;padding:12px 14px 12px 46px;position:relative;margin-bottom:10px;font-size:14.5px;box-shadow:var(--shadow)}
ol.iq li::before{counter-increment:q;content:counter(q);position:absolute;left:12px;top:11px;width:24px;height:24px;border-radius:6px;background:var(--ink);color:var(--auf-ink);font-size:13px;font-weight:700;display:flex;align-items:center;justify-content:center}
.cmp{border:1px solid #e6e9e4;border-radius:12px;background:var(--paper-2);box-shadow:var(--shadow);padding:16px 18px;margin-bottom:14px}
.cmp h3{margin:0 0 10px;font-size:14px;color:var(--ink)}
.cmp .pair{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.cmp .before{background:#fbeceb;border-radius:8px;padding:10px 12px;font-size:13.5px;color:#5f2c28}
.cmp .after{background:#e9f6ef;border-radius:8px;padding:10px 12px;font-size:13.5px;color:#1e4a34}
.cmp .lbl{font-size:11px;text-transform:uppercase;letter-spacing:.06em;font-weight:700;margin:0 0 6px;color:var(--muted)}
.cmp mark{background:#ffe9a8;padding:0 2px;border-radius:2px}
.cmp .pills{margin-top:10px;display:flex;flex-wrap:wrap;gap:6px}
.cmp .pill2{font-size:11px;font-weight:700;background:#e5eefb;color:#255fb0;padding:3px 9px;border-radius:999px}
@media (max-width:720px){.cmp .pair{grid-template-columns:1fr}}
details.volltext{margin-top:14px;background:var(--paper-2);border:1px solid var(--rahmen);border-radius:12px;box-shadow:var(--shadow)}
details.volltext summary{cursor:pointer;padding:14px 18px;font-weight:700;font-size:14px;list-style:none}
details.volltext summary::-webkit-details-marker{display:none}
details.volltext summary::before{content:"▸ ";color:var(--accent)}
details.volltext[open] summary::before{content:"▾ "}
details.volltext pre{margin:0;padding:0 18px 18px;white-space:pre-wrap;word-break:break-word;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px;color:var(--text)}
.sources{margin-top:28px;font-size:12.5px;color:var(--muted)}
.sources h2{font-size:12px;letter-spacing:.13em;text-transform:uppercase;margin:0 0 8px}
.sources a{color:var(--accent);text-decoration:none}
.sources a:hover{text-decoration:underline}
.caveat{margin-top:18px;background:#fbf3e6;border:1px solid #ecd9b3;border-left:4px solid var(--amber);border-radius:12px;padding:14px 18px;font-size:13.5px;color:#5f4a1f}
.caveat b{color:#8a5b0c}
.foot{margin-top:22px;padding-top:16px;border-top:1px solid var(--rahmen);font-size:12px;color:var(--muted);display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
a:focus-visible,li:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media (max-width:720px){.grid{grid-template-columns:1fr} td.factor{width:auto}}
@media print{body{background:#fff} .card,table.score,.chip,ol.iq li,.bluf,details.volltext{box-shadow:none} header.head{box-shadow:none}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}"""

# Die Vorlage setzt im Druck einen weißen Seitengrund (`body{background:#fff}`), die Renderer der
# Themen-Familie hatten das nie: Bei ihnen blieb die Seitenfarbe auch im Druck. Wer das erhalten will,
# reicht diese Zeile als Teil seines Zusatzes mit (sie wiederholt nur den Wert des normalen Bildschirms).
DRUCK_SEITENFARBE_BEHALTEN = "@media print{body{background:var(--paper)}}"


def bericht_css(zusatz: str = "", design=None) -> str:
    """Das vollständige CSS der Themen-Familie mit den Werten des geltenden Designs (`design`, sonst
    `design.laden()`, bei jedem Aufruf frisch gelesen). `zusatz` sind die eigenen Regeln des Berichts;
    sie stehen hinter dem Thema und gewinnen bei gleicher Gewichtung. Das Ergebnis beginnt und endet mit
    einem Zeilenumbruch und gehört unverändert zwischen `<style>` und `</style>`."""
    d = design if design is not None else design_modul.laden()
    teile = ["/* Bericht-Stil (P2-72): erzeugt aus pipeline/bericht_stil.py */", _wurzel(d), _REGELN]
    zusatz = (zusatz or "").strip("\n")
    if zusatz:
        teile.append(zusatz)
    return "\n" + "\n".join(teile) + "\n"


# ── Einsetzen in einen fertigen Bericht ───────────────────────────────────────────────────────
# Ein HTML-Kommentar wird als Ganzes übersprungen: Ein `<style>` darin (die Vorlage erklärt sich selbst in
# Kommentaren) ist kein Stilblock. Gruppe 1 = der ganze Block, 2 = seine Attribute.
# Ein `<style/>` zählt als eigener Block: Ein Modell schreibt ihn gelegentlich als „leeren Stilblock“, HTML
# kennt aber kein selbstschließendes `<style>`. Der Browser öffnet damit einen Block, der den folgenden
# `<style>` als Text verschluckt; das `:root` davor wird ungültig und der Bericht verliert alle Farben.
_STIL_ODER_KOMMENTAR_RE = re.compile(
    r"<!--.*?-->|(<style\b([^>]*?)\s*(?:/>|>.*?</style\s*>))", re.S | re.I)
_ZUSATZ_RE = re.compile(r"(?:^|\s)data-zusatz(?:\s|=|$)", re.I)
_KOPF_ENDE_ODER_KOMMENTAR_RE = re.compile(r"<!--.*?-->|(</head\s*>)", re.S | re.I)


class EinsetzenFehler(ValueError):
    """Der Bericht lässt sich nicht bearbeiten (kein <head>, nicht UTF-8 …)."""


def _stilbloecke(text: str) -> list:
    """Alle <style>-Elemente außerhalb von HTML-Kommentaren, in Dokumentreihenfolge."""
    return [m for m in _STIL_ODER_KOMMENTAR_RE.finditer(text) if m.group(1)]


def _kopf_ende(text: str):
    """Das erste `</head>` außerhalb von HTML-Kommentaren (Treffer, Gruppe 1) oder None."""
    for m in _KOPF_ENDE_ODER_KOMMENTAR_RE.finditer(text):
        if m.group(1):
            return m
    return None


def _ist_zusatz(treffer) -> bool:
    return bool(_ZUSATZ_RE.search(treffer.group(2)))


def _ist_selbstschliessend(treffer) -> bool:
    return treffer.group(1).endswith("/>")


def _zeilenrand(text: str, anfang: int, ende: int) -> tuple:
    """Erweitert [anfang, ende) auf die ganze Zeile, wenn der Block allein auf ihr steht."""
    a = anfang
    while a > 0 and text[a - 1] in " \t":
        a -= 1
    e = ende
    while e < len(text) and text[e] in " \t":
        e += 1
    steht_allein = (a == 0 or text[a - 1] == "\n") and (e >= len(text) or text[e] in "\r\n")
    if not steht_allein:
        return anfang, ende
    if text[e:e + 2] == "\r\n":
        e += 2
    elif text[e:e + 1] == "\n":
        e += 1
    return a, e


def stil_einsetzen(text: str, css: str) -> str:
    """Ersetzt in `text` den Themenblock durch `<style>{css}</style>`. Regeln:
      * genau EIN Block ohne `data-zusatz` bleibt übrig; weitere solche Blöcke entfallen,
      * Blöcke mit `data-zusatz` bleiben byte-genau stehen,
      * der Themenblock steht vor dem ersten Zusatzblock,
      * fehlt ein Themenblock, wird er vor dem ersten Zusatzblock bzw. vor `</head>` angelegt,
      * ein `<style/>` entfällt immer, auch mit `data-zusatz` (er trägt keine Regeln und zerstört den
        folgenden Block, s. `_STIL_ODER_KOMMENTAR_RE`).
    Sonst bleibt der Text, wie er war. Ohne `</head>` und ohne Block: `EinsetzenFehler`."""
    block = f"<style>{css}</style>"
    treffer = _stilbloecke(text)
    leere = [m for m in treffer if _ist_selbstschliessend(m)]
    treffer = [m for m in treffer if not _ist_selbstschliessend(m)]
    themen = [m for m in treffer if not _ist_zusatz(m)]
    zusaetze = [m for m in treffer if _ist_zusatz(m)]

    ersetzungen = []           # (anfang, ende, neuer Text)
    if themen and not (zusaetze and zusaetze[0].start(1) < themen[0].start(1)):
        ersetzungen.append((themen[0].start(1), themen[0].end(1), block))
        rest = themen[1:]
    else:
        if zusaetze:
            anker = zusaetze[0].start(1)
            a, _ = _zeilenrand(text, anker, zusaetze[0].end(1))
            vorne = text[a:anker]
            ersetzungen.append((a, a, f"{vorne}{block}\n"))
        else:
            kopf = _kopf_ende(text)
            if not kopf:
                raise EinsetzenFehler("Der Bericht hat weder einen <style>-Block noch ein </head>.")
            davor = "" if kopf.start() == 0 or text[kopf.start() - 1] == "\n" else "\n"
            ersetzungen.append((kopf.start(), kopf.start(), f"{davor}{block}\n"))
        rest = themen
    for m in rest + leere:
        a, e = _zeilenrand(text, m.start(1), m.end(1))
        ersetzungen.append((a, e, ""))

    neu = text
    for a, e, ersatz in sorted(ersetzungen, key=lambda r: (r[0], r[1]), reverse=True):
        neu = neu[:a] + ersatz + neu[e:]
    return neu


@dataclass
class Ergebnis:
    pfad: Path
    geaendert: bool = False
    stil_geaendert: bool = False
    icon_geaendert: bool = False
    klassen_ohne_regel: list = field(default_factory=list)


def bericht_einsetzen_text(text: str) -> str:
    """Der Bericht-Text mit dem CSS und dem Icon des geltenden Designs (ohne Dateizugriff)."""
    from app import favicon     # lazy: das Modul braucht beim Import weder App noch Icon

    return favicon.mit_favicon(stil_einsetzen(text, bericht_css()))


def _atomar_schreiben(pfad: Path, daten: bytes) -> None:
    """Schreibt in eine Nachbardatei und ersetzt dann in einem Schritt; Zugriffsrechte bleiben."""
    rechte = stat.S_IMODE(pfad.stat().st_mode)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{pfad.name}.", suffix=".tmp", dir=str(pfad.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(daten)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_name, rechte)
        os.replace(tmp_name, pfad)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def einsetzen(pfad) -> Ergebnis:
    """Setzt Stil und Icon des geltenden Designs in die Datei `pfad` ein (siehe Moduldoc). Schreibt nur,
    wenn sich etwas ändert. Wirft `EinsetzenFehler` (kein <head>, nicht UTF-8) oder `OSError`."""
    from app import favicon
    from pipeline import report_check

    p = Path(pfad).resolve()
    try:
        roh = p.read_bytes()
        text = roh.decode("utf-8")
    except UnicodeDecodeError as fehler:
        raise EinsetzenFehler(f"{p.name}: keine UTF-8-Datei ({fehler.reason}).") from fehler
    nur_stil = stil_einsetzen(text, bericht_css())
    neu = favicon.mit_favicon(nur_stil)
    ergebnis = Ergebnis(pfad=p, geaendert=neu != text, stil_geaendert=nur_stil != text,
                        icon_geaendert=neu != nur_stil)
    if ergebnis.geaendert:
        _atomar_schreiben(p, neu.encode("utf-8"))
    ergebnis.klassen_ohne_regel = report_check.pruefe(neu)
    return ergebnis


# ── Die Vorlage ───────────────────────────────────────────────────────────────────────────────
def vorlage_soll(text: str) -> str:
    """Die Vorlage, wie sie sein muss: ihr Stil-Block ist `bericht_css()` mit der VORGABE."""
    return stil_einsetzen(text, bericht_css(design=design_modul.vorgabe()))


def vorlage_abweichung(pfad: Optional[Path] = None) -> Optional[str]:
    """None, wenn der Stil-Block der Vorlage genau `bericht_css()` mit der Vorgabe ist, sonst ein Satz."""
    p = Path(pfad) if pfad else VORLAGE
    text = p.read_text(encoding="utf-8")
    if vorlage_soll(text) == text:
        return None
    return (f"{p.name}: Der <style>-Block weicht von bericht_css() mit der Vorgabe ab. Neu erzeugen mit: "
            "cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.bericht_stil vorlage")


def vorlage_schreiben(pfad: Optional[Path] = None) -> bool:
    """Erzeugt den Stil-Block der Vorlage neu. True, wenn die Datei sich geändert hat."""
    p = Path(pfad) if pfad else VORLAGE
    text = p.read_text(encoding="utf-8")
    neu = vorlage_soll(text)
    if neu == text:
        return False
    _atomar_schreiben(p, neu.encode("utf-8"))
    return True


# ── Kommandozeile ─────────────────────────────────────────────────────────────────────────────
_NUTZUNG = ("Nutzung: python -m pipeline.bericht_stil einsetzen <bericht.html> [...]\n"
            "         python -m pipeline.bericht_stil vorlage [--pruefen]")


def _cmd_einsetzen(dateien: list) -> int:
    if not dateien:
        print(_NUTZUNG, file=sys.stderr)
        return EXIT_FEHLER
    schlimmstes = EXIT_OK
    for arg in dateien:
        p = Path(arg)
        if not p.is_file():
            print(f"✗ {arg}: Datei nicht gefunden", file=sys.stderr)
            schlimmstes = max(schlimmstes, EXIT_FEHLER)
            continue
        try:
            erg = einsetzen(p)
        except (EinsetzenFehler, OSError, design_modul.DesignFehler) as fehler:
            print(f"✗ {p.name}: {fehler}", file=sys.stderr)
            schlimmstes = max(schlimmstes, EXIT_FEHLER)
            continue
        was = []
        if erg.stil_geaendert:
            was.append("Stil")
        if erg.icon_geaendert:
            was.append("Icon")
        print(f"✓ {p.name}: " + (" und ".join(was) + " eingesetzt" if was else "schon aktuell, unverändert"))
        if erg.klassen_ohne_regel:
            for satz in erg.klassen_ohne_regel:
                print(f"    {satz}")
            print("    → Für diese Klassen gibt es keine Regel. Jede Klasse durch eine aus "
                  "assets/report_theme_bms.html ersetzen und den Befehl noch einmal aufrufen.")
            schlimmstes = max(schlimmstes, EXIT_KLASSEN_OHNE_REGEL)
    return schlimmstes


def _cmd_vorlage(argumente: list) -> int:
    if argumente not in ([], ["--pruefen"]):
        print(_NUTZUNG, file=sys.stderr)
        return EXIT_FEHLER
    if argumente:
        abweichung = vorlage_abweichung()
        if abweichung:
            print(abweichung, file=sys.stderr)
            return EXIT_VORLAGE_ABWEICHT
        print(f"{VORLAGE.name}: aktuell")
        return EXIT_OK
    print(f"{VORLAGE.name}: " + ("neu erzeugt" if vorlage_schreiben() else "schon aktuell"))
    return EXIT_OK


def main(argv: Optional[list] = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["einsetzen"]:
        return _cmd_einsetzen(argv[1:])
    if argv[:1] == ["vorlage"]:
        return _cmd_vorlage(argv[1:])
    print(_NUTZUNG, file=sys.stderr)
    return EXIT_FEHLER


if __name__ == "__main__":
    sys.exit(main())
