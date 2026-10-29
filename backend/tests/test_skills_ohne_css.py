"""P2-72 (Paket S, Vertrag S): Die sechs Skills, die HTML-Berichte schreiben, enthalten kein CSS mehr.

Die Skills `job-deepdive`, `absagen-analyse`, `angebot-vergleich`, `interview-vorbereiten`, `cv-match` und
`cv-erstellen` schreiben HTML mit Klassen. Danach setzt der Befehl `bericht_stil einsetzen` den Stil des
geltenden Designs ein, und `report_check` prüft das Ergebnis. Was hier festgehalten wird:

  1. Im Skill-Text steht kein Farbwert, kein Style-Block, keine Inline-Farbe und keine CSS-Regel, und kein
     Wort für eine Markenfarbe (ein Partner-Design muss nicht Navy und Cyan heißen).
  2. Jeder der sechs nennt `bericht_stil einsetzen` und danach `report_check`, in der Schreibweise, die die
     Skills für Python-Werkzeuge schon verwenden.
  3. Jede Klasse im wörtlichen HTML der Skills hat eine Regel im zentralen CSS (`bericht_css()`) oder steht
     in der begründeten Positivliste, und die Klassen-Kombinationen bestehen `report_check`.
  4. Die Vorlage `assets/report_theme_bms.html` zeigt dieselben Klassen und bietet keinen Block `data-zusatz`
     an; kein Skill leitet zu eigenem CSS an.

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention). Es wird nur gelesen.
"""
import re
from pathlib import Path

import pytest

PROJEKT = Path(__file__).resolve().parents[2]
SKILLS = ("job-deepdive", "absagen-analyse", "angebot-vergleich", "interview-vorbereiten",
          "cv-match", "cv-erstellen")

FARBWERT_RE = re.compile(r"#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|\b(?:rgba?|hsla?)\s*\(", re.I)
STILBLOCK_RE = re.compile(r"<style", re.I)
# Eine CSS-Regel in einer Zeile oder über mehrere: `{ … eigenschaft: wert; … }`. JSON und Python-Wörterbücher
# haben kein Semikolon zwischen den Klammern.
CSS_REGEL_RE = re.compile(r"\{[^{}`]*?[a-z-]+\s*:\s*[^{}`;]+;[^{}`]*\}")
INLINE_STIL_RE = re.compile(r"""style\s*=\s*(["'])(.*?)\1""", re.I | re.S)
# Eigenschaften, die Farbe tragen (Layout wie `margin-top` ist erlaubt, es hängt nicht am Design).
FARB_EIGENSCHAFT_RE = re.compile(r"\b(?:color|background|border|outline|fill|stroke|shadow|opacity|filter)\b", re.I)
MARKENFARBE_WORT_RE = re.compile(r"\b(?:navy|cyan)\b", re.I)
KLASSE_RE = re.compile(r"""class\s*=\s*(["'])(.*?)\1""", re.I | re.S)

# Klassen im wörtlichen HTML der Skills, die bewusst KEINE eigene Regel haben (Klassen ohne Gestaltung):
# {Klasse: Begründung}. Leer: Jede Klasse in den sechs Skills wird heute gestaltet.
KLASSEN_OHNE_GESTALTUNG = {}


def _text(skill: str) -> str:
    return (PROJEKT / ".claude" / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")


def _klassen_attribute(text: str) -> list:
    """Alle Werte von class="…" im Text (Code-Blöcke und Fließtext), ohne Doppelte, in Reihenfolge."""
    gesehen, aus = set(), []
    for m in KLASSE_RE.finditer(text):
        wert = " ".join(m.group(2).split())
        if wert and wert not in gesehen:
            gesehen.add(wert)
            aus.append(wert)
    return aus


# ── 1. Kein CSS im Skill-Text ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("skill", SKILLS)
def test_kein_farbwert_kein_style_block_keine_inline_farbe(skill):
    text = _text(skill)

    assert FARBWERT_RE.findall(text) == [], f"{skill}: Farbwert im Skill-Text"
    assert STILBLOCK_RE.search(text) is None, f"{skill}: Style-Block im Skill-Text"
    assert "data-zusatz" not in text, f"{skill}: leitet zu einem eigenen Zusatzblock an"
    assert CSS_REGEL_RE.findall(text) == [], f"{skill}: CSS-Regel im Skill-Text"
    assert MARKENFARBE_WORT_RE.search(text) is None, f"{skill}: nennt eine Markenfarbe beim Namen"
    for m in INLINE_STIL_RE.finditer(text):
        wert = m.group(2)
        assert not FARB_EIGENSCHAFT_RE.search(wert) and not FARBWERT_RE.search(wert), \
            f"{skill}: Inline-Stil mit Farbe: {wert}"


@pytest.mark.parametrize("skill", SKILLS)
def test_der_skill_text_nennt_keine_phasennummer_dieses_schritts(skill):
    """Skills gehen an Kunden: keine Phasen-Nummer dieses Umbaus im Text."""
    assert "P2-72" not in _text(skill)


# ── 2. Pflichtschritt: einsetzen, danach report_check ─────────────────────────────────────────
@pytest.mark.parametrize("skill", SKILLS)
def test_jeder_skill_nennt_einsetzen_und_danach_report_check(skill):
    text = _text(skill)

    befehl = "~/.bewerbung_mgmt_venv/bin/python -m pipeline.bericht_stil einsetzen"
    assert f"cd backend && {befehl}" in text, \
        f"{skill}: `einsetzen` fehlt in der Schreibweise der übrigen Python-Werkzeuge"
    erste = text.index("pipeline.bericht_stil einsetzen")
    assert "pipeline.report_check" in text[erste:], f"{skill}: `report_check` steht nicht NACH `einsetzen`"


@pytest.mark.parametrize("skill", SKILLS)
def test_der_bericht_wird_ohne_eigenen_style_block_geschrieben(skill):
    """Der Skill sagt ausdrücklich, dass der Bericht ohne Style-Block entsteht und der Befehl ihn einsetzt."""
    text = _text(skill)

    assert re.search(r"ohne eigenen\s+Style-Block|Style-Block\s+(?:der Vorlage\s+)?NICHT\s+abschreiben", text), \
        f"{skill}: nennt nicht, dass kein Style-Block geschrieben wird"


# ── 3. Die Klassen des wörtlichen HTML haben Regeln ───────────────────────────────────────────
@pytest.mark.parametrize("skill", SKILLS)
def test_jede_klasse_im_html_der_skills_hat_eine_regel(skill):
    from pipeline import bericht_stil

    css = bericht_stil.bericht_css()
    ohne_regel = []
    for wert in _klassen_attribute(_text(skill)):
        for klasse in wert.split():
            if klasse in KLASSEN_OHNE_GESTALTUNG:
                continue
            if not re.search(rf"\.{re.escape(klasse)}(?![\w-])", css):
                ohne_regel.append(klasse)
    assert ohne_regel == [], f"{skill}: Klassen ohne Regel im zentralen CSS: {sorted(set(ohne_regel))}"


@pytest.mark.parametrize("skill", SKILLS)
def test_die_klassen_kombinationen_der_skills_bestehen_report_check(skill):
    from pipeline import bericht_stil, report_check

    spans = "".join(f'<span class="{wert}"></span>' for wert in _klassen_attribute(_text(skill)))
    dokument = f"<html><head><style>{bericht_stil.bericht_css()}</style></head><body>{spans}</body></html>"

    assert report_check.pruefe(dokument) == []


def test_die_positivliste_ist_begruendet_und_nicht_veraltet():
    """Jeder Eintrag braucht eine Begründung und muss in einem Skill auch wirklich vorkommen."""
    vorhanden = {k for skill in SKILLS for w in _klassen_attribute(_text(skill)) for k in w.split()}
    for klasse, grund in KLASSEN_OHNE_GESTALTUNG.items():
        assert grund.strip(), klasse
        assert klasse in vorhanden, f"{klasse} steht in keinem Skill mehr — aus der Positivliste streichen"


# ── 4. Die Vorlage ─────────────────────────────────────────────────────────────────────────────
def test_die_vorlage_bietet_keinen_zusatzblock_an_und_zeigt_alle_klassen_der_skills():
    vorlage = (PROJEKT / "assets" / "report_theme_bms.html").read_text(encoding="utf-8")

    assert "data-zusatz" not in vorlage
    in_der_vorlage = {k for w in _klassen_attribute(vorlage) for k in w.split()}
    fehlen = {skill: sorted({k for w in _klassen_attribute(_text(skill)) for k in w.split()} - in_der_vorlage)
              for skill in SKILLS}
    assert {s: f for s, f in fehlen.items() if f} == {}, \
        "Klassen aus den Skills, die die Vorlage im Beispiel-Markup nicht zeigt"
