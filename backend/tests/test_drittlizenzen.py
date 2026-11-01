"""Tests für `pipeline/drittlizenzen.py` (P2-77) — die Seite „Rechtliches → Drittanbieter-Lizenzen“
wird aus den Lockfiles ERZEUGT und nie von Hand gepflegt.

Zwei Teile:
  A. Einheitstests (Punkte 1 bis 6 der Spec) mit gebautem Fake-Bestand in `tmp_path`: Fake-
     `site-packages` mit echten `*.dist-info`-Ordnern (METADATA, RECORD, Lizenzdateien), Fake-
     `node_modules` und Fake-Lockfiles. Der Generator bekommt Projektwurzel, Spiegel und `site_pfad`
     als Parameter, der echte venv und der echte Build-Spiegel werden nie angefasst.
  B. Wache über den ECHTEN Stand (Punkte 7 bis 10): vergleicht die eingecheckte Seite mit den
     eingecheckten Lockfiles. Sie braucht weder venv-Metadaten noch node_modules und läuft deshalb
     auch in der CI (backend, backend-windows). Sie prüft Bestand und Kennungen, nicht den Wortlaut
     (den prüft `scripts/drittlizenzen.sh --pruefen` in der Entwicklungsinstallation).

Kein app.*/pipeline.*-Import auf Modulebene (conftest-Konvention, s. tests/conftest.py)."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MD_REL = "frontend/src/rechtliches/drittlizenzen.md"
TXT_REL = "frontend/src/rechtliches/drittlizenzen_texte.txt"


def _mod():
    from pipeline import drittlizenzen
    return drittlizenzen


# ── Bau des Fake-Bestands ────────────────────────────────────────────────────────────────

def _py_paket(site: Path, name: str, version: str, *, expression=None, lizenz_feld=None,
              dateien=None):
    """Legt `<name>-<version>.dist-info` mit METADATA, RECORD und Lizenzdateien an.
    `dateien`: {Pfad innerhalb der dist-info: Inhalt (str oder bytes)}."""
    di = site / f"{name.replace('-', '_')}-{version}.dist-info"
    di.mkdir(parents=True)
    meta = [f"Metadata-Version: 2.1", f"Name: {name}", f"Version: {version}"]
    if expression:
        meta.append(f"License-Expression: {expression}")
    if lizenz_feld:
        meta.append(f"License: {lizenz_feld}")
    (di / "METADATA").write_text("\n".join(meta) + "\n", encoding="utf-8")
    zeilen = [f"{di.name}/METADATA,,", f"{di.name}/RECORD,,", f"{name.replace('-', '_')}/__init__.py,,"]
    for rel, inhalt in (dateien or {}).items():
        ziel = di / rel
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(inhalt if isinstance(inhalt, bytes) else inhalt.encode("utf-8"))
        zeilen.append(f"{di.name}/{rel},,")
    (di / "RECORD").write_text("\n".join(zeilen) + "\n", encoding="utf-8")


def _npm_paket(nm: Path, schluessel: str, version: str, dateien=None):
    """Legt `<nm>/<schluessel ohne node_modules/>/package.json` und Lizenzdateien an."""
    ordner = nm / schluessel
    ordner.mkdir(parents=True)
    (ordner / "package.json").write_text(json.dumps({"name": schluessel, "version": version}), encoding="utf-8")
    for name, inhalt in (dateien or {}).items():
        (ordner / name).write_bytes(inhalt if isinstance(inhalt, bytes) else inhalt.encode("utf-8"))


def _bauen(tmp_path: Path, texte: dict | None = None) -> SimpleNamespace:
    """Kleiner, aber vollständiger Bestand:
      Python direkt: alpha, Gamma_Pkg (Lockfile-Schreibweise, pyproject: Gamma.Pkg -> PEP 503)
      Python mit:    beta (mit NOTICE), Delta
      Oberfläche:    reactish (direkt), helper (mitgebracht)
      Bauwerkzeuge:  buildtool (direkt), 3 weitere (MIT, Apache-2.0, CC-BY-4.0)"""
    texte = texte or {}
    root = tmp_path / "projekt"
    site = tmp_path / "site-packages"
    nm = tmp_path / "node_modules"
    (root / "backend").mkdir(parents=True)
    (root / "frontend").mkdir(parents=True)
    site.mkdir()
    nm.mkdir()

    (root / "backend" / "requirements-lock.txt").write_text(
        "# Kommentar\n\nalpha==1.0\nbeta==2.0\nDelta==0.5\nGamma_Pkg==3.1\n", encoding="utf-8")
    (root / "backend" / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0"\ndependencies = ["alpha>=1.0", "Gamma.Pkg>=3"]\n',
        encoding="utf-8")

    def t(name):
        return texte.get(name, f"Lizenz von {name}\nZeile zwei\n")

    _py_paket(site, "alpha", "1.0", expression="MIT", dateien={"licenses/LICENSE": t("alpha")})
    _py_paket(site, "beta", "2.0", lizenz_feld="BSD-3-Clause",
              dateien={"licenses/LICENSE": t("beta"), "licenses/NOTICE": "Hinweis von beta\n"})
    _py_paket(site, "Delta", "0.5", expression="ISC", dateien={"COPYING.txt": t("Delta")})
    _py_paket(site, "Gamma_Pkg", "3.1", expression="Apache-2.0 OR BSD-3-Clause",
              dateien={"licenses/LICENSE": t("Gamma_Pkg")})

    (root / "frontend" / "package.json").write_text(json.dumps({
        "dependencies": {"reactish": "^1.2.0"},
        "devDependencies": {"buildtool": "^5.0.0"},
    }), encoding="utf-8")
    (root / "frontend" / "package-lock.json").write_text(json.dumps({
        "lockfileVersion": 3,
        "packages": {
            "": {"name": "x", "dependencies": {"reactish": "^1.2.0"}, "devDependencies": {"buildtool": "^5.0.0"}},
            "node_modules/reactish": {"version": "1.2.0", "license": "MIT"},
            "node_modules/helper": {"version": "0.3.0", "license": "ISC"},
            "node_modules/buildtool": {"version": "5.0.0", "license": "MIT", "dev": True},
            "node_modules/bt-helper": {"version": "1.0.0", "license": "Apache-2.0", "dev": True},
            "node_modules/browserdb": {"version": "2.0.0", "license": "CC-BY-4.0", "dev": True},
            "node_modules/buildtool/node_modules/nested": {"version": "0.1.0", "license": "MIT", "dev": True},
        },
    }), encoding="utf-8")
    _npm_paket(nm, "reactish", "1.2.0", {"LICENSE": t("reactish"), "README.md": "kein Lizenztext"})
    _npm_paket(nm, "helper", "0.3.0", {"LICENSE.md": t("helper")})
    return SimpleNamespace(root=root, site=[site], nm=nm, site_dir=site)


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """Fake-Bestand plus passende Konstanten (ZWECK, LIZENZ_FESTGELEGT)."""
    m = _mod()
    monkeypatch.setattr(m, "ZWECK", {"alpha": "Zweck alpha", "gamma-pkg": "Zweck gamma",
                                       "reactish": "Zweck reactish"})
    monkeypatch.setattr(m, "LIZENZ_FESTGELEGT", {})
    return _bauen(tmp_path)


def _lauf(b, capsys, *args):
    """CLI-Lauf gegen den Fake-Bestand. Liefert (Exit-Code, stdout, stderr)."""
    capsys.readouterr()
    code = _mod().main(["--node-modules", str(b.nm), *args], projekt_root=b.root, site_pfad=b.site)
    out = capsys.readouterr()
    return code, out.out, out.err


def _erzeugt(b):
    return _mod().erzeugen(b.root, b.nm, b.site)


# ── 1. Inhalt, Reihenfolge, Determinismus ─────────────────────────────────────────────────

def test_dateien_nennen_pakete_mit_version_und_kennung_in_richtiger_reihenfolge(fake):
    md, txt = _erzeugt(fake)

    # Paketzeilen mit Version, Kennung und (bei direkten Paketen) Zweck.
    assert "- **alpha** 1.0 — MIT — Zweck alpha\n" in md
    assert "- **Gamma_Pkg** 3.1 — Apache-2.0 OR BSD-3-Clause — Zweck gamma\n" in md
    assert "- **beta** 2.0 — BSD-3-Clause\n" in md          # Kennung aus dem Feld License
    assert "- **Delta** 0.5 — ISC\n" in md
    assert "- **reactish** 1.2.0 — MIT — Zweck reactish\n" in md
    assert "- **helper** 0.3.0 — ISC\n" in md
    assert "- **buildtool** 5.0.0 — MIT\n" in md             # Bauwerkzeug ohne Zweck

    # Fester Aufbau: Abschnitte in der Reihenfolge der Spec.
    ueberschriften = [z[4:] for z in md.split("\n") if z.startswith("### ")]
    assert ueberschriften == [
        "Backend (Python), direkt verwendet",
        "Backend (Python), von diesen Paketen mitgebracht",
        "Oberfläche (läuft im Browser), direkt verwendet",
        "Oberfläche, mitgebracht",
        "Zum Bauen der Oberfläche",
        "Separat vom Nutzer installierte Programme",
        "Von Nutzern angebundene Drittdienste",
    ]
    # Innerhalb eines Abschnitts nach Namen (casefold): beta vor Delta.
    assert md.index("- **beta**") < md.index("- **Delta**")
    # Gamma_Pkg steht (direkt) vor der mitgebrachten Gruppe.
    assert md.index("- **Gamma_Pkg**") < md.index("- **beta**")

    # Bauwerkzeuge: 1 direktes, 3 weitere, gesamt 4. Zählung: Anzahl absteigend, dann Kennung.
    assert "Dazu kommen 3 weitere Werkzeuge" in md
    assert "Lizenzen aller 4: 2 × MIT, 1 × Apache-2.0, 1 × CC-BY-4.0." in md
    assert md.rstrip("\n").endswith("Diese Übersicht wird aus den Paketlisten des Programms erzeugt.")
    assert "\n---\n" in md

    # Texte: Jedes Paket mit Version, die NOTICE-Datei kommt mit, Blöcke nach erstem Paket sortiert.
    assert "Hinweis von beta" in txt
    gilt = [z for z in txt.split("\n") if z.startswith("Gilt für: ")]
    assert gilt == [
        "Gilt für: alpha 1.0 (Python)",
        "Gilt für: beta 2.0 (Python)",
        "Gilt für: beta 2.0 (Python)",
        "Gilt für: Delta 0.5 (Python)",
        "Gilt für: Gamma_Pkg 3.1 (Python)",
        "Gilt für: helper 0.3.0 (Oberfläche)",
        "Gilt für: reactish 1.2.0 (Oberfläche)",
    ]
    dateien = [z for z in txt.split("\n") if z.startswith("Datei: ")]
    assert dateien == ["Datei: LICENSE", "Datei: LICENSE", "Datei: NOTICE", "Datei: COPYING.txt",
                       "Datei: LICENSE", "Datei: LICENSE.md", "Datei: LICENSE"]
    assert "kein Lizenztext" not in txt        # README ist keine Lizenzdatei
    assert txt.endswith("\n") and not txt.endswith("\n\n")


def test_zwei_laeufe_sind_byte_gleich_und_ohne_pfade(fake, capsys):
    a = _erzeugt(fake)
    b = _erzeugt(fake)
    assert a == b
    for text in a:
        assert str(fake.root) not in text and str(fake.nm) not in text and str(fake.site_dir) not in text

    code, _, _ = _lauf(fake, capsys)
    assert code == 0
    md_pfad, txt_pfad = fake.root / MD_REL, fake.root / TXT_REL
    vorher = (md_pfad.read_bytes(), txt_pfad.read_bytes())
    assert vorher == (a[0].encode("utf-8"), a[1].encode("utf-8"))
    code, out, _ = _lauf(fake, capsys)
    assert code == 0 and "unverändert" in out
    assert (md_pfad.read_bytes(), txt_pfad.read_bytes()) == vorher


# ── 2. Wortgleiche Texte stehen einmal ───────────────────────────────────────────────────

def test_gleicher_lizenztext_ergibt_einen_block_mit_beiden_paketen(tmp_path, monkeypatch):
    m = _mod()
    monkeypatch.setattr(m, "ZWECK", {"alpha": "a", "gamma-pkg": "g", "reactish": "r"})
    gemeinsam = "Gemeinsamer Wortlaut\nCopyright Autor\n"
    # alpha (Python) und reactish (Oberfläche) bringen byte-gleichen Text mit (Art darf gemischt sein).
    b = _bauen(tmp_path, {"alpha": gemeinsam, "reactish": gemeinsam})
    _, txt = _erzeugt(b)
    assert txt.count("Gemeinsamer Wortlaut") == 1
    assert "Gilt für: alpha 1.0 (Python), reactish 1.2.0 (Oberfläche)\nDatei: LICENSE\n" in txt
    # Die übrigen Pakete behalten ihren eigenen Block.
    assert "Gilt für: beta 2.0 (Python)\n" in txt


# ── 3. Angleichung: nur LF und Leerzeichen am Zeilenende ─────────────────────────────────

def test_crlf_und_zeilenendleerzeichen_werden_angeglichen_sonst_bleibt_der_wortlaut(tmp_path, monkeypatch):
    m = _mod()
    monkeypatch.setattr(m, "ZWECK", {"alpha": "a", "gamma-pkg": "g", "reactish": "r"})
    roh = ("Kopf  \r\n"
           "  eingerückt bleibt  mit  Doppelleerzeichen\t\r\n"
           "\r\n"
           "Mail: autor@beispiel.example\r\n"
           "Ende").encode("utf-8")
    b = _bauen(tmp_path, {"alpha": roh})
    _, txt = _erzeugt(b)
    erwartet = ("Kopf\n"
                "  eingerückt bleibt  mit  Doppelleerzeichen\n"
                "\n"
                "Mail: autor@beispiel.example\n"     # Adresse bleibt unverändert (nichts geschwärzt)
                "Ende\n")
    assert erwartet in txt
    assert "\r" not in txt
    assert "Kopf  " not in txt


# ── 4. Abbrüche mit Exit 2, die Meldung nennt das Paket ──────────────────────────────────

def test_abbruch_version_im_venv_weicht_ab(fake, capsys):
    lock = fake.root / "backend" / "requirements-lock.txt"
    lock.write_text(lock.read_text(encoding="utf-8").replace("alpha==1.0", "alpha==1.1"), encoding="utf-8")
    code, _, err = _lauf(fake, capsys)
    assert code == 2
    assert "alpha" in err and "1.0" in err and "1.1" in err
    assert "pip install -r backend/requirements-lock.txt" in err


def test_abbruch_version_im_node_modules_weicht_ab(fake, capsys):
    (fake.nm / "reactish" / "package.json").write_text(json.dumps({"version": "1.1.0"}), encoding="utf-8")
    code, _, err = _lauf(fake, capsys)
    assert code == 2
    assert "reactish" in err and "1.1.0" in err and "1.2.0" in err
    assert "frontend/build.sh" in err


def test_abbruch_keine_lizenzdatei_python(fake, capsys):
    di = next(fake.site_dir.glob("Delta-*.dist-info"))
    (di / "COPYING.txt").unlink()
    rec = di / "RECORD"
    rec.write_text("\n".join(z for z in rec.read_text(encoding="utf-8").split("\n")
                             if "COPYING" not in z), encoding="utf-8")
    code, _, err = _lauf(fake, capsys)
    assert code == 2
    assert "Delta" in err and "Lizenzdatei" in err


def test_abbruch_keine_lizenzdatei_npm(fake, capsys):
    (fake.nm / "helper" / "LICENSE.md").unlink()
    code, _, err = _lauf(fake, capsys)
    assert code == 2
    assert "helper" in err and "Lizenzdatei" in err


def test_abbruch_unklare_kennung_ohne_tabelleneintrag(fake, capsys):
    _py_paket(fake.site_dir, "unklar", "1.0", lizenz_feld="BSD", dateien={"LICENSE": "Text\n"})
    with (fake.root / "backend" / "requirements-lock.txt").open("a", encoding="utf-8") as f:
        f.write("unklar==1.0\n")
    code, _, err = _lauf(fake, capsys)
    assert code == 2
    assert "unklar" in err and "LIZENZ_FESTGELEGT" in err


def test_tabelleneintrag_mit_richtigem_hash_gilt_mit_falschem_bricht_ab(fake, capsys, monkeypatch):
    m = _mod()
    _py_paket(fake.site_dir, "unklar", "1.0", lizenz_feld="BSD", dateien={"LICENSE": "Text\r\n"})
    with (fake.root / "backend" / "requirements-lock.txt").open("a", encoding="utf-8") as f:
        f.write("unklar==1.0\n")

    # Der Hash gilt für den ANGEGLICHENEN Wortlaut (LF).
    monkeypatch.setattr(m, "LIZENZ_FESTGELEGT", {"unklar": ("BSD-2-Clause", m.wortlaut_hash(["Text\n"]))})
    code, _, err = _lauf(fake, capsys)
    assert code == 0, err
    assert "- **unklar** 1.0 — BSD-2-Clause\n" in (fake.root / MD_REL).read_text(encoding="utf-8")

    monkeypatch.setattr(m, "LIZENZ_FESTGELEGT", {"unklar": ("BSD-2-Clause", "000000000000")})
    code, _, err = _lauf(fake, capsys)
    assert code == 2
    assert "unklar" in err and "geändert" in err and "LIZENZ_FESTGELEGT" in err


def test_abbruch_direktes_paket_ohne_zweck(fake, capsys, monkeypatch):
    m = _mod()
    monkeypatch.setattr(m, "ZWECK", {"gamma-pkg": "g", "reactish": "r"})      # alpha fehlt
    code, _, err = _lauf(fake, capsys)
    assert code == 2
    assert "alpha" in err and "ZWECK" in err

    monkeypatch.setattr(m, "ZWECK", {"alpha": "a", "gamma-pkg": "g"})         # reactish fehlt
    code, _, err = _lauf(fake, capsys)
    assert code == 2
    assert "reactish" in err and "ZWECK" in err


def test_abbruch_kennung_ausserhalb_der_positivliste(fake, capsys):
    # Python: GPL im Produktivbestand.
    di = next(fake.site_dir.glob("Delta-*.dist-info"))
    meta = di / "METADATA"
    meta.write_text(meta.read_text(encoding="utf-8").replace("License-Expression: ISC",
                                                             "License-Expression: GPL-3.0-only"),
                    encoding="utf-8")
    code, _, err = _lauf(fake, capsys)
    assert code == 2 and "Delta" in err and "GPL-3.0-only" in err

    # Bauwerkzeug mit unzulässiger Lizenz (CC-BY-4.0 ist für Bauwerkzeuge erlaubt, GPL nicht).
    meta.write_text(meta.read_text(encoding="utf-8").replace("GPL-3.0-only", "ISC"), encoding="utf-8")
    lock = fake.root / "frontend" / "package-lock.json"
    lock.write_text(lock.read_text(encoding="utf-8").replace('"Apache-2.0", "dev"', '"GPL-3.0-only", "dev"'),
                    encoding="utf-8")
    code, _, err = _lauf(fake, capsys)
    assert code == 2 and "bt-helper" in err

    # CC-BY-4.0 im Produktivbestand ist nicht erlaubt.
    lock.write_text(lock.read_text(encoding="utf-8").replace("GPL-3.0-only", "Apache-2.0")
                    .replace('"version": "1.2.0", "license": "MIT"', '"version": "1.2.0", "license": "CC-BY-4.0"'),
                    encoding="utf-8")
    code, _, err = _lauf(fake, capsys)
    assert code == 2 and "reactish" in err and "CC-BY-4.0" in err


# ── 5. kennung_erlaubt ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ausdruck, nur_bau, erwartet", [
    ("MIT", False, True),
    ("GPL-3.0-only", False, False),
    ("Apache-2.0 OR BSD-3-Clause", False, True),
    ("(MIT OR CC0-1.0)", False, True),          # eine Seite genügt, Klammern werden ignoriert
    ("MIT AND GPL-2.0-only", False, False),     # bei AND müssen beide erlaubt sein
    ("MIT AND ISC", False, True),
    ("GPL-2.0-only OR GPL-3.0-only", False, False),
    ("CC-BY-4.0", False, False),                # nur für Bauwerkzeuge
    ("CC-BY-4.0", True, True),
    ("GPL-3.0-only", True, False),
    ("MIT OR (GPL-2.0-only AND ISC)", False, True),
    ("MIT AND (GPL-2.0-only OR ISC)", False, True),
    ("(MIT", False, False),                     # kaputter Ausdruck ist nie erlaubt
    ("", False, False),
    ("Apache 2.0", False, False),               # unklare Schreibweise ist nie erlaubt
])
def test_kennung_erlaubt(ausdruck, nur_bau, erwartet):
    assert _mod().kennung_erlaubt(ausdruck, nur_bau=nur_bau) is erwartet


# ── 6. --pruefen ─────────────────────────────────────────────────────────────────────────

def test_pruefen_aktuell_veraltet_und_schreibt_nichts(fake, capsys):
    code, _, _ = _lauf(fake, capsys)
    assert code == 0
    md_pfad, txt_pfad = fake.root / MD_REL, fake.root / TXT_REL

    code, out, _ = _lauf(fake, capsys, "--pruefen")
    assert code == 0 and "aktuell" in out

    # Eine geänderte Zeile in der Texte-Datei: Exit 1, die Ausgabe nennt genau diese Datei.
    geaendert = txt_pfad.read_bytes().replace(b"Zeile zwei", b"Zeile ZWEI", 1)
    txt_pfad.write_bytes(geaendert)
    md_vorher = md_pfad.read_bytes()
    stand = (txt_pfad.read_bytes(), txt_pfad.stat().st_mtime_ns, md_pfad.stat().st_mtime_ns)
    code, out, _ = _lauf(fake, capsys, "--pruefen")
    assert code == 1
    assert TXT_REL in out and MD_REL not in out
    # Es wurde nichts geschrieben (Inhalt und mtime).
    assert (txt_pfad.read_bytes(), txt_pfad.stat().st_mtime_ns, md_pfad.stat().st_mtime_ns) == stand
    assert md_pfad.read_bytes() == md_vorher

    # Fehlende Datei: ebenfalls Exit 1, und sie wird nicht angelegt.
    md_pfad.unlink()
    code, out, _ = _lauf(fake, capsys, "--pruefen")
    assert code == 1 and MD_REL in out
    assert not md_pfad.exists()

    # Der Generator stellt beides wieder her.
    code, _, _ = _lauf(fake, capsys)
    assert code == 0
    code, _, _ = _lauf(fake, capsys, "--pruefen")
    assert code == 0


# ── B. Wache über den echten Stand (Punkte 7 bis 10) ─────────────────────────────────────

def _echt():
    md = (PROJECT_ROOT / MD_REL).read_text(encoding="utf-8")
    txt = (PROJECT_ROOT / TXT_REL).read_text(encoding="utf-8")
    return md, txt


def test_wache_seite_passt_zu_den_lockfiles():
    """Punkt 7. Rot, sobald ein Lockfile (oder pyproject/package.json) sich ändert und die Seite nicht
    neu erzeugt wurde. Abhilfe: scripts/drittlizenzen.sh (in der Entwicklungsinstallation, mit venv und Build-Spiegel)."""
    m = _mod()
    md, txt = _echt()
    meldungen = m.abweichungen(m.bestand_soll(PROJECT_ROOT), m.bestand_ist(md, txt))
    assert meldungen == [], "\n".join(meldungen) + "\n→ scripts/drittlizenzen.sh ausführen"


def test_wache_alle_kennungen_stehen_auf_der_positivliste():
    """Punkt 8. Bauwerkzeuge dürfen zusätzlich CC-BY-4.0 tragen."""
    m = _mod()
    md, txt = _echt()
    ist = m.bestand_ist(md, txt)
    gesehen = 0
    for abschnitt, kennungen in ist["kennungen"].items():
        for name, kennung in kennungen.items():
            gesehen += 1
            assert m.kennung_erlaubt(kennung, nur_bau=(abschnitt == "bau_direkt")), \
                f"{name}: {kennung} steht nicht auf der Positivliste"
    assert gesehen >= 48
    assert ist["bau_zaehlung"], "Zählung der Bauwerkzeuge fehlt"
    for kennung in ist["bau_zaehlung"]:
        assert m.kennung_erlaubt(kennung, nur_bau=True), f"Bauwerkzeug-Lizenz {kennung} nicht erlaubt"


def test_wache_dateien_sind_utf8_nur_lf_und_enden_mit_einem_zeilenumbruch():
    """Punkt 9."""
    for rel in (MD_REL, TXT_REL):
        roh = (PROJECT_ROOT / rel).read_bytes()
        roh.decode("utf-8")
        assert b"\r" not in roh, f"{rel}: enthält CR"
        assert roh.endswith(b"\n") and not roh.endswith(b"\n\n"), f"{rel}: muss mit genau einem LF enden"


def test_wache_uebersicht_nutzt_nur_die_mittel_des_mini_renderers():
    """Keine Backticks, Links, Tabellen oder Zitate (Rechtliches.tsx kann nur ##/###, Absätze, - Listen,
    **fett**, nackte https-Adressen und ---). Dazu: Der Bestand ist so vollständig, wie die Abnahme es
    verlangt."""
    m = _mod()
    md, txt = _echt()
    assert "`" not in md and "](" not in md
    for zeile in md.split("\n"):
        assert not zeile.lstrip().startswith(("|", ">", "# ", "1.")), zeile
    ist = m.bestand_ist(md, txt)
    assert len(ist["python_direkt"]) + len(ist["python_mit"]) == 38
    assert len(ist["npm_direkt"]) + len(ist["npm_mit"]) == 10
    assert len(ist["bau_direkt"]) == 8 and ist["bau_gesamt"] == 176
    assert len(ist["texte"]) == 48 and ist["bloecke"] >= 1


def test_wache_gegenprobe_geaenderte_version_wird_gemeldet(tmp_path):
    """Punkt 10. Kopie der Eingaben in tmp_path mit je einer geänderten Version: die Abweichung
    wird gemeldet (und die unveränderte Kopie meldet nichts)."""
    m = _mod()
    md, txt = _echt()
    kopie = tmp_path / "kopie"
    for rel in ("backend/requirements-lock.txt", "backend/pyproject.toml",
                "frontend/package.json", "frontend/package-lock.json"):
        ziel = kopie / rel
        ziel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT_ROOT / rel, ziel)
    ist = m.bestand_ist(md, txt)
    assert m.abweichungen(m.bestand_soll(kopie), ist) == []

    # Python: fastapi
    lock = kopie / "backend" / "requirements-lock.txt"
    lock.write_text(lock.read_text(encoding="utf-8").replace("fastapi==", "fastapi==99.", 1), encoding="utf-8")
    meldungen = m.abweichungen(m.bestand_soll(kopie), ist)
    assert any("fastapi" in z for z in meldungen), meldungen
    # Die Meldung erscheint in beiden Abschnitten, in denen das Paket vorkommt (Übersicht und Texte).
    assert len([z for z in meldungen if "fastapi" in z]) == 2

    # npm: eine Version im Lockfile ändern (react)
    lock.write_text(lock.read_text(encoding="utf-8").replace("fastapi==99.", "fastapi=="), encoding="utf-8")
    npm_lock = kopie / "frontend" / "package-lock.json"
    daten = json.loads(npm_lock.read_text(encoding="utf-8"))
    daten["packages"]["node_modules/react"]["version"] = "0.0.1"
    npm_lock.write_text(json.dumps(daten), encoding="utf-8")
    meldungen = m.abweichungen(m.bestand_soll(kopie), ist)
    assert any("react " in z and "0.0.1" in z for z in meldungen), meldungen

    # Neues Paket im Lockfile, das die Seite nicht kennt
    npm_lock.write_text(json.dumps(json.loads((PROJECT_ROOT / "frontend/package-lock.json")
                                              .read_text(encoding="utf-8"))), encoding="utf-8")
    lock.write_text(lock.read_text(encoding="utf-8") + "neuespaket==1.0\n", encoding="utf-8")
    meldungen = m.abweichungen(m.bestand_soll(kopie), ist)
    assert any("neuespaket" in z for z in meldungen), meldungen
