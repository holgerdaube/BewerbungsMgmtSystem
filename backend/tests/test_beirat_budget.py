"""Phase 62A (P1-5) — Budget-Guard + Not-Aus muessen jetzt auch fuer die Beirats-Einstiege
gelten. Regressionstests fuer die Luecke aus tasks/code_review_2026-07-25.md: 72 echte
Beirats-Laeufe liefen fuer 129,62 $ an `_guard_tagesbudget()` vorbei, weil weder
`beirat_debatte_starten` noch `_beirat_stellen_check_starten` ihn aufriefen.

Wie in conftest.py beschrieben: KEINE app.*/pipeline.*-Importe auf Modulebene, nur in
Testfunktionen/Fixtures. Nutzt `client`/`session`/`seed` aus conftest.py.

B1 (spec_phase62, Invariante): KEIN Test hier darf einen echten Beirats-Lauf ausloesen —
`beirat_engine.debatte_starten` wird deshalb in JEDEM Test dieser Datei durch eine folgenlose
Fake-Funktion ersetzt (Fixture `_kein_echter_beirat_start` unten, autouse). Das gilt auch fuer
die 409-Faelle: dort blockt der Guard zwar schon VOR dem Engine-Aufruf (das ist ja gerade der
Fix), aber die Fake-Funktion ist ein zusaetzliches Sicherheitsnetz fuer den Fall, dass der
Guard das nicht tut, wie erwartet.
"""
import types

import pytest


def _fake_debatte_starten(**kwargs):
    """Ersatz fuer beirat_engine.debatte_starten (s. Fixture unten). Liefert nur die Felder,
    die die beiden Endpunkte aus dem Rueckgabewert lesen (main.py::beirat_debatte_starten und
    ::beirat_stellen_check) — ohne jede Nebenwirkung: keine DEBATTEN-Registrierung, keine
    AgentTask-Zeile, kein `asyncio.create_task`, also garantiert kein echter Lauf (B1)."""
    min_beitraege = int(kwargs.get("min_beitraege") or 8)
    return types.SimpleNamespace(
        id="test_fake_debatte",
        min_beitraege=min_beitraege,
        max_beitraege=int(min_beitraege * 1.5) + 2,
        teilnehmer=[{"id": "beirat-vera-brandt"}],
    )


@pytest.fixture(autouse=True)
def _kein_echter_beirat_start(monkeypatch):
    """B1-Sicherheitsnetz fuer ALLE Tests dieser Datei (nicht nur die Gegenprobe): der Modul-
    Import in main.py passiert je Endpunkt-Aufruf frisch (`import beirat_engine as be`) — das
    ist aber nur ein Attribut-Lookup auf das EINE gecachte Modulobjekt in sys.modules. Ein
    Attribut-Patch auf dieses Objekt (statt auf eine lokale Kopie) wirkt deshalb zuverlaessig
    an beiden Aufrufstellen. Modul-Import bewusst HIER (Fixture-Koerper), nicht auf Datei-
    ebene — beirat_engine zieht transitiv app.agent_runner/app.db/app.models nach, s.
    conftest.py-Regel."""
    import beirat_engine
    monkeypatch.setattr(beirat_engine, "debatte_starten", _fake_debatte_starten)


@pytest.fixture(autouse=True)
def _budget_limit_aufraeumen(session):
    """Autouse-TEARDOWN: raeumt die BudgetLimit-Zeile 'claude-runs' nach JEDEM Test dieser
    Datei wieder weg. Grund: `_db_ready` (conftest.py) ist session-scoped — alle Testdateien
    EINES pytest-Laufs teilen sich dieselbe tmp-DB. Vor Phase 62A existierte in keinem Test
    eine BudgetLimit-Zeile (verifiziert per grep). Liesse ein Testfall hier active=False oder
    ein sehr niedriges Tageslimit stehen, wuerde das ohne Aufraeumen jeden SPAETER laufenden
    Test blocken, der ueber denselben Guard laeuft (create_task literal main.py:767,
    job_chat_ask main.py:897) — Test-Isolation, nicht nur Kosmetik."""
    yield
    from sqlmodel import select
    from app.models import BudgetLimit
    row = session.exec(select(BudgetLimit).where(BudgetLimit.provider == "claude-runs")).first()
    if row:
        session.delete(row)
        session.commit()


def _budget_limit_setzen(session, *, active=True, enforcement="hart",
                         daily_limit_usd=100.0, monthly_limit_usd=None,
                         max_runs_per_day=100000):
    """BudgetLimit-Zeile provider='claude-runs' anlegen/aktualisieren (s. agent_runner.
    _claude_limits — NICHT provider='claude', das ist das Fixkosten-Abo aus budgets.yaml,
    s. tasks/lessons.md). Setzt IMMER alle steuerungsrelevanten Felder explizit (kein Teil-
    Update), damit einzelne Tests nicht von der Reihenfolge/dem Vorzustand abhaengen.
    `max_runs_per_day` bewusst hoch (100000): die Laeufe-Zaehlung zaehlt ALLE AgentTask-Zeilen
    der session-weiten tmp-DB seit lokaler Mitternacht (agent_runner.tagesverbrauch) — ein
    niedriger Wert koennte je nach Testreihenfolge/anderen Testdateien ungewollt zuerst greifen
    und den eigentlich zu pruefenden Pfad (Not-Aus bzw. Tagesbudget-$) verdecken."""
    from sqlmodel import select
    from app.models import BudgetLimit
    row = session.exec(select(BudgetLimit).where(BudgetLimit.provider == "claude-runs")).first()
    if not row:
        row = BudgetLimit(provider="claude-runs")
    row.active = active
    row.enforcement = enforcement
    row.daily_limit_usd = daily_limit_usd
    row.monthly_limit_usd = monthly_limit_usd
    row.max_runs_per_day = max_runs_per_day
    session.add(row)
    session.commit()
    return row


# ── Not-Aus (active=False) — muss laut Kommentar in _guard_tagesbudget "IMMER" blocken ──────

def test_stellen_check_notaus_liefert_409(client, session, seed):
    """Vor Phase 62A rief _beirat_stellen_check_starten() den Guard gar nicht auf — der
    dedizierte Endpunkt POST /api/beirat/stellen-check (Frontend: BeiratCheckButton.tsx) lief
    am Not-Aus komplett vorbei."""
    _budget_limit_setzen(session, active=False)
    job_id = seed["jobs"][0].id
    r = client.post("/api/beirat/stellen-check", json={"job_id": job_id})
    assert r.status_code == 409
    assert "pausiert" in r.json()["detail"]


def test_debatte_notaus_liefert_409(client, session):
    """Dasselbe fuer den freien Debatten-Einstieg (Frontend: Beirat.tsx) — vor Phase 62A hatte
    beirat_debatte_starten() nicht einmal eine Session-Dependency, geschweige denn den Guard."""
    _budget_limit_setzen(session, active=False)
    r = client.post("/api/beirat/debatten", json={"thema": "Testfrage fuer den Beirat"})
    assert r.status_code == 409
    assert "pausiert" in r.json()["detail"]


# ── Tageslimit ueberschritten (unabhaengig vom Not-Aus) ─────────────────────────────────────

def test_stellen_check_tageslimit_ueberschritten_liefert_409(client, session, seed):
    """Zweiter Verstoss-Typ (neben active=False): das $-Tageslimit selbst. `max_runs_per_day`
    bleibt hoch gesetzt, damit garantiert der $-Zweig (nicht der Laeufe-Zaehler) den Block
    ausloest — Beleg, dass wirklich `agent_runner.budget_ueberschritten()` durchgereicht wird,
    nicht nur die active-Flagge."""
    from app.models import AgentTask
    _budget_limit_setzen(session, active=True, enforcement="hart", daily_limit_usd=0.01,
                         max_runs_per_day=100000)
    session.add(AgentTask(kind="test-tageslimit-fixture", cost_usd=50.0))
    session.commit()
    job_id = seed["jobs"][0].id
    r = client.post("/api/beirat/stellen-check", json={"job_id": job_id})
    assert r.status_code == 409
    assert "Tagesbudget" in r.json()["detail"]


# ── Gegenprobe (B1): ohne Limit-Verletzung darf der Guard NICHT blockieren ──────────────────

def test_stellen_check_gegenprobe_ohne_verletzung_blockt_nicht(client, session, seed):
    """Beweis, dass Phase 62A keine Uebersicherung einbaut: mit gesundem Budget kommt der
    Request bis zum (gefakten, s. _kein_echter_beirat_start) Engine-Start durch."""
    _budget_limit_setzen(session, active=True, enforcement="hart", daily_limit_usd=100.0,
                         max_runs_per_day=100000)
    job_id = seed["jobs"][0].id
    r = client.post("/api/beirat/stellen-check", json={"job_id": job_id})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "test_fake_debatte"
    assert "company_fit_fehlt" in body


def test_debatte_gegenprobe_ohne_verletzung_blockt_nicht(client, session):
    """Dieselbe Gegenprobe fuer den freien Debatten-Einstieg."""
    _budget_limit_setzen(session, active=True, enforcement="hart", daily_limit_usd=100.0,
                         max_runs_per_day=100000)
    r = client.post("/api/beirat/debatten", json={"thema": "Testfrage fuer den Beirat"})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "test_fake_debatte"
    assert body["teilnehmer"] == ["beirat-vera-brandt"]
