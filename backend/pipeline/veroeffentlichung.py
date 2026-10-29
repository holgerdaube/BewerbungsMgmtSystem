#!/usr/bin/env python3
"""Export-Werkzeug fuer das oeffentliche Repo (P2-83, Paket E, Vertrag E der Bau-Spec).

Erzeugt aus EINEM COMMIT des privaten Repos den oeffentlichen Baum in einer lokalen Arbeitskopie des
oeffentlichen Repos (`personendaten.OEFFENTLICHES_REPO`) und VERWEIGERT bei jedem Personendaten- oder
Geheimnis-Fund. Es committet, taggt und pusht NIE: das Ergebnis liegt als ungesicherte Aenderung in der
Arbeitskopie und wird von Hand durchgesehen (Schritt 4 der Open-Source-Umstellung).

Aufruf (aus `backend/`, bequemer ueber `scripts/veroeffentlichen.sh`):
    python -m pipeline.veroeffentlichung --ziel ORDNER [--ref COMMIT] [--pruefen]

Ablauf:
  1. `--ref` (Vorgabe `HEAD`) muss in `main` enthalten sein (`git merge-base --is-ancestor`). Steht
     `HEAD` auf dem Commit und der Arbeitsbaum hat ungesicherte Aenderungen, gibt es eine Warnung:
     exportiert wird der Commit, nicht der Arbeitsbaum.
  2. Die Eintraege kommen per `git archive` (`kundenpaket.sammle_aus_git_archive`), minus
     `NICHT_OEFFENTLICH`. Ausgenommene Dateien werden NICHT geprueft: sie verlassen das Haus nicht.
  3. Pruefung: persoenliche Muster aus Profil, Datenbank und Musterdatei (`personendaten.muster_laden`),
     dann `personendaten.pruefen(..., umfang="oeffentlich")` ueber alle Eintraege, dazu eine schnelle
     Geheimnis-Suche (`geheimnis_funde`). Fehlt Profil oder Datenbank, bricht das Werkzeug ab: ohne
     sie wuerde die Pruefung die persoenlichen Regeln still auslassen und Sicherheit nur vortaeuschen.
  4. `--pruefen` endet hier.
  5. Das Ziel wird geprueft (`ziel_pruefen`): eigene Arbeitskopie (`.git` im Ordner selbst), `origin`
     (und die Push-Adresse) zeigt auf das oeffentliche Repo, keine ungesicherten Aenderungen, nicht das
     Quell-Repo. Dazu die COMMIT-IDENTITAET (P2-84): Die wirksame Autor- und Committer-Adresse
     (`git var GIT_AUTHOR_IDENT`/`GIT_COMMITTER_IDENT`, also Konfiguration UND Umgebungsvariablen) muss
     eine GitHub-noreply-Adresse sein, und alle Autor-, Committer- und Tagger-Adressen schon vorhandener
     Commits und Tags muessen noreply-Adressen oder GitHubs eigene sein. Sonst stuende die private
     Mailadresse in jedem oeffentlichen Commit und Tag. Sonst Abbruch, nichts geschrieben.
  6. Spiegeln: alles im Ziel ausser dem Git-Verzeichnis wird geloescht, die Eintraege werden mit ihren
     Rechten (ausfuehrbar ja/nein) und BYTE-GENAU wie im Archiv geschrieben (Zeilenenden bleiben).
  7. Ausgabe: Zahl der Dateien, `git status --short` des Ziels (auf 40 Zeilen gekuerzt) und die
     naechsten Schritte als Hinweis (die Befehle aus docs/RELEASE.md, Abschnitt Veroeffentlichen).

Exit-Codes: 0 in Ordnung, 1 Funde, 2 Abbruch (Voraussetzung fehlt), 3 Aufruf falsch.

NIE EIN FUNDSTUECK UND NIE DIE GEFUNDENE ADRESSE AUSGEBEN. Die Ausgabe landet in Terminals, Logs und
Berichten und darf deshalb den gefundenen Begriff und die private Mailadresse nicht enthalten. Auch die
Fehlermeldung von `git var` bleibt draussen: Sie nennt die Adresse, die git aus Benutzer und Rechnername
geraten hat (`_identitaet_adresse`). Ein Fund zeigt Datei, Zeile und Regel, dazu NUR die Laenge der Zeile
und ihren Anfang, soweit er aus Satzzeichen besteht (`_zeile_beschreiben`: jeder Treffer enthaelt
Buchstaben oder Ziffern, ein Anfang ohne sie kann keinen enthalten). Ein Dateipfad, der selbst einen
Treffer traegt (Name im Dateinamen), wird segmentweise geschwaerzt (`_maskierte_pfade`).

Die Geheimnis-Muster sind so zusammengesetzt, dass diese Datei sich nicht selbst meldet.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, NamedTuple

from pipeline import kundenpaket, personendaten
from pipeline.personendaten import OEFFENTLICHES_REPO, UMFANG_OEFFENTLICH, Eintrag, Fund, Muster

PROJECT_ROOT = kundenpaket.PROJECT_ROOT

# Was NICHT in den oeffentlichen Baum kommt (Leitentscheidung 1). Ein Muster mit "/" am Ende ist ein
# ganzer Ordner, sonst ein exakter Pfad (`personendaten.pfad_trifft`). Alles andere, was oeffentlich nicht
# stehen darf, wird im privaten Repo bereinigt: es gibt keinen zweiten, getrennt gepflegten Baum.
NICHT_OEFFENTLICH: tuple[str, ...] = ("tasks/", ".claude/launch.json")

HAUPTZWEIG = "main"
STATUS_MAX_ZEILEN = 40

EXIT_OK, EXIT_FUNDE, EXIT_ABBRUCH, EXIT_AUFRUF = 0, 1, 2, 3

MELDUNG_UNVOLLSTAENDIG = ("Ohne Profil und Datenbank lässt sich nicht prüfen, ob persönliche Daten "
                          "im Export stehen.")

# Eine relative Angabe fuer --ziel gilt ab dem Ordner, in dem das Skript aufgerufen wurde (das Skript
# wechselt selbst nach backend/). scripts/veroeffentlichen.sh setzt diese Umgebungsvariable.
AUFRUFORDNER_VARIABLE = "BMS_AUFRUFORDNER"

_MASKE = "‹geschwärzt›"


class VeroeffentlichungFehler(Exception):
    """Voraussetzung fehlt (Revision, Quelle, Ziel, git) -- Exit-Code 2. KEIN Fund: Funde sind
    `Ergebnis.funde` und fuehren zu Exit-Code 1."""


class _AufrufFehler(Exception):
    """Falscher Aufruf (unbekannte Option, --ziel fehlt) -- Exit-Code 3."""


class Ergebnis(NamedTuple):
    commit: kundenpaket.CommitInfo
    version: str
    anzahl_dateien: int                  # Dateien im oeffentlichen Baum (nach NICHT_OEFFENTLICH)
    ausgenommen: tuple[str, ...]         # Pfade, die NICHT_OEFFENTLICH traf
    muster: Muster
    funde: tuple[Fund, ...]              # ohne Dubletten
    fund_zeilen: tuple[str, ...]         # die Funde fuer die Ausgabe (geschwaerzt)
    ziel: Path | None                    # aufgeloestes Ziel; None bei --pruefen
    geschrieben: bool
    status: tuple[str, ...]              # `git status --short` des Ziels nach dem Spiegeln


# ── git ──────────────────────────────────────────────────────────────────────────────────────

def _git(args: list[str], ordner: Path, *, ok: tuple[int, ...] | None = (0,)) -> subprocess.CompletedProcess:
    """Ruft git in `ordner` auf (Bytes-Ausgabe). Ein Rueckgabewert ausserhalb von `ok` ist ein Abbruch;
    `ok=None` nimmt jeden (der Aufrufer wertet `returncode` selbst aus und zeigt die Fehlermeldung von
    git nie an). `.git` darf eine Zeiger-Datei sein (iCloud-Workaround) -- fuer git selbst transparent."""
    try:
        proc = subprocess.run(["git", *args], cwd=ordner, capture_output=True)
    except FileNotFoundError as exc:
        raise VeroeffentlichungFehler("git ist auf diesem Rechner nicht verfügbar.") from exc
    if ok is not None and proc.returncode not in ok:
        meldung = proc.stderr.decode("utf-8", "replace").strip()
        raise VeroeffentlichungFehler(f"git {' '.join(args)} fehlgeschlagen: {meldung}")
    return proc


def _git_text(args: list[str], ordner: Path) -> str:
    return _git(args, ordner).stdout.decode("utf-8", "replace").strip()


def _gleicher_ort(a: str | Path, b: str | Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


# ── Schritt 1: Revision ──────────────────────────────────────────────────────────────────────

def ref_pruefen(ref: str, root: Path) -> kundenpaket.CommitInfo:
    """`ref` muss ein Commit sein UND in `main` liegen. Gibt den aufgeloesten Commit zurueck."""
    try:
        info = kundenpaket.commit_info(ref, root)
    except (kundenpaket.KundenpaketFehler, ValueError) as exc:
        raise VeroeffentlichungFehler(f"Die Revision „{ref}“ gibt es im Quell-Repo nicht.") from exc
    proc = subprocess.run(["git", "merge-base", "--is-ancestor", info.voll, f"refs/heads/{HAUPTZWEIG}"],
                          cwd=root, capture_output=True)
    if proc.returncode == 1:
        raise VeroeffentlichungFehler(
            f"{ref} ({info.kurz}) ist nicht in {HAUPTZWEIG} enthalten. Veröffentlicht wird nur, was auf "
            f"{HAUPTZWEIG} gelandet ist.")
    if proc.returncode != 0:
        raise VeroeffentlichungFehler(f"Der Zweig {HAUPTZWEIG} fehlt im Quell-Repo; ohne ihn lässt sich "
                                      f"nicht prüfen, ob {ref} darin enthalten ist.")
    return info


def _head_ungesichert(info: kundenpaket.CommitInfo, root: Path) -> bool:
    """Steht HEAD auf dem Export-Commit UND hat der Arbeitsbaum ungesicherte Aenderungen an
    versionierten Dateien? Dann weicht der Arbeitsbaum vom Export ab (Warnung)."""
    if _git_text(["rev-parse", "HEAD"], root) != info.voll:
        return False
    return bool(_git(["status", "--porcelain", "--untracked-files=no"], root).stdout.strip())


def _nicht_exportierbar(sha: str, root: Path) -> int:
    """Zahl der Symlinks (120000) und Submodule (160000) im Stand: `git archive` kennt sie, der
    Export (nur Dateien) schreibt sie nicht."""
    ausgabe = _git(["ls-tree", "-r", "-z", sha], root).stdout.decode("utf-8", "replace")
    return sum(1 for satz in ausgabe.split("\0") if satz.split(" ", 1)[0] in ("120000", "160000"))


# ── Schritt 2: Eintraege ─────────────────────────────────────────────────────────────────────

def oeffentliche_eintraege(eintraege: list[Eintrag]) -> tuple[list[Eintrag], list[str]]:
    """Trennt `NICHT_OEFFENTLICH` ab. Gibt (Eintraege des oeffentlichen Baums, ausgenommene Pfade) zurueck."""
    behalten: list[Eintrag] = []
    ausgenommen: list[str] = []
    for e in eintraege:
        if personendaten.pfad_trifft(e.pfad, NICHT_OEFFENTLICH):
            ausgenommen.append(e.pfad)
        else:
            behalten.append(e)
    return behalten, ausgenommen


def _version(eintraege: list[Eintrag]) -> str:
    for e in eintraege:
        if e.pfad == "VERSION":
            return e.inhalt.decode("utf-8", "replace").strip()
    return "unbekannt"


# ── Schritt 3: Geheimnis-Suche ───────────────────────────────────────────────────────────────
# Zusammengesetzt (Anfang + Rest), damit weder diese Datei noch ihre Tests sich selbst melden. Der Rest
# verlangt jeweils einen Schluessel realistischer Laenge: eine Regex-Schreibweise oder ein Hinweis in der
# Doku ("beginnt mit ...") ist kein Fund.
_GEHEIMNIS_PLATZHALTER_RE = re.compile(r"[<>{}$]|\.\.\.|…|x{3,}|^(?:your|dein|ihr|example|beispiel|"
                                       r"platzhalter|changeme|geheim)", re.IGNORECASE)


def _kein_platzhalter(treffer: re.Match) -> bool:
    wert = treffer.groupdict().get("wert")
    return wert is None or not _GEHEIMNIS_PLATZHALTER_RE.search(wert)


_GEHEIMNIS_REGELN: tuple[tuple[str, re.Pattern], ...] = (
    ("Geheimnis: Anthropic-Schlüssel", re.compile("sk-" + "ant-" + r"[A-Za-z0-9_\-]{16,}")),
    ("Geheimnis: Apify-Token", re.compile("apify_" + "api_" + r"[A-Za-z0-9]{16,}")),
    ("Geheimnis: client_secret mit Wert",
     re.compile("client_" + "secret" + r"[\"']?\s*[:=]\s*[\"'](?P<wert>[^\"'\s]{8,})[\"']", re.IGNORECASE)),
    ("Geheimnis: privater Schlüssel (PEM)", re.compile("-----" + "BEGIN [A-Z ]*" + "PRIVATE KEY-----")),
    ("Geheimnis: GitHub-Token",
     re.compile(r"(?<![A-Za-z0-9_])(?:gh[pousr]" + "_" + r"[A-Za-z0-9]{30,}|github" + "_pat_" + r"[A-Za-z0-9_]{20,})")),
)


def geheimnis_funde(eintraege: list[Eintrag]) -> list[Fund]:
    """Schnelle Suche nach Schluesseln und Tokens in allen Textdateien. Der Ausschnitt bleibt leer: die
    Ausgabe zeigt nie die Zeile (s. `fund_zeilen`)."""
    funde: list[Fund] = []
    for e in eintraege:
        try:
            zeilen = e.inhalt.decode("utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for i, zeile in enumerate(zeilen, start=1):
            for regel, muster in _GEHEIMNIS_REGELN:
                if any(_kein_platzhalter(m) for m in muster.finditer(zeile)):
                    funde.append(Fund(e.pfad, i, regel, ""))
    return funde


def alle_funde(eintraege: list[Eintrag], muster: Muster) -> list[Fund]:
    """Personendaten im Umfang „oeffentlich“ plus Geheimnisse, ohne Dubletten (gleiche Datei, Zeile
    und Regel), in der Reihenfolge des ersten Auftretens."""
    gesehen: set[tuple[str, int, str]] = set()
    ergebnis: list[Fund] = []
    for f in personendaten.pruefen(eintraege, muster, umfang=UMFANG_OEFFENTLICH) + geheimnis_funde(eintraege):
        schluessel = (f.pfad, f.zeile, f.regel)
        if schluessel not in gesehen:
            gesehen.add(schluessel)
            ergebnis.append(f)
    return ergebnis


# ── Ausgabe der Funde, geschwaerzt ───────────────────────────────────────────────────────────

def _zeile_beschreiben(zeile: str) -> str:
    """Laenge der Zeile und ihr Anfang, soweit er aus Satzzeichen und Leerraum besteht (hoechstens acht
    Zeichen). Jeder Treffer (Name, Strasse, Mailadresse, Nummer, Schluessel) enthaelt Buchstaben oder
    Ziffern -- ein Anfang bis zum ersten davon kann keinen Treffer enthalten."""
    rest = zeile.lstrip()
    anfang = []
    for zeichen in rest[:8]:
        if zeichen.isalnum():
            break
        anfang.append(zeichen if zeichen.isprintable() else "·")
    text = f"Zeile mit {len(zeile)} Zeichen"
    return text + (f", Anfang „{''.join(anfang)}“" if anfang else "")


def _endung(segment: str) -> str:
    stamm, punkt, ende = segment.rpartition(".")
    return f".{ende}" if punkt and stamm and 0 < len(ende) <= 6 and ende.isalnum() else ""


def _maskierte_pfade(pfade: list[str], muster: Muster) -> dict[str, str]:
    """Pfad -> Pfad fuer die Ausgabe. Ein Pfad, der selbst einen Treffer traegt (Name im Dateinamen),
    verraet den Begriff durch seine Anzeige. Geprueft wird jedes Segment (und jede Endung) einzeln mit
    denselben Regeln wie die Pruefung; getroffene Segmente werden ersetzt, die Endung bleibt, wenn sie
    selbst unauffaellig ist. Trifft nur der ganze Pfad (Muster ueber Ordnergrenzen), wird er ganz
    geschwaerzt."""
    kandidaten: set[str] = set()
    for p in pfade:
        kandidaten.add(p)
        for segment in p.split("/"):
            kandidaten.update((segment, _endung(segment)))
    kandidaten.discard("")
    getroffen = {f.pfad for f in personendaten.pruefen(
        [Eintrag(k, 0o644, b"") for k in sorted(kandidaten)], muster, umfang=UMFANG_OEFFENTLICH)}
    ergebnis: dict[str, str] = {}
    for p in pfade:
        if p not in getroffen:
            ergebnis[p] = p
            continue
        teile = []
        for segment in p.split("/"):
            if segment in getroffen:
                ende = _endung(segment)
                teile.append(_MASKE + (ende if ende and ende not in getroffen else ""))
            else:
                teile.append(segment)
        ergebnis[p] = "/".join(teile) if any(t != s for t, s in zip(teile, p.split("/"))) else _MASKE
    return ergebnis


def fund_zeilen(funde: list[Fund], eintraege: list[Eintrag], muster: Muster) -> list[str]:
    """Die Funde fuer die Ausgabe: `  <Datei>:<Zeile>  [<Regel>]  <Laenge und Anfang der Zeile>`, wie
    die Paketpruefung, nur ohne Ausschnitt. `Fund.ausschnitt` wird NIE ausgegeben."""
    inhalt = {e.pfad: e.inhalt for e in eintraege}
    maske = _maskierte_pfade(sorted({f.pfad for f in funde}), muster)
    zeilen_von: dict[str, list[str]] = {}
    ausgabe = []
    for f in funde:
        ort = maske[f.pfad]
        detail = ""
        if f.zeile:
            ort += f":{f.zeile}"
            if f.pfad not in zeilen_von:
                zeilen_von[f.pfad] = inhalt.get(f.pfad, b"").decode("utf-8", "replace").splitlines()
            zeilen = zeilen_von[f.pfad]
            if 0 < f.zeile <= len(zeilen):
                detail = "  " + _zeile_beschreiben(zeilen[f.zeile - 1])
        ausgabe.append(f"  {ort}  [{f.regel}]{detail}")
    return ausgabe


# ── Schritt 5: Ziel ──────────────────────────────────────────────────────────────────────────

_ORIGIN_RE = re.compile(
    r"^(?:https://(?:[^/@\s]+@)?github\.com/|ssh://git@github\.com/|git@github\.com:)"
    + re.escape(OEFFENTLICHES_REPO) + r"(?:\.git)?/?$",
    re.IGNORECASE)


def origin_ist_oeffentlich(url: str) -> bool:
    """Zeigt die Adresse auf das oeffentliche Repo (https oder ssh, mit oder ohne `.git`)? Ein anderer
    Host, ein anderes Konto oder ein laengerer Repo-Name ist es nicht."""
    return bool(_ORIGIN_RE.match(url.strip()))


# Commit-Identitaet (Leitentscheidung 3 der Bau-Spec P2-84). Die Muster stehen in Regex-Schreibweise
# (maskierte Punkte), damit diese Datei sich nicht selbst als Mailadresse meldet; die Meldungen nennen
# die Form mit Platzhaltern <ID> und <Konto>.
#   noreply:  `<ID>+<Konto>` oder `<Konto>` vor der noreply-Domain von GitHub (Konto: 1 bis 39 Zeichen).
#   eigene:   GitHubs eigene Adressen, die in einem Verlauf stehen duerfen (Commits ueber die Weboberflaeche
#             tragen die allgemeine Absenderadresse von GitHub als Committer, Dependabot und Co. die
#             Bot-Form). Als Identitaet fuer EIGENE Commits taugen sie nicht.
_NOREPLY_RE = re.compile(r"(?:\d+\+)?[A-Za-z0-9-]{1,39}@users\.noreply\.github\.com", re.ASCII)
_GITHUB_EIGENE_RE = re.compile(
    r"noreply@github\.com|\d+\+[A-Za-z0-9-]+\[bot\]@users\.noreply\.github\.com", re.ASCII)
_IDENT_ADRESSE_RE = re.compile(r"<([^<>]*)>")
_IDENTITAETEN = ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT")
_IDENTITAET_UMGEBUNG = ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL", "EMAIL")

MELDUNG_IDENTITAET = ("Die Commit-Adresse der Arbeitskopie ist keine GitHub-noreply-Adresse. Setzen mit: "
                      "git -C \"{ziel}\" config user.email <ID>+<Konto>@users.noreply.github.com")
MELDUNG_UMGEBUNG = (" Eine gesetzte Umgebungsvariable ({namen}) geht der Einstellung vor; sie muss "
                    "entfernt oder auf die noreply-Adresse gesetzt werden.")
MELDUNG_VERLAUF = "Ein Commit oder Tag im Ziel trägt eine andere Adresse als die GitHub-noreply-Adresse."


def noreply_adresse(adresse: str) -> bool:
    """Ist das eine GitHub-noreply-Adresse (`<ID>+<Konto>` oder `<Konto>`)? Die Identitaet fuer eigene
    Commits muss eine sein."""
    return bool(_NOREPLY_RE.fullmatch(adresse))


def verlauf_adresse_erlaubt(adresse: str) -> bool:
    """Darf diese Adresse in einem vorhandenen Commit oder Tag stehen: eine noreply-Adresse oder eine der
    beiden eigenen Formen von GitHub?"""
    return noreply_adresse(adresse) or bool(_GITHUB_EIGENE_RE.fullmatch(adresse))


def _identitaet_adresse(art: str, ordner: Path) -> str | None:
    """Wirksame Adresse laut `git var <art>` (Konfiguration des Ziels, globale Konfiguration und die
    Umgebungsvariablen GIT_AUTHOR_EMAIL, GIT_COMMITTER_EMAIL und EMAIL zusammen). `None`, wenn git keine
    Identitaet liefert. Die Fehlermeldung von git wird verworfen: ohne Konfiguration rät git eine Adresse
    aus Benutzer und Rechnername und nennt sie dort. Ohne Fehler kann git diese geratene Adresse auch
    liefern -- sie ist dann keine noreply-Adresse und fuehrt ebenfalls zum Abbruch."""
    proc = _git(["var", art], ordner, ok=None)
    if proc.returncode != 0:
        return None
    treffer = _IDENT_ADRESSE_RE.search(proc.stdout.decode("utf-8", "replace"))
    return treffer.group(1) if treffer else None


def _verlauf_adressen(ordner: Path) -> list[str]:
    """Autor-, Committer- und Tagger-Adressen aller vorhandenen Commits (alle Zweige) und Tags. Ein leichtes
    Tag hat keinen Tagger (leere Zeile) und wird uebersprungen. Ein Repo ohne Referenzen hat keine Commits:
    `git log --all` wird dort nicht aufgerufen (es faellt je nach git-Version unterschiedlich aus)."""
    adressen: list[str] = []
    if _git_text(["for-each-ref", "--count=1", "--format=%(refname)"], ordner):
        ausgabe = _git(["log", "--all", "--format=%ae%n%ce"], ordner).stdout.decode("utf-8", "replace")
        adressen.extend(ausgabe.splitlines())
    tags = _git(["for-each-ref", "refs/tags", "--format=%(taggeremail)"], ordner)
    for zeile in tags.stdout.decode("utf-8", "replace").splitlines():
        roh = zeile.strip()
        if roh:
            adressen.append(roh[1:-1] if roh.startswith("<") and roh.endswith(">") else roh)
    return adressen


def _identitaet_pruefen(ordner: Path) -> None:
    """Die Adresse, mit der `git commit` und `git tag` im Ziel zeichnen wuerden, und die Adressen im
    vorhandenen Verlauf muessen GitHub-noreply-Adressen sein. Keine Meldung nennt eine gefundene Adresse."""
    for art in _IDENTITAETEN:
        adresse = _identitaet_adresse(art, ordner)
        if adresse is None or not noreply_adresse(adresse):
            meldung = MELDUNG_IDENTITAET.format(ziel=ordner)
            gesetzt = [n for n in _IDENTITAET_UMGEBUNG if n in os.environ]
            if gesetzt:
                meldung += MELDUNG_UMGEBUNG.format(namen=", ".join(gesetzt))
            raise VeroeffentlichungFehler(meldung)
    if not all(verlauf_adresse_erlaubt(a) for a in _verlauf_adressen(ordner)):
        raise VeroeffentlichungFehler(MELDUNG_VERLAUF)


def _git_verzeichnis(ordner: Path) -> Path:
    gemeinsam = _git_text(["rev-parse", "--git-common-dir"], ordner)
    return (ordner / gemeinsam).resolve()


def ziel_pruefen(ziel: str | Path, root: Path) -> tuple[Path, frozenset[str]]:
    """Prueft die Arbeitskopie, in die gespiegelt wird (Ordner, `origin`, Commit-Identitaet, sauberer
    Stand). Gibt (aufgeloestes Ziel, Namen im Ziel, die das Spiegeln nie loeschen darf) zurueck. Jede
    Verletzung ist ein Abbruch, geschrieben wird nichts."""
    ordner = Path(ziel).expanduser()
    if not ordner.is_absolute() and os.environ.get(AUFRUFORDNER_VARIABLE):
        ordner = Path(os.environ[AUFRUFORDNER_VARIABLE]) / ordner
    if not ordner.is_dir():
        raise VeroeffentlichungFehler(f"Das Ziel {ordner} ist kein Ordner.")
    ordner = ordner.resolve()

    if not (ordner / ".git").exists():
        raise VeroeffentlichungFehler(f"Das Ziel {ordner} ist keine Git-Arbeitskopie (.git fehlt im Ordner).")
    wurzel = Path(_git_text(["rev-parse", "--show-toplevel"], ordner))
    if not _gleicher_ort(wurzel, ordner):
        raise VeroeffentlichungFehler(f"Das Ziel {ordner} ist nicht die Wurzel einer Arbeitskopie.")

    quelle = root.resolve()
    if any(_gleicher_ort(ordner, p) for p in (quelle, *quelle.parents)):
        raise VeroeffentlichungFehler("Das Ziel ist das Quell-Repo oder enthält es. Gespiegelt wird nur in "
                                      "eine eigene Arbeitskopie des öffentlichen Repos.")
    if _gleicher_ort(_git_verzeichnis(ordner), _git_verzeichnis(quelle)):
        raise VeroeffentlichungFehler("Das Ziel gehört zum Quell-Repo (gleiches Git-Verzeichnis).")

    for bezeichnung, args in (("origin", ["remote", "get-url", "origin"]),
                              ("Push-Adresse von origin", ["remote", "get-url", "--push", "origin"])):
        try:
            url = _git_text(args, ordner)
        except VeroeffentlichungFehler as exc:
            raise VeroeffentlichungFehler(f"Das Ziel hat keinen Remote origin ({exc}).") from exc
        if not origin_ist_oeffentlich(url):
            raise VeroeffentlichungFehler(
                f"{bezeichnung} des Ziels zeigt nicht auf das öffentliche Repo ({OEFFENTLICHES_REPO}).")

    _identitaet_pruefen(ordner)

    offen = [z for z in _git_text(["status", "--porcelain"], ordner).splitlines() if z.strip()]
    if offen:
        raise VeroeffentlichungFehler(
            f"Das Ziel hat ungesicherte Änderungen ({len(offen)} Einträge in git status). Sie gingen beim "
            "Spiegeln verloren; erst committen oder verwerfen.")

    # Das Git-Verzeichnis darf nie geloescht werden -- auch nicht, wenn `.git` nur auf einen Nachbarn
    # zeigt (iCloud: `.git` ist eine Datei, das Verzeichnis heisst `.git.nosync`).
    geschuetzt = {".git"}
    echt = Path(_git_text(["rev-parse", "--absolute-git-dir"], ordner)).resolve()
    if echt.parent == ordner:
        geschuetzt.add(echt.name)
    return ordner, frozenset(geschuetzt)


# ── Schritt 6: Spiegeln ──────────────────────────────────────────────────────────────────────

def _pfade_pruefen(eintraege: list[Eintrag], geschuetzt: frozenset[str]) -> None:
    """Kein Eintrag darf aus dem Ziel hinausschreiben oder das Git-Verzeichnis beruehren."""
    for e in eintraege:
        teile = e.pfad.split("/")
        if (e.pfad.startswith("/") or "\\" in e.pfad or "" in teile or "." in teile or ".." in teile
                or teile[0] in geschuetzt):
            raise VeroeffentlichungFehler("Ein Pfad im Export liegt ausserhalb des Ziels oder im "
                                          "Git-Verzeichnis; nichts geschrieben.")


def spiegeln(ziel: Path, eintraege: list[Eintrag], geschuetzt: frozenset[str]) -> None:
    """Loescht alles im Ziel ausser dem Git-Verzeichnis und schreibt die Eintraege: Rechte ausfuehrbar
    ja/nein, Inhalt byte-genau. Symlinks im Ziel werden entfernt, nie verfolgt."""
    for kind in ziel.iterdir():
        if kind.name in geschuetzt:
            continue
        if kind.is_symlink() or not kind.is_dir():
            kind.unlink()
        else:
            shutil.rmtree(kind)
    for e in eintraege:
        datei = ziel.joinpath(*e.pfad.split("/"))
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_bytes(e.inhalt)
        os.chmod(datei, 0o755 if e.modus & 0o111 else 0o644)


def _status_kurz(ziel: Path) -> list[str]:
    """`git status --short` des Ziels, jede Datei einzeln (nicht nur neue Ordner)."""
    # Nicht strippen: die erste Spalte kann ein Leerzeichen sein (" D datei" = geloescht, nicht vorgemerkt).
    ausgabe = _git(["status", "--short", "--untracked-files=all"], ziel).stdout.decode("utf-8", "replace")
    return [z for z in ausgabe.splitlines() if z.strip()]


# ── Orchestrierung ───────────────────────────────────────────────────────────────────────────

def exportieren(*, ziel: str | Path | None, ref: str = "HEAD", nur_pruefen: bool = False,
                projekt_root: Path = PROJECT_ROOT, db_pfad: Path | None = None, extra: Path | None = None,
                melden: Callable[[str], None] = print) -> Ergebnis:
    """Der ganze Ablauf (Moduldoc). `projekt_root`, `db_pfad` und `extra` sind Parameter, damit die Tests
    mit Wegwerf-Repos und erfundenen Quellen arbeiten; die CLI nimmt die Vorgaben (Projekt, `BMS_DATA_DIR`
    bzw. `data/`, Secrets-Ordner). Wirft `VeroeffentlichungFehler` bei fehlender Voraussetzung."""
    if ziel is None and not nur_pruefen:
        raise ValueError("ziel fehlt (nur mit nur_pruefen=True darf es entfallen)")
    root = Path(projekt_root)
    info = ref_pruefen(ref, root)
    if _head_ungesichert(info, root):
        melden(f"Warnung: Der Arbeitsbaum hat ungesicherte Änderungen. Exportiert wird der Commit "
               f"{info.kurz}, nicht der Arbeitsbaum.")

    muster = personendaten.muster_laden(root, db_pfad=db_pfad, extra=extra)
    if not muster.vollstaendig:
        raise VeroeffentlichungFehler(
            MELDUNG_UNVOLLSTAENDIG + "".join(f"\n  - {h}" for h in muster.hinweise))
    melden("Prüfmuster: Profil und Datenbank gelesen, Musterdatei "
           + ("gelesen." if muster.extra_gelesen else "nicht vorhanden."))

    try:
        roh = kundenpaket.sammle_aus_git_archive(info.voll, root)
    except kundenpaket.KundenpaketFehler as exc:
        raise VeroeffentlichungFehler(str(exc)) from exc
    eintraege, ausgenommen = oeffentliche_eintraege(roh)
    version = _version(eintraege)
    melden(f"Quelle: {ref} ({info.kurz}, {info.datum}), Version {version}")
    melden(f"Dateien im öffentlichen Baum: {len(eintraege)} ({len(ausgenommen)} nicht öffentlich: "
           f"{', '.join(NICHT_OEFFENTLICH)})")
    uebersprungen = _nicht_exportierbar(info.voll, root)
    if uebersprungen:
        melden(f"Hinweis: {uebersprungen} Symlink(s) oder Submodul(e) im Stand werden nicht exportiert.")

    funde = alle_funde(eintraege, muster)
    zeilen = fund_zeilen(funde, eintraege, muster) if funde else []
    ergebnis = Ergebnis(info, version, len(eintraege), tuple(ausgenommen), muster, tuple(funde),
                        tuple(zeilen), None, False, ())
    if funde or nur_pruefen:
        return ergebnis

    ordner, geschuetzt = ziel_pruefen(ziel, root)
    _pfade_pruefen(eintraege, geschuetzt)
    spiegeln(ordner, eintraege, geschuetzt)
    return ergebnis._replace(ziel=ordner, geschrieben=True, status=tuple(_status_kurz(ordner)))


def _naechste_schritte(ergebnis: Ergebnis) -> list[str]:
    """Die Befehle aus docs/RELEASE.md, Abschnitt Veroeffentlichen -- mit dem echten Ziel und der echten
    Version. Das Werkzeug fuehrt sie nie selbst aus."""
    ziel = ergebnis.ziel
    version, tag = ergebnis.version, f"v{ergebnis.version}"
    return [
        "Nächste Schritte (das macht dieses Werkzeug nicht selbst; docs/RELEASE.md, Abschnitt Veröffentlichen):",
        f"  1. Ergebnis durchsehen: git -C \"{ziel}\" status und git -C \"{ziel}\" diff",
        f"  2. Committen, mit Signatur und der noreply-Adresse (geprüft): git -C \"{ziel}\" add -A, dann "
        f"git -C \"{ziel}\" commit -s -m \"BMS {version}\"",
        f"  3. main pushen: git -C \"{ziel}\" push origin main",
        "  4. Die CI im öffentlichen Repo abwarten (muss grün sein)",
        f"  5. Taggen und das Tag pushen (das startet das Release): git -C \"{ziel}\" tag -a {tag} -m "
        f"\"BMS {version}\", dann git -C \"{ziel}\" push origin {tag}",
        f"  6. Das Release prüfen: scripts/release.sh abholen {version}",
    ]


def _ausgabe_ergebnis(ergebnis: Ergebnis, nur_pruefen: bool) -> None:
    if ergebnis.funde:
        print(f"Funde: {len(ergebnis.funde)}")
        for zeile in ergebnis.fund_zeilen:
            print(zeile)
        print("Nichts geschrieben (Funde vorhanden). Die Fundstellen zeigen nur Datei, Zeile und Regel.")
        return
    if nur_pruefen:
        print("Prüfung ohne Fund. Nichts geschrieben (--pruefen).")
        return
    print(f"Geschrieben: {ergebnis.anzahl_dateien} Dateien nach {ergebnis.ziel}")
    if ergebnis.status:
        print("git status --short im Ziel:")
        for zeile in ergebnis.status[:STATUS_MAX_ZEILEN]:
            print(f"  {zeile}")
        if len(ergebnis.status) > STATUS_MAX_ZEILEN:
            print(f"  ... und {len(ergebnis.status) - STATUS_MAX_ZEILEN} weitere "
                  f"(insgesamt {len(ergebnis.status)} Zeilen)")
    else:
        print("git status --short im Ziel: keine Änderungen gegenüber dem letzten Commit.")
    for zeile in _naechste_schritte(ergebnis):
        print(zeile)


# ── Aufruf ───────────────────────────────────────────────────────────────────────────────────

class _Parser(argparse.ArgumentParser):
    def error(self, message: str):
        raise _AufrufFehler(message)


def _parser() -> argparse.ArgumentParser:
    ap = _Parser(prog="veroeffentlichen.sh", allow_abbrev=False,
                 description="Erzeugt den öffentlichen Baum aus einem Commit des privaten Repos "
                             "und verweigert bei jedem Fund.")
    ap.add_argument("--ziel", metavar="ORDNER",
                    help="lokale Arbeitskopie des öffentlichen Repos (Pflicht, außer mit --pruefen)")
    ap.add_argument("--ref", default="HEAD", metavar="COMMIT",
                    help="Commit, der exportiert wird (Vorgabe HEAD; muss in main enthalten sein)")
    ap.add_argument("--pruefen", action="store_true", help="nur prüfen, nichts schreiben")
    return ap


def main(argv: list[str] | None = None, projekt_root: Path = PROJECT_ROOT, *,
         db_pfad: Path | None = None, extra: Path | None = None) -> int:
    ap = _parser()
    try:
        args = ap.parse_args(argv)
        if args.ref.startswith("-"):
            raise _AufrufFehler("--ref erwartet einen Commit, keine Option.")
        if not args.pruefen and not args.ziel:
            raise _AufrufFehler("--ziel fehlt (ohne --pruefen wird in eine Arbeitskopie gespiegelt).")
    except _AufrufFehler as exc:
        ap.print_usage(sys.stdout)
        print(f"Aufruf falsch: {exc}")
        return EXIT_AUFRUF
    except SystemExit as exc:                      # --help
        return exc.code if isinstance(exc.code, int) else EXIT_OK

    try:
        ergebnis = exportieren(ziel=args.ziel, ref=args.ref, nur_pruefen=args.pruefen,
                               projekt_root=projekt_root, db_pfad=db_pfad, extra=extra)
    except VeroeffentlichungFehler as exc:
        print(f"Abbruch: {exc}")
        return EXIT_ABBRUCH
    except OSError as exc:
        print(f"Abbruch: {exc.__class__.__name__} beim Schreiben ({exc.strerror or exc}). Das Ziel kann "
              "halb beschrieben sein; git -C <Ziel> status zeigt den Stand.")
        return EXIT_ABBRUCH

    _ausgabe_ergebnis(ergebnis, args.pruefen)
    return EXIT_FUNDE if ergebnis.funde else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
