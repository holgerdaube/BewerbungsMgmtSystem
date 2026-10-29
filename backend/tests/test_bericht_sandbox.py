"""P2-58: HTML-Berichte und der Tages-Digest laufen im Browser in einer Sandbox, getrennt vom
Ursprung der API.

Befund (Review zu P2-57, 29.09.2026): /api/artifact lieferte HTML-Berichte inline vom BMS-Ursprung
aus. Ein Skript in einem Bericht (Prompt-Injection aus Webinhalten, die ein KI-Lauf übernimmt, oder
ein ausbrechendes Attribut in den alten JS-Dashboards) lief damit im Ursprung der API. Im Browser
nachgestellt: Ein Probebericht las /api/jobs und verwarf eine Stelle per POST .../discard, beides
mit 200 (tasks/spec_p2-58_bericht_sandbox.md). Seitdem trägt jede Inline-HTML-Antwort
`Content-Security-Policy: sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox`
und `Cache-Control: no-cache`. Ohne allow-same-origin ist der Ursprung des Berichts `null`: Lesen
verhindert die fehlende CORS-Freigabe (P2-55), Schreiben die Herkunftsprüfung (P2-57).

Isolation wie tests/test_artifact_security.py: Die Fixture `projekt` bindet `main._PROJECT_ROOT`
auf ein tmp-Verzeichnis um, Dateien entstehen per pathlib, angefragt wird mit Posix-Pfaden wie in
der DB (läuft so auch im Job backend-windows). App-Module nur funktionslokal importieren
(s. conftest.py).
"""
import ast
from pathlib import Path

import pytest

# Was der Bericht darf, als Menge: Skripte (71 ältere Berichte bauen ihren Inhalt per Skript auf),
# neue Tabs, und diese Tabs ohne Sandbox. Gleichheit statt Anwesenheit (Lektion P2-44): Ein
# zusätzliches allow-same-origin höbe den ganzen Schutz auf.
ERWARTET = {"allow-scripts", "allow-popups", "allow-popups-to-escape-sandbox"}

_HTML = b'<!DOCTYPE html><html><head><meta charset="utf-8"><title>Bericht</title></head><body>ok</body></html>'


def _anlegen(wurzel, rel, inhalt):
    ziel = wurzel.joinpath(*rel.split("/"))
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(inhalt)
    return ziel


@pytest.fixture()
def projekt(tmp_path, monkeypatch):
    import app.main as main

    wurzel = tmp_path / "projekt"
    wurzel.mkdir()
    monkeypatch.setattr(main, "_PROJECT_ROOT", wurzel)
    return wurzel


def _csp(antwort):
    """Alle CSP-Header der Antwort als Liste (leer ohne Header)."""
    return antwort.headers.get_list("content-security-policy")


def _in_sandbox(antwort):
    """Sandbox-Header genau einmal und mit genau dem Wert, dazu no-cache: Ohne no-cache zeigte
    Chrome einen früher geöffneten Bericht weiter ohne Sandbox aus dem Festplatten-Cache (gemessen,
    s. Spec)."""
    import app.main as main

    return (_csp(antwort) == [main._BERICHT_SANDBOX]
            and antwort.headers.get("cache-control") == "no-cache")


def test_header_wert_ist_genau_die_sandbox():
    import app.main as main

    teile = main._BERICHT_SANDBOX.split()
    assert teile[0] == "sandbox"
    assert set(teile[1:]) == ERWARTET
    assert "allow-same-origin" not in teile, "allow-same-origin gäbe dem Bericht den Ursprung der API zurück"
    assert main._BERICHT_KOPF == {"Content-Security-Policy": main._BERICHT_SANDBOX, "Cache-Control": "no-cache"}


def test_jeder_bericht_ordner_liefert_html_in_der_sandbox(client, projekt):
    """Abgeleitet aus der Positivliste: Ein neuer Ordner mit Berichten läuft automatisch mit."""
    import app.main as main

    ordner = sorted(name for name, endungen in main._ARTEFAKT_ORDNER.items() if ".html" in endungen)
    assert {"data/company_fit", "data/job_postings", "data/interview_prep", "data/beirat",
            "data/analysen", "data/transcripts"} <= set(ordner)
    for name in ordner:
        pfad = f"{name}/2026_09_29_Bericht.html"
        _anlegen(projekt, pfad, _HTML)
        antwort = client.get("/api/artifact", params={"path": pfad})
        assert antwort.status_code == 200, name
        assert antwort.headers["content-type"].startswith("text/html"), name
        assert _in_sandbox(antwort), (name, _csp(antwort), antwort.headers.get("cache-control"))
        assert antwort.headers.get("x-content-type-options") == "nosniff", name


def test_alle_drei_rueckgabewege_tragen_die_sandbox(client, projekt):
    """artifact() antwortet auf drei Wegen mit HTML: HTMLResponse, wenn das Favicon nachgesetzt
    wird; FileResponse, wenn der Bericht das BMS-Icon schon trägt; FileResponse als Rückfall bei
    ungültigem UTF-8. Jeder Weg ist über den Inhalt der Antwort erkennbar."""
    from app import favicon

    assert favicon.FAVICON_LINK, "das Icon des Designs fehlt, der Test prüfte sonst nur einen Weg"
    ohne_icon = _HTML
    mit_icon = ('<!DOCTYPE html><html><head><meta charset="utf-8">' + favicon.FAVICON_LINK
                + "<title>Neu</title></head><body>neu</body></html>").encode("utf-8")
    kaputt = b'<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>\xff\xfe</body></html>'
    faelle = {
        "data/company_fit/2026_07_09_CompanyFit_Alt.html": ohne_icon,
        "data/company_fit/2026_09_29_CompanyFit_Neu.html": mit_icon,
        "data/company_fit/2026_09_29_CompanyFit_Kaputt.html": kaputt,
    }
    for pfad, inhalt in faelle.items():
        _anlegen(projekt, pfad, inhalt)

    alt = client.get("/api/artifact", params={"path": "data/company_fit/2026_07_09_CompanyFit_Alt.html"})
    assert favicon.FAVICON_LINK in alt.text, "Favicon wird weiter nachgesetzt (P2-44)"
    neu = client.get("/api/artifact", params={"path": "data/company_fit/2026_09_29_CompanyFit_Neu.html"})
    assert neu.content == mit_icon
    rueckfall = client.get("/api/artifact", params={"path": "data/company_fit/2026_09_29_CompanyFit_Kaputt.html"})
    assert rueckfall.content == kaputt

    for antwort in (alt, neu, rueckfall):
        assert antwort.status_code == 200
        assert antwort.headers["content-type"].startswith("text/html")
        assert _in_sandbox(antwort), (_csp(antwort), antwort.headers.get("cache-control"))
        assert antwort.headers.get("x-content-type-options") == "nosniff"


@pytest.mark.parametrize("pfad, inhalt, typ", [
    ("data/job_files/job_7/2026_09_29_Stellenbeschreibung.pdf", b"%PDF-1.4 probe", "application/pdf"),
    ("outputs/cv/CV_Name_Firma_Position.pdf", b"%PDF-1.4 probe", "application/pdf"),
    ("data/job_files/job_7/2026_09_29_Screenshot.png", b"\x89PNG probe", "image/png"),
    ("data/cv_basis/base_de.docx", b"PK probe", "application/octet-stream"),
    ("outputs/anschreiben/Anschreiben_Name_Firma.docx", b"PK probe", "application/octet-stream"),
    ("data/transcripts/2026_09_29_Transkript_Firma.md", b"# Rohtext", "application/octet-stream"),
])
def test_andere_dateitypen_ohne_sandbox(client, projekt, pfad, inhalt, typ):
    """Den Schaden richtet nur HTML im Ursprung der API an: Eine PDF zeigt der Browser in seinem
    eigenen Betrachter, ein Bild führt nichts aus, Word und Markdown gehen als Download raus."""
    _anlegen(projekt, pfad, inhalt)

    anzeige = client.get("/api/artifact", params={"path": pfad})
    download = client.get("/api/artifact", params={"path": pfad, "download": "true"})

    assert anzeige.headers["content-type"].startswith(typ)
    assert download.headers["content-type"].startswith("application/octet-stream")
    for antwort in (anzeige, download):
        assert antwort.status_code == 200
        assert _csp(antwort) == []
        assert antwort.headers.get("x-content-type-options") == "nosniff"


def test_html_als_download_ohne_sandbox(client, projekt):
    """Ein Download wird nicht angezeigt; er kommt unverändert und ohne Sandbox (Datei aus dem
    Finder hat ohnehin keinen BMS-Ursprung)."""
    pfad = "data/company_fit/2026_09_29_CompanyFit_Download.html"
    _anlegen(projekt, pfad, _HTML)

    antwort = client.get("/api/artifact", params={"path": pfad, "download": "true"})

    assert antwort.status_code == 200
    assert antwort.headers["content-type"].startswith("application/octet-stream")
    assert antwort.content == _HTML
    assert _csp(antwort) == []


def test_tages_digest_in_der_sandbox(client):
    """Der Digest zeigt fremden Text (Absender und Betreff von Mails, Titel aus den Portalen)."""
    antwort = client.get("/api/digest")

    assert antwort.status_code == 200
    assert antwort.headers["content-type"].startswith("text/html")
    assert _in_sandbox(antwort), (_csp(antwort), antwort.headers.get("cache-control"))


def test_oberflaeche_bleibt_ohne_sandbox(tmp_path, monkeypatch):
    """Die Oberfläche ist die App und braucht ihren Ursprung (Muster test_spa_fallback.py: Die
    echte Route gibt es nur mit gebautem frontend/dist, deshalb eine Mini-App mit main.spa)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import app.main as main

    dist = tmp_path / "frontend" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "assets" / "app.js").write_text("//", encoding="utf-8")
    (dist / "index.html").write_text("<!doctype html><title>BMS</title>", encoding="utf-8")
    monkeypatch.setattr(main, "_DIST", dist)
    mini = FastAPI()
    mini.get("/{full_path:path}")(main.spa)
    spa = TestClient(mini)

    for adresse in ("/", "/jobs/12", "/assets/app.js"):
        antwort = spa.get(adresse)
        assert antwort.status_code == 200, adresse
        assert _csp(antwort) == [], adresse


def test_sandbox_wirkt_nur_mit_cors_und_herkunftspruefung(client, seed):
    """Die Sandbox nimmt dem Bericht nur den Ursprung. Dass er damit nichts mehr erreicht, liegt an
    zwei anderen Stellen, die hier mit Origin `null` (so fragt ein Bericht in der Sandbox an)
    festgehalten sind: keine CORS-Freigabe beim Lesen (P2-55), 403 beim Schreiben (P2-57)."""
    job_id = seed["jobs"][0].id

    lesen = client.get("/api/jobs", headers={"Origin": "null"})
    assert lesen.status_code == 200          # der Server antwortet, der Browser gibt es nicht heraus
    assert "access-control-allow-origin" not in lesen.headers

    schreiben = client.post(f"/api/jobs/{job_id}/discard", headers={"Origin": "null"})
    assert schreiben.status_code == 403
    assert client.get(f"/api/jobs/{job_id}").json()["job"]["status"] == "Beworben"


class _HtmlFunde(ast.NodeVisitor):
    """Sammelt je Aufruf, der HTML ausliefert (HTMLResponse oder media_type mit html), die
    umgebende Funktion und ob `headers=` übergeben wird."""

    def __init__(self, datei):
        self.datei = datei
        self.stapel = ["<Modul>"]
        self.funde = set()

    def _funktion(self, knoten):
        self.stapel.append(knoten.name)
        self.generic_visit(knoten)
        self.stapel.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _funktion

    def visit_Call(self, knoten):
        name = getattr(knoten.func, "id", None) or getattr(knoten.func, "attr", None)
        html_typ = any(k.arg == "media_type" and isinstance(k.value, ast.Constant)
                       and "html" in str(k.value.value) for k in knoten.keywords)
        if name == "HTMLResponse" or html_typ:
            self.funde.add((self.datei, self.stapel[-1], any(k.arg == "headers" for k in knoten.keywords)))
        self.generic_visit(knoten)


def test_waechter_html_nur_aus_artifact_digest_und_doku():
    """Jede HTML-Antwort aus einer Route muss in die Sandbox. Wer eine neue HTML-Route baut,
    setzt dort `_BERICHT_KOPF` (s. tasks/spec_p2-58_bericht_sandbox.md) und trägt sie hier
    ein. Die Oberfläche (main.spa) liefert index.html ohne media_type und fällt nicht darunter.
    P2-59: Die Dokumentationsseite (`routes_doku.dokument`) ist die dritte Stelle; ihr Kopf ist
    in tests/test_doku.py gegen `main._BERICHT_KOPF` geprüft."""
    app_ordner = Path(__file__).resolve().parent.parent / "app"
    funde = set()
    for datei in sorted(app_ordner.glob("*.py")):
        sammler = _HtmlFunde(datei.name)
        sammler.visit(ast.parse(datei.read_text(encoding="utf-8")))
        funde |= sammler.funde

    assert funde == {("main.py", "artifact", True), ("main.py", "digest", True),
                     ("routes_doku.py", "dokument", True)}, (
        f"HTML-Auslieferung außerhalb von artifact/digest/dokument oder ohne headers=: {sorted(funde)}")
