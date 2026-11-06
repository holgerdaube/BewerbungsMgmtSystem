"""Netzwerk-Import (P2-62, Paket I): Zielfirmen, Headhunter und Netzwerk-Kontakte aus einer Datei.

Wer eine Liste aufbaut, hat die Einträge meist schon als Tabelle: in Excel, als CSV oder als
Export der eigenen Verbindungen bei LinkedIn. Dieses Modul liest so eine Datei, zeigt vorher, was
passieren würde (`vorschau`, schreibt nie), und legt die Einträge danach an (`importieren`). Der
Router `app/routes_netzwerk_import.py` übersetzt nur die Ausnahmen `ImportFehler` in HTTP-Status.

Öffentliche Funktionen (Vertrag V1 bis V7 der Bau-Spec P2-62):

    vorlage(liste, format)                                   -> (Inhalt, Dateiname, Media-Type)
    vorschau(liste, dateiname, inhalt, *, session)           -> dict
    importieren(liste, dateiname, inhalt, *, session, daten_dir=None) -> dict

Regeln, die man dem Code nicht ansieht:

* Bestehende Einträge werden nie überschrieben, nur leere Felder werden ergänzt, und in der App
  gelöschte Einträge (Tombstones, `deleted_at`) bleiben gelöscht. Das ist die Regel des alten
  Drive-Imports (`import_lists._upsert`, Phase 22); dessen Skript gehört nicht ins Kundenpaket und
  wird deshalb nicht importiert. Die Schlüssel sind dieselben wie bei den Anlege-Endpunkten in
  `app/main.py` (`app.normalize.slug_parts`), damit ein importierter Eintrag und ein von Hand
  angelegter nie nebeneinander stehen.
* Der Import setzt KEIN `next_action_date`. Der Einzel-Endpunkt für Kontakte setzt ohne Angabe
  heute plus zehn Werktage; bei einem Import mit hunderten Zeilen stünden sonst alle am selben Tag
  als fällige Aktion unter den Follow-ups.
* Atomar ist der Import nur mit einem ausdrücklichen `BEGIN IMMEDIATE`. `flush_or_duplicate`
  arbeitet mit einem SAVEPOINT je Zeile, und pysqlite eröffnet bei der ersten Anweisung, die kein
  INSERT, UPDATE oder DELETE ist, keine Transaktion: Der SAVEPOINT startet sie, sein RELEASE
  schließt sie wieder mit einem COMMIT. Ohne die Vorkehrung bliebe nach einem Fehler mitten im
  Schreiben ein Teil der Zeilen stehen (belegt in `tests/test_netzwerk_import.py`). Der Beginn mit
  Schreibsperre verhindert außerdem, dass zwischen Planung und Schreiben jemand dazwischenschreibt.
* Die Excel-Vorlage und der Excel-Export der App (`pipeline/export_excel.py`) müssen sich wieder
  einlesen lassen. Der Export schreibt in die Spalte „Karriereseite“ ersatzweise die Webseite; sie
  wird beim Rückimport nicht als Karriereseite übernommen (Feld `nicht_gleich`), denn der
  Zielfirmen-Sweep behandelt eine gesetzte `karriere_url` als geprüften Treffer und läse sonst die
  Startseite als Karriereseite.
"""
from __future__ import annotations

import csv
import io
import itertools
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Callable, Iterator

from sqlalchemy.exc import OperationalError
from sqlmodel import select

from app.models import Headhunter, NetworkContact, TargetCompany
from app.normalize import slug_parts
from app.sprache import aktuell, datum as sprach_datum, tx, uebersetzt
from app.terminal import tt
from app.zeit import jetzt_utc

MAX_BYTES = 5 * 1024 * 1024       # Obergrenze der Datei, geprüft vor dem Lesen
MAX_ZEILEN = 5000                 # Obergrenze der Datenzeilen (ohne Kopfzeile und Leerzeilen)
ZEILEN_UEBRIGE = 100              # so viele Zeilen ohne Besonderheit zeigt die Vorschau höchstens
_KOPF_SUCHE = 30                  # so weit sucht die Kopfzeile von LinkedIn nach unten
_PROBE_ZEICHEN = 100_000          # Ausschnitt für Kopfzeilen- und Trennzeichensuche
_MAX_ENTPACKT = 200 * 1024 * 1024  # entpackte Größe einer .xlsx, Schutz vor Zip-Bomben

# ── Texte für Kunden (Sie-Form, keine Gedankenstriche, nichts Internes) ──────────────────────
# Die Konstanten sind deutsch und stehen als Schlüssel im Katalog; `ImportFehler` und die Stellen, an denen
# sie als Meldung in die Antwort gehen, übersetzen sie erst beim Auslösen (`uebersetzt`).
TEXT_ZU_GROSS = "Die Datei ist größer als 5 MB. Bitte teilen Sie sie in mehrere Dateien auf."
TEXT_SICHERUNG_LAEUFT = "Es läuft gerade eine Sicherung. Bitte versuchen Sie es gleich noch einmal."
_TEXT_UNBEKANNTE_LISTE = "Diese Liste gibt es nicht. Möglich sind zielfirmen, headhunter und kontakte."
_TEXT_UNBEKANNTES_FORMAT = "Dieses Format gibt es nicht. Möglich sind csv und xlsx."
_TEXT_LEER = "Die Datei ist leer."
_TEXT_XLS = ("Das alte Excel-Format .xls wird nicht gelesen. Bitte speichern Sie die Datei in Excel "
             "als .xlsx oder .csv.")
_TEXT_DATEITYP = ("Dieser Dateityp wird nicht gelesen. Bitte laden Sie eine Datei mit der Endung "
                  ".csv, .txt oder .xlsx hoch.")
_TEXT_CSV_UNLESBAR = "Die Datei konnte nicht als CSV-Tabelle gelesen werden."
_TEXT_XLSX_UNLESBAR = ("Die Excel-Datei konnte nicht gelesen werden. Bitte speichern Sie sie in "
                       "Excel erneut als .xlsx.")
_TEXT_KEIN_BLATT = "Die Excel-Datei enthält kein Tabellenblatt."
_TEXT_XLSX_ZU_GROSS = "Die Excel-Datei ist zu umfangreich. Bitte teilen Sie sie in mehrere Dateien auf."
_TEXT_KEIN_KOPF = ("In der Datei wurde keine Kopfzeile gefunden. Die erste Zeile mit Inhalt muss "
                   "die Spaltenüberschriften enthalten.")
_TEXT_DB_BELEGT = "Die Datenbank ist gerade belegt. Bitte versuchen Sie es gleich noch einmal."
_TEXT_LINKEDIN = ("LinkedIn-Exporte enthalten alle Verbindungen. Die Liste Netzwerk-Kontakte ist für "
                  "Kontakte gedacht, die Sie aktiv pflegen. Löschen Sie vorher Zeilen, die Sie dort "
                  "nicht brauchen.")
_TEXT_NUR_KOPFZEILE = "Die Datei enthält nur eine Kopfzeile, es gibt nichts zu importieren."
_TEXT_GELOESCHT = ("Dieser Eintrag wurde in der App gelöscht und wird übersprungen. Sie können ihn "
                   "im Papierkorb wiederherstellen.")
_DATUM_HINWEIS = "Datum als TT.MM.JJJJ oder JJJJ-MM-TT, zum Beispiel 31.12.2026."


class ImportFehler(Exception):
    """Ein Fehler, den der Nutzer lesen soll: `status` ist der HTTP-Status, `text` der Kundentext."""

    def __init__(self, status: int, text: str):
        text = uebersetzt(text)
        super().__init__(text)
        self.status = status
        self.text = text


# ── Werte: Zellen, Daten und Schreibweisen (V6) ──────────────────────────────────────────────
_UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _schluessel(text) -> str:
    """Spaltenüberschrift (V4) als Vergleichsschlüssel: klein, Umlaute aufgelöst, nur a bis z und
    0 bis 9. NFC zuerst, denn ein „ü“ aus macOS-Dateien kann aus „u“ und einem Trema bestehen."""
    klein = unicodedata.normalize("NFC", str(text or "")).lower().translate(_UMLAUTE)
    return re.sub(r"[^a-z0-9]+", "", klein)


def _tausender(zahl: int) -> str:
    """5000 als „5.000“ (de) beziehungsweise „5,000“ (en)."""
    text = f"{zahl:,}"
    return text if aktuell() == "en" else text.replace(",", ".")


def _leer(wert) -> bool:
    return wert is None or not str(wert).strip()


def _zelle(wert) -> str | None:
    """Rohwert einer Zelle (CSV-Text oder Excel-Typ) als getrimmter Text, leer als None. Ganze
    Zahlen aus Excel ohne „.0“, Excel-Daten als ISO-Datum, Wahrheitswerte als Ja oder Nein."""
    if wert is None:
        return None
    if isinstance(wert, bool):
        return "Ja" if wert else "Nein"
    if isinstance(wert, datetime):
        return wert.date().isoformat()
    if isinstance(wert, date):
        return wert.isoformat()
    if isinstance(wert, float):
        if wert != wert or wert in (float("inf"), float("-inf")):
            return None
        return str(int(wert)) if wert.is_integer() else repr(wert)
    if isinstance(wert, int):
        return str(wert)
    text = str(wert).replace("\xa0", " ").strip().strip("\ufeff\u200b").strip()
    return text or None


_MONATE = {"jan": 1, "jae": 1, "feb": 2, "mar": 3, "mae": 3, "mrz": 3, "apr": 4, "may": 5, "mai": 5,
           "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "okt": 10, "nov": 11, "dec": 12,
           "dez": 12}
_ISO_DATUM = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ].*)?")
_DE_DATUM = re.compile(r"(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{2}|\d{4})")
_EN_DATUM = re.compile(r"(\d{1,2})\.?\s+([^\W\d_]{3,9})\.?,?\s+(\d{4})")


def _datum_iso(text: str) -> str | None:
    """ISO bleibt, „TT.MM.JJJJ“ und „T.M.JJ“ werden ISO, ebenso „12 Sep 2023“ aus LinkedIn. Nicht
    lesbar (auch ein Tag, den es nicht gibt): None. Zweistellige Jahre zählen ab 2000."""
    s = text.strip()
    if (m := _ISO_DATUM.fullmatch(s)):
        jahr, monat, tag = (int(x) for x in m.groups())
    elif (m := _DE_DATUM.fullmatch(s)):
        tag, monat, jahr = (int(x) for x in m.groups())
        if jahr < 100:
            jahr += 2000
    elif (m := _EN_DATUM.fullmatch(s)):
        tag, jahr = int(m.group(1)), int(m.group(3))
        monat = _MONATE.get(_schluessel(m.group(2))[:3])
        if monat is None:
            return None
    else:
        return None
    try:
        return date(jahr, monat, tag).isoformat()
    except ValueError:
        return None


def _datum_text(text: str) -> str:
    """Datum, das als Text erhalten bleibt, wenn es sich nicht lesen lässt (letzter Kontakt, Stand)."""
    return _datum_iso(text) or text


def _datum_streng(text: str) -> str | None:
    """Datum, das überwacht wird (`next_action_date`): Nicht Lesbares wird NICHT übernommen."""
    return _datum_iso(text)


def _de_datum(iso_oder_text: str) -> str:
    """ISO-Datum in der Schreibweise der Oberflächensprache (de `TT.MM.JJJJ`, en `TT/MM/JJJJ`)."""
    if re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", iso_oder_text):
        return sprach_datum(iso_oder_text)
    return iso_oder_text


_PRIORITAETEN = {"hoch": "Hoch", "high": "Hoch", "mittel": "Mittel", "medium": "Mittel",
                 "mid": "Mittel", "niedrig": "Niedrig", "low": "Niedrig", "gering": "Niedrig"}
_KANAELE = {"linkedin": "LinkedIn", "email": "E-Mail", "mail": "E-Mail", "telefon": "Telefon",
            "phone": "Telefon", "tel": "Telefon", "anruf": "Telefon", "call": "Telefon",
            "persoenlich": "Persönlich", "inperson": "Persönlich", "personal": "Persönlich",
            "vorort": "Persönlich"}


def _prioritaet(text: str) -> str:
    return _PRIORITAETEN.get(_schluessel(text), text)


def _kanal(text: str) -> str:
    return _KANAELE.get(_schluessel(text), text)


def _tier(text: str) -> str:
    """„1“, „1.0“ und „Tier 1“ sind dasselbe Tier; alles andere bleibt, wie es ist."""
    m = re.fullmatch(r"(?:tier\s*)?(\d+)(?:[.,]0+)?", text.strip(), re.IGNORECASE)
    return str(int(m.group(1))) if m else text


def _szenario(text: str) -> str:
    """Ein Buchstabe oder mehrere („a“, „a/b“) werden groß; ein längerer Text bleibt."""
    return text.upper() if re.fullmatch(r"[A-Za-z](?:\s*[/,&+]\s*[A-Za-z])*", text.strip()) else text


def _url_vergleich(wert) -> str:
    """Webadresse ohne Schema, ohne „www.“ und ohne Schrägstrich am Ende, zum Vergleichen."""
    s = str(wert or "").strip().lower()
    s = re.sub(r"^[a-z][a-z0-9+.-]*://", "", s)
    return re.sub(r"^www\.", "", s).rstrip("/")


# ── Konfiguration je Liste (V4): EINE Tabelle für Modell, Spalten, Pflicht und Anzeige ───────
@dataclass(frozen=True)
class Feld:
    name: str                              # Feld im Modell, bei Hilfsfeldern nur ein Schlüssel
    vorlage: str                           # Spaltenname in der Vorlage, zugleich Anzeigename
    synonyme: tuple = ()                   # weitere erkannte Überschriften
    pflicht: str = ""                      # Text der Spalte „Pflicht“ im Blatt „Hinweise“
    hinweis: str = ""                      # erlaubte Werte und Formate für das Blatt „Hinweise“
    norm: Callable | None = None           # Schreibweise des Werts; None heißt: nicht lesbar
    in_vorlage: bool = True
    modellfeld: bool = True                # False: Hilfsfeld, wird vor dem Planen aufgelöst
    nicht_gleich: str | None = None        # nicht ergänzen, wenn gleich diesem Feld (Webadressen)


@dataclass(frozen=True)
class Liste:
    kennung: str
    titel: str                             # Name in Texten, Blatt und Dateiname der Vorlage
    modell: type
    felder: tuple
    blaetter: tuple                        # passende Blattnamen einer Excel-Datei, in Rangfolge
    schluessel: tuple                      # Felder des `dedup_key` (wie die Anlege-Endpunkte)
    pflicht_spalten: tuple                 # mindestens eine dieser Spalten muss es geben
    pflicht_werte: tuple                   # mindestens eines dieser Felder braucht je Zeile einen Wert
    anzeige: tuple                         # Felder der Anzeige „A · B“
    spalte_fehlt: str
    zeile_fehlt: str
    zeile_unlesbar: str
    standard_neu: tuple = ()               # (Feld, Funktion) für neue Einträge ohne Wert


_ZIELFIRMEN = Liste(
    kennung="zielfirmen", titel="Zielfirmen", modell=TargetCompany,
    felder=(
        Feld("company", "Firma", ("Company", "Unternehmen", "Zielfirma", "Name"), pflicht="Ja",
             hinweis="Name der Firma. Jede Firma wird nur einmal angelegt."),
        Feld("industry", "Branche", ("Industry",), hinweis="Freitext."),
        Feld("size_ma", "Größe (MA)", ("Mitarbeiter", "Größe", "Size", "Employees"),
             hinweis="Freitext oder Zahl, zum Beispiel 5000 oder 1000 bis 5000."),
        Feld("revenue", "Umsatz", ("Revenue",), hinweis="Freitext, zum Beispiel 120 Mio. EUR."),
        Feld("location_hq", "HQ", ("Hauptsitz", "Standort", "Location", "Ort"),
             hinweis="Ort des Hauptsitzes."),
        Feld("ownership", "Eigentümer", ("Ownership", "Eigentum"),
             hinweis="Freitext, zum Beispiel börsennotiert, Familienunternehmen oder Private Equity."),
        Feld("tier", "Tier", ("Stufe",), norm=_tier,
             hinweis="1, 2 oder 3. 1 ist die höchste Priorität. Auch Schreibweisen wie Tier 1 "
                     "werden erkannt."),
        Feld("scenario", "Szenario", ("Scenario",), norm=_szenario,
             hinweis="A, B oder C. Kleinbuchstaben werden in Großbuchstaben umgewandelt."),
        Feld("key_contact", "Key Contact", ("Ansprechpartner", "Kontakt"),
             hinweis="Name der wichtigsten Kontaktperson in der Firma."),
        Feld("connection_status", "Status", ("Connection Status", "Verbindung"),
             hinweis="Freitext, zum Beispiel der Stand Ihrer Verbindung zur Firma."),
        Feld("website", "Webseite", ("Website", "Homepage", "URL"), hinweis="Adresse der Firmenwebseite."),
        Feld("karriere_url", "Karriereseite", ("Karriere-URL", "Career URL", "Jobs"),
             nicht_gleich="website",
             hinweis="Adresse der Karriereseite. Ist sie gleich der Webseite einer vorhandenen Firma, "
                     "wird sie nicht als Karriereseite übernommen."),
        Feld("wachstumssignal", "Wachstumssignal", ("Growth Signal",), hinweis="Freitext."),
        Feld("ki_readiness", "KI-Readiness", ("AI Readiness",), hinweis="Freitext."),
        Feld("einschaetzung", "Einschätzung", ("Bewertung", "Assessment"), hinweis="Freitext."),
        Feld("ranking", "Ranking", ("Rang",), hinweis="Zahl oder Freitext, zum Beispiel 1."),
        Feld("last_update", "Letzte Aktualisierung", ("Last Update", "Stand"), norm=_datum_text,
             hinweis=_DATUM_HINWEIS + " Ohne Angabe wird bei neuen Einträgen das heutige Datum "
                                      "eingetragen."),
    ),
    blaetter=("Zielfirmen", "Target Companies"),
    schluessel=("company",), pflicht_spalten=("company",), pflicht_werte=("company",),
    anzeige=("company",),
    spalte_fehlt="Keine Spalte für die Firma gefunden. Erwartet wird zum Beispiel „Firma“.",
    zeile_fehlt="Es fehlt die Firma.",
    zeile_unlesbar="Die Firma enthält keine lateinischen Buchstaben oder Ziffern und kann nicht "
                   "angelegt werden.",
    standard_neu=(("last_update", lambda: _heute().isoformat()),),
)

_HEADHUNTER = Liste(
    kennung="headhunter", titel="Headhunter", modell=Headhunter,
    felder=(
        Feld("firma", "Firma", ("Company", "Unternehmen", "Agentur", "Personalberatung"),
             pflicht="Ja, wenn kein Ansprechpartner angegeben ist", hinweis="Name der Personalberatung."),
        Feld("ansprechpartner", "Ansprechpartner", ("Kontakt", "Name", "Contact", "Berater"),
             pflicht="Ja, wenn keine Firma angegeben ist", hinweis="Name der Ansprechperson."),
        Feld("fokus", "Fokus", ("Focus", "Schwerpunkt"),
             hinweis="Freitext, zum Beispiel Branche oder Funktion."),
        Feld("region", "Region", hinweis="Freitext, zum Beispiel DACH."),
        Feld("kanal", "Kanal", ("Channel",), hinweis="Freitext, zum Beispiel LinkedIn oder E-Mail."),
        Feld("linkedin_gefolgt", "LinkedIn gefolgt", ("LinkedIn",), hinweis="Ja oder Nein."),
        Feld("letzter_kontakt", "Letzter Kontakt", ("Last Contact",), norm=_datum_text,
             hinweis=_DATUM_HINWEIS),
        Feld("status", "Status", hinweis="Freitext."),
        Feld("webseite", "Webseite", ("Website", "URL", "Homepage"), hinweis="Adresse der Webseite."),
        Feld("notizen", "Notizen", ("Notes", "Notiz", "Bemerkung"), hinweis="Freitext."),
    ),
    blaetter=("Headhunter", "Headhunters"),
    schluessel=("firma", "ansprechpartner"), pflicht_spalten=("firma", "ansprechpartner"),
    pflicht_werte=("firma", "ansprechpartner"), anzeige=("firma", "ansprechpartner"),
    spalte_fehlt="Keine Spalte für die Firma oder den Ansprechpartner gefunden. Erwartet wird zum "
                 "Beispiel „Firma“ oder „Ansprechpartner“.",
    zeile_fehlt="Es fehlen Firma und Ansprechpartner.",
    zeile_unlesbar="Firma und Ansprechpartner enthalten keine lateinischen Buchstaben oder Ziffern "
                   "und können nicht angelegt werden.",
)

_KONTAKTE = Liste(
    kennung="kontakte", titel="Netzwerk-Kontakte", modell=NetworkContact,
    felder=(
        Feld("name", "Name", ("Full Name", "Kontakt"), pflicht="Ja",
             hinweis="Name der Person. Statt dieser Spalte können Sie auch die Spalten Vorname und "
                     "Nachname verwenden."),
        Feld("vorname", "Vorname", ("First Name",), in_vorlage=False, modellfeld=False),
        Feld("nachname", "Nachname", ("Last Name",), in_vorlage=False, modellfeld=False),
        Feld("beziehung", "Beziehung", ("Relationship",),
             hinweis="Freitext, zum Beispiel ehemalige Kollegin."),
        Feld("unternehmen", "Unternehmen", ("Firma", "Company", "Arbeitgeber"), hinweis="Freitext."),
        Feld("rolle", "Rolle", ("Position", "Funktion", "Title", "Job Title"), hinweis="Freitext."),
        Feld("prioritaet", "Priorität", ("Priority",), norm=_prioritaet,
             hinweis="Hoch, Mittel oder Niedrig. Auch high, medium und low werden erkannt."),
        Feld("letzter_kontakt", "Letzter Kontakt", ("Last Contact",), norm=_datum_text,
             hinweis=_DATUM_HINWEIS),
        Feld("kanal", "Kanal", ("Channel",), norm=_kanal,
             hinweis="LinkedIn, E-Mail, Telefon oder Persönlich. Auch email, phone und in person "
                     "werden erkannt."),
        Feld("next_action", "Nächste Aktion", ("Next Action",),
             hinweis="Freitext, zum Beispiel Kaffee vereinbaren."),
        Feld("next_action_date", "Fällig am", ("Fällig", "Next Action Date", "Due"), norm=_datum_streng,
             hinweis=_DATUM_HINWEIS + " Ohne Angabe wird kein Termin gesetzt."),
        Feld("notizen", "Notizen", ("Notes", "Notiz", "Bemerkung"), hinweis="Freitext."),
    ),
    blaetter=("Netzwerk", "Netzwerk-Kontakte", "Network Contacts", "Kontakte"),
    schluessel=("name", "unternehmen"), pflicht_spalten=("name", "vorname", "nachname"),
    pflicht_werte=("name",), anzeige=("name", "unternehmen"),
    spalte_fehlt="Keine Spalte für den Namen gefunden. Erwartet wird zum Beispiel „Name“ oder "
                 "„Vorname“ und „Nachname“.",
    zeile_fehlt="Es fehlt der Name.",
    zeile_unlesbar="Der Name enthält keine lateinischen Buchstaben oder Ziffern und kann nicht "
                   "angelegt werden.",
)

LISTEN = {liste.kennung: liste for liste in (_ZIELFIRMEN, _HEADHUNTER, _KONTAKTE)}

# Zusatzspalten der LinkedIn-Datei `Connections.csv`; Company und Position erkennt schon die
# Kontakte-Liste selbst (Unternehmen, Rolle), First und Last Name als Vorname und Nachname.
_LINKEDIN_ZUSATZ = (
    Feld("li_url", "Profil-Adresse", ("URL",), modellfeld=False),
    Feld("li_email", "E-Mail-Adresse", ("Email Address", "Email"), modellfeld=False),
    Feld("li_seit", "Verbunden seit", ("Connected On",), norm=_datum_text, modellfeld=False),
)


def _heute() -> date:
    """Eigene Funktion, damit ein Test das Datum festlegen kann."""
    return date.today()


def _liste(kennung: str) -> Liste:
    liste = LISTEN.get(str(kennung))
    if liste is None:
        raise ImportFehler(404, _TEXT_UNBEKANNTE_LISTE)
    return liste


# ── Datei lesen (V5) ─────────────────────────────────────────────────────────────────────────
@dataclass
class _Tabelle:
    art: str                               # "csv", "xlsx" oder "linkedin"
    blatt: str | None
    daten: list                            # (Zeilennummer, Zellen)
    hinweise: list
    zuordnung: dict                        # Spaltenindex -> Feld
    erkannt: list
    ignoriert: list


def _dekodieren(inhalt: bytes) -> str:
    """UTF-8 mit oder ohne BOM, sonst cp1252 (Excel unter Windows). UTF-16 mit BOM kommt vor, wenn
    jemand in Excel „Unicode-Text“ speichert; das BOM nennt die Byte-Reihenfolge."""
    if inhalt.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return inhalt.decode("utf-16")
        except UnicodeDecodeError as exc:
            raise ImportFehler(400, _TEXT_CSV_UNLESBAR) from exc
    if b"\x00" in inhalt:                  # Binärdatei (etwa eine umbenannte .xlsx), kein Text
        raise ImportFehler(400, _TEXT_CSV_UNLESBAR)
    try:
        return inhalt.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return inhalt.decode("cp1252")
    except UnicodeDecodeError:             # fünf Byte-Werte kennt cp1252 nicht; latin-1 kennt alle
        return inhalt.decode("latin-1")


def _ist_namenskopf(zellen) -> bool:
    return {"firstname", "lastname"} <= {_schluessel(z) for z in zellen if z}


def _ist_linkedin_kopf(kopf) -> bool:
    schluessel = {_schluessel(z) for z in kopf if z}
    return {"firstname", "lastname"} <= schluessel and bool({"connectedon", "url"} & schluessel)


def _trennzeichen(zeilen: list[str], liste: Liste) -> str:
    """Trennzeichen aus der Kopfzeile: `csv.Sniffer` entscheidet nur, wenn sein Ergebnis in der
    Kopfzeile mindestens so oft vorkommt wie jedes andere; sonst gilt das häufigste von Semikolon,
    Komma und Tab in der Kopfzeile (bei Gleichstand das Semikolon)."""
    zeilen = [z for z in zeilen if z.strip()]
    if not zeilen:
        return ";"
    index = 0
    if liste.kennung == "kontakte":        # LinkedIn: Hinweiszeilen stehen vor der Kopfzeile
        for i, zeile in enumerate(zeilen[:_KOPF_SUCHE]):
            if re.search(r"first\s*name", zeile, re.I) and re.search(r"last\s*name", zeile, re.I):
                index = i
                break
    kopf = zeilen[index]
    kandidaten = ";,\t"
    haeufigstes = max(kandidaten, key=kopf.count)
    try:
        gewaehlt = csv.Sniffer().sniff("\n".join(zeilen[index:index + 40]), delimiters=kandidaten).delimiter
    except csv.Error:
        gewaehlt = ""
    if gewaehlt and kopf.count(gewaehlt) > 0 and kopf.count(gewaehlt) >= kopf.count(haeufigstes):
        return gewaehlt
    return haeufigstes


def _kopf_und_daten(zeilen: Iterator, liste: Liste) -> tuple[list, list]:
    """Trennt die Kopfzeile von den Datenzeilen. Kopfzeile ist die erste Zeile mit Inhalt, bei
    Kontakten die erste mit „First Name“ und „Last Name“ (LinkedIn setzt Hinweiszeilen davor).
    Leere Zeilen fallen weg, zählen aber bei der Zeilennummer mit."""
    nicht_leer = ((nr, z) for nr, z in zeilen if any(c is not None for c in z))
    anfang = list(itertools.islice(nicht_leer, _KOPF_SUCHE))
    if not anfang:
        raise ImportFehler(400, _TEXT_KEIN_KOPF)
    index = 0
    if liste.kennung == "kontakte":
        for i, (_nr, zellen) in enumerate(anfang):
            if _ist_namenskopf(zellen):
                index = i
                break
    kopf = anfang[index][1]
    daten: list = []
    for nr, zellen in itertools.chain(anfang[index + 1:], nicht_leer):
        if len(daten) >= MAX_ZEILEN:
            raise ImportFehler(400, tx("Die Datei enthält mehr als {anzahl} Zeilen. Bitte teilen Sie sie in "
                                       "mehrere Dateien auf.", anzahl=_tausender(MAX_ZEILEN)))
        daten.append((nr, zellen))
    return kopf, daten


def _csv_lesen(liste: Liste, inhalt: bytes) -> tuple[list, list]:
    text = _dekodieren(inhalt)
    trennzeichen = _trennzeichen(text[:_PROBE_ZEICHEN].splitlines(), liste)

    def zeilen():
        # Zeilennummer = laufender Datensatz, so zählt Excel; ein Feld mit Zeilenumbruch in
        # Anführungszeichen verschiebt die Nummer gegenüber den Textzeilen nicht.
        for nr, zeile in enumerate(csv.reader(io.StringIO(text, newline=""), delimiter=trennzeichen), 1):
            yield nr, [_zelle(c) for c in zeile]

    try:
        return _kopf_und_daten(zeilen(), liste)
    except csv.Error as exc:
        raise ImportFehler(400, _TEXT_CSV_UNLESBAR) from exc


def _xlsx_lesen(liste: Liste, inhalt: bytes) -> tuple[str, bool, list, list]:
    import openpyxl                        # erst hier: der Import kostet einen Moment

    try:
        with zipfile.ZipFile(io.BytesIO(inhalt)) as archiv:
            entpackt = sum(info.file_size for info in archiv.infolist())
        if entpackt > _MAX_ENTPACKT:
            raise ImportFehler(400, _TEXT_XLSX_ZU_GROSS)
        arbeitsmappe = openpyxl.load_workbook(io.BytesIO(inhalt), read_only=True, data_only=True)
    except ImportFehler:
        raise
    except Exception as exc:               # noqa: BLE001 -- kaputtes ZIP, Passwortschutz, fremdes Format
        raise ImportFehler(400, _TEXT_XLSX_UNLESBAR) from exc
    try:
        blaetter = list(arbeitsmappe.worksheets)
        if not blaetter:
            raise ImportFehler(400, _TEXT_KEIN_BLATT)
        blatt = next((b for name in liste.blaetter for b in blaetter
                      if _schluessel(b.title) == _schluessel(name)), blaetter[0])
        # Eine falsche Dimensionsangabe (manche Programme schreiben „A1“) schnitte sonst Zeilen und
        # Spalten ab.
        blatt.reset_dimensions()

        def zeilen():
            for nr, zeile in enumerate(blatt.iter_rows(values_only=True), 1):
                yield nr, [_zelle(c) for c in zeile]

        try:
            kopf, daten = _kopf_und_daten(zeilen(), liste)
        except ImportFehler:
            raise
        except Exception as exc:           # noqa: BLE001 -- defektes Blatt
            raise ImportFehler(400, _TEXT_XLSX_UNLESBAR) from exc
        return blatt.title, len(blaetter) > 1, kopf, daten
    finally:
        arbeitsmappe.close()


def _einlesen(liste: Liste, dateiname: str, inhalt: bytes) -> _Tabelle:
    """Prüft die Datei, liest sie und ordnet die Spalten zu (V4, V5)."""
    if len(inhalt) > MAX_BYTES:
        raise ImportFehler(413, TEXT_ZU_GROSS)
    endung = PurePosixPath(str(dateiname or "").replace("\\", "/")).suffix.lower()
    if endung == ".xls":
        raise ImportFehler(400, _TEXT_XLS)
    if endung not in (".csv", ".txt", ".xlsx"):
        raise ImportFehler(400, _TEXT_DATEITYP)
    if not inhalt:
        raise ImportFehler(400, _TEXT_LEER)

    hinweise: list = []
    if endung == ".xlsx":
        blatt, mehrere, kopf, daten = _xlsx_lesen(liste, inhalt)
        art = "xlsx"
        if mehrere:
            hinweise.append(tx("Die Datei enthält mehrere Tabellenblätter. "
                               "Gelesen wird das Blatt „{blatt}“.", blatt=blatt))
    else:
        blatt = None
        kopf, daten = _csv_lesen(liste, inhalt)
        art = "csv"
    # LinkedIn auch als .xlsx (Abnahme P2-62): Der Hinweis unten rät, die Datei vorher zu kürzen, und
    # wer das in Excel tut, speichert oft als Arbeitsmappe. Ohne diese Erkennung gingen Kanal und
    # Notizen (Profil-Adresse, Mailadresse, Verbindungsdatum) verloren.
    if liste.kennung == "kontakte" and _ist_linkedin_kopf(kopf):
        art = "linkedin"
        hinweise.append(uebersetzt(_TEXT_LINKEDIN))
    felder = liste.felder + (_LINKEDIN_ZUSATZ if art == "linkedin" else ())
    zuordnung, erkannt, ignoriert = _spalten_zuordnen(kopf, felder)
    if not any(feld.name in liste.pflicht_spalten for feld in zuordnung.values()):
        raise ImportFehler(400, liste.spalte_fehlt)
    if not daten:
        hinweise.append(uebersetzt(_TEXT_NUR_KOPFZEILE))
    return _Tabelle(art, blatt, daten, hinweise, zuordnung, erkannt, ignoriert)


def _spalten_zuordnen(kopf: list, felder: tuple) -> tuple[dict, list, list]:
    """V4: Die erste passende Spalte je Feld gewinnt, jede weitere für dasselbe Feld und jede ohne
    Zuordnung ist ignoriert. Rückgabe: {Spaltenindex: Feld}, erkannte und ignorierte Spalten."""
    nach_name: dict = {}
    for feld in felder:
        for name in (feld.vorlage, *feld.synonyme):
            nach_name.setdefault(_schluessel(name), feld)
    zuordnung: dict = {}
    erkannt: list = []
    ignoriert: list = []
    belegt: set = set()
    for index, text in enumerate(kopf):
        if not text:
            continue
        feld = nach_name.get(_schluessel(text))
        if feld is None or feld.name in belegt:
            ignoriert.append(text)
            continue
        belegt.add(feld.name)
        zuordnung[index] = feld
        erkannt.append({"spalte": text, "feld": feld.name, "label": feld.vorlage})
    return zuordnung, erkannt, ignoriert


# ── Zeilen auswerten und planen (V6, V7) ─────────────────────────────────────────────────────
def _zeilenwerte(liste: Liste, zuordnung: dict, zellen: list, linkedin: bool) -> tuple[dict, list]:
    """Werte einer Zeile je Feld, schon in der Schreibweise der App, dazu Meldungen."""
    werte: dict = {}
    meldungen: list = []
    for index, feld in zuordnung.items():
        roh = zellen[index] if index < len(zellen) else None
        wert = None
        if roh is not None:
            wert = feld.norm(roh) if feld.norm else roh
            if wert is None:
                meldungen.append(tx("Das Datum in der Spalte „{spalte}“ ist nicht lesbar und wurde "
                                    "nicht übernommen. Erwartet wird zum Beispiel 31.12.2026.",
                                    spalte=feld.vorlage))
        werte[feld.name] = wert
    if liste.kennung == "kontakte":
        _kontakt_aufloesen(werte, linkedin)
    return werte, meldungen


def _kontakt_aufloesen(werte: dict, linkedin: bool) -> None:
    """Hilfsfelder auflösen: Name aus Vorname und Nachname (Zeile ohne Name), bei LinkedIn zudem
    Kanal und Notizen aus Adresse, Mailadresse und Verbindungsdatum."""
    if _leer(werte.get("name")):
        teile = (werte.get("vorname"), werte.get("nachname"))
        werte["name"] = " ".join(t for t in teile if t) or None
    if linkedin:
        if _leer(werte.get("kanal")):
            werte["kanal"] = "LinkedIn"
        teile = []
        if werte.get("li_url"):
            teile.append(tx("LinkedIn: {adresse}", adresse=werte["li_url"]))
        if werte.get("li_email"):
            teile.append(tx("E-Mail: {adresse}", adresse=werte["li_email"]))
        if werte.get("li_seit"):
            teile.append(tx("verbunden seit {datum}", datum=_de_datum(werte["li_seit"])))
        if teile and _leer(werte.get("notizen")):
            werte["notizen"] = " · ".join(teile)
    for hilfsfeld in ("vorname", "nachname", "li_url", "li_email", "li_seit"):
        werte.pop(hilfsfeld, None)


def _anzeige(liste: Liste, werte: dict) -> str:
    text = " · ".join(" ".join(str(werte[f]).split()) for f in liste.anzeige if not _leer(werte.get(f)))
    if not text:
        return tx("(ohne Angabe)")
    return text if len(text) <= 120 else text[:119] + "…"


@dataclass
class _Auftrag:
    """Ein Eintrag, der geschrieben wird: neu (`db` ist None) oder eine Ergänzung an `db`."""
    schluessel: str
    db: object | None
    felder: dict


@dataclass
class _Stand:
    """Was während der Planung über einen Schlüssel feststeht: die Zeile in der Datenbank (oder
    eine geplante neue), die Werte, die sie nach den bisherigen Zeilen hätte, und ob sie gelöscht ist."""
    werte: dict
    geloescht: bool
    erste_nr: int
    auftrag: _Auftrag | None


@dataclass
class _ZeileErgebnis:
    nr: int
    aktion: str
    anzeige: str
    felder_ergaenzt: list
    meldung: str | None

    def als_dict(self) -> dict:
        return {"nr": self.nr, "aktion": self.aktion, "anzeige": self.anzeige,
                "felder_ergaenzt": self.felder_ergaenzt, "meldung": self.meldung}


@dataclass
class _Plan:
    zeilen: list
    auftraege: list

    def anzahl(self) -> dict:
        zaehler = {"zeilen": len(self.zeilen), "neu": 0, "ergaenzt": 0, "unveraendert": 0,
                   "geloescht": 0, "fehler": 0}
        for zeile in self.zeilen:
            zaehler[zeile.aktion] += 1
        return zaehler


def _modellwerte(liste: Liste, zeile) -> dict:
    return {f.name: getattr(zeile, f.name, None) for f in liste.felder if f.modellfeld}


def _luecken(liste: Liste, stand: _Stand, werte: dict) -> dict:
    """Felder, in denen die Zeile einen Wert hat und der Eintrag noch keinen: nur diese werden
    ergänzt, nie wird etwas Gefülltes überschrieben."""
    neu: dict = {}
    for feld in liste.felder:
        wert = werte.get(feld.name)
        if not feld.modellfeld or wert is None or not _leer(stand.werte.get(feld.name)):
            continue
        if feld.nicht_gleich and _url_vergleich(wert) == _url_vergleich(stand.werte.get(feld.nicht_gleich)):
            continue
        neu[feld.name] = wert
    return neu


def _pflicht_fehler(liste: Liste, werte: dict) -> str | None:
    if any(slug_parts(werte.get(f)) for f in liste.pflicht_werte):
        return None
    if any(not _leer(werte.get(f)) for f in liste.pflicht_werte):
        return uebersetzt(liste.zeile_unlesbar)
    return uebersetzt(liste.zeile_fehlt)


def _planen(liste: Liste, tabelle: _Tabelle, session) -> _Plan:
    """Plant alle Zeilen gegen die Datenbank und gegen die Zeilen davor, schreibt aber nichts. Eine
    zweite Zeile mit demselben Schlüssel wirkt auf das Ergebnis der ersten: Sie kann deren leere
    Felder füllen, mehr nicht."""
    linkedin = tabelle.art == "linkedin"
    modellnamen = {f.name for f in liste.felder if f.modellfeld}
    bestand = {z.dedup_key: z for z in session.exec(select(liste.modell)).all() if z.dedup_key}
    stand_je_schluessel: dict = {}
    ergebnisse: list = []
    auftraege: list = []

    for nr, zellen in tabelle.daten:
        werte, meldungen = _zeilenwerte(liste, tabelle.zuordnung, zellen, linkedin)
        anzeige = _anzeige(liste, werte)
        fehler = _pflicht_fehler(liste, werte)
        if fehler:
            ergebnisse.append(_ZeileErgebnis(nr, "fehler", anzeige, [], " ".join([fehler, *meldungen])))
            continue
        schluessel = slug_parts(*(werte.get(f) for f in liste.schluessel))
        stand = stand_je_schluessel.get(schluessel)
        doppelt = stand is not None
        if doppelt:
            meldungen.insert(0, tx("Doppelt in der Datei, siehe Zeile {nr}.", nr=stand.erste_nr))
        elif schluessel in bestand:
            vorhanden = bestand[schluessel]
            stand = _Stand(_modellwerte(liste, vorhanden), bool(vorhanden.deleted_at), nr, None)
            stand_je_schluessel[schluessel] = stand
        else:
            felder_neu = {k: v for k, v in werte.items() if v is not None and k in modellnamen}
            auftrag = _Auftrag(schluessel, None, felder_neu)
            auftraege.append(auftrag)
            stand_je_schluessel[schluessel] = _Stand(dict(felder_neu), False, nr, auftrag)
            ergebnisse.append(_ZeileErgebnis(nr, "neu", anzeige, [], " ".join(meldungen) or None))
            continue

        if stand.geloescht:
            meldungen.append(uebersetzt(_TEXT_GELOESCHT))
            ergebnisse.append(_ZeileErgebnis(nr, "geloescht", anzeige, [], " ".join(meldungen)))
            continue
        neu = _luecken(liste, stand, werte)
        if neu:
            stand.werte.update(neu)
            if stand.auftrag is None:
                stand.auftrag = _Auftrag(schluessel, bestand[schluessel], {})
                auftraege.append(stand.auftrag)
            stand.auftrag.felder.update(neu)
        aktion = "ergaenzt" if neu else "unveraendert"
        ergaenzt = [f.name for f in liste.felder if f.name in neu]
        ergebnisse.append(_ZeileErgebnis(nr, aktion, anzeige, ergaenzt, " ".join(meldungen) or None))

    # Standardwerte erst am Ende: Eine spätere Zeile desselben Eintrags darf den Wert noch liefern.
    for auftrag in auftraege:
        if auftrag.db is None:
            for name, wert in liste.standard_neu:
                if _leer(auftrag.felder.get(name)):
                    auftrag.felder[name] = wert()
    return _Plan(ergebnisse, auftraege)


# ── Schreiben ────────────────────────────────────────────────────────────────────────────────
def _sicherung_anlegen(session, daten_dir) -> str:
    from app import sicherung

    engine = session.get_bind().engine
    db_pfad = Path(engine.url.database) if engine.url.database else None
    try:
        return sicherung.anlegen(daten_dir=daten_dir, db_pfad=db_pfad).name
    except sicherung.SicherungLaeuft:
        raise ImportFehler(409, TEXT_SICHERUNG_LAEUFT) from None
    except Exception as exc:               # noqa: BLE001 -- der Nutzer bekommt den Grund als Klartext
        raise ImportFehler(500, tx("Die Sicherung vor dem Import ist fehlgeschlagen, es wurde nichts "
                                   "importiert. Grund: {grund}",
                                   grund=str(exc) or type(exc).__name__)) from exc


def _schreibtransaktion_beginnen(session) -> None:
    """Öffnet die Transaktion ausdrücklich und mit Schreibsperre (Gründe im Moduldocstring). Steht
    die Verbindung schon in einer Transaktion, ist sie atomar und es bleibt, wie es ist."""
    verbindung = session.connection()
    if getattr(verbindung.connection.dbapi_connection, "in_transaction", False):
        return
    try:
        verbindung.exec_driver_sql("BEGIN IMMEDIATE")
    except OperationalError as exc:
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            raise ImportFehler(409, _TEXT_DB_BELEGT) from exc
        raise


def _schreiben(liste: Liste, plan: _Plan, session) -> list:
    """Schreibt die Aufträge in die laufende Transaktion. Rückgabe: Ergebnisse der Aufträge, die an
    einer Dublette scheiterten (ein gleichzeitiger Import hat den Schlüssel angelegt): Sie wirken
    dann wie eine Ergänzung, so wie in `import_lists._upsert`."""
    from app.db import flush_or_duplicate

    jetzt = jetzt_utc()
    rennen: list = []
    for auftrag in plan.auftraege:
        if auftrag.db is not None:
            for name, wert in auftrag.felder.items():
                setattr(auftrag.db, name, wert)
            auftrag.db.updated_at = jetzt
            session.add(auftrag.db)
            continue
        # `session.add` bewusst erst im Callback, s. Docstring von flush_or_duplicate.
        neu = liste.modell(dedup_key=auftrag.schluessel, **auftrag.felder)
        if flush_or_duplicate(session, lambda eintrag=neu: session.add(eintrag)):
            continue
        vorhanden = session.exec(select(liste.modell).where(
            liste.modell.dedup_key == auftrag.schluessel)).first()
        ergebnis = "geloescht" if vorhanden is not None and vorhanden.deleted_at else "unveraendert"
        if vorhanden is not None and not vorhanden.deleted_at:
            for name, wert in auftrag.felder.items():
                if _leer(getattr(vorhanden, name, None)):
                    setattr(vorhanden, name, wert)
                    ergebnis = "ergaenzt"
            if ergebnis == "ergaenzt":
                vorhanden.updated_at = jetzt
                session.add(vorhanden)
        rennen.append(ergebnis)
    return rennen


# ── Öffentliche Funktionen ───────────────────────────────────────────────────────────────────
def vorschau(liste: str, dateiname: str, inhalt: bytes, *, session) -> dict:
    """V2: liest und plant, schreibt NICHTS (keine Datenbankänderung, keine Sicherung).

    Antwort: `liste`, `format` (csv, xlsx, linkedin), `blatt` (nur bei Excel), `spalten` (`erkannt` mit
    spalte, feld und label, `ignoriert`), `anzahl` (zeilen, neu, ergaenzt, unveraendert, geloescht,
    fehler), `zeilen` (alle Fehler- und Gelöscht-Zeilen plus die ersten `ZEILEN_UEBRIGE` übrigen, in
    Dateireihenfolge), `zeilen_gekuerzt` und `hinweise`. `nr` einer Zeile ist die Zeilennummer in der
    Datei (Kopfzeile mitgezählt)."""
    cfg = _liste(liste)
    tabelle = _einlesen(cfg, dateiname, inhalt)
    plan = _planen(cfg, tabelle, session)
    auffaellig = [z for z in plan.zeilen if z.aktion in ("fehler", "geloescht")]
    uebrige = [z for z in plan.zeilen if z.aktion not in ("fehler", "geloescht")]
    gezeigt = sorted(auffaellig + uebrige[:ZEILEN_UEBRIGE], key=lambda z: z.nr)
    return {
        "liste": cfg.kennung,
        "format": tabelle.art,
        "blatt": tabelle.blatt,
        "spalten": {"erkannt": tabelle.erkannt, "ignoriert": tabelle.ignoriert},
        "anzahl": plan.anzahl(),
        "zeilen": [z.als_dict() for z in gezeigt],
        "zeilen_gekuerzt": len(uebrige) > ZEILEN_UEBRIGE,
        "hinweise": tabelle.hinweise,
    }


def importieren(liste: str, dateiname: str, inhalt: bytes, *, session, daten_dir=None) -> dict:
    """V3: plant neu und schreibt. Gibt es etwas zu schreiben (`neu + ergaenzt > 0`), entsteht
    vorher eine Sicherung; danach läuft alles in EINER Transaktion mit einem Commit. Scheitert die
    Sicherung, ist nichts geändert; scheitert das Schreiben, wird alles zurückgenommen.

    Geplant wird zweimal: erst nur lesend, um zu wissen, ob eine Sicherung nötig ist, dann unter
    der Schreibsperre, damit der Stand, der geschrieben wird, derselbe ist, gegen den geplant
    wurde. Die Antwort zählt aus der zweiten Planung.

    Antwort: `{"anzahl": {...wie bei der Vorschau...}, "sicherung": "<Dateiname>" oder None}`."""
    cfg = _liste(liste)
    tabelle = _einlesen(cfg, dateiname, inhalt)
    vorab = _planen(cfg, tabelle, session)
    if not vorab.auftraege:
        return {"anzahl": vorab.anzahl(), "sicherung": None}

    sicherungsdatei = _sicherung_anlegen(session, daten_dir)
    try:
        _schreibtransaktion_beginnen(session)
        session.expire_all()               # Stand aus der Datenbank, nicht aus der ersten Planung
        plan = _planen(cfg, tabelle, session)
        rennen = _schreiben(cfg, plan, session)
        session.commit()
    except ImportFehler:
        session.rollback()
        raise
    except Exception as exc:               # noqa: BLE001 -- der Nutzer bekommt den Grund als Klartext
        session.rollback()
        raise ImportFehler(500, tx("Der Import ist fehlgeschlagen, es wurde nichts importiert. "
                                   "Grund: {grund}", grund=str(exc) or type(exc).__name__)) from exc

    anzahl = plan.anzahl()
    for ergebnis in rennen:
        anzahl["neu"] -= 1
        anzahl[ergebnis] += 1
    print(tt("[netzwerk-import] {kennung}: {neu} neu, {ergaenzt} ergänzt, Sicherung {sicherung}", kennung=cfg.kennung, neu=anzahl['neu'], ergaenzt=anzahl['ergaenzt'], sicherung=sicherungsdatei), flush=True)
    return {"anzahl": anzahl, "sicherung": sicherungsdatei}


# ── Vorlagen (V1) ────────────────────────────────────────────────────────────────────────────
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_CSV = "text/csv; charset=utf-8"


def _vorlagenfelder(liste: Liste) -> list:
    return [f for f in liste.felder if f.in_vorlage]


def _vorlage_csv(liste: Liste) -> bytes:
    """Semikolon und UTF-8 mit BOM: So öffnet Excel die Datei im deutschen Raum mit Umlauten."""
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    schreiber.writerow([f.vorlage for f in _vorlagenfelder(liste)])
    return b"\xef\xbb\xbf" + puffer.getvalue().encode("utf-8")


def _vorlage_xlsx(liste: Liste) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    felder = _vorlagenfelder(liste)
    arbeitsmappe = Workbook()
    blatt = arbeitsmappe.active
    blatt.title = liste.titel
    blatt.append([f.vorlage for f in felder])
    for index, feld in enumerate(felder, 1):
        blatt.cell(row=1, column=index).font = Font(bold=True)
        blatt.column_dimensions[get_column_letter(index)].width = max(14, len(feld.vorlage) + 4)
    blatt.freeze_panes = "A2"

    hinweise = arbeitsmappe.create_sheet(tx("Hinweise"))
    hinweise.append([tx("Spalte"), tx("Pflicht"), tx("Erlaubte Werte und Format"),
                     tx("Weitere erkannte Spaltennamen")])
    for zelle in hinweise[1]:
        zelle.font = Font(bold=True)
    for feld in felder:
        hinweise.append([feld.vorlage, uebersetzt(feld.pflicht or "Nein"), uebersetzt(feld.hinweis),
                         ", ".join(feld.synonyme)])
    hinweise.append([])
    for satz in (tx("Jede Zeile des ersten Blatts ist ein Eintrag. Die Reihenfolge der Spalten ist beliebig, "
                    "Spalten mit anderen Überschriften werden ignoriert."),
                 tx("Bestehende Einträge werden nie überschrieben. Es werden nur leere Felder ergänzt."),
                 tx("Einträge, die Sie in der App gelöscht haben, bleiben gelöscht.")):
        hinweise.append([satz])
    for spalte, breite in zip("ABCD", (24, 40, 80, 50)):
        hinweise.column_dimensions[spalte].width = breite
    for zeile in hinweise.iter_rows(min_row=2, max_row=1 + len(felder)):
        for zelle in zeile:
            zelle.alignment = Alignment(wrap_text=True, vertical="top")
    puffer = io.BytesIO()
    arbeitsmappe.save(puffer)
    return puffer.getvalue()


def vorlage(liste: str, format: str) -> tuple[bytes, str, str]:
    """V1: nur die Kopfzeile mit den deutschen Spaltennamen, Pflichtspalten zuerst. Rückgabe:
    Inhalt, Dateiname, Media-Type."""
    cfg = _liste(liste)
    art = str(format or "").strip().lower()
    if art == "csv":
        return _vorlage_csv(cfg), f"Vorlage_{cfg.titel}.csv", _CSV
    if art == "xlsx":
        return _vorlage_xlsx(cfg), f"Vorlage_{cfg.titel}.xlsx", _XLSX
    raise ImportFehler(422, _TEXT_UNBEKANNTES_FORMAT)
