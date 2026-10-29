"""Tests für das Nachholen des Anzeigentexts (P2-75, Vertrag B) in `pipeline/posting_snapshot.py`:
`hat_anzeigentext()`, `render_basis(..., hinweis=)`, `anzeigentext_sichern()`, `nachholen()` und
die Kommandozeile `nachholen`.

Anlass: Eine Stelle aus einer Job-Mail bekam beim Erfassen nur einen Basis-Snapshot ohne Anzeigentext,
weil LinkedIn den Abruf gedrosselt hatte (HTTP 429). Firma-Prüfung, CV-Match und CV liefen trotzdem
durch. Jetzt holt `anzeigentext_sichern()` den Text nach; ersetzt wird der Snapshot nur bei Befund
`OK` oder (P2-76) bei `ABGELAUFEN` mit Anzeigentext, alles andere lässt die Datei bytegleich.

Dieses Modul heißt bewusst genau so: `conftest.py` ersetzt `posting_snapshot.anzeigentext_sichern`
für alle Testmodule AUSSER diesem durch eine Attrappe (Paket C, damit `create_task` in anderen
Tests nie ins Netz greift).

Isolation wie in `test_posting_snapshot_full.py`: kein app.*/pipeline.*-Import auf Modulebene
(conftest.py-Konvention), `_SNAPSHOT_DIR` je Test per `monkeypatch` auf `tmp_path`, `check_url`
IMMER ersetzt (kein echtes Netz), Pausen ersetzt.
"""
import datetime
import json
import runpy
import sys
import uuid
from pathlib import Path

import pytest

# Wortlaut aus der Spec, hier bewusst ausgeschrieben: ändert jemand die Konstanten im Modul,
# fällt das auf (Kundentexte sind Vertrag).
GRUND_429 = ("LinkedIn hat den Abruf auch nach mehreren Versuchen abgelehnt (zu viele Anfragen). "
             "Ein späterer Versuch klappt meist.")
GRUND_BLOCKIERT = "Das Portal blockiert automatische Abrufe."
GRUND_LOGIN = "Die Anzeige ist nur mit Anmeldung sichtbar."
GRUND_OFFLINE = "Die Anzeige ist nicht mehr online."
GRUND_UNKLAR = "Die abgerufene Seite passt nicht eindeutig zur Stelle."
GRUND_KEINE_URL = "Die Stelle hat keine Anzeigen-Adresse."
GRUND_NICHT_GEFUNDEN = "Stelle nicht gefunden."

ANZEIGENTEXT = ("Ihre Aufgaben:\n\nTeam von Beratern führen und Projekte verantworten.\n\n"
                "Ihr Profil:\n\nMehrjährige Erfahrung im Professional-Services-Umfeld.")


# ── Hilfen ─────────────────────────────────────────────────────────────────────────────────
def _neuer_job(session, url="auto", status=None):
    """Frischer Job mit EINDEUTIGER url/status (uuid) — die tmp-DB akkumuliert über die Sitzung
    und `Job.url` hat einen UNIQUE-Index (Muster `test_posting_snapshot_full.py`)."""
    from app.models import Job

    kennung = uuid.uuid4().hex[:8]
    status = status or f"P275Nachholen-{kennung}"
    if url == "auto":
        url = f"https://example.invalid/stelle/{kennung}"
    job = Job(company_name=f"Beispiel GmbH {kennung}", title="Musterstelle Professional Services",
              status=status, found_date=datetime.date.today().isoformat(),
              dedup_key=f"p275-nachholen|{kennung}", url=url)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def _basis(session, job, text=None):
    """Legt den Basis-Snapshot an (wie beim Erfassen) und gibt den relativen Pfad zurück."""
    from pipeline import posting_snapshot

    rel = posting_snapshot.render_basis(job, text)
    session.add(job)
    session.commit()
    session.refresh(job)
    return rel


def _datei(tmp_path, job) -> Path:
    return tmp_path / Path(job.posting_snapshot_path).name


class _Abruf:
    """Ersatz für `check_url`: merkt sich die Aufrufe und liefert ein festes Ergebnis. Ein
    `ergebnis` von `None` = der Aufruf darf gar nicht stattfinden (Test schlägt fehl)."""

    def __init__(self, ergebnis=None, fehler=None):
        self.ergebnis = ergebnis
        self.fehler = fehler
        self.aufrufe = []

    def __call__(self, url, company, title, return_text=False, **kwargs):
        self.aufrufe.append({"url": url, "company": company, "title": title,
                             "return_text": return_text, "kwargs": kwargs})
        if self.fehler is not None:
            raise self.fehler
        assert self.ergebnis is not None, "check_url darf hier nicht aufgerufen werden"
        return dict(self.ergebnis)


def _abruf_patchen(monkeypatch, ergebnis=None, fehler=None) -> _Abruf:
    from pipeline import verify_jobs

    abruf = _Abruf(ergebnis, fehler)
    monkeypatch.setattr(verify_jobs, "check_url", abruf)
    return abruf


def _ok(text=ANZEIGENTEXT, versuche=1):
    return {"befund": "OK", "http_status": 200, "final_url": "https://example.invalid/x",
            "beleg": "Titel 100% + Firma im Text", "anzeigentext": text, "versuche": versuche}


def _abgelaufen(text=ANZEIGENTEXT, versuche=1):
    """P2-76: Portal geschlossen („keine Bewerbungen mehr“), Seite aber noch sichtbar und Titel
    und Firma passen -> `check_url` liefert `ABGELAUFEN` samt Anzeigentext (`text=None` = ohne)."""
    pr = {"befund": "ABGELAUFEN", "http_status": 200, "final_url": "https://example.invalid/x",
          "beleg": "Text-Marker: keine bewerbungen mehr angenommen", "versuche": versuche}
    if text is not None:
        pr["anzeigentext"] = text
    return pr


def _joblogs(session, job):
    from sqlmodel import select
    from app.models import JobLog

    session.expire_all()
    return list(session.exec(select(JobLog).where(JobLog.job_id == job.id)).all())


# ── hat_anzeigentext ───────────────────────────────────────────────────────────────────────
def test_hat_anzeigentext_wahr_bei_basis_mit_karte(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job = _neuer_job(session)
    _basis(session, job, text=ANZEIGENTEXT)

    assert posting_snapshot.hat_anzeigentext(job) is True


def test_hat_anzeigentext_wahr_bei_vollversion_mit_volltext_block(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job = _neuer_job(session)
    _basis(session, job, text=ANZEIGENTEXT)
    posting_snapshot.render_full(job.id, {"aufgaben": ["Team führen"]}, "amber")
    session.refresh(job)

    assert "Volltext (unbereinigt)" in _datei(tmp_path, job).read_text(encoding="utf-8")
    assert posting_snapshot.hat_anzeigentext(job) is True


def test_hat_anzeigentext_wahr_bei_gruen_gegliedert_ohne_block(session, monkeypatch, tmp_path):
    """Die Firma-Prüfung hat das Original gegliedert, ein Volltext-Block blieb nicht stehen:
    Quelle grün genügt (Vertrag B, dritte Bedingung)."""
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job = _neuer_job(session)
    posting_snapshot.render_full(job.id, {"aufgaben": ["Team führen"]}, "gruen")
    session.refresh(job)

    html = _datei(tmp_path, job).read_text(encoding="utf-8")
    assert "Volltext (unbereinigt)" not in html
    assert posting_snapshot.hat_anzeigentext(job) is True


def test_hat_anzeigentext_wahr_bei_aelterem_snapshot_mit_freiem_volltext_block(session, monkeypatch, tmp_path):
    """Ältere, freihändig geschriebene Snapshots: irgendein `<details>…<pre>` zählt als Volltext
    (`_lege_volltext_kandidaten`), auch mit abweichendem `<summary>`."""
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job = _neuer_job(session)
    alt = ('<html><body><header class="head"><div class="meta"><div><p class="k">Quelle</p>'
           '<p class="v">amber — Teilquelle</p></div></div></header>'
           '<details><summary>Original-Text anzeigen</summary><pre>Alter Anzeigentext.</pre></details>'
           '</body></html>')
    (tmp_path / "alt.html").write_text(alt, encoding="utf-8")
    job.posting_snapshot_path = "data/job_postings/alt.html"
    session.add(job)
    session.commit()

    assert posting_snapshot.hat_anzeigentext(job) is True


@pytest.mark.parametrize("quelle", ["amber", "rot"])
def test_hat_anzeigentext_falsch_bei_amber_oder_rot_gegliedert_ohne_block(session, monkeypatch, tmp_path, quelle):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job = _neuer_job(session)
    posting_snapshot.render_full(job.id, {"aufgaben": ["Team führen"]}, quelle)
    session.refresh(job)

    assert posting_snapshot.hat_anzeigentext(job) is False


def test_hat_anzeigentext_falsch_bei_basis_ohne_text(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job = _neuer_job(session)
    _basis(session, job, text=None)

    assert posting_snapshot.hat_anzeigentext(job) is False


def test_hat_anzeigentext_falsch_ohne_datei(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job = _neuer_job(session)
    assert posting_snapshot.hat_anzeigentext(job) is False          # kein posting_snapshot_path

    job.posting_snapshot_path = "data/job_postings/gibt_es_nicht.html"
    assert posting_snapshot.hat_anzeigentext(job) is False          # Pfad gesetzt, Datei fehlt


def test_hat_anzeigentext_ist_reine_lesefunktion(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    abruf = _abruf_patchen(monkeypatch)                              # darf nie aufgerufen werden
    job = _neuer_job(session)
    _basis(session, job, text=None)
    vorher = _datei(tmp_path, job).read_bytes()

    posting_snapshot.hat_anzeigentext(job)

    assert _datei(tmp_path, job).read_bytes() == vorher
    assert abruf.aufrufe == []


# ── render_basis(hinweis=) ─────────────────────────────────────────────────────────────────
def test_render_basis_hinweis_landet_escaped_im_banner(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job = _neuer_job(session)
    posting_snapshot.render_basis(job, ANZEIGENTEXT, hinweis="Vermerk <b>fett</b>")

    html = _datei(tmp_path, job).read_text(encoding="utf-8")
    assert '<div class="caveat"><b>Hinweis:</b> Vermerk &lt;b&gt;fett&lt;/b&gt;</div>' in html


def test_render_basis_ohne_hinweis_hat_keinen_banner(session, monkeypatch, tmp_path):
    """Bestehende Aufrufe ändern sich nicht: ohne `hinweis` kein Banner."""
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job = _neuer_job(session)
    _basis(session, job, text=ANZEIGENTEXT)

    assert '<div class="caveat">' not in _datei(tmp_path, job).read_text(encoding="utf-8")


# ── anzeigentext_sichern: vorhanden ────────────────────────────────────────────────────────
@pytest.mark.parametrize("variante", ["basis", "voll", "gruen"])
def test_sichern_vorhanden_ruft_check_url_nicht_auf(session, monkeypatch, tmp_path, variante):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    abruf = _abruf_patchen(monkeypatch)                              # jeder Aufruf = Testfehler
    job = _neuer_job(session)
    if variante == "basis":
        _basis(session, job, text=ANZEIGENTEXT)
    elif variante == "voll":
        _basis(session, job, text=ANZEIGENTEXT)
        posting_snapshot.render_full(job.id, {"aufgaben": ["x"]}, "amber")
    else:
        posting_snapshot.render_full(job.id, {"aufgaben": ["x"]}, "gruen")
    session.refresh(job)
    vorher = _datei(tmp_path, job).read_bytes()

    erg = posting_snapshot.anzeigentext_sichern(job.id)

    assert erg["status"] == "vorhanden"
    assert erg["job_id"] == job.id
    assert erg["posting_snapshot_path"] == job.posting_snapshot_path
    assert erg["grund"] is None and erg["befund"] is None and erg["versuche"] is None
    assert abruf.aufrufe == []
    assert _datei(tmp_path, job).read_bytes() == vorher
    assert _joblogs(session, job) == []


# ── anzeigentext_sichern: nachgeholt ───────────────────────────────────────────────────────
def test_sichern_nachgeholt_ersetzt_basis_ohne_text(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    abruf = _abruf_patchen(monkeypatch, _ok(versuche=3))
    job = _neuer_job(session)
    rel_vorher = _basis(session, job, text=None)
    assert posting_snapshot.hat_anzeigentext(job) is False

    erg = posting_snapshot.anzeigentext_sichern(job.id)

    assert erg["status"] == "nachgeholt"
    assert erg["befund"] == "OK"
    assert erg["versuche"] == 3
    assert erg["grund"] is None
    # Dateiname stabil: dieselbe Datei wird ersetzt, kein „_2“
    assert erg["posting_snapshot_path"] == rel_vorher
    session.refresh(job)
    assert job.posting_snapshot_path == rel_vorher
    assert len(list(tmp_path.glob("*.html"))) == 1

    # Abruf wie in Vertrag B: mit Text, ohne eigenen `wiederholen`-Parameter
    assert len(abruf.aufrufe) == 1
    a = abruf.aufrufe[0]
    assert a["url"] == job.url and a["company"] == job.company_name and a["title"] == job.title
    assert a["return_text"] is True
    assert a["kwargs"] == {}

    html = _datei(tmp_path, job).read_text(encoding="utf-8")
    assert '<h2 class="sec">Anzeigentext (automatisch extrahiert, unbereinigt)</h2>' in html
    assert "Team von Beratern führen und Projekte verantworten." in html
    heute = datetime.date.today().strftime("%d.%m.%Y")
    assert (f'<div class="caveat"><b>Hinweis:</b> Anzeigentext am {heute} nachgeholt. '
            f'Gegliedert wird er bei der nächsten Firma-Prüfung.</div>') in html
    assert posting_snapshot.hat_anzeigentext(job) is True
    # Badge ehrlich: jetzt liegt ein Text vor -> grün (und nur deshalb)
    assert posting_snapshot._erkenne_alte_quelle(html) == "gruen"

    logs = _joblogs(session, job)
    assert len(logs) == 1
    assert logs[0].art == "auto"
    assert logs[0].eintrag == "Anzeigentext der Anzeige nachgeholt."


def test_sichern_nachgeholt_ist_beim_zweiten_aufruf_vorhanden(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    abruf = _abruf_patchen(monkeypatch, _ok())
    job = _neuer_job(session)
    _basis(session, job, text=None)

    assert posting_snapshot.anzeigentext_sichern(job.id)["status"] == "nachgeholt"
    assert posting_snapshot.anzeigentext_sichern(job.id)["status"] == "vorhanden"

    assert len(abruf.aufrufe) == 1                                    # der zweite Aufruf bleibt ohne Netz
    assert len(_joblogs(session, job)) == 1


def test_sichern_job_ohne_snapshot_bekommt_den_ersten_snapshot(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    _abruf_patchen(monkeypatch, _ok())
    job = _neuer_job(session)
    assert job.posting_snapshot_path is None

    erg = posting_snapshot.anzeigentext_sichern(job.id)

    assert erg["status"] == "nachgeholt"
    session.refresh(job)
    assert job.posting_snapshot_path == erg["posting_snapshot_path"]
    assert job.posting_snapshot_path.startswith("data/job_postings/")
    assert posting_snapshot.hat_anzeigentext(job) is True
    assert "Team von Beratern führen" in _datei(tmp_path, job).read_text(encoding="utf-8")
    assert len(_joblogs(session, job)) == 1


def test_sichern_ersetzt_auch_einen_amber_gegliederten_snapshot_ohne_text(session, monkeypatch, tmp_path):
    """Die Firma-Prüfung lief einmal ohne Anzeige (amber, Teilquelle). Kommt der Text später doch,
    wird dieselbe Datei durch die Basis mit Text ersetzt; gegliedert wird bei der nächsten Prüfung."""
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    _abruf_patchen(monkeypatch, _ok())
    job = _neuer_job(session)
    posting_snapshot.render_full(job.id, {"aufgaben": ["Aus der Zusammenfassung"]}, "amber")
    session.refresh(job)
    rel_vorher = job.posting_snapshot_path

    erg = posting_snapshot.anzeigentext_sichern(job.id)

    assert erg["status"] == "nachgeholt"
    assert erg["posting_snapshot_path"] == rel_vorher
    assert len(list(tmp_path.glob("*.html"))) == 1


def test_sichern_abgelaufen_mit_text_wird_nachgeholt(session, monkeypatch, tmp_path):
    """P2-76: Das Portal ist geschlossen, die Seite zeigt den Text aber noch. Der Text kommt in den
    Snapshot (sonst ginge er mit dem Schließen verloren); der Hinweis nennt das Portal."""
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    abruf = _abruf_patchen(monkeypatch, _abgelaufen(versuche=2))
    job = _neuer_job(session)
    rel_vorher = _basis(session, job, text=None)
    assert posting_snapshot.hat_anzeigentext(job) is False

    erg = posting_snapshot.anzeigentext_sichern(job.id)

    assert erg["status"] == "nachgeholt"
    assert erg["befund"] == "ABGELAUFEN"
    assert erg["versuche"] == 2
    assert erg["grund"] is None
    assert erg["posting_snapshot_path"] == rel_vorher
    session.refresh(job)
    assert job.posting_snapshot_path == rel_vorher
    assert len(list(tmp_path.glob("*.html"))) == 1

    assert len(abruf.aufrufe) == 1
    assert abruf.aufrufe[0]["return_text"] is True

    html = _datei(tmp_path, job).read_text(encoding="utf-8")
    assert '<h2 class="sec">Anzeigentext (automatisch extrahiert, unbereinigt)</h2>' in html
    assert "Team von Beratern führen und Projekte verantworten." in html
    heute = datetime.date.today().strftime("%d.%m.%Y")
    assert (f'<div class="caveat"><b>Hinweis:</b> Anzeigentext am {heute} nachgeholt. '
            f'Das Portal nimmt laut Abruf keine Bewerbungen mehr an. '
            f'Gegliedert wird er bei der nächsten Firma-Prüfung.</div>') in html
    assert posting_snapshot.hat_anzeigentext(job) is True

    logs = _joblogs(session, job)
    assert len(logs) == 1
    assert logs[0].art == "auto"
    assert logs[0].eintrag == "Anzeigentext der Anzeige nachgeholt."


def test_sichern_ok_hinweis_nennt_das_portal_nicht(session, monkeypatch, tmp_path):
    """P2-76: Der Portal-Satz gehört nur zu `ABGELAUFEN`; bei `OK` bleibt der Hinweis wie in P2-75."""
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    _abruf_patchen(monkeypatch, _ok())
    job = _neuer_job(session)
    _basis(session, job, text=None)

    assert posting_snapshot.anzeigentext_sichern(job.id)["status"] == "nachgeholt"

    html = _datei(tmp_path, job).read_text(encoding="utf-8")
    assert "keine Bewerbungen mehr an" not in html


@pytest.mark.parametrize("text", [None, "", "   \n "])
def test_sichern_abgelaufen_ohne_text_bleibt_fehlt(session, monkeypatch, tmp_path, text):
    """P2-76: `ABGELAUFEN` ohne (oder mit leerem) Anzeigentext, etwa nach einer Umleitung auf die
    generische Seite: nichts zu sichern, Datei bytegleich, kein JobLog."""
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    _abruf_patchen(monkeypatch, _abgelaufen(text=text, versuche=1))
    job = _neuer_job(session)
    rel_vorher = _basis(session, job, text=None)
    vorher = _datei(tmp_path, job).read_bytes()

    erg = posting_snapshot.anzeigentext_sichern(job.id)

    assert erg["status"] == "fehlt"
    assert erg["grund"] == GRUND_OFFLINE
    assert erg["befund"] == "ABGELAUFEN"
    assert erg["posting_snapshot_path"] == rel_vorher
    assert _datei(tmp_path, job).read_bytes() == vorher
    session.refresh(job)
    assert job.posting_snapshot_path == rel_vorher
    assert _joblogs(session, job) == []


def test_sichern_abgelaufen_ohne_snapshot_erst_fehlt_dann_nachgeholt(session, monkeypatch, tmp_path):
    """P2-76: Ein Job ohne Snapshot bekommt bei `ABGELAUFEN` mit Text seinen ersten; bei
    `ABGELAUFEN` ohne Text bleibt das Verzeichnis leer."""
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    _abruf_patchen(monkeypatch, _abgelaufen(text=None))
    job = _neuer_job(session)

    erg = posting_snapshot.anzeigentext_sichern(job.id)

    assert erg["status"] == "fehlt" and erg["posting_snapshot_path"] is None
    assert list(tmp_path.iterdir()) == []

    _abruf_patchen(monkeypatch, _abgelaufen())
    erg = posting_snapshot.anzeigentext_sichern(job.id)

    assert erg["status"] == "nachgeholt"
    session.refresh(job)
    assert job.posting_snapshot_path == erg["posting_snapshot_path"]
    assert "Team von Beratern führen" in _datei(tmp_path, job).read_text(encoding="utf-8")


# ── anzeigentext_sichern: fehlt ────────────────────────────────────────────────────────────
_FEHLT_FAELLE = [
    # (Befund, http_status, anzeigentext, erwarteter Grund)
    ("NICHT_PRUEFBAR", 429, None, GRUND_429),
    ("NICHT_PRUEFBAR", 403, None, GRUND_BLOCKIERT),
    ("NICHT_PRUEFBAR", 503, None, GRUND_BLOCKIERT),
    ("LOGIN_WALL", 200, None, GRUND_LOGIN),
    ("TOT", 404, None, GRUND_OFFLINE),
    ("ABGELAUFEN", 200, None, GRUND_OFFLINE),
    ("UMGELEITET_GENERISCH", 200, None, GRUND_OFFLINE),
    # Bei einem unklaren Treffer liefert check_url den Seitentext mit — er darf NICHTS ersetzen.
    ("INHALT_UNKLAR", 200, "Irgendein Seitentext, der nicht eindeutig zur Stelle passt.", GRUND_UNKLAR),
]


@pytest.mark.parametrize("befund,http_status,text,grund", _FEHLT_FAELLE)
def test_sichern_fehlt_je_befund_datei_bleibt_bytegleich(session, monkeypatch, tmp_path,
                                                         befund, http_status, text, grund):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    pr = {"befund": befund, "http_status": http_status, "final_url": "https://example.invalid/x",
          "beleg": "Beleg", "versuche": 4}
    if text:
        pr["anzeigentext"] = text
    _abruf_patchen(monkeypatch, pr)
    job = _neuer_job(session)
    rel_vorher = _basis(session, job, text=None)
    vorher = _datei(tmp_path, job).read_bytes()

    erg = posting_snapshot.anzeigentext_sichern(job.id)

    assert erg["status"] == "fehlt"
    assert erg["grund"] == grund
    assert erg["befund"] == befund
    assert erg["versuche"] == 4
    assert erg["posting_snapshot_path"] == rel_vorher
    assert _datei(tmp_path, job).read_bytes() == vorher
    session.refresh(job)
    assert job.posting_snapshot_path == rel_vorher
    assert _joblogs(session, job) == []


def test_sichern_fehlt_ohne_versuche_feld_im_ergebnis(session, monkeypatch, tmp_path):
    """Das Feld `versuche` stammt aus Paket A; fehlt es im Ergebnis, ist es `None`, kein Fehler."""
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    _abruf_patchen(monkeypatch, {"befund": "NICHT_PRUEFBAR", "http_status": 429, "beleg": "x"})
    job = _neuer_job(session)

    erg = posting_snapshot.anzeigentext_sichern(job.id)

    assert erg["status"] == "fehlt" and erg["grund"] == GRUND_429
    assert erg["versuche"] is None


def test_sichern_fehlt_ohne_snapshot_legt_keine_datei_an(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    _abruf_patchen(monkeypatch, {"befund": "NICHT_PRUEFBAR", "http_status": 429, "beleg": "x",
                                 "versuche": 4})
    job = _neuer_job(session)

    erg = posting_snapshot.anzeigentext_sichern(job.id)

    assert erg["status"] == "fehlt"
    assert erg["posting_snapshot_path"] is None
    assert list(tmp_path.iterdir()) == []
    session.refresh(job)
    assert job.posting_snapshot_path is None
    assert _joblogs(session, job) == []


def test_sichern_fehlt_bei_ok_ohne_text(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    _abruf_patchen(monkeypatch, _ok(text="   "))
    job = _neuer_job(session)
    _basis(session, job, text=None)
    vorher = _datei(tmp_path, job).read_bytes()

    erg = posting_snapshot.anzeigentext_sichern(job.id)

    assert erg["status"] == "fehlt" and erg["befund"] == "OK"
    assert "keinen auswertbaren Anzeigentext" in erg["grund"]
    assert _datei(tmp_path, job).read_bytes() == vorher
    assert _joblogs(session, job) == []


def test_sichern_zeitueberschreitung_ist_nicht_nicht_mehr_online(session, monkeypatch, tmp_path):
    """`check_url` meldet Zeitüberschreitung/Netzfehler als TOT ohne HTTP-Status. Der Grund darf
    dann nicht „nicht mehr online“ lauten: die Anzeige kann leben, nur das Netz hakt."""
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    _abruf_patchen(monkeypatch, {"befund": "TOT", "http_status": None, "beleg": "Timeout nach 20 s"})
    job = _neuer_job(session)

    erg = posting_snapshot.anzeigentext_sichern(job.id)

    assert erg["status"] == "fehlt"
    assert erg["grund"] != GRUND_OFFLINE
    assert "nicht erreicht" in erg["grund"]


def test_sichern_ausnahme_im_abruf_wird_zu_fehlt(session, monkeypatch, tmp_path, capsys):
    """Ein unerwarteter Fehler im Abruf darf den Start einer Aufgabe nicht mit einem 500 abbrechen;
    die Meldung geht auf stderr, nie auf stdout."""
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    _abruf_patchen(monkeypatch, fehler=RuntimeError("kaputt"))
    job = _neuer_job(session)
    _basis(session, job, text=None)
    vorher = _datei(tmp_path, job).read_bytes()

    erg = posting_snapshot.anzeigentext_sichern(job.id)

    assert erg["status"] == "fehlt"
    assert erg["grund"] == "Der Abruf der Anzeige ist fehlgeschlagen."
    assert _datei(tmp_path, job).read_bytes() == vorher
    ausgabe = capsys.readouterr()
    assert ausgabe.out == ""
    assert "kaputt" in ausgabe.err


def test_sichern_schreibt_nichts_auf_stdout(session, monkeypatch, tmp_path, capsys):
    """Der Aufruf kommt im Server aus einem Threadpool: keine Ausgaben auf stdout."""
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    _abruf_patchen(monkeypatch, _ok())
    job = _neuer_job(session)

    assert posting_snapshot.anzeigentext_sichern(job.id)["status"] == "nachgeholt"
    assert capsys.readouterr().out == ""


# ── Sonderfälle: keine URL, gelöscht, unbekannt ────────────────────────────────────────────
@pytest.mark.parametrize("url", [None, "", "   "])
def test_sichern_ohne_url_fehlt_ohne_abruf(session, monkeypatch, tmp_path, url):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    abruf = _abruf_patchen(monkeypatch)
    job = _neuer_job(session, url=None)
    if url is not None:
        job.url = url
        session.add(job)
        session.commit()

    erg = posting_snapshot.anzeigentext_sichern(job.id)

    assert erg["status"] == "fehlt"
    assert erg["grund"] == GRUND_KEINE_URL
    assert erg["befund"] is None and erg["versuche"] is None
    assert abruf.aufrufe == []
    assert list(tmp_path.iterdir()) == []


def test_sichern_geloeschter_job_fehlt_ohne_abruf(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    abruf = _abruf_patchen(monkeypatch)
    job = _neuer_job(session)
    job.deleted_at = datetime.datetime.utcnow().isoformat()
    session.add(job)
    session.commit()

    erg = posting_snapshot.anzeigentext_sichern(job.id)

    assert erg["status"] == "fehlt"
    assert erg["grund"] == GRUND_NICHT_GEFUNDEN
    assert abruf.aufrufe == []


def test_sichern_unbekannte_job_id_fehlt(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    abruf = _abruf_patchen(monkeypatch)

    erg = posting_snapshot.anzeigentext_sichern(987654321)

    assert erg == {"job_id": 987654321, "status": "fehlt", "grund": GRUND_NICHT_GEFUNDEN,
                   "befund": None, "versuche": None, "posting_snapshot_path": None}
    assert abruf.aufrufe == []


# ── nachholen() im Bestand ─────────────────────────────────────────────────────────────────
def _bestand(session, tmp_path):
    """Vier Jobs mit gemeinsamem, eindeutigem Status (in dieser ID-Reihenfolge):
    mit Text · ohne Text · ohne Text · gelöscht. Dazu ein Job mit anderem Status (nicht im Filter)."""
    from pipeline import posting_snapshot

    status = f"P275Bestand-{uuid.uuid4().hex[:8]}"
    mit_text = _neuer_job(session, status=status)
    _basis(session, mit_text, text=ANZEIGENTEXT)
    ohne_a = _neuer_job(session, status=status)
    _basis(session, ohne_a, text=None)
    ohne_b = _neuer_job(session, status=status)
    _basis(session, ohne_b, text=None)
    geloescht = _neuer_job(session, status=status)
    geloescht.deleted_at = datetime.datetime.utcnow().isoformat()
    session.add(geloescht)
    session.commit()
    anderer = _neuer_job(session, status=f"{status}-anders")
    _basis(session, anderer, text=None)
    return status, mit_text, ohne_a, ohne_b, geloescht, anderer


def test_nachholen_bestand_zaehlt_und_pausiert_nur_nach_netzabruf(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    pausen = []
    monkeypatch.setattr(posting_snapshot, "_schlafen", pausen.append)
    status, mit_text, ohne_a, ohne_b, geloescht, anderer = _bestand(session, tmp_path)
    antworten = {ohne_a.url: _ok(), ohne_b.url: {"befund": "NICHT_PRUEFBAR", "http_status": 429,
                                                 "beleg": "x", "versuche": 4}}

    aufrufe = []

    def abruf(url, company, title, return_text=False, **kw):
        aufrufe.append(url)
        return dict(antworten[url])

    from pipeline import verify_jobs
    monkeypatch.setattr(verify_jobs, "check_url", abruf)

    erg = posting_snapshot.nachholen(status, dry_run=False)

    assert erg["jobs_gesamt"] == 3                                    # gelöscht und anderer Status fehlen
    assert (erg["vorhanden"], erg["nachgeholt"], erg["fehlt"]) == (1, 1, 1)
    assert erg["fehlt_ids"] == [ohne_b.id]
    assert erg["dry_run"] is False
    assert [e["job_id"] for e in erg["jobs"]] == [mit_text.id, ohne_a.id, ohne_b.id]
    assert aufrufe == [ohne_a.url, ohne_b.url]                        # nur die ohne Text wurden abgerufen
    # Pause (0,5 s) nur NACH dem Abruf von ohne_a (es folgt noch ein Job); weder nach dem Job ohne
    # Netzabruf noch nach dem letzten Job.
    assert pausen == [0.5]
    # Der Job mit anderem Status blieb unberührt
    session.refresh(anderer)
    assert posting_snapshot.hat_anzeigentext(anderer) is False


def test_nachholen_trockenlauf_zaehlt_ohne_netz_und_ohne_schreiben(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    pausen = []
    monkeypatch.setattr(posting_snapshot, "_schlafen", pausen.append)
    abruf = _abruf_patchen(monkeypatch)                               # jeder Aufruf = Testfehler
    status, mit_text, ohne_a, ohne_b, geloescht, anderer = _bestand(session, tmp_path)
    vorher = {p.name: p.read_bytes() for p in tmp_path.iterdir()}

    erg = posting_snapshot.nachholen(status, dry_run=True)

    assert erg["dry_run"] is True
    assert erg["jobs_gesamt"] == 3
    assert (erg["vorhanden"], erg["nachgeholt"], erg["fehlt"]) == (1, 0, 2)
    assert erg["fehlt_ids"] == [ohne_a.id, ohne_b.id]
    assert abruf.aufrufe == []
    assert pausen == []
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == vorher
    assert _joblogs(session, ohne_a) == []


def test_nachholen_mit_job_id_ignoriert_den_statusfilter(session, monkeypatch, tmp_path):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    _abruf_patchen(monkeypatch, _ok())
    job = _neuer_job(session, status="Absage")                        # nicht in der Standardliste
    _basis(session, job, text=None)

    erg = posting_snapshot.nachholen(job_id=job.id)

    assert erg["jobs_gesamt"] == 1 and erg["nachgeholt"] == 1


# ── CLI: _nachholen_main ───────────────────────────────────────────────────────────────────
def _json_von_stdout(capsys):
    ausgabe = capsys.readouterr()
    return json.loads(ausgabe.out), ausgabe.err


def test_cli_job_id_nachgeholt_exit_0_json_auf_stdout_tabelle_auf_stderr(session, monkeypatch, tmp_path, capsys):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    _abruf_patchen(monkeypatch, _ok())
    job = _neuer_job(session)
    _basis(session, job, text=None)

    code = posting_snapshot._nachholen_main(job.id, posting_snapshot._NACHHOLEN_STATUS_STANDARD, False)

    daten, err = _json_von_stdout(capsys)                             # stdout = genau ein JSON-Dokument
    assert code == 0
    assert daten["status"] == "nachgeholt" and daten["job_id"] == job.id
    assert str(job.id) in err and "nachgeholt" in err


def test_cli_job_id_vorhanden_exit_0(session, monkeypatch, tmp_path, capsys):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    _abruf_patchen(monkeypatch)
    job = _neuer_job(session)
    _basis(session, job, text=ANZEIGENTEXT)

    code = posting_snapshot._nachholen_main(job.id, "", False)

    daten, _ = _json_von_stdout(capsys)
    assert code == 0 and daten["status"] == "vorhanden"


def test_cli_job_id_fehlt_exit_3(session, monkeypatch, tmp_path, capsys):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    _abruf_patchen(monkeypatch, {"befund": "NICHT_PRUEFBAR", "http_status": 429, "beleg": "x",
                                 "versuche": 4})
    job = _neuer_job(session)

    code = posting_snapshot._nachholen_main(job.id, "", False)

    daten, err = _json_von_stdout(capsys)
    assert code == 3
    assert daten["status"] == "fehlt" and daten["grund"] == GRUND_429 and daten["versuche"] == 4
    assert GRUND_429 in err


def test_cli_job_id_dry_run_ohne_netz(session, monkeypatch, tmp_path, capsys):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    abruf = _abruf_patchen(monkeypatch)                               # jeder Aufruf = Testfehler
    job = _neuer_job(session)
    _basis(session, job, text=None)
    vorher = _datei(tmp_path, job).read_bytes()

    code = posting_snapshot._nachholen_main(job.id, "", True)

    daten, _ = _json_von_stdout(capsys)
    assert code == 3                                                  # kein Text im Snapshot
    assert daten["status"] == "fehlt" and daten["dry_run"] is True
    assert abruf.aufrufe == []
    assert _datei(tmp_path, job).read_bytes() == vorher


def test_cli_bestand_exit_0_und_zusammenfassung(session, monkeypatch, tmp_path, capsys):
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    monkeypatch.setattr(posting_snapshot, "_schlafen", lambda s: None)
    _abruf_patchen(monkeypatch, {"befund": "NICHT_PRUEFBAR", "http_status": 429, "beleg": "x",
                                 "versuche": 4})
    status, mit_text, ohne_a, ohne_b, geloescht, anderer = _bestand(session, tmp_path)

    code = posting_snapshot._nachholen_main(None, status, False)

    daten, _ = _json_von_stdout(capsys)
    assert code == 0                                                  # im Bestand immer 0
    assert daten["jobs_gesamt"] == 3
    assert (daten["vorhanden"], daten["nachgeholt"], daten["fehlt"]) == (1, 0, 2)
    assert daten["fehlt_ids"] == [ohne_a.id, ohne_b.id]
    assert "jobs" not in daten                                        # Einzelheiten stehen auf stderr


# ── CLI: Verdrahtung über `python -m pipeline.posting_snapshot` (im Prozess) ────────────────
def _als_main(argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["posting_snapshot", *argv])
    with pytest.raises(SystemExit) as ende:
        runpy.run_module("pipeline.posting_snapshot", run_name="__main__")
    return ende.value.code


def test_cli_verdrahtung_exit_codes_und_dry_run(session, monkeypatch, capsys):
    """`runpy` führt den `__main__`-Block in einem frischen Namensraum aus: dessen
    `_SNAPSHOT_DIR` ist `DATA_DIR/job_postings`, also das tmp-Datenverzeichnis des Tests (conftest),
    nie das echte `data/`. Kein Test-Monkeypatch auf `_SNAPSHOT_DIR` hier."""
    import os
    from pipeline import posting_snapshot

    assert str(posting_snapshot._SNAPSHOT_DIR).startswith(os.environ["BMS_DATA_DIR"])
    abruf = _abruf_patchen(monkeypatch)                               # jeder Aufruf = Testfehler

    mit_text = _neuer_job(session)
    _basis(session, mit_text, text=ANZEIGENTEXT)
    ohne_url = _neuer_job(session, url=None)
    ohne_text = _neuer_job(session)
    _basis(session, ohne_text, text=None)

    assert _als_main(["nachholen", "--job-id", str(mit_text.id)], monkeypatch) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "vorhanden"

    assert _als_main(["nachholen", "--job-id", str(ohne_url.id)], monkeypatch) == 3
    assert json.loads(capsys.readouterr().out)["grund"] == GRUND_KEINE_URL

    assert _als_main(["nachholen", "--job-id", str(ohne_text.id), "--dry-run"], monkeypatch) == 3
    assert json.loads(capsys.readouterr().out)["dry_run"] is True

    assert _als_main(["nachholen", "--status", f"gibt-es-nicht-{uuid.uuid4().hex}", "--dry-run"],
                     monkeypatch) == 0
    assert json.loads(capsys.readouterr().out)["jobs_gesamt"] == 0
    assert abruf.aufrufe == []
