"""Phase 69, Stufe B: API-Tests für die neuen Endpunkte rund um Gesamtprozess-KPIs.

Wie in conftest.py beschrieben: KEINE app.*-Importe auf Modulebene, nur in Testfunktionen.
Deckt ab: PATCH outreach.bewerbung_datum, PATCH/POST interview.gegenueber+vor_ort (inkl.
Validierung), sowie das neue CRUD für /api/netzwerk-gespraeche (Gespräche ohne Stelle).
Der Dashboard-Vertrag selbst (gesamtprozess-Block, Schlüsselmenge) wird bereits in
test_api_smoke.py::test_dashboard_ok_und_erwartete_keys geprüft — hier ergänzend ein
Zahlen-Beleg, dass ein frisch angelegtes NetzwerkGespraech tatsächlich in der Dashboard-KPI
"Gespräche gesamt" auftaucht (Rundreise-Test statt nur Vertrags-Test)."""


def _outreach_anlegen(session, unternehmen="Firma X"):
    from app.models import Outreach
    o = Outreach(unternehmen=unternehmen, kontakt="Kontakt X", typ="Warmer Kontakt", status="Initiated")
    session.add(o)
    session.commit()
    session.refresh(o)
    return o


def _headhunter_anlegen(session, firma="Such AG"):
    from app.models import Headhunter
    hh = Headhunter(firma=firma, ansprechpartner="Frau Muster")
    session.add(hh)
    session.commit()
    session.refresh(hh)
    return hh


# ── Outreach.bewerbung_datum ─────────────────────────────────────────────────────────────────
def test_update_outreach_akzeptiert_bewerbung_datum(client, session):
    o = _outreach_anlegen(session)
    resp = client.patch(f"/api/outreach/{o.id}", json={"bewerbung_datum": "2026-05-01"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["bewerbung_datum"] == "2026-05-01"


def test_update_outreach_next_action_datum_wiedervorlage(client, session):
    """Simuliert den Dashboard-Button "Wiedervorlage +7 Tage" — derselbe PATCH-Weg wie die
    bestehende Fälligkeitspflege auf /outreach (next_action_datum), nur ausgelöst vom
    Keine-Reaktion-Drilldown."""
    o = _outreach_anlegen(session)
    resp = client.patch(f"/api/outreach/{o.id}", json={"next_action_datum": "2026-08-03"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["next_action_datum"] == "2026-08-03"


# ── Interview.gegenueber / vor_ort ────────────────────────────────────────────────────────────
def test_create_interview_mit_gegenueber_und_vor_ort(client, seed):
    job = seed["jobs"][0]
    resp = client.post(f"/api/jobs/{job.id}/interviews",
                        json={"art": "Fachgespräch", "gegenueber": "Hiring Manager", "vor_ort": True})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["gegenueber"] == "Hiring Manager"
    assert data["vor_ort"] is True


def test_create_interview_lehnt_unbekanntes_gegenueber_ab(client, seed):
    job = seed["jobs"][0]
    resp = client.post(f"/api/jobs/{job.id}/interviews",
                        json={"art": "HR-Screen", "gegenueber": "Praktikant"})
    assert resp.status_code == 422, resp.text


def test_interview_gegenueber_erlaubt_kein_netzwerk_wert(client, seed):
    """Interview kennt (anders als NetzwerkGespraech) den Zusatzwert "Netzwerk" NICHT —
    verlangt zwingend eine Stelle, ein reiner Netzwerk-Kontakt ohne Stelle gehört dorthin."""
    job = seed["jobs"][0]
    resp = client.post(f"/api/jobs/{job.id}/interviews",
                        json={"art": "Sonstiges", "gegenueber": "Netzwerk"})
    assert resp.status_code == 422, resp.text


def test_update_interview_setzt_gegenueber_und_vor_ort(client, seed):
    job = seed["jobs"][0]
    iv = client.post(f"/api/jobs/{job.id}/interviews", json={"art": "HR-Screen"}).json()
    resp = client.patch(f"/api/interviews/{iv['id']}", json={"gegenueber": "Recruiter", "vor_ort": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["gegenueber"] == "Recruiter"
    assert resp.json()["vor_ort"] is True


# ── /api/netzwerk-gespraeche ──────────────────────────────────────────────────────────────────
def test_netzwerkgespraech_anlegen_ohne_datum_422(client, session):
    resp = client.post("/api/netzwerk-gespraeche", json={"person": "Herr Ohne Datum"})
    assert resp.status_code == 422, resp.text


def test_netzwerkgespraech_anlegen_unbekannter_outreach_id_404(client, session):
    resp = client.post("/api/netzwerk-gespraeche", json={"datum": "2026-07-20", "outreach_id": 999999})
    assert resp.status_code == 404, resp.text


def test_netzwerkgespraech_roundtrip_outreach(client, session):
    """POST -> GET (gefiltert nach outreach_id) -> DELETE -> GET wieder leer. Kein Testdaten-
    Rückstand nach dem Test (Aufruf-Konvention der Bau-Aufgabe)."""
    o = _outreach_anlegen(session)
    resp = client.post("/api/netzwerk-gespraeche", json={
        "datum": "2026-07-20", "person": "Frau Testkontakt", "unternehmen": o.unternehmen,
        "gegenueber": "Netzwerk", "vor_ort": True, "outreach_id": o.id, "notiz": "Telefonat",
    })
    assert resp.status_code == 200, resp.text
    ng = resp.json()
    assert ng["outreach_id"] == o.id
    assert ng["vor_ort"] is True

    listing = client.get(f"/api/netzwerk-gespraeche?outreach_id={o.id}").json()
    assert any(x["id"] == ng["id"] for x in listing)

    resp = client.delete(f"/api/netzwerk-gespraeche/{ng['id']}")
    assert resp.status_code == 200, resp.text

    listing_danach = client.get(f"/api/netzwerk-gespraeche?outreach_id={o.id}").json()
    assert all(x["id"] != ng["id"] for x in listing_danach)


def test_netzwerkgespraech_roundtrip_headhunter(client, session):
    hh = _headhunter_anlegen(session)
    resp = client.post("/api/netzwerk-gespraeche", json={
        "datum": "2026-07-15", "person": hh.ansprechpartner, "unternehmen": hh.firma,
        "gegenueber": "Headhunter", "headhunter_id": hh.id,
    })
    assert resp.status_code == 200, resp.text
    ng = resp.json()

    listing = client.get(f"/api/netzwerk-gespraeche?headhunter_id={hh.id}").json()
    assert any(x["id"] == ng["id"] for x in listing)

    client.delete(f"/api/netzwerk-gespraeche/{ng['id']}")


def test_netzwerkgespraech_lehnt_unbekanntes_gegenueber_ab(client, session):
    resp = client.post("/api/netzwerk-gespraeche", json={"datum": "2026-07-20", "gegenueber": "Praktikant"})
    assert resp.status_code == 422, resp.text


def test_netzwerkgespraech_erlaubt_zusatzwert_netzwerk(client, session):
    """Anders als bei Interview ist "Netzwerk" hier ein GÜLTIGER Wert (reiner Netzwerk-Kontakt,
    kein Recruiter/Hiring Manager/Headhunter)."""
    resp = client.post("/api/netzwerk-gespraeche", json={"datum": "2026-07-20", "gegenueber": "Netzwerk"})
    assert resp.status_code == 200, resp.text
    client.delete(f"/api/netzwerk-gespraeche/{resp.json()['id']}")


def test_netzwerkgespraech_loeschen_unbekannte_id_404(client, session):
    resp = client.delete("/api/netzwerk-gespraeche/999999")
    assert resp.status_code == 404, resp.text


def test_netzwerkgespraech_zaehlt_in_dashboard_gespraeche_kpi(client, session):
    """Rundreise-Beleg: ein frisch angelegtes NetzwerkGespraech erhöht die Dashboard-KPI
    "Gespräche gesamt" (gesamtprozess.gespraeche.wert) sofort um 1 -- EINE Berechnung
    (app.gesamtprozess), kein separat gepflegter Zähler."""
    vorher = client.get("/api/dashboard").json()["gesamtprozess"]["gespraeche"]["wert"]
    resp = client.post("/api/netzwerk-gespraeche", json={
        "datum": "2026-07-10", "person": "Herr Dashboard-Test", "gegenueber": "Headhunter",
    })
    ng = resp.json()
    nachher = client.get("/api/dashboard").json()["gesamtprozess"]["gespraeche"]["wert"]
    assert nachher == vorher + 1
    client.delete(f"/api/netzwerk-gespraeche/{ng['id']}")
