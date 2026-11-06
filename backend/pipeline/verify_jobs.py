#!/usr/bin/env python3
"""Deterministischer URL-Prüfer für Job-Treffer — die mechanische Hälfte des
Vier-Augen-Prinzips (Phase 14).

Anlass (10.07.2026): Der Tageslauf ingestete 3 Treffer, alle drei fehlerhaft (Anzeige
abgelaufen / Deep-Link tot / hinter 403). Der Finder hatte die Probleme sogar in
`source_note` vermerkt — und trotzdem geschrieben. Eine Warnung im Freitext ist kein
Schutz; der Schutz ist ein Gate (Stufe B). Dieses Modul liefert den mechanischen Befund,
das zweite Augenpaar (Prüf-Subagent, Stufe C) urteilt darauf.

Arbeitsteilung: nur MECHANISCHE Fakten (HTTP-Status, finale URL nach Redirects,
Seitentext-Marker). Kein Scoring, keine DB-Änderung.

P2-75: LinkedIn drosselt die Abrufe je Anfrage (HTTP 429, gemessen: 3 von 12 bis 9 von 18
Abrufen, verstreut über den Lauf). Das ist eine Drosselung, keine Sperre — ein späterer Versuch
klappt. Deshalb wird NUR bei 429 wiederholt (403, Login-Wall, 404/410, Abgelaufen nicht): ein
Einzelabruf (`check_url`) direkt mit Pausen, ein Stapel (`check`, `bestand`) in Runden (erst
alle Adressen, dann nur die gedrosselten). So bleiben die Zusatzpausen je Lauf bei höchstens
35 s; die aufrufenden Skills geben dem Bash-Aufruf deshalb ein Zeitlimit von 300000 ms.

P2-76: Der Portal-Status („nimmt die Stelle noch Bewerbungen an?") kommt aus diesem Abruf statt aus
WebFetch (`portal_status`, CLI `portal`). Dafür gelten drei Regeln:
  * Ein Portal, das die Verbindung annimmt und dann nicht antwortet (`httpx.ReadTimeout`) oder sie
    ohne Antwort schließt (`httpx.RemoteProtocolError`), bremst automatische Abrufe aus (StepStone).
    Das ist `NICHT_PRUEFBAR`, nicht `TOT` — „tot" nur, wenn bestätigt (P2-4). Scheitert schon der
    Verbindungsaufbau (`ConnectError`, `ConnectTimeout`) oder gibt es eine andere Zeitüberschreitung,
    bleibt es `TOT`.
  * `BESETZT_TEXT_MARKERS` kennt auch die deutsche LinkedIn-Fassung („keine Bewerbungen mehr
    angenommen"). Eine geschlossene Anzeige, die LinkedIn noch zeigt, ist so `ABGELAUFEN`, trägt
    aber ihren Text (`anzeigentext`), wenn Titel und Firma noch auf der Seite stehen.
  * Der Bot-Schutz wird nie umgangen: keine anderen Kennungen, kein HTTP/2-Trick.

CLI (aus backend/):
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.verify_jobs check <records.json>
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.verify_jobs bestand [--status "Neu,Prüfen"]
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.verify_jobs portal <job_id> [<job_id> …]

Ausgabe: JSON auf stdout (Zusammenfassung; bei `portal` eine Liste je Stelle) + Report-Datei (nicht
bei `portal`: nur lesend, schreibt weder Datenbank noch Dateien). Fehler: Klartext auf stderr, Exit 2.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl, urlencode

import httpx

from app.db import engine, init_db
from app.models import Job
from app.naming import dated_filename
from pipeline import bewerbungssprache
from pipeline import gmail_client   # _entkleiden wiederverwenden (kein Duplikat)

from sqlmodel import Session, select

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent   # Bewerbung_Mgmt_System/

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
_HEADERS = {"User-Agent": _UA, "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}

# Marker in der FINALEN URL → Anzeige abgelaufen (Redirect kann trotz HTTP 200 kommen!).
EXPIRED_URL_MARKERS = (
    "expired_jd_redirect", "job-not-found", "jobnotfound", "job_not_found",
    "jobclosed", "job-closed", "no-longer-available", "position-closed", "job_expired",
)
# Marker im SEITENTEXT → Stelle nicht mehr offen.
BESETZT_TEXT_MARKERS = (
    "no longer accepting applications", "no longer available", "this job is no longer",
    "position has been filled", "position is now closed", "job has expired",
    "nicht mehr verfügbar", "nicht mehr verfuegbar", "stelle wurde besetzt",
    "stelle ist besetzt", "diese stelle ist nicht mehr", "leider ist diese",
    "diese anzeige ist abgelaufen", "anzeige ist nicht mehr", "bewerbung nicht mehr möglich",
    # P2-76: LinkedIn auf Deutsch („Es werden keine Bewerbungen mehr angenommen.") — der Abruf läuft
    # mit Accept-Language de-DE, die englische Fassung oben greift dort nicht; dazu die Formulierung,
    # die die Skills bisher als einzigen Marker kannten.
    "keine bewerbungen mehr angenommen", "nimmt keine bewerbungen mehr entgegen",
)
# Login-Wall-Indikatoren.
LOGIN_MARKERS = (
    "sign in to view", "sign in to see", "join now to see", "join linkedin",
    "sign in", "anmelden, um", "jetzt anmelden", "log in to continue", "melde dich an",
    "create your account", "sign up to see",
)

# P2-93: dieselben Marker für Französisch, Italienisch, Spanisch, Portugiesisch aus der Sprachtabelle
# (`bewerbungssprache`). Die DE-/EN-Listen oben bleiben unverändert und stehen vorn, ein bisheriger
# Treffer behält also seinen Beleg. Beide Listen sind enger gefasst als der bloße Landessatz: Ein
# Besetzt-Marker schlägt im Seitentext alles (auch den Titel), darum kein Marker, der auf offenen
# Anzeigen vorkommt („le plus disponible“, „sesión ha caducado“). Die Login-Marker greifen ohnehin nur
# ohne Titel und Firma (`check_url`, b) und stehen auch auf offenen Seiten (Anmelde-Hinweis im Kopf).
_BESETZT_ALLE = BESETZT_TEXT_MARKERS + bewerbungssprache.alle_marker("geschlossen")
_LOGIN_ALLE = LOGIN_MARKERS + bewerbungssprache.alle_marker("login")

_STOP = {"of", "and", "the", "for", "to", "in", "at", "on", "der", "die", "das", "und",
         "für", "fuer", "im", "mit", "von", "de", "en", "us", "job", "jobs", "career", "careers"}
_LEGAL = {"gmbh", "ag", "inc", "ltd", "llc", "co", "kg", "se", "plc", "sa", "bv", "oy",
          "corp", "corporation", "group", "gruppe", "holding", "deutschland", "germany"}


def _die(msg: str) -> "NoReturn":       # noqa: F821
    print(msg, file=sys.stderr)
    raise SystemExit(2)


def _tokens(s: str) -> list:
    """Signifikante Wörter (≥3 Zeichen, keine Stopwörter), klein."""
    return [w for w in re.findall(r"[A-Za-zÄÖÜäöüß0-9]+", (s or "").lower())
            if len(w) >= 3 and w not in _STOP]


def _company_tokens(company: str) -> list:
    return [t for t in _tokens(company) if t not in _LEGAL]


# P2-13 (Phase 67D): Query-Parameter, die NICHT die Identität der Anzeige tragen (Tracking/
# Locale/Suchkontext) — aus der Live-DB abgeleitet (11 Bestands-URLs mit '?', Stand 26.07.2026,
# s. Abschlussbericht Phase 67D für die volle Beleg-Tabelle je Parameter) + den im Review
# genannten generischen Familien (utm_*, gh_src, ref, source). Im Zweifel großzügig aufgenommen
# — lieber einen Redirect übersehen als eine gute Anzeige fälschlich blockieren:
#   lang/language     Sprachauswahl (eine Karriereseite "?lang=en-us", Personio "?language=de",
#                      njoyn "&lang=4") — dieselbe Anzeige, nur andere Anzeigesprache.
#   trackingId/        LinkedIn-Klick-Analytics ("?alternateChannel=search&trackingId=…") —
#   alternateChannel   die Job-Identität steht bei LinkedIn bereits im PFAD (/jobs/view/<id>/).
#   q/l/radius/sort/   Indeed-Suchkontext ("/jobs?q=…&l=…&radius=…&sort=…&fromage=…&vjk=…") —
#   fromage            beschreibt die SUCHE, nicht die einzelne Anzeige.
#   locations          Workday-Suchfilter (GUID-Liste in der Such-URL), analog.
#   workerSubType      Workday-interne Worker-Typ-Kennung, an einer bereits über den Pfad
#                      (REQ-Nummer) identifizierten Anzeige — kein Identitätsmerkmal.
#   page/countryID     njoyn-Navigations-/Filter-Parameter neben der eigentlichen Mandanten-ID.
# NICHT gestrichen (identitätstragend): "jk"/"vjk" (Indeed-Job-Key — genau der Fall "Job-ID nur
# in der Query", für den dieser Fix gebaut wurde) und "CLID" (njoyn-Mandant).
_TRACKING_QUERY_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id", "utm_name",
    "gh_src", "ref", "source", "src",
    "gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "igshid", "_hsenc", "_hsmi", "mkt_tok",
    "lang", "language", "trackingid", "alternatechannel",
    "q", "l", "radius", "sort", "fromage", "locations", "workersubtype", "page", "countryid",
}


def _clean_query_pairs(query: str) -> list:
    """(key, value)-Paare OHNE Tracking-/Locale-/Suchkontext-Parameter (_TRACKING_QUERY_PARAMS),
    sortiert — Reihenfolge-Unterschiede zwischen Original- und finaler URL sollen keinen
    künstlichen Unterschied erzeugen."""
    return sorted((k, v) for k, v in parse_qsl(query, keep_blank_values=True)
                  if k.lower() not in _TRACKING_QUERY_PARAMS)


def _norm_url(u: str) -> str:
    """Scheme+Host+Pfad (ohne Trailing-Slash) + bereinigte Query — für Redirect-Erkennung.

    Bis Phase 67D (P2-13) wurde die Query komplett verworfen: Portale, die die Job-ID NUR in
    der Query führen (z. B. Indeed „?jk=…"/„?vjk=…"), konnten so eine abgelaufene Anzeige als
    OK durchrutschen lassen, wenn der Redirect auf denselben Pfad, aber mit anderer/fehlender
    Job-ID-Query ging — `redirected` blieb `False`. Tracking-/Locale-/Suchkontext-Parameter
    werden vorher entfernt (`_clean_query_pairs`), sonst gälte jede Anzeige mit UTM-/
    Sprachparametern fälschlich als „umgeleitet"."""
    p = urlsplit(u or "")
    base = f"{p.scheme.lower()}://{p.netloc.lower()}{p.path.rstrip('/')}"
    query = urlencode(_clean_query_pairs(p.query))
    return f"{base}?{query}" if query else base


def _last_path_segment(u: str) -> str:
    path = urlsplit(u or "").path.rstrip("/")
    return path.rsplit("/", 1)[-1] if "/" in path else path


def _snippet(text: str, needles, width: int = 180) -> str:
    low = text.lower()
    for n in needles:
        i = low.find(n)
        if i >= 0:
            start = max(0, i - 40)
            return re.sub(r"\s+", " ", text[start:start + width]).strip()
    return re.sub(r"\s+", " ", text[:width]).strip()


def _title_ratio(text_low: str, title: str) -> tuple:
    """(Anteil vorhandener Titel-Tokens, Liste der vorhandenen Tokens)."""
    toks = _tokens(title)
    if not toks:
        return 0.0, []
    present = [t for t in toks if t in text_low]
    return len(present) / len(toks), present


_LINKEDIN_DESC_RE = re.compile(
    r'<div[^>]*class="[^"]*(?:show-more-less-html__markup|description__text)[^"]*"[^>]*>(.*?)</div>',
    re.S | re.I)


def _anzeigen_kern(html_roh: str, volltext: str) -> str:
    """Der EIGENTLICHE Anzeigentext für den Snapshot (Fix 07.08.2026, Echtfall):
    LinkedIn liefert ohne Login die komplette Seiten-Chrome mit — Cookie-Banner, dreifaches
    Login-Formular, „Ähnliche Jobs", SEO-Listen, Sprach-Footer. `entkleiden()` entfernt nur
    Markup, keinen Boilerplate; der Basis-Snapshot zeigte dadurch ~80 % Müll und die eigentliche
    Anzeige begraben in der Mitte. LinkedIn-Guest-Seiten tragen den Anzeigentext seit Jahren
    stabil im Container `show-more-less-html__markup` (bzw. `description__text`) — den schneiden
    wir aus dem ROHEN HTML und entkleiden nur ihn. Greift der Schnitt nicht (anderes Portal,
    Markup-Änderung, verdächtig kurzer Treffer), bleibt der bisherige Volltext der ehrliche
    Fallback — nie stillschweigend Inhalt verlieren. Die VERFÜGBARKEITS-Prüfungen in check_url()
    laufen bewusst weiter über den Volltext: Besetzt-/Login-Marker stehen AUSSERHALB des
    Beschreibungs-Containers."""
    m = _LINKEDIN_DESC_RE.search(html_roh)
    if not m:
        return volltext
    kern = gmail_client._entkleiden(m.group(1))
    if len(kern) < 300:          # verdächtig kurz — lieber der volle Text als ein Fragment
        return volltext
    return kern


# P2-75: Wiederholung bei HTTP 429 (Rate-Limit). Alle Pausen laufen über `_schlafen`, damit
# Tests sie ersetzen können (nie echt warten) — auch der 0,5-s-Abstand zwischen zwei Adressen.
_schlafen = time.sleep
# Einzelabruf: Pausen in Sekunden vor Versuch 2/3/4 (Messung 14.10.2026: von 29 gedrosselten
# Abrufen klappten 17 sofort, 6 nach 3 s und die letzten 6 nach weiteren 8 s). `Retry-After`
# des Servers (ganze Sekunden bis `_RETRY_AFTER_MAX`) ersetzt die jeweilige Pause.
_PAUSEN_429 = (3, 8, 20)
_RETRY_AFTER_MAX = 30
# Stapel: Pausen in Sekunden vor Runde 2/3/4 (Messung: 9 → 2 → 0 gedrosselte Adressen von 24).
_RUNDEN_PAUSEN = (5, 10, 20)
_ABSTAND = 0.5      # kein Hammering: Pause zwischen zwei Adressen innerhalb einer Runde


def _pause_429(r, nr: int) -> float:
    """Pause vor dem nächsten Versuch nach einer 429-Antwort `r`; `nr` zählt ab 0. Ein
    `Retry-After` als ganze Sekunden ≤ `_RETRY_AFTER_MAX` ersetzt die Liste, alles andere
    (Datumsangabe, Unsinn, zu lang) wird ignoriert."""
    headers = getattr(r, "headers", None)
    wert = str(headers.get("Retry-After") or "").strip() if headers is not None else ""
    if re.fullmatch(r"[0-9]{1,4}", wert) and int(wert) <= _RETRY_AFTER_MAX:
        return int(wert)
    return _PAUSEN_429[nr]


def _beleg_429(versuche: int) -> str:
    """Beleg für ein 429, das auch nach allen Versuchen blieb (bei einem Versuch: Altwortlaut)."""
    if versuche > 1:
        return f"HTTP 429 nach {versuche} Versuchen (Rate-Limit)"
    return "HTTP 429 (Bot-Block/Rate-Limit)"


def _ist_rate_limit(pr: dict) -> bool:
    """Wahr, wenn der Befund NUR an der Drosselung hängt (wiederholungswürdig). Ein 429 mit
    Abgelaufen-Marker oder generischem Redirect hat einen eigenen Befund und zählt nicht."""
    return pr.get("http_status") == 429 and pr.get("befund") == "NICHT_PRUEFBAR"


def check_url(url: str, company: str, title: str, return_text: bool = False,
              wiederholen: bool = True) -> dict:
    """Mechanischer Befund zu EINER URL. Kein DB-Zugriff, keine Bewertung der Passung.

    P2-75: Bei HTTP 429 wird mit Pausen `_PAUSEN_429` (bzw. `Retry-After`) bis zu dreimal
    wiederholt, derselbe Client, bewertet wird die LETZTE Antwort. Bleibt es bei 429 →
    `NICHT_PRUEFBAR` mit Beleg „HTTP 429 nach 4 Versuchen". Nur 429 löst eine Wiederholung aus.
    `wiederholen=False` = genau ein Versuch (so ruft der Stapel in `_abrufen_in_runden` auf).
    Jedes Ergebnis außer `KEINE_URL` trägt `versuche` (1 = ohne Wiederholung).

    P2-76: `httpx.ReadTimeout` (Verbindung steht, keine Antwort) und `httpx.RemoteProtocolError`
    (Verbindung ohne Antwort beendet) sind `NICHT_PRUEFBAR` mit eigenem Beleg — das Portal bremst
    automatische Abrufe aus, die Anzeige lebt vermutlich. Alle übrigen Zeitüberschreitungen und
    Verbindungsfehler bleiben `TOT`.

    `return_text=True` (Phase 38): der beim Live-Check ohnehin geladene, entkleidete
    Seitentext landet als `anzeigentext` im Ergebnis (bei Befund OK/INHALT_UNKLAR, seit P2-76
    auch bei `ABGELAUFEN` durch einen Seitentext-Marker, wenn Titel ≥ 60 % und Firma noch im Text
    stehen — der Befund bleibt `ABGELAUFEN`; bei einer Umleitung/URL-Marker nie Text),
    Cap 20.000 Zeichen — Basis für `posting_snapshot.render_basis()`. Seit dem Fix vom
    07.08.2026 ist das bei LinkedIn-Guest-Seiten der geschnittene Anzeigen-KERN statt der
    ganzen Seite (s. `_anzeigen_kern`). Der Prüf-Subagent (Stufe C der Vier-Augen-
    Verifikation) bekommt diesen Text NIE zu sehen; `check()` poppt ihn vor dem Schreiben
    der `_verify.json` wieder heraus."""
    if not url or not url.strip():
        return {"befund": "KEINE_URL", "http_status": None, "final_url": None,
                "beleg": "Record ohne url-Feld"}

    versuche = 0
    try:
        with httpx.Client(follow_redirects=True, timeout=20.0, headers=_HEADERS) as cl:
            while True:
                versuche += 1
                r = cl.get(url)
                # P2-75: nur ein 429 wird wiederholt. Bewertet wird erst die letzte Antwort
                # (unten) — ein 429 mit Abgelaufen-Marker/generischem Redirect behält so seinen
                # eigenen Befund, kostet höchstens die Wartezeit.
                if not (wiederholen and r.status_code == 429 and versuche <= len(_PAUSEN_429)):
                    break
                _schlafen(_pause_429(r, versuche - 1))
    except httpx.ReadTimeout:
        # P2-76: Verbindung steht, dann kommt nichts — das Portal bremst automatische Abrufe aus.
        # Vor `TimeoutException`, weil `ReadTimeout` eine davon ist.
        return {"befund": "NICHT_PRUEFBAR", "http_status": None, "final_url": None,
                "beleg": "Keine Antwort nach 20 s (das Portal bremst automatische Abrufe vermutlich aus)",
                "versuche": versuche}
    except httpx.RemoteProtocolError:
        # P2-76: Verbindung ohne Antwort beendet — dieselbe Lage in der anderen Form.
        return {"befund": "NICHT_PRUEFBAR", "http_status": None, "final_url": None,
                "beleg": "Verbindung ohne Antwort beendet (das Portal blockiert automatische Abrufe vermutlich)",
                "versuche": versuche}
    except httpx.TimeoutException:
        return {"befund": "TOT", "http_status": None, "final_url": None,
                "beleg": "Timeout nach 20 s", "versuche": versuche}
    except httpx.RequestError as e:
        # DNS-/Verbindungsfehler o. ä.
        return {"befund": "TOT", "http_status": None, "final_url": None,
                "beleg": f"Netzfehler: {type(e).__name__}"[:200], "versuche": versuche}

    status = r.status_code
    final_url = str(r.url)
    low_final = final_url.lower()
    redirected = _norm_url(url) != _norm_url(final_url)
    out = {"http_status": status, "final_url": final_url, "versuche": versuche}

    # Reihenfolge ist Absicht — der erste Treffer gewinnt.
    # 1) hart tot
    if status in (404, 410):
        return {**out, "befund": "TOT", "beleg": f"HTTP {status}"}
    # 2) Abgelaufen-Marker in der finalen URL (Redirect kann trotz 200 passieren)
    for m in EXPIRED_URL_MARKERS:
        if m in low_final:
            return {**out, "befund": "ABGELAUFEN", "beleg": f"finale URL enthält '{m}'"}
    # 3) Redirect auf generische Seite: das identitätstragende Merkmal der Original-URL fehlt
    # komplett in der finalen URL — entweder der letzte Pfad-Teil ODER (P2-13, Phase 67D) einer
    # ihrer identitätstragenden Query-Werte. Portale wie Indeed führen die Job-ID NUR in der
    # Query („?jk=…"), auf einem generischen, geteilten Pfad — ohne diesen zweiten Zweig würde
    # `redirected` zwar korrekt True (Query jetzt Teil des Vergleichs), aber der Pfad-Teil-Check
    # allein könnte nie greifen (derselbe generische Pfad bleibt ja bestehen). Erst wenn ALLE
    # eigenen (nicht-Tracking-)Query-Werte verschwunden sind, gilt die Query-Identität als
    # verloren — großzügig: ein einzelner überlebender Wert genügt als Gegenbeweis.
    seg = _last_path_segment(url)
    verloren = seg if (seg and seg.lower() not in low_final) else None
    if not verloren:
        query_werte = [v for _, v in _clean_query_pairs(urlsplit(url).query) if v]
        if query_werte and all(v.lower() not in low_final for v in query_werte):
            verloren = query_werte[0]
    if redirected and verloren:
        return {**out, "befund": "UMGELEITET_GENERISCH",
                "beleg": f"Redirect: '{verloren}' fehlt in finaler URL {final_url}"[:200]}
    # 4) Bot-Block / Rate-Limit (ein 429 steht hier erst, wenn alle Versuche aufgebraucht sind)
    if status == 429:
        return {**out, "befund": "NICHT_PRUEFBAR", "beleg": _beleg_429(versuche)}
    if status == 403:
        return {**out, "befund": "NICHT_PRUEFBAR", "beleg": f"HTTP {status} (Bot-Block/Rate-Limit)"}
    # nur 200 wird inhaltlich geprüft; alles andere (5xx …) ist nicht verlässlich prüfbar
    if status != 200:
        return {**out, "befund": "NICHT_PRUEFBAR", "beleg": f"HTTP {status}"}

    # 5) Seitentext auswerten
    text = gmail_client._entkleiden(r.text[:300000])
    low = text.lower()
    # Titel-/Firmen-Abgleich (für a, b, c und d)
    ratio, present = _title_ratio(low, title)
    has_company = any(t in low for t in _company_tokens(company))
    # a) Besetzt-Marker
    for m in _BESETZT_ALLE:
        if m in low:
            out2 = {**out, "befund": "ABGELAUFEN", "beleg": f"Seitentext: '{m}' — {_snippet(text, [m])}"[:200]}
            # P2-76: „Geschlossen" heißt nicht „Text weg" — zeigt die Seite Titel und Firma der Stelle
            # noch, bekommt der Aufrufer den Anzeigentext trotzdem (Befund bleibt ABGELAUFEN).
            if return_text and ratio >= 0.6 and has_company:
                out2["anzeigentext"] = _anzeigen_kern(r.text[:300000], text)[:20000]
            return out2
    # b) Login-Wall: Sign-in-Dominanz, kein Stellentext
    if any(m in low for m in _LOGIN_ALLE) and ratio < 0.3 and not has_company:
        return {**out, "befund": "LOGIN_WALL", "beleg": f"Sign-in-Seite, Titel/Firma fehlen — {_snippet(text, _LOGIN_ALLE)}"[:200]}
    # c) Titel ≥ 60 % + Firma im Text
    if ratio >= 0.6 and has_company:
        out2 = {**out, "befund": "OK", "beleg": f"Titel {ratio:.0%} + Firma im Text — {_snippet(text, present)}"[:200]}
        if return_text:
            out2["anzeigentext"] = _anzeigen_kern(r.text[:300000], text)[:20000]
        return out2
    # d) sonst unklar
    out2 = {**out, "befund": "INHALT_UNKLAR",
            "beleg": f"Titel {ratio:.0%}, Firma {'ja' if has_company else 'nein'} — {_snippet(text, present or [title])}"[:200]}
    if return_text:
        out2["anzeigentext"] = _anzeigen_kern(r.text[:300000], text)[:20000]
    return out2


def portal_status(pr: dict) -> str:
    """P2-76: Portal-Status einer Stelle aus dem Befund von `check_url` — rein, ohne Abruf.

    `offen`        Befund `OK`.
    `geschlossen`  `ABGELAUFEN`, `UMGELEITET_GENERISCH` und `TOT` mit HTTP 404/410 (die Seite
                   gibt es nicht mehr).
    `unklar`       alles andere: `NICHT_PRUEFBAR` (Bot-Schutz, Drosselung), `LOGIN_WALL`,
                   `INHALT_UNKLAR`, `TOT` ohne Status (Netzfehler sagt nichts über die Anzeige),
                   `KEINE_URL`. Der Skill fragt dann ein zweites Mal anders nach (WebFetch)."""
    befund = pr.get("befund")
    if befund == "OK":
        return "offen"
    if befund in ("ABGELAUFEN", "UMGELEITET_GENERISCH"):
        return "geschlossen"
    if befund == "TOT" and pr.get("http_status") in (404, 410):
        return "geschlossen"
    return "unklar"


def _summary(befunde) -> dict:
    s = {}
    for b in befunde:
        s[b] = s.get(b, 0) + 1
    return s


def _abrufen_in_runden(ziele, return_text: bool = False) -> list:
    """P2-75: `ziele` = [(url, firma, titel), …] → eine Prüfung je Ziel, gleiche Reihenfolge.

    Runde 1 ruft ALLE Adressen mit genau einem Versuch ab (`wiederholen=False`, 0,5 s Abstand).
    Adressen, die nur an der Drosselung (429) hängen, kommen in bis zu drei weitere Runden —
    Pause `_RUNDEN_PAUSEN` vor Runde 2/3/4, wieder 0,5 s Abstand innerhalb der Runde. Das
    Ergebnis der LETZTEN Runde mit Abruf zählt; `versuche` = Zahl dieser Runden. Bleibt eine
    Adresse bei 429, trägt sie den Beleg „nach N Versuchen". Ein Text (`return_text`), der erst
    in einer späteren Runde kommt, liegt wie sonst im Ergebnis (`anzeigentext`)."""
    ergebnisse = [None] * len(ziele)
    versuche = [0] * len(ziele)
    offen = list(range(len(ziele)))
    for runde in range(len(_RUNDEN_PAUSEN) + 1):
        if runde:
            _schlafen(_RUNDEN_PAUSEN[runde - 1])
        for pos, i in enumerate(offen):
            if pos:
                _schlafen(_ABSTAND)
            url, firma, titel = ziele[i]
            pr = check_url(url, firma, titel, return_text=return_text, wiederholen=False)
            if "versuche" in pr:            # KEINE_URL hat keinen Abruf
                versuche[i] += 1
                pr["versuche"] = versuche[i]
            ergebnisse[i] = pr
        offen = [i for i in offen if _ist_rate_limit(ergebnisse[i])]
        if not offen:
            break
    for i in offen:                          # nach der letzten Runde noch gedrosselt
        if versuche[i] > 1:
            ergebnisse[i]["beleg"] = _beleg_429(versuche[i])
    return ergebnisse


def _kennzahlen_wiederholen(prueferg) -> dict:
    """Zusammenfassungsfelder zur Wiederholung: Adressen mit mehr als einem Versuch und
    Adressen, die am Ende noch gedrosselt waren."""
    return {"wiederholt": sum(1 for pr in prueferg if pr.get("versuche", 0) > 1),
            "rate_limit_offen": sum(1 for pr in prueferg if _ist_rate_limit(pr))}


def check(records_path: str) -> dict:
    """records.json (Ingest-Schema) prüfen → <name>_verify.json mit pruefung-Block je Record.

    Phase 38: fängt nebenbei den beim Live-Check ohnehin geladenen Anzeigentext ein und
    schreibt ihn in eine ZWEITE Datei `<name>_texte.json` ({url: text}) — für
    `pipeline.ingest --texte`, das daraus einen Basis-Snapshot bei der Erfassung baut.
    Die `_verify.json` bleibt bewusst unverändert (Format-identisch zu vor Phase 38): der
    Prüf-Subagent (zweites Augenpaar) bekommt nie Volltexte vorgesetzt, nur den Befund.

    P2-75: gedrosselte Adressen (HTTP 429) werden in Runden nachgeholt (`_abrufen_in_runden`).
    Neu in der `_verify.json` ist nur `pruefung.versuche`; die Zusammenfassung meldet zusätzlich
    `wiederholt` (Adressen mit mehr als einem Versuch) und `rate_limit_offen` (am Ende noch 429)."""
    p = Path(records_path)
    if not p.exists():
        _die(f"{records_path} nicht gefunden.")
    records = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        _die("records.json muss eine Liste von Objekten sein.")

    out_records, befunde, texte = [], [], {}
    prueferg = _abrufen_in_runden(
        [(rec.get("url"), rec.get("company"), rec.get("title")) for rec in records],
        return_text=True)
    for rec, pr in zip(records, prueferg):
        pr["beleg"] = (pr.get("beleg") or "")[:200]
        anzeigentext = pr.pop("anzeigentext", None)
        if anzeigentext and rec.get("url"):
            texte[rec["url"]] = anzeigentext
        out_records.append({**rec, "pruefung": pr})
        befunde.append(pr["befund"])

    out_path = p.with_name(p.stem + "_verify.json")
    out_path.write_text(json.dumps(out_records, ensure_ascii=False, indent=2), encoding="utf-8")
    texte_path = p.with_name(p.stem + "_texte.json")
    texte_path.write_text(json.dumps(texte, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"geprueft": len(records), "datei": str(out_path), "texte": len(texte),
            "texte_datei": str(texte_path), **_kennzahlen_wiederholen(prueferg),
            **_summary(befunde)}


def bestand(status_csv: str) -> dict:
    """DB-Bestand prüfen (read-only) → data/exports/<datum>_URL_Check.json + Tabelle.

    P2-75: wie `check()` in Runden bei HTTP 429; die Zusammenfassung trägt zusätzlich
    `wiederholt` und `rate_limit_offen`."""
    init_db()
    stat = [s.strip() for s in (status_csv or "").split(",") if s.strip()]
    with Session(engine) as s:
        q = select(Job).where(Job.deleted_at.is_(None))   # Phase 32 B — Tombstones nicht mitprüfen
        if stat:
            q = q.where(Job.status.in_(stat))
        jobs = list(s.exec(q).all())

    rows, befunde = [], []
    printable = []
    prueferg = _abrufen_in_runden([(j.url, j.company_name, j.title) for j in jobs])
    for j, pr in zip(jobs, prueferg):
        pr["beleg"] = (pr.get("beleg") or "")[:200]
        rows.append({"id": j.id, "company": j.company_name, "title": j.title,
                     "url": j.url, "status": j.status, "pruefung": pr})
        befunde.append(pr["befund"])
        printable.append((j.id, (j.company_name or "")[:24], pr["befund"]))

    out_dir = PROJECT_ROOT / "data" / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / dated_filename("URL_Check", "json")
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    # Tabelle auf stderr, damit stdout reines JSON bleibt.
    print(f"\n{'ID':>4}  {'Firma':<24}  Befund", file=sys.stderr)
    print("-" * 52, file=sys.stderr)
    for jid, comp, bef in printable:
        print(f"{jid:>4}  {comp:<24}  {bef}", file=sys.stderr)

    return {"geprueft": len(jobs), "status": stat, "datei": str(out_path.relative_to(PROJECT_ROOT)),
            **_kennzahlen_wiederholen(prueferg), **_summary(befunde)}


def portal(job_ids) -> list:
    """P2-76: Portal-Status einzelner Stellen der Datenbank — NUR LESEND (keine Schreibzugriffe auf
    Datenbank oder Dateien; das Rückschreiben von `portal_closed`/`availability_status` bleibt bei
    den Skills).

    `job_ids` = IDs in der gewünschten Reihenfolge (doppelte IDs zählen einmal). Nicht gelöschte
    Stellen werden über `_abrufen_in_runden` abgerufen (Wiederholung bei HTTP 429 in Runden,
    P2-75). Rückgabe: eine Liste, je ID ein Eintrag `{job_id, url, portal, befund, beleg,
    http_status, versuche}`. Eine unbekannte oder gelöschte ID ergibt Befund `UNBEKANNT`, Portal
    `unklar` und `versuche` 0, ohne Abruf; eine Stelle ohne URL ergibt `KEINE_URL` (ebenfalls
    `versuche` 0, kein Abruf)."""
    ids = list(dict.fromkeys(int(i) for i in job_ids))
    init_db()
    with Session(engine) as s:
        q = select(Job).where(Job.id.in_(ids), Job.deleted_at.is_(None))   # Tombstones sind „unbekannt"
        stellen = {j.id: (j.url, j.company_name, j.title) for j in s.exec(q).all()}

    gefunden = [i for i in ids if i in stellen]
    abrufe = dict(zip(gefunden, _abrufen_in_runden([stellen[i] for i in gefunden])))

    ergebnis = []
    for jid in ids:
        if jid not in abrufe:
            ergebnis.append({"job_id": jid, "url": None, "portal": "unklar", "befund": "UNBEKANNT",
                             "beleg": "Stelle nicht gefunden", "http_status": None, "versuche": 0})
            continue
        pr = abrufe[jid]
        ergebnis.append({"job_id": jid, "url": stellen[jid][0], "portal": portal_status(pr),
                         "befund": pr["befund"], "beleg": (pr.get("beleg") or "")[:200],
                         "http_status": pr.get("http_status"), "versuche": pr.get("versuche", 0)})
    return ergebnis


def main() -> None:
    ap = argparse.ArgumentParser(prog="pipeline.verify_jobs", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_c = sub.add_parser("check", help="records.json vor dem Ingest prüfen")
    p_c.add_argument("records_json")

    p_b = sub.add_parser("bestand", help="DB-Bestand prüfen (read-only)")
    p_b.add_argument("--status", default="Neu,Prüfen", help='Komma-Liste, Default "Neu,Prüfen"')

    p_p = sub.add_parser("portal", help="Portal-Status einzelner Stellen (nur lesend, P2-76)")
    p_p.add_argument("job_ids", nargs="+", type=int, metavar="job_id")

    a = ap.parse_args()
    if a.cmd == "check":
        out = check(a.records_json)
    elif a.cmd == "portal":
        out = portal(a.job_ids)
    else:
        out = bestand(a.status)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
