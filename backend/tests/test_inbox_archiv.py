"""Inbox-Archiv fuer Mails ohne Stelle (P2-52, Paket I1).

Auftrag: Mails ohne Stelle (Newsletter, Rundmails, alles ohne Bewerbungsbezug) lassen
sich in der App archivieren und zurueckholen — NUR in der App, Gmail bleibt unberuehrt.
`email.archived_at` ist dabei kein Review-/Gelesen-Status (den hatte Phase 36 bewusst
abgelehnt), sondern ein Tombstone gegen Neu-Import: die Zeile bleibt erhalten, `gmail_ingest`
erkennt ihre `gmail_message_id` beim naechsten Mail-Check weiterhin als bekannt.

Invariante (V6): `archived_at` gesetzt ⇒ `job_id` und `application_id` sind leer. Archivieren
ist deshalb nur fuer Mails OHNE Stelle erlaubt (409 sonst), und Zuordnen (`/assign`) holt eine
archivierte Mail automatisch zurueck.

Geteilte tmp-DB (conftest.py, `session`-scope): zwischen Tests NICHT geleert. Zusicherungen
deshalb nur auf eigene ids/eindeutige Marker, nie auf Tabellen-Gesamtzahlen (Ausnahme: Differenz
vorher/nachher, z. B. beim Dashboard-Zaehler). Jede Test-Mail bekommt eine eindeutige
`gmail_message_id` (uuid4). Alle Absender-/Betreff-Werte sind synthetisch (T3) — keine echten
Firmen- oder Personennamen.

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention) — nur funktionslokal.
"""
import uuid
from datetime import datetime, timedelta


def _mail(session, *, job=None, subject=None, needs_reply=False, archived=False,
          category="Sonstige", direction="incoming", stunden_zurueck=1.0):
    """Legt eine Email-Zeile in der Test-DB an und gibt sie zurueck.

    `job=None` (Default) erzeugt eine Mail OHNE Stelle (job_id/application_id leer) — der
    Regelfall dieser Suite. `job=<Job>` setzt job_id/company_id, fuer den 409-Fall
    ("zugeordnete Mail laesst sich nicht archivieren"). `archived=True` setzt archived_at direkt
    beim Anlegen (fuer Tests, die eine bereits archivierte Mail als Ausgangslage brauchen, ohne
    den Archivieren-Endpunkt selbst zu pruefen).
    """
    from app.models import Email

    e = Email(
        gmail_message_id=f"p252-{uuid.uuid4().hex}",
        direction=direction, category=category,
        from_addr="postfach@dienst-x.test", subject=subject or "Testmail ohne Bewerbungsbezug",
        received_at=datetime.utcnow() - timedelta(hours=stunden_zurueck),
        needs_reply=needs_reply,
        job_id=job.id if job else None,
        company_id=job.company_id if job else None,
        archived_at=(datetime.utcnow().isoformat() if archived else None),
    )
    session.add(e)
    session.commit()
    session.refresh(e)
    return e


# ── Archivieren ────────────────────────────────────────────────────────────────────────────
def test_archivieren_mail_ohne_stelle_wandert_ins_archiv(client, session):
    mail = _mail(session, subject="Marker archivieren")

    resp = client.post(f"/api/emails/{mail.id}/archive")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["archived_at"]   # ISO-Zeitstempel gesetzt

    inbox_ids = {e["id"] for e in client.get("/api/inbox").json()}
    assert mail.id not in inbox_ids   # Standardansicht: fehlt

    archiv = {e["id"]: e for e in client.get("/api/inbox", params={"archived": "true"}).json()}
    assert mail.id in archiv
    assert archiv[mail.id]["archived_at"] == body["archived_at"]
    assert archiv[mail.id]["subject"] == "Marker archivieren"

    # Zweites Archivieren: 200, Zeitstempel bleibt UNVERAENDERT (Idempotenz, kein Fehler).
    resp2 = client.post(f"/api/emails/{mail.id}/archive")
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["archived_at"] == body["archived_at"]


def test_archivieren_zugeordneter_mail_gibt_409(client, session, seed):
    job = seed["jobs"][0]
    mail = _mail(session, job=job)

    resp = client.post(f"/api/emails/{mail.id}/archive")
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == (
        "Nur Mails ohne Stelle lassen sich archivieren. Lösen Sie zuerst die Zuordnung."
    )

    # Unveraendert: weder archiviert noch aus der Zuordnung gefallen.
    session.expire_all()
    from app.models import Email
    unveraendert = session.get(Email, mail.id)
    assert unveraendert.archived_at is None
    assert unveraendert.job_id == job.id


def test_archivieren_unbekannte_id_gibt_404(client):
    resp = client.post("/api/emails/999999999/archive")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "E-Mail nicht gefunden"


# ── Zurueckholen ───────────────────────────────────────────────────────────────────────────
def test_zurueckholen_bringt_mail_wieder_in_die_inbox(client, session):
    mail = _mail(session, archived=True, subject="Marker zurueckholen")

    resp = client.post(f"/api/emails/{mail.id}/restore")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}

    inbox_ids = {e["id"] for e in client.get("/api/inbox").json()}
    assert mail.id in inbox_ids
    archiv_ids = {e["id"] for e in client.get("/api/inbox", params={"archived": "true"}).json()}
    assert mail.id not in archiv_ids


def test_zurueckholen_nicht_archivierter_mail_gibt_404(client, session):
    mail = _mail(session)   # nie archiviert

    resp = client.post(f"/api/emails/{mail.id}/restore")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "E-Mail ist nicht archiviert"


def test_zurueckholen_unbekannte_id_gibt_404(client):
    resp = client.post("/api/emails/999999999/restore")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "E-Mail nicht gefunden"


# ── Invariante: Zuordnen holt aus dem Archiv ──────────────────────────────────────────────────
def test_zuordnen_archivierter_mail_holt_sie_automatisch_zurueck(client, session, seed):
    """V6/V7: archived_at gesetzt ⇒ job_id/application_id leer — umgekehrt darf eine Mail mit
    Stelle nie archiviert bleiben. assign_email() muss archived_at deshalb beim Zuordnen loeschen."""
    mail = _mail(session, archived=True, subject="Marker zuordnen")
    job = seed["jobs"][1]

    resp = client.post(f"/api/emails/{mail.id}/assign", json={"job_id": job.id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"]["archived_at"] is None

    inbox_ids = {e["id"] for e in client.get("/api/inbox").json()}
    assert mail.id in inbox_ids
    archiv_ids = {e["id"] for e in client.get("/api/inbox", params={"archived": "true"}).json()}
    assert mail.id not in archiv_ids


# ── Dashboard ──────────────────────────────────────────────────────────────────────────────
def test_dashboard_emails_sinkt_um_eins_kennzahlen_bleiben_gleich(client, session):
    """Lehre Phase 85: Kennzahl-Vergleich immer vorher/nachher, nie gegen eine angenommene
    Gesamtzahl. Nur totals.emails darf sich aendern (Spec V7) — responses/avg_response_hours/
    response_rate zaehlen laut app.response_metrics ohnehin nur Mails MIT application_id, eine
    archivierte Mail hat nie eine."""
    mail = _mail(session, subject="Marker Dashboard")

    vorher = client.get("/api/dashboard").json()["totals"]
    resp = client.post(f"/api/emails/{mail.id}/archive")
    assert resp.status_code == 200, resp.text
    nachher = client.get("/api/dashboard").json()["totals"]

    assert nachher["emails"] == vorher["emails"] - 1
    assert nachher["responses"] == vorher["responses"]
    assert nachher["avg_response_hours"] == vorher["avg_response_hours"]
    assert nachher["response_rate"] == vorher["response_rate"]


# ── Tagesbericht ───────────────────────────────────────────────────────────────────────────
def test_digest_archivierte_mail_fehlt_unter_zu_beantworten(session):
    """Betreff-Marker gezielt NUR im Abschnitt "Zu beantworten" pruefen (nicht im ganzen
    Dokument) — Vorbild test_digest_absagen.py::_abschnitt. Eine zweite, nicht archivierte
    Mail mit needs_reply dient als Gegenprobe: der Abschnitt selbst funktioniert weiter, nur die
    archivierte Mail fehlt darin."""
    from pipeline import digest as digest_modul

    marker_archiviert = f"P252-Archiv-{uuid.uuid4().hex[:8]}"
    marker_aktiv = f"P252-Aktiv-{uuid.uuid4().hex[:8]}"
    _mail(session, subject=marker_archiviert, needs_reply=True, archived=True)
    _mail(session, subject=marker_aktiv, needs_reply=True, archived=False)

    html = digest_modul.build_digest_html()
    start = html.index("Zu beantworten (")
    abschnitt = html[start:html.index("</section>", start)]

    assert marker_archiviert not in abschnitt
    assert marker_aktiv in abschnitt


# ── Neu-Import: Dedup haelt auch bei archivierten Mails ────────────────────────────────────
def test_neu_import_ueberspringt_archivierte_mail_als_dublette(session):
    """Vorbild test_mail_zwillinge.py::test_ingest_emails_...: derselbe gmail_message_id-Wert
    darf beim naechsten Mail-Check nicht zu einer zweiten Zeile fuehren — sonst kaeme eine
    archivierte Mail beim Ingest zurueck. `gmail_ingest.seen_mid` liest ALLE Email-Zeilen ohne
    Filter auf archived_at, das Dedup greift also unveraendert (pipeline/gmail_ingest.py bleibt
    in diesem Paket unangetastet)."""
    from app.models import Email
    from pipeline import gmail_ingest as gi

    mail = _mail(session, archived=True)
    mid = mail.gmail_message_id

    result = gi.ingest_emails([{
        "gmail_message_id": mid, "direction": "incoming",
        "from_addr": "postfach@dienst-x.test", "subject": "Erneut zugestellt",
        "received_at": "2026-09-28T08:00:00Z", "category": "Sonstige",
    }])
    assert result["dup"] == 1
    assert result["new"] == 0

    session.expire_all()
    wieder = session.get(Email, mail.id)
    assert wieder.archived_at == mail.archived_at   # bleibt archiviert, unangetastet


# ── Migration: Alt-Schema ohne archived_at ──────────────────────────────────────────────────
def test_ensure_columns_migriert_alt_schema_email_archiviert(tmp_path, monkeypatch):
    """Vorbild test_availability.py::test_ensure_columns_migriert_alt_schema_job_availability —
    eigene throwaway-SQLite-Datei (nicht die geteilte Session-tmp-DB), weil hier das Roh-Schema
    manipuliert wird. `email` wird durch ein Alt-Schema OHNE archived_at ersetzt;
    _ensure_columns() muss die Spalte additiv ergaenzen, Bestandszeilen bleiben NULL."""
    import sqlite3
    from sqlmodel import create_engine
    import app.db as db_modul

    db_path = tmp_path / "isoliert_email.sqlite"
    ersatz_engine = create_engine(f"sqlite:///{db_path}", echo=False,
                                  connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_modul, "engine", ersatz_engine)

    db_modul.init_db()   # volles modernes Schema anlegen ...

    # ... dann email durch ein Alt-Schema OHNE archived_at ersetzen.
    conn = sqlite3.connect(str(db_path))
    conn.execute("DROP TABLE email")
    conn.execute("CREATE TABLE email (id INTEGER PRIMARY KEY, subject TEXT, gmail_message_id TEXT)")
    conn.execute("INSERT INTO email (id, subject, gmail_message_id) VALUES (1, 'Alte Mail', 'p252-alt-1')")
    conn.commit()
    spalten_vorher = {r[1] for r in conn.execute("PRAGMA table_info(email)")}
    conn.close()
    assert "archived_at" not in spalten_vorher

    db_modul._ensure_columns()

    conn = sqlite3.connect(str(db_path))
    try:
        spalten_nachher = {r[1] for r in conn.execute("PRAGMA table_info(email)")}
        assert "archived_at" in spalten_nachher
        zeile = conn.execute("SELECT archived_at FROM email WHERE id = 1").fetchone()
    finally:
        conn.close()
    assert zeile == (None,)
