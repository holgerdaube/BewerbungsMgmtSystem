"""Dokumentationsseite (P2-59, Paket D): welche Dokumente die Oberfläche zeigt und wie aus einer
Markdown-Datei die Seite wird, die im Rahmen der Dokumentation steht.

Eine feste Liste (`KATALOG`) statt eines Ordner-Scans: Die Oberfläche zeigt genau die Dokumente,
die für diese Installation gedacht sind, in fester Reihenfolge und mit lesbaren Titeln. Zwei Gruppen:

  * "kunde"  liegt auch im Kundenpaket (`pipeline.kundenpaket`: `DOKU_ERLAUBT` plus die Dateien
             im Paket-Root: CHANGELOG.md und die beiden Installationsanleitungen).
  * "intern" gibt es nur in der Entwicklungsinstallation. Das Paket enthält diese Dateien nicht,
             und `verfuegbar()` lässt jeden Eintrag weg, dessen Datei fehlt. Eine eigene Kennung
             der Installationsart braucht es dafür nicht.

Sicherheit: Der Name aus der Adresse wird nie als Pfad benutzt. `eintrag_fuer` vergleicht ihn nur
mit den Einträgen der Liste (Kennung oder Dateiname), alles andere ist unbekannt. Gelesen wird
ausschließlich die `datei` eines Listeneintrags, relativ zum Projekt-Root, und `rendern` nimmt
nur Einträge, die genau so in der Liste stehen. Dateinamen mit Endung `.md` oder `.html` werden
angenommen, weil sich gerenderte Dokumente mit relativen Links aufeinander beziehen können: Die
Seite liegt unter `/api/doku/<name>`, ein Link auf `SETUP-EMAIL.html` löst darin zu
`/api/doku/SETUP-EMAIL.html` auf.

Der Projekt-Root ist ein Parameter und wird im Rumpf aufgelöst (Muster `app/version.py`): Tests
übergeben einen tmp-Ordner, und der Standardwert hängt nicht an einem beim Import festgelegten
Wert.

Der Reiter „Installation & Updates“ (P2-71) zeigt die Anleitung des laufenden Systems:
`BMS_Install_Windows.md` unter Windows, sonst `BMS_Install_MAC.md`. Kennung und Titel bleiben. Das
System ist wie der Projekt-Root ein Parameter (`systemname`, ein Wert von `os.name`) und wird im
Rumpf aufgelöst: Ein Test prüft beide Fälle, ohne `os.name` umzubiegen (Lehre aus Phase 71D,
`pathlib` verzweigt selbst auf `os.name`).
"""
from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath
from typing import Optional

from app import sprache
from pipeline import changelog

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Die beiden Installationsanleitungen (P2-71), je eine für ein System. Beide liegen im Kundenpaket,
# der Reiter „Installation & Updates“ zeigt nur die des laufenden Systems (`installationsdatei`).
INSTALLATION_MAC = "BMS_Install_MAC.md"
INSTALLATION_WINDOWS = "BMS_Install_Windows.md"
INSTALLATIONSDATEIEN = (INSTALLATION_MAC, INSTALLATION_WINDOWS)

# Die Reihenfolge ist die Reihenfolge der Tabs. Die Kundengruppe steht vor der internen, die
# Oberfläche setzt zwischen beide einen Trenner. `datei` ist ein Pfad mit "/" relativ zum
# Projekt-Root. `docs/FUNKTIONEN.md` entsteht erst mit dem Doku-Paket (P2-59, W): Bis dahin fehlt
# die Datei, und `verfuegbar()` lässt den Eintrag weg. Beim Eintrag "installation" steht hier die
# Mac-Datei als Platzhalter: `katalog()` setzt die Datei des gefragten Systems ein.
_KATALOG_BASIS: tuple[dict, ...] = (
    {"id": "version", "titel": "Version", "gruppe": "kunde", "datei": "CHANGELOG.md"},
    {"id": "funktionen", "titel": "Funktionen", "gruppe": "kunde", "datei": "docs/FUNKTIONEN.md"},
    {"id": "anleitung", "titel": "Anleitung", "gruppe": "kunde", "datei": "docs/ANLEITUNG.md"},
    {"id": "installation", "titel": "Installation & Updates", "gruppe": "kunde", "datei": INSTALLATION_MAC},
    {"id": "email", "titel": "E-Mail einrichten", "gruppe": "kunde", "datei": "docs/SETUP-EMAIL.md"},
    {"id": "windows", "titel": "Windows", "gruppe": "kunde", "datei": "docs/SETUP-WINDOWS.md"},
    {"id": "coach-site", "titel": "Coach-Site", "gruppe": "kunde", "datei": "docs/ANLEITUNG_COACH_SITE.md"},
    {"id": "beirat", "titel": "Beirat", "gruppe": "kunde", "datei": "docs/BEIRAT-CHARTA.md"},
    {"id": "technik", "titel": "Technik", "gruppe": "intern", "datei": "docs/DOKUMENTATION.md"},
    {"id": "automatik", "titel": "Automatik", "gruppe": "intern", "datei": "docs/AUTOMATION.md"},
    {"id": "release", "titel": "Release", "gruppe": "intern", "datei": "docs/RELEASE.md"},
    {"id": "entwicklung", "titel": "Entwickler-Installation", "gruppe": "intern", "datei": "docs/INSTALLATION.md"},
)


def englische_datei(datei: str) -> str:
    """Pfad der englischen Fassung (P2-91): `docs/X.md` → `docs/en/X.md`, im Projekt-Root `X.md` → `X.en.md`."""
    p = PurePosixPath(datei)
    return str(p.parent / "en" / p.name) if p.parent.name == "docs" else f"{p.stem}.en.md"


_TITEL_EN = {
    "version": "Version", "funktionen": "Features", "anleitung": "User guide",
    "installation": "Installation & updates", "email": "Email setup", "windows": "Windows",
    "coach-site": "Coach site", "beirat": "Advisory Board", "technik": "Technical", "automatik": "Automation",
    "release": "Release", "entwicklung": "Developer installation",
}


def titel(eintrag: dict) -> str:
    """Titel des Reiters in der aktuellen Sprache."""
    return _TITEL_EN[eintrag["id"]] if sprache.aktuell() == "en" else eintrag["titel"]


def installationsdatei(systemname: Optional[str] = None) -> str:
    """Die Installationsanleitung des Systems: `BMS_Install_Windows.md` für "nt", sonst
    `BMS_Install_MAC.md`. `systemname` ist ein Wert von `os.name`; ohne Angabe gilt das laufende
    System, aufgelöst beim Aufruf. Tests übergeben den Wert, statt `os.name` umzubiegen."""
    name = os.name if systemname is None else systemname
    return INSTALLATION_WINDOWS if name == "nt" else INSTALLATION_MAC


def katalog(systemname: Optional[str] = None) -> tuple[dict, ...]:
    """Der Katalog für ein System: Er unterscheidet sich nur in der Datei des Eintrags
    "installation". Neue Kopien, damit ein Aufrufer die Basisliste nicht verändert."""
    datei = installationsdatei(systemname)
    return tuple({**e, "datei": datei} if e["id"] == "installation" else dict(e) for e in _KATALOG_BASIS)


# Der Katalog des laufenden Systems (beim Import festgelegt, `os.name` ändert sich im Prozess nie).
# `verfuegbar()` und `eintrag_fuer()` lösen das System dagegen bei jedem Aufruf auf.
KATALOG: tuple[dict, ...] = katalog()

# Nur diese Endungen gelten als Dateiname. Alles andere (auch `.pdf`, `.txt`) ist unbekannt.
_DATEI_ENDUNGEN = (".md", ".html")

# Ein Anker-Tag, dann das, was ihn zum externen Link macht (Webadresse als Ziel) und was ihn
# davon ausnimmt (schon ein target). Relative Links auf andere Dokumente, Sprünge innerhalb der
# Seite und Mail-Adressen bleiben unberührt.
_ANKER_RE = re.compile(r"<a\b([^>]*)>")
_EXTERNES_ZIEL_RE = re.compile(r'\bhref="https?://', re.IGNORECASE)
_HAT_ZIEL_RE = re.compile(r"\btarget=", re.IGNORECASE)


def _root(projekt_root: Optional[Path]) -> Path:
    return Path(projekt_root) if projekt_root is not None else PROJECT_ROOT


def _pfad(eintrag: dict, root: Path) -> Path:
    return root.joinpath(*eintrag["datei"].split("/"))


def _vorhanden(eintrag: dict, root: Path) -> bool:
    try:
        return _pfad(eintrag, root).is_file()
    except OSError:     # unlesbarer Ordner: wie eine fehlende Datei behandeln
        return False


def verfuegbar(projekt_root: Optional[Path] = None, systemname: Optional[str] = None) -> list[dict]:
    """Die Einträge des Katalogs, deren Datei in dieser Installation existiert, in
    Katalog-Reihenfolge. Kopien, damit ein Aufrufer den Katalog nicht verändert. Hier fällt auch
    die Gruppe "intern" im Kundenpaket weg, weil das Paket diese Dateien nicht enthält. Der Reiter
    "installation" trägt die Anleitung des Systems `systemname` (Vorgabe: das laufende)."""
    root = _root(projekt_root)
    return [e for e in katalog(systemname) if _vorhanden(e, root)]


def _dateien_des_eintrags(eintrag: dict) -> tuple[str, ...]:
    """Alle Dateien, unter deren Namen ein Eintrag erreichbar ist. Meist ist es die eigene; die
    Installationsanleitung hat zwei (je System), und jede führt auf denselben Reiter. So löst ein
    Link auf die Anleitung des anderen Systems auf den Reiter auf und nicht ins Leere."""
    if eintrag["id"] == "installation":
        return INSTALLATIONSDATEIEN
    return (eintrag["datei"],)


def eintrag_fuer(name: str, projekt_root: Optional[Path] = None,
                 systemname: Optional[str] = None) -> Optional[dict]:
    """Der Katalogeintrag zu `name`, sonst None. `name` ist eine Kennung ("anleitung") oder der
    Dateiname eines Eintrags mit Endung `.md` oder `.html` ("ANLEITUNG.html", "BMS_Install_MAC.md"),
    jeweils ohne Unterscheidung von Groß- und Kleinschreibung. Ein Eintrag, dessen Datei fehlt,
    gilt als unbekannt, damit alles, was die Schnittstelle ausliefert, auch in `verfuegbar()` steht.
    Beide Installationsanleitungen (`BMS_Install_MAC.md`, `BMS_Install_Windows.md`) führen auf den
    Reiter "installation", dessen Datei die des Systems `systemname` ist (Vorgabe: das laufende).
    Die früheren Namen `BMS_Install.md` und `BMS_Install_Auto.md` kennt die Auflösung nicht mehr.

    Kennung und Dateiname verwechseln sich nie: Eine Kennung hat keinen Punkt, ein Dateiname
    immer. Das ist wichtig, weil "installation" die Kennung der Installationsanleitung ist, während
    `INSTALLATION.md` die Entwickler-Installation meint. Nur ASCII, damit keine Sonderschreibweise
    (etwa Zeichen, die sich beim Kleinschreiben in ASCII verwandeln) einen Treffer erzeugt."""
    if not isinstance(name, str) or not name.isascii():
        return None
    # P2-91: Links in der englischen Doku nennen `BMS_Install_MAC.en.md`, gemeint ist derselbe Reiter.
    gesucht = name.lower().replace(".en.", ".")
    root = _root(projekt_root)
    for eintrag in katalog(systemname):
        stamme = [PurePosixPath(datei).stem.lower() for datei in _dateien_des_eintrags(eintrag)]
        if gesucht == eintrag["id"] or gesucht in (s + endung for s in stamme for endung in _DATEI_ENDUNGEN):
            return eintrag if _vorhanden(eintrag, root) else None
    return None


def _ohne_leeren_abschnitt(text: str) -> str:
    """Der Abschnitt „Unveröffentlicht“ im CHANGELOG bleibt nach jeder Freigabe als leere
    Überschrift stehen. Der Renderer machte daraus eine leere Karte an erster Stelle, und genau
    die sähe jeder Kunde zuerst. Mit Inhalt (in der Entwicklungsinstallation) bleibt er."""
    for abschnitt in changelog.abschnitte(text):
        if abschnitt.version is None and not abschnitt.inhalt:
            return text[:abschnitt.start] + text[abschnitt.ende:]
    return text


def _externe_links_im_neuen_tab(seite: str) -> str:
    """Webadressen öffnen in einem neuen Tab. Sonst lädt ein Klick die fremde Seite in den Rahmen
    der Dokumentation, und viele Seiten verbieten das Einbetten. Der Rahmen erlaubt dafür Popups
    (`allow-popups`, und `allow-popups-to-escape-sandbox`, damit der neue Tab nicht selbst in der
    Sandbox läuft). `noopener` verhindert den Zugriff auf das öffnende Fenster."""
    def ersetzen(treffer: re.Match) -> str:
        attribute = treffer.group(1)
        if not _EXTERNES_ZIEL_RE.search(attribute) or _HAT_ZIEL_RE.search(attribute):
            return treffer.group(0)
        return f'<a{attribute} target="_blank" rel="noopener noreferrer">'
    return _ANKER_RE.sub(ersetzen, seite)


def rendern(eintrag: dict, projekt_root: Optional[Path] = None) -> str:
    """Die fertige Seite zu einem Katalogeintrag, über denselben Renderer wie die
    `docs/*.html`-Zwillinge (`pipeline.docs_render`). Ein Eintrag, der nicht unverändert im
    Katalog steht (für eines der beiden Systeme), ist ein Fehler (ValueError): Hier wird nie ein
    Pfad aus einer Anfrage gelesen.
    Eine fehlende oder nicht lesbare Datei wirft OSError.

    Der Renderer wird erst hier geladen: Fehlt das Markdown-Paket, betrifft das nur die
    Dokumentation und nicht den Start des Servers.

    P2-72: Die Seite trägt das Design, das JETZT gilt (`design.laden()`, bei jedem Aufruf gelesen). Die
    mitgelieferten `docs/*.html` rendern dagegen immer mit der Vorgabe."""
    if not any(eintrag in katalog(system) for system in ("nt", "posix")):
        raise ValueError("Unbekanntes Dokument")
    from pipeline import design
    from pipeline.docs_render import render_markdown

    root = _root(projekt_root)
    pfad = _pfad(eintrag, root)
    englisch = root / englische_datei(eintrag["datei"])
    if sprache.aktuell() == "en" and englisch.is_file():
        pfad, lang = englisch, "en"
    else:
        lang = "de"
    text = pfad.read_text(encoding="utf-8")
    if pfad.name in ("CHANGELOG.md", "CHANGELOG.en.md"):
        text = _ohne_leeren_abschnitt(text)
    return _externe_links_im_neuen_tab(render_markdown(text, pfad.name, design.laden(), sprache=lang))
