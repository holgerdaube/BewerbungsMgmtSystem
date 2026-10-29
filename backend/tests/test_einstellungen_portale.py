"""Phase 87 — Suchportale als eigener Bereich auf /einstellungen (Bau-Spec Stufen A/B/C2/F1).

Deckt ab:
  1. GET seedet 8 Portale (6 Standard + frei1/frei2) — sowohl beim ALLERERSTEN GET (frische
     Singleton-Zeile, `_einstellungen_singleton()` seedet aus `suchprofil.PORTALE_DEFAULT` über
     `seed_aus_yaml()`) als auch bei einer BESTEHENDEN Zeile mit leerem `portale_json`
     (Alt-Zustand nach `ALTER TABLE ... DEFAULT '[]'`, s. `app/db.py::_ADD_COLUMNS` — dort greift
     der Auffüll-Fallback in `main.py::_einstellungen_out()`).
  2. PATCH mit einem geänderten Portal lässt die übrigen sieben unverändert (Merge-
     Regressionstest, Muster `plaene`).
  3. PATCH-Validierung: unbekannter `zugriff`, unerlaubtes URL-Schema (`ftp://`), unbekannter
     `key` und eine Freizeile mit Name aber ohne URL bei `aktiv: true` -> je 422, Bestand
     bleibt unverändert.
  4. Prüf-Endpunkt `POST /api/einstellungen/portale/pruefen`: dreistufige Bewertung
     (200/300 KB -> grün, 403 -> amber, 200/2 KB -> amber, ConnectError -> rot) gegen einen
     LOKALEN `httpx.Client`-Mock — KEINE echten Netzabrufe (Bau-Spec-Pflicht). SSRF-Sperre auf
     eine private Ziel-IP (127.0.0.1) -> rot, OHNE dass der Mock-Client überhaupt aufgerufen wird.
  5. C2 (YAML-Vertrag): nach `suchprofil.regenerieren(e)` steht der Schlüssel `portale` GENAU
     EINMAL im Kopf, als LISTE (nicht als das alte Rumpf-Dict) — auf einer YAML-KOPIE in
     `tmp_path`, NIEMALS auf der echten `config/suchprofile.yaml`.

WICHTIG — Test-Isolation:
  - `SuchEinstellung` ist ein echter Singleton (id=1) über die GANZE session-weite tmp-DB
    hinweg (conftest.py::_db_ready, scope="session") — KEIN Rollback zwischen Tests (Muster
    test_availability.py-Docstring). Jeder Test, der eine bestimmte Ausgangslage braucht, setzt
    sie deshalb selbst über `_reset_einstellungen()` (Zeile löschen) bzw. schreibt die Zeile
    direkt.
  - Ein autouse-Fixture leitet `suchprofil.SUCHPROFILE_PATH` auf eine YAML-Kopie in `tmp_path`
    um — sowohl `GET` (seedet beim allerersten Aufruf aus der Datei) als auch `PATCH`
    (regeneriert die Datei bei jedem Save) dürfen NIE die echte `config/suchprofile.yaml`
    anfassen (Bau-Spec-Pflicht).
  - App-Module werden — wie in der gesamten Suite — NIE auf Modulebene importiert, nur
    innerhalb der Testfunktionen/Fixtures.
"""
import json

import pytest


_ALLE_KEYS = {"linkedin", "indeed", "stepstone", "xing", "nejo", "arbeitsagentur", "frei1", "frei2"}


@pytest.fixture(autouse=True)
def _suchprofile_yaml_isoliert(tmp_path, monkeypatch):
    """PFLICHT (Bau-Spec Phase 87): niemals die echte config/suchprofile.yaml beschreiben. Jeder
    Test in dieser Datei bekommt automatisch eine eigene, minimale YAML-Kopie in `tmp_path` statt
    der echten Datei — `seed_aus_yaml()` (GET) hat für JEDEN fehlenden Kopf-Schlüssel einen
    sicheren Fallback (s. suchprofil.py), ein leerer Kopf reicht deshalb aus."""
    from pipeline import suchprofil

    pfad = tmp_path / "suchprofile.yaml"
    pfad.write_text(suchprofil.MARKER + "\nportale_technik: {}\n", encoding="utf-8")
    monkeypatch.setattr(suchprofil, "SUCHPROFILE_PATH", pfad)
    return pfad


def _reset_einstellungen(session):
    """Löscht die Singleton-Zeile (falls vorhanden) — macht jeden Test unabhängig von der
    Ausführungsreihenfolge innerhalb dieser Datei (s. Moduldocstring)."""
    from app.models import SuchEinstellung

    vorhanden = session.get(SuchEinstellung, 1)
    if vorhanden:
        session.delete(vorhanden)
        session.commit()


# ── 1. GET seedet 8 Portale ──────────────────────────────────────────────────────────────────
def test_get_seedet_acht_portale_bei_frischer_singleton_zeile(session, client):
    _reset_einstellungen(session)

    r = client.get("/api/einstellungen")

    assert r.status_code == 200
    portale = r.json()["portale"]
    assert len(portale) == 8
    assert {p["key"] for p in portale} == _ALLE_KEYS
    linkedin = next(p for p in portale if p["key"] == "linkedin")
    assert linkedin["name"] == "LinkedIn"
    assert linkedin["url"] == "https://www.linkedin.com/jobs/search/?keywords=$QUERY&location=$LOCATION"
    assert linkedin["zugriff"] == "websearch"
    assert linkedin["aktiv"] is True
    assert linkedin["standard"] is True
    frei1 = next(p for p in portale if p["key"] == "frei1")
    assert frei1["name"] == "" and frei1["url"] == "" and frei1["standard"] is False


def test_get_faellt_bei_bestehender_zeile_mit_leerem_portale_json_auf_default_zurueck(session, client):
    """Simuliert exakt den Altbestand nach `ALTER TABLE ... ADD COLUMN portale_json TEXT
    DEFAULT '[]'` — eine Zeile, die es schon vor dieser Phase gab und die NIE über
    `_einstellungen_singleton()`s Erzeugungs-Zweig lief. Deckt den B1-Fallback in
    `_einstellungen_out()` ab, unabhängig von der Erzeugungs-Seedung (A1)."""
    from app.models import SuchEinstellung

    _reset_einstellungen(session)
    e = SuchEinstellung(id=1, suchbereich_json="{}", plaene_json="[]", modelle_json="{}",
                        portale_json="[]")
    session.add(e)
    session.commit()

    r = client.get("/api/einstellungen")

    assert r.status_code == 200
    portale = r.json()["portale"]
    assert len(portale) == 8
    assert {p["key"] for p in portale} == _ALLE_KEYS


# ── 2. Merge-Regressionstests ────────────────────────────────────────────────────────────────
def test_patch_teilsave_auf_alt_zeile_mit_leerem_portale_json_loescht_nichts(session, client):
    """Der Fall, der in der echten Abnahme (21.08.2026) durchgefallen ist — und den der Test
    darunter NICHT abdeckt: dort legt `_reset_einstellungen` + GET die Zeile neu an, wodurch
    `portale_json` bereits die acht Defaults enthält. Eine Bestandszeile stammt aber aus
    Phase 49/50 und hatte nach dem `ALTER TABLE` nur `'[]'` — der Merge las den ROHEN DB-Wert,
    fand nichts zum Mergen und schrieb beim ersten Teil-Save sieben Portale weg (Oberfläche
    zeigte acht, DB kannte danach eines). Seit dem Fix mergen Lese- und Schreibpfad beide über
    `main._portale_liste()`.
    """
    from app.models import SuchEinstellung

    _reset_einstellungen(session)
    session.add(SuchEinstellung(id=1, suchbereich_json="{}", plaene_json="[]", modelle_json="{}",
                                portale_json="[]"))
    session.commit()

    r = client.patch("/api/einstellungen", json={"portale": [
        {"key": "frei2", "name": "Testportal", "url": "https://example.com/jobs?q=$QUERY",
         "zugriff": "websearch", "aktiv": False},
    ]})

    assert r.status_code == 200
    portale = r.json()["portale"]
    assert len(portale) == 8, "Teil-Save auf einer Alt-Zeile darf die übrigen Portale nicht löschen"
    assert {p["key"] for p in portale} == _ALLE_KEYS
    by_key = {p["key"]: p for p in portale}
    assert by_key["frei2"]["name"] == "Testportal"
    assert by_key["linkedin"]["url"].startswith("https://www.linkedin.com/jobs/")

    # Und der Bestand ist wirklich in der DB gelandet, nicht nur in der Antwort aufgefüllt.
    gespeichert = json.loads(session.get(SuchEinstellung, 1).portale_json)
    assert len(gespeichert) == 8


def test_patch_mit_einem_geaenderten_portal_laesst_die_uebrigen_sieben_unveraendert(session, client):
    _reset_einstellungen(session)
    original = client.get("/api/einstellungen").json()["portale"]
    original_by_key = {p["key"]: p for p in original}

    r = client.patch("/api/einstellungen", json={"portale": [
        {"key": "linkedin", "name": "LinkedIn (privat)", "url": "https://www.linkedin.com/jobs/?x=1",
         "zugriff": "websearch", "aktiv": False},
    ]})

    assert r.status_code == 200
    portale = r.json()["portale"]
    assert len(portale) == 8
    by_key = {p["key"]: p for p in portale}
    assert by_key["linkedin"]["name"] == "LinkedIn (privat)"
    assert by_key["linkedin"]["url"] == "https://www.linkedin.com/jobs/?x=1"
    assert by_key["linkedin"]["aktiv"] is False
    for key in _ALLE_KEYS - {"linkedin"}:
        assert by_key[key] == original_by_key[key], f"Portal {key} wurde vom Teil-Save verändert"

    # Reihenfolge bleibt stabil nach PORTALE_DEFAULT (linkedin zuerst).
    assert [p["key"] for p in portale] == [
        "linkedin", "indeed", "stepstone", "xing", "nejo", "arbeitsagentur", "frei1", "frei2"]


def test_patch_berechnet_standard_serverseitig_unabhaengig_vom_payload(session, client):
    """`standard` ist keine Nutzereingabe (s. `_validiere_portale`-Docstring) — selbst ein
    Payload, der es falsch/gar nicht mitschickt, darf die Standard/Frei-Unterscheidung nicht
    verfälschen."""
    _reset_einstellungen(session)
    client.get("/api/einstellungen")   # Zeile mit den 8 Defaults anlegen

    r = client.patch("/api/einstellungen", json={"portale": [
        {"key": "frei1", "name": "Mein Portal", "url": "https://beispiel.example/jobs",
         "zugriff": "websearch", "aktiv": True, "standard": True},   # falscher Wert im Payload
    ]})

    assert r.status_code == 200
    frei1 = next(p for p in r.json()["portale"] if p["key"] == "frei1")
    assert frei1["standard"] is False, "frei1 muss trotz payload['standard']=True als Frei-Zeile gelten"


# ── 3. Validierung ───────────────────────────────────────────────────────────────────────────
def test_patch_mit_unbekanntem_zugriff_liefert_422_und_aendert_nichts(session, client):
    _reset_einstellungen(session)
    original = client.get("/api/einstellungen").json()["portale"]

    r = client.patch("/api/einstellungen", json={"portale": [
        {"key": "linkedin", "name": "LinkedIn", "url": "https://www.linkedin.com/jobs/",
         "zugriff": "quatsch", "aktiv": True},
    ]})

    assert r.status_code == 422
    assert client.get("/api/einstellungen").json()["portale"] == original


def test_patch_mit_ftp_url_liefert_422(session, client):
    _reset_einstellungen(session)
    client.get("/api/einstellungen")

    r = client.patch("/api/einstellungen", json={"portale": [
        {"key": "nejo", "name": "Nejo", "url": "ftp://nejo.com/jobs",
         "zugriff": "fetch", "aktiv": True},
    ]})

    assert r.status_code == 422
    assert "http" in r.json()["detail"]


def test_patch_mit_unbekanntem_key_liefert_422(session, client):
    _reset_einstellungen(session)
    client.get("/api/einstellungen")

    r = client.patch("/api/einstellungen", json={"portale": [
        {"key": "monster", "name": "Monster", "url": "https://www.monster.de/",
         "zugriff": "websearch", "aktiv": True},
    ]})

    assert r.status_code == 422


def test_patch_freizeile_mit_name_ohne_url_und_aktiv_true_liefert_422(session, client):
    _reset_einstellungen(session)
    client.get("/api/einstellungen")

    r = client.patch("/api/einstellungen", json={"portale": [
        {"key": "frei1", "name": "Weiteres Portal", "url": "", "zugriff": "websearch", "aktiv": True},
    ]})

    assert r.status_code == 422


def test_patch_freizeile_mit_name_ohne_url_und_aktiv_false_ist_erlaubt(session, client):
    """Gegenprobe zum vorigen Test: leere URL ist bei den Freizeilen zulässig, SOLANGE `aktiv`
    false bleibt (Bau-Spec B2) — eine inaktive, angefangene Freizeile darf gespeichert werden."""
    _reset_einstellungen(session)
    client.get("/api/einstellungen")

    r = client.patch("/api/einstellungen", json={"portale": [
        {"key": "frei2", "name": "Weiteres Portal", "url": "", "zugriff": "websearch", "aktiv": False},
    ]})

    assert r.status_code == 200
    frei2 = next(p for p in r.json()["portale"] if p["key"] == "frei2")
    assert frei2["name"] == "Weiteres Portal" and frei2["url"] == ""


def test_patch_mit_mehr_als_acht_eintraegen_liefert_422(session, client):
    _reset_einstellungen(session)
    client.get("/api/einstellungen")

    eintrag = {"key": "linkedin", "name": "LinkedIn", "url": "https://www.linkedin.com/jobs/",
               "zugriff": "websearch", "aktiv": True}
    r = client.patch("/api/einstellungen", json={"portale": [eintrag] * 9})
    assert r.status_code == 422


# ── 4. Prüf-Endpunkt ─────────────────────────────────────────────────────────────────────────
class _FakeResp:
    """Winziger httpx-Response-Ersatz für den gestreamten Abruf — `portal_pruefen` liest nur
    `.status_code`, `.headers`, `.url`, `.is_redirect` und `.iter_bytes()`."""

    def __init__(self, status_code, body=b"", headers=None, url="http://example.test/"):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self.url = url

    @property
    def is_redirect(self):
        return self.status_code in (301, 302, 303, 307, 308) and any(
            k.lower() == "location" for k in self.headers)

    def iter_bytes(self):
        schritt = 4096
        for i in range(0, len(self._body), schritt):
            yield self._body[i:i + schritt]


class _FakeStreamCtx:
    def __init__(self, resp):
        self._resp = resp

    def __enter__(self):
        return self._resp

    def __exit__(self, *a):
        return False


def _fake_client_klasse(skript):
    """Baut eine `httpx.Client`-Ersatzklasse, die je `stream()`-Aufruf den nächsten Eintrag aus
    `skript` liefert (Antwort-Tupel `(status, body, headers, final_url)` oder eine Exception-
    Instanz, die geworfen wird) — KEIN echter Netzabruf (Bau-Spec-Pflicht)."""

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def stream(self, method, url):
            eintrag = skript.pop(0)
            if isinstance(eintrag, BaseException):
                raise eintrag
            status, body, headers, final_url = eintrag
            return _FakeStreamCtx(_FakeResp(status, body, headers, final_url))

    return _FakeClient


def _stub_dns(monkeypatch, ip: str) -> None:
    """Ersetzt `socket.getaddrinfo` durch eine feste, NETZWERKFREIE Antwort. Der SSRF-Check
    (`_portal_ziel_erlaubt` -> `_portal_ziel_privat`) löst den Hostnamen real auf, BEVOR er den
    Mock-`httpx.Client` überhaupt erreicht — ohne diesen Stub wäre jeder `pruefen`-Test gegen
    einen echten öffentlichen Portal-Namen (linkedin.com, indeed.com, ...) selbst ein echter
    DNS-Netzabruf und damit ein Verstoß gegen die Bau-Spec-Pflicht 'keine echten Netzabrufe im
    Test' (und in einer abgeschotteten CI ohne DNS ein Flaky-Risiko)."""
    import socket

    def _fake(host, *a, **kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake)


def test_pruefen_200_mit_300kb_ist_gruen(client, monkeypatch):
    import httpx

    _stub_dns(monkeypatch, "93.184.216.34")   # öffentliche Beispiel-IP, keine reale DNS-Abfrage
    fake = _fake_client_klasse([(200, b"x" * (300 * 1024), {}, "https://www.linkedin.com/jobs/")])
    monkeypatch.setattr(httpx, "Client", fake)

    r = client.post("/api/einstellungen/portale/pruefen",
                     json={"url": "https://www.linkedin.com/jobs/search/?keywords=$QUERY"})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "gruen"
    assert body["http"] == 200
    assert body["bytes"] == 300 * 1024
    assert "final_url" in body


def test_pruefen_403_ist_amber(client, monkeypatch):
    import httpx

    _stub_dns(monkeypatch, "93.184.216.34")
    fake = _fake_client_klasse([(403, b"blocked", {}, "https://de.indeed.com/jobs")])
    monkeypatch.setattr(httpx, "Client", fake)

    r = client.post("/api/einstellungen/portale/pruefen", json={"url": "https://de.indeed.com/jobs?q=$QUERY"})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "amber"
    assert body["http"] == 403


def test_pruefen_200_mit_2kb_ist_amber(client, monkeypatch):
    import httpx

    _stub_dns(monkeypatch, "93.184.216.34")
    fake = _fake_client_klasse([(200, b"x" * 2048, {}, "https://www.stepstone.de/jobs")])
    monkeypatch.setattr(httpx, "Client", fake)

    r = client.post("/api/einstellungen/portale/pruefen", json={"url": "https://www.stepstone.de/jobs?what=$QUERY"})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "amber"
    assert body["http"] == 200
    assert body["bytes"] == 2048


def test_pruefen_connect_error_ist_rot(client, monkeypatch):
    import httpx

    _stub_dns(monkeypatch, "93.184.216.34")
    fake = _fake_client_klasse([httpx.ConnectError("Verbindung verweigert")])
    monkeypatch.setattr(httpx, "Client", fake)

    r = client.post("/api/einstellungen/portale/pruefen", json={"url": "https://existiert-nicht.example/jobs"})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rot"
    assert body["http"] is None


def test_pruefen_private_ip_wird_ohne_abruf_verweigert(client, monkeypatch):
    """SSRF-Pflicht: eine private/loopback-Ziel-IP führt zu 'rot', OHNE dass überhaupt ein
    `httpx.Client` instanziiert wird — der SSRF-Check läuft VOR jedem Netzabruf. Kein DNS-Stub
    nötig: "127.0.0.1" ist bereits ein numerisches IP-Literal, `socket.getaddrinfo` löst es ohne
    jede Netzwerk-I/O lokal auf (Standard-Betriebssystemverhalten, kein DNS-Server involviert)."""
    import httpx

    class _DarfNichtAufgerufenWerden:
        def __init__(self, *a, **kw):
            raise AssertionError("httpx.Client wurde trotz SSRF-Sperre instanziiert")

    monkeypatch.setattr(httpx, "Client", _DarfNichtAufgerufenWerden)

    r = client.post("/api/einstellungen/portale/pruefen", json={"url": "http://127.0.0.1:8000/"})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rot"
    assert "privat" in body["meldung"].lower() or "lokal" in body["meldung"].lower()


def test_pruefen_ersetzt_platzhalter_vor_dem_abruf(client, monkeypatch):
    """$QUERY/$LOCATION/$PAGE müssen VOR dem Abruf ersetzt sein — sonst prüft man eine URL, die
    es so nie gibt (Bau-Spec B4)."""
    import httpx

    _stub_dns(monkeypatch, "93.184.216.34")
    aufgerufene_urls = []

    class _AufzeichnenderClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def stream(self, method, url):
            aufgerufene_urls.append(url)
            return _FakeStreamCtx(_FakeResp(200, b"x" * (30 * 1024), {}, url))

    monkeypatch.setattr(httpx, "Client", _AufzeichnenderClient)

    client.post("/api/einstellungen/portale/pruefen",
                json={"url": "https://nejo.com/de/jobs?q=$QUERY&page=$PAGE"})

    assert len(aufgerufene_urls) == 1
    assert "$QUERY" not in aufgerufene_urls[0]
    assert "$PAGE" not in aufgerufene_urls[0]
    assert "Director" in aufgerufene_urls[0]   # url-kodiertes "Director Professional Services"


# ── 5. C2 — YAML-Vertrag: `portale` genau einmal, als Liste ────────────────────────────────────
def test_regenerieren_schreibt_portale_genau_einmal_als_liste(tmp_path, monkeypatch):
    """Fallstrick C1 der Bau-Spec: schreibt der Writer `portale:` in den Kopf, während der Rumpf
    (unterhalb `suchprofil.MARKER`) NOCH den alten Schlüssel `portale:` (statt `portale_technik:`)
    trüge, gäbe es ihn zweimal auf gleicher Ebene — `yaml.safe_load` nähme still den LETZTEN
    (den Rumpf-Dict), die Einstellungen wären wirkungslos. Dieser Test baut deshalb bewusst eine
    Kopie nach, die den Rumpf bereits korrekt umbenannt zeigt (Stufe C1, von der Hauptsession
    bereits erledigt) und prüft die Kopf-Seite der Vereinbarung: GENAU EIN `portale:`-Schlüssel,
    als Liste. Arbeitet auf einer YAML-KOPIE in `tmp_path` — niemals auf der echten
    `config/suchprofile.yaml`."""
    import re

    import yaml
    from pipeline import suchprofil
    from app.models import SuchEinstellung

    pfad = tmp_path / "suchprofile_c2.yaml"
    pfad.write_text(
        suchprofil.MARKER + "\n"
        "portale_technik:\n"
        "  apify: [\"LinkedIn\", \"Indeed\", \"StepStone\", \"Xing\"]\n"
        "  websearch: [\"Firmen-Karriereseiten\"]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(suchprofil, "SUCHPROFILE_PATH", pfad)

    plaene = [
        {"plan": "A", "label": "Plan A", "aktiv": True, "prioritaet": 1,
         "titel": [], "senioritaet": [], "branche": []},
        {"plan": "B", "label": "Plan B", "aktiv": False, "prioritaet": 2,
         "titel": [], "senioritaet": [], "branche": []},
        {"plan": "C", "label": "Plan C", "aktiv": False, "prioritaet": 3,
         "titel": [], "senioritaet": [], "branche": []},
    ]
    e = SuchEinstellung(
        id=999, min_mitarbeiter=100, suchbereich_json="{}",
        plaene_json=json.dumps(plaene, ensure_ascii=False),
        modelle_json="{}",
        portale_json=json.dumps(suchprofil.PORTALE_DEFAULT, ensure_ascii=False),
    )

    suchprofil.regenerieren(e)

    text = pfad.read_text(encoding="utf-8")
    treffer = re.findall(r"^portale:\s*$", text, flags=re.MULTILINE)
    assert len(treffer) == 1, f"'portale:' muss GENAU EINMAL im Kopf stehen, gefunden: {len(treffer)}"

    geparst = yaml.safe_load(text)
    assert isinstance(geparst["portale"], list), "portale muss eine LISTE sein, kein Dict"
    assert len(geparst["portale"]) == 8
    assert {p["key"] for p in geparst["portale"]} == _ALLE_KEYS
    # Der Rumpf-Block bleibt als eigener, unterscheidbarer Schlüssel erhalten.
    assert "portale_technik" in geparst
    assert isinstance(geparst["portale_technik"], dict)


def test_regenerieren_faellt_bei_leerem_portale_json_auf_default_zurueck(tmp_path, monkeypatch):
    """Sicherheitsnetz aus `baue_managed()`: eine leere Portal-Liste (Alt-Zeile, s. Test 1 oben)
    darf beim Schreiben NICHT zu einer leeren Suche führen — sonst bricht die Suche still, bis
    irgendwer zufällig die neue Portale-Karte speichert."""
    import yaml
    from pipeline import suchprofil
    from app.models import SuchEinstellung

    pfad = tmp_path / "suchprofile_fallback.yaml"
    pfad.write_text(suchprofil.MARKER + "\nportale_technik: {}\n", encoding="utf-8")
    monkeypatch.setattr(suchprofil, "SUCHPROFILE_PATH", pfad)

    plaene = [
        {"plan": "A", "label": "Plan A", "aktiv": True, "prioritaet": 1,
         "titel": [], "senioritaet": [], "branche": []},
        {"plan": "B", "label": "Plan B", "aktiv": False, "prioritaet": 2,
         "titel": [], "senioritaet": [], "branche": []},
        {"plan": "C", "label": "Plan C", "aktiv": False, "prioritaet": 3,
         "titel": [], "senioritaet": [], "branche": []},
    ]
    e = SuchEinstellung(id=998, min_mitarbeiter=100, suchbereich_json="{}",
                        plaene_json=json.dumps(plaene, ensure_ascii=False),
                        modelle_json="{}", portale_json="[]")

    suchprofil.regenerieren(e)

    geparst = yaml.safe_load(pfad.read_text(encoding="utf-8"))
    assert len(geparst["portale"]) == 8
    assert {p["key"] for p in geparst["portale"]} == _ALLE_KEYS


# ── 6. P2-73 — abgelöste Standard-Adressen ───────────────────────────────────────────────────
# Ein Portal ist umgezogen, die alte Adresse leitet nur noch um. Ein neuer Wert in
# `PORTALE_DEFAULT` erreicht keine bestehende Installation: Dort liegt die Liste schon in der
# Datenbank und im Kopf der Suchprofil-Datei. Die Tests hier decken die reine Ersetzungsregel,
# den Start-Schritt (Datenbank UND Datei) und die Prüfung ab, die einen Umzug sichtbar macht.
_NEJO_ALT = "https://mynejo.com/de-de/jobs?q=$QUERY&page=$PAGE"
_BA_ALT = "https://www.arbeitsagentur.de/jobsuche/suche?angebotsart=1&was=$QUERY"
_PLAENE_LEER = [
    {"plan": "A", "label": "Plan A", "aktiv": True, "prioritaet": 1,
     "titel": [], "senioritaet": [], "branche": []},
    {"plan": "B", "label": "Plan B", "aktiv": True, "prioritaet": 2,
     "titel": [], "senioritaet": [], "branche": []},
    {"plan": "C", "label": "Plan C", "aktiv": False, "prioritaet": 3,
     "titel": [], "senioritaet": [], "branche": []},
]


def _portale_mit(**urls):
    """Die Standard-Liste, je Schlüssel mit der übergebenen Adresse statt der heutigen."""
    from pipeline import suchprofil

    return [{**p, "url": urls.get(p["key"], p["url"])} for p in suchprofil.PORTALE_DEFAULT]


def _zeile_schreiben(session, portale_json: str):
    """Legt die Einstellungs-Zeile mit genau dieser Portal-Liste an und schreibt die Datei so,
    wie ein Speichern sie hinterlassen hätte (Kopf aus der Zeile, Rumpf unverändert)."""
    from app.models import SuchEinstellung
    from pipeline import suchprofil

    _reset_einstellungen(session)
    e = SuchEinstellung(id=1, min_mitarbeiter=100, suchbereich_json="{}",
                        plaene_json=json.dumps(_PLAENE_LEER, ensure_ascii=False),
                        modelle_json="{}", portale_json=portale_json)
    session.add(e)
    session.commit()
    session.refresh(e)
    suchprofil.regenerieren(e)
    return e


def _url_in_datei(pfad, key):
    import yaml

    return {p["key"]: p["url"] for p in yaml.safe_load(pfad.read_text(encoding="utf-8"))["portale"]}[key]


def test_standards_und_fruehere_standards_sind_ueberschneidungsfrei():
    """Stünde eine heutige Standard-Adresse zugleich in der Liste der abgelösten, würde der
    Start-Schritt sie bei jedem Start „ersetzen“ und die Datei jedes Mal neu schreiben."""
    from pipeline import suchprofil

    heute = {p["key"]: p["url"] for p in suchprofil.PORTALE_DEFAULT}
    for key, fruehere in suchprofil.PORTALE_FRUEHERE_STANDARDS.items():
        assert key in heute, f"unbekannter Portal-Schlüssel: {key}"
        assert heute[key] not in fruehere


def test_nachziehen_ersetzt_nur_woertlich_abgeloeste_adressen():
    from pipeline import suchprofil

    heute = {p["key"]: p["url"] for p in suchprofil.PORTALE_DEFAULT}
    eingabe = _portale_mit(nejo=_NEJO_ALT, arbeitsagentur=_BA_ALT)
    # Felder, die der Nutzer geändert haben kann, dürfen die Ersetzung weder verhindern noch
    # dabei verloren gehen.
    for p in eingabe:
        if p["key"] == "nejo":
            p["aktiv"], p["name"] = False, "Nejo (eigener Name)"
    vorher = json.dumps(eingabe, sort_keys=True)

    neu, geaendert = suchprofil.standard_adressen_nachziehen(eingabe)

    assert geaendert == ["nejo", "arbeitsagentur"]
    nach_key = {p["key"]: p for p in neu}
    assert nach_key["nejo"]["url"] == heute["nejo"] == "https://nejo.com/de/jobs?q=$QUERY&page=$PAGE"
    assert nach_key["nejo"]["aktiv"] is False and nach_key["nejo"]["name"] == "Nejo (eigener Name)"
    assert nach_key["arbeitsagentur"]["url"] == heute["arbeitsagentur"]
    assert nach_key["arbeitsagentur"]["url"].endswith("&suchbereich=jobs")
    assert nach_key["linkedin"] == next(p for p in eingabe if p["key"] == "linkedin")
    assert json.dumps(eingabe, sort_keys=True) == vorher, "die Eingabe darf nicht verändert werden"
    # Zweiter Durchgang: nichts mehr zu tun.
    assert suchprofil.standard_adressen_nachziehen(neu) == (neu, [])


def test_nachziehen_laesst_eine_eigene_adresse_stehen():
    """Auch wenn sie auf den alten Host zeigt: Wer die Adresse geändert hat, hat entschieden."""
    from pipeline import suchprofil

    eigene = "https://mynejo.com/de-de/jobs?q=$QUERY&page=$PAGE&is_management_job=true"
    eingabe = _portale_mit(nejo=eigene)

    neu, geaendert = suchprofil.standard_adressen_nachziehen(eingabe)

    assert geaendert == []
    assert {p["key"]: p["url"] for p in neu}["nejo"] == eigene


def test_start_zieht_datenbank_und_datei_nach(session, _suchprofile_yaml_isoliert):
    from app import main
    from app.models import SuchEinstellung

    pfad = _suchprofile_yaml_isoliert
    _zeile_schreiben(session, json.dumps(_portale_mit(nejo=_NEJO_ALT, arbeitsagentur=_BA_ALT)))
    assert _url_in_datei(pfad, "nejo") == _NEJO_ALT          # Ausgangslage wie nach einem Update

    assert main._portal_adressen_nachziehen() == ["nejo", "arbeitsagentur"]

    session.expire_all()
    gespeichert = {p["key"]: p["url"] for p in json.loads(session.get(SuchEinstellung, 1).portale_json)}
    assert gespeichert["nejo"] == "https://nejo.com/de/jobs?q=$QUERY&page=$PAGE"
    assert gespeichert["arbeitsagentur"].endswith("&was=$QUERY&suchbereich=jobs")
    assert _url_in_datei(pfad, "nejo") == gespeichert["nejo"]
    assert _url_in_datei(pfad, "arbeitsagentur") == gespeichert["arbeitsagentur"]
    assert "portale_technik: {}" in pfad.read_text(encoding="utf-8"), "der Rumpf bleibt erhalten"
    # Zweiter Start: nichts zu tun, die Datei wird nicht noch einmal geschrieben.
    stand = pfad.read_text(encoding="utf-8")
    assert main._portal_adressen_nachziehen() == []
    assert pfad.read_text(encoding="utf-8") == stand


def test_start_laesst_eigene_adresse_in_datenbank_und_datei_stehen(session, _suchprofile_yaml_isoliert):
    from app import main
    from app.models import SuchEinstellung

    eigene = "https://jobs.example.test/suche?q=$QUERY"
    _zeile_schreiben(session, json.dumps(_portale_mit(nejo=eigene)))
    stand = _suchprofile_yaml_isoliert.read_text(encoding="utf-8")

    assert main._portal_adressen_nachziehen() == []

    session.expire_all()
    assert {p["key"]: p["url"] for p in json.loads(session.get(SuchEinstellung, 1).portale_json)}["nejo"] == eigene
    assert _suchprofile_yaml_isoliert.read_text(encoding="utf-8") == stand


def test_start_ohne_einstellungszeile_legt_keine_an(session, _suchprofile_yaml_isoliert):
    """Das Anlegen samt Seed gehört dem ersten GET. Ein Start-Schritt, der die Zeile selbst
    anlegte, würde den Seed aus der Suchprofil-Datei umgehen."""
    from app import main
    from app.models import SuchEinstellung

    _reset_einstellungen(session)
    stand = _suchprofile_yaml_isoliert.read_text(encoding="utf-8")

    assert main._portal_adressen_nachziehen() == []

    session.expire_all()
    assert session.get(SuchEinstellung, 1) is None
    assert _suchprofile_yaml_isoliert.read_text(encoding="utf-8") == stand


def test_start_schreibt_bei_leerer_portal_liste_nur_die_datei_neu(session, _suchprofile_yaml_isoliert):
    """Altbestand vor Phase 87: `portale_json == '[]'`. Die Oberfläche zeigt dann schon die
    heutigen Standards (Auffüllung beim Lesen), im Kopf der Datei steht aber, was beim letzten
    Speichern galt, und die Such-Skills lesen die Datei."""
    import yaml
    from app import main
    from app.models import SuchEinstellung
    from pipeline import suchprofil

    pfad = _suchprofile_yaml_isoliert
    _zeile_schreiben(session, "[]")
    # Kopf so, wie ihn ein Speichern VOR dem Umzug geschrieben hat.
    kopf = yaml.safe_dump({"portale": _portale_mit(nejo=_NEJO_ALT)}, allow_unicode=True, sort_keys=False)
    pfad.write_text(kopf + "\n" + suchprofil.MARKER + "\nportale_technik: {}\n", encoding="utf-8")

    assert main._portal_adressen_nachziehen() == ["Suchprofil-Datei"]

    assert _url_in_datei(pfad, "nejo") == "https://nejo.com/de/jobs?q=$QUERY&page=$PAGE"
    session.expire_all()
    assert session.get(SuchEinstellung, 1).portale_json == "[]", "die Zeile selbst bleibt, wie sie war"
    assert main._portal_adressen_nachziehen() == []


def test_pruefen_umleitung_auf_anderen_host_ist_amber(client, monkeypatch):
    """Der Fall, der drei Wochen unbemerkt blieb: Die alte Adresse antwortet nach einer Umleitung
    mit vollem Inhalt. Für die Such-Agenten ist das kein funktionierendes Portal, sondern ein
    Abruf, der nur eine Umleitung meldet."""
    import httpx

    _stub_dns(monkeypatch, "93.184.216.34")
    fake = _fake_client_klasse([
        (301, b"", {"Location": "https://nejo.com/de/jobs?q=x&page=1"}, "https://mynejo.com/de-de/jobs?q=x&page=1"),
        (200, b"x" * (300 * 1024), {}, "https://nejo.com/de/jobs?q=x&page=1"),
    ])
    monkeypatch.setattr(httpx, "Client", fake)

    r = client.post("/api/einstellungen/portale/pruefen", json={"url": _NEJO_ALT})

    body = r.json()
    assert r.status_code == 200
    assert body["status"] == "amber"
    assert body["http"] == 200 and body["bytes"] == 300 * 1024
    assert body["final_url"].startswith("https://nejo.com/")
    assert "nejo.com" in body["meldung"] and "neue Adresse" in body["meldung"]


def test_pruefen_umleitung_auf_demselben_host_bleibt_gruen(client, monkeypatch):
    """Eine Seite, die nur ihre eigene Adresse umschreibt (Parameter anhängt, Pfad normalisiert),
    ist kein Umzug: Solchen Umleitungen folgt auch der Abruf der Such-Agenten selbst."""
    import httpx

    _stub_dns(monkeypatch, "93.184.216.34")
    basis = "https://www.arbeitsagentur.de/jobsuche/suche?angebotsart=1&was=x"
    fake = _fake_client_klasse([
        (301, b"", {"Location": basis + "&suchbereich=jobs"}, basis),
        (200, b"x" * (300 * 1024), {}, basis + "&suchbereich=jobs"),
    ])
    monkeypatch.setattr(httpx, "Client", fake)

    r = client.post("/api/einstellungen/portale/pruefen", json={"url": _BA_ALT})

    body = r.json()
    assert body["status"] == "gruen"
    assert "antwortet, liefert Inhalt" in body["meldung"]
