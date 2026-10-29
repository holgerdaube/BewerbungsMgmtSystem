"""Smoke-Tests fuer die Kern-Endpunkte (Phase 57 Stufe E1.4).

Wie in conftest.py beschrieben: KEINE app.*-Importe auf Modulebene, nur in Testfunktionen.
Nutzt die Fixtures `client`/`seed` aus conftest.py (App-Import + BMS_DATA_DIR-Isolation dort).
"""


def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_jobs_list_ok_und_seed_sichtbar(client, seed):
    r = client.get("/api/jobs")
    assert r.status_code == 200
    jobs = r.json()
    assert isinstance(jobs, list)

    titel_zu_job = {j["title"]: j for j in jobs}
    assert "Head of Customer Success" in titel_zu_job
    assert "Director Professional Services" in titel_zu_job

    seed_job = titel_zu_job["Head of Customer Success"]
    assert seed_job["company_name"] == seed["companies"][0].name
    assert seed_job["status"] == "Beworben"
    assert seed_job["match_score"] == 4
    # Vertrag der Response-Form (main.py::list_jobs) — schrumpft er, faellt es hier auf.
    erwartete_keys = {
        "id", "company_name", "title", "seniority", "location", "work_model", "tab",
        "plan_ab", "portal", "url", "match_score", "status", "next_step", "found_date",
        "salary", "follow_up_date", "verified_at", "verify_note",
    }
    assert erwartete_keys.issubset(seed_job.keys())


def test_dashboard_ok_und_erwartete_keys(client, seed):
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    data = r.json()

    assert set(data.keys()) == {
        "totals", "by_status", "by_score", "by_portal", "by_tab",
        "by_situation", "by_situation_plan", "funnel", "gesamtprozess",
    }
    erwartete_totals_keys = {
        "jobs", "companies", "radar_companies", "applications", "active_applications",
        "applied_offline",   # Phase 74: Beworben-Check
        "emails", "responses", "avg_response_hours", "response_rate", "top_matches",
        "followups_overdue", "followups_open", "netzwerk_overdue", "netzwerk_open",
    }
    assert set(data["totals"].keys()) == erwartete_totals_keys

    # Gesamtprozess seit Beginn (Phase 69, Stufe B) — additiver Block, EINE Berechnung
    # ueber app.gesamtprozess (Stufe A). "rows" nur bei "keine_reaktion" (Payload klein halten).
    # "funnel" (Phase 70, Stufe A) additiv dazugekommen -- lebt bewusst unter gesamtprozess.funnel,
    # NICHT auf Top-Level ("funnel" dort ist der Pipeline-Funnel, s. Assertion oben).
    assert set(data["gesamtprozess"].keys()) == {
        "bewerbungen", "gespraeche", "absagen", "keine_reaktion", "funnel",
    }
    for kpi_name in ("bewerbungen", "gespraeche", "absagen"):
        assert set(data["gesamtprozess"][kpi_name].keys()) == {"wert", "splits"}
    assert set(data["gesamtprozess"]["keine_reaktion"].keys()) == {"wert", "splits", "rows"}
    assert set(data["gesamtprozess"]["funnel"].keys()) == {"stufen", "engstellen"}
    assert len(data["gesamtprozess"]["funnel"]["stufen"]) == 5

    # Seed-Daten muessen mitgezaehlt sein (>= statt ==, da die tmp-DB ueber mehrere Tests
    # hinweg akkumuliert -- s. conftest.py::seed-Docstring).
    assert data["totals"]["jobs"] >= 2
    assert data["totals"]["applications"] >= 1
    assert data["funnel"]["Beworben"] >= 1
