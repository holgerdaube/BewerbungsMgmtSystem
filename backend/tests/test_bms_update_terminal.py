"""Terminal-Sprache von scripts/bms_update.py (P2-95): Erkennung, englische Ausgabe und Waechter.

Die Waechtertests lesen den Quelltext per `ast` und stellen sicher, dass jeder Kundentext ueber
`_t(...)` laeuft und im Woerterbuch `_EN` steht -- ein neuer, vergessener Text faellt hier auf.
"""
from __future__ import annotations

import ast
import re
import string
import subprocess
import sys
from pathlib import Path

import pytest

SKRIPTE = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SKRIPTE))
import bms_update  # noqa: E402

QUELLE = SKRIPTE / "bms_update.py"


@pytest.fixture
def sprache(monkeypatch):
    """Schaltet die Terminalsprache um und setzt den Zwischenspeicher davor und danach zurueck."""
    def setzen(wert: str | None):
        bms_update._SPRACHE_ZWISCHENSPEICHER = None
        if wert is None:
            monkeypatch.delenv("BMS_TERMINAL_SPRACHE", raising=False)
        else:
            monkeypatch.setenv("BMS_TERMINAL_SPRACHE", wert)
    yield setzen
    bms_update._SPRACHE_ZWISCHENSPEICHER = None


# ── (1) Erkennungsreihenfolge ───────────────────────────────────────────────────────────────
def _fake_defaults(antworten: dict[str, tuple[int, str]]):
    def run(befehl, **kwargs):
        schluessel = befehl[-1]
        code, ausgabe = antworten.get(schluessel, (1, ""))
        return subprocess.CompletedProcess(befehl, code, stdout=ausgabe, stderr="")
    return run


MAC_DE = '(\n    "de-DE",\n    "en-DE"\n)\n'
MAC_EN = '(\n    "en-GB",\n    "de-DE"\n)\n'


def test_umgebungsvariable_gewinnt_vor_dem_system(sprache, monkeypatch):
    monkeypatch.setattr(bms_update.sys, "platform", "darwin")
    monkeypatch.setattr(bms_update.subprocess, "run", _fake_defaults({"AppleLanguages": (0, MAC_DE)}))
    sprache("en")
    assert bms_update._terminal_sprache() == "en"
    sprache("de")
    assert bms_update._terminal_sprache() == "de"


def test_macos_erster_eintrag_von_applelanguages(sprache, monkeypatch):
    monkeypatch.setattr(bms_update.sys, "platform", "darwin")
    monkeypatch.setattr(bms_update.subprocess, "run", _fake_defaults({"AppleLanguages": (0, MAC_DE)}))
    sprache(None)
    assert bms_update._terminal_sprache() == "de"
    monkeypatch.setattr(bms_update.subprocess, "run", _fake_defaults({"AppleLanguages": (0, MAC_EN)}))
    sprache(None)
    assert bms_update._terminal_sprache() == "en"      # nur der ERSTE Eintrag zaehlt


def test_macos_faellt_auf_applelocale_zurueck(sprache, monkeypatch):
    monkeypatch.setattr(bms_update.sys, "platform", "darwin")
    monkeypatch.setattr(bms_update.subprocess, "run",
                        _fake_defaults({"AppleLanguages": (1, ""), "AppleLocale": (0, "de_AT\n")}))
    sprache(None)
    assert bms_update._terminal_sprache() == "de"


def test_ohne_system_antwort_gelten_lc_und_lang(sprache, monkeypatch):
    monkeypatch.setattr(bms_update.sys, "platform", "linux")
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    sprache(None)
    assert bms_update._terminal_sprache() == "de"
    monkeypatch.setenv("LC_MESSAGES", "fr_FR.UTF-8")      # LC_MESSAGES schlaegt LANG
    sprache(None)
    assert bms_update._terminal_sprache() == "en"
    monkeypatch.setenv("LC_ALL", "de_DE.UTF-8")           # LC_ALL schlaegt beides
    sprache(None)
    assert bms_update._terminal_sprache() == "de"


def test_nichts_gesetzt_ist_englisch(sprache, monkeypatch):
    monkeypatch.setattr(bms_update.sys, "platform", "linux")
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)
    sprache(None)
    assert bms_update._terminal_sprache() == "en"


def test_windows_nutzt_die_ui_sprache(sprache, monkeypatch):
    class _Kernel:
        def __init__(self, kennung):
            self.kennung = kennung

        def GetUserDefaultUILanguage(self):
            return self.kennung

    class _Ctypes:
        def __init__(self, kennung):
            self.windll = type("W", (), {"kernel32": _Kernel(kennung)})()

    monkeypatch.setattr(bms_update.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "ctypes", _Ctypes(0x0407))      # de-DE
    sprache(None)
    assert bms_update._terminal_sprache() == "de"
    monkeypatch.setitem(sys.modules, "ctypes", _Ctypes(0x0809))      # en-GB
    sprache(None)
    assert bms_update._terminal_sprache() == "en"


def test_fehler_bei_der_erkennung_ist_englisch(sprache, monkeypatch):
    monkeypatch.setattr(bms_update.sys, "platform", "darwin")

    def kaputt(befehl, **kwargs):
        raise OSError("defaults fehlt")

    monkeypatch.setattr(bms_update.subprocess, "run", kaputt)
    monkeypatch.setenv("LANG", "de_DE.UTF-8")         # selbst ein deutsches LANG rettet den Fehlerfall nicht
    sprache(None)
    assert bms_update._terminal_sprache() == "en"


def test_ungueltige_umgebungsvariable_wird_ignoriert(sprache, monkeypatch):
    monkeypatch.setattr(bms_update.sys, "platform", "darwin")
    monkeypatch.setattr(bms_update.subprocess, "run", _fake_defaults({"AppleLanguages": (0, MAC_DE)}))
    sprache("fr")
    assert bms_update._terminal_sprache() == "de"


def test_systemabfrage_wird_einmal_je_prozess_gemerkt(sprache, monkeypatch):
    monkeypatch.setattr(bms_update.sys, "platform", "darwin")
    aufrufe = []

    def run(befehl, **kwargs):
        aufrufe.append(befehl)
        return subprocess.CompletedProcess(befehl, 0, stdout=MAC_DE, stderr="")

    monkeypatch.setattr(bms_update.subprocess, "run", run)
    sprache(None)
    assert bms_update._terminal_sprache() == "de"
    assert bms_update._terminal_sprache() == "de"
    assert len(aufrufe) == 1


# ── (2) Englische Ausgabe ───────────────────────────────────────────────────────────────────
def test_hilfe_ist_englisch(sprache, capsys):
    sprache("en")
    with pytest.raises(SystemExit):
        bms_update._parser().parse_args(["--help"])
    ausgabe = capsys.readouterr().out
    assert "Installs a new BMS version without losing your data or customisations." in ausgabe
    assert "Program folder of the installation." in ausgabe
    assert "Programmordner" not in ausgabe and "Spielt" not in ausgabe


def test_hilfe_deutsch_bleibt_wie_vorher(sprache, capsys):
    sprache("de")
    with pytest.raises(SystemExit):
        bms_update._parser().parse_args(["--help"])
    ausgabe = capsys.readouterr().out
    assert "Spielt eine neue BMS-Version ein, ohne Daten oder Anpassungen zu verlieren." in ausgabe
    assert "Programmordner der Installation." in ausgabe


def test_abbruchmeldung_ist_englisch(sprache, tmp_path, capsys):
    sprache("en")
    code = bms_update.main(["--installation", str(tmp_path / "gibt-es-nicht"), "--offline"])
    assert code == bms_update.EXIT_ABGEBROCHEN
    assert capsys.readouterr().out.strip() == f"The folder “{tmp_path / 'gibt-es-nicht'}” was not found."


def test_abbruchmeldung_deutsch_ist_byte_gleich(sprache, tmp_path, capsys):
    sprache("de")
    code = bms_update.main(["--installation", str(tmp_path / "gibt-es-nicht"), "--offline"])
    assert code == bms_update.EXIT_ABGEBROCHEN
    assert capsys.readouterr().out.strip() == f"Der Ordner „{tmp_path / 'gibt-es-nicht'}“ wurde nicht gefunden."


def test_aufruffehler_ist_englisch_mit_exit_3(sprache, capsys):
    sprache("en")
    assert bms_update.main([]) == bms_update.EXIT_AUFRUF_FALSCH
    assert capsys.readouterr().out.startswith("Error: ")


def test_rueckfrage_und_kennzahlen_englisch(sprache):
    sprache("en")
    assert bms_update._t("Update von {alt} auf {neu} jetzt einspielen? [j/N] ", alt="1.0.0", neu="1.1.0") \
        == "Install the update from 1.0.0 to 1.1.0 now? [y/N] "
    assert bms_update._groesse_mb(4_699_463) == "4.7"          # Dezimalpunkt statt -komma
    sprache("de")
    assert bms_update._groesse_mb(4_699_463) == "4,7"


def test_delegation_reicht_die_sprache_weiter(sprache, tmp_path, monkeypatch):
    import zipfile
    paket = tmp_path / "p.zip"
    with zipfile.ZipFile(paket, "w") as zf:
        zf.writestr("scripts/bms_update.py", "# andere Fassung\n")
    aufrufe = []

    def run(befehl, **kwargs):
        aufrufe.append(kwargs)
        return subprocess.CompletedProcess(befehl, 0)

    monkeypatch.setattr(bms_update.subprocess, "run", run)
    sprache("en")
    assert bms_update._selbstaktualisierung_pruefen(paket, False, ["--ja"]) == 0
    assert aufrufe[0]["env"]["BMS_TERMINAL_SPRACHE"] == "en"


# ── (3)/(4) Waechter ────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def baum() -> ast.Module:
    return ast.parse(QUELLE.read_text(encoding="utf-8"))


def _aufrufname(knoten: ast.Call) -> str | None:
    if isinstance(knoten.func, ast.Name):
        return knoten.func.id
    if isinstance(knoten.func, ast.Attribute):
        return knoten.func.attr
    return None


def _modul_konstanten(baum: ast.Module) -> dict[str, str]:
    werte: dict[str, str] = {}
    for knoten in baum.body:
        if isinstance(knoten, ast.Assign) and isinstance(knoten.value, ast.Constant) \
                and isinstance(knoten.value.value, str):
            for ziel in knoten.targets:
                if isinstance(ziel, ast.Name):
                    werte[ziel.id] = knoten.value.value
    return werte


def _vorlagen(baum: ast.Module) -> list[tuple[int, str]]:
    """Alle Vorlagen, die an `_t(...)` gehen: (Zeile, deutscher Text). Ein Name wird ueber die
    Modulkonstanten aufgeloest; alles andere (f-String, Berechnung) ist ein Fehler."""
    konstanten = _modul_konstanten(baum)
    gefunden: list[tuple[int, str]] = []
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Call) and _aufrufname(knoten) == "_t" and knoten.args:
            erstes = knoten.args[0]
            if isinstance(erstes, ast.Constant) and isinstance(erstes.value, str):
                gefunden.append((knoten.lineno, erstes.value))
            elif isinstance(erstes, ast.Name) and erstes.id in konstanten:
                gefunden.append((knoten.lineno, konstanten[erstes.id]))
            elif isinstance(erstes, ast.Name) and erstes.id == "deutsch":
                continue                       # der Rumpf von _t selbst
            else:
                pytest.fail(f"Zeile {knoten.lineno}: _t() braucht eine feste Zeichenkette als Vorlage")
    return gefunden


def _platzhalter(text: str) -> set[str]:
    return {feld.split("!")[0].split(":")[0] for _, feld, _, _ in string.Formatter().parse(text)
            if feld is not None}


def test_jede_vorlage_steht_im_woerterbuch(baum):
    fehlend = [(zeile, text[:60]) for zeile, text in _vorlagen(baum) if text not in bms_update._EN]
    assert not fehlend, f"Vorlagen ohne englischen Text: {fehlend}"


def test_woerterbuch_hat_keine_toten_eintraege(baum):
    benutzt = {text for _, text in _vorlagen(baum)}
    tot = [schluessel[:60] for schluessel in bms_update._EN if schluessel not in benutzt]
    assert not tot, f"Eintraege in _EN, die kein _t() benutzt: {tot}"


def test_platzhalter_stimmen_zwischen_deutsch_und_englisch_ueberein():
    for deutsch, englisch in bms_update._EN.items():
        assert _platzhalter(deutsch) == _platzhalter(englisch), deutsch[:60]
        # formatierbar: kein loses { oder }
        werte = {name: "x" for name in _platzhalter(deutsch)}
        deutsch.format(**werte)
        englisch.format(**werte)


def test_jeder_aufruf_liefert_die_vorgesehenen_platzhalter(baum):
    """Die Werte eines _t()-Aufrufs decken die Platzhalter der Vorlage genau ab."""
    konstanten = _modul_konstanten(baum)
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Call) and _aufrufname(knoten) == "_t" and knoten.args:
            erstes = knoten.args[0]
            if isinstance(erstes, ast.Name):
                if erstes.id not in konstanten:
                    continue
                text = konstanten[erstes.id]
            else:
                text = erstes.value
            uebergeben = {k.arg for k in knoten.keywords if k.arg}
            assert _platzhalter(text) == uebergeben, (knoten.lineno, text[:60])


def test_kein_englischer_text_enthaelt_deutsche_umlaute():
    for deutsch, englisch in bms_update._EN.items():
        assert not re.search(r"[äöüÄÖÜß„]", englisch), englisch[:60]
        assert "Sie " not in englisch and " Ihr " not in englisch, englisch[:60]


_DEUTSCH = re.compile(
    r"[äöüÄÖÜß]|\b(der|die|das|den|dem|nicht|und|oder|wurde|wird|Sie|Ihr|Ihre|ist|kein|keine|"
    r"bitte|Paket|Fehler|Ordner|Datenbank)\b")


def _ausserhalb_t_strings(baum: ast.Module):
    """Alle Zeichenketten des Moduls ausser Docstrings, ausser Argumenten von `_t(...)`, dem
    Woerterbuch `_EN` und den `_TEXT_*`-Konstanten (deutsche Schluessel, nur ueber `_t` benutzt)."""
    ausgenommen: set[int] = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            if knoten.body and isinstance(knoten.body[0], ast.Expr) \
                    and isinstance(knoten.body[0].value, ast.Constant):
                ausgenommen.add(id(knoten.body[0].value))
        if isinstance(knoten, ast.Call) and _aufrufname(knoten) == "_t":
            for teil in ast.walk(knoten):
                ausgenommen.add(id(teil))
        if isinstance(knoten, ast.Assign) and any(
                isinstance(z, ast.Name) and (z.id == "_EN" or z.id.startswith("_TEXT_"))
                for z in knoten.targets):
            for teil in ast.walk(knoten):
                ausgenommen.add(id(teil))
        if isinstance(knoten, ast.AnnAssign) and isinstance(knoten.target, ast.Name) \
                and knoten.target.id == "_EN":
            for teil in ast.walk(knoten):
                ausgenommen.add(id(teil))
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str) \
                and id(knoten) not in ausgenommen:
            yield knoten.lineno, knoten.value


def test_keine_deutsche_textkonstante_geht_an_t_vorbei(baum):
    verdaechtig = [(zeile, text[:60]) for zeile, text in _ausserhalb_t_strings(baum)
                   if _DEUTSCH.search(text)]
    assert not verdaechtig, f"Deutscher Wortlaut ohne _t(): {verdaechtig}"


def test_ausgabestellen_benutzen_t(baum):
    """print/input/add_argument/ArgumentParser und die Ausnahmen der Werkzeugs bekommen keinen
    festen Text und keinen f-String, sondern `_t(...)` bzw. eine Variable."""
    ausnahmen_klassen = {"Abbruch", "Fehlgeschlagen", "OnlineFehler"}
    unerlaubt: list[tuple[int, str]] = []
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Call):
            continue
        name = _aufrufname(knoten)
        if name in ("print", "input"):
            zu_pruefen = list(knoten.args)
        elif name in ("add_argument", "ArgumentParser", "_Parser"):
            zu_pruefen = [k.value for k in knoten.keywords if k.arg in ("help", "description")]
        elif name in ausnahmen_klassen:
            zu_pruefen = list(knoten.args[:1])
        else:
            continue
        for arg in zu_pruefen:
            for teil in ast.walk(arg):
                if isinstance(teil, ast.Call) and _aufrufname(teil) == "_t":
                    break
            else:
                if isinstance(arg, ast.JoinedStr):
                    woerter = "".join(w.value for w in arg.values if isinstance(w, ast.Constant))
                    if re.search(r"[A-Za-zÄÖÜäöüß]", woerter):
                        unerlaubt.append((knoten.lineno, "f-String mit Text ohne _t"))
                elif isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                        and re.search(r"[A-Za-zÄÖÜäöüß]{2}", arg.value):
                    unerlaubt.append((knoten.lineno, arg.value[:40]))
                elif isinstance(arg, ast.BinOp):
                    for teil in ast.walk(arg):
                        if isinstance(teil, ast.Constant) and isinstance(teil.value, str) \
                                and re.search(r"[A-Za-zÄÖÜäöüß]{2}", teil.value):
                            unerlaubt.append((knoten.lineno, teil.value[:40]))
    assert not unerlaubt, f"Ausgaben ohne _t(): {unerlaubt}"


def test_kein_deutscher_text_in_der_englischen_hilfe(sprache, capsys):
    """Gegenprobe zum Waechter: die ganze --help-Ausgabe auf Englisch enthaelt keinen deutschen Satz."""
    sprache("en")
    with pytest.raises(SystemExit):
        bms_update._parser().parse_args(["--help"])
    ausgabe = capsys.readouterr().out
    assert not re.search(r"[äöüÄÖÜß]|\b(Sie|nicht|und|oder|Datenbank)\b", ausgabe)
