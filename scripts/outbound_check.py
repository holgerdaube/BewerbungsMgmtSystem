#!/usr/bin/env python3
"""scripts/outbound_check.py — Erkennung statt nur Vorbeugung (Phase 66B, zu P1-1).

Liest die Agent-Task-Logs (NUR LESEND, ändert/löscht nie etwas) und listet, wohin die headless
laufenden Skills tatsächlich ausgehende Verbindungen aufgebaut haben — als Handgriff, den man
bei Bedarf manuell aufruft. KEIN Automatismus, KEIN Cron, KEINE Alarmierung (s.
tasks/spec_phase66_sandbox.md, Stufe 66B).

Hintergrund: Der Review-Verifier hat das am 25.07.2026 einmal manuell getan (mehrere hundert
curl-Aufrufe über mehrere Tage, 100 % an localhost oder legitime Karriereseiten/Google-APIs).
Dieses Skript macht daraus
einen wiederholbaren Befehl.

WAS DIESES WERKZEUG SIEHT:
  - `curl`-Aufrufe innerhalb von Bash-Kommandos (Text-Extraktion der URL, kein echter
    Shell-Parser — best effort, wie der manuelle Review-Durchgang selbst).
  - `WebFetch`-Aufrufe (das `url`-Feld steht dort strukturiert, keine Extraktion nötig).
  - Als schwaches Zusatzsignal ("weitere Signale"): `wget`/`nc`/`netcat`/`ssh`/`scp`/`rsync ::`
    sowie Python-Netzwerk-Aufrufe (`requests.`, `httpx.`, `urllib.request`, `urlopen(`,
    `http.client`, `socket.connect(`), sofern sie WÖRTLICH im Bash-Kommandotext stehen (z. B. ein
    `python -c "..."`-Einzeiler).

WAS DIESES WERKZEUG STRUKTURELL NICHT SIEHT (S4 — keine Sicherheits-Behauptung ohne Deckung):
  - Netzwerkverkehr, den ein per Bash gestartetes Python-MODUL selbst macht (`pipeline.gmail_client`
    und `pipeline.apify_client` nutzen `httpx` INNERHALB des Moduls — im
    Log steht nur der Aufrufbefehl, z. B. "python -m pipeline.gmail_client search …", nicht die
    HTTP-Requests, die das Modul dann intern absetzt). Dasselbe gilt für jeden anderen Netzwerkzugriff
    aus importiertem Code.
  - WebSearch-Ergebnisse (die Suche läuft serverseitig bei Anthropic, nicht auf diesem Mac — kein
    "ausgehendes Ziel" im hier gemeinten Sinn).
  - Alles, was NICHT als Text im Log steht (kompilierter/verschleierter Code, Base64-dekodierte
    Kommandos zur Laufzeit u. ä.).
  Dieses Werkzeug ist ein grobes, augenfälliges Signal für den sichtbarsten Exfiltrationsweg
  (direkte curl-Aufrufe) — keine Netzwerküberwachung. Es ersetzt kein Codereview und ist kein
  Beleg für "nichts Verdächtiges passiert", sondern nur für "nichts Verdächtiges SICHTBAR".

AUSGABE: kurze Übersicht (Zählungen) + auffällige Treffer (Roh-IPs, bekannte Tunnel-/Paste-/
Webhook-Dienste, Punycode-Hosts) einzeln aufgelistet. Alles andere (der lange Schwanz aus
Karriereseiten/Firmenwebsites/Headhunter-Seiten) wird nur als Top-N gezeigt (`--all` für die
volle Liste) — DAS zu bewerten ("ist diese Firmen-Domain plausibel") bleibt der Blick des Nutzers, kein
Algorithmus kann hunderte wechselnde legitime Zielfirmen von einer erfundenen unterscheiden.

Exit-Codes (informativ, kein Gate): 0 = sauber/nichts Auffälliges, 1 = Log-Verzeichnis fehlt oder
Lesefehler, 2 = mindestens ein auffälliger Treffer (Roh-IP/Tunnel-Dienst/Punycode).

Keine Projekt-Abhängigkeiten (nur Python-Standardbibliothek) — läuft mit jedem Python 3, nicht nur
der venv. Aufruf:
    python3 scripts/outbound_check.py [--all] [--top N] [--days N] [--log-dir PFAD]
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

# Identische Auflösung wie backend/app/agent_runner.py::LOG_DIR (Phase 63B) — bewusst dieselbe
# Env-Variable, damit ein abweichender BMS_LOG_DIR (z. B. in Tests) automatisch mitgilt.
DEFAULT_LOG_DIR = Path(os.environ.get("BMS_LOG_DIR", str(Path.home() / ".bewerbung_mgmt_logs")))

# ── Gepflegte Liste erwarteter Ziele (S1: empirisch, nicht geraten — Basis: ein realer Scan
# über die Log-Dateien am 26.07.2026, s. Phase-66B-Bericht). Bei Bedarf hier ergänzen. ────────────────
KNOWN_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
# Google/OAuth-Familie (Gmail) + die Pay-per-Call-API von Apify, FALLS sie je per curl statt über
# das Python-Modul aufgerufen werden (normalerweise NICHT sichtbar, s. Docstring oben).
# P2-78: api.perplexity.ai gestrichen -- das Modul ist entfernt, ein Aufruf dorthin ist jetzt ein
# unbekanntes Ziel und soll im Bericht auffallen.
KNOWN_INFRA_SUFFIXES = ("googleapis.com", "google.com", "api.apify.com")

# Bekannte Tunnel-/Paste-/Webhook-Dienste — in einer normalen Bewerbungs-Recherche gibt es dafür
# keinen legitimen Grund; typische Exfiltrations-/Command&Control-Infrastruktur. Liste bei Bedarf
# ergänzen (bewusst keine Anspruch auf Vollständigkeit).
SUSPICIOUS_HOST_SUFFIXES = (
    "ngrok.io", "ngrok-free.app", "ngrok.app", "ngrok.dev", "trycloudflare.com",
    "pastebin.com", "hastebin.com", "hasteb.in", "paste.ee",
    "transfer.sh", "file.io", "0x0.st", "anonfiles.com", "gofile.io",
    "webhook.site", "requestbin.com", "requestbin.net", "pipedream.net",
    "interactsh.com", "oastify.com", "canarytokens.com", "burpcollaborator.net",
    "requestcatcher.com", "beeceptor.com", "dnslog.cn",
)

# URL-Extraktion: best effort (Text-Regex, kein Shell-Parser) — endet an Whitespace/Quote/
# Shell-Metazeichen. Bewusst großzügig (Scheme beliebig, nicht nur http/s), damit z. B. ein
# `curl ftp://…` oder `file://…` nicht unbemerkt durchrutscht.
URL_RE = re.compile(r"\b\w[\w+.-]*://[^\s'\"|;&)]+")
CURL_SEGMENT_RE = re.compile(r"\bcurl\b[^\n]*")

# "Weitere Signale" (S1: schwaches Zusatzsignal, s. Docstring "was dieses Werkzeug NICHT sieht").
# wget/nc/netcat/ssh/scp nur als KOMMANDO matchen (Start der Zeile/des Strings oder direkt nach
# einem Shell-Trenner ;/&/|), NICHT als beliebiges Vorkommen des Wortes — sonst schlägt z. B. eine
# Python-Zeile `for nc in new_contacts:` (reale Fehlalarm-Falle, gefunden beim Testlauf gegen die
# echte Log-Historie am 26.07.2026) fälschlich anschlägt, weil "nc" zufällig als Schleifenvariable
# vorkommt.
NET_KEYWORD_RE = re.compile(
    r"(?:^|[\n;&|]|\$\()\s*(?:wget|nc|netcat|ssh|scp)\b"
    r"|\brsync\b[^\n]*::"
    r"|\brequests\.(?:get|post|put|patch|delete)\("
    r"|\bhttpx\.(?:get|post|put|patch|delete|Client)\("
    r"|\burllib\.request\b"
    r"|\burlopen\("
    r"|\bhttp\.client\b"
    r"|\bsocket\.connect\("
)


def _split_host(netloc: str) -> str:
    """Reiner Host-Anteil ohne Port/IPv6-Klammern (netloc kann 'host:port' oder '[ipv6]:port' sein)."""
    netloc = netloc.strip()
    if netloc.startswith("["):
        return netloc[1:netloc.index("]")] if "]" in netloc else netloc[1:]
    if netloc.count(":") == 1:
        host, _, port = netloc.partition(":")
        if port.isdigit():
            return host
    return netloc


def _host_of(url: str) -> str:
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc or (parsed.path.split("/")[0] if parsed.path else url)
        return _split_host(netloc)
    except Exception:
        return url


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def classify(host: str) -> str:
    """host -> 'local' | 'known-infra' | 'suspicious-ip' | 'suspicious-listed' |
    'suspicious-punycode' | 'other'. 'other' ist NICHT automatisch verdächtig — es ist der lange
    Schwanz aus Firmen-/Karriereseiten, den kein Algorithmus bewerten kann (s. Moduldocstring)."""
    h = host.lower()
    if h in KNOWN_LOCAL_HOSTS:
        return "local"
    if h and _is_ip_literal(h) and h not in KNOWN_LOCAL_HOSTS:
        return "suspicious-ip"
    if any(h == s or h.endswith("." + s) for s in SUSPICIOUS_HOST_SUFFIXES):
        return "suspicious-listed"
    if "xn--" in h:
        return "suspicious-punycode"
    if any(h == s or h.endswith("." + s) for s in KNOWN_INFRA_SUFFIXES):
        return "known-infra"
    return "other"


def _iter_tool_use_blocks(log_path: Path):
    """Yields (tool_name, input_dict) für jeden tool_use-Block in einer Log-Datei — sowohl vom
    Hauptlauf als auch von etwaigen Subagenten (die tauchen im selben stream-json-Log auf, tragen
    dort zusätzlich ein `subagent_type`-Feld, s. Phase-66B-Bericht). Fehlerhafte Zeilen werden
    gezählt, nicht geworfen — ein einzelnes kaputtes JSON-Objekt darf den gesamten Scan nicht
    abbrechen."""
    parse_errors = 0
    try:
        raw = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"WARNUNG: {log_path.name} nicht lesbar ({e}) — übersprungen", file=sys.stderr)
        return parse_errors
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            parse_errors += 1
            continue
        if ev.get("type") != "assistant":
            continue
        msg = ev.get("message", {})
        content = msg.get("content", []) if isinstance(msg, dict) else []
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield block.get("name"), (block.get("input") or {})
    return parse_errors


class Treffer:
    """Ein extrahiertes ausgehendes Ziel + wo es herkam (für die Beispiel-Anzeige)."""

    __slots__ = ("host", "url", "task", "quelle")

    def __init__(self, host: str, url: str, task: str, quelle: str):
        self.host = host
        self.url = url
        self.task = task
        self.quelle = quelle  # "curl" | "webfetch"


def scan(log_dir: Path, days: int | None):
    if not log_dir.is_dir():
        print(f"FEHLER: Log-Verzeichnis nicht gefunden: {log_dir}", file=sys.stderr)
        sys.exit(1)

    files = sorted(log_dir.glob("*.jsonl"))
    if days is not None:
        cutoff = datetime.now() - timedelta(days=days)
        files = [f for f in files if datetime.fromtimestamp(f.stat().st_mtime) >= cutoff]

    treffer: list[Treffer] = []
    weitere_signale: list[tuple[str, str]] = []  # (task, kurzer Befehlsausschnitt)
    parse_errors_total = 0
    mtimes = []

    for f in files:
        mtimes.append(f.stat().st_mtime)
        gen = _iter_tool_use_blocks(f)
        while True:
            try:
                name, inp = next(gen)
            except StopIteration as stop:
                parse_errors_total += stop.value or 0
                break
            if name == "Bash":
                cmd = inp.get("command", "") or ""
                for seg_match in CURL_SEGMENT_RE.finditer(cmd):
                    segment = seg_match.group(0)
                    for u in URL_RE.findall(segment):
                        treffer.append(Treffer(_host_of(u), u, f.name, "curl"))
                if NET_KEYWORD_RE.search(cmd):
                    ausschnitt = cmd.strip().replace("\n", " ")[:160]
                    weitere_signale.append((f.name, ausschnitt))
            elif name == "WebFetch":
                u = inp.get("url", "")
                if u:
                    treffer.append(Treffer(_host_of(u), u, f.name, "webfetch"))

    zeitraum = None
    if mtimes:
        zeitraum = (datetime.fromtimestamp(min(mtimes)), datetime.fromtimestamp(max(mtimes)))
    return files, treffer, weitere_signale, parse_errors_total, zeitraum


def _report(quelle_label: str, treffer: list[Treffer], top: int, show_all: bool) -> bool:
    """Druckt den Abschnitt für eine Quelle (curl/webfetch). Gibt True zurück, wenn mindestens
    ein auffälliger Treffer dabei war (für den Exit-Code)."""
    print(f"\n{quelle_label}:")
    if not treffer:
        print("  keine Aufrufe im gewählten Zeitraum")
        return False

    by_class: dict[str, Counter] = defaultdict(Counter)
    beispiele: dict[str, list[Treffer]] = defaultdict(list)
    for t in treffer:
        klasse = classify(t.host)
        by_class[klasse][t.host] += 1
        if len(beispiele[t.host]) < 3:
            beispiele[t.host].append(t)

    gesamt = len(treffer)
    n_local = sum(by_class["local"].values())
    n_infra = sum(by_class["known-infra"].values())
    n_other = sum(by_class["other"].values())
    n_suspicious = gesamt - n_local - n_infra - n_other

    print(f"  gesamt: {gesamt} Aufrufe")
    if n_local:
        pct = 100 * n_local / gesamt
        print(f"  lokal (eigene API): {n_local} ({pct:.1f} %)")
    if n_infra:
        print(f"  bekannte Infrastruktur (Google/OAuth, Apify): {n_infra}")
    if n_other:
        distinct = len(by_class["other"])
        print(f"  sonstige Ziele (Karriereseiten u. ä., nicht auf der Liste — normal, s. Docstring): "
              f"{n_other} Aufrufe, {distinct} verschiedene Hosts")
        anzeige = by_class["other"].most_common(None if show_all else top)
        for host, n in anzeige:
            print(f"    {n:6d}  {host}")
        if not show_all and distinct > top:
            print(f"    … und {distinct - top} weitere (--all für die volle Liste)")

    auffaellig_klassen = ("suspicious-ip", "suspicious-listed", "suspicious-punycode")
    auffaellig_gesamt = sum(sum(by_class[k].values()) for k in auffaellig_klassen)
    print(f"  AUFFÄLLIG ({auffaellig_gesamt}):")
    if not auffaellig_gesamt:
        print("    keine")
    else:
        grund = {"suspicious-ip": "Roh-IP (kein Hostname)",
                 "suspicious-listed": "bekannter Tunnel-/Paste-/Webhook-Dienst",
                 "suspicious-punycode": "Punycode-Host (xn--, möglicher Homograph)"}
        for klasse in auffaellig_klassen:
            for host, n in by_class[klasse].most_common():
                bsp = beispiele[host][0]
                print(f"    {n:3d}x  {host:30s}  [{grund[klasse]}]  Beispiel: {bsp.task} → {bsp.url}")
    return bool(auffaellig_gesamt)


def main():
    ap = argparse.ArgumentParser(
        description="Listet ausgehende Ziele aus den Agent-Task-Logs (nur lesend). "
                    "Kein Automatismus — manueller Aufruf bei Bedarf (Phase 66B).")
    ap.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR,
                     help=f"Log-Verzeichnis (Default: {DEFAULT_LOG_DIR}, Override auch über BMS_LOG_DIR)")
    ap.add_argument("--top", type=int, default=20, help="Wie viele 'sonstige' Hosts in der Kurzübersicht (Default 20)")
    ap.add_argument("--all", action="store_true", help="Vollständige Host-Liste statt Top-N")
    ap.add_argument("--days", type=int, default=None, help="Nur Log-Dateien der letzten N Tage (Default: alle)")
    args = ap.parse_args()

    files, treffer, weitere_signale, parse_errors, zeitraum = scan(args.log_dir, args.days)

    print(f"Outbound-Check — {args.log_dir}")
    if zeitraum:
        print(f"Log-Dateien: {len(files)} (Zeitraum {zeitraum[0]:%Y-%m-%d} .. {zeitraum[1]:%Y-%m-%d})"
              f", Zeilen mit Parse-Fehlern: {parse_errors} (ignoriert)")
    else:
        print(f"Log-Dateien: {len(files)}")
        if not files:
            print("Keine .jsonl-Dateien gefunden — nichts zu prüfen.")
            sys.exit(0)

    curl_treffer = [t for t in treffer if t.quelle == "curl"]
    webfetch_treffer = [t for t in treffer if t.quelle == "webfetch"]

    auffaellig = False
    auffaellig |= _report("curl (aus Bash-Aufrufen)", curl_treffer, args.top, args.all)
    auffaellig |= _report("WebFetch", webfetch_treffer, args.top, args.all)

    print(f"\nWeitere Signale (wget/nc/ssh/scp/rsync/Python-Netzwerkaufrufe direkt im Bash-Befehl): "
          f"{len(weitere_signale)} Treffer")
    for task, ausschnitt in weitere_signale[:20]:
        print(f"    {task}: {ausschnitt}")
    if len(weitere_signale) > 20:
        print(f"    … und {len(weitere_signale) - 20} weitere")

    print("\nHinweis: Dieses Werkzeug zeigt nur, was als curl-/WebFetch-Aufruf im Log-Text sichtbar "
          "ist — s. Docstring 'WAS DIESES WERKZEUG NICHT SIEHT'. Kein Beleg für Abwesenheit, nur für "
          "Abwesenheit von SICHTBAREN Auffälligkeiten. Die 'sonstigen Ziele' oben sind der erwartete "
          "lange Schwanz aus Firmen-/Karriereseiten — der Blick eines Menschen entscheidet, nicht dieses Skript.")

    sys.exit(2 if auffaellig else 0)


if __name__ == "__main__":
    main()
