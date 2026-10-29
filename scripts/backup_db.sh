#!/bin/bash
# scripts/backup_db.sh — Backup der Live-DB (I6-Konvention) + optionale Rotation.
#
# Legt IMMER zuerst ein frisches Backup an:
#   data/backups/bewerbung_backup_<JJJJMMTT_HHMMSS>[_<label>][_<N>].sqlite
#
# Usage:
#   scripts/backup_db.sh                    Nur Backup anlegen.
#   scripts/backup_db.sh --label vor_x       Backup mit Suffix (I6: "_vor_<schritt>").
#   scripts/backup_db.sh --rotate            Backup + Rotations-Kandidaten AUFLISTEN (Dry-Run,
#                                             loescht nichts).
#   scripts/backup_db.sh --rotate --apply    Backup + Rotations-Kandidaten WIRKLICH loeschen.
#   scripts/backup_db.sh --rotate --keep 20  Andere Aufbewahrungsmenge als der Default (15).
#
# Rotation behaelt die N (Default 15) Backups mit der juengsten Aenderungszeit, alles Aeltere
# gilt als Kandidat. Default ist immer Dry-Run — geloescht wird nur mit explizitem --apply
# (s. tasks/lessons.md: "Backups nie automatisch loeschen"). Unveraendert seit Phase 68A (die
# Rotation entscheidet ausschliesslich ueber die Aenderungszeit, nie ueber Dateigroesse).
#
# Phase 68A (P3-2): Kopie ueber SQLites eigene Online-Backup-Mechanik (`.backup`-Dot-Command),
# NICHT mehr `cp`. `cp` liest byteweise ohne SQLites Sperrprotokoll -- laeuft es exakt waehrend
# eine Transaktion Seiten schreibt, kann die Kopie einen inkonsistenten Mix aus altem und neuem
# Stand enthalten. Der alte Kommentar rechtfertigte `cp` mit "read-safe bei ruhendem Server",
# aber genau das prueft das Skript nirgends -- und der Normalbetrieb ist ein durchgehend
# laufender Server. `.backup` nutzt SQLites Online-Backup-API und ist bei gleichzeitigen
# Schreibzugriffen konsistent, ganz ohne neue Abhaengigkeit: die sqlite3-CLI ist macOS-
# Systemstandard (/usr/bin/sqlite3) und wird bereits in README.md's eigenem Verifikations-
# Workflow genutzt ("sqlite3 data/bewerbung.sqlite 'PRAGMA integrity_check;'"). Bewusst
# `.backup`, nicht `VACUUM INTO`: empirisch gegen
# die echte DB geprueft (Phase 68A) liefert `.backup` eine bytegleiche Kopie (2797 Seiten wie
# das Original), waehrend `VACUUM INTO` hier WEGEN der FTS5-Volltextsuche (Tabelle `suchindex`)
# eine GROESSERE Datei erzeugt (2991 Seiten) -- das Gegenteil der ueblichen Annahme "VACUUM INTO
# ist kleiner". `.backup` haelt damit auch den Groessenvergleich fuer "belegt X MB"
# (agent_runner.py::_backup_hinweis, reine Anzeige, keine Entscheidungsgrundlage) konsistent zu
# den bisherigen cp-Backups.
#
# Phase 68A (P3-3): Zeitstempel jetzt sekundengenau (vorher nur Minute) UND zusaetzlich eine
# deterministische Kollisions-Pruefung mit Suffix (_2, _3, ... -- identisches Muster zu
# cleanup.py::_freier_name / beirat_engine.py::_freier_name). Sekunden senken nur die
# Wahrscheinlichkeit einer Kollision, die Suffix-Schleife schliesst sie aus: zwei Aufrufe
# innerhalb derselben Sekunde ueberschreiben sich nicht mehr lautlos.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DB_PATH="$PROJECT_ROOT/data/bewerbung.sqlite"
BACKUP_DIR="$PROJECT_ROOT/data/backups"

KEEP=15
ROTATE=0
APPLY=0
LABEL=""

usage() {
  echo "Usage: $0 [--label <text>] [--rotate [--apply] [--keep N]]"
  exit 1
}

while [ $# -gt 0 ]; do
  case "$1" in
    --rotate) ROTATE=1; shift ;;
    --apply) APPLY=1; shift ;;
    --keep) KEEP="$2"; shift 2 ;;
    --label) LABEL="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "Unbekannte Option: $1" >&2; usage ;;
  esac
done

if [ ! -f "$DB_PATH" ]; then
  echo "FEHLER: Live-DB nicht gefunden unter $DB_PATH" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

# LABEL auf ein Zeichen-Set beschraenken, das gefahrlos in einen Dateinamen UND in den
# sqlite3-Dot-Command (".backup '<pfad>'", s. u.) eingebettet werden kann -- schliesst
# nebenbei aus, dass ein Label mit "/" aus dem Backup-Ordner heraus schreiben koennte (bestand
# latent schon vorher, war aber nicht das eigentliche Ziel dieses Fixes).
if [ -n "$LABEL" ]; then
  LABEL="$(printf '%s' "$LABEL" | tr -c 'A-Za-z0-9_.-' '_')"
fi

TS="$(date +%Y%m%d_%H%M%S)"
if [ -n "$LABEL" ]; then
  BASE="bewerbung_backup_${TS}_${LABEL}"
else
  BASE="bewerbung_backup_${TS}"
fi
DEST="$BACKUP_DIR/${BASE}.sqlite"
if [ -e "$DEST" ]; then
  N=2
  while [ -e "$BACKUP_DIR/${BASE}_${N}.sqlite" ]; do
    N=$((N + 1))
  done
  DEST="$BACKUP_DIR/${BASE}_${N}.sqlite"
fi

sqlite3 "$DB_PATH" ".backup '$DEST'"
echo "Backup angelegt: data/backups/$(basename "$DEST")"

if [ "$ROTATE" -eq 0 ]; then
  if [ "$APPLY" -eq 1 ]; then
    echo "Hinweis: --apply hat ohne --rotate keine Wirkung." >&2
  fi
  exit 0
fi

# Alle Backups nach Aenderungszeit absteigend (neueste zuerst) sortieren. sed statt awk, damit
# Leerzeichen im Projektpfad (iCloud: "Mobile Documents") die Pfad-Spalte nicht zerreissen.
ALL_BACKUPS="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'bewerbung_backup_*.sqlite' \
  -exec stat -f '%m %N' {} \; | sort -rn | sed -E 's/^[0-9]+ //')"

TOTAL=0
if [ -n "$ALL_BACKUPS" ]; then
  TOTAL=$(printf '%s\n' "$ALL_BACKUPS" | wc -l | tr -d ' ')
fi

CANDIDATES=""
if [ "$TOTAL" -gt "$KEEP" ]; then
  CANDIDATES="$(printf '%s\n' "$ALL_BACKUPS" | tail -n +"$((KEEP + 1))")"
fi

CANDIDATE_COUNT=0
if [ -n "$CANDIDATES" ]; then
  CANDIDATE_COUNT=$(printf '%s\n' "$CANDIDATES" | wc -l | tr -d ' ')
fi

echo ""
echo "Rotation: $TOTAL Backup(s) gesamt, behalte die neuesten $KEEP, $CANDIDATE_COUNT Loesch-Kandidat(en)."

if [ "$CANDIDATE_COUNT" -eq 0 ]; then
  echo "Nichts zu tun."
  exit 0
fi

if [ "$APPLY" -eq 1 ]; then
  printf '%s\n' "$CANDIDATES" | while IFS= read -r f; do
    [ -z "$f" ] && continue
    echo "LOESCHE: $(basename "$f")"
    rm -f "$f"
  done
  echo "Rotation angewendet: $CANDIDATE_COUNT Datei(en) geloescht."
else
  echo "Dry-Run — folgende Dateien WUERDEN geloescht (fuer echtes Loeschen: --rotate --apply):"
  printf '%s\n' "$CANDIDATES" | while IFS= read -r f; do
    [ -z "$f" ] && continue
    echo "  $(basename "$f")"
  done
fi
