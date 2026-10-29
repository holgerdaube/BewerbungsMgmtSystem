"""Query-Übersetzung Gmail → IMAP (Phase 71F, `pipeline.imap_mail.translate_query`).

Reine Funktion, kein IMAP-/Netzzugriff, kein `app.*`-Import nötig — trotzdem nur innerhalb der
Testfunktionen importiert (Projekt-Konvention aus conftest.py). Deckt die Spec-Vorgabe
"mind. 6 Fälle inkl. Kombination" deutlich ab und misst zusätzlich gegen die ECHTE Query aus
`.claude/skills/email-check/SKILL.md`, damit die Vereinfachung ("Positivkriterien ODER-
verknüpft statt der ursprünglichen Klammerstruktur") nicht nur in der Theorie stimmt, sondern
für den tatsächlich genutzten Fall.
"""
import datetime


def test_after_datum():
    from pipeline.imap_mail import translate_query

    p = translate_query("after:2026/01/15")
    assert p["since"] == datetime.date(2026, 1, 15)
    assert p["before"] is None


def test_before_datum_mit_bindestrich_getrennt():
    from pipeline.imap_mail import translate_query

    p = translate_query("before:2026-02-01")
    assert p["before"] == datetime.date(2026, 2, 1)


def test_newer_than_tage():
    from pipeline.imap_mail import translate_query

    p = translate_query("newer_than:2d")
    assert p["since"] == datetime.date.today() - datetime.timedelta(days=2)


def test_newer_than_monate_und_jahre():
    from pipeline.imap_mail import translate_query

    heute = datetime.date.today()
    assert translate_query("newer_than:1m")["since"] == heute - datetime.timedelta(days=30)
    assert translate_query("newer_than:1y")["since"] == heute - datetime.timedelta(days=365)


def test_from_einzelwert():
    from pipeline.imap_mail import translate_query

    p = translate_query("from:karriere@beispiel.de")
    assert p["positive"] == [("from", "karriere@beispiel.de")]
    assert p["negative"] == []


def test_subject_einzelwert():
    from pipeline.imap_mail import translate_query

    p = translate_query("subject:Bewerbung")
    assert p["positive"] == [("subject", "Bewerbung")]


def test_freitext_wird_text_kriterium():
    from pipeline.imap_mail import translate_query

    p = translate_query("Vorstellungsgespräch")
    assert p["positive"] == [("text", "Vorstellungsgespräch")]


def test_from_or_gruppe_wird_zu_mehreren_positiv_leaves():
    from pipeline.imap_mail import translate_query

    p = translate_query("from:(a@b.de OR c@d.de OR e@beispiel.de)")
    assert p["positive"] == [("from", "a@b.de"), ("from", "c@d.de"), ("from", "e@beispiel.de")]


def test_negierte_subject_or_gruppe_mit_quoted_phrases():
    from pipeline.imap_mail import translate_query

    p = translate_query('-subject:("new jobs similar" OR "apply now to")')
    assert p["negative"] == [("subject", "new jobs similar"), ("subject", "apply now to")]
    assert p["positive"] == []


def test_gmail_only_operatoren_werden_ignoriert_und_vermerkt():
    from pipeline.imap_mail import translate_query

    p = translate_query("-in:chats -category:promotions newer_than:2d")
    assert p["since"] == datetime.date.today() - datetime.timedelta(days=2)
    assert p["positive"] == []
    assert p["negative"] == []
    notes = " ".join(p["notes"])
    assert "in:chats" in notes
    assert "category:promotions" in notes


def test_unbekanntes_praefix_wird_ignoriert_statt_zu_crashen():
    from pipeline.imap_mail import translate_query

    p = translate_query("larger:5M newer_than:2d")
    assert p["since"] is not None
    assert any("larger:5M" in n for n in p["notes"])


def test_kombination_datum_or_gruppe_negation_und_freitext():
    """Der Spec-geforderte Kombinationsfall: Datum + positive OR-Gruppe + negierte OR-Gruppe +
    ignorierter Gmail-Operator in EINER Query."""
    from pipeline.imap_mail import translate_query

    q = ('newer_than:3d -in:chats from:(a@b.de OR c@d.de) -subject:(Werbung OR Spam) '
         "Zwischenstand")
    p = translate_query(q)
    assert p["since"] == datetime.date.today() - datetime.timedelta(days=3)
    assert ("from", "a@b.de") in p["positive"]
    assert ("from", "c@d.de") in p["positive"]
    assert ("text", "Zwischenstand") in p["positive"]
    assert ("subject", "Werbung") in p["negative"]
    assert ("subject", "Spam") in p["negative"]
    assert any("in:chats" in n for n in p["notes"])


def test_standalone_klammer_gruppe_ueber_zwei_felder_wird_flach_zu_or():
    """Die reale email-check-Query klammert `(subject:(...) OR from:(...))` — beide Felder
    landen im selben flachen Positiv-Topf (bewusste Vereinfachung, s. Moduldocstring)."""
    from pipeline.imap_mail import translate_query

    q = "(subject:(Bewerbung OR interview) OR from:(recruiting OR karriere))"
    p = translate_query(q)
    assert set(p["positive"]) == {
        ("subject", "Bewerbung"), ("subject", "interview"),
        ("from", "recruiting"), ("from", "karriere"),
    }


def test_echte_email_check_query_wird_ohne_absturz_und_korrekt_uebersetzt():
    """Wortgetreuer Ausschnitt aus `.claude/skills/email-check/SKILL.md` Schritt 1 (gekürzt um
    ein paar OR-Glieder, Struktur/Operatoren identisch) — der reale Fall, den die Vereinfachung
    treffen muss."""
    from pipeline.imap_mail import translate_query

    q = (
        'newer_than:2d -in:chats -category:promotions -category:social '
        '-from:(jobalerts-noreply@linkedin.com OR jobs-listings@linkedin.com) '
        '-from:(github.com OR email.apple.com) '
        '-subject:("new jobs similar" OR "apply now to") '
        '-subject:(Sendung OR Rechnung) '
        '(subject:(Bewerbung OR interview OR Absage OR "your application") '
        'OR from:(recruiting OR karriere OR no-reply OR myworkday.com))'
    )
    p = translate_query(q)

    assert p["since"] == datetime.date.today() - datetime.timedelta(days=2)
    assert p["before"] is None

    positiv = set(p["positive"])
    assert positiv == {
        ("subject", "Bewerbung"), ("subject", "interview"), ("subject", "Absage"),
        ("subject", "your application"),
        ("from", "recruiting"), ("from", "karriere"), ("from", "no-reply"),
        ("from", "myworkday.com"),
    }
    negativ = set(p["negative"])
    assert negativ == {
        ("from", "jobalerts-noreply@linkedin.com"), ("from", "jobs-listings@linkedin.com"),
        ("from", "github.com"), ("from", "email.apple.com"),
        ("subject", "new jobs similar"), ("subject", "apply now to"),
        ("subject", "Sendung"), ("subject", "Rechnung"),
    }
    notes = " ".join(p["notes"])
    assert "in:chats" in notes
    assert "category:promotions" in notes
    assert "category:social" in notes


def test_leere_query_liefert_leeren_kontext_ohne_fehler():
    from pipeline.imap_mail import translate_query

    p = translate_query("")
    assert p == {"since": None, "before": None, "positive": [], "negative": [], "notes": []}
