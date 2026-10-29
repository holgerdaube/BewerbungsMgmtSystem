"""Backfill (Phase 42 Stufe C): trägt Bestands-Debatten aus data/beirat/ als historische
AgentTask-Rows nach — vor Stufe A schrieb die Beirat-Engine keine Rows, „Läufe gesamt" im
Task-Center war deshalb unvollständig. Idempotent (Erkennung über debatte_id in params_json,
identisch zum Live-Pfad in beirat_engine.py) — ein zweiter Lauf ist ein No-op, nur INSERT,
nie UPDATE/DELETE bestehender Rows. Noch laufende Debatten (status "läuft") werden bewusst
übersprungen, nicht als "failed" verbucht — sie sind schlicht noch nicht fertig.

Aufruf: cd backend && ~/.bewerbung_mgmt_venv/bin/python -m scripts.backfill_beirat_tasks
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from app.db import engine
from app.models import AgentTask

PROJEKT_ROOT = Path(__file__).resolve().parent.parent.parent
DATEN_DIR = PROJEKT_ROOT / "data" / "beirat"
BEIRAT_KINDS = ("beirat-stellen-check", "beirat-debatte")


def _lokal_zu_utc(iso: str) -> datetime:
    """gestartet/Datei-mtime sind naive LOKALE Zeit (datetime.now() bzw. Filesystem-mtime) —
    DST-korrekt auf naives UTC umrechnen (AgentTask-Konvention, s. Model-Kommentar). Wichtig
    für die Guardrail-Tagesgrenze (agent_runner._tagesbeginn_utc) — sonst würden historische
    Rows fälschlich ins heutige Tagesbudget einzahlen."""
    lokal = datetime.fromisoformat(iso)
    return lokal.astimezone(timezone.utc).replace(tzinfo=None)


def _bereits_erfasste_ids(session: Session) -> set[str]:
    vorhanden = session.exec(select(AgentTask).where(AgentTask.kind.in_(BEIRAT_KINDS))).all()
    ids: set[str] = set()
    for t in vorhanden:
        try:
            debatte_id = json.loads(t.params_json or "{}").get("debatte_id")
        except Exception:
            continue
        if debatte_id:
            ids.add(debatte_id)
    return ids


def _result_json(d: dict) -> dict:
    if d.get("modus") == "stellen_check" and d.get("entscheidung"):
        e = d["entscheidung"]
        result = {"debatte_id": d["id"], "ampel": e.get("ampel"), "score": e.get("gesamt"),
                  "stimmen": e.get("stimmen"), "dashboard_path": d.get("dashboard_pfad")}
    else:
        result = {"debatte_id": d["id"], "beitraege": len(d.get("beitraege") or [])}
    result["hinweis"] = "vor Phase 42, Kosten nicht erfasst"
    return result


def main() -> None:
    dateien = sorted(p for p in DATEN_DIR.glob("*.json") if not p.name.endswith("_rohdaten.json"))
    neu, bereits_da, laufend, unlesbar = 0, 0, 0, 0

    with Session(engine) as session:
        erfasst = _bereits_erfasste_ids(session)
        for pfad in dateien:
            try:
                d = json.loads(pfad.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"⚠️  {pfad.name}: nicht lesbar ({e}) — übersprungen")
                unlesbar += 1
                continue

            debatte_id = d.get("id")
            if not debatte_id or debatte_id in erfasst:
                bereits_da += 1
                continue
            if d.get("status") == "läuft":
                laufend += 1
                continue   # noch nicht terminal — kein Backfill, kein falsches "failed"

            kind = "beirat-stellen-check" if d.get("modus") == "stellen_check" else "beirat-debatte"
            gestartet_utc = _lokal_zu_utc(d["gestartet"])
            beendet_utc = _lokal_zu_utc(
                datetime.fromtimestamp(pfad.stat().st_mtime).isoformat())
            if beendet_utc < gestartet_utc:
                beendet_utc = gestartet_utc   # Datei-mtime älter als gestartet? Randfall, nie negativ

            params = {"debatte_id": debatte_id, "min_beitraege": d.get("min_beitraege"),
                      "teilnehmer": [t.get("id") for t in (d.get("teilnehmer") or [])],
                      "provider": d.get("provider")}

            t = AgentTask(
                kind=kind, job_id=d.get("job_id"), prompt=d.get("thema"),
                params_json=json.dumps(params, ensure_ascii=False),
                status="done" if d.get("status") == "fertig" else "failed",
                error=d.get("fehler"),
                cost_usd=0.0,
                result_json=json.dumps(_result_json(d), ensure_ascii=False)[:20000],
                created_at=gestartet_utc, started_at=gestartet_utc, finished_at=beendet_utc,
                duration_s=round((beendet_utc - gestartet_utc).total_seconds(), 1),
            )
            session.add(t)
            neu += 1

        session.commit()

    print(f"Backfill fertig: {neu} neue Rows angelegt · {bereits_da} bereits erfasst "
          f"(No-op) · {laufend} noch laufend übersprungen · {unlesbar} unlesbar "
          f"· {len(dateien)} Debatten-Dateien insgesamt.")


if __name__ == "__main__":
    main()
