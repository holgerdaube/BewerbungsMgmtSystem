"""Manuelles Anlegen einer Stelle: Warnung bei bekannter URL oder Firma+Titel, gelöschte Stellen zählen nicht."""
import uuid

import pytest

from app import normalize as N


def _stelle(**felder):
    kennung = uuid.uuid4().hex[:8]
    return {"company_name": f"Probefirma {kennung} GmbH", "title": f"Rolle {kennung}", **felder}


@pytest.mark.parametrize("url,erwartet", [
    ("https://www.linkedin.com/jobs/view/senior-rolle-bei-firma-4312345678/?trk=x", "linkedin.com/jobs/view/4312345678"),
    ("https://de.linkedin.com/jobs/view/4312345678", "linkedin.com/jobs/view/4312345678"),
    ("https://www.linkedin.com/jobs/search/?currentJobId=4312345678&keywords=x", "linkedin.com/jobs/view/4312345678"),
    ("https://www.example.com/stelle/1/?utm_source=a&id=7#x", "example.com/stelle/1?id=7"),
    ("HTTP://Example.com/Stelle/", "example.com/Stelle"),
    ("example.com/stelle", "example.com/stelle"),
    ("  ", None), (None, None),
])
def test_url_vergleich(url, erwartet):
    assert N.url_vergleich(url) == erwartet


def test_url_bereits_erfasst_nennt_die_stelle(client):
    url = f"https://example.com/stelle/{uuid.uuid4().hex}"
    erste = client.post("/api/jobs", json=_stelle(url=url)).json()
    assert erste["existing"] is False

    zweite = client.post("/api/jobs", json=_stelle(url=f"{url}/?utm_source=mail")).json()
    assert zweite["existing"] is True and zweite["art"] == "url"
    assert zweite["job"]["id"] == erste["job"]["id"]


def test_firma_und_titel_bereits_erfasst_auch_in_anderer_schreibweise(client):
    daten = _stelle()
    erste = client.post("/api/jobs", json=daten).json()

    zweite = client.post("/api/jobs", json={"company_name": daten["company_name"].replace(" GmbH", "").upper(),
                                            "title": f"  {daten['title']} (m/w/d) "}).json()
    assert zweite["existing"] is True and zweite["art"] == "firma_titel"
    assert zweite["job"]["id"] == erste["job"]["id"]


def test_gleiche_firma_anderer_titel_ist_keine_dublette(client):
    daten = _stelle()
    client.post("/api/jobs", json=daten)
    assert client.post("/api/jobs", json={**daten, "title": daten["title"] + " Zwei"}).json()["existing"] is False


def test_geloeschte_stelle_wird_ignoriert_auch_mehrfach(client):
    url = f"https://example.com/stelle/{uuid.uuid4().hex}"
    daten = _stelle(url=url)
    ids = []
    for _ in range(3):
        antwort = client.post("/api/jobs", json=daten).json()
        assert antwort["existing"] is False, "die gelöschte Stelle darf das Anlegen nicht blockieren"
        assert antwort["job"]["id"] not in ids and antwort["job"]["deleted_at"] is None
        ids.append(antwort["job"]["id"])
        assert client.get("/api/jobs/dublette", params={"url": url}).json()["job"]["id"] == antwort["job"]["id"]
        assert client.delete(f"/api/jobs/{antwort['job']['id']}").status_code == 200
    assert client.get("/api/jobs/dublette", params={"url": url}).json() == {"art": None, "job": None}


def test_vorabpruefung(client):
    url = f"https://example.com/stelle/{uuid.uuid4().hex}"
    daten = _stelle(url=url)
    job_id = client.post("/api/jobs", json=daten).json()["job"]["id"]

    nur_url = client.get("/api/jobs/dublette", params={"url": url}).json()
    assert nur_url["art"] == "url" and nur_url["job"]["id"] == job_id
    assert set(nur_url["job"]) == {"id", "company_name", "title", "status"}

    firma_titel = client.get("/api/jobs/dublette", params={"company_name": daten["company_name"], "title": daten["title"]}).json()
    assert firma_titel["art"] == "firma_titel" and firma_titel["job"]["id"] == job_id

    # Nur die Firma allein reicht nicht für eine Warnung
    assert client.get("/api/jobs/dublette", params={"company_name": daten["company_name"]}).json()["job"] is None
