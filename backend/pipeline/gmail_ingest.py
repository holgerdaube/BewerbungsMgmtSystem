#!/usr/bin/env python3
"""E-Mail-Tracking-Ingest für das Bewerbungs-Management-System.

Claude-in-the-Loop liest Gmail (letzte 24–36h), klassifiziert bewerbungsrelevante Mails
und übergibt sie hier als Records. Dieser Modul schreibt sie deterministisch in die DB:
Firma/Job/Bewerbung zuordnen (oder anlegen), Kontakt pflegen, Antwortzeit berechnen,
Job-/Bewerbungsstatus fortschreiben. Dedup über gmail_message_id.

Record-Schema (ein Objekt je Mail):
    {
      "gmail_message_id": "…", "gmail_thread_id": "…",
      "direction": "incoming|outgoing",
      "from_addr": "…", "to_addr": "…", "subject": "…", "snippet": "…",
      "received_at": "2026-07-08T15:35:54Z",           # ISO
      "category": "Eingangsbestätigung|Einladung|Absage|Rückfrage|Angebot|Sonstige",
      "company": "…",                                   # zur Zuordnung/Anlage
      "job_title": "…",                                 # existierenden Job matchen ODER neu anlegen
      "job_status": "Beworben|Absage|Interview|Angebot", # Status für gematchten/neuen Job
      "needs_reply": false,
      "contact": {"name": "…", "email": "…", "role": "Recruiter"},
      "applied_date": "…"                               # optional, für Antwortzeit
    }
"""
import datetime
import json
import re
import sys

from sqlmodel import Session, select

from app.db import engine, flush_or_duplicate, init_db
from app.models import Application, Company, Contact, Email, Job, JobLog, Run
from app import normalize as N
from pipeline.dedup_text import titel_aehnlichkeit

RESPONSE_CATS = {"Eingangsbestätigung", "Einladung", "Absage", "Rückfrage", "Angebot"}


def _parse_dt(s):
    if not s:
        return None
    s = str(s).strip()
    for fmt in (None, "%d.%m.%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            if fmt is None:
                return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
            return datetime.datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _words(s) -> list:
    """Wort-Tokens für den Fuzzy-Firmen-Abgleich unten — `\\w+` (unicode-fähig) statt
    `[a-z0-9]+`, damit z. B. „Müller" ein Token bleibt statt in „m"+"ller" zu zerfallen."""
    return re.findall(r"\w+", (s or "").lower())


def _is_sub_sequence(kurz, lang) -> bool:
    n, m = len(kurz), len(lang)
    return n > 0 and n <= m and any(lang[i:i + n] == kurz for i in range(m - n + 1))


def _fuzzy_find_company(session, name):
    """Firma über Wort-Teilfolge statt exaktem Namen finden — deckt Firmen-Kürzel/-Zusätze in
    Mail-Signaturen ab, z. B. Mail-Absender „Muster" vs. getrackt „Muster Management
    Consultants" (Fall 22.07.2026 — derselbe Root Cause steckt hinter den 6 Dubletten-Paaren
    aus der Absagen-Analyse vom 09.07., s. tasks/todo.md: "gmail_ingest-Firmen-Matching bei
    abweichender Schreibweise").

    Bewusst NUR wortgrenzen-basiert (kurz muss als zusammenhängende Token-Folge IRGENDWO in
    lang vorkommen), nicht roher Zeichen-Substring: ein kurzer Firmenname darf NIEMALS einen
    anderen, unverwandten Firmennamen treffen, der ihn nur zufällig als Zeichenkette enthält,
    z. B. „Rat" in „Vorrat" — zwei unterschiedliche Firmen. Roher Substring hätte das getan
    (\"rat\" in \"vorrat\"); mit Wort-Tokens ist \"rat\" nie eine Teilfolge von \"vorrat\",
    weil beides je EIN Token ist. Gegen die echten Firmen der laufenden DB verifiziert:
    0 Fehltreffer, mehrere echte Treffer, bereits ab Mindestlänge 3 Zeichen (identische
    Schwelle wie `main.py::network_check`, dort aber ohne Wortgrenzen — hier bewusst stärker
    abgesichert, weil ein Fehl-Match hier nicht nur eine Anzeige verfälscht, sondern eine Mail
    an der falschen Firma/Job landet).

    Matcht NUR bei GENAU EINEM Kandidaten — bei mehreren (z. B. könnte „Beispiel Deutschland"
    zu mehreren Varianten derselben Beratung passen) wird abgestellt: lieber eine zusätzliche
    Firma anlegen als raten (gleiche Philosophie wie der Kommentar in `_match_job` oben — „ein
    stiller Fehl-Match ist schlimmer als ein zusätzlicher Job, den der Nutzer in der Review sieht").
    """
    wa = _words(name)
    if not wa or (len(wa) < 2 and len(wa[0]) < 3):
        return None
    treffer = []
    for c in session.exec(select(Company)).all():
        wb = _words(c.name)
        if not wb:
            continue
        kurz, lang = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
        if len(kurz) < 2 and len(kurz[0]) < 3:
            continue
        if _is_sub_sequence(kurz, lang):
            treffer.append(c)
    return treffer[0] if len(treffer) == 1 else None


def _get_or_create_company(session, cache, name, **fields):
    key = (name or "").strip().lower()
    if not key:
        return None
    if key in cache:
        return cache[key]
    # P2-3 (Phase 67F): case-insensitiver Abgleich VOR dem Fuzzy-Match (Muster main.py::
    # create_job) — der UNIQUE-Index auf company(LOWER(TRIM(name))) ist ebenfalls case-
    # insensitiv; ein rein case-sensitiver Vorab-Check hätte eine bestehende, nur anders
    # geschriebene Firma verfehlt und wäre geradewegs in den Index gelaufen.
    comp = next((c for c in session.exec(select(Company)).all() if c.name.strip().lower() == key), None)
    if not comp:
        comp = _fuzzy_find_company(session, name)
    if not comp:
        neu = Company(name=name, **{k: v for k, v in fields.items() if v})
        # `session.add(neu)` bewusst ERST im Callback (nicht davor!) — s. Docstring von
        # flush_or_duplicate (begin_nested() autoflusht sonst vorher pending Änderungen
        # AUSSERHALB der Savepoint-Absicherung).
        if flush_or_duplicate(session, lambda: session.add(neu)):
            comp = neu
        else:
            # Echte Race (zwei fast gleichzeitige Schreiber legen dieselbe Firma an) — die jetzt
            # existierende Zeile nachschlagen statt mit einem 500er zu crashen.
            comp = next((c for c in session.exec(select(Company)).all() if c.name.strip().lower() == key), None)
    cache[key] = comp
    return comp


# Sentinel-Rückgabe von `_match_job`: MEHRERE gleichwertige Kandidaten gefunden (Phase 61A,
# 25.07.2026, P0-1-Fix). Eigener Wert statt eines zweiten Bedeutungs-Overloads von None — None
# bleibt exklusiv „kein Kandidat" (Aufrufer legt einen neuen Job an), _MEHRDEUTIG heißt „einer
# der bestehenden Jobs IST die richtige Stelle, wir wissen nur nicht welcher" (Aufrufer legt
# NICHTS an — ein dritter Job wäre schlicht falsch, s. Docstring unten und
# tasks/spec_phase61_mail_zuordnung.md, Abschnitt „Bewusste Abweichung vom Fix-Vorschlag").
_MEHRDEUTIG = object()

# Titel-Schwelle für den Fuzzy-Fallback unten. GEMESSEN (nicht geraten, M2) gegen die echten
# Jobtitel der Live-DB, read-only, 25.07.2026:
#   - Review-Beleg mechanisch reproduziert: den FRÜHEREN 20-Zeichen-Fallback (Z. 139-143 vor diesem
#     Fix) exakt nachgebaut und gegen alle echten Firmen mit 2+ Jobs laufen lassen (ct_key-
#     exakter Vorabgleich zuerst, wie im echten Code). Ergebnis: GENAU 8 Firmen, bei denen der
#     alte Fallback einen Treffer geliefert hätte (deckt sich exakt mit „8 Firmen-Paare" aus dem
#     Review) — darunter das Review-Beispiel Firma A „Stelle A (m/f/d)" vs.
#     „… – Stelle B (m/f/d)".
#   - Von diesen 8 liegen 7 mit voller Titel-Ähnlichkeit (titel_aehnlichkeit(), ungestrippt) bei
#     >= 0.5 (Firma A 0.667, Firma B 0.750, Firma C 0.857, Firma D 0.750, Firma E 0.636,
#     Firma F 0.625, Firma G 0.5-0.727 je nach Teilpaar) — 0.5
#     erkennt sie alle als mehrdeutig.
#   - Der 8. Fall (eine Executive-Search-Beratung, zwei gleichlautende Mandate) scort nur
#     0.364 UND bleibt damit bewusst UNTER der Schwelle: jenseits der gemeinsamen ersten 3 Wörter
#     sind es zwei versch. Mandate (versch. Technologie-Domäne/Kunde) — exakt das „Exec-Search-
#     Genre"-Fehlalarm-Muster, das dedup_text.py's eigene Kalibrierungs-Historie (Iteration 2)
#     bereits als Nicht-Match dokumentiert. Der alte Fallback flaggte nur wegen des gemeinsamen
#     PRÄFIXES (20 Zeichen); die volle Titel-Ähnlichkeit ist hier zu Recht präziser als die
#     mechanische Reproduktion des alten Bugs — dieser Fall bleibt ein einzelner sauberer
#     Treffer statt fälschlich mehrdeutig. Schwelle NICHT weiter gesenkt, um ihn zu erzwingen.
#   - Schwellen-Sweep über alle 63 realen Firmen-Paare (>=2 aktive/nicht-gelöschte Jobs
#     derselben Firma): 0.40→20, 0.45→17, 0.50→16, 0.55→14, 0.60→13 von 63 läge über der Schwelle.
#   - Degradations-Probe (eingehender Mail-Titel = wahre Zielstelle OHNE Gender-Suffix — eine
#     realistische Betreff-Extraktions-Ungenauigkeit): in allen 4 getesteten Richtungen
#     (Firma A und Firma G, je kürzerer/längerer Titel als wahres Ziel) lag der Score
#     gegen die WAHRE Stelle bei >= 0.5, gegen die falsche Schwester-Stelle bei <= 0.455 — 0.5
#     findet den wahren Treffer UND schließt die falsche Stelle sauber aus.
#   - Gender-Vorab-Strippen (app.naming._GENDER_RE, wie für Dateinamen) GEPRÜFT und NICHT
#     übernommen: es verschlechtert die Trennschärfe (Minimum der Kollisionsgruppe fällt von
#     0.500 auf 0.333 — kurze Titel verlieren dabei einen überproportionalen Anteil ihrer
#     ohnehin wenigen Wörter). Titel bleiben daher roh, wie in dedup_text.py.
_TITEL_SCHWELLE = 0.5

# P2-43 — Status, die belegen, dass sich der Nutzer auf eine Stelle tatsächlich beworben hat, und die
# Teilmenge, in der diese Bewerbung noch läuft. Nur für die Zwillingsregel unten. „Vorbereitet“
# (Anschreiben liegt bereit) ist bewusst KEIN Beleg: es steht an der Bewerbungszeile, nicht am
# Job-Status, und auch an nie verschickten Bewerbungen (Echtfall: die Bewerbungszeile hängt an
# einem Job mit dem Status „Beirat abgelehnt“, beworben hat sich der Nutzer auf den Zwilling).
_BEWORBEN_STATI = {"Beworben", "Interview", "Angebot", "Absage", "Keine Rückmeldung"}
_LAUFEND_STATI = {"Beworben", "Interview", "Angebot"}


def _zwillinge_aufloesen(kandidaten):
    """Mehrere Kandidaten → die EINE laufende Bewerbung unter Zwillingen, sonst `_MEHRDEUTIG` (P2-43).

    Greift nur, wenn ALLE Kandidaten dieselbe Rolle sind (`N.rollen_schluessel`: Dubletten einer
    Anzeige, typischerweise per „Als Dublette parken“ oder als Neuausschreibung entstanden).
    Dann lautet die Frage nicht „welche Stelle meint die Mail?“, sondern „welcher Datensatz
    trägt die Bewerbung?“. Zugeordnet wird nur, wenn GENAU EIN Zwilling einen Bewerbungs-Status
    hat UND diese Bewerbung noch läuft.

    Echtfall (18.09.2026): Einladung zur zweiten Runde ohne Titel in Betreff und
    Vorschau; an der Firma hängen seit der P2-39-Bereinigung mehrere Zwillinge mit
    unterschiedlichem Status (Interview, Kein Match, Geparkt/Dublette) — die Mail blieb ohne Stelle.

    Warum nur laufende Bewerbungen: Bewirbt sich der Nutzer auf eine Neuausschreibung, deren
    Vorgänger auf „Absage“ steht, und kommt die Eingangsbestätigung, bevor er den Status der neuen
    Stelle gesetzt hat, wäre der abgelehnte Vorgänger der einzige beworbene Zwilling — die Mail
    setzte ihn zurück auf „Beworben“. Zwei beworbene Zwillinge bleiben ebenso mehrdeutig.

    Die Phase-61A-Regel „lieber keine Zuordnung als eine falsche“ bleibt unangetastet: Zwischen
    VERSCHIEDENEN Rollen entscheidet der Status nie (s. tasks/spec_phase61_mail_zuordnung.md,
    „Bewusste Abweichung“)."""
    if len({N.rollen_schluessel(j.title) for j in kandidaten}) != 1:
        return _MEHRDEUTIG
    beworben = [j for j in kandidaten if j.status in _BEWORBEN_STATI]
    if len(beworben) == 1 and beworben[0].status in _LAUFEND_STATI:
        return beworben[0]
    return _MEHRDEUTIG


def _match_job(session, comp, title):
    """Bestehenden Job der Firma per Firma+Titel finden (exakter ct_key-Vergleich, dann
    Fuzzy-Fallback über dedup_text.titel_aehnlichkeit()). Ohne Titel: einzigen Job der Firma
    zurückgeben (sonst None).

    Rückgabe: Job (genau ein Kandidat) | None (kein Kandidat) | _MEHRDEUTIG (mehrere
    gleichwertige Kandidaten — s. Sentinel-Kommentar oben).

    MIT Titel und ohne Treffer: None → der Aufrufer legt einen neuen Job an. Früher fiel die
    Funktion hier auf `jobs[0]` zurück, sobald die Firma genau EINEN Job hatte. Dadurch wäre
    eine Mail zu „Stelle A" am Job „Stelle B" derselben Firma
    gelandet (10.07. beim Nachhol-Lauf aufgefallen). Eine Firma schreibt mehrere Rollen aus;
    ein stiller Fehl-Match ist schlimmer als ein zusätzlicher Job, den der Nutzer in der Review sieht.

    Phase 61A (25.07.2026, P0-1 aus dem Code-Review): dieselbe Philosophie zu Ende geführt,
    zwei weitere stille Fehl-Matches behoben:
    1. Gelöschte Jobs (Tombstones, `deleted_at`) sind NIE Kandidat — die Firma hat den Job
       gelöscht, eine eingehende Mail darf ihn nicht wiederbeleben (in der Live-DB kommt diese
       Überschneidung mehrfach vor).
    2. Der alte 20-Zeichen-Präfix-Fallback nahm bei MEHREREN passenden Titeln den ERSTEN
       Treffer der DB-Reihenfolge — exakt das Muster, das `_fuzzy_find_company` oben schon
       richtig macht („ein Kandidat oder keiner"). Ersetzt durch titel_aehnlichkeit()
       (dedup_text.py, konfigurationsfrei — KEIN Aufruf von dedup_text.konfiguration(), die
       liest config/suchprofile.yaml und existiert in CI nicht) gegen `_TITEL_SCHWELLE`: ALLE
       Kandidaten über der Schwelle sammeln, genau einer → Treffer, mehrere → `_MEHRDEUTIG`.
       Bewusst KEIN Rückgriff auf den Job-Status (aktiv/terminal) zur Entscheidung — genau das
       hätte die Fehlrichtung nur umgedreht (s. Spec-Abschnitt „Bewusste Abweichung").

    P2-43 (19.09.2026): EINE Ausnahme, nur unter Zwillingen derselben Rolle — s.
    `_zwillinge_aufloesen`. Zwischen verschiedenen Rollen gilt Punkt 2 unverändert.
    """
    if not comp:
        return None
    jobs = session.exec(
        select(Job).where(Job.company_id == comp.id, Job.deleted_at.is_(None))
    ).all()
    if not jobs:
        return None
    if not title:
        if len(jobs) == 1:
            return jobs[0]
        # P2-43: sind alle Stellen der Firma Zwillinge EINER Rolle, trägt die eine laufende
        # Bewerbung die Mail. Scheitert das, bleibt es bei None (nicht _MEHRDEUTIG), damit der
        # Aufrufer den Volltext-Versuch weiter unternehmen kann.
        zwilling = _zwillinge_aufloesen(jobs)
        return None if zwilling is _MEHRDEUTIG else zwilling
    want = N.ct_key(comp.name, title)
    exakt = [j for j in jobs if N.ct_key(j.company_name, j.title) == want]
    if len(exakt) == 1:
        return exakt[0]
    if len(exakt) > 1:
        return _zwillinge_aufloesen(exakt)          # P2-43
    fuzzy = [j for j in jobs if titel_aehnlichkeit(title, j.title) >= _TITEL_SCHWELLE]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if len(fuzzy) > 1:
        return _zwillinge_aufloesen(fuzzy)          # P2-43
    return None


# Mindestlaenge eines Jobtitels, damit er im Volltext gesucht werden darf. Kurze Titel wie
# „Consultant“ kaemen in einer langen Mail zufaellig vor; 15 Zeichen (nach dem Flachklopfen)
# verlangen im Grunde zwei Woerter.
_VOLLTEXT_MIN_TITEL = 15


def _flach(text):
    """Nur Kleinbuchstaben und Ziffern — Satzzeichen, Klammern und Leerraum fallen weg.

    Noetig, weil dieselbe Rolle in der Anzeige und in der Mail unterschiedlich gesetzt ist:
    „(Senior) Manager Einkauf & Service Delivery (m/w/d)“ taucht im Fliesstext mit
    denselben Zeichen auf, aber schon ein anderer Bindestrich oder ein Zeilenumbruch mitten im
    Titel wuerde einen wortgetreuen Vergleich scheitern lassen.
    """
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _volltext(gmail_message_id):
    """Mailtext aus Gmail nachladen — None, wenn das nicht geht.

    BEWUSST fehlertolerant: Ohne Netz oder Zugangsdaten (CI hat beides nicht) und bei einer
    inzwischen geloeschten Mail laeuft der Ingest normal weiter, nur ohne diese Zusatzquelle.
    Ein Zuordnungs-Komfort darf den Ingest nie zum Absturz bringen.
    """
    if not gmail_message_id:
        return None
    try:
        from pipeline import gmail_client
        rec = gmail_client.cmd_get(gmail_message_id) or {}
    except Exception:
        return None
    return rec.get("body") or rec.get("text") or None


def _match_job_im_volltext(session, comp, gmail_message_id):
    """Die Stellen DIESER Firma im Mailtext suchen — genau ein Treffer zaehlt.

    WOFUER (Echtfall, 08.09.2026): Der Stellentitel steht in vielen Absagen NUR im
    Fliesstext („vielen Dank fuer deine Bewerbung auf die Position …“), waehrend der Betreff
    generisch bleibt („Firma A | Deine Bewerbung“). Der Lauf sieht davon nichts: Er arbeitet
    mit Betreff und Gmail-Snippet, und das Snippet ist mit ~120 Zeichen nicht nur kurz, sondern
    kuerzt ausgerechnet die Titel-Stelle weg („… fuer deine Bewerbung ... Leider koennen wir
    dich …“). Also blieb `job_title` leer, und die Absage landete ohne Stelle in der Inbox —
    obwohl ein Mensch sie in drei Sekunden zuordnet, weil er den Volltext liest.

    RICHTUNG DER SUCHE: Es werden die BEKANNTEN Titel im Text gesucht, nicht ein Titel aus dem
    Text geraten. Das braucht kein Modell, ist deterministisch und kann nichts erfinden. Neben-
    effekt: Stehen zwei aehnliche Stellen in der DB („X“ und „X in Duesseldorf“), trifft nur
    die, deren Titel wirklich so im Text steht.

    Mehrere Treffer → `_MEHRDEUTIG`, wie in `_match_job`: lieber keine Zuordnung als eine falsche.
    """
    jobs = session.exec(
        select(Job).where(Job.company_id == comp.id, Job.deleted_at.is_(None))
    ).all()
    if not jobs:
        return None
    text = _volltext(gmail_message_id)
    if not text:
        return None
    flach_text = _flach(text)
    treffer = [j for j in jobs
               if len(_flach(j.title)) >= _VOLLTEXT_MIN_TITEL and _flach(j.title) in flach_text]
    if len(treffer) == 1:
        return treffer[0]
    if len(treffer) > 1:
        return _zwillinge_aufloesen(treffer)        # P2-43: identische Titel = Zwillinge
    return None


# ── Spaete „Eingangsbestaetigung“ = meist eine Absage (P2-48, 25.09.2026) ────────────────
# ECHTFALL: Bewerbung am 24.07., am 25.09. — 63 Tage spaeter — kam eine Mail mit
# dem Betreff „Zukunft gestalten - Ihre Bewerbung bei uns“. Betreff und Gmail-Vorschau lasen
# sich wie eine Eingangsbestaetigung („vielen Dank fuer Ihre Bewerbung …“), der Absagesatz stand
# erst in Absatz 2: „Leider koennen wir auch Sie im weiteren Auswahlprozess nicht beruecksichtigen.“
# Der Lauf stufte sie als Eingangsbestaetigung ein, die Stelle blieb auf „Beworben“.
#
# Die Regel dafuer steht seit einem frueheren Echtfall (30.07.2026) in email-check/SKILL.md: Volltext
# ist PFLICHT, u. a. wenn die Mail spaeter als 7 Tage nach der Bewerbung kommt. Sie wurde uebergangen.
# Prosa allein traegt hier nicht — deshalb dieselbe Pruefung deterministisch im Code.
#
# GEMESSEN am echten Bestand (25.09.2026): Von 154 Eingangsbestaetigungen kam GENAU EINE mehr als
# 7 Tage nach der Bewerbung — die Mail aus diesem Echtfall. Die Musterliste unten lief gegen 22 echte
# Volltexte (10 echte Eingangsbestaetigungen, 11 bekannte Absagen, plus dieser Fall): 0 Fehlalarme
# bei den Bestaetigungen, der Fall erkannt. Sie ist bewusst ein NETZ, kein Klassifikator — sie stuft nur
# „Eingangsbestaetigung“ herauf, nie etwas herunter.
_SPAETE_BESTAETIGUNG_TAGE = 7

_ABSAGE_MUSTER = [re.compile(m, re.I) for m in (
    r"nicht (?:weiter )?ber(?:ü|ue)cksichtig",
    r"nicht in die engere (?:Wahl|Auswahl)",
    r"nicht zum Zuge",
    r"leider .{0,60}absag|absage erteilen|leider eine Absage",
    r"regret to inform|unfortunately[,.]? (?:we|you)|not (?:be )?(?:moving|going) forward",
    r"decided (?:not to (?:proceed|move)|to (?:proceed|move) forward with (?:other|another))",
    r"not (?:been )?(?:selected|successful)|no longer under consideration|will not be progressing",
    r"andere[nr]? Bewerber.{0,40}entschieden",
)]


# Ein Treffer mitten in einem BEDINGUNGSSATZ ist keine Absage: „Sollten wir Sie nicht
# beruecksichtigen koennen, melden wir uns" steht so in echten Eingangsbestaetigungen. Deshalb
# zaehlt ein Muster nur, wenn im Vorlauf kein Bedingungswort steht (gemessen an genau diesen
# Saetzen, 25.09.2026 — ohne den Vorlauf-Check schlugen sie als Absage an).
_BEDINGUNG_RE = re.compile(r"\b(falls|sofern|sollte[nst]?|wenn|should|in case)\b", re.I)
_BEDINGUNG_FENSTER = 60


def absage_im_volltext(text) -> bool:
    """Traegt dieser Mailtext eine unmissverstaendliche Absage-Formulierung? (P2-48)"""
    text = text or ""
    for muster in _ABSAGE_MUSTER:
        for treffer in muster.finditer(text):
            vorlauf = text[max(0, treffer.start() - _BEDINGUNG_FENSTER):treffer.start()]
            if not _BEDINGUNG_RE.search(vorlauf):
                return True
    return False


def spaete_absage_erkennen(gmail_message_id, kategorie, empfangen, beworben_am):
    """`True`, wenn eine als „Eingangsbestaetigung“ eingestufte Mail in Wahrheit eine Absage ist.

    Drei Bedingungen, alle noetig: die Einstufung lautet „Eingangsbestaetigung“ (nur sie behauptet,
    es sei nichts passiert), die Mail kam mehr als `_SPAETE_BESTAETIGUNG_TAGE` Tage nach der
    Bewerbung, und der VOLLTEXT enthaelt eine Absage-Formulierung. Der Volltext wird nur in
    diesem seltenen Fall geladen (Messung: 1 von 154) — kein pauschaler Netzaufruf je Mail.
    Faellt das Laden aus (kein Netz, Mail geloescht), bleibt es bei der Einstufung des Laufs."""
    if kategorie != "Eingangsbestätigung" or not (empfangen and beworben_am):
        return False
    if (empfangen - beworben_am).days <= _SPAETE_BESTAETIGUNG_TAGE:
        return False
    return absage_im_volltext(_volltext(gmail_message_id))


def beworben_am_je_job(session) -> dict:
    """`job_id` -> Zeitpunkt der Bewerbung. Schwester von `bewerbungs_anker`, nur job-basiert.

    WOFUER: Die Exporte (Excel-Spalte „Beworben am“, Coach-Site) brauchen den Zeitpunkt je STELLE,
    nicht je Bewerbung — 148 Stellen haben Bewerbungsbezug, aber nicht jede eine `Application`-Row.

    DIESELBEN ZWEI QUELLEN wie dort, aus demselben Grund: `application.applied_date` allein ist
    duenn (Bestand 08.09.2026: 23 von 148 Stellen), der JobLog-Statuswechsel deckt 98 ab.
    Zusammen traegt die Spalte; mit `applied_date` allein waere sie zu vier Fuenfteln leer und
    damit wertlos.

    Bei mehreren Wechseln auf „Beworben“ zaehlt der FRUEHESTE — gefragt ist, seit wann der Prozess
    laeuft, nicht wann er zuletzt angefasst wurde. `applied_date` schlaegt das Log, weil es von
    Hand gepflegt ist und damit die genauere Angabe.
    """
    from app.models import Application, JobLog

    aus_log = {}
    for eintrag in session.exec(select(JobLog).where(JobLog.eintrag.contains(BEWORBEN_MARKE))).all():
        if not eintrag.created_at:
            continue
        bisher = aus_log.get(eintrag.job_id)
        if bisher is None or eintrag.created_at < bisher:
            aus_log[eintrag.job_id] = eintrag.created_at

    anker = dict(aus_log)
    for app in session.exec(select(Application)).all():
        if app.job_id and app.applied_date:
            gedeutet = _parse_dt(app.applied_date)
            if gedeutet:
                anker[app.job_id] = gedeutet
    return anker


def response_time_hours(received_at, applied_at):
    """Stunden zwischen Bewerbungs-Anker und Antwort-Mail, oder None (kein Anker / negativ).
    Extrahiert aus dem Batch-Ingest (Phase 36), damit der Assign-Endpunkt (main.py) dieselbe
    Rechnung für eine EINZELNE E-Mail nutzt statt sie zu duplizieren."""
    if not received_at or not applied_at:
        return None
    delta = (received_at - applied_at).total_seconds() / 3600.0
    return round(delta, 1) if delta >= 0 else None


def anker_fuer_antwortzeit(applied_je_bewerbung, applied_je_firma, app_id, company_key):
    """Bezugspunkt fuer die Antwortzeit: die EIGENE Bewerbung schlaegt den Firmen-Anker.

    P2-17 (Phase 92). Bis dahin war der Anker allein nach Firmennamen verschluesselt und nahm
    die FRUEHESTE Bewerbung bei dieser Firma. Bei Mehrfachbewerbungen misst das gegen die
    falsche Bewerbung: Eine Absage vom 26.08.2026 auf eine Bewerbung vom 23.08. stand
    mit 1358,9 h in der DB statt rund 72 h — gerechnet ab der ersten Bewerbung bei dieser Firma im
    Juli. Das verzerrt jede Auswertung ueber Antwortzeiten nach oben, und zwar genau bei den
    Firmen, die der Nutzer mehrfach angeschrieben hat.

    Der Firmen-Anker bleibt als Rueckfallebene: Mails ohne Stellenzuordnung (Absage ohne
    erkennbaren Stellenbezug, mehrdeutige Treffer) haben keine Bewerbung, an der sie haengen —
    fuer sie ist die frueheste Bewerbung bei der Firma weiterhin die beste verfuegbare Schaetzung.

    `POST /api/emails/{id}/assign` in `app/main.py` rechnet schon immer gegen die Bewerbung
    selbst. Vor dieser Umstellung lieferten die beiden Wege fuer dieselbe Mail unterschiedliche
    Zahlen — je nachdem, ob sie im Lauf oder von Hand zugeordnet wurde.
    """
    if app_id is not None:
        eigen = applied_je_bewerbung.get(app_id)
        if eigen:
            return eigen
    return applied_je_firma.get(company_key) if company_key else None


BEWORBEN_MARKE = "→ Beworben"


def bewerbungs_anker(session) -> dict:
    """`application_id` -> Zeitpunkt der Bewerbung, aus der besten verfuegbaren Quelle.

    P2-17 (Phase 92). Die naheliegende Quelle `application.applied_date` ist duenn: Im Bestand
    des Nutzers ist sie nur bei einer Minderheit der Bewerbungen gefuellt — der Ingest legt
    Bewerbungen aus Mails an und hat das Datum meist nicht. Ohne eine zweite Quelle liefe die
    Antwortzeit fuer den Rest der Bewerbungen weiter auf den Firmen-Anker, und genau der Fall,
    der die Umstellung ausgeloest hat, waere NICHT behoben.

    Zweite Quelle ist das JobLog: Der Statuswechsel auf „Beworben" wird bei jedem PATCH
    automatisch protokolliert (`Status: Pruefen → Beworben`, art='auto'). Das ist der
    Zeitpunkt, zu dem die Bewerbung im System als raus markiert wurde. Fuer den ausloesenden
    Fall steht dort der 23.08.2026, 09:37 — dasselbe Datum, das LinkedIn im Mailtext nennt
    („Applied on Aug 23"). Das deckt einen Großteil der verbleibenden Luecken ab, zusammen also
    die meisten Bewerbungen.

    Gibt es mehrere Wechsel auf „Beworben" (Job zurueckgesetzt und erneut beworben), zaehlt der
    FRUEHESTE — die Antwortzeit misst ab der ersten Bewerbung auf DIESE Stelle.
    """
    from app.models import Application, JobLog

    anker = {}
    aus_log = {}
    for eintrag in session.exec(select(JobLog).where(JobLog.eintrag.contains(BEWORBEN_MARKE))).all():
        if eintrag.created_at:
            bisher = aus_log.get(eintrag.job_id)
            if bisher is None or eintrag.created_at < bisher:
                aus_log[eintrag.job_id] = eintrag.created_at
    for app in session.exec(select(Application)).all():
        dt = _parse_dt(app.applied_date) or aus_log.get(app.job_id)
        if dt:
            anker[app.id] = dt
    return anker


def _upsert_contact(session, comp, job_id, c):
    if not c or not comp:
        return
    email = c.get("email")
    existing = None
    if email:
        existing = session.exec(select(Contact).where(Contact.email == email)).first()
        # P2-80: Ein Kontakt gleichen Namens bei derselben Firma, aber noch ohne Adresse (etwa aus
        # einem Gesprächs-Debrief), bekommt die Adresse nachgetragen statt einer Dublette daneben.
        # Ohne Adresse sucht Schritt 1b des Gmail-Checks nicht nach ihm.
        name = " ".join((c.get("name") or "").split()).lower()
        if not existing and name:
            for k in session.exec(select(Contact).where(Contact.company_id == comp.id)).all():
                if not k.email and " ".join((k.name or "").split()).lower() == name:
                    k.email = email
                    session.add(k)
                    return
    if not existing:
        session.add(Contact(company_id=comp.id, job_id=job_id, name=c.get("name"),
                            email=email, role=c.get("role"), notes=c.get("notes")))


def ingest_emails(records, run_type="email_check"):
    init_db()
    today = datetime.date.today().isoformat()
    records = sorted(records, key=lambda r: r.get("received_at") or "")
    with Session(engine) as s:
        run = Run(run_type=run_type, portals="Gmail", jobs_found=0)
        s.add(run)
        s.flush()

        seen_mid = {e.gmail_message_id for e in s.exec(select(Email)).all() if e.gmail_message_id}
        cache = {}
        # Zwei Anker (P2-17): die Bewerbung selbst ist der richtige Bezugspunkt, die Firma nur
        # die Rueckfallebene fuer Mails ohne Stellenzuordnung — siehe `anker_fuer_antwortzeit`.
        applied_je_bewerbung = {}   # application_id -> apply datetime
        applied_at = {}             # company_key -> earliest apply datetime (Rueckfallebene)

        # Anker aus bestehenden Bewerbungen vorbelegen
        applied_je_bewerbung.update(bewerbungs_anker(s))
        for app in s.exec(select(Application)).all():
            dt = _parse_dt(app.applied_date)
            job = s.get(Job, app.job_id)
            if job and job.company_id:
                comp = s.get(Company, job.company_id)
                if comp and dt:
                    k = comp.name.lower()
                    applied_at[k] = min(applied_at.get(k, dt), dt)

        new_emails = dup = responses = mehrdeutig = spaete_absagen = 0
        beworben_je_job = beworben_am_je_job(s)      # P2-48: Bewerbungszeitpunkt je Stelle
        for rec in records:
            mid = rec.get("gmail_message_id")
            if mid and mid in seen_mid:
                dup += 1
                continue
            if mid:
                seen_mid.add(mid)

            company = (rec.get("company") or "").strip()
            comp = _get_or_create_company(s, cache, company) if company else None
            # Anker-Schlüssel = die AUFGELÖSTE (kanonische) Firma, nicht der rohe Mail-Name —
            # sonst verfehlt die Antwortzeit-Berechnung den aus bestehenden Bewerbungen
            # vorbelegten Anker (Zeile ~131 oben), sobald eine Mail eine abweichende
            # Schreibweise nutzt (derselbe Fall wie oben, 22.07.2026).
            ck = comp.name.lower() if comp else (company.lower() if company else None)
            rec_dt = _parse_dt(rec.get("received_at"))
            direction = rec.get("direction") or "incoming"
            category = rec.get("category") or "Sonstige"

            # Job zuordnen oder anlegen. Bei _MEHRDEUTIG (Phase 61A) bewusst KEINEN neuen Job
            # anlegen — im Gegensatz zum Fall „kein Kandidat" (match is None): dort könnte die
            # Firma die Rolle schlicht noch nicht in der DB haben, hier dagegen IST einer der
            # bestehenden Jobs die richtige Stelle, wir wissen nur nicht welcher; ein dritter
            # Job wäre schlicht falsch. Die Mail bleibt firmenbezogen ohne Stelle (bestehender
            # „Ohne Stelle"-Pfad unten, job=None) und wird separat gezählt.
            match = _match_job(s, comp, rec.get("job_title")) if comp else None
            # Zweiter Anlauf ueber den Mailtext, wenn der Lauf keinen Titel liefern konnte
            # (s. `_match_job_im_volltext`). Nur bei statusveraendernden Kategorien — fuer
            # Rauschen lohnt der Netzwerkaufruf nicht — und nur, wenn wirklich kein Titel
            # im Record steht: Steht einer drin, hat `_match_job` bereits entschieden.
            if match is None and comp and not rec.get("job_title") and category in RESPONSE_CATS:
                match = _match_job_im_volltext(s, comp, rec.get("gmail_message_id"))
            ist_mehrdeutig = match is _MEHRDEUTIG
            job = None if ist_mehrdeutig else match
            if ist_mehrdeutig:
                mehrdeutig += 1
            # P2-48: spaete „Eingangsbestaetigung“ am Volltext gegenpruefen (s. dort). Nur fuer
            # eine ZUGEORDNETE Stelle sinnvoll — ohne sie gibt es keinen Bewerbungszeitpunkt.
            if job is not None and direction == "incoming" and spaete_absage_erkennen(
                    mid, category, rec_dt, beworben_je_job.get(job.id)):
                category = "Absage"
                rec = {**rec, "job_status": "Absage"}
                spaete_absagen += 1
                betreff = rec.get("subject") or "(kein Betreff)"
                # Das schließende Anführungszeichen steht bewusst als eigenes Literal:
                # im f-String stünde sonst ein ASCII-Quote als Schließer (P2-15).
                s.add(JobLog(job_id=job.id, art="auto", eintrag=(
                    f"Absage aus dem Mail-Volltext erkannt: „{betreff}" + "\u201c"
                    f" — als Eingangsbestätigung eingestuft, kam aber "
                    f"{(rec_dt - beworben_je_job[job.id]).days} Tage nach der Bewerbung")))

            if not job and not ist_mehrdeutig and comp and rec.get("job_title"):
                dk = N.dedup_key(comp.name, rec["job_title"])
                neuer_job = Job(
                    company_id=comp.id, company_name=comp.name, title=rec["job_title"],
                    portal="E-Mail", status=rec.get("job_status") or "Beworben",
                    found_date=today, dedup_key=dk,
                    source_note="aus Gmail erkannt " + today,
                )
                if flush_or_duplicate(s, lambda: s.add(neuer_job)):
                    job = neuer_job
                else:
                    # P2-3 (Phase 67F): dedup_key existiert bereits an einem Job, den _match_job
                    # (eigene, bewusst vorsichtigere Heuristik, P0-1-Fix Phase 61A) nicht als
                    # Treffer erkannt hat — die Mail trotzdem dem tatsächlichen Besitzer des
                    # Schlüssels zuordnen statt sie mit einem 500er abzubrechen oder eine echte
                    # zweite Dublette anzulegen.
                    job = s.exec(select(Job).where(Job.dedup_key == dk)).first()
                    if job and rec.get("job_status"):
                        job.status = rec["job_status"]
                        s.add(job)
            elif job and rec.get("job_status"):
                job.status = rec["job_status"]
                s.add(job)

            # Bewerbung sicherstellen (für gematchte/angelegte Jobs)
            app = None
            if job:
                app = s.exec(select(Application).where(Application.job_id == job.id)).first()
                if not app:
                    app = Application(job_id=job.id, status=rec.get("job_status") or "Beworben",
                                      applied_date=rec.get("applied_date"), channel="E-Mail",
                                      last_status_change=datetime.datetime.utcnow())
                    s.add(app)
                    s.flush()
                elif rec.get("job_status"):
                    app.status = rec["job_status"]
                    app.last_status_change = datetime.datetime.utcnow()
                    s.add(app)

            _upsert_contact(s, comp, job.id if job else None, rec.get("contact"))

            # Apply-Anker aktualisieren (ausgehende Mail = Bewerbung raus). Beide Ebenen
            # werden gepflegt: die Bewerbung, an der die Mail haengt, UND die Firma als
            # Rueckfallebene fuer Mails ohne Stellenzuordnung.
            applied_dt = _parse_dt(rec.get("applied_date"))
            if ck and rec_dt:
                if applied_dt:
                    applied_at[ck] = min(applied_at.get(ck, applied_dt), applied_dt)
                if direction == "outgoing":
                    applied_at[ck] = min(applied_at.get(ck, rec_dt), rec_dt)
            if app and rec_dt:
                if applied_dt:
                    applied_je_bewerbung[app.id] = min(
                        applied_je_bewerbung.get(app.id, applied_dt), applied_dt)
                if direction == "outgoing":
                    applied_je_bewerbung[app.id] = min(
                        applied_je_bewerbung.get(app.id, rec_dt), rec_dt)

            # Antwortzeit für eingehende Antworten
            rt = None
            is_response = direction == "incoming" and category in RESPONSE_CATS
            if is_response and rec_dt:
                anker = anker_fuer_antwortzeit(applied_je_bewerbung, applied_at,
                                               app.id if app else None, ck)
                rt = response_time_hours(rec_dt, anker)
            if is_response and rt is not None:
                responses += 1

            s.add(Email(
                application_id=app.id if app else None,
                company_id=comp.id if comp else None,
                job_id=job.id if job else None,
                gmail_thread_id=rec.get("gmail_thread_id"), gmail_message_id=mid,
                direction=direction, from_addr=rec.get("from_addr"), to_addr=rec.get("to_addr"),
                subject=rec.get("subject"), snippet=rec.get("snippet"),
                received_at=rec_dt, is_response=is_response, response_time_hours=rt,
                category=category, needs_reply=bool(rec.get("needs_reply")),
            ))
            new_emails += 1

        run.emails_checked = len(records)
        run.responses_found = responses
        run.finished_at = datetime.datetime.utcnow()
        run.summary = (f"{new_emails} Mails neu · {dup} Dubletten · {responses} Antworten mit Zeit · "
                       f"{mehrdeutig} mehrdeutig (ohne Stelle)"
                       + (f" · {spaete_absagen} späte Absage(n) am Volltext erkannt" if spaete_absagen else ""))
        s.add(run)
        s.commit()
        return {"new": new_emails, "dup": dup, "responses": responses, "mehrdeutig": mehrdeutig,
                "spaete_absagen": spaete_absagen,          # P2-48
                "total": len(records), "run_id": run.id}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Nutzung: python -m pipeline.gmail_ingest <emails.json>")
    with open(sys.argv[1], encoding="utf-8") as fh:
        recs = json.load(fh)
    print(json.dumps(ingest_emails(recs), ensure_ascii=False))
