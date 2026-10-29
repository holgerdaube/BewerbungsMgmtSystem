"""API-Router „Version" (P2-51, V5; P2-82, Vertrag A) — Versions-/Update-Auskunft für die
Einstellungen-Seite.

Eigener `APIRouter` statt einer neuen `@app.*`-Route direkt in `main.py` (wie `routes_sicherung.py`
und `routes_doku.py`): `main.py` bekommt nur Import + `include_router`. Alle Logik liegt in
`app/version.py` (installierte Fassung) und `app/update_pruefen.py` (Nachfrage bei GitHub-Releases),
dieser Router ist bewusst dünn.
"""
from fastapi import APIRouter

from app.update_pruefen import neueste_version
from app.version import version_info

router = APIRouter(prefix="/api", tags=["version"])


@router.get("/version")
def get_version():
    return version_info()


@router.get("/version/neueste")
def get_neueste_version():
    """P2-82 (Vertrag A): fragt auf Knopfdruck bei GitHub-Releases nach der neuesten Version und
    vergleicht sie mit der installierten. Antwortet immer 200; ein Fehler steht als Kundentext im
    Feld `fehler` (Format: s. `app/update_pruefen.py`). Reine GET-Route ohne Speicherung. Die
    Herkunftsprüfung betrifft nur schreibende Methoden, die Route hängt an keiner Sperre. Die Route
    ist absichtlich `def` (nicht `async`): Der Abruf blockiert bis zu 10 s und läuft so im
    Threadpool statt im Ereignis-Loop."""
    return neueste_version(version_info().get("version"))
