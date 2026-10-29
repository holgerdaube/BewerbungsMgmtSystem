"""P2-3 (Phase 67F): ein Duplikat-Insert auf einem der neuen UNIQUE-Indizes muss wie ein
normaler Dubletten-Treffer gezaehlt werden -- NICHT als 500er/ungefangene Exception enden.

Nutzt die geteilte Session-tmp-DB aus conftest.py (`_db_ready`/`session`/`client`) -- diese
Tests manipulieren kein rohes Schema, nur normale Model-Inserts, deshalb KEINE eigene
throwaway-DB noetig (anders als tests/test_db_migration.py).

Zwei Test-Staerken kombiniert:
  1. Deterministische SEQUENZIELLE Tests (kein Timing/Sleep) fuer die Kernmechanik
     (`app.db.flush_or_duplicate`) inkl. Gegenprobe (ohne den Fix wuerde derselbe Konflikt
     ungefangen werfen).
  2. ECHTE Zwei-Thread-Races (per `threading.Barrier` statt `sleep()` synchronisiert, daher
     nicht flaky) gegen die tatsaechlichen Aufrufer (`pipeline.ingest.ingest_records`,
     `POST /api/jobs`, `POST /api/target-companies`) -- das ist die reale Situation, vor der
     P2-3 schuetzen soll (zwei fast gleichzeitig laufende Prozesse/Anfragen).
"""
import threading
import uuid

import pytest


def _mit_synthetischer_leerer_config(monkeypatch, tmp_path):
    """`config/suchprofile.yaml` ist gitignored und fehlt in CI (Phase 57 E2) — `dedup_text.
    konfiguration()` (von `ingest_records()` IMMER aufgerufen, auch ohne Anzeigentext) würde
    dort mit `SystemExit` abbrechen. Patcht `CONFIG_FILE` auf eine synthetische, leere YAML,
    damit die Modul-Defaults greifen — identisches Muster wie test_dedup_text.py/
    test_ingest_repost_selber_lauf.py::_mit_synthetischer_leerer_config."""
    import pipeline.dedup_text as dedup_text

    leere_config = tmp_path / "suchprofile.yaml"
    leere_config.write_text("dedup_text: {}\n", encoding="utf-8")
    monkeypatch.setattr(dedup_text, "CONFIG_FILE", leere_config)


# ── Kernmechanik: app.db.flush_or_duplicate ────────────────────────────────────────────────────
def test_flush_or_duplicate_faengt_kollision_ab_geschwister_bleiben_erhalten(session):
    """Zwei Job-Inserts in DERSELBEN Session, zweiter kollidiert auf dedup_key -- NUR der
    Savepoint des zweiten rollt zurueck, der ERSTE (bereits geflushte) bleibt erhalten. Genau
    diese Eigenschaft laesst einen Ingest-Batch mit mehreren echten Jobs ueberleben, wenn EINER
    davon kollidiert (s. pipeline/ingest.py)."""
    from app.db import flush_or_duplicate
    from app.models import Job

    dk = f"kernmechanik|{uuid.uuid4().hex[:8]}"

    job1 = Job(title="Erster", dedup_key=dk, found_date="2026-01-01")
    assert flush_or_duplicate(session, lambda: session.add(job1)) is True
    erste_id = job1.id
    assert erste_id is not None

    job2 = Job(title="Zweiter (Dublette)", dedup_key=dk, found_date="2026-01-01")
    assert flush_or_duplicate(session, lambda: session.add(job2)) is False   # abgefangen, NICHT geworfen
    session.commit()

    from sqlmodel import select
    treffer = session.exec(select(Job).where(Job.dedup_key == dk)).all()
    assert len(treffer) == 1, f"erwartet genau 1 Zeile nach der abgefangenen Dublette, bekam {len(treffer)}"
    assert treffer[0].id == erste_id
    assert treffer[0].title == "Erster"   # der zweite Versuch hat nichts ueberschrieben


def test_ohne_flush_or_duplicate_wuerde_dieselbe_kollision_ungefangen_werfen(session):
    """Gegenprobe: ein NACKTER `session.add()` + `session.flush()` (das Verhalten VOR P2-3,
    ueberall im Backend so vorgefunden) wirft bei genau demselben Konflikt eine ungefangene
    IntegrityError -- exakt das Verhalten, das einen echten Ingest-Batch mit einem 500er
    abbrechen wuerde. Beweist, dass `flush_or_duplicate` keine Kosmetik ist, sondern eine
    echte Verhaltensaenderung."""
    from sqlalchemy.exc import IntegrityError
    from app.models import Job

    dk = f"gegenprobe|{uuid.uuid4().hex[:8]}"
    session.add(Job(title="Erster", dedup_key=dk, found_date="2026-01-01"))
    session.commit()

    session.add(Job(title="Zweiter", dedup_key=dk, found_date="2026-01-01"))
    with pytest.raises(IntegrityError):
        session.flush()   # das alte, ungeschuetzte Verhalten
    session.rollback()    # Session fuer eventuelle weitere Nutzung wieder gebrauchsfaehig machen


# ── Echte Zwei-Thread-Race gegen pipeline.ingest.ingest_records ────────────────────────────────
def test_ingest_records_zwei_gleichzeitige_laeufe_race_wird_als_dublette_gezaehlt(_db_ready, monkeypatch, tmp_path):
    """Simuliert zwei fast gleichzeitig laufende Ingest-Prozesse (z. B. `jobsuche` +
    `mail-jobsuche` zeitgleich gestartet) mit demselben Treffer. `threading.Barrier` statt
    `sleep()`: beide Threads starten `ingest_records()` GENAU gleichzeitig, kein Timing-Raten,
    daher nicht flaky. Erwartung: genau 1 Job persistiert, die Gesamtsumme ueber beide
    Rueckgabewerte zaehlt genau 1x 'new' und 1x 'dup' -- kein Thread darf crashen."""
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from pipeline.ingest import ingest_records

    eindeutig = uuid.uuid4().hex[:8]
    rec = {
        "company": f"Racefirma {eindeutig} GmbH", "title": "Director Race Testing",
        "location": "Remote",
        "verifikation": {"status": "BESTÄTIGT", "beleg": "Testfixture", "geprueft_am": "2026-07-26"},
    }
    barrier = threading.Barrier(2)
    results, fehler = {}, {}

    def worker(name):
        try:
            barrier.wait(timeout=60)  # P2-19: Notbremse gegen Haengen, keine Laufzeitzusage
            results[name] = ingest_records([rec])
        except BaseException as e:   # noqa: BLE001 -- bewusst BaseException: SystemExit (z. B. aus
            # einer fehlenden config/suchprofile.yaml) erbt NICHT von Exception und würde sonst
            # lautlos im Thread verschwinden (Python druckt es nur nach stderr, `results` bliebe
            # leer OHNE dass `fehler` etwas zeigt) -- genau das ist real passiert (CI, 26.07.2026,
            # s. Baubericht Phase 67F) und machte den Fehlschlag zunächst schwer diagnostizierbar.
            fehler[name] = e

    threads = [threading.Thread(target=worker, args=(n,)) for n in ("A", "B")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=90)  # P2-19: Notbremse gegen Haengen, keine Laufzeitzusage

    assert not fehler, f"mindestens ein Thread ist mit einer ungefangenen Exception gecrasht: {fehler}"
    assert set(results) == {"A", "B"}, f"nicht beide Threads sind rechtzeitig fertig geworden: {results}"

    total_new = results["A"]["new"] + results["B"]["new"]
    total_dup = results["A"]["dup"] + results["B"]["dup"]
    assert total_new == 1, f"erwartet genau 1 neuer Job trotz Race, bekam {total_new} (results={results})"
    assert total_dup == 1, f"erwartet genau 1 als Dublette gezaehlt, bekam {total_dup} (results={results})"

    from sqlmodel import Session, select
    from app.db import engine
    from app.models import Job
    with Session(engine) as s:
        jobs = s.exec(select(Job).where(Job.company_name == rec["company"])).all()
    assert len(jobs) == 1, f"erwartet genau 1 persistierter Job trotz Race, bekam {len(jobs)}"


def test_ingest_records_case_variante_firma_wird_wiederverwendet_nicht_dupliziert(_db_ready, monkeypatch, tmp_path):
    """P2-3-Nebenfix in `_get_or_create_company` (ingest.py): der neue UNIQUE-Index ist
    case-insensitiv (LOWER(TRIM(name))); der Vorab-Check muss das jetzt auch sein, sonst waere
    JEDE case-variante Wiederholung derselben Firma ein Konflikt am Index. Zwei Ingest-Laeufe
    mit anders geschriebenem Firmennamen muessen dieselbe Company-Zeile treffen."""
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from pipeline.ingest import ingest_records

    eindeutig = uuid.uuid4().hex[:8]
    firma = f"Kobalt {eindeutig} Systems AG"
    rec1 = {"company": firma, "title": "Director A", "location": "Remote",
            "verifikation": {"status": "BESTÄTIGT", "beleg": "t", "geprueft_am": "2026-07-26"}}
    rec2 = {"company": firma.upper(), "title": "Director B", "location": "Remote",
            "verifikation": {"status": "BESTÄTIGT", "beleg": "t", "geprueft_am": "2026-07-26"}}

    r1 = ingest_records([rec1])
    r2 = ingest_records([rec2])
    assert r1["new"] == 1 and r2["new"] == 1   # zwei verschiedene JOBS (Titel A vs B), keine Crashes

    from sqlmodel import Session, select
    from app.db import engine
    from app.models import Company
    with Session(engine) as s:
        firmen = [c for c in s.exec(select(Company)).all()
                  if c.name.strip().lower() == firma.strip().lower()]
    assert len(firmen) == 1, f"case-variante Firma haette wiederverwendet werden muessen, gefunden: {firmen}"


# ── Echte Zwei-Thread-Race gegen die HTTP-Schicht (main.py) ────────────────────────────────────
def test_create_job_zwei_gleichzeitige_anfragen_liefert_existing_statt_500(client):
    """POST /api/jobs zweimal mit identischer Firma+Titel, GENAU gleichzeitig (Barrier) --
    darf keine 500 liefern; ein Aufruf gewinnt (existing=False), der andere bekommt entweder
    den bestehenden Job gemeldet (existing=True) oder 409 (beides zulaessig, s. main.py::
    create_job), aber NIE einen 500er."""
    eindeutig = uuid.uuid4().hex[:8]
    payload = {"company_name": f"Doppelklick {eindeutig} AG", "title": "Head of Delivery"}

    barrier = threading.Barrier(2)
    antworten = {}

    def worker(name):
        barrier.wait(timeout=60)  # P2-19: Notbremse gegen Haengen, keine Laufzeitzusage
        antworten[name] = client.post("/api/jobs", json=payload)

    threads = [threading.Thread(target=worker, args=(n,)) for n in ("A", "B")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=90)  # P2-19: Notbremse gegen Haengen, keine Laufzeitzusage

    assert set(antworten) == {"A", "B"}
    for name, resp in antworten.items():
        assert resp.status_code < 500, f"Thread {name}: 500er statt sauberer Dubletten-Behandlung ({resp.text})"
        assert resp.status_code in (200, 409), f"Thread {name}: unerwarteter Status {resp.status_code} ({resp.text})"

    from sqlmodel import Session, select
    from app.db import engine
    from app.models import Job
    with Session(engine) as s:
        jobs = s.exec(select(Job).where(Job.company_name == payload["company_name"])).all()
    assert len(jobs) == 1, f"erwartet genau 1 persistierter Job trotz doppelter Anfrage, bekam {len(jobs)}"


def test_create_target_company_zwei_gleichzeitige_anfragen_liefert_409_statt_500(client):
    """Schwesterstelle (eines der 'vier weiteren Modelle'): POST /api/target-companies zweimal
    GENAU gleichzeitig mit identischer Firma -- genau eine Anfrage darf gewinnen (200), die
    andere bekommt den REGULAEREN 409 ('existiert bereits'), NIE einen 500er."""
    eindeutig = uuid.uuid4().hex[:8]
    payload = {"company": f"Zielfirma Race {eindeutig} GmbH"}

    barrier = threading.Barrier(2)
    antworten = {}

    def worker(name):
        barrier.wait(timeout=60)  # P2-19: Notbremse gegen Haengen, keine Laufzeitzusage
        antworten[name] = client.post("/api/target-companies", json=payload)

    threads = [threading.Thread(target=worker, args=(n,)) for n in ("A", "B")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=90)  # P2-19: Notbremse gegen Haengen, keine Laufzeitzusage

    assert set(antworten) == {"A", "B"}
    codes = sorted(r.status_code for r in antworten.values())
    assert codes == [200, 409], (f"erwartet genau ein 200 + ein 409, bekam {codes} "
                                  f"({[r.text for r in antworten.values()]})")

    from sqlmodel import Session, select
    from app.db import engine
    from app.models import TargetCompany
    with Session(engine) as s:
        treffer = s.exec(select(TargetCompany).where(TargetCompany.company == payload["company"])).all()
    assert len(treffer) == 1, f"erwartet genau 1 persistierte Zielfirma trotz Race, bekam {len(treffer)}"
