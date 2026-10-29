"""API-Router „Design“ (P2-72, Paket G): das geltende Design für Oberfläche und Berichte.

Eigener `APIRouter` wie `app/routes_version.py`: `main.py` bekommt dafür nur Import und
`include_router`. Die Logik (Lesen, Prüfen, Zwischenspeichern, CSS) liegt in `pipeline/design.py`,
dieser Router ist bewusst dünn. Alles ist nur lesbar (GET).

  GET /api/design               JSON: name, produktname, quelle, warnungen
  GET /api/design.css           text/css: ein :root-Block mit allen Rollen und den zwei Schriften
  GET /api/design/icon/32|180   das geltende Icon als PNG (jede andere Größe: 404)

Jede Antwort trägt `Cache-Control: no-cache` und einen ETag aus dem Inhalt des geltenden Designs
(`Design.stand`). Der Browser fragt bei jedem Aufruf nach und bekommt bei unverändertem Design ein
leeres 304: Eine neue Design-Datei gilt damit nach einem Neuladen der Seite, ein Update oder ein
Neubau der Oberfläche ist nicht nötig. Alle drei Aufrufe teilen sich den Stand; ein geänderter Wert
macht auch die Icons zu einer „neuen“ Antwort, was nur eine unnötige Übertragung kostet.
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from pipeline import design

router = APIRouter(prefix="/api", tags=["design"])


def _geltendes_design() -> design.Design:
    """Das geltende Design. Fehler der Überschreibung gibt es hier nie (sie sind Warnungen); nur eine
    beschädigte Vorgabe (kaputte Installation) wird zu einer verständlichen 500."""
    try:
        return design.laden()
    except design.DesignFehler as fehler:
        raise HTTPException(500, f"Die Design-Vorgabe des Programms ist unbrauchbar: {fehler}")


def _etag(d: design.Design) -> str:
    return f'"{d.stand}"'


def _passt(request: Request, etag: str) -> bool:
    """Trifft `If-None-Match` unseren ETag? Erlaubt sind `*`, eine Liste und die schwache Schreibweise
    `W/"…"` (Proxys schwächen ETags ab; für einen Vergleich auf 304 genügt der Wert)."""
    kopf = request.headers.get("if-none-match")
    if not kopf:
        return False
    if kopf.strip() == "*":
        return True
    angebote = [teil.strip() for teil in kopf.split(",")]
    return any(teil.removeprefix("W/") == etag for teil in angebote)


def _kopf(etag: str) -> dict:
    return {"Cache-Control": "no-cache", "ETag": etag}


def _nicht_geaendert(etag: str) -> Response:
    return Response(status_code=304, headers=_kopf(etag))


@router.get("/design")
def design_auskunft(request: Request):
    d = _geltendes_design()
    etag = _etag(d)
    if _passt(request, etag):
        return _nicht_geaendert(etag)
    return JSONResponse({"name": d.name, "produktname": d.produktname, "quelle": d.quelle,
                         "warnungen": list(d.warnungen)}, headers=_kopf(etag))


@router.get("/design.css")
def design_css(request: Request):
    d = _geltendes_design()
    etag = _etag(d)
    if _passt(request, etag):
        return _nicht_geaendert(etag)
    return Response(design.css_oberflaeche(d), media_type="text/css; charset=utf-8",
                    headers=_kopf(etag))


@router.get("/design/icon/{groesse}")
def design_icon(groesse: str, request: Request):
    """`groesse` ist ein Text und keine Zahl: „032“, „32.0“ und „abc“ sind keine Größe, sondern 404
    (statt 422)."""
    if groesse not in design.ICON_GROESSEN:
        raise HTTPException(404, "Unbekannte Icon-Größe")
    d = _geltendes_design()
    etag = _etag(d)
    if _passt(request, etag):
        return _nicht_geaendert(etag)
    inhalt = d.icon_bytes(groesse)
    if inhalt is None:      # Datei zwischen Prüfung und Lesen verschwunden oder zu groß geworden
        raise HTTPException(404, "Icon nicht gefunden")
    return Response(inhalt, media_type="image/png", headers=_kopf(etag))
