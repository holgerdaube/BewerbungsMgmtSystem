"""Phase 90 (Beiratsbesetzung über die Einstellungen, tasks/spec_phase90_beirat_besetzung.md) —
Tests für Stufe A (`beirat_engine.py`: `lade_mitglieder()` um farbe/vorsitz, `vorsitz_id()` +
PATCH-Kern `aktualisiere_mitglied()`), Stufe B (die drei API-Endpunkte in `main.py`) und Stufe C1
(neue Task-Art `beirat-persona` in `agent_runner.PROMPTS`).

Wie in conftest.py/test_beirat_fehler.py beschrieben: KEINE app.*/pipeline.*-Importe auf
Modulebene (gilt hier auch für `beirat_engine` selbst) — nur in Testfunktionen. Alle
Frontmatter-Tests laufen gegen SYNTHETISCHE `.claude/agents/beirat-*.md`-Nachbauten in
`tmp_path` (`beirat_engine.AGENTS_DIR` wird je Test per monkeypatch dorthin umgebogen) — kein
Test liest oder schreibt die echten Persona-Dateien im Projekt, kein echter Skill-/Debatten-Lauf,
kein Subprozess.

Der wichtigste Test dieser Phase ist `test_patch_aendert_nur_frontmatter_body_bleibt_
byte_identisch` — die 8 KB kalibrierter Persona-Text je Kopf sind das Wertvollste am ganzen
Feature (Spec-Fallstricke); jede andere Regel (Farbe/Vorsitz/Umbenennen) ist wertlos, wenn der
PATCH-Pfad dabei den Body beschädigt.
"""
import pytest


# ── Synthetische Persona-Datei (Muster der echten .claude/agents/beirat-*.md) ────────────────
PERSONA_TEMPLATE = """---
name: {id}
description: {desc}
model: sonnet{farbe_zeile}{vorsitz_zeile}
---

*Fiktive Persona/Archetyp; keine reale Person; Ähnlichkeiten mit lebenden oder verstorbenen
Personen sind unbeabsichtigt.*

# Rolle im Beirat
Du bist **{anzeige}** (Testkopf, rein synthetisch für Phase-90-Tests) — bringt eine
Test-Perspektive in den Beirat ein.

# Mentales Betriebssystem
- Testprinzip eins — unveränderliche Zeile, Beleg für Body-Byte-Identität (Umlaute: äöüß).
- Testprinzip zwei — „mit typografischen Anführungszeichen“.

# Grenzen & blinde Flecken
- Verweist auf einen anderen Testkopf, wenn es um etwas anderes geht als seine eigene Brille.
"""


def _persona_schreiben(ordner, id_, anzeige="Test Kopf", desc="Testbeschreibung für Phase 90.",
                       farbe=None, vorsitz=None):
    """Legt EINE synthetische Persona-Datei in `ordner` an (Muster der sieben echten Dateien).
    `farbe`/`vorsitz` bleiben standardmäßig KOMPLETT aus dem Frontmatter weg (nicht etwa leer
    gesetzt) — genau der Altbestand-Fall, den A1s Code-Fallback abfangen muss."""
    farbe_zeile = "\nfarbe: \"" + farbe + "\"" if farbe else ""
    vorsitz_zeile = "" if vorsitz is None else "\nvorsitz: " + ("true" if vorsitz else "false")
    text = PERSONA_TEMPLATE.format(id=id_, desc=desc, farbe_zeile=farbe_zeile,
                                   vorsitz_zeile=vorsitz_zeile, anzeige=anzeige)
    pfad = ordner / (id_ + ".md")
    pfad.write_text(text, encoding="utf-8")
    return pfad


# ── A1: lade_mitglieder() liest farbe/vorsitz aus dem Frontmatter ────────────────────────────

def test_lade_mitglieder_liest_farbe_und_vorsitz_aus_frontmatter(monkeypatch, tmp_path):
    import beirat_engine as be
    monkeypatch.setattr(be, "AGENTS_DIR", tmp_path)
    _persona_schreiben(tmp_path, "beirat-test-a", anzeige="Alpha Test", farbe="#112233", vorsitz=True)
    _persona_schreiben(tmp_path, "beirat-test-b", anzeige="Beta Test", farbe="#445566", vorsitz=False)

    mitglieder = {m["id"]: m for m in be.lade_mitglieder()}
    assert mitglieder["beirat-test-a"]["farbe"] == "#112233"
    assert mitglieder["beirat-test-a"]["vorsitz"] is True
    assert mitglieder["beirat-test-b"]["farbe"] == "#445566"
    assert mitglieder["beirat-test-b"]["vorsitz"] is False


def test_lade_mitglieder_faellt_ohne_frontmatter_felder_auf_code_fallback_zurueck(monkeypatch, tmp_path):
    """Altbestand ohne farbe:/vorsitz: im Frontmatter. Auflösung laut Spec: Frontmatter >
    FARBEN-Tabelle > Neutralgrau `#64748b`; ohne das `vorsitz`-Feld gilt ein Kopf als NICHT
    Vorsitz (kein Rätselraten — die Auflösung „keiner markiert → Fallback auf VORSITZ_ID“
    passiert erst in `vorsitz_id()`, s. unten)."""
    import beirat_engine as be
    monkeypatch.setattr(be, "AGENTS_DIR", tmp_path)
    # bekannter Code-Fallback-Eintrag: beirat-ray-calloway steht in FARBEN
    _persona_schreiben(tmp_path, "beirat-ray-calloway", anzeige="Ray Calloway")
    # unbekannte ID: fällt auf das Neutralgrau zurück
    _persona_schreiben(tmp_path, "beirat-unbekannt", anzeige="Unbekannt")

    mitglieder = {m["id"]: m for m in be.lade_mitglieder()}
    assert mitglieder["beirat-ray-calloway"]["farbe"] == be.FARBEN["beirat-ray-calloway"]
    assert mitglieder["beirat-ray-calloway"]["vorsitz"] is False
    assert mitglieder["beirat-unbekannt"]["farbe"] == "#64748b"
    assert mitglieder["beirat-unbekannt"]["vorsitz"] is False


def test_lade_mitglieder_liefert_volle_perspektive_und_gekuerzte_beschreibung(monkeypatch, tmp_path):
    """B1: `perspektive` = volle `description`, `beschreibung` bleibt wie bisher auf 300 Zeichen
    gekappt (Live-Ansicht der Debatte, unverändertes Verhalten)."""
    import beirat_engine as be
    monkeypatch.setattr(be, "AGENTS_DIR", tmp_path)
    # .strip(): das Frontmatter-Feld wird beim Parsen immer getrimmt (_frontmatter_feld) — ein
    # nachgestelltes Leerzeichen aus der Wiederholung würde beim Rück-Vergleich sonst stören.
    lange_beschreibung = ("Testsatz für die Perspektive. " * 15).strip()
    assert len(lange_beschreibung) > 300
    _persona_schreiben(tmp_path, "beirat-test-lang", anzeige="Lang Test", desc=lange_beschreibung)

    m = {m["id"]: m for m in be.lade_mitglieder()}["beirat-test-lang"]
    assert m["perspektive"] == lange_beschreibung
    assert m["beschreibung"] == lange_beschreibung[:300]
    assert len(m["beschreibung"]) == 300


# ── A2: vorsitz_id() — genau einer markiert → dieser; keiner/mehrere → Fallback + Warnung ────

def test_vorsitz_id_mit_genau_einem_markierten_mitglied():
    import beirat_engine as be
    mitglieder = {
        "beirat-a": {"id": "beirat-a", "vorsitz": False},
        "beirat-b": {"id": "beirat-b", "vorsitz": True},
    }
    assert be.vorsitz_id(mitglieder) == "beirat-b"


def test_vorsitz_id_faellt_bei_keinem_markierten_mitglied_auf_konstante_zurueck(capsys):
    import beirat_engine as be
    mitglieder = {
        "beirat-a": {"id": "beirat-a", "vorsitz": False},
        "beirat-b": {"id": "beirat-b", "vorsitz": False},
    }
    ergebnis = be.vorsitz_id(mitglieder)
    assert ergebnis == be.VORSITZ_ID
    ausgabe = capsys.readouterr().out
    assert "WARNUNG" in ausgabe and "vorsitz_id" in ausgabe


def test_vorsitz_id_faellt_bei_mehreren_markierten_mitgliedern_auf_konstante_zurueck(capsys):
    import beirat_engine as be
    mitglieder = {
        "beirat-a": {"id": "beirat-a", "vorsitz": True},
        "beirat-b": {"id": "beirat-b", "vorsitz": True},
    }
    ergebnis = be.vorsitz_id(mitglieder)
    assert ergebnis == be.VORSITZ_ID
    ausgabe = capsys.readouterr().out
    assert "WARNUNG" in ausgabe and "2 Mitglieder markiert" in ausgabe


def test_vorsitz_id_akzeptiert_auch_eine_liste_statt_eines_dicts():
    """`Debatte.__init__` ruft `vorsitz_id(self.mitglieder)` mit einem id→dict-Dict auf; die
    Funktion soll aber auch eine reine Liste (z. B. direkt `lade_mitglieder()`) akzeptieren —
    beide Formen sind im Modul im Umlauf."""
    import beirat_engine as be
    mitglieder = [{"id": "beirat-a", "vorsitz": False}, {"id": "beirat-b", "vorsitz": True}]
    assert be.vorsitz_id(mitglieder) == "beirat-b"


# ── B2 / Kern: PATCH ändert NUR das Frontmatter — der wichtigste Test dieser Phase ───────────

def test_patch_aendert_nur_frontmatter_body_bleibt_byte_identisch(monkeypatch, tmp_path):
    import beirat_engine as be
    monkeypatch.setattr(be, "AGENTS_DIR", tmp_path)
    pfad = _persona_schreiben(tmp_path, "beirat-test-a", anzeige="Alpha Test",
                              farbe="#112233", vorsitz=False)
    original_front, original_body = be._frontmatter_parsen(pfad.read_text(encoding="utf-8"))

    be.aktualisiere_mitglied("beirat-test-a", {"farbe": "#abcdef", "perspektive": "Neue Perspektive."})

    neues_front, neuer_body = be._frontmatter_parsen(pfad.read_text(encoding="utf-8"))
    assert neuer_body == original_body                              # Zeichen für Zeichen identisch
    assert neuer_body.encode("utf-8") == original_body.encode("utf-8")  # ausdrücklich Byte-Ebene
    assert 'farbe: "#abcdef"' in neues_front
    assert "description: Neue Perspektive." in neues_front
    # Felder, die NICHT im PATCH-Payload standen, bleiben unangetastet
    assert "name: beirat-test-a" in neues_front
    assert "model: sonnet" in neues_front


def test_patch_ohne_anzeige_laesst_die_rollen_zeile_unangetastet(monkeypatch, tmp_path):
    """Gegenprobe zur Umbenennen-Ausnahme: OHNE `anzeige` im Payload darf sich an der
    „Du bist **…**“-Zeile gar nichts ändern, auch wenn andere Felder gepatcht werden."""
    import beirat_engine as be
    monkeypatch.setattr(be, "AGENTS_DIR", tmp_path)
    pfad = _persona_schreiben(tmp_path, "beirat-test-a", anzeige="Alpha Test")
    original_text = pfad.read_text(encoding="utf-8")

    be.aktualisiere_mitglied("beirat-test-a", {"farbe": "#abcdef"})

    _, neuer_body = be._frontmatter_parsen(pfad.read_text(encoding="utf-8"))
    _, original_body = be._frontmatter_parsen(original_text)
    assert neuer_body == original_body
    assert "Du bist **Alpha Test**" in neuer_body


# ── B2: Umbenennen zieht die Body-Zeile „Du bist **<Name>**“ mit ────────────────────────────

def test_patch_anzeige_umbenennen_zieht_body_zeile_mit(monkeypatch, tmp_path):
    import beirat_engine as be
    monkeypatch.setattr(be, "AGENTS_DIR", tmp_path)
    pfad = _persona_schreiben(tmp_path, "beirat-test-a", anzeige="Alpha Test")
    _, original_body = be._frontmatter_parsen(pfad.read_text(encoding="utf-8"))

    m = be.aktualisiere_mitglied("beirat-test-a", {"anzeige": "Alpha Neu"})

    assert m["anzeige"] == "Alpha Neu"
    _, neuer_body = be._frontmatter_parsen(pfad.read_text(encoding="utf-8"))
    assert "Du bist **Alpha Neu**" in neuer_body
    assert "Du bist **Alpha Test**" not in neuer_body
    assert neuer_body.count("Du bist **Alpha Neu**") == 1            # genau EINE Fundstelle
    # Rest des Bodys unangetastet: die eine Zeile zurückgerechnet ergibt wieder das Original
    zurueckgerechnet = neuer_body.replace("Du bist **Alpha Neu**", "Du bist **Alpha Test**", 1)
    assert zurueckgerechnet == original_body


# ── B2: Vorsitz-Regeln (genau einer, immer einer) ────────────────────────────────────────────

def test_patch_vorsitz_true_nimmt_es_dem_bisherigen_ab(monkeypatch, tmp_path):
    import beirat_engine as be
    monkeypatch.setattr(be, "AGENTS_DIR", tmp_path)
    _persona_schreiben(tmp_path, "beirat-test-a", anzeige="Alpha", vorsitz=True)
    _persona_schreiben(tmp_path, "beirat-test-b", anzeige="Beta", vorsitz=False)

    be.aktualisiere_mitglied("beirat-test-b", {"vorsitz": True})

    mitglieder = {m["id"]: m for m in be.lade_mitglieder()}
    assert mitglieder["beirat-test-b"]["vorsitz"] is True
    assert mitglieder["beirat-test-a"]["vorsitz"] is False
    assert sum(1 for m in mitglieder.values() if m["vorsitz"]) == 1  # immer genau einer


def test_patch_vorsitz_false_auf_einzigen_vorsitz_ist_fehler(monkeypatch, tmp_path):
    import beirat_engine as be
    monkeypatch.setattr(be, "AGENTS_DIR", tmp_path)
    pfad_a = _persona_schreiben(tmp_path, "beirat-test-a", anzeige="Alpha", vorsitz=True)
    original_text = pfad_a.read_text(encoding="utf-8")
    _persona_schreiben(tmp_path, "beirat-test-b", anzeige="Beta", vorsitz=False)

    with pytest.raises(be.MitgliedFehler):
        be.aktualisiere_mitglied("beirat-test-a", {"vorsitz": False})

    # unverändert: Alpha bleibt Vorsitz, die Datei wurde gar nicht erst angefasst
    assert pfad_a.read_text(encoding="utf-8") == original_text
    mitglieder = {m["id"]: m for m in be.lade_mitglieder()}
    assert mitglieder["beirat-test-a"]["vorsitz"] is True


def test_patch_vorsitz_false_auf_nicht_vorsitz_ist_erlaubt(monkeypatch, tmp_path):
    """Gegenprobe: `vorsitz: false` auf ein Mitglied, das ohnehin nicht Vorsitz ist, bleibt
    harmlos — die 422-Regel greift NUR beim aktuellen UND einzigen Vorsitz."""
    import beirat_engine as be
    monkeypatch.setattr(be, "AGENTS_DIR", tmp_path)
    _persona_schreiben(tmp_path, "beirat-test-a", anzeige="Alpha", vorsitz=True)
    _persona_schreiben(tmp_path, "beirat-test-b", anzeige="Beta", vorsitz=False)

    m = be.aktualisiere_mitglied("beirat-test-b", {"vorsitz": False})
    assert m["vorsitz"] is False


def test_patch_unbekannter_platz_ist_nicht_gefunden(monkeypatch, tmp_path):
    import beirat_engine as be
    monkeypatch.setattr(be, "AGENTS_DIR", tmp_path)
    _persona_schreiben(tmp_path, "beirat-test-a", anzeige="Alpha")

    with pytest.raises(be.MitgliedNichtGefunden):
        be.aktualisiere_mitglied("beirat-nicht-vorhanden", {"farbe": "#112233"})


# ── B2: ungültige Farbe → Fehler (main.py übersetzt das in 422) ─────────────────────────────

@pytest.mark.parametrize("ungueltig", ["blau", "#12345", "#1234567", "112233", "#GGHHII", ""])
def test_patch_ungueltige_farbe_ist_fehler(monkeypatch, tmp_path, ungueltig):
    import beirat_engine as be
    monkeypatch.setattr(be, "AGENTS_DIR", tmp_path)
    _persona_schreiben(tmp_path, "beirat-test-a", anzeige="Alpha")

    with pytest.raises(be.MitgliedFehler):
        be.aktualisiere_mitglied("beirat-test-a", {"farbe": ungueltig})


# ── B: die drei HTTP-Endpunkte (main.py) — Whitelist, Status-Codes, Feldnamen ────────────────

def test_get_mitglieder_endpoint_liefert_vorsitz_und_perspektive(client, monkeypatch, tmp_path):
    import beirat_engine as be
    monkeypatch.setattr(be, "AGENTS_DIR", tmp_path)
    lang = ("Testperspektive für den Endpunkt. " * 15).strip()  # s. Kommentar im A1-Pendant oben
    _persona_schreiben(tmp_path, "beirat-test-a", anzeige="Alpha", desc=lang, vorsitz=True)

    resp = client.get("/api/beirat/mitglieder")
    assert resp.status_code == 200
    daten = {m["id"]: m for m in resp.json()}
    assert daten["beirat-test-a"]["vorsitz"] is True
    assert daten["beirat-test-a"]["perspektive"] == lang
    assert daten["beirat-test-a"]["beschreibung"] == lang[:300]


def test_patch_endpoint_ungueltige_farbe_ist_422(client, monkeypatch, tmp_path):
    import beirat_engine as be
    monkeypatch.setattr(be, "AGENTS_DIR", tmp_path)
    _persona_schreiben(tmp_path, "beirat-test-a", anzeige="Alpha")

    resp = client.patch("/api/beirat/mitglieder/beirat-test-a", json={"farbe": "keinehexfarbe"})
    assert resp.status_code == 422


def test_patch_endpoint_unbekannter_platz_ist_404(client, monkeypatch, tmp_path):
    import beirat_engine as be
    monkeypatch.setattr(be, "AGENTS_DIR", tmp_path)
    _persona_schreiben(tmp_path, "beirat-test-a", anzeige="Alpha")

    resp = client.patch("/api/beirat/mitglieder/beirat-nicht-da", json={"farbe": "#112233"})
    assert resp.status_code == 404


def test_patch_endpoint_ignoriert_unbekannte_payload_felder(client, monkeypatch, tmp_path):
    """Whitelist-Filter in main.py: ein fremder Payload-Schlüssel (hier `model`) darf weder
    einen Fehler auslösen noch durchschlagen — nur `anzeige`/`perspektive`/`farbe`/`vorsitz`
    sind erlaubt."""
    import beirat_engine as be
    monkeypatch.setattr(be, "AGENTS_DIR", tmp_path)
    _persona_schreiben(tmp_path, "beirat-test-a", anzeige="Alpha", farbe="#112233")

    resp = client.patch("/api/beirat/mitglieder/beirat-test-a",
                        json={"model": "opus", "farbe": "#654321"})
    assert resp.status_code == 200
    daten = resp.json()
    assert daten["farbe"] == "#654321"
    assert daten["model"] == "sonnet"          # unverändert — 'model' ist nicht erlaubt


def test_patch_endpoint_setzt_vorsitz_um(client, monkeypatch, tmp_path):
    import beirat_engine as be
    monkeypatch.setattr(be, "AGENTS_DIR", tmp_path)
    _persona_schreiben(tmp_path, "beirat-test-a", anzeige="Alpha", vorsitz=True)
    _persona_schreiben(tmp_path, "beirat-test-b", anzeige="Beta", vorsitz=False)

    resp = client.patch("/api/beirat/mitglieder/beirat-test-b", json={"vorsitz": True})
    assert resp.status_code == 200 and resp.json()["vorsitz"] is True

    nochmal = client.get("/api/beirat/mitglieder")
    daten = {m["id"]: m for m in nochmal.json()}
    assert daten["beirat-test-a"]["vorsitz"] is False
    assert daten["beirat-test-b"]["vorsitz"] is True


def test_neu_besetzen_endpoint_ohne_name_ist_422(client, monkeypatch, tmp_path):
    import beirat_engine as be
    monkeypatch.setattr(be, "AGENTS_DIR", tmp_path)
    _persona_schreiben(tmp_path, "beirat-test-a", anzeige="Alpha")

    resp = client.post("/api/beirat/mitglieder/beirat-test-a/neu-besetzen", json={"perspektive": "X"})
    assert resp.status_code == 422


def test_neu_besetzen_endpoint_ohne_perspektive_ist_422(client, monkeypatch, tmp_path):
    import beirat_engine as be
    monkeypatch.setattr(be, "AGENTS_DIR", tmp_path)
    _persona_schreiben(tmp_path, "beirat-test-a", anzeige="Alpha")

    resp = client.post("/api/beirat/mitglieder/beirat-test-a/neu-besetzen", json={"name": "X"})
    assert resp.status_code == 422


def test_neu_besetzen_endpoint_unbekannter_platz_ist_404(client, monkeypatch, tmp_path):
    import beirat_engine as be
    monkeypatch.setattr(be, "AGENTS_DIR", tmp_path)
    _persona_schreiben(tmp_path, "beirat-test-a", anzeige="Alpha")

    resp = client.post("/api/beirat/mitglieder/beirat-nicht-da/neu-besetzen",
                       json={"name": "X", "perspektive": "Y"})
    assert resp.status_code == 404


# ── C1: Task-Art „beirat-persona“ (agent_runner.PROMPTS) ────────────────────────────────────

def test_prompts_beirat_persona_ist_headless_und_nicht_retryable():
    from app import agent_runner
    spec = agent_runner.PROMPTS["beirat-persona"]
    assert spec["headless"] is True
    assert spec.get("retryable", False) is False        # PFLICHT laut Spec: kein blinder Retry
    assert spec["timeout_s"] == 1800
    assert spec["needs_params"] == ("platz_id", "name", "perspektive")


def test_build_prompt_beirat_persona_enthaelt_die_drei_parameter():
    from app import agent_runner
    prompt = agent_runner.build_prompt(
        "beirat-persona", None,
        {"platz_id": "beirat-ray-calloway", "name": "Neuer Kopf", "perspektive": "Vergütung und Verhandlung"},
    )
    assert "beirat-ray-calloway" in prompt
    assert "Neuer Kopf" in prompt
    assert "Vergütung und Verhandlung" in prompt


def test_build_prompt_beirat_persona_fehlender_parameter_wirft():
    from app import agent_runner
    with pytest.raises(agent_runner.PromptError):
        agent_runner.build_prompt("beirat-persona", None,
                                  {"platz_id": "beirat-ray-calloway", "name": "X"})
