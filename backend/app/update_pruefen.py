"""Update-Auskunft für die App (P2-82, Vertrag A): fragt auf Knopfdruck bei GitHub-Releases nach der
neuesten Version und vergleicht sie mit der installierten.

Das BMS wird als Open Source bereitgestellt; neue Versionen erscheinen als GitHub-Release des
öffentlichen Repos. Dieses Modul beantwortet nur die Frage „Gibt es etwas Neueres?“. Einspielen tut
es NICHT — das geht weiter nur bei beendetem Server über `update.command`/`update_windows.bat`
(`scripts/bms_update.py`, Leitentscheidung 4 der Spec `tasks/spec_p2-82_lizenz_raus_update_github.md`).

Leitplanken (Spec, Leitentscheidungen 2 und 3):
  * NUR auf Knopfdruck: Es gibt keinen Abruf beim Start, keinen Hintergrund-Abruf, keine Erinnerung.
    Der einzige Aufrufer ist `GET /api/version/neueste` (`app/routes_version.py`).
  * Adresse und Repo sind Konstanten, KEINE Umgebungsvariablen: Wer sie umbiegen könnte, könnte ein
    fremdes „neuestes“ Release unterschieben. Nur Tests ersetzen sie im Prozess.
  * Anonym: kein Token, keine Kennung, nur `User-Agent: BMS-Update`. GitHub sieht die IP-Adresse des
    Rechners (der Hinweis steht in der Oberfläche neben dem Knopf).
  * Keine Umleitung wird verfolgt, die Zertifikatsprüfung bleibt an, die Antwort wird auf 1 MB
    begrenzt gelesen.
  * Keine Speicherung, kein Zwischenspeicher, kein Protokolleintrag mit IP oder Antwortinhalt. Das
    Ergebnis ist ein reines Wörterbuch; es verlässt das Modul nur als Antwort der Route.

`GITHUB_REPO` steht absichtlich auch in `scripts/bms_update.py` (das Werkzeug darf nichts aus `app`
importieren); `tests/test_update_pruefen.py` hält beide Konstanten gleich.

Antwortformat (immer ein Wörterbuch, die Route antwortet immer 200):
    {"installiert": "1.7.0", "neueste": "2.0.0", "neuer": True, "veroeffentlicht": "2026-11-15",
     "seite": "https://github.com/<repo>/releases/tag/v2.0.0", "aenderungen": "- …", "fehler": None}
Bei einem Fehler stehen `fehler` (Kundentext, Sie-Form) und `installiert`; alle übrigen Felder sind None.
"""
from __future__ import annotations

import json
import re
import ssl
import time
from datetime import date
from typing import Optional

import httpx

GITHUB_REPO = "holgerdaube/BewerbungsMgmtSystem"
GITHUB_API = "https://api.github.com"
ZEIT_S = 10                          # Gesamtzeit der Anfrage (Verbindung, Antwort, Lesen)
ANTWORT_MAX_BYTES = 1024 * 1024      # Vertrag A: Antwort höchstens 1 MB lesen
AENDERUNGEN_MAX_ZEICHEN = 4000       # Vertrag A: `aenderungen` höchstens 4000 Zeichen

_KOPF = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "BMS-Update",
}

# `[0-9]` statt `\d` (kein Unicode-Ziffernvorrat), `fullmatch` statt `$` (kein Zeilenumbruch am Ende).
_ZAHLEN = r"[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}"
_TAG_RE = re.compile(rf"v({_ZAHLEN})")
_VERSION_RE = re.compile(_ZAHLEN)
_DATUM_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_OHNE_LEERRAUM_RE = re.compile(r"[^\s\x00-\x1f\x7f]+")

# Kundentexte (Vertrag U, Sie-Form, ohne Phasennummer).
FEHLER_KEINE_VERBINDUNG = "Es besteht keine Verbindung zu GitHub."
FEHLER_ZEIT = "GitHub antwortet nicht rechtzeitig."
FEHLER_UNTERBROCHEN = "Die Verbindung zu GitHub wurde unterbrochen."
FEHLER_ZERTIFIKAT = "Die sichere Verbindung zu GitHub ließ sich nicht prüfen."
FEHLER_UNGUELTIG = "Die Antwort von GitHub ist ungültig."
FEHLER_KEINE_VERSION = "Es ist noch keine Version veröffentlicht."
FEHLER_GRENZE = "GitHub begrenzt gerade die Anfragen. Bitte versuchen Sie es in einer Stunde erneut."


class _AuskunftFehler(Exception):
    """Interner Abbruch mit fertigem Kundentext; verlässt das Modul nie als Ausnahme."""


def _version_tupel(text: object) -> Optional[tuple[int, int, int]]:
    """(major, minor, patch) aus `X.Y.Z`, sonst None. Zahlenvergleich statt Textvergleich
    (`1.10.0` ist neuer als `1.9.0`)."""
    if not isinstance(text, str) or not _VERSION_RE.fullmatch(text):
        return None
    major, minor, patch = (int(teil) for teil in text.split("."))
    return major, minor, patch


def _ist_zertifikatsfehler(exc: BaseException) -> bool:
    """Steht in der Ursachenkette ein `ssl.SSLError` (nicht überprüfbares Zertifikat, falscher Name,
    abgelaufen, …)? `httpx.ConnectError` verpackt ihn, deshalb die Kette ablaufen."""
    gesehen: set[int] = set()
    while exc is not None and id(exc) not in gesehen:
        if isinstance(exc, ssl.SSLError):
            return True
        gesehen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return False


def _netzfehler(exc: BaseException) -> _AuskunftFehler:
    """Kundentext zu einem Fehler beim Verbinden oder Lesen."""
    if isinstance(exc, httpx.TimeoutException):
        return _AuskunftFehler(FEHLER_ZEIT)
    if isinstance(exc, httpx.DecodingError):
        return _AuskunftFehler(FEHLER_UNGUELTIG)
    if _ist_zertifikatsfehler(exc):
        return _AuskunftFehler(FEHLER_ZERTIFIKAT)
    if isinstance(exc, httpx.ConnectError):
        return _AuskunftFehler(FEHLER_KEINE_VERBINDUNG)
    if isinstance(exc, (httpx.NetworkError, httpx.ProtocolError)):
        return _AuskunftFehler(FEHLER_UNTERBROCHEN)
    return _AuskunftFehler(FEHLER_KEINE_VERBINDUNG)


def _statuspruefung(status: int) -> None:
    if status == 200:
        return
    if status == 404:
        raise _AuskunftFehler(FEHLER_KEINE_VERSION)
    if status in (403, 429):
        raise _AuskunftFehler(FEHLER_GRENZE)
    # Auch 3xx: Die Auskunft folgt keiner Umleitung (Leitentscheidung 6), 5xx und alles andere ist
    # keine Antwort, mit der sich etwas anfangen ließe.
    raise _AuskunftFehler(FEHLER_UNGUELTIG)


def _abrufen() -> bytes:
    """Ein einziger GET auf `releases/latest`; liefert den Antwortkörper (höchstens 1 MB).
    `GITHUB_API`, `GITHUB_REPO` und `ZEIT_S` werden erst hier gelesen, damit Tests sie ersetzen
    können. `trust_env` bleibt an: Ein Firmen-Proxy aus der Umgebung des Rechners wird genutzt."""
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/releases/latest"
    ende = time.monotonic() + ZEIT_S
    teile: list[bytes] = []
    gelesen = 0
    try:
        with httpx.Client(timeout=ZEIT_S, follow_redirects=False, verify=True, headers=_KOPF) as client:
            with client.stream("GET", url) as antwort:
                _statuspruefung(antwort.status_code)
                for stueck in antwort.iter_bytes():
                    gelesen += len(stueck)
                    if gelesen > ANTWORT_MAX_BYTES:
                        raise _AuskunftFehler(FEHLER_UNGUELTIG)
                    if time.monotonic() > ende:        # tröpfelnde Antwort: Gesamtzeit gilt
                        raise _AuskunftFehler(FEHLER_ZEIT)
                    teile.append(stueck)
    except _AuskunftFehler:
        raise
    except (httpx.HTTPError, httpx.InvalidURL, httpx.StreamError, OSError) as exc:
        raise _netzfehler(exc) from None
    return b"".join(teile)


def _datum(wert: object) -> Optional[str]:
    """`JJJJ-MM-TT` aus `published_at` (ISO 8601, UTC), sonst None."""
    if not isinstance(wert, str):
        return None
    teil = wert[:10]
    if not _DATUM_RE.fullmatch(teil):
        return None
    try:
        date.fromisoformat(teil)
    except ValueError:
        return None
    return teil


def _seite(wert: object) -> Optional[str]:
    """`html_url` nur, wenn sie auf eine Release-Seite des eigenen Repos zeigt (sonst None):
    Die Oberfläche macht daraus einen Link."""
    if (not isinstance(wert, str) or not _OHNE_LEERRAUM_RE.fullmatch(wert)
            or not wert.startswith(f"https://github.com/{GITHUB_REPO}/releases/")):
        return None
    return wert


def _aenderungen(wert: object) -> Optional[str]:
    """`body` des Release als reiner Text, höchstens 4000 Zeichen; Zeilenenden als `\\n`
    (GitHub liefert oft `\\r\\n`). Leer oder kein Text -> None."""
    if not isinstance(wert, str):
        return None
    text = wert.replace("\r\n", "\n").replace("\r", "\n").strip()
    return text[:AENDERUNGEN_MAX_ZEICHEN] or None


def _auswerten(roh: bytes, installiert: Optional[str]) -> dict:
    """Prüft die JSON-Antwort und baut daraus das Antwortwörterbuch (Vertrag A)."""
    try:
        daten = json.loads(roh.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise _AuskunftFehler(FEHLER_UNGUELTIG) from None
    if not isinstance(daten, dict):
        raise _AuskunftFehler(FEHLER_UNGUELTIG)
    tag = daten.get("tag_name")
    treffer = _TAG_RE.fullmatch(tag) if isinstance(tag, str) else None
    if not treffer:
        raise _AuskunftFehler(FEHLER_UNGUELTIG)
    neueste = treffer.group(1)

    bekannt = _version_tupel(installiert)
    # Unbekannte oder 0.0.0-Installation (Quellbaum ohne VERSION): lieber „neuer“ melden.
    neuer = bekannt is None or bekannt == (0, 0, 0) or _version_tupel(neueste) > bekannt
    return {
        "installiert": installiert,
        "neueste": neueste,
        "neuer": neuer,
        "veroeffentlicht": _datum(daten.get("published_at")),
        "seite": _seite(daten.get("html_url")),
        "aenderungen": _aenderungen(daten.get("body")),
        "fehler": None,
    }


def _fehlerantwort(installiert: Optional[str], text: str) -> dict:
    return {"installiert": installiert, "neueste": None, "neuer": None, "veroeffentlicht": None,
            "seite": None, "aenderungen": None, "fehler": text}


def neueste_version(installiert: Optional[str]) -> dict:
    """Fragt bei GitHub nach der neuesten veröffentlichten Version (ohne Entwürfe und Vorabversionen)
    und vergleicht sie mit `installiert`. Wirft nie: Jeder Fehler steht als Kundentext im Feld
    `fehler` (Format: s. Moduldocstring)."""
    installiert = installiert if isinstance(installiert, str) else None
    try:
        return _auswerten(_abrufen(), installiert)
    except _AuskunftFehler as exc:
        return _fehlerantwort(installiert, str(exc))
