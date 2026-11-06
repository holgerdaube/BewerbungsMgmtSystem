"""Alte Beirats-Debatten auf Englisch (P2-96): Originale bleiben, die Anzeige wählt die Fassung.

Kein echter KI-Lauf, kein Zugriff auf `data/beirat`: `DATEN_DIR` zeigt in ein tmp-Verzeichnis.
Kein app.*-Import auf Modulebene (conftest.py-Konvention).
"""
import json

import pytest

TITEL = "Stellen-Check: Soll sich Max Mustermann auf „Leiter Service“ bei Beispiel GmbH bewerben? (Job 7)"


def _debatte(debatte_id="2026_09_01_0900_aaaaaa", **zusatz):
    d = {
        "id": debatte_id, "thema": TITEL, "kontext": "Rohmaterial der Anzeige", "status": "fertig", "gestartet": "2026-09-01T09:00:00",
        "modus": "stellen_check", "job_id": 7, "min_beitraege": 8,
        "teilnehmer": [{"id": "beirat-vera-brandt", "anzeige": "Vera Brandt", "farbe": "#123456"}],
        "beitraege": [{"kopf": "beirat-vera-brandt", "anzeige": "Vera Brandt", "farbe": "#123456", "frage": "Passt die Rolle?",
                       "text": "Die Rolle passt nicht.", "ts": "2026-09-01T09:01:00"}],
        "moderationen": [{"text": "Vera Brandt eröffnet.", "ts": "2026-09-01T09:00:30"}],
        "synthese": None,
        "abstimmung": {"beirat-vera-brandt": {"scores": {"rollenfit": 3}, "votum": "Nicht", "begruendung": "Zu weit weg."}},
        "entscheidung": {"ampel": "Nicht", "gesamt": 4.4, "bereichs_avg": {"rollenfit": 3.0, "cv_ergebnisse": 3.0, "unternehmen": 3.0,
                                                                           "uebertragbarkeit": 3.0, "karrierewirkung": 3.0,
                                                                           "interview_chance": 3.0},
                         "stimmen": {"Bewerben": 0, "Bedingt": 0, "Nicht": 1}, "enthaltungen": []},
        "check_synthese": {"begruendung": "Passt nicht.", "bedingt_bedingungen": [],
                           "risiko_board": [{"risiko": "Kein Fit", "schwere": "hoch", "status": "geklaert", "naechster_schritt": "Absagen"}],
                           "kern_je_kopf": [{"kopf": "beirat-vera-brandt", "kern": "Nein."}], "empfehlung": "Nicht bewerben."},
        "dashboard_pfad": "data/beirat/20260901_Beirat_Beispiel.html", "fehler": None,
    }
    d.update(zusatz)
    return d


@pytest.fixture()
def ordner(tmp_path, monkeypatch):
    import beirat_engine as be

    monkeypatch.setattr(be, "DATEN_DIR", tmp_path)
    return tmp_path


def _speichern(ordner, d):
    (ordner / f"{d['id']}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    (ordner / "20260901_Beirat_Beispiel_rohdaten.json").write_text(
        json.dumps({"job_titel": "Leiter Service", "job_firma": "Beispiel GmbH"}), encoding="utf-8")


def _englisch(monkeypatch):
    from app import sprache

    monkeypatch.setattr(sprache, "aktuell", lambda: "en")


def _falsche_ki(monkeypatch, antwort=None):
    from pipeline import beirat_uebersetzen as bu

    aufrufe = []

    def ki(prompt):
        texte = json.loads(prompt[prompt.rindex("\n\n") + 2:])
        aufrufe.append(texte)
        return json.dumps([f"EN: the text {i}" for i, _ in enumerate(texte)]) if antwort is None else antwort(texte), 0.1

    monkeypatch.setattr(bu, "_ki_aufruf", ki)
    return aufrufe


def test_gesammelt_wird_der_text_nicht_feste_werte_und_rohmaterial():
    from pipeline.beirat_uebersetzen import texte_sammeln

    texte = [t for t, _ in texte_sammeln(_debatte())]
    assert TITEL in texte and "Die Rolle passt nicht." in texte and "Zu weit weg." in texte and "Kein Fit" in texte
    for fest in ("hoch", "geklaert", "Nicht", "beirat-vera-brandt", "Vera Brandt", "Rohmaterial der Anzeige", "fertig"):
        assert fest not in texte


def test_uebersetzung_laesst_original_und_feste_werte_stehen(ordner, monkeypatch):
    from pipeline import beirat_uebersetzen as bu

    d = _debatte()
    _speichern(ordner, d)
    vorher = (ordner / f"{d['id']}.json").read_bytes()
    _falsche_ki(monkeypatch)
    _englisch(monkeypatch)

    bu.debatte_uebersetzen(ordner / f"{d['id']}.json", ordner)

    assert (ordner / f"{d['id']}.json").read_bytes() == vorher
    en = json.loads((ordner / "en" / f"{d['id']}.json").read_text(encoding="utf-8"))
    assert en["thema"].startswith("EN:") and en["beitraege"][0]["text"].startswith("EN:")
    assert en["abstimmung"]["beirat-vera-brandt"]["votum"] == "Nicht"
    assert en["check_synthese"]["risiko_board"][0]["schwere"] == "hoch"
    assert en["entscheidung"] == d["entscheidung"] and en["kontext"] == d["kontext"]
    bericht = (ordner / "en" / "20260901_Beirat_Beispiel.html").read_text(encoding="utf-8")
    assert "EN: the text" in bericht and "2026-09-01" in bericht and "Advisory Board" in bericht


def test_enthaltung_wird_uebersetzt_ohne_absturz_und_bleibt_enthaltung(ordner, monkeypatch):
    from pipeline import beirat_uebersetzen as bu

    d = _debatte()
    d["teilnehmer"].append({"id": "beirat-mateo-vidal", "anzeige": "Mateo Vidal", "farbe": "#654321"})
    d["abstimmung"]["beirat-mateo-vidal"] = None
    d["entscheidung"]["enthaltungen"] = ["beirat-mateo-vidal"]
    _speichern(ordner, d)
    _falsche_ki(monkeypatch)
    _englisch(monkeypatch)

    bu.debatte_uebersetzen(ordner / f"{d['id']}.json", ordner)

    en = json.loads((ordner / "en" / f"{d['id']}.json").read_text(encoding="utf-8"))
    assert en["abstimmung"]["beirat-mateo-vidal"] is None
    assert en["abstimmung"]["beirat-vera-brandt"]["begruendung"].startswith("EN:")
    assert (ordner / "en" / "20260901_Beirat_Beispiel.html").is_file()


@pytest.mark.parametrize("antwort, meldung", [
    ('["nur einer"]', "Texte statt"),
    ("keine Liste", "Keine JSON-Liste"),
    ('["", "x"]', "Leerer Text"),
    ('["Die Rolle ist nicht passend und das wird auch so sein", "Sie ist auf der Stelle nicht mit dabei und die"]', "deutsch"),
])
def test_unbrauchbare_antwort_wird_abgelehnt(antwort, meldung):
    from pipeline.beirat_uebersetzen import UebersetzungFehler, antwort_pruefen

    with pytest.raises(UebersetzungFehler, match=meldung):
        antwort_pruefen(antwort, ["a", "b"])


def test_fehler_wird_einmal_halbiert_wiederholt(monkeypatch):
    from pipeline import beirat_uebersetzen as bu

    aufrufe = []

    def ki(texte):
        aufrufe.append(len(texte))
        if len(texte) == 4:
            return "kaputt"
        return json.dumps(["the text"] * len(texte))

    _falsche_ki(monkeypatch, ki)
    ergebnis, kosten = bu._uebersetzen(["a", "b", "c", "d"])
    assert len(ergebnis) == 4 and aufrufe == [4, 2, 2] and kosten == pytest.approx(0.3)


def test_fertiges_wird_uebersprungen_und_kaputte_debatte_stoppt_den_lauf_nicht(ordner, monkeypatch):
    from pipeline import beirat_uebersetzen as bu

    for i in ("aaaaaa", "bbbbbb", "cccccc"):
        _speichern(ordner, _debatte(f"2026_09_01_0900_{i}"))
    (ordner / "en").mkdir()
    (ordner / "en" / "2026_09_01_0900_aaaaaa.json").write_text("{}", encoding="utf-8")
    assert {p.stem[-6:] for p in bu.offene_debatten(ordner)} == {"bbbbbb", "cccccc"}

    _englisch(monkeypatch)
    _falsche_ki(monkeypatch)
    echt = bu.debatte_uebersetzen

    def teils_kaputt(pfad, o):
        if "bbbbbb" in pfad.name:
            raise bu.UebersetzungFehler("kaputt")
        return echt(pfad, o)

    monkeypatch.setattr(bu, "debatte_uebersetzen", teils_kaputt)
    stand = bu.lauf(bu.offene_debatten(ordner), ordner, 1, None, melden=lambda _: None)
    assert (stand["fertig"], stand["fehler"]) == (1, 1)
    assert {p.stem[-6:] for p in bu.offene_debatten(ordner)} == {"bbbbbb"}


def test_abo_limit_und_kostengrenze_stoppen_den_lauf(ordner, monkeypatch):
    from pipeline import beirat_uebersetzen as bu

    pfade = []
    for i in ("aaaaaa", "bbbbbb"):
        d = _debatte(f"2026_09_01_0900_{i}")
        _speichern(ordner, d)
        pfade.append(ordner / f"{d['id']}.json")

    def am_limit(_pfad, _ordner):
        raise bu.AboLimit("usage limit")

    monkeypatch.setattr(bu, "debatte_uebersetzen", am_limit)
    stand = bu.lauf(pfade, ordner, 1, None, melden=lambda _: None)
    assert stand["gestoppt"].startswith("Abo-Limit") and stand["fertig"] == 0

    monkeypatch.setattr(bu, "debatte_uebersetzen", lambda _p, _o: 5.0)
    stand = bu.lauf(pfade, ordner, 1, 4.0, melden=lambda _: None)
    assert stand["fertig"] == 1 and "Kostengrenze" in stand["gestoppt"]


def test_deutsch_sieht_nur_das_original(ordner, monkeypatch):
    import beirat_engine as be
    from app import sprache

    monkeypatch.setattr(sprache, "aktuell", lambda: "de")
    d = _debatte()
    _speichern(ordner, d)
    (ordner / "en").mkdir()
    (ordner / "en" / f"{d['id']}.json").write_text(json.dumps({**d, "thema": "Job check english"}), encoding="utf-8")
    assert be.debatten_liste()[0]["thema"] == TITEL
    assert be.debatte_lesen(d["id"]) == d


def test_englisch_zeigt_die_fassung_und_sonst_den_uebersetzten_titel(ordner, monkeypatch):
    import beirat_engine as be

    _englisch(monkeypatch)
    d = _debatte()
    _speichern(ordner, d)
    erwartet = "Job check: Should Max Mustermann apply for “Leiter Service” at Beispiel GmbH? (Job 7)"
    assert be.debatten_liste()[0]["thema"] == erwartet
    gelesen = be.debatte_lesen(d["id"])
    assert gelesen["thema"] == erwartet and gelesen["beitraege"][0]["text"] == "Die Rolle passt nicht."

    (ordner / "en").mkdir()
    (ordner / "en" / f"{d['id']}.json").write_text(json.dumps({**d, "thema": "Fertig übersetzt"}), encoding="utf-8")
    assert be.debatten_liste()[0]["thema"] == "Fertig übersetzt"
    assert be.debatte_lesen(d["id"])["thema"] == "Fertig übersetzt"


def test_freier_titel_bleibt_unveraendert(ordner, monkeypatch):
    import beirat_engine as be

    _englisch(monkeypatch)
    assert be._thema_auf_englisch("Soll ich wechseln?") == "Soll ich wechseln?"


def test_aufraeumen_meldet_die_englischen_dateien_nicht_als_verwaist():
    from pipeline import cleanup

    assert "data/beirat/en" in cleanup._ORPHAN_UNTERORDNER_AUSNAHMEN


def test_aeltere_windows_datei_wird_weiter_gelesen(ordner, monkeypatch):
    """Debatten wurden ohne feste Kodierung geschrieben, unter Windows also als cp1252. Jetzt immer UTF-8, die alten bleiben lesbar."""
    import beirat_engine as be
    from app import sprache

    monkeypatch.setattr(sprache, "aktuell", lambda: "de")
    d = _debatte()
    (ordner / f"{d['id']}.json").write_bytes(json.dumps(d, ensure_ascii=False).encode("cp1252"))
    assert be.debatten_liste()[0]["thema"] == TITEL
    assert be.debatte_lesen(d["id"])["thema"] == TITEL
    (ordner / "neu.json").write_text(json.dumps(_debatte("neu"), ensure_ascii=False), encoding="utf-8")
    assert be.debatte_lesen("neu")["thema"] == TITEL
