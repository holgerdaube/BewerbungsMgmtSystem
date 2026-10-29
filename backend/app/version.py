"""Versionsauskunft der laufenden Installation (P2-51, Verträge V1 + V5).

Kein Kopierschutz und keine Lizenzprüfung — dieses Modul beantwortet nur EINE Frage: „Welche
Fassung läuft hier gerade, und woher weiß ich das?" Drei Installationsarten:

  * "paket"    — `bms_manifest.json` liegt im Programmordner (U2a hat sie mitgepackt, V3):
                 Werte kommen von DORT, `commit` auf 7 Zeichen gekürzt.
  * "git"      — kein Manifest, aber `.git` (Datei oder Ordner — bei einer iCloud-Installation
                 z. B. ein Zeiger auf `.git.nosync/`, für `git` selbst transparent): `version`
                 aus `VERSION`, `commit`/`datum` über `git rev-parse`/`git show`.
  * "unbekannt" — keins von beidem (z. B. ein Quellbaum ohne Git-Metadaten): `version` aus
                 `VERSION`, falls vorhanden, sonst None.

Jeder Git-Aufruf läuft mit Timeout 5 s und fängt jeden Fehler ab (kein `git` installiert, kein
Repo, Timeout, …) — die Einstellungen-Seite darf an dieser Auskunft NIE mit einem 500 scheitern
(V5). Aus demselben Grund: kein Zwischenspeichern über Prozess-Aufrufe hinweg — `version_info()`
ist erlaubt, aber nicht verpflichtet, ihr Ergebnis zu cachen (der Nutzer startet den Server nach
Änderungen ohnehin neu); hier bewusst OHNE Cache, damit `root`/`data_dir` in Tests bei jedem
Aufruf frisch wirken (Lehre Phase 87: ein Default/Cache, der an einen einzigen State bindet,
wird in Tests zur Falle)."""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Optional

from pipeline import changelog

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_GIT_TIMEOUT_S = 5

_BETRIEBSSYSTEM = {"Darwin": "mac", "Windows": "windows", "Linux": "linux"}

# `git describe --tags --long --dirty --match "v[0-9]*"` -> "v1.0.0-3-gabc1234[-dirty]".
_DESCRIBE_RE = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)-(?P<abstand>\d+)-g[0-9a-f]+(?P<dirty>-dirty)?$")


def _betriebssystem() -> str:
    return _BETRIEBSSYSTEM.get(platform.system(), "linux")


def _version_datei(root: Path) -> Optional[str]:
    pfad = root / "VERSION"
    if not pfad.is_file():
        return None
    text = pfad.read_text(encoding="utf-8").strip()
    return text or None


def version_text(root: Path | None = None) -> str:
    """Kurzer Versionstext für `FastAPI(version=…)` (V1) — aus `VERSION`, sonst „0.0.0“.
    `root=None` (Normalbetrieb) löst erst im Rumpf auf den echten Programmordner auf (Lehre
    Phase 87, s. Moduldocstring)."""
    root = Path(root) if root is not None else PROJECT_ROOT
    return _version_datei(root) or "0.0.0"


def _git(root: Path, *args: str) -> Optional[str]:
    """Ein Git-Aufruf gegen `root`, robust gegen jeden Fehler (V5: nie ein 500) — leere Ausgabe
    zählt wie ein Fehler (None), damit Aufrufer nicht zusätzlich auf „“ prüfen müssen."""
    try:
        ergebnis = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if ergebnis.returncode != 0:
        return None
    ausgabe = ergebnis.stdout.strip()
    return ausgabe or None


def _entwicklungsstand(root: Path) -> tuple[Optional[str], bool]:
    """(Anzeigetext, freigabe) aus `git describe` (V5) — ohne passendes Tag „noch keine
    Freigabe“/False; ein Parse-Fehler (unerwartetes Format) fällt auf denselben Text zurück,
    statt eine falsche Freigabe zu melden."""
    beschreibung = _git(root, "describe", "--tags", "--long", "--dirty", "--match", "v[0-9]*")
    if not beschreibung:
        return "noch keine Freigabe", False
    treffer = _DESCRIBE_RE.match(beschreibung)
    if not treffer:
        return "noch keine Freigabe", False
    abstand = int(treffer.group("abstand"))
    dirty = bool(treffer.group("dirty"))
    text = f"{abstand} {'Commit' if abstand == 1 else 'Commits'} nach {treffer.group('version')}"
    if dirty:
        text += ", mit lokalen Änderungen"
    return text, (abstand == 0 and not dirty)


def _aenderungen_aus_changelog(root: Path, version: Optional[str], *, unveroeffentlicht_zuerst: bool) -> Optional[str]:
    """Abschnitt aus `CHANGELOG.md` (V5): bei `paket` direkt die installierte `version`; bei
    `git` zuerst „Unveröffentlicht“ (falls nicht leer), sonst die `version` aus `VERSION`.
    Jeder Lesefehler (Datei fehlt, kaputtes Encoding) -> None statt Ausnahme."""
    try:
        text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        return None
    if unveroeffentlicht_zuerst:
        offen = changelog.abschnitt(text, None)
        if offen:
            return offen
    if not version:
        return None
    return changelog.abschnitt(text, version)


def _neuestes_update(data_dir: Path) -> Optional[dict]:
    """Neuester Update-Bericht (V4) mit `ergebnis == "ok"` und ohne `zurueckgenommen_am`, sonst
    None. Sortiert über die Ordnernamen (`<JJJJ-MM-TT_HHMMSS>_…`, lexikographisch = chronologisch)
    statt über den `zeitpunkt`-Feldinhalt — robuster gegen krumme/fehlende Feldwerte."""
    ordner = data_dir / "updates"
    if not ordner.is_dir():
        return None
    try:
        eintraege = sorted(ordner.iterdir(), key=lambda p: p.name, reverse=True)
    except OSError:
        return None
    for eintrag in eintraege:
        bericht_pfad = eintrag / "bericht.json"
        if not bericht_pfad.is_file():
            continue
        try:
            bericht = json.loads(bericht_pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if bericht.get("ergebnis") == "ok" and not bericht.get("zurueckgenommen_am"):
            return {"zeitpunkt": bericht.get("zeitpunkt"), "von": bericht.get("von"),
                    "nach": bericht.get("nach")}
    return None


def version_info(root: Path | None = None, data_dir: Path | None = None) -> dict:
    """Antwortkörper für `GET /api/version` (V5). `root`/`data_dir` sind NUR für Tests gedacht
    (Lehre Phase 87: Defaults nie an einen Modulwert binden, der über einen Aufruf hinweg
    feststeht — stattdessen hier im Rumpf auflösen): im Programmbetrieb ist `root` der
    Programmordner, `data_dir` `BMS_DATA_DIR` bzw. `<root>/data` (Muster `app/db.py`)."""
    root = Path(root) if root is not None else PROJECT_ROOT
    if data_dir is not None:
        data_dir = Path(data_dir)
    else:
        data_dir = Path(os.environ.get("BMS_DATA_DIR", root / "data"))

    manifest_pfad = root / "bms_manifest.json"
    version = commit = datum = entwicklungsstand = aenderungen = None
    freigabe = False

    if manifest_pfad.is_file():
        installation = "paket"
        try:
            manifest = json.loads(manifest_pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = {}
        version = manifest.get("version")
        freigabe = bool(manifest.get("freigabe"))
        commit_voll = manifest.get("commit") or None
        commit = commit_voll[:7] if commit_voll else None
        datum = manifest.get("commit_datum")
        aenderungen = _aenderungen_aus_changelog(root, version, unveroeffentlicht_zuerst=False)
    elif (root / ".git").exists():
        installation = "git"
        version = _version_datei(root)
        commit = _git(root, "rev-parse", "--short", "HEAD")
        datum = _git(root, "show", "-s", "--format=%cs", "HEAD")
        entwicklungsstand, freigabe = _entwicklungsstand(root)
        aenderungen = _aenderungen_aus_changelog(root, version, unveroeffentlicht_zuerst=True)
    else:
        installation = "unbekannt"
        version = _version_datei(root)

    return {
        "version": version,
        "freigabe": freigabe,
        "commit": commit,
        "datum": datum,
        "installation": installation,
        "entwicklungsstand": entwicklungsstand,
        "betriebssystem": _betriebssystem(),
        "installationsordner": str(root),
        "letztes_update": _neuestes_update(data_dir),
        "aenderungen": aenderungen,
    }
