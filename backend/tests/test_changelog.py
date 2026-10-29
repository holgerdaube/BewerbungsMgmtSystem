"""P2-51 — `pipeline/changelog.py`: Abschnitte lesen, Freigabe fortschreiben, Formfehler melden.

App-Module nur funktionslokal importieren (s. conftest.py).
"""
from datetime import date

import pytest

TEXT = """# Änderungen

Einleitung.

## Unveröffentlicht

- Neuer Punkt A
- Neuer Punkt B

## 1.0.0 (01.09.2026)

- Alter Punkt
"""


def test_abschnitt_liest_version_und_unveroeffentlicht():
    from pipeline.changelog import abschnitt

    assert abschnitt(TEXT, "1.0.0") == "- Alter Punkt"
    assert abschnitt(TEXT, None) == "- Neuer Punkt A\n- Neuer Punkt B"
    assert abschnitt(TEXT, "9.9.9") is None


def test_freigeben_macht_aus_unveroeffentlicht_die_version():
    from pipeline.changelog import abschnitt, freigeben, pruefen

    neu = freigeben(TEXT, "1.1.0", date(2026, 9, 28))
    assert "## 1.1.0 (28.09.2026)\n\n- Neuer Punkt A\n- Neuer Punkt B\n" in neu
    assert abschnitt(neu, None) is None  # neuer, leerer Abschnitt steht oben
    assert neu.index("## Unveröffentlicht") < neu.index("## 1.1.0") < neu.index("## 1.0.0")
    assert abschnitt(neu, "1.0.0") == "- Alter Punkt"
    assert pruefen(neu) == []


def test_erste_freigabe_ohne_aeltere_abschnitte():
    from pipeline.changelog import abschnitt, freigeben

    text = "# Änderungen\n\n## Unveröffentlicht\n\n- Erste Version\n"
    neu = freigeben(text, "1.0.0", date(2026, 9, 28))
    assert neu == "# Änderungen\n\n## Unveröffentlicht\n\n## 1.0.0 (28.09.2026)\n\n- Erste Version\n"
    assert abschnitt(neu, "1.0.0") == "- Erste Version"


@pytest.mark.parametrize("text, meldung", [
    ("# Änderungen\n\n## 1.0.0 (01.09.2026)\n\n- x\n", "fehlt"),
    ("# Änderungen\n\n## Unveröffentlicht\n\n\n## 1.0.0 (01.09.2026)\n\n- x\n", "leer"),
    (TEXT + "\n## 1.1 (02.09.2026)\n\n- y\n", "falschen Format"),
])
def test_freigeben_verweigert(text, meldung):
    from pipeline.changelog import ChangelogFehler, freigeben

    with pytest.raises(ChangelogFehler, match=meldung):
        freigeben(text, "1.1.0", date(2026, 9, 28))


def test_freigeben_verweigert_vorhandene_version():
    from pipeline.changelog import ChangelogFehler, freigeben

    with pytest.raises(ChangelogFehler, match="schon"):
        freigeben(TEXT, "1.0.0", date(2026, 9, 28))


@pytest.mark.parametrize("wert, erwartet", [("1.2.3", (1, 2, 3)), ("0.0.0", (0, 0, 0)), (" 10.0.1\n", (10, 0, 1))])
def test_version_tupel(wert, erwartet):
    from pipeline.changelog import version_tupel

    assert version_tupel(wert) == erwartet


@pytest.mark.parametrize("wert", ["v1.2.3", "1.2", "1.2.3-beta", ""])
def test_version_tupel_lehnt_ab(wert):
    from pipeline.changelog import ChangelogFehler, version_tupel

    with pytest.raises(ChangelogFehler):
        version_tupel(wert)


def test_echtes_changelog_ist_formgerecht():
    """Das ausgelieferte CHANGELOG.md muss der Freigabe standhalten (Wächter)."""
    from pipeline.changelog import pruefen
    from pipeline.kundenpaket import PROJECT_ROOT

    text = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert pruefen(text) == []
    assert "## Unveröffentlicht" in text
