"""Das App-Icon für JEDE HTML-Seite und JEDEN Bericht — an einer Stelle.

ANLASS (Vorgabe vom 28.08.2026): „Alle sollen das Favicon nutzen, keine Webseite und kein Report
mehr, der im Browser nicht das Favicon nutzt." Eine Bestandsaufnahme ergab: Von elf Erzeugern
hatten drei ein Icon (Coach-Site, Doku-Seiten, die App selbst), sieben nicht — Tages-Digest,
Beirats-Dashboard, Anzeigen-Snapshot, Aufräum-Bericht, Migrations-Bericht, Transkript-Bericht,
Company-Fit-Dashboard. Dazu die Report-Vorlage, aus der alle Skill-Berichte entstehen.

HERKUNFT: Der Code stammt unverändert aus `coach_export._favicon_link`/`_mit_favicon`
(Phase 82). Er lag dort und in `docs_render.py` als ZWEI Kopien — bewusst, damit beide Module
ohne Abhängigkeit voneinander laufen. Mit sieben weiteren Nutzern trägt diese Begründung nicht
mehr: Neun Kopien wären neun Stellen, an denen jemand das Icon vergessen kann.

NEU gegenüber den Kopien ist allein die IDEMPOTENZ (`mit_favicon` prüft auf ein bereits
vorhandenes Icon). Sie ist die Voraussetzung dafür, dass dieselbe Funktion sowohl beim Erzeugen
als auch beim Ausliefern und beim Nachrüsten bestehender Dateien laufen darf, ohne dass sich
Links stapeln.

DREI EBENEN, damit wirklich nichts durchrutscht:
  1. **Erzeuger** binden das Icon direkt ein — die Datei trägt es dann auch beim Öffnen aus
     dem Finder (`file://`).
  2. **`/api/artifact`** setzt es beim Ausliefern nach, falls es fehlt. Das deckt sofort ALLES
     ab, was aus der App geöffnet wird — auch die vielen Berichte, die es schon gibt.
  3. **`pipeline.favicon_nachruesten`** schreibt es in bestehende Dateien und läuft im
     Ansichten-Refresh des Tageslaufs mit. Damit bekommen auch die von Skills erzeugten
     Berichte das Icon in die Datei, ohne dass eine SKILL.md sich darauf besinnen muss.

P2-72 (Design aus einer Quelle): Das Icon kommt nicht mehr aus `frontend/public/`, sondern aus dem
Design (`pipeline/design.py`: `laden().icon_bytes(32)`). Damit gilt:
  * NEUE Berichte bekommen das Icon des GELTENDEN Designs (`favicon_link()`), bei jedem Aufruf frisch
    gelesen. Wer eines einbindet, ruft die Funktion zur Laufzeit und merkt sich den Link nicht.
  * GÜLTIG sind zwei Icons: das der Vorgabe und das des geltenden Designs (`gueltige_links()`). Ein
    Bericht mit einem von beiden bleibt unverändert; ersetzt wird nur ein Icon, das keines von beiden
    ist. Das fängt weiter die von Modellen verstümmelten Icons ab (P2-44), schreibt aber bei einem
    Designwechsel nicht den Bestand um (Leitentscheidung 10).
  * `FAVICON_LINK` bleibt als Name erhalten (andere Module importieren ihn). Er ist keine beim Import
    berechnete Konstante mehr, sondern wird beim Zugriff berechnet (Modul-`__getattr__`, PEP 562):
    `favicon.FAVICON_LINK` und `from app.favicon import FAVICON_LINK` liefern immer das Icon des
    Designs, das gerade gilt. `from … import` bindet den Wert dabei einmalig an den Importeur; wer
    in einem langlebigen Prozess (Server) bei Designwechsel aktuell bleiben muss, ruft `favicon_link()`.
"""
import base64
import re
from pathlib import Path

from pipeline import design as _design

PROJEKT_ROOT = Path(__file__).resolve().parent.parent.parent

# Base64 und Link je Stand des Designs (`Design.stand` ändert sich mit jedem Byte des Icons): Ein Bericht
# braucht den Link mehrfach, die Umrechnung soll nicht jedes Mal laufen.
_LINKS: dict = {}


def _link_aus(png: bytes) -> str:
    b64 = base64.b64encode(png).decode("ascii")
    return f'<link rel="icon" type="image/png" href="data:image/png;base64,{b64}">'


def favicon_link(design=None) -> str:
    """`<link>`-Tag mit dem App-Icon als Data-URI — das Icon des GELTENDEN Designs (oder des übergebenen
    `Design`-Objekts), bei jedem Aufruf frisch gelesen.

    Bewusst KEINE zusaetzliche Datei neben dem HTML: Berichte werden verschickt, in den
    Coach-Export kopiert und aus dem Finder geoeffnet — ein Verweis auf eine Nachbardatei
    ginge dabei verloren. 2,5 KB PNG werden zu 3,3 KB Base64; das ist der Preis dafuer, dass
    eine Seite eigenstaendig bleibt.

    Ist das Design nicht lesbar (beschädigte Vorgabe) oder fehlt das Icon, gibt es eben kein Icon
    (leerer Text) statt eines Absturzes.
    """
    try:
        d = design if design is not None else _design.laden()
        eintrag = _LINKS.get(d.stand)
        if eintrag is None:
            png = d.icon_bytes(32)
            if png is None:
                return ""
            if len(_LINKS) >= 16:
                _LINKS.clear()
            eintrag = _LINKS[d.stand] = _link_aus(png)
        return eintrag
    except (_design.DesignFehler, OSError):
        return ""


def vorgabe_link() -> str:
    """Der Link des Icons der VORGABE (nie einer Überschreibung)."""
    try:
        return favicon_link(_design.vorgabe())
    except _design.DesignFehler:
        return ""


def gueltige_links() -> tuple:
    """Die Icon-Links, die in einem Bericht stehen dürfen, ohne ersetzt zu werden: das Icon der Vorgabe
    und das des geltenden Designs (ein Eintrag, wenn beide gleich sind; leer, wenn kein Icon lesbar ist)."""
    links = []
    for link in (favicon_link(), vorgabe_link()):
        if link and link not in links:
            links.append(link)
    return tuple(links)


def __getattr__(name: str):
    """`FAVICON_LINK` als Name erhalten (P2-72): beim Zugriff berechnet, nie beim Import festgehalten."""
    if name == "FAVICON_LINK":
        return favicon_link()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# "<head" NICHT als Praefix von "<header …>" missverstehen (posting_snapshot.py & Co. nutzen
# "<header class=…>" im <body>) — der Lookahead verlangt Whitespace oder ">" direkt danach.
_HEAD_RE = re.compile(r"<head(?=[\s>])[^>]*>", re.IGNORECASE)
# BEVORZUGTE Einfuegestelle: direkt hinter der Zeichensatz-Angabe. Grund: Der Data-URI ist mit
# 3,3 KB groesser als die 1024 Bytes, innerhalb derer der HTML-Standard das `<meta charset>`
# erwartet. Setzt man das Icon davor, rutscht die Angabe aus diesem Fenster und der Browser darf
# die Kodierung RATEN — bei einem deutschen Bericht heisst das kaputte Umlaute. Erst wenn keine
# Zeichensatz-Angabe existiert, wird hinter `<head>` eingefuegt.
_CHARSET_RE = re.compile(r"<meta[^>]+charset[^>]*>", re.IGNORECASE)
# Ein bereits vorhandenes Icon erkennen — egal ob als Data-URI, Datei-Verweis oder mit
# `shortcut icon` geschrieben. Ohne diese Pruefung wuerde das Nachruesten Links stapeln.
_HAT_ICON_RE = re.compile(r'<link[^>]+rel=["\'][^"\']*\bicon\b', re.IGNORECASE)
# Icon-Links, die DIESES Modul verantwortet: rel="icon" und rel="shortcut icon". Bewusst NICHT
# `apple-touch-icon` oder `mask-icon` — die stehen fuer andere Zwecke und bleiben unberuehrt
# (P2-44). Das Muster erkennt auch Schreibweisen ohne Anfuehrungszeichen.
_ICON_TAG_RE = re.compile(
    r'<link\b[^>]*\brel=["\']?(?:shortcut\s+)?icon(?=["\'\s>])[^>]*>', re.IGNORECASE)


def hat_favicon(text: str) -> bool:
    """Traegt dieser HTML-Text bereits IRGENDEIN Icon (auch ein fremdes)?"""
    return bool(_HAT_ICON_RE.search(text))


def hat_bms_favicon(text: str) -> bool:
    """Traegt dieser HTML-Text das App-Icon dieses Projekts? (P2-44)

    Unterscheidet sich bewusst von `hat_favicon`: Ein Bericht kann ein Icon tragen, das nicht
    unseres ist — genau der Fall, der am 23.09.2026 am ATS-Scan auffiel.
    P2-72: Unseres sind zwei Icons, das der Vorgabe und das des geltenden Designs.
    """
    return any(link in text for link in gueltige_links())


def mit_favicon(text: str) -> str:
    """Setzt den Favicon-Link in den Kopf des Dokuments — idempotent.

    Als ErsetzungsFUNKTION (nicht als String) an `re.sub` uebergeben: `re` interpretiert in
    String-Ersetzungen Backslash-Ziffern-Folgen als Backreference, und Base64-Text ist nicht
    davor gefeit.

    Eingefuegt wird hinter der Zeichensatz-Angabe, nicht hinter `<head>` — sonst schoebe der
    3,3 KB grosse Data-URI das `<meta charset>` aus den ersten 1024 Bytes, und der Browser
    duerfte die Kodierung raten (kaputte Umlaute).

    Unveraendert zurueck, wenn ein gueltiges App-Icon schon da ist (das der Vorgabe oder das des
    geltenden Designs, P2-72), weder Zeichensatz noch `<head>` existieren (z. B. ein HTML-Fragment)
    oder kein Favicon verfuegbar ist.

    FREMDES ICON WIRD ERSETZT (P2-44, 23.09.2026). Bis dahin genuegte irgendein Icon-Link, damit
    diese Funktion die Datei in Ruhe liess — mit der Folge, dass ein falsches Icon fuer immer
    blieb. Gemessen am echten Bestand: 26 Skill-Berichte (18 ATS-Scans, 8 Match-
    Dashboards) trugen ein fremdes Icon, mehrere davon mit abgeschnittenem Base64, das gar kein
    Bild mehr ergibt. Ursache ist die Report-Vorlage: Sie traegt den 3,3 KB langen Data-URI, den
    ein Modell beim Schreiben des Berichts mitkopieren muss — in etwa jedem zwanzigsten Lauf
    verstuemmelt. Seitdem gilt: unser Icon gewinnt, mehrfache Icon-Links werden auf eines
    reduziert.
    """
    link = favicon_link()          # P2-72: das Icon des Designs, das JETZT gilt
    if not link or hat_bms_favicon(text):
        return text
    if _ICON_TAG_RE.search(text):
        # Ersetzungs-FUNKTION statt String (s. o.: Backreference-Falle). Der erste Treffer wird
        # unser Link, jeder weitere faellt weg — sonst stapelten sich Icons.
        gesehen = {"n": 0}

        def _ersetze(_m):
            gesehen["n"] += 1
            return link if gesehen["n"] == 1 else ""

        return _ICON_TAG_RE.sub(_ersetze, text)
    for muster in (_CHARSET_RE, _HEAD_RE):
        if muster.search(text):
            return muster.sub(lambda m: m.group(0) + link, text, count=1)
    return text
