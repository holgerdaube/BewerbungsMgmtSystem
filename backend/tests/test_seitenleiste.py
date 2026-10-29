"""P2-61: Jede Seite der Oberfläche ist über die Seitenleiste erreichbar.

Anlass: Phase 40 nahm den Beirat aus der Seitenleiste, die Route `/beirat` blieb. Für den Entwickler war
die Adresse kein Problem; die Kunden-Doku musste dagegen erklären, wie man `/beirat` von Hand an
die Adresse anhängt. Dieser Test verlangt für jede feste Route aus `App.tsx` einen Eintrag in
`NAV` (`components/Layout.tsx`), außer für Seiten, die eine andere Seite öffnet; die stehen mit
Grund in `OHNE_MENUEPUNKT`.

Bewusst nicht geprüft: ob ein Eintrag zur Laufzeit sichtbar ist. Outreach steht in `NAV`,
erscheint aber nur, wenn es Outreach-Zeilen gibt (P2-61). Das ist Absicht und im Browser belegt.
"""
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"

# Route → warum sie ohne eigenen Menüpunkt auskommt.
OHNE_MENUEPUNKT = {
    "/jobs/neu": "öffnet sich über „+ Stelle anlegen“ in der Stellenliste und aus einer Mail der Inbox",
}


def _routen() -> set[str]:
    quelle = (FRONTEND / "App.tsx").read_text(encoding="utf-8")
    pfade = set(re.findall(r'<Route\s+path="([^"]+)"', quelle))
    # Routen mit Parameter (/jobs/:id) erreicht man über ihre Liste, nie direkt aus dem Menü.
    return {p for p in pfade if ":" not in p}


def _menuepunkte() -> set[str]:
    quelle = (FRONTEND / "components" / "Layout.tsx").read_text(encoding="utf-8")
    nav = re.search(r"const NAV = \[(.*?)\n\]", quelle, re.S)
    assert nav, "NAV-Liste in Layout.tsx nicht gefunden"
    return set(re.findall(r"to: '([^']+)'", nav.group(1)))


def test_jede_seite_hat_einen_menuepunkt():
    ohne = _routen() - _menuepunkte() - set(OHNE_MENUEPUNKT)
    assert not ohne, f"Seiten ohne Menüpunkt (nur über die Adresse erreichbar): {sorted(ohne)}"


def test_ausnahmen_und_menuepunkte_zeigen_auf_echte_seiten():
    """Gegenrichtung: Eine Ausnahme oder ein Menüpunkt ohne Route wäre ein toter Eintrag."""
    routen = _routen()
    assert set(OHNE_MENUEPUNKT) <= routen
    assert _menuepunkte() <= routen


def test_erkennung_liest_beide_dateien():
    """Die Erkennung selbst: Fände sie nichts, wäre der erste Test immer grün."""
    assert {"/", "/beirat", "/jobs/neu"} <= _routen()
    assert {"/", "/netzwerk", "/rechtliches"} <= _menuepunkte()
