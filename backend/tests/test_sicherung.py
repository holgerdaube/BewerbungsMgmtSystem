"""Tests für app/sicherung.py (P2-52, Paket S1) -- automatische Datenbank-Sicherung: Ablage
(V1), Aufbewahrung (V2, `zu_entfernen`), Einstellungen (V3), Kernfunktionen (`anlegen`/
`rotieren`/`faellig`/`status`, V4) und Takt (V5).

App-Module werden ausschließlich innerhalb der Testfunktionen importiert (Konvention aus
conftest.py) -- diese Datei importiert selbst nichts aus app.*/pipeline.* auf Modulebene. Jeder
Test arbeitet unter `tmp_path`; das echte `data/` wird nie angefasst (kein Test übergibt
`daten_dir`/`db_pfad` ohne `tmp_path`, und `app.db.DATA_DIR`/`DB_PATH` werden nur GEZIELT per
`monkeypatch` auf `tmp_path` umgebogen, nie auf einen echten Pfad).

Mehrere Tests hier lösen ABSICHTLICH echte Fehlschläge/einen echten Takt-Start aus -- dabei
mutiert `app.sicherung` seine modul-globalen Laufzeitwerte (`_letzter_fehler`, `_takt_start`,
`_task`) per `global`, nicht über etwas, das `monkeypatch` automatisch zurückdrehen könnte. Die
autouse-Fixture unten setzt sie vor UND nach jedem Test zurück, damit kein Test vom vorherigen
abhängt (auch nicht über Dateigrenzen hinweg -- `test_sicherung_api.py` importiert dasselbe
Modulobjekt und hat dieselbe Fixture)."""
import asyncio
import contextlib
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _sicherung_globaler_zustand_isoliert():
    import app.sicherung as sicherung

    sicherung._letzter_fehler = None
    sicherung._takt_start = None
    sicherung._task = None
    sicherung._LOCK = threading.Lock()
    yield
    sicherung._letzter_fehler = None
    sicherung._takt_start = None
    sicherung._task = None
    sicherung._LOCK = threading.Lock()


def _kleine_db(pfad: Path, zeilen=("Erste Firma", "Zweite Firma")) -> None:
    """Winzige SQLite-Quelldatei mit ein paar Zeilen (Vorbild test_bms_update.py)."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(pfad))
    conn.execute("CREATE TABLE company (id INTEGER PRIMARY KEY, name TEXT)")
    conn.executemany("INSERT INTO company (name) VALUES (?)", [(z,) for z in zeilen])
    conn.commit()
    conn.close()


def _zeilen_lesen(pfad: Path) -> list:
    conn = sqlite3.connect(str(pfad))
    try:
        return [r[0] for r in conn.execute("SELECT name FROM company ORDER BY id")]
    finally:
        conn.close()


@pytest.fixture()
def _isolierte_datenwurzel(tmp_path, monkeypatch):
    """Biegt app.db.DATA_DIR/DB_PATH auf tmp_path um -- für Tests von `einmal_pruefen()`/
    `starten()`, die (V5-Vertrag) KEINEN eigenen daten_dir-Parameter haben und deshalb
    ausschließlich über `app.db` lesen."""
    from app import db

    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "bewerbung.sqlite")
    return tmp_path


# ── anlegen (V1) ──────────────────────────────────────────────────────────────────────────────
def test_anlegen_erzeugt_zip_mit_genau_einer_datei(tmp_path):
    import zipfile
    from app import sicherung

    db_pfad = tmp_path / "quelle" / "bewerbung.sqlite"
    _kleine_db(db_pfad)

    ziel = sicherung.anlegen(daten_dir=tmp_path, db_pfad=db_pfad,
                              jetzt=datetime(2026, 9, 28, 15, 27, 14))

    assert ziel.name == "bewerbung_2026-09-28_152714.zip"
    assert ziel.parent == tmp_path / "backups" / "auto"
    with zipfile.ZipFile(ziel) as zf:
        assert zf.namelist() == ["bewerbung.sqlite"]
        assert zf.getinfo("bewerbung.sqlite").compress_type == zipfile.ZIP_DEFLATED


def test_anlegen_laesst_sich_zurueckspielen_wie_in_der_anleitung(tmp_path):
    """Entpacken (wie das Zurückspielen von Hand in `BMS_Install_MAC.md` bzw.
    `BMS_Install_Windows.md`, Abschnitt „Ihre Daten“), integrity_check, Zeileninhalt gegen die
    Quelle -- kein Byte-Vergleich: die SQLite-Backup-API kann eine byte-abweichende, aber
    inhaltlich identische Datei erzeugen (Vorbild test_bms_update.py::…wird_gesichert…)."""
    import zipfile
    from app import sicherung

    db_pfad = tmp_path / "quelle" / "bewerbung.sqlite"
    _kleine_db(db_pfad, zeilen=("Alpha GmbH", "Beta AG", "Gamma KG"))

    ziel = sicherung.anlegen(daten_dir=tmp_path, db_pfad=db_pfad, jetzt=datetime(2026, 9, 28, 12, 0, 0))

    entpackt_dir = tmp_path / "entpackt"
    with zipfile.ZipFile(ziel) as zf:
        zf.extractall(entpackt_dir)
    wiederhergestellt = entpackt_dir / "bewerbung.sqlite"
    assert wiederhergestellt.is_file()

    conn = sqlite3.connect(str(wiederhergestellt))
    try:
        zeile = conn.execute("PRAGMA integrity_check").fetchone()
    finally:
        conn.close()
    assert zeile[0] == "ok"
    assert _zeilen_lesen(wiederhergestellt) == _zeilen_lesen(db_pfad)

    ordner = tmp_path / "backups" / "auto"
    punkt_dateien = [p.name for p in ordner.iterdir() if p.name.startswith(".")]
    assert punkt_dateien == []


def test_anlegen_fehler_beim_packen_hinterlaesst_keine_dateien_und_loescht_sich_beim_naechsten_erfolg(
        tmp_path, monkeypatch):
    from app import sicherung

    db_pfad = tmp_path / "quelle" / "bewerbung.sqlite"
    _kleine_db(db_pfad)
    original = sicherung._als_zip_packen
    soll_scheitern = {"wert": True}

    def _vielleicht_kaputt(quelle, ziel_zip):
        if soll_scheitern["wert"]:
            raise RuntimeError("Packen absichtlich kaputt (Test)")
        return original(quelle, ziel_zip)

    monkeypatch.setattr(sicherung, "_als_zip_packen", _vielleicht_kaputt)

    with pytest.raises(RuntimeError):
        sicherung.anlegen(daten_dir=tmp_path, db_pfad=db_pfad, jetzt=datetime(2026, 1, 1, 10, 0, 0))

    ordner = tmp_path / "backups" / "auto"
    assert list(ordner.iterdir()) == []
    status = sicherung.status(daten_dir=tmp_path)
    assert status["letzter_fehler"] is not None
    assert "Packen absichtlich kaputt" in status["letzter_fehler"]["meldung"]

    soll_scheitern["wert"] = False
    sicherung.anlegen(daten_dir=tmp_path, db_pfad=db_pfad, jetzt=datetime(2026, 1, 1, 11, 0, 0))

    status2 = sicherung.status(daten_dir=tmp_path)
    assert status2["letzter_fehler"] is None


def test_anlegen_kaputte_kopie_ergibt_fehler_und_keine_fertige_datei(tmp_path, monkeypatch):
    from app import sicherung

    db_pfad = tmp_path / "quelle" / "bewerbung.sqlite"
    _kleine_db(db_pfad)

    def _immer_kaputt(pfad):
        raise RuntimeError("integrity_check meldet absichtlich einen Fehler (Test)")

    monkeypatch.setattr(sicherung, "_integritaet_pruefen", _immer_kaputt)

    with pytest.raises(RuntimeError):
        sicherung.anlegen(daten_dir=tmp_path, db_pfad=db_pfad, jetzt=datetime(2026, 1, 1, 10, 0, 0))

    ordner = tmp_path / "backups" / "auto"
    assert list(ordner.iterdir()) == []
    assert sicherung.status(daten_dir=tmp_path)["letzter_fehler"] is not None


def test_anlegen_bei_belegter_sperre_wirft_sicherunglaeuft(tmp_path):
    from app import sicherung

    db_pfad = tmp_path / "quelle" / "bewerbung.sqlite"
    _kleine_db(db_pfad)

    sicherung._LOCK.acquire()
    try:
        with pytest.raises(sicherung.SicherungLaeuft):
            sicherung.anlegen(daten_dir=tmp_path, db_pfad=db_pfad, jetzt=datetime(2026, 1, 1, 10, 0, 0))
    finally:
        sicherung._LOCK.release()


def test_anlegen_kollision_in_derselben_sekunde_bekommt_suffix(tmp_path):
    from app import sicherung

    db_pfad = tmp_path / "quelle" / "bewerbung.sqlite"
    _kleine_db(db_pfad)
    jetzt = datetime(2026, 9, 28, 15, 27, 14)

    erste = sicherung.anlegen(daten_dir=tmp_path, db_pfad=db_pfad, jetzt=jetzt)
    zweite = sicherung.anlegen(daten_dir=tmp_path, db_pfad=db_pfad, jetzt=jetzt)
    dritte = sicherung.anlegen(daten_dir=tmp_path, db_pfad=db_pfad, jetzt=jetzt)

    assert erste.name == "bewerbung_2026-09-28_152714.zip"
    assert zweite.name == "bewerbung_2026-09-28_152714_2.zip"
    assert dritte.name == "bewerbung_2026-09-28_152714_3.zip"


def test_anlegen_entfernt_nur_zwischendateien_aelter_als_1h(tmp_path):
    from app import sicherung

    db_pfad = tmp_path / "quelle" / "bewerbung.sqlite"
    _kleine_db(db_pfad)
    ordner = tmp_path / "backups" / "auto"
    ordner.mkdir(parents=True)

    jetzt = datetime(2026, 9, 28, 12, 0, 0)
    alter_rest_sqlite = ordner / ".bewerbung_2026-09-28_095959.sqlite.tmp"   # gut 2 h alt
    alter_rest_zip = ordner / ".bewerbung_2026-09-28_095959.zip.part"
    alter_rest_sqlite.write_bytes(b"rest")
    alter_rest_zip.write_bytes(b"rest")
    frischer_rest = ordner / ".bewerbung_2026-09-28_113000.sqlite.tmp"      # 30 min alt
    frischer_rest.write_bytes(b"frisch")

    sicherung.anlegen(daten_dir=tmp_path, db_pfad=db_pfad, jetzt=jetzt)

    assert not alter_rest_sqlite.exists()
    assert not alter_rest_zip.exists()
    assert frischer_rest.exists()   # jünger als 1 h -- bleibt unberührt


def test_anlegen_ohne_parameter_loest_daten_dir_und_db_pfad_ueber_app_db_auf(tmp_path, monkeypatch):
    """Lehre 27.08.2026: `daten_dir`/`db_pfad` dürfen nie an einen Modulwert gebunden sein --
    ohne Argumente muss `anlegen()` `app.db.DATA_DIR`/`DB_PATH` zur LAUFZEIT lesen, nicht beim
    Import von app.sicherung."""
    from app import db, sicherung

    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    ziel_db = tmp_path / "bewerbung.sqlite"
    monkeypatch.setattr(db, "DB_PATH", ziel_db)
    _kleine_db(ziel_db)

    ziel = sicherung.anlegen(jetzt=datetime(2026, 9, 28, 12, 0, 0))

    assert ziel == tmp_path / "backups" / "auto" / "bewerbung_2026-09-28_120000.zip"
    assert ziel.is_file()


# ── V2: zu_entfernen (reine Funktion) ───────────────────────────────────────────────────────
def test_zu_entfernen_leere_liste():
    from app.sicherung import zu_entfernen

    assert zu_entfernen([], datetime(2026, 9, 28, 12, 0, 0)) == []


def test_zu_entfernen_eine_einzelne_datei_bleibt_immer():
    from app.sicherung import zu_entfernen

    jetzt = datetime(2026, 9, 28, 12, 0, 0)
    alt = ("bewerbung_2020-01-01_000000.zip", datetime(2020, 1, 1))
    assert zu_entfernen([alt], jetzt) == []


def test_zu_entfernen_gleicher_tag_nur_die_neueste_ueberlebt():
    """Zwei Sicherungen desselben Tages, BEIDE außerhalb der letzten 24 h (sonst würde Regel 2
    allein schon beide behalten und der Tages-Vorrang gar nicht geprüft): nur die jüngere darf
    über die Tagesregel überleben, die ältere muss weichen."""
    from app.sicherung import zu_entfernen

    jetzt = datetime(2026, 9, 28, 20, 0, 0)
    heute = ("bewerbung_2026-09-28_120000.zip", datetime(2026, 9, 28, 12, 0, 0))       # neueste insgesamt
    aelter_25 = ("bewerbung_2026-09-25_060000.zip", datetime(2026, 9, 25, 6, 0, 0))    # 3 Tage 14h alt
    neuer_25 = ("bewerbung_2026-09-25_180000.zip", datetime(2026, 9, 25, 18, 0, 0))    # 3 Tage 2h alt

    entfernt = zu_entfernen([heute, aelter_25, neuer_25], jetzt,
                             taeglich=7, woechentlich=0, monatlich=0)

    assert entfernt == ["bewerbung_2026-09-25_060000.zip"]


def _sechzig_tage_datensatz(jetzt: datetime):
    """63 Einträge: ein täglicher Eintrag 12:00 Uhr über 60 Tage plus drei zusätzliche, ÄLTERE
    Einträge (06:00) an drei Tagen außerhalb des 24h-Fensters -- Ground-Truth unabhängig per
    Referenzskript berechnet (Scratchpad dieser Session), s. Testkommentare unten."""
    eintraege = []
    for n in range(60):
        tag = jetzt - timedelta(days=n)
        zeit = tag.replace(hour=12, minute=0, second=0, microsecond=0)
        eintraege.append((f"bewerbung_{zeit.strftime('%Y-%m-%d_%H%M%S')}.zip", zeit))
    for n in (10, 20, 30):
        tag = jetzt - timedelta(days=n)
        zeit = tag.replace(hour=6, minute=0, second=0, microsecond=0)
        eintraege.append((f"bewerbung_{zeit.strftime('%Y-%m-%d_%H%M%S')}.zip", zeit))
    return eintraege


def test_zu_entfernen_60_tage_mehrere_pro_tag_erwartete_menge_exakt():
    """jetzt = 2026-09-28 (Montag) 20:00. Von Hand nachvollzogen: die 7 jüngsten Tage (22.-28.9)
    über die Tagesregel, dazu die neuesten Einträge der nächsten beiden ISO-Wochen (KW 38: der
    20.9, KW 37: der 13.9) über die Wochenregel -- danach sind 4 Wochen erreicht (KW 40/39
    bereits durch die Tagesregel abgedeckt). Keiner der drei zusätzlichen 06:00-Einträge
    überlebt (ihr Tag ist an keiner Stelle ein Überlebender-Tag)."""
    from app.sicherung import zu_entfernen

    jetzt = datetime(2026, 9, 28, 20, 0, 0)
    eintraege = _sechzig_tage_datensatz(jetzt)
    assert len(eintraege) == 63

    entfernt = set(zu_entfernen(eintraege, jetzt))
    behalten = sorted(name for name, _ in eintraege if name not in entfernt)

    erwartet = [
        "bewerbung_2026-09-13_120000.zip", "bewerbung_2026-09-20_120000.zip",
        "bewerbung_2026-09-22_120000.zip", "bewerbung_2026-09-23_120000.zip",
        "bewerbung_2026-09-24_120000.zip", "bewerbung_2026-09-25_120000.zip",
        "bewerbung_2026-09-26_120000.zip", "bewerbung_2026-09-27_120000.zip",
        "bewerbung_2026-09-28_120000.zip",
    ]
    assert behalten == erwartet
    assert len(entfernt) == 63 - 9
    extras = {"bewerbung_2026-09-18_060000.zip", "bewerbung_2026-09-08_060000.zip",
              "bewerbung_2026-08-29_060000.zip"}
    assert extras.issubset(entfernt)   # die drei zusätzlichen Einträge werden NIE behalten


def test_zu_entfernen_60_tage_mit_monatlich():
    """Dieselben 63 Einträge, jetzt zusätzlich `monatlich=3`: die drei jüngsten VORHANDENEN
    Monate (September/August/Juli) kommen über deren jeweils neuesten Eintrag hinzu -- der
    September-Repräsentant (28.9) ist bereits über die Tagesregel behalten, neu sind nur
    31.8. und 31.7."""
    from app.sicherung import zu_entfernen

    jetzt = datetime(2026, 9, 28, 20, 0, 0)
    eintraege = _sechzig_tage_datensatz(jetzt)

    entfernt = set(zu_entfernen(eintraege, jetzt, monatlich=3))
    behalten = sorted(name for name, _ in eintraege if name not in entfernt)

    erwartet = [
        "bewerbung_2026-07-31_120000.zip", "bewerbung_2026-08-31_120000.zip",
        "bewerbung_2026-09-13_120000.zip", "bewerbung_2026-09-20_120000.zip",
        "bewerbung_2026-09-22_120000.zip", "bewerbung_2026-09-23_120000.zip",
        "bewerbung_2026-09-24_120000.zip", "bewerbung_2026-09-25_120000.zip",
        "bewerbung_2026-09-26_120000.zip", "bewerbung_2026-09-27_120000.zip",
        "bewerbung_2026-09-28_120000.zip",
    ]
    assert behalten == erwartet


def test_zu_entfernen_zehn_tage_luecke_trotzdem_sieben_tagesstaende():
    """Sicherungen an den Tagen 0-4 (relativ zu jetzt), dann eine Lücke von zehn Tagen (5-14,
    kein Betrieb), dann weiter zurück wieder Sicherungen. `woechentlich=0`, damit nur die
    Tagesregel isoliert geprüft wird. Erwartung: die 7 jüngsten VORHANDENEN Tage -- die Lücke
    verschiebt das Fenster weiter nach hinten, verkürzt es aber nicht auf weniger als 7."""
    from app.sicherung import zu_entfernen

    jetzt = datetime(2026, 9, 28, 20, 0, 0)
    tage_mit_sicherung = list(range(0, 5)) + list(range(15, 40))
    eintraege = []
    for n in tage_mit_sicherung:
        zeit = (jetzt - timedelta(days=n)).replace(hour=12, minute=0, second=0, microsecond=0)
        eintraege.append((f"bewerbung_{zeit.strftime('%Y-%m-%d_%H%M%S')}.zip", zeit))

    entfernt = set(zu_entfernen(eintraege, jetzt, taeglich=7, woechentlich=0, monatlich=0))
    behalten = sorted(name for name, _ in eintraege if name not in entfernt)

    erwartet = [
        "bewerbung_2026-09-12_120000.zip", "bewerbung_2026-09-13_120000.zip",
        "bewerbung_2026-09-24_120000.zip", "bewerbung_2026-09-25_120000.zip",
        "bewerbung_2026-09-26_120000.zip", "bewerbung_2026-09-27_120000.zip",
        "bewerbung_2026-09-28_120000.zip",
    ]
    assert behalten == erwartet
    assert len(behalten) == 7


# ── rotieren ─────────────────────────────────────────────────────────────────────────────────
def test_rotieren_fasst_fremde_dateien_und_data_backups_nie_an(tmp_path):
    from app import sicherung

    auto_ordner = tmp_path / "backups" / "auto"
    auto_ordner.mkdir(parents=True)
    fremd_sqlite = auto_ordner / "bewerbung_backup_x.sqlite"
    fremd_sqlite.touch()
    notiz = auto_ordner / "notiz.txt"
    notiz.touch()
    punkt_datei = auto_ordner / ".bewerbung_2020-01-01_000000.sqlite.tmp"
    punkt_datei.touch()

    jetzt = datetime(2026, 9, 28, 12, 0, 0)
    for n in range(1, 15):
        zeit = jetzt - timedelta(days=n)
        (auto_ordner / f"bewerbung_{zeit.strftime('%Y-%m-%d_%H%M%S')}.zip").touch()

    direkt = tmp_path / "backups" / "bewerbung_backup_alt.sqlite"
    direkt.touch()

    sicherung.einstellungen_speichern({"taeglich": 1, "woechentlich": 0, "monatlich": 0},
                                       daten_dir=tmp_path)
    entfernt = sicherung.rotieren(daten_dir=tmp_path, jetzt=jetzt)

    assert fremd_sqlite.exists()
    assert notiz.exists()
    assert punkt_datei.exists()
    assert direkt.exists()
    assert len(entfernt) == 13   # 14 eigene Dateien (n=1..14), nur die juengste (n=1) bleibt


def test_rotieren_gibt_leere_liste_ohne_eigene_dateien(tmp_path):
    from app import sicherung

    assert sicherung.rotieren(daten_dir=tmp_path, jetzt=datetime(2026, 9, 28, 12, 0, 0)) == []


# ── faellig ──────────────────────────────────────────────────────────────────────────────────
def test_faellig_true_ohne_jede_sicherung(tmp_path):
    from app.sicherung import faellig

    assert faellig(daten_dir=tmp_path, jetzt=datetime(2026, 9, 28, 10, 0, 0)) is True


def test_faellig_false_wenn_heute_schon_gesichert(tmp_path):
    from app.sicherung import faellig

    ordner = tmp_path / "backups" / "auto"
    ordner.mkdir(parents=True)
    (ordner / "bewerbung_2026-09-28_060000.zip").touch()

    assert faellig(daten_dir=tmp_path, jetzt=datetime(2026, 9, 28, 20, 0, 0)) is False


def test_faellig_true_wenn_nur_gestern_gesichert(tmp_path):
    from app.sicherung import faellig

    ordner = tmp_path / "backups" / "auto"
    ordner.mkdir(parents=True)
    (ordner / "bewerbung_2026-09-27_235900.zip").touch()

    assert faellig(daten_dir=tmp_path, jetzt=datetime(2026, 9, 28, 0, 5, 0)) is True


# ── V3: Einstellungen ────────────────────────────────────────────────────────────────────────
def test_einstellungen_laden_fehlende_datei_ergibt_standard(tmp_path):
    from app.sicherung import _STANDARD_EINSTELLUNGEN, einstellungen_laden

    assert einstellungen_laden(daten_dir=tmp_path) == _STANDARD_EINSTELLUNGEN


def test_einstellungen_laden_kaputtes_json_ergibt_standard_und_loggt(tmp_path, capsys):
    from app.sicherung import _STANDARD_EINSTELLUNGEN, einstellungen_laden

    (tmp_path / "sicherung.json").write_text("{kaputt", encoding="utf-8")

    ergebnis = einstellungen_laden(daten_dir=tmp_path)

    assert ergebnis == _STANDARD_EINSTELLUNGEN
    assert "[sicherung] WARNUNG" in capsys.readouterr().out


def test_einstellungen_speichern_teil_speichern_behaelt_uebrige_werte(tmp_path):
    from app.sicherung import einstellungen_laden, einstellungen_speichern

    einstellungen_speichern({"taeglich": 10, "monatlich": 2}, daten_dir=tmp_path)
    einstellungen_speichern({"aktiv": False}, daten_dir=tmp_path)

    assert einstellungen_laden(daten_dir=tmp_path) == {
        "aktiv": False, "taeglich": 10, "woechentlich": 4, "monatlich": 2,
    }


def test_einstellungen_speichern_unbekannter_schluessel_wirft_value_error(tmp_path):
    from app.sicherung import einstellungen_speichern

    with pytest.raises(ValueError):
        einstellungen_speichern({"unbekannt": 1}, daten_dir=tmp_path)


@pytest.mark.parametrize("aenderung", [
    {"aktiv": "ja"},
    {"aktiv": 1},
    {"taeglich": True},
    {"taeglich": 0},
    {"taeglich": 61},
    {"woechentlich": -1},
    {"woechentlich": 53},
    {"monatlich": -1},
    {"monatlich": 25},
    {"monatlich": 3.5},
])
def test_einstellungen_speichern_ungueltige_werte_wirft_value_error(tmp_path, aenderung):
    from app.sicherung import einstellungen_speichern

    with pytest.raises(ValueError):
        einstellungen_speichern(aenderung, daten_dir=tmp_path)


def test_einstellungen_speichern_schreibt_atomar_ohne_tmp_rest(tmp_path):
    from app.sicherung import einstellungen_speichern

    einstellungen_speichern({"taeglich": 5}, daten_dir=tmp_path)

    assert (tmp_path / "sicherung.json").is_file()
    assert not (tmp_path / "sicherung.json.tmp").exists()


# ── V4: status ───────────────────────────────────────────────────────────────────────────────
def test_status_warnung_bei_fehler(tmp_path):
    from app import sicherung

    sicherung._letzter_fehler = {"zeitpunkt": "2026-09-28T10:00:00+02:00", "meldung": "Testfehler xyz"}

    ergebnis = sicherung.status(daten_dir=tmp_path, jetzt=datetime(2026, 9, 28, 12, 0, 0))

    assert ergebnis["warnung"] == "Die letzte Sicherung ist fehlgeschlagen: Testfehler xyz"


def test_status_warnung_bei_4_tage_alter_sicherung(tmp_path):
    from app import sicherung

    ordner = tmp_path / "backups" / "auto"
    ordner.mkdir(parents=True)
    (ordner / "bewerbung_2026-09-24_090000.zip").touch()   # jetzt(28.9 12:00) minus 4 Tage 3h

    ergebnis = sicherung.status(daten_dir=tmp_path, jetzt=datetime(2026, 9, 28, 12, 0, 0))

    assert ergebnis["warnung"] == "Die letzte Sicherung ist 4 Tage alt."


def test_status_keine_warnung_solange_unter_72h(tmp_path):
    from app import sicherung

    ordner = tmp_path / "backups" / "auto"
    ordner.mkdir(parents=True)
    (ordner / "bewerbung_2026-09-26_130000.zip").touch()   # 2 Tage 23h alt

    ergebnis = sicherung.status(daten_dir=tmp_path, jetzt=datetime(2026, 9, 28, 12, 0, 0))

    assert ergebnis["warnung"] is None


def test_status_keine_warnung_wenn_automatik_aus(tmp_path):
    from app import sicherung

    sicherung.einstellungen_speichern({"aktiv": False}, daten_dir=tmp_path)

    ergebnis = sicherung.status(daten_dir=tmp_path, jetzt=datetime(2026, 9, 28, 12, 0, 0))

    assert ergebnis["aktiv"] is False
    assert ergebnis["warnung"] is None


def test_status_warnung_keine_sicherung_nur_nach_10_minuten_takt(tmp_path):
    from app import sicherung

    jetzt = datetime(2026, 9, 28, 12, 0, 0)

    sicherung._takt_start = jetzt - timedelta(minutes=5)
    assert sicherung.status(daten_dir=tmp_path, jetzt=jetzt)["warnung"] is None

    sicherung._takt_start = jetzt - timedelta(minutes=11)
    assert (sicherung.status(daten_dir=tmp_path, jetzt=jetzt)["warnung"]
            == "Es gibt noch keine automatische Sicherung.")


def test_status_ohne_takt_start_keine_warnung_ohne_sicherung(tmp_path):
    """`_takt_start` ist None, solange `starten()` nie lief (z. B. ein Skript-Aufruf oder ein
    Testkontext ohne Lifespan) -- dann darf Regel 3 nicht feuern, mangels Referenzpunkt."""
    from app import sicherung

    assert sicherung._takt_start is None
    ergebnis = sicherung.status(daten_dir=tmp_path, jetzt=datetime(2026, 9, 28, 12, 0, 0))
    assert ergebnis["warnung"] is None


def test_status_weitere_sicherungen_getrennt_gezaehlt_und_nie_angefasst(tmp_path):
    from app import sicherung

    backups_ordner = tmp_path / "backups"
    backups_ordner.mkdir(parents=True)
    a = backups_ordner / "bewerbung_backup_2026-09-01.sqlite"
    a.write_bytes(b"x" * 100)
    b = backups_ordner / "bewerbung_backup_2026-09-08.zip"
    b.write_bytes(b"y" * 50)
    (backups_ordner / ".versteckt.sqlite").write_bytes(b"z")
    (backups_ordner / "notiz.md").write_text("kein Backup", encoding="utf-8")

    ergebnis = sicherung.status(daten_dir=tmp_path, jetzt=datetime(2026, 9, 28, 12, 0, 0))

    assert ergebnis["weitere"] == {"anzahl": 2, "gesamtgroesse": 150}
    assert a.exists()
    assert b.exists()


def test_status_ordner_anzahl_und_gesamtgroesse_der_eigenen_reihe(tmp_path):
    from app import sicherung

    ordner = tmp_path / "backups" / "auto"
    ordner.mkdir(parents=True)
    (ordner / "bewerbung_2026-09-27_120000.zip").write_bytes(b"a" * 30)
    (ordner / "bewerbung_2026-09-28_120000.zip").write_bytes(b"b" * 70)

    ergebnis = sicherung.status(daten_dir=tmp_path, jetzt=datetime(2026, 9, 28, 20, 0, 0))

    assert ergebnis["ordner"] == str(ordner)
    assert ergebnis["anzahl"] == 2
    assert ergebnis["gesamtgroesse"] == 100
    assert ergebnis["letzte"]["datei"] == "bewerbung_2026-09-28_120000.zip"
    assert ergebnis["letzte"]["groesse"] == 70
    assert ergebnis["letzte"]["zeitpunkt"].startswith("2026-09-28T12:00:00")
    assert ergebnis["laeuft"] is False


# ── V5: einmal_pruefen ───────────────────────────────────────────────────────────────────────
def test_einmal_pruefen_aus_wenn_automatik_deaktiviert(_isolierte_datenwurzel):
    from app import sicherung

    sicherung.einstellungen_speichern({"aktiv": False}, daten_dir=_isolierte_datenwurzel)

    assert sicherung.einmal_pruefen() == "aus"


def test_einmal_pruefen_nicht_faellig_wenn_heute_schon_gesichert(_isolierte_datenwurzel):
    from app import sicherung
    from app import db

    _kleine_db(db.DB_PATH)
    jetzt = datetime(2026, 9, 28, 10, 0, 0)
    sicherung.anlegen(jetzt=jetzt)

    assert sicherung.einmal_pruefen(jetzt=jetzt.replace(hour=15)) == "nicht_faellig"


def test_einmal_pruefen_laeuft_wenn_sperre_belegt(_isolierte_datenwurzel):
    from app import sicherung
    from app import db

    _kleine_db(db.DB_PATH)
    sicherung._LOCK.acquire()
    try:
        ergebnis = sicherung.einmal_pruefen(jetzt=datetime(2026, 9, 28, 10, 0, 0))
    finally:
        sicherung._LOCK.release()

    assert ergebnis == "laeuft"


def test_einmal_pruefen_gesichert_ruft_rotieren_auf(_isolierte_datenwurzel, monkeypatch):
    from app import sicherung
    from app import db

    _kleine_db(db.DB_PATH)
    original_rotieren = sicherung.rotieren
    aufrufe = []

    def _rotieren_spion(*args, **kwargs):
        aufrufe.append((args, kwargs))
        return original_rotieren(*args, **kwargs)

    monkeypatch.setattr(sicherung, "rotieren", _rotieren_spion)

    ergebnis = sicherung.einmal_pruefen(jetzt=datetime(2026, 9, 28, 10, 0, 0))

    assert ergebnis == "gesichert"
    assert len(aufrufe) == 1


def test_einmal_pruefen_fehler_rotiert_nicht(_isolierte_datenwurzel, monkeypatch):
    """Regressionstest: rot ohne die Absicherung, s. Verifikation im Baubericht -- ein
    fehlgeschlagener Lauf darf `rotieren()` NIE aufrufen (sonst würde eine kaputte/fehlende
    neue Sicherung die bestehende Reihe trotzdem ausdünnen)."""
    from app import sicherung
    from app import db

    _kleine_db(db.DB_PATH)

    def _anlegen_kaputt(*args, **kwargs):
        raise RuntimeError("Absichtlich kaputt (Test)")

    monkeypatch.setattr(sicherung, "anlegen", _anlegen_kaputt)
    rotieren_aufrufe = []
    monkeypatch.setattr(sicherung, "rotieren", lambda *a, **kw: rotieren_aufrufe.append(1))

    ergebnis = sicherung.einmal_pruefen(jetzt=datetime(2026, 9, 28, 10, 0, 0))

    assert ergebnis == "fehler"
    assert rotieren_aufrufe == []


# ── V5: starten (Takt) ───────────────────────────────────────────────────────────────────────
def test_starten_ruft_einmal_pruefen_ueber_den_takt_auf_und_ist_idempotent(monkeypatch):
    import app.sicherung as sicherung

    aufrufe = []
    monkeypatch.setattr(sicherung, "_ERSTE_PRUEFUNG_S", 0)
    monkeypatch.setattr(sicherung, "_PRUEF_INTERVALL_S", 3600)
    monkeypatch.setattr(sicherung, "einmal_pruefen", lambda jetzt=None: aufrufe.append(1) or "gesichert")

    async def _lauf():
        sicherung.starten()
        erster_task = sicherung._task
        assert erster_task is not None

        for _ in range(200):
            if aufrufe:
                break
            await asyncio.sleep(0.01)

        sicherung.starten()   # zweiter Aufruf: idempotent
        assert sicherung._task is erster_task

        erster_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await erster_task

    asyncio.run(_lauf())
    assert aufrufe == [1]


# ── Nachbesserungen aus der Abnahme (P2-52) ─────────────────────────────────────────────────────
def test_anlegen_ordner_nicht_anlegbar_meldet_den_fehler_sofort(tmp_path):
    """Scheitert schon das Anlegen des Ordners (hier belegt eine Datei den Namen `auto`), muss
    `letzter_fehler` das sofort zeigen. Vorher lag mkdir außerhalb des Fehlerpfads, und unter
    macOS/Linux warf zusätzlich das Aufräumen (`NotADirectoryError`) und verdeckte den Fehler."""
    from app import sicherung

    db_pfad = tmp_path / "quelle" / "bewerbung.sqlite"
    _kleine_db(db_pfad)
    (tmp_path / "backups").mkdir()
    (tmp_path / "backups" / "auto").write_text("belegt", encoding="utf-8")

    with pytest.raises(OSError):
        sicherung.anlegen(daten_dir=tmp_path, db_pfad=db_pfad)

    assert sicherung._letzter_fehler is not None
    warnung = sicherung.status(daten_dir=tmp_path)["warnung"]
    assert warnung.startswith("Die letzte Sicherung ist fehlgeschlagen")


def test_einstellungen_laden_verwirft_von_hand_verdorbene_werte_einzeln(tmp_path, capsys):
    from app.sicherung import einstellungen_laden

    (tmp_path / "sicherung.json").write_text(
        '{"aktiv": false, "taeglich": "sieben", "woechentlich": 99, "monatlich": 2}', encoding="utf-8")

    assert einstellungen_laden(daten_dir=tmp_path) == {
        "aktiv": False, "taeglich": 7, "woechentlich": 4, "monatlich": 2}
    assert "ungültiger Wert" in capsys.readouterr().out


def test_rotieren_laeuft_trotz_verdorbener_einstellungsdatei(tmp_path):
    """Ein Text statt einer Zahl in `sicherung.json` hätte `zu_entfernen()` mit einem TypeError
    abbrechen lassen, und damit jedes künftige Ausdünnen."""
    from app import sicherung

    (tmp_path / "sicherung.json").write_text('{"taeglich": "sieben"}', encoding="utf-8")
    ordner = tmp_path / "backups" / "auto"
    ordner.mkdir(parents=True)
    jetzt = datetime(2026, 9, 28, 12, 0, 0)
    eintraege = []
    for tag in range(20):
        t = jetzt - timedelta(days=tag, hours=1)
        name = f"bewerbung_{t:%Y-%m-%d_%H%M%S}.zip"
        (ordner / name).write_bytes(b"x")
        eintraege.append((name, t))

    entfernt = sicherung.rotieren(daten_dir=tmp_path, jetzt=jetzt)

    assert sorted(entfernt) == sorted(sicherung.zu_entfernen(eintraege, jetzt))   # Standardwerte
    assert entfernt
