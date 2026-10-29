#!/usr/bin/env python3
"""Company-Fit-Dashboard — deterministisches Layout OHNE LLM-Markup (Design-Review 10.08.2026).

Anlass (Drift-Diagnose 10.08.2026): Die firma-pruefen-SKILL.md delegierte das Dashboard-Design
an den Plugin-Skill `anthropic-skills:company-fit-analysis` — der ist im headless-Runner
NACHWEISLICH NIE verfügbar (Init-Event aller task_*.jsonl listet ihn nicht; galt auch für die
„guten" Läufe). Bis 08.08. fiel das nicht auf, weil die Läufe Re-Checks von Bestandsfirmen
waren: das Modell las den Vorgänger-Report DERSELBEN Firma und kopierte dessen Struktur/CSS
wörtlich. Der Batch vom 09.08. bestand aus NEUEN Firmen ohne Vorgänger — der erste Lauf
improvisierte ein flaches Ein-Karten-Layout, und jeder Folgelauf nahm „die neueste Datei" als
Vorlage, also die bereits gedriftete: Selbstfortpflanzung (14 betroffene Dateien 09.–10.08.,
9,5–13,4 KB statt 14,7–33,5 KB). Exakt das Drift-Muster aus Phase 79 (s. dort) — und
dieselbe Lösung: das Layout ist Code, nicht Prosa. Muster = `posting_snapshot.render_full()` /
`transcript_report.render_full`.

Das Modell liefert nur noch INHALTE (JSON, s. `render_full()`-Docstring), niemals HTML.
Kopf, Kartenraster, Score-Tabelle, Badges, Quellen-Block und Footer kommen vollständig aus
diesem Modul. Style-Quelle war die kuratierte Referenz vom 08.08. (vom Nutzer als „in Ordnung"
abgenommen); seit P2-72 kommt das CSS aus `pipeline/bericht_stil.py` (Werte des geltenden Designs),
dieses Modul reicht nur seine eigenen Regeln als Zusatz mit.

CLI (aus backend/):
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.company_fit render /tmp/company_fit_<job_id>.json
        → schreibt das Dashboard, druckt {"job_id", "company_fit_path", "abschnitte": […]}.
          Registrierung am Job läuft danach unverändert über `pipeline.deepdive.register`.
"""
import datetime
import json
import sys
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from app.db import DATA_DIR, engine, init_db
from app.models import Job
from app.favicon import favicon_link
from pipeline.bericht_stil import DRUCK_SEITENFARBE_BEHALTEN, bericht_css

# T1-Regel (s. posting_snapshot.py): IMMER über DATA_DIR aus app.db — folgt dem Test-Override
# BMS_DATA_DIR, Tests schreiben nie in das echte data/company_fit/.
_FIT_DIR = DATA_DIR / "company_fit"

# CSS: das gemeinsame Thema kommt aus `pipeline/bericht_stil.py` (P2-72), mit den Werten des
# geltenden Designs. Hier steht nur, worin das Company-Fit-Dashboard davon abweicht — und zwar so,
# dass es genauso aussieht wie vor der Umstellung (Leitentscheidung 8: nichts „bereinigen“).
_CSS_ZUSATZ = """
.bluf{border-left:4px solid var(--amber)}
""" + DRUCK_SEITENFARBE_BEHALTEN + "\n"


def _css() -> str:
    """Das CSS des Dashboards, bei jedem Aufruf mit dem Design, das gerade gilt."""
    return bericht_css(_CSS_ZUSATZ)


def _esc(s) -> str:
    return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# Ampel: ASCII-Kategorien wie deepdive._FIT_AMPEL_WERTE (dieselben Werte, die Schritt 4 der
# SKILL.md an register() übergibt) — die Darstellung (Dot-Klasse + Label) kommt aus dem Code.
_AMPEL_WERTE = {"gruen", "gelb", "rot"}
_AMPEL_DOT = {"gruen": "green", "gelb": "amber", "rot": "red"}
_AMPEL_LABEL = {"gruen": "Grün", "gelb": "Gelb", "rot": "Rot"}

# Kanon-Abschnitte mit festem Karten-Layout (die kuratierte Referenz vom 08.08.). Unbekannte Schlüssel → ValueError
# (Tippfehler sollen knallen, nicht still verschwinden — Muster posting_snapshot).
_ABSCHNITT_SCHLUESSEL = {
    "geschaeftsmodell_was",            # str | dict {kv-Label: Text} → Karte „Was & für wen"
    "geschaeftsmodell_wettbewerber",   # list[str] → Karte „Wettbewerber & Marktstellung"
    "ki_disruption",                   # str → eigene Karte
    "arbeitgeber_realitaet",           # dict mit festen Unterschlüsseln → 4-Karten-Grid
    "chancen",                         # list[str | {"label","text"}] → linke Karte
    "risiken",                         # list[str | {"label","text"}] → rechte Karte
}
_ARBEITGEBER_KARTEN = (
    ("bewertungen", "Glassdoor / kununu"),
    ("modern", "Echt modern vs. behauptet modern"),
    ("aktivitaet", "Aktivitäts-Indikator"),
    ("entwicklung", "Geschäftsentwicklung & Tarifbindung"),
)
_EINFLUSS_SCHLUESSEL = {"faktor", "wert", "warum", "relevanz"}
_EINFLUSS_BADGE = {"pos": "+", "neu": "0", "neg": "−"}
_QUELLEN_SCHLUESSEL = {"label", "url"}

_FOOT_HINWEIS_DEFAULT = "Fakten mit Quelle · Einschätzungen als Annahme markiert"


def _absaetze(text) -> str:
    text = "" if text is None else str(text).strip()
    return "".join(f"<p>{_esc(p)}</p>" for p in text.split("\n\n") if p.strip())


def _kv_absaetze(wert) -> str:
    """Karte „Was & für wen": dict → kv-Label + Absatz je Paar (Reihenfolge bleibt), str → Absätze."""
    if isinstance(wert, dict):
        teile = []
        for label, text in wert.items():
            inhalt = _absaetze(text)
            if not inhalt:
                continue
            teile.append(f'<p class="kv">{_esc(label)}</p>{inhalt}')
        return "".join(teile)
    return _absaetze(wert)


def _listen_items(werte, kontext: str) -> str:
    """Chancen/Risiken-Items: str ODER {"label": str, "text": str} (Label wird fett vorangestellt
    — Referenz-Risiken tragen solche Präfixe). Anderes → ValueError."""
    items = []
    for w in werte or []:
        if isinstance(w, dict):
            unbekannt = set(w) - {"label", "text"}
            if unbekannt:
                raise ValueError(f"Unbekannte Schlüssel in {kontext}-Eintrag: {sorted(unbekannt)} — "
                                 f"erlaubt sind ['label', 'text']")
            label, text = w.get("label"), w.get("text")
            if not str(text or "").strip():
                continue
            praefix = f"<b>{_esc(label)}:</b> " if str(label or "").strip() else ""
            items.append(f"<li>{praefix}{_esc(text)}</li>")
        elif str(w or "").strip():
            items.append(f"<li>{_esc(w)}</li>")
    return f'<ul class="clean">{"".join(items)}</ul>' if items else ""


def _einfluss_tabelle(zeilen) -> str:
    if not zeilen:
        return ""
    tr = []
    for z in zeilen:
        z = z or {}
        unbekannt = set(z) - _EINFLUSS_SCHLUESSEL
        if unbekannt:
            raise ValueError(f"Unbekannte Schlüssel in rollen_einfluss: {sorted(unbekannt)} — "
                             f"erlaubt sind {sorted(_EINFLUSS_SCHLUESSEL)}")
        wert = z.get("wert")
        if wert not in _EINFLUSS_BADGE:
            raise ValueError(f"rollen_einfluss.wert muss pos|neu|neg sein, nicht {wert!r}")
        tr.append(
            f'<tr>\n<td class="factor">{_esc(z.get("faktor"))}</td>\n'
            f'<td><span class="badge {wert}">{_EINFLUSS_BADGE[wert]}</span></td>\n'
            f'<td>{_esc(z.get("warum"))}</td>\n'
            f'<td class="rel">{_esc(z.get("relevanz"))}</td>\n</tr>')
    return ('<table class="score">\n'
            "<thead><tr><th>Faktor</th><th>Wert</th><th>Warum</th><th>Relevanz</th></tr></thead>\n"
            "<tbody>\n" + "\n".join(tr) + "\n</tbody>\n</table>")


def _quellen_block(quellen) -> str:
    if not quellen:
        return ""
    teile = []
    for q in quellen:
        q = q or {}
        unbekannt = set(q) - _QUELLEN_SCHLUESSEL
        if unbekannt:
            raise ValueError(f"Unbekannte Schlüssel in quellen: {sorted(unbekannt)} — "
                             f"erlaubt sind {sorted(_QUELLEN_SCHLUESSEL)}")
        label = str(q.get("label") or "").strip()
        if not label:
            continue
        url = str(q.get("url") or "").strip()
        if url:
            teile.append(f'<a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(label)}</a>')
        else:
            teile.append(_esc(label))
    if not teile:
        return ""
    return ('<div class="sources">\n<h2>Quellen</h2>\n<p>\n      '
            + " ·\n      ".join(teile) + "\n    </p>\n  </div>")


def _freier_name(ordner: Path, fname: str) -> str:
    """Kollision → _2, _3 … (identisches Muster wie posting_snapshot/transcript_report)."""
    if not (ordner / fname).exists():
        return fname
    stem, punkt, ext = fname.rpartition(".")
    n = 2
    while (ordner / f"{stem}_{n}{punkt}{ext}").exists():
        n += 1
    return f"{stem}_{n}{punkt}{ext}"


def render_full(job_id: int, sub: str, fit_ampel: str, fit_text: str, bluf: str,
                abschnitte: dict, rollen_einfluss: list, klaerungsfrage,
                quellen: Optional[list] = None, markt_segment: Optional[str] = None,
                quellen_kurz: Optional[str] = None, recheck_von: Optional[str] = None,
                foot_hinweis: Optional[str] = None, out_path: Optional[str] = None) -> dict:
    """Schreibt das Company-Fit-Dashboard deterministisch im Layout der kuratierten Referenz.

    Das Modell liefert NUR Inhalte — jedes HTML-Element (Kopf, Meta-Grid, BLUF, Kartenraster,
    Score-Tabelle, Quellen, Footer) kommt aus diesem Modul. Reihenfolge ist FEST: Kopf → BLUF →
    Geschäftsmodell & Marktposition (2 Karten) → KI-/Digital-Disruption → Einfluss dieser Rolle
    (Score-Tabelle) → Arbeitgeber-Realität (4 Karten) → Chancen & Risiken (2 Karten) →
    Klärungsfrage (.caveat) → Quellen → Footer. Leere Abschnitte werden weggelassen, nie mit
    „–" gefüllt.

    `fit_ampel`: "gruen"|"gelb"|"rot" (ASCII, wie deepdive.register) — steuert Dot + Label.
    `abschnitte`: nur die Kanon-Schlüssel (s. `_ABSCHNITT_SCHLUESSEL`), sonst ValueError.
    `rollen_einfluss`: Liste aus {"faktor","wert"("pos"|"neu"|"neg"),"warum","relevanz"}.
    `klaerungsfrage`: str oder list[str] (mehrere Fragen → mehrere Absätze im .caveat).
    `quellen`: Liste aus {"label", "url"(optional)} → klickbarer Quellen-Block.
    `recheck_von`: Datum (JJJJ-MM-TT) des Vorgänger-Dashboards → eyebrow „· Re-Check" + Footer.
    `out_path`: NUR für Reparaturen — ersetzt exakt diese bestehende Datei (relativ zum
    Projekt oder absolut) statt eine neue datierte Datei anzulegen. Ohne `out_path` entsteht
    IMMER eine neue, datierte Datei (Phase-30-Regel: Historie bleibt liegen); die Registrierung
    am Job übernimmt danach wie bisher `pipeline.deepdive.register` — dieses Modul schreibt
    NICHT in die DB.

    Rückgabe: {"job_id", "company_fit_path", "abschnitte": [erkannte Bausteine]}."""
    if fit_ampel not in _AMPEL_WERTE:
        raise ValueError(f"fit_ampel muss gruen|gelb|rot sein, nicht {fit_ampel!r}")
    abschnitte = abschnitte or {}
    unbekannt = set(abschnitte) - _ABSCHNITT_SCHLUESSEL
    if unbekannt:
        raise ValueError(f"Unbekannte abschnitte-Schlüssel: {sorted(unbekannt)} — erlaubt sind nur "
                         f"{sorted(_ABSCHNITT_SCHLUESSEL)}")
    arbeitgeber = abschnitte.get("arbeitgeber_realitaet") or {}
    unbekannt = set(arbeitgeber) - {k for k, _ in _ARBEITGEBER_KARTEN}
    if unbekannt:
        raise ValueError(f"Unbekannte arbeitgeber_realitaet-Schlüssel: {sorted(unbekannt)} — "
                         f"erlaubt sind {sorted(k for k, _ in _ARBEITGEBER_KARTEN)}")

    init_db()
    with Session(engine) as s:
        job = s.get(Job, job_id)
        if not job:
            raise SystemExit(f"Job {job_id} nicht gefunden")
        firma = job.company_name or "Unbekannte Firma"

    heute = datetime.date.today().isoformat()
    erkannt = []

    # Kopf
    eyebrow = "Company-Fit · Re-Check" if recheck_von else "Company-Fit"
    meta = [("Fit-Ampel",
             f'<span class="dot {_AMPEL_DOT[fit_ampel]}"></span>{_AMPEL_LABEL[fit_ampel]}'
             + (f" · {_esc(fit_text)}" if str(fit_text or "").strip() else ""))]
    if str(markt_segment or "").strip():
        meta.append(("Markt/Segment", _esc(markt_segment)))
    meta.append(("Datum", heute))
    if str(quellen_kurz or "").strip():
        meta.append(("Quellen", _esc(quellen_kurz)))
    meta_html = "".join(f'<div><p class="k">{k}</p><p class="v">{v}</p></div>' for k, v in meta)
    sub_html = f'\n    <p class="sub">{_esc(sub)}</p>' if str(sub or "").strip() else ""

    teile = [f'''  <header class="head">
    <p class="eyebrow">{eyebrow}</p>
    <h1>{_esc(firma)}</h1>{sub_html}
    <div class="meta">
      {meta_html}
    </div>
  </header>''']

    # BLUF
    if str(bluf or "").strip():
        erkannt.append("bluf")
        teile.append(f'''  <div class="bluf">
    <p class="fitlabel">Kernaussage in einem Satz</p>
    <p>{_esc(bluf)}</p>
  </div>''')

    # Geschäftsmodell & Marktposition (2 Karten)
    was_html = _kv_absaetze(abschnitte.get("geschaeftsmodell_was"))
    wettbewerb_html = _listen_items(abschnitte.get("geschaeftsmodell_wettbewerber"),
                                    "geschaeftsmodell_wettbewerber")
    karten = []
    if was_html:
        karten.append(f'<div class="card">\n      <h3>Was &amp; für wen</h3>\n      {was_html}\n    </div>')
    if wettbewerb_html:
        karten.append('<div class="card">\n      <h3>Wettbewerber &amp; Marktstellung</h3>\n      '
                      f'{wettbewerb_html}\n    </div>')
    if karten:
        erkannt.append("geschaeftsmodell")
        teile.append('  <h2 class="sec">Geschäftsmodell &amp; Marktposition</h2>\n'
                     '  <div class="grid">\n    ' + "\n    ".join(karten) + "\n  </div>")

    # KI-/Digital-Disruption
    ki_html = _absaetze(abschnitte.get("ki_disruption"))
    if ki_html:
        erkannt.append("ki_disruption")
        teile.append(f'  <h2 class="sec">KI-/Digital-Disruption</h2>\n  <div class="card">{ki_html}</div>')

    # Einfluss dieser Rolle (Score-Tabelle)
    tabelle = _einfluss_tabelle(rollen_einfluss)
    if tabelle:
        erkannt.append("rollen_einfluss")
        teile.append(f'  <h2 class="sec">Einfluss dieser Rolle auf das Unternehmen</h2>\n  {tabelle}')

    # Arbeitgeber-Realität (4 Karten, feste Titel/Reihenfolge)
    ag_karten = []
    for schluessel, titel in _ARBEITGEBER_KARTEN:
        inhalt = _absaetze(arbeitgeber.get(schluessel))
        if inhalt:
            ag_karten.append(f'<div class="card">\n      <h3>{_esc(titel)}</h3>\n      {inhalt}\n    </div>')
    if ag_karten:
        erkannt.append("arbeitgeber_realitaet")
        teile.append('  <h2 class="sec">Arbeitgeber-Realität</h2>\n  <div class="grid">\n    '
                     + "\n    ".join(ag_karten) + "\n  </div>")

    # Chancen & Risiken (2 Karten)
    chancen_html = _listen_items(abschnitte.get("chancen"), "chancen")
    risiken_html = _listen_items(abschnitte.get("risiken"), "risiken")
    cr_karten = []
    if chancen_html:
        cr_karten.append(f'<div class="card">\n      <h3>Chancen</h3>\n      {chancen_html}\n    </div>')
    if risiken_html:
        cr_karten.append(f'<div class="card">\n      <h3>Risiken</h3>\n      {risiken_html}\n    </div>')
    if cr_karten:
        erkannt.append("chancen_risiken")
        teile.append('  <h2 class="sec">Chancen &amp; Risiken</h2>\n  <div class="grid">\n    '
                     + "\n    ".join(cr_karten) + "\n  </div>")

    # Klärungsfrage (.caveat) — str oder list[str]
    fragen = klaerungsfrage if isinstance(klaerungsfrage, (list, tuple)) else [klaerungsfrage]
    fragen = [str(f).strip() for f in fragen if str(f or "").strip()]
    if fragen:
        erkannt.append("klaerungsfrage")
        label = "Klärungsfragen fürs Gespräch" if len(fragen) > 1 else "Klärungsfrage fürs Gespräch"
        inhalt = fragen[0] if len(fragen) == 1 else "</p><p>".join(_esc(f) for f in fragen)
        if len(fragen) == 1:
            teile.append(f'  <div class="caveat"><b>{label}:</b> {_esc(inhalt)}</div>')
        else:
            teile.append(f'  <div class="caveat"><b>{label}:</b><p>{inhalt}</p></div>')

    # Quellen
    quellen_html = _quellen_block(quellen)
    if quellen_html:
        erkannt.append("quellen")
        teile.append("  " + quellen_html)

    # Footer
    foot_links = f"Bewerbungs-Mgmt · erzeugt am {heute}"
    if recheck_von:
        foot_links += f" · Re-Check des Dashboards vom {_esc(recheck_von)}"
    teile.append(f'''  <div class="foot">
    <span>{foot_links}</span>
    <span>{_esc(foot_hinweis or _FOOT_HINWEIS_DEFAULT)}</span>
  </div>''')

    _FAVICON = favicon_link()      # P2-72: Icon des geltenden Designs, bei jedem Bericht frisch
    html = f'''<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">{_FAVICON}
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Company-Fit · {_esc(firma)}</title>
<style>{_css()}</style>
</head>
<body>
<div class="wrap">

{chr(10).join(teile)}

</div>
</body>
</html>
'''

    if out_path:
        ziel = Path(out_path)
        if not ziel.is_absolute():
            ziel = DATA_DIR.parent / ziel
        if not ziel.is_file():
            raise SystemExit(f"out_path {out_path} existiert nicht — Reparatur-Modus ersetzt nur "
                             f"bestehende Dateien (neue Dashboards ohne out_path erzeugen)")
        ziel.write_text(html, encoding="utf-8")
        rel = str(ziel.resolve()).replace(str(DATA_DIR.parent.resolve()) + "/", "")
    else:
        from app.naming import report_filename
        _FIT_DIR.mkdir(parents=True, exist_ok=True)
        fname = _freier_name(_FIT_DIR, f"{report_filename('CompanyFit', firma)}.html")
        (_FIT_DIR / fname).write_text(html, encoding="utf-8")
        rel = f"data/company_fit/{fname}"

    return {"job_id": job_id, "company_fit_path": rel, "abschnitte": erkannt}


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != "render":
        print("Aufruf: python -m pipeline.company_fit render <json-datei>", file=sys.stderr)
        return 2
    daten = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    result = render_full(
        daten["job_id"], daten.get("sub"), daten["fit_ampel"], daten.get("fit_text"),
        daten.get("bluf"), daten.get("abschnitte") or {}, daten.get("rollen_einfluss") or [],
        daten.get("klaerungsfrage"), quellen=daten.get("quellen"),
        markt_segment=daten.get("markt_segment"), quellen_kurz=daten.get("quellen_kurz"),
        recheck_von=daten.get("recheck_von"), foot_hinweis=daten.get("foot_hinweis"),
        out_path=daten.get("out_path"))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
