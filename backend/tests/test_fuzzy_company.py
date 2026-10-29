"""Kontrakt-Tests fuer pipeline/gmail_ingest.py::_fuzzy_find_company (Phase 57 Stufe E1.4).

Bestand exakt nach Spec (synthetisch, T3 -- erfundene Namen nach dokumentierten
Empirie-Faellen aus tasks/todo.md, keine Kontakt-/CV-Daten):
    ["nordstern Management Consultants GmbH", "Zinkwire Software", "Beispielwerk Sued GmbH"]

Der Bestand wird EINMAL pro Modul angelegt (`scope="module"`) -- nicht ueber die
funktionsweite `session`-Fixture aus conftest.py, sonst wuerden mehrere Testfunktionen dieselben
Firmennamen mehrfach einfuegen und sich gegenseitig in eine kuenstliche Mehrdeutigkeit treiben.
Empirisch verifiziert (venv-REPL) VOR dem Schreiben dieser Tests -- s. Abschlussbericht.
"""
import pytest


@pytest.fixture(scope="module")
def firmen_bestand(_db_ready):
    """Legt den Spec-Bestand EINMAL fuer alle Tests dieser Datei an (module-scoped, kann daher
    nicht von der funktionsweiten `session`-Fixture abhaengen -- eigene Session gegen denselben
    Engine, s. app.db.engine)."""
    from sqlmodel import Session
    from app.db import engine
    from app.models import Company

    with Session(engine) as s:
        firmen = [
            Company(name="nordstern Management Consultants GmbH"),
            Company(name="Zinkwire Software"),
            Company(name="Beispielwerk Sued GmbH"),
        ]
        for f in firmen:
            s.add(f)
        s.commit()
    return {"nordstern": "nordstern Management Consultants GmbH",
            "zinkwire": "Zinkwire Software", "beispielwerk": "Beispielwerk Sued GmbH"}


def test_nordstern_findet_eindeutigen_treffer(firmen_bestand, session):
    from pipeline.gmail_ingest import _fuzzy_find_company

    treffer = _fuzzy_find_company(session, "nordstern")
    assert treffer is not None
    assert treffer.name == firmen_bestand["nordstern"]


def test_wire_findet_zinkwire_nicht(firmen_bestand, session):
    """Empirische Gegenprobe aus todo.md (23.07.2026): 'Wire' darf NIEMALS 'Zinkwire' treffen --
    Wortgrenzen-Matching, kein roher Substring ('wire' in 'zinkwire' waere True, ist hier aber
    IRRELEVANT, weil beides je EIN Wort-Token ist und Token-Gleichheit geprueft wird)."""
    from pipeline.gmail_ingest import _fuzzy_find_company

    assert _fuzzy_find_company(session, "Wire") is None


def test_mehrdeutiger_name_liefert_none(firmen_bestand, session):
    """'GmbH' passt als Wort-Teilfolge auf ZWEI Firmen im Bestand (nordstern-Firma UND
    Beispielwerk) -- Ein-Kandidat-oder-keiner-Regel liefert bei mehreren Treffern None,
    nie einen geratenen Treffer."""
    from pipeline.gmail_ingest import _fuzzy_find_company

    assert _fuzzy_find_company(session, "GmbH") is None


def test_exakter_einzelworttreffer_beispielwerk(firmen_bestand, session):
    from pipeline.gmail_ingest import _fuzzy_find_company

    treffer = _fuzzy_find_company(session, "Beispielwerk")
    assert treffer is not None
    assert treffer.name == firmen_bestand["beispielwerk"]


def test_unbekannter_name_liefert_none(firmen_bestand, session):
    from pipeline.gmail_ingest import _fuzzy_find_company

    assert _fuzzy_find_company(session, "Nichtvorhanden") is None


def test_zu_kurzer_name_liefert_none(firmen_bestand, session):
    """Laengen-Gate: ein einzelnes Wort unter 3 Zeichen wird gar nicht erst verglichen."""
    from pipeline.gmail_ingest import _fuzzy_find_company

    assert _fuzzy_find_company(session, "ab") is None
    assert _fuzzy_find_company(session, "") is None
