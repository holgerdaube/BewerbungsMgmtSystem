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
  cd "$_SKRIPT_ORDNER" || { echo "Fehler: Der Programmordner wurde nicht gefunden."; return 1; }

  VENV="$HOME/.bewerbung_mgmt_venv/bin/python"
  if [ ! -x "$VENV" ]; then
    echo "Fehler: Die Python-Umgebung wurde nicht gefunden unter $HOME/.bewerbung_mgmt_venv"
    echo "Bitte zuerst die Einrichtung aus BMS_Install_MAC.md abschließen."
    return 1
  fi

  "$VENV" scripts/bms_wiederherstellen.py --installation "$PWD" "$@"
  # NICHT "status" nennen: zsh belegt "$status" fest als Synonym fuer "$?" (schreibgeschuetzt).
  ergebnis=$?

  if [ $# -eq 0 ]; then
    echo
    echo -n "Zum Schließen Enter drücken "
    read -r _wartend
  fi
  return $ergebnis
}

main "$@"; exit $?
