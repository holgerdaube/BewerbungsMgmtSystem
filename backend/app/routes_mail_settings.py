"""API-Router „E-Mail-Konto" (Phase 71F — Produktisierung: Mail-Provider-Abstraktion).

Eigener `APIRouter` statt neuer `@app.*`-Routen direkt in `main.py` — das ist bewusst der
EINZIGE Umbau an `main.py` selbst (Import + `include_router`, s. dortige Kommentarzeile).

Drei Endpunkte, alle unter `/api/settings/mail`:
  * `GET  ""`      — aktuelle Konfiguration OHNE Passwort (`password_set`-Flag statt Wert).
  * `PUT  ""`       — validiert + schreibt `mail_settings.json` (chmod 600, via
                      `pipeline.imap_mail.save_settings`); leeres/fehlendes Passwortfeld
                      behält das vorhandene (Spec-Vorgabe „leeres Passwort-Feld = vorhandenes
                      behalten").
  * `POST "/test"`  — Verbindungstest; testet die im Request mitgegebenen (ggf. noch
                      UNGESPEICHERTEN) Formularfelder, sonst die gespeicherte Konfiguration.
                      Gmail: bestehenden Token-Check (`gmail_client._creds()`) wiederverwenden.
                      IMAP: Login + Auswahl des Entwürfe-Ordners (`imap_mail.test_connection`).

Payloads sind bewusst plain `dict` (kein `pydantic.BaseModel`) — Projektkonvention, s.
`main.py::update_einstellungen` (kein einziges `BaseModel` irgendwo im Backend, Stand 71F).

Fehlertexte erreichen den Client als Klartext über `HTTPException(status, detail=…)` —
FastAPI serialisiert das als `{"detail": "…"}`, `frontend/src/api.ts::api()` liest genau dieses
Feld in `ApiError` (lessons.md „Frontend": *Wer serverseitig eine gute Fehlermeldung schreibt,
muss prüfen, dass sie den Client auch erreicht*). `gmail_client`/`imap_mail` brechen bei
Fehlern mit `SystemExit` + Klartext auf stderr ab (Modul-Konvention seit Phase 8.3) — hier
exakt so abgefangen wie im bestehenden Vorbild `main.py::email_body`
(`/api/emails/{id}/body`): stderr umleiten, `SystemExit` fangen, Text weiterreichen statt
eines rohen 500ers.
"""
import contextlib
import io

from fastapi import APIRouter, HTTPException

from app.sprache import tx
from pipeline import gmail_client, imap_mail

router = APIRouter(prefix="/api/settings/mail", tags=["mail-settings"])

_ALLOWED_PROVIDERS = {"gmail", "imap"}
_ALLOWED_SECURITY = {"ssl", "starttls"}
_OUT_DEFAULTS = {"host": "", "port": 993, "security": "ssl", "username": "",
                 "drafts_folder": imap_mail.DEFAULT_DRAFTS_FOLDER}


def _out(data: dict) -> dict:
    """Antwortform für GET/PUT — IMMER dieselben Felder (auch bei provider=gmail, dann mit
    Platzhalter-Defaults), damit das Frontend keine Fallunterscheidung pro Provider braucht."""
    out = {"provider": data.get("provider") or "gmail", **_OUT_DEFAULTS}
    for k in ("host", "port", "security", "username", "drafts_folder"):
        if data.get(k) not in (None, ""):
            out[k] = data[k]
    out["password_set"] = bool(data.get("password"))
    return out


def _rufe_mit_stderr_abgefangen(fn, fehler_praefix: str):
    """Ruft `fn()` auf; ein `SystemExit` (Modul-Konvention `_die()`) wird zu `HTTPException(400,
    Klartext)` statt zu einem rohen 500er — Muster aus `main.py::email_body`."""
    puffer = io.StringIO()
    try:
        with contextlib.redirect_stderr(puffer):
            return fn()
    except SystemExit:
        raise HTTPException(400, puffer.getvalue().strip() or fehler_praefix)
    except Exception as exc:                 # noqa: BLE001 — nie 500, immer lesbarer Hinweis
        raise HTTPException(400, tx("{praefix}: {grund}", praefix=fehler_praefix, grund=str(exc)))


@router.get("")
def get_mail_settings():
    return _out(imap_mail.load_settings())


@router.put("")
def put_mail_settings(payload: dict):
    editierbar = {"provider", "host", "port", "security", "username", "password", "drafts_folder"}
    unbekannt = set(payload) - editierbar
    if unbekannt:
        raise HTTPException(422, tx("Nicht editierbare Felder: {felder}", felder=", ".join(sorted(unbekannt))))

    provider = str(payload.get("provider") or "").strip().lower()
    if provider not in _ALLOWED_PROVIDERS:
        raise HTTPException(422, tx("provider muss 'gmail' oder 'imap' sein, nicht {wert}",
                                    wert=repr(payload.get("provider"))))

    if provider == "gmail":
        imap_mail.save_settings({"provider": "gmail"})
        return _out({"provider": "gmail"})

    host = str(payload.get("host") or "").strip()
    username = str(payload.get("username") or "").strip()
    drafts_folder = str(payload.get("drafts_folder") or "").strip()
    fehlend = [name for name, wert in (("host", host), ("username", username),
                                        ("drafts_folder", drafts_folder)) if not wert]
    if fehlend:
        raise HTTPException(422, tx("Pflichtfeld(er) fehlen: {felder}", felder=", ".join(fehlend)))

    security = str(payload.get("security") or "ssl").strip().lower()
    if security not in _ALLOWED_SECURITY:
        raise HTTPException(422, tx("security muss 'ssl' oder 'starttls' sein, nicht {wert}",
                                    wert=repr(payload.get("security"))))

    try:
        port = int(payload.get("port") or 993)
    except (TypeError, ValueError):
        raise HTTPException(422, tx("port muss eine Zahl sein"))
    if not (0 < port <= 65535):
        raise HTTPException(422, tx("port muss zwischen 1 und 65535 liegen"))

    bestehend = imap_mail.load_settings()
    neues_passwort = payload.get("password")
    if neues_passwort is not None and str(neues_passwort).strip():
        passwort = str(neues_passwort)
    elif bestehend.get("provider") == "imap" and bestehend.get("password"):
        passwort = bestehend["password"]      # leeres Feld = vorhandenes behalten (Spec-Vorgabe)
    else:
        raise HTTPException(422, tx("password fehlt"))

    neue_settings = {
        "provider": "imap", "host": host, "port": port, "security": security,
        "username": username, "password": passwort, "drafts_folder": drafts_folder,
    }
    imap_mail.save_settings(neue_settings)
    return _out(neue_settings)


@router.post("/test")
def test_mail_settings(payload: dict | None = None):
    """Testet vorrangig die MITGEGEBENEN Formularfelder (noch ungespeichert) — fehlt ein Feld
    im Request, wird die gespeicherte Konfiguration ergänzt. So kann „Verbindung testen" schon
    VOR „Speichern" geklickt werden (typische Formular-UX), ohne ein evtl. falsches Passwort
    erst auf die Platte zu schreiben."""
    payload = payload or {}
    bestehend = imap_mail.load_settings()
    provider = str(payload.get("provider") or bestehend.get("provider") or "gmail").strip().lower()

    if provider == "gmail":
        def _gmail_check():
            creds = gmail_client._creds()
            with gmail_client._client(creds) as cl:
                konto = gmail_client._get(cl, "/profile").get("emailAddress")
            return {"ok": True, "meldung": tx("Gmail verbunden ({konto}).", konto=konto)}

        return _rufe_mit_stderr_abgefangen(_gmail_check, tx("Gmail-Verbindung fehlgeschlagen"))

    test_settings = {
        "host": payload.get("host") or bestehend.get("host"),
        "port": payload.get("port") or bestehend.get("port"),
        "security": payload.get("security") or bestehend.get("security"),
        "username": payload.get("username") or bestehend.get("username"),
        "drafts_folder": payload.get("drafts_folder") or bestehend.get("drafts_folder"),
    }
    neues_passwort = payload.get("password")
    if neues_passwort is not None and str(neues_passwort).strip():
        test_settings["password"] = neues_passwort
    elif bestehend.get("provider") == "imap":
        test_settings["password"] = bestehend.get("password")

    return _rufe_mit_stderr_abgefangen(lambda: imap_mail.test_connection(test_settings),
                                        tx("IMAP-Verbindung fehlgeschlagen"))
