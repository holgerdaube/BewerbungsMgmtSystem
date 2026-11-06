#!/usr/bin/env python3
"""Anzeigen-Snapshot bei Erfassung — Basis-Version OHNE LLM (Phase 38) + gegliederte Vollversion
OHNE LLM-Layout (Phase 79).

Anlass (17.07.2026): der Anzeigen-Snapshot entstand bisher erst beim firma-pruefen-
Lauf — bis dahin ist die Anzeige oft schon tot (LinkedIn `expired_jd_redirect`, Phase 14), und
solange keine Prüfung lief, wirkte „Dateien & Dokumente" inkonsistent (Firmen-Dashboard geerbt,
job-eigener Snapshot fehlt). Muster = `transcript_report.py` (Phase 30/35): `render_basis()`
läuft deterministisch beim Ingest (pipeline.ingest, mit dem von `verify_jobs.check()`
mitgefangenen Anzeigentext), der spätere firma-pruefen-Lauf ERSETZT dieselbe Datei durch die
geprüfte Vollversion (Design-Entscheidung 7 der Spec — Pfad/Dateiname bleiben stabil).

Kopf nach der Phase-35-Typ-Tabelle (header.head): eyebrow „Anzeigen-Snapshot" → h1 = Stellentitel
→ sub „Firma · Portal" → Meta-Grid Ort/Modell/Gehalt/Veröffentlicht/Original-URL/Abrufdatum +
Quellen-Badge. Badge-Ehrlichkeit (Anti-Halluzinations-Linie, Design-Entscheidung 4): grün nur
wenn wirklich ein Anzeigentext vorliegt, sonst amber — nie beschönigen.

Phase 79 (08.08.2026, Echtfall — eine Stelle bekam nur eine ununterteilte Rohtext-
Karte, eine andere die gewünschte Gliederung, obwohl beide firma-pruefen erfolgreich durchlaufen
hatten): bis hierhin hatte NUR die Basis-Stufe einen deterministischen Erzeuger — die Vollversion
entstand freihändig im firma-pruefen-Lauf (Modell schreibt HTML nach Prosa-Anleitung in
SKILL.md) und driftete deshalb über Läufe hinweg (25 verschiedene „Aufgaben"-Überschriften-
Varianten im Bestand, Spec-Befund 2). `render_full()` schließt diese Lücke nach dem
`transcript_report`-Muster, aber STRENGER: das Modell liefert nur noch reine Inhalte
(`abschnitte`-Dict), das Layout (Reihenfolge, Überschriften, `<ul>`/`<details>`) kommt
vollständig aus diesem Modul.

Zwei Erzeugungswege:
  (a) render_basis(job, text=None) — deterministisch, OHNE LLM. Läuft automatisch beim Ingest.
  (b) render_full(job_id, abschnitte, quelle, hinweis=None, widersprueche=None) — vom Skill
      `firma-pruefen` aufgerufen: ERSETZT dieselbe Datei (Dateiname bleibt stabil), der bereits
      konservierte Volltext wandert dabei in einen zugeklappten `<details>`-Block (Konservierungs-
      Zweck des Snapshots — Anzeigen verschwinden, LinkedIn `expired_jd_redirect`).

CLI (aus backend/):
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.posting_snapshot backfill [--status "Neu,Prüfen,Beworben,Interview,Angebot"]
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.posting_snapshot nachholen [--job-id N | --status "…"] [--dry-run]
        → P2-75: holt fehlenden Anzeigentext nach (siehe `anzeigentext_sichern()` weiter unten).
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.posting_snapshot pruefen
        → Entscheidung 4 der Phase-79-Spec: meldet Jobs mit abgeschlossenem firma-pruefen-Lauf,
          deren Snapshot KEINE eigenen Abschnitte trägt (Negativ-Abgrenzung gegen die Basis-
          Abschnitte — NIE gegen einen erwarteten Überschriften-Namen, s. Messfalle in Spec-
          Befund 2) + die A/B/C-Verteilung über den geprüften Bestand. Rein lesend, kein
          Schreibzugriff. Exit-Code 1 bei Befunden, 0 sonst (Muster `report_check.main`).
"""
import datetime
import functools
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app.db import DATA_DIR, engine, init_db
from app.models import AgentTask, Job, JobLog
# Phase 79 Stufe E (Backfill `gliedern`): gemeinsamer HTML-Stripper statt einer zweiten
# Parser-Variante (Umsetzungshinweis der Spec) — wandelt Karten-Inhalt/Rohtext-Bruchstücke aus
# FRÜHEREN, freihändig geschriebenen Snapshots in reinen Text.
from pipeline.htmltext import entkleiden
from app.favicon import favicon_link
from app.sprache import datum, html_lang, tx, uebersetzt
from pipeline.bericht_stil import DRUCK_SEITENFARBE_BEHALTEN, bericht_css, fassungen

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Bewerbung_Mgmt_System/

# T1-Fix (Phase 79, Spec-Befund 3 — 08.08.2026 LIVE reproduziert): `_SNAPSHOT_DIR` zog bisher
# HART über PROJECT_ROOT, OHNE den Test-Override `BMS_DATA_DIR` (anders als `app.db.DATA_DIR`,
# s. dort). Damit schrieb JEDER Test, der über ingest/render_basis lief, in das ECHTE
# `data/job_postings/` — Live-Beleg: ein einzelner Lauf von `tests/test_ingest_repost_selber_
# lauf.py` erzeugte 4 neue Dateien (540 → 544, sofort wieder entfernt); Bestand: 265 von 540
# Dateien waren Testartefakte (`…Repost_Test_AG…`, `…repost_slug…`). Jetzt über `DATA_DIR`
# (app/db.py) — folgt automatisch `BMS_DATA_DIR`, WENN conftest.py es vor jedem app.*/
# pipeline.*-Import setzt (kritische Import-Reihenfolge, s. conftest.py-Docstring: `app.db`
# bindet `DATA_DIR` beim Modul-Import, nicht erst bei Nutzung).
_SNAPSHOT_DIR = DATA_DIR / "job_postings"

# CSS: das gemeinsame Thema kommt aus `pipeline/bericht_stil.py` (P2-72), mit den Werten des
# geltenden Designs. Hier steht nur, worin der Anzeigen-Snapshot davon abweicht — so, dass er genauso
# aussieht wie vor der Umstellung (Leitentscheidung 8: nichts „bereinigen“).
#   * Meta-Werte brechen um (lange Original-URL) und ihre Links bleiben in der Kopffarbe,
#   * Absätze in Karten bewahren Zeilenumbrüche (Anzeigentext), Listenpunkte tragen die Textfarbe,
#   * im Druck behält der aufgeklappte Volltext seinen Schatten (die Vorlage nimmt ihn dort weg).
_CSS_ZUSATZ = """
.head .meta .v{word-break:break-word}
.head .meta .v a{color:var(--auf-ink)}
.card p{white-space:pre-wrap}
ul.clean li{color:var(--text)}
@media print{details.volltext{box-shadow:var(--shadow)}}
""" + DRUCK_SEITENFARBE_BEHALTEN + "\n"


def _css() -> str:
    """Das CSS des Snapshots, bei jedem Aufruf mit dem Design, das gerade gilt."""
    return bericht_css(_CSS_ZUSATZ)


def _esc(s) -> str:
    return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _unesc(s: str) -> str:
    """Gegenstück zu `_esc()` — exakt umgekehrte Ersetzungsreihenfolge (Phase 79, gebraucht von
    `_lese_vorhandenen_volltext()` unten, um den in einer BESTEHENDEN Snapshot-Datei bereits
    konservierten Text zurückzugewinnen)."""
    return s.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")


def _meta_spalten(job: Job) -> list:
    """Ort/Modell · Gehalt · Veröffentlicht · Original-URL — leere Spalten weglassen (Typ-Tabelle)."""
    spalten = []
    ort_modell = " · ".join(t for t in (job.location, job.work_model) if t)
    if ort_modell:
        spalten.append((tx("Ort / Modell"), ort_modell))
    if job.salary:
        spalten.append((tx("Gehalt"), job.salary))
    if job.published_date:
        spalten.append((tx("Veröffentlicht"), job.published_date))
    if job.url:
        spalten.append((tx("Original-URL"), f'<a href="{_esc(job.url)}" target="_blank" rel="noreferrer">{_esc(job.url)}</a>'))
    return spalten


# P2-4 (Phase 67B): NICHT_PRUEFBAR (Bot-Block/Rate-Limit, HTTP 403/429/5xx) und LOGIN_WALL sind
# KEINE bestätigt toten Anzeigen — sie bedeuten nur „wir konnten nicht nachschauen". Vorher warf
# `tot = pr["befund"] not in ("OK", "INHALT_UNKLAR")` beide in denselben roten „nicht mehr
# abrufbar"-Topf wie TOT/ABGELAUFEN/UMGELEITET_GENERISCH, wo die Anzeige NACHWEISLICH weg oder
# umgezogen ist. Rot bleibt reserviert für diese bestätigten Fälle; Bot-Block/Login-Wall werden
# amber („nicht prüfbar"), dieselbe Farbe wie die bestehende Metadaten-Teilquelle, aber mit
# eigenem, ehrlichem Text (Design-Entscheidung 4 verlangt „nie beschönigen" — das gilt in beide
# Richtungen, auch gegen unnötiges Schlechterreden einer in Wahrheit noch lebenden Anzeige).
KONFIRMIERT_TOT_BEFUNDE = {"TOT", "ABGELAUFEN", "UMGELEITET_GENERISCH"}
NICHT_PRUEFBAR_BEFUNDE = {"NICHT_PRUEFBAR", "LOGIN_WALL"}


def _badge(hat_text: bool, tot: bool = False, nicht_pruefbar: bool = False) -> tuple:
    """(Label, CSS-Farbklasse fürs .dot). Nie beschönigen — Design-Entscheidung 4."""
    if tot:
        return ("rot", tx("Anzeige zum Nachzieh-Zeitpunkt nicht mehr abrufbar"))
    if nicht_pruefbar:
        return ("amber", tx("Nicht prüfbar (Bot-Schutz/Login-Wall beim Nachzieh-Lauf) — "
                            "dadurch NICHT als tot bestätigt, Status bleibt offen"))
    if hat_text:
        return ("grün", tx("Original automatisch beim Suchlauf abgerufen (mechanischer Live-Check)"))
    return ("amber", tx("Teilquelle: Suchlauf-Record (nur Metadaten, kein Anzeigentext)"))


# ── Phase 79: Vollversion-Gliederung (Entscheidung 1 der Spec) ─────────────────────────────
# Fünf Kanon-Abschnitte, feste Reihenfolge — Aufgaben → Anforderungen → Benefits → Über das
# Unternehmen → Kontext. Das Modell liefert nur noch INHALTE (Listen/Strings), niemals HTML;
# Reihenfolge/Überschriften/Markup kommen ausschließlich aus diesem Modul (Drift-Fix, s.
# Moduldocstring). Unbekannte Schlüssel sind ein Programmierfehler des Aufrufers → ValueError
# in `render_full()` (Tippfehler sollen knallen, nicht still verschwinden).
_ABSCHNITT_TITEL = {
    "aufgaben": "Aufgaben",
    "anforderungen": "Anforderungen",
    "benefits": "Benefits",
    "ueber_das_unternehmen": "Über das Unternehmen",
    "kontext": "Kontext",
}
_ABSCHNITT_REIHENFOLGE = ("aufgaben", "anforderungen", "benefits", "ueber_das_unternehmen", "kontext")

# `quelle`-Ampel für render_full — bewusst ASCII (Muster `deepdive._FIT_AMPEL_WERTE`), NICHT das
# an anderer Stelle in diesem Modul genutzte "grün" mit Umlaut (das ist nur die DARSTELLUNG).
# Die Badge-Ehrlichkeit (Anti-Halluzinations-Linie) bleibt Code-Text — das Modell liefert NUR die
# Kategorie, nie die Formulierung (Entscheidung 1 der Spec).
_QUELLE_WERTE = {"gruen", "amber", "rot"}
_QUELLE_LABEL = {"gruen": "grün", "amber": "amber", "rot": "rot"}
# Ampel-PUNKT zum Label (Wunsch vom 11.08.2026: „grün" stand nur als Wort da) — dieselben
# .dot-Klassen wie im Company-Fit-Kopf; Schlüssel ist das DARSTELLUNGS-Label (auch von
# _badge() geliefert), Fallback grau für unbekannte Alt-Labels.
_QUELLE_DOT = {"grün": "green", "amber": "amber", "rot": "red"}


def _quelle_text(quelle: str) -> str:
    """Anzeigetext der Quellen-Ampel in der Sprache, die beim Erzeugen gilt (nie beim Import)."""
    return {
        "gruen": tx("Original beim Firma-Prüfungslauf abgerufen"),
        "amber": tx("Teilquelle beim Firma-Prüfungslauf (kein wörtlicher Originaltext)"),
        "rot": tx("Anzeige beim Firma-Prüfungslauf nicht abrufbar"),
    }[quelle]


# Footer-Hinweise (Entscheidung 4 der Spec): sichtbarer Ausfall statt stiller Basis-Version — ein firma-pruefen-
# Lauf, der die Aufwertung ausließe, würde sonst denselben Footer-Text wie ein UNGEPRÜFTER Job
# zeigen und fiele nicht auf. Basis: "Automatisch bei Erfassung gesichert — Firma-Prüfung ausstehend",
# Vollversion: "Bei der Firma-Prüfung geprüft und gegliedert" (beide über tx() an der Stelle der Verwendung).


def _abschnitt_inhalt_html(wert) -> str:
    """Listen -> `<ul class="clean"><li>…</li></ul>`, Strings -> Absätze (Split an Leerzeilen,
    wie die bestehende Anzeigentext-Karte). `_esc()` auf JEDEM Element (Fremdtext = Daten,
    Phase 66B). Leere/fehlende Werte liefern `""` — der Aufrufer lässt den ganzen Abschnitt dann
    weg (Entscheidung 1: nie mit „–" auffüllen)."""
    if wert is None:
        return ""
    if isinstance(wert, (list, tuple)):
        items = "".join(f"<li>{_esc(x)}</li>" for x in wert if str(x).strip())
        return f'<ul class="clean">{items}</ul>' if items else ""
    text = str(wert).strip()
    if not text:
        return ""
    return "".join(f"<p>{_esc(p)}</p>" for p in text.split("\n\n") if p.strip())


_WIDERSPRUCH_SCHLUESSEL = {"feld", "anzeigentext", "eckdaten"}


def _widersprueche_html(widersprueche: Optional[list]) -> str:
    """Eigener Kartenblock „⚠️ Widersprüche" (Entscheidung 1, Reihenfolge nach den fünf Kanon-
    Abschnitten). Format je Eintrag — selbst entworfen, von der Spec nicht bis auf die Schlüssel
    festgelegt (nur der Freitext-Vorläufer `job.verify_note`-Anhang „KONFLIKT <Feld>: <Quelle A
    sagt X> vs. <Quelle B sagt Y>" aus Phase 21/models.py ist dokumentiert): jedes Element ist
    `{"feld": str, "anzeigentext": str, "eckdaten": str}` — beide Seiten WÖRTLICH, `_esc()` auf
    allen drei Werten (Fremdtext = Daten, Phase 66B)."""
    if not widersprueche:
        return ""
    zeilen = []
    for w in widersprueche:
        w = w or {}
        # Phase 79 (Abnahme-Härtung): rät der Aufrufer die Schlüsselnamen, entstünde sonst
        # STILL eine inhaltsleere Zeile („: Anzeigentext „“ vs. Eckdaten „“") — derselbe
        # Grund, aus dem `render_full` unbekannte `abschnitte`-Schlüssel ablehnt.
        unbekannt = set(w) - _WIDERSPRUCH_SCHLUESSEL
        if unbekannt:
            raise ValueError(
                f"Unbekannte Schlüssel in widersprueche: {sorted(unbekannt)} — erlaubt sind "
                f"{sorted(_WIDERSPRUCH_SCHLUESSEL)}")
        feld = _esc(w.get("feld") or "")
        anzeige = _esc(w.get("anzeigentext") or "")
        eckdaten = _esc(w.get("eckdaten") or "")
        # P2-15-Falle: schließendes deutsches Anführungszeichen ist U+201C, NIE ASCII '"' — als
        # \u-Escape geschrieben, damit kein Editor/Copy-Paste versehentlich das falsche Zeichen
        # einsetzt.
        zeilen.append(f"<p><b>{feld}:</b> "
                      + tx("Anzeigentext „{anzeige}“ vs. Eckdaten „{eckdaten}“", anzeige=anzeige, eckdaten=eckdaten)
                      + "</p>")
    if not zeilen:
        return ""
    return '<h2 class="sec">' + tx("⚠️ Widersprüche") + '</h2>\n<div class="card">' + "".join(zeilen) + "</div>"


def _build_html(job: Job, text: Optional[str], quelle_label: str, quelle_text: str,
                hinweis_banner: Optional[str] = None, abschnitte: Optional[dict] = None,
                widersprueche: Optional[list] = None, footer_hinweis: Optional[str] = None) -> str:
    """Phase 79: `abschnitte`/`widersprueche`/`footer_hinweis` sind NEU und rein additiv.
    `abschnitte=None` (Default) erzeugt EXAKT das alte Basis-Layout von vor Phase 79
    (Regressionsschutz, s. `tests/test_posting_snapshot_full.py` Punkt 6/`tests/
    test_daten_pfade.py`) — dieselbe Bedingung entscheidet auch über den Footer-Text
    (`footer_hinweis=None` → Basis-Footer).

    Ist `abschnitte` gesetzt (auch `{}`, das ist der Auslöser, nicht „hat Inhalt"), rendert die
    Funktion das Voll-Layout: die fünf Kanon-Abschnitte in fester Reihenfolge (Aufgaben →
    Anforderungen → Benefits → Über das Unternehmen → Kontext), optional „⚠️ Widersprüche", dann
    der Volltext — der wandert HIER in einen zugeklappten `<details>`-Block statt der offenen
    Anzeigentext-Karte (Konservierungs-Zweck des Snapshots bleibt, Entscheidung 1 der Spec:
    „zugeklappt heißt nicht gelöscht") —, zuletzt weiterhin Erfassungs-Kontext."""
    url_label = tx("Original-URL")
    meta_html = "".join(f'<div><p class="k">{_esc(k)}</p><p class="v">{v if k == url_label else _esc(v)}</p></div>'
                        for k, v in _meta_spalten(job))
    erzeugt = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    kontext_teile = []
    if job.source_note:
        kontext_teile.append(f"<p><b>{tx('Erfassung:')}</b> {_esc(job.source_note)}</p>")
    if job.verify_note:
        kontext_teile.append(f"<p><b>{tx('Vier-Augen-Beleg:')}</b> {_esc(job.verify_note)}</p>")
    kontext_html = "".join(kontext_teile) or "<p>" + tx("Kein Erfassungs-Kontext hinterlegt.") + "</p>"
    erfassungs_kontext_karte = f'<h2 class="sec">{tx("Erfassungs-Kontext")}</h2>\n<div class="card">{kontext_html}</div>'

    if abschnitte is None:
        # Heutiges Verhalten (Phase 38, vor Phase 79) — UNVERÄNDERT, byte-identisch.
        content_karten = [erfassungs_kontext_karte]
        if text:
            absaetze = "".join(f"<p>{_esc(p)}</p>" for p in text.split("\n\n") if p.strip())
            content_karten.insert(0, '<h2 class="sec">' + tx("Anzeigentext (automatisch extrahiert, unbereinigt)") + '</h2>\n'
                                      f'<div class="card">{absaetze}</div>')
    else:
        # Phase 79 Voll-Layout (Entscheidung 1): feste Reihenfolge, dann ggf. Widersprüche, dann
        # der konservierte Volltext zugeklappt, zuletzt weiterhin Erfassungs-Kontext.
        content_karten = []
        for schluessel in _ABSCHNITT_REIHENFOLGE:
            inhalt_html = _abschnitt_inhalt_html(abschnitte.get(schluessel))
            if not inhalt_html:
                continue
            titel = uebersetzt(_ABSCHNITT_TITEL[schluessel])
            content_karten.append(f'<h2 class="sec">{titel}</h2>\n<div class="card">{inhalt_html}</div>')
        widerspruch_karte = _widersprueche_html(widersprueche)
        if widerspruch_karte:
            content_karten.append(widerspruch_karte)
        if text:
            content_karten.append('<details class="volltext">\n<summary>' + tx("Volltext (unbereinigt)") + '</summary>\n'
                                  f'<pre>{_esc(text)}</pre>\n</details>')
        content_karten.append(erfassungs_kontext_karte)

    banner_html = (f'<div class="caveat"><b>{tx("Hinweis:")}</b> {_esc(hinweis_banner)}</div>' if hinweis_banner else "")
    footer_text = footer_hinweis or tx("Automatisch bei Erfassung gesichert — Firma-Prüfung ausstehend")

    titel = tx("Anzeigen-Snapshot · {titel}", titel=_esc(job.title))
    _FAVICON = favicon_link()      # P2-72: Icon des geltenden Designs, bei jedem Snapshot frisch
    return f"""<!DOCTYPE html>
<html lang="{html_lang()}">
<head>
<meta charset="utf-8">{_FAVICON}
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titel}</title>
<style>{_css()}</style>
</head>
<body>
<div class="wrap">
  <header class="head">
    <p class="eyebrow">{tx("Anzeigen-Snapshot")}</p>
    <h1>{_esc(job.title)}</h1>
    <p class="sub">{_esc(" · ".join(t for t in (job.company_name, job.portal) if t))}</p>
    <div class="meta">
      {meta_html}
      <div><p class="k">{tx("Abrufdatum")}</p><p class="v">{erzeugt[:10]}</p></div>
      <div><p class="k">{tx("Quelle")}</p><p class="v"><span class="dot {_QUELLE_DOT.get(quelle_label, "grau")}"></span>{_esc(uebersetzt(quelle_label))} — {_esc(quelle_text)}</p></div>
    </div>
  </header>

  {banner_html}

  {"".join(content_karten)}

  <div class="foot">
    <span>{tx("Bewerbungs-Mgmt · erzeugt am {datum}", datum=erzeugt)}</span>
    <span>{_esc(footer_text)}</span>
  </div>
</div>
</body>
</html>
"""


def _freier_name(ordner: Path, fname: str) -> str:
    """Kollision → _2, _3 … (identisches Muster wie transcript_report.py/app/main.py)."""
    if not (ordner / fname).exists():
        return fname
    stem, punkt, ext = fname.rpartition(".")
    n = 2
    while (ordner / f"{stem}_{n}{punkt}{ext}").exists():
        n += 1
    return f"{stem}_{n}{punkt}{ext}"


def _ziel_dateiname(job: Job) -> str:
    """Stabiler Dateiname: existiert bereits ein posting_snapshot_path, dessen Basisnamen
    wiederverwenden (spätere firma-pruefen-Läufe ERSETZEN dieselbe Datei) — sonst neu berechnen."""
    from app.naming import report_filename
    if job.posting_snapshot_path:
        return Path(job.posting_snapshot_path).name
    base = report_filename("Anzeige", job.company_name, job.title)
    return _freier_name(_SNAPSHOT_DIR, f"{base}.html")


# ── Phase 79: bereits konservierten Volltext aus der BESTEHENDEN Datei zurückgewinnen ──────
# `render_full()` bekommt bewusst KEINEN eigenen `text`-Parameter (anders als `render_basis`) —
# das Modell soll die Anzeige nicht ein zweites Mal komplett durchreichen, nur um sie unverändert
# zu konservieren. Stattdessen liest `render_full()` den Volltext aus der Datei, die es gleich
# ersetzt (Muster `transcript_report.render_full`, das `t.file_path` — den separat abgelegten
# Rohtext — bei JEDEM Aufruf neu einliest statt ihn als Parameter zu verlangen). Zwei Quellen,
# erste passende gewinnt: (1) ein bereits vorhandener Volltext-<details>-Block (zweiter
# render_full-Lauf auf einem schon gegliederten Snapshot — Idempotenz), (2) die Phase-38-Basis-
# Anzeigentext-Karte (erster render_full-Lauf nach render_basis). Kein Snapshot/keine Datei/nie
# ein Anzeigentext vorhanden (rot-Badge-Fall) → None, NICHT erfinden.
#
# Berichte bleiben in der Sprache, in der sie entstanden: Die Überschriften werden deshalb in beiden Fassungen
# gesucht (deutsch und englisch, `fassungen()`), nicht nur in der Sprache, die gerade gilt.
def _oder(*deutsche_texte: str) -> str:
    """Regex-Alternative aus allen Fassungen der Texte (jeweils maskiert)."""
    return "|".join(re.escape(f) for t in deutsche_texte for f in fassungen(t))


@functools.lru_cache(maxsize=None)
def _volltext_details_re():
    return re.compile(r"<summary>(?:" + _oder("Volltext (unbereinigt)") + r")</summary>\s*<pre>(.*?)</pre>", re.S)


@functools.lru_cache(maxsize=None)
def _anzeigentext_karte_re():
    return re.compile(
        r'<h2 class="sec">(?:' + _oder("Anzeigentext (automatisch extrahiert, unbereinigt)")
        + r')</h2>\s*<div class="card">(.*?)</div>', re.S)


_P_RE = re.compile(r"<p>(.*?)</p>", re.S)


def _lese_vorhandenen_volltext(job: Job) -> Optional[str]:
    if not job.posting_snapshot_path:
        return None
    pfad = _SNAPSHOT_DIR / Path(job.posting_snapshot_path).name
    if not pfad.is_file():
        return None
    html = pfad.read_text(encoding="utf-8", errors="replace")
    m = _volltext_details_re().search(html)
    if m:
        return _unesc(m.group(1)) or None
    m = _anzeigentext_karte_re().search(html)
    if m:
        text = "\n\n".join(_unesc(p) for p in _P_RE.findall(m.group(1)))
        return text or None
    return None


def render_basis(job: Job, text: Optional[str] = None, hinweis: Optional[str] = None) -> Optional[str]:
    """Deterministischer Basis-Snapshot OHNE LLM (Phase 38) — läuft automatisch bei jedem
    Ingest-Treffer mit URL. `text` ist der von `verify_jobs.check()` mitgefangene Anzeigentext
    (None bei Metadaten-Only-Treffern, z. B. QUELLE_VERTRAUT ohne prüfbaren Live-Check).
    `hinweis` (P2-75, optional): Callout-Banner im Kopf, gebraucht von `anzeigentext_sichern()`
    für den Vermerk „nachgeholt“; ohne Angabe bleibt die Ausgabe byte-identisch.
    Setzt `job.posting_snapshot_path`, committet NICHT selbst (Aufrufer verwaltet die Session).
    Gibt den relativen Pfad zurück, oder None bei einem Fehler (bricht den Ingest NIE ab —
    Design-Entscheidung 6: ein Job ohne Snapshot ist der heutige Zustand, kein Schaden)."""
    try:
        label, quelle_text = _badge(bool(text))
        html = _build_html(job, text, label, quelle_text, hinweis_banner=hinweis)
        _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        fname = _ziel_dateiname(job)
        (_SNAPSHOT_DIR / fname).write_text(html, encoding="utf-8")
        rel = f"data/job_postings/{fname}"
        job.posting_snapshot_path = rel
        return rel
    except Exception as e:                                  # noqa: BLE001 — Snapshot ist Kür, kein Muss
        print(f"[posting_snapshot] Fehler bei Job {job.id}: {e}", file=sys.stderr)
        return None


def render_full(job_id: int, abschnitte: dict, quelle: str, hinweis: Optional[str] = None,
                widersprueche: Optional[list] = None) -> dict:
    """Ersetzt den Snapshot unter `posting_snapshot_path` (legt ihn an, falls noch keiner
    existiert — `_ziel_dateiname()` wie bisher) durch die gegliederte Vollversion. Vom Skill
    `firma-pruefen` aufgerufen, NACHDEM die Anzeige geprüft und in `abschnitte` zerlegt wurde
    (Phase 79, Echtfall, 08.08.2026 — s. Moduldocstring).

    `abschnitte`: `{"aufgaben": [str, …], "anforderungen": [str, …], "benefits": [str, …],
    "ueber_das_unternehmen": str, "kontext": str}` — Listen werden als `<ul>` gerendert, Strings
    als Absätze. Unbekannte Schlüssel → `ValueError` (Tippfehler sollen knallen). Leere/fehlende
    Abschnitte werden weggelassen, nie mit „–" gefüllt.

    `quelle`: `"gruen"|"amber"|"rot"` — steuert NUR die Kategorie, der Anzeigetext kommt aus dem
    Code (`_QUELLE_LABEL`/`_quelle_text()`), NICHT vom Modell frei betextet (Badge-Ehrlichkeit,
    Anti-Halluzinations-Linie). Ungültiger Wert → `ValueError` (Muster `deepdive._FIT_AMPEL_WERTE`).

    `hinweis` (optional): Callout-Banner (z. B. Portal-geschlossen-Hinweis), landet wie bisher in
    `.caveat`. `widersprueche` (optional): s. `_widersprueche_html()`.

    Setzt den Footer auf „Bei der Firma-Prüfung geprüft und gegliedert" (Entscheidung 4 — ein
    ausgelassener Gliederungs-Lauf fällt dadurch sichtbar auf, statt als stille Basis-Version
    durchzugehen). Rückgabe: `{"job_id", "posting_snapshot_path", "abschnitte": [erkannte
    Schlüssel, feste Reihenfolge]}`."""
    if quelle not in _QUELLE_WERTE:
        raise ValueError(f"quelle muss gruen|amber|rot sein, nicht {quelle!r}")
    abschnitte = abschnitte or {}
    unbekannt = set(abschnitte) - set(_ABSCHNITT_TITEL)
    if unbekannt:
        raise ValueError(f"Unbekannte abschnitte-Schlüssel: {sorted(unbekannt)} — erlaubt sind nur "
                          f"{sorted(_ABSCHNITT_TITEL)}")

    init_db()
    with Session(engine) as s:
        job = s.get(Job, job_id)
        if not job:
            raise SystemExit(f"Job {job_id} nicht gefunden")

        text = _lese_vorhandenen_volltext(job)
        label, quelle_text = _QUELLE_LABEL[quelle], _quelle_text(quelle)
        html = _build_html(job, text, label, quelle_text, hinweis_banner=hinweis,
                           abschnitte=abschnitte, widersprueche=widersprueche,
                           footer_hinweis=tx("Bei der Firma-Prüfung geprüft und gegliedert"))
        _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        fname = _ziel_dateiname(job)
        (_SNAPSHOT_DIR / fname).write_text(html, encoding="utf-8")
        rel = f"data/job_postings/{fname}"
        job.posting_snapshot_path = rel
        s.add(job)
        s.commit()

        erkannt = [k for k in _ABSCHNITT_REIHENFOLGE if _abschnitt_inhalt_html(abschnitte.get(k))]
        return {"job_id": job.id, "posting_snapshot_path": rel, "abschnitte": erkannt}


def backfill(status_csv: str) -> dict:
    """Einmaliger Nachzieh-Lauf (Phase 38 Stufe C) für Bestands-Jobs ohne Snapshot: Live-Nachfetch
    der URL (Anzeige lebt noch → grüner Snapshot mit Text; tot/Login-Wall/keine URL → ehrlicher
    Metadaten-Snapshot amber/rot mit Banner). Committet je Job einzeln (ein Fehler stoppt nicht
    den ganzen Lauf)."""
    from pipeline.verify_jobs import check_url

    init_db()
    stat = [s.strip() for s in (status_csv or "").split(",") if s.strip()]
    done = skipped = errors = 0
    zeilen = []
    with Session(engine) as s:
        q = select(Job).where(Job.deleted_at.is_(None), Job.posting_snapshot_path.is_(None))
        if stat:
            q = q.where(Job.status.in_(stat))
        jobs = list(s.exec(q).all())

        for i, job in enumerate(jobs):
            if not job.url:
                text, tot, nicht_pruefbar = None, False, False
            else:
                pr = check_url(job.url, job.company_name, job.title, return_text=True)
                text = pr.get("anzeigentext")
                befund = pr["befund"]
                # P2-4: NICHT explizit als "alles außer OK/INHALT_UNKLAR ist tot" werten (das war
                # der Bug) — nur die bestätigt-tot-Befunde geben rot, Bot-Block/Login-Wall geben
                # ein eigenes, neutrales amber.
                tot = befund in KONFIRMIERT_TOT_BEFUNDE
                nicht_pruefbar = befund in NICHT_PRUEFBAR_BEFUNDE
            try:
                anzeige_tot = bool(job.url) and tot
                anzeige_nicht_pruefbar = bool(job.url) and nicht_pruefbar
                label, quelle_text = _badge(bool(text), tot=anzeige_tot, nicht_pruefbar=anzeige_nicht_pruefbar)
                if anzeige_tot:
                    banner = tx("Anzeige beim Nachzieh-Lauf nicht mehr abrufbar — nur Metadaten aus "
                                "der Erfassung.")
                elif anzeige_nicht_pruefbar:
                    banner = tx("Anzeige beim Nachzieh-Lauf nicht prüfbar (Bot-Schutz/Login-Wall) — "
                                "Status unklar, NICHT als tot bestätigt. Nur Metadaten aus der Erfassung.")
                else:
                    banner = None
                html = _build_html(job, text, label, quelle_text, hinweis_banner=banner)
                _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
                fname = _ziel_dateiname(job)
                (_SNAPSHOT_DIR / fname).write_text(html, encoding="utf-8")
                job.posting_snapshot_path = f"data/job_postings/{fname}"
                s.add(job)
                s.commit()
                done += 1
                befund_label = "OK" if text else ("TOT" if tot else ("NICHT_PRUEFBAR" if nicht_pruefbar else "METADATEN"))
                zeilen.append((job.id, (job.company_name or "")[:24], befund_label))
            except Exception as e:                            # noqa: BLE001
                errors += 1
                print(f"[posting_snapshot backfill] Job {job.id}: {e}", file=sys.stderr)
            if job.url and i < len(jobs) - 1:
                time.sleep(0.5)                                # kein Hammering

    print("-" * 52, file=sys.stderr)
    for jid, comp, befund in zeilen:
        print(f"{jid:>4}  {comp:<24}  {befund}", file=sys.stderr)
    return {"jobs_gesamt": len(jobs), "gesichert": done, "fehler": errors}


# ── Phase 79, CLI-Modus `pruefen` (Entscheidung 4 der Spec) ────────────────────────────────
# Rein lesend — KEIN Schreibzugriff auf DB oder Dateien. Bewusst NICHT in pipeline/report_check.py
# gebaut (das ist ein reiner HTML/CSS-Checker `pruefe(html) -> list` ohne DB-Zugriff, s. dessen
# Modulkopf) — eine DB-gestützte Bestandsregel („welche Jobs mit abgeschlossenem firma-pruefen-
# Lauf haben einen ungegliederten Snapshot?") gehört hierher, nicht dorthin.
def _basis_headings() -> set:
    """Die Überschriften der Basis-Abschnitte in beiden Sprachen (s. `fassungen()`)."""
    return {f for t in ("Anzeigentext (automatisch extrahiert, unbereinigt)", "Erfassungs-Kontext")
            for f in fassungen(t)}


_H2_SEC_RE = re.compile(r'<h2 class="sec">(.*?)</h2>', re.S)


def _snapshot_headings(html: str) -> set:
    """Alle `h2.sec`-Überschriften im Snapshot-HTML (house style, s. `bericht_stil`/SKILL.md Schritt 3b:
    jeder Snapshot — ob deterministisch oder freihändig vom Modell vor Phase 79 erzeugt —
    verwendet dieselbe `<h2 class="sec">`-Klasse für Abschnittsüberschriften)."""
    return {_unesc(m.strip()) for m in _H2_SEC_RE.findall(html) if m.strip()}


def _klassifiziere_snapshot(html: str) -> str:
    """Negativ-Abgrenzung gegen die BEKANNTEN Basis-Abschnitte (Messfalle in Spec-Befund 2 — NIE
    gegen einen erwarteten Überschriften-Namen prüfen, das lieferte beim ersten Anlauf 56 %
    statt der tatsächlichen 83 %). 'C' = trägt NUR die Basis-Abschnitte (gar nicht gegliedert),
    'A' = zusätzlich exakt „Aufgaben" UND „Anforderungen" (die Referenz für diesen Zustand),
    'B' = irgendetwas anderes über die Basis hinaus (gegliedert, aber abweichend benannt/
    zusammengefasst — 25 Varianten allein für die Aufgaben-Überschrift im Bestand)."""
    eigene = _snapshot_headings(html) - _basis_headings()
    if not eigene:
        return "C"
    if all(any(f in eigene for f in fassungen(t)) for t in ("Aufgaben", "Anforderungen")):
        return "A"
    return "B"


def pruefen() -> dict:
    """Jobs mit abgeschlossenem `firma-pruefen`-Lauf (`AgentTask.kind == "firma-pruefen"`,
    `status == "done"`) gegen ihren Snapshot prüfen. Rückgabe: `{"verteilung": {"A": n, "B": n,
    "C": n}, "befunde": [(job_id, firma, titel), …]}` — `befunde` sind die Gruppe-C-Jobs (kein
    eigener Abschnitt trotz abgeschlossener Prüfung, s. Ziel 2 der Spec: „Ein firma-pruefen-Lauf,
    der die Aufwertung ausläss, fällt auf statt still durchzugehen")."""
    init_db()
    verteilung = {"A": 0, "B": 0, "C": 0}
    befunde = []
    with Session(engine) as s:
        tasks = s.exec(select(AgentTask).where(AgentTask.kind == "firma-pruefen",
                                               AgentTask.status == "done")).all()
        job_ids = sorted({t.job_id for t in tasks if t.job_id is not None})
        for job_id in job_ids:
            job = s.get(Job, job_id)
            if not job or job.deleted_at or not job.posting_snapshot_path:
                continue
            pfad = _SNAPSHOT_DIR / Path(job.posting_snapshot_path).name
            if not pfad.is_file():
                continue
            html = pfad.read_text(encoding="utf-8", errors="replace")
            gruppe = _klassifiziere_snapshot(html)
            verteilung[gruppe] += 1
            if gruppe == "C":
                befunde.append((job.id, (job.company_name or "")[:30], (job.title or "")[:40]))
    return {"verteilung": verteilung, "befunde": befunde}


def _pruefen_main() -> int:
    ergebnis = pruefen()
    v = ergebnis["verteilung"]
    gesamt = sum(v.values())
    print(f"Geprüfte Jobs mit abgeschlossenem firma-pruefen-Lauf: {gesamt}")
    print(f"Verteilung: A (sauber getrennt) = {v['A']} · B (gegliedert, abweichend benannt) = {v['B']} "
          f"· C (gar nicht gegliedert) = {v['C']}")
    if ergebnis["befunde"]:
        print(f"\n{len(ergebnis['befunde'])} Job(s) mit abgeschlossenem firma-pruefen-Lauf, aber OHNE "
              f"eigene Abschnitte (Snapshot nicht gegliedert):")
        for jid, comp, titel in ergebnis["befunde"]:
            print(f"  Job {jid:>4}  {comp:<30}  {titel}")
        return 1
    print("Keine Befunde — alle geprüften Jobs mit firma-pruefen-Lauf tragen einen gegliederten Snapshot.")
    return 0


# ── Phase 79, Stufe E: Backfill-CLI `gliedern` (Spec-Entscheidung 7) ────────────────────────
# Zwei deterministische Wege OHNE LLM für Jobs, deren Snapshot vor Stufe A entstand (das Modell
# schrieb das HTML damals freihändig, s. Moduldocstring) und deshalb NICHT im Kanon-Format
# vorliegt:
#   E1 — Gruppe B: eigene `<h2 class="sec">`-Abschnitte samt Inhalt vorhanden, nur abweichend
#        benannt (25 Varianten allein für „Aufgaben" im Bestand, Spec-Befund 2) -> Überschrift
#        aufs Kanon-Mapping abbilden, Inhalt UNVERÄNDERT übernehmen (verlustfrei).
#   E2 — Gruppe C + Container-Fälle: keine eigenen Abschnitte ODER nur eine generische
#        Sammel-Überschrift (`Strukturierte Wiedergabe`, `Job Summary`, `Die Rolle` …) -> den
#        konservierten Volltext per DE/EN-Überschriften-Heuristik teilen.
# Beide Wege rufen am Ende dasselbe `render_full()` (Stufe A, unverändert) — hier entsteht KEIN
# zweiter Schreibweg. „Ehrlichkeit vor Vollständigkeit" (Spec-Entscheidung 7): erkennt keiner der
# beiden Wege etwas Belastbares (keine Aufgaben/Anforderungen-Überschrift, kein wiederfindbarer
# Volltext, keine erkennbare Quellen-Ampel im alten Kopf), bleibt die Datei UNANGETASTET — der
# Job wird namentlich als „nicht gliederbar" gemeldet, nie geraten oder paraphrasiert.

# E1: Überschrift -> Kanon-Schlüssel, toleranter Teilstring-Treffer (die Überschriften tragen im
# Bestand Zusätze wie „(wörtlich)"/„(Auszüge)"/„(Key Responsibilities)" — deshalb `re.search`,
# nicht `re.fullmatch`). Reihenfolge ist die Prüfreihenfolge; „aufgaben" zuerst, weil mehrdeutige
# Altbestände wie „Job Requirements (Aufgaben)" das deutsche Wort im Titel führen — das
# literale „Aufgaben" im Bestandsheading gewinnt gegen das generische „Requirements".
_E1_ZIEL_MUSTER = (
    ("aufgaben", re.compile(r"(?i)aufgaben|responsibilit|your\s*task|what\s*you.?ll\s*do|"
                             r"your\s*impact|key\s*responsibilit|next\s*challenge")),
    ("anforderungen", re.compile(r"(?i)anforderung|ihr\s*profil|qualifikation|qualification|"
                                  r"what\s*you\s*bring|requirement")),
    ("benefits", re.compile(r"(?i)benefit|wir\s*bieten|what\s*we\s*offer|we\s*offer")),
    ("ueber_das_unternehmen", re.compile(r"(?i)über\s*(das\s*unternehmen|uns)|"
                                          r"about\s*(us|the\s*company)|unternehmen")),
)
# Strukturelle/redundante Überschriften — NIE Inhalt (auch nicht als Kontext-Rest): der Volltext-
# Block wird separat gerettet (`_lege_volltext_kandidaten()`), Widersprüche/Strukturierte
# Merkmale stehen bereits in `job.verify_note` (landet automatisch in der Erfassungs-Kontext-
# Karte, s. `_build_html()`).
_E1_AUSSCHLUSS_MUSTER = re.compile(r"(?i)volltext|full\s*text|widerspr|contradiction|strukturierte\s+merkmale")
# Echte Misch-Überschrift („Aufgaben & Anforderungen", ein Bestandsbeispiel) — im
# Original NIE sortenrein getrennt, deshalb NICHT einer der beiden Kategorien zuschlagen (das
# behauptete Trennung, die es im Original gar nicht gab), sondern in `kontext` belassen. Anders
# als z. B. „Job Requirements (Aufgaben)" — dort ist die Parenthese eine Klarstellung EINER
# Kategorie, kein Verbund zweier — deshalb ein eigenes, engeres Muster statt „matcht mehrere
# Ziel-Muster gleichzeitig" (das träfe auch harmlose Zufallstreffer wie „Benefits (Deine
# Zukunft bei uns im Unternehmen)").
_E1_MISCHUEBERSCHRIFT_MUSTER = re.compile(
    r"(?i)aufgaben\s*(?:&|/|und|and)\s*anforderungen|anforderungen\s*(?:&|/|und|and)\s*aufgaben")

_UL_RE = re.compile(r"<ul[^>]*>(.*?)</ul>", re.S)
_LI_RE = re.compile(r"<li[^>]*>(.*?)</li>", re.S)
_P_TOL_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.S)
_H2_SPLIT_RE = re.compile(r'<h2 class="sec">')


def _h2_sec_bloecke(html: str) -> list:
    """Zerlegt den Karten-Bereich in `(Überschrift, Inhalt-bis-zur-nächsten-Überschrift)`-Paare —
    dieselbe `<h2 class="sec">`-Trennmarke wie `_snapshot_headings()`/`_H2_SEC_RE` (house style),
    hier aber MIT dem Inhalt zwischen zwei Überschriften statt nur dem Überschriften-Text."""
    teile = _H2_SPLIT_RE.split(html)[1:]              # [0] ist alles vor der ersten Überschrift
    bloecke = []
    for teil in teile:
        m = re.match(r"(.*?)</h2>(.*)", teil, re.S)
        if not m:
            continue
        bloecke.append((_unesc(m.group(1).strip()), m.group(2)))
    return bloecke


def _karten_inhalt(card_html: str):
    """`<ul>` -> `list[str]`, sonst `<p>`-Absätze -> `str` (Absatz-Trenner `\\n\\n`), sonst
    (freihändiges Markup ohne `<ul>`/`<p>`) der entkleidete Rohtext. `entkleiden()` statt
    eigenem Tag-Stripping (Umsetzungshinweis der Spec — kein zweiter HTML-Parser)."""
    ul_m = _UL_RE.search(card_html)
    if ul_m:
        items = [entkleiden(li).strip() for li in _LI_RE.findall(ul_m.group(1))]
        items = [i for i in items if i]
        if items:
            return items
    absaetze = [entkleiden(p).strip() for p in _P_TOL_RE.findall(card_html)]
    absaetze = [a for a in absaetze if a]
    if absaetze:
        return "\n\n".join(absaetze)
    text = entkleiden(card_html).strip()
    return text or None


def _merge_abschnitt(ziel: dict, schluessel: str, wert) -> None:
    """Zweite Quelle für denselben Kanon-Schlüssel (selten) additiv zusammenführen statt zu
    überschreiben — Listen werden verkettet, alles andere als Text verbunden."""
    vorhanden = ziel.get(schluessel)
    if vorhanden is None:
        ziel[schluessel] = wert
        return
    if isinstance(vorhanden, list) and isinstance(wert, list):
        ziel[schluessel] = vorhanden + wert
        return

    def _txt(w):
        return "\n".join(w) if isinstance(w, list) else str(w)

    ziel[schluessel] = _txt(vorhanden) + "\n\n" + _txt(wert)


def _e1_abschnitte(html: str) -> Optional[dict]:
    """Gruppe B (Spec-Entscheidung 7): vorhandene `<h2 class="sec">`-Abschnitte samt Inhalt
    einlesen, Überschrift per Mapping auf den Kanon abbilden. E1-fähig NUR, wenn dabei
    mindestens EIN Abschnitt eindeutig als Aufgaben ODER Anforderungen erkannt wird — die
    inhaltliche Trennung hat dann tatsächlich stattgefunden, nur die Benennung weicht ab. Ohne
    einen solchen Treffer ist es ein Container-Fall (das Modell hat nie in Aufgaben/
    Anforderungen getrennt, z. B. „Strukturierte Wiedergabe"/„Job Summary"/„Die Rolle") -> gehört
    zu E2, `None`. Nicht zuordenbare, aber inhaltlich echte Zusatz-Überschriften (z. B. „Gehalt",
    „Position im Überblick") fallen NICHT weg, sondern sammeln sich unverändert in `kontext` —
    verlustfrei, wie von der Spec verlangt."""
    ergebnis: dict = {}
    kontext_teile = []
    fund_kern = False
    for titel, inhalt_html in _h2_sec_bloecke(html):
        if _E1_AUSSCHLUSS_MUSTER.search(titel):
            continue
        ziel = None
        if not _E1_MISCHUEBERSCHRIFT_MUSTER.search(titel):
            for schluessel, muster in _E1_ZIEL_MUSTER:
                if muster.search(titel):
                    ziel = schluessel
                    break
        karten_m = re.search(r'<div class="card">(.*?)</div>', inhalt_html, re.S)
        if not karten_m:
            continue
        wert = _karten_inhalt(karten_m.group(1))
        if not wert:
            continue
        if ziel in ("aufgaben", "anforderungen"):
            fund_kern = True
        if ziel:
            _merge_abschnitt(ergebnis, ziel, wert)
        else:
            kontext_teile.append("\n".join(wert) if isinstance(wert, list) else wert)
    if not fund_kern:
        return None
    if kontext_teile:
        _merge_abschnitt(ergebnis, "kontext", "\n\n".join(kontext_teile))
    return ergebnis or None


# E2: Überschriften-Heuristik auf dem KONSERVIERTEN VOLLTEXT (Rohtext, keine Tags) — genau die
# vier Kategorien aus der Spec, Zeilen-Match statt Teilstring-Match (eine Zeile MUSS im
# Wesentlichen NUR die Überschrift sein, sonst würde z. B. ein Aufzählungspunkt „Requirements: 5+
# Jahre Erfahrung…" fälschlich als eigene Überschrift erkannt). `kontext` bleibt hier bewusst
# LEER — ohne eigene Kontext-Überschrift im Rohtext gäbe es nur Geratenes, und der komplette
# Volltext bleibt ohnehin im `<details>`-Block erhalten (kein Verlust).
_E2_HEADING_MUSTER = (
    ("aufgaben", re.compile(r"(?i)^(ihre|deine?)?\s*aufgaben\b|^responsibilit(y|ies)?\b|"
                             r"^what\s+you.?ll\s+do\b|^(dein|your)\s+impact\b|^key\s+responsibilit\w*\b")),
    ("anforderungen", re.compile(r"(?i)^(ihr|dein)?\s*profil\b|^anforderungen\b|^qualifikationen?\b|"
                                  r"^qualifications?\b|^what\s+you\s+bring\b|^requirements?\b")),
    ("benefits", re.compile(r"(?i)^benefits?\b|^wir\s+bieten\b|^what\s+we\s+offer\b")),
    ("ueber_das_unternehmen", re.compile(r"(?i)^über\s+(uns|die\s+firma|das\s+unternehmen)\b|"
                                          r"^about\s+us\b")),
)
_E2_MAX_HEADING_LEN = 60
_BULLET_PREFIX_RE = re.compile(r"^[•▪◦‣·\-\*]\s+")


def _e2_abschnitte(text: str) -> Optional[dict]:
    """Gruppe C + Container-Fälle (Spec-Entscheidung 7): den konservierten Volltext zeilenweise
    nach den vier Kern-Überschriften absuchen und dazwischen aufteilen. Kein einziger Treffer ->
    `None` (der Aufrufer meldet den Job als „nicht gliederbar" statt zu raten)."""
    zeilen = text.splitlines()
    grenzen = []
    for i, zeile in enumerate(zeilen):
        kandidat = zeile.strip().rstrip(":： ").strip()
        if not kandidat or len(kandidat) > _E2_MAX_HEADING_LEN:
            continue
        for schluessel, muster in _E2_HEADING_MUSTER:
            if muster.match(kandidat):
                grenzen.append((i, schluessel))
                break
    if not grenzen:
        return None
    ergebnis: dict = {}
    for idx, (start, schluessel) in enumerate(grenzen):
        ende = grenzen[idx + 1][0] if idx + 1 < len(grenzen) else len(zeilen)
        block = [_BULLET_PREFIX_RE.sub("", z.strip()) for z in zeilen[start + 1:ende] if z.strip()]
        if not block:
            continue
        wert = "\n\n".join(block) if schluessel == "ueber_das_unternehmen" else block
        _merge_abschnitt(ergebnis, schluessel, wert)
    return ergebnis or None


# Volltext-Rettung aus FRÜHEREN, freihändig geschriebenen Snapshots — toleranter als
# `_lese_vorhandenen_volltext()` (die exakt auf den NEUEN, deterministischen Wortlaut von
# Stufe A passt): im Bestand variiert allein der `<summary>`-Text der Altfassungen frei
# („Original-Text anzeigen/verbergen", „…, inkl. LinkedIn-Rahmen" …). `_lese_vorhandenen_
# volltext()` bleibt UNVERÄNDERT (Dateiliste) — diese Funktion ist rein additiv daneben.
_LEGACY_VOLLTEXT_DETAILS_RE = re.compile(r"<details[^>]*>.*?<pre>(.*?)</pre>.*?</details>", re.S)
_LEGACY_VOLLTEXT_HEADING_RE = re.compile(r"(?i)volltext|full\s*text")


def _lege_volltext_kandidaten(html: str) -> Optional[str]:
    """Reihenfolge, erster Treffer gewinnt: (1) IRGENDein `<details>…<pre>…</pre>…</details>` —
    unabhängig vom `<summary>`-Wortlaut, (2) eine `<h2 class="sec">`-Überschrift mit dem Wort
    „Volltext" darin, deren Karte gelesen wird (`<pre>` bevorzugt, sonst `entkleiden()`),
    (3) Fallback auf die bestehende Phase-38-Anzeigentext-Karte (`_anzeigentext_karte_re()`, falls
    sie unverändert stehen blieb). Kein Fund -> `None`, NICHT erfinden."""
    m = _LEGACY_VOLLTEXT_DETAILS_RE.search(html)
    if m:
        text = _unesc(m.group(1)).strip()
        if text:
            return text
    for titel, inhalt_html in _h2_sec_bloecke(html):
        if not _LEGACY_VOLLTEXT_HEADING_RE.search(titel):
            continue
        pre_m = re.search(r"<pre>(.*?)</pre>", inhalt_html, re.S)
        if pre_m:
            text = _unesc(pre_m.group(1)).strip()
            if text:
                return text
        text = entkleiden(inhalt_html).strip()
        if text:
            return text
    m = _anzeigentext_karte_re().search(html)
    if m:
        text = "\n\n".join(_unesc(p) for p in _P_RE.findall(m.group(1)))
        if text.strip():
            return text
    return None


# Quellen-Ampel aus dem KOPF eines bestehenden Snapshots zurückgewinnen (Spec-Entscheidung 7:
# „quelle beim Re-Rendern aus dem vorhandenen Snapshot-Kopf übernehmen, ein Backfill darf aus
# amber/rot NIE grün machen"). Toleriert die im Bestand beobachteten Varianten — der Snapshot-
# Kopf ist über die Projektgeschichte MEHRFACH umgebaut worden (aktuell: `header.head`/`.meta`
# mit Label „Quelle"/„Quellen-Badge" + Wortlaut grün/amber/rot; älter: `header.hero`/`.badges`
# mit `<span class="pill amber-badge">`/🟠-Emoji, KEIN „Quelle"-Label). Reihenfolge, erster
# Treffer gewinnt: (1) Ampel-Wort/-Emoji nahe einem „Quelle"-Label, (2) IRGENDein Ampel-Token
# innerhalb des `<header>`-Blocks — der ist kurz genug, dass ein Treffer dort praktisch nie etwas
# anderes bedeutet als die Quellen-Ampel.
_QUELLE_ZEILE_RE = re.compile(r'(?i)(?:Quelle|Source)[^<]{0,40}</p>\s*<p class="v">(.{0,400}?)</(?:p|div)>', re.S)
_QUELLE_FREITEXT_RE = re.compile(r"(?i)Quelle:?\s*(.{0,160})", re.S)
_QUELLE_TOKEN_RE = re.compile(r"🟢|🟡|🟠|🔴|grün|gruen|amber|\brot\b", re.I)
# Englische Fassung der Ampel-Wörter, nur im Quellen-Fenster gesucht (im Kopf könnte „Red“ im Stellentitel stehen).
_QUELLE_TOKEN_EN_RE = re.compile(r"\bgreen\b|\bred\b", re.I)
_HEADER_BLOCK_RE = re.compile(r"<header\b.*?</header>", re.S)


def _erkenne_alte_quelle(html: str) -> Optional[str]:
    """Kein eindeutiger Fund -> `None` (der Aufrufer lässt den Job dann unangetastet, statt eine
    Ampel-Farbe zu raten — dieselbe Ehrlichkeits-Regel wie beim Volltext)."""
    m = _QUELLE_ZEILE_RE.search(html)
    fenster = m.group(1) if m else ""
    if not fenster:
        m2 = _QUELLE_FREITEXT_RE.search(html)
        fenster = m2.group(1) if m2 else ""
    tok = _QUELLE_TOKEN_RE.search(fenster) or _QUELLE_TOKEN_EN_RE.search(fenster)
    if not tok:
        hm = _HEADER_BLOCK_RE.search(html)
        kopf = hm.group(0) if hm else html[:2000]
        tok = _QUELLE_TOKEN_RE.search(kopf)
    if not tok:
        return None
    t = tok.group(0)
    tl = t.lower()
    if t == "🟢" or "grün" in tl or "gruen" in tl or tl == "green":
        return "gruen"
    if t in ("🟡", "🟠") or "amber" in tl:
        return "amber"
    if t == "🔴" or tl in ("rot", "red"):
        return "rot"
    return None


def _snapshot_html_lesen(job: Job) -> Optional[str]:
    if not job.posting_snapshot_path:
        return None
    pfad = _SNAPSHOT_DIR / Path(job.posting_snapshot_path).name
    if not pfad.is_file():
        return None
    return pfad.read_text(encoding="utf-8", errors="replace")


def _gliederungs_plan(job: Job, html: str, quelle_fallback: Optional[str] = None) -> dict:
    """Ermittelt für EINEN Job den Weg (E1/E2/keiner) + die daraus resultierenden `abschnitte` +
    die Ist-Überschriften für die Trockenlauf-Vorschau. Reine Funktion, KEIN Schreibzugriff —
    das übernimmt ausschließlich `gliedern()` unten.

    `quelle_fallback` (Phase 79, Entscheidung vom 09.08.2026): Snapshots aus einer sehr alten
    Vorlage tragen ÜBERHAUPT KEIN Quellen-Signal im Kopf (die Badge-Konvention kam später). Ohne
    Fallback bleiben sie unangetastet — die Ampel zu raten wäre gegen die Anti-Halluzinations-
    Linie. Mit `--quelle-fallback amber` werden sie dennoch gegliedert und bekommen ehrlich die
    AMBER-Kennzeichnung („Teilquelle"), weil genau das der Sachstand ist: Der Anzeigentext liegt
    vor, aber ob er beim Abruf wörtlich aus dem Original stammte, ist nicht mehr belegbar.
    Bewusst ein expliziter Schalter und NIE ein Default — grün darf so nie entstehen."""
    ist_ueberschriften = sorted(_snapshot_headings(html))
    quelle = _erkenne_alte_quelle(html) or quelle_fallback
    if quelle is not None:
        e1 = _e1_abschnitte(html)
        if e1 is not None:
            return {"weg": "E1", "abschnitte": e1, "quelle": quelle,
                    "ist_ueberschriften": ist_ueberschriften}
        volltext = _lese_vorhandenen_volltext(job) or _lege_volltext_kandidaten(html)
        if volltext:
            e2 = _e2_abschnitte(volltext)
            if e2 is not None:
                return {"weg": "E2", "abschnitte": e2, "quelle": quelle,
                        "ist_ueberschriften": ist_ueberschriften}
    return {"weg": None, "abschnitte": None, "quelle": quelle, "ist_ueberschriften": ist_ueberschriften}


def _stage_volltext(job: Job, text: Optional[str]) -> None:
    """Zwischen-Schritt beim ECHTEN Schreiben (nie im Trockenlauf): schreibt den aus dem alten
    Snapshot geretteten Volltext EINMAL im Basis-Format (`_build_html()` ohne `abschnitte`,
    unverändert), damit `render_full()`s eigenes `_lese_vorhandenen_volltext()` (ebenfalls
    unverändert) ihn im NEUEN Format wiederfindet, bevor `render_full()` die Datei direkt danach
    endgültig überschreibt. Kein zweiter dauerhafter Zustand — nur der eine Zwischenschritt."""
    if not text:
        return
    label, quelle_text = _badge(True)
    html = _build_html(job, text, label, quelle_text)
    _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    fname = _ziel_dateiname(job)
    (_SNAPSHOT_DIR / fname).write_text(html, encoding="utf-8")


def gliedern(dry_run: bool = False, status_csv: Optional[str] = None,
            job_id: Optional[int] = None, quelle_fallback: Optional[str] = None) -> dict:
    """CLI-Kern für `python -m pipeline.posting_snapshot gliedern` (Stufe E, Spec-Entscheidung 7)
    — Gruppe B (E1, Umbenennen) + Gruppe C/Container-Fälle (E2, aus dem Volltext gliedern), beide
    OHNE LLM. `--dry-run` (`dry_run=True`) klassifiziert nur und schreibt NICHTS. Rückgabe:
    `{"e1": n, "e2": n, "nicht_gliederbar": [(job_id, firma), …], "vorschau": [(job_id, firma,
    ist_ueberschriften, weg, abschnitts_schluessel), …], "dry_run": bool}`."""
    init_db()
    stat = [s.strip() for s in (status_csv or "").split(",") if s.strip()]
    e1_n = e2_n = 0
    nicht_gliederbar = []
    vorschau = []
    with Session(engine) as s:
        tasks = s.exec(select(AgentTask).where(AgentTask.kind == "firma-pruefen",
                                                AgentTask.status == "done")).all()
        job_ids = sorted({t.job_id for t in tasks if t.job_id is not None})
        if job_id is not None:
            job_ids = [j for j in job_ids if j == job_id]
        for jid in job_ids:
            job = s.get(Job, jid)
            if not job or job.deleted_at or not job.posting_snapshot_path:
                continue
            if stat and job.status not in stat:
                continue
            html = _snapshot_html_lesen(job)
            if html is None:
                continue
            if _klassifiziere_snapshot(html) == "A":
                continue                                          # sauber getrennt -- nichts zu tun
            plan = _gliederungs_plan(job, html, quelle_fallback)
            firma = (job.company_name or "")[:30]

            if plan["weg"] is None:
                nicht_gliederbar.append((jid, firma))
                vorschau.append((jid, firma, plan["ist_ueberschriften"], "nicht gliederbar", None))
                continue

            if plan["weg"] == "E1":
                e1_n += 1
            else:
                e2_n += 1
            vorschau.append((jid, firma, plan["ist_ueberschriften"], plan["weg"],
                              sorted(plan["abschnitte"])))
            if dry_run:
                continue

            volltext = _lese_vorhandenen_volltext(job) or _lege_volltext_kandidaten(html)
            _stage_volltext(job, volltext)
            render_full(job.id, plan["abschnitte"], plan["quelle"])

    return {"e1": e1_n, "e2": e2_n, "nicht_gliederbar": nicht_gliederbar, "vorschau": vorschau,
            "dry_run": dry_run}


def _gliedern_main(dry_run: bool, status_csv: str, job_id: Optional[int],
                   quelle_fallback: Optional[str] = None) -> int:
    ergebnis = gliedern(dry_run=dry_run, status_csv=status_csv, job_id=job_id,
                        quelle_fallback=quelle_fallback)
    for jid, firma, ist, weg, ziel in ergebnis["vorschau"]:
        ziel_txt = f"{weg} ({', '.join(ziel)})" if ziel else weg
        print(f"Job {jid:>4}  {firma:<30}  Ist: {', '.join(ist) or '–'}")
        print(f"          -> {ziel_txt}")
    modus = "TROCKENLAUF — nichts geschrieben" if dry_run else "ECHTER LAUF"
    ng = ", ".join(str(j) for j, _ in ergebnis["nicht_gliederbar"]) or "–"
    print(f"\n[{modus}] E1: {ergebnis['e1']} umbenannt · E2: {ergebnis['e2']} gegliedert · "
          f"nicht gliederbar: {ng}")
    return 0


# ── P2-75: Anzeigentext nachholen ───────────────────────────────────────────────────────────
# Anlass: Eine Stelle aus einer Job-Mail bekam beim Erfassen nur einen Basis-Snapshot OHNE
# Anzeigentext, weil der Abruf von LinkedIn gedrosselt wurde (HTTP 429). Firma-Prüfung, CV-Match
# und CV liefen trotzdem durch und kannten die Anforderungen der Stelle nicht. Es gab bisher
# keinen Weg, fehlenden Text für einen Job MIT Snapshot nachzuholen (`backfill` nimmt nur Jobs
# ganz ohne Snapshot).
#
# Der Snapshot bleibt der eine Ort für den Anzeigentext (Leitentscheidung 3 der Spec): Nachholen
# schreibt den Basis-Snapshot mit Text und einem Hinweis, gegliedert wird er bei der nächsten
# Firma-Prüfung — es entsteht kein zweiter Gliederungsweg. Ersetzt wird NUR bei Befund `OK`
# (Titel und Firma passen) oder — P2-76 — bei `ABGELAUFEN` MIT Anzeigentext; alles andere lässt
# die Datei bytegleich.
#
# P2-76: Ein geschlossenes Portal heißt nicht, dass der Text weg ist. Zeigt LinkedIn eine Anzeige
# mit „keine Bewerbungen mehr“ noch an, liefert `check_url` den Befund `ABGELAUFEN` UND den
# Anzeigentext (Titel und Firma passen). Der Text ist dann genau das, was der Snapshot
# konservieren soll — sonst ginge er mit dem Schließen der Anzeige verloren. `ABGELAUFEN` ohne
# Text (Umleitung auf die generische Seite) bleibt `fehlt`.
_NACHHOLEN_STATUS_STANDARD = "Neu,Prüfen,Beworben,Interview,Angebot"
_NACHHOLEN_ABSTAND_S = 0.5            # Abstand zwischen zwei Jobs mit Netzabruf (kein Hammering)
_schlafen = time.sleep                # Modulfunktion, damit Tests die Pause ersetzen können

# Gründe für `fehlt` — Kundentexte, ohne Phasennummer. Der Server hängt sie in die Rückfrage an
# (`ANZEIGE_FEHLT: … <grund> …`), deshalb enden alle auf einen Punkt.
def _grund(name: str) -> str:
    """Die Gründe für `fehlt` in der Sprache, die jetzt gilt (nie beim Import festgehalten)."""
    return {
        "nicht_gefunden": tx("Stelle nicht gefunden."),
        "keine_url": tx("Die Stelle hat keine Anzeigen-Adresse."),
        "rate_limit": tx("LinkedIn hat den Abruf auch nach mehreren Versuchen abgelehnt "
                         "(zu viele Anfragen). Ein späterer Versuch klappt meist."),
        "blockiert": tx("Das Portal blockiert automatische Abrufe."),
        "login": tx("Die Anzeige ist nur mit Anmeldung sichtbar."),
        "offline": tx("Die Anzeige ist nicht mehr online."),
        "unklar": tx("Die abgerufene Seite passt nicht eindeutig zur Stelle."),
        "nicht_erreichbar": tx("Die Anzeige konnte nicht erreicht werden (Zeitüberschreitung oder "
                               "Netzfehler). Ein späterer Versuch klappt meist."),
        "leer": tx("Die abgerufene Seite enthielt keinen auswertbaren Anzeigentext."),
        "abruf_fehler": tx("Der Abruf der Anzeige ist fehlgeschlagen."),
        "speichern": tx("Der Anzeigentext konnte nicht gespeichert werden."),
        "trockenlauf": tx("Im Snapshot liegt kein Anzeigentext. Trockenlauf, es wurde nichts abgerufen."),
    }[name]


# Zusatz zur Tabelle der Spec (Randfall, den sie nicht nennt): `check_url` meldet Zeitüberschreitung/Netzfehler
# als TOT ohne HTTP-Status. „Nicht mehr online“ wäre dafür falsch (eine lebende Anzeige würde als weg gemeldet),
# deshalb der eigene Grund `nicht_erreichbar`.

# P2-76: Befunde von `check_url`, bei denen ein mitgelieferter Anzeigentext in den Snapshot darf.
# `OK` = Anzeige offen, Titel und Firma passen. `ABGELAUFEN` trägt nur dann Text, wenn eine
# Text-Marker-Seite („keine Bewerbungen mehr“) noch sichtbar ist und Titel und Firma passen;
# Umleitungen (`expired_jd_redirect`) tragen nie Text. `INHALT_UNKLAR` liefert zwar Seitentext,
# darf aber nichts ersetzen (die Seite passt nicht eindeutig zur Stelle).
_BEFUNDE_MIT_TEXT = ("OK", "ABGELAUFEN")


def hat_anzeigentext(job: Job) -> bool:
    """P2-75: Liegt der Anzeigentext dieser Stelle im Snapshot? Reine Lesefunktion (kein Netz,
    kein Schreiben). Wahr, wenn eine Snapshot-Datei existiert UND eine dieser Bedingungen gilt:
      * `_lese_vorhandenen_volltext()` findet Text (Basis-Karte oder Block „Volltext (unbereinigt)“),
      * `_lege_volltext_kandidaten()` findet Text (ältere, freihändig geschriebene Snapshots),
      * `_erkenne_alte_quelle()` meldet grün: die Firma-Prüfung hat das Original gegliedert,
        ohne dass ein Volltext-Block stehen blieb.
    Amber/rot gegliedert ohne Block, Basis ohne Text oder keine Datei -> falsch."""
    html = _snapshot_html_lesen(job)
    if html is None:
        return False
    if _lese_vorhandenen_volltext(job):
        return True
    if _lege_volltext_kandidaten(html):
        return True
    return _erkenne_alte_quelle(html) == "gruen"


def _sichern_ergebnis(job_id: int, status: str, grund: Optional[str] = None,
                      befund: Optional[str] = None, versuche: Optional[int] = None,
                      pfad: Optional[str] = None) -> dict:
    return {"job_id": job_id, "status": status, "grund": grund, "befund": befund,
            "versuche": versuche, "posting_snapshot_path": pfad}


def _grund_fuer_befund(pr: dict) -> str:
    """Tabelle der Spec: Befund von `check_url` -> Grund für `fehlt`."""
    befund = pr.get("befund")
    if befund == "NICHT_PRUEFBAR":
        return _grund("rate_limit") if pr.get("http_status") == 429 else _grund("blockiert")
    if befund == "LOGIN_WALL":
        return _grund("login")
    if befund in KONFIRMIERT_TOT_BEFUNDE:
        # TOT ohne HTTP-Status = Zeitüberschreitung/Netzfehler, keine bestätigt tote Anzeige.
        if befund == "TOT" and pr.get("http_status") is None:
            return _grund("nicht_erreichbar")
        return _grund("offline")
    if befund == "INHALT_UNKLAR":
        return _grund("unklar")
    if befund == "OK":
        return _grund("leer")                   # OK, aber ohne Text
    return _grund("abruf_fehler")


def _sichern(job_id: int, abrufen: bool) -> dict:
    """Kern von `anzeigentext_sichern()`. `abrufen=False` = Trockenlauf: alle Prüfungen vor dem
    Netzabruf laufen, dann endet es mit `fehlt` statt eines Abrufs (kein Netz, kein Schreiben)."""
    init_db()
    with Session(engine) as s:
        job = s.get(Job, job_id)
        if not job or job.deleted_at:
            return _sichern_ergebnis(job_id, "fehlt", grund=_grund("nicht_gefunden"))
        pfad = job.posting_snapshot_path
        if hat_anzeigentext(job):
            return _sichern_ergebnis(job_id, "vorhanden", pfad=pfad)
        if not (job.url or "").strip():
            return _sichern_ergebnis(job_id, "fehlt", grund=_grund("keine_url"), pfad=pfad)
        if not abrufen:
            return _sichern_ergebnis(job_id, "fehlt", grund=_grund("trockenlauf"), pfad=pfad)

        from pipeline.verify_jobs import check_url
        try:
            # Einzelabruf: `check_url` wiederholt bei 429 selbst mit Pausen (Vertrag A, P2-75).
            pr = check_url(job.url, job.company_name, job.title, return_text=True)
        except Exception as e:                                  # noqa: BLE001 — Start nie am Abruf scheitern lassen
            print(f"[posting_snapshot nachholen] Job {job_id}: {type(e).__name__}: {e}", file=sys.stderr)
            return _sichern_ergebnis(job_id, "fehlt", grund=_grund("abruf_fehler"), pfad=pfad)

        befund = pr.get("befund")
        versuche = pr.get("versuche")          # nur wenn der Abruf es meldet (Vertrag A) -> .get()
        text = pr.get("anzeigentext")
        # P2-76: Text nehmen wir bei `OK` und bei `ABGELAUFEN` (Portal geschlossen, Seite aber noch
        # sichtbar, Titel und Firma passen). `ABGELAUFEN` ohne Text fällt durch auf `fehlt`.
        if befund not in _BEFUNDE_MIT_TEXT or not (text or "").strip():
            # Nichts schreiben: die Datei bleibt bytegleich.
            return _sichern_ergebnis(job_id, "fehlt", grund=_grund_fuer_befund(pr), befund=befund,
                                     versuche=versuche, pfad=pfad)

        heute_text = datum(datetime.date.today())
        if befund == "ABGELAUFEN":
            hinweis = (tx("Anzeigentext am {datum} nachgeholt.", datum=heute_text) + " "
                       + tx("Das Portal nimmt laut Abruf keine Bewerbungen mehr an.") + " "
                       + tx("Gegliedert wird er bei der nächsten Firma-Prüfung."))
        else:
            hinweis = (tx("Anzeigentext am {datum} nachgeholt.", datum=heute_text) + " "
                       + tx("Gegliedert wird er bei der nächsten Firma-Prüfung."))
        rel = render_basis(job, text, hinweis=hinweis)
        if rel is None:                                          # render_basis meldet den Fehler auf stderr
            return _sichern_ergebnis(job_id, "fehlt", grund=_grund("speichern"), befund=befund,
                                     versuche=versuche, pfad=pfad)
        try:
            s.add(job)
            s.add(JobLog(job_id=job.id, eintrag=tx("Anzeigentext der Anzeige nachgeholt."), art="auto"))
            s.commit()
        except Exception as e:                                  # noqa: BLE001
            s.rollback()
            print(f"[posting_snapshot nachholen] Job {job_id}: Speichern fehlgeschlagen: "
                  f"{type(e).__name__}: {e}", file=sys.stderr)
            return _sichern_ergebnis(job_id, "fehlt", grund=_grund("speichern"), befund=befund,
                                     versuche=versuche, pfad=pfad)
        return _sichern_ergebnis(job_id, "nachgeholt", befund=befund, versuche=versuche, pfad=rel)


def anzeigentext_sichern(job_id: int) -> dict:
    """P2-75: Stellt sicher, dass der Anzeigentext einer Stelle im Snapshot liegt — holt ihn nach,
    wenn er fehlt. Aufgerufen von `app/main.py::create_task()` (im Threadpool: synchron, eigene
    Session, committet selbst, keine Ausgabe auf stdout) und von der CLI `nachholen`.

    Rückgabe: `{"job_id", "status", "grund", "befund", "versuche", "posting_snapshot_path"}`,
    `status` ist `"vorhanden"` (nichts zu tun, KEIN Netzabruf), `"nachgeholt"` (Basis-Snapshot mit
    Text und Hinweis geschrieben, ein `JobLog` angelegt) oder `"fehlt"` (`grund` sagt warum, die
    Datei bleibt bytegleich). `befund`/`versuche` stammen aus `check_url` und sind ohne Abruf `None`.
    Ein Job ohne Snapshot läuft durch denselben Weg und bekommt bei Erfolg seinen ersten.

    P2-76: `nachgeholt` gibt es bei Befund `OK` und bei `ABGELAUFEN` MIT Anzeigentext (Portal
    geschlossen, Seite noch sichtbar); im zweiten Fall nennt der Hinweis im Snapshot, dass das
    Portal keine Bewerbungen mehr annimmt. `ABGELAUFEN` ohne Text bleibt `fehlt`."""
    return _sichern(job_id, abrufen=True)


def nachholen(status_csv: str = _NACHHOLEN_STATUS_STANDARD, dry_run: bool = False,
              job_id: Optional[int] = None) -> dict:
    """CLI-Kern für `python -m pipeline.posting_snapshot nachholen` (P2-75). `job_id` gesetzt =
    nur diese Stelle (ohne Statusfilter), sonst alle nicht gelöschten Jobs mit einem Status aus
    `status_csv` (leer = alle). `dry_run=True` zählt nur, welche Jobs keinen Anzeigentext haben
    (kein Netz, kein Schreiben). Zwischen zwei Jobs mit Netzabruf liegen 0,5 s.

    Rückgabe: `{"jobs_gesamt", "vorhanden", "nachgeholt", "fehlt", "fehlt_ids", "dry_run",
    "jobs": [<Ergebnis je Job wie `anzeigentext_sichern()`>]}`; im Trockenlauf bedeutet `fehlt`
    „ohne Anzeigentext“."""
    init_db()
    if job_id is not None:
        ids = [job_id]
    else:
        stat = [t.strip() for t in (status_csv or "").split(",") if t.strip()]
        with Session(engine) as s:
            q = select(Job.id).where(Job.deleted_at.is_(None))
            if stat:
                q = q.where(Job.status.in_(stat))
            ids = sorted(s.exec(q).all())

    jobs = []
    for i, jid in enumerate(ids):
        erg = _sichern(jid, abrufen=not dry_run)
        jobs.append(erg)
        if erg["befund"] is not None and i < len(ids) - 1:      # nur nach einem Netzabruf pausieren
            _schlafen(_NACHHOLEN_ABSTAND_S)
    zahl = {st: sum(1 for e in jobs if e["status"] == st) for st in ("vorhanden", "nachgeholt", "fehlt")}
    return {"jobs_gesamt": len(jobs), **zahl,
            "fehlt_ids": [e["job_id"] for e in jobs if e["status"] == "fehlt"],
            "dry_run": dry_run, "jobs": jobs}


def _nachholen_main(job_id: Optional[int], status_csv: str, dry_run: bool) -> int:
    """JSON auf stdout, Tabelle auf stderr (Muster `backfill`). Exit-Code mit `--job-id`: 0 bei
    `vorhanden`/`nachgeholt`, 3 bei `fehlt`; im Bestand immer 0 (Details im JSON)."""
    ergebnis = nachholen(status_csv, dry_run=dry_run, job_id=job_id)
    print("-" * 52, file=sys.stderr)
    for e in ergebnis["jobs"]:
        versuche = f" ({e['versuche']} Versuche)" if e.get("versuche") else ""
        grund = f"  {e['grund']}" if e.get("grund") else ""
        print(f"{e['job_id']:>4}  {e['status']:<10}  {e['befund'] or '-'}{versuche}{grund}", file=sys.stderr)
    if job_id is not None:
        einzel = {**ergebnis["jobs"][0], **({"dry_run": True} if dry_run else {})}
        print(json.dumps(einzel, ensure_ascii=False))
        return 0 if einzel["status"] in ("vorhanden", "nachgeholt") else 3
    zusammenfassung = {k: v for k, v in ergebnis.items() if k != "jobs"}
    print(json.dumps(zusammenfassung, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(prog="pipeline.posting_snapshot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_b = sub.add_parser("backfill", help="Bestands-Jobs ohne Snapshot einmalig nachziehen")
    p_b.add_argument("--status", default="Neu,Prüfen,Beworben,Interview,Angebot")
    p_n = sub.add_parser("nachholen", help="Fehlenden Anzeigentext nachholen (P2-75)")
    p_n.add_argument("--job-id", type=int, default=None, help="nur diese Stelle (Exit 0 = Text da, 3 = fehlt)")
    p_n.add_argument("--status", default=_NACHHOLEN_STATUS_STANDARD, help="Job.status-Filter, CSV")
    p_n.add_argument("--dry-run", action="store_true", help="nur zählen, wer keinen Text hat; kein Netz")
    sub.add_parser("pruefen", help="Jobs mit firma-pruefen-Lauf ohne gegliederten Snapshot melden (Phase 79)")
    p_g = sub.add_parser("gliedern", help="Gruppe B/C ohne LLM nachziehen (Phase 79 Stufe E)")
    p_g.add_argument("--dry-run", action="store_true", help="nur klassifizieren, nichts schreiben")
    p_g.add_argument("--status", default="", help="optionaler Job.status-Filter, CSV")
    p_g.add_argument("--job-id", type=int, default=None, help="nur diesen einen Job verarbeiten")
    # Phase 79 (09.08.2026): bewusst OPT-IN — ohne diesen Schalter bleiben Snapshots ohne
    # Quellen-Signal unangetastet (Ampel raten = Anti-Halluzinations-Verstoß). "gruen" ist
    # nicht erlaubt: eine unbelegbare Herkunft darf nie als bestätigtes Original erscheinen.
    p_g.add_argument("--quelle-fallback", choices=["amber", "rot"], default=None,
                     help="Ampel für Snapshots aus alten Vorlagen OHNE Quellen-Signal "
                          "(empfohlen: amber = Teilquelle, Herkunft nicht mehr belegbar)")
    a = ap.parse_args()
    if a.cmd == "pruefen":
        sys.exit(_pruefen_main())
    if a.cmd == "gliedern":
        sys.exit(_gliedern_main(a.dry_run, a.status, a.job_id, a.quelle_fallback))
    if a.cmd == "nachholen":
        sys.exit(_nachholen_main(a.job_id, a.status, a.dry_run))
    print(json.dumps(backfill(a.status), ensure_ascii=False))
