"""Tests fuer `pipeline/release.py` (P2-51 Arbeitspaket U2b) -- das Freigabe-Werkzeug, das
`VERSION` anhebt, `CHANGELOG.md` fortschreibt, committet, taggt und nach origin pusht.

WEGWERF-REPO MIT BARE-"ORIGIN": `release.freigeben()` macht echte `git fetch`/`git push` --
das darf NIE gegen ein echtes GitHub laufen. Jeder Test baut deshalb ein eigenes Paar aus
Arbeits-Repo + lokalem bare-Repo als "origin" in `tmp_path` (Muster wie
test_kundenpaket.py::_scratch_repo, hier zusaetzlich mit Remote und initialem Push, weil
freigeben() Branch/Sync/Push braucht). `core.autocrlf false` wie dort (Lehre P2-50,
Windows-CI: sonst liefert `git show`/der committete Inhalt auf windows-latest CRLF statt LF).

CI UND PAKETPRUEFUNG PER MONKEYPATCH: `release._ci_lauf_status` und `kundenpaket.bauen` werden
in JEDEM Test ersetzt -- kein Test ruft echtes `gh`, keiner haengt von einem echten CI-Lauf ab.

App-Import bewusst NIE auf Modulebene (conftest.py-Konvention, s. dort)."""
import hashlib
import subprocess
from datetime import date
from pathlib import Path

import pytest

CHANGELOG_OK = """# Änderungen

Einleitung.

## Unveröffentlicht

- Testpunkt für die Freigabe.
"""

CHANGELOG_LEER = """# Änderungen

Einleitung.

## Unveröffentlicht

## 1.0.0 (01.01.2026)

- Alter Punkt.
"""

CHANGELOG_FORMFALSCH = CHANGELOG_OK + "\n## 1.1 (02.09.2026)\n\n- x\n"


# ── Hilfsfunktionen ─────────────────────────────────────────────────────────────────────────

def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _repo_mit_origin(tmp_path, *, version="1.0.0", changelog_text=CHANGELOG_OK):
    """Wegwerf-Arbeits-Repo + lokales bare-Repo als "origin": Branch main, ein Commit mit
    VERSION/CHANGELOG.md/README.md, main schon auf origin gepusht -- der synchrone
    Ausgangszustand, den freigeben() als Startpunkt erwartet. `git symbolic-ref HEAD` VOR dem
    ersten Commit statt `git init -b main`: funktioniert mit jeder Git-Version, unabhaengig vom
    konfigurierten Default-Branch-Namen (im Gegensatz zu `-b`, das eine neuere Git-Version
    braucht)."""
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True, capture_output=True)
    # HEAD des bare-Repos ebenfalls auf main: sonst zeigt er auf den Default-Branch des Rechners
    # (auf den CI-Runnern „master"), ein Klon davon bleibt leer und hat keinen Commit, auf den ein
    # Tag zeigen könnte (CI-Fund 28.09.2026, lokal unsichtbar).
    subprocess.run(["git", "--git-dir", str(bare), "symbolic-ref", "HEAD", "refs/heads/main"],
                    check=True, capture_output=True)

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "core.autocrlf", "false")
    (repo / "VERSION").write_text(f"{version}\n", encoding="utf-8", newline="\n")
    (repo / "CHANGELOG.md").write_text(changelog_text, encoding="utf-8", newline="\n")
    (repo / "README.md").write_text("# Test\n", encoding="utf-8", newline="\n")
    _git(repo, "add", "VERSION", "CHANGELOG.md", "README.md")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-q", "-u", "origin", "main")
    return repo


def _mock_ci_ok(monkeypatch):
    from pipeline import release
    monkeypatch.setattr(release, "_ci_lauf_status", lambda sha, root: ("completed", "success"))


def _mock_paket_ok(monkeypatch):
    from pipeline import kundenpaket as kp
    ergebnis = kp.Ergebnis(quelle="HEAD", anzahl_im_paket=3, anzahl_ausgeschlossen=1,
                            ersetzte_pfade=(), uebersprungen=(), funde=(), zip_pfad=None,
                            zip_groesse=None, uncommitted_hinweis=False,
                            version="1.0.0", freigabe=False, firmen_db_pfad=None)
    monkeypatch.setattr(kp, "bauen", lambda **kwargs: ergebnis)


def _happy(monkeypatch):
    """Beide teuren/externen Pruefungen gruen -- Baseline fuer Tests, die eine ANDERE Regel
    isoliert pruefen wollen (Muster wie test_kundenpaket.py: ein Fund pro Test)."""
    _mock_ci_ok(monkeypatch)
    _mock_paket_ok(monkeypatch)


# ── 1. Versionsstufen ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("stufe, aktuelle, erwartet", [
    ("patch", "1.0.0", "1.0.1"),
    ("minor", "1.0.5", "1.1.0"),
    ("major", "1.9.3", "2.0.0"),
])
def test_neue_version_stufen(stufe, aktuelle, erwartet):
    from pipeline import release

    assert release._neue_version(stufe, aktuelle) == erwartet


def test_neue_version_explizit_muss_groesser_sein():
    from pipeline import release

    assert release._neue_version("2.5.0", "1.0.0") == "2.5.0"
    with pytest.raises(release.ReleaseFehler):
        release._neue_version("1.0.0", "1.0.0")
    with pytest.raises(release.ReleaseFehler):
        release._neue_version("0.9.0", "1.0.0")


# ── 2. Jede Ablehnung einzeln ──────────────────────────────────────────────────────────────

def test_freigeben_lehnt_falschen_branch_ab(tmp_path, monkeypatch):
    from pipeline import release

    repo = _repo_mit_origin(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature")
    _happy(monkeypatch)

    rc = release.freigeben("1.1.0", projekt_root=repo, heute=date(2026, 9, 28))
    assert rc == 1


def test_freigeben_lehnt_unsauberen_arbeitsbaum_ab(tmp_path, monkeypatch, capsys):
    from pipeline import release

    repo = _repo_mit_origin(tmp_path)
    (repo / "README.md").write_text("# geaendert\n", encoding="utf-8")
    _happy(monkeypatch)

    rc = release.freigeben("1.1.0", projekt_root=repo, heute=date(2026, 9, 28))
    assert rc == 1
    assert "README.md" in capsys.readouterr().out


def test_freigeben_lehnt_nicht_synchron_ab(tmp_path, monkeypatch):
    from pipeline import release

    repo = _repo_mit_origin(tmp_path)
    # Ein weiterer, NICHT gepushter Commit -- HEAD laeuft origin/main davon.
    (repo / "README.md").write_text("# lokal weiter\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "lokal, nicht gepusht")
    _happy(monkeypatch)

    rc = release.freigeben("1.1.0", projekt_root=repo, heute=date(2026, 9, 28))
    assert rc == 1


def test_freigeben_lehnt_version_nicht_groesser_ab(tmp_path, monkeypatch):
    from pipeline import release

    repo = _repo_mit_origin(tmp_path, version="1.0.0")
    _happy(monkeypatch)

    rc = release.freigeben("1.0.0", projekt_root=repo, heute=date(2026, 9, 28))
    assert rc == 1


def test_freigeben_lehnt_tag_lokal_ab(tmp_path, monkeypatch):
    from pipeline import release

    repo = _repo_mit_origin(tmp_path)
    _git(repo, "tag", "v1.1.0")
    _happy(monkeypatch)

    rc = release.freigeben("1.1.0", projekt_root=repo, heute=date(2026, 9, 28))
    assert rc == 1


def test_freigeben_lehnt_tag_auf_origin_ab(tmp_path, monkeypatch):
    from pipeline import release

    repo = _repo_mit_origin(tmp_path)
    # Tag existiert NUR auf origin (ueber einen zweiten Klon angelegt) -- lokal in `repo` gibt
    # es ihn nicht, `git ls-remote --tags origin` muss ihn trotzdem finden.
    zweiter = tmp_path / "zweiter"
    subprocess.run(["git", "clone", "-q", str(tmp_path / "origin.git"), str(zweiter)],
                    check=True, capture_output=True)
    _git(zweiter, "config", "user.email", "test@example.com")
    _git(zweiter, "config", "user.name", "Test")
    _git(zweiter, "tag", "v1.1.0")
    _git(zweiter, "push", "-q", "origin", "v1.1.0")
    _happy(monkeypatch)

    rc = release.freigeben("1.1.0", projekt_root=repo, heute=date(2026, 9, 28))
    assert rc == 1


def test_freigeben_lehnt_changelog_leer_ab(tmp_path, monkeypatch):
    from pipeline import release

    repo = _repo_mit_origin(tmp_path, changelog_text=CHANGELOG_LEER)
    _happy(monkeypatch)

    rc = release.freigeben("1.1.0", projekt_root=repo, heute=date(2026, 9, 28))
    assert rc == 1


def test_freigeben_lehnt_changelog_formfalsch_ab(tmp_path, monkeypatch):
    from pipeline import release

    repo = _repo_mit_origin(tmp_path, changelog_text=CHANGELOG_FORMFALSCH)
    _happy(monkeypatch)

    rc = release.freigeben("1.1.0", projekt_root=repo, heute=date(2026, 9, 28))
    assert rc == 1


def test_freigeben_lehnt_ci_rot_ab(tmp_path, monkeypatch):
    from pipeline import release

    repo = _repo_mit_origin(tmp_path)
    monkeypatch.setattr(release, "_ci_lauf_status", lambda sha, root: ("completed", "failure"))
    _mock_paket_ok(monkeypatch)

    rc = release.freigeben("1.1.0", projekt_root=repo, heute=date(2026, 9, 28))
    assert rc == 1


def test_freigeben_lehnt_ci_laufend_ab(tmp_path, monkeypatch):
    from pipeline import release

    repo = _repo_mit_origin(tmp_path)
    monkeypatch.setattr(release, "_ci_lauf_status", lambda sha, root: ("in_progress", None))
    _mock_paket_ok(monkeypatch)

    rc = release.freigeben("1.1.0", projekt_root=repo, heute=date(2026, 9, 28))
    assert rc == 1


def test_freigeben_lehnt_ci_fehlt_ab(tmp_path, monkeypatch):
    from pipeline import release

    repo = _repo_mit_origin(tmp_path)
    monkeypatch.setattr(release, "_ci_lauf_status", lambda sha, root: ("fehlt", None))
    _mock_paket_ok(monkeypatch)

    rc = release.freigeben("1.1.0", projekt_root=repo, heute=date(2026, 9, 28))
    assert rc == 1


def test_freigeben_lehnt_paketfunde_ab(tmp_path, monkeypatch, capsys):
    from pipeline import kundenpaket as kp
    from pipeline import release

    repo = _repo_mit_origin(tmp_path)
    _mock_ci_ok(monkeypatch)
    fund = kp.Fund("docs/ANLEITUNG.md", 3, "Testregel", "Ausschnitt")
    ergebnis = kp.Ergebnis(quelle="HEAD", anzahl_im_paket=3, anzahl_ausgeschlossen=1,
                            ersetzte_pfade=(), uebersprungen=(), funde=(fund,), zip_pfad=None,
                            zip_groesse=None, uncommitted_hinweis=False,
                            version="1.0.0", freigabe=False, firmen_db_pfad=None)
    monkeypatch.setattr(kp, "bauen", lambda **kwargs: ergebnis)

    rc = release.freigeben("1.1.0", projekt_root=repo, heute=date(2026, 9, 28))
    assert rc == 1
    assert "Testregel" in capsys.readouterr().out


def test_freigeben_ohne_ci_pruefung_ueberspringt_rote_ci(tmp_path, monkeypatch):
    """--ohne-ci-pruefung ist die dokumentierte Ausnahme (Notfaelle/Tests) -- mit ihr darf
    eine sonst blockierende CI-Ablehnung nicht mehr greifen."""
    from pipeline import release

    repo = _repo_mit_origin(tmp_path)
    monkeypatch.setattr(release, "_ci_lauf_status", lambda sha, root: ("completed", "failure"))
    _mock_paket_ok(monkeypatch)

    rc = release.freigeben("1.1.0", probe=True, ohne_ci_pruefung=True,
                            projekt_root=repo, heute=date(2026, 9, 28))
    assert rc == 0


# ── 3. --probe aendert nichts ────────────────────────────────────────────────────────────

def test_freigeben_probe_aendert_nichts(tmp_path, monkeypatch, capsys):
    from pipeline import release

    repo = _repo_mit_origin(tmp_path)
    _happy(monkeypatch)

    vorher_version = (repo / "VERSION").read_text(encoding="utf-8")
    vorher_changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    vorher_head = _git(repo, "rev-parse", "HEAD").stdout.strip()

    rc = release.freigeben("1.1.0", probe=True, projekt_root=repo, heute=date(2026, 9, 28))
    assert rc == 0

    # Die Spec verlangt fuer --probe explizit, dass die geplanten Aenderungen angezeigt werden
    # (neue VERSION, der entstehende CHANGELOG-Abschnitt, Tag) -- nicht nur, dass nichts passiert.
    ausgabe = capsys.readouterr().out
    assert "1.1.0" in ausgabe
    assert "Testpunkt für die Freigabe." in ausgabe
    assert "v1.1.0" in ausgabe

    assert (repo / "VERSION").read_text(encoding="utf-8") == vorher_version
    assert (repo / "CHANGELOG.md").read_text(encoding="utf-8") == vorher_changelog
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == vorher_head
    assert "v1.1.0" not in _git(repo, "tag", "-l").stdout
    # Nichts wurde nach origin gepusht.
    bare = tmp_path / "origin.git"
    assert "v1.1.0" not in subprocess.run(
        ["git", "-C", str(bare), "tag", "-l"], check=True, capture_output=True, text=True
    ).stdout


# ── 4. Erfolgsfall ────────────────────────────────────────────────────────────────────────

def test_freigeben_erfolgsfall(tmp_path, monkeypatch, capsys):
    from pipeline import release

    repo = _repo_mit_origin(tmp_path)
    (repo / "unversioniert.txt").write_text("bleibt liegen\n", encoding="utf-8")
    _happy(monkeypatch)

    rc = release.freigeben("1.1.0", projekt_root=repo, heute=date(2026, 9, 28))
    assert rc == 0

    # VERSION und CHANGELOG.md richtig.
    assert (repo / "VERSION").read_text(encoding="utf-8") == "1.1.0\n"
    changelog_text = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## 1.1.0 (28.09.2026)" in changelog_text
    assert "- Testpunkt für die Freigabe." in changelog_text
    assert "## Unveröffentlicht" in changelog_text.split("## 1.1.0")[0]

    # Commit da, mit der erwarteten Nachricht.
    assert _git(repo, "log", "-1", "--format=%s").stdout.strip() == "Release 1.1.0"

    # Tag da UND annotiert (kein Lightweight-Tag).
    assert _git(repo, "cat-file", "-t", "v1.1.0").stdout.strip() == "tag"

    # main und Tag stehen auf origin.
    bare = tmp_path / "origin.git"
    zweige = subprocess.run(["git", "-C", str(bare), "branch", "--list", "main"],
                             check=True, capture_output=True, text=True).stdout
    assert "main" in zweige
    tags = subprocess.run(["git", "-C", str(bare), "tag", "-l", "v1.1.0"],
                           check=True, capture_output=True, text=True).stdout
    assert "v1.1.0" in tags
    origin_head = subprocess.run(["git", "-C", str(bare), "rev-parse", "main"],
                                  check=True, capture_output=True, text=True).stdout.strip()
    assert origin_head == _git(repo, "rev-parse", "HEAD").stdout.strip()

    # Unversionierte Datei bleibt unberuehrt UND wird als Hinweis ausgegeben.
    assert (repo / "unversioniert.txt").exists()
    ausgabe = capsys.readouterr().out
    assert "unversioniert.txt" in ausgabe

    # Schlussmeldung (P2-84): Freigabe im Entwicklungs-Repo, Weg ins oeffentliche Repo. Kein Link auf
    # die Actions-Seite und kein Hinweis auf `abholen`: im Entwicklungs-Repo entsteht kein Release.
    assert "Freigabe 1.1.0 im Entwicklungs-Repo: main und v1.1.0 stehen auf origin." in ausgabe
    assert ("Veröffentlichen: scripts/veroeffentlichen.sh --ziel <Arbeitskopie> --ref v1.1.0 "
            "(docs/RELEASE.md, Abschnitt Veröffentlichen).") in ausgabe
    assert "abholen" not in ausgabe
    assert "Actions" not in ausgabe and "github.com" not in ausgabe


def test_freigeben_mit_englischem_changelog_ohne_heute(tmp_path, monkeypatch):
    """Echtfall 06.11.2026: Die echte Freigabe ruft `freigeben` ohne `heute` auf. Der englische
    Zweig bekam dann `None` als Datum und brach ab, NACHDEM VERSION und CHANGELOG.md geschrieben
    waren. Die Tests gaben `heute` immer mit und hatten kein CHANGELOG.en.md, deshalb blieb das
    verborgen. Dieser Test laesst `heute` weg und hat beide Changelogs."""
    from pipeline import release, uebersetzung

    repo = _repo_mit_origin(tmp_path)
    (repo / "CHANGELOG.en.md").write_text(
        "# Changes\n\nIntro.\n\n## Unreleased\n\n- Test item for the release.\n",
        encoding="utf-8", newline="\n")
    monkeypatch.setattr(uebersetzung, "pruefen", lambda root, gruppen: [])

    def _bestaetigen(root, ziel):   # schreibt die Quellen-Datei, die freigeben() mitcommittet
        pfad = root / uebersetzung.QUELLEN_DATEI
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text('{"CHANGELOG.en.md": "x"}\n', encoding="utf-8")

    monkeypatch.setattr(uebersetzung, "bestaetigen", _bestaetigen)
    _git(repo, "add", "CHANGELOG.en.md")
    _git(repo, "commit", "-q", "-m", "en")
    _git(repo, "push", "-q", "origin", "main")
    _happy(monkeypatch)

    rc = release.freigeben("1.1.0", projekt_root=repo)
    assert rc == 0

    kopf = f"## 1.1.0 ({date.today().strftime('%d.%m.%Y')})"
    assert kopf in (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    en = (repo / "CHANGELOG.en.md").read_text(encoding="utf-8")
    assert kopf in en and "- Test item for the release." in en
    assert "CHANGELOG.en.md" in _git(repo, "show", "--name-only", "--format=", "HEAD").stdout
    assert _git(repo, "status", "--porcelain").stdout.strip() == ""


# ── 5. Firmennamen-Regel nur, wenn die Datenbank lokal vorhanden ist ──────────────────────

def test_pruefe_paket_reicht_firmen_db_nur_wenn_datei_vorhanden(tmp_path, monkeypatch):
    from pipeline import kundenpaket as kp
    from pipeline import release

    # conftest.py setzt BMS_DATA_DIR global auf ein session-weites tmp-Verzeichnis (Isolation
    # gegen die echte DB, s. dortiger Docstring) -- fuer DIESEN Test soll _firmen_db_pfad()
    # aber auf projekt_root/data zurueckfallen, wie es ohne gesetzte Variable waere.
    monkeypatch.delenv("BMS_DATA_DIR", raising=False)

    repo = _repo_mit_origin(tmp_path)
    ergebnis = kp.Ergebnis(quelle="HEAD", anzahl_im_paket=1, anzahl_ausgeschlossen=0,
                            ersetzte_pfade=(), uebersprungen=(), funde=(), zip_pfad=None,
                            zip_groesse=None, uncommitted_hinweis=False,
                            version="1.0.0", freigabe=False, firmen_db_pfad=None)
    erhalten = {}

    def fake_bauen(*, arbeitsbaum, ref, ziel, nur_pruefen, projekt_root, firmen_db=None):
        erhalten["firmen_db"] = firmen_db
        return ergebnis

    monkeypatch.setattr(kp, "bauen", fake_bauen)

    # Ohne data/bewerbung.sqlite (Normalfall in einem frischen Wegwerf-Repo/der CI) --
    # firmen_db wird NICHT gereicht, weil die Datei fehlt.
    release._pruefe_paket(repo)
    assert erhalten["firmen_db"] is None

    # Mit einer (Dummy-)Datenbankdatei wird der Pfad durchgereicht -- geoeffnet wird sie NICHT
    # von release.py (das gehoert kundenpaket.bauen, hier ja ohnehin nur ein Fake).
    (repo / "data").mkdir()
    (repo / "data" / "bewerbung.sqlite").write_bytes(b"keine echte sqlite-Datei, nur der Pfad zaehlt")
    release._pruefe_paket(repo)
    assert erhalten["firmen_db"] == repo / "data" / "bewerbung.sqlite"


# ── 6. notizen ────────────────────────────────────────────────────────────────────────────

def test_notizen_gibt_abschnitt_aus(tmp_path, capsys):
    from pipeline import release

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CHANGELOG.md").write_text(
        "# Änderungen\n\n## Unveröffentlicht\n\n## 1.0.0 (01.09.2026)\n\n- Erste Version.\n",
        encoding="utf-8")

    rc = release.notizen("1.0.0", projekt_root=repo)
    assert rc == 0
    assert capsys.readouterr().out.strip() == "- Erste Version."


def test_notizen_fehlende_version(tmp_path):
    from pipeline import release

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CHANGELOG.md").write_text("# Änderungen\n\n## Unveröffentlicht\n\n- x\n",
                                        encoding="utf-8")

    rc = release.notizen("9.9.9", projekt_root=repo)
    assert rc == 1


# ── 7. abholen ────────────────────────────────────────────────────────────────────────────

def test_abholen_erfolg_prueft_pruefsumme(tmp_path, monkeypatch):
    from pipeline import release

    repo = tmp_path / "repo"
    repo.mkdir()
    ziel = tmp_path / "kunde"

    def fake_gh(args, projekt_root):
        zielordner = Path(args[args.index("--dir") + 1])
        inhalt = b"zip-inhalt (Test)"
        (zielordner / "BMS_1.0.0.zip").write_bytes(inhalt)
        digest = hashlib.sha256(inhalt).hexdigest()
        (zielordner / "BMS_1.0.0.zip.sha256").write_text(f"{digest}  BMS_1.0.0.zip\n",
                                                           encoding="utf-8")

    monkeypatch.setattr(release, "_gh", fake_gh)
    rc = release.abholen("1.0.0", ziel=str(ziel), projekt_root=repo)
    assert rc == 0
    assert (ziel / "BMS_1.0.0.zip").exists()


def test_abholen_laedt_aus_dem_oeffentlichen_repo(tmp_path, monkeypatch):
    """Das Release gibt es nur im oeffentlichen Repo (P2-84): `gh release download` bekommt
    `--repo <OEFFENTLICHES_REPO>`, sonst suchte es in `origin`, dem Entwicklungs-Repo."""
    from pipeline import personendaten, release

    repo = tmp_path / "repo"
    repo.mkdir()
    ziel = tmp_path / "kunde"
    aufrufe = []

    def fake_gh(args, projekt_root):
        aufrufe.append(list(args))
        zielordner = Path(args[args.index("--dir") + 1])
        inhalt = b"zip-inhalt (Test)"
        (zielordner / "BMS_2.0.0.zip").write_bytes(inhalt)
        (zielordner / "BMS_2.0.0.zip.sha256").write_text(
            f"{hashlib.sha256(inhalt).hexdigest()}  BMS_2.0.0.zip\n", encoding="utf-8")

    monkeypatch.setattr(release, "_gh", fake_gh)
    assert release.abholen("2.0.0", ziel=str(ziel), projekt_root=repo) == 0

    assert len(aufrufe) == 1
    args = aufrufe[0]
    assert args[:3] == ["release", "download", "v2.0.0"]
    assert args[args.index("--repo") + 1] == personendaten.OEFFENTLICHES_REPO
    assert args[args.index("--dir") + 1] == str(ziel)


def test_abholen_meldet_fehler_von_gh(tmp_path, monkeypatch, capsys):
    from pipeline import release

    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_gh(args, projekt_root):
        raise release.ReleaseFehler("gh release download v9.9.9 fehlgeschlagen: release not found")

    monkeypatch.setattr(release, "_gh", fake_gh)
    assert release.abholen("9.9.9", ziel=str(tmp_path / "kunde"), projekt_root=repo) == 1
    assert "release not found" in capsys.readouterr().out


def test_abholen_bricht_bei_falscher_pruefsumme_ab(tmp_path, monkeypatch):
    from pipeline import release

    repo = tmp_path / "repo"
    repo.mkdir()
    ziel = tmp_path / "kunde"

    def fake_gh(args, projekt_root):
        zielordner = Path(args[args.index("--dir") + 1])
        (zielordner / "BMS_1.0.0.zip").write_bytes(b"zip-inhalt")
        (zielordner / "BMS_1.0.0.zip.sha256").write_text(
            "0" * 64 + "  BMS_1.0.0.zip\n", encoding="utf-8")

    monkeypatch.setattr(release, "_gh", fake_gh)
    rc = release.abholen("1.0.0", ziel=str(ziel), projekt_root=repo)
    assert rc == 1
