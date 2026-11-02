"""LinkedIn-Profil aus eingefügtem Text oder PDF: Eingabe, Vorschlag der KI, Vorschau, additives Übernehmen."""
import uuid

import pytest


def _pdf_mit_text(text: str) -> bytes:
    """Kleinstes gültiges PDF mit einer Textzeile, von Hand gebaut (pypdf schreibt keinen Text)."""
    strom = f"BT /F1 12 Tf 10 100 Td ({text}) Tj ET".encode("latin-1")
    objekte = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(strom)).encode() + b" >>\nstream\n" + strom + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    aus = b"%PDF-1.4\n"
    positionen = []
    for n, objekt in enumerate(objekte, 1):
        positionen.append(len(aus))
        aus += f"{n} 0 obj\n".encode() + objekt + b"\nendobj\n"
    xref = len(aus)
    aus += f"xref\n0 {len(objekte) + 1}\n0000000000 65535 f \n".encode()
    aus += b"".join(f"{p:010d} 00000 n \n".encode() for p in positionen)
    aus += f"trailer << /Size {len(objekte) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return aus


@pytest.fixture
def lt():
    from pipeline import linkedin_text
    linkedin_text.verwerfen()
    linkedin_text._eingabe_pfad().unlink(missing_ok=True)
    return linkedin_text


@pytest.fixture
def lauf_abgefangen(monkeypatch):
    """Kein echter KI-Lauf: Der Task wird nur angelegt, gestartet wird nichts."""
    from app import main
    aufrufe = []

    async def create_task(payload, session):
        aufrufe.append(payload)
        return {"id": 4711, "status": "queued", "kind": payload["kind"]}

    monkeypatch.setattr(main, "create_task", create_task)
    return aufrufe


def test_text_startet_den_lauf_und_der_lauf_holt_ihn(client, lt, lauf_abgefangen):
    antwort = client.post("/api/profil/linkedin-einlesen", data={"text": "  Mein Profiltext  "})
    assert antwort.status_code == 200 and antwort.json()["task_id"] == 4711
    assert lauf_abgefangen == [{"kind": "profil-einlesen"}]
    assert client.get("/api/profil/linkedin-eingabe").json() == {"text": "Mein Profiltext"}


def test_pdf_wird_lokal_zu_text(client, lt, lauf_abgefangen):
    antwort = client.post("/api/profil/linkedin-einlesen",
                          files={"file": ("profil.pdf", _pdf_mit_text("Leitung Delivery"), "application/pdf")})
    assert antwort.status_code == 200
    assert "Leitung Delivery" in client.get("/api/profil/linkedin-eingabe").json()["text"]


@pytest.mark.parametrize("daten,dateien,meldung", [
    ({"text": "   "}, None, "einfügen"),
    ({"text": "x" * 60_001}, None, "zu lang"),
    (None, {"file": ("kaputt.pdf", b"kein pdf", "application/pdf")}, "nicht als PDF"),
])
def test_unbrauchbare_eingabe_startet_keinen_lauf(client, lt, lauf_abgefangen, daten, dateien, meldung):
    antwort = client.post("/api/profil/linkedin-einlesen", data=daten, files=dateien)
    assert antwort.status_code == 422 and meldung in antwort.json()["detail"]
    assert lauf_abgefangen == []
    assert client.get("/api/profil/linkedin-eingabe").status_code == 404


@pytest.mark.parametrize("roh,meldung", [
    ([], "JSON-Objekt"),
    ({"skills": "x"}, "Listen"),
    ({"werdegang": [{"art": "Erfunden", "firma": "x"}]}, "art"),
    ({"headline": 5}, "Text"),
    ({"headline": "x" * 301}, "zu lang"),
    ({"skills": ["x"] * 201}, "zu viele"),
])
def test_vorschlag_wird_geprueft(lt, roh, meldung):
    with pytest.raises(lt.EingabeFehler, match=meldung):
        lt.vorschlag_pruefen(roh)


def test_fremde_felder_und_leere_eintraege_fallen_weg(lt):
    v = lt.vorschlag_pruefen({"headline": " Kopf ", "passwort": "x", "skills": [" A ", ""],
                              "werdegang": [{"art": "Beruf"}, {"art": "Beruf", "firma": "F", "geheim": "x"}]})
    assert v["headline"] == "Kopf" and v["skills"] == ["A"] and "passwort" not in v
    assert v["werdegang"] == [{"art": "Beruf", "firma": "F", "rolle": "", "von": "", "bis": "", "beschreibung": ""}]


def test_ablauf_vorschau_aendert_nichts_uebernehmen_ist_additiv(client, lt, monkeypatch):
    from app import main

    async def create_task(payload, session):
        return {"id": 1, "status": "queued", "kind": payload["kind"]}

    monkeypatch.setattr(main, "create_task", create_task)
    kennung = uuid.uuid4().hex[:8]
    skill_vorhanden = f"Vorhanden {kennung}"
    skill_neu = f"Neu {kennung}"
    firma = f"Probefirma {kennung}"
    assert client.post("/api/profil/skills", json={"name": skill_vorhanden, "bereich": "Test"}).status_code == 200
    vorher = client.get("/api/profil").json()["profile"]
    client.patch("/api/profil", json={"headline": "Schon gesetzt"})

    client.post("/api/profil/linkedin-einlesen", data={"text": "Text"})
    abgabe = client.post("/api/profil/linkedin-vorschlag", json={
        "headline": "Neue Headline", "positionierung": "",
        "skills": [skill_vorhanden, skill_neu, skill_neu],
        "werdegang": [{"art": "Beruf", "firma": firma, "rolle": "Rolle", "von": "2020", "bis": "heute"}],
    })
    assert abgabe.status_code == 200
    # Der rohe Text liegt nach der Abgabe nicht mehr herum
    assert client.get("/api/profil/linkedin-eingabe").status_code == 404

    vorschau = client.get("/api/profil/linkedin-vorschlag").json()
    assert vorschau["vorhanden"] is True and vorschau["felder"] == []
    assert vorschau["felder_behalten"] == ["Headline"]
    assert vorschau["skills_neu"] == [skill_neu] and vorschau["skills_vorhanden"] == 2
    assert [e["firma"] for e in vorschau["werdegang_neu"]] == [firma]

    def namen():
        return [s["name"] for liste in client.get("/api/profil").json()["skills"].values() for s in liste]

    assert skill_neu not in namen()     # die Vorschau schreibt nichts

    ergebnis = client.post("/api/profil/linkedin-vorschlag/uebernehmen").json()
    assert ergebnis["skills_neu"] == 1 and ergebnis["werdegang_neu"] == 1 and ergebnis["profil_aktualisiert"] == []
    assert skill_neu in namen()
    assert client.get("/api/profil").json()["profile"]["headline"] == "Schon gesetzt"
    assert client.get("/api/profil/linkedin-vorschlag").json() == {"vorhanden": False}
    assert client.post("/api/profil/linkedin-vorschlag/uebernehmen").status_code == 404
    client.patch("/api/profil", json={"headline": vorher.get("headline")})


def test_verwerfen_und_ungueltige_abgabe(client, lt):
    assert client.post("/api/profil/linkedin-vorschlag", json={"werdegang": [{"art": "Erfunden"}]}).status_code == 422
    assert client.get("/api/profil/linkedin-vorschlag").json() == {"vorhanden": False}
    assert client.post("/api/profil/linkedin-vorschlag", json={"headline": "x"}).status_code == 200
    assert client.delete("/api/profil/linkedin-vorschlag").status_code == 200
    assert client.get("/api/profil/linkedin-vorschlag").json() == {"vorhanden": False}


def test_lauf_ist_ohne_web_und_ohne_parameter():
    from app import agent_runner
    art = agent_runner.PROMPTS["profil-einlesen"]
    assert art["headless"] is True and not art.get("needs_params")
    assert {"WebSearch", "WebFetch"} <= set(art["disallowed_tools"])
