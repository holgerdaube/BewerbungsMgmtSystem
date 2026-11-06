"""P2-90: Texte des Servers sind vollständig übersetzt. Reine Prüfung über den Quelltext (ast), ohne Server.

Ratsche: `NOCH_NICHT_UMGESTELLT` listet Dateien, in denen `HTTPException` noch festen Text tragen darf.
"""
import ast
import json
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
TEXTE = BACKEND / "app" / "texte"
NOCH_NICHT_UMGESTELLT: set[str] = set()


def _dateien() -> list[Path]:
    return sorted(list((BACKEND / "app").glob("*.py")) + list((BACKEND / "pipeline").glob("*.py")) + [BACKEND / "beirat_engine.py"])


def _rel(p: Path) -> str:
    return p.relative_to(BACKEND).as_posix()


def _ist_tx(knoten: ast.Call) -> bool:
    f = knoten.func
    return (isinstance(f, ast.Name) and f.id == "tx") or (isinstance(f, ast.Attribute) and f.attr == "tx")


def _tx_aufrufe() -> list[tuple[str, ast.Call]]:
    aus = []
    for p in _dateien():
        for k in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(k, ast.Call) and _ist_tx(k):
                aus.append((_rel(p), k))
    return aus


def _katalog(name: str = "en.json") -> dict:
    return json.loads((TEXTE / name).read_text(encoding="utf-8"))


def _platzhalter(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def test_tx_nur_mit_literal():
    for datei, k in _tx_aufrufe():
        assert k.args and isinstance(k.args[0], ast.Constant) and isinstance(k.args[0].value, str), f"{datei}:{k.lineno}"


def test_jeder_text_ist_uebersetzt_und_jeder_eintrag_benutzt():
    benutzt = {k.args[0].value for _d, k in _tx_aufrufe()}
    katalog = _katalog()
    assert not benutzt - set(katalog), sorted(benutzt - set(katalog))[:20]
    assert not set(katalog) - benutzt, sorted(set(katalog) - benutzt)[:20]


def test_platzhalter_stimmen():
    katalog = _katalog()
    for datei, k in _tx_aufrufe():
        deutsch = k.args[0].value
        namen = {w.arg for w in k.keywords}
        assert _platzhalter(deutsch) == namen, f"{datei}:{k.lineno} {deutsch!r}"
        if deutsch in katalog:
            assert _platzhalter(katalog[deutsch]) == namen, f"{datei}:{k.lineno} {katalog[deutsch]!r}"


def test_englische_texte_ohne_umlaute():
    for name in ("en.json", "en_daten.json"):
        for deutsch, englisch in _katalog(name).items():
            assert not re.search(r"[äöüÄÖÜß]", englisch) or re.search(r"[äöüÄÖÜß]", deutsch), englisch


@pytest.mark.parametrize("datei", _dateien(), ids=_rel)
def test_fehlermeldungen_laufen_ueber_tx(datei):
    if _rel(datei) in NOCH_NICHT_UMGESTELLT:
        return
    fest = []
    for k in ast.walk(ast.parse(datei.read_text(encoding="utf-8"))):
        if isinstance(k, ast.Call) and getattr(k.func, "id", getattr(k.func, "attr", "")) == "HTTPException":
            for a in list(k.args[1:]) + [w.value for w in k.keywords if w.arg == "detail"]:
                if isinstance(a, ast.JoinedStr) or (isinstance(a, ast.Constant) and isinstance(a.value, str) and re.search("[A-Za-z]", a.value)):
                    fest.append(k.lineno)
    assert not fest, f"{_rel(datei)}: Zeilen {fest}"


def test_status_passen_zur_oberflaeche():
    """Die englischen Status heißen im Backend und in der Oberfläche gleich (Excel, Digest, Berichte)."""
    common = json.loads((BACKEND.parent / "frontend" / "src" / "i18n" / "en" / "common.json").read_text(encoding="utf-8"))
    katalog = _katalog()
    for de, en in common["status"].items():
        if de in katalog:
            assert katalog[de] == en, de
