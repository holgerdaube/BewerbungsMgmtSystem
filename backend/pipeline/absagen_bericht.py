"""P2-79: Der neueste Lost-Order-Bericht (Skill `absagen-analyse`) und ob ein neuer fällig ist.

Zwei Nutzer, deshalb ein eigenes Modul: die Coach-Site verlinkt den neuesten Bericht samt Datum
(`coach_export.py`), und der Tageslauf fragt vor dem Modellstart, ob der Wochenlauf dran ist
(`agent_runner`, Schlüssel `in_kette_nur_wenn`). Beide müssen denselben Bericht für den neuesten
halten, sonst verlinkt die Coach-Site einen anderen als den, nach dem der Rhythmus rechnet.

DAS DATUM KOMMT AUS DEM DATEINAMEN (`JJJJMMTT_Analyse_Absagen.html`, ältere Läufe `JJJJ_MM_TT_…`),
nicht aus der Änderungszeit: Die Nachrüstung der Favicons (`favicon_nachruesten`) und die
Umbenennung des Bestands (P2-63) haben die Änderungszeiten alter Berichte auf spätere Tage gesetzt.
Nach der Änderungszeit sortiert, sähe ein Bericht vom Juli wie einer vom August aus. Nur eine Datei
ohne Datum im Namen fällt auf die Änderungszeit zurück.

RHYTHMUS: ein Bericht je Kalenderwoche (Montag bis Sonntag). Fällig ist der Lauf, wenn der neueste
Bericht vor dem Montag der laufenden Woche entstand. Normalerweise trifft das den Montags-Tageslauf;
fällt der aus, holt der nächste Tageslauf derselben Woche ihn nach. Ein Start von Hand mitten in der
Woche zählt für diese Woche mit. Eine starre 7-Tage-Frist dagegen wanderte mit jedem Nachholen um
einen Tag weiter durch die Woche.
"""
import datetime
import re
from pathlib import Path
from typing import Optional

MUSTER = "*Analyse_Absagen*.html"

# Status, die der Bericht auswertet (Absagen und bestätigte Funkstille, s. absagen-analyse/SKILL.md).
# Gibt es keine einzige solche Stelle, hat der Lauf nichts auszuwerten und kostet nur Geld.
_STATUS_AUSWERTBAR = ("Absage", "Keine Rückmeldung")

# Erfundene Stellen einer frischen Installation (`app/beispieldaten.py`, `portal`). Sie enthalten
# Absagen; ohne diesen Ausschluss liefe in jeder neuen Installation jede Woche eine Analyse über
# Beispieldaten.
_PORTAL_BEISPIELDATEN = "Beispieldaten"

_DATUM_RE = re.compile(r"^(\d{4})_?(\d{2})_?(\d{2})_")


def ordner() -> Path:
    from app.db import DATA_DIR      # zur Laufzeit: Tests lenken DATA_DIR um (conftest, T1)
    return DATA_DIR / "analysen"


def berichtsdatum(pfad: Path) -> datetime.date:
    """Datum aus dem Dateinamen, sonst (kein gültiges Datum im Namen) aus der Änderungszeit."""
    m = _DATUM_RE.match(pfad.name)
    if m:
        try:
            return datetime.date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            pass
    return datetime.date.fromtimestamp(pfad.stat().st_mtime)


def neuester(verzeichnis: Optional[Path] = None) -> Optional[tuple[Path, datetime.date]]:
    """(Pfad, Berichtsdatum) des neuesten Berichts oder None. Gleiches Datum: die zuletzt
    geschriebene Datei gewinnt."""
    verzeichnis = verzeichnis or ordner()
    if not verzeichnis.is_dir():
        return None
    kandidaten = [(berichtsdatum(p), p.stat().st_mtime, p)
                  for p in verzeichnis.glob(MUSTER) if p.is_file()]
    if not kandidaten:
        return None
    datum, _, pfad = max(kandidaten)
    return pfad, datum


def anzahl_auswertbar() -> int:
    """Stellen mit Absage oder „Keine Rückmeldung“, ohne gelöschte und ohne Beispieldaten."""
    from sqlmodel import Session, func, or_, select
    from app.db import engine
    from app.models import Job

    with Session(engine) as s:
        return s.exec(select(func.count()).select_from(Job).where(
            Job.deleted_at.is_(None),
            Job.status.in_(_STATUS_AUSWERTBAR),
            or_(Job.portal.is_(None), Job.portal != _PORTAL_BEISPIELDATEN),
        )).one()


def faellig(heute: Optional[datetime.date] = None, verzeichnis: Optional[Path] = None,
            anzahl: Optional[int] = None) -> tuple[bool, str]:
    """(fällig?, Begründung) für den Wochenlauf im Tageslauf. Die Begründung steht danach im
    Task-Center, beim Überspringen ist sie das Einzige, was der Nutzer von dem Schritt sieht."""
    from app.sprache import datum, tx      # zur Laufzeit, wie `app.db` oben: das Modul bleibt leicht zu importieren

    heute = heute or datetime.date.today()
    if anzahl is None:
        anzahl = anzahl_auswertbar()
    if anzahl == 0:
        return False, tx("Übersprungen: keine Absagen und keine unbeantworteten Bewerbungen auszuwerten.")
    bericht = neuester(verzeichnis)
    if bericht is None:
        return True, tx("Noch kein Bericht vorhanden.")
    _, berichtsdatum = bericht
    wochenbeginn = heute - datetime.timedelta(days=heute.weekday())
    if berichtsdatum >= wochenbeginn:
        return False, tx("Übersprungen: Der Bericht dieser Woche liegt vor (Stand {datum}).", datum=datum(berichtsdatum))
    return True, tx("Letzter Bericht vom {datum}.", datum=datum(berichtsdatum))
