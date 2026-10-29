"""P2-57: Herkunftsprüfung für schreibende Anfragen, Host-Prüfung gegen DNS-Rebinding.

Seit P2-55 gibt das Backend fremden Webseiten keine CORS-Freigabe. Einfache Anfragen (POST ohne
Inhalt, als Formular oder Upload) schickt der Browser trotzdem ab, nur die Antwort bleibt der
fremden Seite verborgen: 21 Routen, darunter `discard` (setzt jede Stelle auf „Kein Match“) und
der Basis-CV-Upload mit `overwrite`. Nach DNS-Rebinding ist eine fremde Domain, die auf 127.0.0.1
zeigt, für den Browser derselbe Ursprung wie sie selbst: Sie liest alles und schreibt mit einem
Origin, der zum Host passt. Die Middleware `_Herkunftspruefung` in `main.py` prüft deshalb vor
jeder Route den Host (jede Anfrage) und den Origin (alles außer GET, HEAD, OPTIONS). Regeln und
Begründung: tasks/spec_p2-57_herkunftspruefung.md.

Dass lesende Anfragen fremder Herkunft weiter beantwortet werden (ohne Freigabe, CORS schützt
dort), prüft test_keine_cors_freigabe.py; dort auch die legitimen Wege mit PATCH. Hier kommen die
einfachen Anfragen dazu, um die es geht, und Anfragen ohne Origin.

Wie in conftest.py: App-Module nur funktionslokal importieren. Dateien nur unter `tmp_path`
(`main._PROJECT_ROOT` umgebunden, Muster test_cv_basis_upload.py).
"""
import io
import re

import pytest

# Fremde Herkünfte gegenüber dem Standard-Host des TestClients (`testserver`): eine beliebige
# Webseite, eine lokal geöffnete HTML-Datei oder ein Sandbox-iframe (`null`), ein anderes lokales
# Projekt und derselbe Rechnername auf einem anderen Port.
FREMDE_HERKUNFT = [
    pytest.param("https://example.com", id="fremde-seite"),
    pytest.param("null", id="null"),
    pytest.param("http://localhost:3000", id="anderes-lokales-projekt"),
    pytest.param("http://testserver:8080", id="gleicher-name-anderer-port"),
]

# Wege, auf denen die Oberfläche, Skills und Skripte schreiben: `basis` bestimmt den Host, den der
# Server sieht, `kopf` die Header, die der Aufrufer mitschickt (Browser: Origin, neuere auch
# Sec-Fetch-Site; curl und Python: keinen).
LEGITIME_WEGE = [
    pytest.param("http://localhost:8000", {"Origin": "http://localhost:8000"}, id="mac"),
    pytest.param("http://localhost:8000",
                 {"Origin": "http://localhost:8000", "Sec-Fetch-Site": "same-origin"}, id="mac-browser"),
    pytest.param("http://127.0.0.1:8000", {"Origin": "http://127.0.0.1:8000"}, id="mac-ip"),
    # Der TestClient zerlegt `[::1]:8000` in der base_url nicht, deshalb der Host von Hand.
    pytest.param("http://localhost:8000", {"Host": "[::1]:8000", "Origin": "http://[::1]:8000"},
                 id="mac-ipv6"),
    pytest.param("http://mein-mac.local:8000", {"Origin": "http://mein-mac.local:8000"}, id="lan-name"),
    pytest.param("http://192.168.178.20:8000", {"Origin": "http://192.168.178.20:8000"}, id="lan-ip"),
    pytest.param("http://desktop-abc:8000", {"Origin": "http://desktop-abc:8000"}, id="windows-name"),
    # Vite-Dev-Server: Die Proxy-Kurzform (changeOrigin: true) schreibt den Host auf
    # localhost:8000 um und reicht Origin und Sec-Fetch-Site des Browsers unverändert durch. Die
    # Seite ruft ihren eigenen Ursprung (:5173) auf, also meldet der Browser same-origin.
    pytest.param("http://localhost:8000", {"Origin": "http://localhost:5173"}, id="vite-proxy"),
    pytest.param("http://localhost:8000",
                 {"Origin": "http://localhost:5173", "Sec-Fetch-Site": "same-origin"},
                 id="vite-proxy-browser"),
    pytest.param("http://localhost:8000", {}, id="ohne-origin"),   # Skills, stop.command, Python
]

# Namen, die eine fremde Seite per DNS-Rebinding vortäuschen könnte, weil sie über das normale DNS
# laufen. `mac.fritz.box` steht für Router-Namen: gesperrt, solange BMS_HOSTS ihn nicht freigibt.
GESPERRTE_HOSTS = [
    pytest.param("evil.example:8000", id="fremde-domain"),
    pytest.param("localhost.evil.example:8000", id="localhost-als-subdomain"),
    pytest.param("127.0.0.1.nip.io:8000", id="ip-als-subdomain"),
    pytest.param("mac.fritz.box:8000", id="router-name"),
]

ERLAUBTE_HOSTS = [
    "localhost:8000", "localhost", "localhost.:8000", "127.0.0.1:8000", "10.0.0.5",
    "[::1]:8000", "[2001:db8::1]:8000", "192.168.178.20:8000",
    "mein-mac.local:8000", "MEIN-MAC.LOCAL:8000", "mein-mac.local.:8000",
    "desktop-abc:8000", "testserver",
]

SCHREIBENDE_METHODEN = {"POST", "PUT", "PATCH", "DELETE"}


def _client(basis="http://testserver"):
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app, base_url=basis)


def _status(job_id):
    """Status der Stelle über den normalen Leseweg (Standard-Host, ohne Origin)."""
    r = _client().get(f"/api/jobs/{job_id}")
    assert r.status_code == 200
    return r.json()["job"]["status"]


def _docx(text):
    """Minimales Word-Dokument im Speicher; `_cv_struktur` muss es öffnen können."""
    from docx import Document

    doc = Document()
    doc.add_paragraph(text)
    puffer = io.BytesIO()
    doc.save(puffer)
    return puffer.getvalue()


def _basis_cv_hochladen(c, inhalt, kopf):
    """Basis-CV ersetzen, wie es das Formular der Profil-Seite schickt: multipart, also ohne
    Preflight, aus Browsersicht eine einfache Anfrage."""
    return c.post(
        "/api/profil/cv-basis",
        files={"file": ("cv.docx", inhalt,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"sprache": "de", "overwrite": "true"},
        headers=kopf,
    )


@pytest.fixture()
def basis_cv(client, tmp_path, monkeypatch):
    """Ein vorhandener `base_de.docx` unter einem tmp-Projektordner (`main._PROJECT_ROOT`
    umgebunden, bevor ein Endpunkt läuft). Gibt (Datei, alter Inhalt, Papierkorb) zurück."""
    import app.main as main

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)
    ordner = tmp_path / "data" / "cv_basis"
    ordner.mkdir(parents=True)
    datei = ordner / "base_de.docx"
    alt = _docx("Alter Basis-CV")
    datei.write_bytes(alt)
    return datei, alt, tmp_path / "data" / "papierkorb"


# ── Fremde Herkunft: abgewiesen, nichts verändert ─────────────────────────────────────────────
@pytest.mark.parametrize("herkunft", FREMDE_HERKUNFT)
def test_discard_fremder_herkunft_abgewiesen(seed, herkunft):
    """`discard` setzt JEDE Stelle auf „Kein Match“, egal welchen Status sie hat. Die Anfrage ist
    ein POST ohne Inhalt, der Browser schickt sie ohne Preflight ab."""
    job_id = seed["jobs"][0].id
    assert _status(job_id) == "Beworben"

    r = _client().post(f"/api/jobs/{job_id}/discard", headers={"Origin": herkunft})
    assert r.status_code == 403
    assert "Schreibzugriff abgelehnt" in r.json()["detail"]
    assert _status(job_id) == "Beworben"


@pytest.mark.parametrize("herkunft", FREMDE_HERKUNFT)
def test_basis_cv_upload_fremder_herkunft_abgewiesen(basis_cv, herkunft):
    """Mit `overwrite=true` ersetzt der Upload den Basis-CV, auf dem jeder CV-Lauf aufbaut. Die
    vorhandene Datei muss byte-gleich bleiben, und nichts landet im Papierkorb."""
    datei, alt, papierkorb = basis_cv

    r = _basis_cv_hochladen(_client(), _docx("Untergeschobener CV"), {"Origin": herkunft})
    assert r.status_code == 403
    assert datei.read_bytes() == alt
    assert not papierkorb.exists()


# ── Vite-Ausnahme: nur über den Proxy ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("sec_fetch_site", ["same-site", "cross-site", "none"])
def test_vite_herkunft_ohne_proxy_abgewiesen(seed, sec_fetch_site):
    """Origin http://localhost:5173 an Host localhost:8000 schickt der Vite-Proxy, aber genauso
    ein anderes Projekt auf Port 5173, das :8000 direkt anspricht. Der Browser unterscheidet die
    beiden: über den Proxy `same-origin`, direkt `same-site` (Ports zählen für die Site nicht)."""
    job_id = seed["jobs"][0].id

    r = _client("http://localhost:8000").post(
        f"/api/jobs/{job_id}/discard",
        headers={"Origin": "http://localhost:5173", "Sec-Fetch-Site": sec_fetch_site})
    assert r.status_code == 403
    assert _status(job_id) == "Beworben"


def test_vite_ausnahme_nur_fuer_genau_diesen_origin(seed):
    """Die Ausnahme gilt für genau den Origin, den Vite ausgibt (`http://localhost:5173`)."""
    job_id = seed["jobs"][0].id

    r = _client("http://localhost:8000").post(f"/api/jobs/{job_id}/discard",
                                              headers={"Origin": "http://127.0.0.1:5173"})
    assert r.status_code == 403
    assert _status(job_id) == "Beworben"


@pytest.mark.parametrize("basis", [
    pytest.param("http://mein-mac.local:8000", id="lan-name"),
    pytest.param("http://192.168.178.20:8000", id="lan-ip"),
    pytest.param("http://127.0.0.1:8000", id="mac-ip"),
])
def test_vite_ausnahme_nur_an_host_localhost(seed, basis):
    """Browser schicken Sec-Fetch-Site nur an vertrauenswürdige Ziele (https, localhost,
    Loopback-IP). An `<mac>.local` oder eine LAN-IP kommt von einer fremden Seite auf
    localhost:5173 nur der Origin an, ohne Sec-Fetch-Site (Review P2-57, in Chromium gemessen);
    macOS löst den eigenen .local-Namen sogar auf 127.0.0.1 auf. Der Vite-Proxy setzt den Host
    immer auf localhost:8000, nur dort gilt die Ausnahme."""
    job_id = seed["jobs"][0].id

    r = _client(basis).post(f"/api/jobs/{job_id}/discard", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 403
    assert _status(job_id) == "Beworben"


# ── Legitime Wege: schreiben weiter ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("basis, kopf", LEGITIME_WEGE)
def test_discard_auf_legitimen_wegen(seed, basis, kopf):
    job_id = seed["jobs"][0].id

    r = _client(basis).post(f"/api/jobs/{job_id}/discard", headers=kopf)
    assert r.status_code == 200
    assert _status(job_id) == "Kein Match"


@pytest.mark.parametrize("basis, kopf", LEGITIME_WEGE)
def test_basis_cv_upload_auf_legitimen_wegen(basis_cv, basis, kopf):
    datei, alt, papierkorb = basis_cv
    neu = _docx("Neuer Basis-CV")

    r = _basis_cv_hochladen(_client(basis), neu, kopf)
    assert r.status_code == 200
    assert datei.read_bytes() == neu
    assert [p.read_bytes() for p in papierkorb.iterdir()] == [alt]


# ── Reverse-Proxy (keiner im Einsatz; geklärt in der Spec) ────────────────────────────────────
def test_reverse_proxy_mit_tls_und_durchgereichtem_host(seed, monkeypatch):
    """Hinter einem Proxy mit TLS schickt der Browser `Origin: https://name`, das Backend spricht
    selbst HTTP. Verglichen werden deshalb nur Host und Port; `Host: name` ohne Port bedeutet den
    Standardport des Origin-Schemas (443). Der Name gehört in BMS_HOSTS."""
    monkeypatch.setenv("BMS_HOSTS", "bms.example.org")
    job_id = seed["jobs"][0].id

    r = _client("https://bms.example.org").post(f"/api/jobs/{job_id}/discard",
                                                headers={"Origin": "https://bms.example.org"})
    assert r.status_code == 200
    assert _status(job_id) == "Kein Match"


@pytest.mark.parametrize("basis, herkunft", [
    # nginx mit `proxy_set_header Host $host`: Der Port fehlt im Host, gilt also 443.
    pytest.param("https://bms.example.org", "https://bms.example.org:8443", id="port-verloren"),
    # nginx ohne Host-Weitergabe: Das Backend sieht die Upstream-Adresse.
    pytest.param("http://127.0.0.1:8000", "https://bms.example.org", id="host-nicht-durchgereicht"),
])
def test_reverse_proxy_ohne_passenden_host_abgewiesen(seed, monkeypatch, basis, herkunft):
    monkeypatch.setenv("BMS_HOSTS", "bms.example.org")
    job_id = seed["jobs"][0].id

    r = _client(basis).post(f"/api/jobs/{job_id}/discard", headers={"Origin": herkunft})
    assert r.status_code == 403
    assert _status(job_id) == "Beworben"


# ── Host-Prüfung gegen DNS-Rebinding ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("host", GESPERRTE_HOSTS)
@pytest.mark.parametrize("pfad", ["/api/health", "/api/jobs", "/api/dashboard", "/api/profil"])
def test_rebinding_liest_nichts(client, host, pfad):
    """Nach dem Umbiegen ist die fremde Seite same-origin; CORS schützt dann nicht mehr. Der
    Server darf unter ihrem Namen gar nicht antworten."""
    r = client.get(pfad, headers={"Host": host})
    assert r.status_code == 403
    assert "Adresse nicht freigegeben" in r.json()["detail"]


@pytest.mark.parametrize("host", GESPERRTE_HOSTS)
def test_rebinding_schreibt_nichts(seed, host):
    """Origin und Host stimmen überein, die Origin-Prüfung allein ließe das durch."""
    job_id = seed["jobs"][0].id

    r = _client().post(f"/api/jobs/{job_id}/discard", headers={"Host": host, "Origin": f"http://{host}"})
    assert r.status_code == 403
    assert _status(job_id) == "Beworben"


@pytest.mark.parametrize("host", ERLAUBTE_HOSTS)
def test_erlaubte_hosts(client, host):
    """IP-Adressen, localhost, *.local und Namen ohne Punkt lassen sich aus dem Internet nicht
    umbiegen; Groß- und Kleinschreibung und ein abschließender Punkt zählen nicht."""
    r = client.get("/api/jobs", headers={"Host": host})
    assert r.status_code == 200


@pytest.mark.parametrize("host", [
    "[evil.example]:8000", "localhost:8000:1", "user@localhost:8000", ".",
    # Kein Browser schickt diese Formen, ohne Punkt gälten sie aber als Rechnername:
    "evil%2eexample:8000", "evil\\example:8000", "evil;example:8000", "[fe80::1%en0]:8000",
])
def test_unlesbarer_host_abgewiesen(client, host):
    """Erlaubt sind nur Zeichen, die ein Browser im Host schickt (Unicode-Namen als Punycode)."""
    r = client.get("/api/jobs", headers={"Host": host})
    assert r.status_code == 403


def test_ohne_host_header_entfaellt_nur_die_host_pruefung(client):
    """Browser schicken immer einen Host-Header; ohne ihn (nur HTTP/1.0, also kein Browser und
    kein Rebinding) entfällt die Host-Prüfung. Ein fremder Origin bleibt trotzdem gesperrt. Über
    HTTP nicht erreichbar (TestClient und h11 setzen den Host), deshalb am Scope geprüft."""
    from app.main import _abweisung

    assert _abweisung({"type": "http", "method": "GET", "headers": []}) is None
    assert _abweisung({"type": "http", "method": "POST", "headers": []}) is None
    grund = _abweisung({"type": "http", "method": "POST",
                        "headers": [(b"origin", b"https://example.com")]})
    assert grund is not None and "Schreibzugriff abgelehnt" in grund


@pytest.mark.parametrize("host, erwartet", [
    ("mac.fritz.box:8000", 200),
    ("MAC.FRITZ.BOX", 200),
    ("bms.example.org", 200),
    ("tailnet-mac.tail1234.ts.net:8000", 200),
    ("andere.fritz.box:8000", 403),
    ("fritz.box", 403),
    ("evil.example", 403),
])
def test_bms_hosts_gibt_genau_die_genannten_namen_frei(client, monkeypatch, host, erwartet):
    """Komma oder Leerzeichen trennen; Port und abschließender Punkt im Eintrag zählen nicht."""
    monkeypatch.setenv("BMS_HOSTS", "mac.fritz.box, bms.example.org:443  tailnet-mac.tail1234.ts.net.")
    r = client.get("/api/jobs", headers={"Host": host})
    assert r.status_code == erwartet


# ── Wächter über alle Routen ──────────────────────────────────────────────────────────────────
@pytest.fixture()
def attrappe(client, monkeypatch):
    """Die echte App samt Middleware, aber mit einer Attrappe statt des Routers dahinter: Sie
    beantwortet jede Anfrage mit 200 und schreibt mit, was sie erreicht. So läuft kein echter
    Handler, auch dann nicht, wenn die Prüfung einmal fehlt. Sonst liefen hier alle schreibenden
    Operationen, lokal mit den echten Secrets (conftest.py setzt BMS_SECRETS_DIR nicht):
    SFTP-Probe auf den Webspace, Mail-Login.

    Die Operationen kommen aus dem OpenAPI-Schema. `app.routes` zeigt die eingebundenen Router
    nicht einzeln (FastAPI 0.140: `_IncludedRouter`); darüber hatte P2-55 vier erreichbare Routen
    übersehen. Pfadparameter werden durch `1` ersetzt, die Attrappe prüft sie nicht. Dazu kommt,
    was nicht im Schema steht, aber hinter derselben Middleware liegt: die Oberfläche (die
    SPA-Route gibt es nur mit gebautem `frontend/dist`), der Mount `/assets` sowie HEAD und
    OPTIONS. Gibt (TestClient, Operationen, erreicht) zurück."""
    from fastapi.testclient import TestClient
    from app.main import app

    http_methoden = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
    operationen = sorted(
        (methode.upper(), re.sub(r"\{[^}]+\}", "1", pfad))
        for pfad, eintrag in app.openapi()["paths"].items()
        for methode in eintrag
        if methode in http_methoden
    ) + [("GET", "/"), ("GET", "/jobs/1"), ("GET", "/assets/index.js"),
         ("HEAD", "/api/jobs"), ("OPTIONS", "/api/jobs")]
    erreicht = []

    async def router_attrappe(scope, receive, send):
        erreicht.append((scope["method"], scope["path"]))
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"erreicht"})

    monkeypatch.setattr(app, "router", router_attrappe)
    monkeypatch.setattr(app, "middleware_stack", None)   # neu aufbauen, mit der Attrappe innen
    return TestClient(app), operationen, erreicht


def test_waechter_kennt_alle_schreibenden_operationen(attrappe):
    """Sonst prüft der Wächter weniger, als er vorgibt: alle vier Methoden und die Routen der
    eingebundenen Router müssen in der Liste stehen."""
    _, operationen, _ = attrappe
    schreibend = [op for op in operationen if op[0] in SCHREIBENDE_METHODEN]

    assert {methode for methode, _ in schreibend} == SCHREIBENDE_METHODEN
    for op in [("POST", "/api/jobs/1/discard"), ("POST", "/api/profil/cv-basis"),
               ("POST", "/api/profil/import-zip"), ("POST", "/api/sicherung"),
               ("POST", "/api/settings/coach/serverpfad"), ("POST", "/api/settings/mail/test"),
               ("PUT", "/api/settings/mail")]:
        assert op in schreibend, op


@pytest.mark.parametrize("herkunft", ["https://example.com", "null"])
def test_waechter_jede_schreibende_operation_weist_fremde_herkunft_ab(attrappe, herkunft):
    c, operationen, erreicht = attrappe

    durchgelassen = [(m, p) for m, p in operationen if m in SCHREIBENDE_METHODEN
                     and c.request(m, p, headers={"Origin": herkunft}).status_code != 403]
    assert durchgelassen == []
    assert erreicht == []


def test_waechter_jede_operation_weist_fremden_host_ab(attrappe):
    c, operationen, erreicht = attrappe

    durchgelassen = [(m, p) for m, p in operationen
                     if c.request(m, p, headers={"Host": "evil.example:8000"}).status_code != 403]
    assert durchgelassen == []
    assert erreicht == []


@pytest.mark.parametrize("kopf", [
    pytest.param({}, id="ohne-origin"),
    pytest.param({"Origin": "http://testserver"}, id="eigener-origin"),
])
def test_waechter_gegenkontrolle_legitime_anfragen_erreichen_jede_route(attrappe, kopf):
    """Die Anfragen des Wächters sind wohlgeformt: legitim geschickt, kommt jede an. Sonst bewiese
    ein 403 oben nichts."""
    c, operationen, erreicht = attrappe

    abgewiesen = [(m, p) for m, p in operationen if c.request(m, p, headers=kopf).status_code != 200]
    assert abgewiesen == []
    assert len(erreicht) == len(operationen)
