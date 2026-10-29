"""Tests für `pipeline/kundenpaket.py` (P2-50 Arbeitspaket A) — das Skript, das aus dem
Git-Stand ein auslieferbares Kunden-ZIP baut: Ausschlüsse, Ersetzungen (README.md; als Rückfall
config/profil_struktur.md und automation/agent_settings.json), das Manifest und danach eine
fail-closed Personendaten-Prüfung, die KEIN ZIP schreibt, solange auch nur ein Fund offen ist.

Seit P2-83 stehen die dateibezogenen Prüfregeln und ihre Tests in `pipeline/personendaten.py` bzw.
`test_personendaten.py`; hier bleibt das Zusammenspiel: Das Kundenpaket ruft die Regeln im Umfang
„paket“ auf, lädt die persönlichen Muster aus den lokalen Quellen (Profil, Datenbank, Musterdatei)
und meldet in der Ausgabe, ob sie vorlagen. Alle Daten dieser Tests sind erfunden (Max Mustermann,
Musterweg, Nordfeld Systeme); Beispiele für verbotene Mailadressen, Telefonnummern und Bestands-IDs
werden zur Laufzeit zusammengesetzt, weil diese Datei beim Export selbst geprüft wird.

Die meisten Tests arbeiten auf handgebauten `Eintrag`-Listen im Speicher -- Ausschließen/
Ersetzen/Prüfen/Zip-Schreiben sind reine Funktionen auf dieser Liste, git ist nur die EINE
Quelle dafür (`sammle_aus_git_archive`/`sammle_aus_arbeitsbaum`). Ein eigener Abschnitt prüft
trotzdem beide Git-Quellen einmal gegen einen echten, winzigen Wegwerf-Repo in `tmp_path` --
das ist der einzige Teil dieses Moduls, der wirklich `git` und Betriebssystem-Pfade anfasst
und deshalb unter Windows (CI-Job `backend-windows`) gesondert Vertrauen braucht.

App-Import bewusst NIE auf Modulebene (conftest.py-Konvention, s. dort) -- `pipeline.
kundenpaket` bindet zwar weder DATA_DIR noch LOG_DIR, bleibt aber konsistent mit den
Nachbartests (test_docs_html.py u. a.).

KEIN Test schreibt nach `data/`/`outputs/` -- jedes ZIP und jeder Scratch-Repo landet in
`tmp_path`; Datenbank-Ordner und Secrets-Ordner zeigen für jeden Test ins Leere (autouse-Fixture), damit
die Quellen des Rechners nie mitspielen. `test_echter_repo_stand_ist_auslieferbar` (letzter Abschnitt) ist
der einzige Test, der den ECHTEN Arbeitsbaum anfasst -- rein LESEND über die `--arbeitsbaum`-Quelle
(nichts wird geschrieben, `nur_pruefen=True`), mit den echten lokalen Quellen, falls es sie gibt (in der CI
nicht: dort laufen nur die allgemeinen Regeln).

P2-82: `docs/LIZENZ.md` ist kein Kundendokument mehr (weder erlaubt noch Pflicht), und der Name des
öffentlichen Repos (`OEFFENTLICHES_REPO`) ist die einzige Schreibweise des Kontonamens, die die Regeln
durchlassen (Tests dazu in test_personendaten.py).

P2-83: `config/profil_struktur.md` ist keine Pflichtdatei mehr (nicht im Git, die App legt sie an), die
Einmal-Werkzeuge und Excel-Migrationen sind gelöscht und stehen nicht mehr in `AUSSCHLUESSE`,
`scripts/rotation_stand.py` bleibt im Paket (zwei Skills rufen es auf)."""
import json
import os
import re
import sqlite3
import subprocess
import zipfile
from pathlib import Path

import pytest

# Die echten lokalen Quellen, für den Wächter ganz unten. Beim Import gelesen, bevor eine Fixture die
# Umgebung auf leere Ordner umbiegt.
_ECHTE_PRUEFMUSTER = (Path(os.environ.get("BMS_SECRETS_DIR") or Path.home() / ".bewerbung_mgmt_secrets")
                      / "pruefmuster.txt")

PROFIL = """# Kandidatenprofil: Max Mustermann

## Identität
- **Name:** Max Mustermann
- **Standort:** Musterweg 1, 12345 Musterstadt
- **Kontakt:** max@beispiel.de
"""


@pytest.fixture(autouse=True)
def _lokale_quellen_isolieren(tmp_path, monkeypatch):
    """Kein Test sieht Datenbank, Musterdatei oder Profil des Rechners: beide Ordner zeigen ins Leere."""
    monkeypatch.setenv("BMS_SECRETS_DIR", str(tmp_path / "secrets_leer"))
    monkeypatch.setenv("BMS_DATA_DIR", str(tmp_path / "daten_leer"))


# ── Hilfsfunktionen für die Git-Tests ───────────────────────────────────────────────────────

def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _scratch_repo(tmp_path):
    """Winziges Wegwerf-Repo mit einem Commit: eine normale Datei + eine ausführbare. Der
    Modus wird über `git update-index --chmod=+x` gesetzt, NICHT über `os.chmod` -- ein
    Dateisystem-chmod ist unter Windows für den Git-Index wirkungslos (kein `core.filemode`),
    der Index-Weg setzt das Bit dagegen plattformunabhängig identisch (wichtig für den
    CI-Job `backend-windows`). `git config user.*` ist repo-lokal, rührt die globale
    Konfiguration nicht an."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    # Die Windows-Runner von GitHub setzen `core.autocrlf=true` — `git archive` lieferte dort
    # "Inhalt\r\n" statt "Inhalt\n" (CI 27.09.2026). Das echte Repo erzwingt LF per
    # `.gitattributes` (`* text=auto eol=lf`), ein Kundenpaket ist also auch unter Windows LF.
    # Dieses Wegwerf-Repo bildet das repo-lokal nach, statt eine .gitattributes mitzuschleppen.
    _git(repo, "config", "core.autocrlf", "false")
    (repo / "normal.txt").write_text("Inhalt\n", encoding="utf-8", newline="\n")
    (repo / "tool.sh").write_text("#!/bin/sh\necho hi\n", encoding="utf-8", newline="\n")
    _git(repo, "add", "normal.txt", "tool.sh")
    _git(repo, "update-index", "--chmod=+x", "tool.sh")
    _git(repo, "commit", "-q", "-m", "init")
    return repo



def _fake_commit():
    from pipeline import kundenpaket as kp
    return kp.CommitInfo("a" * 40, "aaaaaaa", "2026-09-27", (2026, 9, 27, 10, 0, 0))


def _scratch_repo_mit_version(tmp_path, version="1.0.0"):
    """Wie `_scratch_repo`, zusätzlich ein `VERSION`-Commit -- Grundlage für Manifest-/
    Freigabe-/Namens-Tests (P2-51 V1/V3), die eine echte Version brauchen."""
    repo = _scratch_repo(tmp_path)
    (repo / "VERSION").write_text(f"{version}\n", encoding="utf-8", newline="\n")
    _git(repo, "add", "VERSION")
    _git(repo, "commit", "-q", "-m", "VERSION")
    return repo


def _scratch_repo_vollstaendig(tmp_path, pflichtdateien, version="1.0.0"):
    """Wegwerf-Repo mit ALLEN `pflichtdateien` (+ einer SKILL.md) -- Grundlage für Tests, die
    einen ERFOLGREICHEN Paketbau brauchen (Manifest/Name/--ziel-ordner Ende-zu-Ende). Platzhalter-
    Inhalt reicht überall außer `automation/agent_settings.json` (muss gültiges JSON sein, s.
    `_agent_settings_neutralisiert`) und `.bat`-Dateien (müssen CRLF enthalten, s. Zeilenenden-
    Regel). `pflichtdateien` übergibt der Aufrufer -- kein Modul-Import auf Dateiebene hier
    (Konvention dieser Datei, s. Kopf-Docstring)."""
    repo = _scratch_repo(tmp_path)
    for pfad in list(pflichtdateien) + [".claude/skills/test/SKILL.md"]:
        ziel = repo / pfad
        ziel.parent.mkdir(parents=True, exist_ok=True)
        if pfad == "automation/agent_settings.json":
            ziel.write_text('{"permissions": {"allow": [], "deny": []}}\n',
                             encoding="utf-8", newline="\n")
        elif pfad.endswith(".bat"):
            ziel.write_bytes(b"@echo off\r\ndir\r\n")
        else:
            ziel.write_text(f"Platzhalter fuer {pfad}\n", encoding="utf-8", newline="\n")
    (repo / "VERSION").write_text(f"{version}\n", encoding="utf-8", newline="\n")
    _git(repo, "add", "-A")
    for ausfuehrbar in ("start.command", "stop.command", "update.command",
                        "wiederherstellen.command"):
        _git(repo, "update-index", "--chmod=+x", ausfuehrbar)
    _git(repo, "commit", "-q", "-m", "vollstaendiges Kundenpaket")
    return repo



# ── Git-Quellen (Plumbing) ───────────────────────────────────────────────────────────────

def test_git_archive_liefert_eintraege_mit_korrektem_modus(tmp_path):
    from pipeline import kundenpaket as kp

    repo = _scratch_repo(tmp_path)
    eintraege = kp.sammle_aus_git_archive("HEAD", repo)
    nach_pfad = {e.pfad: e for e in eintraege}

    assert nach_pfad["normal.txt"].modus == 0o644
    assert nach_pfad["normal.txt"].inhalt == b"Inhalt\n"
    assert nach_pfad["tool.sh"].modus == 0o755
    assert nach_pfad["tool.sh"].inhalt == b"#!/bin/sh\necho hi\n"


def test_arbeitsbaum_liefert_eintraege_und_meldet_fehlende(tmp_path):
    from pipeline import kundenpaket as kp

    repo = _scratch_repo(tmp_path)
    # Eine weitere Datei tracken, dann von der Platte löschen -- muss übersprungen UND
    # gemeldet werden (Spec: "Dateien, die im Arbeitsbaum fehlen: ueberspringen, im Bericht
    # nennen"), darf den Lauf aber nicht abbrechen.
    (repo / "wird_geloescht.txt").write_text("weg\n", encoding="utf-8")
    _git(repo, "add", "wird_geloescht.txt")
    _git(repo, "commit", "-q", "-m", "zweiter Commit")
    (repo / "wird_geloescht.txt").unlink()

    eintraege, uebersprungen = kp.sammle_aus_arbeitsbaum(repo)
    nach_pfad = {e.pfad: e for e in eintraege}

    assert nach_pfad["tool.sh"].modus == 0o755
    assert "wird_geloescht.txt" not in nach_pfad
    assert "wird_geloescht.txt" in uebersprungen


def test_arbeitsbaum_prueft_auch_neue_noch_nicht_hinzugefuegte_dateien(tmp_path):
    """Abnahme 27.09.2026: Ein neuer Kommentar mit einer Wohnanschrift in einer noch nicht
    hinzugefügten Datei (`frontend/src/profil.ts`) fiel durch die Vorschau, weil
    `git ls-files -s` nur den Index kennt. Neue Dateien gehören in die Vorschau, von
    `.gitignore` ausgeschlossene nicht. Der Umlaut-Name belegt `-z`: ohne NUL-Trennung maskiert
    git ihn oktal, und die Datei wäre unter dem maskierten Namen nicht zu finden. Vergleich in
    NFC, weil macOS Dateinamen mit Umlauten zerlegt ablegen kann."""
    import unicodedata

    from pipeline import kundenpaket as kp

    repo = _scratch_repo(tmp_path)
    (repo / ".gitignore").write_text("ignoriert.txt\n", encoding="utf-8", newline="\n")
    (repo / "ignoriert.txt").write_text("darf nicht ins Paket\n", encoding="utf-8")
    (repo / "neu.txt").write_text("noch nicht hinzugefügt\n", encoding="utf-8")
    (repo / "ümlaut.txt").write_text("x\n", encoding="utf-8")

    eintraege, _ = kp.sammle_aus_arbeitsbaum(repo)
    pfade = {unicodedata.normalize("NFC", e.pfad) for e in eintraege}

    assert "neu.txt" in pfade
    assert unicodedata.normalize("NFC", "ümlaut.txt") in pfade
    assert ".gitignore" in pfade
    assert "ignoriert.txt" not in pfade
    assert {"normal.txt", "tool.sh"} <= pfade          # die getrackten bleiben natürlich drin


def test_commit_info_liest_sha_kurz_und_datum(tmp_path):
    from pipeline import kundenpaket as kp

    repo = _scratch_repo(tmp_path)
    info = kp.commit_info("HEAD", repo)
    voll = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                           check=True, capture_output=True, text=True).stdout.strip()

    assert info.voll == voll
    assert voll.startswith(info.kurz)
    assert len(info.datum) == 10 and info.datum.count("-") == 2

# ── Der Name des öffentlichen Repos (Regeln: test_personendaten.py) ──────────────────────────────

def test_oeffentliches_repo_konstante_ist_der_gewollte_name_und_dieselbe_wie_in_personendaten():
    from pipeline import kundenpaket as kp
    from pipeline import personendaten

    assert kp.OEFFENTLICHES_REPO == "holgerdaube/BewerbungsMgmtSystem"
    assert kp.OEFFENTLICHES_REPO is personendaten.OEFFENTLICHES_REPO
    assert kp.Eintrag is personendaten.Eintrag and kp.Fund is personendaten.Fund


def test_oeffentliches_repo_konstante_stimmt_mit_update_pruefen_und_werkzeug_ueberein():
    """P2-82: Der Name steht an drei Stellen (Paketprüfung, Update-Auskunft der App, Update-Werkzeug).
    Gelesen wird als Text, nichts wird importiert (das Werkzeug darf nichts aus `app` importieren,
    und die Paketprüfung nicht aus dem Programm). Weicht eine Stelle ab, wäre die Ausnahme zu eng
    (der echte Name wird gemeldet) oder die Prüfung ließe einen anderen Namen durch."""
    from pipeline import kundenpaket as kp

    muster = re.compile(r"""^GITHUB_REPO(?:\s*:\s*[\w\[\], .|]+)?\s*=\s*(["'])([^"']+)\1""", re.MULTILINE)
    for rel in ("backend/app/update_pruefen.py", "scripts/bms_update.py"):
        quelle = (kp.PROJECT_ROOT / rel).read_text(encoding="utf-8")
        treffer = muster.findall(quelle)
        assert len(treffer) == 1, f"{rel}: GITHUB_REPO nicht genau einmal als Konstante gefunden"
        assert treffer[0][1] == kp.OEFFENTLICHES_REPO, rel


# ── Prüfen: das Kundenpaket ruft personendaten.pruefen im Umfang „paket“ ──────────────────────────

def test_pruefen_eintraege_ist_der_umfang_paket_und_ohne_muster_nur_allgemein():
    from pipeline import kundenpaket as kp
    from pipeline import personendaten

    muster = personendaten.Muster(anschrift=("Musterweg",), namen=("Mustermann",))
    eintraege = [
        kp.Eintrag("docs/ANLEITUNG.md", 0o644, "Im Musterweg wohnt Mustermann.\n".encode()),
        kp.Eintrag("update_windows.bat", 0o644, b"@echo off\necho hi\n"),             # LF ohne CR
        kp.Eintrag("docs/SETUP-EMAIL.md", 0o644, ("Mail an " + "jemand" + "@" + "fremde-firma.de\n").encode()),
    ]

    mit = kp.pruefen_eintraege(eintraege, muster)
    assert mit == personendaten.pruefen(eintraege, muster, umfang="paket")
    assert {f.regel for f in mit} == {"Anschrift", "Name des Nutzers in Kundentexten", "Zeilenende",
                                      "E-Mail-Adressen"}

    ohne = kp.pruefen_eintraege(eintraege)                  # kein Muster: nur die allgemeinen Regeln
    assert {f.regel for f in ohne} == {"Zeilenende", "E-Mail-Adressen"}


def test_alle_funde_sind_dateiregeln_plus_paketweite_regeln():
    from pipeline import kundenpaket as kp
    from pipeline import personendaten

    muster = personendaten.Muster(anschrift=("Musterweg",))
    eintraege = [kp.Eintrag("docs/ANLEITUNG.md", 0o644, b"Im Musterweg.\n")]
    roh = {"docs/ANLEITUNG.md"}

    funde = kp.alle_funde(eintraege, roh, muster)

    assert funde == kp.pruefen_eintraege(eintraege, muster) + kp.pruefen_paket(eintraege, roh)
    assert any(f.regel == "Anschrift" for f in funde) and any(f.regel == "Pflichtdatei fehlt" for f in funde)
    assert kp.alle_funde(eintraege, roh) == kp.pruefen_eintraege(eintraege) + kp.pruefen_paket(eintraege, roh)


def test_lizenz_doku_ist_aus_dem_kundenpaket_raus_lizenzdateien_bleiben_pflicht():
    """P2-82: `docs/LIZENZ.md` ist weder erlaubt noch Pflicht, ein Rest im Arbeitsbaum wird nicht
    mitgeliefert. Die Open-Source-Lizenz (LICENSE, NOTICE, lizenz.txt) bleibt Pflicht."""
    from pipeline import kundenpaket as kp

    assert "LIZENZ" not in kp.DOKU_ERLAUBT
    assert "docs/LIZENZ.md" not in kp.PFLICHTDATEIEN
    assert not any("LIZENZ" in pfad.upper().replace("DRITTLIZENZEN", "") for pfad in kp.PFLICHTDATEIEN
                   if pfad.startswith("docs/"))
    fehlend = {f.pfad for f in kp.pruefen_paket([], set()) if f.regel == "Pflichtdatei fehlt"}
    assert "docs/LIZENZ.md" not in fehlend
    assert {"LICENSE", "NOTICE", "frontend/src/rechtliches/lizenz.txt"} <= fehlend

    liste = [kp.Eintrag(p, 0o644, b"x") for p in ("docs/LIZENZ.md", "docs/LIZENZ.html", "docs/ANLEITUNG.md")]
    behalten, ausgeschlossen = kp.ausschliessen(liste)
    assert [e.pfad for e in behalten] == ["docs/ANLEITUNG.md"]
    assert set(ausgeschlossen) == {"docs/LIZENZ.md", "docs/LIZENZ.html"}


def test_regel_import_ausgeschlossener_module():
    from pipeline import kundenpaket as kp

    importierend = kp.Eintrag("backend/pipeline/nutzer.py", 0o644,
                                b"from pipeline import kundenpaket\n")
    # kundenpaket.py selbst ist ausgeschlossen (s. AUSSCHLUESSE) -- war aber im Quellbestand.
    roh_pfade = {"backend/pipeline/nutzer.py", "backend/pipeline/kundenpaket.py"}
    funde = kp.pruefen_paket([importierend], roh_pfade)
    assert any(f.regel == "Import ausgeschlossener Module" for f in funde)

    unbedenklich = kp.Eintrag("backend/pipeline/nutzer2.py", 0o644,
                                b"from pipeline import docs_render\nimport json\n")
    # docs_render.py MUSS hier als "behalten" mitgegeben werden -- sonst waere es aus Sicht
    # der Regel ja gerade ausgeschlossen (fehlt in kept), und der Test wuerde nicht das
    # pruefen, was er soll (unbedenklicher Import bleibt unbedenklich).
    docs_render_datei = kp.Eintrag("backend/pipeline/docs_render.py", 0o644, b"# ...\n")
    roh_pfade2 = {"backend/pipeline/nutzer2.py", "backend/pipeline/docs_render.py"}
    funde2 = kp.pruefen_paket([unbedenklich, docs_render_datei], roh_pfade2)
    assert not any(f.regel == "Import ausgeschlossener Module" for f in funde2)


# ── 2. Ausschlüsse ─────────────────────────────────────────────────────────────────────────

def test_ausschluesse_praefixe_werkzeuge_und_docs_positivliste():
    from pipeline import kundenpaket as kp

    liste = [
        kp.Eintrag("tasks/todo.md", 0o644, b"x"),
        kp.Eintrag("backend/tests/test_irgendwas.py", 0o644, b"x"),
        kp.Eintrag(".claude/launch.json", 0o644, b"x"),
        kp.Eintrag("scripts/test.sh", 0o755, b"x"),                    # Entwicklungswerkzeug
        kp.Eintrag("CONTRIBUTING.md", 0o644, b"x"),                    # Datei für das öffentliche Repo
        kp.Eintrag("SECURITY.md", 0o644, b"x"),
        kp.Eintrag("docs/DOKUMENTATION.md", 0o644, b"x"),              # interne Doku
        kp.Eintrag("docs/ANLEITUNG.md", 0o644, b"x"),                  # da
        kp.Eintrag("scripts/cv_basis_umbau_v10.py", 0o644, b"x"),      # da (bleibt bewusst)
        kp.Eintrag("scripts/rotation_stand.py", 0o644, b"x"),          # da: zwei Skills rufen es auf
        kp.Eintrag("backend/app/main.py", 0o644, b"x"),                # da
    ]
    behalten, ausgeschlossen = kp.ausschliessen(liste)
    behalten_pfade = {e.pfad for e in behalten}

    for pfad in ("tasks/todo.md", "backend/tests/test_irgendwas.py", ".claude/launch.json",
                 "scripts/test.sh", "CONTRIBUTING.md", "SECURITY.md", "docs/DOKUMENTATION.md"):
        assert pfad in ausgeschlossen and pfad not in behalten_pfade

    for pfad in ("docs/ANLEITUNG.md", "scripts/cv_basis_umbau_v10.py", "scripts/rotation_stand.py",
                 "backend/app/main.py"):
        assert pfad in behalten_pfade


def test_ausschluesse_ohne_geloeschte_dateien_und_mit_den_neuen_werkzeugen():
    """P2-83: Die gelöschten Einmal-Werkzeuge und Excel-Migrationen stehen nicht mehr in der Liste,
    `rotation_stand.py` bleibt im Paket; die Prüf- und Export-Werkzeuge stehen darin (das Export-Werkzeug
    importiert das ausgeschlossene kundenpaket.py, ginge es mit, wäre das Paket ein Fund wert)."""
    from pipeline import kundenpaket as kp

    gruende = dict(kp.AUSSCHLUESSE)
    for pfad in ("backend/import_lists.py", "backend/import_outreach.py", "backend/migrate_tracker.py",
                 "backend/cleanup_duplicates.py", "scripts/vertigis_firmen_merge.py",
                 "scripts/bewerbungsstatus_nachziehen.py", "scripts/antwortzeiten_neu_berechnen.py",
                 "scripts/rotation_stand.py", "scripts/tageslauf_messung.py", "scripts/cv_basis_umbau_v9.py"):
        assert pfad not in gruende, pfad
    for pfad in ("backend/pipeline/kundenpaket.py", "backend/pipeline/personendaten.py",
                 "backend/pipeline/veroeffentlichung.py", "scripts/veroeffentlichen.sh",
                 "CONTRIBUTING.md", "SECURITY.md"):
        assert gruende.get(pfad), f"{pfad} fehlt in AUSSCHLUESSE oder ohne Begründung"
    assert all(grund for grund in gruende.values())

    # Ein Eintrag ohne Datei ist kein Fehler: das Paket baut auch, wenn keine der Dateien da ist.
    behalten, ausgeschlossen = kp.ausschliessen([kp.Eintrag("backend/app/main.py", 0o644, b"x")])
    assert [e.pfad for e in behalten] == ["backend/app/main.py"] and ausgeschlossen == []


def test_ausschluesse_nennen_nur_dateien_die_es_gibt():
    """Ein Eintrag für eine gelöschte Datei ist Ballast, der die Liste unlesbar macht. Ausgenommen sind
    die Werkzeuge, die erst mit dem Export-Paket entstehen, und was im öffentlichen Baum fehlt (dort
    läuft dieser Test ebenfalls)."""
    from pipeline import kundenpaket as kp

    erst_spaeter = {"backend/pipeline/veroeffentlichung.py", "scripts/veroeffentlichen.sh"}
    nicht_oeffentlich = {"tasks/", ".claude/launch.json"}          # fehlen im öffentlichen Baum
    pfade = {e.pfad for e in kp.sammle_aus_arbeitsbaum()[0]}
    verwaist = []
    for muster, _grund in kp.AUSSCHLUESSE:
        if muster in erst_spaeter or muster in nicht_oeffentlich:
            continue
        treffer = any(p.startswith(muster) for p in pfade) if muster.endswith("/") else muster in pfade
        if not treffer:
            verwaist.append(muster)
    assert not verwaist, f"AUSSCHLUESSE nennt Dateien, die es nicht (mehr) gibt: {verwaist}"


def test_drittlizenzen_werkzeug_ausgeschlossen_ergebnisse_pflicht_und_geprueft():
    """P2-77: Generator und Wrapper sind Entwicklungswerkzeuge und bleiben draußen; ihre
    ERGEBNISSE (Übersicht und Wortlaut unter frontend/src/rechtliches/) gehen ins Paket, sind
    Pflichtdateien und werden wie jede andere ausgelieferte Textdatei geprüft."""
    from pipeline import kundenpaket as kp

    werkzeuge = ("backend/pipeline/drittlizenzen.py", "scripts/drittlizenzen.sh")
    ergebnisse = ("frontend/src/rechtliches/drittlizenzen.md",
                  "frontend/src/rechtliches/drittlizenzen_texte.txt")

    # Ausgeschlossen, mit Begründung (jede Zeile der Liste hat eine).
    gruende = dict(kp.AUSSCHLUESSE)
    for pfad in werkzeuge:
        assert gruende.get(pfad), f"{pfad} fehlt in AUSSCHLUESSE oder ohne Begründung"
    behalten, ausgeschlossen = kp.ausschliessen(
        [kp.Eintrag(p, 0o644, b"x") for p in werkzeuge + ergebnisse])
    assert set(ausgeschlossen) == set(werkzeuge)
    assert {e.pfad for e in behalten} == set(ergebnisse)

    # Pflichtdateien: beide stehen in der Liste, fehlen sie, meldet das die Paketprüfung ...
    for pfad in ergebnisse:
        assert pfad in kp.PFLICHTDATEIEN
    fehlend = {f.pfad for f in kp.pruefen_paket([], set()) if f.regel == "Pflichtdatei fehlt"}
    assert set(ergebnisse) <= fehlend

    # ... und sind sie da, meldet sie nichts mehr.
    vorhanden = [kp.Eintrag(p, 0o644, b"Lizenztexte\n") for p in ergebnisse]
    fehlend2 = {f.pfad for f in kp.pruefen_paket(vorhanden, set(ergebnisse))
                if f.regel == "Pflichtdatei fehlt"}
    assert not (set(ergebnisse) & fehlend2)

    # Ein ausgeliefertes Modul, das den ausgeschlossenen Generator importiert, wäre ein Fund
    # (Sicherheitsnetz: der Bau lieferte sonst ein Paket mit kaputtem Import).
    nutzer = kp.Eintrag("backend/pipeline/nutzer.py", 0o644,
                         b"from pipeline import drittlizenzen\n")
    funde = kp.pruefen_paket([nutzer], {"backend/pipeline/nutzer.py", "backend/pipeline/drittlizenzen.py"})
    assert any(f.regel == "Import ausgeschlossener Module" for f in funde)

# ── 3. Ersetzungen ─────────────────────────────────────────────────────────────────────────

def test_ersetzen_readme_und_als_rueckfall_profil_struktur_und_agent_settings():
    """P2-51: `VERSION.txt` entfällt (Punkt 1) -- die Version steht jetzt lesbar im README (aus
    dem `VERSION`-Eintrag der Liste, s. `_version_aus_eintraegen`) UND maschinenlesbar im
    Manifest (separat getestet). P2-83: `profil_struktur.md` und `agent_settings.json` werden nur noch
    ersetzt, wenn sie im Stand vorkommen."""
    from pipeline import kundenpaket as kp

    agent_settings_original = json.dumps({
        "hooks": {"PreToolUse": [{"matcher": "Write", "hooks": []}]},
        "permissions": {
            "allow": [
                "Read",
                "Bash(~/.bewerbung_mgmt_venv/bin/python:*)",
                "Bash($HOME/.bewerbung_mgmt_venv/bin/python:*)",
                "Bash(" + "/Users/" + "jemand/.bewerbung_mgmt_venv/bin/python:*)",
                "Bash(" + "/home/" + "jemand/.bewerbung_mgmt_venv/bin/python:*)",
            ],
            "deny": ["Bash(rm:*)"],
        },
    }, indent=2, ensure_ascii=False).encode("utf-8")

    liste = [
        kp.Eintrag("README.md", 0o644, b"# Altes Entwickler-README\n"),
        kp.Eintrag("config/profil_struktur.md", 0o644,
                   "# Profil-Struktur\n\nStand: 2026-08-10T00:00:00Z\n\n## Werdegang\n"
                   "Echter Werdegang steht hier\n".encode("utf-8")),
        kp.Eintrag("automation/agent_settings.json", 0o644, agent_settings_original),
        kp.Eintrag("VERSION", 0o644, b"1.2.3\n"),
    ]
    ergebnis = kp.ersetzen(liste, _fake_commit(), ist_arbeitsbaum=False)
    nach_pfad = {e.pfad: e for e in ergebnis}

    readme = nach_pfad["README.md"].inhalt.decode("utf-8")
    # P2-82: Hilfe über die Issues-Seite des öffentlichen Repos statt einer Mailadresse.
    assert f"https://github.com/{kp.OEFFENTLICHES_REPO}/issues" in readme
    assert "info@daube.tech" not in readme
    assert "Apache License 2.0" in readme
    # P2-71: Die README verweist auf beide Anleitungen (macOS bzw. Windows), sagt in einem Satz,
    # dass Claude mit der Datei durch die Installation führt, und kennt die alten Namen nicht mehr.
    assert "`BMS_Install_MAC.md` (macOS)" in readme
    assert "`BMS_Install_Windows.md` (Windows)" in readme
    assert "Claude führt Sie mit der Datei durch die Installation." in readme
    assert "BMS_Install.md" not in readme and "BMS_Install_Auto" not in readme
    assert "CHANGELOG.md" in readme
    assert "update.command" in readme and "update_windows.bat" in readme
    assert "Version 1.2.3 (Stand 27.09.2026)" in readme
    # Kein Wort über den Entwickler: außer dem Repo-Namen steht kein Kontoname darin
    konto = kp.OEFFENTLICHES_REPO.split("/")[0]
    assert konto not in readme.replace(kp.OEFFENTLICHES_REPO, "").lower()

    struktur = nach_pfad["config/profil_struktur.md"].inhalt.decode("utf-8")
    assert "Echter Werdegang" not in struktur
    assert struktur.startswith("# Profil-Struktur")

    settings = json.loads(nach_pfad["automation/agent_settings.json"].inhalt.decode("utf-8"))
    assert settings["hooks"] == {"PreToolUse": [{"matcher": "Write", "hooks": []}]}
    assert settings["permissions"]["deny"] == ["Bash(rm:*)"]
    allow = settings["permissions"]["allow"]
    assert "Bash(~/.bewerbung_mgmt_venv/bin/python:*)" in allow
    assert "Bash($HOME/.bewerbung_mgmt_venv/bin/python:*)" in allow
    assert not any("/Users/" in a or "/home/" in a for a in allow)

    # VERSION selbst bleibt unveraendert durch (kein Ersetzungs-Ziel), VERSION.txt entsteht nicht.
    assert nach_pfad["VERSION"].inhalt == b"1.2.3\n"
    assert "VERSION.txt" not in nach_pfad

    # Fehlt VERSION in der Liste (z. B. aelterer Commit vor P2-51), faellt _version_aus_eintraegen
    # auf "0.0.0" zurueck statt abzustuerzen -- s. dessen Docstring.
    ohne_version = [e for e in liste if e.pfad != "VERSION"]
    ergebnis_ohne = kp.ersetzen(ohne_version, _fake_commit(), ist_arbeitsbaum=False)
    readme_ohne = next(e for e in ergebnis_ohne if e.pfad == "README.md").inhalt.decode("utf-8")
    assert "Version 0.0.0" in readme_ohne


def test_ersetzen_ergaenzt_keine_dateien_die_im_stand_fehlen():
    """P2-83: `config/profil_struktur.md` ist nicht mehr im Git. Fehlt sie im Stand, wird sie weder ergänzt
    noch ist sie eine Pflichtdatei (die App legt sie beim Start an); `ANPASSBAR` behält sie, damit ein
    Update die beim Kunden entstandene Datei nicht als entfallen löscht."""
    from pipeline import kundenpaket as kp

    liste = [kp.Eintrag("README.md", 0o644, b"x"), kp.Eintrag("VERSION", 0o644, b"1.0.0\n")]
    assert {e.pfad for e in kp.ersetzen(liste, _fake_commit(), ist_arbeitsbaum=False)} == {"README.md", "VERSION"}

    assert "config/profil_struktur.md" not in kp.PFLICHTDATEIEN
    assert "automation/agent_settings.json" in kp.PFLICHTDATEIEN
    assert "config/profil_struktur.md" in kp.ANPASSBAR
    fehlend = {f.pfad for f in kp.pruefen_paket([], set()) if f.regel == "Pflichtdatei fehlt"}
    assert "config/profil_struktur.md" not in fehlend


# ── 4. ZIP ─────────────────────────────────────────────────────────────────────────────────

def test_zip_ohne_praefixordner_rechte_sortiert_zeitstempel(tmp_path):
    from pipeline import kundenpaket as kp

    liste = [
        kp.Eintrag("z_zweite.txt", 0o644, b"b"),
        kp.Eintrag("backend/start.command", 0o755, b"#!/bin/sh\necho hi\n"),
        kp.Eintrag("a_erste.txt", 0o644, b"a"),
    ]
    ziel = tmp_path / "ziel" / "paket.zip"
    kp.zip_schreiben(liste, ziel, (2026, 9, 27, 10, 0, 0))

    with zipfile.ZipFile(ziel) as zf:
        namen = zf.namelist()
        # Exakt dieselben Pfade wie eingegeben, sortiert -- kein zusaetzlicher Wurzelordner.
        assert namen == ["a_erste.txt", "backend/start.command", "z_zweite.txt"]

        info_start = zf.getinfo("backend/start.command")
        assert (info_start.external_attr >> 16) & 0o777 == 0o755
        # Als Unix-Eintrag markiert, sonst ignorieren Entpacker die Rechte (gilt auch fuer
        # ein unter Windows gebautes Paket -- der CI-Job backend-windows belegt das).
        assert info_start.create_system == 3
        assert info_start.date_time == (2026, 9, 27, 10, 0, 0)

        info_txt = zf.getinfo("a_erste.txt")
        assert (info_txt.external_attr >> 16) & 0o777 == 0o644
        assert info_txt.date_time == (2026, 9, 27, 10, 0, 0)

    # Nichts landet ausserhalb von tmp_path -- keine data/config-Referenz im Test noetig, das
    # ZIP liegt ausschliesslich unter dem uebergebenen `ziel`-Pfad.
    assert not any(n.startswith("data/") or n.startswith("outputs/") for n in namen)
    assert "config/profil.md" not in namen


# ── 5. Fail-closed ──────────────────────────────────────────────────────────────────────────

def _lokale_quellen_anlegen(repo, tmp_path, monkeypatch, *, profil=PROFIL, mit_datenbank=True):
    """Profil, Datenbank und Musterdatei wie bei einem Entwickler: im Wegwerf-Repo, aber nicht im Git
    (`.gitignore`, wie im echten Repo). Datenbank über `BMS_DATA_DIR`, Musterdatei über `BMS_SECRETS_DIR`."""
    (repo / ".gitignore").write_text("config/profil.md\ndata/\n", encoding="utf-8", newline="\n")
    if profil is not None:
        (repo / "config").mkdir(exist_ok=True)
        (repo / "config" / "profil.md").write_text(profil, encoding="utf-8", newline="\n")
    if mit_datenbank:
        (repo / "data").mkdir(exist_ok=True)
        conn = sqlite3.connect(repo / "data" / "bewerbung.sqlite")
        conn.execute("CREATE TABLE company (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE contact (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO company (name) VALUES ('Nordfeld Systeme GmbH')")
        conn.execute("INSERT INTO contact (name) VALUES ('Anna Beispiel')")
        conn.commit()
        conn.close()
    geheim = tmp_path / "geheim"
    geheim.mkdir()
    (geheim / "pruefmuster.txt").write_text("# frühere Anschrift\nAltweg\n", encoding="utf-8")
    monkeypatch.setenv("BMS_DATA_DIR", str(repo / "data"))
    monkeypatch.setenv("BMS_SECRETS_DIR", str(geheim))


def test_fail_closed_kein_zip_bei_fund_exit_code_1(tmp_path, capsys):
    from pipeline import kundenpaket as kp

    repo = _scratch_repo(tmp_path)
    (repo / "leck.md").write_text("Telefon: " + "+49" + " 69 87654321\n", encoding="utf-8")
    _git(repo, "add", "leck.md")
    _git(repo, "commit", "-q", "-m", "mit eingeschleustem Fund")

    ziel = tmp_path / "ziel"
    rc = kp.main(["--arbeitsbaum", "--ziel-ordner", str(ziel)], projekt_root=repo)
    ausgabe = capsys.readouterr().out

    assert rc == 1
    assert not ziel.exists() or not list(ziel.glob("*.zip"))
    assert "Telefonnummern" in ausgabe
    assert "Kein ZIP geschrieben" in ausgabe


def test_ci_ohne_profil_und_datenbank_laufen_nur_die_allgemeinen_regeln_und_die_ausgabe_sagt_es(
        tmp_path, capsys):
    """Frischer Checkout (CI): weder Profil noch Datenbank. Eine Anschrift wird nicht gefunden (sie ist
    nur als Muster aus dem Profil bekannt), eine allgemeine Regel schon; die Ausgabe nennt beide
    übersprungenen Regelgruppen."""
    from pipeline import kundenpaket as kp

    repo = _scratch_repo_vollstaendig(tmp_path, kp.PFLICHTDATEIEN)
    rc = kp.main(["--arbeitsbaum", "--pruefen"], projekt_root=repo)
    ausgabe = capsys.readouterr().out
    assert rc == 0, ausgabe
    assert "Firmennamen-Regel: uebersprungen" in ausgabe
    assert "Profil-Regeln (Anschrift, Kontakt, Name): uebersprungen" in ausgabe

    (repo / "notiz.md").write_text("Im Musterweg 1, dazu " + "jemand" + "@" + "fremde-firma.de\n",
                                    encoding="utf-8")
    rc = kp.main(["--arbeitsbaum", "--pruefen"], projekt_root=repo)
    ausgabe = capsys.readouterr().out
    assert rc == 1
    assert "notiz.md:1  [E-Mail-Adressen]" in ausgabe and "[Anschrift]" not in ausgabe


def test_mit_lokalen_quellen_werden_die_persoenlichen_regeln_geprueft(tmp_path, monkeypatch, capsys):
    """Entwickler-Rechner: Profil, Datenbank und Musterdatei liegen vor. Die Ausgabe sagt, wogegen
    geprüft wurde; ein Fund aus jeder Quelle verhindert das ZIP. Gilt für den Arbeitsbaum ebenso wie für
    `git archive`, und für Dateien, die das Paket später ausschließt, ist es einerlei."""
    from pipeline import kundenpaket as kp

    repo = _scratch_repo_vollstaendig(tmp_path, kp.PFLICHTDATEIEN)
    _lokale_quellen_anlegen(repo, tmp_path, monkeypatch)

    rc = kp.main(["--arbeitsbaum", "--pruefen"], projekt_root=repo)
    ausgabe = capsys.readouterr().out
    assert rc == 0, ausgabe
    assert f"Firmennamen-Regel: geprueft gegen {(repo / 'data' / 'bewerbung.sqlite')}" in ausgabe
    assert "Profil-Regeln (Anschrift, Kontakt, Name): geprueft gegen das Profil." in ausgabe
    assert "config/profil.md" not in ausgabe                         # nicht im Git, nicht im Paket

    funde_je_quelle = {
        "Anschrift": "Wohnhaft im Musterweg 1.",                                  # Profil
        "Private Kontaktdaten": "Mail: " + "max" + "@" + "anbieter.example.com",  # Profil (Vorderteil)
        "Dritte Personen": "Danke an Anna Beispiel.",                             # Datenbank
        "Firmennamen aus dem Bewerbungsverlauf": "Absage von Nordfeld Systeme.",  # Datenbank
    }
    for regel, text in funde_je_quelle.items():
        (repo / "leck.md").write_text(text + "\n", encoding="utf-8")
        ziel = tmp_path / f"ziel_{abs(hash(regel))}"
        rc = kp.main(["--arbeitsbaum", "--ziel-ordner", str(ziel)], projekt_root=repo)
        ausgabe = capsys.readouterr().out
        assert rc == 1, regel
        assert f"leck.md:1  [{regel}]" in ausgabe, ausgabe
        assert "Kein ZIP geschrieben" in ausgabe and not ziel.exists()

    # Musterdatei (frühere Anschrift) und derselbe Fund über `git archive` statt Arbeitsbaum
    (repo / "leck.md").write_text("Früher im Altweg.\n", encoding="utf-8")
    _git(repo, "add", "leck.md")
    _git(repo, "commit", "-q", "-m", "Fund aus der Musterdatei")
    rc = kp.main(["--ref", "HEAD", "--ziel-ordner", str(tmp_path / "ziel_ref")], projekt_root=repo)
    ausgabe = capsys.readouterr().out
    assert rc == 1 and "leck.md:1  [Anschrift]" in ausgabe


def test_bauen_nimmt_ein_uebergebenes_muster_und_firmen_db_als_pfad(tmp_path, monkeypatch):
    """`bauen(muster=…)` hat Vorrang vor den lokalen Quellen; `firmen_db=…` ist der Weg des
    Freigabe-Werkzeugs (`release.py`) und ersetzt die Suche nach der Datenbank."""
    from pipeline import kundenpaket as kp
    from pipeline import personendaten

    repo = _scratch_repo_vollstaendig(tmp_path, kp.PFLICHTDATEIEN)
    _lokale_quellen_anlegen(repo, tmp_path, monkeypatch)
    (repo / "leck.md").write_text("Im Musterweg und bei Nordfeld Systeme.\n", encoding="utf-8")

    eigenes = personendaten.Muster(anschrift=("Gartenallee",), profil_gelesen=True)
    ergebnis = kp.bauen(arbeitsbaum=True, ref=None, ziel=None, nur_pruefen=True, projekt_root=repo,
                         muster=eigenes)
    assert ergebnis.funde == () and ergebnis.profil_gelesen and ergebnis.firmen_db_pfad is None

    # Weg des Freigabe-Werkzeugs: Datenbank als Pfad, Profil und Musterdatei aus den Standardorten
    db = repo / "data" / "bewerbung.sqlite"
    monkeypatch.setenv("BMS_DATA_DIR", str(tmp_path / "anderswo_leer"))
    ergebnis = kp.bauen(arbeitsbaum=True, ref=None, ziel=None, nur_pruefen=True, projekt_root=repo,
                         firmen_db=db)
    assert ergebnis.firmen_db_pfad == db and ergebnis.profil_gelesen
    assert {f.regel for f in ergebnis.funde} == {"Anschrift", "Firmennamen aus dem Bewerbungsverlauf"}

    # Ohne `firmen_db` und mit leerem Datenordner: keine Datenbank, die Firmenregel entfällt
    ergebnis = kp.bauen(arbeitsbaum=True, ref=None, ziel=None, nur_pruefen=True, projekt_root=repo)
    assert ergebnis.firmen_db_pfad is None and ergebnis.profil_gelesen
    assert {f.regel for f in ergebnis.funde} == {"Anschrift"}


def test_ohne_profil_laeuft_die_datenbank_regel_weiter(tmp_path, monkeypatch, capsys):
    from pipeline import kundenpaket as kp

    repo = _scratch_repo_vollstaendig(tmp_path, kp.PFLICHTDATEIEN)
    _lokale_quellen_anlegen(repo, tmp_path, monkeypatch, profil=None)
    (repo / "leck.md").write_text("Danke an Anna Beispiel.\n", encoding="utf-8")

    rc = kp.main(["--arbeitsbaum", "--pruefen"], projekt_root=repo)
    ausgabe = capsys.readouterr().out

    assert rc == 1 and "leck.md:1  [Dritte Personen]" in ausgabe
    assert "Firmennamen-Regel: geprueft gegen" in ausgabe
    assert "Profil-Regeln (Anschrift, Kontakt, Name): uebersprungen" in ausgabe


def test_ref_und_arbeitsbaum_zusammen_ist_technischer_fehler(tmp_path):
    from pipeline import kundenpaket as kp

    repo = _scratch_repo(tmp_path)
    rc = kp.main(["--arbeitsbaum", "--ref", "HEAD", "--ziel-ordner", str(tmp_path / "ziel")],
                 projekt_root=repo)
    assert rc == 2


# ── 6. Startdatei-Ausfuehrbarkeit (Punkt 3) ────────────────────────────────────────────────

def test_regel_startdatei_nicht_ausfuehrbar():
    from pipeline import kundenpaket as kp

    ausfuehrbar = kp.Eintrag("update.command", 0o755, b"#!/bin/zsh\necho hi\n")
    assert kp._startdateien_funde([ausfuehrbar]) == []

    nicht_ausfuehrbar = kp.Eintrag("update.command", 0o644, b"#!/bin/zsh\necho hi\n")
    funde = kp._startdateien_funde([nicht_ausfuehrbar])
    assert any(f.regel == "Startdatei nicht ausfuehrbar" and f.pfad == "update.command" for f in funde)

    # P2-66: auch der Wiederherstellen-Starter braucht das Ausfuehr-Bit.
    nicht_ausf_w = kp.Eintrag("wiederherstellen.command", 0o644, b"#!/bin/zsh\necho hi\n")
    assert any(f.pfad == "wiederherstellen.command"
               for f in kp._startdateien_funde([nicht_ausf_w]))

    # Eine FEHLENDE Startdatei ist Sache der Pflichtdateien-Regel, nicht dieser hier.
    assert kp._startdateien_funde([]) == []

    # .bat braucht das Unix-Bit nicht -- ausserhalb von _STARTDATEIEN_AUSFUEHRBAR, keine Pruefung.
    bat = kp.Eintrag("update_windows.bat", 0o644, b"@echo off\r\n")
    assert kp._startdateien_funde([bat]) == []


# ── 9. Manifest (V3) ────────────────────────────────────────────────────────────────────────

def test_manifest_hashes_stimmen_nicht_selbstgelistet_sortiert_version_freigabe(tmp_path):
    import hashlib

    from pipeline import kundenpaket as kp

    eintraege = [
        kp.Eintrag("a_erste.txt", 0o644, b"Inhalt A"),
        kp.Eintrag("backend/start.command", 0o755, b"#!/bin/sh\necho hi\n"),
    ]
    commit = _fake_commit()
    manifest_eintrag = kp._manifest_eintrag(eintraege, commit, "1.2.3", freigabe=True, vorschau=False)
    paket = eintraege + [manifest_eintrag]

    ziel = tmp_path / "paket.zip"
    kp.zip_schreiben(paket, ziel, commit.zeit_tuple)
    with zipfile.ZipFile(ziel) as zf:
        manifest_bytes = zf.read("bms_manifest.json")
        manifest = json.loads(manifest_bytes)
        for pfad, eintrag in manifest["dateien"].items():
            inhalt = zf.read(pfad)
            assert eintrag["sha256"] == hashlib.sha256(inhalt).hexdigest()
            assert eintrag["groesse"] == len(inhalt)
        info_start = zf.getinfo("backend/start.command")
        assert manifest["dateien"]["backend/start.command"]["ausfuehrbar"] is True
        assert (info_start.external_attr >> 16) & 0o111

    assert "bms_manifest.json" not in manifest["dateien"]
    assert manifest["version"] == "1.2.3"
    assert manifest["freigabe"] is True
    assert manifest["vorschau"] is False
    assert manifest["produkt"] == kp.PRODUKT_MANIFEST
    assert manifest["format"] == 1
    assert manifest["commit"] == commit.voll
    assert manifest["commit_datum"] == commit.datum
    assert manifest["anpassbar"] == list(kp.ANPASSBAR)

    # Serialisierung V3: ensure_ascii=False, indent=1, sort_keys=True, LF am Ende.
    assert manifest_bytes.endswith(b"\n") and not manifest_bytes.endswith(b"\n\n")
    roh = manifest_bytes.decode("utf-8")
    top_level = ("anpassbar", "commit", "commit_datum", "dateien", "format", "freigabe",
                 "produkt", "version", "vorschau")
    positionen = [roh.index(f'"{schluessel}"') for schluessel in top_level]
    assert positionen == sorted(positionen), "Top-Level-Schluessel nicht alphabetisch sortiert"


def test_version_aus_eintraegen_liest_archiv_nicht_arbeitsbaum(tmp_path):
    """V3: "version" kommt aus dem GEPACKTEN Stand -- bei `--ref` aus dem Archiv, nicht aus
    einer lokal (unversioniert) geaenderten Datei im Arbeitsbaum."""
    from pipeline import kundenpaket as kp

    repo = _scratch_repo_mit_version(tmp_path, version="1.0.0")
    (repo / "VERSION").write_text("9.9.9\n", encoding="utf-8", newline="\n")  # nicht committet

    archiv = kp.sammle_aus_git_archive("HEAD", repo)
    assert kp._version_aus_eintraegen(archiv) == "1.0.0"

    arbeitsbaum, _ = kp.sammle_aus_arbeitsbaum(repo)
    assert kp._version_aus_eintraegen(arbeitsbaum) == "9.9.9"


# ── 10. Freigabe-Erkennung und Name (Punkt 2) ─────────────────────────────────────────────

def test_freigabe_erkennung_ueber_git_tag(tmp_path):
    from pipeline import kundenpaket as kp

    repo = _scratch_repo_mit_version(tmp_path, version="1.0.0")
    info = kp.commit_info("HEAD", repo)

    assert kp._ist_freigegeben(info, "1.0.0", repo) is False  # noch kein Tag

    _git(repo, "tag", "-a", "v1.0.0", "-m", "BMS 1.0.0")
    assert kp._ist_freigegeben(info, "1.0.0", repo) is True
    assert kp._ist_freigegeben(info, "1.0.1", repo) is False  # falsche Version, gleicher Commit


def test_commit_info_schaelt_annotiertes_tag(tmp_path):
    """`--ref v1.2.3` mit einem ANNOTIERTEN Tag (so legt release.py Freigaben an): `git show`
    gibt dort zuerst Tagger und Nachricht aus, `commit_info` scheiterte daran (P2-51,
    gefunden im Ende-zu-Ende-Test)."""
    from pipeline import kundenpaket as kp

    repo = _scratch_repo_mit_version(tmp_path, version="1.0.0")
    _git(repo, "tag", "-a", "v1.0.0", "-m", "BMS 1.0.0\n\nMehrzeilige Nachricht")
    assert kp.commit_info("v1.0.0", repo) == kp.commit_info("HEAD", repo)


def test_ziel_dateiname_freigabe_keine_freigabe_vorschau():
    from pipeline import kundenpaket as kp

    commit = _fake_commit()
    assert kp.ziel_dateiname(commit, "1.0.0", True, False) == "BMS_1.0.0.zip"
    assert kp.ziel_dateiname(commit, "1.0.0", False, False) == "BMS_1.0.0_2026-09-27_aaaaaaa.zip"
    assert kp.ziel_dateiname(commit, "1.0.0", True, True) == "BMS_VORSCHAU_2026-09-27.zip"
    # Freigabe wird bei --arbeitsbaum von bauen() nie hereingereicht (immer False) -- die
    # Vorschau gewinnt trotzdem, selbst wenn hier versehentlich True stuende.
    assert kp.ziel_dateiname(commit, "1.0.0", False, True) == "BMS_VORSCHAU_2026-09-27.zip"


# ── 11. Ende-zu-Ende mit vollstaendigem Fixture-Repo (--ziel-ordner, Punkt 2/8) ────────────

def test_ziel_ordner_option_und_erfolgreicher_bau_im_arbeitsbaum(tmp_path):
    from pipeline import kundenpaket as kp

    repo = _scratch_repo_vollstaendig(tmp_path, kp.PFLICHTDATEIEN, version="1.0.0")
    ziel = tmp_path / "irgendwo" / "anders"
    rc = kp.main(["--arbeitsbaum", "--ziel-ordner", str(ziel)], projekt_root=repo)

    assert rc == 0, "vollstaendiges Fixture-Repo sollte ohne Funde durchlaufen"
    zips = list(ziel.glob("*.zip"))
    assert len(zips) == 1
    datum = kp.commit_info("HEAD", repo).datum
    assert zips[0].name == f"BMS_VORSCHAU_{datum}.zip"

    with zipfile.ZipFile(zips[0]) as zf:
        assert "bms_manifest.json" in zf.namelist()
        manifest = json.loads(zf.read("bms_manifest.json"))
        assert manifest["version"] == "1.0.0"
        assert manifest["vorschau"] is True
        assert manifest["freigabe"] is False


def test_ziel_ordner_option_freigegebener_stand_aus_ref(tmp_path):
    from pipeline import kundenpaket as kp

    repo = _scratch_repo_vollstaendig(tmp_path, kp.PFLICHTDATEIEN, version="2.0.0")
    _git(repo, "tag", "-a", "v2.0.0", "-m", "BMS 2.0.0")
    ziel = tmp_path / "ziel"
    rc = kp.main(["--ref", "HEAD", "--ziel-ordner", str(ziel)], projekt_root=repo)

    assert rc == 0
    zips = list(ziel.glob("*.zip"))
    assert [z.name for z in zips] == ["BMS_2.0.0.zip"]


# ── 12. .gitattributes: .bat/.cmd CRLF, Rest bleibt LF (Punkt 6c/7) ───────────────────────

def test_gitattributes_start_windows_bat_ist_als_crlf_deklariert():
    """Das eigentliche Neu-Auschecken von `start_windows.bat`/`stop_windows.bat` (Punkt 7,
    Inhalt unveraendert, nur Zeilenenden) macht die Hauptsession/dieses Paket EINMALIG im
    Arbeitsbaum -- hier wird nur geprueft, dass die DEKLARATION in `.gitattributes` dafuer
    tatsaechlich greift. Laeuft gegen den ECHTEN Projekt-Root wie `test_echter_repo_stand_ist_
    auslieferbar`, prueft aber nur `.gitattributes` selbst (mein exklusives Paket), nicht den
    Gesamtstand der anderen Pakete."""
    from pipeline import kundenpaket as kp

    for pfad in ("start_windows.bat", "stop_windows.bat", "update_windows.bat",
                 "wiederherstellen_windows.bat"):
        ausgabe = subprocess.run(["git", "check-attr", "eol", "--", pfad], cwd=kp.PROJECT_ROOT,
                                  check=True, capture_output=True, text=True).stdout
        assert ausgabe.strip().endswith("eol: crlf"), f"{pfad}: {ausgabe.strip()!r}"
    for pfad in ("start.command", "stop.command", "update.command", "wiederherstellen.command"):
        ausgabe = subprocess.run(["git", "check-attr", "eol", "--", pfad], cwd=kp.PROJECT_ROOT,
                                  check=True, capture_output=True, text=True).stdout
        assert ausgabe.strip().endswith("eol: lf"), f"{pfad}: {ausgabe.strip()!r}"


def _scratch_repo_mit_gitattributes(tmp_path):
    """Wie `_scratch_repo`, zusaetzlich eine `.gitattributes` nach dem echten Muster (LF-Default,
    CRLF fuer .bat/.cmd) sowie ein `tool.bat` und `tool2.command` -- prueft die tatsaechliche
    Wechselwirkung von `.gitattributes` und `git archive` (nicht nur die Deklaration wie oben).
    `core.autocrlf false` wie in `_scratch_repo`, damit die Windows-CI-Laufumgebung keinen
    Unterschied macht (s. dortige Begruendung)."""
    repo = _scratch_repo(tmp_path)
    (repo / ".gitattributes").write_text(
        "* text=auto eol=lf\n*.bat text eol=crlf\n*.cmd text eol=crlf\n",
        encoding="utf-8", newline="\n",
    )
    # Quelle bewusst mit LF geschrieben -- git normalisiert Text beim Add ohnehin auf LF im
    # Objekt, die CRLF-Ausgabe muss also wirklich vom `git archive`-Export kommen, nicht davon,
    # dass schon die Quelle CRLF enthielt.
    (repo / "tool.bat").write_text("@echo off\necho hi\n", encoding="utf-8", newline="\n")
    (repo / "tool2.command").write_text("#!/bin/sh\necho hi\n", encoding="utf-8", newline="\n")
    _git(repo, "add", ".gitattributes", "tool.bat", "tool2.command")
    _git(repo, "commit", "-q", "-m", "gitattributes")
    return repo


def test_gitattributes_git_archive_liefert_bat_crlf_command_lf(tmp_path):
    from pipeline import kundenpaket as kp

    repo = _scratch_repo_mit_gitattributes(tmp_path)
    eintraege = kp.sammle_aus_git_archive("HEAD", repo)
    nach_pfad = {e.pfad: e for e in eintraege}

    assert nach_pfad["tool.bat"].inhalt == b"@echo off\r\necho hi\r\n"
    assert nach_pfad["tool2.command"].inhalt == b"#!/bin/sh\necho hi\n"
    assert b"\r" not in nach_pfad["tool2.command"].inhalt



# ── 13. Der dauerhafte Wächter: echter Arbeitsbaum ──────────────────────────────────────────

def test_echter_repo_stand_ist_auslieferbar():
    """Prüfung über den ECHTEN Arbeitsbaum (`--arbeitsbaum`-Quelle, `nur_pruefen=True` -- schreibt
    nichts), mit den echten lokalen Quellen, falls es sie gibt: Profil in `config/`, Datenbank in `data/`
    (nicht `BMS_DATA_DIR`, das die Tests auf einen leeren Ordner umbiegen) und die Musterdatei im
    echten Secrets-Ordner. Ohne sie (CI, frischer Checkout) laufen die allgemeinen Regeln und die
    paketweiten Regeln: Wächter gegen jedes künftige Einschleppen von Personendaten in eine
    ausgelieferte Datei."""
    from pipeline import kundenpaket as kp
    from pipeline import personendaten

    db = kp.PROJECT_ROOT / "data" / "bewerbung.sqlite"
    muster = personendaten.muster_laden(kp.PROJECT_ROOT, db_pfad=db, extra=_ECHTE_PRUEFMUSTER)

    ergebnis = kp.bauen(arbeitsbaum=True, ref=None, ziel=None, nur_pruefen=True, muster=muster)
    assert ergebnis.funde == (), (
        f"{len(ergebnis.funde)} Personendaten-Fund(e) im echten Arbeitsbaum:\n" +
        "\n".join(f"{f.pfad}:{f.zeile}  [{f.regel}]  {f.ausschnitt}" for f in ergebnis.funde)
    )
