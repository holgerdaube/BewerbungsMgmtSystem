#!/bin/zsh
# Englische Fassungen prüfen oder bestätigen (P2-91), reicht alle Argumente an `python -m pipeline.uebersetzung` durch.
#
#   uebersetzung.sh --pruefen [--alle]
#   uebersetzung.sh --bestaetigen docs/en/ANLEITUNG.md
# Entwicklungswerkzeug: kommt nicht ins Kundenpaket.
set -e
BACKEND="$(cd "$(dirname "$0")/../backend" && pwd)"
VENV="$HOME/.bewerbung_mgmt_venv/bin/python"
cd "$BACKEND"
"$VENV" -m pipeline.uebersetzung "$@"
