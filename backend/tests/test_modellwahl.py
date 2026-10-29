"""P2-51 (V6) und P2-59 — „KI-Modell je Funktion“: drei wählbare Aliase (opus/sonnet/haiku),
Standard bleibt „sonnet“, Anzeigenamen nur noch im Backend gepflegt (`agent_runner.MODELLE`).
Seit P2-59 ist Fable NICHT wählbar (Vorgabe 01.10.2026, Kosten: $10/$50 statt $4/$20 je
Mio. Tokens bei Opus 5.5): `agent_runner.GESPERRTE_MODELLE` und `agent_runner.wirksames_modell()`.

Deckt ab:
  1. `GET /api/einstellungen` liefert `modell_optionen` mit genau opus/sonnet/haiku (Reihenfolge
     und Anzeigenamen), ohne Fable, und `modell_standard == "sonnet"`.
  2. `PATCH /api/einstellungen` mit einem erlaubten Alias -> 200, roundtrip.
  3. `PATCH` mit `fable` oder einem unbekannten Alias -> 422; die Meldung nennt nur die erlaubten
     Aliase, die gespeicherten Werte bleiben unverändert.
  4. `agent_runner.modell_fuer_kind()` / `modell_fuer_beirat()` lesen den gespeicherten Alias aus
     der DB-Zeile.
  5. Ein früher gespeichertes `fable` (oder ein unbekannter Wert) läuft mit `sonnet`: in
     `modell_fuer_kind`, `modell_fuer_beirat`, `_argv`, der Beirats-Debatte und in
     `GET /api/einstellungen`; Lesen verändert die gespeicherte Zeile nie, die Einstellungen-Karte
     kann danach ohne Fehler speichern.
  6. `wirksames_modell`: Einheit (erlaubt/gesperrt/unbekannt/leer) und höchstens eine Log-Zeile je
     Wert und Prozess.
  7. Wächter: jedes `PROMPTS[*]["model"]` ist ein erlaubter Alias, `GESPERRTE_MODELLE` und
     `MODELL_ALIASE` überschneiden sich nie.
  8. `_argv` setzt `--model <alias>`; die Altwerte `opus`/`haiku` bleiben gültig (keine Migration,
     Entscheidung 6 der P2-51-Bau-Spec).

WICHTIG — Test-Isolation (Muster `test_einstellungen_portale.py`): `PATCH /api/einstellungen`
schreibt `config/suchprofile.yaml` über `suchprofil.regenerieren()` — das autouse-Fixture unten
leitet `suchprofil.SUCHPROFILE_PATH` immer auf eine `tmp_path`-Kopie um. `SuchEinstellung` ist ein
echter Singleton (id=1) über die session-weite tmp-DB (conftest.py::_db_ready) — jeder Test setzt
seine Ausgangslage über `_reset_einstellungen()`. App-Module werden nie auf Modulebene importiert,
nur innerhalb der Testfunktionen/Fixtures (Konvention aus conftest.py)."""
import json

import pytest


@pytest.fixture(autouse=True)
def _suchprofile_yaml_isoliert(tmp_path, monkeypatch):
    """PFLICHT (Muster test_einstellungen_portale.py): niemals die echte
    config/suchprofile.yaml lesen oder beschreiben."""
    from pipeline import suchprofil

    pfad = tmp_path / "suchprofile.yaml"
    pfad.write_text(suchprofil.MARKER + "\nportale_technik: {}\n", encoding="utf-8")
    monkeypatch.setattr(suchprofil, "SUCHPROFILE_PATH", pfad)
    return pfad


@pytest.fixture(autouse=True)
def _rueckfall_log_frisch(monkeypatch):
    """P2-59: `wirksames_modell` loggt je Prozess und Wert nur einmal. Ohne frischen Merker hinge
    es von der Testreihenfolge ab, ob ein Test die Zeile überhaupt sieht."""
    from app import agent_runner

    monkeypatch.setattr(agent_runner, "_RUECKFALL_GELOGGT", set())


def _reset_einstellungen(session):
    from app.models import SuchEinstellung

    vorhanden = session.get(SuchEinstellung, 1)
    if vorhanden:
        session.delete(vorhanden)
        session.commit()


def _modelle_roh_setzen(session, client, modelle: dict):
    """Legt den Altbestand an, den die API nicht mehr erzeugen kann: ROHE Werte in
    `sucheinstellung.modelle_json` (z. B. ein früher gewähltes Fable). Die Zeile entsteht über
    den normalen GET, damit alle übrigen Felder wie in einer echten Installation befüllt sind."""
    from app.models import SuchEinstellung

    _reset_einstellungen(session)
    client.get("/api/einstellungen")
    session.expire_all()
    e = session.get(SuchEinstellung, 1)
    e.modelle_json = json.dumps(modelle)
    session.add(e)
    session.commit()


def _modelle_roh(session) -> dict:
    """Die GESPEICHERTEN Werte, ohne Umweg über die API (die zeigt die wirksamen)."""
    from app.models import SuchEinstellung

    session.expire_all()
    return json.loads(session.get(SuchEinstellung, 1).modelle_json)


# ── 1. GET: drei Optionen ohne Fable, Standard sonnet ──────────────────────────────────────
def test_get_liefert_drei_modell_optionen_ohne_fable_und_standard_sonnet(session, client):
    _reset_einstellungen(session)

    r = client.get("/api/einstellungen")

    assert r.status_code == 200
    body = r.json()
    assert body["modell_standard"] == "sonnet"
    # Reihenfolge = Anzeigereihenfolge der Auswahl; die Namen nennen die heutige Version.
    assert body["modell_optionen"] == [
        {"alias": "opus", "label": "Opus 5.5"},
        {"alias": "sonnet", "label": "Sonnet 5.5"},
        {"alias": "haiku", "label": "Haiku 4.5"},
    ]
    assert "fable" not in json.dumps(body["modell_optionen"]).lower()
    # Frische Zeile: alle sechs Funktionen mit dem Standardmodell vorbelegt.
    assert set(body["modelle"].values()) == {"sonnet"}


# ── 2. PATCH: erlaubten Alias speichern ──────────────────────────────────────────────────────
def test_patch_modelle_erlaubter_alias_ist_200_und_roundtrip(session, client):
    _reset_einstellungen(session)

    r = client.patch("/api/einstellungen", json={"modelle": {"jobsuche": "opus"}})

    assert r.status_code == 200
    assert r.json()["modelle"]["jobsuche"] == "opus"
    # Teil-Save: die übrigen fünf Funktionen bleiben beim Standard (Lehre Phase 87).
    assert r.json()["modelle"]["company-fit"] == "sonnet"


# ── 3. Fable und Unbekanntes -> 422, nichts wird gespeichert ─────────────────────────────────
def test_patch_modelle_fable_ist_422_und_db_unveraendert(session, client):
    _reset_einstellungen(session)
    client.patch("/api/einstellungen", json={"modelle": {"jobsuche": "opus"}})
    vorher = _modelle_roh(session)

    r = client.patch("/api/einstellungen", json={"modelle": {"jobsuche": "fable", "beirat": "haiku"}})

    assert r.status_code == 422
    # Die Erlaubnisliste kommt aus MODELLE und nennt Fable nicht (nur der abgelehnte Wert steht
    # am Ende der Meldung).
    assert "muss opus, sonnet oder haiku sein" in r.json()["detail"]
    # Auch der erlaubte Teil derselben Anfrage (beirat -> haiku) wurde nicht übernommen.
    assert _modelle_roh(session) == vorher
    assert client.get("/api/einstellungen").json()["modelle"]["jobsuche"] == "opus"


def test_patch_modelle_unbekannter_alias_ist_422_und_nennt_nur_erlaubte_aliase(session, client):
    _reset_einstellungen(session)

    r = client.patch("/api/einstellungen", json={"modelle": {"jobsuche": "gpt5"}})

    assert r.status_code == 422
    meldung = r.json()["detail"]
    for alias in ("opus", "sonnet", "haiku"):
        assert alias in meldung, f"Meldung nennt nicht alle erlaubten Aliase: {meldung!r}"
    assert "fable" not in meldung.lower(), f"Meldung nennt Fable: {meldung!r}"


# ── 4. modell_fuer_kind / modell_fuer_beirat lesen den gespeicherten Alias ──────────────────
def test_modell_fuer_kind_und_beirat_geben_gespeicherten_alias(session, client):
    _reset_einstellungen(session)
    client.patch("/api/einstellungen", json={"modelle": {"jobsuche": "opus", "beirat": "haiku"}})

    from app import agent_runner

    assert agent_runner.modell_fuer_kind("jobsuche") == "opus"
    assert agent_runner.modell_fuer_beirat() == "haiku"
    # kind ohne Kern-Funktion (z. B. "profil-einlesen") bleibt unverändert -> None.
    assert agent_runner.modell_fuer_kind("profil-einlesen") is None


def test_modell_fuer_kind_ohne_gespeicherten_wert_faellt_auf_standard_zurueck(session, client):
    _reset_einstellungen(session)
    client.get("/api/einstellungen")   # legt die Zeile mit dem Standardmodell an

    from app import agent_runner

    assert agent_runner.modell_fuer_kind("jobsuche") == agent_runner.MODELL_STANDARD == "sonnet"


# ── 5. Früher gespeichertes Fable läuft mit sonnet ───────────────────────────────────────────
def test_gespeichertes_fable_laeuft_in_runner_und_beirat_mit_sonnet(session, client):
    _modelle_roh_setzen(session, client, {
        "jobsuche": "fable", "company-fit": "fable", "cv-match": "opus",
        "ats-scan": "fable", "anschreiben": "haiku", "beirat": "fable"})

    from app import agent_runner

    # Jede der fünf Runner-Funktionen (die Such-kinds erben die jobsuche-Wahl) und der Beirat:
    # Fable wird zu Sonnet, erlaubte Wahlen bleiben, wie sie sind.
    assert agent_runner.modell_fuer_kind("jobsuche") == "sonnet"
    assert agent_runner.modell_fuer_kind("zielfirmen-sweep") == "sonnet"   # erbt die jobsuche-Wahl
    assert agent_runner.modell_fuer_kind("firma-pruefen") == "sonnet"
    assert agent_runner.modell_fuer_kind("cv-match") == "opus"
    assert agent_runner.modell_fuer_kind("cv-erstellen") == "sonnet"
    assert agent_runner.modell_fuer_kind("anschreiben-erstellen") == "haiku"
    assert agent_runner.modell_fuer_beirat() == "sonnet"


def test_gespeichertes_fable_erreicht_den_cli_aufruf_nie(session, client):
    _modelle_roh_setzen(session, client, {"jobsuche": "fable"})

    from app.agent_runner import _argv, modell_fuer_kind

    # So baut `_run_task` den Aufruf: der Alias kommt aus modell_fuer_kind.
    argv = _argv("x", "jobsuche", modell_fuer_kind("jobsuche"))

    assert argv[argv.index("--model") + 1] == "sonnet"
    assert "fable" not in argv


def test_gespeichertes_fable_laeuft_in_der_beirats_debatte_mit_sonnet(session, client,
                                                                       monkeypatch, tmp_path):
    """Der Beirat ruft die CLI nicht über den Runner, sondern über `beirat_engine`; die Debatte
    legt `modell_fuer_beirat()` über das Frontmatter-`model` jeder Persona."""
    import beirat_engine

    monkeypatch.setattr(beirat_engine, "DATEN_DIR", tmp_path / "beirat_test")   # data/beirat bleibt unberührt
    _modelle_roh_setzen(session, client, {"beirat": "fable"})

    d = beirat_engine.Debatte(
        thema="Testfrage für den Beirat (synthetisch)", kontext="", min_beitraege=2,
        teilnehmer_ids=None, provider="anthropic", openai_model="gpt-4o-mini", modus="frei",
    )

    assert d.mitglieder, "keine Beirats-Personas gefunden, der Test prüfte nichts"
    assert {m["model"] for m in d.mitglieder.values()} == {"sonnet"}


def test_unbekannter_gespeicherter_wert_laeuft_mit_sonnet(session, client):
    # Von Hand geänderte Zeile oder Altbestand: weder ein Alias der Auswahl noch eine Modell-ID.
    _modelle_roh_setzen(session, client, {"jobsuche": "gpt5", "company-fit": "claude-opus-5-5"})

    from app import agent_runner

    assert agent_runner.modell_fuer_kind("jobsuche") == "sonnet"
    assert agent_runner.modell_fuer_kind("firma-pruefen") == "sonnet"


def test_get_zeigt_wirksame_modelle_statt_gespeichertem_fable(session, client):
    _modelle_roh_setzen(session, client, {"jobsuche": "fable", "company-fit": "opus", "beirat": "fable"})

    r = client.get("/api/einstellungen")

    assert r.status_code == 200
    modelle = r.json()["modelle"]
    assert modelle["jobsuche"] == "sonnet"
    assert modelle["beirat"] == "sonnet"
    assert modelle["company-fit"] == "opus"
    # Jeder angezeigte Wert steht in der Auswahl (sonst zeigte das Auswahlfeld einen Wert, den es
    # dort nicht gibt).
    assert set(modelle.values()) <= {o["alias"] for o in r.json()["modell_optionen"]}
    # Lesen schreibt nie: die gespeicherte Zeile behält ihren Wert.
    assert _modelle_roh(session)["jobsuche"] == "fable"


def test_karte_kann_nach_altem_fable_ohne_fehler_speichern(session, client):
    _modelle_roh_setzen(session, client, {"jobsuche": "fable"})
    angezeigt = client.get("/api/einstellungen").json()["modelle"]

    # Das schickt die Einstellungen-Karte beim Speichern: alle angezeigten Werte.
    r = client.patch("/api/einstellungen", json={"modelle": angezeigt})

    assert r.status_code == 200
    assert r.json()["modelle"]["jobsuche"] == "sonnet"
    assert _modelle_roh(session)["jobsuche"] == "sonnet"   # das alte Fable ist damit auch aus der Zeile weg


# ── 6. wirksames_modell: Einheit und Log ───────────────────────────────────────────────────
@pytest.mark.parametrize("alias", ["opus", "sonnet", "haiku"])
def test_wirksames_modell_laesst_erlaubte_aliase_durch(alias, capsys):
    from app import agent_runner

    assert agent_runner.wirksames_modell(alias) == alias
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("wert", [
    None, "", "fable", "Fable", " fable ", "claude-fable-5-1", "claude-sonnet-5", "gpt5", 5, ["opus"],
])
def test_wirksames_modell_faellt_bei_leer_gesperrt_und_unbekannt_auf_standard(wert):
    from app import agent_runner

    assert agent_runner.wirksames_modell(wert) == agent_runner.MODELL_STANDARD == "sonnet"


def test_rueckfall_loggt_hoechstens_einmal_je_wert(capsys):
    from app import agent_runner

    for _ in range(3):
        agent_runner.wirksames_modell("fable")
    agent_runner.wirksames_modell("gpt5")
    agent_runner.wirksames_modell("gpt5")
    agent_runner.wirksames_modell(None)       # nichts gewählt: Normalfall, keine Zeile
    agent_runner.wirksames_modell("sonnet")   # erlaubt: keine Zeile

    zeilen = [z for z in capsys.readouterr().out.splitlines() if z.strip()]
    assert len(zeilen) == 2, zeilen
    assert zeilen[0].startswith("[agent-runner]")
    assert "'fable'" in zeilen[0] and "gesperrt" in zeilen[0]
    assert "'gpt5'" in zeilen[1] and "unbekannt" in zeilen[1]
    assert all("'sonnet'" in z for z in zeilen)   # die Zeile nennt auch, womit stattdessen gelaufen wird


# ── 7. Wächter ───────────────────────────────────────────────────────────────────────────────
def test_alle_prompts_modelle_sind_erlaubte_aliase():
    """Eine feste Modell-Angabe in PROMPTS geht an `--model`, ohne `wirksames_modell` zu
    durchlaufen. Damit die Fable-Regel dort nicht unterlaufen werden kann (und keine feste
    Modell-ID wie `claude-sonnet-5` auf einer alten Version hängen bleibt), muss sie ein Alias
    der Auswahl sein."""
    from app import agent_runner

    for kind, spec in agent_runner.PROMPTS.items():
        if "model" in spec:
            assert spec["model"] in agent_runner.MODELL_ALIASE, (
                f"PROMPTS[{kind!r}]['model'] = {spec['model']!r} ist kein erlaubter Alias "
                f"({', '.join(agent_runner.MODELL_ALIASE)})")
    assert agent_runner.PROMPTS["job-frage"]["model"] == "sonnet"


def test_gesperrte_und_waehlbare_modelle_ueberschneiden_sich_nie():
    from app import agent_runner

    # Die Regel selbst: Wer sie aufheben will, ändert bewusst auch diese Zeile.
    assert "fable" in agent_runner.GESPERRTE_MODELLE
    assert set(agent_runner.GESPERRTE_MODELLE).isdisjoint(agent_runner.MODELL_ALIASE)
    assert not any("fable" in m["label"].lower() for m in agent_runner.MODELLE)
    # Der Standard ist wählbar, sonst wäre der Rückfall selbst ein unzulässiger Wert.
    assert agent_runner.MODELL_STANDARD in agent_runner.MODELL_ALIASE


# ── 8. _argv setzt --model <alias> ───────────────────────────────────────────────────────────
def test_argv_mit_alias_enthaelt_model_alias():
    from app.agent_runner import _argv

    argv = _argv("x", "jobsuche", "opus")

    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "opus"


def test_argv_job_frage_nutzt_den_kurznamen_sonnet():
    from app.agent_runner import _argv

    argv = _argv("x", "job-frage")

    assert argv[argv.index("--model") + 1] == "sonnet"


def test_jeder_claude_lauf_nennt_ein_erlaubtes_modell(session, client):
    """P2-59: Kein CLI-Aufruf ohne `--model`. Läufe ohne eigene Funktion in der Modellwahl
    (z. B. email-check) liefen sonst mit dem CLI-Standard der Installation, der auch Fable sein
    kann. Geprüft über den echten Aufrufweg (`modell_fuer_kind` als Override, wie in `_run`)."""
    from app.agent_runner import MODELL_ALIASE, PROMPTS, _argv, modell_fuer_kind

    _reset_einstellungen(session)
    claude_laeufe = [k for k, spec in PROMPTS.items() if not spec.get("local_cmd")]
    assert "email-check" in claude_laeufe   # ein Lauf ohne Funktion ist wirklich dabei
    for kind in claude_laeufe:
        argv = _argv("x", kind, modell_fuer_kind(kind))
        assert argv.count("--model") == 1, kind
        assert argv[argv.index("--model") + 1] in MODELL_ALIASE, kind
    assert _argv("x", "email-check")[_argv("x", "email-check").index("--model") + 1] == "sonnet"


# ── Altwerte opus/haiku bleiben gültig (keine Migration) ─────────────────────────────────────
def test_altwerte_opus_und_haiku_bleiben_gueltige_aliase(session, client):
    _reset_einstellungen(session)

    r = client.patch("/api/einstellungen",
                      json={"modelle": {"jobsuche": "opus", "company-fit": "haiku"}})

    assert r.status_code == 200
    assert r.json()["modelle"]["jobsuche"] == "opus"
    assert r.json()["modelle"]["company-fit"] == "haiku"
    assert "opus" in {o["alias"] for o in r.json()["modell_optionen"]}
    assert "haiku" in {o["alias"] for o in r.json()["modell_optionen"]}
