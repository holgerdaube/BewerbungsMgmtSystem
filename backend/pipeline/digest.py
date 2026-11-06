"""Tages-Digest als self-contained HTML — Zusammenfassung des Bewerbungsstands."""
import datetime
import html
import re
from string import Template

from sqlmodel import Session, select

from app.db import engine
from app import favicon, zeit
from app.sprache import datum, html_lang, tx, uebersetzt
from app.models import Application, Company, Email, Job, JobLog
from pipeline import design, zustandsfarben

# Phase 80: Palette = Styleguide v5 §18.10 (Rollback-Tabelle: tasks/spec_phase80_styleguide_v18_theme.md)
#
# P2-72 (Design aus einer Quelle): Die Markenwerte (Seitengrund, Karte, Rahmen, Schrift, Akzent) stehen
# nicht mehr als Farbwerte im CSS, sondern als `$rolle`-Platzhalter. `_css()` setzt sie bei JEDEM Aufruf aus
# dem geltenden Design ein (`design.laden()`), nie beim Import: Eine geänderte Design-Datei gilt ohne
# Neustart. Mit der Vorgabe entsteht byte-genau das CSS von vorher.
# Fest bleibt, was Bedeutung trägt (Leitentscheidung 2): die Pastelle der Änderungs-Tags (`.chg.*`) samt
# ihrer Schrift, das Rot des Absage-Tags (`.tag`) und das Neutralgrau für Nebentext (`.muted`, `.empty`,
# Slate-400): Es gehört zu keiner Rolle, denn `text_gedaempft` ist ein anderer Wert.
# P2-79: Die Zeilen-Regeln des Digest (Zeile, Absage-Tag, Leertext, Änderungs-Tags) werden an zwei Stellen
# gebraucht: im Digest selbst und auf der Seite „Tages-Digest“ der Coach-Site, deren eigenes CSS sie nicht
# kennt. Sie stehen deshalb als eigene Stücke hier und NUR hier. `_CSS_VORLAGE` setzt sie an ihrer alten
# Stelle wieder ein (die Reihenfolge ist fest: das CSS des Digest ist byte-gleich zu dem von vor P2-79, der
# Hash steht in tests/test_design_ausgaben.py); `zeilen_css()` reicht dieselben Stücke an die Coach-Site.
# Bewusst NICHT dabei: `.badge`, `.muted`, `.kpi*`, `section`, `h2` und `.foot`, die hat die Coach-Site selbst.
_CSS_ZEILE = """.row{display:flex;gap:8px;align-items:baseline;padding:6px 0;border-bottom:1px solid $spur;font-size:14px}
.row:last-child{border:0}"""
_CSS_TAG = ".tag{background:#fee2e2;color:#b91c1c;border-radius:9999px;padding:1px 8px;font-size:11px}"
_CSS_LEER = ".empty{color:#94A3B8;font-size:14px}"
_CSS_AENDERUNG = """.row.zwei{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:baseline}
.row.zwei .links{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;min-width:0}
.chg{border-radius:9999px;padding:1px 8px;font-size:11px;white-space:nowrap}
.chg.bew{background:#E6F7EE;color:#0F7A3D}
.chg.iv{background:#E1F6FB;color:#0B6E85}
.chg.absage{background:#FEE2E2;color:#B91C1C}
.chg.kein{background:#EEF2F7;color:#5F6F84}
.chg.pruef{background:#FDF3D6;color:#8A6100}
.chg.neutral{background:#EAF3FB;color:$text_auf_zustand}"""

_CSS_VORLAGE = Template("""
body{font-family:$schrift_text,system-ui,-apple-system,sans-serif;background:$flaeche;color:$text;margin:0;padding:24px}
.wrap{max-width:840px;margin:0 auto}
h1{color:$marke;margin:0 0 4px}.sub{color:$text_gedaempft;font-size:14px;margin-bottom:20px}
.kpis{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:24px}
.kpi{background:$karte;border:1px solid $rahmen;border-radius:12px;padding:12px 16px;min-width:120px}
.kpi .n{font-size:26px;font-weight:700;color:$marke}.kpi.acc .n{color:$aktion}
.kpi .l{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:$text_gedaempft}
section{background:$karte;border:1px solid $rahmen;border-radius:12px;padding:16px;margin-bottom:16px}
h2{font-size:15px;color:$marke;margin:0 0 10px}
""" + _CSS_ZEILE + """.badge{display:inline-flex;width:22px;height:22px;border-radius:50%;font-size:12px;font-weight:700;align-items:center;justify-content:center}
.muted{color:#94A3B8}""" + _CSS_TAG + "\n" + _CSS_LEER + """
.foot{margin-top:20px;padding-top:12px;border-top:1px solid $rahmen;font-size:12px;color:$text_gedaempft;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
""" + _CSS_AENDERUNG + "\n")


def markenwerte(d) -> dict:
    """Ersetzungstabelle für die CSS-Vorlagen von Digest und Coach-Site: je Farbrolle des Designs `d` der
    Wert, dazu `schrift_text` (Name der Textschrift) und `text_auf_zustand` (fest, Bedeutung).

    Beide Ausgaben schreiben Weiß seit jeher kurz (`#fff`). Die Design-Datei schreibt `#FFFFFF`; damit
    die Ausgabe mit der Vorgabe byte-gleich bleibt, wird nur diese eine Farbe kurz geschrieben. Gleiche
    Farbe, andere Schreibweise.
    """
    werte = {rolle: ("#fff" if farbe == "#FFFFFF" else farbe) for rolle, farbe in d.farben.items()}
    schrift = d.schriften["text"]
    # „System“ ist keine Schriftfamilie, sondern der Platzhalter für die Systemschrift des Designs
    # (unter Windows gibt es eine Schrift dieses Namens, die hier nicht gemeint ist).
    werte["schrift_text"] = "system-ui" if schrift == "System" else schrift
    werte["text_auf_zustand"] = zustandsfarben.TEXT_AUF_ZUSTAND
    return werte


def _css(d) -> str:
    return _CSS_VORLAGE.substitute(markenwerte(d))


# Rückweg in die App, nur in der Ansicht über /api/digest (Muster „← Zurück zu Stellen“ im Stellen-Detail).
# Eine eigene Regel statt eines Eintrags in `_CSS_VORLAGE`: Die Datei des Tageslaufs bleibt byte-gleich.
_CSS_ZURUECK = Template(""".zurueck{display:inline-block;margin-bottom:12px;font-size:14px;color:$aktion;text-decoration:none}
.zurueck:hover{text-decoration:underline}""")


def zeilen_css(d) -> str:
    """Nur die Zeilen-Regeln des Digest (`.row`, `.row.zwei`, `.links`, `.tag`, `.empty`, `.chg.*`) mit den
    Markenwerten des Designs `d`, für die Seite „Tages-Digest“ der Coach-Site (P2-79). Dieselben Stücke wie in
    `_css()`, also dieselben Werte; die Coach-Site hängt sie hinter ihr eigenes CSS, ohne sie noch einmal
    zu schreiben."""
    return Template("\n".join((_CSS_ZEILE, _CSS_TAG, _CSS_LEER, _CSS_AENDERUNG))).substitute(markenwerte(d))


# Zielstellen-Fit-Skala nach Daube.Tech-Styleguide v5 §18.4 (Design-Review 10.08.2026 — vorher lagen
# hier generische Office-Ampelfarben mit weißer Schrift auf Gelb/Orange/Hellgrün, WCAG-Fail).
#
# P2-72: Die Skala steht jetzt in `pipeline/zustandsfarben.py` (EINE Tabelle, gleich der in ui.tsx).
# BENANNTE AUSNAHME: Auf Score 5 (Grün) schreiben Digest und Coach-Site weiße Schrift (Kontrast 3,1:1), die
# Tabelle und die App Navy (5,4:1). §18.8 lässt Weiß nur auf Score 1 zu. Die Abweichung ist alt (Phase 80:
# „Weiß nur auf den dunklen Enden der Skala, 1 = Rot, 5 = Grün“) und gehört zur Ausgabe, wie sie heute
# aussieht; P2-72 ändert nichts Sichtbares, deshalb steht sie hier und nicht in der Tabelle. Die
# Coach-Site übernimmt sie von hier (sie nahm die Skala schon immer aus dem Digest).
SCORE_SCHRIFT_AUSNAHME = {5: "#ffffff"}


def score_farben(sc):
    """(Fläche, Schrift) des Score-Badges in Digest und Coach-Site: die Tabelle, mit der Ausnahme oben."""
    flaeche, schrift = zustandsfarben.score_farbe(sc)
    return flaeche, SCORE_SCHRIFT_AUSNAHME.get(sc, schrift)


# ZEITFENSTER des Absagen-Abschnitts. Vorgabe vom 31.08.2026: „Hier sollen die Absagen
# der letzten 96h auftauchen. Die aktuellen 24h sind gerade bei einem Wochenende zu kurz.“
# 96 Stunden reichen von Freitagfrueh bis Montagfrueh: Was uebers Wochenende hereinkam, fiel
# mit 24 Stunden aus JEDEM Bericht heraus, den man montags liest — der Fall trat sofort ein,
# weil Absagen ueberdurchschnittlich oft freitags verschickt werden.
#
# Die Zahl steht ABSICHTLICH nur an dieser einen Stelle: Fenstergrenze, Ueberschrift und
# Leertext lesen sie, damit die Beschriftung nicht von der Rechnung abweichen kann.
ABSAGEN_FENSTER_STUNDEN = 96

# ZEITFENSTER des Beworben-Abschnitts, seit 04.09.2026 gleich dem der Absagen (Wunsch
# des Nutzers: „macht die Beworben Spanne bitte auch auf 96h“).
#
# Die urspruengliche Begruendung fuer 72 Stunden steht hier bewusst noch, weil sie falsch
# war: Bewerbungen loese der Nutzer selbst aus, sehe sie also ohnehin, ein Wochenend-Loch wie bei
# eingehenden Absage-Mails gebe es nicht. Das verwechselt Erinnerung mit Ueberblick. Der
# Abschnitt sagt nicht „du hast dich beworben“, sondern „das ist gerade in der Luft“ — und da
# reisst ein Wochenende dieselbe Luecke wie anderswo: Am Freitag, 04.09.2026 lagen im
# 72-Stunden-Fenster 8 Bewerbungen, im 96-Stunden-Fenster 11; die drei fehlenden waren alle
# vom Montag.
#
# Der Gleichstand hat einen zweiten Nutzen: Beworben und Absagen sind jetzt derselbe
# Zeitraum und damit direkt gegeneinander lesbar (raus vs. rein).
#
# Wie bei den Absagen steht die Zahl nur an dieser Stelle — Ueberschrift, Fenstergrenze und
# Leertext lesen sie.
BEWORBEN_FENSTER_STUNDEN = 96

# Datenkonvention des JobLog, wortgleich in `pipeline/gmail_ingest.py:258`. Dort ist es der
# Mail-Ingest mit eigenen Abhaengigkeiten — ein gemeinsames Modul nur fuer diesen String waere
# Overkill. Die Doppelung wird durch `test_beworben_marke_deckt_sich_mit_gmail_ingest`
# zusammengehalten, nicht durch Hoffnung.
BEWORBEN_MARKE = "→ Beworben"

# Wochentagskuerzel fuer die Tagesmarke — bewusst eine eigene Liste statt strftime("%a"):
# Letzteres haengt an der Locale des Prozesses und liefert unter der C-Locale „Sat“ statt „Sa“.
def _wochentage():
    """Kürzel Montag bis Sonntag in der Sprache, die beim Erzeugen gilt."""
    return (tx("Mo"), tx("Di"), tx("Mi"), tx("Do"), tx("Fr"), tx("Sa"), tx("So"))


def _e(x):
    return html.escape(str(x)) if x is not None else ""


def _zeitpunkt(wann_utc):
    """Empfangszeit in LOKALER Zeit, mit Tagesmarke, wenn es nicht heute war.

    Zwei Gruende fuer die Umrechnung: Im Fenster liegen Mails mehrerer Tage, die blosse
    Uhrzeit waere also mehrdeutig. Und `received_at` ist UTC — ohne Umrechnung stuende hier
    eine Uhrzeit, die um den Zeitzonen-Versatz von der abweicht, die der Nutzer in seinem
    Postfach sieht (im Sommer zwei Stunden).

    DREI MARKEN, seit das Fenster vier Tage umfasst (31.08.2026): heute nur die Uhrzeit,
    gestern das Wort, alles davor der Wochentag. Die blosse Verlaengerung des Fensters
    haette „gestern“ auch unter Mails von vorgestern und vorvorgestern geschrieben — also
    eine falsche Angabe, keine fehlende. Der Wochentag ist im Vier-Tage-Fenster eindeutig
    und beantwortet genau die Frage, um die es beim Wochenende geht: kam die Absage noch am
    Freitag oder erst danach?

    Seit P2-26 (03.09.2026) wird sie auch vom Beworben-Abschnitt genutzt — dort ist das
    Fenster mit 72 Stunden kuerzer, aber die Logik (heute/gestern/Wochentag) bleibt dieselbe.
    """
    lokal = zeit.nach_lokal(wann_utc)
    tage_her = (datetime.date.today() - lokal.date()).days
    if tage_her <= 0:
        marke = ""
    elif tage_her == 1:
        marke = tx("gestern") + ", "
    else:
        marke = _wochentage()[lokal.weekday()] + ", "
    return marke + tx("{zeit} Uhr", zeit=lokal.strftime("%H:%M"))


def beworben_im_fenster(logs, job_map, jetzt_utc):
    """Die Bewerbungen der letzten BEWORBEN_FENSTER_STUNDEN, neueste zuerst.

    `logs`: alle JobLog-Zeilen. `job_map`: {job_id: Job}. Rueckgabe: Liste von
    `(log, job_oder_None)`, je Job nur der JUENGSTE Beworben-Eintrag.

    Quelle ist bewusst das JobLog, nicht `Application.created_at` oder `.applied_date`: Am
    Bestand vom 03.09.2026 deckt Application nur 4 von 9 tatsaechlichen Bewerbungen der letzten
    72h ab, und `applied_date` ist in allen neun Faellen leer (bestaetigt den P2-17-Befund).
    Der Statuswechsel auf „Beworben" wird dagegen zuverlaessig geloggt.

    Dedup auf den juengsten Eintrag je Job: Ein Job kann den Status mehrfach durchlaufen
    (zurueckgesetzt und neu gesetzt) — ohne Dedup stuende dieselbe Bewerbung zweimal im
    Bericht.
    """
    grenze = jetzt_utc - datetime.timedelta(hours=BEWORBEN_FENSTER_STUNDEN)
    juengste_je_job = {}
    for log in logs:
        if BEWORBEN_MARKE not in log.eintrag or log.created_at < grenze:
            continue
        bisher = juengste_je_job.get(log.job_id)
        if bisher is None or log.created_at > bisher.created_at:
            juengste_je_job[log.job_id] = log
    ausgewaehlt = sorted(juengste_je_job.values(), key=lambda l: l.created_at, reverse=True)
    # Ein Log ohne passenden Job faellt nicht raus (Job koennte geloescht sein) -> (log, None).
    return [(log, job_map.get(log.job_id)) for log in ausgewaehlt]


_KLAMMER_AM_ENDE = re.compile(r"\s*\([^)]*\)\s*$")


def status_kette(logs_heute):
    """Was der Tag mit diesem Job gemacht hat: (vorher, nachher) oder None.

    Zusammengefasst ueber den ganzen Tag: `vorher` ist der Vorstatus des AELTESTEN Wechsels,
    `nachher` der Zielstatus des JUENGSTEN. Ein Job lief am 03.09. `Neu → Pruefen` und danach
    `Pruefen → Beworben`; die ehrliche Tagesbilanz ist `Neu → Beworben`, nicht der letzte
    Schritt allein. Sind beide gleich (hin und zurueck), gilt nur der juengste Wechsel — sonst
    stuende dort faelschlich „Pruefen → Pruefen".

    Eine Vorsortierung von `logs_heute` ist NICHT vorausgesetzt — hier wird selbst sortiert,
    damit der Aufrufer sich darum nicht kuemmern muss.
    """
    wechsel = []
    for log in sorted(logs_heute, key=lambda l: l.created_at):
        eintrag = log.eintrag
        if not eintrag.startswith("Status: ") or " → " not in eintrag:
            continue
        rumpf = eintrag[len("Status: "):]
        # Klammer-Zusatz am ENDE (Herkunftsvermerk wie „(Review)“) ist kein Statusname und
        # faellt weg. Bewusst nur am Zeilenende und nicht ab der ersten Klammer: Traegt eines
        # Tages ein Statusname selbst eine Klammer, wuerde ein Schnitt an der ersten Fundstelle
        # den Pfeil mit abschneiden — der Wechsel fiele danach STUMM aus dem Bericht heraus.
        rumpf = _KLAMMER_AM_ENDE.sub("", rumpf)
        vorher, _, nachher = rumpf.partition(" → ")
        if vorher and nachher:
            wechsel.append((vorher.strip(), nachher.strip()))
    if not wechsel:
        return None
    vorher_gesamt = wechsel[0][0]
    nachher_gesamt = wechsel[-1][1]
    if vorher_gesamt == nachher_gesamt and len(wechsel) > 1:
        return wechsel[-1]
    return (vorher_gesamt, nachher_gesamt)


# Farbzuordnung nach `nachher` bzw. Status, Reihenfolge ist die Prüf-Reihenfolge (§2.3 der
# Spec). Werte aus der bestehenden Digest-Palette abgeleitet (Score-Gruen #18A957,
# Akzent-Cyan #00B4D8, Grau #5F6F84, das bestehende .tag-Rot) — durchweg dunkle Schrift auf
# hellem Grund, Styleguide v5 §18.8 verbietet Weiss auf Gelb/Orange/Cyan/hellem Gruen.
# P2-72: Die Pastelle (`.chg.*` in `_CSS_VORLAGE`) tragen Bedeutung und bleiben feste Werte.
_CHG_FARBEN = (
    ("Beworben", "bew"),
    ("Interview", "iv"),
    ("Absage", "absage"),
    # Alle Endstationen tragen dasselbe Grau wie „Kein Match": Die Spur endet hier, aus welchem
    # Grund auch immer. Ohne diese drei Zeilen faende ein grosser Teil der Stellen im Bestand
    # keine Zuordnung und stuende im Bericht neutral-blau da, also wie etwas, das
    # noch laeuft.
    ("Kein Match", "kein"),
    ("Nicht verfügbar", "kein"),
    ("Beirat abgelehnt", "kein"),
    ("Keine Rückmeldung", "kein"),
    ("Prüfen", "pruef"),
    # „Geparkt" bleibt bewusst NICHT grau: aufgeschoben ist nicht beendet, die Stelle kann
    # wiederkommen. Sie faellt auf „neutral" und hebt sich damit von den Endstationen ab.
)


def _chg_suffix(text):
    for stichwort, suffix in _CHG_FARBEN:
        if stichwort in text:
            return suffix
    return "neutral"


def aenderung_anzeige(job, logs_heute, nur_auto=False):
    """(Text, CSS-Suffix) fuer die rechte Spalte von „Heute geaendert".

    Drei Stufen, in dieser Reihenfolge:
    1. Statuswechsel vorhanden -> „vorher → nachher".
    2. Sonst ein manueller Eintrag (juengster) -> dessen Text, gekuerzt. Ohne Statuswechsel ist
       die Notiz die einzige Information darueber, was passiert ist.
    3. Sonst (kein Log — reiner Feld-Edit) -> der aktuelle Job-Status. Die Zelle bleibt nie
       leer: Der Job steht in der Liste, weil `updated_at` heute ist, eine leere Zelle saehe
       nach einem Fehler aus.

    `nur_auto` (P2-79, Coach-Site): Es zaehlen nur Eintraege mit `art == "auto"`. Das sind die
    Statuswechsel, die die App selbst schreibt (Bestand 16.10.2026: 1095 von 1095). Stufe 2 entfaellt,
    denn der Text einer Verlaufsnotiz gehoert zu „Notizen & Verlauf“ und damit auf die Sperrliste der
    Coach-Site. Auch eine von Hand getippte Zeile „Status: a → b“ wird ignoriert: Sie ist Freitext
    und kein Wechsel, den die App geschrieben hat. Rueckfall ist wie sonst der aktuelle Job-Status.
    """
    if nur_auto:
        logs_heute = [l for l in logs_heute if l.art == "auto"]
    kette = status_kette(logs_heute)
    if kette is not None:
        vorher, nachher = kette
        text = f"{uebersetzt(vorher)} → {uebersetzt(nachher)}"
        return text, _chg_suffix(nachher)

    # Bei `nur_auto` ist die Liste leer: der Filter oben hat alles ausser „auto“ entfernt.
    manuelle = sorted(
        (l for l in logs_heute if l.art == "manuell"), key=lambda l: l.created_at, reverse=True
    )
    if manuelle:
        text = manuelle[0].eintrag
        if len(text) > 60:
            text = text[:60] + "…"
        return text, "neutral"

    return uebersetzt(job.status), "neutral"


def digest_inhalt(fuer_coach: bool = False) -> str:
    """KPIs und Abschnitte des Digest, ohne Seitenhülle (alles zwischen Untertitel und Fußzeile).

    P2-79: Aus `build_digest_html()` herausgelöst, damit die Coach-Site denselben Inhalt in ihre eigene
    Seite setzen kann und nicht einen zweiten Digest nachbaut. `build_digest_html()` ist Hülle plus dieser
    Inhalt und bleibt byte-gleich zu vorher.

    `fuer_coach=True` ist die Fassung für die Coach-Site und folgt deren Sperrliste (Spec Phase 81):
    - „📧 Zu beantworten“ entfällt (Mail-Absender und -Betreff); `needs_reply` wird gar nicht erst gelesen.
    - „🎯 Offene Aktionen (in Prüfung)“ entfällt (Freitext `job.next_step`, Entscheidung vom 16.10.2026).
    - „🔄 Heute geändert“ zeigt nur Statuswechsel aus Einträgen mit `art == "auto"`; kein Notiztext, Rückfall
      ist der aktuelle Job-Status.
    Alles andere bleibt wie im normalen Digest: KPIs, Neue Treffer, Absagen (Firma, Stelle, Empfangszeit,
    Wartezeit; weder Adresse noch Betreff) und Beworben bei.
    """
    today = datetime.date.today()
    with Session(engine) as s:
        jobs = s.exec(select(Job).where(Job.deleted_at.is_(None))).all()   # Phase 32 B — Tombstones raus
        # P2-52 — archivierte Mails (immer "ohne Stelle") raus: der Nutzer hat sie bewusst aus der
        # Inbox geraeumt, sie gehoeren weder unter "Zu beantworten" noch in die Absagen-/
        # Antworten-Zahlen dieses Berichts.
        emails = s.exec(select(Email).where(Email.archived_at.is_(None))).all()
        apps = s.exec(select(Application)).all()
        firmen = {c.id: c.name for c in s.exec(select(Company)).all()}
        logs = s.exec(select(JobLog)).all()   # bedient sowohl §1 (Beworben) als auch §2 (Heute geändert) — nur eine Abfrage

    job_map = {j.id: j for j in jobs}
    neu = sorted([j for j in jobs if j.status == "Neu"], key=lambda j: -(j.match_score or 0))
    # Nur der normale Digest braucht diese beiden (Zu beantworten, Offene Aktionen); für die Coach-Site
    # werden `needs_reply` und `next_step` gar nicht erst gelesen.
    pruefen = [] if fuer_coach else [j for j in jobs if j.status == "Prüfen" and j.next_step]
    to_reply = [] if fuer_coach else [e for e in emails if e.needs_reply]
    responses = [e for e in emails if e.is_response and e.response_time_hours is not None]
    avg = round(sum(e.response_time_hours for e in responses) / len(responses), 1) if responses else None
    # „Heute“ ist der lokale Tag des Nutzers, gespeichert ist naives UTC: siehe `zeit.lokales_datum`.
    changed_today = [j for j in jobs if j.updated_at and zeit.lokales_datum(j.updated_at) == today]

    # Logs nach Job gruppieren — einmal fuer beide Abschnitte (§1 Beworben, §2 Heute geaendert).
    # `logs_heute` nimmt denselben lokalen Tag wie `changed_today`.
    logs_je_job = {}
    for log in logs:
        logs_je_job.setdefault(log.job_id, []).append(log)
    # Coach-Site (P2-79): Vorauswahl auf die automatisch geschriebenen Einträge. Notizen und Chat-Texte
    # gehören zu „Notizen & Verlauf“ (Sperrliste); sie sollen weder Text noch Reihenfolge der Zeilen
    # beeinflussen. `aenderung_anzeige(nur_auto=…)` hält dieselbe Regel noch einmal selbst ein.
    logs_heute_je_job = {
        job_id: [l for l in job_logs
                 if zeit.lokales_datum(l.created_at) == today and (not fuer_coach or l.art == "auto")]
        for job_id, job_logs in logs_je_job.items()
    }

    # Absagen aus dem E-Mail-Check (Wunsch vom 28.08.2026). Quelle ist bewusst die
    # KATEGORIE der Mail, nicht der Job-Status: Der Status kann auch von Hand gesetzt worden
    # sein, hier geht es um das, was der Postfach-Lauf tatsaechlich hereingeholt hat.
    # `direction == incoming` schliesst eigene gesendete Mails aus, die dieselbe Kategorie
    # tragen koennten.
    #
    # ZEITFENSTER: gleitende Stunden, NICHT der Kalendertag (Vorgabe 28.08.2026). Ein
    # Kalendertag verliert systematisch die Abendpost: Eine Absage von gestern 22 Uhr taucht in
    # keinem Bericht auf, den man morgens liest. Wie weit das Fenster zurueckreicht, sagt
    # ABSAGEN_FENSTER_STUNDEN (seit 31.08.2026 vier Tage statt einem — siehe dort).
    #
    # GERECHNET WIRD IN UTC: `email.received_at` kommt aus `gmail_client._iso()` und ist naives
    # UTC (nachgeprueft am 28.08.2026: eine Mail steht als 09:18:27 in der DB, ihr Mail-Header
    # sagt `Fri, 28 Aug 2026 09:18:27 +0000`). Mit `datetime.now()` waere die Fenstergrenze um
    # den UTC-Versatz verschoben — im Sommer in Deutschland um zwei Stunden.
    jetzt_utc = zeit.jetzt_utc()
    grenze = jetzt_utc - datetime.timedelta(hours=ABSAGEN_FENSTER_STUNDEN)

    def _ist_absage(e):
        return e.category == "Absage" and e.direction == "incoming" and e.received_at

    absagen_fenster = sorted([e for e in emails if _ist_absage(e) and e.received_at >= grenze],
                             key=lambda e: e.received_at, reverse=True)
    absagen_woche = [e for e in emails if _ist_absage(e)
                     and e.received_at >= jetzt_utc - datetime.timedelta(days=7)]

    # Beworben bei (P2-26, 03.09.2026). Quelle und Dedup: siehe `beworben_im_fenster`.
    beworben = beworben_im_fenster(logs, job_map, jetzt_utc)
    # Der Wochenwert zaehlt BEWERBUNGEN, nicht Log-Zeilen — also je Job einmal, genau wie das
    # 72-Stunden-Fenster darueber. Am Bestand vom 03.09.2026 hat ein Job zwei
    # `→ Beworben`-Eintraege innerhalb der Woche (Status zurueckgesetzt und neu gesetzt);
    # ungededupliziert stuende unter dem Abschnitt eine Zahl, die sich mit seiner eigenen
    # Ueberschrift nicht vergleichen laesst. Bei den Absagen ist das anders und richtig so:
    # dort ist jede Zeile eine eigene MAIL.
    beworben_woche_grenze = jetzt_utc - datetime.timedelta(days=7)
    beworben_woche = {
        log.job_id for log in logs
        if BEWORBEN_MARKE in log.eintrag and log.created_at >= beworben_woche_grenze
    }

    def score_badge(sc):
        if not sc:
            # unbewertet = Grau (§18.4 score.none) mit Navy-Text — nie weiß auf hellem Grau
            farbe, text = zustandsfarben.SCORE_NICHT_BEWERTET
            return f'<span class="badge" style="background:{farbe};color:{text}">–</span>'
        farbe, text = score_farben(sc)
        return f'<span class="badge" style="background:{farbe};color:{text}">{sc}</span>'

    def job_rows(items, empty):
        if not items:
            return f'<div class="empty">{empty}</div>'
        out = []
        for j in items[:15]:
            out.append(f'<div class="row">{score_badge(j.match_score)}<b>{_e(j.company_name)}</b>'
                       f'<span>{_e(j.title)}</span><span class="muted">· {_e(j.location) or ""}</span></div>')
        return "".join(out)

    kpis = [
        (tx("Stellen"), len(jobs), False), (tx("Top-Zielstellen ≥4"), sum(1 for j in jobs if (j.match_score or 0) >= 4), True),
        (tx("Bewerbungen"), len(apps), False), (tx("Antworten"), len(responses), False),
        (tx("Ø Antwortzeit"), f"{avg} h" if avg is not None else "–", False),
        (tx("Neu zu sichten"), len(neu), True),
    ]
    kpi_html = "".join(
        f'<div class="kpi {"acc" if acc else ""}"><div class="n">{v}</div><div class="l">{_e(l)}</div></div>'
        for l, v, acc in kpis
    )

    def _wartezeit(stunden):
        """Wie lange die Firma gebraucht hat — Stunden bis 48 h, danach Tage.

        Die Zahl stammt aus `email.response_time_hours` und ist seit P2-17 (Phase 92) gegen die
        RICHTIGE Bewerbung gerechnet; vorher lief sie bei mehrfach angeschriebenen Firmen gegen
        die aelteste Bewerbung und war teils um den Faktor 18 zu hoch.
        """
        if stunden is None:
            return None
        if stunden < 48:
            return tx("nach {stunden} h", stunden=round(stunden))
        tage = round(stunden / 24)
        if tage == 1:
            return tx("nach {tage} Tag", tage=tage)
        return tx("nach {tage} Tagen", tage=tage)

    def absage_rows(items):
        if not items:
            return ('<div class="empty">'
                    + tx("In den letzten {stunden} Stunden keine Absagen.", stunden=ABSAGEN_FENSTER_STUNDEN)
                    + "</div>")
        out = []
        for e in items:
            job = job_map.get(e.job_id)
            firma = (job.company_name if job else None) or firmen.get(e.company_id) or tx("Firma unbekannt")
            stelle = (job.title if job else None) or tx("ohne Stellenzuordnung")
            details = [_zeitpunkt(e.received_at)]
            wartezeit = _wartezeit(e.response_time_hours)
            if wartezeit:
                details.append(wartezeit)
            out.append('<div class="row"><span class="tag">' + tx("Absage") + '</span>'
                       + "<b>" + _e(firma) + "</b><span>" + _e(stelle) + "</span>"
                       + '<span class="muted">· ' + _e(" · ".join(details)) + "</span></div>")
        return "".join(out)

    def beworben_rows(items):
        if not items:
            return ('<div class="empty">'
                    + tx("In den letzten {stunden} Stunden keine Bewerbungen.", stunden=BEWORBEN_FENSTER_STUNDEN)
                    + "</div>")
        out = []
        for log, job in items[:15]:
            firma = (job.company_name if job else None) or tx("Firma unbekannt")
            stelle = (job.title if job else None) or tx("ohne Stellenzuordnung")
            out.append('<div class="row">' + score_badge(job.match_score if job else None)
                       + "<b>" + _e(firma) + "</b><span>" + _e(stelle) + "</span>"
                       + '<span class="muted">· ' + _e(_zeitpunkt(log.created_at)) + "</span></div>")
        rest = len(items) - 15
        if rest > 0:
            out.append(f'<div class="empty">{tx("… und {anzahl} weitere", anzahl=rest)}</div>')
        return "".join(out)

    def geaendert_rows(items, logs_nach_job):
        # `job_rows` bleibt fuer „Neue Treffer" und „Offene Aktionen" unangetastet — die
        # bleiben einspaltig. Diese Funktion bedient ausschliesslich „Heute geaendert".
        if not items:
            return '<div class="empty">' + tx("Heute noch keine Änderungen.") + '</div>'

        def juengstes_log(j):
            job_logs = logs_nach_job.get(j.id) or []
            return max((l.created_at for l in job_logs), default=None)

        # Jobs ohne Log sollen ans Ende, nicht nach vorn springen — deshalb zwei Gruppen statt
        # eines einzigen Sorts mit Ersatzwert.
        mit_log = sorted(
            (j for j in items if juengstes_log(j) is not None), key=juengstes_log, reverse=True
        )
        ohne_log = [j for j in items if juengstes_log(j) is None]
        sortiert = mit_log + ohne_log

        out = []
        for j in sortiert[:15]:
            text, suffix = aenderung_anzeige(j, logs_nach_job.get(j.id) or [], nur_auto=fuer_coach)
            out.append(
                '<div class="row zwei"><span class="links">' + score_badge(j.match_score)
                + "<b>" + _e(j.company_name) + "</b><span>" + _e(j.title) + "</span>"
                + '<span class="muted">· ' + _e(j.location) + "</span></span>"
                + '<span class="chg ' + suffix + '">' + _e(text) + "</span></div>"
            )
        rest = len(sortiert) - 15
        if rest > 0:
            out.append(f'<div class="empty">{tx("… und {anzahl} weitere", anzahl=rest)}</div>')
        return "".join(out)

    # Einordnung unter den Absagen: die einzige Groessenordnung im Bericht. Sie beantwortet,
    # ob diese vier Tage viel oder wenig waren. Eine Zeile „Gestern: n“ gaebe es hier nicht mehr
    # sinnvoll — sie laege mitten im Fenster und zaehlte dieselben Mails ein zweites Mal.
    absagen_kontext = tx("Letzte 7 Tage: {anzahl}", anzahl=len(absagen_woche))
    # Dieselbe Einordnung fuer den Beworben-Abschnitt — beantwortet: viel oder wenig fuer diese Woche?
    beworben_kontext = tx("Letzte 7 Tage: {anzahl}", anzahl=len(beworben_woche))

    # Die Abschnitte als Liste, damit die Coach-Fassung zwei davon einfach auslaesst (P2-79). Ohne
    # Auslassung ergibt `"\n".join(...)` genau den Text, den die frühere durchgehende Vorlage hatte.
    abschnitte = [
        f'<div class="kpis">{kpi_html}</div>',
        f'<section><h2>{tx("✨ Neue Treffer zum Sichten ({anzahl})", anzahl=len(neu))}</h2>{job_rows(neu, tx("Keine neuen Treffer."))}</section>',
    ]
    if not fuer_coach:
        reply_html = "".join(
            f'<div class="row"><span class="tag">{tx("Antwort")}</span><b>{_e(e.from_addr)}</b><span>{_e(e.subject)}</span></div>'
            for e in to_reply[:15]
        ) or '<div class="empty">' + tx("Keine offenen Antworten.") + '</div>'
        abschnitte.append(f'<section><h2>{tx("📧 Zu beantworten ({anzahl})", anzahl=len(to_reply))}</h2>{reply_html}</section>')
    abschnitte += [
        f'''<section><h2>{tx("🚫 Absagen der letzten {stunden} Stunden ({anzahl})", stunden=ABSAGEN_FENSTER_STUNDEN, anzahl=len(absagen_fenster))}</h2>{absage_rows(absagen_fenster)}
<div class="muted" style="font-size:12px;margin-top:10px">{_e(absagen_kontext)}</div></section>''',
        f'''<section><h2>{tx("📤 Beworben bei — letzte {stunden} Stunden ({anzahl})", stunden=BEWORBEN_FENSTER_STUNDEN, anzahl=len(beworben))}</h2>{beworben_rows(beworben)}
<div class="muted" style="font-size:12px;margin-top:10px">{_e(beworben_kontext)}</div></section>''',
    ]
    if not fuer_coach:
        steps_html = "".join(
            f'<div class="row">{score_badge(j.match_score)}<b>{_e(j.company_name)}</b><span class="muted">{_e(j.next_step)}</span></div>'
            for j in pruefen[:15]
        ) or '<div class="empty">' + tx("Keine offenen Aktionen.") + '</div>'
        abschnitte.append(f'<section><h2>{tx("🎯 Offene Aktionen (in Prüfung)")}</h2>{steps_html}</section>')
    abschnitte.append(
        f'<section><h2>{tx("🔄 Heute geändert ({anzahl})", anzahl=len(changed_today))}</h2>'
        f'{geaendert_rows(changed_today, logs_heute_je_job)}</section>')
    return "\n".join(abschnitte)


def build_digest_html(zurueck_zu: str | None = None) -> str:
    """Der vollständige Digest als eigenständige HTML-Seite: Hülle plus `digest_inhalt()`.
    `zurueck_zu`: Ziel des Links „← Zurück zum Dashboard“ oben links. Nur die App setzt ihn; die Datei des
    Tageslaufs wird aus dem Finder geöffnet, dort führte ein Link auf „/“ ins Leere."""
    today = datetime.date.today()
    from pipeline.user_profile import user_name

    # P2-72: Das Design gilt, wie es JETZT ist (Icon und CSS bei jedem Aufruf frisch gelesen).
    geltend = design.laden()
    css = _css(geltend)
    zurueck = ""
    if zurueck_zu:
        css += _CSS_ZURUECK.substitute(markenwerte(geltend)) + "\n"
        zurueck = f'<a class="zurueck" href="{_e(zurueck_zu)}">{tx("← Zurück zum Dashboard")}</a>\n'
    titel = tx("Tages-Digest {datum}", datum=today)
    kopf_titel = tx("Bewerbungs-Digest")
    foot = tx("Bewerbungs-Mgmt · erzeugt am {datum}", datum=today.strftime("%Y-%m-%d"))
    foot_quelle = tx("Automatischer Tages-Digest · Quelle: bewerbung.sqlite")
    return f"""<!doctype html><html lang="{html_lang()}"><head><meta charset="utf-8">{favicon.favicon_link(geltend)}
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{titel}</title>
<style>{css}</style></head><body><div class="wrap">
{zurueck}<h1>{kopf_titel}</h1><div class="sub">{_e(user_name())} · {datum(today)}</div>
{digest_inhalt()}
<div class="foot"><span>{foot}</span><span>{foot_quelle}</span></div>
</div></body></html>"""


if __name__ == "__main__":
    from pathlib import Path
    from app.naming import dated_filename
    out_dir = Path(__file__).resolve().parent.parent.parent / "data" / "digests"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / dated_filename("Bewerbungs-Digest", "html")
    out.write_text(build_digest_html(), encoding="utf-8")
    print("Gespeichert:", out)
