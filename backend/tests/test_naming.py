"""Kontrakt-Tests fuer app/naming.py (Phase 57 Stufe E1.4).

Reine Funktionen -- kein DB-/App-Zugriff noetig, `app.naming` wird trotzdem NUR in den
Testfunktionen importiert (Projekt-Konvention aus conftest.py, konsistent gehalten).
Erwartungswerte stammen aus echter Ausfuehrung im venv-REPL (nicht geraten) -- diese Tests
frieren das bestehende Verhalten als Kontrakt ein, sie aendern es nie.
"""
import datetime


def test_dated_filename_format():
    from app.naming import dated_filename

    name = dated_filename("Job Search Tracker Max Mustermann", "xlsx", datetime.date(2026, 7, 9))
    assert name == "20260709_Job_Search_Tracker_Max_Mustermann.xlsx"


def test_dated_filename_leerzeichen_und_extension_punkt():
    from app.naming import dated_filename

    # ext mit fuehrendem Punkt wird toleriert (lstrip('.')); jede Whitespace-RUN wird zu genau
    # EINEM "_" (re.sub(r"\s+", "_", ...) -- kollabiert, verdoppelt nicht).
    name = dated_filename("  Mein   Report  ", ".html", datetime.date(2026, 1, 5))
    assert name == "20260105_Mein_Report.html"


def test_cv_filename_umlaut_transliteration(monkeypatch):
    import pipeline.user_profile as up
    from app.naming import cv_filename

    monkeypatch.setattr(up, "user_name", lambda: "Max Mustermann")
    name = cv_filename("Müller & Söhne GmbH", "Großkunden-Betreuer", "DE")
    assert name == "CV_MaxMustermann_Mueller_Soehne_Grosskunden-Betreuer_DE"
    assert "ü" not in name and "ö" not in name and "ß" not in name


def test_cv_filename_gender_zusatz_entfernt(monkeypatch):
    import pipeline.user_profile as up
    from app.naming import cv_filename

    monkeypatch.setattr(up, "user_name", lambda: "Max Mustermann")
    varianten = [
        "Manager (m/w/d)", "Manager (f/m/x)", "Manager (w/m/d)",
        "Manager (all genders)", "Manager (M/W/D)",
    ]
    for pos in varianten:
        name = cv_filename("Test", pos, "DE")
        assert name == "CV_MaxMustermann_Test_Manager_DE", f"Gender-Tag nicht entfernt bei {pos!r}: {name}"


def test_cv_filename_gender_zusatz_doppelpunkt_notation_entfernt(monkeypatch):
    """P3-5 (Code-Review 2026-07-25): Die Doppelpunkt-Alternative in `_GENDER_RE` erlaubte
    strukturell nur GENAU EIN Buchstaben-Paar (`[a-z]:[a-z]`) -- "(m:w:d)" (drei Buchstaben)
    blieb deshalb stehen und landete als "..._mwd_DE" im empfaengersichtbaren Dateinamen. Fix:
    dieselbe {1,4}-Wiederholungslogik wie bei der Schraegstrich-/Pipe-Alternative. "(m:w)" (zwei
    Buchstaben) funktionierte schon vorher -- als Regressions-Absicherung mit aufgenommen."""
    import pipeline.user_profile as up
    from app.naming import cv_filename

    monkeypatch.setattr(up, "user_name", lambda: "Max Mustermann")
    varianten = [
        "Manager (m:w:d)", "Manager (w:m:d)", "Manager (M:W:D)", "Manager (m:w)",
    ]
    for pos in varianten:
        name = cv_filename("Test", pos, "DE")
        assert name == "CV_MaxMustermann_Test_Manager_DE", f"Gender-Tag nicht entfernt bei {pos!r}: {name}"


def test_cv_filename_sprachsuffix_immer_gesetzt():
    from app.naming import cv_filename

    ohne_sprache = cv_filename("Test AG", "Head of Sales")
    mit_en = cv_filename("Test AG", "Head of Sales", "EN")
    assert ohne_sprache.endswith("_DE")   # Default DE, wenn keine Sprache uebergeben
    assert mit_en.endswith("_EN")
    assert ohne_sprache != mit_en   # DE/EN duerfen sich nie ueberschreiben


def test_cover_letter_filename_analog_zu_cv_filename(monkeypatch):
    import pipeline.user_profile as up
    from app.naming import cover_letter_filename

    monkeypatch.setattr(up, "user_name", lambda: "Max Mustermann")
    name = cover_letter_filename("Müller & Söhne GmbH", "Direktor (m/w/d)", "DE")
    assert name == "CoverLetter_MaxMustermann_Mueller_Soehne_Direktor_DE"

    ohne_sprache = cover_letter_filename("Test AG", "Head of Sales")
    assert ohne_sprache.endswith("_DE")   # Vorgabe vom 11.07.: Suffix IMMER, nicht nur bei EN


def test_report_filename_typ_praefix_und_companyfit_ohne_position():
    from app.naming import report_filename

    when = datetime.date(2026, 7, 9)
    # Veto-Punkt: CompanyFit bekommt NIE eine Rolle im Namen, auch wenn eine uebergeben wird.
    name_fit = report_filename("CompanyFit", "Müller & Söhne GmbH", "Direktor", when=when)
    assert name_fit == "20260709_CompanyFit_Mueller_Soehne"

    name_match = report_filename("Match", "Test AG", "Head of Sales (m/w/d)", when=when, runde=2)
    assert name_match == "20260709_Match_Test_Head_of_Sales_R2"


def test_report_filename_unbekannter_typ_wirft_valueerror():
    from app.naming import report_filename

    import pytest
    with pytest.raises(ValueError):
        report_filename("KeinGueltigerTyp", "Test AG")


# --- Phase 71A (Name aus dem Profil): cv_filename/cover_letter_filename lesen den Namen jetzt
# ueber pipeline.user_profile.user_name() statt einen Namen hart zu kodieren. Die Tests OBEN
# mocken user_name auf "Max Mustermann" (Phase-71-Abnahme: config/profil.md ist Bereich 2 und
# existiert in einem CI-Checkout NIE — ohne Mock fielen sie dort auf "Bewerber" zurueck; die
# Regression gegen das ECHTE Profil liegt in test_user_profile.py und skippt ohne die Datei).
# Die Tests HIER machen die neue Namensquelle explizit (Mock auf einen anderen Namen).

def test_cover_letter_filename_nutzt_user_name_generisch(monkeypatch):
    import pipeline.user_profile as up
    from app.naming import cover_letter_filename

    monkeypatch.setattr(up, "user_name", lambda: "Max Muster")
    name = cover_letter_filename("Test AG", "Direktor", "DE")
    assert name == "CoverLetter_MaxMuster_Test_Direktor_DE"


def test_cover_letter_filename_umlaut_name_aus_profil_mock(monkeypatch):
    import pipeline.user_profile as up
    from app.naming import cover_letter_filename

    monkeypatch.setattr(up, "user_name", lambda: "Jörg Müller")
    name = cover_letter_filename("Test AG", "Direktor", "DE")
    assert name == "CoverLetter_JoergMueller_Test_Direktor_DE"


def test_tracker_filename_generisch_nur_jahr():
    """Spec-Vorgabe 71A Punkt 5: '{JAHR}_Job_Search_Tracker_{Name}.xlsx' -- BEWUSST nur das
    Jahr (nicht das volle Datum wie dated_filename), Monat/Tag werden ignoriert."""
    import datetime
    from app.naming import tracker_filename

    name = tracker_filename("Max Muster", "xlsx", datetime.date(2026, 3, 15))
    assert name == "2026_Job_Search_Tracker_Max_Muster.xlsx"

    # Gegenprobe: ein anderer Tag im selben Jahr liefert denselben Namen (Jahr, nicht Datum).
    name_anderer_tag = tracker_filename("Max Muster", "xlsx", datetime.date(2026, 11, 30))
    assert name_anderer_tag == name


def test_tracker_filename_regression():
    """Rueckwaertskompatibilitaet (Spec Phase 71A, Leitplanke): fuer einen Beispielnamen + Jahr 2026
    exakt das bisherige Namensschema '2026_Job_Search_Tracker_Max_Mustermann.xlsx'."""
    import datetime
    from app.naming import tracker_filename

    name = tracker_filename("Max Mustermann", "xlsx", datetime.date(2026, 7, 31))
    assert name == "2026_Job_Search_Tracker_Max_Mustermann.xlsx"


def test_tracker_filename_default_jahr_ist_heute():
    import datetime
    from app.naming import tracker_filename

    name = tracker_filename("Test Name", "xlsx")
    assert name == f"{datetime.date.today().year}_Job_Search_Tracker_Test_Name.xlsx"


# =============================================================================================
# P2-63 (01.10.2026): kürzere Dateinamen. Datum JJJJMMTT, neue Typ-Wörter, Kurzform für Firma
# und Rolle. Firmen sind erfunden. Je Kernregel steht eine Gegenprobe daneben.
# =============================================================================================

def _nutzer(monkeypatch, name="Max Muster"):
    import pipeline.user_profile as up
    monkeypatch.setattr(up, "user_name", lambda: name)


def test_p263_firma_kurz_klammerzusatz_und_klient_faellt_weg():
    from app.naming import _firma_kurz

    roh = "Muster Beratung (Klient: internationale Bank, nicht genannt)"
    assert _firma_kurz(roh) == "Muster_Beratung"
    # Gegenprobe: ohne Klammer bleibt der volle Name stehen
    assert _firma_kurz("Muster Beratung") == "Muster_Beratung"


def test_p263_firma_kurz_schnittzeichen():
    from app.naming import _firma_kurz

    assert _firma_kurz("Beispiel Systeme: Region Nord") == "Beispiel_Systeme"      # Doppelpunkt
    assert _firma_kurz("Beispiel Systeme, Niederlassung Wien") == "Beispiel_Systeme"   # Komma
    assert _firma_kurz("Beispiel Systeme; Sparte A") == "Beispiel_Systeme"         # Semikolon
    assert _firma_kurz("Beispiel Systeme | Karriere") == "Beispiel_Systeme"        # Pipe
    assert _firma_kurz("Beispiel Systeme - Standort Ost") == "Beispiel_Systeme"    # Leerzeichen-Strich
    # Gegenprobe: Bindestrich OHNE Leerzeichen gehört zum Namen
    assert _firma_kurz("Muster-Beratung") == "Muster-Beratung"


def test_p263_firma_kurz_rechtsformen_am_ende():
    from app.naming import _firma_kurz

    for roh in ["Muster GmbH", "Muster AG", "Muster SE", "Muster mbH", "Muster KGaA", "Muster Inc.",
                "Muster Ltd", "Muster LLC", "Muster plc", "Muster S.A.", "Muster B.V.", "Muster N.V.",
                "Muster e.V.", "Muster GmbH & Co. KG", "Muster UG (haftungsbeschränkt)", "Muster Co."]:
        assert _firma_kurz(roh) == "Muster", roh
    # Gegenproben: Rechtsform mitten im Namen bleibt, Teil eines Wortes bleibt
    assert _firma_kurz("AG Muster") == "AG_Muster"
    assert _firma_kurz("Musterag") == "Musterag"
    assert _firma_kurz("Seeberg SE Partner") == "Seeberg_SE_Partner"
    # Besteht der Name nur aus der Rechtsform, bleibt er benennbar
    assert _firma_kurz("AG") == "AG"


def test_p263_firma_kurz_laenge_25_an_der_wortgrenze():
    from app.naming import _firma_kurz

    lang = "Muster Beratung Internationale Dienstleistungen"
    kurz = _firma_kurz(lang)
    assert kurz == "Muster_Beratung"          # 'Muster_Beratung_Internationale' wären 30
    assert len(kurz) <= 25
    # Gegenprobe: genau 25 Zeichen bleiben unverändert
    genau = "Abcdefghij_Klmnopqrs_Tuvwx"[:25]
    assert len(genau) == 25 and _firma_kurz(genau.replace("_", " ")) == genau
    # Ein einziges überlanges Wort wird hart gekürzt
    assert len(_firma_kurz("A" * 40)) == 25


def test_p263_firma_kurz_leer_und_umlaute():
    from app.naming import _firma_kurz

    assert _firma_kurz("") == "Firma"
    assert _firma_kurz(None) == "Firma"
    assert _firma_kurz("(nur Klammer)") == "Firma"
    assert _firma_kurz("Müller & Söhne GmbH") == "Mueller_Soehne"


def test_p263_rolle_laenge_bericht_30_dokument_35(monkeypatch):
    from app.naming import cv_filename, cover_letter_filename, report_filename, transcript_filename

    _nutzer(monkeypatch)
    rolle = "Head of Customer Success Europe West"
    bericht = report_filename("Match", "Test", rolle, when=datetime.date(2026, 10, 1))
    assert bericht == "20261001_Match_Test_Head_of_Customer_Success"          # 31 Zeichen > 30: Europe fällt
    cv = cv_filename("Test", rolle, "DE")
    assert cv == "CV_MaxMuster_Test_Head_of_Customer_Success_Europe_DE"       # 31 Zeichen <= 35: bleibt
    brief = cover_letter_filename("Test", rolle, "EN")
    assert brief == "CoverLetter_MaxMuster_Test_Head_of_Customer_Success_Europe_EN"
    tr = transcript_filename("Transkript", "2026-10-01", "Anna", "Test", rolle)
    assert tr == "Transkript_20261001_Anna_Test_Head_of_Customer_Success"
    # 35er-Grenze: noch ein Wort mehr (45 Zeichen) fällt auch im CV
    lang = cv_filename("Test", "Head of Customer Success Europe West Region", "DE")
    assert lang == "CV_MaxMuster_Test_Head_of_Customer_Success_Europe_DE"
    # Gegenprobe: kurze Rolle bleibt vollständig
    assert report_filename("Match", "Test", "Head of Sales", when=datetime.date(2026, 10, 1)) \
        == "20261001_Match_Test_Head_of_Sales"


def test_p263_regionszusatz_nach_strich_faellt_weg(monkeypatch):
    from app.naming import cv_filename, report_filename

    _nutzer(monkeypatch)
    assert cv_filename("Test", "Head of Delivery - DACH", "DE") == "CV_MaxMuster_Test_Head_of_Delivery_DE"
    assert cv_filename("Test", "Head of Delivery (m/w/d) - DACH", "DE") == "CV_MaxMuster_Test_Head_of_Delivery_DE"
    r = report_filename("Anzeige", "Test", "Head of Delivery - EMEA", when=datetime.date(2026, 10, 1))
    assert r == "20261001_Anzeige_Test_Head_of_Delivery"
    # Gegenprobe: Bindestrich ohne Leerzeichen bleibt
    assert cv_filename("Test", "Vice-President", "DE") == "CV_MaxMuster_Test_Vice-President_DE"


def test_p263_firma_kurz_gilt_auch_fuer_cv_und_anschreiben(monkeypatch):
    from app.naming import cv_filename, cover_letter_filename

    _nutzer(monkeypatch)
    firma = "Muster Beratung (Klient: internationale Bank, nicht genannt)"
    assert cv_filename(firma, "Lead", "DE") == "CV_MaxMuster_Muster_Beratung_Lead_DE"
    assert cover_letter_filename(firma, "Lead", "DE") == "CoverLetter_MaxMuster_Muster_Beratung_Lead_DE"


def test_p263_neue_typ_woerter_und_abbildung_der_alten():
    from app.naming import report_filename

    when = datetime.date(2026, 10, 1)
    assert report_filename("Auswertung", "Test", "Lead", when=when, runde=3) == "20261001_Auswertung_Test_Lead_R3"
    assert report_filename("Anzeige", "Test", "Lead", when=when) == "20261001_Anzeige_Test_Lead"
    assert report_filename("Beirat", "Test", "Lead", when=when) == "20261001_Beirat_Test_Lead"
    # alte Wörter als Eingabe ergeben den neuen Namen
    assert report_filename("TranskriptReport", "Test", "Lead", when=when, runde=3) == "20261001_Auswertung_Test_Lead_R3"
    assert report_filename("Stellenausschreibung", "Test", "Lead", when=when) == "20261001_Anzeige_Test_Lead"
    assert report_filename("BeiratsCheck", "Test", "Lead", when=when) == "20261001_Beirat_Test_Lead"


def test_p263_posting_filename_wie_alle_berichte():
    from app.naming import posting_filename

    heute = f"{datetime.date.today():%Y%m%d}"
    assert posting_filename("Test AG", "Lead (m/w/d)") == f"{heute}_Anzeige_Test_Lead"
    # Gegenprobe: kein Typ-Wort vorn, keine alte Form
    assert not posting_filename("Test AG", "Lead").startswith("Stellenausschreibung")


def test_p263_datum_ueberall_jjjjmmtt():
    from app.naming import _konversationsdatum, _report_date, transcript_filename

    assert _konversationsdatum("2026-10-01") == "20261001"
    assert _report_date(datetime.date(2026, 10, 1)) == "20261001"
    assert _report_date("2026-10-01") == "20261001"
    assert transcript_filename("Debrief", "2026-10-01", None, "Test", "Lead", 2) == "Debrief_20261001_Unbekannt_Test_Lead_R2"
    # Gegenprobe: kein Unterstrich-Datum mehr
    assert "_10_01" not in _report_date("2026-10-01")


def test_p263_datum_leser_beide_formate():
    from app.naming import datum_aus_name, datum_aus_praefix

    soll = datetime.date(2026, 10, 1)
    assert datum_aus_praefix("20261001_Auswertung_X.html") == soll
    assert datum_aus_praefix("2026_10_01_Match_X.html") == soll
    assert datum_aus_praefix("Match_20261001_X.html") is None
    assert datum_aus_praefix("20261399_X.html") is None            # unmögliches Datum
    assert datum_aus_praefix("202610012_X.html") is None           # neunstellig, kein Datum
    assert datum_aus_name("Transkript_20261001_Anna_X.md") == soll
    assert datum_aus_name("Transkript_2026_10_01_Anna_X.md") == soll
    assert datum_aus_name("ohne_datum.md") is None


def test_p263_alte_namen_fuer_die_weichen(monkeypatch):
    from app.naming import cv_filename, cv_filename_alt, cover_letter_filename_alt

    _nutzer(monkeypatch)
    firma = "Muster Beratung GmbH (Klient: internationale Bank)"
    assert cv_filename_alt(firma, "Lead", "EN") == \
        "CV_MaxMuster_Muster_Beratung_GmbH_Klient_internationale_Bank_Lead_EN"
    assert cv_filename(firma, "Lead", "EN") == "CV_MaxMuster_Muster_Beratung_Lead_EN"
    assert cover_letter_filename_alt("Test AG", "Lead", "DE") == "CoverLetter_MaxMuster_Test_AG_Lead_DE"


def test_rolle_behaelt_inhaltlichen_teil_nach_bindestrich():
    """Abnahme P2-63: Nur Regionszusätze fallen weg, ein inhaltlicher Teil des Titels bleibt."""
    from app.naming import _rolle_kurz

    assert _rolle_kurz("Head of IT - Infrastructure", 30) == "Head_of_IT_-_Infrastructure"
    assert _rolle_kurz("Head of Delivery - DACH", 30) == "Head_of_Delivery"
    assert _rolle_kurz("Presales Manager - Remote Germany", 30) == "Presales_Manager"
    assert _rolle_kurz("Sales Lead - Nord/Ost", 30) == "Sales_Lead"


def test_kuerzen_genau_an_der_wortgrenze_behaelt_das_letzte_wort():
    """Abnahme P2-63: Fällt die Grenze genau auf einen Unterstrich, bleibt das letzte Wort."""
    from app.naming import _truncate_words

    assert _truncate_words("Director_Professional_Services_Cloud", 30) == "Director_Professional_Services"
    assert _truncate_words("Director_Professional_Services_Cloud", 29) == "Director_Professional"
