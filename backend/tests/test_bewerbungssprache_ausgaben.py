"""Bewerbungssprachen in den Unterlagen nach außen: Fußzeile, Sprache aus der Grußformel, Datum im
Anschreiben, Dateinamen (Akzente, Endungs-Klammern).

Deutsch und Englisch bleiben byte-gleich, ausgenommen das Datum im englischen Anschreiben
(`3 November 2026` statt `03.11.2026`) und Akzentbuchstaben, die früher aus dem Namen fielen.
Alle Firmen, Rollen und Texte sind erfunden. App-Importe in den Testfunktionen (conftest-Konvention).
"""
import datetime

import pytest

from tests.test_cv_export import _docx_mit_text, _fake_to_pdf, _patch_project_root
from tests.test_p2_63_leser import _stelle

TAG = datetime.date(2026, 11, 3)
PROFIL = """# Kandidatenprofil — Test

## Identität
- **Name:** Erika Mustermann
- **Standort:** Musterweg 3, 12345 Musterstadt
- **Kontakt:** erika@example.com · +49-170-1234567
"""
OHNE_KOPF = "Betreff: Bewerbung als Leiterin\n\nLiebes Team,\n\nText.\n\nGrüße\nErika Mustermann"


@pytest.fixture()
def profil(tmp_path, monkeypatch):
    import pipeline.user_profile as up

    datei = tmp_path / "profil.md"
    datei.write_text(PROFIL, encoding="utf-8")
    monkeypatch.setattr(up, "_PROFIL_MD", datei)
    return datei


@pytest.fixture()
def name_muster(monkeypatch):
    import pipeline.user_profile as up

    monkeypatch.setattr(up, "user_name", lambda: "Max Mustermann")


# ── Fix 1: Fußzeile ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sprache,erwartet", [
    (None, "Seite 1 von 1"), ("DE", "Seite 1 von 1"), ("de", "Seite 1 von 1"),
    ("EN", "Page 1 of 1"), ("en-US", "Page 1 of 1"),
    ("FR", "Page 1 sur 1"), ("fr", "Page 1 sur 1"),
    ("IT", "Pagina 1 di 1"), ("ES", "Página 1 de 1"), ("PT", "Página 1 de 1"),
    ("NL", "1 / 1"),                                    # unbekannt: neutral, nicht Deutsch
])
def test_fusszeile_je_sprache(tmp_path, monkeypatch, sprache, erwartet):
    from docx import Document
    from pipeline import cv_export, user_profile

    monkeypatch.setattr(user_profile, "user_name", lambda: "Testname Mock")
    pfad = tmp_path / "cv.docx"
    _docx_mit_text(pfad, ["EXECUTIVE SUMMARY", "Text."])

    fehler, _warnung = cv_export._nachbearbeiten(pfad, sprache)

    assert fehler is None
    assert Document(str(pfad)).sections[0].footer.paragraphs[0].text == f"Testname Mock · {erwartet}"


def test_fusszeilen_labels_in_cv_export_nutzt_die_quelle():
    from pipeline import cv_export

    assert cv_export._fusszeilen_labels("DE") == ("Seite ", " von ")
    assert cv_export._fusszeilen_labels("EN") == ("Page ", " of ")
    assert cv_export._fusszeilen_labels("pt") == ("Página ", " de ")
    assert cv_export._fusszeilen_labels(None) == ("Seite ", " von ")
    assert cv_export._fusszeilen_labels("xx") == ("", " / ")


# ── Fix 10: Sprache des Anschreibens aus der Grußformel ─────────────────────────────────────
@pytest.mark.parametrize("schluss,erwartet", [
    ("Mit freundlichen Grüßen,\nMax Muster", "DE"),
    ("Kind regards,\nMax Muster", "EN"),
    ("Sincerely\nMax Muster", "EN"),
    ("Cordialement,\nMax Muster", "FR"),
    ("Veuillez agréer, Madame, Monsieur, l'expression de mes salutations distinguées.\nMax Muster", "FR"),
    ("Cordiali saluti,\nMax Muster", "IT"),
    ("Un cordial saludo,\nMax Muster", "ES"),
    ("Com os melhores cumprimentos,\nMax Muster", "PT"),
    ("Max Muster", "DE"),                                     # keine Formel: Rückfall Deutsch wie heute
])
def test_sprache_aus_text_alle_sechs_sprachen(schluss, erwartet):
    from app.models import Application
    from pipeline import cv_export

    app = Application(cover_letter_text="Max Muster\n\nBetreff\n\nAnrede,\n\nText.\n\n" + schluss)
    assert cv_export._sprache_aus_text(app, None) == erwartet


def test_cover_letter_filename_mit_franzoesischer_formel(session, tmp_path, monkeypatch, name_muster):
    """Ende zu Ende: ohne gesetzte Sprache landet ein französischer Brief auf `_FR`."""
    from app.models import Application

    cv_export, _ = _patch_project_root(monkeypatch, tmp_path)
    monkeypatch.setattr(cv_export, "to_pdf", _fake_to_pdf)
    firma, job = _stelle(session, "Société Générale", "Livreur colis", "p293|fr1")
    text = "Max Mustermann\n\nLyon, 3 novembre 2026\n\nObjet : Candidature\n\nMadame, Monsieur,\n\nTexte.\n\nCordialement,\nMax"
    roh = tmp_path / "outputs" / "anschreiben" / "_raw_1.docx"
    _docx_mit_text(roh, text.split("\n\n"))
    app = Application(job_id=job.id, status="Beworben", cover_letter_text=text,
                      cover_letter_path="outputs/anschreiben/_raw_1.docx")
    session.add(app)
    session.commit()
    session.refresh(app)

    out = cv_export.export_cover_letter(app.id)

    assert out["docx"] == "outputs/anschreiben/CoverLetter_MaxMustermann_Societe_Generale_Livreur_colis_FR.docx"
    session.refresh(app)
    assert app.cover_letter_language == "FR"


# ── Fix 3: Datum im Anschreiben ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sprache,datum", [
    (None, "03.11.2026"), ("DE", "03.11.2026"), ("de", "03.11.2026"),
    ("EN", "3 November 2026"),
    ("FR", "3 novembre 2026"), ("IT", "3 novembre 2026"),
    ("ES", "3 de noviembre de 2026"), ("PT", "3 de novembro de 2026"),
    ("NL", "2026-11-03"),
])
def test_briefkopf_datum_je_sprache(profil, sprache, datum):
    from pipeline.cover_letter_render import mit_briefkopf

    kopf = mit_briefkopf(OHNE_KOPF, heute=TAG, sprache=sprache)

    assert f"Musterstadt, {datum}" in kopf.split("\n\n")
    assert kopf.endswith(OHNE_KOPF)


def test_briefkopf_ohne_sprache_bleibt_wie_bisher(profil):
    from pipeline.cover_letter_render import mit_briefkopf

    assert mit_briefkopf(OHNE_KOPF, heute=TAG) == mit_briefkopf(OHNE_KOPF, heute=TAG, sprache="DE")
    assert "Musterstadt, 03.11.2026" in mit_briefkopf(OHNE_KOPF, heute=TAG)


@pytest.mark.parametrize("sprache", ["DE", "EN", "FR", "IT", "ES", "PT"])
def test_ort_datum_zeile_wird_in_allen_sprachen_erkannt(profil, sprache):
    from pipeline import bewerbungssprache
    from pipeline.cover_letter_render import _ist_ort_datum

    zeile = f"Musterstadt, {bewerbungssprache.datum_text(TAG, sprache)}"
    assert _ist_ort_datum(zeile, 1), zeile
    # Gegenprobe: Fließtext mit Komma und Jahreszahl, aber zu spät im Brief
    assert not _ist_ort_datum(zeile, 7)
    assert not _ist_ort_datum("Seit 2019 arbeite ich in der Logistik, und zwar mit großer Freude am Fach.", 1)


@pytest.mark.parametrize("sprache", ["EN", "FR", "IT", "ES", "PT"])
def test_gerendertes_anschreiben_datum_rechts_in_landessprache(profil, tmp_path, sprache):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from pipeline import bewerbungssprache
    from pipeline.cover_letter_render import render_cover_letter

    ziel = tmp_path / "brief.docx"
    render_cover_letter(OHNE_KOPF, ziel, sprache=sprache)

    erwartet = f"Musterstadt, {bewerbungssprache.datum_text(datetime.date.today(), sprache)}"
    absaetze = {p.text: p for p in Document(str(ziel)).paragraphs}
    assert absaetze[erwartet].alignment == WD_ALIGN_PARAGRAPH.RIGHT
    assert ".20" not in erwartet.replace(str(datetime.date.today().year), "")      # kein Punktdatum


def test_gerendertes_anschreiben_ohne_sprache_hat_deutsches_datum(profil, tmp_path):
    from docx import Document
    from pipeline.cover_letter_render import render_cover_letter

    ziel = tmp_path / "brief.docx"
    render_cover_letter(OHNE_KOPF, ziel)
    texte = [p.text for p in Document(str(ziel)).paragraphs]
    assert f"Musterstadt, {datetime.date.today():%d.%m.%Y}" in texte


def test_betreff_und_grussformel_in_fremdsprachen_werden_formatiert(profil, tmp_path):
    from docx import Document
    from pipeline.cover_letter_render import render_cover_letter

    text = ("Erika Mustermann\nMusterweg 3\n\nMusterstadt, 3 novembre 2026\n\n"
            "Objet : Candidature au poste de cheffe\n\nMadame, Monsieur,\n\nTexte.\n\n"
            "Cordialement,\n\nErika Mustermann")
    ziel = tmp_path / "brief.docx"
    render_cover_letter(text, ziel, sprache="FR")
    absaetze = {p.text: p for p in Document(str(ziel)).paragraphs}

    betreff = absaetze["Objet : Candidature au poste de cheffe"]
    assert betreff.runs[0].bold is True and betreff.runs[0].font.size.pt == 12
    assert absaetze["Cordialement,"].paragraph_format.space_after.pt == 0       # Name direkt darunter
    assert absaetze["Texte."].paragraph_format.space_after is None      # erbt den Normal-Abstand


def test_render_and_export_reicht_die_gespeicherte_sprache_weiter(session, tmp_path, monkeypatch, profil):
    """Die Sprache der Bewerbung (`cover_letter_language`) kommt beim Rendern an; ohne Angabe gilt
    die Grußformel des Texts."""
    from docx import Document
    from app.models import Application
    from pipeline import cover_letter_render

    cv_export, _ = _patch_project_root(monkeypatch, tmp_path)
    monkeypatch.setattr(cv_export, "to_pdf", _fake_to_pdf)
    firma, job = _stelle(session, "Muster SL", "Operario", "p293|r1")
    app = Application(job_id=job.id, status="Beworben", cover_letter_language="ES",
                      cover_letter_text="Asunto: Solicitud\n\nEstimada Sra. Ruiz:\n\nTexto.\n\nAtentamente,\nErika")
    session.add(app)
    session.commit()

    out = cover_letter_render.render_and_export(job.id)

    erwartet = f"Musterstadt, {datetime.date.today().day} de "
    texte = [p.text for p in Document(str(tmp_path / out["docx"])).paragraphs]
    assert any(t.startswith(erwartet) and t.endswith(f" de {datetime.date.today().year}") for t in texte), texte


# ── Fix 2: Dateinamen ───────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("roh,erwartet", [
    ("Société Générale", "Societe_Generale"),
    ("Logística Peñón", "Logistica_Penon"),
    ("Più", "Piu"),
    ("Randstad España", "Randstad_Espana"),
    ("Indépendant", "Independant"),
    ("Œuvre Æther", "Oeuvre_Aether"),
    ("Intel·ligència", "Intelligencia"),
    ("distribuição", "distribuicao"),
    ("Carta de condução", "Carta_de_conducao"),
])
def test_sanitize_part_akzente_auf_grundbuchstaben(roh, erwartet):
    from app.naming import _sanitize_part

    assert _sanitize_part(roh) == erwartet


@pytest.mark.parametrize("roh,erwartet", [
    ("Müller & Söhne GmbH", "Mueller_Soehne_GmbH"),
    ("Großkunden-Betreuer", "Grosskunden-Betreuer"),
    ("Ärzte Übung Öl", "Aerzte_Uebung_Oel"),
    ("Head of IT - Infrastructure", "Head_of_IT_-_Infrastructure"),
    ("Sage™ ½ ² Co.", "Sage_Co"),                     # NFKD würde TM, 12, 2 daraus machen
    ("Berater (Senior)", "Berater_Senior"),
    ("Kaufmann/-frau für Büromanagement", "Kaufmann_-frau_fuer_Bueromanagement"),
    ("Straße 12 / Nord", "Strasse_12_Nord"),
])
def test_sanitize_part_deutsch_und_englisch_bleiben_gleich(roh, erwartet):
    from app.naming import _sanitize_part

    assert _sanitize_part(roh) == erwartet


def test_sanitize_part_zerlegte_umlaute_bleiben_wie_vor_der_aenderung():
    """Ein `ü` aus `u` + Trema (macOS-Dateisystem) wurde schon vorher zu `u`, nicht zu `ue` —
    die Reihenfolge Umlaut-Tabelle zuerst, Akzente danach ändert das nicht."""
    from app.naming import _sanitize_part

    assert _sanitize_part("Müller") == "Muller"
    assert _sanitize_part("Müller") != _sanitize_part("Müller")


def test_alle_stellen_in_naming_nutzen_dieselbe_hilfsfunktion(name_muster, monkeypatch):
    """Firma, Rolle, Teilnehmer und der eigene Name laufen durch `_translit`."""
    from app import naming
    import pipeline.user_profile as up

    monkeypatch.setattr(up, "user_name", lambda: "José García")
    cv = naming.cv_filename("Société Générale", "Chargé de mission", "FR")
    assert cv == "CV_JoseGarcia_Societe_Generale_Charge_de_mission_FR"
    cl = naming.cover_letter_filename("Logística Peñón", "Conductor repartidor", "es")
    assert cl == "CoverLetter_JoseGarcia_Logistica_Penon_Conductor_repartidor_ES"
    assert naming.transcript_filename("Transkript", "2026-11-03", "Zoë Müller", "Più SpA", "Chef", 1) == \
        "Transkript_20261103_Zoe_Mueller_Piu_SpA_Chef_R1"
    assert naming.report_filename("Anzeige", "Randstad España", "Conductor repartidor", when=TAG) == \
        "20261103_Anzeige_Randstad_Espana_Conductor_repartidor"
    assert naming.company_fit_filename("Société Générale") == "CompanyFit_Societe_Generale"
    assert naming.cv_filename_alt("Société Générale", "Chargé", "FR") == "CV_JoseGarcia_Societe_Generale_Charge_FR"


def test_translit_tabelle_fuer_die_suche_bleibt_unveraendert():
    """`search_index` nimmt nur ß aus `_TRANSLIT`; die neuen Buchstaben stehen in einer eigenen Tabelle."""
    from app import naming

    assert naming._TRANSLIT == {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}


@pytest.mark.parametrize("titel,erwartet", [
    ("Motorista Entregador(a)", "Motorista_Entregador"),
    ("Operario(a) de almacén", "Operario_de_almacen"),
    ("Addetto(a) alle vendite", "Addetto_alle_vendite"),
    ("Conductor(a) repartidor(a)", "Conductor_repartidor"),
    ("Empleados(as) de tienda", "Empleados_de_tienda"),
    ("Livreur(se) de colis", "Livreur_de_colis"),
    ("Directeur(trice) commercial", "Directeur_commercial"),
    ("Technicien(ne) de maintenance", "Technicien_de_maintenance"),
    ("Boulanger(ère) qualifié", "Boulanger_qualifie"),
    ("Motorista Entregador (a)", "Motorista_Entregador_a"),   # mit Leerzeichen: nicht am Wort, bleibt
])
def test_rolle_klammer_endung_faellt_weg(titel, erwartet):
    from app.naming import _rolle_kurz

    assert _rolle_kurz(titel, 35) == erwartet


@pytest.mark.parametrize("titel,erwartet", [
    ("Berater (Senior)", "Berater_Senior"),
    ("Mitarbeiter(in) Vertrieb", "Mitarbeiterin_Vertrieb"),     # heutiges Verhalten, bewusst nicht geändert
    ("Ingenieur(e)", "Ingenieure"),
    ("Kundenberater*in", "Kundenberaterin"),
    ("Leiter (m/w/d) Vertrieb", "Leiter_Vertrieb"),
    ("Manager (EMEA)", "Manager_EMEA"),
    ("Pflegekraft (w/m/d) Station A(1)", "Pflegekraft_Station_A1"),
    ("Conductor/a repartidor/a", "Conductor_a_repartidor_a"),   # Spec: nicht anfassen
    ("Kaufmann/-frau für Büromanagement", "Kaufmann_-frau_fuer_Bueromanagement"),
    ("Head of IT - Infrastructure", "Head_of_IT_-_Infrastructure"),
])
def test_rolle_deutsche_und_englische_titel_bleiben_wie_vor_der_aenderung(titel, erwartet):
    from app.naming import _rolle_kurz

    assert _rolle_kurz(titel, 35) == erwartet


def test_cv_dateiname_entregador_a(name_muster):
    from app.naming import cv_filename

    assert cv_filename("Coca-Cola FEMSA", "Motorista Entregador(a)", "PT") == \
        "CV_MaxMustermann_Coca-Cola_FEMSA_Motorista_Entregador_PT"


# ── Falle: Bestandsdateien dürfen nicht verwaisen ───────────────────────────────────────────
def test_cv_bestandsdatei_ohne_akzente_wird_beim_erneuten_export_umgestellt(
        session, tmp_path, monkeypatch, name_muster):
    """Eine CV-Datei, die vor der Änderung `Crdit_Muster` hieß, bekommt beim erneuten Export den
    neuen Namen. Kein `_2`, kein Waise; die alte PDF wandert in den Papierkorb."""
    from app import naming
    from app.models import CVVersion

    cv_export, cleanup = _patch_project_root(monkeypatch, tmp_path)
    monkeypatch.setattr(cv_export, "to_pdf", _fake_to_pdf)
    firma, job = _stelle(session, "Crédit Muster", "Directeur", "p293|cv1")
    alt = "CV_MaxMustermann_Crdit_Muster_Directeur_FR"
    neu = naming.cv_filename(firma.name, job.title, "FR")
    assert neu == "CV_MaxMustermann_Credit_Muster_Directeur_FR"
    ordner = tmp_path / "outputs" / "cv"
    _docx_mit_text(ordner / f"{alt}.docx", ["Max Muster", "EXECUTIVE SUMMARY"])
    (ordner / f"{alt}.pdf").write_bytes(b"%PDF-1.4 ALT\n")
    cv = CVVersion(job_id=job.id, language="FR", kind="tailored", status="fertig",
                   file_path=f"outputs/cv/{alt}.docx", pdf_path=f"outputs/cv/{alt}.pdf")
    session.add(cv)
    session.commit()
    session.refresh(cv)

    out = cv_export.export(cv.id)

    assert out["docx"] == f"outputs/cv/{neu}.docx" and out["pdf"] == f"outputs/cv/{neu}.pdf"
    assert sorted(p.name for p in ordner.iterdir()) == [f"{neu}.docx", f"{neu}.pdf"]
    assert any(alt in p.name for p in cleanup.PAPIERKORB.glob("*"))


def test_anschreiben_bestandsdatei_ohne_akzente_wird_umgestellt(session, tmp_path, monkeypatch, name_muster):
    from app import naming
    from app.models import Application

    cv_export, cleanup = _patch_project_root(monkeypatch, tmp_path)
    monkeypatch.setattr(cv_export, "to_pdf", _fake_to_pdf)
    firma, job = _stelle(session, "Logística Peñón", "Conductor", "p293|cl1")
    alt = "CoverLetter_MaxMustermann_Logstica_Pen_Conductor_ES"
    neu = naming.cover_letter_filename(firma.name, job.title, "ES")
    ordner = tmp_path / "outputs" / "anschreiben"
    _docx_mit_text(ordner / f"{alt}.docx", ["Max Muster", "Atentamente,"])
    (ordner / f"{alt}.pdf").write_bytes(b"%PDF-1.4 ALT\n")
    app = Application(job_id=job.id, status="Beworben", cover_letter_language="ES",
                      cover_letter_path=f"outputs/anschreiben/{alt}.docx",
                      cover_letter_pdf_path=f"outputs/anschreiben/{alt}.pdf")
    session.add(app)
    session.commit()
    session.refresh(app)

    out = cv_export.export_cover_letter(app.id)

    assert out["docx"] == f"outputs/anschreiben/{neu}.docx"
    assert sorted(p.name for p in ordner.iterdir()) == [f"{neu}.docx", f"{neu}.pdf"]
    assert any(alt in p.name for p in cleanup.PAPIERKORB.glob("*"))
