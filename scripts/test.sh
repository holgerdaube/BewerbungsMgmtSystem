#!/bin/zsh
# Backend-Testsuite (Phase 57 Stufe E1). Isolation gegen die Live-DB laeuft ueber
# backend/tests/conftest.py (BMS_DATA_DIR auf ein pytest-tmp-Verzeichnis) -- dieses Skript setzt
# dafuer NICHTS Zusaetzliches, es ruft nur pytest im richtigen Verzeichnis mit dem richtigen
# Interpreter auf. Projekt-Root-tauglich (funktioniert unabhaengig vom Aufruf-Verzeichnis) und
# Leerzeichen-Pfad-sicher (iCloud-Pfad "Bewerbung_Mgmt_System" enthaelt keine, aber der Pfad
# davor tut es -- durchgaengig gequotet).
set -e
BACKEND="$(cd "$(dirname "$0")/../backend" && pwd)"
VENV="$HOME/.bewerbung_mgmt_venv/bin/python"
cd "$BACKEND"
"$VENV" -m pytest tests/ -q "$@"
