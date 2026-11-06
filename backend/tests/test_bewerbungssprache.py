"""Bewerbungssprachen (DE, EN, FR, IT, ES, PT): die EINE Tabelle `pipeline.bewerbungssprache`.

Geprüft werden die Tabelle selbst (vollständig, kleingeschrieben, ohne Doppelte zu den bestehenden
DE- und EN-Markern in `verify_jobs` und im Skill `email-check`), das Datum je Sprache, die
Spracherkennung über Stoppwörter an Beispieltexten und die Grußformeln. Alle Texte sind erfunden.
Das Modul importiert nichts aus `app.*`; die Vergleichslisten aus `verify_jobs` und dem Skill
werden nur gelesen.
"""
import datetime
import re
from pathlib import Path

import pytest

SKILL_EMAIL_CHECK = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "email-check" / "SKILL.md"
DATUM = datetime.date(2026, 11, 3)


def _quelle():
    from pipeline import bewerbungssprache
    return bewerbungssprache


# ── Tabelle ─────────────────────────────────────────────────────────────────────────────────
def test_tabelle_hat_alle_sechs_sprachen_in_fester_reihenfolge():
    b = _quelle()
    assert b.CODES == ("DE", "EN", "FR", "IT", "ES", "PT")
    assert all(b.SPRACHEN[c].code == c for c in b.CODES)


def test_tabelle_vollstaendig_und_kleingeschrieben():
    b = _quelle()
    listen = ("grussformeln", "grussformeln_anfang", "betreff_woerter", "stoppwoerter",
              "geschlossen", "login", "mail_betreff", "mail_absender")
    for c, s in b.SPRACHEN.items():
        assert len(s.fusszeile) == 2 and all(isinstance(t, str) for t in s.fusszeile), c
        assert len(s.monate) == 12 and len(set(s.monate)) == 12, c
        assert s.grussformeln and s.betreff_woerter and s.stoppwoerter, c
        for feld in listen:
            for wort in getattr(s, feld):
                assert wort == wort.lower() and wort == wort.strip() and wort, (c, feld, wort)
    # die vier neuen Sprachen tragen auch alle Marker-Felder
    for c in ("FR", "IT", "ES", "PT"):
        for feld in b.FELDER_MARKER:
            assert getattr(b.SPRACHEN[c], feld), (c, feld)


def test_tabelle_spec_inhalte_stichprobe():
    b = _quelle().SPRACHEN
    assert b["FR"].fusszeile == ("Page ", " sur ")
    assert b["IT"].fusszeile == ("Pagina ", " di ")
    assert b["ES"].fusszeile == b["PT"].fusszeile == ("Página ", " de ")
    assert "cordialement" in b["FR"].grussformeln and "veuillez agréer" in b["FR"].grussformeln_anfang
    assert "inscrições estão encerradas" in b["PT"].geschlossen
    assert "não está mais disponível" in b["PT"].geschlossen
    assert "no podemos identificar tu navegador" in b["ES"].login
    assert "accedi per" in b["IT"].login
    assert "risorseumane" in b["IT"].mail_absender
    # Spec Fix 4: `oferta` und `vaga` treffen auch Werbung und stehen nicht im Betreff
    assert "oferta" not in b["ES"].mail_betreff and "vaga" not in b["PT"].mail_betreff


def test_alle_marker_ohne_doppelte_in_tabellenreihenfolge():
    b = _quelle()
    betreff = b.alle_marker("mail_betreff")
    assert len(betreff) == len(set(betreff))
    assert betreff.count("candidatura") == 1          # steht in IT, ES und PT
    assert betreff.index("candidature") < betreff.index("candidatura") < betreff.index("entrevista")
    assert b.alle_marker("mail_betreff", ["pt"]) == ("candidatura", "entrevista", "recrutamento")
    assert "rh" in b.alle_marker("mail_absender") and b.alle_marker("mail_absender").count("rh") == 1


# ── Keine Doppelungen zu den bestehenden DE- und EN-Markern ─────────────────────────────────
def _skill_woerter() -> set:
    """Stichwörter der Haupt-Query im Skill `email-check` (Betreff- und Absender-Gruppen)."""
    text = SKILL_EMAIL_CHECK.read_text(encoding="utf-8")
    query = re.search(r"--query '([^']*)'", text).group(1)
    woerter = set()
    for gruppe in re.findall(r"(?:subject|from):\(([^)]*)\)", query):
        for teil in gruppe.split(" OR "):
            woerter.add(teil.strip().strip('"').lower())
    return woerter


def _ohne_ueberlappung(neu, alt, was):
    for wort in neu:
        assert wort not in alt, f"{was}: {wort!r} steht schon in den DE-/EN-Markern"
        for a in alt:
            assert a not in wort, f"{was}: {wort!r} enthält den DE-/EN-Marker {a!r}"


def test_geschlossen_und_login_ohne_doppelte_zu_verify_jobs():
    from pipeline import verify_jobs
    b = _quelle()
    _ohne_ueberlappung(b.alle_marker("geschlossen"), verify_jobs.BESETZT_TEXT_MARKERS, "geschlossen")
    _ohne_ueberlappung(b.alle_marker("login"), verify_jobs.LOGIN_MARKERS, "login")


def test_mail_woerter_ohne_doppelte_zur_haupt_query_im_skill():
    b = _quelle()
    alt = _skill_woerter()
    assert {"bewerbung", "interview", "karriere", "hr"} <= alt          # Prämisse: richtig gelesen
    for feld in ("mail_betreff", "mail_absender"):
        for wort in b.alle_marker(feld):
            assert wort not in alt, f"{feld}: {wort!r} steht schon in der Haupt-Query"


# ── Datum ───────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("code,erwartet", [
    ("DE", "03.11.2026"),
    ("EN", "3 November 2026"),
    ("FR", "3 novembre 2026"),
    ("IT", "3 novembre 2026"),
    ("ES", "3 de noviembre de 2026"),
    ("PT", "3 de novembro de 2026"),
])
def test_datum_text_alle_sechs_sprachen(code, erwartet):
    assert _quelle().datum_text(DATUM, code) == erwartet


def test_datum_text_deutsch_ist_wie_strftime():
    b = _quelle()
    for tag in (datetime.date(2026, 1, 5), datetime.date(2026, 12, 31), datetime.date(2027, 2, 28)):
        assert b.datum_text(tag, "DE") == tag.strftime("%d.%m.%Y")


def test_datum_text_ohne_sprache_deutsch_unbekannte_iso_und_kleinschreibung():
    b = _quelle()
    assert b.datum_text(DATUM, None) == b.datum_text(DATUM, "") == "03.11.2026"
    assert b.datum_text(DATUM, "nl") == "2026-11-03"          # nie ein deutscher Punkt
    assert b.datum_text(DATUM, "fr") == "3 novembre 2026"
    assert b.datum_text(DATUM, "pt-BR") == "3 de novembro de 2026"


def test_datum_text_erster_im_monat_und_monatsnamen():
    b = _quelle()
    assert b.datum_text(datetime.date(2026, 1, 1), "FR") == "1er janvier 2026"
    assert b.datum_text(datetime.date(2026, 1, 1), "IT") == "1 gennaio 2026"
    assert b.datum_text(datetime.date(2026, 8, 9), "FR") == "9 août 2026"
    assert b.datum_text(datetime.date(2026, 3, 9), "PT") == "9 de março de 2026"
    assert b.datum_text(datetime.date(2026, 9, 30), "ES") == "30 de septiembre de 2026"


def test_normiere_code():
    b = _quelle()
    assert b.normiere_code(None) is None and b.normiere_code("  ") is None
    assert b.normiere_code("fr") == "FR" and b.normiere_code("en-US") == "EN"
    assert b.normiere_code("pt_BR") == "PT" and b.normiere_code("English") == "EN"
    assert b.normiere_code("Deutsch") == "DE" and b.normiere_code("German") == "DE"
    assert b.normiere_code("nl") == "NL"                         # unbekannt bleibt unbekannt
    assert b.sprache("nl") is None and b.sprache("it").code == "IT"


# ── Fußzeilen-Wörter ────────────────────────────────────────────────────────────────────────
def test_fusszeilen_labels():
    b = _quelle()
    assert b.fusszeilen_labels("DE") == ("Seite ", " von ")
    assert b.fusszeilen_labels("en-US") == ("Page ", " of ")
    assert b.fusszeilen_labels("fr") == ("Page ", " sur ")
    assert b.fusszeilen_labels(None) == b.fusszeilen_labels("") == ("Seite ", " von ")   # Altbestand
    assert b.fusszeilen_labels("NL") == ("", " / ")                                      # nicht Deutsch


# ── Stoppwörter und Spracherkennung ─────────────────────────────────────────────────────────
BEISPIELE = {
    "DE": ("Wir suchen für unser Unternehmen eine erfahrene Fachkraft. Ihre Aufgaben sind die "
           "Betreuung der Kunden sowie die Planung der Touren. Sie bringen Erfahrung mit und "
           "haben Kenntnisse in der Logistik."),
    "EN": ("We are looking for a driver to join our team. Your responsibilities include delivering "
           "parcels to customers. You will have experience with the role and the requirements "
           "are listed below."),
    "FR": ("Nous recherchons pour notre entreprise un livreur. Vos missions : livrer les colis dans "
           "la région. Vous avez une expérience de la conduite et vous êtes autonome. Rejoignez "
           "notre équipe pour un poste en CDI avec des avantages."),
    "IT": ("Cerchiamo un autista consegnatario per la nostra azienda. Il candidato ideale ha "
           "esperienza nella guida e conosce la zona. Requisiti: patente B e disponibilità al "
           "lavoro su turni. Offriamo un contratto stabile."),
    "ES": ("Buscamos un conductor repartidor para nuestro equipo en Lorca. Tus funciones serán el "
           "reparto de paquetes. Ofrecemos un puesto estable, con experiencia mínima de dos años. "
           "Los candidatos deben tener el carnet y disponibilidad para las rutas del trabajo."),
    "PT": ("Procuramos um motorista de distribuição para a nossa equipa em Lisboa. Os candidatos "
           "devem ter experiência de condução e disponibilidade. Oferecemos uma vaga com contrato "
           "e também formação. Não são necessários anos de experiência."),
}


@pytest.mark.parametrize("code", ["DE", "EN", "FR", "IT", "ES", "PT"])
def test_erkenne_sprache_an_beispielanzeigen(code):
    assert _quelle().erkenne_sprache(BEISPIELE[code]) == code


@pytest.mark.parametrize("code", ["DE", "EN", "FR", "IT", "ES", "PT"])
def test_erkenne_sprache_auch_bei_kurzen_ausschnitten_und_grossschreibung(code):
    b = _quelle()
    kurz = " ".join(BEISPIELE[code].split(".")[:2]) + "."
    assert b.erkenne_sprache(kurz) == code
    assert b.erkenne_sprache(BEISPIELE[code].upper()) == code


def test_stoppwoerter_teilen_sich_keine_sprache():
    b = _quelle()
    gesehen = {}
    for c in b.CODES:
        assert len(b.stoppwoerter(c)) >= 18, c
        for w in b.stoppwoerter(c):
            assert w not in gesehen, f"{w!r} steht in {gesehen[w]} und {c}"
            gesehen[w] = c


def test_erkenne_sprache_gleichstand_leer_und_titel_bleiben_beim_standard():
    b = _quelle()
    assert b.erkenne_sprache("") == b.erkenne_sprache(None) == "DE"
    assert b.erkenne_sprache("Livreur Colis Indépendant Auto-Entrepreneur") == "DE"   # keine Funktionswörter
    assert b.erkenne_sprache("und and") == "DE"                 # Gleichstand DE/EN → Deutsch wie heute
    assert b.erkenne_sprache("und and", standard="EN") == "EN"
    assert b.erkenne_sprache("", standard="fr") == "FR"


def test_erkenne_sprache_de_en_wie_der_bisherige_beirat():
    """DE und EN führen dieselben Stoppwörter wie die frühere Beirat-Heuristik; für reine DE- und
    EN-Texte kommt dasselbe heraus."""
    b = _quelle()
    assert b.erkenne_sprache("Wir sind ein Unternehmen mit Erfahrung und Verantwortung") == "DE"
    assert b.erkenne_sprache("Our team will have the experience and the role") == "EN"
    assert {"und", "für", "unternehmen", "verantwortung"} <= b.stoppwoerter("DE")
    assert {"and", "responsibilities", "requirements", "about"} <= b.stoppwoerter("EN")


# ── Grußformeln ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("zeile,code", [
    ("Mit freundlichen Grüßen", "DE"), ("Mit freundlichen Grüßen,", "DE"), ("Viele Grüße", "DE"),
    ("Kind regards,", "EN"), ("Yours faithfully", "EN"), ("Regards.", "EN"),
    ("Cordialement,", "FR"), ("Bien à vous", "FR"),
    ("Veuillez agréer, Madame, Monsieur, l'expression de mes salutations distinguées.", "FR"),
    ("Cordiali saluti", "IT"), ("Distinti saluti,", "IT"),
    ("Atentamente,", "ES"), ("Un cordial saludo", "ES"),
    ("Atenciosamente,", "PT"), ("Com os melhores cumprimentos,", "PT"),
])
def test_grussformel_erkannt_und_sprache_zugeordnet(zeile, code):
    b = _quelle()
    assert b.grussformel_re().match(zeile)
    assert b.sprache_aus_grussformel("Text davor.\n\n" + zeile + "\nMax Muster") == code


@pytest.mark.parametrize("zeile", [
    "Mit freundlichen Grüßen Max Muster",       # Name in derselben Zeile: kein Schluss-Absatz
    "Ich freue mich auf Ihre Antwort.",
    "Regards the project went well",
    "Cordialement vôtre et bien plus",
    "Atentamente esperamos su respuesta",
    "",
])
def test_keine_grussformel(zeile):
    b = _quelle()
    assert not b.grussformel_re().match(zeile)
    assert b.sprache_aus_grussformel(zeile) is None


def test_grussformel_re_wie_die_alte_liste_fuer_de_und_en():
    """Die frühere Liste in `cover_letter_render` ist Teil der neuen, mehr nicht."""
    b = _quelle()
    alt = ["mit freundlichen grüßen", "freundliche grüße", "beste grüße", "viele grüße",
           "herzliche grüße", "kind regards", "best regards", "warm regards", "regards", "sincerely",
           "yours sincerely", "yours faithfully"]
    assert list(b.alle_marker("grussformeln", ["DE", "EN"])) == alt
    nur_de_en = b.grussformel_re(["DE", "EN"])
    assert not nur_de_en.match("Cordialement")


def test_betreff_re_alle_sprachen_und_de_en_wie_zuvor():
    b = _quelle()
    r = b.betreff_re()
    for zeile in ("Bewerbung als Leiter", "Application: Lead", "Subject: Lead", "Re: Stelle",
                  "Betreff Lead", "Objet : Candidature au poste", "Oggetto: candidatura",
                  "Asunto: Solicitud de empleo", "Assunto: Candidatura à vaga",
                  "Candidature au poste de chef"):
        assert r.match(zeile), zeile
    for zeile in ("Recruitment is fun", "Reorganisation", "Sehr geehrte Damen und Herren,",
                  "Madame, Monsieur,", "Gentile dottoressa Rossi,"):
        assert not r.match(zeile), zeile


def test_modul_importiert_nichts_aus_app_oder_cv_export():
    quelle = (Path(__file__).resolve().parents[1] / "pipeline" / "bewerbungssprache.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+(app|pipeline\.cv_export|cv_export)\b", quelle, re.M)
    assert not re.search(r"from pipeline import .*cv_export", quelle)
