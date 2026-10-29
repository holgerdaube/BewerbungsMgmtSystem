"""P2-82 (Vertrag A) — `app/update_pruefen.py` und `GET /api/version/neueste`.

Der Knopf „Nach Updates suchen“ fragt bei GitHub-Releases nach der neuesten Version. Hier läuft alles
gegen einen Probeserver aus der Standardbibliothek auf 127.0.0.1 (`GITHUB_API` wird im Test
ersetzt); KEIN Test spricht GitHub an. Eine Sicherung davor lässt nur Loopback-Namen auflösen.

Deckt ab:
  1. Vergleich: neuer, gleich, älter, Zahlen- statt Textvergleich (1.10.0 > 1.9.0), installierte
     Version unbekannt oder 0.0.0 -> `neuer: True`.
  2. Anfrage: genau ein GET auf `/repos/<repo>/releases/latest` mit den vier Kopfzeilen, ohne Token
     und ohne Cookie; keine Umleitung wird verfolgt.
  3. Felder: `veroeffentlicht` (JJJJ-MM-TT), `seite` nur beim eigenen Repo, `aenderungen` (höchstens
     4000 Zeichen, nur Text).
  4. Fehlertexte wörtlich aus Vertrag U: 404, 403/429, Zeitüberschreitung (auch tröpfelnde und
     abgerissene Antwort), kaputtes oder zu großes JSON, falsches `tag_name`, kein Netz, unterbrochene
     Verbindung, nicht prüfbares Zertifikat (echte TLS-Verbindung, Ersatz ohne `openssl`).
  5. Route: immer 200, nur GET, `installiert` aus `version_info()`.
  6. Wächter: `GITHUB_REPO` hier und in `scripts/bms_update.py` gleich (SOLANGE Paket U die Konstante
     im Werkzeug nicht gesetzt hat, ist dieser eine Test rot); keine Umgebungsvariable, kein
     Protokoll, keine Speicherung im Quelltext.

App-Module werden ausschließlich innerhalb der Testfunktionen/Fixtures importiert (Konvention aus
conftest.py)."""
import json
import re
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Optional, Union

import pytest

BACKEND = Path(__file__).resolve().parent.parent
PROJEKT = BACKEND.parent
_REPO = "holgerdaube/BewerbungsMgmtSystem"      # wortgleich zu GITHUB_REPO (Wächter unten)

# Kundentexte wörtlich aus Vertrag U (die Tests prüfen den Wortlaut, nicht die Konstanten des Moduls).
T_KEINE_VERBINDUNG = "Es besteht keine Verbindung zu GitHub."
T_ZEIT = "GitHub antwortet nicht rechtzeitig."
T_UNTERBROCHEN = "Die Verbindung zu GitHub wurde unterbrochen."
T_ZERTIFIKAT = "Die sichere Verbindung zu GitHub ließ sich nicht prüfen."
T_UNGUELTIG = "Die Antwort von GitHub ist ungültig."
T_KEINE_VERSION = "Es ist noch keine Version veröffentlicht."
T_GRENZE = "GitHub begrenzt gerade die Anfragen. Bitte versuchen Sie es in einer Stunde erneut."

FEHLER_FELDER_NULL = ("neueste", "neuer", "veroeffentlicht", "seite", "aenderungen")


# ── Probeserver ──────────────────────────────────────────────────────────────────────────────
@dataclass
class Anfrage:
    methode: str
    pfad: str
    kopf: dict[str, str]


@dataclass
class Antwort:
    status: int = 200
    body: bytes = b""
    typ: Optional[str] = "application/json; charset=utf-8"
    kopf: dict[str, str] = field(default_factory=dict)
    content_length: Union[int, str, None] = "auto"   # "auto" = len(body), None = keine Kopfzeile
    warten_vor_antwort: bool = False                 # hängt, bis der Test endet (Zeitgrenze)
    stocken_nach: Optional[int] = None               # sendet so viele Byte, hängt dann
    troepfeln: bool = False                          # ein Byte alle 0,1 s, bis der Test endet
    trennen: bool = False                            # schließt die Verbindung ohne jede Antwort


class _Handler(BaseHTTPRequestHandler):
    server_version = "Probe"
    sys_version = ""

    def log_message(self, *args):
        pass

    def do_GET(self):
        probe = self.server.probe
        probe.anfragen.append(Anfrage(self.command, self.path,
                                      {k.lower(): v for k, v in self.headers.items()}))
        antwort = probe.beantworten(self.path)
        if antwort.trennen:
            self.close_connection = True
            return
        if antwort.warten_vor_antwort:
            probe.freigabe.wait(15)
            return
        self.send_response(antwort.status)
        if antwort.typ is not None:
            self.send_header("Content-Type", antwort.typ)
        laenge = len(antwort.body) if antwort.content_length == "auto" else antwort.content_length
        if laenge is not None:
            self.send_header("Content-Length", str(laenge))
        for name, wert in antwort.kopf.items():
            self.send_header(name, wert)
        self.end_headers()
        if antwort.troepfeln:
            while not probe.freigabe.is_set():
                self.wfile.write(b" ")
                self.wfile.flush()
                time.sleep(0.1)
            return
        if antwort.stocken_nach is not None:
            self.wfile.write(antwort.body[:antwort.stocken_nach])
            self.wfile.flush()
            probe.freigabe.wait(15)
            return
        self.wfile.write(antwort.body)


class _ProbeServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        art = sys.exc_info()[0]
        if art is not None and issubclass(art, (ConnectionError, TimeoutError, ssl.SSLError)):
            return          # der Client hat die Verbindung selbst beendet (gewollt)
        self.probe.handler_fehler.append(repr(sys.exc_info()[1]))


class Probe:
    def __init__(self, tls_kontext: Optional[ssl.SSLContext] = None):
        self.anfragen: list[Anfrage] = []
        self.handler_fehler: list[str] = []
        self.regel: Union[Antwort, Callable[[str], Antwort], None] = None
        self.freigabe = threading.Event()
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

    def beantworten(self, pfad: str) -> Antwort:
        if self.regel is None:
            return Antwort(404, b"")
        return self.regel(pfad) if callable(self.regel) else self.regel

    def antwortet(self, status: int = 200, body: Union[bytes, str, dict, None] = None, **rest) -> "Probe":
        """Kurzform: `body` als dict wird zu JSON."""
        if isinstance(body, dict):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.regel = Antwort(status, body or b"", **rest)
        return self

    def beenden(self):
        self.freigabe.set()
        self.server.shutdown()
        self.server.server_close()
        self._thread.join(5)


# ── Fixtures ─────────────────────────────────────────────────────────────────────────────────
@pytest.fixture()
def u(monkeypatch):
    """Das Modul `app.update_pruefen`, mit Netz-Sicherung: nur Loopback darf aufgelöst werden, und
    Proxy-Einstellungen des Rechners (Umgebung, macOS-Systemeinstellungen) bleiben außen vor: Ein
    gesetztes `NO_PROXY` sorgt dafür, dass `getproxies()` die Systemeinstellungen gar nicht liest."""
    import app.update_pruefen as modul

    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    echt = socket.getaddrinfo

    def nur_lokal(host, *args, **kwargs):
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise AssertionError(f"Test greift auf das Netz zu: {host!r}")
        return echt(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", nur_lokal)
    return modul


@pytest.fixture()
def probe(u, monkeypatch):
    p = Probe()
    monkeypatch.setattr(u, "GITHUB_API", p.host)
    yield p
    p.beenden()
    assert p.handler_fehler == [], f"Fehler im Probeserver: {p.handler_fehler}"


def _release(u, **ueberschreiben) -> dict:
    """Ein Release, wie `releases/latest` es liefert (nur die Felder, die das Modul liest, plus
    ein paar, die es ignorieren muss)."""
    basis = {
        "tag_name": "v2.0.0",
        "html_url": f"https://github.com/{u.GITHUB_REPO}/releases/tag/v2.0.0",
        "draft": False,
        "prerelease": False,
        "published_at": "2026-11-15T09:30:00Z",
        "body": "- Erster Punkt\n- Zweiter Punkt",
        "assets": [{"name": "BMS_2.0.0.zip", "size": 1234,
                    "digest": "sha256:" + "a" * 64,
                    "browser_download_url": f"https://github.com/{u.GITHUB_REPO}/releases/download/v2.0.0/BMS_2.0.0.zip"}],
    }
    basis.update(ueberschreiben)
    return {k: v for k, v in basis.items() if v is not _FEHLT}


_FEHLT = object()


def _fehlerfall(ergebnis: dict, text: str, installiert: Optional[str] = "1.7.0") -> None:
    assert ergebnis["fehler"] == text
    assert ergebnis["installiert"] == installiert
    for feld in FEHLER_FELDER_NULL:
        assert ergebnis[feld] is None, feld


# ── 1. Vergleich ─────────────────────────────────────────────────────────────────────────────
def test_neuere_version_wird_gemeldet(u, probe):
    probe.antwortet(200, _release(u))

    ergebnis = u.neueste_version("1.7.0")

    assert ergebnis == {
        "installiert": "1.7.0", "neueste": "2.0.0", "neuer": True,
        "veroeffentlicht": "2026-11-15",
        "seite": f"https://github.com/{u.GITHUB_REPO}/releases/tag/v2.0.0",
        "aenderungen": "- Erster Punkt\n- Zweiter Punkt", "fehler": None,
    }


def test_gleiche_version_ist_nicht_neuer(u, probe):
    probe.antwortet(200, _release(u))

    ergebnis = u.neueste_version("2.0.0")

    assert ergebnis["neuer"] is False
    assert ergebnis["neueste"] == "2.0.0" and ergebnis["installiert"] == "2.0.0"
    assert ergebnis["fehler"] is None


def test_aeltere_veroeffentlichte_version_ist_nicht_neuer(u, probe):
    """Entwicklungsstand über dem letzten Release (Git-Installation): kein „neuer“."""
    probe.antwortet(200, _release(u))

    ergebnis = u.neueste_version("2.1.0")

    assert ergebnis["neuer"] is False
    assert ergebnis["neueste"] == "2.0.0"


@pytest.mark.parametrize("installiert, github, neuer", [
    ("1.9.0", "1.10.0", True),       # Textvergleich ergäbe False
    ("1.10.0", "1.9.0", False),
    ("1.7.0", "1.7.1", True),
    ("1.7.1", "1.7.0", False),
    ("0.9.9", "1.0.0", True),
    ("10.0.0", "9.99.99", False),
])
def test_vergleich_ist_ein_zahlenvergleich(u, probe, installiert, github, neuer):
    probe.antwortet(200, _release(u, tag_name=f"v{github}"))

    assert u.neueste_version(installiert)["neuer"] is neuer


@pytest.mark.parametrize("installiert", [None, "0.0.0", "", "unbekannt", "1.7", "1.7.0-rc1", "v1.7.0", 7])
def test_unbekannte_installierte_version_gilt_als_neuer(u, probe, installiert):
    probe.antwortet(200, _release(u))

    ergebnis = u.neueste_version(installiert)

    assert ergebnis["neuer"] is True
    assert ergebnis["neueste"] == "2.0.0"
    assert ergebnis["installiert"] == (installiert if isinstance(installiert, str) else None)


# ── 2. Anfrage ───────────────────────────────────────────────────────────────────────────────
def test_anfrage_ist_ein_einziger_anonymer_get_mit_den_vier_kopfzeilen(u, probe):
    probe.antwortet(200, _release(u))

    u.neueste_version("1.7.0")

    assert len(probe.anfragen) == 1
    anfrage = probe.anfragen[0]
    assert anfrage.methode == "GET"
    assert anfrage.pfad == f"/repos/{u.GITHUB_REPO}/releases/latest"
    assert anfrage.kopf["accept"] == "application/vnd.github+json"
    assert anfrage.kopf["x-github-api-version"] == "2022-11-28"
    assert anfrage.kopf["user-agent"] == "BMS-Update"
    # Ohne Token, ohne Kennung, ohne Cookie (Leitentscheidung 3).
    assert not {"authorization", "cookie", "proxy-authorization"} & set(anfrage.kopf)


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_umleitung_wird_nicht_verfolgt(u, probe, status):
    def regel(pfad):
        if pfad == "/ziel":
            return Antwort(200, json.dumps(_release(u)).encode("utf-8"))
        return Antwort(status, b"", kopf={"Location": f"{probe.host}/ziel"})

    probe.regel = regel

    _fehlerfall(u.neueste_version("1.7.0"), T_UNGUELTIG)
    assert [a.pfad for a in probe.anfragen] == [f"/repos/{u.GITHUB_REPO}/releases/latest"]


# ── 3. Felder ────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("html_url", [
    # Der Repo-Name hinter einem fremden Host wird zur Laufzeit aus `_REPO` zusammengesetzt: Die Quelle
    # trägt den Namen nur in der erlaubten Form (Personendaten-Prüfung, `OEFFENTLICHES_REPO`).
    f"https://evil.example/{_REPO}/releases/tag/v2.0.0",
    f"https://github.com.evil.example/{_REPO}/releases/tag/v2.0.0",
    "http://github.com/holgerdaube/BewerbungsMgmtSystem/releases/tag/v2.0.0",
    f"https://github.com/{_REPO}X/releases/tag/v2.0.0",
    "https://github.com/anderer/BewerbungsMgmtSystem/releases/tag/v2.0.0",
    "https://github.com/holgerdaube/BewerbungsMgmtSystem/issues/1",
    "https://github.com/holgerdaube/BewerbungsMgmtSystem/releases",       # ohne abschließenden Schrägstrich
    "javascript:alert(1)",
    "https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/tag/v2.0.0 \"onclick=\"x",
    "https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/tag/v2.0.0\n",
    "",
    None,
    42,
    ["https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/"],
])
def test_fremde_oder_fehlende_html_url_ergibt_keine_seite(u, probe, html_url):
    probe.antwortet(200, _release(u, html_url=html_url))

    ergebnis = u.neueste_version("1.7.0")

    assert ergebnis["seite"] is None
    assert ergebnis["fehler"] is None                 # der Rest der Auskunft bleibt brauchbar
    assert ergebnis["neueste"] == "2.0.0" and ergebnis["neuer"] is True


def test_fehlende_html_url_im_json_ergibt_keine_seite(u, probe):
    probe.antwortet(200, _release(u, html_url=_FEHLT))

    assert u.neueste_version("1.7.0")["seite"] is None


def test_seite_folgt_der_repo_konstante(u, probe, monkeypatch):
    """Der Präfix wird zur Laufzeit aus `GITHUB_REPO` gebildet, nicht fest einkopiert."""
    monkeypatch.setattr(u, "GITHUB_REPO", "probe/Repo")
    probe.antwortet(200, _release(u))
    assert u.neueste_version("1.7.0")["seite"] == "https://github.com/probe/Repo/releases/tag/v2.0.0"
    probe.antwortet(200, _release(u, html_url="https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/tag/v2.0.0"))
    assert u.neueste_version("1.7.0")["seite"] is None


@pytest.mark.parametrize("published_at, erwartet", [
    ("2026-11-15T09:30:00Z", "2026-11-15"),
    ("2026-01-02T00:00:00+01:00", "2026-01-02"),
    ("2026-11-15", "2026-11-15"),
    ("2026-13-45T00:00:00Z", None),                   # kein Datum
    ("gestern", None),
    ("", None),
    (None, None),
    (20261115, None),
])
def test_veroeffentlicht_ist_ein_datum_oder_null(u, probe, published_at, erwartet):
    probe.antwortet(200, _release(u, published_at=published_at))

    assert u.neueste_version("1.7.0")["veroeffentlicht"] == erwartet


def test_aenderungen_sind_hoechstens_4000_zeichen_lang(u, probe):
    probe.antwortet(200, _release(u, body="- Punkt\n" * 1000))

    aenderungen = u.neueste_version("1.7.0")["aenderungen"]

    assert len(aenderungen) == 4000
    assert aenderungen.startswith("- Punkt\n- Punkt")


def test_aenderungen_normalisieren_zeilenenden_und_bleiben_reiner_text(u, probe):
    body = "<script>alert(1)</script>\r\n- **Fett** [Link](https://x.example)\r\n- Zwei"
    probe.antwortet(200, _release(u, body=body))

    aenderungen = u.neueste_version("1.7.0")["aenderungen"]

    assert aenderungen == "<script>alert(1)</script>\n- **Fett** [Link](https://x.example)\n- Zwei"


@pytest.mark.parametrize("body", [None, "", "   \n ", 5, ["- a"], {"a": 1}])
def test_aenderungen_ohne_text_sind_null(u, probe, body):
    probe.antwortet(200, _release(u, body=body))

    ergebnis = u.neueste_version("1.7.0")

    assert ergebnis["aenderungen"] is None
    assert ergebnis["fehler"] is None


def test_fehlendes_body_feld_ist_kein_fehler(u, probe):
    probe.antwortet(200, _release(u, body=_FEHLT, published_at=_FEHLT))

    ergebnis = u.neueste_version("1.7.0")

    assert ergebnis["aenderungen"] is None and ergebnis["veroeffentlicht"] is None
    assert ergebnis["neueste"] == "2.0.0" and ergebnis["fehler"] is None


# ── 4. Fehler ────────────────────────────────────────────────────────────────────────────────
def test_404_heisst_noch_keine_version(u, probe):
    probe.antwortet(404, {"message": "Not Found"})

    _fehlerfall(u.neueste_version("1.7.0"), T_KEINE_VERSION)


@pytest.mark.parametrize("status", [403, 429])
def test_anfragegrenze(u, probe, status):
    probe.antwortet(status, {"message": "API rate limit exceeded"}, kopf={"X-RateLimit-Remaining": "0"})

    _fehlerfall(u.neueste_version("1.7.0"), T_GRENZE)


@pytest.mark.parametrize("status", [401, 500, 502, 503])
def test_sonstiger_status_ist_eine_ungueltige_antwort(u, probe, status):
    probe.antwortet(status, {"message": "x"})

    _fehlerfall(u.neueste_version("1.7.0"), T_UNGUELTIG)


def test_zeitueberschreitung_ohne_antwort(u, probe, monkeypatch):
    monkeypatch.setattr(u, "ZEIT_S", 0.3)
    probe.antwortet(200, b"", warten_vor_antwort=True)

    start = time.monotonic()
    ergebnis = u.neueste_version("1.7.0")

    _fehlerfall(ergebnis, T_ZEIT)
    assert time.monotonic() - start < 5


def test_zeitueberschreitung_mitten_in_der_antwort(u, probe, monkeypatch):
    monkeypatch.setattr(u, "ZEIT_S", 0.3)
    koerper = json.dumps(_release(u)).encode("utf-8")
    probe.antwortet(200, koerper, stocken_nach=20)

    _fehlerfall(u.neueste_version("1.7.0"), T_ZEIT)


def test_troepfelnde_antwort_stoesst_an_die_gesamtzeit(u, probe, monkeypatch):
    """Jedes Byte kommt rechtzeitig (Lesezeit 0,6 s, Abstand 0,1 s), die Antwort endet nie: Es zählt
    die Gesamtzeit."""
    monkeypatch.setattr(u, "ZEIT_S", 0.6)
    probe.antwortet(200, b"", content_length=100000, troepfeln=True)

    start = time.monotonic()
    ergebnis = u.neueste_version("1.7.0")

    _fehlerfall(ergebnis, T_ZEIT)
    assert time.monotonic() - start < 5


def test_kaputtes_json(u, probe):
    probe.antwortet(200, b'{"tag_name": "v2.0.0", ')

    _fehlerfall(u.neueste_version("1.7.0"), T_UNGUELTIG)


@pytest.mark.parametrize("body", [
    b"", b"nicht json", b"\xff\xfe\x00", b"[]", b"[1, 2]", b'"v2.0.0"', b"42", b"null", b"true",
    # zu tief verschachtelt (RecursionError). Eigene kurze Kennung: Der Testname landet in der
    # Umgebungsvariablen PYTEST_CURRENT_TEST, unter Windows sind höchstens 32767 Zeichen erlaubt.
    pytest.param(b"[" * 100000, id="tief_verschachtelt"),
])
def test_kein_json_objekt(u, probe, body):
    probe.antwortet(200, body)

    _fehlerfall(u.neueste_version("1.7.0"), T_UNGUELTIG)


@pytest.mark.parametrize("tag", [
    "2.0.0", "V2.0.0", "v2.0", "v2", "v2.0.0.1", "v2.0.0-rc1", "v2.0.0+build", "v2.0.x", "vx.y.z",
    "v2.0.0\n", " v2.0.0", "v2.0.0 ", "v 2.0.0", "v-1.0.0", "v1234567890.0.0", "v1.1234567890.0",
    "v1.0.1234567890", "v٢.٠.٠", "v2.0.0/../..", "", None, 2, ["v2.0.0"],
])
def test_falsches_tag_name(u, probe, tag):
    probe.antwortet(200, _release(u, tag_name=tag))

    _fehlerfall(u.neueste_version("1.7.0"), T_UNGUELTIG)


def test_fehlendes_tag_name(u, probe):
    probe.antwortet(200, _release(u, tag_name=_FEHLT))

    _fehlerfall(u.neueste_version("1.7.0"), T_UNGUELTIG)


def test_grenzwerte_des_tag_namens_gehen_durch(u, probe):
    probe.antwortet(200, _release(u, tag_name="v123456789.0.999999999"))

    ergebnis = u.neueste_version("1.7.0")

    assert ergebnis["neueste"] == "123456789.0.999999999" and ergebnis["neuer"] is True


def test_antwort_genau_ein_megabyte_geht_durch_ein_byte_mehr_nicht(u, probe):
    kern = json.dumps(_release(u)).encode("utf-8")
    genau = kern[:-1] + b" " * (u.ANTWORT_MAX_BYTES - len(kern)) + b"}"
    assert len(genau) == u.ANTWORT_MAX_BYTES
    probe.antwortet(200, genau)
    assert u.neueste_version("1.7.0")["fehler"] is None

    probe.antwortet(200, genau + b" ")
    _fehlerfall(u.neueste_version("1.7.0"), T_UNGUELTIG)


def test_riesige_antwort_ohne_laengenangabe_wird_abgebrochen(u, probe):
    """Ohne Content-Length (Verbindung schließt am Ende) greift die Grenze beim Lesen."""
    probe.antwortet(200, b"{" + b" " * (3 * 1024 * 1024) + b"}", content_length=None)

    _fehlerfall(u.neueste_version("1.7.0"), T_UNGUELTIG)


def test_kein_netz_geschlossener_port(u, monkeypatch):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    # Der Port ist wieder frei und nichts lauscht darauf.
    monkeypatch.setattr(u, "GITHUB_API", f"http://127.0.0.1:{port}")

    _fehlerfall(u.neueste_version("1.7.0"), T_KEINE_VERBINDUNG)


def test_abgerissene_verbindung_ohne_antwort(u, probe):
    probe.antwortet(200, b"", trennen=True)

    _fehlerfall(u.neueste_version("1.7.0"), T_UNTERBROCHEN)


def test_verbindung_reisst_mitten_im_koerper_ab(u, probe):
    """Der Server verspricht mehr Byte als er sendet und schließt dann."""
    probe.antwortet(200, b'{"tag_name": "v2', content_length=5000)

    _fehlerfall(u.neueste_version("1.7.0"), T_UNTERBROCHEN)


def test_zertifikatsfehler_im_ablauf_ist_der_zertifikatstext(u, monkeypatch):
    """Ersatz ohne `openssl`: `httpx.ConnectError` mit `ssl.SSLCertVerificationError` als Ursache,
    so wie httpx einen nicht prüfbaren Zertifikatsfehler meldet."""
    import httpx

    aufrufe = []

    def _scheitert(self, methode, url, **kwargs):
        aufrufe.append(url)
        fehler = httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        fehler.__cause__ = ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED]")
        raise fehler

    monkeypatch.setattr(httpx.Client, "stream", _scheitert)

    _fehlerfall(u.neueste_version("1.7.0"), T_ZERTIFIKAT)
    assert len(aufrufe) == 1                           # nie „ohne Prüfung“ ein zweites Mal


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


def test_unbekanntes_zertifikat_wird_abgelehnt_und_nichts_gesendet(u, tmp_path, monkeypatch):
    """Echte TLS-Verbindung zu einem Server mit selbst ausgestelltem Zertifikat: die Prüfung lehnt ab,
    der Server sieht keine einzige Anfrage."""
    schluessel, zertifikat = _openssl_zertifikat(tmp_path)
    kontext = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    kontext.load_cert_chain(str(zertifikat), str(schluessel))
    tls_probe = Probe(kontext)
    try:
        monkeypatch.setattr(u, "GITHUB_API", f"https://127.0.0.1:{tls_probe.port}")
        tls_probe.antwortet(200, _release(u))

        _fehlerfall(u.neueste_version("1.7.0"), T_ZERTIFIKAT)
        assert tls_probe.anfragen == []
    finally:
        tls_probe.beenden()


def test_neueste_version_wirft_nie_und_liefert_immer_alle_felder(u, probe, monkeypatch):
    felder = {"installiert", "neueste", "neuer", "veroeffentlicht", "seite", "aenderungen", "fehler"}
    for regel in (Antwort(200, json.dumps(_release(u)).encode("utf-8")), Antwort(404), Antwort(500, b"x"),
                  Antwort(200, b"kein json")):
        probe.regel = regel
        assert set(u.neueste_version("1.7.0")) == felder
    monkeypatch.setattr(u, "GITHUB_API", "http://127.0.0.1:1")
    assert set(u.neueste_version(None)) == felder


# ── 5. Route ─────────────────────────────────────────────────────────────────────────────────
def test_route_liefert_die_auskunft_als_200(u, probe, client, monkeypatch):
    monkeypatch.setattr("app.routes_version.version_info", lambda: {"version": "1.7.0"})
    probe.antwortet(200, _release(u))

    r = client.get("/api/version/neueste")

    assert r.status_code == 200
    assert r.json() == {
        "installiert": "1.7.0", "neueste": "2.0.0", "neuer": True, "veroeffentlicht": "2026-11-15",
        "seite": f"https://github.com/{u.GITHUB_REPO}/releases/tag/v2.0.0",
        "aenderungen": "- Erster Punkt\n- Zweiter Punkt", "fehler": None,
    }


@pytest.mark.parametrize("status, text", [(404, T_KEINE_VERSION), (403, T_GRENZE), (429, T_GRENZE),
                                          (500, T_UNGUELTIG)])
def test_route_antwortet_auch_bei_fehlern_mit_200(u, probe, client, monkeypatch, status, text):
    monkeypatch.setattr("app.routes_version.version_info", lambda: {"version": "1.7.0"})
    probe.antwortet(status, {"message": "x"})

    r = client.get("/api/version/neueste")

    assert r.status_code == 200
    _fehlerfall(r.json(), text)


def test_route_ohne_netz_antwortet_mit_200(u, client, monkeypatch):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setattr(u, "GITHUB_API", f"http://127.0.0.1:{port}")
    monkeypatch.setattr("app.routes_version.version_info", lambda: {"version": "1.7.0"})

    r = client.get("/api/version/neueste")

    assert r.status_code == 200
    _fehlerfall(r.json(), T_KEINE_VERBINDUNG)


def test_route_nimmt_die_installierte_version_aus_version_info(u, probe, client):
    from app.version import version_info

    probe.antwortet(200, _release(u))

    r = client.get("/api/version/neueste")

    assert r.status_code == 200
    assert r.json()["installiert"] == version_info()["version"]


def test_route_meldet_bei_unbekannter_installation_neuer(u, probe, client, monkeypatch):
    monkeypatch.setattr("app.routes_version.version_info", lambda: {"version": None})
    probe.antwortet(200, _release(u))

    r = client.get("/api/version/neueste")

    assert r.json()["installiert"] is None
    assert r.json()["neuer"] is True


def test_route_ist_nur_get_und_die_alte_versionsroute_bleibt(u, probe, client):
    from app.main import app

    # Über das OpenAPI-Schema statt `app.routes`: eingebundene Router stehen dort nicht einzeln.
    pfade = app.openapi()["paths"]
    assert set(pfade["/api/version/neueste"]) == {"get"}
    assert set(pfade["/api/version"]) == {"get"}
    probe.antwortet(200, _release(u))
    assert client.get("/api/version").status_code == 200


def test_route_fragt_nur_auf_anfrage_bei_github(u, probe, client):
    """Die alte Versionsroute (Einstellungen-Seite) löst nie einen Abruf aus (Leitentscheidung 3)."""
    probe.antwortet(200, _release(u))

    assert client.get("/api/version").status_code == 200

    assert probe.anfragen == []


# ── 6. Wächter ───────────────────────────────────────────────────────────────────────────────
def _konstante(pfad: Path, name: str = "GITHUB_REPO") -> Optional[str]:
    treffer = re.findall(rf'^{name}\s*=\s*["\']([^"\']+)["\']', pfad.read_text(encoding="utf-8"), re.MULTILINE)
    assert len(treffer) <= 1, f"{name} steht mehrfach in {pfad.name}"
    return treffer[0] if treffer else None


def test_github_repo_ist_in_app_und_werkzeug_gleich():
    """Leitentscheidung 1: Der Repo-Name steht an genau zwei Stellen, beide gleich. Das Werkzeug darf
    nichts aus `app` importieren, deshalb liest der Test beide Dateien als Text.

    Dieser Test wird erst grün, wenn Paket U `GITHUB_REPO` in `scripts/bms_update.py` gesetzt hat."""
    app_repo = _konstante(BACKEND / "app" / "update_pruefen.py")
    werkzeug_repo = _konstante(PROJEKT / "scripts" / "bms_update.py")

    assert app_repo, "GITHUB_REPO fehlt in backend/app/update_pruefen.py"
    assert werkzeug_repo, "GITHUB_REPO fehlt in scripts/bms_update.py"
    assert re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", app_repo)
    assert app_repo == werkzeug_repo


def test_konstanten_laut_vertrag(u):
    assert u.GITHUB_REPO == "holgerdaube/BewerbungsMgmtSystem"
    assert u.GITHUB_API == "https://api.github.com"
    assert u.ZEIT_S == 10


def test_quelltext_haelt_die_leitplanken_ein():
    """Statische Wächter: Adresse nur als Konstante (keine Umgebungsvariable), keine Umleitung,
    Zertifikatsprüfung an, kein Token, kein Protokoll, keine Speicherung, kein Zwischenspeicher."""
    quelltext = (BACKEND / "app" / "update_pruefen.py").read_text(encoding="utf-8")
    code = "\n".join(zeile for zeile in quelltext.splitlines() if not zeile.lstrip().startswith("#"))
    # Docstrings enthalten Erklärtext; geprüft wird der Code ohne Zeichenketten in dreifachen Anführungszeichen.
    code = re.sub(r'""".*?"""', "", code, flags=re.DOTALL)

    assert "follow_redirects=False" in code
    assert "verify=True" in code
    for verboten in ("verify=False", "os.environ", "getenv", "import logging", "logging.", "print(",
                     "Authorization", "token", "netrc", "sqlite", "sqlmodel", "write_text", "write_bytes",
                     "open(", "lru_cache", "functools", "cache", "app.db", "from app"):
        assert verboten not in code, f"update_pruefen.py enthält {verboten!r}"


def test_routes_version_hat_nur_lesende_routen():
    quelltext = (BACKEND / "app" / "routes_version.py").read_text(encoding="utf-8")

    assert re.findall(r"@router\.(\w+)\(", quelltext) == ["get", "get"]
    assert "routes_lizenz" not in quelltext and "lizenz" not in quelltext.lower()
