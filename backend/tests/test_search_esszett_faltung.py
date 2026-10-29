"""Tests für Phase 67B (P2-11 aus dem Code-Review): Volltextsuche faltet „ß" nicht zu „ss".

`search_index.py` läuft mit FTS5 `tokenize='unicode61 remove_diacritics 2'` — das faltet
Kombinationszeichen (ä/ö/ü → a/o/u), aber ß ist ein EIGENSTÄNDIGES Unicode-Zeichen ohne
Grundbuchstabe+Kombinationszeichen-Zerlegung und bleibt unangetastet. „Großkunden" (Original) und
„Grosskunden" (Nutzereingabe) landeten deshalb als zwei verschiedene Tokens im Index — eine Suche
nach dem einen fand das andere nicht, in KEINER Richtung. Fix: dieselbe ß→ss-Abbildung wie
`naming.py::_TRANSLIT` beim Indexieren (`_insert`) UND beim Suchen (`query`) anwenden.

Isolation wie überall in dieser Suite: kein app.*/pipeline.*-Import auf Modulebene (conftest.py).
Die tmp-DB akkumuliert testübergreifend — deshalb wird hier NIE ein Gesamt-Trefferzahl geprüft,
sondern immer nur "ist unser frisch angelegter Job unter den Treffern".
"""


def test_fold_esszett_ersetzt_kleines_und_grosses_eszett():
    from pipeline.search_index import _fold_esszett

    assert _fold_esszett("Großkunden") == "Grosskunden"
    assert _fold_esszett("STRAẞE") == "STRASSE"
    assert _fold_esszett("ohne Umlaut oder Eszett") == "ohne Umlaut oder Eszett"
    assert _fold_esszett("") == ""


def test_fold_esszett_ruehrt_umlaute_nicht_an():
    """P2-11 ist AUSSCHLIESSLICH ß->ss — die volle Umlaut-Transliteration (ä/ö/ü) aus
    naming._TRANSLIT ist bewusst NICHT Teil dieses Fixes (anderer Befund, andere Phase)."""
    from pipeline.search_index import _fold_esszett

    assert _fold_esszett("über später Größe") == "über später Grösse"


def test_suche_ohne_eszett_findet_dokument_mit_echtem_eszett(session, seed):
    """Kernszenario aus dem Befund: Eingabe 'Grosskunden' (ASCII-Ersatz) muss ein Dokument
    finden, dessen Originaltext 'Großkunden' (echtes ß) enthält. Ohne den Fix bleibt das
    Ergebnis für diese Query leer, weil der Index das literale 'ß' unverändert speichert."""
    from pipeline.search_index import query, rebuild

    job = seed["jobs"][0]
    job.raw_json = '{"beschreibung": "Wir betreuen ausschließlich Großkunden in der DACH-Region."}'
    session.add(job)
    session.commit()

    info = rebuild()
    assert info["dokumente"] > 0

    ergebnis = query("Grosskunden")
    treffer_ids = {e["job_id"] for e in ergebnis["ergebnisse"]}
    assert job.id in treffer_ids, (
        "Suche nach 'Grosskunden' (ss) muss das mit 'Großkunden' (ß) indizierte Dokument finden "
        f"(gefundene Job-IDs: {treffer_ids})"
    )


def test_suche_mit_echtem_eszett_findet_dokument_das_nur_ss_enthaelt(session, seed):
    """Rückrichtung (im Befund ausdrücklich verlangt): Eingabe 'Großkunden' (mit echtem ß) muss
    auch ein Dokument finden, das selbst nur 'Grosskunden' (ASCII ss, z. B. Schweizer
    Schreibweise) enthält — sonst hilft die Faltung nur in eine Richtung."""
    from pipeline.search_index import query, rebuild

    job = seed["jobs"][1]
    job.raw_json = '{"beschreibung": "Fokus auf Grosskunden im Schweizer Markt."}'
    session.add(job)
    session.commit()

    rebuild()

    ergebnis = query("Großkunden")
    treffer_ids = {e["job_id"] for e in ergebnis["ergebnisse"]}
    assert job.id in treffer_ids, (
        "Suche nach 'Großkunden' (ß) muss das nur mit 'Grosskunden' (ss) indizierte Dokument "
        f"finden (gefundene Job-IDs: {treffer_ids})"
    )


def test_insert_ist_einzige_schreibstelle_und_faltet_immer():
    """Regressionsschutz gegen 'ein zehnter Aufrufer vergisst die Faltung': rebuild() darf
    Dokument-Zeilen (Tabelle `suchindex`, nicht `suchindex_meta`) ausschließlich über _insert()
    schreiben — sonst könnte ein künftiger Aufrufer die ß-Faltung umgehen, indem er wieder direkt
    per exec_driver_sql in `suchindex` schreibt."""
    import inspect

    from pipeline import search_index

    quelltext = inspect.getsource(search_index.rebuild)
    assert "INSERT INTO suchindex (" not in quelltext, (
        "rebuild() enthält wieder ein direktes 'INSERT INTO suchindex (' statt über _insert() "
        "zu gehen — die ß-Faltung würde dort nicht mehr greifen"
    )
    assert quelltext.count("_insert(conn,") == 9, (
        "rebuild() sollte alle neun Dokument-Quellen (stelle, stellenbeschreibung, company-fit, "
        "transkript, debrief, briefing, match, ats, verlauf) über _insert() schreiben"
    )
