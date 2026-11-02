"""API-Tests für `app/routes_profil_identitaet.py` (P2-69, Vertrag A): `GET`/`PUT /api/profil/identitaet`.

Die Tests laufen gegen die ECHTE App (`client`-Fixture), damit auch die Middleware der App greift.
Isolation: `user_profile._PROFIL_MD` und der Papierkorb (`app.db.DATA_DIR`) zeigen in jedem
Test auf `tmp_path`; die autouse-Fixture prüft nach, dass beide dort liegen. Die echte
`config/profil.md` wird nie gelesen oder geschrieben. Imports von App-Modulen nur in Fixtures/Tests
(conftest-Regel). Beispiele: nur Max Mustermann / Musterstadt."""
import hashlib

import pytest

STAND_VERALTET = ("Die Profil-Datei wurde inzwischen geändert. Bitte laden Sie die Karte neu und tragen Sie "
                  "Ihre Änderung noch einmal ein.")

PROFIL = """# Kandidatenprofil: Max Mustermann

## Identität
- **Name:** Max Mustermann
- **Positionierung:** Service Delivery Leader, DACH
- **Standort:** Musterweg 3, 12345 Musterstadt
- **Kontakt:** max.mustermann@example.com · +49 170 1234567
- **LinkedIn:** https://www.linkedin.com/in/max-mustermann/
- **Telefon privat:** 030 1234567

## Kurzprofil
Zwei Sätze über Max.

## Zielrolle
- **Ebene:** Director oder Head of
- **Region:** DACH

## Harte Rahmenbedingungen
- Kein Umzug.

## Sprachen / CV-Fassungen
- **Deutsch:** `data/cv_basis/base_de.docx`

## Bekannte Skill-Gaps / Red Flags
- (noch keine)

## Empirie aus dem Bewerbungsverlauf
- Absagen: 3 von 10
"""


@pytest.fixture(autouse=True)
def _profil_pfade(tmp_path, monkeypatch):
    from app import db
    from pipeline import user_profile

    projekt = tmp_path / "projekt"
    monkeypatch.setattr(user_profile, "_PROFIL_MD", projekt / "config" / "profil.md")
    monkeypatch.setattr(db, "DATA_DIR", projekt / "data")
    wurzel = user_profile.PROJECT_ROOT.resolve()
    for pfad in (user_profile._PROFIL_MD, db.DATA_DIR / "papierkorb"):
        aufgeloest = pfad.resolve()
        assert tmp_path.resolve() in aufgeloest.parents, f"Test zeigt nicht auf tmp_path: {pfad}"
        assert wurzel not in aufgeloest.parents, f"Test zeigt in die echte Installation: {pfad}"
    return projekt


@pytest.fixture()
def datei():
    from pipeline import user_profile
    return user_profile._PROFIL_MD


@pytest.fixture()
def papierkorb(_profil_pfade):
    return _profil_pfade / "data" / "papierkorb"


def _anlegen(datei, text=PROFIL):
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_bytes(text.encode("utf-8"))


def _put_body(antwort, **aenderungen):
    """PUT-Body aus einer GET-Antwort (wie die Karte): ohne vorhanden/unveraendert/hinweise/papierkorb."""
    body = {k: v for k, v in antwort.items() if k not in ("vorhanden", "unveraendert", "hinweise", "papierkorb")}
    ident = aenderungen.pop("identitaet", None)
    if ident:
        body["identitaet"] = {**body["identitaet"], **ident}
    body.update(aenderungen)
    return body


# ── GET ──────────────────────────────────────────────────────────────────────────────────────────
def test_get_ohne_datei(client, datei):
    r = client.get("/api/profil/identitaet")

    assert r.status_code == 200
    assert r.json() == {
        "vorhanden": False, "stand": "",
        "identitaet": {"name": "", "positionierung": "", "anschrift": "", "email": "", "telefon": "",
                       "linkedin": "", "aktuell": "", "weitere": []},
        "kurzprofil": "",
        "zielrolle": [{"schluessel": "Zieltermin", "wert": ""}],
        "rahmenbedingungen": "", "skill_gaps": "", "unveraendert": [], "hinweise": [],
    }
    assert not datei.exists()                       # Lesen legt nichts an


def test_get_mit_datei(client, datei):
    _anlegen(datei)

    r = client.get("/api/profil/identitaet")

    assert r.status_code == 200
    body = r.json()
    assert list(body) == ["vorhanden", "stand", "identitaet", "kurzprofil", "zielrolle", "rahmenbedingungen",
                          "skill_gaps", "unveraendert", "hinweise"]
    assert body["vorhanden"] is True
    assert body["stand"] == hashlib.sha256(PROFIL.encode("utf-8")).hexdigest()
    assert body["identitaet"] == {
        "name": "Max Mustermann", "positionierung": "Service Delivery Leader, DACH",
        "anschrift": "Musterweg 3, 12345 Musterstadt", "email": "max.mustermann@example.com",
        "telefon": "+49 170 1234567", "linkedin": "https://www.linkedin.com/in/max-mustermann/",
        "aktuell": "", "weitere": [{"schluessel": "Telefon privat", "wert": "030 1234567"}]}
    assert body["kurzprofil"] == "Zwei Sätze über Max."
    # Ältere Zeilen wie „Ebene“ bleiben in der Datei, die Maske zeigt nur den Zieltermin.
    assert body["zielrolle"] == [{"schluessel": "Zieltermin", "wert": ""}]
    assert body["rahmenbedingungen"] == "- Kein Umzug."
    assert body["skill_gaps"] == "- (noch keine)"
    assert body["unveraendert"] == ["Sprachen / CV-Fassungen", "Empirie aus dem Bewerbungsverlauf"]
    assert body["hinweise"] == []
    assert datei.read_bytes() == PROFIL.encode("utf-8")


def test_get_mit_hinweis_zur_anschrift(client, datei):
    _anlegen(datei, PROFIL.replace("Musterweg 3, 12345 Musterstadt", "Musterstadt"))
    assert client.get("/api/profil/identitaet").json()["hinweise"] == [
        "Die Ortszeile Ihrer Anschreiben entsteht aus ‚Straße Nr, PLZ Ort‘."]


def test_get_beispiel_datei(client, datei):
    from app import beispieldaten
    _anlegen(datei, beispieldaten._profil_md_text())
    body = client.get("/api/profil/identitaet").json()
    assert body["identitaet"]["name"] == beispieldaten.NAME
    assert body["unveraendert"] == ["Sprachen / CV-Fassungen", "Empirie aus dem Bewerbungsverlauf"]


def test_get_nicht_utf8_datei_gibt_422_mit_kundentext(client, datei):
    datei.parent.mkdir(parents=True)
    datei.write_bytes(b"## Identit\xe4t\n- **Name:** Max M\xfcller\n")
    r = client.get("/api/profil/identitaet")
    assert r.status_code == 422 and "UTF-8" in r.json()["detail"]


# ── PUT ──────────────────────────────────────────────────────────────────────────────────────────
def test_put_legt_die_datei_an(client, datei, papierkorb):
    from pipeline import user_profile
    body = _put_body(client.get("/api/profil/identitaet").json(), identitaet={
        "name": "Max Mustermann", "anschrift": "Musterweg 3, 12345 Musterstadt",
        "email": "max.mustermann@example.com", "telefon": "+49 170 1234567"},
        kurzprofil="Zwei Sätze über Max.", rahmenbedingungen="- Kein Umzug.")

    r = client.put("/api/profil/identitaet", json=body)

    assert r.status_code == 200
    antwort = r.json()
    assert list(antwort) == ["vorhanden", "stand", "identitaet", "kurzprofil", "zielrolle", "rahmenbedingungen",
                             "skill_gaps", "unveraendert", "hinweise", "papierkorb"]
    assert antwort["vorhanden"] is True and antwort["papierkorb"] is None
    assert antwort["stand"] == hashlib.sha256(datei.read_bytes()).hexdigest()
    assert antwort["identitaet"]["name"] == "Max Mustermann"
    assert antwort["identitaet"]["email"] == "max.mustermann@example.com"
    assert antwort["unveraendert"] == ["Sprachen / CV-Fassungen", "Empirie aus dem Bewerbungsverlauf"]
    text = datei.read_text(encoding="utf-8")
    assert text.startswith("# Kandidatenprofil: Max Mustermann\n\n## Identität\n- **Name:** Max Mustermann\n")
    assert "- **Kontakt:** max.mustermann@example.com · +49 170 1234567\n" in text
    assert not papierkorb.exists()
    # Die Leser sehen die Eingaben sofort
    assert user_profile.user_name() == "Max Mustermann"
    assert user_profile.anschrift() == "Musterweg 3, 12345 Musterstadt"
    assert user_profile.briefkopf_ort() == "Musterstadt"


def test_put_aendert_eine_zeile_und_sichert_die_alte_datei_im_papierkorb(client, datei, papierkorb):
    _anlegen(datei)
    geladen = client.get("/api/profil/identitaet").json()

    r = client.put("/api/profil/identitaet", json=_put_body(geladen, identitaet={"aktuell": "Zusteller bei der Beispiel GmbH"}))

    assert r.status_code == 200
    antwort = r.json()
    neu = datei.read_text(encoding="utf-8")
    # genau eine neue Zeile, hinter der letzten Feldzeile der Identität
    assert neu == PROFIL.replace("- **Telefon privat:** 030 1234567\n",
                                 "- **Telefon privat:** 030 1234567\n- **Aktuell:** Zusteller bei der Beispiel GmbH\n")
    kopie = papierkorb / antwort["papierkorb"].rsplit("/", 1)[1]
    assert antwort["papierkorb"].startswith("data/papierkorb/") and antwort["papierkorb"].endswith("_profil.md")
    assert kopie.read_bytes() == PROFIL.encode("utf-8")
    assert antwort["stand"] == hashlib.sha256(datei.read_bytes()).hexdigest() != geladen["stand"]
    assert antwort["identitaet"]["aktuell"] == "Zusteller bei der Beispiel GmbH"


def test_put_ohne_aenderung_schreibt_nichts_und_legt_keine_kopie_an(client, datei, papierkorb):
    _anlegen(datei)
    geladen = client.get("/api/profil/identitaet").json()
    mtime = datei.stat().st_mtime_ns

    r = client.put("/api/profil/identitaet", json=_put_body(geladen))

    assert r.status_code == 200 and r.json()["papierkorb"] is None and r.json()["stand"] == geladen["stand"]
    assert datei.read_bytes() == PROFIL.encode("utf-8") and datei.stat().st_mtime_ns == mtime
    assert not papierkorb.exists()


def test_put_erneut_mit_dem_neuen_stand_klappt(client, datei, papierkorb):
    _anlegen(datei)
    erste = client.put("/api/profil/identitaet", json=_put_body(client.get("/api/profil/identitaet").json(),
                                                                kurzprofil="Erste Fassung.")).json()
    zweite = client.put("/api/profil/identitaet", json=_put_body(erste, kurzprofil="Zweite Fassung."))

    assert zweite.status_code == 200
    assert "Zweite Fassung." in datei.read_text(encoding="utf-8")
    assert len(list(papierkorb.iterdir())) == 2


def test_put_mit_veraltetem_stand_gibt_409_und_laesst_die_datei_unveraendert(client, datei, papierkorb):
    _anlegen(datei)
    geladen = client.get("/api/profil/identitaet").json()
    # inzwischen ersetzt ein Skill die Empirie
    nachher = PROFIL.replace("Absagen: 3 von 10", "Absagen: 4 von 10")
    _anlegen(datei, nachher)

    r = client.put("/api/profil/identitaet", json=_put_body(geladen, identitaet={"name": "Anna Beispiel"}))

    assert r.status_code == 409
    assert r.json()["detail"] == STAND_VERALTET
    assert datei.read_bytes() == nachher.encode("utf-8")
    assert not papierkorb.exists()


def test_put_409_wenn_die_datei_inzwischen_fehlt_oder_neu_ist(client, datei):
    r = client.put("/api/profil/identitaet", json={"stand": "abc", "identitaet": {"name": "Max"}})
    assert r.status_code == 409 and not datei.exists()

    _anlegen(datei)
    r = client.put("/api/profil/identitaet", json={"stand": "", "identitaet": {"name": "Max"}})
    assert r.status_code == 409 and datei.read_bytes() == PROFIL.encode("utf-8")


def test_put_ohne_stand_gibt_400(client, datei):
    _anlegen(datei)
    for body in ({"identitaet": {"name": "Max"}}, {"stand": None, "identitaet": {"name": "Max"}},
                 {"stand": 5, "identitaet": {"name": "Max"}}):
        r = client.put("/api/profil/identitaet", json=body)
        assert r.status_code == 400 and "Stand" in r.json()["detail"]
    assert datei.read_bytes() == PROFIL.encode("utf-8")


@pytest.mark.parametrize("aenderung,fragment", [
    ({"identitaet": {"name": ""}}, "Namen"),
    ({"identitaet": {"name": "   "}}, "Namen"),
    ({"identitaet": {"aktuell": "Zeile 1\nZeile 2"}}, "nur eine Zeile"),
    ({"identitaet": {"email": "a@b.de\r\nBcc: x"}}, "nur eine Zeile"),
    ({"identitaet": {"aktuell": "x" * 301}}, "zu lang"),
    ({"kurzprofil": "Text\n## Neuer Abschnitt\nmehr"}, "‚## ‘"),
    ({"rahmenbedingungen": "## Empirie aus dem Bewerbungsverlauf"}, "‚## ‘"),
    ({"skill_gaps": "x" * 5001}, "zu lang"),
    ({"identitaet": {"weitere": [{"schluessel": "Erfunden", "wert": "x"}]}}, "‚Erfunden‘ gibt es in Ihrer Profil-Datei nicht"),
    ({"zielrolle": [{"schluessel": "Erfunden", "wert": "x"}]}, "‚Erfunden‘ gibt es in Ihrer Profil-Datei nicht"),
    ({"zielrolle": "Ebene"}, "unerwartetes Format"),
])
def test_put_gibt_400_mit_text_und_laesst_die_datei_unveraendert(client, datei, papierkorb, aenderung, fragment):
    _anlegen(datei)
    geladen = client.get("/api/profil/identitaet").json()

    r = client.put("/api/profil/identitaet", json=_put_body(geladen, **aenderung))

    assert r.status_code == 400, r.text
    assert fragment in r.json()["detail"]
    assert datei.read_bytes() == PROFIL.encode("utf-8")
    assert not papierkorb.exists()


def test_put_ohne_name_im_body_gibt_400(client, datei):
    _anlegen(datei)
    stand = client.get("/api/profil/identitaet").json()["stand"]
    for body in ({"stand": stand}, {"stand": stand, "identitaet": {}}, {"stand": stand, "identitaet": None}):
        r = client.put("/api/profil/identitaet", json=body)
        assert r.status_code == 400 and "Namen" in r.json()["detail"]


def test_put_mit_kaputtem_body_gibt_422(client, datei):
    _anlegen(datei)
    r = client.put("/api/profil/identitaet", json=["kein", "objekt"])
    assert r.status_code == 422
    assert datei.read_bytes() == PROFIL.encode("utf-8")


def test_put_antwort_traegt_hinweise_zu_den_eingaben(client, datei):
    geladen = client.get("/api/profil/identitaet").json()
    body = _put_body(geladen, identitaet={"name": "Max Mustermann", "anschrift": "Musterstadt",
                                          "email": "max.mustermann.example.com"})

    r = client.put("/api/profil/identitaet", json=body)

    assert r.status_code == 200
    assert r.json()["hinweise"] == ["Die Ortszeile Ihrer Anschreiben entsteht aus ‚Straße Nr, PLZ Ort‘.",
                                    "Die E-Mail-Adresse enthält kein ‚@‘. Bitte prüfen Sie die Schreibweise."]


def test_put_nur_der_name_ist_pflicht_alles_andere_darf_fehlen(client, datei):
    r = client.put("/api/profil/identitaet", json={"stand": "", "identitaet": {"name": "Max Mustermann"}})
    assert r.status_code == 200
    assert "- **Name:** Max Mustermann\n" in datei.read_text(encoding="utf-8")


def test_put_scheitert_das_ersetzen_gibt_500_und_die_alte_datei_bleibt(client, datei, monkeypatch):
    import os
    _anlegen(datei)
    geladen = client.get("/api/profil/identitaet").json()
    echtes_replace = os.replace

    def kaputt(quelle, ziel):
        if str(ziel) == str(datei):
            raise OSError("Ersetzen verweigert")
        return echtes_replace(quelle, ziel)
    monkeypatch.setattr(os, "replace", kaputt)

    r = client.put("/api/profil/identitaet", json=_put_body(geladen, kurzprofil="Neu."))

    assert r.status_code == 500
    assert "nicht gespeichert" in r.json()["detail"] and "unverändert" in r.json()["detail"]
    assert datei.read_bytes() == PROFIL.encode("utf-8")
    assert sorted(p.name for p in datei.parent.iterdir()) == ["profil.md"]


def test_put_rundweg_get_put_get_ist_stabil_bei_crlf(client, datei):
    crlf = PROFIL.replace("\n", "\r\n")
    _anlegen(datei, crlf)
    erste = client.get("/api/profil/identitaet").json()

    r = client.put("/api/profil/identitaet", json=_put_body(erste, identitaet={"linkedin": ""}, rahmenbedingungen="- Kein Umzug.\n- Vollzeit."))

    assert r.status_code == 200
    neu = datei.read_bytes().decode("utf-8")
    assert "\n" not in neu.replace("\r\n", "")
    assert "- Vollzeit.\r\n" in neu and "LinkedIn" not in neu


# ── Schema ───────────────────────────────────────────────────────────────────────────────────────
def test_routen_stehen_im_openapi_schema(client):
    from app.main import app
    pfade = app.openapi()["paths"]
    assert set(pfade["/api/profil/identitaet"]) == {"get", "put"}
