"""Tests fuer die Online-Suche und das Laden in scripts/bms_update.py (P2-82, Paket U).

Das Werkzeug fragt in Schritt 2 die GitHub-Releases des Repositorys nach einer neuen Version und
laedt sie (Vertrag U der Spec tasks/spec_p2-82_lizenz_raus_update_github.md). Diese Datei spielt
GitHub mit einem Probeserver aus der Standardbibliothek (`http.server` im Thread, 127.0.0.1,
Port 0): er zaehlt und speichert jede Anfrage (Pfad, Kopfzeilen, Rumpf), antwortet nach Vorgabe des
Tests und wird nach jedem Test beendet. `GITHUB_API` und `GITHUB_SEITE` zeigen per `monkeypatch` auf
ihn. Die Zielpruefung der Umleitungen (`_ziel_erlaubt`) ersetzt der Test, wo er eine Umleitung zu
einem "erlaubten" Host mit dem Probeserver spielt (dessen Adresse ist http und 127.0.0.1); die echte
Regel prueft ein eigener Test an einer Tabelle von Adressen.

KEIN TEST SPRICHT github.com, api.github.com ODER SONST EINE ADRESSE IM NETZ AN. Als zweite
Sicherung ersetzt eine Autouse-Fixture die Namensaufloesung: jeder Name ausser 127.0.0.1/localhost
laesst den Test sofort scheitern. Die echte Installation bleibt unberuehrt: HOME/USERPROFILE,
BMS_SECRETS_DIR und die Installation liegen unter `tmp_path`; die Lizenzdatei dort ist erfunden
(Max Mustermann) und dient nur dem Beweis, dass sie nicht mehr gelesen wird.

Wie test_bms_update.py laedt diese Datei das Werkzeug per Pfad (eigene Modulinstanz) und baut ihre
Pakete selbst; sie importiert nichts aus app/pipeline.
"""
from __future__ import annotations

import ast
import builtins
import importlib.util
import inspect
import io
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Union
from urllib.parse import urlsplit

import pytest

_PROJEKT_ROOT = Path(__file__).resolve().parent.parent.parent
_SKRIPT_PFAD = _PROJEKT_ROOT / "scripts" / "bms_update.py"


def _lade_bms_update():
    spec = importlib.util.spec_from_file_location("bms_update_github_unter_test", _SKRIPT_PFAD)
    modul = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modul      # vor exec_module, s. test_bms_update.py (dataclasses)
    spec.loader.exec_module(modul)
    return modul


bms_update = _lade_bms_update()
_QUELLTEXT = _SKRIPT_PFAD.read_text(encoding="utf-8")
_EIGENES_SKRIPT = _SKRIPT_PFAD.read_bytes()
OnlineFehler = bms_update.OnlineFehler

REPO = "holgerdaube/BewerbungsMgmtSystem"      # wortgleich zur Spec: Leitentscheidung 1
RELEASE_PFAD = f"/repos/{REPO}/releases/latest"

# Kundentexte aus Vertrag U (wortgleich)
T_KEINE_VERBINDUNG = "Es besteht keine Verbindung zu GitHub."
T_ZEIT = "GitHub antwortet nicht rechtzeitig."
T_UNTERBROCHEN = "Die Verbindung zu GitHub wurde unterbrochen."
T_ZERTIFIKAT = "Die sichere Verbindung zu GitHub ließ sich nicht prüfen."
T_UNGUELTIG = "Die Antwort von GitHub ist ungültig."
T_KEINE_VERSION = "Es ist noch keine Version veröffentlicht."
T_GRENZE = "GitHub begrenzt gerade die Anfragen. Bitte versuchen Sie es in einer Stunde erneut."
T_PRUEFSUMME = "Zur neuesten Version fehlt die Prüfsumme. Sie wird nicht eingespielt."
T_BESCHAEDIGT = "Das geladene Paket ist unvollständig oder beschädigt."

# Erfundene Lizenzdatei (nie echte Daten): liegt im Test an beiden moeglichen Orten und darf weder
# gelesen noch irgendwohin gesendet werden.
LIZENZ_MARKER = ("Max Mustermann", "max.mustermann@example.com", "MUSTER-0000-TEST",
                 "U2lnbmF0dXItZnVlci1kZW4tVGVzdA==")
LIZENZ_BYTES = (json.dumps(
    {"payload": {"license_id": LIZENZ_MARKER[2], "customer": LIZENZ_MARKER[0] + " GmbH (Köln)",
                 "email": LIZENZ_MARKER[1], "updates_until": "2028-10-09"},
     "signature": LIZENZ_MARKER[3]},
    indent=2, ensure_ascii=False) + "\r\n").encode("utf-8")

# Namen aus der Zeit der Lizenzpflicht, zusammengesetzt, damit die Suche im Arbeitsbaum (Abnahme der
# Spec, Wächter in test_ohne_lizenz.py) hier nichts findet. Sie dienen nur als Gegenprobe.
ALTE_LIZENZDATEI = "lizenz" + ".json"
ALTER_DIENST = "bms." + "daube.tech"

_STANDARD = ["--ja", "--ohne-abhaengigkeiten", "--ohne-selbsttest"]
WEG = object()          # Marker: dieses Feld aus dem Probe-Release entfernen


# ── Pakete und Installationen (Muster aus test_bms_update.py) ───────────────────────────────
def _sha256(daten: bytes) -> str:
    return sha256(daten).hexdigest()


def _manifest_bauen(version: str, dateien: dict[str, bytes]) -> dict:
    return {
        "anpassbar": [], "commit": "a" * 40, "commit_datum": "2026-09-28",
        "dateien": {pfad: {"ausfuehrbar": False, "groesse": len(inhalt), "sha256": _sha256(inhalt)}
                    for pfad, inhalt in dateien.items()},
        "format": 1, "freigabe": True, "produkt": "Bewerbungs-Management-System",
        "version": version, "vorschau": False,
    }


def _paket_bauen(ziel_ordner: Path, dateiname: str, version: str, dateien: dict[str, bytes]) -> Path:
    ziel_ordner.mkdir(parents=True, exist_ok=True)
    zip_pfad = ziel_ordner / dateiname
    with zipfile.ZipFile(zip_pfad, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("bms_manifest.json",
                    json.dumps(_manifest_bauen(version, dateien), ensure_ascii=False, indent=1,
                               sort_keys=True) + "\n")
        for pfad, inhalt in dateien.items():
            zf.writestr(pfad, inhalt)
    return zip_pfad


GRUNDDATEIEN = {
    "scripts/bms_update.py": _EIGENES_SKRIPT,
    "backend/requirements-lock.txt": b"fastapi==1.0.0\n",
    "frontend/package-lock.json": b"{}\n",
}


def _installation_bauen(wurzel: Path, version: str) -> Path:
    installation = wurzel / "BMS"
    for pfad, inhalt in GRUNDDATEIEN.items():
        ziel = installation / pfad
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(inhalt)
    (installation / "bms_manifest.json").write_text(
        json.dumps(_manifest_bauen(version, GRUNDDATEIEN), ensure_ascii=False, indent=1,
                   sort_keys=True) + "\n", encoding="utf-8")
    (installation / "frontend" / "dist").mkdir(parents=True, exist_ok=True)
    (installation / "frontend" / "dist" / "index.html").write_bytes(b"<html></html>")
    return installation


def _verzeichnis_hashes(basis: Path, *, ausschluss=("data",)) -> dict[str, str]:
    ergebnis = {}
    for pfad in basis.rglob("*"):
        if pfad.is_file():
            rel = pfad.relative_to(basis)
            if rel.parts and rel.parts[0] in ausschluss:
                continue
            ergebnis[rel.as_posix()] = _sha256(pfad.read_bytes())
    return ergebnis


def _download_pfad(version: str, name: str) -> str:
    return f"/{REPO}/releases/download/v{version}/{name}"


# ── Probeserver (spielt GitHub) ──────────────────────────────────────────────────────────────
@dataclass
class Anfrage:
    methode: str
    pfad: str
    query: str
    kopf: dict[str, str]
    kopf_namen: list[str]
    rumpf: bytes


@dataclass
class Antwort:
    status: int = 200
    typ: str | None = "application/json"
    body: bytes = b""
    kopf: dict[str, str] = field(default_factory=dict)
    content_length: Union[int, str, None] = "auto"    # "auto" = len(body), None = keine Kopfzeile
    warten_vor_antwort: bool = False                  # haengt, bis der Test endet (Zeitgrenze)
    stocken_nach: int | None = None                   # sendet so viele Byte, haengt dann
    trennen: bool = False                             # schliesst die Verbindung ohne jede Antwort


class _Handler(BaseHTTPRequestHandler):
    server_version = "Probe"
    sys_version = ""

    def setup(self):
        super().setup()
        self.server.probe.verbindungen += 1

    def log_message(self, *args):
        pass

    def _bearbeiten(self):
        probe = self.server.probe
        teile = urlsplit(self.path)          # auch die Absolut-Form ("GET http://host/pfad"), wie bei einem Proxy
        laenge = int(self.headers.get("Content-Length") or 0)
        rumpf = self.rfile.read(laenge) if laenge else b""
        anfrage = Anfrage(self.command, teile.path, teile.query,
                          {k.lower(): v for k, v in self.headers.items()},
                          [k.lower() for k in self.headers.keys()], rumpf)
        antwort = probe.beantworten(anfrage)
        if antwort.trennen:
            self.close_connection = True
            return
        if antwort.warten_vor_antwort:
            probe.freigabe.wait(15)
            return
        self.send_response(antwort.status)
        if antwort.typ is not None:
            self.send_header("Content-Type", antwort.typ)
        laenge_senden = len(antwort.body) if antwort.content_length == "auto" else antwort.content_length
        if laenge_senden is not None:
            self.send_header("Content-Length", str(laenge_senden))
        for name, wert in antwort.kopf.items():
            self.send_header(name, wert)
        self.end_headers()
        if antwort.stocken_nach is not None:
            self.wfile.write(antwort.body[:antwort.stocken_nach])
            self.wfile.flush()
            probe.freigabe.wait(15)
            return
        self.wfile.write(antwort.body)

    do_GET = _bearbeiten
    do_POST = _bearbeiten


class _ProbeServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        art = sys.exc_info()[0]
        if art is not None and issubclass(art, (ConnectionError, TimeoutError, ssl.SSLError)):
            return          # der Client hat die Verbindung selbst beendet (gewollt, z. B. Abbruch)
        self.probe.handler_fehler.append(repr(sys.exc_info()[1]))


Regel = Union[Antwort, Callable[[Anfrage], Antwort], None]


class Probe:
    def __init__(self, tls_kontext: ssl.SSLContext | None = None):
        self.anfragen: list[Anfrage] = []
        self.verbindungen = 0
        self.handler_fehler: list[str] = []
        self.routen: dict[str, Regel] = {}          # exakter Pfad -> Antwort oder Regel
        self.freigabe = threading.Event()
        self._sperre = threading.Lock()
        self.server = _ProbeServer(("127.0.0.1", 0), _Handler)
        self.server.probe = self
        if tls_kontext is not None:
            self.server.socket = tls_kontext.wrap_socket(self.server.socket, server_side=True)
        self.port = self.server.server_address[1]
        self._thread = threading.Thread(target=self.server.serve_forever,
                                        kwargs={"poll_interval": 0.02}, daemon=True)
        self._thread.start()

    @property
    def host(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def lokal(self) -> str:
        """Dieselbe Adresse unter einem anderen Namen: fuer eine Umleitung zu einem "anderen" Host."""
        return f"http://localhost:{self.port}"

    def beantworten(self, anfrage: Anfrage) -> Antwort:
        with self._sperre:
            self.anfragen.append(anfrage)
        if anfrage.pfad == "/ziel":
            return Antwort(200, "text/plain; charset=utf-8", b"Ziel erreicht\n")
        regel = self.routen.get(anfrage.pfad)
        if regel is None:
            return Antwort(404, None, b"")
        return regel(anfrage) if callable(regel) else regel

    def zaehlen(self, ende: str) -> int:
        return sum(1 for a in self.anfragen if a.pfad.endswith(ende))

    def beenden(self):
        self.freigabe.set()
        self.server.shutdown()
        self.server.server_close()
        self._thread.join(5)


@pytest.fixture()
def probe():
    p = Probe()
    yield p
    p.beenden()
    assert p.handler_fehler == [], f"Fehler im Probeserver: {p.handler_fehler}"


# ── Umgebung eines Tests ─────────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _kein_fremdes_netz(monkeypatch):
    """Zweite Sicherung neben dem Probeserver: nur Loopback darf aufgeloest werden."""
    echt = socket.getaddrinfo

    def nur_lokal(host, *args, **kwargs):
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise AssertionError(f"Test greift auf das Netz zu: {host!r}")
        return echt(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", nur_lokal)
    # Proxy-Einstellungen des Rechners (Umgebung, macOS-Systemeinstellungen) duerfen den Weg zum
    # Probeserver nicht beeinflussen.
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {})


def _anwenden(ziel: dict, abweichung: dict | None) -> None:
    for name, wert in (abweichung or {}).items():
        if wert is WEG:
            ziel.pop(name, None)
        else:
            ziel[name] = wert


class Umgebung:
    """Alles, was ein Test rund um das Werkzeug braucht, unter tmp_path."""

    def __init__(self, wurzel: Path, probe: Probe, monkeypatch):
        self.wurzel = wurzel
        self.probe = probe
        self.monkeypatch = monkeypatch
        self.home = wurzel / "home"
        self.downloads = self.home / "Downloads"
        self.secrets = wurzel / "secrets"
        self.installation = _installation_bauen(wurzel, "1.0.0")
        self.pakete = self.installation / "data" / "updates" / "pakete"
        self._pakete_bytes: dict[str, bytes] = {}
        self.angebot: str | None = None          # die zuletzt mit anbieten() angebotene Version

        self.secrets.mkdir()
        (self.home / ".bewerbung_mgmt_secrets").mkdir(parents=True)
        (self.secrets / ALTE_LIZENZDATEI).write_bytes(LIZENZ_BYTES)
        (self.home / ".bewerbung_mgmt_secrets" / ALTE_LIZENZDATEI).write_bytes(LIZENZ_BYTES)
        monkeypatch.setenv("HOME", str(self.home))
        monkeypatch.setenv("USERPROFILE", str(self.home))
        monkeypatch.setenv("BMS_SECRETS_DIR", str(self.secrets))
        monkeypatch.delenv("BMS_DATA_DIR", raising=False)   # conftest setzt es sessionweit
        monkeypatch.setattr(bms_update, "GITHUB_API", probe.host)
        monkeypatch.setattr(bms_update, "GITHUB_SEITE", probe.host)
        monkeypatch.setattr(bms_update, "_laeuft_nicht_in_venv", lambda: False)
        monkeypatch.setattr(bms_update, "_server_laeuft", lambda port=None: False)

    # -- Aufruf --
    def start(self, *zusatz: str) -> int:
        return bms_update.main(["--installation", str(self.installation), *zusatz])

    def aktualisieren(self, *zusatz: str) -> int:
        return self.start(*_STANDARD, *zusatz)

    # -- Pakete --
    def dateien(self, version: str, ersatz: dict[str, bytes] | None = None) -> dict[str, bytes]:
        return {**GRUNDDATEIEN, "backend/neu.py": f"# Version {version}\n".encode(), **(ersatz or {})}

    def paket_bytes(self, version: str, ersatz: dict[str, bytes] | None = None) -> bytes:
        schluessel = version + repr(sorted((ersatz or {}).items()))
        if schluessel not in self._pakete_bytes:
            pfad = _paket_bauen(self.wurzel / "server", f"BMS_{version}.zip", version,
                                self.dateien(version, ersatz))
            self._pakete_bytes[schluessel] = pfad.read_bytes()
            pfad.unlink()
        return self._pakete_bytes[schluessel]

    def download_paket(self, version: str) -> Path:
        return _paket_bauen(self.downloads, f"BMS_{version}.zip", version, self.dateien(version))

    # -- GitHub spielen --
    def zip_pfad(self, version: str) -> str:
        return _download_pfad(version, f"BMS_{version}.zip")

    def anbieten(self, version: str, /, *, ersatz: dict[str, bytes] | None = None,
                 release: dict | None = None, asset: dict | None = None,
                 pruefsummendatei: bytes | None = None) -> bytes:
        """GitHub hat `version` als neuestes Release (Felder wie bei der echten API, am 29.10.2026
        live geprueft): `release` und `asset` ueberschreiben Felder (WEG entfernt sie),
        `pruefsummendatei` legt zusaetzlich das Asset `BMS_<version>.zip.sha256` an. Gibt die Bytes
        des Pakets zurueck."""
        paket = self.paket_bytes(version, ersatz)
        self.angebot = version
        zip_name = f"BMS_{version}.zip"
        zip_pfad = self.zip_pfad(version)
        paket_asset = {"name": zip_name, "size": len(paket), "digest": "sha256:" + _sha256(paket),
                       "content_type": "application/zip", "state": "uploaded",
                       "browser_download_url": self.probe.host + zip_pfad}
        _anwenden(paket_asset, asset)
        assets = [paket_asset]
        if pruefsummendatei is not None:
            datei_name = zip_name + ".sha256"
            datei_pfad = _download_pfad(version, datei_name)
            assets.append({"name": datei_name, "size": len(pruefsummendatei),
                           "digest": "sha256:" + _sha256(pruefsummendatei),
                           "browser_download_url": self.probe.host + datei_pfad})
            self.probe.routen[datei_pfad] = Antwort(200, "application/octet-stream", pruefsummendatei)
        daten = {"tag_name": f"v{version}", "name": f"BMS {version}", "draft": False,
                 "prerelease": False, "published_at": "2026-11-15T09:00:00Z",
                 "html_url": f"{self.probe.host}/{REPO}/releases/tag/v{version}",
                 "body": "- Neu", "assets": assets}
        _anwenden(daten, release)
        self.probe.routen[RELEASE_PFAD] = Antwort(200, "application/json; charset=utf-8",
                                                  json.dumps(daten).encode("utf-8"))
        self.probe.routen[zip_pfad] = Antwort(200, "application/octet-stream", paket)
        return paket

    def release_roh(self, antwort: Antwort) -> None:
        self.probe.routen[RELEASE_PFAD] = antwort

    def laden_setzen(self, antwort: Regel, version: str | None = None) -> None:
        """Ersetzt die Antwort auf den Download des (zuletzt) angebotenen Pakets."""
        self.probe.routen[self.zip_pfad(version or self.angebot)] = antwort

    def erlaube_hosts(self, *hosts: str) -> None:
        """Ersetzt die Zielpruefung der Umleitungen durch eine Regel fuer den Probeserver: erlaubt
        sind genau diese Hostnamen (der echte Test der Regel steht weiter unten)."""
        erlaubt = set(hosts)
        self.monkeypatch.setattr(bms_update, "_ziel_erlaubt",
                                 lambda adresse: urlsplit(adresse).hostname in erlaubt)

    def kette_aufbauen(self, anzahl: int, version: str = "1.1.0", code: int = 302) -> str:
        """Das Paket liegt hinter `anzahl` Umleitungen (alle auf den Namen "localhost" desselben
        Probeservers). Gibt den Pfad des Endziels zurueck."""
        paket = self.paket_bytes(version)
        wege = [self.zip_pfad(version)] + [f"/weg{i}" for i in range(1, anzahl)] + [f"/cdn/BMS_{version}.zip"]
        for i in range(anzahl):
            self.probe.routen[wege[i]] = Antwort(code, None, b"", {"Location": self.probe.lokal + wege[i + 1]})
        self.probe.routen[wege[-1]] = Antwort(200, "application/octet-stream", paket)
        return wege[-1]

    # -- Ergebnis --
    def installierte_version(self) -> str:
        return json.loads((self.installation / "bms_manifest.json").read_text(encoding="utf-8"))["version"]

    def unveraendert(self) -> dict[str, str]:
        return _verzeichnis_hashes(self.installation)


@pytest.fixture()
def umgebung(tmp_path, monkeypatch, probe):
    return Umgebung(tmp_path, probe, monkeypatch)


@pytest.fixture()
def freier_port():
    """Ein Port, an dem nichts lauscht (Verbindung wird abgelehnt)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _tot(umgebung, freier_port):
    umgebung.monkeypatch.setattr(bms_update, "GITHUB_API", f"http://127.0.0.1:{freier_port}")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Ablauf von Schritt 2
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_hoehere_version_online_wird_geladen_geprueft_und_eingespielt(umgebung, capsys):
    paket = umgebung.anbieten("1.1.0")

    code = umgebung.aktualisieren()
    out = capsys.readouterr().out

    assert code == 0, out
    geladen = umgebung.pakete / "BMS_1.1.0.zip"
    assert geladen.read_bytes() == paket
    assert list(umgebung.pakete.iterdir()) == [geladen]            # keine .teil-Reste
    assert umgebung.installierte_version() == "1.1.0"
    assert (umgebung.installation / "backend" / "neu.py").read_bytes() == b"# Version 1.1.0\n"
    assert ("Suche auf GitHub nach einer neuen Version. GitHub erhält dabei die IP-Adresse "
            "dieses Rechners.") in out
    assert re.search(r"Version 1\.1\.0 gefunden, lade \d+,\d MB …", out)
    assert "Paket geladen und geprüft." in out
    assert "Update auf Version 1.1.0 abgeschlossen" in out
    assert [(a.methode, a.pfad) for a in umgebung.probe.anfragen] == [
        ("GET", RELEASE_PFAD), ("GET", umgebung.zip_pfad("1.1.0"))]
    assert not umgebung.downloads.exists()                          # der Download-Ordner bleibt unberuehrt


def test_groessenangabe_in_megabyte_mit_komma():
    assert bms_update._groesse_mb(4_699_463) == "4,7"
    assert bms_update._groesse_mb(1_000_000) == "1,0"
    assert bms_update._groesse_mb(40_000) == "0,1"          # nie "0,0"


def test_gleiche_version_online_ohne_kandidat_ist_auf_dem_neuesten_stand(umgebung, capsys):
    umgebung.anbieten("1.0.0")
    vorher = umgebung.unveraendert()

    code = umgebung.aktualisieren()
    out = capsys.readouterr().out

    assert code == 0
    assert "Ihr BMS ist auf dem neuesten Stand (Version 1.0.0)." in out
    assert umgebung.probe.zaehlen(".zip") == 0
    assert umgebung.unveraendert() == vorher
    assert not umgebung.pakete.exists()


def test_aeltere_version_online_ohne_kandidat_ist_auf_dem_neuesten_stand(umgebung, capsys):
    umgebung.anbieten("0.9.0")
    code = umgebung.aktualisieren()
    assert code == 0
    assert "auf dem neuesten Stand (Version 1.0.0)" in capsys.readouterr().out
    assert umgebung.probe.zaehlen(".zip") == 0


def test_gleiche_version_online_mit_erzwingen_wird_geladen(umgebung, capsys):
    paket = umgebung.anbieten("1.0.0")

    code = umgebung.aktualisieren("--erzwingen")
    out = capsys.readouterr().out

    assert code == 0, out
    assert (umgebung.pakete / "BMS_1.0.0.zip").read_bytes() == paket
    assert umgebung.probe.zaehlen(".zip") == 1
    assert "neuesten Stand" not in out


def test_aeltere_version_online_mit_erzwingen_wird_nicht_geladen(umgebung, capsys):
    umgebung.anbieten("0.9.0")
    assert umgebung.aktualisieren("--erzwingen") == 0
    assert "auf dem neuesten Stand" in capsys.readouterr().out
    assert umgebung.probe.zaehlen(".zip") == 0


def test_hoehere_version_in_downloads_gewinnt_ohne_download(umgebung, capsys):
    umgebung.anbieten("1.1.0")
    umgebung.download_paket("1.2.0")

    code = umgebung.aktualisieren()

    assert code == 0, capsys.readouterr().out
    assert umgebung.installierte_version() == "1.2.0"
    assert umgebung.probe.zaehlen("/latest") == 1          # gefragt wird, geladen nicht
    assert umgebung.probe.zaehlen(".zip") == 0
    assert not umgebung.pakete.exists()


def test_gleiche_version_in_downloads_wie_online_gewinnt_lokal(umgebung):
    umgebung.anbieten("1.1.0")
    umgebung.download_paket("1.1.0")
    assert umgebung.aktualisieren() == 0
    assert umgebung.installierte_version() == "1.1.0"
    assert umgebung.probe.zaehlen(".zip") == 0


def test_hoehere_version_online_als_in_downloads_gewinnt_online(umgebung, capsys):
    umgebung.anbieten("1.2.0")
    umgebung.download_paket("1.1.0")

    code = umgebung.aktualisieren()

    assert code == 0, capsys.readouterr().out
    assert umgebung.installierte_version() == "1.2.0"
    assert umgebung.probe.zaehlen(".zip") == 1


# ── Fehler der Online-Suche sind Hinweise, keine Abbrueche ──────────────────────────────────
def _antwort_auf_release(antwort: Antwort):
    def einrichten(umgebung, freier_port):
        umgebung.release_roh(antwort)
    return einrichten


def _umleitung(umgebung, freier_port):
    umgebung.release_roh(Antwort(302, None, b"", {"Location": umgebung.probe.host + "/ziel"}))


def _mit_abweichung(**abweichung):
    def einrichten(umgebung, freier_port):
        umgebung.anbieten("1.1.0", **abweichung)
    return einrichten


FEHLERFAELLE = {
    "nicht_erreichbar": (_tot, T_KEINE_VERBINDUNG),
    "404_noch_keine_version": (_antwort_auf_release(Antwort(404, "application/json",
                                                             b'{"message": "Not Found"}')),
                               T_KEINE_VERSION),
    "403_anfragegrenze": (_antwort_auf_release(Antwort(
        403, "application/json", b'{"message": "API rate limit exceeded for 203.0.113.7."}',
        {"X-RateLimit-Remaining": "0"})), T_GRENZE),
    "429_anfragegrenze": (_antwort_auf_release(Antwort(429, "text/plain", b"Too Many Requests\n")),
                          T_GRENZE),
    "500_serverfehler": (_antwort_auf_release(Antwort(500, "application/json", b"{}")), T_UNGUELTIG),
    "503_html": (_antwort_auf_release(Antwort(503, "text/html", b"<h1>Interne Fehlerseite</h1>")),
                 T_UNGUELTIG),
    "302_umleitung": (_umleitung, T_UNGUELTIG),
    "204_statt_200": (_antwort_auf_release(Antwort(204, None, b"")), T_UNGUELTIG),
    "kaputtes_json": (_antwort_auf_release(Antwort(200, "application/json",
                                                   b"<html>Anmeldung am Firmennetz</html>")), T_UNGUELTIG),
    "falsches_tag_name": (_mit_abweichung(release={"tag_name": "latest"}), T_UNGUELTIG),
    "fremde_download_url": (_mit_abweichung(asset={"browser_download_url":
                                                   "https://evil.example/BMS_1.1.0.zip"}), T_UNGUELTIG),
    "digest_fehlt_ohne_sha256_asset": (_mit_abweichung(asset={"digest": WEG}), T_PRUEFSUMME),
}


def test_abgerissene_verbindung_ohne_antwort_hat_einen_eigenen_text(umgebung):
    umgebung.release_roh(Antwort(trennen=True))
    with pytest.raises(OnlineFehler) as exc:
        bms_update.online_auskunft()
    assert str(exc.value) == T_UNTERBROCHEN
    assert umgebung.probe.zaehlen("/latest") == 1


@pytest.mark.parametrize("fall", list(FEHLERFAELLE))
def test_fehler_der_online_suche_ohne_kandidat_bricht_mit_grund_ab(umgebung, freier_port, capsys, fall):
    einrichten, grund = FEHLERFAELLE[fall]
    einrichten(umgebung, freier_port)
    vorher = umgebung.unveraendert()

    code = umgebung.aktualisieren()
    out = capsys.readouterr().out

    assert code == 1, out
    assert f"Online-Suche nicht möglich: {grund}" in out
    zeilen = out.strip().splitlines()
    assert zeilen[-1].startswith("Kein Update-Paket gefunden.")       # der bisherige Abbruchtext ...
    assert zeilen[-1].endswith(f"Online-Suche nicht möglich: {grund}")  # ... ergaenzt um den Grund
    assert "Interne Fehlerseite" not in out and "203.0.113.7" not in out    # Text des Servers wird nie gezeigt
    assert umgebung.unveraendert() == vorher
    assert umgebung.probe.zaehlen(".zip") == 0
    assert umgebung.probe.zaehlen("/ziel") == 0                       # die Auskunft folgt keiner Umleitung
    assert not umgebung.pakete.exists()


@pytest.mark.parametrize("fall", list(FEHLERFAELLE))
def test_fehler_der_online_suche_mit_kandidat_geht_ueber_downloads_weiter(umgebung, freier_port,
                                                                          capsys, fall):
    einrichten, grund = FEHLERFAELLE[fall]
    einrichten(umgebung, freier_port)
    umgebung.download_paket("1.1.0")

    code = umgebung.aktualisieren()
    out = capsys.readouterr().out

    assert code == 0, out
    assert f"Online-Suche nicht möglich: {grund}" in out
    assert umgebung.installierte_version() == "1.1.0"
    assert umgebung.probe.zaehlen(".zip") == 0
    assert umgebung.probe.zaehlen("/ziel") == 0


def test_antwortet_github_nicht_rechtzeitig_ist_das_ein_hinweis(umgebung, capsys):
    umgebung.monkeypatch.setattr(bms_update, "ZEIT_AUSKUNFT_S", 0.3)
    umgebung.release_roh(Antwort(warten_vor_antwort=True))
    umgebung.download_paket("1.1.0")

    code = umgebung.aktualisieren()
    out = capsys.readouterr().out

    assert code == 0, out
    assert f"Online-Suche nicht möglich: {T_ZEIT}" in out
    assert umgebung.installierte_version() == "1.1.0"


# ── Keine Lizenzdatei: weder gelesen noch gesendet ──────────────────────────────────────────
def test_lizenzdatei_wird_weder_gelesen_noch_gesendet(umgebung, capsys, monkeypatch):
    umgebung.anbieten("1.1.0")
    geoeffnet: list[str] = []
    echt_open = io.open

    def aufzeichnen(datei, *args, **kwargs):
        try:
            geoeffnet.append(os.fspath(datei))
        except TypeError:
            pass                    # Dateideskriptor (int): kein Pfad
        return echt_open(datei, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", aufzeichnen)
    monkeypatch.setattr(io, "open", aufzeichnen)

    code = umgebung.aktualisieren()
    out = capsys.readouterr()

    assert code == 0, out.out
    assert [p for p in geoeffnet if "lizenz" in os.path.basename(p).lower()] == []
    for anfrage in umgebung.probe.anfragen:             # nichts davon ging ueber die Leitung
        gesendet = json.dumps([anfrage.pfad, anfrage.query, anfrage.kopf]) + anfrage.rumpf.decode("latin-1")
        for marker in LIZENZ_MARKER:
            assert marker not in gesendet
    for marker in LIZENZ_MARKER:
        assert marker not in out.out + out.err
    assert "Lizenz" not in out.out                               # kein Kundentext erwaehnt sie noch


def test_lizenzdatei_fehlt_oder_ist_da_aendert_nichts_am_ablauf(umgebung, capsys):
    umgebung.anbieten("1.1.0")
    (umgebung.secrets / ALTE_LIZENZDATEI).unlink()
    (umgebung.home / ".bewerbung_mgmt_secrets" / ALTE_LIZENZDATEI).unlink()

    code = umgebung.aktualisieren()
    out = capsys.readouterr().out

    assert code == 0, out
    assert umgebung.installierte_version() == "1.1.0"
    assert "Online-Suche übersprungen" not in out and "Lizenz" not in out


def test_das_werkzeug_kennt_keine_lizenzfunktionen_mehr():
    assert not hasattr(bms_update, "_lizenz_pfad")
    assert not hasattr(bms_update, "PAKETDIENST")
    assert not hasattr(bms_update, "_neuere_version_melden")
    for verboten in (ALTE_LIZENZDATEI, ALTER_DIENST, "PAKETDIENST", "updates_bis", "neuere_version"):
        assert verboten not in _QUELLTEXT, f"„{verboten}“ steht noch im Quelltext von bms_update.py"


# ── --offline und Pfad-Argument: keine einzige Anfrage ──────────────────────────────────────
def test_offline_stellt_keine_anfrage_und_nimmt_downloads(umgebung, capsys):
    umgebung.anbieten("1.5.0")
    umgebung.download_paket("1.1.0")

    code = umgebung.aktualisieren("--offline")
    out = capsys.readouterr().out

    assert code == 0, out
    assert umgebung.installierte_version() == "1.1.0"
    assert umgebung.probe.anfragen == [] and umgebung.probe.verbindungen == 0
    assert "GitHub" not in out


def test_offline_ohne_kandidat_bricht_ab_ohne_anfrage(umgebung, capsys):
    umgebung.anbieten("1.5.0")

    code = umgebung.aktualisieren("--offline")
    out = capsys.readouterr().out

    assert code == 1
    assert "Kein Update-Paket gefunden." in out and "--offline" in out
    assert umgebung.probe.anfragen == [] and umgebung.probe.verbindungen == 0


def test_pfad_argument_stellt_keine_anfrage(umgebung, capsys):
    umgebung.anbieten("1.5.0")
    eigenes = _paket_bauen(umgebung.wurzel / "irgendwo", "BMS_1.1.0.zip", "1.1.0", umgebung.dateien("1.1.0"))

    code = umgebung.aktualisieren(str(eigenes))

    assert code == 0, capsys.readouterr().out
    assert umgebung.installierte_version() == "1.1.0"
    assert umgebung.probe.anfragen == [] and umgebung.probe.verbindungen == 0


def test_pfad_argument_und_offline_zusammen_stellen_keine_anfrage(umgebung):
    umgebung.anbieten("1.5.0")
    eigenes = _paket_bauen(umgebung.wurzel / "irgendwo", "BMS_1.1.0.zip", "1.1.0", umgebung.dateien("1.1.0"))
    assert umgebung.aktualisieren(str(eigenes), "--offline") == 0
    assert umgebung.probe.verbindungen == 0


def test_zurueck_und_git_checkout_stellen_keine_anfrage(umgebung):
    umgebung.anbieten("1.5.0")
    assert umgebung.start("--zurueck", "--ja") == 1          # es gibt kein Update zum Zuruecknehmen
    (umgebung.installation / ".git").mkdir()
    assert umgebung.aktualisieren() == 1                     # Weigerung im Git-Checkout (Schritt 1)
    assert umgebung.probe.verbindungen == 0


def test_pruefen_laedt_das_paket_und_aendert_nichts(umgebung, capsys):
    paket = umgebung.anbieten("1.1.0")
    vorher = umgebung.unveraendert()

    code = umgebung.start("--pruefen")
    out = capsys.readouterr().out

    assert code == 0, out
    assert "Neue Version: 1.1.0" in out
    assert (umgebung.pakete / "BMS_1.1.0.zip").read_bytes() == paket     # bleibt liegen
    assert umgebung.unveraendert() == vorher
    assert umgebung.installierte_version() == "1.0.0"


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Pruefsumme: digest, sonst .sha256-Asset, sonst kein Einspielen (Leitentscheidung 5)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_digest_fehlt_mit_pruefsummendatei_wird_sie_genommen(umgebung, capsys):
    paket = umgebung.paket_bytes("1.1.0")
    datei = f"{_sha256(paket)}  BMS_1.1.0.zip\n".encode()
    umgebung.anbieten("1.1.0", asset={"digest": WEG}, pruefsummendatei=datei)

    code = umgebung.aktualisieren()

    assert code == 0, capsys.readouterr().out
    assert umgebung.installierte_version() == "1.1.0"
    assert [a.pfad for a in umgebung.probe.anfragen] == [
        RELEASE_PFAD, _download_pfad("1.1.0", "BMS_1.1.0.zip.sha256"), umgebung.zip_pfad("1.1.0")]


@pytest.mark.parametrize("digest", [WEG, None], ids=["fehlt", "null"])
def test_digest_null_oder_fehlend_gilt_gleich(umgebung, digest):
    """GitHub liefert `digest: null` fuer Assets, die vor Juni 2025 hochgeladen wurden."""
    paket = umgebung.paket_bytes("1.1.0")
    umgebung.anbieten("1.1.0", asset={"digest": digest}, pruefsummendatei=_sha256(paket).encode())
    assert bms_update.online_auskunft()["sha256"] == _sha256(paket)


def test_pruefsummendatei_gross_geschrieben_mit_windows_zeilenende_wird_gelesen(umgebung):
    paket = umgebung.paket_bytes("1.1.0")
    umgebung.anbieten("1.1.0", asset={"digest": WEG},
                      pruefsummendatei=(_sha256(paket).upper() + " *BMS_1.1.0.zip\r\n").encode())
    assert bms_update.online_auskunft()["sha256"] == _sha256(paket)


def test_pruefsummendatei_darf_ueber_eine_erlaubte_umleitung_kommen(umgebung):
    paket = umgebung.paket_bytes("1.1.0")
    umgebung.anbieten("1.1.0", asset={"digest": WEG}, pruefsummendatei=b"wird ersetzt")
    datei_pfad = _download_pfad("1.1.0", "BMS_1.1.0.zip.sha256")
    umgebung.probe.routen["/cdn/summe"] = Antwort(200, "text/plain", _sha256(paket).encode())
    umgebung.probe.routen[datei_pfad] = Antwort(302, None, b"", {"Location": umgebung.probe.lokal + "/cdn/summe"})
    umgebung.erlaube_hosts("localhost")

    assert bms_update.online_auskunft()["sha256"] == _sha256(paket)


def test_digest_fehlt_ohne_pruefsummendatei_wird_nichts_geladen(umgebung, capsys):
    umgebung.anbieten("1.1.0", asset={"digest": WEG})
    vorher = umgebung.unveraendert()

    code = umgebung.aktualisieren()
    out = capsys.readouterr().out

    assert code == 1
    assert T_PRUEFSUMME in out
    assert umgebung.probe.zaehlen(".zip") == 0               # das Paket wird gar nicht erst geladen
    assert umgebung.unveraendert() == vorher


UNBRAUCHBARE_PRUEFSUMMENDATEIEN = {
    "leer": lambda u: Antwort(200, "text/plain", b""),
    "kein_hex": lambda u: Antwort(200, "text/plain", b"das ist keine pruefsumme\n"),
    "zu_kurz": lambda u: Antwort(200, "text/plain", ("ab" * 31).encode()),
    "zu_lang": lambda u: Antwort(200, "text/plain", ("ab" * 33).encode()),
    "ueber_4_kb": lambda u: Antwort(200, "text/plain", b"ab" * 40 + b" " * 5000),
    "404": lambda u: Antwort(404, None, b""),
    "500": lambda u: Antwort(500, None, b""),
    "fremde_umleitung": lambda u: Antwort(302, None, b"", {"Location": "https://evil.example/summe"}),
}


@pytest.mark.parametrize("fall", list(UNBRAUCHBARE_PRUEFSUMMENDATEIEN))
def test_unbrauchbare_pruefsummendatei_heisst_pruefsumme_fehlt(umgebung, fall):
    umgebung.anbieten("1.1.0", asset={"digest": WEG}, pruefsummendatei=b"x")
    umgebung.probe.routen[_download_pfad("1.1.0", "BMS_1.1.0.zip.sha256")] = \
        UNBRAUCHBARE_PRUEFSUMMENDATEIEN[fall](umgebung)
    with pytest.raises(OnlineFehler) as exc:
        bms_update.online_auskunft()
    assert str(exc.value) == T_PRUEFSUMME
    assert umgebung.probe.zaehlen("BMS_1.1.0.zip") == 0


def test_pruefsummendatei_mit_fremder_adresse_wird_nicht_geholt(umgebung):
    umgebung.anbieten("1.1.0", asset={"digest": WEG}, pruefsummendatei=b"x")
    daten = json.loads(umgebung.probe.routen[RELEASE_PFAD].body)
    daten["assets"][1]["browser_download_url"] = "https://evil.example/BMS_1.1.0.zip.sha256"
    umgebung.release_roh(Antwort(200, "application/json", json.dumps(daten).encode()))
    with pytest.raises(OnlineFehler) as exc:
        bms_update.online_auskunft()
    assert str(exc.value) == T_PRUEFSUMME
    assert umgebung.probe.zaehlen(".sha256") == 0


def test_anfragegrenze_bei_der_pruefsummendatei_bleibt_eine_anfragegrenze(umgebung):
    umgebung.anbieten("1.1.0", asset={"digest": WEG}, pruefsummendatei=b"x")
    umgebung.probe.routen[_download_pfad("1.1.0", "BMS_1.1.0.zip.sha256")] = Antwort(429, None, b"")
    with pytest.raises(OnlineFehler) as exc:
        bms_update.online_auskunft()
    assert str(exc.value) == T_GRENZE


def test_falsche_pruefsummendatei_verwirft_das_geladene_paket(umgebung, capsys):
    umgebung.anbieten("1.1.0", asset={"digest": WEG}, pruefsummendatei=("ab" * 32).encode())
    vorher = umgebung.unveraendert()

    code = umgebung.aktualisieren()
    out = capsys.readouterr().out

    assert code == 1
    assert T_BESCHAEDIGT in out
    assert umgebung.unveraendert() == vorher
    assert list(umgebung.pakete.iterdir()) == []


def test_digest_hat_vorrang_vor_der_pruefsummendatei(umgebung):
    paket = umgebung.paket_bytes("1.1.0")
    umgebung.anbieten("1.1.0", pruefsummendatei=("ab" * 32).encode())      # digest bleibt der echte
    auskunft = bms_update.online_auskunft()
    assert auskunft["sha256"] == _sha256(paket)
    assert umgebung.probe.zaehlen(".sha256") == 0               # die Datei wird gar nicht geholt


# ── Pruefung des geladenen Pakets ───────────────────────────────────────────────────────────
def _falscher_digest(umgebung, paket):
    # Der Download ist in sich stimmig (Groesse), aber GitHub nennt eine andere Summe.
    daten = json.loads(umgebung.probe.routen[RELEASE_PFAD].body)
    daten["assets"][0]["digest"] = "sha256:" + "ab" * 32
    umgebung.release_roh(Antwort(200, "application/json", json.dumps(daten).encode("utf-8")))


def _verfaelschter_inhalt(umgebung, paket):
    schlecht = bytes([paket[0] ^ 0xFF]) + paket[1:]          # gleiche Laenge, anderer Inhalt
    umgebung.laden_setzen(Antwort(200, "application/octet-stream", schlecht))


def _release_nennt_7_byte_zu_viel(umgebung, paket):
    daten = json.loads(umgebung.probe.routen[RELEASE_PFAD].body)
    daten["assets"][0]["size"] = len(paket) + 7
    umgebung.release_roh(Antwort(200, "application/json", json.dumps(daten).encode("utf-8")))


def _mehr_byte_als_angekuendigt(umgebung, paket):
    # Keine Content-Length: der Strom laeuft weiter als die angekuendigte Groesse.
    umgebung.laden_setzen(Antwort(200, "application/octet-stream", paket + b"x" * 200_000,
                                  content_length=None))


def _mehr_byte_als_die_groesse_sagt(umgebung, paket):
    umgebung.laden_setzen(Antwort(200, "application/octet-stream", paket + b"x" * 50))


def _abgebrochene_uebertragung(umgebung, paket):
    # Content-Length verspricht das ganze Paket, es kommen aber 10 Byte zu wenig.
    umgebung.laden_setzen(Antwort(200, "application/octet-stream", paket[:-10], content_length=len(paket)))


def _groesse_stimmt_nicht_ohne_content_length(umgebung, paket):
    # Pruefsumme des Pakets stimmt, die angekuendigte Groesse nicht, und es gibt keine
    # Content-Length: nur der Vergleich mit `size` deckt das auf.
    _release_nennt_7_byte_zu_viel(umgebung, paket)
    umgebung.laden_setzen(Antwort(200, "application/octet-stream", paket, content_length=None))


def _leere_antwort(umgebung, paket):
    umgebung.laden_setzen(Antwort(200, "application/octet-stream", b"", content_length=None))


INTEGRITAETSFAELLE = [_falscher_digest, _verfaelschter_inhalt, _release_nennt_7_byte_zu_viel,
                      _groesse_stimmt_nicht_ohne_content_length, _mehr_byte_als_angekuendigt,
                      _mehr_byte_als_die_groesse_sagt, _abgebrochene_uebertragung, _leere_antwort]


@pytest.mark.parametrize("verderben", INTEGRITAETSFAELLE, ids=lambda f: f.__name__.strip("_"))
def test_beschaedigtes_paket_wird_nicht_eingespielt_und_aufgeraeumt(umgebung, capsys, verderben):
    paket = umgebung.anbieten("1.1.0")
    verderben(umgebung, paket)
    vorher = umgebung.unveraendert()

    code = umgebung.aktualisieren()
    out = capsys.readouterr().out

    assert code == 1, out
    assert T_BESCHAEDIGT in out
    assert "Kein Update-Paket gefunden." in out
    assert umgebung.unveraendert() == vorher
    assert list(umgebung.pakete.iterdir()) == []             # weder .zip noch .teil


@pytest.mark.parametrize("verderben", INTEGRITAETSFAELLE, ids=lambda f: f.__name__.strip("_"))
def test_beschaedigtes_paket_faellt_auf_downloads_zurueck(umgebung, capsys, verderben):
    paket = umgebung.anbieten("1.2.0")
    verderben(umgebung, paket)
    umgebung.download_paket("1.1.0")

    code = umgebung.aktualisieren()
    out = capsys.readouterr().out

    assert code == 0, out
    assert T_BESCHAEDIGT in out
    assert umgebung.installierte_version() == "1.1.0"
    assert list(umgebung.pakete.iterdir()) == []


class _EndlosAntwort:
    """Statt einer Antwort: ein Strom, der nie endet. Zaehlt, wie viel gelesen wurde."""

    def __init__(self):
        self.gelesen = 0
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, anzahl):
        self.gelesen += anzahl
        return b"x" * anzahl


def _auskunft_fuer(**felder) -> dict:
    """Eine Auskunft, wie `online_auskunft()` sie liefert (gueltig), mit `felder` als Abweichung."""
    auskunft = {"version": "1.1.0", "url": bms_update._download_url("1.1.0", "BMS_1.1.0.zip"),
                "groesse": 1000, "sha256": "ab" * 32, "seite": None}
    auskunft.update(felder)
    return auskunft


def test_paket_zu_gross_online_laden_liest_hoechstens_ein_byte_ueber_der_groesse(umgebung, tmp_path):
    strom = _EndlosAntwort()
    umgebung.monkeypatch.setattr(bms_update, "_online_oeffnen", lambda *a, **k: strom)
    ziel = tmp_path / "pakete" / "BMS_1.1.0.zip"

    with pytest.raises(OnlineFehler) as exc:
        bms_update.online_laden(_auskunft_fuer(groesse=100_000), ziel)

    assert str(exc.value) == T_BESCHAEDIGT
    assert 100_000 < strom.gelesen <= 100_001       # nicht mehr als die Groesse plus das eine Byte
    assert list(ziel.parent.iterdir()) == []


def test_paket_zu_gross_content_length_ueber_der_groesse_wird_gar_nicht_gelesen(umgebung, tmp_path):
    paket = umgebung.anbieten("1.1.0")
    umgebung.laden_setzen(Antwort(200, "application/octet-stream", paket + b"x" * 1000))
    ziel = tmp_path / "z" / "BMS_1.1.0.zip"

    with pytest.raises(OnlineFehler) as exc:
        bms_update.online_laden(bms_update.online_auskunft(), ziel)

    assert str(exc.value) == T_BESCHAEDIGT
    assert list(ziel.parent.iterdir()) == []


def test_dateiname_kommt_nur_aus_der_geprueften_versionsnummer(umgebung, tmp_path):
    paket = umgebung.anbieten("1.1.0", asset={"name": "BMS_1.1.0.zip"})
    umgebung.laden_setzen(Antwort(200, "application/octet-stream", paket,
                                  {"Content-Disposition": 'attachment; filename="../../evil.zip"'}))

    assert umgebung.aktualisieren() == 0
    assert [p.name for p in umgebung.pakete.iterdir()] == ["BMS_1.1.0.zip"]
    assert (umgebung.pakete / "BMS_1.1.0.zip").read_bytes() == paket
    assert not list(tmp_path.rglob("evil*"))


# ── Auskunft pruefen ────────────────────────────────────────────────────────────────────────
def _roh(daten) -> Antwort:
    return Antwort(200, "application/json", json.dumps(daten).encode("utf-8"))


def _gueltiges_release(u: Umgebung) -> dict:
    u.anbieten("1.7.0")
    return json.loads(u.probe.routen[RELEASE_PFAD].body)


def _asset_url(u: Umgebung, pfad: str) -> dict:
    return {"asset": {"browser_download_url": u.probe.host + pfad}}


UNGUELTIGE_RELEASES = {          # Name -> Funktion(Umgebung) -> Argumente fuer anbieten("1.7.0", ...)
    "tag_ohne_patch": lambda u: {"release": {"tag_name": "v1.7"}},
    "tag_mit_zeilenende": lambda u: {"release": {"tag_name": "v1.7.0\n"}},
    "tag_mit_buchstaben": lambda u: {"release": {"tag_name": "v1.7.x"}},
    "tag_mit_pfad": lambda u: {"release": {"tag_name": "v../1.7.0"}},
    "tag_mit_zusatz": lambda u: {"release": {"tag_name": "v1.7.0-beta"}},
    "tag_doppeltes_v": lambda u: {"release": {"tag_name": "vv1.7.0"}},
    "tag_latest": lambda u: {"release": {"tag_name": "latest"}},
    "tag_zehn_stellen": lambda u: {"release": {"tag_name": "v1234567890.0.0"}},
    "tag_keine_zeichenkette": lambda u: {"release": {"tag_name": 170}},
    "tag_fehlt": lambda u: {"release": {"tag_name": WEG}},
    "assets_fehlen": lambda u: {"release": {"assets": WEG}},
    "assets_keine_liste": lambda u: {"release": {"assets": "keine liste"}},
    "assets_leer": lambda u: {"release": {"assets": []}},
    "assets_nur_muell": lambda u: {"release": {"assets": [None, 5, "x", []]}},
    "paket_heisst_anders": lambda u: {"asset": {"name": "BMS_9.9.9.zip"}},
    "url_fremder_host": lambda u: {"asset": {"browser_download_url": "https://evil.example/BMS_1.7.0.zip"}},
    "url_anderes_repo": lambda u: _asset_url(u, "/jemand/anderes/releases/download/v1.7.0/BMS_1.7.0.zip"),
    "url_andere_version": lambda u: _asset_url(u, _download_pfad("1.6.0", "BMS_1.6.0.zip")),
    "url_anderer_dateiname": lambda u: _asset_url(u, _download_pfad("1.7.0", "evil.zip")),
    "url_mit_anhang": lambda u: {"asset": {"browser_download_url":
                                           u.probe.host + _download_pfad("1.7.0", "BMS_1.7.0.zip") + "?x=1"}},
    "url_fehlt": lambda u: {"asset": {"browser_download_url": WEG}},
    "url_keine_zeichenkette": lambda u: {"asset": {"browser_download_url": 5}},
    "groesse_null": lambda u: {"asset": {"size": 0}},
    "groesse_negativ": lambda u: {"asset": {"size": -5}},
    "groesse_zu_gross": lambda u: {"asset": {"size": 200 * 1024 * 1024 + 1}},
    "groesse_text": lambda u: {"asset": {"size": "4699463"}},
    "groesse_kommazahl": lambda u: {"asset": {"size": 4699463.5}},
    "groesse_wahrheitswert": lambda u: {"asset": {"size": True}},
    "groesse_fehlt": lambda u: {"asset": {"size": WEG}},
    "digest_falscher_algorithmus": lambda u: {"asset": {"digest": "sha1:" + "ab" * 20}},
    "digest_zu_kurz": lambda u: {"asset": {"digest": "sha256:" + "ab" * 31}},
    "digest_zu_lang": lambda u: {"asset": {"digest": "sha256:" + "ab" * 33}},
    "digest_kein_hex": lambda u: {"asset": {"digest": "sha256:" + "zz" * 32}},
    "digest_ohne_algorithmus": lambda u: {"asset": {"digest": "ab" * 32}},
    "digest_keine_zeichenkette": lambda u: {"asset": {"digest": 5}},
}


@pytest.mark.parametrize("fall", list(UNGUELTIGE_RELEASES))
def test_ungueltiges_release_ist_ein_fehler(umgebung, fall):
    umgebung.anbieten("1.7.0", **UNGUELTIGE_RELEASES[fall](umgebung))
    with pytest.raises(OnlineFehler) as exc:
        bms_update.online_auskunft()
    assert str(exc.value) == T_UNGUELTIG


UNGUELTIGE_ANTWORTEN = {
    "kein_json": b"<html>Anmeldung am Firmennetz</html>",
    "leer": b"",
    "json_liste": b"[]",
    "json_zahl": b"42",
    "json_null": b"null",
    "json_tief_verschachtelt": b"[" * 5000 + b"]" * 5000,
    "kein_utf8": b'{"tag_name": "v1.7.0", "x": "\xff\xfe"}',
}


@pytest.mark.parametrize("body", list(UNGUELTIGE_ANTWORTEN.values()), ids=list(UNGUELTIGE_ANTWORTEN))
def test_ungueltige_antwort_ist_ein_fehler(umgebung, body):
    umgebung.release_roh(Antwort(200, "application/json", body))
    with pytest.raises(OnlineFehler) as exc:
        bms_update.online_auskunft()
    assert str(exc.value) == T_UNGUELTIG


def test_zu_grosse_antwort_ist_ein_fehler_und_wird_nur_bis_1_mb_gelesen(umgebung):
    u = umgebung
    daten = _gueltiges_release(u)
    daten["body"] = "x" * (1024 * 1024 + 10)
    u.release_roh(_roh(daten))
    with pytest.raises(OnlineFehler) as exc:
        bms_update.online_auskunft()
    assert str(exc.value) == T_UNGUELTIG


def test_antwort_knapp_unter_1_mb_wird_gelesen(umgebung):
    daten = _gueltiges_release(umgebung)
    daten["body"] = "x" * (1024 * 1024 - 5000)
    umgebung.release_roh(_roh(daten))
    assert bms_update.online_auskunft()["version"] == "1.7.0"


def test_gueltiges_release_liefert_genau_die_geprueften_felder(umgebung):
    paket = umgebung.anbieten("1.7.0", release={"zukunftsfeld": {"a": [1, 2]}, "body": "- Neu\n- Mehr"},
                              asset={"label": "Programmpaket", "download_count": 3})

    auskunft = bms_update.online_auskunft()

    assert auskunft == {
        "version": "1.7.0",
        "url": f"{umgebung.probe.host}/{REPO}/releases/download/v1.7.0/BMS_1.7.0.zip",
        "groesse": len(paket), "sha256": _sha256(paket),
        "seite": f"{umgebung.probe.host}/{REPO}/releases/tag/v1.7.0"}
    assert list(inspect.signature(bms_update.online_auskunft).parameters) == []


@pytest.mark.parametrize("seite", ["https://evil.example/releases", f"/{REPO}/releases/tag/v1.7.0", 5, WEG])
def test_fremde_oder_fehlende_release_seite_stoppt_das_update_nicht(umgebung, seite):
    umgebung.anbieten("1.7.0", release={"html_url": seite})
    auskunft = bms_update.online_auskunft()
    assert auskunft["seite"] is None and auskunft["version"] == "1.7.0"


def test_auskunft_ohne_content_type_wird_trotzdem_gelesen(umgebung):
    daten = _gueltiges_release(umgebung)
    umgebung.release_roh(Antwort(200, None, json.dumps(daten).encode(), content_length=None))
    assert bms_update.online_auskunft()["version"] == "1.7.0"


def test_ungueltiges_release_im_ablauf_ist_ein_hinweis_und_kein_laden(umgebung, capsys):
    umgebung.anbieten("1.1.0", release={"tag_name": "v1.1"})
    umgebung.download_paket("1.1.0")

    assert umgebung.aktualisieren() == 0
    assert f"Online-Suche nicht möglich: {T_UNGUELTIG}" in capsys.readouterr().out
    assert umgebung.probe.zaehlen(".zip") == 0


# ── online_laden mit einer von aussen gebauten Auskunft ─────────────────────────────────────
@pytest.mark.parametrize("abweichung", [
    {"version": "1.1.0&x=1"}, {"version": "../1.1.0"}, {"version": "1.1.0\n"}, {"version": "1.1"},
    {"version": ""}, {"version": "a.b.c"}, {"version": "1234567890.0.0"}, {"version": None},
    {"version": 110},
    {"url": "https://evil.example/BMS_1.1.0.zip"}, {"url": None}, {"url": 5},
    {"url": "{host}/{repo}/releases/download/v1.1.0/BMS_1.1.0.zip?token=x"},
    {"groesse": 0}, {"groesse": -1}, {"groesse": 200 * 1024 * 1024 + 1}, {"groesse": "100"},
    {"groesse": True}, {"groesse": None},
    {"sha256": "AB" * 32}, {"sha256": "ab" * 31}, {"sha256": None}, {"sha256": 5},
])
def test_online_laden_nimmt_nur_eine_gepruefte_auskunft(umgebung, tmp_path, abweichung):
    umgebung.anbieten("1.1.0")
    abweichung = {k: v.format(host=umgebung.probe.host, repo=REPO) if isinstance(v, str) else v
                  for k, v in abweichung.items()}
    ziel = tmp_path / "z" / "BMS.zip"

    with pytest.raises(OnlineFehler):
        bms_update.online_laden(_auskunft_fuer(**abweichung), ziel)

    assert umgebung.probe.verbindungen == 0
    assert not ziel.parent.exists()


@pytest.mark.parametrize("auskunft", [None, [], "1.1.0", 5])
def test_online_laden_nimmt_nur_ein_dict(umgebung, tmp_path, auskunft):
    with pytest.raises(OnlineFehler):
        bms_update.online_laden(auskunft, tmp_path / "z" / "BMS.zip")
    assert umgebung.probe.verbindungen == 0


# ── Zweiter Anlauf ──────────────────────────────────────────────────────────────────────────
def test_zweiter_anlauf_laedt_nicht_neu_und_raeumt_altes_weg(umgebung, capsys):
    paket = umgebung.anbieten("1.1.0")

    assert umgebung.start("--pruefen") == 0
    assert umgebung.probe.zaehlen(".zip") == 1
    capsys.readouterr()

    # Altlasten im Paketordner: andere Pakete und Teildateien gehen, fremde Dateien bleiben.
    (umgebung.pakete / "BMS_0.9.0.zip").write_bytes(b"alt")
    (umgebung.pakete / "BMS_1.1.0.zip.teil").write_bytes(b"halb")
    (umgebung.pakete / "BMS_0.8.0.zip.teil").write_bytes(b"halb")
    (umgebung.pakete / "notiz.txt").write_text("bleibt", encoding="utf-8")

    assert umgebung.start("--pruefen") == 0
    out = capsys.readouterr().out
    assert umgebung.probe.zaehlen(".zip") == 1               # kein zweiter Download
    assert umgebung.probe.zaehlen("/latest") == 2
    assert "Version 1.1.0 gefunden, das Paket liegt bereits geladen vor." in out
    assert "Paket geladen und geprüft." in out
    assert sorted(p.name for p in umgebung.pakete.iterdir()) == ["BMS_1.1.0.zip", "notiz.txt"]
    assert (umgebung.pakete / "BMS_1.1.0.zip").read_bytes() == paket


def test_vorhandene_datei_mit_falschem_inhalt_wird_neu_geladen(umgebung):
    paket = umgebung.anbieten("1.1.0")
    umgebung.pakete.mkdir(parents=True)
    (umgebung.pakete / "BMS_1.1.0.zip").write_bytes(b"x" * len(paket))      # gleiche Groesse, anderer Inhalt

    assert umgebung.start("--pruefen") == 0
    assert umgebung.probe.zaehlen(".zip") == 1
    assert (umgebung.pakete / "BMS_1.1.0.zip").read_bytes() == paket


def test_neues_angebot_loescht_das_alte_geladene_paket(umgebung):
    umgebung.anbieten("1.1.0")
    assert umgebung.start("--pruefen") == 0
    umgebung.anbieten("1.2.0")
    assert umgebung.start("--pruefen") == 0
    assert [p.name for p in umgebung.pakete.iterdir()] == ["BMS_1.2.0.zip"]


# ── Selbstaktualisierung ────────────────────────────────────────────────────────────────────
_STUB_MIT_PROTOKOLL = (
    "import json, os, sys\n"
    "with open(os.environ['BMS_STUB_AUSGABE'], 'w', encoding='utf-8') as f:\n"
    "    json.dump(sys.argv[1:], f)\n"
    "sys.exit(42)\n"
).encode("utf-8")


def test_selbstaktualisierung_bekommt_den_pfad_des_geladenen_pakets_als_argument(umgebung):
    ausgabe = umgebung.wurzel / "stub_argv.json"
    umgebung.monkeypatch.setenv("BMS_STUB_AUSGABE", str(ausgabe))
    umgebung.anbieten("1.1.0", ersatz={"scripts/bms_update.py": _STUB_MIT_PROTOKOLL})

    code = umgebung.aktualisieren()

    assert code == 42                                        # nur die Fassung im Paket liefert 42
    argv = json.loads(ausgabe.read_text(encoding="utf-8"))
    geladen = umgebung.pakete / "BMS_1.1.0.zip"
    pfade = [a for a in argv if a.lower().endswith(".zip")]
    assert len(pfade) == 1 and os.path.samefile(pfade[0], geladen)   # der Pfad steht ausdruecklich da
    assert "--delegiert" in argv
    assert argv[argv.index("--installation") + 1] == str(umgebung.installation)
    for schalter in _STANDARD:
        assert schalter in argv                               # die Schalter des Kunden gehen mit
    assert umgebung.probe.zaehlen(".zip") == 1                # genau ein Download, die Fassung im Paket sucht nicht neu
    assert umgebung.probe.zaehlen("/latest") == 1
    assert umgebung.installierte_version() == "1.0.0"         # die Stub-Fassung hat nichts eingespielt


_STUB_MIT_MARKE = b"import sys\nprint('STUB-FASSUNG LAEUFT', flush=True)\nsys.exit(42)\n"


def test_meldungen_dieses_laufs_stehen_vor_der_ausgabe_der_fassung_im_paket(umgebung):
    """Laeuft das Werkzeug ohne Terminal (Ausgabe in eine Datei oder an ein aufrufendes Programm),
    puffert Python die eigene Ausgabe, die Fassung im Paket schreibt als eigener Prozess sofort:
    "Paket geladen und geprueft." stand in der Verbundprobe hinter deren Plan. Der Test startet das
    Werkzeug deshalb als eigenen Prozess mit umgeleiteter Ausgabe. Im Testprozess selbst faellt der
    Fehler nicht auf, dort puffert die Ausgabe nicht."""
    umgebung.anbieten("1.1.0", ersatz={"scripts/bms_update.py": _STUB_MIT_MARKE})
    starter = umgebung.wurzel / "starter.py"
    starter.write_text(
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('bms_update_starter', {str(_SKRIPT_PFAD)!r})\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "sys.modules[spec.name] = m\n"
        "spec.loader.exec_module(m)\n"
        f"m.GITHUB_API = {umgebung.probe.host!r}\n"           # nur der Probeserver auf 127.0.0.1
        f"m.GITHUB_SEITE = {umgebung.probe.host!r}\n"
        "m._laeuft_nicht_in_venv = lambda: False\n"
        "m._server_laeuft = lambda port=None: False\n"
        "sys.exit(m.main(sys.argv[1:]))\n", encoding="utf-8")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env.pop("BMS_DATA_DIR", None)
    for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        env.pop(name, None)               # ein Proxy des Rechners duerfte den Weg zum Probeserver nicht beeinflussen
    env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost"

    lauf = subprocess.run([sys.executable, str(starter), "--installation", str(umgebung.installation), *_STANDARD],
                          env=env, capture_output=True, timeout=120)

    out = lauf.stdout.decode("utf-8")
    assert lauf.returncode == 42, out + lauf.stderr.decode("utf-8", "replace")
    assert out.index("Paket geladen und geprüft.") < out.index("STUB-FASSUNG LAEUFT")


def test_selbstaktualisierung_mit_pfad_argument_gibt_den_pfad_nur_einmal_weiter(umgebung):
    ausgabe = umgebung.wurzel / "stub_argv.json"
    umgebung.monkeypatch.setenv("BMS_STUB_AUSGABE", str(ausgabe))
    eigenes = _paket_bauen(umgebung.wurzel / "irgendwo", "BMS_1.1.0.zip", "1.1.0",
                           {**umgebung.dateien("1.1.0"), "scripts/bms_update.py": _STUB_MIT_PROTOKOLL})

    assert umgebung.aktualisieren(str(eigenes)) == 42
    argv = json.loads(ausgabe.read_text(encoding="utf-8"))
    assert argv.count(str(eigenes)) == 1
    assert umgebung.probe.verbindungen == 0


# ── Was uebertragen wird ────────────────────────────────────────────────────────────────────
ERLAUBTE_KOPFZEILEN = {"host", "accept", "x-github-api-version", "user-agent", "accept-encoding",
                       "connection"}


def test_uebertragen_wird_nur_die_anfrage_und_sonst_nichts(umgebung):
    umgebung.anbieten("1.1.0")
    assert umgebung.aktualisieren() == 0

    auskunft, laden = umgebung.probe.anfragen
    assert (auskunft.methode, auskunft.pfad, auskunft.query) == ("GET", RELEASE_PFAD, "")
    assert (laden.methode, laden.pfad, laden.query) == ("GET", umgebung.zip_pfad("1.1.0"), "")
    assert auskunft.kopf["accept"] == "application/vnd.github+json"
    assert auskunft.kopf["x-github-api-version"] == "2022-11-28"
    for anfrage in (auskunft, laden):
        assert anfrage.rumpf == b""                           # kein Inhalt, nur die Anfrage selbst
        assert anfrage.kopf["user-agent"] == "BMS-Update"
        assert set(anfrage.kopf_namen) <= ERLAUBTE_KOPFZEILEN, anfrage.kopf_namen
        assert len(anfrage.kopf_namen) == len(set(anfrage.kopf_namen))
        for kopfname in ("authorization", "cookie", "content-type", "content-length", "referer", "origin"):
            assert kopfname not in anfrage.kopf                # kein Token, keine Kennung
        for wert in anfrage.kopf.values():                    # keine Version, kein System, keine Lizenzwerte
            assert "python" not in wert.lower() and "1.0.0" not in wert
            for marker in LIZENZ_MARKER:
                assert marker not in wert
    assert not any(a.methode != "GET" for a in umgebung.probe.anfragen)


def test_ein_fehlertext_des_servers_wird_nie_angezeigt(umgebung, capsys):
    umgebung.release_roh(Antwort(403, "text/plain; charset=utf-8",
                                 "Geheimer\x1b[31m Serverhinweis\n".encode()))
    assert umgebung.aktualisieren() == 1
    out = capsys.readouterr().out
    assert "Serverhinweis" not in out and "\x1b" not in out
    assert T_GRENZE in out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# online_laden einzeln
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_online_laden_schreibt_das_paket_ueber_eine_teil_datei(umgebung, tmp_path):
    paket = umgebung.anbieten("1.1.0")
    ziel = tmp_path / "neuer" / "ordner" / "BMS_1.1.0.zip"          # der Ordner wird angelegt

    ergebnis = bms_update.online_laden(bms_update.online_auskunft(), ziel)

    assert ergebnis is None
    assert ziel.read_bytes() == paket
    assert [p.name for p in ziel.parent.iterdir()] == ["BMS_1.1.0.zip"]


def test_die_beiden_festen_schnittstellen_haben_die_neue_form():
    assert list(inspect.signature(bms_update.online_auskunft).parameters) == []
    assert list(inspect.signature(bms_update.online_laden).parameters) == ["auskunft", "ziel"]
    assert issubclass(bms_update.OnlineFehler, Exception)


@pytest.mark.parametrize("status, text", [(404, T_UNGUELTIG), (403, T_GRENZE), (429, T_GRENZE),
                                          (500, T_UNGUELTIG), (204, T_UNGUELTIG)])
def test_online_laden_antwort_ungleich_200_laesst_ziel_unberuehrt(umgebung, tmp_path, status, text):
    umgebung.anbieten("1.1.0")
    auskunft = bms_update.online_auskunft()
    umgebung.laden_setzen(Antwort(status, "text/plain; charset=utf-8", b"Etwas ging schief.\n"))
    ziel = tmp_path / "z" / "BMS_1.1.0.zip"
    ziel.parent.mkdir()
    ziel.write_bytes(b"vorher")

    with pytest.raises(OnlineFehler) as exc:
        bms_update.online_laden(auskunft, ziel)

    assert str(exc.value) == text           # beim Laden heisst 404 nie "noch keine Version veroeffentlicht"
    assert ziel.read_bytes() == b"vorher"
    assert [p.name for p in ziel.parent.iterdir()] == ["BMS_1.1.0.zip"]


def test_online_laden_in_unbeschreibbaren_ordner_ist_ein_onlinefehler(umgebung, tmp_path):
    umgebung.anbieten("1.1.0")
    datei = tmp_path / "ist_eine_datei"
    datei.write_bytes(b"x")                                    # als Ordner unbrauchbar, auf jeder Plattform

    with pytest.raises(OnlineFehler) as exc:
        bms_update.online_laden(bms_update.online_auskunft(), datei / "BMS_1.1.0.zip")

    assert "lässt sich nicht" in str(exc.value) and "speichern" in str(exc.value)


# ── Zeitgrenzen ─────────────────────────────────────────────────────────────────────────────
def test_zeitueberschreitung_beim_laden_loescht_die_teil_datei(umgebung, tmp_path):
    paket = umgebung.anbieten("1.1.0")
    auskunft = bms_update.online_auskunft()
    umgebung.laden_setzen(Antwort(200, "application/octet-stream", paket, stocken_nach=100))   # haengt nach 100 Byte
    umgebung.monkeypatch.setattr(bms_update, "ZEIT_LADEN_S", 0.3)
    ziel = tmp_path / "z" / "BMS_1.1.0.zip"

    with pytest.raises(OnlineFehler) as exc:
        bms_update.online_laden(auskunft, ziel)

    assert str(exc.value) == T_ZEIT
    assert list(ziel.parent.iterdir()) == []


def test_konstanten_stehen_wie_in_der_spec():
    assert bms_update.GITHUB_REPO == REPO == "holgerdaube/BewerbungsMgmtSystem"
    assert bms_update.GITHUB_API == "https://api.github.com"
    assert bms_update.GITHUB_SEITE == "https://github.com"
    assert bms_update.ZEIT_AUSKUNFT_S == 10
    assert bms_update.ZEIT_LADEN_S == 120
    assert bms_update.PAKET_MAX_BYTES == 200 * 1024 * 1024
    assert bms_update.UMLEITUNGEN_MAX == 3


def test_kundentexte_stehen_wie_in_vertrag_u():
    assert bms_update._TEXT_KEINE_VERBINDUNG == T_KEINE_VERBINDUNG
    assert bms_update._TEXT_ZEITUEBERSCHREITUNG == T_ZEIT
    assert bms_update._TEXT_UNTERBROCHEN == T_UNTERBROCHEN
    assert bms_update._TEXT_ZERTIFIKAT == T_ZERTIFIKAT
    assert bms_update._TEXT_ANTWORT_UNGUELTIG == T_UNGUELTIG
    assert bms_update._TEXT_NOCH_KEINE_VERSION == T_KEINE_VERSION
    assert bms_update._TEXT_ANFRAGEGRENZE == T_GRENZE
    assert bms_update._TEXT_PRUEFSUMME_FEHLT == T_PRUEFSUMME
    assert bms_update._TEXT_PAKET_BESCHAEDIGT == T_BESCHAEDIGT


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Umleitungen (Leitentscheidung 6)
# ═════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
def test_umleitung_zu_erlaubtem_host_wird_gefolgt(umgebung, capsys, code):
    umgebung.anbieten("1.1.0")
    umgebung.erlaube_hosts("localhost")
    ziel = umgebung.kette_aufbauen(1, code=code)

    assert umgebung.aktualisieren() == 0, capsys.readouterr().out
    assert umgebung.installierte_version() == "1.1.0"
    assert [a.pfad for a in umgebung.probe.anfragen] == [RELEASE_PFAD, umgebung.zip_pfad("1.1.0"), ziel]
    cdn = umgebung.probe.anfragen[-1]
    assert cdn.kopf["host"] == f"localhost:{umgebung.probe.port}"
    assert set(cdn.kopf_namen) <= {"host", "user-agent", "accept-encoding", "connection"}   # nichts Zusaetzliches
    assert cdn.kopf["user-agent"] == "BMS-Update"


def test_umleitung_mit_relativer_adresse_wird_gegen_die_aktuelle_aufgeloest(umgebung):
    paket = umgebung.anbieten("1.1.0")
    umgebung.erlaube_hosts("127.0.0.1")
    umgebung.probe.routen[umgebung.zip_pfad("1.1.0")] = Antwort(302, None, b"", {"Location": "/cdn/relativ.zip"})
    umgebung.probe.routen["/cdn/relativ.zip"] = Antwort(200, "application/octet-stream", paket)

    ziel = umgebung.wurzel / "z" / "BMS_1.1.0.zip"
    bms_update.online_laden(bms_update.online_auskunft(), ziel)

    assert ziel.read_bytes() == paket


@pytest.mark.parametrize("anzahl", [1, 2, 3])
def test_bis_zu_drei_umleitungen_sind_erlaubt(umgebung, tmp_path, anzahl):
    paket = umgebung.anbieten("1.1.0")
    umgebung.erlaube_hosts("localhost")
    endziel = umgebung.kette_aufbauen(anzahl)
    ziel = tmp_path / "z" / "BMS_1.1.0.zip"

    bms_update.online_laden(bms_update.online_auskunft(), ziel)

    assert ziel.read_bytes() == paket
    assert umgebung.probe.zaehlen(endziel) == 1
    assert len([a for a in umgebung.probe.anfragen if a.pfad != RELEASE_PFAD]) == anzahl + 1


def test_eine_vierte_umleitung_wird_nicht_mehr_gefolgt(umgebung, capsys):
    umgebung.anbieten("1.1.0")
    umgebung.erlaube_hosts("localhost")
    endziel = umgebung.kette_aufbauen(4)
    umgebung.download_paket("1.0.5")              # der Rueckfall: ein aelteres Paket im Download-Ordner

    code = umgebung.aktualisieren()
    out = capsys.readouterr().out

    assert code == 0, out
    assert f"Laden nicht möglich: {T_UNGUELTIG}" in out
    assert umgebung.probe.zaehlen(endziel) == 0              # das Endziel wurde nie angefragt
    assert len([a for a in umgebung.probe.anfragen if a.pfad != RELEASE_PFAD]) == 4   # Original + 3 Umleitungen
    assert list(umgebung.pakete.iterdir()) == []             # nichts geladen, nichts liegen geblieben
    assert umgebung.installierte_version() == "1.0.5"        # das Paket aus Downloads wurde eingespielt


def test_umleitung_zu_fremdem_host_wird_abgelehnt_ohne_je_dorthin_zu_gehen(umgebung, capsys):
    umgebung.anbieten("1.1.0")
    umgebung.erlaube_hosts("localhost")                      # 127.0.0.1 ist hier der "fremde" Host
    fremd = Probe()
    try:
        fremd.routen["/cdn/BMS_1.1.0.zip"] = Antwort(200, "application/octet-stream",
                                                     umgebung.paket_bytes("1.1.0"))
        umgebung.laden_setzen(Antwort(302, None, b"", {"Location": f"{fremd.host}/cdn/BMS_1.1.0.zip"}))
        umgebung.download_paket("1.0.5")

        code = umgebung.aktualisieren()
        out = capsys.readouterr().out

        assert code == 0, out
        assert f"Laden nicht möglich: {T_UNGUELTIG}" in out
        assert fremd.anfragen == [] and fremd.verbindungen == 0
        assert umgebung.installierte_version() == "1.0.5"
    finally:
        fremd.beenden()


def test_umleitung_zu_fremdem_host_ohne_ersatzregel_mit_der_echten_regel(umgebung, capsys):
    """Ohne Ersatz der Zielpruefung gilt die echte Regel: eine Umleitung zu einer http-Adresse (hier
    der Probeserver) ist abgelehnt, auch wenn sie auf denselben Rechner zeigt."""
    umgebung.anbieten("1.1.0")
    umgebung.kette_aufbauen(1)
    vorher = umgebung.unveraendert()

    code = umgebung.aktualisieren()
    out = capsys.readouterr().out

    assert code == 1, out
    assert f"Laden nicht möglich: {T_UNGUELTIG}" in out
    assert umgebung.probe.zaehlen("/cdn/BMS_1.1.0.zip") == 0
    assert umgebung.unveraendert() == vorher
    assert list(umgebung.pakete.iterdir()) == []


@pytest.mark.parametrize("kopf", [{}, {"Location": ""}], ids=["ohne_location", "leere_location"])
def test_umleitung_ohne_ziel_ist_ein_fehler(umgebung, tmp_path, kopf):
    umgebung.anbieten("1.1.0")
    auskunft = bms_update.online_auskunft()
    umgebung.laden_setzen(Antwort(302, None, b"", kopf))
    with pytest.raises(OnlineFehler) as exc:
        bms_update.online_laden(auskunft, tmp_path / "z" / "BMS_1.1.0.zip")
    assert str(exc.value) == T_UNGUELTIG


def test_die_auskunft_folgt_keiner_umleitung_auch_nicht_zu_einem_erlaubten_host(umgebung):
    umgebung.anbieten("1.1.0")
    umgebung.erlaube_hosts("localhost", "127.0.0.1")
    umgebung.release_roh(Antwort(302, None, b"", {"Location": umgebung.probe.lokal + "/ziel"}))
    with pytest.raises(OnlineFehler) as exc:
        bms_update.online_auskunft()
    assert str(exc.value) == T_UNGUELTIG
    assert umgebung.probe.zaehlen("/ziel") == 0


ERLAUBTE_ZIELE = [
    "https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/download/v1.0.0/BMS_1.0.0.zip",
    "https://release-assets.githubusercontent.com/github-production-release-asset/1?sp=r&sig=x",
    "https://objects.githubusercontent.com/x",
    "https://github-releases.githubusercontent.com/x",
    "https://a.b.githubusercontent.com/x",
    "https://GitHub.com/x",
    "https://github.com:443/x",
]
# Adressen mit Benutzerteil vor dem Host (`user:pw<@>github.com`) werden aus Teilen zusammengesetzt: so
# steht in der Quelle keine Zeichenfolge, die wie eine Mailadresse aussieht (Personendaten-Prüfung).
_AT = "@"
ABGELEHNTE_ZIELE = [
    "http://github.com/x", "http://objects.githubusercontent.com/x", "ftp://github.com/x",
    "file:///etc/passwd", "//github.com/x", "/x", "github.com/x", "",
    "https://evil.example/x", "https://github.com.evil.example/x", "https://evilgithub.com/x",
    "https://notgithub.com/x", "https://api.github.com.evil.example/x",
    "https://githubusercontent.com/x", "https://evilgithubusercontent.com/x",
    "https://githubusercontent.com.evil.example/x", "https://.githubusercontent.com/x",
    "https://github.com@evil.example/x", f"https://user:pw{_AT}github.com/x",
    f"https://evil.example{_AT}github.com/x",
    "https://github.com:8443/x", "https://github.com:abc/x", "https://github.com:/x/\u0000",
    "https://127.0.0.1/x", "https://localhost/x", "https://[::1]/x",
    "https://github.com\n.evil.example/x", "https://github.com /x", "https://github.com/\u00e4",
    "https://g\u0131thub.com/x", "https://github.com./x",
]


@pytest.mark.parametrize("adresse", ERLAUBTE_ZIELE)
def test_zielpruefung_erlaubt_github_hosts(adresse):
    assert bms_update._ziel_erlaubt(adresse) is True


@pytest.mark.parametrize("adresse", ABGELEHNTE_ZIELE)
def test_zielpruefung_lehnt_alles_andere_ab(adresse):
    assert bms_update._ziel_erlaubt(adresse) is False


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Sicherheit der Verbindung
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_opener_hat_keinen_umleitungs_handler_nutzt_proxy_und_prueft_zertifikate(monkeypatch):
    # Ein ProxyHandler ohne Proxy-Einstellungen traegt keine Methoden und wird nicht eingehaengt.
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {"https": "http://127.0.0.1:9"})
    opener = bms_update._opener()
    assert not any(isinstance(h, urllib.request.HTTPRedirectHandler) for h in opener.handlers)
    assert any(isinstance(h, urllib.request.ProxyHandler) for h in opener.handlers)
    assert opener.addheaders == []                                  # keine Standard-Kopfzeilen (Python-Version)
    kontext = bms_update._ssl_kontext()
    assert kontext.verify_mode == ssl.CERT_REQUIRED and kontext.check_hostname is True


def test_proxy_einstellungen_des_rechners_gelten_weiter(umgebung, tmp_path, monkeypatch):
    """Der Rechner schreibt einen Proxy vor (Firmennetz): Auskunft und Download gehen darueber. Der
    Probeserver ist der Proxy; die Namen api.github.test und github.test loest niemand auf."""
    umgebung.anbieten("1.1.0")
    paket = umgebung.paket_bytes("1.1.0")
    monkeypatch.setattr(bms_update, "GITHUB_API", "http://api.github.test")
    monkeypatch.setattr(bms_update, "GITHUB_SEITE", "http://github.test")
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {"http": umgebung.probe.host})
    monkeypatch.setattr(urllib.request, "proxy_bypass", lambda host: False)
    daten = json.loads(umgebung.probe.routen[RELEASE_PFAD].body)
    daten["assets"][0]["browser_download_url"] = "http://github.test" + umgebung.zip_pfad("1.1.0")
    umgebung.release_roh(_roh(daten))
    ziel = tmp_path / "z" / "BMS_1.1.0.zip"

    bms_update.online_laden(bms_update.online_auskunft(), ziel)

    assert ziel.read_bytes() == paket
    assert [a.kopf["host"] for a in umgebung.probe.anfragen] == ["api.github.test", "github.test"]


@pytest.mark.parametrize("adresse", ["file:///etc/passwd", "ftp://127.0.0.1/", "gopher://x/y"])
def test_nur_http_und_https_werden_gesprochen(umgebung, adresse):
    umgebung.monkeypatch.setattr(bms_update, "GITHUB_API", adresse)
    with pytest.raises(OnlineFehler):
        bms_update.online_auskunft()
    assert umgebung.probe.verbindungen == 0


def test_zertifikatsfehler_gibt_den_satz_aus_und_wiederholt_nicht(umgebung):
    aufrufe = []

    class _Opener:
        def open(self, anfrage, timeout=None):
            aufrufe.append(anfrage.full_url)
            raise urllib.error.URLError(ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED]"))

    umgebung.monkeypatch.setattr(bms_update, "_opener", lambda: _Opener())

    with pytest.raises(OnlineFehler) as exc:
        bms_update.online_auskunft()

    assert str(exc.value) == T_ZERTIFIKAT
    assert len(aufrufe) == 1                                        # nie "ohne Pruefung" noch einmal


def test_zertifikatsfehler_im_ablauf_ist_ein_hinweis(umgebung, capsys):
    class _Opener:
        def open(self, anfrage, timeout=None):
            raise urllib.error.URLError(ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED]"))

    umgebung.monkeypatch.setattr(bms_update, "_opener", lambda: _Opener())
    umgebung.download_paket("1.1.0")

    assert umgebung.aktualisieren() == 0
    assert f"Online-Suche nicht möglich: {T_ZERTIFIKAT}" in capsys.readouterr().out


def _openssl_zertifikat(ordner: Path) -> tuple[Path, Path]:
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("openssl nicht vorhanden")
    schluessel, zertifikat = ordner / "schluessel.pem", ordner / "zertifikat.pem"
    ergebnis = subprocess.run(
        [openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(schluessel),
         "-out", str(zertifikat), "-days", "1", "-subj", "/CN=127.0.0.1"],
        capture_output=True, timeout=60)
    if ergebnis.returncode != 0:
        pytest.skip("openssl konnte kein Testzertifikat erzeugen")
    return schluessel, zertifikat


def test_unbekanntes_zertifikat_wird_abgelehnt_und_nichts_gesendet(tmp_path, monkeypatch):
    """Echte TLS-Verbindung zu einem Server mit selbst ausgestelltem Zertifikat: die Pruefung des
    Werkzeugs lehnt ab, der Server sieht keine einzige Anfrage."""
    schluessel, zertifikat = _openssl_zertifikat(tmp_path)
    kontext = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    kontext.load_cert_chain(str(zertifikat), str(schluessel))
    tls_probe = Probe(kontext)
    try:
        monkeypatch.setattr(bms_update, "GITHUB_API", f"https://127.0.0.1:{tls_probe.port}")

        with pytest.raises(OnlineFehler) as exc:
            bms_update.online_auskunft()

        assert str(exc.value) == T_ZERTIFIKAT
        assert tls_probe.anfragen == []
    finally:
        tls_probe.beenden()


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Waechter im Quelltext von bms_update.py
# ═════════════════════════════════════════════════════════════════════════════════════════════
_ERLAUBTE_UMGEBUNGSNAMEN = {"PORT", "BMS_DATA_DIR"}


def _importierte_module(quelltext: str) -> set[str]:
    namen: set[str] = set()
    for knoten in ast.walk(ast.parse(quelltext)):
        if isinstance(knoten, ast.Import):
            namen |= {a.name.split(".")[0] for a in knoten.names}
        elif isinstance(knoten, ast.ImportFrom):
            namen.add("." * knoten.level + (knoten.module or "").split(".")[0])
    return namen


def _umgebungszugriffe(quelltext: str) -> tuple[set[str], int]:
    """(Namen aus os.environ.get("X") / os.environ["X"] / setdefault / pop, Anzahl der Zugriffe,
    die sich nicht auf einen festen Namen aufloesen lassen, z. B. dict(os.environ) oder
    os.environ.get(name))."""
    baum = ast.parse(quelltext)
    eltern = {kind: knoten for knoten in ast.walk(baum) for kind in ast.iter_child_nodes(knoten)}
    namen: set[str] = set()
    uebrige = 0
    for knoten in ast.walk(baum):
        if not (isinstance(knoten, ast.Attribute) and knoten.attr == "environ"
                and isinstance(knoten.value, ast.Name) and knoten.value.id == "os"):
            continue
        vater = eltern[knoten]
        aufruf = eltern.get(vater)
        if (isinstance(vater, ast.Attribute) and vater.attr in ("get", "setdefault", "pop")
                and isinstance(aufruf, ast.Call) and aufruf.args
                and isinstance(aufruf.args[0], ast.Constant) and isinstance(aufruf.args[0].value, str)):
            namen.add(aufruf.args[0].value)
        elif (isinstance(vater, ast.Subscript) and isinstance(vater.slice, ast.Constant)
              and isinstance(vater.slice.value, str)):
            namen.add(vater.slice.value)
        else:
            uebrige += 1
    for knoten in ast.walk(baum):               # os.getenv / os.putenv umgehen os.environ
        if (isinstance(knoten, ast.Attribute) and knoten.attr in ("getenv", "putenv", "unsetenv")
                and isinstance(knoten.value, ast.Name) and knoten.value.id == "os"):
            uebrige += 1
    return namen, uebrige


def _dynamische_importe(quelltext: str) -> int:
    anzahl = 0
    for knoten in ast.walk(ast.parse(quelltext)):
        if isinstance(knoten, ast.Call):
            f = knoten.func
            if (isinstance(f, ast.Name) and f.id == "__import__") or \
                    (isinstance(f, ast.Attribute) and f.attr == "import_module"):
                anzahl += 1
    return anzahl


def _konstante(quelltext: str, name: str):
    zuweisungen = [k for k in ast.parse(quelltext).body if isinstance(k, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == name for t in k.targets)]
    assert len(zuweisungen) == 1, f"{name} muss genau einmal zugewiesen werden"
    wert = zuweisungen[0].value
    assert isinstance(wert, ast.Constant), f"{name} muss eine feste Konstante sein"
    return wert.value


def test_waechter_keine_abgeschaltete_zertifikatspruefung():
    for verboten in ("_create_unverified_context", "CERT_NONE", "CERT_OPTIONAL", "check_hostname",
                     "verify_mode", "_create_default_https_context", "verify=False"):
        assert verboten not in _QUELLTEXT, f"„{verboten}“ steht im Quelltext von bms_update.py"
    aufrufe = [k for k in ast.walk(ast.parse(_QUELLTEXT)) if isinstance(k, ast.Call)
               and isinstance(k.func, ast.Attribute) and k.func.attr == "create_default_context"]
    assert aufrufe, "ssl.create_default_context() wird nicht benutzt"


def test_waechter_repo_und_adressen_sind_feste_https_konstanten_ohne_umgebungsvariable():
    assert _konstante(_QUELLTEXT, "GITHUB_REPO") == "holgerdaube/BewerbungsMgmtSystem"
    assert _konstante(_QUELLTEXT, "GITHUB_API") == "https://api.github.com"
    assert _konstante(_QUELLTEXT, "GITHUB_SEITE") == "https://github.com"
    namen, _ = _umgebungszugriffe(_QUELLTEXT)
    assert not any(wort in n for n in namen for wort in ("GITHUB", "REPO", "URL", "HOST", "API", "PAKET"))


def test_waechter_umgebungsvariablen_nur_die_bekannten_namen():
    namen, uebrige = _umgebungszugriffe(_QUELLTEXT)
    assert namen == _ERLAUBTE_UMGEBUNGSNAMEN, f"Unerwartete Umgebungsvariablen: {namen ^ _ERLAUBTE_UMGEBUNGSNAMEN}"
    assert uebrige == 1, "genau ein Zugriff auf os.environ als Ganzes (Umgebung des Selbsttests) erlaubt"


def test_waechter_nur_importe_aus_der_standardbibliothek():
    module = _importierte_module(_QUELLTEXT)
    fremd = {m for m in module if m not in sys.stdlib_module_names}
    assert fremd == set(), f"Importe ausserhalb der Standardbibliothek: {fremd}"
    assert _dynamische_importe(_QUELLTEXT) == 0
    assert not any(m in ("app", "pipeline") for m in module)


def test_waechter_schlagen_bei_einem_gepflanzten_verstoss_an():
    """Gegenprobe zu den Waechtern oben (Lehre aus tasks/lessons.md: ein Waechter, der nie feuert,
    beweist nichts): dieselben Funktionen muessen auf einem synthetischen Verstoss anschlagen."""
    namen, uebrige = _umgebungszugriffe('import os\nurl = os.environ.get("BMS_GITHUB_API", "x")\n'
                                        'a = os.environ["ANDERE"]\nb = dict(os.environ)\n'
                                        'c = os.environ.get(variable)\nd = os.getenv("X")\n')
    assert namen == {"BMS_GITHUB_API", "ANDERE"} and uebrige == 3
    assert "requests" in _importierte_module("import requests\nfrom httpx import get\nfrom . import x\n")
    assert {"requests", "httpx", ".", "os"} <= _importierte_module(
        "import requests\nfrom httpx import get\nfrom . import x\nimport os.path\n")
    assert _dynamische_importe('import importlib\nimportlib.import_module("x")\n__import__("y")\n') == 2
    with pytest.raises(AssertionError):
        _konstante('GITHUB_API = "a" + "b"\n', "GITHUB_API")
