"""P2-69: Lesen und Schreiben von `config/profil.md` für die Karte „Identität und Suchstrategie“.

Die Datei bleibt die einzige Quelle. Die Leser (`pipeline/user_profile.py`, zwölf Skills) ändern sich
nicht; die Maske erzeugt genau die Schreibweise, die deren Regexe erwarten (`- **Name:** …`).

LEITENTSCHEIDUNG 1 (Verlustfreiheit) bestimmt den Aufbau dieses Moduls: Die Datei wird in ZEILEN MIT
IHREN ZEILENENDEN zerlegt (`_Zeile.inhalt` + `_Zeile.ende`, `\\n` oder `\\r\\n` oder leer bei der letzten
Zeile ohne Schluss-Zeilenende) und daraus wieder zusammengesetzt, nie über `"\\n".join`. Gelesen und
geschrieben wird als Bytes (UTF-8), damit nichts umgerechnet wird. Verändert wird ausschließlich, was
die Maske anzeigt UND was der Kunde geändert hat: unbekannte Abschnitte, unbekannte Zeilen in bekannten
Abschnitten, Empirie, „Sprachen / CV-Fassungen“, Leerzeilen, Kommentare, Unterüberschriften und der
Dateikopf bleiben Byte für Byte stehen. Ohne Änderung in der Maske ergibt Speichern dieselbe Datei
(`anwenden(text, lesen_aus_text(text)) == text`).

Aufbau:
  * Reine Funktionen: `zerlegen`/`zusammensetzen` (Vertrag F, Zerlegung), `lesen_aus_text`,
    `anwenden`, `kontakt_teilen`/`kontakt_zusammensetzen`, `hinweise_fuer`, `stand_von`.
  * Zwei I/O-Funktionen: `lesen()` und `schreiben(daten, stand)`. Der Pfad kommt ZUR LAUFZEIT aus
    `user_profile._PROFIL_MD` (Tests patchen denselben Pfad wie bisher), nie aus einer Kopie davon.
  * Kein Import aus `app` auf Modulebene. Nur der Papierkorb-Ordner (`app.db.DATA_DIR`, damit Tests
    ihn umlenken können) und das Namensmuster `app.naming.dated_filename` werden in
    `_papierkorb_ordner()`/`_papierkorb_name()` erst beim Aufruf geholt.

Zwei Schutzmechanismen vor dem Schreiben: der `stand` (SHA-256 der Dateibytes, leer bei fehlender
Datei) verhindert, dass die Maske eine inzwischen von einem Skill geänderte Datei überschreibt
(`StandVeraltet` → HTTP 409), und eine Kopie der alten Datei geht in den Papierkorb
(`data/papierkorb/JJJJMMTT_profil.md`, Leitentscheidung 3). Geschrieben wird atomar (Temp-Datei im
selben Ordner, `os.replace`).

Beispiele in Kommentaren und Texten: nur Max Mustermann / Musterstadt (Regel „keine Verlaufsspuren“).
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import tempfile
import threading
from collections import deque
from typing import Optional

from app.sprache import tx, uebersetzt
from pipeline import user_profile

# ── Konstanten ───────────────────────────────────────────────────────────────────────────────────
# Titel, Ebene und Branche der Zielrollen kommen aus den Suchplänen (`suchprofile.yaml`). Ältere Zeilen wie
# „Ebene“ bleiben in vorhandenen Dateien unberührt stehen, die Maske zeigt sie nur nicht mehr.
STANDARD_ZIELROLLE = ("Zieltermin",)
MAX_EINZEILIG = 300      # Zeichen je einzeiligem Feld
MAX_FREITEXT = 5000      # Zeichen je Freitext-Abschnitt

# Deutscher Text als Konstante; übersetzt wird beim Auslösen (`uebersetzt(STAND_VERALTET_TEXT)`).
STAND_VERALTET_TEXT = ("Die Profil-Datei wurde inzwischen geändert. Bitte laden Sie die Karte neu und "
                       "tragen Sie Ihre Änderung noch einmal ein.")

# Erkennung der bekannten Abschnitte: Überschrift (getrimmt, casefold) BEGINNT mit …
_IDENTITAET = "identität"
_KURZPROFIL = "kurzprofil"
_ZIELROLLE = "zielrolle"
_RAHMEN = "harte rahmenbedingungen"
_GAPS = "bekannte skill-gaps"
_EMPIRIE = "empirie"

# Feldzeile `- **Schlüssel:** Wert` (Vertrag F). Gruppe 1 = Einrückung + Aufzählungszeichen, 2 = Schlüssel,
# 3 = Wert. Beim Ändern wird nur Gruppe 3 ersetzt.
_FELD_RE = re.compile(r"^(\s*[-*]\s*)\*\*(.+?):\*\*[ \t]*(.*)$")

# Reihenfolge der Identitätsfelder in der Datei (so legt die Vorlage sie an) und ihre Schlüssel.
_IDENT_REIHE = ("name", "positionierung", "anschrift", "kontakt", "linkedin", "aktuell")
_IDENT_SCHLUESSEL = {"name": "Name", "positionierung": "Positionierung", "anschrift": "Standort",
                     "kontakt": "Kontakt", "linkedin": "LinkedIn", "aktuell": "Aktuell"}
# Bei leerem Wert entfällt die Zeile. Spec: Positionierung, LinkedIn, Aktuell. Zusätzlich Standort und
# Kontakt: Die Leser in `user_profile.py` suchen mit `\*\*Standort:\*\*\s*(.+)`, und `\s*` überspringt
# auch Zeilenumbrüche. Eine leere Zeile `- **Standort:**` ließe den Leser die FOLGENDE Zeile als
# Anschrift lesen (dasselbe bei Kontakt). Fehlt die Zeile, liefert der Leser sauber „leer“.
_ZEILE_ENTFAELLT_BEI_LEER = frozenset({"Positionierung", "LinkedIn", "Aktuell", "Standort", "Kontakt"})

_LABEL = {"name": "Name", "positionierung": "Positionierung", "anschrift": "Anschrift",
          "email": "E-Mail", "telefon": "Telefon", "linkedin": "LinkedIn", "aktuell": "Aktuell",
          "kurzprofil": "Kurzprofil", "rahmenbedingungen": "Harte Rahmenbedingungen",
          "skill_gaps": "Bekannte Skill-Gaps"}

_ZEILENTRENNER = "\n\r\x0b\x0c\x1c\x1d\x1e\x85  "

# Schreibvorgänge der Maske nacheinander: Stand prüfen und Datei ersetzen als ein Schritt.
_SPERRE = threading.Lock()


class StandVeraltet(Exception):
    """Der `stand` der Anfrage passt nicht zur Datei (HTTP 409). Bewusst KEIN `ValueError`, damit die
    Route Eingabefehler (400) und veralteten Stand (409) nicht verwechseln kann."""


class DateiNichtLesbar(ValueError):
    """Die Profil-Datei ist nicht als UTF-8 lesbar (von Hand mit anderer Kodierung gespeichert)."""


# ── Zerlegung (Vertrag F) ────────────────────────────────────────────────────────────────────────
class _Zeile:
    """Eine Zeile samt Zeilenende. `ende` ist `\\n`, `\\r\\n` oder leer (nur die letzte Datei-Zeile)."""
    __slots__ = ("inhalt", "ende")

    def __init__(self, inhalt: str, ende: str):
        self.inhalt = inhalt
        self.ende = ende

    def ist_leer(self) -> bool:
        return not self.inhalt.strip()


class Abschnitt:
    """Überschriftenzeile + Rumpfzeilen. Der Dateikopf ist ein Abschnitt ohne Überschrift
    (`ueberschrift is None`, `zeilen` ohne Überschriftenzeile); bei allen anderen ist `zeilen[0]` die
    Zeile `## …`."""

    def __init__(self, ueberschrift: Optional[str], zeilen: list[_Zeile]):
        self.ueberschrift = ueberschrift
        self.zeilen = zeilen


class Dokument:
    """Zerlegte Profil-Datei. `abschnitte[0]` ist immer der Kopf (kann leer sein)."""

    def __init__(self, abschnitte: list[Abschnitt], eol: str, ohne_schluss: bool):
        self.abschnitte = abschnitte
        self.eol = eol                    # vorherrschendes Zeilenende, gilt für NEUE Zeilen
        self.ohne_schluss = ohne_schluss  # Datei endet ohne Zeilenende

    def alle_zeilen(self) -> list[_Zeile]:
        return [z for a in self.abschnitte for z in a.zeilen]

    def finde(self, anfang: str) -> Optional[Abschnitt]:
        """Erster Abschnitt, dessen Überschrift (getrimmt, ohne Rücksicht auf Groß-/Kleinschreibung)
        mit `anfang` beginnt."""
        for a in self.abschnitte:
            if a.ueberschrift is not None and a.ueberschrift.casefold().startswith(anfang):
                return a
        return None

    def anlegen(self, titel: str) -> Abschnitt:
        """Neuer, leerer Abschnitt: vor „Empirie“, sonst am Dateiende."""
        neu = Abschnitt(titel, [_Zeile("## " + titel, self.eol)])
        for i, a in enumerate(self.abschnitte):
            if a.ueberschrift is not None and a.ueberschrift.casefold().startswith(_EMPIRIE):
                neu.zeilen.append(_Zeile("", self.eol))   # Leerzeile zwischen den Abschnitten
                self.abschnitte.insert(i, neu)
                return neu
        letzte = self.alle_zeilen()
        if letzte and not letzte[-1].ist_leer():
            self.abschnitte[-1].zeilen.append(_Zeile("", self.eol))
        self.abschnitte.append(neu)
        return neu

    def enden_richten(self) -> None:
        """Nach Änderungen: jede Zeile außer der letzten braucht ein Zeilenende (neue Zeilen tragen das
        vorherrschende). Endete die Datei ursprünglich ohne Zeilenende, bleibt das so."""
        zeilen = self.alle_zeilen()
        for i, z in enumerate(zeilen):
            if i < len(zeilen) - 1:
                if not z.ende:
                    z.ende = self.eol
            elif self.ohne_schluss:
                z.ende = ""
            elif not z.ende:
                z.ende = self.eol


def _zeilen(text: str) -> list[_Zeile]:
    """Zerlegt in Zeilen MIT ihrem Zeilenende. Getrennt wird nur an `\\n` (ein davor stehendes `\\r`
    gehört zum Zeilenende); andere Trennzeichen bleiben im Zeileninhalt. `"".join(inhalt + ende)` ergibt
    für jeden Text den Text zurück."""
    teile = text.split("\n")
    zeilen: list[_Zeile] = []
    for i, teil in enumerate(teile):
        if i == len(teile) - 1:
            if teil:                                   # letzte Zeile ohne Zeilenende
                zeilen.append(_Zeile(teil, ""))
        elif teil.endswith("\r"):
            zeilen.append(_Zeile(teil[:-1], "\r\n"))
        else:
            zeilen.append(_Zeile(teil, "\n"))
    return zeilen


def _dominantes_ende(text: str) -> str:
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    return "\r\n" if crlf > lf else "\n"


def zerlegen(text: str) -> Dokument:
    """Kopf (alles vor der ersten Zeile `## `) und Abschnitte (Überschriftenzeile + Rumpfzeilen).
    `### Unterüberschriften` beginnen keinen Abschnitt."""
    abschnitte = [Abschnitt(None, [])]
    zeilen = _zeilen(text)
    for z in zeilen:
        if z.inhalt.startswith("## "):
            abschnitte.append(Abschnitt(z.inhalt[3:].strip(), [z]))
        else:
            abschnitte[-1].zeilen.append(z)
    return Dokument(abschnitte, _dominantes_ende(text), bool(zeilen) and zeilen[-1].ende == "")


def zusammensetzen(dok: Dokument) -> str:
    """Setzt die Zeilen unverändert wieder zusammen (Zeileninhalt + eigenes Zeilenende)."""
    return "".join(z.inhalt + z.ende for z in dok.alle_zeilen())


def stand_von(inhalt: Optional[bytes]) -> str:
    """SHA-256 der Dateibytes; leer, wenn die Datei fehlt."""
    return "" if inhalt is None else hashlib.sha256(inhalt).hexdigest()


# ── Kontakt ──────────────────────────────────────────────────────────────────────────────────────
_KONTAKT_TRENNER = re.compile(r"\s*[·|]\s*")


def kontakt_teilen(wert: str) -> tuple[str, str]:
    """`Kontakt`-Wert → (E-Mail, Telefon). An `·` oder `|` teilen; der erste Teil mit `@` ist die
    E-Mail, der Rest (mit ` · ` verbunden) das Telefon."""
    email = ""
    rest: list[str] = []
    for teil in (t.strip() for t in _KONTAKT_TRENNER.split(wert or "")):
        if not teil:
            continue
        if not email and "@" in teil:
            email = teil
        else:
            rest.append(teil)
    return email, " · ".join(rest)


def kontakt_zusammensetzen(email: str, telefon: str) -> str:
    """`E-Mail · Telefon`; bei nur einem Wert ohne Trenner."""
    return " · ".join(t for t in ((email or "").strip(), (telefon or "").strip()) if t)


# ── Lesen ────────────────────────────────────────────────────────────────────────────────────────
def _kf(text: str) -> str:
    return text.strip().casefold()


def _felder(a: Abschnitt) -> list[tuple[int, re.Match]]:
    """Feldzeilen des Abschnitts als (Index in `a.zeilen`, Treffer); die Überschrift zählt nicht."""
    treffer = []
    for i, z in enumerate(a.zeilen):
        if a.ueberschrift is not None and i == 0:
            continue
        m = _FELD_RE.match(z.inhalt)
        if m:
            treffer.append((i, m))
    return treffer


def _ident_zuordnung(a: Abschnitt) -> tuple[dict, list[tuple[int, re.Match]]]:
    """Identität: erstes Vorkommen jedes bekannten Schlüssels (genaue Schreibweise, so wie auch
    `user_profile.py` sie sucht) → Maskenfeld; alle übrigen Feldzeilen (auch weitere Vorkommen
    desselben Schlüssels) sind `weitere`."""
    umgekehrt = {v: k for k, v in _IDENT_SCHLUESSEL.items()}
    zuordnung: dict = {}
    uebrige = []
    for i, m in _felder(a):
        feld = umgekehrt.get(m.group(2).strip())
        if feld and feld not in zuordnung:
            zuordnung[feld] = (i, m)
        else:
            uebrige.append((i, m))
    return zuordnung, uebrige


def _freitext_teile(a: Abschnitt) -> tuple[int, int]:
    """(Index des ersten Kern-Zeile, Index hinter der letzten) in `a.zeilen`; Kern = Rumpf ohne die
    Leerzeilen an Anfang und Ende. Besteht der Rumpf nur aus Leerzeilen (oder ist leer), ist der Kern
    leer und beginnt direkt hinter der Überschrift, die Leerzeilen zählen dann als „nach dem Rumpf“."""
    n = len(a.zeilen)
    von = 1
    while von < n and a.zeilen[von].ist_leer():
        von += 1
    if von == n:
        return 1, 1
    bis = n
    while a.zeilen[bis - 1].ist_leer():
        bis -= 1
    return von, bis


def _freitext_lesen(a: Optional[Abschnitt]) -> str:
    if a is None:
        return ""
    von, bis = _freitext_teile(a)
    return "\n".join(z.inhalt for z in a.zeilen[von:bis])


def _leere_daten() -> dict:
    return {
        "identitaet": {"name": "", "positionierung": "", "anschrift": "", "email": "", "telefon": "",
                       "linkedin": "", "aktuell": "", "weitere": []},
        "kurzprofil": "",
        "zielrolle": [{"schluessel": k, "wert": ""} for k in STANDARD_ZIELROLLE],
        "rahmenbedingungen": "",
        "skill_gaps": "",
        "unveraendert": [],
    }


def lesen_aus_text(text: Optional[str]) -> dict:
    """Maskenwerte aus dem Dateitext (`None` = Datei fehlt → leere Werte + Standard-Schlüssel der
    Zielrolle). Enthält `unveraendert`: Überschriften aller Abschnitte, die die Maske nicht anfasst."""
    if text is None:
        return _leere_daten()
    dok = zerlegen(text)
    daten = _leere_daten()

    behandelt: set[int] = set()
    ident = dok.finde(_IDENTITAET)
    if ident is not None:
        behandelt.add(id(ident))
        zuordnung, uebrige = _ident_zuordnung(ident)
        werte = {f: zuordnung[f][1].group(3).strip() for f in zuordnung}
        email, telefon = kontakt_teilen(werte.get("kontakt", ""))
        d = daten["identitaet"]
        d["name"] = werte.get("name", "")
        d["positionierung"] = werte.get("positionierung", "")
        d["anschrift"] = werte.get("anschrift", "")
        d["email"], d["telefon"] = email, telefon
        d["linkedin"] = werte.get("linkedin", "")
        d["aktuell"] = werte.get("aktuell", "")
        d["weitere"] = [{"schluessel": m.group(2).strip(), "wert": m.group(3).strip()} for _, m in uebrige]

    for schluessel, prefix in (("kurzprofil", _KURZPROFIL), ("rahmenbedingungen", _RAHMEN),
                               ("skill_gaps", _GAPS)):
        a = dok.finde(prefix)
        if a is not None:
            behandelt.add(id(a))
            daten[schluessel] = _freitext_lesen(a)

    ziel = dok.finde(_ZIELROLLE)
    if ziel is not None:
        behandelt.add(id(ziel))
        standard = {_kf(k) for k in STANDARD_ZIELROLLE}
        liste = [{"schluessel": m.group(2).strip(), "wert": m.group(3).strip()}
                 for _, m in _felder(ziel) if _kf(m.group(2)) in standard]
        vorhanden = {_kf(e["schluessel"]) for e in liste}
        liste += [{"schluessel": k, "wert": ""} for k in STANDARD_ZIELROLLE if _kf(k) not in vorhanden]
        daten["zielrolle"] = liste

    daten["unveraendert"] = [a.ueberschrift for a in dok.abschnitte[1:] if id(a) not in behandelt]
    return daten


def _ohne_klammerzusatz(anschrift: str) -> str:
    """Wie `user_profile._standort_ohne_klammerzusatz`: ein Zusatz in Klammern am Ende (etwa
    „(Rhein-Main)“) gehört nicht zur Anschrift."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", anschrift or "").strip()


def _hinweise(anschrift: str, email: str) -> list[str]:
    hinweise = []
    ort = _ohne_klammerzusatz(anschrift)
    if ort and ("," not in ort or not re.search(r"(?<!\d)\d{4,5}(?!\d)", ort)):
        hinweise.append(tx("Die Ortszeile Ihrer Anschreiben entsteht aus ‚Straße Nr, PLZ Ort‘."))
    if (email or "").strip() and "@" not in email:
        hinweise.append(tx("Die E-Mail-Adresse enthält kein ‚@‘. Bitte prüfen Sie die Schreibweise."))
    return hinweise


def hinweise_fuer(daten: dict) -> list[str]:
    """Nicht blockierende Hinweise zu den Werten einer Leseantwort (`lesen_aus_text`)."""
    ident = daten.get("identitaet") or {}
    return _hinweise(ident.get("anschrift", ""), ident.get("email", ""))


# ── Prüfen und Normalisieren (Eingabe der Maske) ─────────────────────────────────────────────────
def _format_fehler(label: str) -> ValueError:
    return ValueError(tx("Die Angabe zu ‚{label}‘ hat ein unerwartetes Format. Bitte laden Sie die Karte "
                         "neu und versuchen Sie es noch einmal.", label=uebersetzt(label)))


def _einzeilig(label: str, wert, pflicht: bool = False) -> Optional[str]:
    """`None` bleibt `None` (= nicht übergeben, Datei bleibt unverändert); sonst getrimmter Text."""
    if wert is None:
        if pflicht:
            raise ValueError(tx("Bitte tragen Sie Ihren Namen ein. Er erscheint im Briefkopf Ihrer "
                                "Anschreiben und in den Dateinamen."))
        return None
    if not isinstance(wert, str):
        raise _format_fehler(label)
    if any(c in wert for c in _ZEILENTRENNER):
        raise ValueError(tx("Das Feld ‚{label}‘ darf nur eine Zeile enthalten. Bitte entfernen Sie den "
                            "Zeilenumbruch.", label=uebersetzt(label)))
    wert = wert.strip()
    if pflicht and not wert:
        raise ValueError(tx("Bitte tragen Sie Ihren Namen ein. Er erscheint im Briefkopf Ihrer "
                            "Anschreiben und in den Dateinamen."))
    return wert


def _laenge_pruefen(label: str, wert: str, grenze: int) -> None:
    if len(wert) > grenze:
        raise ValueError(tx("Das Feld ‚{label}‘ ist zu lang. Erlaubt sind höchstens {grenze} Zeichen, "
                            "Ihre Eingabe hat {laenge}.", label=uebersetzt(label), grenze=grenze,
                            laenge=len(wert)))


def _freitext(label: str, wert) -> Optional[str]:
    """Freitext: Zeilenenden vereinheitlichen, Leerzeilen an Anfang und Ende entfernen. Keine Zeile darf
    mit `## ` beginnen (sonst entstünde ein neuer Abschnitt in der Datei)."""
    if wert is None:
        return None
    if not isinstance(wert, str):
        raise _format_fehler(label)
    zeilen = wert.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while zeilen and not zeilen[0].strip():
        zeilen.pop(0)
    while zeilen and not zeilen[-1].strip():
        zeilen.pop()
    for z in zeilen:
        if z.startswith("## "):
            raise ValueError(tx("Im Feld ‚{label}‘ darf keine Zeile mit ‚## ‘ beginnen, denn damit beginnt in "
                                "der Profil-Datei ein neuer Abschnitt. Bitte ändern Sie den Zeilenanfang.",
                                label=uebersetzt(label)))
    return "\n".join(zeilen)


def _liste(label: str, eintraege) -> Optional[list[tuple[str, str]]]:
    """`weitere` bzw. `zielrolle`: Liste aus `{schluessel, wert}` → [(Schlüssel, Wert)]."""
    if eintraege is None:
        return None
    if not isinstance(eintraege, list):
        raise _format_fehler(label)
    ergebnis = []
    for e in eintraege:
        if not isinstance(e, dict) or not isinstance(e.get("schluessel"), str) or not e["schluessel"].strip():
            raise _format_fehler(label)
        schluessel = e["schluessel"].strip()
        wert = _einzeilig(schluessel, e.get("wert"))
        if wert is None:
            raise _format_fehler(schluessel)
        ergebnis.append((schluessel, wert))
    return ergebnis


def _normalisieren(daten) -> dict:
    """Prüft die Eingabe der Maske und liefert sie getrimmt. `None` heißt „nicht übergeben“ und lässt
    die Datei an dieser Stelle unberührt; nur der Name ist Pflicht."""
    if not isinstance(daten, dict):
        raise ValueError(tx("Die Angaben haben ein unerwartetes Format. Bitte laden Sie die Karte neu und "
                            "versuchen Sie es noch einmal."))
    ident = daten.get("identitaet")
    if ident is None:
        ident = {}
    if not isinstance(ident, dict):
        raise _format_fehler("Identität")
    n = {"name": _einzeilig(_LABEL["name"], ident.get("name"), pflicht=True)}
    for feld in ("positionierung", "anschrift", "email", "telefon", "linkedin", "aktuell"):
        n[feld] = _einzeilig(_LABEL[feld], ident.get(feld))
    n["weitere"] = _liste("Weitere Angaben", ident.get("weitere"))
    n["zielrolle"] = _liste("Zielrolle", daten.get("zielrolle"))
    for feld in ("kurzprofil", "rahmenbedingungen", "skill_gaps"):
        n[feld] = _freitext(_LABEL[feld], daten.get(feld))
    return n


# ── Anwenden (Änderungen in den Text einarbeiten) ────────────────────────────────────────────────
def _wert_setzen(zeile: _Zeile, m: re.Match, wert: str) -> None:
    """Ersetzt NUR den Wert; Einrückung, Aufzählungszeichen, Schlüssel und der Abstand nach dem
    Doppelpunkt bleiben."""
    praefix = zeile.inhalt[:m.start(3)]
    if not praefix.endswith((" ", "\t")):
        praefix += " "
    zeile.inhalt = (praefix + wert) if wert else praefix.rstrip()


def _feld_anhaengen(a: Abschnitt, schluessel: str, wert: str, eol: str) -> None:
    """Neue Feldzeile hinter der letzten Feldzeile des Abschnitts (ohne Feldzeile: hinter der
    Überschrift)."""
    letzte = 0
    for i, _ in _felder(a):
        letzte = i
    a.zeilen.insert(letzte + 1, _Zeile(f"- **{schluessel}:** {wert}", eol))


def _unbekanntes_feld(schluessel: str) -> ValueError:
    return ValueError(tx("Das Feld ‚{schluessel}‘ gibt es in Ihrer Profil-Datei nicht und kann hier nicht "
                         "neu angelegt werden. Ergänzen Sie es bei Bedarf von Hand in der Datei "
                         "config/profil.md.", schluessel=schluessel))


def _liste_anwenden(a: Abschnitt, eintraege: list[tuple[str, str]], standard: dict[str, str],
                    ausgenommen: frozenset = frozenset()) -> list[tuple[str, str]]:
    """Wirkt `eintraege` auf die Feldzeilen von `a`: Der n-te Eintrag eines Schlüssels gehört zum n-ten
    Vorkommen dieses Schlüssels (ohne Rücksicht auf Groß-/Kleinschreibung). Ein geänderter Wert ersetzt
    nur den Wert der Zeile; nicht genannte Zeilen bleiben stehen. Einträge, zu denen es keine Zeile gibt,
    sind erlaubt, wenn der Schlüssel zu `standard` gehört (dann entsteht eine neue Zeile, bei leerem
    Wert keine); sonst `ValueError`. Gibt die neuen Zeilen als (Schlüssel, Wert) zurück."""
    warteschlangen: dict[str, deque] = {}
    for idx, (schluessel, _) in enumerate(eintraege):
        warteschlangen.setdefault(_kf(schluessel), deque()).append(idx)
    verbraucht: set[int] = set()
    for i, m in _felder(a):
        if i in ausgenommen:
            continue
        q = warteschlangen.get(_kf(m.group(2)))
        if q:
            idx = q.popleft()
            verbraucht.add(idx)
            schluessel, wert = eintraege[idx]
            if m.group(3).strip() != wert:
                _laenge_pruefen(schluessel, wert, MAX_EINZEILIG)
                _wert_setzen(a.zeilen[i], m, wert)
    neu = []
    for idx, (schluessel, wert) in enumerate(eintraege):
        if idx in verbraucht:
            continue
        if _kf(schluessel) not in standard:
            raise _unbekanntes_feld(schluessel)
        if wert:
            _laenge_pruefen(schluessel, wert, MAX_EINZEILIG)
            neu.append((standard[_kf(schluessel)], wert))
    return neu


def _identitaet_anwenden(a: Abschnitt, n: dict, eol: str) -> None:
    zuordnung, _ = _ident_zuordnung(a)

    werte: dict[str, Optional[str]] = {f: n.get(f) for f in ("name", "positionierung", "anschrift",
                                                              "linkedin", "aktuell")}
    werte["kontakt"] = None
    if n["email"] is not None or n["telefon"] is not None:
        alt = zuordnung.get("kontakt")
        alt_email, alt_telefon = kontakt_teilen(alt[1].group(3)) if alt else ("", "")
        email = alt_email if n["email"] is None else n["email"]
        telefon = alt_telefon if n["telefon"] is None else n["telefon"]
        if (email, telefon) != (alt_email, alt_telefon):   # sonst bleibt die Zeile wie sie ist
            werte["kontakt"] = kontakt_zusammensetzen(email, telefon)

    loeschen: set[int] = set()
    neu: list[tuple[str, str]] = []
    for feld in _IDENT_REIHE:
        wert = werte.get(feld)
        if wert is None:
            continue
        schluessel = _IDENT_SCHLUESSEL[feld]
        if feld in zuordnung:
            i, m = zuordnung[feld]
            if m.group(3).strip() == wert:
                continue
            if not wert and schluessel in _ZEILE_ENTFAELLT_BEI_LEER:
                loeschen.add(i)
            else:
                _laenge_pruefen("E-Mail und Telefon" if feld == "kontakt" else _LABEL[feld], wert,
                                MAX_EINZEILIG)
                _wert_setzen(a.zeilen[i], m, wert)
        elif wert:
            _laenge_pruefen("E-Mail und Telefon" if feld == "kontakt" else _LABEL[feld], wert,
                            MAX_EINZEILIG)
            neu.append((schluessel, wert))

    if n["weitere"] is not None:
        # Schlüssel der Identität werden über die Maskenfelder gepflegt, nicht über `weitere`.
        _liste_anwenden(a, n["weitere"], standard={},
                        ausgenommen=frozenset(i for i, _ in zuordnung.values()))

    for i in sorted(loeschen, reverse=True):
        del a.zeilen[i]
    for schluessel, wert in neu:
        _feld_anhaengen(a, schluessel, wert, eol)


def _zielrolle_anwenden(a: Abschnitt, eintraege: list[tuple[str, str]], eol: str) -> None:
    standard = {_kf(k): k for k in STANDARD_ZIELROLLE}
    for schluessel, wert in _liste_anwenden(a, eintraege, standard):
        _feld_anhaengen(a, schluessel, wert, eol)


def _vergleichszeilen(text: str) -> list[str]:
    """Zeilen eines Freitexts für den Vergleich „unverändert?“: ein einzelnes `\\r` zählt wie ein
    Zeilenumbruch (so schickt es ein Textfeld zurück), Leerraum am Zeilenende zählt nicht."""
    if not text:
        return []
    return [z.rstrip() for z in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def _freitext_anwenden(a: Abschnitt, text: str, label: str, eol: str) -> None:
    """Ersetzt den Kern des Rumpfes (ohne Leerzeilen an Anfang und Ende). Die Leerzeilen davor und
    danach bleiben, ebenso der Abschnitt bei unverändertem Text (Vergleich ohne Leerraum am
    Zeilenende)."""
    von, bis = _freitext_teile(a)
    alt = a.zeilen[von:bis]
    neu_inhalt = text.split("\n") if text else []
    if _vergleichszeilen("\n".join(z.inhalt for z in alt)) == _vergleichszeilen(text):
        return
    _laenge_pruefen(label, text, MAX_FREITEXT)
    neu = [_Zeile(inhalt, alt[j].ende if j < len(alt) else eol) for j, inhalt in enumerate(neu_inhalt)]
    a.zeilen[von:bis] = neu


def _vorlage(name: str) -> str:
    """Gerüst für eine fehlende Datei (Aufbau wie `app.beispieldaten._profil_md_text()`): die
    Abschnitte stehen leer da, die Werte der Maske werden anschließend wie bei einer vorhandenen Datei
    eingefügt."""
    return "\n".join([
        f"# Kandidatenprofil: {name}", "",
        "## Identität", "",
        "## Kurzprofil", "",
        "## Zielrolle", "",
        "## Harte Rahmenbedingungen", "",
        "## Sprachen / CV-Fassungen",
        "- **Deutsch:** `data/cv_basis/base_de.docx`",
        "- **Englisch:** `data/cv_basis/base_en.docx`", "",
        "## Bekannte Skill-Gaps / Red Flags", "",
        "## Empirie aus dem Bewerbungsverlauf",
        "- (pflegt das BMS selbst, bitte die Überschrift unverändert lassen)", "",
    ])


_TITEL = "# Kandidatenprofil: "


def _name_im_abschnitt(a: Abschnitt) -> str:
    zuordnung, _ = _ident_zuordnung(a)
    treffer = zuordnung.get("name")
    return treffer[1].group(3).strip() if treffer else ""


def _titel_nachziehen(dok: Dokument, alt: str, neu: Optional[str]) -> None:
    """P2-69 (Abnahme): Die Titelzeile der Vorlage trägt den Namen (`# Kandidatenprofil: <Name>`).
    Ändert jemand den Namen in der Maske, zieht genau diese Zeile im Dateikopf mit, sonst stünde
    über dem neuen Namen noch der alte (etwa der der Beispieldaten). Nur wenn die Zeile exakt dem
    Muster mit dem BISHERIGEN Namen entspricht; ein von Hand anders geschriebener Titel bleibt."""
    if not alt or not neu or neu == alt:
        return
    for zeile in dok.abschnitte[0].zeilen:
        if zeile.inhalt.rstrip() == _TITEL + alt:
            zeile.inhalt = _TITEL + neu
            return


def anwenden(text: Optional[str], daten: dict) -> str:
    """Arbeitet die Maskenwerte in den Dateitext ein und liefert den neuen Text. `text=None` (Datei
    fehlt) baut zuerst die Vorlage. Wirft `ValueError` (Kundentext) bei ungültigen Eingaben; der
    Eingabetext wird nie verändert."""
    n = _normalisieren(daten)
    if text is None:
        text = _vorlage(n["name"])
    dok = zerlegen(text)
    eol = dok.eol

    ident = dok.finde(_IDENTITAET) or dok.anlegen("Identität")
    alter_name = _name_im_abschnitt(ident)
    _identitaet_anwenden(ident, n, eol)
    _titel_nachziehen(dok, alter_name, n["name"])

    def freitext(schluessel: str, prefix: str, titel: str) -> None:
        wert = n[schluessel]
        if wert is None:
            return
        a = dok.finde(prefix)
        if a is None:
            if not wert:
                return                       # kein Inhalt: keinen Abschnitt anlegen
            a = dok.anlegen(titel)
        _freitext_anwenden(a, wert, _LABEL[schluessel], eol)

    freitext("kurzprofil", _KURZPROFIL, "Kurzprofil")

    if n["zielrolle"] is not None:
        a = dok.finde(_ZIELROLLE)
        if a is None and any(wert for _, wert in n["zielrolle"]):
            a = dok.anlegen("Zielrolle")
        if a is not None:
            _zielrolle_anwenden(a, n["zielrolle"], eol)

    freitext("rahmenbedingungen", _RAHMEN, "Harte Rahmenbedingungen")
    freitext("skill_gaps", _GAPS, "Bekannte Skill-Gaps / Red Flags")

    dok.enden_richten()
    return zusammensetzen(dok)


# ── Datei: Lesen, Papierkorb, atomares Schreiben ─────────────────────────────────────────────────
def _pfad():
    """Immer zur Laufzeit aus `user_profile` (Tests patchen genau diesen Pfad)."""
    return user_profile._PROFIL_MD


def _bytes_lesen(pfad) -> Optional[bytes]:
    try:
        return pfad.read_bytes()
    except FileNotFoundError:
        return None


def _dekodieren(inhalt: bytes) -> str:
    try:
        return inhalt.decode("utf-8")
    except UnicodeDecodeError:
        raise DateiNichtLesbar(tx("Ihre Profil-Datei config/profil.md ist nicht als UTF-8 gespeichert und "
                                  "kann deshalb hier nicht bearbeitet werden. Bitte speichern Sie die Datei "
                                  "im Texteditor als UTF-8.")) from None


def lesen() -> dict:
    """Maskenwerte aus `config/profil.md` plus `vorhanden`, `stand`, `unveraendert`, `hinweise`
    (Antwortform von `GET /api/profil/identitaet`)."""
    roh = _bytes_lesen(_pfad())
    daten = lesen_aus_text(None if roh is None else _dekodieren(roh))
    unveraendert = daten.pop("unveraendert")
    return {"vorhanden": roh is not None, "stand": stand_von(roh), **daten,
            "unveraendert": [uebersetzt(u) for u in unveraendert], "hinweise": hinweise_fuer(daten)}


def _papierkorb_ordner():
    """`<Datenordner>/papierkorb`, erst beim Aufruf aufgelöst (Tests lenken `app.db.DATA_DIR` um)."""
    from app import db
    return db.DATA_DIR / "papierkorb"


def _papierkorb_name(ordner) -> str:
    """`JJJJMMTT_profil.md` (Muster `dated_filename`), bei Kollision `_2`, `_3` … (Muster
    `main._freier_name`)."""
    from app.naming import dated_filename
    name = dated_filename("profil", "md")
    if not (ordner / name).exists():
        return name
    stem, _, ext = name.rpartition(".")
    n = 2
    while (ordner / f"{stem}_{n}.{ext}").exists():
        n += 1
    return f"{stem}_{n}.{ext}"


def _in_papierkorb_kopieren(pfad) -> str:
    """Kopie (nicht Verschieben) der alten Datei in den Papierkorb. Rückgabe: Pfad relativ zum
    Datenordner mit Präfix `data/` wie bei den Löschendpunkten. Scheitert die Kopie, wirft die
    Funktion `OSError`, und die Datei wird NICHT überschrieben."""
    ordner = _papierkorb_ordner()
    ordner.mkdir(parents=True, exist_ok=True)
    name = _papierkorb_name(ordner)
    shutil.copy2(str(pfad), str(ordner / name))
    return f"data/papierkorb/{name}"


def _atomar_schreiben(pfad, inhalt: bytes) -> None:
    """Temp-Datei im selben Ordner, dann `os.replace`: Bei einem Fehler bleibt die alte Datei stehen
    und die Temp-Datei wird entfernt. Die Zugriffsrechte der alten Datei bleiben erhalten."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(pfad.parent), prefix=".profil_", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(inhalt)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(tmp, stat.S_IMODE(pfad.stat().st_mode))
        except FileNotFoundError:
            os.chmod(tmp, 0o644)
        os.replace(tmp, str(pfad))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def schreiben(daten: dict, stand: str) -> dict:
    """Schreibt die Maskenwerte in `config/profil.md`.

    Ablauf unter einer Sperre (zwei Speichern gleichzeitig laufen nacheinander): Dateibytes lesen →
    `stand` vergleichen (`StandVeraltet`) → neuen Text berechnen (`ValueError` bei ungültiger Eingabe)
    → bei geändertem Inhalt Kopie der alten Datei in den Papierkorb → atomar ersetzen. Ist das Ergebnis
    byte-gleich zur Datei, wird nichts geschrieben und nichts in den Papierkorb gelegt.

    Rückgabe: `{"geschrieben": bool, "papierkorb": Pfad der Sicherungskopie oder None,
    "hinweise": [...]}` (die Hinweise gelten für die EINGEGEBENEN Werte, etwa eine E-Mail ohne `@`,
    die beim erneuten Lesen als Telefon erscheint)."""
    pfad = _pfad()
    with _SPERRE:
        roh = _bytes_lesen(pfad)
        if stand_von(roh) != stand:
            raise StandVeraltet(uebersetzt(STAND_VERALTET_TEXT))
        neu = anwenden(None if roh is None else _dekodieren(roh), daten).encode("utf-8")
        n = _normalisieren(daten)
        hinweise = _hinweise(n["anschrift"] or "", n["email"] or "")
        if roh is not None and neu == roh:
            return {"geschrieben": False, "papierkorb": None, "hinweise": hinweise}
        papierkorb = _in_papierkorb_kopieren(pfad) if roh is not None else None
        _atomar_schreiben(pfad, neu)
    return {"geschrieben": True, "papierkorb": papierkorb, "hinweise": hinweise}
