"""Tests für `pipeline/absagen_bericht.py` (P2-79): neuester Lost-Order-Bericht und Wochenrhythmus.

Kein app.*/pipeline.*-Import auf Modulebene (conftest-Konvention).
"""
import datetime
import os
import uuid


def _bericht(ordner, name, mtime=None):
    ordner.mkdir(parents=True, exist_ok=True)
    p = ordner / name
    p.write_text("<html>Bericht</html>", encoding="utf-8")
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


def test_datum_kommt_aus_dem_namen_nicht_aus_der_aenderungszeit(tmp_path):
    from pipeline import absagen_bericht as ab
    # Der Juli-Bericht wurde im August angefasst (Favicon-Nachrüstung) — er bleibt der ältere.
    august = datetime.datetime(2026, 8, 28, 13, 57).timestamp()
    _bericht(tmp_path, "20260709_Analyse_Absagen.html", mtime=august)
    neuer = _bericht(tmp_path, "20260801_Analyse_Absagen.html",
                     mtime=datetime.datetime(2026, 8, 1, 9, 0).timestamp())
    pfad, datum = ab.neuester(tmp_path)
    assert pfad == neuer and datum == datetime.date(2026, 8, 1)


def test_altes_namensformat_und_fehlender_ordner(tmp_path):
    from pipeline import absagen_bericht as ab
    assert ab.neuester(tmp_path / "gibt_es_nicht") is None
    _bericht(tmp_path, "2026_07_09_Analyse_Absagen_Alt.html")
    assert ab.neuester(tmp_path)[1] == datetime.date(2026, 7, 9)


def test_ohne_datum_im_namen_gilt_die_aenderungszeit(tmp_path):
    from pipeline import absagen_bericht as ab
    p = _bericht(tmp_path, "Analyse_Absagen.html",
                 mtime=datetime.datetime(2026, 9, 3, 12, 0).timestamp())
    assert ab.berichtsdatum(p) == datetime.date(2026, 9, 3)


def test_ein_bericht_je_kalenderwoche(tmp_path):
    from pipeline import absagen_bericht as ab
    montag = datetime.date(2026, 10, 19)
    # Kein Bericht → fällig
    assert ab.faellig(montag, tmp_path, anzahl=5)[0] is True
    # Bericht vom Sonntag davor → am Montag fällig
    _bericht(tmp_path, "20261018_Analyse_Absagen.html")
    ok, grund = ab.faellig(montag, tmp_path, anzahl=5)
    assert ok is True and "18.10.2026" in grund
    # Bericht vom Montag selbst → für den Rest der Woche erledigt, bis einschließlich Sonntag
    _bericht(tmp_path, "20261019_Analyse_Absagen.html")
    for tag in range(7):
        ok, grund = ab.faellig(montag + datetime.timedelta(days=tag), tmp_path, anzahl=5)
        assert ok is False and "19.10.2026" in grund
    # Nächster Montag → wieder fällig
    assert ab.faellig(montag + datetime.timedelta(days=7), tmp_path, anzahl=5)[0] is True


def test_ausgefallener_montag_wird_in_derselben_woche_nachgeholt(tmp_path):
    from pipeline import absagen_bericht as ab
    _bericht(tmp_path, "20261012_Analyse_Absagen.html")      # Montag der Vorwoche
    assert ab.faellig(datetime.date(2026, 10, 21), tmp_path, anzahl=5)[0] is True   # Mittwoch


def test_nichts_auszuwerten_heisst_ueberspringen(tmp_path):
    from pipeline import absagen_bericht as ab
    ok, grund = ab.faellig(datetime.date(2026, 10, 19), tmp_path, anzahl=0)
    assert ok is False and "keine Absagen" in grund


def test_anzahl_zaehlt_ohne_beispieldaten_und_ohne_geloeschte(session):
    from app.models import Job
    from pipeline import absagen_bericht as ab

    vorher = ab.anzahl_auswertbar()
    suffix = uuid.uuid4().hex[:8]

    def job(status, **kw):
        session.add(Job(company_name=f"Zaehl AG {suffix}", title="Leitung", status=status,
                        dedup_key=f"zaehl|{status}|{uuid.uuid4().hex[:6]}", **kw))

    job("Absage")
    job("Keine Rückmeldung", portal="LinkedIn")
    job("Absage", portal="Beispieldaten")
    job("Absage", deleted_at=datetime.datetime(2026, 10, 1))
    job("Beworben")
    session.commit()
    assert ab.anzahl_auswertbar() == vorher + 2
