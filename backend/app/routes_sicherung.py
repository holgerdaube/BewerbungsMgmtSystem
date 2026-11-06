"""API-Router „Sicherung" (P2-52, Paket S1) -- Status, „Jetzt sichern" und Einstellungen der
automatischen Datenbank-Sicherung für die Einstellungen-Seite und das Dashboard-Banner.

Eigener APIRouter statt neuer @app.*-Routen direkt in main.py (Muster app/routes_version.py) --
der einzige Umbau an main.py selbst (Import, include_router, Aufruf von app.sicherung.starten()
im Startup-Hook) bleibt bewusst der Hauptsession vorbehalten (s. Bau-Spec
tasks/spec_p2-52_sicherung_inbox_archiv.md, Verträge V4/V5). Alle Logik liegt in
app/sicherung.py, dieser Router ist bewusst dünn -- er übersetzt nur die drei Ausnahmefälle
(Sperre belegt, Sicherung fehlgeschlagen, ungültige Einstellungen) in HTTP-Status/Klartext.

Payload von PATCH ist bewusst ein plain dict (kein pydantic.BaseModel) -- Projektkonvention
(Invariante I6, Muster app/routes_coach_settings.py)."""
from fastapi import APIRouter, HTTPException

from app import sicherung
from app.sprache import tx
from app.terminal import tt

router = APIRouter(prefix="/api", tags=["sicherung"])


@router.get("/sicherung")
def get_sicherung():
    return sicherung.status()


@router.post("/sicherung")
def post_sicherung():
    """„Jetzt sichern" -- synchrone Route, FastAPI führt sie im Threadpool aus (V4: läuft auch
    bei aktiv: false). Rotiert nach erfolgreichem Anlegen mit den gespeicherten Einstellungen."""
    try:
        sicherung.anlegen()
    except sicherung.SicherungLaeuft as exc:
        raise HTTPException(409, str(exc))
    except Exception as exc:
        raise HTTPException(500, tx("Sicherung fehlgeschlagen: {grund}", grund=str(exc)))

    # Die Sicherung steht ab hier. Scheitert nur das Ausdünnen, darf die Antwort nicht „fehlgeschlagen"
    # lauten: der Nutzer hielte sonst eine vorhandene Sicherung für verloren.
    try:
        entfernt = sicherung.rotieren()
    except Exception as exc:       # noqa: BLE001
        print(tt("[sicherung] WARNUNG: Ausdünnen nach „Jetzt sichern“ fehlgeschlagen: {fehler}", fehler=exc), flush=True)
        entfernt = []
    stand = sicherung.status()
    # stand["letzte"] ist garantiert die gerade eben angelegte Datei: die Aufbewahrungsregel
    # behält die neueste immer (V2), und zwischen anlegen()/rotieren() oben und dieser
    # status()-Abfrage kann keine NEUERE Sicherung entstanden sein (dieselbe Sperre serialisiert
    # Takt und „Jetzt sichern", s. app/sicherung.py::rotieren()) -- deshalb hier wiederverwendet
    # statt derselben {datei, zeitpunkt, groesse}-Form ein zweites Mal Code zu geben.
    return {"neu": stand["letzte"], "entfernt": entfernt, "status": stand}


@router.patch("/sicherung/einstellungen")
def patch_sicherung_einstellungen(payload: dict):
    try:
        sicherung.einstellungen_speichern(payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return sicherung.status()
