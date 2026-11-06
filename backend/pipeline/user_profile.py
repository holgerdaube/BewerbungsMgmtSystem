"""Zentrale Nutzer-Identität: EIN Leser für den Namen aus `config/profil.md`.

Phase 71A (Neutralisierung Backend): ersetzt die vorher in `pipeline/cv_export.py` duplizierte
Lese-Logik (`_name_aus_profil`) — dieses Modul ist ab jetzt die einzige Stelle, die
`config/profil.md` nach dem Namen durchsucht; alle anderen Stellen (naming.py, cv_export.py,
main.py, export_outreach.py, …) rufen `user_name()`/`user_first_name()` auf, statt selbst zu
parsen ("ein Leser, eine Wahrheit").

BMS_DATA_DIR-unabhängig: `profil.md` liegt IMMER projekt-root-relativ unter `config/` (exakt wie
zuvor in `cv_export.py`) — das Profil ist Teil der Konfiguration/Installation, nicht der per
BMS_DATA_DIR verschiebbaren Laufzeitdaten.

Kein In-Prozess-Cache (bewusst, Design-Entscheidung): die Datei ist wenige hundert Bytes groß,
ein Regex-Scan kostet Mikrosekunden, und `user_name()` wird pro Export/Aufruf höchstens
einige Male aufgerufen — kein Hot-Path. Ein Cache hätte in Tests (mehrere Profil-Fixtures pro
Prozess über `monkeypatch`) nur Fallen aufgemacht, ohne einen gemessenen Bedarf zu lösen
(die Spec erlaubt einen einfachen Cache, verlangt ihn aber nicht — "Simplicity First").

Fallback "Bewerber" (nicht der Name des Entwicklers): Phase 71 macht das System personen-neutral; ohne
gepflegtes Profil erscheint ein generischer Platzhalter statt eines fremden Namens.
"""
import re
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Bewerbung_Mgmt_System/
_PROFIL_MD = PROJECT_ROOT / "config" / "profil.md"
_FALLBACK_NAME = "Bewerber"

_NAME_RE = re.compile(r"\*\*Name:\*\*\s*(.+)")
_STANDORT_RE = re.compile(r"\*\*Standort:\*\*\s*(.+)")
_KONTAKT_RE = re.compile(r"\*\*Kontakt:\*\*\s*(.+)")
_LINKEDIN_RE = re.compile(r"\*\*LinkedIn:\*\*\s*(.+)")


def _fallback_name() -> str:
    from app.sprache import uebersetzt    # erst hier: Dieses Modul läuft auch ohne Datenbank-Importe
    return uebersetzt(_FALLBACK_NAME)


def user_name() -> str:
    """Name aus `config/profil.md` (`## Identität` → `**Name:** …`), getrimmt.

    Fallback `"Bewerber"`, wenn die Datei fehlt, nicht lesbar ist, kein `**Name:**`-Eintrag
    gefunden wird, oder der Eintrag nach dem Trimmen leer ist — nie ein Crash, nie ein leerer
    String (Aufrufer wie `naming.py` verlassen sich auf einen nicht-leeren Rückgabewert)."""
    try:
        text = _PROFIL_MD.read_text(encoding="utf-8")
    except OSError:
        return _fallback_name()
    m = _NAME_RE.search(text)
    if not m:
        return _fallback_name()
    name = m.group(1).strip()
    return name or _fallback_name()


def user_first_name() -> str:
    """Erstes Wort von `user_name()` — für Fließtext ("Soll sich <Vorname> auf … bewerben?").
    `user_name()` ist laut Kontrakt nie leer/nur-Whitespace, `.split()[0]` ist daher sicher."""
    return user_name().split()[0]


def _feld(muster) -> str:
    """Ein `**Feld:** …`-Eintrag aus `config/profil.md`, oder "" wenn er fehlt."""
    try:
        text = _PROFIL_MD.read_text(encoding="utf-8")
    except OSError:
        return ""
    m = muster.search(text)
    return m.group(1).strip() if m else ""


def _standort_ohne_klammerzusatz() -> str:
    """`**Standort:**` aus `config/profil.md`, ohne einen Klammerzusatz am Ende (z. B. "…
    (Rhein-Main)") — gemeinsame Normalisierung fuer `briefkopf()`, `briefkopf_ort()` und
    `anschrift()` (P2-50: vorher in `briefkopf()`/`briefkopf_ort()` je einzeln dupliziert)."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", _feld(_STANDORT_RE)).strip()


def briefkopf() -> str:
    """Absenderblock fuer Anschreiben — Name, Anschrift, Kontakt, LinkedIn.

    ANLASS (P2-24, 31.08.2026): Ein Anschreiben kam einmal ohne Briefkopf heraus. Der
    Renderer erwartete ihn im Text, der Skill listete ihn in seinem `Aufbau` aber NICHT auf —
    er stand nur beilaeufig in einer Klammer, die klang, als erzeuge ihn der Renderer. Zwei
    Laeufe am selben Tag: einer schrieb ihn, der andere nicht. Ein Briefkopf besteht aus reinen
    Profildaten; ihn ein Modell schreiben zu lassen heisst, eine Konstante jedes Mal neu zu
    wuerfeln.

    Die `Standort`-Zeile im Profil traegt einen Zusatz in Klammern ("… (Rhein-Main)"), der in
    einen Briefkopf nicht gehoert — er wird entfernt.

    Leere Rueckgabe, wenn kein Name im Profil steht: Dann ist das Profil nicht gepflegt, und ein
    Kopf aus Platzhaltern waere schlechter als keiner.
    """
    name = user_name()
    if name == _FALLBACK_NAME:
        return ""
    zeilen = [name]
    standort = _standort_ohne_klammerzusatz()
    if standort:
        zeilen.append(standort)
    kontakt = _feld(_KONTAKT_RE)
    if kontakt:
        # Im Profil mit "·" getrennt, im Brief ist "|" die gewohnte Schreibweise.
        zeilen.append(kontakt.replace("·", "|"))
    linkedin = _feld(_LINKEDIN_RE)
    if linkedin:
        zeilen.append("LinkedIn: " + linkedin)
    return "\n".join(zeilen)


def briefkopf_ort() -> str:
    """Ort fuer die Ort-/Datumszeile — die Stadt aus der Anschrift ("12345 Musterstadt" -> "Musterstadt")."""
    standort = _standort_ohne_klammerzusatz()
    if not standort:
        return ""
    letzter = standort.split(",")[-1].strip()
    ohne_plz = re.sub(r"^\d{4,5}\s+", "", letzter)
    return ohne_plz or letzter


def anschrift() -> str:
    """Anschrift aus `config/profil.md` (`**Standort:**`), ohne Klammerzusatz.

    P2-50 (Kundenpaket): Startpunkt der Routenplanung zu Vorstellungsgesprächen (`GET /api/profil`
    → `adresse`, genutzt von `FollowUps.tsx`/`JobDetail.tsx`) stand bisher fest im Frontend
    (eine feste Adresse) — falsch fuer fast jeden Nutzer. Leerer String, wenn
    Datei oder Feld fehlt (dieselbe Nicht-Erfinden-Regel wie `briefkopf()`)."""
    return _standort_ohne_klammerzusatz()
