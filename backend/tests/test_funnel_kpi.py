"""Tests für Phase 70, Stufe A (`app/gesamtprozess.py::funnel_kpi`) — der Gesamtprozess als
5-stufiger Trichter (Gesichtet -> Relevant -> Beworben -> Antworten -> Interviews),
s. tasks/spec_phase70_funnel_gesamtprozess.md.

Reine Funktion ohne DB-/FastAPI-Import (Muster `test_gesamtprozess.py`) — synthetische
Duck-Type-Objekte (`types.SimpleNamespace`) statt echter SQLModel-Rows/DB-Session. Kein
`app.*`-Import auf Modulebene (Konvention der Suite, s. conftest.py)."""
import types


def _job(id=1, status="Beworben", company_name="Firma X"):
    return types.SimpleNamespace(id=id, status=status, company_name=company_name)


def _application(id=1, job_id=100, status="Beworben", applied_date=None, created_at=None):
    import datetime
    return types.SimpleNamespace(
        id=id, job_id=job_id, status=status, applied_date=applied_date,
        created_at=created_at or datetime.datetime(2026, 1, 1),
    )


def _outreach(id=1, unternehmen="Firma X", kontakt="Kontakt X", bewerbung_datum=None,
              status="Initiated", antwort=None, antwort_datum=None, datum=None):
    return types.SimpleNamespace(
        id=id, unternehmen=unternehmen, kontakt=kontakt, bewerbung_datum=bewerbung_datum,
        status=status, antwort=antwort, antwort_datum=antwort_datum, datum=datum,
    )


def _interview(id=1, job_id=100, status="Absolviert", gegenueber=None, vor_ort=False):
    return types.SimpleNamespace(
        id=id, job_id=job_id, status=status, gegenueber=gegenueber, vor_ort=vor_ort,
    )


def _netzwerkgespraech(id=1, unternehmen="Firma Y", gegenueber=None, vor_ort=False):
    return types.SimpleNamespace(id=id, unternehmen=unternehmen, gegenueber=gegenueber, vor_ort=vor_ort)


def _email(job_id=100, direction="incoming", application_id=None, is_response=False,
           response_time_hours=None):
    return types.SimpleNamespace(
        job_id=job_id, direction=direction, application_id=application_id,
        is_response=is_response, response_time_hours=response_time_hours,
    )


def _leer():
    """Alle sechs Parameter leer -> alle Stufen 0, keine Exception (Basis-0-Fall)."""
    from app.gesamtprozess import funnel_kpi
    return funnel_kpi([], [], [], [], [], [])


# ═══════════════════════════════════════════════════════════════════════════════════════════
# Stufen-Zählung
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_stufe1_gesichtet_zaehlt_alle_jobs():
    from app.gesamtprozess import funnel_kpi

    jobs = [_job(id=i, status="Neu") for i in range(1, 6)]
    result = funnel_kpi(jobs, [], [], [], [], [])

    assert result["stufen"][0] == {
        "stufe": "Gesichtet", "anzahl": 5, "vs_vorstufe": None, "vs_start": 100.0,
        "kommentar": "Gesamter Pool aller erfassten Stellen",
    }


def test_stufe2_relevant_schliesst_die_drei_status_aus_status_none_zaehlt():
    from app.gesamtprozess import funnel_kpi

    jobs = [
        _job(id=1, status="Kein Match"),
        _job(id=2, status="Nicht verfügbar"),
        _job(id=3, status="Beirat abgelehnt"),
        _job(id=4, status="Beworben"),
        _job(id=5, status=None),   # NULL zählt als relevant
    ]
    result = funnel_kpi(jobs, [], [], [], [], [])

    assert result["stufen"][1]["anzahl"] == 2


def test_stufe3_beworben_nutzt_bewerbungen_kpi_nicht_neu_nachgebaut():
    """Beworben ruft bewerbungen_kpi() auf statt die Formel zu duplizieren — Beleg: Application
    im Status 'Vorbereitet' zählt NICHT (identisch zur Formel dort)."""
    from app.gesamtprozess import funnel_kpi

    jobs = [_job(id=1, status="Beworben")]
    apps = [
        _application(id=1, job_id=1, status="Beworben"),
        _application(id=2, job_id=1, status="Vorbereitet"),   # zählt NICHT
    ]
    outreach = [_outreach(id=1, bewerbung_datum="2026-05-01")]

    result = funnel_kpi(jobs, apps, [], outreach, [], [])

    assert result["stufen"][2]["anzahl"] == 2   # 1 Application + 1 Outreach
    assert result["stufen"][2]["kommentar"] == "1 Ausschreibungen + 1 über Netzwerk"


def test_stufe4_antworten_nutzt_response_kpis():
    from app.gesamtprozess import funnel_kpi

    jobs = [_job(id=1, status="Beworben")]
    apps = [_application(id=1, job_id=1, status="Beworben")]
    emails = [
        _email(job_id=1, application_id=1, is_response=True, response_time_hours=48.0),
        _email(job_id=1, application_id=1, is_response=True, response_time_hours=96.0),  # dedupliziert
    ]

    result = funnel_kpi(jobs, apps, emails, [], [], [])

    assert result["stufen"][3]["anzahl"] == 1   # EINE eindeutige Bewerbung, nicht 2 Mails


def test_stufe5_interviews_union_status_ohne_row():
    from app.gesamtprozess import funnel_kpi

    jobs = [_job(id=1, status="Interview")]   # Status gesetzt, aber KEINE Interview-Row
    result = funnel_kpi(jobs, [], [], [], [], [])

    assert result["stufen"][4]["anzahl"] == 1


def test_stufe5_interviews_union_row_ohne_status():
    from app.gesamtprozess import funnel_kpi

    jobs = [_job(id=1, status="Beworben")]   # Status NICHT 'Interview'
    interviews = [_interview(id=1, job_id=1, status="Geplant")]   # aber eine Interview-Row
    result = funnel_kpi(jobs, [], [], [], interviews, [])

    assert result["stufen"][4]["anzahl"] == 1


def test_stufe5_interviews_union_beides_zaehlt_als_ein_job():
    from app.gesamtprozess import funnel_kpi

    jobs = [_job(id=1, status="Interview")]
    interviews = [_interview(id=1, job_id=1, status="Absolviert")]
    result = funnel_kpi(jobs, [], [], [], interviews, [])

    assert result["stufen"][4]["anzahl"] == 1   # Union, keine Doppelzählung


# ═══════════════════════════════════════════════════════════════════════════════════════════
# Prozent-Rundung / Basis-0 / >100 %-Fall
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_prozente_werden_auf_eine_nachkommastelle_gerundet():
    from app.gesamtprozess import funnel_kpi

    jobs = [_job(id=i, status="Beworben") for i in range(1, 4)]   # 3 gesichtet, alle relevant
    result = funnel_kpi(jobs, [], [], [], [], [])

    # 3/3*100 = 100.0 (exakt) -- ein Fall mit Rundungsbedarf s. Live-Beleg (97/260=37.3...).
    assert result["stufen"][1]["vs_vorstufe"] == 100.0
    assert result["stufen"][1]["vs_start"] == 100.0


def test_basis_0_liefert_none_nie_zerodivision():
    result = _leer()

    for i, stufe in enumerate(result["stufen"]):
        if i > 0:
            assert stufe["vs_vorstufe"] is None
        assert stufe["vs_start"] is None
    assert result["engstellen"]["screening"] is None
    assert result["engstellen"]["groesster_verlust"] is None


def test_stufe3_kann_ueber_100_prozent_liegen_wird_nicht_gekappt():
    """Mixed-Basis (Spec-Fallstrick): Stufe 2 zählt Stellen, Stufe 3 Bewerbungen -- viele
    Netzwerk-Bewerbungen ggü. wenigen relevanten Stellen kann > 100 % ergeben. Muss angezeigt,
    NICHT gekappt werden."""
    from app.gesamtprozess import funnel_kpi

    jobs = [_job(id=1, status="Beworben")]   # 1 gesichtet, 1 relevant
    outreach = [_outreach(id=i, bewerbung_datum="2026-05-01") for i in range(1, 6)]   # 5 Netzwerk-Bewerbungen

    result = funnel_kpi(jobs, [], [], outreach, [], [])

    assert result["stufen"][2]["anzahl"] == 5
    assert result["stufen"][2]["vs_vorstufe"] == 500.0   # 5/1*100, UNGEKAPPT


# ═══════════════════════════════════════════════════════════════════════════════════════════
# groesster_verlust — Auswahl inkl. Gleichstand
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_groesster_verlust_waehlt_die_stufe_mit_dem_niedrigsten_vs_vorstufe():
    """Live-Beleg 29.07.2026: Antworten (19,1 %) ist der niedrigste vs_vorstufe-Wert unter den
    Stufen 2-5 -> 'Größter Verlust' zeigt exakt den in der Spec vorgegebenen Beispieltext."""
    from app.gesamtprozess import funnel_kpi

    jobs = [_job(id=i, status="Beworben") for i in range(1, 261)]
    for j in jobs[97:]:   # 260 - 97 = 163 auf "nicht relevant" setzen
        j.status = "Kein Match"
    apps = [_application(id=i, job_id=jobs[i - 1].id, status="Beworben") for i in range(1, 69)]
    outreach = []   # 68 Beworben komplett über Application, keine Netzwerk-Bewerbung nötig
    emails = []
    for i in range(1, 14):
        emails.append(_email(job_id=apps[i - 1].job_id, application_id=apps[i - 1].id,
                              is_response=True, response_time_hours=100.0))
    interviews = [_interview(id=i, job_id=apps[i - 1].job_id, status="Absolviert") for i in range(1, 5)]
    for iv in interviews:
        jobs[iv.job_id - 1].status = "Interview"

    result = funnel_kpi(jobs, apps, emails, outreach, interviews, [])

    assert result["stufen"][0]["anzahl"] == 260
    assert result["stufen"][1]["anzahl"] == 97
    assert result["stufen"][2]["anzahl"] == 68
    assert result["stufen"][3]["anzahl"] == 13
    assert result["stufen"][4]["anzahl"] == 4
    gv = result["engstellen"]["groesster_verlust"]
    assert gv["stufe"] == "Antworten"
    assert gv["prozent"] == 19.1
    assert gv["text"] == "Größter Verlust: Antwortquote 19,1 % auf 68 Bewerbungen"


def test_groesster_verlust_bei_gleichstand_gewinnt_die_erste_stufe():
    """Zwei Stufen mit demselben (niedrigsten) vs_vorstufe -- die im Trichter FRÜHERE Stufe
    gewinnt (dokumentierte Regel, s. funnel_kpi-Docstring)."""
    from app.gesamtprozess import funnel_kpi

    # 10 gesichtet, 5 relevant (Screening 50,0 %); 4 davon beworben (Bewerbungsquote 80,0 %);
    # 2 Antworten (Antwortquote 50,0 % -- Gleichstand mit Screening); 2 Interviews auf den
    # BEIDEN geantworteten Jobs (Interview-Konversion 100,0 %, klar über dem Gleichstand-Wert,
    # damit NICHT versehentlich diese Stufe den niedrigsten Wert stellt).
    jobs = [_job(id=i, status="Beworben") for i in range(1, 11)]
    for j in jobs[5:]:
        j.status = "Kein Match"   # 5 relevant von 10 -> Screening 50,0 %
    apps = [_application(id=i, job_id=jobs[i - 1].id, status="Beworben") for i in range(1, 5)]  # 4 beworben
    emails = [
        _email(job_id=apps[0].job_id, application_id=apps[0].id, is_response=True, response_time_hours=10.0),
        _email(job_id=apps[1].job_id, application_id=apps[1].id, is_response=True, response_time_hours=10.0),
    ]   # 2 von 4 Antworten -> Antwortquote 50,0 %
    jobs[0].status = "Interview"
    jobs[1].status = "Interview"   # 2 Interviews auf den 2 geantworteten Jobs -> Konversion 100 %

    result = funnel_kpi(jobs, apps, emails, [], [], [])

    # Beleg der Konstruktion: Screening/Antwortquote liegen beide bei 50,0 %, die anderen beiden
    # Kandidaten klar darüber.
    assert result["engstellen"]["screening"] == 50.0
    assert result["engstellen"]["bewerbungsquote"] == 80.0
    assert result["engstellen"]["antwortquote"] == 50.0
    assert result["engstellen"]["interview_konversion"] == 100.0
    # Screening (Stufe 2) kommt im Trichter VOR Antwortquote (Stufe 4) -> gewinnt bei Gleichstand.
    assert result["engstellen"]["groesster_verlust"]["stufe"] == "Relevant"


# ═══════════════════════════════════════════════════════════════════════════════════════════
# Rückgabe-Vertrag
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_rueckgabe_hat_fuenf_stufen_und_alle_engstellen_schluessel():
    result = _leer()

    assert len(result["stufen"]) == 5
    assert [s["stufe"] for s in result["stufen"]] == [
        "Gesichtet", "Relevant", "Beworben", "Antworten", "Interviews",
    ]
    assert set(result["engstellen"].keys()) == {
        "screening", "bewerbungsquote", "antwortquote", "interview_konversion",
        "ende_zu_ende", "groesster_verlust",
    }
