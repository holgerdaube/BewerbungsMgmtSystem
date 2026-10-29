"""Tests für `pipeline/veroeffentlichung.py` (P2-83, Paket E): das Export-Werkzeug, das aus einem Commit
des privaten Repos den öffentlichen Baum in einer lokalen Arbeitskopie des öffentlichen Repos erzeugt und
bei jedem Personendaten- oder Geheimnis-Fund verweigert.

NUR ERFUNDENE DATEN: Profil „Max Mustermann“, Datenbank, Musterdatei und alle Repos entstehen in
`tmp_path` (Autor der Commits im Quell-Repo: „Test Autor“, `autor@example.com`; im Ziel eine erfundene
GitHub-noreply-Adresse, die Prüfung der Commit-Identität verlangt sie). Nichts wird je gepusht: der
`origin` des Ziels ist nur eine Adresse, die das Werkzeug liest. Diese Datei wird mit dem öffentlichen
Baum geprüft (Umfang oeffentlich), deshalb steht hier kein Text, den die allgemeinen Regeln oder die
Geheimnis-Suche selbst melden würden: Schlüssel und Adressen werden zur Laufzeit zusammengesetzt, die
Repo-Adresse kommt aus `OEFFENTLICHES_REPO`.

Die Tests zur Commit-Identität (P2-84) sehen weder die globale Git-Konfiguration noch die Umgebung des
Rechners (`_git_umgebung_isolieren`): Sonst hinge „ohne user.email“ davon ab, was auf dem Rechner steht.

Aufbau: Hilfen -> sauberer Export -> Funde (Personendaten, Geheimnisse, Pfade) und die geschwärzte Ausgabe
-> `--pruefen` -> Revision (`main`, HEAD mit ungesicherten Änderungen) -> fehlende Quellen -> Ziel-Prüfung
-> Commit-Identität des Ziels (noreply, Verlauf, Tags) -> Spiegeln (Löschen, Rechte, Zeilenenden,
Git-Verzeichnis) -> Einheiten -> Aufruf und Skript -> Wächter über den echten Stand.

App-/Pipeline-Importe nie auf Modulebene (conftest-Regel), nur über die Fixtures `ve` und `pd`. Kein Test
liest oder schreibt `data/`, `outputs/`, `config/profil.md` oder den echten Secrets-Ordner. Einziger Test,
der das echte Projekt anfasst: `test_echter_stand_hat_keine_funde_mit_allgemeinen_regeln` (rein lesend)."""
import hashlib
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJEKT_ROOT = Path(__file__).resolve().parents[2]
UNIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="Ausführ-Bit und Symlinks gibt es unter Windows nicht")

PROFIL = """# Kandidatenprofil: Max Mustermann

## Identität
- **Name:** Max Mustermann
- **Positionierung:** Service Delivery Leader, DACH
- **Standort:** Musterweg 1, 12345 Musterstadt (Rhein-Main)
- **Kontakt:** max@beispiel.de · 069 5550123
- **LinkedIn:** https://www.linkedin.com/in/max-mustermann/

## Kurzprofil
Ein Satz.
"""

# Was die Prüfung in der Ausgabe nie zeigen darf (Muster aus Profil, Datenbank und Musterdatei).
BEGRIFFE = ("Mustermann", "Musterweg", "12345", "max@", "5550123", "Anna Beispiel", "Nordfeld", "Altmeier")

BASIS = {
    "README.md": "# Beispiel\n\nEin harmloser Text.\n",
    "VERSION": "1.2.3\n",
    "docs/ANLEITUNG.md": "Anleitung.\n",
    "tool.sh": "#!/bin/sh\necho hi\n",
    "start.bat": b"@echo off\r\necho hi\r\n",
    ".claude/skills/x/SKILL.md": "Skill.\n",
    # NICHT_OEFFENTLICH: wird nie geprüft und nie exportiert
    "tasks/notiz.md": "Intern: Musterweg 1 und Anna Beispiel.\n",
    ".claude/launch.json": "{}\n",
}
OEFFENTLICH = {"README.md", "VERSION", "docs/ANLEITUNG.md", "tool.sh", "start.bat", ".claude/skills/x/SKILL.md"}


# ── Hilfen ──────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def ve():
    from pipeline import veroeffentlichung
    return veroeffentlichung


@pytest.fixture
def pd():
    from pipeline import personendaten
    return personendaten


@pytest.fixture(autouse=True)
def _lokale_quellen_isolieren(tmp_path, monkeypatch):
    """Datenbank-Ordner und Secrets-Ordner zeigen ins Leere: kein Test sieht die Quellen des Rechners."""
    monkeypatch.setenv("BMS_SECRETS_DIR", str(tmp_path / "secrets_leer"))
    monkeypatch.setenv("BMS_DATA_DIR", str(tmp_path / "daten_leer"))
    monkeypatch.delenv("BMS_AUFRUFORDNER", raising=False)


@pytest.fixture(autouse=True)
def _git_umgebung_isolieren(tmp_path, monkeypatch):
    """Weder die globale noch die System-Konfiguration von git noch die Mail-Umgebungsvariablen des
    Rechners dürfen in einen Test hineinreichen: `git var` (Commit-Identität des Ziels) liest sie alle.
    Ohne das hinge der Test „ohne user.email“ am Rechner (Linux, Windows, die CI, der Entwicklungsrechner)."""
    leer = tmp_path / "git_global_leer.cfg"
    leer.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(leer))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for name in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL", "EMAIL"):
        monkeypatch.delenv(name, raising=False)


def _git(repo, *args):
    proc = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, encoding="utf-8")
    return proc.stdout.strip()


def _neues_repo(pfad, email="autor@example.com"):
    """Wegwerf-Repo mit Zweig `main` und erfundenem Autor. `config/` steht in `info/exclude`, damit das
    erfundene Profil nie in einen Commit gerät. Repo-lokale Einstellungen: unabhängig von der
    globalen Git-Konfiguration (Signieren, Zeilenenden)."""
    pfad.mkdir(parents=True)
    _git(pfad, "init", "-q", "-b", "main")
    _git(pfad, "config", "user.email", email)
    _git(pfad, "config", "user.name", "Test Autor")
    _git(pfad, "config", "core.autocrlf", "false")
    _git(pfad, "config", "commit.gpgsign", "false")
    (pfad / ".git" / "info" / "exclude").write_text("config/\n", encoding="utf-8")
    return pfad


def _commit(repo, dateien=None, *, ausfuehrbar=(), entfernen=(), nachricht="Stand"):
    for pfad, inhalt in (dateien or {}).items():
        datei = repo / pfad
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_bytes(inhalt.encode("utf-8") if isinstance(inhalt, str) else inhalt)
    for pfad in entfernen:
        (repo / pfad).unlink()
    for pfad in ausfuehrbar:
        (repo / pfad).chmod(0o755)                    # sonst meldet git (core.filemode) eine Änderung
    _git(repo, "add", "-A")
    for pfad in ausfuehrbar:
        _git(repo, "update-index", "--chmod=+x", pfad)
    _git(repo, "commit", "-q", "-m", nachricht)
    return _git(repo, "rev-parse", "HEAD")


def _db(tmp_path, *, company=("Nordfeld Systeme GmbH",), contact=("Anna Beispiel", "Recruiting Team"),
        dateiname="test.sqlite"):
    """Erfundene SQLite mit den Tabellen, die `personendaten.muster_laden` liest."""
    pfad = tmp_path / dateiname
    conn = sqlite3.connect(pfad)
    conn.execute("CREATE TABLE company (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE job (id INTEGER PRIMARY KEY, company_name TEXT)")
    conn.execute("CREATE TABLE targetcompany (id INTEGER PRIMARY KEY, company TEXT)")
    conn.execute("CREATE TABLE headhunter (id INTEGER PRIMARY KEY, firma TEXT)")
    conn.execute("CREATE TABLE contact (id INTEGER PRIMARY KEY, name TEXT)")
    conn.executemany("INSERT INTO company (name) VALUES (?)", [(w,) for w in company])
    conn.executemany("INSERT INTO contact (name) VALUES (?)", [(w,) for w in contact])
    conn.commit()
    conn.close()
    return pfad


def _at(vorn, hinten):
    """Adressen mit „@“ zur Laufzeit: eine Mailadresse im Quelltext meldet die E-Mail-Regel."""
    return vorn + "@" + hinten


def _url(pd):
    return f"https://github.com/{pd.OEFFENTLICHES_REPO}.git"


def _noreply(konto="beispiel-konto", nummer="4711"):
    """Erfundene GitHub-noreply-Adresse (`<Nummer>+<Konto>` oder, mit `nummer=None`, nur `<Konto>`)."""
    return _at(f"{nummer}+{konto}" if nummer else konto, "users.noreply.github.com")


def _privat():
    """Erfundene „private“ Adresse: darf nie in einer Ausgabe stehen."""
    return _at("privat.person", "beispiel.de")


def _ziel_repo(pfad, pd, *, origin=True, dateien=None):
    """Arbeitskopie des „öffentlichen“ Repos: eigenes Repo mit noreply-Identität (die Prüfung des Ziels
    verlangt sie), `origin` nur als Adresse (es wird nie gepusht)."""
    _neues_repo(pfad, _noreply())
    if origin:
        _git(pfad, "remote", "add", "origin", _url(pd) if origin is True else origin)
    if dateien:
        _commit(pfad, dateien, nachricht="Anfang")
    return pfad


@pytest.fixture
def umg(tmp_path, pd):
    """Quell-Repo mit Profil (Max Mustermann), Datenbank, leerer Musterdatei und sauberem Ziel."""
    quelle = _neues_repo(tmp_path / "quelle")
    _commit(quelle, BASIS, ausfuehrbar=["tool.sh"], nachricht="Anfang")
    (quelle / "config").mkdir()
    (quelle / "config" / "profil.md").write_text(PROFIL, encoding="utf-8")
    ziel = _ziel_repo(tmp_path / "oeffentlich", pd, dateien={"alt.txt": "alt\n"})
    return SimpleNamespace(quelle=quelle, ziel=ziel, db=_db(tmp_path), tmp=tmp_path,
                           extra=tmp_path / "keine_musterdatei.txt")


def _lauf(ve, umg, *args, ziel=True, **kw):
    """`main` mit den erfundenen Quellen. Rückgabe: Exit-Code."""
    argv = (["--ziel", str(kw.pop("ziel_pfad", umg.ziel))] if ziel else []) + list(args)
    return ve.main(argv, projekt_root=kw.pop("quelle", umg.quelle), db_pfad=kw.pop("db", umg.db),
                   extra=kw.pop("extra", umg.extra))


def _dateien(ordner):
    """Alle Dateien eines Ordners (relativ, mit „/“) ohne `.git`."""
    return {p.relative_to(ordner).as_posix() for p in ordner.rglob("*")
            if p.is_file() and ".git" not in p.relative_to(ordner).parts}


def _schnappschuss(ordner):
    """Inhalt aller Dateien und Ordner ohne `.git` -- zum Vergleich „nichts geschrieben“."""
    stand = {}
    for p in sorted(ordner.rglob("*")):
        rel = p.relative_to(ordner)
        if ".git" in rel.parts:
            continue
        stand[rel.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
    return stand


def _git_stand(repo):
    """Was ein Commit oder Tag im Ziel ändern würde."""
    return (_git(repo, "rev-list", "--all", "--count"), _git(repo, "tag"), _git(repo, "reflog"))


def _ohne_begriffe(text):
    for begriff in BEGRIFFE:
        assert begriff.lower() not in text.lower(), f"{begriff!r} steht in der Ausgabe"


def _git_als(repo, autor, *args, committer=None):
    """git mit fester Autor- und Committer-Adresse NUR für diesen Aufruf (Umgebungsvariablen): so entsteht ein
    Commit oder Tag mit fremder Adresse, ohne die Einstellung des Repos zu ändern."""
    umgebung = {**os.environ, "GIT_AUTHOR_EMAIL": autor, "GIT_COMMITTER_EMAIL": committer or autor}
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=umgebung)


def _identitaets_abbruch(ve, umg, capsys, erwartet, *adressen):
    """Ein Lauf bricht mit Exit 2 ab, nennt `erwartet`, nie eine der `adressen`, und das Ziel bleibt, wie es war.
    Gibt die Ausgabe zurück."""
    dateien, git_stand = _schnappschuss(umg.ziel), _git_stand(umg.ziel)

    assert _lauf(ve, umg) == 2

    ausgabe = capsys.readouterr().out
    assert erwartet in ausgabe
    for adresse in adressen:
        assert adresse not in ausgabe
    assert _schnappschuss(umg.ziel) == dateien and _git_stand(umg.ziel) == git_stand
    return ausgabe


def _geheimnis(art):
    """Schlüssel zur Laufzeit zusammengesetzt: diese Datei meldet sich sonst selbst."""
    return {
        "anthropic": "sk-" + "ant-" + "api03-" + "A1b2C3d4E5f6G7h8I9j0",
        "apify": "apify_" + "api_" + "A1b2C3d4E5f6G7h8I9j0K1",
        "client_secret": '{"client_' + 'secret": "GOCS' + 'PX-A1b2C3d4E5f6G7h8"}',
        "pem": "-----" + "BEGIN RSA PRIVATE" + " KEY-----",
        "github": "gh" + "p_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7",
        "github_pat": "github" + "_pat_" + "A1b2C3d4E5f6G7h8I9j0K1l2",
    }[art]


# ── Sauberer Export ─────────────────────────────────────────────────────────────────────────────

def test_sauberer_export_spiegelt_den_oeffentlichen_baum(ve, umg, capsys):
    vorher = _git_stand(umg.ziel)

    assert _lauf(ve, umg) == 0
    ausgabe = capsys.readouterr().out

    assert _dateien(umg.ziel) == OEFFENTLICH                    # alt.txt weg, tasks/ und launch.json fehlen
    for pfad in OEFFENTLICH:
        assert (umg.ziel / pfad).read_bytes() == (umg.quelle / pfad).read_bytes(), pfad
    assert f"Geschrieben: {len(OEFFENTLICH)} Dateien" in ausgabe
    assert "Version 1.2.3" in ausgabe
    assert " D alt.txt" in ausgabe and "?? README.md" in ausgabe          # git status --short des Ziels
    assert "Nächste Schritte" in ausgabe and "v1.2.3" in ausgabe
    assert _git_stand(umg.ziel) == vorher                       # kein Commit, kein Tag
    _ohne_begriffe(ausgabe)


def test_naechste_schritte_nennen_die_befehle_aus_der_doku(ve, umg, capsys):
    """Commit mit `-s`, Push von main, CI abwarten, Tag, Push des Tags, Release prüfen -- wie in
    docs/RELEASE.md, Abschnitt Veröffentlichen, mit echtem Ziel und echter Version."""
    assert _lauf(ve, umg) == 0
    ausgabe = capsys.readouterr().out
    ziel = f'git -C "{umg.ziel.resolve()}"'

    assert f'{ziel} add -A' in ausgabe
    assert f'{ziel} commit -s -m "BMS 1.2.3"' in ausgabe
    assert f"{ziel} push origin main" in ausgabe
    assert "CI" in ausgabe and "abwarten" in ausgabe
    assert f'{ziel} tag -a v1.2.3 -m "BMS 1.2.3"' in ausgabe
    assert f"{ziel} push origin v1.2.3" in ausgabe
    assert "scripts/release.sh abholen 1.2.3" in ausgabe
    assert ausgabe.index("commit -s") < ausgabe.index("push origin main") < ausgabe.index("tag -a") \
        < ausgabe.index("push origin v1.2.3")                  # die Reihenfolge ist Teil der Regel


def test_ausgenommene_pfade_werden_nicht_geprueft_und_nicht_exportiert(ve, umg):
    """`tasks/notiz.md` nennt Straße und Dritte, `.claude/launch.json` ein Geheimnis: beides bleibt draußen,
    ohne Fund."""
    _commit(umg.quelle, {".claude/launch.json": '{"x": "' + _geheimnis("anthropic") + '"}\n'})

    assert _lauf(ve, umg) == 0
    assert not (umg.ziel / "tasks").exists()
    assert not (umg.ziel / ".claude" / "launch.json").exists()
    assert (umg.ziel / ".claude" / "skills" / "x" / "SKILL.md").is_file()


def test_nicht_oeffentlich_ist_die_kurze_ausschlussliste(ve):
    assert ve.NICHT_OEFFENTLICH == ("tasks/", ".claude/launch.json")


def test_im_quell_repo_geloeschte_datei_verschwindet_im_ziel(ve, umg, capsys):
    _commit(umg.quelle, {"weg.txt": "kommt und geht\n"})
    assert _lauf(ve, umg) == 0
    assert (umg.ziel / "weg.txt").is_file()
    _git(umg.ziel, "add", "-A")                                  # nur der Test committet im Wegwerf-Ziel
    _git(umg.ziel, "commit", "-q", "-m", "Erster Export")
    vorher = _git_stand(umg.ziel)
    _commit(umg.quelle, entfernen=["weg.txt"])
    capsys.readouterr()

    assert _lauf(ve, umg) == 0

    assert not (umg.ziel / "weg.txt").exists()
    assert " D weg.txt" in capsys.readouterr().out
    assert _git_stand(umg.ziel) == vorher


def test_zweiter_export_ohne_aenderung_meldet_keine_aenderungen(ve, umg, capsys):
    assert _lauf(ve, umg) == 0
    _git(umg.ziel, "add", "-A")
    _git(umg.ziel, "commit", "-q", "-m", "Erster Export")
    capsys.readouterr()

    assert _lauf(ve, umg) == 0
    assert "keine Änderungen gegenüber dem letzten Commit" in capsys.readouterr().out


def test_status_wird_auf_40_zeilen_gekuerzt(ve, umg, capsys):
    _commit(umg.quelle, {f"viele/datei_{i:03d}.txt": "x\n" for i in range(60)})

    assert _lauf(ve, umg) == 0
    ausgabe = capsys.readouterr().out

    gezeigt = [z for z in ausgabe.splitlines() if re.match(r"^  (\?\?| D|D ) ", z)]
    gesamt = len(OEFFENTLICH) + 60 + 1                                         # plus die gelöschte alt.txt
    assert len(gezeigt) == 40
    assert f"... und {gesamt - 40} weitere (insgesamt {gesamt} Zeilen)" in ausgabe


def test_relatives_ziel_gilt_ab_dem_aufrufordner(ve, umg, monkeypatch):
    monkeypatch.setenv("BMS_AUFRUFORDNER", str(umg.tmp))
    assert _lauf(ve, umg, ziel_pfad="oeffentlich") == 0
    assert _dateien(umg.ziel) == OEFFENTLICH


# ── Funde: Personendaten ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pfad, text, regel", [
    ("docs/A.md", "Wohnhaft im Musterweg 1.\n", "Anschrift"),
    ("docs/B.md", "Postleitzahl 12345 genügt.\n", "Anschrift"),
    ("docs/C.md", "Danke an Anna Beispiel für die Hilfe.\n", "Dritte Personen"),
    ("docs/D.md", "Bei Nordfeld Systeme war ich lange.\n", "Firmennamen aus dem Bewerbungsverlauf"),
    ("docs/E.md", "Geschrieben von Max Mustermann.\n", "Name des Nutzers"),
    ("src/f.py", "# Mustermanns Vorgabe vom 11.07.\n", "Name des Nutzers"),
    ("docs/G.md", "Mail an max@beispiel.de bitte.\n", "Private Kontaktdaten"),
    ("docs/H.md", "Profil: linkedin.com/in/max-mustermann\n", "Private Kontaktdaten"),
])
def test_fund_in_einer_datei_verweigert_den_export(ve, umg, capsys, pfad, text, regel):
    _commit(umg.quelle, {pfad: text})
    vorher_ziel = _schnappschuss(umg.ziel)
    vorher_stand = _git_stand(umg.ziel)

    assert _lauf(ve, umg) == 1

    ausgabe = capsys.readouterr().out
    assert f"{pfad}:1  [{regel}]" in ausgabe
    assert "Nichts geschrieben" in ausgabe
    assert _schnappschuss(umg.ziel) == vorher_ziel
    assert _git_stand(umg.ziel) == vorher_stand
    _ohne_begriffe(ausgabe)


def test_allgemeine_regeln_laufen_im_oeffentlichen_umfang_mit(ve, umg, capsys):
    """Benutzerpfad, fremde Mailadresse und Bestands-ID sind Funde, auch in Kommentaren und Tests --
    zusammengesetzt, damit diese Datei sie nicht selbst enthält."""
    text = "\n".join(["pfad = '/Users/" + "jemand/projekt'", "mail = jemand@" + "fremde-firma.de",
                      "Siehe Job " + "4711"]) + "\n"
    _commit(umg.quelle, {"docs/Z.md": text})

    assert _lauf(ve, umg) == 1
    ausgabe = capsys.readouterr().out
    for zeile, regel in ((1, "Absoluter Benutzerpfad"), (2, "E-Mail-Adressen"), (3, "Bestands-IDs")):
        assert f"docs/Z.md:{zeile}  [{regel}]" in ausgabe
    assert "jemand" not in ausgabe and "4711" not in ausgabe


def test_ausgabe_zeigt_nur_laenge_und_satzzeichen_am_anfang(ve, umg, capsys):
    zeile = "    // Wohnhaft im Musterweg 1, mehr steht hier nicht."
    _commit(umg.quelle, {"docs/Z.md": "harmlos\n" + zeile + "\n"})

    assert _lauf(ve, umg) == 1
    ausgabe = capsys.readouterr().out
    assert f"docs/Z.md:2  [Anschrift]  Zeile mit {len(zeile)} Zeichen, Anfang „// “" in ausgabe
    assert "Wohnhaft" not in ausgabe and "mehr steht" not in ausgabe
    _ohne_begriffe(ausgabe)


def test_jeder_fund_einmal_auch_bei_mehreren_treffern_in_einer_zeile(ve, umg, capsys):
    _commit(umg.quelle, {"docs/Z.md": "Musterweg und nochmal Musterweg und Anna Beispiel\n"})
    assert _lauf(ve, umg) == 1
    ausgabe = capsys.readouterr().out
    assert ausgabe.count("docs/Z.md:1  [Anschrift]") == 1
    assert ausgabe.count("docs/Z.md:1  [Dritte Personen]") == 1
    assert "Funde: 2" in ausgabe


def test_name_im_dateipfad_wird_in_der_ausgabe_geschwaerzt(ve, umg, capsys):
    _commit(umg.quelle, {"docs/Mustermann_Notizen.md": "harmlos\n", "docs/Anna_Beispiel.md": "harmlos\n"})

    assert _lauf(ve, umg) == 1
    ausgabe = capsys.readouterr().out
    assert "docs/‹geschwärzt›.md  [Name des Nutzers (Dateipfad)]" in ausgabe
    assert "docs/‹geschwärzt›.md  [Dritte Personen (Dateipfad)]" in ausgabe
    _ohne_begriffe(ausgabe)


def test_erlaubte_nennungen_sind_kein_fund(ve, umg, pd):
    """Zuschreibungsliste (Name in LICENSE/NOTICE), Marke und Repo-Name bleiben ohne Fund."""
    repo = pd.OEFFENTLICHES_REPO
    _commit(umg.quelle, {"NOTICE": "Copyright Max Mustermann\n", "LICENSE": "Max Mustermann\n",
                         "docs/Marke.md": f"Daube.Tech baut das. Quelle: https://github.com/{repo}/issues\n"})
    assert _lauf(ve, umg) == 0


def test_musterdatei_wird_mitgeprueft(ve, umg, capsys):
    extra = umg.tmp / "pruefmuster.txt"
    extra.write_text("# frühere Anschrift\nAltweg\nHans Altmeier\n", encoding="utf-8")
    _commit(umg.quelle, {"docs/Z.md": "Früher im Altweg.\n", "docs/Y.md": "Mit Hans Altmeier.\n"})

    assert _lauf(ve, umg, extra=extra) == 1
    ausgabe = capsys.readouterr().out
    assert "docs/Z.md:1  [Anschrift]" in ausgabe and "docs/Y.md:1  [Dritte Personen]" in ausgabe
    assert "Prüfmuster: Profil und Datenbank gelesen, Musterdatei gelesen." in ausgabe
    _ohne_begriffe(ausgabe)


# ── Funde: Geheimnisse ──────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("art, regel", [
    ("anthropic", "Anthropic-Schlüssel"), ("apify", "Apify-Token"), ("client_secret", "client_secret mit Wert"),
    ("pem", "privater Schlüssel (PEM)"), ("github", "GitHub-Token"), ("github_pat", "GitHub-Token"),
])
def test_geheimnis_verweigert_den_export(ve, umg, capsys, art, regel):
    geheimnis = _geheimnis(art)
    _commit(umg.quelle, {"scripts/lauf.sh": f"export X='{geheimnis}'\n"})
    vorher = _schnappschuss(umg.ziel)

    assert _lauf(ve, umg) == 1

    ausgabe = capsys.readouterr().out
    assert f"scripts/lauf.sh:1  [Geheimnis: {regel}]" in ausgabe
    assert "A1b2C3d4" not in ausgabe and geheimnis not in ausgabe
    assert _schnappschuss(umg.ziel) == vorher


def test_geheimnis_suche_ohne_falschen_alarm(ve, pd):
    def funde(text):
        return ve.geheimnis_funde([pd.Eintrag("docs/x.md", 0o644, text.encode("utf-8"))])

    assert funde("Der Schlüssel beginnt mit sk-" + "ant- und ist geheim.\n") == []
    assert funde("muster = re.compile('sk-" + "ant-[A-Za-z0-9_-]{20,}')\n") == []
    assert funde("CRED = InstalledAppFlow.from_client_" + "secrets_file(pfad)\n") == []
    assert funde('"client_' + 'secret": "<DEIN_SECRET>"\n') == []
    assert funde("client_" + "secret = os.environ['X']\n") == []
    assert funde("-----" + "BEGIN [A-Z ]*" + "PRIVATE KEY-----\n") == []
    assert funde("export GH_TOKEN=ghp" + "_<token>\n") == []
    # eine Binärdatei wird nicht durchsucht
    assert ve.geheimnis_funde([pd.Eintrag("x.bin", 0o644, b"\xff\xfe" + _geheimnis("anthropic").encode())]) == []


def test_geheimnis_in_ausgenommener_datei_verlaesst_das_haus_nicht(ve, umg):
    _commit(umg.quelle, {"tasks/schluessel.txt": _geheimnis("anthropic") + "\n"})
    assert _lauf(ve, umg) == 0
    assert not (umg.ziel / "tasks").exists()


# ── --pruefen ───────────────────────────────────────────────────────────────────────────────────

def test_pruefen_schreibt_nichts_und_braucht_kein_ziel(ve, umg, capsys):
    vorher = _schnappschuss(umg.ziel)

    assert _lauf(ve, umg, "--pruefen", ziel=False) == 0
    assert "Prüfung ohne Fund" in capsys.readouterr().out
    assert _schnappschuss(umg.ziel) == vorher


def test_pruefen_mit_ziel_prueft_das_ziel_nicht(ve, umg):
    """`--pruefen` endet vor der Ziel-Prüfung: auch ein unbrauchbares Ziel ändert den Exit-Code nicht."""
    assert _lauf(ve, umg, "--pruefen", ziel_pfad=umg.tmp / "gibt_es_nicht") == 0
    assert not (umg.tmp / "gibt_es_nicht").exists()


def test_pruefen_meldet_funde(ve, umg, capsys):
    _commit(umg.quelle, {"docs/Z.md": "Im Musterweg.\n"})
    vorher = _schnappschuss(umg.ziel)

    assert _lauf(ve, umg, "--pruefen", ziel=False) == 1
    assert "docs/Z.md:1  [Anschrift]" in capsys.readouterr().out
    assert _schnappschuss(umg.ziel) == vorher


# ── Revision ────────────────────────────────────────────────────────────────────────────────────

def test_ref_ausserhalb_von_main_bricht_ab(ve, umg, capsys):
    _git(umg.quelle, "checkout", "-q", "-b", "entwurf")
    _commit(umg.quelle, {"neu.txt": "noch nicht auf main\n"})
    vorher = _schnappschuss(umg.ziel)

    assert _lauf(ve, umg) == 2                                   # HEAD steht auf dem Nebenzweig
    assert "nicht in main enthalten" in capsys.readouterr().out
    assert _lauf(ve, umg, "--ref", "entwurf") == 2
    assert _schnappschuss(umg.ziel) == vorher

    assert _lauf(ve, umg, "--ref", "main") == 0                  # was auf main liegt, geht
    assert "neu.txt" not in _dateien(umg.ziel)


def test_unbekannte_revision_bricht_ab(ve, umg, capsys):
    assert _lauf(ve, umg, "--ref", "gibt-es-nicht") == 2
    assert "gibt es im Quell-Repo nicht" in capsys.readouterr().out


def test_repo_ohne_main_bricht_ab(ve, umg, capsys):
    _git(umg.quelle, "branch", "-m", "main", "haupt")
    assert _lauf(ve, umg) == 2
    assert "Der Zweig main fehlt" in capsys.readouterr().out


def test_aelterer_stand_per_tag(ve, umg):
    _git(umg.quelle, "tag", "v0")
    _commit(umg.quelle, {"neu.txt": "später\n"})

    assert _lauf(ve, umg, "--ref", "v0") == 0
    assert "neu.txt" not in _dateien(umg.ziel)
    assert _dateien(umg.ziel) == OEFFENTLICH


def test_head_mit_ungesicherten_aenderungen_warnt_und_exportiert_den_commit(ve, umg, capsys):
    (umg.quelle / "README.md").write_text("# Geändert und nicht committet\n", encoding="utf-8")

    assert _lauf(ve, umg) == 0

    assert "Warnung: Der Arbeitsbaum hat ungesicherte Änderungen" in capsys.readouterr().out
    assert (umg.ziel / "README.md").read_bytes() == BASIS["README.md"].encode()      # der Commit, nicht die Datei


def test_sauberer_arbeitsbaum_gibt_keine_warnung(ve, umg, capsys):
    assert _lauf(ve, umg) == 0
    assert "Warnung" not in capsys.readouterr().out


# ── Fehlende Quellen ────────────────────────────────────────────────────────────────────────────

def test_ohne_profil_kein_export(ve, umg, capsys):
    (umg.quelle / "config" / "profil.md").unlink()
    vorher = _schnappschuss(umg.ziel)

    assert _lauf(ve, umg) == 2

    ausgabe = capsys.readouterr().out
    assert "Ohne Profil und Datenbank lässt sich nicht prüfen, ob persönliche Daten im Export stehen." in ausgabe
    assert "Das Profil" in ausgabe                               # der Hinweis aus muster_laden
    assert _schnappschuss(umg.ziel) == vorher


def test_ohne_datenbank_kein_export(ve, umg, capsys):
    vorher = _schnappschuss(umg.ziel)
    assert _lauf(ve, umg, db=umg.tmp / "fehlt.sqlite") == 2
    ausgabe = capsys.readouterr().out
    assert "Ohne Profil und Datenbank lässt sich nicht prüfen, ob persönliche Daten im Export stehen." in ausgabe
    assert "Die Datenbank" in ausgabe
    assert _schnappschuss(umg.ziel) == vorher


def test_ohne_profil_auch_nicht_mit_pruefen(ve, umg):
    (umg.quelle / "config" / "profil.md").unlink()
    assert _lauf(ve, umg, "--pruefen", ziel=False) == 2


def test_standard_datenbank_liegt_unter_bms_data_dir(ve, umg, monkeypatch):
    """Ohne `db_pfad` gilt `BMS_DATA_DIR` (Tests setzen es auf einen leeren Ordner): dort liegt keine
    Datenbank, also Abbruch; mit der Datenbank im Ordner geht es durch."""
    daten = umg.tmp / "daten_leer"
    daten.mkdir()
    args = ["--pruefen"]
    assert ve.main(args, projekt_root=umg.quelle, extra=umg.extra) == 2
    shutil.copyfile(umg.db, daten / "bewerbung.sqlite")
    assert ve.main(args, projekt_root=umg.quelle, extra=umg.extra) == 0


# ── Ziel-Prüfung ────────────────────────────────────────────────────────────────────────────────

def test_ziel_ohne_git_bricht_ab(ve, umg, capsys):
    ohne = umg.tmp / "kein_repo"
    ohne.mkdir()
    (ohne / "x.txt").write_text("bleibt\n", encoding="utf-8")

    assert _lauf(ve, umg, ziel_pfad=ohne) == 2

    assert "keine Git-Arbeitskopie" in capsys.readouterr().out
    assert _dateien(ohne) == {"x.txt"}


def test_ziel_das_nicht_existiert_bricht_ab(ve, umg, capsys):
    assert _lauf(ve, umg, ziel_pfad=umg.tmp / "gibt_es_nicht") == 2
    assert "ist kein Ordner" in capsys.readouterr().out
    assert not (umg.tmp / "gibt_es_nicht").exists()


def test_ordner_in_einem_fremden_repo_ist_kein_ziel(ve, umg, pd, capsys):
    """Ein Unterordner einer Arbeitskopie hat kein eigenes `.git` -- git fände den `origin` des Elternrepos."""
    unter = umg.ziel / "unterordner"
    unter.mkdir()
    (unter / "x.txt").write_text("bleibt\n", encoding="utf-8")

    assert _lauf(ve, umg, ziel_pfad=unter) == 2
    assert "keine Git-Arbeitskopie" in capsys.readouterr().out
    assert (unter / "x.txt").is_file() and (umg.ziel / "alt.txt").is_file()


@pytest.mark.parametrize("origin", [
    "https://github.com/anderes-konto/etwas.git",
    "https://gitlab.com/{repo}.git",
    "https://github.com/{repo}-alt.git",
    "{ssh}{konto}-x/{name}.git",
    "/lokal/{name}",
])
def test_fremder_origin_bricht_ab(ve, umg, pd, capsys, origin):
    konto, name = pd.OEFFENTLICHES_REPO.split("/")
    _git(umg.ziel, "remote", "set-url", "origin", origin.format(
        repo=pd.OEFFENTLICHES_REPO, konto=konto, name=name, ssh=_at("git", "github.com:")))
    vorher = _schnappschuss(umg.ziel)

    assert _lauf(ve, umg) == 2

    assert "zeigt nicht auf das öffentliche Repo" in capsys.readouterr().out
    assert _schnappschuss(umg.ziel) == vorher


def test_fremde_push_adresse_bricht_ab(ve, umg, capsys):
    _git(umg.ziel, "remote", "set-url", "--push", "origin", "https://example.com/anderswo.git")
    assert _lauf(ve, umg) == 2
    assert "Push-Adresse" in capsys.readouterr().out


def test_ziel_ohne_origin_bricht_ab(ve, umg, pd, capsys):
    ohne = _ziel_repo(umg.tmp / "ohne_origin", pd, origin=False, dateien={"alt.txt": "alt\n"})
    assert _lauf(ve, umg, ziel_pfad=ohne) == 2
    assert "keinen Remote origin" in capsys.readouterr().out
    assert _dateien(ohne) == {"alt.txt"}


@pytest.mark.parametrize("aenderung", ["geaendert", "neue_datei", "geloescht", "vorgemerkt"])
def test_ziel_mit_ungesicherten_aenderungen_bricht_ab(ve, umg, capsys, aenderung):
    if aenderung == "geaendert":
        (umg.ziel / "alt.txt").write_text("von Hand geändert\n", encoding="utf-8")
    elif aenderung == "neue_datei":
        (umg.ziel / "neu.txt").write_text("von Hand\n", encoding="utf-8")
    elif aenderung == "geloescht":
        (umg.ziel / "alt.txt").unlink()
    else:
        (umg.ziel / "neu.txt").write_text("von Hand\n", encoding="utf-8")
        _git(umg.ziel, "add", "neu.txt")
    vorher = _schnappschuss(umg.ziel)

    assert _lauf(ve, umg) == 2

    assert "ungesicherte Änderungen" in capsys.readouterr().out
    assert _schnappschuss(umg.ziel) == vorher


def test_ziel_gleich_quell_repo_bricht_ab(ve, umg, pd, capsys):
    """Selbst wenn der `origin` des Quell-Repos stimmt: gespiegelt wird nie in das Quell-Repo."""
    _git(umg.quelle, "remote", "add", "origin", _url(pd))
    vorher = _schnappschuss(umg.quelle)

    assert _lauf(ve, umg, ziel_pfad=umg.quelle) == 2

    assert "Quell-Repo" in capsys.readouterr().out
    assert _schnappschuss(umg.quelle) == vorher
    assert (umg.quelle / "tasks" / "notiz.md").is_file()


def test_arbeitsbaum_des_quell_repos_ist_kein_ziel(ve, umg, pd, capsys):
    """Ein Worktree teilt das Git-Verzeichnis des Quell-Repos -- gleiche Historie, gleiches Risiko."""
    _git(umg.quelle, "remote", "add", "origin", _url(pd))
    worktree = umg.tmp / "worktree"
    _git(umg.quelle, "worktree", "add", "-q", "-b", "zweit", str(worktree))

    assert _lauf(ve, umg, ziel_pfad=worktree) == 2
    assert "Quell-Repo" in capsys.readouterr().out
    assert (worktree / "README.md").is_file()


def test_ziel_das_das_quell_repo_enthaelt_bricht_ab(ve, tmp_path, pd, capsys):
    huelle = _ziel_repo(tmp_path / "huelle", pd)
    quelle = _neues_repo(huelle / "quelle")
    _commit(quelle, BASIS)
    (quelle / "config").mkdir()
    (quelle / "config" / "profil.md").write_text(PROFIL, encoding="utf-8")

    assert ve.main(["--ziel", str(huelle)], projekt_root=quelle, db_pfad=_db(tmp_path),
                   extra=tmp_path / "x.txt") == 2

    assert "enthält es" in capsys.readouterr().out
    assert (quelle / "README.md").is_file()


# ── Commit-Identität des Ziels (P2-84) ──────────────────────────────────────────────────────────

MELDUNG_IDENTITAET = "Die Commit-Adresse der Arbeitskopie ist keine GitHub-noreply-Adresse."
MELDUNG_VERLAUF = "Ein Commit oder Tag im Ziel trägt eine andere Adresse als die GitHub-noreply-Adresse."


@pytest.mark.parametrize("adresse", [_noreply(), _noreply(nummer=None), _noreply(konto="a" * 39),
                                     _noreply(konto="Beispiel-Konto-1")])
def test_ziel_mit_noreply_adresse_besteht(ve, umg, adresse):
    _git(umg.ziel, "config", "user.email", adresse)
    assert _lauf(ve, umg) == 0
    assert _dateien(umg.ziel) == OEFFENTLICH


def test_ziel_mit_privater_adresse_bricht_ab(ve, umg, capsys):
    _git(umg.ziel, "config", "user.email", _privat())

    ausgabe = _identitaets_abbruch(ve, umg, capsys, MELDUNG_IDENTITAET, _privat(), "privat.person")

    assert f'git -C "{umg.ziel.resolve()}" config user.email <ID>+<Konto>' in ausgabe   # mit Platzhaltern
    assert "Umgebungsvariable" not in ausgabe                    # keine gesetzt: kein Hinweis darauf


def test_ziel_ohne_user_email_bricht_ab(ve, umg, capsys):
    """Ohne Einstellung rät git je nach Rechner eine Adresse aus Benutzer und Rechnername oder bricht ab:
    beides ist ein Abbruch, und die geratene Adresse steht nie in der Ausgabe."""
    _git(umg.ziel, "config", "--unset", "user.email")
    geraten = subprocess.run(["git", "-C", str(umg.ziel), "var", "GIT_AUTHOR_IDENT"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
    adressen = re.findall(r"<([^<>]+)>", geraten.stdout + geraten.stderr)
    adressen += re.findall(r"got '([^']+)'", geraten.stderr)      # „unable to auto-detect email address“

    _identitaets_abbruch(ve, umg, capsys, MELDUNG_IDENTITAET, *adressen)


def test_githubs_eigene_adresse_ist_keine_identitaet_fuer_eigene_commits(ve, umg, capsys):
    _git(umg.ziel, "config", "user.email", _at("noreply", "github.com"))
    _identitaets_abbruch(ve, umg, capsys, MELDUNG_IDENTITAET, _at("noreply", "github.com"))


@pytest.mark.parametrize("variable, ohne_einstellung", [("GIT_AUTHOR_EMAIL", False),
                                                        ("GIT_COMMITTER_EMAIL", False),
                                                        ("EMAIL", True)])
def test_wirksame_identitaet_zaehlt_auch_die_umgebung(ve, umg, capsys, monkeypatch, variable, ohne_einstellung):
    """`GIT_AUTHOR_EMAIL` und `GIT_COMMITTER_EMAIL` gehen der Einstellung des Ziels vor, `EMAIL` gilt ohne
    Einstellung: In allen drei Fällen zeichnete `git commit` mit der privaten Adresse, obwohl
    `git config user.email` im Ziel stimmen könnte. Der Hinweis in der Meldung nennt die Variable."""
    if ohne_einstellung:
        _git(umg.ziel, "config", "--unset", "user.email")
    monkeypatch.setenv(variable, _privat())

    ausgabe = _identitaets_abbruch(ve, umg, capsys, MELDUNG_IDENTITAET, _privat(), "privat.person")

    assert "Umgebungsvariable" in ausgabe and variable in ausgabe


def test_git_meldung_mit_der_adresse_bleibt_draussen(ve, umg, capsys, monkeypatch):
    """Scheitert `git var` (hier: leerer Name), nennt git die Adresse in seiner Fehlermeldung. Sie darf nicht
    in die Ausgabe des Werkzeugs gelangen."""
    _git(umg.ziel, "config", "user.email", _privat())
    monkeypatch.setenv("GIT_AUTHOR_NAME", "")
    if sys.platform != "win32":                                  # dort löscht ein leerer Wert die Variable
        probe = subprocess.run(["git", "-C", str(umg.ziel), "var", "GIT_AUTHOR_IDENT"], capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
        assert probe.returncode != 0 and _privat() in probe.stderr, "Voraussetzung des Tests: git nennt sie"

    ausgabe = _identitaets_abbruch(ve, umg, capsys, MELDUNG_IDENTITAET, _privat(), "privat.person")

    assert "empty ident name" not in ausgabe and "fatal" not in ausgabe


@pytest.mark.parametrize("fall", ["autor", "committer", "anderer_zweig"])
def test_vorhandener_commit_mit_fremder_adresse_bricht_ab(ve, umg, capsys, fall):
    """Autor ODER Committer eines vorhandenen Commits (auch auf einem anderen Zweig) mit fremder Adresse."""
    if fall == "anderer_zweig":
        _git(umg.ziel, "checkout", "-q", "-b", "nebenzweig")
        _git_als(umg.ziel, _privat(), "commit", "-q", "--allow-empty", "-m", "fremd")
        _git(umg.ziel, "checkout", "-q", "main")
    elif fall == "autor":
        _git_als(umg.ziel, _privat(), "commit", "-q", "--allow-empty", "-m", "fremd", committer=_noreply())
    else:
        _git_als(umg.ziel, _noreply(), "commit", "-q", "--allow-empty", "-m", "fremd", committer=_privat())
    assert _git(umg.ziel, "status", "--short") == ""

    _identitaets_abbruch(ve, umg, capsys, MELDUNG_VERLAUF, _privat(), "privat.person")


def test_tag_mit_fremder_adresse_bricht_ab(ve, umg, capsys):
    """Die Commits sind in Ordnung, nur das annotierte Tag trägt eine fremde Tagger-Adresse."""
    _git_als(umg.ziel, _privat(), "tag", "-a", "v0.1", "-m", "fremd")
    assert _git(umg.ziel, "log", "--all", "--format=%ae%n%ce").split() == [_noreply()] * 2

    _identitaets_abbruch(ve, umg, capsys, MELDUNG_VERLAUF, _privat(), "privat.person")


def test_leichtes_tag_und_tag_mit_noreply_adresse_bestehen(ve, umg):
    """Ein leichtes Tag hat keinen Tagger (leere Zeile) und wird übersprungen."""
    _git(umg.ziel, "tag", "leicht")
    _git_als(umg.ziel, _noreply(), "tag", "-a", "v0.1", "-m", "mit noreply")
    assert _lauf(ve, umg) == 0


def test_githubs_eigene_adressen_im_verlauf_sind_erlaubt(ve, umg):
    """Ein Commit über die Weboberfläche trägt als Committer die allgemeine Absenderadresse von GitHub, ein
    Dependabot-Commit die Bot-Form. Beides darf im Verlauf stehen."""
    web = _at("noreply", "github.com")
    bot = _at("4711+dependabot[bot]", "users.noreply.github.com")
    _git_als(umg.ziel, _noreply(), "commit", "-q", "--allow-empty", "-m", "Weboberfläche", committer=web)
    _git_als(umg.ziel, bot, "commit", "-q", "--allow-empty", "-m", "Bot")
    _git_als(umg.ziel, _noreply(), "tag", "-a", "v0.1", "-m", "Tag", committer=web)

    assert _lauf(ve, umg) == 0


def test_leeres_repo_besteht_die_pruefung_des_verlaufs(ve, umg, pd):
    """Ohne Commit und ohne Tag gibt es keine Adressen im Verlauf (und `git log --all` wird nicht gebraucht)."""
    leer = _ziel_repo(umg.tmp / "leer", pd)
    assert _git(leer, "for-each-ref") == ""

    assert _lauf(ve, umg, ziel_pfad=leer) == 0
    assert _dateien(leer) == OEFFENTLICH


def test_leeres_repo_mit_privater_adresse_bricht_ab(ve, umg, pd, capsys):
    """Auch ohne Verlauf zählt die Adresse, mit der der erste Commit entstünde."""
    leer = _ziel_repo(umg.tmp / "leer", pd)
    _git(leer, "config", "user.email", _privat())

    assert _lauf(ve, umg, ziel_pfad=leer) == 2
    ausgabe = capsys.readouterr().out
    assert MELDUNG_IDENTITAET in ausgabe and _privat() not in ausgabe
    assert _dateien(leer) == set()


def test_identitaet_wird_nach_dem_origin_geprueft(ve, umg, capsys):
    """Reihenfolge der Meldungen: Zuerst der `origin`, dann die Identität, dann der saubere Stand."""
    _git(umg.ziel, "config", "user.email", _privat())
    (umg.ziel / "neu.txt").write_text("von Hand\n", encoding="utf-8")
    assert _lauf(ve, umg) == 2
    assert MELDUNG_IDENTITAET in capsys.readouterr().out         # vor „ungesicherte Änderungen“

    _git(umg.ziel, "remote", "set-url", "origin", "https://example.com/anderswo.git")
    assert _lauf(ve, umg) == 2
    assert "zeigt nicht auf das öffentliche Repo" in capsys.readouterr().out


def test_pruefen_braucht_keine_identitaet(ve, umg):
    """`--pruefen` endet vor der Ziel-Prüfung: auch eine private Adresse im Ziel ändert nichts."""
    _git(umg.ziel, "config", "user.email", _privat())
    assert _lauf(ve, umg, "--pruefen", ziel=False) == 0


# ── Spiegeln ────────────────────────────────────────────────────────────────────────────────────

@UNIX_ONLY
def test_ausfuehrbar_bit_wird_uebernommen(ve, umg):
    assert _lauf(ve, umg) == 0
    for pfad in OEFFENTLICH:
        modus = (umg.ziel / pfad).stat().st_mode
        assert bool(modus & 0o111) == (pfad == "tool.sh"), pfad


def test_zeilenenden_bleiben_byte_genau(ve, umg):
    _commit(umg.quelle, {"crlf.txt": b"eins\r\nzwei\r\n", "gemischt.txt": b"a\nb\r\nc\n", "leer.txt": b""})
    assert _lauf(ve, umg) == 0
    assert (umg.ziel / "start.bat").read_bytes() == b"@echo off\r\necho hi\r\n"
    assert (umg.ziel / "crlf.txt").read_bytes() == b"eins\r\nzwei\r\n"
    assert (umg.ziel / "gemischt.txt").read_bytes() == b"a\nb\r\nc\n"
    assert (umg.ziel / "leer.txt").read_bytes() == b""


def test_versteckte_dateien_und_ordner_im_ziel_werden_geloescht(ve, umg):
    _commit(umg.ziel, {".versteckt": "x\n", "ordner/unter/datei.txt": "x\n", ".github/workflows/alt.yml": "x\n"})
    assert _lauf(ve, umg) == 0
    assert _dateien(umg.ziel) == OEFFENTLICH
    assert not (umg.ziel / "ordner").exists() and not (umg.ziel / ".github").exists()


@UNIX_ONLY
def test_symlink_im_ziel_wird_entfernt_aber_nicht_verfolgt(ve, umg):
    ausserhalb = umg.tmp / "ausserhalb"
    ausserhalb.mkdir()
    (ausserhalb / "wichtig.txt").write_text("darf bleiben\n", encoding="utf-8")
    (umg.ziel / "verweis").symlink_to(ausserhalb, target_is_directory=True)
    _git(umg.ziel, "add", "verweis")
    _git(umg.ziel, "commit", "-q", "-m", "Verweis")

    assert _lauf(ve, umg) == 0

    assert not (umg.ziel / "verweis").exists() and not (umg.ziel / "verweis").is_symlink()
    assert (ausserhalb / "wichtig.txt").read_text(encoding="utf-8") == "darf bleiben\n"


def test_git_verzeichnis_bleibt_auch_wenn_es_nosync_heisst(ve, umg):
    """Wie im Projekt unter iCloud: `.git` ist eine Zeiger-Datei, das Verzeichnis heißt `.git.nosync`."""
    shutil.move(str(umg.ziel / ".git"), str(umg.ziel / ".git.nosync"))
    (umg.ziel / ".git").write_text("gitdir: .git.nosync\n", encoding="utf-8")
    with open(umg.ziel / ".git.nosync" / "info" / "exclude", "a", encoding="utf-8") as f:
        f.write(".git.nosync/\n")                                  # wie in der .gitignore des Projekts
    assert _git(umg.ziel, "status", "--short") == ""

    assert _lauf(ve, umg) == 0

    assert (umg.ziel / ".git.nosync" / "HEAD").is_file()
    assert _git(umg.ziel, "rev-list", "--all", "--count") == "1"
    assert "D alt.txt" in _git(umg.ziel, "status", "--short")


def test_pfade_ausserhalb_des_ziels_werden_abgelehnt(ve, pd):
    eintraege = [pd.Eintrag("docs/a.md", 0o644, b"x")]
    ve._pfade_pruefen(eintraege, frozenset({".git"}))                          # in Ordnung
    for schlecht in ("../aussen.txt", "/abs.txt", ".git/config", "a//b.txt", "a/./b.txt", "a\\b.txt"):
        with pytest.raises(ve.VeroeffentlichungFehler):
            ve._pfade_pruefen([pd.Eintrag(schlecht, 0o644, b"x")], frozenset({".git"}))
    with pytest.raises(ve.VeroeffentlichungFehler):
        ve._pfade_pruefen([pd.Eintrag(".git.nosync/x", 0o644, b"x")], frozenset({".git", ".git.nosync"}))


@UNIX_ONLY
def test_symlink_im_quell_stand_wird_gemeldet_nicht_exportiert(ve, umg, capsys):
    (umg.quelle / "verweis").symlink_to("README.md")
    _commit(umg.quelle, {})
    assert _lauf(ve, umg) == 0
    assert "1 Symlink(s) oder Submodul(e)" in capsys.readouterr().out
    assert not (umg.ziel / "verweis").exists()


# ── Einheiten ───────────────────────────────────────────────────────────────────────────────────

def test_origin_adressen(ve, pd):
    konto, name = pd.OEFFENTLICHES_REPO.split("/")
    repo = pd.OEFFENTLICHES_REPO
    ssh, ssh_url = _at("git", "github.com:"), "ssh://" + _at("git", "github.com/")
    richtig = [f"https://github.com/{repo}", f"https://github.com/{repo}.git", f"https://github.com/{repo}/",
               f"{ssh}{repo}.git", f"{ssh}{repo}", f"{ssh_url}{repo}.git",
               "https://" + _at("nutzer", "github.com/") + f"{repo}.git", f"  https://github.com/{repo}.git\n"]
    falsch = [f"https://github.com/{konto}/{name}-alt.git", f"https://github.com/{konto}-x/{name}.git",
              f"https://github.com/x{konto}/{name}.git", f"https://github.com/{repo}/extra",
              f"https://gitlab.com/{repo}.git", f"https://evilgithub.com/{repo}.git",
              f"http://github.com/{repo}.git", _at("git", f"evilgithub.com:{repo}.git"), f"file:///x/{repo}",
              f"/lokal/{name}", "", "https://github.com/"]
    assert all(ve.origin_ist_oeffentlich(u) for u in richtig)
    assert not any(ve.origin_ist_oeffentlich(u) for u in falsch)


def test_noreply_adressen(ve):
    domain = "users.noreply.github.com"
    richtig = [_at("4711+beispiel-konto", domain), _at("beispiel-konto", domain), _at("1+a", domain),
               _at("a", domain), _at("a" * 39, domain), _at("0815+" + "b" * 39, domain),
               _at("Beispiel-Konto", domain)]
    falsch = [_at("a" * 40, domain), _at("a.b", domain), _at("a_b", domain), _at("4711+", domain),
              _at("+a", domain), _at("4711+a+b", domain), _at("x y", domain), _at("", domain),
              _at("beispiel", "noreply.github.com"), _at("beispiel", "github.com"),
              _at("beispiel", domain + ".example.org"), _at("beispiel", "x" + domain),
              _at("beispiel", "users.noreply.github.de"), _privat(), _at("autor", "example.com"), "",
              "beispiel", _noreply() + "\n", " " + _noreply(), _at("noreply", "github.com"),
              _at("4711+dependabot[bot]", domain)]
    assert all(ve.noreply_adresse(a) for a in richtig)
    assert not any(ve.noreply_adresse(a) for a in falsch)


def test_githubs_eigene_adressen_im_verlauf(ve):
    domain = "users.noreply.github.com"
    erlaubt = [_noreply(), _noreply(nummer=None), _at("noreply", "github.com"),
               _at("4711+dependabot[bot]", domain), _at("49699333+dependabot[bot]", domain)]
    verboten = [_privat(), "", _at("noreply", "github.com.example.org"), _at("x-noreply", "github.com"),
                _at("dependabot[bot]", domain), _at("4711+dependabot[bot]", "example.com"),
                _at("4711+[bot]", domain), _at("4711+dependabot[bot]", domain) + "x",
                _at("NoReply", "github.com")]
    assert all(ve.verlauf_adresse_erlaubt(a) for a in erlaubt)
    assert not any(ve.verlauf_adresse_erlaubt(a) for a in verboten)


def test_zeile_beschreiben_zeigt_nie_buchstaben_oder_ziffern(ve):
    assert ve._zeile_beschreiben("    # Max Mustermann") == "Zeile mit 20 Zeichen, Anfang „# “"
    assert ve._zeile_beschreiben("Max Mustermann") == "Zeile mit 14 Zeichen"
    assert ve._zeile_beschreiben("- **Name:** Max") == "Zeile mit 15 Zeichen, Anfang „- **“"
    assert ve._zeile_beschreiben("12345 Musterstadt") == "Zeile mit 17 Zeichen"
    assert ve._zeile_beschreiben("") == "Zeile mit 0 Zeichen"
    lang = ve._zeile_beschreiben("////////////////////////////////// und so weiter")
    assert lang.count("/") == 8                                  # höchstens acht Zeichen Anfang


def test_oeffentliche_eintraege_trennt_nicht_oeffentliches_ab(ve, pd):
    eintraege = [pd.Eintrag(p, 0o644, b"x") for p in
                 ("README.md", "tasks/a.md", "tasks/unter/b.md", "tasksfremd.md", ".claude/launch.json",
                  ".claude/launch.json.alt", ".claude/skills/x/SKILL.md")]
    behalten, ausgenommen = ve.oeffentliche_eintraege(eintraege)
    assert ausgenommen == ["tasks/a.md", "tasks/unter/b.md", ".claude/launch.json"]
    assert [e.pfad for e in behalten] == ["README.md", "tasksfremd.md", ".claude/launch.json.alt",
                                           ".claude/skills/x/SKILL.md"]


def test_maskierte_pfade_ohne_muster_bleiben_unveraendert(ve, pd):
    pfade = ["docs/a.md", "src/Mustermann.py"]
    assert ve._maskierte_pfade(pfade, pd.Muster()) == {p: p for p in pfade}


def test_modul_nennt_kein_muster_in_der_repr_des_ergebnisses(ve, umg):
    """`Ergebnis` trägt das Muster; seine Darstellung darf nichts verraten (nur Zahlen)."""
    ergebnis = ve.exportieren(ziel=None, nur_pruefen=True, projekt_root=umg.quelle, db_pfad=umg.db,
                              extra=umg.extra, melden=lambda _t: None)
    _ohne_begriffe(repr(ergebnis.muster) + str(ergebnis.muster))
    assert ergebnis.funde == () and ergebnis.anzahl_dateien == len(OEFFENTLICH) and not ergebnis.geschrieben


# ── Aufruf und Skript ───────────────────────────────────────────────────────────────────────────

def test_aufruf_ohne_ziel_ist_ein_aufruffehler(ve, umg, capsys):
    assert ve.main([], projekt_root=umg.quelle, db_pfad=umg.db, extra=umg.extra) == 3
    assert "--ziel fehlt" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [["--gibt-es-nicht"], ["--pruefen", "--ref=-x"], ["--ziel"], ["--pr"]])
def test_falscher_aufruf_gibt_exit_3(ve, umg, argv):
    assert ve.main(argv, projekt_root=umg.quelle, db_pfad=umg.db, extra=umg.extra) == 3


def test_hilfe_gibt_exit_0(ve, umg, capsys):
    assert ve.main(["-h"], projekt_root=umg.quelle, db_pfad=umg.db, extra=umg.extra) == 0
    assert "--ziel" in capsys.readouterr().out


def test_exit_codes_sind_wie_vereinbart(ve):
    assert (ve.EXIT_OK, ve.EXIT_FUNDE, ve.EXIT_ABBRUCH, ve.EXIT_AUFRUF) == (0, 1, 2, 3)


def test_skript_reicht_argumente_an_das_modul_durch():
    skript = PROJEKT_ROOT / "scripts" / "veroeffentlichen.sh"
    text = skript.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/zsh\n")
    assert '"$VENV" -m pipeline.veroeffentlichung "$@"' in text
    assert 'cd "$BACKEND"' in text and "bewerbung_mgmt_venv" in text
    assert "BMS_AUFRUFORDNER" in text
    if sys.platform != "win32":
        assert os.access(skript, os.X_OK)


def test_doku_nennt_dieselben_befehle_wie_die_naechsten_schritte():
    """docs/RELEASE.md, Abschnitt „Veröffentlichen“, und die Hinweise des Werkzeugs beschreiben denselben
    Ablauf: Commit mit `-s`, `main` pushen, CI abwarten, annotiertes Tag, Tag pushen, Release prüfen, dazu die
    einmalige Identität. Ändert sich eine Seite, muss die andere folgen."""
    text = (PROJEKT_ROOT / "docs" / "RELEASE.md").read_text(encoding="utf-8")
    abschnitt = text.split("\n## Veröffentlichen\n", 1)[1]

    for befehl in ('commit -s -m "BMS X.Y.Z"', "push origin main", 'tag -a vX.Y.Z -m "BMS X.Y.Z"',
                   "push origin vX.Y.Z", "scripts/release.sh abholen X.Y.Z", "scripts/release.sh freigeben",
                   "scripts/veroeffentlichen.sh --ziel <Arbeitskopie> --ref vX.Y.Z", "add -A",
                   "config user.email", "git clone"):
        assert befehl in abschnitt, f"{befehl!r} fehlt im Abschnitt „Veröffentlichen“"
    assert abschnitt.index("commit -s") < abschnitt.index("push origin main") < abschnitt.index("tag -a") \
        < abschnitt.index("push origin vX.Y.Z")
    assert "wird dann ergänzt" not in text
    assert "Pull Request" in abschnitt and "Co-authored-by" in abschnitt     # Beiträge Dritter


def test_werkzeug_gehoert_nicht_ins_kundenpaket():
    from pipeline import kundenpaket
    ausgeschlossen = {muster for muster, _grund in kundenpaket.AUSSCHLUESSE}
    assert {"backend/pipeline/veroeffentlichung.py", "scripts/veroeffentlichen.sh"} <= ausgeschlossen


# ── Wächter über den echten Stand ───────────────────────────────────────────────────────────────

def test_echter_stand_hat_keine_funde_mit_allgemeinen_regeln():
    """Der öffentliche Baum des echten Projekts (versionierte und neue, nicht ignorierte Dateien des
    Arbeitsbaums, minus NICHT_OEFFENTLICH) besteht die Prüfung im Umfang „oeffentlich“ und die
    Geheimnis-Suche -- MIT LEEREM MUSTER: nur die allgemeinen Regeln (fremde Mailadressen, Telefonnummern,
    Bestands-IDs, absolute Benutzerpfade) und die Geheimnisse. Läuft in der CI ohne Profil und Datenbank.
    Die persönlichen Muster prüft erst `scripts/veroeffentlichen.sh --pruefen` auf dem Rechner mit den
    lokalen Quellen. Rein lesend; die Meldung nennt nur Datei, Zeile und Regel.

    Quelle ist der Arbeitsbaum (wie beim Wächter in test_kundenpaket.py), nicht `git archive HEAD`: so
    schlägt der Test schon VOR dem Commit an. In der CI sind beide gleich."""
    from pipeline import kundenpaket, personendaten, veroeffentlichung

    roh, _uebersprungen = kundenpaket.sammle_aus_arbeitsbaum(kundenpaket.PROJECT_ROOT)
    eintraege, _ausgenommen = veroeffentlichung.oeffentliche_eintraege(roh)
    assert eintraege, "keine Dateien im echten Stand gefunden"

    funde = veroeffentlichung.alle_funde(eintraege, personendaten.Muster())
    assert funde == [], f"{len(funde)} Fund(e) im öffentlichen Baum:\n" + "\n".join(
        f"  {f.pfad}:{f.zeile}  [{f.regel}]" for f in funde)
