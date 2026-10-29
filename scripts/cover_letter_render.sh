#!/bin/zsh
# Deterministischer Anschreiben-Render (KEIN LLM): Klartext -> Brief-.docx + PDF (Phase 48 Stufe A).
set -e
BACKEND="$(cd "$(dirname "$0")/../backend" && pwd)"
VENV="$HOME/.bewerbung_mgmt_venv/bin/python"
cd "$BACKEND"
"$VENV" -m pipeline.cover_letter_render "$1"
