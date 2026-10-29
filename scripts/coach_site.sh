#!/bin/zsh
# Coach-Site aktualisieren (Phase 81) = Export + Deploy in einem Schritt.
# Läuft als local_cmd-AgentTask "coach-site" (Button in Einstellungen + Tageslauf-Ende) —
# deterministisch, KEIN LLM, 0 Kosten. Konfiguration kommt seit Phase 82 aus den Einstellungen
# (Shell-Kontrakt pipeline.coach_settings) statt aus coach_sftp.env. Ist die Funktion
# abgeschaltet, bricht dieser Schritt VOR dem Export ab (kein sinnloser Export ohne Ziel) und
# meldet das ehrlich mit Exit 0 — der Tageslauf bleibt grün (I4).
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$HOME/.bewerbung_mgmt_venv/bin/python"

# Gleicher Shell-Kontrakt wie coach_deploy.sh — hier interessiert uns nur COACH_AKTIV, den
# Rest liest coach_deploy.sh gleich noch einmal selbst (jedes Skript bleibt eigenständig
# aufrufbar, ohne sich Zustand über Umgebungsvariablen weiterreichen zu müssen).
eval "$(cd "$ROOT/backend" && "$VENV" -m pipeline.coach_settings shell)"
: "${COACH_AKTIV:=0}"
if [ "$COACH_AKTIV" != "1" ]; then
  echo "Coach-Site ist in den Einstellungen abgeschaltet — übersprungen."
  exit 0
fi

cd "$ROOT/backend"
"$VENV" -m pipeline.coach_export
exec "$ROOT/scripts/coach_deploy.sh"
