#!/usr/bin/env python3
"""Report-Selbstprüfung: benutzte CSS-Klassen ⇔ vorhandene CSS-Regeln (23.07.2026).

Hintergrund: Die generierten HTML-Reports (ATS-Scan, Match, Company-Fit, …) sind EIGENSTÄNDIGE
Dateien — das Theme `assets/report_theme_bms.html` wird nicht verlinkt, sein CSS also in
den `<style>`-Block kopiert. Kürzt ein Lauf dabei das CSS, ist das Markup weiterhin korrekt, aber
die Darstellung bricht LAUTLOS: Am 23.07.2026 standen in einem ATS-Scan 9× `class="chip pos"` und
6× `class="chip neg"`, die Regeln `.chip.pos`/`.chip.neg` fehlten aber im `<style>` — alle
Keyword-Chips erschienen grau statt grün/rot. Der Nutzer hat es gesehen, keine Automatik.

Dieser Check ist die Gegenmaßnahme: rein deterministisch (kein LLM, keine Kosten), meldet jede
im Markup benutzte, aber nicht definierte Bedeutungs-Klasse.

CLI:
    cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.report_check <report.html> [...]
Exit-Code 0 = ok, 1 = mindestens eine Regel fehlt (Details auf stdout).
"""

import re
import sys
from collections import Counter
from pathlib import Path

# Generisch statt fester Klassenliste: Eine gepflegte Liste war der erste Versuch und ging schief —
# sie enthielt geratene Namen (`badge gruen`), während die Reports real `badge pos/neg/neu`,
# `kw hit/miss`, `status ok/risk`, `fscore hi/mid/lo`, `verdict amber` … benutzen. Ein Checker,
# der die halben Klassen nicht kennt, meldet fälschlich „grün". Deshalb: JEDE im Markup benutzte
# Klassen-Kombination gegen das CSS prüfen, ohne Vorwissen über Report-Typen.


def _styles(html: str) -> str:
    return "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S | re.I))


def _markup_ohne_code(html: str) -> str:
    """HTML ohne <style>- und <script>-Inhalte.

    Ohne diesen Schnitt entstehen Fehlalarme: mehrere Company-Fit-Reports bauen ihre Badges per
    JS zusammen (`class="${badgeClass(r.score)} badge"`). Das ist ein Template-Literal, keine
    Klasse — die echte Klasse entsteht erst zur Laufzeit und ist statisch nicht prüfbar.
    """
    ohne = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.S | re.I)
    return re.sub(r"<script[^>]*>.*?</script>", " ", ohne, flags=re.S | re.I)


# Eine Selektor-Einheit: optionaler Element-Name + eine oder mehrere Klassen
# (`table.score`, `.chip`, `.badge.pos`). Der optionale Element-Teil ist wichtig — ohne ihn
# galt `score` in `table.score{…}` als undefiniert und alle 46 Beirats-Checks wurden
# fälschlich beanstandet (`<table class="score risiko">`).
_SEL_UNIT = re.compile(r"(?:[A-Za-z][\w-]*)?((?:\.[A-Za-z][\w-]*)+)")


def _css_index(styles: str) -> tuple:
    """(allein wirksame Klassen, kombinierte Selektoren) — EINMAL aufgebaut statt pro
    Kombination neu zu suchen; über den ganzen Report-Bestand sonst zu langsam.

    Die Unterscheidung ist der Kern des Checks: In `.badge.pos{…}` wirkt `.pos` NUR zusammen mit
    `.badge` — als eigenständige Regel zählt es nicht. Ohne das galt im echten Defekt `pos` als
    definiert (wegen `.badge.pos`), obwohl `.chip.pos` fehlte, und der Originalfehler wäre
    durchgerutscht. Ein Element-Präfix (`table.score`) ändert dagegen nichts an der Klasse selbst.
    """
    allein, kombis = set(), set()
    for m in _SEL_UNIT.finditer(styles):
        klassen = [k for k in m.group(1).split(".") if k]
        if len(klassen) == 1:
            allein.add(klassen[0])
        else:
            kombis.add(tuple(sorted(klassen)))
    return allein, kombis


def pruefe(html: str) -> list:
    """→ Liste der Beanstandungen (leer = ok): Klassen-Kombinationen, die im Markup stehen,
    im CSS aber keinerlei Regel haben (= wirkungslos, Farbe/Bedeutung geht verloren).

    Regel: entweder existiert der kombinierte Selektor (`.chip.pos`), oder JEDER Teil ist
    einzeln definiert. Es reicht ausdrücklich NICHT, dass nur die Basisklasse existiert — im
    echten Fall war `.chip` da und nur der bedeutungstragende Modifikator `.pos` fehlte.
    """
    styles = _styles(html)
    if not styles.strip():
        return ["kein <style>-Block im Report — Theme-CSS fehlt komplett"]

    allein, kombis = _css_index(styles)
    markup = _markup_ohne_code(html)

    benutzt = Counter()
    for attr in re.findall(r'class="([^"]+)"', markup):
        if "${" in attr or "{{" in attr:          # Template-Literal, keine echte Klasse
            continue
        # Fremd-Markup überspringen: Anzeigen-Snapshots (data/job_postings) enthalten den
        # kopierten Original-HTML der Stellenseite samt fremder Utility-Frameworks (Tailwind:
        # `hover:bg-…`, `px-2`, `w-full`, `!font-regular`). Deren Regeln liegen beim Fremdanbieter
        # und sollen hier gar nicht vorhanden sein — sie sind kein Report-Layout.
        if any(z in attr for z in (":", "[", "!", "/")) or len(attr.split()) > 6:
            continue
        teile = tuple(sorted(t for t in attr.split() if t))
        if len(teile) >= 2:                        # nur Kombinationen (Basis + Modifikator)
            benutzt[teile] += 1

    fehler = []
    for teile, n in sorted(benutzt.items(), key=lambda x: -x[1]):
        vorhanden = set(teile)
        # Eine Klasse ist wirksam, wenn irgendeine Regel sie erfasst, deren Selektor-Klassen
        # alle im selben class-Attribut stehen. CSS matcht Teilmengen: `.status.risk{…}` greift
        # auch bei class="status risk schwach". Die frühere Alles-oder-nichts-Prüfung erzeugte
        # dadurch massenhaft Fehlalarme (73 von 202 Reports).
        unwirksam = [
            t for t in teile
            if t not in allein
            and not any(t in k and set(k) <= vorhanden for k in kombis)
        ]
        if not unwirksam:
            continue
        fehler.append(f'{n}× class="{" ".join(teile)}" im Markup, '
                      f'aber {", ".join("." + t for t in unwirksam)} ohne Regel im <style>')
    return fehler


def main(argv: list) -> int:
    if not argv:
        print("Nutzung: python -m pipeline.report_check <report.html> [...]", file=sys.stderr)
        return 2
    schlecht = 0
    for arg in argv:
        p = Path(arg)
        if not p.exists():
            print(f"✗ {arg}: Datei nicht gefunden")
            schlecht += 1
            continue
        fehler = pruefe(p.read_text(encoding="utf-8", errors="replace"))
        if fehler:
            schlecht += 1
            print(f"✗ {p.name}")
            for f in fehler:
                print(f"    {f}")
        else:
            print(f"✓ {p.name}")
    if schlecht:
        print(f"\n{schlecht} Report(s) mit fehlenden CSS-Regeln — `python -m pipeline.bericht_stil "
              f"einsetzen <Datei>` setzt das vollständige CSS ein. Fehlt danach noch eine Regel, "
              f"die Klasse durch eine aus assets/report_theme_bms.html ersetzen.")
    return 1 if schlecht else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
