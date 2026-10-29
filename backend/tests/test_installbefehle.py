"""Tests für die beiden Installationsanleitungen (P2-71, überarbeitet in P2-82, Paket I).

`BMS_Install_MAC.md` und `BMS_Install_Windows.md` sind Anweisungen an Claude. Sie enthalten fertige
Befehle, die das Programmpaket aus den GitHub-Releases des BMS laden (Auskunft über die GitHub-API,
Download des Release-Assets, Prüfsumme). Ein Tippfehler darin fällt erst beim Anwender auf. Dieses
Modul prüft deshalb vier Dinge:

  1. AUFBAU: Die Überschriften der Ebenen `#` und `##` stehen wörtlich und in der Reihenfolge aus
     „Gemeinsamer Aufbau“ (P2-71, Vertrag D; seit P2-82 mit Schritt 0 bis Schritt 10) in beiden
     Dateien, „Was unter Windows eingeschränkt ist“ nur in der Windows-Datei.
  2. ALTE NAMEN: `BMS_Install.md` und `BMS_Install_Auto.md` gibt es nicht mehr, und kein
     ausgeliefertes Dokument nennt sie. `CHANGELOG.md` ist ausgenommen: Der Eintrag zu den neuen
     Anleitungen und die Einträge früherer Versionen nennen sie absichtlich.
  3. KEIN PAKETDIENST, KEINE LIZENZ: In den Anleitungen steht keine Adresse des früheren Paketdienstes
     und kein Wort zu Lizenzdatei, Testlizenz oder Ansichtsmodus (P2-82, Vertrag I).
  4. BEFEHLE: Die Blöcke zu Auskunft, Laden und Prüfsumme stehen je Datei genau einmal darin und
     sind zeichengleich mit den Blöcken in der Spec (`tasks/spec_p2-82_lizenz_raus_update_github.md`,
     nicht im Kundenpaket: fehlt sie, entfällt nur dieser Vergleich). Dieselben Blöcke werden
     WÖRTLICH ausgeführt, gegen einen Probeserver auf 127.0.0.1, der die zwei GitHub-Adressen spielt:
     sh und zsh unter macOS/Linux, Windows PowerShell 5.1 unter Windows. Dazu die Befehle für den
     Fehlerfall (Datei fehlt auf GitHub, Prüfsumme weicht ab).

Aufbau und Befehle werden zeilenweise aus dem Markdown geholt: Eine Zeile, die nach der Einrückung
mit ``` beginnt, öffnet oder schließt einen Codeblock. Ein regulärer Ausdruck über den ganzen
Text scheitert, weil im Fließtext der Anleitungen an einer Stelle drei Backticks in einer Zeile
stehen. Zeilen mit `#` innerhalb von Codeblocks sind keine Überschriften.

Wo die Anleitungen liegen, sagt die Fixture `projekt_root` (Vorgabe: das Projekt). Eine Gegenprobe
überschreibt sie in einem Wrapper-Modul und lässt dieselben Tests gegen eine verfälschte Kopie
laufen. Die Selbsttests am Ende prüfen, dass die Prüfungen anschlagen.

KEIN TEST SPRICHT GITHUB ODER SONST EINE ADRESSE IM NETZ AN: Der Probeserver lauscht nur auf
127.0.0.1. Vor jedem Lauf werden `https://api.github.com` und `https://github.com` im Befehl durch
seine Adresse ersetzt und geprüft, dass keine echte Adresse übrig ist. Die Antworten des Probeservers
folgen der echten GitHub-API (gegengeprüft am 29.10.2026: `tag_name`, `html_url`, je Asset `name`,
`size`, `digest`, `browser_download_url`; der Download antwortet in Wirklichkeit mit einer Umleitung).

DER POWERSHELL-TEIL läuft nur unter Windows und wurde bei der Entstehung dieser Fassung nicht
ausgeführt (kein Windows auf dem Entwicklungsrechner): Er läuft zum ersten Mal im CI-Job
`backend-windows`.

App-Module nur funktionslokal importieren (s. conftest.py); sonst braucht die Datei nur die
Standardbibliothek.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_PFAD = PROJECT_ROOT / "tasks" / "spec_p2-82_lizenz_raus_update_github.md"

DATEIEN = {"mac": "BMS_Install_MAC.md", "windows": "BMS_Install_Windows.md"}
ALTE_DATEIEN = ("BMS_Install.md", "BMS_Install_Auto.md")
SPRACHE = {"mac": "sh", "windows": "powershell"}

# Repo und Adressen, wie sie in den Befehlen stehen. Die zwei Adressen ersetzt der Test durch den Probeserver.
GITHUB_REPO = "holgerdaube/BewerbungsMgmtSystem"
API_ADRESSE = "https://api.github.com"
GITHUB_ADRESSE = "https://github.com"
# Nach dem Ersetzen darf in keinem Befehl ein Hinweis auf diese Hosts übrig sein.
ECHTE_HOSTS = ("github.com", "githubusercontent.com", "daube.tech")


@pytest.fixture()
def projekt_root() -> Path:
    """Wo die Anleitungen und die Kundentexte liegen. Eine Gegenprobe überschreibt diese Fixture."""
    return PROJECT_ROOT


def _anleitung(root: Path, system: str) -> str:
    return (root / DATEIEN[system]).read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════════════════
# Markdown zeilenweise zerlegen
# ═══════════════════════════════════════════════════════════════════════════════════════════
# Zaun: Einrückung, mindestens drei Backticks, danach höchstens eine Sprachangabe.
_ZAUN_RE = re.compile(r"^(\s*)(`{3,})\s*([^\s`]*)")


@dataclass(frozen=True)
class Block:
    sprache: str
    text: str       # ohne die Einrückung des Zauns, ohne Zeilenende am Schluss
    zeile: int      # Zeile des öffnenden Zauns, 1-basiert


def _zerlegen(text: str) -> tuple[list[tuple[int, str]], list[Block]]:
    """(Fließtext-Zeilen mit Zeilennummer, Codeblöcke). Eine Zeile, die nach der Einrückung mit
    ``` beginnt, öffnet einen Block; er endet an der nächsten Zeile, die nur aus mindestens
    ebenso vielen Backticks besteht. Ein nie geschlossener Block ist ein Fehler der Datei."""
    prosa: list[tuple[int, str]] = []
    bloecke: list[Block] = []
    offen: tuple[str, int, str, int, list[str]] | None = None
    for nr, zeile in enumerate(text.splitlines(), 1):
        if offen is None:
            treffer = _ZAUN_RE.match(zeile)
            if treffer:
                offen = (treffer.group(1), len(treffer.group(2)), treffer.group(3).lower(), nr, [])
            else:
                prosa.append((nr, zeile))
            continue
        einzug, laenge, sprache, start, inhalt = offen
        nackt = zeile.strip()
        if nackt and set(nackt) == {"`"} and len(nackt) >= laenge:
            bloecke.append(Block(sprache, "\n".join(inhalt), start))
            offen = None
        else:
            inhalt.append(zeile[len(einzug):] if zeile.startswith(einzug) else zeile.lstrip())
    if offen is not None:
        raise AssertionError(f"Der Codeblock ab Zeile {offen[3]} wird nie geschlossen")
    return prosa, bloecke


def _ueberschriften(text: str) -> list[str]:
    """Die Überschriften der Ebenen `#` und `##` außerhalb von Codeblöcken, in Reihenfolge."""
    prosa, _ = _zerlegen(text)
    return [zeile.rstrip() for _, zeile in prosa if re.match(r"^#{1,2} \S", zeile)]


def _fliesstext(text: str) -> str:
    """Der Text außerhalb der Codeblöcke, Zeilenumbrüche und Mehrfach-Leerraum zu einem Leerzeichen."""
    prosa, _ = _zerlegen(text)
    return re.sub(r"\s+", " ", " ".join(zeile for _, zeile in prosa))


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 1 — Aufbau
# ═══════════════════════════════════════════════════════════════════════════════════════════
SCHRITTE = 11       # „## Schritt 0: …“ bis „## Schritt 10: …“ (P2-82: Schritt „Lizenz einspielen“ entfällt)


def _soll_ueberschriften(system: str) -> list[tuple[str, bool]]:
    """„Gemeinsamer Aufbau“ der Spec (P2-71 Vertrag D, mit elf Schritten seit P2-82):
    (Text, nur-Anfang). Bei den Schritten zählt nur der Anfang `## Schritt N:`, der Titel danach ist
    je System frei."""
    windows = system == "windows"
    soll = [(f"# BMS: Installation und Einrichtung unter {'Windows' if windows else 'macOS'}", False),
            ("## So starten Sie", False),
            ("## Was Sie brauchen", False),
            ("# Anweisung an Claude: geführte Installation", False),
            ("## Gesprächsregeln", False)]
    soll += [(f"## Schritt {n}:", True) for n in range(SCHRITTE)]
    soll += [("# Nach der Installation", False),
             ("## Einrichten: Das BMS lernt Sie kennen", False),
             ("## Kurz prüfen, ob alles sitzt", False),
             ("## Aktualisierungen einspielen", False),
             ("## Wenn etwas nicht klappt", False)]
    if windows:
        soll.append(("## Was unter Windows eingeschränkt ist", False))
    soll += [("## Ihre Daten", False), ("## Hilfe", False)]
    return soll


def _passt(soll: tuple[str, bool], gefunden: str) -> bool:
    text, nur_anfang = soll
    return gefunden.startswith(text) if nur_anfang else gefunden == text


def _aufbau_probleme(text: str, system: str) -> list[str]:
    """Was am Aufbau nicht stimmt, leer wenn alles stimmt."""
    soll = _soll_ueberschriften(system)
    gefunden = _ueberschriften(text)
    probleme = [f"fehlt: {s[0]}{' …' if s[1] else ''}" for s in soll
                if not any(_passt(s, g) for g in gefunden)]
    probleme += [f"unerwartet: {g}" for g in gefunden if not any(_passt(s, g) for s in soll)]
    if not probleme:
        if len(gefunden) != len(soll):
            probleme.append(f"Anzahl weicht ab: {len(gefunden)} statt {len(soll)} Überschriften "
                            "(eine steht doppelt)")
        else:
            for stelle, (s, g) in enumerate(zip(soll, gefunden), 1):
                if not _passt(s, g):
                    probleme.append(f"Reihenfolge weicht ab ab Stelle {stelle}: "
                                    f"erwartet {s[0]!r}, gefunden {g!r}")
                    break
    return probleme


@pytest.mark.parametrize("system", ["mac", "windows"])
def test_aufbau_der_anleitung_stimmt_mit_der_spec_ueberein(projekt_root, system):
    """Ebene `#` und `##` wörtlich und in der Reihenfolge aus „Gemeinsamer Aufbau“; Schritt 0 bis
    10; „Was unter Windows eingeschränkt ist“ nur in der Windows-Datei; sonst keine weiteren."""
    probleme = _aufbau_probleme(_anleitung(projekt_root, system), system)

    assert not probleme, f"{DATEIEN[system]}:\n" + "\n".join(probleme)


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 2 — Alte Namen
# ═══════════════════════════════════════════════════════════════════════════════════════════
# `BMS_Install` allein oder mit `_Auto`, danach kein weiteres Namenszeichen: trifft `BMS_Install.md`,
# `BMS_Install_Auto.md`, `BMS_Install.html`, aber nicht `BMS_Install_MAC.md` und `_Windows.md`.
_ALTER_NAME_RE = re.compile(r"BMS_Install(?:_Auto)?(?![\w])", re.IGNORECASE)


def _alte_namen_funde(text: str) -> list[str]:
    return [f"Zeile {nr}: {m.group(0)!r} in {zeile.strip()[:100]!r}"
            for nr, zeile in enumerate(text.splitlines(), 1) for m in _ALTER_NAME_RE.finditer(zeile)]


def _ausgelieferte_dokumente() -> list[str]:
    """Die Liste der Kundentexte wie in `test_kundendoku.py` (Positivliste für `docs/` plus die
    Dokumente im Paket-Root), dazu `README.md`. OHNE `CHANGELOG.md`: Er nennt die alten Namen in
    den Einträgen früherer Versionen und im neuen Eintrag absichtlich."""
    from pipeline import kundenpaket as kp
    return (sorted(f"docs/{name}.md" for name in kp.DOKU_ERLAUBT)
            + list(DATEIEN.values()) + ["README.md"])


def test_alte_anleitungen_gibt_es_nicht_mehr(projekt_root):
    vorhanden = [name for name in ALTE_DATEIEN if (projekt_root / name).exists()]

    assert not vorhanden, f"Die früheren Anleitungen sind ersetzt und dürfen nicht mehr existieren: {vorhanden}"
    for name in DATEIEN.values():
        assert (projekt_root / name).is_file(), f"{name} fehlt"


def test_kein_ausgeliefertes_dokument_nennt_die_alten_namen(projekt_root):
    assert "CHANGELOG.md" not in _ausgelieferte_dokumente()
    funde = []
    for rel in _ausgelieferte_dokumente():
        text = (projekt_root / rel).read_text(encoding="utf-8")
        funde += [f"{rel} {f}" for f in _alte_namen_funde(text)]

    assert not funde, "Alte Anleitungsnamen in ausgelieferten Dokumenten:\n" + "\n".join(funde)


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 3 — Kein Paketdienst, keine Lizenz (P2-82)
# ═══════════════════════════════════════════════════════════════════════════════════════════
# Das BMS ist kostenlos (Apache-2.0). Die Anleitungen kennen weder den früheren Paketdienst noch die
# frühere Lizenzdatei. „Apache-Lizenz“ im Fließtext ist erlaubt, daher keine Suche nach „Lizenz“ allein.
_VERBOTENE_BEGRIFFE = ("daube.tech", "Lizenzdatei", "Testlizenz", "Ansichtsmodus", "LIZENZ-PFAD",
                       "/api/paket", "Kaufpreis", "Kauflizenz", "Paketdienst")


def _verbotene_funde(text: str) -> list[str]:
    return [f"Zeile {nr}: {begriff!r} in {zeile.strip()[:100]!r}"
            for nr, zeile in enumerate(text.splitlines(), 1)
            for begriff in _VERBOTENE_BEGRIFFE if begriff.lower() in zeile.lower()]


@pytest.mark.parametrize("system", ["mac", "windows"])
def test_anleitungen_kennen_weder_paketdienst_noch_lizenzdatei(projekt_root, system):
    funde = _verbotene_funde(_anleitung(projekt_root, system))

    assert not funde, f"{DATEIEN[system]}:\n" + "\n".join(funde)


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 4 — Die Befehlsblöcke
# ═══════════════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Befehle:
    """Die drei Blöcke, die Claude dem Anwender vorgibt: Auskunft holen, Paket laden, Prüfsumme."""
    auskunft: str
    laden: str
    pruefsumme: str


# Woran man den jeweiligen Block erkennt. Je Sprache und Datei muss genau ein Block passen.
_MARKER = {
    "sh": {"auskunft": "/releases/latest", "laden": "/releases/download/", "pruefsumme": "shasum"},
    "powershell": {"auskunft": "/releases/latest", "laden": "/releases/download/",
                   "pruefsumme": "Get-FileHash"},
}

MAC_FEHLERBEFEHL = 'rm -f "ZIP-PFAD"'
WINDOWS_FEHLERBEFEHLE = ('Remove-Item -ErrorAction SilentlyContinue "ZIP-PFAD"',)


def _hauptbefehle(text: str, sprache: str, quelle: str) -> Befehle:
    """Holt die drei Blöcke der Sprache `sh` bzw. `powershell` aus `text`. Fehlt einer oder gibt es
    mehrere, ist das ein Fehler (der Test ist rot, nie übersprungen)."""
    _, bloecke = _zerlegen(text)
    gefunden = {}
    for name, marker in _MARKER[sprache].items():
        passende = [b for b in bloecke if b.sprache == sprache and marker in b.text]
        if len(passende) != 1:
            raise AssertionError(
                f"{quelle}: {len(passende)} Codeblöcke ({sprache}) mit {marker!r} für {name} gefunden, "
                f"erwartet genau 1" + (f" (Zeilen {[b.zeile for b in passende]})" if passende else ""))
        gefunden[name] = passende[0].text
    return Befehle(**gefunden)


def _fehlerbefehle(text: str, system: str, quelle: str) -> tuple[str, ...]:
    """Die Befehle, mit denen die Anleitung im Fehlerfall die Datei löscht.
    macOS: ein sh-Block `rm -f "ZIP-PFAD"`. Windows: ein Befehl im Fließtext, in Backticks. Stehen
    sie nicht wörtlich da, ist das ein Fehler."""
    if system == "mac":
        passende = [b for b in _zerlegen(text)[1] if b.sprache == "sh" and b.text == MAC_FEHLERBEFEHL]
        if len(passende) != 1:
            raise AssertionError(f"{quelle}: {len(passende)} sh-Blöcke mit {MAC_FEHLERBEFEHL!r}, erwartet genau 1")
        return (MAC_FEHLERBEFEHL,)
    prosa = _fliesstext(text)
    fehlend = [b for b in WINDOWS_FEHLERBEFEHLE if f"`{b}`" not in prosa]
    if fehlend:
        raise AssertionError(f"{quelle}: Befehle nicht wörtlich im Fließtext (in Backticks): {fehlend}")
    return WINDOWS_FEHLERBEFEHLE


def _unterschiede(a: Befehle, b: Befehle) -> list[str]:
    return [name for name in ("auskunft", "laden", "pruefsumme") if getattr(a, name) != getattr(b, name)]


@pytest.mark.parametrize("system", ["mac", "windows"])
def test_die_befehlsbloecke_stehen_je_datei_genau_einmal_darin(projekt_root, system):
    """Findet der Test in einer Anleitung keinen passenden Block, ist er rot (nicht übersprungen)."""
    text = _anleitung(projekt_root, system)
    befehle = _hauptbefehle(text, SPRACHE[system], DATEIEN[system])
    _fehlerbefehle(text, system, DATEIEN[system])

    assert f'"{API_ADRESSE}/repos/{GITHUB_REPO}/releases/latest"' in befehle.auskunft
    assert '-H "Accept: application/vnd.github+json"' in befehle.auskunft
    # Laden folgt Umleitungen (-L: GitHub leitet auf seinen Download-Server um) und scheitert bei
    # einem Fehlerstatus (-f), statt die Fehlerseite als „Paket“ abzulegen.
    assert " -fsSL " in befehle.laden
    assert f'"{GITHUB_ADRESSE}/{GITHUB_REPO}/releases/download/vVERSION/BMS_VERSION.zip"' in befehle.laden
    assert "ZIP-PFAD" in befehle.laden and "ZIP-PFAD" in befehle.pruefsumme
    for block in (befehle.auskunft, befehle.laden, befehle.pruefsumme):
        assert "LIZENZ" not in block and "?" not in block, block


@pytest.mark.parametrize("system", ["mac", "windows"])
def test_die_befehlsbloecke_sind_zeichengleich_mit_der_spec(projekt_root, system):
    """Spec P2-82, Vertrag I: „Die Blöcke wörtlich so“. Die Spec liegt nicht im Kundenpaket; fehlt
    sie, entfällt nur dieser Vergleich (die Ausführung unten bleibt)."""
    if not SPEC_PFAD.is_file():
        pytest.skip(f"{SPEC_PFAD.name} liegt nicht vor (nicht im Kundenpaket)")
    spec = SPEC_PFAD.read_text(encoding="utf-8")
    sprache = SPRACHE[system]

    aus_spec = _hauptbefehle(spec, sprache, SPEC_PFAD.name)
    aus_datei = _hauptbefehle(_anleitung(projekt_root, system), sprache, DATEIEN[system])

    abweichend = _unterschiede(aus_datei, aus_spec)
    zeilen = [f"  {n}:\n    Datei {getattr(aus_datei, n)!r}\n    Spec  {getattr(aus_spec, n)!r}"
              for n in abweichend]
    assert not abweichend, f"{DATEIEN[system]}: Block weicht von der Spec ab: {abweichend}\n" + "\n".join(zeilen)
    # Auch die Fehlerfall-Befehle stehen so in der Spec (im Fließtext, in Backticks).
    gesamt = _fliesstext(spec)
    for befehl in _fehlerbefehle(_anleitung(projekt_root, system), system, DATEIEN[system]):
        assert f"`{befehl}`" in gesamt, f"{befehl!r} steht nicht in der Spec"


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 5 — Probeserver: spielt die zwei GitHub-Adressen (Auskunft und Download)
# ═══════════════════════════════════════════════════════════════════════════════════════════
VERSION = "2.0.0"

AUSKUNFT_PFAD = f"/repos/{GITHUB_REPO}/releases/latest"
DOWNLOAD_PFAD = f"/{GITHUB_REPO}/releases/download/v{VERSION}/BMS_{VERSION}.zip"
# Der echte Download antwortet mit einer Umleitung auf einen Host unter githubusercontent.com.
WEITERLEITUNG_PFAD = f"/release-assets/BMS_{VERSION}.zip"


def _paket_bauen() -> bytes:
    """Ein kleines, echtes ZIP mit Bytes über den ganzen Wertebereich (ein Fehler durch
    Textmodus oder Umkodierung fällt so in der Prüfsumme auf)."""
    puffer = BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_STORED) as zf:
        for name, inhalt in (("bms_manifest.json", b"{}\n"), ("start.command", b"#!/bin/zsh\n"),
                             ("daten.bin", bytes((i * 7 + 3) % 256 for i in range(40000)))):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 20, 0, 0, 0))
            zf.writestr(info, inhalt)
    return puffer.getvalue()


PAKET_BYTES = _paket_bauen()
PAKET_SHA256 = sha256(PAKET_BYTES).hexdigest()
# Die kleine Prüfsummen-Datei, die das Release zusätzlich enthält (nur als zweites Asset in der Auskunft).
SUMMEN_DATEI = f"{PAKET_SHA256}  BMS_{VERSION}.zip\n".encode("utf-8")


def _release() -> dict:
    """Die Auskunft von `GET /repos/{owner}/{repo}/releases/latest`, im Aufbau der echten Antwort.
    Das Asset mit der Prüfsummen-Datei steht absichtlich VOR dem ZIP: Wer „das erste Asset“ nimmt, fällt auf."""
    basis = f"https://github.com/{GITHUB_REPO}/releases"
    return {
        "url": f"https://api.github.com/repos/{GITHUB_REPO}/releases/1",
        "html_url": f"{basis}/tag/v{VERSION}",
        "tag_name": f"v{VERSION}",
        "name": f"BMS {VERSION}",
        "draft": False,
        "prerelease": False,
        "published_at": "2026-10-29T08:00:00Z",
        "assets": [
            {"name": f"BMS_{VERSION}.zip.sha256", "size": len(SUMMEN_DATEI),
             "content_type": "text/plain", "digest": f"sha256:{sha256(SUMMEN_DATEI).hexdigest()}",
             "browser_download_url": f"{basis}/download/v{VERSION}/BMS_{VERSION}.zip.sha256"},
            {"name": f"BMS_{VERSION}.zip", "size": len(PAKET_BYTES),
             "content_type": "application/zip", "digest": f"sha256:{PAKET_SHA256}",
             "browser_download_url": f"{basis}/download/v{VERSION}/BMS_{VERSION}.zip"},
        ],
        # Nur ASCII-Zeichen und Escapes: Der Test soll die Anleitung prüfen, nicht die Kodierung der Konsole.
        "body": "- Neu: Beispiel\n- Behoben: Umlaute äöüß",
    }


class _Handler(BaseHTTPRequestHandler):
    server_version = "Probe"
    sys_version = ""

    def log_message(self, *args):
        pass

    def _antworten(self, status: int, typ: str, body: bytes, kopf: dict[str, str] | None = None):
        self.send_response(status)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(body)))
        for name, wert in (kopf or {}).items():
            self.send_header(name, wert)
        self.end_headers()
        self.wfile.write(body)

    def _text(self, status: int, satz: str):
        self._antworten(status, "text/plain; charset=utf-8", (satz + "\n").encode("utf-8"))

    def _nur_get(self):
        self.server.dienst.verstoesse.append(f"{self.command} {self.path}: GitHub wird hier nur mit GET gefragt")
        self._text(405, "Method Not Allowed")

    do_POST = do_PUT = do_DELETE = do_PATCH = _nur_get

    def do_GET(self):
        dienst = self.server.dienst
        teile = urlsplit(self.path)
        dienst.aufrufe.append(teile.path)
        if teile.query:
            dienst.verstoesse.append(f"GET {self.path}: Die Adressen der Anleitung haben keinen Anfrageteil (?)")
        if teile.path == AUSKUNFT_PFAD:
            if "application/vnd.github+json" not in self.headers.get("Accept", ""):
                dienst.verstoesse.append(f"GET {teile.path}: Kopfzeile Accept: application/vnd.github+json fehlt")
            return self._antworten(200, "application/json; charset=utf-8",
                                   (json.dumps(_release(), indent=2) + "\n").encode("utf-8"))
        if teile.path == DOWNLOAD_PFAD:
            if dienst.laden == "404":
                return self._text(404, "Not Found")
            if dienst.laden == "umleitung":
                return self._antworten(302, "text/plain", b"", {"Location": WEITERLEITUNG_PFAD})
            inhalt = PAKET_BYTES[:-100] if dienst.laden == "beschaedigt" else PAKET_BYTES
            return self._antworten(200, "application/octet-stream", inhalt)
        if teile.path == WEITERLEITUNG_PFAD and dienst.laden == "umleitung":
            return self._antworten(200, "application/octet-stream", PAKET_BYTES)
        dienst.verstoesse.append(f"GET {self.path}: unbekannte Adresse")
        self._text(404, "Not Found")


class _GitHub:
    """Der Probeserver: lauscht auf 127.0.0.1 (Port 0), merkt sich Aufrufe und Verstöße (falscher Pfad,
    Anfrageteil in der Adresse, Kopfzeile Accept fehlt, andere Methode als GET).

    `laden` steuert den Download: `direkt` (200 mit dem Paket), `umleitung` (302 auf einen zweiten
    Pfad, wie die echte Adresse), `404` (Datei gibt es nicht), `beschaedigt` (200, aber 100 Byte zu wenig)."""

    def __init__(self, *, laden: str = "direkt"):
        assert laden in ("direkt", "umleitung", "404", "beschaedigt"), laden
        self.laden = laden
        self.aufrufe: list[str] = []
        self.verstoesse: list[str] = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.server.daemon_threads = True
        self.server.dienst = self
        self.server.handle_error = self._handler_fehler
        self.port = self.server.server_address[1]
        self._thread = threading.Thread(target=self.server.serve_forever,
                                        kwargs={"poll_interval": 0.02}, daemon=True)
        self._thread.start()

    def _handler_fehler(self, request, client_address):
        art = sys.exc_info()[0]
        if art is not None and issubclass(art, (ConnectionError, TimeoutError)):
            return          # der Client hat die Verbindung selbst beendet
        self.verstoesse.append(f"Fehler im Handler: {sys.exc_info()[1]!r}")

    @property
    def adresse(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def beenden(self):
        self.server.shutdown()
        self.server.server_close()
        self._thread.join(5)


@pytest.fixture()
def github():
    """Fabrik: `github()` bzw. `github(laden="404")` startet einen Probeserver. Nach dem Test werden
    alle beendet und auf Verstöße gegen das Verhalten der echten Adressen geprüft."""
    gestartet: list[_GitHub] = []

    def starten(*, laden: str = "direkt") -> _GitHub:
        dienst = _GitHub(laden=laden)
        gestartet.append(dienst)
        return dienst

    yield starten
    for dienst in gestartet:
        dienst.beenden()
    for dienst in gestartet:
        assert dienst.verstoesse == [], f"Verstöße der Befehle gegen die GitHub-Adressen im Probeserver: {dienst.verstoesse}"


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 6 — Befehle wörtlich ausführen (sh, zsh, Windows PowerShell)
# ═══════════════════════════════════════════════════════════════════════════════════════════
# Testaufbau, kein Teil der Anleitung: Damit die erfasste Ausgabe richtig kodiert ist, stellt der
# Test der Windows-PowerShell die Ausgabe auf UTF-8. In try/catch, weil das Setzen ohne angehängte
# Konsole fehlschlagen kann.
_POWERSHELL_VORSPANN = "try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }; "

AUSFUEHRUNGEN = [
    pytest.param("mac", "sh", id="mac-sh"),
    pytest.param("mac", "zsh", id="mac-zsh"),
    pytest.param("windows", "powershell", id="windows-powershell"),
]


def _shell_vorbereiten(shell: str) -> Callable[[str], list[str]]:
    """Gibt zurück, wie ein Skript aufgerufen wird. Übersprungen (mit Grund) wird nur, wenn das
    System oder ein Werkzeug fehlt; fehlende Blöcke in den Anleitungen sind vorher schon rot."""
    if shell in ("sh", "zsh"):
        if os.name != "posix":
            pytest.skip("sh-Blöcke laufen nur unter macOS/Linux (os.name == 'posix')")
        exe = "/bin/sh" if shell == "sh" else shutil.which("zsh")
        if exe is None:
            pytest.skip("zsh nicht gefunden")
        for werkzeug in ("curl", "shasum"):
            if shutil.which(werkzeug) is None:
                pytest.skip(f"{werkzeug} nicht gefunden")
        return lambda skript: [exe, "-c", skript]
    if os.name != "nt":
        pytest.skip("powershell-Blöcke laufen nur unter Windows (os.name == 'nt')")
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        pytest.skip("powershell.exe nicht gefunden")
    if shutil.which("curl.exe") is None:
        pytest.skip("curl.exe nicht gefunden")
    return lambda skript: [powershell, "-NoProfile", "-NonInteractive", "-Command",
                           _POWERSHELL_VORSPANN + skript]


@dataclass
class Ergebnis:
    code: int
    ausgabe: str
    fehler: str

    def __str__(self) -> str:
        return f"Exit {self.code}\nAusgabe: {self.ausgabe!r}\nFehlerausgabe: {self.fehler!r}"


def _dekodiert(daten: bytes) -> str:
    return daten.decode("utf-8-sig", errors="replace").replace("\r\n", "\n")


@dataclass
class Arbeitsumgebung:
    """Alles unter tmp_path, Pfade MIT Leerzeichen (wie bei echten Anwendern), Umgebung ohne Proxy
    und ohne die curl-Einstellungen des Entwicklers."""
    wurzel: Path
    dienst: _GitHub
    downloads: Path = field(init=False)
    umgebung: dict[str, str] = field(init=False)

    def __post_init__(self):
        ordner = self.wurzel / "Ordner mit Leerzeichen"
        self.downloads = ordner / "Downloads Ordner"
        self.downloads.mkdir(parents=True)
        home = self.wurzel / "home"
        home.mkdir()
        # PSModulePath nicht vererben: Der Windows-CI-Schritt läuft unter PowerShell 7 (pwsh) und
        # gibt seinen Modulpfad an den Kindprozess weiter. Windows PowerShell 5.1 findet dann das
        # Utility-Modul von PowerShell 7 statt des eigenen und kennt `Get-FileHash` nicht mehr
        # (erster CI-Lauf von P2-71: „The term 'Get-FileHash' is not recognized“). Ohne die Variable
        # baut powershell.exe seinen Vorgabepfad selbst, wie beim Anwender, der es aus dem Startmenü öffnet.
        umgebung = {k: v for k, v in os.environ.items()
                    if k.lower() not in ("http_proxy", "https_proxy", "all_proxy", "no_proxy",
                                         "curl_home", "zdotdir", "psmodulepath")}
        # Unter Windows sind Namen von Umgebungsvariablen nicht groß-/kleinschreibungsabhängig:
        # keine zwei Schreibweisen derselben Variable im Block.
        for name in (("NO_PROXY",) if os.name == "nt" else ("NO_PROXY", "no_proxy")):
            umgebung[name] = "127.0.0.1,localhost"
        umgebung.update({"CURL_HOME": str(home), "ZDOTDIR": str(home)})
        self.umgebung = umgebung

    def zip_pfad(self, version: str = VERSION) -> Path:
        return self.downloads / f"BMS_{version}.zip"

    def einsetzen(self, befehl: str, version: str = VERSION) -> str:
        """Die zwei GitHub-Adressen durch den Probeserver ersetzen, Platzhalter durch Pfade unter tmp_path."""
        werte = {"ZIP-PFAD": str(self.zip_pfad(version)), "VERSION": version}
        fertig = befehl.replace(API_ADRESSE, self.dienst.adresse).replace(GITHUB_ADRESSE, self.dienst.adresse)
        fertig = re.sub("|".join(map(re.escape, werte)), lambda t: werte[t.group(0)], fertig)
        # Sicherung: Nichts darf mehr an GitHub gehen, und kein Platzhalter darf übrig sein.
        echte = [h for h in ECHTE_HOSTS if h in fertig]
        assert not echte, f"Befehl enthält noch eine echte Adresse ({echte}): {fertig}"
        uebrig = [p for p in ("ZIP-PFAD", "VERSION") if p in fertig]
        assert not uebrig, f"Platzhalter nicht ersetzt: {uebrig}"
        return fertig

    def ausfuehren(self, aufruf: Callable[[str], list[str]], befehl: str, version: str = VERSION) -> Ergebnis:
        skript = self.einsetzen(befehl, version)
        try:
            lauf = subprocess.run(aufruf(skript), stdin=subprocess.DEVNULL, capture_output=True,
                                  env=self.umgebung, cwd=self.wurzel, timeout=90)
        except subprocess.TimeoutExpired:
            raise AssertionError(f"Zeitüberschreitung bei: {skript}") from None
        return Ergebnis(lauf.returncode, _dekodiert(lauf.stdout), _dekodiert(lauf.stderr))


def _auskunft_auswerten(ausgabe: str) -> tuple[str, str]:
    """Was Claude aus der Auskunft nimmt (Spec P2-82, Vertrag I): `tag_name` ohne `v` als Version und
    beim Asset `BMS_<Version>.zip` den Wert `digest` ohne `sha256:`."""
    daten = json.loads(ausgabe)
    tag = daten["tag_name"]
    version = tag[1:] if tag.startswith("v") else tag
    asset = next(a for a in daten["assets"] if a["name"] == f"BMS_{version}.zip")
    return version, asset["digest"].removeprefix("sha256:")


@pytest.mark.parametrize("system, shell", AUSFUEHRUNGEN)
def test_befehle_laden_das_paket_und_pruefen_die_summe(projekt_root, github, tmp_path, system, shell):
    """Die Auskunft nennt Tag und Prüfsumme des Assets; Laden gibt `Antwort: 200` aus und die
    Zieldatei ist bytegleich mit dem Paket des Probeservers; die Prüfsumme aus dem dritten Block
    (beim Mac das erste Wort) stimmt mit dem `digest` überein, Groß-/Kleinschreibung egal."""
    befehle = _hauptbefehle(_anleitung(projekt_root, system), SPRACHE[system], DATEIEN[system])
    aufruf = _shell_vorbereiten(shell)
    umgebung = Arbeitsumgebung(tmp_path, github())

    auskunft = umgebung.ausfuehren(aufruf, befehle.auskunft)
    assert '"tag_name"' in auskunft.ausgabe and '"digest"' in auskunft.ausgabe, f"Auskunft ohne tag_name/digest:\n{auskunft}"
    version, erwartet = _auskunft_auswerten(auskunft.ausgabe)
    assert version == VERSION and erwartet == PAKET_SHA256

    laden = umgebung.ausfuehren(aufruf, befehle.laden, version)
    assert laden.ausgabe.strip() == "Antwort: 200", f"Laden:\n{laden}"
    ziel = umgebung.zip_pfad(version)
    assert ziel.is_file(), "Die Zieldatei fehlt"
    geladen = ziel.read_bytes()
    assert len(geladen) == len(PAKET_BYTES) and sha256(geladen).hexdigest() == PAKET_SHA256, \
        "Die Zieldatei ist nicht bytegleich mit dem Paket des Probeservers"
    with zipfile.ZipFile(ziel) as zf:       # ein lesbares ZIP, nicht nur gleiche Bytes
        assert zf.testzip() is None

    summe = umgebung.ausfuehren(aufruf, befehle.pruefsumme, version)
    erstes_wort = summe.ausgabe.split()[0] if summe.ausgabe.split() else ""
    assert erstes_wort.lower() == erwartet.lower(), f"Prüfsumme:\n{summe}"

    assert umgebung.dienst.aufrufe == [AUSKUNFT_PFAD, DOWNLOAD_PFAD]


@pytest.mark.parametrize("system, shell", AUSFUEHRUNGEN)
def test_laden_folgt_der_weiterleitung_von_github(projekt_root, github, tmp_path, system, shell):
    """Die echte Download-Adresse antwortet mit einer Umleitung (302). Der Befehl muss ihr folgen und
    am Ende `Antwort: 200` ausgeben; die Zieldatei ist das Paket, nicht die Umleitungsseite."""
    befehle = _hauptbefehle(_anleitung(projekt_root, system), SPRACHE[system], DATEIEN[system])
    aufruf = _shell_vorbereiten(shell)
    umgebung = Arbeitsumgebung(tmp_path, github(laden="umleitung"))

    laden = umgebung.ausfuehren(aufruf, befehle.laden)

    assert laden.ausgabe.strip() == "Antwort: 200", f"Laden:\n{laden}"
    ziel = umgebung.zip_pfad()
    assert ziel.is_file() and sha256(ziel.read_bytes()).hexdigest() == PAKET_SHA256
    assert umgebung.dienst.aufrufe == [DOWNLOAD_PFAD, WEITERLEITUNG_PFAD]


@pytest.mark.parametrize("system, shell", AUSFUEHRUNGEN)
def test_fehlende_datei_auf_github_zeigt_404_und_raeumt_auf(projekt_root, github, tmp_path, system, shell):
    """Gibt es die Datei nicht (404): Laden gibt `Antwort: 404` aus, und danach liegt kein gültiges
    Paket unter dem Zielpfad (curl legt mit -f keine Fehlerseite ab). Der Befehl der Anleitung für den
    Fehlerfall räumt auf, auch wenn gar keine Datei da ist (zweiter Aufruf), und meldet dann keinen Fehler."""
    text = _anleitung(projekt_root, system)
    befehle = _hauptbefehle(text, SPRACHE[system], DATEIEN[system])
    fehlerbefehle = _fehlerbefehle(text, system, DATEIEN[system])
    aufruf = _shell_vorbereiten(shell)
    umgebung = Arbeitsumgebung(tmp_path, github(laden="404"))
    ziel = umgebung.zip_pfad()

    laden = umgebung.ausfuehren(aufruf, befehle.laden)
    assert laden.ausgabe.strip() == "Antwort: 404", f"Laden:\n{laden}"
    if os.name == "posix":
        assert laden.code == 22, f"curl -f meldet den Fehlerstatus über den Exit-Code 22:\n{laden}"
    # Ohne -f läge die Fehlerseite („Not Found“) als vermeintliches Paket da; mit -f legt curl höchstens
    # eine leere Datei an (meist gar keine).
    assert not ziel.exists() or ziel.stat().st_size == 0, "Nach einem 404 darf keine Fehlerseite als Paket liegen"

    for befehl in fehlerbefehle:
        umgebung.ausfuehren(aufruf, befehl)
    assert not ziel.exists(), "Die Datei muss nach dem Fehlerfall-Befehl gelöscht sein"
    for befehl in fehlerbefehle:        # ohne Datei: kein Fehler (unter Windows ist der Exit-Code nicht aussagekräftig)
        lauf = umgebung.ausfuehren(aufruf, befehl)
        if os.name == "posix":
            assert lauf.code == 0 and lauf.fehler == "", f"Der Befehl muss auch ohne Datei still bleiben:\n{lauf}"
    assert not ziel.exists()

    assert umgebung.dienst.aufrufe == [DOWNLOAD_PFAD]


@pytest.mark.parametrize("system, shell", AUSFUEHRUNGEN)
def test_abweichende_pruefsumme_wird_erkannt_und_aufgeraeumt(projekt_root, github, tmp_path, system, shell):
    """Kommt ein unvollständiges Paket an (200, aber zu kurz), zeigt der Prüfsummen-Befehl einen anderen
    Wert als der `digest` der Auskunft. Der Befehl für den Fehlerfall löscht die Datei."""
    text = _anleitung(projekt_root, system)
    befehle = _hauptbefehle(text, SPRACHE[system], DATEIEN[system])
    fehlerbefehle = _fehlerbefehle(text, system, DATEIEN[system])
    aufruf = _shell_vorbereiten(shell)
    umgebung = Arbeitsumgebung(tmp_path, github(laden="beschaedigt"))
    ziel = umgebung.zip_pfad()

    laden = umgebung.ausfuehren(aufruf, befehle.laden)
    assert laden.ausgabe.strip() == "Antwort: 200", f"Laden:\n{laden}"
    assert ziel.is_file()

    summe = umgebung.ausfuehren(aufruf, befehle.pruefsumme)
    erstes_wort = summe.ausgabe.split()[0] if summe.ausgabe.split() else ""
    assert re.fullmatch(r"[0-9a-fA-F]{64}", erstes_wort), f"Prüfsumme:\n{summe}"
    assert erstes_wort.lower() != PAKET_SHA256, "Die Prüfsumme eines beschädigten Pakets darf nicht passen"

    for befehl in fehlerbefehle:
        umgebung.ausfuehren(aufruf, befehl)
    assert not ziel.exists(), "Die Datei muss nach dem Fehlerfall-Befehl gelöscht sein"


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 7 — Selbsttests: Die Prüfungen schlagen an (Gegenproben, dauerhaft)
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_zerlegen_arbeitet_zeilenweise_und_kennt_eingerueckte_zaeune():
    text = ("# Titel\n\n"
            "2. **Befehle in eigenen Codeblöcken** (` ```sh `), vollständig.\n\n"    # drei Backticks im Fließtext
            "## Abschnitt\n\n"
            "```sh\n# kein Kommentar-Titel\n## auch keiner\necho eins\n```\n\n"
            "1. Punkt:\n\n"
            "   ```powershell\n   # eingerückt\n   Get-Date\n   ```\n\n"
            "Text danach\n")

    prosa, bloecke = _zerlegen(text)

    assert _ueberschriften(text) == ["# Titel", "## Abschnitt"]
    assert [(b.sprache, b.text) for b in bloecke] == [
        ("sh", "# kein Kommentar-Titel\n## auch keiner\necho eins"),
        ("powershell", "# eingerückt\nGet-Date")]
    assert any("Text danach" in zeile for _, zeile in prosa)
    with pytest.raises(AssertionError):
        _zerlegen("# T\n\n```sh\nnie geschlossen\n")


def _zeile(muster: str) -> str:
    """Eine ganze Zeile exakt (für re.sub mit MULTILINE)."""
    return "(?m)^" + re.escape(muster) + "$"


def _tauschen(text: str, a: str, b: str) -> str:
    """Zwei Überschriftenzeilen (Anfang der Zeile bis Zeilenende) vertauschen."""
    text = re.sub(_zeile(a), "@@", text, count=1)
    text = re.sub(_zeile(b), a, text, count=1)
    return text.replace("@@", b, 1)


@pytest.mark.parametrize("system", ["mac", "windows"])
@pytest.mark.parametrize("name, aendern", [
    ("fehlende Überschrift", lambda t: re.sub(_zeile("## Gesprächsregeln") + "\n", "", t, count=1)),
    ("fehlender Schritt", lambda t: re.sub(r"(?m)^## Schritt 7:[^\n]*\n", "", t, count=1)),
    ("zwölfter Schritt", lambda t: re.sub(_zeile("# Nach der Installation"),
                                          "## Schritt 11: Noch ein Schritt\n\n# Nach der Installation", t, count=1)),
    ("vertauschte Überschriften", lambda t: _tauschen(t, "## Ihre Daten", "## Hilfe")),
    ("vertauschte Schritte", lambda t: re.sub(r"(?m)^## Schritt (3|4):",
                                              lambda m: "## Schritt " + {"3": "4", "4": "3"}[m.group(1)] + ":", t)),
    ("geänderte Überschrift", lambda t: re.sub(_zeile("## Hilfe"), "## Hilfe und Kontakt", t, count=1)),
    ("falsche Ebene", lambda t: re.sub(_zeile("## Kurz prüfen, ob alles sitzt"),
                                       "### Kurz prüfen, ob alles sitzt", t, count=1)),
    ("zusätzliche Überschrift", lambda t: t + "\n## Noch ein Abschnitt\n"),
    ("doppelte Überschrift", lambda t: re.sub(_zeile("## Hilfe"), "## Hilfe\n\n## Hilfe", t, count=1)),
    ("Titel der Datei", lambda t: re.sub(r"\A# [^\n]*", "# Installation", t, count=1)),
])
def test_aufbaupruefung_schlaegt_bei_verfaelschtem_aufbau_an(projekt_root, system, name, aendern):
    original = _anleitung(projekt_root, system)
    assert _aufbau_probleme(original, system) == []

    verfaelscht = aendern(original)

    assert verfaelscht != original, f"Die Verfälschung {name!r} hat nichts geändert"
    assert _aufbau_probleme(verfaelscht, system), name


def test_aufbaupruefung_kennt_den_windows_abschnitt_nur_in_der_windows_datei(projekt_root):
    mac = _anleitung(projekt_root, "mac")
    windows = _anleitung(projekt_root, "windows")
    abschnitt = "## Was unter Windows eingeschränkt ist"

    assert abschnitt not in _ueberschriften(mac) and abschnitt in _ueberschriften(windows)
    # Die Datei des einen Systems besteht die Prüfung des anderen nicht.
    assert _aufbau_probleme(mac, "windows") and _aufbau_probleme(windows, "mac")
    # Der Abschnitt in der Mac-Datei ist ein Fund, sein Fehlen in der Windows-Datei ebenfalls.
    assert _aufbau_probleme(mac.replace("\n## Ihre Daten\n", f"\n{abschnitt}\n\n## Ihre Daten\n", 1), "mac")
    assert _aufbau_probleme(windows.replace(f"\n{abschnitt}\n", "\n", 1), "windows")


def test_aufbaupruefung_zaehlt_ueberschriften_in_codebloecken_nicht(projekt_root):
    for system in ("mac", "windows"):
        original = _anleitung(projekt_root, system)
        mit_block = original + "\n```sh\n# BMS: Titel im Block\n## Schritt 99: im Block\n## Zusatz\n```\n"
        assert _aufbau_probleme(mit_block, system) == [], system


@pytest.mark.parametrize("system", ["mac", "windows"])
def test_begriffspruefung_schlaegt_bei_lizenz_und_paketdienst_an(projekt_root, system):
    original = _anleitung(projekt_root, system)
    assert _verbotene_funde(original) == []

    # Die alte Adresse zusammengesetzt, sonst schlüge der Wächter test_ohne_lizenz.py hier an.
    for eingeschleust in ("Paket von " + "bms." + "daube.tech laden", "Schreiben Sie uns über daube.tech/kontakt",
                          "Ihre Lizenzdatei", "kostenlose Testlizenz", "Band „Ansichtsmodus“",
                          'curl --data-binary @"LIZENZ-PFAD" "https://x/api/paket/laden"'):
        assert _verbotene_funde(original + f"\n{eingeschleust}\n"), eingeschleust
    # „Apache-Lizenz“ im Fließtext ist erlaubt.
    assert _verbotene_funde("Open Source unter der Apache-Lizenz 2.0") == []


def _im_block_aendern(text: str, block: Block, aenderung: Callable[[str], str]) -> str:
    """`aenderung` auf jede Zeile des Blocks anwenden (nicht auf gleichlautenden Fließtext: Der
    Prüfbefehl steht in den Anleitungen auch einmal inline im Text)."""
    zeilen = text.splitlines()
    for i in range(block.zeile, block.zeile + len(block.text.splitlines())):   # Zeile nach dem Zaun
        zeilen[i] = aenderung(zeilen[i])
    return "\n".join(zeilen) + "\n"


@pytest.mark.parametrize("system", ["mac", "windows"])
def test_befehlspruefung_schlaegt_bei_verfaelschten_bloecken_an(projekt_root, system):
    text = _anleitung(projekt_root, system)
    sprache = SPRACHE[system]
    original = _hauptbefehle(text, sprache, "Original")
    bloecke = {name: next(b for b in _zerlegen(text)[1] if b.sprache == sprache and b.text == getattr(original, name))
               for name in ("auskunft", "laden", "pruefsumme")}

    # um ein Zeichen verändert: Der Vergleich meldet genau diesen Block
    aenderungen = {"auskunft": lambda z: z.replace("-sS", "-sK", 1),
                   "laden": lambda z: z.replace("BMS_VERSION.zip", "BMS_VERSIO.zip", 1),
                   "pruefsumme": lambda z: z + " "}
    for name, aenderung in aenderungen.items():
        kopie = _im_block_aendern(text, bloecke[name], aenderung)
        assert kopie != text, name
        assert _unterschiede(_hauptbefehle(kopie, sprache, "Kopie"), original) == [name], name

    # doppelt vorhanden, in anderer Sprache oder gar nicht: rot statt übersprungen
    doppelt = text + f"\n```{sprache}\n{original.auskunft}\n```\n"
    with pytest.raises(AssertionError, match="erwartet genau 1"):
        _hauptbefehle(doppelt, sprache, "Doppelt")
    zeilen = text.splitlines()
    zeilen[bloecke["laden"].zeile - 1] = "```text"
    with pytest.raises(AssertionError, match="erwartet genau 1"):
        _hauptbefehle("\n".join(zeilen) + "\n", sprache, "Andere Sprache")
    ohne = _im_block_aendern(text, bloecke["pruefsumme"], lambda z: "echo ohne")
    with pytest.raises(AssertionError, match="erwartet genau 1"):
        _hauptbefehle(ohne, sprache, "Ohne Prüfsumme")


@pytest.mark.parametrize("system", ["mac", "windows"])
def test_fehlerbefehle_muessen_woertlich_in_der_anleitung_stehen(projekt_root, system):
    text = _anleitung(projekt_root, system)
    assert _fehlerbefehle(text, system, "Original")

    if system == "mac":
        block = next(b for b in _zerlegen(text)[1] if b.text == MAC_FEHLERBEFEHL)
        kaputt = _im_block_aendern(text, block, lambda z: z + "x")
    else:
        kaputt = text.replace(f"`{WINDOWS_FEHLERBEFEHLE[0]}`", "`Remove-Item ZIP-PFAD`", 1)
    assert kaputt != text
    with pytest.raises(AssertionError):
        _fehlerbefehle(kaputt, system, "Kaputt")


def test_ersetzung_laesst_keine_echte_adresse_durch(tmp_path):
    """Die Sicherung in `einsetzen`: Die zwei GitHub-Adressen werden ersetzt, jede andere Spur eines
    echten Hosts (auch ein Host unter githubusercontent.com oder der frühere Paketdienst) ist ein Fehler."""
    umgebung = Arbeitsumgebung(tmp_path, type("Dienst", (), {"adresse": "http://127.0.0.1:1"})())

    fertig = umgebung.einsetzen(f'curl "{API_ADRESSE}/x" "{GITHUB_ADRESSE}/y" -o "ZIP-PFAD"')
    assert "github.com" not in fertig and fertig.count("http://127.0.0.1:1/") == 2

    for echt in ('curl "http://github.com/y"', 'curl "https://raw.githubusercontent.com/y"',
                 'curl "https://bms.' + 'daube.tech/api/paket/auskunft"'):  # zusammengesetzt wegen test_ohne_lizenz.py
        with pytest.raises(AssertionError, match="echte Adresse"):
            umgebung.einsetzen(echt)
    # Bleibt nach dem Einsetzen ein Platzhalter übrig (hier erzwungen durch eine Version, die selbst
    # „VERSION“ heißt), schlägt die Sicherung ebenfalls an.
    with pytest.raises(AssertionError, match="Platzhalter"):
        umgebung.einsetzen('curl "BMS_VERSION.zip"', version="VERSION")


def test_probeserver_schlaegt_bei_falscher_adresse_oder_kopfzeile_an(github):
    """Der Probeserver beißt: eine falsche Adresse, ein Anfrageteil oder eine fehlende Accept-Kopfzeile
    sind Verstöße, eine richtige Anfrage ist keiner."""
    dienst = github()
    ohne_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def holen(pfad: str, accept: str | None = "application/vnd.github+json") -> int:
        anfrage = urllib.request.Request(dienst.adresse + pfad, headers={"Accept": accept} if accept else {})
        try:
            with ohne_proxy.open(anfrage, timeout=10) as antwort:
                return antwort.status
        except urllib.error.HTTPError as fehler:
            return fehler.code

    assert holen(AUSKUNFT_PFAD) == 200 and dienst.verstoesse == []
    assert holen("/api/paket/auskunft") == 404
    assert holen(AUSKUNFT_PFAD + "?x=1") == 200
    assert holen(AUSKUNFT_PFAD, accept=None) == 200
    assert len(dienst.verstoesse) == 3, dienst.verstoesse
    dienst.verstoesse.clear()       # erwartet; sonst schlägt die Fixture am Ende an


def test_alte_namen_werden_erkannt_die_neuen_nicht():
    for text in ("siehe `BMS_Install.md`", "BMS_Install.html im Ordner", "`BMS_Install_Auto.md` führt",
                 "bms_install.md", "Datei BMS_Install, Abschnitt 3"):
        assert _alte_namen_funde(text), text
    for text in ("siehe `BMS_Install_MAC.md`", "`BMS_Install_Windows.md`, Abschnitt „Hilfe“",
                 "BMS_Install_MAC.html", "Installation des BMS"):
        assert not _alte_namen_funde(text), text


def test_ein_alter_dateiname_in_einem_kundentext_wird_gefunden(projekt_root, tmp_path):
    """Gegenstück zum Test oben, mit dem Weg über Dateien: ein Kundentext mit altem Namen ist ein Fund."""
    sauber = "Siehe `BMS_Install_MAC.md`, Abschnitt „Aktualisierungen einspielen“.\n"
    alt = "Siehe `BMS_Install.md`, Abschnitt 5.\n"
    (tmp_path / "sauber.md").write_text(sauber, encoding="utf-8")
    (tmp_path / "alt.md").write_text(alt, encoding="utf-8")

    assert not _alte_namen_funde((tmp_path / "sauber.md").read_text(encoding="utf-8"))
    assert _alte_namen_funde((tmp_path / "alt.md").read_text(encoding="utf-8"))
