#!/bin/zsh
# Export ins oeffentliche Repo bequem vom Projekt-Root aufrufen (P2-83, Paket E) -- reicht alle
# Argumente 1:1 an `python -m pipeline.veroeffentlichung` durch (Muster scripts/kundenpaket.sh:
# venv-Python, cd backend, Projekt-Root-tauglich unabhaengig vom Aufruf-Verzeichnis,
# Leerzeichen-Pfad-sicher).
#
#   veroeffentlichen.sh --ziel <Ordner> [--ref <Commit>] [--pruefen]
#
# --ziel ORDNER:  lokale Arbeitskopie des oeffentlichen Repos (eigenes .git, origin zeigt auf das
#                 oeffentliche Repo, keine ungesicherten Aenderungen). Ein relativer Pfad gilt ab dem
#                 Ordner, in dem dieses Skript aufgerufen wurde.
# --ref COMMIT:   exportierter Commit (Vorgabe HEAD); muss in main enthalten sein.
# --pruefen:      nur pruefen (Personendaten und Geheimnisse), nichts schreiben; --ziel entfaellt.
#
# Das Werkzeug committet, taggt und pusht NIE. Es bricht ab, wenn Profil (config/profil.md) oder
# Datenbank (BMS_DATA_DIR bzw. data/bewerbung.sqlite) fehlen: ohne sie laesst sich nicht pruefen,
# ob persoenliche Daten im Export stehen. Die optionale Musterdatei liegt in
# ~/.bewerbung_mgmt_secrets/pruefmuster.txt.
# Exit-Codes: 0 in Ordnung, 1 Funde, 2 Abbruch (Voraussetzung fehlt), 3 Aufruf falsch.
# Entwicklungswerkzeug: kommt nicht ins Kundenpaket.
set -e
BACKEND="$(cd "$(dirname "$0")/../backend" && pwd)"
VENV="$HOME/.bewerbung_mgmt_venv/bin/python"
if [ ! -x "$VENV" ]; then
    echo "Abbruch: Das Python-venv fehlt ($VENV)." >&2
    exit 2
fi
export BMS_AUFRUFORDNER="$PWD"
cd "$BACKEND"
"$VENV" -m pipeline.veroeffentlichung "$@"
