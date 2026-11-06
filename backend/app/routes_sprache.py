"""API-Router „Sprache" (P2-88): Sprache der Oberfläche lesen und setzen.

Eigener Endpunkt statt `PATCH /api/einstellungen`: Der schreibt bei jedem Aufruf `config/suchprofile.yaml`
neu, und das hat mit der Sprache nichts zu tun.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app import sprache
from app.db import get_session

router = APIRouter(prefix="/api", tags=["sprache"])


def _antwort() -> dict:
    return {"sprache": sprache.aktuell(), "gewaehlt": bool(sprache.gespeichert()), "angebot": list(sprache.SPRACHEN)}


@router.get("/sprache")
def get_sprache():
    return _antwort()


@router.put("/sprache")
def put_sprache(payload: dict, session: Session = Depends(get_session)):
    wert = payload.get("sprache")
    if wert not in sprache.SPRACHEN:
        raise HTTPException(422, sprache.tx("Die Sprache muss de oder en sein."))
    # Die Zeile entsteht erst beim ersten Zugriff und seedet aus der Suchprofil-Datei. Import erst hier:
    # `app.main` bindet diesen Router ein, oben im Modul wäre es ein Zirkelimport.
    from app.main import _einstellungen_singleton
    e = _einstellungen_singleton(session)
    e.sprache = wert
    e.updated_at = datetime.utcnow()
    session.add(e)
    session.commit()
    return _antwort()
