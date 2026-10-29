"""T1-Regressionsschutz für `pipeline/posting_snapshot.py` (Phase 79, Spec-Befund 3 —
08.08.2026 LIVE reproduziert, s. tasks/spec_phase79_snapshot_render_full.md).

Vorher zog `posting_snapshot._SNAPSHOT_DIR` HART über `PROJECT_ROOT`, OHNE den Test-Override
`BMS_DATA_DIR` (anders als `app.db.DATA_DIR`) — jeder Test, der über `ingest`/`render_basis`
lief, schrieb in das ECHTE `data/job_postings/`. Live-Beleg: ein einzelner Lauf von
`tests/test_ingest_repost_selber_lauf.py` erzeugte 4 neue Dateien (540 → 544, sofort wieder
entfernt); Bestand: 265 von 540 Dateien waren Testartefakte (`…Repost_Test_AG…`,
`…repost_slug…`). Fix: `_SNAPSHOT_DIR` zieht jetzt auf `app.db.DATA_DIR`.

Zwei Fälle (Bau-Auftrag Stufe D.7/D.8):
  7. `_SNAPSHOT_DIR` liegt STRUKTURELL unter `DATA_DIR` (`Path.is_relative_to`, kein
     String-Match — Muster `tests/test_secrets_pfade.py`).
  8. Ein `render_basis()`-Aufruf im Test legt NICHTS unterhalb des ECHTEN Projekt-`data/`-
     Ordners an (`posting_snapshot.PROJECT_ROOT / "data" / "job_postings"` — genau der Ort, an
     dem der Bug vor Phase 79 zuschlug).

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention) — alle Importe funktions-
lokal in den Testfunktionen. Es werden NIRGENDS echte Dateien im echten `data/` angelegt: die
tmp-DB-Isolation aus conftest.py (`BMS_DATA_DIR`) bindet `_SNAPSHOT_DIR` bereits vor jedem
Test an ein tmp-Verzeichnis — Fall 8 beweist genau das, ohne selbst einen Monkeypatch zu setzen.
"""
from pathlib import Path


# ── Fall 7: strukturell unter DATA_DIR ──────────────────────────────────────────────────────
def test_snapshot_dir_liegt_unter_data_dir():
    """`_SNAPSHOT_DIR` muss unter `app.db.DATA_DIR` liegen, NICHT unter irgendeinem
    Alt-Pfad-Baustein wie `PROJECT_ROOT`. `Path.is_relative_to` statt String-Vergleich: ein
    Teilstring-Treffer wäre durch einen zufälligen Ordnernamen täuschbar (s. Docstring von
    `test_secrets_pfade.py`)."""
    from app.db import DATA_DIR
    from pipeline import posting_snapshot

    assert posting_snapshot._SNAPSHOT_DIR.is_relative_to(DATA_DIR), (
        f"_SNAPSHOT_DIR ({posting_snapshot._SNAPSHOT_DIR}) liegt NICHT unter DATA_DIR "
        f"({DATA_DIR}) — die T1-Test-Isolation (BMS_DATA_DIR) würde umgangen (Spec-Befund 3)."
    )
    # Die konkrete Erwartung aus der Spec (Entscheidung 6): direktes Kind "job_postings".
    assert posting_snapshot._SNAPSHOT_DIR == DATA_DIR / "job_postings"


# ── Fall 8: render_basis() schreibt NICHTS unter das echte Projekt-data/ ───────────────────
def test_render_basis_schreibt_nichts_unter_echtes_projekt_data(session):
    """Kein `_SNAPSHOT_DIR`-Monkeypatch (bewusst — das ist der Normalfall der meisten
    bestehenden Tests, z. B. `test_ingest_*.py`, die `render_basis()` indirekt über den Ingest
    auslösen): der reine tmp-DB-Isolationsmechanismus aus `conftest.py` MUSS bereits ausreichen,
    damit die Datei NICHT im echten `data/job_postings/` landet. Genau das war vor Phase 79
    NICHT der Fall (Spec-Befund 3, Live-Beleg 540 → 544 Dateien)."""
    import uuid
    from datetime import date

    from app.models import Job
    from pipeline import posting_snapshot

    echter_ordner = posting_snapshot.PROJECT_ROOT / "data" / "job_postings"
    vorher = set(echter_ordner.glob("*")) if echter_ordner.is_dir() else set()

    suffix = uuid.uuid4().hex[:8]
    job = Job(company_name=f"T1Test GmbH {suffix}", title="T1-Testrolle",
              status=f"T1Test-{suffix}", found_date=date.today().isoformat(),
              dedup_key=f"t1test|{suffix}", url=f"https://example.invalid/t1/{suffix}")
    session.add(job)
    session.commit()
    session.refresh(job)

    rel = posting_snapshot.render_basis(job, text="Testinhalt für den T1-Beleg (pytest).")
    session.add(job)
    session.commit()

    nachher = set(echter_ordner.glob("*")) if echter_ordner.is_dir() else set()
    assert nachher == vorher, (
        "render_basis() hat Dateien im ECHTEN Projekt-data/job_postings/ angelegt — T1-Verstoß! "
        f"Neue Dateien: {sorted(p.name for p in (nachher - vorher))}"
    )

    # Stattdessen landet die Datei unter der (tmp-isolierten) _SNAPSHOT_DIR — der Fix wirkt
    # tatsächlich, es ist nicht bloß "irgendwo hin geschrieben".
    assert rel is not None
    geschrieben = posting_snapshot._SNAPSHOT_DIR / Path(rel).name
    assert geschrieben.is_file()
    assert geschrieben.is_relative_to(posting_snapshot._SNAPSHOT_DIR)
    assert not geschrieben.is_relative_to(echter_ordner)
