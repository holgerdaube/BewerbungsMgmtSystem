#!/usr/bin/env python3
"""Gmail-Zugang für das Bewerbungs-Management-System (Phase 8.3).

Ersetzt den claude.ai-Gmail-Connector, der in headless-Läufen (`claude -p`) nicht zur
Verfügung steht: dort sind NULL MCP-Tools registriert (verifiziert 10.07.2026). Dieser
Client läuft in beiden Welten — headless wie interaktiv — und ist damit der einzige
Gmail-Codepfad der Skills.

FASSADE seit Phase 71F (Produktisierung): `cmd_search`/`cmd_get`/`cmd_draft` sind der
EINZIGE Vertrag, den Skills/Module kennen — Signatur UND Ausgabeformat bleiben für Gmail
unverändert. Intern dispatchen die drei Funktionen zusätzlich nach `mail_settings.json`
(`pipeline.imap_mail.load_settings()`) an den IMAP-Codepfad (`pipeline.imap_mail`), wenn dort
`provider: "imap"` konfiguriert ist. Fehlt die Datei (Bestandsinstallationen wie die
Entwicklungsinstallation), bleibt der Provider "gmail" und ALLES unten läuft exakt wie vor Phase 71F — kein
einziger Aufruf verhält sich anders. Der Import von `pipeline.imap_mail` passiert bewusst
lazy (innerhalb der Funktionen, nicht auf Modulebene): `imap_mail` importiert seinerseits
`_entkleiden` aus `pipeline.htmltext` (derselben Quelle wie unten), ein Modulebene-Import
hier hätte also keinen echten Zirkel — lazy hält die Kopplung trotzdem einseitig und macht
das Modul isoliert lauffähig, falls `imap_mail` fehlt/kaputt ist.

SICHERHEITSGARANTIE — der Grund, warum dieses Modul existiert:
    Es gibt genau drei Verben: `search`, `get`, `draft`.
    Es gibt KEIN Verb zum Verschicken, Löschen oder Labeln. Nicht abgeschaltet,
    sondern nicht vorhanden. Eine Mail kann über diesen Client das Postfach nicht
    verlassen — das ist eine Eigenschaft des Codes, nicht der Prompt-Disziplin.
    (Der Google-Scope `gmail.compose` erlaubt der API technisch mehr; einen
    Draft-only-Scope bietet Google nicht. Die Grenze zieht hier der fehlende Codepfad.)

Arbeitsteilung wie überall im Projekt: Dieses Modul liefert nur MECHANISCHE Fakten
(Absender, Betreff, Zeitstempel, Richtung). Die Beurteilung — Kategorie, Firma,
Stellentitel, Statuswechsel — trifft der Skill. Die Records passen 1:1 in das
Schema von `pipeline/gmail_ingest.py`.

CLI (immer aus backend/ heraus):
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.gmail_client auth
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.gmail_client search --query "newer_than:2d …" [--max 50]
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.gmail_client get <message_id>
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.gmail_client draft --to a@b.de \
        --subject "…" --body-file entwurf.txt [--in-reply-to <message_id>]

Ausgabe: JSON auf stdout. Fehler: Klartext auf stderr, Exit 2.

Einmalige Einrichtung (Handarbeit, s. tasks/todo.md Phase 8.3):
    ~/.bewerbung_mgmt_secrets/gmail_credentials.json  ← OAuth-Client (Desktop) aus der Google
                                                          Cloud Console
    ~/.bewerbung_mgmt_secrets/gmail_token.json        ← schreibt `auth`, chmod 600, enthält
                                                          das Refresh-Token

Seit Phase 63A liegen beide Dateien AUSSERHALB von Projekt & iCloud (Vorbild:
beirat_engine.py, `~/.bewerbung_beirat`) — Override über `BMS_SECRETS_DIR`, Default
`~/.bewerbung_mgmt_secrets` (Verzeichnis chmod 700, Dateien chmod 600).
"""
import argparse
import base64
import datetime
import json
import os
import re
import sys
import warnings
from email.message import EmailMessage
from pathlib import Path

import httpx
import yaml

# google-auth/urllib3 warnen unter Python 3.9 bei jedem Import. Die Meldungen landen sonst
# im Task-Log jedes headless-Laufs und verdecken echte Fehler. stdout bleibt reines JSON.
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*OpenSSL.*")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent   # Bewerbung_Mgmt_System/
# Phase 63A (P1-2): Secrets liegen AUSSERHALB von Projekt & iCloud — sonst sind sie auf jedem
# Gerät am selben Apple-Account und im iCloud-Webzugriff sichtbar. Gleiches Muster wie
# beirat_engine.KEY_DIR (~/.bewerbung_beirat). Override per BMS_SECRETS_DIR, sonst fester Pfad.
SECRETS_DIR = Path(os.environ.get("BMS_SECRETS_DIR", str(Path.home() / ".bewerbung_mgmt_secrets")))
CRED_FILE = SECRETS_DIR / "gmail_credentials.json"
TOKEN_FILE = SECRETS_DIR / "gmail_token.json"

API = "https://gmail.googleapis.com/gmail/v1/users/me"

# readonly = lesen, compose = Entwürfe anlegen. Bewusst NICHT gmail.modify (Labels/Löschen).
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]

MAX_HARD = 200          # Obergrenze, auch wenn --max höher gesetzt wird
MAX_DEFAULT = 50


def _die(msg: str) -> "NoReturn":       # noqa: F821
    print(msg, file=sys.stderr)
    raise SystemExit(2)


# ── Auth ──────────────────────────────────────────────────────────────────────────────
def _save_token(creds) -> None:
    """Schreibt das (ggf. per Refresh erneuerte) Token zurück — Phase 63A: derselbe Pfad wie
    beim Lesen (SECRETS_DIR/TOKEN_FILE), Verzeichnis wird bei Bedarf mit 700 angelegt, sonst
    würde ein Refresh auf einem frischen Rechner (Verzeichnis existiert noch nicht) scheitern."""
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(TOKEN_FILE.parent, 0o700)   # Secrets-Verzeichnis — niemals gruppen-/weltlesbar
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    os.chmod(TOKEN_FILE, 0o600)          # Refresh-Token — niemals gruppen-/weltlesbar


def cmd_auth() -> dict:
    """Einmaliger OAuth-Flow im Browser. Danach trägt das Refresh-Token die headless-Läufe."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CRED_FILE.exists():
        _die(f"{CRED_FILE} fehlt.\n"
             "→ Google Cloud Console: Projekt anlegen, Gmail API aktivieren,\n"
             "  OAuth-Client-ID vom Typ 'Desktop-App' erzeugen, JSON hierher speichern.\n"
             "  WICHTIG: Zustimmungsbildschirm auf 'In Produktion' veroeffentlichen —\n"
             "  im Status 'Testing' verfaellt das Refresh-Token nach 7 Tagen.")
    flow = InstalledAppFlow.from_client_secrets_file(str(CRED_FILE), SCOPES)
    # access_type=offline + prompt=consent erzwingen ein Refresh-Token (sonst nur Access-Token)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    _save_token(creds)
    email = _get(_client(creds), "/profile").get("emailAddress")
    # Phase 63A: TOKEN_FILE liegt bewusst NICHT mehr unter PROJECT_ROOT (relative_to würde
    # ValueError werfen) — absoluter Pfad statt projektrelativem.
    return {"ok": True, "account": email, "token_file": str(TOKEN_FILE)}


def _creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    if not TOKEN_FILE.exists():
        _die(f"Nicht autorisiert ({TOKEN_FILE} fehlt).\n"
             "→ einmalig ausfuehren: python -m pipeline.gmail_client auth")
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())     # still, ohne Browser — der headless-Fall
            _save_token(creds)
        else:
            _die("Token ungueltig und nicht erneuerbar.\n"
                 "→ Haeufigste Ursache: die Google-App steht auf 'Testing' (Refresh-Token "
                 "verfaellt nach 7 Tagen). Auf 'In Produktion' setzen, dann erneut 'auth'.")
    return creds


def _client(creds) -> httpx.Client:
    return httpx.Client(
        headers={"Authorization": f"Bearer {creds.token}"},
        timeout=30.0,
    )


def _get(cl: httpx.Client, path: str, **params) -> dict:
    r = cl.get(API + path, params=params or None)
    if r.status_code >= 400:
        # Der Token-Wert steht im Header, nicht im Body — die Fehlermeldung ist unbedenklich.
        _die(f"Gmail-API {r.status_code} bei GET {path}: {r.text[:400]}")
    return r.json()


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────────────
def _header_map(headers: list) -> dict:
    return {h["name"].lower(): h["value"] for h in headers or []}


def _headers(msg: dict) -> dict:
    return _header_map(msg.get("payload", {}).get("headers", []))


def _iso(internal_date_ms) -> str:
    ts = int(internal_date_ms) / 1000
    return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ")


_CHARSET_RE = re.compile(r'charset\s*=\s*"?([\w.:-]+)"?', re.IGNORECASE)


def _charset_of(payload: dict) -> "str | None":
    """Content-Type-Charset DIESES MIME-Teils (P2-12, Phase 67D) — `payload["headers"]` trägt
    ihn bereits (für einen Top-Level-Payload die echten RFC822-Header, für einen `parts[]`-Eintrag
    die MIME-Header genau dieses Teils), er wurde bisher nur nie gelesen. `None` wenn kein
    Content-Type-Header vorhanden ist oder er kein `charset=…` nennt — der Aufrufer fällt dann
    auf UTF-8 zurück."""
    ct = _header_map(payload.get("headers", [])).get("content-type", "")
    m = _CHARSET_RE.search(ct)
    return m.group(1) if m else None


def _decode(data: str, charset: "str | None" = None) -> str:
    """Base64url-Rohbytes eines Teils dekodieren: zuerst streng als UTF-8, sonst mit dem
    MIME-Charset des Teils (P2-12), zuletzt UTF-8 mit Ersatzzeichen.

    Warum UTF-8 zuerst (gemessen am echten Postfach, 05.11.2026): Die Gmail-API liefert
    `body.data` bei `format=full` bereits nach UTF-8 umkodiert, laesst den Content-Type-Header
    des Teils aber unveraendert (`charset="iso-8859-1"`, in der Rohform steht `Ol=E1`, in
    `body.data` `Ol\\xc3\\xa1`). Alle 18 Teile mit ISO-8859-1 oder Windows-1252 im Kopf aus
    100 Bewerbungsmails waren so; mit dem Kopf dekodiert wurde aus „ä“ ein „Ã¤“. Echte
    Latin-1-Bytes mit Umlauten sind dagegen fast nie gueltiges UTF-8, fallen also weiter auf
    den Charset des Teils zurueck. Kaputte/exotische Angaben fuehren nie zum Absturz."""
    raw = base64.urlsafe_b64decode(data.encode("utf-8"))
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass   # keine UTF-8-Bytes: echter Fremd-Charset, der Kopf des Teils gilt
    if charset:
        try:
            return raw.decode(charset, errors="replace")
        except (LookupError, ValueError):
            pass   # unbekannter/kaputter Charset-Name — Fallback unten, wie bisher
    return raw.decode("utf-8", errors="replace")


# HTML→Text seit Phase 25 in pipeline/htmltext.py (gemeinsam mit search_index.py, nicht dupliziert).
# Viele Bewerbermanagement-Systeme schicken NUR text/html — ohne diesen Schritt bekommt der
# Skill Markup statt Inhalt.
from pipeline.htmltext import entkleiden as _entkleiden


# P2-16 (Phase 91): Wann gilt ein text/plain-Teil als STUMMEL — siehe `_alternative_waehlen`.
# Gemessen am echten Postfach (16 Mails mit beiden Teilen, 26.08.2026): Bei normalen Absendern
# sind 0-30 % der Inhaltswoerter des HTML-Teils im plain-Teil nicht enthalten (blosse
# Umbruch- und Entity-Unterschiede), bei den LinkedIn-Stummeln 51-74 %. 0.40 liegt in der
# Luecke. Die Mindestzahl faengt nur Degenerationsfaelle ab (winziger HTML-Teil, bei dem ein
# einzelnes neues Wort schon 100 % ergaebe).
STUMMEL_ANTEIL = 0.40
STUMMEL_MINDESTWOERTER = 12

# Unsichtbare Fuellzeichen, mit denen Marketing-Mails die Vorschauzeile strecken (LinkedIn
# nutzt U+034F). Sie sind kein Text und wuerden den Vergleich nur verwaessern.
_UNSICHTBAR = re.compile(r"[\u034f\u200b-\u200d\u2060\ufeff]")
_URL_ODER_MAIL = re.compile(r"https?://\S+|\S+@\S+\.\S+")
_INHALTSWORT = re.compile(r"[a-z\u00e0-\u00ff0-9]{4,}")


def _inhaltswoerter(text: str) -> list:
    """Woerter ab vier Zeichen, ohne Links, Mailadressen und unsichtbare Fuellzeichen.

    Bewusst wortweise statt zeichenweise: Der plain-Teil bricht Zeilen oft bei 72 Zeichen um,
    der HTML-Teil nicht. Ein Zeichen- oder Zeilenvergleich haelt denselben Satz dann faelschlich
    fuer neuen Inhalt — gemessen an sieben normalen Mails, die so auf bis zu 641 angeblich neue
    Zeichen kamen. Auf Wortebene faellt dieser Scheinunterschied weg.
    """
    roh = _URL_ODER_MAIL.sub(" ", _UNSICHTBAR.sub(" ", text)).lower()
    return _INHALTSWORT.findall(roh)


def _ist_stummel(plain: str, html_text: str) -> bool:
    """Traegt der plain-Teil die Nachricht NICHT, die im HTML-Teil steht?

    Mass ist der Anteil der Inhaltswoerter des HTML-Teils, die im plain-Teil ueberhaupt nicht
    vorkommen. Bewusst ein ANTEIL und keine absolute Menge: LinkedIn haengt an jede Mail einen
    Block Stellenwerbung, der die absolute Zahl neuer Woerter aufblaeht. Ohne diesen Block
    faellt sie von 40-75 auf 18-20 — der Anteil dagegen steigt sogar (0,55 auf 0,63), weil
    Werbung Zaehler und Nenner gleichermassen fuellt. Der Anteil misst also die Stummel-Eigenschaft
    selbst, die absolute Zahl nur LinkedIns Werbelaune.

    Reine Laengen taugen als Mass gar nicht: Der plain-Teil einer LinkedIn-Absage ist mit 2296
    Zeichen sogar LAENGER als der Text aus ihrem HTML-Teil (1711) — er besteht fast vollstaendig
    aus Tracking-URLs.
    """
    im_plain = set(_inhaltswoerter(plain))
    im_html = _inhaltswoerter(html_text)
    if not im_html:
        return False
    fehlend = [w for w in im_html if w not in im_plain]
    return (len(fehlend) / len(im_html) >= STUMMEL_ANTEIL
            and len(set(fehlend)) >= STUMMEL_MINDESTWOERTER)


def _erster_teil(payload: dict, mime: str) -> str:
    """Erster Teil des gesuchten MIME-Typs in der Tiefensuche — dieselbe Reihenfolge, in der
    `_body_text` schon immer gesucht hat."""
    if payload.get("mimeType") == mime and payload.get("body", {}).get("data"):
        return _decode(payload["body"]["data"], _charset_of(payload))
    for part in payload.get("parts") or []:
        treffer = _erster_teil(part, mime)
        if treffer:
            return treffer
    return ""


def _alternative_waehlen(payload: dict) -> str:
    """Waehlt in einem `multipart/alternative` den Teil, der die Nachricht wirklich traegt.

    ANLASS (Echtfall, 26.08.2026): LinkedIn verschickt Absagen als multipart/alternative mit
    einem 2,3-KB-text/plain-Teil, der nur die Kopfzeile „Your update from <Firma>“ plus einen
    Footer aus Tracking-URLs enthaelt. Der eigentliche Satz („Unfortunately, we will not be
    moving forward with your application“) steht AUSSCHLIESSLICH im 143-KB-HTML-Teil. Die
    fruehere Regel „bevorzuge text/plain“ lieferte der Klassifikation damit einen Text, in dem
    eine Absage gar nicht stehen KANN; fuenf Absagen landeten so faelschlich als
    „Eingangsbestaetigung“ im Tracker. Kein Fehler des Skills — dem Lauf fehlte der Text.

    RFC 2046 macht die Teile eines `multipart/alternative` zu gleichwertigen Darstellungen
    DERSELBEN Nachricht. Fehlt im plain-Teil, was im HTML-Teil steht, ist er keine gleichwertige
    Darstellung mehr, sondern ein Platzhalter — dann gilt der HTML-Teil. Sonst bleibt es bei
    text/plain, das bei ordentlichen Absendern sauberer ist als jedes Tag-Strippen.

    Die Regel greift NUR in `alternative`: In `mixed` sind die Teile eigenstaendige Dokumente
    (Mailtext plus Anhang), dort waere jeder Vergleich sinnlos.
    """
    plain = _erster_teil(payload, "text/plain")
    html = _erster_teil(payload, "text/html")
    if not html:
        return plain
    html_text = _entkleiden(html)
    if not plain:
        return html_text
    return html_text if _ist_stummel(plain, html_text) else plain


def _body_text(payload: dict) -> str:
    """Bevorzugt text/plain; faellt auf text/html zurueck (dann von Tags befreit). Dekodiert seit
    P2-12 (Phase 67D) mit dem Content-Type-Charset DIESES Teils (`_charset_of`) statt immer
    UTF-8 zu erzwingen — ältere Firmen-/ATS-Mailsysteme senden teils ISO-8859-1/Windows-1252,
    sonst entstehen Ersatzzeichen genau im klassifikationsrelevanten Text. UTF-8 bleibt Fallback
    (kein/unbekannter Charset).

    Seit P2-16 (Phase 91) mit einer Ausnahme: Ist der plain-Teil eines `multipart/alternative`
    nur ein Stummel, gewinnt der HTML-Teil — Begruendung in `_alternative_waehlen`."""
    mime = payload.get("mimeType", "")
    data = payload.get("body", {}).get("data")
    charset = _charset_of(payload)
    if data and mime == "text/plain":
        return _decode(data, charset)
    if mime == "multipart/alternative":
        gewaehlt = _alternative_waehlen(payload)
        if gewaehlt:
            return gewaehlt
    for part in payload.get("parts") or []:
        text = _body_text(part)
        if text:
            return text
    if data and mime == "text/html":
        return _entkleiden(_decode(data, charset))
    return ""


def _record(msg: dict, me: str) -> dict:
    """Mechanische Felder im Schema von pipeline/gmail_ingest.py — keine Beurteilung."""
    h = _headers(msg)
    from_addr = h.get("from", "")
    return {
        "gmail_message_id": msg["id"],
        "gmail_thread_id": msg.get("threadId"),
        # Richtung deterministisch aus dem Konto ableiten, statt sie das Modell raten zu lassen
        "direction": "outgoing" if me and me.lower() in from_addr.lower() else "incoming",
        "from_addr": from_addr,
        "to_addr": h.get("to", ""),
        "subject": h.get("subject", ""),
        "snippet": msg.get("snippet", ""),
        "received_at": _iso(msg.get("internalDate", 0)),
    }


# ── Fassaden-Dispatch (Phase 71F) ───────────────────────────────────────────────────────
def _provider() -> str:
    """Konfigurierter Mail-Provider aus mail_settings.json. Default 'gmail' bei fehlender/
    kaputter Datei — s. Moduldocstring."""
    from pipeline import imap_mail
    return imap_mail.provider()


# P2-51 (Vertrag V8): Absender mit Leerzeichen, Klammern oder Anfuehrungszeichen wuerden die
# Gmail-/IMAP-Query-Syntax zerlegen (s. `_top_level_chunks`/`_split_or` in `pipeline.imap_mail`)
# — sie werden uebersprungen statt escaped, damit die Query nie kaputtgeht.
_UNSICHERER_ABSENDER_ZEICHEN = re.compile(r"[\s()\"']")


def _suchprofil_ausschluss_absender() -> list:
    """Liest `email_check.ausschluss_absender` aus `config/suchprofile.yaml` (P2-51, Vertrag V8)
    — die privaten Rausch-Absender einer Installation stehen seither dort, nicht mehr fest im
    Skill-Text. Fehlende Datei, kaputtes YAML oder fehlender Schluessel ergeben eine leere Liste
    (Bestandsverhalten ohne den Schalter `--suchprofil-ausschluesse`). Importiert nur die
    Pfadkonstante aus `pipeline.suchprofil`, aendert das Modul nicht."""
    from pipeline import suchprofil

    pfad = suchprofil.SUCHPROFILE_PATH
    if not pfad.exists():
        return []
    try:
        daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    absender = (daten.get("email_check") or {}).get("ausschluss_absender") or []
    return list(absender) if isinstance(absender, list) else []


def _suchprofil_ausschluss_query_teil() -> str:
    """Baut den Query-Zusatz ` -from:(a OR b)` fuer `cmd_search(..., suchprofil_ausschluesse=True)`.
    Eintraege mit Leerzeichen, Klammern oder Anfuehrungszeichen werden mit Warnung auf stderr
    uebersprungen statt die Query zu zerlegen; bleibt danach nichts uebrig (leere/fehlende Liste),
    ist der Rueckgabewert ein leerer String — die Query bleibt dann unveraendert."""
    gueltig = []
    for eintrag in _suchprofil_ausschluss_absender():
        wert = str(eintrag).strip()
        if not wert:
            continue
        if _UNSICHERER_ABSENDER_ZEICHEN.search(wert):
            print(f"gmail_client: Absender {eintrag!r} enthaelt Leerzeichen, Klammern oder "
                  "Anfuehrungszeichen und wird uebersprungen.", file=sys.stderr)
            continue
        gueltig.append(wert)
    return " -from:(" + " OR ".join(gueltig) + ")" if gueltig else ""


# ── Verben ────────────────────────────────────────────────────────────────────────────
def cmd_search(query: str, max_results: int, suchprofil_ausschluesse: bool = False) -> list:
    if not query or not query.strip():
        _die("--query ist Pflicht. Ohne Suchbegriff wuerde der Lauf das ganze Postfach lesen "
             "— das verbietet die Datenschutzgrenze in .claude/skills/email-check/SKILL.md.")
    if suchprofil_ausschluesse:
        # P2-51 (V8): private Rausch-Absender kommen aus config/suchprofile.yaml statt fest im
        # Skill-Text zu stehen — gilt fuer Gmail UND IMAP (imap_mail.translate_query kennt
        # -from:(...) bereits, s. backend/tests/test_gmail_ausschluss.py).
        query = query + _suchprofil_ausschluss_query_teil()
    if _provider() == "imap":
        from pipeline import imap_mail
        return imap_mail.cmd_search(query, max_results)
    n = max(1, min(int(max_results), MAX_HARD))
    creds = _creds()
    with _client(creds) as cl:
        me = _get(cl, "/profile").get("emailAddress", "")
        listing = _get(cl, "/messages", q=query, maxResults=n)
        out = []
        for stub in listing.get("messages", []):
            msg = _get(cl, f"/messages/{stub['id']}", format="metadata",
                       metadataHeaders=["From", "To", "Subject", "Date"])
            out.append(_record(msg, me))
    return out


def cmd_get(message_id: str) -> dict:
    if _provider() == "imap":
        from pipeline import imap_mail
        return imap_mail.cmd_get(message_id)
    creds = _creds()
    with _client(creds) as cl:
        me = _get(cl, "/profile").get("emailAddress", "")
        msg = _get(cl, f"/messages/{message_id}", format="full")
    rec = _record(msg, me)
    rec["body"] = _body_text(msg.get("payload", {}))
    return rec


def cmd_draft(to: str, subject: str, body: str, in_reply_to=None) -> dict:
    """Legt einen ENTWURF an. Es gibt in diesem Modul keinen Weg, ihn abzuschicken."""
    if not to or not to.strip():
        _die("--to ist Pflicht: das Postfach verlangt mindestens einen Empfaenger auch fuer Entwuerfe.\n"
             "Ist die Adresse unbekannt, die eigene Adresse eintragen (s. tasks/lessons.md).")
    if _provider() == "imap":
        from pipeline import imap_mail
        return imap_mail.cmd_draft(to, subject, body, in_reply_to=in_reply_to)
    creds = _creds()
    mail = EmailMessage()
    mail["To"] = to
    mail["Subject"] = subject
    mail.set_content(body)

    payload = {}
    with _client(creds) as cl:
        if in_reply_to:
            orig = _get(cl, f"/messages/{in_reply_to}", format="metadata",
                        metadataHeaders=["Message-Id", "References"])
            h = _headers(orig)
            mid = h.get("message-id")
            if mid:
                mail["In-Reply-To"] = mid
                mail["References"] = (h.get("references", "") + " " + mid).strip()
            payload["threadId"] = orig.get("threadId")   # haengt den Entwurf in den Thread

        payload["raw"] = base64.urlsafe_b64encode(mail.as_bytes()).decode("utf-8")
        r = cl.post(API + "/drafts", json={"message": payload})
        if r.status_code >= 400:
            _die(f"Gmail-API {r.status_code} beim Anlegen des Entwurfs: {r.text[:400]}")
        d = r.json()

    return {"ok": True, "draft_id": d.get("id"),
            "thread_id": (d.get("message") or {}).get("threadId"),
            "hinweis": "Entwurf angelegt — nicht verschickt. Du prüfst und sendest selbst."}


# ── CLI ───────────────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(prog="pipeline.gmail_client", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("auth", help="einmaliger OAuth-Flow im Browser")

    p_s = sub.add_parser("search", help="Mails suchen (read-only)")
    p_s.add_argument("--query", required=True, help="Gmail-Suchsyntax, z. B. 'newer_than:2d subject:(Bewerbung)'")
    p_s.add_argument("--max", type=int, default=MAX_DEFAULT, help=f"Default {MAX_DEFAULT}, Hard-Cap {MAX_HARD}")
    p_s.add_argument("--suchprofil-ausschluesse", action="store_true",
                      help="haengt email_check.ausschluss_absender aus config/suchprofile.yaml "
                           "als -from:(...) an die Query an")

    p_g = sub.add_parser("get", help="eine Mail im Volltext lesen")
    p_g.add_argument("message_id")

    p_d = sub.add_parser("draft", help="Gmail-ENTWURF anlegen (kein Versand)")
    p_d.add_argument("--to", required=True)
    p_d.add_argument("--subject", required=True)
    body = p_d.add_mutually_exclusive_group(required=True)
    body.add_argument("--body-file", help="Datei mit dem Mailtext (empfohlen)")
    body.add_argument("--body", help="Mailtext direkt")
    p_d.add_argument("--in-reply-to", help="message_id der Mail, auf die geantwortet wird (Threading)")

    a = ap.parse_args()
    if a.cmd == "auth":
        out = cmd_auth()
    elif a.cmd == "search":
        out = cmd_search(a.query, a.max, a.suchprofil_ausschluesse)
    elif a.cmd == "get":
        out = cmd_get(a.message_id)
    else:
        text = Path(a.body_file).read_text(encoding="utf-8") if a.body_file else a.body
        out = cmd_draft(a.to, a.subject, text, a.in_reply_to)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
