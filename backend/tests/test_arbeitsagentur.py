"""Tests fuer `pipeline/arbeitsagentur_client.py` (Phase 86, Stufe D/E2).

Testet den SSR-Parser (`_extract_suchergebnis`) und das Feld-Mapping (`_normalize`) GEGEN EIN
EINGECHECKTES HTML-FIXTURE (`fixtures/arbeitsagentur_suche.html`, gekuerzt aus einer echten,
live am 21.08.2026 abgerufenen Antwort von https://www.arbeitsagentur.de/jobsuche/suche) —
KEIN Netzabruf im Test. `run()` selbst wird hier bewusst NICHT aufgerufen: es schreibt nach
`data/arbeitsagentur/` (regulaerer Ausgabeordner des Clients), den der Test laut Bau-Auftrag
NICHT befuellen darf. Modul-Import auf Ebene der Testfunktionen ist hier unproblematisch —
`arbeitsagentur_client` importiert selbst kein `app.*`/`pipeline.db`-Modul und bindet keine
Pfade an Import-Zeit ausser `PROJECT_ROOT`/`OUT_DIR` (reine `Path`-Objekte, kein Dateizugriff),
die conftest-Regel (kein App-Import auf Modulebene) gilt trotzdem vorsorglich: Import passiert
in den Testfunktionen, nicht auf Modulebene dieser Datei.
"""
from pathlib import Path

import pytest

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_FIXTURE_HTML = (_FIXTURES_DIR / "arbeitsagentur_suche.html").read_text(encoding="utf-8")


def test_extract_suchergebnis_findet_den_richtigen_json_block():
    """Der Parser sammelt alle <script type="application/json">-Bloecke ein und waehlt den
    einen, dessen JSON ein Dict mit Schluessel 'suchergebnis' ist (Angular-SSR-State)."""
    from pipeline.arbeitsagentur_client import _extract_suchergebnis

    suchergebnis = _extract_suchergebnis(_FIXTURE_HTML)
    assert suchergebnis["maxErgebnisse"] == 36
    assert len(suchergebnis["ergebnisliste"]) == 2


def test_normalize_mapped_beide_records_korrekt():
    """Feld-Mapping gegen die Spec-Tabelle (Stufe D1): company/title/location/published_date."""
    from pipeline.arbeitsagentur_client import _extract_suchergebnis, _normalize

    suchergebnis = _extract_suchergebnis(_FIXTURE_HTML)
    items = suchergebnis["ergebnisliste"]
    records = [_normalize(it) for it in items]

    r0 = records[0]
    assert r0["company"] == "Dr. Ausbüttel GmbH & Co. KG"
    assert r0["title"] == "Leiter Facility Services, Catering & Empfang (m/w/d), Dortmund"
    assert r0["location"] == "44149 Dortmund"
    assert r0["published_date"] == "2026-08-18"
    assert r0["portal"] == "Arbeitsagentur"
    assert r0["raw_json"] is items[0]

    r1 = records[1]
    assert r1["company"] == "VINCI Construction Shared Services GmbH"
    assert r1["title"] == "Leiter MTA (m/w/d) Maschinentechnische Abteilung"
    assert r1["location"] == "37520 Osterode am Harz"


def test_normalize_externeurl_gewinnt_gegen_jobdetail_url():
    """`externeURL` ist gesetzt -> die Original-Anzeige gewinnt, NICHT die BA-Detailseite."""
    from pipeline.arbeitsagentur_client import _extract_suchergebnis, _normalize

    suchergebnis = _extract_suchergebnis(_FIXTURE_HTML)
    item_mit_url = suchergebnis["ergebnisliste"][0]
    assert item_mit_url.get("externeURL")   # Fixture-Annahme, die dieser Test belegen soll

    record = _normalize(item_mit_url)
    assert record["url"] == item_mit_url["externeURL"]
    assert "jobdetail" not in record["url"]


def test_normalize_fallback_auf_jobdetail_url_wenn_externeurl_fehlt():
    """Fehlt `externeURL` (zweiter Fixture-Record), greift der Fallback ueber `referenznummer`
    auf die maschinenlesbare BA-Detailseite -- niemals eine leere/None-URL."""
    from pipeline.arbeitsagentur_client import DETAIL_URL, _extract_suchergebnis, _normalize

    suchergebnis = _extract_suchergebnis(_FIXTURE_HTML)
    item_ohne_url = suchergebnis["ergebnisliste"][1]
    assert not item_ohne_url.get("externeURL")   # Fixture-Annahme, die dieser Test belegen soll

    record = _normalize(item_ohne_url)
    refnr = item_ohne_url["referenznummer"]
    assert record["url"] == DETAIL_URL.format(refnr=refnr)


def test_normalize_published_date_fallback_auf_veroeffentlichungszeitraum():
    """Fehlt `datumErsteVeroeffentlichung` (zweiter Fixture-Record), greift der Fallback auf
    `veroeffentlichungszeitraum.von`."""
    from pipeline.arbeitsagentur_client import _extract_suchergebnis, _normalize

    suchergebnis = _extract_suchergebnis(_FIXTURE_HTML)
    item_ohne_datum = suchergebnis["ergebnisliste"][1]
    assert "datumErsteVeroeffentlichung" not in item_ohne_datum   # Fixture-Annahme

    record = _normalize(item_ohne_datum)
    assert record["published_date"] == item_ohne_datum["veroeffentlichungszeitraum"]["von"]


def test_extract_suchergebnis_ohne_passenden_json_block_liefert_d2_fehler():
    """HTTP 200, aber die Seite wurde umgebaut (kein <script type="application/json"> mit
    Schluessel 'suchergebnis') -> klare Fehlermeldung ueber `_die()`, EXIT != 0, NIEMALS als
    '0 Treffer' durchgereicht (Stufe D2 der Spec)."""
    from pipeline.arbeitsagentur_client import _extract_suchergebnis

    kaputtes_html = (
        "<html><body>"
        '<script type="application/json">{"irgendwas": "anderes"}</script>'
        "</body></html>"
    )
    with pytest.raises(SystemExit) as exc_info:
        _extract_suchergebnis(kaputtes_html)
    assert exc_info.value.code != 0


def test_extract_suchergebnis_fehlermeldung_ist_kein_null_treffer_text(capsys):
    """Regression gegen D2: die Fehlermeldung muss explizit vor '0 Treffer' warnen, nicht
    selbst wie ein normales Nulltreffer-Ergebnis klingen."""
    from pipeline.arbeitsagentur_client import _extract_suchergebnis

    with pytest.raises(SystemExit):
        _extract_suchergebnis("<html><body>kein Script-Block hier</body></html>")

    stderr = capsys.readouterr().err
    assert "suchergebnis" in stderr
    assert "umgebaut" in stderr
    assert "0 Treffer" in stderr   # die Meldung grenzt sich aktiv von "0 Treffer" ab
