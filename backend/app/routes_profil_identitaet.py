"""API-Router „Profil-Datei“ (P2-69): `GET`/`PUT /api/profil/identitaet` für die Karte „Identität und
Suchstrategie“ auf der Profil-Seite. Die Karte liest und schreibt `config/profil.md`; die Datei bleibt
die einzige Quelle (Leser wie `pipeline/user_profile.py` und die Skills ändern sich nicht).

Eigener APIRouter (Muster app/routes_sicherung.py), die Logik liegt in `pipeline/profil_datei.py`
(Vertrag F). Dieser Router übersetzt nur Ausnahmen in HTTP-Status mit Kundentext:

  * 400 bei ungültiger Eingabe (`ValueError`, der Text steht im `detail`),
  * 409 bei veraltetem `stand` (die Datei hat sich seit dem Laden geändert, z. B. durch einen Skill),
  * 422 bei GET, wenn die Datei nicht als UTF-8 lesbar ist,
  * 500, wenn die Datei nicht geschrieben werden konnte (die alte Datei bleibt dann stehen).

Payload von PUT ist ein plain dict (kein pydantic.BaseModel) -- Projektkonvention (Invariante I6,
Muster app/routes_coach_settings.py); die Prüfung der Felder macht `profil_datei.schreiben`."""
from fastapi import APIRouter, HTTPException

from app.sprache import tx
from pipeline import profil_datei

router = APIRouter(prefix="/api", tags=["profil-datei"])


@router.get("/profil/identitaet")
def get_profil_identitaet():
    try:
        return profil_datei.lesen()
    except profil_datei.DateiNichtLesbar as exc:
        raise HTTPException(422, str(exc))
    except OSError as exc:
        raise HTTPException(500, tx("Ihre Profil-Datei konnte nicht gelesen werden: {grund}", grund=str(exc)))


@router.put("/profil/identitaet")
def put_profil_identitaet(payload: dict):
    stand = payload.get("stand")
    if not isinstance(stand, str):
        raise HTTPException(400, tx("Es fehlt die Angabe zum Stand der Profil-Datei. Bitte laden Sie die "
                                    "Karte neu und versuchen Sie es noch einmal."))
    try:
        ergebnis = profil_datei.schreiben(payload, stand)
    except profil_datei.StandVeraltet as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except OSError as exc:
        raise HTTPException(500, tx("Ihre Profil-Datei konnte nicht gespeichert werden: {grund}. "
                                    "Die bisherige Datei ist unverändert.", grund=str(exc)))
    antwort = profil_datei.lesen()
    # Hinweise zu den eingegebenen Werten (z. B. E-Mail ohne „@“, die beim Lesen als Telefon
    # erscheint) zusätzlich zu denen der frisch gelesenen Datei, ohne Doppelte.
    antwort["hinweise"] = list(dict.fromkeys(antwort["hinweise"] + ergebnis["hinweise"]))
    antwort["papierkorb"] = ergebnis["papierkorb"]
    return antwort
