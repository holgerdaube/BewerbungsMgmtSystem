"""Tests für Phase 67B (P2-7 aus dem Code-Review): Response Rate / Ø Antwortzeit zählten Mails
statt Bewerbungen. Erhielt eine Bewerbung mehrere qualifizierende Antworten (Eingangsbestätigung
→ Einladung → Absage), zählte sie mehrfach — die Quote konnte über 100 % steigen, der
Zeit-Durchschnitt verzerrte sich zugunsten mailreicher Bewerbungen. Fix: `app/response_metrics.py`
dedupliziert auf Bewerbungsebene (`Email.application_id`) und nutzt je Bewerbung die FRÜHESTE
qualifizierende Antwort — main.py UND export_excel.py rufen jetzt dieselbe Funktion.

Drei Ebenen, wie in conftest.py vorgesehen (keine app.*-Importe auf Modulebene):
  1. Reine Funktion `response_kpis()` — deterministisch, ohne DB, deckt die Kernfälle ab.
  2. `/api/dashboard` end-to-end — Vorher/Nachher-Delta an EINER frischen, isolierten Bewerbung
     (Delta statt Absolutwert, weil die tmp-DB testübergreifend akkumuliert, s. conftest.py).
  3. `export_excel.build_workbook()` end-to-end — derselbe Delta-Beweis für den Excel-Pfad, plus
     ein Identitäts-Check, dass export_excel.py dieselbe Funktion aufruft wie main.py (nicht neu
     nachbaut) — das ist die vom Befund verlangte „beide Stellen bleiben identisch"-Garantie.
"""
import datetime


# ── Ebene 1: reine Funktion, keine DB ───────────────────────────────────────────────────────
def _mail(application_id, hours, is_response=True):
    """Leichtgewichtiges Email-Duck-Type-Objekt — response_kpis() braucht nur diese 3 Attribute."""
    import types
    return types.SimpleNamespace(
        application_id=application_id, response_time_hours=hours, is_response=is_response,
    )


def test_response_kpis_dedupliziert_mehrere_antworten_auf_dieselbe_bewerbung():
    from app.response_metrics import response_kpis

    # 3 Bewerbungen insgesamt, aber Bewerbung 1 hat DREI qualifizierende Antwort-Mails.
    emails = [_mail(1, 5.0), _mail(1, 48.0), _mail(1, 96.0), _mail(2, 10.0)]
    apps = [object(), object(), object()]  # 3 Bewerbungen gesamt (Inhalt irrelevant, nur Länge zählt)

    result = response_kpis(emails, apps)

    # OHNE Fix: len([e for e in emails if ...]) == 4 Mails -> 133 % Rate. Mit Fix: 2 EINDEUTIGE
    # Bewerbungen (1 und 2) von 3 -> 67 %.
    assert result["responses"] == 2
    assert result["response_rate"] == round(2 / 3 * 100)
    assert result["response_rate"] <= 100, "Rate darf durch Mehrfach-Antworten nie über 100% steigen"


def test_response_kpis_nimmt_die_frueheste_antwort_je_bewerbung():
    from app.response_metrics import response_kpis

    # Bewerbung 1: Eingangsbestätigung nach 5h, spaeter Absage nach 96h -> Ø soll 5.0 sein, nicht
    # (5+96)/2 = 50.5 und nicht 96 (die spaeteste).
    emails = [_mail(1, 96.0), _mail(1, 5.0)]  # bewusst in "falscher" Reihenfolge eingefuegt
    apps = [object()]

    result = response_kpis(emails, apps)

    assert result["responses"] == 1
    assert result["avg_response_hours"] == 5.0


def test_response_kpis_ignoriert_mails_ohne_application_id():
    """Eine Mail, die nur der Firma zugeordnet ist (kein konkreter Job/keine Bewerbung —
    z. B. das 'Ohne Stelle'-Muster aus gmail_ingest.py), darf keine Bewerbung vortäuschen, die
    es nicht gibt: sie zählt weder für die Rate noch für die Zeit."""
    from app.response_metrics import response_kpis

    emails = [_mail(None, 12.0)]
    apps = [object(), object()]

    result = response_kpis(emails, apps)

    assert result["responses"] == 0
    assert result["avg_response_hours"] is None
    assert result["response_rate"] == 0


def test_response_kpis_ignoriert_non_response_und_fehlende_zeit():
    from app.response_metrics import response_kpis

    emails = [
        _mail(1, None),                       # response_time_hours fehlt
        _mail(2, 10.0, is_response=False),    # is_response=False
    ]
    apps = [object(), object()]

    result = response_kpis(emails, apps)
    assert result["responses"] == 0
    assert result["avg_response_hours"] is None


def test_response_kpis_ohne_bewerbungen_liefert_none_rate():
    from app.response_metrics import response_kpis

    result = response_kpis([], [])
    assert result == {"responses": 0, "avg_response_hours": None, "response_rate": None}


# ── Ebene 2: /api/dashboard end-to-end (Delta statt Absolutwert) ───────────────────────────
def test_dashboard_response_rate_zaehlt_bewerbung_nicht_mail(client, session, seed):
    from app.models import Email

    job = seed["jobs"][0]
    application = seed["application"]

    vorher = client.get("/api/dashboard").json()["totals"]["responses"]

    basis = datetime.datetime.utcnow() - datetime.timedelta(days=2)
    for stunden, kategorie in ((6.0, "Eingangsbestätigung"), (48.0, "Einladung"), (96.0, "Absage")):
        session.add(Email(
            application_id=application.id, job_id=job.id, direction="incoming",
            category=kategorie, is_response=True, response_time_hours=stunden,
            received_at=basis + datetime.timedelta(hours=stunden),
        ))
    session.commit()

    nachher = client.get("/api/dashboard").json()["totals"]["responses"]

    # Drei neue qualifizierende Antwort-Mails auf EINE (vorher antwortlose) Bewerbung dürfen den
    # Zähler nur um 1 erhöhen (eindeutige Bewerbung), nicht um 3 (Mail-Zählung, der alte Bug).
    assert nachher - vorher == 1


# ── Ebene 3: export_excel.py end-to-end — Delta + Identität mit main.py ────────────────────
def test_export_excel_response_rate_zaehlt_bewerbung_nicht_mail(session, seed, tmp_path, monkeypatch):
    import openpyxl
    from app.models import Email
    from pipeline import export_excel

    # NIE in echte outputs/exports schreiben (T1) — EXPORT_DIR wird aus __file__ abgeleitet und
    # reagiert NICHT auf BMS_DATA_DIR, deshalb hier direkt patchen.
    monkeypatch.setattr(export_excel, "EXPORT_DIR", tmp_path)

    def _antworten_zelle():
        pfad = export_excel.build_workbook()
        wb = openpyxl.load_workbook(pfad)
        ws = wb["Dashboard"]
        assert ws.cell(row=4, column=7).value == "Antworten"   # Layout-Kontrakt absichern
        return ws.cell(row=5, column=7).value

    vorher = _antworten_zelle()

    job = seed["jobs"][0]
    application = seed["application"]
    basis = datetime.datetime.utcnow() - datetime.timedelta(days=2)
    for stunden, kategorie in ((6.0, "Eingangsbestätigung"), (48.0, "Einladung"), (96.0, "Absage")):
        session.add(Email(
            application_id=application.id, job_id=job.id, direction="incoming",
            category=kategorie, is_response=True, response_time_hours=stunden,
            received_at=basis + datetime.timedelta(hours=stunden),
        ))
    session.commit()

    nachher = _antworten_zelle()
    assert nachher - vorher == 1


def test_export_excel_nutzt_dieselbe_funktion_wie_main():
    """P2-7 verlangt ausdrücklich, dass main.py und export_excel.py NICHT unabhängig
    voneinander driften dürfen. Der Fix zieht die Berechnung an eine Stelle (app.response_metrics)
    — dieser Test stellt sicher, dass export_excel.py wirklich dieselbe Funktion aufruft statt
    sie (erneut textgleich) zu duplizieren, was den ursprünglichen Befund unbemerkt wieder
    einführen könnte."""
    from app.response_metrics import response_kpis
    from pipeline import export_excel

    assert export_excel.response_kpis is response_kpis
