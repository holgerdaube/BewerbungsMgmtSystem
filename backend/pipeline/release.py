#!/usr/bin/env python3
"""Freigabe-Werkzeug (P2-51 Arbeitspaket U2b) -- hebt `VERSION` an, schreibt den
Unveroeffentlicht-Abschnitt von `CHANGELOG.md` fest, committet, setzt ein annotiertes Tag
`vX.Y.Z` und pusht main + Tag in das Entwicklungs-Repo (`origin`). Seit P2-84 entsteht dort KEIN
Release mehr: `.github/workflows/release.yml` laeuft bei einem Tag-Push nur im oeffentlichen Repo
(`personendaten.OEFFENTLICHES_REPO`). Dorthin kommt der Stand per Export
(`scripts/veroeffentlichen.sh`, docs/RELEASE.md, Abschnitt Veroeffentlichen); der Tag-Push im
oeffentlichen Repo baut das Kundenpaket und veroeffentlicht es als GitHub Release (P2-51 Paket U2a
fuer den Paketbau selbst). `abholen` laedt aus dem oeffentlichen Repo.

WARUM ALLE PRUEFUNGEN VOR DER ERSTEN AENDERUNG: Ein Commit/Tag/Push laesst sich nicht sauber
zuruecknehmen, sobald andere Stellen (CI, ein zweiter Klon) ihn schon gesehen haben. Deshalb
laufen ALLE Pruefungen (Branch, sauberer Arbeitsbaum, Sync mit origin, gruene CI, Version/Tag
frei, CHANGELOG formgerecht, Paketpruefung ohne Funde) VOR jeder Datei-Aenderung -- erst danach
schreibt `freigeben()` ueberhaupt etwas. Scheitert ein Schritt NACH dem Commit trotzdem (Netz,
Tag existiert doch schon, Push abgelehnt), nimmt das Werkzeug NICHTS automatisch zurueck --
das koennte Objekte loeschen, die woanders schon gefetcht wurden. Stattdessen druckt es die
genauen Befehle, mit denen der Maintainer von Hand fortsetzt.

NIE GEGEN DAS ECHTE REPO GETESTET: Alle git-Ablaeufe hier (fetch/push/tag) sind fuer den
ECHTEN Gebrauch gedacht -- die Tests dieses Moduls laufen ausschliesslich gegen Wegwerf-Repos
in `tmp_path` mit einem lokalen bare-Repo als "origin" (s. test_release.py). `gh` wird nur
lesend benutzt (`gh run list`) bzw. beim Download (`gh release download`) -- in Tests immer per
monkeypatch ersetzt, nie ein echter Aufruf.

CLI (aus backend/):
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.release freigeben patch --probe
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.release freigeben 1.2.0
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.release notizen 1.2.0
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.release abholen 1.2.0
Bequemer Aufruf vom Projekt-Root: `scripts/release.sh` (reicht Argumente 1:1 durch).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import date
from pathlib import Path

from pipeline import changelog
from pipeline import kundenpaket
from pipeline import uebersetzung
from pipeline.kundenpaket import PROJECT_ROOT
from pipeline.personendaten import OEFFENTLICHES_REPO

_STUFEN = ("patch", "minor", "major")


class ReleaseFehler(Exception):
    """Eine Pruefung hat abgelehnt oder ein git/gh-Aufruf ist gescheitert -- die Meldung ist
    direkt lesbar, `main()` druckt sie ohne Traceback."""


# ── git/gh-Hilfsfunktionen ───────────────────────────────────────────────────────────────
# Eigene, schlanke Kopie statt Import aus kundenpaket.py: dieses Modul darf kundenpaket.py
# nicht aendern (Leitplanke U2b), und die Fehlerklasse muss ReleaseFehler sein, damit main()
# EINEN Fangpunkt hat.

def _git(args: list[str], projekt_root: Path) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", *args], cwd=projekt_root, capture_output=True, check=True)
    except FileNotFoundError as exc:
        raise ReleaseFehler("git ist auf diesem Rechner nicht verfuegbar.") from exc
    except subprocess.CalledProcessError as exc:
        meldung = exc.stderr.decode("utf-8", "replace").strip()
        raise ReleaseFehler(f"git {' '.join(args)} fehlgeschlagen: {meldung}") from exc


def _gh(args: list[str], projekt_root: Path) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["gh", *args], cwd=projekt_root, capture_output=True, check=True)
    except FileNotFoundError as exc:
        raise ReleaseFehler("gh (GitHub CLI) ist auf diesem Rechner nicht verfuegbar.") from exc
    except subprocess.CalledProcessError as exc:
        meldung = exc.stderr.decode("utf-8", "replace").strip()
        raise ReleaseFehler(f"gh {' '.join(args)} fehlgeschlagen: {meldung}") from exc


# ── Einzelpruefungen (jede wirft ReleaseFehler mit einer klaren Meldung) ──────────────────

def _pruefe_branch_main(projekt_root: Path) -> None:
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], projekt_root).stdout.decode("utf-8").strip()
    if branch != "main":
        raise ReleaseFehler(f"Aktueller Branch ist „{branch}“, nicht „main“. Erst zu main wechseln.")


def _pruefe_sauberer_arbeitsbaum(projekt_root: Path) -> list[str]:
    """Versionierte Aenderungen (gestaged oder nicht) blockieren die Freigabe. Unversionierte
    Dateien blockieren NICHT -- nur als Hinweis zurueckgegeben (Spec: "unversionierte nur als
    Hinweis")."""
    zeilen = _git(["status", "--porcelain"], projekt_root).stdout.decode("utf-8").splitlines()
    versioniert = [z[3:] for z in zeilen if z[:2] != "??"]
    unversioniert = [z[3:] for z in zeilen if z[:2] == "??"]
    if versioniert:
        raise ReleaseFehler("Arbeitsbaum hat geaenderte, versionierte Dateien: "
                             + ", ".join(versioniert) + ". Erst committen oder verwerfen.")
    return unversioniert


def _pruefe_synchron_mit_origin(projekt_root: Path) -> str:
    """git fetch + Vergleich HEAD gegen origin/main. Gibt die VOLLE SHA von HEAD zurueck (fuer
    die CI-Pruefung -- Lehre 11.09./P2-36: gh run list --commit braucht die volle SHA, eine
    Kurz-SHA liefert still eine leere Liste)."""
    _git(["fetch", "origin"], projekt_root)
    head = _git(["rev-parse", "HEAD"], projekt_root).stdout.decode("utf-8").strip()
    origin_main = _git(["rev-parse", "origin/main"], projekt_root).stdout.decode("utf-8").strip()
    if head != origin_main:
        raise ReleaseFehler("HEAD ist nicht auf demselben Stand wie origin/main. "
                             "Erst pushen oder pullen, dann erneut versuchen.")
    return head


def _ci_lauf_status(sha: str, projekt_root: Path) -> tuple[str, str | None]:
    """(status, conclusion) des NEUESTEN gh-Laufs von ci.yml fuer die volle SHA. status
    "fehlt", wenn gh keinen Lauf kennt; sonst roh aus der API (status u. a.
    "completed"/"in_progress"/"queued", conclusion nur bei "completed" gesetzt). Eigene
    Funktion statt Inline-Code in _pruefe_ci(), damit Tests genau HIER per monkeypatch
    ansetzen koennen, ohne `gh` zu brauchen."""
    proc = _gh(["run", "list", "--commit", sha, "--workflow", "ci.yml",
                "--json", "status,conclusion"], projekt_root)
    laeufe = json.loads(proc.stdout.decode("utf-8") or "[]")
    if not laeufe:
        return "fehlt", None
    neuester = laeufe[0]
    return neuester.get("status", "fehlt"), neuester.get("conclusion")


def _pruefe_ci(sha: str, projekt_root: Path) -> None:
    status, conclusion = _ci_lauf_status(sha, projekt_root)
    if status == "fehlt":
        raise ReleaseFehler(f"Kein CI-Lauf (ci.yml) zu Commit {sha} gefunden.")
    if status != "completed":
        raise ReleaseFehler(f"CI-Lauf (ci.yml) zu Commit {sha} laeuft noch (Status "
                             f"„{status}“). Bitte abwarten.")
    if conclusion != "success":
        raise ReleaseFehler(f"CI-Lauf (ci.yml) zu Commit {sha} ist nicht erfolgreich "
                             f"(Ergebnis „{conclusion}“).")


def _neue_version(ziel: str, aktuelle_version: str) -> str:
    """Loest 'X.Y.Z' oder eine Erhoehungsstufe (patch/minor/major) gegen die aktuelle VERSION
    auf und verlangt, dass das Ergebnis groesser ist."""
    aktuelles_tupel = changelog.version_tupel(aktuelle_version)
    ziel = ziel.strip()
    if ziel in _STUFEN:
        major, minor, patch = aktuelles_tupel
        if ziel == "patch":
            neu_tupel = (major, minor, patch + 1)
        elif ziel == "minor":
            neu_tupel = (major, minor + 1, 0)
        else:
            neu_tupel = (major + 1, 0, 0)
        neue_version = f"{neu_tupel[0]}.{neu_tupel[1]}.{neu_tupel[2]}"
    else:
        neue_version = ziel
        try:
            neu_tupel = changelog.version_tupel(neue_version)
        except changelog.ChangelogFehler as exc:
            raise ReleaseFehler(str(exc)) from exc

    if neu_tupel <= aktuelles_tupel:
        raise ReleaseFehler(f"{neue_version} ist nicht groesser als die aktuelle Version "
                             f"{aktuelle_version}.")
    return neue_version


def _pruefe_tag_frei(tag_name: str, projekt_root: Path) -> None:
    lokal = _git(["tag", "-l", tag_name], projekt_root).stdout.decode("utf-8").strip()
    if lokal:
        raise ReleaseFehler(f"Tag {tag_name} existiert bereits lokal.")
    remote = _git(["ls-remote", "--tags", "origin", tag_name], projekt_root) \
        .stdout.decode("utf-8").strip()
    if remote:
        raise ReleaseFehler(f"Tag {tag_name} existiert bereits auf origin.")


def _pruefe_und_baue_changelog(neue_version: str, heute: date, projekt_root: Path) -> tuple[str, str]:
    """Liest CHANGELOG.md, prueft die Form (changelog.pruefen) und baut den neuen Text
    (changelog.freigeben -- das deckt "Unveroeffentlicht nicht leer" und "Version noch nicht
    vorhanden" gleich mit ab, keine doppelte Regel hier). Schreibt NICHTS auf die Platte --
    der Rueckgabewert dient sowohl --probe als auch dem echten Schreibschritt, damit beide
    exakt denselben Text erzeugen."""
    text = (projekt_root / "CHANGELOG.md").read_text(encoding="utf-8")
    form_fehler = changelog.pruefen(text)
    if form_fehler:
        raise ReleaseFehler("CHANGELOG.md: " + " ".join(form_fehler))
    try:
        neuer_text = changelog.freigeben(text, neue_version, heute)
    except changelog.ChangelogFehler as exc:
        raise ReleaseFehler(f"CHANGELOG.md: {exc}") from exc
    abschnitt_text = changelog.abschnitt(neuer_text, neue_version) or ""
    return neuer_text, abschnitt_text


def _pruefe_und_baue_changelog_en(neue_version: str, heute: date, projekt_root: Path) -> str:
    """P2-91: Dieselbe Freigabe für `CHANGELOG.en.md`. Fehlt der englische Abschnitt, bricht die Freigabe ab."""
    text = (projekt_root / "CHANGELOG.en.md").read_text(encoding="utf-8")
    form_fehler = changelog.pruefen(text)
    if form_fehler:
        raise ReleaseFehler("CHANGELOG.en.md: " + " ".join(form_fehler))
    try:
        return changelog.freigeben(text, neue_version, heute)
    except changelog.ChangelogFehler as exc:
        raise ReleaseFehler(f"CHANGELOG.en.md: {exc}") from exc


def _pruefe_uebersetzungen(projekt_root: Path) -> None:
    """P2-91: Zur Freigabe müssen alle englischen Fassungen aktuell sein, auch die der Technik-Doku.
    Ausgenommen ist nur das Changelog: Dessen Quelle ändert die Freigabe selbst."""
    funde = [f for f in uebersetzung.pruefen(projekt_root, uebersetzung.GRUPPEN) if "CHANGELOG" not in f]
    if funde:
        raise ReleaseFehler("Englische Fassungen veraltet (scripts/uebersetzung.sh --pruefen --alle): " + "; ".join(funde[:5]))


def _firmen_db_pfad(projekt_root: Path) -> Path:
    """Pfad zur lokalen Datenbank fuer die Firmennamen-Regel der Paketpruefung (P2-51/U2a) --
    wie die App respektiert das BMS_DATA_DIR, sonst data/ im Projekt. Nur Path.exists() wird
    hier geprueft, GEOEFFNET wird die Datei ausschliesslich in kundenpaket.bauen() selbst
    (lesend) -- dieses Modul fasst das data/ der Installation sonst nirgends an."""
    basis = os.environ.get("BMS_DATA_DIR")
    ordner = Path(basis) if basis else (projekt_root / "data")
    return ordner / "bewerbung.sqlite"


def _pruefe_paket(projekt_root: Path) -> None:
    """Paketpruefung fuer HEAD ohne Funde. `firmen_db` wird nur mitgegeben, wenn die
    Datenbank lokal vorhanden ist (BMS_DATA_DIR bzw. data/bewerbung.sqlite) -- so laeuft die
    Firmennamen-Regel (U2a, Regel 6b) beim Maintainer automatisch mit, in der CI (keine Datenbank
    im Checkout) faellt sie automatisch weg (kundenpaket.bauen behandelt firmen_db=None als
    "Regel ueberspringen")."""
    db_pfad = _firmen_db_pfad(projekt_root)
    ergebnis = kundenpaket.bauen(arbeitsbaum=False, ref="HEAD", ziel=None, nur_pruefen=True,
                                  projekt_root=projekt_root,
                                  firmen_db=db_pfad if db_pfad.exists() else None)
    if ergebnis.funde:
        zeilen = "\n".join(
            (f"  {f.pfad}:{f.zeile}  [{f.regel}]  {f.ausschnitt}" if f.zeile
             else f"  {f.pfad}  [{f.regel}]  {f.ausschnitt}")
            for f in ergebnis.funde
        )
        raise ReleaseFehler(f"Paketpruefung hat {len(ergebnis.funde)} Fund(e):\n{zeilen}")


def _freigabe_pruefen(ziel: str, *, ohne_ci_pruefung: bool, projekt_root: Path,
                       heute: date) -> tuple[str, str, str, list[str]]:
    """Alle Pruefungen VOR jeder Aenderung, in der Reihenfolge der Spec. Bei Erfolg
    (neue_version, neuer_changelog_text, abschnitt_text, hinweise-auf-unversionierte-Dateien)."""
    _pruefe_branch_main(projekt_root)
    hinweise = _pruefe_sauberer_arbeitsbaum(projekt_root)
    sha = _pruefe_synchron_mit_origin(projekt_root)
    if not ohne_ci_pruefung:
        _pruefe_ci(sha, projekt_root)

    aktuelle_version = (projekt_root / "VERSION").read_text(encoding="utf-8").strip()
    neue_version = _neue_version(ziel, aktuelle_version)
    _pruefe_tag_frei(f"v{neue_version}", projekt_root)

    neuer_text, abschnitt_text = _pruefe_und_baue_changelog(neue_version, heute, projekt_root)
    _pruefe_uebersetzungen(projekt_root)
    if (projekt_root / "CHANGELOG.en.md").is_file():
        _pruefe_und_baue_changelog_en(neue_version, heute, projekt_root)     # bricht ab, bevor etwas geschrieben ist
    _pruefe_paket(projekt_root)

    return neue_version, neuer_text, abschnitt_text, hinweise


# ── Befehle ────────────────────────────────────────────────────────────────────────────

def freigeben(ziel: str, *, probe: bool = False, ohne_ci_pruefung: bool = False,
              projekt_root: Path = PROJECT_ROOT, heute: date | None = None) -> int:
    """Hebt die Version an: Pruefungen, dann (ausser bei --probe) VERSION/CHANGELOG.md
    schreiben, committen, taggen, nach origin pushen. `heute` ist injizierbar (Tests) --
    date.today() wird bewusst ERST HIER, nicht als Default-Wert der Signatur ausgewertet
    (sonst wuerde Python es einmalig beim Modul-Import einfrieren)."""
    tag_datum = heute if heute is not None else date.today()

    try:
        neue_version, neuer_text, abschnitt_text, hinweise = _freigabe_pruefen(
            ziel, ohne_ci_pruefung=ohne_ci_pruefung, projekt_root=projekt_root, heute=tag_datum)
    except ReleaseFehler as exc:
        print(f"Abbruch: {exc}")
        return 1

    for pfad in hinweise:
        print(f"Hinweis: nicht versionierte Datei bleibt unberuehrt: {pfad}")

    tag_name = f"v{neue_version}"

    if probe:
        print(f"Probelauf fuer Freigabe {neue_version}: alle Pruefungen bestanden, nichts geaendert.")
        print(f"VERSION wuerde auf {neue_version} stehen.")
        print(f"CHANGELOG-Abschnitt „{neue_version}“:")
        print(abschnitt_text or "(leer)")
        print(f"Tag: {tag_name}")
        return 0

    # Englischen Text VOR dem ersten Schreiben bauen und mit `tag_datum`, nicht `heute`: `heute` ist
    # ausserhalb der Tests None (Absturz bei der echten Freigabe 2.2.0, 06.11.2026, nach dem
    # Schreiben von VERSION und CHANGELOG.md).
    neuer_text_en = None
    if (projekt_root / "CHANGELOG.en.md").is_file():
        neuer_text_en = _pruefe_und_baue_changelog_en(neue_version, tag_datum, projekt_root)

    (projekt_root / "VERSION").write_text(f"{neue_version}\n", encoding="utf-8", newline="\n")
    (projekt_root / "CHANGELOG.md").write_text(neuer_text, encoding="utf-8", newline="\n")
    zu_committen = ["VERSION", "CHANGELOG.md"]
    if neuer_text_en is not None:
        (projekt_root / "CHANGELOG.en.md").write_text(neuer_text_en, encoding="utf-8", newline="\n")
        uebersetzung.bestaetigen(projekt_root, "CHANGELOG.en.md")
        zu_committen += ["CHANGELOG.en.md", uebersetzung.QUELLEN_DATEI]

    commit_nachricht = f"Release {neue_version}"
    tag_nachricht = f"BMS {neue_version}\n\n{abschnitt_text}\n"

    try:
        _git(["add", *zu_committen], projekt_root)
        _git(["commit", "-m", commit_nachricht], projekt_root)
    except ReleaseFehler as exc:
        print(f"Fehler beim Commit: {exc}")
        print("VERSION und CHANGELOG.md sind im Arbeitsbaum bereits geaendert -- von Hand "
              "committen oder mit `git checkout -- VERSION CHANGELOG.md CHANGELOG.en.md` zuruecksetzen.")
        return 2

    # Ab hier ist der Commit da -- Spec: nichts automatisch zuruecknehmen, sondern bei jedem
    # weiteren Fehler die noch FEHLENDEN Schritte als genaue Befehle ausgeben.
    try:
        _git(["tag", "-a", tag_name, "-m", tag_nachricht], projekt_root)
    except ReleaseFehler as exc:
        print(f"Fehler beim Anlegen des Tags: {exc}")
        print(f"Der Commit „{commit_nachricht}“ ist bereits da. Zum Fortsetzen von Hand:")
        print(f"  git tag -a {tag_name} -m \"BMS {neue_version}\"")
        print("  git push origin main")
        print(f"  git push origin {tag_name}")
        return 2

    try:
        _git(["push", "origin", "main"], projekt_root)
    except ReleaseFehler as exc:
        print(f"Fehler beim Push nach main: {exc}")
        print(f"Commit und Tag {tag_name} sind lokal vorhanden. Zum Fortsetzen von Hand:")
        print("  git push origin main")
        print(f"  git push origin {tag_name}")
        return 2

    try:
        _git(["push", "origin", tag_name], projekt_root)
    except ReleaseFehler as exc:
        print(f"Fehler beim Push des Tags: {exc}")
        print("main steht schon auf origin. Zum Fortsetzen von Hand:")
        print(f"  git push origin {tag_name}")
        return 2

    # Im Entwicklungs-Repo gibt es kein Release (release.yml laeuft dort nicht, s. Moduldoc): kein
    # Actions-Link und kein Hinweis auf `abholen`, sondern der Weg ins oeffentliche Repo.
    print(f"Freigabe {neue_version} im Entwicklungs-Repo: main und {tag_name} stehen auf origin.")
    print(f"Veröffentlichen: scripts/veroeffentlichen.sh --ziel <Arbeitskopie> --ref {tag_name} "
          "(docs/RELEASE.md, Abschnitt Veröffentlichen).")
    return 0


def notizen(version: str, *, projekt_root: Path = PROJECT_ROOT) -> int:
    text = (projekt_root / "CHANGELOG.md").read_text(encoding="utf-8")
    abschnitt_text = changelog.abschnitt(text, version)
    if abschnitt_text is None:
        print(f"Kein CHANGELOG-Abschnitt fuer Version {version}.")
        return 1
    # P2-91: Englisch zuerst (Hauptsprache auf GitHub), Deutsch darunter.
    en_pfad = projekt_root / "CHANGELOG.en.md"
    en_text = changelog.abschnitt(en_pfad.read_text(encoding="utf-8"), version) if en_pfad.is_file() else None
    if en_text:
        print(f"{en_text}\n\n---\n\n{abschnitt_text}")
    else:
        print(abschnitt_text)
    return 0


def _sha256_pruefen(datei: Path, sha_datei: Path) -> bool:
    """Prueft `datei` gegen die erste Zeile von `sha_datei` im sha256sum-Format
    ("<hex>  <name>")."""
    erste_zeile = sha_datei.read_text(encoding="utf-8").strip().splitlines()[0]
    erwartet = erste_zeile.split()[0].lower()
    tatsaechlich = hashlib.sha256(datei.read_bytes()).hexdigest()
    return erwartet == tatsaechlich


def abholen(version: str, *, ziel: str | None = None, projekt_root: Path = PROJECT_ROOT) -> int:
    """Laedt das Release `vVERSION` des OEFFENTLICHEN Repos (alle Anhaenge) und prueft ZIP gegen
    `.sha256`. Zum Pruefen einer Freigabe, nicht zum Veroeffentlichen."""
    zielordner = Path(ziel) if ziel else (projekt_root / "outputs" / "kundenpaket")
    zielordner.mkdir(parents=True, exist_ok=True)
    tag_name = f"v{version}"

    try:
        # Das Release gibt es nur im oeffentlichen Repo; ohne --repo suchte gh in `origin`, dem
        # Entwicklungs-Repo, und fand nichts.
        _gh(["release", "download", tag_name, "--repo", OEFFENTLICHES_REPO,
             "--dir", str(zielordner), "--clobber"], projekt_root)
    except ReleaseFehler as exc:
        print(f"Abbruch: {exc}")
        return 1

    zip_pfad = zielordner / f"BMS_{version}.zip"
    sha_pfad = zielordner / f"BMS_{version}.zip.sha256"
    if not zip_pfad.exists() or not sha_pfad.exists():
        print(f"Abbruch: erwartete Dateien fehlen in {zielordner} "
              f"({zip_pfad.name}, {sha_pfad.name}).")
        return 1

    if not _sha256_pruefen(zip_pfad, sha_pfad):
        print(f"Abbruch: SHA-256-Pruefsumme von {zip_pfad.name} stimmt nicht.")
        return 1

    print(f"Kundenpaket liegt unter {zip_pfad}")
    return 0


def main(argv: list[str] | None = None, projekt_root: Path = PROJECT_ROOT) -> int:
    ap = argparse.ArgumentParser(prog="pipeline.release",
                                  description="Freigabe-Werkzeug (P2-51).")
    sub = ap.add_subparsers(dest="befehl", required=True)

    p_frei = sub.add_parser("freigeben", help="Version freigeben (Commit, Tag, Push nach origin)")
    p_frei.add_argument("version", help="X.Y.Z oder eine Erhoehungsstufe: patch, minor, major")
    p_frei.add_argument("--probe", action="store_true",
                         help="alle Pruefungen laufen, aber nichts wird geaendert")
    p_frei.add_argument("--ohne-ci-pruefung", action="store_true",
                         help="CI-Status nicht pruefen (nur fuer Tests und Notfaelle)")

    p_notizen = sub.add_parser("notizen", help="Release-Notizen einer Version anzeigen")
    p_notizen.add_argument("version")

    p_abholen = sub.add_parser("abholen", help="Kundenpaket aus dem Release des oeffentlichen Repos "
                                                "herunterladen")
    p_abholen.add_argument("version")
    p_abholen.add_argument("--ziel", default=None, help="Zielordner (Default outputs/kundenpaket/)")

    args = ap.parse_args(argv)

    if args.befehl == "freigeben":
        return freigeben(args.version, probe=args.probe, ohne_ci_pruefung=args.ohne_ci_pruefung,
                          projekt_root=projekt_root)
    if args.befehl == "notizen":
        return notizen(args.version, projekt_root=projekt_root)
    return abholen(args.version, ziel=args.ziel, projekt_root=projekt_root)


if __name__ == "__main__":
    raise SystemExit(main())
