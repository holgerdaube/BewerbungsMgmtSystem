"""`pipeline.imap_mail.cmd_search`/`cmd_get` gegen ein IMAP-Fake (Phase 71F).

Kein echter Server (Spec-Vorgabe „IMAP-Netzzugriffe in Tests mocken") — ein kleines Fake
implementiert nur die tatsächlich genutzten `imaplib.IMAP4_SSL`-Methoden
(`login`/`select`/`uid`/`close`/`logout`) mit realistischen Rückgabeformen (insbesondere die
FETCH-Antwort als `(info_bytes, daten_bytes)`-Tupel, wie `imaplib` sie wirklich liefert).

Ziel: beweisen, dass `search`/`get` dieselbe Feldstruktur wie der Gmail-Pfad liefern
(`gmail_message_id`, `gmail_thread_id`, `direction`, `from_addr`, `to_addr`, `subject`,
`snippet`, `received_at`, bei `get` zusätzlich `body`) UND dass die in
`test_imap_query_translation.py` isoliert geprüfte Positiv-/Negativ-Filterlogik im
Zusammenspiel mit echten (wire-serialisierten) Nachrichten tatsächlich greift.
"""
import email as email_lib
from email.message import EmailMessage

import pytest


def _msg(from_, to, subject, date, message_id, body="Text der Nachricht.", html=None):
    m = EmailMessage()
    m["From"] = from_
    m["To"] = to
    m["Subject"] = subject
    m["Date"] = date
    m["Message-ID"] = message_id
    if html:
        m.set_content(html, subtype="html")
    else:
        m.set_content(body)
    return m.as_bytes()


def _header_slice(raw: bytes) -> bytes:
    """Simuliert, was ein echter Server für `BODY.PEEK[HEADER.FIELDS (...)]` zurückgäbe: nur
    die angefragten Header-Zeilen, ggf. weiterhin RFC-2047-kodiert."""
    msg = email_lib.message_from_bytes(raw)
    lines = [f"{name}: {msg.get(name)}" for name in ("From", "To", "Subject", "Date", "Message-ID")
             if msg.get(name) is not None]
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")


class _FakeImapSearch:
    def __init__(self, entries):
        self.entries = dict(entries)   # uid(str) -> raw bytes
        self.select_calls = []
        self.closed = False
        self.logged_out = False

    def login(self, user, pw):
        return ("OK", [b"ok"])

    def select(self, mailbox, readonly=False):
        self.select_calls.append((mailbox, readonly))
        return ("OK", [str(len(self.entries)).encode()])

    def uid(self, command, *args):
        command = command.upper()
        if command == "SEARCH":
            if len(args) >= 3 and args[1] == "HEADER" and args[2] == "Message-ID":
                target = args[3].strip('"')
                hits = [uid for uid, raw in self.entries.items()
                        if email_lib.message_from_bytes(raw).get("Message-ID", "").strip() == target]
                return ("OK", [" ".join(hits).encode()])
            return ("OK", [" ".join(self.entries.keys()).encode()])
        if command == "FETCH":
            # `imaplib` liefert UIDs aus SEARCH als bytes zurueck (data[0].split()) -- ein
            # realer Client reicht diese bytes unveraendert an den naechsten FETCH-Aufruf
            # durch (s. imap_mail.py). Das Fake muss dieselbe bytes/str-Normalisierung
            # vornehmen, die ein echter Server intern ebenfalls tut, sonst laeuft jeder
            # Lookup gegen den (str-keyed) `self.entries`-Dict ins Leere.
            uid_key = args[0].decode() if isinstance(args[0], bytes) else args[0]
            spec = args[1] if len(args) > 1 else ""
            raw = self.entries.get(uid_key)
            if raw is None:
                return ("OK", [None])
            body = _header_slice(raw) if "HEADER.FIELDS" in spec else raw
            return ("OK", [(f"{uid_key} (UID {uid_key} ...)".encode(), body), b")"])
        return ("NO", [b"unbekanntes Kommando"])

    def close(self):
        self.closed = True
        return ("OK", [b"ok"])

    def logout(self):
        self.logged_out = True
        return ("OK", [b"ok"])


@pytest.fixture()
def imap_env(tmp_path, monkeypatch):
    import pipeline.imap_mail as imap_mail

    monkeypatch.setattr(imap_mail, "SETTINGS_FILE", tmp_path / "mail_settings.json")
    imap_mail.save_settings({
        "provider": "imap", "host": "imap.beispiel.de", "port": 993, "security": "ssl",
        "username": "ich@beispiel.de", "password": "geheim123", "drafts_folder": "Drafts",
    })
    return imap_mail


def _install_fake(monkeypatch, imap_mail, fake):
    monkeypatch.setattr(imap_mail.imaplib, "IMAP4_SSL", lambda host, port: fake)


# ── cmd_search ───────────────────────────────────────────────────────────────────────────
def test_cmd_search_liefert_gmail_kompatible_feldstruktur(imap_env, monkeypatch):
    raw = _msg("Personalabteilung Muster <recruiting@firma.de>", "ich@beispiel.de", "Ihre Bewerbung",
               "Fri, 31 Jul 2026 10:00:00 +0200", "<msg1@firma.de>")
    fake = _FakeImapSearch({"1": raw})
    _install_fake(monkeypatch, imap_env, fake)

    out = imap_env.cmd_search("from:recruiting", 10)
    assert len(out) == 1
    rec = out[0]
    for feld in ("gmail_message_id", "gmail_thread_id", "direction", "from_addr", "to_addr",
                 "subject", "snippet", "received_at"):
        assert feld in rec
    assert rec["gmail_message_id"] == "<msg1@firma.de>"
    assert rec["gmail_thread_id"] is None
    assert rec["subject"] == "Ihre Bewerbung"
    assert rec["direction"] == "incoming"
    assert rec["received_at"] == "2026-07-31T08:00:00Z"   # +0200 -> UTC
    assert fake.select_calls[0][1] is True                # readonly


def test_cmd_search_positivfilter_schliesst_nicht_passende_treffer_aus(imap_env, monkeypatch):
    treffer = _msg("Recruiting <recruiting@firma.de>", "ich@beispiel.de", "Ihre Bewerbung",
                    "Fri, 31 Jul 2026 10:00:00 +0200", "<treffer@firma.de>")
    rauschen = _msg("Newsletter <newsletter@beispiel.de>", "ich@beispiel.de", "Sommer-Angebote",
                     "Fri, 31 Jul 2026 09:00:00 +0200", "<rauschen@beispiel.de>")
    fake = _FakeImapSearch({"1": treffer, "2": rauschen})
    _install_fake(monkeypatch, imap_env, fake)

    out = imap_env.cmd_search("from:recruiting", 10)
    ids = {r["gmail_message_id"] for r in out}
    assert ids == {"<treffer@firma.de>"}


def test_cmd_search_negativfilter_schlaegt_trotz_positivtreffer_zu(imap_env, monkeypatch):
    """Passt sowohl auf die Positiv- (subject) als auch die Negativ-Klausel (from) -- muss
    ausgeschlossen bleiben (Negation schlägt Positivtreffer, s. `_apply_leaf_filters`)."""
    ambivalent = _msg("no-reply@portal.example", "ich@beispiel.de", "Bewerbung Status Update",
                       "Fri, 31 Jul 2026 10:00:00 +0200", "<ambivalent@portal.example>")
    fake = _FakeImapSearch({"1": ambivalent})
    _install_fake(monkeypatch, imap_env, fake)

    out = imap_env.cmd_search("subject:Bewerbung -from:(portal.example)", 10)
    assert out == []


def test_cmd_search_direction_outgoing_bei_eigener_adresse(imap_env, monkeypatch):
    eigene = _msg("Ich <ich@beispiel.de>", "recruiting@firma.de", "Re: Ihre Bewerbung",
                   "Fri, 31 Jul 2026 11:00:00 +0200", "<eigene@beispiel.de>")
    fake = _FakeImapSearch({"1": eigene})
    _install_fake(monkeypatch, imap_env, fake)

    out = imap_env.cmd_search("subject:Bewerbung", 10)
    assert out[0]["direction"] == "outgoing"


def test_cmd_search_ohne_positivkriterium_liefert_alles_im_zeitfenster(imap_env, monkeypatch):
    a = _msg("a@beispiel.de", "ich@beispiel.de", "A", "Fri, 31 Jul 2026 10:00:00 +0200", "<a@beispiel.de>")
    b = _msg("b@beispiel.de", "ich@beispiel.de", "B", "Fri, 31 Jul 2026 09:00:00 +0200", "<b@beispiel.de>")
    fake = _FakeImapSearch({"1": a, "2": b})
    _install_fake(monkeypatch, imap_env, fake)

    out = imap_env.cmd_search("newer_than:2d", 10)
    assert {r["gmail_message_id"] for r in out} == {"<a@beispiel.de>", "<b@beispiel.de>"}
    # neueste zuerst
    assert out[0]["gmail_message_id"] == "<a@beispiel.de>"


# ── cmd_get ──────────────────────────────────────────────────────────────────────────────
def test_cmd_get_liefert_body_inkl_html_entkleidung(imap_env, monkeypatch):
    raw = _msg("Firma <hr@firma.de>", "ich@beispiel.de", "Absage",
               "Fri, 31 Jul 2026 12:00:00 +0200", "<absage@firma.de>",
               html="<p>Leider <b>keine</b> Zusage.</p>")
    fake = _FakeImapSearch({"1": raw})
    _install_fake(monkeypatch, imap_env, fake)

    rec = imap_env.cmd_get("<absage@firma.de>")
    assert rec["gmail_message_id"] == "<absage@firma.de>"
    assert rec["from_addr"] == "Firma <hr@firma.de>"
    assert "keine Zusage" in rec["body"]
    assert "<p>" not in rec["body"] and "<b>" not in rec["body"]
    assert fake.select_calls[0][1] is True   # readonly


def test_cmd_get_unbekannte_message_id_bricht_klar_ab(imap_env, monkeypatch, capsys):
    fake = _FakeImapSearch({})
    _install_fake(monkeypatch, imap_env, fake)

    with pytest.raises(SystemExit) as exc_info:
        imap_env.cmd_get("<nicht-vorhanden@beispiel.de>")
    assert exc_info.value.code == 2
    meldung = capsys.readouterr().err
    assert "nicht-vorhanden@beispiel.de" in meldung
    assert "Traceback" not in meldung
