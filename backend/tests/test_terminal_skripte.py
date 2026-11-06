"""Tests fuer die Terminal-Sprache der Starthilfen (P2-95, Paket A/B).

Regel: Steht das Betriebssystem auf Deutsch (oder BMS_TERMINAL_SPRACHE=de), bleibt jede Meldung
byte-gleich; alles andere und jeder Fehler bei der Erkennung heisst Englisch.

Geprueft werden hier `scripts/bms_wiederherstellen.py` (Erkennung, Woerterbuch, Waechter per ast)
sowie die neun Start-/Stopp-/Update-/Wiederherstellungs-Skripte (.command und .bat).

NEBENWIRKUNGEN: Skripte laufen nur dort, wo das gefahrlos geht -- immer mit HOME in einem
Wegwerf-Ordner (kein venv, also Abbruch vor jedem Start) und, bei stop.command, mit einem freien
PORT ab 19000. Nichts davon beruehrt das echte BMS auf Port 8000.
"""
from __future__ import annotations

import ast
import importlib.util
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

_PROJEKT_ROOT = Path(__file__).resolve().parent.parent.parent
_SKRIPT_ORDNER = _PROJEKT_ROOT / "scripts"
_WH_PFAD = _SKRIPT_ORDNER / "bms_wiederherstellen.py"

if str(_SKRIPT_ORDNER) not in sys.path:
    sys.path.insert(0, str(_SKRIPT_ORDNER))

COMMANDS = ["update.command", "start.command", "start_lan.command", "stop.command",
            "wiederherstellen.command"]
BATS = ["update_windows.bat", "start_windows.bat", "stop_windows.bat",
        "wiederherstellen_windows.bat"]

UMLAUT = re.compile("[äöüÄÖÜß]")
# Deutsche Woerter, die in englischem Text nichts verloren haben (Gross-/Kleinschreibung egal).
VERBOTEN_EN = re.compile(r"\b(nicht|bitte|fehler|l(ä|ae)uft|wurde|keine|sicherung|sie|und|oder|"
                         r"werden|wird)\b", re.IGNORECASE)
# Zusaetzlich fuer Meldungen ausserhalb der Sprachverzweigung (dort darf gar nichts Deutsches stehen,
# auch nicht in ASCII-Schreibweise der .bat).
VERBOTEN_ROH = re.compile(r"fehler|nicht|bitte|laeuft|l(ä|ae)uft|laufen|beende|prozess|bewerbungs|"
                          r"veraendert|ver(ä|ae)ndert|hinweis|achtung|starte|setup siehe|trotzdem|"
                          r"abgebrochen|gefunden|zum schlie", re.IGNORECASE)


def _lade_wh():
    spec = importlib.util.spec_from_file_location("bms_wh_terminal_unter_test", _WH_PFAD)
    modul = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modul
    spec.loader.exec_module(modul)
    return modul


wh = _lade_wh()


@pytest.fixture(autouse=True)
def _sprache_zuruecksetzen():
    wh._terminal_sprache.cache_clear()
    yield
    wh._terminal_sprache.cache_clear()


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 1. bms_wiederherstellen.py
# ═══════════════════════════════════════════════════════════════════════════════════════════
def _sprache(monkeypatch, **env):
    for name in ("BMS_TERMINAL_SPRACHE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)
    for name, wert in env.items():
        monkeypatch.setenv(name, wert)
    wh._terminal_sprache.cache_clear()
    return wh._terminal_sprache()


@pytest.mark.parametrize("wert,erwartet", [
    ("de", "de"), ("DE", "de"), ("de-DE", "de"), ("en", "en"), ("fr", "en"), ("xx", "en")])
def test_erkennung_umgebungsvariable_gewinnt(monkeypatch, wert, erwartet):
    # Die Variable gewinnt vor jedem Systemwert (hier: ein Systemwert mit der Gegenspache).
    gegen = "en_US.UTF-8" if erwartet == "de" else "de_DE.UTF-8"
    monkeypatch.setattr(wh.sys, "platform", "linux")
    assert _sprache(monkeypatch, BMS_TERMINAL_SPRACHE=wert, LANG=gegen) == erwartet


@pytest.mark.parametrize("env,erwartet", [
    ({"LANG": "de_DE.UTF-8"}, "de"),
    ({"LANG": "en_US.UTF-8"}, "en"),
    ({"LANG": "C"}, "en"),
    ({"LC_ALL": "de_AT.UTF-8", "LANG": "en_US.UTF-8"}, "de"),     # LC_ALL vor LANG
    ({"LC_ALL": "en_GB.UTF-8", "LANG": "de_DE.UTF-8"}, "en"),
    ({"LC_MESSAGES": "de_CH", "LANG": "en_US.UTF-8"}, "de"),      # LC_MESSAGES vor LANG
    ({}, "en"),                                                    # nichts bekannt: Englisch
])
def test_erkennung_locale_variablen(monkeypatch, env, erwartet):
    monkeypatch.setattr(wh.sys, "platform", "linux")
    assert _sprache(monkeypatch, **env) == erwartet


class _Lauf:
    def __init__(self, stdout):
        self.stdout = stdout


def _defaults_stub(monkeypatch, antworten):
    """Ersetzt subprocess.run im Werkzeug: `antworten` bildet AppleLanguages/AppleLocale auf
    stdout ab, eine Exception-Instanz wird geworfen."""
    def run(befehl, **kwargs):
        wert = antworten.get(befehl[-1], "")
        if isinstance(wert, Exception):
            raise wert
        return _Lauf(wert)
    monkeypatch.setattr(wh.subprocess, "run", run)


@pytest.mark.parametrize("sprachen,erwartet", [
    ('(\n    "de-DE",\n    "en-US"\n)\n', "de"),
    ('(\n    "en-GB",\n    "de-DE"\n)\n', "en"),                    # nur der erste Eintrag zaehlt
    ('(\n    "fr-FR"\n)\n', "en"),
    ('(\n    de\n)\n', "de"),
])
def test_erkennung_macos_apple_languages(monkeypatch, sprachen, erwartet):
    monkeypatch.setattr(wh.sys, "platform", "darwin")
    _defaults_stub(monkeypatch, {"AppleLanguages": sprachen})
    assert _sprache(monkeypatch, LANG="de_DE" if erwartet == "en" else "en_US") == erwartet


def test_erkennung_macos_faellt_auf_apple_locale_dann_env(monkeypatch):
    monkeypatch.setattr(wh.sys, "platform", "darwin")
    _defaults_stub(monkeypatch, {"AppleLanguages": "", "AppleLocale": "de_DE\n"})
    assert _sprache(monkeypatch, LANG="en_US") == "de"
    _defaults_stub(monkeypatch, {"AppleLanguages": OSError("kein defaults"),
                                 "AppleLocale": OSError("kein defaults")})
    assert _sprache(monkeypatch, LANG="de_DE.UTF-8") == "de"
    assert _sprache(monkeypatch) == "en"


def test_erkennung_windows_ui_sprache_und_fehler(monkeypatch):
    monkeypatch.setattr(wh.sys, "platform", "win32")
    monkeypatch.setattr(wh, "_sprache_windows", lambda: "de")
    assert _sprache(monkeypatch, LANG="en_US") == "de"
    monkeypatch.setattr(wh, "_sprache_windows", lambda: "en")
    assert _sprache(monkeypatch, LANG="de_DE") == "en"

    def kaputt():
        raise OSError("ctypes fehlt")
    monkeypatch.setattr(wh, "_sprache_windows", kaputt)
    assert _sprache(monkeypatch) == "en"                           # jeder Fehler: Englisch
    assert _sprache(monkeypatch, LANG="de_DE") == "en"             # auch mit deutscher Locale


def test_erkennung_zwischenspeicher(monkeypatch):
    monkeypatch.setattr(wh.sys, "platform", "linux")
    assert _sprache(monkeypatch, BMS_TERMINAL_SPRACHE="de") == "de"
    monkeypatch.setenv("BMS_TERMINAL_SPRACHE", "en")
    assert wh._terminal_sprache() == "de"                          # gemerkt
    wh._terminal_sprache.cache_clear()
    assert wh._terminal_sprache() == "en"


def test_t_deutsch_ist_der_schluessel_englisch_aus_dem_woerterbuch(monkeypatch):
    _sprache(monkeypatch, BMS_TERMINAL_SPRACHE="de")
    assert wh._t("Nummer der Sicherung (Enter = abbrechen): ") == "Nummer der Sicherung (Enter = abbrechen): "
    assert wh._t("Bitte eine Zahl zwischen 1 und {max} eingeben.", max=3) == \
        "Bitte eine Zahl zwischen 1 und 3 eingeben."
    _sprache(monkeypatch, BMS_TERMINAL_SPRACHE="en")
    assert wh._t("Bitte eine Zahl zwischen 1 und {max} eingeben.", max=3) == \
        "Please enter a number between 1 and 3."
    # Unbekannter Schluessel: nicht abstuerzen, deutschen Text durchreichen.
    assert wh._t("kein Eintrag {x}", x=1) == "kein Eintrag 1"


def _ast():
    return ast.parse(_WH_PFAD.read_text(encoding="utf-8"))


def _t_aufrufe(baum):
    return [n for n in ast.walk(baum)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_t"]


def _modulkonstanten(baum) -> dict[str, str]:
    werte = {}
    for n in baum.body:
        if (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)):
            werte[n.targets[0].id] = n.value.value
    return werte


def _platzhalter(text: str) -> list[str]:
    return sorted(re.findall(r"\{(\w+)(?:[:!][^}]*)?\}", text)) + sorted(re.findall(r"%[a-zA-Z]", text))


def test_waechter_jeder_t_aufruf_hat_woerterbucheintrag_und_umgekehrt():
    baum = _ast()
    konstanten = _modulkonstanten(baum)
    benutzt: set[str] = set()
    for aufruf in _t_aufrufe(baum):
        arg = aufruf.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            schluessel = arg.value
        elif isinstance(arg, ast.Attribute) and arg.attr == "art":
            continue                                             # _t(k.art): Art-Konstanten unten
        elif isinstance(arg, ast.Name) and arg.id in konstanten:
            schluessel = konstanten[arg.id]
        else:
            pytest.fail(f"_t() mit nicht pruefbarem Argument in Zeile {aufruf.lineno}")
        assert schluessel in wh._EN, f"Zeile {aufruf.lineno}: fehlt in _EN: {schluessel!r}"
        benutzt.add(schluessel)
    benutzt |= {konstanten[n] for n in ("ART_AUTO", "ART_MANUELL", "ART_VORHER")}
    ueberzaehlig = set(wh._EN) - benutzt
    assert not ueberzaehlig, f"Eintraege in _EN ohne _t()-Aufruf: {sorted(ueberzaehlig)}"


def test_waechter_platzhalter_deutsch_und_englisch_gleich():
    for de, en in wh._EN.items():
        assert _platzhalter(de) == _platzhalter(en), f"Platzhalter weichen ab: {de!r}"
        # und die englische Fassung laesst sich mit genau diesen Werten formatieren
        werte = {name: "x" for name in _platzhalter(de) if not name.startswith("%")}
        en.format(**werte)


def test_waechter_englisch_ohne_deutsche_woerter_und_umlaute():
    for de, en in wh._EN.items():
        assert not UMLAUT.search(en), f"Umlaut im englischen Text: {en!r}"
        treffer = VERBOTEN_EN.search(en)
        assert not treffer, f"Deutsches Wort {treffer.group(0)!r} im englischen Text: {en!r}"
        assert en != de or not re.search(r"[A-Za-z]{4,}", en) or de.startswith("%"), \
            f"Englischer Text fehlt: {de!r}"


def test_waechter_kein_deutscher_text_ausserhalb_von_t():
    """Jede Stringkonstante im Code, die nicht (a) das erste Argument eines _t(), (b) ein
    Woerterbuch-Eintrag oder (c) ein Docstring ist, darf nichts Deutsches enthalten."""
    baum = _ast()
    erlaubt: set[int] = set()
    for aufruf in _t_aufrufe(baum):
        for knoten in ast.walk(aufruf.args[0]):
            erlaubt.add(id(knoten))
    for n in ast.walk(baum):
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_EN"
                                             for t in n.targets):
            erlaubt.update(id(k) for k in ast.walk(n))
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            doc = n.body[0] if n.body else None
            if isinstance(doc, ast.Expr) and isinstance(doc.value, ast.Constant):
                erlaubt.add(id(doc.value))
    # Die Art-Konstanten sind deutsche Schluessel (werden vor der Ausgabe uebersetzt).
    for n in baum.body:
        if (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                and n.targets[0].id in ("ART_AUTO", "ART_MANUELL", "ART_VORHER")):
            erlaubt.update(id(k) for k in ast.walk(n))
    verdaechtig = []
    for n in ast.walk(baum):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in erlaubt:
            if UMLAUT.search(n.value) or re.search(
                    r"\b(nicht|Bitte|Fehler|Sicherung|wurde|keine|Datenbank|und|Sie)\b", n.value):
                verdaechtig.append((n.lineno, n.value))
    assert not verdaechtig, f"Deutscher Text an _t() vorbei: {verdaechtig}"


def test_englisch_liste_und_fehlermeldungen_ohne_deutsch(tmp_path, monkeypatch, capsys):
    _sprache(monkeypatch, BMS_TERMINAL_SPRACHE="en")
    monkeypatch.delenv("BMS_DATA_DIR", raising=False)
    monkeypatch.setattr(wh.bms_update, "_server_laeuft", lambda port=None: False)

    # ohne Datenordner
    assert wh.main(["--installation", str(tmp_path)]) == 1
    aus = capsys.readouterr().out
    assert "No data folder has been found yet." in aus

    # Liste mit einer manuellen Sicherung und ein falscher Dateiname
    backups = tmp_path / "data" / "backups"
    backups.mkdir(parents=True)
    (backups / "bewerbung_backup_20261005_101500.sqlite").write_bytes(b"x" * 10)
    assert wh.main(["--installation", str(tmp_path), "--liste"]) == 0
    aus = capsys.readouterr().out
    assert "Available backups (newest first):" in aus
    assert "05/10/2026 10:15" in aus and "manual backup" in aus
    assert wh.main(["--installation", str(tmp_path), "--datei", "gibt_es_nicht.sqlite"]) == 1
    aus = capsys.readouterr().out
    assert "was not found" in aus
    assert not UMLAUT.search(aus) and not VERBOTEN_EN.search(aus), aus


def test_deutsch_liste_wie_bisher(tmp_path, monkeypatch, capsys):
    _sprache(monkeypatch, BMS_TERMINAL_SPRACHE="de")
    monkeypatch.delenv("BMS_DATA_DIR", raising=False)
    monkeypatch.setattr(wh.bms_update, "_server_laeuft", lambda port=None: False)
    backups = tmp_path / "data" / "backups"
    backups.mkdir(parents=True)
    (backups / "bewerbung_backup_20261005_101500.sqlite").write_bytes(b"x" * 10)
    assert wh.main(["--installation", str(tmp_path), "--liste"]) == 0
    aus = capsys.readouterr().out
    assert aus.startswith("Verfügbare Sicherungen (neueste zuerst):\n")
    assert "05.10.2026 10:15  manuelle Sicherung" in aus


def test_englisch_argparse_hilfe_ohne_deutsch(monkeypatch):
    _sprache(monkeypatch, BMS_TERMINAL_SPRACHE="en")
    hilfe = wh._parser().format_help()
    assert "Restores a backup of the BMS database" in hilfe
    assert "Program folder of the installation." in hilfe
    assert not UMLAUT.search(hilfe)


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 2. .command (zsh)
# ═══════════════════════════════════════════════════════════════════════════════════════════
_ZSH_DA = (sys.platform.startswith("win") or shutil.which("zsh") is None)
nur_mit_zsh = pytest.mark.skipif(_ZSH_DA, reason="zsh nicht verfuegbar (Windows)")


def _zweige(zeilen: list[str], beginn, ende_zweig):
    """Liefert (ausserhalb, de, en) als Zeilenlisten. `beginn(zeile)`: Anfang der Verzweigung,
    `ende_zweig`: Funktion (zeile, modus) -> 'wechsel' | 'ende' | None."""
    ausserhalb, de, en = [], [], []
    modus = None
    for zeile in zeilen:
        roh = zeile.strip()
        if modus is None:
            if beginn(roh):
                modus = "de"
            else:
                ausserhalb.append(zeile)
            continue
        ereignis = ende_zweig(roh, modus)
        if ereignis == "wechsel":
            modus = "en"
        elif ereignis == "ende":
            modus = None
        else:
            (de if modus == "de" else en).append(zeile)
    assert modus is None, "Sprachverzweigung nicht geschlossen"
    return ausserhalb, de, en


def _command_zweige(name):
    text = (_PROJEKT_ROOT / name).read_text(encoding="utf-8")
    return _zweige(
        text.splitlines(),
        lambda z: z.startswith('if [ "$BMS_TERMINAL_SPRACHE" = de ]; then'),
        lambda z, m: "wechsel" if (z == "else" and m == "de") else ("ende" if z == "fi" else None))


def _meldungszeilen(zeilen):
    return [z for z in zeilen if re.match(r"\s*(echo|printf)\b", z)]


@nur_mit_zsh
@pytest.mark.parametrize("name", COMMANDS)
def test_command_syntax_ok(name):
    erg = subprocess.run(["zsh", "-n", str(_PROJEKT_ROOT / name)], capture_output=True, text=True)
    assert erg.returncode == 0, erg.stderr


@pytest.mark.parametrize("name", COMMANDS)
def test_command_hat_sprachbestimmung_und_export(name):
    text = (_PROJEKT_ROOT / name).read_text(encoding="utf-8")
    assert "defaults read -g AppleLanguages" in text and "defaults read -g AppleLocale" in text
    assert "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}" in text
    assert "export BMS_TERMINAL_SPRACHE" in text
    assert "\r" not in text


@pytest.mark.parametrize("name", COMMANDS)
def test_command_englischer_zweig_ohne_deutsch(name):
    ausserhalb, de, en = _command_zweige(name)
    assert en, "kein englischer Zweig"
    assert len(_meldungszeilen(de)) == len(_meldungszeilen(en)), "Zweige nicht paarweise"
    for z in en:
        assert not UMLAUT.search(z), z
        assert not VERBOTEN_EN.search(z), z
    # Ausserhalb der Verzweigung steht keine deutsche Meldung.
    for z in _meldungszeilen(ausserhalb):
        assert not UMLAUT.search(z) and not VERBOTEN_ROH.search(z), z
    # In den Zweigen steht nur Ausgabe, kein Ablauf (kein exit/return/read dazwischen).
    for z in de + en:
        assert re.match(r"\s*(echo|printf)\b", z), f"Ablauf im Sprachzweig: {z!r}"


def _env(tmp_path, **extra):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("BMS_") and k not in ("LC_ALL", "LC_MESSAGES", "LANG", "PORT", "HOST")}
    env["HOME"] = str(tmp_path / "home")
    (tmp_path / "home").mkdir(exist_ok=True)
    env.update(extra)
    return env


def _lauf(name, tmp_path, *args, **env):
    return subprocess.run(["zsh", str(_PROJEKT_ROOT / name), *args], capture_output=True, text=True,
                          env=_env(tmp_path, **env), cwd=tmp_path, timeout=60, stdin=subprocess.DEVNULL)


@nur_mit_zsh
@pytest.mark.parametrize("name,englisch,deutsch", [
    ("start.command", "Error: venv not found at", "Fehler: venv nicht gefunden unter"),
    ("start_lan.command", "Error: venv not found at", "Fehler: venv nicht gefunden unter"),
    ("update.command", "Error: The Python environment was not found at",
     "Fehler: Die Python-Umgebung wurde nicht gefunden unter"),
    ("wiederherstellen.command", "Error: The Python environment was not found at",
     "Fehler: Die Python-Umgebung wurde nicht gefunden unter"),
])
def test_command_ohne_venv_zeigt_meldung_in_der_sprache(tmp_path, name, englisch, deutsch):
    # HOME im Wegwerf-Ordner: kein venv, das Skript bricht vor jedem Start ab.
    erg = _lauf(name, tmp_path, BMS_TERMINAL_SPRACHE="en")
    assert erg.returncode == 1, erg.stderr
    assert englisch in erg.stdout and not UMLAUT.search(erg.stdout) and not VERBOTEN_EN.search(erg.stdout)
    erg = _lauf(name, tmp_path, BMS_TERMINAL_SPRACHE="de")
    assert erg.returncode == 1
    assert deutsch in erg.stdout


@nur_mit_zsh
def test_command_deutsch_nennt_readme_de_englisch_readme_und_install_en(tmp_path):
    assert "Setup siehe README.de.md." in _lauf("start.command", tmp_path, BMS_TERMINAL_SPRACHE="de").stdout
    assert "Setup: see README.md." in _lauf("start.command", tmp_path, BMS_TERMINAL_SPRACHE="en").stdout
    assert "BMS_Install_MAC.en.md" in _lauf("update.command", tmp_path, BMS_TERMINAL_SPRACHE="en").stdout
    assert "BMS_Install_MAC.md" in _lauf("update.command", tmp_path, BMS_TERMINAL_SPRACHE="de").stdout


def _defaults_attrappe(tmp_path, sprachen: str, locale: str = "") -> str:
    """Ein falsches `defaults` vorne im PATH, damit die Erkennung nicht die echte Systemsprache
    liest. Gibt den PATH zurueck."""
    ordner = tmp_path / "fakebin"
    ordner.mkdir(exist_ok=True)
    skript = ordner / "defaults"
    skript.write_text(
        "#!/bin/sh\n"
        'case "$3" in\n'
        f"  AppleLanguages) printf '%s' '{sprachen}'; [ -n '{sprachen}' ] || exit 1 ;;\n"
        f"  AppleLocale) printf '%s' '{locale}'; [ -n '{locale}' ] || exit 1 ;;\n"
        "esac\n", encoding="utf-8")
    skript.chmod(0o755)
    return f"{ordner}:/usr/bin:/bin"


@nur_mit_zsh
@pytest.mark.parametrize("sprachen,locale,lang,erwartet", [
    ('(\n    "de-DE",\n    "en-US"\n)\n', "", "", "Fehler: venv nicht gefunden"),
    ('(\n    "en-US",\n    "de-DE"\n)\n', "", "de_DE.UTF-8", "Error: venv not found"),   # erster Eintrag
    ("", "de_DE", "en_US.UTF-8", "Fehler: venv nicht gefunden"),                       # AppleLocale
    ("", "", "de_DE.UTF-8", "Fehler: venv nicht gefunden"),                            # LANG
    ("", "", "", "Error: venv not found"),                                             # nichts: Englisch
])
def test_command_erkennung_ohne_variable(tmp_path, sprachen, locale, lang, erwartet):
    path = _defaults_attrappe(tmp_path, sprachen, locale)
    extra = {"PATH": path}
    if lang:
        extra["LANG"] = lang
    erg = _lauf("start.command", tmp_path, **extra)
    assert erwartet in erg.stdout, (erg.stdout, erg.stderr)


@nur_mit_zsh
def test_command_stop_ohne_lauschenden_server(tmp_path):
    # Freien Port ab 19000 suchen; nichts lauscht dort, stop.command meldet das und endet mit 0.
    port = None
    for kandidat in range(19000, 19200):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", kandidat))
            except OSError:
                continue
            port = kandidat
            break
    assert port, "kein freier Port"
    erg = _lauf("stop.command", tmp_path, BMS_TERMINAL_SPRACHE="en", PORT=str(port))
    assert erg.returncode == 0, erg.stderr
    assert f"Nothing is running on port {port} — BMS has already stopped." in erg.stdout
    erg = _lauf("stop.command", tmp_path, BMS_TERMINAL_SPRACHE="de", PORT=str(port))
    assert erg.returncode == 0
    assert f"Auf Port {port} läuft nichts — das Bewerbungs-Management ist bereits beendet." in erg.stdout


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 3. .bat (nur Textpruefung -- Windows ist hier nicht ausfuehrbar)
# ═══════════════════════════════════════════════════════════════════════════════════════════
def _bat_zweige(name):
    daten = (_PROJEKT_ROOT / name).read_bytes().decode("utf-8")
    return _zweige(
        daten.split("\r\n"),
        lambda z: z == 'if "%BMS_TERMINAL_SPRACHE%"=="de" (',
        lambda z, m: "wechsel" if (z == ") else (" and m == "de") else ("ende" if z == ")" else None))


@pytest.mark.parametrize("name", BATS)
def test_bat_crlf_und_ascii(name):
    daten = (_PROJEKT_ROOT / name).read_bytes()
    assert daten.endswith(b"\r\n")
    assert b"\n" not in daten.replace(b"\r\n", b""), "Zeilenende ohne CR"
    assert b"\r" not in daten.replace(b"\r\n", b""), "CR ohne LF"
    for nr, zeile in enumerate(daten.decode("utf-8").split("\r\n"), start=1):
        if zeile.isascii():
            continue
        # Nicht-ASCII bestand schon vorher in Kommentaren (Trennlinien in stop_windows.bat); in
        # Befehlen und Meldungen darf nichts Nicht-ASCII stehen.
        assert zeile.lstrip().lower().startswith("rem"), f"{name}:{nr}: Nicht-ASCII ausserhalb rem"


@pytest.mark.parametrize("name", BATS)
def test_bat_hat_sprachbestimmung_mit_rueckfall_englisch(name):
    text = (_PROJEKT_ROOT / name).read_text(encoding="utf-8")
    assert ('if not defined BMS_TERMINAL_SPRACHE for /f %%L in (\'powershell -NoProfile -Command '
            '"(Get-UICulture).TwoLetterISOLanguageName" 2^>nul\') do set "BMS_TERMINAL_SPRACHE=%%L"') in text
    assert 'if not defined BMS_TERMINAL_SPRACHE set "BMS_TERMINAL_SPRACHE=en"' in text
    assert 'if /i "%BMS_TERMINAL_SPRACHE:~0,2%"=="de" (set "BMS_TERMINAL_SPRACHE=de") else' in text
    # Die Bestimmung kommt vor der ersten Verzweigung und vor dem Ablauf (cd / venv-Pruefung).
    erste_verzweigung = text.index('if "%BMS_TERMINAL_SPRACHE%"=="de" (')
    assert text.index("if not defined BMS_TERMINAL_SPRACHE") < erste_verzweigung
    ablauf = [text.index(m) for m in ("if not exist", 'set "PORT=') if m in text]
    assert ablauf and text.index("if not defined BMS_TERMINAL_SPRACHE") < min(ablauf)


@pytest.mark.parametrize("name", BATS)
def test_bat_meldungen_nur_in_sprachzweigen_und_nichts_deutsches_im_englischen(name):
    ausserhalb, de, en = _bat_zweige(name)
    assert de and en
    assert len(de) == len(en), "Zweige nicht paarweise"
    for z in ausserhalb:
        roh = z.strip().lower()
        if roh.startswith(("echo", "set /p")):
            assert roh in ("echo.", "echo"), f"Meldung ausserhalb der Sprachverzweigung: {z!r}"
    for z in en:
        assert z.isascii(), z
        assert not VERBOTEN_EN.search(z), z
        assert "!" not in z.replace("!WEITER!", ""), f"Ausrufezeichen bei delayed expansion: {z!r}"
    for z in de + en:
        roh = z.strip().lower()
        # In den Zweigen steht nur Ausgabe/Eingabeaufforderung -- kein Ablauf.
        assert roh.startswith(("echo", "set /p")), f"Ablauf im Sprachzweig: {z!r}"
        if roh.startswith("echo"):
            # Klammern in einem echo im Block muessen mit ^ maskiert sein, sonst schliessen
            # sie den Block.
            ohne = z.replace("^(", "").replace("^)", "")
            assert "(" not in ohne and ")" not in ohne, f"unmaskierte Klammer: {z!r}"


def test_bat_englisch_nennt_englische_dateien():
    for name, datei in (("update_windows.bat", "BMS_Install_Windows.en.md"),
                        ("wiederherstellen_windows.bat", "BMS_Install_Windows.en.md"),
                        ("start_windows.bat", "docs\\en\\SETUP-WINDOWS.md")):
        _, de, en = _bat_zweige(name)
        assert any(datei in z for z in en), (name, datei)
        assert not any(".en.md" in z or "\\en\\" in z for z in de)


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh fehlt")
@pytest.mark.parametrize("skript", ["scripts/refresh_views.sh", "scripts/coach_site.sh", "scripts/coach_deploy.sh"])
def test_lokale_schritte_haben_keine_einsprachigen_meldungen(skript):
    """Diese Skripte laufen als lokale Schritte. Ihre Ausgabe erscheint im Task-Center, Meldungen gehen über `_m`."""
    text = (_PROJEKT_ROOT / skript).read_text(encoding="utf-8")
    assert subprocess.run(["zsh", "-n", str(_PROJEKT_ROOT / skript)]).returncode == 0
    assert not re.findall(r"^\s*echo\b", text, re.M)


def test_lokaler_schritt_meldet_sich_in_der_vorgegebenen_sprache(tmp_path):
    """Der Runner gibt die Sprache vor, ein leeres PATH-`defaults` darf den Lauf nicht abbrechen (`set -e`)."""
    if shutil.which("zsh") is None:
        pytest.skip("zsh fehlt")
    text = (_PROJEKT_ROOT / "scripts/coach_deploy.sh").read_text(encoding="utf-8")
    kopf = text[text.index("# P2-95"):text.index("_m() {")] + text[text.index("_m() {"):].split("\n", 1)[0] + "\n"
    probe = tmp_path / "probe.sh"
    probe.write_text("#!/bin/zsh\nset -euo pipefail\n" + kopf + '_m "Deutsch" "English"\n', encoding="utf-8")
    for vorgabe, erwartet in (("de", "Deutsch"), ("en", "English")):
        umgebung = {"PATH": "/usr/bin:/bin", "BMS_TERMINAL_SPRACHE": vorgabe}
        lauf = subprocess.run(["zsh", str(probe)], env=umgebung, capture_output=True, text=True)
        assert (lauf.returncode, lauf.stdout.strip()) == (0, erwartet)
    leer = tmp_path / "bin"
    leer.mkdir()
    (leer / "defaults").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (leer / "defaults").chmod(0o755)
    lauf = subprocess.run(["zsh", str(probe)], env={"PATH": f"{leer}:/usr/bin:/bin", "LANG": "de_DE.UTF-8"},
                          capture_output=True, text=True)
    assert (lauf.returncode, lauf.stdout.strip()) == (0, "Deutsch")
