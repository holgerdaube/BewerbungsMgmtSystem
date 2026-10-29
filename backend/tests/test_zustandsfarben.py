"""P2-72 (Vertrag R) — Die Zustandsfarben in Python: `pipeline/zustandsfarben.py`.

Status, Score und die Schrift darauf tragen Bedeutung, nicht Marke (Leitentscheidung 2). Sie standen vorher
in `frontend/src/components/ui.tsx` und dazu viermal in Python, in drei Schreibweisen. Diese Datei hält
fest:

  1. Die Tabelle in Python ist die in `ui.tsx` (`STATUS_FARBEN`, `STATUS_FARBE_UNBEKANNT`, `SCORE_COLORS`,
     `SCORE_TEXT`, `SCORE_NONE` und `TEXT_AUF_ZUSTAND`, auf das dort verwiesen wird), Wert für Wert und in
     derselben Schreibweise. Die erste Trichterstufe ist die aus `Dashboard.tsx`.
  2. Die kleinen Funktionen: Rückfall für unbekannte Status und Scores, Form ohne Raute für Excel.
  3. WÄCHTER: In `digest.py`, `coach_export.py`, `docs_render.py` und `export_excel.py` steht keine eigene
     Status- oder Score-Tabelle mehr und kein Zustandsfarbwert als Literal. Was dort bewusst fest steht,
     nennt die Positivliste unten mit einem Satz Begründung; die benannte Ausnahme (Score 5 in Digest und
     Coach-Site) steht in einer eigenen Liste. Der Wächter ist selbst geprüft (`test_waechter_*`): Er schlägt
     an, wenn jemand eine Kopie zurückbaut.

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py); `pipeline.zustandsfarben` selbst braucht keine App.
"""
import ast
import re
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJEKT_DIR = BACKEND_DIR.parent
UI_TSX = PROJEKT_DIR / "frontend" / "src" / "components" / "ui.tsx"
DASHBOARD_TSX = PROJEKT_DIR / "frontend" / "src" / "pages" / "Dashboard.tsx"

HEX = r"#[0-9A-Fa-f]{6}"


# ── ui.tsx lesen ──────────────────────────────────────────────────────────────────────────────
def _tsx_wert(token: str, text_auf_zustand: str) -> str:
    token = token.strip()
    if token == "TEXT_AUF_ZUSTAND":
        return text_auf_zustand
    treffer = re.fullmatch(rf"'({HEX})'", token)
    assert treffer, f"unerwarteter Wert in ui.tsx: {token!r}"
    return treffer.group(1)


def _block(text: str, anfang: str) -> str:
    """Der Rumpf des Objektliterals, das nach `anfang` beginnt (bis zur schließenden Klammer)."""
    start = text.index(anfang)
    start = text.index("{", text.index("=", start))
    tiefe = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            tiefe += 1
        elif text[i] == "}":
            tiefe -= 1
            if tiefe == 0:
                return text[start + 1:i]
    raise AssertionError(f"Literal nach {anfang!r} nicht geschlossen")


def tsx_tabellen() -> dict:
    text = UI_TSX.read_text(encoding="utf-8")
    m = re.search(rf"export const TEXT_AUF_ZUSTAND\s*=\s*'({HEX})'", text)
    assert m, "ui.tsx nennt TEXT_AUF_ZUSTAND nicht (export const TEXT_AUF_ZUSTAND = '#…')"
    taz = m.group(1)

    t = {"text_auf_zustand": taz}
    t["score_flaeche"] = {int(k): _tsx_wert(v, taz) for k, v in
                          re.findall(r"(\d):\s*('#[0-9A-Fa-f]{6}'|TEXT_AUF_ZUSTAND)",
                                     _block(text, "export const SCORE_COLORS"))}
    t["score_schrift"] = {int(k): _tsx_wert(v, taz) for k, v in
                          re.findall(r"(\d):\s*('#[0-9A-Fa-f]{6}'|TEXT_AUF_ZUSTAND)",
                                     _block(text, "const SCORE_TEXT"))}
    m = re.search(rf"const SCORE_NONE\s*=\s*'({HEX})'", text)
    assert m
    t["score_nichts"] = m.group(1)
    # Schrift auf „nicht bewertet“: die Anzeige des leeren Scores in ScoreBadge
    m = re.search(r"backgroundColor:\s*SCORE_NONE,\s*color:\s*('#[0-9A-Fa-f]{6}'|TEXT_AUF_ZUSTAND)", text)
    assert m, "ScoreBadge: Anzeige ohne Score nicht gefunden"
    t["score_nichts_schrift"] = _tsx_wert(m.group(1), taz)

    status = {}
    for zeile in _block(text, "export const STATUS_FARBEN").splitlines():
        m = re.match(rf"\s*(?:'([^']+)'|(\w+)):\s*\{{\s*bg:\s*'({HEX})',\s*text:\s*('{HEX}'|TEXT_AUF_ZUSTAND)\s*\}}",
                     zeile)
        if m:
            status[m.group(1) or m.group(2)] = (m.group(3), _tsx_wert(m.group(4), taz))
    t["status"] = status
    m = re.search(rf"export const STATUS_FARBE_UNBEKANNT\s*=\s*\{{\s*bg:\s*'({HEX})',\s*text:\s*('{HEX}'|TEXT_AUF_ZUSTAND)",
                  text)
    assert m
    t["status_unbekannt"] = (m.group(1), _tsx_wert(m.group(2), taz))
    return t


def tsx_trichter_start() -> tuple:
    text = DASHBOARD_TSX.read_text(encoding="utf-8")
    m = re.search(rf"const FUNNEL_FARBEN[^=]*=\s*\[\s*\{{\s*bg:\s*'({HEX})',\s*text:\s*'({HEX})'", text)
    assert m, "Dashboard.tsx: erste Stufe von FUNNEL_FARBEN nicht gefunden"
    return m.group(1), m.group(2)


# ── 1. Die Tabelle gleicht ui.tsx ─────────────────────────────────────────────────────────────
def test_der_leser_findet_alle_tabellen_in_ui_tsx():
    """Wächter des Wächters: Ein Leser, der still nichts findet, würde jeden Vergleich bestehen lassen."""
    t = tsx_tabellen()
    assert len(t["status"]) == 11
    assert sorted(t["score_flaeche"]) == [1, 2, 3, 4, 5] and sorted(t["score_schrift"]) == [1, 2, 3, 4, 5]
    assert t["text_auf_zustand"] == "#0B1F3A"


def test_status_farben_sind_die_aus_ui_tsx():
    from pipeline import zustandsfarben as zf

    assert dict(zf.STATUS_FARBEN) == tsx_tabellen()["status"]


def test_status_rueckfall_ist_der_aus_ui_tsx():
    from pipeline import zustandsfarben as zf

    assert zf.STATUS_FARBE_UNBEKANNT == tsx_tabellen()["status_unbekannt"]


def test_score_farben_sind_die_aus_ui_tsx():
    from pipeline import zustandsfarben as zf

    t = tsx_tabellen()
    assert {s: f for s, (f, _) in zf.SCORE_FARBEN.items()} == t["score_flaeche"]
    assert {s: x for s, (_, x) in zf.SCORE_FARBEN.items()} == t["score_schrift"]


def test_nicht_bewertet_ist_das_aus_ui_tsx():
    from pipeline import zustandsfarben as zf

    t = tsx_tabellen()
    assert zf.SCORE_NICHT_BEWERTET == (t["score_nichts"], t["score_nichts_schrift"])


def test_text_auf_zustand_ist_der_aus_ui_tsx():
    from pipeline import zustandsfarben as zf

    assert zf.TEXT_AUF_ZUSTAND == tsx_tabellen()["text_auf_zustand"]


def test_erste_trichterstufe_ist_die_aus_dashboard_tsx():
    from pipeline import zustandsfarben as zf

    assert zf.TRICHTER_START == tsx_trichter_start()


def test_eine_schreibweise_rrggbb():
    from pipeline import zustandsfarben as zf

    paare = (list(zf.STATUS_FARBEN.values()) + list(zf.SCORE_FARBEN.values())
             + [zf.STATUS_FARBE_UNBEKANNT, zf.SCORE_NICHT_BEWERTET, zf.TRICHTER_START])
    for flaeche, schrift in paare:
        assert re.fullmatch(HEX, flaeche) and re.fullmatch(HEX, schrift), (flaeche, schrift)


def test_die_tabellen_sind_nicht_veraenderbar():
    from pipeline import zustandsfarben as zf

    with pytest.raises(TypeError):
        zf.STATUS_FARBEN["Neu"] = ("#000000", "#ffffff")
    with pytest.raises(TypeError):
        zf.SCORE_FARBEN[1] = ("#000000", "#ffffff")


# ── 2. Die Funktionen ─────────────────────────────────────────────────────────────────────────
def test_unbekannter_oder_leerer_status_bekommt_den_rueckfall():
    from pipeline import zustandsfarben as zf

    for status in (None, "", "Gibt es nicht"):
        assert zf.status_farbe(status) == zf.STATUS_FARBE_UNBEKANNT
    assert zf.status_farbe("Beworben") == zf.STATUS_FARBEN["Beworben"]


def test_leerer_oder_unbekannter_score_heisst_nicht_bewertet():
    from pipeline import zustandsfarben as zf

    for score in (None, 0, 6, -1):
        assert zf.score_farbe(score) == zf.SCORE_NICHT_BEWERTET
    for score in (1, 2, 3, 4, 5):
        assert zf.score_farbe(score) == zf.SCORE_FARBEN[score]


def test_form_ohne_raute_fuer_excel():
    from pipeline import zustandsfarben as zf

    assert zf.ohne_raute("#0B1F3A") == "0B1F3A"
    assert zf.ohne_raute("#ffffff") == "FFFFFF"       # Excel schreibt GROSS
    assert zf.ohne_raute("94a3b8") == "94A3B8"


def test_das_modul_braucht_nur_die_standardbibliothek():
    """Der Excel-Export läuft auch als Kommandozeile und soll dafür weder die App noch die Datenbank laden."""
    quelle = (BACKEND_DIR / "pipeline" / "zustandsfarben.py").read_text(encoding="utf-8")
    importe = [n for n in ast.walk(ast.parse(quelle)) if isinstance(n, (ast.Import, ast.ImportFrom))]
    module = {(n.module if isinstance(n, ast.ImportFrom) else n.names[0].name).split(".")[0] for n in importe}
    assert module <= {"__future__", "types", "typing"}, module


# ── 3. Wächter: keine Kopien in den vier Modulen ──────────────────────────────────────────────
AUSGABEN = ("digest.py", "coach_export.py", "docs_render.py", "export_excel.py")

# Kein Zustandsfarbwert als Literal in den vier Modulen — AUSSER diesen, jeweils mit Begründung. Ein Eintrag
# hier ist eine bewusste Entscheidung; wer einen Wert ergänzt, begründet ihn.
POSITIVLISTE_LITERALE = {
    "digest.py": {
        "94A3B8": "Neutralgrau für Nebentext (.muted, .empty), Slate-400: gehört zu keiner Rolle und ist kein Zustand",
    },
    "coach_export.py": {
        "94A3B8": "Neutralgrau für Nebentext (.muted), Slate-400: gehört zu keiner Rolle und ist kein Zustand",
    },
    "docs_render.py": {
        "E4A11B": "Amber der Hinweisbox (--amber): Bedeutung „Achtung“, nicht der Status Geparkt",
    },
    "export_excel.py": {
        "64748B": "Beschriftung (LABEL_FONT), Slate-500: Neutralgrau ohne Rolle, nicht der Status Kein Match",
        "94A3B8": "Nebentext (SPLIT_FONT, Ende-zu-Ende-Zeile), Slate-400: Neutralgrau ohne Rolle",
    },
}
# Benannte Ausnahmen von der Tabelle: Name der Konstante je Modul. Jede ist im Modul begründet.
POSITIVLISTE_AUSNAHMEN = {
    "digest.py": {"SCORE_SCHRIFT_AUSNAHME"},     # Score 5: weiße Schrift in Digest und Coach-Site (wie bisher)
}

_HEX_IM_TEXT = re.compile(r"(?<![0-9A-Fa-f])#?([0-9A-Fa-f]{6})(?![0-9A-Fa-f])")


def _zustandswerte() -> set:
    """Alle Flächen der Zustandsfarben (GROSS, ohne Raute), dazu Navy, die Schrift auf ihnen. Weiß fehlt
    absichtlich: Es steht in jeder Ausgabe an vielen Stellen, auch als Papier und als Kartenfarbe."""
    from pipeline import zustandsfarben as zf

    werte = {f for f, _ in zf.STATUS_FARBEN.values()} | {f for f, _ in zf.SCORE_FARBEN.values()}
    werte |= {zf.STATUS_FARBE_UNBEKANNT[0], zf.SCORE_NICHT_BEWERTET[0], zf.TRICHTER_START[0],
              zf.TEXT_AUF_ZUSTAND}
    return {zf.ohne_raute(w) for w in werte}


def _ohne_docstrings(baum: ast.AST) -> list:
    """Alle Knoten außer den Docstrings (Moduldoc, Funktions- und Klassendoc): Dort stehen Erklärungen."""
    doc_knoten = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if (knoten.body and isinstance(knoten.body[0], ast.Expr)
                    and isinstance(knoten.body[0].value, ast.Constant)
                    and isinstance(knoten.body[0].value.value, str)):
                doc_knoten.add(id(knoten.body[0].value))
    return [k for k in ast.walk(baum) if id(k) not in doc_knoten]


def zustandskopien(quelltext: str, modul: str) -> list:
    """Funde in einem Quelltext: Zustandsfarbwerte als Literal (außer der Positivliste des Moduls) und
    Tabellen-Literale (Dict, Liste, Tupel, Menge mit Farbwerten) unter einem Namen außerhalb der
    Positivliste der Ausnahmen."""
    erlaubt = set(POSITIVLISTE_LITERALE.get(modul, {}))
    ausnahmen = POSITIVLISTE_AUSNAHMEN.get(modul, set())
    zustand = _zustandswerte()
    baum = ast.parse(quelltext)
    funde = []
    for knoten in _ohne_docstrings(baum):
        if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str):
            for treffer in _HEX_IM_TEXT.findall(knoten.value):
                wert = treffer.upper()
                if wert in zustand and wert not in erlaubt:
                    funde.append(f"{modul}: Zustandsfarbe {wert} als Literal (Zeile {knoten.lineno})")
    for knoten in baum.body:        # Tabellen auf Modulebene, unter welchem Namen auch immer
        if isinstance(knoten, ast.Assign) and isinstance(knoten.value, (ast.Dict, ast.List, ast.Tuple, ast.Set)):
            farben = [k for k in ast.walk(knoten.value) if isinstance(k, ast.Constant)
                      and isinstance(k.value, str) and re.fullmatch(r"#?[0-9A-Fa-f]{6}", k.value)]
            namen = {t.id for t in knoten.targets if isinstance(t, ast.Name)}
            if farben and not namen <= ausnahmen:
                funde.append(f"{modul}: Farbtabelle {sorted(namen)} (Zeile {knoten.lineno})")
    return funde


@pytest.mark.parametrize("modul", AUSGABEN)
def test_keine_eigene_status_oder_score_tabelle_in_den_ausgaben(modul):
    quelltext = (BACKEND_DIR / "pipeline" / modul).read_text(encoding="utf-8")

    assert zustandskopien(quelltext, modul) == []


@pytest.mark.parametrize("modul", AUSGABEN)
def test_die_positivliste_der_literale_ist_nicht_veraltet(modul):
    """Jeder Eintrag der Positivliste steht wirklich noch im Modul: Sonst bliebe eine Erlaubnis ohne Anlass."""
    baum = ast.parse((BACKEND_DIR / "pipeline" / modul).read_text(encoding="utf-8"))
    werte = {t.upper() for k in _ohne_docstrings(baum) if isinstance(k, ast.Constant) and isinstance(k.value, str)
             for t in _HEX_IM_TEXT.findall(k.value)}
    for wert in POSITIVLISTE_LITERALE.get(modul, {}):
        assert wert in werte, f"{modul}: {wert} steht nicht mehr im Modul, Eintrag aus der Positivliste streichen"
    for name in POSITIVLISTE_AUSNAHMEN.get(modul, set()):
        assert any(isinstance(k, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in k.targets)
                   for k in baum.body), f"{modul}: Ausnahme {name} gibt es nicht mehr"


def test_der_beirat_nimmt_die_fuellfarbe_der_score_balken_aus_der_tabelle(monkeypatch):
    """`beirat_engine` trug die Skala als weitere Kopie (`_SCORE_FARBE`). Jetzt entscheidet die Tabelle:
    Mit der echten Tabelle steht je Stufe ihr Wert im Balken, mit einer ausgetauschten der neue."""
    import beirat_engine
    from pipeline import zustandsfarben

    assert not hasattr(beirat_engine, "_SCORE_FARBE")
    bereich = beirat_engine.ABSTIMMUNGS_BEREICHE[0]
    for wert, stufe in ((0.0, 1), (2.0, 2), (3.4, 3), (4.0, 4), (9.0, 5)):
        html = beirat_engine._score_balken_html({bereich: wert})
        erste_zeile = html.splitlines()[0]
        assert f"background:{zustandsfarben.SCORE_FARBEN[stufe][0]}" in erste_zeile, (wert, erste_zeile)

    probe = {stufe: ("#12AB%02d" % stufe, "#000000") for stufe in range(1, 6)}
    monkeypatch.setattr(zustandsfarben, "SCORE_FARBEN", probe)
    html = beirat_engine._score_balken_html({bereich: 9.0})
    assert "background:#12AB05" in html.splitlines()[0]


def test_die_benannte_ausnahme_ist_genau_score_5_weiss():
    """Die einzige Abweichung der Ausgaben von ui.tsx (Digest und Coach-Site, Score 5) ist benannt, begrenzt
    und wirkt in beiden Ausgaben gleich."""
    from pipeline import digest, zustandsfarben as zf

    assert digest.SCORE_SCHRIFT_AUSNAHME == {5: "#ffffff"}
    assert digest.score_farben(5) == (zf.SCORE_FARBEN[5][0], "#ffffff")
    assert digest.score_farben(5)[1] != zf.SCORE_FARBEN[5][1], "die Ausnahme weicht von der Tabelle ab"
    for score in (1, 2, 3, 4):
        assert digest.score_farben(score) == zf.SCORE_FARBEN[score]
    assert digest.score_farben(None) == zf.SCORE_NICHT_BEWERTET


def test_digest_und_coach_site_zeigen_dieselben_score_badges():
    from pipeline import coach_export, digest

    for score in (1, 2, 3, 4, 5, 6):
        flaeche, schrift = digest.score_farben(score)
        assert f"background:{flaeche};color:{schrift}" in coach_export._score_badge(score)
    assert "–" in coach_export._score_badge(None)


# ── Der Wächter ist selbst geprüft ────────────────────────────────────────────────────────────
def test_waechter_schlaegt_bei_einer_zurueckgebauten_tabelle_an():
    kopie = ('_STATUS_FARBEN = {"Neu": ("#94A3B8", "#0B1F3A"), "Prüfen": ("#5B61E6", "#ffffff")}\n'
             '_SCORE = {5: "#18A957", 4: "#84C83D"}\n')

    funde = zustandskopien(kopie, "coach_export.py")

    assert any("Farbtabelle" in f and "_STATUS_FARBEN" in f for f in funde)
    assert any("Farbtabelle" in f and "_SCORE" in f for f in funde)
    assert any("5B61E6" in f for f in funde) and any("18A957" in f for f in funde)


def test_waechter_schlaegt_bei_einem_einzelnen_wert_an():
    assert zustandskopien('def f():\n    return "background:#00B4D8"\n', "digest.py")
    assert zustandskopien('X = "0B1F3A"\n', "export_excel.py")       # Navy in Excel-Schreibweise
    assert zustandskopien('Y = "#e5484d"\n', "digest.py")           # kleingeschrieben


def test_waechter_laesst_die_positivliste_und_docstrings_durch():
    assert zustandskopien('X = ".muted{color:#94A3B8}"\n', "digest.py") == []
    assert zustandskopien('"""Erklärung mit #00B4D8 und #18A957"""\nX = 1\n', "digest.py") == []
    assert zustandskopien('SCORE_SCHRIFT_AUSNAHME = {5: "#ffffff"}\n', "digest.py") == []
    assert zustandskopien('SCORE_SCHRIFT_AUSNAHME = {5: "#ffffff"}\n', "coach_export.py") != []   # nur im Digest erlaubt


def test_waechter_prueft_auch_fremde_namen():
    assert zustandskopien('FARBEN = ["#123456", "#654321"]\n', "digest.py")
