#!/usr/bin/env python3
"""Update-Werkzeug beim Kunden (P2-51, Arbeitspaket U1) -- spielt ein neues BMS-Programmpaket
in eine bestehende Installation ein, ohne Datenbank oder Anpassungen zu verlieren.

NUR STANDARDBIBLIOTHEK, KEINE IMPORTE AUS `app`/`pipeline`: Dieses Skript laeuft neben einer
halb ersetzten Installation -- es darf sich nie auf den (gerade instabilen) Programmcode
verlassen, den es selbst ueberschreibt. `backend/app/selbsttest.py` ist die einzige Stelle, die
NACH dem Schreiben `app.*` importiert, und das bewusst in einem eigenen Subprozess (s. dort).

NETZ (P2-82, s. tasks/spec_p2-82_lizenz_raus_update_github.md, Vertrag U): Ausser dem lokalen
`GET 127.0.0.1/api/health` spricht dieses Werkzeug nur in Schritt 2 mit GitHub, und nur auf Start
des Kunden. `online_auskunft()` fragt `api.github.com` nach dem neuesten Release des Repositorys
`GITHUB_REPO` (`GET /repos/<Repo>/releases/latest`, ohne Anmeldung, ohne Token, nur der
`User-Agent: BMS-Update`), `online_laden(auskunft, ziel)` holt `BMS_<Version>.zip` von dort. Eine
Lizenzdatei gibt es nicht mehr: sie wird weder gelesen noch gesendet, uebertragen wird allein die
Anfrage selbst, und GitHub sieht dabei die IP-Adresse des Rechners. Die Pruefsumme kommt aus dem
Feld `digest` des Release-Assets (Fallback: das Asset `BMS_<Version>.zip.sha256`; fehlt beides, wird
nichts eingespielt). Regeln: Die Zertifikatspruefung bleibt immer an. Die Auskunft folgt keiner
Umleitung; beim Laden folgt das Werkzeug hoechstens `UMLEITUNGEN_MAX` Umleitungen, jede nur nach
`https://` und nur zu `github.com` oder einem Host mit der Endung `.githubusercontent.com`. Die
Proxy-Einstellungen des Rechners gelten weiter (Firmennetze). Repo und Adressen stehen als
Konstanten im Quelltext (keine Umgebungsvariable). `--offline` und ein Pfad-Argument unterbinden
jeden Kontakt.

AUFRUF (aus update.command / update_windows.bat, s. dort):
    bms_update.py [PAKET] --installation DIR [--pruefen] [--ja] [--erzwingen] [--zurueck]
                  [--offline] [--ohne-abhaengigkeiten] [--ohne-selbsttest] [--delegiert]

EXIT-CODES: 0 fertig oder nichts zu tun, 1 abgebrochen ohne Aenderung, 2 fehlgeschlagen und
zurueckgerollt, 3 Aufruf falsch (Argumente).

ABLAUF (13 Schritte, s. Bau-Spec tasks/spec_p2-51_updates_versionen_neutral.md, Abschnitt
"Paket U1" fuer die volle Herleitung):
  1 Installation pruefen (kein Git-Checkout, laeuft in der venv)
  2 Paket finden (P2-82: ein Pfad-Argument gilt, dann ohne jeden Netzkontakt; sonst gewinnt die
    hoechste Version aus dem neuesten GitHub-Release und den Dateien ~/Downloads/BMS_*.zip.
    Online wird nur gefragt, wenn --offline fehlt; jeder Fehler dort ist ein Hinweis, kein
    Abbruch. Das geladene Paket liegt unter <data>/updates/pakete/BMS_<Version>.zip und gilt
    danach wie ein uebergebenes)
  3 Selbstaktualisierung (weicht das Skript IM Paket vom laufenden ab, an die neue Fassung
    delegieren -- so gilt immer die Update-LOGIK der neuen Version, nicht der alten)
  4 Paket pruefen (Manifest V3, SHA-256, keine unsicheren/geschuetzten Pfade, Version, Vorschau)
  5 Server aus? (GET /api/health)
  6 Plan erstellen und anzeigen (--pruefen endet hier)
  7 Rueckfrage (uebersprungen mit --ja)
  8 Sperre anlegen
  9 Sicherung (Datenbank, jede ersetzte/entfernte Datei, altes Manifest, ggf. altes dist/)
 10 Dateien schreiben (atomar)
 11 Abhaengigkeiten (pip / npm ci / Oberflaeche bauen)
 12 Selbsttest (eigener Subprozess, s. backend/app/selbsttest.py)
 13 Abschluss: neues Manifest uebernehmen, Bericht schreiben, Sperre loesen

JEDER FEHLER AB SCHRITT 10 rollt vollstaendig zurueck (Exit 2) -- Sicherheit geht vor Komfort,
lieber abbrechen als eine Kundendatei in einem halb fertigen Zustand zu lassen. Schritte 1-9
aendern nichts am Programmordner; ein Abbruch dort ist Exit 1 (bzw. 3 fuer einen falschen Aufruf).

DATEIREGELN (s. Bau-Spec, Tabelle "Dateiregeln") -- `_datei_entscheiden()` setzt sie um: fuer
jeden Pfad aus altem UND neuem Manifest wird verglichen, ob die lokale Datei noch dem alten
Manifest-Hash entspricht (dann unveraendert vom Kunden -> gefahrlos ersetzen), vom alten
Hash ABWEICHT (Kunde hat editiert -> sichern + melden; bei einer per `anpassbar`-Muster als
kundenseitig editierbar markierten Datei -> behalten, neue Fassung nur zum Nachschlagen
ablegen) oder ganz fehlt (Kunde hat sie geloescht -> wiederherstellen, ausser bei `anpassbar`:
dann bleibt sie geloescht). `anpassbar` kommt IMMER aus dem NEUEN Manifest, auch fuer Pfade,
die im neuen Paket gar nicht mehr vorkommen (Spec V3).
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import http.client
import json
import os
import re
import shutil
import socket
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ── Exit-Codes (s. Moduldoc) ────────────────────────────────────────────────────────────────
EXIT_OK = 0
EXIT_ABGEBROCHEN = 1
EXIT_ZURUECKGEROLLT = 2
EXIT_AUFRUF_FALSCH = 3

MANIFEST_NAME = "bms_manifest.json"
SPERR_NAME = ".update.lock"

# ── GitHub-Releases (P2-82, Vertrag U) ──────────────────────────────────────────────────────
# Repo und Adressen BEWUSST als Konstanten, keine Umgebungsvariablen (Leitentscheidung 2): wer sie
# umbiegen koennte, koennte dem Kunden ein fremdes Paket unterschieben. Nur die Tests ersetzen sie im
# Prozess (auf einen Probeserver unter 127.0.0.1). `GITHUB_REPO` steht zusaetzlich in
# backend/app/update_pruefen.py (dort darf dieses Skript nichts importieren); ein Test haelt beide
# gleich.
GITHUB_REPO = "holgerdaube/BewerbungsMgmtSystem"
GITHUB_API = "https://api.github.com"
GITHUB_SEITE = "https://github.com"      # Herkunft der Download-Adressen und der Release-Seite
ZEIT_AUSKUNFT_S = 10          # Zeitgrenze je Netzvorgang bei der Auskunft
ZEIT_LADEN_S = 120            # Zeitgrenze je Netzvorgang beim Laden des Pakets
PAKET_MAX_BYTES = 200 * 1024 * 1024
UMLEITUNGEN_MAX = 3           # so viele Umleitungen folgt das Laden, die Auskunft keiner
_AUSKUNFT_MAX_BYTES = 1024 * 1024      # Antwort der Release-Auskunft: hoechstens 1 MB lesen
_PRUEFSUMMENDATEI_MAX_BYTES = 4 * 1024
_LESEBLOCK = 64 * 1024
_UMLEITUNGS_CODES = (301, 302, 303, 307, 308)
_ERLAUBTER_HOST = "github.com"
_ERLAUBTE_HOST_ENDUNG = ".githubusercontent.com"

# Pfade, die ein Paket NIEMALS ausliefern darf (Bau-Spec, Schritt "Paket pruefen") -- unabhaengig
# von `anpassbar`: selbst ein manipuliertes Manifest darf den Rechten der Installation nichts von
# diesen Orten ueberschreiben. Praefix mit "/" = ganzer Ordner, sonst exakter Pfad (gleiche
# Matching-Logik wie backend/pipeline/kundenpaket.py::_pfad_trifft).
GESCHUETZTE_PFADE: tuple[str, ...] = (
    "data/", "outputs/", ".git/", "frontend/node_modules/", "frontend/dist/",
    "config/profil.md", "config/suchprofile.yaml", "config/zielfirmen.md",
    "config/budgets.yaml", MANIFEST_NAME,
)

_RUECKFRAGE_JA = ("j", "y")
_LAUFWERK_RE = re.compile(r"^[A-Za-z]:")

# Strenge Formen fuer Werte aus der Antwort von GitHub (P2-82). Nur ASCII-Ziffern und `fullmatch`
# (kein `$`, das ein Zeilenende durchliesse): die Version landet in einer Adresse und in einem
# Dateinamen. Hoechstens 9 Stellen je Teil, damit der Dateiname kurz bleibt.
_VERSION_RE = re.compile(r"[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_DIGEST_RE = re.compile(r"sha256:([0-9a-f]{64})")

# Kundentexte der Online-Suche (Sie-Form, ohne Phasen-Nummer).
_TEXT_KEINE_VERBINDUNG = "Es besteht keine Verbindung zu GitHub."
_TEXT_ZEITUEBERSCHREITUNG = "GitHub antwortet nicht rechtzeitig."
_TEXT_UNTERBROCHEN = "Die Verbindung zu GitHub wurde unterbrochen."
_TEXT_ZERTIFIKAT = "Die sichere Verbindung zu GitHub ließ sich nicht prüfen."
_TEXT_ANTWORT_UNGUELTIG = "Die Antwort von GitHub ist ungültig."
_TEXT_NOCH_KEINE_VERSION = "Es ist noch keine Version veröffentlicht."
_TEXT_ANFRAGEGRENZE = "GitHub begrenzt gerade die Anfragen. Bitte versuchen Sie es in einer Stunde erneut."
_TEXT_PRUEFSUMME_FEHLT = "Zur neuesten Version fehlt die Prüfsumme. Sie wird nicht eingespielt."
_TEXT_PAKET_BESCHAEDIGT = "Das geladene Paket ist unvollständig oder beschädigt."


# ── Terminalsprache (P2-95) ─────────────────────────────────────────────────────────────────
# Regel: Steht das Betriebssystem auf Deutsch, bleibt jede Meldung wie sie ist; in jedem anderen
# Fall (und bei jedem Fehler der Erkennung) kommt Englisch. Unabhaengig von der Oberflaechensprache
# der App. Alles in dieser einen Datei, weil das Skript aus Entpack-Ordnern laeuft (keine
# Geschwister-Module). Die deutschen Texte sind zugleich die Schluessel von `_EN`.
_SPRACHE_ZWISCHENSPEICHER: str | None = None   # nur das Ergebnis der Systemabfrage; Tests setzen es zurueck


def _system_sprache_roh() -> str:
    """Sprachwert des Betriebssystems (z. B. "de-DE", "en_GB") oder "" wenn nichts zu ermitteln
    ist. macOS: erster Eintrag von `defaults read -g AppleLanguages`, sonst `AppleLocale`. Windows:
    `GetUserDefaultUILanguage`. Sonst (und wenn das System nichts liefert): LC_ALL, LC_MESSAGES,
    LANG. Fehler wirft die Funktion weiter, `_terminal_sprache()` macht daraus Englisch."""
    if sys.platform == "darwin":
        ergebnis = subprocess.run(["defaults", "read", "-g", "AppleLanguages"],
                                  capture_output=True, text=True, timeout=5)
        if ergebnis.returncode == 0:
            for zeile in ergebnis.stdout.splitlines():
                eintrag = zeile.strip().strip(",").strip('"').strip()
                if eintrag and eintrag not in ("(", ")"):
                    return eintrag
        ergebnis = subprocess.run(["defaults", "read", "-g", "AppleLocale"],
                                  capture_output=True, text=True, timeout=5)
        if ergebnis.returncode == 0 and ergebnis.stdout.strip():
            return ergebnis.stdout.strip()
    elif sys.platform == "win32":
        import ctypes
        kennung = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return "de" if (kennung & 0x3FF) == 0x07 else "en"     # 0x07 = LANG_GERMAN
    return (os.environ.get("LC_ALL", "").strip() or os.environ.get("LC_MESSAGES", "").strip()
            or os.environ.get("LANG", "").strip())


def _terminal_sprache() -> str:
    """"de" oder "en". Reihenfolge: Umgebungsvariable BMS_TERMINAL_SPRACHE (de/en, wird bei jedem
    Aufruf gelesen), dann das Betriebssystem (einmal je Prozess zwischengespeichert). Beginnt der
    Wert mit "de", gilt Deutsch; alles andere und jeder Fehler: Englisch."""
    global _SPRACHE_ZWISCHENSPEICHER
    vorgabe = os.environ.get("BMS_TERMINAL_SPRACHE", "").strip().lower()
    if vorgabe in ("de", "en"):
        return vorgabe
    if _SPRACHE_ZWISCHENSPEICHER is None:
        try:
            roh = _system_sprache_roh().strip().lower()
            _SPRACHE_ZWISCHENSPEICHER = "de" if roh.startswith("de") else "en"
        except Exception:
            _SPRACHE_ZWISCHENSPEICHER = "en"
    return _SPRACHE_ZWISCHENSPEICHER


# Deutscher Text (mit benannten Platzhaltern) -> englischer Text. Jeder Platzhalter steht in beiden.
_EN: dict[str, str] = {
    # Kundentexte der Online-Suche
    "Es besteht keine Verbindung zu GitHub.": "There is no connection to GitHub.",
    "GitHub antwortet nicht rechtzeitig.": "GitHub did not respond in time.",
    "Die Verbindung zu GitHub wurde unterbrochen.": "The connection to GitHub was interrupted.",
    "Die sichere Verbindung zu GitHub ließ sich nicht prüfen.":
        "The secure connection to GitHub could not be verified.",
    "Die Antwort von GitHub ist ungültig.": "The response from GitHub is invalid.",
    "Es ist noch keine Version veröffentlicht.": "No version has been released yet.",
    "GitHub begrenzt gerade die Anfragen. Bitte versuchen Sie es in einer Stunde erneut.":
        "GitHub is currently limiting requests. Please try again in an hour.",
    "Zur neuesten Version fehlt die Prüfsumme. Sie wird nicht eingespielt.":
        "The checksum for the latest version is missing. It will not be installed.",
    "Das geladene Paket ist unvollständig oder beschädigt.":
        "The downloaded package is incomplete or damaged.",
    # Installation und Paket finden
    "Der Ordner „{installation}“ wurde nicht gefunden.": "The folder “{installation}” was not found.",
    "Dies ist eine Entwicklungsinstallation mit Git. Bitte Updates dort über Git einspielen, nicht über dieses Werkzeug.":
        "This is a development installation with Git. Please apply updates there using Git, not with this tool.",
    "Dieses Werkzeug muss über die mitgelieferte Python-Umgebung laufen. Bitte update.command (Mac) bzw. update_windows.bat (Windows) verwenden, nicht scripts/bms_update.py direkt.":
        "This tool must run in the Python environment supplied with BMS. Please use update.command (Mac) or update_windows.bat (Windows), not scripts/bms_update.py directly.",
    "Kein Update-Paket gefunden. Legen Sie die Datei „BMS_<Version>.zip“ in den Download-Ordner ({downloads}).":
        "No update package found. Put the file “BMS_<version>.zip” in your downloads folder ({downloads}).",
    "Mehrere Pakete gefunden, verwende die höchste Version: {name}":
        "Several packages found, using the highest version: {name}",
    "Die Paketdatei „{pfad}“ wurde nicht gefunden.": "The package file “{pfad}” was not found.",
    "Das Paket lässt sich nicht in „{ordner}“ speichern ({grund}).":
        "The package cannot be saved in “{ordner}” ({grund}).",
    "Online-Suche übersprungen: Sie haben --offline angegeben.":
        "Online search skipped: you specified --offline.",
    "Suche auf GitHub nach einer neuen Version. GitHub erhält dabei die IP-Adresse dieses Rechners.":
        "Searching GitHub for a new version. GitHub will see this computer’s IP address.",
    "Online-Suche nicht möglich: {grund}": "Online search not possible: {grund}",
    "Version {version} gefunden, das Paket liegt bereits geladen vor.":
        "Version {version} found, the package has already been downloaded.",
    "Version {version} gefunden, lade {groesse} MB …": "Version {version} found, downloading {groesse} MB …",
    "Paket geladen und geprüft.": "Package downloaded and verified.",
    "Laden nicht möglich: {grund}": "Download not possible: {grund}",
    "Ihr BMS ist auf dem neuesten Stand (Version {version}).":
        "Your BMS is up to date (version {version}).",
    "unbekannt": "unknown",
    "keine": "none",
    # Paket prüfen
    "Die Paketdatei „{pfad}“ lässt sich nicht lesen: {fehler}":
        "The package file “{pfad}” cannot be read: {fehler}",
    "Die Paketdatei ist beschädigt (fehlerhafter Eintrag: {eintrag}).":
        "The package file is damaged (faulty entry: {eintrag}).",
    "Die Paketdatei enthält kein bms_manifest.json.": "The package file does not contain a bms_manifest.json.",
    "bms_manifest.json im Paket ist beschädigt: {fehler}": "bms_manifest.json in the package is damaged: {fehler}",
    "Dieses Paket hat ein unbekanntes Format ({format!r}). Bitte eine neuere Fassung des Update-Werkzeugs verwenden.":
        "This package has an unknown format ({format!r}). Please use a newer version of the update tool.",
    "Die Paketdatei enthält einen unsicheren Pfad: {pfad}": "The package file contains an unsafe path: {pfad}",
    "Die Paketdatei enthält einen geschützten Pfad: {pfad}": "The package file contains a protected path: {pfad}",
    "Der Paketdatei fehlen Einträge: {liste}": "The package file is missing entries: {liste}",
    "Die Paketdatei enthält unerwartete Einträge: {liste}":
        "The package file contains unexpected entries: {liste}",
    "„{pfad}“ hat im Paket eine andere Größe als im Manifest angegeben.":
        "“{pfad}” has a different size in the package from the one given in the manifest.",
    "„{pfad}“ stimmt nicht mit der Prüfsumme im Manifest überein (Paket möglicherweise beschädigt oder unvollständig).":
        "“{pfad}” does not match the checksum in the manifest (the package may be damaged or incomplete).",
    "Dieses Paket ist eine Vorschau (kein freigegebener Stand) und wird ohne --erzwingen nicht eingespielt.":
        "This package is a preview (not a released version) and will not be installed without --erzwingen.",
    "Die Paketversion ({neu}) ist nicht neuer als die installierte Version ({alt}). Mit --erzwingen dennoch einspielen.":
        "The package version ({neu}) is not newer than the installed version ({alt}). Install it anyway with --erzwingen.",
    # Plan
    "„{pfad}“ wurde von Ihnen entfernt und bleibt entfernt (angepasste Datei).":
        "“{pfad}” was removed by you and stays removed (customised file).",
    "„{pfad}“ stand im installierten Manifest, ist aber ein unsicherer oder geschützter Pfad und wurde übersprungen.":
        "“{pfad}” was listed in the installed manifest, but it is an unsafe or protected path and was skipped.",
    "Installierte Version: {version}": "Installed version: {version}",
    "Neue Version: {version}": "New version: {version}",
    "Dateien: {neu} neu, {geaendert} geändert, {entfernt} entfernt.":
        "Files: {neu} new, {geaendert} changed, {entfernt} removed.",
    "Von Ihnen geänderte Programmdateien werden gesichert und ersetzt: {dateien}":
        "Program files you have changed will be backed up and replaced: {dateien}",
    "Angepasste Dateien bleiben erhalten: {dateien}": "Customised files will be kept: {dateien}",
    "Python-Pakete": "Python packages",
    "Oberflächen-Bausteine (npm ci)": "interface components (npm ci)",
    "Oberfläche neu bauen": "rebuild the interface",
    "Abhängigkeiten: {liste}": "Dependencies: {liste}",
    # Sperre, Abhängigkeiten, Selbsttest
    "Es läuft bereits ein Update, oder ein vorheriges wurde nicht sauber beendet. Wenn Sie sicher sind, dass kein Update läuft, löschen Sie „{lock}“ und versuchen Sie es erneut.":
        "An update is already running, or a previous one did not finish cleanly. If you are sure no update is running, delete “{lock}” and try again.",
    "Installation der Python-Pakete fehlgeschlagen.": "Installing the Python packages failed.",
    "npm wurde nicht gefunden.": "npm was not found.",
    "Installation der Oberflächen-Bausteine fehlgeschlagen.": "Installing the interface components failed.",
    "Bauen der Oberfläche fehlgeschlagen.": "Building the interface failed.",
    "Hinweis: Selbsttest übersprungen (backend/app/selbsttest.py ist in diesem Paket nicht enthalten).":
        "Note: self-test skipped (backend/app/selbsttest.py is not included in this package).",
    "Selbsttest hat das Zeitlimit überschritten.": "The self-test exceeded the time limit.",
    "Selbsttest fehlgeschlagen:\n{ausgabe}": "Self-test failed:\n{ausgabe}",
    # Ablauf
    "Das BMS läuft noch. Beenden Sie es zuerst mit stop.command bzw. stop_windows.bat.":
        "BMS is still running. Stop it first with stop.command or stop_windows.bat.",
    "Für dieses Update muss die Oberfläche neu gebaut werden, npm wurde aber nicht gefunden. Bitte Node.js installieren und erneut versuchen.":
        "This update requires the interface to be rebuilt, but npm was not found. Please install Node.js and try again.",
    "Update von {alt} auf {neu} jetzt einspielen? [j/N] ":
        "Install the update from {alt} to {neu} now? [y/N] ",
    "Abgebrochen. Es wurde nichts verändert.": "Cancelled. Nothing was changed.",
    "Sicherung fehlgeschlagen, es wurde nichts verändert: {fehler}":
        "Backup failed, nothing was changed: {fehler}",
    "Update fehlgeschlagen, alle Änderungen wurden zurückgerollt: {fehler}\nSicherung liegt unter: {ordner}\nHinweis: Python- oder Oberflächen-Bausteine können bereits auf dem neuen Stand sein.":
        "Update failed, all changes have been rolled back: {fehler}\nBackup is located at: {ordner}\nNote: Python packages or interface components may already be at the new version.",
    "Update auf Version {version} abgeschlossen. Starten Sie das BMS wie gewohnt.":
        "Update to version {version} complete. Start BMS as usual.",
    "Es gibt kein Update, das rückgängig gemacht werden kann.": "There is no update that can be undone.",
    "Datenbank auf den Stand vor dem Update zurücksetzen? Alle Änderungen seit dem Update gehen verloren. [j/N] ":
        "Reset the database to its state before the update? All changes made since the update will be lost. [y/N] ",
    "Update zurückgenommen. Installierte Version jetzt: {version}.":
        "Update undone. Installed version is now: {version}.",
    "Die Datenbank wurde auf den Stand vor dem Update zurückgesetzt.":
        "The database was reset to its state before the update.",
    "Fehler: {fehler}": "Error: {fehler}",
    "Fehlgeschlagen: {fehler}": "Failed: {fehler}",
    # Befehlszeile
    "Spielt eine neue BMS-Version ein, ohne Daten oder Anpassungen zu verlieren.":
        "Installs a new BMS version without losing your data or customisations.",
    "Pfad zu einem BMS_*.zip-Paket (sonst gewinnt die höchste Version aus dem neuesten GitHub-Release und dem Download-Ordner; mit einem Pfad findet kein Netzkontakt statt).":
        "Path to a BMS_*.zip package (otherwise the highest version from the latest GitHub release and the downloads folder is used; with a path, no network contact takes place).",
    "Programmordner der Installation.": "Program folder of the installation.",
    "Nur prüfen und den Ablaufplan zeigen, nichts ändern.": "Only check and show the plan, change nothing.",
    "Rückfrage vor dem Einspielen automatisch bestätigen.": "Confirm the question before installing automatically.",
    "Vorschau-Pakete und gleiche/ältere Versionen dennoch einspielen.":
        "Install preview packages and same or older versions anyway.",
    "Nicht online nach einer neuen Version suchen.": "Do not search online for a new version.",
    "Letztes Update rückgängig machen, statt ein neues einzuspielen.":
        "Undo the last update instead of installing a new one.",
    "Bei --zurueck die Datenbank ohne Rückfrage mit zurücksetzen (nur für Tests und Notfälle; --ja allein beantwortet diese Frage NICHT).":
        "With --zurueck, also reset the database without asking (for tests and emergencies only; --ja alone does NOT answer this question).",
    "Python- und npm-Abhängigkeiten nicht installieren (nur für Tests und Notfälle).":
        "Do not install Python and npm dependencies (for tests and emergencies only).",
    "Selbsttest nach dem Einspielen überspringen (nur für Tests und Notfälle).":
        "Skip the self-test after installing (for tests and emergencies only).",
    "Intern: markiert, dass bereits an die im Paket enthaltene Werkzeug-Fassung übergeben wurde, keine erneute Selbstaktualisierung.":
        "Internal: marks that control has already passed to the tool version contained in the package, so no further self-update.",
}


def _t(deutsch: str, **werte: object) -> str:
    """Meldung in der Terminalsprache. `deutsch` ist der deutsche Text mit benannten Platzhaltern
    ({name}); auf Deutsch kommt er (mit den eingesetzten Werten) unveraendert heraus, sonst der
    Eintrag in `_EN`. Ohne Werte wird nichts formatiert."""
    text = deutsch if _terminal_sprache() == "de" else _EN.get(deutsch, deutsch)
    return text.format(**werte) if werte else text


class Abbruch(Exception):
    """Sauberer Abbruch VOR jeder Aenderung -- `nachricht` ist Kundentext (Sie-Form)."""

    def __init__(self, nachricht: str, exit_code: int = EXIT_ABGEBROCHEN):
        super().__init__(nachricht)
        self.nachricht = nachricht
        self.exit_code = exit_code


class Fehlgeschlagen(Exception):
    """Fehler AB Schritt 10 -- fuehrt zum Zurueckrollen. `nachricht` ist Kundentext."""

    def __init__(self, nachricht: str):
        super().__init__(nachricht)
        self.nachricht = nachricht


class OnlineFehler(Exception):
    """Die Online-Suche oder das Laden bei GitHub ist gescheitert (P2-82). Die Nachricht ist
    Kundentext (Sie-Form). Im Ablauf nur ein Hinweis, kein Abbruch: es geht mit dem Paket aus dem
    Download-Ordner weiter."""

    def __init__(self, nachricht: str):
        super().__init__(nachricht)
        self.nachricht = nachricht


class _ArgparseFehler(Exception):
    """Traegt argparse-Fehlermeldungen weiter, statt dass ArgumentParser().error() den
    Prozess per SystemExit(2) sofort beendet -- main() uebersetzt das auf Exit 3 (Aufruf falsch,
    s. Moduldoc) und bleibt fuer main([...])-Aufrufe aus Tests ein normaler Rueckgabewert."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ArgparseFehler(message)


# ── Datenmodell des Ablaufplans (Schritt 6) ─────────────────────────────────────────────────
@dataclass
class DateiAktion:
    pfad: str
    art: str                              # "schreiben" | "entfernen" | "behalten" | "nichts"
    anpassbar: bool
    bucket: str | None = None             # "neu" | "geaendert" | "entfernt" | "anpassbar_behalten"
    melde_lokal_geaendert: bool = False   # zusaetzlich in bericht["lokal_geaendert_gesichert"]
    neue_fassung_ablegen: bool = False    # neue_fassungen/<pfad> = neuer Inhalt (behaltene, abweichende anpassbare Datei)
    inhalt: bytes | None = None           # neuer Inhalt bei art == "schreiben" bzw. neue_fassung_ablegen
    ausfuehrbar: bool = False
    hinweis: str | None = None            # Freitext fuer Faelle ausserhalb der 5 Report-Buckets


@dataclass
class Plan:
    installierte_version: str | None
    neue_version: str
    aktionen: list[DateiAktion]
    pip_noetig: bool
    npm_ci_noetig: bool
    build_noetig: bool
    npm_fehlt: bool
    kein_altes_manifest: bool
    hinweise: list[str] = field(default_factory=list)   # z. B. verworfene Pfade aus dem alten Manifest


# ── Kleine Hilfsfunktionen (einzeln testbar/mockbar) ────────────────────────────────────────
def _sha256(daten: bytes) -> str:
    return hashlib.sha256(daten).hexdigest()


def _version_tupel(text: str) -> tuple[int, int, int] | None:
    """Eigene, schlanke Kopie von `pipeline.changelog.version_tupel()` -- dieses Skript darf
    `pipeline` nicht importieren (s. Moduldoc)."""
    teile = text.strip().split(".")
    if len(teile) != 3:
        return None
    try:
        return (int(teile[0]), int(teile[1]), int(teile[2]))
    except ValueError:
        return None


def _laeuft_nicht_in_venv() -> bool:
    """True, wenn der aktuelle Python-Prozess NICHT in einer venv laeuft (`sys.prefix ==
    sys.base_prefix`). Eigene Funktion statt der Inline-Bedingung, damit Tests sie gezielt
    monkeypatchen koennen -- der echte Interpreter, unter dem die Testsuite laeuft (lokale venv
    des Projekts ODER ein CI-Runner ohne venv), soll fuer die UEBRIGEN Tests keine Rolle
    spielen (nur der eine Test fuer diese Pruefung selbst hebt den Patch gezielt auf)."""
    return sys.prefix == sys.base_prefix


def _server_laeuft(port: int | None = None) -> bool:
    """Schritt 5: GET http://127.0.0.1:<PORT>/api/health, Timeout 1 s. JEDE HTTP-Antwort
    (auch ein Fehlerstatus) zaehlt als "laeuft noch" -- Sicherheit geht vor Komfort. Nur ein
    echter Verbindungsfehler (nichts hoert auf dem Port) gilt als "aus"."""
    port = port or int(os.environ.get("PORT", "8000"))
    url = f"http://127.0.0.1:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=1):
            return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


def _npm_pfad() -> str | None:
    return shutil.which("npm")


def _pfad_unsicher(pfad: str) -> bool:
    """Absolut, Backslash, Laufwerksbuchstabe oder ein ".."/leeres Segment -- jede Form, mit der
    ein Eintrag aus dem ZIP-Ordner ausbrechen koennte (Zip-Slip)."""
    if not pfad or pfad.startswith("/") or "\\" in pfad:
        return True
    if _LAUFWERK_RE.match(pfad):
        return True
    return any(teil in ("", "..") for teil in pfad.split("/"))


def _pfad_geschuetzt(pfad: str) -> bool:
    for muster in GESCHUETZTE_PFADE:
        if muster.endswith("/"):
            if pfad.startswith(muster):
                return True
        elif pfad == muster:
            return True
    return False


def _data_dir(installation: Path) -> Path:
    """Gleiche Regel wie `app/db.py::DATA_DIR` -- hier eigenstaendig nachgebaut (kein Import
    aus app.*), s. Bau-Spec V4: BMS_DATA_DIR, sonst <Programmordner>/data."""
    return Path(os.environ.get("BMS_DATA_DIR", str(installation / "data")))


# ── Schritt 1: Installation pruefen ─────────────────────────────────────────────────────────
def _installation_pruefen(installation: Path) -> None:
    if not installation.is_dir():
        raise Abbruch(_t("Der Ordner „{installation}“ wurde nicht gefunden.", installation=installation))
    if (installation / ".git").exists():
        raise Abbruch(_t("Dies ist eine Entwicklungsinstallation mit Git. Bitte Updates dort über "
                         "Git einspielen, nicht über dieses Werkzeug."))
    if _laeuft_nicht_in_venv():
        raise Abbruch(_t("Dieses Werkzeug muss über die mitgelieferte Python-Umgebung laufen. Bitte "
                         "update.command (Mac) bzw. update_windows.bat (Windows) verwenden, nicht "
                         "scripts/bms_update.py direkt."))


# ── Schritt 2: Paket finden ──────────────────────────────────────────────────────────────────
def _paket_version_lesen(pfad: Path) -> tuple[int, int, int] | None:
    try:
        with zipfile.ZipFile(pfad) as zf:
            manifest = json.loads(zf.read(MANIFEST_NAME))
        return _version_tupel(str(manifest.get("version", "")))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, OSError, ValueError):
        return None


def _downloads_kandidaten() -> tuple[Path, list[tuple[tuple[int, int, int], Path]]]:
    """(Download-Ordner, gueltige Pakete darin als (Version, Pfad), aufsteigend nach Version)."""
    downloads = Path.home() / "Downloads"
    kandidaten = sorted(downloads.glob("BMS_*.zip")) if downloads.is_dir() else []
    gueltige: list[tuple[tuple[int, int, int], Path]] = []
    for kandidat in kandidaten:
        version = _paket_version_lesen(kandidat)
        if version is not None:
            gueltige.append((version, kandidat))
    gueltige.sort(key=lambda paar: paar[0])
    return downloads, gueltige


def _kein_paket_text(downloads: Path) -> str:
    return _t("Kein Update-Paket gefunden. Legen Sie die Datei „BMS_<Version>.zip“ in "
              "den Download-Ordner ({downloads}).", downloads=downloads)


def _hoechstes_aus_downloads(gueltige: list[tuple[tuple[int, int, int], Path]]) -> Path:
    if len(gueltige) > 1:
        print(_t("Mehrere Pakete gefunden, verwende die höchste Version: {name}",
                 name=gueltige[-1][1].name))
    return gueltige[-1][1]


def _paket_finden(paket_arg: str | None) -> Path:
    """Paket OHNE jeden Netzkontakt: das Pfad-Argument, sonst die hoechste gueltige Version unter
    ~/Downloads. Die Online-Suche (P2-82) liegt darueber in `_paket_beschaffen()`."""
    if paket_arg:
        pfad = Path(paket_arg)
        if not pfad.is_file():
            raise Abbruch(_t("Die Paketdatei „{pfad}“ wurde nicht gefunden.", pfad=pfad))
        return pfad

    downloads, gueltige = _downloads_kandidaten()
    if not gueltige:
        raise Abbruch(_kein_paket_text(downloads))
    return _hoechstes_aus_downloads(gueltige)


# ── Schritt 2, online: GitHub-Releases (P2-82, Vertrag U "Netzregeln") ──────────────────────
def _ssl_kontext() -> ssl.SSLContext:
    """Standardkontext: Zertifikat UND Hostname werden immer geprueft. Es gibt keinen Weg im
    Werkzeug, das abzuschalten, und nach einem Zertifikatsfehler wird nie ohne Pruefung
    wiederholt."""
    return ssl.create_default_context()


def _opener() -> urllib.request.OpenerDirector:
    """Eigener Opener OHNE Umleitungs-Handler: eine 3xx-Antwort wird als HTTPError gemeldet und
    der `Location`-Adresse nie von selbst gefolgt. Beim Laden entscheidet `_online_oeffnen()`
    Schritt fuer Schritt, ob eine Umleitung erlaubt ist (Leitentscheidung 6). Nur http(s), keine
    file:/ftp:-Handler. Der `ProxyHandler` liest die Proxy-Einstellungen des Rechners
    (Firmennetze), die Zertifikatspruefung gilt auch dort. Keine Standardkopfzeilen (`addheaders`
    leer): die Anfrage traegt allein, was `_online_oeffnen()` setzt, also weder Python- noch
    Systemname."""
    opener = urllib.request.OpenerDirector()
    opener.addheaders = []
    for handler in (urllib.request.ProxyHandler(), urllib.request.HTTPHandler(),
                    urllib.request.HTTPSHandler(context=_ssl_kontext()),
                    urllib.request.HTTPDefaultErrorHandler(), urllib.request.HTTPErrorProcessor(),
                    urllib.request.UnknownHandler()):      # fremdes Schema (file:, ftp:) -> URLError
        opener.add_handler(handler)
    return opener


def _statustext(code: int, *, auskunft: bool) -> str:
    """Kundentext zu einer Antwort ausser 200. Der Text des Servers wird NIE angezeigt: jede
    Antwort wird auf einen festen Satz abgebildet. 404 heisst bei der Auskunft "noch keine Version"
    (das Repository hat kein veroeffentlichtes Release), beim Laden ist es eine unbrauchbare
    Antwort."""
    if code in (403, 429):
        return _t(_TEXT_ANFRAGEGRENZE)
    if code == 404 and auskunft:
        return _t(_TEXT_NOCH_KEINE_VERSION)
    return _t(_TEXT_ANTWORT_UNGUELTIG)


def _netzfehlertext(ursache: object) -> str:
    """Kundentext zu einem Fehler beim Verbinden oder Lesen."""
    if isinstance(ursache, urllib.error.URLError):
        ursache = ursache.reason
    if isinstance(ursache, (TimeoutError, socket.timeout)):
        return _t(_TEXT_ZEITUEBERSCHREITUNG)
    if isinstance(ursache, ssl.SSLError):     # u. a. ssl.SSLCertVerificationError
        return _t(_TEXT_ZERTIFIKAT)
    if isinstance(ursache, (ConnectionError, http.client.HTTPException)) \
            and not isinstance(ursache, ConnectionRefusedError):
        return _t(_TEXT_UNTERBROCHEN)             # die Verbindung stand schon und riss ab
    return _t(_TEXT_KEINE_VERBINDUNG)


def _antwort_lesen(antwort, anzahl: int) -> bytes:
    """Liest hoechstens `anzahl` Byte aus der Antwort. Ein Fehler dabei (Zeitgrenze,
    abgerissene Verbindung) wird zum OnlineFehler mit Kundentext; Fehler beim SCHREIBEN auf die
    Platte gehoeren nicht hierher und bleiben OSError."""
    try:
        return antwort.read(anzahl)
    except (OSError, http.client.HTTPException) as exc:
        raise OnlineFehler(_netzfehlertext(exc)) from None


def _ziel_erlaubt(adresse: str) -> bool:
    """Darf das Werkzeug einer Umleitung zu dieser Adresse folgen? Nur `https://`, nur der Host
    `github.com` oder ein Host mit der Endung `.githubusercontent.com` (Download-Server von GitHub),
    nur der Standardport, keine Zugangsdaten in der Adresse, nur druckbares ASCII. Eigene Funktion,
    damit der Test mit dem Probeserver (http, 127.0.0.1) sie gezielt ersetzen kann; die echte
    Regel prueft ein eigener Test an einer Tabelle von Adressen (Leitentscheidung 6)."""
    if not adresse or not all(33 <= ord(zeichen) < 127 for zeichen in adresse):
        return False
    try:
        teile = urllib.parse.urlsplit(adresse)
        host, port = teile.hostname, teile.port
    except ValueError:
        return False
    if teile.scheme != "https" or not host or port not in (None, 443):
        return False
    if teile.username is not None or teile.password is not None:
        return False
    if host == _ERLAUBTER_HOST:
        return True
    return host.endswith(_ERLAUBTE_HOST_ENDUNG) and len(host) > len(_ERLAUBTE_HOST_ENDUNG)


def _online_oeffnen(adresse: str, kopfzeilen: dict[str, str], zeitgrenze: float, *,
                    auskunft: bool, umleitungen_max: int = 0):
    """GET `adresse`. Gibt die geoeffnete Antwort zurueck, aber nur bei genau 200; jede andere
    Antwort ist ein OnlineFehler mit festem Kundentext (`_statustext`). Bei `umleitungen_max` > 0
    folgt die Funktion so vielen Umleitungen (301/302/303/307/308), jede nur, wenn `_ziel_erlaubt()`
    das Ziel zulaesst; eine weitere Umleitung ist ebenso ein Fehler wie ein fremdes Ziel, zu dem
    dann nie eine Anfrage geht. Kopfzeilen: nur die uebergebenen (keine Version, kein Systemname,
    kein Token)."""
    for umleitungen in range(umleitungen_max + 1):
        anfrage = urllib.request.Request(adresse, method="GET", headers=kopfzeilen)
        try:
            antwort = _opener().open(anfrage, timeout=zeitgrenze)
        except urllib.error.HTTPError as exc:      # vor URLError/OSError: HTTPError ist deren Unterklasse
            try:
                code = exc.code
                ort = exc.headers.get("Location") if exc.headers is not None else None
            finally:
                exc.close()
            if code in _UMLEITUNGS_CODES and umleitungen_max > 0:
                if umleitungen >= umleitungen_max or not ort:
                    raise OnlineFehler(_t(_TEXT_ANTWORT_UNGUELTIG)) from None
                ziel = urllib.parse.urljoin(adresse, ort)
                if not _ziel_erlaubt(ziel):
                    raise OnlineFehler(_t(_TEXT_ANTWORT_UNGUELTIG)) from None
                adresse = ziel
                continue
            raise OnlineFehler(_statustext(code, auskunft=auskunft)) from None
        except (OSError, http.client.HTTPException, ValueError) as exc:
            raise OnlineFehler(_netzfehlertext(exc)) from None
        if antwort.status != 200:
            antwort.close()
            raise OnlineFehler(_t(_TEXT_ANTWORT_UNGUELTIG))
        return antwort
    raise OnlineFehler(_t(_TEXT_ANTWORT_UNGUELTIG))    # nicht erreichbar, die Schleife endet mit return/raise


def _download_url(version: str, name: str) -> str:
    """Die einzig erlaubte Download-Adresse eines Assets (Leitentscheidung 6 und Vertrag U):
    `<Seite>/<Repo>/releases/download/v<Version>/<Name>`."""
    return f"{GITHUB_SEITE}/{GITHUB_REPO}/releases/download/v{version}/{name}"


def _json_laden(adresse: str, zeitgrenze: float) -> object:
    """GET `adresse` ohne Umleitung, hoechstens 1 MB lesen, als JSON deuten. Wirft OnlineFehler."""
    kopf = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "BMS-Update"}
    with _online_oeffnen(adresse, kopf, zeitgrenze, auskunft=True) as antwort:
        roh = _antwort_lesen(antwort, _AUSKUNFT_MAX_BYTES + 1)
    if len(roh) > _AUSKUNFT_MAX_BYTES:
        raise OnlineFehler(_t(_TEXT_ANTWORT_UNGUELTIG))
    try:
        return json.loads(roh.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise OnlineFehler(_t(_TEXT_ANTWORT_UNGUELTIG)) from None


def _asset_finden(assets: object, name: str) -> dict | None:
    """Das erste Asset mit genau diesem Namen, sonst None."""
    if not isinstance(assets, list):
        return None
    for asset in assets:
        if isinstance(asset, dict) and asset.get("name") == name:
            return asset
    return None


def _pruefsumme_aus_datei(version: str, asset: dict) -> str:
    """Fallback nach Leitentscheidung 5: die erste Zeichenfolge der Datei `BMS_<Version>.zip.sha256`.
    Sie wird wie das Paket mit der Umleitungsregel geladen. Ist die Datei nicht zu bekommen oder
    nicht brauchbar, fehlt die Pruefsumme (Kundentext: das Paket wird nicht eingespielt). Ein
    Netzfehler (keine Verbindung, Zeitgrenze, Anfragegrenze) bleibt ein Netzfehler."""
    name = f"BMS_{version}.zip.sha256"
    url = asset.get("browser_download_url")
    if url != _download_url(version, name):
        raise OnlineFehler(_t(_TEXT_PRUEFSUMME_FEHLT))
    try:
        with _online_oeffnen(url, {"User-Agent": "BMS-Update"}, ZEIT_AUSKUNFT_S, auskunft=False,
                             umleitungen_max=UMLEITUNGEN_MAX) as antwort:
            roh = _antwort_lesen(antwort, _PRUEFSUMMENDATEI_MAX_BYTES + 1)
    except OnlineFehler as exc:
        if exc.nachricht == _t(_TEXT_ANTWORT_UNGUELTIG):        # 404, fremde Umleitung, 5xx: keine Datei
            raise OnlineFehler(_t(_TEXT_PRUEFSUMME_FEHLT)) from None
        raise
    if len(roh) > _PRUEFSUMMENDATEI_MAX_BYTES:
        raise OnlineFehler(_t(_TEXT_PRUEFSUMME_FEHLT))
    woerter = roh.decode("utf-8", errors="replace").split()
    kandidat = woerter[0].lower() if woerter else ""
    if not _SHA256_RE.fullmatch(kandidat):
        raise OnlineFehler(_t(_TEXT_PRUEFSUMME_FEHLT))
    return kandidat


def _auskunft_aus_release(daten: object) -> dict:
    """Prueft das Release-Objekt von GitHub und baut die Auskunft (Vertrag U): `version`, `url`,
    `groesse`, `sha256`, `seite`. Unbekannte Felder bleiben unbeachtet (GitHub ergaenzt welche).
    Wirft OnlineFehler."""
    if not isinstance(daten, dict):
        raise OnlineFehler(_t(_TEXT_ANTWORT_UNGUELTIG))
    tag = daten.get("tag_name")
    if not isinstance(tag, str):
        raise OnlineFehler(_t(_TEXT_ANTWORT_UNGUELTIG))
    version = tag[1:] if tag.startswith("v") else tag
    if not _VERSION_RE.fullmatch(version):
        raise OnlineFehler(_t(_TEXT_ANTWORT_UNGUELTIG))

    assets = daten.get("assets")
    paket = _asset_finden(assets, f"BMS_{version}.zip")
    if paket is None:
        raise OnlineFehler(_t(_TEXT_ANTWORT_UNGUELTIG))
    url, groesse = paket.get("browser_download_url"), paket.get("size")
    if url != _download_url(version, f"BMS_{version}.zip"):
        raise OnlineFehler(_t(_TEXT_ANTWORT_UNGUELTIG))
    if not (isinstance(groesse, int) and not isinstance(groesse, bool)
            and 1 <= groesse <= PAKET_MAX_BYTES):
        raise OnlineFehler(_t(_TEXT_ANTWORT_UNGUELTIG))

    digest = paket.get("digest")
    if digest is None:
        datei = _asset_finden(assets, f"BMS_{version}.zip.sha256")
        if datei is None:
            raise OnlineFehler(_t(_TEXT_PRUEFSUMME_FEHLT))
        pruefsumme = _pruefsumme_aus_datei(version, datei)
    else:
        treffer = _DIGEST_RE.fullmatch(digest) if isinstance(digest, str) else None
        if treffer is None:
            raise OnlineFehler(_t(_TEXT_ANTWORT_UNGUELTIG))
        pruefsumme = treffer.group(1)

    seite = daten.get("html_url")
    if not (isinstance(seite, str) and seite.startswith(f"{GITHUB_SEITE}/{GITHUB_REPO}/releases/")):
        seite = None       # nur Anzeige: eine fremde oder fehlende Seite stoppt das Update nicht
    return {"version": version, "url": url, "groesse": groesse, "sha256": pruefsumme, "seite": seite}


def online_auskunft() -> dict:
    """GET /repos/<GITHUB_REPO>/releases/latest: welche Version ist die neueste veroeffentlichte
    (ohne Entwuerfe und Vorabversionen)? Gibt die geprueften Angaben zurueck: `version`, `url`
    (Asset `BMS_<version>.zip`), `groesse`, `sha256`, `seite` (Release-Seite oder None). Keine
    Umleitung wird verfolgt, hoechstens 1 MB wird gelesen. Wirft bei JEDEM Fehler OnlineFehler mit
    dem Kundentext."""
    daten = _json_laden(f"{GITHUB_API}/repos/{GITHUB_REPO}/releases/latest", ZEIT_AUSKUNFT_S)
    return _auskunft_aus_release(daten)


def _auskunft_fuer_laden(auskunft: object) -> tuple[str, str, int, str]:
    """(version, url, groesse, sha256) aus einer Auskunft; prueft sie erneut mit denselben Regeln
    wie `online_auskunft()`, weil `online_laden()` auch mit einer von aussen gebauten Auskunft
    aufgerufen werden kann. Wirft OnlineFehler."""
    if not isinstance(auskunft, dict):
        raise OnlineFehler(_t(_TEXT_ANTWORT_UNGUELTIG))
    version, url = auskunft.get("version"), auskunft.get("url")
    groesse, pruefsumme = auskunft.get("groesse"), auskunft.get("sha256")
    if not (isinstance(version, str) and _VERSION_RE.fullmatch(version)):
        raise OnlineFehler(_t(_TEXT_ANTWORT_UNGUELTIG))
    if url != _download_url(version, f"BMS_{version}.zip"):
        raise OnlineFehler(_t(_TEXT_ANTWORT_UNGUELTIG))
    if not (isinstance(groesse, int) and not isinstance(groesse, bool)
            and 1 <= groesse <= PAKET_MAX_BYTES):
        raise OnlineFehler(_t(_TEXT_ANTWORT_UNGUELTIG))
    if not (isinstance(pruefsumme, str) and _SHA256_RE.fullmatch(pruefsumme)):
        raise OnlineFehler(_t(_TEXT_ANTWORT_UNGUELTIG))
    return version, url, groesse, pruefsumme


def online_laden(auskunft: dict, ziel: Path) -> None:
    """Laedt das Paket der Auskunft (`url`) nach `ziel`, ueber eine `.teil`-Datei daneben, die erst
    nach dem Schliessen und nur im Erfolgsfall umbenannt wird. Der Dateiname kommt allein aus dem
    Aufrufer, nie aus einer Kopfzeile der Antwort. Das Laden folgt hoechstens `UMLEITUNGEN_MAX`
    Umleitungen, jede nur zu GitHub (`_ziel_erlaubt`). Gelesen werden hoechstens `groesse` Byte: die
    Funktion stoppt beim ersten Byte darueber und prueft Groesse und SHA-256 VOR dem Umbenennen, ein
    beschaedigtes Paket erscheint nie unter dem Namen BMS_<Version>.zip. Wirft bei JEDEM Fehler
    OnlineFehler; `ziel` ist dann unberuehrt und die `.teil`-Datei geloescht."""
    _version, url, groesse, pruefsumme = _auskunft_fuer_laden(auskunft)
    ziel = Path(ziel)
    teil = ziel.with_name(ziel.name + ".teil")

    try:
        ziel.parent.mkdir(parents=True, exist_ok=True)
        with _online_oeffnen(url, {"User-Agent": "BMS-Update"}, ZEIT_LADEN_S, auskunft=False,
                             umleitungen_max=UMLEITUNGEN_MAX) as antwort:
            angekuendigt = _laenge_lesen(antwort)
            if angekuendigt is not None and angekuendigt != groesse:
                raise OnlineFehler(_t(_TEXT_PAKET_BESCHAEDIGT))

            summe = hashlib.sha256()
            gelesen = 0
            with open(teil, "wb") as datei:
                while True:
                    # Hoechstens EIN Byte ueber der Grenze: so faellt "mehr als angekuendigt"
                    # auf, ohne dass ein endloser Datenstrom je ganz gelesen wuerde.
                    block = _antwort_lesen(antwort, min(_LESEBLOCK, groesse + 1 - gelesen))
                    if not block:
                        break
                    gelesen += len(block)
                    if gelesen > groesse:
                        raise OnlineFehler(_t(_TEXT_PAKET_BESCHAEDIGT))
                    datei.write(block)
                    summe.update(block)

        if gelesen != groesse or summe.hexdigest() != pruefsumme:
            raise OnlineFehler(_t(_TEXT_PAKET_BESCHAEDIGT))
        os.replace(teil, ziel)
    except OSError as exc:
        _teil_loeschen(teil)
        raise OnlineFehler(_t("Das Paket lässt sich nicht in „{ordner}“ speichern ({grund}).",
                              ordner=ziel.parent,
                              grund=exc.strerror or exc.__class__.__name__)) from None
    except BaseException:
        _teil_loeschen(teil)
        raise


def _laenge_lesen(antwort) -> int | None:
    """`Content-Length` der Antwort als Zahl, None wenn die Kopfzeile fehlt. Eine unlesbare Angabe
    ist ein OnlineFehler (Paket nicht vertrauenswuerdig)."""
    roh = antwort.headers.get("Content-Length")
    if roh is None:
        return None
    try:
        laenge = int(roh)
    except ValueError:
        raise OnlineFehler(_t(_TEXT_PAKET_BESCHAEDIGT)) from None
    if laenge < 0:
        raise OnlineFehler(_t(_TEXT_PAKET_BESCHAEDIGT))
    return laenge


def _teil_loeschen(teil: Path) -> None:
    try:
        teil.unlink()
    except OSError:
        pass


def _online_suchen(offline: bool) -> tuple[dict | None, str | None]:
    """Schritt 2, Punkt 4: (Auskunft, Hinweis). Die Auskunft ist None, wenn nicht gefragt wurde
    oder die Suche scheiterte; `hinweis` nennt dann den Grund (dieselbe Zeile, die auch ausgegeben
    wurde) und wird bei einem Abbruch an den Text angehaengt. Hinweis None und Auskunft gesetzt
    heisst: GitHub hat geantwortet. Wirft nie OnlineFehler."""
    if offline:
        return None, _t("Online-Suche übersprungen: Sie haben --offline angegeben.")

    print(_t("Suche auf GitHub nach einer neuen Version. GitHub erhält dabei die IP-Adresse dieses "
             "Rechners."), flush=True)
    try:
        auskunft = online_auskunft()
    except OnlineFehler as exc:
        text = _t("Online-Suche nicht möglich: {grund}", grund=exc.nachricht)
        print(text)
        return None, text
    return auskunft, None


def _datei_passt(pfad: Path, groesse: int, sha256: str) -> bool:
    try:
        if pfad.stat().st_size != groesse:
            return False
        summe = hashlib.sha256()
        with open(pfad, "rb") as datei:
            for block in iter(lambda: datei.read(1024 * 1024), b""):
                summe.update(block)
    except OSError:
        return False
    return summe.hexdigest() == sha256


def _groesse_mb(groesse: int) -> str:
    zahl = f"{max(groesse / 1_000_000, 0.1):.1f}"
    return zahl.replace(".", ",") if _terminal_sprache() == "de" else zahl


def _paket_laden(auskunft: dict, data_dir: Path) -> Path:
    """Schritt 2, Punkt 6: das angebotene Paket nach <data>/updates/pakete/BMS_<Version>.zip.
    Der Dateiname entsteht aus der GEPRUEFTEN Versionsnummer, nie aus einem Namen oder einer
    Kopfzeile der Antwort. Andere BMS_*.zip und *.teil dort werden vorher geloescht (es liegt nie
    mehr als ein Paket da); liegt das Ziel schon mit passender Groesse und Pruefsumme dort (zweiter
    Anlauf), wird nicht neu geladen. Wirft OnlineFehler."""
    version, groesse, pruefsumme = auskunft["version"], auskunft["groesse"], auskunft["sha256"]
    ordner = (data_dir / "updates" / "pakete").absolute()
    ziel = ordner / f"BMS_{version}.zip"
    try:
        ordner.mkdir(parents=True, exist_ok=True)
        for alt in ordner.glob("*.teil"):
            alt.unlink()
        for alt in ordner.glob("BMS_*.zip"):
            if alt.name != ziel.name:
                alt.unlink()
        vorhanden = ziel.is_file() and _datei_passt(ziel, groesse, pruefsumme)
        if ziel.is_file() and not vorhanden:
            ziel.unlink()
    except OSError as exc:
        raise OnlineFehler(_t("Das Paket lässt sich nicht in „{ordner}“ speichern ({grund}).",
                              ordner=ordner,
                              grund=exc.strerror or exc.__class__.__name__)) from None

    if vorhanden:
        print(_t("Version {version} gefunden, das Paket liegt bereits geladen vor.", version=version))
    else:
        print(_t("Version {version} gefunden, lade {groesse} MB …", version=version,
                 groesse=_groesse_mb(groesse)), flush=True)
        online_laden(auskunft, ziel)
    print(_t("Paket geladen und geprüft."))
    return ziel


def _paket_beschaffen(args: argparse.Namespace, data_dir: Path,
                      installierte_version: str | None) -> Path:
    """Schritt 2 (Vertrag U): das Paket, das eingespielt wird. Ein Pfad-Argument gilt und
    bedeutet keinen Netzkontakt. Sonst gewinnt die hoechste Version aus dem neuesten GitHub-Release
    und den Paketen im Download-Ordner, egal woher (mit --erzwingen genuegt dem Angebot eine
    Version gleich der installierten). Jeder Fehler der Online-Suche ist ein Hinweis, kein
    Abbruch: es geht mit dem Paket aus dem Download-Ordner weiter."""
    if args.paket:
        return _paket_finden(args.paket)

    downloads, kandidaten = _downloads_kandidaten()
    bester = kandidaten[-1] if kandidaten else None

    auskunft, hinweis = _online_suchen(args.offline)

    if auskunft is not None:
        angebot = _version_tupel(auskunft["version"])
        installiert = _version_tupel(installierte_version) if installierte_version else None
        ueber_installierter = (installiert is None or angebot > installiert
                               or (args.erzwingen and angebot == installiert))
        ueber_kandidat = bester is None or angebot > bester[0]
        if ueber_installierter and ueber_kandidat:
            try:
                return _paket_laden(auskunft, data_dir)
            except OnlineFehler as exc:
                # Wie bei der Auskunft: kein Abbruch, weiter mit dem Download-Ordner. Bei einem
                # beschaedigten Paket ist der Satz allein die Meldung (Vertrag U).
                hinweis = exc.nachricht
                if hinweis != _t(_TEXT_PAKET_BESCHAEDIGT):
                    hinweis = _t("Laden nicht möglich: {grund}", grund=hinweis)
                print(hinweis)

    if bester is not None:
        return _hoechstes_aus_downloads(kandidaten)

    if auskunft is not None and hinweis is None:
        raise Abbruch(_t("Ihr BMS ist auf dem neuesten Stand (Version {version}).",
                         version=installierte_version or _t("unbekannt")),
                      exit_code=EXIT_OK)
    raise Abbruch(_kein_paket_text(downloads) + (" " + hinweis if hinweis else ""))


# ── Schritt 3: Selbstaktualisierung ─────────────────────────────────────────────────────────
def _selbstaktualisierung_pruefen(paket_pfad: Path, delegiert: bool,
                                   argv_wirksam: list[str]) -> int | None:
    """Weicht scripts/bms_update.py IM PAKET vom laufenden Skript ab, an die neue Fassung
    delegieren -- damit gilt immer die Update-LOGIK der neuen Version. Gibt den Exit-Code des
    delegierten Laufs zurueck, oder None, wenn KEINE Delegation noetig war (dann laeuft der
    Aufrufer normal weiter)."""
    if delegiert:
        return None
    try:
        with zipfile.ZipFile(paket_pfad) as zf:
            neue_fassung = zf.read("scripts/bms_update.py")
    except (zipfile.BadZipFile, KeyError, OSError, FileNotFoundError):
        return None  # Schritt 4 (Paket pruefen) meldet ein kaputtes/unvollstaendiges Paket sauber

    eigene_fassung = Path(__file__).resolve().read_bytes()
    if neue_fassung == eigene_fassung:
        return None

    with tempfile.TemporaryDirectory(prefix="bms_update_selbst_") as tmp:
        temp_skript = Path(tmp) / "bms_update.py"
        temp_skript.write_bytes(neue_fassung)
        # P2-71: Vor der Uebergabe alles ausgeben, was dieser Lauf schon gemeldet hat. Ohne Terminal
        # (Ausgabe in eine Datei oder an ein aufrufendes Programm) puffert Python, "Paket geladen und
        # geprueft." stuende sonst HINTER dem Plan der Fassung im Paket (Befund der Verbundprobe).
        sys.stdout.flush()
        sys.stderr.flush()
        # Die Sprache geht an die Fassung im Paket mit (P2-95), auch wenn sie sie selbst anders erkennte.
        umgebung = dict(os.environ)
        umgebung["BMS_TERMINAL_SPRACHE"] = _terminal_sprache()
        ergebnis = subprocess.run([sys.executable, str(temp_skript), *argv_wirksam, "--delegiert"],
                                  env=umgebung)
    return ergebnis.returncode


# ── Schritt 4: Paket pruefen ─────────────────────────────────────────────────────────────────
def _paket_lesen_und_pruefen(paket_pfad: Path) -> dict:
    try:
        zf = zipfile.ZipFile(paket_pfad)
    except (zipfile.BadZipFile, FileNotFoundError, OSError) as exc:
        raise Abbruch(_t("Die Paketdatei „{pfad}“ lässt sich nicht lesen: {fehler}",
                         pfad=paket_pfad, fehler=exc)) from exc

    with zf:
        kaputt = zf.testzip()
        if kaputt is not None:
            raise Abbruch(_t("Die Paketdatei ist beschädigt (fehlerhafter Eintrag: {eintrag}).",
                             eintrag=kaputt))

        try:
            manifest = json.loads(zf.read(MANIFEST_NAME))
        except KeyError as exc:
            raise Abbruch(_t("Die Paketdatei enthält kein bms_manifest.json.")) from exc
        except json.JSONDecodeError as exc:
            raise Abbruch(_t("bms_manifest.json im Paket ist beschädigt: {fehler}", fehler=exc)) from exc

        if manifest.get("format") != 1:
            raise Abbruch(_t("Dieses Paket hat ein unbekanntes Format ({format!r}). "
                             "Bitte eine neuere Fassung des Update-Werkzeugs verwenden.",
                             format=manifest.get("format")))

        dateien = manifest.get("dateien", {})
        namen = {n for n in zf.namelist() if not n.endswith("/")}
        erwartete_namen = set(dateien) | {MANIFEST_NAME}

        # Pfade ZUERST pruefen, dann erst gegen die ZIP-Eintraege abgleichen: unter Windows
        # schreibt zipfile einen Backslash im Eintragsnamen beim Packen zu "/" um, ein Manifest-
        # Pfad "a\\b.txt" fiele sonst nur als "fehlender Eintrag" auf (CI-Fund 28.09.2026).
        for pfad in sorted(set(dateien) | namen):
            if _pfad_unsicher(pfad):
                raise Abbruch(_t("Die Paketdatei enthält einen unsicheren Pfad: {pfad}", pfad=pfad))
            if _pfad_geschuetzt(pfad) and pfad != MANIFEST_NAME:
                raise Abbruch(_t("Die Paketdatei enthält einen geschützten Pfad: {pfad}", pfad=pfad))
        if MANIFEST_NAME in dateien:
            raise Abbruch(_t("Die Paketdatei enthält einen geschützten Pfad: {pfad}", pfad=MANIFEST_NAME))

        fehlend = erwartete_namen - namen
        if fehlend:
            raise Abbruch(_t("Der Paketdatei fehlen Einträge: {liste}", liste=", ".join(sorted(fehlend))))
        unerwartet = namen - erwartete_namen
        if unerwartet:
            raise Abbruch(_t("Die Paketdatei enthält unerwartete Einträge: {liste}",
                             liste=", ".join(sorted(unerwartet))))

        for pfad, info in dateien.items():
            inhalt = zf.read(pfad)
            if len(inhalt) != info.get("groesse"):
                raise Abbruch(_t("„{pfad}“ hat im Paket eine andere Größe als im Manifest angegeben.",
                                 pfad=pfad))
            if _sha256(inhalt) != info.get("sha256"):
                raise Abbruch(_t("„{pfad}“ stimmt nicht mit der Prüfsumme im Manifest überein "
                                 "(Paket möglicherweise beschädigt oder unvollständig).", pfad=pfad))

    return manifest


def _installierte_version(installation: Path) -> tuple[dict | None, str | None]:
    """(altes Manifest oder None, installierte Version oder None). Quelle: bms_manifest.json,
    sonst VERSION, sonst unbekannt (Bau-Spec V5)."""
    manifest_pfad = installation / MANIFEST_NAME
    if manifest_pfad.is_file():
        try:
            daten = json.loads(manifest_pfad.read_text(encoding="utf-8"))
            return daten, daten.get("version")
        except (json.JSONDecodeError, OSError):
            pass
    version_pfad = installation / "VERSION"
    if version_pfad.is_file():
        try:
            return None, version_pfad.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return None, None


def _paket_gegen_installation_pruefen(manifest: dict, installierte_version: str | None,
                                       erzwingen: bool) -> None:
    if manifest.get("vorschau") and not erzwingen:
        raise Abbruch(_t("Dieses Paket ist eine Vorschau (kein freigegebener Stand) und wird ohne "
                         "--erzwingen nicht eingespielt."))

    neu_tupel = _version_tupel(str(manifest.get("version", "")))
    alt_tupel = _version_tupel(installierte_version) if installierte_version else None
    if neu_tupel is not None and alt_tupel is not None and neu_tupel <= alt_tupel and not erzwingen:
        raise Abbruch(_t("Die Paketversion ({neu}) ist nicht neuer als die "
                         "installierte Version ({alt}). Mit --erzwingen dennoch "
                         "einspielen.", neu=manifest.get("version"), alt=installierte_version))


# ── Schritt 6: Plan erstellen ────────────────────────────────────────────────────────────────
def _datei_entscheiden(installation: Path, pfad: str, alt_info: dict | None, neu_info: dict | None,
                        anpassbar_muster: tuple[str, ...], kein_alt: bool,
                        zf: zipfile.ZipFile) -> DateiAktion:
    anpassbar = any(fnmatch.fnmatch(pfad, m) for m in anpassbar_muster)
    lokal_pfad = installation / pfad
    lokal_vorhanden = lokal_pfad.is_file()
    lokal_hash = _sha256(lokal_pfad.read_bytes()) if lokal_vorhanden else None
    alt_hash = alt_info["sha256"] if alt_info else None
    neu_hash = neu_info["sha256"] if neu_info else None
    ausfuehrbar_neu = bool(neu_info.get("ausfuehrbar")) if neu_info else False

    def neuer_inhalt() -> bytes:
        return zf.read(pfad)

    # Zeile 8 der Dateiregeln-Tabelle: am Ziel steht schon der neue Inhalt -- Vorrang vor allem
    # Weiteren (verhindert unnoetige "geaendert"-Meldungen/Sicherungen fuer echte No-ops).
    if lokal_vorhanden and neu_info is not None and lokal_hash == neu_hash:
        return DateiAktion(pfad, "nichts", anpassbar)

    # Zeile 4: im neuen Paket nicht mehr enthalten.
    if not kein_alt and neu_info is None:
        if not anpassbar:
            return DateiAktion(pfad, "entfernen", anpassbar, bucket="entfernt")
        if lokal_vorhanden and alt_hash is not None and lokal_hash == alt_hash:
            return DateiAktion(pfad, "entfernen", anpassbar, bucket="entfernt")
        return DateiAktion(pfad, "behalten", anpassbar,
                            bucket="anpassbar_behalten" if lokal_vorhanden else None)

    # Zeile "kein altes Manifest" -- neu_info ist hier IMMER gesetzt, s. _plan_erstellen: die
    # betrachtete Pfadmenge ist dann exakt die des neuen Manifests.
    if kein_alt:
        if not anpassbar:
            # bucket "neu", wenn lokal nichts existierte (Nachbesserung Abnahme P2-51): ohne
            # lokale Datei sichert _dateien_schreiben() NICHTS unter dateien/<pfad> -- ein
            # spaeteres --zurueck muss diesen Pfad dann per bericht["neu"] LOESCHEN koennen,
            # statt vergeblich eine nie existierende Sicherung wiederherzustellen zu versuchen.
            bucket = "geaendert" if lokal_vorhanden else "neu"
            return DateiAktion(pfad, "schreiben", anpassbar, bucket=bucket,
                                melde_lokal_geaendert=lokal_vorhanden,
                                inhalt=neuer_inhalt(), ausfuehrbar=ausfuehrbar_neu)
        if lokal_vorhanden:
            return DateiAktion(pfad, "behalten", anpassbar, bucket="anpassbar_behalten",
                                neue_fassung_ablegen=True, inhalt=neuer_inhalt())
        return DateiAktion(pfad, "schreiben", anpassbar, bucket="neu",
                            inhalt=neuer_inhalt(), ausfuehrbar=ausfuehrbar_neu)

    # Zeilen 5/6: neu im Paket, nicht im alten Manifest.
    if alt_info is None:
        if not lokal_vorhanden:
            return DateiAktion(pfad, "schreiben", anpassbar, bucket="neu",
                                inhalt=neuer_inhalt(), ausfuehrbar=ausfuehrbar_neu)
        if not anpassbar:
            return DateiAktion(pfad, "schreiben", anpassbar, bucket="neu", melde_lokal_geaendert=True,
                                inhalt=neuer_inhalt(), ausfuehrbar=ausfuehrbar_neu)
        return DateiAktion(pfad, "behalten", anpassbar, bucket="anpassbar_behalten",
                            neue_fassung_ablegen=True, inhalt=neuer_inhalt())

    # Zeilen 1/2/3: Pfad in altem UND neuem Manifest bekannt.
    if lokal_vorhanden and lokal_hash == alt_hash:
        bucket = "geaendert" if alt_hash != neu_hash else None
        return DateiAktion(pfad, "schreiben", anpassbar, bucket=bucket,
                            inhalt=neuer_inhalt(), ausfuehrbar=ausfuehrbar_neu)
    if not lokal_vorhanden:
        if not anpassbar:
            # bucket "neu" (nicht "geaendert", Nachbesserung Abnahme P2-51): "wiederherstellen"
            # ohne lokale Vorlage hinterlaesst KEINE Sicherung unter dateien/<pfad> -- --zurueck
            # muss den Pfad ueber bericht["neu"] wieder loeschen koennen (der Kunde hatte ihn vor
            # diesem Update ja bewusst entfernt), sonst bliebe er nach --zurueck faelschlich stehen.
            return DateiAktion(pfad, "schreiben", anpassbar, bucket="neu",
                                inhalt=neuer_inhalt(), ausfuehrbar=ausfuehrbar_neu)
        return DateiAktion(
            pfad, "nichts", anpassbar,
            hinweis=_t("„{pfad}“ wurde von Ihnen entfernt und bleibt entfernt (angepasste Datei).",
                       pfad=pfad))
    if not anpassbar:
        return DateiAktion(pfad, "schreiben", anpassbar, bucket="geaendert", melde_lokal_geaendert=True,
                            inhalt=neuer_inhalt(), ausfuehrbar=ausfuehrbar_neu)
    # anpassbar, lokal vom Original abgewichen: Kundenfassung bleibt. Eine neue_fassungen/-Ablage
    # lohnt nur, wenn sich die PRODUKT-Version wirklich geaendert hat (alt != neu) -- hat sich nur
    # die lokale Kopie vom unveraenderten Original entfernt, gibt es nichts Neues zum Nachschlagen
    # (optionale Nachbesserung Abnahme P2-51).
    if alt_hash != neu_hash:
        return DateiAktion(pfad, "behalten", anpassbar, bucket="anpassbar_behalten",
                            neue_fassung_ablegen=True, inhalt=neuer_inhalt())
    return DateiAktion(pfad, "behalten", anpassbar, bucket="anpassbar_behalten")


def _plan_erstellen(installation: Path, altes_manifest: dict | None, neues_manifest: dict,
                     paket_pfad: Path, installierte_version: str | None) -> Plan:
    # Kopie, KEINE Referenz auf altes_manifest["dateien"]: unten wird daraus geloescht, das darf
    # die spaeter gesicherte "bms_manifest.alt.json" (_sicherung_erstellen nutzt altes_manifest
    # unveraendert) nicht mit beeinflussen.
    alte_dateien: dict = dict((altes_manifest or {}).get("dateien", {}))
    neue_dateien: dict = neues_manifest.get("dateien", {})
    anpassbar_muster = tuple(neues_manifest.get("anpassbar", ()))
    kein_alt = altes_manifest is None

    # Verteidigung in der Tiefe (Nachbesserung Abnahme P2-51): das ALTE Manifest liegt beim
    # Kunden auf der Platte -- von Hand veraendert, korrumpiert oder aus einer aelteren
    # Werkzeug-Fassung ohne diese Pruefungen. Ein unsicherer oder geschuetzter Pfad darin wird
    # GENAUSO verworfen wie einer aus dem (in Schritt 4 frisch geprueften) neuen Paket: fuer die
    # Planung, als haette der alte Eintrag nie existiert. Kommt derselbe Pfad im NEUEN Manifest
    # gueltig vor, wird er ganz normal als "neu im Paket" behandelt (Zeilen 5/6) -- sonst taucht
    # er im Plan ueberhaupt nicht mehr auf und bleibt unangetastet.
    verworfene_alte_pfade = sorted(p for p in alte_dateien if _pfad_unsicher(p) or _pfad_geschuetzt(p))
    for pfad in verworfene_alte_pfade:
        del alte_dateien[pfad]
    hinweise = [_t("„{pfad}“ stand im installierten Manifest, ist aber ein unsicherer oder "
                   "geschützter Pfad und wurde übersprungen.", pfad=p) for p in verworfene_alte_pfade]

    alle_pfade = sorted(set(alte_dateien) | set(neue_dateien))
    aktionen: list[DateiAktion] = []
    with zipfile.ZipFile(paket_pfad) as zf:
        for pfad in alle_pfade:
            aktionen.append(_datei_entscheiden(installation, pfad, alte_dateien.get(pfad),
                                                neue_dateien.get(pfad), anpassbar_muster, kein_alt, zf))

    def _hash(dateien: dict, pfad: str) -> str | None:
        info = dateien.get(pfad)
        return info["sha256"] if info else None

    pip_noetig = (kein_alt or _hash(alte_dateien, "backend/requirements-lock.txt")
                  != _hash(neue_dateien, "backend/requirements-lock.txt"))

    node_modules_fehlt = not (installation / "frontend" / "node_modules").is_dir()
    npm_ci_noetig = (kein_alt or node_modules_fehlt
                     or _hash(alte_dateien, "frontend/package-lock.json")
                     != _hash(neue_dateien, "frontend/package-lock.json"))

    frontend_geaendert = any(a.pfad.startswith("frontend/") and a.art in ("schreiben", "entfernen")
                              for a in aktionen)
    dist_fehlt = not (installation / "frontend" / "dist").is_dir()
    build_noetig = frontend_geaendert or dist_fehlt
    npm_fehlt = build_noetig and _npm_pfad() is None

    return Plan(installierte_version=installierte_version, neue_version=str(neues_manifest.get("version", "?")),
                aktionen=aktionen, pip_noetig=pip_noetig, npm_ci_noetig=npm_ci_noetig,
                build_noetig=build_noetig, npm_fehlt=npm_fehlt, kein_altes_manifest=kein_alt,
                hinweise=hinweise)


def _plan_text(plan: Plan) -> str:
    neu = [a for a in plan.aktionen if a.bucket == "neu"]
    geaendert = [a for a in plan.aktionen if a.bucket == "geaendert"]
    entfernt = [a for a in plan.aktionen if a.bucket == "entfernt"]
    lokal_geaendert = [a for a in plan.aktionen if a.melde_lokal_geaendert]
    angepasst = [a for a in plan.aktionen if a.bucket == "anpassbar_behalten"]

    zeilen = [
        _t("Installierte Version: {version}", version=plan.installierte_version or _t("unbekannt")),
        _t("Neue Version: {version}", version=plan.neue_version),
        _t("Dateien: {neu} neu, {geaendert} geändert, {entfernt} entfernt.",
           neu=len(neu), geaendert=len(geaendert), entfernt=len(entfernt)),
    ]
    if lokal_geaendert:
        zeilen.append(_t("Von Ihnen geänderte Programmdateien werden gesichert und ersetzt: {dateien}",
                         dateien=", ".join(a.pfad for a in lokal_geaendert)))
    if angepasst:
        zeilen.append(_t("Angepasste Dateien bleiben erhalten: {dateien}",
                         dateien=", ".join(a.pfad for a in angepasst)))

    abhaengigkeiten = []
    if plan.pip_noetig:
        abhaengigkeiten.append(_t("Python-Pakete"))
    if plan.npm_ci_noetig:
        abhaengigkeiten.append(_t("Oberflächen-Bausteine (npm ci)"))
    if plan.build_noetig:
        abhaengigkeiten.append(_t("Oberfläche neu bauen"))
    zeilen.append(_t("Abhängigkeiten: {liste}",
                     liste=", ".join(abhaengigkeiten) if abhaengigkeiten else _t("keine")))
    zeilen.extend(plan.hinweise)
    return "\n".join(zeilen)


# ── Schritt 7: Rueckfrage ────────────────────────────────────────────────────────────────────
def _rueckfrage(frage: str) -> bool:
    print(frage, end="")
    try:
        antwort = input()
    except EOFError:
        return False
    return antwort.strip().lower() in _RUECKFRAGE_JA


# ── Schritt 8: Sperre ─────────────────────────────────────────────────────────────────────────
def _sperren(data_dir: Path) -> Path:
    ordner = data_dir / "updates"
    ordner.mkdir(parents=True, exist_ok=True)
    lock = ordner / SPERR_NAME
    try:
        os.close(os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError as exc:
        raise Abbruch(_t("Es läuft bereits ein Update, oder ein vorheriges wurde nicht sauber "
                         "beendet. Wenn Sie sicher sind, dass kein Update läuft, löschen Sie "
                         "„{lock}“ und versuchen Sie es erneut.", lock=lock)) from exc
    return lock


def _entsperren(lock: Path) -> None:
    try:
        lock.unlink()
    except FileNotFoundError:
        pass


def _sicherung_ordner_anlegen(data_dir: Path, von: str | None, nach: str) -> Path:
    stempel = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    basis = data_dir / "updates" / f"{stempel}_{von or 'unbekannt'}_zu_{nach}"
    kandidat, zaehler = basis, 2
    while True:
        try:
            kandidat.mkdir(parents=True, exist_ok=False)
            return kandidat
        except FileExistsError:
            kandidat = Path(f"{basis}_{zaehler}")
            zaehler += 1


# ── Schritt 9: Sicherung ─────────────────────────────────────────────────────────────────────
def _sicherung_erstellen(installation: Path, data_dir: Path, sicherung_dir: Path,
                          altes_manifest: dict | None, plan: Plan) -> None:
    db_pfad = data_dir / "bewerbung.sqlite"
    if db_pfad.is_file():
        quelle_uri = db_pfad.resolve().as_uri() + "?mode=ro"
        quelle_conn = sqlite3.connect(quelle_uri, uri=True)
        try:
            ziel_conn = sqlite3.connect(str(sicherung_dir / "datenbank.sqlite"))
            try:
                quelle_conn.backup(ziel_conn)
            finally:
                ziel_conn.close()
        finally:
            quelle_conn.close()

    if altes_manifest is not None:
        (sicherung_dir / "bms_manifest.alt.json").write_text(
            json.dumps(altes_manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
            encoding="utf-8")

    if plan.build_noetig:
        alter_dist = installation / "frontend" / "dist"
        if alter_dist.is_dir():
            shutil.copytree(alter_dist, sicherung_dir / "frontend_dist_alt")


def _sichern(sicherung_dir: Path, pfad: str, quelle: Path) -> None:
    ziel = sicherung_dir / "dateien" / pfad
    ziel.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(quelle, ziel)


# ── Schritt 10: Dateien schreiben ───────────────────────────────────────────────────────────
def _atomar_schreiben(ziel: Path, inhalt: bytes, ausfuehrbar: bool) -> None:
    ziel.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(dir=str(ziel.parent), prefix=".bms_update_tmp_")
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(inhalt)
        if os.name != "nt":   # NTFS kennt keine POSIX-Ausfuehrbar-Bits (Bau-Spec: unter Windows wirkungslos)
            os.chmod(tmp_name, 0o755 if ausfuehrbar else 0o644)
        os.replace(tmp_name, ziel)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _leere_ordner_entfernen(installation: Path, entfernte_dateien: list[Path]) -> None:
    ordner = {p.parent for p in entfernte_dateien}
    for start in sorted(ordner, key=lambda p: len(p.parts), reverse=True):
        aktuell = start
        while aktuell != installation and installation in aktuell.parents:
            try:
                aktuell.rmdir()
            except OSError:
                break
            aktuell = aktuell.parent


def _dateien_schreiben(installation: Path, sicherung_dir: Path, aktionen: list[DateiAktion],
                        angefasst: list[tuple[str, bool]]) -> None:
    """Schreibt/entfernt Dateien nach dem Plan. `angefasst` ist eine vom AUFRUFER erzeugte,
    LEERE Liste (kein Rueckgabewert!) -- diese Funktion haengt fuer jeden Pfad, den sie WIRKLICH
    anfasst, ein (pfad, gab_es_vorher_lokal)-Paar an, und zwar NACHDEM die Sicherung dieser
    einen Datei geschrieben ist und BEVOR die Datei selbst geschrieben/entfernt wird.

    KRITISCH (Nachbesserung Abnahme P2-51, vorher ein Datenverlust-Bug): scheitert ein
    Schreibvorgang MITTEN in der Schleife (PermissionError unter Windows bei gesperrter Datei,
    volle Platte), wirft diese Funktion und bricht ab -- weil `angefasst` aber dieselbe Liste
    ist, die der Aufrufer haelt (kein Return, keine Kopie), bleibt sie bei ihm bis genau zu dem
    Punkt gefuellt, an dem der Fehler auftrat. `_rollback_dateien()` verarbeitet NUR diese Liste:
    Aktionen, die diese Schleife nie erreicht hat, bleiben vollstaendig unangetastet. Der fruehere
    Code liess `_rollback_dateien()` stattdessen ALLE Plan-Aktionen durchgehen und nahm bei jeder
    ohne Sicherung an, sie sei "neu angelegt und daher zu loeschen" -- das traf auch auf Dateien
    zu, die schreiben() nie erreicht hatte und die deshalb noch ihren VOLLSTAENDIG UNVERAENDERTEN
    Originalinhalt trugen: der Rollback haette sie geloescht."""
    entfernte: list[Path] = []
    for a in aktionen:
        ziel = installation / a.pfad
        if a.art == "schreiben":
            vorher_vorhanden = ziel.is_file()
            if vorher_vorhanden:
                _sichern(sicherung_dir, a.pfad, ziel)
            angefasst.append((a.pfad, vorher_vorhanden))
            _atomar_schreiben(ziel, a.inhalt or b"", a.ausfuehrbar)
        elif a.art == "entfernen":
            if ziel.is_file():
                _sichern(sicherung_dir, a.pfad, ziel)
                angefasst.append((a.pfad, True))
                ziel.unlink()
                entfernte.append(ziel)
        elif a.art == "behalten" and a.neue_fassung_ablegen and a.inhalt is not None:
            neue_fassung_ziel = sicherung_dir / "neue_fassungen" / a.pfad
            neue_fassung_ziel.parent.mkdir(parents=True, exist_ok=True)
            neue_fassung_ziel.write_bytes(a.inhalt)
    _leere_ordner_entfernen(installation, entfernte)


def _manifest_uebernehmen(installation: Path, paket_pfad: Path) -> None:
    with zipfile.ZipFile(paket_pfad) as zf:
        inhalt = zf.read(MANIFEST_NAME)
    _atomar_schreiben(installation / MANIFEST_NAME, inhalt, ausfuehrbar=False)


# ── Schritt 11: Abhaengigkeiten ──────────────────────────────────────────────────────────────
def _subprocess_pruefen(befehl: list[str], *, cwd: Path, fehlermeldung: str) -> None:
    try:
        ergebnis = subprocess.run(befehl, cwd=str(cwd), capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Fehlgeschlagen(f"{fehlermeldung} ({exc})") from exc
    if ergebnis.returncode != 0:
        ausgabe = (ergebnis.stderr or ergebnis.stdout or "").strip()
        raise Fehlgeschlagen(f"{fehlermeldung}\n{ausgabe[-2000:]}")


def _abhaengigkeiten_installieren(installation: Path, plan: Plan) -> None:
    if plan.pip_noetig:
        _subprocess_pruefen(
            [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
             "-r", "backend/requirements-lock.txt"],
            cwd=installation, fehlermeldung=_t("Installation der Python-Pakete fehlgeschlagen."))

    npm = _npm_pfad()
    if plan.npm_ci_noetig:
        if npm is None:
            raise Fehlgeschlagen(_t("npm wurde nicht gefunden."))
        _subprocess_pruefen([npm, "ci"], cwd=installation / "frontend",
                             fehlermeldung=_t("Installation der Oberflächen-Bausteine fehlgeschlagen."))

    if plan.build_noetig:
        if npm is None:
            raise Fehlgeschlagen(_t("npm wurde nicht gefunden."))
        _subprocess_pruefen([npm, "run", "build", "--", "--outDir", "dist_neu", "--emptyOutDir"],
                             cwd=installation / "frontend", fehlermeldung=_t("Bauen der Oberfläche fehlgeschlagen."))
        dist = installation / "frontend" / "dist"
        dist_neu = installation / "frontend" / "dist_neu"
        if dist.is_dir():
            shutil.rmtree(dist)
        os.replace(dist_neu, dist)


# ── Schritt 12: Selbsttest ───────────────────────────────────────────────────────────────────
def _selbsttest_ausfuehren(installation: Path, data_dir: Path) -> None:
    modul_pfad = installation / "backend" / "app" / "selbsttest.py"
    if not modul_pfad.is_file():
        print(_t("Hinweis: Selbsttest übersprungen (backend/app/selbsttest.py ist in diesem Paket "
                 "nicht enthalten)."))
        return

    db_quelle = data_dir / "bewerbung.sqlite"
    with tempfile.TemporaryDirectory(prefix="bms_update_selbsttest_") as tmp:
        tmp_pfad = Path(tmp)
        tmp_data, tmp_log, tmp_secrets = tmp_pfad / "data", tmp_pfad / "logs", tmp_pfad / "secrets"
        tmp_data.mkdir()
        tmp_log.mkdir()
        tmp_secrets.mkdir()
        if db_quelle.is_file():
            shutil.copy2(db_quelle, tmp_data / "bewerbung.sqlite")

        umgebung = dict(os.environ)
        umgebung["BMS_DATA_DIR"] = str(tmp_data)
        umgebung["BMS_LOG_DIR"] = str(tmp_log)
        umgebung["BMS_SECRETS_DIR"] = str(tmp_secrets)
        umgebung["BMS_TERMINAL_SPRACHE"] = _terminal_sprache()

        try:
            ergebnis = subprocess.run([sys.executable, "-m", "app.selbsttest"],
                                       cwd=str(installation / "backend"), env=umgebung,
                                       capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired as exc:
            raise Fehlgeschlagen(_t("Selbsttest hat das Zeitlimit überschritten.")) from exc

    if ergebnis.returncode != 0:
        raise Fehlgeschlagen(_t("Selbsttest fehlgeschlagen:\n{ausgabe}",
                                ausgabe=(ergebnis.stdout + ergebnis.stderr).strip()))


# ── Zurueckrollen (Fehler ab Schritt 10) ────────────────────────────────────────────────────
def _rollback_dateien(installation: Path, sicherung_dir: Path,
                       angefasst: list[tuple[str, bool]]) -> None:
    """Macht NUR die in `angefasst` verzeichneten Pfade rueckgaengig (s. _dateien_schreiben) --
    rueckwaerts in der Reihenfolge, in der sie angefasst wurden. Ein Pfad, den schreiben() nie
    erreicht hat, taucht hier gar nicht auf und bleibt unberuehrt (KEIN Blick mehr auf die volle
    Plan-Aktionsliste -- genau das war der Datenverlust-Bug)."""
    betroffen: list[Path] = []
    for pfad, gab_es_vorher in reversed(angefasst):
        ziel = installation / pfad
        if gab_es_vorher:
            sicherung = sicherung_dir / "dateien" / pfad
            if sicherung.is_file():
                ziel.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sicherung, ziel)
        elif ziel.is_file():
            ziel.unlink()
            betroffen.append(ziel)
    _leere_ordner_entfernen(installation, betroffen)


def _rollback_dist(installation: Path, sicherung_dir: Path) -> None:
    alter_dist = sicherung_dir / "frontend_dist_alt"
    if not alter_dist.is_dir():
        return
    neuer_dist = installation / "frontend" / "dist"
    if neuer_dist.is_dir():
        shutil.rmtree(neuer_dist)
    shutil.copytree(alter_dist, neuer_dist)


# ── Bericht (V4) ─────────────────────────────────────────────────────────────────────────────
def _bericht_schreiben(sicherung_dir: Path, *, von: str | None, nach: str, ergebnis: str,
                        aktionen: list[DateiAktion], zusatz_hinweise: list[str] = (),
                        zurueckgenommen_am: str | None = None) -> dict:
    bericht = {
        "format": 1,
        "zeitpunkt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "von": von,
        "nach": nach,
        "ergebnis": ergebnis,
        "zurueckgenommen_am": zurueckgenommen_am,
        "neu": sorted(a.pfad for a in aktionen if a.bucket == "neu"),
        "geaendert": sorted(a.pfad for a in aktionen if a.bucket == "geaendert"),
        "entfernt": sorted(a.pfad for a in aktionen if a.bucket == "entfernt"),
        "lokal_geaendert_gesichert": sorted(a.pfad for a in aktionen if a.melde_lokal_geaendert),
        "anpassbar_behalten": sorted(a.pfad for a in aktionen if a.bucket == "anpassbar_behalten"),
        "hinweise": list(zusatz_hinweise) + [a.hinweis for a in aktionen if a.hinweis],
    }
    (sicherung_dir / "bericht.json").write_text(
        json.dumps(bericht, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return bericht


# ── Update-Ablauf (Schritte 1-13) ────────────────────────────────────────────────────────────
def _update_ausfuehren(args: argparse.Namespace, argv_wirksam: list[str]) -> int:
    installation = Path(args.installation).resolve()
    _installation_pruefen(installation)

    # P2-71/P2-82: Die installierte Version wird VOR Schritt 2 gelesen (sie liest nur), weil der
    # Vergleich mit dem neuesten GitHub-Release sie braucht.
    altes_manifest, installierte_version = _installierte_version(installation)
    data_dir = _data_dir(installation)

    paket_pfad = _paket_beschaffen(args, data_dir, installierte_version)

    # Delegiert das Werkzeug an die Fassung im Paket, bekommt diese den Pfad des Pakets
    # AUSDRUECKLICH als Argument (P2-71): sonst suchte und lud sie ein zweites Mal, und eine aeltere
    # Fassung im Paket kennt die Online-Suche gar nicht und faende ein geladenes Paket nicht.
    argv_delegation = argv_wirksam if args.paket else [*argv_wirksam, str(paket_pfad)]
    exit_code = _selbstaktualisierung_pruefen(paket_pfad, args.delegiert, argv_delegation)
    if exit_code is not None:
        return exit_code

    neues_manifest = _paket_lesen_und_pruefen(paket_pfad)
    _paket_gegen_installation_pruefen(neues_manifest, installierte_version, args.erzwingen)

    if _server_laeuft():
        raise Abbruch(_t("Das BMS läuft noch. Beenden Sie es zuerst mit stop.command bzw. stop_windows.bat."))

    plan = _plan_erstellen(installation, altes_manifest, neues_manifest, paket_pfad, installierte_version)
    print(_plan_text(plan))

    # --ohne-abhaengigkeiten ueberspringt Schritt 11 komplett (s. unten) -- dann waere ein
    # Abbruch wegen fehlendem npm nur fuer eine Installation da, die gar nicht versucht wird.
    if plan.npm_fehlt and not args.ohne_abhaengigkeiten:
        raise Abbruch(_t("Für dieses Update muss die Oberfläche neu gebaut werden, npm wurde aber "
                         "nicht gefunden. Bitte Node.js installieren und erneut versuchen."))

    if args.pruefen:
        return EXIT_OK

    if not args.ja:
        frage = _t("Update von {alt} auf {neu} jetzt einspielen? [j/N] ",
                   alt=installierte_version or _t("unbekannt"), neu=plan.neue_version)
        if not _rueckfrage(frage):
            raise Abbruch(_t("Abgebrochen. Es wurde nichts verändert."))

    lock_pfad = _sperren(data_dir)
    try:
        sicherung_dir = _sicherung_ordner_anlegen(data_dir, installierte_version, plan.neue_version)
        try:
            _sicherung_erstellen(installation, data_dir, sicherung_dir, altes_manifest, plan)
        except Exception as exc:
            raise Abbruch(_t("Sicherung fehlgeschlagen, es wurde nichts verändert: {fehler}",
                             fehler=exc)) from exc

        # Vom AUFRUFER angelegt, NICHT von _dateien_schreiben() zurueckgegeben: bricht die
        # Funktion mitten in der Schleife ab (Exception statt return), bleibt diese Liste hier
        # trotzdem bis zu dem Punkt gefuellt, an dem es geschah -- dieselbe Listen-Identitaet,
        # kein verlorener Rueckgabewert (s. _dateien_schreiben-Docstring).
        angefasst: list[tuple[str, bool]] = []
        try:
            _dateien_schreiben(installation, sicherung_dir, plan.aktionen, angefasst)
            if not args.ohne_abhaengigkeiten:
                _abhaengigkeiten_installieren(installation, plan)
            if not args.ohne_selbsttest:
                _selbsttest_ausfuehren(installation, data_dir)
            _manifest_uebernehmen(installation, paket_pfad)
        except Exception as exc:
            _rollback_dateien(installation, sicherung_dir, angefasst)
            if plan.build_noetig:
                _rollback_dist(installation, sicherung_dir)
            _bericht_schreiben(sicherung_dir, von=installierte_version, nach=plan.neue_version,
                                ergebnis="zurueckgerollt", aktionen=plan.aktionen,
                                zusatz_hinweise=plan.hinweise)
            raise Abbruch(
                _t("Update fehlgeschlagen, alle Änderungen wurden zurückgerollt: {fehler}\n"
                   "Sicherung liegt unter: {ordner}\n"
                   "Hinweis: Python- oder Oberflächen-Bausteine können bereits auf dem neuen Stand sein.",
                   fehler=exc, ordner=sicherung_dir),
                exit_code=EXIT_ZURUECKGEROLLT,
            ) from exc

        _bericht_schreiben(sicherung_dir, von=installierte_version, nach=plan.neue_version,
                            ergebnis="ok", aktionen=plan.aktionen, zusatz_hinweise=plan.hinweise)
        print(_t("Update auf Version {version} abgeschlossen. Starten Sie das BMS wie gewohnt.",
                 version=plan.neue_version))
        return EXIT_OK
    finally:
        _entsperren(lock_pfad)


# ── --zurueck ─────────────────────────────────────────────────────────────────────────────────
def _letztes_erfolgreiches_update_finden(data_dir: Path) -> tuple[Path | None, dict | None]:
    updates_dir = data_dir / "updates"
    if not updates_dir.is_dir():
        return None, None
    kandidaten = []
    for ordner in updates_dir.iterdir():
        bericht_pfad = ordner / "bericht.json"
        if not bericht_pfad.is_file():
            continue
        try:
            bericht = json.loads(bericht_pfad.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if bericht.get("ergebnis") == "ok" and not bericht.get("zurueckgenommen_am"):
            kandidaten.append((bericht.get("zeitpunkt", ""), ordner, bericht))
    if not kandidaten:
        return None, None
    kandidaten.sort(key=lambda t: t[0])
    _, ordner, bericht = kandidaten[-1]
    return ordner, bericht


def _zurueck_ausfuehren(args: argparse.Namespace) -> int:
    installation = Path(args.installation).resolve()
    _installation_pruefen(installation)
    data_dir = _data_dir(installation)

    sicherung_dir, bericht = _letztes_erfolgreiches_update_finden(data_dir)
    if sicherung_dir is None or bericht is None:
        raise Abbruch(_t("Es gibt kein Update, das rückgängig gemacht werden kann."))

    if _server_laeuft():
        raise Abbruch(_t("Das BMS läuft noch. Beenden Sie es zuerst mit stop.command bzw. stop_windows.bat."))

    lock_pfad = _sperren(data_dir)
    try:
        entfernte: list[Path] = []
        for pfad in bericht.get("neu", []):
            ziel = installation / pfad
            if ziel.is_file():
                ziel.unlink()
                entfernte.append(ziel)

        dateien_sicherung = sicherung_dir / "dateien"
        if dateien_sicherung.is_dir():
            for quelle in dateien_sicherung.rglob("*"):
                if quelle.is_file():
                    rel = quelle.relative_to(dateien_sicherung)
                    ziel = installation / rel
                    ziel.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(quelle, ziel)
        _leere_ordner_entfernen(installation, entfernte)

        _rollback_dist(installation, sicherung_dir)

        altes_manifest_pfad = sicherung_dir / "bms_manifest.alt.json"
        ziel_manifest = installation / MANIFEST_NAME
        if altes_manifest_pfad.is_file():
            shutil.copy2(altes_manifest_pfad, ziel_manifest)
        elif ziel_manifest.is_file():
            ziel_manifest.unlink()

        if not args.ohne_abhaengigkeiten:
            _subprocess_pruefen(
                [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                 "-r", "backend/requirements-lock.txt"],
                cwd=installation, fehlermeldung=_t("Installation der Python-Pakete fehlgeschlagen."))

        db_zurueckgesetzt = False
        # "--ja" beantwortet diese Frage BEWUSST NICHT: es bestaetigt nur "Update/Ruecknahme
        # jetzt ausfuehren", nicht "Datenbank-Aenderungen seit dem Update wegwerfen" -- zwei
        # verschiedene Risikostufen (Nachbesserung Abnahme P2-51). Nur der eigene Schalter
        # --mit-datenbank darf diese eine Frage nicht-interaktiv bejahen.
        frage = _t("Datenbank auf den Stand vor dem Update zurücksetzen? Alle Änderungen seit dem "
                   "Update gehen verloren. [j/N] ")
        if args.mit_datenbank or _rueckfrage(frage):
            db_sicherung = sicherung_dir / "datenbank.sqlite"
            if db_sicherung.is_file():
                aktuelle_db = data_dir / "bewerbung.sqlite"
                if aktuelle_db.is_file():
                    shutil.copy2(aktuelle_db, sicherung_dir / "datenbank_vor_ruecknahme.sqlite")
                data_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(db_sicherung, aktuelle_db)
                db_zurueckgesetzt = True

        bericht["zurueckgenommen_am"] = datetime.now().astimezone().isoformat(timespec="seconds")
        (sicherung_dir / "bericht.json").write_text(
            json.dumps(bericht, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")

        print(_t("Update zurückgenommen. Installierte Version jetzt: {version}.",
                 version=bericht.get("von") or _t("unbekannt")))
        if db_zurueckgesetzt:
            print(_t("Die Datenbank wurde auf den Stand vor dem Update zurückgesetzt."))
        return EXIT_OK
    finally:
        _entsperren(lock_pfad)


# ── Argumente & Einstieg ─────────────────────────────────────────────────────────────────────
def _parser() -> _Parser:
    p = _Parser(prog="bms_update.py",
                description=_t("Spielt eine neue BMS-Version ein, ohne Daten oder Anpassungen zu verlieren."))
    p.add_argument("paket", nargs="?", default=None,
                    help=_t("Pfad zu einem BMS_*.zip-Paket (sonst gewinnt die höchste Version aus dem "
                            "neuesten GitHub-Release und dem Download-Ordner; mit einem Pfad "
                            "findet kein Netzkontakt statt)."))
    p.add_argument("--installation", required=True, help=_t("Programmordner der Installation."))
    p.add_argument("--pruefen", action="store_true",
                    help=_t("Nur prüfen und den Ablaufplan zeigen, nichts ändern."))
    p.add_argument("--ja", action="store_true",
                    help=_t("Rückfrage vor dem Einspielen automatisch bestätigen."))
    p.add_argument("--erzwingen", action="store_true",
                    help=_t("Vorschau-Pakete und gleiche/ältere Versionen dennoch einspielen."))
    p.add_argument("--offline", action="store_true",
                    help=_t("Nicht online nach einer neuen Version suchen."))
    p.add_argument("--zurueck", action="store_true",
                    help=_t("Letztes Update rückgängig machen, statt ein neues einzuspielen."))
    p.add_argument("--mit-datenbank", action="store_true",
                    help=_t("Bei --zurueck die Datenbank ohne Rückfrage mit zurücksetzen (nur für "
                            "Tests und Notfälle; --ja allein beantwortet diese Frage NICHT)."))
    p.add_argument("--ohne-abhaengigkeiten", action="store_true",
                    help=_t("Python- und npm-Abhängigkeiten nicht installieren (nur für Tests und Notfälle)."))
    p.add_argument("--ohne-selbsttest", action="store_true",
                    help=_t("Selbsttest nach dem Einspielen überspringen (nur für Tests und Notfälle)."))
    p.add_argument("--delegiert", action="store_true",
                    help=_t("Intern: markiert, dass bereits an die im Paket enthaltene Werkzeug-Fassung "
                            "übergeben wurde, keine erneute Selbstaktualisierung."))
    return p


def main(argv: list[str] | None = None) -> int:
    argv_wirksam = list(sys.argv[1:]) if argv is None else list(argv)

    parser = _parser()
    try:
        args = parser.parse_args(argv_wirksam)
    except _ArgparseFehler as exc:
        print(_t("Fehler: {fehler}", fehler=exc))
        return EXIT_AUFRUF_FALSCH

    try:
        if args.zurueck:
            return _zurueck_ausfuehren(args)
        return _update_ausfuehren(args, argv_wirksam)
    except Abbruch as exc:
        print(exc.nachricht)
        return exc.exit_code
    except Fehlgeschlagen as exc:
        # Nur auf dem --zurueck-Pfad erreichbar (der normale Update-Pfad faengt Fehlgeschlagen
        # bereits selbst ab und rollt zurueck, s. _update_ausfuehren) -- Dateien sind dort schon
        # wiederhergestellt, ein weiteres Zurueckrollen gibt es nicht.
        print(_t("Fehlgeschlagen: {fehler}", fehler=exc.nachricht))
        return EXIT_ABGEBROCHEN


if __name__ == "__main__":
    raise SystemExit(main())
