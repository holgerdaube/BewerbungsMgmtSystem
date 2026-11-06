"""Automatische Datenbank-Sicherung im laufenden Server (P2-52, Paket S1).

Bisher gab es KEINEN automatischen Sicherungslauf -- nur Handarbeit (`scripts/backup_db.sh`,
nur Mac) oder Sicherungen als Nebeneffekt anderer Vorgänge (`pipeline/cleanup.py::_backup_db`,
`scripts/bms_update.py::_sicherung_erstellen` vor einem Update). Dieses Modul schließt die
Lücke: ein asyncio-Task im Server prüft 60 s nach dem Start und danach alle 30 min, ob heute
schon eine automatische Sicherung existiert, und legt bei Bedarf eine neue an (`starten()`,
`einmal_pruefen()`, V5). Reines Python, keine externe CLI (kein `sqlite3`-Kommandozeilentool) --
läuft dadurch unverändert unter macOS UND Windows (Kundeninstallationen auf beiden Systemen).

**Ablage (V1):** `<DATA_DIR>/backups/auto/bewerbung_JJJJ-MM-TT_HHMMSS.zip`, Inhalt genau eine
Datei `bewerbung.sqlite`. Der Zeitpunkt steckt im Dateinamen (nie in `mtime` -- iCloud-Sync und
Kopiervorgänge verändern `mtime`, der Dateiname bleibt stabil). Ein eigener Unterordner
`auto/`, bewusst getrennt von den bestehenden Sicherungswegen: drei andere Leser kennen das
Muster `data/backups/bewerbung_backup_*.sqlite` direkt in `data/backups/`
(`pipeline.cleanup._backup_dateien`, `scripts/backup_db.sh --rotate`,
`agent_runner._backup_hinweis`) -- die neue automatische Reihe darf von KEINEM davon erfasst
werden, sonst würde z. B. `cleanup._backup_dateien` sie nach 60 Tagen in den Papierkorb
verschieben. Dieses Modul fasst `data/backups/` (ohne `auto/`) selbst nie an, zählt die dortigen
Dateien nur für die Statusauskunft (`status()["weitere"]`).

**Aufbewahrung (V2, `zu_entfernen()`):** reine Funktion ohne Dateizugriff -- immer die neueste
Sicherung, alle der letzten 24 Stunden, je Kalendertag die neueste für die N jüngsten
VORHANDENEN Tage mit Sicherung (kein Kalenderfenster: eine Pause im Betrieb verschiebt das
Fenster nach hinten, verkürzt es aber nicht), ebenso je ISO-Woche und optional je Monat.
Ausgedünnt wird nur NACH einer erfolgreichen neuen Sicherung (`rotieren()`, aufgerufen von
`einmal_pruefen()` und vom `POST`-Endpunkt) -- ein gescheiterter Lauf löscht nie etwas. Die
Lektion „Backups nie automatisch löschen" (`tasks/lessons.md`) gilt unverändert für die
BESTEHENDEN manuellen Sicherungen in `data/backups/`; diese automatische Reihe hat eine EIGENE,
bewusst gewählte Ausdünnung, keinen Widerspruch dazu.

Öffentliche Funktionen: `einstellungen_laden`/`einstellungen_speichern` (V3, `sicherung.json`),
`anlegen`/`rotieren`/`faellig`/`status` (V4, vom Router `app/routes_sicherung.py` verwendet),
`einmal_pruefen`/`starten` (V5, Takt) und `zu_entfernen` (V2, s. o.). `daten_dir`/`db_pfad`/
`jetzt` sind überall optionale Parameter, NIE an einen Modulwert gebunden (Lehre 27.08.2026,
`tasks/lessons.md`): fehlen sie, löst der Funktionsrumpf sie zur Laufzeit über `app.db.DATA_DIR`
bzw. `app.db.DB_PATH` auf -- ein Test kann sie entweder direkt übergeben oder `app.db.DATA_DIR`/
`app.db.DB_PATH` selbst per `monkeypatch` umbiegen (z. B. `einmal_pruefen()`, das V5 zufolge
KEINEN eigenen `daten_dir`-Parameter hat).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import threading
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from app.sprache import tx
from app.terminal import tt

# ── V3: Einstellungen (data/sicherung.json) ─────────────────────────────────────────────────
_EINSTELLUNGEN_DATEI = "sicherung.json"
_STANDARD_EINSTELLUNGEN: dict = {"aktiv": True, "taeglich": 7, "woechentlich": 4, "monatlich": 0}
# Gültige Wertebereiche (Spec V3): bool ist kein int -- wird in _wert_gueltig() ausdrücklich
# VOR der int-Prüfung ausgeschlossen (bool ist in Python ein int-Subtyp).
_GRENZEN: dict = {"taeglich": (1, 60), "woechentlich": (0, 52), "monatlich": (0, 24)}


def _bezeichnung(schluessel: str) -> str:
    """Für Meldungen an den Nutzer: nie den internen Schlüssel zeigen."""
    return {"taeglich": tx("täglichen"), "woechentlich": tx("wöchentlichen"),
            "monatlich": tx("monatlichen")}[schluessel]


# ── V5: Takt ─────────────────────────────────────────────────────────────────────────────────
_ERSTE_PRUEFUNG_S = 60
_PRUEF_INTERVALL_S = 1800

# ── Erkennung der eigenen Dateireihe (V1) ───────────────────────────────────────────────────
_DATEI_RE = re.compile(r"^bewerbung_(\d{4}-\d{2}-\d{2})_(\d{6})(?:_\d+)?\.zip$")
_TMP_RE = re.compile(r"^\.bewerbung_(\d{4}-\d{2}-\d{2}_\d{6})\.(?:sqlite\.tmp|zip\.part)$")

# In-Prozess-Zustand (bewusst im Speicher, s. V4-Vertrag): EIN Server-Prozess hält die Sperre
# und die Takt-Schleife, kein Multi-Prozess-Betrieb hier (gleiches Muster wie
# agent_runner._LETZTE_ROTATION).
_LOCK = threading.Lock()
_letzter_fehler: dict | None = None       # {"zeitpunkt": ISO, "meldung": str} oder None
_takt_start: datetime | None = None       # von starten() gesetzt -- Basis für V4-Warnregel 3
_task: "asyncio.Task | None" = None       # der laufende Takt-Task, s. starten()


class SicherungLaeuft(Exception):
    """Die Sperre ist belegt -- es läuft bereits eine andere Sicherung (Takt oder „Jetzt
    sichern" gleichzeitig)."""


# ── Modulwerte NIE cachen, immer zur Laufzeit lesen (Lehre 27.08.2026) ──────────────────────
def _resolve_daten_dir(daten_dir: Path | None) -> Path:
    if daten_dir is not None:
        return Path(daten_dir)
    from app import db
    return db.DATA_DIR


def _resolve_db_pfad(db_pfad: Path | None) -> Path:
    if db_pfad is not None:
        return Path(db_pfad)
    from app import db
    return db.DB_PATH


def _auto_ordner(daten_dir: Path) -> Path:
    return daten_dir / "backups" / "auto"


# ── V3: Einstellungen ────────────────────────────────────────────────────────────────────────
def _wert_gueltig(schluessel: str, wert) -> bool:
    """EINE Prüfung für Lesen und Schreiben: Beim Lesen verwirft sie von Hand verdorbene Werte
    (sonst bräche z. B. ein Text statt einer Zahl `zu_entfernen()` und damit jedes Ausdünnen),
    beim Schreiben weist sie sie mit einer Meldung ab."""
    if schluessel == "aktiv":
        return isinstance(wert, bool)
    minimum, maximum = _GRENZEN[schluessel]
    return isinstance(wert, int) and not isinstance(wert, bool) and minimum <= wert <= maximum


def einstellungen_laden(daten_dir: Path | None = None) -> dict:
    """Liest `sicherung.json`, füllt fehlende/unlesbare Werte mit den Standardwerten auf.

    Genau DIESE Funktion füllt Standardwerte auf (Lehre Phase 87, `tasks/lessons.md`: kein
    Default, der nur im Lesepfad existiert) -- `einstellungen_speichern()` unten baut auf ihr
    auf, statt eine eigene Fallback-Logik zu pflegen."""
    daten_dir = _resolve_daten_dir(daten_dir)
    pfad = daten_dir / _EINSTELLUNGEN_DATEI
    roh: dict = {}
    if pfad.is_file():
        try:
            geladen = json.loads(pfad.read_text(encoding="utf-8"))
            if isinstance(geladen, dict):
                roh = geladen
            else:
                raise ValueError("kein JSON-Objekt")
        except (OSError, ValueError) as exc:
            print(tt("[sicherung] WARNUNG: {pfad} ist unlesbar ({art}: {fehler}), verwende Standardwerte", pfad=pfad, art=type(exc).__name__, fehler=exc), flush=True)

    ergebnis = dict(_STANDARD_EINSTELLUNGEN)
    for schluessel in _STANDARD_EINSTELLUNGEN:
        if schluessel not in roh:
            continue
        if _wert_gueltig(schluessel, roh[schluessel]):
            ergebnis[schluessel] = roh[schluessel]
        else:
            print(tt("[sicherung] WARNUNG: ungültiger Wert {wert!r} für '{schluessel}' in {pfad}, verwende {ersatz!r}", wert=roh[schluessel], schluessel=schluessel, pfad=pfad, ersatz=ergebnis[schluessel]), flush=True)
    return ergebnis


def einstellungen_speichern(aenderung: dict, daten_dir: Path | None = None) -> dict:
    """Mischt `aenderung` in die geladenen Einstellungen (Teil-Speichern behält die übrigen
    Werte), prüft das Ergebnis und schreibt es atomar (`.tmp` + `os.replace`).

    Wirft `ValueError` mit einem lesbaren Kundentext bei unbekannten Schlüsseln oder
    ungültigen Werten -- der Router übersetzt das in einen 422."""
    daten_dir = _resolve_daten_dir(daten_dir)

    unbekannt = set(aenderung) - set(_STANDARD_EINSTELLUNGEN)
    if unbekannt:
        raise ValueError(tx("Unbekannte Einstellung: {namen}.", namen=", ".join(sorted(unbekannt))))

    ergebnis = einstellungen_laden(daten_dir)
    ergebnis.update(aenderung)

    if not _wert_gueltig("aktiv", ergebnis["aktiv"]):
        raise ValueError(tx("Die automatische Sicherung lässt sich nur ein- oder ausschalten."))
    for schluessel, (minimum, maximum) in _GRENZEN.items():
        if not _wert_gueltig(schluessel, ergebnis[schluessel]):
            raise ValueError(tx("Die Zahl der {art} Sicherungen muss eine ganze "
                                "Zahl zwischen {minimum} und {maximum} sein.",
                                art=_bezeichnung(schluessel), minimum=minimum, maximum=maximum))

    daten_dir.mkdir(parents=True, exist_ok=True)
    pfad = daten_dir / _EINSTELLUNGEN_DATEI
    tmp = pfad.with_name(pfad.name + ".tmp")
    tmp.write_text(json.dumps(ergebnis, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8")
    os.replace(tmp, pfad)
    return ergebnis


# ── V1: Zwischendateien ──────────────────────────────────────────────────────────────────────
def _stempel(jetzt: datetime) -> str:
    return jetzt.strftime("%Y-%m-%d_%H%M%S")


def _tmp_sqlite_pfad(ordner: Path, stempel: str) -> Path:
    return ordner / f".bewerbung_{stempel}.sqlite.tmp"


def _tmp_zip_pfad(ordner: Path, stempel: str) -> Path:
    return ordner / f".bewerbung_{stempel}.zip.part"


def _alte_zwischendateien_entfernen(ordner: Path, jetzt: datetime) -> None:
    """Eigene `.tmp`/`.part`-Reste aus abgebrochenen Läufen (Server-Absturz mitten im Anlegen),
    die älter als 1 h sind. Der Zeitpunkt kommt -- wie bei der fertigen `.zip` -- aus dem
    Dateinamen, nie aus `mtime` (V1). Nicht erkannte Dateien bleiben unangetastet."""
    if not ordner.is_dir():
        return
    for pfad in ordner.glob(".bewerbung_*"):
        treffer = _TMP_RE.match(pfad.name)
        if not treffer:
            continue
        try:
            zeitpunkt = datetime.strptime(treffer.group(1), "%Y-%m-%d_%H%M%S")
        except ValueError:
            continue
        if jetzt - zeitpunkt > timedelta(hours=1):
            pfad.unlink(missing_ok=True)


def _ziel_dateiname(ordner: Path, stempel: str) -> str:
    """`bewerbung_<stempel>.zip`, bei Namenskollision (zwei Sicherungen in derselben Sekunde)
    `_2`, `_3`, ... (V1)."""
    basis = f"bewerbung_{stempel}.zip"
    if not (ordner / basis).exists():
        return basis
    zaehler = 2
    while True:
        kandidat = f"bewerbung_{stempel}_{zaehler}.zip"
        if not (ordner / kandidat).exists():
            return kandidat
        zaehler += 1


def _kopie_erstellen(db_pfad: Path, ziel: Path) -> None:
    """Kopie über die SQLite-Backup-API, Quelle read-only geöffnet (Vorbild
    `scripts/bms_update.py::_sicherung_erstellen`). Beide Verbindungen werden VOR der Rückkehr
    geschlossen -- unter Windows lässt sich eine Datei mit offener Verbindung nicht löschen/
    umbenennen."""
    quelle = sqlite3.connect(db_pfad.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    try:
        ziel_conn = sqlite3.connect(str(ziel))
        try:
            quelle.backup(ziel_conn)
        finally:
            ziel_conn.close()
    finally:
        quelle.close()


def _integritaet_pruefen(pfad: Path) -> None:
    conn = sqlite3.connect(str(pfad))
    try:
        zeile = conn.execute("PRAGMA integrity_check").fetchone()
    finally:
        conn.close()
    ergebnis = zeile[0] if zeile else None
    if ergebnis != "ok":
        raise RuntimeError(tx("Die Prüfsumme der Kopie ist nicht in Ordnung ({ergebnis}).",
                              ergebnis=ergebnis or tx("kein Ergebnis")))


def _als_zip_packen(quelle: Path, ziel_zip: Path) -> None:
    with zipfile.ZipFile(ziel_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.write(quelle, arcname="bewerbung.sqlite")


def _still_entfernen(pfad: Path) -> None:
    """Eigene Zwischendatei entfernen, ohne dass ein Aufräumfehler den eigentlichen Fehler
    verdeckt. `missing_ok` reicht nicht: Ist ein Elternteil des Pfads eine Datei, wirft `unlink`
    unter macOS/Linux `NotADirectoryError`. Bleibt ein Rest liegen, räumt ihn der nächste Lauf
    nach einer Stunde weg (`_alte_zwischendateien_entfernen`)."""
    try:
        pfad.unlink(missing_ok=True)
    except OSError:
        pass


def _fehler_merken(meldung: str, jetzt: datetime) -> None:
    global _letzter_fehler
    _letzter_fehler = {"zeitpunkt": jetzt.astimezone().isoformat(), "meldung": meldung}


def anlegen(daten_dir: Path | None = None, db_pfad: Path | None = None,
            jetzt: datetime | None = None) -> Path:
    """Legt eine neue automatische Sicherung an (V1): Kopie über die SQLite-Backup-API,
    Prüfsumme, ZIP packen, atomar umbenennen. Wirft `SicherungLaeuft`, wenn schon eine andere
    Sicherung läuft (Sperre nicht-blockierend genommen), sonst die ursprüngliche Ausnahme bei
    jedem anderen Fehler -- in beiden Fehlerfällen bleibt kein `.tmp`/`.part`-Rest zurück, und
    bei jedem Fehler AUSSER `SicherungLaeuft` wird `letzter_fehler` gesetzt (gelöscht bei
    Erfolg). Gibt den Pfad der fertigen `.zip`-Datei zurück."""
    daten_dir = _resolve_daten_dir(daten_dir)
    db_pfad = _resolve_db_pfad(db_pfad)
    jetzt = jetzt or datetime.now()

    if not _LOCK.acquire(blocking=False):
        raise SicherungLaeuft(tx("Es läuft bereits eine Sicherung."))
    try:
        ordner = _auto_ordner(daten_dir)
        stempel = _stempel(jetzt)
        tmp_sqlite = _tmp_sqlite_pfad(ordner, stempel)
        tmp_zip = _tmp_zip_pfad(ordner, stempel)
        start = time.monotonic()
        try:
            # Ordner anlegen und Reste räumen gehören mit in den Fehlerpfad: Scheitert schon das
            # (Rechte, volle Platte), muss `letzter_fehler` es sofort zeigen und nicht erst die
            # Drei-Tage-Warnung.
            ordner.mkdir(parents=True, exist_ok=True)
            _alte_zwischendateien_entfernen(ordner, jetzt)
            _kopie_erstellen(db_pfad, tmp_sqlite)
            _integritaet_pruefen(tmp_sqlite)
            ziel_pfad = ordner / _ziel_dateiname(ordner, stempel)
            _als_zip_packen(tmp_sqlite, tmp_zip)
            os.replace(tmp_zip, ziel_pfad)
        except Exception as exc:
            _still_entfernen(tmp_sqlite)
            _still_entfernen(tmp_zip)
            meldung = str(exc) or type(exc).__name__
            _fehler_merken(meldung, jetzt)
            print(tt("[sicherung] Fehler beim Anlegen: {meldung}", meldung=meldung), flush=True)
            raise
        # Erst NACH dem try: die fertige ZIP steht bereits. Ein Fehler beim Aufräumen der Kopie
        # darf sie nicht nachträglich zum Fehlschlag machen.
        _still_entfernen(tmp_sqlite)

        global _letzter_fehler
        _letzter_fehler = None
        dauer_s = time.monotonic() - start
        groesse = ziel_pfad.stat().st_size
        print(tt("[sicherung] gesichert: {name} ({groesse} Bytes, {dauer:.1f} s)", name=ziel_pfad.name, groesse=groesse, dauer=dauer_s), flush=True)
        return ziel_pfad
    finally:
        _LOCK.release()


# ── V2: Aufbewahrung (reine Funktion, kein Dateizugriff) ────────────────────────────────────
def zu_entfernen(eintraege: list, jetzt: datetime, taeglich: int = 7, woechentlich: int = 4,
                  monatlich: int = 0) -> list:
    """Welche Namen aus `eintraege` (Liste von `(name, zeitpunkt)`) die Aufbewahrungsregel NICHT
    mehr schützt (V2 der Bau-Spec, hier unverändert übernommen): immer die neueste, alles der
    letzten 24 Stunden, je Kalendertag/ISO-Woche/Monat die neueste für die N jüngsten
    VORHANDENEN Perioden -- kein Kalenderfenster, eine Pause im Betrieb verschiebt es nur nach
    hinten. Reine Funktion, kein Dateizugriff, keine Seiteneffekte."""
    sortiert = sorted(eintraege, key=lambda e: e[1], reverse=True)   # neueste zuerst
    behalten = set()
    if sortiert:
        behalten.add(sortiert[0][0])                                 # die neueste immer
    for name, t in sortiert:
        if jetzt - t < timedelta(hours=24):                          # letzte 24 h vollständig
            behalten.add(name)

    def stufe(schluessel, anzahl):
        gesehen = []
        for name, t in sortiert:
            k = schluessel(t)
            if k in gesehen:
                continue
            if len(gesehen) >= anzahl:
                break
            gesehen.append(k)
            behalten.add(name)                                       # neueste je Tag/Woche/Monat

    stufe(lambda t: t.date(), taeglich)
    stufe(lambda t: t.isocalendar()[:2], woechentlich)
    stufe(lambda t: (t.year, t.month), monatlich)
    return [name for name, _ in sortiert if name not in behalten]


def _datei_zeitpunkt(name: str) -> datetime | None:
    treffer = _DATEI_RE.match(name)
    if not treffer:
        return None
    try:
        return datetime.strptime(f"{treffer.group(1)}_{treffer.group(2)}", "%Y-%m-%d_%H%M%S")
    except ValueError:
        return None


def _erkannte_dateien(ordner: Path) -> list:
    """`[(name, zeitpunkt), ...]` der eigenen Reihe in `ordner` -- alles, was nicht exakt auf
    `_DATEI_RE` passt (fremde Dateien, Punkt-Dateien, andere Endungen), wird ignoriert."""
    if not ordner.is_dir():
        return []
    ergebnis = []
    try:
        eintraege = list(ordner.iterdir())
    except OSError:
        return []
    for pfad in eintraege:
        try:
            if not pfad.is_file():
                continue
        except OSError:
            continue
        zeitpunkt = _datei_zeitpunkt(pfad.name)
        if zeitpunkt is not None:
            ergebnis.append((pfad.name, zeitpunkt))
    return ergebnis


def rotieren(daten_dir: Path | None = None, jetzt: datetime | None = None) -> list:
    """Wendet `zu_entfernen()` (V2) mit den gespeicherten Einstellungen (V3) auf die erkannten
    Dateien der eigenen Reihe an und löscht sie. Nur nach einem erfolgreichen `anlegen()`
    aufrufen (von `einmal_pruefen()` und vom `POST`-Endpunkt) -- ein gescheiterter Lauf dünnt
    nie aus. Läuft unter derselben Sperre wie `anlegen()` (V5: „Anlegen + Ausdünnen")."""
    daten_dir = _resolve_daten_dir(daten_dir)
    jetzt = jetzt or datetime.now()
    ordner = _auto_ordner(daten_dir)
    einstellungen = einstellungen_laden(daten_dir)

    with _LOCK:
        eintraege = _erkannte_dateien(ordner)
        namen = zu_entfernen(eintraege, jetzt, taeglich=einstellungen["taeglich"],
                              woechentlich=einstellungen["woechentlich"],
                              monatlich=einstellungen["monatlich"])
        entfernt = []
        for name in namen:
            try:
                (ordner / name).unlink()
                entfernt.append(name)
            except OSError as exc:
                print(tt("[sicherung] WARNUNG: {name} konnte nicht entfernt werden: {fehler}", name=name, fehler=exc), flush=True)

    if entfernt:
        print(tt("[sicherung] {anzahl} alte Sicherung(en) entfernt", anzahl=len(entfernt)), flush=True)
    return entfernt


def faellig(daten_dir: Path | None = None, jetzt: datetime | None = None) -> bool:
    """True, wenn KEINE Datei der eigenen Reihe das Datum von `jetzt` (lokaler Kalendertag)
    trägt."""
    daten_dir = _resolve_daten_dir(daten_dir)
    jetzt = jetzt or datetime.now()
    heute = jetzt.date()
    ordner = _auto_ordner(daten_dir)
    return not any(zeitpunkt.date() == heute for _, zeitpunkt in _erkannte_dateien(ordner))


# ── V4: Statusauskunft ───────────────────────────────────────────────────────────────────────
def _weitere_sicherungen(daten_dir: Path) -> list:
    """`*.sqlite`/`*.zip` direkt in `data/backups/` (ohne `auto/`-Unterordner, ohne
    Punkt-Dateien) -- die BESTEHENDEN Sicherungswege, die dieses Modul nie anfasst, nur zählt."""
    ordner = daten_dir / "backups"
    if not ordner.is_dir():
        return []
    ergebnis = []
    try:
        eintraege = list(ordner.iterdir())
    except OSError:
        return []
    for pfad in eintraege:
        if pfad.name.startswith("."):
            continue
        if pfad.suffix not in (".sqlite", ".zip"):
            continue
        try:
            if pfad.is_file():
                ergebnis.append(pfad)
        except OSError:
            continue
    return ergebnis


def _warnung_ermitteln(einstellungen: dict, neueste: tuple | None, jetzt: datetime) -> str | None:
    """V4-Reihenfolge: ein Fehlschlag wird IMMER gemeldet (unabhängig von `aktiv` -- auch ein
    fehlgeschlagenes „Jetzt sichern" bei ausgeschalteter Automatik ist meldenswert, s.
    Entscheidung 7 der Bau-Spec: „wenn die letzte Sicherung fehlschlug ODER bei eingeschalteter
    Automatik älter als 3 Tage ist" -- nur die zweite Bedingung ist an `aktiv` geknüpft). Ist
    die Automatik aus UND liegt kein Fehler vor, gibt es keine Warnung."""
    if _letzter_fehler is not None:
        return tx("Die letzte Sicherung ist fehlgeschlagen: {meldung}", meldung=_letzter_fehler["meldung"])
    if not einstellungen["aktiv"]:
        return None
    if neueste is not None:
        alter = jetzt - neueste[1]
        if alter > timedelta(hours=72):
            tage = alter.days
            if tage == 1:
                return tx("Die letzte Sicherung ist {tage} Tag alt.", tage=tage)
            return tx("Die letzte Sicherung ist {tage} Tage alt.", tage=tage)
        return None
    if _takt_start is not None and jetzt - _takt_start > timedelta(minutes=10):
        return tx("Es gibt noch keine automatische Sicherung.")
    return None


def status(daten_dir: Path | None = None, jetzt: datetime | None = None) -> dict:
    """Antwortkörper für `GET /api/sicherung` (V4) -- darf NIE mit einer Ausnahme scheitern,
    jeder Verzeichniszugriff ist defensiv (leere Listen statt Absturz bei Berechtigungsfehlern
    o. Ä.)."""
    daten_dir = _resolve_daten_dir(daten_dir)
    jetzt = jetzt or datetime.now()
    einstellungen = einstellungen_laden(daten_dir)
    ordner = _auto_ordner(daten_dir)

    eintraege = sorted(_erkannte_dateien(ordner), key=lambda e: e[1], reverse=True)
    neueste = eintraege[0] if eintraege else None
    letzte = None
    if neueste is not None:
        name, zeitpunkt = neueste
        try:
            groesse = (ordner / name).stat().st_size
        except OSError:
            groesse = 0
        letzte = {"datei": name, "zeitpunkt": zeitpunkt.astimezone().isoformat(), "groesse": groesse}

    def _groesse(name: str) -> int:
        try:
            return (ordner / name).stat().st_size
        except OSError:
            return 0

    weitere_dateien = _weitere_sicherungen(daten_dir)

    return {
        "aktiv": einstellungen["aktiv"],
        "taeglich": einstellungen["taeglich"],
        "woechentlich": einstellungen["woechentlich"],
        "monatlich": einstellungen["monatlich"],
        "ordner": str(ordner),
        "letzte": letzte,
        "anzahl": len(eintraege),
        "gesamtgroesse": sum(_groesse(name) for name, _ in eintraege),
        "weitere": {
            "anzahl": len(weitere_dateien),
            "gesamtgroesse": sum(p.stat().st_size for p in weitere_dateien if _existiert(p)),
        },
        "laeuft": _LOCK.locked(),
        "letzter_fehler": _letzter_fehler,
        "warnung": _warnung_ermitteln(einstellungen, neueste, jetzt),
    }


def _existiert(pfad: Path) -> bool:
    try:
        return pfad.is_file()
    except OSError:
        return False


# ── V5: Takt ─────────────────────────────────────────────────────────────────────────────────
def einmal_pruefen(jetzt: datetime | None = None) -> str:
    """Ein Durchlauf der Takt-Prüfung (V5): `"aus"` (Automatik aus), `"nicht_faellig"` (heute
    schon gesichert), `"laeuft"` (Sperre belegt), `"gesichert"` (neu angelegt + ausgedünnt) oder
    `"fehler"` (Ausnahme beim Anlegen -- NICHT ausgedünnt, `anlegen()` hat den Fehler bereits
    geloggt und `letzter_fehler` gesetzt). Kein `daten_dir`-Parameter (V5-Vertrag) -- der reale
    Takt prüft immer die echte Installation; Tests biegen dafür `app.db.DATA_DIR`/`DB_PATH` per
    `monkeypatch` um."""
    jetzt = jetzt or datetime.now()
    einstellungen = einstellungen_laden()
    if not einstellungen["aktiv"]:
        return "aus"
    if not faellig(jetzt=jetzt):
        return "nicht_faellig"
    try:
        anlegen(jetzt=jetzt)
    except SicherungLaeuft:
        return "laeuft"
    except Exception:
        return "fehler"
    rotieren(jetzt=jetzt)
    return "gesichert"


async def _takt_schleife() -> None:
    """Wartet `_ERSTE_PRUEFUNG_S`, prüft dann in einer Endlosschleife alle
    `_PRUEF_INTERVALL_S` -- beide Werte werden bei JEDEM Warten neu vom Modul gelesen
    (monkeypatch-fähig, Lehre 27.08.2026). `einmal_pruefen()` läuft blockierend (Datei-/
    SQLite-Zugriff) und deshalb über `asyncio.to_thread`, damit sie den Event-Loop nicht
    aufhält (Muster `agent_runner._worker()`/`einmal_pruefen` selbst ruft `anlegen()` synchron).
    Jede Ausnahme wird geloggt, die Schleife lebt weiter (`einmal_pruefen()` fängt die
    erwartbaren Fehler bereits selbst ab; dieser try/except ist das letzte Sicherheitsnetz für
    alles Unerwartete, z. B. einen Fehler in `einstellungen_laden()`/`faellig()` selbst)."""
    await asyncio.sleep(_ERSTE_PRUEFUNG_S)
    while True:
        try:
            ergebnis = await asyncio.to_thread(einmal_pruefen)
            # Nur Ereignisse ins Server-Log: „gesichert" und „fehler" meldet anlegen() selbst,
            # „aus"/„nicht_faellig" wären 48 gleiche Zeilen am Tag.
            if ergebnis == "laeuft":
                print(tt("[sicherung] Takt übersprungen: es läuft bereits eine Sicherung"), flush=True)
        except Exception as exc:       # noqa: BLE001 -- Schleife darf nie sterben (V5)
            print(tt("[sicherung] KRITISCH: Takt-Prüfung fehlgeschlagen: {art}: {fehler}", art=type(exc).__name__, fehler=exc), flush=True)
        await asyncio.sleep(_PRUEF_INTERVALL_S)


def starten() -> None:
    """Startet den Sicherungstakt (V5) -- idempotent: ein zweiter Aufruf legt keinen zweiten
    Task an. Muss aus einem laufenden Event-Loop gerufen werden (Startup-Hook, Muster
    `agent_runner.start_workers()`)."""
    global _task, _takt_start
    if _task is not None:
        return
    _takt_start = datetime.now()
    _task = asyncio.create_task(_takt_schleife())
    print(tt("[sicherung] Takt gestartet: erste Prüfung in {erste} s, danach alle {minuten} min", erste=_ERSTE_PRUEFUNG_S, minuten=_PRUEF_INTERVALL_S // 60), flush=True)
