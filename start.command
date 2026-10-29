#!/bin/zsh
# Bewerbungs-Management-System starten (Doppelklick oder: ./start.command)
# Öffnet die App im Browser und startet den lokalen Server.
cd "$(dirname "$0")/backend"
VENV="$HOME/.bewerbung_mgmt_venv/bin/python"

if [ ! -x "$VENV" ]; then
  echo "Fehler: venv nicht gefunden unter $HOME/.bewerbung_mgmt_venv"
  echo "Setup siehe README.md."
  exit 1
fi

( sleep 2; open "http://localhost:8000" ) &
echo "Starte Bewerbungs-Management auf http://localhost:8000  (Beenden: Ctrl+C)"
PORT=8000 "$VENV" run_server.py
