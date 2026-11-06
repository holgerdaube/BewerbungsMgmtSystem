"""Ein Lauf mit festem Ergebnis gilt nur als fertig, wenn das Ergebnis da ist.

Anlass: Ein `cv-match` hörte nach dem inneren Skill `cv-job-match` auf. Exit-Code 0 und ein Abschlusstext, also „done“, aber
weder Entwurf noch Dashboard. Erst der Folgeschritt `cv-erstellen` fiel darüber.

Kein app.*-Import auf Modulebene (conftest.py-Konvention).
"""
import asyncio
import datetime
import json
import os
import stat
import uuid

import pytest


def _jetzt():
    return datetime.datetime.utcnow()


@pytest.fixture()
def stelle(session):
    from app.models import Company, Job

    firma = Company(name="Beispiel " + uuid.uuid4().hex[:8])
    session.add(firma)
    session.commit()
    session.refresh(firma)
    job = Job(company_id=firma.id, company_name=firma.name, title="Rolle", portal="LinkedIn", status="Neu",
              dedup_key=uuid.uuid4().hex, found_date="2026-11-05")
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def _datei(name, alter_s=0):
    """Datei unter der Test-Datenwurzel, gespeicherter Pfad wie in der Datenbank."""
    from app.db import DATA_DIR

    ordner = DATA_DIR / "ergebnis_test"
    ordner.mkdir(parents=True, exist_ok=True)
    pfad = ordner / f"{uuid.uuid4().hex}_{name}"
    pfad.write_text("x", encoding="utf-8")
    if alter_s:
        stempel = pfad.stat().st_mtime - alter_s
        os.utime(pfad, (stempel, stempel))
    return f"data/ergebnis_test/{pfad.name}"


def test_cv_match_ohne_neuen_entwurf_ist_kein_erfolg(session, stelle):
    from app.agent_runner import _ergebnis_fehlt
    from app.models import CVVersion

    start = _jetzt()
    assert "CV" in _ergebnis_fehlt("cv-match", stelle.id, start)
    # Ein alter Entwurf aus einem früheren Lauf zählt nicht.
    session.add(CVVersion(job_id=stelle.id, status="entwurf", match_dashboard_path="data/x.html",
                          created_at=start - datetime.timedelta(hours=1)))
    # Ein neuer Entwurf ohne Dashboard ist genau der halbfertige Zustand.
    session.add(CVVersion(job_id=stelle.id, status="entwurf", created_at=start + datetime.timedelta(seconds=5)))
    session.commit()
    assert _ergebnis_fehlt("cv-match", stelle.id, start)

    session.add(CVVersion(job_id=stelle.id, status="entwurf", match_dashboard_path="data/x.html",
                          created_at=start + datetime.timedelta(seconds=5)))
    session.commit()
    assert _ergebnis_fehlt("cv-match", stelle.id, start) is None


def test_cv_erstellen_braucht_eine_neu_geschriebene_datei(session, stelle):
    from app.agent_runner import _ergebnis_fehlt
    from app.models import CVVersion

    start = _jetzt()
    session.add(CVVersion(job_id=stelle.id, status="fertig", file_path=_datei("alt.docx", alter_s=3600)))
    session.add(CVVersion(job_id=stelle.id, status="entwurf", file_path=_datei("entwurf.docx")))
    session.commit()
    assert _ergebnis_fehlt("cv-erstellen", stelle.id, start)

    session.add(CVVersion(job_id=stelle.id, status="fertig", file_path=_datei("neu.docx")))
    session.commit()
    assert _ergebnis_fehlt("cv-erstellen", stelle.id, start) is None


def test_firma_pruefen_braucht_einen_neuen_bericht(session, stelle):
    from app.agent_runner import _ergebnis_fehlt
    from app.models import Company

    start = _jetzt()
    firma = session.get(Company, stelle.company_id)
    firma.fit_analysis_path = _datei("alt.html", alter_s=3600)
    session.add(firma)
    session.commit()
    assert _ergebnis_fehlt("firma-pruefen", stelle.id, start)

    firma.fit_analysis_path = _datei("neu.html")
    session.add(firma)
    session.commit()
    assert _ergebnis_fehlt("firma-pruefen", stelle.id, start) is None


def test_firma_pruefen_ohne_firmeneintrag_schaut_in_den_ordner(session, stelle):
    from app.agent_runner import _ergebnis_fehlt
    from app.db import DATA_DIR

    start = _jetzt()
    stelle.company_id = None
    session.add(stelle)
    session.commit()
    ordner = DATA_DIR / "company_fit"
    ordner.mkdir(parents=True, exist_ok=True)
    for alt in ordner.glob("*CompanyFit*.html"):
        alt.unlink()
    assert _ergebnis_fehlt("firma-pruefen", stelle.id, start)
    (ordner / "20261105_CompanyFit_Beispiel.html").write_text("x", encoding="utf-8")
    assert _ergebnis_fehlt("firma-pruefen", stelle.id, start) is None


def test_anschreiben_braucht_eine_neu_geschriebene_datei(session, stelle):
    from app.agent_runner import _ergebnis_fehlt
    from app.models import Application

    start = _jetzt()
    bewerbung = Application(job_id=stelle.id, cover_letter_path=_datei("alt.docx", alter_s=3600))
    session.add(bewerbung)
    session.commit()
    assert _ergebnis_fehlt("anschreiben-erstellen", stelle.id, start)

    bewerbung.cover_letter_path = _datei("neu.docx")
    session.add(bewerbung)
    session.commit()
    assert _ergebnis_fehlt("anschreiben-erstellen", stelle.id, start) is None


def test_andere_arten_und_laeufe_ohne_stelle_bleiben_unberuehrt(stelle):
    from app.agent_runner import _ergebnis_fehlt

    assert _ergebnis_fehlt("job-frage", stelle.id, _jetzt()) is None
    assert _ergebnis_fehlt("cv-match", None, _jetzt()) is None
    assert _ergebnis_fehlt("cv-match", 987654321, _jetzt()) is None


def test_scheitert_die_pruefung_selbst_bleibt_der_lauf_gut(stelle, monkeypatch, capsys):
    from app import agent_runner

    def kaputt(*_):
        raise RuntimeError("Datenbank weg")

    monkeypatch.setitem(agent_runner._ERGEBNIS_PRUEFUNG, "cv-match", kaputt)
    assert agent_runner._ergebnis_fehlt("cv-match", stelle.id, _jetzt()) is None
    assert "Ergebnisprüfung" in capsys.readouterr().out


def test_meldung_folgt_der_sprache(stelle, monkeypatch):
    from app import agent_runner, sprache

    monkeypatch.setattr(sprache, "aktuell", lambda: "en")
    assert agent_runner._ergebnis_fehlt("cv-match", stelle.id, _jetzt()).startswith("The run did not create")


def _falscher_claude(tmp_path):
    """Programm, das wie ein erfolgreicher Lauf endet, aber nichts anlegt."""
    ereignis = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "Fertig.",
                           "num_turns": 1, "total_cost_usd": 0.0})
    pfad = tmp_path / "claude_probe"
    pfad.write_text(f"#!/bin/sh\ncat <<'ENDE'\n{ereignis}\nENDE\n", encoding="utf-8")
    pfad.chmod(pfad.stat().st_mode | stat.S_IEXEC)
    return str(pfad)


@pytest.mark.skipif(os.name == "nt", reason="Shell-Attrappe nur unter Unix")
def test_lauf_ohne_ergebnis_endet_als_fehlgeschlagen(session, stelle, tmp_path, monkeypatch):
    """Der ganze Weg durch den Runner: Exit-Code 0 und Abschlusstext, aber kein Entwurf."""
    from sqlmodel import Session

    from app import agent_runner, ki_anbieter
    from app.db import engine
    from app.models import AgentTask

    monkeypatch.setattr(agent_runner, "CLAUDE_BIN", _falscher_claude(tmp_path))
    monkeypatch.setattr(ki_anbieter, "aktiv", lambda: "claude")
    task = AgentTask(kind="cv-match", job_id=stelle.id, status="queued", prompt="Testprompt (pytest)")
    session.add(task)
    session.commit()
    session.refresh(task)

    asyncio.run(agent_runner._run_task(task.id))

    with Session(engine) as s:
        fertig = s.get(AgentTask, task.id)
        assert fertig.status == "failed", fertig.error
        assert "CV-Entwurf" in fertig.error


@pytest.mark.skipif(os.name == "nt", reason="Shell-Attrappe nur unter Unix")
def test_gegenprobe_ohne_pruefung_bliebe_der_lauf_done(session, stelle, tmp_path, monkeypatch):
    """Gegenprobe zum Test davor: Dieselbe Attrappe endet ohne Prüfung als „done“, das war der Fehler."""
    from sqlmodel import Session

    from app import agent_runner, ki_anbieter
    from app.db import engine
    from app.models import AgentTask

    monkeypatch.setattr(agent_runner, "CLAUDE_BIN", _falscher_claude(tmp_path))
    monkeypatch.setattr(ki_anbieter, "aktiv", lambda: "claude")
    monkeypatch.delitem(agent_runner._ERGEBNIS_PRUEFUNG, "cv-match")
    task = AgentTask(kind="cv-match", job_id=stelle.id, status="queued", prompt="Testprompt (pytest)")
    session.add(task)
    session.commit()
    session.refresh(task)

    asyncio.run(agent_runner._run_task(task.id))

    with Session(engine) as s:
        assert s.get(AgentTask, task.id).status == "done"
