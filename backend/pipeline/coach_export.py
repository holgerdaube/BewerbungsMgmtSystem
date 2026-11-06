#!/usr/bin/env python3
"""Coach-Site-Export (Phase 81) — statischer Read-only-Spiegel für die Coach-Site.

Deterministisch, OHNE LLM (Muster digest.py): rendert aus der DB vier Seiten (index / digest /
stellen / absagen) im §18-Token-Look und kopiert die freigegebenen, bereits existierenden
Report-Dateien (CompanyFit_, Match_) der Pipeline-Jobs dazu. Hochgeladen wird separat über
scripts/coach_deploy.sh (lftp-SFTP-Spiegel); der App-Trigger ist der local_cmd-Task
"coach-site" (scripts/coach_site.sh = Export + Deploy).

WHITELIST-Prinzip (Spec Phase 81, testbewehrt in tests/test_coach_export_sperrliste.py):
Dieses Modul liest die Sperrfelder GAR NICHT ERST aus der DB — job.salary, job.notes,
job.verify_note, JobLog/JobChat, Email-, Beirats-, Transkript-, Kontakt- und Budget-Daten
kommen in keiner Query vor. Vertrauliche Mandate erscheinen UNVERÄNDERT wie in der App
(Entscheidung des Nutzers 10.08.2026: Coach = der Nutzer, was diese Datensicht angeht).

Tages-Digest (P2-79): Die Seite `digest.html` setzt `digest.digest_inhalt(fuer_coach=True)` in die Seitenhülle
der Coach-Site, es gibt keinen zweiten Digest. Diese Fassung lässt „Zu beantworten“ und „Offene Aktionen“
weg und liest `needs_reply` und `next_step` gar nicht erst; „Heute geändert“ nimmt nur Verlaufseinträge mit
`art == "auto"` und nie einen Notiztext. Ehrlich dazu: Der Absagen-Abschnitt des Digest liest Mail-Zeilen
(Kategorie, Empfangszeit, Zuordnung, Wartezeit) und das Verlaufsprotokoll insgesamt; ausgegeben werden davon nur
Firma, Stelle, Zeit und Wartezeit, nie Adresse, Betreff oder Text. Das hält tests/test_coach_export_sperrliste.py
mit Marker-Strings in genau diesen Feldern fest.

Favicon (Phase 82): das App-Icon landet als Base64-Data-URI im <head> jeder generierten Seite UND
jedes kopierten Artefakts (favicon.favicon_link/_mit_favicon) — bewusst OHNE eigene Datei im Export,
damit die Whitelist-Regex in tests/test_coach_export_sperrliste.py unangetastet bleibt (I3).
P2-72: Das Icon und die Markenwerte im CSS kommen aus dem geltenden Design (pipeline/design.py), bei
jedem Export frisch gelesen; die Zustandsfarben aus pipeline/zustandsfarben.py (nur Bedeutung, kein Design).

CLI (aus backend/):
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.coach_export            # exportiert
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.coach_export --dry-run  # listet nur
"""
import datetime
import html
import json
import re
import shutil
import sys
from pathlib import Path
from string import Template

import yaml
from sqlmodel import Session, select

from app.db import DATA_DIR, engine, init_db
from app.models import Application, Company, CVVersion, Job
# Score-Badge-Farben aus dem Digest wiederverwenden — EINE Quelle für die §18.4-Skala samt Kontrastregel
# (§18.8: Navy-Text auf Gelb/Orange/Hellgrün) und deren benannter Ausnahme (Score 5), dazu die Ersetzungs-
# tabelle für die Markenwerte im CSS. P2-72: Die Skala selbst steht in pipeline/zustandsfarben.py.
from pipeline.digest import markenwerte, score_farben
from pipeline import absagen_bericht, design, digest, zustandsfarben
from pipeline.bericht_stil import fassungen
from app import favicon
from app.sprache import datum, html_lang, tx, uebersetzt
from app.zeit import nach_lokal
# P2-30: die Datumsquelle ist fertig gebaut (deckt einen Großteil der Stellen ab, applied_date
# allein deutlich weniger) — hier NICHT nachbauen, nur importieren.
from pipeline.gmail_ingest import beworben_am_je_job

# P2-30: Status, deren Bewerbungsprozess noch läuft — dort ist „seit N Tagen" die Zahl, über
# die ein Coach spricht. Bei abgeschlossenen Stellen (Absage etc.) wäre die Laufzeit
# Vergangenheit und würde die Spalte nur verrauschen, siehe Spec §2.
_STATUS_LAUFEND = ("Beworben", "Interview", "Angebot")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_EXPORT_DIR = DATA_DIR / "exports" / "coach_site"
_CONFIG_PATH = PROJECT_ROOT / "config" / "coach_export.yaml"

# P2-72 (Design aus einer Quelle): Die Markenwerte stehen als `$rolle`-Platzhalter im CSS und kommen bei
# JEDEM Export aus dem geltenden Design (`_css()`, nie beim Import). Mit der Vorgabe entsteht byte-genau
# das CSS von vorher. Fest bleibt das Neutralgrau für Nebentext (`.muted`, Slate-400): Es gehört zu keiner
# Rolle, `text_gedaempft` ist ein anderer Wert. Die Zustandsfarben (Status, Score) stehen inline in den
# Zellen und kommen aus `pipeline/zustandsfarben.py`.
_CSS_VORLAGE = Template("""
body{font-family:$schrift_text,system-ui,-apple-system,sans-serif;background:$flaeche;color:$text;margin:0;padding:24px}
.wrap{max-width:1080px;margin:0 auto}
h1{color:$marke;margin:0 0 4px;font-size:24px}
.sub{color:$text_gedaempft;font-size:14px;margin-bottom:18px}
nav{margin-bottom:22px;display:flex;gap:10px;flex-wrap:wrap}
nav a{background:$karte;border:1px solid $rahmen;border-radius:999px;padding:6px 14px;font-size:13px;
color:$text;text-decoration:none;font-weight:600}
nav a.aktiv{background:$aktion;border-color:$aktion;color:$auf_aktion}
.kpis{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:24px}
.kpi{background:$karte;border:1px solid $rahmen;border-radius:12px;padding:12px 16px;min-width:130px}
.kpi .n{font-size:26px;font-weight:700;color:$marke}.kpi.acc .n{color:$aktion}
.kpi .l{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:$text_gedaempft}
section{background:$karte;border:1px solid $rahmen;border-radius:12px;padding:16px;margin-bottom:16px}
h2{font-size:15px;color:$marke;margin:0 0 10px}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;color:$text_gedaempft;font-size:11px;text-transform:uppercase;letter-spacing:.06em;
padding:8px 10px;border-bottom:1px solid $rahmen}
td{padding:9px 10px;border-bottom:1px solid $spur;vertical-align:top}
tr:last-child td{border-bottom:none}
.badge{display:inline-flex;width:22px;height:22px;border-radius:50%;font-size:12px;font-weight:700;
align-items:center;justify-content:center}
.status{display:inline-block;border-radius:999px;padding:2px 10px;font-size:11px;font-weight:700;white-space:nowrap}
.balkenreihe{display:flex;align-items:center;gap:10px;margin:6px 0;font-size:13px}
.balkenreihe .label{width:110px;color:$text_gedaempft}
.balken{flex:1;background:$spur;border-radius:6px;height:12px;overflow:hidden}
.balken div{height:100%;border-radius:6px}
.balkenreihe .n{width:34px;text-align:right;font-weight:700}
a.report{color:$aktion;text-decoration:none;font-weight:600;font-size:12.5px}
a.report:hover{text-decoration:underline}
.muted{color:#94A3B8}.grund{max-width:420px}
.foot{margin-top:20px;padding-top:12px;border-top:1px solid $rahmen;font-size:12px;color:$text_gedaempft;
display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
""")


def _css(d) -> str:
    return _CSS_VORLAGE.substitute(markenwerte(d))


def _e(x) -> str:
    return html.escape(str(x)) if x is not None else ""


def _score_badge(sc) -> str:
    if not sc:
        bg, text = zustandsfarben.SCORE_NICHT_BEWERTET
        return f'<span class="badge" style="background:{bg};color:{text}">–</span>'
    bg, text = score_farben(sc)
    return f'<span class="badge" style="background:{bg};color:{text}">{sc}</span>'


def _status_pille(status) -> str:
    bg, text = zustandsfarben.status_farbe(status)
    return f'<span class="status" style="background:{bg};color:{text}">{_e(uebersetzt(status))}</span>'


def _beworben_am_zelle(zeitpunkt, status) -> str:
    """P2-30: Datum `DD.MM.YYYY`, sonst „–". Bei laufendem Prozess (§2 der Spec) zusätzlich
    die Laufzeit als gedämpfter Zusatz — die Zahl, über die ein Coach spricht. Bei
    abgeschlossenen Stellen nur das Datum, sonst verrauscht die Laufzeit die Spalte."""
    if not zeitpunkt:
        return "–"
    lokal = nach_lokal(zeitpunkt)
    text = datum(lokal)
    if status in _STATUS_LAUFEND:
        tage = (datetime.datetime.now(lokal.tzinfo) - lokal).days
        # Deutsch sagt seit jeher auch „seit 1 Tagen“ und bleibt Zeichen für Zeichen so. Der zweite Schlüssel
        # (anderer Platzhalter, gleicher deutscher Text) lässt Englisch den Singular richtig schreiben.
        if tage == 1:
            laufzeit = tx("· seit {tag} Tagen", tag=tage)
        else:
            laufzeit = tx("· seit {tage} Tagen", tage=tage)
        return f'{text} <span class="muted">{laufzeit}</span>'
    return text


def _rel_datei(rel: str) -> Path:
    """Projekt-relative Pfade ('data/…') über DATA_DIR auflösen (folgt BMS_DATA_DIR)."""
    rel = (rel or "").strip()
    if rel.startswith("data/"):
        return DATA_DIR / rel[5:]
    return PROJECT_ROOT / rel


# P2-22 (28.08.2026): Die Favicon-Logik liegt jetzt in `app/favicon.py` — sie wird von neun
# Stellen gebraucht (alle Report-Erzeuger, der Artefakt-Endpunkt, die Nachruestung). Die frueher
# hier begruendete Eigenstaendigkeit ("beide Module ohne Abhaengigkeit voneinander lauffaehig")
# traegt bei neun Nutzern nicht mehr: Das waeren neun Stellen, an denen jemand das Icon vergisst.
# P2-72: Das Icon des geltenden Designs wird je Seite zur Laufzeit gelesen (`favicon.favicon_link()`), nicht
# beim Import festgehalten; `_mit_favicon` ist die Funktion selbst und liest es bei jedem Aufruf.
_mit_favicon = favicon.mit_favicon


def _kopiere_mit_favicon(quelle: Path, ziel: Path) -> None:
    """Kopiert ein Artefakt in den Export und setzt dabei den Favicon-Link in dessen <head>
    ein (Spec 3.3). Kein <head> gefunden, kein Favicon verfügbar oder die Datei nicht als
    UTF-8 lesbar → unverändert kopieren, exakt wie vor Phase 82 (shutil.copy2)."""
    try:
        text = quelle.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        shutil.copy2(quelle, ziel)
        return
    neu = _mit_favicon(text)
    if neu == text:
        shutil.copy2(quelle, ziel)
        return
    ziel.write_text(neu, encoding="utf-8")
    shutil.copystat(quelle, ziel)


# Die Reiter in ihrer Anzeige-Reihenfolge (P2-79: „Tages-Digest“ neben der Übersicht).
def _navigation() -> tuple:
    """Die Reiter mit Beschriftung in der Sprache, die beim Export gilt."""
    return (
        ("index", "index.html", tx("Übersicht")),
        ("digest", "digest.html", tx("Tages-Digest")),
        ("stellen", "stellen.html", tx("Stellen & Bewerbungen")),
        ("absagen", "absagen.html", tx("Absagen & Muster")),
    )


def _seite(titel: str, aktiv: str, inhalt: str, stand: str, geltend=None, tages_digest: bool = True,
           css_zusatz: str = "") -> str:
    """Eine Seite der Coach-Site. `tages_digest=False` nimmt den Reiter „Tages-Digest“ aus der Navigation
    (Config-Schlüssel `tages_digest`); `css_zusatz` hängt Regeln hinter das gemeinsame CSS, bisher nur die
    Zeilen-Regeln des Digest für `digest.html`. Ohne Zusatz ist das `<style>` byte-gleich zu dem von vorher."""
    geltend = geltend or design.laden()      # P2-72: das Design gilt, wie es JETZT ist
    nav = "".join(
        f'<a href="{ziel}" class="{"aktiv" if key == aktiv else ""}">{label}</a>'
        for key, ziel, label in _navigation() if tages_digest or key != "digest")
    zusatz = f"{css_zusatz}\n" if css_zusatz else ""
    sub_zeile = tx("Bewerbungs-Übersicht für den Coaching-Kontext")
    foot_stand = tx("Bewerbungs-Mgmt · Stand {stand}", stand=stand)
    foot_hinweis = tx("Vertraulich — nur für den Coaching-Kontext · Quelle: lokale Bewerbungsdatenbank")
    return f"""<!doctype html><html lang="{html_lang()}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex, nofollow">{favicon.favicon_link(geltend)}<title>{_e(titel)}</title>
<style>{_css(geltend)}{zusatz}</style></head><body><div class="wrap">
<h1>{_e(titel)}</h1><div class="sub">{sub_zeile}</div>
<nav>{nav}</nav>
{inhalt}
<div class="foot"><span>{foot_stand}</span><span>{foot_hinweis}</span></div>
</div></body></html>"""


def _lade_config() -> dict:
    cfg = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    # Kompat: die Erst-Konfig (bis 10.08. nachmittags) kannte nur status_pipeline
    cfg.setdefault("status_aktiv", cfg.get("status_pipeline",
                                           ["Angebot", "Interview", "Beworben"]))
    cfg.setdefault("status_vorstufe", ["Prüfen", "Neu"])
    cfg.setdefault("status_absagen", ["Absage"])
    cfg.setdefault("artefakte", ["CompanyFit", "Match"])
    cfg.setdefault("snapshots", False)
    cfg.setdefault("absagen_analyse_report", True)
    cfg.setdefault("tages_digest", True)       # P2-79: ohne Eintrag gibt es den Reiter
    return cfg


# ── Anzeigen-Snapshots (Erweiterung 10.08.): Erfassungs-Kontext MUSS raus ──────────────────
# Der Kanon-Snapshot (posting_snapshot._build_html) endet mit der Karte
# `<h2 class="sec">Erfassungs-Kontext</h2><div class="card">…</div>` — darin stehen
# job.source_note und job.verify_note (Vier-Augen-Interna, Sperrliste!). Die Karte enthält
# nur <p>-Absätze (kein verschachteltes div), der non-greedy Match ist daher sicher.
# Berichte bleiben in der Sprache, in der sie entstanden: Die Karte heißt je nach Sprache anders und wird in
# BEIDEN Fassungen entfernt (`fassungen()`); sonst bliebe sie in einem englischen Snapshot stehen, die
# Marker-Prüfung unten würde ihn zwar noch auffangen, aber die Datei fiele ganz aus dem Export.
def _erfassung_re():
    return re.compile(
        r'<h2 class="sec">(?:' + "|".join(re.escape(f) for f in fassungen("Erfassungs-Kontext"))
        + r')</h2>\s*<div class="card">.*?</div>', re.S)
# "Vier-Augen" als Präfix (nicht nur "-Beleg"): Alt-Snapshots tragen Prüfvermerke auch
# frei im Text ("Vier-Augen-Check bereits bestätigt", Live-Fund vom 10.08.).
def _erfassung_marker() -> tuple:
    """Spuren der Erfassungs-Interna im Text (beide Sprachen): bleibt nach dem Entfernen eine übrig, wird die Datei
    übersprungen."""
    return fassungen("Erfassungs-Kontext") + fassungen("Vier-Augen")


def _snapshot_bereinigt(quelle: Path):
    """Snapshot-HTML ohne Erfassungs-Kontext — oder None, wenn die Bereinigung nicht
    NACHWEISLICH gelungen ist (Alt-Struktur): dann wird die Datei übersprungen und gemeldet,
    nie geraten (Laufzeit-Guard zusätzlich zur Sperrlisten-Testabdeckung)."""
    html_text = quelle.read_text(encoding="utf-8", errors="replace")
    bereinigt = _erfassung_re().sub("", html_text)
    if any(m in bereinigt for m in _erfassung_marker()):
        return None
    return bereinigt


def _artefakte_fuer_job(s: Session, job: Job, typen: list) -> list:
    """(label, Quellpfad)-Paare der freigegebenen, existierenden Reports dieses Jobs."""
    gefunden = []
    if "CompanyFit" in typen and job.company_id:
        comp = s.get(Company, job.company_id)
        if comp and comp.fit_analysis_path:
            p = _rel_datei(comp.fit_analysis_path)
            if p.is_file():
                gefunden.append((tx("Company-Fit"), p))
    if "Match" in typen:
        cv = s.exec(select(CVVersion).where(CVVersion.job_id == job.id,
                                            CVVersion.match_dashboard_path.is_not(None))
                    .order_by(CVVersion.created_at.desc())).first()
        if cv and cv.match_dashboard_path:
            p = _rel_datei(cv.match_dashboard_path)
            if p.is_file():
                gefunden.append((tx("Match"), p))
    return gefunden


def export(dry_run: bool = False) -> dict:
    init_db()
    cfg = _lade_config()
    jetzt = datetime.datetime.now()
    stand = f"{datum(jetzt)} {jetzt:%H:%M}"
    geltend = design.laden()     # P2-72: EIN Stand des Designs für alle Seiten dieses Exports
    mit_digest = bool(cfg["tages_digest"])      # P2-79: false → weder digest.html noch Reiter
    kopien = []          # (Quelle, Zielname)
    snapshot_texte = {}  # Zielname -> bereinigtes HTML (Snapshots werden gefiltert geschrieben)
    uebersprungen = []   # Snapshots, deren Bereinigung nicht nachweislich gelang
    with Session(engine) as s:
        jobs = s.exec(select(Job).where(Job.deleted_at.is_(None))).all()
        pipeline = [j for j in jobs if j.status in (cfg["status_aktiv"] + cfg["status_vorstufe"])]
        absagen = [j for j in jobs if j.status in cfg["status_absagen"]]
        alle_aktiv = [j for j in jobs]

        # Absagegründe: je Job die neueste Application mit rejection_reason
        gruende = {}
        kanaele = {}
        for a in s.exec(select(Application).order_by(Application.id)).all():
            if a.rejection_reason:
                gruende[a.job_id] = a.rejection_reason
            if a.channel:
                kanaele[a.job_id] = a.channel

        # P2-30: Bewerbungsdatum je Stelle — fertige Funktion, nicht nachgebaut (s. o.).
        beworben = beworben_am_je_job(s)

        # ── stellen.html — zwei Sektionen: Aktive Bewerbungen + Sichtung & Prüfung ──
        def _job_zeile(j: Job) -> str:
            links = []
            for label, quelle in _artefakte_fuer_job(s, j, cfg["artefakte"]):
                ziel = quelle.name
                kopien.append((quelle, ziel))
                links.append(f'<a class="report" href="artefakte/{_e(ziel)}">{label}</a>')
            if cfg.get("snapshots") and "Anzeige" in cfg["artefakte"] and j.posting_snapshot_path:
                p = _rel_datei(j.posting_snapshot_path)
                if p.is_file():
                    bereinigt = _snapshot_bereinigt(p)
                    if bereinigt is None:
                        uebersprungen.append(p.name)
                    else:
                        snapshot_texte[p.name] = bereinigt
                        links.append(f'<a class="report" href="artefakte/{_e(p.name)}">{tx("Anzeige")}</a>')
            return (
                f"<tr><td>{_score_badge(j.match_score)}</td><td><b>{_e(j.company_name)}</b></td>"
                f"<td>{_e(j.title)}</td><td>{_e(uebersetzt(j.seniority) or '–')}</td>"
                f"<td>{_e(j.location or '–')}</td><td>{_status_pille(j.status)}</td>"
                f"<td>{_e(j.found_date or '–')}</td>"
                f"<td>{_beworben_am_zelle(beworben.get(j.id), j.status)}</td>"
                f"<td>{' · '.join(links) or '<span class=muted>–</span>'}</td></tr>")

        def _sektion(titel: str, status_liste: list) -> str:
            rang = {st: i for i, st in enumerate(status_liste)}
            gruppe = [j for j in pipeline if j.status in status_liste]
            gruppe.sort(key=lambda j: (rang.get(j.status, 99), -(j.match_score or 0)))
            if not gruppe:
                return (f"<section><h2>{_e(titel)} (0)</h2>"
                        f'<p class="muted" style="font-size:13px">{tx("Aktuell keine Stellen in diesen Status.")}</p></section>')
            zeilen = "".join(_job_zeile(j) for j in gruppe)
            return (f"<section><h2>{_e(titel)} ({len(gruppe)})</h2><table>"
                    f"<thead><tr><th>{tx('Fit')}</th><th>{tx('Firma')}</th><th>{tx('Rolle')}</th><th>{tx('Ebene')}</th>"
                    f"<th>{tx('Standort')}</th><th>{tx('Status')}</th><th>{tx('Gefunden')}</th>"
                    f"<th>{tx('Beworben am')}</th><th>{tx('Reports')}</th></tr></thead>"
                    f"<tbody>{zeilen}</tbody></table></section>")

        stellen_html = _seite(
            tx("Stellen & Bewerbungen"), "stellen",
            _sektion(tx("Aktive Bewerbungen"), cfg["status_aktiv"])
            + _sektion(tx("Sichtung & Prüfung"), cfg["status_vorstufe"]), stand, geltend, tages_digest=mit_digest)

        # ── absagen.html ───────────────────────────────────────────────────────────
        absagen.sort(key=lambda j: (j.found_date or ""), reverse=True)
        a_zeilen = []
        for j in absagen:
            a_zeilen.append(
                f"<tr><td>{_score_badge(j.match_score)}</td><td><b>{_e(j.company_name)}</b></td>"
                f"<td>{_e(j.title)}</td><td>{_e(kanaele.get(j.id) or '–')}</td>"
                f"<td class=grund>{_e(gruende.get(j.id) or '')  or '<span class=muted>' + tx('kein Grund erfasst') + '</span>'}</td></tr>")
        analyse_link = ""
        if cfg.get("absagen_analyse_report"):
            # P2-79: Der neueste Bericht und sein Datum kommen aus `absagen_bericht` (Datum aus dem
            # Dateinamen, nicht aus der Änderungszeit), dieselbe Quelle wie der Rhythmus im Tageslauf.
            # Der Coach sieht so, wie alt die Analyse ist, die er liest.
            bericht = absagen_bericht.neuester()
            if bericht:
                datei, berichtsdatum = bericht
                kopien.append((datei, datei.name))
                analyse_link = (f'<section><h2>{tx("Lost-Order-Analyse")}</h2><p style="font-size:13.5px">'
                                f'<a class="report" href="artefakte/{_e(datei.name)}">'
                                f'{tx("Vollständiger Muster-Bericht vom {datum}", datum=datum(berichtsdatum))}</a></p></section>')
        absagen_html = _seite(
            tx("Absagen & Muster"), "absagen",
            f"<section><h2>{tx('Absagen ({anzahl})', anzahl=len(absagen))}</h2><table>"
            f"<thead><tr><th>{tx('Fit')}</th><th>{tx('Firma')}</th><th>{tx('Rolle')}</th><th>{tx('Kanal')}</th>"
            f"<th>{tx('Absagegrund')}</th></tr></thead>"
            f"<tbody>{''.join(a_zeilen)}</tbody></table></section>{analyse_link}", stand, geltend, tages_digest=mit_digest)

        # ── index.html ─────────────────────────────────────────────────────────────
        counts = {}
        for j in alle_aktiv:
            counts[j.status or "Neu"] = counts.get(j.status or "Neu", 0) + 1
        laufend = sum(counts.get(st, 0) for st in ("Beworben", "Interview", "Angebot"))
        kpis = [
            (tx("Stellen gesamt"), len(alle_aktiv), False),
            (tx("Top-Zielstellen ≥4"), sum(1 for j in alle_aktiv if (j.match_score or 0) >= 4), True),
            (tx("Laufende Bewerbungen"), laufend, True),
            (tx("Interviews"), counts.get("Interview", 0), False),
            (tx("Absagen"), counts.get("Absage", 0), False),
        ]
        kpi_html = "".join(
            f'<div class="kpi {"acc" if acc else ""}"><div class="n">{n}</div><div class="l">{_e(l)}</div></div>'
            for l, n, acc in kpis)
        max_n = max(counts.values()) if counts else 1
        reihen = []
        for st in ("Neu", "Prüfen", "Beworben", "Interview", "Angebot", "Geparkt",
                   "Absage", "Keine Rückmeldung", "Kein Match", "Beirat abgelehnt",
                   "Nicht verfügbar"):
            n = counts.get(st, 0)
            if not n:
                continue
            bg, _txt = zustandsfarben.status_farbe(st)
            reihen.append(f'<div class="balkenreihe"><span class="label">{_e(uebersetzt(st))}</span>'
                          f'<div class="balken"><div style="width:{n / max_n * 100:.0f}%;background:{bg}"></div></div>'
                          f'<span class="n">{n}</span></div>')
        index_html = _seite(
            tx("Bewerbungs-Übersicht"), "index",
            f'<div class="kpis">{kpi_html}</div>'
            f"<section><h2>{tx('Verteilung nach Status')}</h2>{''.join(reihen)}</section>",
            stand, geltend, tages_digest=mit_digest)

    dateien = {"index.html": index_html, "stellen.html": stellen_html,
               "absagen.html": absagen_html,
               "robots.txt": "User-agent: *\nDisallow: /\n"}

    # ── digest.html (P2-79) ────────────────────────────────────────────────────────────────
    # Der Digest des Tages in der Fassung für die Coach-Site (Sperrliste, s. Modul-Docstring). Das CSS für
    # seine Zeilen kommt aus digest.py und wird hinter das Seiten-CSS gehängt, damit es nur dort steht.
    if mit_digest:
        dateien["digest.html"] = _seite(
            tx("Tages-Digest"), "digest",
            '<div class="sub">'
            + tx("Digest vom {datum} · wird mit jedem Tageslauf erneuert", datum=datum(datetime.date.today()))
            + '</div>'
            + digest.digest_inhalt(fuer_coach=True),
            stand, geltend, tages_digest=mit_digest, css_zusatz=digest.zeilen_css(geltend))

    alle_artefakte = sorted({z for _, z in kopien} | set(snapshot_texte))
    if dry_run:
        return {"dry_run": True, "seiten": sorted(dateien), "artefakte": alle_artefakte,
                "snapshots_uebersprungen": sorted(set(uebersprungen)), "ziel": str(_EXPORT_DIR)}

    if _EXPORT_DIR.exists():
        shutil.rmtree(_EXPORT_DIR)
    (_EXPORT_DIR / "artefakte").mkdir(parents=True)
    for name, inhalt in dateien.items():
        (_EXPORT_DIR / name).write_text(inhalt, encoding="utf-8")
    for quelle, ziel in kopien:
        _kopiere_mit_favicon(quelle, _EXPORT_DIR / "artefakte" / ziel)
    # Snapshots werden GEFILTERT geschrieben (nie 1:1 kopiert — Erfassungs-Kontext ist raus);
    # Favicon (Phase 82) genauso wie bei den kopierten Artefakten direkt mit einsetzen.
    for ziel, inhalt in snapshot_texte.items():
        (_EXPORT_DIR / "artefakte" / ziel).write_text(_mit_favicon(inhalt), encoding="utf-8")
    gesamt = sum(p.stat().st_size for p in _EXPORT_DIR.rglob("*") if p.is_file())
    return {"dry_run": False, "seiten": sorted(dateien), "artefakte": alle_artefakte,
            "snapshots_uebersprungen": sorted(set(uebersprungen)),
            "bytes": gesamt, "ziel": str(_EXPORT_DIR)}


def main() -> int:
    result = export(dry_run="--dry-run" in sys.argv)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
