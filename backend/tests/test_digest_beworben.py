"""Tages-Digest: Abschnitt „Beworben bei" (Wunsch vom 03.09.2026).

Wörtlich: „Kannst du bitte zwischen 'Absagen' und 'Offene Aktionen' noch einen Bereich
'Beworben bei' einfügen? Hier sollen die Bewerbungen der letzten 72h aufgeführt werden. Den
Status bekommst du ja aus der Datenbank."

NACHTRAG 04.09.2026: „macht die Beworben Spanne bitte auch auf 96h“ — dasselbe Fenster wie
bei den Absagen, damit sich beide Abschnitte gegeneinander lesen lassen. Die Zahlen unten sind
nachgezogen; der Messwert im naechsten Absatz bleibt dagegen stehen, wie er erhoben wurde
(72-Stunden-Fenster, 03.09.2026) — ein Befund wird nicht umgeschrieben, wenn sich die
Einstellung aendert.

Quelle ist bewusst das JobLog und NICHT `Application` — am echten Bestand gemessen (Spec §0)
deckt `Application.created_at` in 72 h nur 4 von 9 tatsächlichen Bewerbungen ab,
`Application.applied_date` ist in allen neun Fällen `None`. Der `→ Beworben`-Statuswechsel im
JobLog ist die einzige Quelle, die vollständig ist.

EIGENE DATENBANK JE TEST (`digest_db`): Wie in `test_digest_absagen.py` — die Suite teilt sich
über `conftest._db_ready` sonst eine tmp-Datenbank, die zwischen Tests nicht geleert wird.
Zusicherungen wie „Letzte 7 Tage: 0" oder „diese Firma steht NICHT drin" wären damit untauglich.

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention).
"""
import datetime

import pytest


@pytest.fixture()
def digest_db(tmp_path, monkeypatch):
    """Frische, leere Datenbank nur für diesen Test — siehe Modul-Docstring."""
    from sqlmodel import Session, SQLModel, create_engine

    import app.models  # noqa: F401  — Import registriert die Tabellen in SQLModel.metadata
    from pipeline import digest as digest_modul

    eng = create_engine("sqlite:///" + str(tmp_path / "digest.sqlite"))
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(digest_modul, "engine", eng)
    with Session(eng) as s:
        yield s


def _abschnitt(html: str, stunden: int = 96) -> str:
    """Nur den Beworben-Abschnitt aus dem Digest schneiden.

    Wie bei den Absagen (siehe dortiges Vorbild): Ein Job, der heute auf Beworben gesetzt
    wurde, hat auch heute ein `updated_at` und steht deshalb ohnehin nochmal in „Heute
    geändert". Ohne diesen Schnitt prüfte eine Nicht-enthalten-Zusicherung das Falsche.
    """
    start = html.index("Beworben bei — letzte " + str(stunden) + " Stunden")
    return html[start:html.index("</section>", start)]


def _log(db, job, eintrag, *, art="auto", stunden_zurueck=1.0):
    """Eine JobLog-Zeile mit naivem UTC `created_at`, wie in der Produktion."""
    from app.models import JobLog

    log = JobLog(job_id=job.id, eintrag=eintrag, art=art,
                 created_at=datetime.datetime.utcnow() - datetime.timedelta(hours=stunden_zurueck))
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def _stelle(db, firma_name, titel, *, status="Beworben", match_score=None):
    """Firma + Stelle anlegen (die Stelle liefert im Digest Firmenname und Titel)."""
    from app.models import Company, Job

    firma = Company(name=firma_name)
    db.add(firma)
    db.commit()
    db.refresh(firma)
    job = Job(company_id=firma.id, company_name=firma_name, title=titel, portal="LinkedIn",
              status=status, found_date=str(datetime.date.today()), match_score=match_score,
              dedup_key=firma_name.lower() + "|" + titel.lower())
    db.add(job)
    db.commit()
    db.refresh(job)
    return firma, job


def test_bewerbung_von_heute_erscheint_mit_firma_stelle_und_zeit(digest_db):
    """Kernfall: Eine heutige Bewerbung steht mit Firma, Titel und Uhrzeit im Abschnitt."""
    from pipeline.digest import BEWORBEN_MARKE, build_digest_html

    _, job = _stelle(digest_db, "Beispiel Group", "(Senior) Consulting Manager")
    vor_zwei_stunden = datetime.datetime.utcnow() - datetime.timedelta(hours=2)
    _log(digest_db, job, "Status: Prüfen " + BEWORBEN_MARKE, stunden_zurueck=2.0)

    html = build_digest_html()

    assert "Beworben bei — letzte 96 Stunden (1)" in html
    abschnitt = _abschnitt(html)
    assert "Beispiel Group" in abschnitt
    assert "(Senior) Consulting Manager" in abschnitt
    erwartete_uhrzeit = (vor_zwei_stunden.replace(tzinfo=datetime.timezone.utc)
                         .astimezone().strftime("%H:%M"))
    assert erwartete_uhrzeit + " Uhr" in abschnitt


def test_fenstergrenze_95_stunden_drin_97_stunden_draussen(digest_db):
    """Die Grenze selbst — mit Abstand nach beiden Seiten, damit der Test nicht an der
    Laufzeit der Suite hängt."""
    from pipeline.digest import BEWORBEN_MARKE, build_digest_html

    _, drin = _stelle(digest_db, "Knapp Drin AG", "Rolle drin")
    _, draussen = _stelle(digest_db, "Knapp Draussen AG", "Rolle draussen")
    _log(digest_db, drin, "Status: Prüfen " + BEWORBEN_MARKE, stunden_zurueck=95)
    _log(digest_db, draussen, "Status: Prüfen " + BEWORBEN_MARKE, stunden_zurueck=97)

    abschnitt = _abschnitt(build_digest_html())

    assert "Rolle drin" in abschnitt
    assert "Rolle draussen" not in abschnitt, "97 Stunden liegen ausserhalb des Fensters"


def test_mehrfache_beworben_eintraege_erscheinen_einmal(digest_db):
    """Ein Job kann den Status mehrfach durchlaufen (zurückgesetzt und neu gesetzt). Ohne
    Dedup je job_id stünde dieselbe Bewerbung zweimal im Bericht."""
    from pipeline.digest import BEWORBEN_MARKE, build_digest_html

    _, job = _stelle(digest_db, "Zweimal AG", "Rolle")
    _log(digest_db, job, "Status: Prüfen " + BEWORBEN_MARKE, stunden_zurueck=50.0)
    juengere_zeit = datetime.datetime.utcnow() - datetime.timedelta(hours=3)
    _log(digest_db, job, "Status: Prüfen " + BEWORBEN_MARKE, stunden_zurueck=3.0)

    html = build_digest_html()

    assert "Beworben bei — letzte 96 Stunden (1)" in html
    abschnitt = _abschnitt(html)
    erwartete_uhrzeit = (juengere_zeit.replace(tzinfo=datetime.timezone.utc)
                         .astimezone().strftime("%H:%M"))
    assert erwartete_uhrzeit + " Uhr" in abschnitt


def test_eintrag_von_vorgestern_traegt_den_wochentag(digest_db):
    """Im 96-h-Fenster liegen Eintraege mehrerer Tage — 48 Stunden zurück ist eindeutig
    nicht mehr heute, die blosse Uhrzeit waere mehrdeutig."""
    from pipeline.digest import BEWORBEN_MARKE, build_digest_html

    _, job = _stelle(digest_db, "Vorgestern AG", "Rolle von vorgestern")
    wann_utc = datetime.datetime.utcnow() - datetime.timedelta(hours=48)
    _log(digest_db, job, "Status: Prüfen " + BEWORBEN_MARKE, stunden_zurueck=48.0)

    abschnitt = _abschnitt(build_digest_html())
    lokal = wann_utc.replace(tzinfo=datetime.timezone.utc).astimezone()
    kuerzel = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][lokal.weekday()]

    assert kuerzel + ", " + lokal.strftime("%H:%M") + " Uhr" in abschnitt


def test_application_ohne_joblog_taucht_nicht_faelschlich_auf(digest_db):
    """Belegt die Quellenwahl: eine `Application`-Zeile allein — ohne JobLog-Statuswechsel —
    erzeugt keinen Eintrag im Beworben-Abschnitt."""
    from app.models import Application
    from pipeline.digest import build_digest_html

    _, job = _stelle(digest_db, "Nur Application AG", "Rolle ohne Log")
    app_row = Application(job_id=job.id, applied_date=None,
                           created_at=datetime.datetime.utcnow() - datetime.timedelta(hours=2))
    digest_db.add(app_row)
    digest_db.commit()

    html = build_digest_html()

    assert "Beworben bei — letzte 96 Stunden (0)" in html
    assert "Nur Application AG" not in _abschnitt(html)


def test_beworben_marke_deckt_sich_mit_gmail_ingest(digest_db):
    """Haelt die bewusste Doppelung des Markers zwischen `digest.py` und `gmail_ingest.py`
    zusammen — nicht durch Hoffnung, sondern durch diesen Test."""
    from pipeline import digest, gmail_ingest

    assert digest.BEWORBEN_MARKE == gmail_ingest.BEWORBEN_MARKE


def test_ohne_bewerbungen_bleibt_der_abschnitt_leer_aber_vorhanden(digest_db):
    """Ein leerer Abschnitt ist eine Aussage („in 96h nichts"), kein Fehler."""
    from pipeline.digest import build_digest_html

    html = build_digest_html()

    assert "Beworben bei — letzte 96 Stunden (0)" in html
    assert "In den letzten 96 Stunden keine Bewerbungen." in html
    assert "Letzte 7 Tage: 0" in _abschnitt(html)


def test_abschnitt_steht_zwischen_absagen_und_offenen_aktionen(digest_db):
    """Wörtliche Vorgabe: „zwischen 'Absagen' und 'Offene Aktionen'"."""
    from pipeline.digest import build_digest_html

    html = build_digest_html()

    pos_absagen = html.index("Absagen der letzten")
    pos_beworben = html.index("Beworben bei — letzte")
    pos_offene = html.index("Offene Aktionen")

    assert pos_absagen < pos_beworben < pos_offene


def test_mehr_als_15_bewerbungen_werden_gedeckelt_mit_hinweis(digest_db):
    """Das bestehende `job_rows` schneidet stumm bei 15 ab — am 01.09. verschwanden so 56 von
    71 Zeilen spurlos (Spec §1.4). Der neue Abschnitt macht das nicht nach: Deckel bei 15 plus
    sichtbarer Hinweis auf die weiteren."""
    from pipeline.digest import BEWORBEN_MARKE, build_digest_html

    for i in range(17):
        _, job = _stelle(digest_db, f"Firma {i:02d}", f"Rolle {i:02d}")
        _log(digest_db, job, "Status: Prüfen " + BEWORBEN_MARKE, stunden_zurueck=1.0 + i * 0.1)

    abschnitt = _abschnitt(build_digest_html())
    zeilen_count = abschnitt.count("Rolle ")

    assert zeilen_count == 15
    assert "und 2 weitere" in abschnitt


def test_wochenwert_zaehlt_bewerbungen_nicht_logzeilen(digest_db):
    """Der Wochenwert unter dem Abschnitt muss dieselbe Zaehlweise haben wie der Abschnitt selbst.

    Fall A (03.09.2026): Eine Stelle hat zwei `→ Beworben`-Eintraege innerhalb einer Woche — der
    Status wurde zurueckgesetzt und neu gesetzt. Ungededupliziert stuende unter „Beworben bei (1)"
    die Zeile „Letzte 7 Tage: 2" fuer ein und dieselbe Bewerbung; die Zahl liesse sich mit der
    Ueberschrift darueber nicht vergleichen.

    Bei den Absagen ist die Zaehlung bewusst anders: Dort ist jede Zeile eine eigene MAIL.
    """
    from pipeline.digest import build_digest_html

    _, job = _stelle(digest_db, "Doppelt AG", "Rolle mit zwei Eintraegen")
    _log(digest_db, job, "Status: Pruefen → Beworben", stunden_zurueck=100)
    _log(digest_db, job, "Status: Pruefen → Beworben", stunden_zurueck=2)

    html = build_digest_html()

    assert "Beworben bei — letzte 96 Stunden (1)" in html
    assert "Letzte 7 Tage: 1" in html, "zwei Log-Zeilen, aber nur EINE Bewerbung"

