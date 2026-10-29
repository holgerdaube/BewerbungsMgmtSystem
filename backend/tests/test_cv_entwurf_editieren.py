"""CV-Entwurf auch nach dem Erstellen editierbar (P2-45, 25.09.2026).

ANLASS (Rückmeldung): „Wenn ich einen CV ‚neu erstellen‘ möchte, dann soll das Editor-Fenster wieder
geöffnet werden … Ich benötige dieses Fenster, um Änderungen zu machen." Bis dahin antwortete
`PATCH /api/cv-versions/{id}/entwurf` bei `status=fertig` mit 409.

Warum das Gate weg darf, steht im Docstring des Endpunkts: `cv_export.entwurf_anwenden()`
schreibt in `cv.file_path` — nach dem Export die FERTIGE Datei —, und `export()` erkennt seinen
eigenen Zielnamen, ist also idempotent. Dieser Endpunkt selbst fasst ohnehin keine Datei an,
sondern nur `entwurf_text`.

Synthetische Daten (T3), App-Importe nur in den Testfunktionen (conftest.py-Konvention).
"""
import json
import uuid

import pytest


def _job_mit_cv(session, status):
    from app.models import CVVersion, Job

    job = Job(company_name=f"P245 AG {uuid.uuid4().hex[:6]}", title="Teststelle",
              status="Beworben", dedup_key=uuid.uuid4().hex)
    session.add(job)
    session.commit()
    session.refresh(job)
    cv = CVVersion(job_id=job.id, language="de", kind="tailored", status=status,
                   file_path="outputs/cv/synthetisch.docx",
                   entwurf_text=json.dumps([{"i": 0, "text": "Alt"}], ensure_ascii=False))
    session.add(cv)
    session.commit()
    session.refresh(cv)
    return job, cv


@pytest.mark.parametrize("status", ["entwurf", "fertig"])
def test_patch_speichert_in_jedem_status(session, client, status):
    """Der Kern von P2-45: Eine fertige Version nimmt Edits genauso an wie ein Entwurf."""
    from app.models import CVVersion

    _, cv = _job_mit_cv(session, status)

    antwort = client.patch(f"/api/cv-versions/{cv.id}/entwurf",
                           json={"entwurf_text": [{"i": 0, "text": "Neu formuliert"}]})

    assert antwort.status_code == 200, antwort.text
    session.expire_all()
    gespeichert = json.loads(session.get(CVVersion, cv.id).entwurf_text)
    assert gespeichert == [{"i": 0, "text": "Neu formuliert"}]


def test_patch_laesst_dateien_und_status_unberuehrt(session, client):
    """Gespeichert wird NUR der Text — Word/PDF entstehen erst im nächsten `cv-erstellen`-Lauf.
    Bliebe hier ein Statuswechsel zurück, verlöre die Workflow-Karte ihre Aussage."""
    from app.models import CVVersion

    _, cv = _job_mit_cv(session, "fertig")

    client.patch(f"/api/cv-versions/{cv.id}/entwurf", json={"entwurf_text": [{"i": 0, "text": "X"}]})

    session.expire_all()
    frisch = session.get(CVVersion, cv.id)
    assert frisch.status == "fertig"
    assert frisch.file_path == "outputs/cv/synthetisch.docx"


def test_patch_ohne_feld_liefert_422(session, client):
    _, cv = _job_mit_cv(session, "fertig")

    assert client.patch(f"/api/cv-versions/{cv.id}/entwurf", json={}).status_code == 422


def test_patch_auf_unbekannte_version_liefert_404(client):
    assert client.patch("/api/cv-versions/99999999/entwurf",
                        json={"entwurf_text": []}).status_code == 404


def test_cv_entwurf_endpunkt_liefert_auch_fertige_version(session, client):
    """Gegenstück im Lesepfad: `cv-erstellen` Schritt 1 holt die Row statusunabhängig — sonst
    fände ein erneuter Lauf den gerade bearbeiteten Text nicht."""
    job, cv = _job_mit_cv(session, "fertig")

    antwort = client.get(f"/api/jobs/{job.id}/cv-entwurf")

    assert antwort.status_code == 200
    assert antwort.json()["id"] == cv.id
