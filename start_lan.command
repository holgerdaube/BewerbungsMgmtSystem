#!/bin/zsh
# Bewerbungs-Management-System im WLAN starten (für Handy/Tablet im selben Netz).
# ACHTUNG: keine Authentifizierung — nur im eigenen, vertrauten WLAN nutzen.
cd "$(dirname "$0")/backend"
VENV="$HOME/.bewerbung_mgmt_venv/bin/python"

# Terminal-Sprache (P2-95): BMS_TERMINAL_SPRACHE (de/en) gewinnt, sonst die Systemsprache
# (macOS, dann LC_ALL/LC_MESSAGES/LANG). Beginnt der Wert mit "de", gilt Deutsch, sonst Englisch.
# Export, damit die Python-Werkzeuge dieselbe Sprache nehmen.
_bms_lang="${BMS_TERMINAL_SPRACHE:-}"
[ -z "$_bms_lang" ] && _bms_lang=$(defaults read -g AppleLanguages 2>/dev/null | sed -n 's/^[ ]*"\{0,1\}\([A-Za-z][-A-Za-z_]*\).*/\1/p' | head -n 1)
[ -z "$_bms_lang" ] && _bms_lang=$(defaults read -g AppleLocale 2>/dev/null)
[ -z "$_bms_lang" ] && _bms_lang="${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}"
case "$_bms_lang" in
  de*|De*|DE*) BMS_TERMINAL_SPRACHE=de ;;
  *) BMS_TERMINAL_SPRACHE=en ;;
esac
export BMS_TERMINAL_SPRACHE

if [ ! -x "$VENV" ]; then
  if [ "$BMS_TERMINAL_SPRACHE" = de ]; then
    echo "Fehler: venv nicht gefunden unter $HOME/.bewerbung_mgmt_venv"
    echo "Setup siehe README.de.md."
  else
    echo "Error: venv not found at $HOME/.bewerbung_mgmt_venv"
    echo "Setup: see README.md."
  fi
  exit 1
fi

IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "<Mac-IP>")
NAME=$(scutil --get LocalHostName 2>/dev/null || echo "mac")
if [ "$BMS_TERMINAL_SPRACHE" = de ]; then
  echo "Starte im WLAN-Modus (Beenden: Ctrl+C)"
  echo "  am Mac:    http://localhost:8000"
  echo "  am Handy:  http://${NAME}.local:8000   oder   http://${IP}:8000"
else
  echo "Starting in Wi-Fi mode (stop: Ctrl+C)"
  echo "  on this Mac:  http://localhost:8000"
  echo "  on your phone:  http://${NAME}.local:8000   or   http://${IP}:8000"
fi
( sleep 2; open "http://localhost:8000" ) &
HOST=0.0.0.0 PORT=8000 "$VENV" run_server.py
