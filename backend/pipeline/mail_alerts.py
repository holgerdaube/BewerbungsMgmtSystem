#!/usr/bin/env python3
"""Job-Alert-Mails aus dem Postfach einsammeln (Phase 13).

Arbeitsteilung wie überall: dieses Modul liefert MECHANISCH die Alert-Mails (Absender,
Betreff, Volltext UND die enthaltenen Links) — der Skill `mail-jobsuche` urteilt
(Extraktion/harte Grenzen/Scoring), `pipeline.ingest` schreibt. Jede Mail wird genau
EINMAL verarbeitet; das garantiert die Tabelle `AlertMail` (gmail_message_id unique),
nicht Labels (der gmail_client kann bewusst nicht labeln) und nicht die `email`-Tabelle
(die gehört dem Bewerbungs-Tracking von email-check).

Reuse statt Duplikat: Auth, HTTP und Body-Parsing kommen aus `pipeline.gmail_client`
(read-only). NEU hier ist nur die Link-Extraktion — der gmail_client strippt HTML zu Text
und verliert dabei die href-URLs, die wir für den URL-Dedup gegen die Apify-Treffer brauchen.

CLI (immer aus backend/ heraus):
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.mail_alerts fetch [--days 2] [--max 30]
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.mail_alerts done <gmail_message_id> --postings <n>
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.mail_alerts status

Ausgabe: JSON auf stdout. Fehler: Klartext auf stderr, Exit 2.
"""
import argparse
import datetime
import json
import re
import sys
from html import unescape
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml
from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import AlertMail
from app.naming import dated_filename
from pipeline import gmail_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent   # Bewerbung_Mgmt_System/
CONFIG_FILE = PROJECT_ROOT / "config" / "suchprofile.yaml"
OUT_DIR = PROJECT_ROOT / "data" / "mail_alerts"

# LinkedIn-Job-URLs (auch die /comm/…-Tracking-Variante) auf die kanonische Form bringen —
# maximiert den URL-Dedup gegen die Apify-Treffer.
_LINKEDIN_JOB_RE = re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(\d+)", re.I)
# Bei allen anderen URLs nur Tracking-Query-Parameter abschneiden (Pfad bleibt).
_TRACKING_KEYS = {
    "trk", "trackingid", "refid", "lipi", "midtoken", "midsig", "eid", "otptoken",
    "recommendedflavor", "trkemail", "li_medium", "li_source", "actorid",
}
# <a href="…"> bzw. href='…'  — inner-Text als Anker (DOTALL, Anker kann umbrechen).
_A_RE = re.compile(r'<a\b[^>]*?href=(?:"([^"]*)"|\'([^\']*)\')[^>]*>(.*?)</a>', re.I | re.S)


def _die(msg: str) -> "NoReturn":       # noqa: F821
    print(msg, file=sys.stderr)
    raise SystemExit(2)


def _load_config() -> dict:
    if not CONFIG_FILE.exists():
        _die(f"{CONFIG_FILE} fehlt.")
    data = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
    cfg = data.get("mail_alerts")
    if not cfg or not cfg.get("absender"):
        _die("config/suchprofile.yaml: Block 'mail_alerts.absender' fehlt (Phase 13 A1).")
    return cfg


# ── Link-Extraktion (das Neue in Phase 13) ─────────────────────────────────────────────
def _normalize_url(url: str) -> str:
    """LinkedIn-Job-URL → kanonisch; sonst Tracking-Query abschneiden."""
    url = unescape((url or "").strip())
    m = _LINKEDIN_JOB_RE.search(url)
    if m:
        return f"https://www.linkedin.com/jobs/view/{m.group(1)}/"
    parts = urlsplit(url)
    if parts.query:
        keep = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
                if k.lower() not in _TRACKING_KEYS and not k.lower().startswith("utm_")]
        parts = parts._replace(query=urlencode(keep))
    return urlunsplit(parts)


def _html_part(payload: dict) -> str:
    """Rohes text/html aus dem Payload (rekursiv) — VOR dem HTML-Strippen, damit die
    Links erhalten bleiben. Nutzt gmail_client._decode (kein Duplikat)."""
    mime = payload.get("mimeType", "")
    data = payload.get("body", {}).get("data")
    if data and mime == "text/html":
        return gmail_client._decode(data)
    for part in payload.get("parts") or []:
        h = _html_part(part)
        if h:
            return h
    return ""


def _extract_links(html_text: str) -> list:
    """Alle http(s)-Links als {url, text}, URL normalisiert, nach normalisierter URL dedupt.
    Der Skill entscheidet, welche davon echte Postings sind."""
    out, seen = [], set()
    for m in _A_RE.finditer(html_text):
        href = m.group(1) or m.group(2) or ""
        if not href.lower().startswith(("http://", "https://")):
            continue
        norm = _normalize_url(href)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        text = unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(3) or ""))).strip()
        out.append({"url": norm, "text": text[:200]})
    return out


# ── Verben ──────────────────────────────────────────────────────────────────────────────
def fetch(days: int, max_results: int) -> dict:
    init_db()
    cfg = _load_config()

    # Query 1: die verifizierten Job-Alert-Absender.
    q1 = f"from:({' OR '.join(cfg['absender'])}) newer_than:{days}d"
    records = list(gmail_client.cmd_search(q1, max_results))

    # Query 2: LinkedIn-Newsletter-Absender NUR wenn der Betreff nach Stellen aussieht
    # (dort kommt „Jobgether via LinkedIn", aber auch Nicht-Job-Newsletter).
    bz = cfg.get("betreff_zusatz") or {}
    if bz.get("from") and bz.get("muster"):
        muster = [str(x).lower() for x in bz["muster"]]
        for r in gmail_client.cmd_search(f"from:{bz['from']} newer_than:{days}d", max_results):
            subj = (r.get("subject") or "").lower()
            if any(x in subj for x in muster):
                records.append(r)

    neu, uebersprungen, emitted, seen_ids = 0, 0, [], set()
    creds = gmail_client._creds()
    with gmail_client._client(creds) as cl, Session(engine) as s:
        for rec in records:
            mid = rec.get("gmail_message_id")
            if not mid or mid in seen_ids:
                continue
            seen_ids.add(mid)
            row = s.exec(select(AlertMail).where(AlertMail.gmail_message_id == mid)).first()
            # Einmal-Schutz sitzt auf dem `done` (processed_at), NICHT aufs Einsammeln: schon
            # VERARBEITETE Mails werden übersprungen, noch offene aber erneut ausgegeben. So
            # strandet ein Abbruch nach `fetch`, aber vor `done` (Timeout/Budget) die Mail nicht
            # — der Retry holt sie nach (der Ingest dedupliziert die Postings ohnehin).
            if row is not None and row.processed_at is not None:
                uebersprungen += 1
                continue
            if row is None:
                s.add(AlertMail(gmail_message_id=mid, sender=rec.get("from_addr"),
                                subject=rec.get("subject"), received_at=rec.get("received_at")))
                neu += 1
            # Volltext einmal laden → body_text (gestrippt) + Links (aus dem HTML-Teil).
            msg = gmail_client._get(cl, f"/messages/{mid}", format="full")
            payload = msg.get("payload", {})
            emitted.append({
                "gmail_message_id": mid,
                "from": rec.get("from_addr"),
                "subject": rec.get("subject"),
                "received_at": rec.get("received_at"),
                "body_text": gmail_client._body_text(payload),
                "links": _extract_links(_html_part(payload)),
            })
        s.commit()

    # Datei nur schreiben, wenn es offene (noch unverarbeitete) Mails gibt; sonst datei=None,
    # dann ist der Lauf fertig. `offen` (nicht `neu`) ist das Arbeitssignal für den Skill.
    datei = None
    if emitted:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out_file = OUT_DIR / dated_filename("Mail_Alerts", "json")
        out_file.write_text(json.dumps(emitted, ensure_ascii=False, indent=2), encoding="utf-8")
        datei = str(out_file.relative_to(PROJECT_ROOT))
    return {"neu": neu, "offen": len(emitted), "uebersprungen": uebersprungen, "datei": datei}


def done(gmail_message_id: str, postings: int) -> dict:
    init_db()
    with Session(engine) as s:
        row = s.exec(select(AlertMail).where(AlertMail.gmail_message_id == gmail_message_id)).first()
        if not row:
            _die(f"AlertMail {gmail_message_id} nicht gefunden — erst 'fetch' ausführen.")
        row.processed_at = datetime.datetime.utcnow()
        row.postings_found = postings
        s.add(row)
        s.commit()
        return {"gmail_message_id": gmail_message_id, "postings_found": postings,
                "processed_at": row.processed_at.strftime("%Y-%m-%dT%H:%M:%SZ")}


def status() -> dict:
    init_db()
    with Session(engine) as s:
        rows = s.exec(select(AlertMail)).all()
    verarbeitet = sum(1 for r in rows if r.processed_at is not None)
    return {"gesamt": len(rows), "verarbeitet": verarbeitet, "offen": len(rows) - verarbeitet,
            "postings_gesamt": sum((r.postings_found or 0) for r in rows)}


# ── CLI ───────────────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(prog="pipeline.mail_alerts", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_f = sub.add_parser("fetch", help="neue Alert-Mails einsammeln (read-only)")
    p_f.add_argument("--days", type=int, default=None, help="Zeitfenster; Default = mail_alerts.max_age_tage")
    p_f.add_argument("--max", type=int, default=30, help="max. Mails je Query (Default 30)")

    p_d = sub.add_parser("done", help="Mail als verarbeitet markieren (nach dem Ingest)")
    p_d.add_argument("gmail_message_id")
    p_d.add_argument("--postings", type=int, required=True, help="Anzahl extrahierter Stellen (auch 0)")

    sub.add_parser("status", help="offen/verarbeitet-Zähler")

    a = ap.parse_args()
    if a.cmd == "fetch":
        days = a.days if a.days is not None else int(_load_config().get("max_age_tage", 2))
        out = fetch(days, a.max)
    elif a.cmd == "done":
        out = done(a.gmail_message_id, a.postings)
    else:
        out = status()
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
