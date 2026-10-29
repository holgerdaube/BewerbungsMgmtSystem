"""Ingest: Stellenzuordnung über den Mailtext, wenn der Betreff nichts hergibt (P2-28).

Fall A (08.09.2026): Eine Absage-Mail ließ sich keiner Stelle zuordnen, obwohl der Mensch
das in drei Sekunden sieht.

DIE KETTE, gemessen statt vermutet:
  * Der Betreff ist generisch: „Beispiel GmbH | Deine Bewerbung" — kein Titel.
  * Der Stellentitel steht im FLIESSTEXT: „vielen Dank für deine Bewerbung auf die Position
    (Senior) Manager Muster-Einkauf & Lieferkette (m/w/d) …" (Volltext: 3525 Zeichen).
  * Der Lauf sieht den Volltext nie. Schritt 1 des Skills liefert nur `subject` und `snippet`,
    und das Gmail-Snippet ist mit 120 Zeichen nicht nur kurz, sondern kürzt ausgerechnet die
    Titel-Stelle weg: „Hallo Max, vielen Dank für deine Bewerbung ... Leider können wir dich
    für den weiteren Prozess nicht berücksichtigen."
  * Folge: `job_title` blieb `null`, `_match_job` bekam nichts zu vergleichen und gab `None`
    zurück — die Absage landete als „⚠ Ohne Stelle" in der Inbox.

Die Zuordnungslogik war also NICHT defekt: Mit dem Titel gefüttert findet sie die Stelle auf
Anhieb (exakter ct_key-Treffer auf Stelle A). Es fehlte die Quelle, nicht die Logik.

RICHTUNG DER SUCHE ist der Kern des Fixes: Es werden die BEKANNTEN Stellentitel der Firma IM
Text gesucht, statt einen Titel aus dem Text zu raten. Das braucht kein Modell, ist
deterministisch und kann nichts erfinden — und löst Fall A nebenbei sauber, obwohl
dort zwei fast gleichnamige Stellen in der DB stehen: Nur „…(m/w/d)" steht wörtlich im Text,
„…(m/w/d) in Musterstadt" nicht.

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention).
"""
import datetime

import pytest

# Ein Beispiel-Mailtext, gekürzt auf die entscheidenden Sätze.
MAILTEXT = """Hallo Max,

vielen Dank für deine Bewerbung auf die Position (Senior) Manager Muster-Einkauf & Lieferkette
(m/w/d) und die Zeit, die du in deine Unterlagen investiert hast.

Leider können wir dich für den weiteren Prozess nicht berücksichtigen.

Viele Grüße
dein Recruiting-Team der Beispiel GmbH
"""

# Was der Lauf tatsächlich zu sehen bekommt — der Titel fehlt darin.
SNIPPET = ("Hallo Max, vielen Dank für deine Bewerbung ... Leider können wir dich für den "
           "weiteren Prozess nicht berücksichtigen.")


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """Frische Datenbank je Test — die Suite teilt sich sonst eine, in der Fremdzeilen mitzählen."""
    from sqlmodel import Session, SQLModel, create_engine

    import app.models  # noqa: F401  — registriert die Tabellen
    from pipeline import gmail_ingest

    eng = create_engine("sqlite:///" + str(tmp_path / "ingest.sqlite"))
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(gmail_ingest, "engine", eng, raising=False)
    with Session(eng) as s:
        yield s


def _firma_mit_stellen(db, firma_name, titel_liste):
    from app.models import Company, Job

    c = Company(name=firma_name)
    db.add(c)
    db.commit()
    db.refresh(c)
    for t in titel_liste:
        db.add(Job(company_id=c.id, company_name=firma_name, title=t, portal="LinkedIn",
                   status="Beworben", found_date=str(datetime.date.today()),
                   dedup_key=f"{firma_name}|{t}".lower()))
    db.commit()
    return c


@pytest.fixture()
def volltext(monkeypatch):
    """`_volltext` fest verdrahten — kein Netz, kein Gmail-Zugang im Test."""
    from pipeline import gmail_ingest

    def _setzen(text):
        monkeypatch.setattr(gmail_ingest, "_volltext", lambda _mid: text)
    return _setzen


def test_titel_nur_im_fliesstext_wird_gefunden(db, volltext):
    """DER Kernfall: Betreff generisch, Snippet ohne Titel, Titel nur im Volltext."""
    from pipeline.gmail_ingest import _match_job_im_volltext

    comp = _firma_mit_stellen(db, "Beispiel GmbH", ["(Senior) Manager Muster-Einkauf & Lieferkette (m/w/d)"])
    volltext(MAILTEXT)

    treffer = _match_job_im_volltext(db, comp, "msg-1")

    assert treffer is not None
    assert treffer.title.startswith("(Senior) Manager Muster-Einkauf")


def test_der_titel_fehlt_im_snippet(db, volltext):
    """Die Prämisse des ganzen Fixes, festgehalten: Mit dem Snippet allein ist nichts zu holen.

    Fällt dieser Test, hat sich die Annahme geändert (Gmail kürzt anders, oder der Ingest
    speichert plötzlich mehr) — dann gehört der Umweg über den Volltext überprüft."""
    from pipeline.gmail_ingest import _match_job_im_volltext

    comp = _firma_mit_stellen(db, "Beispiel GmbH", ["(Senior) Manager Muster-Einkauf & Lieferkette (m/w/d)"])
    volltext(SNIPPET)

    assert _match_job_im_volltext(db, comp, "msg-1") is None


def test_aehnliche_stelle_ohne_wortlaut_im_text_trifft_nicht(db, volltext):
    """Ein Bestand mit zwei fast gleichnamigen Stellen, nur eine steht so im Text.

    Job „…(m/w/d)" kommt wörtlich vor, „…(m/w/d) in Musterstadt" nicht — die Suche nach bekannten
    Titeln IM Text löst die Mehrdeutigkeit damit von selbst, ohne Ähnlichkeitsschwelle."""
    from pipeline.gmail_ingest import _match_job_im_volltext

    comp = _firma_mit_stellen(db, "Beispiel GmbH", [
        "(Senior) Manager Muster-Einkauf & Lieferkette (m/w/d)",
        "(Senior) Manager Muster-Einkauf & Lieferkette (m/w/d) in Musterstadt",
    ])
    volltext(MAILTEXT)

    treffer = _match_job_im_volltext(db, comp, "msg-1")

    assert treffer is not None
    assert treffer.title.endswith("(m/w/d)"), "die Musterstadt-Variante steht so nicht im Text"


def test_zwei_echte_treffer_bleiben_mehrdeutig(db, volltext):
    """Nennt eine Mail zwei Stellen derselben Firma, wird nichts zugeordnet — dieselbe Haltung
    wie in `_match_job`: lieber keine Zuordnung als eine falsche."""
    from pipeline.gmail_ingest import _MEHRDEUTIG, _match_job_im_volltext

    comp = _firma_mit_stellen(db, "Beispiel GmbH", [
        "(Senior) Manager Muster-Einkauf & Lieferkette (m/w/d)",
        "Senior Manager Prozessberatung (m/w/d)",
    ])
    volltext(MAILTEXT + "\nDeine Bewerbung als Senior Manager Prozessberatung (m/w/d) läuft weiter.")

    assert _match_job_im_volltext(db, comp, "msg-1") is _MEHRDEUTIG


def test_abweichende_schreibweise_stoert_nicht(db, volltext):
    """Zeilenumbruch mitten im Titel, andere Bindestriche, doppelte Leerzeichen: Der Vergleich
    läuft über `_flach` (nur Buchstaben und Ziffern), sonst wäre er in der Praxis wertlos —
    im Originaltext ist der Titel über zwei Zeilen umbrochen."""
    from pipeline.gmail_ingest import _match_job_im_volltext

    comp = _firma_mit_stellen(db, "Beispiel GmbH", ["(Senior) Manager Muster-Einkauf & Lieferkette (m/w/d)"])
    volltext("… deine Bewerbung auf die Position (Senior)  Manager Muster‑Einkauf &\nLieferkette "
             "(m/w/d) und die Zeit …")

    assert _match_job_im_volltext(db, comp, "msg-1") is not None


def test_kurze_titel_werden_nicht_im_text_gesucht(db, volltext):
    """Ein Titel wie „Consultant" käme in einer langen Mail zufällig vor und würde eine falsche
    Stelle treffen. Unter `_VOLLTEXT_MIN_TITEL` Zeichen wird deshalb gar nicht erst gesucht."""
    from pipeline.gmail_ingest import _match_job_im_volltext

    comp = _firma_mit_stellen(db, "Beispiel AG", ["Consultant"])
    volltext("Wir suchen laufend Verstärkung, etwa als Consultant im Bereich Delivery.")

    assert _match_job_im_volltext(db, comp, "msg-1") is None


def test_ohne_volltext_bleibt_es_bei_keiner_zuordnung(db, volltext):
    """Kein Netz, kein Gmail-Zugang, gelöschte Mail: Der Ingest läuft weiter, ordnet eben nicht zu."""
    from pipeline.gmail_ingest import _match_job_im_volltext

    comp = _firma_mit_stellen(db, "Beispiel GmbH", ["(Senior) Manager Muster-Einkauf & Lieferkette (m/w/d)"])
    volltext(None)

    assert _match_job_im_volltext(db, comp, "msg-1") is None


def test_volltext_helfer_verschluckt_fehler(monkeypatch):
    """`_volltext` darf nie werfen — ein Zuordnungs-Komfort bringt den Ingest nicht zum Absturz.

    In der CI gibt es weder Netz noch Zugangsdaten; ohne dieses Auffangnetz wäre jeder
    Ingest-Lauf dort ein Fehlschlag."""
    from pipeline import gmail_client, gmail_ingest

    def _kracht(_mid):
        raise RuntimeError("kein Netz")

    monkeypatch.setattr(gmail_client, "cmd_get", _kracht)

    assert gmail_ingest._volltext("msg-1") is None
    assert gmail_ingest._volltext(None) is None


def test_ohne_stellen_der_firma_kein_netzwerkaufruf(db, monkeypatch):
    """Hat die Firma gar keine Stelle, wird der Volltext erst gar nicht geholt — der Aufruf
    kostet Zeit und Gmail-Kontingent."""
    from app.models import Company
    from pipeline import gmail_ingest

    c = Company(name="Ohne Stellen GmbH")
    db.add(c)
    db.commit()
    db.refresh(c)
    gerufen = []
    monkeypatch.setattr(gmail_ingest, "_volltext", lambda mid: gerufen.append(mid))

    assert gmail_ingest._match_job_im_volltext(db, c, "msg-1") is None
    assert gerufen == [], "ohne Kandidaten darf der Volltext nicht geladen werden"
