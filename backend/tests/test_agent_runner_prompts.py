"""Tests für Phase 78: `build_prompt("cv-match", ...)` trägt den Rahmen-Kontrakt „baue IMMER neu
aus der aktuellen Basis-CV-Datei" (s. tasks/spec_phase78_cv_match_neuaufbau.md, Entscheidung 2).

Anlass (Fall A, 07.08.2026): Ein manuell gestarteter cv-match-Lauf hatte
nach dem v10-Umbau der Basis-CVs „bereits vollständig erledigt" erkannt und einen v9-basierten
Alt-Entwurf recycelt statt neu zu bauen — eine vom Modell selbst improvisierte Abkürzung, die
NIRGENDS spezifiziert war (weder im Runner noch in der SKILL.md). Lehre aus dem
job-frage-Fall (Commit a4c8c60): ein Kontrakt, der AUSNAHMSLOS gelten soll, gehört ins
Runner-TEMPLATE, nicht nur in die SKILL.md — sonst erreicht er den Lauf nicht garantiert.

Diese Tests prüfen NUR den Text im Prompt-Template (das testbare Artefakt, s. Spec Stufe C) —
kein LLM-Verhalten (nicht deterministisch testbar).

App-Importe ausschließlich innerhalb der Testfunktionen (Konvention aus conftest.py — siehe
dessen Docstring zur Import-Reihenfolge). `build_prompt()` selbst braucht weder DB noch
Dateisystem, die Konvention wird trotzdem eingehalten, damit die Import-Reihenfolge unabhängig
von der Ausführungsreihenfolge der Testdateien bleibt.
"""
import pytest


def test_cv_match_prompt_enthaelt_rahmen_kontrakt_immer_neu():
    """Schlüsselphrase aus Spec-Entscheidung 2 — der Kern des Kontrakts: kein Recycling einer
    bereits vorhandenen CVVersion, jeder Lauf baut neu aus der aktuellen Basis-CV-Datei."""
    from app.agent_runner import build_prompt

    prompt = build_prompt("cv-match", 7)

    assert "IMMER neu" in prompt


def test_cv_match_prompt_enthaelt_neue_cvversion_pflicht():
    """Zweite Schlüsselphrase aus Spec-Entscheidung 2: eine NEUE CVVersion-Row entsteht, die
    alte bleibt unangetastet — genau das hat der Echtfall vom 07.08.2026 verletzt (Row 80 wurde
    wiederverwendet statt eine neue anzulegen)."""
    from app.agent_runner import build_prompt

    prompt = build_prompt("cv-match", 7)

    assert "NEUE CVVersion" in prompt


def test_cv_match_prompt_enthaelt_weiterhin_headless_suffix():
    """Der Rahmen-Absatz ist eine ERGÄNZUNG hinter dem Trigger-Satz (Muster job-frage) — der
    HEADLESS_SUFFIX (gilt für JEDEN headless-Lauf, u. a. die Fremdtext-Warnung aus Phase 66B)
    darf dadurch nicht verloren gehen."""
    from app.agent_runner import HEADLESS_SUFFIX, build_prompt

    prompt = build_prompt("cv-match", 7)

    assert prompt.endswith(HEADLESS_SUFFIX)


def test_cv_match_prompt_enthaelt_weiterhin_trigger_satz_mit_job_id():
    """Der ursprüngliche Trigger-Satz („CV-Match für Job {job_id}") bleibt am Anfang des Prompts
    erhalten — Downstream-Code (Task-Center-Anzeige, Ketten-Aufrufe) darf sich weiter darauf
    verlassen, dass der Prompt damit beginnt."""
    from app.agent_runner import build_prompt

    prompt = build_prompt("cv-match", 7)

    assert prompt.startswith("CV-Match für Job 7")


def test_cv_match_prompt_ohne_job_id_wirft_prompterror():
    """Regressionsschutz: `needs_job` bleibt unverändert True — der Umbau des Templates vom
    Einzeiler auf ein mehrzeiliges Muster darf die bestehende Validierung nicht aushebeln."""
    from app.agent_runner import PromptError, build_prompt

    with pytest.raises(PromptError):
        build_prompt("cv-match", None)


def test_cv_match_prompt_ist_syntaktisch_sauber_gebaut():
    """Regressionsschutz gegen die P2-15-Falle (typografische Anführungszeichen in
    Python-String-Literalen — ein ASCII '\"' als schließendes Zeichen bricht den String):
    das reine Zustandekommen von `PROMPTS["cv-match"]["template"]` als String und der
    erfolgreiche `.format()`-Aufruf beweisen, dass das Literal syntaktisch intakt ist."""
    from app.agent_runner import PROMPTS

    template = PROMPTS["cv-match"]["template"]

    assert isinstance(template, str)
    assert template.format(job_id=1)   # wirft bei einem kaputten/verschachtelten Literal


def test_cv_match_spec_ist_ansonsten_unveraendert():
    """Rahmenbedingungen aus Entscheidung 5 der Spec (kein Schema-/API-Change, kein neuer
    Parameter): `needs_job`, `headless` und `disallowed_tools` bleiben exakt wie vor Phase 78."""
    from app.agent_runner import PROMPTS

    spec = PROMPTS["cv-match"]

    assert spec["needs_job"] is True
    assert spec["headless"] is True
    assert spec["disallowed_tools"] == ["WebSearch"]
    assert "force" not in spec   # Entscheidung 1: bewusst KEIN force-Flag


# ── P2-45: derselbe Kontrakt für den Geschwister-Skill `cv-erstellen` ───────────────────────
# Fall B (25.09.2026): Der Lauf meldete „war schon heute abgeschlossen
# (Status `fertig`), ich habe nichts neu erzeugt, nur verifiziert" und endete nach 15 Sekunden —
# dieselbe improvisierte Abkürzung wie oben bei cv-match, nur beim Schwester-Skill. Der Kontrakt
# steht deshalb auch hier im TEMPLATE, nicht nur in der SKILL.md.
def test_cv_erstellen_prompt_verbietet_die_schon_erledigt_abkuerzung():
    from app.agent_runner import build_prompt

    prompt = build_prompt("cv-erstellen", 679)

    assert "IMMER neu" in prompt
    assert "fertig" in prompt          # der Status, der als Abbruchgrund ausgeschlossen wird


def test_cv_erstellen_prompt_verlangt_dieselbe_cvversion():
    """Unterschied zu cv-match: KEINE neue Row. Der Editier-Zyklus (bearbeiten, speichern, neu
    erstellen, P2-45) arbeitet bewusst auf derselben CVVersion — sonst stünden am Job zwei
    Versionen für denselben Stand."""
    from app.agent_runner import build_prompt

    prompt = build_prompt("cv-erstellen", 679)

    assert "DERSELBEN CVVersion" in prompt
    assert "keine neue" in prompt



# ── P2-74: Rahmen-Kontrakt für `mail-jobsuche` ───────────────────────────────────────────────
# Anlass: Nach einem Modellwechsel erreichten nur noch 10 % statt 44 % der extrahierten Postings
# den Ingest. Die Läufe sortierten schon anhand der Mail-Angaben aus (Ort außerhalb des Umkreises,
# schwache Passung, angenommene Firmengröße). Der Kern der Gegenregel steht deshalb im TEMPLATE.
def test_mail_jobsuche_prompt_beginnt_weiter_mit_dem_trigger():
    """Der Trigger-Satz bleibt die erste Zeile: Daran erkennt der Lauf den Skill."""
    from app.agent_runner import build_prompt

    prompt = build_prompt("mail-jobsuche", None)

    assert prompt.startswith("Mail-Jobsuche\n\nRahmen (Pflicht):")


def test_mail_jobsuche_prompt_verlangt_beleg_fuer_jede_grenze():
    from app.agent_runner import build_prompt

    prompt = build_prompt("mail-jobsuche", None)

    assert "nur aus, wenn es eine harte Grenze BELEGT verletzt" in prompt
    assert "eine Annahme ist keiner" in prompt
    assert "je aussortiertem Posting die Grenze und der Beleg" in prompt


def test_mail_jobsuche_prompt_schliesst_ort_und_schwache_passung_als_gruende_aus():
    """Die beiden Gründe, mit denen die Läufe den größten Teil aussortiert hatten."""
    from app.agent_runner import build_prompt

    prompt = build_prompt("mail-jobsuche", None)

    assert "Ein Ort außerhalb des Umkreises ist für sich kein Ausschlussgrund" in prompt
    assert "Bucket „Deutschlandweit“" in prompt
    assert "Schwache Passung ist ebenfalls kein Ausschlussgrund" in prompt
    assert "mit Score 1 oder 2" in prompt


def test_mail_jobsuche_prompt_traegt_weiter_den_headless_suffix():
    from app.agent_runner import HEADLESS_SUFFIX, build_prompt

    prompt = build_prompt("mail-jobsuche", None)

    assert prompt.endswith(HEADLESS_SUFFIX)
    assert prompt.count("Rahmen (Pflicht):") == 1


def test_die_uebrigen_suchlaeufe_behalten_ihren_reinen_trigger():
    """Der Kontrakt gilt dem Lauf, an dem der Einbruch gemessen wurde. Die Regel selbst steht für
    alle Suchläufe im gemeinsamen Abschnitt; ein Rahmen in jeder Vorlage würde sie nur
    vervielfachen."""
    from app.agent_runner import HEADLESS_SUFFIX, build_prompt

    for kind, trigger in (("zielfirmen-sweep", "Zielfirmen-Sweep"), ("headhunter-suche", "Headhunter-Suche")):
        assert build_prompt(kind, None) == trigger + HEADLESS_SUFFIX


def _sprache_setzen(monkeypatch, wert):
    from app import sprache
    monkeypatch.setattr(sprache, "aktuell", lambda: wert)


def test_deutscher_prompt_bleibt_ohne_sprachhinweis(monkeypatch):
    from app import agent_runner as ar
    _sprache_setzen(monkeypatch, "de")
    assert ar.build_prompt("firma-pruefen", 1).endswith(ar.HEADLESS_SUFFIX)


def test_englischer_prompt_nennt_die_ausgabesprache(monkeypatch):
    from app import agent_runner as ar
    _sprache_setzen(monkeypatch, "en")
    prompt = ar.build_prompt("firma-pruefen", 1)
    assert prompt.endswith(ar.SPRACH_HINWEIS_EN)
    assert "config/glossar_de_en.md" in prompt


def test_chatgpt_erbt_den_sprachhinweis(monkeypatch):
    from app import agent_runner as ar, ki_anbieter
    _sprache_setzen(monkeypatch, "en")
    prompt = ar.build_prompt("firma-pruefen", 1)
    assert ar.SPRACH_HINWEIS_EN in ki_anbieter.codex_prompt(prompt, "firma-pruefen", ar.PROMPTS["firma-pruefen"])


def test_persona_datei_bleibt_ausgenommen(monkeypatch):
    from app import agent_runner as ar
    _sprache_setzen(monkeypatch, "en")
    prompt = ar.build_prompt("beirat-persona", None, {"platz_id": "x", "name": "y", "perspektive": "z"})
    assert ar.SPRACH_HINWEIS_EN not in prompt


def test_glossar_liegt_im_kundenpaket():
    from pipeline import kundenpaket
    assert "config/glossar_de_en.md" in kundenpaket.PFLICHTDATEIEN


def test_meldungen_zu_task_arten_folgen_der_sprache(monkeypatch):
    """Die Meldung erreicht die Oberfläche als `detail`. Auf Englisch darf sie nicht deutsch bleiben."""
    from app import sprache
    from app.agent_runner import PromptError, build_prompt

    monkeypatch.setattr(sprache, "aktuell", lambda: "en")
    with pytest.raises(PromptError, match="Unknown task type 'gibt-es-nicht'. Allowed: "):
        build_prompt("gibt-es-nicht", None)
