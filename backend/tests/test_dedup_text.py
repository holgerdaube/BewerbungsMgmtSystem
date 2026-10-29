"""Kontrakt-Tests fuer pipeline/dedup_text.py (Phase 57 Stufe E1.4).

Reine Funktionen (`aehnlichkeit`, `titel_aehnlichkeit`) -- kein DB-Zugriff. `konfiguration()`
liest config/suchprofile.yaml (read-only, keine Live-Daten, nur der kalibrierte Schwellwert) --
das ist bewusst KEIN app.*/pipeline.*-Modulebene-Import (nur in Testfunktionen, wie ueberall in
dieser Suite). Alle Text-Fixtures sind synthetisch (T3).

NACHTRAG (Phase 57 Stufe E2, CI-Fix): `config/suchprofile.yaml` ist bewusst `.gitignore`'t
(das echte persoenliche Suchprofil -- T3/I2 "Repo bleibt personendatenfrei") und existiert
deshalb in einem frischen Checkout (CI!) nicht -- `konfiguration()` bricht dort mit `SystemExit`
ab. Die zwei betroffenen Tests patchen `CONFIG_FILE` deshalb auf eine synthetische, leere YAML;
`konfiguration()` faellt dann auf ihre eigenen, im Modul kodierten Defaults zurueck (0.045/0.45,
s. pipeline/dedup_text.py::konfiguration()) -- derselbe Code-Pfad wie im echten Deployment, nur
ohne den Sonderfall "Datei fehlt komplett". Die Kalibrierung selbst bleibt unangetastet.
"""


def _mit_synthetischer_leerer_config(monkeypatch, tmp_path):
    """Patcht `pipeline.dedup_text.CONFIG_FILE` auf eine synthetische, leere YAML-Datei, damit
    `konfiguration()` ihre Modul-Defaults liefert, ohne das echte (gitignorte) Suchprofil zu
    brauchen. Funktionslokaler Import von `pipeline.dedup_text` (T1-Konvention dieser Suite)."""
    import pipeline.dedup_text as dedup_text

    leere_config = tmp_path / "suchprofile.yaml"
    leere_config.write_text("dedup_text: {}\n", encoding="utf-8")
    monkeypatch.setattr(dedup_text, "CONFIG_FILE", leere_config)


def test_aehnlichkeit_identischer_text_ist_eins():
    from pipeline.dedup_text import aehnlichkeit

    text = ("Wir suchen einen erfahrenen Manager fuer den Bereich Vertrieb "
            "und Kundenbetreuung in Deutschland.")
    assert aehnlichkeit(text, text) == 1.0


def test_aehnlichkeit_disjunkte_texte_ist_null():
    from pipeline.dedup_text import aehnlichkeit

    a = "Wir suchen einen erfahrenen Manager fuer den Bereich Vertrieb und Kundenbetreuung."
    b = "Der Himmel ist blau und die Sonne scheint heute besonders hell ueber den Bergen."
    assert aehnlichkeit(a, b) == 0.0


def test_aehnlichkeit_leere_texte_ist_null():
    from pipeline.dedup_text import aehnlichkeit

    assert aehnlichkeit("", "") == 0.0


def test_titel_aehnlichkeit_nah_verwandt_vs_verschieden(monkeypatch, tmp_path):
    from pipeline.dedup_text import titel_aehnlichkeit, konfiguration

    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    schwelle = konfiguration()["titel_schwelle"]
    # "nah verwandt": Repost-artige Erweiterung desselben Titels (4 gemeinsame / 5 gesamt = 0.8)
    nah_a, nah_b = "Senior Manager Customer Success", "Senior Manager Customer Success EMEA"
    # "verschieden": komplett anderer Rollentyp, keine gemeinsamen Woerter
    versch_a, versch_b = "Senior Manager Customer Success", "Werkstudent Facility Management"

    score_nah = titel_aehnlichkeit(nah_a, nah_b)
    score_verschieden = titel_aehnlichkeit(versch_a, versch_b)

    assert score_nah >= schwelle, f"nah verwandt sollte Titel-Schwelle {schwelle} erreichen: {score_nah}"
    assert score_verschieden < schwelle, f"verschiedene Titel sollten unter {schwelle} bleiben: {score_verschieden}"


def test_aehnlichkeit_schwellwert_knapp_darueber_und_darunter(monkeypatch, tmp_path):
    """Kalibrierten Text-Schwellwert (config/suchprofile.yaml::dedup_text.schwelle, Default in
    dedup_text.konfiguration() = 0.045) referenzieren statt neu erfinden -- NICHT die Kalibrierung
    aendern, nur je einen synthetischen Fall knapp ueber/unter der Schwelle konstruieren.

    Konstruktion (5-Wort-Shingles): ein gemeinsamer Praefix von k=5 Woertern liefert genau
    EIN gemeinsames Shingle; der Rest sind je m disjunkte, eindeutige Fuellwoerter. Damit ist
    Jaccard = 1 / (2*m + 1) exakt herleitbar -- m=10 -> 1/21 (knapp drueber), m=11 -> 1/23
    (knapp drunter). Empirisch mit dem echten Modul verifiziert, nicht nur ausgerechnet.
    """
    from pipeline.dedup_text import aehnlichkeit, konfiguration

    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    schwelle = konfiguration()["schwelle"]

    def bauen(k, m):
        gemeinsam = [f"gem{i}" for i in range(k)]
        a = gemeinsam + [f"asuf{i}" for i in range(m)]
        b = gemeinsam + [f"bsuf{i}" for i in range(m)]
        return " ".join(a), " ".join(b)

    text_a, text_b = bauen(k=5, m=10)     # -> 1/21 ~= 0.0476
    score_oben = aehnlichkeit(text_a, text_b)
    assert score_oben >= schwelle

    text_a2, text_b2 = bauen(k=5, m=11)   # -> 1/23 ~= 0.0435
    score_unten = aehnlichkeit(text_a2, text_b2)
    assert score_unten < schwelle


# ── P2-37: Rohtext-Vorrang (s. tasks/spec_p2-37_rohtext_textvergleich.md §4) ────────────────
# Snapshot-Fixtures sind Klartext mit EINER Überschrift je Zeile (Format wie
# `text_aus_snapshot()` es liefert) — synthetisch, keine Live-Daten (T3).

_ENGLISCHES_ORIGINAL = (
    "We design and deliver enterprise-grade customer success programs across EMEA. "
    "The role owns renewal forecasting, escalation management and executive business "
    "reviews for our largest strategic accounts, partnering closely with sales, "
    "product and support leadership to keep churn low and expansion high. You will "
    "build repeatable playbooks, coach a team of account managers and report directly "
    "into the VP of Customer Success on quarterly business outcomes and account risk."
)


def test_rollen_relevanter_text_aus_bevorzugt_rohtext_bei_angereichertem_snapshot():
    """Test 1 (Spec §4): angereicherter Snapshot (Aufgaben/Anforderungen als deutsche
    Zusammenfassung, Benefits, „Über das Unternehmen“, „Volltext (unbereinigt)“ mit dem
    englischen Original >= 400 Zeichen, „Erfassungs-Kontext“) -- `rollen_relevanter_text_aus`
    liefert GENAU das Original: ohne Zusammenfassung, ohne Firmen-Blurb, ohne
    Erfassungs-Kontext."""
    from pipeline.dedup_text import rollen_relevanter_text_aus

    assert len(_ENGLISCHES_ORIGINAL) >= 400

    snapshot = (
        "Firma\nBeispiel AG\nOrt\nMuenchen\n"
        "Aufgaben\n"
        "Sie verantworten das Renewal-Forecasting fuer strategische Grosskunden.\n"
        "Sie eskalieren kritische Faelle und fuehren Business Reviews mit dem Kunden.\n"
        "Anforderungen\n"
        "Mehrjaehrige Erfahrung im Customer Success einer Softwarefirma.\n"
        "Benefits\n"
        "30 Tage Urlaub und ein Jobrad.\n"
        "Über das Unternehmen\n"
        "Wir sind ein fuehrender Anbieter fuer Customer-Success-Software.\n"
        "Volltext (unbereinigt)\n"
        + _ENGLISCHES_ORIGINAL + "\n"
        "Erfassungs-Kontext\n"
        "Erfasst am 20.07.2026 ueber die Karriereseite.\n"
    )

    ergebnis = rollen_relevanter_text_aus(snapshot)

    assert ergebnis == _ENGLISCHES_ORIGINAL
    assert "Renewal-Forecasting" not in ergebnis
    assert "fuehrender Anbieter" not in ergebnis
    assert "Karriereseite" not in ergebnis


def test_pruefen_repost_regression_rohtext_vorrang(monkeypatch, tmp_path):
    """Test 2 (Spec §4) -- Repost-Regression (Fall A, s. Moduldocstring Punkt 4): derselbe
    angereicherte Snapshot gegen das englische Original als Kandidat erreicht jetzt
    `pruefen(...) >= schwelle` -- vor P2-37 verglich der Abschnittsfilter die deutsche
    Zusammenfassung gegen den englischen Kandidaten (Score nahe null). Gegenprobe in derselben
    Funktion: die Zusammenfassung ALLEIN gegen denselben Kandidaten bleibt unter der Schwelle --
    so ist festgehalten, woran es vorher scheiterte."""
    from pipeline.dedup_text import pruefen, aehnlichkeit, rollen_relevanter_text_aus, konfiguration

    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    cfg = konfiguration()

    deutsche_zusammenfassung = (
        "Aufgaben\n"
        "Sie verantworten das Renewal-Forecasting fuer strategische Grosskunden.\n"
        "Sie eskalieren kritische Faelle und fuehren Business Reviews mit dem Kunden.\n"
        "Anforderungen\n"
        "Mehrjaehrige Erfahrung im Customer Success einer Softwarefirma.\n"
        "Sehr gute Kommunikationsfaehigkeiten auf Deutsch und Englisch noetig.\n"
    )
    snapshot = (
        "Firma\nBeispiel AG\n"
        + deutsche_zusammenfassung +
        "Benefits\n30 Tage Urlaub und ein Jobrad.\n"
        "Über das Unternehmen\nWir sind ein fuehrender Anbieter fuer CS-Software.\n"
        "Volltext (unbereinigt)\n"
        + _ENGLISCHES_ORIGINAL + "\n"
        "Erfassungs-Kontext\nErfasst am 20.07.2026 ueber die Karriereseite.\n"
    )

    titel = "Senior Customer Success Manager EMEA"
    text_neu = rollen_relevanter_text_aus(snapshot)
    score = pruefen(titel, text_neu, titel, _ENGLISCHES_ORIGINAL, cfg)

    assert score is not None
    assert score >= cfg["schwelle"], f"Rohtext-Vorrang sollte die Schwelle erreichen: {score}"

    # Gegenprobe: NUR die deutsche Zusammenfassung (das fruehere Ergebnis des Abschnittsfilters,
    # bevor Rohtext-Vorrang griff) gegen denselben Kandidaten.
    score_alt = aehnlichkeit(deutsche_zusammenfassung, _ENGLISCHES_ORIGINAL, cfg["shingle_woerter"])
    assert score_alt < cfg["schwelle"], (
        f"Zusammenfassung allein sollte unter der Schwelle bleiben (woran es vorher scheiterte): {score_alt}"
    )


def test_rollen_relevanter_text_aus_rueckfall_ohne_rohtext():
    """Test 3 (Spec §4): kein Rohtext-Abschnitt vorhanden (z. B. Fall B, s.
    Moduldocstring Punkt 1) -- Abschnittsfilter behaelt Aufgaben/Anforderungen, verwirft
    Benefits/„Über das Unternehmen“ (bisheriges Verhalten)."""
    from pipeline.dedup_text import rollen_relevanter_text_aus

    snapshot = (
        "Firma\nBeispiel KG\n"
        "Aufgaben\n"
        "Sie betreuen Bestandskunden im Bereich Facility Management.\n"
        "Anforderungen\n"
        "Abgeschlossene kaufmaennische Ausbildung.\n"
        "Benefits\n"
        "Betriebliche Altersvorsorge.\n"
        "Über das Unternehmen\n"
        "Wir sind ein familiengefuehrtes Unternehmen seit 1950.\n"
    )

    ergebnis = rollen_relevanter_text_aus(snapshot)

    assert "Bestandskunden im Bereich Facility Management" in ergebnis
    assert "kaufmaennische Ausbildung" in ergebnis
    assert "Altersvorsorge" not in ergebnis
    assert "familiengefuehrtes Unternehmen" not in ergebnis


def test_rollen_relevanter_text_aus_rueckfall_bei_kurzem_rohtext_markerfix():
    """Test 4 (Spec §4): Rohtext unter `_ROHTEXT_MIN_ZEICHEN` (400) -- Rueckfall auf den
    Abschnittsfilter. Der kurze „Volltext (…)“-Abschnitt wird dort jetzt MITGENOMMEN
    (Marker-Fix §3.3: `^volltext\\b` statt `^volltext$` -- vorher passte das Muster auf
    „Volltext (unbereinigt)“ nie)."""
    from pipeline.dedup_text import rollen_relevanter_text_aus

    kurzer_rohtext = "Kurzer englischer Originaltext, deutlich unter der 400-Zeichen-Schwelle."
    assert len(kurzer_rohtext) < 400

    snapshot = (
        "Firma\nBeispiel OHG\n"
        "Aufgaben\n"
        "Sie unterstuetzen das Team im Tagesgeschaeft.\n"
        "Volltext (unbereinigt)\n"
        + kurzer_rohtext + "\n"
        "Erfassungs-Kontext\n"
        "Erfasst am 20.07.2026.\n"
    )

    ergebnis = rollen_relevanter_text_aus(snapshot)

    assert "Tagesgeschaeft" in ergebnis
    assert kurzer_rohtext in ergebnis
    assert "Erfasst am 20.07.2026" not in ergebnis


def test_rollen_relevanter_text_aus_basis_snapshot_anzeigentext():
    """Test 5 (Spec §4): Basis-Snapshot (Phase-38-Renderer, EIN Block „Anzeigentext
    (automatisch extrahiert, unbereinigt)“) -- Rohtext-Vorrang liefert den Anzeigentext wie
    bisher."""
    from pipeline.dedup_text import rollen_relevanter_text_aus

    anzeigentext = (
        "We are hiring a Support Engineer to join our EMEA team, responsible for triaging "
        "customer-reported incidents, reproducing defects, and working with engineering to "
        "ship fixes. You will own the on-call rotation, maintain our internal knowledge base "
        "and continuously improve our diagnostic tooling to reduce time to resolution across "
        "our largest enterprise accounts and our newest strategic partners across the region."
    )
    assert len(anzeigentext) >= 400

    snapshot = (
        "Firma\nBeispiel Support GmbH\nOrt\nBerlin\nGehalt\n60.000 - 70.000 EUR\n"
        "Anzeigentext (automatisch extrahiert, unbereinigt)\n"
        + anzeigentext + "\n"
    )

    ergebnis = rollen_relevanter_text_aus(snapshot)

    assert ergebnis == anzeigentext


def test_rohtext_aus_endet_am_naechsten_marker():
    """Test 6 (Spec §4, Abnahme-Korrektur 11.09.): der Rohtext endet NUR an `_ROHTEXT_ENDE`
    („Erfassungs-Kontext“, „Quellen“ -- der tatsaechlichen Vorlagen-Grenze beider Renderer) --
    danach kommt nichts mehr mit. NICHT an anderen BEHALTEN-/VERWERFEN-Markern der
    Abschnitts-Filterung (das war der in der Abnahme korrigierte Fehler, s. eigener
    Regressionstest unten)."""
    from pipeline.dedup_text import rohtext_aus

    text_quellen = (
        "Volltext\n"
        "Dies ist der eigentliche Anzeigentext, den wir behalten wollen.\n"
        "Quellen\n"
        "https://beispiel.de/stelle/123\n"
    )
    assert rohtext_aus(text_quellen) == "Dies ist der eigentliche Anzeigentext, den wir behalten wollen."

    text_kontext = (
        "Anzeigentext (automatisch extrahiert, unbereinigt)\n"
        "Ein anderer Anzeigentext, ebenfalls zu behalten.\n"
        "Erfassungs-Kontext\n"
        "Erfasst am 01.01.2026, sollte nicht mitkommen.\n"
    )
    assert rohtext_aus(text_kontext) == "Ein anderer Anzeigentext, ebenfalls zu behalten."


def test_rohtext_aus_ueberschriften_im_anzeigentext_beenden_ihn_nicht():
    """Regressionstest (Abnahme-Korrektur 11.09., s. Moduldocstring Punkt 4 „Messfehler“):
    Zeilen, die zufaellig wie ein BEHALTEN-/VERWERFEN-Marker der Abschnitts-Filterung aussehen
    („Requirements“, „Key Responsibilities:“, „Qualifications“, „Aufgaben“, „Benefits“,
    „Über das Unternehmen“), aber MITTEN IM Anzeigentext selbst stehen, duerfen die
    Rohtext-Sammlung NICHT beenden -- nur `_ROHTEXT_ENDE` tut das. Die erste, in der Abnahme
    korrigierte Fassung brach hier faelschlich ab (127 von 381 gemessenen Rohtexten behielten
    dadurch weniger als die Haelfte; ein Beispiel (Fall C) fiel in echter Ingest-Richtung auf 14 %
    statt 100 %)."""
    from pipeline.dedup_text import rohtext_aus

    text = (
        "Volltext (unbereinigt)\n"
        "About the role\n"
        "We are looking for a consultant to join our team.\n"
        "Requirements\n"
        "Several years of experience in enterprise consulting.\n"
        "Key Responsibilities:\n"
        "Own the customer relationship end to end.\n"
        "Qualifications\n"
        "Fluent in German and English.\n"
        "Aufgaben\n"
        "Diese Zeile gehoert zufaellig auch zum englischen Original.\n"
        "Benefits\n"
        "Includes a company car and 30 days of holiday.\n"
        "Über das Unternehmen\n"
        "This is still part of the original posting text, not the company blurb.\n"
        "Erfassungs-Kontext\n"
        "Erfasst am 20.07.2026, gehoert NICHT zum Rohtext.\n"
    )

    ergebnis = rohtext_aus(text)

    assert "About the role" in ergebnis
    assert "Requirements" in ergebnis
    assert "Several years of experience" in ergebnis
    assert "Key Responsibilities:" in ergebnis
    assert "Own the customer relationship" in ergebnis
    assert "Qualifications" in ergebnis
    assert "Fluent in German" in ergebnis
    assert "Aufgaben" in ergebnis
    assert "Diese Zeile gehoert zufaellig" in ergebnis
    assert "Benefits" in ergebnis
    assert "company car" in ergebnis
    assert "Über das Unternehmen" in ergebnis
    assert "still part of the original posting text" in ergebnis
    assert "Erfassungs-Kontext" not in ergebnis
    assert "gehoert NICHT zum Rohtext" not in ergebnis


def test_rohtext_aus_laeuft_bis_textende_ohne_endmarker():
    """NEU (Abnahme-Korrektur 11.09.): fehlt `_ROHTEXT_ENDE` komplett (aeltere Snapshots ohne
    „Erfassungs-Kontext“/„Quellen“, 8 von 381 gemessen), laeuft die Rohtext-Sammlung bis zum
    Textende -- kein vorzeitiger Abbruch an irgendeiner anderen Zeile."""
    from pipeline.dedup_text import rohtext_aus

    text = (
        "Volltext (unbereinigt)\n"
        "Erste Zeile des Anzeigentextes.\n"
        "Zweite Zeile, die ganz normal weitergeht.\n"
        "Letzte Zeile ohne jeden Endmarker danach.\n"
    )

    ergebnis = rohtext_aus(text)

    assert ergebnis == (
        "Erste Zeile des Anzeigentextes.\n"
        "Zweite Zeile, die ganz normal weitergeht.\n"
        "Letzte Zeile ohne jeden Endmarker danach."
    )


def test_pruefen_ingest_richtung_ueberschrift_im_original_beeinflusst_score_nicht(monkeypatch, tmp_path):
    """NEU (Abnahme-Korrektur 11.09., Ingest-Richtung): angereicherter Snapshot, dessen
    englisches Original MITTEN DRIN eine Zeile „Requirements“ traegt, gegen denselben VOLLEN
    Original-Text als Kandidat (`kandidat_text()`, wie im echten Ingest-Hook
    `pipeline/ingest.py` Z. 288) -- der Score muss nahe 1,0 liegen (Bestand und Kandidat
    durchlaufen denselben `_rauschen_filtern`-Schritt auf denselben Zeilen). Mit der ersten,
    in der Abnahme korrigierten Fassung (Rohtext-Abbruch an jeder BEHALTEN-/
    VERWERFEN-Ueberschrift) lag der Score deutlich darunter -- Gegenprobe per Wegwerf-Skript
    im Scratchpad, s. Bericht."""
    from pipeline.dedup_text import pruefen, kandidat_text, rollen_relevanter_text_aus, konfiguration

    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    cfg = konfiguration()

    original_mit_ueberschrift = (
        "We are looking for an experienced Senior Solution Consultant to join our DACH team, "
        "designing and implementing complex technical solutions for enterprise customers.\n"
        "Requirements\n"
        "Several years of experience in enterprise software consulting, fluent German and "
        "English, and a track record of translating customer requirements into workable "
        "technical designs across cloud and on-premise deployments for strategic accounts."
    )
    assert len(original_mit_ueberschrift) >= 400

    snapshot = (
        "Firma\nBeispiel AG\n"
        "Aufgaben\nSie beraten Kunden zu komplexen Loesungen.\n"
        "Anforderungen\nMehrjaehrige Erfahrung in der Unternehmensberatung.\n"
        "Benefits\nFlexible Arbeitszeiten.\n"
        "Über das Unternehmen\nWir sind ein globaler Softwareanbieter.\n"
        "Volltext (unbereinigt)\n"
        + original_mit_ueberschrift + "\n"
        "Erfassungs-Kontext\nErfasst am 20.07.2026.\n"
    )

    titel = "Senior Solution Consultant DACH"
    text_bestand = rollen_relevanter_text_aus(snapshot)
    text_kandidat = kandidat_text(original_mit_ueberschrift)

    score = pruefen(titel, text_bestand, titel, text_kandidat, cfg)

    assert score is not None
    assert score >= 0.9, f"Score sollte nahe 1,0 liegen: {score}"


def test_rohtext_aus_entfernt_portal_chrome():
    """Test 7 (Spec §4): Portal-Chrome-Zeile im Rohtext-Abschnitt wird von `_rauschen_filtern`
    entfernt (Teilstring-Erkennung, s. `_PORTAL_CHROME_TEILSTRING`)."""
    from pipeline.dedup_text import rohtext_aus

    text = (
        "Volltext (unbereinigt)\n"
        "Passwort vergessen? Jetzt zuruecksetzen.\n"
        "Dies ist der eigentliche, rollenrelevante Anzeigentext.\n"
    )

    ergebnis = rohtext_aus(text)

    assert "Passwort" not in ergebnis
    assert ergebnis == "Dies ist der eigentliche, rollenrelevante Anzeigentext."


def test_rollen_relevanter_text_huelle_delegiert_an_reine_funktion(monkeypatch):
    """Test 8 (Spec §4): `rollen_relevanter_text(pfad)` ist nur noch eine duenne Huelle um
    `rollen_relevanter_text_aus()` (P2-37 §3.1) -- per Monkeypatch von `text_aus_snapshot`
    geprueft, ohne echten Datei-/DB-Zugriff."""
    import pipeline.dedup_text as dedup_text

    synthetischer_text = (
        "Aufgaben\nSie tun Dinge.\n"
        "Volltext (unbereinigt)\n"
        + ("Ein hinreichend langer englischer Beispieltext fuer den Huellen-Test. " * 8) + "\n"
        "Erfassungs-Kontext\nEnde.\n"
    )

    monkeypatch.setattr(dedup_text, "text_aus_snapshot", lambda pfad: synthetischer_text)

    erwartet = dedup_text.rollen_relevanter_text_aus(synthetischer_text)
    ergebnis = dedup_text.rollen_relevanter_text("irrelevanter/pfad.html")

    assert ergebnis == erwartet
    assert ergebnis != ""
