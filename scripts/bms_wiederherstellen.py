#!/usr/bin/env python3
"""Wiederherstellungs-Werkzeug beim Kunden (P2-66, Paket W) -- spielt eine Sicherung der
BMS-Datenbank zurueck.

NUR STANDARDBIBLIOTHEK, KEINE IMPORTE AUS `app`/`pipeline` (wie scripts/bms_update.py): Das
Werkzeug laeuft bei beendetem BMS und darf sich nicht auf den Programmcode verlassen, dessen
Datenbank es gerade austauscht. Die kleinen Helfer (Server-Pruefung, Sperre, Rueckfrage,
Zip-Slip-Pruefung, Exit-Code-Muster, Selbsttest) kommen aus `bms_update` -- am Code von
`bms_update.py` wird dafuer nichts geaendert.

AUFRUF (aus wiederherstellen.command / wiederherstellen_windows.bat, s. dort):
    bms_wiederherstellen.py --installation DIR [--liste] [--datei NAME] [--ja]

EXIT-CODES: 0 fertig oder nur Liste, 1 abgebrochen ohne Aenderung (Nein, Server laeuft, Sperre,
nichts da, Sicherung unbrauchbar), 2 Fehler beim Einsetzen -- Ausgangszustand wiederhergestellt,
3 Aufruf falsch.

WARUM EIN WERKZEUG UND KEIN KNOPF IN DER APP: Der Server bindet die Datenbank beim Import in
genau einer Engine (app/db.py). Ein Austausch der Datei im laufenden Betrieb waere riskant.
Deshalb laeuft dieses Werkzeug nur bei beendetem BMS.

RUECKNAHME OHNE EIGENEN SCHALTER: Vor dem Einsetzen sichert das Werkzeug den aktuellen Stand als
`data/backups/bewerbung_backup_<Zeit>_vor_wiederherstellung.sqlite`. Diese Datei erscheint beim
naechsten Aufruf selbst in der Liste -- zuruecknehmen heisst, das Werkzeug erneut zu starten und
sie zu waehlen.

NUR DIE DATENBANK: Dokumente (outputs/, Uploads in data/) bleiben unveraendert, die Sicherungen
enthalten nur die Datenbank. Das sagt das Werkzeug vor der Rueckfrage ausdruecklich.

Die Installations-Pruefung von bms_update (bricht bei .git ab) wird bewusst NICHT benutzt: es
geht nur um Daten, nicht um Code, das Werkzeug laeuft auch in einer Git-Installation.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Der Skriptordner steht bei `python scripts/x.py` ohnehin auf sys.path; beim Laden per
# importlib (Tests) nicht -- dann ergaenzen.
_SKRIPT_ORDNER = str(Path(__file__).resolve().parent)
if _SKRIPT_ORDNER not in sys.path:
    sys.path.insert(0, _SKRIPT_ORDNER)

import bms_update  # noqa: E402

EXIT_OK = bms_update.EXIT_OK
EXIT_ABGEBROCHEN = bms_update.EXIT_ABGEBROCHEN
EXIT_ZURUECKGEROLLT = bms_update.EXIT_ZURUECKGEROLLT
EXIT_AUFRUF_FALSCH = bms_update.EXIT_AUFRUF_FALSCH
Abbruch = bms_update.Abbruch

DB_NAME = "bewerbung.sqlite"
SQLITE_KOPF = b"SQLite format 3\x00"
VOR_WIEDERHERSTELLUNG = "_vor_wiederherstellung"

# Lokale Kopie von `app/sicherung.py::_DATEI_RE` (kein Import aus app.*).
_AUTO_RE = re.compile(r"^bewerbung_(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})(\d{2})(?:_\d+)?\.zip$")
# Zeitstempel in manuellen Sicherungen: bewerbung_backup_20261005_101500[...].sqlite
_MANUELL_ZEIT_RE = re.compile(r"(\d{8})_(\d{6})")

ART_AUTO = "automatische Sicherung"
ART_MANUELL = "manuelle Sicherung"
ART_VORHER = "vor Wiederherstellung"


@dataclass
class Kandidat:
    pfad: Path
    zeitpunkt: datetime
    art: str
    groesse: int


# ── Kandidaten (Schritt 2/3) ────────────────────────────────────────────────────────────────
def _zeit_aus_name(name: str) -> datetime | None:
    treffer = _AUTO_RE.match(name)
    try:
        if treffer:
            return datetime(*(int(g) for g in treffer.groups()))
        treffer = _MANUELL_ZEIT_RE.search(name)
        if treffer:
            return datetime.strptime(treffer.group(1) + treffer.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return None


def _kandidat(pfad: Path, art: str | None = None) -> Kandidat | None:
    try:
        if not pfad.is_file():
            return None
        info = pfad.stat()
    except OSError:
        return None
    zeit = _zeit_aus_name(pfad.name) or datetime.fromtimestamp(info.st_mtime)
    if art is None:
        art = ART_VORHER if VOR_WIEDERHERSTELLUNG in pfad.name else ART_MANUELL
    return Kandidat(pfad, zeit, art, info.st_size)


def _nur_datenbank_im_zip(pfad: Path) -> bool:
    try:
        with zipfile.ZipFile(pfad) as zf:
            return zf.namelist() == [DB_NAME]
    except (zipfile.BadZipFile, OSError):
        return False


def _kandidaten_sammeln(data_dir: Path) -> list[Kandidat]:
    """Automatische Sicherungen (ZIP) plus alles, was direkt in data/backups liegt. Nicht
    aufgenommen: data/updates (dafuer gibt es `update --zurueck`), Papierkorb, Zwischendateien,
    Punktdateien, Unterordner."""
    gefunden: list[Kandidat] = []
    auto = data_dir / "backups" / "auto"
    if auto.is_dir():
        for p in auto.iterdir():
            if _AUTO_RE.match(p.name):
                k = _kandidat(p, ART_AUTO)
                if k:
                    gefunden.append(k)
    direkt = data_dir / "backups"
    if direkt.is_dir():
        for p in direkt.iterdir():
            if p.name.startswith(".") or p.suffix.lower() not in (".sqlite", ".zip"):
                continue
            # P2-66 Abnahme: ZIPs direkt in data/backups koennen auch Ordner-Sicherungen anderer
            # Werkzeuge sein (z. B. vor einer Umbenennung) -- nur ZIPs mit genau der Datenbank
            # gehoeren in die Liste.
            if p.suffix.lower() == ".zip" and not _nur_datenbank_im_zip(p):
                continue
            k = _kandidat(p)
            if k:
                gefunden.append(k)
    gefunden.sort(key=lambda k: (k.zeitpunkt, k.pfad.name), reverse=True)
    return gefunden


def _datum_text(zeit: datetime) -> str:
    return zeit.strftime("%d.%m.%Y %H:%M")


def _liste_ausgeben(kandidaten: list[Kandidat]) -> None:
    print("Verfügbare Sicherungen (neueste zuerst):")
    for nr, k in enumerate(kandidaten, start=1):
        print(f"  {nr:>2}. {_datum_text(k.zeitpunkt)}  {k.art:<24} {k.groesse / 1_000_000:.1f} MB  "
              f"({k.pfad.name})")


# ── Auswahl (Schritt 4) ─────────────────────────────────────────────────────────────────────
def _auswaehlen(kandidaten: list[Kandidat], datei: str | None) -> Kandidat:
    if datei:
        for k in kandidaten:
            if k.pfad.name == datei:
                return k
        raise Abbruch(f"Die Sicherung „{datei}“ wurde nicht gefunden. Mit --liste sehen Sie, "
                       f"welche Sicherungen vorhanden sind.")
    for versuch in range(2):
        print("Nummer der Sicherung (Enter = abbrechen): ", end="")
        try:
            eingabe = input().strip()
        except EOFError:
            eingabe = ""
        if not eingabe:
            raise Abbruch("Abgebrochen. Es wurde nichts geändert.")
        if eingabe.isdigit() and 1 <= int(eingabe) <= len(kandidaten):
            return kandidaten[int(eingabe) - 1]
        if versuch == 0:
            print(f"Bitte eine Zahl zwischen 1 und {len(kandidaten)} eingeben.")
    raise Abbruch("Keine gültige Auswahl. Abgebrochen, es wurde nichts geändert.")


# ── Kandidat pruefen (Schritt 5) ────────────────────────────────────────────────────────────
def _db_pruefen(db: Path) -> None:
    """Header, integrity_check, Tabelle `job`. Wirft Abbruch mit Grund."""
    try:
        with db.open("rb") as f:
            kopf = f.read(len(SQLITE_KOPF))
    except OSError as exc:
        raise Abbruch(f"Die Sicherung lässt sich nicht lesen: {exc}") from exc
    if kopf != SQLITE_KOPF:
        raise Abbruch("Die Datei ist keine BMS-Sicherung (keine gültige Datenbank).")
    try:
        conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            ergebnis = [z[0] for z in conn.execute("PRAGMA integrity_check")]
            if ergebnis != ["ok"]:
                raise Abbruch("Die Sicherung ist beschädigt (Integritätsprüfung nicht bestanden). "
                               "Bitte wählen Sie eine andere.")
            hat_job = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='job'").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise Abbruch(f"Die Sicherung ist keine lesbare Datenbank: {exc}") from exc
    if not hat_job:
        raise Abbruch("Die Datei ist keine BMS-Sicherung (die Stellen-Tabelle fehlt).")


def _kandidat_vorbereiten(kandidat: Kandidat, arbeitsordner: Path, installation: Path) -> Path:
    """Kandidat als einfache SQLite-Datei nach `arbeitsordner/bewerbung.sqlite` bringen und
    pruefen. An `data/` wird dabei nichts geaendert."""
    ziel = arbeitsordner / DB_NAME
    quelle = kandidat.pfad
    if quelle.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(quelle) as zf:
                namen = zf.namelist()
                if any(bms_update._pfad_unsicher(n) for n in namen):
                    raise Abbruch("Die Datei ist keine BMS-Sicherung (unzulässiger Pfad im Archiv).")
                if namen != [DB_NAME]:
                    raise Abbruch("Die Datei ist keine BMS-Sicherung (das Archiv enthält nicht "
                                   "genau die Datenbank).")
                with zf.open(DB_NAME) as src, ziel.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        except (zipfile.BadZipFile, OSError, EOFError, zipfile.LargeZipFile) as exc:
            raise Abbruch(f"Die Sicherung lässt sich nicht entpacken ({exc}). Bitte wählen Sie "
                           f"eine andere.") from exc
    else:
        try:
            shutil.copyfile(quelle, ziel)
        except OSError as exc:
            raise Abbruch(f"Die Sicherung lässt sich nicht lesen: {exc}") from exc
    _db_pruefen(ziel)
    # Selbsttest auf einer Kopie (bms_update legt sie selbst an): migriert eine aeltere
    # Datenbank additiv wie beim Serverstart und zeigt, ob diese Programmversion sie oeffnen kann.
    try:
        bms_update._selbsttest_ausfuehren(installation, arbeitsordner)
    except bms_update.Fehlgeschlagen as exc:
        raise Abbruch("Die Sicherung lässt sich mit dieser Programmversion nicht öffnen:\n"
                       f"{exc.nachricht}") from exc
    return ziel


# ── Aktuellen Stand sichern (Schritt 7) ─────────────────────────────────────────────────────
def _vorher_sichern(data_dir: Path, jetzt: datetime) -> Path | None:
    live = data_dir / DB_NAME
    if not live.is_file():
        print("Hinweis: Es gibt noch keine aktuelle Datenbank, daher entfällt die Sicherung "
              "des aktuellen Stands.")
        return None
    ordner = data_dir / "backups"
    ordner.mkdir(parents=True, exist_ok=True)
    basis = f"bewerbung_backup_{jetzt.strftime('%Y%m%d_%H%M%S')}{VOR_WIEDERHERSTELLUNG}"
    ziel, zaehler = ordner / f"{basis}.sqlite", 2
    while ziel.exists():
        ziel = ordner / f"{basis}_{zaehler}.sqlite"
        zaehler += 1
    zwischen = ordner / f".{ziel.name}.part"
    try:
        quelle_conn = sqlite3.connect(live.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            ziel_conn = sqlite3.connect(str(zwischen))
            try:
                quelle_conn.backup(ziel_conn)
            finally:
                ziel_conn.close()
        finally:
            quelle_conn.close()
        pruef = sqlite3.connect(str(zwischen))
        try:
            if [z[0] for z in pruef.execute("PRAGMA integrity_check")] != ["ok"]:
                raise sqlite3.DatabaseError("Integritätsprüfung der Kopie nicht bestanden")
        finally:
            pruef.close()
        os.replace(zwischen, ziel)
    except (sqlite3.Error, OSError) as exc:
        zwischen.unlink(missing_ok=True)
        raise Abbruch(f"Der aktuelle Stand konnte nicht gesichert werden ({exc}). Es wurde "
                       f"nichts geändert.") from exc
    return ziel


# ── Einsetzen (Schritt 8) ───────────────────────────────────────────────────────────────────
def _live_aus_datei_ersetzen(data_dir: Path, quelle: Path) -> None:
    tmp = data_dir / ".bewerbung.sqlite.wiederherstellung.tmp"
    try:
        shutil.copyfile(quelle, tmp)
        os.replace(tmp, data_dir / DB_NAME)
    finally:
        tmp.unlink(missing_ok=True)


def _einsetzen(data_dir: Path, db_neu: Path, sicherung_vorher: Path | None,
               jetzt: datetime) -> None:
    """Wirft OSError/sqlite3.Error bei Misserfolg -- vorher ist der Ausgangszustand schon
    wiederhergestellt (Aufrufer meldet Exit 2)."""
    live = data_dir / DB_NAME
    tmp = data_dir / ".bewerbung.sqlite.wiederherstellung.tmp"
    umbenannt: list[tuple[Path, Path]] = []
    ersetzt = False
    try:
        shutil.copyfile(db_neu, tmp)
        # WAL ist im BMS aus. Liegen trotzdem Reste daneben, wuerden sie zur alten Datenbank
        # gehoeren: mit Zeitstempel beiseite legen, nicht loeschen.
        stempel = jetzt.strftime("%Y%m%d_%H%M%S")
        for endung in ("-wal", "-shm"):
            rest = data_dir / (DB_NAME + endung)
            if rest.exists():
                neu = data_dir / f"{DB_NAME}{endung}.vor_wiederherstellung_{stempel}"
                os.replace(rest, neu)
                umbenannt.append((rest, neu))
        os.replace(tmp, live)
        ersetzt = True
        _db_pruefen(live)
    except (OSError, sqlite3.Error, Abbruch):
        tmp.unlink(missing_ok=True)
        for alt, neu in umbenannt:
            try:
                os.replace(neu, alt)
            except OSError:
                pass
        if ersetzt and sicherung_vorher is not None:
            _live_aus_datei_ersetzen(data_dir, sicherung_vorher)
        raise


# ── Protokoll (Schritt 9) ───────────────────────────────────────────────────────────────────
def _protokoll_schreiben(data_dir: Path, jetzt: datetime, kandidat: Kandidat,
                         sicherung_vorher: Path | None, ergebnis: str) -> None:
    try:
        ordner = data_dir / "backups"
        ordner.mkdir(parents=True, exist_ok=True)
        basis = f"wiederherstellung_{jetzt.strftime('%Y%m%d_%H%M%S')}"
        ziel, zaehler = ordner / f"{basis}.json", 2
        while ziel.exists():  # zwei Laeufe in derselben Sekunde: kein Protokoll ueberschreiben
            ziel = ordner / f"{basis}_{zaehler}.json"
            zaehler += 1
        ziel.write_text(json.dumps({
            "zeitpunkt": jetzt.isoformat(timespec="seconds"),
            "quelle": kandidat.pfad.name,
            "quelle_zeitpunkt": kandidat.zeitpunkt.isoformat(timespec="seconds"),
            "sicherung_vorher": sicherung_vorher.name if sicherung_vorher else None,
            "ergebnis": ergebnis,
        }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    except OSError:
        print("Hinweis: Das Protokoll konnte nicht geschrieben werden.")


# ── Ablauf ──────────────────────────────────────────────────────────────────────────────────
def _ausfuehren(args) -> int:
    installation = Path(args.installation)
    if not installation.is_dir():
        raise Abbruch(f"Der Ordner „{installation}“ wurde nicht gefunden.")
    data_dir = bms_update._data_dir(installation)

    # 1. Server und Sperre
    if bms_update._server_laeuft():
        raise Abbruch("Das BMS läuft noch. Beenden Sie es zuerst mit stop.command (Mac) bzw. "
                       "stop_windows.bat (Windows) und starten Sie dieses Werkzeug dann erneut.")
    if not data_dir.is_dir():
        raise Abbruch("Es wurde noch kein Datenordner gefunden. Hier gibt es nichts "
                       "wiederherzustellen.")

    lock = None
    if not args.liste:
        try:
            lock = bms_update._sperren(data_dir)
        except Abbruch as exc:
            raise Abbruch("Es läuft bereits ein Update oder eine Wiederherstellung, oder ein "
                           "vorheriger Lauf wurde nicht sauber beendet. Wenn Sie sicher sind, "
                           "dass nichts läuft, löschen Sie die Datei „"
                           f"{data_dir / 'updates' / bms_update.SPERR_NAME}“ und versuchen Sie es "
                           "erneut.") from exc
    try:
        # 2./3. Kandidaten und Liste
        kandidaten = _kandidaten_sammeln(data_dir)
        if not kandidaten:
            raise Abbruch("Es wurden keine Sicherungen gefunden (weder automatische noch "
                           "manuelle). Es wurde nichts geändert.")
        _liste_ausgeben(kandidaten)
        if args.liste:
            return EXIT_OK

        # 4. Auswahl
        kandidat = _auswaehlen(kandidaten, args.datei)

        # 5. Pruefen (nur in einem Temp-Ordner, data/ bleibt unberuehrt)
        print(f"\nDie Sicherung vom {_datum_text(kandidat.zeitpunkt)} wird geprüft ...")
        with tempfile.TemporaryDirectory(prefix="bms_wiederherstellen_") as tmp:
            arbeit = Path(tmp)
            db_neu = _kandidat_vorbereiten(kandidat, arbeit, installation)

            # 6. Rueckfrage
            print(f"\nGewählt: {kandidat.art} vom {_datum_text(kandidat.zeitpunkt)} "
                  f"({kandidat.pfad.name}).")
            print("Alles, was Sie seit diesem Zeitpunkt im BMS erfasst oder geändert haben, ist "
                  "danach nicht mehr in der Datenbank. Ihr aktueller Stand wird vorher gesichert "
                  "und lässt sich mit diesem Werkzeug zurückholen.")
            print("Dokumente in outputs und data bleiben unverändert. Dateien, die nach der "
                  "Sicherung entstanden sind, sind danach nicht mehr mit einer Stelle verknüpft.")
            if not args.ja and not bms_update._rueckfrage("\nSicherung jetzt einspielen? (j/n): "):
                raise Abbruch("Abgebrochen. Es wurde nichts geändert.")

            # 7. Aktuellen Stand sichern
            jetzt = datetime.now()
            vorher = _vorher_sichern(data_dir, jetzt)
            if vorher:
                print(f"Aktueller Stand gesichert als {vorher.name}.")

            # 8. Einsetzen
            try:
                _einsetzen(data_dir, db_neu, vorher, jetzt)
            except (OSError, sqlite3.Error, Abbruch) as exc:
                _protokoll_schreiben(data_dir, jetzt, kandidat, vorher, "fehlgeschlagen")
                print(f"Fehler beim Einsetzen: {getattr(exc, 'nachricht', exc)}\n"
                      "Der ursprüngliche Stand wurde wiederhergestellt. Sie können das BMS wie "
                      "gewohnt starten.")
                return EXIT_ZURUECKGEROLLT

        # 9./10. Protokoll und Abschluss
        _protokoll_schreiben(data_dir, jetzt, kandidat, vorher, "ok")
        print(f"\nFertig. Die Datenbank steht jetzt auf dem Stand vom "
              f"{_datum_text(kandidat.zeitpunkt)}. Starten Sie das BMS wie gewohnt.")
        if vorher:
            print("Zurücknehmen können Sie das so: Starten Sie dieses Werkzeug noch einmal und "
                  f"wählen Sie den Eintrag „{ART_VORHER}“ ({vorher.name}).")
        return EXIT_OK
    finally:
        if lock is not None:
            bms_update._entsperren(lock)


def _parser() -> bms_update._Parser:
    p = bms_update._Parser(
        prog="bms_wiederherstellen.py",
        description="Spielt eine Sicherung der BMS-Datenbank zurück (bei beendetem BMS).")
    p.add_argument("--installation", required=True, help="Programmordner der Installation.")
    p.add_argument("--liste", action="store_true",
                    help="Nur die vorhandenen Sicherungen anzeigen, nichts ändern.")
    p.add_argument("--datei", default=None,
                    help="Dateiname der Sicherung (statt Auswahl per Nummer).")
    p.add_argument("--ja", action="store_true",
                    help="Rückfrage vor dem Einspielen automatisch bestätigen.")
    return p


def main(argv: list[str] | None = None) -> int:
    argv_wirksam = list(sys.argv[1:]) if argv is None else list(argv)
    try:
        args = _parser().parse_args(argv_wirksam)
    except bms_update._ArgparseFehler as exc:
        print(f"Fehler: {exc}")
        return EXIT_AUFRUF_FALSCH
    try:
        return _ausfuehren(args)
    except Abbruch as exc:
        print(exc.nachricht)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
