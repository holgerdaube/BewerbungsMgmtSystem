"""Wächter P2-82 (Vertrag L): Das BMS läuft ohne Lizenzdatei mit vollem Funktionsumfang.

Das Programm steht unter Apache-2.0 und wird nicht mehr verkauft. Bis 1.7.0 sperrten eine Middleware
(402), der Schreibschutz in `app/db.py`, der Runner, die Beirat-Engine und die Kommandozeile ohne
gültige Lizenzdatei. Dieser Wächter hält fest, dass davon nichts zurückkommt:

  1. Es gibt kein Modul `pipeline/lizenz.py` und keine Route `app/routes_lizenz.py` mehr, und kein
     ausgeliefertes Python-Modul (Backend ohne `tests/`, `scripts/`) importiert `pipeline.lizenz`.
  2. Keine Datei unter `backend/`, `frontend/src/`, `scripts/` und `.claude/` enthält die Namen der
     alten Sperre oder des Kaufwegs (Liste `VERBOTEN` unten). Ausgenommen ist diese Datei selbst.
  3. Eine schreibende Route antwortet ohne Lizenzdatei mit 200 (nicht 402), die App kennt keine
     Lizenz-Route und keine Lizenz-Middleware mehr.

Die Prüfung der Dateien ist ein Textvergleich über den Arbeitsbaum, ohne Git. Das Verzeichnis
`.claude/worktrees/` (lokale Arbeitskopien, nicht im Repository) und erzeugte Ordner werden
übersprungen. Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention).
"""
import ast
import os
import re
from pathlib import Path

import pytest

PROJEKT = Path(__file__).resolve().parents[2]
DIESE_DATEI = Path(__file__).resolve()

# Verbotene Namen (Wortgrenzen, damit z. B. `test_cli_pruefen_exit_codes` in test_docs_html.py nicht
# anschlägt: dort heißt „pruefen“ etwas anderes). Die Namen der Sperre, der Prüfschlüssel, der Kauf-
# Adresse der Oberfläche und die Adresse des früheren Paketdienstes.
VERBOTEN = (
    ("cli_pruefen", re.compile(r"(?<!\w)cli_pruefen(?!\w)")),
    ("berechtigt()", re.compile(r"(?<!\w)berechtigt\(\)")),
    ("PRUEFSCHLUESSEL", re.compile(r"(?<!\w)PRUEFSCHLUESSEL(?!\w)")),
    ("bms.daube.tech", re.compile(re.escape("bms.daube.tech"), re.IGNORECASE)),
    ("KAUF_URL", re.compile(r"(?<!\w)KAUF_URL(?!\w)")),
)

# Wurzeln der Suche (relativ zum Projekt) und Ordnernamen, die nie durchsucht werden.
WURZELN = ("backend", "frontend/src", "scripts", ".claude")
UEBERSPRINGEN = {"__pycache__", "node_modules", "dist", ".git", ".git.nosync", ".pytest_cache",
                 ".venv", "worktrees", ".mypy_cache", ".ruff_cache"}
GROESSE_MAX = 4_000_000          # Bytes; größere Dateien sind keine Quelltexte


def _dateien(wurzeln):
    """Alle Dateien unter den Wurzeln (ohne die übersprungenen Ordner), sortiert."""
    for rel in wurzeln:
        wurzel = PROJEKT / rel
        if not wurzel.is_dir():
            continue
        for ordner, unterordner, namen in os.walk(wurzel):
            unterordner[:] = sorted(u for u in unterordner if u not in UEBERSPRINGEN)
            for name in sorted(namen):
                yield Path(ordner) / name


def _text(pfad: Path):
    """Der Text einer Datei, oder None bei Binärdateien, zu großen Dateien und Lesefehlern."""
    try:
        if pfad.stat().st_size > GROESSE_MAX:
            return None
        roh = pfad.read_bytes()
    except OSError:
        return None
    if b"\0" in roh:
        return None
    return roh.decode("utf-8", errors="replace")


def _rel(pfad: Path) -> str:
    return pfad.relative_to(PROJEKT).as_posix()


# ── 1. Das Modul und seine Importe sind weg ───────────────────────────────────────────────────
def test_lizenzmodul_und_lizenzroute_gibt_es_nicht_mehr():
    assert not (PROJEKT / "backend" / "pipeline" / "lizenz.py").exists()
    assert not (PROJEKT / "backend" / "app" / "routes_lizenz.py").exists()


def _importiert_lizenz(baum: ast.AST) -> list:
    """Die Zeilen, in denen ein `pipeline.lizenz` (oder ein relatives `lizenz`) importiert wird."""
    zeilen = []
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            if any(a.name == "pipeline.lizenz" or a.name.startswith("pipeline.lizenz.")
                   for a in knoten.names):
                zeilen.append(knoten.lineno)
        elif isinstance(knoten, ast.ImportFrom):
            modul = knoten.module or ""
            if modul == "pipeline.lizenz" or modul.startswith("pipeline.lizenz."):
                zeilen.append(knoten.lineno)
            elif modul in ("pipeline", "") and any(a.name == "lizenz" for a in knoten.names):
                zeilen.append(knoten.lineno)
            elif modul == "lizenz" and knoten.level > 0:
                zeilen.append(knoten.lineno)
    return zeilen


def test_kein_ausgeliefertes_modul_importiert_pipeline_lizenz():
    """Backend ohne `tests/` und `scripts/`: weder `import pipeline.lizenz` noch `from pipeline import
    lizenz`, auch nicht als Zeichenkette für `importlib` (`"pipeline.lizenz"`)."""
    treffer = []
    for pfad in _dateien(("backend", "scripts")):
        if pfad.suffix != ".py":
            continue
        rel = _rel(pfad)
        if rel.startswith("backend/tests/"):
            continue
        text = _text(pfad)
        if text is None:
            continue
        if re.search(r"pipeline\.lizenz(?!\w)", text):
            treffer.append(f"{rel}: Verweis auf pipeline.lizenz")
        try:
            baum = ast.parse(text, filename=rel)
        except SyntaxError as exc:                              # pragma: no cover -- Quelltext kaputt
            treffer.append(f"{rel}: nicht lesbar ({exc.msg})")
            continue
        treffer += [f"{rel}:{z}: Import von lizenz" for z in _importiert_lizenz(baum)]
    assert treffer == [], "\n".join(treffer)


def test_der_wachter_erkennt_die_importformen():
    """Sonst prüft der Wächter weniger, als er vorgibt."""
    for quelltext in ("import pipeline.lizenz", "import pipeline.lizenz as l",
                      "from pipeline import lizenz", "from pipeline import ingest, lizenz",
                      "from pipeline.lizenz import berechtigt", "from . import lizenz",
                      "from .lizenz import MELDUNG"):
        assert _importiert_lizenz(ast.parse(quelltext)), quelltext
    for quelltext in ("from pipeline import drittlizenzen", "import pipeline.kundenpaket",
                      "from pipeline import ingest"):
        assert _importiert_lizenz(ast.parse(quelltext)) == [], quelltext


# ── 2. Keine Spur der alten Sperre im Arbeitsbaum ─────────────────────────────────────────────
def test_keine_datei_enthaelt_namen_der_lizenzsperre_oder_des_kaufwegs():
    """Backend, Oberfläche (`frontend/src`), Werkzeuge (`scripts`) und `.claude`. Der Text einer
    Datei darf keinen der Namen aus `VERBOTEN` tragen; ausgenommen ist nur diese Datei."""
    treffer = []
    for pfad in _dateien(WURZELN):
        if pfad.resolve() == DIESE_DATEI:
            continue
        text = _text(pfad)
        if text is None:
            continue
        for name, muster in VERBOTEN:
            for nummer, zeile in enumerate(text.splitlines(), 1):
                if muster.search(zeile):
                    treffer.append(f"{_rel(pfad)}:{nummer}: {name}")
                    break
    assert treffer == [], "\n".join(treffer)


def test_der_wachter_findet_die_verbotenen_namen_und_schont_andere():
    """Die Muster treffen die alten Namen und lassen ähnliche, erlaubte Namen in Ruhe."""
    treffen = ["lizenz.cli_pruefen('cleanup')", "if not lizenz.berechtigt():",
               "PRUEFSCHLUESSEL = {}", "https://bms.daube.tech/api/paket", "export const KAUF_URL = 'x'"]
    schonen = ["def test_cli_pruefen_exit_codes(tmp_path):", "docs_html --pruefen",
               "KAUF_URL_ALT", "berechtigt_fuer_alle()", "pruefschluessel"]
    for zeile in treffen:
        assert any(muster.search(zeile) for _, muster in VERBOTEN), zeile
    for zeile in schonen:
        assert not any(muster.search(zeile) for _, muster in VERBOTEN), zeile


# ── 3. Schreiben geht ohne Lizenzdatei ────────────────────────────────────────────────────────
def test_schreibende_route_antwortet_ohne_lizenzdatei_mit_200(client, seed):
    """Eine Notiz an einer Stelle anlegen (POST): 200 und kein Lizenz-Kopf. Der Test legt keine
    Lizenzdatei an; es gibt auch nichts mehr, was eine läse."""
    job = seed["jobs"][0]

    antwort = client.post(f"/api/jobs/{job.id}/log", json={"eintrag": "Notiz ohne Lizenzdatei"})

    assert antwort.status_code == 200, antwort.text
    assert antwort.json()["eintrag"] == "Notiz ohne Lizenzdatei"
    assert "X-BMS-Lizenz" not in antwort.headers
    verlauf = client.get(f"/api/jobs/{job.id}/log").json()
    assert any(e["eintrag"] == "Notiz ohne Lizenzdatei" for e in verlauf)


@pytest.mark.parametrize("methode, pfad, rumpf", [
    ("patch", "/api/jobs/{id}", {"notes": "geändert ohne Lizenzdatei"}),
    ("post", "/api/jobs/{id}/log", {"eintrag": "zweite Notiz"}),
])
def test_weitere_schreibende_routen_antworten_nicht_mit_402(client, seed, methode, pfad, rumpf):
    job = seed["jobs"][1]

    antwort = client.request(methode, pfad.format(id=job.id), json=rumpf)

    assert antwort.status_code == 200, antwort.text
    assert antwort.status_code != 402


def test_die_app_kennt_keine_lizenzroute_und_keine_lizenzmiddleware(client):
    import app.main as main

    pfade = main.app.openapi()["paths"]
    assert [p for p in pfade if "lizenz" in p.lower()] == []
    assert [m.cls.__name__ for m in main.app.user_middleware if "lizenz" in m.cls.__name__.lower()] == []
    assert not hasattr(main, "_OHNE_LIZENZ")
