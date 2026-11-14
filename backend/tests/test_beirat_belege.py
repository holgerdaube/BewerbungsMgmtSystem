"""P2-97 Stufe B: Belegpflicht im Beirat (Zitate aus dem CV, vom Code geprüft).

Kein KI-Lauf, kein Zugriff auf `data/`. Alle Texte, Firmen und Namen sind erfunden.
App-Importe in den Testfunktionen (conftest-Konvention).
"""
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

DATEN = Path(__file__).resolve().parent / "daten"
STAND = datetime(2026, 9, 1, 9, 0)
BEREICHE = ("rollenfit", "cv_ergebnisse", "unternehmen", "uebertragbarkeit", "karrierewirkung", "interview_chance")

CV_ZITAT = "Senkung der Reklamationsquote von 8 auf 3 Prozent in 14 Monaten"
CV_TEXT = (
    "Leitung Kundenservice, Beispiel GmbH\n"
    f"- {CV_ZITAT}\n"
    "- Aufbau eines Teams von 12 Mitarbeitenden an drei Standorten\n"
)
KONTEXT_MIT_CV = (
    "STELLE: Leiter Service bei Beispiel GmbH (Job 7)\n\n"
    "ANZEIGENTEXT (Original-Snapshot):\nWir suchen Verantwortung fuer den Aufbau von Serviceprozessen.\n\n"
    f"CV-BASIS (DE, outputs/base_de.docx):\n{CV_TEXT}\n\n"
    "COMPANY-FIT (Ampel: gruen):\nSolide."
)


def _alte_debatte() -> SimpleNamespace:
    """Stellen-Check im Format vor P2-97: Abstimmung ohne `belege`."""
    mitglieder = {
        "beirat-vera-brandt": {"id": "beirat-vera-brandt", "anzeige": "Vera Brandt", "farbe": "#123456"},
        "beirat-max-beispiel": {"id": "beirat-max-beispiel", "anzeige": "Max Beispiel", "farbe": "#654321"},
    }
    scores = {b: 7 for b in BEREICHE}
    abstimmung = {
        "beirat-vera-brandt": {"scores": dict(scores), "votum": "Bewerben", "begruendung": "Passt gut zur Rolle."},
        "beirat-max-beispiel": {"scores": {**scores, "cv_ergebnisse": 5}, "votum": "Bedingt", "begruendung": "Zahlen fehlen."},
    }
    return SimpleNamespace(
        id="2026_09_01_0900_aaaaaa", job_id=7, job_titel="Leiter Service", job_firma="Beispiel GmbH",
        beitraege=[{"kopf": "beirat-vera-brandt", "anzeige": "Vera Brandt", "farbe": "#123456",
                    "text": "Die Rolle passt.", "ts": "2026-09-01T09:01:00"}],
        moderationen=[{"text": "Vera Brandt eroeffnet.", "ts": "2026-09-01T09:00:30"}],
        abstimmung=abstimmung,
        entscheidung={"ampel": "Bedingt", "gesamt": 6.8, "bereichs_avg": {b: 6.5 for b in BEREICHE},
                      "stimmen": {"Bewerben": 1, "Bedingt": 1, "Nicht": 0}, "enthaltungen": []},
        check_synthese={"begruendung": "Mehrheit sieht Potenzial.", "bedingt_bedingungen": ["Zahlen klaeren"],
                        "risiko_board": [{"risiko": "Zahlen fehlen", "schwere": "mittel", "status": "ungeklaert",
                                          "naechster_schritt": "Nachfragen"}],
                        "kern_je_kopf": [{"kopf": "beirat-vera-brandt", "kern": "Passt."}],
                        "empfehlung": "Bewerben, Zahlen vorbereiten."},
        company_fit_fehlt=False, synthese_fehler=None, mitglieder=mitglieder)


def _html(monkeypatch, sprache_code, debatte):
    from app import sprache
    import beirat_engine as be

    monkeypatch.setattr(sprache, "aktuell", lambda: sprache_code)
    return be._dashboard_html(debatte, stand=STAND)


def _neue_debatte(monkeypatch, tmp_path, kontext=KONTEXT_MIT_CV):
    import beirat_engine as be

    monkeypatch.setattr(be, "DATEN_DIR", tmp_path / "beirat_test")
    return be.Debatte(thema="Testfrage (erfunden)", kontext=kontext, min_beitraege=2, teilnehmer_ids=None,
                      provider="anthropic", openai_model="gpt-4o-mini", modus="stellen_check")


def _stimme(cv_ergebnisse=8, belege=None, **zusatz):
    s = {"scores": {b: 7 for b in BEREICHE}, "votum": "Bewerben", "begruendung": "Passt."}
    s["scores"]["cv_ergebnisse"] = cv_ergebnisse
    if belege is not None:
        s["belege"] = belege
    s.update(zusatz)
    return s


MITGLIEDER = {"beirat-a": {"anzeige": "Anna Beispiel"}, "beirat-b": {"anzeige": "Bernd Muster"}}


# ── _cv_abschnitt ────────────────────────────────────────────────────────────────────────────

def test_cv_abschnitt_mit_cv():
    import beirat_engine as be

    assert be._cv_abschnitt(KONTEXT_MIT_CV) == CV_TEXT.strip()


def test_cv_abschnitt_ohne_cv_und_ohne_marke():
    import beirat_engine as be

    ohne_cv = "STELLE: X\n\nCV-BASIS: NICHT VERFÜGBAR (outputs/base_de.docx nicht gefunden) — echte Lücke.\n\nCOMPANY-FIT: NICHT VERFÜGBAR"
    assert be._cv_abschnitt(ohne_cv) is None
    assert be._cv_abschnitt("STELLE: X\n\nANZEIGENTEXT: nur Text") is None
    assert be._cv_abschnitt("") is None and be._cv_abschnitt(None) is None


def test_cv_abschnitt_ohne_company_fit_bis_zum_ende():
    import beirat_engine as be

    kontext = "STELLE: X\n\nCV-BASIS (EN, outputs/base_en.docx):\nLed a service team of twelve people.\nSecond line."
    assert be._cv_abschnitt(kontext) == "Led a service team of twelve people.\nSecond line."


# ── _belege_pruefen ──────────────────────────────────────────────────────────────────────────

def test_belege_gefunden_und_nicht_gefunden():
    import beirat_engine as be

    s = _stimme(belege=[{"bereich": "cv_ergebnisse", "zitat": CV_ZITAT},
                        {"bereich": "rollenfit", "zitat": "Verantwortung fuer drei Milliarden Umsatz"}])
    be._belege_pruefen(s, CV_TEXT)
    assert [b["geprueft"] for b in s["belege"]] == [True, False]
    assert s["belege"][0] == {"bereich": "cv_ergebnisse", "zitat": CV_ZITAT, "geprueft": True}


def test_zitat_aus_der_anzeige_gilt_als_nicht_gefunden():
    import beirat_engine as be

    s = _stimme(belege=[{"bereich": "rollenfit", "zitat": "Verantwortung fuer den Aufbau von Serviceprozessen"}])
    be._belege_pruefen(s, be._cv_abschnitt(KONTEXT_MIT_CV))
    assert s["belege"][0]["geprueft"] is False


def test_ohne_cv_ist_geprueft_none():
    import beirat_engine as be

    s = _stimme(belege=[{"bereich": "cv_ergebnisse", "zitat": CV_ZITAT}])
    be._belege_pruefen(s, None)
    assert s["belege"][0]["geprueft"] is None


def test_muell_eintraege_fallen_weg_und_je_bereich_hoechstens_drei():
    import beirat_engine as be

    roh = ["text", None, 5, {}, {"bereich": "cv_ergebnisse"}, {"bereich": "cv_ergebnisse", "zitat": "   "},
           {"bereich": "cv_ergebnisse", "zitat": 7}, {"bereich": "unternehmen", "zitat": CV_ZITAT},
           {"bereich": None, "zitat": CV_ZITAT}, {"zitat": CV_ZITAT}]
    roh += [{"bereich": "cv_ergebnisse", "zitat": f"{CV_ZITAT} {i}", "geprueft": True, "extra": 1} for i in range(5)]
    s = _stimme(belege=roh)
    be._belege_pruefen(s, CV_TEXT)
    assert len(s["belege"]) == 3
    assert all(set(b) == {"bereich", "zitat", "geprueft"} for b in s["belege"])
    assert all(b["geprueft"] is False for b in s["belege"])   # vom Modell gelieferte "geprueft" zaehlt nicht


def test_ohne_belege_schluessel_bleibt_er_weg():
    import beirat_engine as be

    s = _stimme()
    be._belege_pruefen(s, CV_TEXT)
    assert "belege" not in s
    kaputt = _stimme(belege="kein Array")
    be._belege_pruefen(kaputt, CV_TEXT)
    assert "belege" not in kaputt


def test_leere_liste_einer_neuen_antwort_bleibt():
    import beirat_engine as be

    s = _stimme(belege=[])
    be._belege_pruefen(s, CV_TEXT)
    assert s["belege"] == []


def test_stimme_ohne_belege_bleibt_gueltig():
    import beirat_engine as be

    assert be.Debatte._stimme_gueltig(_stimme()) is True
    assert be.Debatte._stimme_gueltig(_stimme(belege=[{"bereich": "x"}])) is True


# ── Abstimmung und Prompts ───────────────────────────────────────────────────────────────────

def test_abstimmung_prompt_verlangt_belege(monkeypatch, tmp_path, _db_ready):
    d = _neue_debatte(monkeypatch, tmp_path)
    m = next(iter(d.mitglieder.values()))
    prompt = d._abstimmung_prompt(m)
    assert '"belege": [{"bereich": "cv_ergebnisse|rollenfit|uebertragbarkeit"' in prompt
    assert "Block CV-BASIS" in prompt and "leere Liste" in prompt
    assert "EXCEPTION" not in prompt


def test_abstimmung_prompt_englisch_laesst_zitate_unuebersetzt(monkeypatch, tmp_path, _db_ready):
    from app import sprache

    d = _neue_debatte(monkeypatch, tmp_path)
    monkeypatch.setattr(sprache, "aktuell", lambda: "en")
    prompt = d._abstimmung_prompt(next(iter(d.mitglieder.values())))
    assert prompt.rstrip().endswith("Never translate them.")


def test_abstimmung_durchfuehren_prueft_zitate_im_code(monkeypatch, tmp_path, _db_ready):
    import asyncio

    d = _neue_debatte(monkeypatch, tmp_path)
    antwort = {"scores": {b: 8 for b in BEREICHE}, "votum": "Bewerben", "begruendung": "Passt.",
               "belege": [{"bereich": "cv_ergebnisse", "zitat": CV_ZITAT},
                          {"bereich": "cv_ergebnisse", "zitat": "Ein frei erfundener Erfolg im Ausland"}]}

    async def fake_turn(provider, openai_model, system_prompt, user_prompt, persona_model, on_delta, task_id=None):
        return json.dumps(antwort), 0.01

    import beirat_engine as be

    monkeypatch.setattr(be, "_turn", fake_turn)
    ergebnis = asyncio.run(d._abstimmung_durchfuehren())
    assert len(ergebnis) == len(d.mitglieder)
    for stimme in ergebnis.values():
        assert [b["geprueft"] for b in stimme["belege"]] == [True, False]
        assert stimme["scores"]["cv_ergebnisse"] == 8     # der Code ändert nie einen Score


def test_synthese_prompt_nennt_zaehlung_nur_bei_stimmen_mit_belege(monkeypatch, tmp_path, _db_ready):
    d = _neue_debatte(monkeypatch, tmp_path)
    kopf_neu, kopf_alt = list(d.mitglieder)[:2]
    d.abstimmung = {k: None for k in d.mitglieder}
    d.abstimmung[kopf_neu] = _stimme(belege=[{"bereich": "cv_ergebnisse", "zitat": CV_ZITAT, "geprueft": True},
                                             {"bereich": "rollenfit", "zitat": "x" * 20, "geprueft": False},
                                             {"bereich": "rollenfit", "zitat": "y" * 20, "geprueft": None}])
    d.abstimmung[kopf_alt] = _stimme()
    d.entscheidung = d._entscheidung_berechnen(d.abstimmung)
    zeilen = d._check_synthese_prompt().split("Alle Voten mit Begründung:\n")[1].split("\n\n")[0].split("\n")
    neu = next(z for z in zeilen if z.startswith(f"- {d.mitglieder[kopf_neu]['anzeige']} "))
    alt = next(z for z in zeilen if z.startswith(f"- {d.mitglieder[kopf_alt]['anzeige']} "))
    assert "1 geprüft gefunden, 1 nicht gefunden" in neu
    assert "CV-Zitate" not in alt


# ── Risiko-Zeile ─────────────────────────────────────────────────────────────────────────────

def _beleg(geprueft, bereich="cv_ergebnisse"):
    return {"bereich": bereich, "zitat": CV_ZITAT, "geprueft": geprueft}


def test_risiko_zeile_bei_8_ohne_geprueften_beleg():
    import beirat_engine as be

    abst = {"beirat-a": _stimme(8, [_beleg(False)]), "beirat-b": _stimme(8, [_beleg(True)])}
    zeile = be._beleg_risiko_zeile(abst, MITGLIEDER, CV_TEXT)
    assert zeile == {"risiko": "CV-Ergebnisse ohne geprüften Beleg bewertet: Anna Beispiel",
                     "schwere": "mittel", "status": "ungeklaert",
                     "naechster_schritt": "Beleg im CV suchen oder den Wert hinterfragen"}


def test_risiko_zeile_nennt_alle_koepfe():
    import beirat_engine as be

    abst = {"beirat-a": _stimme(7, []), "beirat-b": _stimme(9, [_beleg(None)])}
    assert be._beleg_risiko_zeile(abst, MITGLIEDER, CV_TEXT)["risiko"].endswith("Anna Beispiel, Bernd Muster")


@pytest.mark.parametrize("abst, cv", [
    ({"beirat-a": _stimme(8, [_beleg(True)])}, CV_TEXT),                        # Beleg geprüft
    ({"beirat-a": _stimme(6, [])}, CV_TEXT),                                    # Wert unter 7
    ({"beirat-a": _stimme(8)}, CV_TEXT),                                        # Stimme im alten Format
    ({"beirat-a": _stimme(8, [])}, None),                                       # kein CV
    ({"beirat-a": None}, CV_TEXT),                                              # Enthaltung
    (None, CV_TEXT),
])
def test_risiko_zeile_fehlt(abst, cv):
    import beirat_engine as be

    assert be._beleg_risiko_zeile(abst, MITGLIEDER, cv) is None


def test_beleg_aus_anderem_bereich_zaehlt_nicht_fuer_cv_ergebnisse():
    import beirat_engine as be

    abst = {"beirat-a": _stimme(8, [_beleg(True, "rollenfit")])}
    assert be._beleg_risiko_zeile(abst, MITGLIEDER, CV_TEXT) is not None


def test_risiko_zeile_wird_ans_board_gehaengt_und_aendert_keinen_score():
    import beirat_engine as be

    abst = {"beirat-a": _stimme(8, [_beleg(False)])}
    vorher = json.dumps(abst, sort_keys=True)
    parsed = {"risiko_board": [{"risiko": "Alt", "schwere": "hoch", "status": "geklaert", "naechster_schritt": "-"}]}
    be._beleg_risiko_anhaengen(parsed, abst, MITGLIEDER, CV_TEXT)
    assert [z["risiko"] for z in parsed["risiko_board"]][0] == "Alt" and len(parsed["risiko_board"]) == 2
    assert json.dumps(abst, sort_keys=True) == vorher
    ohne_board = {"begruendung": "x"}
    be._beleg_risiko_anhaengen(ohne_board, abst, MITGLIEDER, CV_TEXT)
    assert len(ohne_board["risiko_board"]) == 1


def test_risiko_zeile_rendert_im_dashboard_mit_den_werten_des_boards():
    import beirat_engine as be

    abst = {"beirat-a": _stimme(8, [_beleg(False)])}
    zeile = be._beleg_risiko_zeile(abst, MITGLIEDER, CV_TEXT)
    html = be._risiko_board_html([zeile])
    assert "schwere-mittel" in html and "🟡" in html and "❓" in html and "Anna Beispiel" in html


def test_risiko_zeile_englisch(monkeypatch):
    from app import sprache
    import beirat_engine as be

    monkeypatch.setattr(sprache, "aktuell", lambda: "en")
    zeile = be._beleg_risiko_zeile({"beirat-a": _stimme(8, [])}, MITGLIEDER, CV_TEXT)
    assert zeile["risiko"] == "CV results rated without a verified quotation: Anna Beispiel"
    assert zeile["schwere"] == "mittel" and zeile["status"] == "ungeklaert"


# ── Dashboard ────────────────────────────────────────────────────────────────────────────────

def _html(monkeypatch, sprache_code, debatte):
    from app import sprache
    import beirat_engine as be

    monkeypatch.setattr(sprache, "aktuell", lambda: sprache_code)
    return be._dashboard_html(debatte, stand=STAND)


@pytest.mark.parametrize("code", ["de", "en"])
def test_alter_bericht_ohne_belege_ist_byte_gleich(monkeypatch, code):
    golden = (DATEN / f"beirat_belege_golden_{code}.html").read_text(encoding="utf-8")
    html = _html(monkeypatch, code, _alte_debatte())
    assert html == golden
    assert "Belege je Kopf" not in html and "Evidence per board member" not in html


def test_dashboard_zeigt_belege_mit_kennzeichen(monkeypatch):
    d = _alte_debatte()
    d.abstimmung["beirat-vera-brandt"]["belege"] = [
        {"bereich": "cv_ergebnisse", "zitat": CV_ZITAT, "geprueft": True},
        {"bereich": "rollenfit", "zitat": "Erfunden <b>fett</b> & frei", "geprueft": False},
        {"bereich": "uebertragbarkeit", "zitat": "Nicht pruefbare Aussage hier", "geprueft": None}]
    d.abstimmung["beirat-max-beispiel"]["belege"] = []
    html = _html(monkeypatch, "de", d)
    assert "Belege je Kopf" in html
    assert html.index("Belege je Kopf") > html.index("Abstimmungs-Matrix") and html.index("Belege je Kopf") < html.index("5. Debatten-Verlauf")
    assert f"„{CV_ZITAT}“" in html
    assert "Erfunden &lt;b&gt;fett&lt;/b&gt; &amp; frei" in html and "<b>fett</b>" not in html
    assert html.count("im CV gefunden") == 2 and "nicht im CV gefunden" in html and "nicht prüfbar" in html
    assert "(kein Zitat genannt)" in html
    en = _html(monkeypatch, "en", d)
    assert "Evidence per board member" in en and "not found in the CV" in en and "cannot be checked" in en
    assert f"“{CV_ZITAT}”" in en       # das Zitat bleibt, wie es ist


# ── Übersetzung ──────────────────────────────────────────────────────────────────────────────

def test_texte_sammeln_nimmt_keine_zitate_mit():
    from pipeline.beirat_uebersetzen import texte_sammeln

    d = {"thema": "Titel", "beitraege": [], "moderationen": [], "synthese": None, "check_synthese": {"begruendung": "B"},
         "abstimmung": {"beirat-a": _stimme(8, [_beleg(True), _beleg(False, "rollenfit")], begruendung="Grund"), "beirat-b": None}}
    texte = [t for t, _ in texte_sammeln(d)]
    assert "Grund" in texte
    assert not any(CV_ZITAT in t for t in texte)
    assert not any(t in ("cv_ergebnisse", "rollenfit") for t in texte)

