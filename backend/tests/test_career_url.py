"""Phase 73 — Karriereseiten-Fallback bei geschlossenen Portal-Stellen: zwei neue Job-Felder
`career_url` (TEXT, nullable) und `portal_closed` (INTEGER DEFAULT 0), s.
tasks/spec_phase73_karriereseiten_check.md Stufe A (Backend).

Deckt A4 der Bau-Spec ab:
  1. PATCH speichert career_url/portal_closed, GET /api/jobs/{id} liefert sie korrekt zurueck.
     Zusaetzlich (Harte Regel des Auftrags): eine career_url-Aenderung darf verified_at/
     verify_note NICHT nullen -- das gilt nur fuer die Original-URL `url`
     (main.py::update_job, "Verifikation zuruecksetzen"-Block).
  2. portal_closed normalisiert robust (bool/int/str) auf 0/1; ein ungueltiger Wert -> 422,
     Bestand bleibt unveraendert (Muster test_status_validation.py).
  3. career_url- und portal_closed-Aenderungen erzeugen einen art="auto"-JobLog-Eintrag;
     portal_closed wird dort als Ja/Nein formatiert (Design-Entscheidung 5 der Spec), NIE als 1/0.
  4. Migration: Alt-Schema `job` ohne die zwei Spalten -> _ensure_columns() ergaenzt sie additiv
     (Muster test_db_migration.py::test_ensure_columns_migriert_alt_schema_cvversion_status).

Muster: test_status_validation.py (client/seed-Fixtures, Assertion-Stil) + test_db_migration.py
(isolierter throwaway-Engine fuer den Migrationstest). App-Module werden -- wie in der gesamten
Suite (s. conftest.py-Docstring) -- NIE auf Modulebene importiert, nur innerhalb der Testfunktionen/
lokal in den Testkoerpern.
"""


# ── A4.1 — PATCH speichert, GET liefert korrekt zurueck; career_url nullt verified_at/verify_note NICHT ──
def test_patch_career_url_und_portal_closed_werden_gespeichert(client, seed):
    job = seed["jobs"][0]
    # verified_at/verify_note vorbelegen (Muster Phase 14 D: url + verify_note IM SELBEN Payload,
    # damit update_job die Verifikation NICHT zuruecksetzt) -- Referenzstand fuer die Harte Regel unten.
    vorbelegen = client.patch(f"/api/jobs/{job.id}", json={
        "url": f"https://example.com/job/{job.id}-urspruenglich",
        "verified_at": "2026-08-01T10:00:00",
        "verify_note": "BESTÄTIGT: Anzeige aktiv",
    })
    assert vorbelegen.status_code == 200, vorbelegen.text

    resp = client.patch(f"/api/jobs/{job.id}", json={
        "career_url": f"https://firma.example.com/karriere/stelle-{job.id}",
        "portal_closed": 1,
    })
    assert resp.status_code == 200, resp.text

    nachher = client.get(f"/api/jobs/{job.id}").json()["job"]
    assert nachher["career_url"] == f"https://firma.example.com/karriere/stelle-{job.id}"
    assert nachher["portal_closed"] == 1
    # Harte Regel: career_url nullt verified_at/verify_note NICHT (nur `url` tut das).
    assert nachher["verified_at"] == "2026-08-01T10:00:00"
    assert nachher["verify_note"] == "BESTÄTIGT: Anzeige aktiv"


# ── A4.2 — robuste 0/1-Normalisierung ───────────────────────────────────────────────────────────
def test_portal_closed_normalisierung(client, seed):
    job = seed["jobs"][1]
    resp = client.patch(f"/api/jobs/{job.id}", json={"portal_closed": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["portal_closed"] == 1

    resp2 = client.patch(f"/api/jobs/{job.id}", json={"portal_closed": "0"})
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["portal_closed"] == 0

    # Ungueltiger Wert -> 422, Bestand bleibt unveraendert (Muster test_update_job_lehnt_unbekannten_status_ab).
    vorher = client.get(f"/api/jobs/{job.id}").json()["job"]["portal_closed"]
    ungueltig = client.patch(f"/api/jobs/{job.id}", json={"portal_closed": "vielleicht"})
    assert ungueltig.status_code == 422, ungueltig.text
    nachher = client.get(f"/api/jobs/{job.id}").json()["job"]["portal_closed"]
    assert nachher == vorher


# ── A4.3 — Auto-Log ─────────────────────────────────────────────────────────────────────────────
def test_career_url_und_portal_closed_erzeugen_auto_log_eintrag(client, seed):
    job = seed["jobs"][0]
    resp = client.patch(f"/api/jobs/{job.id}", json={
        "career_url": f"https://firma.example.com/karriere/stelle-{job.id}-neu",
        "portal_closed": 1,
    })
    assert resp.status_code == 200, resp.text

    log = client.get(f"/api/jobs/{job.id}/log").json()
    auto_eintraege = [e["eintrag"] for e in log if e["art"] == "auto"]
    assert any("Karriereseite" in e for e in auto_eintraege), log
    # Design-Entscheidung 5: Ja/Nein im Log, NICHT die rohen 0/1-Werte.
    assert any("Portal geschlossen: Nein → Ja" in e for e in auto_eintraege), log


# ── A4.4 — Migration: Alt-Schema ohne die zwei Spalten ────────────────────────────────────────────
def test_ensure_columns_migriert_alt_schema_job_career_url_portal_closed(tmp_path, monkeypatch):
    """Analog test_db_migration.py::test_ensure_columns_migriert_alt_schema_cvversion_status --
    eigene throwaway-SQLite-Datei (nicht die geteilte Session-tmp-DB aus conftest.py, da hier das
    Roh-Schema manipuliert wird). `job` wird durch ein Alt-Schema OHNE career_url/portal_closed
    ersetzt; _ensure_columns() muss beide Spalten additiv ergaenzen. Die Bestandszeile bekommt fuer
    portal_closed den SQL-DEFAULT 0 (NICHT NULL, Muster interview.vor_ort aus Phase 69)."""
    import sqlite3
    from sqlmodel import create_engine
    import app.db as db_modul

    db_path = tmp_path / "isoliert.sqlite"
    ersatz_engine = create_engine(f"sqlite:///{db_path}", echo=False,
                                  connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_modul, "engine", ersatz_engine)

    db_modul.init_db()   # volles modernes Schema anlegen ...

    # ... dann job durch ein Alt-Schema OHNE career_url/portal_closed ersetzen (minimal, wie vor Phase 73).
    conn = sqlite3.connect(str(db_path))
    conn.execute("DROP TABLE job")
    conn.execute("CREATE TABLE job (id INTEGER PRIMARY KEY, title TEXT, dedup_key TEXT, found_date TEXT)")
    conn.execute("INSERT INTO job (id, title, dedup_key, found_date) VALUES (1, 'Alter Job', 'k1', '2026-01-01')")
    conn.commit()
    spalten_vorher = {r[1] for r in conn.execute("PRAGMA table_info(job)")}
    conn.close()
    assert "career_url" not in spalten_vorher
    assert "portal_closed" not in spalten_vorher

    db_modul._ensure_columns()

    conn = sqlite3.connect(str(db_path))
    try:
        spalten_nachher = {r[1] for r in conn.execute("PRAGMA table_info(job)")}
        assert "career_url" in spalten_nachher
        assert "portal_closed" in spalten_nachher
        zeile = conn.execute("SELECT career_url, portal_closed FROM job WHERE id = 1").fetchone()
    finally:
        conn.close()
    assert zeile == (None, 0)
