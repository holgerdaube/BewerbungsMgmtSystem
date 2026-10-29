"""Tests für P2-79 — Coach-Site: Reiter „Tages-Digest“ (`pipeline/coach_export.py` + `pipeline/digest.py`).

Auftrag 16.10.2026: Neben „Übersicht“ steht ein Reiter „Tages-Digest“, der mit jedem Tageslauf
erneuert wird. Der Digest ist EINE Quelle: `digest.digest_inhalt(fuer_coach=True)` liefert den Inhalt, die
Coach-Site setzt ihn in ihre Seitenhülle. Diese Datei prüft die Seite und ihre Verdrahtung; die Sperrliste
(keine Mail-Adressen, keine Notiztexte, kein `next_step`) hält `test_coach_export_sperrliste.py` mit
Marker-Strings fest.

Deckt ab: Reihenfolge der Reiter in allen vier Seiten; die Abschnitte der Seite (drin: Neue Treffer, Absagen,
Beworben bei, Statuswechsel; draußen: Zu beantworten, Offene Aktionen, Notiztext); `tages_digest: false` (weder
Datei noch Reiter) und das Fehlen des Schlüssels (Seite da); die drei alten Seiten sind bis auf den Reiter
unverändert; die Zeilen-Regeln des Digest stehen im Quelltext nur einmal (A4); der normale `build_digest_html()`
bleibt unverändert (Regression: Zu beantworten, manuelle Notiz, Offene Aktionen); der Lost-Order-Link trägt das
Datum aus dem Dateinamen.

EIGENE DATENBANK JE TEST (`coach_db`): Der Digest zeigt je Abschnitt nur die ersten 15 Zeilen, die geteilte
Test-DB sammelt Zeilen aller früheren Tests (Vorbild: `digest_db` in test_digest_absagen.py). `digest.engine`
und `coach_export.engine` sind Modul-Globals, ein `monkeypatch` auf beide genügt.

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention).
"""
import datetime
import os
import re
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

REIHENFOLGE = ["Übersicht", "Tages-Digest", "Stellen & Bewerbungen", "Absagen & Muster"]
NAV_RE = re.compile(r'<a href="[^"]+" class="[^"]*">([^<]+)</a>')
STAND_RE = re.compile(r"Stand \d{2}\.\d{2}\.\d{4} \d{2}:\d{2}")


@pytest.fixture()
def coach_db(session, tmp_path, monkeypatch):
    """Eine frische Datenbank, ein leerer Analysen-Ordner und ein eigener Export-Ordner nur für diesen Test.
    `session` (geteilte Test-DB) bleibt als Fixture dabei: Sie stellt sicher, dass `app.db` an das
    Wegwerf-Verzeichnis gebunden ist, bevor irgendetwas importiert wird."""
    from sqlmodel import Session, SQLModel, create_engine

    import app.models  # noqa: F401  — Import registriert die Tabellen in SQLModel.metadata
    from pipeline import absagen_bericht, coach_export, digest

    eng = create_engine("sqlite:///" + str(tmp_path / "coach.sqlite"))
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(digest, "engine", eng)
    monkeypatch.setattr(coach_export, "engine", eng)
    monkeypatch.setattr(coach_export, "_EXPORT_DIR", tmp_path / "coach_site")
    (tmp_path / "analysen").mkdir()
    monkeypatch.setattr(absagen_bericht, "ordner", lambda: tmp_path / "analysen")
    with Session(eng) as s:
        yield s


def _heute_mittag() -> datetime.datetime:
    """Heute 12:00 als naiver Zeitpunkt. Bewusst nicht `utcnow()`: Der Digest vergleicht `.date()` mit dem
    LOKALEN Datum; zwischen 0 und 2 Uhr Ortszeit läge `utcnow()` auf gestern, die Zeile fiele still aus
    „Heute geändert“ und der Test prüfte nichts mehr."""
    return datetime.datetime.combine(datetime.date.today(), datetime.time(12, 0))


def _stelle(db, firma, status, *, score=3, heute=False, **felder):
    from app.models import Job

    j = Job(company_name=firma, title="Director PS", status=status, match_score=score,
            found_date=datetime.date.today().isoformat(), location="Hamburg",
            dedup_key=f"coachdigest|{firma}|{uuid.uuid4().hex[:6]}",
            url=f"https://example.invalid/{uuid.uuid4().hex[:6]}", **felder)
    if heute:
        j.updated_at = _heute_mittag()
    db.add(j)
    db.commit()
    db.refresh(j)
    return j


def _log(db, job, eintrag, art="auto"):
    from app.models import JobLog

    db.add(JobLog(job_id=job.id, eintrag=eintrag, art=art, created_at=_heute_mittag()))
    db.commit()


def _welt(db):
    """Eine kleine Welt mit allem, was der Digest zeigen kann."""
    from app.models import Email

    neu = _stelle(db, "Neutreffer Digest GmbH", "Neu", score=4)
    gewechselt = _stelle(db, "Wechsel Digest AG", "Beworben", score=5, heute=True)
    _log(db, gewechselt, "Status: Prüfen → Beworben")
    nur_notiz = _stelle(db, "Notiz Digest AG", "Interview", score=3, heute=True)
    _log(db, nur_notiz, "Telefonat mit der Personalabteilung, Rückmeldung nächste Woche", art="manuell")
    pruefen = _stelle(db, "Pruef Digest AG", "Prüfen", score=2, next_step="Rückruf vereinbaren")
    absage = _stelle(db, "Absage Digest GmbH", "Absage", score=2)
    db.add(Email(job_id=absage.id, direction="incoming", category="Absage", response_time_hours=30.0,
                 subject="Ihre Bewerbung", received_at=datetime.datetime.utcnow()))
    db.add(Email(job_id=gewechselt.id, direction="incoming", category="Rückfrage", needs_reply=True,
                 from_addr="personal@example.invalid", subject="Rückfrage zu Ihrer Bewerbung",
                 received_at=datetime.datetime.utcnow()))
    db.commit()
    return SimpleNamespace(neu=neu, gewechselt=gewechselt, nur_notiz=nur_notiz, pruefen=pruefen, absage=absage)


def _abschnitt(seite: str, ueberschrift: str) -> str:
    start = seite.index(ueberschrift)
    return seite[start:seite.index("</section>", start)]


def _export(tmp_path, coach_export):
    coach_export.export()
    ordner = tmp_path / "coach_site"
    return {p.name: p.read_text(encoding="utf-8") for p in ordner.glob("*.html")}


def _config(monkeypatch, tmp_path, inhalt: str):
    from pipeline import coach_export

    datei = tmp_path / "coach_export.yaml"
    datei.write_text(inhalt, encoding="utf-8")
    monkeypatch.setattr(coach_export, "_CONFIG_PATH", datei)


# ── Reiter ────────────────────────────────────────────────────────────────────────────────────
def test_reiter_stehen_in_allen_vier_seiten_in_derselben_reihenfolge(coach_db, tmp_path):
    from pipeline import coach_export

    seiten = _export(tmp_path, coach_export)

    assert sorted(seiten) == ["absagen.html", "digest.html", "index.html", "stellen.html"]
    for name, text in seiten.items():
        nav = text[text.index("<nav>"):text.index("</nav>")]
        assert NAV_RE.findall(nav) == REIHENFOLGE, name
    # der aktive Reiter ist je Seite der eigene
    for name, aktiv in (("index.html", "Übersicht"), ("digest.html", "Tages-Digest"),
                        ("stellen.html", "Stellen & Bewerbungen"), ("absagen.html", "Absagen & Muster")):
        assert f'class="aktiv">{aktiv}</a>' in seiten[name], name
        assert seiten[name].count('class="aktiv"') == 1, name
    assert 'href="digest.html"' in seiten["index.html"]


# ── Inhalt der Seite ──────────────────────────────────────────────────────────────────────────
def test_digest_seite_zeigt_die_erlaubten_abschnitte(coach_db, tmp_path):
    from pipeline import coach_export

    w = _welt(coach_db)
    seite = _export(tmp_path, coach_export)["digest.html"]

    assert "Digest vom " + datetime.date.today().strftime("%d.%m.%Y") in seite
    assert "wird mit jedem Tageslauf erneuert" in seite
    # KPIs und die vier erlaubten Abschnitte
    assert 'class="kpis"' in seite
    assert "Neue Treffer" in seite and w.neu.company_name in _abschnitt(seite, "Neue Treffer")
    assert "Absagen der letzten" in seite and w.absage.company_name in _abschnitt(seite, "Absagen der letzten")
    assert "Beworben bei" in seite
    assert "Heute geändert" in seite and w.gewechselt.company_name in _abschnitt(seite, "Heute geändert")
    # der Statuswechsel einer heute geänderten Stelle, mit seiner Farbklasse
    assert "Prüfen → Beworben" in _abschnitt(seite, "Heute geändert")
    assert 'class="chg bew"' in seite


def test_digest_seite_laesst_zu_beantworten_und_offene_aktionen_weg(coach_db, tmp_path):
    from pipeline import coach_export

    _welt(coach_db)
    seite = _export(tmp_path, coach_export)["digest.html"]

    assert "Zu beantworten" not in seite and "Offene Aktionen" not in seite
    assert "Rückfrage zu Ihrer Bewerbung" not in seite and "personal@example.invalid" not in seite
    assert "Rückruf vereinbaren" not in seite                    # next_step der Stelle in Prüfung


def test_heute_geaendert_zeigt_ohne_statuswechsel_den_status_nicht_die_notiz(coach_db, tmp_path):
    from pipeline import coach_export

    w = _welt(coach_db)
    seite = _export(tmp_path, coach_export)["digest.html"]
    geaendert = _abschnitt(seite, "Heute geändert")

    assert w.nur_notiz.company_name in geaendert
    assert "Telefonat mit der Personalabteilung" not in seite
    # Rückfall: der aktuelle Job-Status der Stelle
    zeile = geaendert[geaendert.index(w.nur_notiz.company_name):]
    assert 'class="chg neutral">Interview</span>' in zeile


def test_absagen_abschnitt_zeigt_firma_stelle_und_zeit_ohne_betreff(coach_db, tmp_path):
    from pipeline import coach_export

    w = _welt(coach_db)
    abschnitt = _abschnitt(_export(tmp_path, coach_export)["digest.html"], "Absagen der letzten")

    assert w.absage.company_name in abschnitt and w.absage.title in abschnitt
    assert "nach 30 h" in abschnitt
    assert "Ihre Bewerbung" not in abschnitt                    # Betreff der Absage-Mail


# ── Config ────────────────────────────────────────────────────────────────────────────────────
def test_tages_digest_false_gibt_weder_seite_noch_reiter(coach_db, tmp_path, monkeypatch):
    from pipeline import coach_export

    _config(monkeypatch, tmp_path, "tages_digest: false\n")
    seiten = _export(tmp_path, coach_export)
    erwartet = [n for n in REIHENFOLGE if n != "Tages-Digest"]

    assert sorted(seiten) == ["absagen.html", "index.html", "stellen.html"]
    assert not (tmp_path / "coach_site" / "digest.html").exists()
    for name, text in seiten.items():
        nav = text[text.index("<nav>"):text.index("</nav>")]
        assert NAV_RE.findall(nav) == erwartet, name
        assert "digest.html" not in text, name
    assert "digest.html" not in coach_export.export(dry_run=True)["seiten"]


def test_ohne_den_schluessel_gibt_es_die_seite(coach_db, tmp_path, monkeypatch):
    """Eine ältere Installation kennt den Schlüssel `tages_digest` nicht: Sie bekommt den Reiter."""
    from pipeline import coach_export

    _config(monkeypatch, tmp_path, "status_absagen: [\"Absage\"]\n")

    assert coach_export._lade_config()["tages_digest"] is True
    assert "digest.html" in coach_export.export(dry_run=True)["seiten"]


def test_die_mitgelieferte_config_schaltet_den_reiter_ein():
    from pipeline import coach_export

    assert coach_export._lade_config()["tages_digest"] is True
    assert "tages_digest: true" in coach_export._CONFIG_PATH.read_text(encoding="utf-8")


# ── Die drei alten Seiten bleiben, wie sie waren ──────────────────────────────────────────────
def test_alte_seiten_unterscheiden_sich_nur_um_den_reiter(coach_db, tmp_path, monkeypatch):
    """Mit und ohne `tages_digest` ist jede der drei alten Seiten gleich — bis auf die eine Zeile im
    `<nav>`. (Der Zeitstempel im Fuß ist auf die Minute genau und wird für den Vergleich ausgeblendet.)"""
    from pipeline import coach_export

    _welt(coach_db)
    mit = _export(tmp_path, coach_export)
    _config(monkeypatch, tmp_path, "tages_digest: false\n")
    ohne = _export(tmp_path, coach_export)

    reiter = '<a href="digest.html" class="">Tages-Digest</a>'
    for name in ("index.html", "stellen.html", "absagen.html"):
        assert reiter in mit[name], name
        assert STAND_RE.sub("", mit[name].replace(reiter, "")) == STAND_RE.sub("", ohne[name]), name


def test_zeilen_regeln_stehen_nur_auf_der_digest_seite(coach_db, tmp_path):
    from pipeline import coach_export

    seiten = _export(tmp_path, coach_export)

    for regel in (".row{", ".row.zwei{", ".row.zwei .links{", ".tag{", ".empty{", ".chg.bew{", ".chg.neutral{"):
        assert seiten["digest.html"].count(regel) == 1, regel
        for alt in ("index.html", "stellen.html", "absagen.html"):
            assert regel not in seiten[alt], (regel, alt)


def test_zeilen_regeln_stehen_im_quelltext_nur_einmal():
    """A4: Die Regeln stehen in `digest.py` und werden an die Coach-Site GEREICHT, nicht kopiert."""
    pipeline = Path(__file__).resolve().parent.parent / "pipeline"
    digest_text = (pipeline / "digest.py").read_text(encoding="utf-8")
    coach_text = (pipeline / "coach_export.py").read_text(encoding="utf-8")

    for regel in (".row{", ".row.zwei{", ".row.zwei .links{", ".tag{", ".empty{", ".chg.bew{", ".chg.neutral{"):
        assert digest_text.count(regel) == 1, regel
        assert regel not in coach_text, regel


def test_zeilen_css_folgt_dem_design():
    """Die Zeilen-Regeln nehmen ihre Markenwerte aus dem geltenden Design wie das übrige CSS (`$spur`,
    `$text_auf_zustand`), nicht aus festen Werten."""
    from pipeline import design, digest

    d = design.vorgabe()
    css = digest.zeilen_css(d)

    assert f"border-bottom:1px solid {d.farben['spur']}" in css
    assert "$" not in css
    # und es ist ein Teil dessen, was der Digest selbst schreibt
    for zeile in css.splitlines():
        assert zeile in digest._css(d), zeile


# ── Der normale Digest bleibt, wie er war ─────────────────────────────────────────────────────
def test_normaler_digest_zeigt_weiter_mails_notiz_und_offene_aktionen(coach_db):
    from pipeline.digest import build_digest_html

    w = _welt(coach_db)
    html = build_digest_html()

    assert "Zu beantworten (1)" in html
    assert "personal@example.invalid" in html and "Rückfrage zu Ihrer Bewerbung" in html
    assert "Offene Aktionen" in html and "Rückruf vereinbaren" in html
    assert "Telefonat mit der Personalabteilung" in _abschnitt(html, "Heute geändert")
    assert w.nur_notiz.company_name in html


def test_build_digest_html_ist_huelle_plus_inhalt(coach_db):
    from pipeline.digest import build_digest_html, digest_inhalt

    _welt(coach_db)
    html = build_digest_html()
    inhalt = digest_inhalt()

    assert inhalt in html
    assert html.index('<div class="sub">') < html.index(inhalt) < html.index('<div class="foot">')
    assert digest_inhalt(fuer_coach=False) == inhalt
    assert "<html" not in inhalt and "<style" not in inhalt


# ── aenderung_anzeige(nur_auto=True) ──────────────────────────────────────────────────────────
def _eintrag(text, art, minute=0):
    wann = datetime.datetime(2026, 10, 16, 12, minute)
    return SimpleNamespace(eintrag=text, art=art, created_at=wann)


def test_nur_auto_ignoriert_notizen_und_von_hand_getippte_statuszeilen():
    from pipeline.digest import aenderung_anzeige

    job = SimpleNamespace(status="Interview")
    notiz = _eintrag("Persönliche Notiz zum Gespräch", "manuell")
    getippt = _eintrag("Status: Prüfen → Beworben", "manuell", 1)
    echt = _eintrag("Status: Beworben → Interview", "auto", 2)

    # ohne Filter (normaler Digest): Notiz-Stufe und getippte Zeile zählen wie bisher
    assert aenderung_anzeige(job, [notiz]) == ("Persönliche Notiz zum Gespräch", "neutral")
    assert aenderung_anzeige(job, [getippt]) == ("Prüfen → Beworben", "bew")
    # mit Filter: nur der echte Wechsel, sonst der aktuelle Status
    assert aenderung_anzeige(job, [notiz, getippt], nur_auto=True) == ("Interview", "neutral")
    assert aenderung_anzeige(job, [notiz, getippt, echt], nur_auto=True) == ("Beworben → Interview", "iv")
    assert aenderung_anzeige(job, [], nur_auto=True) == ("Interview", "neutral")


# ── Lost-Order-Link ───────────────────────────────────────────────────────────────────────────
def test_lost_order_link_traegt_das_datum_aus_dem_dateinamen(coach_db, tmp_path):
    """Der neueste Bericht gilt nach dem DATUM IM NAMEN, nicht nach der Änderungszeit: Die ältere Datei hat die
    neuere Änderungszeit (Favicon-Nachrüstung), der Link muss trotzdem auf die vom September zeigen."""
    from pipeline import coach_export

    alt = tmp_path / "analysen" / "20260709_Analyse_Absagen.html"
    neu = tmp_path / "analysen" / "20260915_Analyse_Absagen.html"
    neu.write_text("<html><head></head><body>September</body></html>", encoding="utf-8")
    alt.write_text("<html><head></head><body>Juli</body></html>", encoding="utf-8")
    os.utime(neu, (1_700_000_000, 1_700_000_000))             # die vom September ist die ältere Datei
    os.utime(alt, (1_790_000_000, 1_790_000_000))

    absagen = _export(tmp_path, coach_export)["absagen.html"]

    assert "Vollständiger Muster-Bericht vom 15.09.2026" in absagen
    assert 'href="artefakte/20260915_Analyse_Absagen.html"' in absagen
    assert "20260709" not in absagen and "09.07.2026" not in absagen
    assert (tmp_path / "coach_site" / "artefakte" / "20260915_Analyse_Absagen.html").is_file()


def test_ohne_bericht_gibt_es_keinen_lost_order_abschnitt(coach_db, tmp_path):
    from pipeline import coach_export

    absagen = _export(tmp_path, coach_export)["absagen.html"]

    assert "Lost-Order-Analyse" not in absagen and "Muster-Bericht" not in absagen
