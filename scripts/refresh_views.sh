#!/bin/zsh
# Deterministischer Ansichten-Refresh (KEIN LLM): Excel-View + Tages-Digest neu bauen.
# Cron-/launchd-tauglich — braucht weder laufenden Server noch Claude-Session.
set -e
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
echo "Ansichten aktualisiert: $(date '+%Y-%m-%d %H:%M')"
