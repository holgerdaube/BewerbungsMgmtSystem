"""P2-51 (V7) — Umkreis dynamisch statt fest „Frankfurt +100km“.

Deckt ab:
  1. `stadt_kurzform()` gegen die V7-Tabelle der Bau-Spec.
  2. `umkreis_label()`: leere Stadt -> None, fehlender/nicht-positiver Radius -> 100.
  3. `baue_managed()`: kein Bucket ohne Stadt (auch wenn „aktiv“ gesetzt ist, KEIN
     Frankfurt-Rückfall mehr); ein vorhandener Bucket trägt `stadt`/`umkreis_km` als eigene
     Felder (nicht nur im Schlüssel/in `regionen`).
  4. `seed_aus_yaml()`: frische Installation (kein Umkreis-Bucket) -> leere Stadt; ein ALTER
     Kopf ohne `stadt`/`umkreis_km`-Felder -> Rückfall auf `regionen[0]` bzw. die Zahl im
     Bucket-Schlüssel.
  5. Regressionsanker: „Frankfurt am Main“, 100 km ergibt weiter exakt
     „Frankfurt +100km“ — als reiner Funktionsaufruf UND über `GET /api/einstellungen`.
  6. `PATCH /api/einstellungen`: eine Umbenennung (Stadt und/oder Radius ändern sich) stellt
     JEDE Stelle/Firma mit der alten Bezeichnung auf die neue um — auch im Papierkorb —, meldet
     `umbenennung` und schreibt den neuen Bucket-Schlüssel in den YAML-Kopf; ohne Wechsel
     passiert nichts; ein aktiver Umkreis ohne Stadt bzw. mit Radius außerhalb 1..1000 ist 422.
  7. `tab_normalisieren()` — angewendet in `pipeline.ingest`, `POST /api/jobs` und
     `PATCH /api/jobs/{id}`: „remote“/„deutschlandweit“ in jeder Schreibung, eine mitgeschickte
     alte Umkreis-Bezeichnung wird auf die aktuelle abgebildet.
  8. Lehre Phase 87: ein Teil-Save (nur `suchbereich`, nur `modelle`) gegen eine BESTEHENDE Zeile
     lässt alle anderen Felder unverändert.

WICHTIG — Test-Isolation (Muster `test_einstellungen_portale.py`/`test_bewerbungspaket_optional.py`):
  - `PATCH /api/einstellungen` schreibt `config/suchprofile.yaml` über
    `suchprofil.regenerieren()` — das autouse-Fixture unten leitet `suchprofil.SUCHPROFILE_PATH`
    IMMER auf eine `tmp_path`-Kopie um, NIE auf die echte Datei.
  - `SuchEinstellung` ist ein echter Singleton (id=1) über die GANZE session-weite tmp-DB hinweg
    (conftest.py::_db_ready, scope="session") — kein Rollback zwischen Tests. Jeder Test setzt
    seine Ausgangslage deshalb selbst über `_einstellung_setzen()`.
  - App-Module werden — wie in der gesamten Suite — NIE auf Modulebene importiert, nur innerhalb
    der Testfunktionen/Fixtures.
"""
import json
import uuid
from datetime import datetime

import pytest


@pytest.fixture(autouse=True)
def _suchprofile_yaml_isoliert(tmp_path, monkeypatch):
    """PFLICHT (Muster test_einstellungen_portale.py): niemals die echte
    config/suchprofile.yaml lesen oder beschreiben."""
    from pipeline import suchprofil

    pfad = tmp_path / "suchprofile.yaml"
    pfad.write_text(suchprofil.MARKER + "\nportale_technik: {}\n", encoding="utf-8")
    monkeypatch.setattr(suchprofil, "SUCHPROFILE_PATH", pfad)
    return pfad


def _reset_einstellungen(session):
    from app.models import SuchEinstellung

    vorhanden = session.get(SuchEinstellung, 1)
    if vorhanden:
        session.delete(vorhanden)
        session.commit()


def _einstellung_setzen(session, *, suchbereich, modelle=None, plaene=None):
    """Setzt die Singleton-Zeile direkt auf eine bekannte Ausgangslage (schneller als eine
    PATCH-Kette) — Muster `test_einstellungen_portale.py::_reset_einstellungen` + Direkt-Insert."""
    from app.models import SuchEinstellung

    _reset_einstellungen(session)
    e = SuchEinstellung(
        id=1, min_mitarbeiter=100,
        suchbereich_json=json.dumps(suchbereich, ensure_ascii=False),
        plaene_json=json.dumps(plaene or [], ensure_ascii=False),
        modelle_json=json.dumps(modelle or {}, ensure_ascii=False),
        portale_json="[]", unterlagen_json="{}",
    )
    session.add(e)
    session.commit()
    session.refresh(e)
    return e


def _job(session, *, tab, region=None, deleted=False):
    from app.models import Company, Job

    firma = f"Beispiel GmbH {uuid.uuid4().hex[:8]}"
    comp = Company(name=firma, region=region)
    session.add(comp)
    session.commit()
    session.refresh(comp)

    j = Job(company_id=comp.id, company_name=firma, title="Testrolle", status="Neu", tab=tab,
            dedup_key=uuid.uuid4().hex,
            deleted_at=datetime.utcnow().isoformat() if deleted else None)
    session.add(j)
    session.commit()
    session.refresh(j)
    return j, comp


FRANKFURT_AKTIV = {"remote": {"aktiv": False}, "deutschlandweit": {"aktiv": False},
                   "umkreis": {"aktiv": True, "stadt": "Frankfurt am Main", "umkreis_km": 100}}


# ── 1. stadt_kurzform (V7-Tabelle) ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("stadt, erwartet", [
    ("Frankfurt am Main", "Frankfurt"),
    ("Bad Homburg vor der Höhe", "Bad Homburg"),
    ("Halle (Saale)", "Halle"),
    ("Freiburg im Breisgau", "Freiburg"),
    ("Mülheim an der Ruhr", "Mülheim"),
    ("Frankfurt/Main", "Frankfurt"),
    ("St. Gallen", "St. Gallen"),
    ("München", "München"),
])
def test_stadt_kurzform_tabelle(stadt, erwartet):
    from pipeline import suchprofil

    assert suchprofil.stadt_kurzform(stadt) == erwartet


# ── 2. umkreis_label ─────────────────────────────────────────────────────────────────────────
def test_umkreis_label_ohne_stadt_ist_none():
    from pipeline import suchprofil

    assert suchprofil.umkreis_label({"stadt": "", "umkreis_km": 100}) is None
    assert suchprofil.umkreis_label({}) is None


def test_umkreis_label_km_fehlt_faellt_auf_100():
    from pipeline import suchprofil

    assert suchprofil.umkreis_label({"stadt": "Köln"}) == "Köln +100km"


def test_umkreis_label_km_null_faellt_auf_100():
    from pipeline import suchprofil

    assert suchprofil.umkreis_label({"stadt": "Köln", "umkreis_km": 0}) == "Köln +100km"


def test_umkreis_label_regressionsanker():
    """Die bisherige Einstellung (Stadt „Frankfurt am Main“, Radius 100) muss weiter exakt
    „Frankfurt +100km“ ergeben — die Kennung, an der viele Stellen hängen."""
    from pipeline import suchprofil

    assert suchprofil.umkreis_label({"stadt": "Frankfurt am Main", "umkreis_km": 100}) == "Frankfurt +100km"


# ── 3. baue_managed: kein Frankfurt-Rückfall, Bucket trägt eigene Felder ───────────────────────
def test_baue_managed_ohne_stadt_erzeugt_trotz_aktiv_keinen_bucket():
    """Bug vor P2-51: `aktiv` ohne Stadt fiel auf „Frankfurt am Main“ zurück. Jetzt: kein Bucket."""
    from pipeline import suchprofil

    managed = suchprofil.baue_managed(100, {"umkreis": {"aktiv": True, "stadt": "", "umkreis_km": 100}}, [])
    assert managed["buckets"] == {}


def test_baue_managed_umkreis_bucket_traegt_stadt_und_km_als_eigene_felder():
    from pipeline import suchprofil

    managed = suchprofil.baue_managed(
        100, {"umkreis": {"aktiv": True, "stadt": "Frankfurt am Main", "umkreis_km": 100}}, [])
    bucket = managed["buckets"]["Frankfurt +100km"]
    assert bucket["regionen"] == ["Frankfurt am Main"]
    assert bucket["stadt"] == "Frankfurt am Main"
    assert bucket["umkreis_km"] == 100


# ── 4. seed_aus_yaml ─────────────────────────────────────────────────────────────────────────
def test_seed_aus_yaml_frische_installation_hat_leere_stadt(tmp_path):
    from pipeline import suchprofil

    ziel = tmp_path / "suchprofile.yaml"
    suchprofil.sicherstellen(ziel)

    seed = suchprofil.seed_aus_yaml(ziel)
    assert seed["suchbereich"]["umkreis"] == {"aktiv": False, "stadt": "", "umkreis_km": 100}


def test_seed_aus_yaml_alter_bucket_ohne_felder_faellt_auf_regionen_und_schluesselzahl_zurueck(tmp_path):
    """Ein Kopf von VOR P2-51: der Umkreis-Bucket hat weder `stadt` noch `umkreis_km` als
    eigenes Feld, nur `regionen: [stadt]` — Radius steckt nur im Bucket-Schlüssel."""
    import yaml
    from pipeline import suchprofil

    ziel = tmp_path / "suchprofile.yaml"
    kopf = {"buckets": {
        "Remote": {"regionen": ["Remote EMEA"], "umzug_ko": True},
        "Frankfurt +100km": {"regionen": ["Frankfurt am Main"], "onsite_ok": True},
    }}
    ziel.write_text(yaml.safe_dump(kopf) + "\n" + suchprofil.MARKER + "\nportale_technik: {}\n",
                    encoding="utf-8")

    seed = suchprofil.seed_aus_yaml(ziel)
    assert seed["suchbereich"]["umkreis"] == {"aktiv": True, "stadt": "Frankfurt am Main", "umkreis_km": 100}


# ── 5. Regressionsanker über die API ────────────────────────────────────────────────────────
def test_get_einstellungen_liefert_frankfurt_100km_bei_bisherigen_werten(session, client):
    _einstellung_setzen(session, suchbereich=FRANKFURT_AKTIV)

    r = client.get("/api/einstellungen")

    assert r.status_code == 200
    assert r.json()["umkreis_label"] == "Frankfurt +100km"


# ── 6. PATCH: Umbenennung ────────────────────────────────────────────────────────────────────
def test_patch_umkreis_umbenennung_stellt_jobs_und_firmen_um_inkl_papierkorb(session, client):
    """`company.region` trägt bei onsite-Firmen dieselbe Bezeichnung wie `job.tab` (die
    Bezeichnung ist die Kennung, Design-Entscheidung 5) — beide müssen bei einer Umbenennung
    mitziehen."""
    _einstellung_setzen(session, suchbereich=FRANKFURT_AKTIV)
    j1, c1 = _job(session, tab="Frankfurt +100km", region="Frankfurt +100km")
    j2, c2 = _job(session, tab="Frankfurt +100km", region="Frankfurt +100km", deleted=True)
    j3, c3 = _job(session, tab="Remote", region="Musterstadt")   # darf UNBERÜHRT bleiben

    r = client.patch("/api/einstellungen",
                      json={"suchbereich": {"umkreis": {"stadt": "Köln", "umkreis_km": 50}}})

    assert r.status_code == 200
    body = r.json()
    assert body["umkreis_label"] == "Köln +50km"
    assert body["umbenennung"] == {"von": "Frankfurt +100km", "nach": "Köln +50km", "jobs": 2, "firmen": 2}

    for obj in (j1, j2, j3, c1, c2, c3):
        session.refresh(obj)
    assert j1.tab == j2.tab == "Köln +50km"      # Papierkorb wird MIT umgestellt
    assert j3.tab == "Remote"                     # unbeteiligt bleibt unbeteiligt
    assert c1.region == c2.region == "Köln +50km"
    assert c3.region == "Musterstadt"

    import yaml
    from pipeline import suchprofil
    geparst = yaml.safe_load(suchprofil.SUCHPROFILE_PATH.read_text(encoding="utf-8"))
    assert "Köln +50km" in geparst["buckets"]
    assert "Frankfurt +100km" not in geparst["buckets"]


def test_patch_umkreis_ohne_wechsel_stellt_nichts_um(session, client):
    _einstellung_setzen(session, suchbereich=FRANKFURT_AKTIV)
    j1, _ = _job(session, tab="Frankfurt +100km", region="Frankfurt am Main")

    r = client.patch("/api/einstellungen", json={
        "suchbereich": {"umkreis": {"stadt": "Frankfurt am Main", "umkreis_km": 100}}})

    assert r.status_code == 200
    assert "umbenennung" not in r.json()
    session.refresh(j1)
    assert j1.tab == "Frankfurt +100km"


def test_patch_umkreis_aktiv_ohne_stadt_ist_422(session, client):
    _einstellung_setzen(session, suchbereich={"umkreis": {"aktiv": False, "stadt": "", "umkreis_km": 100}})

    r = client.patch("/api/einstellungen", json={"suchbereich": {"umkreis": {"aktiv": True}}})

    assert r.status_code == 422
    assert "Stadt" in r.json()["detail"]


@pytest.mark.parametrize("km", [0, -5, 1001, 5000])
def test_patch_umkreis_km_ausserhalb_1_bis_1000_ist_422(session, client, km):
    _einstellung_setzen(session, suchbereich=FRANKFURT_AKTIV)

    r = client.patch("/api/einstellungen",
                      json={"suchbereich": {"umkreis": {"stadt": "Köln", "umkreis_km": km}}})

    assert r.status_code == 422


# ── 7. tab_normalisieren — Ingest, POST, PATCH ──────────────────────────────────────────────
def test_normalisierung_im_ingest_mappt_alte_kennung_auf_aktuelles_label(session, monkeypatch, tmp_path):
    import pipeline.dedup_text as dedup_text
    from pipeline import ingest
    from app.models import Job

    # `ingest_records()` ruft immer `dedup_text.konfiguration()`, das `config/suchprofile.yaml`
    # liest. Die Datei ist gitignored: ohne Ersatz liest der Test lokal die echte YAML und
    # bricht in der CI ab (Muster tests/test_ingest_neuausschreibung.py).
    leere_config = tmp_path / "suchprofile.yaml"
    leere_config.write_text("dedup_text: {}\n", encoding="utf-8")
    monkeypatch.setattr(dedup_text, "CONFIG_FILE", leere_config)

    _einstellung_setzen(session, suchbereich={
        "umkreis": {"aktiv": True, "stadt": "Köln", "umkreis_km": 50}})

    ergebnis = ingest.ingest_records(
        [{"company": "Beispiel GmbH", "title": "Testrolle", "tab": "Frankfurt +100km"}],
        erlaube_unverifiziert=True)

    assert ergebnis["new"] == 1
    job = session.get(Job, ergebnis["new_ids"][0])
    assert job.tab == "Köln +50km"


def test_normalisierung_bei_post_jobs(session, client):
    _einstellung_setzen(session, suchbereich={
        "umkreis": {"aktiv": True, "stadt": "Köln", "umkreis_km": 50}})

    r = client.post("/api/jobs", json={
        "company_name": "Beispiel GmbH", "title": "Testrolle POST", "tab": "Frankfurt +100km"})

    assert r.status_code == 200
    assert r.json()["job"]["tab"] == "Köln +50km"


def test_normalisierung_bei_patch_jobs(session, client):
    _einstellung_setzen(session, suchbereich={
        "umkreis": {"aktiv": True, "stadt": "Köln", "umkreis_km": 50}})
    j, _ = _job(session, tab="Remote")

    r = client.patch(f"/api/jobs/{j.id}", json={"tab": "Frankfurt +100km"})

    assert r.status_code == 200
    assert r.json()["tab"] == "Köln +50km"


def test_normalisierung_remote_deutschlandweit_in_beliebiger_schreibung(session, client):
    _einstellung_setzen(session, suchbereich={"umkreis": {"aktiv": False, "stadt": "", "umkreis_km": 100}})
    j, _ = _job(session, tab="Frankfurt +100km")

    r = client.patch(f"/api/jobs/{j.id}", json={"tab": "dEuTschlandweit"})

    assert r.status_code == 200
    assert r.json()["tab"] == "Deutschlandweit"


# ── 8. Lehre Phase 87: Teil-Save gegen eine BESTEHENDE Zeile ────────────────────────────────
def test_teil_save_nur_suchbereich_laesst_modelle_unveraendert(session, client):
    _einstellung_setzen(session, suchbereich=FRANKFURT_AKTIV, modelle={"jobsuche": "opus"})

    r = client.patch("/api/einstellungen", json={"suchbereich": {"umkreis": {"umkreis_km": 75}}})

    assert r.status_code == 200
    assert r.json()["modelle"]["jobsuche"] == "opus"


def test_teil_save_nur_modelle_laesst_suchbereich_unveraendert(session, client):
    _einstellung_setzen(session, suchbereich=FRANKFURT_AKTIV)

    r = client.patch("/api/einstellungen", json={"modelle": {"jobsuche": "haiku"}})

    assert r.status_code == 200
    assert r.json()["umkreis_label"] == "Frankfurt +100km"
