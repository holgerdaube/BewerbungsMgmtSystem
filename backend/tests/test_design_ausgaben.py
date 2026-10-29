"""P2-72 (Vertrag R) — Digest, Coach-Site, Doku-Seiten und Excel-Export nehmen ihre Markenwerte aus dem
geltenden Design.

Deckt ab:
  1. MIT DER VORGABE sieht jede Ausgabe aus wie vorher: Die CSS-Texte von Digest, Coach-Site und Doku-Seiten
     sind byte-gleich zu denen von vor P2-72 (SHA-256 aus dem Stand 1.7.0 festgehalten), dazu die heutigen
     Werte in den Ausgaben und in der Excel-Datei.
  2. MIT EINEM PROBE-DESIGN (auffällig andere Farben, andere Schrift, anderes Icon, unter `tmp_path`) steht in
     keiner Ausgabe mehr ein Markenwert der Vorgabe — außer dort, wo er Bedeutung ist (Zustandsfarben,
     Pastelle der Änderungs-Tags, Schrift darauf). Das Probe-Design ist selbst gültig (keine Warnung).
  3. ICON: Digest, Coach-Site (Seiten und kopierte Berichte) und Doku-Ansicht tragen das Icon des Designs,
     das GILT; die mitgelieferten `docs/*.html` das der Vorgabe, auch wenn ein anderes Design gilt.
  4. LAUFZEIT STATT IMPORT: Eine geänderte Design-Datei wirkt beim nächsten Aufruf, ohne dass ein Modul neu
     geladen wird. Der Quelltext-Wächter hält fest, dass kein Modul das Icon oder das Design beim Import
     festhält; er ist selbst geprüft.
  5. Die Doku-Ansicht (`app/doku.py`) rendert mit dem geltenden Design, die mitgelieferten `docs/*.html`
     bleiben unter jedem Design byte-gleich zur Vorgabe.

Alles unter `tmp_path`: Der Datenordner wird nur für den einzelnen Test umgelenkt, das Profil (`config/
profil.md`) wird nie gelesen. Kein app.*/pipeline.*-Import auf Modulebene (conftest.py).
"""
import ast
import base64
import hashlib
import json
import re
import struct
import uuid
import zlib
from datetime import date
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJEKT_DIR = BACKEND_DIR.parent

# Die heutigen Werte (Leitentscheidung 1) — Tabelle wie in test_design.py.
HEUTIGE_FARBEN = {
    "marke": "#0B1F3A", "auf_marke": "#DCE4EE",
    "aktion": "#00B4D8", "aktion_hover": "#0096C7", "auf_aktion": "#FFFFFF",
    "stahl": "#BFC7D5", "flaeche": "#F4F7FB", "karte": "#FFFFFF", "rahmen": "#DCE4EE",
    "spur": "#EAF0F6", "text": "#0B1F3A", "text_gedaempft": "#5F6F84", "trenner": "#2A3F5F",
}

# Ein Probe-Design, das sich in jeder Rolle von der Vorgabe unterscheidet. Alle Paare bestehen die
# Kontrastprüfung (4,5:1), sonst fiele ein Paar auf die Vorgabe zurück und der Test sähe einen Vorgabe-Wert.
PROBE_FARBEN = {
    "marke": "#7A1E5C", "auf_marke": "#FBEFF7",
    "aktion": "#B4410A", "aktion_hover": "#8A3208", "auf_aktion": "#FFF3E0",
    "stahl": "#C9A7BC", "flaeche": "#FFF8E1", "karte": "#FFFDF5", "rahmen": "#E0C9A6",
    "spur": "#F3E3C3", "text": "#2B1030", "text_gedaempft": "#6B5560", "trenner": "#5A2A4A",
}
PROBE_SCHRIFTEN = {"ueberschrift": "Inter", "text": "Montserrat"}

# Das SHA-256 des CSS von vor P2-72 (Stand HEAD a56ec98 = Paket 1.7.0 plus Paket G): `_CSS` der drei Module.
CSS_VON_VORHER = {
    "digest": "0771574f94d58c7d008f3c395db2b5458570cfd16df0db7c777748234e8b5c9d",
    "coach_export": "dbf5370c9fef384d26d446e4582de8b0ac1c1038c864c2b9ee30ec451ab6c978",
    "docs_render": "f3dbee577b0eb7827f6f654c413044a5f4792981d4033deae8cccc9d59aad8d1",
}


# ── Hilfen ────────────────────────────────────────────────────────────────────────────────────
def png(breite=32, farbe=b"\x30\x20\x10"):
    def block(typ, daten):
        return struct.pack(">I", len(daten)) + typ + daten + struct.pack(">I", zlib.crc32(typ + daten))

    bild = zlib.compress((b"\x00" + farbe * breite) * breite)
    return (b"\x89PNG\r\n\x1a\n" + block(b"IHDR", struct.pack(">IIBBBBB", breite, breite, 8, 2, 0, 0, 0))
            + block(b"IDAT", bild) + block(b"IEND", b""))


PROBE_ICON = png(32, b"\xc8\x10\x90")


def icon_base64(daten: bytes) -> str:
    return base64.b64encode(daten).decode("ascii")


def vorgabe_icon() -> bytes:
    return (PROJEKT_DIR / "assets" / "design" / "icon-32.png").read_bytes()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Werkstatt:
    """Der Datenordner eines Tests mit der Überschreibung `design/design.json` (oder ohne sie)."""

    def __init__(self, tmp_path):
        self.daten = tmp_path / "daten"
        self.ordner = self.daten / "design"

    def probe_anlegen(self, farben=None, schriften=None, icon=PROBE_ICON):
        self.ordner.mkdir(parents=True, exist_ok=True)
        (self.ordner / "icon-32.png").write_bytes(icon)
        (self.ordner / "design.json").write_text(json.dumps({
            "format": 1, "name": "Probe", "farben": farben or PROBE_FARBEN,
            "schriften": schriften or PROBE_SCHRIFTEN, "icon": {"32": "icon-32.png"},
        }), encoding="utf-8")


@pytest.fixture()
def werkstatt(session, tmp_path, monkeypatch):
    """Lenkt den Datenordner NUR für das Design um (`app.db.DATA_DIR` ist beim Import gebunden und bleibt),
    schaltet das Profil ab und räumt den Zwischenspeicher davor und danach. `session` zuerst: Die Datenbank
    ist dann schon an den Wegwerf-Ordner der Sitzung gebunden."""
    from pipeline import design, user_profile

    monkeypatch.setenv("BMS_DATA_DIR", str(tmp_path / "daten"))
    monkeypatch.setattr(user_profile, "_PROFIL_MD", tmp_path / "kein_profil.md")    # -> „Bewerber“
    design.zwischenspeicher_leeren()
    yield Werkstatt(tmp_path)
    design.zwischenspeicher_leeren()


@pytest.fixture()
def probe(werkstatt):
    """Das Probe-Design gilt. Es muss sich selbst bestehen: gültig, aus der Überschreibung, ohne Warnung."""
    from pipeline import design

    werkstatt.probe_anlegen()
    d = design.laden()
    assert d.quelle == "ueberschreibung" and d.warnungen == (), d.warnungen
    assert {r: d.farben[r] for r in PROBE_FARBEN} == PROBE_FARBEN
    return d


def ohne_bedeutung(html: str) -> str:
    """Der Text ohne die Stellen, an denen ein fester Wert Bedeutung trägt: inline gesetzte Zustandsfarben
    (`style="…"`), die Pastelle der Änderungs-Tags (`.chg.*`) und das Rot des Absage-Tags (`.tag`)."""
    text = re.sub(r'style="[^"]*"', "", html)
    text = re.sub(r"\.chg\.[a-z]+\{[^}]*\}", "", text)
    return re.sub(r"\.tag\{[^}]*\}", "", text)


def vorgabe_markenwerte_in(text: str) -> list:
    """Welche Markenwerte der Vorgabe stehen im Text? Weiß fehlt absichtlich: Es steht in jeder Ausgabe (Papier,
    Schrift auf Zustandsflächen, Kopfzeile). Dazu die Kanalform von Navy (`rgba(11,31,58,…)`)."""
    gefunden = [f for f in sorted(set(HEUTIGE_FARBEN.values()) - {"#FFFFFF"}) if f.lower() in text.lower()]
    if re.search(r"rgba?\(\s*11\s*,\s*31\s*,\s*58", text):
        gefunden.append("rgba(11,31,58")
    return gefunden


# ── Digest ────────────────────────────────────────────────────────────────────────────────────
def test_digest_css_mit_der_vorgabe_ist_das_css_von_vorher(werkstatt):
    from pipeline import design, digest

    assert sha(digest._css(design.vorgabe())) == CSS_VON_VORHER["digest"]


def test_digest_mit_der_vorgabe_zeigt_die_heutigen_werte(werkstatt, seed):
    from pipeline.digest import build_digest_html

    html = build_digest_html()

    assert "body{font-family:Inter,system-ui,-apple-system,sans-serif;background:#F4F7FB;color:#0B1F3A;" in html
    assert ".kpi{background:#fff;border:1px solid #DCE4EE;" in html
    assert ".kpi.acc .n{color:#00B4D8}" in html
    assert icon_base64(vorgabe_icon()) in html


def test_digest_mit_dem_probe_design(probe, seed):
    from pipeline.digest import build_digest_html

    html = build_digest_html()

    assert f"font-family:Montserrat,system-ui,-apple-system,sans-serif;background:{PROBE_FARBEN['flaeche']};" \
           f"color:{PROBE_FARBEN['text']};" in html
    assert f"h1{{color:{PROBE_FARBEN['marke']};" in html
    assert f".kpi.acc .n{{color:{PROBE_FARBEN['aktion']}}}" in html
    assert f".kpi{{background:{PROBE_FARBEN['karte']};border:1px solid {PROBE_FARBEN['rahmen']};" in html
    assert f"border-bottom:1px solid {PROBE_FARBEN['spur']}" in html
    assert vorgabe_markenwerte_in(ohne_bedeutung(html)) == []
    # Zustandsfarben bleiben (Score 4 aus dem Seed: Fläche der Tabelle, Schrift Navy), das Icon ist das des Designs
    assert "background:#84C83D;color:#0B1F3A" in html
    assert icon_base64(PROBE_ICON) in html and icon_base64(vorgabe_icon()) not in html


def test_digest_liest_das_design_bei_jedem_aufruf(werkstatt, seed):
    """Laufzeit statt Import: Zwischen zwei Aufrufen im selben Prozess ändert sich die Design-Datei."""
    from pipeline.digest import build_digest_html

    vorher = build_digest_html()
    werkstatt.probe_anlegen()
    nachher = build_digest_html()

    assert icon_base64(vorgabe_icon()) in vorher and icon_base64(PROBE_ICON) not in vorher
    assert icon_base64(PROBE_ICON) in nachher and icon_base64(vorgabe_icon()) not in nachher
    assert PROBE_FARBEN["marke"] in nachher and PROBE_FARBEN["marke"] not in vorher


def test_digest_score_5_behaelt_die_weisse_schrift_unter_jedem_design(probe, session, seed):
    """Die benannte Ausnahme (Score 5, weiße Schrift) ist Bedeutung und hängt am Design nicht."""
    from app.models import Job
    from pipeline.digest import build_digest_html

    session.add(Job(company_name=f"Fünf AG {seed['suffix']}", title="Rolle", status="Neu", match_score=5,
                    dedup_key=f"fuenf|{seed['suffix']}", found_date=date.today().isoformat()))
    session.commit()

    assert "background:#18A957;color:#ffffff" in build_digest_html()


# ── Coach-Site ────────────────────────────────────────────────────────────────────────────────
def _coach_fixture(session, tmp_path, monkeypatch):
    """Eine Beworben-Stelle mit Company-Fit-Bericht (mit <head>, ohne Icon), eine Absage und eine Stelle in Prüfung."""
    from app.db import DATA_DIR
    from app.models import Application, Company, Job
    from pipeline import coach_export

    monkeypatch.setattr(coach_export, "_EXPORT_DIR", tmp_path / "coach_site")
    (DATA_DIR / "company_fit").mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex[:8]
    fit = DATA_DIR / "company_fit" / f"2026_10_13_CompanyFit_Ausgaben_{suffix}.html"
    fit.write_text("<html><head><title>CompanyFit</title></head><body>Inhalt</body></html>", encoding="utf-8")
    comp = Company(name=f"Ausgaben AG {suffix}", fit_analysis_path=f"data/company_fit/{fit.name}")
    session.add(comp)
    session.commit()
    session.refresh(comp)
    jobs = {}
    for status, score in (("Beworben", 5), ("Absage", 1), ("Prüfen", 3)):
        jobs[status] = Job(company_id=comp.id if status == "Beworben" else None,
                           company_name=f"Ausgaben {status} {suffix}", title="Rolle", status=status,
                           match_score=score, found_date=date.today().isoformat(),
                           dedup_key=f"ausgaben|{status}|{suffix}", url=f"https://example.invalid/{status}-{suffix}")
        session.add(jobs[status])
    session.commit()
    session.refresh(jobs["Absage"])
    session.add(Application(job_id=jobs["Absage"].id, channel="Portal", rejection_reason="Intern besetzt"))
    session.commit()
    return coach_export, fit


def _coach_texte(ordner: Path) -> dict:
    return {p.relative_to(ordner).as_posix(): p.read_text(encoding="utf-8")
            for p in ordner.rglob("*.html")}


def test_coach_css_mit_der_vorgabe_ist_das_css_von_vorher(werkstatt):
    from pipeline import coach_export, design

    assert sha(coach_export._css(design.vorgabe())) == CSS_VON_VORHER["coach_export"]


def test_coach_site_mit_der_vorgabe_zeigt_die_heutigen_werte(werkstatt, session, tmp_path, monkeypatch):
    coach_export, fit = _coach_fixture(session, tmp_path, monkeypatch)

    coach_export.export()
    texte = _coach_texte(tmp_path / "coach_site")

    for name in ("index.html", "stellen.html", "absagen.html"):
        assert "nav a.aktiv{background:#00B4D8;border-color:#00B4D8;color:#fff}" in texte[name], name
        assert "background:#F4F7FB;color:#0B1F3A;margin:0;padding:24px" in texte[name], name
        assert icon_base64(vorgabe_icon()) in texte[name], name
    assert icon_base64(vorgabe_icon()) in texte[f"artefakte/{fit.name}"]


def test_coach_site_mit_dem_probe_design(probe, session, tmp_path, monkeypatch):
    coach_export, fit = _coach_fixture(session, tmp_path, monkeypatch)

    coach_export.export()
    texte = _coach_texte(tmp_path / "coach_site")

    for name in ("index.html", "stellen.html", "absagen.html"):
        html = texte[name]
        assert f"nav a.aktiv{{background:{PROBE_FARBEN['aktion']};border-color:{PROBE_FARBEN['aktion']};" \
               f"color:{PROBE_FARBEN['auf_aktion']}}}" in html, name
        assert f"font-family:Montserrat,system-ui,-apple-system,sans-serif;" \
               f"background:{PROBE_FARBEN['flaeche']};color:{PROBE_FARBEN['text']}" in html, name
        assert f".balken{{flex:1;background:{PROBE_FARBEN['spur']}" in html, name
        assert vorgabe_markenwerte_in(ohne_bedeutung(html)) == [], name
        assert icon_base64(PROBE_ICON) in html and icon_base64(vorgabe_icon()) not in html, name
    # Zustandsfarben bleiben: Status-Pille „Beworben“ cyan mit Navy-Schrift, trotz Orange als Aktionsfarbe
    assert 'class="status" style="background:#00B4D8;color:#0B1F3A">Beworben' in texte["stellen.html"]
    # das kopierte Berichtsdokument trägt das Icon des Designs, das gilt
    bericht = texte[f"artefakte/{fit.name}"]
    assert bericht.count("data:image/png;base64,") == 1 and icon_base64(PROBE_ICON) in bericht


def test_coach_site_liest_das_design_bei_jedem_export(werkstatt, session, tmp_path, monkeypatch):
    coach_export, _fit = _coach_fixture(session, tmp_path, monkeypatch)

    coach_export.export()
    vorher = (tmp_path / "coach_site" / "index.html").read_text(encoding="utf-8")
    werkstatt.probe_anlegen()
    coach_export.export()
    nachher = (tmp_path / "coach_site" / "index.html").read_text(encoding="utf-8")

    assert icon_base64(vorgabe_icon()) in vorher and icon_base64(PROBE_ICON) not in vorher
    assert icon_base64(PROBE_ICON) in nachher and PROBE_FARBEN["aktion"] in nachher


# ── Doku-Seiten und Doku-Ansicht ──────────────────────────────────────────────────────────────
DOKU_TEXT = ("# Titel der Beispielseite\n\nEinleitung mit `code` und einem [Verweis](ANLEITUNG.html).\n\n"
             "> Hinweis in einer Box mit `code`.\n\n## Abschnitt\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n"
             "```\nCodeblock\n```\n")


def test_docs_css_mit_der_vorgabe_ist_das_css_von_vorher(werkstatt):
    from pipeline import design, docs_render

    assert sha(docs_render._css(design.vorgabe())) == CSS_VON_VORHER["docs_render"]


def test_die_mitgelieferten_docs_bleiben_unter_jedem_design_gleich(probe):
    """Unter dem Probe-Design: Die eingecheckten docs/*.html entsprechen weiter dem, was der Renderer erzeugt,
    und ein Aufruf ohne Design nimmt die Vorgabe (Farben UND Icon)."""
    from pipeline import design, docs_render

    md_dateien = sorted(docs_render._DOCS_DIR.glob("*.md"))
    assert md_dateien, "keine docs/*.md gefunden"
    assert docs_render.pruefen(md_dateien) == []

    html = docs_render.render_markdown(DOKU_TEXT, "BEISPIEL.md")

    assert html == docs_render.render_markdown(DOKU_TEXT, "BEISPIEL.md", design.vorgabe())
    assert icon_base64(vorgabe_icon()) in html and icon_base64(PROBE_ICON) not in html
    assert "--ink:#0B1F3A;" in html and PROBE_FARBEN["marke"] not in html


def test_doku_ansicht_mit_der_vorgabe_ist_die_mitgelieferte_seite(werkstatt, tmp_path):
    """Ohne Überschreibung ist die Doku-Ansicht dieselbe Seite wie die mitgelieferte."""
    from app import doku
    from pipeline import docs_render

    wurzel = tmp_path / "wurzel"
    (wurzel / "docs").mkdir(parents=True)
    (wurzel / "docs" / "ANLEITUNG.md").write_text(DOKU_TEXT, encoding="utf-8")
    eintrag = doku.eintrag_fuer("anleitung", projekt_root=wurzel)

    assert doku.rendern(eintrag, projekt_root=wurzel) == docs_render.render_markdown(DOKU_TEXT, "ANLEITUNG.md")


def test_doku_ansicht_mit_dem_probe_design(probe, tmp_path):
    from app import doku

    wurzel = tmp_path / "wurzel"
    (wurzel / "docs").mkdir(parents=True)
    (wurzel / "docs" / "ANLEITUNG.md").write_text(DOKU_TEXT, encoding="utf-8")
    eintrag = doku.eintrag_fuer("anleitung", projekt_root=wurzel)

    html = doku.rendern(eintrag, projekt_root=wurzel)

    assert f"--ink:{PROBE_FARBEN['text']};" in html and f"--paper:{PROBE_FARBEN['flaeche']};" in html
    assert f"--card:{PROBE_FARBEN['karte']};" in html and f"--line:{PROBE_FARBEN['rahmen']};" in html
    assert f"--muted:{PROBE_FARBEN['text_gedaempft']};" in html and f"--accent:{PROBE_FARBEN['aktion']};" in html
    assert f"color:{PROBE_FARBEN['stahl']};max-width:65ch" in html
    # --ink trägt in der Vorgabe Text UND Marke: Weicht die Marke ab, setzt eine Zusatzregel die Kopffläche
    assert html.count(f"header.head{{background:{PROBE_FARBEN['marke']}}}") == 1
    assert vorgabe_markenwerte_in(html) == []
    assert icon_base64(PROBE_ICON) in html and icon_base64(vorgabe_icon()) not in html


def test_doku_ansicht_ohne_abweichende_marke_hat_keine_zusatzregel(werkstatt):
    """Gleicht die Marke dem Text (wie in der Vorgabe), bleibt das CSS unverändert: keine Zusatzregel."""
    from pipeline import design, docs_render

    css = docs_render._css(design.vorgabe())

    assert "header.head{background:#" not in css


def test_doku_ansicht_liest_das_design_bei_jedem_aufruf(werkstatt, tmp_path):
    from app import doku

    wurzel = tmp_path / "wurzel"
    (wurzel / "docs").mkdir(parents=True)
    (wurzel / "docs" / "ANLEITUNG.md").write_text(DOKU_TEXT, encoding="utf-8")
    eintrag = doku.eintrag_fuer("anleitung", projekt_root=wurzel)

    vorher = doku.rendern(eintrag, projekt_root=wurzel)
    werkstatt.probe_anlegen()
    nachher = doku.rendern(eintrag, projekt_root=wurzel)

    assert icon_base64(vorgabe_icon()) in vorher and icon_base64(PROBE_ICON) in nachher
    assert PROBE_FARBEN["aktion"] in nachher and PROBE_FARBEN["aktion"] not in vorher


# ── Excel ─────────────────────────────────────────────────────────────────────────────────────
def _rgb(farbe) -> str:
    """Die sechs Stellen einer openpyxl-Farbe (`00RRGGBB`), GROSS; leer bei Theme- und Indexfarben."""
    if farbe is None or farbe.type != "rgb" or not isinstance(farbe.rgb, str):
        return ""
    return farbe.rgb[-6:].upper()


def _excel(tmp_path, monkeypatch):
    import openpyxl
    from pipeline import export_excel

    monkeypatch.setattr(export_excel, "EXPORT_DIR", tmp_path / "excel")
    return openpyxl.load_workbook(export_excel.build_workbook())


def test_excel_mit_der_vorgabe_zeigt_die_heutigen_werte(werkstatt, seed, tmp_path, monkeypatch):
    wb = _excel(tmp_path, monkeypatch)

    kopf = wb["Stellen"]["A1"]
    assert _rgb(kopf.fill.fgColor) == "0B1F3A" and _rgb(kopf.font.color) == "FFFFFF"
    assert _rgb(wb["Dashboard"]["A1"].font.color) == "0B1F3A"          # Titel
    assert _rgb(wb["Dashboard"]["A5"].font.color) == "0B1F3A"          # Kennzahl (KPI_FONT)
    assert _rgb(wb["Funnel"]["A4"].font.color) == "0B1F3A"             # Zelltext


def test_excel_mit_dem_probe_design(probe, seed, tmp_path, monkeypatch):
    from pipeline import zustandsfarben as zf

    wb = _excel(tmp_path, monkeypatch)
    marke, text = PROBE_FARBEN["marke"].lstrip("#"), PROBE_FARBEN["text"].lstrip("#")

    for blatt in ("Stellen", "Aussortiert", "Kontakte", "Netzwerk", "Headhunter", "Zielfirmen", "Outreach", "Referenzen"):
        zelle = wb[blatt]["A1"]
        assert _rgb(zelle.fill.fgColor) == marke, blatt                # Kopfzeile = Markenfläche
    assert _rgb(wb["Funnel"]["A3"].fill.fgColor) == marke              # Kopf der Funnel-Tabelle
    assert _rgb(wb["Dashboard"]["A1"].font.color) == marke             # Titel
    assert _rgb(wb["Dashboard"]["A5"].font.color) == marke             # Kennzahl
    assert _rgb(wb["Dashboard"]["A10"].font.color) == marke            # Abschnittsüberschrift
    assert _rgb(wb["Funnel"]["A4"].font.color) == text                 # Zelltext = Textfarbe

    # Kein Markenwert der Vorgabe mehr, außer in Zellen mit einer Zustandsfläche (dort ist Navy die Schrift)
    # und der ersten Trichterstufe (Bedeutung: Start, Fläche Navy).
    zustandsflaechen = ({zf.ohne_raute(f) for f, _ in zf.STATUS_FARBEN.values()}
                        | {zf.ohne_raute(f) for f, _ in zf.SCORE_FARBEN.values()}
                        | {zf.ohne_raute(zf.TRICHTER_START[0])})
    leck = []
    for ws in wb:
        for zeile in ws.iter_rows():
            for z in zeile:
                fl = _rgb(z.fill.fgColor) if z.fill.patternType == "solid" else ""
                if fl in zustandsflaechen:
                    continue
                for was, wert in (("Schrift", _rgb(z.font.color)), ("Fläche", fl)):
                    if wert in {f.lstrip("#") for f in HEUTIGE_FARBEN.values()} - {"FFFFFF"}:
                        leck.append((ws.title, z.coordinate, was, wert))
    assert leck == []
    # Zustandsfarben bleiben: eine Zelle mit der Fläche von „Beworben“ gibt es weiter (Seed: eine Beworben-Stelle)
    assert any(_rgb(z.fill.fgColor) == "00B4D8" for zeile in wb["Stellen"].iter_rows() for z in zeile)


def test_excel_liest_das_design_bei_jedem_export(werkstatt, seed, tmp_path, monkeypatch):
    vorher = _excel(tmp_path, monkeypatch)
    werkstatt.probe_anlegen()
    nachher = _excel(tmp_path, monkeypatch)

    assert _rgb(vorher["Stellen"]["A1"].fill.fgColor) == "0B1F3A"
    assert _rgb(nachher["Stellen"]["A1"].fill.fgColor) == PROBE_FARBEN["marke"].lstrip("#")


def test_excel_zustandsfarben_sind_die_tabelle(werkstatt, seed, tmp_path, monkeypatch):
    """Score-4-Zelle des Seeds (Fit-Spalte der Beworben-Stelle): Fläche und Schrift aus der Tabelle."""
    from pipeline import zustandsfarben as zf

    wb = _excel(tmp_path, monkeypatch)
    ws = wb["Stellen"]
    flaeche, schrift = (zf.ohne_raute(w) for w in zf.SCORE_FARBEN[4])

    assert any(_rgb(z.fill.fgColor) == flaeche and _rgb(z.font.color) == schrift
               for zeile in ws.iter_rows(min_col=3, max_col=3) for z in zeile)


# ── Wächter: nichts wird beim Import festgehalten ─────────────────────────────────────────────
AUSGABEN = ("digest.py", "coach_export.py", "docs_render.py", "export_excel.py")
_DESIGN_NAMEN = {"favicon", "design", "design_modul", "_design"}


def beim_import_festgehalten(quelltext: str) -> list:
    """Funde: Wer das Design oder das Icon beim Import in eine Modulkonstante bindet, sieht eine geänderte
    Design-Datei erst nach einem Neustart. Gesucht wird auf Modulebene (ohne Funktionen und Klassen) nach einem
    AUFRUF von `favicon.…()` oder `design.…()`, und überall nach `FAVICON_LINK`, dem beim Import gebundenen
    Namen. Eine Funktion zu binden (`_mit_favicon = favicon.mit_favicon`) ist kein Aufruf und bleibt erlaubt."""
    baum = ast.parse(quelltext)
    funde = []
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Name) and knoten.id == "FAVICON_LINK":
            funde.append(f"FAVICON_LINK (Zeile {knoten.lineno})")
        elif isinstance(knoten, ast.Attribute) and knoten.attr == "FAVICON_LINK":
            funde.append(f"….FAVICON_LINK (Zeile {knoten.lineno})")
        elif isinstance(knoten, ast.ImportFrom) and any(a.name == "FAVICON_LINK" for a in knoten.names):
            funde.append(f"Import von FAVICON_LINK (Zeile {knoten.lineno})")
    for knoten in baum.body:
        if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)):
            continue
        if isinstance(knoten, ast.If):       # `if __name__ == "__main__":` läuft nicht beim Import
            continue
        for k in ast.walk(knoten):
            if (isinstance(k, ast.Call) and isinstance(k.func, ast.Attribute)
                    and isinstance(k.func.value, ast.Name) and k.func.value.id in _DESIGN_NAMEN):
                funde.append(f"Aufruf {k.func.value.id}.{k.func.attr}() auf Modulebene (Zeile {k.lineno})")
    return funde


@pytest.mark.parametrize("modul", AUSGABEN)
def test_kein_modul_haelt_design_oder_icon_beim_import_fest(modul):
    assert beim_import_festgehalten((BACKEND_DIR / "pipeline" / modul).read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("modul", AUSGABEN)
def test_kein_modul_liest_das_icon_mehr_aus_frontend_public(modul):
    baum = ast.parse((BACKEND_DIR / "pipeline" / modul).read_text(encoding="utf-8"))
    konstanten = {k.value for k in ast.walk(baum) if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    assert "favicon-32.png" not in konstanten and "public" not in konstanten


def test_waechter_schlaegt_bei_einer_beim_import_gebundenen_konstante_an():
    assert beim_import_festgehalten("from app import favicon\n_FAVICON_LINK = favicon.favicon_link()\n")
    assert beim_import_festgehalten("from pipeline import design\n_DESIGN = design.laden()\n")
    assert beim_import_festgehalten("from app.favicon import FAVICON_LINK as _FAVICON\n")
    assert beim_import_festgehalten("from app import favicon\nX = favicon.FAVICON_LINK\n")


def test_waechter_laesst_laufzeit_aufrufe_und_funktionsbindung_durch():
    quelle = ("from app import favicon\nfrom pipeline import design\n"
              "_mit_favicon = favicon.mit_favicon\n"
              "def f():\n    return favicon.favicon_link(design.laden())\n"
              "if __name__ == '__main__':\n    print(design.laden())\n")
    assert beim_import_festgehalten(quelle) == []
