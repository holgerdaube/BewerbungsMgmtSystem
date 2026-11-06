#!/usr/bin/env python3
"""Sucheinstellungen: DB (`SuchEinstellung`) <-> `config/suchprofile.yaml` (Phase 49).

`config/suchprofile.yaml` bleibt der VERTRAG zur Jobsuche — 9 unabhängige Stellen (5 Skills,
4 Python-Loader) lesen die Datei direkt, das Backend gehört NICHT dazu. Die DB ist seit dieser
Phase die Quelle der Wahrheit für die drei Pläne A/B/C + den globalen Suchbereich/die
Firmengröße; dieses Modul schreibt die Datei bei jedem Save neu (Muster Profil-Seite →
`main.py::_profil_struktur_schreiben` — komplett neu erzeugt, nicht gepatcht).

Kommentar-erhaltender Marker-Split-Writer (KEIN neues Dependency — PyYAML 6.0.3 im venv kann
beim Neuschreiben keine Kommentare erhalten): alles UNTERHALB von MARKER sind manuell gepflegte
Technik-Parameter (Portale, Apify-Actors, Restructuring-Radar, Ausschlüsse, Mail-Alerts,
Repost-Erkennung) — der Writer fasst diesen Teil NIE an, ersetzt nur den Kopf darüber.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SUCHPROFILE_PATH = PROJECT_ROOT / "config" / "suchprofile.yaml"

MARKER = "# <<< ENDE AUTO-GENERIERT (EINSTELLUNGEN) — ab hier manuell gepflegte Technik-Parameter <<<"
HEADER = ("# >>> AUTO-GENERIERT aus der Einstellungen-Seite (/einstellungen) — NICHT händisch\n"
          "# editieren, wird beim nächsten Speichern überschrieben. Technik-Parameter stehen\n"
          "# unterhalb des Markers und werden vom Writer NIE angefasst. >>>\n")

# Feste Bucket-Identitäten (Job.tab referenziert sie) — nur die drei aktiv-Schalter + beim
# Umkreis-Bucket Stadt/Umkreis-km sind editierbar (Design-Entscheidung 6). MVP-Grenze: eine
# kuratierte Ortsliste rund um den Umkreis-Mittelpunkt wird NICHT aus Stadt+km abgeleitet
# (bleibt Nachrüst-Punkt) — der Umkreis-Bucket bekommt beim Regenerieren nur `regionen: [stadt]`.
_REMOTE_REGIONEN = ["Remote EMEA", "Remote DACH", "Remote Germany"]
_DEUTSCHLANDWEIT_REGIONEN = ["Deutschland"]

# Reiner Alt-Feld-Spiegel ohne Entsprechung im neuen Plan-Modell — kein Code liest ihn
# strukturiert (Design-Entscheidung 3), deshalb kein UI-Feld dafür. Neue Installationen starten
# leer, weil die Läufe die Datei lesen und sonst jede Stelle unterhalb von „Manager“ bemängeln.
# Ein Wert, der schon in der Datei steht, bleibt erhalten (`schreibe_suchprofile`).
_SENIORITY_MIN = ""

_PLAN_KEYS = ("plan", "label", "aktiv", "prioritaet", "titel", "senioritaet", "branche")

# Phase 87 — sechs Standard-Suchportale für Deutschland + zwei leere Freizeilen (Design-
# Entscheidung 4: feste Zahl Zeilen, keine „Zeile hinzufügen“). Alle sechs URLs am 21.08.2026
# live geprüft (Bau-Spec Phase 87, Bewertungstabelle): LinkedIn/Xing/Nejo/Arbeitsagentur
# antworten mit HTTP 200 und substanziellem Inhalt (grün); Indeed liefert HTTP 403
# (Bot-Schutz) und StepStone HTTP 200 mit nur ~2 KB (vermutlich JS-Rendering) — beide amber,
# bleiben aber als Default AKTIV, weil ihr tatsächlicher Suchkanal die Websuche ist, nicht der
# Direktabruf (Design-Entscheidung 1: `zugriff` unterscheidet websearch/fetch). Die
# Arbeitsagentur-URL ist die in Phase 86 verifizierte SSR-Suchseite (der alte REST-Endpunkt
# liefert seit ≥13.08.2026 durchgängig 403).
#
# P2-73 (13.10.2026): Nejo ist von `mynejo.com/de-de/jobs` nach `nejo.com/de/jobs` umgezogen
# (301 seit 21.09.2026), die Arbeitsagentur leitet auf dieselbe Adresse mit `suchbereich=jobs`
# um. Beide Einträge tragen jetzt das Ziel, das ohne Umleitung mit HTTP 200 antwortet. Die
# früheren Adressen stehen unten in `PORTALE_FRUEHERE_STANDARDS`.
PORTALE_DEFAULT = [
    {"key": "linkedin", "name": "LinkedIn",
     "url": "https://www.linkedin.com/jobs/search/?keywords=$QUERY&location=$LOCATION",
     "zugriff": "websearch", "aktiv": True, "standard": True},
    {"key": "indeed", "name": "Indeed",
     "url": "https://de.indeed.com/jobs?q=$QUERY&l=$LOCATION",
     "zugriff": "websearch", "aktiv": True, "standard": True},
    {"key": "stepstone", "name": "StepStone",
     "url": "https://www.stepstone.de/jobs?what=$QUERY&where=$LOCATION",
     "zugriff": "websearch", "aktiv": True, "standard": True},
    {"key": "xing", "name": "Xing",
     "url": "https://www.xing.com/jobs/search?keywords=$QUERY",
     "zugriff": "websearch", "aktiv": True, "standard": True},
    {"key": "nejo", "name": "Nejo",
     "url": "https://nejo.com/de/jobs?q=$QUERY&page=$PAGE",
     "zugriff": "fetch", "aktiv": True, "standard": True},
    {"key": "arbeitsagentur", "name": "Arbeitsagentur",
     "url": "https://www.arbeitsagentur.de/jobsuche/suche?angebotsart=1&was=$QUERY&suchbereich=jobs",
     "zugriff": "fetch", "aktiv": True, "standard": True},
    {"key": "frei1", "name": "", "url": "", "zugriff": "websearch", "aktiv": False, "standard": False},
    {"key": "frei2", "name": "", "url": "", "zugriff": "websearch", "aktiv": False, "standard": False},
]

# P2-73 — Adressen, die früher Standard waren. Zieht ein Portal um, leitet die alte Adresse nur
# noch um; ein Such-Agent folgt einer Umleitung auf einen anderen Host aber nicht von selbst
# (WebFetch meldet sie und verlangt einen zweiten Abruf). Gemessen: Vom 21.09. bis 13.10.2026
# kostete deshalb jeder Nejo-Abruf zwei der fünf Abrufe eines Such-Agenten, an einem Tag blieb
# der Folgeabruf ganz aus. Ein neuer Wert in `PORTALE_DEFAULT` allein hilft keiner bestehenden
# Installation: Die Liste liegt dort schon in der Datenbank und im Kopf der Suchprofil-Datei.
# Ändert sich künftig wieder eine Standard-Adresse: die ABGELÖSTE hier eintragen.
PORTALE_FRUEHERE_STANDARDS = {
    "nejo": ("https://mynejo.com/de-de/jobs?q=$QUERY&page=$PAGE",),
    "arbeitsagentur": ("https://www.arbeitsagentur.de/jobsuche/suche?angebotsart=1&was=$QUERY",),
}


def _ist_fruehere_standardadresse(portal) -> bool:
    return (isinstance(portal, dict)
            and str(portal.get("url") or "").strip() in PORTALE_FRUEHERE_STANDARDS.get(portal.get("key"), ()))


def standard_adressen_nachziehen(portale: list) -> tuple[list, list]:
    """Ersetzt abgelöste Standard-Adressen durch die heutigen (P2-73).

    Eine Adresse wird NUR ersetzt, wenn sie wörtlich einer früheren Standard-Adresse ihres Portals
    entspricht. Hat der Nutzer sie geändert, bleibt sie stehen, auch wenn sie auf denselben Host
    zeigt: Dann war es eine Entscheidung, kein Altbestand. Alle übrigen Felder (Name, Zugriff,
    aktiv) bleiben unberührt. Gibt die neue Liste und die Schlüssel der geänderten Portale zurück;
    die übergebene Liste wird nicht verändert."""
    aktuell = {p["key"]: p["url"] for p in PORTALE_DEFAULT}
    neu, geaendert = [], []
    for portal in portale:
        if _ist_fruehere_standardadresse(portal):
            portal = {**portal, "url": aktuell[portal["key"]]}
            geaendert.append(portal["key"])
        neu.append(portal)
    return neu, geaendert


def kopf_hat_fruehere_standardadresse(pfad: Path = None) -> bool:
    """True, wenn im Kopf der Suchprofil-Datei noch eine abgelöste Standard-Adresse steht.

    Eigene Prüfung neben der Datenbank, weil beide auseinanderlaufen können: Eine Zeile mit leerer
    Portal-Liste (Altbestand vor Phase 87) zeigt in der Oberfläche schon die neuen Standards, im
    Kopf der Datei steht aber noch, was beim letzten Speichern galt. Die Such-Skills lesen die
    Datei. Eine fehlende oder unlesbare Datei ist hier kein Fehler, sondern „nichts zu tun“."""
    pfad = pfad or SUCHPROFILE_PATH
    try:
        daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return False
    portale = daten.get("portale") if isinstance(daten, dict) else None
    return isinstance(portale, list) and any(_ist_fruehere_standardadresse(p) for p in portale)


# P2-51 (V7) — Umkreis-Bezeichnung: bleibt die KENNUNG (Job.tab/Company.region referenzieren sie
# als Text, s. Entscheidung 5 der Bau-Spec), aber Stadt-Kurzform und Label-Bau sind jetzt EIGENE,
# getestete Funktionen statt eines inline `stadt.split()[0]` — der frühere Kurzform-Bug machte aus
# „Bad Homburg" „Bad" (nur das erste Wort), weil ein Namenszusatz wie „vor der Höhe" nicht erkannt
# wurde.
_STADT_TRENNER = (" am ", " an der ", " an ", " im ", " in der ", " ob der ", " vor der ",
                  " bei ", " (", "/")


def stadt_kurzform(stadt: str) -> str:
    """Teil vor dem ERSTEN Namenszusatz (V7, Tabelle in der Bau-Spec), sonst der volle,
    getrimmte Name. „Frankfurt am Main" -> „Frankfurt", „Bad Homburg vor der Höhe" ->
    „Bad Homburg", „Halle (Saale)" -> „Halle", „St. Gallen" -> „St. Gallen" (kein Trenner)."""
    stadt = (stadt or "").strip()
    fruehester = None
    for trenner in _STADT_TRENNER:
        i = stadt.find(trenner)
        if i != -1 and (fruehester is None or i < fruehester):
            fruehester = i
    return stadt if fruehester is None else stadt[:fruehester].strip()


def _umkreis_km_normalisiert(umkreis: dict) -> int:
    """Ganzzahliges `umkreis_km` > 0, sonst 100 (V7) — EINE Stelle für Label UND Bucket-Wert,
    damit beide nie auseinanderlaufen."""
    try:
        km = int(umkreis.get("umkreis_km"))
    except (TypeError, ValueError):
        km = 0
    return km if km > 0 else 100


def umkreis_label(umkreis: dict) -> str | None:
    """„<Stadt-Kurzform> +<km>km" (V7) — Stadt leer/fehlend -> None. Dieselbe Bezeichnung
    steht als Bucket-Schlüssel in `config/suchprofile.yaml` (s. `baue_managed`) UND als
    `Job.tab`/`Company.region` (Design-Entscheidung 5: die Bezeichnung bleibt die Kennung)."""
    stadt = (umkreis.get("stadt") or "").strip()
    if not stadt:
        return None
    return f"{stadt_kurzform(stadt)} +{_umkreis_km_normalisiert(umkreis)}km"


def aktuelles_umkreis_label(session) -> str | None:
    """Aktuelles Umkreis-Label (V7) aus der `SuchEinstellung`-Singleton-Zeile — Quelle der
    Wahrheit für `tab_normalisieren()` beim Ingest (`pipeline.ingest`) und beim manuellen
    Anlegen/Ändern einer Stelle (`main.py::create_job`/`update_job`). Keine Zeile (noch nie
    gespeichert) -> None, OHNE sie hier lazy anzulegen (das bleibt allein
    `main.py::_einstellungen_singleton()` beim GET vorbehalten). Lokaler statt modulweiter
    Import von `app.models`: dieses Modul bleibt so frei von einer harten SQLModel/DB-
    Abhängigkeit, solange nur die reinen YAML-Funktionen oben genutzt werden (z. B. in
    Tests/Skripten ohne DB)."""
    from app.models import SuchEinstellung
    e = session.get(SuchEinstellung, 1)
    if not e:
        return None
    return umkreis_label(json.loads(e.suchbereich_json).get("umkreis") or {})


_UMKREIS_MUSTER = re.compile(r"^.+\s\+\s?\d+\s?km$", re.IGNORECASE)


def tab_normalisieren(wert: str | None, label: str | None) -> str | None:
    """Vereinheitlicht einen rohen `tab`-Wert (V7) — genutzt von `pipeline.ingest`
    (Record-Feld `tab`) sowie `POST /api/jobs`/`PATCH /api/jobs/{id}` in `main.py`: leer -> None;
    „remote"/„deutschlandweit" in beliebiger Schreibung -> die kanonische Form; ein Wert im
    Umkreis-Muster („… +<km>km") UND ein aktuelles `label` -> `label` (eine mitgeschickte, aber
    inzwischen umbenannte Umkreis-Bezeichnung landet so automatisch auf der aktuellen statt eine
    zweite, veraltete Kennung in der DB anzulegen); alles andere bleibt unverändert."""
    wert = (wert or "").strip()
    if not wert:
        return None
    niedrig = wert.lower()
    if niedrig == "remote":
        return "Remote"
    if niedrig == "deutschlandweit":
        return "Deutschlandweit"
    if label and _UMKREIS_MUSTER.match(wert):
        return label
    return wert


def _plan_by(plaene: list, name: str) -> dict:
    return next((p for p in plaene if p.get("plan") == name), {})


def _vereinigung(plaene: list, feld: str) -> list:
    """Union eines Listenfelds über die AKTIVEN Pläne, Reihenfolge = erste Nennung (Priorität A→B→C)."""
    ergebnis: list = []
    for p in plaene:
        if not p.get("aktiv"):
            continue
        for wert in p.get(feld) or []:
            if wert not in ergebnis:
                ergebnis.append(wert)
    return ergebnis


def baue_managed(min_mitarbeiter: int, suchbereich: dict, plaene: list, portale: list = None) -> dict:
    """DB-Werte → managed dict für die YAML (Design-Entscheidung 3): `plaene` NEU/strukturiert,
    `titel_plan_a/b/c` + `seniority_min/ziel` + `branche` als flache Alt-Spiegel (Abwärtskompa-
    tibilität für die 9 Konsumenten), `buckets` aus `suchbereich` regeneriert, `min_mitarbeiter`
    aus der DB. Alle Spiegel entstehen HIER aus derselben DB — kein Drift-Risiko.

    Phase 87 — `portale` wandert unverändert (Liste von Dicts) in den Kopf; s. Fallstrick C1 der
    Bau-Spec: der Rumpf-Block heißt seither `portale_technik`, sonst gäbe es den Schlüssel
    `portale` ZWEIMAL auf gleicher Ebene und `yaml.safe_load` nähme still den letzten (den
    Rumpf) — die Einstellungen wären wirkungslos, ohne dass irgendwo ein Fehler auftaucht.
    Leere/fehlende Liste (Alt-Zeile vor dem ersten Save dieser Phase, s. `app/db.py::
    _ADD_COLUMNS`) fällt auf `PORTALE_DEFAULT` zurück — dasselbe Auffüll-Muster wie bei
    `modelle` in `main.py::_einstellungen_out()`, hier aber an der einzigen Stelle nötig, die
    TATSÄCHLICH in die YAML schreibt: ein leerer Kopf würde die Suche sonst still auf null
    Portale reduzieren (Design-Entscheidung 3: „ein Bereich, der nur Text speichert, wäre
    Fassade“)."""
    plan_a = _plan_by(plaene, "A")
    plan_b = _plan_by(plaene, "B")
    plan_c = _plan_by(plaene, "C")

    # list(...)-Kopien überall: dieselbe Liste darf im `managed`-Objektgraphen NICHT mehrfach
    # referenziert werden, sonst dumpt PyYAML Anchors/Aliases (&id001/*id001) statt echter Listen
    # — technisch von yaml.safe_load identisch lesbar, aber schlechter Stil für eine Datei, die
    # als „nicht mehr von Hand editieren" markiert ist, UND ein Mutations-Fallstrick (Ändern der
    # einen Kopie würde unbemerkt die andere mitändern). Bug gefunden + gefixt 22.07.2026 beim
    # ersten echten PATCH-Testlauf (Tail-Diff bestand, aber der Kopf enthielt Anchors).
    buckets: dict = {}
    if suchbereich.get("remote", {}).get("aktiv"):
        buckets["Remote"] = {"regionen": list(_REMOTE_REGIONEN), "umzug_ko": True}
    if suchbereich.get("deutschlandweit", {}).get("aktiv"):
        buckets["Deutschlandweit"] = {"regionen": list(_DEUTSCHLANDWEIT_REGIONEN), "umzug_ko": True}
    umkreis = suchbereich.get("umkreis") or {}
    stadt = (umkreis.get("stadt") or "").strip()
    if umkreis.get("aktiv") and stadt:
        # Bucket-SCHLÜSSEL braucht die Stadt-KURZFORM (Design-Entscheidung 6: „<Stadt-Kurzform>
        # +<km>km" — Job.tab referenziert diesen String als STABILES Label). Die Kurzform-Regel
        # steht jetzt in `stadt_kurzform()` (P2-51, V7) — NICHT mehr `stadt.split()[0]` (Bug
        # gefunden + gefixt 22.07.2026: das erste Wort allein macht aus einem mehrteiligen
        # Stadtnamen mit Namenszusatz eine falsche Kurzform). P2-51 zusätzlich: KEIN Rückfall
        # mehr auf eine feste Default-Stadt, wenn „aktiv" ohne Stadt gespeichert ist — der Bucket
        # entfällt dann einfach (s. Bedingung oben), statt eine geratene Stadt zu buckettieren.
        buckets[umkreis_label(umkreis)] = {
            "regionen": [stadt], "onsite_ok": True,
            "stadt": stadt, "umkreis_km": _umkreis_km_normalisiert(umkreis),
        }

    def _plan_kopie(p: dict) -> dict:
        return {k: (list(p[k]) if isinstance(p.get(k), list) else p.get(k)) for k in _PLAN_KEYS}

    # Phase 87 — frische Dict-Kopien (kein geteiltes Objekt mit dem Aufrufer/der DB-Zeile),
    # aus demselben Anker-Grund wie bei den Plänen oben; Fallback auf PORTALE_DEFAULT, s. Docstring.
    portale_liste = [dict(p) for p in (portale or PORTALE_DEFAULT)]

    return {
        "plaene": [_plan_kopie(plan_a), _plan_kopie(plan_b), _plan_kopie(plan_c)],
        "titel_plan_a": list(plan_a.get("titel") or []),
        "titel_plan_b": list(plan_b.get("titel") or []),
        "titel_plan_c": list(plan_c.get("titel") or []),
        "seniority_min": _SENIORITY_MIN,
        "seniority_ziel": _vereinigung(plaene, "senioritaet"),
        "branche": _vereinigung(plaene, "branche"),
        "buckets": buckets,
        "min_mitarbeiter": min_mitarbeiter,
        "portale": portale_liste,
    }


def schreibe_suchprofile(managed: dict, pfad: Path) -> None:
    """Ersetzt NUR den Kopf oberhalb von MARKER — der Rest (Technik-Parameter samt Kommentaren)
    bleibt byte-genau erhalten. Wirft, wenn der Marker fehlt (Schutz: dann ist die einmalige
    Umstrukturierung noch nicht gelaufen — NIE ungeprüft überschreiben, sonst gehen kalibrierte
    Technik-Kommentare verloren)."""
    text = pfad.read_text(encoding="utf-8")
    i = text.find(MARKER)
    if i == -1:
        raise RuntimeError(
            "MARKER fehlt in suchprofile.yaml — einmalige Umstrukturierung (Phase 49 Stufe A) "
            "nötig, sonst würden die manuell gepflegten Technik-Kommentare überschrieben."
        )
    tail = text[i:]
    bisher = (yaml.safe_load(text[:i]) or {}).get("seniority_min")
    if bisher:
        managed = {**managed, "seniority_min": bisher}
    head = HEADER + yaml.safe_dump(managed, allow_unicode=True, sort_keys=False, width=1000)
    pfad.write_text(head + "\n" + tail, encoding="utf-8")


def seed_aus_yaml(pfad: Path) -> dict:
    """Einmalige Migration (Design-Entscheidung 5): liest die HEUTIGEN YAML-Werte und leitet die
    initialen DB-Werte ab — Plan A aus `titel_plan_a`, Plan B aus `titel_plan_b`, beide mit den
    heute GLOBALEN `seniority_ziel`/`branche` dupliziert (die Pläne teilten sich diese Werte
    bislang); Plan C leer/inaktiv. `buckets` → `suchbereich` (aktive Bucket-Namen → Schalter; der
    Umkreis-Bucket → Stadt/Radius aus seinen eigenen Feldern `stadt`/`umkreis_km`, bei einem
    älteren Kopf ohne diese Felder aus `regionen[0]` bzw. der Zahl im Bucket-Namen, s.
    `umkreis_label`/P2-51 V7; kein Umkreis-Bucket → Stadt leer, KEIN Default-Rückfall auf eine
    feste Stadt). Wird NUR beim allerersten GET aufgerufen (danach ist die DB die Quelle der
    Wahrheit) — schreibt selbst NIE in die YAML.

    Phase 87 — `portale` kommt bewusst NICHT aus der YAML: der alte Rumpf-Block `portale:`
    (jetzt `portale_technik:`) ist ein Dict mit Apify-/Websearch-/Nejo-/Arbeitsagentur-Unter-
    schlüsseln, keine Liste von Name/URL/Zugriff-Objekten — die beiden Strukturen haben keine
    sinnvolle Entsprechung. Seed kommt deshalb direkt aus `PORTALE_DEFAULT`."""
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    seniority_ziel = list(daten.get("seniority_ziel") or [])
    branche = list(daten.get("branche") or [])

    plaene = [
        {"plan": "A", "label": "Plan A", "aktiv": True, "prioritaet": 1,
         "titel": list(daten.get("titel_plan_a") or []), "senioritaet": seniority_ziel, "branche": branche},
        {"plan": "B", "label": "Plan B", "aktiv": True, "prioritaet": 2,
         "titel": list(daten.get("titel_plan_b") or []), "senioritaet": seniority_ziel, "branche": branche},
        {"plan": "C", "label": "Plan C", "aktiv": False, "prioritaet": 3,
         "titel": [], "senioritaet": [], "branche": []},
    ]

    buckets = daten.get("buckets") or {}
    umkreis_name = next((b for b in buckets if b not in ("Remote", "Deutschlandweit")), None)
    umkreis = {"aktiv": False, "stadt": "", "umkreis_km": 100}
    if umkreis_name:
        bucket = buckets.get(umkreis_name) or {}
        stadt = bucket.get("stadt")
        if not stadt:
            regionen = bucket.get("regionen") or []
            stadt = regionen[0] if regionen else ""
        km = bucket.get("umkreis_km")
        if km is None:
            treffer = re.search(r"\+\s*(\d+)\s*km", umkreis_name)
            km = int(treffer.group(1)) if treffer else 100
        umkreis = {"aktiv": True, "stadt": stadt, "umkreis_km": km}
    suchbereich = {
        "remote": {"aktiv": "Remote" in buckets},
        "deutschlandweit": {"aktiv": "Deutschlandweit" in buckets},
        "umkreis": umkreis,
    }

    return {"min_mitarbeiter": daten.get("min_mitarbeiter", 100), "suchbereich": suchbereich, "plaene": plaene,
            "portale": [dict(p) for p in PORTALE_DEFAULT]}


# Technik-Rumpf einer frisch angelegten Datei (Phase 100, s. `sicherstellen()`): bewusst
# schlank und ohne erfundene Inhalte — nur die Schlüssel, deren FEHLEN echte Läufe abbricht,
# plus die empirisch kalibrierten `dedup_text`-Werte, die ein neuer Nutzer nicht raten soll
# (leeres Dict = Modul-Defaults aus `pipeline/dedup_text.py`, exakt derselbe Code-Pfad).
_START_RUMPF = """
# Ab hier: manuell gepflegte Technik-Parameter. Diese Fassung wurde beim ersten Start
# automatisch angelegt (Phase 100) — sie macht die App lauffähig, ersetzt aber NICHT das
# Ausfüllen der Zielrollen unter /einstellungen. Anleitung: docs/INSTALLATION.md.

portale_technik: {}

# Repost-/Dublettenerkennung: leeres Dict = die kalibrierten Modul-Defaults
# (Schwelle 0.045 / Titel 0.45 / 400 Zeichen / 5 Wörter). Nicht auf Verdacht ändern.
dedup_text: {}

# Absender, aus denen `mail-jobsuche` Stellen liest. Ohne mindestens einen Eintrag
# beendet sich der Lauf mit einer Meldung (pipeline/mail_alerts.py).
mail_alerts:
  absender:
    - jobalerts-noreply@linkedin.com
    - jobs-noreply@linkedin.com
    - jobs-listings@linkedin.com
  max_age_tage: 2

# Titel, die trotz Treffer nie übernommen werden sollen (z. B. reine Vertriebsrollen).
ausschluss_titel: []

# Stellen, die älter sind, werden nicht mehr aufgenommen.
max_alter_tage: 30

# Nur nötig, wenn die Jobsuche über Apify laufen soll — Actors werden bewusst gepinnt,
# der Agent sucht sich nie selbst welche aus (Kostenbremse). Aufbau und Prüfbefehl:
# docs/INSTALLATION.md bzw. `python -m pipeline.apify_client schema <Portal>`.
# apify_actors: {}
"""


def sicherstellen(pfad: Path = SUCHPROFILE_PATH) -> bool:
    """Legt eine lauffähige Startfassung an, falls `config/suchprofile.yaml` fehlt.

    Phase 100: Die Datei ist per .gitignore ausgeschlossen und hatte keine Vorlage im Repo —
    nach einem frischen `git clone` fehlte sie also immer. Sie ist aber Startvoraussetzung, und
    zwar an zwei Stellen mit unfreundlichem Ausgang: `seed_aus_yaml()` (unten) las sie ohne
    Guard, wodurch schon `GET /api/einstellungen` mit einem 500er endete und die Einstellungen-
    Seite tot war; und `dedup_text.konfiguration()` beendet den Prozess mit `SystemExit`, womit
    KEIN Job in die Datenbank kam. Beides ohne Hinweis darauf, dass nur eine Datei fehlt.

    Deshalb hier eine Datei statt einzelner Fallbacks: die weiteren Leser
    (`apify_client`, `mail_alerts`, `schreibe_suchprofile`) finden danach
    ebenfalls eine gültige Datei vor, ohne dass ihre Fehlermeldungen aufgeweicht werden müssen.

    Der Kopf entsteht durch dieselbe Funktion wie bei jedem Speichern (`baue_managed`), enthält
    also garantiert die Struktur, die `/einstellungen` erwartet — inklusive MARKER, ohne den
    jeder spätere Save mit `RuntimeError` abbräche. Die Pläne bleiben absichtlich OHNE Titel:
    erfundene Zielrollen würden stillschweigend nach etwas suchen, das der Nutzer nie wollte.

    Rückgabe: True, wenn eine Datei angelegt wurde. Eine vorhandene Datei wird nie angefasst.
    """
    if pfad.exists():
        return False

    plaene = [
        {"plan": "A", "label": "Plan A", "aktiv": True, "prioritaet": 1,
         "titel": [], "senioritaet": [], "branche": []},
        {"plan": "B", "label": "Plan B", "aktiv": True, "prioritaet": 2,
         "titel": [], "senioritaet": [], "branche": []},
        {"plan": "C", "label": "Plan C", "aktiv": False, "prioritaet": 3,
         "titel": [], "senioritaet": [], "branche": []},
    ]
    suchbereich = {
        "remote": {"aktiv": True},
        "deutschlandweit": {"aktiv": True},
        "umkreis": {"aktiv": False, "stadt": "", "umkreis_km": 100},
    }
    managed = baue_managed(100, suchbereich, plaene, [dict(p) for p in PORTALE_DEFAULT])
    kopf = HEADER + yaml.safe_dump(managed, allow_unicode=True, sort_keys=False, width=1000)

    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(kopf + "\n" + MARKER + "\n" + _START_RUMPF, encoding="utf-8")
    return True


def regenerieren(einstellung) -> None:
    """Vom PATCH-Endpunkt aufgerufen: aktuelle `SuchEinstellung`-Row → YAML neu schreiben."""
    managed = baue_managed(
        einstellung.min_mitarbeiter,
        json.loads(einstellung.suchbereich_json),
        json.loads(einstellung.plaene_json),
        json.loads(einstellung.portale_json) if einstellung.portale_json else [],
    )
    schreibe_suchprofile(managed, SUCHPROFILE_PATH)
