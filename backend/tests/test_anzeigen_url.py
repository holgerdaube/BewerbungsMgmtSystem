"""Maschinen-Fassung einer Stellenseite (17.11.2026).

Workable stellt neben jeder Anzeige (`apply.workable.com/<konto>/j/<code>`) eine Markdown-Fassung
für KI-Werkzeuge bereit (`/<konto>/jobs/view/<code>.md`). Die Websuche lieferte diese Fassung, die
Jobsuche übernahm sie wörtlich, und der Link der Stelle zeigte im Browser rohes Markdown. Die Seite
für Menschen wiederum liefert einem Abruf nur eine leere App-Hülle mit dem Titel.

Vertrag:
  * `normalize.anzeigen_url` bildet die Maschinen-Fassung auf die Seite für Menschen ab,
    `normalize.abruf_url` umgekehrt; jede andere Adresse bleibt unverändert.
  * Der Ingest speichert die Adresse für Menschen und findet den Anzeigentext trotzdem unter der
    Adresse, die der Record mitbrachte.
  * `verify_jobs.check_url` ruft für die Seite für Menschen die Maschinen-Fassung ab.

Konvention conftest.py: keine app.*/pipeline.*-Importe auf Modulebene."""
import uuid

import httpx
import pytest

_MENSCH = "https://apply.workable.com/beispiel/j/ABC123DEF0"
_MASCHINE = "https://apply.workable.com/beispiel/jobs/view/ABC123DEF0.md"
_ECHTER_CLIENT = httpx.Client


@pytest.mark.parametrize("eingabe", [
    _MASCHINE,
    "https://apply.workable.com/beispiel/jobs/view/ABC123DEF0",
    "https://apply.workable.com/beispiel/jobs/view/ABC123DEF0/",
    "https://apply.workable.com/beispiel/jobs/view/ABC123DEF0.md?utm_source=suche",
    "http://apply.workable.com/beispiel/jobs/view/ABC123DEF0.md",
])
def test_anzeigen_url_bildet_maschinen_fassung_auf_seite_fuer_menschen_ab(eingabe):
    from app.normalize import anzeigen_url

    assert anzeigen_url(eingabe) == _MENSCH


@pytest.mark.parametrize("eingabe", [
    _MENSCH,
    _MENSCH + "/",
    _MENSCH + "/?utm_source=suche",
])
def test_abruf_url_bildet_seite_fuer_menschen_auf_maschinen_fassung_ab(eingabe):
    from app.normalize import abruf_url

    assert abruf_url(eingabe) == _MASCHINE


@pytest.mark.parametrize("andere", [
    None,
    "",
    "https://www.linkedin.com/jobs/view/1234567890/",
    "https://beispiel.jobs.personio.de/job/123456",
    "https://example.test/stellen/handbuch.md",
    "https://apply.workable.com/beispiel/",
    "https://apply.workable.com/beispiel/j/ABC123DEF0/apply",
])
def test_andere_adressen_bleiben_unveraendert(andere):
    from app.normalize import abruf_url, anzeigen_url

    assert anzeigen_url(andere) == andere
    assert abruf_url(andere) == andere


def test_ingest_speichert_seite_fuer_menschen_und_findet_den_anzeigentext(session, monkeypatch, tmp_path):
    import pipeline.dedup_text as dedup_text

    leere_config = tmp_path / "suchprofile.yaml"
    leere_config.write_text("dedup_text: {}\n", encoding="utf-8")
    monkeypatch.setattr(dedup_text, "CONFIG_FILE", leere_config)
    from sqlmodel import select

    from app.models import Job
    from pipeline.ingest import ingest_records

    konto = f"beispiel{uuid.uuid4().hex[:6]}"
    maschine = f"https://apply.workable.com/{konto}/jobs/view/ABC123DEF0.md"
    rec = {"company": f"Beispiel {konto} GmbH", "title": "Director Professional Services", "url": maschine,
           "verifikation": {"status": "BESTÄTIGT", "beleg": "Anzeige gesehen", "geprueft_am": "2026-11-17"}}
    text = "# Director Professional Services\n\nBeispiel GmbH sucht eine Leitung für Professional Services."

    ergebnis = ingest_records([rec], texte={maschine: text})

    assert ergebnis["new"] == 1, ergebnis
    assert ergebnis["snapshots"] == 1, ergebnis
    job = session.get(Job, ergebnis["new_ids"][0])
    assert job.url == f"https://apply.workable.com/{konto}/j/ABC123DEF0"
    # Derselbe Treffer als Maschinen-Fassung in einem späteren Lauf ist eine Dublette.
    assert ingest_records([dict(rec)], texte={})["dup"] == 1
    assert len(session.exec(select(Job).where(Job.url.contains(konto))).all()) == 1


def test_check_url_ruft_fuer_die_seite_fuer_menschen_die_maschinen_fassung_ab(monkeypatch):
    import pipeline.verify_jobs as verify_jobs

    aufrufe = []

    def handler(request):
        aufrufe.append(str(request.url))
        return httpx.Response(200, text="# Head of Customer Success\n\n> Beispiel · Remote\n\nBeispiel GmbH sucht ...")

    monkeypatch.setattr(httpx, "Client", lambda **kw: _ECHTER_CLIENT(transport=httpx.MockTransport(handler), **kw))

    pr = verify_jobs.check_url(_MENSCH, "Beispiel GmbH", "Head of Customer Success", return_text=True)

    assert aufrufe == [_MASCHINE]
    assert pr["befund"] == "OK", pr
    assert "Beispiel GmbH sucht" in pr["anzeigentext"]
