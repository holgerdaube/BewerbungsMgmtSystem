"""Direkt-Fixes 27.07.2026 nach dem Job-272-Vorfall (Match-1-Vertriebsrolle bekam volle
Unterlagen, Triage übersprungen, Review-Statuswechsel unsichtbar):

Fix 1 — `_set_status` (Review ✓/✕) schreibt jetzt einen JobLog-Eintrag (vorher der EINZIGE
Status-Pfad ohne Log; 8 Jobs standen kommentarlos auf „Prüfen").
Fix 2 — `_guard_low_match`: Unterlagen-Läufe (LOW_MATCH_KINDS) für Stellen mit Match ≤ 2
liefern 409 „LOW_MATCH: …", außer `params.low_match_ok=true` kommt ausdrücklich mit;
`beirat-stellen-check` und unbewertete Jobs bleiben frei.

Wie in conftest.py beschrieben: KEINE app.*-Importe auf Modulebene, nur in Testfunktionen.
Der Override-Positivfall wird als Unit-Test gegen `_guard_low_match` geprüft (kein echter
POST — der würde eine AgentTask-Row anlegen und den Runner anwerfen)."""
import uuid

import pytest


def _job_anlegen(session, match_score, status="Neu"):
    from app.models import Job
    j = Job(company_name=f"LowMatch AG {uuid.uuid4().hex[:8]}", title="Teststelle",
            match_score=match_score, match_rationale="Vertriebsrolle, kein PS-Bezug",
            status=status, dedup_key=uuid.uuid4().hex)
    session.add(j)
    session.commit()
    session.refresh(j)
    return j


# ── Fix 1: Review-Statuswechsel schreibt JobLog ──────────────────────────────────────────────

def test_approve_schreibt_joblog(client, session):
    from sqlmodel import select
    from app.models import JobLog
    j = _job_anlegen(session, match_score=4, status="Neu")
    resp = client.post(f"/api/jobs/{j.id}/approve")
    assert resp.status_code == 200 and resp.json()["status"] == "Prüfen"
    logs = session.exec(select(JobLog).where(JobLog.job_id == j.id)).all()
    assert len(logs) == 1 and logs[0].art == "auto"
    assert logs[0].eintrag == "Status: Neu → Prüfen (Review)"


def test_discard_schreibt_joblog(client, session):
    from sqlmodel import select
    from app.models import JobLog
    j = _job_anlegen(session, match_score=1, status="Neu")
    resp = client.post(f"/api/jobs/{j.id}/discard")
    assert resp.status_code == 200 and resp.json()["status"] == "Kein Match"
    logs = session.exec(select(JobLog).where(JobLog.job_id == j.id)).all()
    assert [l.eintrag for l in logs] == ["Status: Neu → Kein Match (Review)"]


def test_gleicher_status_erzeugt_keinen_logeintrag(client, session):
    from sqlmodel import select
    from app.models import JobLog
    j = _job_anlegen(session, match_score=4, status="Prüfen")
    client.post(f"/api/jobs/{j.id}/approve")   # Prüfen → Prüfen (No-Op)
    assert session.exec(select(JobLog).where(JobLog.job_id == j.id)).all() == []


# ── Fix 2: Match-≤2-Guard am Task-Start ──────────────────────────────────────────────────────

def test_unterlagen_task_bei_match_1_liefert_409_low_match(client, session):
    j = _job_anlegen(session, match_score=1, status="Prüfen")
    resp = client.post("/api/tasks", json={"kind": "firma-pruefen", "job_id": j.id})
    assert resp.status_code == 409
    assert resp.json()["detail"].startswith("LOW_MATCH:")
    assert "1/5" in resp.json()["detail"]


def test_match_3_und_unbewertet_passieren_den_guard(session):
    from app.main import _guard_low_match
    j3 = _job_anlegen(session, match_score=3)
    j_none = _job_anlegen(session, match_score=None)
    _guard_low_match(j3, {"firma-pruefen"}, {})       # darf nicht raisen
    _guard_low_match(j_none, {"cv-erstellen"}, {})    # unbewertet → frei


def test_override_und_freie_kinds_passieren(session):
    from fastapi import HTTPException
    from app.main import _guard_low_match
    j = _job_anlegen(session, match_score=2)
    _guard_low_match(j, {"firma-pruefen"}, {"low_match_ok": True})   # Override → frei
    _guard_low_match(j, {"beirat-stellen-check"}, {})                # Beirat bewusst frei
    with pytest.raises(HTTPException) as e:
        _guard_low_match(j, {"cv-match"}, {})                        # ohne Override → 409
    assert e.value.status_code == 409 and str(e.value.detail).startswith("LOW_MATCH:")


def test_kette_mit_unterlagen_schritt_wird_gegatet(client, session):
    """Rezepte (Ganze Kette) enthalten Unterlagen-Schritte → derselbe Guard greift.
    Geprüft werden ALLE Rezepte mit mindestens einem Unterlagen-Schritt — „tageslauf" hat
    keinen (reiner Ingest-Lauf) und ist bewusst nicht gatebar."""
    from app import agent_runner
    from app.main import LOW_MATCH_KINDS
    rezepte = [k for k, v in agent_runner.RECIPES.items() if set(v["steps"]) & LOW_MATCH_KINDS]
    assert rezepte, "kein Rezept mit Unterlagen-Schritt — Test liefe ins Leere"
    j = _job_anlegen(session, match_score=1, status="Prüfen")
    for rezept in rezepte:   # _guard_low_match wirft VOR dem Anlegen der Rows → keine Seiteneffekte
        resp = client.post("/api/tasks", json={"kind": rezept, "job_id": j.id})
        assert resp.status_code == 409, rezept
        assert resp.json()["detail"].startswith("LOW_MATCH:"), rezept


def test_kette_bewerbungspaket_greift_ueber_ihre_schritte(client, session):
    """Phase 83: „bewerbungspaket“ ist ein REZEPT, keine Task-Art — der Guard greift trotzdem,
    weil `create_task()` die Kette vorher über `agent_runner.rezept_aufloesen()` auflöst. Damit
    ist ein Ketten-Name in LOW_MATCH_KINDS überflüssig (dort stand bis Phase 83 das tote
    „job-deepdive“, das es als Task-Art nie gab). P2-41: das vormalige Rezept „deepdive“ entfällt
    ersatzlos — inhaltlich deckungsgleich mit „bewerbungspaket“ ohne den optionalen
    Anschreiben-Baustein (Standard aus). Fällt dieser Test, wurde die Schritt-Auflösung
    angefasst."""
    from app import agent_runner
    from app.main import LOW_MATCH_KINDS
    assert "deepdive" not in agent_runner.RECIPES                            # P2-41: entfallen
    assert "bewerbungspaket" in agent_runner.RECIPES and "bewerbungspaket" not in agent_runner.PROMPTS
    assert "bewerbungspaket" not in LOW_MATCH_KINDS                      # Kette selbst NICHT im Set …
    assert set(agent_runner.RECIPES["bewerbungspaket"]["steps"]) & LOW_MATCH_KINDS   # … ihre Schritte schon
    assert LOW_MATCH_KINDS <= set(agent_runner.PROMPTS)   # nur echte Task-Arten, keine toten Namen
    j = _job_anlegen(session, match_score=1, status="Prüfen")
    resp = client.post("/api/tasks", json={"kind": "bewerbungspaket", "job_id": j.id})
    assert resp.status_code == 409
    assert resp.json()["detail"].startswith("LOW_MATCH:")
