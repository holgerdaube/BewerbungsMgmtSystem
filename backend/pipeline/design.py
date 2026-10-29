"""Das Design des BMS aus einer Quelle (P2-72, Vertrag Q).

Farben, Schriften, Produktname und Icons stehen in EINER Design-Datei. Dieses Modul liest sie, prüft
sie Rolle für Rolle und gibt das geltende Design als unveränderliches Objekt heraus. Es braucht nur
die Standardbibliothek und kennt weder die App noch die Datenbank.

ZWEI ORTE, EIN FORMAT:
  * Vorgabe:        `assets/design/standard.json` (mit `icon-32.png` und `icon-180.png` daneben) —
                    Teil des Programms, das heutige Aussehen. Ein Update ersetzt sie.
  * Überschreibung: `<Datenordner>/design/design.json` (Icons daneben) — Datenordner wie in
                    `app/db.py` (`BMS_DATA_DIR`, sonst `<Projekt>/data`). `data/` ist für jedes
                    Paket gesperrt, die Überschreibung übersteht damit jedes Update.
Gelesen wird Rolle für Rolle: Was die Überschreibung nicht nennt oder was ungültig ist, kommt aus der
Vorgabe.

EIN UNGÜLTIGES DESIGN MACHT DAS BMS NIE UNBENUTZBAR (Leitentscheidung 5):
  * Farben nur als `#RRGGBB` (Groß-/Kleinschreibung egal, intern GROSS).
  * Die vier Paare aus Fläche und Schrift (`FARBPAARE`) gelten nur gemeinsam und nur mit Kontrast
    mindestens 4,5:1 (WCAG). Ein Paar mit nur einer Hälfte in der Überschreibung wird gegen die andere
    Hälfte aus der Vorgabe geprüft. Fällt ein Paar durch, gilt für DIESES Paar die Vorgabe. `text`
    gehört zu zwei Paaren (mit `flaeche` und mit `karte`): Alle Paare werden gleichzeitig geprüft, die
    durchgefallenen fallen auf die Vorgabe zurück, danach wird erneut geprüft, bis nichts mehr kippt.
    Das Ergebnis hängt so nicht von der Reihenfolge in der Datei ab.
  * Die VORGABE wird nie am Kontrast gemessen. Sie hat mit Absicht Weiß auf Cyan (rund 2,5:1,
    Leitentscheidung 3). Ein Paar der Überschreibung, das der Vorgabe wörtlich gleicht (etwa eine
    unveränderte Kopie von `standard.json`), gilt deshalb ohne Prüfung und ohne Warnung.
  * Schriften nur aus `SCHRIFTEN` (was die Oberfläche mitbringt, plus Systemschrift).
  * `produktname`: 3 bis 40 Zeichen, eine Zeile, keine Steuerzeichen. **Nur die Vorgabe nennt ihn.**
    Vorgabe 14.10.2026: Der Name bleibt „Bewerbungs-Management-System“, auch mit einem anderen Design
    (Partner). Steht er in einer Überschreibung, gilt die Vorgabe, dazu eine Warnung.
  * Icons: nur Dateinamen ohne Pfadanteil, im Ordner der jeweiligen JSON-Datei, PNG (Signatur und
    IHDR-Kopf geprüft), quadratisch, höchstens 200 KB.
  * Kaputtes JSON, falsches `format`, unbekannte Felder, eine Datei statt eines Objekts: nie eine
    Ausnahme nach außen, sondern Vorgabe und eine Warnung. Unbekannte Felder werden ignoriert.
Jede Ablehnung steht als Warnung im Log (einmal je Änderung der Dateien) und in `Design.warnungen`.
Einzige Ausnahme: Ist die VORGABE selbst unbrauchbar (beschädigte Installation), wirft `laden()` einen
`DesignFehler`. Einen eingebauten Notfall-Satz Farben gibt es bewusst nicht — er wäre eine zweite
Quelle.

ZWISCHENSPEICHER: Schlüssel sind Größe und Änderungszeit der beiden JSON-Dateien (dazu die der Icons,
die geprüft wurden). Wer eine Datei ändert, sieht es beim nächsten `laden()`, ohne Neustart.

Kommandozeile (es liest nur):
    cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.design zeigen

Das CSS der Berichte und der Befehl zum Einsetzen liegen in einem eigenen Modul (Vertrag R).
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import struct
import sys
import threading
import unicodedata
import zlib
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, NamedTuple, Optional

PROJEKT_ROOT = Path(__file__).resolve().parents[2]
VORGABE_DATEI = PROJEKT_ROOT / "assets" / "design" / "standard.json"

# Überschreibung: `<Datenordner>/design/design.json`. Der Datenordner wird bei jedem Aufruf neu
# bestimmt (`ueberschreibung_pfad`), nie beim Import: Tests lenken `BMS_DATA_DIR` um.
UEBERSCHREIBUNG_ORDNER = "design"
UEBERSCHREIBUNG_NAME = "design.json"

FORMAT = 1
QUELLE_VORGABE = "vorgabe"
QUELLE_UEBERSCHREIBUNG = "ueberschreibung"

# Die 13 Farbrollen (Leitentscheidung 1) in der Reihenfolge der Design-Datei.
FARBROLLEN = (
    "marke", "auf_marke", "aktion", "aktion_hover", "auf_aktion", "stahl", "flaeche", "karte",
    "rahmen", "spur", "text", "text_gedaempft", "trenner",
)
# Paare aus Fläche und Schrift darauf: gelten nur gemeinsam und nur mit ausreichendem Kontrast.
FARBPAARE = (
    ("marke", "auf_marke"), ("aktion", "auf_aktion"), ("flaeche", "text"), ("karte", "text"),
)
KONTRAST_MIN = 4.5

SCHRIFTROLLEN = ("ueberschrift", "text")
# Erlaubte Schriften und ihr vollständiger Schriftstapel (wie bisher in `tailwind.config.js`:
# `heading` = Montserrat, `sans` = Inter). Eigene Schriftdateien eines Partners gibt es in diesem
# Schritt nicht (Leitentscheidung 11).
SCHRIFTEN = {
    "Inter": "'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif",
    "Montserrat": "'Montserrat', 'Poppins', Arial, sans-serif",
    "System": "system-ui, -apple-system, 'Segoe UI', sans-serif",
}

NAME_LAENGE = (1, 40)
PRODUKTNAME_LAENGE = (3, 40)

ICON_GROESSEN = ("32", "180")
ICON_MAX_BYTES = 200 * 1024
# Obergrenze der Kantenlänge: Ein winziges PNG kann Milliarden Bildpunkte versprechen, und das
# Favicon lädt jede Seite des BMS. Ohne Grenze ließe sich der Browser damit lahmlegen.
ICON_MAX_PIXEL = 1024
_ICON_NAME_MAX = 100
_PNG_SIGNATUR = b"\x89PNG\r\n\x1a\n"

# Eine Design-Datei ist wenige hundert Bytes groß; alles darüber ist kein Design.
JSON_MAX_BYTES = 64 * 1024

_DATEI_FELDER = ("format", "name", "farben", "schriften", "produktname", "icon")

_LOG = logging.getLogger(__name__)


class DesignFehler(RuntimeError):
    """Die VORGABE ist unbrauchbar (Datei fehlt, kaputt, unvollständig): beschädigte Installation.
    Fehler in der Überschreibung lösen das nie aus, sie werden zu Warnungen."""


@dataclass(frozen=True)
class Design:
    """Das geltende Design. Unveränderlich; `laden()` gibt dasselbe Objekt zurück, solange sich keine
    Datei ändert.

    name          Bezeichnung des Designs („Standard“)
    produktname   Anzeigename des Programms (Titel, Seitenleiste). Wer ihn in HTML setzt, maskiert ihn.
    quelle        "vorgabe" oder "ueberschreibung" (mindestens ein Wert stammt aus der Überschreibung)
    farben        Rolle -> "#RRGGBB" (GROSS), alle 13 Rollen aus `FARBROLLEN`
    schriften     Rolle ("ueberschrift", "text") -> Name aus `SCHRIFTEN`
    icons         Größe ("32", "180") -> Pfad der geprüften PNG-Datei
    warnungen     abgelehnte Werte der Überschreibung, je ein Satz
    stand         Kennzeichen des Inhalts (für den ETag): ändert sich mit jedem Wert, jeder
                  Warnung und jedem Byte der Icons, nicht mit der Änderungszeit der Dateien
    """
    name: str
    produktname: str
    quelle: str
    farben: Mapping[str, str]
    schriften: Mapping[str, str]
    icons: Mapping[str, Path]
    warnungen: tuple
    stand: str

    def __hash__(self) -> int:       # die Mappings sind nicht hashbar; der Stand reicht
        return hash(self.stand)

    def icon(self, groesse) -> Optional[Path]:
        """Pfad des Icons der Größe 32 oder 180 (int oder str), sonst None."""
        return self.icons.get(str(groesse))

    def icon_bytes(self, groesse) -> Optional[bytes]:
        """Inhalt des Icons (höchstens `ICON_MAX_BYTES`) oder None, wenn es fehlt oder nicht lesbar ist."""
        pfad = self.icon(groesse)
        if pfad is None:
            return None
        try:
            with pfad.open("rb") as f:
                daten = f.read(ICON_MAX_BYTES + 1)
        except OSError:
            return None
        return daten if len(daten) <= ICON_MAX_BYTES else None


# ── Farbrechnung ──────────────────────────────────────────────────────────────────────────────
def ist_farbe(wert) -> bool:
    """Nur `#RRGGBB` (sieben Zeichen, hexadezimal); ein angehängter Zeilenumbruch gilt nicht."""
    if not isinstance(wert, str) or len(wert) != 7 or wert[0] != "#":
        return False
    return all(c in "0123456789abcdefABCDEF" for c in wert[1:])


def _rgb(farbe: str) -> tuple:
    return int(farbe[1:3], 16), int(farbe[3:5], 16), int(farbe[5:7], 16)


def kanaele(farbe: str) -> str:
    """"#0B1F3A" -> "11 31 58" (für `rgb(var(--marke) / <alpha-value>)`)."""
    r, g, b = _rgb(farbe)
    return f"{r} {g} {b}"


def _linear(kanal: int) -> float:
    s = kanal / 255
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def leuchtdichte(farbe: str) -> float:
    """Relative Leuchtdichte nach WCAG 2 (Schwelle 0,04045; bei 8 Bit gleich der älteren 0,03928)."""
    r, g, b = _rgb(farbe)
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def kontrast(farbe_a: str, farbe_b: str) -> float:
    """Kontrastverhältnis nach WCAG 2 (1 bis 21), unabhängig von der Reihenfolge."""
    la, lb = leuchtdichte(farbe_a), leuchtdichte(farbe_b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _kontrast_text(wert: float) -> str:
    """"4,49" — abgerundet, damit knapp unter 4,5 nie als „4,50“ erscheint."""
    return f"{math.floor(wert * 100) / 100:.2f}".replace(".", ",")


# ── Pfade ─────────────────────────────────────────────────────────────────────────────────────
def datenordner() -> Path:
    """Datenordner wie `app/db.py` (`BMS_DATA_DIR`, sonst `<Projekt>/data`), bei jedem Aufruf frisch."""
    return Path(os.environ.get("BMS_DATA_DIR", PROJEKT_ROOT / "data"))


def ueberschreibung_pfad() -> Path:
    return datenordner() / UEBERSCHREIBUNG_ORDNER / UEBERSCHREIBUNG_NAME


# ── Einzelprüfungen ───────────────────────────────────────────────────────────────────────────
def _kurz(wert) -> str:
    """Wert für eine Warnung: maskiert (keine Zeilenumbrüche im Log) und gekürzt."""
    text = repr(wert)
    return text if len(text) <= 48 else text[:45] + "..."


def _einzeiler(wert, laenge: tuple) -> Optional[str]:
    """Text in einer Zeile, ohne Steuerzeichen (Unicode-Klasse C*, dazu Zeilen-/Absatztrenner),
    Länge in Zeichen; Leerraum am Rand wird abgeschnitten. Sonst None."""
    if not isinstance(wert, str):
        return None
    text = wert.strip()
    if not laenge[0] <= len(text) <= laenge[1]:
        return None
    for zeichen in text:
        klasse = unicodedata.category(zeichen)
        if klasse.startswith("C") or klasse in ("Zl", "Zp"):
            return None
    return text


def _ist_dateiname(wert) -> bool:
    """Nur ein Dateiname: kein Pfadtrenner (`/`, `\\`), kein Laufwerk oder Datenstrom (`:`), keine
    Steuerzeichen, nicht `.` oder `..`, nicht leer."""
    if not isinstance(wert, str) or not wert or wert != wert.strip():
        return False
    if len(wert) > _ICON_NAME_MAX or wert in (".", ".."):
        return False
    return not any(z in "/\\:" or ord(z) < 32 or ord(z) == 127 for z in wert)


def _png_kopf(daten: bytes) -> Optional[tuple]:
    """(Breite, Höhe) aus dem IHDR-Kopf, wenn Signatur, Kopf-Chunk und seine Prüfsumme stimmen,
    sonst None. Kein Fremdpaket, das Bild selbst wird nicht dekodiert."""
    if len(daten) < 33 or daten[:8] != _PNG_SIGNATUR:
        return None
    laenge, typ = struct.unpack(">I4s", daten[8:16])
    if laenge != 13 or typ != b"IHDR":
        return None
    if struct.unpack(">I", daten[29:33])[0] != zlib.crc32(daten[12:29]):
        return None
    return struct.unpack(">II", daten[16:24])


def _signatur(pfad: Path):
    """(Größe, Änderungszeit in ns) einer Datei oder None, wenn es sie nicht gibt."""
    try:
        st = pfad.stat()
    except OSError:
        return None
    return st.st_size, st.st_mtime_ns


class _Icon(NamedTuple):
    pfad: Path
    pruefsumme: str


class _Teil(NamedTuple):
    """Die geprüften Werte EINER Datei (Vorgabe oder Überschreibung); fehlende Rollen fehlen."""
    name: Optional[str]
    produktname: Optional[str]
    farben: dict
    schriften: dict
    icons: dict


def _icon_pruefen(ordner: Path, angabe, groesse: str, wo: str, warnungen: list,
                  abhaengig: list) -> Optional[_Icon]:
    """Prüft ein Icon (Name, Lage, Größe, PNG-Kopf, quadratisch). Jede Datei, die dabei angefasst
    wird, kommt in `abhaengig`: Ändert sie sich später, muss der Zwischenspeicher neu rechnen."""
    if not _ist_dateiname(angabe):
        warnungen.append(f"{wo}: Icon {groesse}: erlaubt ist nur ein Dateiname ohne Pfad "
                         f"({_kurz(angabe)}).")
        return None
    pfad = ordner / angabe
    abhaengig.append((pfad, _signatur(pfad)))
    try:
        if not pfad.is_file():
            warnungen.append(f"{wo}: Icon {groesse}: Datei {_kurz(angabe)} fehlt.")
            return None
        if Path(os.path.realpath(pfad)).parent != Path(os.path.realpath(ordner)):
            warnungen.append(f"{wo}: Icon {groesse}: {_kurz(angabe)} liegt nicht im Ordner der "
                             "Design-Datei.")
            return None
        with pfad.open("rb") as f:
            daten = f.read(ICON_MAX_BYTES + 1)
    except OSError as fehler:
        warnungen.append(f"{wo}: Icon {groesse}: {_kurz(angabe)} nicht lesbar ({fehler.strerror or 'Fehler'}).")
        return None
    if len(daten) > ICON_MAX_BYTES:
        warnungen.append(f"{wo}: Icon {groesse}: {_kurz(angabe)} ist größer als "
                         f"{ICON_MAX_BYTES // 1024} KB.")
        return None
    kopf = _png_kopf(daten)
    if kopf is None:
        warnungen.append(f"{wo}: Icon {groesse}: {_kurz(angabe)} ist kein PNG.")
        return None
    breite, hoehe = kopf
    if breite != hoehe or not 0 < breite <= ICON_MAX_PIXEL:
        warnungen.append(f"{wo}: Icon {groesse}: {_kurz(angabe)} muss quadratisch sein (1 bis "
                         f"{ICON_MAX_PIXEL} Bildpunkte), ist aber {breite} x {hoehe}.")
        return None
    return _Icon(pfad, hashlib.sha256(daten).hexdigest())


def _teil_pruefen(daten: dict, ordner: Path, wo: str, warnungen: list,
                  abhaengig: list, fester_produktname: Optional[str] = None) -> Optional[_Teil]:
    """Prüft den Inhalt EINER Design-Datei Wert für Wert. None, wenn die Datei als Ganzes nicht gilt
    (kein Objekt, falsches `format`). Einzelne ungültige Werte entfallen mit je einer Warnung.
    `fester_produktname` (nur bei der Überschreibung): Der Produktname ist fest (Moduldoc). Ein anderer
    Wert in der Datei entfällt mit einer Warnung; derselbe Wert wie in der Vorgabe (etwa eine
    unveränderte Kopie von `standard.json`) bleibt ohne Warnung."""
    format_ = daten.get("format")
    if type(format_) is not int or format_ != FORMAT:       # weder True noch 1.0 noch "1"
        warnungen.append(f"{wo}: Unbekanntes Format ({_kurz(format_)}), erwartet {FORMAT}. Die "
                         "Datei wird nicht gelesen.")
        return None
    unbekannt = sorted(str(k) for k in daten if k not in _DATEI_FELDER)
    if unbekannt:
        warnungen.append(f"{wo}: Unbekannte Felder werden ignoriert: {', '.join(map(_kurz, unbekannt))}.")

    name = None
    if "name" in daten:
        name = _einzeiler(daten["name"], NAME_LAENGE)
        if name is None:
            warnungen.append(f"{wo}: Name {_kurz(daten['name'])} ist unbrauchbar (1 bis "
                             f"{NAME_LAENGE[1]} Zeichen, eine Zeile, keine Steuerzeichen).")

    produktname = None
    if "produktname" in daten and fester_produktname is not None:
        if daten["produktname"] != fester_produktname:
            warnungen.append(f"{wo}: Der Produktname ist fest und lässt sich nicht überschreiben "
                             f"({_kurz(daten['produktname'])} wird ignoriert).")
    elif "produktname" in daten:
        produktname = _einzeiler(daten["produktname"], PRODUKTNAME_LAENGE)
        if produktname is None:
            warnungen.append(f"{wo}: Produktname {_kurz(daten['produktname'])} ist unbrauchbar "
                             f"({PRODUKTNAME_LAENGE[0]} bis {PRODUKTNAME_LAENGE[1]} Zeichen, eine "
                             "Zeile, keine Steuerzeichen).")

    farben = {}
    if "farben" in daten:
        if isinstance(daten["farben"], dict):
            unbekannt = sorted(str(k) for k in daten["farben"] if k not in FARBROLLEN)
            if unbekannt:
                warnungen.append(f"{wo}: Unbekannte Farbrollen werden ignoriert: "
                                 f"{', '.join(map(_kurz, unbekannt))}.")
            for rolle in FARBROLLEN:
                if rolle not in daten["farben"]:
                    continue
                if ist_farbe(daten["farben"][rolle]):
                    farben[rolle] = daten["farben"][rolle].upper()
                else:
                    warnungen.append(f"{wo}: Farbe „{rolle}“: {_kurz(daten['farben'][rolle])} ist "
                                     "kein Wert der Form #RRGGBB.")
        else:
            warnungen.append(f"{wo}: „farben“ muss ein Objekt sein.")

    schriften = {}
    if "schriften" in daten:
        if isinstance(daten["schriften"], dict):
            unbekannt = sorted(str(k) for k in daten["schriften"] if k not in SCHRIFTROLLEN)
            if unbekannt:
                warnungen.append(f"{wo}: Unbekannte Schriftrollen werden ignoriert: "
                                 f"{', '.join(map(_kurz, unbekannt))}.")
            for rolle in SCHRIFTROLLEN:
                if rolle not in daten["schriften"]:
                    continue
                wert = daten["schriften"][rolle]
                if isinstance(wert, str) and wert in SCHRIFTEN:
                    schriften[rolle] = wert
                else:
                    warnungen.append(f"{wo}: Schrift „{rolle}“: {_kurz(wert)} ist nicht erlaubt "
                                     f"(erlaubt: {', '.join(SCHRIFTEN)}).")
        else:
            warnungen.append(f"{wo}: „schriften“ muss ein Objekt sein.")

    icons = {}
    if "icon" in daten:
        if isinstance(daten["icon"], dict):
            unbekannt = sorted(str(k) for k in daten["icon"] if k not in ICON_GROESSEN)
            if unbekannt:
                warnungen.append(f"{wo}: Unbekannte Icon-Größen werden ignoriert: "
                                 f"{', '.join(map(_kurz, unbekannt))}.")
            for groesse in ICON_GROESSEN:
                if groesse in daten["icon"]:
                    icon = _icon_pruefen(ordner, daten["icon"][groesse], groesse, wo, warnungen,
                                         abhaengig)
                    if icon is not None:
                        icons[groesse] = icon
        else:
            warnungen.append(f"{wo}: „icon“ muss ein Objekt sein.")

    return _Teil(name, produktname, farben, schriften, icons)


def _datei_lesen(pfad: Path, wo: str, warnungen: list) -> Optional[dict]:
    """Liest eine Design-Datei als JSON-Objekt. None, wenn es sie nicht gibt (ohne Warnung) oder sie
    unbrauchbar ist (mit Warnung)."""
    try:
        with pfad.open("rb") as f:
            roh = f.read(JSON_MAX_BYTES + 1)
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as fehler:
        warnungen.append(f"{wo}: Datei nicht lesbar ({fehler.strerror or 'Fehler'}).")
        return None
    if len(roh) > JSON_MAX_BYTES:
        warnungen.append(f"{wo}: Datei ist größer als {JSON_MAX_BYTES // 1024} KB.")
        return None
    try:
        daten = json.loads(roh.decode("utf-8-sig"))
    except (ValueError, RecursionError):      # kaputtes JSON, keine UTF-8-Datei, zu tief verschachtelt
        warnungen.append(f"{wo}: Datei ist kein gültiges JSON.")
        return None
    if not isinstance(daten, dict):
        warnungen.append(f"{wo}: Die Datei enthält kein JSON-Objekt.")
        return None
    return daten


def _vorgabe_lesen(pfad: Path, abhaengig: list) -> _Teil:
    """Die Vorgabe: vollständig und ohne jede Beanstandung, sonst `DesignFehler`."""
    wo = "Vorgabe"
    meldungen: list = []
    daten = _datei_lesen(pfad, wo, meldungen)
    if daten is None and not meldungen:
        meldungen.append(f"{wo}: {pfad.name} fehlt.")
    teil = _teil_pruefen(daten, pfad.parent, wo, meldungen, abhaengig) if daten is not None else None
    if teil is not None and not meldungen:
        fehlt = [r for r in FARBROLLEN if r not in teil.farben]
        fehlt += [f"schrift_{r}" for r in SCHRIFTROLLEN if r not in teil.schriften]
        fehlt += [f"icon_{g}" for g in ICON_GROESSEN if g not in teil.icons]
        fehlt += [f for f, v in (("name", teil.name), ("produktname", teil.produktname)) if v is None]
        if fehlt:
            meldungen.append(f"{wo}: unvollständig, es fehlt: {', '.join(fehlt)}.")
    if teil is None or meldungen:
        raise DesignFehler(" ".join(meldungen))
    return teil


def _ueberschreibung_lesen(pfad: Path, warnungen: list, abhaengig: list,
                           fester_produktname: str) -> Optional[_Teil]:
    wo = "Überschreibung"
    daten = _datei_lesen(pfad, wo, warnungen)
    if daten is None:
        return None
    return _teil_pruefen(daten, pfad.parent, wo, warnungen, abhaengig, fester_produktname)


def _paare_pruefen(vorgabe: dict, angeboten: dict, warnungen: list) -> dict:
    """Welche Farben der Überschreibung gelten, nach der Paarregel (Moduldoc). Gibt die angenommenen
    Rollen zurück; alle übrigen kommen aus der Vorgabe."""
    gueltig = dict(angeboten)
    while True:
        durchgefallen = []
        for a, b in FARBPAARE:
            if a not in gueltig and b not in gueltig:
                continue
            ca, cb = gueltig.get(a, vorgabe[a]), gueltig.get(b, vorgabe[b])
            if (ca, cb) == (vorgabe[a], vorgabe[b]):    # wörtlich die Vorgabe: nie ablehnen
                continue
            verhaeltnis = kontrast(ca, cb)
            if verhaeltnis < KONTRAST_MIN:
                durchgefallen.append((a, b, ca, cb, verhaeltnis))
        if not durchgefallen:
            return gueltig
        for a, b, ca, cb, verhaeltnis in durchgefallen:       # erst alle prüfen, dann alle streichen
            warnungen.append(
                f"Überschreibung: Farbpaar {a}/{b} ({ca} auf {cb}) hat nur {_kontrast_text(verhaeltnis)}:1 "
                f"Kontrast, nötig sind {str(KONTRAST_MIN).replace('.', ',')}:1. Für dieses Paar gilt die Vorgabe.")
            gueltig.pop(a, None)
            gueltig.pop(b, None)


def _stand(inhalt: dict, icons: Mapping) -> str:
    h = hashlib.sha256(json.dumps(inhalt, sort_keys=True, ensure_ascii=True).encode("ascii"))
    for groesse in ICON_GROESSEN:
        h.update(groesse.encode("ascii") + b":" + icons[groesse].pruefsumme.encode("ascii") + b";")
    return h.hexdigest()[:20]


def _zusammenfuehren(v: _Teil, o: Optional[_Teil], warnungen: list) -> Design:
    """Vorgabe `v`, darüber die Überschreibung `o`, Rolle für Rolle."""
    o = o or _Teil(None, None, {}, {}, {})
    gueltige_farben = _paare_pruefen(v.farben, o.farben, warnungen) if o.farben else {}
    farben = {r: gueltige_farben.get(r, v.farben[r]) for r in FARBROLLEN}
    schriften = {r: o.schriften.get(r, v.schriften[r]) for r in SCHRIFTROLLEN}
    icons = {g: o.icons.get(g, v.icons[g]) for g in ICON_GROESSEN}
    name = o.name or v.name
    produktname = v.produktname          # fest, s. Moduldoc (die Überschreibung nennt ihn nie)
    aus_ueberschreibung = bool(o.name or gueltige_farben or o.schriften or o.icons)
    quelle = QUELLE_UEBERSCHREIBUNG if aus_ueberschreibung else QUELLE_VORGABE
    stand = _stand({"name": name, "produktname": produktname, "quelle": quelle, "farben": farben,
                    "schriften": schriften, "warnungen": warnungen}, icons)
    return Design(name=name, produktname=produktname, quelle=quelle,
                  farben=MappingProxyType(farben), schriften=MappingProxyType(schriften),
                  icons=MappingProxyType({g: i.pfad for g, i in icons.items()}),
                  warnungen=tuple(warnungen), stand=stand)


# ── Zwischenspeicher und Einstieg ─────────────────────────────────────────────────────────────
_sperre = threading.Lock()
_speicher: dict = {}


def zwischenspeicher_leeren() -> None:
    with _sperre:
        _speicher.clear()


def _laden(vorgabe_datei: Path, ueberschreibung_datei: Optional[Path]) -> Design:
    schluessel = (str(vorgabe_datei), str(ueberschreibung_datei) if ueberschreibung_datei else None)
    with _sperre:
        eintrag = _speicher.get(schluessel)
        dateien = (_signatur(vorgabe_datei),
                   _signatur(ueberschreibung_datei) if ueberschreibung_datei else None)
        if (eintrag is not None and eintrag["dateien"] == dateien
                and all(_signatur(p) == s for p, s in eintrag["abhaengig"])):
            return eintrag["design"]
        warnungen: list = []
        abhaengig: list = []
        vorgabe = _vorgabe_lesen(vorgabe_datei, abhaengig)
        ueberschreibung = (_ueberschreibung_lesen(ueberschreibung_datei, warnungen, abhaengig,
                                                  vorgabe.produktname)
                           if ueberschreibung_datei else None)
        design = _zusammenfuehren(vorgabe, ueberschreibung, warnungen)
        for satz in warnungen:
            _LOG.warning("Design: %s", satz)
        if len(_speicher) >= 16:
            _speicher.clear()
        _speicher[schluessel] = {"dateien": dateien, "abhaengig": tuple(abhaengig), "design": design}
        return design


def laden(vorgabe_datei: Optional[Path] = None,
          ueberschreibung_datei: Optional[Path] = None) -> Design:
    """Das geltende Design: Vorgabe, darüber die Überschreibung, Rolle für Rolle geprüft. Wirft nie,
    außer bei unbrauchbarer Vorgabe (`DesignFehler`). Ohne Argumente gelten `VORGABE_DATEI` und
    `ueberschreibung_pfad()`; Tests geben eigene Pfade unter `tmp_path` mit."""
    return _laden(Path(vorgabe_datei) if vorgabe_datei else VORGABE_DATEI,
                  Path(ueberschreibung_datei) if ueberschreibung_datei else ueberschreibung_pfad())


def vorgabe(vorgabe_datei: Optional[Path] = None) -> Design:
    """Nur die Vorgabe, ohne Überschreibung: für alles, was immer das Standard-Design zeigt (die
    mitgelieferten `docs/*.html`, der Vergleich von Icons)."""
    return _laden(Path(vorgabe_datei) if vorgabe_datei else VORGABE_DATEI, None)


# ── Hilfen für Oberfläche und Berichte ────────────────────────────────────────────────────────
def variablenname(rolle: str) -> str:
    """"auf_marke" -> "--auf-marke" (Kanäle `R G B`); die Farbe selbst steht in `<name>-farbe`."""
    return "--" + rolle.replace("_", "-")


def css_oberflaeche(design: Optional[Design] = None) -> str:
    """Der `:root`-Block für die Oberfläche (`GET /api/design.css`): je Farbrolle die Kanäle
    (`--marke: 11 31 58;`, für `rgb(var(--marke) / <alpha-value>)`) und die Farbe
    (`--marke-farbe: #0B1F3A;`), dazu `--schrift-ueberschrift` und `--schrift-text` als vollständige
    Schriftstapel. Nur Werte, die `laden()` geprüft hat; Namen und Texte des Designs stehen nicht darin."""
    d = design or laden()
    zeilen = [":root {"]
    for rolle in FARBROLLEN:
        name = variablenname(rolle)
        zeilen.append(f"  {name}: {kanaele(d.farben[rolle])};")
        zeilen.append(f"  {name}-farbe: {d.farben[rolle]};")
    for rolle in SCHRIFTROLLEN:
        zeilen.append(f"  --schrift-{rolle}: {SCHRIFTEN[d.schriften[rolle]]};")
    zeilen.append("}")
    return "\n".join(zeilen) + "\n"


# ── Kommandozeile ─────────────────────────────────────────────────────────────────────────────
def _zeigen() -> int:
    try:
        d = laden()
    except DesignFehler as fehler:
        print(f"Die Design-Vorgabe ist unbrauchbar: {fehler}", file=sys.stderr)
        return 1
    ueberschreibung = ueberschreibung_pfad()
    print(f"Geltendes Design: {d.name}")
    print(f"Quelle:           {d.quelle}")
    print(f"Produktname:      {d.produktname}")
    print(f"Stand:            {d.stand}")
    print(f"Vorgabe:          {VORGABE_DATEI}")
    print(f"Überschreibung:   {ueberschreibung}" + ("" if ueberschreibung.is_file() else " (keine Datei)"))
    print("Farben:")
    for rolle in FARBROLLEN:
        print(f"  {rolle:<15} {d.farben[rolle]}   {kanaele(d.farben[rolle])}")
    print("Farbpaare (Kontrast, nötig 4,5:1 für Werte der Überschreibung):")
    for a, b in FARBPAARE:
        print(f"  {a + '/' + b:<22} {_kontrast_text(kontrast(d.farben[a], d.farben[b]))}:1")
    print("Schriften:")
    for rolle in SCHRIFTROLLEN:
        print(f"  {rolle:<15} {d.schriften[rolle]}")
    print("Icons:")
    for groesse in ICON_GROESSEN:
        print(f"  {groesse:<15} {d.icons[groesse]}")
    if d.warnungen:
        print(f"Warnungen ({len(d.warnungen)}):")
        for satz in d.warnungen:
            print(f"  - {satz}")
    else:
        print("Warnungen: keine")
    return 0


def main(argv: Optional[list] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv != ["zeigen"]:
        print("Nutzung: python -m pipeline.design zeigen", file=sys.stderr)
        return 2
    # Die Warnungen stehen unten in der Ausgabe; ohne Handler würde `logging` sie zusätzlich auf
    # stderr wiederholen. Der Handler gilt nur für diesen Lauf.
    stumm = logging.NullHandler()
    _LOG.addHandler(stumm)
    try:
        return _zeigen()
    finally:
        _LOG.removeHandler(stumm)


if __name__ == "__main__":
    sys.exit(main())
