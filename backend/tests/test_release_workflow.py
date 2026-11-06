"""Tests für `.github/workflows/release.yml` (P2-84, Paket C1): Releases entstehen nur im öffentlichen Repo,
und das Release trägt die beiden Installationsanleitungen.

Textprüfung der Workflow-Datei, kein Netzwerk, kein `gh`, kein YAML-Paket (die CI installiert nur die
Laufzeit-Abhängigkeiten). Die beiden Schritte für `BMS_latest.zip` werden zusätzlich mit bash nachgestellt.
Die Datei wird zeilenweise in ihre Jobs und Schritte zerlegt; das genügt, weil
`release.yml` eine feste, flache Form hat.

NUR ERFUNDENE DATEN, KEINE ECHTEN KONTEN: Das Repo kommt aus `personendaten.OEFFENTLICHES_REPO`, nicht aus
einem Literal in dieser Datei. Diese Datei wird mit dem öffentlichen Baum geprüft.

App-/Pipeline-Importe nie auf Modulebene (conftest-Regel), nur über die Fixture `repo`."""
import hashlib
import os
import re
import shutil
import subprocess
import sys
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


# ── BMS_latest.zip: fester Name für den Download-Link der Produktseite ────────────────────────────────

def _run_block(schritt_text):
    """Der Inhalt von `run: |` eines Schritts, ohne die Einrückung (zehn Leerzeichen)."""
    teile = schritt_text.split("        run: |\n", 1)
    assert len(teile) == 2, "Schritt ohne `run: |`"
    zeilen = []
    for zeile in teile[1].splitlines():
        if zeile.strip() and not zeile.startswith("          "):
            break
        zeilen.append(zeile[10:])
    return "\n".join(zeilen).strip() + "\n"


def test_latest_schritt_steht_vor_der_pruefsumme(text):
    """Nur so erzeugt die Schleife in „Pruefsumme“ auch `BMS_latest.zip.sha256`."""
    assert text.index("- name: Fester Name fuer die Produktseite") < text.index("- name: Pruefsumme")


def test_latest_schritt_laeuft_nur_beim_tag_push(text):
    """Der Probebau heißt `BMS_<Version>_<Datum>_<SHA>.zip`; eine Kopie dort hätte kein Original."""
    assert re.search(r"^        if: github\.event_name == 'push'$",
                     _schritt(text, "Fester Name fuer die Produktseite"), re.MULTILINE)


def test_latest_schritt_kopiert_das_versionierte_zip(text):
    befehl = _run_block(_schritt(text, "Fester Name fuer die Produktseite"))
    assert 'cp "BMS_$tag.zip" BMS_latest.zip' in befehl
    assert "exit 1" in befehl.split("cp ")[0], "fehlt das Original, bricht der Schritt nicht ab"


def test_release_haengt_latest_ueber_die_muster_an(text):
    """`gh release create` nimmt `paket/*.zip` und `paket/*.sha256`; ein eigener Eintrag ist nicht nötig, aber
    die Muster dürfen nicht auf `BMS_<Version>` eingeengt werden."""
    schritt = re.sub(r"\\\n\s*", " ", _schritt(text, "GitHub Release veroeffentlichen"))
    zeile = next(z for z in schritt.splitlines() if "gh release create" in z)
    assert '"${{ runner.temp }}"/paket/*.zip' in zeile
    assert '"${{ runner.temp }}"/paket/*.sha256' in zeile


@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash") or not shutil.which("sha256sum"),
                    reason="braucht bash und sha256sum (läuft in der CI unter Ubuntu und auf dem Mac)")
def test_latest_und_pruefsumme_nachgestellt(text, tmp_path):
    """Beide Schritte so ausführen, wie die CI es tut: Paketordner mit einem Test-ZIP, `GITHUB_REF` eines Tags."""
    inhalt = b"zip-inhalt (Test)"
    (tmp_path / "BMS_9.8.7.zip").write_bytes(inhalt)
    umgebung = {"PATH": os.environ.get("PATH", ""), "GITHUB_REF": "refs/tags/v9.8.7"}
    for name in ("Fester Name fuer die Produktseite", "Pruefsumme"):
        lauf = subprocess.run(["bash", "-e", "-c", _run_block(_schritt(text, name))], cwd=tmp_path,
                              env=umgebung, capture_output=True, text=True)
        assert lauf.returncode == 0, f"{name}: {lauf.stderr}"

    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "BMS_9.8.7.zip", "BMS_9.8.7.zip.sha256", "BMS_latest.zip", "BMS_latest.zip.sha256"]
    assert (tmp_path / "BMS_latest.zip").read_bytes() == inhalt
    digest = hashlib.sha256(inhalt).hexdigest()
    assert (tmp_path / "BMS_latest.zip.sha256").read_text() == f"{digest}  BMS_latest.zip\n"
    assert (tmp_path / "BMS_9.8.7.zip.sha256").read_text() == f"{digest}  BMS_9.8.7.zip\n"
    pruefung = subprocess.run(["sha256sum", "-c", "BMS_latest.zip.sha256"], cwd=tmp_path, env=umgebung,
                              capture_output=True, text=True)
    assert pruefung.returncode == 0, pruefung.stdout + pruefung.stderr


@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"),
                    reason="braucht bash (läuft in der CI unter Ubuntu und auf dem Mac)")
def test_latest_schritt_bricht_ohne_original_ab(text, tmp_path):
    """Passt das gebaute ZIP nicht zum Tag, entsteht kein Release mit einem falschen BMS_latest.zip."""
    (tmp_path / "BMS_9.8.6.zip").write_bytes(b"alt")
    lauf = subprocess.run(["bash", "-e", "-c", _run_block(_schritt(text, "Fester Name fuer die Produktseite"))],
                          cwd=tmp_path, env={"PATH": os.environ.get("PATH", ""), "GITHUB_REF": "refs/tags/v9.8.7"},
                          capture_output=True, text=True)
    assert lauf.returncode != 0
    assert "BMS_9.8.7.zip fehlt" in lauf.stderr
    assert not (tmp_path / "BMS_latest.zip").exists()
