"""API-Router „Coach-Site" (Phase 82, Arbeitspaket A1) — macht die in Phase 81 fest
verdrahtete Coach-Site (SFTP-Zugang nur in `~/.bewerbung_mgmt_secrets/coach_sftp.env`,
Terminal-Skripte, die Zieladresse hart im `.htaccess`-Template) über die UI konfigurierbar
(Auftrag vom 12.08.2026, s. `tasks/spec_phase82_coach_konfigurierbar.md` Abschnitt 1.4).

Eigener `APIRouter` statt neuer `@app.*`-Routen direkt in `main.py` (Muster
`app/routes_mail_settings.py`) — der einzige Umbau an `main.py` selbst (Import +
`include_router`, genau 2 Zeilen) bleibt bewusst der Hauptsession vorbehalten.

Vier Endpunkte, alle unter `/api/settings/coach`:
  * `GET  ""`            — aktuelle Konfiguration OHNE Passwörter (`*_set`-Flags statt Wert),
                           plus `quelle` (settings/env-migriert/leer, s.
                           `pipeline.coach_settings.quelle`).
  * `PUT  ""`             — validiert + schreibt `coach_settings.json`
                           (`pipeline.coach_settings.save_settings`). Leeres/fehlendes
                           `sftp_password` behält das gespeicherte; ein mitgeschicktes
                           `coach_password` wird SOFORT über `set_coach_login()` zu bcrypt
                           verrechnet (nie als Klartext gespeichert, s. dortiger
                           Moduldocstring). `aktiv: true` verlangt eine vollständige
                           Konfiguration (`fehlende_felder()`).
  * `POST "/test"`        — Verbindungstest gegen die MITGESENDETEN (ggf. noch
                           ungespeicherten) Formularwerte, fehlende Felder werden aus der
                           gespeicherten Konfiguration ergänzt (Muster Mail-Test aus
                           `routes_mail_settings.py`) — ändert nichts auf der Platte und
                           nichts auf dem Server.
  * `POST "/serverpfad"`  — Automatik-Ermittlung von `authuserfile`
                           (`pipeline.coach_settings.serverpfad_ermitteln`, Bau-Spec 1.4):
                           läuft nur im LEEREN Zielverzeichnis (409 sonst) und räumt die
                           hochgeladene PHP-Probe-Datei in JEDEM Fall wieder auf.

Payloads sind bewusst plain `dict` (kein `pydantic.BaseModel`) — Projektkonvention (Invariante
I6). Fehlertexte erreichen den Client als Klartext über `HTTPException(status, detail=…)` —
genau wie in `routes_mail_settings.py`, dessen Docstring auf `frontend/src/api.ts::api()`
verweist, das dieses Feld als `ApiError.message` liest.

I2 (Live-Leak 10.08.2026, s. tasks/lessons.md): `coach_settings.sftp_lauf()` /
`serverpfad_ermitteln()` filtern lftp-Rohausgaben bereits VOR jeder Rückgabe (Erfolg wie
Fehler) über `ohne_geheimnisse()`. Dieser Router filtert bei einem gefangenen `RuntimeError`/
`ServerpfadKonflikt` sicherheitshalber ein zweites Mal — Verteidigung in der Tiefe direkt an
der API-Grenze; ein zweiter Filterdurchlauf auf bereits gefiltertem Text verändert dessen
Inhalt nicht. Kein Zugriff auf die DB, keine Task-Logik — reine Datei-/Subprocess-Operationen
aus `pipeline.coach_settings`.
"""
from fastapi import APIRouter, HTTPException

from pipeline import coach_settings

router = APIRouter(prefix="/api/settings/coach", tags=["coach-settings"])

_EDITIERBARE_FELDER = {
    "aktiv", "site_url", "sftp_host", "sftp_user", "sftp_password", "sftp_dir",
    "authuserfile", "coach_user", "coach_password",
}


def _aktueller_coach_user(data: dict) -> str:
    """`coach_user` aus den Settings, sonst Fallback auf den in `coach_htpasswd` hinterlegten
    Benutzernamen (z. B. nach der Phase-81-Migration oder nach einem Login-Setzen über den
    alten Terminal-Weg `scripts/coach_passwort.sh`) — genau der in
    `coach_settings.coach_login_benutzer()` dokumentierte Zweck: „damit die UI ihn nach einem
    Neustart anzeigen kann, falls coach_user leer ist". Dieselbe Auflösung dient hier zugleich
    als Vergleichsbasis für die „coach_user geändert"-Prüfung in `put_coach_settings` — sonst
    würde jede Migration/jeder Alt-Login beim nächsten Speichern fälschlich als „Benutzername
    geändert" gelten."""
    return str(data.get("coach_user") or "").strip() or coach_settings.coach_login_benutzer()


def _out(data: dict) -> dict:
    """Antwortform für GET/PUT (API-Kontrakt 1.4) — NIE `sftp_password` oder ein
    Coach-Passwort im Klartext (Letzteres existiert ohnehin nirgends, s.
    `coach_settings`-Moduldocstring); `*_set`-Flags statt Wert, `quelle` für die UI-Diagnose."""
    return {
        "aktiv": bool(data.get("aktiv")),
        "site_url": str(data.get("site_url") or ""),
        "sftp_host": str(data.get("sftp_host") or ""),
        "sftp_user": str(data.get("sftp_user") or ""),
        "sftp_dir": str(data.get("sftp_dir") or ""),
        "authuserfile": str(data.get("authuserfile") or ""),
        "coach_user": _aktueller_coach_user(data),
        "sftp_password_set": bool(data.get("sftp_password")),
        "coach_password_set": coach_settings.coach_login_gesetzt(),
        "quelle": coach_settings.quelle(),
    }


@router.get("")
def get_coach_settings():
    return _out(coach_settings.load_settings())


@router.put("")
def put_coach_settings(payload: dict):
    unbekannt = set(payload) - _EDITIERBARE_FELDER
    if unbekannt:
        raise HTTPException(422, f"Nicht editierbare Felder: {', '.join(sorted(unbekannt))}")

    site_url = str(payload.get("site_url") or "").strip()
    if site_url and not site_url.startswith("https://"):
        raise HTTPException(422, "Basic-Auth über HTTP würde das Passwort im Klartext "
                                  "übertragen — die Adresse muss mit https:// beginnen.")
    site_url = site_url.rstrip("/")

    sftp_dir = str(payload.get("sftp_dir") or "").strip()
    if sftp_dir and not sftp_dir.startswith("/"):
        raise HTTPException(422, "sftp_dir muss ein absoluter Serverpfad sein (beginnend mit '/').")

    authuserfile = str(payload.get("authuserfile") or "").strip()
    if authuserfile and not authuserfile.startswith("/"):
        raise HTTPException(422, "authuserfile muss ein absoluter Serverpfad sein (beginnend mit '/').")

    # Ab hier wird die gespeicherte Konfiguration gebraucht (Vergleichsbasis fuer
    # coach_user/sftp_password) -- reiner Lesezugriff, kein Seiteneffekt.
    bestehend = coach_settings.load_settings()

    coach_user = str(payload.get("coach_user") or "").strip()
    alter_coach_user = _aktueller_coach_user(bestehend)
    coach_password_roh = payload.get("coach_password")
    coach_password_mitgeschickt = coach_password_roh is not None and str(coach_password_roh).strip() != ""

    if coach_user != alter_coach_user and not coach_password_mitgeschickt:
        raise HTTPException(422, "Benutzername geändert — bitte auch ein Passwort setzen, "
                                  "sonst passt die hinterlegte Zugangsdatei nicht mehr.")

    neues_sftp_passwort = payload.get("sftp_password")
    if neues_sftp_passwort is not None and str(neues_sftp_passwort).strip():
        sftp_password = str(neues_sftp_passwort)
    else:
        sftp_password = str(bestehend.get("sftp_password") or "")   # leer/fehlend = behalten

    # Coach-Login VOR dem Vollstaendigkeits-Check setzen, falls mitgeschickt: fehlende_felder()
    # prueft coach_login_gesetzt() gegen den ECHTEN Dateizustand -- ein frisch im selben PUT
    # gesetztes Login muss dort schon als "vorhanden" zaehlen, sonst waere eine
    # Erstkonfiguration (alle Felder inkl. Login in einem Aufruf) nie in einem Schritt moeglich.
    if coach_password_mitgeschickt:
        ziel_user = coach_user or alter_coach_user
        try:
            coach_settings.set_coach_login(ziel_user, str(coach_password_roh))
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    neue_settings = {
        "aktiv": bool(payload.get("aktiv", False)),
        "site_url": site_url,
        "sftp_host": str(payload.get("sftp_host") or "").strip(),
        "sftp_user": str(payload.get("sftp_user") or "").strip(),
        "sftp_password": sftp_password,
        "sftp_dir": sftp_dir,
        "authuserfile": authuserfile,
        "coach_user": coach_user,
    }

    if neue_settings["aktiv"]:
        fehlend = coach_settings.fehlende_felder(neue_settings)
        if fehlend:
            raise HTTPException(422, f"Zum Aktivieren fehlen noch: {', '.join(fehlend)}")

    coach_settings.save_settings(neue_settings)
    return _out(neue_settings)


@router.post("/test")
def test_coach_settings(payload: dict | None = None):
    """Testet vorrangig die MITGEGEBENEN Formularfelder (noch ungespeichert) — fehlt ein Feld
    im Request, wird die gespeicherte Konfiguration ergänzt (Muster
    `routes_mail_settings.py::test_mail_settings`). Schreibt nichts."""
    payload = payload or {}
    bestehend = coach_settings.load_settings()
    test_settings = {
        "sftp_host": payload.get("sftp_host") or bestehend.get("sftp_host"),
        "sftp_user": payload.get("sftp_user") or bestehend.get("sftp_user"),
        "sftp_dir": payload.get("sftp_dir") or bestehend.get("sftp_dir"),
    }
    neues_passwort = payload.get("sftp_password")
    if neues_passwort is not None and str(neues_passwort).strip():
        test_settings["sftp_password"] = neues_passwort
    else:
        test_settings["sftp_password"] = bestehend.get("sftp_password")

    ziel_dir = str(test_settings.get("sftp_dir") or "").strip()
    if not ziel_dir:
        raise HTTPException(400, "sftp_dir fehlt — bitte zuerst das Zielverzeichnis eintragen.")

    try:
        ausgabe = coach_settings.sftp_lauf(test_settings, [f"cls -1 {ziel_dir}"])
    except RuntimeError as exc:
        raise HTTPException(400, coach_settings.ohne_geheimnisse(str(exc), test_settings))

    anzahl = len([zeile for zeile in ausgabe.splitlines() if zeile.strip()])
    stand = "leer" if anzahl == 0 else f"{anzahl} Einträge"
    return {"ok": True, "meldung": f"Verbunden. Zielverzeichnis {ziel_dir} erreichbar ({stand})."}


@router.post("/serverpfad")
def post_serverpfad(payload: dict | None = None):
    """Automatik fuer `authuserfile` (Bau-Spec 1.4) — nutzt wie `/test` vorrangig die
    mitgesendeten Formularwerte, ergaenzt Fehlendes aus der gespeicherten Konfiguration.
    `ServerpfadKonflikt` (Zielverzeichnis nicht leer) MUSS vor dem allgemeinen `RuntimeError`
    abgefangen werden, da sie davon erbt -- sonst wuerde die spezifischere 409-Behandlung nie
    erreicht."""
    payload = payload or {}
    bestehend = coach_settings.load_settings()
    daten = {
        "site_url": payload.get("site_url") or bestehend.get("site_url"),
        "sftp_host": payload.get("sftp_host") or bestehend.get("sftp_host"),
        "sftp_user": payload.get("sftp_user") or bestehend.get("sftp_user"),
        "sftp_dir": payload.get("sftp_dir") or bestehend.get("sftp_dir"),
    }
    neues_passwort = payload.get("sftp_password")
    if neues_passwort is not None and str(neues_passwort).strip():
        daten["sftp_password"] = neues_passwort
    else:
        daten["sftp_password"] = bestehend.get("sftp_password")

    try:
        return coach_settings.serverpfad_ermitteln(daten)
    except coach_settings.ServerpfadKonflikt as exc:
        raise HTTPException(409, coach_settings.ohne_geheimnisse(str(exc), daten))
    except RuntimeError as exc:
        raise HTTPException(400, coach_settings.ohne_geheimnisse(str(exc), daten))
