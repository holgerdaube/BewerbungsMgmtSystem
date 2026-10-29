"""Phase 74 — Beworben-Check (wöchentliche Verfügbarkeitsprüfung): zwei neue Job-Felder
`availability_status` (TEXT, nullable, feste Wertemenge offen/karriereseite_offen/offline/unklar)
und `availability_checked_at` (TEXT, nullable, ISO-Datum), s.
tasks/spec_phase74_beworben_check.md Stufe A (Backend).

Deckt A7 der Bau-Spec ab (5 Tests):
  1. PATCH speichert availability_status/availability_checked_at, GET /api/jobs/{id} liefert
     beide korrekt zurück; ein ungültiger availability_status -> 422, Bestand bleibt unverändert.
  2. Auto-Log: Statuswechsel None->"offline" erzeugt einen art="auto"-JobLog-Eintrag mit dem
     Label "Verfügbarkeit" und dem Anzeige-Text "nicht mehr ausgeschrieben" (NICHT den rohen
     Code); ein PATCH NUR mit availability_checked_at erzeugt KEINEN neuen Log-Eintrag (Design-
     Entscheidung 4 der Spec: reines Systemdatum, kein Wochen-Spam).
  3. Listen-Filter: GET /api/jobs?availability_status=offline liefert den markierten Seed-Job
     (und ausschließlich Zeilen mit genau diesem Wert); die Antwort-Zeilen enthalten beide Felder.
  4. Dashboard: totals.applied_offline zählt Jobs mit Status Beworben/Interview UND
     availability_status="offline"; ein Statuswechsel auf "Absage" nimmt den Job wieder heraus.
  5. Migration: Alt-Schema `job` ohne die zwei Spalten -> _ensure_columns() ergänzt sie additiv
     (Muster test_db_migration.py / test_career_url.py::test_ensure_columns_migriert_alt_schema_
     job_career_url_portal_closed).

Muster: test_career_url.py (Phase 73 — strukturell identisches Feld-Paar-Vorbild) + conftest.py
(client/seed-Fixtures). App-Module werden -- wie in der gesamten Suite (s. conftest.py-Docstring)
-- NIE auf Modulebene importiert, nur innerhalb der Testfunktionen.

Hinweis zu Test 3/4 (Abweichung von der wörtlichen Spec-Formulierung "== 1"/"genau"): die
tmp-SQLite-DB ist SESSION-weit geteilt (conftest.py::_db_ready, scope="session") -- mehrere
Tests, die eigene Seed-Jobs auf availability_status="offline" setzen, akkumulieren in derselben
DB (kein Rollback zwischen Tests). Ein absoluter Vergleich ("== 1") wäre deshalb von der
Ausführungsreihenfolge der Tests abhängig. Stattdessen: Vorher/Nachher-Delta (etabliertes Muster
in dieser Suite, s. test_gesamtprozess_api.py::test_netzwerkgespraech_zaehlt_in_dashboard_
gespraeche_kpi) bzw. eine Mitgliedschafts-/Kontrakt-Prüfung statt exakter Listenlänge. Deckt
dieselbe fachliche Aussage ab, robust gegen Testreihenfolge.
"""


# ── A7.1 — PATCH speichert, GET liefert korrekt zurück; ungültiger Wert -> 422 mit Bestandsschutz ──
def test_patch_availability_status_und_checked_at_werden_gespeichert(client, seed):
    job = seed["jobs"][0]
    resp = client.patch(f"/api/jobs/{job.id}", json={
        "availability_status": "offen",
        "availability_checked_at": "2026-08-04",
    })
    assert resp.status_code == 200, resp.text

    nachher = client.get(f"/api/jobs/{job.id}").json()["job"]
    assert nachher["availability_status"] == "offen"
    assert nachher["availability_checked_at"] == "2026-08-04"

    # Ungültiger Wert -> 422, Bestand bleibt unverändert (Muster test_status_validation.py /
    # test_career_url.py::test_portal_closed_normalisierung).
    ungueltig = client.patch(f"/api/jobs/{job.id}", json={"availability_status": "vielleicht"})
    assert ungueltig.status_code == 422, ungueltig.text
    unveraendert = client.get(f"/api/jobs/{job.id}").json()["job"]
    assert unveraendert["availability_status"] == "offen"


# ── A7.2 — Auto-Log bei Statuswechsel, KEIN Log-Eintrag für availability_checked_at allein ──
def test_availability_status_erzeugt_auto_log_checked_at_nicht(client, seed):
    job = seed["jobs"][1]   # frischer Seed-Job: availability_status startet bei None

    resp = client.patch(f"/api/jobs/{job.id}", json={
        "availability_status": "offline",
        "availability_checked_at": "2026-08-04",
    })
    assert resp.status_code == 200, resp.text

    log = client.get(f"/api/jobs/{job.id}/log").json()
    auto_eintraege = [e["eintrag"] for e in log if e["art"] == "auto"]
    assert any("Verfügbarkeit" in e and "nicht mehr ausgeschrieben" in e for e in auto_eintraege), log

    anzahl_vorher = len(log)
    # NUR availability_checked_at ändern (wöchentlicher Re-Check ohne Statuswechsel) -> KEIN
    # neuer Log-Eintrag (Design-Entscheidung 4: reines Systemdatum, kein Wochen-Spam).
    resp2 = client.patch(f"/api/jobs/{job.id}", json={"availability_checked_at": "2026-08-11"})
    assert resp2.status_code == 200, resp2.text
    log_nachher = client.get(f"/api/jobs/{job.id}/log").json()
    assert len(log_nachher) == anzahl_vorher, log_nachher


# ── A7.3 — Listen-Filter liefert den markierten Seed-Job, beide Felder in der Antwort-Zeile ──
def test_listen_filter_availability_status(client, seed):
    job = seed["jobs"][0]
    resp = client.patch(f"/api/jobs/{job.id}", json={
        "availability_status": "offline",
        "availability_checked_at": "2026-08-04",
    })
    assert resp.status_code == 200, resp.text

    r = client.get("/api/jobs", params={"availability_status": "offline"})
    assert r.status_code == 200, r.text
    rows = r.json()

    ids = {row["id"] for row in rows}
    assert job.id in ids, rows
    # Filter-Vertrag: JEDE zurückgegebene Zeile trägt tatsächlich "offline" (kein Leck anderer Werte).
    assert all(row["availability_status"] == "offline" for row in rows), rows

    zeile = next(row for row in rows if row["id"] == job.id)
    assert zeile["availability_status"] == "offline"
    assert zeile["availability_checked_at"] == "2026-08-04"


# ── A7.4 — Dashboard: totals.applied_offline zählt Beworben/Interview + offline, Absage nicht ──
def test_dashboard_applied_offline(client, seed):
    job = seed["jobs"][0]
    assert job.status == "Beworben"

    vorher = client.get("/api/dashboard").json()["totals"]["applied_offline"]

    resp = client.patch(f"/api/jobs/{job.id}", json={
        "availability_status": "offline",
        "availability_checked_at": "2026-08-04",
    })
    assert resp.status_code == 200, resp.text
    nachher = client.get("/api/dashboard").json()["totals"]["applied_offline"]
    assert nachher == vorher + 1

    # Status -> Absage: keine "laufende" Bewerbung mehr, zählt nicht mehr mit (Design-Entscheidung 3).
    resp2 = client.patch(f"/api/jobs/{job.id}", json={"status": "Absage"})
    assert resp2.status_code == 200, resp2.text
    danach = client.get("/api/dashboard").json()["totals"]["applied_offline"]
    assert danach == vorher


# ── A7.5 — Migration: Alt-Schema ohne die zwei Spalten ──────────────────────────────────────────
def test_ensure_columns_migriert_alt_schema_job_availability(tmp_path, monkeypatch):
    """Analog test_career_url.py::test_ensure_columns_migriert_alt_schema_job_career_url_
    portal_closed -- eigene throwaway-SQLite-Datei (nicht die geteilte Session-tmp-DB aus
    conftest.py, da hier das Roh-Schema manipuliert wird). `job` wird durch ein Alt-Schema OHNE
    availability_status/availability_checked_at ersetzt; _ensure_columns() muss beide Spalten
    additiv ergänzen. Beide Felder sind nullable OHNE SQL-DEFAULT (anders als portal_closed) --
    die Bestandszeile bekommt für beide NULL, nicht 0."""
    import sqlite3
    from sqlmodel import create_engine
    import app.db as db_modul

    db_path = tmp_path / "isoliert.sqlite"
    ersatz_engine = create_engine(f"sqlite:///{db_path}", echo=False,
                                  connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_modul, "engine", ersatz_engine)

    db_modul.init_db()   # volles modernes Schema anlegen ...

    # ... dann job durch ein Alt-Schema OHNE availability_status/availability_checked_at ersetzen.
    conn = sqlite3.connect(str(db_path))
    conn.execute("DROP TABLE job")
    conn.execute("CREATE TABLE job (id INTEGER PRIMARY KEY, title TEXT, dedup_key TEXT, found_date TEXT)")
    conn.execute("INSERT INTO job (id, title, dedup_key, found_date) VALUES (1, 'Alter Job', 'k1', '2026-01-01')")
    conn.commit()
    spalten_vorher = {r[1] for r in conn.execute("PRAGMA table_info(job)")}
    conn.close()
    assert "availability_status" not in spalten_vorher
    assert "availability_checked_at" not in spalten_vorher

    db_modul._ensure_columns()

    conn = sqlite3.connect(str(db_path))
    try:
        spalten_nachher = {r[1] for r in conn.execute("PRAGMA table_info(job)")}
        assert "availability_status" in spalten_nachher
        assert "availability_checked_at" in spalten_nachher
        zeile = conn.execute(
            "SELECT availability_status, availability_checked_at FROM job WHERE id = 1"
        ).fetchone()
    finally:
        conn.close()
    assert zeile == (None, None)
