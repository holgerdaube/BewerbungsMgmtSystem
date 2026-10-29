"""Tages-Digest: Abschnitt „Absagen der letzten 96 Stunden" (Wunsch vom 28.08.2026).

FENSTERBREITE, zweimal geaendert: erst „heute“ (Kalendertag), dann 24 Stunden, seit dem
31.08.2026 96 Stunden („die aktuellen 24h sind gerade bei einem Wochenende zu kurz“).
Die Tests pruefen die Beschriftung deshalb NICHT gegen `digest.ABSAGEN_FENSTER_STUNDEN`,
sondern gegen die ausgeschriebene Zahl — sonst pruefte sich der Code gegen sich selbst und
eine versehentlich geaenderte Konstante fiele nirgends auf. Nur
`test_ueberschrift_leertext_und_fenster_haengen_an_derselben_konstante` fasst sie an, und
zwar genau um zu belegen, dass Text und Rechnung nicht auseinanderlaufen koennen.

Der Digest hatte bis dahin ÜBERHAUPT keine Tests — diese Datei ist die erste. Sie deckt den
neuen Abschnitt ab und nebenbei die Grundannahme, dass `build_digest_html()` gegen die
Test-DB läuft (conftest.py biegt `BMS_DATA_DIR` um, `app.db.engine` zeigt also auf die
tmp-Datenbank, nicht auf die echte).

Quelle des Abschnitts ist bewusst die KATEGORIE der Mail und nicht der Job-Status: Der Status
kann auch von Hand gesetzt worden sein, hier geht es um das, was der Postfach-Lauf tatsächlich
hereingeholt hat.

EIGENE DATENBANK JE TEST (`digest_db`): Die Suite teilt sich über `conftest._db_ready`
(scope="session") EINE tmp-Datenbank, die zwischen Tests nicht geleert wird. Für Zusicherungen
wie „Absagen heute (0)" oder „diese Firma steht NICHT drin" ist das untauglich — Zeilen aus
früheren Tests würden mitzählen. `pipeline.digest` liest `engine` als Modul-Global, deshalb
genügt ein `monkeypatch` darauf; die übrige Suite bleibt unberührt und dieser Test hinterlässt
umgekehrt auch nichts in der geteilten DB.

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
    """Nur den Absagen-Abschnitt aus dem Digest schneiden.

    Noetig fuer JEDE Nicht-enthalten-Zusicherung: Eine Test-Stelle taucht auch in „Heute
    geaendert" auf (ihr `updated_at` ist heute), ihr Firmenname steht also ohnehin irgendwo im
    Dokument. Ohne diesen Schnitt wuerde der Test das Falsche pruefen — genau so ist er beim
    ersten Lauf durchgefallen.

    `stunden` nur fuer den Waechter-Test, der die Fensterkonstante verstellt: Dann traegt die
    Ueberschrift eine andere Zahl und der Schnitt faende sie sonst nicht.
    """
    start = html.index("Absagen der letzten " + str(stunden) + " Stunden")
    return html[start:html.index("</section>", start)]


def _mail(db, *, stunden_zurueck=2.0, kategorie="Absage", richtung="incoming",
          job=None, company_id=None, antwortzeit=None, mid=None, wann=None):
    """Eine eingegangene Mail in der Test-DB anlegen und zurückgeben.

    `stunden_zurueck` zählt ab **utcnow** — genau wie das Fenster im Digest. `received_at` ist
    in der Produktion naives UTC (aus `gmail_client._iso()`), die Testdaten müssen dieselbe
    Konvention haben, sonst prüft der Test eine Welt, die es nicht gibt.
    """
    from app.models import Email

    if wann is None:
        wann = datetime.datetime.utcnow() - datetime.timedelta(hours=stunden_zurueck)
    e = Email(gmail_message_id=mid or f"test-{kategorie}-{stunden_zurueck}-{richtung}",
              direction=richtung, category=kategorie, received_at=wann,
              from_addr="hr@example.com", subject="Ihre Bewerbung",
              job_id=job.id if job else None,
              company_id=company_id if company_id is not None else (job.company_id if job else None),
              response_time_hours=antwortzeit,
              is_response=(richtung == "incoming"))
    db.add(e)
    db.commit()
    return e


def _stelle(db, firma_name, titel):
    """Firma + Stelle anlegen (die Stelle liefert im Digest Firmenname und Titel)."""
    from app.models import Company, Job

    firma = Company(name=firma_name)
    db.add(firma)
    db.commit()
    db.refresh(firma)
    job = Job(company_id=firma.id, company_name=firma_name, title=titel, portal="LinkedIn",
              status="Absage", found_date=str(datetime.date.today()),
              dedup_key=firma_name.lower() + "|" + titel.lower())
    db.add(job)
    db.commit()
    db.refresh(job)
    return firma, job


def test_absage_von_heute_erscheint_mit_firma_stelle_und_uhrzeit(digest_db):
    """Kernfall: Was der Postfach-Lauf heute an Absagen brachte, steht im Digest."""
    from pipeline.digest import build_digest_html

    _, job = _stelle(digest_db, "Beispiel Group", "(Senior) Consulting Manager")
    vor_zwei_stunden = datetime.datetime.utcnow() - datetime.timedelta(hours=2)
    _mail(digest_db, job=job, antwortzeit=861.0, wann=vor_zwei_stunden)

    html = build_digest_html()

    assert "Absagen der letzten 96 Stunden (1)" in html
    assert "Beispiel Group" in html
    assert "(Senior) Consulting Manager" in html
    erwartete_uhrzeit = (vor_zwei_stunden.replace(tzinfo=datetime.timezone.utc)
                         .astimezone().strftime("%H:%M"))
    assert erwartete_uhrzeit + " Uhr" in _abschnitt(html)


def test_wartezeit_in_tagen_ab_48_stunden_und_in_stunden_darunter(digest_db):
    """Die Wartezeit macht den Unterschied zwischen „Screening" und „lange hingehalten" sichtbar.
    Unter zwei Tagen bleibt die Stundenangabe aussagekräftiger, darüber wären es unlesbare Zahlen
    (861 h statt 36 Tagen)."""
    from pipeline.digest import build_digest_html

    _, schnell = _stelle(digest_db, "Schnell AG", "Rolle A")
    _, langsam = _stelle(digest_db, "Langsam GmbH", "Rolle B")
    _, exakt = _stelle(digest_db, "Grenzfall SE", "Rolle C")
    _mail(digest_db, job=schnell, antwortzeit=36.4, mid="m-schnell")
    _mail(digest_db, job=langsam, antwortzeit=861.0, mid="m-langsam")
    _mail(digest_db, job=exakt, antwortzeit=24.0, mid="m-exakt")

    html = build_digest_html()

    assert "nach 36 h" in html          # unter 48 h → Stunden
    assert "nach 36 Tagen" in html      # 861 h → Tage
    assert "nach 24 h" in html          # klar unter der Grenze
    assert "nach 861" not in _abschnitt(html), (
        "Stundenzahl darf bei langen Wartezeiten nicht durchschlagen")


def test_ein_tag_wird_nicht_als_ein_tagen_geschrieben(digest_db):
    """Kleinigkeit, die sonst jedem sofort auffällt: Singular."""
    from pipeline.digest import build_digest_html

    _, job = _stelle(digest_db, "Eintag AG", "Rolle")
    _mail(digest_db, job=job, antwortzeit=30.0 * 24)   # 30 Tage — Plural
    _, job2 = _stelle(digest_db, "Grenze AG", "Rolle")
    _mail(digest_db, job=job2, antwortzeit=50.0, mid="m-eintag")   # 50 h → 2 Tage

    html = build_digest_html()

    assert "nach 30 Tagen" in html
    assert "nach 2 Tagen" in html
    assert " 1 Tagen" not in _abschnitt(html), "Singular ist 1 Tag, nicht 1 Tagen"


def test_absage_von_gestern_abend_ist_im_fenster(digest_db):
    """DER Grund für die Umstellung auf ein gleitendes Fenster (28.08.2026): Mit einem Kalendertag
    fiel die Abendpost systematisch durch. Eine Absage von gestern 22 Uhr tauchte in keinem
    Bericht auf, den man morgens liest — sie war „gestern", bevor sie je jemand gesehen hatte.

    Am echten Bestand belegt: Eine Absage vom 27.08. 17:00 Uhr war in der
    Kalendertag-Fassung unsichtbar und steht seit der Umstellung drin."""
    from pipeline.digest import build_digest_html

    _, job = _stelle(digest_db, "Abendpost GmbH", "Rolle von gestern Abend")
    _mail(digest_db, job=job, stunden_zurueck=20)

    html = build_digest_html()

    assert "Absagen der letzten 96 Stunden (1)" in html
    assert "Rolle von gestern Abend" in _abschnitt(html)


def test_absage_vom_wochenende_ist_montags_noch_im_fenster(digest_db):
    """DER Grund für die Verbreiterung auf 96 Stunden (31.08.2026): „Die aktuellen 24h
    sind gerade bei einem Wochenende zu kurz.“

    Eine Absage vom Freitagabend war montags 24 Stunden alt mal drei — sie tauchte in keinem
    einzigen Bericht auf, den je jemand zu Gesicht bekam, weil freitags, samstags und sonntags
    niemand den Digest liest. Genau diese Luecke schliesst das Vier-Tage-Fenster; 80 Stunden
    entsprechen dem Abstand Freitagabend → Montagmorgen."""
    from pipeline.digest import build_digest_html

    _, job = _stelle(digest_db, "Freitagabend AG", "Rolle vom Wochenende")
    _mail(digest_db, job=job, stunden_zurueck=80)

    abschnitt = _abschnitt(build_digest_html())

    assert "Rolle vom Wochenende" in abschnitt, (
        "80 Stunden — im alten 24-Stunden-Fenster war das unsichtbar")


def test_fenstergrenze_95_stunden_drin_97_stunden_draussen(digest_db):
    """Die Grenze selbst — bewusst mit Abstand nach beiden Seiten geprüft, damit der Test nicht
    an der Laufzeit der Suite hängt."""
    from pipeline.digest import build_digest_html

    _, drin = _stelle(digest_db, "Knapp Drin AG", "Rolle drin")
    _, draussen = _stelle(digest_db, "Knapp Draussen AG", "Rolle draussen")
    _mail(digest_db, job=drin, stunden_zurueck=95, mid="m-drin")
    _mail(digest_db, job=draussen, stunden_zurueck=97, mid="m-draussen")

    abschnitt = _abschnitt(build_digest_html())

    assert "Rolle drin" in abschnitt
    assert "Rolle draussen" not in abschnitt, "97 Stunden liegen ausserhalb des Fensters"


def test_eintrag_von_gestern_traegt_die_tagesmarke(digest_db):
    """Im Fenster liegen Mails mehrerer Tage — die blosse Uhrzeit wäre mehrdeutig.

    Konstruktion: Genau 24 Stunden zurück ist dieselbe Uhrzeit am Vortag, liegt also
    unabhängig von der Laufzeit der Suite immer auf dem gestrigen lokalen Datum."""
    from pipeline.digest import build_digest_html

    _, job = _stelle(digest_db, "Tagesmarke AG", "Rolle mit Marke")
    _mail(digest_db, job=job, stunden_zurueck=24)

    abschnitt = _abschnitt(build_digest_html())

    assert "Rolle mit Marke" in abschnitt
    assert "gestern," in abschnitt


def test_aelterer_eintrag_traegt_den_wochentag_statt_gestern(digest_db):
    """DER Folgefehler, den die Verbreiterung fast angerichtet hätte: Die Marke kannte nur
    zwei Fälle — heute oder „gestern“. Im Vier-Tage-Fenster hätte sie damit unter jede Mail von
    vorgestern und vorvorgestern „gestern“ geschrieben, also eine FALSCHE Angabe statt einer
    fehlenden.

    Der Wochentag ist im Vier-Tage-Fenster eindeutig und beantwortet die eigentliche
    Frage: kam die Absage noch am Freitag oder erst übers Wochenende?"""
    from pipeline.digest import build_digest_html

    _, job = _stelle(digest_db, "Vorvorgestern AG", "Rolle von vor drei Tagen")
    wann_utc = datetime.datetime.utcnow() - datetime.timedelta(hours=72)
    _mail(digest_db, job=job, wann=wann_utc)

    abschnitt = _abschnitt(build_digest_html())
    lokal = wann_utc.replace(tzinfo=datetime.timezone.utc).astimezone()
    kuerzel = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][lokal.weekday()]

    assert kuerzel + ", " + lokal.strftime("%H:%M") + " Uhr" in abschnitt
    assert "gestern," not in abschnitt, "vor drei Tagen ist nicht gestern"


def test_uhrzeit_wird_von_utc_in_lokalzeit_umgerechnet(digest_db):
    """`received_at` ist naives UTC (aus `gmail_client._iso()`). Ohne Umrechnung stünde im
    Bericht eine Uhrzeit, die um den Zeitzonen-Versatz von der abweicht, die im
    Postfach angezeigt wird — im Sommer zwei Stunden."""
    from pipeline.digest import build_digest_html

    _, job = _stelle(digest_db, "Zeitzone AG", "Rolle")
    wann_utc = datetime.datetime.utcnow() - datetime.timedelta(hours=3)
    _mail(digest_db, job=job, wann=wann_utc)

    abschnitt = _abschnitt(build_digest_html())
    lokal = wann_utc.replace(tzinfo=datetime.timezone.utc).astimezone()

    assert lokal.strftime("%H:%M") + " Uhr" in abschnitt
    if lokal.utcoffset().total_seconds() != 0:
        assert wann_utc.strftime("%H:%M") + " Uhr" not in abschnitt, (
            "die rohe UTC-Uhrzeit darf nicht im Bericht stehen")


def test_eigene_gesendete_mail_zaehlt_nicht_als_absage(digest_db):
    """`direction == outgoing` sind Mails, die der Nutzer selbst geschrieben hat. Sie dürfen nie
    als eingegangene Absage gezählt werden — sonst meldet der Digest Absagen, die es nicht gibt."""
    from pipeline.digest import build_digest_html

    _, job = _stelle(digest_db, "Ausgehend AG", "Rolle")
    _mail(digest_db, job=job, richtung="outgoing")

    html = build_digest_html()

    assert "Absagen der letzten 96 Stunden (0)" in html
    assert "Ausgehend AG" not in _abschnitt(html)


def test_absage_ohne_stellenzuordnung_wird_trotzdem_gezeigt(digest_db):
    """Phase 36: Absagen ohne erkennbaren Stellenbezug werden bewusst trotzdem erfasst. Sie
    dürfen im Digest nicht verschwinden — die Firma steht dann über `company_id` zur Verfügung."""
    from app.models import Company
    from pipeline.digest import build_digest_html

    firma = Company(name="Ohne Stelle GmbH")
    digest_db.add(firma)
    digest_db.commit()
    digest_db.refresh(firma)
    _mail(digest_db, job=None, company_id=firma.id)

    html = build_digest_html()

    assert "Absagen der letzten 96 Stunden (1)" in html
    assert "Ohne Stelle GmbH" in html
    assert "ohne Stellenzuordnung" in html


def test_absage_ganz_ohne_firma_bricht_den_digest_nicht(digest_db):
    """Robustheit: weder Stelle noch Firma zugeordnet — der Digest muss trotzdem bauen."""
    from pipeline.digest import build_digest_html

    _mail(digest_db, job=None, company_id=None, antwortzeit=None)

    html = build_digest_html()

    assert "Absagen der letzten 96 Stunden (1)" in html
    assert "Firma unbekannt" in html


def test_ueberschrift_leertext_und_fenster_haengen_an_derselben_konstante(digest_db, monkeypatch):
    """Die Fensterbreite stand vor dem 31.08.2026 an vier Stellen: Grenze, Überschrift,
    Leertext und Kommentar. Wer sie ändert, ändert leicht drei davon — der Bericht behauptet
    dann eine andere Zeitspanne, als er rechnet, und niemand sieht es ihm an.

    Der Test dreht die Konstante auf 48 und prüft beide Enden: die Beschriftung folgt, und
    eine Mail von vor 60 Stunden fällt heraus."""
    from pipeline import digest as digest_modul

    monkeypatch.setattr(digest_modul, "ABSAGEN_FENSTER_STUNDEN", 48)
    _, job = _stelle(digest_db, "Ausserhalb AG", "Rolle nach 60 Stunden")
    _mail(digest_db, job=job, stunden_zurueck=60)

    html = digest_modul.build_digest_html()

    assert "Absagen der letzten 48 Stunden (0)" in html
    assert "In den letzten 48 Stunden keine Absagen." in html
    assert "Rolle nach 60 Stunden" not in _abschnitt(html, 48)


def test_ohne_absagen_bleibt_der_abschnitt_leer_aber_vorhanden(digest_db):
    """Ein leerer Abschnitt ist eine Aussage („heute nichts"), kein Fehler — er verschwindet
    deshalb nicht."""
    from pipeline.digest import build_digest_html

    html = build_digest_html()

    assert "Absagen der letzten 96 Stunden (0)" in html
    assert "In den letzten 96 Stunden keine Absagen." in html
    assert "Letzte 7 Tage: 0" in html
