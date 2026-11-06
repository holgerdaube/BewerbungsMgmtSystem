#!/usr/bin/env python3
"""Coach-Site-Einstellungen (Phase 82 A1) — macht die in Phase 81 fest verdrahtete
Coach-Site (SFTP-Zugang nur in `~/.bewerbung_mgmt_secrets/coach_sftp.env`, Terminal-Skripte,
eine feste Domain hart im `.htaccess`-Template) für andere Installationen konfigurierbar —
Auftrag 12.08.2026: „ich benötige in den Einstellungen noch eine Möglichkeit für andere
Benutzer, ein anderes Ziel anzugeben, also die Eingabe einer URL und eines Benutzers und eines
Passwortes und eine Möglichkeit, diese Funktion an- und abzuschalten."

SPEICHERORT: `~/.bewerbung_mgmt_secrets/coach_settings.json` (Verzeichnis 700, Datei 600 —
exakt das Muster aus `pipeline.imap_mail.SETTINGS_FILE`/`save_settings`). Override per
`BMS_SECRETS_DIR` (für Tests Pflicht — ohne den Override gäbe es keinen Weg, dieses Modul zu
testen, ohne die echten Secrets anzufassen, s. `tests/test_coach_settings.py`).

MIGRATION AUS PHASE 81 (ohne Zutun des Nutzers): fehlt `coach_settings.json`, aber
`coach_sftp.env` existiert (das alte, rein terminalbasierte Setup), liefert `load_settings()`
deren Werte automatisch — `aktiv=true`, weil eine vorhandene env-Datei bedeutet: das Setup lief
bereits und war aktiv. Die env-Datei wird dabei NUR GELESEN, nie geschrieben oder gelöscht — sie
bleibt der Rollback-Pfad: ein `git revert` dieser Phase plus Löschen von `coach_settings.json`
fällt automatisch auf den alten Zustand zurück, ohne dass Code angefasst werden muss.

COACH-PASSWORT: wird NIE gespeichert — `set_coach_login()` verrechnet es sofort zu einem
bcrypt-Hash in `coach_htpasswd` (dieselbe Datei, die `scripts/coach_deploy.sh` bereits heute
hochlädt). Kein Klartext-Coach-Passwort erreicht jemals die Platte.

SHELL-KONTRAKT (Skripte ↔ Python, Bau-Spec Abschnitt 1.3): `python -m pipeline.coach_settings
shell` gibt die Konfiguration als `VAR='wert'`-Zeilen aus, die eine aufrufende Shell per
`eval "$(...)"` einliest — INKLUSIVE des SFTP-Passworts im Klartext auf stdout. Das ist
BEABSICHTIGT, kein I1-Verstoß: die Shell hält das Passwort nur kurz in einer eigenen Variable,
es landet nie in der Prozessliste (anders als ein CLI-Argument) und nie in einem Log, solange
die aufrufenden Skripte es selbst nicht ausgeben. Modus `zeigen` (auch Default ohne Argument)
liefert stattdessen JSON OHNE Passwort, für Diagnose am Terminal. `shell` gibt IMMER Exit 0
zurück — auch ohne jede Konfiguration (dann `COACH_AKTIV='0'` und leere Werte) —, sonst reißt
`set -e` in den aufrufenden Skripten den Tageslauf ab (Invariante I4).

I2 (Live-Leak 10.08.2026, s. tasks/lessons.md): jede lftp-Fehlerausgabe trägt die volle
`sftp://user:pass@host`-Verbindungs-URL. `ohne_geheimnisse()` ist die EINZIGE Stelle, die das
filtern darf — `sftp_lauf()` filtert IMMER, bevor Text zurückgegeben wird (Erfolg wie Fehler);
niemand sonst im Modul fasst rohe lftp-Ausgabe an.
"""
import contextlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import bcrypt
import httpx

# Gleiches Muster wie pipeline.imap_mail.SECRETS_DIR (Phase 71F) — Override per BMS_SECRETS_DIR.
SECRETS_DIR = Path(os.environ.get("BMS_SECRETS_DIR", str(Path.home() / ".bewerbung_mgmt_secrets")))
SETTINGS_FILE = SECRETS_DIR / "coach_settings.json"
ENV_FILE = SECRETS_DIR / "coach_sftp.env"      # Phase 81, wird nur GELESEN (Migrationspfad)
HTPASSWD_FILE = SECRETS_DIR / "coach_htpasswd"

_DEFAULTS = {
    "aktiv": False, "site_url": "", "sftp_host": "", "sftp_user": "", "sftp_password": "",
    "sftp_dir": "", "authuserfile": "", "coach_user": "",
}


class ServerpfadKonflikt(RuntimeError):
    """Eigene Exception-Klasse (statt eines generischen `RuntimeError`) — damit
    `routes_coach_settings.post_serverpfad` daraus HTTP 409 macht statt 400 (API-Kontrakt 1.4:
    „Im Zielverzeichnis liegen bereits Dateien" ist ein Konflikt, kein simpler Fehlschlag)."""


# ── Einstellungsdatei ────────────────────────────────────────────────────────────────────
def _aus_datei_lesen() -> "dict | None":
    if not SETTINGS_FILE.exists():
        return None
    try:
        roh = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(roh, dict):
        return None
    return roh


def _parse_env_datei(pfad: Path) -> dict:
    """Sehr einfacher `KEY=VALUE`-Parser für die Phase-81-env-Datei (kein allgemeiner
    .env-Parser — keine Variablenexpansion, kein Multiline, das braucht diese eine Datei nicht):
    `#`-Kommentare und Leerzeilen überspringen, führendes `export ` tolerieren, umschließende
    `"`/`'` strippen."""
    werte: dict = {}
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#"):
            continue
        if zeile.startswith("export "):
            zeile = zeile[len("export "):].strip()
        if "=" not in zeile:
            continue
        key, _, wert = zeile.partition("=")
        key = key.strip()
        wert = wert.strip()
        if len(wert) >= 2 and wert[0] == wert[-1] and wert[0] in "\"'":
            wert = wert[1:-1]
        werte[key] = wert
    return werte


def _aus_env_migrieren() -> "dict | None":
    """Migrationspfad aus Phase 81 (Bau-Spec 1.2). `site_url`/`coach_user` bleiben leer — beide
    Konzepte gab es in Phase 81 noch nicht (die Site hing hart an einer festen Domain, der Login
    kam ausschließlich über `scripts/coach_passwort.sh`, dessen Ergebnis bereits in
    `coach_htpasswd` liegt und über `coach_login_benutzer()` sichtbar bleibt)."""
    if not ENV_FILE.exists():
        return None
    roh = _parse_env_datei(ENV_FILE)
    return {
        "aktiv": True,
        "site_url": "",
        "sftp_host": roh.get("COACH_SFTP_HOST", ""),
        "sftp_user": roh.get("COACH_SFTP_USER", ""),
        "sftp_password": roh.get("COACH_SFTP_PASS", ""),
        "sftp_dir": roh.get("COACH_SFTP_DIR", ""),
        "authuserfile": roh.get("COACH_AUTHUSERFILE", ""),
        "coach_user": "",
    }


def load_settings() -> dict:
    """JSON, sonst env-Migration (1.2), sonst Defaults. Unbekannte Schlüssel aus der Datei
    werden verworfen, fehlende mit Defaults ergänzt — so bleibt die Rückgabeform stabil, auch
    wenn ein künftiges Feld dazukommt oder eine alte Datei ein inzwischen entferntes trägt."""
    roh = _aus_datei_lesen()
    if roh is None:
        roh = _aus_env_migrieren()
    if roh is None:
        roh = {}
    ergebnis = dict(_DEFAULTS)
    for feld in _DEFAULTS:
        if feld in roh:
            ergebnis[feld] = roh[feld]
    ergebnis["aktiv"] = bool(ergebnis["aktiv"])
    return ergebnis


def save_settings(data: dict) -> None:
    """Schreibt `coach_settings.json` chmod 600 (Muster `imap_mail.save_settings`) — nur
    bekannte Felder (unbekannte werden verworfen, fehlende mit Defaults ergänzt, damit die Datei
    immer dieselbe, vollständige Form hat). Das Coach-Passwort ist bewusst NICHT Teil dieses
    Dicts — es existiert als Klartext nirgends, s. `set_coach_login()`."""
    bereinigt = dict(_DEFAULTS)
    for feld in _DEFAULTS:
        if feld in data:
            bereinigt[feld] = data[feld]
    bereinigt["aktiv"] = bool(bereinigt["aktiv"])
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(SETTINGS_FILE.parent, 0o700)
    SETTINGS_FILE.write_text(json.dumps(bereinigt, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(SETTINGS_FILE, 0o600)


def quelle() -> str:
    """`settings` (JSON vorhanden) · `env-migriert` (nur die alte Phase-81-env-Datei) · `leer`
    (nichts von beidem) — rein Datei-Existenz-basiert, s. Bau-Spec 1.4."""
    if SETTINGS_FILE.exists():
        return "settings"
    if ENV_FILE.exists():
        return "env-migriert"
    return "leer"


# ── Coach-Login (Basic-Auth-Zugangsdatei) ───────────────────────────────────────────────
_BCRYPT_PREFIX_RE = re.compile(rb"^\$2[abxy]\$")


def set_coach_login(benutzer: str, passwort: str) -> None:
    """Verrechnet das Coach-Passwort SOFORT zu einem bcrypt-Hash — das Klartext-Passwort wird
    NIRGENDS gespeichert (Bau-Spec 1.1). Präfix wird auf `$2y$` normalisiert: Pythons `bcrypt`
    liefert `$2b$`, aber Apache/APR (IONOS) und `htpasswd -B` (bisheriger Terminal-Weg,
    `scripts/coach_passwort.sh`) erzeugen/erwarten `$2y$`. Für Passwörter ohne Bytes >= 0x80
    (also praktisch jedes getippte Passwort) sind beide Varianten identisch — `2y` behebt nur
    eine historische PHP-Randbehandlung solcher Bytes — `bcrypt.checkpw()` prüft beide gleich
    (s. `tests/test_coach_settings.py`, dort auch der Beweis per `checkpw`). Datei bekommt
    GENAU EINE Zeile `benutzer:hash` — ein einziger Coach-Login ist Produktentscheidung
    (Plan-Dialog 12.08.2026)."""
    from app.sprache import tx      # erst hier: das Kommandozeilen-Werkzeug `shell` soll app.db nicht laden
    benutzer = (benutzer or "").strip()
    if not benutzer:
        raise ValueError(tx("Coach-Benutzername darf nicht leer sein."))
    pw_bytes = (passwort or "").encode("utf-8")
    if len(pw_bytes) > 72:
        raise ValueError(tx("Coach-Passwort ist zu lang (bcrypt erlaubt maximal 72 Byte)."))
    hash_bytes = bcrypt.hashpw(pw_bytes, bcrypt.gensalt())
    hash_bytes = _BCRYPT_PREFIX_RE.sub(b"$2y$", hash_bytes, count=1)
    HTPASSWD_FILE.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(HTPASSWD_FILE.parent, 0o700)
    HTPASSWD_FILE.write_text(f"{benutzer}:{hash_bytes.decode('ascii')}\n", encoding="utf-8")
    os.chmod(HTPASSWD_FILE, 0o600)


def coach_login_gesetzt() -> bool:
    if not HTPASSWD_FILE.exists():
        return False
    return bool(HTPASSWD_FILE.read_text(encoding="utf-8").strip())


def coach_login_benutzer() -> str:
    """Liest den Benutzernamen aus `coach_htpasswd` (Format `benutzer:hash`) — damit zeigt die
    UI ihn auch dann an, wenn `coach_user` in den Settings leer ist (z. B. weil der Login noch
    über den alten Terminal-Weg `scripts/coach_passwort.sh` gesetzt wurde)."""
    if not HTPASSWD_FILE.exists():
        return ""
    zeile = HTPASSWD_FILE.read_text(encoding="utf-8").strip()
    benutzer, trenner, _ = zeile.partition(":")
    return benutzer if trenner else ""


# ── Pflichtfelder für aktiv=true ─────────────────────────────────────────────────────────
_FEHLENDE_FELDER_REIHENFOLGE = (
    ("site_url", "site_url"),
    ("sftp_host", "sftp_host"),
    ("sftp_user", "sftp_user"),
    ("sftp_password", "SFTP-Passwort"),
    ("sftp_dir", "sftp_dir"),
    ("authuserfile", "authuserfile"),
    ("coach_user", "coach_user"),
)


def fehlende_felder(data: dict) -> list:
    """Deutsche Klartext-Liste der noch fehlenden Pflichtfelder für `aktiv=true` (API-Kontrakt
    1.4). Das Coach-Passwort steht NIE in `data` (es wird nie gespeichert, s. Moduldocstring) —
    ob es gesetzt ist, wird separat über `coach_login_gesetzt()` geprüft."""
    from app.sprache import tx, uebersetzt      # erst hier, s. set_coach_login
    fehlend = [uebersetzt(label) for feld, label in _FEHLENDE_FELDER_REIHENFOLGE
               if not str(data.get(feld) or "").strip()]
    if not coach_login_gesetzt():
        fehlend.append(tx("Coach-Passwort"))
    return fehlend


# ── Shell-Kontrakt (1.3) ──────────────────────────────────────────────────────────────────
def _shell_quote_immer(wert: str) -> str:
    """Wie `shlex.quote()`s eigener Quoting-Zweig, aber IMMER mit sichtbaren `'...'` umschlossen
    — `shlex.quote()` selbst lässt die Anführungszeichen bei „sicheren" Strings (nur Ziffern/
    Buchstaben/`@%+=:,./-`) weg, der Shell-Kontrakt will aber einheitlich aussehende
    `VAR='wert'`-Zeilen, unabhängig vom Inhalt. Escaping ist exakt `shlex.quote()`s Algorithmus
    für den Quoting-Fall — per `shlex.split()` gegengeprüft in `tests/test_coach_settings.py`."""
    return "'" + wert.replace("'", "'\"'\"'") + "'"


_SHELL_FELDER = (
    ("COACH_AKTIV", lambda d: "1" if d.get("aktiv") else "0"),
    ("COACH_SITE_URL", lambda d: str(d.get("site_url") or "")),
    ("COACH_SFTP_HOST", lambda d: str(d.get("sftp_host") or "")),
    ("COACH_SFTP_USER", lambda d: str(d.get("sftp_user") or "")),
    ("COACH_SFTP_PASS", lambda d: str(d.get("sftp_password") or "")),
    ("COACH_SFTP_DIR", lambda d: str(d.get("sftp_dir") or "")),
    ("COACH_AUTHUSERFILE", lambda d: str(d.get("authuserfile") or "")),
)


def shell_zeilen(data: dict) -> str:
    """Bau-Spec 1.3: sieben `VAR='wert'`-Zeilen zum `eval`-Einlesen in `scripts/coach_deploy.sh`
    / `coach_site.sh`. IMMER alle sieben, auch ganz ohne Konfiguration (dann `COACH_AKTIV='0'`
    und leere Werte) — die aufrufenden Skripte verlassen sich auf genau diese Variablen, `set
    -e` dort würde sonst den Tageslauf abreißen (I4)."""
    zeilen = [f"{name}={_shell_quote_immer(wert_fn(data))}" for name, wert_fn in _SHELL_FELDER]
    return "\n".join(zeilen) + "\n"


# ── I2: gefilterte lftp-Ausgabe ──────────────────────────────────────────────────────────
def ohne_geheimnisse(text: str, data: dict) -> str:
    """Filtert lftp-Rohtext, BEVOR er irgendwohin geht — Antwort, Exception oder Log (I2,
    Live-Leak 10.08.2026: die volle `sftp://user:pass@host`-Verbindungs-URL landete ungefiltert
    im Frontend). Zwei Schritte: (1) jede Zeile mit `sftp://` komplett verwerfen — die
    Verbindungs-URL inkl. Zugangsdaten steht nur dort; (2) ein evtl. dennoch auftauchendes
    Passwort (z. B. in einer Fehlermeldung außerhalb einer `sftp://`-Zeile) durch `***` ersetzen.
    EINZIGE Stelle im Modul, die das darf — `sftp_lauf()` ruft ausschließlich hierüber."""
    passwort = str(data.get("sftp_password") or "")
    zeilen = [z for z in (text or "").splitlines() if "sftp://" not in z]
    gefiltert = "\n".join(zeilen).strip()
    if passwort:
        gefiltert = gefiltert.replace(passwort, "***")
    return gefiltert


# ── lftp-Aufrufe ──────────────────────────────────────────────────────────────────────────
def sftp_lauf(data: dict, befehle: list, timeout: int = 60) -> str:
    """Ein lftp-Aufruf gegen den in `data` beschriebenen SFTP-Zugang (Muster
    `scripts/coach_deploy.sh`: `-u user,pass sftp://host`, `set sftp:auto-confirm yes` gegen die
    Hostkey-Nachfrage beim IONOS-Erstkontakt). `befehle` sind die eigentlichen lftp-Kommandos
    (z. B. `["cls -1 /coach"]`) — Präfix (`set sftp:auto-confirm yes;`) und Suffix (`bye`) setzt
    diese Funktion selbst. Rückgabe ist STETS durch `ohne_geheimnisse()` gefiltert (I2) — auch im
    Fehlerfall. Fehlt `lftp` im PATH → `RuntimeError` mit Installationshinweis (macOS: Homebrew)."""
    from app.sprache import tx      # erst hier, s. set_coach_login
    if shutil.which("lftp") is None:
        raise RuntimeError(tx("lftp fehlt — installieren mit: brew install lftp"))
    host = str(data.get("sftp_host") or "").strip()
    user = str(data.get("sftp_user") or "").strip()
    passwort = str(data.get("sftp_password") or "")
    if not host or not user:
        raise RuntimeError(tx("SFTP-Host und SFTP-Benutzer müssen gesetzt sein, bevor eine "
                              "Verbindung aufgebaut werden kann."))
    kommando = "set sftp:auto-confirm yes; " + "; ".join(
        b.strip().rstrip(";") for b in befehle) + "; bye"
    cmd = ["lftp", "-u", f"{user},{passwort}", f"sftp://{host}", "-e", kommando]
    try:
        ergebnis = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        text = ohne_geheimnisse((exc.stdout or "") + (exc.stderr or ""), data)
        meldung = tx("lftp-Zeitüberschreitung nach {timeout}s.", timeout=timeout)
        raise RuntimeError(f"{meldung} {text}".strip()) from None
    ausgabe = ohne_geheimnisse((ergebnis.stdout or "") + (ergebnis.stderr or ""), data)
    if ergebnis.returncode != 0:
        raise RuntimeError(ausgabe or tx("lftp beendete sich mit Exit-Code {code}.", code=ergebnis.returncode))
    return ausgabe


# ── Serverpfad-Automatik (API-Kontrakt 1.4, POST /serverpfad) ───────────────────────────
_SERVERPFAD_ERLAUBT = {".", "..", ".htaccess", ".htpasswd", "bms_pfad_probe.php"}
_PROBE_PHP_INHALT = '<?php echo "BMSPFAD:" . __DIR__ . ":ENDE";'
_PROBE_MARKER_RE = re.compile(r"BMSPFAD:(.*?):ENDE")
_PROBE_DATEINAME = "bms_pfad_probe.php"


def serverpfad_ermitteln(data: dict) -> dict:
    """Fünf Schritte (Bau-Spec 1.4 `POST /serverpfad`):
    1. Guard: das Zielverzeichnis darf außer `.`/`..`/`.htaccess`/`.htpasswd`/der Probe-Datei
       selbst NICHTS enthalten → sonst `ServerpfadKonflikt` (409). Grund: die Probe-Datei ist für
       die Dauer des HTTP-Abrufs öffentlich lesbar — im leeren Verzeichnis gibt es nichts zu sehen.
    2. Eine winzige PHP-Datei hochladen, die ihr eigenes Verzeichnis ausgibt.
    3. Sie per HTTP abrufen und den Marker `BMSPFAD:<pfad>:ENDE` herausschneiden.
    4. `finally`: die Probe-Datei per `rm -f` wieder löschen — AUCH bei jedem Fehler (Upload-
       Fehlschlag inklusive), Löschfehler selbst werden verschluckt (best effort, s.
       tasks/lessons.md „Fehlerpfade/catch-all": ein `finally`, das aufräumen soll, darf nicht an
       einer eigenen Exception scheitern und dabei die eigentliche Fehlermeldung verschlucken).
    5. Kein Marker gefunden → `RuntimeError` (400) mit der Bitte, den Pfad manuell einzutragen.
       Nie raten — ob PHP fehlt, der Pfad falsch ist oder der Server nicht erreichbar war, spielt
       für die Nutzeraktion keine Rolle: von Hand eintragen."""
    from app.sprache import tx      # erst hier, s. set_coach_login
    sftp_dir = str(data.get("sftp_dir") or "").strip()
    site_url = str(data.get("site_url") or "").strip().rstrip("/")
    if not sftp_dir or not site_url:
        raise RuntimeError(
            tx("Serverpfad-Ermittlung braucht Adresse der Seite UND SFTP-Zielverzeichnis — bitte "
               "beides zuerst ausfüllen und speichern.")
        )

    bestand = sftp_lauf(data, [f"cls -1 -a {sftp_dir}"])
    eintraege = {z.strip() for z in bestand.splitlines() if z.strip()}
    unerwartet = eintraege - _SERVERPFAD_ERLAUBT
    if unerwartet:
        raise ServerpfadKonflikt(
            tx("Im Zielverzeichnis liegen bereits Dateien. Die automatische Ermittlung läuft nur "
               "im leeren Verzeichnis; bitte den Pfad manuell eintragen — siehe Anleitung.")
        )

    remote_probe = f"{sftp_dir}/{_PROBE_DATEINAME}"
    marker = None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            lokale_probe = Path(tmp) / _PROBE_DATEINAME
            lokale_probe.write_text(_PROBE_PHP_INHALT, encoding="utf-8")
            sftp_lauf(data, [f'put "{lokale_probe}" -o {remote_probe}'])
        try:
            antwort = httpx.get(f"{site_url}/{_PROBE_DATEINAME}", timeout=15, follow_redirects=True)
            treffer = _PROBE_MARKER_RE.search(antwort.text)
            marker = treffer.group(1) if treffer else None
        except Exception:            # noqa: BLE001 — jeder Grund (DNS, Timeout, kein PHP) führt
            marker = None            # zur selben ehrlichen "nicht erreichbar"-Meldung, nie raten.
    finally:
        with contextlib.suppress(Exception):
            sftp_lauf(data, [f"rm -f {remote_probe}"])

    if not marker:
        raise RuntimeError(
            tx("Die Datei war nicht erreichbar oder PHP ist nicht aktiv — bitte den Serverpfad "
               "manuell eintragen, siehe Anleitung.")
        )
    return {"authuserfile": f"{marker}/.htpasswd", "serverpfad": marker}


# ── CLI ───────────────────────────────────────────────────────────────────────────────────
def main() -> None:
    """`python -m pipeline.coach_settings shell` (Shell-Kontrakt 1.3) oder `zeigen` (auch
    Default ohne Argument, JSON ohne Passwort — für Diagnose am Terminal). Gibt in BEIDEN Modi
    Exit 0 zurück (I4) — beide Pfade sind reine Datei-Lesevorgänge, es gibt nichts, was hier
    kontrolliert fehlschlagen müsste."""
    modus = sys.argv[1] if len(sys.argv) > 1 else "zeigen"
    data = load_settings()
    if modus == "shell":
        sys.stdout.write(shell_zeilen(data))
        return
    diagnose = {k: v for k, v in data.items() if k != "sftp_password"}
    diagnose["sftp_password_gesetzt"] = bool(data.get("sftp_password"))
    diagnose["coach_password_gesetzt"] = coach_login_gesetzt()
    diagnose["quelle"] = quelle()
    print(json.dumps(diagnose, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
