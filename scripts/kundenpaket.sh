#!/bin/zsh
# Kundenpaket-Bauer bequem vom Projekt-Root aufrufen (P2-50 Arbeitspaket A) -- reicht alle
# Argumente 1:1 an `python -m pipeline.kundenpaket` durch (Muster scripts/docs_html.sh:
# venv-Python, cd backend, Projekt-Root-tauglich unabhaengig vom Aufruf-Verzeichnis,
# Leerzeichen-Pfad-sicher).
#
# Ohne Argumente:   baut aus HEAD ein Kunden-ZIP nach outputs/kundenpaket/.
# --pruefen:        nur pruefen (Exit 1 bei Personendaten-Funden), schreibt kein ZIP.
# --arbeitsbaum:    Quelle ist der aktuelle Arbeitsbaum statt HEAD (Vorschau vor dem Commit).
# --ziel-ordner DIR: anderer Zielordner fuer das ZIP (P2-51: umbenannt von --ziel, s. Bau-Spec
#                    Paket U2a Punkt 2 -- release.yml ruft die Option unter diesem Namen auf).
# --ref REF:        andere Git-Revision (nur ohne --arbeitsbaum).
#
# Firmennamen-Regel (P2-51): laeuft automatisch mit, wenn unter BMS_DATA_DIR (sonst data/)
# eine bewerbung.sqlite liegt -- sonst uebersprungen, die Ausgabe sagt das.
set -e
BACKEND="$(cd "$(dirname "$0")/../backend" && pwd)"
VENV="$HOME/.bewerbung_mgmt_venv/bin/python"
cd "$BACKEND"
"$VENV" -m pipeline.kundenpaket "$@"
