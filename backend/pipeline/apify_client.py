#!/usr/bin/env python3
"""Apify-Zugang für die Jobsuche (Phase 8.3, opt-in).

Ersetzt den claude.ai-Apify-Connector, der in headless-Läufen nicht existiert.

WARUM DETERMINISTISCH statt Agent-gesteuert:
    Planungsgrundlage ist der Apify **Free Plan** (~5 $ Guthaben/Monat), und alle Job-Actors rechnen
    pro Ereignis ab. Dürfte der Agent per `search-actors` selbst Scraper wählen und
    beliebig viele Ergebnisse ziehen, wäre das Monatsbudget nach wenigen Läufen weg.
    Deshalb: Actors sind in `config/suchprofile.yaml` **gepinnt**, das Item-Limit ist
    hart gedeckelt, und `--dry-run` zeigt jeden geplanten Aufruf, bevor Credits fließen.

Dieses Modul liefert ROHDATEN. Die Beurteilung (passt der Titel? greift eine
Ausschlussregel? welcher Score?) trifft der `jobsuche`-Skill — dieselbe Arbeitsteilung
wie bei `gmail_client`: Modul holt Fakten, Agent urteilt.

CLI (immer aus backend/ heraus):
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.apify_client usage
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.apify_client schema LinkedIn
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.apify_client run --portal LinkedIn \
        --query "Director Professional Services" --location "Remote Germany" [--max-items 25] [--dry-run]

Token: `APIFY_TOKEN` aus der Umgebung (in `agent.env` im Secrets-Verzeichnis, chmod 600 —
dasselbe Muster wie CLAUDE_CODE_OAUTH_TOKEN; der Runner reicht die Datei per `_child_env()`
durch). Seit Phase 63A liegt das Secrets-Verzeichnis AUSSERHALB von Projekt & iCloud:
Default `~/.bewerbung_mgmt_secrets`, Override `BMS_SECRETS_DIR`.
Der Token wird nie ausgegeben, auch nicht in Fehlermeldungen.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import httpx
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent   # Bewerbung_Mgmt_System/
PROFILE = PROJECT_ROOT / "config" / "suchprofile.yaml"
OUT_DIR = PROJECT_ROOT / "data" / "apify"
# Phase 63A (P1-2): agent.env liegt AUSSERHALB von Projekt & iCloud (gleiches Muster wie
# pipeline.gmail_client.SECRETS_DIR und beirat_engine.KEY_DIR). Override per BMS_SECRETS_DIR.
SECRETS_DIR = Path(os.environ.get("BMS_SECRETS_DIR", str(Path.home() / ".bewerbung_mgmt_secrets")))

API = "https://api.apify.com/v2"

MAX_ITEMS_DEFAULT = 25
MAX_ITEMS_HARD = 100        # Kostenbremse: mehr geht nur durch bewusste Code-Änderung
RUN_TIMEOUT_S = 300


def _die(msg: str, code: int = 1) -> "NoReturn":       # noqa: F821
    """Exit 1 = echter Fehler. Exit 2 ist reserviert für „Budget erschoepft" (Phase 10),
    damit Skills das eine vom anderen unterscheiden koennen."""
    print(msg, file=sys.stderr)
    raise SystemExit(code)


ENV_FILE = SECRETS_DIR / "agent.env"


def token_or_none() -> "Optional[str]":       # noqa: F821
    """APIFY_TOKEN aus der Umgebung ODER aus ENV_FILE (SECRETS_DIR/agent.env). Kein Abbruch.

    Die Env-Datei muss hier selbst gelesen werden: nur der Phase-8-Runner reicht sie per
    `_child_env()` an seine Subprozesse durch. Eine normale Shell und der FastAPI-Server
    (Budget-Sync!) sehen sie sonst nicht. Der Wert wird nie geloggt.
    """
    tok = (os.environ.get("APIFY_TOKEN") or "").strip()
    if tok:
        return tok
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == "APIFY_TOKEN":
                return v.strip().strip('"').strip("'") or None
    return None


def _token() -> str:
    tok = token_or_none()
    if not tok:
        _die("APIFY_TOKEN fehlt.\n"
             "→ Token unter https://console.apify.com/settings/integrations holen und in\n"
             f"  {ENV_FILE} eintragen (Format/Beispiel: automation/agent.env.example).\n"
             "  (chmod 600; NIE Zeilen in dieser Datei loeschen — s. tasks/lessons.md)\n"
             "Ohne Apify laeuft die Jobsuche weiterhin ueber WebSearch.")
    return tok


def _profile() -> dict:
    with open(PROFILE, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _actor_cfg(portal: str) -> dict:
    actors = _profile().get("apify_actors") or {}
    cfg = actors.get(portal)
    if not cfg:
        _die(f"Kein Actor fuer Portal '{portal}' konfiguriert.\n"
             f"→ verfuegbar: {', '.join(actors) or '(keine)'}\n"
             f"→ nachtragen in {PROFILE.relative_to(PROJECT_ROOT)} unter 'apify_actors'.")
    return cfg


def _fill(node, query: str, location: str, max_items: int):
    """Platzhalter ersetzen. $MAX wird zur Zahl — Apify lehnt Strings in int-Feldern ab."""
    if isinstance(node, dict):
        return {k: _fill(v, query, location, max_items) for k, v in node.items()}
    if isinstance(node, list):
        return [_fill(v, query, location, max_items) for v in node]
    if node == "$MAX":
        return max_items
    if isinstance(node, str):
        return node.replace("$QUERY", query).replace("$LOCATION", location)
    return node


# ── Verben ────────────────────────────────────────────────────────────────────────────
def cmd_usage() -> dict:
    """Monatsverbrauch zeigen — vor jedem Lauf wissen, wie viel Guthaben noch da ist.

    Die API liefert nur eine USD-GESAMTsumme, keine USD-Aufschlüsselung je Dienst
    (`monthlyServiceUsage` sind Mengen: Compute-Units, Dataset-Reads …, keine Beträge).
    Der Abrechnungszeitraum steht unter `usageCycle`, NICHT auf Top-Level.
    """
    with httpx.Client(timeout=30.0) as cl:
        r = cl.get(f"{API}/users/me/usage/monthly", params={"token": _token()})
        if r.status_code >= 400:
            _die(f"Apify-API {r.status_code}: {r.text[:300]}")
        d = r.json().get("data", {})
    zyklus = d.get("usageCycle") or {}
    dienste = d.get("monthlyServiceUsage") or {}
    # USD je Dienst steckt in `amountAfterVolumeDiscountUsd` — nur die > 0.01, absteigend.
    posten = {k: round(v.get("amountAfterVolumeDiscountUsd") or 0, 3)
              for k, v in dienste.items() if (v.get("amountAfterVolumeDiscountUsd") or 0) >= 0.01}
    return {
        "zeitraum": f"{(zyklus.get('startAt') or '?')[:10]} – {(zyklus.get('endAt') or '?')[:10]}",
        "verbraucht_usd": round(d.get("totalUsageCreditsUsdAfterVolumeDiscount") or 0, 3),
        "posten_usd": dict(sorted(posten.items(), key=lambda kv: -kv[1])),
    }


_JSON_TYP = {str: "string", int: "integer", float: "number", list: "array", bool: "boolean"}


def _pruefe_input(payload: dict, props: dict, required: list) -> list:
    """Gefuelltes Input gegen das echte Actor-Schema halten. Fängt Actor-Wechsel ab,
    bevor ein Lauf Credits fuer eine 400er-Antwort verbrennt."""
    probleme = []
    for k, v in payload.items():
        feld = props.get(k)
        if not feld:
            probleme.append(f"'{k}' gibt es im Actor-Schema nicht")
            continue
        erwartet, gesendet = feld.get("type"), _JSON_TYP.get(type(v))
        if erwartet and gesendet and erwartet != gesendet:
            probleme.append(f"'{k}': Actor erwartet {erwartet}, gesendet wird {gesendet}")
        if feld.get("enum") and not isinstance(v, list) and str(v) not in feld["enum"]:
            probleme.append(f"'{k}'={v!r} ist nicht in {feld['enum']}")
    for r in required:
        if r not in payload:
            probleme.append(f"Pflichtfeld '{r}' fehlt im konfigurierten Input")
    return probleme


def cmd_schema(portal: str) -> dict:
    """Input-Schema des gepinnten Actors — und ein Abgleich gegen unsere Konfiguration.

    Macht einen Actor-Wechsel selbstdokumentierend UND selbstprüfend.
    """
    cfg = _actor_cfg(portal)
    aid = cfg["actor"].replace("/", "~")
    with httpx.Client(timeout=30.0) as cl:
        r = cl.get(f"{API}/acts/{aid}/builds/default")     # oeffentlich, kein Token noetig
        if r.status_code >= 400:
            _die(f"Actor '{cfg['actor']}' nicht abrufbar (HTTP {r.status_code}).")
        sch = r.json().get("data", {}).get("inputSchema")
    if isinstance(sch, str):
        sch = json.loads(sch)
    props = (sch or {}).get("properties", {})
    required = (sch or {}).get("required") or []

    # mit Beispielwerten fuellen — genau so, wie `run` es tun wuerde
    beispiel = _fill(cfg["input"], "Director Professional Services", "Deutschland", MAX_ITEMS_DEFAULT)
    probleme = _pruefe_input(beispiel, props, required)
    return {
        "portal": portal,
        "actor": cfg["actor"],
        "beispiel_input": beispiel,
        "felder": {k: {"type": v.get("type"), "enum": v.get("enum")} for k, v in props.items()},
        "required": required,
        "probleme": probleme,
        "status": "ok" if not probleme else "Input passt NICHT zum Actor-Schema",
    }


def cmd_run(portal: str, query: str, location: str, max_items: int, dry_run: bool) -> dict:
    cfg = _actor_cfg(portal)
    n = max(1, min(int(max_items), MAX_ITEMS_HARD))
    payload = _fill(cfg["input"], query, location, n)
    aid = cfg["actor"].replace("/", "~")
    plan = {"portal": portal, "actor": cfg["actor"], "max_items": n, "input": payload}

    if dry_run:
        plan["dry_run"] = True
        plan["hinweis"] = "Nichts ausgefuehrt, keine Credits verbraucht."
        return plan       # dry-run kostet nichts → keine Budget-Pruefung

    # ── Budget-Guard (Phase 10): VOR dem Geldausgeben ────────────────────────────────
    # Erst den echten Verbrauch nachziehen (best effort — ein Sync-Fehler darf den Lauf
    # nicht verhindern), dann gegen die Limits aus der App pruefen.
    from pipeline.budget import ensure_budget, sync_apify
    sync = sync_apify()
    if not sync.get("ok"):
        print(f"  Hinweis: Apify-Verbrauch nicht aktualisiert ({sync.get('fehler')}) — "
              f"Budget-Pruefung nutzt den letzten bekannten Stand.", file=sys.stderr)
    stand = ensure_budget("apify", estimated_cost=0.05)
    if not stand["allowed"]:
        _die(f"Budget erschoepft: {stand['grund']}\n"
             f"→ Limit in der App aendern: http://localhost:8000/budget", code=2)
    if stand["warn"]:
        print(f"  WARNUNG: {stand['grund']} (enforcement=weich, Lauf geht weiter)", file=sys.stderr)

    # Vorpruefung gegen das echte Schema: ein 400er wuerde sonst Credits kosten.
    # Faellt der Check selbst aus (Netz/Endpunkt), laufen wir trotzdem weiter.
    try:
        probleme = cmd_schema(portal)["probleme"]
    except SystemExit:
        probleme = []
    if probleme:
        _die(f"Input passt nicht zum Actor-Schema von {cfg['actor']} — Lauf abgebrochen, "
             f"keine Credits verbraucht:\n  - " + "\n  - ".join(probleme) +
             f"\n→ 'apify_actors.{portal}.input' in config/suchprofile.yaml korrigieren.")

    with httpx.Client(timeout=RUN_TIMEOUT_S + 30) as cl:
        r = cl.post(
            f"{API}/acts/{aid}/run-sync-get-dataset-items",
            params={"token": _token(), "maxItems": n, "timeout": RUN_TIMEOUT_S},
            json=payload,
        )
        if r.status_code >= 400:
            # r.text kann den Token nicht enthalten — der steht nur im Query-String.
            _die(f"Apify-Lauf fehlgeschlagen (HTTP {r.status_code}) fuer {cfg['actor']}:\n"
                 f"{r.text[:400]}\n"
                 f"→ Input-Schema pruefen: python -m pipeline.apify_client schema {portal}")
        items = r.json()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = f"{portal.lower()}_{query.lower().replace(' ', '_')[:40]}"
    out_file = OUT_DIR / f"{slug}.json"
    out_file.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    plan.update({
        "treffer": len(items),
        "rohdaten": str(out_file.relative_to(PROJECT_ROOT)),
        "vorschau": [_normalize(it) for it in items[:5]],
        "hinweis": "Rohdaten. Titel-/Ausschlusspruefung und Scoring macht der jobsuche-Skill.",
    })
    return plan


# Actor-Ausgaben heissen je Scraper anders. Best effort — der Skill prueft am Rohdatensatz nach.
# Feldnamen variieren je Actor stark. `organization`/`locations_derived` z. B. bei
# fantastic-jobs/advanced-linkedin-job-search-api (verifiziert 10.07.2026).
_ALIASES = {
    "title": ("title", "jobTitle", "position", "name"),
    "company": ("company", "companyName", "company_name", "employer", "organization",
                "organization_name", "companyOrganization"),
    "location": ("location", "jobLocation", "place", "city", "locations_derived",
                 "locations", "location_name"),
    "url": ("url", "jobUrl", "link", "jobLink", "applyUrl", "organization_url"),
    "published": ("postedAt", "publishedAt", "date", "datePosted", "postedDate",
                  "date_posted", "date_created"),
    "salary": ("salary", "salaryText", "compensation"),
}


def _erster_str(v):
    """Wert → nicht-leerer String. Listen (z. B. locations_derived) → erstes Element."""
    if isinstance(v, str) and v.strip():
        return v.strip()
    if isinstance(v, (list, tuple)):
        for x in v:
            s = _erster_str(x)
            if s:
                return s
    return None


def _normalize(item: dict) -> dict:
    out = {}
    for feld, keys in _ALIASES.items():
        for k in keys:
            s = _erster_str(item.get(k))
            if s:
                out[feld] = s
                break
    return out


# ── CLI ───────────────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(prog="pipeline.apify_client")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("usage", help="Apify-Monatsverbrauch (Free Plan: ~5 $)")

    p_sc = sub.add_parser("schema", help="Input-Schema des gepinnten Actors")
    p_sc.add_argument("portal")

    p_r = sub.add_parser("run", help="Actor ausfuehren (kostet Credits!)")
    p_r.add_argument("--portal", required=True, help="LinkedIn | Indeed | StepStone | Xing")
    p_r.add_argument("--query", required=True, help="Rollentitel aus suchprofile.yaml")
    p_r.add_argument("--location", required=True)
    p_r.add_argument("--max-items", type=int, default=MAX_ITEMS_DEFAULT,
                     help=f"Default {MAX_ITEMS_DEFAULT}, Hard-Cap {MAX_ITEMS_HARD}")
    p_r.add_argument("--dry-run", action="store_true", help="nur zeigen, was gesendet wuerde")

    a = ap.parse_args()
    if a.cmd == "usage":
        out = cmd_usage()
    elif a.cmd == "schema":
        out = cmd_schema(a.portal)
    else:
        out = cmd_run(a.portal, a.query, a.location, a.max_items, a.dry_run)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
