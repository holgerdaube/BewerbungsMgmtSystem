"""Tests für Phase 67B (P2-4 aus dem Code-Review): Login-Wall/Rate-Limit wurden als tote Anzeige
dargestellt.

`posting_snapshot.py::backfill()` warf bisher `tot = pr["befund"] not in ("OK", "INHALT_UNKLAR")`
— das wirft NICHT_PRUEFBAR (HTTP 403/429, Bot-Block/Rate-Limit) und LOGIN_WALL in denselben roten
"nicht mehr abrufbar"-Topf wie TOT/ABGELAUFEN/UMGELEITET_GENERISCH, obwohl die Anzeige dort in
Wahrheit live sein kann — man konnte nur nicht nachschauen. Fix: ein dritter, neutraler
Zustand (amber, "nicht prüfbar") für NICHT_PRUEFBAR/LOGIN_WALL; rot bleibt reserviert für
bestätigt tote Anzeigen (TOT/ABGELAUFEN/UMGELEITET_GENERISCH).

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention). Jeder Job bekommt einen
eindeutigen Status-Wert als `backfill()`-Filter, damit die Tests unabhängig von akkumuliertem
Zustand aus anderen Tests exakte Zählungen prüfen können (s. Docstring der Helper-Funktion).
"""
import uuid
from datetime import date
from pathlib import Path


def _neuer_job(session, url=None):
    """Frischer Job mit EINDEUTIGEM Status (uuid-Suffix) — als `backfill(status)`-Filter
    verwendet, damit ein Testlauf garantiert NUR den eigenen Job erfasst, unabhängig davon,
    wie viele andere Jobs die (session-weit akkumulierende) tmp-DB aus anderen Tests schon
    enthält (gleiches Prinzip wie `seed()`s Namens-Suffix in conftest.py).

    Die URL trägt seit 26.07.2026 denselben uuid-Suffix und ist NICHT mehr ein fester Default:
    `job.url` hat seit der Dubletten-Entscheidung (zwei Stellen mit gleicher URL) einen UNIQUE-Index, und in der
    session-weit akkumulierenden tmp-DB hätte sonst der zweite Test dieser Datei an einer
    UNIQUE-Verletzung scheitern müssen — ein Test-Artefakt, kein Produktfehler."""
    from app.models import Job

    status = f"BadgeTest-{uuid.uuid4().hex[:8]}"
    if url is None:
        url = f"https://example.invalid/stelle/{status}"
    job = Job(company_name=f"BadgeTest GmbH {status}", title="Director Professional Services",
              status=status, found_date=date.today().isoformat(),
              dedup_key=f"badge-test|{status}", url=url)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job, status


def _html_fuer(tmp_path, job) -> str:
    fname = Path(job.posting_snapshot_path).name
    return (tmp_path / fname).read_text(encoding="utf-8")


def _quelle_zeile(html: str) -> str:
    """Extrahiert die 'Quelle'-Meta-Zeile aus dem gerenderten Snapshot (dieselbe Struktur wie
    _build_html()) — vermeidet ein Substring-Match, das versehentlich woanders im Dokument
    matcht (z. B. im CSS, das --amber/--red als Variablennamen enthält)."""
    marker = '<p class="k">Quelle</p><p class="v">'
    start = html.index(marker) + len(marker)
    ende = html.index("</p>", start)
    return html[start:ende]


def _erwarte_badge(quelle: str, label: str, dot: str, kontext: str) -> None:
    """Seit 11.08.2026 trägt die Quelle-Zeile einen Ampel-PUNKT vor dem Label — die
    Badge-Ehrlichkeit umfasst jetzt BEIDE: ein amber-Label mit grünem Punkt wäre exakt die
    Beschönigung, die diese Tests jagen. Deshalb Label UND Dot-Klasse gemeinsam prüfen."""
    erwartet = f'<span class="dot {dot}"></span>{label}'
    assert quelle.startswith(erwartet), f"erwarte {label}-Badge ({dot}-Punkt) {kontext}, bekam: {quelle!r}"


# ── Reine Funktion _badge() ─────────────────────────────────────────────────────────────────
def test_badge_nicht_pruefbar_ist_amber_nicht_rot():
    from pipeline.posting_snapshot import _badge

    label, text = _badge(hat_text=False, tot=False, nicht_pruefbar=True)
    assert label == "amber"
    assert label != "rot"
    assert "prüfbar" in text.lower()


def test_badge_bestaetigt_tot_bleibt_rot():
    from pipeline.posting_snapshot import _badge

    label, _ = _badge(hat_text=False, tot=True, nicht_pruefbar=False)
    assert label == "rot"


def test_badge_mit_text_bleibt_gruen():
    from pipeline.posting_snapshot import _badge

    label, _ = _badge(hat_text=True)
    assert label == "grün"


def test_badge_ohne_text_ohne_befund_bleibt_amber_metadaten():
    from pipeline.posting_snapshot import _badge

    label, text = _badge(hat_text=False)
    assert label == "amber"
    assert "Teilquelle" in text


def test_badge_nicht_pruefbar_hat_anderen_text_als_metadaten_amber():
    """Beide amber-Fälle müssen unterscheidbar bleiben (Design-Entscheidung 4, „nie
    beschönigen" gilt auch für Verwechslungen zwischen zwei ehrlichen, aber verschiedenen
    Gründen für Amber)."""
    from pipeline.posting_snapshot import _badge

    _, text_np = _badge(hat_text=False, nicht_pruefbar=True)
    _, text_meta = _badge(hat_text=False)
    assert text_np != text_meta


def test_befund_mengen_sind_disjunkt_und_vollstaendig_wie_erwartet():
    """Regressionsschutz für den eigentlichen Bug: KONFIRMIERT_TOT_BEFUNDE und
    NICHT_PRUEFBAR_BEFUNDE dürfen sich nie überschneiden — sonst wäre wieder unklar, welcher
    Zweig in backfill() gewinnt."""
    from pipeline.posting_snapshot import KONFIRMIERT_TOT_BEFUNDE, NICHT_PRUEFBAR_BEFUNDE

    assert KONFIRMIERT_TOT_BEFUNDE == {"TOT", "ABGELAUFEN", "UMGELEITET_GENERISCH"}
    assert NICHT_PRUEFBAR_BEFUNDE == {"NICHT_PRUEFBAR", "LOGIN_WALL"}
    assert KONFIRMIERT_TOT_BEFUNDE.isdisjoint(NICHT_PRUEFBAR_BEFUNDE)


# ── backfill() end-to-end mit gefaktem check_url ────────────────────────────────────────────
def test_backfill_nicht_pruefbar_bot_block_wird_amber_nicht_rot(session, monkeypatch, tmp_path):
    import pipeline.verify_jobs as verify_jobs
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job, status = _neuer_job(session)

    monkeypatch.setattr(verify_jobs, "check_url", lambda url, company, title, return_text=False: {
        "befund": "NICHT_PRUEFBAR", "http_status": 403, "final_url": url,
        "beleg": "HTTP 403 (Bot-Block/Rate-Limit)",
    })

    result = posting_snapshot.backfill(status)
    assert result == {"jobs_gesamt": 1, "gesichert": 1, "fehler": 0}

    session.refresh(job)
    quelle = _quelle_zeile(_html_fuer(tmp_path, job))
    _erwarte_badge(quelle, "amber", "amber", "bei Bot-Block")


def test_backfill_login_wall_wird_amber_nicht_rot(session, monkeypatch, tmp_path):
    import pipeline.verify_jobs as verify_jobs
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job, status = _neuer_job(session)

    monkeypatch.setattr(verify_jobs, "check_url", lambda url, company, title, return_text=False: {
        "befund": "LOGIN_WALL", "http_status": 200, "final_url": url,
        "beleg": "Sign-in-Seite, Titel/Firma fehlen",
    })

    result = posting_snapshot.backfill(status)
    assert result == {"jobs_gesamt": 1, "gesichert": 1, "fehler": 0}

    session.refresh(job)
    quelle = _quelle_zeile(_html_fuer(tmp_path, job))
    _erwarte_badge(quelle, "amber", "amber", "bei Login-Wall")


def test_backfill_bestaetigt_tot_bleibt_rot(session, monkeypatch, tmp_path):
    """Regressionsschutz (Q5): eine ECHT tote Anzeige (HTTP 404) muss weiterhin rot bleiben —
    der Fix darf die berechtigten roten Fälle nicht mit-entschärfen."""
    import pipeline.verify_jobs as verify_jobs
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job, status = _neuer_job(session)

    monkeypatch.setattr(verify_jobs, "check_url", lambda url, company, title, return_text=False: {
        "befund": "TOT", "http_status": 404, "final_url": url, "beleg": "HTTP 404",
    })

    result = posting_snapshot.backfill(status)
    assert result == {"jobs_gesamt": 1, "gesichert": 1, "fehler": 0}

    session.refresh(job)
    quelle = _quelle_zeile(_html_fuer(tmp_path, job))
    _erwarte_badge(quelle, "rot", "red", "bei bestätigtem HTTP 404")


def test_backfill_ok_mit_text_bleibt_gruen(session, monkeypatch, tmp_path):
    """Regressionsschutz (Q5): eine lebende, geprüfte Anzeige bleibt grün."""
    import pipeline.verify_jobs as verify_jobs
    from pipeline import posting_snapshot

    monkeypatch.setattr(posting_snapshot, "_SNAPSHOT_DIR", tmp_path)
    job, status = _neuer_job(session)

    monkeypatch.setattr(verify_jobs, "check_url", lambda url, company, title, return_text=False: {
        "befund": "OK", "http_status": 200, "final_url": url,
        "beleg": "Titel 100% + Firma im Text", "anzeigentext": "Wir suchen eine Führungskraft ...",
    })

    result = posting_snapshot.backfill(status)
    assert result == {"jobs_gesamt": 1, "gesichert": 1, "fehler": 0}

    session.refresh(job)
    quelle = _quelle_zeile(_html_fuer(tmp_path, job))
    _erwarte_badge(quelle, "grün", "green", "bei OK+Text")
