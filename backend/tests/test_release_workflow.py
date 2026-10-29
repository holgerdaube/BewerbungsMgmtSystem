"""Tests für `.github/workflows/release.yml` (P2-84, Paket C1): Releases entstehen nur im öffentlichen Repo,
und das Release trägt die beiden Installationsanleitungen.

Reine Textprüfung der Workflow-Datei, kein Netzwerk, kein `gh`, kein YAML-Paket (die CI installiert nur die
Laufzeit-Abhängigkeiten). Die Datei wird zeilenweise in ihre Jobs und Schritte zerlegt; das genügt, weil
`release.yml` eine feste, flache Form hat.

NUR ERFUNDENE DATEN, KEINE ECHTEN KONTEN: Das Repo kommt aus `personendaten.OEFFENTLICHES_REPO`, nicht aus
einem Literal in dieser Datei. Diese Datei wird mit dem öffentlichen Baum geprüft.

App-/Pipeline-Importe nie auf Modulebene (conftest-Regel), nur über die Fixture `repo`."""
import re
from pathlib import Path

import pytest

PROJEKT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = PROJEKT_ROOT / ".github" / "workflows" / "release.yml"
ANLEITUNGEN = ("BMS_Install_MAC.md", "BMS_Install_Windows.md")


@pytest.fixture
def repo():
    from pipeline import personendaten
    return personendaten.OEFFENTLICHES_REPO


@pytest.fixture
def text():
    return WORKFLOW.read_text(encoding="utf-8")


def _job(text, name):
    """Der Textblock eines Jobs unter `jobs:` (zwei Leerzeichen Einrückung) bis zum nächsten Job."""
    treffer = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  \S|\Z)", text, re.MULTILINE | re.DOTALL)
    assert treffer, f"Job {name!r} fehlt in release.yml"
    return treffer.group(1)


def _schritt(text, name):
    """Der Textblock eines Schritts (`- name: …`, sechs Leerzeichen Einrückung) bis zum nächsten Schritt."""
    treffer = re.search(rf"^      - name: {re.escape(name)}\n(.*?)(?=^      - |\Z)", text,
                        re.MULTILINE | re.DOTALL)
    assert treffer, f"Schritt {name!r} fehlt in release.yml"
    return treffer.group(1)


def _bedingung(job_text):
    """Die `if:`-Zeile des Jobs selbst (vier Leerzeichen Einrückung, nicht die eines Schritts)."""
    zeilen = re.findall(r"^    if: (.+)$", job_text, re.MULTILINE)
    assert len(zeilen) == 1, "der Job braucht genau eine eigene if-Bedingung"
    return zeilen[0].strip()


@pytest.mark.parametrize("job", ["tests", "paket"])
def test_job_laeuft_nur_im_oeffentlichen_repo_oder_beim_probebau(text, repo, job):
    """Im Entwicklungs-Repo entsteht kein Release (Leitentscheidung 2): ein Tag-Push dort startet
    weder den Testlauf noch den Paketbau. Der Probebau (`workflow_dispatch`) läuft in jedem Repo."""
    erwartet = f"github.event_name == 'workflow_dispatch' || github.repository == '{repo}'"
    assert _bedingung(_job(text, job)) == erwartet


@pytest.mark.parametrize("job", ["tests", "paket"])
def test_bedingung_nennt_genau_ein_repo_und_zwar_das_oeffentliche(text, repo, job):
    namen = re.findall(r"github\.repository\s*==\s*'([^']*)'", _job(text, job))
    assert namen == [repo]


def test_paket_wartet_auf_die_tests(text):
    """Ein übersprungener `tests`-Job überspringt über `needs` auch `paket`; fiele `needs` weg, bliebe die
    Bedingung am Paketjob die einzige Sperre."""
    assert re.search(r"^    needs: tests$", _job(text, "paket"), re.MULTILINE)


def test_release_schritt_haengt_beide_anleitungen_an(text):
    schritt = _schritt(text, "GitHub Release veroeffentlichen")
    # Zeilenumbrüche mit „\“ zusammenziehen: der Befehl steht über mehrere Zeilen
    befehl = re.sub(r"\\\n\s*", " ", schritt)
    release_zeilen = [z for z in befehl.splitlines() if "gh release create" in z]
    assert len(release_zeilen) == 1
    for anleitung in ANLEITUNGEN:
        assert anleitung in release_zeilen[0], f"{anleitung} hängt nicht am Release"
    assert "*.zip" in release_zeilen[0] and "*.sha256" in release_zeilen[0]
    assert "--verify-tag" in release_zeilen[0]


def test_release_schritt_bricht_ab_wenn_eine_anleitung_fehlt(text):
    schritt = _schritt(text, "GitHub Release veroeffentlichen")
    pruefung = schritt.split("gh release create")[0]
    for anleitung in ANLEITUNGEN:
        assert anleitung in pruefung, f"{anleitung} wird vor dem Release nicht geprüft"
    assert "exit 1" in pruefung


def test_release_schritt_laeuft_nur_beim_tag_push(text):
    """Der Probebau legt kein Release an, auch nicht mit den Anleitungen."""
    assert re.search(r"^        if: github\.event_name == 'push'$",
                     _schritt(text, "GitHub Release veroeffentlichen"), re.MULTILINE)


@pytest.mark.parametrize("anleitung", ANLEITUNGEN)
def test_anleitungen_liegen_im_projekt_root(anleitung):
    datei = PROJEKT_ROOT / anleitung
    assert datei.is_file(), f"{anleitung} fehlt im Projekt-Root; der Checkout in release.yml fände sie nicht"
    assert datei.stat().st_size > 0
