#!/bin/zsh
# Coach-Site aktualisieren (Phase 81) = Export + Deploy in einem Schritt.
# Läuft als local_cmd-AgentTask "coach-site" (Button in Einstellungen + Tageslauf-Ende) —
# deterministisch, KEIN LLM, 0 Kosten. Konfiguration kommt seit Phase 82 aus den Einstellungen
# (Shell-Kontrakt pipeline.coach_settings) statt aus coach_sftp.env. Ist die Funktion
# abgeschaltet, bricht dieser Schritt VOR dem Export ab (kein sinnloser Export ohne Ziel) und
# meldet das ehrlich mit Exit 0 — der Tageslauf bleibt grün (I4).
set -e
# P2-95: Sprache der Meldungen. Der Runner setzt BMS_TERMINAL_SPRACHE auf die Sprache der Oberfläche, weil die Ausgabe
# im Task-Center landet; von Hand gestartet folgt das Skript dem Betriebssystem.
if [ -z "${BMS_TERMINAL_SPRACHE:-}" ]; then
  _bms_lang=$({ defaults read -g AppleLanguages 2>/dev/null || true; } | sed -n '2p' | tr -d ' ",')
  [ -n "$_bms_lang" ] || _bms_lang=$(defaults read -g AppleLocale 2>/dev/null || true)
  [ -n "$_bms_lang" ] || _bms_lang="${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}"
  case "$_bms_lang" in
    de*|De*|DE*) BMS_TERMINAL_SPRACHE=de ;;
    *) BMS_TERMINAL_SPRACHE=en ;;
  esac
fi
_m() { if [ "$BMS_TERMINAL_SPRACHE" = "de" ]; then print -r -- "$1"; else print -r -- "$2"; fi; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$HOME/.bewerbung_mgmt_venv/bin/python"

# Gleicher Shell-Kontrakt wie coach_deploy.sh — hier interessiert uns nur COACH_AKTIV, den
# Rest liest coach_deploy.sh gleich noch einmal selbst (jedes Skript bleibt eigenständig
# aufrufbar, ohne sich Zustand über Umgebungsvariablen weiterreichen zu müssen).
eval "$(cd "$ROOT/backend" && "$VENV" -m pipeline.coach_settings shell)"
: "${COACH_AKTIV:=0}"
if [ "$COACH_AKTIV" != "1" ]; then
  _m "Coach-Site ist in den Einstellungen abgeschaltet — übersprungen." "The coach site is switched off in the settings, skipped."
  exit 0
fi

cd "$ROOT/backend"
"$VENV" -m pipeline.coach_export
exec "$ROOT/scripts/coach_deploy.sh"
