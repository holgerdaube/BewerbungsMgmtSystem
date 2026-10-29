#!/bin/zsh
# Drittanbieter-Lizenzen bequem vom Projekt-Root aufrufen (P2-77) -- reicht alle Argumente 1:1 an
# `python -m pipeline.drittlizenzen` durch (Muster scripts/docs_html.sh: venv-Python, cd backend,
# Projekt-Root-tauglich unabhaengig vom Aufruf-Verzeichnis, Leerzeichen-Pfad-sicher).
#
# Ohne Argumente:   erzeugt frontend/src/rechtliches/drittlizenzen.md und drittlizenzen_texte.txt
#                   aus den Lockfiles (braucht das venv und den Build-Spiegel, s. frontend/build.sh).
# --pruefen:        vergleicht nur (Exit 1, wenn eine Datei veraltet ist), schreibt NICHTS.
# --node-modules D: anderer Ordner als ~/.bewerbung_mgmt_node/frontend_build/node_modules.
# Entwicklungswerkzeug: kommt nicht ins Kundenpaket.
set -e
BACKEND="$(cd "$(dirname "$0")/../backend" && pwd)"
VENV="$HOME/.bewerbung_mgmt_venv/bin/python"
cd "$BACKEND"
"$VENV" -m pipeline.drittlizenzen "$@"
