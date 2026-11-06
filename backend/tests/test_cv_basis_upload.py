"""Tests für P2-27 (tasks/spec_p2-27_cv_basis_upload.md): Basis-CVs über die Profil-Seite hoch-
laden. Diese Datei prüft AUSSCHLIESSLICH gegen die Spec (§1), nicht gegen den zeitgleich von
einem zweiten Agenten gebauten Code in `app/main.py` — Endpunktpfade, Statuscodes und Feldnamen
aus Spec §1 sind der Vertrag zwischen den beiden Agenten.

WARUM diese Datei so vorsichtig mit `_PROJECT_ROOT` umgeht: Die ECHTEN Basis-CVs liegen unter
`data/cv_basis/base_de.docx` / `base_en.docx` und werden von fünf Aufrufern gelesen
(`beirat_engine.py`, `agent_runner.py`, vier SKILL.md). Ein Test, der versehentlich gegen den
echten Ordner schreibt oder gar überschreibt, würde den gepflegten Lebenslauf zerstören —
irreversibel, denn Papierkorb hin oder her, es ist trotzdem der echte Stand. Deshalb exakt das
Muster aus `test_loeschen_reihenfolge.py` (WICHTIGER BEFUND 1 dort): `app.main._PROJECT_ROOT`
wird beim Modul-Import HART gebunden und reagiert nicht auf Env-Overrides — jeder Test hier bindet
ihn deshalb per `monkeypatch.setattr` auf `tmp_path` um, BEVOR er irgendeinen Endpunkt aufruft.
Die beiden Reihenfolge-Tests (`test_zweiter_upload_ohne_overwrite_wird_abgelehnt`,
`test_kaputte_docx_wird_vor_dem_schreiben_abgelehnt`) lesen die vorhandene Datei zusätzlich VOR
und NACH dem Request byteweise ein und vergleichen — nicht nur der Statuscode zählt, sondern dass
im Fehlerfall im Zielordner buchstäblich nichts passiert ist (Spec §1.3: „Reihenfolge ist
verbindlich — erst prüfen, dann schreiben").

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention).
"""
import io

import pytest


def _minimal_docx(mit_stationen: bool) -> bytes:
    """Baut ein Minimal-.docx im Speicher — NIE wird eine echte Datei von der Platte gelesen.

    `mit_stationen=True` bildet die Struktur nach, die `pipeline.cv_export._ist_stationsstart`
    (Style „Normal“, Text enthält ein TAB) und `_ist_stationstitel` (Style „Normal“, kein TAB,
    mindestens ein fetter Run) erkennen: Titel-Absatz (fett, kein Tab), dann ein Absatz
    „Firma<TAB>Zeitraum“, dann ein Bullet-Absatz. `_stationsgrenzen` zählt daraus GENAU eine
    Station — Beweis genug, dass der Upload-Helfer dieselbe Zählung wie der echte
    Seitenumbruch-Schutz benutzt (Spec §1.5), ohne die volle 14-Stationen-Struktur der echten
    Basis-CVs nachbauen zu müssen.

    `mit_stationen=False` liefert ein Dokument ganz ohne Tab-Absatz — `_stationsgrenzen` findet
    keine Station, `stationen == 0` (Spec §1.5 Warnungsfall).
    """
    from docx import Document

    doc = Document()
    doc.add_heading("BERUFSERFAHRUNG", level=1)
    if mit_stationen:
        titel = doc.add_paragraph()
        titel.add_run("Head of Customer Success").bold = True
        doc.add_paragraph("Musterfirma GmbH\t2020 – heute")
        doc.add_paragraph("Team von 40 Personen verantwortet", style="List Bullet")
    else:
        doc.add_paragraph("Ein Absatz ganz ohne Stationsstruktur.")
    puffer = io.BytesIO()
    doc.save(puffer)
    return puffer.getvalue()


def _kaputte_bytes() -> bytes:
    """Bytes, die garantiert kein Word-Dokument sind (kein ZIP-Signatur-Header) — das muss die
    Öffnen-Probe (`Document(io.BytesIO(...))`, Spec §1.3 Schritt 4) zum Scheitern bringen, BEVOR
    irgendetwas geschrieben wird."""
    return b"das ist kein docx, nur normaler text\n" * 10


@pytest.fixture()
def cv_basis_root(client, tmp_path, monkeypatch):
    """Bindet `main._PROJECT_ROOT` auf `tmp_path` um (Muster test_loeschen_reihenfolge.py) und
    gibt den `data/cv_basis`-Ordner zurück. `client` zuerst als Fixture-Parameter, damit die App
    (und damit `app.main`) sicher importiert ist, bevor wir das Modul patchen."""
    import app.main as main

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)
    ordner = tmp_path / "data" / "cv_basis"
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def _upload(client, sprache="de", docx_bytes=None, overwrite=None, filename="cv.docx"):
    if docx_bytes is None:
        docx_bytes = _minimal_docx(mit_stationen=True)
    data = {"sprache": sprache}
    if overwrite is not None:
        data["overwrite"] = overwrite
    return client.post(
        "/api/profil/cv-basis",
        files={"file": (filename, docx_bytes,
                         "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data=data,
    )


# ── Upload legt Basis-CV an ─────────────────────────────────────────────────────────────────
def test_upload_legt_basis_cv_an(client, cv_basis_root):
    inhalt = _minimal_docx(mit_stationen=True)
    r = _upload(client, sprache="de", docx_bytes=inhalt)
    assert r.status_code == 200
    body = r.json()
    assert body["sprache"] == "de"
    assert body["filename"] == "base_de.docx"

    ziel = cv_basis_root / "base_de.docx"
    assert ziel.is_file()
    assert body["size_bytes"] == ziel.stat().st_size == len(inhalt)


# ── Reihenfolge-Beweis 1: 409 lässt die vorhandene Datei unangetastet ───────────────────────
def test_zweiter_upload_ohne_overwrite_wird_abgelehnt(client, cv_basis_root):
    erste_fassung = _minimal_docx(mit_stationen=True)
    r1 = _upload(client, sprache="de", docx_bytes=erste_fassung)
    assert r1.status_code == 200

    ziel = cv_basis_root / "base_de.docx"
    vorher = ziel.read_bytes()

    zweite_fassung = _minimal_docx(mit_stationen=False)   # bewusst ANDERER Inhalt
    r2 = _upload(client, sprache="de", docx_bytes=zweite_fassung)
    assert r2.status_code == 409
    detail = r2.json()["detail"]
    assert detail["grund"] == "existiert"
    assert detail["sprache"] == "de"

    nachher = ziel.read_bytes()
    assert nachher == vorher, "409 darf die vorhandene Datei nicht anfassen (Spec §1.3 Schritt 5)"


# ── Reihenfolge-Beweis 2: kaputte Datei — nichts geschrieben, Original unangetastet ─────────
def test_kaputte_docx_wird_vor_dem_schreiben_abgelehnt(client, cv_basis_root):
    gueltige_fassung = _minimal_docx(mit_stationen=True)
    r1 = _upload(client, sprache="de", docx_bytes=gueltige_fassung)
    assert r1.status_code == 200

    ziel = cv_basis_root / "base_de.docx"
    vorher = ziel.read_bytes()

    r2 = _upload(client, sprache="de", docx_bytes=_kaputte_bytes(), overwrite="true")
    assert r2.status_code == 422

    nachher = ziel.read_bytes()
    assert nachher == vorher, (
        "Die Öffnen-Probe (Spec §1.3 Schritt 4) muss VOR dem Schreiben laufen — auch mit "
        "overwrite=true darf eine kaputte Datei den vorhandenen CV nicht zerstören."
    )
    assert not (cv_basis_root / "base_de.docx.neu").exists()


# ── Overwrite schiebt die alte Fassung in den Papierkorb ────────────────────────────────────
def test_overwrite_schiebt_die_alte_datei_in_den_papierkorb(client, cv_basis_root, tmp_path):
    erste_fassung = _minimal_docx(mit_stationen=True)
    r1 = _upload(client, sprache="de", docx_bytes=erste_fassung)
    assert r1.status_code == 200

    zweite_fassung = _minimal_docx(mit_stationen=False)
    r2 = _upload(client, sprache="de", docx_bytes=zweite_fassung, overwrite="true")
    assert r2.status_code == 200

    ziel = cv_basis_root / "base_de.docx"
    assert ziel.read_bytes() == zweite_fassung

    papierkorb = tmp_path / "data" / "papierkorb"
    treffer = list(papierkorb.glob("*base_de*")) if papierkorb.is_dir() else []
    assert treffer, "die alte Fassung muss im Papierkorb wiederzufinden sein, nicht gelöscht"
    assert any(p.read_bytes() == erste_fassung for p in treffer)


# ── Falsche Endung ───────────────────────────────────────────────────────────────────────────
def test_falsche_endung_wird_abgelehnt(client, cv_basis_root):
    r = _upload(client, sprache="de", docx_bytes=b"%PDF-1.4 kein docx", filename="cv.pdf")
    assert r.status_code == 422
    assert not (cv_basis_root / "base_de.docx").exists()
    assert not list(cv_basis_root.glob("base_de.*"))


# ── Pfad-Traversal über den Sprachcode ───────────────────────────────────────────────────────
@pytest.mark.parametrize("sprache", ["../../etc/passwd", "de/../x", "DE", "deu"])
def test_sprachcode_mit_pfadanteil_wird_abgelehnt(client, cv_basis_root, tmp_path, sprache):
    r = _upload(client, sprache=sprache)
    assert r.status_code == 422
    # nichts ausserhalb des cv_basis-Ordners (und nichts darin) entstanden:
    assert list(cv_basis_root.iterdir()) == []
    ausserhalb = list((tmp_path / "data").rglob("passwd"))
    assert ausserhalb == []


# ── Leere Datei ──────────────────────────────────────────────────────────────────────────────
def test_leere_datei_wird_abgelehnt(client, cv_basis_root):
    r = _upload(client, sprache="de", docx_bytes=b"")
    assert r.status_code == 422
    assert not (cv_basis_root / "base_de.docx").exists()


# ── GET-Liste: Stationen + Automatik-Kennzeichen ────────────────────────────────────────────
def test_liste_zeigt_stationen_und_automatik_kennzeichen(client, cv_basis_root):
    assert _upload(client, sprache="de", docx_bytes=_minimal_docx(mit_stationen=True)).status_code == 200
    assert _upload(client, sprache="en", docx_bytes=_minimal_docx(mit_stationen=True)).status_code == 200
    assert _upload(client, sprache="fr", docx_bytes=_minimal_docx(mit_stationen=True)).status_code == 200
    assert _upload(client, sprache="nl", docx_bytes=_minimal_docx(mit_stationen=True)).status_code == 200

    r = client.get("/api/profil/cv-basis")
    assert r.status_code == 200
    liste = {eintrag["sprache"]: eintrag for eintrag in r.json()}

    assert liste["de"]["stationen"] == 1
    assert liste["de"]["automatisch"] is True
    assert liste["en"]["automatisch"] is True
    assert liste["fr"]["automatisch"] is True        # seit der Sprachwahl nach Anzeige: de, en, fr, it, es, pt
    assert liste["nl"]["automatisch"] is False


# ── GET übersteht eine unlesbare Datei im Ordner ────────────────────────────────────────────
def test_liste_uebersteht_eine_unlesbare_datei(client, cv_basis_root):
    (cv_basis_root / "base_xx.docx").write_bytes(_kaputte_bytes())

    r = client.get("/api/profil/cv-basis")
    assert r.status_code == 200
    liste = {eintrag["sprache"]: eintrag for eintrag in r.json()}

    assert "xx" in liste
    assert liste["xx"]["stationen"] is None
    assert liste["xx"]["warnung"]


# ── CV ohne Stationsstruktur wird angenommen, aber gewarnt ──────────────────────────────────
def test_cv_ohne_stationen_wird_angenommen_aber_gewarnt(client, cv_basis_root):
    r = _upload(client, sprache="de", docx_bytes=_minimal_docx(mit_stationen=False))
    assert r.status_code == 200
    body = r.json()
    assert body["stationen"] == 0
    assert body["warnung"]
    assert (cv_basis_root / "base_de.docx").is_file()


# ── Verwaistes PDF wandert in den Papierkorb ────────────────────────────────────────────────
def test_verwaistes_pdf_wandert_in_den_papierkorb(client, cv_basis_root, tmp_path):
    altes_pdf = b"%PDF-1.4 alte veraltete fassung\n"
    (cv_basis_root / "base_de.pdf").write_bytes(altes_pdf)

    r = _upload(client, sprache="de", docx_bytes=_minimal_docx(mit_stationen=True))
    assert r.status_code == 200
    body = r.json()
    assert body.get("pdf_papierkorb")

    assert not (cv_basis_root / "base_de.pdf").exists()
    papierkorb = tmp_path / "data" / "papierkorb"
    treffer = list(papierkorb.glob("*base_de*.pdf")) if papierkorb.is_dir() else []
    assert treffer
    assert any(p.read_bytes() == altes_pdf for p in treffer)


# ── DELETE nutzt den Papierkorb ─────────────────────────────────────────────────────────────
def test_loeschen_nutzt_den_papierkorb(client, cv_basis_root, tmp_path):
    inhalt = _minimal_docx(mit_stationen=True)
    assert _upload(client, sprache="de", docx_bytes=inhalt).status_code == 200

    r = client.delete("/api/profil/cv-basis/de")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["papierkorb"]

    assert not (cv_basis_root / "base_de.docx").exists()
    papierkorb = tmp_path / "data" / "papierkorb"
    treffer = list(papierkorb.glob("*base_de*")) if papierkorb.is_dir() else []
    assert any(p.read_bytes() == inhalt for p in treffer)


# ── P2-32: Der Struktur-Check prueft nicht nur DASS, sondern WIE ────────────────────────────
def _docx_mit_muster(beschreibung_vor_titel: bool) -> bytes:
    """Ein Mini-CV mit drei Berufsstationen, wahlweise im v10- oder im v7-Muster.

    v10: Firma<Tab>Zeitraum → Titel (bold) → Beschreibung
    v7 : Firma<Tab>Zeitraum → Beschreibung → Titel (bold)   ← die schaedliche Zwischenzeile
    """
    import io

    from docx import Document
    from docx.shared import Pt

    d = Document()
    d.add_paragraph("BERUFSERFAHRUNG", style="Heading 1")
    for n in range(3):
        d.add_paragraph(f"Firma {n} GmbH\t01/202{n} – 12/202{n}")

        def titel():
            p = d.add_paragraph()
            r = p.add_run(f"Director Services {n}")
            r.bold = True
            r.font.size = Pt(11)

        def beschreibung():
            d.add_paragraph(f"Anbieter von Dingen, Beschreibung {n}.")

        if beschreibung_vor_titel:
            beschreibung(); titel()
        else:
            titel(); beschreibung()
        d.add_paragraph(f"Bullet {n}", style="List Bullet")
    puffer = io.BytesIO()
    d.save(puffer)
    return puffer.getvalue()


def test_v7_muster_wird_beim_upload_gewarnt(cv_basis_root, client):
    """DER Fall vom 08.09.2026: Es wurden CVs hochgeladen, in denen die Firmenbeschreibung wieder
    zwischen Firmenzeile und Jobtitel stand — das alte v7-Muster.

    Die erste Fassung des Checks zaehlte nur, DASS Stationen erkannt werden. Es waren 14, also
    blieb sie stumm — und genau diese Zwischenzeile ist die Ursache dafuer, dass der
    Workday-Parser den Titel mit der naechsten Station paart. Der Upload gelingt weiterhin (eine
    abweichende Struktur ist nicht ungueltig), aber er sagt jetzt, was los ist.
    """
    antwort = _upload(client, docx_bytes=_docx_mit_muster(True))

    assert antwort.status_code == 200, antwort.text
    warnung = antwort.json()["warnung"]
    assert warnung, "das v7-Muster muss eine Warnung ausloesen"
    assert "v7" in warnung and "cv_basis_umbau_v10" in warnung, warnung


def test_v10_muster_wird_nicht_gewarnt(cv_basis_root, client):
    """Die Gegenprobe — sonst warnte der Check bei jeder Datei und niemand laese ihn noch."""
    antwort = _upload(client, docx_bytes=_docx_mit_muster(False))

    assert antwort.status_code == 200, antwort.text
    assert antwort.json()["warnung"] is None, antwort.json()["warnung"]

