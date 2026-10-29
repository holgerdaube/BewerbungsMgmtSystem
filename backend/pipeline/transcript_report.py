#!/usr/bin/env python3
"""Transkript-Report — EIN vollwertiges Artefakt je Transkript (Phase 30 Stufe C).

Aufbau (Design-Entscheidung 6 der Spec): (1) Headline — Firma, Rolle, Gesprächsdatum, Teilnehmer,
Runde, Status-Badges; (2) Findings — Zusammenfassung/Signale/To-dos/offene Fragen (leer/Platzhalter
bei render_basis, gefüllt bei render_full); (3) vollständiger Original-Transkript-Text am Ende.
Stil = Company-Fit-Look, aber statisches HTML. Das CSS kommt seit P2-72 aus `pipeline/bericht_stil.py`
(Werte des geltenden Designs); `assets/report_theme_bms.html` ist die Lese-Vorlage für Aufbau und
Klassen (Skills/Menschen), dieses Modul der deterministische Generator für denselben Look.

Zwei Erzeugungswege (Design-Entscheidung 7):
  (a) render_basis(transcript_id) — deterministisch, OHNE LLM. Läuft automatisch am Ende von
      create_transcript UND vom Transkript-Upload-Endpunkt (backend/app/main.py). Der Report
      existiert damit SOFORT — Findings-Sektion trägt den Hinweis "Debrief ausstehend".
  (b) render_full(transcript_id, sections, summary, todos=None) — vom Skill `gespraech-debrief`
      aufgerufen: ERSETZT dieselbe Datei durch die Vollversion (Dateiname bleibt stabil, kein
      Duplikat), setzt `summary` (3–5 Sätze, Pflicht) und optional `todos_json` am Transcript.
      `debrief_path` wird für Neufälle NICHT mehr gesetzt (Altbestand behält seins, Migration
      folgt in Phase 31).

CLI (aus backend/):
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.transcript_report <transcript_id>
        → render_basis (Nachrüsten für Alt-Transkripte ohne report_path / manuelles Debuggen)
"""
import datetime
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from app.db import artefakt_pfad, engine, init_db
from app.models import Interview, Job, Transcript
from app.favicon import favicon_link
from pipeline.bericht_stil import DRUCK_SEITENFARBE_BEHALTEN, bericht_css

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Bewerbung_Mgmt_System/
_REPORT_DIR = PROJECT_ROOT / "data" / "transcripts"

# CSS: das gemeinsame Thema kommt aus `pipeline/bericht_stil.py` (P2-72), mit den Werten des
# geltenden Designs. Hier steht nur, worin dieser Report davon abweicht — so, dass er genauso aussieht
# wie vor der Umstellung (Leitentscheidung 8: nichts „bereinigen“).
_CSS_ZUSATZ = """
.dot{width:10px;height:10px}
""" + DRUCK_SEITENFARBE_BEHALTEN + "\n"


def _css() -> str:
    """Das CSS des Reports, bei jedem Aufruf mit dem Design, das gerade gilt. Auch
    `migrate_reports` nimmt es von hier (statt der früheren Konstante `_CSS`)."""
    return bericht_css(_CSS_ZUSATZ)


def _esc(s) -> str:
    return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _lies_rohtext(rel_path: Optional[str]) -> str:
    if not rel_path:
        return "(kein Transkript-Rohtext hinterlegt)"
    p = artefakt_pfad(rel_path)
    # Phase 79: gemeinsame Auflösung (data/ → aktive Datenwurzel) statt PROJECT_ROOT — s. app/db.py::artefakt_pfad
    if not p.is_file():
        return f"(Datei nicht gefunden: {rel_path})"
    return p.read_text(encoding="utf-8", errors="replace")


def _datum_de(iso: Optional[str]) -> str:
    """'YYYY-MM-DD' -> 'DD.MM.YYYY' (Referenz-Kopf-Format). Robust: nicht parsbar -> Rohwert."""
    s = str(iso or "").strip()[:10]
    try:
        return datetime.date.fromisoformat(s).strftime("%d.%m.%Y")
    except ValueError:
        return s


def _sub_zeile(job: Job, iv: Optional[Interview]) -> str:
    teile = [job.company_name or "Unbekannte Firma", f"Job {job.id}"]
    if iv:
        runde = f"Runde {iv.runde}" + (f" ({iv.art})" if iv.art else "")
        teile.append(runde)
    return " · ".join(t for t in teile if t)


def _meta_spalten(t: Transcript, iv: Optional[Interview], status_danach: Optional[str]) -> list:
    """Kontakt · Art · Datum · Status danach (Typ-Tabelle, Phase 35) — leere Spalten weglassen."""
    spalten = []
    if t.kontakt:
        spalten.append(("Kontakt", t.kontakt))
    art = t.gespraechsart or (iv.art if iv else None)
    if art:
        spalten.append(("Art", art))
    stand = t.recorded_at or (t.created_at.date().isoformat() if t.created_at else None)
    if stand:
        spalten.append(("Datum", _datum_de(stand)))
    status = status_danach or (iv.status if iv else None)
    if status:
        spalten.append(("Status danach", status))
    return spalten


def _badges_zusatz(t: Transcript) -> list:
    """Ergänzende Badge-Zeile für das, was NICHT schon in den Meta-Spalten steht (Sprache/Quelle)."""
    out = []
    if t.language:
        out.append(t.language.upper())
    quelle = {"manuell": "Text eingefügt", "upload": "Datei-Upload"}.get(t.source, t.source)
    if quelle:
        out.append(quelle)
    return out


# ── HTML-Sanitizer für sec["html"] (P2-14, Code-Review 2026-07-25) ──────────────────────────
# `sections[].html` stammt aus dem Debrief-Skill (LLM-Freitext über Transkript-Zitate, teils
# recherchierter Fremdtext) und wurde bisher UNGEFILTERT in den Report geschrieben — Stored-XSS-
# Fläche, weil der Report über /api/artifact als text/html inline ausgeliefert wird. Whitelist
# ist bewusst NICHT geraten, sondern aus den echten Bestandsreports unter data/transcripts/
# abgeleitet (Report Phase 67E): dort kommen p/div/span/ul/li/b/i/code vor (Zitat-Boxen
# `div.quote`, Signal-Callouts `div.signal.pos/warn`, Tag-Chips `span.tag …`, Absatz-Feinschliff
# per `style="margin:…;font-size:…"`) — nur `class`/`style` als Attribute, nie `href`/`src`/
# `on*`. `ol`/`strong`/`em`/`br` ergänzt (harmlose Geschwister von ul/b/i, kein Beleg nötig).
_ERLAUBTE_TAGS = {"p", "div", "span", "ul", "ol", "li", "b", "strong", "i", "em", "br", "code"}
_ERLAUBTE_ATTRS = {"class", "style"}
# Verteidigung in der Tiefe für `style`: keine Funktionsaufrufe/Importe, kein javascript:-Schema.
# Die echten Reports brauchen nur "prop:wert;prop:wert" (s. o.) — nichts davon nutzt Klammern.
_STYLE_VERBOTEN = re.compile(r"url\s*\(|expression\s*\(|@import|javascript\s*:|behavior\s*:", re.I)


def _esc_attr(s) -> str:
    """Wie `_esc()`, plus `"` → `&quot;` — Pflicht für Attributwerte (nicht für Text-Inhalt):
    ein roher `"` im Wert würde das Attribut vorzeitig schließen und den Rest als neues Markup
    freigeben (klassischer Attribut-Escape, s. Report Phase 67E)."""
    return _esc(s).replace('"', "&quot;")


class _AbschnittSanitizer(HTMLParser):
    """Whitelist-Sanitizer: nicht erlaubte Tags werden entfernt, ihr TEXT bleibt erhalten (nur
    bei script/style fällt auch der Inhalt weg — dort steht Code, kein lesbarer Text). Nicht
    erlaubte Attribute werden stillschweigend gestrichen, ein gefährlicher `style`-Wert komplett.
    `convert_charrefs=True` (Default/empfohlen) liefert Entities bereits aufgelöst über
    `handle_data` — eigene `handle_entityref`/`handle_charref` sind deshalb nicht nötig."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip_depth = 0   # >0 während script/style-INHALT übersprungen wird

    def _oeffnen(self, tag: str, attrs) -> None:
        behalten = []
        for k, v in attrs:
            k = k.lower()
            if k not in _ERLAUBTE_ATTRS:
                continue
            wert = v or ""
            if k == "style" and _STYLE_VERBOTEN.search(wert):
                continue
            behalten.append((k, wert))
        attr_html = "".join(f' {k}="{_esc_attr(v)}"' for k, v in behalten)
        self.out.append(f"<{tag}{attr_html}>")

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in _ERLAUBTE_TAGS:
            self._oeffnen(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        if tag in ("script", "style") or self._skip_depth:
            return
        if tag not in _ERLAUBTE_TAGS:
            return
        self._oeffnen(tag, attrs)
        if tag != "br":
            self.out.append(f"</{tag}>")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag in _ERLAUBTE_TAGS:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self._skip_depth:
            self.out.append(_esc(data))

    def ergebnis(self) -> str:
        return "".join(self.out)


def _sanitiere_html(roh: str) -> str:
    """Öffentliche Schnittstelle des Sanitizers (s. Klassen-Docstring oben für die Whitelist-
    Begründung). Kaputtes/nicht wohlgeformtes HTML lässt `HTMLParser` nicht crashen — im
    unwahrscheinlichen Fall eines internen Fehlers wird der Rohtext stattdessen komplett
    escaped ausgegeben (sicher, auch wenn hässlich) statt den Report-Bau abzubrechen."""
    if not roh:
        return ""
    parser = _AbschnittSanitizer()
    try:
        parser.feed(roh)
        parser.close()
    except Exception:
        return _esc(roh)
    return parser.ergebnis()


def _sections_html(sections) -> str:
    teile = []
    for sec in sections or []:
        titel = _esc(sec.get("title") or "Findings")
        inhalt = _sanitiere_html(sec.get("html") or "")
        teile.append(f'<h2 class="sec">{titel}</h2>\n<div class="card">{inhalt}</div>')
    return "\n".join(teile)


def _build_html(job: Job, t: Transcript, iv: Optional[Interview], sections, hinweis: str,
                eyebrow: str = "Transkript-Report", status_danach: Optional[str] = None) -> str:
    """Report-Kopf nach der Phase-35-Referenz (Debrief-Kopf als Vorbild): eyebrow → h1=ROLLE
    (nicht Firma) → sub (Firma · Job <id> · Runde (Art)) → beschriftetes Meta-Grid Kontakt/Art/
    Datum/Status danach. `eyebrow`/`status_danach` sind der einzige Unterschied Basis vs. Vollversion
    (Design-Entscheidung 3 der Spec) — Kopf-Struktur ist identisch."""
    titel = f"{eyebrow} · {_esc(job.company_name)}"
    meta_html = "".join(f'<div><p class="k">{_esc(k)}</p><p class="v">{_esc(v)}</p></div>'
                        for k, v in _meta_spalten(t, iv, status_danach))
    badges_html = "".join(f'<span class="pill">{_esc(b)}</span>' for b in _badges_zusatz(t))
    rohtext = _lies_rohtext(t.file_path)
    erzeugt = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    _FAVICON = favicon_link()      # P2-72: Icon des geltenden Designs, bei jedem Report frisch
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">{_FAVICON}
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titel}</title>
<style>{_css()}</style>
</head>
<body>
<div class="wrap">
  <header class="head">
    <p class="eyebrow">{_esc(eyebrow)}</p>
    <h1>{_esc(job.title) or 'Unbekannte Rolle'}</h1>
    <p class="sub">{_esc(_sub_zeile(job, iv))}</p>
    <div class="meta">{meta_html}</div>
    <div class="badges">{badges_html}</div>
  </header>

  {_sections_html(sections)}

  <h2 class="sec">Volltext</h2>
  <details class="volltext">
    <summary>Original-Transkript-Text anzeigen/verbergen</summary>
    <pre>{_esc(rohtext)}</pre>
  </details>

  <div class="foot">
    <span>Bewerbungs-Mgmt · erzeugt am {erzeugt}</span>
    <span>{_esc(hinweis)}</span>
  </div>
</div>
</body>
</html>
"""


def _freier_name(ordner: Path, fname: str) -> str:
    """Kollision → _2, _3 … (identisches Muster wie app/main.py::_freier_name)."""
    if not (ordner / fname).exists():
        return fname
    stem, punkt, ext = fname.rpartition(".")
    n = 2
    while (ordner / f"{stem}_{n}{punkt}{ext}").exists():
        n += 1
    return f"{stem}_{n}{punkt}{ext}"


def _ziel_dateiname(t: Transcript, job: Job, iv: Optional[Interview]) -> str:
    """Stabiler Dateiname: existiert bereits ein report_path, dessen Basisnamen wiederverwenden
    (render_full ERSETZT dieselbe Datei) — sonst neu berechnen (Kollision → _2, _3 …)."""
    from app.naming import report_filename
    if t.report_path:
        return Path(t.report_path).name
    base = report_filename("Auswertung", job.company_name, job.title,
                           when=t.recorded_at, runde=iv.runde if iv else None)
    return _freier_name(_REPORT_DIR, f"{base}.html")


def _speichere(t: Transcript, job: Job, iv: Optional[Interview], html: str) -> str:
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    fname = _ziel_dateiname(t, job, iv)
    (_REPORT_DIR / fname).write_text(html, encoding="utf-8")
    return f"data/transcripts/{fname}"


def render_basis(transcript_id: int) -> dict:
    """Deterministischer Basis-Report OHNE LLM — läuft automatisch bei Anlage/Upload eines
    Transkripts, damit der Report sofort existiert. Findings-Sektion verweist auf den ausstehenden
    Debrief-Lauf."""
    init_db()
    with Session(engine) as s:
        t = s.get(Transcript, transcript_id)
        if not t:
            raise SystemExit(f"Transcript {transcript_id} nicht gefunden")
        job = s.get(Job, t.job_id)
        iv = s.get(Interview, t.interview_id) if t.interview_id else None
        sections = [{
            "title": "Findings",
            "html": (f'<p>Debrief ausstehend — <b>„Debrief für Job {job.id}“</b> ausführen, um '
                     f'Zusammenfassung, Signale &amp; Red Flags, To-dos und offene Fragen zu ergänzen.</p>'),
        }]
        html = _build_html(job, t, iv, sections, "Automatisch erzeugt — Debrief ausstehend",
                           eyebrow="Transkript-Report", status_danach="Debrief ausstehend")
        t.report_path = _speichere(t, job, iv, html)
        s.add(t)
        s.commit()
        return {"transcript_id": t.id, "report_path": t.report_path}


def render_full(transcript_id: int, sections: list, summary: str, todos: Optional[list] = None,
                status_danach: Optional[str] = None) -> dict:
    """Ersetzt den Report unter report_path (legt ihn an, falls noch keiner existiert) durch die
    Vollversion mit gefüllten Findings — Dateiname bleibt stabil, kein Duplikat. Setzt `summary`
    (Pflicht, 3–5 Sätze — die einzige Inhaltsanzeige rechts im Job-Detail) und optional
    `todos_json`. Die Zusammenfassung wird zusätzlich als ERSTE Findings-Karte ins Report-HTML
    geschrieben (spec-konform: "Findings — Zusammenfassung, was gut/wackelig lief, …") — so bleibt
    sie auch über die Volltextsuche (FTS) auffindbar, nicht nur als DB-Feld. `debrief_path` wird
    für Neufälle bewusst NICHT gesetzt (Design-Entscheidung 7). `status_danach` (Phase 35, optional)
    ist die Kopf-Meta-Spalte „Status danach" — vom Skill übergeben, wenn es mehr sagen kann als der
    reine Interview-Status (z. B. „Absolviert · Feedback zugesagt bis ca. 24.07."), sonst fällt
    `_build_html` auf `iv.status` zurück."""
    import json as _json
    init_db()
    with Session(engine) as s:
        t = s.get(Transcript, transcript_id)
        if not t:
            raise SystemExit(f"Transcript {transcript_id} nicht gefunden")
        job = s.get(Job, t.job_id)
        iv = s.get(Interview, t.interview_id) if t.interview_id else None
        alle_sections = [{"title": "Zusammenfassung", "html": f"<p>{_esc(summary)}</p>"}] + list(sections or [])
        html = _build_html(job, t, iv, alle_sections, "Debrief abgeschlossen",
                           eyebrow="Gesprächs-Debrief", status_danach=status_danach)
        t.report_path = _speichere(t, job, iv, html)
        t.summary = summary
        if todos is not None:
            t.todos_json = _json.dumps(todos, ensure_ascii=False)
        s.add(t)
        s.commit()
        return {"transcript_id": t.id, "report_path": t.report_path, "summary": t.summary}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Nutzung: python -m pipeline.transcript_report <transcript_id>")
    import json
    print(json.dumps(render_basis(int(sys.argv[1])), ensure_ascii=False))
