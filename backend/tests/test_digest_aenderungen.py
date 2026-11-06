"""Tages-Digest: „Heute geändert" wird zweispaltig (Wunsch vom 03.09.2026).

Wörtlich: „Danach erweitere bitte den Bereich 'Heute geändert'. Das sollte 2-spaltig
werden. In der ersten Spalte die Firma + Position und Ort wie wir es haben, in der 2ten Spalte
rechts daneben WAS geändert wurde, also Prüfung / kein Match / beworben / etc."

Die rechte Spalte fasst den Tag als KETTE zusammen (Spec §2.2): eine Stelle lief am 03.09. real
`Neu → Prüfen` und danach `Prüfen → Beworben` — am echten Bestand belegt (Spec §0), dass
mehrere Wechsel an einem Tag vorkommen. Der letzte Schritt allein wäre eine unehrliche
Tagesbilanz.

`job_rows` bleibt für „Neue Treffer" und „Offene Aktionen" unangetastet (Spec §2.5) — die
neue zweispaltige Darstellung lebt in einer eigenen Funktion `geaendert_rows`.

EIGENE DATENBANK JE TEST (`digest_db`): Wie in `test_digest_absagen.py` — die Suite teilt sich
über `conftest._db_ready` sonst eine tmp-Datenbank, die zwischen Tests nicht geleert wird.

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention).
"""
import contextlib
import datetime
import itertools
import os
import time

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


def _abschnitt(html: str) -> str:
    """Nur den Heute-geändert-Abschnitt aus dem Digest schneiden.

    Wie beim Beworben-Abschnitt (dortiges Vorbild): Ein heute geänderter Job kann auch in
    „Beworben bei" auftauchen (heutiger `→ Beworben`-Log), sein Firmenname stünde also ohnehin
    zweimal im Dokument. Ohne diesen Schnitt prüfte eine Nicht-enthalten-Zusicherung das
    Falsche.
    """
    start = html.index("Heute geändert")
    return html[start:html.index("</section>", start)]


_ZEITZAEHLER = itertools.count(1)


def _log(db, job, eintrag, *, art="auto", wann=None):
    """Eine JobLog-Zeile mit naivem UTC `created_at`, wie in der Produktion.

    Ohne `wann` bekommt jeder Aufruf einen Zeitpunkt kurz nach der heutigen lokalen Mitternacht,
    aufsteigend in Aufrufreihenfolge: erster Aufruf = frueher am Tag.

    BEWUSST NICHT `utcnow() - N Stunden`, wie die erste Fassung es tat. Der Digest filtert die
    Eintraege auf den heutigen lokalen Tag; laeuft die Suite frueh am Morgen, liegt
    „6 Stunden zurueck“ auf GESTERN und faellt aus diesem Filter. Am 04.09.2026 um 05:40 UTC
    ist genau das passiert — und der Schaden war zweierlei:
      * `test_tageskette_fasst_mehrere_wechsel_zusammen` wurde rot (nur ein Wechsel uebrig),
      * `test_hin_und_zurueck_zeigt_nur_den_letzten_wechsel` blieb GRUEN, ohne noch irgendetwas
        zu pruefen — von zwei Wechseln kam einer an, und dessen Anzeige erfuellte die Erwartung
        zufaellig. Ein Test, der zur falschen Tageszeit stumm nichts mehr prueft, ist schlimmer
        als einer, der rot wird.
    """
    from app import zeit
    from app.models import JobLog

    if wann is None:
        wann = zeit.tagesbeginn_utc() + datetime.timedelta(seconds=next(_ZEITZAEHLER))
    log = JobLog(job_id=job.id, eintrag=eintrag, art=art, created_at=wann)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def _stelle(db, firma_name, titel, *, status="Beworben", match_score=None, location=None,
            heute_geaendert=True):
    """Firma + Stelle anlegen. `heute_geaendert` setzt `updated_at` auf jetzt, damit der Job
    im Abschnitt „Heute geändert" auftaucht — genau wie in der Produktion (`updated_at` faellt
    auf den heutigen lokalen Tag, Spec §2.6)."""
    from app.models import Company, Job

    firma = Company(name=firma_name)
    db.add(firma)
    db.commit()
    db.refresh(firma)
    job = Job(company_id=firma.id, company_name=firma_name, title=titel, portal="LinkedIn",
              status=status, found_date=str(datetime.date.today()), match_score=match_score,
              location=location, dedup_key=firma_name.lower() + "|" + titel.lower())
    db.add(job)
    db.commit()
    db.refresh(job)
    if heute_geaendert:
        job.updated_at = datetime.datetime.utcnow()
        db.add(job)
        db.commit()
        db.refresh(job)
    return firma, job


def test_statuswechsel_steht_in_der_zweiten_spalte(digest_db):
    """Kernfall: Ein heutiger Statuswechsel `Prüfen → Beworben` erscheint mit der Beworben-
    Farbklasse `chg bew`."""
    from pipeline.digest import build_digest_html

    _, job = _stelle(digest_db, "Beispiel Group", "(Senior) Consulting Manager")
    _log(digest_db, job, "Status: Prüfen → Beworben")

    abschnitt = _abschnitt(build_digest_html())

    assert 'class="chg bew"' in abschnitt
    assert "Prüfen → Beworben" in abschnitt


def test_review_zusatz_wird_abgeschnitten(digest_db):
    """`Status: Neu → Prüfen (Review)` ist ein Herkunftsvermerk, kein Statusname — er gehört
    nicht in den Bericht. Ergebnis muss `Neu → Prüfen` ohne den Klammerzusatz sein."""
    from pipeline.digest import build_digest_html

    _, job = _stelle(digest_db, "Klammer AG", "Rolle")
    _log(digest_db, job, "Status: Neu → Prüfen (Review)")

    abschnitt = _abschnitt(build_digest_html())

    assert "Neu → Prüfen" in abschnitt
    assert "(Review)" not in abschnitt


def test_tageskette_fasst_mehrere_wechsel_zusammen(digest_db):
    """Fall aus der Spec: `Neu → Prüfen` (früher am Tag) und `Prüfen → Beworben`
    (später) fassen sich zur ehrlichen Tagesbilanz `Neu → Beworben` zusammen."""
    from pipeline.digest import build_digest_html

    _, job = _stelle(digest_db, "Kette AG", "Rolle")
    _log(digest_db, job, "Status: Neu → Prüfen")
    _log(digest_db, job, "Status: Prüfen → Beworben")

    abschnitt = _abschnitt(build_digest_html())

    assert "Neu → Beworben" in abschnitt
    assert "Prüfen → Beworben" not in abschnitt
    assert "Neu → Prüfen" not in abschnitt


def test_hin_und_zurueck_zeigt_nur_den_letzten_wechsel(digest_db):
    """Sind Anfangs- und Endstatus über den Tag gleich (hin und zurück), stünde eine naive
    Kette faelschlich `Prüfen → Prüfen`. Es gilt dann nur der jüngste Wechsel."""
    from pipeline.digest import build_digest_html

    _, job = _stelle(digest_db, "Hin Und Zurueck AG", "Rolle")
    _log(digest_db, job, "Status: Prüfen → Kein Match")
    _log(digest_db, job, "Status: Kein Match → Prüfen")

    abschnitt = _abschnitt(build_digest_html())

    assert "Prüfen → Prüfen" not in abschnitt
    assert "Kein Match → Prüfen" in abschnitt


def test_ohne_statuswechsel_zeigt_die_manuelle_notiz(digest_db):
    """Stufe 2 der Regel (Spec §2.2): Ohne Statuswechsel ist eine manuelle Notiz die einzige
    Information darüber, was passiert ist. Suffix `neutral`."""
    from pipeline.digest import build_digest_html

    _, job = _stelle(digest_db, "Notiz AG", "Rolle")
    _log(digest_db, job, "Telefonat mit HR, Rückmeldung naechste Woche", art="manuell")

    abschnitt = _abschnitt(build_digest_html())

    assert "Telefonat mit HR, Rückmeldung naechste Woche" in abschnitt
    assert 'class="chg neutral"' in abschnitt


def test_lange_notiz_wird_gekuerzt(digest_db):
    """Notizen länger als 60 Zeichen werden gekürzt und bekommen ein `…` angehängt (Spec §2.2)."""
    from pipeline.digest import build_digest_html

    _, job = _stelle(digest_db, "Lange Notiz AG", "Rolle")
    lange_notiz = "A" * 80
    _log(digest_db, job, lange_notiz, art="manuell")

    abschnitt = _abschnitt(build_digest_html())

    assert lange_notiz not in abschnitt
    assert ("A" * 60 + "…") in abschnitt


def test_ganz_ohne_log_zeigt_den_aktuellen_status(digest_db):
    """Stufe 3 (Spec §2.2): Kein Log — ein Feld-Edit hat `updated_at` ohne JobLog-Eintrag
    geändert. Die Zelle bleibt trotzdem nicht leer, sonst sähe sie nach einem Fehler aus."""
    from pipeline.digest import build_digest_html

    _, job = _stelle(digest_db, "Ohne Log AG", "Rolle", status="Interview")

    abschnitt = _abschnitt(build_digest_html())

    assert "Interview" in abschnitt
    assert 'class="chg neutral"' in abschnitt


@pytest.mark.parametrize("nachher,suffix", [
    ("Beworben", "bew"),
    ("Interview", "iv"),
    ("Absage", "absage"),
    ("Kein Match", "kein"),
    ("Prüfen", "pruef"),
    ("Sonstiges", "neutral"),
])
def test_jeder_zielstatus_bekommt_seine_farbklasse(digest_db, nachher, suffix):
    """Die Farbtabelle aus Spec §2.3, Zeile für Zeile."""
    from pipeline.digest import build_digest_html

    _, job = _stelle(digest_db, f"Farbe {suffix} AG", "Rolle")
    _log(digest_db, job, f"Status: Vorher → {nachher}")

    abschnitt = _abschnitt(build_digest_html())

    assert f'class="chg {suffix}"' in abschnitt


def test_linke_spalte_bleibt_unveraendert(digest_db):
    """Links bleiben Score-Badge, Firma fett, Titel, Ort (muted) unverändert stehen (Spec §2.1)."""
    from pipeline.digest import build_digest_html

    _, job = _stelle(digest_db, "Linksbuendig AG", "Rolle Links", match_score=4,
                      location="Berlin, München")
    _log(digest_db, job, "Status: Prüfen → Beworben")

    abschnitt = _abschnitt(build_digest_html())

    assert "Linksbuendig AG" in abschnitt
    assert "Rolle Links" in abschnitt
    assert "Berlin, München" in abschnitt
    assert ">4<" in abschnitt


def test_neue_treffer_bleiben_einspaltig(digest_db):
    """`job_rows` bleibt unberührt — der Neue-Treffer-Abschnitt enthält kein `row zwei`
    (Spec §2.5: die zweispaltige Darstellung ist eine eigene Funktion, `job_rows` rendert
    weiterhin auch „Neue Treffer" und „Offene Aktionen" einspaltig)."""
    from app.models import Company, Job
    from pipeline.digest import build_digest_html

    firma = Company(name="Neuer Treffer AG")
    digest_db.add(firma)
    digest_db.commit()
    digest_db.refresh(firma)
    job = Job(company_id=firma.id, company_name="Neuer Treffer AG", title="Frische Rolle",
              portal="LinkedIn", status="Neu", found_date=str(datetime.date.today()),
              dedup_key="neuer treffer ag|frische rolle")
    digest_db.add(job)
    digest_db.commit()

    html = build_digest_html()

    start = html.index("Neue Treffer")
    neue_treffer_abschnitt = html[start:html.index("</section>", start)]

    assert "Frische Rolle" in neue_treffer_abschnitt
    assert "row zwei" not in neue_treffer_abschnitt


def test_mehr_als_15_aenderungen_werden_gedeckelt_mit_hinweis(digest_db):
    """Wie beim Beworben-Abschnitt (Spec §1.4/§2.5): Deckel bei 15 Einträgen, danach ein
    sichtbarer Hinweis auf die weiteren — das bestehende `job_rows` schnitt hier früher
    stumm ab."""
    from pipeline.digest import build_digest_html

    for i in range(17):
        _, job = _stelle(digest_db, f"Firma {i:02d}", f"Rolle {i:02d}")
        _log(digest_db, job, "Status: Prüfen → Beworben")

    abschnitt = _abschnitt(build_digest_html())
    zeilen_count = abschnitt.count("Rolle ")

    assert zeilen_count == 15
    assert "und 2 weitere" in abschnitt


def test_klammer_im_statusnamen_verschluckt_den_wechsel_nicht(digest_db):
    """Der Herkunftsvermerk wird am ZEILENENDE abgeschnitten, nicht ab der ersten Klammer.

    Die erste Fassung schnitt ab der ersten Fundstelle von „ (". Traegt ein Statusname selbst
    einmal eine Klammer, faellt damit der Pfeil mit weg — der Wechsel verschwindet dann STUMM aus
    dem Bericht, statt nur unsauber beschriftet zu sein. Am Bestand vom 03.09.2026 gab es diesen
    Fall in 196 Status-Eintraegen kein einziges Mal; der Test haelt die robuste Fassung trotzdem
    fest, weil ein stiller Datenverlust nicht auffaellt, wenn er eintritt.
    """
    from pipeline.digest import status_kette

    class _Log:
        def __init__(self, eintrag):
            self.eintrag = eintrag
            self.art = "auto"
            self.created_at = __import__("datetime").datetime(2026, 9, 3, 8, 0)

    assert status_kette([_Log("Status: Prüfen (extern) → Beworben (Review)")]) == (
        "Prüfen (extern)", "Beworben")


def test_endstationen_sind_grau_geparkt_dagegen_nicht():
    """Neun Status gibt es im System, die erste Farbtabelle kannte fuenf davon.

    „Nicht verfuegbar", „Beirat abgelehnt" und „Keine Rueckmeldung" sind Endstationen wie
    „Kein Match" — 144 der 452 Stellen im Bestand (03.09.2026) standen ohne diese Zuordnung
    neutral-blau da, sahen im Bericht also aus wie etwas, das noch laeuft.

    „Geparkt" ist die Ausnahme und bleibt neutral: aufgeschoben ist nicht beendet.
    """
    from pipeline.digest import _chg_suffix

    for status in ("Kein Match", "Nicht verfügbar", "Beirat abgelehnt", "Keine Rückmeldung"):
        assert _chg_suffix(status) == "kein", status
    assert _chg_suffix("Geparkt") == "neutral"


@contextlib.contextmanager
def _zeitzone(name):
    """Prozess-Zeitzone fuer die Dauer des Blocks wechseln und danach sauber zuruecksetzen.

    Windows kennt `time.tzset` nicht; dort ueberspringen sich die Tests selbst. Geprueft wird die
    Tagesgrenze dann in den Linux-Laeufen.
    """
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset gibt es nur unter Unix")
    bisher = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    try:
        yield
    finally:
        if bisher is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = bisher
        time.tzset()


def _geaendert_um(db, firma, wann):
    """Stelle, deren letzte Aenderung samt Statuswechsel genau auf `wann` (naives UTC) faellt."""
    _, job = _stelle(db, firma, "Rolle", heute_geaendert=False)
    job.updated_at = wann
    db.add(job)
    db.commit()
    _log(db, job, "Status: Prüfen → Beworben", wann=wann)


def test_aenderung_nach_lokaler_mitternacht_zaehlt_als_heute(digest_db):
    """Der Tag im Bericht ist der LOKALE Tag des Nutzers, gespeichert ist aber UTC.

    In Berlin faellt 00:00:01 Uhr noch auf den UTC-Vortag. Vergleicht man das UTC-Datum mit dem
    lokalen, fehlt jede Aenderung aus der ersten Stunde des Tages (im Sommer aus den ersten zwei)
    den ganzen Tag lang in „Heute geändert“.
    """
    from app import zeit
    from pipeline.digest import build_digest_html

    with _zeitzone("Europe/Berlin"):
        _geaendert_um(digest_db, "Nachtschicht AG",
                      zeit.tagesbeginn_utc() + datetime.timedelta(seconds=1))
        abschnitt = _abschnitt(build_digest_html())

    assert "Nachtschicht AG" in abschnitt
    assert "Prüfen → Beworben" in abschnitt


def test_aenderung_vor_lokaler_mitternacht_zaehlt_nicht_als_heute(digest_db):
    """Die Gegenrichtung, westlich von UTC: In New York liegt 23:59:59 Uhr von gestern schon auf
    dem UTC-Datum von heute. Der UTC-Vergleich meldete diese Stelle faelschlich als heute geaendert.
    """
    from app import zeit
    from pipeline.digest import build_digest_html

    with _zeitzone("America/New_York"):
        _geaendert_um(digest_db, "Gestern Inc",
                      zeit.tagesbeginn_utc() - datetime.timedelta(seconds=1))
        abschnitt = _abschnitt(build_digest_html())

    assert "Gestern Inc" not in abschnitt
