"""Mail-Zuordnung bei Zwillingsstellen (P2-43, 19.09.2026).

Fall A (Rückmeldung aus dem Betrieb): „mal wieder so eine email zuordnung zur stelle ... wieso
erfasst du dies nicht zu einer aktiven bewerbung?“ Die Einladung zur zweiten Runde nannte in
Betreff und Vorschau keinen Titel; an der Firma hängen seit der P2-39-Bereinigung drei Stellen
derselben Rolle — eine im Interview, eine auf Kein Match, eine auf Geparkt (Dublette). `_match_job` ordnet
ohne Titel nur bei GENAU einer Stelle zu, die Volltextsuche fand drei gleiche Titel → „Ohne Stelle“.

Regel (`gmail_ingest._zwillinge_aufloesen`): Sind alle Kandidaten dieselbe Rolle
(`N.rollen_schluessel`), gewinnt der EINE Zwilling mit Bewerbungs-Status — aber nur, wenn diese
Bewerbung noch läuft (Beworben/Interview/Angebot). Zwischen verschiedenen Rollen entscheidet der
Status weiterhin nie (Phase 61A).

Alle Firmen- und Stellennamen synthetisch (T3). App-Importe nur in den Testfunktionen.
"""
import uuid

import pytest


def _firma(session, name):
    from app.models import Company

    comp = Company(name=f"{name} {uuid.uuid4().hex[:6]}")
    session.add(comp)
    session.commit()
    session.refresh(comp)
    return comp


def _stellen(session, comp, eintraege):
    """eintraege: Liste (titel, status) — gibt die angelegten Jobs in derselben Reihenfolge zurück."""
    from app.models import Job

    jobs = []
    for titel, status in eintraege:
        j = Job(company_id=comp.id, company_name=comp.name, title=titel, status=status,
                found_date="2026-09-01", dedup_key=f"synthetic|p243|{uuid.uuid4().hex}")
        session.add(j)
        jobs.append(j)
    session.commit()
    for j in jobs:
        session.refresh(j)
    return jobs


# ── _match_job ohne Titel ───────────────────────────────────────────────────────────────────
def test_vertigis_fall_ohne_titel_trifft_die_laufende_bewerbung(session):
    from pipeline.gmail_ingest import _match_job

    comp = _firma(session, "Kartenwerk")
    interview, _, _ = _stellen(session, comp, [
        ("Director Musterdienste (m/w/x)", "Interview"),
        ("Director Musterdienste (m/w/x)", "Kein Match"),
        ("Director Musterdienste (m/w/x)", "Geparkt"),
    ])
    treffer = _match_job(session, comp, None)
    assert treffer is not None and treffer.id == interview.id


def test_gender_varianten_zaehlen_als_zwillinge(session):
    """Fall B: „(m/f/d)“ läuft im Interview, „(m/w/d)“ ist Kein Match."""
    from pipeline.gmail_ingest import _match_job

    comp = _firma(session, "Pumpenbau")
    laufend, _ = _stellen(session, comp, [
        ("Head of Customer Success (m/f/d)", "Interview"),
        ("Head of Customer Success (m/w/d)", "Kein Match"),
    ])
    treffer = _match_job(session, comp, "")
    assert treffer is not None and treffer.id == laufend.id


def test_verschiedene_rollen_bleiben_ohne_titel_unzugeordnet(session):
    """Phase 61A bleibt: auch wenn nur EINE Stelle läuft, entscheidet der Status nicht zwischen
    verschiedenen Rollen (Rückgabe None, nicht _MEHRDEUTIG — der Volltext-Versuch bleibt offen)."""
    from pipeline.gmail_ingest import _MEHRDEUTIG, _match_job

    comp = _firma(session, "Vertragswerk")
    _stellen(session, comp, [
        ("Director, Professional Services (all genders)", "Interview"),
        ("AVP Solution Advisory DACH (all genders)", "Absage"),
    ])
    treffer = _match_job(session, comp, None)
    assert treffer is None and treffer is not _MEHRDEUTIG


def test_zwillinge_plus_fremde_rolle_bleiben_ohne_titel_unzugeordnet(session):
    from pipeline.gmail_ingest import _match_job

    comp = _firma(session, "Mischkonzern")
    _stellen(session, comp, [
        ("Head of Delivery (m/w/d)", "Interview"),
        ("Head of Delivery (m/w/d)", "Geparkt"),
        ("Senior Manager Operations (m/w/d)", "Kein Match"),
    ])
    assert _match_job(session, comp, None) is None


# ── Status-Grenzfälle ───────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("stati", [
    ("Absage", "Geparkt"),        # einzige Bewerbung ist abgeschlossen
    ("Absage", "Prüfen"),         # neu beworben, Status noch nicht gesetzt — Vorgänger NICHT treffen
    ("Absage", "Beworben"),       # zwei Bewerbungen auf dieselbe Rolle
    ("Absage", "Absage"),         # beide abgeschlossen
    ("Kein Match", "Geparkt"),    # nie beworben
])
def test_zwillinge_ohne_genau_eine_laufende_bewerbung_bleiben_mehrdeutig(session, stati):
    from pipeline.gmail_ingest import _MEHRDEUTIG, _match_job

    comp = _firma(session, "Randfall")
    titel = "Senior Manager Servicezentrum (Person*)"
    _stellen(session, comp, [(titel, stati[0]), (titel, stati[1])])
    assert _match_job(session, comp, titel) is _MEHRDEUTIG
    assert _match_job(session, comp, None) is None


def test_status_entscheidet_nicht_die_bewerbungszeile(session):
    """Fall C: die Bewerbungszeile (nur „Vorbereitet“, Anschreiben nie
    verschickt) hängt am abgelehnten Zwilling, beworben wurde auf den anderen."""
    from app.models import Application
    from pipeline.gmail_ingest import _match_job

    comp = _firma(session, "Betriebsdienste")
    titel = "Senior Manager Musterbetrieb (m/w/d)"
    abgelehnt, beworben = _stellen(session, comp, [(titel, "Beirat abgelehnt"), (titel, "Beworben")])
    session.add(Application(job_id=abgelehnt.id, status="Vorbereitet"))
    session.commit()

    treffer = _match_job(session, comp, titel)
    assert treffer is not None and treffer.id == beworben.id


def test_exakter_einzeltreffer_bleibt_wie_bisher(session):
    """Nennt die Mail genau einen der Titel wörtlich, gewinnt er — die Zwillingsregel greift
    erst bei mehreren Kandidaten (sonst verlöre eine Eingangsbestätigung vor dem Statuswechsel
    ihre Zuordnung)."""
    from pipeline.gmail_ingest import _match_job

    comp = _firma(session, "Wortlaut")
    neu, _ = _stellen(session, comp, [
        ("Head of Customer Success (m/f/d)", "Prüfen"),
        ("Head of Customer Success (m/w/d)", "Kein Match"),
    ])
    treffer = _match_job(session, comp, "Head of Customer Success (m/f/d)")
    assert treffer is not None and treffer.id == neu.id


# ── Volltext ────────────────────────────────────────────────────────────────────────────────
def test_volltext_mit_drei_gleichen_titeln_trifft_die_laufende_bewerbung(session, monkeypatch):
    import pipeline.gmail_ingest as gi

    comp = _firma(session, "Kartenwerk")
    titel = "Director Musterdienste (m/w/x)"
    interview, _, _ = _stellen(session, comp, [(titel, "Interview"), (titel, "Kein Match"), (titel, "Geparkt")])
    monkeypatch.setattr(gi, "_volltext",
                        lambda _mid: f"Guten Tag, zur Position {titel} laden wir Sie zur zweiten Runde ein.")
    treffer = gi._match_job_im_volltext(session, comp, "msg-p243")
    assert treffer is not None and treffer.id == interview.id


# ── Gesamter Mail-Durchlauf ─────────────────────────────────────────────────────────────────
def test_ingest_emails_haengt_titellose_einladung_an_die_laufende_bewerbung(session, monkeypatch):
    from sqlmodel import select
    import pipeline.gmail_ingest as gi
    from app.models import Application, Email, Job

    monkeypatch.setattr(gi, "_volltext", lambda _mid: None)   # kein Gmail-Zugriff im Test
    comp = _firma(session, "Kartenwerk")
    titel = "Director Musterdienste (m/w/x)"
    interview, kein_match, geparkt = _stellen(session, comp, [
        (titel, "Interview"), (titel, "Kein Match"), (titel, "Geparkt")])
    app = Application(job_id=interview.id, status="Interview")
    session.add(app)
    session.commit()
    session.refresh(app)

    mid = f"synthetic-p243-{uuid.uuid4().hex[:8]}"
    result = gi.ingest_emails([{
        "gmail_message_id": mid, "direction": "incoming",
        "from_addr": "recruiting@kartenwerk-example.test",
        "subject": "Ihre Bewerbung | Einladung zur zweiten Runde",
        "snippet": "Gerne würden wir Sie zur zweiten Runde der Interviews einladen.",
        "received_at": "2026-09-18T18:49:13Z", "category": "Einladung",
        "company": comp.name, "job_status": "Interview", "needs_reply": True,
    }])
    assert result["mehrdeutig"] == 0

    session.expire_all()
    mail = session.exec(select(Email).where(Email.gmail_message_id == mid)).one()
    assert mail.job_id == interview.id and mail.application_id == app.id
    stati = {j.id: j.status for j in session.exec(select(Job).where(Job.company_id == comp.id)).all()}
    assert stati == {interview.id: "Interview", kein_match.id: "Kein Match", geparkt.id: "Geparkt"}


def test_rollen_schluessel_ist_titelteil_des_stellen_schluessels():
    """Dubletten-Erkennung und Mail-Zuordnung teilen EINE Definition von „dieselbe Rolle“."""
    from app import normalize as N
    from pipeline.ingest import _stellen_schluessel

    titel = "Head of Customer Success (m/f/d)"
    assert _stellen_schluessel("Pumpenbau GmbH", titel).split("|", 1)[1] == N.rollen_schluessel(titel)
    assert N.rollen_schluessel(titel) == N.rollen_schluessel("Head of Customer Success (m/w/d)")
