"""Draft-MIME-Bau für IMAP (Phase 71F, `pipeline.imap_mail._build_mime`/`cmd_draft`).

Zwei Ebenen: (1) `_build_mime()` ist eine reine Funktion (kein IMAP-Zugriff) — Header,
Empfänger und Umlaute werden direkt an der serialisierten Nachricht geprüft. (2) `cmd_draft()`
wird gegen ein IMAP-Fake getestet (kein echter Server, s. Spec-Vorgabe) — geprüft wird, dass
exakt EIN `APPEND` mit `\\Draft`-Flag in den konfigurierten Ordner geht und die dabei
angehängten Bytes dieselbe MIME-Nachricht sind.

App-/Pipeline-Importe bewusst innerhalb der Testfunktionen (Konvention aus conftest.py).
"""
import email as email_lib
import email.policy

import pytest


def _decode(raw_value: str) -> str:
    from email.header import decode_header, make_header
    return str(make_header(decode_header(raw_value)))


def _parse(raw: bytes):
    """`message_from_bytes` nutzt ohne Angabe die alte `compat32`-Policy (kein `.get_content()`).
    `_build_mime` selbst baut mit der modernen `EmailMessage`/`policy.default`-API -- zum
    Re-Parsen fuer `.get_content()` deshalb dieselbe Policy explizit anfordern."""
    return email_lib.message_from_bytes(raw, policy=email.policy.default)


# ── _build_mime: reine Funktion ─────────────────────────────────────────────────────────
def test_build_mime_setzt_to_subject_und_body():
    from pipeline.imap_mail import _build_mime

    msg = _build_mime("empfaenger@beispiel.de", "Betreff hier", "Text hier")
    assert msg["To"] == "empfaenger@beispiel.de"
    assert _decode(msg["Subject"]) == "Betreff hier"
    assert msg.get_content().strip() == "Text hier"


def test_build_mime_traegt_message_id_und_date():
    from pipeline.imap_mail import _build_mime

    msg = _build_mime("a@b.de", "S", "T")
    assert msg["Message-ID"]
    assert msg["Date"]


def test_build_mime_in_reply_to_setzt_references():
    from pipeline.imap_mail import _build_mime

    msg = _build_mime("a@b.de", "Re: S", "T", in_reply_to="<original-123@mail.beispiel.de>")
    assert msg["In-Reply-To"] == "<original-123@mail.beispiel.de>"
    assert msg["References"] == "<original-123@mail.beispiel.de>"


def test_build_mime_ohne_in_reply_to_lässt_header_weg():
    from pipeline.imap_mail import _build_mime

    msg = _build_mime("a@b.de", "S", "T")
    assert msg["In-Reply-To"] is None
    assert msg["References"] is None


def test_build_mime_umlaute_in_betreff_und_text_ueberleben_den_wire_roundtrip():
    """Der eigentliche Kern der Spec-Vorgabe: Umlaute im Betreff (RFC-2047-kodiert) UND im
    Body müssen nach Serialisierung + Re-Parse (genau der Pfad, den ein echter
    IMAP-APPEND/FETCH durchläuft) unverändert wieder da sein.

    NUR die HEADER müssen 7-bit-ASCII-sauber sein (RFC 2047 encoded-words, hier per
    RFC-2047-Base64 sichtbar am `=?utf-8?b?…?=`-Präfix). Der BODY nicht zwingend: die
    moderne `EmailMessage`-Policy (`email.policy.default`) wählt dafür standardmäßig
    `Content-Transfer-Encoding: 8bit` -- das lässt rohe UTF-8-Mehrbyte-Sequenzen im Body
    stehen. Anders als klassisches 7-bit-SMTP ist ein IMAP-APPEND ein längenpräfigiertes
    Byte-Literal, kein 7-bit-Transport -- 8bit-Body ist hier unproblematisch (verifiziert
    per Round-Trip unten, nicht nur behauptet)."""
    from pipeline.imap_mail import _build_mime

    msg = _build_mime("bewerber@beispiel.de", "Rückfrage zu Ihrer Bewerbung äöüß ÄÖÜ",
                       "Grüße,\nBjörn Müller — Straße 12, München")
    raw = msg.as_bytes()
    kopf = raw.split(b"\n\n", 1)[0]
    kopf.decode("ascii")   # wirft, falls der Betreff NICHT korrekt RFC-2047-kodiert waere

    back = _parse(raw)
    assert _decode(back["Subject"]) == "Rückfrage zu Ihrer Bewerbung äöüß ÄÖÜ"
    assert back.get_content().strip() == "Grüße,\nBjörn Müller — Straße 12, München"


def test_build_mime_empfaenger_mit_anzeigename_und_umlaut():
    from pipeline.imap_mail import _build_mime

    msg = _build_mime('"Müller, Jörg" <joerg@beispiel.de>', "S", "T")
    raw = msg.as_bytes()
    raw.split(b"\n\n", 1)[0].decode("ascii")   # nur der Header muss ASCII-sauber sein
    back = _parse(raw)
    # "To" wird beim Parsen als RFC-2047-kodierter Header zurückgegeben -- über decode_header lesbar.
    assert "joerg@beispiel.de" in back["To"]
    assert "Müller" in _decode(back["To"]) or "M=C3=BCller" in back["To"] or "M?ller" in back["To"] \
        or "=?utf-8?" in back["To"].lower()


# ── cmd_draft(): gegen ein IMAP-Fake (kein Netz) ────────────────────────────────────────
class _FakeImapDraft:
    """Minimaler IMAP-Stub nur für den APPEND-Pfad — s. Moduldocstring dieser Datei."""

    def __init__(self):
        self.login_args = None
        self.appended = []
        self.closed = False
        self.logged_out = False

    def login(self, user, pw):
        self.login_args = (user, pw)
        return ("OK", [b"login ok"])

    def append(self, mailbox, flags, date_time, message):
        self.appended.append({"mailbox": mailbox, "flags": flags, "message": message})
        return ("OK", [b"APPEND completed"])

    def close(self):
        self.closed = True
        return ("OK", [b"CLOSE completed"])

    def logout(self):
        self.logged_out = True
        return ("OK", [b"BYE"])


@pytest.fixture()
def imap_settings(tmp_path, monkeypatch):
    import pipeline.imap_mail as imap_mail

    monkeypatch.setattr(imap_mail, "SETTINGS_FILE", tmp_path / "mail_settings.json")
    settings = {
        "provider": "imap", "host": "imap.beispiel.de", "port": 993, "security": "ssl",
        "username": "ich@beispiel.de", "password": "geheim123", "drafts_folder": "Entwürfe",
    }
    imap_mail.save_settings(settings)
    return imap_mail


def test_cmd_draft_appended_mit_draft_flag_in_konfigurierten_ordner(imap_settings, monkeypatch):
    import pipeline.imap_mail as imap_mail

    fake = _FakeImapDraft()
    monkeypatch.setattr(imap_mail.imaplib, "IMAP4_SSL", lambda host, port: fake)

    out = imap_mail.cmd_draft("empfaenger@beispiel.de", "Betreff äöü", "Text mit Umlauten grüßt")

    assert out["ok"] is True
    assert out["draft_id"] is None
    assert "Entwürfe" in out["hinweis"]
    assert len(fake.appended) == 1
    call = fake.appended[0]
    assert call["flags"] == r"(\Draft)"
    # Mailbox-Argument ist IMAP-UTF7-kodiert + gequoted (Ordnername "Entwürfe" enthält ein ü).
    assert call["mailbox"].startswith('"') and call["mailbox"].endswith('"')
    # Angehängte Bytes sind eine gültige MIME-Nachricht; nur die HEADER müssen ASCII-sauber
    # sein (s. Begründung in test_build_mime_umlaute_…), der Body darf 8bit-UTF-8 sein.
    call["message"].split(b"\n\n", 1)[0].decode("ascii")
    back = _parse(call["message"])
    assert back["To"] == "empfaenger@beispiel.de"
    assert _decode(back["Subject"]) == "Betreff äöü"
    assert fake.closed and fake.logged_out
    assert fake.login_args == ("ich@beispiel.de", "geheim123")


def test_cmd_draft_ohne_empfaenger_bricht_mit_klarer_meldung_ab(imap_settings, capsys):
    import pipeline.imap_mail as imap_mail

    with pytest.raises(SystemExit) as exc_info:
        imap_mail.cmd_draft("", "S", "T")
    assert exc_info.value.code == 2
    meldung = capsys.readouterr().err
    assert "Pflicht" in meldung
    assert "Traceback" not in meldung


def test_cmd_draft_fehlende_imap_konfiguration_bricht_ab(tmp_path, monkeypatch, capsys):
    import pipeline.imap_mail as imap_mail

    monkeypatch.setattr(imap_mail, "SETTINGS_FILE", tmp_path / "mail_settings.json")
    imap_mail.save_settings({"provider": "imap"})   # kein host/username/password

    with pytest.raises(SystemExit) as exc_info:
        imap_mail.cmd_draft("a@b.de", "S", "T")
    assert exc_info.value.code == 2
    meldung = capsys.readouterr().err
    assert "host" in meldung and "username" in meldung and "password" in meldung


# ── P2-46: Message-ID ohne Namensaufloesung ────────────────────────────────────────────────
# ANLASS (25.09.2026): `email.utils.make_msgid()` ohne Argument ruft `socket.getfqdn()`. Auf
# Auf einem Entwicklungsrechner hing das 30 Sekunden — jeder Test dieser Datei zahlte sie, die Suite lief 3:40
# statt 10 Sekunden, und ein IMAP-Entwurf haette in der App genauso lange gehangen. Nach seinem
# hosts-Eintrag antwortet die Aufloesung sofort, liefert aber `1.0.0.0.….ip6.arpa`. Beides
# gehoert nicht in eine Message-ID; richtig ist die Domain des Absenders.
def test_message_id_fragt_den_rechnernamen_nicht_mehr(monkeypatch):
    """Der Kern: `socket.getfqdn` darf ueberhaupt nicht mehr aufgerufen werden. Der Test macht
    den Aufruf toedlich — haelt jemand die alte Variante fuer gleichwertig, faellt er hier."""
    import socket

    from pipeline.imap_mail import _build_mime

    def _verboten(*_a, **_k):
        raise AssertionError("socket.getfqdn() darf fuer die Message-ID nicht befragt werden")

    monkeypatch.setattr(socket, "getfqdn", _verboten)

    msg = _build_mime("a@b.de", "S", "T", domain="beispiel.de")

    assert msg["Message-ID"].endswith("@beispiel.de>")


def test_message_id_ohne_domain_nutzt_die_ersatz_domain():
    from pipeline.imap_mail import _MSGID_FALLBACK_DOMAIN, _build_mime

    msg = _build_mime("a@b.de", "S", "T")

    assert msg["Message-ID"].endswith(f"@{_MSGID_FALLBACK_DOMAIN}>")


@pytest.mark.parametrize("settings, erwartet", [
    ({"username": "ich@beispiel.de", "host": "imap.anders.de"}, "beispiel.de"),  # Konto schlaegt Server
    ({"host": "imap.beispiel.de"}, "beispiel.de"),                               # Praefix faellt weg
    ({"host": "beispiel.de"}, "beispiel.de"),                                    # ohne Praefix unveraendert
    ({"username": "ohne-at", "host": "mail.firma.example"}, "firma.example"),
    ({}, "bewerbung-mgmt.local"),
])
def test_msgid_domain_ableitung(settings, erwartet):
    from pipeline.imap_mail import _msgid_domain

    assert _msgid_domain(settings) == erwartet


def test_cmd_draft_setzt_die_konto_domain_in_die_message_id(imap_settings, monkeypatch):
    """Ende zu Ende: die Fixture konfiguriert `ich@beispiel.de` — genau diese Domain muss in der
    angehaengten Nachricht stehen, nicht der Rechnername."""
    import email as email_lib

    import pipeline.imap_mail as imap_mail

    fake = _FakeImapDraft()
    monkeypatch.setattr(imap_mail.imaplib, "IMAP4_SSL", lambda host, port: fake)

    imap_mail.cmd_draft("empfaenger@beispiel.de", "Betreff", "Text")

    gesendet = email_lib.message_from_bytes(fake.appended[0]["message"])
    assert gesendet["Message-ID"].endswith("@beispiel.de>")

