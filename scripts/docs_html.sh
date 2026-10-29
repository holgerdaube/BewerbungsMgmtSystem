#!/bin/zsh
# Docs-Renderer bequem vom Projekt-Root aufrufen (Phase 83 Arbeitspaket D1) -- reicht alle
# Argumente 1:1 an `python -m pipeline.docs_render` durch (Muster scripts/test.sh: venv-Python,
# cd backend, Projekt-Root-tauglich unabhaengig vom Aufruf-Verzeichnis, Leerzeichen-Pfad-sicher).
#
# Ohne Argumente:        rendert ALLE docs/*.md -> gleichnamige .html.
# --pruefen:              prueft nur (Exit 1 bei fehlender/veralteter HTML), schreibt NICHTS.
# --datei docs/X.md:      nur eine einzelne Datei (kombinierbar mit --pruefen).
set -e
BACKEND="$(cd "$(dirname "$0")/../backend" && pwd)"
VENV="$HOME/.bewerbung_mgmt_venv/bin/python"
cd "$BACKEND"
"$VENV" -m pipeline.docs_render "$@"
