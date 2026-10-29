"""Tests für Phase 69 Stufe A (`app/gesamtprozess.py`) — die vier KPI-Formeln für das Dashboard
„Gesamtprozess seit Beginn" (Bewerbungen · Gespräche · Absagen · Keine Reaktion,
s. tasks/spec_phase69_gesamtprozess_kpis.md, Entscheidung 2).

Reine Funktionen ohne DB-/FastAPI-Import (Muster `response_metrics.py` /
test_response_rate_dedup.py) — deshalb hier synthetische Duck-Type-Objekte
(`types.SimpleNamespace`) statt echter SQLModel-Rows/DB-Session. Jede Test-Factory setzt genau
die Attribute, die `gesamtprozess.py` tatsächlich liest (direkter Attributzugriff, kein
`getattr(..., default)` — die Funktionen erwarten vollständige Row-artige Objekte, wie sie eine
echte DB-Query immer liefert).

Kein `app.*`-Import auf Modulebene nötig (anders als bei DB-gestützten Testdateien) — dieses
Modul selbst hat keine App-Abhängigkeit; die Imports stehen trotzdem funktionslokal in den
Testfunktionen, Konvention der Suite."""
import types
from datetime import date, datetime, timedelta

HEUTE = date(2026, 7, 27)   # fester Stichtag statt date.today() — deterministische Tests


def _application(id=1, job_id=100, status="Beworben", applied_date=None, created_at=None):
    return types.SimpleNamespace(
        id=id, job_id=job_id, status=status, applied_date=applied_date,
        created_at=created_at or datetime(2026, 1, 1),
    )


def _outreach(id=1, unternehmen="Firma X", kontakt="Kontakt X", bewerbung_datum=None,
              status="Initiated", antwort=None, antwort_datum=None, datum=None):
    return types.SimpleNamespace(
        id=id, unternehmen=unternehmen, kontakt=kontakt, bewerbung_datum=bewerbung_datum,
        status=status, antwort=antwort, antwort_datum=antwort_datum, datum=datum,
    )


def _job(id=1, status="Beworben", company_name="Firma X"):
    return types.SimpleNamespace(id=id, status=status, company_name=company_name)


def _interview(id=1, job_id=100, status="Absolviert", gegenueber=None, vor_ort=False):
    return types.SimpleNamespace(
        id=id, job_id=job_id, status=status, gegenueber=gegenueber, vor_ort=vor_ort,
    )


def _netzwerkgespraech(id=1, unternehmen="Firma Y", gegenueber=None, vor_ort=False):
    return types.SimpleNamespace(id=id, unternehmen=unternehmen, gegenueber=gegenueber, vor_ort=vor_ort)


def _email(job_id=100, direction="incoming"):
    return types.SimpleNamespace(job_id=job_id, direction=direction)


# ═══════════════════════════════════════════════════════════════════════════════════════════
# KPI 1 — Bewerbungen gesamt
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_bewerbungen_kpi_zaehlt_application_ausser_vorbereitet():
    from app.gesamtprozess import bewerbungen_kpi

    apps = [
        _application(id=1, status="Beworben"),
        _application(id=2, status="Absage"),
        _application(id=3, status="Interview"),
        _application(id=4, status="Vorbereitet"),   # zählt NICHT
    ]
    result = bewerbungen_kpi(apps, [])

    assert result["wert"] == 3
    assert result["splits"] == {"Positionsausschreibungen": 3, "Netzwerk": 0}


def test_bewerbungen_kpi_application_ohne_applied_date_zaehlt_trotzdem():
    """Status ist das alleinige Kriterium — ein fehlendes applied_date schließt NICHT aus
    (Spec-Entscheidung 2, wörtlich: 'applied_date-los zählt trotzdem')."""
    from app.gesamtprozess import bewerbungen_kpi

    apps = [_application(id=1, status="Beworben", applied_date=None)]
    result = bewerbungen_kpi(apps, [])

    assert result["wert"] == 1


def test_bewerbungen_kpi_zaehlt_outreach_mit_bewerbung_datum():
    from app.gesamtprozess import bewerbungen_kpi

    outreach = [
        _outreach(id=1, bewerbung_datum="2026-05-01"),
        _outreach(id=2, bewerbung_datum=None),   # zählt NICHT
    ]
    result = bewerbungen_kpi([], outreach)

    assert result["wert"] == 1
    assert result["splits"] == {"Positionsausschreibungen": 0, "Netzwerk": 1}


def test_bewerbungen_kpi_application_und_outreach_bewerbung_werden_nicht_dedupliziert():
    """Kern-Anforderung der Spec: eine Outreach-Bewerbung (bewerbung_datum gesetzt) UND eine
    Application zur selben faktischen Bewerbung zählen BEIDE — die Doppelzählungs-Vermeidung ist
    laut Spec eine PFLEGE-Regel (Backfill-Disziplin/UI-Tooltip), keine Code-Automatik."""
    from app.gesamtprozess import bewerbungen_kpi

    apps = [_application(id=1, job_id=100, status="Beworben")]
    outreach = [_outreach(id=1, unternehmen="Firma X", bewerbung_datum="2026-05-01")]

    result = bewerbungen_kpi(apps, outreach)

    assert result["wert"] == 2   # KEINE Dedup — beide Quellen zählen unabhängig
    assert result["splits"] == {"Positionsausschreibungen": 1, "Netzwerk": 1}
    assert len(result["rows"]) == 2


# ═══════════════════════════════════════════════════════════════════════════════════════════
# KPI 2 — Gespräche gesamt
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_gespraeche_kpi_zaehlt_nur_absolvierte_interviews():
    from app.gesamtprozess import gespraeche_kpi

    interviews = [
        _interview(id=1, status="Absolviert"),
        _interview(id=2, status="Geplant"),   # zählt NICHT
        _interview(id=3, status="Abgesagt"),  # zählt NICHT
    ]
    result = gespraeche_kpi(interviews, [])

    assert result["wert"] == 1


def test_gespraeche_kpi_zaehlt_alle_netzwerkgespraeche():
    from app.gesamtprozess import gespraeche_kpi

    ng = [_netzwerkgespraech(id=1), _netzwerkgespraech(id=2)]
    result = gespraeche_kpi([], ng)

    assert result["wert"] == 2


def test_gespraeche_kpi_splittet_nach_gegenueber():
    from app.gesamtprozess import gespraeche_kpi

    interviews = [
        _interview(id=1, gegenueber="Recruiter"),
        _interview(id=2, gegenueber="Hiring Manager"),
        _interview(id=3, gegenueber="Headhunter"),
        _interview(id=4, gegenueber=None),          # -> Sammel-Bucket
        _interview(id=5, gegenueber="Fachbereich"),  # -> Sammel-Bucket
    ]
    ng = [_netzwerkgespraech(id=10, gegenueber="Netzwerk")]  # -> Sammel-Bucket (kein eigener Split)

    result = gespraeche_kpi(interviews, ng)

    assert result["splits"]["Recruiter (Firma)"] == 1
    assert result["splits"]["Hiring Manager"] == 1
    assert result["splits"]["Headhunter"] == 1
    assert result["splits"]["Fachbereich/Sonstige"] == 3
    assert result["wert"] == 6


def test_gespraeche_kpi_vor_ort_split_ueber_beide_quellen():
    """Querschnitt 'davon vor Ort' zählt vor_ort=True aus Interview UND NetzwerkGespraech
    zusammen (Spec-Entscheidung 2: 'vor_ort beider Quellen')."""
    from app.gesamtprozess import gespraeche_kpi

    interviews = [
        _interview(id=1, vor_ort=True),
        _interview(id=2, vor_ort=False),
    ]
    ng = [
        _netzwerkgespraech(id=10, vor_ort=True),
        _netzwerkgespraech(id=11, vor_ort=True),
        _netzwerkgespraech(id=12, vor_ort=False),
    ]
    result = gespraeche_kpi(interviews, ng)

    assert result["splits"]["davon_vor_Ort"] == 3
    assert result["wert"] == 5   # vor_ort ist Querschnitt, KEIN zusätzlicher Bucket-Zähler


# ═══════════════════════════════════════════════════════════════════════════════════════════
# KPI 3 — Absagen gesamt
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_absagen_kpi_zaehlt_job_absage_aber_nicht_beirat_abgelehnt():
    """Terminal-Status wie 'Beirat abgelehnt' (Eigenentscheidung) sind KEINE Absage an den Nutzer und
    zählen bewusst nicht — ebenso 'Kein Match'/'Nicht verfügbar' (Spec-Entscheidung 2)."""
    from app.gesamtprozess import absagen_kpi

    jobs = [
        _job(id=1, status="Absage"),
        _job(id=2, status="Beirat abgelehnt"),
        _job(id=3, status="Kein Match"),
        _job(id=4, status="Nicht verfügbar"),
        _job(id=5, status="Beworben"),
    ]
    result = absagen_kpi(jobs, [])

    assert result["wert"] == 1
    assert result["splits"] == {"Ausschreibungen": 1, "Netzwerk": 0}


def test_absagen_kpi_zaehlt_outreach_closed_negative():
    from app.gesamtprozess import absagen_kpi

    outreach = [
        _outreach(id=1, status="Closed Negative"),
        _outreach(id=2, status="In Dialogue"),   # zählt NICHT
        _outreach(id=3, status="On Hold"),       # zählt NICHT
    ]
    result = absagen_kpi([], outreach)

    assert result["wert"] == 1
    assert result["splits"] == {"Ausschreibungen": 0, "Netzwerk": 1}


# ═══════════════════════════════════════════════════════════════════════════════════════════
# KPI 4 — Keine Reaktion (Schwelle KEINE_REAKTION_TAGE = 14, Grenzfälle 13/15 Tage)
# ═══════════════════════════════════════════════════════════════════════════════════════════
def test_keine_reaktion_konstante_ist_14_tage():
    from app.gesamtprozess import KEINE_REAKTION_TAGE
    assert KEINE_REAKTION_TAGE == 14


def test_keine_reaktion_ausschreibung_grenzfall_13_tage_zaehlt_nicht():
    from app.gesamtprozess import keine_reaktion_kpi

    jobs = [_job(id=1, status="Beworben")]
    apps = [_application(id=1, job_id=1, applied_date=(HEUTE - timedelta(days=13)).isoformat())]

    result = keine_reaktion_kpi(jobs, [], apps, [], heute=HEUTE)

    assert result["wert"] == 0
    assert result["splits"]["Ausschreibungen"] == 0


def test_keine_reaktion_ausschreibung_grenzfall_15_tage_zaehlt():
    from app.gesamtprozess import keine_reaktion_kpi

    jobs = [_job(id=1, status="Beworben", company_name="Firma X")]
    apps = [_application(id=1, job_id=1, applied_date=(HEUTE - timedelta(days=15)).isoformat())]

    result = keine_reaktion_kpi(jobs, [], apps, [], heute=HEUTE)

    assert result["wert"] == 1
    assert result["splits"]["Ausschreibungen"] == 1
    assert result["rows"][0] == {
        "id": 1, "label": "Firma X", "kanal": "Ausschreibung", "tage": 15,
    }


def test_keine_reaktion_ausschreibung_mit_eingehender_mail_zaehlt_nicht():
    """Eine eingehende Mail zum Job (egal welcher Kategorie) widerlegt 'keine Reaktion' —
    selbst wenn die Bewerbung längst über der Schwelle liegt."""
    from app.gesamtprozess import keine_reaktion_kpi

    jobs = [_job(id=1, status="Beworben")]
    apps = [_application(id=1, job_id=1, applied_date=(HEUTE - timedelta(days=30)).isoformat())]
    emails = [_email(job_id=1, direction="incoming")]

    result = keine_reaktion_kpi(jobs, emails, apps, [], heute=HEUTE)

    assert result["wert"] == 0


def test_keine_reaktion_ausschreibung_nur_status_beworben_relevant():
    from app.gesamtprozess import keine_reaktion_kpi

    jobs = [_job(id=1, status="Absage")]   # nicht 'Beworben' -> irrelevant für diese KPI
    apps = [_application(id=1, job_id=1, applied_date=(HEUTE - timedelta(days=30)).isoformat())]

    result = keine_reaktion_kpi(jobs, [], apps, [], heute=HEUTE)

    assert result["wert"] == 0


def test_keine_reaktion_ausschreibung_faellt_auf_created_at_zurueck():
    """Fehlt applied_date, zählt ersatzweise created_at (Spec-Entscheidung 2)."""
    from app.gesamtprozess import keine_reaktion_kpi

    jobs = [_job(id=1, status="Beworben")]
    alt_datum = datetime.combine(HEUTE - timedelta(days=20), datetime.min.time())
    apps = [_application(id=1, job_id=1, applied_date=None, created_at=alt_datum)]

    result = keine_reaktion_kpi(jobs, [], apps, [], heute=HEUTE)

    assert result["wert"] == 1


def test_keine_reaktion_ausschreibung_ohne_jede_bewerbung_zaehlt_defensiv_nicht():
    """Kein Application-Row zu diesem Job -> kein bestimmbares Alter -> zählt NICHT (defensiv,
    nie raten/crashen)."""
    from app.gesamtprozess import keine_reaktion_kpi

    jobs = [_job(id=1, status="Beworben")]

    result = keine_reaktion_kpi(jobs, [], [], [], heute=HEUTE)

    assert result["wert"] == 0


def test_keine_reaktion_ausschreibung_unparsebares_applied_date_crasht_nicht_faellt_auf_created_at_zurueck():
    """Garbage-Text in applied_date darf NIE crashen. Application.created_at ist ein
    Pflichtfeld (immer ein echtes datetime, s. models.py) — der Fallback greift deshalb hier
    zuverlässig: ein FRISCHES created_at (< Schwelle) sorgt dafür, dass der Job trotz
    unparsebarem applied_date NICHT als 'keine Reaktion' zählt."""
    from app.gesamtprozess import keine_reaktion_kpi

    jobs = [_job(id=1, status="Beworben")]
    frisch = datetime.combine(HEUTE - timedelta(days=5), datetime.min.time())
    apps = [_application(id=1, job_id=1, applied_date="irgendwas-kein-datum", created_at=frisch)]

    result = keine_reaktion_kpi(jobs, [], apps, [], heute=HEUTE)   # darf nicht werfen

    assert result["wert"] == 0


def test_keine_reaktion_netzwerk_grenzfall_13_und_15_tage():
    from app.gesamtprozess import keine_reaktion_kpi

    outreach = [
        _outreach(id=1, status="Initiated", antwort=None,
                  datum=(HEUTE - timedelta(days=13)).isoformat()),   # zählt NICHT
        _outreach(id=2, status="Initiated", antwort=None,
                  datum=(HEUTE - timedelta(days=15)).isoformat()),   # zählt
    ]

    result = keine_reaktion_kpi([], [], [], outreach, heute=HEUTE)

    assert result["wert"] == 1
    assert result["splits"]["Netzwerk"] == 1
    assert result["rows"][0]["id"] == 2
    assert result["rows"][0]["tage"] == 15


def test_keine_reaktion_netzwerk_antwort_ja_zaehlt_nicht():
    from app.gesamtprozess import keine_reaktion_kpi

    outreach = [_outreach(id=1, status="Initiated", antwort="Ja",
                          datum=(HEUTE - timedelta(days=30)).isoformat())]

    result = keine_reaktion_kpi([], [], [], outreach, heute=HEUTE)

    assert result["wert"] == 0


def test_keine_reaktion_netzwerk_nur_initiated_und_on_hold_relevant():
    from app.gesamtprozess import keine_reaktion_kpi

    outreach = [
        _outreach(id=1, status="In Dialogue", antwort=None,
                  datum=(HEUTE - timedelta(days=30)).isoformat()),   # zählt NICHT
        _outreach(id=2, status="On Hold", antwort="Nein",
                  datum=(HEUTE - timedelta(days=30)).isoformat()),   # zählt
        _outreach(id=3, status="Closed Negative", antwort=None,
                  datum=(HEUTE - timedelta(days=30)).isoformat()),   # zählt NICHT (kein Initiated/On Hold)
    ]

    result = keine_reaktion_kpi([], [], [], outreach, heute=HEUTE)

    assert result["wert"] == 1
    assert result["rows"][0]["id"] == 2


def test_keine_reaktion_netzwerk_nutzt_antwort_datum_vor_datum():
    """'letzte Aktivität' bevorzugt antwort_datum vor datum (Spec-Entscheidung 2)."""
    from app.gesamtprozess import keine_reaktion_kpi

    # datum liegt weit zurück (würde für sich allein zählen), antwort_datum ist frisch (< 14 Tage)
    # -> antwort_datum gewinnt, KEINE Reaktion-Kandidat.
    outreach = [_outreach(
        id=1, status="Initiated", antwort="Nein",
        datum=(HEUTE - timedelta(days=100)).isoformat(),
        antwort_datum=(HEUTE - timedelta(days=1)).isoformat(),
    )]

    result = keine_reaktion_kpi([], [], [], outreach, heute=HEUTE)

    assert result["wert"] == 0


def test_keine_reaktion_netzwerk_unparsebares_datum_crasht_nicht():
    from app.gesamtprozess import keine_reaktion_kpi

    outreach = [_outreach(id=1, status="Initiated", antwort=None, datum="nicht-iso")]

    result = keine_reaktion_kpi([], [], [], outreach, heute=HEUTE)   # darf nicht werfen

    assert result["wert"] == 0


def test_keine_reaktion_kombiniert_ausschreibung_und_netzwerk():
    from app.gesamtprozess import keine_reaktion_kpi

    jobs = [_job(id=1, status="Beworben")]
    apps = [_application(id=1, job_id=1, applied_date=(HEUTE - timedelta(days=20)).isoformat())]
    outreach = [_outreach(id=1, status="Initiated", antwort=None,
                          datum=(HEUTE - timedelta(days=20)).isoformat())]

    result = keine_reaktion_kpi(jobs, [], apps, outreach, heute=HEUTE)

    assert result["wert"] == 2
    assert result["splits"] == {"Ausschreibungen": 1, "Netzwerk": 1}
    assert len(result["rows"]) == 2
