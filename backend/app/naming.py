"""Zentrale Datei-Namenskonvention für generierte/geteilte Dokumente.

Format: JJJJMMTT_Name.ext  (z. B. 20260709_Job_Search_Tracker_Max_Mustermann.xlsx)
Datum voran → chronologisch sortierbar; Unterstriche statt Leerzeichen.

P2-63 (01.10.2026): Dateinamen kürzer. Datum `JJJJMMTT` statt `JJJJ_MM_TT`, kürzere Typ-Wörter
(Anzeige, Auswertung, Beirat), Firma auf 25 Zeichen ohne Zusätze/Rechtsform (`_firma_kurz`),
Rollen auf 30 (Berichte, Transkript) bzw. 35 Zeichen (CV, Anschreiben). LESER müssen beide
Datumsformate verstehen (Bestand vor der Umbenennung): dafür `datum_aus_praefix`/`DATUM_RE`.
"""
import datetime
import re
from typing import Optional


def dated_filename(name: str, ext: str, when: Optional[datetime.date] = None) -> str:
    d = when or datetime.date.today()
    safe = re.sub(r"\s+", "_", str(name).strip()).strip("_")
    return f"{d:%Y%m%d}_{safe}.{ext.lstrip('.')}"


# P2-63: Leser für BEIDE Datumsformate (neu `JJJJMMTT`, Bestand `JJJJ_MM_TT`). Präfix-Variante
# (Dateiname beginnt mit dem Datum, gefolgt von `_`) und Such-Variante (Datum irgendwo im Namen).
DATUM_PRAEFIX_RE = re.compile(r"^(?:(\d{4})_(\d{2})_(\d{2})|(\d{4})(\d{2})(\d{2}))_")
DATUM_RE = re.compile(r"(\d{4})_(\d{2})_(\d{2})|(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)")


def _datum_aus_match(m) -> Optional[datetime.date]:
    if not m:
        return None
    g = m.groups()
    teile = g[:3] if g[0] else g[3:]
    try:
        return datetime.date(int(teile[0]), int(teile[1]), int(teile[2]))
    except ValueError:
        return None


def datum_aus_praefix(name: str) -> Optional[datetime.date]:
    """Datum aus dem Namenspräfix (`20261001_…` ODER `2026_10_01_…`), sonst None (auch bei
    unmöglichem Datum wie `20261399_`)."""
    return _datum_aus_match(DATUM_PRAEFIX_RE.match(str(name)))


def datum_aus_name(name: str) -> Optional[datetime.date]:
    """Erstes Datum irgendwo im Namen, beide Formate (für Namen mit Typ-Präfix wie Transkript)."""
    return _datum_aus_match(DATUM_RE.search(str(name)))


# --- CV-Sonderkonvention -----------------------------------------------------
# BEWUSSTE ABWEICHUNG von dated_filename: CV-Dateien tragen den Empfänger-sichtbaren
# Namen CV_<Name>_<Firma>_<Position>_DE|_EN statt eines Datumspräfixes. Explizite
# Vorgabe des Nutzers (Empfänger/ATS sehen den Dateinamen des Anhangs).
# Notwendige Ergänzungen (vom Nutzer später änderbar):
#   - Sprach-Suffix IMMER gesetzt (_DE oder _EN, Default DE wenn keine Sprache übergeben),
#     sonst überschreiben sich DE- und EN-Version.
#   - Kollisions-Nummerierung (_2, _3 …) übernimmt der Aufrufer (pipeline.cv_export).

_TRANSLIT = {
    "ä": "ae", "ö": "oe", "ü": "ue",
    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
    "ß": "ss",
}

# P2-36 (11.09.2026): Regex + Kommentarblock (Historie P3-5) nach app/normalize.py verschoben —
# ein kanonischer Ort, wie slug_parts (ingest.py braucht denselben Gender-Zusatz-Regex jetzt
# ebenfalls, s. Spec tasks/spec_p2-36_neuausschreibung_dublette.md §2.2). Re-Export unter dem
# alten Namen, damit die fünf Verwendungen unten wörtlich bleiben.
from app.normalize import GENDER_RE as _GENDER_RE


def _translit(s: str) -> str:
    for k, v in _TRANSLIT.items():
        s = s.replace(k, v)
    return s


def _sanitize_part(part: str) -> str:
    """Umlaute → ae/oe/…; Leerzeichen und '/' → '_'; alles außer [A-Za-z0-9_-]
    entfernen; Mehrfach-'_' zusammenfassen."""
    part = _translit(str(part))
    part = re.sub(r"[\s/]+", "_", part.strip())
    part = re.sub(r"[^A-Za-z0-9_-]", "", part)
    part = re.sub(r"_+", "_", part).strip("_-")
    return part


def _truncate_words(s: str, limit: int) -> str:
    """Auf 'limit' Zeichen kürzen, dabei an der letzten '_'-Wortgrenze abschneiden."""
    if len(s) <= limit:
        return s
    cut = s[:limit]
    if s[limit] in "_-":
        # P2-63: Der Schnitt fällt genau auf eine Wortgrenze, das letzte Wort ist vollständig.
        return cut.strip("_-")
    if "_" in cut:
        cut = cut.rsplit("_", 1)[0]
    return cut.strip("_-") or s[:limit]


def _camel_name(name: str) -> str:
    """Nutzer-Name (aus `user_name()`) → CamelCase ohne Trennzeichen, Umlaute-sicher
    (`_translit`) — für den CV-/Anschreiben-Dateinamen. "Max Mustermann" → "MaxMustermann"
    (Bestandsverhalten unverändert, da bereits großgeschrieben); "Jörg Müller" → "JoergMueller".
    Keine erzwungene Groß-/Kleinschreibung — nur [A-Za-z0-9] bleibt übrig, der Rest
    (Leerzeichen, Bindestrich, …) wird entfernt."""
    return re.sub(r"[^A-Za-z0-9]", "", _translit(str(name or "")))


# --- P2-63: Kurzformen für Firma und Rolle -------------------------------------
# Abschnitts-Trenner in Firmennamen: alles ab dem ersten Treffer ist Zusatz (Klammer, Klient,
# Aufzählung, Standort). Bindestrich OHNE Leerzeichen ("Muster-Beratung") bleibt Teil des Namens.
_FIRMA_SCHNITT_RE = re.compile(r"[(:,;|]|\s[-\u2013\u2014]\s")
# Rechtsformen am Ende (token-weise, ohne Groß-/Kleinschreibung und ohne Schlusspunkte verglichen).
# "GmbH & Co. KG" fällt über die Einzeltokens KG, Co, &, GmbH.
_RECHTSFORMEN = {
    "gmbh", "mbh", "ag", "se", "kg", "kgaa", "ohg", "gbr", "ug", "e.v", "inc", "ltd", "llc", "llp",
    "plc", "s.a", "sa", "sas", "b.v", "bv", "n.v", "nv", "co", "&",
}
_REGION_SCHNITT_RE = re.compile(r"\s[-\u2013\u2014]\s")
FIRMA_MAX = 25
ROLLE_MAX_BERICHT = 30
ROLLE_MAX_DOKUMENT = 35


def _firma_kurz(company: str) -> str:
    """P2-63: Firmenname für den Dateinamen. Zusätze ab `(`, `:`, `,`, `;`, `|` oder ` - ` weg,
    Rechtsformen am Ende weg, bereinigen (`_sanitize_part`), auf 25 Zeichen an der Wortgrenze
    kürzen. Leer → 'Firma'. Bleibt nach dem Entfernen der Rechtsform nichts übrig, gilt der
    Name vor der Entfernung (eine Firma, die nur 'AG' heißt, bleibt benennbar)."""
    roh = _FIRMA_SCHNITT_RE.split(str(company or ""), maxsplit=1)[0].strip()
    teile = roh.split()
    while len(teile) > 1 and teile[-1].lower().rstrip(".,") in _RECHTSFORMEN:
        teile.pop()
    ohne = " ".join(teile).strip()
    firma = _truncate_words(_sanitize_part(ohne), FIRMA_MAX)
    return firma or "Firma"


def _rolle_kurz(position: Optional[str], limit: int) -> str:
    """P2-63: Rolle für den Dateinamen. Gender-Zusätze raus, Regionszusatz nach ` - ` (z. B.
    ' - DACH') abgeschnitten, bereinigt, auf `limit` Zeichen an der Wortgrenze gekürzt.
    Leer → '' (der Aufrufer setzt seinen Rückfall)."""
    pos = _GENDER_RE.sub(" ", str(position or ""))
    teile = _REGION_SCHNITT_RE.split(pos, maxsplit=1)
    # Abnahme P2-63: nur einen REGIONSZUSATZ abschneiden („ - DACH“, „ - Remote Germany“), keinen
    # inhaltlichen Teil des Titels („Head of IT - Infrastructure“ bliebe sonst „Head_of_IT“).
    if len(teile) == 2 and _ist_regionszusatz(teile[1]):
        pos = teile[0]
    return _truncate_words(_sanitize_part(pos), limit)


_REGIONSWOERTER = {
    "dach", "emea", "apac", "cee", "nordics", "benelux", "europe", "europa", "eu", "global",
    "international", "remote", "hybrid", "germany", "deutschland", "austria", "oesterreich",
    "österreich", "switzerland", "schweiz", "nord", "sued", "süd", "ost", "west", "mitte",
    "north", "south", "east", "central", "region", "and", "und", "&", "/",
}


def _ist_regionszusatz(rest: str) -> bool:
    """Wahr, wenn der Teil nach „ - “ nur aus Regionswörtern besteht (Groß-/Kleinschreibung egal)."""
    woerter = [w for w in re.split(r"[\s,/&]+", str(rest).strip().lower()) if w]
    return bool(woerter) and all(w.strip("().") in _REGIONSWOERTER for w in woerter)


def cv_filename(company: str, position: str, language: Optional[str] = None) -> str:
    """CV-Konvention des Nutzers: CV_<Name>_<Firma>_<Position>_DE|_EN (ohne Extension).
    Sprach-Suffix ist immer gesetzt (Default DE), damit sich DE/EN nie überschreiben.
    Bewusste Abweichung von dated_filename — Empfänger sehen diesen Namen."""
    from pipeline.user_profile import user_name
    firma = _firma_kurz(company)
    pos = _rolle_kurz(position, ROLLE_MAX_DOKUMENT) or "Position"
    sprache = (language or "DE").upper()
    return f"CV_{_camel_name(user_name())}_{firma}_{pos}_{sprache}"


def cover_letter_filename(company: str, position: str, language: Optional[str] = None) -> str:
    """Anschreiben-Konvention des Nutzers: CoverLetter_<Name>_<Firma>_<Rolle>_DE|_EN (ohne
    Extension). Sprach-Suffix ist immer gesetzt (Default DE) — exakt wie cv_filename(), Korrektur
    vom 11.07.2026 (vorher: Suffix nur bei Englisch). Gleiche Sanitisierung wie
    cv_filename (interne Helfer wiederverwendet, nicht dupliziert)."""
    from pipeline.user_profile import user_name
    firma = _firma_kurz(company)
    rolle = _rolle_kurz(position, ROLLE_MAX_DOKUMENT) or "Rolle"
    sprache = (language or "DE").upper()
    return f"CoverLetter_{_camel_name(user_name())}_{firma}_{rolle}_{sprache}"


def cv_filename_alt(company: str, position: str, language: Optional[str] = None) -> str:
    """P2-63: der Name, den `cv_filename` VOR der Kürzung gebildet hätte (volle Firma, Rolle auf 50).
    Nur für die Re-Export-Weiche in `pipeline.cv_export`: Eine Datei der Stelle, die noch den alten
    Namen trägt, gilt als eigene und wird beim erneuten Export auf den neuen Namen umgestellt,
    statt als Waise liegen zu bleiben."""
    from pipeline.user_profile import user_name
    firma = _sanitize_part(company or "") or "Firma"
    pos = _GENDER_RE.sub(" ", str(position or ""))
    pos = _truncate_words(_sanitize_part(pos), 50) or "Position"
    return f"CV_{_camel_name(user_name())}_{firma}_{pos}_{(language or 'DE').upper()}"


def cover_letter_filename_alt(company: str, position: str, language: Optional[str] = None) -> str:
    """P2-63: Anschreiben-Name vor der Kürzung (s. `cv_filename_alt`)."""
    from pipeline.user_profile import user_name
    firma = _sanitize_part(company or "") or "Firma"
    rolle = _GENDER_RE.sub(" ", str(position or ""))
    rolle = _truncate_words(_sanitize_part(rolle), 50) or "Rolle"
    return f"CoverLetter_{_camel_name(user_name())}_{firma}_{rolle}_{(language or 'DE').upper()}"


# --- Transkript-/Debrief-Sonderkonvention ------------------------------------
# BEWUSSTE ABWEICHUNG von dated_filename UND von den früheren Ad-hoc-Mustern
# ("Transkript_Job42_R2_Beispiel", "Debrief_Job57_T3") — die internen IDs (Job-/Transkript-Id)
# sagen dem Menschen nichts. Vorgabe des Nutzers (11.07.2026): Gesprächsdatum, Teilnehmer, Firma,
# Position müssen im Dateinamen erkennbar sein. Datum ist das GESPRÄCHSDATUM (recorded_at),
# NICHT das Erstellungsdatum der Datei — ein Transkript, das erst Tage später eingefügt wird,
# soll trotzdem am Gesprächstag einsortiert werden.

def _konversationsdatum(recorded_at) -> str:
    """recorded_at ist meist 'YYYY-MM-DD' (aus <input type=date>). Robust parsen, sonst heute."""
    s = str(recorded_at or "").strip()[:10]
    try:
        d = datetime.date.fromisoformat(s)
    except ValueError:
        d = datetime.date.today()
    return f"{d:%Y%m%d}"


def transcript_filename(kind: str, recorded_at, kontakt: Optional[str], company: str,
                        position: str, runde: Optional[int] = None) -> str:
    """Schema: <Kind>_<JJJJMMTT Gespräch>_<Teilnehmer>_<Firma>_<Position>[_R<Runde>]
    (ohne Extension). kind: 'Transkript' oder 'Debrief' — Debrief einer Runde bekommt so
    denselben Namensstamm wie sein Quell-Transkript, nur mit anderem Präfix (leicht paarbar).
    Fehlende Angaben fallen auf 'Unbekannt'/'Firma'/'Position' zurück statt die Datei
    unbenennbar zu machen."""
    datum = _konversationsdatum(recorded_at)
    teilnehmer = _sanitize_part(kontakt or "") or "Unbekannt"
    firma = _firma_kurz(company)
    pos = _rolle_kurz(position, ROLLE_MAX_BERICHT) or "Position"
    praefix = "Debrief" if str(kind).lower().startswith("debrief") else "Transkript"
    runde_teil = f"_R{int(runde)}" if runde else ""
    return f"{praefix}_{datum}_{teilnehmer}_{firma}_{pos}{runde_teil}"


# --- Stellenausschreibungs-Snapshot (Phase 18) -------------------------------
# Datum ist bewusst das ABRUFDATUM (heute) — der Snapshot konserviert die Anzeige zu einem
# Zeitpunkt (Stellenanzeigen verschwinden, s. Phase 14). Gleiche Sanitisierung wie die
# anderen Sonderkonventionen (interne Helfer wiederverwendet, nicht dupliziert).

def posting_filename(company: str, position: str) -> str:
    """P2-63: Schema wie alle Berichte, `<JJJJMMTT Abruf>_Anzeige_<Firma>_<Rolle>` (ohne Extension;
    früher `Stellenausschreibung_<Datum>_…`). Nur noch Altaufrufer, der Name kommt aus
    `report_filename`. Fallbacks 'Firma' bei fehlender Angabe; fehlt die Rolle, entfällt sie."""
    return report_filename("Anzeige", company, position)


# --- Company-Fit-Dashboard (Phase 24 E) --------------------------------------
# BEWUSSTE ABWEICHUNG von dated_filename UND von den früheren rohen Slugs (z. B.
# "beispiel-gmbh.html"): sprechender Name statt Slug. OHNE Datum — es gibt genau EIN
# Dashboard je Firma, ein Re-Run von firma-pruefen überschreibt bewusst den alten Stand
# (unverändertes Verhalten, nur mit neuem Namen). Gleiche Sanitisierung wie die anderen
# Sonderkonventionen (interne Helfer wiederverwendet, nicht dupliziert).

def company_fit_filename(company: str) -> str:
    """Schema: CompanyFit_<Firma> (ohne Extension). Fallback 'Firma' bei fehlender Angabe."""
    return f"CompanyFit_{_firma_kurz(company)}"


# --- Einheitlicher Report-Namens-Helfer (Phase 30) ---------------------------
# EIN Helfer für ALLE neu erzeugten Report-HTML-Dateien (Company-Fit, Match, ATS-Scan, Briefing,
# Debrief, Transkript(-Report), Stellenausschreibung, Analyse) — löst den Wildwuchs der bisherigen
# Ad-hoc-Slugs ab (z. B. "beispiel_match.html" vs. "Beispiel_SeniorManagerVertrieb_match.html").
# Schema: JJJJ_MM_TT_<Typ>_<Firma>[_<Rolle>][_Rn]. Gleiche Sanitisierung wie die anderen
# Sonderkonventionen (interne Helfer wiederverwendet, nicht dupliziert). NUR für neue Aufrufer
# (Stufe B/C) — `posting_filename`/`transcript_filename`/`company_fit_filename` bleiben für
# Alt-Aufrufer/Migration (Phase 31) bestehen, werden aber von neuem Code nicht mehr genutzt.
#
# Veto-Punkt CompanyFit (Vorgabe des Nutzers, Spec Phase 30 Design-Entscheidung 4): bekommt IMMER ein
# Datum, aber NIE eine Rolle im Namen (firmenbezogen, gilt für alle Jobs der Firma) — jede
# Neu-Prüfung erzeugt bewusst eine NEUE, datierte Datei; `fit_analysis_path` zeigt auf die
# aktuellste, ältere bleiben als Historie liegen.

_REPORT_TYPES = {
    "CompanyFit", "Match", "ATSscan", "Briefing", "Debrief", "Transkript",
    "Auswertung", "Anzeige", "Analyse", "Beirat",
}
# P2-63: alte Typ-Wörter bleiben als EINGABE erlaubt (Skills/Altaufrufer) und ergeben den neuen Namen.
_TYP_ALT = {
    "Stellenausschreibung": "Anzeige",
    "TranskriptReport": "Auswertung",
    "BeiratsCheck": "Beirat",
}


def _report_date(when) -> str:
    """`when` ist meist ein datetime.date ODER ein ISO-Datumsstring (z. B. Transkript.recorded_at),
    manchmal None. Robust parsen, sonst heute (Erzeugungsdatum als Fallback) — analog
    `_konversationsdatum` oben, aber date-Objekte zusätzlich direkt akzeptiert."""
    if isinstance(when, datetime.date):
        return f"{when:%Y%m%d}"
    s = str(when or "").strip()[:10]
    try:
        d = datetime.date.fromisoformat(s)
    except ValueError:
        d = datetime.date.today()
    return f"{d:%Y%m%d}"


def report_filename(typ: str, company: str, position: Optional[str] = None,
                    when=None, runde: Optional[int] = None) -> str:
    """Schema: JJJJMMTT_<Typ>_<Firma>[_<Rolle>][_Rn] (ohne Extension).

    typ (verbindliches Enum, s. o.): CompanyFit, Match, ATSscan, Briefing, Debrief, Transkript,
    Auswertung, Anzeige, Analyse, Beirat. Die alten Wörter Stellenausschreibung, TranskriptReport
    und BeiratsCheck werden als Eingabe angenommen und auf Anzeige/Auswertung/Beirat abgebildet.
    when: Datum fürs Präfix — datetime.date ODER ISO-String ODER None (→ heute). Für
    TranskriptReport/Debrief ist das bewusst das GESPRÄCHSDATUM (recorded_at), nicht der
    Erzeugungszeitpunkt, damit spät nachgetragene Transkripte am Gesprächstag einsortiert werden.
    firma: `_firma_kurz` (25 Zeichen, ohne Zusätze/Rechtsform). position: entfällt bei
    typ='CompanyFit' (Veto-Punkt), sonst auf 30 Zeichen an der Wortgrenze gekürzt, Gender-Tags und
    Regionszusatz nach ' - ' entfernt. runde: hängt '_Rn' an, wenn gesetzt (>0).
    Fallbacks 'Firma' bei fehlender Firma — nie unbenennbar."""
    typ = _TYP_ALT.get(typ, typ)
    if typ not in _REPORT_TYPES:
        raise ValueError(f"Unbekannter Report-Typ {typ!r} — erlaubt: {sorted(_REPORT_TYPES)}")
    datum = _report_date(when)
    firma = _firma_kurz(company)
    teile = [datum, typ, firma]
    if position and typ != "CompanyFit":
        pos = _rolle_kurz(position, ROLLE_MAX_BERICHT)
        if pos:
            teile.append(pos)
    if runde:
        teile.append(f"R{int(runde)}")
    return "_".join(teile)


# --- Outreach-Tracker-Export (Phase 71A) --------------------------------------
# BEWUSSTE ABWEICHUNG von dated_filename (volles Datum): hier zählt nur das JAHR, kein Tag — der
# Tracker-Download spiegelt den AKTUELLEN Gesamtstand (kein Tages-Snapshot wie z. B.
# export_excel.py "Bewerbungs-Stand"), analog zur vom Nutzer gepflegten Drive-Vorlage
# (data/templates/). Ersetzt den früher hartkodierten Namen "Job_Search_Tracker_Max_Mustermann" —
# für das Profil des Nutzers (config/profil.md) und das Jahr 2026 ergibt sich exakt der Bestandsname
# (Regressionstest in test_naming.py).

def tracker_filename(name: str, ext: str, when: Optional[datetime.date] = None) -> str:
    """Schema: <JAHR>_Job_Search_Tracker_<Name_mit_Unterstrichen>.<ext>. `when` nur fürs Jahr
    (Default heute); `name` typischerweise `user_name()` — Leerzeichen → '_', sonst wie
    dated_filename sanitisiert (keine Umlaut-Transliteration nötig, `name` ist bereits ein
    Personenname aus dem Profil, keine Firmen-/Positionsangabe mit Sonderzeichen)."""
    d = when or datetime.date.today()
    safe = re.sub(r"\s+", "_", str(name).strip()).strip("_")
    return f"{d.year}_Job_Search_Tracker_{safe}.{ext.lstrip('.')}"
