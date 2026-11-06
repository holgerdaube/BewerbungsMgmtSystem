"""Normalization helpers — turn messy free-text tracker values into clean, filterable fields.

Every function keeps things conservative: when in doubt it returns a neutral bucket
rather than guessing, and callers always keep the original raw text alongside.
"""
import re
import unicodedata
from typing import Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit

# ── Situation ────────────────────────────────────────────────────────────────
# Priority reflects the user's strategy (Anleitung-Tab): Plan-A-core signals win over RUN.
_SITUATION_PRIORITY = ["CARVE-OUT", "POST-MERGER", "BUILD", "SCALE-UP", "RESTRUCT", "PE", "RUN"]


def norm_situation(raw) -> Tuple[Optional[str], Optional[str]]:
    """Return (normalized_code, raw). Picks the strongest build-signal in a combo like 'SCALE-UP / RESTRUCT'."""
    if raw is None:
        return None, None
    s = str(raw).strip()
    if not s or s.lower() in ("none", "unklar", "unbekannt", "unknown"):
        return "UNKLAR", s or None
    up = s.upper()
    for code in _SITUATION_PRIORITY:
        if code == "PE":
            if re.search(r"\bPE\b", up):
                return "PE", s
        elif code in up:
            return code, s
    if "UNKLAR" in up or "UNKNOWN" in up:
        return "UNKLAR", s
    return "UNKLAR", s


# ── Suchplan (Phase 51) ────────────────────────────────────────────────────────
def norm_plan(raw) -> Optional[str]:
    """'Plan B (Grenzfall)' -> 'B', ' plan a ' -> 'A', 'C' -> 'C', None/'' -> None.
    Deckt die in der Live-DB verschmutzten plan_ab-Schreibweisen ab (nur lesend genutzt,
    kein Massen-Update des Bestands)."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    up = s.upper()
    if up.startswith("PLAN "):
        up = up[5:].strip()
    return up[0] if up and up[0] in ("A", "B", "C") else None


# ── Seniority ────────────────────────────────────────────────────────────────
# Stufen von oben nach unten. Die Auswahl im Formular steht in frontend/src/senioritaet.ts,
# test_seniority.py hält beide gleich. Unterhalb von Teamlead angelehnt an die LinkedIn-Stufen
# (Internship, Entry level, Associate, Mid-Senior level) und die üblichen deutschen Karrierestufen.
SENIORITAETEN = ("C-Level", "VP", "Senior Director", "Director", "Head", "Senior Manager", "Manager", "Teamlead",
                 "Experte", "Erfahrener Mitarbeiter", "Angestellter", "Berufseinsteiger", "Trainee",
                 "Auszubildender", "Werkstudent", "Praktikant")

_C_LEVEL_RE = re.compile(r"\bC-LEVEL\b|\bC[A-Z]O\b|\bCHIEF\b|GESCHÄFTSFÜHR|\bVORSTAND|^EXECUTIVE( LEVEL)?$")
_HEAD_DE_RE = re.compile(r"BEREICHSLEIT|ABTEILUNGSLEIT")
_EXPERTE_RE = re.compile(r"\bEXPERT|SPEZIALIST|SPECIALIST|\bPRINCIPAL\b|\bLEAD\b|\bSTAFF\b")
_ERFAHREN_RE = re.compile(r"\bSENIOR\b|\bSR\b|ERFAHREN|MIT BERUFSERFAHRUNG")
_EINSTEIG_RE = re.compile(r"\bJUNIOR\b|\bJR\b|EINSTEIG|\bENTRY\b|ABSOLVENT|OHNE BERUFSERFAHRUNG")
_ANGESTELLT_RE = re.compile(r"ANGESTELLT|MITARBEITER|FACHKRAFT|SACHBEARBEIT|\bASSOCIATE\b|^PROFESSIONAL$")
_TRAINEE_RE = re.compile(r"\bTRAINEE\b|VOLONT")
_AZUBI_RE = re.compile(r"AUSZUBILD|\bAZUBI\b|AUSBILDUNG|APPRENTICE")
_WERKSTUDENT_RE = re.compile(r"WERKSTUDENT|WORKING STUDENT")
# Romanische Schreibweisen (nur eindeutige): Stagiaire, Stagista, Becario, Estagiário.
_PRAKTIKANT_RE = re.compile(r"PRAKTIK|\bINTERN(SHIP)?\b|\bSTAGIAIRE|\bSTAGISTA|\bBECARI[OA]|\bESTAGI[ÁA]RI[OA]")
# Directeur/Directrice (FR), Direttore/Direttrice (IT), Diretor/Diretora (PT). Spanisch (`Director`,
# `Directora`) trifft schon das englische „DIRECTOR“. Mehrdeutiges (Responsable, Jefe, Gerente) bewusst nicht.
_DIRECTOR_ROMANISCH_RE = re.compile(r"\bDIRECTEUR|\bDIRECTRICE|\bDIRETTORE|\bDIRETTRICE|\bDIRETORA?\b")


def norm_seniority(raw) -> Tuple[Optional[str], Optional[str]]:
    if raw is None:
        return None, None
    s = str(raw).strip()
    if not s or s.lower() == "none":
        return None, None
    up = s.upper()
    if "VP" in up or "VICE PRESIDENT" in up:
        return "VP", s
    if _C_LEVEL_RE.search(up):
        return "C-Level", s
    if "SENIOR DIRECTOR" in up or "SR DIRECTOR" in up or "SR. DIRECTOR" in up:
        return "Senior Director", s
    if "DIRECTOR" in up or _DIRECTOR_ROMANISCH_RE.search(up):
        return "Director", s
    if "HEAD" in up or _HEAD_DE_RE.search(up):
        return "Head", s
    if "SENIOR MANAGER" in up or "SR MANAGER" in up:
        return "Senior Manager", s
    if "MANAGER" in up:
        return "Manager", s
    if "TEAMLEIT" in up or "TEAM LEAD" in up or "TEAMLEAD" in up:
        return "Teamlead", s
    # Reihenfolge wichtig: „Senior Intern“ ist ein Praktikum, „Ohne Berufserfahrung“ kein „Erfahren“.
    for muster, stufe in ((_PRAKTIKANT_RE, "Praktikant"), (_WERKSTUDENT_RE, "Werkstudent"),
                          (_AZUBI_RE, "Auszubildender"), (_TRAINEE_RE, "Trainee"),
                          (_EINSTEIG_RE, "Berufseinsteiger"), (_EXPERTE_RE, "Experte"),
                          (_ERFAHREN_RE, "Erfahrener Mitarbeiter"), (_ANGESTELLT_RE, "Angestellter")):
        if muster.search(up):
            return stufe, s
    return "Sonstige", s


# ── Status ───────────────────────────────────────────────────────────────────
def norm_status(raw) -> Tuple[str, Optional[str]]:
    """Map free-text status into a small clean set. Returns (normalized, raw)."""
    if raw is None:
        return "Neu", None
    s = str(raw).strip()
    if not s or s.lower() in ("none", "unklar", "unbekannt", ""):
        return "Neu", s or None
    low = s.lower()
    if "beirat" in low:
        return "Beirat abgelehnt", s
    if "absage" in low or "abgelehnt" in low or "rejected" in low:
        return "Absage", s
    if ("bewerbung" in low and ("geschickt" in low or "abgeschickt" in low)) or "bewerbung abgeschickt" in low:
        if "keine" not in low:
            return "Beworben", s
    if any(k in low for k in ["no longer accepting", "not found", "nicht mehr verfügbar",
                              "nicht mehr verfuegbar", "stelle nicht mehr", "nicht verfügbar",
                              "falscherlink", "falscher link", "link nicht mehr"]):
        return "Nicht verfügbar", s
    if "geparkt" in low or "geplant" in low:
        return "Geparkt", s
    # Phase 85: VOR dem "Kein Match"-Zweig einsortiert — dessen breite Stichwortliste (u.a.
    # "keine bewerbung") würde sonst zuerst greifen, obwohl es sich um Ghosting handelt.
    if any(k in low for k in ["keine rückmeldung", "keine rueckmeldung", "nie geantwortet",
                              "ghosting", "no response"]):
        return "Keine Rückmeldung", s
    if any(k in low for k in ["keine bewerbung", "kein fit", "skill gap", "skill issue",
                              "sales rolle", "only ", "nur berlin", "onsite", "umzug", "no-go",
                              "too large", "zu klein", "zu kein", "location", "csm", "presales skills",
                              "ic rolle", "ic-rolle", "service manager", "ländercheck", "laendercheck"]):
        return "Kein Match", s
    return "Prüfen", s


# ── Work model ───────────────────────────────────────────────────────────────
def _ohne_akzente(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


# Romanische Entsprechungen (FR, IT, ES, PT), ohne Akzente verglichen. Das Ergebnis bleibt der deutsche
# Maschinenwert. „Teilweise“ (`télétravail partiel`, `teletrabajo parcial`) zählt als Hybrid, nicht als Remote.
_ROMANISCH_HYBRID = ("hybride", "hibrido", "ibrido", "partiel", "parcial", "parziale")
_ROMANISCH_REMOTE = ("teletravail", "teletrabajo", "da remoto", "smart working", "remoto")
_ROMANISCH_ONSITE = ("presentiel", "sur site", "presencial", "in sede")


def norm_work_model(raw) -> Optional[str]:
    if raw is None:
        return None
    low = str(raw).strip().lower()
    if not low:
        return None
    falt = _ohne_akzente(low)
    if "remote" in low and "hybrid" not in low and not any(w in falt for w in _ROMANISCH_HYBRID):
        return "Remote"
    if "hybrid" in low or any(w in falt for w in _ROMANISCH_HYBRID):
        return "Hybrid"
    if any(w in falt for w in _ROMANISCH_REMOTE):
        return "Remote"
    if "vor ort" in low or "onsite" in low or "on-site" in low or "field" in low or "büro" in low:
        return "Onsite"
    if any(w in falt for w in _ROMANISCH_ONSITE):
        return "Onsite"
    return str(raw).strip()


# ── Portal (from URL) ────────────────────────────────────────────────────────
def norm_portal(url) -> str:
    if not url:
        return "Unbekannt"
    u = str(url).lower()
    if "linkedin." in u:
        return "LinkedIn"
    if "indeed." in u:
        return "Indeed"
    if "stepstone." in u:
        return "StepStone"
    if "xing." in u:
        return "Xing"
    if "kununu." in u:
        return "kununu"
    if "glassdoor." in u:
        return "Glassdoor"
    if "welcometothejungle" in u or "wttj" in u:
        return "Welcome to the Jungle"
    if "arbeitsagentur" in u or "bundesagentur" in u:
        return "Bundesagentur"
    return "Firmenseite"


# ── Contact parsing ──────────────────────────────────────────────────────────
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def parse_contact(raw):
    """From a 'Recruiter / Hiring Manager' cell return dict(name, email, role) or None."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() in ("none", "nicht bekannt", "nicht gelistet", "unbekannt", "n/a", "-"):
        return None
    email = None
    m = _EMAIL_RE.search(s)
    if m:
        email = m.group(0)
    role = None
    low = s.lower()
    if "recruit" in low:
        role = "Recruiter"
    elif "hiring manager" in low or "berichtet an" in low or "reports to" in low:
        role = "Hiring Manager"
    name = s if not email else s.replace(email, "").strip(" ,;()")
    return {"name": name or None, "email": email, "role": role, "notes": s}


# ── Dedup key ────────────────────────────────────────────────────────────────
def _slug(x) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(x or "").lower())


def slug_parts(*parts) -> str:
    """dedup_key-Slug aus mehreren Teilen (join OHNE Trenner). Ein kanonischer Ort für
    import_lists (Firmen/Headhunter/Netzwerk-Kontakte) UND main.py (Netzwerk-Kontakt-CRUD,
    Phase 22) — identisch zur früheren import_lists._slug, nicht dupliziert."""
    return re.sub(r"[^a-z0-9]+", "", "".join(str(p or "") for p in parts).lower())


_URL_TRACKING = ("utm_", "trk", "refid", "trackingid", "position", "pagenum", "originalsubdomain")


def url_vergleich(url) -> Optional[str]:
    """Vergleichsform einer Stellen-URL, nur für den Dublettenabgleich: ohne Schema, `www.`, Fragment,
    Tracking-Parameter und Schrägstrich am Ende. LinkedIn-Stellen werden auf die Stellennummer reduziert
    (`/jobs/view/titel-bei-firma-123456` und `/jobs/view/123456/?trk=…` sind dieselbe Stelle)."""
    s = str(url or "").strip()
    if not s:
        return None
    teile = urlsplit(s if "://" in s else f"https://{s}")
    host = teile.netloc.lower().removeprefix("www.")
    if host.endswith("linkedin.com"):
        nummer = re.search(r"/jobs/view/(?:[^/]*-)?(\d{6,})", teile.path) or re.search(r"\bcurrentJobId=(\d+)", teile.query)
        if nummer:
            return f"linkedin.com/jobs/view/{nummer.group(1)}"
    parameter = sorted((k, v) for k, v in parse_qsl(teile.query) if not k.lower().startswith(_URL_TRACKING))
    return host + teile.path.rstrip("/") + (f"?{urlencode(parameter)}" if parameter else "")


def dedup_key(company, title, location=None) -> str:
    return f"{_slug(company)}|{_slug(title)[:60]}|{_slug(location)[:30]}"


def ct_key(company, title) -> str:
    """Firma+Titel-Schlüssel — fängt Near-Dubletten mit abweichendem Standort/URL.

    P2-36 (11.09.2026): bewusst NICHT um den Gender-Zusatz bereinigt (roher Titel) —
    `gmail_ingest._match_job` nutzt diesen Schlüssel für die EXAKTE Mail→Stelle-Zuordnung; mit
    bereinigtem Titel würde ein Firma-Paar mit zwei Gender-Varianten derselben Rolle (ein
    Echtfall) dort plötzlich mehrdeutig — eine Mail zu einer laufenden Bewerbung
    fände dann keinen eindeutigen Job mehr. Der bereinigte Vergleich für die Ingest-Dedup-Regel
    lebt separat in `pipeline.ingest._stellen_schluessel` (s. Spec
    `tasks/spec_p2-36_neuausschreibung_dublette.md`, Abschnitt 2.2/3)."""
    return f"{_slug(company)}|{_slug(title)[:60]}"


# ── Firmen-Schlüssel (P2-39) ───────────────────────────────────────────────────────────────────────────
# Rechtsform-/Regionszusätze, die zwei Schreibweisen DERSELBEN Firma auseinanderreissen können
# (case-insensitiv, NUR ganze Wörter — s. Docstring von firma_key unten für die Begründung).
# Messung 12.09.2026 (über die Firmen und aktiven Stellen der laufenden DB, read-only, s.
# tasks/spec_p2-39_firmen_schluessel.md §2): 15 Firmen-Gruppen fallen bei dieser Bereinigung
# zusammen — JEDE davon derselbe Arbeitgeber (u. a. Firma A/Firma A GmbH, Firma B/Firma B SE,
# Firma C/Firma C Deutschland, Firma D/Firma D EMEA, Firma E/Firma E SE) — 0 Fälle, in denen zwei
# verschiedene Arbeitgeber verschmelzen würden.
# 26.10.2026: Seitenzusätze `jobs|careers|karriere` (LinkedIn nennt die Stellenseite eines Vermittlers
# „Firma F Jobs“; dieselbe Anzeige kam unter „Firma F“ und „Firma F Jobs“ zweimal in „Prüfen“).
# Messung über 626 Firmennamen: genau dieses Paar fällt neu zusammen, 0 verschiedene Arbeitgeber.
FIRMEN_ZUSAETZE = re.compile(
    r"\b(?:gmbh|mbh|ag|se|kg|kgaa|ug|ohg|gbr|ev|ltd|limited|inc|llc|llp|plc|bv|nv|sa|sas|sarl|"
    r"srl|spa|oy|ab|as|aps|pte|pty|holdings?|group|deutschland|germany|europe|emea|"
    r"international|global|jobs|careers|karriere)\b",
    re.IGNORECASE,
)
# 03.11.2026: iberische Rechtsformen (`S.L.`, `SLU`, `Lda`, `Ltda`). Sie fallen NUR als eigenes Wort am
# Ende weg und nie als einziges Wort: `sl` ist auch ein Namensbestandteil, `lda` ein Kürzel.
# Messung 03.11.2026 (read-only, Kopie der laufenden DB): über 764 Firmennamen (Firmen, Stellen,
# Zielfirmen, Headhunter) ändern sich nur 3 Schlüssel (Punkt- und Schrägstrich-Schreibweisen von
# SA und A/S), 0 Paare verschiedener Firmen fallen neu zusammen, 0 trennen sich; kein Name enthält
# `sl`, `slu`, `lda` oder `ltda`. Die romanischen Schreibweisen belegen die Tests.
_FIRMEN_ZUSATZ_ENDE = re.compile(r"(?:\s+(?:sl|slu|lda|ltda))+\s*$")
# Einzelbuchstaben mit Punkt oder Schrägstrich dazwischen (`S.p.A.`, `S.A.R.L.`, `S/A`, `e.V.`):
# Trenner weg, damit der Zusatz als ein Wort erkannt wird.
_EINZELBUCHSTABEN_KETTE = re.compile(r"\b(?:[a-z][./])+[a-z]\b")


def firma_key(name) -> str:
    """Bereinigter Firmen-Schlüssel für den Dublettenabgleich ÜBER Firmen-Schreibweisen hinweg
    (P2-39, Echtfall: eine Stelle hing an der Firma „Beispiel“, zwei weitere an „Beispiel
    GmbH“ — zwei Firmen-Rows für denselben Arbeitgeber, jede Dublettenstufe beginnt mit dem
    Firmennamen und verfehlte den Treffer deshalb systematisch).

    Ablauf: Kleinbuchstaben → Sonderzeichen zu Leerzeichen → Zusatzwörter (FIRMEN_ZUSAETZE,
    Wortgrenzen) entfernen → Leerzeichen weg. Wortgrenzen sind Pflicht, sonst würden Zusatzwörter
    echte Namensbestandteile mit anschlucken — „Firma X Consulting“ muss von „Firma X“ verschieden
    bleiben, „Firma Y Security“ von „Firma Y Data“ (Messung s. tasks/spec_p2-39_firmen_schluessel.md §2,
    Tests in tests/test_firmen_schluessel.py).

    Rückfall: bleibt nach dem Entfernen nichts übrig (Firma heißt z. B. nur „SE Group“), gilt
    der unbereinigte Slug — NIE ein leerer Schlüssel.

    NICHT für `ct_key`/`dedup_key` verwenden — die bleiben bewusst roh (s. deren Kommentare):
    `gmail_ingest._match_job` braucht die exakte, unbereinigte Firma+Titel-Zuordnung für die
    Mail→Stelle-Zuordnung; ein bereinigter Schlüssel könnte dort zwei tatsächlich verschiedene
    Firmen (z. B. „Firma X“/„Firma X Consulting“) versehentlich zusammenwerfen."""
    roh_slug = _slug(name)
    if not roh_slug:
        return roh_slug
    klein = _EINZELBUCHSTABEN_KETTE.sub(lambda m: re.sub(r"[./]", "", m.group(0)), str(name or "").lower())
    ohne_sonderzeichen = re.sub(r"[^a-z0-9]+", " ", klein)
    bereinigt = FIRMEN_ZUSAETZE.sub(" ", ohne_sonderzeichen)
    bereinigt = _FIRMEN_ZUSATZ_ENDE.sub("", bereinigt.rstrip())
    schluessel = re.sub(r"\s+", "", bereinigt)
    return schluessel or roh_slug


# ── Gender-Zusatz (P2-36) ──────────────────────────────────────────────────────────────────────────────
# Gender-Zusätze aus dem Stellentitel entfernen: (m/w/d), (f/m/x), (w/m/d),
# (all genders) und verwandte Schreibweisen (case-insensitive).
# P3-5 (Code-Review 2026-07-25): Die Doppelpunkt-Alternative erlaubte strukturell nur GENAU EIN
# Buchstaben-Paar ([a-z]:[a-z]) -- "(m:w:d)" (drei Buchstaben) blieb deshalb stehen und landete
# als "..._mwd_DE" im empfängersichtbaren Dateinamen. Jetzt dieselbe {1,4}-Wiederholungslogik wie
# bei der Schrägstrich-/Pipe-Alternative (nur mit ":" statt "[/|]" als Trenner) -- read-only
# gegen alle echten Jobtitel der Live-DB geprüft (Phase 68B): 0 Titel enthalten überhaupt
# einen Doppelpunkt, die Änderung betrifft aktuell keinen Bestandstitel, ist aber künftig
# wirksam und regressionsfrei (die 122 Titel, bei denen ALT bereits matchte, matchen mit NEU
# identisch weiter).
# P2-36 (11.09.2026): von app/naming.py hierher verschoben — ein kanonischer Ort, wie
# `slug_parts` oben. `ingest.py` braucht den Regex jetzt ebenfalls (bereinigter Firma+Titel-
# Schlüssel, s. `titel_ohne_gender` unten); `naming.py` importiert ihn ab jetzt von hier statt
# ihn selbst zu definieren. Muster unverändert (am Bestand geprüft, s. P3-5 oben).
# 03.11.2026: Teile in der Klammer dürfen auch `nb` oder `xy` sein (`(f/m/nb)`, `(m/f/xy)`). OHNE Klammer
# fällt der Zusatz nur am Titelende weg und nur als eines der Paare H/F, F/H, M/F, F/M, H/M, M/H (mit
# davorstehendem ` - ` möglich, `Livreur - F/H`); danach dürfen noch Gender-Klammern folgen
# (`Chauffeur H/F (H/F)`). Nicht angefasst: `Repartidor/a`, `Chauffeur/Livreur`, `IT/OT`, `B/C`.
_GENDER_TEIL = r"(?:[a-z]|nb|xy)"
_GENDER_KLAMMER = (
    r"\(\s*(?:all\s+genders|" + _GENDER_TEIL + r"(?:\s*[/|]\s*" + _GENDER_TEIL + r"){1,4}|[a-z]\*|"
    + _GENDER_TEIL + r"(?:\s*:\s*" + _GENDER_TEIL + r"){1,4})\s*\)"
)
_GENDER_PAAR_ENDE = (
    r"(?:\s+-\s+|\s+)?(?<![\w/])(?:h\s*/\s*[fm]|f\s*/\s*[hm]|m\s*/\s*[fh])(?![\w/])"
    r"(?=(?:\s*" + _GENDER_KLAMMER + r")*\s*$)"
)
GENDER_RE = re.compile(_GENDER_KLAMMER + "|" + _GENDER_PAAR_ENDE, re.IGNORECASE)


def titel_ohne_gender(title) -> str:
    """Stellentitel ohne Gender-Zusatz, z. B. „Manager (m/f/d)“ -> „Manager“ (P2-36, s. Spec
    `tasks/spec_p2-36_neuausschreibung_dublette.md` §2.2) — für den bereinigten Firma+Titel-
    Schlüssel `pipeline.ingest._stellen_schluessel`. NICHT für `ct_key`/`dedup_key` verwenden
    (bleiben roh, s. Kommentar an `ct_key`)."""
    ohne_zusatz = GENDER_RE.sub(" ", str(title or ""))
    return re.sub(r"\s+", " ", ohne_zusatz).strip()


def rollen_schluessel(title) -> str:
    """Titelteil des bereinigten Stellen-Schlüssels: Titel ohne Gender-Zusatz als Slug, auf 60
    Zeichen gekappt. EINE Definition von „dieselbe Rolle“ für zwei Nutzer (P2-43):
    `pipeline.ingest._stellen_schluessel` (Dubletten beim Einlesen, mit Firmenteil davor) und
    `pipeline.gmail_ingest._zwillinge_aufloesen` (Mail-Zuordnung innerhalb EINER Firma, daher
    ohne Firmenteil). Laufen die beiden auseinander, würde eine als Dublette geparkte Stelle
    bei der Mail-Zuordnung plötzlich als eigene Rolle zählen — oder umgekehrt."""
    return _slug(titel_ohne_gender(title))[:60]


def match_score_int(raw) -> Optional[int]:
    if raw is None:
        return None
    try:
        return int(float(str(raw).strip()))
    except (ValueError, TypeError):
        m = re.search(r"[1-5]", str(raw))
        return int(m.group(0)) if m else None
