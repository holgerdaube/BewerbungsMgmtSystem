#!/bin/zsh
# Bewerbungs-Management-System aktualisieren (Doppelklick oder: ./update.command [Optionen])
# Spielt ein neues Programmpaket ein, ohne Daten oder Anpassungen zu verlieren. Die eigentliche
# Arbeit macht scripts/bms_update.py (P2-51), dieses Skript reicht nur den Programmordner durch.
#
# Den eigenen Ordner VOR der Funktion ermitteln: innerhalb einer zsh-Funktion ist "$0" NICHT der
# Skriptpfad, sondern der Name der Funktion selbst ("main") -- "$(dirname "$0")" dort waere immer
# "." und liesse das Skript im falschen Verzeichnis suchen (empirisch geprueft). Auf oberster
# Ebene, vor jeder Funktionsdefinition, bedeutet "$0" dagegen zuverlaessig den Aufrufpfad; ":A"
# macht daraus einen absoluten, symlink-aufgeloesten Pfad, ":h" liefert dessen Ordner.
_SKRIPT_ORDNER="${0:A:h}"

# ALLES WEITERE in einer Funktion, aufgerufen erst in der LETZTEN Zeile: zsh liest ein laufendes
# Skript waehrend der Ausfuehrung nach, sobald es eine neue Zeile braucht. Ein Update ersetzt aber
# genau DIESE Datei. Stuende der Code hier direkt (nicht in einer Funktion), koennte zsh nach dem
# Ersetzen die naechste Zeile schon aus der NEUEN Fassung lesen, mitten im Ablauf. Eine Funktion
# wird beim Aufruf einmal vollstaendig eingelesen, das Risiko entfaellt (gleiches Muster wie in
# stop.command mit dem Beenden-Ablauf).
main() {
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

  cd "$_SKRIPT_ORDNER" || {
    if [ "$BMS_TERMINAL_SPRACHE" = de ]; then
      echo "Fehler: Der Programmordner wurde nicht gefunden."
    else
      echo "Error: The program folder was not found."
    fi
    return 1
  }

  VENV="$HOME/.bewerbung_mgmt_venv/bin/python"
  if [ ! -x "$VENV" ]; then
    if [ "$BMS_TERMINAL_SPRACHE" = de ]; then
      echo "Fehler: Die Python-Umgebung wurde nicht gefunden unter $HOME/.bewerbung_mgmt_venv"
      echo "Bitte zuerst die Einrichtung aus BMS_Install_MAC.md abschließen."
    else
      echo "Error: The Python environment was not found at $HOME/.bewerbung_mgmt_venv"
      echo "Please complete the setup from BMS_Install_MAC.en.md first."
    fi
    return 1
  fi

  "$VENV" scripts/bms_update.py --installation "$PWD" "$@"
  # NICHT "status" nennen: zsh belegt "$status" bereits fest als Synonym fuer "$?" (schreibgeschuetzt,
  # ein Zuweisungsversuch bricht mit "read-only variable: status" ab -- empirisch geprueft).
  ergebnis=$?

  if [ $# -eq 0 ]; then
    echo
    if [ "$BMS_TERMINAL_SPRACHE" = de ]; then
      echo -n "Zum Schließen Enter drücken "
    else
      echo -n "Press Enter to close "
    fi
    read -r _wartend
  fi
  return $ergebnis
}

main "$@"; exit $?
