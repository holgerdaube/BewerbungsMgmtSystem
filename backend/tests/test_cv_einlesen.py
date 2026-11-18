"""Profil aus dem Lebenslauf: Basis-CV auslesen, PDF oder Word hochladen, Word wird neuer Basis-CV.

`main._PROJECT_ROOT` wird umgebogen, weil `data/cv_basis` nicht an `BMS_DATA_DIR` hängt und die echten Basis-CVs
sonst berührt würden (Muster test_cv_basis_upload.py).
"""
import io
import uuid

import pytest
from docx import Document

from tests.test_linkedin_text import _pdf_mit_text


def _docx(text: str = "Leitung Delivery") -> bytes:
    doc = Document()
    doc.add_paragraph(text)
    tabelle = doc.add_table(rows=1, cols=1)
    tabelle.cell(0, 0).text = "Skill aus Tabelle"
    puffer = io.BytesIO()
    doc.save(puffer)
    return puffer.getvalue()


def _docx_mit_textfeld() -> bytes:
    """Ein Textfeld, wie Word es speichert: zweimal derselbe Inhalt."""
    from docx.oxml import parse_xml

    doc = Document()
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    for _ in range(2):
        doc.element.body.insert(0, parse_xml(
            f'<w:p {w}><w:r><w:pict><w:txbxContent><w:p><w:r><w:t>Text im Feld</w:t></w:r></w:p>'
            '</w:txbxContent></w:pict></w:r></w:p>'))
    puffer = io.BytesIO()
    doc.save(puffer)
    return puffer.getvalue()


@pytest.fixture
def cv_ordner(client, tmp_path, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)
    ordner = tmp_path / "data" / "cv_basis"
    ordner.mkdir(parents=True)
    return ordner


@pytest.fixture
def lauf(monkeypatch):
    """Kein echter KI-Lauf: Der Task wird nur angelegt."""
    from app import main
    from pipeline import linkedin_text

    linkedin_text.verwerfen()
    linkedin_text._eingabe_pfad().unlink(missing_ok=True)
    linkedin_text._quelle_pfad().unlink(missing_ok=True)
    aufrufe = []

    async def create_task(payload, session):
        aufrufe.append(payload)
        return {"id": 4711, "status": "queued", "kind": payload["kind"]}

    monkeypatch.setattr(main, "create_task", create_task)
    return aufrufe


def _eingabe(client):
    return client.get("/api/profil/linkedin-eingabe").json()["text"]


def test_basis_cv_wird_ausgelesen_und_bleibt_unveraendert(client, cv_ordner, lauf):
    ziel = cv_ordner / "base_en.docx"
    ziel.write_bytes(_docx("Head of Delivery"))
    vorher = ziel.read_bytes()

    antwort = client.post("/api/profil/cv-einlesen", data={"sprache": "en"})

    assert antwort.status_code == 200 and antwort.json()["basis_cv"] is None
    assert lauf == [{"kind": "profil-einlesen"}]
    text = _eingabe(client)
    assert "Head of Delivery" in text and "Skill aus Tabelle" in text
    assert ziel.read_bytes() == vorher


def test_fehlender_basis_cv_startet_keinen_lauf(client, cv_ordner, lauf):
    assert client.post("/api/profil/cv-einlesen", data={"sprache": "fr"}).status_code == 404
    assert lauf == []


@pytest.mark.parametrize("sprache", ["", "deu", "DE", "../x", "de\n"])
def test_ungueltiger_sprachcode_wird_abgelehnt(client, cv_ordner, lauf, sprache):
    antwort = client.post("/api/profil/cv-einlesen", data={"sprache": sprache},
                          files={"file": ("cv.docx", _docx(), "application/octet-stream")})
    assert antwort.status_code == 422 and lauf == []
    assert list(cv_ordner.iterdir()) == []


def test_word_upload_wird_neuer_basis_cv(client, cv_ordner, lauf):
    inhalt = _docx()
    antwort = client.post("/api/profil/cv-einlesen", data={"sprache": "de"},
                          files={"file": ("mein_cv.docx", inhalt, "application/octet-stream")})

    assert antwort.status_code == 200 and antwort.json()["basis_cv"] == "gespeichert"
    assert (cv_ordner / "base_de.docx").read_bytes() == inhalt
    assert not (cv_ordner / "base_de.docx.neu").exists()
    assert "Leitung Delivery" in _eingabe(client)


def test_word_upload_ueberschreibt_vorhandenen_basis_cv_nie(client, cv_ordner, lauf):
    ziel = cv_ordner / "base_de.docx"
    ziel.write_bytes(_docx("Bestehende Fassung"))
    vorher = ziel.read_bytes()

    antwort = client.post("/api/profil/cv-einlesen", data={"sprache": "de"},
                          files={"file": ("neu.docx", _docx("Neue Fassung"), "application/octet-stream")})

    assert antwort.status_code == 200 and antwort.json()["basis_cv"] == "vorhanden"
    assert ziel.read_bytes() == vorher
    assert "Neue Fassung" in _eingabe(client)


def test_pdf_wird_gelesen_aber_nie_basis_cv(client, cv_ordner, lauf):
    antwort = client.post("/api/profil/cv-einlesen",
                          files={"file": ("cv.pdf", _pdf_mit_text("Leitung Delivery"), "application/pdf")})

    assert antwort.status_code == 200 and antwort.json()["basis_cv"] is None
    assert "Leitung Delivery" in _eingabe(client)
    assert list(cv_ordner.iterdir()) == []


@pytest.mark.parametrize("name,inhalt,meldung", [
    ("cv.txt", b"Text", "PDF"),
    ("cv", b"Text", "PDF"),
    ("kaputt.docx", b"kein word", "Word"),
    ("kaputt.pdf", b"kein pdf", "PDF"),
])
def test_unbrauchbare_datei_startet_keinen_lauf(client, cv_ordner, lauf, name, inhalt, meldung):
    antwort = client.post("/api/profil/cv-einlesen", data={"sprache": "de"},
                          files={"file": (name, inhalt, "application/octet-stream")})
    assert antwort.status_code == 422 and meldung in antwort.json()["detail"]
    assert lauf == [] and list(cv_ordner.iterdir()) == []


def test_textfelder_werden_ohne_wiederholung_gelesen():
    from pipeline import linkedin_text

    assert linkedin_text.docx_zu_text(_docx_mit_textfeld()).count("Text im Feld") == 1


def test_eintraege_aus_dem_cv_tragen_die_quelle_cv(client, cv_ordner, lauf):
    kennung = uuid.uuid4().hex[:8]
    skill, firma = f"CV-Skill {kennung}", f"CV-Firma {kennung}"
    stand_vorher = client.get("/api/profil").json()["profile"].get("linkedin_eingelesen_am")
    (cv_ordner / "base_de.docx").write_bytes(_docx())
    client.post("/api/profil/cv-einlesen", data={"sprache": "de"})

    # Eine von der KI mitgeschickte Quelle zählt nicht.
    abgabe = client.post("/api/profil/linkedin-vorschlag", json={
        "quelle": "linkedin", "skills": [skill],
        "werdegang": [{"art": "Beruf", "firma": firma, "rolle": "Rolle", "von": "2020", "bis": "heute"}],
    })
    assert abgabe.status_code == 200
    assert client.post("/api/profil/linkedin-vorschlag/uebernehmen").status_code == 200

    profil = client.get("/api/profil").json()
    eintrag = next(e for e in profil["werdegang"] if e["firma"] == firma)
    gefunden = next(s for liste in profil["skills"].values() for s in liste if s["name"] == skill)
    assert eintrag["quelle"] == "cv" and gefunden["quelle"] == "cv"
    assert profil["profile"].get("linkedin_eingelesen_am") == stand_vorher


def test_linkedin_weg_bleibt_bei_quelle_linkedin(client, lauf):
    kennung = uuid.uuid4().hex[:8]
    skill = f"LinkedIn-Skill {kennung}"
    client.post("/api/profil/linkedin-einlesen", data={"text": "Profiltext"})
    client.post("/api/profil/linkedin-vorschlag", json={"skills": [skill]})
    client.post("/api/profil/linkedin-vorschlag/uebernehmen")

    skills = client.get("/api/profil").json()["skills"]
    assert next(s for liste in skills.values() for s in liste if s["name"] == skill)["quelle"] == "linkedin"
