#!/usr/bin/env python3
"""Drittanbieter-Lizenzen (P2-77) — die Seite „Rechtliches → Drittanbieter-Lizenzen“ wird ERZEUGT.

Auslöser: Die Seite war von Hand gepflegt und lief den Paketlisten davon (10 statt 38 Python-Pakete,
keine Versionen, keine Lizenztexte, obwohl MIT, BSD und Apache-2.0 verlangen, dass Copyright- und
Lizenzhinweis mitgehen). Seither gilt wie bei `docs_render.py`: Doppelpflege-Verbot. Quellen sind die
Lockfiles (`backend/requirements-lock.txt`, `frontend/package-lock.json`) sowie `pyproject.toml` und
`package.json` für die Einteilung „direkt“ und „mitgebracht“. Erzeugt werden zwei Dateien, beide nie von
Hand zu ändern:
  - `frontend/src/rechtliches/drittlizenzen.md`          Übersicht (Name, Version, Kennung, Zweck)
  - `frontend/src/rechtliches/drittlizenzen_texte.txt`   Wortlaut aller mitinstallierten Lizenzen

LEITLINIEN
  - Wortlaut bleibt unverändert. Erlaubt sind nur zwei Angleichungen: Zeilenenden auf LF und
    Leerzeichen am Zeilenende weg. Nichts wird geschwärzt (auch keine Autoren-Adressen, dafür gibt es
    die pfadgebundene Ausnahme in `pipeline/kundenpaket.py`).
  - Byte-gleiche Texte (nach der Angleichung) stehen einmal, mit allen Paketen, für die sie gelten.
  - Die Lizenzkennung wird nicht geraten: (1) `License-Expression`, (2) das Feld `License`, wenn es
    genau eine Kennung der Positivliste ist, (3) die Tabelle `LIZENZ_FESTGELEGT` mit Kennung und
    SHA-256 des Wortlauts. Passt nichts oder hat sich der Wortlaut geändert, bricht der Generator ab.
  - Positivliste statt Einzelfallprüfung: Eine neue Lizenz macht den Lauf (und die CI-Wache) rot,
    die Projektleitung entscheidet. Die Liste selbst ist ihre Entscheidung (bestätigt 16.10.2026).
  - Deterministisch: kein Datum, keine BMS-Version, kein absoluter Pfad. Zwei Läufe = gleiche Bytes.
  - Nur Standardbibliothek.

ERZEUGT WIRD BEIM MAINTAINER, GEPRÜFT ÜBERALL: Der Generator braucht das venv (Python-Metadaten) und den
Build-Spiegel (`node_modules`). Die reinen Prüffunktionen für die CI-Wache (`bestand_soll`,
`bestand_ist`, `abweichungen`, `kennung_erlaubt`) brauchen beides nicht — sie vergleichen den Bestand
der erzeugten Seite mit den Lockfiles. Die Wache prüft Bestand und Kennungen, nicht den Wortlaut (den
prüft `--pruefen` mit venv und Spiegel, also nur beim Maintainer).

NAHT FÜR DIE TESTS: `sammeln(projekt_root, node_modules, site_pfad=None)`. `site_pfad` ist eine Liste von
Ordnern, in denen `importlib.metadata` nach `*.dist-info` sucht (Vorgabe: `sys.path`, also das venv). Die
Einheitstests bauen in `tmp_path` ein Fake-`site-packages` mit echten `*.dist-info`-Ordnern.

CLI (aus backend/):
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.drittlizenzen              # erzeugt beide Dateien
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.drittlizenzen --pruefen    # vergleicht nur
        [--node-modules DIR]   # Vorgabe: ~/.bewerbung_mgmt_node/frontend_build/node_modules
Bequemer Aufruf vom Projekt-Root: `scripts/drittlizenzen.sh` (reicht Argumente 1:1 durch).

Exit-Codes: 0 erzeugt bzw. bei `--pruefen` aktuell; 1 nur bei `--pruefen`: mindestens eine Datei
veraltet (die Ausgabe nennt sie); 2 Fehler (die Meldung nennt das Paket und den nächsten Schritt).
"""
import argparse
import hashlib
import importlib.metadata
import json
import re
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STANDARD_NODE_MODULES = Path.home() / ".bewerbung_mgmt_node" / "frontend_build" / "node_modules"

ZIEL_MD = "frontend/src/rechtliches/drittlizenzen.md"
ZIEL_MD_EN = "frontend/src/rechtliches/drittlizenzen.en.md"
ZIEL_TXT = "frontend/src/rechtliches/drittlizenzen_texte.txt"

# ── Konstanten ─────────────────────────────────────────────────────────────────────────────
# Positivliste: Entscheidung vom 16.10.2026, MPL-2.0 (certifi) eingeschlossen. Eine neue
# Lizenz macht den Generator und die CI-Wache rot, die Projektleitung entscheidet. Nicht hier eigenmächtig
# erweitern.
POSITIVLISTE: frozenset[str] = frozenset({
    "MIT", "MIT-0", "ISC", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "PSF-2.0", "MPL-2.0",
    "OFL-1.1",
})
# Nur für Bauwerkzeuge erlaubt (laufen nur beim Bauen, sind nicht Teil der fertigen Oberfläche).
NUR_BAUWERKZEUG: frozenset[str] = frozenset({"CC-BY-4.0"})  # heute: caniuse-lite

# Pakete, deren Lizenzfeld nicht eindeutig ist. Kennung und SHA-256 (erste 12 Hex-Zeichen) des
# angeglichenen Wortlauts, beim Bau im venv GELESEN (nicht übernommen): google-auth und
# google-auth-oauthlib tragen im Feld „License“ nur „Apache 2.0“, ihr Text ist „Apache License,
# Version 2.0“. pyasn1_modules trägt „BSD“, der Text hat zwei Bedingungen und nicht die Klausel
# „Neither the name …“, ist also BSD-2-Clause. Hat sich der Wortlaut geändert, bricht der Generator ab:
# Text neu lesen, Kennung bestätigen, Hash hier nachziehen. Schlüssel: Name nach PEP 503.
LIZENZ_FESTGELEGT: dict[str, tuple[str, str]] = {
    "google-auth": ("Apache-2.0", "c71d239df917"),
    "google-auth-oauthlib": ("Apache-2.0", "cfc7749b96f6"),
    "pyasn1-modules": ("BSD-2-Clause", "07538c4a2098"),
}

# Zweck je direktem Paket (Python und Oberfläche). Schlüssel: Name nach PEP 503 (bei npm der
# Paketname). Fehlt ein Eintrag für ein direktes Paket, bricht der Generator ab. Kein " — " im Text
# (Trenner der Paketzeile).
ZWECK: dict[str, str] = {
    # Python (pyproject.toml)
    "fastapi": "Web-Schnittstelle des Backends",
    "uvicorn": "lokaler Webserver",
    "sqlmodel": "Datenmodell und Datenbankzugriff",
    "python-docx": "Word-Dateien (Lebenslauf, Anschreiben)",
    "openpyxl": "Excel-Import (Netzwerk, Listen)",
    "python-multipart": "Datei-Uploads",
    "pypdf": "Text aus dem PDF des LinkedIn-Profils lesen",
    "httpx": "Abrufe bei Apify, Arbeitsagentur, OpenAI",
    "pyyaml": "Konfiguration (Suchprofile, Budgets)",
    "google-auth": "Gmail-Anbindung",
    "google-auth-oauthlib": "Anmeldung bei Gmail",
    "bcrypt": "Passwort-Hash der Coach-Site",
    "markdown": "Dokumentation nach HTML",
    # Oberfläche (package.json, dependencies)
    "react": "Grundgerüst der Oberfläche",
    "i18next": "Oberfläche in mehreren Sprachen",
    "react-i18next": "Mehrsprachigkeit in der Oberfläche",
    "react-dom": "Darstellung im Browser",
    "react-router-dom": "Seitennavigation",
    "@fontsource/inter": "Schrift Inter (Fließtext)",
    "@fontsource/montserrat": "Schrift Montserrat (Überschriften)",
}

# Programme, die der Nutzer separat installiert (nicht Teil der Software, das BMS ruft sie als
# eigenständige Prozesse auf). Name, Lizenz, Zweck, ohne Versionen. Reihenfolge wie hier.
PROGRAMME: list[tuple[str, str, str]] = [
    ("Python", "PSF-2.0", "Laufzeit des Backends"),
    ("SQLite", "Public Domain", "Datenbank (in Python enthalten)"),
    ("Node.js", "MIT", "baut die Oberfläche bei Installation und Update"),
    ("Claude Code", "proprietär (Anthropic)", "führt die KI-Funktionen aus, wenn Claude gewählt ist"),
    ("Codex CLI", "Apache-2.0", "führt die KI-Funktionen aus, wenn ChatGPT gewählt ist"),
    ("LibreOffice", "MPL-2.0", "wandelt Lebensläufe in PDF um"),
    ("Homebrew", "BSD-2-Clause", "installiert die Programme (macOS)"),
    ("winget", "MIT", "installiert die Programme (Windows)"),
    ("Git for Windows", "GPL-2.0", "wird von Claude Code unter Windows gebraucht"),
    ("lftp", "GPL-3.0", "lädt die Coach-Site per SFTP hoch (optional)"),
    ("htpasswd (Apache httpd)", "Apache-2.0", "Passwortdatei der Coach-Site (optional)"),
]

# Von Nutzern angebundene Drittdienste (Wortlaut und Reihenfolge laut Spec P2-77). Kommt ein Dienst
# dazu oder fällt einer weg, hier und in frontend/src/rechtliches/datenschutz.md nachziehen.
DIENSTE: list[str] = [
    "**Anthropic (Claude, Claude Code)**: KI-Funktionen, wenn Claude gewählt ist, mit eigenem Konto oder eigenem API-Schlüssel",
    "**OpenAI (ChatGPT, Codex CLI)**: KI-Funktionen, wenn ChatGPT gewählt ist, mit eigenem ChatGPT-Konto; "
    "außerdem optional zweiter Motor für den Beirat, mit eigenem API-Schlüssel",
    "**Apify** (optional): Portal-Suche mit Scrapern von Drittentwicklern, mit eigenem Konto",
    "**Jobsuche der Bundesagentur für Arbeit**: Abruf der öffentlichen Suchseite, ohne Konto",
    "**E-Mail-Anbieter des Nutzers** (IMAP) oder **Google Gmail**: Antworten und Job-Alerts lesen",
    "**Google Drive** (optional): Export des Outreach-Trackers",
    "**GitHub**: Suche nach Updates und Laden neuer Versionen, nur auf Start des Nutzers, ohne Konto",
]

# Lizenzdatei = Dateiname (ohne Rücksicht auf Groß-/Kleinschreibung) beginnt so.
_LIZENZDATEI_RE = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", re.IGNORECASE)

# Abschnittsüberschriften der Übersicht (fester Aufbau, `bestand_ist` liest danach).
_H_PY_DIREKT = "Backend (Python), direkt verwendet"
_H_PY_MIT = "Backend (Python), von diesen Paketen mitgebracht"
_H_NPM_DIREKT = "Oberfläche (läuft im Browser), direkt verwendet"
_H_NPM_MIT = "Oberfläche, mitgebracht"
_H_BAU = "Zum Bauen der Oberfläche"
_H_PROGRAMME = "Separat vom Nutzer installierte Programme"
_H_DIENSTE = "Von Nutzern angebundene Drittdienste"
_ABSCHNITT_ZU_SCHLUESSEL = {
    _H_PY_DIREKT: "python_direkt",
    _H_PY_MIT: "python_mit",
    _H_NPM_DIREKT: "npm_direkt",
    _H_NPM_MIT: "npm_mit",
    _H_BAU: "bau_direkt",
}
_ANZEIGE_ABSCHNITT = {
    "python_direkt": _H_PY_DIREKT,
    "python_mit": _H_PY_MIT,
    "npm_direkt": _H_NPM_DIREKT,
    "npm_mit": _H_NPM_MIT,
    "bau_direkt": _H_BAU,
}

_TRENNLINIE = "=" * 70
_OHNE_ANGABE = "ohne Angabe"


class GeneratorFehler(Exception):
    """Fehler mit Meldung für den Maintainer (Paket und nächster Schritt). Führt zu Exit 2."""


# ── Kleine Helfer ───────────────────────────────────────────────────────────────────────────

def norm_name(name: str) -> str:
    """Paketname nach PEP 503: klein geschrieben, Folgen von `-`, `_`, `.` gelten als `-`."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _angleichen(text: str) -> str:
    """Die EINZIGEN erlaubten Änderungen am Lizenzwortlaut: Zeilenenden auf LF, Leerzeichen
    (und Tabs) am Zeilenende weg. Nichts sonst."""
    text = re.sub(r"\r\n?", "\n", text)
    return re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)


def wortlaut_hash(texte: list[str]) -> str:
    """SHA-256 (erste 12 Hex-Zeichen) der angeglichenen Lizenztexte eines Pakets: alle
    Lizenzdateien in Pfadreihenfolge, durch einen Zeilenumbruch getrennt (bei einer Datei also
    einfach der Hash dieses Textes)."""
    voll = "\n".join(texte)
    return hashlib.sha256(voll.encode("utf-8")).hexdigest()[:12]


def _lesen(pfad: Path, paket: str) -> str:
    """Lizenzdatei lesen (UTF-8, ein führendes BOM ist Kodierungsmarke und kein Wortlaut) und angleichen."""
    try:
        roh = pfad.read_bytes()
        return _angleichen(roh.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError) as exc:
        raise GeneratorFehler(
            f"Lizenzdatei von {paket} nicht lesbar ({pfad.name}): {exc}. "
            f"→ Datei prüfen und sie als UTF-8 ablegen oder den Generator anpassen."
        ) from exc


# ── Positivliste ───────────────────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r"\(|\)|[^\s()]+")


def kennung_erlaubt(ausdruck: str, nur_bau: bool = False) -> bool:
    """Ist die Lizenzkennung (SPDX-Ausdruck) auf der Positivliste?

    Klammern strukturieren, `A OR B` ist erlaubt, wenn eine Seite erlaubt ist, `A AND B` nur, wenn
    beide erlaubt sind (AND bindet stärker als OR). Alles Unbekannte oder Fehlerhafte (leerer
    Ausdruck, offene Klammer, `WITH`, `+`) ist nicht erlaubt. `CC-BY-4.0` gilt nur mit `nur_bau`."""
    if not isinstance(ausdruck, str):
        return False
    erlaubt = {k.lower() for k in (POSITIVLISTE | NUR_BAUWERKZEUG if nur_bau else POSITIVLISTE)}
    tokens = _TOKEN_RE.findall(ausdruck)
    if not tokens:
        return False
    pos = 0

    def ausdruck_lesen() -> bool:
        nonlocal pos
        wert = term_lesen()
        while pos < len(tokens) and tokens[pos].upper() == "OR":
            pos += 1
            rechts = term_lesen()
            wert = wert or rechts
        return wert

    def term_lesen() -> bool:
        nonlocal pos
        wert = faktor_lesen()
        while pos < len(tokens) and tokens[pos].upper() == "AND":
            pos += 1
            rechts = faktor_lesen()
            wert = wert and rechts
        return wert

    def faktor_lesen() -> bool:
        nonlocal pos
        if pos >= len(tokens):
            raise ValueError("Ausdruck endet zu früh")
        tok = tokens[pos]
        pos += 1
        if tok == "(":
            wert = ausdruck_lesen()
            if pos >= len(tokens) or tokens[pos] != ")":
                raise ValueError("Klammer nicht geschlossen")
            pos += 1
            return wert
        if tok == ")" or tok.upper() in ("AND", "OR"):
            raise ValueError("unerwartetes Token")
        return tok.lower() in erlaubt

    try:
        wert = ausdruck_lesen()
    except ValueError:
        return False
    return wert and pos == len(tokens)


def _einzelne_kennung(feld: str | None) -> str | None:
    """Stufe 2 der Kennungsermittlung: Das Feld `License` zählt nur, wenn es (bis auf Klammern und
    Leerraum) genau EINE Kennung der Positivliste ist. „Apache 2.0“ oder „BSD“ zählen nicht."""
    if not feld or len(feld) > 80 or "\n" in feld:
        return None
    tokens = [t for t in _TOKEN_RE.findall(feld) if t not in ("(", ")")]
    if len(tokens) != 1:
        return None
    treffer = {k.lower(): k for k in POSITIVLISTE}.get(tokens[0].lower())
    return treffer


# ── Sammeln ────────────────────────────────────────────────────────────────────────────────

@dataclass
class Lizenzdatei:
    pfad: str       # sortierbar, relativ zur dist-info bzw. zum Paketordner
    name: str       # Dateiname
    text: str       # angeglichen


@dataclass
class Paket:
    name: str       # wie im Lockfile geschrieben
    version: str
    art: str        # "Python" oder "Oberfläche"
    kennung: str
    zweck: str | None = None
    dateien: list[Lizenzdatei] = field(default_factory=list)


@dataclass
class Bestand:
    python_direkt: list[Paket]
    python_mit: list[Paket]
    npm_direkt: list[Paket]
    npm_mit: list[Paket]
    bau_direkt: list[tuple[str, str, str]]      # (Name, Version, Kennung)
    bau_zaehlung: dict[str, int]                # Kennung -> Anzahl über alle dev-Einträge
    bau_gesamt: int


def _lockfile_python(root: Path) -> list[tuple[str, str]]:
    lock = root / "backend" / "requirements-lock.txt"
    try:
        zeilen = lock.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise GeneratorFehler(f"{lock.name} nicht lesbar: {exc}") from exc
    paare = []
    for roh in zeilen:
        zeile = roh.strip()
        if not zeile or zeile.startswith("#"):
            continue
        treffer = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)", zeile)
        if not treffer:
            raise GeneratorFehler(
                f"backend/requirements-lock.txt: Zeile nicht lesbar: {zeile!r}. "
                f"→ Erwartet wird je Zeile name==version."
            )
        paare.append((treffer.group(1), treffer.group(2)))
    return paare


def _direkte_python(root: Path) -> list[str]:
    try:
        daten = tomllib.loads((root / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise GeneratorFehler(f"backend/pyproject.toml nicht lesbar: {exc}") from exc
    namen = []
    for eintrag in daten.get("project", {}).get("dependencies", []):
        name = re.split(r"[<>=!~;\[\s(]", eintrag.strip(), maxsplit=1)[0]
        if name:
            namen.append(name)
    return namen


def _json_laden(pfad: Path, bezeichnung: str) -> dict:
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GeneratorFehler(f"{bezeichnung} nicht lesbar: {exc}") from exc


def _npm_name(schluessel: str) -> str:
    return schluessel.rsplit("node_modules/", 1)[1]


def _lizenz_str(eintrag: dict) -> str | None:
    wert = eintrag.get("license")
    return wert if isinstance(wert, str) and wert.strip() else None


def _lockfile_npm(root: Path) -> tuple[list[tuple[str, str, str | None, str]], list[tuple[str, str, str | None]]]:
    """Aus package-lock.json: (Produktiv-Pakete, dev-Pakete). Produktiv: (Name, Version, Kennung,
    Schlüssel) ohne `"dev": true`; dev: (Name, Version, Kennung). Nur Schlüssel `node_modules/…`.
    `"devOptional": true` zählt als dev: So markiert npm ein Bauwerkzeug, das ein Produktivpaket zusätzlich
    als optionalen Peer nennt (TypeScript bei `react-i18next`). In die Auslieferung gelangt es nicht."""
    daten = _json_laden(root / "frontend" / "package-lock.json", "frontend/package-lock.json")
    produktiv, dev = [], []
    for schluessel, eintrag in daten.get("packages", {}).items():
        if not schluessel.startswith("node_modules/") or not isinstance(eintrag, dict):
            continue
        name = _npm_name(schluessel)
        version = str(eintrag.get("version", ""))
        kennung = _lizenz_str(eintrag)
        if eintrag.get("dev") is True or eintrag.get("devOptional") is True:
            dev.append((name, version, kennung))
        else:
            produktiv.append((name, version, kennung, schluessel))
    return produktiv, dev


def _package_json(root: Path) -> dict:
    return _json_laden(root / "frontend" / "package.json", "frontend/package.json")


def _casefold_key(name: str) -> str:
    return name.casefold()


def _zweck(name: str) -> str:
    z = ZWECK.get(norm_name(name))
    if not z:
        raise GeneratorFehler(
            f"Für das direkte Paket {name} fehlt der Zweck. "
            f"→ In backend/pipeline/drittlizenzen.py in ZWECK einen kurzen Zweck eintragen."
        )
    return z


def _dist_finden(name: str, site_pfad: list | None):
    kwargs = {"name": name}
    if site_pfad is not None:
        kwargs["path"] = [str(p) for p in site_pfad]
    for dist in importlib.metadata.Distribution.discover(**kwargs):
        return dist
    raise GeneratorFehler(
        f"Python-Paket {name} ist im venv nicht installiert, das Lockfile verlangt es. "
        f"→ pip install -r backend/requirements-lock.txt"
    )


def _python_lizenzdateien(dist, name: str) -> list[Lizenzdatei]:
    """Lizenzdateien aus `dist.files`: Einträge innerhalb von `*.dist-info/` (auch im Unterordner
    `licenses/`), deren Dateiname auf das Lizenz-Muster passt. Sortiert nach Pfad."""
    dateien = []
    for f in dist.files or []:
        teile = f.parts
        if len(teile) < 2 or not teile[0].endswith(".dist-info"):
            continue
        if not _LIZENZDATEI_RE.match(f.name):
            continue
        rel = "/".join(teile[1:])
        dateien.append((rel, f))
    dateien.sort(key=lambda t: t[0])
    ergebnis = []
    for rel, f in dateien:
        ergebnis.append(Lizenzdatei(rel, f.name, _lesen(Path(str(dist.locate_file(f))), name)))
    return ergebnis


def _python_kennung(name: str, dist, dateien: list[Lizenzdatei]) -> str:
    """Kennung nach Leitentscheidung 4: License-Expression, dann einzelne Kennung im Feld License,
    dann die Tabelle LIZENZ_FESTGELEGT (mit Hash-Prüfung). Sonst Abbruch."""
    expr = (dist.metadata.get("License-Expression") or "").strip()
    if expr:
        return expr
    feld = (dist.metadata.get("License") or "").strip()
    einzel = _einzelne_kennung(feld)
    if einzel:
        return einzel
    hash_ist = wortlaut_hash([d.text for d in dateien])
    fest = LIZENZ_FESTGELEGT.get(norm_name(name))
    kurz = feld.splitlines()[0][:60] if feld else "leer"
    if fest is None:
        raise GeneratorFehler(
            f"Lizenzkennung von {name} ist nicht eindeutig (Feld License: {kurz!r}). "
            f"→ Den Lizenztext in der dist-info von {name} lesen und in LIZENZ_FESTGELEGT "
            f"(backend/pipeline/drittlizenzen.py) die Zeile pflegen: Kennung und Hash {hash_ist}."
        )
    kennung, hash_soll = fest
    if hash_ist != hash_soll:
        raise GeneratorFehler(
            f"Der Lizenzwortlaut von {name} hat sich geändert (Hash {hash_ist}, festgelegt war "
            f"{hash_soll}). → Den Text neu lesen, die Kennung bestätigen und die Zeile in "
            f"LIZENZ_FESTGELEGT (backend/pipeline/drittlizenzen.py) nachziehen."
        )
    return kennung


def _npm_lizenzdateien(ordner: Path, name: str) -> list[Lizenzdatei]:
    kandidaten = sorted(p for p in ordner.iterdir() if p.is_file() and _LIZENZDATEI_RE.match(p.name))
    return [Lizenzdatei(p.name, p.name, _lesen(p, name)) for p in kandidaten]


def sammeln(projekt_root: Path, node_modules: Path, site_pfad: list | None = None) -> Bestand:
    """Sammelt den Bestand aus Lockfiles, venv-Metadaten und Build-Spiegel. Wirft GeneratorFehler."""
    root = Path(projekt_root)
    node_modules = Path(node_modules)
    probleme: list[str] = []

    def kennung_pruefen(name: str, version: str, kennung: str | None, nur_bau: bool = False) -> None:
        if kennung is None or not kennung_erlaubt(kennung, nur_bau=nur_bau):
            probleme.append(
                f"Lizenz von {name} {version} ist {kennung or _OHNE_ANGABE!r} und steht nicht auf der "
                f"Positivliste. → Die Projektleitung entscheidet, ob die Liste (POSITIVLISTE in "
                f"backend/pipeline/drittlizenzen.py) erweitert wird oder das Paket entfällt."
            )

    # Python ----------------------------------------------------------------------------
    lock_py = _lockfile_python(root)
    direkte = {norm_name(n) for n in _direkte_python(root)}
    lock_namen = {norm_name(n) for n, _ in lock_py}
    for d in sorted(direkte - lock_namen):
        raise GeneratorFehler(
            f"Das direkte Paket {d} aus backend/pyproject.toml fehlt in backend/requirements-lock.txt. "
            f"→ Lockfile erneuern (pip freeze aus dem venv)."
        )
    py_direkt, py_mit = [], []
    for name, version in lock_py:
        dist = _dist_finden(name, site_pfad)
        if dist.version != version:
            raise GeneratorFehler(
                f"venv passt nicht zum Lockfile: {name} ist in Version {dist.version} installiert, "
                f"das Lockfile nennt {version}. → pip install -r backend/requirements-lock.txt"
            )
        dateien = _python_lizenzdateien(dist, name)
        if not dateien:
            raise GeneratorFehler(
                f"{name} {version} bringt keine Lizenzdatei mit (nichts Passendes in der dist-info). "
                f"→ Lizenz des Pakets prüfen und den Generator um einen Weg dafür erweitern."
            )
        kennung = _python_kennung(name, dist, dateien)
        kennung_pruefen(name, version, kennung)
        ist_direkt = norm_name(name) in direkte
        paket = Paket(name, version, "Python", kennung, _zweck(name) if ist_direkt else None, dateien)
        (py_direkt if ist_direkt else py_mit).append(paket)

    # npm -------------------------------------------------------------------------------
    pj = _package_json(root)
    npm_direkte = set(pj.get("dependencies", {}))
    bau_namen = list(pj.get("devDependencies", {}))
    produktiv, dev = _lockfile_npm(root)
    produktiv_namen = {n for n, _, _, _ in produktiv}
    for n in sorted(npm_direkte - produktiv_namen):
        raise GeneratorFehler(
            f"Das direkte Paket {n} aus frontend/package.json fehlt im Lockfile (oder ist dort als "
            f"Bauwerkzeug markiert). → In frontend npm install ausführen und das Lockfile prüfen."
        )
    npm_direkt, npm_mit = [], []
    for name, version, kennung, schluessel in produktiv:
        ordner = node_modules / schluessel[len("node_modules/"):]
        pj_datei = ordner / "package.json"
        try:
            ist_version = json.loads(pj_datei.read_text(encoding="utf-8")).get("version")
        except (OSError, json.JSONDecodeError):
            ist_version = None
        if ist_version != version:
            gefunden = f"in Version {ist_version}" if ist_version else "nicht"
            raise GeneratorFehler(
                f"Build-Spiegel passt nicht zum Lockfile: {name} ist dort {gefunden} vorhanden, das "
                f"Lockfile nennt {version}. → frontend/build.sh"
            )
        dateien = _npm_lizenzdateien(ordner, name)
        if not dateien:
            raise GeneratorFehler(
                f"{name} {version} bringt keine Lizenzdatei mit (nichts Passendes im Paketordner). "
                f"→ Lizenz des Pakets prüfen und den Generator um einen Weg dafür erweitern."
            )
        if kennung is None:
            probleme.append(f"Im Lockfile fehlt die Lizenzangabe von {name} {version}. → Lockfile prüfen.")
            kennung = _OHNE_ANGABE
        else:
            kennung_pruefen(name, version, kennung)
        ist_direkt = name in npm_direkte
        paket = Paket(name, version, "Oberfläche", kennung, _zweck(name) if ist_direkt else None, dateien)
        (npm_direkt if ist_direkt else npm_mit).append(paket)

    # Bauwerkzeuge -------------------------------------------------------------------------
    dev_nach_name = {n: (v, k) for n, v, k in dev}
    bau_direkt = []
    for name in bau_namen:
        if name not in dev_nach_name:
            raise GeneratorFehler(
                f"Das Bauwerkzeug {name} aus frontend/package.json fehlt im Lockfile (oder ist dort nicht "
                f"als dev markiert). → In frontend npm install ausführen und das Lockfile prüfen."
            )
        version, kennung = dev_nach_name[name]
        bau_direkt.append((name, version, kennung or _OHNE_ANGABE))
    zaehlung: Counter = Counter()
    for name, version, kennung in dev:
        kennung_pruefen(name, version, kennung, nur_bau=True)
        zaehlung[kennung or _OHNE_ANGABE] += 1

    if probleme:
        raise GeneratorFehler("\n".join(probleme))

    def sortiert(pakete: list[Paket]) -> list[Paket]:
        return sorted(pakete, key=lambda p: (_casefold_key(p.name), p.version))

    return Bestand(
        python_direkt=sortiert(py_direkt),
        python_mit=sortiert(py_mit),
        npm_direkt=sortiert(npm_direkt),
        npm_mit=sortiert(npm_mit),
        bau_direkt=sorted(bau_direkt, key=lambda t: _casefold_key(t[0])),
        bau_zaehlung=dict(zaehlung),
        bau_gesamt=len(dev),
    )


# ── Erzeugen ───────────────────────────────────────────────────────────────────────────────

def _zaehlung_sortiert(zaehlung: dict[str, int]) -> list[tuple[str, int]]:
    """Anzahl absteigend, dann Kennung."""
    return sorted(zaehlung.items(), key=lambda t: (-t[1], t[0]))


def _paketzeile(p: Paket) -> str:
    zeile = f"- **{p.name}** {p.version} — {p.kennung}"
    return f"{zeile} — {p.zweck}" if p.zweck else zeile


# Die englische Übersicht entsteht aus der deutschen: Gleiche Zeilen, gleiche Pakete, nur die festen Texte unten.
_UEBERSICHT_EN: tuple[tuple[str, str], ...] = (
    ("## Drittanbieter-Lizenzen", "## Third-party licences"),
    ("Diese Software verwendet Open-Source-Bestandteile. Für jeden gilt seine eigene Lizenz. Die Installation lädt die "
     "Pakete in genau diesen Versionen aus den öffentlichen Paketverzeichnissen PyPI und npm. Den vollständigen Wortlaut "
     "aller Lizenzen zeigt „Lizenztexte anzeigen“ unten. Im Programmordner steht er in der Datei "
     "frontend/src/rechtliches/drittlizenzen_texte.txt.",
     "This software uses open-source components. Each has its own licence. The installation downloads the packages in "
     "exactly these versions from the public PyPI and npm registries. “Show licence texts” below shows the full wording of "
     "all licences. In the program folder it is in the file frontend/src/rechtliches/drittlizenzen_texte.txt."),
    (_H_PY_DIREKT, "Backend (Python), used directly"),
    (_H_PY_MIT, "Backend (Python), brought in by these packages"),
    (_H_NPM_DIREKT, "Interface (runs in the browser), used directly"),
    (_H_NPM_MIT, "Interface, brought in"),
    (_H_BAU, "For building the interface"),
    (_H_PROGRAMME, "Programs installed separately by the user"),
    (_H_DIENSTE, "Third-party services connected by users"),
    ("Sie sind nicht Bestandteil dieser Software. Das BMS ruft sie als eigenständige Programme auf.",
     "They are not part of this software. The BMS calls them as independent programs."),
    ("Diese Dienste sind keine Bestandteile dieser Software. Ihre Nutzung unterliegt den Bedingungen des jeweiligen "
     "Anbieters, s. Datenschutzerklärung.",
     "These services are not part of this software. Their use is subject to the terms of the respective provider, see "
     "the privacy notice."),
    ("Diese Übersicht wird aus den Paketlisten des Programms erzeugt.",
     "This overview is generated from the program's package lists."),
    # Zweck der Pakete
    ("Abrufe bei Apify, Arbeitsagentur, OpenAI", "Requests to Apify, the Federal Employment Agency, OpenAI"),
    ("Anmeldung bei Gmail", "Sign-in to Gmail"),
    ("Darstellung im Browser", "Rendering in the browser"),
    ("Datei-Uploads", "File uploads"),
    ("Datenmodell und Datenbankzugriff", "Data model and database access"),
    ("Dokumentation nach HTML", "Documentation to HTML"),
    ("Excel-Import (Netzwerk, Listen)", "Excel import (network, lists)"),
    ("Gmail-Anbindung", "Gmail connection"),
    ("Grundgerüst der Oberfläche", "Basis of the interface"),
    ("Konfiguration (Suchprofile, Budgets)", "Configuration (search profiles, budgets)"),
    ("Mehrsprachigkeit in der Oberfläche", "Multiple languages in the interface"),
    ("Oberfläche in mehreren Sprachen", "Interface in several languages"),
    ("Passwort-Hash der Coach-Site", "Password hash of the coach site"),
    ("Schrift Inter (Fließtext)", "Inter typeface (body text)"),
    ("Schrift Montserrat (Überschriften)", "Montserrat typeface (headings)"),
    ("Seitennavigation", "Page navigation"),
    ("Text aus dem PDF des LinkedIn-Profils lesen", "Reading text from the LinkedIn profile PDF"),
    ("Web-Schnittstelle des Backends", "Web interface of the backend"),
    ("Word-Dateien (Lebenslauf, Anschreiben)", "Word files (CV, cover letter)"),
    ("lokaler Webserver", "local web server"),
    # Programme
    ("Laufzeit des Backends", "Runtime of the backend"),
    ("Datenbank (in Python enthalten)", "Database (included in Python)"),
    ("baut die Oberfläche bei Installation und Update", "builds the interface during installation and updates"),
    ("proprietär (Anthropic)", "proprietary (Anthropic)"),
    ("führt die KI-Funktionen aus, wenn Claude gewählt ist", "runs the AI functions if Claude is selected"),
    ("führt die KI-Funktionen aus, wenn ChatGPT gewählt ist", "runs the AI functions if ChatGPT is selected"),
    ("wandelt Lebensläufe in PDF um", "converts CVs to PDF"),
    ("installiert die Programme (macOS)", "installs the programs (macOS)"),
    ("installiert die Programme (Windows)", "installs the programs (Windows)"),
    ("wird von Claude Code unter Windows gebraucht", "needed by Claude Code on Windows"),
    ("lädt die Coach-Site per SFTP hoch (optional)", "uploads the coach site via SFTP (optional)"),
    ("Passwortdatei der Coach-Site (optional)", "password file of the coach site (optional)"),
    # Dienste
    ("KI-Funktionen, wenn Claude gewählt ist, mit eigenem Konto oder eigenem API-Schlüssel",
     "AI functions if Claude is selected, with your own account or API key"),
    ("KI-Funktionen, wenn ChatGPT gewählt ist, mit eigenem ChatGPT-Konto; außerdem optional zweiter Motor für den Beirat, "
     "mit eigenem API-Schlüssel",
     "AI functions if ChatGPT is selected, with your own ChatGPT account; also an optional second engine for the Advisory "
     "Board, with your own API key"),
    ("Portal-Suche mit Scrapern von Drittentwicklern, mit eigenem Konto",
     "portal search with scrapers by third-party developers, with your own account"),
    ("**Jobsuche der Bundesagentur für Arbeit**: Abruf der öffentlichen Suchseite, ohne Konto",
     "**Job search of the German Federal Employment Agency**: fetching the public search page, no account"),
    ("**E-Mail-Anbieter des Nutzers** (IMAP) oder **Google Gmail**: Antworten und Job-Alerts lesen",
     "**The user's email provider** (IMAP) or **Google Gmail**: reading replies and job alerts"),
    ("Export des Outreach-Trackers", "export of the outreach tracker"),
    ("Suche nach Updates und Laden neuer Versionen, nur auf Start des Nutzers, ohne Konto",
     "checking for updates and downloading new versions, only when the user starts it, no account"),
)


def uebersicht_englisch(md: str) -> str:
    """Die deutsche Übersicht als englische Fassung. Ein neuer deutscher Text ohne Eintrag oben lässt
    test_drittlizenzen.py scheitern."""
    for deutsch, englisch in _UEBERSICHT_EN:
        md = md.replace(deutsch, englisch)
    return re.sub(
        r"Dazu kommen (\d+) weitere Werkzeuge, die diese mitbringen\. Sie laufen nur beim Bauen und sind nicht Teil der "
        r"fertigen Oberfläche\. Lizenzen aller (\d+):",
        r"In addition there are \1 more tools that these bring in. They only run during the build and are not part of the "
        r"finished interface. Licences of all \2:", md)


def uebersicht_erzeugen(b: Bestand) -> str:
    """Die Übersicht `drittlizenzen.md`. Nur Mittel des Mini-Renderers der Rechtliches-Seite
    (`##`/`###`, Absätze, `-`-Listen, `**fett**`, `---`): keine Backticks, keine Links, keine
    Tabellen. Jeder Absatz steht in EINER Zeile."""
    z: list[str] = []
    z.append("## Drittanbieter-Lizenzen")
    z.append("")
    z.append(
        "Diese Software verwendet Open-Source-Bestandteile. Für jeden gilt seine eigene Lizenz. "
        "Die Installation lädt die Pakete in genau "
        "diesen Versionen aus den öffentlichen Paketverzeichnissen PyPI und npm. Den vollständigen "
        "Wortlaut aller Lizenzen zeigt „Lizenztexte anzeigen“ unten. Im Programmordner steht er in der "
        "Datei frontend/src/rechtliches/drittlizenzen_texte.txt."
    )
    for titel, pakete in (
        (_H_PY_DIREKT, b.python_direkt),
        (_H_PY_MIT, b.python_mit),
        (_H_NPM_DIREKT, b.npm_direkt),
        (_H_NPM_MIT, b.npm_mit),
    ):
        z += ["", f"### {titel}", ""]
        z += [_paketzeile(p) for p in pakete]

    weitere = b.bau_gesamt - len(b.bau_direkt)
    zaehl = ", ".join(f"{n} × {k}" for k, n in _zaehlung_sortiert(b.bau_zaehlung))
    z += ["", f"### {_H_BAU}", ""]
    z += [f"- **{n}** {v} — {k}" for n, v, k in b.bau_direkt]
    z += [
        "",
        f"Dazu kommen {weitere} weitere Werkzeuge, die diese mitbringen. Sie laufen nur beim Bauen und "
        f"sind nicht Teil der fertigen Oberfläche. Lizenzen aller {b.bau_gesamt}: {zaehl}.",
    ]

    z += ["", f"### {_H_PROGRAMME}", ""]
    z += [f"- **{n}** — {lizenz} — {zweck}" for n, lizenz, zweck in PROGRAMME]
    z += [
        "",
        "Sie sind nicht Bestandteil dieser Software. Das BMS ruft sie als eigenständige Programme auf.",
    ]

    z += [
        "",
        f"### {_H_DIENSTE}",
        "",
        "Diese Dienste sind keine Bestandteile dieser Software. Ihre Nutzung unterliegt den Bedingungen "
        "des jeweiligen Anbieters, s. Datenschutzerklärung.",
        "",
    ]
    z += [f"- {d}" for d in DIENSTE]
    z += ["", "---", "", "Diese Übersicht wird aus den Paketlisten des Programms erzeugt."]

    text = "\n".join(z) + "\n"
    _renderer_tauglich(text)
    return text


def _renderer_tauglich(text: str) -> None:
    """Der Mini-Renderer kann nur das Wenige (s. `uebersicht_erzeugen`). Kommt durch einen
    Paketnamen oder einen Zweck etwas anderes hinein, bricht der Generator ab, statt eine Seite
    mit rohem Markdown auszuliefern."""
    for nr, zeile in enumerate(text.split("\n"), 1):
        if "`" in zeile or "](" in zeile or zeile.lstrip().startswith(("|", ">")):
            raise GeneratorFehler(
                f"Die Übersicht enthält in Zeile {nr} etwas, das der Mini-Renderer der Rechtliches-Seite "
                f"nicht kann (Backtick, Link, Tabelle oder Zitat): {zeile[:80]!r}. "
                f"→ Den Namen oder den Zweck in backend/pipeline/drittlizenzen.py anpassen."
            )


def texte_erzeugen(b: Bestand) -> str:
    """Der Wortlaut `drittlizenzen_texte.txt`. Gleiche (angeglichene) Texte stehen einmal, mit allen
    Paketen. Blöcke nach dem ersten Paket sortiert (casefold), innerhalb eines Pakets nach Pfad."""
    gruppen: dict[str, list[tuple[Paket, Lizenzdatei]]] = {}
    for p in b.python_direkt + b.python_mit + b.npm_direkt + b.npm_mit:
        for d in p.dateien:
            gruppen.setdefault(d.text, []).append((p, d))

    bloecke = []
    for text, mitglieder in gruppen.items():
        mitglieder.sort(key=lambda t: (_casefold_key(t[0].name), t[0].art, t[0].version, t[1].pfad))
        erstes_paket, erste_datei = mitglieder[0]
        pakete: list[str] = []
        for p, _ in mitglieder:
            kopf = f"{p.name} {p.version} ({p.art})"
            if kopf not in pakete:
                pakete.append(kopf)
        sortschluessel = (_casefold_key(erstes_paket.name), erstes_paket.art, erste_datei.pfad)
        block = "\n".join([
            _TRENNLINIE,
            "Gilt für: " + ", ".join(pakete),
            f"Datei: {erste_datei.name}",
            _TRENNLINIE,
            text if text.endswith("\n") else text + "\n",
        ])
        bloecke.append((sortschluessel, block))
    bloecke.sort(key=lambda t: t[0])

    kopf = (
        "Lizenztexte der Open-Source-Bestandteile\n\n"
        "Der Wortlaut steht unverändert so, wie ihn die Pakete mitbringen. Pakete mit gleichem "
        "Wortlaut stehen in einem Block.\n\n"
    )
    return (kopf + "\n".join(b for _, b in bloecke)).rstrip("\n") + "\n"


def erzeugen(projekt_root: Path, node_modules: Path, site_pfad: list | None = None) -> tuple[str, str]:
    """Liefert (Übersicht, Texte) als Text. Schreibt nichts."""
    bestand = sammeln(projekt_root, node_modules, site_pfad)
    return uebersicht_erzeugen(bestand), texte_erzeugen(bestand)


# ── Wache: reine Prüffunktionen (ohne venv-Metadaten und ohne node_modules) ───────────────────

def bestand_soll(projekt_root: Path) -> dict:
    """Der Soll-Bestand allein aus Lockfiles, `pyproject.toml` und `package.json`.

    Schlüssel: python_direkt, python_mit, npm_direkt, npm_mit (je sortierte Liste von
    (Name, Version)), bau_direkt (Liste (Name, Version)), kennungen (Abschnitt -> {Name: Kennung},
    nur npm und Bauwerkzeuge, denn Python-Kennungen stehen nur in den venv-Metadaten),
    bau_zaehlung ({Kennung: Anzahl}), bau_gesamt, texte (Liste (Name, Version, Art), jedes Paket,
    das einen Wortlaut bekommt)."""
    root = Path(projekt_root)
    lock_py = _lockfile_python(root)
    direkte = {norm_name(n) for n in _direkte_python(root)}
    lock_namen = {norm_name(n) for n, _ in lock_py}
    fehlend = sorted(direkte - lock_namen)
    if fehlend:
        raise GeneratorFehler(
            f"Direkte Pakete aus backend/pyproject.toml fehlen im Lockfile: {', '.join(fehlend)}."
        )
    py_direkt = sorted([(n, v) for n, v in lock_py if norm_name(n) in direkte], key=lambda t: t[0].casefold())
    py_mit = sorted([(n, v) for n, v in lock_py if norm_name(n) not in direkte], key=lambda t: t[0].casefold())

    pj = _package_json(root)
    npm_direkte = set(pj.get("dependencies", {}))
    produktiv, dev = _lockfile_npm(root)
    npm_direkt = sorted([(n, v) for n, v, _, _ in produktiv if n in npm_direkte], key=lambda t: t[0].casefold())
    npm_mit = sorted([(n, v) for n, v, _, _ in produktiv if n not in npm_direkte], key=lambda t: t[0].casefold())
    dev_nach_name = {n: (v, k) for n, v, k in dev}
    bau_namen = sorted(pj.get("devDependencies", {}), key=str.casefold)
    bau_direkt = [(n, dev_nach_name[n][0]) for n in bau_namen if n in dev_nach_name]

    kennungen = {
        "npm_direkt": {n: k or _OHNE_ANGABE for n, v, k, _ in produktiv if n in npm_direkte},
        "npm_mit": {n: k or _OHNE_ANGABE for n, v, k, _ in produktiv if n not in npm_direkte},
        "bau_direkt": {n: dev_nach_name[n][1] or _OHNE_ANGABE for n in bau_namen if n in dev_nach_name},
    }
    zaehlung = Counter((k or _OHNE_ANGABE) for _, _, k in dev)
    texte = sorted(
        [(n, v, "Python") for n, v in py_direkt + py_mit] + [(n, v, "Oberfläche") for n, v in npm_direkt + npm_mit],
        key=lambda t: (t[0].casefold(), t[2]),
    )
    return {
        "python_direkt": py_direkt,
        "python_mit": py_mit,
        "npm_direkt": npm_direkt,
        "npm_mit": npm_mit,
        "bau_direkt": bau_direkt,
        "kennungen": kennungen,
        "bau_zaehlung": dict(zaehlung),
        "bau_gesamt": len(dev),
        "texte": texte,
    }


_PAKETZEILE_RE = re.compile(r"^- \*\*(.+?)\*\* (\S+) — (.+?)(?: — (.+))?$")
_BAU_WEITERE_RE = re.compile(r"Dazu kommen (\d+) weitere Werkzeuge")
_BAU_ZAEHLUNG_RE = re.compile(r"Lizenzen aller (\d+): (.+?)\.?$")
_KOPF_RE = re.compile(
    r"^" + re.escape(_TRENNLINIE) + r"\nGilt für: (.+)\nDatei: (.+)\n" + re.escape(_TRENNLINIE) + r"$",
    re.MULTILINE,
)
_GILT_FUER_RE = re.compile(r"^(.+) (\S+) \((Python|Oberfläche)\)$")


def bestand_ist(md_text: str, txt_text: str) -> dict:
    """Liest den Bestand der erzeugten Dateien: die Paketzeilen der Übersicht (Abschnitt für
    Abschnitt) und die `Gilt für`-Zeilen der Texte. Gleiche Schlüssel wie `bestand_soll`, dazu
    `bloecke` (Anzahl der Blöcke in der Texte-Datei). `kennungen` enthält hier alle Abschnitte,
    auch die Python-Pakete."""
    ist = {
        "python_direkt": [], "python_mit": [], "npm_direkt": [], "npm_mit": [], "bau_direkt": [],
        "kennungen": {k: {} for k in _ANZEIGE_ABSCHNITT},
        "bau_zaehlung": {}, "bau_gesamt": 0, "texte": [], "bloecke": 0,
    }
    aktuell = None
    weitere = None
    for zeile in md_text.replace("\r\n", "\n").split("\n"):
        if zeile.startswith("### "):
            aktuell = _ABSCHNITT_ZU_SCHLUESSEL.get(zeile[4:].strip())
            continue
        if aktuell is None:
            continue
        treffer = _PAKETZEILE_RE.match(zeile)
        if treffer:
            name, version, kennung = treffer.group(1), treffer.group(2), treffer.group(3)
            ist[aktuell].append((name, version))
            ist["kennungen"][aktuell][name] = kennung
            continue
        if aktuell == "bau_direkt":
            m = _BAU_WEITERE_RE.search(zeile)
            if m:
                weitere = int(m.group(1))
            m = _BAU_ZAEHLUNG_RE.search(zeile)
            if m:
                ist["bau_gesamt"] = int(m.group(1))
                for teil in m.group(2).split(", "):
                    anz, _, kennung = teil.partition(" × ")
                    if anz.strip().isdigit() and kennung:
                        ist["bau_zaehlung"][kennung.strip()] = int(anz)
    for k in ("python_direkt", "python_mit", "npm_direkt", "npm_mit", "bau_direkt"):
        ist[k] = sorted(ist[k], key=lambda t: t[0].casefold())
    ist["bau_weitere"] = weitere

    texte = []
    for treffer in _KOPF_RE.finditer(txt_text.replace("\r\n", "\n")):
        ist["bloecke"] += 1
        for teil in treffer.group(1).split(", "):
            m = _GILT_FUER_RE.match(teil)
            if m:
                texte.append((m.group(1), m.group(2), m.group(3)))
    ist["texte"] = sorted(set(texte), key=lambda t: (t[0].casefold(), t[2]))
    return ist


def _vergleich_paare(titel: str, soll: list, ist: list, py: bool = False) -> list[str]:
    """Abweichungen zwischen zwei Listen von (Name, Version). Verglichen wird bei Python-Namen nach
    PEP 503, sonst exakt."""
    schluessel = norm_name if py else (lambda n: n)
    s = {schluessel(n): (n, v) for n, v in soll}
    i = {schluessel(n): (n, v) for n, v in ist}
    meldungen = []
    for k in sorted(s, key=str.casefold):
        if k not in i:
            meldungen.append(f"{titel}: {s[k][0]} {s[k][1]} fehlt in der Übersicht.")
        elif s[k][1] != i[k][1]:
            meldungen.append(
                f"{titel}: {s[k][0]} steht in Version {i[k][1]} in der Übersicht, das Lockfile nennt {s[k][1]}."
            )
    for k in sorted(i, key=str.casefold):
        if k not in s:
            meldungen.append(
                f"{titel}: {i[k][0]} {i[k][1]} steht in der Übersicht, kommt aber im Lockfile dort nicht mehr vor."
            )
    return meldungen


def abweichungen(soll: dict, ist: dict) -> list[str]:
    """Vergleicht Soll (Lockfiles) und Ist (erzeugte Dateien). Je Abweichung eine deutsche Meldung;
    eine leere Liste heißt: Seite und Lockfiles passen zusammen."""
    meldungen: list[str] = []
    for schluessel in ("python_direkt", "python_mit", "npm_direkt", "npm_mit", "bau_direkt"):
        meldungen += _vergleich_paare(
            _ANZEIGE_ABSCHNITT[schluessel], soll[schluessel], ist[schluessel], py=schluessel.startswith("python")
        )
    for schluessel, soll_k in soll.get("kennungen", {}).items():
        ist_k = ist.get("kennungen", {}).get(schluessel, {})
        for name in sorted(soll_k, key=str.casefold):
            if name in ist_k and ist_k[name] != soll_k[name]:
                meldungen.append(
                    f"{_ANZEIGE_ABSCHNITT[schluessel]}: Lizenz von {name} ist {soll_k[name]} im Lockfile, "
                    f"die Übersicht nennt {ist_k[name]}."
                )
    if soll["bau_zaehlung"] != ist["bau_zaehlung"] or soll["bau_gesamt"] != ist["bau_gesamt"]:
        meldungen.append(
            f"{_H_BAU}: Zählung der Bauwerkzeuge weicht ab (Lockfile: {soll['bau_gesamt']} Einträge, "
            f"{_zaehlung_text(soll['bau_zaehlung'])}; Übersicht: {ist['bau_gesamt']} Einträge, "
            f"{_zaehlung_text(ist['bau_zaehlung'])})."
        )
    soll_t = {(n, v, a) for n, v, a in soll["texte"]}
    ist_t = set(ist["texte"])
    for n, v, a in sorted(soll_t - ist_t, key=lambda t: (t[0].casefold(), t[2])):
        andere = [x for x in ist_t if x[0] == n and x[2] == a]
        if andere:
            meldungen.append(
                f"Lizenztexte: {n} ({a}) steht dort in Version {andere[0][1]}, das Lockfile nennt {v}."
            )
        else:
            meldungen.append(f"Lizenztexte: {n} {v} ({a}) fehlt in den Lizenztexten.")
    soll_namen = {(n, a) for n, _, a in soll_t}
    for n, v, a in sorted(ist_t - soll_t, key=lambda t: (t[0].casefold(), t[2])):
        if (n, a) not in soll_namen:
            meldungen.append(f"Lizenztexte: {n} {v} ({a}) steht dort, kommt aber im Lockfile nicht mehr vor.")
    return meldungen


def _zaehlung_text(zaehlung: dict[str, int]) -> str:
    return ", ".join(f"{n} × {k}" for k, n in _zaehlung_sortiert(zaehlung)) or "leer"


# ── CLI ────────────────────────────────────────────────────────────────────────────────────

def _rel(pfad: Path, root: Path) -> str:
    try:
        return pfad.relative_to(root).as_posix()
    except ValueError:
        return pfad.name


def main(argv=None, *, projekt_root: Path | None = None, site_pfad: list | None = None) -> int:
    """`projekt_root` und `site_pfad` sind für die Tests (Fake-Bestand in tmp_path); auf der
    Kommandozeile gelten Projektwurzel und venv."""
    ap = argparse.ArgumentParser(prog="pipeline.drittlizenzen", description=__doc__.split("\n")[0])
    ap.add_argument("--pruefen", action="store_true",
                    help="nur vergleichen (nichts schreiben); Exit 1, wenn eine Datei veraltet ist")
    ap.add_argument("--node-modules", default=str(STANDARD_NODE_MODULES), metavar="DIR",
                    help="Ordner node_modules des Build-Spiegels (Vorgabe: ~/.bewerbung_mgmt_node/"
                         "frontend_build/node_modules)")
    args = ap.parse_args(argv)
    root = Path(projekt_root) if projekt_root else PROJECT_ROOT
    ziele = [(root / ZIEL_MD, ZIEL_MD), (root / ZIEL_TXT, ZIEL_TXT), (root / ZIEL_MD_EN, ZIEL_MD_EN)]

    try:
        md, txt = erzeugen(root, Path(args.node_modules), site_pfad)
    except GeneratorFehler as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 2

    inhalte = [md.encode("utf-8"), txt.encode("utf-8"), uebersicht_englisch(md).encode("utf-8")]
    if args.pruefen:
        veraltet = []
        for (pfad, rel), soll in zip(ziele, inhalte):
            if not pfad.is_file():
                veraltet.append(f"{rel}: fehlt")
            elif pfad.read_bytes() != soll:
                veraltet.append(f"{rel}: veraltet")
        for v in veraltet:
            print(v)
        if veraltet:
            print("→ scripts/drittlizenzen.sh ausführen und das Ergebnis committen.")
            return 1
        print("Alles aktuell (3 Dateien geprüft).")
        return 0

    for (pfad, rel), inhalt in zip(ziele, inhalte):
        if pfad.is_file() and pfad.read_bytes() == inhalt:
            print(f"unverändert: {rel}")
            continue
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_bytes(inhalt)
        print(f"geschrieben: {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
