"""P2-72 (Paket R): Das CSS der Berichte aus EINER Funktion (`pipeline/bericht_stil.py`) und der
Befehl `python -m pipeline.bericht_stil einsetzen <Datei>`.

Was hier festgehalten wird (Vertrag R der Spec `tasks/spec_p2-72_design_eine_quelle.md`):

  1. `bericht_css()` mit der Vorgabe trägt die HEUTIGEN Werte der Berichte (Tabelle unten). Mit einem
     Probe-Design (auffällig andere Farben, anderer Name, anderes Icon) steht in keinem der fünf
     erzeugten Berichte (Company-Fit, Transkript-Report, Anzeigen-Snapshot, Aufräum-Bericht,
     Beirats-Dashboard) mehr ein Markenwert der Vorgabe — außer in den Regeln, die Bedeutung tragen
     (Schrift auf Zustandsflächen, neutrale Chips; Liste `ERLAUBTE_MARKENWERTE`). Zustandsfarben
     bleiben fest.
  2. Das Design wird bei jedem Aufruf gelesen (erst Vorgabe, dann Überschreibung anlegen, dann wieder
     entfernen), nie beim Import festgehalten.
  3. Wächter: Keine Konstante `_CSS` und kein `:root` im Quelltext der fünf Renderer; die Vorlage
     `assets/report_theme_bms.html` ist `bericht_css()` mit der Vorgabe.
  4. `einsetzen`: ändert nur den Stilblock und das Icon, zweimal angewandt gleich einmal, legt fehlende
     Blöcke an, fasst mehrere zu einem zusammen, lässt `<style data-zusatz>` unangetastet, meldet
     Klassen ohne Regel (Exit 3), schreibt atomar.
  5. Icon: Ein Bericht mit dem Icon der Vorgabe bleibt unter einem anderen Design unverändert, ein
     verstümmeltes oder fremdes Icon wird ersetzt, ein neuer Bericht trägt das Icon des geltenden
     Designs, und `FAVICON_LINK` ist zur Laufzeit aktuell.

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention); Pfade nur unter `tmp_path`.
Das Design lenkt `BMS_DATA_DIR` per `monkeypatch` auf `tmp_path` um (`design.ueberschreibung_pfad()`
liest es bei jedem Aufruf), der echte Ordner wird nie berührt.
"""
import hashlib
import json
import os
import re
import runpy
import struct
import sys
import uuid
import zlib
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parent.parent
RENDERER_DATEIEN = ("pipeline/company_fit.py", "pipeline/transcript_report.py",
                    "pipeline/posting_snapshot.py", "pipeline/cleanup.py", "beirat_engine.py")

# ── Die heutigen Werte (Vorgabe) ──────────────────────────────────────────────────────────────
# Die `:root`-Variablen des Themas mit der Vorgabe. Wer die Vorgabe ändert, ändert bewusst auch diese
# Tabelle. Zustandsfarben stehen fest, die übrigen kommen aus den Rollen des Designs.
WURZEL_VORGABE = {
    "--ink": "#0B1F3A", "--line": "#2A3F5F", "--paper": "#F4F7FB", "--paper-2": "#FFFFFF",
    "--muted": "#5F6F84", "--text": "#0B1F3A", "--accent": "#00B4D8",
    "--rahmen": "#DCE4EE", "--spur": "#EAF0F6", "--stahl": "#BFC7D5", "--auf-ink": "#FFFFFF",
    "--green": "#18A957", "--amber": "#E4A11B", "--red": "#E5484D",
    "--pos": "#18A957", "--neu": "#94A3B8", "--neg": "#E5484D",
    "--radius": "14px", "--shadow": "0 1px 2px rgba(16,26,40,.06),0 8px 24px rgba(16,26,40,.06)",
}
ZUSTANDSFARBEN = {k: WURZEL_VORGABE[k] for k in ("--green", "--amber", "--red", "--pos", "--neu", "--neg")}
# Werte, die die Berichte vor der Umstellung zeigten (aus dem Thema `assets/report_theme_bms.html`
# vom 13.10.2026), nach Auflösen der Variablen: (Selektor, Eigenschaft) -> Wert.
HEUTIGE_WERTE = {
    ("body", "background"): "#F4F7FB", ("body", "color"): "#0B1F3A",
    ("header.head", "background"): "#0B1F3A", ("header.head", "color"): "#FFFFFF",
    (".head .eyebrow", "color"): "#BFC7D5", (".head .sub", "color"): "#BFC7D5",
    (".head .meta .k", "color"): "#BFC7D5", (".head .meta .v", "color"): "#FFFFFF",
    (".head h1 a", "border-bottom"): "1px solid #2A3F5F",
    (".head .badges .pill", "background"): "#2A3F5F", (".head .badges .pill", "color"): "#BFC7D5",
    (".head .badges .pill", "border"): "1px solid #2A3F5F",
    (".bluf", "border"): "1px solid #DCE4EE", (".bluf", "border-left"): "4px solid #00B4D8",
    (".bluf", "background"): "#FFFFFF", ("h2.sec", "color"): "#5F6F84",
    ("h2.sec::before", "background"): "#00B4D8",
    (".card", "background"): "#FFFFFF", (".card", "border"): "1px solid #DCE4EE",
    (".card p", "color"): "#0B1F3A", (".card .kv", "color"): "#5F6F84",
    ("table.score th", "background"): "#EAF0F6", ("table.score th", "color"): "#5F6F84",
    ("table.score td", "border-bottom"): "1px solid #EAF0F6",
    ("table.score", "border"): "1px solid #DCE4EE",
    (".chip", "border"): "1px solid #DCE4EE", (".chip span", "color"): "#5F6F84",
    ("ol.iq li", "border"): "1px solid #DCE4EE", ("ol.iq li::before", "background"): "#0B1F3A",
    ("ol.iq li::before", "color"): "#FFFFFF",
    ("details.volltext", "border"): "1px solid #DCE4EE",
    ("details.volltext pre", "color"): "#0B1F3A", ("details.volltext summary::before", "color"): "#00B4D8",
    (".sources", "color"): "#5F6F84", (".sources a", "color"): "#00B4D8",
    (".foot", "border-top"): "1px solid #DCE4EE", (".foot", "color"): "#5F6F84",
    ("a:focus-visible", "outline"): "2px solid #00B4D8",
    # Zustandsfarben und Pastelle: fest
    (".dot.green", "background"): "#18A957", (".dot.amber", "background"): "#E4A11B",
    (".dot.red", "background"): "#E5484D", (".dot.grau", "background"): "#94A3B8",
    (".badge.pos", "background"): "#18A957", (".badge.neu", "background"): "#94A3B8",
    (".badge.neg", "background"): "#E5484D", (".badge", "color"): "#fff",
    (".caveat", "background"): "#fbf3e6", (".caveat", "border-left"): "4px solid #E4A11B",
    (".chip.pos", "background"): "#e5f6ec", (".chip.neg", "background"): "#fbe9e7",
    (".chip .tag.direkt", "background"): "#BFECF5", (".chip .tag.direkt", "color"): "#0B1F3A",
}

# Markenwerte der Vorgabe: Alle Farbrollen als Hexwert. In einem Bericht unter einem anderen Design
# darf keiner davon mehr vorkommen — außer in den Regeln unten.
VORGABE_MARKENWERTE = {"#0B1F3A", "#DCE4EE", "#00B4D8", "#0096C7", "#FFFFFF", "#BFC7D5", "#F4F7FB",
                       "#EAF0F6", "#5F6F84", "#2A3F5F"}
# (Selektor, Eigenschaft, Wert): Regeln, die Bedeutung tragen und deshalb fest bleiben, auch wo sie
# zufällig einem Rollenwert gleichen (Leitentscheidung 2).
ERLAUBTE_MARKENWERTE = {
    (":root", "--auf-ink", "#FFFFFF"),               # Weiß auf DUNKLER Markenfläche (hell: auf_marke)
    (".badge", "color", "#FFFFFF"),                  # Schrift auf Zustandsfläche
    ("body", "background", "#FFFFFF"),               # Druck: weißer Seitengrund der Vorlage
    (".chip .tag.direkt", "color", "#0B1F3A"),       # Schrift auf Pastell
    (".chip .tag.indirekt", "background", "#EAF0F6"),    # neutraler Bedeutungs-Chip
    (".chip .tag.indirekt", "color", "#5F6F84"),
    (".card .flag.na", "background", "#EAF0F6"),
}


# ── Hilfen ────────────────────────────────────────────────────────────────────────────────────
def _png(rgb, kante=32) -> bytes:
    """Ein gültiges, einfarbiges, quadratisches PNG (Signatur, IHDR mit Prüfsumme, IDAT, IEND)."""
    def chunk(typ, daten):
        return struct.pack(">I", len(daten)) + typ + daten + struct.pack(">I", zlib.crc32(typ + daten))
    kopf = struct.pack(">IIBBBBB", kante, kante, 8, 2, 0, 0, 0)
    zeile = b"\x00" + bytes(rgb) * kante
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", kopf) + chunk(b"IDAT", zlib.compress(zeile * kante))
            + chunk(b"IEND", b""))


PROBE_FARBEN_DUNKEL = {
    "marke": "#4A148C", "auf_marke": "#F3E5F5", "aktion": "#BF360C", "aktion_hover": "#8E2400",
    "auf_aktion": "#FFFFFF", "stahl": "#CE93D8", "flaeche": "#FFF8E1", "karte": "#FFFDF7",
    "rahmen": "#F0C27B", "spur": "#FFE0B2", "text": "#1B1B1B", "text_gedaempft": "#6D4C41",
    "trenner": "#7B1FA2",
}
PROBE_FARBEN_HELL = dict(PROBE_FARBEN_DUNKEL, marke="#FFD600", auf_marke="#1B1B1B")


@pytest.fixture()
def probe(tmp_path, monkeypatch):
    """Legt ein Probe-Design als Überschreibung unter `tmp_path/design/` an (Datenordner per
    `BMS_DATA_DIR` umgelenkt). Aufruf `probe(farben)` schreibt es und gibt das geltende Design zurück;
    `probe.entfernen()` löscht die Überschreibung wieder."""
    from pipeline import design

    monkeypatch.setenv("BMS_DATA_DIR", str(tmp_path))
    ordner = tmp_path / "design"

    class _Probe:
        def __call__(self, farben=PROBE_FARBEN_DUNKEL):
            ordner.mkdir(exist_ok=True)
            (ordner / "probe-32.png").write_bytes(_png((200, 30, 60), 32))
            (ordner / "probe-180.png").write_bytes(_png((200, 30, 60), 180))
            (ordner / "design.json").write_text(json.dumps({
                "format": 1, "name": "Probe", "farben": farben,
                "schriften": {"ueberschrift": "System", "text": "System"},
                "icon": {"32": "probe-32.png", "180": "probe-180.png"}}), encoding="utf-8")
            d = design.laden()
            assert d.quelle == "ueberschreibung" and d.warnungen == (), d.warnungen
            return d

        def entfernen(self):
            for datei in ordner.glob("*"):
                datei.unlink()
            ordner.rmdir()

    return _Probe()


def _ohne_kommentare(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _deklarationen(css: str) -> list:
    """[(Selektor, Eigenschaft, Wert)] in Dokumentreihenfolge. `@media`-Blöcke werden flach gelesen."""
    aus = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", _ohne_kommentare(css)):
        selektoren = [" ".join(s.split()) for s in m.group(1).split(",")]
        for d in m.group(2).split(";"):
            if ":" in d:
                eig, wert = d.split(":", 1)
                for s in selektoren:
                    aus.append((s, eig.strip().lower(), wert.strip()))
    return aus


def _stilbloecke(html: str) -> list:
    return [m.group(1) for m in re.finditer(r"<style\b[^>]*>(.*?)</style\s*>", html, re.S | re.I)]


def _wurzel(css: str) -> dict:
    return {eig: wert for s, eig, wert in _deklarationen(css) if s == ":root" and eig.startswith("--")}


def _ohne_medien(css: str) -> str:
    """Das CSS ohne seine `@media`-Blöcke (Bildschirm, wie er am Anfang steht)."""
    return re.sub(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css)


def _aufgeloest(css: str) -> dict:
    """{(Selektor, Eigenschaft): Wert} der Regeln ohne `@media`, mit aufgelösten Variablen; spätere
    Regeln gewinnen."""
    deklarationen = _deklarationen(_ohne_medien(css))
    variablen = _wurzel(css)

    def loese(wert):
        for _ in range(5):
            neu = re.sub(r"var\((--[\w-]+)\)", lambda m: variablen[m.group(1)], wert)
            if neu == wert:
                return wert
            wert = neu
        return wert
    return {(s, eig): loese(wert) for s, eig, wert in deklarationen if eig and not eig.startswith("--")}


def _hexwerte(wert: str) -> set:
    gefunden = set()
    for h in re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", wert):
        h = h.upper()
        gefunden.add(h if len(h) == 7 else "#" + "".join(c * 2 for c in h[1:]))
    return gefunden


def _markenwerte_in_regeln(html: str) -> set:
    """{(Selektor, Eigenschaft, Wert)}: Wo steht ein Markenwert der Vorgabe als Literal im CSS?"""
    aus = set()
    for css in _stilbloecke(html):
        for s, eig, wert in _deklarationen(css):
            for h in _hexwerte(wert) & VORGABE_MARKENWERTE:
                aus.add((s, eig, h))
    return aus


def _ohne_stilbloecke(html: str) -> str:
    return re.sub(r"<style\b[^>]*>.*?</style\s*>", "", html, flags=re.S | re.I)


def _sha(pfad: Path) -> str:
    return hashlib.sha256(pfad.read_bytes()).hexdigest()


# ── Die fünf Berichte aus festen, erfundenen Eingaben ─────────────────────────────────────────
def _neuer_job(session):
    from app.models import Job

    kennung = f"BStilTest-{uuid.uuid4().hex[:8]}"
    job = Job(company_name="Beispiel GmbH", title="Teamleiter Zustellung", status=kennung,
              found_date=date.today().isoformat(), dedup_key=f"bstil|{kennung}",
              url=f"https://example.invalid/stelle/{kennung}")
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def _fuenf_berichte(session, monkeypatch, tmp_path) -> dict:
    """Je ein Bericht der fünf Renderer aus erfundenen Eingaben (Max Mustermann, Beispiel GmbH)."""
    from app.models import Interview, Transcript
    import beirat_engine as be
    from pipeline import cleanup, company_fit, posting_snapshot, transcript_report

    berichte = {}
    job = _neuer_job(session)

    monkeypatch.setattr(company_fit, "_FIT_DIR", tmp_path / "fit")
    erg = company_fit.render_full(
        job.id, sub="Logistik · Zustellung", fit_ampel="gelb", fit_text="solider Fit",
        bluf="Die Stelle passt zu Max Mustermann.",
        abschnitte={"geschaeftsmodell_was": {"Kerngeschäft": "Pakete im Nahverkehr."},
                    "chancen": ["Feste Tour"], "risiken": [{"label": "Schicht", "text": "Frühdienst"}]},
        rollen_einfluss=[{"faktor": "Planung", "wert": "pos", "warum": "Ortskenntnis", "relevanz": "Hebel"}],
        klaerungsfrage="Wie viele Sendungen pro Tour?", quellen=[{"label": "Anzeige", "url": "https://example.invalid/a"}])
    berichte["company_fit"] = (tmp_path / "fit" / Path(erg["company_fit_path"]).name).read_text(encoding="utf-8")

    t = Transcript(job_id=job.id, source="manuell", title="1. Gespräch", recorded_at="2026-01-15",
                   language="de", kontakt="Erika Mustermann", gespraechsart="Video-Call")
    iv = Interview(job_id=job.id, runde=1, art="Video-Call", status="Absolviert")
    berichte["transcript_report"] = transcript_report._build_html(
        job, t, iv, [{"title": "Was gut lief", "html": "<ul class='clean'><li>Klare Antworten.</li></ul>"}],
        "Automatisch erzeugt")

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path / "snap")
    posting_snapshot.render_basis(job, text="Wir suchen Verstärkung für unser Zustellteam.")
    session.add(job)
    session.commit()
    session.refresh(job)
    erg = posting_snapshot.render_full(job.id, {"aufgaben": ["Pakete zustellen"], "kontext": "Beispiel."}, "amber",
                                       hinweis="Beispielhinweis")
    berichte["posting_snapshot"] = (tmp_path / "snap" / Path(erg["posting_snapshot_path"]).name).read_text(encoding="utf-8")

    berichte["cleanup"] = cleanup._build_html({
        "erzeugt_am": "2026-01-15T10:30:00Z",
        "orphans": {"anzahl": 1, "groesse_bytes": 1000, "groesse_mb": 0.0, "dateien": [
            {"pfad": "data/x/a.html", "ordner": "data/x", "groesse_bytes": 1000, "alter_tage": 3}]},
        "dangling_referenzen": {"anzahl": 1, "eintraege": [
            {"modell": "Job", "id": 3, "feld": "posting_snapshot_path", "pfad": "data/x/fehlt.html"}]},
        "rotation": {"schwelle_tage": 60, "anzahl": 1, "groesse_mb": 1.0, "je_ordner": {
            "data/backups": {"anzahl": 1, "groesse_bytes": 1_000_000}}},
        "row_pflege": {"schwelle_tage": 90, "agenttask_kandidaten": 1, "run_kandidaten": 0},
        "papierkorb": {"anzahl": 1, "groesse_mb": 0.1}, "auffaellig": True})

    koepfe = {f"kopf{i}": {"anzeige": f"Mitglied {i}"} for i in range(1, 4)}
    d = SimpleNamespace(
        entscheidung={"ampel": "Bedingt", "gesamt": 6.0, "stimmen": {"Bewerben": 2, "Bedingt": 1, "Nicht": 0},
                      "enthaltungen": [], "bereichs_avg": {b: 2.0 + j for j, b in enumerate(be.ABSTIMMUNGS_BEREICHE)}},
        check_synthese={"bedingt_bedingungen": ["Schicht klären"], "risiko_board": [
            {"risiko": "Frühdienst", "schwere": "hoch", "status": "ungeklaert", "naechster_schritt": "Fragen"}],
            "begruendung": "Passt.", "kern_je_kopf": [], "empfehlung": "Bewerben."},
        company_fit_fehlt=True, synthese_fehler=None, job_firma="Beispiel GmbH", job_titel="Zusteller",
        job_id=1, mitglieder=koepfe,
        abstimmung={k: {"scores": {b: 5 for b in be.ABSTIMMUNGS_BEREICHE}, "votum": "Bewerben"} for k in koepfe},
        beitraege=[{"anzeige": "Mitglied 1", "farbe": "#7C4DFF", "text": "Beitrag"}],
        moderationen=[{"text": "Frage?"}])
    berichte["beirat_engine"] = be._dashboard_html(d)
    return berichte


# ── 1. Die Werte ──────────────────────────────────────────────────────────────────────────────
def test_css_mit_der_vorgabe_traegt_die_heutigen_werte():
    from pipeline import bericht_stil

    css = bericht_stil.bericht_css()

    assert _wurzel(css) == WURZEL_VORGABE
    aufgeloest = _aufgeloest(css)
    abweichend = {k: (soll, aufgeloest.get(k)) for k, soll in HEUTIGE_WERTE.items()
                  if (aufgeloest.get(k) or "").lower() != soll.lower()}
    assert abweichend == {}, "Mit der Vorgabe müssen die Berichte aussehen wie vorher"
    assert css.startswith("\n") and css.endswith("\n"), "gehört unverändert zwischen <style> und </style>"


def test_zusatz_steht_hinter_dem_thema_und_gewinnt():
    from pipeline import bericht_stil

    css = bericht_stil.bericht_css(".dot{width:10px;height:10px}\n")

    assert css.rstrip().endswith(".dot{width:10px;height:10px}")
    assert css.index(".dot{display:inline-block;width:14px") < css.index(".dot{width:10px")
    assert _aufgeloest(css)[(".dot", "width")] == "10px"


def test_ein_uebergebenes_design_gilt_statt_des_geltenden(probe):
    from pipeline import bericht_stil, design

    d = probe(PROBE_FARBEN_DUNKEL)
    css = bericht_stil.bericht_css(design=d)
    assert _wurzel(css)["--ink"] == "#4A148C"
    assert _wurzel(bericht_stil.bericht_css(design=design.vorgabe()))["--ink"] == "#0B1F3A"


# ── 1b. Was cv-match und cv-erstellen früher selbst mitbrachten (Paket S) ───────────────────────
# Die Werte stammen aus dem Skill-Text vom 13.10.2026: cv-match (Red-Flag-Zeile, Vorher/Nachher-Karten),
# cv-erstellen (dritte Chip-Gruppe). Fest bleiben die Pastelle der Bedeutung und zwei Werte aus der Palette
# von vor der letzten Umstellung (Rand der `.cmp`-Karte, Blau der `.pill2`-Chips). Die Marke zeigen nur die
# Stellen, die im Skill schon `var(--…)` waren (Karte, Schatten, Überschrift, gedämpfte Schrift).
SKILL_REGELN = {
    # cv-erstellen, Baustein 3 (dritte Chip-Gruppe: abdeckbar, aber nicht eingearbeitet)
    (".chip.warn", "background"): "#fdf3e0", (".chip.warn", "border-color"): "#eed9a8",
    # cv-match, Bewertungstabelle (Muss-Anforderung mit Erfüllung bis 4)
    ("tr.redflag td", "background"): "#fdeceb",
    # cv-match, Vorher/Nachher-Gegenüberstellung
    (".cmp", "border"): "1px solid #e6e9e4", (".cmp", "border-radius"): "12px",
    (".cmp", "background"): "#FFFFFF", (".cmp", "box-shadow"): WURZEL_VORGABE["--shadow"],
    (".cmp", "padding"): "16px 18px", (".cmp", "margin-bottom"): "14px",
    (".cmp h3", "margin"): "0 0 10px", (".cmp h3", "font-size"): "14px", (".cmp h3", "color"): "#0B1F3A",
    (".cmp .pair", "display"): "grid", (".cmp .pair", "grid-template-columns"): "1fr 1fr",
    (".cmp .pair", "gap"): "14px",
    (".cmp .before", "background"): "#fbeceb", (".cmp .before", "border-radius"): "8px",
    (".cmp .before", "padding"): "10px 12px", (".cmp .before", "font-size"): "13.5px",
    (".cmp .before", "color"): "#5f2c28",
    (".cmp .after", "background"): "#e9f6ef", (".cmp .after", "border-radius"): "8px",
    (".cmp .after", "padding"): "10px 12px", (".cmp .after", "font-size"): "13.5px",
    (".cmp .after", "color"): "#1e4a34",
    (".cmp .lbl", "font-size"): "11px", (".cmp .lbl", "text-transform"): "uppercase",
    (".cmp .lbl", "letter-spacing"): ".06em", (".cmp .lbl", "font-weight"): "700",
    (".cmp .lbl", "margin"): "0 0 6px", (".cmp .lbl", "color"): "#5F6F84",
    (".cmp mark", "background"): "#ffe9a8", (".cmp mark", "padding"): "0 2px",
    (".cmp mark", "border-radius"): "2px",
    (".cmp .pills", "margin-top"): "10px", (".cmp .pills", "display"): "flex",
    (".cmp .pills", "flex-wrap"): "wrap", (".cmp .pills", "gap"): "6px",
    (".cmp .pill2", "font-size"): "11px", (".cmp .pill2", "font-weight"): "700",
    (".cmp .pill2", "background"): "#e5eefb", (".cmp .pill2", "color"): "#255fb0",
    (".cmp .pill2", "padding"): "3px 9px", (".cmp .pill2", "border-radius"): "999px",
}
# Diese drei folgen dem Design (im Skill stand dort schon die Variable); alle übrigen sind fest.
SKILL_REGELN_MARKE = {(".cmp", "background"): "karte", (".cmp h3", "color"): "marke",
                      (".cmp .lbl", "color"): "text_gedaempft"}


def test_regeln_aus_cv_match_und_cv_erstellen_stehen_im_zentralen_css():
    from pipeline import bericht_stil

    css = bericht_stil.bericht_css()
    aufgeloest = _aufgeloest(css)

    abweichend = {k: (soll, aufgeloest.get(k)) for k, soll in SKILL_REGELN.items()
                  if (aufgeloest.get(k) or "").lower() != soll.lower()}
    assert abweichend == {}, "Die Berichte müssen die Werte zeigen, die die Skills bisher nannten"
    assert "@media (max-width:720px){.cmp .pair{grid-template-columns:1fr}}" in css


def test_die_neuen_regeln_folgen_dem_design_nur_wo_der_skill_eine_variable_hatte(probe):
    from pipeline import bericht_stil

    d = probe(PROBE_FARBEN_DUNKEL)
    css = bericht_stil.bericht_css(design=d)
    aufgeloest = _aufgeloest(css)

    for stelle, rolle in SKILL_REGELN_MARKE.items():
        assert aufgeloest[stelle].upper() == PROBE_FARBEN_DUNKEL[rolle].upper(), (stelle, rolle)
    fest = {k: (soll, aufgeloest.get(k)) for k, soll in SKILL_REGELN.items()
            if k not in SKILL_REGELN_MARKE and (aufgeloest.get(k) or "").lower() != soll.lower()}
    assert fest == {}, "Bedeutung und Palette von früher bleiben unter jedem Design fest"
    uebrig = _markenwerte_in_regeln(f"<style>{css}</style>") - ERLAUBTE_MARKENWERTE
    assert uebrig == set(), f"Markenwert der Vorgabe als Literal in den Regeln: {sorted(uebrig)}"


# Klassen, die nur die neuen Regeln kennen. In den fünf Renderern darf keine davon vorkommen, sonst träfe
# eine neue Regel dort ein Element (Leitplanke von Paket S: keine Wirkung auf die fünf Renderer).
NEUE_KLASSEN = ("cmp", "pair", "before", "after", "lbl", "pills", "pill2", "redflag", "warn")


@pytest.mark.parametrize("datei", RENDERER_DATEIEN)
def test_waechter_die_neuen_klassen_kommen_in_keinem_der_fuenf_renderer_vor(datei):
    """Statische Seite des Beweises: Keine Zeichenkette im Quelltext setzt eine der neuen Klassen. (Die
    dynamische Seite — berechnete Stile aller Elemente in Chrome, alt gegen neu — lief einmalig in Paket S.)"""
    import ast

    pfad = BACKEND / datei
    baum = ast.parse(pfad.read_text(encoding="utf-8"), filename=str(pfad))
    gesetzt = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str):
            s = knoten.value
            for m in re.finditer(r"class\s*=\s*[\"']([^\"']*)[\"']", s):
                gesetzt.update(m.group(1).split())
            if s.strip() in NEUE_KLASSEN:                       # Klassennamen aus Wörterbüchern
                gesetzt.add(s.strip())
    assert gesetzt & set(NEUE_KLASSEN) == set(), f"{datei}: {sorted(gesetzt & set(NEUE_KLASSEN))}"


# ── 2. Probe-Design: kein Markenwert der Vorgabe in den fünf Berichten ──────────────────────────
@pytest.mark.parametrize("farben, schrift_auf_marke", [
    (PROBE_FARBEN_DUNKEL, "#FFFFFF"),        # dunkle Marke: Weiß bleibt lesbar
    (PROBE_FARBEN_HELL, "#1B1B1B"),          # helle Marke: auf_marke des Designs
])
def test_probe_design_in_allen_fuenf_berichten_kein_markenwert_der_vorgabe(
        farben, schrift_auf_marke, probe, session, monkeypatch, tmp_path):
    probe(farben)
    berichte = _fuenf_berichte(session, monkeypatch, tmp_path)
    assert set(berichte) == {"company_fit", "transcript_report", "posting_snapshot", "cleanup", "beirat_engine"}

    for name, html in berichte.items():
        assert len(_stilbloecke(html)) == 1, name
        wurzel = _wurzel(_stilbloecke(html)[0])
        # Die Rollen des Probe-Designs stehen ausgeschrieben im Bericht
        assert wurzel["--ink"] == farben["marke"].upper(), name
        assert wurzel["--accent"] == farben["aktion"].upper(), name
        assert wurzel["--paper"] == farben["flaeche"].upper(), name
        assert wurzel["--paper-2"] == farben["karte"].upper(), name
        assert wurzel["--rahmen"] == farben["rahmen"].upper(), name
        assert wurzel["--spur"] == farben["spur"].upper(), name
        assert wurzel["--stahl"] == farben["stahl"].upper(), name
        assert wurzel["--line"] == farben["trenner"].upper(), name
        assert wurzel["--text"] == farben["text"].upper(), name
        assert wurzel["--muted"] == farben["text_gedaempft"].upper(), name
        assert wurzel["--auf-ink"].upper() == schrift_auf_marke, name
        # Zustandsfarben: unverändert
        assert {k: wurzel[k] for k in ZUSTANDSFARBEN} == ZUSTANDSFARBEN, name
        # Kein Markenwert der Vorgabe als Literal, außer in den Regeln mit Bedeutung
        uebrig = _markenwerte_in_regeln(html) - ERLAUBTE_MARKENWERTE
        assert uebrig == set(), f"{name}: Markenwert der Vorgabe im Bericht: {sorted(uebrig)}"
        # ... und auch nicht im Rest des Dokuments (Inline-Stile, Text)
        rest = _ohne_stilbloecke(html).upper()
        assert [h for h in VORGABE_MARKENWERTE if h in rest] == [], name
        # Icon des Probe-Designs, nicht das der Vorgabe
        from app import favicon
        assert favicon.favicon_link() in html and favicon.vorgabe_link() not in html, name


def test_zustandsfarben_bleiben_fest_auch_in_den_eigenen_regeln_der_renderer(probe, session, monkeypatch, tmp_path):
    probe(PROBE_FARBEN_DUNKEL)
    berichte = _fuenf_berichte(session, monkeypatch, tmp_path)

    beirat = _aufgeloest(_stilbloecke(berichte["beirat_engine"])[0])
    assert beirat[(".ampel-banner.gruen .titel", "color")] == "#18A957"
    assert beirat[("table.risiko td.schwere-hoch", "color")] == "#E5484D"
    assert beirat[(".ampel-banner.gruen", "background")] == "#eafaf1"
    assert beirat[(".scorebar-track", "background")] == "#FFE0B2", "Spur folgt dem Design"
    assert beirat[(".scorebar-fill", "background")] == "#BF360C", "Aktionsfarbe folgt dem Design"
    snapshot = _aufgeloest(_stilbloecke(berichte["posting_snapshot"])[0])
    assert snapshot[(".dot.green", "background")] == "#18A957"


# ── 3. Zur Laufzeit gelesen ───────────────────────────────────────────────────────────────────
def test_das_design_wird_bei_jedem_aufruf_gelesen(probe):
    from pipeline import bericht_stil, cleanup

    vorher = bericht_stil.bericht_css()
    assert _wurzel(vorher)["--ink"] == "#0B1F3A"

    probe(PROBE_FARBEN_DUNKEL)                      # Überschreibung anlegen, kein Neustart, kein Leeren
    waehrend = bericht_stil.bericht_css()
    assert _wurzel(waehrend)["--ink"] == "#4A148C"
    assert _wurzel(cleanup._css())["--ink"] == "#4A148C", "auch der Renderer liest zur Laufzeit"

    probe.entfernen()                               # wieder weg: wieder die Vorgabe, byte-gleich
    assert bericht_stil.bericht_css() == vorher


def test_die_rollen_eines_ungueltigen_designs_fallen_auf_die_vorgabe_zurueck(probe, tmp_path):
    from pipeline import bericht_stil

    probe(PROBE_FARBEN_DUNKEL)
    (tmp_path / "design" / "design.json").write_text("{kaputt", encoding="utf-8")

    assert _wurzel(bericht_stil.bericht_css()) == WURZEL_VORGABE


# ── 4. Wächter ────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("datei", RENDERER_DATEIEN)
def test_waechter_keine_css_konstante_mit_eigenem_root_in_den_renderern(datei):
    """Die fünf Renderer reichen nur ihre eigenen Regeln als Zusatz mit: keine Konstante `_CSS` und
    kein Text mit `:root` im Quelltext (ein eigenes `:root` wäre eine zweite Quelle des Designs)."""
    import ast

    pfad = BACKEND / datei
    baum = ast.parse(pfad.read_text(encoding="utf-8"), filename=str(pfad))
    konstanten, mit_root = [], []
    for knoten in ast.walk(baum):
        ziele = []
        if isinstance(knoten, ast.Assign):
            ziele = [t.id for t in knoten.targets if isinstance(t, ast.Name)]
        elif isinstance(knoten, ast.AnnAssign) and isinstance(knoten.target, ast.Name):
            ziele = [knoten.target.id]
        konstanten += [z for z in ziele if z == "_CSS"]
        if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str) and ":root" in knoten.value:
            mit_root.append(knoten.value[:40])
    assert konstanten == [], f"{datei}: Konstante _CSS gefunden — das CSS kommt aus bericht_stil.bericht_css()"
    assert mit_root == [], f"{datei}: eigenes :root im Quelltext"


@pytest.mark.parametrize("datei", RENDERER_DATEIEN)
def test_waechter_renderer_rufen_bericht_css_und_binden_das_icon_zur_laufzeit(datei):
    quelle = (BACKEND / datei).read_text(encoding="utf-8")
    assert "bericht_css(" in quelle
    assert "favicon_link()" in quelle, "das Icon des geltenden Designs wird bei jedem Bericht neu geholt"
    assert "import FAVICON_LINK" not in quelle, "FAVICON_LINK würde beim Import festgehalten"


def test_migrate_reports_nimmt_das_css_vom_transcript_report():
    quelle = (BACKEND / "pipeline/migrate_reports.py").read_text(encoding="utf-8")
    assert "TR._CSS" not in quelle and "TR._css()" in quelle


def test_vorlage_entspricht_bericht_css_mit_der_vorgabe():
    from pipeline import bericht_stil

    abweichung = bericht_stil.vorlage_abweichung()

    assert abweichung is None, abweichung


def test_vorlage_abweichung_nennt_den_befehl_zum_neu_erzeugen(tmp_path):
    from pipeline import bericht_stil

    kopie = tmp_path / "vorlage.html"
    text = bericht_stil.VORLAGE.read_text(encoding="utf-8")
    kopie.write_text(text.replace("--rahmen:#DCE4EE", "--rahmen:#000000", 1), encoding="utf-8")

    abweichung = bericht_stil.vorlage_abweichung(kopie)

    assert abweichung and "python -m pipeline.bericht_stil vorlage" in abweichung
    assert bericht_stil.vorlage_schreiben(kopie) is True          # neu erzeugen heilt sie ...
    assert bericht_stil.vorlage_abweichung(kopie) is None
    assert bericht_stil.vorlage_schreiben(kopie) is False         # ... und ist wiederholbar
    assert kopie.read_text(encoding="utf-8") == text


def test_vorlage_ist_unter_einem_anderen_design_trotzdem_die_vorgabe(probe):
    """Die Vorlage zeigt immer die Vorgabe (wie die mitgelieferten docs/*.html), nie eine Überschreibung."""
    from pipeline import bericht_stil

    probe(PROBE_FARBEN_DUNKEL)

    assert bericht_stil.vorlage_abweichung() is None


def test_vorlage_behaelt_den_pflichtfuss_und_nennt_den_neuen_weg():
    from pipeline import bericht_stil

    text = bericht_stil.VORLAGE.read_text(encoding="utf-8")

    assert "Bewerbungs-Mgmt · erzeugt am" in text, "Pflichtwortlaut des Fußes"
    assert "Daube.Tech" not in text.split("<div class=\"foot\">")[1]
    assert "EINZIGE Style-Quelle" not in text and "wörtlich" not in text.split("</style>")[0].lower()
    assert "bericht_stil einsetzen" in text
    assert "data-zusatz" not in text, "Paket S: Die Vorlage bietet kein eigenes CSS mehr an"


def test_vorlage_zeigt_die_klassen_der_modell_berichte_und_besteht_report_check():
    """Paket S: Die Vorlage ist die Quelle für Aufbau und Klassen. Alles, was die Skills schreiben, steht dort
    als Beispiel-Markup, und jede Klasse darin hat ihre Regel."""
    from pipeline import bericht_stil, report_check

    text = bericht_stil.VORLAGE.read_text(encoding="utf-8")

    for name in NEUE_KLASSEN:
        assert re.search(rf'class="[^"]*\b{name}\b', text), f"Beispiel-Markup mit Klasse {name} fehlt in der Vorlage"
    assert report_check.pruefe(text) == []


def test_der_hinweis_bei_klassen_ohne_regel_bietet_kein_eigenes_css_an(tmp_path, capsys):
    """Beide Hinweistexte (`einsetzen` und `report_check`) raten, die Klasse durch eine aus der Vorlage zu
    ersetzen. Der Zusatzblock bleibt als Mechanismus im Code, wird aber nirgends empfohlen."""
    from pipeline import bericht_stil, report_check

    pfad = _bericht(tmp_path, BERICHT.replace('<div class="card">', '<div class="card"><span class="kasten best">x</span>'))

    assert bericht_stil.main(["einsetzen", str(pfad)]) == bericht_stil.EXIT_KLASSEN_OHNE_REGEL
    ausgabe = capsys.readouterr().out
    assert "assets/report_theme_bms.html" in ausgabe and "ersetzen" in ausgabe
    assert "data-zusatz" not in ausgabe and "ergänzen" not in ausgabe

    assert report_check.main([str(pfad)]) == 1
    ausgabe = capsys.readouterr().out
    assert "bericht_stil" in ausgabe and "einsetzen" in ausgabe and "assets/report_theme_bms.html" in ausgabe
    assert "data-zusatz" not in ausgabe and "ergänzen" not in ausgabe


# ── 5. einsetzen ──────────────────────────────────────────────────────────────────────────────
BERICHT = (
    '<!DOCTYPE html>\n<html lang="de">\n<head>\n<meta charset="utf-8">\n<title>Probe</title>\n'
    "<style>body{color:red}</style>\n</head>\n<body>\n"
    '<header class="head"><p class="eyebrow">E</p><h1>Titel</h1></header>\n'
    '<div class="card"><p>Inhalt mit Umlauten: äöüß</p></div>\n</body>\n</html>\n'
)


def _bericht(tmp_path, text=BERICHT, name="bericht.html") -> Path:
    pfad = tmp_path / name
    pfad.write_bytes(text.encode("utf-8"))
    return pfad


def test_einsetzen_aendert_nur_stilblock_und_icon(tmp_path):
    from app import favicon
    from pipeline import bericht_stil

    pfad = _bericht(tmp_path)

    erg = bericht_stil.einsetzen(pfad)

    erwartet = (BERICHT.replace('<meta charset="utf-8">', '<meta charset="utf-8">' + favicon.favicon_link(), 1)
                .replace("<style>body{color:red}</style>", "<style>" + bericht_stil.bericht_css() + "</style>", 1))
    assert pfad.read_bytes() == erwartet.encode("utf-8"), "außer Stilblock und Icon bleibt jedes Byte"
    assert erg.geaendert and erg.stil_geaendert and erg.icon_geaendert
    assert erg.klassen_ohne_regel == []


def test_einsetzen_zweimal_angewandt_ist_gleich_einmal(tmp_path):
    from pipeline import bericht_stil

    pfad = _bericht(tmp_path)
    bericht_stil.einsetzen(pfad)
    einmal = pfad.read_bytes()

    zweites = bericht_stil.einsetzen(pfad)

    assert pfad.read_bytes() == einmal
    assert not zweites.geaendert and not zweites.stil_geaendert and not zweites.icon_geaendert


def test_einsetzen_legt_einen_fehlenden_stilblock_im_head_an(tmp_path):
    from pipeline import bericht_stil

    ohne = BERICHT.replace("<style>body{color:red}</style>\n", "")
    pfad = _bericht(tmp_path, ohne)

    bericht_stil.einsetzen(pfad)
    neu = pfad.read_text(encoding="utf-8")

    assert neu.count("<style>") == 1
    assert neu.index("<style>") < neu.index("</head>") < neu.index("<body>")
    assert "<title>Probe</title>\n<style>" in neu
    icon = re.search(r'<link rel="icon"[^>]*>', neu).group(0)
    assert neu.replace(icon, "").replace("<style>" + bericht_stil.bericht_css() + "</style>\n", "") == ohne
    einmal = pfad.read_bytes()
    bericht_stil.einsetzen(pfad)
    assert pfad.read_bytes() == einmal


def test_einsetzen_fasst_mehrere_stilbloecke_zu_einem_zusammen(tmp_path):
    from pipeline import bericht_stil

    mehrere = BERICHT.replace("<style>body{color:red}</style>\n",
                              "<style>body{color:red}</style>\n<style type=\"text/css\">\n.alt{a:b}\n</style>\n")
    pfad = _bericht(tmp_path, mehrere)

    bericht_stil.einsetzen(pfad)
    neu = pfad.read_text(encoding="utf-8")

    assert len(_stilbloecke(neu)) == 1
    assert ".alt{a:b}" not in neu
    assert _stilbloecke(neu)[0] == bericht_stil.bericht_css()
    assert "<style>\n\n" not in neu and "</style>\n\n</head>" not in neu, "keine Leerzeile hinterlassen"


def test_einsetzen_laesst_den_zusatzblock_unangetastet(tmp_path):
    """Auffanglösung: Ein Bericht mit eigenen Regeln behält sie in `<style data-zusatz>` (empfohlen wird der Weg
    nirgends mehr, `.cmp` selbst steht seit Paket S im zentralen CSS; der Selektor ist hier nur ein Beispiel)."""
    from pipeline import bericht_stil

    zusatz = '<style data-zusatz>\n.cmp{display:flex;gap:8px}\n.cmp .best{font-weight:700}\n</style>'
    mit = BERICHT.replace("</head>", zusatz + "\n</head>")
    pfad = _bericht(tmp_path, mit.replace("<div class=\"card\">", '<div class="card cmp">'))

    bericht_stil.einsetzen(pfad)
    neu = pfad.read_text(encoding="utf-8")

    assert zusatz in neu, "der Zusatzblock bleibt Byte für Byte stehen"
    bloecke = _stilbloecke(neu)
    assert bloecke[0] == bericht_stil.bericht_css() and len(bloecke) == 2
    assert neu.index("<style>") < neu.index("<style data-zusatz>"), "Thema vor dem Zusatz, damit der Zusatz gewinnt"
    einmal = pfad.read_bytes()
    bericht_stil.einsetzen(pfad)
    assert pfad.read_bytes() == einmal


def test_einsetzen_stellt_das_thema_vor_einen_zusatzblock_der_zuerst_steht(tmp_path):
    from pipeline import bericht_stil

    zusatz = "<style data-zusatz>\n.cmp{color:red}\n</style>"
    verdreht = BERICHT.replace("<style>body{color:red}</style>\n", zusatz + "\n<style>body{color:red}</style>\n")
    pfad = _bericht(tmp_path, verdreht)

    bericht_stil.einsetzen(pfad)
    neu = pfad.read_text(encoding="utf-8")

    assert neu.index("<style>") < neu.index("<style data-zusatz>")
    assert neu.count(zusatz) == 1 and len(_stilbloecke(neu)) == 2
    einmal = pfad.read_bytes()
    bericht_stil.einsetzen(pfad)
    assert pfad.read_bytes() == einmal


def test_einsetzen_ohne_themenblock_aber_mit_zusatz_legt_das_thema_davor_an(tmp_path):
    from pipeline import bericht_stil

    zusatz = "<style data-zusatz>\n.cmp{color:red}\n</style>"
    pfad = _bericht(tmp_path, BERICHT.replace("<style>body{color:red}</style>", zusatz))

    bericht_stil.einsetzen(pfad)
    neu = pfad.read_text(encoding="utf-8")

    assert neu.index("<style>") < neu.index("<style data-zusatz>") and neu.count(zusatz) == 1


def test_ein_style_tag_in_einem_html_kommentar_ist_kein_stilblock(tmp_path):
    """Die Vorlage erklärt sich in Kommentaren selbst und nennt dort `<style>`-Tags."""
    from pipeline import bericht_stil

    kommentar = "<!-- erklaert den <style>-Block: <style>x{a:b}</style> und </head> -->\n"
    pfad = _bericht(tmp_path, BERICHT.replace("<title>", kommentar + "<title>"))

    bericht_stil.einsetzen(pfad)
    neu = pfad.read_text(encoding="utf-8")

    assert kommentar in neu
    assert len(_stilbloecke(_ohne_kommentare_html(neu))) == 1


def _ohne_kommentare_html(text):
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


@pytest.mark.parametrize("leer", ["<style/>", "<style />", "<STYLE data-zusatz/>"])
@pytest.mark.parametrize("schon_eingesetzt", [False, True], ids=["frisch", "schon_eingesetzt"])
def test_einsetzen_entfernt_ein_selbstschliessendes_style(tmp_path, leer, schon_eingesetzt):
    """Ein Modell schrieb `<style/>` als „leeren Stilblock“ in den Kopf. Der Browser öffnet damit einen Block,
    der den eingesetzten `<style>` als Text verschluckt; `:root` wird ungültig, der Bericht verliert alle
    Farben. Frisch (ohne `</style>`) und schon einmal eingesetzt (`<style/>` direkt vor dem Thema)."""
    from pipeline import bericht_stil

    thema = "<style>" + bericht_stil.bericht_css() + "</style>\n" if schon_eingesetzt else ""
    pfad = _bericht(tmp_path, BERICHT.replace("<style>body{color:red}</style>\n", leer + "\n" + thema))

    bericht_stil.einsetzen(pfad)
    neu = pfad.read_text(encoding="utf-8")

    assert leer not in neu
    assert neu.lower().count("<style") == 1 and _stilbloecke(neu) == [bericht_stil.bericht_css()]
    assert "<title>Probe</title>\n<style>\n" in neu, "keine Leerzeile, wo der leere Block stand"
    einmal = pfad.read_bytes()
    bericht_stil.einsetzen(pfad)
    assert pfad.read_bytes() == einmal


def test_einsetzen_setzt_ein_verstuemmeltes_oder_fremdes_icon_und_laesst_das_richtige(tmp_path):
    from app import favicon
    from pipeline import bericht_stil

    kaputt = '<link rel="icon" type="image/png" href="data:image/png;base64,iVBORw0KGgoAAAANS">'
    pfad = _bericht(tmp_path, BERICHT.replace("<title>", kaputt + "\n<title>"))

    bericht_stil.einsetzen(pfad)
    neu = pfad.read_text(encoding="utf-8")

    assert neu.count(favicon.favicon_link()) == 1 and "iVBORw0KGgoAAAANS\"" not in neu
    assert len(re.findall(r'rel="icon"', neu)) == 1


def test_einsetzen_meldet_klassen_ohne_regel_und_der_zusatzblock_heilt_es(tmp_path, capsys):
    from pipeline import bericht_stil

    mit_klasse = BERICHT.replace('<div class="card">', '<div class="card"><span class="kasten best">x</span>')
    pfad = _bericht(tmp_path, mit_klasse)

    code = bericht_stil.main(["einsetzen", str(pfad)])
    ausgabe = capsys.readouterr().out

    assert code == bericht_stil.EXIT_KLASSEN_OHNE_REGEL == 3
    assert 'class="best kasten"' in ausgabe and ".kasten" in ausgabe
    assert "<style>" in pfad.read_text(encoding="utf-8") and "body{color:red}" not in pfad.read_text(encoding="utf-8"), \
        "die Datei ist trotz der Meldung geschrieben"

    pfad.write_text(pfad.read_text(encoding="utf-8").replace(
        "</head>", "<style data-zusatz>\n.kasten{color:red}\n.best{font-weight:700}\n</style>\n</head>"), encoding="utf-8")
    assert bericht_stil.main(["einsetzen", str(pfad)]) == 0


def test_einsetzen_verwendet_report_check(monkeypatch, tmp_path):
    """Die Prüfung der Klassen ist die von `report_check`, nicht eine Kopie davon."""
    from pipeline import bericht_stil, report_check

    aufrufe = []
    monkeypatch.setattr(report_check, "pruefe", lambda html: aufrufe.append(html) or ["Probe-Befund"])
    pfad = _bericht(tmp_path)

    erg = bericht_stil.einsetzen(pfad)

    assert erg.klassen_ohne_regel == ["Probe-Befund"] and len(aufrufe) == 1
    assert _stilbloecke(aufrufe[0])[0] == bericht_stil.bericht_css(), "geprüft wird der fertige Bericht"


def test_einsetzen_exit_codes_und_unbrauchbare_dateien(tmp_path, capsys):
    from pipeline import bericht_stil

    assert bericht_stil.main(["einsetzen", str(tmp_path / "fehlt.html")]) == bericht_stil.EXIT_FEHLER
    assert bericht_stil.main(["einsetzen"]) == bericht_stil.EXIT_FEHLER
    assert bericht_stil.main([]) == bericht_stil.EXIT_FEHLER
    fragment = _bericht(tmp_path, "<div>nur ein Schnipsel</div>", "fragment.html")
    vorher = _sha(fragment)
    assert bericht_stil.main(["einsetzen", str(fragment)]) == bericht_stil.EXIT_FEHLER
    assert _sha(fragment) == vorher, "eine unbrauchbare Datei bleibt unverändert"
    kein_utf8 = tmp_path / "latin.html"
    kein_utf8.write_bytes('<html><head></head><body>Gr\xfc\xdfe</body></html>'.encode("latin-1"))
    vorher = _sha(kein_utf8)
    assert bericht_stil.main(["einsetzen", str(kein_utf8)]) == bericht_stil.EXIT_FEHLER
    assert _sha(kein_utf8) == vorher
    capsys.readouterr()


def test_einsetzen_schreibt_atomar_und_behaelt_die_rechte(tmp_path, monkeypatch):
    from pipeline import bericht_stil

    pfad = _bericht(tmp_path)
    os.chmod(pfad, 0o640)
    bericht_stil.einsetzen(pfad)
    if os.name == "posix":                           # Windows kennt diese Rechte nicht
        assert oct(pfad.stat().st_mode & 0o777) == oct(0o640)
    assert [p.name for p in tmp_path.iterdir()] == ["bericht.html"], "keine Zwischendatei bleibt liegen"

    # Schlägt das Ersetzen fehl, bleibt das Original unverändert und es bleibt nichts liegen
    pfad2 = _bericht(tmp_path, name="zweiter.html")
    vorher = _sha(pfad2)

    def kaputt(*_a, **_k):
        raise OSError("Platte voll")
    monkeypatch.setattr(bericht_stil.os, "replace", kaputt)
    with pytest.raises(OSError):
        bericht_stil.einsetzen(pfad2)
    assert _sha(pfad2) == vorher
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bericht.html", "zweiter.html"]


def test_einsetzen_nimmt_mehrere_dateien_und_meldet_den_schlimmsten_code(tmp_path, capsys):
    from pipeline import bericht_stil

    gut = _bericht(tmp_path, name="a.html")
    schlecht = _bericht(tmp_path, BERICHT.replace('<div class="card">', '<div class="x y">'), "b.html")

    code = bericht_stil.main(["einsetzen", str(gut), str(schlecht)])

    assert code == 3
    ausgabe = capsys.readouterr().out
    assert "✓ a.html" in ausgabe and "✓ b.html" in ausgabe and "x y" in ausgabe


def test_einsetzen_laeuft_als_modul(tmp_path, monkeypatch, capsys):
    pfad = _bericht(tmp_path)
    monkeypatch.setattr(sys, "argv", ["bericht_stil", "einsetzen", str(pfad)])

    with pytest.raises(SystemExit) as ende:
        runpy.run_module("pipeline.bericht_stil", run_name="__main__")

    assert ende.value.code == 0
    assert "✓ bericht.html: Stil und Icon eingesetzt" in capsys.readouterr().out
    assert "<style>body{color:red}</style>" not in pfad.read_text(encoding="utf-8")


def test_einsetzen_nutzt_das_geltende_design(probe, tmp_path):
    from app import favicon
    from pipeline import bericht_stil

    probe(PROBE_FARBEN_DUNKEL)
    pfad = _bericht(tmp_path)

    bericht_stil.einsetzen(pfad)
    neu = pfad.read_text(encoding="utf-8")

    assert _wurzel(_stilbloecke(neu)[0])["--ink"] == "#4A148C"
    assert favicon.favicon_link() in neu and favicon.vorgabe_link() not in neu


# ── 6. Icon ───────────────────────────────────────────────────────────────────────────────────
def _dokument(icon: str = "") -> str:
    return f'<html><head><meta charset="utf-8">{icon}<title>x</title></head><body>x</body></html>'


def test_icon_der_vorgabe_bleibt_unter_einem_anderen_design_unveraendert(probe):
    from app import favicon

    vorgabe = favicon.vorgabe_link()
    probe(PROBE_FARBEN_DUNKEL)
    bericht = _dokument(vorgabe)

    assert favicon.favicon_link() != vorgabe, "das Probe-Design hat ein anderes Icon"
    assert favicon.hat_bms_favicon(bericht)
    assert favicon.mit_favicon(bericht) == bericht


def test_icon_des_geltenden_designs_bleibt_unveraendert(probe):
    from app import favicon

    probe(PROBE_FARBEN_DUNKEL)
    bericht = _dokument(favicon.favicon_link())

    assert favicon.mit_favicon(bericht) == bericht


def test_verstuemmeltes_oder_fremdes_icon_wird_durch_das_des_geltenden_designs_ersetzt(probe):
    from app import favicon

    probe(PROBE_FARBEN_DUNKEL)
    neu_link = favicon.favicon_link()
    verstuemmelt = '<link rel="icon" type="image/png" href="data:image/png;base64,iVBORw0KGgoAAAANS">'
    fremd = '<link rel="shortcut icon" href="/eigen.ico">'

    for kaputt in (verstuemmelt, fremd):
        ergebnis = favicon.mit_favicon(_dokument(kaputt))
        assert ergebnis.count(neu_link) == 1
        assert "iVBORw0KGgoAAAANS\"" not in ergebnis and "/eigen.ico" not in ergebnis


def test_ein_neuer_bericht_traegt_das_icon_des_geltenden_designs(probe):
    from app import favicon
    from pipeline import cleanup

    vorgabe = favicon.vorgabe_link()
    probe(PROBE_FARBEN_DUNKEL)
    html = cleanup._build_html({
        "erzeugt_am": "2026-01-15T10:30:00Z", "orphans": {"anzahl": 0, "groesse_mb": 0, "dateien": []},
        "dangling_referenzen": {"anzahl": 0, "eintraege": []},
        "rotation": {"schwelle_tage": 60, "anzahl": 0, "groesse_mb": 0, "je_ordner": {}},
        "row_pflege": {"schwelle_tage": 90, "agenttask_kandidaten": 0, "run_kandidaten": 0},
        "papierkorb": {"anzahl": 0, "groesse_mb": 0}, "auffaellig": False})

    assert favicon.favicon_link() in html and vorgabe not in html
    assert favicon.mit_favicon(_dokument()).count(favicon.favicon_link()) == 1


def test_das_icon_gilt_zur_laufzeit_auch_ueber_den_namen_favicon_link(probe):
    """`FAVICON_LINK` war eine beim Import berechnete Konstante; jetzt wird er beim Zugriff berechnet."""
    from app import favicon

    vorgabe = favicon.vorgabe_link()
    assert favicon.FAVICON_LINK == vorgabe

    probe(PROBE_FARBEN_DUNKEL)
    assert favicon.FAVICON_LINK == favicon.favicon_link() != vorgabe
    from app.favicon import FAVICON_LINK            # auch die Importform bekommt den aktuellen Stand
    assert FAVICON_LINK == favicon.favicon_link()
    assert favicon.gueltige_links() == (favicon.favicon_link(), vorgabe)

    probe.entfernen()
    assert favicon.FAVICON_LINK == vorgabe
    assert favicon.gueltige_links() == (vorgabe,)


def test_favicon_link_gibt_es_nur_fuer_vorhandene_namen():
    import app.favicon as favicon

    with pytest.raises(AttributeError):
        favicon.GIBT_ES_NICHT
    assert not hasattr(favicon, "FAVICON_DATEI"), "das Icon kommt aus dem Design, nicht aus frontend/public"


def test_icon_der_vorgabe_ist_byte_gleich_dem_bisherigen_app_icon():
    """Die mitgelieferten docs/*.html tragen das Icon und werden byte-genau verglichen
    (test_docs_html.py): Mit der Vorgabe darf sich kein Byte ändern."""
    import base64

    from app import favicon
    from pipeline import design

    png = design.vorgabe().icon_bytes(32)

    assert favicon.vorgabe_link() == ('<link rel="icon" type="image/png" href="data:image/png;base64,'
                                      + base64.b64encode(png).decode("ascii") + '">')
    assert hashlib.sha256(png).hexdigest() == "ee30554183c03b4c1cff8b01b7d458ef6b1f2299e7db0854f22616d92b2dc40b"
