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

PORT="${PORT:-8000}"
FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

lauscher() { lsof -ti ":$PORT" -sTCP:LISTEN 2>/dev/null }

PIDS=$(lauscher)
if [ -z "$PIDS" ]; then
  if [ "$BMS_TERMINAL_SPRACHE" = de ]; then
    echo "Auf Port $PORT läuft nichts — das Bewerbungs-Management ist bereits beendet."
  else
    echo "Nothing is running on port $PORT — BMS has already stopped."
  fi
  exit 0
fi

if [ "$BMS_TERMINAL_SPRACHE" = de ]; then
  echo "Bewerbungs-Management läuft auf Port $PORT (Prozess: $(echo $PIDS | tr '\n' ' '))"
else
  echo "BMS is running on port $PORT (process: $(echo $PIDS | tr '\n' ' '))"
fi

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
  if [ "$BMS_TERMINAL_SPRACHE" = de ]; then
    echo "⚠️  Es laufen gerade $ANZAHL Agent-Lauf/Läufe:"
  else
    echo "⚠️  $ANZAHL agent run(s) are currently active:"
  fi
  printf '%s' "$ANTWORT" | grep -o '"kind": *"[^"]*"' | cut -d'"' -f4 | sort | uniq -c | sed 's/^/     /'
  echo
  if [ "$BMS_TERMINAL_SPRACHE" = de ]; then
    echo "   Beenden bricht sie ab. Skill-Läufe (eigener Prozess) lassen sich später neu starten,"
    echo "   eine laufende Beirats-Debatte ist verloren — sie läuft im Server selbst."
  else
    echo "   Stopping aborts them. Skill runs (separate process) can be restarted later,"
    echo "   a running Advisory Board debate is lost — it runs inside the server itself."
  fi
  if [ "$FORCE" -eq 1 ]; then
    if [ "$BMS_TERMINAL_SPRACHE" = de ]; then
      echo "   --force gesetzt: wird trotzdem beendet."
    else
      echo "   --force set: stopping anyway."
    fi
  elif [ -t 0 ]; then
    if [ "$BMS_TERMINAL_SPRACHE" = de ]; then
      echo -n "   Trotzdem beenden? [j/N] "
    else
      echo -n "   Stop anyway? [y/N] "
    fi
    read -r ANTWORT_USER
    case "$ANTWORT_USER" in
      j|J|y|Y) ;;
      *)
        if [ "$BMS_TERMINAL_SPRACHE" = de ]; then
          echo "Abgebrochen — nichts verändert."
        else
          echo "Cancelled — nothing changed."
        fi
        exit 1 ;;
    esac
  else
    if [ "$BMS_TERMINAL_SPRACHE" = de ]; then
      echo "Abgebrochen — nichts verändert. (Mit --force trotzdem beenden.)"
    else
      echo "Cancelled — nothing changed. (Use --force to stop anyway.)"
    fi
    exit 1
  fi
fi

# ── Freundlich beenden ───────────────────────────────────────────────────────────────────
if [ "$BMS_TERMINAL_SPRACHE" = de ]; then
  echo "Beende…"
else
  echo "Stopping…"
fi
echo $PIDS | xargs kill 2>/dev/null

# Bis zu 10 s auf den sauberen Abgang warten (uvicorn schließt Verbindungen und Log-Dateien).
for _ in $(seq 1 20); do
  [ -z "$(lauscher)" ] && break
  sleep 0.5
done

# ── Notfalls hart ────────────────────────────────────────────────────────────────────────
REST=$(lauscher)
if [ -n "$REST" ]; then
  if [ "$BMS_TERMINAL_SPRACHE" = de ]; then
    echo "Prozess reagiert nicht auf das normale Beenden — erzwinge das Ende (kill -9)."
  else
    echo "Process is not responding to the normal stop — forcing it to end (kill -9)."
  fi
  echo $REST | xargs kill -9 2>/dev/null
  sleep 1
fi

if [ -z "$(lauscher)" ]; then
  if [ "$BMS_TERMINAL_SPRACHE" = de ]; then
    echo "✓ Bewerbungs-Management beendet. Neu starten: start.command (oder start_lan.command)."
  else
    echo "✓ BMS stopped. To start it again: start.command (or start_lan.command)."
  fi
else
  if [ "$BMS_TERMINAL_SPRACHE" = de ]; then
    echo "✗ Port $PORT ist weiterhin belegt: $(lauscher | tr '\n' ' ')" >&2
    echo "  Prüfen mit: lsof -i :$PORT" >&2
  else
    echo "✗ Port $PORT is still in use: $(lauscher | tr '\n' ' ')" >&2
    echo "  Check with: lsof -i :$PORT" >&2
  fi
  exit 1
fi
