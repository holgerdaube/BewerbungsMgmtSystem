#!/bin/zsh
# Bewerbungs-Management-System beenden (Doppelklick oder: ./stop.command [--force])
# Gegenstück zu start.command / start_lan.command.
#
# Warum ein eigenes Skript und nicht einfach "kill"? Weil ein Stopp im falschen Moment Arbeit
# vernichtet: Der Server startet Skill-Läufe als Kindprozesse, und die Beirats-Debatten laufen
# sogar IM Server selbst (tasks/lessons.md, „Server-Neustart tötet In-Server-Läufe", 27.07.2026)
# — ein hartes Beenden lässt eine bereits bezahlte Debatte unwiederbringlich sterben. Dieses
# Skript prüft deshalb ZUERST, ob gerade etwas läuft, und fragt nach, bevor es zuschlägt.
#
# Ablauf: Port prüfen → laufende Läufe prüfen → freundlich beenden (SIGTERM) → notfalls hart.
set -u

PORT="${PORT:-8000}"
FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

lauscher() { lsof -ti ":$PORT" -sTCP:LISTEN 2>/dev/null }

PIDS=$(lauscher)
if [ -z "$PIDS" ]; then
  echo "Auf Port $PORT läuft nichts — das Bewerbungs-Management ist bereits beendet."
  exit 0
fi

echo "Bewerbungs-Management läuft auf Port $PORT (Prozess: $(echo $PIDS | tr '\n' ' '))"

# ── Laufende Agent-Läufe erkennen ────────────────────────────────────────────────────────
# Bewusst ohne jq (nicht überall installiert) und mit kurzem Timeout: Antwortet der Server
# nicht mehr, soll das Beenden trotzdem möglich sein — dann gilt „unbekannt", nicht „nichts".
# BEIDE Zustände zählen: `running` ist der Lauf, der gerade stirbt — `queued` sind die Schritte
# einer Kette, die danach nie mehr an die Reihe kämen (ein Tageslauf hat sieben davon, während
# Schritt eins läuft). Wer nur auf `running` schaut, hält einen Tageslauf für „fast nichts".
ANTWORT=""
for ZUSTAND in running queued; do
  TEIL=$(curl -s --max-time 3 "http://127.0.0.1:$PORT/api/tasks?status=$ZUSTAND&limit=50" 2>/dev/null)
  [ -n "$TEIL" ] && ANTWORT="$ANTWORT$TEIL"
done
if [ -n "$ANTWORT" ]; then
  ANZAHL=$(printf '%s' "$ANTWORT" | grep -o '"kind"' | wc -l | tr -d ' ')
else
  ANZAHL="?"
fi

if [ "$ANZAHL" != "0" ] && [ "$ANZAHL" != "?" ]; then
  echo
  echo "⚠️  Es laufen gerade $ANZAHL Agent-Lauf/Läufe:"
  printf '%s' "$ANTWORT" | grep -o '"kind": *"[^"]*"' | cut -d'"' -f4 | sort | uniq -c | sed 's/^/     /'
  echo
  echo "   Beenden bricht sie ab. Skill-Läufe (eigener Prozess) lassen sich später neu starten,"
  echo "   eine laufende Beirats-Debatte ist verloren — sie läuft im Server selbst."
  if [ "$FORCE" -eq 1 ]; then
    echo "   --force gesetzt: wird trotzdem beendet."
  elif [ -t 0 ]; then
    echo -n "   Trotzdem beenden? [j/N] "
    read -r ANTWORT_USER
    case "$ANTWORT_USER" in
      j|J|y|Y) ;;
      *) echo "Abgebrochen — nichts verändert."; exit 1 ;;
    esac
  else
    echo "Abgebrochen — nichts verändert. (Mit --force trotzdem beenden.)"
    exit 1
  fi
fi

# ── Freundlich beenden ───────────────────────────────────────────────────────────────────
echo "Beende…"
echo $PIDS | xargs kill 2>/dev/null

# Bis zu 10 s auf den sauberen Abgang warten (uvicorn schließt Verbindungen und Log-Dateien).
for _ in $(seq 1 20); do
  [ -z "$(lauscher)" ] && break
  sleep 0.5
done

# ── Notfalls hart ────────────────────────────────────────────────────────────────────────
REST=$(lauscher)
if [ -n "$REST" ]; then
  echo "Prozess reagiert nicht auf das normale Beenden — erzwinge das Ende (kill -9)."
  echo $REST | xargs kill -9 2>/dev/null
  sleep 1
fi

if [ -z "$(lauscher)" ]; then
  echo "✓ Bewerbungs-Management beendet. Neu starten: start.command (oder start_lan.command)."
else
  echo "✗ Port $PORT ist weiterhin belegt: $(lauscher | tr '\n' ' ')" >&2
  echo "  Prüfen mit: lsof -i :$PORT" >&2
  exit 1
fi
