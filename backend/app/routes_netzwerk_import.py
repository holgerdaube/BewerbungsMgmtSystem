"""API-Router „Netzwerk-Import“ (P2-62, Paket I) -- Vorlage, Vorschau und Import von Zielfirmen,
Headhunter und Netzwerk-Kontakten aus einer Datei, für die Seite Netzwerk.

Eigener APIRouter statt neuer @app.*-Routen in main.py (Muster app/routes_beispieldaten.py). Die
Einbindung (`include_router`) gehört der Hauptsession und muss vor dem SPA-Fallback stehen. Alle
Logik liegt in app/netzwerk_import.py, dieser Router liest nur die hochgeladene Datei (Grenze 5 MB
VOR dem Parsen) und übersetzt `ImportFehler` in HTTP-Status und Klartext.

Die Routen sind synchron: FastAPI führt sie im Threadpool aus, so blockieren Parsen, Sicherung und
Schreiben den Event-Loop des Servers nicht.

Pfade (Listen-Kennung `zielfirmen`, `headhunter` oder `kontakte`, sonst 404):

    GET  /api/netzwerk-import/{liste}/vorlage?format=csv|xlsx   Vorlage zum Herunterladen
    POST /api/netzwerk-import/{liste}/vorschau                  Feld `datei`, schreibt nichts
    POST /api/netzwerk-import/{liste}                           Feld `datei`, sichert und schreibt
"""
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlmodel import Session

from app import netzwerk_import
from app.db import get_session

router = APIRouter(prefix="/api", tags=["netzwerk-import"])


def _datei_lesen(datei: UploadFile | None) -> tuple[str, bytes]:
    """Name und Inhalt der hochgeladenen Datei. Mehr als 5 MB wird nicht erst eingelesen."""
    if datei is None:
        raise HTTPException(400, "Bitte wählen Sie eine Datei aus.")
    if datei.size is not None and datei.size > netzwerk_import.MAX_BYTES:
        raise HTTPException(413, netzwerk_import.TEXT_ZU_GROSS)
    inhalt = datei.file.read(netzwerk_import.MAX_BYTES + 1)
    if len(inhalt) > netzwerk_import.MAX_BYTES:
        raise HTTPException(413, netzwerk_import.TEXT_ZU_GROSS)
    return datei.filename or "", inhalt


@router.get("/netzwerk-import/{liste}/vorlage")
def get_vorlage(liste: str, dateiformat: str = Query("csv", alias="format")):
    try:
        inhalt, dateiname, media_type = netzwerk_import.vorlage(liste, dateiformat)
    except netzwerk_import.ImportFehler as exc:
        raise HTTPException(exc.status, exc.text)
    return Response(content=inhalt, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{dateiname}"'})


@router.post("/netzwerk-import/{liste}/vorschau")
def post_vorschau(liste: str, datei: UploadFile | None = File(None),
                  session: Session = Depends(get_session)):
    name, inhalt = _datei_lesen(datei)
    try:
        return netzwerk_import.vorschau(liste, name, inhalt, session=session)
    except netzwerk_import.ImportFehler as exc:
        raise HTTPException(exc.status, exc.text)


@router.post("/netzwerk-import/{liste}")
def post_import(liste: str, datei: UploadFile | None = File(None),
                session: Session = Depends(get_session)):
    name, inhalt = _datei_lesen(datei)
    try:
        return netzwerk_import.importieren(liste, name, inhalt, session=session)
    except netzwerk_import.ImportFehler as exc:
        raise HTTPException(exc.status, exc.text)
