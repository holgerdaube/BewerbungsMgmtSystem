"""Phase 85 — neuer Job-Status „Keine Rückmeldung" (Ghosting-Endstatus, manuell gesetzt,
s. tasks/spec_phase85_status_keine_rueckmeldung.md). Deckt die Backend-Anteile der Stufe E ab:

  E.1  ALLOWED_JOB_STATUSES enthält den Wert; PATCH damit -> 200, ein Tippfehler -> 422.
  E.2  TERMINAL_STATUSES enthält ihn -> ein Job damit taucht NICHT in der Follow-up-Liste auf.
  E.3  Funnel: ein Job mit dem Status zählt weiter als "relevant" (Stufe 2) und NICHT als Absage.
  E.4  Excel: Export mit einem Job in diesem Status läuft durch (kein KeyError in
       STATUS_FARBEN) und färbt die Zeile.
  E.5  Vorschlagsliste (`keine_reaktion_kpi`): Job "Beworben" + 60 Tage alt + keine eingehende
       Mail -> in der Liste; MIT eingehender Mail -> nicht; 10 Tage alt -> nicht. PLUS der
       zentrale Regressionsbeleg: derselbe 60-Tage-Job mit Status "Keine Rückmeldung" zählt
       WEITERHIN, die Zahl bleibt identisch (das ist der ganze Zweck der Phase).
  E.6  norm_status("keine Rückmeldung") -> "Keine Rückmeldung" (nicht "Kein Match").

Wie in conftest.py vorgesehen: KEINE app.*-/pipeline.*-Importe auf Modulebene, alles
funktionslokal. Reine KPI-Tests (E.3/E.5/E.6) nutzen synthetische `types.SimpleNamespace`-Rows
wie test_gesamtprozess.py (kein DB-Import nötig); E.1/E.2/E.4 brauchen `client`/`session`/`seed`
aus conftest.py (T3 — nie echte Live-Daten, eigene uuid-Suffix-Firmennamen)."""
import types
import uuid
from datetime import date, timedelta

HEUTE = date(2026, 8, 19)


def _job(id=1, status="Beworben", company_name="Firma X"):
    return types.SimpleNamespace(id=id, status=status, company_name=company_name)


def _application(id=1, job_id=100, status="Beworben", applied_date=None, created_at=None):
    return types.SimpleNamespace(
        id=id, job_id=job_id, status=status, applied_date=applied_date,
        created_at=created_at,
    )


def _email(job_id=100, direction="incoming"):
    return types.SimpleNamespace(job_id=job_id, direction=direction)


def _neuer_job(session, status, **felder):
    """Job mit garantiert eindeutigem Namen/dedup_key in der geteilten tmp-DB (Muster
    test_export_excel_stellen.py)."""
    from app.models import Company, Job

    suffix = uuid.uuid4().hex[:8]
    firma = f"P85 Testfirma {suffix}"
    c = Company(name=firma)
    session.add(c)
    session.commit()
    session.refresh(c)
    j = Job(company_id=c.id, company_name=firma, title=felder.pop("title", "Head of Delivery"),
            status=status, found_date=date.today().isoformat(),
            dedup_key=f"p85|{suffix}", match_score=felder.pop("match_score", 3), **felder)
    session.add(j)
    session.commit()
    session.refresh(j)
    return j


# ═══════════════════════════════════════════════════════════════════════════════════════════
# E.1 — ALLOWED_JOB_STATUSES / PATCH
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_allowed_job_statuses_enthaelt_keine_rueckmeldung():
    from app.main import ALLOWED_JOB_STATUSES

    assert "Keine Rückmeldung" in ALLOWED_JOB_STATUSES


def test_patch_job_mit_keine_rueckmeldung_liefert_200(client, seed):
    job = seed["jobs"][0]
    resp = client.patch(f"/api/jobs/{job.id}", json={"status": "Keine Rückmeldung"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "Keine Rückmeldung"


def test_patch_job_mit_tippfehler_liefert_422(client, seed):
    job = seed["jobs"][0]
    resp = client.patch(f"/api/jobs/{job.id}", json={"status": "Keine Rückmeldun"})
    assert resp.status_code == 422, resp.text


# ═══════════════════════════════════════════════════════════════════════════════════════════
# E.2 — TERMINAL_STATUSES / Follow-up-Liste
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_terminal_statuses_enthaelt_keine_rueckmeldung():
    from app.main import TERMINAL_STATUSES

    assert "Keine Rückmeldung" in TERMINAL_STATUSES


def test_terminal_statuses_dupikate_konsistent():
    """Die drei Duplikate (main.py/ingest.py/dedup_text.py, dokumentierter Grund: main.py darf
    nicht importiert werden) UND export_excel.py's eigene Kopie müssen alle denselben Wert
    kennen — sonst driftet genau die Fehlerklasse zurück, die die main.py-Kommentare
    beschreiben."""
    from app.main import TERMINAL_STATUSES as MAIN_TS
    from pipeline.ingest import _TERMINAL_STATUSES as INGEST_TS
    from pipeline.dedup_text import _TERMINAL_STATUSES as DEDUP_TS
    from pipeline.export_excel import TERMINAL_STATUSES as EXCEL_TS

    for ts in (MAIN_TS, INGEST_TS, DEDUP_TS, EXCEL_TS):
        assert "Keine Rückmeldung" in ts


def test_job_mit_keine_rueckmeldung_nicht_in_followup_liste(client, seed):
    """Ein Job mit Fälligkeitsdatum, der auf 'Keine Rückmeldung' steht, ist terminal — er darf
    NICHT mehr unter /api/followups auftauchen (Follow-up ist gegenstandslos, Entscheidung 1)."""
    job = seed["jobs"][0]
    morgen = (date.today() + timedelta(days=1)).isoformat()
    resp = client.patch(f"/api/jobs/{job.id}",
                        json={"status": "Keine Rückmeldung", "follow_up_date": morgen})
    assert resp.status_code == 200, resp.text

    fu = client.get("/api/followups").json()
    ids = {row["id"] for row in fu["jobs"]}
    assert job.id not in ids


def test_job_mit_beworben_bleibt_in_followup_liste_zum_vergleich(client, seed):
    """Gegenprobe: derselbe Aufbau mit 'Beworben' (nicht terminal) taucht weiterhin auf —
    zeigt, dass der Ausschluss oben tatsächlich am neuen Status liegt, nicht an follow_up_date
    generell."""
    job = seed["jobs"][1]
    morgen = (date.today() + timedelta(days=1)).isoformat()
    resp = client.patch(f"/api/jobs/{job.id}",
                        json={"status": "Beworben", "follow_up_date": morgen})
    assert resp.status_code == 200, resp.text

    fu = client.get("/api/followups").json()
    ids = {row["id"] for row in fu["jobs"]}
    assert job.id in ids


# ═══════════════════════════════════════════════════════════════════════════════════════════
# E.3 — Funnel: weiterhin "relevant", NICHT "Absage"
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_keine_rueckmeldung_zaehlt_nicht_in_nicht_relevant_status():
    """Entscheidung 2 der Spec, wörtlich: NICHT in _NICHT_RELEVANT_STATUS aufnehmen — die
    Stelle WAR relevant und wurde beworben."""
    from app.gesamtprozess import _NICHT_RELEVANT_STATUS

    assert "Keine Rückmeldung" not in _NICHT_RELEVANT_STATUS


def test_funnel_stufe_relevant_zaehlt_keine_rueckmeldung_mit():
    from app.gesamtprozess import funnel_kpi

    jobs = [
        _job(id=1, status="Keine Rückmeldung"),
        _job(id=2, status="Kein Match"),   # zählt NICHT als relevant
    ]
    result = funnel_kpi(jobs, [], [], [], [], [])
    relevant_stufe = next(s for s in result["stufen"] if s["stufe"] == "Relevant")

    assert relevant_stufe["anzahl"] == 1


def test_absagen_kpi_zaehlt_keine_rueckmeldung_nicht_als_absage():
    """Entscheidung 3: absagen_kpi() vergleicht exakt == 'Absage' — Ghosting ist keine Absage
    AN den Nutzer."""
    from app.gesamtprozess import absagen_kpi

    jobs = [_job(id=1, status="Keine Rückmeldung"), _job(id=2, status="Absage")]
    result = absagen_kpi(jobs, [])

    assert result["wert"] == 1
    assert result["splits"] == {"Ausschreibungen": 1, "Netzwerk": 0}


# ═══════════════════════════════════════════════════════════════════════════════════════════
# E.4 — Excel-Export: kein KeyError, Zeile korrekt eingefärbt
# ═══════════════════════════════════════════════════════════════════════════════════════════
def _export(tmp_path, monkeypatch):
    from pipeline import export_excel
    import openpyxl

    monkeypatch.setattr(export_excel, "EXPORT_DIR", tmp_path)
    return openpyxl.load_workbook(export_excel.build_workbook())


def test_excel_status_farben_enthaelt_keine_rueckmeldung():
    from pipeline.export_excel import STATUS_FARBEN

    assert STATUS_FARBEN["Keine Rückmeldung"] == ("7A5C5C", "FFFFFF")


def test_excel_keine_rueckmeldung_steht_im_stellen_blatt_nicht_im_aussortierten():
    """Zuordnungs-Entscheidung (Hauptsession-Korrektur, 18.08.): „Keine Rückmeldung" ist das
    Ergebnis einer ERFOLGTEN Bewerbung — wie „Absage" — und gehört deshalb ins Blatt „Stellen"
    (PIPELINE_ORDER). Das Aussortiert-Blatt beantwortet „warum wurde die Stelle aussortiert?"
    (Spalte „Grund") und sammelt Stellen, auf die nie beworben wurde; dort stünde für einen
    Ghosting-Fall sinnlos „Begründung offen"."""
    from pipeline.export_excel import AUSSORTIERT, PIPELINE_ORDER

    assert "Keine Rückmeldung" in PIPELINE_ORDER
    assert "Keine Rückmeldung" not in AUSSORTIERT


def test_excel_export_mit_keine_rueckmeldung_laeuft_ohne_keyerror(session, seed, tmp_path, monkeypatch):
    """Der eigentliche Testfall aus der Spec (Fallstrick): STATUS_FARBEN[status] ist im
    Stellen-Blatt sowohl für die Gruppenüberschrift als auch in `_job_zeile` ein Direktzugriff
    OHNE Fallback — fehlt der Schlüssel, bricht der Export mit KeyError. Läuft build_workbook()
    durch und trägt die Gruppe die richtige Farbe, ist der Schlüssel überall vorhanden."""
    j = _neuer_job(session, "Keine Rückmeldung")

    wb = _export(tmp_path, monkeypatch)  # wirft KeyError, falls STATUS_FARBEN den Schlüssel nicht hätte
    ws = wb["Stellen"]

    # Gruppenüberschrift „Keine Rückmeldung  (n)" mit der Phase-85-Farbe
    kopf = [r for r in range(2, ws.max_row + 1)
            if str(ws.cell(row=r, column=1).value or "").startswith("Keine Rückmeldung  (")]
    assert len(kopf) == 1, f"Statusgruppe fehlt im Stellen-Blatt: {kopf}"
    kopf_zelle = ws.cell(row=kopf[0], column=1)
    assert kopf_zelle.fill.fgColor.rgb.endswith("7A5C5C")
    assert kopf_zelle.font.color.rgb.endswith("FFFFFF")

    # ... und die Job-Zeile selbst steht darunter
    treffer = [r for r in range(kopf[0] + 1, ws.max_row + 1)
               if ws.cell(row=r, column=1).value == j.company_name]
    assert len(treffer) == 1, f"Job nicht unter seiner Statusgruppe gefunden: {treffer}"


def test_excel_dashboard_pipeline_block_zeigt_keine_rueckmeldung(session, seed, tmp_path, monkeypatch):
    """`PIPELINE_ORDER + AUSSORTIERT` (Blatt Dashboard, "Pipeline — Stellen je Status") muss den
    neuen Status ebenfalls mitliefern, sonst fehlt genau die Zeile im Gesamtüberblick."""
    _neuer_job(session, "Keine Rückmeldung")

    wb = _export(tmp_path, monkeypatch)
    ws = wb["Dashboard"]
    werte = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
    assert "Keine Rückmeldung" in werte


# ═══════════════════════════════════════════════════════════════════════════════════════════
# E.5 — Vorschlagsliste (`keine_reaktion_kpi`) — der kritische Regressionsbeleg
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_beworben_60_tage_ohne_mail_zaehlt_in_vorschlagsliste():
    from app.gesamtprozess import keine_reaktion_kpi

    jobs = [_job(id=1, status="Beworben", company_name="Firma Sechzig Tage")]
    apps = [_application(id=1, job_id=1, applied_date=(HEUTE - timedelta(days=60)).isoformat())]

    result = keine_reaktion_kpi(jobs, [], apps, [], heute=HEUTE)

    assert result["wert"] == 1
    assert result["splits"]["Ausschreibungen"] == 1


def test_beworben_60_tage_mit_eingehender_mail_zaehlt_nicht():
    from app.gesamtprozess import keine_reaktion_kpi

    jobs = [_job(id=1, status="Beworben")]
    apps = [_application(id=1, job_id=1, applied_date=(HEUTE - timedelta(days=60)).isoformat())]
    emails = [_email(job_id=1, direction="incoming")]

    result = keine_reaktion_kpi(jobs, emails, apps, [], heute=HEUTE)

    assert result["wert"] == 0


def test_beworben_10_tage_zaehlt_nicht_schwelle_nicht_erreicht():
    from app.gesamtprozess import keine_reaktion_kpi

    jobs = [_job(id=1, status="Beworben")]
    apps = [_application(id=1, job_id=1, applied_date=(HEUTE - timedelta(days=10)).isoformat())]

    result = keine_reaktion_kpi(jobs, [], apps, [], heute=HEUTE)

    assert result["wert"] == 0


def test_regressionsbeleg_umstellung_auf_keine_rueckmeldung_haelt_kpi_konstant():
    """DER zentrale Regressionstest der Phase (Spec-Fallstrick, Verifikationspunkt 3 des
    Auftrags): ein Job 'Beworben', 60 Tage alt, keine eingehende Mail zählt in
    keine_reaktion_kpi(). Stellt der Nutzer denselben Job auf 'Keine Rückmeldung' um, MUSS die Zahl
    GLEICH bleiben (nicht sinken) — sonst würde der neue Status genau die Arbeit, die er
    sichtbar machen soll, wieder unsichtbar machen."""
    from app.gesamtprozess import keine_reaktion_kpi

    apps = [_application(id=1, job_id=1, applied_date=(HEUTE - timedelta(days=60)).isoformat())]

    vorher = keine_reaktion_kpi(
        [_job(id=1, status="Beworben", company_name="Firma Ghosting")], [], apps, [], heute=HEUTE)
    nachher = keine_reaktion_kpi(
        [_job(id=1, status="Keine Rückmeldung", company_name="Firma Ghosting")], [], apps, [], heute=HEUTE)

    assert vorher["wert"] == 1
    assert nachher["wert"] == 1
    assert vorher["wert"] == nachher["wert"]
    assert nachher["rows"][0]["label"] == "Firma Ghosting"
    assert nachher["rows"][0]["tage"] == 60


def test_keine_rueckmeldung_zaehlt_unabhaengig_vom_alter_mit():
    """Für den neuen Status gilt die 14-Tage-Schwelle NICHT (Entscheidung 5) — selbst ein erst
    vor 2 Tagen manuell umgestellter Job zählt sofort mit, während derselbe Job unter 'Beworben'
    (unterhalb der Schwelle) noch nicht zählen würde."""
    from app.gesamtprozess import keine_reaktion_kpi

    apps = [_application(id=1, job_id=1, applied_date=(HEUTE - timedelta(days=2)).isoformat())]

    als_beworben = keine_reaktion_kpi(
        [_job(id=1, status="Beworben")], [], apps, [], heute=HEUTE)
    als_keine_rueckmeldung = keine_reaktion_kpi(
        [_job(id=1, status="Keine Rückmeldung")], [], apps, [], heute=HEUTE)

    assert als_beworben["wert"] == 0          # unter der 14-Tage-Schwelle
    assert als_keine_rueckmeldung["wert"] == 1  # Schwelle gegenstandslos für diesen Status


def test_keine_rueckmeldung_mit_eingehender_mail_zaehlt_trotzdem_nicht():
    """Die Mail-Bedingung bleibt für BEIDE Status unverändert (nur Status-Filter und
    Alters-Schwelle wurden laut Spec angepasst, sonst nichts)."""
    from app.gesamtprozess import keine_reaktion_kpi

    apps = [_application(id=1, job_id=1, applied_date=(HEUTE - timedelta(days=60)).isoformat())]
    emails = [_email(job_id=1, direction="incoming")]

    result = keine_reaktion_kpi(
        [_job(id=1, status="Keine Rückmeldung")], emails, apps, [], heute=HEUTE)

    assert result["wert"] == 0


# ═══════════════════════════════════════════════════════════════════════════════════════════
# E.6 — norm_status()
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_norm_status_erkennt_keine_rueckmeldung():
    from app.normalize import norm_status

    normalisiert, roh = norm_status("keine Rückmeldung")
    assert normalisiert == "Keine Rückmeldung"


def test_norm_status_erkennt_ascii_schreibweise():
    from app.normalize import norm_status

    normalisiert, _ = norm_status("keine rueckmeldung erhalten")
    assert normalisiert == "Keine Rückmeldung"


def test_norm_status_erkennt_weitere_muster():
    from app.normalize import norm_status

    for text in ("nie geantwortet", "klassisches Ghosting", "no response erhalten"):
        normalisiert, _ = norm_status(text)
        assert normalisiert == "Keine Rückmeldung", f"{text!r} -> {normalisiert!r}"


def test_norm_status_geht_nicht_vorher_ins_kein_match_netz():
    """Der eigentliche Grund für die Einsortierung VOR dem Kein-Match-Zweig: dessen breite
    Stichwortliste würde sonst zuerst greifen (s. Spec-Vorgabe explizit)."""
    from app.normalize import norm_status

    normalisiert, _ = norm_status("keine Rückmeldung")
    assert normalisiert != "Kein Match"
