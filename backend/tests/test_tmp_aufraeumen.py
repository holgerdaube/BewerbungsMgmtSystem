"""P2-53: `agent_runner.cleanup_tmp()` räumt Zwischendateien der Läufe nach der Log-Frist auf.

Geschützt bleibt, was die DB referenziert (bis Mitte September registrierte `cv-erstellen`
Entwürfe in `data/tmp/`), und alles Jüngere. Die Tests arbeiten in `tmp_path`; nur der
Verweis-Test nutzt den isolierten Test-`DATA_DIR` aus `conftest.py`, weil `artefakt_pfad`
`data/…`-Pfade genau dorthin auflöst. Die echten Ordner fasst kein Test an: Der Standard-
Ordnerliste (`_tmp_ordner()`) wird nur ihr Inhalt abgefragt, nie aufgeräumt.

Tests, die ein Löschen erwarten, brauchen die Fixture `session`: Ohne angelegte Tabellen findet
`cleanup_tmp` keine Verweisliste und löscht absichtlich nichts (s. eigenen Test dazu).
"""
import os
import time
import uuid
from pathlib import Path

import pytest


def _altern(pfad: Path, tage: int = 40) -> None:
    zeitpunkt = time.time() - tage * 86400
    os.utime(pfad, (zeitpunkt, zeitpunkt))


def test_alte_datei_geht_neue_bleibt(tmp_path, session):
    from app import agent_runner

    alt = tmp_path / "alt.json"
    alt.write_text("x", encoding="utf-8")
    _altern(alt)
    neu = tmp_path / "neu.json"
    neu.write_text("x", encoding="utf-8")

    assert agent_runner.cleanup_tmp(ordner=[tmp_path]) == 1
    assert not alt.exists()
    assert neu.exists()
    assert tmp_path.is_dir()                       # der Ordner selbst bleibt


def test_datei_mit_db_verweis_bleibt_auch_wenn_alt(session, seed):
    from app import agent_runner
    from app.db import DATA_DIR
    from app.models import CVVersion

    ordner = DATA_DIR / "tmp"
    ordner.mkdir(parents=True, exist_ok=True)
    kennung = uuid.uuid4().hex[:8]
    registriert = ordner / f"entwurf_{kennung}.docx"
    registriert.write_bytes(b"x")
    _altern(registriert)
    frei = ordner / f"frei_{kennung}.json"
    frei.write_text("x", encoding="utf-8")
    _altern(frei)
    session.add(CVVersion(job_id=seed["jobs"][0].id, language="DE", kind="tailored",
                          status="entwurf", file_path=f"data/tmp/{registriert.name}"))
    session.commit()

    agent_runner.cleanup_tmp(ordner=[ordner])

    assert registriert.exists()
    assert not frei.exists()


def test_leerer_alter_unterordner_geht_neuer_und_gefuellter_bleiben(tmp_path, session):
    from app import agent_runner

    alt_leer = tmp_path / "alt_leer"
    alt_leer.mkdir()
    _altern(alt_leer)
    neu_leer = tmp_path / "neu_leer"
    neu_leer.mkdir()
    gefuellt = tmp_path / "gefuellt"
    gefuellt.mkdir()
    (gefuellt / "neu.txt").write_text("x", encoding="utf-8")
    _altern(gefuellt)

    agent_runner.cleanup_tmp(ordner=[tmp_path])

    assert not alt_leer.exists()
    assert neu_leer.exists()
    assert (gefuellt / "neu.txt").exists()


def test_frist_null_loescht_nichts(tmp_path, monkeypatch):
    from app import agent_runner

    monkeypatch.setattr(agent_runner, "LOG_RETENTION_DAYS", 0)
    alt = tmp_path / "alt.json"
    alt.write_text("x", encoding="utf-8")
    _altern(alt, tage=400)

    assert agent_runner.cleanup_tmp(ordner=[tmp_path]) == 0
    assert alt.exists()


def test_ohne_verweisliste_wird_nichts_geloescht(tmp_path, monkeypatch, capsys):
    """Lässt sich die DB nicht lesen, weiß niemand, was geschützt ist: dann lieber gar nichts."""
    from app import agent_runner
    import pipeline.cleanup as cleanup

    def kaputt(session):
        raise RuntimeError("DB nicht erreichbar")

    monkeypatch.setattr(cleanup, "_alle_referenzen", kaputt)
    alt = tmp_path / "alt.json"
    alt.write_text("x", encoding="utf-8")
    _altern(alt)

    assert agent_runner.cleanup_tmp(ordner=[tmp_path]) == 0
    assert alt.exists()
    assert "WARNUNG" in capsys.readouterr().out


@pytest.mark.skipif(os.name == "nt", reason="Symlinks brauchen unter Windows Sonderrechte")
def test_symlink_wird_nicht_verfolgt(tmp_path, session):
    from app import agent_runner

    ausserhalb = tmp_path / "ausserhalb"
    ausserhalb.mkdir()
    wichtig = ausserhalb / "wichtig.txt"
    wichtig.write_text("x", encoding="utf-8")
    _altern(wichtig)
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    (tmp / "verweis").symlink_to(ausserhalb)

    agent_runner.cleanup_tmp(ordner=[tmp])

    assert wichtig.exists()


def test_gedrosselt_raeumt_logs_und_zwischendateien(monkeypatch):
    from app import agent_runner

    aufrufe = []
    monkeypatch.setattr(agent_runner, "cleanup_logs", lambda: aufrufe.append("logs") or 0)
    monkeypatch.setattr(agent_runner, "cleanup_tmp", lambda: aufrufe.append("tmp") or 0)
    monkeypatch.setattr(agent_runner, "_LETZTE_ROTATION",
                        time.time() - agent_runner._ROTATION_INTERVALL_S - 1)

    agent_runner._cleanup_logs_gedrosselt()

    assert aufrufe == ["logs", "tmp"]


def test_standardordner_umfassen_den_fehlgriff_unter_backend():
    from app import agent_runner

    ordner = agent_runner._tmp_ordner()

    assert agent_runner.DATA_DIR / "tmp" in ordner
    assert agent_runner.PROJECT_ROOT / "backend" / "data" / "tmp" in ordner


def test_runner_warnt_vor_nachwirkendem_cd_backend():
    from app.agent_runner import HEADLESS_SUFFIX

    assert "`cd backend` gilt für ALLE folgenden Befehle" in HEADLESS_SUFFIX
    assert "../data/tmp/" in HEADLESS_SUFFIX
    assert "räumt dort alte Dateien" in HEADLESS_SUFFIX
