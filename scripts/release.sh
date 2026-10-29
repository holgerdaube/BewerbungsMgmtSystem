#!/bin/zsh
# Freigabe-Werkzeug bequem vom Projekt-Root aufrufen (P2-51) -- reicht alle Argumente 1:1 an
# `python -m pipeline.release` durch (gleiches Muster wie scripts/kundenpaket.sh: venv-Python,
# cd backend, Projekt-Root-tauglich unabhaengig vom Aufruf-Verzeichnis, Leerzeichen-Pfad-sicher).
#
# freigeben X.Y.Z|patch|minor|major [--probe] [--ohne-ci-pruefung]:  Version freigeben.
# notizen X.Y.Z:                                                     Release-Notizen zeigen.
# abholen X.Y.Z [--ziel DIR]:                                        Kundenpaket herunterladen.
set -e
BACKEND="$(cd "$(dirname "$0")/../backend" && pwd)"
VENV="$HOME/.bewerbung_mgmt_venv/bin/python"
cd "$BACKEND"
"$VENV" -m pipeline.release "$@"
