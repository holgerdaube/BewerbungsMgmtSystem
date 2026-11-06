#!/usr/bin/env python3
"""Alte Beirats-Debatten ins Englische übersetzen (P2-96).

Debatten aus der Zeit vor der Mehrsprachigkeit liegen auf Deutsch in `data/beirat/`. Dieses Werkzeug legt englische Fassungen
daneben in `data/beirat/en/`: die Debatte als `<id>.json`, den Bericht ohne KI aus der übersetzten Fassung. Die Originale bleiben
unverändert, die Anzeige wählt nach der Oberflächensprache (`beirat_engine.debatte_lesen`).

Fertige Debatten werden übersprungen, ein Abbruch lässt sich also einfach neu starten. Am Abo-Limit stoppt der Lauf.

CLI, aus `backend/`:
    python -m pipeline.beirat_uebersetzen --pruefen
    python -m pipeline.beirat_uebersetzen --ids <id>[,<id>] [--ordner DIR]
    python -m pipeline.beirat_uebersetzen --alle --max-usd 20 --parallel 3
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import beirat_engine as be
from app import agent_runner, sprache

MAX_WOERTER_JE_STUECK = 2500
MAX_DEUTSCH_ANTEIL = 0.05
# Feste Werte, die der Code liest oder die Namen sind. Sie bleiben, wie sie sind.
_FESTE_SCHLUESSEL = {"kopf", "schwere", "status", "votum", "ampel", "id"}
_DEUTSCH_RE = re.compile(r"\b(und|der|die|das|nicht|für|mit|ist|eine|sich|auf|werden|von|bei|dass|auch|wird|sind)\b")
_LIMIT_RE = re.compile(r"usage limit|rate limit|limit reached|hit your limit|quota", re.IGNORECASE)


class AboLimit(RuntimeError):
    """Das Abo ist am Limit. Der Lauf stoppt, ein neuer Start setzt fort."""


class UebersetzungFehler(RuntimeError):
    """Die Antwort war unbrauchbar."""


def _im_baum(wert, setzen, aus: list) -> None:
    """Sammelt alle Texte in verschachtelten Feldern. `setzen` schreibt die Übersetzung an die Fundstelle."""
    if isinstance(wert, str):
        if wert.strip():
            aus.append((wert, setzen))
    elif isinstance(wert, dict):
        for k, v in wert.items():
            if k not in _FESTE_SCHLUESSEL:
                _im_baum(v, lambda t, ziel=wert, s=k: ziel.__setitem__(s, t), aus)
    elif isinstance(wert, list):
        for i, v in enumerate(wert):
            _im_baum(v, lambda t, ziel=wert, s=i: ziel.__setitem__(s, t), aus)


def texte_sammeln(d: dict) -> list:
    """Alle zu übersetzenden Texte einer Debatte als (Text, Setzer). `kontext` bleibt Rohmaterial."""
    aus: list = []
    _im_baum(d.get("thema"), lambda t: d.__setitem__("thema", t), aus)
    for b in d.get("beitraege") or []:
        for feld in ("frage", "text"):
            _im_baum(b.get(feld), lambda t, ziel=b, s=feld: ziel.__setitem__(s, t), aus)
    for m in d.get("moderationen") or []:
        _im_baum(m.get("text"), lambda t, ziel=m: ziel.__setitem__("text", t), aus)
    _im_baum(d.get("synthese"), lambda t: d.__setitem__("synthese", t), aus)
    for stimme in (d.get("abstimmung") or {}).values():
        if stimme is None:  # Enthaltung: Der Kopf hat nicht abgestimmt
            continue
        _im_baum(stimme.get("begruendung"), lambda t, ziel=stimme: ziel.__setitem__("begruendung", t), aus)
    _im_baum(d.get("check_synthese"), lambda t: d.__setitem__("check_synthese", t), aus)
    return aus


def in_stuecke(texte: list[str], max_woerter: int = MAX_WOERTER_JE_STUECK) -> list[list[str]]:
    stuecke, aktuell, woerter = [], [], 0
    for t in texte:
        n = len(t.split())
        if aktuell and woerter + n > max_woerter:
            stuecke.append(aktuell)
            aktuell, woerter = [], 0
        aktuell.append(t)
        woerter += n
    if aktuell:
        stuecke.append(aktuell)
    return stuecke


def _prompt(texte: list[str]) -> str:
    glossar = be._glossar_zeilen()
    begriffe = f"\nUse these terms consistently (German = English):\n{glossar}\n" if glossar else "\n"
    return (
        "Translate every string in the JSON array below from German to British English. These are contributions from a "
        "job applicant's advisory board. Translate everything, including quotations from CVs and job postings.\n"
        "Keep unchanged: names of people and companies, job titles, product names, numbers, currency amounts, dates, "
        "Markdown formatting and line breaks. Add nothing, leave nothing out, do not summarise."
        f"{begriffe}\n"
        "Reply with ONLY a JSON array of strings: same length, same order, no explanation, no code fence.\n\n"
        + json.dumps(texte, ensure_ascii=False)
    )


def _ki_aufruf(prompt: str) -> tuple[str, float]:
    """Ein KI-Lauf ohne Werkzeuge. Gibt (Antworttext, Kosten in USD) zurück."""
    env, _ = agent_runner._child_env("job-frage")
    argv = [agent_runner.CLAUDE_BIN, "-p", "--output-format", "json", "--model", agent_runner.MODELL_STANDARD,
            "--strict-mcp-config", "--setting-sources", "project", "--max-budget-usd", "3",
            "--disallowedTools", "Bash,Edit,Write,Read,Glob,Grep,WebFetch,WebSearch,Task,Skill,NotebookEdit"]
    with tempfile.TemporaryDirectory() as ordner:
        lauf = subprocess.run(argv, input=prompt, cwd=ordner, env=env, capture_output=True, text=True,
                              encoding="utf-8", timeout=900)
    try:
        daten = json.loads(lauf.stdout)
    except ValueError:
        text = f"{lauf.stdout[-300:]} {lauf.stderr[-300:]}"
        raise (AboLimit if _LIMIT_RE.search(text) else UebersetzungFehler)(text.strip() or f"Exit {lauf.returncode}")
    if daten.get("is_error"):
        text = str(daten.get("result"))[:300]
        raise (AboLimit if _LIMIT_RE.search(text) else UebersetzungFehler)(text)
    return str(daten.get("result") or ""), float(daten.get("total_cost_usd") or 0.0)


def antwort_pruefen(roh: str, texte: list[str]) -> list[str]:
    """Die Antwort als Liste, oder `UebersetzungFehler`. Fängt das, was sonst still in die Anzeige käme."""
    start, ende = roh.find("["), roh.rfind("]")
    if start < 0 or ende < start:
        raise UebersetzungFehler("Keine JSON-Liste in der Antwort")
    try:
        liste = json.loads(roh[start:ende + 1])
    except ValueError as exc:
        raise UebersetzungFehler(f"Antwort ist kein gültiges JSON: {exc}") from exc
    if not isinstance(liste, list) or len(liste) != len(texte):
        raise UebersetzungFehler(f"{len(liste) if isinstance(liste, list) else '?'} Texte statt {len(texte)}")
    if not all(isinstance(t, str) and t.strip() for t in liste):
        raise UebersetzungFehler("Leerer Text in der Antwort")
    gesamt = " ".join(liste)
    woerter = len(gesamt.split()) or 1
    if len(_DEUTSCH_RE.findall(gesamt)) / woerter > MAX_DEUTSCH_ANTEIL:
        raise UebersetzungFehler("Antwort ist überwiegend deutsch")
    return liste


def _uebersetzen(texte: list[str], tief: int = 0) -> tuple[list[str], float]:
    """Übersetzt ein Stück. Scheitert es, einmal halbiert nochmal: Lange Stücke sind die häufigste Ursache."""
    kosten = 0.0
    try:
        roh, kosten = _ki_aufruf(_prompt(texte))
        return antwort_pruefen(roh, texte), kosten
    except UebersetzungFehler:
        if tief >= 1 or len(texte) < 2:
            raise
    mitte = len(texte) // 2
    links, k1 = _uebersetzen(texte[:mitte], tief + 1)
    rechts, k2 = _uebersetzen(texte[mitte:], tief + 1)
    return links + rechts, kosten + k1 + k2  # auch der gescheiterte Versuch hat gekostet


def _schreiben(pfad: Path, text: str) -> None:
    """Atomar: Ein Abbruch hinterlässt keine halbe Datei, die beim Fortsetzen als fertig gälte."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    zwischen = pfad.with_name(pfad.name + ".tmp")
    zwischen.write_text(text, encoding="utf-8")
    os.replace(zwischen, pfad)


def _bericht_daten(d: dict, ordner: Path) -> SimpleNamespace | None:
    """Was `_dashboard_html` braucht, oder None, wenn die Debatte keinen Bericht hat."""
    if not (d.get("dashboard_pfad") and d.get("entscheidung") and d.get("check_synthese")):
        return None
    name = Path(d["dashboard_pfad"]).name
    roh_pfad = ordner / (name[:-5] + "_rohdaten.json")
    if not roh_pfad.is_file():
        return None
    roh = json.loads(roh_pfad.read_text(encoding="utf-8"))
    return SimpleNamespace(
        id=d["id"], job_id=d.get("job_id"), job_titel=roh.get("job_titel", ""), job_firma=roh.get("job_firma", ""),
        beitraege=d.get("beitraege") or [], moderationen=d.get("moderationen") or [], abstimmung=d["abstimmung"],
        entscheidung=d["entscheidung"], check_synthese=d["check_synthese"], company_fit_fehlt=False, synthese_fehler=None,
        mitglieder={t["id"]: t for t in d.get("teilnehmer") or []})


def bericht_schreiben(d: dict, ordner: Path) -> bool:
    """Englischer Bericht aus der übersetzten Fassung, ohne KI, mit dem Datum der Debatte."""
    daten = _bericht_daten(d, ordner)
    if daten is None:
        return False
    stand = datetime.fromisoformat(d["gestartet"]) if d.get("gestartet") else None
    _schreiben(ordner / "en" / Path(d["dashboard_pfad"]).name, be._dashboard_html(daten, stand=stand))
    return True


def debatte_uebersetzen(pfad: Path, ordner: Path) -> float:
    """Eine Debatte. Gibt die Kosten zurück. Die Datei entsteht erst, wenn alles fertig ist."""
    d = be.debatte_aus_datei(pfad)
    fundstellen = texte_sammeln(d)
    uebersetzt: list[str] = []
    kosten = 0.0
    for stueck in in_stuecke([t for t, _ in fundstellen]):
        ergebnis, k = _uebersetzen(stueck)
        uebersetzt += ergebnis
        kosten += k
    for (_, setzen), neu in zip(fundstellen, uebersetzt):
        setzen(neu)
    d["uebersetzt_aus"] = "de"
    bericht_schreiben(d, ordner)
    _schreiben(ordner / "en" / pfad.name, json.dumps(d, ensure_ascii=False, indent=1))
    return kosten


def offene_debatten(ordner: Path) -> list[Path]:
    """Abgeschlossene deutsche Debatten ohne englische Fassung, neueste zuerst."""
    aus = []
    for f in sorted(ordner.glob("*.json"), reverse=True):
        if f.name.endswith("_rohdaten.json") or (ordner / "en" / f.name).exists():
            continue
        try:
            d = be.debatte_aus_datei(f)
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("id") and d.get("beitraege") and d.get("status") != "laeuft" and not d.get("uebersetzt_aus"):
            aus.append(f)
    return aus


def lauf(pfade: list[Path], ordner: Path, parallel: int, max_usd: float | None, melden=print) -> dict:
    stand = {"fertig": 0, "fehler": 0, "kosten": 0.0, "gestoppt": None}
    sperre = threading.Lock()
    stopp = threading.Event()

    def arbeit(pfad: Path) -> None:
        if stopp.is_set():
            return
        with sperre:
            if max_usd is not None and stand["kosten"] >= max_usd:
                stand["gestoppt"] = f"Kostengrenze {max_usd} USD erreicht"
                stopp.set()
                return
        try:
            kosten = debatte_uebersetzen(pfad, ordner)
        except AboLimit as exc:
            with sperre:
                stand["gestoppt"] = f"Abo-Limit: {exc}"
            stopp.set()
            return
        except Exception as exc:  # noqa: BLE001 — eine kaputte Debatte darf den Lauf nicht beenden
            with sperre:
                stand["fehler"] += 1
            melden(f"FEHLER {pfad.stem}: {type(exc).__name__}: {str(exc)[:200]}")
            return
        with sperre:
            stand["fertig"] += 1
            stand["kosten"] += kosten
            melden(f"OK {pfad.stem}: {kosten:.2f} USD, gesamt {stand['kosten']:.2f} USD, {stand['fertig']} fertig")

    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        list(pool.map(arbeit, pfade))
    return stand


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline.beirat_uebersetzen", description=__doc__.split("\n")[0])
    ap.add_argument("--pruefen", action="store_true", help="nur zählen, was noch offen ist")
    ap.add_argument("--alle", action="store_true")
    ap.add_argument("--ids", help="kommagetrennte Debatten-IDs")
    ap.add_argument("--ordner", help="Ordner der Debatten (Vorgabe: data/beirat)")
    ap.add_argument("--parallel", type=int, default=2)
    ap.add_argument("--max-usd", type=float, default=None)
    args = ap.parse_args(argv)
    ordner = Path(args.ordner) if args.ordner else be.DATEN_DIR
    # Der Bericht wird englisch beschriftet, egal welche Sprache die Oberfläche gerade hat. Gilt nur für diesen Prozess.
    sprache.aktuell = lambda: "en"
    offen = offene_debatten(ordner)
    if args.pruefen or not (args.alle or args.ids):
        print(f"Offen: {len(offen)} Debatten")
        return 0
    pfade = offen if args.alle else [ordner / f"{i.strip()}.json" for i in args.ids.split(",")]
    stand = lauf(pfade, ordner, args.parallel, args.max_usd)
    print(f"Fertig: {stand['fertig']}, Fehler: {stand['fehler']}, Kosten: {stand['kosten']:.2f} USD, "
          f"offen: {len(offene_debatten(ordner))}" + (f", gestoppt: {stand['gestoppt']}" if stand["gestoppt"] else ""))
    return 1 if stand["fehler"] or stand["gestoppt"] else 0


if __name__ == "__main__":
    sys.exit(main())
