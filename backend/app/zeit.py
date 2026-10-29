"""Zeitzonen an einer Stelle — die Konvention des Projekts und ihre Umrechnungen.

DIE KONVENTION (galt schon vorher, war aber nirgends aufgeschrieben):
    Gespeichert wird **naives UTC**. Jedes `datetime`-Feld der Modelle entsteht aus
    `datetime.utcnow()` bzw. — bei E-Mails — aus `gmail_client._iso()`, das
    `utcfromtimestamp` nutzt. In der Datenbank steht also ein UTC-Zeitpunkt OHNE
    Zeitzonen-Angabe. Umgerechnet wird ausschliesslich am Rand: bei der Anzeige.

WARUM DIESES MODUL ENTSTAND (28.08.2026): Die Konvention war korrekt, aber unsichtbar. Drei
Stellen hatten sich unabhaengig voneinander dieselben zwei Zeilen gebaut
(`agent_runner._tagesbeginn_utc`, `budget.py`, `digest.py`), und die API verschwieg die
Zeitzone voellig: Sie lieferte `"2026-08-28T09:18:27"` — ein String, den JavaScript als
LOKALE Zeit liest. Im Sommer zeigte die Oberflaeche dadurch jeden Zeitpunkt zwei Stunden zu
frueh. Aufgefallen ist es an einer Absage, die laut Bericht um 09:18 Uhr kam, im Postfach aber
um 11:18 Uhr steht.

`UtcZeit` schliesst genau diese Luecke — und zwar typgesteuert, nicht ueber Feldnamen: Nur
echte `datetime`-Werte werden markiert. Von Hand eingetragene Datums-Strings
(`job.verified_at`, `networkcontact.letzter_kontakt`, `interview.scheduled_at`) bleiben
unberuehrt; sie als UTC zu deuten haette sie um den Zeitzonen-Versatz auf den Vortag
geschoben.

WAS SICH BEWUSST NICHT AENDERT: Die Werte bleiben intern naiv. Ein Wechsel auf
zeitzonenbewusste Objekte im ORM haette jeden Vergleich mit `utcnow()` im Projekt gebrochen
(14 Stellen) — der Gewinn waere derselbe gewesen, das Risiko um ein Vielfaches groesser.
"""
import datetime

from pydantic import field_serializer

UTC = datetime.timezone.utc


class UtcZeit:
    """Mixin fuer Modelle: markiert `datetime`-Werte beim Serialisieren als UTC.

    Aus `"2026-08-28T09:18:27"` wird `"2026-08-28T09:18:27+00:00"`. Damit weiss jeder
    Empfaenger, was er in der Hand haelt — `new Date(...)` im Browser rechnet dann von selbst
    in die lokale Zeit um, ohne dass eine einzige Anzeigestelle etwas tun muss.

    Reihenfolge beim Erben beachten: `class Email(UtcZeit, SQLModel, table=True)`. Das Mixin
    muss VOR `SQLModel` stehen, sonst greift der Serializer nicht.

    Bereits zeitzonenbewusste Werte bleiben unveraendert — das Mixin ergaenzt nur, was fehlt.
    """

    @field_serializer("*", when_used="json")
    def _utc_markieren(self, wert):
        if isinstance(wert, datetime.datetime) and wert.tzinfo is None:
            return wert.replace(tzinfo=UTC).isoformat()
        return wert


def iso_utc(wert):
    """`datetime` → ISO-String MIT UTC-Kennzeichnung; alles andere unveraendert.

    Fuer die Endpunkte, die ihr JSON von Hand bauen (`_task_dto`, die Inbox-Liste u. a.). Dort
    greift `UtcZeit` nicht — das Mixin haengt an der Modell-Serialisierung, ein handgebautes
    dict geht daran vorbei. Genau so blieb `/api/tasks` beim ersten Anlauf unmarkiert, waehrend
    `/api/emails` schon stimmte.

    Strings kommen unveraendert zurueck: `interview.scheduled_at` und `email.reply_draft_at`
    sind Text, keine Zeitstempel im Sinne der Konvention.
    """
    if isinstance(wert, datetime.datetime):
        return (wert if wert.tzinfo else wert.replace(tzinfo=UTC)).isoformat()
    return wert


def jetzt_utc() -> datetime.datetime:
    """Aktueller Zeitpunkt als naives UTC — passend zu allen gespeicherten Zeitstempeln.

    Bewusst `now(UTC).replace(tzinfo=None)` statt des veralteten `utcnow()`: dasselbe Ergebnis,
    keine Verwarnung, und die Naiv-UTC-Absicht steht ausdrucklich da.
    """
    return datetime.datetime.now(UTC).replace(tzinfo=None)


def nach_lokal(utc_naiv: datetime.datetime) -> datetime.datetime:
    """Naives UTC → zeitzonenbewusste LOKALE Zeit (fuer Anzeigen im Backend)."""
    return utc_naiv.replace(tzinfo=UTC).astimezone()


def lokales_datum(utc_naiv: datetime.datetime) -> datetime.date:
    """Auf welchen LOKALEN Kalendertag faellt dieser UTC-Zeitpunkt?

    Nicht `utc_naiv.date()` nehmen: Zwischen 22:00 und 24:00 UTC ist in Deutschland bereits der
    Folgetag, im Winter ab 23:00.
    """
    return nach_lokal(utc_naiv).date()


def tagesbeginn_utc() -> datetime.datetime:
    """Lokale Mitternacht als naives UTC.

    Nicht ueber `date.today()` oder `utcnow().date()` rechnen: Gespeichert ist UTC, der Nutzer denkt
    in lokalen Tagen. In Deutschland (UTC+2 im Sommer) wuerde eine naive Pruefung das Tagesbudget
    um 02:00 lokal zuruecksetzen und zwischen 00:00 und 02:00 den Vortag mitzaehlen.
    """
    lokal_jetzt = datetime.datetime.now().astimezone()
    mitternacht = lokal_jetzt.replace(hour=0, minute=0, second=0, microsecond=0)
    return mitternacht.astimezone(UTC).replace(tzinfo=None)


def monatsbeginn_utc() -> datetime.datetime:
    """Lokaler Monatserster als naives UTC — Monats-Aequivalent zu `tagesbeginn_utc()`."""
    lokal_jetzt = datetime.datetime.now().astimezone()
    monatserster = lokal_jetzt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return monatserster.astimezone(UTC).replace(tzinfo=None)
