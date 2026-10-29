"""Gesamtprozess-KPIs seit Beginn — EINE Berechnung für Dashboard UND Excel-Export (Phase 69,
Stufe A). Vorbild ist ausdrücklich `app/response_metrics.py` (Phase 67B, P2-7): die dort gemachte
Erfahrung — dieselbe Formel lebte einmal in main.py und einmal in export_excel.py und driftete
auseinander — gilt hier ab Tag 1. Genau EIN Ort für alle vier KPI-Formeln; `/api/dashboard`
(Stufe B) und `pipeline/export_excel.py` (Stufe C) rufen dieselben vier Funktionen auf.

Wunsch vom 27.07.2026 (s. tasks/spec_phase69_gesamtprozess_kpis.md): das Dashboard soll den
GESAMTEN Bewerbungsprozess zeigen, nicht nur die Ausschreibungs-Pipeline — inklusive der frühen
Netzwerk-Phase (Outreach-Tracker). Vier KPIs:
  1. Bewerbungen gesamt  (Ausschreibungen + Netzwerk)
  2. Gespräche gesamt    (Interview + NetzwerkGespraech, inkl. Gegenüber-/vor-Ort-Split)
  3. Absagen gesamt      (Job-Absage + Outreach Closed Negative)
  4. Keine Reaktion      (Schwelle KEINE_REAKTION_TAGE, mit Row-Listen fürs Aufrollen)

BEWUSST reine Funktionen ohne DB-/FastAPI-Import (Muster response_metrics.py): `export_excel.py`
läuft als eigenständiges CLI (`refresh_views.sh`) und darf NICHT die ganze FastAPI-App
importieren. Dieses Modul importiert deshalb nichts aus `app.main`, nur Stdlib, und nimmt
bereits geladene Row-Listen entgegen (Application/Job/Outreach/Interview/NetzwerkGespraech/
Email) statt selbst aus der DB zu lesen.

Rückgabeform je Funktion: {"wert": int, "splits": dict, "rows": list[dict]}. `rows` sind bewusst
kompakte dicts (`id`, `label`, `kanal`, `tage`) — genug fürs Aufrollen in der UI (Stufe B), ohne
dass dieses Modul selbst Firmen-/Job-Objekte nachlädt (das bliebe eine reine Funktion). `tage`
ist nur bei "Keine Reaktion" inhaltlich belegt (Tage seit letzter Aktivität); bei den anderen drei
KPIs bleibt es `None` — die Feldform ist trotzdem überall gleich, das hält Aufrufer/UI einfach.

Datums-Parsing ist überall defensiv: Outreach-Daten sind teils Freitext (s. Spec-Fallstricke),
ein unparsebares Datum zählt schlicht nicht für die 14-Tage-Schwelle — es crasht nie.
"""
from datetime import date, datetime
from typing import Iterable, Optional

# Phase 70 — `funnel_kpi()` (unten) ruft `response_kpis()` auf statt die Formel neu zu bauen.
# response_metrics.py ist wie dieses Modul App-frei (kein DB-/FastAPI-Import), der Import auf
# Modulebene ist deshalb unbedenklich (s. Spec-Punkt 1: "response_metrics darf importiert
# werden — beides sind App-freie Kennzahl-Module").
from app.response_metrics import response_kpis

# Schwelle für "Keine Reaktion" — bewusst eine Konstante im Modul, KEIN Setting (Spec-Entscheidung
# 2): erst bei echtem Bedarf konfigurierbar machen, nicht vorab spekulativ bauen.
KEINE_REAKTION_TAGE = 14

# Gegenüber-Wert -> Split-Bucket-Name fürs Dashboard (Spec-Entscheidung 2, Karte "Gespräche
# gesamt"). Werte, die hier NICHT auftauchen (None/"Fachbereich"/"Sonstige"/"Netzwerk", der für
# NetzwerkGespraech zusätzlich erlaubte Wert), landen im Sammel-Bucket "Fachbereich/Sonstige".
_GEGENUEBER_BUCKETS = {
    "Headhunter": "Headhunter",
    "Recruiter": "Recruiter (Firma)",
    "Hiring Manager": "Hiring Manager",
}
_SAMMEL_BUCKET = "Fachbereich/Sonstige"


def _bucket(gegenueber: Optional[str]) -> str:
    return _GEGENUEBER_BUCKETS.get(gegenueber, _SAMMEL_BUCKET)


def _parse_datum(wert) -> Optional[date]:
    """Robuste Datums-Extraktion — akzeptiert `date`/`datetime`-Objekte direkt sowie ISO-Strings
    ("YYYY-MM-DD" oder mit Zeitanteil, erste 10 Zeichen reichen). Alles andere (None, leer,
    unparsebarer Freitext) -> None. NIE eine Exception werfen (s. Spec-Fallstricke: Outreach-
    Daten sind teils Freitext-gemischt) — ein unparsebares Datum zählt einfach nicht mit."""
    if wert is None:
        return None
    if isinstance(wert, datetime):
        return wert.date()
    if isinstance(wert, date):
        return wert
    if isinstance(wert, str):
        s = wert.strip()
        if not s:
            return None
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None
    return None


def bewerbungen_kpi(apps: Iterable, outreach: Iterable) -> dict:
    """KPI 1 "Bewerbungen gesamt" (Spec-Entscheidung 2).

    `apps`: Application-Rows — zählt jede mit `status != 'Vorbereitet'` (Status ist das
    alleinige Kriterium, ein fehlendes `applied_date` schließt NICHT aus).
    `outreach`: Outreach-Rows — zählt jede mit gesetztem `bewerbung_datum` (Netzwerk-Bewerbung).
    Die Doppelzählungs-Vermeidung (dieselbe Bewerbung nicht sowohl als Application ALS AUCH als
    Outreach-Bewerbung) ist laut Spec eine PFLEGE-Regel (UI-Tooltip + Backfill-Disziplin), keine
    Code-Regel — beide Quellen zählen hier bewusst unabhängig voneinander.
    """
    app_rows = [a for a in apps if (a.status or "") != "Vorbereitet"]
    outreach_rows = [o for o in outreach if o.bewerbung_datum]

    rows = [
        {"id": a.id, "label": f"Job {a.job_id}", "kanal": "Ausschreibung", "tage": None}
        for a in app_rows
    ] + [
        {"id": o.id, "label": o.unternehmen, "kanal": "Netzwerk", "tage": None}
        for o in outreach_rows
    ]
    return {
        "wert": len(app_rows) + len(outreach_rows),
        "splits": {
            "Positionsausschreibungen": len(app_rows),
            "Netzwerk": len(outreach_rows),
        },
        "rows": rows,
    }


def gespraeche_kpi(interviews: Iterable, netzwerkgespraeche: Iterable) -> dict:
    """KPI 2 "Gespräche gesamt" (Spec-Entscheidung 2).

    `interviews`: Interview-Rows — zählt jede mit `status == 'Absolviert'`.
    `netzwerkgespraeche`: alle NetzwerkGespraech-Rows (Gespräche ohne Stelle, keine eigene
    Statusspalte — jede Row ist ein geführtes Gespräch).
    Split nach `gegenueber` in die vier Buckets aus der Spec + Querschnitt "davon vor Ort"
    (`vor_ort` BEIDER Quellen) als zusätzlicher Schlüssel `davon_vor_Ort` — bewusst additiv zu
    den vier Buckets, nicht Teil ihrer Summe (ein Gespräch kann z. B. "Hiring Manager" UND
    "vor Ort" zugleich sein, s. Dashboard-Karte "Unterzeilen je Gegenüber-Typ + davon vor Ort Z").
    """
    absolvierte = [i for i in interviews if (i.status or "") == "Absolviert"]
    netzwerkgespraeche = list(netzwerkgespraeche)

    splits = {"Headhunter": 0, "Recruiter (Firma)": 0, "Hiring Manager": 0, _SAMMEL_BUCKET: 0}
    vor_ort = 0
    rows = []

    for i in absolvierte:
        splits[_bucket(i.gegenueber)] += 1
        if i.vor_ort:
            vor_ort += 1
        rows.append({
            "id": i.id, "label": f"Job {i.job_id}",
            "kanal": i.gegenueber or "Sonstige", "tage": None,
        })

    for g in netzwerkgespraeche:
        splits[_bucket(g.gegenueber)] += 1
        if g.vor_ort:
            vor_ort += 1
        rows.append({
            "id": g.id, "label": g.unternehmen,
            "kanal": g.gegenueber or "Netzwerk", "tage": None,
        })

    splits["davon_vor_Ort"] = vor_ort
    return {"wert": len(absolvierte) + len(netzwerkgespraeche), "splits": splits, "rows": rows}


def absagen_kpi(jobs: Iterable, outreach: Iterable) -> dict:
    """KPI 3 "Absagen gesamt" (Spec-Entscheidung 2).

    `jobs`: Job-Rows — zählt `status == 'Absage'`. Terminal-Status wie 'Beirat abgelehnt',
    'Kein Match', 'Nicht verfügbar' zählen bewusst NICHT (Eigenentscheidungen bzw.
    Stellenwegfall, keine Absage AN den Nutzer) — durch den exakten `== 'Absage'`-Vergleich
    automatisch ausgeschlossen, keine gesonderte Ausschlussliste nötig.
    `outreach`: Outreach-Rows — zählt `status == 'Closed Negative'`.
    """
    jobs_abgesagt = [j for j in jobs if j.status == "Absage"]
    outreach_abgesagt = [o for o in outreach if o.status == "Closed Negative"]

    rows = [
        {"id": j.id, "label": j.company_name, "kanal": "Ausschreibung", "tage": None}
        for j in jobs_abgesagt
    ] + [
        {"id": o.id, "label": o.unternehmen, "kanal": "Netzwerk", "tage": None}
        for o in outreach_abgesagt
    ]
    return {
        "wert": len(jobs_abgesagt) + len(outreach_abgesagt),
        "splits": {"Ausschreibungen": len(jobs_abgesagt), "Netzwerk": len(outreach_abgesagt)},
        "rows": rows,
    }


def keine_reaktion_kpi(
    jobs: Iterable, emails: Iterable, apps: Iterable, outreach: Iterable,
    heute: Optional[date] = None,
) -> dict:
    """KPI 4 "Keine Reaktion" (Spec-Entscheidung 2) — Schwelle `KEINE_REAKTION_TAGE` (14 Tage).

    Ausschreibungen: Job `status IN ('Beworben', 'Keine Rückmeldung')` UND KEINE eingehende
    E-Mail zum Job (`Email.direction == 'incoming'` über `job_id`) UND die (früheste)
    zugehörige Bewerbung ist älter als die Schwelle (`Application.applied_date`, fehlt es:
    `created_at`). Ohne JEDE verwertbare Bewerbungs-Row/Datum zu diesem Job zählt er defensiv
    NICHT mit (kein Alter bestimmbar, s. Moduldocstring zum Datums-Parsing).

    Phase 85: Für `status == 'Keine Rückmeldung'` (manuell vom Nutzer gesetzter Ghosting-
    Endstatus) gilt die 14-Tage-Schwelle NICHT — die Entscheidung "es kommt nichts mehr" ist
    bereits getroffen, der Job zählt unabhängig vom Alter mit. Für `status == 'Beworben'`
    bleibt die Schwelle unverändert. Grund: würde man beim Umstellen von "Beworben" auf "Keine
    Rückmeldung" aus dieser KPI herausfallen, sänke die angezeigte Zahl, obwohl sich am
    Sachverhalt nichts geändert hat — genau das soll der neue Status sichtbar machen, nicht
    verschleiern.

    Netzwerk: Outreach mit `antwort != 'Ja'` (inkl. NULL) UND `status IN ('Initiated',
    'On Hold')` UND letzte Aktivität (`antwort_datum`, sonst `datum`) älter als die Schwelle.

    Beide Teillisten kommen NICHT nur gezählt, sondern als Row-Listen zurück (fürs Aufrollen in
    der UI, Spec-Entscheidung 2) — `tage` ist hier (anders als bei den drei anderen KPIs)
    tatsächlich befüllt.

    `heute`: Stichtag, Default `date.today()` — als Parameter statt hart `date.today()` im Body,
    damit Tests deterministisch gegen feste Tage prüfen können (Grenzfälle 13/15 Tage).
    """
    heute = heute or date.today()
    jobs = list(jobs)
    apps = list(apps)
    outreach = list(outreach)

    job_ids_mit_eingang = {
        e.job_id for e in emails
        if e.direction == "incoming" and e.job_id is not None
    }

    # job_id -> früheste verwertbare Bewerbungs-Datum (mehrere Application-Rows je Job sind
    # selten, aber möglich — die früheste zählt fürs Alter).
    fruehste_bewerbung: dict = {}
    for a in apps:
        datum = _parse_datum(a.applied_date) or _parse_datum(a.created_at)
        if datum is None:
            continue
        bisher = fruehste_bewerbung.get(a.job_id)
        if bisher is None or datum < bisher:
            fruehste_bewerbung[a.job_id] = datum

    ausschreibungen_rows = []
    for j in jobs:
        if j.status not in ("Beworben", "Keine Rückmeldung"):
            continue
        if j.id in job_ids_mit_eingang:
            continue
        datum = fruehste_bewerbung.get(j.id)
        if datum is None:
            continue
        tage = (heute - datum).days
        # Phase 85: für den manuell gesetzten Endstatus zählt die Zeile unabhängig vom Alter.
        if j.status == "Keine Rückmeldung" or tage >= KEINE_REAKTION_TAGE:
            ausschreibungen_rows.append({
                "id": j.id, "label": j.company_name, "kanal": "Ausschreibung", "tage": tage,
            })

    netzwerk_rows = []
    for o in outreach:
        if o.antwort == "Ja":
            continue
        if o.status not in ("Initiated", "On Hold"):
            continue
        datum = _parse_datum(o.antwort_datum) or _parse_datum(o.datum)
        if datum is None:
            continue
        tage = (heute - datum).days
        if tage >= KEINE_REAKTION_TAGE:
            netzwerk_rows.append({
                "id": o.id, "label": o.unternehmen or o.kontakt, "kanal": "Netzwerk", "tage": tage,
            })

    rows = ausschreibungen_rows + netzwerk_rows
    return {
        "wert": len(rows),
        "splits": {
            "Ausschreibungen": len(ausschreibungen_rows),
            "Netzwerk": len(netzwerk_rows),
        },
        "rows": rows,
    }


# ═══════════════════════════════════════════════════════════════════════════════════════════
# Funnel-KPI (Phase 70, Stufe A) — „Gesamtprozess als Trichter": WIE VIELE Stellen/Bewerbungen
# jede Stufe überleben (Gesichtet -> Relevant -> Beworben -> Antworten -> Interviews), statt nur
# die vier Einzel-KPIs oben lose nebeneinander zu zeigen. Anlass (Rückmeldung vom 29.07.2026): „das Look
# & Feel ist zu wenig, die Daten zeigen kein klares Bild" — Vorbild ist ein handgebautes
# Excel-Funnel-Blatt (s. tasks/spec_phase70_funnel_gesamtprozess.md). EINE Berechnung für Web
# (/api/dashboard, unter gesamtprozess.funnel — der Top-Level-Key "funnel" ist bereits vom
# Pipeline-Funnel belegt) UND Excel (Blatt "Funnel"): ruft NUR bestehende KPI-Funktionen dieses
# Moduls + response_kpis auf, dupliziert keine Formel neu (Fallstrick „Eine Quelle", Phase 67B).
#
# Mixed-Basis bewusst wie im Vorbild: Stufe 1-2 zählen STELLEN, Stufe 3-5 BEWERBUNGEN. Dadurch
# kann `vs_vorstufe` von Stufe 3 (Beworben) > 100 % werden (viele Netzwerk-Bewerbungen ggü.
# wenigen relevanten Stellen) — das ist korrekt und wird bewusst NICHT gekappt.
_NICHT_RELEVANT_STATUS = {"Kein Match", "Nicht verfügbar", "Beirat abgelehnt"}


def _prozent(anzahl, basis) -> Optional[float]:
    """anzahl/basis*100, 1 Nachkommastelle. Basis 0 -> None (nie ZeroDivisionError)."""
    if not basis:
        return None
    return round(anzahl / basis * 100, 1)


def _de_prozent_prosa(p: float) -> str:
    """Deutsches Komma für Fließtext ('37,3 %', MIT Leerzeichen vor %) — NUR für den
    `groesster_verlust`-Satz gebraucht. Die Zahlen-Felder in `engstellen` bleiben rohe floats;
    die Konsumenten (Excel Stufe A, Dashboard Stufe B) formatieren sie kontextabhängig selbst
    (Tabellenzelle ohne Leerzeichen vs. Fließtext mit) — dieselbe Arbeitsteilung wie bei
    `vs_vorstufe`/`vs_start` in `stufen` (auch dort rohe floats, Formatierung liegt beim
    Konsumenten)."""
    return f"{p:.1f}".replace(".", ",") + " %"


# Je Stufe (2-5) EIN fester Satzbaustein fürs `groesster_verlust.text` (Spec-Vorgabe:
# „Textbausteine je Stufe fest: Screening/Bewerbungsquote/Antwortquote/Interview-Konversion").
# `p` ist die bereits deutsch formatierte Prozent-Prosa, `basis` die Anzahl der Vorstufe (nur
# von der Antwortquote im Satz gebraucht: „... auf 68 Bewerbungen").
_ENGSTELLEN_SATZ = {
    "Relevant": lambda p, basis: f"Screening: nur {p} der gesichteten Stellen sind relevant",
    "Beworben": lambda p, basis: f"Bewerbungsquote: {p} der relevanten Stellen wurden beworben",
    "Antworten": lambda p, basis: f"Antwortquote {p} auf {basis} Bewerbungen",
    "Interviews": lambda p, basis: f"Interview-Konversion: {p} der Antworten führten zum Interview",
}


def funnel_kpi(jobs: Iterable, apps: Iterable, emails: Iterable, outreach: Iterable,
               interviews: Iterable, netzwerkgespraeche: Iterable) -> dict:
    """Der Gesamtprozess als 5-stufiger Trichter (Phase 70) — Stufen-Definitionen im Detail s.
    tasks/spec_phase70_funnel_gesamtprozess.md.

    1. Gesichtet — der gesamte Pool (Aufrufer liefert bereits `deleted_at IS NULL`-gefiltert,
       Muster wie bei den vier KPI-Funktionen oben).
    2. Relevant — ohne Status 'Kein Match'/'Nicht verfügbar'/'Beirat abgelehnt' (Status NULL
       zählt als relevant).
    3. Beworben — `bewerbungen_kpi()["wert"]`.
    4. Antworten — `response_kpis()["responses"]` (eindeutige Bewerbungen mit Antwort).
    5. Interviews — eindeutige Jobs mit Status 'Interview' ODER mind. einer Interview-Row
       (Union über beide Kriterien, robuster als jede Einzelvariante).

    Rückgabe: {"stufen": [{"stufe", "anzahl", "vs_vorstufe", "vs_start", "kommentar"}, … 5],
               "engstellen": {"screening", "bewerbungsquote", "antwortquote",
                              "interview_konversion", "ende_zu_ende", "groesster_verlust"}}
    """
    jobs = list(jobs)

    gesichtet = len(jobs)
    relevant = sum(1 for j in jobs if j.status not in _NICHT_RELEVANT_STATUS)

    bew_kpi = bewerbungen_kpi(apps, outreach)
    beworben = bew_kpi["wert"]

    resp = response_kpis(emails, apps)
    antworten = resp["responses"]
    abs_kpi = absagen_kpi(jobs, outreach)
    kr_kpi = keine_reaktion_kpi(jobs, emails, apps, outreach)

    # Union: Job.status == 'Interview' ODER mind. eine Interview-Row (jeder Status zählt hier
    # mit, s. Spec: „mind. einer Interview-Row") — ein Job kann über den Status oder nur über
    # eine (z. B. noch nicht als 'Absolviert' geführte) Interview-Zeile erkennbar sein.
    interview_job_ids = {i.job_id for i in interviews}
    status_job_ids = {j.id for j in jobs if j.status == "Interview"}
    interview_jobs = len(interview_job_ids | status_job_ids)
    ges_kpi = gespraeche_kpi(interviews, netzwerkgespraeche)

    avg_resp = resp["avg_response_hours"]
    avg_teil = (f"Ø Antwortzeit {avg_resp:.1f} h" if avg_resp is not None
                else "Ø Antwortzeit unbekannt")

    _roh = [
        ("Gesichtet", gesichtet, "Gesamter Pool aller erfassten Stellen"),
        ("Relevant", relevant, "ohne Kein Match / nicht verfügbar / Beirat abgelehnt"),
        ("Beworben", beworben,
         f"{bew_kpi['splits'].get('Positionsausschreibungen', 0)} Ausschreibungen + "
         f"{bew_kpi['splits'].get('Netzwerk', 0)} über Netzwerk"),
        ("Antworten", antworten,
         f"{avg_teil} · {abs_kpi['wert']} Absagen, {kr_kpi['wert']} ohne Reaktion"),
        ("Interviews", interview_jobs,
         f"{ges_kpi['wert']} Gespräche gesamt inkl. Headhunter & Netzwerk"),
    ]

    stufen = []
    for i, (name, anzahl, kommentar) in enumerate(_roh):
        vs_vorstufe = None if i == 0 else _prozent(anzahl, _roh[i - 1][1])
        stufen.append({
            "stufe": name, "anzahl": anzahl,
            "vs_vorstufe": vs_vorstufe, "vs_start": _prozent(anzahl, gesichtet),
            "kommentar": kommentar,
        })

    # Engstellen: Stufe 2-5 nach dem NIEDRIGSTEN vs_vorstufe (None -> übersprungen, eine
    # Basis-0-Stufe kann nie „größter Verlust" werden). Bei Gleichstand gewinnt die ERSTE Stufe
    # in Trichter-Reihenfolge — `min()` ersetzt den bisherigen Minimalwert nur bei einem STRIKT
    # kleineren Kandidaten und behält damit bei Gleichstand den zuerst eingefügten (s. Test).
    kandidaten = []
    for idx in range(1, len(stufen)):
        p = stufen[idx]["vs_vorstufe"]
        if p is None:
            continue
        basis = stufen[idx - 1]["anzahl"]
        satz = _ENGSTELLEN_SATZ[stufen[idx]["stufe"]](_de_prozent_prosa(p), basis)
        kandidaten.append((p, stufen[idx]["stufe"], satz))

    engstellen = {
        "screening": stufen[1]["vs_vorstufe"],
        "bewerbungsquote": stufen[2]["vs_vorstufe"],
        "antwortquote": stufen[3]["vs_vorstufe"],
        "interview_konversion": stufen[4]["vs_vorstufe"],
        "ende_zu_ende": stufen[4]["vs_start"],
        "groesster_verlust": None,
    }
    if kandidaten:
        p_min, stufe_min, satz_min = min(kandidaten, key=lambda k: k[0])
        engstellen["groesster_verlust"] = {
            "stufe": stufe_min, "prozent": p_min, "text": f"Größter Verlust: {satz_min}",
        }

    return {"stufen": stufen, "engstellen": engstellen}
