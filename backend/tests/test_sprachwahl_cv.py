"""Sprachwahl für Lebenslauf und Beirat: Basis-CV `base_<sprache>.docx` für DE, EN, FR, IT, ES, PT.

Geprüft wird:
  * `beirat_engine._erkenne_sprache` liefert für deutsche und englische Texte dasselbe wie die frühere
    DE/EN-Heuristik (hier als Vergleichsfunktion nachgebaut), kennt jetzt auch fr, it, es, pt und bleibt bei
    Gleichstand und leerem Text auf `de`;
  * `beirat_engine._cv_text`: passende Fassung, sonst Englisch, sonst Deutsch (nur für fr, it, es, pt);
  * `main._CV_AUTOMATISCH` und die Liste der Basis-CVs auf der Profil-Seite;
  * `deepdive.register_entwurf` schreibt `CVVersion.language` einheitlich groß;
  * der Prompt von `cv-match` und die Skill-Texte tragen dieselbe Formel, ohne Pfad-Zweiteilung.
Alle Texte, Firmen und Namen sind erfunden. App-Importe in den Testfunktionen (conftest-Konvention).
"""
import re
import uuid
from pathlib import Path

import pytest

PROJEKT = Path(__file__).resolve().parents[2]
SKILLS = PROJEKT / ".claude" / "skills"
SPRACH_SKILLS = ("cv-job-match", "cv-match", "job-deepdive", "anschreiben-erstellen", "interview-vorbereiten")

DE = ("Wir sind ein Unternehmen mit Erfahrung und Verantwortung. Ihre Aufgaben sind vielfältig, "
      "wir suchen eine Leitung für unsere Teams sowie Kenntnisse in der Beratung.")
EN = ("We are a company with experience. Your responsibilities are broad and our team will have "
      "the role you are about to take. The requirements are clear.")
FR = ("Nous recherchons pour notre entreprise une personne avec de l'expérience dans les missions "
      "de notre équipe. Vous rejoignez les équipes et vos missions sont variées pour nos clients.")
IT = ("Cerchiamo per la nostra azienda una persona con esperienza e competenze nel lavoro, "
      "che sono richieste dai nostri clienti. Offriamo un ruolo nel team della sede di Milano.")
ES = ("Buscamos para nuestro equipo una persona con experiencia en las funciones del puesto. "
      "Ofrecemos trabajo estable, además de formación durante los años de contrato.")
PT = ("Procuramos para a nossa equipa uma pessoa com experiência. Você terá funções variadas "
      "e não são necessários muitos anos, além de uma vaga em Lisboa e oferecemos trabalho.")


def _alte_heuristik(text: str) -> str:
    """Die bisherige DE/EN-Heuristik des Beirats, wörtlich (Mengen und Zählung), als Vergleich."""
    de_w = {"und", "für", "mit", "ist", "sind", "eine", "einer", "unternehmen", "wir", "sie",
            "unser", "unsere", "ihre", "aufgaben", "erfahrung", "kenntnisse", "verantwortung",
            "als", "bei", "der", "die", "das", "sowie", "werden", "haben"}
    en_w = {"and", "for", "with", "is", "are", "our", "you", "we", "the", "responsibilities",
            "experience", "requirements", "role", "team", "will", "have", "your", "about"}
    woerter = re.findall(r"[a-zA-ZäöüÄÖÜß]+", (text or "").lower())
    de = sum(1 for w in woerter if w in de_w)
    en = sum(1 for w in woerter if w in en_w)
    return "en" if en > de else "de"


# ── Fix 9: Spracherkennung im Beirat ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("text,erwartet", [
    (DE, "de"), (EN, "en"), (FR, "fr"), (IT, "it"), (ES, "es"), (PT, "pt"),
])
def test_erkenne_sprache_alle_sechs_klein(text, erwartet):
    import beirat_engine as be

    assert be._erkenne_sprache(text) == erwartet


@pytest.mark.parametrize("text", [
    DE, EN, "", None, "Head of Customer Success", "Projektleiter Logistik (m/w/d)",
    "und and", "Wir suchen ein Team. We will have the role.", "Our team ist eine gute Wahl, wir haben das.",
    "Ihre Aufgaben: Betreuung der Kunden. Sie bringen Erfahrung mit und werden unser Team stärken.",
    "You will have the experience and the requirements for our role in the team.",
])
def test_deutsch_und_englisch_wie_die_alte_heuristik(text):
    import beirat_engine as be

    assert be._erkenne_sprache(text) == _alte_heuristik(text)


def test_gleichstand_und_leer_bleiben_deutsch():
    import beirat_engine as be

    assert be._erkenne_sprache("") == "de"
    assert be._erkenne_sprache(None) == "de"
    assert be._erkenne_sprache("und and") == "de"                      # Gleichstand DE/EN: Deutsch wie heute
    assert be._erkenne_sprache("Livreur Colis Indépendant") == "de"    # keine Funktionswörter: Standard


def test_deutscher_text_mit_romanischen_firmennamen_bleibt_deutsch():
    """Der Fall, den die neuen Stoppwörter gefährden könnten: deutscher Fließtext, dazwischen Namen und Begriffe aus
    anderen Sprachen. Die deutschen Treffer überwiegen, das Ergebnis bleibt `de` (wie mit der alten Heuristik)."""
    import beirat_engine as be

    text = ("Wir sind ein Unternehmen mit Erfahrung und Verantwortung. Ihre Aufgaben: Betreuung der Kunden "
            "der Société des Bains et des Hôtels de la Côte, der Compagnie des Alpes sowie der Aziende del Nord "
            "und der Empresa de Aguas del Sur. Sie werden unser Team als Leitung verstärken.")
    assert _alte_heuristik(text) == "de"
    assert be._erkenne_sprache(text) == "de"


def test_englischer_text_mit_romanischen_namen_bleibt_englisch():
    import beirat_engine as be

    text = ("We are a company with experience. Your responsibilities include the clients of Société des Bains "
            "et des Hôtels and the Compagnie des Alpes. You will have the role in our team.")
    assert _alte_heuristik(text) == "en"
    assert be._erkenne_sprache(text) == "en"


def test_ueberwiegende_fremdsprache_gewinnt_und_gleichstand_bleibt_deutsch():
    """Grenzfall mit Absicht festgehalten: Mehr romanische als deutsche Treffer ergeben die romanische Sprache,
    bei gleich vielen Treffern bleibt Deutsch. Ein Titel mit einem einzigen Funktionswort entscheidet sonst."""
    import beirat_engine as be

    assert be._erkenne_sprache("Responsable des opérations pour les clients") == "fr"
    assert be._erkenne_sprache("Leitung des opérations der Clients") == "de"     # je ein Treffer: Deutsch
    assert be._erkenne_sprache("Aufgaben im Bereich les opérations des clients") == "fr"


# ── Fix 9: Basis-CV für den Beirat ───────────────────────────────────────────────────────────
@pytest.fixture()
def basis_ordner(tmp_path, monkeypatch):
    """`artefakt_pfad` zeigt auf einen Ordner im Scratch, die Basis-CVs entstehen darin."""
    import beirat_engine as be

    def _pfad(rel):
        return tmp_path / rel

    monkeypatch.setattr(be, "artefakt_pfad", _pfad)
    return tmp_path / "data" / "cv_basis"


def _cv(ordner, code, text):
    from docx import Document

    ordner.mkdir(parents=True, exist_ok=True)
    doc = Document()
    doc.add_paragraph(text)
    doc.save(str(ordner / f"base_{code}.docx"))


def test_cv_text_nimmt_die_passende_fassung(basis_ordner):
    import beirat_engine as be

    for code in ("de", "en", "fr", "it", "es", "pt"):
        _cv(basis_ordner, code, f"Lebenslauf {code}")
    for code in ("de", "en", "fr", "it", "es", "pt"):
        text, rel = be._cv_text(code, 1000)
        assert text == f"Lebenslauf {code}"
        assert rel == f"data/cv_basis/base_{code}.docx"


@pytest.mark.parametrize("code", ["fr", "it", "es", "pt"])
def test_cv_text_fehlt_die_fassung_zuerst_englisch(basis_ordner, code):
    import beirat_engine as be

    _cv(basis_ordner, "de", "deutsch")
    _cv(basis_ordner, "en", "english")
    text, rel = be._cv_text(code, 1000)
    assert (text, rel) == ("english", "data/cv_basis/base_en.docx")


@pytest.mark.parametrize("code", ["fr", "it", "es", "pt"])
def test_cv_text_ohne_englisch_dann_deutsch(basis_ordner, code):
    import beirat_engine as be

    _cv(basis_ordner, "de", "deutsch")
    text, rel = be._cv_text(code, 1000)
    assert (text, rel) == ("deutsch", "data/cv_basis/base_de.docx")


@pytest.mark.parametrize("code", ["fr", "it", "es", "pt"])
def test_cv_text_ohne_jede_fassung_meldet_die_gewuenschte(basis_ordner, code):
    import beirat_engine as be

    basis_ordner.mkdir(parents=True, exist_ok=True)
    assert be._cv_text(code, 1000) == ("", f"data/cv_basis/base_{code}.docx")


def test_cv_text_deutsch_und_englisch_wie_bisher(basis_ordner):
    """Für `de` und `en` kein Rückfall: fehlt `base_en`, bleibt die Lücke (wie früher), es wird nichts anderes gelesen."""
    import beirat_engine as be

    _cv(basis_ordner, "de", "deutsch")
    assert be._cv_text("en", 1000) == ("", "data/cv_basis/base_en.docx")
    assert be._cv_text("de", 1000) == ("deutsch", "data/cv_basis/base_de.docx")
    assert be._cv_text("unbekannt", 1000) == ("deutsch", "data/cv_basis/base_de.docx")   # nie ein fremder Pfad
    assert be._cv_text("../../etc/passwd", 1000)[1] == "data/cv_basis/base_de.docx"


def test_stellen_kontext_nennt_die_benutzte_fassung(basis_ordner, monkeypatch):
    """Anzeige französisch, nur `base_en` vorhanden: Der Kontext nennt EN, nicht FR."""
    import beirat_engine as be

    _cv(basis_ordner, "en", "english cv")
    monkeypatch.setattr(be, "_html_text", lambda rel, limit: FR)
    from app.models import Job

    job = Job(id=1, title="Responsable", company_name="Beispiel SARL", posting_snapshot_path="data/job_postings/x.html")
    kontext, _ = be.sammle_stellen_kontext(job, None)
    assert "CV-BASIS (EN, data/cv_basis/base_en.docx)" in kontext
    assert "english cv" in kontext


# ── main: Automatik-Kennzeichen und Reihenfolge ──────────────────────────────────────────────
def test_cv_automatisch_umfasst_sechs_sprachen(client):
    import app.main as main

    assert main._CV_AUTOMATISCH == {"de", "en", "fr", "it", "es", "pt"}


def test_cv_basis_liste_kennzeichnet_sechs_sprachen_und_haelt_de_en_vorn(client, tmp_path, monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)
    ordner = tmp_path / "data" / "cv_basis"
    for code in ("pt", "nl", "fr", "en", "es", "de", "it"):
        _cv(ordner, code, "Text")
    liste = client.get("/api/profil/cv-basis").json()
    assert [e["sprache"] for e in liste] == ["de", "en", "es", "fr", "it", "nl", "pt"]
    assert {e["sprache"]: e["automatisch"] for e in liste} == {
        "de": True, "en": True, "es": True, "fr": True, "it": True, "pt": True, "nl": False}


def test_profil_hinweis_in_beiden_sprachen_gleichschluessig():
    """Beide Sprachdateien tragen dieselben Schlüssel im Block `basis_cv`; der Hinweis nennt die sechs Sprachen."""
    import json

    i18n = PROJEKT / "frontend" / "src" / "i18n"
    de = json.loads((i18n / "de" / "profil.json").read_text(encoding="utf-8"))["basis_cv"]
    en = json.loads((i18n / "en" / "profil.json").read_text(encoding="utf-8"))["basis_cv"]
    assert de.keys() == en.keys()
    for wort in ("Französisch", "Italienisch", "Spanisch", "Portugiesisch"):
        assert wort in de["hinweis"] and wort in de["nur_manuell_hinweis"]
    for wort in ("French", "Italian", "Spanish", "Portuguese"):
        assert wort in en["hinweis"] and wort in en["nur_manuell_hinweis"]
    for text in (de["hinweis"], en["hinweis"]):
        assert not re.search(r"\bP\d-\d+\b|\bPhase \d+", text)


# ── Sprachkürzel groß ────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("roh,erwartet", [
    ("fr", "FR"), ("FR", "FR"), ("en", "EN"), ("de", "DE"), ("pt", "PT"), ("en-US", "EN"), ("pt_BR", "PT"),
    ("Deutsch", "DE"), (None, None), ("", None),
])
def test_register_entwurf_schreibt_die_sprache_gross(session, tmp_path, monkeypatch, roh, erwartet):
    from app.models import CVVersion
    from pipeline import deepdive
    from tests.test_cv_export import _docx_mit_text
    from tests.test_p2_63_leser import _stelle

    monkeypatch.setattr(deepdive, "PROJECT_ROOT", tmp_path)
    _docx_mit_text(tmp_path / "data" / "cv_basis" / "entwuerfe" / "arbeit.docx", ["Erika Mustermann", "Text"])
    _, job = _stelle(session, f"Muster {uuid.uuid4().hex[:6]} GmbH", "Leitung", f"sprachwahl|{uuid.uuid4().hex}")

    ergebnis = deepdive.register_entwurf(job.id, {
        "language": roh, "kind": "tailored", "file_path": "data/cv_basis/entwuerfe/arbeit.docx"})

    session.expire_all()
    assert session.get(CVVersion, ergebnis["cv_version_id"]).language == erwartet


def test_register_deepdive_schreibt_die_sprache_gross(session, tmp_path, monkeypatch):
    from app.models import CVVersion
    from pipeline import cv_export, deepdive
    from tests.test_p2_63_leser import _stelle

    monkeypatch.setattr(deepdive, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cv_export, "export", lambda _id: {"docx": "x"})        # kein Umbenennen, kein PDF
    _, job = _stelle(session, f"Muster {uuid.uuid4().hex[:6]} GmbH", "Leitung", f"sprachwahl|{uuid.uuid4().hex}")

    ergebnis = deepdive.register(job.id, cv={"language": "it", "file_path": "outputs/cv/x.docx"})

    session.expire_all()
    assert session.get(CVVersion, ergebnis["cv_version_id"]).language == "IT"


def test_vergleiche_mit_de_en_vertragen_grosse_codes(session):
    """Die Stellen, die `language` auf Gleichheit mit DE/EN prüfen, bekommen weiter dieselben Werte: Dateiname
    und Anzeige gehen über `.upper()`, also gleich für klein und groß."""
    from app import naming

    for roh in ("de", "DE", "en", "EN", "fr", "FR"):
        assert naming.cv_filename("Muster GmbH", "Leitung", roh).endswith("_" + roh.upper())
        assert naming.cv_filename("Muster GmbH", "Leitung", roh) == naming.cv_filename("Muster GmbH", "Leitung", roh.upper())


# ── Prompt und Skills: dieselbe Formel ───────────────────────────────────────────────────────
def test_cv_match_prompt_traegt_die_formel():
    from app.agent_runner import build_prompt

    prompt = build_prompt("cv-match", 7)
    assert "base_<sprache>.docx" in prompt
    assert "de, en, fr, it, es oder pt" in prompt
    assert "zuerst base_en.docx, sonst base_de.docx" in prompt
    assert "nichts übersetzen" in prompt and "Sprachbruch melden" in prompt
    assert "base_de.docx bzw. base_en.docx" not in prompt          # nicht mehr zwei Pfade
    # Der Rest des Vertrags bleibt (Tests in test_agent_runner_prompts.py prüfen ihn einzeln)
    assert "IMMER neu" in prompt and "NEUE CVVersion" in prompt and prompt.startswith("CV-Match für Job 7")


def _skill(name, flach=True):
    """Skill-Text; `flach` fasst Zeilenumbrüche und Mehrfach-Leerzeichen zu einem Leerzeichen zusammen."""
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    return " ".join(text.split()) if flach else text


@pytest.mark.parametrize("name", SPRACH_SKILLS)
def test_skills_nennen_die_formel_und_nicht_mehr_zwei_pfade(name):
    text = _skill(name)
    assert "base_<sprache>.docx" in text
    assert "zuerst `base_en.docx`" in text or "zuerst die englische" in text
    assert "sonst `base_de.docx`" in text or "sonst die deutsche" in text
    assert "nichts übersetzen" in text
    assert "Sprachbruch" in text
    assert "base_de.docx` bzw. `data/cv_basis/base_en.docx`" not in text
    assert "`base_de.docx`/`base_en.docx`" not in text


def test_cv_job_match_hat_sprachregel_und_basis_cv_absatz_in_gleicher_formel():
    text = _skill("cv-job-match")
    regel = text[text.index("## Sprachregeln"):text.index("## Kandidat und Basis-CV")]
    absatz = text[text.index("## Kandidat und Basis-CV"):text.index("## Workflow")]
    schritt0 = text[text.index("### Schritt 0"):text.index("### Schritt 1")]
    for teil in (regel, absatz, schritt0):
        assert "base_<sprache>.docx" in teil
    assert "französische" in regel and "Fehlt bei einer französischen" in regel
    assert "base_fr.docx" in absatz
    assert "zuerst die englische, sonst die deutsche" in schritt0


@pytest.mark.parametrize("name", ["cv-match", "cv-job-match", "job-deepdive"])
def test_skills_sagen_das_sprachkuerzel_gross(name):
    text = _skill(name)
    assert "großgeschrieben" in text
    assert "`DE`" in text and "`FR`" in text


def test_anschreiben_skill_hat_die_tabelle_und_laesst_de_en_bei_den_bisherigen_regeln():
    from pipeline import bewerbungssprache as b

    text = _skill("anschreiben-erstellen", flach=False)
    assert "Auf Deutsch und auf\nEnglisch gelten die bisherigen Regeln (Schritt 3)" in text
    tabelle = text[text.index("| Sprache | Anrede"):text.index("Die Schlussformel steht als eigener Absatz")]
    zeilen = [z for z in tabelle.splitlines() if z.startswith("|")][2:]
    assert [z.split("|")[1].strip() for z in zeilen] == ["Französisch", "Italienisch", "Spanisch", "Portugiesisch"]
    for z in zeilen:
        assert "`" in z.split("|")[2] and "`" in z.split("|")[4]
    # Datum setzt der Renderer; der Skill schreibt es nicht selbst
    assert "Ort-/Datumszeile" in text and "nicht von Hand schreiben" in text
    # Jede Schlussformel der Tabelle erkennt der Renderer als Schluss-Absatz (außer dem langen Schlusssatz,
    # der über den Zeilenanfang erkannt wird)
    erkennung = b.grussformel_re()
    gefunden = re.findall(r"`([^`]*?)`", "|".join(z.split("|")[4] for z in zeilen))
    assert len(gefunden) >= 6
    for formel in gefunden:
        assert erkennung.match(formel.rstrip(",.") if not formel.startswith("Veuillez") else "Veuillez agréer"), formel


def test_anschreiben_skill_lang_wert_nennt_sechs_sprachen():
    assert 'LANG = <id>, "<DE|EN|FR|IT|ES|PT>"' in _skill("anschreiben-erstellen")
