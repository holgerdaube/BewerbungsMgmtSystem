"""Ingest: Neuausschreibungen aussortierter Stellen erscheinen wieder als „Neu“ (P2-36, 11.09.2026).

Fall A (Rückmeldung aus dem Betrieb): „sag mir mal wieso du die zweite Stelle nicht als Dublette
der ersten erkannt hast.“ Die Firma hatte dieselbe Stelle zweimal auf LinkedIn ausgeschrieben — Titel und
Ort leicht verschieden (Gender-Zusatz „(m/f/d)“, anderer Ort), neue LinkedIn-ID. Die dritte
Dedup-Stufe (`normalize.ct_key`, Firma+Titel ohne Ort) verfehlte den Treffer, weil der
Gender-Zusatz im Titel mitgeschleppt wurde.

Der bereinigte Firma+Titel-Schlüssel (`ingest._stellen_schluessel`, Titel ohne Gender-Zusatz)
fängt das jetzt ab — ABER: eine im ENDSTATUS aussortierte Stelle (Kein Match/Absage/...) darf
eine neue Anzeige (neuer Link) nicht länger stumm verschlucken. Fall B: Eine Stelle
„Head of Customer Success (m/w/d)“ landete auf „Kein Match“ (24.08.), die Stelle „... (m/f/d)“ kam
am 09.09. erneut rein — mit dem reinen Schlüssel-Fix wäre sie (die Stelle, auf die sich der Nutzer
tatsächlich beworben hat!) still verworfen worden. Entscheidung (11.09.2026): eine solche
Neuausschreibung wird angelegt, mit Hinweis „NEUAUSSCHREIBUNG?“; Dubletten laufender Stellen
(inkl. „Geparkt“) und reine Papierkorb-Treffer bleiben weiter gesperrt (s. Spec
`tasks/spec_p2-36_neuausschreibung_dublette.md`).

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention).
"""
import types
import uuid


def _mit_synthetischer_leerer_config(monkeypatch, tmp_path):
    """s. tests/test_ingest_repost_selber_lauf.py::_mit_synthetischer_leerer_config — identisches
    Muster: `dedup_text.konfiguration()` (von `ingest_records()` IMMER aufgerufen) würde ohne
    Patch mit SystemExit abbrechen, weil `config/suchprofile.yaml` gitignored ist und in CI
    fehlt."""
    import pipeline.dedup_text as dedup_text

    leere_config = tmp_path / "suchprofile.yaml"
    leere_config.write_text("dedup_text: {}\n", encoding="utf-8")
    monkeypatch.setattr(dedup_text, "CONFIG_FILE", leere_config)


def _verifikation(beleg: str) -> dict:
    return {"status": "BESTÄTIGT", "beleg": beleg, "geprueft_am": "2026-09-11"}


def _firmenname(prefix="Firma") -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]} AG"


def _firma_anlegen(session, prefix="Firma"):
    """Company direkt über die Session anlegen — `company.name` trägt einen UNIQUE-Index,
    deshalb IMMER ein per-Test eindeutiger Name (Muster conftest.py::seed /
    test_bewerbungsstatus_mitziehen.py::_job_mit_bewerbung, die Suite teilt sich EINE
    session-weite tmp-DB)."""
    from app.models import Company

    comp = Company(name=_firmenname(prefix))
    session.add(comp)
    session.commit()
    session.refresh(comp)
    return comp


def _job_anlegen(session, comp, *, title, location=None, status="Prüfen", deleted_at=None,
                 found_date="2026-08-23", url=None, dedup_key=None):
    """Job DIREKT über die Session anlegen (Muster test_bewerbungsstatus_mitziehen.py::
    _job_mit_bewerbung) — simuliert einen BESTEHENDEN Job (Vorgänger/Konkurrenz), der NICHT
    über `ingest_records()` eingeliefert wird."""
    from app.models import Job
    from app import normalize as N

    dk = dedup_key or N.dedup_key(comp.name, title, location)
    job = Job(company_id=comp.id, company_name=comp.name, title=title, location=location,
              status=status, portal="LinkedIn", found_date=found_date, url=url,
              dedup_key=dk, deleted_at=deleted_at)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def _neue_url() -> str:
    return f"https://example.test/job/{uuid.uuid4().hex[:8]}"


# ── 1. titel_ohne_gender ─────────────────────────────────────────────────────
def test_titel_ohne_gender_entfernt_alle_bekannten_varianten():
    from app.normalize import titel_ohne_gender

    assert titel_ohne_gender("Manager (m/w/d)") == "Manager"
    assert titel_ohne_gender("Manager (m/f/d)") == "Manager"
    assert titel_ohne_gender("Manager (w/m/d)") == "Manager"
    assert titel_ohne_gender("Manager (f/m/x)") == "Manager"
    assert titel_ohne_gender("Manager (all genders)") == "Manager"
    # Zusatz mitten im Titel -> Leerzeichen kollabiert, keine doppelten Spaces übrig.
    assert titel_ohne_gender("Manager (m/w/d) Sales") == "Manager Sales"
    # Ohne Zusatz unverändert.
    assert titel_ohne_gender("Director Professional Services") == "Director Professional Services"
    # None -> "" (nie ein Absturz bei fehlendem Titel).
    assert titel_ohne_gender(None) == ""


# ── 2. Fall A (laufende Stelle deckt die Anzeige ab) ──────────────────
def test_fall_a_gender_zusatz_wird_als_dublette_erkannt(session, monkeypatch, tmp_path):
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from pipeline.ingest import ingest_records

    comp = _firma_anlegen(session, "Beispiel Medizintechnik")
    _job_anlegen(session, comp, title="Manager, Technical Service (Linie A), Northern Europe",
                 location="Germany", status="Prüfen", found_date="2026-09-09")

    rec = {"company": comp.name,
           "title": "Manager (m/f/d), Technical Service (Linie A), Northern Europe",
           "location": "Musterstadt, North Rhine-Westphalia, Germany", "url": _neue_url(),
           "verifikation": _verifikation("Live gesehen — Mail-Alert 10.09.")}

    result = ingest_records([rec])

    assert result["dup"] == 1, result
    assert result["new"] == 0, result


# ── 3. Fall B (Endstatus-Vorgänger -> Neuausschreibung) ──────────────
def test_fall_b_neuausschreibung_wird_angelegt(session, monkeypatch, tmp_path):
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from sqlmodel import select
    from app.models import Job, JobLog
    from pipeline.ingest import ingest_records

    comp = _firma_anlegen(session, "Muster Group")
    alt = _job_anlegen(session, comp, title="Head of Customer Success (m/w/d)",
                       status="Kein Match", found_date="2026-08-23")

    url = _neue_url()
    rec = {"company": comp.name, "title": "Head of Customer Success (m/f/d)", "url": url,
           "verifikation": _verifikation("Live gesehen — Mail-Alert 09.09.")}
    result = ingest_records([rec])

    assert result["new"] == 1, result
    assert result["neuausschreibungen"] == 1, result

    neu = session.exec(select(Job).where(Job.url == url)).one()
    assert f"NEUAUSSCHREIBUNG? Job {alt.id}" in (neu.verify_note or ""), neu.verify_note
    assert "Kein Match" in (neu.verify_note or ""), neu.verify_note

    logs = session.exec(select(JobLog).where(JobLog.job_id == neu.id)).all()
    assert any("NEUAUSSCHREIBUNG?" in (l.eintrag or "") for l in logs), logs


# ── 4. Gleiche URL wie eine Endstatus-Stelle -> Dublette (§2.1 Schritt 1, unverändert) ──
def test_gleiche_url_wie_endstatus_stelle_bleibt_dublette(session, monkeypatch, tmp_path):
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from pipeline.ingest import ingest_records

    comp = _firma_anlegen(session, "URL-Gleich")
    url = _neue_url()
    _job_anlegen(session, comp, title="Director Services", status="Absage", url=url)

    rec = {"company": comp.name, "title": "Director Services", "url": url,
           "verifikation": _verifikation("Live gesehen")}
    result = ingest_records([rec])

    assert result["dup"] == 1, result
    assert result["new"] == 0, result


# ── 5. Record ohne URL, Treffer im Endstatus -> Dublette (konservativ) ──────
def test_ohne_url_mit_endstatus_treffer_bleibt_dublette(session, monkeypatch, tmp_path):
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from pipeline.ingest import ingest_records

    comp = _firma_anlegen(session, "Ohne-URL")
    _job_anlegen(session, comp, title="Head of Sales (m/w/d)", status="Absage")

    rec = {"company": comp.name, "title": "Head of Sales (m/f/d)",
           "verifikation": _verifikation("Live gesehen")}
    result = ingest_records([rec])

    assert result["dup"] == 1, result
    assert result["new"] == 0, result


# ── 6. Nur Papierkorb-Treffer -> Dublette (Sperre bleibt) ───────────────────
def test_nur_papierkorb_treffer_bleibt_dublette(session, monkeypatch, tmp_path):
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from pipeline.ingest import ingest_records

    comp = _firma_anlegen(session, "Papierkorb")
    _job_anlegen(session, comp, title="Head of Sales (m/w/d)", status="Kein Match",
                 deleted_at="2026-08-25T00:00:00")

    rec = {"company": comp.name, "title": "Head of Sales (m/f/d)", "url": _neue_url(),
           "verifikation": _verifikation("Live gesehen")}
    result = ingest_records([rec])

    assert result["dup"] == 1, result
    assert result["new"] == 0, result


# ── 7. Treffer gemischt (Endstatus + laufend) -> Dublette (laufend gewinnt) ──
def test_treffer_gemischt_laufend_gewinnt_bleibt_dublette(session, monkeypatch, tmp_path):
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from pipeline.ingest import ingest_records

    comp = _firma_anlegen(session, "Gemischt")
    _job_anlegen(session, comp, title="Head of Sales (m/w/d)", status="Kein Match")
    _job_anlegen(session, comp, title="Head of Sales (all genders)", status="Prüfen")

    rec = {"company": comp.name, "title": "Head of Sales (m/f/d)", "url": _neue_url(),
           "verifikation": _verifikation("Live gesehen")}
    result = ingest_records([rec])

    assert result["dup"] == 1, result
    assert result["new"] == 0, result


# ── 8. Geparkt gilt als laufend -> Dublette ─────────────────────────────────
def test_geparkt_gilt_als_laufend_bleibt_dublette(session, monkeypatch, tmp_path):
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from pipeline.ingest import ingest_records

    comp = _firma_anlegen(session, "Geparkt")
    _job_anlegen(session, comp, title="Head of Sales (m/w/d)", status="Geparkt")

    rec = {"company": comp.name, "title": "Head of Sales (m/f/d)", "url": _neue_url(),
           "verifikation": _verifikation("Live gesehen")}
    result = ingest_records([rec])

    assert result["dup"] == 1, result
    assert result["new"] == 0, result


# ── 9. dedup_key-Kollision bei exakt gleichem Titel+Ort (§2.4, UNIQUE-Index) ─
def test_dedup_key_kollision_bekommt_anderen_schluessel_kein_absturz(session, monkeypatch, tmp_path):
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from sqlmodel import select
    from app.models import Job
    from pipeline.ingest import ingest_records

    comp = _firma_anlegen(session, "Kollision")
    alt = _job_anlegen(session, comp, title="Director Services", location="Berlin", status="Absage")

    url = _neue_url()
    rec = {"company": comp.name, "title": "Director Services", "location": "Berlin", "url": url,
           "verifikation": _verifikation("Live gesehen")}
    result = ingest_records([rec])

    assert result["new"] == 1, result
    assert result["neuausschreibungen"] == 1, result

    neu = session.exec(select(Job).where(Job.url == url)).one()
    assert neu.dedup_key != alt.dedup_key, (neu.dedup_key, alt.dedup_key)


# ── 10. Selber Lauf: zwei neue Anzeigen derselben aussortierten Stelle ──────
def test_selber_lauf_erste_neuausschreibung_zweite_dublette(session, monkeypatch, tmp_path):
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from pipeline.ingest import ingest_records

    comp = _firma_anlegen(session, "SelberLauf")
    _job_anlegen(session, comp, title="Head of Sales (m/w/d)", status="Kein Match")

    rec_a = {"company": comp.name, "title": "Head of Sales (m/f/d)", "url": _neue_url(),
             "verifikation": _verifikation("Live gesehen A")}
    rec_b = {"company": comp.name, "title": "Head of Sales (all genders)", "url": _neue_url(),
             "verifikation": _verifikation("Live gesehen B")}

    result = ingest_records([rec_a, rec_b])

    assert result["new"] == 1, (
        "Record A trifft den Kein-Match-Vorgänger -> Neuausschreibung -> neu angelegt: "
        f"{result}"
    )
    assert result["dup"] == 1, (
        "Record B trifft den GERADE ERST angelegten, jetzt laufenden Job aus Record A -> "
        f"Dublette (nicht ein zweites Mal Neuausschreibung): {result}"
    )
    assert result["neuausschreibungen"] == 1, result


# ── 11. Zwei Endstatus-Vorgänger -> Hinweis nennt den mit der höheren id ────
def test_zwei_endstatus_vorgaenger_hinweis_nennt_hoehere_id(session, monkeypatch, tmp_path):
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from sqlmodel import select
    from app.models import Job
    from pipeline.ingest import ingest_records

    comp = _firma_anlegen(session, "ZweiVorgaenger")
    aelter = _job_anlegen(session, comp, title="Head of Sales (m/w/d)", status="Kein Match",
                          found_date="2026-08-01")
    neuer = _job_anlegen(session, comp, title="Head of Sales (w/m/d)", status="Absage",
                         found_date="2026-08-15")
    assert neuer.id > aelter.id, "Testvoraussetzung: 'neuer' muss die höhere id tragen"

    url = _neue_url()
    rec = {"company": comp.name, "title": "Head of Sales (m/f/d)", "url": url,
           "verifikation": _verifikation("Live gesehen")}
    result = ingest_records([rec])

    assert result["neuausschreibungen"] == 1, result
    neu = session.exec(select(Job).where(Job.url == url)).one()
    assert f"Job {neuer.id}" in (neu.verify_note or ""), neu.verify_note
    assert f"Job {aelter.id} " not in (neu.verify_note or ""), neu.verify_note


# ── 12. Hinweis-Format: deutsche Anführungszeichen, kein ASCII-Quote, kein weiteres '|' ──
def test_hinweis_format_deutsche_anfuehrungszeichen_kein_pipe_im_anhang(session, monkeypatch, tmp_path):
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from sqlmodel import select
    from app.models import Job
    from pipeline.ingest import ingest_records

    comp = _firma_anlegen(session, "HinweisFormat")
    _job_anlegen(session, comp, title="Head | of Sales (m/w/d)", status="Kein Match")

    url = _neue_url()
    rec = {"company": comp.name, "title": "Head | of Sales (m/f/d)", "url": url,
           "verifikation": _verifikation("Live gesehen")}
    result = ingest_records([rec])
    assert result["neuausschreibungen"] == 1, result

    neu = session.exec(select(Job).where(Job.url == url)).one()
    note = neu.verify_note or ""
    idx = note.index("NEUAUSSCHREIBUNG?")
    anhang = note[idx:]

    assert "„" in anhang and "“" in anhang, note
    assert '"' not in anhang, note
    # Der Titel enthielt ein '|' -> muss durch '/' ersetzt sein, sonst würde der Review-Code
    # (der an ' | ' trennt) den Anhang mitten im Titel zerreißen.
    assert "|" not in anhang, note


# ── 13. Vier-Augen-Gate greift auch bei einer Neuausschreibung ─────────────
def test_vier_augen_gate_greift_auch_bei_neuausschreibung(session, monkeypatch, tmp_path):
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from pipeline.ingest import ingest_records

    comp = _firma_anlegen(session, "Gate")
    _job_anlegen(session, comp, title="Head of Sales (m/w/d)", status="Kein Match")

    rec = {"company": comp.name, "title": "Head of Sales (m/f/d)", "url": _neue_url()}
    # KEIN verifikation-Block -> Vier-Augen-Gate muss greifen, unabhängig von der Lage.

    result = ingest_records([rec])

    assert result["unverifiziert"] == 1, result
    assert result["new"] == 0, result
    assert result["neuausschreibungen"] == 0, result


# ── 14. run.summary endet auf das neue Segment, Dict trägt den Schlüssel ───
def test_run_summary_endet_auf_neuausschreibungen_segment(session, monkeypatch, tmp_path):
    _mit_synthetischer_leerer_config(monkeypatch, tmp_path)
    from app.models import Run
    from pipeline.ingest import ingest_records

    comp = _firma_anlegen(session, "Summary")
    _job_anlegen(session, comp, title="Head of Sales (m/w/d)", status="Kein Match")

    rec = {"company": comp.name, "title": "Head of Sales (m/f/d)", "url": _neue_url(),
           "verifikation": _verifikation("Live gesehen")}
    result = ingest_records([rec])

    assert "neuausschreibungen" in result, result
    run = session.get(Run, result["run_id"])
    assert run.summary.endswith("Neuausschreibungen (früher aussortiert)"), run.summary


# ── 15. Regression: gmail_ingest._match_job bleibt eindeutig (§3 der Spec) ─
def test_regression_match_job_bleibt_eindeutig_trotz_gender_varianten(session):
    """`ct_key` bleibt bewusst roh (P2-36 §3) — `gmail_ingest._match_job` nutzt ihn für die
    EXAKTE Mail->Stelle-Zuordnung. Zwei Gender-Varianten derselben Rolle bei einer Firma (eine
    Kein-Match, eine laufende Bewerbung) dürfen dort NICHT mehrdeutig werden — sonst würde eine
    eingehende Mail zur laufenden Bewerbung (Beworben) plötzlich keinen Job mehr treffen."""
    from pipeline import gmail_ingest

    comp = _firma_anlegen(session, "Regression")
    _job_anlegen(session, comp, title="Head of Customer Success (m/w/d)", status="Kein Match")
    beworben = _job_anlegen(session, comp, title="Head of Customer Success (m/f/d)", status="Beworben")

    treffer = gmail_ingest._match_job(session, comp, "Head of Customer Success (m/f/d)")

    assert treffer is not gmail_ingest._MEHRDEUTIG, (
        "ct_key bleibt roh -> exakter Titel-Treffer, NICHT mehrdeutig (s. Spec §3)"
    )
    assert treffer is not None
    assert treffer.id == beworben.id


# ── 16. _einordnen als reine Funktion — je ein Fall pro Tabellenzeile (§2.1 Schritt 3) ──
def _fake_job(id, status, deleted_at=None):
    return types.SimpleNamespace(id=id, status=status, deleted_at=deleted_at)


def test_einordnen_keine_treffer_ist_neu():
    from pipeline.ingest import _einordnen

    assert _einordnen("https://x/1", []) == ("neu", None)


def test_einordnen_treffer_ohne_url_ist_dublette():
    from pipeline.ingest import _einordnen

    laufend = _fake_job(1, "Prüfen")
    assert _einordnen(None, [laufend]) == ("dublette", None)
    assert _einordnen("", [laufend]) == ("dublette", None)


def test_einordnen_laufender_treffer_ist_dublette():
    from pipeline.ingest import _einordnen

    laufend = _fake_job(1, "Prüfen")
    assert _einordnen("https://x/2", [laufend]) == ("dublette", None)


def test_einordnen_geparkt_zaehlt_als_laufend_ist_dublette():
    from pipeline.ingest import _einordnen

    geparkt = _fake_job(1, "Geparkt")
    assert _einordnen("https://x/3", [geparkt]) == ("dublette", None)


def test_einordnen_nur_endstatus_treffer_ist_neuausschreibung_hoechste_id():
    from pipeline.ingest import _einordnen

    aelter = _fake_job(10, "Kein Match")
    neuer = _fake_job(20, "Absage")
    lage, vorgaenger = _einordnen("https://x/4", [aelter, neuer])
    assert lage == "neuausschreibung"
    assert vorgaenger is neuer


def test_einordnen_gemischt_laufend_gewinnt_ist_dublette():
    from pipeline.ingest import _einordnen

    endstatus = _fake_job(1, "Kein Match")
    laufend = _fake_job(2, "Prüfen")
    assert _einordnen("https://x/5", [endstatus, laufend]) == ("dublette", None)


def test_einordnen_nur_papierkorb_treffer_ist_dublette():
    from pipeline.ingest import _einordnen

    papierkorb = _fake_job(1, "Kein Match", deleted_at="2026-08-25T00:00:00")
    assert _einordnen("https://x/6", [papierkorb]) == ("dublette", None)


def test_einordnen_papierkorb_und_endstatus_gemischt_ist_neuausschreibung():
    """Ein Papierkorb-Treffer ändert nichts an der Neuausschreibungs-Entscheidung — nur
    NICHT-gelöschte Treffer zählen für die Endstatus-/Laufend-Unterscheidung."""
    from pipeline.ingest import _einordnen

    papierkorb = _fake_job(1, "Kein Match", deleted_at="2026-08-25T00:00:00")
    endstatus = _fake_job(2, "Absage")
    lage, vorgaenger = _einordnen("https://x/7", [papierkorb, endstatus])
    assert lage == "neuausschreibung"
    assert vorgaenger is endstatus


# ── P2-42: Titel im Hinweis an der Wortgrenze kürzen ────────────────────────────────────────
# Fall C (17.09.2026): der harte 40-Zeichen-Schnitt ließ „Senior Manager
# Service Center Quality & “ stehen. Die Regexe unten spiegeln die beiden Frontend-Parser aus
# `frontend/src/components/ui.tsx` — ein gekürzter Titel darf keinen von beiden brechen.
import re

_PARSE_NEUAUSSCHREIBUNG = re.compile(r"NEUAUSSCHREIBUNG\?\s*Job\s*(\d+)\s*„[^“]*“\s*—\s*([^,|]+)")
_PARSE_DUBLETTE = re.compile(r"DUBLETTE\?\s*Job\s*(\d+)[^—]*—\s*Text-Ähnlichkeit\s*(\d+)\s*%")


def test_titel_kurz_fall_c_endet_an_wortgrenze_ohne_verbinder():
    from pipeline.ingest import _titel_kurz

    kurz = _titel_kurz("Senior Manager Service Center Quality & Public (Person*)")
    assert kurz == "Senior Manager Service Center Quality…"


def test_titel_kurz_laesst_kurze_und_genau_40_zeichen_lange_titel_unveraendert():
    from pipeline.ingest import _titel_kurz

    assert _titel_kurz("Head of Customer Success (m/w/d)") == "Head of Customer Success (m/w/d)"
    genau_40 = "Director Consulting Services SAP (m/f/d)"
    assert len(genau_40) == 40
    assert _titel_kurz(genau_40) == genau_40


def test_titel_kurz_behaelt_wort_das_genau_an_der_grenze_endet():
    from pipeline.ingest import _titel_kurz

    titel = "Director Professional Services Germanyyy Nord"    # Wort endet bei Zeichen 40
    assert titel[40] == " "
    assert _titel_kurz(titel) == "Director Professional Services Germanyyy…"


def test_titel_kurz_ohne_leerzeichen_schneidet_hart_mit_auslassung():
    from pipeline.ingest import _titel_kurz

    kurz = _titel_kurz("X" * 60)
    assert kurz == "X" * 40 + "…"


def test_titel_kurz_entfernt_haengende_striche_und_ersetzt_trenner():
    from pipeline.ingest import _titel_kurz

    # „Government“ endet bei Zeichen 41 — Schnitt davor, der hängende Gedankenstrich fällt weg.
    assert _titel_kurz("Director Consulting Services – Government & Public Sector") \
        == "Director Consulting Services…"
    assert _titel_kurz("Head | of Sales") == "Head / of Sales"
    assert "\u201c" not in _titel_kurz("Leitung \u201eNeue Märkte\u201c (m/w/d)")
    assert len(_titel_kurz("Senior Manager Service Center Quality & Public (Person*)")) <= 41


def test_hinweise_mit_gekuerztem_titel_bleiben_fuer_beide_parser_lesbar():
    from pipeline.ingest import _neuausschreibung_hinweis, _titel_kurz

    vorgaenger = types.SimpleNamespace(
        id=429, title="Senior Manager Service Center Quality & Public (Person*)",
        status="Absage", found_date="2026-08-21")
    hinweis = _neuausschreibung_hinweis(vorgaenger)
    assert "„Senior Manager Service Center Quality…“" in hinweis, hinweis
    treffer = _PARSE_NEUAUSSCHREIBUNG.search(hinweis)
    assert treffer and treffer.group(1) == "429" and treffer.group(2).strip() == "Absage", hinweis

    nr = 383
    dublette = (f" | DUBLETTE? Job {nr} „{_titel_kurz('Director Consulting Services - Commercial Sector')}“ — "
                f"Text-Ähnlichkeit 53 % (geprüft 2026-09-18)")
    treffer = _PARSE_DUBLETTE.search(dublette)
    assert treffer and treffer.groups() == (str(nr), "53"), dublette

