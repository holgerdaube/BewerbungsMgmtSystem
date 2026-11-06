#!/bin/zsh
# Deterministischer Ansichten-Refresh (KEIN LLM): Excel-View + Tages-Digest neu bauen.
# Cron-/launchd-tauglich — braucht weder laufenden Server noch Claude-Session.
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

BACKEND="$(cd "$(dirname "$0")/../backend" && pwd)"
VENV="$HOME/.bewerbung_mgmt_venv/bin/python"
cd "$BACKEND"
"$VENV" -m pipeline.export_excel
"$VENV" -m pipeline.digest
"$VENV" -m pipeline.search_index rebuild
# Favicon in HTML-Berichte nachtragen, denen es fehlt (28.08.2026). Deterministisch und
# idempotent. Nötig, weil Skill-Läufe ihre Berichte direkt auf die Platte schreiben, an
# jedem Python-Code vorbei — ohne diesen Schritt trüge so ein Bericht beim Öffnen aus dem
# Finder kein Icon.
"$VENV" -m pipeline.favicon_nachruesten
_m "Ansichten aktualisiert: $(date '+%Y-%m-%d %H:%M')" "Views updated: $(date '+%Y-%m-%d %H:%M')"
