"""Regressionstest für P2-8 (Phase 67D): Der Repost-Vergleichspool in `pipeline/ingest.py`
wurde bisher EINMAL vor der Record-Schleife aus dem DB-Bestand gebaut und nie um die IM SELBEN
LAUF neu angelegten Jobs ergänzt — zwei echte Reposts (dieselbe Rolle, umbenannt) im selben
Ingest-Lauf wurden nie miteinander verglichen, kein „DUBLETTE?"-Hinweis (Echtfall-Muster:
Fall A, s. pipeline/dedup_text.py-Moduldocstring). Fix: der neu angelegte Job wird
nach dem Rendern seines Snapshots (erst dann steht `posting_snapshot_path`, das die Poolbildung
oben verlangt) mit demselben Schlüssel (`N.slug_parts(job.company_name)`) in `jobs_je_firma`
aufgenommen — spätere Records desselben Laufs werden dagegen geprüft.

Ohne den Fix bleibt `dubletten_verdacht` in diesem Test bei 0 (empirisch verifiziert durch
Zurücksetzen des Fixes vor dem Schreiben dieses Tests, s. Abschlussbericht Phase 67D).

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention: BMS_DATA_DIR muss VOR dem
ersten Import gesetzt sein, das übernimmt conftest.py selbst)."""
import uuid


def _mit_synthetischer_leerer_config(monkeypatch, tmp_path):
    """`config/suchprofile.yaml` ist gitignored und fehlt in CI (Phase 57 E2) —
    `dedup_text.konfiguration()` (von `ingest_records()` IMMER aufgerufen, auch ohne
    Anzeigentext) würde dort mit `SystemExit` abbrechen. Patcht `CONFIG_FILE` auf eine
    synthetische, leere YAML, damit die Modul-Defaults (0.045/0.45/400/5) greifen — identisches
    Muster wie `test_dedup_text.py::_mit_synthetischer_leerer_config`."""
    import pipeline.dedup_text as dedup_text

    leere_config = tmp_path / "suchprofile.yaml"
    leere_config.write_text("dedup_text: {}\n", encoding="utf-8")
    monkeypatch.setattr(dedup_text, "CONFIG_FILE", leere_config)


def _verifikation(beleg: str) -> dict:
    return {"status": "BESTÄTIGT", "beleg": beleg, "geprueft_am": "2026-07-26"}


# Ein Anzeigentext, wie ihn zwei umbenannte Reposts derselben Rolle real teilen würden (>= 400
# Zeichen, die dedup_text.konfiguration()-Default-Schranke `min_text_zeichen`) — bewusst
# identisch für beide Records: der Titel-Vorfilter (titel_aehnlichkeit) UND der Text-Score
# (aehnlichkeit) müssen beide anschlagen, s. pipeline/dedup_text.py::pruefen().
_ANZEIGENTEXT = (
    "Wir suchen eine erfahrene Führungskraft für den Bereich Customer Success. Sie "
    "verantworten den Aufbau eines internationalen Teams, steuern die Kundenerfolgs-Strategie "
    "und arbeiten eng mit Vertrieb und Produkt zusammen. Erfahrung im Lösungsvertrieb sowie im "
    "Aufbau skalierbarer Prozesse ist erforderlich. Sie berichten direkt an die "
    "Geschäftsführung und verantworten ein Budget von mehreren Millionen Euro jährlich in "
    "einem wachsenden internationalen Markt mit hoher Wettbewerbsdynamik."
)
assert len(_ANZEIGENTEXT) >= 400


def test_repost_im_selben_lauf_wird_als_dublette_verdaechtigt(session, monkeypatch, tmp_path):
    """Zwei Records DERSELBEN Firma, ähnlicher Titel (Repost-Muster „... EMEA"-Erweiterung wie
    im Fall A) + (nahezu) identischem Anzeigentext, IM SELBEN
    `ingest_records()`-Aufruf. Unterschiedliche URL/Titel -> bestehen die mechanische
    Dedup-Prüfung (dedup_key/ct_key/URL) einzeln -> OHNE den Fix vergleicht Record 2 nur gegen
    den (hier leeren) DB-Bestand VOR dem Lauf, nicht gegen den in diesem Lauf gerade angelegten
    Job 1 -> dubletten_verdacht bliebe 0. MIT dem Fix findet Record 2 Job 1 im (jetzt
    mitwachsenden) Pool."""
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from pipeline.ingest import ingest_records

    firma = f"Repost Test AG {uuid.uuid4().hex[:8]}"
    url_a = f"https://example.test/job/{uuid.uuid4().hex[:8]}"
    url_b = f"https://example.test/job/{uuid.uuid4().hex[:8]}"
    rec_a = {"company": firma, "title": "Senior Manager Customer Success", "url": url_a,
             "verifikation": _verifikation("Live gesehen — Portal A")}
    rec_b = {"company": firma, "title": "Senior Manager Customer Success EMEA", "url": url_b,
             "verifikation": _verifikation("Live gesehen — Portal B")}

    result = ingest_records([rec_a, rec_b], texte={url_a: _ANZEIGENTEXT, url_b: _ANZEIGENTEXT})

    # Mechanische Vorbedingung: beide Records müssen die einfache Dedup-Prüfung SEPARAT
    # bestehen (verschiedener dedup_key/ct_key/URL) — sonst wäre dies kein Test für P2-8,
    # sondern nur für den längst bestehenden mechanischen Dedup.
    assert result["new"] == 2, f"beide Records sollten als neu angelegt werden: {result}"
    assert result["dup"] == 0, f"kein mechanischer Dublette-Treffer erwartet: {result}"
    assert result["unverifiziert"] == 0, f"beide Records tragen einen gültigen Beleg: {result}"

    assert result["dubletten_verdacht"] == 1, (
        "P2-8: Record B (SELBER Lauf) hätte Record A als Dubletten-Verdacht erkennen müssen — "
        f"bekam dubletten_verdacht={result['dubletten_verdacht']} (voller Result: {result})"
    )

    from sqlmodel import select
    from app.models import Job, JobLog

    job_a = session.exec(select(Job).where(Job.url == url_a)).one()
    job_b = session.exec(select(Job).where(Job.url == url_b)).one()
    assert "DUBLETTE?" in (job_b.verify_note or ""), job_b.verify_note
    assert f"Job {job_a.id}" in (job_b.verify_note or ""), job_b.verify_note

    logs = session.exec(select(JobLog).where(JobLog.job_id == job_b.id)).all()
    assert any("DUBLETTE?" in (l.eintrag or "") for l in logs), logs


def test_repost_nutzt_slug_parts_als_poolschluessel_nicht_rohen_firmennamen(session, monkeypatch, tmp_path):
    """Regressionsschutz für den im Befund genannten Stolperstein („Sieh dir den Schlüssel des
    Dicts genau an"): der Pool wird über `N.slug_parts(company_name)` geführt, NICHT über den
    rohen Firmennamen. Zwei Schreibweisen derselben Firma (Groß-/Kleinschreibung +
    Leerzeichen-Variante), die nach `slug_parts` auf denselben Schlüssel fallen, müssen den
    Repost trotzdem erkennen — würde stattdessen der rohe Name als Schlüssel verwendet, läge
    der frisch angelegte Job im falschen/einem anderen Fach und Record 2 fände ihn nicht."""
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from pipeline.ingest import ingest_records

    suffix = uuid.uuid4().hex[:8]
    firma_a = f"Repost-Slug {suffix} GmbH"
    firma_b = f"repost slug {suffix} gmbh"   # andere Schreibweise, IDENTISCHER slug_parts-Wert
    url_a = f"https://example.test/job/{uuid.uuid4().hex[:8]}"
    url_b = f"https://example.test/job/{uuid.uuid4().hex[:8]}"
    rec_a = {"company": firma_a, "title": "Director Professional Services", "url": url_a,
             "verifikation": _verifikation("Live gesehen — Portal A")}
    rec_b = {"company": firma_b, "title": "Director Professional Services EMEA", "url": url_b,
             "verifikation": _verifikation("Live gesehen — Portal B")}

    result = ingest_records([rec_a, rec_b], texte={url_a: _ANZEIGENTEXT, url_b: _ANZEIGENTEXT})

    assert result["new"] == 2, result
    assert result["dubletten_verdacht"] == 1, (
        f"Repost haette ueber slug_parts()-Normalisierung gefunden werden muessen: {result}"
    )
