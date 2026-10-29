"""P2-78 — `budget.seed_limits()`: Perplexity ist aus `SEED` raus, seine Limit-Zeile wird aus
bestehenden Installationen aufgeräumt. Kosten bleiben.

Hintergrund: Bis 1.7.0 legte `seed_limits()` die Zeile „Perplexity (Suche)“ in jeder Datenbank an,
obwohl kein Ablauf den Dienst je aufrief. Seit P2-78 steht der Anbieter nicht mehr in `SEED`,
sondern in `ABGELOESTE_ANBIETER`. `seed_limits()` löscht dessen `BudgetLimit`-Zeile. Bis zum
Nachtrag galt das nur, wenn es keine `ApiCost`-Zeile zu ihm gibt. Nachtrag 16.10.2026 (Wunsch): auch mit Kosten (Messläufe aus
dem Juli), denn die Steuerung braucht niemand mehr. Eine `ApiCost`-Zeile wird nie gelöscht, der
Bericht zeigt vorhandene Kosten weiter, nur ohne Limit.

Wie in conftest.py beschrieben: KEINE app.*/pipeline.*-Importe auf Modulebene, nur in
Testfunktionen/Fixtures. Jeder Test läuft gegen eine EIGENE Datenbankdatei unter `tmp_path`
(Muster test_digest_beworben.py): `budget.engine` zeigt auf sie, `budget.init_db` ist stillgelegt
(die Tabellen legt die Fixture an), `budget.BUDGETS_YAML` zeigt auf eine fehlende Datei, damit
`report()` mit den Standardwerten rechnet. So berührt kein Test die session-weite Test-DB der
übrigen Suite und nie die echte `data/`.
"""
import pytest


@pytest.fixture()
def budget_db(tmp_path, monkeypatch):
    """Frische, leere Datenbank nur für diesen Test. Liefert die Engine."""
    from sqlmodel import SQLModel, create_engine

    import app.models  # noqa: F401  — Import registriert die Tabellen in SQLModel.metadata
    from pipeline import budget

    eng = create_engine("sqlite:///" + str(tmp_path / "budget.sqlite"))
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(budget, "engine", eng)
    monkeypatch.setattr(budget, "init_db", lambda: None)
    monkeypatch.setattr(budget, "BUDGETS_YAML", tmp_path / "keine_budgets.yaml")
    return eng


# ── Hilfen ────────────────────────────────────────────────────────────────────────────
def _limit_anlegen(eng, provider, **felder):
    """BudgetLimit-Zeile anlegen, wie es ein 1.7.0-Seed für Perplexity getan hat (Standard)."""
    from sqlmodel import Session

    from app.models import BudgetLimit

    werte = {"label": "Perplexity (Suche)", "daily_limit_usd": 0.50, "monthly_limit_usd": 5.00,
             "enforcement": "hart"}
    werte.update(felder)
    with Session(eng) as s:
        s.add(BudgetLimit(provider=provider, **werte))
        s.commit()


def _kosten_anlegen(eng, provider, cost_usd=0.12, datum=None, source="metered"):
    """ApiCost-Zeile anlegen (Standard: heute, damit `report()` den Betrag unter „heute“ führt)."""
    from sqlmodel import Session

    from app.models import ApiCost
    from pipeline import budget

    with Session(eng) as s:
        s.add(ApiCost(provider=provider, date=datum or budget._heute(), cost_usd=cost_usd,
                      calls=3, source=source))
        s.commit()


def _limit_zeilen(eng):
    """Alle BudgetLimit-Zeilen als sortierte, vergleichbare Tupel (ohne Zeitstempel)."""
    from sqlmodel import Session, select

    from app.models import BudgetLimit

    with Session(eng) as s:
        return sorted(
            (b.provider, b.label, b.daily_limit_usd, b.monthly_limit_usd, b.enforcement,
             b.active, b.max_runs_per_day)
            for b in s.exec(select(BudgetLimit)).all())


def _kosten_zeilen(eng):
    """Alle ApiCost-Zeilen als sortierte, vergleichbare Tupel."""
    from sqlmodel import Session, select

    from app.models import ApiCost

    with Session(eng) as s:
        return sorted((c.provider, c.date, c.cost_usd, c.calls, c.source)
                      for c in s.exec(select(ApiCost)).all())


def _limit_anbieter(eng):
    return {z[0] for z in _limit_zeilen(eng)}


def _report_anbieter(budget):
    return {p["provider"]: p for p in budget.report()["providers"]}


# ── 1. Frische Datenbank ──────────────────────────────────────────────────────────────
def test_frische_datenbank_hat_keine_perplexity_zeile(budget_db):
    from pipeline import budget

    budget.seed_limits()

    anbieter = _limit_anbieter(budget_db)
    assert "perplexity" not in anbieter
    # Die übrigen SEED-Zeilen sind da, mit den Startwerten aus SEED.
    assert anbieter == {e["provider"] for e in budget.SEED}
    zeilen = {z[0]: z for z in _limit_zeilen(budget_db)}
    for e in budget.SEED:
        assert zeilen[e["provider"]][1:5] == (e["label"], e["daily_limit_usd"],
                                              e["monthly_limit_usd"], e["enforcement"])


def test_seed_enthaelt_keinen_abgeloesten_anbieter():
    """Wer einen Anbieter in `ABGELOESTE_ANBIETER` einträgt, muss ihn aus `SEED` nehmen. Stünde
    er in beiden, legte `seed_limits()` die Zeile bei jedem Aufruf neu an."""
    from pipeline import budget

    assert "perplexity" in budget.ABGELOESTE_ANBIETER
    assert not {e["provider"] for e in budget.SEED} & set(budget.ABGELOESTE_ANBIETER)


# ── 2. Zeile ohne Kosten wird aufgeräumt ──────────────────────────────────────────────
def test_perplexity_zeile_ohne_kosten_wird_geloescht(budget_db):
    """Der Zustand einer Installation mit 1.7.0: Zeile da, nie ein Cent Kosten."""
    from pipeline import budget

    _limit_anlegen(budget_db, "perplexity")
    assert "perplexity" in _limit_anbieter(budget_db)

    budget.seed_limits()

    assert "perplexity" not in _limit_anbieter(budget_db)
    assert _kosten_zeilen(budget_db) == []


def test_ensure_budget_raeumt_ebenfalls_auf_und_blockiert_nichts(budget_db):
    """`ensure_budget()` ruft `seed_limits()` selbst. Ohne Zeile gilt „kein Limit“ = erlaubt."""
    from pipeline import budget

    _limit_anlegen(budget_db, "perplexity")

    antwort = budget.ensure_budget("perplexity", 0.05)

    assert antwort["allowed"] is True and antwort["limits"] is None
    assert "perplexity" not in _limit_anbieter(budget_db)


# ── 3. Zeile mit Kosten: Limit weg, Kosten bleiben ────────────────────────────────────
def test_perplexity_zeile_mit_kosten_verliert_limit_kosten_bleiben(budget_db):
    """Messläufe aus dem Juli: Die Steuerung verschwindet, die Kosten bleiben (Nachtrag
    16.10.2026)."""
    from pipeline import budget

    _limit_anlegen(budget_db, "perplexity")
    _kosten_anlegen(budget_db, "perplexity", cost_usd=0.12, datum="2026-07-10")
    vorher_kosten = _kosten_zeilen(budget_db)

    budget.seed_limits()
    budget.seed_limits()          # ein zweiter Lauf ändert nichts mehr

    assert "perplexity" not in _limit_anbieter(budget_db)
    assert _kosten_zeilen(budget_db) == vorher_kosten
    assert vorher_kosten == [("perplexity", "2026-07-10", 0.12, 3, "metered")]


def test_kosten_ohne_limit_zeile_bleiben_und_es_entsteht_keine_neue_zeile(budget_db):
    """Hat jemand die Zeile von Hand gelöscht, bleibt nur die Geschichte: `seed_limits()` legt
    Perplexity nicht wieder an (es steht nicht mehr in `SEED`) und fasst die Kosten nicht an."""
    from pipeline import budget

    _kosten_anlegen(budget_db, "perplexity", datum="2026-07-10")

    budget.seed_limits()

    assert "perplexity" not in _limit_anbieter(budget_db)
    assert _kosten_zeilen(budget_db) == [("perplexity", "2026-07-10", 0.12, 3, "metered")]


# ── 4. report() nennt perplexity nie, Kosten bleiben gespeichert ──────────────────────
def test_report_nennt_perplexity_nicht_ohne_kosten(budget_db):
    from pipeline import budget

    _limit_anlegen(budget_db, "perplexity")

    anbieter = _report_anbieter(budget)

    assert "perplexity" not in anbieter
    assert {"apify", "claude-runs"} <= set(anbieter)          # die übrigen Karten bleiben


def test_report_blendet_perplexity_auch_mit_kosten_aus(budget_db):
    """Nachtrag 16.10.2026: weder Tabelle „Dienste“ noch „Budget-Steuerung“ zeigen Perplexity,
    die Kosten bleiben gespeichert. Ausgeblendete Kosten zählen auch in den Summen nicht mit."""
    from pipeline import budget

    _limit_anlegen(budget_db, "perplexity")
    _kosten_anlegen(budget_db, "perplexity", cost_usd=0.12)
    vorher_kosten = _kosten_zeilen(budget_db)

    bericht = budget.report()
    anbieter = {p["provider"]: p for p in bericht["providers"] if p["art"] == "verbrauch"}

    assert "perplexity" not in anbieter
    assert {"apify", "claude-runs"} <= set(anbieter)
    assert bericht["totals"]["heute_usd"] == round(sum(p["heute_usd"] for p in bericht["providers"]), 4)
    assert _kosten_zeilen(budget_db) == vorher_kosten


# ── 5. Andere Anbieter unberührt, Wiederholung ändert nichts ──────────────────────────
def test_andere_anbieter_bleiben_unberuehrt_und_zwei_aufrufe_ergeben_denselben_stand(budget_db):
    from pipeline import budget

    # Apify mit von Hand geänderten Werten: SEED darf nie überschreiben.
    _limit_anlegen(budget_db, "apify", label="Mein Apify", daily_limit_usd=1.23,
                   monthly_limit_usd=None, enforcement="weich", active=False)
    # Ein Anbieter außerhalb von SEED und ABGELOESTE_ANBIETER: bleibt samt Kosten stehen.
    _limit_anlegen(budget_db, "hedy", label="Hedy", daily_limit_usd=2.0, monthly_limit_usd=9.0)
    _kosten_anlegen(budget_db, "hedy", cost_usd=0.5, datum="2026-08-01")
    _kosten_anlegen(budget_db, "apify", cost_usd=0.07, datum="2026-08-02", source="sync")
    # Dazu die abgelöste Zeile ohne Kosten, die aufgeräumt werden soll.
    _limit_anlegen(budget_db, "perplexity")

    budget.seed_limits()
    nach_erstem = (_limit_zeilen(budget_db), _kosten_zeilen(budget_db))
    budget.seed_limits()
    nach_zweitem = (_limit_zeilen(budget_db), _kosten_zeilen(budget_db))

    assert nach_erstem == nach_zweitem
    limits = {z[0]: z for z in nach_erstem[0]}
    assert set(limits) == {"apify", "hedy", "claude-runs"}     # perplexity weg, claude-runs neu
    assert limits["apify"][1:] == ("Mein Apify", 1.23, None, "weich", False, None)
    assert limits["hedy"][1:] == ("Hedy", 2.0, 9.0, "hart", True, None)
    assert nach_erstem[1] == [("apify", "2026-08-02", 0.07, 3, "sync"),
                              ("hedy", "2026-08-01", 0.5, 3, "metered")]


def test_aufraeumen_und_anlegen_laufen_in_einem_commit(budget_db):
    """Vertrag B: Aufräumen und Anlegen fehlender Zeilen teilen sich einen Commit."""
    from sqlalchemy import event

    from pipeline import budget

    _limit_anlegen(budget_db, "perplexity")                    # soll weg
    # apify und claude-runs fehlen noch: sollen im selben Aufruf entstehen
    commits = []
    event.listen(budget_db, "commit", lambda verbindung: commits.append(1))

    budget.seed_limits()

    assert len(commits) == 1
    assert _limit_anbieter(budget_db) == {e["provider"] for e in budget.SEED}
