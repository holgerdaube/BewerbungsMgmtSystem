#!/usr/bin/env python3
"""Startet den Backend-Server unabhängig vom Arbeitsverzeichnis.

Python legt beim Ausführen eines Skripts dessen Ordner (backend/) auf sys.path[0],
daher funktioniert `from app.main import app` ohne --app-dir / cwd-Tricks.
Loop=asyncio + http=h11 vermeiden uvloop/httptools (im Sandbox-Preview nicht ladbar).
"""
import os
import sys

import uvicorn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.main import app  # noqa: E402

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    # Standard: nur localhost. Für Handy-Zugriff im eigenen WLAN bewusst freigeben:
    # HOST=0.0.0.0 PORT=8000 python run_server.py  (oder start_lan.command) — keine Auth, nur im vertrauten Netz!
    host = os.environ.get("HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port, loop="asyncio", http="h11", log_level="info")
