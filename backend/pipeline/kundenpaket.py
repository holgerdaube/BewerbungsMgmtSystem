#!/usr/bin/env python3
"""Kundenpaket-Bauer (P2-50 Arbeitspaket A) — baut aus dem Git-Stand ein auslieferbares
Kunden-ZIP: ohne Entwicklungsdateien, ohne persönliche Daten des Entwicklers, mit ein paar
neutralisierten Dateien. `BMS_Install_MAC.md` und `BMS_Install_Windows.md` (P2-71, vorher
`BMS_Install.md` und `BMS_Install_Auto.md`) führen durch die Installation AUS einem solchen ZIP;
dieses Modul ist der Weg, es sauber zu BAUEN.

WARUM FAIL-CLOSED: Ausschließen und Ersetzen allein reichen nicht — ein künftiger Commit
könnte versehentlich wieder Personendaten in eine ausgelieferte Datei tragen (Doku, Skill,
Kommentar). Deshalb läuft nach jedem Bauversuch eine Prüfung über das FERTIGE Paket, und bei
auch nur einem Fund entsteht KEIN ZIP (Exit-Code 1). `test_echter_repo_stand_ist_auslieferbar`
lässt genau diese Prüfung dauerhaft über den echten Arbeitsbaum laufen — künftiges
Einschleppen wird damit zu einem roten CI-Lauf, nicht zu einem stillen Leck.

DIE PRÜFREGELN LIEGEN IN `pipeline/personendaten.py` (P2-83): Dieses Modul ruft sie mit dem
Umfang `"paket"` auf. Ihre persönlichen Muster (Anschrift, private Mail, LinkedIn, Namen Dritter,
Name des Nutzers, Firmennamen) kommen NICHT aus dem Code, sondern zur Laufzeit aus Profil,
Datenbank und der optionalen Musterdatei (`personendaten.muster_laden`). Fehlen Profil und
Datenbank (CI, frischer Checkout), entfallen diese Regeln, die allgemeinen laufen weiter, und die
Ausgabe sagt es. Hier bleiben die PAKETWEITEN Regeln (Pflichtdateien, Import ausgeschlossener
Module, Ausführ-Bit der Startdateien).

ZWEI QUELLEN, EIN DATENMODELL: Der Kern arbeitet auf einer Liste von `Eintrag`s
(Pfad/Modus/Inhalt-Bytes) im Speicher, ohne Zwischenordner auf der Platte:
  - Standard: `git archive --format=tar <ref>` (Default HEAD) — der Auslieferungsweg, nur
    committete, versionierte Dateien. Gelesen aus dem Tar-Stream des Subprozesses.
  - `--arbeitsbaum`: `git ls-files -s` (Modus aus dem Index) + Inhalt von der Platte — für
    Vorschau und für die Tests, die schon VOR dem Commit grün werden müssen.
Beide liefern dieselbe Eintrag-Form, Ausschließen/Ersetzen/Prüfen/Zip-Schreiben kennen den
Unterschied danach nicht mehr. Pfade sind IMMER Git-Konvention (Vorwärtsschrägstrich,
plattformunabhängig) — `pathlib` kommt erst ins Spiel, wenn wirklich eine Datei auf der Platte
gelesen oder das ZIP geschrieben wird (Windows-CI-Job `backend-windows` läuft mitgeprüft).

ZIP OHNE PRÄFIX-ORDNER: `BMS_Install_MAC.md` und `BMS_Install_Windows.md` erwarten nach dem
Entpacken direkt `start.command` bzw. `start_windows.bat` im Zielordner — jeder Eintrag landet
deshalb an seinem reinen Pfad, ohne gemeinsamen Wurzelordner im Archiv. Unix-Rechte kommen aus
dem Git-Modus (100644/100755) in `external_attr`, damit macOS/Linux `start.command` & Co.
ausführbar entpacken; unter Windows ist dieses Bit wirkungslos, aber auch harmlos (reine
Metadaten im Zip, kein OS-Zugriff beim Schreiben). Zeitstempel aller Einträge = Commit-Zeit
(reproduzierbar über mehrere Bauten desselben Commits).

WAS DAS SKRIPT NICHT LEISTET: Im Quellcode selbst feste Werte, etwa eine Wohnanschrift als
Routenplanungs-Startpunkt oder der Name des Entwicklers in Oberflächentexten, kann es nicht
nachträglich sauber herausschneiden, es prüft nur, ob sie NOCH da sind.

MANIFEST UND VERSION (P2-51, Paket U2a): Nach `ersetzen()` bekommt das Paket einen weiteren
Eintrag `bms_manifest.json` (Vertrag V3 der Bau-Spec) — Pfad, Ausführ-Bit, Größe und SHA-256
jeder ausgelieferten Datei, plus Version/Freigabe/Vorschau-Status. Das Manifest entsteht VOR der
Personendaten-Prüfung und wird deshalb selbst mitgeprüft (ein Leck im Manifest — etwa über einen
Dateinamen — fiele sonst durchs Raster). `version` liest IMMER aus der Datei `VERSION` des
GEPACKTEN Stands (Eintrag in der bereits eingesammelten Liste, nie von der Platte des
Arbeitsbaums direkt) — bei `--ref` also aus dem Archiv dieser Revision, nicht vom aktuell
ausgecheckten Stand. `freigabe` kommt aus `git tag --points-at` (nie bei `--arbeitsbaum`, dort
könnten Änderungen NACH dem letzten Tag stecken). `VERSION.txt` (Vorgänger-Arbeitspaket P2-50)
entfällt ersatzlos: `datetime.now()` machte es nicht reproduzierbar, das Manifest übernimmt seine
Aufgabe vollständig und lässt sich aus demselben Commit jederzeit identisch neu bauen.

CLI (aus backend/):
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.kundenpaket                       # HEAD -> ZIP
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.kundenpaket --pruefen             # nur pruefen
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.kundenpaket --arbeitsbaum         # Vorschau
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.kundenpaket --ziel-ordner DIR --ref v1.2.3
Bequemer Aufruf vom Projekt-Root: `scripts/kundenpaket.sh` (reicht Argumente 1:1 durch).
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import stat
import subprocess
import tarfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable, NamedTuple

from pipeline import personendaten
# Eintrag und Fund leben in personendaten (dort gebraucht), werden hier wieder angeboten: so bleiben
# `kundenpaket.Eintrag`/`.Fund` und die Konstante des oeffentlichen Repos fuer alle Aufrufer gleich.
from pipeline.personendaten import ABSOLUTER_PFAD_RE as _ABSOLUTER_PFAD_RE
from pipeline.personendaten import OEFFENTLICHES_REPO, Eintrag, Fund, Muster
from pipeline.personendaten import pfad_trifft as _pfad_trifft

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Kunden sehen diesen Namen im Kunden-README (Arbeitspaket A) -- dieselbe Bezeichnung wie in
# BMS_Install_MAC.md/BMS_Install_Windows.md.
PRODUKTNAME = "Bewerbungs-Management-System (BMS)"

# V3-Manifest-Feld "produkt": ohne das Klammerkuerzel, exakt wie die Bau-Spec es vorschreibt --
# bewusst eine eigene Konstante statt PRODUKTNAME.replace(...), damit der Manifest-Wortlaut nicht
# heimlich an einer README-Formulierung haengt, die sich unabhaengig davon aendern darf.
PRODUKT_MANIFEST = "Bewerbungs-Management-System"

_MODUS_SYMLINK = 0o120000


class CommitInfo(NamedTuple):
    voll: str    # vollstaendiger SHA
    kurz: str    # git rev-parse --short
    datum: str   # "JJJJ-MM-TT", aus dem Commit-Zeitstempel
    zeit_tuple: tuple[int, int, int, int, int, int]   # fuer ZipInfo.date_time


class Ergebnis(NamedTuple):
    quelle: str
    anzahl_im_paket: int
    anzahl_ausgeschlossen: int
    ersetzte_pfade: tuple[str, ...]
    uebersprungen: tuple[str, ...]
    funde: tuple[Fund, ...]
    zip_pfad: Path | None
    zip_groesse: int | None
    uncommitted_hinweis: bool
    version: str               # V3 "version" -- aus VERSION im gepackten Stand, s. _version_aus_eintraegen
    freigabe: bool              # V3 "freigabe" -- traegt der Commit das Tag v<version>?
    firmen_db_pfad: Path | None  # None = Firmennamen-Regel uebersprungen (Datenbank fehlte oder war nicht lesbar)
    profil_gelesen: bool = False  # False = Regeln aus dem Profil (Anschrift, Kontakt, Name) uebersprungen


class KundenpaketFehler(Exception):
    """Technischer Fehler (z. B. kein git, ungueltige Revision) -- fuehrt zu Exit-Code 2.
    KEIN Personendaten-Fund -- die sind Fund/Ergebnis.funde und fuehren zu Exit-Code 1."""


# ── Ausschliessen ─────────────────────────────────────────────────────────────────────────
# Muster endet auf "/": Praefix (ganzer Ordner). Sonst: exakter Pfad. Jede Zeile mit kurzer
# Begruendung, wie von der Spec gefordert (Tabelle "1. Ausschliessen"). Ein Eintrag fuer eine Datei,
# die es (noch) nicht gibt, ist kein Fehler.
AUSSCHLUESSE: tuple[tuple[str, str], ...] = (
    ("tasks/", "interne Notizen, Bewerbungsverlauf, Mailadressen Dritter"),
    ("backend/tests/", "pruefen gezielt Daten der Entwicklungsinstallation (Name, Stationszahl), fuer Kunden ohne Nutzen"),
    (".github/", "Entwicklungswerkzeug (CI-Workflows)"),
    (".gitleaks.toml", "Entwicklungswerkzeug (Secret-Scan-Konfiguration)"),
    (".claude/launch.json", "absolute Pfade der Entwicklungsinstallation, nur fuer die Entwicklung"),
    # P2-83: Dateien fuer das oeffentliche Repo; CONTRIBUTING verweist auf Entwicklerdateien, die das
    # Kundenpaket nicht enthaelt (z. B. scripts/test.sh).
    ("CONTRIBUTING.md", "Entwickler-/Repo-Datei (Beitragen im oeffentlichen Repo, P2-83)"),
    ("SECURITY.md", "Entwickler-/Repo-Datei (Sicherheitsmeldungen im oeffentlichen Repo, P2-83)"),
    ("scripts/test.sh", "Entwicklungswerkzeug"),
    ("scripts/docs_html.sh", "Entwicklungswerkzeug"),
    ("scripts/install_hooks.sh", "Entwicklungswerkzeug"),
    ("scripts/precommit_secret_scan.sh", "Entwicklungswerkzeug"),
    ("scripts/kundenpaket.sh", "Entwicklungswerkzeug (baut dieses Paket selbst)"),
    ("backend/pipeline/kundenpaket.py", "das Skript selbst (Entwicklungswerkzeug, P2-83: die Pruefmuster liegen nicht mehr darin)"),
    ("backend/pipeline/personendaten.py", "Pruefregeln fuer Paket und Export, Entwicklungswerkzeug (P2-83)"),
    ("backend/pipeline/release.py", "Werkzeug nur fuer den Freigabe-Workflow der Entwicklung (P2-51 Paket U2b)"),
    ("scripts/release.sh", "Werkzeug nur fuer den Freigabe-Workflow der Entwicklung (P2-51 Paket U2b)"),
    # P2-83: Export-Werkzeug fuer das oeffentliche Repo (Paket E); ohne diese Zeilen lieferte das
    # Kundenpaket ein Modul, das das ausgeschlossene kundenpaket.py importiert.
    ("backend/pipeline/veroeffentlichung.py", "Werkzeug fuer den Export ins oeffentliche Repo (P2-83)"),
    ("scripts/veroeffentlichen.sh", "Werkzeug fuer den Export ins oeffentliche Repo (P2-83)"),
    # P2-77: Der Generator liest venv und Build-Spiegel, beides gibt es beim Kunden nicht so.
    # Ausgeliefert werden nur seine ERGEBNISSE (frontend/src/rechtliches/drittlizenzen*, s. PFLICHTDATEIEN).
    ("backend/pipeline/drittlizenzen.py",
     "Entwicklungswerkzeug: erzeugt die Drittanbieter-Lizenzen aus venv und Build-Spiegel (P2-77)"),
    ("scripts/drittlizenzen.sh", "Entwicklungswerkzeug (P2-77)"),
)

# docs/ ist eine POSITIVLISTE statt eines Praefix-Ausschlusses: die meisten docs/*.md sind
# interne Entwicklerdoku (DOKUMENTATION, WAS_IST_NEU, INSTALLATION, AUTOMATION, COACH_SITE,
# GMAIL-STRATEGIE), nur diese sieben sind fuer Kunden gedacht (je .md + generierte .html).
# P2-59: FUNKTIONEN ist die Kurzuebersicht, die die Dokumentationsseite im Reiter "Funktionen" zeigt.
# P2-82: Keine eigene Lizenz-Doku mehr; die Open-Source-Lizenz liegt in LICENSE und NOTICE (s. PFLICHTDATEIEN).
DOKU_ERLAUBT: frozenset[str] = frozenset({
    "ANLEITUNG", "ANLEITUNG_COACH_SITE", "BEIRAT-CHARTA", "BEIRAT-PERSONA-TEMPLATE",
    "FUNKTIONEN", "SETUP-EMAIL", "SETUP-WINDOWS",
})

# Fehlt eine davon im fertigen Paket, ist es kaputt (schuetzt gegen zu eifriges Ausschliessen).
# `config/profil_struktur.md` steht bewusst NICHT darin (P2-83): Die Datei ist persoenlich und nicht
# mehr im Git; die App erzeugt sie beim Start, wenn sie fehlt. Kommt sie im Stand doch vor, ersetzt
# `ersetzen` sie als Rueckfall durch die neutrale Fassung.
PFLICHTDATEIEN: tuple[str, ...] = (
    "BMS_Install_MAC.md", "BMS_Install_Windows.md",
    "start.command", "start_windows.bat", "stop.command", "stop_windows.bat",
    "backend/run_server.py", "backend/requirements-lock.txt",
    "frontend/package.json", "frontend/package-lock.json",
    "docs/ANLEITUNG.md", "docs/SETUP-EMAIL.md", "docs/BEIRAT-CHARTA.md",
    "docs/FUNKTIONEN.md",
    "automation/agent.env.example", "automation/agent_settings.json", "automation/pfad_waechter.py",
    "scripts/refresh_views.sh", "scripts/cover_letter_render.sh", "scripts/coach_site.sh",
    "config/scoring_rubrik.md", "config/coach_export.yaml",
    # P2-51 Paket U2a Punkt 3: Update- und Versionsmechanismus. Die vier U1-Dateien entstehen in
    # einem PARALLELEN Paket -- bis dahin ist ihr Fehlen ein erwarteter Fund (s. Bau-Spec).
    "VERSION", "CHANGELOG.md", "update.command", "update_windows.bat",
    "scripts/bms_update.py", "backend/app/selbsttest.py", "backend/pipeline/changelog.py",
    # P2-66: Sicherung zurueckspielen (Werkzeug plus die beiden Doppelklick-Starter).
    "wiederherstellen.command", "wiederherstellen_windows.bat", "scripts/bms_wiederherstellen.py",
    # P2-77: Drittanbieter-Lizenzen (Uebersicht + Wortlaut), vom Generator erzeugt. Fehlt eine,
    # ist die Seite Rechtliches -> Drittanbieter-Lizenzen im Paket kaputt (die Oberflaeche bindet beide ein).
    "frontend/src/rechtliches/drittlizenzen.md", "frontend/src/rechtliches/drittlizenzen_texte.txt",
    # 29.10.2026: eigene Open-Source-Lizenz (Apache-2.0). Ohne LICENSE und NOTICE darf das Programm
    # nicht weitergegeben werden; lizenz.txt zeigt den Wortlaut im Reiter „Open-Source-Lizenz“.
    "LICENSE", "NOTICE", "frontend/src/rechtliches/lizenz.txt",
)

# V3-Manifest-Feld "anpassbar": fnmatch-Muster fuer ausgelieferte Dateien, die NACH der
# Installation beim Kunden weiterleben und sich unterscheiden DUERFEN, ohne dass ein Update sie
# stumpf ueberschreibt (Update-Werkzeug Paket U1 liest genau diese Liste aus dem NEUEN Manifest).
# Zwei Quellen, U2a Punkt 5 geprueft:
#   - die App SCHREIBT die Datei selbst um (kein Kunden-Handeditieren noetig, aber der Inhalt
#     WEICHT vom Auslieferungsstand ab): `.claude/agents/beirat-*.md` (beirat_engine.py::
#     _frontmatter_feld_setzen/_anzeige_umbenennen -- Persona-Umbenennung/-Ersatz ueber die
#     Oberflaeche) und `config/profil_struktur.md` (main.py::_PROFIL_STRUKTUR_PATH, bei jedem
#     Profil-Save neu erzeugt). Seit P2-83 liefert das Paket die Datei nicht mehr aus (sie ist
#     persoenlich und nicht im Git, die App legt sie beim Start an); der Eintrag bleibt trotzdem,
#     damit ein Update die beim Kunden entstandene Datei behaelt statt sie als entfallen zu loeschen.
#   - die Kunden-Doku fordert Handbearbeitung: `config/scoring_rubrik.md`, Abschnitt
#     "Dimension 2" (frueher BMS_Install.md 3.4 -- Zielrollen A/B/C an die eigene Situation
#     anpassen; heute nennen BMS_Install_MAC.md/BMS_Install_Windows.md die Datei im Abschnitt
#     "Aktualisierungen einspielen" als anpassbar und beim Update erhalten).
#     Die dortigen VIER Dateien zur Umkreis-Anpassung (u. a. drei SKILL.md) fallen bewusst NICHT
#     zusaetzlich hierunter: Genau dieses Handbearbeiten macht P2-51 ueberfluessig (Umkreis kommt
#     jetzt aus den Einstellungen, Pakete N2/D nehmen die Anweisung wieder aus der Doku).
# Weitere Kandidaten (Schreibzugriffe der App ausserhalb data/outputs/, s. grep-Belege im
# Abnahmebericht) ergaben nichts zusaetzliches -- `config/coach_export.yaml` wird nur gelesen,
# nirgends zur Handbearbeitung angewiesen.
ANPASSBAR: tuple[str, ...] = (
    ".claude/agents/beirat-*.md", "config/profil_struktur.md", "config/scoring_rubrik.md",
)

# Diese .command-Dateien oeffnen Kunden per Doppelklick; ohne Unix-Ausfuehr-Bit startet macOS
# stattdessen einen Text-Editor. .bat-Dateien brauchen das Bit nicht (Windows kennt es nicht,
# dort entscheidet allein die Endung) -- s. _startdateien_funde (Spec Punkt 3, "bestehende
# Pruefung der Startdateien erweitert": bisher lief das Ausfuehr-Bit nur unbesehen durch die
# Kette git-Index -> Eintrag -> ZIP, hier wird es zum ersten Mal wirklich GEPRUEFT).
_STARTDATEIEN_AUSFUEHRBAR: tuple[str, ...] = ("start.command", "stop.command", "update.command",
                                                "wiederherstellen.command")  # P2-66


def _docs_erlaubt(pfad: str) -> bool:
    p = PurePosixPath(pfad)
    return p.suffix in (".md", ".html") and p.stem in DOKU_ERLAUBT


# ── Git-Quellen ────────────────────────────────────────────────────────────────────────────

def _git(args: list[str], projekt_root: Path) -> subprocess.CompletedProcess:
    """Ruft git im Projekt auf (immer Bytes-stdout -- Text-Dekodierung macht die aufrufende
    Stelle bewusst selbst, je nach Kommando). `.git` ist bei uns eine Zeiger-Datei auf
    `.git.nosync/` (iCloud-Workaround) -- fuer git selbst transparent, kein Sonderfall hier."""
    try:
        return subprocess.run(["git", *args], cwd=projekt_root, capture_output=True, check=True)
    except FileNotFoundError as exc:
        raise KundenpaketFehler("git ist auf diesem Rechner nicht verfuegbar.") from exc
    except subprocess.CalledProcessError as exc:
        meldung = exc.stderr.decode("utf-8", "replace").strip()
        raise KundenpaketFehler(f"git {' '.join(args)} fehlgeschlagen: {meldung}") from exc


def commit_info(ref: str, projekt_root: Path = PROJECT_ROOT) -> CommitInfo:
    """Liest SHA (voll/kurz) und Commit-Zeit fuer `ref`. Die Zeit kommt aus `%cI` (ISO 8601
    MIT dem Offset des Committers) -- fuer Zeitstempel/Dateiname genuegt die Wandzeit daraus
    (kein UTC-Umrechnen: reproduzierbar fuer jeden, der denselben Commit baut, unabhaengig von
    dessen lokaler Zeitzone). `^{commit}` schaelt ein annotiertes Tag (so legt `release.py` die
    Freigaben an) auf seinen Commit -- ohne das gibt `git show` zuerst Tagger und Tag-Nachricht aus,
    und `--ref v1.2.3` scheiterte (P2-51, gefunden im Ende-zu-Ende-Test)."""
    proc = _git(["show", "-s", "--format=%H|%h|%cI", f"{ref}^{{commit}}"], projekt_root)
    voll, kurz, iso = proc.stdout.decode("utf-8").strip().splitlines()[0].split("|")
    dt = datetime.fromisoformat(iso)
    return CommitInfo(voll, kurz, dt.strftime("%Y-%m-%d"),
                       (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second))


def sammle_aus_git_archive(ref: str, projekt_root: Path = PROJECT_ROOT) -> list[Eintrag]:
    """Auslieferungsweg: `git archive --format=tar <ref>` -- NUR committete, versionierte
    Dateien. Der komplette Tar-Stream wird gepuffert (Projektgroesse macht das unproblematisch)
    und aus dem Speicher gelesen (`io.BytesIO`) statt als Pipe gestreamt -- vermeidet
    Streaming-Sonderfaelle von `tarfile` und ist auf jedem Betriebssystem gleich einfach.
    Verzeichnis-Eintraege (git archive legt sie an) werden uebersprungen, `Eintrag` kennt nur
    Dateien.

    MODUS-FALLE (per Scratch-Repo-Test empirisch gefunden, nicht aus der Doku geraten): git
    archiviert Tar-Eintraege NICHT mit den reinen Index-Rechten 644/755, sondern wendet dabei
    zusaetzlich `tar.umask` an (git-Default 0002, unabhaengig vom Prozess-Umask) -- eine
    normale Datei kommt im Tar deshalb typischerweise mit 664 statt 644 an (0666 & ~0002),
    eine ausfuehrbare mit 775 statt 755. Das wuerde OHNE Normalisierung 1:1 ins ZIP
    durchschlagen (falsche external_attr-Rechte). Deshalb hier NICHT `ti.mode` roh uebernehmen,
    sondern auf die kanonische Git-Bedeutung zurueckfuehren: nur die Ausfuehrbarkeit zaehlt."""
    proc = _git(["archive", "--format=tar", ref], projekt_root)
    eintraege = []
    with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:") as tar:
        for ti in tar:
            if not ti.isfile():
                continue
            inhalt = tar.extractfile(ti).read()
            modus = 0o755 if (ti.mode & 0o111) else 0o644
            eintraege.append(Eintrag(ti.name, modus, inhalt))
    return eintraege


def sammle_aus_arbeitsbaum(projekt_root: Path = PROJECT_ROOT) -> tuple[list[Eintrag], list[str]]:
    """Vorschau-/Test-Weg: `git ls-files -s` (Modus aus dem INDEX: 100644/100755/120000) +
    Inhalt von der PLATTE. Symlinks (Modus 120000) und Dateien, die im Index stehen, aber auf
    der Platte fehlen, werden uebersprungen und als zweite Rueckgabe gemeldet (Spec: "im
    Bericht nennen", kein stilles Verschlucken). `projekt_root / pfad` funktioniert mit dem
    Vorwaertsschraegstrich-Pfad aus git auch unter Windows (pathlib akzeptiert "/" auf beiden
    Plattformen als Trenner).

    Dazu kommen NEUE, noch nicht hinzugefuegte Dateien, soweit `.gitignore` sie nicht
    ausschliesst (`git ls-files --others --exclude-standard`): Die Vorschau soll zeigen, was der
    naechste Commit ausliefern wuerde. Ohne sie fiel bei der Abnahme 27.09.2026 ein neuer
    Kommentar mit einer Wohnanschrift (`frontend/src/profil.ts`) durch die Pruefung, weil die Datei
    noch nicht im Index stand. Ihr Modus kommt von der Platte (ausfuehrbar ja/nein).

    Beide Aufrufe mit `-z` (NUL-getrennt): Ohne `-z` maskiert git Pfade mit Umlauten oktal
    (`core.quotepath`), die Datei waere dann unter dem maskierten Namen nicht zu finden."""
    eintraege: list[Eintrag] = []
    uebersprungen: list[str] = []

    index = _git(["ls-files", "-s", "-z"], projekt_root).stdout.decode("utf-8")
    for satz in index.split("\0"):
        if not satz:
            continue
        kopf, pfad = satz.split("\t", 1)
        modus = int(kopf.split()[0], 8)
        if modus == _MODUS_SYMLINK:
            uebersprungen.append(pfad)
            continue
        datei = projekt_root / pfad
        if not datei.is_file():
            uebersprungen.append(pfad)
            continue
        eintraege.append(Eintrag(pfad, modus & 0o777, datei.read_bytes()))

    neu = _git(["ls-files", "--others", "--exclude-standard", "-z"], projekt_root).stdout.decode("utf-8")
    for pfad in neu.split("\0"):
        if not pfad:
            continue
        datei = projekt_root / pfad
        if datei.is_symlink() or not datei.is_file():
            uebersprungen.append(pfad)
            continue
        modus = 0o755 if datei.stat().st_mode & 0o111 else 0o644
        eintraege.append(Eintrag(pfad, modus, datei.read_bytes()))

    eintraege.sort(key=lambda e: e.pfad)
    return eintraege, uebersprungen


# ── Ausschliessen ──────────────────────────────────────────────────────────────────────────

def ausschliessen(eintraege: list[Eintrag]) -> tuple[list[Eintrag], list[str]]:
    """Wendet AUSSCHLUESSE + die docs/-Positivliste an. Gibt (behaltene Eintraege,
    ausgeschlossene Pfade) zurueck."""
    behalten: list[Eintrag] = []
    ausgeschlossen: list[str] = []
    muster = tuple(m for m, _grund in AUSSCHLUESSE)
    for e in eintraege:
        if e.pfad.startswith("docs/"):
            if _docs_erlaubt(e.pfad):
                behalten.append(e)
            else:
                ausgeschlossen.append(e.pfad)
            continue
        if _pfad_trifft(e.pfad, muster):
            ausgeschlossen.append(e.pfad)
        else:
            behalten.append(e)
    return behalten, ausgeschlossen


# ── Ersetzen und ergaenzen ───────────────────────────────────────────────────────────────

def _tt_mm_jjjj(iso_datum: str) -> str:
    """"2026-09-27" -> "27.09.2026" -- `commit.datum` kommt immer aus `commit_info()` als
    `dt.strftime("%Y-%m-%d")`, ein simpler Split genuegt deshalb (kein erneutes Datums-Parsen)."""
    jahr, monat, tag = iso_datum.split("-")
    return f"{tag}.{monat}.{jahr}"


def _readme_kundenpaket(version: str, commit_datum: str) -> bytes:
    """Kurzer Kunden-Wegweiser statt des Entwickler-READMEs -- bewusst ohne jedes Wort
    ueber Entwicklung, Git oder den Entwickler (Spec, Abschnitt "2. Ersetzen und ergaenzen"). Die
    Versionszeile ersetzt seit P2-51 das fruehere `VERSION.txt` (Punkt 1) -- dieselbe Angabe
    steht jetzt zusaetzlich, maschinenlesbar, im Manifest (V3, Feld "version")."""
    text = (
        f"# {PRODUKTNAME}\n\n"
        f"Version {version} (Stand {_tt_mm_jjjj(commit_datum)}).\n\n"
        "## Installation und Einrichtung\n\n"
        "Schritt für Schritt in `BMS_Install_MAC.md` (macOS) bzw. `BMS_Install_Windows.md` "
        "(Windows) in diesem Ordner. Claude führt Sie mit der Datei durch die Installation.\n\n"
        "## Bedienung\n\n"
        "Wie Sie mit der laufenden Anwendung arbeiten, erklärt `docs/ANLEITUNG.md`.\n\n"
        "## Änderungen\n\n"
        "Was sich von Version zu Version für Sie ändert, steht in `CHANGELOG.md`.\n\n"
        "## Aktualisieren\n\n"
        "Eine neue Version spielen Sie mit `update.command` (Mac) oder `update_windows.bat` "
        "(Windows) ein. Ob es eine gibt, zeigt in den Einstellungen der Knopf „Nach Updates "
        "suchen“.\n\n"
        "## Lizenz\n\n"
        "Das BMS ist Open Source unter der Apache License 2.0 (`LICENSE`, `NOTICE`).\n\n"
        "## Hilfe\n\n"
        # P2-82, Leitentscheidung 10: Hilfe ueber die Issues-Seite des oeffentlichen Repos.
        f"Fragen und Fehler: https://github.com/{OEFFENTLICHES_REPO}/issues\n"
    )
    return text.encode("utf-8")


def _profil_struktur_neutral() -> bytes:
    """Neutrale Grundfassung ohne Werdegang -- die Kopfzeilen sind WORTGLEICH mit dem Generator
    `backend/app/main.py::_profil_struktur_schreiben` (dort steht dieselbe Erklaerung), nur die
    "Stand:"-Zeile (Zeitstempel des letzten echten Saves) fehlt hier, dafuer der Hinweis, dass
    die Datei beim ersten Speichern auf der Profil-Seite entsteht. Seit P2-83 nur noch Rueckfall
    (s. `ersetzen`): Die Datei ist nicht mehr im Git; kommt sie im Stand doch vor, darf sie keine
    Kandidaten-Substanz ins Paket tragen."""
    text = (
        "# Profil-Struktur\n\n"
        "Automatisch aus der Profil-Seite erzeugt — NICHT von Hand editieren (wird beim "
        "nächsten Save überschrieben). Ergänzt `config/profil.md` (Such-Strategie) um die "
        "Kandidaten-Substanz für Matching/Anschreiben.\n\n"
        "Diese Datei entsteht neu, sobald auf der Profil-Seite zum ersten Mal gespeichert "
        "wird — bis dahin enthält sie keinen Werdegang.\n"
    )
    return text.encode("utf-8")


def _agent_settings_neutralisiert(inhalt: bytes) -> bytes:
    """Entfernt aus `permissions.allow` jeden Eintrag mit einem absoluten BENUTZER-Pfad
    (/Users/, /home/, C:\\Users, C:/Users) -- alles andere bleibt Byte-fuer-Byte-aequivalent
    (gleiche `json.dumps`-Konvention wie das Original: indent=2, ensure_ascii=False). Die
    "~"- und "$HOME"-Formen bleiben immer stehen, die gelten auf jedem Rechner (Spec)."""
    daten = json.loads(inhalt.decode("utf-8"))
    berechtigungen = daten.get("permissions")
    if isinstance(berechtigungen, dict) and isinstance(berechtigungen.get("allow"), list):
        berechtigungen["allow"] = [
            e for e in berechtigungen["allow"]
            if not (isinstance(e, str) and _ABSOLUTER_PFAD_RE.search(e))
        ]
    text = json.dumps(daten, indent=2, ensure_ascii=False) + "\n"
    return text.encode("utf-8")


def _version_aus_eintraegen(eintraege: list[Eintrag]) -> str:
    """Liest `version` aus dem Inhalt von `VERSION` im GEPACKTEN Stand (V3) -- bewusst aus der
    Eintrag-Liste, nicht von der Platte des Arbeitsbaums: bei `--ref <alter-tag>` muss die
    VERSION dieses alten Standes herauskommen, nicht die des aktuell ausgecheckten. Fehlt die
    Datei (Commit vor P2-51, oder ein sonst kaputtes Paket), gilt "0.0.0" -- dieselbe Bedeutung
    wie V1 fuer "noch keine Freigabe"; die Pflichtdateien-Regel meldet das Fehlen ohnehin
    separat als eigenen Fund, hier soll nur nichts abstuerzen."""
    for e in eintraege:
        if e.pfad == "VERSION":
            return e.inhalt.decode("utf-8").strip()
    return "0.0.0"


def ersetzen(eintraege: list[Eintrag], commit: CommitInfo, ist_arbeitsbaum: bool) -> list[Eintrag]:
    """Tauscht README.md / config/profil_struktur.md / automation/agent_settings.json gegen
    ihre neutrale Kundenfassung. Reine Datentransformation auf der In-Memory-Liste -- ruehrt
    nichts auf der Platte an. Seit P2-83 sind die letzten beiden nur noch ein Rueckfall:
    `profil_struktur.md` ist nicht mehr im Git (die App legt sie beim Start an), und
    `agent_settings.json` ist in der getrackten Fassung schon neutral. Eine Datei, die in
    `eintraege` fehlt (nicht im Stand oder zuvor ausgeschlossen), wird nicht ersetzt und auch nicht
    ergaenzt -- fehlt eine Pflichtdatei, meldet das die Pflichtdateien-Regel, kein Absturz hier.
    `VERSION.txt` (P2-50) entfaellt seit P2-51 ersatzlos, s. Moduldoc "MANIFEST UND VERSION"."""
    version = _version_aus_eintraegen(eintraege)
    ersetzungen: dict[str, Callable[[Eintrag], bytes]] = {
        "README.md": lambda e: _readme_kundenpaket(version, commit.datum),
        "config/profil_struktur.md": lambda e: _profil_struktur_neutral(),
        "automation/agent_settings.json": lambda e: _agent_settings_neutralisiert(e.inhalt),
    }
    ergebnis = []
    for e in eintraege:
        macher = ersetzungen.get(e.pfad)
        ergebnis.append(Eintrag(e.pfad, e.modus, macher(e)) if macher else e)
    return ergebnis


# ── Pruefen (fail-closed) ────────────────────────────────────────────────────────────────

def pruefen_eintraege(eintraege: list[Eintrag], muster: Muster | None = None) -> list[Fund]:
    """Alle DATEIBEZOGENEN Pruefregeln im Umfang `"paket"` (`personendaten.pruefen`). Ohne `muster`
    laufen nur die allgemeinen Regeln (E-Mail, Telefon, Bestands-IDs, Zeilenenden): so pruefen
    Tests eine einzelne Regel isoliert, ohne dass Profil oder Datenbank des Rechners mitspielen.
    OHNE die zwei paketweiten Regeln (Pflichtdateien, Import ausgeschlossener Module) -- die
    ergeben nur ueber die VOLLSTAENDIGE Liste einen Sinn und haben deshalb ihre eigene Funktion
    `pruefen_paket`. `alle_funde` ruft beide zusammen auf."""
    return personendaten.pruefen(eintraege, muster if muster is not None else Muster(),
                                  umfang=personendaten.UMFANG_PAKET)


def _resolvierbarer_pfad(kandidat: str) -> str | None:
    """Bildet einen Python-Modulnamen (wie er in `import`/`from ... import` steht) auf den
    ERWARTETEN Datei-Pfad ab -- NUR fuer die drei Wurzeln, die die Spec fuer diese Regel nennt
    (backend/, backend/app/, backend/pipeline/). Reine Namenskonvention, kein
    Dateisystemzugriff -- ob der Pfad WIRKLICH (noch) existiert, prueft die aufrufende Stelle
    gegen die tatsaechlich eingesammelten Pfade (s. _import_funde)."""
    teile = kandidat.split(".")
    if teile[0] == "app":
        rest = teile[1:] or ["__init__"]
        return "backend/app/" + "/".join(rest) + ".py"
    if teile[0] == "pipeline":
        rest = teile[1:] or ["__init__"]
        return "backend/pipeline/" + "/".join(rest) + ".py"
    if len(teile) == 1:
        return f"backend/{teile[0]}.py"
    return None


def _import_funde(eintraege: list[Eintrag], roh_pfade: set[str]) -> list[Fund]:
    """Regel "Import ausgeschlossener Module": ein ausgeliefertes .py importiert ein Modul,
    dessen Datei beim Ausschliessen weggefallen ist -- Sicherheitsnetz gegen ein kaputtes
    Paket. Ein Kandidat zaehlt nur, wenn sein per Namenskonvention erwarteter Pfad
    tatsaechlich im QUELLBESTAND (roh_pfade, VOR dem Ausschliessen) vorhanden war -- alles
    andere (Stdlib, Drittanbieter-Pakete, ein Attribut statt eines Submoduls) kann per
    Namenskonvention nicht von einer echten Datei unterschieden werden und wird deshalb
    ignoriert statt falschen Alarm zu schlagen."""
    kept = {e.pfad for e in eintraege}
    funde = []
    for e in eintraege:
        if not e.pfad.endswith(".py"):
            continue
        try:
            baum = ast.parse(e.inhalt.decode("utf-8"), filename=e.pfad)
        except (UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(baum):
            kandidaten: list[str] = []
            if isinstance(node, ast.Import):
                kandidaten = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue  # relativer Import -- ausserhalb der drei Wurzeln (Spec)
                if node.module:
                    kandidaten = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            gesehen: set[str] = set()
            for kandidat in kandidaten:
                ziel = _resolvierbarer_pfad(kandidat)
                if ziel is None or ziel in gesehen:
                    continue
                gesehen.add(ziel)
                if ziel in roh_pfade and ziel not in kept:
                    funde.append(Fund(e.pfad, node.lineno, "Import ausgeschlossener Module",
                                       f"import {kandidat}  ->  {ziel} (ausgeschlossen)"))
    return funde


def _startdateien_funde(eintraege: list[Eintrag]) -> list[Fund]:
    """Punkt 3: `update.command` muss im Paket ausfuehrbar sein -- erweitert die bisher nur
    beilaeufige Rechte-Weitergabe (git-Modus -> Eintrag -> ZIP) um eine echte Pruefung, auch
    fuer die beiden laengst bestehenden .command-Starter. Eine FEHLENDE Datei meldet bereits
    die Pflichtdateien-Regel -- hier zaehlt nur, wer da ist, aber ohne Ausfuehr-Bit."""
    nach_pfad = {e.pfad: e for e in eintraege}
    funde = []
    for pfad in _STARTDATEIEN_AUSFUEHRBAR:
        e = nach_pfad.get(pfad)
        if e is not None and not (e.modus & 0o111):
            funde.append(Fund(pfad, 0, "Startdatei nicht ausfuehrbar",
                               f"Modus {oct(e.modus)} -- macOS oeffnet die Datei sonst im Editor"))
    return funde


def pruefen_paket(eintraege: list[Eintrag], roh_pfade: set[str]) -> list[Fund]:
    """Die PAKETWEITEN Regeln: Pflichtdateien (fehlt eine, ist das Paket kaputt), Import
    ausgeschlossener Module (s. _import_funde) und Startdateien-Ausfuehrbarkeit."""
    kept_pfade = {e.pfad for e in eintraege}
    funde = [Fund(p, 0, "Pflichtdatei fehlt", "") for p in PFLICHTDATEIEN if p not in kept_pfade]
    if not any(p.startswith(".claude/skills/") and p.endswith("SKILL.md") for p in kept_pfade):
        funde.append(Fund(".claude/skills/*/SKILL.md", 0, "Pflichtdatei fehlt", "keine SKILL.md im Paket"))
    funde += _import_funde(eintraege, roh_pfade)
    funde += _startdateien_funde(eintraege)
    return funde


# ── Alle Regeln zusammen ─────────────────────────────────────────────────────────────────

def alle_funde(eintraege: list[Eintrag], roh_pfade: set[str], muster: Muster | None = None) -> list[Fund]:
    """Dateibezogene Regeln (`pruefen_eintraege`) plus paketweite (`pruefen_paket`). `muster` bewusst
    optional und per Default leer: Aufrufer ohne Profil und Datenbank (CI, Wegwerf-Repos) laufen so
    mit den allgemeinen Regeln -- `bauen()` und die CLI laden das Muster aus den lokalen Quellen."""
    return pruefen_eintraege(eintraege, muster) + pruefen_paket(eintraege, roh_pfade)


# ── Manifest (V3) ────────────────────────────────────────────────────────────────────────

def _sha256(inhalt: bytes) -> str:
    return hashlib.sha256(inhalt).hexdigest()


def _ist_freigegeben(commit: CommitInfo, version: str, projekt_root: Path) -> bool:
    """V3 "freigabe": traegt der gepackte Commit das Tag `v<version>`? `git tag --points-at`
    kann mehrere Tags auf demselben Commit liefern (z. B. zusaetzlich ein weiteres Tag) --
    deshalb Mitgliedschaft in der ganzen Zeilenmenge pruefen, nicht nur die erste Zeile.
    `--arbeitsbaum` ruft diese Funktion bewusst gar nicht erst auf (immer False, s. bauen())."""
    tags = _git(["tag", "--points-at", commit.voll], projekt_root).stdout.decode("utf-8").splitlines()
    return f"v{version}" in tags


def manifest_erzeugen(eintraege: list[Eintrag], commit: CommitInfo, version: str,
                       freigabe: bool, vorschau: bool) -> dict:
    """Baut den Manifest-Inhalt nach V3 aus der FERTIGEN Paket-Liste (nach ausschliessen +
    ersetzen, aber OHNE den Manifest-Eintrag selbst -- "die Manifestdatei steht nicht in
    dateien"). `eintraege` hier ist deshalb bewusst NICHT dieselbe Liste, die am Ende ins ZIP
    geht (die enthaelt den Manifest-Eintrag zusaetzlich, s. bauen())."""
    dateien = {
        e.pfad: {"ausfuehrbar": bool(e.modus & 0o111), "groesse": len(e.inhalt), "sha256": _sha256(e.inhalt)}
        for e in eintraege
    }
    return {
        "anpassbar": list(ANPASSBAR),
        "commit": commit.voll,
        "commit_datum": commit.datum,
        "dateien": dateien,
        "format": 1,
        "freigabe": freigabe,
        "produkt": PRODUKT_MANIFEST,
        "version": version,
        "vorschau": vorschau,
    }


def _manifest_eintrag(eintraege: list[Eintrag], commit: CommitInfo, version: str,
                       freigabe: bool, vorschau: bool) -> Eintrag:
    manifest = manifest_erzeugen(eintraege, commit, version, freigabe, vorschau)
    # Serialisierung exakt wie V3 vorschreibt -- sort_keys=True macht den Bau reproduzierbar
    # (dieselbe Eintrag-Liste ergibt IMMER dieselben Bytes, unabhaengig von der Python-
    # Dict-Iterationsreihenfolge) und ist zugleich die "sortiert"-Eigenschaft, die Punkt 8 der
    # Tests verlangt.
    inhalt = (json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8")
    return Eintrag("bms_manifest.json", 0o644, inhalt)


# ── ZIP schreiben ────────────────────────────────────────────────────────────────────────

def ziel_dateiname(commit: CommitInfo, version: str, freigabe: bool, ist_arbeitsbaum: bool) -> str:
    """Punkt 2: freigegeben -> nur die Version (das Kunden-ZIP fuer genau dieses Release);
    sonst Version + Datum + Kurz-SHA (mehrere Entwicklungsstaende derselben Version bleiben
    unterscheidbar); Vorschau aus dem Arbeitsbaum traegt gar keine Version (die koennte sich
    seit dem letzten VERSION-Commit schon wieder geaendert haben)."""
    if ist_arbeitsbaum:
        return f"BMS_VORSCHAU_{commit.datum}.zip"
    if freigabe:
        return f"BMS_{version}.zip"
    return f"BMS_{version}_{commit.datum}_{commit.kurz}.zip"


def zip_schreiben(eintraege: list[Eintrag], ziel_pfad: Path,
                   zeit_tuple: tuple[int, int, int, int, int, int]) -> None:
    """Schreibt das ZIP OHNE Praefix-Ordner (BMS_Install_MAC.md/BMS_Install_Windows.md erwarten
    start.command bzw. start_windows.bat direkt im Zielordner), Eintraege sortiert, alle mit
    demselben Zeitstempel = Commit-Zeit (reproduzierbar ueber mehrere Bauten desselben Commits).
    Unix-Rechte aus dem Git-Modus in `external_attr`, damit macOS/Linux Skripte ausfuehrbar
    entpacken -- unter Windows sind diese Bits wirkungslos, aber harmlos (reine Zip-Metadaten,
    kein Dateisystemzugriff beim Schreiben selbst)."""
    ziel_pfad.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ziel_pfad, "w", zipfile.ZIP_DEFLATED) as zf:
        for e in sorted(eintraege, key=lambda x: x.pfad):
            info = zipfile.ZipInfo(e.pfad, date_time=zeit_tuple)
            # Entpacker werten die Unix-Rechte nur aus, wenn der Eintrag als "Unix" markiert ist.
            # zipfile setzt das nur beim Bauen AUF einem Unix-System — explizit, damit ein unter
            # Windows gebautes Paket `start.command` beim Mac-Kunden trotzdem ausfuehrbar liefert.
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | e.modus) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, e.inhalt)


# ── Orchestrierung ───────────────────────────────────────────────────────────────────────

def bauen(*, arbeitsbaum: bool, ref: str | None, ziel: str | None, nur_pruefen: bool,
          projekt_root: Path = PROJECT_ROOT, firmen_db: Path | None = None,
          muster: Muster | None = None) -> Ergebnis:
    """Baut das Paket Ende-zu-Ende: Quelle einsammeln -> ausschliessen -> ersetzen -> Manifest
    (V3) -> pruefen -> (bei Erfolg + nicht nur_pruefen) ZIP schreiben. `projekt_root` ist
    bewusst ein Parameter (Default PROJECT_ROOT, keine CLI-Option) -- die Test-Suite baut damit
    gegen winzige Wegwerf-Repos in tmp_path, ohne die oeffentliche CLI-Flaeche zu erweitern.
    Die persoenlichen Pruefmuster (P2-83) kommen aus `muster`; ohne Angabe laedt `bauen` sie mit
    `personendaten.muster_laden(projekt_root, db_pfad=firmen_db)`: Profil in `projekt_root/config`,
    Datenbank (nur lesend) unter `firmen_db`, sonst unter `BMS_DATA_DIR` bzw. `projekt_root/data`,
    dazu die optionale Musterdatei. Fehlt eine Quelle, entfallen die betroffenen Regeln still (CI),
    die Ausgabe sagt es."""
    if arbeitsbaum and ref:
        raise KundenpaketFehler("--ref ist nur ohne --arbeitsbaum sinnvoll.")

    uncommitted_hinweis = False
    uebersprungen: tuple[str, ...] = ()

    if arbeitsbaum:
        roh, uebersprungen_liste = sammle_aus_arbeitsbaum(projekt_root)
        uebersprungen = tuple(uebersprungen_liste)
        info = commit_info("HEAD", projekt_root)
        quelle = "Arbeitsbaum (Vorschau)"
    else:
        aktueller_ref = ref or "HEAD"
        info = commit_info(aktueller_ref, projekt_root)
        roh = sammle_aus_git_archive(aktueller_ref, projekt_root)
        # Hinweis statt Fehler: das Paket ist trotzdem gueltig, es enthaelt eben den Stand von
        # HEAD, nicht die lokalen Änderungen (Spec, Abschnitt "Aufbau").
        status = _git(["status", "--porcelain", "--untracked-files=no"], projekt_root)
        uncommitted_hinweis = bool(status.stdout.strip())
        quelle = f"{aktueller_ref} ({info.kurz})"

    roh_pfade = {e.pfad for e in roh}
    behalten, ausgeschlossen_pfade = ausschliessen(roh)
    ersetzt_liste = ersetzen(behalten, info, arbeitsbaum)

    kandidaten_ersetzt = ("README.md", "config/profil_struktur.md", "automation/agent_settings.json")
    ersetzt_pfade_menge = {e.pfad for e in ersetzt_liste}
    ersetzte_pfade = tuple(p for p in kandidaten_ersetzt if p in ersetzt_pfade_menge)

    # Manifest NACH ersetzen(), VOR der Pruefung -- es wird selbst mitgeprueft (V3/Punkt 1).
    version = _version_aus_eintraegen(ersetzt_liste)
    vorschau = arbeitsbaum
    freigabe = False if arbeitsbaum else _ist_freigegeben(info, version, projekt_root)
    manifest_eintrag = _manifest_eintrag(ersetzt_liste, info, version, freigabe, vorschau)
    paket_liste = ersetzt_liste + [manifest_eintrag]

    if muster is None:
        muster = personendaten.muster_laden(projekt_root, db_pfad=firmen_db)
    funde = tuple(alle_funde(paket_liste, roh_pfade, muster))

    zip_pfad: Path | None = None
    zip_groesse: int | None = None
    if not nur_pruefen and not funde:
        zielordner = Path(ziel) if ziel else (projekt_root / "outputs" / "kundenpaket")
        zip_pfad = zielordner / ziel_dateiname(info, version, freigabe, arbeitsbaum)
        zip_schreiben(paket_liste, zip_pfad, info.zeit_tuple)
        zip_groesse = zip_pfad.stat().st_size

    return Ergebnis(quelle, len(paket_liste), len(ausgeschlossen_pfade), ersetzte_pfade,
                     uebersprungen, funde, zip_pfad, zip_groesse, uncommitted_hinweis,
                     version, freigabe, muster.db_pfad if muster.datenbank_gelesen else None,
                     muster.profil_gelesen)


def _ausgabe_drucken(e: Ergebnis) -> None:
    print(f"Quelle: {e.quelle}")
    # Punkt 2: "Ausgabe nennt Version und ob es eine Freigabe ist."
    print(f"Version: {e.version} ({'Freigabe' if e.freigabe else 'keine Freigabe'})")
    print(f"Dateien im Paket: {e.anzahl_im_paket}")
    print(f"Ausgeschlossen: {e.anzahl_ausgeschlossen}")
    if e.ersetzte_pfade:
        print("Ersetzt/ergaenzt: " + ", ".join(e.ersetzte_pfade))
    if e.uebersprungen:
        print(f"Uebersprungen (Symlink oder im Arbeitsbaum fehlend): {', '.join(e.uebersprungen)}")
    if e.uncommitted_hinweis:
        print("Hinweis: Der Arbeitsbaum hat nicht committete Aenderungen -- das Paket "
              "enthaelt den Stand von HEAD.")
    # Punkt 6b: "Ohne Datenbank (CI): Regel uebersprungen, die Ausgabe sagt das."
    if e.firmen_db_pfad:
        print(f"Firmennamen-Regel: geprueft gegen {e.firmen_db_pfad}")
    else:
        print("Firmennamen-Regel: uebersprungen (keine Datenbank gefunden).")
    # P2-83: Dasselbe fuer die Regeln aus dem Profil (Anschrift, Kontaktdaten, Name des Nutzers).
    if e.profil_gelesen:
        print("Profil-Regeln (Anschrift, Kontakt, Name): geprueft gegen das Profil.")
    else:
        print("Profil-Regeln (Anschrift, Kontakt, Name): uebersprungen (kein Profil gefunden).")
    if e.funde:
        print(f"Funde: {len(e.funde)}")
        for f in e.funde:
            ort = f"{f.pfad}:{f.zeile}" if f.zeile else f.pfad
            print(f"  {ort}  [{f.regel}]  {f.ausschnitt}")
        print("Kein ZIP geschrieben (Funde vorhanden).")
    elif e.zip_pfad:
        print(f"ZIP: {e.zip_pfad} ({e.zip_groesse} Bytes)")
    else:
        print("Nur geprueft, kein ZIP geschrieben (--pruefen).")


def main(argv: list[str] | None = None, projekt_root: Path = PROJECT_ROOT) -> int:
    ap = argparse.ArgumentParser(prog="pipeline.kundenpaket", description=__doc__.split("\n")[0])
    ap.add_argument("--arbeitsbaum", action="store_true",
                     help="Quelle ist der aktuelle Arbeitsbaum (Vorschau/Tests) statt git archive")
    ap.add_argument("--ref", default=None,
                     help="Git-Revision fuer git archive (Default HEAD; nur ohne --arbeitsbaum)")
    ap.add_argument("--ziel-ordner", dest="ziel", default=None,
                     help="Zielordner fuer das ZIP (Default outputs/kundenpaket/)")
    ap.add_argument("--pruefen", action="store_true", help="nur pruefen und berichten, kein ZIP")
    args = ap.parse_args(argv)

    try:
        ergebnis = bauen(arbeitsbaum=args.arbeitsbaum, ref=args.ref, ziel=args.ziel,
                          nur_pruefen=args.pruefen, projekt_root=projekt_root)
    except KundenpaketFehler as exc:
        print(f"Fehler: {exc}")
        return 2

    _ausgabe_drucken(ergebnis)
    return 1 if ergebnis.funde else 0


if __name__ == "__main__":
    raise SystemExit(main())

