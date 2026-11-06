"""API-Router „Beispieldaten“ (P2-59, Paket B) -- Status und Entfernen der Beispieldaten einer
frischen Kundeninstallation, für die Einstellungen-Seite und den Hinweis im Dashboard.

Eigener APIRouter statt neuer @app.*-Routen in main.py (Muster app/routes_sicherung.py). Die
Einbindung (`include_router`) und der Aufruf beim Start (`beispieldaten.einspielen_falls_neu`) gehören
der Hauptsession. Alle Logik liegt in app/beispieldaten.py, dieser Router übersetzt nur die
Ausnahmefälle in HTTP-Status und Klartext: Nichts zu entfernen, eine Sicherung läuft oder an einer
Beispielstelle arbeitet eine Aufgabe gibt 409, eine gescheiterte Sicherung 500 (dann bleibt alles
unverändert).
"""
from fastapi import APIRouter, HTTPException

from app import beispieldaten
from app.sprache import tx
from app.terminal import tt

router = APIRouter(prefix="/api", tags=["beispieldaten"])


@router.get("/beispieldaten")
def get_beispieldaten():
    return beispieldaten.status()


@router.post("/beispieldaten/entfernen")
def post_beispieldaten_entfernen():
    """Synchrone Route (läuft im Threadpool): erst die Sicherung, dann das Entfernen. Danach wird die
    abgeleitete Profil-Struktur neu geschrieben, denn Skills und Werdegang der Beispieldaten standen
    darin."""
    try:
        ergebnis = beispieldaten.entfernen()
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except Exception as exc:       # noqa: BLE001 -- der Nutzer bekommt den Grund als Klartext
        raise HTTPException(500, str(exc) or tx("Die Beispieldaten konnten nicht entfernt werden."))

    # Funktionslokal importiert: main.py bindet diesen Router ein, ein Import auf Modulebene wäre
    # zirkulär. Ein Fehler hier macht das Entfernen nicht ungeschehen, er wird nur protokolliert.
    try:
        from sqlmodel import Session

        from app import db
        from app.main import _profil_struktur_schreiben

        with Session(db.engine) as session:
            _profil_struktur_schreiben(session)
    except Exception as exc:       # noqa: BLE001
        print(tt("[beispieldaten] WARNUNG: Profil-Struktur nicht neu geschrieben: {fehler}", fehler=exc), flush=True)
    return ergebnis
