"""Beispieldaten für eine frische Kundeninstallation (P2-59, Paket B).

WARUM: Wer das BMS zum ersten Mal startet, sieht leere Seiten und kann nichts ausprobieren. Eine
frische Paket-Installation bekommt deshalb beim allerersten Start die erfundene Bewerbungsgeschichte
von „Birne Helene“ (Postbote, fünf Jahre Paketzustellung): Profil, Skills, Werdegang, Firmen,
Stellen in allen wichtigen Stufen, Bewerbungen, einen Gesprächstermin, Mails, einen Netzwerk-
Kontakt, die Profil-Datei `config/profil.md` und einen Basis-Lebenslauf. Die Daten werden beim
ersten Start ERZEUGT statt mitgeliefert: Das Update-Werkzeug schreibt nie nach `data/` und lehnt
Pakete mit `data/` oder `config/profil.md` ab.

WANN (`einspielen_falls_neu`): nur, wenn ALLES gilt: die Datenbank-Datei gab es vor dem Start noch
nicht (`db_war_da` False, die Hauptsession prüft `DB_PATH.exists()` VOR `init_db()`), die
Markierung `<daten_dir>/beispieldaten.json` fehlt (auch „entfernt“ zählt: nie zweimal), die
Installation ist ein Paket (`app/version.py`) oder `BMS_BEISPIELDATEN=1` ist gesetzt (Tests,
Abnahme), und die Tabellen job, company, email und application sind leer. In einer Git-Installation
passiert ohne die Variable also nie etwas. Die Funktion wirft nie: Ein Fehler wird als Zeile
protokolliert, das Ergebnis ist `False`, und weil alle Datenbank-Zeilen in EINER Transaktion
entstehen, bleibt dann nichts Halbes zurück.

REIHENFOLGE: erst die Zeilen (eine Transaktion), danach die beiden Dateien (jede nur, wenn sie noch
fehlt), die Markierung zuletzt. Scheitert eine Datei, wird die Markierung trotzdem geschrieben: Die
Zeilen existieren dann, und ohne Markierung ließen sie sich nie wieder entfernen.

NICHT angelegt: Suchpläne und Suchbereich (sonst liefe der Tageslauf echte, bezahlte Suchen),
Zielfirmen, Headhunter, Lebenslauf-Versionen. Firmen tragen weder Webseite noch Karriere-URL, Stellen
keine URL, damit kein Hintergrund-Lauf sie abruft.

ENTFERNEN (`entfernen`): nur bei Status „vorhanden“. Zuerst eine Sicherung über
`app.sicherung.anlegen()`, danach in einer Transaktion nur die markierten Zeilen (HART gelöscht) und
alles, was an markierten Stellen hängt. Mails, die nicht markiert sind, aber an einer Beispielstelle
hängen, und Aufgaben-Zeilen (Kosten-Historie) werden gelöst statt gelöscht. Dateien wandern nur in
den Papierkorb `data/papierkorb/`, wenn ihr SHA-256 noch dem angelegten Stand entspricht: Wer die
Profil-Datei oder den Lebenslauf inzwischen selbst geändert hat, behält sie.

PFADE: Projekt-Root, Datenordner und Datenbank-Engine sind überall optionale Parameter und werden
erst im Funktionsrumpf aufgelöst (Lehre Phase 87: ein Default, der an einen Modulwert bindet, wird
in Tests zur Falle). Tests übergeben sie ausschließlich auf `tmp_path`.

Alle Texte sind erfunden: Mailadressen nur unter `beispiel.de`, die Telefonnummer ausschließlich die
Beispielnummer aus der Installationsanleitung, keine Muster wie Stellen- oder Mailnummern. Das
verlangt die Paketprüfung (`pipeline/kundenpaket.py`) für jeden ausgelieferten Text.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import threading
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

NAME = "Birne Helene"
MARKIERUNG = "beispieldaten.json"
ENV_VARIABLE = "BMS_BEISPIELDATEN"

_QUELLE = "beispiel"
_NOTIZ = "Beispieldaten"
_DEDUP_PRAEFIX = "beispiel|"
_PROFIL_MD = "config/profil.md"
_BASIS_CV = "data/cv_basis/base_de.docx"
# Nur diese beiden Pfade legt das Modul an. Beim Entfernen werden ausschließlich sie aus der
# Markierung gelesen: Die Datei liegt im Datenordner, ein verbogener Eintrag darf nichts anderes
# verschieben.
_ERLAUBTE_DATEIEN = (_PROFIL_MD, _BASIS_CV)
_LEER_PRUEFEN = ("job", "company", "email", "application")
_AKTIVE_AUFGABEN = ("queued", "running")

_LOCK = threading.Lock()

# ── Erfundene Angaben ────────────────────────────────────────────────────────────────────────
_NETZWERK_NAME = "Paul Paket"
_MAIL = "birne.helene@beispiel.de"
_TELEFON = "+49 170 1234567"
_ANSCHRIFT = "Musterweg 7, 12345 Musterstadt"
_ORT = "Musterstadt"
_HEADLINE = "Postbote mit 5 Jahren Erfahrung in der Paketzustellung"
_POSITIONIERUNG = (
    "Verlässlicher Postbote, der Pakete bei Regen, Schnee und Mittagshitze pünktlich an die richtige "
    "Tür bringt. Fünf Jahre Paketzustellung in Musterstadt haben Ortskenntnis, Zeitgefühl und einen "
    "sicheren Griff am Handscanner geschult. Freundlich zu Kundschaft und Hunden, vorsichtig mit "
    "Gartenzwergen und immer auf der Suche nach der nächsten Tour."
)

_SKILLS = (
    ("Zustellung", (("Paketzustellung", None), ("Briefzustellung", None), ("Tourenplanung", None),
                    ("Handscanner und Zustell-App", None))),
    ("Fahrzeuge", (("Führerschein Klasse B", None), ("Elektro-Transporter", None), ("Lastenrad", None))),
    ("Lager", (("Staplerschein", None), ("Kommissionierung", None))),
    ("Persönlich", (("Kundenfreundlichkeit", None), ("Zeitmanagement", None), ("Wetterfestigkeit", None))),
    ("Sprachen", (("Deutsch", "Muttersprache"), ("Englisch", "Grundkenntnisse"))),
)

# (Art, Firma, Rolle, Ort, von, bis, Beschreibung)
_WERDEGANG = (
    ("Beruf", "Blitzpaket Zustelldienst GmbH", "Paketzusteller", _ORT, "04/2021", "heute",
     "Pakete und Päckchen auf einer festen Tour in Musterstadt zugestellt, täglich rund 150 Sendungen. "
     "Zustellnachweise mit dem Handscanner erfasst und Rückfragen der Kundschaft freundlich geklärt."),
    ("Beruf", "Lagerhaus Grünwald KG", "Lagerhelfer", _ORT, "08/2019", "03/2021",
     "Waren kommissioniert, Lieferungen mit dem Stapler eingelagert und bei der Inventur unterstützt."),
    ("Ausbildung", "Berufsschule Musterstadt", "Fachkraft für Kurier-, Express- und Postdienstleistungen",
     _ORT, "2017", "2019", None),
    ("Zertifizierung", None, "Führerschein Klasse B", None, "2016", None, None),
    ("Zertifizierung", "Lagerhaus Grünwald KG", "Staplerschein", _ORT, "2019", None, None),
)

# (Schlüssel, Name, Branche, Situation, zuerst gesehen vor Tagen)
_FIRMEN = (
    ("blitzpaket", "Blitzpaket Zustelldienst GmbH", "Paketzustellung", "RUN", 35),
    ("gruenwald", "Grünwald Logistik GmbH", "Logistik", "RUN", 26),
    ("krause", "Kurierdienst Krause GmbH", "Kurierdienst", "SCALE-UP", 14),
    ("stadtpost", "Stadtpost Musterstadt GmbH", "Brief- und Paketzustellung", "RUN", 0),
    ("pedalkurier", "Pedalkurier Musterstadt GbR", "Lastenradkurier", "SCALE-UP", 3),
    ("sonnenschein", "Spedition Sonnenschein AG", "Spedition", "RUN", 33),
)

# Stellen. `gefunden` und `beworben` zählen Tage in die Vergangenheit, `faellig_in` Tage in die
# Zukunft. `verlauf` sind die Statuswechsel im Format, das die App selbst protokolliert
# (`Status: alt → neu`), je als (Tage zurück, Stunde, Minute, Text); eine optionale fünfte Angabe
# ersetzt die Art „auto“.
_STELLEN = (
    {"firma": "stadtpost", "schluessel": "zusteller-briefe-pakete",
     "titel": "Zusteller/in Briefe und Pakete (m/w/d)", "status": "Neu", "gefunden": 0, "plan": "A",
     "score": 5, "gehalt": "ab 2.600 Euro brutto im Monat",
     "begruendung": "Gleiche Tätigkeit wie bisher, Arbeitsort in Musterstadt, Vollzeit.",
     "naechster_schritt": "Anzeige ansehen und entscheiden, ob Sie sich bewerben."},
    {"firma": "pedalkurier", "schluessel": "lastenradkurier",
     "titel": "Lastenradkurier/in (m/w/d)", "status": "Prüfen", "gefunden": 3, "plan": "A", "score": 4,
     "begruendung": "Zustellung mit dem Lastenrad: neues Fahrzeug, aber dieselbe Ortskenntnis.",
     "naechster_schritt": "Klären, ob eine Einarbeitung auf dem Lastenrad angeboten wird.",
     "verlauf": ((3, 9, 5, "Status: Neu → Prüfen"),)},
    {"firma": "gruenwald", "schluessel": "fahrer-nahverkehr-7-5-t",
     "titel": "Fahrer/in Nahverkehr 7,5 t (m/w/d)", "status": "Beworben", "gefunden": 26, "plan": "B",
     "score": 4, "gehalt": "2.800 Euro brutto im Monat", "bauchgefuehl": 3,
     "begruendung": "Fahrer im Nahverkehr passt zur Zielrolle. Der Führerschein Klasse C1 ist erwünscht "
                    "und wird laut Anzeige vom Unternehmen bezahlt.",
     "naechster_schritt": "Nach zwei Wochen ohne Antwort nachfassen.", "faellig_in": 1,
     "notizen": "Bewerbung ging per E-Mail raus. Bisher keine Antwort, nicht einmal eine automatische.",
     "beworben": 20, "kanal": "E-Mail",
     "bewerbung_notiz": "Per E-Mail verschickt, keine Eingangsbestätigung erhalten.",
     "verlauf": ((26, 9, 0, "Status: Neu → Prüfen"), (20, 10, 0, "Status: Prüfen → Beworben"))},
    {"firma": "krause", "schluessel": "kurierfahrer-express",
     "titel": "Kurierfahrer/in Express (m/w/d)", "status": "Interview", "gefunden": 14, "plan": "B",
     "score": 5, "gehalt": "2.900 Euro brutto im Monat", "bauchgefuehl": 4,
     "begruendung": "Express-Kurier mit festen Touren in Musterstadt, passt zu fünf Jahren Zustellerfahrung.",
     "naechster_schritt": "Telefongespräch vorbereiten.", "faellig_in": 2,
     "notizen": "Im Gespräch Ortskenntnis, Pünktlichkeit und die hohe Zustellquote erwähnen.",
     "beworben": 12, "kanal": "E-Mail", "bewerbung_notiz": "Per E-Mail beworben, Antwort kam am nächsten Tag.",
     "verlauf": ((14, 9, 0, "Status: Neu → Prüfen"), (12, 10, 0, "Status: Prüfen → Beworben"),
                 (4, 14, 25, "Status: Beworben → Interview · Bewerbung: Beworben → Interview"))},
    {"firma": "sonnenschein", "schluessel": "disponent-tourenplanung",
     "titel": "Disponent/in Tourenplanung (m/w/d)", "status": "Absage", "gefunden": 33, "plan": "C",
     "score": 3,
     "begruendung": "Disposition ist das Fernziel, bisher fehlt Erfahrung in der Tourenplanung.",
     "notizen": "Die Absage kam freundlich. Beim nächsten Mal die Tourenplanung als Schwerpunkt "
                "der Bewerbung herausstellen.",
     "beworben": 30, "kanal": "E-Mail", "bewerbung_notiz": "Per E-Mail beworben.",
     "absagegrund": "Mehr Erfahrung in der Disposition gewünscht",
     "verlauf": ((33, 9, 0, "Status: Neu → Prüfen"), (30, 10, 0, "Status: Prüfen → Beworben"),
                 (9, 16, 10, "Status: Beworben → Absage · Bewerbung: Beworben → Absage"))},
)

# Mails ohne Gmail-Kennung. (Stellenschlüssel oder None, Absender, Betreff, Auszug, Kategorie,
# Tage zurück, Stunde, Minute). Antworten rechnet die Funktion wie der Mail-Ingest.
_MAILS = (
    ("kurierfahrer-express", "Kurierdienst Krause <bewerbung@krause.beispiel.de>",
     "Ihre Bewerbung bei Kurierdienst Krause ist eingegangen",
     "Guten Tag, vielen Dank für Ihre Bewerbung als Kurierfahrer/in Express. Wir melden uns in den "
     "nächsten Tagen bei Ihnen.", "Eingangsbestätigung", 11, 9, 12),
    ("kurierfahrer-express", "Karla Kurier <karla.kurier@krause.beispiel.de>", "Einladung zum Telefongespräch",
     "Guten Tag, wir möchten Sie gern kennenlernen. Passt Ihnen ein Telefonat am {termin} um "
     "10:00 Uhr? Es dauert etwa 30 Minuten.", "Einladung", 4, 14, 20),
    ("disponent-tourenplanung", "Spedition Sonnenschein <bewerbungen@sonnenschein.beispiel.de>",
     "Eingangsbestätigung Ihrer Bewerbung als Disponent/in Tourenplanung",
     "Guten Tag, Ihre Bewerbung ist bei uns angekommen. Sie hören in Kürze von uns.",
     "Eingangsbestätigung", 28, 11, 40),
    ("disponent-tourenplanung", "Spedition Sonnenschein <personal@sonnenschein.beispiel.de>",
     "Ihre Bewerbung bei der Spedition Sonnenschein",
     "Guten Tag, vielen Dank für Ihr Interesse. Leider haben wir uns für eine Bewerbung mit mehr "
     "Erfahrung in der Disposition entschieden. Wir wünschen Ihnen alles Gute.", "Absage", 9, 16, 5),
    (None, "Gartenfreunde Musterstadt <vorstand@gartenfreunde.beispiel.de>",
     "Gartenfreunde Musterstadt: Einladung zum Herbstfest",
     "Liebe Mitglieder, wir laden Sie herzlich zum Herbstfest in den Vereinsgarten ein. Für Kuchen "
     "ist gesorgt, Gartenzwerge dürfen mitgebracht werden.", "Sonstige", 2, 18, 30),
)

# Kurze Namen der Tabellen in der Markierung und in den Antworten, in Anzeigereihenfolge.
_ARTEN = (
    ("stellen", "job"), ("firmen", "company"), ("bewerbungen", "application"), ("mails", "email"),
    ("gespraeche", "interview"), ("kontakte", "contact"), ("netzwerk", "networkcontact"),
    ("skills", "profileskill"), ("werdegang", "careerentry"),
)


def _log(text: str) -> None:
    print(f"[beispieldaten] {text}", flush=True)


# ── Pfade und Zeit (Auflösung erst im Rumpf) ─────────────────────────────────────────────────
def _projekt_root(projekt_root) -> Path:
    if projekt_root is not None:
        return Path(projekt_root)
    from app import db
    return db.PROJECT_ROOT


def _daten_dir(daten_dir) -> Path:
    if daten_dir is not None:
        return Path(daten_dir)
    from app import db
    return db.DATA_DIR


def _engine(engine):
    if engine is not None:
        return engine
    from app import db
    return db.engine


def _jetzt(jetzt: datetime | None) -> datetime:
    """Lokale Uhrzeit ohne Zeitzone, wie `datetime.now()`. Eine übergebene Zeit mit Zeitzone wird
    in die lokale umgerechnet."""
    wert = jetzt or datetime.now()
    if wert.tzinfo is not None:
        wert = wert.astimezone().replace(tzinfo=None)
    return wert


def _utc_naiv(lokal: datetime) -> datetime:
    """Die Datenbank speichert naive UTC-Zeiten (`app/zeit.py`); die lokale Zeit wird hier umgerechnet."""
    return lokal.astimezone(timezone.utc).replace(tzinfo=None)


class _Tage:
    """Relative Zeitpunkte zu `jetzt`. Positive Tage zählen in die Vergangenheit, negative in die
    Zukunft. Datumsfelder der App sind lokale Kalendertage, Zeitstempel naive UTC-Zeit."""

    def __init__(self, jetzt: datetime):
        self.heute = jetzt.date()

    def datum(self, vor_tagen: int) -> date:
        return self.heute - timedelta(days=vor_tagen)

    def lokal(self, vor_tagen: int, stunde: int, minute: int = 0) -> datetime:
        return datetime.combine(self.datum(vor_tagen), time(stunde, minute))

    def utc(self, vor_tagen: int, stunde: int, minute: int = 0) -> datetime:
        return _utc_naiv(self.lokal(vor_tagen, stunde, minute))


def _de_datum(tag: date) -> str:
    return f"{tag:%d.%m.%Y}"


# ── Markierung ───────────────────────────────────────────────────────────────────────────────
def _markierung_pfad(daten: Path) -> Path:
    return daten / MARKIERUNG


def _markierung_lesen(daten: Path) -> dict | None:
    pfad = _markierung_pfad(daten)
    if not pfad.is_file():
        return None
    try:
        inhalt = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _log(f"WARNUNG: {pfad.name} ist unlesbar ({type(exc).__name__}: {exc})")
        return None
    return inhalt if isinstance(inhalt, dict) else None


def _markierung_schreiben(daten: Path, inhalt: dict) -> None:
    """Atomar (`.tmp` und `os.replace`): Ein halb geschriebener Stand würde „nie zweimal“ aushebeln."""
    daten.mkdir(parents=True, exist_ok=True)
    pfad = _markierung_pfad(daten)
    tmp = pfad.with_name(pfad.name + ".tmp")
    tmp.write_text(json.dumps(inhalt, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, pfad)


def status(daten_dir=None) -> dict:
    """Antwortkörper für `GET /api/beispieldaten`: `status` ist `keine`, `vorhanden` oder `entfernt`;
    `anzahl` nennt je Art, was noch markiert ist (nur bei `vorhanden`). Darf nie scheitern."""
    markierung = _markierung_lesen(_daten_dir(daten_dir))
    zustand = markierung.get("status") if markierung else None
    if zustand not in ("vorhanden", "entfernt"):
        return {"status": "keine", "name": None, "angelegt_am": None, "entfernt_am": None, "anzahl": {}}
    anzahl: dict = {}
    if zustand == "vorhanden":
        ids = markierung.get("ids") or {}
        anzahl = {art: len(ids.get(tabelle) or []) for art, tabelle in _ARTEN}
        anzahl["dateien"] = len(markierung.get("dateien") or {})
    return {"status": zustand, "name": markierung.get("name") or NAME,
            "angelegt_am": markierung.get("angelegt_am"), "entfernt_am": markierung.get("entfernt_am"),
            "anzahl": anzahl}


# ── Dateien ──────────────────────────────────────────────────────────────────────────────────
def _sha256(inhalt: bytes) -> str:
    return hashlib.sha256(inhalt).hexdigest()


def _sha256_datei(pfad: Path) -> str:
    return _sha256(pfad.read_bytes())


def _bytes_schreiben(ziel: Path, inhalt: bytes) -> None:
    """Atomar schreiben: Das Projekt kann in iCloud liegen, ein direktes Überschreiben könnte einen
    halb geschriebenen Stand synchronisieren. Bytes statt Text, damit die Prüfsumme auf jedem
    Betriebssystem zum Dateiinhalt passt (kein Zeilenende-Umbau)."""
    ziel.parent.mkdir(parents=True, exist_ok=True)
    tmp = ziel.with_name(ziel.name + ".neu")
    try:
        tmp.write_bytes(inhalt)
        os.replace(tmp, ziel)
    finally:
        if tmp.exists():
            tmp.unlink()


def _profil_md_text() -> str:
    """Aufbau wie die Vorlage in `BMS_Install_MAC.md` bzw. `BMS_Install_Windows.md` (Abschnitt
    „Einrichten: Das BMS lernt Sie kennen“, dort „Ihr Profil: Identität und Suchstrategie“): Name,
    Standort und Kontakt erkennt `pipeline/user_profile.py` an der Fettschrift der Feldnamen."""
    zeilen = [
        f"# Kandidatenprofil: {NAME}",
        "",
        "## Identität",
        f"- **Name:** {NAME}",
        f"- **Positionierung:** {_HEADLINE}",
        f"- **Standort:** {_ANSCHRIFT}",
        f"- **Kontakt:** {_MAIL} · {_TELEFON}",
        "- **Aktuell:** Paketzusteller bei der Blitzpaket Zustelldienst GmbH, seit 2021",
        "",
        "## Kurzprofil",
        "Postbote mit fünf Jahren Erfahrung in der Paketzustellung in Musterstadt. Kennt die Touren, "
        "die Kundschaft und die Abkürzungen. Sucht eine Stelle in der Zustellung oder im Kurierdienst "
        "und möchte mittelfristig in die Disposition wechseln.",
        "",
        "## Zielrolle",
        "- **Ebene:** Zusteller oder Fahrer, später Disposition",
        "- **Funktion Plan A:** Zustellung von Briefen und Paketen",
        "- **Funktion Plan B:** Kurierfahrer im Nahverkehr",
        "- **Funktion Plan C:** Disposition und Tourenplanung, mittelfristig",
        "- **Branche:** Logistik, Zustellung, Kurierdienste",
        "- **Region:** Musterstadt und Umgebung",
        "- **Zieltermin:** neue Stelle bis zum Jahresende",
        "",
        "## Harte Rahmenbedingungen",
        "- Arbeitsort höchstens 30 km von Musterstadt entfernt.",
        "- Vollzeit, keine Nachtschichten.",
        "- Kein Umzug.",
        "",
        "## Sprachen / CV-Fassungen",
        "- **Deutsch:** `data/cv_basis/base_de.docx`",
        "- Englisch: Grundkenntnisse, nur deutsche Bewerbungen",
        "",
        "## Bekannte Skill-Gaps / Red Flags",
        "- Noch wenig Erfahrung in der Disposition.",
        "",
        "## Empirie aus dem Bewerbungsverlauf",
        "- (pflegt das BMS selbst, bitte die Überschrift unverändert lassen)",
        "",
    ]
    return "\n".join(zeilen)


def _basis_cv_bytes(jetzt: datetime) -> bytes:
    """Basis-Lebenslauf im v10-Aufbau, den `pipeline/cv_export.py` erwartet (Vorbilder:
    `scripts/cv_basis_umbau_v10.py` und `BMS_Install_MAC.md` bzw. `BMS_Install_Windows.md`,
    Abschnitt „Einrichten: Das BMS lernt Sie kennen“, dort „Ihr Lebenslauf“).

    Rubriken sind „Heading 1“ in Großbuchstaben. Je Berufsstation stehen vier Teile untereinander:
    `Firma<TAB>Zeitraum`, dann der Titel (beide „Normal“, fett, 11 pt), EINE kursive Beschreibung und
    Aufzählungen im Stil „List Paragraph“ MIT Nummerierung (`numPr`). Das Bullet-Zeichen kommt aus
    der Nummerierung, der Stilname allein reicht nicht, und `entwurf_extrahieren` erkennt nur „List
    Paragraph“. Der Tabulator darf nirgends sonst stehen, er ist das Erkennungszeichen einer
    Station; die Ausbildung ist deshalb eine einzeilige Tab-Zeile, die übrigen Rubriken trennen mit
    „•“."""
    from docx import Document
    from docx.enum.text import WD_TAB_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()
    abschnitt = doc.sections[0]
    abschnitt.page_width, abschnitt.page_height = Cm(21.0), Cm(29.7)
    abschnitt.left_margin = abschnitt.right_margin = Cm(2.0)
    abschnitt.top_margin = abschnitt.bottom_margin = Cm(1.8)
    textbreite = Cm(17.0)
    navy = RGBColor(0x0B, 0x1F, 0x3A)

    def schrift(stil, groesse, fett=None, farbe=None):
        stil.font.name = "Calibri"
        stil.font.size = Pt(groesse)
        if fett is not None:
            stil.font.bold = fett
        if farbe is not None:
            stil.font.color.rgb = farbe
        # Die Vorlage koppelt Überschriften an Theme-Schriften; ohne diese Zeilen gewinnt das Theme.
        rfonts = stil.element.rPr.rFonts
        for attribut in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
            rfonts.attrib.pop(qn(attribut), None)
        rfonts.set(qn("w:eastAsia"), "Calibri")

    normal = doc.styles["Normal"]
    schrift(normal, 10.5)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(2)
    rubrik = doc.styles["Heading 1"]
    schrift(rubrik, 11.5, fett=True, farbe=navy)
    rubrik.paragraph_format.space_before = Pt(14)
    rubrik.paragraph_format.space_after = Pt(4)

    def zeile(text, groesse=None, fett=False, kursiv=False, farbe=None):
        absatz = doc.add_paragraph()
        lauf = absatz.add_run(text)
        lauf.bold = fett or None
        lauf.italic = kursiv or None
        if groesse:
            lauf.font.size = Pt(groesse)
        if farbe is not None:
            lauf.font.color.rgb = farbe
        return absatz

    def station(firma, zeitraum, titel, beschreibung, aufzaehlung):
        anker = zeile(f"{firma}\t{zeitraum}", groesse=11, fett=True)
        anker.paragraph_format.space_before = Pt(26)     # Stationsabstand der v10-Vorlage
        anker.paragraph_format.tab_stops.add_tab_stop(textbreite, WD_TAB_ALIGNMENT.RIGHT)
        zeile(titel, groesse=11, fett=True)
        zeile(beschreibung, kursiv=True)
        for text in aufzaehlung:
            absatz = doc.add_paragraph(text, style="List Paragraph")
            nummerierung = absatz._p.get_or_add_pPr().get_or_add_numPr()
            nummerierung.get_or_add_ilvl().val = 0
            nummerierung.get_or_add_numId().val = 1      # Punkt-Aufzählung der Standardvorlage
            absatz.paragraph_format.left_indent = Cm(0.63)
            absatz.paragraph_format.first_line_indent = Cm(-0.63)

    # Kopf
    zeile(NAME, groesse=20, fett=True, farbe=navy)
    zeile(_HEADLINE, groesse=11)
    zeile(_ANSCHRIFT)
    zeile(f"{_MAIL} · {_TELEFON}")

    doc.add_paragraph("KURZPROFIL", style="Heading 1")
    zeile("Zuverlässiger Postbote mit fünf Jahren Erfahrung in der Paketzustellung. Sichere "
          "Tourenplanung, freundlicher Umgang mit der Kundschaft und gute Laune bei jedem Wetter. "
          "Sucht eine neue Aufgabe in der Zustellung, im Kurierdienst oder in der Disposition.")

    doc.add_paragraph("BERUFSERFAHRUNG", style="Heading 1")
    station("Blitzpaket Zustelldienst GmbH", "04/2021 bis heute", "Paketzusteller",
            "Regionaler Zustelldienst für Pakete und Päckchen in Musterstadt und Umgebung.",
            ("Täglich rund 150 Pakete und Päckchen auf einer festen Tour in Musterstadt pünktlich "
             "zugestellt.",
             "Zustellnachweise mit dem Handscanner erfasst und Abholungen in der Zustell-App organisiert.",
             "Rund 98 Prozent der Sendungen schon beim ersten Zustellversuch übergeben.",
             "Zwei neue Kolleginnen und Kollegen auf der Tour eingearbeitet."))
    station("Lagerhaus Grünwald KG", "08/2019 bis 03/2021", "Lagerhelfer",
            "Familiengeführtes Lager für Haushaltswaren und Gartenbedarf.",
            ("Waren kommissioniert, verpackt und für den Versand bereitgestellt.",
             "Lieferungen mit dem Stapler entladen und eingelagert.",
             "Bei der Inventur unterstützt und Bestandsdifferenzen geklärt."))

    doc.add_paragraph("AUSBILDUNG", style="Heading 1")
    ausbildung = zeile("Fachkraft für Kurier-, Express- und Postdienstleistungen, Berufsschule "
                       "Musterstadt\t2017 bis 2019")
    ausbildung.paragraph_format.tab_stops.add_tab_stop(textbreite, WD_TAB_ALIGNMENT.RIGHT)

    doc.add_paragraph("KENNTNISSE", style="Heading 1")
    for bereich, eintraege in _SKILLS[:-1]:
        absatz = doc.add_paragraph()
        absatz.add_run(f"{bereich}: ").bold = True
        absatz.add_run(" • ".join(name for name, _ in eintraege))

    doc.add_paragraph("SPRACHEN", style="Heading 1")
    zeile(" • ".join(f"{name}: {niveau}" for name, niveau in _SKILLS[-1][1]))

    eigenschaften = doc.core_properties
    eigenschaften.author = NAME
    eigenschaften.title = f"Lebenslauf {NAME}"
    eigenschaften.comments = _NOTIZ
    eigenschaften.created = eigenschaften.modified = _utc_naiv(jetzt)

    puffer = io.BytesIO()
    doc.save(puffer)
    return puffer.getvalue()


def _dateien_schreiben(wurzel: Path, jetzt: datetime) -> dict:
    """Legt Profil-Datei und Basis-Lebenslauf an, je nur wenn sie fehlen. Jede Datei einzeln
    abgesichert: Scheitert eine, bleibt die andere, und die Aufrufer schreiben die Markierung trotzdem.
    Rückgabe: `{relativer Pfad: SHA-256}` der tatsächlich angelegten Dateien."""
    angelegt: dict = {}
    for rel, erzeuger in ((_PROFIL_MD, lambda: _profil_md_text().encode("utf-8")),
                          (_BASIS_CV, lambda: _basis_cv_bytes(jetzt))):
        ziel = wurzel.joinpath(*rel.split("/"))
        try:
            if ziel.exists():
                continue                          # eigene Datei: nie überschreiben
            inhalt = erzeuger()
            _bytes_schreiben(ziel, inhalt)
            angelegt[rel] = _sha256(inhalt)
        except Exception as exc:                  # noqa: BLE001 -- eine Datei darf die andere nicht verhindern
            _log(f"WARNUNG: {rel} nicht angelegt ({type(exc).__name__}: {exc})")
    return angelegt


# ── Einspielen ───────────────────────────────────────────────────────────────────────────────
def _zeilen_anlegen(session, tage: _Tage) -> tuple[dict, dict]:
    """Alle Datenbank-Zeilen in der übergebenen Session (der Aufrufer committet einmal). Rückgabe:
    (Ids je Tabelle, tatsächlich gesetzte Profilwerte)."""
    from app.models import (Application, CareerEntry, Company, Contact, Email, Interview, Job, JobLog,
                            NetworkContact, Profile, ProfileSkill)
    from app import normalize as N
    from pipeline.gmail_ingest import RESPONSE_CATS, response_time_hours

    angelegt: dict[str, list] = {tabelle: [] for _, tabelle in _ARTEN}
    angelegt["joblog"] = []

    def neu(tabelle: str, zeile):
        session.add(zeile)
        angelegt[tabelle].append(zeile)
        return zeile

    # Profil: nur leere Felder füllen, damit nie ein vorhandener Wert überschrieben wird.
    profil = session.get(Profile, 1)
    if profil is None:
        profil = Profile(id=1)
        session.add(profil)
    profil_werte: dict = {}
    for feld, wert in (("headline", _HEADLINE), ("standort", _ORT), ("positionierung", _POSITIONIERUNG)):
        if not getattr(profil, feld):
            setattr(profil, feld, wert)
            profil_werte[feld] = wert

    for bereich, eintraege in _SKILLS:
        for reihenfolge, (skill, hinweis) in enumerate(eintraege):
            neu("profileskill", ProfileSkill(bereich=bereich, name=skill, note=hinweis, quelle=_QUELLE,
                                             sort_order=reihenfolge))
    for reihenfolge, (art, firma, rolle, ort, von, bis, beschreibung) in enumerate(_WERDEGANG):
        neu("careerentry", CareerEntry(art=art, firma=firma, rolle=rolle, ort=ort, von=von, bis=bis,
                                       beschreibung=beschreibung, quelle=_QUELLE, sort_order=reihenfolge))

    firmen: dict = {}
    for schluessel, firmenname, branche, situation, gesehen in _FIRMEN:
        angelegt_am = tage.utc(gesehen, 8, 30)
        firmen[schluessel] = neu("company", Company(
            name=firmenname, industry=branche, region=_ORT, situation=situation, situation_raw=situation,
            notes=_NOTIZ, created_at=angelegt_am, updated_at=angelegt_am))
    session.flush()

    stellen: dict = {}
    bewerbungen: dict = {}
    for spec in _STELLEN:
        firma = firmen[spec["firma"]]
        gefunden = tage.utc(spec["gefunden"], 8, 30)
        verlauf = spec.get("verlauf", ())
        zuletzt = max([tage.utc(t, h, m) for t, h, m, *_ in verlauf] + [gefunden])
        faellig = spec.get("faellig_in")
        job = neu("job", Job(
            company_id=firma.id, company_name=firma.name, title=spec["titel"], location=_ORT,
            work_model="Onsite", tab="Deutschlandweit", plan_ab=spec["plan"], portal=_NOTIZ, url=None,
            salary=spec.get("gehalt"), published_date=tage.datum(spec["gefunden"] + 1).isoformat(),
            found_date=tage.datum(spec["gefunden"]).isoformat(), match_score=spec["score"],
            match_rationale=spec["begruendung"], gut_feeling=spec.get("bauchgefuehl"),
            status=spec["status"], next_step=spec.get("naechster_schritt"),
            follow_up_date=tage.datum(-faellig).isoformat() if faellig is not None else None,
            notes=spec.get("notizen"), source_note=_NOTIZ, dedup_key=_DEDUP_PRAEFIX + spec["schluessel"],
            created_at=gefunden, updated_at=zuletzt))
        stellen[spec["schluessel"]] = (job, firma)
    session.flush()

    for spec in _STELLEN:
        job, _ = stellen[spec["schluessel"]]
        if "beworben" in spec:
            geaendert = tage.utc(*spec["verlauf"][-1][:3])
            bewerbungen[spec["schluessel"]] = neu("application", Application(
                job_id=job.id, applied_date=tage.datum(spec["beworben"]).isoformat(), channel=spec["kanal"],
                status=spec["status"], last_status_change=geaendert, notes=spec.get("bewerbung_notiz"),
                rejection_reason=spec.get("absagegrund"), created_at=tage.utc(spec["beworben"], 10, 0)))
        for vor_tagen, stunde, minute, text, *art in spec.get("verlauf", ()):
            neu("joblog", JobLog(job_id=job.id, eintrag=text, art=art[0] if art else "auto",
                                 created_at=tage.utc(vor_tagen, stunde, minute)))
    session.flush()

    # Gesprächstermin und Ansprechperson an der Stelle mit der Einladung.
    krause_job, krause = stellen["kurierfahrer-express"]
    termin = tage.datum(-3)
    neu("interview", Interview(
        job_id=krause_job.id, application_id=bewerbungen["kurierfahrer-express"].id, company_id=krause.id,
        runde=1, art="HR-Screen", scheduled_at=f"{termin.isoformat()}T10:00",
        interviewer="Karla Kurier, Recruiterin", status="Geplant", gegenueber="Recruiter", vor_ort=False,
        notes="Telefongespräch, etwa 30 Minuten.", created_at=tage.utc(4, 14, 30),
        updated_at=tage.utc(4, 14, 30)))
    neu("contact", Contact(
        company_id=krause.id, job_id=krause_job.id, name="Karla Kurier", role="Recruiterin",
        email="karla.kurier@krause.beispiel.de", notes="Hat die Einladung zum Telefongespräch geschickt.",
        created_at=tage.utc(4, 14, 25)))
    neu("joblog", JobLog(job_id=krause_job.id, art="manuell", created_at=tage.utc(4, 14, 40),
                         eintrag=f"Telefongespräch am {_de_datum(termin)} um 10:00 Uhr vereinbart."))

    # Mails: Antworten werden wie im Mail-Ingest gerechnet (Antwort-Kategorie, Stunden seit der Bewerbung).
    for schluessel, absender, betreff, auszug, kategorie, vor_tagen, stunde, minute in _MAILS:
        job, firma = stellen[schluessel] if schluessel else (None, None)
        bewerbung = bewerbungen.get(schluessel) if schluessel else None
        empfangen = tage.utc(vor_tagen, stunde, minute)
        ist_antwort = kategorie in RESPONSE_CATS
        anker = None
        if ist_antwort and bewerbung is not None:
            anker = datetime.combine(date.fromisoformat(bewerbung.applied_date), time.min)
        neu("email", Email(
            application_id=bewerbung.id if bewerbung else None, company_id=firma.id if firma else None,
            job_id=job.id if job else None, direction="incoming", from_addr=absender, to_addr=_MAIL,
            subject=betreff, snippet=auszug.format(termin=_de_datum(termin)), received_at=empfangen,
            is_response=ist_antwort, response_time_hours=response_time_hours(empfangen, anker) if anker else None,
            category=kategorie, needs_reply=False, created_at=empfangen))

    neu("networkcontact", NetworkContact(
        name=_NETZWERK_NAME, beziehung="Ehemaliger Kollege", unternehmen="Blitzpaket Zustelldienst GmbH",
        rolle="Zusteller", letzter_kontakt=tage.datum(40).isoformat(), kanal="Persönlich",
        prioritaet="Mittel", notizen="Kennt Leute bei Stadtpost und beim Kurierdienst Krause.",
        next_action="Fragen, ob er bei Stadtpost jemanden kennt.",
        next_action_date=tage.datum(-5).isoformat(),
        # Derselbe Schlüssel wie beim Anlegen in der App (`slug_parts` aus Name und Unternehmen): Mit
        # einem eigenen Präfix legten ein Datei-Import (P2-62) oder ein manuelles Anlegen desselben
        # Kontakts eine Dublette an. Beim Entfernen zählt ohnehin der Name (`_beispiel_bedingungen`).
        dedup_key=N.slug_parts(_NETZWERK_NAME, "Blitzpaket Zustelldienst GmbH")))
    session.flush()

    ids = {tabelle: sorted(zeile.id for zeile in zeilen) for tabelle, zeilen in angelegt.items()}
    return ids, profil_werte


def _installationsart(wurzel: Path, daten: Path) -> str:
    from app import version
    return version.version_info(wurzel, daten).get("installation") or "unbekannt"


def _tabellen_leer(session) -> bool:
    from sqlalchemy import func
    from sqlmodel import SQLModel, select

    for name in _LEER_PRUEFEN:
        if session.exec(select(func.count()).select_from(SQLModel.metadata.tables[name])).one():
            return False
    return True


def _einspielen(db_war_da: bool, projekt_root, daten_dir, jetzt, engine) -> bool:
    if db_war_da:
        return False
    daten = _daten_dir(daten_dir)
    if _markierung_pfad(daten).exists():
        return False
    wurzel = _projekt_root(projekt_root)
    if os.environ.get(ENV_VARIABLE) != "1" and _installationsart(wurzel, daten) != "paket":
        return False

    from sqlmodel import Session

    jetzt = _jetzt(jetzt)
    eng = _engine(engine)
    with Session(eng) as session:
        if not _tabellen_leer(session):
            return False
        ids, profil_werte = _zeilen_anlegen(session, _Tage(jetzt))
        session.commit()          # EINE Transaktion für alle Zeilen: ein Fehler davor legt nichts an

    dateien = _dateien_schreiben(wurzel, jetzt)
    _markierung_schreiben(daten, {
        "status": "vorhanden", "angelegt_am": jetzt.isoformat(timespec="seconds"), "name": NAME,
        "ids": ids, "dateien": dateien, "profil_werte": profil_werte,
    })
    _log(f"Beispieldaten von {NAME} angelegt ({len(ids['job'])} Stellen, {len(ids['company'])} Firmen).")
    return True


def einspielen_falls_neu(db_war_da: bool, *, projekt_root=None, daten_dir=None, jetzt=None,
                         engine=None) -> bool:
    """Legt die Beispieldaten an, wenn dies der allererste Start einer Paket-Installation ist
    (Bedingungen s. Moduldocstring). `True`, wenn etwas angelegt wurde. Wirft nie.

    `db_war_da`: gab es die Datenbank-Datei schon vor `init_db()`? Aufruf in `main._startup()` NACH
    `init_db()` und `suchprofil.sicherstellen()`. `engine` ist nur für Tests gedacht; im Normalbetrieb
    ist es `app.db.engine`. Danach muss der Aufrufer `_profil_struktur_schreiben` rufen, wenn das
    Ergebnis `True` ist."""
    try:
        return _einspielen(db_war_da, projekt_root, daten_dir, jetzt, engine)
    except Exception as exc:       # noqa: BLE001 -- ein Start darf an den Beispieldaten nie scheitern
        _log(f"WARNUNG: Beispieldaten nicht angelegt ({type(exc).__name__}: {exc})")
        return False


# ── Entfernen ────────────────────────────────────────────────────────────────────────────────
def _beispiel_bedingungen(tabellen: dict) -> dict:
    """Zweiter Schlüssel je Tabelle neben der Id: woran eine Zeile noch als Beispielzeile zu erkennen ist.

    WARUM: SQLite vergibt die Id einer gelöschten Zeile mit der höchsten Id wieder. Löscht ein Kunde
    den zuletzt angelegten Beispiel-Skill von Hand und trägt danach einen eigenen ein, trägt dieser
    dieselbe Id. Nur anhand der Id würde „Beispieldaten entfernen“ ihn mitlöschen. Die Merkmale hier
    kann die Oberfläche nicht ändern (Stellen-Schlüssel, Firmenname, Quelle) oder sie trennen
    Beispiel von echt (Absender, Mailadresse). Beim Netzwerk-Kontakt zählt der Name und nicht der
    Schlüssel: Die App berechnet den Schlüssel bei jedem Speichern aus Name und Unternehmen neu, auch
    wenn nur eine Notiz geändert wurde. Eine vom Kunden selbst umbenannte Zeile bleibt stehen, sie
    gehört dann ihm. Bewerbungen, Gespräche und Verlauf hängen an ihrer Stelle und brauchen keinen
    eigenen Schlüssel."""
    firmennamen = [firma[1] for firma in _FIRMEN]
    return {
        "job": tabellen["job"].c.dedup_key.like(f"{_DEDUP_PRAEFIX}%"),
        "company": tabellen["company"].c.name.in_(firmennamen),
        "email": tabellen["email"].c.from_addr.like("%beispiel.de%"),
        "contact": tabellen["contact"].c.email.like("%beispiel.de"),
        "networkcontact": tabellen["networkcontact"].c.name == _NETZWERK_NAME,
        "profileskill": tabellen["profileskill"].c.quelle == _QUELLE,
        "careerentry": tabellen["careerentry"].c.quelle == _QUELLE,
    }


def _verifizierte_ids(verbindung, ids: dict) -> dict:
    """Die Ids aus der Markierung, die in der Datenbank noch eine Beispielzeile bezeichnen (Id UND
    zweiter Schlüssel, s. `_beispiel_bedingungen`). Nur diese Zeilen darf das Entfernen anfassen."""
    from sqlalchemy import select
    from sqlmodel import SQLModel

    tabellen = SQLModel.metadata.tables
    echt: dict = {}
    for name, bedingung in _beispiel_bedingungen(tabellen).items():
        markiert = ids.get(name) or []
        tabelle = tabellen[name]
        echt[name] = [zeile[0] for zeile in verbindung.execute(
            select(tabelle.c.id).where(tabelle.c.id.in_(markiert), bedingung))] if markiert else []
    return echt


def _aktive_aufgaben_pruefen(eng, ids: dict) -> None:
    """Läuft gerade eine Aufgabe an einer Beispielstelle, würde sie nach dem Löschen Zeilen an eine
    Stelle schreiben, die es nicht mehr gibt."""
    from sqlalchemy import select
    from sqlmodel import SQLModel

    aufgaben = SQLModel.metadata.tables["agenttask"]
    with eng.connect() as verbindung:
        job_ids = _verifizierte_ids(verbindung, ids)["job"]
        aktiv = job_ids and verbindung.execute(select(aufgaben.c.id).where(
            aufgaben.c.job_id.in_(job_ids), aufgaben.c.status.in_(_AKTIVE_AUFGABEN)).limit(1)).first()
    if aktiv:
        raise ValueError("An einer Beispielstelle läuft gerade eine Aufgabe. Bitte warten Sie, bis sie "
                         "fertig ist, und versuchen Sie es dann noch einmal.")


def _sicherung_anlegen(daten: Path, eng, jetzt: datetime) -> str:
    from app import sicherung

    db_pfad = Path(eng.url.database) if eng.url.database else None
    try:
        return sicherung.anlegen(daten_dir=daten, db_pfad=db_pfad, jetzt=jetzt).name
    except sicherung.SicherungLaeuft:
        raise ValueError("Es läuft gerade eine Sicherung. Bitte versuchen Sie es gleich noch einmal.") from None
    except Exception as exc:       # noqa: BLE001
        raise RuntimeError("Die Sicherung vor dem Entfernen ist fehlgeschlagen, die Beispieldaten "
                           f"bleiben unverändert. Grund: {exc}") from exc


def _artefaktpfade(verbindung, kinder: list, tabellen: dict, job_ids: list, firma_ids: list) -> list:
    """Gespeicherte Dateipfade (Spalten auf `_path`) der Zeilen, die gleich gelöscht werden: Berichte,
    Lebensläufe und Anschreiben, die der Nutzer an einer Beispielstelle erzeugt hat."""
    from sqlalchemy import select

    abfragen = [(tabelle, tabelle.c.job_id.in_(job_ids)) for tabelle in kinder if job_ids]
    if job_ids:
        abfragen.append((tabellen["job"], tabellen["job"].c.id.in_(job_ids)))
    if firma_ids:
        abfragen.append((tabellen["company"], tabellen["company"].c.id.in_(firma_ids)))
    pfade: list = []
    for tabelle, bedingung in abfragen:
        spalten = [spalte for spalte in tabelle.c if spalte.name.endswith("_path")]
        if not spalten:
            continue
        for zeile in verbindung.execute(select(*spalten).where(bedingung)):
            pfade.extend(wert for wert in zeile if isinstance(wert, str) and wert)
    return pfade


def _datenbank_aufraeumen(eng, ids: dict, profil_werte: dict) -> tuple[dict, dict, list]:
    """Die ganze Datenbank-Arbeit in EINER Transaktion. Rückgabe: (entfernt je Art, gelöst, Pfade
    der mitgelöschten Artefakte). Gelöscht wird nur, was Id UND zweiten Schlüssel trägt
    (`_verifizierte_ids`)."""
    from sqlalchemy import delete, or_, select, update
    from sqlmodel import SQLModel
    from app import models  # noqa: F401  (stellt sicher, dass alle Tabellen registriert sind)

    tabellen = SQLModel.metadata.tables
    gezaehlt: dict = {}
    geloest = {"mails": 0, "aufgaben": 0}

    def loeschen(verbindung, name, bedingung) -> None:
        anzahl = verbindung.execute(delete(tabellen[name]).where(bedingung)).rowcount or 0
        gezaehlt[name] = gezaehlt.get(name, 0) + anzahl

    # Alle Tabellen mit job_id außer Mails und Aufgaben-Log (die werden gelöst); Kinder zuerst.
    kinder = [t for t in reversed(SQLModel.metadata.sorted_tables)
              if "job_id" in t.c and t.name not in ("email", "agenttask")]

    with eng.begin() as verbindung:
        echt = _verifizierte_ids(verbindung, ids)
        job_ids, firma_ids = echt["job"], echt["company"]
        bewerbung = tabellen["application"]
        bewerbung_ids = [zeile[0] for zeile in verbindung.execute(
            select(bewerbung.c.id).where(bewerbung.c.job_id.in_(job_ids)))] if job_ids else []
        pfade = _artefaktpfade(verbindung, kinder, tabellen, job_ids, firma_ids)

        # Mails: markierte löschen, übrige an Beispielstellen lösen (bleiben als „ohne Stelle“).
        mail = tabellen["email"]
        if echt["email"]:
            loeschen(verbindung, "email", mail.c.id.in_(echt["email"]))
        bedingungen = []
        if job_ids:
            bedingungen.append(mail.c.job_id.in_(job_ids))
        if bewerbung_ids:
            bedingungen.append(mail.c.application_id.in_(bewerbung_ids))
        if bedingungen:
            geloest["mails"] = verbindung.execute(
                update(mail).where(or_(*bedingungen)).values(job_id=None, application_id=None)).rowcount or 0

        if job_ids:
            # Aufgaben bleiben als Kosten-Historie im Task-Center, nur ohne Verweis auf die Stelle.
            aufgaben = tabellen["agenttask"]
            geloest["aufgaben"] = verbindung.execute(
                update(aufgaben).where(aufgaben.c.job_id.in_(job_ids)).values(job_id=None)).rowcount or 0
            for tabelle in kinder:
                loeschen(verbindung, tabelle.name, tabelle.c.job_id.in_(job_ids))

        # Markierte Zeilen ohne Stelle (Ansprechperson und Netzwerk-Kontakt auch dann, wenn sie
        # inzwischen von ihrer Stelle gelöst wurden).
        for name in ("contact", "networkcontact", "profileskill", "careerentry"):
            if echt[name]:
                loeschen(verbindung, name, tabellen[name].c.id.in_(echt[name]))

        if job_ids:
            loeschen(verbindung, "job", tabellen["job"].c.id.in_(job_ids))
        if firma_ids:
            # Eigene Zeilen, die noch auf eine Beispielfirma zeigen, verlieren nur den Verweis.
            for tabelle in SQLModel.metadata.sorted_tables:
                if "company_id" in tabelle.c:
                    verbindung.execute(update(tabelle).where(tabelle.c.company_id.in_(firma_ids))
                                       .values(company_id=None))
            loeschen(verbindung, "company", tabellen["company"].c.id.in_(firma_ids))

        # Profil: Werte nur leeren, solange sie noch genau den Beispielwerten entsprechen.
        profil = tabellen["profile"]
        zeile = verbindung.execute(select(profil).where(profil.c.id == 1)).mappings().first()
        if zeile is not None:
            leeren = {feld: None for feld in ("headline", "standort", "positionierung")
                      if profil_werte.get(feld) is not None and zeile[feld] == profil_werte[feld]}
            if leeren:
                verbindung.execute(update(profil).where(profil.c.id == 1).values(**leeren))

    entfernt = {art: gezaehlt.get(tabelle, 0) for art, tabelle in _ARTEN}
    return entfernt, geloest, pfade


def _freier_pfad(ordner: Path, name: str) -> Path:
    ziel = ordner / name
    zaehler = 2
    while ziel.exists():
        ziel = ordner / f"{Path(name).stem}_{zaehler}{Path(name).suffix}"
        zaehler += 1
    return ziel


def _in_papierkorb(wurzel: Path, pfad: Path, jetzt: datetime) -> None:
    """Eigene Verschiebung nach `data/papierkorb/` mit Datumspräfix (Muster der App). Der Helfer der
    Lösch-Endpunkte kommt nicht infrage: Er lässt nur Ordner der Artefakt-Positivliste zu, die
    Profil-Datei liegt in `config/`."""
    ordner = wurzel / "data" / "papierkorb"
    ordner.mkdir(parents=True, exist_ok=True)
    shutil.move(str(pfad), str(_freier_pfad(ordner, f"{jetzt:%Y%m%d}_{pfad.name}")))


def _artefaktpfad_pruefen(wurzel: Path, gespeichert: str) -> Path | None:
    """Der Pfad aus der Datenbank als echter Pfad, wenn er eine Datei unter `data/` oder `outputs/`
    ist. Gesperrt bleiben der Papierkorb, die Sicherungen, die Datenbank und die Basis-Lebensläufe;
    `..` und Verknüpfungen zählen dort, wo sie hinzeigen."""
    rel = str(gespeichert).replace("\\", "/").lstrip("/")
    try:
        echt = (wurzel / rel).resolve()
        relativ = echt.relative_to(wurzel.resolve()).as_posix()
    except (OSError, RuntimeError, ValueError):
        return None
    if not relativ.startswith(("data/", "outputs/")):
        return None
    if relativ.startswith(("data/papierkorb/", "data/backups/", "data/cv_basis/base_")):
        return None
    if relativ.endswith((".sqlite", ".sqlite-wal", ".sqlite-shm")):
        return None
    return echt if echt.is_file() else None


def _artefakte_verschieben(wurzel: Path, pfade: list, jetzt: datetime) -> int:
    verschoben = 0
    for gespeichert in dict.fromkeys(pfade):          # Reihenfolge behalten, Dubletten weglassen
        pfad = _artefaktpfad_pruefen(wurzel, gespeichert)
        if pfad is None:
            continue
        try:
            _in_papierkorb(wurzel, pfad, jetzt)
            verschoben += 1
        except OSError as exc:
            _log(f"WARNUNG: {gespeichert} blieb liegen ({type(exc).__name__}: {exc})")
    return verschoben


def _dateien_aufraeumen(wurzel: Path, dateien: dict, jetzt: datetime) -> tuple[int, list]:
    """Verschiebt Profil-Datei und Basis-Lebenslauf in den Papierkorb, aber nur, wenn ihr Inhalt noch
    der angelegten Fassung entspricht. Rückgabe: (verschoben, behalten)."""
    verschoben, behalten = 0, []
    for rel, soll in dateien.items():
        if rel not in _ERLAUBTE_DATEIEN:
            continue
        pfad = wurzel.joinpath(*rel.split("/"))
        try:
            if not pfad.is_file():
                continue                              # schon weg, nichts zu tun
            if _sha256_datei(pfad) != soll:
                behalten.append(rel)                  # eigene Fassung
                continue
            _in_papierkorb(wurzel, pfad, jetzt)
            verschoben += 1
        except OSError as exc:
            _log(f"WARNUNG: {rel} blieb liegen ({type(exc).__name__}: {exc})")
            behalten.append(rel)
    return verschoben, behalten


def _entfernen(wurzel: Path, daten: Path, eng, jetzt: datetime) -> dict:
    markierung = _markierung_lesen(daten)
    if not markierung or markierung.get("status") != "vorhanden":
        raise ValueError("Es sind keine Beispieldaten vorhanden, die entfernt werden könnten.")
    ids = {tabelle: [int(i) for i in werte] for tabelle, werte in (markierung.get("ids") or {}).items()}

    _aktive_aufgaben_pruefen(eng, ids)
    sicherungsdatei = _sicherung_anlegen(daten, eng, jetzt)
    entfernt, geloest, pfade = _datenbank_aufraeumen(eng, ids, markierung.get("profil_werte") or {})

    # Dateien erst nach dem Commit: Scheitert ein Verschieben, bleibt eine Datei liegen statt einer
    # Datenbank, die auf Gelöschtes zeigt. Die Verbindungen sind hier bereits geschlossen.
    verschoben, behalten = _dateien_aufraeumen(wurzel, markierung.get("dateien") or {}, jetzt)
    verschoben += _artefakte_verschieben(wurzel, pfade, jetzt)
    entfernt["dateien"] = verschoben

    _markierung_schreiben(daten, {
        "status": "entfernt", "name": markierung.get("name") or NAME,
        "angelegt_am": markierung.get("angelegt_am"), "entfernt_am": jetzt.isoformat(timespec="seconds"),
        "sicherung": sicherungsdatei, "ids": {}, "dateien": {},
    })
    _log(f"Beispieldaten entfernt, Sicherung {sicherungsdatei}.")
    return {"ok": True, "entfernt": entfernt, "geloest": geloest, "behalten": behalten,
            "sicherung": sicherungsdatei, "status": status(daten)}


def entfernen(*, projekt_root=None, daten_dir=None, engine=None, jetzt=None) -> dict:
    """Entfernt die Beispieldaten (Ablauf s. Moduldocstring). Antwortkörper für
    `POST /api/beispieldaten/entfernen`:

        {"ok": True, "entfernt": {Art: Anzahl, ..., "dateien": Anzahl}, "geloest": {"mails": n,
         "aufgaben": n}, "behalten": [relative Pfade eigener Fassungen], "sicherung": "<Dateiname>",
         "status": {...wie `status()`...}}

    Wirft `ValueError` mit Kundentext, wenn nichts zu entfernen ist, eine Sicherung oder das Entfernen
    schon läuft oder an einer Beispielstelle eine Aufgabe arbeitet (Router: 409), und `RuntimeError`,
    wenn die Sicherung scheitert (Router: 500). In beiden Fällen bleibt alles unverändert."""
    wurzel = _projekt_root(projekt_root)
    daten = _daten_dir(daten_dir)
    eng = _engine(engine)
    jetzt = _jetzt(jetzt)
    if not _LOCK.acquire(blocking=False):
        raise ValueError("Die Beispieldaten werden gerade entfernt. Bitte warten Sie einen Moment.")
    try:
        return _entfernen(wurzel, daten, eng, jetzt)
    finally:
        _LOCK.release()
