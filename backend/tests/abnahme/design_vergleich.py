#!/usr/bin/env python3
"""Vergleichswerkzeug für die Abnahme von P2-72 „Design aus einer Quelle“ (Paket V).

ZWECK: Beweisen, dass ein großer Umbau am Design nichts Sichtbares ändert. Das Werkzeug stellt zwei
Stände des Programms nebeneinander, erzeugt von beiden dieselben Seiten und Berichte und meldet
jeden Unterschied. Es liegt unter `backend/tests/` und gehört damit nicht zum Kundenpaket
(`pipeline/kundenpaket.py`, Ausschluss `backend/tests/`); pytest sammelt es nicht ein (Name ohne
`test_`, kein `__init__.py`).

AUFRUF (mit dem Python der BMS-Umgebung, aus beliebigem Ordner):

    ~/.bewerbung_mgmt_venv/bin/python backend/tests/abnahme/design_vergleich.py \\
        --alt outputs/kundenpaket/BMS_<Version>.zip --neu arbeitsbaum --ausgabe /tmp/vergleich

    --alt, --neu   ein Kundenpaket (ZIP), ein Ordner mit dem Programm oder `arbeitsbaum`
                   (nur --neu und --alt: die von Git verfolgten Dateien des Projekts plus neue,
                   nicht ignorierte Dateien, ohne data/, outputs/ und config/profil.md)
    --ausgabe      Ordner für Bildschirmfotos, Berichte, Differenzbilder und `bericht.md`
    --design       eine design.json, oder `probe` für das eingebaute Probe-Design (auffällig andere
                   Farben, anderes Icon; der Produktname bleibt fest; die Farbpaare erfüllen die Kontrastprüfung).
                   Die Datei wird als `data/design/design.json` in den Datenordner des NEUEN Stands
                   gelegt (PNG-Dateien daneben kommen mit). Der Stand 1.7.0 kennt das nicht und
                   ignoriert die Datei. Mit Design ist jeder Unterschied zum alten Stand erwartet;
                   geprüft wird, dass die Seiten sich ändern, die Zustandsfarben nicht (Diffbilder).
    --nur          `oberflaeche` oder `berichte` (Vorgabe: beides)
    --scratch      Arbeitsordner außerhalb des Projekts (Vorgabe: <TMP>/bms_design_vergleich)
    --port-alt/--port-neu   Anfangswerte für freie Ports (Vorgabe 18801/18802, nie 8000)
    --behalten     den Arbeitsordner des Laufs nicht löschen

EXIT-CODE: 0 = alles gleich, 1 = Unterschiede, 2 = das Werkzeug konnte nicht laufen.

ABLAUF
 1. Je Stand eine Probe-Installation: Programm entpacken oder kopieren, die Oberfläche im Spiegel
    bauen (rsync ohne node_modules/dist, node_modules als APFS-Klon von
    ~/.bewerbung_mgmt_node/frontend_build, `tsc --noEmit`, `vite build`), das gebaute `dist` kommt
    in die Probe.
 2. Der erste Stand erzeugt die Beispieldaten, wird beendet; Datenordner und die dabei neu
    entstandenen Laufzeitdateien (z. B. config/suchprofile.yaml) sind die gemeinsame Basis. Beide
    Stände bekommen DIESELBE Kopie davon.
 3. Jeder Stand wird nacheinander am SELBEN Pfad installiert (`<lauf>/BMS`), mit denselben Ordnern
    für Secrets, Logs und Home. Grund: Die Einstellungen zeigen Installations- und Datenordner;
    zwei verschiedene Pfade wären ein Scheinunterschied in jedem Bildschirmfoto. Ports: je Stand
    ein eigener freier Port (nie 8000), die Oberfläche zeigt ihn nirgends.
 4. Start über das Probeserver-Muster: Ein kleiner Wrapper startet `app.main` auf dem Port des Stands.
    Der Server bekommt nur eine bereinigte Umgebung (kein Zugriff auf das echte Home, keine fremden
    Schlüssel in der Umgebung). Den ersten Sicherungstakt schiebt der Wrapper weit hinaus, damit
    keine Sicherung zufällig in einen Lauf fällt. Seit P2-82 gibt es keine Lizenzpflicht mehr: Das
    Werkzeug legt keine Lizenzdatei an und vergleicht nur Stände ohne Lizenzpflicht (Stände bis 1.7.0
    sperren das Schreiben ohne Lizenz und lassen sich damit nicht mehr bespielen).
 5. Oberfläche: Google Chrome ohne Fenster (eigenes Profil im Arbeitsordner, ein Start je Stand),
    ferngesteuert über das DevTools-Protokoll (siehe unten), je Seite zwei Fenstergrößen
    (1440x900, 390x844), ganze Seitenhöhe, danach Titel und Symbole des Browser-Tabs (mit
    Prüfsumme der Bilddatei). Zusätzlich das gebaute CSS. Chrome läuft unter `sandbox-exec` mit
    einer Netzsperre (ausgehend nur localhost; fängt auch den Google-Updater ab, den Chrome beim
    Start anstößt) und mit `--use-mock-keychain`: Ohne diesen Schalter blieb die erste Navigation
    gelegentlich für Minuten im Schlüsselbund-Zugriff hängen.
 6. Berichte: Ein eigener Prozess (Programmordner und Datenordner der Probe) erzeugt aus festen,
    erfundenen Eingaben je einen Bericht jeder Art. Zeitangaben werden maskiert (Liste unten), die
    maskierte Fassung wird verglichen und als Bildschirmfoto aufgenommen.
 7. Vergleich: Bilder bildpunktgenau (PNG mit zlib dekodiert, kein Fremdpaket), Texte als
    Zeilen-Diff, CSS zusätzlich nach dem Auflösen von var(--…) gegen `:root`-Blöcke und ein
    CSS-Block des Stands (`/api/design.css`, falls es ihn gibt), Farben in eine Schreibweise
    gebracht (`rgb(var(--x) / .5)` und `rgb(11 31 58 / .5)` gelten bei `--x: 11 31 58` als gleich).

WARUM DEVTOOLS-PROTOKOLL STATT `--screenshot`: Die Kommandozeilenoption fotografiert nur den
sichtbaren Ausschnitt und wartet nach fester Zeit (`--virtual-time-budget` zählt keine
Netzwerkzeit verlässlich). Das Protokoll (WebSocket auf 127.0.0.1, selbst geschriebener Client aus
der Standardbibliothek) erlaubt: das Ende der Ladevorgänge zu erkennen (abgefangene fetch-/XHR-
Aufrufe, Ruhe im DOM, Schriften geladen), Animationen und den Textcursor abzuschalten, die ganze
Seitenhöhe aufzunehmen und Titel/Symbole der Seite auszulesen.

MASKEN (vor dem Vergleich in beiden Ausgaben gleich angewendet, Treffer stehen in bericht.md):
  M1 „erzeugt am <Datum> <Uhrzeit>“ (ISO oder deutsch) -> „erzeugt am ‹ZEITPUNKT›“
     (Snapshot, Transkript, Cleanup, Beirat)
  M2 „Stand <TT.MM.JJJJ> <Uhrzeit>“ der Coach-Site -> „Stand ‹ZEITPUNKT›“
  M3 das Tagesdatum des Erzeugerlaufs (ISO, deutsch, ohne Trenner) -> ‹HEUTE›
     (Company-Fit „erzeugt am“, Digest, Datum-Felder, Excel J2)
  M4 Excel: `dcterms:created/modified` in docProps/core.xml -> ‹ZEITPUNKT›
Alles andere in den Berichten ist von der Uhr unabhängig (feste Eingaben, feste Datenbasis).

BEKANNTE UNSCHÄRFEN (siehe auch bericht.md, Abschnitt „Grenzen“):
  * Läuft ein Vergleich über Mitternacht, stimmt das Tagesdatum der beiden Stände nicht mehr.
  * Schriftdarstellung ist nur auf demselben Rechner und mit derselben Chrome-Version vergleichbar.
  * Bildschirmfotos decken nur die aufgenommenen Seiten und Zustände ab (keine geöffneten Menüs,
    keine Formulareingaben, kein Zeigerzustand).
"""
from __future__ import annotations

import argparse
import atexit
import base64
import concurrent.futures
import difflib
import fnmatch
import hashlib
import http.client
import io
import itertools
import json
import operator
import os
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import zipfile
import zlib
from datetime import date, datetime
from pathlib import Path

# ── Konstanten ──────────────────────────────────────────────────────────────────────────────
PROJEKT_STANDARD = Path(__file__).resolve().parents[3]       # …/Bewerbung_Mgmt_System
VENV_PYTHON = Path.home() / ".bewerbung_mgmt_venv" / "bin" / "python"
NODE_MODULES_QUELLE = Path.home() / ".bewerbung_mgmt_node" / "frontend_build" / "node_modules"
NODE_PAKETE_QUELLE = NODE_MODULES_QUELLE.parent
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")
# Netzsperre für Chrome und alles, was Chrome startet (auch der Google-Updater, den Chrome beim Start
# anstößt): ausgehend ist nur localhost erlaubt. Chrome bekommt dafür --no-sandbox (verschachtelte
# Seatbelt-Profile gehen auf macOS nicht); es lädt nur eigene Seiten und selbst erzeugte Berichte.
NETZSPERRE = ('(version 1)(allow default)(deny network-outbound)'
              '(allow network-outbound (remote ip "localhost:*"))(allow network-outbound (remote unix-socket))')

# Fenstergrößen: (Breite, Höhe, Kürzel im Dateinamen)
FENSTER = ((1440, 900, "1440"), (390, 844, "390"))
MAX_SEITENHOEHE = 12000          # höhere Seiten werden abgeschnitten (und gemeldet)
STABIL_RUHE_MS = 600             # so lange darf weder ein fetch enden noch das DOM sich ändern
SEITE_TIMEOUT_S = 45

# Auszuschließen beim Kopieren eines Ordners oder des Arbeitsbaums. Nichts davon wird gelesen.
AUSSCHLUSS_PRAEFIX = (
    "data/", "outputs/", "cv/", "tasks/", ".git/", ".git.nosync/", ".github/", "backend/tests/",
    ".claude/worktrees/", "frontend/node_modules/", "frontend/dist/", "node_modules/",
    "automation/agent.env",
)
AUSSCHLUSS_DATEIEN = {
    "config/profil.md", "config/zielfirmen.md", "config/suchprofile.yaml", "config/budgets.yaml",
    ".claude/launch.json", ".claude/settings.local.json", ".DS_Store", ".env", ".gitleaks.toml",
}
AUSSCHLUSS_MUSTER = ("*/__pycache__/*", "*.pyc", "*.sqlite", "*.sqlite-wal", "*.sqlite-shm",
                     "config/*_backup_*.yaml", "*/.DS_Store", "_tmp_*", ".tmp_*", ".verify*")
# Wie das Kundenpaket: aus docs/ nur diese Dokumente (sonst hätte die Doku-Seite des Arbeitsbaums
# interne Reiter, die das Paket nicht hat).
DOKU_ERLAUBT = {"ANLEITUNG", "ANLEITUNG_COACH_SITE", "BEIRAT-CHARTA", "BEIRAT-PERSONA-TEMPLATE",
                "FUNKTIONEN", "SETUP-EMAIL", "SETUP-WINDOWS"}

# Zahl der Zeilen, die ein Textunterschied in bericht.md höchstens zeigt (vollständig in diff/).
BERICHT_DIFF_ZEILEN = 24
AUSGABE_MARKE = ".design_vergleich_ausgabe"


def log(text: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


class WerkzeugFehler(Exception):
    """Das Werkzeug konnte nicht laufen (Exit-Code 2) — kein Unterschied zwischen den Ständen."""


# ── Prozessverwaltung ───────────────────────────────────────────────────────────────────────
# Das Werkzeug beendet nur Prozesse, die es selbst gestartet hat, über ihre PID (und, für Chrome,
# über die eigene Prozessgruppe: Jeder Prozess startet mit `start_new_session=True`, die Gruppe
# trägt also die PID des Kindes und enthält nur dessen Nachkommen).
_PROZESSE: list = []
_PROZESS_SPERRE = threading.Lock()


def prozess_starten(args, *, env, cwd=None, logdatei: Path | None = None):
    if logdatei:
        logdatei.parent.mkdir(parents=True, exist_ok=True)
    ziel = open(logdatei, "ab") if logdatei else subprocess.DEVNULL
    try:
        p = subprocess.Popen([str(a) for a in args], env=env, cwd=cwd, stdin=subprocess.DEVNULL,
                             stdout=ziel, stderr=subprocess.STDOUT, start_new_session=True)
    finally:
        if logdatei:
            ziel.close()
    with _PROZESS_SPERRE:
        _PROZESSE.append(p)
    return p


def _gruppe_signalisieren(p, sig) -> None:
    """Signal an die EIGENE Prozessgruppe (nur wenn sie wirklich die des Kindes ist), sonst nur an
    die PID."""
    try:
        if os.getpgid(p.pid) == p.pid:
            os.killpg(p.pid, sig)
        else:
            os.kill(p.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def prozess_beenden(p, schonfrist: float = 8.0) -> None:
    if p is None:
        return
    if p.poll() is None:
        _gruppe_signalisieren(p, signal.SIGTERM)
        try:
            p.wait(timeout=schonfrist)
        except subprocess.TimeoutExpired:
            _gruppe_signalisieren(p, signal.SIGKILL)
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
    # Nachzügler der eigenen Gruppe (Chrome-Hilfsprozesse) einsammeln.
    try:
        os.killpg(p.pid, 0)
    except (ProcessLookupError, PermissionError):
        pass
    else:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    with _PROZESS_SPERRE:
        if p in _PROZESSE:
            _PROZESSE.remove(p)


def alle_prozesse_beenden() -> None:
    with _PROZESS_SPERRE:
        rest = list(_PROZESSE)
    for p in rest:
        prozess_beenden(p, schonfrist=3.0)


def _abbruch(signum, _rahmen) -> None:
    alle_prozesse_beenden()
    raise SystemExit(130 if signum == signal.SIGINT else 143)


def port_frei(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    # Zusätzlich: Antwortet dort schon jemand? (bind allein sieht fremde Lauscher nicht immer)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) != 0


def freier_port(ab: int, verboten=(8000,)) -> int:
    for port in range(ab, ab + 200):
        if port in verboten or port == 8000:
            continue
        if port_frei(port):
            return port
    raise WerkzeugFehler(f"Kein freier Port ab {ab} gefunden.")


# ── Stände: entpacken, kopieren, bauen ──────────────────────────────────────────────────────
class Stand:
    """Ein Stand des Programms (alt oder neu) samt seiner Probe-Vorbereitung."""

    def __init__(self, name: str, quelle: str, lauf: "Lauf", port: int):
        self.name = name
        self.quelle = quelle
        self.lauf = lauf
        self.port = port
        self.wurzel = lauf.arbeit / f"stand_{name}"
        self.programm = self.wurzel / "programm"
        self.bau = self.wurzel / "bau"
        self.art = ""
        self.beschreibung = ""
        self.version = ""
        self.dateien = 0
        self.schritte: list = []          # (Name, Sekunden)
        self.warnungen: list = []
        self.tsc_ok = None
        self.netzsperre = None
        self.tsc_ausgabe = ""
        self.hinweise: list = []

    def zeit(self, name: str, start: float) -> None:
        self.schritte.append((name, round(time.time() - start, 1)))


def _ausgeschlossen(rel: str, ordner: bool = False) -> bool:
    """Gehört die Datei (oder, mit `ordner=True`, der Ordner) NICHT in die Probe? Die docs-Positivliste
    gilt nur für Dateien: Der Ordner docs/ selbst muss betreten werden."""
    if rel in AUSSCHLUSS_DATEIEN or any(rel.startswith(p) for p in AUSSCHLUSS_PRAEFIX):
        return True
    if any(fnmatch.fnmatch(rel, m) for m in AUSSCHLUSS_MUSTER):
        return True
    if not ordner and rel.startswith("docs/"):
        name = rel[len("docs/"):]
        stamm, _, endung = name.rpartition(".")
        if "/" in name or endung not in ("md", "html") or stamm not in DOKU_ERLAUBT:
            return True
    return False


def _git(projekt: Path, *args: str, binaer: bool = False):
    erg = subprocess.run(["git", "-C", str(projekt), *args], capture_output=True, timeout=60)
    if erg.returncode != 0:
        raise WerkzeugFehler(f"git {' '.join(args)} fehlgeschlagen: {erg.stderr.decode('utf-8', 'replace')[:300]}")
    return erg.stdout if binaer else erg.stdout.decode("utf-8", "replace").strip()


def zip_entpacken(zip_pfad: Path, ziel: Path) -> int:
    """Entpackt das Paket in einen NEUEN, leeren Ordner. Prüft jeden Pfad, bevor er geschrieben wird."""
    ziel.mkdir(parents=True, exist_ok=False)
    anzahl = 0
    with zipfile.ZipFile(zip_pfad) as zf:
        namen = [n for n in zf.namelist() if n and not n.endswith("/")]
        spitzen = {n.split("/", 1)[0] for n in namen}
        # Ein einziger Oberordner (z. B. „BMS_1.7.0/“) wird abgestreift, das Paket hat keinen.
        abstreifen = len(spitzen) == 1 and all("/" in n for n in namen) and "backend" not in spitzen
        for info in zf.infolist():
            if info.is_dir():
                continue
            rel = info.filename
            if abstreifen:
                rel = rel.split("/", 1)[1]
            teile = Path(rel).parts
            if rel.startswith("/") or ".." in teile:
                raise WerkzeugFehler(f"Unzulässiger Pfad im ZIP: {info.filename}")
            zielpfad = ziel.joinpath(*teile)
            zielpfad.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as quelle, open(zielpfad, "wb") as ausgabe:
                shutil.copyfileobj(quelle, ausgabe)
            if (info.external_attr >> 16) & 0o111:
                zielpfad.chmod(zielpfad.stat().st_mode | 0o111)
            anzahl += 1
    return anzahl


def baum_kopieren_ordner(quelle: Path, ziel: Path) -> int:
    anzahl = 0
    for wurzel, ordner, dateien in os.walk(quelle):
        rel_ordner = Path(wurzel).relative_to(quelle).as_posix()
        rel_ordner = "" if rel_ordner == "." else rel_ordner
        # Ordner, die nie hineingehören, gar nicht erst betreten (spart auch iCloud-Zugriffe).
        ordner[:] = [o for o in ordner
                     if not _ausgeschlossen(f"{rel_ordner}/{o}/".lstrip("/"), ordner=True)
                     and o not in ("__pycache__", "node_modules")]
        for datei in dateien:
            rel = f"{rel_ordner}/{datei}".lstrip("/")
            if _ausgeschlossen(rel):
                continue
            q = Path(wurzel) / datei
            if q.is_symlink():
                continue
            z = ziel / rel
            z.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(q, z)
            anzahl += 1
    return anzahl


def baum_kopieren_git(projekt: Path, ziel: Path) -> tuple[int, int]:
    """Von Git verfolgte Dateien plus neue, nicht ignorierte Dateien (z. B. ein Modul, das eine
    andere Sitzung gerade neu angelegt hat). Inhalte kommen von der Platte, nicht aus dem Index."""
    verfolgt = _git(projekt, "ls-files", "-z", binaer=True).decode("utf-8").split("\0")
    neu = _git(projekt, "ls-files", "--others", "--exclude-standard", "-z", binaer=True).decode("utf-8").split("\0")
    anzahl = 0
    for rel in [r for r in verfolgt + neu if r]:
        if _ausgeschlossen(rel):
            continue
        q = projekt / rel
        if q.is_symlink() or not q.is_file():
            continue
        z = ziel / rel
        z.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(q, z)
        anzahl += 1
    return anzahl, len([r for r in neu if r and not _ausgeschlossen(r)])


def manifest_nachbauen(projekt: Path, ziel: Path) -> None:
    """Der Arbeitsbaum hat kein `bms_manifest.json`; ohne es hielte `app/version.py` die Probe für
    eine „unbekannte“ Installation und die Einstellungen zeigten andere Texte als beim Paket.
    Version aus VERSION, Commit und Datum von HEAD, Freigabe nur, wenn HEAD das Tag v<Version> trägt."""
    version = (ziel / "VERSION").read_text(encoding="utf-8").strip() if (ziel / "VERSION").is_file() else "0.0.0"
    commit = _git(projekt, "rev-parse", "HEAD")
    datum = _git(projekt, "show", "-s", "--format=%cs", "HEAD")
    try:
        tags = _git(projekt, "tag", "--points-at", "HEAD").split()
    except WerkzeugFehler:
        tags = []
    manifest = {"format": 1, "produkt": "Bewerbungs-Management-System", "version": version,
                "commit": commit, "commit_datum": datum, "freigabe": f"v{version}" in tags,
                "vorschau": False, "dateien": {}, "anpassbar": []}
    (ziel / "bms_manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")


def stand_bereitstellen(stand: Stand, projekt: Path) -> None:
    start = time.time()
    q = stand.quelle
    if q == "arbeitsbaum":
        stand.art = "arbeitsbaum"
        anzahl, neu = baum_kopieren_git(projekt, stand.programm)
        stand.dateien = anzahl
        manifest_nachbauen(projekt, stand.programm)
        stand.beschreibung = f"Arbeitsbaum {projekt} ({anzahl} Dateien, davon {neu} neu und noch nicht in Git)"
        if neu:
            stand.hinweise.append(f"Arbeitsbaum enthält {neu} neue Dateien, die Git noch nicht verfolgt.")
        try:
            geaendert = [z for z in _git(projekt, "status", "--porcelain").splitlines()
                         if not z.startswith("?? backend/tests/abnahme/")]       # das Werkzeug selbst zählt nicht
            stand.hinweise.append(f"Git-Stand: {_git(projekt, 'rev-parse', '--short', 'HEAD')} "
                                  f"({'Arbeitsbaum gleich HEAD' if not geaendert else f'{len(geaendert)} Datei(en) im Arbeitsbaum geändert oder neu'})")
        except WerkzeugFehler:
            pass
    else:
        pfad = Path(q).expanduser()
        if not pfad.exists():
            raise WerkzeugFehler(f"--{stand.name}: {pfad} gibt es nicht.")
        if pfad.is_file() and pfad.suffix.lower() == ".zip":
            stand.art = "zip"
            stand.dateien = zip_entpacken(pfad, stand.programm)
            stand.beschreibung = f"Paket {pfad.name} ({stand.dateien} Dateien)"
        elif pfad.is_dir():
            stand.art = "ordner"
            stand.programm.mkdir(parents=True)
            stand.dateien = baum_kopieren_ordner(pfad, stand.programm)
            stand.beschreibung = f"Ordner {pfad} ({stand.dateien} Dateien)"
        else:
            raise WerkzeugFehler(f"--{stand.name}: {pfad} ist weder ZIP noch Ordner.")
    for pflicht in ("backend/run_server.py", "frontend/package.json", "frontend/index.html"):
        if not (stand.programm / pflicht).is_file():
            raise WerkzeugFehler(f"Stand {stand.name}: {pflicht} fehlt im Programm.")
    v = stand.programm / "VERSION"
    stand.version = v.read_text(encoding="utf-8").strip() if v.is_file() else "unbekannt"
    stand.zeit("Programm bereitstellen", start)


def oberflaeche_bauen(stand: Stand) -> None:
    """Spiegel-Verfahren (spec_p2-69, Leitplanken): Quelle ohne node_modules/dist spiegeln,
    node_modules als APFS-Klon der vorhandenen Installation, Typprüfung, Vite-Bau. Gebaut wird NIE
    im Projekt, `frontend/build.sh` und `npm install` laufen nicht."""
    start = time.time()
    quelle = stand.programm / "frontend"
    if not (NODE_MODULES_QUELLE / ".bin" / "vite").exists():
        raise WerkzeugFehler(f"{NODE_MODULES_QUELLE} fehlt oder ist unvollständig (node_modules der Oberfläche).")
    node = shutil.which("node")
    if not node:
        raise WerkzeugFehler("node nicht gefunden.")
    for datei in ("package.json", "package-lock.json"):
        a, b = quelle / datei, NODE_PAKETE_QUELLE / datei
        if b.is_file() and a.is_file() and a.read_bytes() != b.read_bytes():
            stand.warnungen.append(f"frontend/{datei} dieses Stands weicht vom Stand der vorhandenen "
                                   f"node_modules ({NODE_PAKETE_QUELLE}) ab; der Bau nutzt trotzdem diese.")
    stand.bau.mkdir(parents=True)
    erg = subprocess.run(["rsync", "-a", "--exclude", "node_modules", "--exclude", "dist",
                          f"{quelle}/", f"{stand.bau}/"], capture_output=True)
    if erg.returncode != 0:
        raise WerkzeugFehler(f"rsync fehlgeschlagen: {erg.stderr.decode('utf-8', 'replace')[:300]}")
    erg = subprocess.run(["cp", "-c", "-R", str(NODE_MODULES_QUELLE), str(stand.bau / "node_modules")],
                         capture_output=True)
    if erg.returncode != 0:
        raise WerkzeugFehler(f"node_modules klonen fehlgeschlagen: {erg.stderr.decode('utf-8', 'replace')[:300]}")
    env = {"PATH": f"{Path(node).parent}:/usr/bin:/bin", "HOME": str(stand.lauf.home), "TMPDIR": str(stand.lauf.tmp),
           "CI": "1", "NO_UPDATE_NOTIFIER": "1", "npm_config_offline": "true"}
    tsc = subprocess.run([node, "node_modules/typescript/bin/tsc", "--noEmit", "-p", "."], cwd=stand.bau,
                         env=env, capture_output=True, timeout=300)
    stand.tsc_ok = tsc.returncode == 0
    stand.tsc_ausgabe = (tsc.stdout + tsc.stderr).decode("utf-8", "replace")
    vite = subprocess.run([node, "node_modules/vite/bin/vite.js", "build"], cwd=stand.bau, env=env,
                          capture_output=True, timeout=300)
    (stand.wurzel / "vite.log").write_bytes(vite.stdout + vite.stderr)
    if vite.returncode != 0:
        raise WerkzeugFehler(f"vite build ({stand.name}) fehlgeschlagen:\n"
                             + (vite.stdout + vite.stderr).decode("utf-8", "replace")[-1500:])
    if not (stand.bau / "dist" / "index.html").is_file():
        raise WerkzeugFehler(f"vite build ({stand.name}) hat kein dist/index.html erzeugt.")
    shutil.copytree(stand.bau / "dist", stand.programm / "frontend" / "dist")
    stand.zeit("Oberfläche bauen (rsync, node_modules klonen, tsc, vite)", start)


# ── Lauf: Ordner ────────────────────────────────────────────────────────────────────────────
class Lauf:
    """Ein Lauf des Werkzeugs: alle Pfade im Scratch-Ordner."""

    def __init__(self, scratch: Path, ausgabe: Path):
        stempel = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.arbeit = scratch / f"lauf_{stempel}_{os.getpid()}"
        self.ausgabe = ausgabe
        self.kanon = self.arbeit / "BMS"                  # der gemeinsame Installationspfad
        self.secrets = self.arbeit / "secrets"
        self.logs = self.arbeit / "logs"
        self.home = self.arbeit / "home"
        self.tmp = self.arbeit / "tmp"
        self.basis = self.arbeit / "basis"                # Daten + Laufzeitdateien aus dem Erstlauf
        self.werkzeug = self.arbeit / "werkzeug"
        self.basis_dateien: list = []
        for p in (self.arbeit, self.home, self.tmp, self.werkzeug):
            p.mkdir(parents=True, exist_ok=True)

    def umgebung(self, **extra) -> dict:
        """Bereinigte Umgebung für Server und Erzeuger: nichts aus der echten Umgebung (Schlüssel,
        Tokens), Home und Temp im Arbeitsordner."""
        env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin",
            "HOME": str(self.home), "TMPDIR": str(self.tmp), "LANG": "de_DE.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1",
            "BMS_DATA_DIR": str(self.kanon / "data"), "BMS_LOG_DIR": str(self.logs),
            "BMS_SECRETS_DIR": str(self.secrets), "BMS_BEISPIELDATEN": "1",
            "VGL_PROGRAMM": str(self.kanon),
        }
        if "TZ" in os.environ:
            env["TZ"] = os.environ["TZ"]
        env.update({k: str(v) for k, v in extra.items()})
        return env


PROBESERVER = '''\
"""Probeserver (P2-72, Paket V): startet den Server des Stands auf dem Port des Laufs."""
import os, sys
prog = os.environ["VGL_PROGRAMM"]
sys.path.insert(0, os.path.join(prog, "backend"))
os.chdir(os.path.join(prog, "backend"))
from app.main import app
try:                      # erste Sicherungsprüfung so weit hinausschieben, dass sie nie in einen Lauf fällt
    from app import sicherung
    sicherung._ERSTE_PRUEFUNG_S = 10 ** 7
except Exception:
    pass
import uvicorn
uvicorn.run(app, host="127.0.0.1", port=int(os.environ["PORT"]), loop="asyncio", http="h11", log_level="warning")
'''


# Eingebautes Probe-Design (`--design probe`): Farben, Name und Icon weichen überall auffällig von der
# Vorgabe ab. Alle Farbpaare erfüllen die Kontrastprüfung des Designs (4,5:1), damit keines still durch
# die Vorgabe ersetzt wird; die Schriften sind die, die die Oberfläche mitbringt.
PROBE_DESIGN = {
    "format": 1, "name": "Probe-Design",
    "farben": {"marke": "#4A1D6B", "auf_marke": "#F3E8FF", "aktion": "#B33C12", "aktion_hover": "#8F2F0E",
               "auf_aktion": "#FFFFFF", "stahl": "#CDB4DB", "flaeche": "#FBF7FF", "karte": "#FFFFFF",
               "rahmen": "#E3D5EF", "spur": "#EFE6F7", "text": "#2B1040", "text_gedaempft": "#6B5A7A",
               "trenner": "#6A3C8C"},
    "schriften": {"ueberschrift": "Montserrat", "text": "Inter"},
    "icon": {"32": "icon-32.png", "180": "icon-180.png"},
}


def probe_design_schreiben(ordner: Path) -> Path:
    """Schreibt das Probe-Design samt zwei quadratischen Icons (orange Fläche, heller Kern) nach `ordner`."""
    ordner.mkdir(parents=True, exist_ok=True)
    for groesse in (32, 180):
        rand = max(2, groesse // 4)
        zeilen = []
        for y in range(groesse):
            zeile = bytearray()
            for x in range(groesse):
                innen = rand <= x < groesse - rand and rand <= y < groesse - rand
                zeile += bytes((255, 235, 200)) if innen else bytes((179, 60, 18))
            zeilen.append(zeile)
        _png_schreiben(ordner / f"icon-{groesse}.png", groesse, groesse, zeilen)
    datei = ordner / "design.json"
    datei.write_text(json.dumps(PROBE_DESIGN, indent=2, ensure_ascii=False), encoding="utf-8")
    return datei


def probeserver_vorbereiten(lauf: Lauf) -> None:
    """Schreibt den Wrapper, der den Server eines Stands startet, in den Werkzeugordner."""
    (lauf.werkzeug / "probeserver.py").write_text(PROBESERVER, encoding="utf-8")


# ── Installation am gemeinsamen Pfad ────────────────────────────────────────────────────────
_BAUM_AUSSER = ("data", "frontend/dist", "__pycache__")


def baum_stand(wurzel: Path) -> dict:
    """{relativer Pfad: Prüfsumme} aller Dateien außer data/, dist und Bytecode — um nach dem
    Erstlauf zu sehen, welche Laufzeitdateien der Start im Programmordner angelegt hat."""
    stand = {}
    for pfad in sorted(wurzel.rglob("*")):
        if not pfad.is_file() or pfad.is_symlink():
            continue
        rel = pfad.relative_to(wurzel).as_posix()
        if rel.split("/", 1)[0] == "data" or rel.startswith("frontend/dist/") or "__pycache__" in rel:
            continue
        stand[rel] = hashlib.sha256(pfad.read_bytes()).hexdigest()
    return stand


def klonen(quelle: Path, ziel: Path) -> None:
    """APFS-Klon (kostet keinen Platz), sonst normale Kopie."""
    erg = subprocess.run(["cp", "-c", "-R", str(quelle), str(ziel)], capture_output=True)
    if erg.returncode != 0:
        if ziel.exists():
            shutil.rmtree(ziel)
        shutil.copytree(quelle, ziel, symlinks=True)


def installieren(stand: Stand, lauf: Lauf, *, mit_basis: bool, design: Path | None = None) -> None:
    """Setzt `<lauf>/BMS` auf den Stand zurück: Programm, frische Ordner für Secrets/Logs/Home,
    optional die gemeinsame Basis (Daten + Laufzeitdateien) und die Design-Überschreibung."""
    if lauf.kanon.exists():
        shutil.rmtree(lauf.kanon)
    klonen(stand.programm, lauf.kanon)
    for p in (lauf.secrets, lauf.logs, lauf.home, lauf.tmp):
        if p.exists():
            shutil.rmtree(p)
        p.mkdir(parents=True)
    lauf.secrets.chmod(0o700)
    if mit_basis:
        shutil.copytree(lauf.basis / "data", lauf.kanon / "data")
        dateien = lauf.basis / "dateien"
        if dateien.is_dir():
            for pfad in dateien.rglob("*"):
                if pfad.is_file():
                    ziel = lauf.kanon / pfad.relative_to(dateien)
                    ziel.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(pfad, ziel)
    if design is not None:
        zielordner = lauf.kanon / "data" / "design"
        zielordner.mkdir(parents=True, exist_ok=True)
        shutil.copy2(design, zielordner / "design.json")
        for png in design.parent.glob("*.png"):
            shutil.copy2(png, zielordner / png.name)


def server_starten(stand: Stand, lauf: Lauf, logdatei: Path):
    env = lauf.umgebung(PORT=stand.port)
    p = prozess_starten([VENV_PYTHON, "-I", lauf.werkzeug / "probeserver.py"], env=env,
                        cwd=str(lauf.kanon / "backend"), logdatei=logdatei)
    ende = time.time() + 120
    while time.time() < ende:
        if p.poll() is not None:
            raise WerkzeugFehler(f"Server ({stand.name}) ist beim Start beendet worden (Exit {p.returncode}):\n"
                                 + logdatei.read_text(encoding="utf-8", errors="replace")[-2000:])
        try:
            status, _ = http_holen(stand.port, "/api/version", timeout=3)
            if status == 200:
                return p
        except OSError:
            pass
        time.sleep(0.4)
    prozess_beenden(p)
    raise WerkzeugFehler(f"Server ({stand.name}) antwortet nach 120 s nicht auf Port {stand.port}.")


def http_holen(port: int, pfad: str, timeout: float = 15):
    """GET auf 127.0.0.1:<port> — der einzige Netzzugriff des Werkzeugs außer dem Chrome-Protokoll."""
    verbindung = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        verbindung.request("GET", pfad)
        antwort = verbindung.getresponse()
        return antwort.status, antwort.read()
    finally:
        verbindung.close()


# ── Chrome über das DevTools-Protokoll ──────────────────────────────────────────────────────
class WebSocket:
    """Minimaler WebSocket-Client (RFC 6455) für 127.0.0.1 — Textrahmen, Fragmente, Ping."""

    def __init__(self, port: int, pfad: str, timeout: float = 60):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        schluessel = base64.b64encode(os.urandom(16)).decode("ascii")
        anfrage = (f"GET {pfad} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\n"
                   f"Connection: Upgrade\r\nSec-WebSocket-Key: {schluessel}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(anfrage.encode("ascii"))
        kopf = b""
        while b"\r\n\r\n" not in kopf:
            stueck = self.sock.recv(4096)
            if not stueck:
                raise WerkzeugFehler("WebSocket: Verbindung beim Handshake geschlossen.")
            kopf += stueck
        kopf, _, rest = kopf.partition(b"\r\n\r\n")
        if b" 101 " not in kopf.split(b"\r\n", 1)[0]:
            raise WerkzeugFehler(f"WebSocket-Handshake abgelehnt: {kopf[:200]!r}")
        self._puffer = rest

    def _lesen(self, n: int) -> bytes:
        while len(self._puffer) < n:
            stueck = self.sock.recv(max(65536, n - len(self._puffer)))
            if not stueck:
                raise WerkzeugFehler("WebSocket: Verbindung unerwartet geschlossen.")
            self._puffer += stueck
        daten, self._puffer = self._puffer[:n], self._puffer[n:]
        return daten

    def senden(self, text: str, opcode: int = 1) -> None:
        nutz = text.encode("utf-8") if isinstance(text, str) else text
        kopf = bytearray([0x80 | opcode])
        n = len(nutz)
        if n < 126:
            kopf.append(0x80 | n)
        elif n < 65536:
            kopf.append(0x80 | 126)
            kopf += struct.pack(">H", n)
        else:
            kopf.append(0x80 | 127)
            kopf += struct.pack(">Q", n)
        maske = os.urandom(4)
        kopf += maske
        # Maskieren mit großen Ganzzahlen (schnell, kein Byte-für-Byte in Python)
        if n:
            m = (maske * (n // 4 + 1))[:n]
            nutz = (int.from_bytes(nutz, "big") ^ int.from_bytes(m, "big")).to_bytes(n, "big")
        self.sock.sendall(bytes(kopf) + nutz)

    def empfangen(self) -> str:
        teile = []
        while True:
            b0, b1 = self._lesen(2)
            fin, opcode = b0 & 0x80, b0 & 0x0F
            laenge = b1 & 0x7F
            if laenge == 126:
                laenge, = struct.unpack(">H", self._lesen(2))
            elif laenge == 127:
                laenge, = struct.unpack(">Q", self._lesen(8))
            daten = self._lesen(laenge)          # Server-Rahmen sind nicht maskiert
            if opcode == 0x9:
                self.senden(daten, opcode=0xA)
                continue
            if opcode == 0x8:
                raise WerkzeugFehler("WebSocket: Gegenstelle hat die Verbindung geschlossen.")
            if opcode in (0x1, 0x0, 0x2):
                teile.append(daten)
                if fin:
                    return b"".join(teile).decode("utf-8")

    def schliessen(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


# Wird bei jedem neuen Dokument vor allem anderen ausgeführt.
INIT_JS = r"""
(() => {
  if (window.__vgl) return;
  const v = {pending: 0, last: performance.now(), mut: performance.now()};
  window.__vgl = v;
  const ofetch = window.fetch;
  if (ofetch) {
    window.fetch = function () {
      v.pending++;
      return ofetch.apply(this, arguments).finally(() => { v.pending--; v.last = performance.now(); });
    };
  }
  const osend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function () {
    v.pending++;
    this.addEventListener('loadend', () => { v.pending--; v.last = performance.now(); });
    return osend.apply(this, arguments);
  };
  new MutationObserver(() => { v.mut = performance.now(); })
    .observe(document, {subtree: true, childList: true, attributes: true, characterData: true});
  const css = '*,*::before,*::after{animation:none!important;transition:none!important;' +
              'caret-color:transparent!important;scroll-behavior:auto!important}';
  const einsetzen = () => {
    if (document.getElementById('__vgl_stil')) return;
    const s = document.createElement('style');
    s.id = '__vgl_stil';
    s.textContent = css;
    (document.head || document.documentElement).appendChild(s);
  };
  if (document.documentElement) einsetzen(); else document.addEventListener('DOMContentLoaded', einsetzen);
})();
"""

STABIL_JS = r"""
(() => {
  const v = window.__vgl;
  if (!v || window.__vgl_alt) return {neu: false};
  const jetzt = performance.now();
  const bilder = [...document.images].every(i => i.complete);
  const schriften = document.fonts ? document.fonts.status === 'loaded' : true;
  const ruhe = Math.round(jetzt - Math.max(v.last, v.mut));
  return {neu: true, ok: document.readyState === 'complete' && v.pending === 0 && ruhe > %d && bilder && schriften,
          zustand: document.readyState, offen: v.pending, ruhe, bilder, schriften,
          hoehe: Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0),
          textlaenge: document.body ? document.body.innerText.length : 0};
})()
""" % STABIL_RUHE_MS

FERTIG_JS = r"""
(() => {
  try { document.getAnimations().forEach(a => a.finish()); } catch (e) {}
  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  window.scrollTo(0, 0);
  return Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0);
})()
"""

# Klickt den Knopf mit diesem Text und wartet, bis ein Rahmen (iframe) darunter fertig geladen hat.
KLICK_JS = r"""
(async () => {
  const text = %s;
  const knopf = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === text);
  if (!knopf) return 'Knopf fehlt';
  const rahmen = document.querySelector('iframe');
  const geladen = rahmen ? new Promise(r => { rahmen.addEventListener('load', () => r(true), {once: true});
                                               setTimeout(() => r(false), 8000); }) : Promise.resolve(true);
  knopf.click();
  await geladen;
  return 'ok';
})()
"""

DETAILS_JS = "document.querySelectorAll('details').forEach(d => { d.open = true; }); true"

# Berechnete Stile aller Elemente (und ihrer ::before/::after mit Inhalt): Sie zeigen, ob zwei Berichte
# gleich aussehen, auch wenn ihr Stilblatt anders geschrieben ist (P2-72: ein CSS für alle Berichte).
# Verglichen werden die sichtbaren und die Layout-Eigenschaften; Breite und Höhe sind die berechneten
# Werte in Pixeln und fangen damit Abstandsunterschiede mit.
STILE_JS = r"""
(() => {
  const P = ['display','position','top','right','bottom','left','float','clear','z-index','overflow-x','overflow-y',
    'box-sizing','width','height','min-width','max-width','min-height','max-height',
    'margin-top','margin-right','margin-bottom','margin-left','padding-top','padding-right','padding-bottom','padding-left',
    'border-top-width','border-right-width','border-bottom-width','border-left-width',
    'border-top-style','border-right-style','border-bottom-style','border-left-style',
    'border-top-color','border-right-color','border-bottom-color','border-left-color',
    'border-top-left-radius','border-top-right-radius','border-bottom-right-radius','border-bottom-left-radius',
    'outline-style','outline-width','outline-color','outline-offset','box-shadow','text-shadow','filter',
    'background-color','background-image','background-size','background-position','background-repeat',
    'color','opacity','visibility','font-family','font-size','font-weight','font-style','font-variant-caps',
    'line-height','letter-spacing','word-spacing','text-align','text-transform','text-decoration-line',
    'text-decoration-color','text-decoration-style','text-indent','text-overflow','white-space','word-break',
    'overflow-wrap','vertical-align','list-style-type','list-style-position','list-style-image',
    'flex-direction','flex-wrap','flex-grow','flex-shrink','flex-basis','justify-content','align-items',
    'align-self','align-content','row-gap','column-gap','grid-template-columns','grid-template-rows',
    'grid-column-start','grid-column-end','grid-row-start','grid-row-end','order','cursor','transform',
    'fill','stroke','border-collapse','border-spacing','table-layout','pointer-events','accent-color'];
  const aus = new Set(['HEAD','STYLE','SCRIPT','META','LINK','TITLE','NOSCRIPT','BASE']);
  const ergebnis = [];
  const marke = (el, pseudo) => {
    const cs = getComputedStyle(el, pseudo || null);
    return P.map(p => cs.getPropertyValue(p)).join('\u0001');
  };
  for (const el of document.querySelectorAll('*')) {
    if (aus.has(el.tagName) || el.closest('head')) continue;
    const kennung = el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
      (el.classList.length ? '.' + [...el.classList].join('.') : '');
    ergebnis.push([kennung, marke(el)]);
    for (const pseudo of ['::before', '::after']) {
      const inhalt = getComputedStyle(el, pseudo).content;
      if (inhalt && inhalt !== 'none' && inhalt !== 'normal') ergebnis.push([kennung + pseudo, marke(el, pseudo)]);
    }
  }
  return {eigenschaften: P, elemente: ergebnis};
})()
"""

META_JS = r"""
(async () => {
  const hash = async (buf) => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', buf)))
    .map(b => b.toString(16).padStart(2, '0')).join('');
  const icons = [];
  for (const l of document.querySelectorAll('link[rel~="icon"], link[rel="apple-touch-icon"]')) {
    let sha = null;
    const href = l.getAttribute('href') || '';
    try {
      if (href.startsWith('data:')) sha = 'data:' + await hash(new TextEncoder().encode(href));
      else { const r = await fetch(l.href); sha = r.ok ? await hash(await r.arrayBuffer()) : 'HTTP ' + r.status; }
    } catch (e) { sha = 'Fehler: ' + e; }
    icons.push({rel: l.getAttribute('rel'), sizes: l.getAttribute('sizes'), type: l.getAttribute('type'),
                href: href.startsWith('data:') ? 'data-uri' : href, sha});
  }
  const theme = document.querySelector('meta[name="theme-color"]');
  return {titel: document.title, sprache: document.documentElement.lang, icons,
          themefarbe: theme ? theme.content : null};
})()
"""


class Chrome:
    """Google Chrome ohne Fenster, gesteuert über das DevTools-Protokoll."""

    def __init__(self, lauf: Lauf, name: str):
        self.lauf = lauf
        self.profil = lauf.arbeit / f"chrome_{name}"
        self.logdatei = lauf.arbeit / f"chrome_{name}.log"
        self.port = freier_port(19300)
        self.proc = None
        self.ws = None
        self._id = 0
        self.ereignisse: list = []
        self.groesse = None
        self.netzsperre = False

    def __enter__(self):
        self.starten()
        return self

    def __exit__(self, *_):
        self.beenden()

    def starten(self) -> None:
        if not CHROME.exists():
            raise WerkzeugFehler(f"Chrome nicht gefunden: {CHROME}")
        self.profil.mkdir(parents=True, exist_ok=True)
        # --host-resolver-rules: Jeder Name außer 127.0.0.1 wird nicht aufgelöst — Chrome darf
        # nirgends sonst hin. Die übrigen Schalter nehmen Chrome die Hintergrund-Netzzugriffe.
        chrome_args = ["--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                "--force-color-profile=srgb", "--font-render-hinting=none", "--no-first-run",
                "--no-default-browser-check", "--mute-audio", "--disable-extensions",
                "--disable-background-networking", "--disable-component-update", "--disable-sync",
                "--disable-default-apps", "--disable-domain-reliability", "--no-pings",
                "--disable-client-side-phishing-detection", "--disable-breakpad",
                "--metrics-recording-only", "--disable-features=Translate,MediaRouter,OptimizationHints,AutofillServerCommunication",
                # Automatisierungsschalter (wie Puppeteer): kein Schlüsselbund-Zugriff (ein hängender
                # Zugriff stoppte die erste Navigation), kein Proxy, keine Drosselung unsichtbarer Seiten.
                "--use-mock-keychain", "--password-store=basic", "--no-proxy-server",
                "--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding", "--disable-ipc-flooding-protection",
                "--disable-hang-monitor", "--disable-popup-blocking", "--disable-prompt-on-repost",
                "--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1",
                f"--user-data-dir={self.profil}", f"--remote-debugging-port={self.port}",
                "--window-size=1440,900", "about:blank"]
        if SANDBOX_EXEC.exists():
            args = [SANDBOX_EXEC, "-p", NETZSPERRE, CHROME, "--no-sandbox", *chrome_args]
            self.netzsperre = True
        else:
            args = [CHROME, *chrome_args]
            self.netzsperre = False
        env = {"PATH": "/usr/bin:/bin", "HOME": str(self.lauf.home), "TMPDIR": str(self.lauf.tmp),
               "LANG": "de_DE.UTF-8"}
        self.proc = prozess_starten(args, env=env, logdatei=self.logdatei)
        ende = time.time() + 40
        ziel = None
        while time.time() < ende:
            if self.proc.poll() is not None:
                raise WerkzeugFehler("Chrome ist beim Start beendet worden:\n"
                                     + self.logdatei.read_text(encoding="utf-8", errors="replace")[-1500:])
            try:
                status, koerper = http_holen(self.port, "/json/list", timeout=2)
                if status == 200:
                    seiten = [t for t in json.loads(koerper) if t.get("type") == "page"]
                    if seiten:
                        ziel = seiten[0]
                        break
            except (OSError, ValueError):
                pass
            time.sleep(0.3)
        if not ziel:
            raise WerkzeugFehler("Chrome meldet kein Seitenziel im DevTools-Protokoll.")
        pfad = ziel["webSocketDebuggerUrl"].split(f":{self.port}", 1)[1]
        self.ws = WebSocket(self.port, pfad)
        for methode in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            self.cdp(methode)
        self.cdp("Page.addScriptToEvaluateOnNewDocument", source=INIT_JS)
        self.cdp("Emulation.setEmulatedMedia", features=[
            {"name": "prefers-color-scheme", "value": "light"},
            {"name": "prefers-reduced-motion", "value": "reduce"}])

    def beenden(self) -> None:
        if self.ws:
            try:
                self.cdp("Browser.close")
            except Exception:       # noqa: BLE001 -- Chrome macht beim Schließen oft die Verbindung zu
                pass
            self.ws.schliessen()
            self.ws = None
        prozess_beenden(self.proc, schonfrist=5.0)
        self.proc = None

    def cdp(self, methode: str, **params):
        self._id += 1
        mid = self._id
        self.ws.senden(json.dumps({"id": mid, "method": methode, "params": params}))
        while True:
            nachricht = json.loads(self.ws.empfangen())
            if nachricht.get("id") == mid:
                if "error" in nachricht:
                    raise WerkzeugFehler(f"{methode}: {nachricht['error']}")
                return nachricht.get("result", {})
            if "method" in nachricht:
                self.ereignisse.append(nachricht)

    def js(self, ausdruck: str, warten: bool = False):
        erg = self.cdp("Runtime.evaluate", expression=ausdruck, returnByValue=True, awaitPromise=warten)
        if "exceptionDetails" in erg:
            raise WerkzeugFehler("JavaScript-Fehler: " + json.dumps(erg["exceptionDetails"], ensure_ascii=False)[:400])
        return erg.get("result", {}).get("value")

    def neu_starten(self) -> None:
        self.beenden()
        self.port = freier_port(19300)
        self.groesse = None
        self.ereignisse = []
        self.starten()

    def aufnehmen_sicher(self, url: str, datei: Path, breite: int, hoehe: int, **kw) -> dict:
        """Wie `aufnehmen`; bei einer Zeitüberschreitung oder einem Verbindungsfehler wird Chrome
        einmal neu gestartet und die Aufnahme wiederholt (selten, aber gesehen: eine Navigation, die
        nie zurückkehrt)."""
        try:
            return self.aufnehmen(url, datei, breite, hoehe, **kw)
        except (TimeoutError, OSError, WerkzeugFehler) as exc:
            log(f"  Aufnahme von {url} fehlgeschlagen ({type(exc).__name__}: {str(exc)[:100]}) — Chrome neu starten, zweiter Versuch")
            self.neu_starten()
            info = self.aufnehmen(url, datei, breite, hoehe, **kw)
            info["wiederholt"] = True
            return info

    def groesse_setzen(self, breite: int, hoehe: int) -> None:
        if self.groesse == (breite, hoehe):
            return
        self.cdp("Emulation.setDeviceMetricsOverride", width=breite, height=hoehe, deviceScaleFactor=1, mobile=False)
        self.groesse = (breite, hoehe)

    def probleme_einsammeln(self) -> list:
        """Konsolenfehler, Netzwerkfehler und Ausnahmen seit dem letzten Aufruf (nur zur Auskunft)."""
        gefunden = []
        for e in self.ereignisse:
            m, p = e.get("method"), e.get("params", {})
            if m == "Runtime.exceptionThrown":
                d = p.get("exceptionDetails", {})
                gefunden.append("Ausnahme: " + str(d.get("exception", {}).get("description") or d.get("text"))[:160])
            elif m == "Log.entryAdded" and p.get("entry", {}).get("level") == "error":
                gefunden.append("Log: " + p["entry"].get("text", "")[:160] + " " + p["entry"].get("url", "")[:100])
            elif m == "Network.loadingFailed" and not p.get("canceled"):
                gefunden.append("Netz: " + p.get("errorText", "")[:80])
            elif m == "Network.responseReceived" and p.get("response", {}).get("status", 0) >= 400:
                gefunden.append(f"HTTP {p['response']['status']}: {p['response'].get('url', '')[:120]}")
        self.ereignisse = []
        return gefunden

    def laden(self, url: str, timeout: float = SEITE_TIMEOUT_S) -> dict:
        """Navigiert und wartet, bis die NEUE Seite fertig und ruhig ist (zwei aufeinanderfolgende
        ruhige Messungen im Abstand von 300 ms)."""
        self.js("window.__vgl_alt = true")
        erg = self.cdp("Page.navigate", url=url)
        if erg.get("errorText"):
            raise WerkzeugFehler(f"Navigation zu {url}: {erg['errorText']}")
        return self.ruhe_abwarten(timeout)

    def ruhe_abwarten(self, timeout: float = SEITE_TIMEOUT_S) -> dict:
        """Wartet, bis die aktuelle (neue) Seite fertig und ruhig ist."""
        ende = time.time() + timeout
        ruhig, letzter = 0, {}
        while time.time() < ende:
            try:
                zustand = self.js(STABIL_JS)
            except WerkzeugFehler:
                zustand = None
            if zustand and zustand.get("neu"):
                letzter = zustand
                ruhig = ruhig + 1 if zustand.get("ok") else 0
                if ruhig >= 2:
                    letzter["stabil"] = True
                    return letzter
            time.sleep(0.3)
        letzter["stabil"] = False
        return letzter

    def aufnehmen(self, url: str, datei: Path, breite: int, hoehe: int, *, details_oeffnen: bool = False,
                  stile: bool = False, klick: str | None = None) -> dict:
        self.groesse_setzen(breite, hoehe)
        zustand = self.laden(url)
        if klick:                                   # Reiter anklicken (z. B. Dokumentation, Reiter „Funktionen“)
            erg = self.js(KLICK_JS % json.dumps(klick), warten=True)
            if erg != "ok":
                raise WerkzeugFehler(f"Klick auf „{klick}“ nicht möglich ({erg})")
            zustand = self.ruhe_abwarten()
            time.sleep(0.5)
        if details_oeffnen:
            self.js(DETAILS_JS)
            time.sleep(0.4)
        seitenhoehe = int(self.js(FERTIG_JS) or hoehe)
        berechnete = self.js(STILE_JS) if stile else None
        abgeschnitten = seitenhoehe > MAX_SEITENHOEHE
        h = max(hoehe, min(seitenhoehe, MAX_SEITENHOEHE))
        aufnahme = self.cdp("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                            clip={"x": 0, "y": 0, "width": breite, "height": h, "scale": 1})
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_bytes(base64.b64decode(aufnahme["data"]))
        try:
            meta = self.js(META_JS, warten=True)
        except WerkzeugFehler as exc:
            meta = {"fehler": str(exc)[:200]}
        return {"stabil": zustand.get("stabil", False), "seitenhoehe": seitenhoehe, "abgeschnitten": abgeschnitten,
                "meta": meta, "probleme": self.probleme_einsammeln(), "stile": berechnete}


# ── PNG: dekodieren, vergleichen, schreiben ─────────────────────────────────────────────────
_PNG_KOPF = b"\x89PNG\r\n\x1a\n"
_NICHT_NULL = re.compile(rb"[^\x00]")


def png_zerlegen(daten: bytes) -> tuple:
    """(Breite, Höhe, Bittiefe, Farbtyp, Interlace, entpackte Rohzeilen)."""
    if daten[:8] != _PNG_KOPF:
        raise ValueError("kein PNG")
    pos, ihdr, idat = 8, None, []
    while pos < len(daten):
        laenge, = struct.unpack(">I", daten[pos:pos + 4])
        art, koerper = daten[pos + 4:pos + 8], daten[pos + 8:pos + 8 + laenge]
        pos += 12 + laenge
        if art == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", koerper)
        elif art == b"IDAT":
            idat.append(koerper)
        elif art == b"IEND":
            break
    if ihdr is None:
        raise ValueError("PNG ohne IHDR")
    breite, hoehe, tiefe, farbtyp, _kompr, _filter, interlace = ihdr
    return breite, hoehe, tiefe, farbtyp, interlace, zlib.decompress(b"".join(idat))


def _bpp(tiefe: int, farbtyp: int, interlace: int) -> int:
    if tiefe != 8 or interlace != 0 or farbtyp not in (2, 6):
        raise ValueError(f"nicht unterstütztes PNG (Tiefe {tiefe}, Farbtyp {farbtyp}, Interlace {interlace})")
    return 3 if farbtyp == 2 else 4


_SWAR_MASKEN: dict = {}


def _zeile_up(roh: bytes, oben: bytes) -> bytes:
    """Up-Filter für alle Bytes auf einmal (Byteweise Addition mod 256 mit großen Ganzzahlen)."""
    n = len(roh)
    masken = _SWAR_MASKEN.get(n)
    if masken is None:
        masken = _SWAR_MASKEN[n] = (int.from_bytes(b"\x7f" * n, "little"), int.from_bytes(b"\x80" * n, "little"))
    niedrig, hoch = masken
    a, b = int.from_bytes(roh, "little"), int.from_bytes(oben, "little")
    return (((a & niedrig) + (b & niedrig)) ^ ((a ^ b) & hoch)).to_bytes(n, "little")


def _zeile_sub(roh: bytes, bpp: int) -> bytes:
    aus = bytearray(len(roh))
    for c in range(bpp):
        aus[c::bpp] = bytes(itertools.accumulate(roh[c::bpp], lambda x, y: (x + y) & 255))
    return bytes(aus)


def _zeile_avg(roh: bytes, oben: bytes, bpp: int) -> bytes:
    n = len(roh)
    aus = bytearray(n)
    for i in range(n):
        links = aus[i - bpp] if i >= bpp else 0
        aus[i] = (roh[i] + ((links + oben[i]) >> 1)) & 255
    return bytes(aus)


def _zeile_paeth(roh: bytes, oben: bytes, bpp: int) -> bytes:
    n = len(roh)
    aus = bytearray(n)
    for i in range(n):
        if i < bpp:
            a = c = 0
        else:
            a, c = aus[i - bpp], oben[i - bpp]
        b = oben[i]
        pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - c - c)
        if pa <= pb and pa <= pc:
            vorhersage = a
        elif pb <= pc:
            vorhersage = b
        else:
            vorhersage = c
        aus[i] = (roh[i] + vorhersage) & 255
    return bytes(aus)


def zeile_rekonstruieren(filterart: int, roh: bytes, oben: bytes, bpp: int) -> bytes:
    if filterart == 0:
        return roh
    if filterart == 1:
        return _zeile_sub(roh, bpp)
    if filterart == 2:
        return _zeile_up(roh, oben)
    if filterart == 3:
        return _zeile_avg(roh, oben, bpp)
    if filterart == 4:
        return _zeile_paeth(roh, oben, bpp)
    raise ValueError(f"unbekannter PNG-Filter {filterart}")


def _png_schreiben(pfad: Path, breite: int, hoehe: int, zeilen) -> None:
    roh = b"".join(b"\x00" + bytes(z) for z in zeilen)

    def stueck(art: bytes, koerper: bytes) -> bytes:
        return struct.pack(">I", len(koerper)) + art + koerper + struct.pack(">I", zlib.crc32(art + koerper) & 0xFFFFFFFF)

    daten = (_PNG_KOPF + stueck(b"IHDR", struct.pack(">IIBBBBB", breite, hoehe, 8, 2, 0, 0, 0))
             + stueck(b"IDAT", zlib.compress(roh, 6)) + stueck(b"IEND", b""))
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(daten)


_BLASS = bytes(int(v * 0.3 + 255 * 0.7) for v in range(256))
_MAGENTA = bytes((255, 0, 255))
_ORANGE = bytes((255, 150, 0))


def bilder_vergleichen(pfad_a: str, pfad_b: str, diff_pfad: str | None) -> dict:
    """Bildpunktgenauer Vergleich zweier PNG-Dateien. Schneller Weg: gleiche Bytes, dann gleiche
    entpackte Rohzeilen; nur sonst werden die Zeilen rekonstruiert. Bei Unterschieden entsteht ein
    Differenzbild (blasse Seite, abweichende Punkte magenta, Umriss des Bereichs rot)."""
    try:
        a_bytes, b_bytes = Path(pfad_a).read_bytes(), Path(pfad_b).read_bytes()
        if a_bytes == b_bytes:
            return {"gleich": True, "modus": "bytegleich", "abweichend": 0, "bereich": None}
        wa, ha, ta, fa, ia, rohwa = png_zerlegen(a_bytes)
        wb, hb, tb, fb, ib, rohb = png_zerlegen(b_bytes)
        if (wa, ha, ta, fa, ia) == (wb, hb, tb, fb, ib) and rohwa == rohb:
            return {"gleich": True, "modus": "gleiche Bilddaten", "abweichend": 0, "bereich": None}
        bpp_a, bpp_b = _bpp(ta, fa, ia), _bpp(tb, fb, ib)
    except (ValueError, zlib.error, OSError, struct.error) as exc:
        return {"gleich": False, "modus": "Fehler", "abweichend": -1, "bereich": None, "fehler": str(exc)}

    breite, hoehe = max(wa, wb), max(ha, hb)
    gemeinsam_b, gemeinsam_h = min(wa, wb), min(ha, hb)
    sa, sb = wa * bpp_a, wb * bpp_b
    vorher_a, vorher_b = bytes(sa), bytes(sb)
    anzahl = 0
    max_kanal = 0                  # größter Abstand eines einzelnen Farbkanals (0..255) über alle Bildpunkte
    x0 = y0 = 10 ** 9
    x1 = y1 = -1
    zeilen = []
    for y in range(hoehe):
        if y >= gemeinsam_h:                      # Zeile gibt es nur in einem der Bilder
            max_kanal = 255
            anzahl += breite
            x0, x1, y0, y1 = 0, max(x1, breite - 1), min(y0, y), max(y1, y)
            zeilen.append(_ORANGE * breite)
            continue
        offset_a, offset_b = y * (sa + 1), y * (sb + 1)
        ra, rb = rohwa[offset_a:offset_a + sa + 1], rohb[offset_b:offset_b + sb + 1]
        za = zeile_rekonstruieren(ra[0], ra[1:], vorher_a, bpp_a)
        if sa == sb and bpp_a == bpp_b and ra == rb and vorher_a == vorher_b:
            zb = za                                # gleiche Rohzeile über gleicher Vorzeile: gleiches Ergebnis
        else:
            zb = zeile_rekonstruieren(rb[0], rb[1:], vorher_b, bpp_b)
        vorher_a, vorher_b = za, zb
        # RGB-Sicht (Alpha weglassen), nur über die gemeinsame Breite
        if bpp_a == 4:
            za3 = bytes(itertools.chain.from_iterable(zip(za[0::4], za[1::4], za[2::4])))
        else:
            za3 = za
        if bpp_b == 4:
            zb3 = bytes(itertools.chain.from_iterable(zip(zb[0::4], zb[1::4], zb[2::4])))
        else:
            zb3 = zb
        a_rgb, b_rgb = za3[:gemeinsam_b * 3], zb3[:gemeinsam_b * 3]
        if a_rgb == b_rgb:
            zeile = bytearray(b_rgb.translate(_BLASS))
        else:
            xor = (int.from_bytes(a_rgb, "little") ^ int.from_bytes(b_rgb, "little")).to_bytes(len(a_rgb), "little")
            spalten = sorted({m.start() // 3 for m in _NICHT_NULL.finditer(xor)})
            zeile = bytearray(b_rgb.translate(_BLASS))
            for sp in spalten:
                zeile[sp * 3:sp * 3 + 3] = _MAGENTA
            anzahl += len(spalten)
            max_kanal = max(max_kanal, max(map(abs, map(operator.sub, a_rgb, b_rgb))))
            x0, x1 = min(x0, spalten[0]), max(x1, spalten[-1])
            y0, y1 = min(y0, y), max(y1, y)
        if breite > gemeinsam_b:                    # Breitenunterschied: Rest der Zeile ist Abweichung
            max_kanal = 255
            zeile += _ORANGE * (breite - gemeinsam_b)
            anzahl += breite - gemeinsam_b
            x0, x1, y0, y1 = min(x0, gemeinsam_b), max(x1, breite - 1), min(y0, y), max(y1, y)
        zeilen.append(zeile)

    ergebnis = {"gleich": anzahl == 0, "modus": "pixelgleich" if anzahl == 0 else "ungleich",
                "abweichend": anzahl, "max_kanal": max_kanal, "groesse_a": [wa, ha], "groesse_b": [wb, hb],
                "bereich": None if anzahl == 0 else [x0, y0, x1, y1]}
    if anzahl and diff_pfad:
        rot = bytes((220, 0, 0))
        for y in (y0, min(y0 + 1, hoehe - 1), y1, max(y1 - 1, 0)):
            if 0 <= y < hoehe:
                z = zeilen[y] if isinstance(zeilen[y], bytearray) else bytearray(zeilen[y])
                for x in range(max(x0, 0), min(x1, breite - 1) + 1):
                    z[x * 3:x * 3 + 3] = rot
                zeilen[y] = z
        for y in range(max(y0, 0), min(y1, hoehe - 1) + 1):
            z = zeilen[y] if isinstance(zeilen[y], bytearray) else bytearray(zeilen[y])
            for x in (x0, min(x0 + 1, breite - 1), x1, max(x1 - 1, 0)):
                if 0 <= x < breite:
                    z[x * 3:x * 3 + 3] = rot
            zeilen[y] = z
        _png_schreiben(Path(diff_pfad), breite, hoehe, zeilen)
        ergebnis["diff"] = str(diff_pfad)
    return ergebnis


# ── CSS: parsen, Variablen auflösen, Farben vereinheitlichen ────────────────────────────────
_KOMMENTAR = re.compile(r"/\*.*?\*/", re.S)
_VAR = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)\s*(?:,\s*([^()]*(?:\([^()]*\)[^()]*)*))?\)")
_FARBE_FUNK = re.compile(r"rgba?\(\s*([0-9.]+%?)\s*[ ,]\s*([0-9.]+%?)\s*[ ,]\s*([0-9.]+%?)\s*(?:[,/]\s*((?:[^()]|\([^()]*\))+?))?\s*\)")
_HEX = re.compile(r"#([0-9a-fA-F]{3,8})\b")


def _ende_suchen(text: str, i: int, zeichen: str) -> int:
    """Index des ersten Zeichens aus `zeichen` ab i, außerhalb von Klammern und Zeichenketten; -1 wenn keins."""
    tiefe, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            ende = i + 1
            while ende < n and text[ende] != c:
                ende += 2 if text[ende] == "\\" else 1
            i = ende
        elif c == "(" or c == "[":
            tiefe += 1
        elif c == ")" or c == "]":
            tiefe = max(0, tiefe - 1)
        elif tiefe == 0 and c in zeichen:
            return i
        i += 1
    return -1


def _block_ende(text: str, offen: int) -> int:
    """Index der passenden schließenden Klammer zur öffnenden bei `offen`."""
    tiefe, i, n = 0, offen, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            ende = i + 1
            while ende < n and text[ende] != c:
                ende += 2 if text[ende] == "\\" else 1
            i = ende
        elif c == "{":
            tiefe += 1
        elif c == "}":
            tiefe -= 1
            if tiefe == 0:
                return i
        i += 1
    return n


def _leer_normalisieren(s: str) -> str:
    s = re.sub(r"\s+", " ", s.strip())
    return re.sub(r"\s*([,;>~+])\s*", r"\1", s) if not s.startswith("@") else s


def css_deklarationen(inneres: str) -> list:
    erg, i, n = [], 0, len(inneres)
    while i < n:
        j = _ende_suchen(inneres, i, ";")
        stueck = inneres[i:(n if j < 0 else j)].strip()
        i = n if j < 0 else j + 1
        if not stueck or ":" not in stueck:
            continue
        name, _, wert = stueck.partition(":")
        erg.append((name.strip().lower(), re.sub(r"\s+", " ", wert.strip())))
    return erg


def css_regeln(text: str, kontext: str = "") -> list:
    """Flache Liste (Kontext, Selektor, [(Eigenschaft, Wert)…]) in Quellreihenfolge. @media/@supports/
    @layer werden aufgelöst (Kontext), @keyframes zählen Schritt für Schritt."""
    text = _KOMMENTAR.sub("", text) if not kontext else text
    regeln, i, n = [], 0, len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        j = _ende_suchen(text, i, "{;")
        if j < 0:
            break
        kopf = re.sub(r"\s+", " ", text[i:j].strip())
        if text[j] == ";":
            regeln.append((kontext, kopf, []))
            i = j + 1
            continue
        k = _block_ende(text, j)
        inneres = text[j + 1:k]
        if kopf.startswith("@"):
            name = kopf.split(" ", 1)[0].lower()
            if name in ("@media", "@supports", "@layer", "@container", "@document", "@scope"):
                regeln += css_regeln(inneres, f"{kontext}{kopf} > ")
            elif "keyframes" in name:
                regeln += css_regeln(inneres, f"{kontext}{kopf} > ")
            else:
                regeln.append((kontext, kopf, css_deklarationen(inneres)))
        else:
            regeln.append((kontext, _leer_normalisieren(kopf), css_deklarationen(inneres)))
        i = k + 1
    return regeln


def css_variablen(regeln: list) -> dict:
    """Werte der benutzerdefinierten Eigenschaften aus `:root`-Blöcken (später gewinnt)."""
    werte = {}
    for kontext, selektor, deklarationen in regeln:
        if kontext == "" and any(t.strip() in (":root", "html", ":root:not([data-theme=light])")
                                 for t in selektor.split(",")):
            for name, wert in deklarationen:
                if name.startswith("--"):
                    werte[name] = wert
    return werte


def _aufloesen(wert: str, variablen: dict) -> str:
    """Ersetzt var(--x) durch den Wert aus `variablen`. Unbekannte Variablen bleiben stehen (auch
    mit Rückfallwert) — sie stehen dann auf beiden Seiten gleich da, wenn sie gleich gemeint sind."""
    def ersatz(m):
        return variablen.get(m.group(1), m.group(0))

    for _ in range(6):                      # verschachtelte var() auflösen
        neu = _VAR.sub(ersatz, wert)
        if neu == wert:
            break
        wert = neu
    return wert


def _zahl(text: str) -> str:
    try:
        f = float(text)
    except ValueError:
        return text
    return ("%g" % round(f, 4))


def _alpha_text(wert: float, quantisieren: bool) -> str:
    """Alphawert als Text. Mit `quantisieren` zählt nur der 8-Bit-Wert (0..255, halbe Werte nach oben):
    0.5 und 0.502 sind dann dasselbe, denn beide ergeben 128."""
    if quantisieren:
        return f"{int(wert * 255 + 0.5)}/255"
    return _zahl(str(wert))


def _farbe_normal(wert: str, quantisieren: bool = False) -> str:
    """Hex und rgb()/rgba() in EINE Schreibweise: `rgb(R G B)` bzw. `rgb(R G B / A)`."""
    def hexersatz(m):
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) not in (6, 8):
            return m.group(0)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        if len(h) == 8 and h[6:8].lower() != "ff":
            return f"rgb({r} {g} {b} / {_alpha_text(int(h[6:8], 16) / 255, quantisieren)})"
        return f"rgb({r} {g} {b})"

    def funkersatz(m):
        teile = []
        for t in m.groups()[:3]:
            teile.append(_zahl(t[:-1]) + "%" if t.endswith("%") else _zahl(t))
        alpha = (m.group(4) or "").strip()
        if alpha:
            if re.fullmatch(r"[0-9.]+%", alpha):
                alpha = _alpha_text(float(alpha[:-1]) / 100, quantisieren)
            elif re.fullmatch(r"[0-9.]+", alpha):
                alpha = _alpha_text(float(alpha), quantisieren)
            if alpha in ("1", "255/255"):
                alpha = ""
        return f"rgb({' '.join(teile)}{' / ' + alpha if alpha else ''})"

    wert = _FARBE_FUNK.sub(funkersatz, wert)
    return _HEX.sub(hexersatz, wert)


def css_wert_normal(wert: str, variablen: dict, eigenschaft: str = "", quantisieren: bool = False) -> str:
    wert = _aufloesen(wert, variablen)
    wert = _farbe_normal(wert, quantisieren)
    if eigenschaft == "font-family":                      # 'Inter' und Inter sind dieselbe Schrift
        wert = wert.replace("'", "").replace('"', "")
    wert = re.sub(r"\s*!\s*important", " !important", wert)
    wert = re.sub(r"(?<![0-9])0+\.(\d)", r"0.\1", wert)
    wert = re.sub(r"(?<![0-9a-zA-Z])\.(\d)", r"0.\1", wert)
    wert = re.sub(r"\s*,\s*", ",", wert)
    return re.sub(r"\s+", " ", wert).strip().lower()


def css_serialisieren(regeln: list, variablen: dict, quantisieren: bool = False) -> list:
    """Eine Zeile je Regel: `Kontext | Selektor { eigenschaft: wert; … }`, Werte aufgelöst/vereinheitlicht.
    Benutzerdefinierte Eigenschaften der `:root`-Blöcke entfallen (sie stehen in `variablen`)."""
    zeilen = []
    for kontext, selektor, deklarationen in regeln:
        if kontext == "" and any(t.strip() in (":root",) for t in selektor.split(",")):
            deklarationen = [d for d in deklarationen if not d[0].startswith("--")]
            if not deklarationen:
                continue
        deklaration_text = "; ".join(f"{n}: {css_wert_normal(w, variablen, n, quantisieren)}" for n, w in deklarationen)
        zeilen.append(f"{kontext}{selektor} {{ {deklaration_text} }}")
    return zeilen


def _zeilen_diff_regeln(zeilen_a: list, zeilen_b: list, anzeige_a: list | None = None,
                        anzeige_b: list | None = None) -> list:
    """Regel-Diff. Verglichen wird `zeilen_*`, angezeigt `anzeige_*` (gleiche Länge, gleiche Reihenfolge:
    die lesbare Fassung ohne gerundete Alphawerte)."""
    anzeige_a = zeilen_a if anzeige_a is None else anzeige_a
    anzeige_b = zeilen_b if anzeige_b is None else anzeige_b
    unterschiede = []
    abgleich = difflib.SequenceMatcher(None, zeilen_a, zeilen_b, autojunk=False)
    for tag, a0, a1, b0, b1 in abgleich.get_opcodes():
        if tag == "equal":
            continue
        unterschiede += ["- " + z for z in anzeige_a[a0:a1]]
        unterschiede += ["+ " + z for z in anzeige_b[b0:b1]]
    return unterschiede


def css_vergleichen(text_a: str, text_b: str, zusatz_a: str = "", zusatz_b: str = "") -> dict:
    """Bytegleich? Sonst: Regeln nach dem Auflösen der Variablen gleich? Zwei Stufen: erst streng,
    dann mit Alphawerten auf 8 Bit gerundet (Tailwind schreibt aus einer Hex-Farbe `/10` als 0.102,
    aus einer Variablen als 0.1; beides ist der 8-Bit-Wert 26 und ergibt dasselbe Bild). `zusatz_*`
    ist ein weiterer CSS-Text, aus dem nur Variablen gelesen werden (z. B. /api/design.css)."""
    if text_a == text_b:
        return {"urteil": "bytegleich", "gleich": True, "unterschiede": []}
    regeln_a, regeln_b = css_regeln(text_a), css_regeln(text_b)
    var_a = css_variablen(css_regeln(zusatz_a)) if zusatz_a else {}
    var_a.update(css_variablen(regeln_a))
    var_b = css_variablen(css_regeln(zusatz_b)) if zusatz_b else {}
    var_b.update(css_variablen(regeln_b))
    streng_a, streng_b = css_serialisieren(regeln_a, var_a), css_serialisieren(regeln_b, var_b)
    if streng_a == streng_b:
        return {"urteil": "regelgleich (nach Auflösen der Variablen)", "gleich": True, "unterschiede": [],
                "regeln": len(streng_a)}
    rund_a, rund_b = css_serialisieren(regeln_a, var_a, True), css_serialisieren(regeln_b, var_b, True)
    if rund_a == rund_b:
        rundung = _zeilen_diff_regeln(streng_a, streng_b)
        return {"urteil": "regelgleich (nach Auflösen der Variablen; Alphawerte nur durch Rundung verschieden, "
                          f"gleicher 8-Bit-Wert, {len(rundung) // 2} Regeln)",
                "gleich": True, "unterschiede": [], "regeln": len(rund_a), "rundung": rundung}
    unterschiede = _zeilen_diff_regeln(rund_a, rund_b, streng_a, streng_b)
    nur_reihenfolge = sorted(rund_a) == sorted(rund_b)
    return {"urteil": "ungleich" + (" (nur die Reihenfolge der Regeln)" if nur_reihenfolge else ""),
            "gleich": False, "unterschiede": unterschiede, "regeln": [len(rund_a), len(rund_b)]}


# ── Texte: Masken und Zeilen-Diff ───────────────────────────────────────────────────────────
def masken_anwenden(text: str, heute: str, treffer: dict) -> str:
    """Wendet M1 bis M3 an (Beschreibung im Moduldocstring). `treffer` zählt, wie oft jede griff."""
    def zaehlen(name, muster, ersatz, s, flags=0):
        neu, n = re.subn(muster, ersatz, s, flags=flags)
        if n:
            treffer[name] = treffer.get(name, 0) + n
        return neu

    text = zaehlen("M1 erzeugt am <Datum> <Uhrzeit>",
                   r"erzeugt am (?:\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4}) \d{2}:\d{2}", "erzeugt am ‹ZEITPUNKT›", text)
    text = zaehlen("M2 Stand <Datum> <Uhrzeit> (Coach-Site)",
                   r"Stand \d{2}\.\d{2}\.\d{4} \d{2}:\d{2}", "Stand ‹ZEITPUNKT›", text)
    iso = heute
    de = f"{heute[8:10]}.{heute[5:7]}.{heute[0:4]}"
    kompakt = heute.replace("-", "")
    text = zaehlen("M3 Tagesdatum des Erzeugerlaufs", "|".join(re.escape(x) for x in (iso, de, kompakt)), "‹HEUTE›", text)
    return text


def zeilen_diff(text_a: str, text_b: str, name_a="alt", name_b="neu") -> list:
    return list(difflib.unified_diff(text_a.splitlines(), text_b.splitlines(), name_a, name_b, lineterm="", n=1))


_STIL_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style>", re.S | re.I)


def stil_und_rest(html_text: str) -> tuple:
    """(alle <style>-Inhalte hintereinander, Dokument ohne <style>-Blöcke)"""
    stile = "\n".join(_STIL_BLOCK.findall(html_text))
    return stile, _STIL_BLOCK.sub("<style></style>", html_text)


# ── Erzeuger der Berichte (läuft im Prozess des jeweiligen Stands) ──────────────────────────
ERZEUGER = r'''
"""Erzeuger der festen Berichte (P2-72, Paket V). Läuft IM Programmordner und Datenordner der Probe,
mit dem Code des jeweiligen Stands. Alle Eingaben sind erfunden (Max Mustermann, Beispiel GmbH)."""
import datetime
import json
import os
import shutil
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace

PROG = Path(os.environ["VGL_PROGRAMM"])
ZIEL = Path(os.environ["VGL_ZIEL"]) / "roh"
ZIEL.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(PROG / "backend"))
os.chdir(PROG / "backend")

ERGEBNIS = {"heute": datetime.date.today().isoformat(), "eintraege": {}}
STATE = {}


def eintrag(name, funktion):
    try:
        funktion()
        ERGEBNIS["eintraege"][name] = {"ok": True}
    except BaseException as exc:                                    # noqa: BLE001 -- auch SystemExit der Erzeuger
        (ZIEL / f"{name}.FEHLER.txt").write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        ERGEBNIS["eintraege"][name] = {"ok": False, "fehler": traceback.format_exc()[-1800:]}


def kopieren(quelle, ziel_name):
    ziel = ZIEL / ziel_name
    ziel.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(quelle, ziel)


def artefakt(rel):
    from app.db import artefakt_pfad
    return artefakt_pfad(rel)


def vorbereiten():
    from sqlmodel import Session, select
    from app.db import engine, init_db
    from app.models import Interview, Job
    init_db()
    with Session(engine) as s:
        jobs = s.exec(select(Job).where(Job.deleted_at.is_(None)).order_by(Job.id)).all()
        job = next((j for j in jobs if j.status == "Beworben"), jobs[0])
        STATE["job_id"] = job.id
        iv = s.exec(select(Interview).order_by(Interview.id)).first()
        STATE["iv_id"] = iv.id if iv else None
        STATE["iv_job_id"] = iv.job_id if iv else job.id


def company_fit():
    from pipeline import company_fit as cf
    erg = cf.render_full(
        STATE["job_id"], sub="Logistik · Zustellung · Situation RUN & <Wachstum>", fit_ampel="gelb",
        fit_text="solider Fit, zwei Vorbehalte",
        bluf="Kernaussage: Die Stelle passt zu Max Mustermann, offen bleiben Einarbeitung & Schichtmodell <bitte klären>.",
        abschnitte={
            "geschaeftsmodell_was": {"Kerngeschäft": "Beispiel GmbH liefert Pakete im Nahverkehr.",
                                     "Wachstum & Finanzlage": "Der Umsatz steigt seit drei Jahren leicht."},
            "geschaeftsmodell_wettbewerber": ["Muster Logistik AG", "Probe Kurier GmbH"],
            "ki_disruption": "Die Routenplanung wird automatisiert, die Zustellung selbst bleibt Handarbeit.",
            "arbeitgeber_realitaet": {"bewertungen": "Bewertungsportal: 3,9 von 5 (Beispielwert).",
                                      "modern": "Handscanner und Zustell-App sind im Einsatz.",
                                      "aktivitaet": "Mehrere offene Stellen in Musterstadt.",
                                      "entwicklung": "Zwei neue Depots sind geplant."},
            "chancen": ["Feste Tour in Musterstadt", {"label": "Entwicklung", "text": "Aufstieg zur Tourenleitung möglich"}],
            "risiken": [{"label": "Schichtmodell", "text": "Frühdienst ab 4 Uhr"}, "Hohe Stückzahl pro Tag"]},
        rollen_einfluss=[
            {"faktor": "Tourenplanung", "wert": "pos", "warum": "Ortskenntnis zählt", "relevanz": "Direkter Hebel"},
            {"faktor": "Vergütung", "wert": "neu", "warum": "Nicht genannt", "relevanz": "Offen"},
            {"faktor": "Arbeitszeit", "wert": "neg", "warum": "Frühdienst", "relevanz": "Belastung"}],
        klaerungsfrage="Wie viele Sendungen pro Tour sind üblich?",
        quellen=[{"label": "Original-Anzeige", "url": "https://example.invalid/anzeige"},
                 {"label": "Recherche Beispielportal"}],
        markt_segment="Paketzustellung", quellen_kurz="example.invalid, Beispielportal")
    pfad = artefakt(erg["company_fit_path"])
    kopieren(pfad, "company_fit.html")
    STATE["fit_rel"] = erg["company_fit_path"]


def debrief():
    from sqlmodel import Session
    from app.db import DATA_DIR, engine
    from app.models import Transcript
    from pipeline import transcript_report as tr
    roh = DATA_DIR / "transcripts" / "beispiel_transkript.txt"
    roh.parent.mkdir(parents=True, exist_ok=True)
    roh.write_text("Erika Mustermann: Willkommen, schön dass es geklappt hat.\n"
                   "Max Mustermann: Danke, ich freue mich auf das Gespräch.\n"
                   "Erika Mustermann: Erzählen Sie kurz, wie Ihre Touren aussehen.\n", encoding="utf-8")
    with Session(engine) as s:
        t = Transcript(job_id=STATE["iv_job_id"], interview_id=STATE["iv_id"], source="manuell",
                       title="1. Gespräch - Beispiel", file_path="data/transcripts/beispiel_transkript.txt",
                       recorded_at="2026-01-15", language="de", kontakt="Erika Mustermann",
                       gespraechsart="Video-Call")
        s.add(t)
        s.commit()
        s.refresh(t)
        tid = t.id
    basis = tr.render_basis(tid)
    kopieren(artefakt(basis["report_path"]), "debrief_basis.html")
    voll = tr.render_full(
        tid, sections=[
            {"title": "Was gut lief", "html": '<ul><li>Klare Antworten zur Tourenplanung.</li>'
                                              '<li>Ortskenntnis betont.</li></ul>'},
            {"title": "Signale & Red Flags",
             "html": '<div class="signal pos"><b>Positiv:</b> Einarbeitung zugesagt.</div>'
                     '<div class="signal warn"><b>Zu beobachten:</b> Frühdienst nicht verhandelbar.</div>'
                     '<p>Zitat: <span class="tag">„Wir starten um 4 Uhr“</span></p>'},
            {"title": "Offene Fragen", "html": "<ol><li>Wie viele Sendungen pro Tour?</li>"
                                              "<li>Wann kommt die Rückmeldung?</li></ol>"}],
        summary="Das Gespräch verlief freundlich. Offen sind Schichtmodell und Tourengröße. "
                "Die Rückmeldung wurde für nächste Woche zugesagt.",
        todos=["Danke-Mail senden", "Frühdienst prüfen"], status_danach="Absolviert · Rückmeldung zugesagt")
    kopieren(artefakt(voll["report_path"]), "debrief.html")


def snapshot():
    from sqlmodel import Session
    from app.db import engine
    from app.models import Job
    from pipeline import posting_snapshot as ps
    text = ("Wir suchen Verstärkung für unser Zustellteam.\n\nSie liefern Pakete aus und bedienen den Handscanner.\n\n"
            "Wir bieten einen sicheren Arbeitsplatz in Musterstadt.")
    with Session(engine) as s:
        job = s.get(Job, STATE["job_id"])
        rel = ps.render_basis(job, text=text)
        s.add(job)
        s.commit()
    kopieren(artefakt(rel), "snapshot_basis.html")
    erg = ps.render_full(
        STATE["job_id"],
        abschnitte={"aufgaben": ["Pakete zustellen", "Handscanner bedienen"],
                    "anforderungen": ["Führerschein Klasse B", "Ortskenntnis in Musterstadt"],
                    "benefits": ["Sicherer Arbeitsplatz", "Dienstkleidung"],
                    "ueber_das_unternehmen": "Beispiel GmbH ist ein kleiner Zustelldienst.\n\nSitz in Musterstadt.",
                    "kontext": "Anzeige von der Karriereseite des Beispielportals."},
        quelle="gruen", hinweis="Beispielhinweis: Anzeige ist noch online.",
        widersprueche=[{"feld": "Ort", "anzeigentext": "Musterstadt", "eckdaten": "Beispielhausen"}])
    kopieren(artefakt(erg["posting_snapshot_path"]), "snapshot.html")


def cleanup():
    from pipeline import cleanup as cl
    ergebnis = {
        "erzeugt_am": "2026-01-15T10:30:00Z",
        "orphans": {"anzahl": 12, "groesse_bytes": 3_500_000, "groesse_mb": 3.5, "dateien": [
            {"pfad": f"data/job_postings/Anzeige_Beispiel_{i}.html", "ordner": "data/job_postings",
             "groesse_bytes": 40_000 + i * 1000, "alter_tage": 10 + i} for i in range(1, 13)]},
        "dangling_referenzen": {"anzahl": 2, "eintraege": [
            {"modell": "Job", "id": 3, "feld": "posting_snapshot_path", "pfad": "data/job_postings/fehlt.html"},
            {"modell": "Company", "id": 5, "feld": "fit_analysis_path", "pfad": "data/company_fit/fehlt.html"}]},
        "rotation": {"schwelle_tage": 60, "anzahl": 4, "groesse_mb": 51.2, "je_ordner": {
            "data/backups": {"anzahl": 3, "groesse_bytes": 50_000_000}, "data/exports": {"anzahl": 1, "groesse_bytes": 1_200_000}}},
        "row_pflege": {"schwelle_tage": 90, "agenttask_kandidaten": 7, "run_kandidaten": 2},
        "papierkorb": {"anzahl": 9, "groesse_mb": 1.25},
        "auffaellig": True,
    }
    (ZIEL / "cleanup.html").write_text(cl._build_html(ergebnis), encoding="utf-8")


def beirat():
    import beirat_engine as be
    koepfe = {f"kopf{i}": {"anzeige": f"Beiratsmitglied {i}"} for i in range(1, 8)}
    bereiche = be.ABSTIMMUNGS_BEREICHE
    abstimmung = {}
    for i, kid in enumerate(sorted(koepfe)):
        if i == 6:
            abstimmung[kid] = None
            continue
        abstimmung[kid] = {"scores": {b: 4 + ((i + j) % 6) for j, b in enumerate(bereiche)},
                           "votum": ["Bewerben", "Bedingt", "Nicht"][i % 3], "begruendung": "Beispiel"}
    d = SimpleNamespace(
        entscheidung={"ampel": "Bedingt", "gesamt": 6.4, "stimmen": {"Bewerben": 3, "Bedingt": 2, "Nicht": 1},
                      "enthaltungen": ["kopf7"],
                      "bereichs_avg": {b: 3.0 + 1.3 * j for j, b in enumerate(bereiche)}},
        check_synthese={"bedingt_bedingungen": ["Schichtmodell klären", "Einarbeitung schriftlich"],
                        "risiko_board": [
                            {"risiko": "Frühdienst ab 4 Uhr", "schwere": "hoch", "status": "ungeklaert", "naechster_schritt": "Nachfragen"},
                            {"risiko": "Tourengröße unklar", "schwere": "mittel", "status": "in_klaerung", "naechster_schritt": None},
                            {"risiko": "Fahrzeug", "schwere": "gering", "status": "geklaert", "naechster_schritt": "-"}],
                        "begruendung": "Die Rolle passt zum Profil, zwei Punkte sind offen.",
                        "kern_je_kopf": [{"kopf": k, "kern": f"Kernaussage von {k}"} for k in sorted(koepfe) if k != "kopf7"],
                        "empfehlung": "Bewerben, wenn der Frühdienst akzeptabel ist."},
        company_fit_fehlt=True, synthese_fehler=None, job_firma="Beispiel GmbH", job_titel="Zusteller/in (m/w/d)",
        job_id=1, mitglieder=koepfe, abstimmung=abstimmung,
        beitraege=[{"anzeige": f"Beiratsmitglied {i}", "farbe": ["#0B1F3A", "#7C4DFF", "#18A957"][i % 3],
                    "text": f"Beitrag {i}: Eine kurze Einschätzung."} for i in range(1, 4)],
        moderationen=[{"text": f"Frage {i}: Was spricht dafür?"} for i in range(1, 4)])
    (ZIEL / "beirat.html").write_text(be._dashboard_html(d), encoding="utf-8")


def digest():
    from pipeline import digest as dg
    (ZIEL / "digest.html").write_text(dg.build_digest_html(), encoding="utf-8")


def coach():
    from sqlmodel import Session
    from app.db import engine
    from app.models import Company, Job
    from pipeline import coach_export as ce
    with Session(engine) as s:
        job = s.get(Job, STATE["job_id"])
        if job and job.company_id and STATE.get("fit_rel"):
            firma = s.get(Company, job.company_id)
            firma.fit_analysis_path = STATE["fit_rel"]
            s.add(firma)
            s.commit()
    ce.export()
    shutil.copytree(ce._EXPORT_DIR, ZIEL / "coach_site", dirs_exist_ok=True)


def doku_fest():
    from pipeline import docs_render as dr
    quelle = ("# Beispiel-Anleitung\n\nEin kurzer Einleitungstext mit **Fettdruck**, `Code` und einem "
              "[Verweis](https://example.invalid/).\n\n---\n\n## Erster Abschnitt\n\n- Punkt eins\n- Punkt zwei\n\n"
              "1. Schritt\n2. Schritt\n\n> Ein Hinweis in einem Zitat.\n\n## Tabelle\n\n| Spalte A | Spalte B |\n"
              "|---|---|\n| eins | zwei |\n| drei | vier |\n\n## Code\n\n```\nstart.command\n```\n\n"
              "### Unterabschnitt\n\nNoch ein Absatz.\n")
    (ZIEL / "doku_fest.html").write_text(dr.render_markdown(quelle, "BEISPIEL.md"), encoding="utf-8")


def doku_app():
    from app import doku
    # FUNKTIONEN.md ändert sich selten; die Anleitung bekommt mit jeder Fassung neue Sätze und störte den
    # Vergleich des Aussehens (Rückfall auf die Anleitung, falls es die Funktionsübersicht nicht gibt).
    eintrag_ = doku.eintrag_fuer("funktionen") or doku.eintrag_fuer("anleitung")
    if eintrag_ is None:
        raise RuntimeError("Weder 'funktionen' noch 'anleitung' im Katalog")
    (ZIEL / "doku_app.html").write_text(doku.rendern(eintrag_), encoding="utf-8")


def excel():
    from pipeline import export_excel as ex
    ordner = ZIEL / "_excel"
    ordner.mkdir(parents=True, exist_ok=True)
    ex.EXPORT_DIR = ordner
    pfad = ex.build_workbook()
    kopieren(pfad, "excel.xlsx")
    shutil.rmtree(ordner, ignore_errors=True)


try:
    vorbereiten()
except BaseException:                                                # noqa: BLE001
    ERGEBNIS["vorbereiten"] = traceback.format_exc()[-1800:]
else:
    for name, funktion in (("company_fit", company_fit), ("debrief", debrief), ("snapshot", snapshot),
                           ("cleanup", cleanup), ("beirat", beirat), ("digest", digest), ("coach", coach),
                           ("doku_fest", doku_fest), ("doku_app", doku_app), ("excel", excel)):
        eintrag(name, funktion)
(ZIEL.parent / "erzeuger.json").write_text(json.dumps(ERGEBNIS, indent=1, ensure_ascii=False), encoding="utf-8")
'''


def berichte_erzeugen(stand: Stand, lauf: Lauf, ziel: Path) -> dict:
    """Startet den Erzeuger als eigenen Prozess im Programmordner der Probe und liest sein Ergebnis."""
    ziel.mkdir(parents=True, exist_ok=True)
    skript = lauf.werkzeug / "berichte_erzeugen.py"
    skript.write_text(ERZEUGER, encoding="utf-8")
    env = lauf.umgebung(VGL_ZIEL=ziel)
    logdatei = ziel / "erzeuger.log"
    p = prozess_starten([VENV_PYTHON, "-I", skript], env=env, cwd=str(lauf.kanon / "backend"), logdatei=logdatei)
    try:
        p.wait(timeout=300)
    except subprocess.TimeoutExpired:
        prozess_beenden(p)
        raise WerkzeugFehler(f"Berichte ({stand.name}): Zeitüberschreitung nach 300 s.")
    finally:
        prozess_beenden(p)
    erg_pfad = ziel / "erzeuger.json"
    if not erg_pfad.is_file():
        raise WerkzeugFehler(f"Berichte ({stand.name}): Erzeuger ohne Ergebnis:\n"
                             + logdatei.read_text(encoding="utf-8", errors="replace")[-2000:])
    return json.loads(erg_pfad.read_text(encoding="utf-8"))


# ── Excel: Teile vergleichen ────────────────────────────────────────────────────────────────
def excel_teile(xlsx: Path, heute: str, treffer: dict) -> dict:
    """{Teilname: lesbarer Text} einer Excel-Datei. docProps/core.xml: Zeitstempel maskiert (M4)."""
    teile = {}
    with zipfile.ZipFile(xlsx) as zf:
        for name in sorted(zf.namelist()):
            if name.endswith("/"):
                continue
            daten = zf.read(name)
            try:
                text = daten.decode("utf-8")
            except UnicodeDecodeError:
                teile[name] = f"<binär {len(daten)} Bytes sha256 {hashlib.sha256(daten).hexdigest()[:16]}>"
                continue
            if name == "docProps/core.xml":
                text, n = re.subn(r"(<dcterms:(?:created|modified)[^>]*>)[^<]*(</dcterms:)", r"\1‹ZEITPUNKT›\2", text)
                if n:
                    treffer["M4 Excel dcterms:created/modified"] = treffer.get("M4 Excel dcterms:created/modified", 0) + n
            text = re.sub(r">\s*<", ">\n<", text)
            teile[name] = masken_anwenden(text, heute, treffer)
    return teile


# ── Ablauf: ein Stand durch die Oberfläche ──────────────────────────────────────────────────
def seiten_aus_layout(programm: Path) -> list:
    """(Pfad, Beschriftung) aus dem NAV-Feld von components/Layout.tsx (Reihenfolge der Seitenleiste)."""
    datei = programm / "frontend" / "src" / "components" / "Layout.tsx"
    if not datei.is_file():
        return []
    text = datei.read_text(encoding="utf-8")
    return re.findall(r"\{\s*to:\s*'([^']+)'\s*,\s*label:\s*'([^']+)'", text)


def seitenname(pfad: str) -> str:
    return "dashboard" if pfad == "/" else pfad.strip("/").replace("/", "_")


def stellen_waehlen(port: int) -> list:
    """Zwei Stellen-Detailseiten aus den Beispieldaten: eine „Beworben“, eine „Interview“ (sonst die
    ersten). Gefragt wird die laufende Probe (Port des Erstlaufs)."""
    status, daten = http_holen(port, "/api/jobs")
    if status != 200:
        return []
    antwort = json.loads(daten)
    if isinstance(antwort, dict):
        antwort = next((v for v in antwort.values() if isinstance(v, list)), [])
    stellen = [s for s in antwort if isinstance(s, dict) and "id" in s]
    stellen.sort(key=lambda s: s["id"])
    gewaehlt = []
    for wunsch in ("Beworben", "Interview"):
        treffer = next((s for s in stellen if s.get("status") == wunsch and s["id"] not in [g["id"] for g in gewaehlt]), None)
        if treffer:
            gewaehlt.append(treffer)
    for s in stellen:
        if len(gewaehlt) >= 2:
            break
        if s["id"] not in [g["id"] for g in gewaehlt]:
            gewaehlt.append(s)
    return [{"id": s["id"], "status": s.get("status")} for s in gewaehlt]


def oberflaeche_aufnehmen(stand: Stand, chrome: "Chrome", seiten: list, ziel: Path) -> dict:
    """Alle Seiten in beiden Fenstergrößen. Rückgabe: {Seitenname: {Fenster: {datei, …}}}."""
    erg = {}
    basis = f"http://127.0.0.1:{stand.port}"
    for eintrag, titel in seiten:
        pfad, _, klick = eintrag.partition("|")                 # „/dokumentation|Funktionen“: Reiter anklicken
        name = seitenname(pfad) + (f"_{klick.lower()}" if klick else "")
        erg[name] = {"pfad": eintrag, "titel": titel, "fenster": {}}
        for breite, hoehe, kuerzel in FENSTER:
            datei = ziel / f"{name}__{kuerzel}.png"
            try:
                info = chrome.aufnehmen_sicher(basis + pfad, datei, breite, hoehe, klick=klick or None)
                info["datei"] = str(datei)
            except (TimeoutError, OSError, WerkzeugFehler) as exc:
                info = {"fehler": str(exc)[:300], "datei": None}
                stand.warnungen.append(f"Aufnahme {name} ({kuerzel}) fehlgeschlagen: {exc}")
            erg[name]["fenster"][kuerzel] = info
        log(f"  {stand.name}: {name} aufgenommen")
    return erg


def berichte_aufnehmen(stand: Stand, chrome: "Chrome", dateien: list, ziel: Path) -> dict:
    """Bildschirmfotos der (maskierten) HTML-Berichte; alle <details> geöffnet."""
    erg = {}
    for rel, pfad in dateien:
        slug = rel.replace("/", "__").rsplit(".", 1)[0]
        erg[rel] = {}
        for breite, hoehe, kuerzel in FENSTER:
            datei = ziel / f"{slug}__{kuerzel}.png"
            try:
                info = chrome.aufnehmen_sicher(pfad.resolve().as_uri(), datei, breite, hoehe, details_oeffnen=True,
                                               stile=True)
                info["datei"] = str(datei)
                stile = info.pop("stile", None)
                if stile is not None:
                    stil_datei = ziel / f"{slug}__{kuerzel}.stile.json"
                    stil_datei.write_text(json.dumps(stile, ensure_ascii=False), encoding="utf-8")
                    info["stile_datei"] = str(stil_datei)
            except (TimeoutError, OSError, WerkzeugFehler) as exc:
                info = {"fehler": str(exc)[:300], "datei": None}
                stand.warnungen.append(f"Aufnahme Bericht {rel} ({kuerzel}) fehlgeschlagen: {exc}")
            erg[rel][kuerzel] = info
    return erg


def css_aus_dist(programm: Path) -> tuple:
    """(Text des gebauten CSS, Text von index.html) — das CSS, auf das index.html verweist."""
    index = programm / "frontend" / "dist" / "index.html"
    html_text = index.read_text(encoding="utf-8") if index.is_file() else ""
    m = re.search(r'<link[^>]+rel="stylesheet"[^>]+href="/(assets/[^"]+\.css)"', html_text)
    if not m:
        m = re.search(r'href="/(assets/[^"]+\.css)"', html_text)
    css = (programm / "frontend" / "dist" / m.group(1)).read_text(encoding="utf-8") if m else ""
    return css, html_text


def stand_durchlaufen(stand: Stand, lauf: Lauf, args, seiten: list, design: Path | None) -> dict:
    """Installiert den Stand am gemeinsamen Pfad, startet ihn, nimmt die Oberfläche auf, beendet ihn,
    erzeugt danach die Berichte und nimmt sie auf. Rückgabe: alle Rohergebnisse des Stands."""
    aus = lauf.ausgabe / stand.name
    ergebnis: dict = {"seiten": {}, "berichte": {}, "meta": {}}
    start = time.time()
    installieren(stand, lauf, mit_basis=True, design=design if stand.name == "neu" else None)
    stand.zeit("Installieren (Klon, Basis)", start)
    ergebnis["design_gelegt"] = bool(design is not None and stand.name == "neu")
    # Ein Chrome je Stand für Oberfläche UND Berichte (jeder Start weckt Chromes Updater; die
    # Netzsperre fängt das ab, weniger Starts sind trotzdem besser).
    with Chrome(lauf, stand.name) as chrome:
        stand.netzsperre = chrome.netzsperre
        _stand_durchlaufen_mit_chrome(stand, lauf, args, seiten, ergebnis, chrome)
    return ergebnis


def _stand_durchlaufen_mit_chrome(stand: Stand, lauf: Lauf, args, seiten: list, ergebnis: dict, chrome: "Chrome") -> None:
    aus = lauf.ausgabe / stand.name

    if args.nur in (None, "oberflaeche"):
        start = time.time()
        server = server_starten(stand, lauf, aus / "server.log")
        try:
            ergebnis["seiten"] = oberflaeche_aufnehmen(stand, chrome, seiten, aus / "seiten")
            # gebautes CSS, CSS-Block des Stands (falls es einen gibt), Version
            css, index_html = css_aus_dist(lauf.kanon)
            (aus / "css").mkdir(parents=True, exist_ok=True)
            (aus / "css" / "gebaut.css").write_text(css, encoding="utf-8")
            (aus / "css" / "index.html").write_text(index_html, encoding="utf-8")
            ergebnis["css"], ergebnis["index_html"] = css, index_html
            ergebnis["design_css"] = ""
            for pfad, name in (("/api/design.css", "design.css"), ("/api/design", "design.json")):
                try:
                    status, koerper = http_holen(stand.port, pfad)
                except OSError:
                    continue
                if status == 200:
                    (aus / "css" / name).write_bytes(koerper)
                    if name == "design.css":
                        ergebnis["design_css"] = koerper.decode("utf-8", "replace")
        finally:
            prozess_beenden(server)
        stand.zeit("Oberfläche aufnehmen", start)

    if args.nur in (None, "berichte"):
        start = time.time()
        roh_ziel = aus / "erzeuger"
        if roh_ziel.exists():
            shutil.rmtree(roh_ziel)
        er = berichte_erzeugen(stand, lauf, roh_ziel)
        ergebnis["erzeuger"] = er
        stand.zeit("Berichte erzeugen", start)
        heute = er.get("heute") or date.today().isoformat()
        treffer: dict = {}
        masken_ziel = aus / "berichte"
        if masken_ziel.exists():
            shutil.rmtree(masken_ziel)
        texte, html_dateien, excel_dict = {}, [], {}
        for pfad in sorted((roh_ziel / "roh").rglob("*")):
            if not pfad.is_file():
                continue
            rel = pfad.relative_to(roh_ziel / "roh").as_posix()
            if rel.endswith(".xlsx"):
                excel_dict[rel] = excel_teile(pfad, heute, treffer)
                zielpfad = masken_ziel / rel
                zielpfad.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(pfad, zielpfad)
                for teil, inhalt in excel_dict[rel].items():
                    tp = masken_ziel / f"{rel}.teile" / teil
                    tp.parent.mkdir(parents=True, exist_ok=True)
                    tp.write_text(inhalt, encoding="utf-8")
                continue
            try:
                roh = pfad.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                roh = f"<binär {pfad.stat().st_size} Bytes>"
            text = masken_anwenden(roh, heute, treffer)
            if rel.endswith(".FEHLER.txt"):
                text = text.strip().splitlines()[-1] if text.strip() else text    # nur „Typ: Meldung“
            zielpfad = masken_ziel / rel
            zielpfad.parent.mkdir(parents=True, exist_ok=True)
            zielpfad.write_text(text, encoding="utf-8")
            texte[rel] = text
            if rel.endswith(".html"):
                html_dateien.append((rel, zielpfad))
        ergebnis["berichte"] = {"texte": texte, "excel": excel_dict, "masken": treffer, "heute": heute,
                                "fehler": {k: v.get("fehler") for k, v in er.get("eintraege", {}).items() if not v.get("ok")},
                                "vorbereiten": er.get("vorbereiten")}
        start = time.time()
        ergebnis["berichte"]["bilder"] = berichte_aufnehmen(stand, chrome, html_dateien, aus / "berichte_bilder")
        stand.zeit("Berichte aufnehmen", start)


def erstlauf(stand: Stand, lauf: Lauf) -> list:
    """Der erste Stand erzeugt die Beispieldaten (frische Datenbank), wird beendet; Datenordner und
    neu entstandene Laufzeitdateien im Programmordner sind die gemeinsame Basis beider Stände.
    Rückgabe: die gewählten Stellen für die Detailseiten."""
    start = time.time()
    installieren(stand, lauf, mit_basis=False)
    vorher = baum_stand(lauf.kanon)
    server = server_starten(stand, lauf, lauf.arbeit / "erstlauf_server.log")
    try:
        stellen = stellen_waehlen(stand.port)
    finally:
        prozess_beenden(server)
    if not (lauf.kanon / "data" / "bewerbung.sqlite").is_file():
        raise WerkzeugFehler("Erstlauf: keine Datenbank entstanden.")
    if not (lauf.kanon / "data" / "beispieldaten.json").is_file():
        raise WerkzeugFehler("Erstlauf: Die Beispieldaten wurden nicht angelegt (siehe erstlauf_server.log).")
    nachher = baum_stand(lauf.kanon)
    geaendert = sorted(r for r, h in nachher.items() if vorher.get(r) != h)
    lauf.basis.mkdir(parents=True, exist_ok=True)
    shutil.copytree(lauf.kanon / "data", lauf.basis / "data")
    for rel in geaendert:
        ziel = lauf.basis / "dateien" / rel
        ziel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(lauf.kanon / rel, ziel)
    lauf.basis_dateien = geaendert
    stand.zeit("Erstlauf (Beispieldaten erzeugen)", start)
    return stellen


# ── Auswertung ──────────────────────────────────────────────────────────────────────────────
def _bilder_paare(paare: list) -> list:
    """Vergleicht Bildpaare parallel. `paare`: [(Schlüssel, Pfad alt, Pfad neu, Diffpfad)]."""
    if not paare:
        return []
    arbeiter = max(1, min(8, (os.cpu_count() or 2) - 1))
    with concurrent.futures.ProcessPoolExecutor(max_workers=arbeiter) as pool:
        futures = {pool.submit(bilder_vergleichen, a, b, d): k for k, a, b, d in paare}
        erg = {}
        for f in concurrent.futures.as_completed(futures):
            k = futures[f]
            try:
                erg[k] = f.result()
            except Exception as exc:                  # noqa: BLE001 -- ein Bildpaar darf den Lauf nicht kippen
                erg[k] = {"gleich": False, "modus": "Fehler", "abweichend": -1, "bereich": None, "fehler": repr(exc)}
    return [(k, erg[k]) for k, _, _, _ in paare]


def _diff_relativ(bilder: dict, ausgabe: Path) -> None:
    """Pfad des Differenzbilds relativ zum Ausgabeordner (für bericht.md)."""
    for f in bilder.values():
        if f.get("diff"):
            f["diff_rel"] = os.path.relpath(f["diff"], ausgabe)


def meta_kurz(meta: dict | None) -> str:
    """Lesbare Kurzform von Titel und Tab-Symbolen (Prüfsumme gekürzt)."""
    if not meta:
        return "(keine Angaben)"
    icons = ", ".join(f"{i.get('rel')}{' ' + i['sizes'] if i.get('sizes') else ''}: {str(i.get('sha'))[:8]}" for i in meta.get("icons", []))
    return f"Titel „{meta.get('titel')}“, Symbole [{icons}]"


def meta_schluessel(meta: dict | None) -> str:
    """Vergleichsform von Titel und Tab-Symbolen: Adresse des Symbols zählt nicht, sein Inhalt schon."""
    if not meta:
        return "keine Angaben"
    icons = [(i.get("rel"), i.get("sizes"), i.get("type"), i.get("sha")) for i in meta.get("icons", [])]
    return json.dumps({"titel": meta.get("titel"), "sprache": meta.get("sprache"), "icons": icons,
                       "themefarbe": meta.get("themefarbe")}, ensure_ascii=False, sort_keys=True)


def seiten_auswerten(alt: dict, neu: dict, ausgabe: Path) -> list:
    namen = list(alt["seiten"]) + [n for n in neu["seiten"] if n not in alt["seiten"]]
    paare, zeilen = [], []
    for n in namen:
        for _, _, k in FENSTER:
            a = alt["seiten"].get(n, {}).get("fenster", {}).get(k, {})
            b = neu["seiten"].get(n, {}).get("fenster", {}).get(k, {})
            if a.get("datei") and b.get("datei"):
                paare.append(((n, k), a["datei"], b["datei"], str(ausgabe / "diff" / "seiten" / f"{n}__{k}.diff.png")))
    bilder = dict(_bilder_paare(paare))
    _diff_relativ(bilder, ausgabe)
    for n in namen:
        pa, pn = alt["seiten"].get(n, {}), neu["seiten"].get(n, {})
        zeile = {"name": n, "pfad": pa.get("pfad") or pn.get("pfad"), "fenster": {}, "gruende": []}
        for _, _, k in FENSTER:
            a, b = pa.get("fenster", {}).get(k, {}), pn.get("fenster", {}).get(k, {})
            if (n, k) in bilder:
                zeile["fenster"][k] = bilder[(n, k)]
                if not bilder[(n, k)]["gleich"]:
                    zeile["gruende"].append(f"Bild {k}")
            else:
                zeile["fenster"][k] = {"gleich": False, "modus": "fehlt", "abweichend": -1,
                                       "fehler": (a.get("fehler") or b.get("fehler") or "Seite fehlt in einem Stand")}
                zeile["gruende"].append(f"Bild {k} nicht vergleichbar")
        ma, mn = (pa.get("fenster", {}).get(FENSTER[0][2], {}).get("meta"), pn.get("fenster", {}).get(FENSTER[0][2], {}).get("meta"))
        zeile["meta_alt"], zeile["meta_neu"] = ma, mn
        zeile["meta_gleich"] = meta_schluessel(ma) == meta_schluessel(mn)
        if not zeile["meta_gleich"]:
            zeile["gruende"].append("Titel/Tab-Symbol")
        zeile["instabil"] = [f"{s}:{k}" for s, p in (("alt", pa), ("neu", pn)) for k, f in p.get("fenster", {}).items()
                             if f.get("stabil") is False]
        zeile["abgeschnitten"] = [f"{s}:{k}" for s, p in (("alt", pa), ("neu", pn)) for k, f in p.get("fenster", {}).items()
                                  if f.get("abgeschnitten")]
        zeile["probleme_alt"] = sorted({x for f in pa.get("fenster", {}).values() for x in f.get("probleme", [])})
        zeile["probleme_neu"] = sorted({x for f in pn.get("fenster", {}).values() for x in f.get("probleme", [])})
        zeile["urteil"] = "gleich" if not zeile["gruende"] else "ungleich"
        zeilen.append(zeile)
    return zeilen


def berichte_auswerten(alt: dict, neu: dict, ausgabe: Path) -> list:
    ta, tn = alt["berichte"].get("texte", {}), neu["berichte"].get("texte", {})
    ea, en = alt["berichte"].get("excel", {}), neu["berichte"].get("excel", {})
    ba, bn = alt["berichte"].get("bilder", {}), neu["berichte"].get("bilder", {})
    namen = sorted(set(ta) | set(tn) | set(ea) | set(en))
    paare = []
    for n in namen:
        for _, _, k in FENSTER:
            a, b = ba.get(n, {}).get(k, {}), bn.get(n, {}).get(k, {})
            if a.get("datei") and b.get("datei"):
                slug = n.replace("/", "__").rsplit(".", 1)[0]
                paare.append(((n, k), a["datei"], b["datei"], str(ausgabe / "diff" / "berichte" / f"{slug}__{k}.diff.png")))
    bilder = dict(_bilder_paare(paare))
    _diff_relativ(bilder, ausgabe)
    zeilen = []
    for n in namen:
        zeile = {"name": n, "gruende": [], "hinweise": []}
        if n in ea or n in en:                                       # Excel
            zeile["art"] = "xlsx"
            teile_a, teile_n = ea.get(n), en.get(n)
            if teile_a is None or teile_n is None:
                zeile["gruende"].append("fehlt in " + ("alt" if teile_a is None else "neu"))
                zeile["datei"] = "fehlt"
            else:
                abweichend = [t for t in sorted(set(teile_a) | set(teile_n)) if teile_a.get(t) != teile_n.get(t)]
                zeile["datei"] = "bytegleich nach Masken" if not abweichend else "ungleich"
                zeile["teile_abweichend"] = abweichend
                for t in abweichend:
                    d = zeilen_diff(teile_a.get(t, ""), teile_n.get(t, ""), f"alt/{t}", f"neu/{t}")
                    (ausgabe / "diff" / "berichte").mkdir(parents=True, exist_ok=True)
                    (ausgabe / "diff" / "berichte" / f"{n}.{t.replace('/', '_')}.diff.txt").write_text("\n".join(d), encoding="utf-8")
                    zeile.setdefault("diffs", {})[t] = d[:BERICHT_DIFF_ZEILEN]
                    zeile["gruende"].append(f"Excel-Teil {t}")
            zeile["urteil"] = "gleich" if not zeile["gruende"] else "ungleich"
            zeilen.append(zeile)
            continue
        a, b = ta.get(n), tn.get(n)
        zeile["art"] = n.rsplit(".", 1)[-1]
        if a is None or b is None:
            zeile["gruende"].append("fehlt in " + ("alt" if a is None else "neu"))
            zeile["datei"] = "fehlt"
            zeile["urteil"] = "ungleich"
            zeilen.append(zeile)
            continue
        if a == b:
            zeile["datei"] = "bytegleich nach Masken"
        else:
            diff = zeilen_diff(a, b)
            (ausgabe / "diff" / "berichte").mkdir(parents=True, exist_ok=True)
            (ausgabe / "diff" / "berichte" / (n.replace("/", "__") + ".diff.txt")).write_text("\n".join(diff), encoding="utf-8")
            zeile["diff_zeilen"] = len([z for z in diff if z[:1] in "+-" and z[:3] not in ("+++", "---")])
            zeile["diff_kopf"] = diff[:BERICHT_DIFF_ZEILEN]
            if n.endswith(".html"):
                stil_a, rest_a = stil_und_rest(a)
                stil_b, rest_b = stil_und_rest(b)
                zeile["inhalt_gleich"] = rest_a == rest_b
                if not zeile["inhalt_gleich"]:
                    d2 = zeilen_diff(rest_a, rest_b)
                    zeile["gruende"].append("Inhalt (ohne Stil)")
                    zeile["inhalt_diff_kopf"] = d2[:BERICHT_DIFF_ZEILEN]
                css = css_vergleichen(stil_a, stil_b)
                zeile["css"] = {k: css[k] for k in ("urteil", "gleich")}
                zeile["css"]["unterschiede"] = css["unterschiede"][:BERICHT_DIFF_ZEILEN]
                zeile["css"]["anzahl"] = len(css["unterschiede"])
                zeile["regeln_gleich"] = css["gleich"]
                zeile["datei"] = ("Stil anders geschrieben, Regeln gleich" if css["gleich"] and zeile["inhalt_gleich"]
                                  else "ungleich")
            else:
                zeile["datei"] = "ungleich"
                zeile["gruende"].append("Textdatei")
        if n.endswith(".html"):
            zeile["bild"] = {}
            for _, _, k in FENSTER:
                if (n, k) in bilder:
                    zeile["bild"][k] = bilder[(n, k)]
                    if not bilder[(n, k)]["gleich"]:
                        zeile["gruende"].append(f"Bild {k}")
                else:
                    zeile["bild"][k] = {"gleich": False, "modus": "fehlt", "abweichend": -1}
                    zeile["gruende"].append(f"Bild {k} nicht vergleichbar")
            # Berechnete Stile aller Elemente in beiden Fenstergrößen (nur sinnvoll bei gleichem Inhalt)
            if zeile.get("datei") != "bytegleich nach Masken" and zeile.get("inhalt_gleich"):
                zeile["stile"] = {}
                for _, _, k in FENSTER:
                    sa, sn = ba.get(n, {}).get(k, {}).get("stile_datei"), bn.get(n, {}).get(k, {}).get("stile_datei")
                    zeile["stile"][k] = (stile_vergleichen(sa, sn) if sa and sn else
                                         {"gleich": False, "fehler": "keine Stildaten", "elemente": 0, "abweichend": -1, "beispiele": []})
                stile_gleich = all(s["gleich"] for s in zeile["stile"].values())
                if not stile_gleich:
                    zeile["gruende"].append("Berechnete Stile")
                if not zeile.get("regeln_gleich", True):
                    if stile_gleich:
                        zeile["datei"] = "Stil umgeschrieben, Wirkung gleich"
                    else:
                        zeile["gruende"].append("Stil-Regeln")
            elif not zeile.get("regeln_gleich", True):
                zeile["gruende"].append("Stil-Regeln")
        zeile["urteil"] = "gleich" if not zeile["gruende"] else "ungleich"
        zeilen.append(zeile)
    return zeilen


def stile_vergleichen(pfad_a: str, pfad_b: str, beispiele: int = 12) -> dict:
    """Vergleicht die berechneten Stile zweier Seiten Element für Element (Reihenfolge im Dokument)."""
    try:
        a = json.loads(Path(pfad_a).read_text(encoding="utf-8"))
        b = json.loads(Path(pfad_b).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"gleich": False, "fehler": str(exc), "elemente": 0, "abweichend": -1, "beispiele": []}
    ea, eb = a["elemente"], b["elemente"]
    if len(ea) != len(eb) or a["eigenschaften"] != b["eigenschaften"]:
        return {"gleich": False, "elemente": [len(ea), len(eb)], "abweichend": -1,
                "beispiele": [f"Elementzahl verschieden: alt {len(ea)}, neu {len(eb)}"]}
    namen = a["eigenschaften"]
    abweichend, elemente_betroffen, bsp = 0, 0, []
    for (ka, va), (kb, vb) in zip(ea, eb):
        if va == vb and ka == kb:
            continue
        elemente_betroffen += 1
        wa, wb = va.split("\u0001"), vb.split("\u0001")
        for n, x, y in zip(namen, wa, wb):
            if x != y:
                abweichend += 1
                if len(bsp) < beispiele:
                    bsp.append(f"{ka}: {n}: {x[:70]} -> {y[:70]}")
        if ka != kb and len(bsp) < beispiele:
            bsp.append(f"Kennung verschieden: {ka} -> {kb}")
    return {"gleich": elemente_betroffen == 0, "elemente": len(ea), "abweichend": abweichend,
            "elemente_betroffen": elemente_betroffen, "beispiele": bsp}


def css_auswerten(alt: dict, neu: dict) -> dict:
    erg = css_vergleichen(alt.get("css", ""), neu.get("css", ""), alt.get("design_css", ""), neu.get("design_css", ""))
    erg["bytes"] = [len(alt.get("css", "")), len(neu.get("css", ""))]
    erg["design_css_vorhanden"] = [bool(alt.get("design_css")), bool(neu.get("design_css"))]
    return erg


def index_hinweis(alt: dict, neu: dict) -> list:
    """index.html der gebauten Oberfläche, Asset-Hashes vereinheitlicht — nur zur Auskunft."""
    def norm(t):
        return re.sub(r"(index|[a-z0-9-]+)-[A-Za-z0-9_-]{8}\.(js|css)", r"\1-HASH.\2", t)
    return zeilen_diff(norm(alt.get("index_html", "")), norm(neu.get("index_html", "")))


# ── bericht.md ──────────────────────────────────────────────────────────────────────────────
def _zelle(f: dict | None) -> str:
    if not f:
        return "-"
    if f.get("gleich"):
        return "gleich" if f.get("modus") in ("bytegleich", "pixelgleich", "gleiche Bilddaten") else "gleich"
    if f.get("abweichend", 0) < 0:
        return f"FEHLER ({f.get('fehler', f.get('modus'))})"
    x0, y0, x1, y1 = f["bereich"] or (0, 0, 0, 0)
    groesse = ""
    if f.get("groesse_a") != f.get("groesse_b"):
        groesse = f", Größe {f['groesse_a'][0]}x{f['groesse_a'][1]} gegen {f['groesse_b'][0]}x{f['groesse_b'][1]}"
    diff = f", Diff `{f['diff_rel']}`" if f.get("diff_rel") else ""
    return (f"UNGLEICH ({f['abweichend']} Punkte, größter Kanalabstand {f.get('max_kanal', '?')}, "
            f"Bereich x{x0}-{x1} y{y0}-{y1}{groesse}{diff})")


def _ueberblick(z: dict) -> list:
    """Eine Zeile je ungleiche Seite oder je ungleichem Bericht: Zahl der abweichenden Punkte, größter
    Kanalabstand, Pfad des Differenzbilds — und die Gründe, die kein Bild sind."""
    zeilen = []
    for typ, eintraege in (("Seite", z["seiten"]), ("Bericht", z["berichte"])):
        for e in eintraege:
            if e["urteil"] == "gleich":
                continue
            teile = []
            for k, f in (e.get("fenster") or e.get("bild") or {}).items():
                if not f.get("gleich"):
                    teile.append(f"{k} px: {_zelle(f)}")
            rest = [g for g in e["gruende"] if not g.startswith("Bild ")]
            if rest:
                teile.append("weitere Gründe: " + ", ".join(rest))
            zeilen.append(f"- {typ} `{e['name']}`: " + "; ".join(teile))
    return zeilen


def _urteil_text(z: dict) -> str:
    """Urteil mit Grund: `gleich`, `gleich (CSS anders geschrieben)` oder `ungleich (Gründe; Bild gleich)`."""
    if z["urteil"] == "gleich":
        zusatz = {"Stil anders geschrieben, Regeln gleich": " (CSS anders geschrieben, Regeln gleich)",
                  "Stil umgeschrieben, Wirkung gleich": " (CSS umgeschrieben, berechnete Stile aller Elemente und Bild gleich)"}
        return "**gleich**" + zusatz.get(z.get("datei"), "")
    grund = ", ".join(z["gruende"])
    bilder = z.get("bild") or z.get("fenster") or {}
    if bilder and all(f.get("gleich") for f in bilder.values()):
        grund += "; Bild gleich"
    return f"**ungleich** ({grund})"


def bericht_schreiben(ctx: dict) -> str:
    z = ctx
    zeilen = ["# Design-Vergleich", ""]
    zeilen += [f"Erzeugt am {z['zeit']} mit `design_vergleich.py` (Abnahme P2-72, Paket V).", ""]
    zeilen += ["**Aufruf:** `" + " ".join(z["aufruf"]) + "`", ""]
    zeilen += ["## Ergebnis", ""]
    zeilen += [f"**{'ALLES GLEICH' if z['alles_gleich'] else 'UNTERSCHIEDE GEFUNDEN'}** — "
               f"Seiten: {z['seiten_gleich']} von {len(z['seiten'])} gleich; "
               f"Berichte: {z['berichte_gleich']} von {len(z['berichte'])} gleich; "
               f"gebautes CSS: {z['css']['urteil'] if z['css'] else 'nicht verglichen'}.", ""]
    ueberblick = _ueberblick(z)
    if ueberblick:
        zeilen += ["## Unterschiede im Überblick", ""] + ueberblick + [""]
    zeilen += ["## Stände", "", "| | Stand | Version | Bau |", "|---|---|---|---|"]
    for s in z["staende"]:
        bau = ", ".join(f"{n} {t} s" for n, t in s["schritte"])
        tsc = "tsc ohne Fehler" if s["tsc_ok"] else ("tsc MIT FEHLERN" if s["tsc_ok"] is False else "tsc nicht gelaufen")
        sperre = ("Chrome mit Netzsperre (nur localhost)" if s.get("netzsperre")
                  else "Chrome OHNE Netzsperre (sandbox-exec fehlt), nur Namensregel auf 127.0.0.1")
        zeilen.append(f"| {s['name']} | {s['beschreibung']} | {s['version']} | {tsc}; Port {s['port']}; {sperre}; {bau} |")
    zeilen.append("")
    if z.get("design"):
        zeilen += [f"Design-Überschreibung für den neuen Stand: `{z['design']}` (nach `data/design/design.json` gelegt).", ""]
    if z.get("basis_dateien"):
        zeilen += ["Aus dem Erstlauf (Beispieldaten) in beide Stände übernommene Laufzeitdateien außerhalb von `data/`: "
                   + ", ".join(f"`{d}`" for d in z["basis_dateien"]) + ".", ""]
    for s in z["staende"]:
        for h in s["hinweise"]:
            zeilen.append(f"- Hinweis ({s['name']}): {h}")
        for w in s["warnungen"]:
            zeilen.append(f"- WARNUNG ({s['name']}): {w}")
        if s["tsc_ok"] is False:
            zeilen += ["", f"Typprüfung ({s['name']}) meldet Fehler:", "", "```", s["tsc_ausgabe"][-1500:], "```"]
    zeilen.append("")

    if z["seiten"]:
        zeilen += ["## Oberfläche (Bildschirmfotos, bildpunktgenau)", "",
                   "| Seite | 1440x900 | 390x844 | Titel/Tab-Symbol | Urteil |", "|---|---|---|---|---|"]
        for s in z["seiten"]:
            zeilen.append(f"| `{s['name']}` | {_zelle(s['fenster'].get('1440'))} | {_zelle(s['fenster'].get('390'))} | "
                          f"{'gleich' if s['meta_gleich'] else 'UNGLEICH'} | {_urteil_text(s)} |")
        zeilen.append("")
        meta_gruppen: dict = {}
        for s in z["seiten"]:
            if not s["meta_gleich"]:
                meta_gruppen.setdefault((meta_kurz(s["meta_alt"]), meta_kurz(s["meta_neu"])), []).append(s["name"])
        for (ma, mn), namen in meta_gruppen.items():
            zeilen += [f"- Titel/Tab-Symbol verschieden bei {len(namen)} Seiten ({', '.join(namen[:4])}{', …' if len(namen) > 4 else ''}): "
                       f"alt {ma} — neu {mn}"]
        for s in z["seiten"]:
            if s["instabil"]:
                zeilen += [f"- `{s['name']}`: Seite nicht zur Ruhe gekommen ({', '.join(s['instabil'])}) — Aufnahme trotzdem gemacht."]
            if s["abgeschnitten"]:
                zeilen += [f"- `{s['name']}`: höher als {MAX_SEITENHOEHE} px, abgeschnitten ({', '.join(s['abgeschnitten'])})."]
            for st in ("alt", "neu"):
                p = s["probleme_" + st]
                if p:
                    zeilen += [f"- Konsole/Netz `{s['name']}` ({st}): " + "; ".join(p[:4])]
        zeilen.append("")
        ungleich = [s for s in z["seiten"] if s["urteil"] == "ungleich"]
        if ungleich:
            zeilen += ["Differenzbilder: `diff/seiten/<seite>__<breite>.diff.png` (blasse Seite, abweichende Punkte magenta, Bereich rot umrahmt).", ""]

    if z["css"] is not None:
        c = z["css"]
        zeilen += ["## Gebautes CSS", "", f"- Urteil: **{c['urteil']}** ({c['bytes'][0]} gegen {c['bytes'][1]} Bytes)",
                   f"- CSS-Block des Stands (`/api/design.css`) vorhanden: alt {c['design_css_vorhanden'][0]}, neu {c['design_css_vorhanden'][1]}"]
        if c.get("rundung"):
            zeilen += ["", "Nur durch Rundung verschiedene Alphawerte (alt, neu), Beispiele:", "", "```diff"] + c["rundung"][:12] + ["```"]
        if not c["gleich"]:
            zeilen += ["", "```diff"] + c["unterschiede"][:60] + ["```"]
            if len(c["unterschiede"]) > 60:
                zeilen.append(f"… und {len(c['unterschiede']) - 60} weitere Zeilen (vollständig: `diff/css.diff.txt`).")
        zeilen.append("")
        if z.get("index_diff"):
            zeilen += ["Hinweis (nicht gewertet): `index.html` der gebauten Oberfläche unterscheidet sich (Asset-Hashes vereinheitlicht):", "",
                       "```diff"] + z["index_diff"][:30] + ["```", ""]

    if z["berichte"]:
        zeilen += ["## Berichte", "",
                   "Spalten: Datei = Text nach den Masken; Inhalt = Dokument ohne `<style>`; Stil = Regeln nach Auflösen der Variablen; "
                   "Bild = Bildschirmfoto (alle `<details>` geöffnet).", "",
                   "| Bericht | Datei | Inhalt | Stil-Regeln | Berechnete Stile | Bild 1440 | Bild 390 | Urteil |",
                   "|---|---|---|---|---|---|---|---|"]
        for b in z["berichte"]:
            fehlt = b.get("datei") == "fehlt"
            inhalt = ("gleich" if b.get("inhalt_gleich", True) else "UNGLEICH") if b["art"] == "html" and not fehlt else "-"
            stil = (b["css"]["urteil"] if b.get("css") else ("gleich" if b["art"] == "html" and not fehlt else "-"))
            bild = b.get("bild", {})
            st = b.get("stile")
            if st:
                if all(s["gleich"] for s in st.values()):
                    berechnet = f"gleich ({st['1440']['elemente']} Elemente)"
                else:
                    berechnet = "UNGLEICH (" + "; ".join(f"{k}: {s.get('abweichend')} Eigenschaften an {s.get('elemente_betroffen', '?')} Elementen"
                                                          for k, s in st.items() if not s["gleich"]) + ")"
            else:
                berechnet = "-"
            zeilen.append(f"| `{b['name']}` | {b.get('datei', '-')} | {inhalt} | {stil} | {berechnet} | {_zelle(bild.get('1440'))} | "
                          f"{_zelle(bild.get('390'))} | {_urteil_text(b)} |")
        zeilen.append("")
        for b in z["berichte"]:
            if b["urteil"] == "gleich" and b.get("datei") == "bytegleich nach Masken":
                continue
            kopf = b.get("diff_kopf") or []
            if kopf or b.get("diffs") or b.get("inhalt_diff_kopf") or b.get("stile"):
                zeilen += [f"### {b['name']}", ""]
                if b.get("inhalt_diff_kopf"):
                    zeilen += ["Inhalt (ohne Stil):", "", "```diff"] + b["inhalt_diff_kopf"] + ["```", ""]
                if b.get("stile") and not all(s["gleich"] for s in b["stile"].values()):
                    for k, s in b["stile"].items():
                        if not s["gleich"]:
                            zeilen += [f"Berechnete Stile bei {k} px (Beispiele):", "", "```"] + s["beispiele"] + ["```", ""]
                if b.get("css") and not b["css"]["gleich"]:
                    gewertet = "" if "Stil-Regeln" in b["gruende"] else " — nicht gewertet, berechnete Stile und Bild sind gleich"
                    zeilen += [f"Stil-Regeln ({b['css']['anzahl']} abweichende Zeilen{gewertet}):", "", "```diff"] + b["css"]["unterschiede"] + ["```", ""]
                elif kopf and b.get("css") and b["css"]["gleich"] and b.get("inhalt_gleich"):
                    zeilen += ["Nur die Schreibweise des CSS unterscheidet sich (Regeln nach dem Auflösen gleich). Zeilen-Diff:", "",
                               "```diff"] + kopf + ["```", ""]
                for t, d in (b.get("diffs") or {}).items():
                    zeilen += [f"Excel-Teil `{t}`:", "", "```diff"] + d + ["```", ""]

    if z["masken"]:
        zeilen += ["## Masken (Treffer je Stand)", "", "| Maske | alt | neu |", "|---|---|---|"]
        for name in sorted(set(z["masken"]["alt"]) | set(z["masken"]["neu"])):
            zeilen.append(f"| {name} | {z['masken']['alt'].get(name, 0)} | {z['masken']['neu'].get(name, 0)} |")
        zeilen.append("")
    if z.get("erzeuger_fehler"):
        zeilen += ["## Erzeuger mit Fehler", ""]
        for st, fehler in z["erzeuger_fehler"].items():
            for name, text in fehler.items():
                zeilen += [f"- {st} / {name}:", "", "```", (text or "")[-600:], "```", ""]

    zeilen += ["## Grenzen", "",
               "- Bildschirmfotos decken nur die aufgenommenen Seiten und Zustände ab (keine offenen Menüs, Formulare, Zeigerzustände).",
               "- Aufgenommen wird mit Chrome ohne Fenster auf diesem Rechner; Schrift und Anti-Aliasing sind nur gegen Läufe mit derselben Chrome-Version vergleichbar.",
               "- Das Tagesdatum des Erzeugerlaufs wird maskiert; ein Lauf über Mitternacht stimmt nicht mehr.",
               "- Berechnete Stile decken keine Regeln für Zeigerzustand, Fokus und Druck ab; dort entscheidet nur der Vergleich der Stil-Regeln (immer im Bericht aufgeführt).",
               "- Die Beispieldaten sind klein; Zustände, die nur große Datenbestände zeigen, fehlen.",
               "- Berichte, die ein Modell schreibt (Match, ATS-Scan, Briefing, Absagen-Analyse, Angebotsvergleich), sind nicht Teil dieses Werkzeugs.", ""]
    if z["dauer"]:
        zeilen += [f"Gesamtdauer: {z['dauer']} s.", ""]
    return "\n".join(zeilen)


# ── Hauptprogramm ───────────────────────────────────────────────────────────────────────────
def argumente(argv=None):
    p = argparse.ArgumentParser(description="Design-Vergleich zweier Stände des BMS (Abnahme P2-72).")
    p.add_argument("--alt", required=True, help="ZIP, Ordner oder `arbeitsbaum`")
    p.add_argument("--neu", required=True, help="ZIP, Ordner oder `arbeitsbaum`")
    p.add_argument("--ausgabe", required=True, help="Ausgabeordner")
    p.add_argument("--design", help="design.json (oder `probe` für das eingebaute Probe-Design), wird als "
                                    "data/design/design.json in den NEUEN Stand gelegt")
    p.add_argument("--nur", choices=("oberflaeche", "berichte"), help="nur diesen Teil ausführen")
    p.add_argument("--scratch", default=str(Path(tempfile.gettempdir()) / "bms_design_vergleich"))
    p.add_argument("--projekt", default=str(PROJEKT_STANDARD), help="Projektordner für `arbeitsbaum`")
    p.add_argument("--port-alt", type=int, default=18801)
    p.add_argument("--port-neu", type=int, default=18802)
    p.add_argument("--behalten", action="store_true", help="Arbeitsordner des Laufs nicht löschen")
    return p.parse_args(argv)


def hauptlauf(args) -> int:
    gestartet = time.time()
    ausgabe = Path(args.ausgabe).expanduser().resolve()
    scratch = Path(args.scratch).expanduser().resolve()
    projekt = Path(args.projekt).expanduser().resolve()
    projekt_text = str(projekt)
    for verboten in (str(scratch), str(ausgabe)):
        if verboten == projekt_text or verboten.startswith(projekt_text + os.sep):
            raise WerkzeugFehler(f"Scratch- und Ausgabeordner müssen außerhalb des Projekts liegen: {verboten}")
    design = None
    if args.design and args.design != "probe":
        design = Path(args.design).expanduser().resolve()
        if not design.is_file():
            raise WerkzeugFehler(f"--design: {design} gibt es nicht.")
    # Ein früherer Lauf des Werkzeugs darf überschrieben werden; ein fremder, nicht leerer Ordner nie.
    if ausgabe.exists() and any(ausgabe.iterdir()):
        if not (ausgabe / AUSGABE_MARKE).is_file():
            raise WerkzeugFehler(f"Der Ausgabeordner {ausgabe} ist nicht leer und stammt nicht von diesem "
                                 f"Werkzeug (Markendatei {AUSGABE_MARKE} fehlt). Bitte einen neuen Ordner angeben.")
        shutil.rmtree(ausgabe)
    ausgabe.mkdir(parents=True, exist_ok=True)
    (ausgabe / AUSGABE_MARKE).write_text("Ausgabe von design_vergleich.py (P2-72)\n", encoding="utf-8")
    scratch.mkdir(parents=True, exist_ok=True)
    if not VENV_PYTHON.exists():
        raise WerkzeugFehler(f"{VENV_PYTHON} fehlt.")

    lauf = Lauf(scratch, ausgabe)
    if args.design == "probe":
        design = probe_design_schreiben(lauf.werkzeug / "probe_design")
    _LAUF_ORDNER.append(lauf.arbeit)
    log(f"Arbeitsordner: {lauf.arbeit}")
    probeserver_vorbereiten(lauf)
    port_alt = freier_port(args.port_alt)
    port_neu = freier_port(max(args.port_neu, port_alt + 1))
    alt, neu = Stand("alt", args.alt, lauf, port_alt), Stand("neu", args.neu, lauf, port_neu)
    staende = (alt, neu)

    log("Stände bereitstellen und Oberfläche bauen (parallel)")
    fehler = []

    def vorbereiten(s):
        try:
            stand_bereitstellen(s, projekt)
            oberflaeche_bauen(s)
        except BaseException as exc:            # noqa: BLE001 -- im Hauptthread neu auslösen
            fehler.append((s.name, exc))

    faeden = [threading.Thread(target=vorbereiten, args=(s,)) for s in staende]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join()
    if fehler:
        name, exc = fehler[0]
        if isinstance(exc, WerkzeugFehler):
            raise exc
        raise WerkzeugFehler(f"Stand {name}: {''.join(traceback.format_exception(exc))[-1500:]}")
    for s in staende:
        log(f"  {s.name}: {s.beschreibung} — " + ", ".join(f"{n} {t} s" for n, t in s.schritte))

    log("Erstlauf: Beispieldaten erzeugen")
    stellen = erstlauf(alt, lauf)
    seiten = seiten_aus_layout(alt.programm)
    for p_, t_ in seiten_aus_layout(neu.programm):
        if p_ not in [x for x, _ in seiten]:
            seiten.append((p_, t_))
    if not seiten:
        raise WerkzeugFehler("Keine Seitenleisten-Einträge in components/Layout.tsx gefunden.")
    if "/outreach" not in [p_ for p_, _ in seiten]:
        seiten.append(("/outreach", "Outreach"))
    if "/jobs/neu" not in [p_ for p_, _ in seiten]:
        seiten.append(("/jobs/neu", "Neue Stelle"))
    for s in stellen:
        seiten.append((f"/jobs/{s['id']}", f"Stelle {s['id']} ({s['status']})"))
    # Die Doku-Seite zeigt zuerst den Reiter „Version“ (= CHANGELOG.md, ändert sich mit jeder Fassung).
    # Der Reiter „Funktionen“ (FUNKTIONEN.md) ändert sich selten und prüft das Aussehen sauber.
    seiten.append(("/dokumentation|Funktionen", "Dokumentation, Reiter Funktionen"))
    log(f"{len(seiten)} Seiten: " + ", ".join(seitenname(p_.partition("|")[0]) + ("_" + p_.partition("|")[2].lower() if "|" in p_ else "")
                                       for p_, _ in seiten))

    ergebnisse = {}
    for s in staende:
        log(f"Stand {s.name} durchlaufen (Port {s.port})")
        ergebnisse[s.name] = stand_durchlaufen(s, lauf, args, seiten, design)

    log("Auswerten")
    ctx = {"zeit": datetime.now().strftime("%d.%m.%Y %H:%M:%S"), "aufruf": sys.argv[:1] and ["design_vergleich.py"] + sys.argv[1:],
           "seiten": [], "berichte": [], "css": None, "index_diff": [], "masken": None, "design": ("eingebautes Probe-Design" if args.design == "probe" else str(design)) if design else None,
           "dauer": None, "staende": [], "erzeuger_fehler": {}}
    a, n = ergebnisse["alt"], ergebnisse["neu"]
    if args.nur in (None, "oberflaeche"):
        ctx["seiten"] = seiten_auswerten(a, n, ausgabe)
        ctx["css"] = css_auswerten(a, n)
        ctx["index_diff"] = index_hinweis(a, n)
        if not ctx["css"]["gleich"]:
            (ausgabe / "diff").mkdir(parents=True, exist_ok=True)
            (ausgabe / "diff" / "css.diff.txt").write_text("\n".join(ctx["css"]["unterschiede"]), encoding="utf-8")
    if args.nur in (None, "berichte"):
        ctx["berichte"] = berichte_auswerten(a, n, ausgabe)
        ctx["masken"] = {"alt": a["berichte"].get("masken", {}), "neu": n["berichte"].get("masken", {})}
        for st, e in (("alt", a), ("neu", n)):
            if e["berichte"].get("fehler"):
                ctx["erzeuger_fehler"][st] = e["berichte"]["fehler"]
            if e["berichte"].get("vorbereiten"):
                ctx["erzeuger_fehler"].setdefault(st, {})["vorbereiten"] = e["berichte"]["vorbereiten"]
    ctx["seiten_gleich"] = sum(1 for s in ctx["seiten"] if s["urteil"] == "gleich")
    ctx["berichte_gleich"] = sum(1 for b in ctx["berichte"] if b["urteil"] == "gleich")
    ctx["alles_gleich"] = (ctx["seiten_gleich"] == len(ctx["seiten"]) and ctx["berichte_gleich"] == len(ctx["berichte"])
                           and (ctx["css"] is None or ctx["css"]["gleich"])
                           and not ctx["erzeuger_fehler"] and all(s.tsc_ok is not False for s in staende))
    ctx["dauer"] = round(time.time() - gestartet)
    ctx["basis_dateien"] = list(lauf.basis_dateien)
    ctx["staende"] = [{"name": s.name, "beschreibung": s.beschreibung, "version": s.version, "port": s.port,
                       "schritte": s.schritte, "tsc_ok": s.tsc_ok, "tsc_ausgabe": s.tsc_ausgabe, "netzsperre": s.netzsperre,
                       "hinweise": s.hinweise, "warnungen": s.warnungen} for s in staende]
    (ausgabe / "bericht.md").write_text(bericht_schreiben(ctx), encoding="utf-8")
    (ausgabe / "ergebnis.json").write_text(json.dumps(ctx, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    log(f"Ergebnis: {'ALLES GLEICH' if ctx['alles_gleich'] else 'UNTERSCHIEDE'} — Seiten {ctx['seiten_gleich']}/{len(ctx['seiten'])}, "
        f"Berichte {ctx['berichte_gleich']}/{len(ctx['berichte'])}, CSS "
        f"{ctx['css']['urteil'] if ctx['css'] else '-'} — {ctx['dauer']} s. Bericht: {ausgabe / 'bericht.md'}")
    if not args.behalten:
        alle_prozesse_beenden()
        shutil.rmtree(lauf.arbeit, ignore_errors=True)
    return 0 if ctx["alles_gleich"] else 1


_LAUF_ORDNER: list = []


def _ordner_hinweis() -> None:
    if _LAUF_ORDNER and _LAUF_ORDNER[0].exists():
        print(f"(Der Arbeitsordner bleibt zur Fehlersuche stehen: {_LAUF_ORDNER[0]})", file=sys.stderr)


def main(argv=None) -> int:
    args = argumente(argv)
    signal.signal(signal.SIGINT, _abbruch)
    signal.signal(signal.SIGTERM, _abbruch)
    atexit.register(alle_prozesse_beenden)
    try:
        return hauptlauf(args)
    except WerkzeugFehler as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        _ordner_hinweis()
        return 2
    except SystemExit:
        raise
    except Exception:
        print("FEHLER (unerwartet):\n" + traceback.format_exc(), file=sys.stderr)
        _ordner_hinweis()
        return 2
    finally:
        alle_prozesse_beenden()


if __name__ == "__main__":
    sys.exit(main())
