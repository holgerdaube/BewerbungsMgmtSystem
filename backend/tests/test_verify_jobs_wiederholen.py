"""Tests für P2-75 (Anzeigentext sichern), Vertrag A: `verify_jobs` wiederholt bei HTTP 429.

Anlass: LinkedIn drosselt Abrufe je Anfrage (HTTP 429, „zu viele Anfragen"). Früher wurde so
eine Anzeige als „nicht abrufbar" gespeichert, der Snapshot blieb ohne Anzeigentext. Jetzt gilt:
  * `check_url()` wiederholt NUR bei 429 (Pausen 3/8/20 s, `Retry-After` ≤ 30 s ersetzt die Pause),
  * `check()` und `bestand()` holen gedrosselte Adressen in bis zu drei weiteren Runden nach
    (Pausen 5/10/20 s), Ausgabereihenfolge und `_verify.json`-Format bleiben, neu ist nur
    `pruefung.versuche` und in der Zusammenfassung `wiederholt` / `rate_limit_offen`.

Netz nur über `httpx.MockTransport` (der echte `httpx.Client` bekommt den Transport), Pausen
laufen über `verify_jobs._schlafen` und werden hier nur mitgeschrieben — es wird nie echt
gewartet. Konvention conftest.py: keine app.*/pipeline.*-Importe auf Modulebene."""
import json

import httpx
import pytest

_URL = "https://www.linkedin.com/jobs/view/1234567890/"
_FIRMA = "Beispiel GmbH"
_TITEL = "Head of Customer Success"
_SEITE = ("<html><body><p>Beispiel GmbH sucht: Head of Customer Success.</p>"
          "<p>Aufgaben: Kundenerfolg verantworten, Team führen.</p></body></html>")

# Die Fixtures unten ersetzen `httpx.Client`; den echten Client merken wir uns hier, damit die
# Fabrik ihn mit dem MockTransport bauen kann (kein Zugriff auf die Ersetzung selbst).
_ECHTER_CLIENT = httpx.Client


def _antwort(status, text=_SEITE, headers=None):
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


def _folge(*antworten):
    """Handler, der die Antworten der Reihe nach liefert (die letzte bleibt stehen)."""
    stand = {"i": 0}

    def handler(request):
        a = antworten[min(stand["i"], len(antworten) - 1)]
        stand["i"] += 1
        return a() if callable(a) else a

    return handler


# ── check_url(): Einzelabruf mit direkter Wiederholung ──────────────────────────────────────
def test_429_dann_200_ist_ok_mit_zwei_versuchen(pausen, netz):
    from pipeline import verify_jobs

    aufrufe = netz(_folge(_antwort(429), _antwort(200)))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL, return_text=True)

    assert erg["befund"] == "OK", erg
    assert erg["versuche"] == 2
    assert pausen == [3]
    assert len(aufrufe) == 2
    assert "Kundenerfolg verantworten" in erg["anzeigentext"]


def test_viermal_429_ist_nicht_pruefbar_mit_beleg_und_drei_pausen(pausen, netz):
    from pipeline import verify_jobs

    aufrufe = netz(_folge(_antwort(429)))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL, return_text=True)

    assert erg["befund"] == "NICHT_PRUEFBAR"
    assert erg["http_status"] == 429
    assert erg["beleg"] == "HTTP 429 nach 4 Versuchen (Rate-Limit)"
    assert erg["versuche"] == 4
    assert pausen == [3, 8, 20]
    assert len(aufrufe) == 4
    assert "anzeigentext" not in erg


def test_retry_after_ersetzt_die_pause(pausen, netz):
    from pipeline import verify_jobs

    netz(_folge(_antwort(429, headers={"Retry-After": "2"}), _antwort(200)))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL)

    assert erg["befund"] == "OK"
    assert pausen == [2]


def test_retry_after_ueber_30_sekunden_wird_ignoriert(pausen, netz):
    """120 s sprengen das Zeitlimit der Skills — dann gilt die Liste (3 s)."""
    from pipeline import verify_jobs

    netz(_folge(_antwort(429, headers={"Retry-After": "120"}), _antwort(200)))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL)

    assert erg["befund"] == "OK"
    assert pausen == [3]


@pytest.mark.parametrize("wert", ["Wed, 21 Oct 2026 07:28:00 GMT", "2.5", "abc", "-5", ""])
def test_retry_after_ohne_ganze_sekunden_faellt_auf_die_liste_zurueck(pausen, netz, wert):
    from pipeline import verify_jobs

    netz(_folge(_antwort(429, headers={"Retry-After": wert}), _antwort(200)))
    verify_jobs.check_url(_URL, _FIRMA, _TITEL)

    assert pausen == [3]


def test_retry_after_gilt_je_pause_einzeln(pausen, netz):
    """Mal Retry-After, mal Liste: die zweite Pause ist die ZWEITE der Liste (8), nicht die erste."""
    from pipeline import verify_jobs

    netz(_folge(_antwort(429, headers={"Retry-After": "1"}), _antwort(429), _antwort(200)))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL)

    assert erg["befund"] == "OK"
    assert erg["versuche"] == 3
    assert pausen == [1, 8]


@pytest.mark.parametrize("status,befund", [(403, "NICHT_PRUEFBAR"), (404, "TOT"), (410, "TOT"),
                                           (500, "NICHT_PRUEFBAR")])
def test_andere_statuscodes_werden_nicht_wiederholt(pausen, netz, status, befund):
    from pipeline import verify_jobs

    aufrufe = netz(_folge(_antwort(status)))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL)

    assert erg["befund"] == befund
    assert erg["versuche"] == 1
    assert len(aufrufe) == 1
    assert pausen == []


def test_403_behaelt_den_alten_beleg(pausen, netz):
    from pipeline import verify_jobs

    netz(_folge(_antwort(403)))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL)

    assert erg["beleg"] == "HTTP 403 (Bot-Block/Rate-Limit)"


def test_login_wall_und_abgelaufen_werden_nicht_wiederholt(pausen, netz):
    from pipeline import verify_jobs

    aufrufe = netz(_folge(_antwort(200, text="<p>Sign in to view this job. Join now to see.</p>")))
    assert verify_jobs.check_url(_URL, _FIRMA, _TITEL)["befund"] == "LOGIN_WALL"
    assert len(aufrufe) == 1

    aufrufe = netz(_folge(_antwort(200, text="<p>Beispiel GmbH: no longer accepting applications</p>")))
    assert verify_jobs.check_url(_URL, _FIRMA, _TITEL)["befund"] == "ABGELAUFEN"
    assert len(aufrufe) == 1
    assert pausen == []


def test_wiederholen_false_ist_genau_ein_versuch(pausen, netz):
    from pipeline import verify_jobs

    aufrufe = netz(_folge(_antwort(429)))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL, wiederholen=False)

    assert erg["befund"] == "NICHT_PRUEFBAR"
    assert erg["versuche"] == 1
    assert erg["beleg"] == "HTTP 429 (Bot-Block/Rate-Limit)"     # Altwortlaut bei einem Versuch
    assert len(aufrufe) == 1
    assert pausen == []


def test_erfolg_beim_ersten_versuch_hat_versuche_1(pausen, netz):
    from pipeline import verify_jobs

    netz(_folge(_antwort(200)))
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL)

    assert erg["befund"] == "OK"
    assert erg["versuche"] == 1
    assert pausen == []


def test_ohne_url_hat_kein_versuche_feld(pausen, netz):
    from pipeline import verify_jobs

    aufrufe = netz(_folge(_antwort(200)))
    erg = verify_jobs.check_url("", _FIRMA, _TITEL)

    assert erg["befund"] == "KEINE_URL"
    assert "versuche" not in erg
    assert aufrufe == []


def test_netzfehler_nach_429_zaehlt_die_versuche(pausen, netz):
    """Timeout im zweiten Versuch → TOT wie bisher, `versuche` sagt, wie weit es kam."""
    from pipeline import verify_jobs

    def handler(request):
        if len(pausen) == 0:
            return _antwort(429)
        raise httpx.ConnectTimeout("zu langsam", request=request)

    netz(handler)
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL)

    assert erg["befund"] == "TOT"
    assert erg["beleg"] == "Timeout nach 20 s"
    assert erg["versuche"] == 2


def test_netzfehler_beim_ersten_versuch_hat_versuche_1(pausen, netz):
    from pipeline import verify_jobs

    def handler(request):
        raise httpx.ConnectError("kein Netz", request=request)

    netz(handler)
    erg = verify_jobs.check_url(_URL, _FIRMA, _TITEL)

    assert erg["befund"] == "TOT"
    assert erg["versuche"] == 1


# ── check(): Stapel in Runden ───────────────────────────────────────────────────────────────
def _records(tmp_path, urls):
    pfad = tmp_path / "mj_records.json"
    recs = [{"company": _FIRMA, "title": _TITEL, "url": u, "notiz": f"r{i}"}
            for i, u in enumerate(urls)]
    pfad.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    return pfad


def _gedrosselt_bis(tabelle):
    """Handler je Adresse: `tabelle[url]` = Zahl der 429, bevor 200 kommt (None = immer 429)."""
    zaehler = {}

    def handler(request):
        url = str(request.url)
        n = zaehler[url] = zaehler.get(url, 0) + 1
        gedrosselt = tabelle.get(url, 0)
        if gedrosselt is None or n <= gedrosselt:
            return _antwort(429)
        return _antwort(200, text=_SEITE + f"<p>Text von {url}</p>")

    return handler


def test_check_holt_gedrosselte_adresse_in_runde_2_nach(tmp_path, pausen, netz):
    from pipeline import verify_jobs

    urls = [f"https://www.linkedin.com/jobs/view/{n}/" for n in (1111, 2222, 3333)]
    pfad = _records(tmp_path, urls)
    aufrufe = netz(_gedrosselt_bis({urls[1]: 1}))

    erg = verify_jobs.check(str(pfad))

    # Anfragen: Runde 1 alle drei, Runde 2 nur die gedrosselte
    assert aufrufe == urls + [urls[1]]
    # Pausen: 0,5 s zwischen den Adressen der Runde 1, dann 5 s vor Runde 2
    assert pausen == [0.5, 0.5, 5]
    assert [p for p in pausen if p != 0.5] == [5]
    assert erg["geprueft"] == 3
    assert erg["OK"] == 3
    assert erg["wiederholt"] == 1
    assert erg["rate_limit_offen"] == 0

    ausgabe = json.loads((tmp_path / "mj_records_verify.json").read_text(encoding="utf-8"))
    # Reihenfolge der Records bleibt, Felder der Records bleiben
    assert [r["url"] for r in ausgabe] == urls
    assert [r["notiz"] for r in ausgabe] == ["r0", "r1", "r2"]
    assert [r["pruefung"]["versuche"] for r in ausgabe] == [1, 2, 1]
    assert all(r["pruefung"]["befund"] == "OK" for r in ausgabe)
    # der Anzeigentext gehört nur in _texte.json, auch der aus der späteren Runde
    assert all("anzeigentext" not in r["pruefung"] for r in ausgabe)
    texte = json.loads((tmp_path / "mj_records_texte.json").read_text(encoding="utf-8"))
    assert set(texte) == set(urls)
    assert f"Text von {urls[1]}" in texte[urls[1]]
    assert erg["texte"] == 3


def test_check_ohne_drosselung_wartet_nur_den_abstand(tmp_path, pausen, netz):
    from pipeline import verify_jobs

    urls = [f"https://www.linkedin.com/jobs/view/{n}/" for n in (1, 2, 3)]
    aufrufe = netz(_gedrosselt_bis({}))

    erg = verify_jobs.check(str(_records(tmp_path, urls)))

    assert aufrufe == urls
    assert pausen == [0.5, 0.5]           # kein 0,5-s-Nachlauf nach der letzten Adresse
    assert erg["wiederholt"] == 0
    assert erg["rate_limit_offen"] == 0


def test_check_dauerhaft_gedrosselt_nach_vier_runden_offen(tmp_path, pausen, netz):
    from pipeline import verify_jobs

    urls = [f"https://www.linkedin.com/jobs/view/{n}/" for n in (1, 2)]
    aufrufe = netz(_gedrosselt_bis({urls[0]: None}))

    erg = verify_jobs.check(str(_records(tmp_path, urls)))

    # Adresse 1: vier Runden; Adresse 2 klappt in Runde 1 und wird nicht erneut abgerufen
    assert aufrufe.count(urls[0]) == 4
    assert aufrufe.count(urls[1]) == 1
    assert [p for p in pausen if p != 0.5] == [5, 10, 20]
    assert erg["NICHT_PRUEFBAR"] == 1 and erg["OK"] == 1
    assert erg["wiederholt"] == 1
    assert erg["rate_limit_offen"] == 1

    ausgabe = json.loads((tmp_path / "mj_records_verify.json").read_text(encoding="utf-8"))
    assert ausgabe[0]["pruefung"]["befund"] == "NICHT_PRUEFBAR"
    assert ausgabe[0]["pruefung"]["versuche"] == 4
    assert ausgabe[0]["pruefung"]["beleg"] == "HTTP 429 nach 4 Versuchen (Rate-Limit)"
    assert ausgabe[1]["pruefung"]["versuche"] == 1


def test_check_runden_nehmen_nur_die_gedrosselten_mit(tmp_path, pausen, netz):
    """Zwei Adressen gedrosselt (eine 1×, eine 2×): Runde 2 holt beide, Runde 3 nur die zweite."""
    from pipeline import verify_jobs

    urls = [f"https://www.linkedin.com/jobs/view/{n}/" for n in (10, 20, 30)]
    aufrufe = netz(_gedrosselt_bis({urls[0]: 1, urls[2]: 2}))

    erg = verify_jobs.check(str(_records(tmp_path, urls)))

    assert aufrufe == urls + [urls[0], urls[2]] + [urls[2]]
    # R1: 0,5 0,5 | 5 | R2: 0,5 | 10 | R3: (eine Adresse, kein Abstand)
    assert pausen == [0.5, 0.5, 5, 0.5, 10]
    assert erg["wiederholt"] == 2
    assert erg["rate_limit_offen"] == 0
    ausgabe = json.loads((tmp_path / "mj_records_verify.json").read_text(encoding="utf-8"))
    assert [r["pruefung"]["versuche"] for r in ausgabe] == [2, 1, 3]


def test_check_andere_befunde_loesen_keine_runde_aus(tmp_path, pausen, netz):
    """403, 404 und eine Record ohne URL kosten keine Wiederholung."""
    from pipeline import verify_jobs

    urls = ["https://example.com/a", "https://example.com/b"]
    pfad = tmp_path / "r.json"
    pfad.write_text(json.dumps([
        {"company": _FIRMA, "title": _TITEL, "url": urls[0]},
        {"company": _FIRMA, "title": _TITEL, "url": urls[1]},
        {"company": _FIRMA, "title": _TITEL},
    ]), encoding="utf-8")

    def handler(request):
        return _antwort(403 if str(request.url).endswith("/a") else 404)

    aufrufe = netz(handler)
    erg = verify_jobs.check(str(pfad))

    assert aufrufe == urls
    assert [p for p in pausen if p != 0.5] == []
    assert erg["NICHT_PRUEFBAR"] == 1 and erg["TOT"] == 1 and erg["KEINE_URL"] == 1
    assert erg["wiederholt"] == 0 and erg["rate_limit_offen"] == 0
    ausgabe = json.loads((tmp_path / "r_verify.json").read_text(encoding="utf-8"))
    assert "versuche" not in ausgabe[2]["pruefung"]       # KEINE_URL: kein Abruf


def test_check_leere_liste(tmp_path, pausen, netz):
    from pipeline import verify_jobs

    netz(_gedrosselt_bis({}))
    pfad = tmp_path / "leer.json"
    pfad.write_text("[]", encoding="utf-8")

    erg = verify_jobs.check(str(pfad))

    assert erg["geprueft"] == 0 and erg["wiederholt"] == 0 and erg["rate_limit_offen"] == 0
    assert pausen == []


# ── bestand(): gleiche Runden gegen die DB-Jobs (conftest legt die Test-DB unter tmp an) ────
def test_bestand_holt_gedrosselte_jobs_in_runden_nach(session, pausen, netz, monkeypatch, tmp_path):
    import uuid

    from app.models import Job
    from pipeline import verify_jobs

    # Die Test-DB ist sitzungsweit geteilt: ein eindeutiger Status trennt diese Jobs von allen anderen.
    status = f"P275-{uuid.uuid4().hex[:8]}"
    urls = [f"https://www.linkedin.com/jobs/view/{n}/" for n in (7001, 7002)]
    ids = []
    for i, u in enumerate(urls):
        job = Job(company_name=_FIRMA, title=_TITEL, url=u, status=status,
                  dedup_key=f"{status}|{i}")
        session.add(job)
        session.commit()
        session.refresh(job)
        ids.append(job.id)

    # Ausgabe nicht in das echte Projekt schreiben
    monkeypatch.setattr(verify_jobs, "PROJECT_ROOT", tmp_path)
    aufrufe = netz(_gedrosselt_bis({urls[0]: 1}))

    erg = verify_jobs.bestand(status)

    assert erg["geprueft"] == 2
    assert erg["OK"] == 2
    assert erg["wiederholt"] == 1
    assert erg["rate_limit_offen"] == 0
    assert aufrufe.count(urls[0]) == 2 and aufrufe.count(urls[1]) == 1
    assert [p for p in pausen if p != 0.5] == [5]
    zeilen = json.loads(next((tmp_path / "data" / "exports").glob("*URL_Check*.json"))
                        .read_text(encoding="utf-8"))
    assert [z["id"] for z in zeilen] == ids                      # Reihenfolge der Jobs bleibt
    assert {z["url"]: z["pruefung"]["versuche"] for z in zeilen} == {urls[0]: 2, urls[1]: 1}
