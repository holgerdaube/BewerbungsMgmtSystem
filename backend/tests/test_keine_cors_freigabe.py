"""P2-55: Das Backend gibt fremden Webseiten keine CORS-Freigabe.

Bis P2-55 stand in `main.py` `CORSMiddleware(allow_origins=["*"], allow_methods=["*"],
allow_headers=["*"])`. Jede Webseite, die im selben Browser offen war, durfte damit die Antworten
der lokalen API lesen (Stellen, Mails, Profil) und nach bestandenem Preflight auch schreiben
(KI-Läufe starten, Stellen löschen). Kein legitimer Aufrufer braucht eine Freigabe: Die
Oberfläche kommt vom selben Server, auch im LAN-Modus; der Vite-Dev-Server leitet `/api` per
Proxy weiter; Skills und Skripte nutzen curl oder Python, für die CORS nicht gilt (Beleg je
Aufrufer: tasks/spec_p2-55_keine_cors_freigabe.md).

Geprüft wird das Verhalten, also der Header, an dem der Browser entscheidet, nicht die Struktur
der App: Ein Test „keine CORSMiddleware registriert" schwiege bei handgesetzten Headern.

Wer später doch eine Herkunft freigeben muss: einzeln eintragen, nie `*`, und diese Datei bewusst
anpassen.

Wie in conftest.py: App-Module nur funktionslokal importieren (Fixtures `client`/`seed` oder im
Test selbst).
"""
import pytest

# Fremde Herkünfte: eine beliebige Webseite, eine lokal geöffnete HTML-Datei oder ein
# Sandbox-iframe (`null`) und der Standardport JEDES Vite-Projekts auf dem Rechner. Die
# Oberfläche braucht keine davon, auch nicht im Dev-Betrieb (Proxy, s. LEGITIME_WEGE).
FREMDE_HERKUNFT = ["https://example.com", "null", "http://localhost:5173"]

# Wege, auf denen die Oberfläche die API erreicht: `basis` ist, was der Server als Host sieht,
# `herkunft` der Origin, den der Browser bei schreibenden Anfragen mitschickt.
LEGITIME_WEGE = [
    pytest.param("http://localhost:8000", "http://localhost:8000", id="mac"),
    pytest.param("http://127.0.0.1:8000", "http://127.0.0.1:8000", id="mac-ip"),
    pytest.param("http://mein-mac.local:8000", "http://mein-mac.local:8000", id="lan-name"),
    pytest.param("http://192.168.178.20:8000", "http://192.168.178.20:8000", id="lan-ip"),
    # Vite-Dev-Server: Der Browser spricht nur mit :5173. Der Proxy (Kurzform in vite.config.ts,
    # Vite setzt dafür changeOrigin: true) schreibt den Host auf localhost:8000 um und reicht den
    # Origin des Browsers unverändert durch.
    pytest.param("http://localhost:8000", "http://localhost:5173", id="vite-proxy"),
]


def _freigabe(response):
    """`Access-Control-Allow-Origin` der Antwort, sonst None. An genau diesem Header macht der
    Browser die CORS-Prüfung fest: Fehlt er, bekommt die fremde Seite die Antwort nicht zu sehen,
    und nach einem Preflight ohne ihn schickt der Browser die eigentliche Anfrage nicht ab.
    Andere Access-Control-*-Header wirken ohne ihn nicht; Starlettes CORSMiddleware hängt
    `Allow-Methods` und `Max-Age` sogar an abgelehnte Preflights. Eine Prüfung auf „gar keine
    Access-Control-Header" gäbe deshalb Fehlalarm, sobald einmal eine einzelne Herkunft bewusst
    freigegeben wird (Gegenprobe P2-55)."""
    return response.headers.get("access-control-allow-origin")


@pytest.mark.parametrize("herkunft", FREMDE_HERKUNFT)
@pytest.mark.parametrize("pfad", ["/api/health", "/api/jobs", "/api/dashboard", "/api/inbox"])
def test_einfache_anfrage_fremder_herkunft_ohne_freigabe(client, herkunft, pfad):
    """Der Server beantwortet die Anfrage (CORS setzt der Browser durch, nicht der Server), gibt
    aber keine Freigabe: Ohne `Access-Control-Allow-Origin` verweigert der Browser der fremden
    Seite das Lesen der Antwort."""
    r = client.get(pfad, headers={"Origin": herkunft})
    assert r.status_code == 200
    assert _freigabe(r) is None


@pytest.mark.parametrize("herkunft", FREMDE_HERKUNFT)
def test_fehlerantwort_fremder_herkunft_ohne_freigabe(client, herkunft):
    """Auch Fehlerantworten bleiben ohne Freigabe; die CORSMiddleware hängte sie an jede Antwort."""
    r = client.get("/api/jobs/999999999", headers={"Origin": herkunft})
    assert r.status_code == 404
    assert _freigabe(r) is None


@pytest.mark.parametrize("herkunft", FREMDE_HERKUNFT)
@pytest.mark.parametrize("methode, pfad, header", [
    ("POST", "/api/tasks", "content-type"),   # JSON-Inhalt; startet KI-Läufe, die Geld kosten
    ("PATCH", "/api/jobs/1", "content-type"),
    ("DELETE", "/api/jobs/1", None),
])
def test_preflight_fremder_herkunft_ohne_freigabe(client, herkunft, methode, pfad, header):
    """Den Preflight schickt der Browser vor jeder Anfrage mit JSON-Inhalt und vor PATCH/DELETE.
    Fehlt in dessen Antwort die Freigabe, schickt er die eigentliche Anfrage gar nicht erst ab.
    Bis P2-55 bestand jeder Preflight. Den Status legt der Test bewusst nicht fest (heute 405):
    Entscheidend ist die fehlende Freigabe, nicht wie der Server OPTIONS beantwortet."""
    kopf = {"Origin": herkunft, "Access-Control-Request-Method": methode}
    if header:
        kopf["Access-Control-Request-Headers"] = header
    r = client.options(pfad, headers=kopf)
    assert _freigabe(r) is None


@pytest.mark.parametrize("basis, herkunft", LEGITIME_WEGE)
def test_eigene_oberflaeche_liest_und_schreibt_weiter(seed, basis, herkunft):
    """Die Oberfläche braucht keine Freigabe, weil sie aus Browsersicht immer mit ihrem eigenen
    Ursprung spricht. Lesen (GET ohne Origin, so schickt es der Browser bei gleichem Ursprung) und
    Schreiben (PATCH mit JSON und Origin) funktionieren auf jedem Weg. Dieser Test ist auch der
    Vertrag für eine spätere Herkunftsprüfung im Backend: Sie darf keinen dieser Wege sperren."""
    from fastapi.testclient import TestClient
    from app.main import app

    c = TestClient(app, base_url=basis)
    job_id = seed["jobs"][0].id

    r = c.get("/api/jobs")
    assert r.status_code == 200
    assert job_id in {j["id"] for j in r.json()}

    marker = f"P2-55 {seed['suffix']} {basis} {herkunft}"
    r = c.patch(f"/api/jobs/{job_id}", json={"next_step": marker}, headers={"Origin": herkunft})
    assert r.status_code == 200

    r = c.get(f"/api/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["job"]["next_step"] == marker
