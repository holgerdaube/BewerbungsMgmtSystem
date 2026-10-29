"""P2-51 (V1 + V5) — `app/version.py` (Versionsauskunft) und `GET /api/version`.

Deckt ab:
  1. Installationsart „paket“: `bms_manifest.json` in einem `tmp_path`-Root, Werte kommen von
     dort, `commit` auf 7 Zeichen gekürzt, `aenderungen` aus dem CHANGELOG-Abschnitt der
     installierten Version.
  2. Installationsart „git“ in einem Wegwerf-Repo: mit Tag (sauber -> `freigabe`, „0 Commits
     nach …“), einen Commit weiter UND dirty (`freigabe` False, „… mit lokalen Änderungen“),
     ganz ohne Tag („noch keine Freigabe“).
  3. Installationsart „unbekannt“ (weder Manifest noch `.git`).
  4. `aenderungen`: `git` nimmt „Unveröffentlicht“, falls nicht leer, sonst den Abschnitt der
     `VERSION`-Version.
  5. `letztes_update`: der neueste Bericht mit `ergebnis == "ok"` ohne `zurueckgenommen_am` —
     ein „zurueckgerollt“-Bericht und ein zurückgenommener „ok“-Bericht werden übersprungen.
  6. `GET /api/version` antwortet 200 — auch wenn jeder Git-Aufruf fehlschlägt (kein 500, V5).

Wegwerf-Repos nach dem Muster `test_kundenpaket.py::_scratch_repo` (`core.autocrlf false` —
Lehre 27.09.2026/CI-Fund: sonst liefert `git`/`git archive` unter der Windows-CI CRLF statt LF).
App-Module werden ausschließlich innerhalb der Testfunktionen importiert (Konvention aus
conftest.py)."""
import json
import subprocess


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _scratch_repo(tmp_path, name="repo"):
    """Winziges Wegwerf-Repo mit einem Commit (Muster `test_kundenpaket.py::_scratch_repo`)."""
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "core.autocrlf", "false")
    (repo / "VERSION").write_text("1.0.0\n", encoding="utf-8", newline="\n")
    (repo / "CHANGELOG.md").write_text(
        "# Änderungen\n\n## Unveröffentlicht\n\n## 1.0.0 (28.09.2026)\n\n- Erste Version.\n",
        encoding="utf-8", newline="\n",
    )
    _git(repo, "add", "VERSION", "CHANGELOG.md")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


CHANGELOG_MIT_OFFENEM_PUNKT = (
    "# Änderungen\n\n## Unveröffentlicht\n\n- Neuer Punkt.\n\n"
    "## 1.0.0 (28.09.2026)\n\n- Erste Version.\n"
)


# ── 1. Installationsart „paket" ─────────────────────────────────────────────────────────────
def test_paket_liest_werte_aus_manifest_und_kuerzt_commit(tmp_path):
    from app.version import version_info

    root = tmp_path / "paket"
    root.mkdir()
    voller_commit = "abc1234567890abc1234567890abc1234567890"
    (root / "bms_manifest.json").write_text(json.dumps({
        "version": "1.2.0", "freigabe": True, "commit": voller_commit,
        "commit_datum": "2026-09-28", "format": 1, "produkt": "x", "vorschau": False,
        "anpassbar": [], "dateien": {},
    }), encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Änderungen\n\n## Unveröffentlicht\n\n## 1.2.0 (28.09.2026)\n\n- Punkt A.\n"
        "\n## 1.0.0 (01.09.2026)\n\n- Alt.\n",
        encoding="utf-8",
    )

    info = version_info(root=root, data_dir=root / "data")

    assert info["installation"] == "paket"
    assert info["version"] == "1.2.0"
    assert info["freigabe"] is True
    assert info["commit"] == voller_commit[:7]
    assert len(info["commit"]) == 7
    assert info["datum"] == "2026-09-28"
    assert info["aenderungen"] == "- Punkt A."
    assert info["betriebssystem"] in ("mac", "windows", "linux")
    assert info["installationsordner"] == str(root)


def test_paket_ohne_freigabe_meldet_freigabe_false(tmp_path):
    from app.version import version_info

    root = tmp_path / "vorschau"
    root.mkdir()
    (root / "bms_manifest.json").write_text(json.dumps({
        "version": "1.3.0", "freigabe": False, "commit": "f" * 40, "commit_datum": "2026-09-28",
        "format": 1, "produkt": "x", "vorschau": True, "anpassbar": [], "dateien": {},
    }), encoding="utf-8")

    info = version_info(root=root, data_dir=root / "data")

    assert info["installation"] == "paket"
    assert info["freigabe"] is False


# ── 2. Installationsart „git" ────────────────────────────────────────────────────────────────
def test_git_installation_auf_dem_tag_ist_freigabe_und_zeigt_0_commits(tmp_path):
    from app.version import version_info

    repo = _scratch_repo(tmp_path)
    _git(repo, "tag", "v1.0.0")

    info = version_info(root=repo, data_dir=repo / "data")

    assert info["installation"] == "git"
    assert info["version"] == "1.0.0"          # aus VERSION, nicht aus dem Tag
    assert info["freigabe"] is True
    assert info["entwicklungsstand"] == "0 Commits nach 1.0.0"
    assert info["commit"]
    assert info["datum"]


def test_git_installation_einen_commit_weiter_und_dirty_ist_keine_freigabe(tmp_path):
    from app.version import version_info

    repo = _scratch_repo(tmp_path)
    _git(repo, "tag", "v1.0.0")
    (repo / "VERSION").write_text("1.1.0\n", encoding="utf-8", newline="\n")
    _git(repo, "add", "VERSION")
    _git(repo, "commit", "-q", "-m", "bump")
    (repo / "CHANGELOG.md").write_text("schmutzig", encoding="utf-8")   # macht den Baum dirty

    info = version_info(root=repo, data_dir=repo / "data")

    assert info["freigabe"] is False
    assert info["entwicklungsstand"] == "1 Commit nach 1.0.0, mit lokalen Änderungen"
    assert info["version"] == "1.1.0"


def test_git_installation_ohne_jeden_tag_meldet_noch_keine_freigabe(tmp_path):
    from app.version import version_info

    repo = _scratch_repo(tmp_path, name="ohne_tag")

    info = version_info(root=repo, data_dir=repo / "data")

    assert info["installation"] == "git"
    assert info["freigabe"] is False
    assert info["entwicklungsstand"] == "noch keine Freigabe"


# ── 3. Installationsart „unbekannt" ─────────────────────────────────────────────────────────
def test_unbekannte_installation_ohne_manifest_und_git(tmp_path):
    from app.version import version_info

    root = tmp_path / "nackt"
    root.mkdir()

    info = version_info(root=root, data_dir=root / "data")

    assert info["installation"] == "unbekannt"
    assert info["version"] is None
    assert info["freigabe"] is False
    assert info["commit"] is None
    assert info["entwicklungsstand"] is None
    assert info["aenderungen"] is None


def test_unbekannte_installation_liest_version_datei_falls_vorhanden(tmp_path):
    from app.version import version_info, version_text

    root = tmp_path / "nur_version"
    root.mkdir()
    (root / "VERSION").write_text("2.0.0\n", encoding="utf-8")

    info = version_info(root=root, data_dir=root / "data")

    assert info["installation"] == "unbekannt"
    assert info["version"] == "2.0.0"
    assert version_text(root=root) == "2.0.0"


def test_version_text_faellt_ohne_version_datei_auf_0_0_0_zurueck(tmp_path):
    from app.version import version_text

    assert version_text(root=tmp_path) == "0.0.0"


# ── 4. aenderungen bei git: Unveröffentlicht zuerst, sonst VERSION-Abschnitt ────────────────
def test_git_aenderungen_nimmt_unveroeffentlicht_wenn_nicht_leer(tmp_path):
    from app.version import version_info

    repo = _scratch_repo(tmp_path)
    (repo / "CHANGELOG.md").write_text(CHANGELOG_MIT_OFFENEM_PUNKT, encoding="utf-8", newline="\n")
    _git(repo, "add", "CHANGELOG.md")
    _git(repo, "commit", "-q", "-m", "changelog")

    info = version_info(root=repo, data_dir=repo / "data")

    assert info["aenderungen"] == "- Neuer Punkt."


def test_git_aenderungen_faellt_auf_version_abschnitt_zurueck_wenn_unveroeffentlicht_leer(tmp_path):
    from app.version import version_info

    repo = _scratch_repo(tmp_path)   # CHANGELOG hat ein LEERES "## Unveröffentlicht"

    info = version_info(root=repo, data_dir=repo / "data")

    assert info["aenderungen"] == "- Erste Version."


# ── 5. letztes_update ────────────────────────────────────────────────────────────────────────
def _bericht_schreiben(data_dir, ordner, *, von, nach, ergebnis="ok", zeitpunkt=None,
                       zurueckgenommen_am=None):
    ziel = data_dir / "updates" / ordner
    ziel.mkdir(parents=True)
    (ziel / "bericht.json").write_text(json.dumps({
        "format": 1, "zeitpunkt": zeitpunkt or "2026-01-01T00:00:00+01:00",
        "von": von, "nach": nach, "ergebnis": ergebnis,
        "zurueckgenommen_am": zurueckgenommen_am,
        "neu": [], "geaendert": [], "entfernt": [],
        "lokal_geaendert_gesichert": [], "anpassbar_behalten": [], "hinweise": [],
    }), encoding="utf-8")


def test_letztes_update_findet_neuesten_ok_bericht_und_ueberspringt_zurueckgerollte(tmp_path):
    from app.version import version_info

    root = tmp_path / "paket"
    root.mkdir()
    data_dir = root / "data"
    _bericht_schreiben(data_dir, "2026-09-01_090000_1.0.0_zu_1.1.0",
                       von="1.0.0", nach="1.1.0", zeitpunkt="2026-09-01T09:00:00+02:00")
    _bericht_schreiben(data_dir, "2026-10-15_091200_1.1.0_zu_1.2.0",
                       von="1.1.0", nach="1.2.0", zeitpunkt="2026-10-15T09:12:00+02:00")
    _bericht_schreiben(data_dir, "2026-11-01_000000_1.2.0_zu_1.3.0",
                       von="1.2.0", nach="1.3.0", ergebnis="zurueckgerollt")

    info = version_info(root=root, data_dir=data_dir)

    assert info["letztes_update"] == {"zeitpunkt": "2026-10-15T09:12:00+02:00",
                                       "von": "1.1.0", "nach": "1.2.0"}


def test_letztes_update_ueberspringt_zurueckgenommenen_bericht(tmp_path):
    from app.version import version_info

    root = tmp_path / "paket"
    root.mkdir()
    data_dir = root / "data"
    _bericht_schreiben(data_dir, "2026-09-01_090000_1.0.0_zu_1.1.0",
                       von="1.0.0", nach="1.1.0", zeitpunkt="2026-09-01T09:00:00+02:00")
    _bericht_schreiben(data_dir, "2026-10-15_091200_1.1.0_zu_1.2.0",
                       von="1.1.0", nach="1.2.0", zeitpunkt="2026-10-15T09:12:00+02:00",
                       zurueckgenommen_am="2026-10-16T08:00:00+02:00")

    info = version_info(root=root, data_dir=data_dir)

    assert info["letztes_update"] == {"zeitpunkt": "2026-09-01T09:00:00+02:00",
                                       "von": "1.0.0", "nach": "1.1.0"}


def test_letztes_update_ist_none_ohne_updates_ordner(tmp_path):
    from app.version import version_info

    root = tmp_path / "frisch"
    root.mkdir()

    info = version_info(root=root, data_dir=root / "data")

    assert info["letztes_update"] is None


# ── 6. Endpunkt: 200, auch wenn jeder Git-Aufruf fehlschlägt ────────────────────────────────
def test_endpunkt_liefert_200(client):
    r = client.get("/api/version")

    assert r.status_code == 200
    body = r.json()
    assert body["installation"] in ("paket", "git", "unbekannt")
    assert body["betriebssystem"] in ("mac", "windows", "linux")


def test_endpunkt_liefert_200_auch_wenn_git_fehlschlaegt(client, monkeypatch):
    """V5: „jeder Fehler ergibt null-Felder, nie einen 500" — hier am HTTP-Endpunkt geprüft,
    nicht nur an `version_info()` direkt: ein fehlendes/kaputtes `git` darf die
    Einstellungen-Seite nie mit einem 500 lahmlegen."""
    from app import version as V

    def _kaputt(*args, **kwargs):
        raise FileNotFoundError("git ist in diesem Test absichtlich nicht auffindbar")

    monkeypatch.setattr(V.subprocess, "run", _kaputt)

    r = client.get("/api/version")

    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_version_info_git_aufruf_mit_timeout_ergibt_none_statt_ausnahme(tmp_path, monkeypatch):
    from app import version as V

    # Repo ZUERST aufbauen (braucht ein echtes `subprocess.run`) — erst DANACH `git` für
    # `version_info()` kaputt machen, sonst schlägt schon `_scratch_repo()` selbst fehl.
    repo = _scratch_repo(tmp_path)
    _git(repo, "tag", "v1.0.0")

    def _haengt(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=V._GIT_TIMEOUT_S)

    monkeypatch.setattr(V.subprocess, "run", _haengt)

    info = V.version_info(root=repo, data_dir=repo / "data")

    assert info["installation"] == "git"
    assert info["commit"] is None
    assert info["datum"] is None
    assert info["entwicklungsstand"] == "noch keine Freigabe"
    assert info["freigabe"] is False
