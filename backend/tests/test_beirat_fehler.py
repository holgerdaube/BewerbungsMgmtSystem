"""Phase 62B (P1-4 + P2-5) — Beirat erkennt API-Fehler statt sie als Beitrag zu speichern, plus
Retry ("1 Versuch + 1 Retry", Muster aus _abstimmung_durchfuehren/Stellen-Check-Synthese) fuer
Dispatch- und Persona-Turn. Regressionstests fuer die Befunde aus
tasks/code_review_2026-07-25.md:

- P1-4: `_turn_anthropic` pruefte weder `is_error` noch `api_error_status` -- eine echte API-
  Fehlermeldung (z. B. Rate-/Session-Limit) wurde als Wortlaut eines Beirats-Kopfs gespeichert
  und floss ueber das Transkript in alle Folge-Prompts (real passiert, s.
  data/beirat/2026_07_23_2126_0e843f.json -- der gespeicherte Beitrag der damaligen
  Vorsitzenden ist reiner Fehlertext; Persona-Namen seit Phase 71C fiktiv, Datei unveraendert).
- P2-5: Dispatch-Turn ohne Retry -- ein einzelner transienter Fehler verwarf die gesamte
  bereits bezahlte Debatte (3 reale Faelle).

Wie in conftest.py beschrieben: KEINE app.*/pipeline.*-Importe auf Modulebene, nur in
Testfunktionen (gilt hier auch fuer `beirat_engine` selbst). Rein synthetische Daten.

B1 (kein echter Beirats-Lauf, KRITISCH): jeder Engine-Test unten ersetzt `beirat_engine._turn`
durch eine Fake-Funktion -- kein Test startet einen Subprozess (`claude -p`) oder ruft eine
echte API. `Debatte` wird bewusst DIREKT konstruiert (nicht ueber `debatte_starten()`), wodurch
`task_id` auf dem Default `None` bleibt: `_task_abschliessen()`/`_log_zeile()` werden dadurch
zu No-Ops (kein AgentTask-Schreiben, kein Log-Schreiben), und es entsteht kein Registry-
Eintrag. `beirat_engine.DATEN_DIR` wird zusaetzlich auf ein pytest-tmp-Verzeichnis umgebogen,
damit `Debatte._speichern()` (in `laufen()` mehrfach aufgerufen) NIEMALS in das echte
`data/beirat/` schreibt -- die Vorgabe "Dateien unter data/beirat/ NUR LESEN, nie schreiben"
gilt auch fuer diese Tests.
"""
import asyncio
import json


# ── Pure Hilfsfunktion: _result_event_auswerten (testbare Naht, B4) ─────────────────────────

def test_result_event_mit_is_error_meldet_fehler_ohne_text():
    """Kernbefund P1-4: is_error/api_error_status muessen erkannt werden. `subtype` bleibt bei
    einem echten API-Fehler oft "success" (real beobachtet in data/agent_logs/task_342.jsonl:
    is_error=True, api_error_status=429, subtype="success") -- die Hilfsfunktion darf sich davon
    NICHT taeuschen lassen, nur `is_error` zaehlt. Bei einem Fehler ist `text` bewusst leer."""
    from beirat_engine import _result_event_auswerten

    event = {
        "type": "result", "subtype": "success", "is_error": True, "api_error_status": 429,
        "result": "Testfehler: Rate-Limit erreicht (synthetisch)", "total_cost_usd": 0.0,
    }
    text, kosten, fehler = _result_event_auswerten(event)
    assert text == ""
    assert kosten == 0.0
    assert fehler is not None
    assert "429" in fehler
    assert "Rate-Limit" in fehler


def test_result_event_normal_liefert_text_und_kosten_wie_bisher():
    """Gegenprobe: ein normales result-Event (kein Fehler) liefert weiterhin Text+Kosten exakt
    wie vor der Aenderung -- keine Verhaltensaenderung im Erfolgsfall (Invariante B5)."""
    from beirat_engine import _result_event_auswerten

    event = {
        "type": "result", "subtype": "success", "is_error": False, "api_error_status": None,
        "result": "Position: Das ist ein synthetischer Testbeitrag.", "total_cost_usd": 0.0234,
    }
    text, kosten, fehler = _result_event_auswerten(event)
    assert text == "Position: Das ist ein synthetischer Testbeitrag."
    assert kosten == 0.0234
    assert fehler is None


def test_result_event_ohne_is_error_feld_gilt_als_erfolg():
    """Defensiv: fehlen is_error/api_error_status komplett (aeltere/minimale Event-Form), gilt
    das Event als Erfolg -- `.get(...)` liefert None, das ist falsy."""
    from beirat_engine import _result_event_auswerten

    event = {"type": "result", "result": "Noch ein synthetischer Text.", "total_cost_usd": 0.01}
    text, kosten, fehler = _result_event_auswerten(event)
    assert text == "Noch ein synthetischer Text."
    assert kosten == 0.01
    assert fehler is None


# ── Engine-Retry: Dispatch- und Persona-Turn (P2-5) ─────────────────────────────────────────

def _ist_dispatch(user_prompt: str) -> bool:
    return user_prompt.startswith("DEBATTEN-STEUERUNG.")


def _ist_synthese(user_prompt: str) -> bool:
    return user_prompt.startswith("Die Debatte ist beendet")


def _neue_test_debatte(monkeypatch, tmp_path, *, min_beitraege=2):
    """Gemeinsamer Aufbau: DATEN_DIR auf ein tmp-Verzeichnis umbiegen (B2 -- data/beirat/ bleibt
    unangetastet), dann eine minimale Debatte im Modus 'frei' anlegen (kein Stellen-Check --
    vermeidet die 7-koepfige Abstimmung/Check-Synthese, die fuer diese Tests irrelevant waere).
    `lade_mitglieder()`/`modell_fuer_beirat()` laufen dabei ECHT (lesen nur lokale Personas-
    Markdown-Dateien bzw. die tmp-DB) -- das kostet nichts und startet keinen Subprozess,
    B1 bleibt gewahrt. Default `min_beitraege=2`: der Konstruktor klemmt intern IMMER auf
    `max(2, ...)` (beirat_engine.py, `Debatte.__init__`) -- 2 ist hier bewusst genannt, nicht 1,
    damit kein Leser der Tests ueber eine stille Klemmung stolpert."""
    import beirat_engine

    monkeypatch.setattr(beirat_engine, "DATEN_DIR", tmp_path / "beirat_test")
    d = beirat_engine.Debatte(
        thema="Testfrage fuer den Beirat (synthetisch)", kontext="", min_beitraege=min_beitraege,
        teilnehmer_ids=None, provider="anthropic", openai_model="gpt-4o-mini", modus="frei",
    )
    assert d.min_beitraege == min_beitraege   # Sicherheitsnetz gegen die max(2, ...)-Klemmung
    assert d.task_id is None   # Sicherheitsnetz: kein AgentTask/Log-Pfad beruehrt (s. Docstring)
    return d, beirat_engine


def test_persona_turn_erfolg_nach_einem_fehlgeschlagenen_versuch(monkeypatch, tmp_path, _db_ready):
    """P1-4+P2-5 zusammen: der erste Persona-Versuch wirft (simulierter API-Fehler), der Retry
    liefert einen echten Beitrag. Beleg: NICHT die Fehlermeldung landet als Beitragstext,
    sondern der Kopf wird beim zweiten Versuch normal gespeichert -- Erfolgsfall des Retries."""
    d, be = _neue_test_debatte(monkeypatch, tmp_path)   # min_beitraege=2 (Default, s. Docstring dort)
    persona_versuche = {"n": 0}

    async def fake_turn(provider, openai_model, system_prompt, user_prompt, persona_model,
                        on_delta, task_id=None):
        if _ist_dispatch(user_prompt):
            if len(d.beitraege) >= d.min_beitraege:
                return json.dumps({"aktion": "abschluss", "begruendung": "genug fuer den Test"}), 0.01
            return json.dumps({"aktion": "dispatch", "kopf": "beirat-vera-brandt",
                               "frage": "Testfrage?"}), 0.01
        if _ist_synthese(user_prompt):
            return "Synthesetext (synthetisch).", 0.01
        # Persona-Turn: NUR der aller-erste Versuch (fuer den 1. der 2 Pflicht-Beitraege) wirft,
        # jeder weitere Aufruf liefert direkt (Retry-Erfolg + der 2. Beitrag ohne Stoerung).
        persona_versuche["n"] += 1
        if persona_versuche["n"] == 1:
            ex = RuntimeError("API-Fehler 429: Testfehler: Rate-Limit erreicht (synthetisch)")
            ex.kosten_usd = 0.0
            raise ex
        return "Echter Beitrag nach Retry (synthetisch).", 0.02

    monkeypatch.setattr(be, "_turn", fake_turn)
    asyncio.run(d.laufen())

    assert d.status == "fertig"
    assert d.fehler is None
    assert len(d.beitraege) == 2   # min_beitraege-Klemmung (s. _neue_test_debatte-Docstring)
    assert d.beitraege[0]["text"] == "Echter Beitrag nach Retry (synthetisch)."
    assert all("API-Fehler" not in b["text"] for b in d.beitraege)
    assert len(d.moderationen) == len(d.beitraege)   # Parallelitaet gewahrt (B4-Naht wirkt korrekt)
    assert persona_versuche["n"] == 3                # 1 Fehlschlag + 1 Retry-Erfolg + 1 weiterer Beitrag


def test_persona_wird_uebersprungen_nach_erschoepftem_retry(monkeypatch, tmp_path, _db_ready):
    """P2-5-Pendant fuer Personas: schlaegt ein Kopf auch nach dem Retry fehl, wird NUR dieser
    Beitrag ausgelassen -- die Debatte laeuft weiter, statt die gesamte bereits bezahlte Debatte
    abzubrechen. moderationen/beitraege muessen danach weiterhin PARALLEL (gleiche Laenge)
    sein -- sonst verschiebt _verlauf_html()s positionsbasiertes zip() alle folgenden Paare."""
    d, be = _neue_test_debatte(monkeypatch, tmp_path)   # min_beitraege=2 (Default, s. Docstring dort)
    persona_versuche = {"n": 0}

    async def fake_turn(provider, openai_model, system_prompt, user_prompt, persona_model,
                        on_delta, task_id=None):
        if _ist_dispatch(user_prompt):
            if len(d.beitraege) >= d.min_beitraege:
                return json.dumps({"aktion": "abschluss", "begruendung": "genug fuer den Test"}), 0.01
            return json.dumps({"aktion": "dispatch", "kopf": "beirat-vera-brandt",
                               "frage": "Testfrage?"}), 0.01
        if _ist_synthese(user_prompt):
            return "Synthesetext (synthetisch).", 0.01
        # Persona-Turn: die ERSTEN ZWEI Versuche (= die komplette 1. Dispatch-Runde) schlagen
        # fehl, danach (2. und 3. Dispatch-Runde, derselbe Kopf wird erneut aufgerufen) klappt
        # es direkt -- macht die 2 fuer min_beitraege=2 noetigen Beitraege voll.
        persona_versuche["n"] += 1
        if persona_versuche["n"] <= 2:
            raise RuntimeError(f"API-Fehler 429: Testfehler Versuch {persona_versuche['n']} (synthetisch)")
        return "Beitrag nach Ueberspringen (synthetisch).", 0.02

    monkeypatch.setattr(be, "_turn", fake_turn)
    asyncio.run(d.laufen())

    assert d.status == "fertig"
    assert len(d.beitraege) == 2   # min_beitraege-Klemmung (s. _neue_test_debatte-Docstring)
    assert d.beitraege[0]["text"] == "Beitrag nach Ueberspringen (synthetisch)."
    assert len(d.moderationen) == len(d.beitraege)   # Parallelitaet TROTZ einer uebersprungenen Runde
    assert persona_versuche["n"] == 4                # 2 Fehlschlaege (ausgelassene Runde) + 2 Erfolge

    # Live-Ereignisstrom enthaelt eine ehrliche "uebersprungen"-Meldung -- kein stiller Abbruch,
    # keine gespeicherte Halb-Wahrheit.
    ereignisse = []
    while not d.queue.empty():
        ereignisse.append(d.queue.get_nowait())
    status_texte = [e["text"] for e in ereignisse if e and e.get("typ") == "status" and "text" in e]
    assert any("übersprungen" in t for t in status_texte)


def test_dispatch_turn_erfolg_nach_einem_fehlgeschlagenen_versuch(monkeypatch, tmp_path, _db_ready):
    """P2-5 direkt am Dispatch: ein einzelner transienter Fehler beim ersten Dispatch-Aufruf darf
    die Debatte nicht mehr toeten -- genau das war das urspruengliche Schadensbild (3 reale
    Faelle, in denen die gesamte bereits bezahlte Debatte verworfen wurde)."""
    d, be = _neue_test_debatte(monkeypatch, tmp_path)   # min_beitraege=2 (Default, s. Docstring dort)
    dispatch_versuche = {"n": 0}

    async def fake_turn(provider, openai_model, system_prompt, user_prompt, persona_model,
                        on_delta, task_id=None):
        if _ist_dispatch(user_prompt):
            dispatch_versuche["n"] += 1
            if dispatch_versuche["n"] == 1:
                raise RuntimeError("API-Fehler 429: Testfehler (synthetisch)")
            if len(d.beitraege) >= d.min_beitraege:
                return json.dumps({"aktion": "abschluss", "begruendung": "genug fuer den Test"}), 0.01
            return json.dumps({"aktion": "dispatch", "kopf": "beirat-vera-brandt",
                               "frage": "Testfrage?"}), 0.01
        if _ist_synthese(user_prompt):
            return "Synthesetext (synthetisch).", 0.01
        return "Beitrag (synthetisch).", 0.02

    monkeypatch.setattr(be, "_turn", fake_turn)
    asyncio.run(d.laufen())

    assert d.status == "fertig"
    assert d.fehler is None
    assert len(d.beitraege) == 2   # min_beitraege-Klemmung (s. _neue_test_debatte-Docstring)
    assert dispatch_versuche["n"] >= 2   # mindestens 1 Fehlschlag + 1 Retry-Erfolg


def test_dispatch_bricht_ehrlich_ab_nach_erschoepftem_retry(monkeypatch, tmp_path, _db_ready):
    """Dokumentiertes Endverhalten am Dispatch (bewusst ANDERS als bei Personas): bleibt der
    Dispatch auch nach dem Retry kaputt, bricht die Debatte ehrlich ab (status='fehler') -- die
    Vorsitzende darf nicht raten, wer als Naechstes dran ist. Kein Persona-/Synthese-Call darf
    je erreicht werden (Beleg: calls["andere"] bleibt 0)."""
    d, be = _neue_test_debatte(monkeypatch, tmp_path)   # min_beitraege irrelevant: Dispatch scheitert immer
    calls = {"dispatch": 0, "andere": 0}

    async def fake_turn(provider, openai_model, system_prompt, user_prompt, persona_model,
                        on_delta, task_id=None):
        if _ist_dispatch(user_prompt):
            calls["dispatch"] += 1
            raise RuntimeError("API-Fehler 429: Testfehler, immer (synthetisch)")
        calls["andere"] += 1
        return "sollte nie erreicht werden", 0.0

    monkeypatch.setattr(be, "_turn", fake_turn)
    asyncio.run(d.laufen())

    assert d.status == "fehler"
    assert d.fehler
    assert "Testfehler" in d.fehler or "fehlgeschlagen" in d.fehler
    assert len(d.beitraege) == 0
    assert calls["dispatch"] == 2   # 1 Versuch + 1 Retry, dann ehrlicher Abbruch
    assert calls["andere"] == 0     # nie bis zu Persona/Synthese gekommen
