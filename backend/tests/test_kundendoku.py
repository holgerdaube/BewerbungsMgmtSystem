"""P2-60: Kunden-Dokumente ohne interne Verweise.

Kunden lesen diese Texte im Programmordner und auf der Dokumentationsseite. Zwei Arten von
Verweisen sind dort sinnlos oder führen ins Leere, beide standen bis P2-60 in ausgelieferten
Dokumenten (u. a. 22 Phasen-Nummern in `ANLEITUNG.md`, Verweise auf `docs/INSTALLATION.md`,
`tasks/lessons.md` und `.github/workflows/ci.yml` in `SETUP-WINDOWS.md`):

  1. Phasen-Nummern der Entwicklung („Phase 38“, „Phasen 81/82“, „Phase-73-Fallback“, „P2-52“).
  2. Namen von Dateien, die das Kundenpaket nicht enthält: interne Doku (`docs/*.md` außerhalb
     von `DOKU_ERLAUBT`) und alles aus `AUSSCHLUESSE` (Ordner wie `tasks/`, einzelne Werkzeuge
     wie `scripts/test.sh`, auch nur mit dem Dateinamen genannt).

Beide Listen kommen aus derselben Quelle wie das Paket (`pipeline.kundenpaket`), die internen
Dokumente aus dem echten `docs/`-Ordner. Ein neues internes Dokument oder ein neuer Ausschluss ist
damit ohne Änderung an diesem Test gesperrt.

Bewusst nicht geprüft: die Skills unter `.claude/` (Anweisungen an die KI-Läufe, kein Lesetext)
und Datumsangaben (ein Datum kann ein legitimes Beispiel sein). Die Erkennung selbst hat einen
eigenen Test mit Beispielen, damit sie nicht unbemerkt blind wird.

App-Module nur funktionslokal importieren (s. conftest.py).
"""
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# „Phase 38“, „Phasen 81/82“, „Phase-73-Fallback“, „Phase 71D“, „P2-52“. Ohne Ziffer („in dieser
# Phase“) ist es kein Verweis auf die Entwicklungsgeschichte.
_PHASE_RE = re.compile(r"\bPhasen?[\s-]+\d[\w/]*|\bP2-\d+")

# Vor und nach einem Namen darf kein weiteres Namenszeichen stehen, sonst wäre
# `COACH_SITE.md` in `ANLEITUNG_COACH_SITE.md` ein Fund.
_DAVOR = r"(?<![\w.-])"
_DANACH = r"(?![\w-])"

# P2-82: Die Lizenz-Doku (`docs/LIZENZ.md`) ist ausgebaut, es gibt weder Datei noch Reiter. Verweise
# darauf fängt `_interne_muster` nur, solange eine Datei dieses Namens im Arbeitsbaum liegt (jede
# docs-Datei außerhalb von `DOKU_ERLAUBT`); dieses Muster gilt unabhängig davon, auch nach dem Löschen.
_LIZENZ_DOKU_RE = re.compile(_DAVOR + r"LIZENZ\.(?:md|html)" + _DANACH)


def _kundentexte() -> list[str]:
    """Alle ausgelieferten Lesetexte: die Positivliste für `docs/` plus die Dokumente im Paket-Root
    (P2-71: die beiden Installationsanleitungen für den Reiter „Installation & Updates“, dazu das
    Änderungsprotokoll für „Version“)."""
    from pipeline import kundenpaket as kp
    return (sorted(f"docs/{name}.md" for name in kp.DOKU_ERLAUBT)
            + [f"docs/en/{name}.md" for name in sorted(kp.DOKU_ERLAUBT)]
            + ["BMS_Install_MAC.md", "BMS_Install_Windows.md", "CHANGELOG.md",
               "BMS_Install_MAC.en.md", "BMS_Install_Windows.en.md", "CHANGELOG.en.md"])


def _interne_muster() -> list[re.Pattern]:
    """Suchmuster für alles, was das Paket nicht enthält."""
    from pipeline import kundenpaket as kp
    muster = []
    for md in sorted((PROJECT_ROOT / "docs").glob("*.md")):
        if md.stem not in kp.DOKU_ERLAUBT:
            muster.append(re.compile(_DAVOR + re.escape(md.stem) + r"\.(?:md|html)" + _DANACH))
    for pfad, _grund in kp.AUSSCHLUESSE:
        if pfad.endswith("/"):
            # Ordner: voller Pfad und letzter Abschnitt („backend/tests/“ und „tests/“)
            for teil in {pfad, pfad.rstrip("/").rsplit("/", 1)[-1] + "/"}:
                muster.append(re.compile(_DAVOR + re.escape(teil)))
        else:
            for teil in {pfad, pfad.rsplit("/", 1)[-1]}:
                muster.append(re.compile(_DAVOR + re.escape(teil) + _DANACH))
    return muster


def _funde(text: str, muster: list[re.Pattern]) -> list[str]:
    funde = []
    for nr, zeile in enumerate(text.splitlines(), 1):
        for m in muster:
            for treffer in m.finditer(zeile):
                funde.append(f"Zeile {nr}: {treffer.group(0)!r} in {zeile.strip()[:120]!r}")
    return funde


def _alle_funde(muster: list[re.Pattern]) -> list[str]:
    funde = []
    for rel in _kundentexte():
        text = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
        funde += [f"{rel} {f}" for f in _funde(text, muster)]
    return funde


def test_kundentexte_sind_vollstaendig_und_vorhanden():
    texte = _kundentexte()
    assert "docs/ANLEITUNG.md" in texte and "docs/SETUP-WINDOWS.md" in texte
    assert "BMS_Install_MAC.md" in texte and "BMS_Install_Windows.md" in texte
    assert "BMS_Install.md" not in texte and "BMS_Install_Auto.md" not in texte
    assert "docs/LIZENZ.md" not in texte           # P2-82: ausgebaut, keine Kunden-Doku mehr
    fehlend = [rel for rel in texte if not (PROJECT_ROOT / rel).is_file()]
    assert not fehlend, f"Kundentexte fehlen: {fehlend}"


def test_kundentexte_ohne_phasen_nummern():
    funde = _alle_funde([_PHASE_RE])
    assert not funde, "Phasen-Nummern in Kundentexten:\n" + "\n".join(funde)


def test_kundentexte_ohne_verweise_auf_nicht_ausgelieferte_dateien():
    funde = _alle_funde(_interne_muster())
    assert not funde, "Verweise auf Dateien, die nicht im Kundenpaket liegen:\n" + "\n".join(funde)


def test_kundentexte_ohne_verweis_auf_die_ausgebaute_lizenz_doku():
    funde = _alle_funde([_LIZENZ_DOKU_RE])
    assert not funde, "Verweise auf die entfallene Lizenz-Doku:\n" + "\n".join(funde)


def test_erkennung_trifft_beispiele():
    """Die Erkennung selbst: jedes Beispiel links ist ein Fund, keines rechts."""
    muster = [_PHASE_RE] + _interne_muster()
    funde = [
        "seit Phase 38 schon bei der Erfassung", "Coach-Site (Phasen 81/82)",
        "Karriereseite (Phase-73-Fallback)", "Windows-Grundlagen (Phase 71D)", "Datensicherung (P2-52)",
        "s. `docs/INSTALLATION.md`", "Strategie: `docs/GMAIL-STRATEGIE.md`", "siehe `AUTOMATION.md`",
        "Technik in DOKUMENTATION.html", "(s. `tasks/lessons.md`)", "Job in `.github/workflows/ci.yml`",
        "`tests/test_docs_html.py`", "`backend/tests/test_cv_export.py`", "`.claude/launch.json`",
        "alle erwarten (`test.sh`, `backup_db.sh`)", "`backend/pipeline/kundenpaket.py`",
    ]
    keine = [
        "Einrichtung: `docs/ANLEITUNG_COACH_SITE.md`",
        "`BMS_Install_MAC.md`, Abschnitt „Aktualisierungen einspielen“",
        "`BMS_Install_Windows.md`, Schritt 2", "Schritt 2",
        "in dieser Phase der Suche", "`scripts/backup_db.sh`", "`scripts/cv_basis_umbau_v10.py`",
        "Reiter „Release“ der Dokumentation", "die Unit-tests/ laufen", "`docs/SETUP-EMAIL.md`",
    ]
    for beispiel in funde:
        assert _funde(beispiel, muster), f"nicht erkannt: {beispiel!r}"
    for beispiel in keine:
        assert not _funde(beispiel, muster), f"fälschlich erkannt: {beispiel!r}"


def test_erkennung_der_entfallenen_lizenz_doku():
    """P2-82: Das eigene Muster trifft die Dateinamen der entfallenen Doku, nicht die der
    Open-Source-Lizenz (`LICENSE`, `NOTICE`, `lizenz.txt`) und nicht das Wort „Lizenz“."""
    for beispiel in ("s. `docs/LIZENZ.md`", "Arten: LIZENZ.html", "siehe [Lizenz](LIZENZ.md)"):
        assert _funde(beispiel, [_LIZENZ_DOKU_RE]), f"nicht erkannt: {beispiel!r}"
    for beispiel in ("`LICENSE` und `NOTICE`", "frontend/src/rechtliches/lizenz.txt",
                     "Open-Source-Lizenz (Apache-2.0)", "Drittanbieter-Lizenzen", "ANLEITUNG_LIZENZ.md"):
        assert not _funde(beispiel, [_LIZENZ_DOKU_RE]), f"fälschlich erkannt: {beispiel!r}"
