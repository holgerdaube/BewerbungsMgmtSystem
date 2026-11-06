"""P2-95: Konsolenmeldungen des Servers folgen der Sprache des Betriebssystems (app/terminal.py)."""
from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path

import pytest

from app import terminal

APP = Path(__file__).resolve().parent.parent / "app"
KATALOG = APP / "texte" / "en_terminal.json"
AUSGABE_FUNKTIONEN = {"print", "_log"}


@pytest.fixture(autouse=True)
def _frisch(monkeypatch):
    """Jeder Test beginnt ohne gemerkte Sprache; danach gilt wieder die Vorgabe aus conftest (de)."""
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)
    terminal.zuruecksetzen()
    yield
    monkeypatch.undo()
    terminal.zuruecksetzen()


def _fake_run(ausgaben: dict[str, str]):
    def run(cmd, **kwargs):
        schluessel = cmd[-1]
        if schluessel not in ausgaben:
            return subprocess.CompletedProcess(cmd, 1, "", "err")
        return subprocess.CompletedProcess(cmd, 0, ausgaben[schluessel], "")
    return run


# ── Erkennung ───────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("wert, erwartet", [("de", "de"), ("en", "en"), ("DE", "de"), (" en ", "en")])
def test_umgebungsvariable_gewinnt(monkeypatch, wert, erwartet):
    monkeypatch.setenv("BMS_TERMINAL_SPRACHE", wert)
    monkeypatch.setenv("LANG", "fr_FR.UTF-8" if erwartet == "de" else "de_DE.UTF-8")
    monkeypatch.setattr(terminal.sys, "platform", "linux")
    assert terminal.sprache() == erwartet


def test_macos_erster_eintrag_von_applelanguages(monkeypatch):
    monkeypatch.delenv("BMS_TERMINAL_SPRACHE", raising=False)
    monkeypatch.setattr(terminal.sys, "platform", "darwin")
    monkeypatch.setattr(terminal.subprocess, "run", _fake_run(
        {"AppleLanguages": '(\n    "de-DE",\n    "en-US"\n)\n', "AppleLocale": "en_US"}))
    assert terminal.sprache() == "de"
    terminal.zuruecksetzen()
    monkeypatch.setattr(terminal.subprocess, "run", _fake_run(
        {"AppleLanguages": '(\n    "en-GB",\n    "de-DE"\n)\n', "AppleLocale": "de_DE"}))
    assert terminal.sprache() == "en"      # nur der ERSTE Eintrag zählt


def test_macos_ohne_applelanguages_gilt_applelocale(monkeypatch):
    monkeypatch.delenv("BMS_TERMINAL_SPRACHE", raising=False)
    monkeypatch.setattr(terminal.sys, "platform", "darwin")
    monkeypatch.setattr(terminal.subprocess, "run", _fake_run({"AppleLocale": "de_AT\n"}))
    assert terminal.sprache() == "de"


def test_umgebung_reihenfolge_lc_all_vor_lang(monkeypatch):
    monkeypatch.delenv("BMS_TERMINAL_SPRACHE", raising=False)
    monkeypatch.setattr(terminal.sys, "platform", "linux")
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    monkeypatch.setenv("LC_ALL", "en_GB.UTF-8")
    assert terminal.sprache() == "en"


def test_fehler_bei_der_erkennung_ergibt_englisch(monkeypatch):
    monkeypatch.delenv("BMS_TERMINAL_SPRACHE", raising=False)
    monkeypatch.setattr(terminal.sys, "platform", "darwin")

    def kaputt(*a, **k):
        raise OSError("kein defaults")
    monkeypatch.setattr(terminal.subprocess, "run", kaputt)
    assert terminal.sprache() == "en"


def test_nichts_gesetzt_ergibt_englisch(monkeypatch):
    monkeypatch.delenv("BMS_TERMINAL_SPRACHE", raising=False)
    monkeypatch.setattr(terminal.sys, "platform", "linux")
    assert terminal.sprache() == "en"


def test_ungueltige_vorgabe_wird_ignoriert(monkeypatch):
    monkeypatch.setenv("BMS_TERMINAL_SPRACHE", "fr")
    monkeypatch.setattr(terminal.sys, "platform", "linux")
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    assert terminal.sprache() == "de"


def test_ergebnis_wird_einmal_gemerkt(monkeypatch):
    monkeypatch.setenv("BMS_TERMINAL_SPRACHE", "en")
    assert terminal.sprache() == "en"
    monkeypatch.setenv("BMS_TERMINAL_SPRACHE", "de")
    assert terminal.sprache() == "en"
    terminal.zuruecksetzen()
    assert terminal.sprache() == "de"


# ── tt ──────────────────────────────────────────────────────────────────────────────────────────
def test_tt_deutsch_ist_unveraendert(monkeypatch):
    monkeypatch.setenv("BMS_TERMINAL_SPRACHE", "de")
    assert terminal.tt("[sicherung] {anzahl} alte Sicherung(en) entfernt", anzahl=2) == \
        "[sicherung] 2 alte Sicherung(en) entfernt"
    assert terminal.tt("Selbsttest bestanden") == "Selbsttest bestanden"
    assert terminal.tt("[sicherung] gesichert: {name} ({groesse} Bytes, {dauer:.1f} s)",
                       name="a.zip", groesse=10, dauer=1.26) == "[sicherung] gesichert: a.zip (10 Bytes, 1.3 s)"


def test_tt_englisch_uebersetzt(monkeypatch):
    monkeypatch.setenv("BMS_TERMINAL_SPRACHE", "en")
    assert terminal.tt("[sicherung] {anzahl} alte Sicherung(en) entfernt", anzahl=2) == \
        "[sicherung] 2 old backup(s) removed"
    assert terminal.tt("Selbsttest bestanden") == "Self-test passed"


def test_tt_fehlender_eintrag_faellt_auf_deutsch_zurueck(monkeypatch):
    monkeypatch.setenv("BMS_TERMINAL_SPRACHE", "en")
    assert terminal.tt("Nur im Test {x}", x=1) == "Nur im Test 1"


def test_tt_wirft_nie_bei_falschen_platzhaltern(monkeypatch):
    monkeypatch.setenv("BMS_TERMINAL_SPRACHE", "en")
    assert isinstance(terminal.tt("[sicherung] {anzahl} alte Sicherung(en) entfernt", falsch=1), str)


# ── Wächter über backend/app/*.py ───────────────────────────────────────────────────────────────
def _quellen():
    for datei in sorted(APP.glob("*.py")):
        yield datei, ast.parse(datei.read_text(encoding="utf-8"))


def _tt_aufrufe():
    for datei, baum in _quellen():
        for n in ast.walk(baum):
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "tt":
                yield datei, n


def _platzhalter(text: str) -> list[str]:
    return sorted(re.findall(r"\{(\w+)", text))


def _literale_ausserhalb_tt(knoten: ast.AST):
    """Textliterale eines Ausdrucks, ohne die in einem `tt(...)`-Aufruf."""
    if isinstance(knoten, ast.Call) and getattr(knoten.func, "id", None) == "tt":
        return
    if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str):
        yield knoten.value
    for kind in ast.iter_child_nodes(knoten):
        yield from _literale_ausserhalb_tt(kind)


def test_jede_konsolenausgabe_laeuft_durch_tt():
    verstoesse = []
    for datei, baum in _quellen():
        if datei.name == "terminal.py":
            continue
        for n in ast.walk(baum):
            if not (isinstance(n, ast.Call) and getattr(n.func, "id", None) in AUSGABE_FUNKTIONEN):
                continue
            argumente = list(n.args) + [k.value for k in n.keywords if k.arg in (None, "sep", "end")]
            for arg in argumente:
                for text in _literale_ausserhalb_tt(arg):
                    if re.fullmatch(r"\[[\w-]+\] ?", text):
                        continue      # Präfix wie "[beispieldaten] " ist in beiden Sprachen gleich
                    if re.search(r"[A-Za-zÄÖÜäöüß]{3}", text):
                        verstoesse.append(f"{datei.name}:{n.lineno}: {text[:60]!r}")
    assert not verstoesse, "print/_log mit Text ohne tt():\n" + "\n".join(verstoesse)


def test_tt_wird_nur_mit_literal_aufgerufen():
    schlecht = [f"{d.name}:{n.lineno}" for d, n in _tt_aufrufe()
                if not (n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str))]
    assert not schlecht, schlecht


def test_jede_tt_vorlage_steht_im_katalog_und_umgekehrt():
    katalog = json.loads(KATALOG.read_text(encoding="utf-8"))
    benutzt = {n.args[0].value for d, n in _tt_aufrufe() if d.name != "terminal.py"
               and n.args and isinstance(n.args[0], ast.Constant)}
    assert benutzt, "keine tt-Aufrufe gefunden"
    assert sorted(benutzt - katalog.keys()) == []
    assert sorted(katalog.keys() - benutzt) == [], "Katalogeinträge ohne tt-Aufruf (veraltet)"


def test_katalog_hat_auf_beiden_seiten_dieselben_platzhalter():
    katalog = json.loads(KATALOG.read_text(encoding="utf-8"))
    for de, en in katalog.items():
        assert _platzhalter(de) == _platzhalter(en), de
        assert en.strip(), de


def test_katalog_enthaelt_keinen_deutschen_text():
    katalog = json.loads(KATALOG.read_text(encoding="utf-8"))
    for de, en in katalog.items():
        assert not re.search(r"[äöüÄÖÜß]", en), en
        assert not re.search(r"\b(WARNUNG|KRITISCH|FEHLER|nicht|wurde|für|und)\b", en), en


def test_aufrufe_liefern_in_beiden_sprachen_ohne_platzhalterrest(monkeypatch):
    """Jede Vorlage lässt sich mit ihren eigenen Platzhaltern füllen, deutsch wie englisch."""
    katalog = json.loads(KATALOG.read_text(encoding="utf-8"))
    for sprache in ("de", "en"):
        monkeypatch.setenv("BMS_TERMINAL_SPRACHE", sprache)
        terminal.zuruecksetzen()
        for de in katalog:
            werte = {p: 1 for p in _platzhalter(de)}
            if "dauer" in werte:
                werte["dauer"] = 1.0
            text = terminal.tt(de, **werte)
            assert "{" not in text, (sprache, de)
