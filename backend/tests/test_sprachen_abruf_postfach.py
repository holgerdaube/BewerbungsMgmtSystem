"""Anzeigen-Abruf und Postfach-Suche in Französisch, Italienisch, Spanisch, Portugiesisch.

Zwei Teile:
  * `verify_jobs.check_url`: Geschlossen- und Login-Marker der Sprachtabelle (`bewerbungssprache`) an
    kurzen Ausschnitten ECHTER öffentlicher Seiten (Stand 03.11.2026) — geschlossene wie offene. Die
    offenen Ausschnitte sind der eigentliche Schutz: Ein Besetzt-Marker schlägt im Seitentext alles,
    auch den Titel, und darf auf offenen Anzeigen nie stehen. Geprüft gegen rund 50 offene Seiten von
    randstad.fr/.it/.es/.pt, hellowork.com, vagas.com.br und net-empregos.com: kein Treffer.
  * `mail_suchlisten`: wann die zweite Suche des Skills `email-check` läuft (Schalter `--sprachen`),
    mit welchen Wörtern, und dass ihre Query nicht länger wird als die Haupt-Query.

Netz wird nie berührt (`httpx.Client.get` ersetzt). Die Postfach-Tests laufen auf einer eigenen
SQLite-Datei im tmp-Ordner, nicht auf der geteilten Test-DB. Keine app.*-/pipeline.*-Importe auf
Modulebene (Konvention conftest.py). Namen und Firmen sind die aus den öffentlichen Seiten.
"""
import re
from pathlib import Path

import pytest

SKILL_EMAIL_CHECK = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "email-check" / "SKILL.md"


# ── Abruf: check_url mit Seitenausschnitten ─────────────────────────────────────────────────
def _befund(monkeypatch, titel, firma, text):
    import httpx
    from pipeline import verify_jobs

    seite = f"<html><body><h1>{titel}</h1><p>{firma}</p><p>{text}</p></body></html>"

    def _fake_get(self, url):
        return httpx.Response(200, text=seite, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", _fake_get)
    return verify_jobs.check_url("https://example.com/emploi/12345", firma, titel)


# Geschlossene Anzeigen, Wortlaut von echten Seiten (Ausschnitt). Ohne die neuen Marker blieb jede
# davon `OK` oder `INHALT_UNKLAR`.
GESCHLOSSEN = [
    ("PT-BR vagas.com.br", "Analista de Credenciamento Junior", "Trasmontano",
     "Que pena, esta vaga está indisponível. As inscrições estão encerradas."),
    ("PT-BR (Prüfbericht)", "Motorista Entregador", "Coca-Cola",
     "Ops! Esta vaga não está mais disponível"),
    ("PT randstad.pt", "Motorista", "Randstad",
     "Lamentamos mas este emprego já não se encontra disponível. Quer receber oportunidades semelhantes?"),
    ("FR randstad.fr", "Chauffeur livreur PL F/H", "Randstad",
     "Désolé, cette offre n'est plus disponible. Recevez nos offres par email."),
    ("IT randstad.it", "Autista consegnatario", "Randstad",
     "Siamo spiacenti, questa offerta di lavoro non è più disponibile. Questa offerta di lavoro è "
     "scaduta o è stata rimossa."),
]


@pytest.mark.parametrize("herkunft,titel,firma,text", GESCHLOSSEN, ids=[g[0] for g in GESCHLOSSEN])
def test_geschlossene_echte_seiten_werden_erkannt(monkeypatch, herkunft, titel, firma, text):
    from pipeline import verify_jobs

    pr = _befund(monkeypatch, titel, firma, text)
    assert pr["befund"] == "ABGELAUFEN", pr
    assert verify_jobs.portal_status(pr) == "geschlossen"


def test_geschlossen_auch_wenn_titel_und_firma_noch_dastehen(monkeypatch):
    """Die geschlossene Seite zeigt Titel und Firma weiter; der Marker gewinnt (wie bei DE/EN)."""
    pr = _befund(monkeypatch, "Motorista Entregador", "Coca-Cola",
                 "Motorista Entregador Coca-Cola. Esta vaga não está mais disponível.")
    assert pr["befund"] == "ABGELAUFEN"


def test_jeder_geschlossen_marker_der_tabelle_greift(monkeypatch):
    from pipeline import bewerbungssprache

    for marker in bewerbungssprache.alle_marker("geschlossen"):
        pr = _befund(monkeypatch, "Stelle ohne Bezug", "Firma ohne Bezug", f"Hinweis: {marker}.")
        assert pr["befund"] == "ABGELAUFEN", marker


# Offene Anzeigen. Jeder Ausschnitt steht so auf echten offenen Seiten (Anmelde-Hinweise im Kopf,
# Oberflächentexte, Fließtext) und darf nicht kippen.
OFFEN = [
    ("FR hellowork.com", "Livreur Colis Indépendant", "SLOOP",
     "Connectez-vous à votre compte pour postuler. Nous cherchons la personne la plus disponible "
     "pour la tournée du matin."),
    ("PT randstad.pt", "Motorista de distribuição", "Randstad",
     "Para se candidatar a este emprego, faça login. Inicie sessão para guardar a pesquisa."),
    ("PT-BR vagas.com.br", "Motorista Entregador", "Coca-Cola",
     "Seja uma das primeiras pessoas a se candidatar! Faça login e veja as vagas com mais match."),
    ("ES", "Conductor repartidor", "Randstad",
     "Inicia sesión para guardar tu búsqueda. Su sesión ha caducado: vuelva a entrar."),
    ("IT", "Autista consegnatario", "Randstad",
     "Accedi per salvare l'offerta. Il lavoro non è più lontano di quanto pensi."),
    ("FR randstad.fr", "Chauffeur livreur", "Randstad",
     "Connectez-vous pour postuler. Cette offre est disponible dès maintenant, le poste est plus "
     "disponible en horaires de nuit."),
]


@pytest.mark.parametrize("herkunft,titel,firma,text", OFFEN, ids=[o[0] for o in OFFEN])
def test_offene_seiten_kippen_nicht(monkeypatch, herkunft, titel, firma, text):
    pr = _befund(monkeypatch, titel, firma, text)
    assert pr["befund"] == "OK", pr


def test_infojobs_sperre_ist_eine_login_wand(monkeypatch):
    """Echte Bot-Seite von InfoJobs auf Spanisch: weder Titel noch Firma auf der Seite → Login-Wand
    (bisher `INHALT_UNKLAR`, weil das BMS die Sperre nicht kannte)."""
    import httpx
    from pipeline import verify_jobs

    def _fake_get(self, url):
        return httpx.Response(200, text="<html><body><p>No podemos identificar tu navegador. "
                              "Inicia sesión para continuar.</p></body></html>",
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", _fake_get)
    pr = verify_jobs.check_url("https://example.com/oferta/1", "Randstad", "Conductor repartidor")
    assert pr["befund"] == "LOGIN_WALL"
    assert verify_jobs.portal_status(pr) == "unklar"
    assert "no podemos identificar tu navegador" in pr["beleg"].lower()


@pytest.mark.parametrize("satz", [
    "Connectez-vous pour voir cette offre.", "Faça login para ver esta vaga.",
    "Inicie sessão para ver o emprego.", "Accedi per vedere l'offerta.",
])
def test_login_seiten_in_den_vier_sprachen(monkeypatch, satz):
    import httpx
    from pipeline import verify_jobs

    def _fake_get(self, url):
        return httpx.Response(200, text=f"<html><body><p>{satz}</p></body></html>",
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", _fake_get)
    pr = verify_jobs.check_url("https://example.com/job/1", "Beispiel Firma", "Beispiel Titel")
    assert pr["befund"] == "LOGIN_WALL", satz


def test_deutsch_und_englisch_bleiben_gleich(monkeypatch):
    """DE-/EN-Listen unverändert und vorn: gleicher Befund, gleicher Beleg wie bisher."""
    from pipeline import verify_jobs

    n = len(verify_jobs.BESETZT_TEXT_MARKERS)
    assert verify_jobs._BESETZT_ALLE[:n] == verify_jobs.BESETZT_TEXT_MARKERS
    assert verify_jobs._LOGIN_ALLE[:len(verify_jobs.LOGIN_MARKERS)] == verify_jobs.LOGIN_MARKERS
    assert verify_jobs.BESETZT_TEXT_MARKERS[:2] == ("no longer accepting applications", "no longer available")
    for text, marker in [("This position is no longer available.", "no longer available"),
                         ("Diese Stelle ist besetzt.", "stelle ist besetzt")]:
        pr = _befund(monkeypatch, "Delivery Executive", "Beispiel", text)
        assert pr["befund"] == "ABGELAUFEN" and f"'{marker}'" in pr["beleg"], pr


# ── Postfach: wann läuft die zweite Suche, mit welchen Wörtern ──────────────────────────────
@pytest.fixture()
def eigene_db(tmp_path, monkeypatch):
    """Eigene SQLite-Datei und eigener `data/cv_basis`-Ordner: Die geteilte Test-DB behält Zeilen
    anderer Tests (auch laufende Bewerbungen auf FR/ES), das würde `sprachen()` verfälschen."""
    from sqlmodel import SQLModel, create_engine
    from pipeline import mail_suchlisten as ms

    engine = create_engine(f"sqlite:///{tmp_path / 'suchlisten.sqlite'}")
    SQLModel.metadata.create_all(engine)
    (tmp_path / "data" / "cv_basis").mkdir(parents=True)
    monkeypatch.setattr(ms, "engine", engine)
    monkeypatch.setattr(ms, "init_db", lambda: None)
    monkeypatch.setattr(ms, "DATA_DIR", tmp_path / "data")
    return engine, tmp_path / "data" / "cv_basis"


def _bewerbung(engine, status, cv=None, anschreiben=None, geloescht=False):
    import datetime
    import uuid
    from sqlmodel import Session
    from app.models import Application, CVVersion, Job

    with Session(engine) as s:
        job = Job(company_name="Beispiel", title="Stelle", status=status, dedup_key=uuid.uuid4().hex,
                  deleted_at=datetime.datetime(2026, 11, 1) if geloescht else None)
        s.add(job)
        s.commit()
        s.refresh(job)
        if cv:
            s.add(CVVersion(job_id=job.id, language=cv, kind="tailored"))
        if anschreiben:
            s.add(Application(job_id=job.id, cover_letter_language=anschreiben))
        s.commit()


def test_ohne_fremdsprache_bleibt_die_liste_leer(eigene_db):
    from pipeline import mail_suchlisten as ms

    engine, cv_basis = eigene_db
    (cv_basis / "base_de.docx").write_bytes(b"x")
    (cv_basis / "base_en.docx").write_bytes(b"x")
    (cv_basis / "base_nl.docx").write_bytes(b"x")          # Sprache ohne Tabelleneintrag: keine Wörter
    _bewerbung(engine, "Beworben", cv="DE", anschreiben="EN")
    _bewerbung(engine, "Interview", cv="en")
    assert ms.sprachen() == []


def test_basis_cv_in_fremdsprache_schaltet_die_suche_ein(eigene_db):
    from pipeline import mail_suchlisten as ms

    _, cv_basis = eigene_db
    (cv_basis / "base_pt.docx").write_bytes(b"x")
    (cv_basis / "base_fr.docx").write_bytes(b"x")
    assert ms.sprachen() == ["FR", "PT"]                   # Tabellenreihenfolge


def test_laufende_bewerbung_in_fremdsprache_schaltet_die_suche_ein(eigene_db):
    from pipeline import mail_suchlisten as ms

    engine, _ = eigene_db
    _bewerbung(engine, "Beworben", cv="es")                # klein geschrieben, wie vom Modell gesetzt
    _bewerbung(engine, "Interview", anschreiben="it")
    _bewerbung(engine, "Angebot", cv="DE", anschreiben="pt-BR")
    assert ms.sprachen() == ["IT", "ES", "PT"]


def test_nicht_laufende_oder_geloeschte_bewerbungen_zaehlen_nicht(eigene_db):
    from pipeline import mail_suchlisten as ms

    engine, _ = eigene_db
    _bewerbung(engine, "Absage", cv="FR")
    _bewerbung(engine, "Prüfen", cv="FR", anschreiben="FR")
    _bewerbung(engine, "Beworben", cv="FR", geloescht=True)
    assert ms.sprachen() == []


def test_cli_sprachen_leer_und_gefuellt(eigene_db, capsys):
    from pipeline import mail_suchlisten as ms

    engine, cv_basis = eigene_db
    ms.main(["--sprachen"])
    assert [z.rstrip() for z in capsys.readouterr().out.splitlines()] == ["SPRACHEN:"]
    (cv_basis / "base_fr.docx").write_bytes(b"x")
    ms.main(["--sprachen"])
    zeilen = capsys.readouterr().out.splitlines()
    assert [z.split(":", 1)[0] for z in zeilen] == ["SPRACHEN", "SPRACHEN_BETREFF", "SPRACHEN_ABSENDER"]
    assert zeilen[0] == "SPRACHEN: FR"
    assert "candidature OR entretien" in zeilen[1]
    assert "candidatura" not in zeilen[1]                  # nur die Wörter der Sprache


def test_ausgabe_ohne_schalter_bleibt_wie_bisher(eigene_db, capsys):
    """Auch mit Fremdsprache: kein SPRACHEN in der Standardausgabe, drei Zeilen wie immer."""
    from pipeline import mail_suchlisten as ms

    _, cv_basis = eigene_db
    (cv_basis / "base_es.docx").write_bytes(b"x")
    ms.main()
    assert [z.split(":", 1)[0] for z in capsys.readouterr().out.splitlines()] == [
        "ADRESSEN", "DOMAINS", "OHNE_MAIL"]


def test_woerter_aus_der_tabelle_ohne_kurze_und_ohne_werbewoerter():
    from pipeline import bewerbungssprache, mail_suchlisten as ms

    w = ms.sprachen_woerter(ms.FREMDSPRACHEN)
    assert ms.FREMDSPRACHEN == ("FR", "IT", "ES", "PT")
    assert set(w["betreff"]) == set(bewerbungssprache.alle_marker("mail_betreff", ms.FREMDSPRACHEN))
    assert "rh" not in w["absender"] and "rh" in bewerbungssprache.alle_marker("mail_absender")
    assert {x for x in bewerbungssprache.alle_marker("mail_absender", ms.FREMDSPRACHEN)
            if len(x) >= ms.ABSENDER_MIN_LAENGE} == set(w["absender"])
    for wort in w["betreff"] + w["absender"]:
        assert re.fullmatch(r"[a-zçéèêàâùûôîïñáíóúãõ-]+", wort), wort          # nichts, was die Query bricht
    assert "oferta" not in w["betreff"] and "vaga" not in w["betreff"]
    assert len(w["betreff"]) == len(set(w["betreff"]))


# ── Skill: zweite Suche, Länge ──────────────────────────────────────────────────────────────
def _skill_queries():
    text = SKILL_EMAIL_CHECK.read_text(encoding="utf-8")
    return text, re.findall(r"--query '([^']*)'", text)


def test_zweite_suche_steht_im_skill_und_die_haupt_query_ist_unberuehrt():
    text, queries = _skill_queries()
    assert "newer_than:2d -in:chats -category:promotions" in queries[0]
    assert "<SPRACHEN_BETREFF" not in queries[0] and "<SPRACHEN_ABSENDER" not in queries[0]
    zweite = [q for q in queries if "<SPRACHEN_BETREFF" in q]
    assert len(zweite) == 1
    assert "<SPRACHEN_ABSENDER" in zweite[0]
    assert "pipeline.mail_suchlisten --sprachen" in text
    assert "Ist `SPRACHEN` leer, Schritt 1c ganz überspringen" in text


def test_zweite_suche_hat_dieselben_ausschluesse_wie_die_haupt_query():
    _, queries = _skill_queries()
    haupt = queries[0]
    zweite = next(q for q in queries if "<SPRACHEN_BETREFF" in q)
    ausschluss = haupt[:haupt.index("(subject:(")]
    assert zweite.startswith(ausschluss), "Rahmen und Ausschlüsse weichen von der Haupt-Query ab"


def test_zweite_suche_bleibt_kuerzer_als_die_haupt_query():
    """Der Skill warnt, dass zu lange Abfragen scheitern (Schritt 1b). Eine Grenze steht dort nicht;
    belegt ist die Haupt-Query, die täglich läuft. Die zweite Suche darf sie auch im ungünstigsten
    Fall (alle vier Sprachen) nicht überschreiten."""
    from pipeline import mail_suchlisten as ms

    _, queries = _skill_queries()
    zweite = next(q for q in queries if "<SPRACHEN_BETREFF" in q)
    w = ms.sprachen_woerter(ms.FREMDSPRACHEN)
    voll = (zweite.replace("<SPRACHEN_BETREFF von oben>", " OR ".join(w["betreff"]))
                  .replace("<SPRACHEN_ABSENDER von oben>", " OR ".join(w["absender"])))
    assert "<" not in voll and "'" not in voll
    assert len(voll) <= len(queries[0]), (len(voll), len(queries[0]))
    assert len(voll) < 1500                                  # feste Obergrenze, falls die Haupt-Query wächst


def test_alle_woerter_der_quelle_kommen_in_der_zweiten_suche_vor():
    """Betreff- und Absender-Wörter der Tabelle stehen weder in der Haupt-Query noch fehlen sie in
    der Ausgabe von `mail_suchlisten`: Der Skill trägt sie nicht fest, er liest sie aus den Zeilen."""
    from pipeline import bewerbungssprache, mail_suchlisten as ms

    text, queries = _skill_queries()
    haupt = queries[0].lower()
    ausgabe = ms.sprachen_woerter(ms.FREMDSPRACHEN)
    for wort in bewerbungssprache.alle_marker("mail_betreff", ms.FREMDSPRACHEN):
        assert wort in ausgabe["betreff"]
        assert not re.search(rf"\b{re.escape(wort)}\b", haupt), wort
    for wort in ausgabe["absender"]:
        assert not re.search(rf"\b{re.escape(wort)}\b", haupt), wort
