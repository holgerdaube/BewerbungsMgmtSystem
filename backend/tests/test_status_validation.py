"""P2-6 (Phase 67F): PATCH /api/jobs/{id} und PATCH /api/interviews/{id} nahmen bisher JEDEN
String als `status` an. Ein Tippfehler/Fremdwert fiel dann still aus TERMINAL_STATUSES, dem
Dashboard-Funnel und der Button-Anzeige heraus. Jetzt: feste erlaubte Wertemenge, 422 bei
Abweichung (Muster `update_einstellungen`).

Die beiden Wertemengen (main.py::ALLOWED_JOB_STATUSES / ALLOWED_INTERVIEW_STATUSES) wurden aus
der LIVE-Bestandsanalyse UND den frontend/src/pages/JobDetail.tsx-Buttons abgeleitet, NICHT nur
aus normalize.norm_status() (der deckt nur 8 von 10 Job-Werten ab, "Interview"/"Angebot" fehlen
dort) — s. Baubericht Phase 67F für den vollen Beleg."""
import pytest

from app.main import ALLOWED_INTERVIEW_STATUSES, ALLOWED_JOB_STATUSES


# ── Job.status ──────────────────────────────────────────────────────────────────────────────
def test_update_job_lehnt_unbekannten_status_ab(client, seed):
    job = seed["jobs"][0]
    resp = client.patch(f"/api/jobs/{job.id}", json={"status": "Quatschwert"})
    assert resp.status_code == 422, resp.text

    # Bestand darf durch den abgelehnten Versuch nicht veraendert worden sein.
    # GET /api/jobs/{id} liefert ein Verbund-Objekt {"job": {...}, "company": {...}, ...}.
    nachher = client.get(f"/api/jobs/{job.id}").json()
    assert nachher["job"]["status"] == job.status


@pytest.mark.parametrize("status", sorted(ALLOWED_JOB_STATUSES))
def test_update_job_akzeptiert_jeden_erlaubten_status(client, seed, status):
    """Bestandsschutz: ALLE 10 Werte (auch die aktuell im Bestand mit 0 Zeilen vorkommenden wie
    'Angebot' — der Skill angebot-vergleich fragt `GET /api/jobs?status=Angebot` ab) muessen
    weiterhin per PATCH setzbar sein. Eine zu enge Menge wuerde genau diesen Skill beim ersten
    echten Versuch brechen."""
    job = seed["jobs"][0]
    resp = client.patch(f"/api/jobs/{job.id}", json={"status": status})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == status


def test_update_job_ohne_status_im_payload_bleibt_unberuehrt(client, seed):
    """Die Validierung darf nur greifen, wenn 'status' ueberhaupt im Payload steht -- ein PATCH,
    das nur andere Felder aendert (z. B. notes), darf nicht ploetzlich 422 werfen."""
    job = seed["jobs"][0]
    resp = client.patch(f"/api/jobs/{job.id}", json={"notes": "nur eine Notiz"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["notes"] == "nur eine Notiz"


def test_update_job_status_fehlermeldung_nennt_erlaubte_werte(client, seed):
    job = seed["jobs"][0]
    resp = client.patch(f"/api/jobs/{job.id}", json={"status": "Erfunden"})
    assert resp.status_code == 422
    for wert in ALLOWED_JOB_STATUSES:
        assert wert in resp.text, f"'{wert}' fehlt in der 422-Fehlermeldung: {resp.text}"


# ── Interview.status ────────────────────────────────────────────────────────────────────────
def _interview_anlegen(client, job_id, status="Geplant"):
    resp = client.post(f"/api/jobs/{job_id}/interviews", json={"art": "HR-Screen", "status": status})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_update_interview_lehnt_unbekannten_status_ab(client, seed):
    job = seed["jobs"][0]
    iv = _interview_anlegen(client, job.id)
    resp = client.patch(f"/api/interviews/{iv['id']}", json={"status": "Verschoben"})
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize("status", sorted(ALLOWED_INTERVIEW_STATUSES))
def test_update_interview_akzeptiert_jeden_erlaubten_status(client, seed, status):
    job = seed["jobs"][0]
    iv = _interview_anlegen(client, job.id)
    resp = client.patch(f"/api/interviews/{iv['id']}", json={"status": status})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == status


def test_job_und_interview_status_sind_unterschiedliche_wertemengen(client, seed):
    """Q6/Auftragsvorgabe: Interview.status ist eine ANDERE (kleinere) Menge als Job.status --
    ein Job-Statuswert darf am Interview nicht akzeptiert werden und umgekehrt."""
    job = seed["jobs"][0]
    iv = _interview_anlegen(client, job.id)

    # "Interview" ist ein gueltiger JOB-Status, aber KEIN gueltiger Interview-Status.
    assert "Interview" in ALLOWED_JOB_STATUSES
    assert "Interview" not in ALLOWED_INTERVIEW_STATUSES
    resp = client.patch(f"/api/interviews/{iv['id']}", json={"status": "Interview"})
    assert resp.status_code == 422, resp.text

    # "Absolviert" ist ein gueltiger INTERVIEW-Status, aber KEIN gueltiger Job-Status.
    assert "Absolviert" in ALLOWED_INTERVIEW_STATUSES
    assert "Absolviert" not in ALLOWED_JOB_STATUSES
    resp = client.patch(f"/api/jobs/{job.id}", json={"status": "Absolviert"})
    assert resp.status_code == 422, resp.text


# ── create_interview (P2-6-Schwesterstelle) ────────────────────────────────────────────────────
def test_create_interview_lehnt_unbekannten_status_ab(client, seed):
    """Schwesterstelle (Q1): dieselbe Tabelle/dasselbe Feld wie update_interview, nur beim
    Anlegen statt beim Aendern -- muss dieselbe Validierung bekommen, sonst bliebe genau EIN
    Einstiegspunkt fuer denselben Fehler offen."""
    job = seed["jobs"][0]
    resp = client.post(f"/api/jobs/{job.id}/interviews", json={"art": "HR-Screen", "status": "Storniert"})
    assert resp.status_code == 422, resp.text


def test_create_interview_ohne_status_nutzt_default(client, seed):
    """Regression: die Skills (interview-vorbereiten) senden 'status':'Geplant' explizit, aber
    ein Aufruf ganz ohne status-Feld darf nicht ploetzlich scheitern (Modell-Default 'Geplant')."""
    job = seed["jobs"][0]
    resp = client.post(f"/api/jobs/{job.id}/interviews", json={"art": "HR-Screen"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "Geplant"
