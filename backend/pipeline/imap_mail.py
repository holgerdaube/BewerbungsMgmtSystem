#!/usr/bin/env python3
"""IMAP-Zugang als zweiter Mail-Provider neben Gmail (Phase 71F — Produktisierung).

Ziel: Kunden ohne Gmail (GMX, Web.de, mailbox.org, Posteo, iCloud-Mail mit App-Passwort, …)
sollen dieselben Skills nutzen können. `pipeline.gmail_client` bleibt die FASSADE, die
Skills/Module rufen — sie dispatcht nach `mail_settings.json` entweder in ihren eigenen
Gmail-Codepfad oder hierher. Dieses Modul kennt AUSSCHLIESSLICH Stdlib (`imaplib`/`email`),
keine dritte Mail-Bibliothek.

SICHERHEITSGARANTIE (identisch zu gmail_client.py, s. dortiger Modul-Docstring):
    Es gibt genau drei Verben: `cmd_search`, `cmd_get`, `cmd_draft`. Kein Senden, kein
    Löschen, kein Labeln — nicht abgeschaltet, sondern nicht vorhanden. `cmd_draft` legt
    einen Entwurf AUSSCHLIESSLICH per IMAP APPEND mit `\\Draft`-Flag im konfigurierten
    Entwürfe-Ordner ab. Dieses Modul importiert NIRGENDS `smtplib` — das ist Bestandteil des
    Sicherheitsmodells, nicht nur eine Konvention (s. `backend/tests/test_kein_sendcodepfad.py`).

Konfiguration: `mail_settings.json` im Secrets-Verzeichnis (`BMS_SECRETS_DIR`, Default
`~/.bewerbung_mgmt_secrets/`, Datei chmod 600, Verzeichnis chmod 700 — exakt das Muster aus
`gmail_client._save_token`). Fehlt die Datei, gilt Provider "gmail" (Bestandsverhalten).

Query-Übersetzung (Gmail-Suchsyntax → IMAP): `translate_query()` erkennt `after:`/`before:`/
`newer_than:Nd|m|y`/`from:`/`subject:` (auch geklammerte OR-Gruppen und Anführungszeichen-
Phrasen) sowie freien Text. Alles andere (z. B. `-in:chats`, `category:promotions` — Gmail-
Kategorien/Labels haben kein IMAP-Äquivalent) wird ignoriert und als Hinweis auf stderr
ausgegeben. Nur das Datumsfenster (SINCE/BEFORE) wird als echtes IMAP-SEARCH-Kriterium
verwendet; alle Absender-/Betreff-/Freitext-Kriterien werden NACH dem Header-Fetch in Python
angewendet — bewusst einfach gehalten (kein IMAP-SEARCH-Charset-Ärger bei Umlauten) und
großzügig statt streng: Positivkriterien werden ODER-verknüpft (nicht UND, nicht die
ursprüngliche Klammerstruktur), Negativkriterien schließen aus. „Recall vor Präzision, die
Skills filtern nach" (Spec-Wortlaut) — für die tatsächlich genutzten Skill-Queries (s.
`.claude/skills/email-check/SKILL.md`) ist das nachweislich exakt (dort steht ohnehin nur EINE
Positiv-Gruppe). Durchsucht wird ausschließlich der Ordner INBOX (kein mail_settings-Feld für
einen Such-Ordner vorgesehen) — bekannte Grenze, s. Abschlussbericht Phase 71F.

`get`/`draft` bauen auf der RFC-5322-Message-ID auf: `search`/`get` liefern sie im Feld
`gmail_message_id` (Namensbestand aus Kompatibilitätsgründen — Skills/DB kennen dieses Feld
als opaken eindeutigen Bezeichner, nicht als Gmail-spezifisches Format). `get <id>` und
`draft --in-reply-to <id>` nehmen exakt diesen String wieder entgegen.
"""
import base64
import contextlib
import datetime
import email
import email.utils
import imaplib
import json
import os
import re
import sys
import time
from email.header import decode_header, make_header
from email.message import EmailMessage
from pathlib import Path

from pipeline.htmltext import entkleiden as _entkleiden

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent   # Bewerbung_Mgmt_System/
# Gleiches Muster wie pipeline.gmail_client.SECRETS_DIR (Phase 63A) — Override per BMS_SECRETS_DIR.
SECRETS_DIR = Path(os.environ.get("BMS_SECRETS_DIR", str(Path.home() / ".bewerbung_mgmt_secrets")))
SETTINGS_FILE = SECRETS_DIR / "mail_settings.json"

MAX_HARD = 200
MAX_DEFAULT = 50
DEFAULT_DRAFTS_FOLDER = "Drafts"

_REQUIRED_IMAP_FIELDS = ("host", "username", "password")
_POOL_CAP_MIN = 500      # Mindest-Kandidatenpool, wenn der Zeitfilter allein nicht eng genug ist.


def _die(msg: str) -> "NoReturn":       # noqa: F821
    print(msg, file=sys.stderr)
    raise SystemExit(2)


# ── Einstellungsdatei ────────────────────────────────────────────────────────────────────
def load_settings() -> dict:
    """Liest mail_settings.json. Default `{"provider": "gmail"}` bei fehlender, leerer oder
    kaputter Datei — jede Installation ohne diese Datei verhält sich exakt wie vor Phase 71F."""
    if not SETTINGS_FILE.exists():
        return {"provider": "gmail"}
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"provider": "gmail"}
    if not isinstance(data, dict) or not data.get("provider"):
        return {"provider": "gmail"}
    return data


def save_settings(data: dict) -> None:
    """Schreibt mail_settings.json chmod 600 (Muster `gmail_client._save_token`, Phase 63A) —
    das Passwort landet NUR hier, nie in der DB, nie in einem Log."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(SETTINGS_FILE.parent, 0o700)
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(SETTINGS_FILE, 0o600)


def provider() -> str:
    return (load_settings().get("provider") or "gmail").strip().lower()


def _require_imap_settings(settings: dict) -> None:
    fehlend = [f for f in _REQUIRED_IMAP_FIELDS if not str(settings.get(f) or "").strip()]
    if fehlend:
        from app.sprache import tx    # erst hier: Dieses Modul läuft auch als reines Werkzeug ohne Datenbank
        _die(tx("IMAP-Konfiguration unvollstaendig ({felder} fehlt) - "
                "bitte unter Einstellungen > E-Mail-Konto ausfuellen und speichern.",
                felder=", ".join(fehlend)))


# ── IMAP "modified UTF-7" (RFC 3501 §5.1.3) ─────────────────────────────────────────────
# Stdlib hat dafür keinen Codec (Pythons eingebautes "utf-7" ist der leicht abweichende
# Standard-UTF-7). Wichtig für deutsche Anbieter: Ordnernamen wie "Entwürfe" enthalten
# Nicht-ASCII-Zeichen; ohne Kodierung lehnen manche Server das SELECT/APPEND ab.
def _imap_utf7_encode(name: str) -> str:
    out, i, n = [], 0, len(name)
    while i < n:
        ch = name[i]
        if ch == "&":
            out.append("&-")
            i += 1
            continue
        if 0x20 <= ord(ch) <= 0x7E:
            out.append(ch)
            i += 1
            continue
        j = i
        while j < n and not (name[j] != "&" and 0x20 <= ord(name[j]) <= 0x7E):
            j += 1
        chunk = name[i:j]
        b64 = base64.b64encode(chunk.encode("utf-16-be")).decode("ascii")
        b64 = b64.rstrip("=").replace("/", ",")
        out.append("&" + b64 + "-")
        i = j
    return "".join(out)


def _mailbox_arg(name: str) -> str:
    """IMAP-Mailbox-Argument: UTF-7-kodiert + IMAP-quoted-string (Leerzeichen/Umlaute in
    Ordnernamen wie "Entwürfe" sind sonst zwei unabhängige Stolperfallen)."""
    encoded = _imap_utf7_encode(name)
    escaped = encoded.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _quote_search_string(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ── Verbindung ────────────────────────────────────────────────────────────────────────────
def _connect(settings: dict) -> imaplib.IMAP4:
    from app.sprache import tx    # erst hier: Dieses Modul läuft auch als reines Werkzeug ohne Datenbank
    host = str(settings.get("host") or "").strip()
    port = int(settings.get("port") or 993)
    security = str(settings.get("security") or "ssl").strip().lower()
    username = str(settings.get("username") or "").strip()
    password = settings.get("password") or ""
    try:
        if security == "starttls":
            imap = imaplib.IMAP4(host, port)
            imap.starttls()
        else:
            imap = imaplib.IMAP4_SSL(host, port)
    except (OSError, imaplib.IMAP4.error) as exc:
        _die(tx("IMAP-Verbindung zu {host}:{port} fehlgeschlagen: {grund}", host=host, port=port, grund=exc))
    try:
        imap.login(username, password)
    except imaplib.IMAP4.error as exc:
        with contextlib.suppress(Exception):
            imap.logout()
        _die(tx("IMAP-Login fuer {benutzer} fehlgeschlagen: {grund}", benutzer=repr(username), grund=exc))
    return imap


def _safe_logout(imap: imaplib.IMAP4) -> None:
    """Zwei unabhängig geschützte Schritte (Lehre Phase 64B, tasks/lessons.md
    „Fehlerpfade/catch-all"): scheitert `close()`, darf das `logout()` nicht verhindern."""
    with contextlib.suppress(Exception):
        imap.close()
    with contextlib.suppress(Exception):
        imap.logout()


def test_connection(settings: dict) -> dict:
    """Login + Auswahl des Entwürfe-Ordners (Spec 71F Schritt 4) — reine Lesbarkeitsprüfung,
    verändert nichts. `_die()` bei jedem Fehlschlag (Konsistenz mit dem Rest des Moduls); der
    Aufrufer (routes_mail_settings.test_mail_settings) fängt `SystemExit` wie main.py es bei
    `gmail_client.cmd_get` bereits tut (stderr umleiten, Klartext an den Client reichen)."""
    _require_imap_settings(settings)
    folder = str(settings.get("drafts_folder") or DEFAULT_DRAFTS_FOLDER).strip() or DEFAULT_DRAFTS_FOLDER
    from app.sprache import tx    # erst hier: Dieses Modul läuft auch als reines Werkzeug ohne Datenbank
    imap = _connect(settings)
    try:
        typ, data = imap.select(_mailbox_arg(folder), readonly=True)
        if typ != "OK":
            _die(tx("IMAP verbunden, aber Entwuerfe-Ordner '{ordner}' nicht auswaehlbar: {grund}",
                    ordner=folder, grund=data))
    finally:
        _safe_logout(imap)
    return {"ok": True,
            "meldung": tx("IMAP-Verbindung erfolgreich: {benutzer} @ {host}, Ordner '{ordner}' gefunden.",
                          benutzer=settings.get('username'), host=settings.get('host'), ordner=folder)}


# ── Query-Übersetzung (Gmail-Suchsyntax → IMAP-Datumsfenster + Python-Nachfilter) ──────────
_CHUNK_RE = re.compile(r"^(-)?([A-Za-z_]+):(.*)$", re.S)
_DATE_RE = re.compile(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$")
_NEWER_RE = re.compile(r"^(\d+)([dmy])$", re.I)
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def _top_level_chunks(text: str) -> list:
    """Zerlegt eine Query in Leerzeichen-getrennte Teile — Klammern (beliebig verschachtelt)
    und Anführungszeichen halten den Inhalt zusammen. Trägt sowohl `from:(a OR b)` (EIN Chunk)
    als auch `(subject:(...) OR from:(...))` (ebenfalls EIN Chunk, wird von `_process_chunk`
    rekursiv aufgelöst)."""
    chunks, buf, depth, in_quote = [], [], 0, False
    for ch in text:
        if in_quote:
            buf.append(ch)
            if ch == '"':
                in_quote = False
            continue
        if ch == '"':
            in_quote = True
            buf.append(ch)
            continue
        if ch == "(":
            depth += 1
            buf.append(ch)
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
            continue
        if ch.isspace() and depth == 0:
            if buf:
                chunks.append("".join(buf))
                buf = []
            continue
        buf.append(ch)
    if buf:
        chunks.append("".join(buf))
    return chunks


def _split_or(s: str) -> list:
    """Wie `_top_level_chunks`, aber Trenner ist das literale " OR " (Gmail-Konvention) statt
    Whitespace — für den Inhalt EINES `from:(...)`/`subject:(...)`-Klammerpaars."""
    parts, buf, in_quote, i, n = [], [], False, 0, len(s)
    while i < n:
        if not in_quote and s[i:i + 4] == " OR ":
            parts.append("".join(buf).strip())
            buf = []
            i += 4
            continue
        ch = s[i]
        if ch == '"':
            in_quote = not in_quote
        buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf).strip())
    return [_strip_quotes(p) for p in parts if p.strip()]


def _parse_date(rest: str) -> "datetime.date | None":
    m = _DATE_RE.match(_strip_quotes(rest.strip()))
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    try:
        return datetime.date(y, mo, d)
    except ValueError:
        return None


def _parse_newer_than(rest: str) -> "datetime.date | None":
    m = _NEWER_RE.match(rest.strip())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    today = datetime.date.today()
    if unit == "d":
        return today - datetime.timedelta(days=n)
    if unit == "m":
        return today - datetime.timedelta(days=30 * n)
    return today - datetime.timedelta(days=365 * n)   # 'y'


def _process_chunk(chunk: str, ctx: dict) -> None:
    chunk = chunk.strip()
    if not chunk or chunk == "OR":
        return
    if chunk.startswith("(") and chunk.endswith(")"):
        for sub in _top_level_chunks(chunk[1:-1]):
            _process_chunk(sub, ctx)
        return
    m = _CHUNK_RE.match(chunk)
    if not m:
        value = _strip_quotes(chunk)
        if value:
            ctx["positive"].append(("text", value))
        return
    negiert, keyword, rest = m.group(1) is not None, m.group(2).lower(), m.group(3)
    if keyword in ("from", "subject"):
        if rest.startswith("(") and rest.endswith(")"):
            values = _split_or(rest[1:-1])
        else:
            values = [_strip_quotes(rest)]
        bucket = ctx["negative"] if negiert else ctx["positive"]
        for v in values:
            if v:
                bucket.append((keyword, v))
        return
    if keyword in ("after", "before"):
        d = _parse_date(rest)
        if d is None:
            ctx["notes"].append(f"IMAP: Datum in '{chunk}' nicht erkannt, Teil wird ignoriert.")
            return
        if keyword == "after":
            ctx["since"] = max(ctx["since"], d) if ctx["since"] else d
        else:
            ctx["before"] = min(ctx["before"], d) if ctx["before"] else d
        return
    if keyword == "newer_than":
        d = _parse_newer_than(rest)
        if d is None:
            ctx["notes"].append(f"IMAP: '{chunk}' nicht erkannt, Teil wird ignoriert.")
            return
        ctx["since"] = max(ctx["since"], d) if ctx["since"] else d
        return
    ctx["notes"].append(f"IMAP: Query-Teil '{chunk}' hat keine IMAP-Entsprechung und wird ignoriert.")


def translate_query(query: str) -> dict:
    """Rückgabe: {"since": date|None, "before": date|None, "positive": [(feld, wert), ...],
    "negative": [(feld, wert), ...], "notes": [str, ...]} — feld ∈ {"from", "subject", "text"}.
    Reine Funktion, kein IMAP-/Netzzugriff (s. `backend/tests/test_imap_query_translation.py`)."""
    ctx = {"since": None, "before": None, "positive": [], "negative": [], "notes": []}
    for chunk in _top_level_chunks(query or ""):
        _process_chunk(chunk, ctx)
    return ctx


def _imap_date(d: datetime.date) -> str:
    # BEWUSST kein strftime("%b") — das ist locale-abhängig (z. B. deutsches "Mär" statt "Mar")
    # und IMAP-SEARCH-Datumsangaben verlangen englische Monatskürzel (RFC 3501 §9).
    return f"{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year:04d}"


def _date_criteria(parsed: dict) -> list:
    crit = []
    if parsed["since"]:
        crit += ["SINCE", _imap_date(parsed["since"])]
    if parsed["before"]:
        crit += ["BEFORE", _imap_date(parsed["before"])]
    return crit


def _search_uids(imap: imaplib.IMAP4, parsed: dict) -> list:
    criteria = _date_criteria(parsed) or ["ALL"]
    typ, data = imap.uid("SEARCH", None, *criteria)
    if typ != "OK":
        _die(f"IMAP-Suche fehlgeschlagen: {data}")
    return data[0].split() if data and data[0] else []


def _cap_pool(uids: list, max_results: int) -> list:
    cap = max(_POOL_CAP_MIN, max_results * 20)
    return uids[-cap:] if len(uids) > cap else uids   # UIDs steigen chronologisch (RFC 3501 §2.3.1.1)


def _matches_leaf(record: dict, field: str, value: str) -> bool:
    value = value.lower()
    if field == "from":
        return value in (record.get("from_addr") or "").lower()
    if field == "subject":
        return value in (record.get("subject") or "").lower()
    haystack = f'{record.get("from_addr") or ""} {record.get("subject") or ""}'.lower()
    return value in haystack


def _apply_leaf_filters(records: list, parsed: dict) -> list:
    positive, negative = parsed["positive"], parsed["negative"]
    out = []
    for r in records:
        if positive and not any(_matches_leaf(r, f, v) for f, v in positive):
            continue
        if any(_matches_leaf(r, f, v) for f, v in negative):
            continue
        out.append(r)
    return out


# ── Header-/Body-Dekodierung ────────────────────────────────────────────────────────────
def _decode_header_value(raw: "str | None") -> str:
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except (UnicodeDecodeError, LookupError, ValueError):
        return raw


def _parse_date_header(raw: "str | None") -> str:
    if not raw:
        return ""
    try:
        dt = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return ""
    if dt is None:
        return ""
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _record_from_headers(msg, settings: dict) -> dict:
    """Mechanische Felder — identische Struktur zu `gmail_client._record()`. `gmail_thread_id`
    bleibt None (generisches IMAP kennt kein Thread-Konzept), `snippet` bleibt leer (kein
    Body-Fetch im Such-Lauf — s. Moduldocstring)."""
    from_addr = _decode_header_value(msg.get("From"))
    me = str(settings.get("username") or "").lower()
    return {
        "gmail_message_id": (msg.get("Message-ID") or "").strip(),
        "gmail_thread_id": None,
        "direction": "outgoing" if me and me in from_addr.lower() else "incoming",
        "from_addr": from_addr,
        "to_addr": _decode_header_value(msg.get("To")),
        "subject": _decode_header_value(msg.get("Subject")),
        "snippet": "",
        "received_at": _parse_date_header(msg.get("Date")),
    }


def _decode_part(part) -> str:
    try:
        raw = part.get_payload(decode=True) or b""
    except Exception:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except (LookupError, ValueError):
        return raw.decode("utf-8", errors="replace")


def _body_text_from_message(msg) -> str:
    """Bevorzugt text/plain, faellt auf text/html zurueck (dann per `_entkleiden` von Markup
    befreit) — dieselbe Präferenz wie `gmail_client._body_text`.

    Seit P2-16 (Phase 91) mit derselben Ausnahme: Traegt der plain-Teil die Nachricht des
    HTML-Teils gar nicht (ein Stummel aus Kopfzeile und Footer), gewinnt der HTML-Teil.
    Anlass, Mass und Messung stehen bei `gmail_client._alternative_waehlen`; die Pruefung wird
    von dort IMPORTIERT statt kopiert, damit die beiden Provider nicht auseinanderlaufen und
    dieselbe Mail je nach Abrufweg unterschiedlich ausgewertet wird."""
    plain, html_body = None, None
    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue
            ctype = part.get_content_type()
            if ctype == "text/plain" and plain is None:
                plain = _decode_part(part)
            elif ctype == "text/html" and html_body is None:
                html_body = _decode_part(part)
    else:
        ctype = msg.get_content_type()
        if ctype == "text/plain":
            plain = _decode_part(msg)
        elif ctype == "text/html":
            html_body = _decode_part(msg)
    if plain and html_body:
        from pipeline.gmail_client import _ist_stummel
        html_text = _entkleiden(html_body)
        if _ist_stummel(plain, html_text):
            return html_text
        return plain
    if plain:
        return plain
    if html_body:
        return _entkleiden(html_body)
    return ""


# ── Verben ────────────────────────────────────────────────────────────────────────────────
def _fetch_header_record(imap: imaplib.IMAP4, uid, settings: dict) -> "dict | None":
    typ, data = imap.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID)])")
    if typ != "OK" or not data or not data[0]:
        return None
    raw = data[0][1] if isinstance(data[0], tuple) else b""
    msg = email.message_from_bytes(raw)
    return _record_from_headers(msg, settings)


def cmd_search(query: str, max_results: int) -> list:
    settings = load_settings()
    _require_imap_settings(settings)
    parsed = translate_query(query or "")
    for note in parsed["notes"]:
        print(note, file=sys.stderr)
    n = max(1, min(int(max_results), MAX_HARD))
    imap = _connect(settings)
    try:
        typ, _data = imap.select(_mailbox_arg("INBOX"), readonly=True)
        if typ != "OK":
            _die("IMAP: Posteingang (INBOX) konnte nicht ausgewaehlt werden.")
        uids = _cap_pool(_search_uids(imap, parsed), n)
        records = [_fetch_header_record(imap, uid, settings) for uid in uids]
    finally:
        _safe_logout(imap)
    records = [r for r in records if r is not None]
    records = _apply_leaf_filters(records, parsed)
    records.sort(key=lambda r: r["received_at"], reverse=True)
    return records[:n]


def _find_uid_by_message_id(imap: imaplib.IMAP4, message_id: str) -> "bytes | None":
    typ, data = imap.uid("SEARCH", None, "HEADER", "Message-ID", _quote_search_string(message_id.strip()))
    if typ != "OK":
        return None
    ids = data[0].split() if data and data[0] else []
    return ids[0] if ids else None


def cmd_get(message_id: str) -> dict:
    if not message_id or not message_id.strip():
        _die("message_id ist Pflicht.")
    settings = load_settings()
    _require_imap_settings(settings)
    imap = _connect(settings)
    try:
        typ, _data = imap.select(_mailbox_arg("INBOX"), readonly=True)
        if typ != "OK":
            _die("IMAP: Posteingang (INBOX) konnte nicht ausgewaehlt werden.")
        uid = _find_uid_by_message_id(imap, message_id)
        if uid is None:
            _die(f"IMAP: Nachricht mit Message-ID {message_id!r} nicht gefunden (INBOX).")
        typ, data = imap.uid("FETCH", uid, "(BODY.PEEK[])")
        if typ != "OK" or not data or not data[0]:
            _die(f"IMAP: Nachricht {message_id!r} konnte nicht geladen werden.")
        raw = data[0][1] if isinstance(data[0], tuple) else b""
    finally:
        _safe_logout(imap)
    msg = email.message_from_bytes(raw)
    rec = _record_from_headers(msg, settings)
    rec["body"] = _body_text_from_message(msg)
    return rec


# Domain fuer die Message-ID, wenn sich aus den Einstellungen keine ableiten laesst (P2-46).
# Bewusst eine `.local`-Adresse: sie ist als nicht oeffentlich erkennbar und kollidiert mit
# keiner echten Domain.
_MSGID_FALLBACK_DOMAIN = "bewerbung-mgmt.local"


def _msgid_domain(settings: dict) -> str:
    """Domain fuer die Message-ID aus den Mail-Einstellungen (P2-46, 25.09.2026).

    WOFUER: `email.utils.make_msgid()` ohne Argument ruft `socket.getfqdn()` auf — eine
    Namensaufloesung des eigenen Rechners. Auf einem Entwicklungs-Mac hing die 30 Sekunden (gemessen
    25.09.2026: jeder `_build_mime`-Aufruf 30,0 s, die Testsuite dadurch 3:40 statt 10 s; ein
    IMAP-Entwurf haette in der App genauso lange gehangen). Nach einem hosts-Eintrag antwortet
    sie sofort, liefert aber `1.0.0.0.…ip6.arpa` — eine IPv6-Rueckwaertsadresse, die als Domain
    einer Message-ID nichts zu suchen hat.

    RICHTIG ist ohnehin die Domain des Absenders: `username` ist die Mailadresse. Faellt sie
    aus, dient der Servername als Ersatz (ein fuehrendes `imap.`/`mail.`/… faellt weg, sonst
    stuende `imap.beispiel.de` in der ID), zuletzt `_MSGID_FALLBACK_DOMAIN`. Der Rechnername
    wird NIE mehr befragt."""
    username = str((settings or {}).get("username") or "").strip()
    if "@" in username:
        domain = username.rsplit("@", 1)[1].strip().strip(".")
        if domain:
            return domain
    host = str((settings or {}).get("host") or "").strip().strip(".")
    if host:
        teile = host.split(".")
        if len(teile) > 2 and teile[0].lower() in ("imap", "mail", "smtp", "pop", "pop3", "email"):
            teile = teile[1:]
        rest = ".".join(t for t in teile if t)
        if rest:
            return rest
    return _MSGID_FALLBACK_DOMAIN


def _build_mime(to: str, subject: str, body: str, in_reply_to=None, domain=None) -> EmailMessage:
    """Reine MIME-Konstruktion, kein IMAP-Zugriff — eigenständig testbar (Umlaute/Header).
    Nutzt wie `gmail_client.cmd_draft` die moderne `EmailMessage`-API (Policy `default`):
    Header mit Nicht-ASCII-Zeichen werden beim Serialisieren automatisch RFC-2047-kodiert,
    `set_content` waehlt Charset/Content-Transfer-Encoding fuer den Body automatisch.

    `domain` steuert die Message-ID (P2-46) — ohne Angabe die Ersatz-Domain, NIE der per
    Namensaufloesung ermittelte Rechnername (Begruendung s. `_msgid_domain`). Aufrufer mit
    Einstellungen reichen `_msgid_domain(settings)` herein."""
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject or ""
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=domain or _MSGID_FALLBACK_DOMAIN)
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body or "")
    return msg


def cmd_draft(to: str, subject: str, body: str, in_reply_to=None) -> dict:
    """Legt einen ENTWURF per IMAP APPEND (`\\Draft`-Flag) an. APPEND braucht keine vorherige
    SELECT des Zielordners (RFC 3501 §6.3.11 — gültig direkt im Authenticated State)."""
    if not to or not to.strip():
        _die("--to ist Pflicht: das Postfach verlangt mindestens einen Empfaenger auch fuer "
             "Entwuerfe.\nIst die Adresse unbekannt, die eigene Adresse eintragen (s. tasks/lessons.md).")
    settings = load_settings()
    _require_imap_settings(settings)
    msg = _build_mime(to, subject, body, in_reply_to, domain=_msgid_domain(settings))
    folder = str(settings.get("drafts_folder") or DEFAULT_DRAFTS_FOLDER).strip() or DEFAULT_DRAFTS_FOLDER
    imap = _connect(settings)
    try:
        typ, data = imap.append(_mailbox_arg(folder), r"(\Draft)",
                                 imaplib.Time2Internaldate(time.time()), msg.as_bytes())
        if typ != "OK":
            _die(f"IMAP-Fehler beim Anlegen des Entwurfs (APPEND '{folder}'): {data}")
    finally:
        _safe_logout(imap)
    return {"ok": True, "draft_id": None, "thread_id": None,
            "hinweis": f"Entwurf im IMAP-Ordner '{folder}' angelegt — nicht verschickt. "
                       "Selbst pruefen und senden."}
