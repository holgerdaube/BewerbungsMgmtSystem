"""P2-91: Die englischen Fassungen der Dokumente bleiben aktuell. Anwender-Doku und Rechtstexte prüft jeder Lauf, die
Technik-Doku die Freigabe. Eine Änderung an der deutschen Fassung: englische Datei nachziehen, dann
`scripts/uebersetzung.sh --bestaetigen <Ziel>`.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_anwender_doku_und_rechtstexte_sind_aktuell():
    from pipeline import uebersetzung
    funde = uebersetzung.pruefen(ROOT, ("anwender", "recht"))
    assert not funde, "\n".join(funde)


def test_alle_paare_haben_eine_quelle():
    from pipeline import uebersetzung
    for p in uebersetzung.PAARE:
        assert (ROOT / p.quelle).is_file(), p.quelle


def _umgebung(tmp_path):
    from pipeline import uebersetzung
    (tmp_path / "docs" / "en").mkdir(parents=True)
    quelle = tmp_path / "docs" / "ANLEITUNG.md"
    ziel = tmp_path / "docs" / "en" / "ANLEITUNG.md"
    quelle.write_text("# Titel\n\n## Abschnitt\n\n```sh\nls -la\n```\n\nhttps://example.com/x\n", encoding="utf-8")
    ziel.write_text("# Title\n\n## Section\n\n```sh\nls -la\n```\n\nhttps://example.com/x\n", encoding="utf-8")
    uebersetzung.bestaetigen(tmp_path, "docs/en/ANLEITUNG.md")
    return uebersetzung, quelle, ziel


def _funde(u, root):
    return [f for f in u.pruefen(root, ("anwender",)) if "ANLEITUNG.md" in f and "ANLEITUNG_" not in f]


def test_bestaetigt_und_gleich_ist_sauber(tmp_path):
    u, _q, _z = _umgebung(tmp_path)
    assert not _funde(u, tmp_path)


def test_geaenderte_quelle_macht_die_uebersetzung_veraltet(tmp_path):
    u, q, _z = _umgebung(tmp_path)
    q.write_text(q.read_text(encoding="utf-8") + "\nNeuer Satz.\n", encoding="utf-8")
    assert any("veraltet" in f for f in _funde(u, tmp_path))


@pytest.mark.parametrize("alt,neu", [("## Section", "### Section"), ("https://example.com/x", "https://example.com/y")])
def test_struktur_faellt_auf(tmp_path, alt, neu):
    u, _q, z = _umgebung(tmp_path)
    z.write_text(z.read_text(encoding="utf-8").replace(alt, neu), encoding="utf-8")
    assert _funde(u, tmp_path)


def test_fehlender_befehlsblock_faellt_auf(tmp_path):
    u, _q, z = _umgebung(tmp_path)
    z.write_text("# Title\n\n## Section\n\nhttps://example.com/x\n", encoding="utf-8")
    assert any("Befehlsblöcke" in f for f in _funde(u, tmp_path))


def test_changelog_form_gilt_auch_fuer_englisch():
    from pipeline import changelog
    text = (ROOT / "CHANGELOG.en.md").read_text(encoding="utf-8")
    assert not changelog.pruefen(text)
    versionen = lambda t: [a.version for a in changelog.abschnitte(t)]  # noqa: E731
    assert versionen(text) == versionen((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))


def test_freigabe_behaelt_den_englischen_abschnittsnamen():
    from datetime import date
    from pipeline import changelog
    neu = changelog.freigeben("# Changes\n\n## Unreleased\n\n- Point\n\n## 1.0.0 (01.01.2026)\n\n- Old\n", "1.1.0", date(2026, 2, 1))
    assert "## Unreleased\n\n## 1.1.0 (01.02.2026)\n\n- Point" in neu
