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
  cd "$_SKRIPT_ORDNER" || { echo "Fehler: Der Programmordner wurde nicht gefunden."; return 1; }

  VENV="$HOME/.bewerbung_mgmt_venv/bin/python"
  if [ ! -x "$VENV" ]; then
    echo "Fehler: Die Python-Umgebung wurde nicht gefunden unter $HOME/.bewerbung_mgmt_venv"
    echo "Bitte zuerst die Einrichtung aus BMS_Install_MAC.md abschließen."
    return 1
  fi

  "$VENV" scripts/bms_update.py --installation "$PWD" "$@"
  # NICHT "status" nennen: zsh belegt "$status" bereits fest als Synonym fuer "$?" (schreibgeschuetzt,
  # ein Zuweisungsversuch bricht mit "read-only variable: status" ab -- empirisch geprueft).
  ergebnis=$?

  if [ $# -eq 0 ]; then
    echo
    echo -n "Zum Schließen Enter drücken "
    read -r _wartend
  fi
  return $ergebnis
}

main "$@"; exit $?
