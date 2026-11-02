#!/usr/bin/env python3
"""Budget-Reporting und -Steuerung für alle kostenpflichtigen Dienste (Phase 10).

Zwei Aufgaben:
  * **Reporting** — was kostet welcher Dienst heute / diesen Monat / im Jahr?
  * **Steuerung** — `ensure_budget()` prüft VOR dem Geldausgeben gegen die Limits aus der DB
    und blockiert (`hart`) oder warnt (`weich`).

Drei Kostenquellen:
  | source    | woher                                   | Beispiel                          |
  |-----------|-----------------------------------------|-----------------------------------|
  | `sync`    | Usage-API des Anbieters (die Wahrheit)  | Apify daily usage                 |
  | `metered` | lokal beim Aufruf protokolliert         | `pipeline.budget record` von Hand |
  | `fix`     | Abo aus `config/budgets.yaml`           | Claude-Abo (nie blockiert)        |

ZUKUNFTSREGEL für jeden neuen Pay-per-Call-Client:
  1. Hat der Anbieter eine Usage-API? → `sync_<provider>()` schreiben. Sonst `record()` je Aufruf.
  2. IMMER `ensure_budget(provider, estimated_cost)` aufrufen, BEVOR Geld fließt.
     `allowed == False` → nicht aufrufen, Grund ausgeben (Exit 2 = „Budget erschöpft", kein Fehler).
     `warn == True` → aufrufen, Grund im Bericht erwähnen.
  3. Abos gehören in `config/budgets.yaml`, nicht in die DB.
  4. Neuen Provider in `SEED` ergänzen — sonst ist er in der App nicht steuerbar.

EHRLICHE GRENZE: Die Steuerung wirkt nur auf Aufrufe über die Pipeline-Clients dieser App.
Ausgaben in der Apify-Konsole oder über claude.ai-Connectors sieht sie erst nach dem nächsten
Sync und kann sie nicht verhindern.

CLI (immer aus backend/ heraus):
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.budget sync
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.budget record <provider> <cost_usd> [--calls N] [--note "…"]
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.budget check <provider> [--estimated 0.05]
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.budget report
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

import httpx
import yaml
from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import AgentTask, ApiCost, BudgetLimit

from app import zeit

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent   # Bewerbung_Mgmt_System/
BUDGETS_YAML = PROJECT_ROOT / "config" / "budgets.yaml"

APIFY_API = "https://api.apify.com/v2"

# Startwerte. Bestehende Rows werden NIE überschrieben — ab dann pflegt der Nutzer sie in der App.
SEED = [
    {"provider": "apify", "label": "Apify (Job-Scraper)",
     "daily_limit_usd": 0.50, "monthly_limit_usd": 5.00, "enforcement": "hart"},
    # Phase 54 — virtuelles Geld (Claude-Abo, keine echte Rechnung). Startzustand "weich":
    # nichts blockiert mehr (ausdrücklicher Wunsch), die $100-Schwelle bleibt als
    # Ampel/Sichtbarkeit stehen. Durchsetzung läuft NICHT über ensure_budget(), sondern über
    # das Runner-Gate (agent_runner.budget_ueberschritten) — s. dortigen Docstring-Hinweis.
    # Provider-ID bewusst "claude-runs" (NICHT "claude"): das Fixkosten-Abo unten in
    # config/budgets.yaml belegt "claude" bereits ("Claude (Max-Abo)") — gleiche ID hätte zwei
    # Provider-Objekte mit identischem `provider`-Schlüssel erzeugt (React-Key-Kollision in
    # Budget.tsx, dazu inhaltlich zwei völlig verschiedene Dinge: Abo-Fixkosten vs. Läufe-Limit).
    {"provider": "claude-runs", "label": "Claude (Agent-Läufe)",
     "daily_limit_usd": 100.0, "monthly_limit_usd": None, "enforcement": "weich"},
]

# P2-78: Anbieter, die das BMS nie mehr aufruft. Ihre Limit-Zeile steht in bestehenden
# Installationen noch in der Datenbank (ein früheres `seed_limits()` hat sie angelegt) und
# erschiene sonst für immer als Karte unter „Budget-Steuerung“. `seed_limits()` löscht diese
# Zeile. Eine `ApiCost`-Zeile wird hier nie gelöscht: Hat der Anbieter Kosten (Messläufe aus der
# Zeit, als es ihn noch gab), bleiben sie gespeichert. `report()` blendet abgelöste Anbieter aber
# ganz aus, weder Tabelle „Dienste“ noch „Budget-Steuerung“ zeigen sie (Nachträge 16.10.2026 auf
# Wunsch; vorher blieb die Zeile mit Kosten stehen). Die Summen ändert das nicht.
# Perplexity: Phase 17 endete mit NO-GO, das Modul `perplexity_search.py` ist seit P2-78
# entfernt. Der Anbieter steht deshalb auch nicht mehr in `SEED`.
ABGELOESTE_ANBIETER = ("perplexity",)


def _die(msg: str, code: int = 1) -> "NoReturn":   # noqa: F821
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _usd(x: float) -> str:
    """Kleine Beträge nicht auf $0.00 runden — sonst liest sich ein Limit von 0.001 wie „kein Limit"."""
    return f"${x:.2f}" if abs(x) >= 0.01 else f"${x:.4f}"


def _heute() -> str:
    return datetime.date.today().isoformat()       # LOKALER Tag, wie im Rest des Projekts


def _monatserster() -> str:
    return datetime.date.today().replace(day=1).isoformat()


def _jahreserster() -> str:
    return datetime.date.today().replace(month=1, day=1).isoformat()


def _lokal_datum(utc_naive: datetime.datetime) -> str:
    """Phase 54 — `AgentTask.created_at` (naives UTC) auf den lokalen Kalendertag abbilden,
    damit die Claude-Zeile dieselben Datums-Vergleiche (`_heute()`/`_monatserster()`) nutzen
    kann wie die ApiCost-Rows der anderen Provider (deren `.date` schon lokal ist)."""
    return zeit.lokales_datum(utc_naive).isoformat()


def config() -> dict:
    """budgets.yaml lesen. Fehlt sie oder ist kaputt → sinnvolle Defaults, kein Crash."""
    if not BUDGETS_YAML.exists():
        return {"usd_eur_rate": 0.92, "fixkosten": []}
    try:
        d = yaml.safe_load(BUDGETS_YAML.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        print(f"[budget] WARNUNG: {BUDGETS_YAML.name} unlesbar ({e}) — Fixkosten ignoriert", file=sys.stderr)
        return {"usd_eur_rate": 0.92, "fixkosten": []}
    d.setdefault("usd_eur_rate", 0.92)
    d.setdefault("fixkosten", [])
    return d


# ── Limits ────────────────────────────────────────────────────────────────────────────
def seed_limits() -> None:
    """Fehlende Limit-Rows anlegen und abgelöste aufräumen. Idempotent, überschreibt nie.

    P2-78: Für jeden Anbieter in `ABGELOESTE_ANBIETER` wird die `BudgetLimit`-Zeile gelöscht.
    `ApiCost` wird nie angefasst, vorhandene Kosten bleiben im Bericht sichtbar. Aufräumen und
    Anlegen laufen in einem Commit.
    """
    init_db()
    with Session(engine) as s:
        vorhanden = {b.provider: b for b in s.exec(select(BudgetLimit)).all()}   # provider ist unique
        for provider in ABGELOESTE_ANBIETER:
            if provider in vorhanden:
                s.delete(vorhanden.pop(provider))
        for eintrag in SEED:
            if eintrag["provider"] not in vorhanden:
                s.add(BudgetLimit(**eintrag))
        s.commit()


def _summen(s: Session, provider: str) -> tuple:
    """(heute, laufender Monat, laufendes Jahr) in USD."""
    rows = s.exec(select(ApiCost).where(ApiCost.provider == provider)).all()
    heute, monat, jahr = _heute(), _monatserster(), _jahreserster()
    return (
        round(sum(r.cost_usd or 0 for r in rows if r.date == heute), 4),
        round(sum(r.cost_usd or 0 for r in rows if r.date >= monat), 4),
        round(sum(r.cost_usd or 0 for r in rows if r.date >= jahr), 4),
    )


def ensure_budget(provider: str, estimated_cost: float = 0.0) -> dict:
    """Der Guard. VOR jedem kostenpflichtigen Aufruf zu rufen.

    HINWEIS (Phase 54): `provider="claude-runs"` wird NICHT über diese Funktion durchgesetzt —
    die Läufe-Zählung + die lokale-Mitternacht/Monats-Logik brauchen `AgentTask`, nicht
    `ApiCost`. Durchsetzung läuft über `agent_runner.budget_ueberschritten()`; diese Funktion
    liefert für "claude-runs" nur einen (ungenutzten) Lesepfad, falls je darauf zugegriffen wird.

    Rückgabe: {allowed, warn, grund, spent_today, spent_month, limits}
    Kein Limit gesetzt → allowed. Dienst pausiert → nie erlaubt.
    """
    seed_limits()
    with Session(engine) as s:
        lim = s.exec(select(BudgetLimit).where(BudgetLimit.provider == provider)).first()
        heute, monat, _ = _summen(s, provider)

    if not lim:
        return {"allowed": True, "warn": False, "grund": None,
                "spent_today": heute, "spent_month": monat, "limits": None}

    limits = {"daily_limit_usd": lim.daily_limit_usd, "monthly_limit_usd": lim.monthly_limit_usd,
              "enforcement": lim.enforcement, "active": lim.active}

    if not lim.active:
        return {"allowed": False, "warn": False,
                "grund": f"Dienst '{provider}' ist in der App pausiert",
                "spent_today": heute, "spent_month": monat, "limits": limits}

    grund = None
    if lim.daily_limit_usd is not None and heute + estimated_cost > lim.daily_limit_usd:
        grund = (f"Tageslimit {_usd(lim.daily_limit_usd)} erreicht "
                 f"({_usd(heute)} verbraucht, geschätzt +{_usd(estimated_cost)})")
    elif lim.monthly_limit_usd is not None and monat + estimated_cost > lim.monthly_limit_usd:
        grund = (f"Monatslimit {_usd(lim.monthly_limit_usd)} erreicht "
                 f"({_usd(monat)} verbraucht, geschätzt +{_usd(estimated_cost)})")

    verletzt = grund is not None
    return {"allowed": not (verletzt and lim.enforcement == "hart"),
            "warn": verletzt and lim.enforcement == "weich",
            "grund": grund, "spent_today": heute, "spent_month": monat, "limits": limits}


# ── Erfassen ──────────────────────────────────────────────────────────────────────────
def record(provider: str, cost_usd: float, calls=None, note=None, date=None) -> dict:
    """Einen `metered`-Verbrauch protokollieren (eine Row je Lauf)."""
    init_db()
    with Session(engine) as s:
        row = ApiCost(provider=provider, date=date or _heute(), cost_usd=float(cost_usd),
                      calls=calls, quantity_note=note, source="metered")
        s.add(row)
        s.commit()
        s.refresh(row)
        return {"id": row.id, "provider": provider, "date": row.date, "cost_usd": row.cost_usd}


def sync_apify() -> dict:
    """Echten Apify-Tagesverbrauch ziehen und als `sync`-Rows UPSERTen.

    Ohne Token kein Fehler, sondern eine klare Meldung — der Budget-Report soll auch dann laufen.
    """
    from pipeline.apify_client import ENV_FILE, token_or_none

    tok = token_or_none()
    if not tok:
        return {"ok": False, "rows": 0,
                "fehler": f"APIFY_TOKEN fehlt ({ENV_FILE}) — Apify-Verbrauch nicht abrufbar"}

    zyklen = [None]
    if datetime.date.today().day <= 3:      # Anfang des Monats auch den Vormonat nachziehen
        letzter_vormonat = datetime.date.today().replace(day=1) - datetime.timedelta(days=1)
        zyklen.append(letzter_vormonat.isoformat())

    init_db()
    geschrieben = 0
    try:
        with httpx.Client(timeout=30.0) as cl:
            for datum in zyklen:
                params = {"token": tok}
                if datum:
                    params["date"] = datum
                r = cl.get(f"{APIFY_API}/users/me/usage/monthly", params=params)
                if r.status_code >= 400:
                    # r.text kann den Token nicht enthalten (der steht im Query-String).
                    return {"ok": False, "rows": geschrieben,
                            "fehler": f"Apify-API {r.status_code}: {r.text[:200]}"}
                daten = r.json().get("data", {})
                geschrieben += _upsert_apify_tage(daten)
    except httpx.HTTPError as e:
        return {"ok": False, "rows": geschrieben, "fehler": f"Netzwerkfehler: {type(e).__name__}"}
    return {"ok": True, "rows": geschrieben, "fehler": None}


def _upsert_apify_tage(daten: dict) -> int:
    """`dailyServiceUsages` → eine `sync`-Row je Tag. Logischer Schlüssel: (provider, date, source)."""
    tage = daten.get("dailyServiceUsages") or []
    n = 0
    with Session(engine) as s:
        for tag in tage:
            datum = (tag.get("date") or "")[:10]
            if not datum:
                continue
            # Je-Tag-Feld heißt `totalUsageCreditsUsd` (verifiziert 10.07.2026 gegen die echte
            # API — NICHT `...AfterVolumeDiscount`, das gibt es nur auf Monats-Top-Level).
            kosten = float(tag.get("totalUsageCreditsUsd") or 0.0)
            row = s.exec(select(ApiCost).where(ApiCost.provider == "apify",
                                               ApiCost.date == datum,
                                               ApiCost.source == "sync")).first()
            if row:
                row.cost_usd = kosten
                row.detail_json = json.dumps(tag, ensure_ascii=False)[:4000]
                row.updated_at = datetime.datetime.utcnow()
            else:
                row = ApiCost(provider="apify", date=datum, cost_usd=kosten, source="sync",
                              detail_json=json.dumps(tag, ensure_ascii=False)[:4000])
            s.add(row)
            n += 1
        s.commit()
    return n


# ── Report ────────────────────────────────────────────────────────────────────────────
def _status(prozent_heute, prozent_monat, aktiv: bool) -> str:
    if not aktiv:
        return "pausiert"
    hoechst = max(p for p in (prozent_heute, prozent_monat) if p is not None) if \
        any(p is not None for p in (prozent_heute, prozent_monat)) else 0
    if hoechst >= 100:
        return "over"
    if hoechst >= 80:
        return "warn"
    return "ok"


def _prozent(verbraucht: float, limit):
    return None if not limit else round(verbraucht / limit * 100, 1)


def report() -> dict:
    """Aggregation für `GET /api/budget`. Verbrauchs-Dienste + Fixkosten + Summen."""
    seed_limits()
    cfg = config()
    rate = float(cfg.get("usd_eur_rate") or 0.92)
    heute_iso, monat_iso = _heute(), _monatserster()

    providers = []
    with Session(engine) as s:
        alle = s.exec(select(ApiCost)).all()
        limits = {b.provider: b for b in s.exec(select(BudgetLimit)).all()}
        # P2-78: abgelöste Anbieter nicht zeigen, ihre Kosten bleiben in ApiCost gespeichert.
        namen = sorted((set([r.provider for r in alle]) | set(limits)) - set(ABGELOESTE_ANBIETER))

        letzter_sync = max([r.updated_at for r in alle if r.source == "sync"], default=None)

        alle_tasks = s.exec(select(AgentTask)).all()  # Phase 54 — Quelle für die Claude-Zeile

        for p in namen:
            runs_heute = hinweis = None
            if p == "claude-runs":
                # Verbrauchsquelle Claude = AgentTask.cost_usd (NICHT ApiCost — s. Design-
                # Entscheidung 5 der Phase-54-Spec: eine Quelle der Wahrheit, keine Spiegelung).
                # Gleiche Formeln wie unten, nur über lokal umgerechnete AgentTask-Tage gebaut.
                tage = [(_lokal_datum(t.created_at), t.cost_usd or 0.0) for t in alle_tasks]
                heute = round(sum(c for d, c in tage if d == heute_iso), 4)
                monat = round(sum(c for d, c in tage if d >= monat_iso), 4)
                jahr = round(sum(c for d, c in tage if d >= _jahreserster()), 4)
                grenze = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
                schnitt = round(sum(c for d, c in tage if d >= grenze) / 30, 4)
                tag_im_monat = datetime.date.today().day
                prognose = round(monat / max(tag_im_monat, 1) * 30 * 12, 2)
                calls_monat = sum(1 for d, _ in tage if d >= monat_iso) or None
                runs_heute = sum(1 for d, _ in tage if d == heute_iso)
                hinweis = ("Virtuelle Kosten (Claude-Abo) — Kostenschätzung der CLI, "
                          "verbraucht Abo-Kontingent, keine echte Rechnung")
                from app import ki_anbieter     # P2-86: Unter ChatGPT gibt es keine Kostenschätzung
                if ki_anbieter.aktiv() == ki_anbieter.CHATGPT:
                    hinweis = "Läufe über das ChatGPT-Abo: keine Kosten in USD, es gelten die Grenzen des Abos"
            else:
                rows = [r for r in alle if r.provider == p]
                heute = round(sum(r.cost_usd or 0 for r in rows if r.date == heute_iso), 4)
                monat = round(sum(r.cost_usd or 0 for r in rows if r.date >= monat_iso), 4)
                jahr = round(sum(r.cost_usd or 0 for r in rows if r.date >= _jahreserster()), 4)
                # Ø/Tag über die letzten 30 Tage (nur Tage mit Daten zählen nicht — echte 30-Tage-Basis)
                grenze = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
                schnitt = round(sum(r.cost_usd or 0 for r in rows if r.date >= grenze) / 30, 4)
                # Jahres-Prognose: zu wenig Historie → laufenden Monat auf 30 Tage hochrechnen.
                tag_im_monat = datetime.date.today().day
                prognose = round(monat / max(tag_im_monat, 1) * 30 * 12, 2)
                calls_monat = sum(r.calls or 0 for r in rows if r.date >= monat_iso) or None

            lim = limits.get(p)
            limit_block = None
            if lim:
                ph = _prozent(heute, lim.daily_limit_usd)
                pm = _prozent(monat, lim.monthly_limit_usd)
                limit_block = {
                    "daily_limit_usd": lim.daily_limit_usd,
                    "monthly_limit_usd": lim.monthly_limit_usd,
                    "enforcement": lim.enforcement, "active": lim.active,
                    "heute_prozent": ph, "monat_prozent": pm,
                    "status": _status(ph, pm, lim.active),
                    "rest_heute_usd": None if lim.daily_limit_usd is None
                    else round(max(lim.daily_limit_usd - heute, 0), 4),
                    "rest_monat_usd": None if lim.monthly_limit_usd is None
                    else round(max(lim.monthly_limit_usd - monat, 0), 4),
                    "max_runs_per_day": lim.max_runs_per_day,
                }
            providers.append({
                "provider": p, "label": (lim.label if lim else None) or p.capitalize(),
                "art": "verbrauch",
                "heute_usd": heute, "monat_usd": monat, "jahr_usd": jahr,
                "schnitt_tag_usd": schnitt, "jahr_prognose_usd": prognose, "geschaetzt": True,
                "heute_eur": round(heute * rate, 2), "monat_eur": round(monat * rate, 2),
                "jahr_prognose_eur": round(prognose * rate, 2),
                "calls_monat": calls_monat,
                "runs_heute": runs_heute, "hinweis": hinweis,
                "limit": limit_block,
            })

    # Fixkosten (Abos) — gemeldet, nie limitiert.
    fix_monat_usd = 0.0
    for f in cfg.get("fixkosten") or []:
        monatlich = float(f.get("monatlich") or 0)
        if monatlich <= 0:
            continue
        usd = monatlich if (f.get("waehrung") or "USD").upper() == "USD" else monatlich / rate
        fix_monat_usd += usd
        providers.append({
            "provider": f.get("provider"), "label": f.get("label") or f.get("provider"),
            "art": "abo", "hinweis": f.get("hinweis"),
            "heute_usd": round(usd / 30, 4), "monat_usd": round(usd, 2),
            "jahr_usd": round(usd * 12, 2), "jahr_prognose_usd": round(usd * 12, 2),
            "geschaetzt": False,
            "heute_eur": round(usd / 30 * rate, 2), "monat_eur": round(usd * rate, 2),
            "jahr_prognose_eur": round(usd * 12 * rate, 2),
            "limit": None,
        })

    heute_ges = round(sum(p["heute_usd"] for p in providers), 4)
    monat_ges = round(sum(p["monat_usd"] for p in providers), 2)
    jahr_ges = round(sum(p["jahr_prognose_usd"] for p in providers), 2)
    return {
        "providers": providers,
        "totals": {
            "heute_usd": heute_ges, "monat_usd": monat_ges, "jahr_prognose_usd": jahr_ges,
            "heute_eur": round(heute_ges * rate, 2), "monat_eur": round(monat_ges * rate, 2),
            "jahr_prognose_eur": round(jahr_ges * rate, 2),
            "fix_monat_usd": round(fix_monat_usd, 2), "fix_monat_eur": round(fix_monat_usd * rate, 2),
        },
        "letzter_sync": letzter_sync.isoformat() + "Z" if letzter_sync else None,
        "usd_eur_rate": rate,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(prog="pipeline.budget")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sync", help="echten Apify-Verbrauch ziehen")
    sub.add_parser("report", help="Aggregation als JSON")

    p_r = sub.add_parser("record", help="metered-Verbrauch protokollieren")
    p_r.add_argument("provider")
    p_r.add_argument("cost_usd", type=float)
    p_r.add_argument("--calls", type=int, default=None)
    p_r.add_argument("--note", default=None)
    p_r.add_argument("--date", default=None, help="YYYY-MM-DD (Default: heute)")

    p_c = sub.add_parser("check", help="Guard prüfen (kostet nichts)")
    p_c.add_argument("provider")
    p_c.add_argument("--estimated", type=float, default=0.0)

    a = ap.parse_args()
    if a.cmd == "sync":
        out = sync_apify()
    elif a.cmd == "record":
        out = record(a.provider, a.cost_usd, a.calls, a.note, a.date)
    elif a.cmd == "check":
        out = ensure_budget(a.provider, a.estimated)
    else:
        out = report()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    # `check` mit allowed=false → Exit 2: "Budget erschöpft", kein Fehler.
    if a.cmd == "check" and not out.get("allowed"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
