"""P2-88: Die Oberfläche bleibt zweisprachig. Reine Textprüfung über den Quelltext, ohne Node.

Geprüft wird: Beide Sprachen haben dieselben Schlüssel und Platzhalter, benutzte Schlüssel existieren, die
Wertelisten sind vollständig, und in umgestellten Dateien steht kein fest verdrahteter deutscher Text und
kein festes `de-DE` mehr. Die Texterkennung ist eine Näherung und deshalb bewusst streng im Einzelfall:
Eine begründete Ausnahme trägt den Marker `// i18n-ok: <Grund>` in der Zeile.

Ratsche: `NOCH_NICHT_UMGESTELLT` listet die Dateien, für die die Texterkennung noch nicht gilt. Eine Datei
in der Liste, die schon sauber ist, lässt den Test scheitern, damit die Liste ehrlich bleibt.
"""
import json
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"
I18N = SRC / "i18n"

NOCH_NICHT_UMGESTELLT: set[str] = set()

# Wörter, die in einem String-Literal auf deutschen Text hindeuten. Bewusst kurz: lieber ein Treffer zu
# wenig als dauernde Fehlalarme, Umlaute fangen den größten Teil.
MERKLISTE = {"bitte", "nicht", "wird", "wurde", "keine", "kein", "oder", "und", "der", "die", "das", "für", "mit"}
# Eigennamen und Fachbegriffe, die in jeder Sprache gleich sind.
EIGENNAMEN = {"ATS", "BMS", "Claude", "ChatGPT", "LinkedIn", "Gmail", "Excel", "Word", "PDF", "CV"}

_JSX_TEXT = re.compile(r"(?<![=\-])>\s*([^<>{}]*[A-Za-zÄÖÜäöüß]{3,}[^<>{}]*?)\s*<")
_ATTRIBUT = re.compile(r"""\b(?:placeholder|title|label|aria-label|alt)="([^"]*[A-Za-zÄÖÜäöüß]{2,}[^"]*)\"""")
_STRING = re.compile(r"""'([^'\n]*)'|`([^`\n]*)`|"([^"\n]*)\"""")
_KLASSEN = re.compile(r"\b(?:rounded|flex|inline|text-|bg-|border|px-|py-|grid|items-|font-|gap-|w-|h-|mt-|mb-|ml-)")


def _ohne_kommentare(quelltext: str) -> str:
    zeilen = [z for z in quelltext.splitlines() if "i18n-ok" not in z]
    text = "\n".join(zeilen)
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"(?<![:'\"\w])//[^\n]*", " ", text)


def _ist_code(text: str) -> bool:
    """JSX-Texterkennung trifft auch TypeScript (`api<T>(…) … <div`). Das erkennt man am Zeichenvorrat."""
    return bool(re.search(r"[=;()&|]|=>|\breturn\b|\bconst\b", text))


def funde(quelltext: str, jsx: bool = True) -> list[str]:
    """Fest verdrahtete Texte in einer Quelldatei. `jsx=False` für reine TypeScript-Dateien."""
    text = _ohne_kommentare(quelltext)
    ergebnis = []
    for m in (_JSX_TEXT.finditer(text) if jsx else ()):
        wort = m.group(1).strip()
        if not _ist_code(wort) and not all(w in EIGENNAMEN for w in re.findall(r"[A-Za-zÄÖÜäöüß]{3,}", wort)):
            ergebnis.append(f"JSX: {wort[:70]}")
    ergebnis += [f"Attribut: {m.group(1)[:70]}" for m in _ATTRIBUT.finditer(text)]
    for m in _STRING.finditer(text):
        wert = next(g for g in m.groups() if g is not None)
        if _KLASSEN.search(wert) or wert.startswith(("/", "./", "../", "common:")) or re.match(r"^\w+:[\w.]+$", wert):
            continue
        ohne_platzhalter = re.sub(r"\$\{[^}]*\}", " ", wert)
        woerter = {w.lower() for w in re.findall(r"[A-Za-zÄÖÜäöüß]+", ohne_platzhalter)}
        if re.search(r"[äöüÄÖÜß]", ohne_platzhalter) or woerter & MERKLISTE:
            ergebnis.append(f"Text: {wert[:70]}")
    return ergebnis


def _quelldateien() -> list[Path]:
    return sorted(p for p in list(SRC.rglob("*.tsx")) + list(SRC.rglob("*.ts"))
                  if I18N not in p.parents and p.name != "vite-env.d.ts")


def _rel(p: Path) -> str:
    return p.relative_to(SRC).as_posix()


def _flach(d: dict, praefix: str = "") -> dict:
    aus = {}
    for k, v in d.items():
        name = f"{praefix}{k}"
        if isinstance(v, dict):
            aus.update(_flach(v, name + "."))
        else:
            aus[name] = v
    return aus


def _sprache(sprache: str) -> dict[str, dict]:
    return {p.stem: _flach(json.loads(p.read_text(encoding="utf-8"))) for p in sorted((I18N / sprache).glob("*.json"))}


def _platzhalter(text: str) -> set[str]:
    return set(re.findall(r"\{\{\s*(\w+)\s*\}\}", text))


def test_beide_sprachen_haben_dieselben_dateien_und_schluessel():
    de, en = _sprache("de"), _sprache("en")
    assert set(de) == set(en)
    for bereich in de:
        assert set(de[bereich]) == set(en[bereich]), bereich


def test_platzhalter_stimmen_ueberein():
    de, en = _sprache("de"), _sprache("en")
    for bereich, texte in de.items():
        for schluessel, text in texte.items():
            assert _platzhalter(text) == _platzhalter(en[bereich][schluessel]), f"{bereich}:{schluessel}"


def test_kein_uebersetzter_text_ist_leer():
    for sprache in ("de", "en"):
        for bereich, texte in _sprache(sprache).items():
            assert all(str(t).strip() for t in texte.values()), f"{sprache}/{bereich}"


def test_mehrzahl_steht_in_beiden_formen():
    for bereich, texte in _sprache("en").items():
        for schluessel in texte:
            if schluessel.endswith("_one"):
                assert schluessel[:-4] + "_other" in texte, f"{bereich}:{schluessel}"


def test_benutzte_schluessel_existieren():
    de = _sprache("de")
    bereiche = "|".join(de)
    muster = re.compile(rf"""['"]((?:{bereiche}):[\w.]+)['"]""")
    for p in _quelldateien():
        text = _ohne_kommentare(p.read_text(encoding="utf-8"))
        for treffer in muster.findall(text):
            bereich, schluessel = treffer.split(":", 1)
            basis = de[bereich]
            assert schluessel in basis or schluessel + "_other" in basis, f"{_rel(p)}: {treffer}"


def test_schluessel_tragen_immer_einen_namespace():
    for p in _quelldateien():
        text = _ohne_kommentare(p.read_text(encoding="utf-8"))
        ohne = re.findall(r"""\bt\(\s*['"]([^'":]+)['"]""", text)
        assert not ohne, f"{_rel(p)}: {ohne}"


@pytest.mark.parametrize("datei", _quelldateien(), ids=_rel)
def test_kein_fester_text_in_umgestellten_dateien(datei):
    rel = _rel(datei)
    gefunden = funde(datei.read_text(encoding="utf-8"), jsx=datei.suffix == ".tsx")
    if rel in NOCH_NICHT_UMGESTELLT:
        assert gefunden, f"{rel} ist sauber: aus NOCH_NICHT_UMGESTELLT streichen"
    else:
        assert not gefunden, f"{rel}: {gefunden}"


@pytest.mark.parametrize("datei", _quelldateien(), ids=_rel)
def test_datum_und_zahl_nur_ueber_den_formatierer(datei):
    rel = _rel(datei)
    if rel in NOCH_NICHT_UMGESTELLT:
        return
    text = _ohne_kommentare(datei.read_text(encoding="utf-8"))
    assert "de-DE" not in text, rel
    assert not re.search(r"\.toLocale(?:Date|Time)?String\(", text), rel


def test_ratsche_kennt_nur_vorhandene_dateien():
    vorhanden = {_rel(p) for p in _quelldateien()}
    assert NOCH_NICHT_UMGESTELLT <= vorhanden, NOCH_NICHT_UMGESTELLT - vorhanden


def test_status_stehen_vollstaendig_in_den_wertelisten():
    quelle = (SRC / "components" / "ui.tsx").read_text(encoding="utf-8")
    block = quelle[quelle.index("STATUS_FARBEN:"):quelle.index("STATUS_FARBE_UNBEKANNT")]
    status = re.findall(r"""^\s*'?([^':\n]+?)'?: \{ bg:""", block, flags=re.M)
    assert len(status) == 11
    de = _sprache("de")["common"]
    for s in status:
        assert f"status.{s}" in de, s


def test_senioritaeten_stehen_vollstaendig_in_den_wertelisten():
    quelle = (SRC / "senioritaet.ts").read_text(encoding="utf-8")
    stufen = re.findall(r"'([^']+)'", quelle)
    assert "Praktikant" in stufen
    de = _sprache("de")["common"]
    for s in stufen:
        assert f"seniority.{s}" in de, s


@pytest.mark.parametrize("bereich", ["status", "situation", "work_model", "seniority", "tab", "verfuegbarkeit", "mail_kategorie"])
def test_werteliste_deutsch_gleich_db_wert_und_ohne_trennzeichen(bereich):
    """Deutsch zeigt genau den DB-Wert, und der Wert taugt als Schlüssel (`.` und `:` trennen dort)."""
    de = json.loads((I18N / "de" / "common.json").read_text(encoding="utf-8"))[bereich]
    for dbwert, anzeige in de.items():
        assert anzeige == dbwert
        assert "." not in dbwert and ":" not in dbwert


def test_glossar_nennt_die_status_wie_die_oberflaeche():
    glossar = (Path(__file__).resolve().parents[2] / "config" / "glossar_de_en.md").read_text(encoding="utf-8")
    zeilen = dict(re.findall(r"^\| ([^|]+?) \| ([^|]+?) \|$", glossar, flags=re.M))
    en = _sprache("en")["common"]
    for s, anzeige in ((k[7:], v) for k, v in en.items() if k.startswith("status.")):
        assert zeilen.get(s) == anzeige, s


# Der Wächter selbst: Diese Fälle müssen erkannt werden, sonst wird er unbemerkt blind.
@pytest.mark.parametrize("zeile", [
    "<h1 className='x'>Stellen anlegen</h1>",
    '<input placeholder="Suche Firma" />',
    "const a = 'Bitte wählen'",
    "const b = `Nicht ${x} vorhanden`",
    "const c = 'Keine Rückmeldung'",
])
def test_waechter_erkennt(zeile):
    assert funde(zeile)


@pytest.mark.parametrize("zeile", [
    "<h1 className='x'>{t('jobs:titel.stellen')}</h1>",
    "const klasse = 'rounded-lg border text-sm'",
    "// Kommentar für die Stelle",
    "const c = 'Keine Rückmeldung' // i18n-ok: DB-Wert",
    "const x = api<JobRow[]>(`/jobs?${p}`)",
    "<span>ATS</span>",
])
def test_waechter_schweigt(zeile):
    assert not funde(zeile)
