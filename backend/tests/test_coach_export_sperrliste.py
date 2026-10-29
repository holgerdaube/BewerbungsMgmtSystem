"""Tests für `pipeline/coach_export.py` (Phase 81 — Coach-Site, Whitelist-Prinzip).

Der kritische Vertrag: Sperrfelder erreichen den Export NIE. Die Fixture befüllt sie mit
eindeutigen Marker-Strings; die Assertions greppen den kompletten Export-Ordner. Zusätzlich:
Whitelist-Dateimuster, Pipeline-/Absagen-Zuordnung, Artefakt-Kopie, vertrauliche Mandate
UNVERÄNDERT (Entscheidung 10.08.2026), robots.txt/noindex, dry-run schreibt nichts.

P2-79 (Seite „Tages-Digest“): Die Fixture trägt zusätzlich Marker in den Feldern, die der Digest kennt, die
Coach-Site aber nie ausgeben darf: Absender und Betreff einer Mail, die beantwortet werden will; Betreff und
Text einer Absage-Mail; eine manuelle Verlaufsnotiz an einer heute geänderten Stelle (auch als von Hand
getippte „Status: a → b“-Zeile); der Freitext `next_step` einer Stelle in Prüfung. Die Prüfung ist dieselbe
wie für die ersten drei Marker: der ganze Export-Ordner, `digest.html` eingeschlossen. Zusätzlich muss der
Absagen-Abschnitt der Seite die Absage-Mail wirklich zeigen (Firma), sonst prüfte der Test ins Leere.

Kein app.*/pipeline.*-Import auf Modulebene (conftest-Konvention); `_EXPORT_DIR` je Test per
monkeypatch auf tmp_path (Muster test_posting_snapshot_full.py)."""
import re
import uuid
from datetime import date, datetime, time
from pathlib import Path


SPERR_MARKER = {
    "salary": "SPERRMARKER-GEHALT-123456-EUR",
    "notes": "SPERRMARKER-PRIVATE-NOTIZ",
    "verify_note": "SPERRMARKER-VIER-AUGEN-INTERN",
    # P2-79 — Felder, die der Digest kennt, die Coach-Site nie zeigen darf
    "mail_absender": "SPERRMARKER-MAIL-ABSENDER",
    "mail_betreff": "SPERRMARKER-MAIL-BETREFF",
    "absage_betreff": "SPERRMARKER-ABSAGE-BETREFF",
    "absage_text": "SPERRMARKER-ABSAGE-TEXT",
    "verlauf_notiz": "SPERRMARKER-VERLAUF-NOTIZ",
    "verlauf_status": "SPERRMARKER-VERLAUF-STATUS",
    "next_step": "SPERRMARKER-NAECHSTER-SCHRITT",
}


def _heute_mittag() -> datetime:
    """Heute 12:00 als naiver Zeitpunkt, wie `updated_at`/`created_at` in der DB. Bewusst nicht `utcnow()`:
    Der Digest vergleicht `.date()` mit dem LOKALEN Datum; zwischen 0 und 2 Uhr Ortszeit läge `utcnow()` auf
    gestern, die Stelle fiele still aus „Heute geändert“ und der Test prüfte nichts mehr."""
    return datetime.combine(date.today(), time(12, 0))


def _fixture(_session, tmp_path, monkeypatch):
    """`_session` (die geteilte Test-DB) bleibt nur in der Signatur, damit die Tests die Datenbank-Fixture
    weiter anfordern; die Fixture-Daten liegen seit P2-79 in einer EIGENEN Datenbank: Der Digest zeigt nur die
    ersten 15 Zeilen je Abschnitt (Zu beantworten in Datenbank-Reihenfolge), die geteilte Test-DB sammelt
    Mails und Stellen aller früheren Tests, und ein Marker jenseits der 15. Zeile liefe nie in den Export —
    die Marker-Prüfung bliebe grün, ohne etwas zu prüfen (Vorbild: `digest_db` in test_digest_absagen.py)."""
    from sqlmodel import Session, SQLModel, create_engine

    from app.models import Application, Company, CVVersion, Email, Job, JobLog
    from pipeline import absagen_bericht, coach_export, digest

    eng = create_engine("sqlite:///" + str(tmp_path / "sperrliste.sqlite"))
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(coach_export, "engine", eng)
    monkeypatch.setattr(digest, "engine", eng)
    session = Session(eng)
    monkeypatch.setattr(coach_export, "_EXPORT_DIR", tmp_path / "coach_site")

    # Artefakt-Quelldateien unter DATA_DIR (Auflösung 'data/…' → DATA_DIR/…)
    from app.db import DATA_DIR
    (DATA_DIR / "company_fit").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "analysen").mkdir(parents=True, exist_ok=True)
    fit = DATA_DIR / "company_fit" / "2026_08_10_CompanyFit_CoachTest_AG.html"
    fit.write_text("<html>CompanyFit-Inhalt</html>", encoding="utf-8")
    match = DATA_DIR / "company_fit" / "2026_08_10_Match_CoachTest_AG_Rolle.html"
    match.write_text("<html>Match-Inhalt</html>", encoding="utf-8")
    # P2-79: Der Export nimmt den Bericht über `absagen_bericht.neuester()`. Die geteilte Test-DATA_DIR sammelt
    # Berichte anderer Tests, deshalb liegt der Bericht dieser Tests in einem eigenen Ordner und gilt allein.
    analysen = tmp_path / "analysen"
    analysen.mkdir()
    analyse = analysen / "2026_08_01_Analyse_Absagen.html"
    analyse.write_text("<html>Lost-Order</html>", encoding="utf-8")
    monkeypatch.setattr(absagen_bericht, "ordner", lambda: analysen)

    # Kanon-Snapshot MIT Erfassungs-Kontext (enthält den verify_note-Marker) — der Export
    # muss den Block entfernen, der Anzeigen-Inhalt muss bleiben.
    (DATA_DIR / "job_postings").mkdir(parents=True, exist_ok=True)
    snap = DATA_DIR / "job_postings" / "2026_08_10_Stellenausschreibung_CoachTest_AG.html"
    snap.write_text(
        "<html><body><h2 class=\"sec\">Aufgaben</h2><div class=\"card\"><ul><li>Anzeigen-Aufgabe wörtlich</li></ul></div>\n"
        "<h2 class=\"sec\">Erfassungs-Kontext</h2>\n<div class=\"card\"><p><b>Vier-Augen-Beleg:</b> "
        f"{SPERR_MARKER['verify_note']}</p></div>\n<div class=\"foot\"><span>Bewerbungs-Mgmt</span></div></body></html>",
        encoding="utf-8")
    # Alt-Snapshot, dessen Kontext-Block NICHT dem Kanon-Muster folgt → Guard muss überspringen
    snap_alt = DATA_DIR / "job_postings" / "2026_07_01_Stellenausschreibung_AltFormat_GmbH.html"
    snap_alt.write_text(
        f"<html><body><p>Anzeige</p><p>Vier-Augen-Beleg: {SPERR_MARKER['verify_note']}</p></body></html>",
        encoding="utf-8")
    # Alt-Snapshot mit FREIEM Prüfvermerk ohne Kanon-Label (Live-Fund 10.08.:
    # "Vier-Augen-Check bereits bestätigt…") → Präfix-Marker muss ihn ebenfalls überspringen
    snap_alt2 = DATA_DIR / "job_postings" / "2026_07_02_Stellenausschreibung_AltCheck_AG.html"
    snap_alt2.write_text(
        "<html><body><p>Anzeige</p><div>(Vier-Augen-Check bereits bestätigt: kein Konflikt).</div></body></html>",
        encoding="utf-8")

    suffix = uuid.uuid4().hex[:8]
    comp = Company(name=f"CoachTest AG {suffix}", fit_analysis_path=f"data/company_fit/{fit.name}")
    session.add(comp)
    session.commit()
    session.refresh(comp)

    def job(status, firma, **kw):
        j = Job(company_name=firma, title=kw.pop("title", "Director PS"),
                status=status, found_date=date.today().isoformat(),
                dedup_key=f"coach|{firma}|{status}|{suffix}",
                url=f"https://example.invalid/{uuid.uuid4().hex[:6]}",
                salary=SPERR_MARKER["salary"], notes=SPERR_MARKER["notes"],
                verify_note=SPERR_MARKER["verify_note"], **kw)
        session.add(j)
        session.commit()
        session.refresh(j)
        return j

    beworben = job("Beworben", f"CoachTest AG {suffix}", company_id=comp.id, match_score=5,
                   posting_snapshot_path=f"data/job_postings/{snap.name}")
    vertraulich = job("Interview", f"[vertraulich] Intrinsic Search {suffix}", match_score=4,
                      posting_snapshot_path=f"data/job_postings/{snap_alt.name}")
    absage = job("Absage", f"Absage GmbH {suffix}", match_score=3)
    job("Neu", f"Neu-Firma {suffix}", match_score=4,      # Vorstufe (Erweiterung 10.08.)
        posting_snapshot_path=f"data/job_postings/{snap_alt2.name}")
    job("Geparkt", f"Geparkt AG {suffix}")                # weiterhin NICHT sichtbar
    # P2-79: Stelle in Prüfung mit Freitext im Feld „nächster Schritt“ (Digest-Abschnitt „Offene Aktionen“)
    job("Prüfen", f"Pruef-Firma {suffix}", next_step=SPERR_MARKER["next_step"])

    session.add(CVVersion(job_id=beworben.id, match_dashboard_path=f"data/company_fit/{match.name}"))
    session.add(Application(job_id=absage.id, channel="Portal",
                            rejection_reason=f"Interne Besetzung bevorzugt {suffix}"))

    # P2-79: Der Digest kennt Mails und das Verlaufsprotokoll. Zwei Stellen gelten als HEUTE GEÄNDERT; an der
    # einen steht eine manuelle Notiz (Stufe „jüngste Notiz“ des normalen Digest), an der anderen eine von Hand
    # getippte Zeile, die wie ein Statuswechsel aussieht, aber keiner ist (art='manuell').
    for stelle in (beworben, vertraulich):
        stelle.updated_at = _heute_mittag()
        session.add(stelle)
    session.add(JobLog(job_id=beworben.id, art="manuell", created_at=_heute_mittag(),
                       eintrag=SPERR_MARKER["verlauf_notiz"]))
    session.add(JobLog(job_id=vertraulich.id, art="manuell", created_at=_heute_mittag(),
                       eintrag=f"Status: Interview → {SPERR_MARKER['verlauf_status']}"))
    # eine eingehende Mail, die beantwortet werden will (Digest: „Zu beantworten“)
    session.add(Email(job_id=beworben.id, direction="incoming", category="Rückfrage", needs_reply=True,
                      from_addr=f"{SPERR_MARKER['mail_absender']}@example.invalid",
                      subject=SPERR_MARKER["mail_betreff"], received_at=datetime.utcnow()))
    # eine Absage-Mail der letzten Stunden (Digest: „Absagen der letzten 96 Stunden“ — Firma ja, Betreff/Text nie)
    session.add(Email(job_id=absage.id, direction="incoming", category="Absage", response_time_hours=30.0,
                      from_addr=f"{SPERR_MARKER['mail_absender']}@example.invalid",
                      subject=SPERR_MARKER["absage_betreff"], snippet=SPERR_MARKER["absage_text"],
                      received_at=datetime.utcnow()))
    session.commit()
    for stelle in (beworben, vertraulich, absage):      # nach dem Schließen weiter lesbar (kein Neuladen nötig)
        session.refresh(stelle)
    session.close()
    return coach_export, beworben, vertraulich, absage, suffix


def _alle_texte(ordner: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="replace")
                     for p in ordner.rglob("*") if p.is_file())


def _abschnitt(seite: str, ueberschrift: str) -> str:
    """Der Abschnitt (`<section>`) einer Seite ab der Überschrift."""
    start = seite.index(ueberschrift)
    return seite[start:seite.index("</section>", start)]


def test_sperrfelder_erreichen_den_export_nie(session, monkeypatch, tmp_path):
    coach_export, *_ = _fixture(session, tmp_path, monkeypatch)
    result = coach_export.export()
    assert result["dry_run"] is False
    inhalt = _alle_texte(tmp_path / "coach_site")
    for feld, marker in SPERR_MARKER.items():
        assert marker not in inhalt, f"Sperrfeld {feld} ist in den Export gelangt!"


def test_tages_digest_zeigt_die_erlaubten_teile_und_nur_die(session, monkeypatch, tmp_path):
    """P2-79: Die Marker-Prüfung oben ist nur etwas wert, wenn die Abschnitte, in denen die Marker stünden,
    wirklich gerendert werden. Hier die Gegenseite: Die Absage-Mail steht mit ihrer FIRMA im Absagen-Abschnitt
    (Betreff und Text nicht), die heute geänderten Stellen stehen in „Heute geändert“ mit dem Status statt
    mit dem Notiztext, und „Zu beantworten“ sowie „Offene Aktionen“ gibt es auf der Seite nicht."""
    coach_export, beworben, vertraulich, absage, _suffix = _fixture(session, tmp_path, monkeypatch)
    coach_export.export()
    seite = (tmp_path / "coach_site" / "digest.html").read_text(encoding="utf-8")

    assert absage.company_name in _abschnitt(seite, "Absagen der letzten")
    geaendert = _abschnitt(seite, "Heute geändert")
    assert beworben.company_name in geaendert and vertraulich.company_name in geaendert
    assert "Zu beantworten" not in seite and "Offene Aktionen" not in seite


def test_whitelist_dateimuster_und_seiten(session, monkeypatch, tmp_path):
    coach_export, *_ = _fixture(session, tmp_path, monkeypatch)
    coach_export.export()
    ordner = tmp_path / "coach_site"
    erlaubt = re.compile(r"^(index|digest|stellen|absagen)\.html$|^robots\.txt$"
                         r"|^artefakte/((CompanyFit_|Match_|Stellenausschreibung_|.*Analyse_Absagen).*\.html|"
                         r"\d{4}_\d{2}_\d{2}_(CompanyFit|Match|Stellenausschreibung|Analyse)_.*\.html)$")
    for p in ordner.rglob("*"):
        if p.is_file():
            # as_posix(): auf Windows liefert str() Backslashes — CI-Fall 10.08.2026
            rel = p.relative_to(ordner).as_posix()
            assert erlaubt.match(rel), f"Unerwartete Datei im Export: {rel}"
    assert (ordner / "index.html").is_file()
    assert (ordner / "robots.txt").read_text().startswith("User-agent: *")
    assert 'name="robots" content="noindex' in (ordner / "index.html").read_text(encoding="utf-8")


def test_pipeline_absagen_zuordnung_und_artefakte(session, monkeypatch, tmp_path):
    coach_export, beworben, vertraulich, absage, suffix = _fixture(session, tmp_path, monkeypatch)
    result = coach_export.export()
    ordner = tmp_path / "coach_site"
    stellen = (ordner / "stellen.html").read_text(encoding="utf-8")
    absagen = (ordner / "absagen.html").read_text(encoding="utf-8")

    assert beworben.company_name in stellen
    # Erweiterung 10.08.: Vorstufe (Neu/Prüfen) ist SICHTBAR, Geparkt weiterhin nicht
    assert "Aktive Bewerbungen" in stellen and "Sichtung &amp; Prüfung" in stellen
    assert f"Neu-Firma {suffix}" in stellen
    assert stellen.index("Aktive Bewerbungen") < stellen.index(f"Neu-Firma {suffix}")
    assert f"Geparkt AG {suffix}" not in stellen
    assert absage.company_name not in stellen and absage.company_name in absagen
    assert f"Interne Besetzung bevorzugt {suffix}" in absagen
    # Artefakte kopiert + verlinkt
    assert any(a.startswith("2026_08_10_CompanyFit_") for a in result["artefakte"])
    assert any(a.startswith("2026_08_10_Match_") for a in result["artefakte"])
    assert 'href="artefakte/2026_08_10_CompanyFit_CoachTest_AG.html"' in stellen
    assert (ordner / "artefakte" / "2026_08_10_Match_CoachTest_AG_Rolle.html").is_file()
    assert "Analyse_Absagen" in absagen


def test_snapshot_bereinigt_und_altformat_guard(session, monkeypatch, tmp_path):
    """Erweiterung 10.08.: Kanon-Snapshot geht MIT Anzeigen-Inhalt, aber OHNE Erfassungs-
    Kontext raus; Alt-Format ohne sicheres Muster wird ÜBERSPRUNGEN und gemeldet."""
    coach_export, beworben, *_ = _fixture(session, tmp_path, monkeypatch)
    result = coach_export.export()
    ordner = tmp_path / "coach_site"

    kopie = ordner / "artefakte" / "2026_08_10_Stellenausschreibung_CoachTest_AG.html"
    assert kopie.is_file()
    inhalt = kopie.read_text(encoding="utf-8")
    assert "Anzeigen-Aufgabe wörtlich" in inhalt
    assert "Erfassungs-Kontext" not in inhalt and "Vier-Augen-Beleg" not in inhalt
    assert SPERR_MARKER["verify_note"] not in inhalt

    assert result["snapshots_uebersprungen"] == [
        "2026_07_01_Stellenausschreibung_AltFormat_GmbH.html",
        "2026_07_02_Stellenausschreibung_AltCheck_AG.html",
    ]
    assert not (ordner / "artefakte" / "2026_07_01_Stellenausschreibung_AltFormat_GmbH.html").exists()
    assert not (ordner / "artefakte" / "2026_07_02_Stellenausschreibung_AltCheck_AG.html").exists()
    stellen = (ordner / "stellen.html").read_text(encoding="utf-8")
    assert 'href="artefakte/2026_08_10_Stellenausschreibung_CoachTest_AG.html">Anzeige</a>' in stellen


def test_vertrauliche_mandate_unveraendert(session, monkeypatch, tmp_path):
    coach_export, _b, vertraulich, *_ = _fixture(session, tmp_path, monkeypatch)
    coach_export.export()
    stellen = (tmp_path / "coach_site" / "stellen.html").read_text(encoding="utf-8")
    assert "[vertraulich] Intrinsic Search" in stellen  # 1:1 wie in der App, keine Maskierung


def test_dry_run_schreibt_nichts(session, monkeypatch, tmp_path):
    coach_export, *_ = _fixture(session, tmp_path, monkeypatch)
    result = coach_export.export(dry_run=True)
    assert result["dry_run"] is True
    assert sorted(result["seiten"]) == ["absagen.html", "digest.html", "index.html", "robots.txt",
                                        "stellen.html"]
    assert not (tmp_path / "coach_site").exists()
