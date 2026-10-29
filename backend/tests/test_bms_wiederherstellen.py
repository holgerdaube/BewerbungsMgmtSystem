"""Tests fuer scripts/bms_wiederherstellen.py (P2-66, Paket W -- Sicherung zurueckspielen).

Das Werkzeug importiert nichts aus app/pipeline; diese Testdatei laedt es deshalb wie
test_bms_update.py per `spec_from_file_location` und baut ihre Installationen und Sicherungen
ausschliesslich unter `tmp_path`. Die echte Installation (data/, outputs/, config/) und
sein Server (Port 8000) werden NIE beruehrt: der Server-Check ist durch einen Stub ersetzt,
`BMS_DATA_DIR` ist entfernt, die Installation ist immer ein Ordner unter tmp_path.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

_PROJEKT_ROOT = Path(__file__).resolve().parent.parent.parent
_SKRIPT_ORDNER = _PROJEKT_ROOT / "scripts"
_SKRIPT_PFAD = _SKRIPT_ORDNER / "bms_wiederherstellen.py"

if str(_SKRIPT_ORDNER) not in sys.path:
    sys.path.insert(0, str(_SKRIPT_ORDNER))


def _lade():
    spec = importlib.util.spec_from_file_location("bms_wiederherstellen_unter_test", _SKRIPT_PFAD)
    modul = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modul
    spec.loader.exec_module(modul)
    return modul


wh = _lade()
bms_update = wh.bms_update   # dieselbe Modulinstanz, die das Werkzeug benutzt


@pytest.fixture(autouse=True)
def _grundannahmen(monkeypatch):
    monkeypatch.delenv("BMS_DATA_DIR", raising=False)
    monkeypatch.setattr(bms_update, "_server_laeuft", lambda port=None: False)
    # Der echte Selbsttest startet einen Subprozess -- nur ein Test unten nimmt ihn mit.
    monkeypatch.setattr(bms_update, "_selbsttest_ausfuehren", lambda installation, data_dir: None)


# ── Bauhilfen ───────────────────────────────────────────────────────────────────────────────
def _db_bauen(pfad: Path, inhalt: str, *, mit_job: bool = True) -> Path:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(pfad))
    try:
        conn.execute("CREATE TABLE job (id INTEGER PRIMARY KEY, titel TEXT)" if mit_job
                     else "CREATE TABLE fremd (id INTEGER PRIMARY KEY, titel TEXT)")
        conn.execute(f"INSERT INTO {'job' if mit_job else 'fremd'} (titel) VALUES (?)", (inhalt,))
        conn.commit()
    finally:
        conn.close()
    return pfad


def _inhalt(pfad: Path) -> list[str]:
    conn = sqlite3.connect(str(pfad))
    try:
        return [r[0] for r in conn.execute("SELECT titel FROM job ORDER BY id")]
    finally:
        conn.close()


def _zip_aus_db(db: Path, ziel: Path, arcname: str = "bewerbung.sqlite") -> Path:
    ziel.parent.mkdir(parents=True, exist_ok=True)
    # writestr mit ZipInfo statt write(): write() normalisiert den Namen je Betriebssystem
    # (unter Windows wird aus "a\\..\\x" oder "C:/x" schlicht "x") -- Zip-Slip-Namen muessen
    # aber roh im Archiv landen (CI Windows, P2-66).
    with zipfile.ZipFile(ziel, "w") as zf:
        zf.writestr(zipfile.ZipInfo(arcname), db.read_bytes())
    return ziel


def _installation(tmp_path: Path) -> tuple[Path, Path]:
    inst = tmp_path / "bms"
    (inst / "data").mkdir(parents=True)
    return inst, inst / "data"


def _hashes(ordner: Path) -> dict[str, str]:
    return {str(p.relative_to(ordner)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(ordner.rglob("*")) if p.is_file()}


def _standard_aufbau(tmp_path: Path):
    """Live-DB 'neu', automatische ZIP 'alt-auto', manuelle Sicherung 'alt-manuell'."""
    inst, data = _installation(tmp_path)
    _db_bauen(data / "bewerbung.sqlite", "live-neu")
    roh = _db_bauen(tmp_path / "roh_auto.sqlite", "alt-auto")
    zip_auto = _zip_aus_db(roh, data / "backups" / "auto" / "bewerbung_2026-09-01_020000.zip")
    manuell = _db_bauen(data / "backups" / "bewerbung_backup_20260920_101500.sqlite", "alt-manuell")
    return inst, data, zip_auto, manuell


def _lauf(inst: Path, *args: str) -> int:
    return wh.main(["--installation", str(inst), *args])


# ── 1. Liste ────────────────────────────────────────────────────────────────────────────────
def test_liste_reihenfolge_arten_und_aendert_nichts(tmp_path, capsys):
    inst, data, zip_auto, manuell = _standard_aufbau(tmp_path)
    vorher_sicherung = _db_bauen(data / "backups" / "bewerbung_backup_20261001_080000_vor_wiederherstellung.sqlite", "x")
    # Dinge, die NICHT in die Liste gehoeren
    (data / "backups" / ".versteckt.sqlite").write_bytes(b"x")
    (data / "backups" / "bewerbung_backup_20261002_000000.sqlite.tmp").write_bytes(b"x")
    (data / "backups" / "unterordner").mkdir()
    _db_bauen(data / "backups" / "unterordner" / "tief.sqlite", "tief")
    (data / "updates" / "2026-09-01_1.0.0_zu_1.1.0").mkdir(parents=True)
    _db_bauen(data / "updates" / "2026-09-01_1.0.0_zu_1.1.0" / "datenbank.sqlite", "upd")
    (data / "backups" / "auto" / "fremd.zip").write_bytes(b"x")

    hashes_vorher = _hashes(inst)
    code = _lauf(inst, "--liste")
    ausgabe = capsys.readouterr().out

    assert code == 0
    assert _hashes(inst) == hashes_vorher          # nichts geaendert, auch keine Sperre/Ordner
    reihenfolge = [zeile for zeile in ausgabe.splitlines() if zeile.strip()[:1].isdigit()]
    assert len(reihenfolge) == 3
    assert "01.10.2026 08:00" in reihenfolge[0] and "vor Wiederherstellung" in reihenfolge[0]
    assert "20.09.2026 10:15" in reihenfolge[1] and "manuelle Sicherung" in reihenfolge[1]
    assert "01.09.2026 02:00" in reihenfolge[2] and "automatische Sicherung" in reihenfolge[2]
    assert "MB" in reihenfolge[0]
    for verboten in ("tief", "versteckt", "datenbank.sqlite", "fremd.zip", ".tmp"):
        assert verboten not in ausgabe
    assert vorher_sicherung.exists()


# ── 2. Rundweg / 3. Ruecknahme ──────────────────────────────────────────────────────────────
def test_rundweg_und_ruecknahme(tmp_path, capsys):
    inst, data, zip_auto, _ = _standard_aufbau(tmp_path)

    code = _lauf(inst, "--datei", zip_auto.name, "--ja")
    ausgabe = capsys.readouterr().out
    assert code == 0, ausgabe
    assert _inhalt(data / "bewerbung.sqlite") == ["alt-auto"]
    vorher = list((data / "backups").glob("*_vor_wiederherstellung.sqlite"))
    assert len(vorher) == 1
    assert vorher[0].name.startswith("bewerbung_backup_")
    assert _inhalt(vorher[0]) == ["live-neu"]
    protokolle = list((data / "backups").glob("wiederherstellung_*.json"))
    assert len(protokolle) == 1
    protokoll = json.loads(protokolle[0].read_text(encoding="utf-8"))
    assert protokoll["quelle"] == zip_auto.name
    assert protokoll["quelle_zeitpunkt"].startswith("2026-09-01T02:00")
    assert protokoll["sicherung_vorher"] == vorher[0].name
    assert protokoll["ergebnis"] == "ok"
    assert "zeitpunkt" in protokoll
    assert "Fertig. Die Datenbank steht jetzt auf dem Stand vom 01.09.2026 02:00" in ausgabe
    assert not (data / "updates" / ".update.lock").exists()   # Sperre frei
    assert not (data / ".bewerbung.sqlite.wiederherstellung.tmp").exists()

    # Ruecknahme: dasselbe Werkzeug, Eintrag "vor Wiederherstellung" waehlen
    code = _lauf(inst, "--datei", vorher[0].name, "--ja")
    assert code == 0
    assert _inhalt(data / "bewerbung.sqlite") == ["live-neu"]


def test_interaktive_auswahl_per_nummer(tmp_path, monkeypatch):
    inst, data, _, _ = _standard_aufbau(tmp_path)
    antworten = iter(["x", "2", "j"])        # ungueltig, dann Nr. 2 (= aeltere), dann Ja
    monkeypatch.setattr("builtins.input", lambda: next(antworten))
    assert _lauf(inst) == 0
    assert _inhalt(data / "bewerbung.sqlite") == ["alt-auto"]


def test_zweimal_ungueltige_auswahl_bricht_ab(tmp_path, monkeypatch):
    inst, data, _, _ = _standard_aufbau(tmp_path)
    hashes = _hashes(inst)
    antworten = iter(["x", "99"])
    monkeypatch.setattr("builtins.input", lambda: next(antworten))
    assert _lauf(inst) == 1
    assert _hashes(inst) == hashes
    assert _inhalt(data / "bewerbung.sqlite") == ["live-neu"]


# ── 4./5. Server und Sperre ─────────────────────────────────────────────────────────────────
def test_server_laeuft_bricht_ab(tmp_path, monkeypatch, capsys):
    inst, data, zip_auto, _ = _standard_aufbau(tmp_path)
    monkeypatch.setattr(bms_update, "_server_laeuft", lambda port=None: True)
    hashes = _hashes(inst)
    assert _lauf(inst, "--datei", zip_auto.name, "--ja") == 1
    assert _hashes(inst) == hashes
    assert "Das BMS läuft noch" in capsys.readouterr().out


def test_sperre_belegt_bricht_ab(tmp_path, capsys):
    inst, data, zip_auto, _ = _standard_aufbau(tmp_path)
    (data / "updates").mkdir()
    sperre = data / "updates" / ".update.lock"
    sperre.write_bytes(b"")
    hashes = _hashes(inst)
    assert _lauf(inst, "--datei", zip_auto.name, "--ja") == 1
    assert _hashes(inst) == hashes
    assert sperre.exists()        # fremde Sperre bleibt unangetastet
    assert "Update" in capsys.readouterr().out


# ── 6. Unbrauchbare Kandidaten ──────────────────────────────────────────────────────────────
def _kandidat_pruefen_lauf(tmp_path, bauen):
    inst, data = _installation(tmp_path)
    _db_bauen(data / "bewerbung.sqlite", "live-neu")
    name = bauen(data)
    hashes = _hashes(inst)
    code = _lauf(inst, "--datei", name, "--ja")
    assert _hashes(inst) == hashes
    return code


def test_kaputte_zip_wird_abgelehnt(tmp_path):
    def bauen(data):
        (data / "backups").mkdir()
        (data / "backups" / "kaputt.zip").write_bytes(b"das ist kein zip")
        return "kaputt.zip"
    assert _kandidat_pruefen_lauf(tmp_path, bauen) == 1


def test_zip_mit_zwei_eintraegen_wird_abgelehnt(tmp_path):
    def bauen(data):
        roh = _db_bauen(data.parent / "r.sqlite", "a")
        ziel = data / "backups" / "zwei.zip"
        ziel.parent.mkdir()
        with zipfile.ZipFile(ziel, "w") as zf:
            zf.write(roh, arcname="bewerbung.sqlite")
            zf.writestr("noch_eine.txt", "x")
        return "zwei.zip"
    assert _kandidat_pruefen_lauf(tmp_path, bauen) == 1


def test_zip_mit_falschem_eintragsnamen_wird_abgelehnt(tmp_path):
    def bauen(data):
        roh = _db_bauen(data.parent / "r.sqlite", "a")
        _zip_aus_db(roh, data / "backups" / "falsch.zip", arcname="andere.sqlite")
        return "falsch.zip"
    assert _kandidat_pruefen_lauf(tmp_path, bauen) == 1


def test_fremde_sqlite_ohne_job_tabelle_wird_abgelehnt(tmp_path, capsys):
    def bauen(data):
        _db_bauen(data / "backups" / "fremd.sqlite", "x", mit_job=False)
        return "fremd.sqlite"
    assert _kandidat_pruefen_lauf(tmp_path, bauen) == 1
    assert "keine BMS-Sicherung" in capsys.readouterr().out


def test_datei_ohne_sqlite_kopf_wird_abgelehnt(tmp_path):
    def bauen(data):
        (data / "backups").mkdir()
        (data / "backups" / "text.sqlite").write_bytes(b"Hallo, ich bin keine Datenbank" * 10)
        return "text.sqlite"
    assert _kandidat_pruefen_lauf(tmp_path, bauen) == 1


def test_integrity_check_nicht_ok_wird_abgelehnt(tmp_path, monkeypatch, capsys):
    inst, data, zip_auto, _ = _standard_aufbau(tmp_path)
    echte_connect = sqlite3.connect

    class _Conn:
        def __init__(self, conn):
            self._c = conn

        def execute(self, sql, *a):
            if "integrity_check" in sql:
                return iter([("*** in database main ***",)])
            return self._c.execute(sql, *a)

        def __getattr__(self, name):
            return getattr(self._c, name)

    monkeypatch.setattr(wh.sqlite3, "connect",
                        lambda *a, **k: _Conn(echte_connect(*a, **k)))
    hashes = _hashes(inst)
    assert _lauf(inst, "--datei", zip_auto.name, "--ja") == 1
    assert _hashes(inst) == hashes
    assert "beschädigt" in capsys.readouterr().out


def test_fehlschlag_des_selbsttests_bricht_ohne_aenderung_ab(tmp_path, monkeypatch, capsys):
    inst, data, zip_auto, _ = _standard_aufbau(tmp_path)

    def _faellt(installation, data_dir):
        raise bms_update.Fehlgeschlagen("Selbsttest fehlgeschlagen: no such column")
    monkeypatch.setattr(bms_update, "_selbsttest_ausfuehren", _faellt)
    hashes = _hashes(inst)
    assert _lauf(inst, "--datei", zip_auto.name, "--ja") == 1
    assert _hashes(inst) == hashes
    assert "nicht öffnen" in capsys.readouterr().out


def test_selbsttest_bekommt_temp_ordner_mit_der_kandidaten_db(tmp_path, monkeypatch):
    inst, data, zip_auto, _ = _standard_aufbau(tmp_path)
    gesehen = {}

    def _spion(installation, data_dir):
        gesehen["inst"] = installation
        gesehen["data"] = Path(data_dir)
        gesehen["inhalt"] = _inhalt(Path(data_dir) / "bewerbung.sqlite")
    monkeypatch.setattr(bms_update, "_selbsttest_ausfuehren", _spion)
    assert _lauf(inst, "--datei", zip_auto.name, "--ja") == 0
    assert gesehen["inhalt"] == ["alt-auto"]
    assert gesehen["data"] != data
    assert gesehen["inst"] == inst


# ── 7. Nein bei der Rueckfrage ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("antwort", ["n", ""])
def test_nein_bei_rueckfrage_aendert_nichts(tmp_path, monkeypatch, antwort):
    inst, data, zip_auto, _ = _standard_aufbau(tmp_path)
    monkeypatch.setattr("builtins.input", lambda: antwort)
    hashes = _hashes(inst)
    assert _lauf(inst, "--datei", zip_auto.name) == 1
    assert _hashes(inst) == hashes


def test_eof_bei_rueckfrage_aendert_nichts(tmp_path, monkeypatch):
    inst, data, zip_auto, _ = _standard_aufbau(tmp_path)

    def _eof():
        raise EOFError
    monkeypatch.setattr("builtins.input", _eof)
    hashes = _hashes(inst)
    assert _lauf(inst, "--datei", zip_auto.name) == 1
    assert _hashes(inst) == hashes


def test_rueckfrage_nennt_die_wichtigen_hinweise(tmp_path, capsys):
    inst, data, zip_auto, _ = _standard_aufbau(tmp_path)
    assert _lauf(inst, "--datei", zip_auto.name, "--ja") == 0
    ausgabe = capsys.readouterr().out
    assert "nicht mehr in der Datenbank" in ausgabe
    assert "Dokumente in outputs und data bleiben unverändert" in ausgabe
    assert "P2" not in ausgabe


# ── 8. Fehler beim Einsetzen ────────────────────────────────────────────────────────────────
def test_fehler_bei_os_replace_gibt_exit_2_und_live_db_bleibt(tmp_path, monkeypatch, capsys):
    inst, data, zip_auto, _ = _standard_aufbau(tmp_path)
    echtes_replace = os.replace

    def _replace(src, dst, *a, **k):
        if Path(dst).name == "bewerbung.sqlite":
            raise OSError("Platte voll (Test)")
        return echtes_replace(src, dst, *a, **k)
    monkeypatch.setattr(os, "replace", _replace)

    assert _lauf(inst, "--datei", zip_auto.name, "--ja") == 2
    assert _inhalt(data / "bewerbung.sqlite") == ["live-neu"]
    assert not (data / ".bewerbung.sqlite.wiederherstellung.tmp").exists()
    assert not (data / "updates" / ".update.lock").exists()
    assert "ursprüngliche Stand" in capsys.readouterr().out
    # die Sicherung des Ausgangsstands liegt trotzdem da, das Protokoll nennt den Fehlschlag
    protokoll = json.loads(next((data / "backups").glob("wiederherstellung_*.json")).read_text("utf-8"))
    assert protokoll["ergebnis"] == "fehlgeschlagen"


def test_fehlgeschlagene_pruefung_nach_dem_ersetzen_stellt_den_alten_stand_her(tmp_path, monkeypatch):
    """Ist die Live-Datei schon ersetzt und die Nachpruefung scheitert, kommt die Sicherung
    aus Schritt 7 zurueck (Exit 2)."""
    inst, data, zip_auto, _ = _standard_aufbau(tmp_path)
    echte_pruefung = wh._db_pruefen
    aufrufe = {"n": 0}

    def _pruefung(db):
        aufrufe["n"] += 1
        if Path(db) == data / "bewerbung.sqlite":
            raise wh.Abbruch("Nachpruefung faellt durch (Test)")
        return echte_pruefung(db)
    monkeypatch.setattr(wh, "_db_pruefen", _pruefung)
    assert _lauf(inst, "--datei", zip_auto.name, "--ja") == 2
    assert _inhalt(data / "bewerbung.sqlite") == ["live-neu"]


# ── 9. Zip-Slip ─────────────────────────────────────────────────────────────────────────────
# (zipfile.write() normalisiert fuehrende "/" und "a/../" selbst weg, beides taugt nicht als Testfall.)
@pytest.mark.parametrize("name", ["../bewerbung.sqlite",
                                  "a\\..\\bewerbung.sqlite", "C:/bewerbung.sqlite"])
def test_zip_slip_namen_werden_abgelehnt(tmp_path, name, capsys):
    inst, data = _installation(tmp_path)
    _db_bauen(data / "bewerbung.sqlite", "live-neu")
    roh = _db_bauen(tmp_path / "r.sqlite", "boese")
    # In backups/auto zaehlt nur der Dateiname -- dort muss die Zip-Slip-Pruefung greifen
    # (ZIPs direkt in backups/ filtert schon die Liste, Abnahme P2-66).
    slip = "bewerbung_2026-09-01_020000.zip"
    (data / "backups" / "auto").mkdir(parents=True, exist_ok=True)
    _zip_aus_db(roh, data / "backups" / "auto" / slip, arcname=name)
    hashes = _hashes(inst)
    assert _lauf(inst, "--datei", slip, "--ja") == 1
    assert _hashes(inst) == hashes
    # Die Zip-Slip-Pruefung selbst muss ablehnen (nicht erst die Namensregel danach).
    assert "unzulässiger Pfad" in capsys.readouterr().out
    assert not (tmp_path / "bewerbung.sqlite").exists()


# ── 10. -wal/-shm ───────────────────────────────────────────────────────────────────────────
def test_wal_und_shm_werden_umbenannt_nicht_geloescht(tmp_path):
    inst, data, zip_auto, _ = _standard_aufbau(tmp_path)
    (data / "bewerbung.sqlite-wal").write_bytes(b"wal-inhalt")
    (data / "bewerbung.sqlite-shm").write_bytes(b"shm-inhalt")
    assert _lauf(inst, "--datei", zip_auto.name, "--ja") == 0
    assert not (data / "bewerbung.sqlite-wal").exists()
    assert not (data / "bewerbung.sqlite-shm").exists()
    wal = list(data.glob("bewerbung.sqlite-wal.vor_wiederherstellung_*"))
    shm = list(data.glob("bewerbung.sqlite-shm.vor_wiederherstellung_*"))
    assert len(wal) == 1 and wal[0].read_bytes() == b"wal-inhalt"
    # (-shm: SQLite ueberschreibt den Index beim Lesen der Live-DB fuer die Vorab-Sicherung, der
    # Inhalt zaehlt hier nicht -- entscheidend ist, dass die Datei beiseite gelegt wurde.)
    assert len(shm) == 1
    assert _inhalt(data / "bewerbung.sqlite") == ["alt-auto"]


# ── 11. Keine Kandidaten / sonstige Randfaelle ──────────────────────────────────────────────
def test_keine_kandidaten_gibt_exit_1(tmp_path, capsys):
    inst, data = _installation(tmp_path)
    _db_bauen(data / "bewerbung.sqlite", "live")
    hashes = _hashes(inst)
    assert _lauf(inst, "--liste") == 1
    assert _lauf(inst, "--ja") == 1
    assert _hashes(inst) == hashes
    assert "keine Sicherungen" in capsys.readouterr().out


def test_unbekannte_datei_gibt_exit_1(tmp_path):
    inst, data, _, _ = _standard_aufbau(tmp_path)
    assert _lauf(inst, "--datei", "gibt_es_nicht.zip", "--ja") == 1


def test_falscher_aufruf_gibt_exit_3(capsys):
    assert wh.main([]) == 3
    assert wh.main(["--installation", "x", "--gibtesnicht"]) == 3


def test_ohne_aktuelle_db_entfaellt_die_vorab_sicherung(tmp_path, capsys):
    inst, data, zip_auto, _ = _standard_aufbau(tmp_path)
    (data / "bewerbung.sqlite").unlink()
    assert _lauf(inst, "--datei", zip_auto.name, "--ja") == 0
    assert _inhalt(data / "bewerbung.sqlite") == ["alt-auto"]
    assert list((data / "backups").glob("*_vor_wiederherstellung*")) == []
    assert "entfällt" in capsys.readouterr().out


def test_namenskollision_der_vorab_sicherung_bekommt_zaehler(tmp_path, monkeypatch):
    inst, data, zip_auto, _ = _standard_aufbau(tmp_path)

    class _FesteZeit(wh.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 5, 12, 0, 0)
    monkeypatch.setattr(wh, "datetime", _FesteZeit)
    assert _lauf(inst, "--datei", zip_auto.name, "--ja") == 0
    # zweiter Lauf in derselben Sekunde: Datei existiert schon
    assert _lauf(inst, "--datei", "bewerbung_backup_20261005_120000_vor_wiederherstellung.sqlite",
                 "--ja") == 0
    namen = sorted(p.name for p in (data / "backups").glob("*_vor_wiederherstellung*.sqlite"))
    assert namen == ["bewerbung_backup_20261005_120000_vor_wiederherstellung.sqlite",
                     "bewerbung_backup_20261005_120000_vor_wiederherstellung_2.sqlite"]


def test_manuelle_sqlite_wird_direkt_eingespielt(tmp_path):
    inst, data, _, manuell = _standard_aufbau(tmp_path)
    assert _lauf(inst, "--datei", manuell.name, "--ja") == 0
    assert _inhalt(data / "bewerbung.sqlite") == ["alt-manuell"]


# ── 12. Git-Installation ────────────────────────────────────────────────────────────────────
def test_git_installation_wird_nicht_abgelehnt(tmp_path):
    inst, data, zip_auto, _ = _standard_aufbau(tmp_path)
    (inst / ".git").mkdir()
    assert _lauf(inst, "--datei", zip_auto.name, "--ja") == 0
    assert _inhalt(data / "bewerbung.sqlite") == ["alt-auto"]


def test_bms_data_dir_wird_beruecksichtigt(tmp_path, monkeypatch):
    inst, _, _, _ = _standard_aufbau(tmp_path)
    anders = tmp_path / "anderes_data"
    _db_bauen(anders / "bewerbung.sqlite", "live-anders")
    _db_bauen(anders / "backups" / "bewerbung_backup_20260101_000000.sqlite", "alt-anders")
    monkeypatch.setenv("BMS_DATA_DIR", str(anders))
    assert _lauf(inst, "--datei", "bewerbung_backup_20260101_000000.sqlite", "--ja") == 0
    assert _inhalt(anders / "bewerbung.sqlite") == ["alt-anders"]


# ── Echter Selbsttest ───────────────────────────────────────────────────────────────────────
def test_echter_selbsttest_mit_init_db_mini_db(tmp_path, monkeypatch):
    """Der echte Selbsttest (Subprozess, `app.main` importieren + `init_db` auf einer Kopie)
    gegen eine mit dem Programmcode gebaute DB. Die Installation ist ein Wegwerfordner unter
    tmp_path, dessen `backend` auf den Programmcode zeigt -- Daten liegen nur unter tmp_path
    (der Selbsttest selbst setzt BMS_DATA_DIR/LOG/SECRETS auf eigene Temp-Ordner)."""
    backend = _PROJEKT_ROOT / "backend"
    inst, data = _installation(tmp_path)
    try:
        (inst / "backend").symlink_to(backend, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks nicht verfuegbar (Windows ohne Rechte)")
    monkeypatch.undo()  # autouse-Stubs zurueck
    monkeypatch.delenv("BMS_DATA_DIR", raising=False)
    monkeypatch.setattr(bms_update, "_server_laeuft", lambda port=None: False)

    # Mini-DB mit dem echten Schema aus init_db: in einem Subprozess gebaut, damit dieser
    # Testprozess app.db nicht mit einer fremden BMS_DATA_DIR importiert.
    import subprocess
    skript = ("from app.db import init_db; init_db()")
    daten_neu = tmp_path / "gen"
    daten_neu.mkdir()
    umgebung = dict(os.environ, BMS_DATA_DIR=str(daten_neu), BMS_LOG_DIR=str(tmp_path / "log"),
                    BMS_SECRETS_DIR=str(tmp_path / "sec"))
    (tmp_path / "log").mkdir()
    (tmp_path / "sec").mkdir()
    erg = subprocess.run([sys.executable, "-c", skript], cwd=str(backend), env=umgebung,
                         capture_output=True, text=True, timeout=120)
    assert erg.returncode == 0, erg.stderr
    mini = daten_neu / "bewerbung.sqlite"
    assert mini.is_file()
    _zip_aus_db(mini, data / "backups" / "auto" / "bewerbung_2026-09-01_020000.zip")
    _db_bauen(data / "bewerbung.sqlite", "live-neu")

    assert _lauf(inst, "--datei", "bewerbung_2026-09-01_020000.zip", "--ja") == 0
    conn = sqlite3.connect(str(data / "bewerbung.sqlite"))
    try:
        assert conn.execute("SELECT count(*) FROM job").fetchone()[0] == 0   # Stand der Sicherung
    finally:
        conn.close()


def test_ordner_zip_in_backups_erscheint_nicht_in_der_liste(tmp_path, capsys):
    """P2-66 Abnahme: ZIPs anderer Werkzeuge (Ordner-Sicherung) gehören nicht in die Liste,
    ZIPs mit genau der Datenbank schon."""
    inst, data, _, _ = _standard_aufbau(tmp_path)
    ordner_zip = data / "backups" / "vor_umbenennung_20261001_120000.zip"
    with zipfile.ZipFile(ordner_zip, "w") as zf:
        zf.writestr("outputs/cv/lebenslauf.docx", b"x")
    db_zip = _zip_aus_db(_db_bauen(tmp_path / "x" / "bewerbung.sqlite", "alt-zip"),
                         data / "backups" / "bewerbung_handzip.zip")
    assert _lauf(inst, "--liste") == 0
    ausgabe = capsys.readouterr().out
    assert ordner_zip.name not in ausgabe
    assert db_zip.name in ausgabe


def test_protokoll_wird_bei_gleicher_sekunde_nicht_ueberschrieben(tmp_path):
    """P2-66 Abnahme: Einspielen und sofortiges Zurücknehmen fallen oft in dieselbe Sekunde."""
    inst, data, zip_auto, _ = _standard_aufbau(tmp_path)
    (data / "backups" / "wiederherstellung_20260101_000000.json").write_text("{}", encoding="utf-8")
    mod = wh
    jetzt = mod.datetime(2026, 1, 1, 0, 0, 0)
    k = mod._kandidaten_sammeln(data)[0]
    mod._protokoll_schreiben(data, jetzt, k, None, "ok")
    assert (data / "backups" / "wiederherstellung_20260101_000000.json").read_text(encoding="utf-8") == "{}"
    assert json.loads((data / "backups" / "wiederherstellung_20260101_000000_2.json")
                      .read_text(encoding="utf-8"))["ergebnis"] == "ok"
