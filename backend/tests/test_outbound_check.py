"""Tests für scripts/outbound_check.py (Phase 66B, Erkennung statt nur Vorbeugung zu P1-1).

Das Skript liegt bewusst außerhalb von backend/ (kein App-/Pipeline-Modul — reine
Standardbibliothek, liest NUR die Agent-Logs des Nutzers) — Import hier über `importlib`, da `scripts/`
kein Python-Package ist und nicht auf dem normalen Importpfad von backend/tests/ liegt.

Geprüft werden die reinen Funktionen (Host-Extraktion, Klassifikation, Regex-Erkennung) sowie ein
End-to-End-Lauf gegen eine SYNTHETISCHE Log-Datei unter tmp_path — NIEMALS gegen die echten
~/.bewerbung_mgmt_logs/ (die enthalten personenbezogene Daten, s. Skript-Docstring, "S5" aus
tasks/spec_phase66_sandbox.md gilt für Tests genauso wie für den Bau selbst).
"""
import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "outbound_check.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("outbound_check", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def oc():
    return _load_module()


# ── Klassifikation ──────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1"])
def test_lokale_hosts_werden_als_local_erkannt(oc, host):
    assert oc.classify(host) == "local"


@pytest.mark.parametrize("host", ["www.googleapis.com", "oauth2.googleapis.com",
                                   "google.com", "api.apify.com"])
def test_bekannte_infrastruktur_wird_erkannt(oc, host):
    assert oc.classify(host) == "known-infra"


def test_perplexity_ist_keine_bekannte_infrastruktur_mehr(oc):
    """P2-78: Das Perplexity-Modul ist entfernt, ein Aufruf dorthin soll auffallen."""
    assert oc.classify("api.perplexity.ai") != "known-infra"


def test_rohe_ip_wird_als_suspicious_erkannt_ausser_loopback(oc):
    assert oc.classify("203.0.113.5") == "suspicious-ip"    # RFC-5737-Dokumentations-Adresse
    assert oc.classify("127.0.0.1") == "local"               # Loopback bleibt lokal, nicht "IP"


@pytest.mark.parametrize("host", ["webhook.site", "sub.ngrok-free.app", "pastebin.com"])
def test_bekannte_tunnel_paste_dienste_werden_erkannt(oc, host):
    assert oc.classify(host) == "suspicious-listed"


def test_punycode_host_wird_erkannt(oc):
    assert oc.classify("xn--80ak6aa92e.com") == "suspicious-punycode"


def test_unbekannter_host_ist_other_nicht_automatisch_verdaechtig(oc):
    """'other' ist der erwartete lange Schwanz aus Karriereseiten (s. Skript-Docstring) — KEINE
    eigene Verdachts-Klasse. Ein Algorithmus kann hunderte wechselnde legitime Zielfirmen nicht
    von einer erfundenen unterscheiden (der Blick des Nutzers entscheidet, s. Doku im Skript)."""
    assert oc.classify("www.irgendeine-firma-karriere.de") == "other"


# ── Host-Extraktion aus URLs ────────────────────────────────────────────────────────────────
def test_host_von_url_ignoriert_port_und_pfad(oc):
    assert oc._host_of("http://localhost:8000/api/jobs/5") == "localhost"
    assert oc._host_of("https://www.example.com/jobs?x=1") == "www.example.com"


# ── "Weitere Signale"-Regex: Regressionstest für den Fehlalarm aus dem echten Testlauf
# (26.07.2026) — bevor die Regex auf Kommando-Position eingeschränkt wurde, matchte JEDES
# Vorkommen von "nc" als Wort, auch eine Python-Schleifenvariable. ─────────────────────────────
def test_variable_namens_nc_loest_keinen_fehlalarm_aus(oc):
    cmd = "for nc in new_contacts:\n    added.append(nc)"
    assert oc.NET_KEYWORD_RE.search(cmd) is None


def test_echtes_netcat_kommando_wird_erkannt(oc):
    assert oc.NET_KEYWORD_RE.search("curl -s foo && nc -l 4444") is not None
    assert oc.NET_KEYWORD_RE.search("nc -l 4444") is not None


def test_python_netzwerkaufruf_wird_erkannt(oc):
    assert oc.NET_KEYWORD_RE.search('urllib.request.urlopen("http://x")') is not None
    assert oc.NET_KEYWORD_RE.search('requests.post("http://x", data=y)') is not None


# ── End-to-End: synthetische Log-Datei (niemals die echten Logs) ────────────────────────────
def _tool_use_line(name, input_dict):
    return json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": name, "input": input_dict}]},
    })


def test_scan_erkennt_curl_und_webfetch_aus_synthetischer_logdatei(oc, tmp_path):
    log = tmp_path / "task_999.jsonl"
    zeilen = [
        _tool_use_line("Bash", {"command": "curl -s http://localhost:8000/api/jobs/1"}),
        _tool_use_line("Bash", {"command": "curl -s https://203.0.113.5/x"}),
        _tool_use_line("WebFetch", {"url": "https://www.beispiel-karriere.de/job/1"}),
        '{"type": "assistant", "message": {"kaputtes json ohne schluss',   # Parse-Fehler, darf nicht abstürzen
        "reine Textzeile ohne JSON — muss ignoriert werden",
    ]
    log.write_text("\n".join(zeilen) + "\n", encoding="utf-8")

    files, treffer, weitere_signale, parse_errors, zeitraum = oc.scan(tmp_path, days=None)

    assert len(files) == 1
    assert parse_errors == 1
    hosts = {(t.quelle, t.host) for t in treffer}
    assert ("curl", "localhost") in hosts
    assert ("curl", "203.0.113.5") in hosts
    assert ("webfetch", "www.beispiel-karriere.de") in hosts

    # Die Klassifikation muss die rohe IP als auffällig erkennen, localhost nicht.
    klassen = {t.host: oc.classify(t.host) for t in treffer}
    assert klassen["203.0.113.5"] == "suspicious-ip"
    assert klassen["localhost"] == "local"


def test_scan_bricht_bei_fehlendem_verzeichnis_kontrolliert_ab(oc, tmp_path):
    with pytest.raises(SystemExit) as exc:
        oc.scan(tmp_path / "gibt_es_nicht", days=None)
    assert exc.value.code == 1


def test_scan_liest_niemals_und_schreibt_niemals_ausserhalb_des_log_dir(oc, tmp_path):
    """Reiner Selbstschutz-Test: ein scan() gegen ein leeres tmp-Verzeichnis darf darin nichts
    anlegen (rein lesendes Werkzeug, S5 der Spec)."""
    vorher = list(tmp_path.iterdir())
    oc.scan(tmp_path, days=None)
    nachher = list(tmp_path.iterdir())
    assert vorher == nachher == []
