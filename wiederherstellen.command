#!/bin/zsh
# Sicherung der Datenbank zurückspielen (Doppelklick oder: ./wiederherstellen.command [Optionen])
# Das BMS muss vorher beendet sein (stop.command). Die eigentliche Arbeit macht
# scripts/bms_wiederherstellen.py (P2-66), dieses Skript reicht nur den Programmordner durch.
#
# Den eigenen Ordner VOR der Funktion ermitteln: innerhalb einer zsh-Funktion ist "$0" der Name
# der Funktion ("main"), nicht der Skriptpfad (gleiches Muster wie update.command). ":A" macht
# daraus einen absoluten, symlink-aufgeloesten Pfad, ":h" liefert dessen Ordner.
_SKRIPT_ORDNER="${0:A:h}"

# ALLES WEITERE in einer Funktion, aufgerufen erst in der LETZTEN Zeile: zsh liest ein laufendes
# Skript waehrend der Ausfuehrung nach, und ein Update kann genau DIESE Datei ersetzen. Eine
# Funktion wird beim Aufruf einmal vollstaendig eingelesen (gleiches Muster wie update.command).
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

  "$VENV" scripts/bms_wiederherstellen.py --installation "$PWD" "$@"
  # NICHT "status" nennen: zsh belegt "$status" fest als Synonym fuer "$?" (schreibgeschuetzt).
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
