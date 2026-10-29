"""API-Router „Dokumentation" (P2-59, Paket D): die Liste der Dokumente und die einzelne Seite.

Eigener `APIRouter` wie `app/routes_version.py`: `main.py` bekommt dafür nur Import und
`include_router`. Die Logik liegt in `app/doku.py`, dieser Router ist bewusst dünn.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app import doku

router = APIRouter(prefix="/api", tags=["doku"])


@router.get("/doku")
def liste():
    """Die Dokumente dieser Installation für die Tabs der Dokumentationsseite. Nur Kennung,
    Titel und Gruppe: Welche Datei dahinter liegt, geht den Browser nichts an."""
    return [{"id": e["id"], "titel": e["titel"], "gruppe": e["gruppe"]} for e in doku.verfuegbar()]


@router.get("/doku/{name}")
def dokument(name: str):
    """Eine Doku-Seite als HTML. `name` ist eine Kennung oder ein Dateiname aus dem Katalog
    (`app/doku.py`), alles andere antwortet mit 404.

    Die Seite trägt denselben Kopf wie die Berichte (`_BERICHT_KOPF`, P2-58): Sie läuft im Browser
    mit eigenem Ursprung statt im Ursprung der API, und `no-cache` sorgt dafür, dass nach einem
    Update nicht die alte Fassung aus dem Zwischenspeicher kommt. Der Import steht erst hier, weil
    `app.main` diesen Router einbindet: Oben im Modul wäre es ein Zirkelimport. So bleibt der Kopf
    eine einzige Quelle."""
    eintrag = doku.eintrag_fuer(name)
    if eintrag is None:
        raise HTTPException(404, "Dokument nicht gefunden")
    try:
        seite = doku.rendern(eintrag)
    except OSError:     # Datei zwischen Prüfung und Lesen verschwunden oder nicht lesbar
        raise HTTPException(404, "Dokument nicht gefunden")
    from app.main import _BERICHT_KOPF
    return HTMLResponse(seite, headers=_BERICHT_KOPF)
