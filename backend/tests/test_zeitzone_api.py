"""P2-20 (28.08.2026): Die API kennzeichnet ihre Zeitstempel als UTC.

ANLASS: `email.received_at` & Co. sind naives UTC, die API lieferte sie aber ohne
Zeitzonen-Angabe aus (`"2026-08-28T09:18:27"`). JavaScript liest so einen String als LOKALE
Zeit — die Oberfläche zeigte im Sommer jeden Zeitpunkt zwei Stunden zu früh. Aufgefallen an
einer Absage, die im Bericht um 09:18 Uhr stand und im Postfach um 11:18 Uhr.

Belegt war das hart: Eine Mail steht als `09:18:27` in der DB, ihr Mail-Header sagt
`Fri, 28 Aug 2026 09:18:27 +0000`.

DER WÄCHTER (`test_kein_endpunkt_liefert_zeitstempel_ohne_zeitzone`) ist der eigentliche Wert
dieser Datei. Das `UtcZeit`-Mixin greift an der MODELL-Serialisierung; Endpunkte, die ihr JSON
von Hand bauen, gehen daran vorbei. Genau so blieb `/api/tasks` beim ersten Anlauf unmarkiert,
während `/api/emails` schon stimmte — auffallen konnte das nur, weil die Endpunkte einzeln
angesehen wurden. Der Wächter macht daraus eine Zusicherung statt einer Fleißaufgabe.

ABGRENZUNG: Nicht jeder Text, der wie ein Zeitpunkt aussieht, IST einer. `job.verified_at`,
`networkcontact.letzter_kontakt` und `interview.scheduled_at` sind Text-Spalten mit von Hand
eingetragenen LOKALEN Daten. Sie als UTC zu deuten hätte sie um den Zeitzonen-Versatz auf den
Vortag geschoben — `test_von_hand_eingetragene_daten_bleiben_unberuehrt` hält das fest.

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention).
"""
import datetime
import re

import pytest

# Ein Zeitstempel OHNE Zonenangabe: 2026-08-28T09:18:27 oder mit Sekundenbruchteilen.
OHNE_ZONE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$")
MIT_ZONE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(\+00:00|Z)$")

# Text-Spalten mit von Hand eingetragenen LOKALEN Zeiten — die dürfen KEINE Zone bekommen.
# P2-52: archived_at ist TEXT wie deleted_at (datetime.utcnow().isoformat(), bewusst unmarkiert
# — die Oberfläche deutet Soft-Delete-Stempel ohne Zone bereits als UTC, s. models.py::Email).
TEXTFELDER = {"scheduled_at", "verified_at", "letzter_kontakt", "reply_draft_at", "deleted_at",
              "archived_at", "recorded_at", "applied_date", "found_date", "follow_up_date"}


def _zeitstempel_ohne_zone(objekt, pfad=""):
    """Alle Werte im JSON finden, die wie ein Zeitpunkt ohne Zonenangabe aussehen."""
    treffer = []
    if isinstance(objekt, dict):
        for k, v in objekt.items():
            treffer += _zeitstempel_ohne_zone(v, pfad + "." + str(k))
    elif isinstance(objekt, list):
        for i, v in enumerate(objekt[:20]):
            treffer += _zeitstempel_ohne_zone(v, pfad + "[" + str(i) + "]")
    elif isinstance(objekt, str) and OHNE_ZONE.match(objekt):
        feld = pfad.rsplit(".", 1)[-1]
        if feld not in TEXTFELDER:
            treffer.append((pfad, objekt))
    return treffer


@pytest.fixture()
def bestand(session):
    """Ein Datensatz je betroffener Art, damit die Endpunkte etwas zu liefern haben.

    WIEDERVERWENDEND, nicht neu anlegend: Die Suite teilt sich über `conftest._db_ready`
    (scope="session") EINE tmp-Datenbank, die zwischen Tests nicht geleert wird. Ein zweites
    Anlegen derselben Zeilen verletzt die Eindeutigkeit von `gmail_message_id` und liess beim
    ersten Lauf drei Tests mit einem Fixture-Fehler abbrechen.
    """
    from sqlmodel import select

    from app.models import AgentTask, Application, Company, Email, Job, JobLog

    vorhanden = session.exec(select(Job).where(Job.dedup_key == "zeitzone|rolle")).first()
    if vorhanden:
        return vorhanden

    firma = Company(name="Zeitzone AG")
    session.add(firma)
    session.commit()
    session.refresh(firma)
    job = Job(company_id=firma.id, company_name="Zeitzone AG", title="Rolle", portal="LinkedIn",
              status="Beworben", found_date="2026-08-03", verified_at="2026-08-03",
              dedup_key="zeitzone|rolle")
    session.add(job)
    session.commit()
    session.refresh(job)
    session.add(Application(job_id=job.id, status="Beworben", channel="E-Mail",
                            applied_date="2026-08-03"))
    session.add(JobLog(job_id=job.id, art="auto", eintrag="Status: Prüfen → Beworben"))
    session.add(Email(gmail_message_id="zeitzone-probe", direction="incoming",
                      category="Absage", received_at=datetime.datetime(2026, 8, 28, 9, 18, 27),
                      subject="Ihre Bewerbung", from_addr="hr@example.com",
                      job_id=job.id, company_id=firma.id,
                      reply_draft_at="2026-07-14T07:53:48"))
    session.add(AgentTask(kind="email-check", status="done", prompt="Testprompt (pytest)",
                          started_at=datetime.datetime(2026, 8, 28, 9, 0, 0),
                          finished_at=datetime.datetime(2026, 8, 28, 9, 5, 0)))
    session.commit()
    return job


def test_kein_endpunkt_liefert_zeitstempel_ohne_zeitzone(client, bestand):
    """DER Wächter: Wer künftig ein DTO von Hand baut und `zeit.iso_utc()` vergisst, fällt hier
    auf — nicht erst dem Nutzer, dem die Uhrzeit um zwei Stunden danebenliegt."""
    pfade = ["/api/emails", "/api/tasks", "/api/jobs", f"/api/jobs/{bestand.id}",
             "/api/dashboard", "/api/companies", "/api/applications"]

    befunde = []
    geprueft = 0
    for pfad in pfade:
        antwort = client.get(pfad)
        if antwort.status_code != 200:
            continue
        geprueft += 1
        for stelle, wert in _zeitstempel_ohne_zone(antwort.json(), pfad):
            befunde.append(stelle + " = " + wert)

    assert geprueft >= 4, f"zu wenige Endpunkte erreichbar ({geprueft}) — der Wächter greift ins Leere"
    assert not befunde, (
        "Zeitstempel ohne Zeitzonen-Angabe gefunden. JavaScript liest sie als LOKALE Zeit, "
        "die Anzeige liegt dann um den Zeitzonen-Versatz daneben. Bau das DTO über "
        "`zeit.iso_utc()`:\n  " + "\n  ".join(befunde))


def test_email_zeitstempel_traegt_die_utc_kennzeichnung(client, bestand):
    """Der konkrete Fall, der die Umstellung ausgelöst hat."""
    mails = client.get("/api/emails").json()
    probe = [m for m in mails if m.get("subject") == "Ihre Bewerbung"]

    assert probe, "Testmail nicht in der Antwort"
    assert MIT_ZONE.match(probe[0]["received_at"]), (
        f"erwartet mit UTC-Kennzeichnung, bekam {probe[0]['received_at']!r}")


def test_task_zeitstempel_traegt_die_utc_kennzeichnung(client, bestand):
    """`/api/tasks` baut sein JSON von Hand (`_task_dto`) — das Mixin greift dort NICHT.
    Dieser Test hält fest, dass der handgebaute Weg trotzdem kennzeichnet."""
    tasks = client.get("/api/tasks").json()

    assert tasks, "keine Tasks in der Antwort"
    for feld in ("created_at", "started_at", "finished_at"):
        wert = tasks[0].get(feld)
        if wert:
            assert MIT_ZONE.match(wert), f"{feld} ohne UTC-Kennzeichnung: {wert!r}"


def test_von_hand_eingetragene_daten_bleiben_unberuehrt(client, bestand):
    """Gegenprobe zum Wächter: `verified_at` und `found_date` sind Text mit LOKALEN Daten.
    Eine UTC-Kennzeichnung würde sie um den Zeitzonen-Versatz auf den Vortag schieben."""
    # `/api/jobs/{id}` liefert ein Bündel (job, company, application, emails, …) — die
    # Stellendaten stecken unter "job".
    job = client.get(f"/api/jobs/{bestand.id}").json()["job"]

    assert job["verified_at"] == "2026-08-03"
    assert job["found_date"] == "2026-08-03"


def test_mixin_markiert_nur_echte_zeitstempel():
    """Direkttest des Mixins — typgesteuert, nicht über Feldnamen."""
    from app.models import Email

    e = Email(gmail_message_id="x", direction="incoming",
              received_at=datetime.datetime(2026, 8, 28, 9, 18, 27),
              reply_draft_at="2026-07-14T07:53:48")
    daten = e.model_dump(mode="json")

    assert daten["received_at"] == "2026-08-28T09:18:27+00:00"
    assert daten["reply_draft_at"] == "2026-07-14T07:53:48", "Text-Spalte darf nicht angefasst werden"


def test_iso_utc_reicht_strings_unveraendert_durch():
    """`zeit.iso_utc()` wird auch auf gemischte Werte angewandt (z. B. in `_artefakt_iso`)."""
    from app import zeit

    assert zeit.iso_utc(datetime.datetime(2026, 8, 28, 9, 0)) == "2026-08-28T09:00:00+00:00"
    assert zeit.iso_utc("2026-08-03") == "2026-08-03"
    assert zeit.iso_utc(None) is None
    schon_bewusst = datetime.datetime(2026, 8, 28, 9, 0, tzinfo=datetime.timezone.utc)
    assert zeit.iso_utc(schon_bewusst) == "2026-08-28T09:00:00+00:00", "keine Doppel-Kennzeichnung"


def test_lokales_datum_kippt_am_abend_auf_den_folgetag():
    """`lokales_datum()` ist der Grund, warum `utc.date()` nicht reicht: Um 23:30 UTC ist in
    Deutschland längst der nächste Tag. Der Test rechnet unabhängig von der Zeitzone der
    laufenden Maschine — er vergleicht gegen die Umrechnung, nicht gegen ein festes Datum."""
    from app import zeit

    spaet_utc = datetime.datetime(2026, 8, 28, 23, 30, 0)
    erwartet = spaet_utc.replace(tzinfo=datetime.timezone.utc).astimezone().date()

    assert zeit.lokales_datum(spaet_utc) == erwartet
    if erwartet != spaet_utc.date():
        assert zeit.lokales_datum(spaet_utc) != spaet_utc.date(), (
            "bei positivem UTC-Versatz muss der lokale Tag abweichen")
