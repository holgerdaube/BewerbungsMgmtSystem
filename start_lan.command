#!/bin/zsh
# Bewerbungs-Management-System im WLAN starten (für Handy/Tablet im selben Netz).
# ACHTUNG: keine Authentifizierung — nur im eigenen, vertrauten WLAN nutzen.
cd "$(dirname "$0")/backend"
VENV="$HOME/.bewerbung_mgmt_venv/bin/python"

if [ ! -x "$VENV" ]; then
  echo "Fehler: venv nicht gefunden unter $HOME/.bewerbung_mgmt_venv"
  echo "Setup siehe README.md."
  exit 1
fi

IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "<Mac-IP>")
NAME=$(scutil --get LocalHostName 2>/dev/null || echo "mac")
echo "Starte im WLAN-Modus (Beenden: Ctrl+C)"
echo "  am Mac:    http://localhost:8000"
echo "  am Handy:  http://${NAME}.local:8000   oder   http://${IP}:8000"
( sleep 2; open "http://localhost:8000" ) &
HOST=0.0.0.0 PORT=8000 "$VENV" run_server.py
