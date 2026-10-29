"""Regressionstest für P2-16 (Phase 91): der Stummel-`text/plain`-Teil.

Fall A, 26.08.2026 — Ein Nutzer las in seinem Postfach eine Absage, im
Tracker stand „Eingangsbestätigung". LinkedIn verschickt Absagen als `multipart/alternative`:
der `text/plain`-Teil (2296 Zeichen) enthält NUR die Kopfzeile „Your update from <Firma>" und
einen Footer aus Tracking-URLs, der eigentliche Satz („Unfortunately, we will not be moving
forward with your application") steht AUSSCHLIESSLICH im `text/html`-Teil (143 KB).

`_body_text()` bevorzugte text/plain und gab damit einen Text zurück, in dem eine Absage gar
nicht stehen KANN. Betroffen waren fünf Absagen — sie lagen als
„Eingangsbestätigung" im Tracker, die zugehörigen Stellen blieben auf „Beworben". Kein
Klassifikationsfehler des Skills: dem Lauf fehlte schlicht der Text.

ZWEI NAHELIEGENDE MASSE WURDEN GEMESSEN UND VERWORFEN — beide sind als Test mitgeschrieben,
damit sie niemand versehentlich wieder einbaut:
1. Reine Länge: Der plain-Teil ist mit 2296 Zeichen sogar LÄNGER als der Text aus dem HTML-Teil
   (1711) — er besteht fast vollständig aus Tracking-URLs (`test_..._nicht_an_der_reinen_laenge`).
2. Menge an Fließtext, den nur der HTML-Teil hat: LinkedIn hängt an jede Mail einen Block
   Stellenwerbung. Ohne ihn fällt diese Menge von 40–75 auf 18–20 neue Wörter und rutscht unter
   jede Schwelle, die normale Mails (bis 19) noch aussortiert (`test_..._ohne_werbeblock`).

Gemessen wird deshalb der ANTEIL der Inhaltswörter des HTML-Teils, die im plain-Teil fehlen —
er misst die Stummel-Eigenschaft selbst, nicht LinkedIns Werbelaune. An 16 echten Mails mit
beiden Teilen (26.08.2026): normale Absender 0,00–0,30, alle LinkedIn-Stummel 0,51–0,74; ohne
Werbeblock steigt der Wert sogar auf 0,63–0,86. `STUMMEL_ANTEIL = 0.40` liegt in der Lücke,
`test_normale_mail_*` und `test_stummel_*` bewachen die beiden Wolken.

Der Vergleich läuft WORTWEISE: Der plain-Teil bricht Zeilen oft bei 72 Zeichen um, der HTML-Teil
nicht — zeichenweise hielten sieben normale Mails bis zu 641 Zeichen desselben Satzes für neuen
Inhalt.

Reine Funktionstests — kein DB-/Netzzugriff, funktionslokaler Import wie überall in dieser Suite.
"""
import base64


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")


def _teil(mime: str, inhalt: str) -> dict:
    return {"mimeType": mime, "headers": [], "body": {"data": _b64(inhalt)}}


def _alternative(plain: str, html: str) -> dict:
    return {"mimeType": "multipart/alternative", "headers": [], "body": {},
            "parts": [_teil("text/plain", plain), _teil("text/html", html)]}


# Nachbau einer LinkedIn-Absage mit erfundenen Daten: Kopfzeile + U+034F-Füllzeichen + Tracking-Footer.
_TRACKING = ("https://www.linkedin.com/help/linkedin/answer/4788?lipi=urn%3Ali%3Apage%3A"
             "email_email_jobs_application_rejected_01&midToken=AQEoi3RIG4&trk=eml-"
             "email_jobs_application_rejected_01-SecurityHelp-0-textfooterglimmer")
STUMMEL_PLAIN = (
    "Your update from Beispiel Analytics\r\n\r\n" + "͏ " * 120 + "\r\n"
    "----------------------------------------\r\n\r\n"
    "This email was intended for Max Mustermann (Delivery Leader EMEA)\r\n"
    "Learn why we included this: " + _TRACKING + "\r\n"
    "You are receiving LinkedIn notification emails.\r\n"
    "Unsubscribe: " + _TRACKING + "\r\nHelp: " + _TRACKING + "\r\n"
    "© 2026 LinkedIn Corporation, 1000 West Maude Avenue, Sunnyvale, CA 94085.\r\n"
)
ABSAGE_SATZ = ("Thank you for your interest in the Team Lead Musterbereich position at "
               "Beispiel Analytics in Musterstadt, Bavaria, Germany. Unfortunately, we will not "
               "be moving forward with your application, but we appreciate your time and "
               "interest in Beispiel Analytics.")
STUMMEL_HTML = (
    "<html><body><p>Your update from Beispiel Analytics</p>"
    "<h2>Team Lead Musterbereich</h2><p>Beispiel Analytics &middot; Musterstadt</p>"
    "<p>Applied on Aug 23</p><p>" + ABSAGE_SATZ + "</p><p>Regards,<br>Beispiel Analytics</p>"
    "<p>Top jobs looking for your skills</p><a href='" + _TRACKING + "'>See more jobs</a>"
    "</body></html>"
)


def test_stummel_plain_teil_der_html_teil_gewinnt():
    """DER Kernfall: ohne den Fix fehlt der Absagesatz im Rückgabetext vollständig."""
    from pipeline.gmail_client import _body_text

    ergebnis = _body_text(_alternative(STUMMEL_PLAIN, STUMMEL_HTML))

    assert "will not be moving forward" in ergebnis, (
        "der Absagesatz steht nur im HTML-Teil — fehlt er, kann keine Klassifikation der Welt "
        "die Mail als Absage erkennen")
    assert "Applied on Aug 23" in ergebnis, "auch die Eckdaten stecken nur im HTML-Teil"


def test_stummel_erkennung_scheitert_nicht_an_der_reinen_laenge():
    """Beleg für die Konstruktion: der plain-Teil ist LÄNGER als der HTML-Text. Ein
    Längenvergleich (der naheliegende Fix) würde hier weiterhin den Stummel wählen."""
    from pipeline.gmail_client import _body_text
    from pipeline.htmltext import entkleiden

    assert len(STUMMEL_PLAIN) > len(entkleiden(STUMMEL_HTML)), (
        "Prämisse des Testfalls verloren — der Stummel muss länger sein als der echte Text")
    assert "will not be moving forward" in _body_text(_alternative(STUMMEL_PLAIN, STUMMEL_HTML))


def test_normale_mail_behaelt_den_plain_teil():
    """Gegenprobe — die Regel darf NUR bei Stummeln greifen. Bei ordentlichen Absendern ist
    text/plain sauberer als jedes Tag-Strippen und bleibt erste Wahl."""
    from pipeline.gmail_client import _body_text

    plain = ("Sehr geehrter Herr Mustermann,\r\n\r\nvielen Dank für Ihre Bewerbung als Head of "
             "Customer Success. Wir haben Ihre Unterlagen erhalten und melden uns innerhalb "
             "der nächsten zwei Wochen bei Ihnen.\r\n\r\nMit freundlichen Grüßen\r\nDas Team")
    html = ("<html><body><p>Sehr geehrter Herr Mustermann,</p><p>vielen Dank f&uuml;r Ihre "
            "Bewerbung als Head of Customer Success. Wir haben Ihre Unterlagen erhalten und "
            "melden uns innerhalb der n&auml;chsten zwei Wochen bei Ihnen.</p>"
            "<p>Mit freundlichen Gr&uuml;&szlig;en<br>Das Team</p></body></html>")

    ergebnis = _body_text(_alternative(plain, html))

    assert ergebnis == plain, "gleichwertige Teile: text/plain bleibt die erste Wahl"


def test_nur_html_unveraendert_entkleidet():
    """Bestandsverhalten (viele ATS senden NUR text/html) — muss unberührt bleiben."""
    from pipeline.gmail_client import _body_text

    ergebnis = _body_text({"mimeType": "multipart/alternative", "headers": [], "body": {},
                           "parts": [_teil("text/html", STUMMEL_HTML)]})

    assert "will not be moving forward" in ergebnis


def test_nur_plain_unveraendert():
    """Bestandsverhalten ohne HTML-Teil — der plain-Teil kommt unverändert zurück."""
    from pipeline.gmail_client import _body_text

    text = "Leider müssen wir Ihnen absagen."
    ergebnis = _body_text({"mimeType": "multipart/alternative", "headers": [], "body": {},
                           "parts": [_teil("text/plain", text)]})

    assert ergebnis == text


def test_regel_greift_nicht_in_multipart_mixed():
    """Abgrenzung: In `mixed` sind die Teile EIGENSTÄNDIGE Dokumente (Anschreiben + Anhang),
    nicht zwei Darstellungen derselben Nachricht. Ein Umfangsvergleich wäre dort sinnlos —
    der lange HTML-Anhang darf den echten Mailtext nicht verdrängen."""
    from pipeline.gmail_client import _body_text

    mailtext = "Kurze Rückfrage: Können Sie Ihr Zeugnis nachreichen?"
    anhang = "<html><body>" + ("<p>Seitenlanger Anhang mit ganz anderem Inhalt.</p>" * 40) + "</body></html>"
    payload = {"mimeType": "multipart/mixed", "headers": [], "body": {},
               "parts": [_teil("text/plain", mailtext), _teil("text/html", anhang)]}

    assert _body_text(payload) == mailtext


def test_inhaltswoerter_ignorieren_urls_und_fuellzeichen():
    """Direkttest des Maßes — Links, Mailadressen und unsichtbare Füllzeichen sind kein Text.
    Ohne das zählten die Tracking-URLs im Footer als Inhalt und verwässerten jeden Vergleich."""
    from pipeline.gmail_client import _inhaltswoerter

    assert _inhaltswoerter("Absage " + _TRACKING + " erhalten kontakt@firma.de ͏") == [
        "absage", "erhalten"]


def test_wortvergleich_ueberlebt_unterschiedliche_zeilenumbrueche():
    """Derselbe Satz, im plain-Teil umgebrochen, im HTML-Teil nicht — das darf NICHT als neuer
    Inhalt gelten (der Grund für den Wort- statt Zeichenvergleich)."""
    from pipeline.gmail_client import _ist_stummel

    satz = ("Vielen Dank für Ihre Bewerbung als Head of Customer Success. Wir melden uns "
            "innerhalb der nächsten zwei Wochen bei Ihnen zurück.")
    umgebrochen = satz.replace(". ", ".\r\n").replace(" als", "\r\nals")

    assert not _ist_stummel(umgebrochen, satz)


def test_stummel_erkennung_haelt_ohne_werbeblock():
    """Robustheitsfall: LinkedIn hängt Stellenwerbung an jede Mail. Fällt sie weg, sinkt die
    absolute Menge neuen Textes stark (gemessen: 40–75 auf 18–20 Wörter) — die Erkennung darf
    daran NICHT hängen, sonst wäre sie an eine Marketing-Laune gekoppelt."""
    from pipeline.gmail_client import _ist_stummel
    from pipeline.htmltext import entkleiden

    ohne_werbung = STUMMEL_HTML.split("<p>Top jobs")[0] + "</body></html>"

    assert _ist_stummel(STUMMEL_PLAIN, entkleiden(ohne_werbung)), (
        "ohne Werbeblock nicht mehr erkannt — das Maß hängt an der Werbung statt am Stummel")


def test_imap_provider_nutzt_dieselbe_schwelle():
    """Beide Provider müssen sich gleich verhalten — sonst hängt die Auswertung davon ab,
    über welchen Weg die Mail geholt wurde. `imap_mail` importiert die Schwelle bewusst aus
    `gmail_client`, statt sie zu kopieren."""
    import email

    from pipeline.imap_mail import _body_text_from_message

    msg = email.message_from_string(
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/alternative; boundary="GRENZE"\r\n\r\n'
        "--GRENZE\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n" + STUMMEL_PLAIN + "\r\n"
        "--GRENZE\r\nContent-Type: text/html; charset=utf-8\r\n\r\n" + STUMMEL_HTML + "\r\n"
        "--GRENZE--\r\n")

    assert "will not be moving forward" in _body_text_from_message(msg)
