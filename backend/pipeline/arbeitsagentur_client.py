#!/usr/bin/env python3
"""Arbeitsagentur-Jobsuche über die serverseitig gerenderte Suchseite (Phase 86, vormals
Phase 37 REST-API).

WARUM SSR STATT REST-API (Umbau 21.08.2026): `rest.arbeitsagentur.de` antwortet auf JEDEM Pfad
mit HTTP 403 bei 1 Byte Body — auch auf der Host-Wurzel, mit und ohne API-Key, mit und ohne
Sandbox-Umgebung (Gegentest gegen github.com: HTTP 200). Live verifiziert 21.08.2026 — das ist
eine Netzsperre, kein Auth- oder Versionsproblem. In den 14 Tagen davor hat der alte, auf dieser
API basierende Client 110 Fehlversuche produziert (Beleg:
`tasks/spec_phase86_tageslauf_bereinigung.md`, Befund 6). Die Jobsuche-SEITE
(`https://www.arbeitsagentur.de/jobsuche/suche`) ist dagegen erreichbar (HTTP 200) und liefert
serverseitig gerendertes HTML (`"from-ssr":true`) mit einem eingebetteten
`<script type="application/json">`-Block (Angular-SSR-State), dessen JSON ein Dict mit Schlüssel
`suchergebnis` ist — darin `ergebnisliste` (fest 25 Einträge je Seite, unabhängig vom
`size`-Parameter) und `maxErgebnisse`. Live verifiziert 21.08.2026.

Ein 403 auf `rest.arbeitsagentur.de` ist demnach KEIN Grund, diesen Kanal in der Jobsuche zu
überspringen — dieser Host wird seit diesem Umbau gar nicht mehr angesprochen.

WARUM DETERMINISTISCH statt Agent-gesteuert (wie apify_client.py):
    Fakten holen ist hier reine Mechanik (ein GET, feste Parameter, HTML parsen). Die
    Beurteilung (passt der Titel? greift eine Ausschlussregel? welcher Score?) trifft weiterhin
    der `jobsuche`-Skill — Modul liefert Rohdaten, Agent urteilt.

KEIN Budget-Guard (anders als apify_client.py) — der Abruf ist eine öffentliche Webseite ohne
Account/Key, es gibt kein Secret, das geschützt werden müsste.

Homeoffice-Filter (`arbeitszeit=ho`) — MESSPROTOKOLL, nicht löschen, nur fortschreiben:
    17.07.2026 (gegen die alte REST-API): der Parameter FUNKTIONIERT mechanisch — ein breiter
    Testbegriff ("Leiter") ging damit von 9529 auf 9 Treffer zurück. Für enge PS-/CS-
    Leitungstitel war die Schnittmenge mit BA-Homeoffice-Tags aber leer (0 Treffer, mehrfach
    getestet) — damals als Bestands-Sparsity gewertet, kein Parameter-Bug.
    21.08.2026 (gegen die neue SSR-Suchseite, live verifiziert): derselbe Filter liefert für
    „Leiter Professional Services“ jetzt 11 von 36 Treffern; der breite Test „Leiter“ geht von
    6612 auf 536 zurück. Der Filter wirkt also inzwischen AUCH für die engen Titel — ob das an
    einem Bestandswechsel seit Juli oder an einem Unterschied REST- vs. SSR-Datenbestand liegt,
    ist offen. Konsequenz: `arbeitszeit=ho` kann jetzt sinnvoll auch für die engen PS-/CS-Titel
    gesetzt werden; die alte Erfahrung (Bestands-Sparsity möglich, je nach Titel/Zeitpunkt wieder
    leer) im Hinterkopf behalten statt blind zu verwerfen.
    13.10.2026 (P2-73, live gemessen): Die Suchseite leitet jede Anfrage auf ihre kanonische Form
    um und hängt dabei `suchbereich=jobs` an; aus `arbeitszeit=ho` macht sie
    `homeoffice=prozentual_0`. Der Client folgt den Umleitungen (`follow_redirects=True`), die
    Trefferzahlen sind über beide Wege identisch („Leiter Professional Services“, 30 Tage:
    34 ohne Filter, 11 mit Homeoffice, 8 im Umkreis von 100 km). Bewusst NICHT auf die neue
    Parameterform umgestellt: Auch eine Anfrage, die `suchbereich=jobs` schon mitbringt, wird
    einmal umgeleitet (Kodierung und Reihenfolge), gewonnen wäre also nichts, und die Übersetzung
    des Homeoffice-Filters macht die Seite selbst. Fällt diese Übersetzung einmal weg, liefert
    `arbeitszeit=ho` dieselbe Zahl wie ohne Filter — daran ist es zu erkennen.

CLI (aus backend/):
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.arbeitsagentur_client run \\
        --was "Leiter Professional Services" [--wo "Frankfurt am Main" --umkreis 100] \\
        [--days 7] [--size 25] [--page 1] [--arbeitszeit ho]

`--size` ist seit Phase 86 die GEWÜNSCHTE Anzahl Records, NICHT mehr ein API-Parameter — der
`size`-Query-Parameter der SSR-Seite ist nachweislich wirkungslos (live verifiziert 21.08.2026,
immer 25 Treffer je Seite). Der Client holt dafür bei Bedarf weitere Seiten nach (`page`,
`page + 1`, …), bis entweder `size` Records vorliegen oder `maxErgebnisse` erschöpft ist —
HÖCHSTENS aber `MAX_PAGES` (4) Seiten je Aufruf. Das ist eine Leitplanke gegen versehentlich
riesige Abrufe, im Geist des früheren `SIZE_HARD` der REST-Variante.

Ausgabe: JSON-Summary auf stdout + Rohdaten unter data/arbeitsagentur/<datum>_<slug>.json.
Record-Schema (bereits normalisiert aufs jobsuche-Ingest-Schema): company, title, location,
url, portal, published_date, raw_json (kompletter Treffer-Eintrag der Suchseite, inkl. z. B.
`homeofficemoeglich`, falls die Seite ihn für den Treffer mitliefert).
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent   # Bewerbung_Mgmt_System/
OUT_DIR = PROJECT_ROOT / "data" / "arbeitsagentur"

SUCHE = "https://www.arbeitsagentur.de/jobsuche/suche"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")
DETAIL_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"

SIZE_DEFAULT = 25
PAGE_SIZE = 25    # von der Seite fest vergeben — der `size`-Parameter wirkt serverseitig NICHT
                  # (live verifiziert 21.08.2026), deshalb hier keine Query-Konstante namens size.
MAX_PAGES = 4     # Leitplanke gegen versehentlich riesige Abrufe (Nachfolger des alten SIZE_HARD)

_JSON_SCRIPT_RE = re.compile(
    r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', re.S
)


def _die(msg: str, code: int = 1) -> "NoReturn":       # noqa: F821
    """Sauberer Fehlerpfad statt Traceback — Seite down/Timeout/umgebaut darf den Aufrufer
    (jobsuche-Skill) nie mit einem Crash stoppen, nur mit einer lesbaren Meldung + Exit != 0."""
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _extract_suchergebnis(html: str) -> dict:
    """Sammelt alle `<script type="application/json">`-Blöcke im HTML ein und gibt den
    `suchergebnis`-Teil des Blocks zurück, dessen `json.loads`-Ergebnis ein Dict mit Schlüssel
    `suchergebnis` ist (Angular-SSR-State-Block). Bewusst über den INHALT erkannt, nicht über
    Script-Attribute (z. B. `id="ng-state"`) — die Id ist kein stabiler Vertrag, der Inhalt schon
    eher. Liefert die Seite HTTP 200, aber keinen solchen Block (Fall D2 der Spec: Seite wurde
    umgebaut), bricht diese Funktion über `_die()` ab — NIEMALS wird das still als 0 Treffer
    durchgereicht, sonst fällt ein künftiger Umbau der Seite unbemerkt aus."""
    for block in _JSON_SCRIPT_RE.findall(html):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if isinstance(data, dict) and "suchergebnis" in data:
            return data["suchergebnis"]
    _die(
        "Arbeitsagentur-Suchseite: HTTP 200, aber kein JSON-Block mit Schlüssel "
        "'suchergebnis' im HTML gefunden — die Seite wurde vermutlich umgebaut. Das ist "
        "KEIN Ergebnis von 0 Treffern, sondern ein Parser-Defekt: bitte prüfen, nicht ignorieren."
    )


def _normalize(item: dict) -> dict:
    """SSR-Suchseiten-Eintrag -> jobsuche-Ingest-Schema (Feld-Mapping s. Spec Phase 86, Stufe D1).
    `url` wie schon in der alten REST-Variante: `externeURL` (Arbeitgeber-Original) gewinnt, falls
    gesetzt — das ist auf der Suchseite oft der Fall und damit besser befüllt als in der alten
    REST-API; sonst Fallback auf die maschinenlesbare BA-Detailseite über `referenznummer`."""
    adresse = ((item.get("stellenlokationen") or [{}])[0] or {}).get("adresse") or {}
    ort = adresse.get("ort")
    plz = adresse.get("plz")
    location = f"{plz} {ort}".strip() if (plz and ort) else (ort or plz)
    refnr = item.get("referenznummer")
    url = item.get("externeURL") or (DETAIL_URL.format(refnr=refnr) if refnr else None)
    published = item.get("datumErsteVeroeffentlichung") or (
        (item.get("veroeffentlichungszeitraum") or {}).get("von")
    )
    return {
        "company": item.get("firma"),
        "title": item.get("stellenangebotsTitel"),
        "location": location,
        "url": url,
        "portal": "Arbeitsagentur",
        "published_date": published,
        "raw_json": item,
    }


def run(was: str, wo: str = None, umkreis: int = None, days: int = None,
        size: int = SIZE_DEFAULT, page: int = 1, arbeitszeit: str = None) -> dict:
    gewuenscht = max(1, int(size))
    p = max(1, int(page))

    records: list[dict] = []
    max_ergebnisse = None
    seiten_geholt = 0

    with httpx.Client(timeout=30.0, follow_redirects=True, headers={"User-Agent": UA}) as cl:
        while seiten_geholt < MAX_PAGES:
            params = {"angebotsart": 1, "was": was, "page": p}
            if wo:
                params["wo"] = wo
            if umkreis:
                params["umkreis"] = int(umkreis)
            if days:
                params["veroeffentlichtseit"] = int(days)
            if arbeitszeit:
                params["arbeitszeit"] = arbeitszeit

            try:
                r = cl.get(SUCHE, params=params)
            except httpx.TimeoutException:
                _die("Arbeitsagentur-Suchseite: Timeout nach 30s — leeres Ergebnis, kein Absturz.")
            except httpx.RequestError as e:
                _die(f"Arbeitsagentur-Suchseite nicht erreichbar ({type(e).__name__}) — "
                     "leeres Ergebnis, kein Absturz.")

            if r.status_code >= 400:
                _die(f"Arbeitsagentur-Suchseite HTTP {r.status_code} — leeres Ergebnis, kein Absturz.")

            suchergebnis = _extract_suchergebnis(r.text)
            seiten_geholt += 1
            max_ergebnisse = suchergebnis.get("maxErgebnisse")
            seite_items = suchergebnis.get("ergebnisliste") or []
            records.extend(_normalize(it) for it in seite_items)

            if len(records) >= gewuenscht:
                break
            if len(seite_items) < PAGE_SIZE:
                break   # letzte Seite erreicht (weniger als PAGE_SIZE Treffer zurueckgegeben)
            if max_ergebnisse is not None and (p * PAGE_SIZE) >= max_ergebnisse:
                break   # naechste Seite waere ohnehin leer
            p += 1

    records = records[:gewuenscht]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.date.today().isoformat()
    slug = was.lower().replace(" ", "_")[:40]
    out_file = OUT_DIR / f"{stamp}_{slug}.json"
    out_file.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "was": was, "wo": wo, "umkreis": umkreis, "arbeitszeit": arbeitszeit,
        "treffer": len(records), "maxErgebnisse": max_ergebnisse,
        "rohdaten": str(out_file.relative_to(PROJECT_ROOT)),
        "vorschau": records[:5],
        "hinweis": "Rohdaten. Titel-/Ausschlusspruefung und Scoring macht der jobsuche-Skill.",
    }


def main() -> None:
    ap = argparse.ArgumentParser(prog="pipeline.arbeitsagentur_client")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_r = sub.add_parser("run", help="Arbeitsagentur-Suchseite abfragen (kostenlos, kein Account)")
    p_r.add_argument("--was", required=True, help='Titel/Suchbegriff, z. B. "Leiter Professional Services"')
    p_r.add_argument("--wo", default=None, help='Ort, z. B. "Frankfurt am Main"')
    p_r.add_argument("--umkreis", type=int, default=None, help="Radius in km (nur mit --wo sinnvoll)")
    p_r.add_argument("--days", type=int, default=None, help="veroeffentlichtseit in Tagen, z. B. 7")
    p_r.add_argument("--size", type=int, default=SIZE_DEFAULT,
                      help=f"Default {SIZE_DEFAULT}, gewuenschte Record-Anzahl (nicht der Seiten-Parameter, "
                           f"s. Modul-Docstring) — holt bei Bedarf bis zu {MAX_PAGES} Seiten nach")
    p_r.add_argument("--page", type=int, default=1, help="Start-Seite")
    p_r.add_argument("--arbeitszeit", default=None, help='z. B. "ho" (Homeoffice) — s. Modul-Docstring: '
                                                          "Messprotokoll 17.07.2026 / 21.08.2026")

    a = ap.parse_args()
    out = run(a.was, wo=a.wo, umkreis=a.umkreis, days=a.days, size=a.size, page=a.page,
             arbeitszeit=a.arbeitszeit)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
