"""Tests für P2-76 (Portal-Status über den Abruf mit Wiederholung), Vertrag A: `verify_jobs`.

Anlass: Firma-Prüfung und Beworben-Check lasen den Portal-Status per WebFetch (Modell-Zusammenfassung,
bei LinkedIn oft HTTP 429). Jetzt kommt er aus `check_url`:
  * zwei neue Seitentext-Marker (LinkedIn deutsch: „keine Bewerbungen mehr angenommen", dazu „nimmt
    keine Bewerbungen mehr entgegen"),
  * `httpx.ReadTimeout` / `httpx.RemoteProtocolError` (Portal nimmt die Verbindung an und antwortet
    nicht, etwa StepStone) sind `NICHT_PRUEFBAR` statt `TOT`; Verbindungsaufbau gescheitert bleibt `TOT`,
  * bei `ABGELAUFEN` durch einen Seitentext-Marker liefert `check_url(return_text=True)` den Anzeigentext
    mit, wenn Titel ≥ 60 % und Firma noch auf der Seite stehen (bei einer Umleitung nie),
  * `portal_status(pr)` (rein) und die Kommandozeile `portal <job_id> …` (nur lesend).

Netz nur über `httpx.MockTransport` (der echte `httpx.Client` bekommt den Transport), Pausen laufen
über `verify_jobs._schlafen` und werden nur mitgeschrieben. Konvention conftest.py: keine
app.*/pipeline.*-Importe auf Modulebene."""
import json
import sys
import uuid

import httpx
import pytest

_URL = "https://www.linkedin.com/jobs/view/1234567890/"
_FIRMA = "Beispiel GmbH"
_TITEL = "Head of Customer Success"
_MARKER_DE = "Es werden keine Bewerbungen mehr angenommen."

_OFFEN = ("<html><body><p>Beispiel GmbH sucht: Head of Customer Success.</p>"
          "<p>Aufgaben: Kundenerfolg verantworten, Team führen. Wir freuen uns auf Ihre Bewerbungen.</p>"
          "</body></html>")
_GESCHLOSSEN = ("<html><body><p>Beispiel GmbH sucht: Head of Customer Success.</p>"
                "<p>Aufgaben: Kundenerfolg verantworten, Team führen.</p>"
                f"<p>{_MARKER_DE}</p></body></html>")

# Die Fixtures unten ersetzen `httpx.Client`; den echten Client merken wir uns hier.
_ECHTER_CLIENT = httpx.Client


def _antwort(status, text=_OFFEN, headers=None):
    return httpx.Response(status, text=text, headers=headers or {})


@pytest.fixture
def pausen(monkeypatch):
    """Ersetzt `verify_jobs._schlafen` — schreibt jede Pause mit, wartet nie."""
    import pipeline.verify_jobs as verify_jobs

    notiert = []
    monkeypatch.setattr(verify_jobs, "_schlafen", notiert.append)
    return notiert


@pytest.fixture
def netz(monkeypatch):
    """Ersetzt `httpx.Client` durch einen echten Client mit MockTransport. Der Test gibt eine
    Funktion `request -> Response` mit; mitgezählt werden alle Anfragen (URL-Strings)."""
    def einrichten(handler):
        aufrufe = []

        def mit_zaehler(request):
            aufrufe.append(str(request.url))
            return handler(request)

        def fabrik(**kw):
            return _ECHTER_CLIENT(transport=httpx.MockTransport(mit_zaehler), **kw)

        monkeypatch.setattr(httpx, "Client", fabrik)
        return aufrufe

    return einrichten


def _immer(antwort):
    return lambda request: antwort


def _wirft(fehler_klasse, text="simuliert"):
    def handler(request):
        raise fehler_klasse(text, request=request)

    return handler


# ── Marker: deutsche Fassung ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("marker,satz", [
    ("keine bewerbungen mehr angenommen", _MARKER_DE),
    ("nimmt keine bewerbungen mehr entgegen", "Das Unternehmen nimmt keine Bewerbungen mehr entgegen."),
])
def test_neue_marker_machen_eine_noch_sichtbare_anzeige_abgelaufen(pausen, netz, marker, satz):
    from pipeline import verify_jobs

    seite = _OFFEN.replace("</body>", f"<p>{satz}</p></body>")
    aufrufe = netz(_immer(_antwort(200, seite)))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL)

    assert erg["befund"] == "ABGELAUFEN", erg
    assert f"Seitentext: '{marker}'" in erg["beleg"]
    assert erg["versuche"] == 1
    assert len(aufrufe) == 1
    assert "anzeigentext" not in erg                  # ohne return_text nie Text


def test_beide_marker_stehen_in_der_liste():
    from pipeline import verify_jobs

    assert "keine bewerbungen mehr angenommen" in verify_jobs.BESETZT_TEXT_MARKERS
    assert "nimmt keine bewerbungen mehr entgegen" in verify_jobs.BESETZT_TEXT_MARKERS


def test_offene_anzeige_mit_dem_wort_bewerbungen_bleibt_ok(pausen, netz):
    """Gegenprobe zur Falsch-Erkennung: „Bewerbungen" allein ist kein Marker."""
    from pipeline import verify_jobs

    netz(_immer(_antwort(200, _OFFEN)))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL, return_text=True)

    assert erg["befund"] == "OK"
    assert "Kundenerfolg verantworten" in erg["anzeigentext"]


# ── Text bei geschlossenem Portal ───────────────────────────────────────────────────────────
def test_abgelaufen_durch_text_marker_liefert_text_bei_passendem_titel_und_firma(pausen, netz):
    from pipeline import verify_jobs

    netz(_immer(_antwort(200, _GESCHLOSSEN)))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL, return_text=True)

    assert erg["befund"] == "ABGELAUFEN"                      # Befund und Beleg bleiben
    assert erg["beleg"].startswith("Seitentext: 'keine bewerbungen mehr angenommen'")
    assert "Kundenerfolg verantworten" in erg["anzeigentext"]
    assert len(erg["anzeigentext"]) <= 20000


def test_englischer_marker_liefert_ebenfalls_text(pausen, netz):
    """Die Lücke gab es mit dem englischen Marker schon vor dem deutschen."""
    from pipeline import verify_jobs

    seite = _OFFEN.replace("</body>", "<p>This job: no longer accepting applications</p></body>")
    netz(_immer(_antwort(200, seite)))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL, return_text=True)

    assert erg["befund"] == "ABGELAUFEN"
    assert "no longer accepting applications" in erg["beleg"]
    assert "Kundenerfolg verantworten" in erg["anzeigentext"]


def test_ohne_return_text_gibt_es_nie_text(pausen, netz):
    from pipeline import verify_jobs

    netz(_immer(_antwort(200, _GESCHLOSSEN)))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL)

    assert erg["befund"] == "ABGELAUFEN"
    assert "anzeigentext" not in erg


def test_ohne_passenden_titel_kein_text(pausen, netz):
    """Titel zu weniger als 60 % auf der Seite (hier 1 von 3 Wörtern): Seite ist nicht die Anzeige."""
    from pipeline import verify_jobs

    seite = f"<html><body><p>Beispiel GmbH. Head of Marketing.</p><p>{_MARKER_DE}</p></body></html>"
    netz(_immer(_antwort(200, seite)))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL, return_text=True)

    assert erg["befund"] == "ABGELAUFEN"
    assert "anzeigentext" not in erg


def test_titel_ab_60_prozent_reicht_fuer_den_text(pausen, netz):
    """Zwei von drei Titelwörtern = 67 % ≥ 60 %."""
    from pipeline import verify_jobs

    seite = f"<html><body><p>Beispiel GmbH. Head Customer.</p><p>{_MARKER_DE}</p></body></html>"
    netz(_immer(_antwort(200, seite)))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL, return_text=True)

    assert erg["befund"] == "ABGELAUFEN"
    assert "Head Customer" in erg["anzeigentext"]


def test_ohne_firma_im_text_kein_text(pausen, netz):
    from pipeline import verify_jobs

    seite = (f"<html><body><p>Head of Customer Success, Kundenerfolg verantworten.</p>"
             f"<p>{_MARKER_DE}</p></body></html>")
    netz(_immer(_antwort(200, seite)))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL, return_text=True)

    assert erg["befund"] == "ABGELAUFEN"
    assert "anzeigentext" not in erg


def test_text_ist_der_anzeigen_kern_nicht_die_seiten_chrome(pausen, netz):
    """Der Marker steht bei LinkedIn AUSSERHALB des Beschreibungs-Containers; der Text aus dem
    Container (nicht der ganze Seitentext mit Marker und Boilerplate) kommt zurück."""
    from pipeline import verify_jobs

    kern = ("<p>Aufgaben:</p><ul><li>Kundenerfolg verantworten und das Team führen</li>"
            "<li>Strategische Kundenbeziehungen aufbauen und Verlängerungen sichern</li></ul>"
            "<p>Profil: Erfahrung in der Leitung von Customer-Success-Teams, Kenntnisse in "
            "Beratung, Projektsteuerung und Kundenkommunikation auf Management-Ebene. "
            "Sie arbeiten eng mit Vertrieb, Produkt und Support zusammen und verantworten "
            "die Kennzahlen Ihres Bereichs gegenüber der Geschäftsführung.</p>")
    seite = ('<html><body><p>LinkedIn nimmt den Schutz Ihrer Privatsphäre ernst</p>'
             '<h1>Head of Customer Success</h1><p>Beispiel GmbH</p>'
             f'<p>{_MARKER_DE}</p>'
             f'<div class="show-more-less-html__markup relative">{kern}</div>'
             '<p>Ähnliche Jobs</p></body></html>')
    netz(_immer(_antwort(200, seite)))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL, return_text=True)

    assert erg["befund"] == "ABGELAUFEN"
    assert "Strategische Kundenbeziehungen" in erg["anzeigentext"]
    assert "Privatsphäre" not in erg["anzeigentext"]
    assert "Ähnliche Jobs" not in erg["anzeigentext"]
    assert _MARKER_DE not in erg["anzeigentext"]


def test_umleitung_expired_jd_redirect_liefert_nie_text(pausen, netz):
    """LinkedIn leitet geschlossene Anzeigen auf eine Seite mit `expired_jd_redirect` um. Selbst
    wenn die Zielseite Titel und Firma nennt: URL-Marker → ABGELAUFEN ohne Text."""
    from pipeline import verify_jobs

    ziel = "https://www.linkedin.com/jobs/search/?trk=expired_jd_redirect"

    def handler(request):
        if str(request.url) == _URL:
            return httpx.Response(302, headers={"Location": ziel})
        return _antwort(200, _GESCHLOSSEN)

    aufrufe = netz(handler)
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL, return_text=True)

    assert erg["befund"] == "ABGELAUFEN"
    assert erg["beleg"] == "finale URL enthält 'expired_jd_redirect'"
    assert erg["final_url"] == ziel
    assert "anzeigentext" not in erg
    assert aufrufe == [_URL, ziel]


def test_check_nimmt_den_text_einer_geschlossenen_anzeige_in_die_texte_datei(tmp_path, pausen, netz):
    """`check()` ruft mit `return_text=True` ab und sammelt Texte in `<name>_texte.json`; die
    `_verify.json` bleibt ohne Text."""
    from pipeline import verify_jobs

    netz(_immer(_antwort(200, _GESCHLOSSEN)))
    pfad = tmp_path / "r.json"
    pfad.write_text(json.dumps([{"company": _FIRMA, "title": _TITEL, "url": _URL}]), encoding="utf-8")

    erg = verify_jobs.check(str(pfad))

    assert erg["ABGELAUFEN"] == 1
    ausgabe = json.loads((tmp_path / "r_verify.json").read_text(encoding="utf-8"))
    assert "anzeigentext" not in ausgabe[0]["pruefung"]
    texte = json.loads((tmp_path / "r_texte.json").read_text(encoding="utf-8"))
    assert "Kundenerfolg verantworten" in texte[_URL]


# ── Ausnahmen: Portal antwortet nicht (NICHT_PRUEFBAR) vs. Verbindung scheitert (TOT) ───────
def test_read_timeout_ist_nicht_pruefbar_mit_beleg(pausen, netz):
    from pipeline import verify_jobs

    aufrufe = netz(_wirft(httpx.ReadTimeout))
    erg = verify_jobs.check_url("https://www.stepstone.de/stellenangebote--Beispiel-12345678-inline.html",
                                _FIRMA, _TITEL, return_text=True)

    assert erg == {"befund": "NICHT_PRUEFBAR", "http_status": None, "final_url": None,
                   "beleg": "Keine Antwort nach 20 s (das Portal bremst automatische Abrufe vermutlich aus)",
                   "versuche": 1}
    assert len(aufrufe) == 1
    assert pausen == []                       # nur 429 wird wiederholt


def test_remote_protocol_error_ist_nicht_pruefbar_mit_beleg(pausen, netz):
    from pipeline import verify_jobs

    aufrufe = netz(_wirft(httpx.RemoteProtocolError, "Server disconnected without sending a response."))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL)

    assert erg == {"befund": "NICHT_PRUEFBAR", "http_status": None, "final_url": None,
                   "beleg": "Verbindung ohne Antwort beendet (das Portal blockiert automatische Abrufe vermutlich)",
                   "versuche": 1}
    assert len(aufrufe) == 1
    assert pausen == []


def test_verbindung_nicht_zustande_gekommen_bleibt_tot(pausen, netz):
    from pipeline import verify_jobs

    netz(_wirft(httpx.ConnectError, "kein Netz"))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL)

    assert erg["befund"] == "TOT"
    assert erg["beleg"] == "Netzfehler: ConnectError"
    assert erg["http_status"] is None
    assert erg["versuche"] == 1


@pytest.mark.parametrize("fehler", [httpx.ConnectTimeout, httpx.WriteTimeout, httpx.PoolTimeout])
def test_uebrige_zeitueberschreitungen_bleiben_tot(pausen, netz, fehler):
    from pipeline import verify_jobs

    netz(_wirft(fehler, "zu langsam"))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL)

    assert erg["befund"] == "TOT"
    assert erg["beleg"] == "Timeout nach 20 s"
    assert erg["versuche"] == 1


def test_read_timeout_nach_429_zaehlt_die_versuche(pausen, netz):
    """Erst gedrosselt, im zweiten Versuch keine Antwort: NICHT_PRUEFBAR, `versuche` sagt, wie weit es kam."""
    from pipeline import verify_jobs

    def handler(request):
        if len(pausen) == 0:
            return _antwort(429)
        raise httpx.ReadTimeout("keine Antwort", request=request)

    netz(handler)
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL)

    assert erg["befund"] == "NICHT_PRUEFBAR"
    assert erg["http_status"] is None
    assert erg["beleg"].startswith("Keine Antwort nach 20 s")
    assert erg["versuche"] == 2
    assert pausen == [3]


def test_stapel_wiederholt_read_timeout_nicht(tmp_path, pausen, netz):
    """Ein Portal, das nicht antwortet, ist keine Drosselung: keine weitere Runde, kein `rate_limit_offen`."""
    from pipeline import verify_jobs

    stepstone = "https://www.stepstone.de/stellenangebote--Beispiel-12345678-inline.html"
    pfad = tmp_path / "r.json"
    pfad.write_text(json.dumps([{"company": _FIRMA, "title": _TITEL, "url": stepstone}]), encoding="utf-8")
    aufrufe = netz(_wirft(httpx.ReadTimeout))

    erg = verify_jobs.check(str(pfad))

    assert aufrufe == [stepstone]
    assert pausen == []
    assert erg["NICHT_PRUEFBAR"] == 1
    assert erg["wiederholt"] == 0 and erg["rate_limit_offen"] == 0
    ausgabe = json.loads((tmp_path / "r_verify.json").read_text(encoding="utf-8"))
    assert ausgabe[0]["pruefung"]["befund"] == "NICHT_PRUEFBAR"
    assert ausgabe[0]["pruefung"]["versuche"] == 1


# ── portal_status(): reine Funktion ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("pr,erwartet", [
    ({"befund": "OK", "http_status": 200}, "offen"),
    ({"befund": "ABGELAUFEN", "http_status": 200}, "geschlossen"),
    ({"befund": "ABGELAUFEN", "http_status": 429}, "geschlossen"),      # Umleitung trotz 429
    ({"befund": "UMGELEITET_GENERISCH", "http_status": 200}, "geschlossen"),
    ({"befund": "TOT", "http_status": 404}, "geschlossen"),
    ({"befund": "TOT", "http_status": 410}, "geschlossen"),
    ({"befund": "TOT", "http_status": None}, "unklar"),                 # Netzfehler sagt nichts
    ({"befund": "TOT", "http_status": 500}, "unklar"),
    ({"befund": "NICHT_PRUEFBAR", "http_status": None}, "unklar"),      # ReadTimeout & Co.
    ({"befund": "NICHT_PRUEFBAR", "http_status": 429}, "unklar"),
    ({"befund": "NICHT_PRUEFBAR", "http_status": 403}, "unklar"),
    ({"befund": "LOGIN_WALL", "http_status": 200}, "unklar"),
    ({"befund": "INHALT_UNKLAR", "http_status": 200}, "unklar"),
    ({"befund": "KEINE_URL", "http_status": None}, "unklar"),
    ({"befund": "UNBEKANNT"}, "unklar"),
    ({}, "unklar"),
])
def test_portal_status_je_befund(pr, erwartet):
    from pipeline import verify_jobs

    vorher = dict(pr)
    assert verify_jobs.portal_status(pr) == erwartet
    assert pr == vorher                                   # rein: ändert das Ergebnis nicht


@pytest.mark.parametrize("handler,erwartet", [
    (_immer(_antwort(200, _OFFEN)), "offen"),
    (_immer(_antwort(200, _GESCHLOSSEN)), "geschlossen"),
    (_immer(_antwort(404)), "geschlossen"),
    (_immer(_antwort(410)), "geschlossen"),
    (_immer(_antwort(403)), "unklar"),
    (_immer(_antwort(200, "<p>Sign in to view this job. Join now to see.</p>")), "unklar"),
    (_wirft(httpx.ReadTimeout), "unklar"),
    (_wirft(httpx.RemoteProtocolError), "unklar"),
    (_wirft(httpx.ConnectError), "unklar"),
])
def test_portal_status_auf_echten_abrufergebnissen(pausen, netz, handler, erwartet):
    from pipeline import verify_jobs

    netz(handler)
    assert verify_jobs.portal_status(verify_jobs.check_url(_URL, _FIRMA, _TITEL)) == erwartet


# ── CLI `portal`: nur lesend, Test-DB (conftest legt sie unter tmp an) ──────────────────────
_FELDER = {"job_id", "url", "portal", "befund", "beleg", "http_status", "versuche"}


def _neuer_job(session, status, nr, url, geloescht=False):
    from app.models import Job

    job = Job(company_name=_FIRMA, title=_TITEL, url=url, status=status,
              dedup_key=f"{status}|{nr}",
              deleted_at="2026-10-01T08:00:00" if geloescht else None)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job.id


def _db_abzug():
    """Der ganze Inhalt der Test-DB als Text (alle Tabellen) — Vergleich vorher/nachher."""
    import sqlite3

    from app.db import DB_PATH

    con = sqlite3.connect(str(DB_PATH))
    try:
        return "\n".join(con.iterdump())
    finally:
        con.close()


def _portal_main(monkeypatch, capsys, *ids):
    """Ruft die Kommandozeile `portal <ids>` auf und gibt das geparste JSON von stdout zurück."""
    from pipeline import verify_jobs

    monkeypatch.setattr(sys, "argv", ["verify_jobs", "portal", *[str(i) for i in ids]])
    verify_jobs.main()                          # kein SystemExit = Exit-Code 0
    return json.loads(capsys.readouterr().out)


def _seiten(tabelle):
    """Handler je Adresse: `tabelle[url]` = Folge von Antworten (die letzte bleibt stehen)."""
    zaehler = {}

    def handler(request):
        url = str(request.url)
        folge = tabelle[url]
        i = zaehler[url] = zaehler.get(url, 0) + 1
        return folge[min(i, len(folge)) - 1]

    return handler


def test_cli_portal_zwei_stellen_plus_unbekannte_id(session, pausen, netz, monkeypatch, capsys, tmp_path):
    status = f"P276-{uuid.uuid4().hex[:8]}"
    url_zu = f"https://www.linkedin.com/jobs/view/{status}-1/"
    url_auf = f"https://www.linkedin.com/jobs/view/{status}-2/"
    id_zu = _neuer_job(session, status, 1, url_zu)
    id_auf = _neuer_job(session, status, 2, url_auf)
    unbekannt = id_auf + 100000
    aufrufe = netz(_seiten({url_zu: [_antwort(200, _GESCHLOSSEN)], url_auf: [_antwort(200, _OFFEN)]}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("pipeline.verify_jobs.PROJECT_ROOT", tmp_path)
    vorher = _db_abzug()

    out = _portal_main(monkeypatch, capsys, id_auf, unbekannt, id_zu)

    # Reihenfolge wie übergeben, genau die vereinbarten Felder
    assert [e["job_id"] for e in out] == [id_auf, unbekannt, id_zu]
    assert all(set(e) == _FELDER for e in out)
    auf, fehlt, zu = out
    assert (auf["url"], auf["portal"], auf["befund"], auf["http_status"], auf["versuche"]) == \
        (url_auf, "offen", "OK", 200, 1)
    assert (zu["url"], zu["portal"], zu["befund"], zu["http_status"], zu["versuche"]) == \
        (url_zu, "geschlossen", "ABGELAUFEN", 200, 1)
    assert "keine bewerbungen mehr angenommen" in zu["beleg"]
    # unbekannte ID: ohne Abruf, ehrlich als „unklar" gemeldet
    assert fehlt == {"job_id": unbekannt, "url": None, "portal": "unklar", "befund": "UNBEKANNT",
                     "beleg": "Stelle nicht gefunden", "http_status": None, "versuche": 0}
    assert sorted(aufrufe) == sorted([url_zu, url_auf])      # nur die beiden Stellen, je einmal
    assert pausen == [0.5]                                   # Abstand zwischen zwei Adressen
    # nur lesend: Datenbank unverändert, keine Datei geschrieben
    assert _db_abzug() == vorher
    assert list(tmp_path.iterdir()) == []


def test_cli_portal_geloeschte_stelle_ist_unbekannt_ohne_abruf(session, pausen, netz, monkeypatch, capsys):
    status = f"P276-{uuid.uuid4().hex[:8]}"
    url = f"https://www.linkedin.com/jobs/view/{status}-1/"
    jid = _neuer_job(session, status, 1, url, geloescht=True)
    aufrufe = netz(_immer(_antwort(200)))

    out = _portal_main(monkeypatch, capsys, jid)

    assert out == [{"job_id": jid, "url": None, "portal": "unklar", "befund": "UNBEKANNT",
                    "beleg": "Stelle nicht gefunden", "http_status": None, "versuche": 0}]
    assert aufrufe == []


def test_cli_portal_doppelte_id_wird_einmal_abgerufen(session, pausen, netz, monkeypatch, capsys):
    status = f"P276-{uuid.uuid4().hex[:8]}"
    url = f"https://www.linkedin.com/jobs/view/{status}-1/"
    jid = _neuer_job(session, status, 1, url)
    aufrufe = netz(_immer(_antwort(200)))

    out = _portal_main(monkeypatch, capsys, jid, jid)

    assert [e["job_id"] for e in out] == [jid]
    assert aufrufe == [url]


def test_cli_portal_429_in_runde_1_und_erfolg_in_runde_2(session, pausen, netz, monkeypatch, capsys):
    status = f"P276-{uuid.uuid4().hex[:8]}"
    url_a = f"https://www.linkedin.com/jobs/view/{status}-1/"
    url_b = f"https://www.linkedin.com/jobs/view/{status}-2/"
    id_a = _neuer_job(session, status, 1, url_a)
    id_b = _neuer_job(session, status, 2, url_b)
    aufrufe = netz(_seiten({url_a: [_antwort(429), _antwort(200, _OFFEN)], url_b: [_antwort(200, _GESCHLOSSEN)]}))
    vorher = _db_abzug()

    out = _portal_main(monkeypatch, capsys, id_a, id_b)

    # Runde 1: beide, Runde 2: nur die gedrosselte
    assert aufrufe == [url_a, url_b, url_a]
    assert pausen == [0.5, 5]
    a, b = out
    assert (a["portal"], a["befund"], a["http_status"], a["versuche"]) == ("offen", "OK", 200, 2)
    assert (b["portal"], b["befund"], b["versuche"]) == ("geschlossen", "ABGELAUFEN", 1)
    assert _db_abzug() == vorher


def test_cli_portal_dauerhaft_gedrosselt_ist_unklar(session, pausen, netz, monkeypatch, capsys):
    status = f"P276-{uuid.uuid4().hex[:8]}"
    url = f"https://www.linkedin.com/jobs/view/{status}-1/"
    jid = _neuer_job(session, status, 1, url)
    aufrufe = netz(_immer(_antwort(429)))

    (eintrag,) = _portal_main(monkeypatch, capsys, jid)

    assert len(aufrufe) == 4
    assert pausen == [5, 10, 20]
    assert eintrag["portal"] == "unklar"
    assert eintrag["befund"] == "NICHT_PRUEFBAR"
    assert eintrag["http_status"] == 429
    assert eintrag["versuche"] == 4
    assert eintrag["beleg"] == "HTTP 429 nach 4 Versuchen (Rate-Limit)"


def test_cli_portal_stepstone_ohne_antwort_ist_unklar_mit_bot_schutz_beleg(session, pausen, netz,
                                                                          monkeypatch, capsys):
    status = f"P276-{uuid.uuid4().hex[:8]}"
    url = "https://www.stepstone.de/stellenangebote--Beispiel-12345678-inline.html"
    jid = _neuer_job(session, status, 1, url)
    aufrufe = netz(_wirft(httpx.ReadTimeout))

    (eintrag,) = _portal_main(monkeypatch, capsys, jid)

    assert aufrufe == [url]                                 # nicht wiederholt
    assert pausen == []
    assert eintrag["portal"] == "unklar"
    assert eintrag["befund"] == "NICHT_PRUEFBAR"
    assert eintrag["http_status"] is None
    assert "bremst automatische Abrufe" in eintrag["beleg"]
    assert eintrag["versuche"] == 1


def test_cli_portal_404_ist_geschlossen_und_stelle_ohne_url_unklar(session, pausen, netz, monkeypatch, capsys):
    status = f"P276-{uuid.uuid4().hex[:8]}"
    url = f"https://www.linkedin.com/jobs/view/{status}-1/"
    id_weg = _neuer_job(session, status, 1, url)
    id_ohne = _neuer_job(session, status, 2, None)
    aufrufe = netz(_immer(_antwort(404)))

    weg, ohne = _portal_main(monkeypatch, capsys, id_weg, id_ohne)

    assert aufrufe == [url]                                 # ohne URL kein Abruf
    assert (weg["portal"], weg["befund"], weg["http_status"]) == ("geschlossen", "TOT", 404)
    assert (ohne["portal"], ohne["befund"], ohne["url"], ohne["versuche"]) == ("unklar", "KEINE_URL", None, 0)
    assert all(set(e) == _FELDER for e in (weg, ohne))


def test_cli_portal_beleg_ist_auf_200_zeichen_begrenzt(session, pausen, netz, monkeypatch, capsys):
    status = f"P276-{uuid.uuid4().hex[:8]}"
    url = f"https://www.linkedin.com/jobs/view/{status}-1/"
    jid = _neuer_job(session, status, 1, url)
    netz(_immer(_antwort(200, _GESCHLOSSEN)))

    (eintrag,) = _portal_main(monkeypatch, capsys, jid)

    assert 0 < len(eintrag["beleg"]) <= 200


def test_cli_portal_ohne_ids_ist_ein_aufruffehler(monkeypatch, capsys):
    from pipeline import verify_jobs

    monkeypatch.setattr(sys, "argv", ["verify_jobs", "portal"])
    with pytest.raises(SystemExit) as e:
        verify_jobs.main()

    assert e.value.code == 2
    assert capsys.readouterr().out == ""
