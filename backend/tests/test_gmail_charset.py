"""Regressionstest für P2-12 (Phase 67D): `gmail_client._decode()`/`_body_text()` dekodierten
die Base64-Rohbytes bisher IMMER als UTF-8 (`errors="replace"`), ohne den Content-Type-Charset
des jeweiligen MIME-Teils auszuwerten. Ältere Firmen-/ATS-Mailsysteme senden teils
ISO-8859-1/Windows-1252 -- ohne den Fix entstehen Ersatzzeichen (U+FFFD) genau im
klassifikationsrelevanten Text (Absage/Einladung/Rückfrage).

Fix: `_charset_of(payload)` liest den `Content-Type`-Header GENAU DES MIME-TEILS, der gerade
dekodiert wird (`payload["headers"]` -- für den Top-Level-Payload die echten RFC822-Header, für
einen `parts[]`-Eintrag die MIME-Header dieses Teils), parst `charset=…` und übergibt ihn an
`_decode()`. UTF-8 bleibt Fallback (kein Charset angegeben ODER Python kennt ihn nicht/Decode
scheitert sonst).

Reine Funktionstests -- kein DB-/Netzzugriff, kein app.*-Import nötig (gmail_client hängt nicht
an app.db), trotzdem funktionslokaler Import wie überall in dieser Suite."""
import base64


def _b64(raw_bytes: bytes) -> str:
    return base64.urlsafe_b64encode(raw_bytes).decode("ascii")


def test_body_text_dekodiert_iso_8859_1_laut_content_type_header():
    """Kernfall: ein `text/plain`-Teil mit `Content-Type: text/plain; charset=ISO-8859-1"` UND
    echten ISO-8859-1-Rohbytes (Umlaute außerhalb des ASCII-Bereichs). Ohne den Fix decodiert
    `_decode()` diese Bytes zwingend als UTF-8 -- jedes Umlaut-Byte (0x80-0xFF) ist dort
    ungültig und wird durch U+FFFD ersetzt; der Text stimmt dann NICHT mehr mit dem Original
    überein und enthält Ersatzzeichen."""
    from pipeline.gmail_client import _body_text

    text = ("Wir bedauern, Ihnen mitteilen zu müssen, dass wir uns für einen anderen "
            "Bewerber entschieden haben. Wir wünschen Ihnen für die Zukunft alles Gute "
            "und grüßen Sie freundlich.")
    payload = {
        "mimeType": "text/plain",
        "headers": [{"name": "Content-Type", "value": 'text/plain; charset="ISO-8859-1"'}],
        "body": {"data": _b64(text.encode("iso-8859-1"))},
    }

    result = _body_text(payload)

    assert result == text, f"erwarte verlustfreie ISO-8859-1-Dekodierung, bekam: {result!r}"
    assert "�" not in result, "Ersatzzeichen (U+FFFD) -- Zeichen einer Zwangs-UTF-8-Dekodierung"


def test_body_text_dekodiert_windows_1252_laut_content_type_header():
    """Zweiter realer Charset (Windows-1252, häufig bei älteren Firmen-Mailsystemen) — mit
    Sonderzeichen (Anführungszeichen U+201E/U+201C), die es in ISO-8859-1 GAR NICHT gibt, aber
    in Windows-1252 an denselben Byte-Positionen (0x84/0x93) belegt sind. Bestätigt, dass der
    Fix den KONKRETEN Charset-Namen nutzt, nicht nur pauschal auf Latin-1 ausweicht."""
    from pipeline.gmail_client import _body_text

    text = "Bewerbung als „Senior Manager Customer Success“ – vielen Dank für Ihr Interesse."
    payload = {
        "mimeType": "text/plain",
        "headers": [{"name": "Content-Type", "value": "text/plain; charset=windows-1252"}],
        "body": {"data": _b64(text.encode("cp1252"))},
    }

    result = _body_text(payload)

    assert result == text, f"erwarte verlustfreie Windows-1252-Dekodierung, bekam: {result!r}"


def test_body_text_html_teil_nutzt_ebenfalls_den_charset_des_teils():
    """Der text/html-Zweig (Fallback von _body_text) muss GENAUSO den Charset auswerten --
    P2-12 nennt explizit ATS-Systeme, die nur text/html schicken (s. lessons.md: Atos/Jobgether)."""
    from pipeline.gmail_client import _body_text

    text = "<p>Wir laden Sie herzlich zum Gespräch für die Position ein.</p>"
    payload = {
        "mimeType": "text/html",
        "headers": [{"name": "Content-Type", "value": "text/html; charset=ISO-8859-1"}],
        "body": {"data": _b64(text.encode("iso-8859-1"))},
    }

    result = _body_text(payload)

    assert "Gespräch" in result
    assert "�" not in result


def test_body_text_multipart_liest_charset_des_jeweiligen_teils_nicht_der_huelle():
    """Eine multipart-Nachricht: der AEUSSERE Payload hat gar keinen sinnvollen Charset
    (`multipart/alternative`), die Charset-Angabe steht NUR am inneren text/plain-Teil. Das
    beweist, dass `_charset_of()` je Rekursionsebene liest (`payload["headers"]` DIESES Teils),
    nicht einmalig von der Hülle."""
    from pipeline.gmail_client import _body_text

    text = "Rückfrage zu Ihrer Bewerbung: Bitte bestätigen Sie den Gesprächstermin."
    hülle = {
        "mimeType": "multipart/alternative",
        "headers": [{"name": "Content-Type", "value": 'multipart/alternative; boundary="xyz"'}],
        "body": {},
        "parts": [
            {
                "mimeType": "text/plain",
                "headers": [{"name": "Content-Type", "value": "text/plain; charset=ISO-8859-1"}],
                "body": {"data": _b64(text.encode("iso-8859-1"))},
            },
        ],
    }

    result = _body_text(hülle)

    assert result == text
    assert "�" not in result


def test_body_text_unbekannter_charset_faellt_auf_utf8_zurueck_statt_abzustuerzen():
    """Anforderung aus dem Befund: eine unbekannte/kaputte Charset-Angabe darf NIE zum Absturz
    führen -- Fallback UTF-8 mit errors='replace' wie bisher. `_decode()` faengt das LookupError
    intern ab; dieser Test beweist es end-to-end über `_body_text()`."""
    from pipeline.gmail_client import _body_text

    text = "Einladung zum Gespräch am Montag."
    payload = {
        "mimeType": "text/plain",
        "headers": [{"name": "Content-Type", "value": "text/plain; charset=x-erfundener-charset-9000"}],
        "body": {"data": _b64(text.encode("utf-8"))},
    }

    result = _body_text(payload)   # darf NICHT werfen

    assert result == text, "Bytes waren echtes UTF-8 -- Fallback muss sie unverändert liefern"


def test_body_text_ohne_content_type_header_bleibt_utf8():
    """Regressionsschutz (Q5): fehlt der Content-Type-Header komplett (z. B. metadata-only
    gefetchte Teile), bleibt exakt das bisherige Verhalten -- UTF-8, kein Fehler."""
    from pipeline.gmail_client import _body_text

    text = "Ganz normale UTF-8-Nachricht ohne Umlaut-Sonderfall."
    payload = {"mimeType": "text/plain", "headers": [], "body": {"data": _b64(text.encode("utf-8"))}}

    assert _body_text(payload) == text


def test_charset_of_parst_verschiedene_schreibweisen():
    """Kontrakttest für den Parser selbst: mit/ohne Anführungszeichen, Groß-/Kleinschreibung,
    zusätzliche Content-Type-Attribute nach dem Charset."""
    from pipeline.gmail_client import _charset_of

    assert _charset_of({"headers": [{"name": "Content-Type", "value": 'text/plain; charset="ISO-8859-1"'}]}) == "ISO-8859-1"
    assert _charset_of({"headers": [{"name": "content-type", "value": "text/plain; charset=utf-8"}]}) == "utf-8"
    assert _charset_of({"headers": [{"name": "Content-Type", "value": "text/plain; CHARSET=Windows-1252; format=flowed"}]}) == "Windows-1252"
    assert _charset_of({"headers": [{"name": "Content-Type", "value": "text/plain"}]}) is None
    assert _charset_of({"headers": []}) is None
