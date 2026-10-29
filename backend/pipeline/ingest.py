#!/usr/bin/env python3
"""Deterministischer Ingest neuer Stellen in die zentrale DB.

Die intelligente Arbeit (Suchen, Extrahieren, Scoring nach Bewertungsraster) macht Claude
in-the-Loop; dieser Modul übernimmt den verlässlichen Teil: Deduplizieren gegen die DB,
Firmen/Kontakte anlegen, Stellen mit Status "Neu" schreiben und den Lauf protokollieren.

Vier-Augen-Gate (Phase 14): Jeder Record MUSS einen `verifikation`-Block tragen (vom Prüf-
Subagenten gesetzt), sonst wird er übersprungen (Zähler `unverifiziert`). Ausnahme nur für
Alt-Importe: CLI-Flag `--erlaube-unverifiziert` (normal NIE setzen).

P2-36 (11.09.2026): Eine neue Anzeige (anderer Link) zu einer Stelle, die bereits im Endstatus
liegt (Absage/Kein Match/Nicht verfügbar/Beirat abgelehnt/Keine Rückmeldung), wird nicht mehr
stumm verworfen, sondern als eigener Job mit Hinweis „NEUAUSSCHREIBUNG?“ angelegt — Dubletten
laufender Stellen (inkl. Geparkt) und reine Papierkorb-Treffer bleiben weiter gesperrt (s.
`_einordnen` unten und `tasks/spec_p2-36_neuausschreibung_dublette.md`).

CLI:
    cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.ingest <records.json> ["Portale"]

Record-Schema (ein Objekt je Stelle), Minimum = company + title:
    {
      "company": "...", "title": "...", "location": "...", "url": "...",
      "portal": "LinkedIn", "work_model": "Remote", "relocation_needed": "Nein",
      "tab": "Remote|Deutschlandweit|<Stadt> +<km>km", "plan_ab": "A|B",
      "seniority": "Director", "salary": "...", "published_date": "...",
      "situation": "SCALE-UP", "match_score": 4, "match_rationale": "... (mit Beleg)",
      "next_step": "...", "source_note": "...",
      "verifikation": {"status": "BESTÄTIGT|KORRIGIERT|QUELLE_VERTRAUT", "beleg": "...",
                       "geprueft_am": "ISO", "herkunft": "apify|mail-alert|nejo|arbeitsagentur"},  # herkunft nur bei QUELLE_VERTRAUT
      "contact": {"name": "...", "email": "...", "role": "Recruiter", "notes": "..."}
    }
"""
import datetime
import json
import sys
from collections import defaultdict

from sqlmodel import Session, select

from app.db import engine, flush_or_duplicate, init_db
from app.models import Company, Contact, Job, JobLog, Run
from app import normalize as N
from pipeline import dedup_text as D

# Phase 44: dieselbe Bedeutung wie main.py::TERMINAL_STATUSES (Absage/Kein Match/Nicht
# verfügbar/Beirat abgelehnt) — hier dupliziert statt importiert, weil main.py NICHT von
# ingest.py importiert werden darf (main.py importiert umgekehrt gar nichts aus pipeline.ingest;
# ein Import hier würde die Abhängigkeitsrichtung verdrehen). Ändert sich der Status-Katalog,
# beide Stellen prüfen.
# Phase 85: "Keine Rückmeldung" ergänzt (Ghosting-Endstatus).
_TERMINAL_STATUSES = {"Absage", "Kein Match", "Nicht verfügbar", "Beirat abgelehnt", "Keine Rückmeldung"}


def _stellen_schluessel(company, title) -> str:
    """Bereinigter Firma+Titel-Schlüssel (P2-36, §2.2 der Spec
    `tasks/spec_p2-36_neuausschreibung_dublette.md`; Firmenteil seit P2-39 zusätzlich bereinigt,
    s. u.) — wie `N.ct_key`, aber mit entferntem Gender-Zusatz im Titel UND bereinigtem
    Firmenteil (`N.firma_key` statt rohem Firmennamen). Fängt zwei Arten von Near-Dubletten ab,
    die die rohe `ct_key`-Prüfung verfehlt:
    - Gender-Zusatz im Titel (Echtfall: „Manager, Technical Service...“ vs. „Manager (m/f/d),
      Technical Service...“ — dieselbe Stelle, zwei Anzeigen).
    - Firmen-Schreibweise (P2-39, Echtfall: „Beispiel“ vs. „Beispiel GmbH“ — dieselbe Firma,
      zwei Firmen-Rows, die eine wurde nicht als Dublette der anderen erkannt).

    Nur für den Ingest-Abgleich hier genutzt, NICHT gespeichert — `N.ct_key` selbst bleibt roh
    (s. dessen Kommentar, Grund: `gmail_ingest._match_job`). Der Titelteil kommt seit P2-43 aus
    `N.rollen_schluessel` — dieselbe Definition nutzt die Mail-Zuordnung für Zwillinge."""
    return f"{N.firma_key(company)}|{N.rollen_schluessel(title)}"


def _einordnen(url, treffer):
    """Reine Entscheidungsfunktion (P2-36, §2.1 Schritt 3 + §2.7 der Spec) — KEIN DB-Zugriff.

    `treffer`: Liste der Job-Objekte, die der Aufrufer bereits über `dedup_key` ODER den
    bereinigten Firma+Titel-Schlüssel (`_stellen_schluessel`) gefunden und nach `id`
    dedupliziert hat. Der „URL schon bekannt“-Fall (§2.1 Schritt 1: irgendein Job, jeder Status,
    auch Papierkorb → Dublette) ist NICHT Teil dieser Funktion — den prüft der Aufrufer davor
    separat, unverändert gegenüber der bisherigen Logik.

    Rückgabe: ("neu", None) | ("dublette", None) | ("neuausschreibung", vorgaenger).

    Entscheidung des Nutzers (11.09.2026, Echtfall: eine im Endstatus aussortierte Stelle bekam
    eine neue Anzeige unter demselben Firma+Titel-Schlüssel): Diese darf nicht länger still
    verschluckt werden — die Stelle, auf die sich der Nutzer tatsächlich beworben hatte, wäre
    sonst nie angelegt worden. Eine laufende Stelle (inkl. „Geparkt“, das bewusst KEIN Endstatus
    ist) deckt die Anzeige dagegen bereits ab; reine Papierkorb-Treffer bleiben Sperre wie bisher."""
    if not treffer:
        return "neu", None
    if not url:
        # Gleiche vs. neue Anzeige ist ohne Link nicht unterscheidbar -> konservativ wie bisher.
        return "dublette", None
    laufend = [j for j in treffer if not j.deleted_at and j.status not in _TERMINAL_STATUSES]
    if laufend:
        return "dublette", None
    endstatus_treffer = [j for j in treffer if not j.deleted_at and j.status in _TERMINAL_STATUSES]
    if endstatus_treffer:
        vorgaenger = max(endstatus_treffer, key=lambda j: j.id)
        return "neuausschreibung", vorgaenger
    # Nur Papierkorb-Treffer -> Sperre bleibt wie bisher.
    return "dublette", None


# Zeichen, die nach dem Kürzen nicht am Titelende hängen bleiben sollen (P2-42).
_HAENGENDE_ZEICHEN = " &+–—-,;:/("


def _titel_kurz(titel, max_len: int = 40) -> str:
    """Titel für die Hinweis-Anhänge `NEUAUSSCHREIBUNG?` und `DUBLETTE?` kürzen (P2-42).

    Geschnitten wird an der letzten Wortgrenze bis `max_len` Zeichen; hängende Verbinder
    (`&`, `–`, `,` …) fallen weg, danach folgt `…`. Bis P2-42 wurde hart nach 40 Zeichen
    geschnitten — Echtfall (17.09.2026): ein Titel wurde exakt bei einem hängenden „&“
    abgeschnitten (z. B. „… Sales & “). Ohne Leerzeichen im Kopf bleibt es beim harten Schnitt,
    ebenfalls mit `…`.

    Zwei Ersetzungen schützen die Parser: ein `|` würde den Anhang-Trenner der verify_note-
    Konvention (` | `) verwirren und wird zu `/`; ein U+201C im Titel beendete den Titel für
    `ui.tsx::parseNeuausschreibung` zu früh und wird zu U+201D."""
    t = " ".join(str(titel or "").split()).replace("|", "/").replace("\u201c", "\u201d")
    if len(t) <= max_len:
        return t
    kopf = t[:max_len + 1]                   # +1: ein Wort, das genau bei max_len endet, bleibt
    grenze = kopf.rfind(" ")
    kurz = kopf[:grenze] if grenze > 0 else t[:max_len]
    return (kurz.rstrip(_HAENGENDE_ZEICHEN) or t[:max_len]) + "…"


def _neuausschreibung_hinweis(vorgaenger) -> str:
    """Hinweistext für §2.3 der Spec — OHNE führendes ' | ' (Aufrufer hängt das je nach
    Kontext selbst an `verify_note` bzw. nutzt den Text direkt für den JobLog-Eintrag, analog
    zum Phase-44-`dublette_hinweis`-Muster weiter unten). Deutsche Anführungszeichen „ (U+201E)
    / “ (U+201C) — NIE ein ASCII '\"' (Lesson P2-15). Titel über `_titel_kurz()` an der
    Wortgrenze gekürzt (P2-42)."""
    titel_kurz = _titel_kurz(vorgaenger.title)
    gefunden = vorgaenger.found_date or "unbekannt"
    return (f"NEUAUSSCHREIBUNG? Job {vorgaenger.id} „{titel_kurz}“ — "
            f"{vorgaenger.status}, zuerst gefunden {gefunden}")


def _get_or_create_company(session, cache, name, **fields):
    key = (name or "").strip().lower()
    if not key:
        return None
    if key in cache:
        comp = cache[key]
        for k, v in fields.items():
            if v and not getattr(comp, k, None):
                setattr(comp, k, v)
        return comp
    # P2-3 (Phase 67F): case-insensitiver Abgleich (Muster main.py::create_job) — der UNIQUE-
    # Index auf company(LOWER(TRIM(name))) ist ebenfalls case-insensitiv; ein case-sensitiver
    # Vorab-Check hier hätte eine bestehende, nur anders geschriebene Firma verfehlt und wäre
    # geradewegs in den Index gelaufen.
    comp = next((c for c in session.exec(select(Company)).all() if c.name.strip().lower() == key), None)
    if not comp:
        # P2-39 (12.09.2026, Echtfall: gleiche Firma unter zwei Schreibweisen mit Rechtsform-
        # zusatz): der exakte Namensvergleich verfehlt eine bestehende Firma mit anderer
        # Schreibweise (Rechtsform-/Regionszusatz). Über den bereinigten Firmen-Schlüssel
        # nachschlagen — GENAU EIN Treffer wird übernommen (der Job behält seinen eigenen
        # `company_name` aus der Anzeige, nur die
        # Zuordnung zur Firmen-Row ändert sich). Finden sich MEHRERE bestehende Firmen mit
        # demselben bereinigten Schlüssel, wird KEINE gewählt (kein Raten — Muster
        # `_MEHRDEUTIG` in `gmail_ingest._match_job`); dann läuft es weiter wie bisher (unten:
        # exakter Treffer bereits gescheitert, also neue Firma anlegen).
        ziel_schluessel = N.firma_key(name)
        firma_treffer = [c for c in session.exec(select(Company)).all()
                        if N.firma_key(c.name) == ziel_schluessel]
        if len(firma_treffer) == 1:
            comp = firma_treffer[0]
    if not comp:
        neu = Company(name=name, **{k: v for k, v in fields.items() if v})
        # `session.add(neu)` bewusst ERST im Callback (nicht davor!) — begin_nested() autoflusht
        # beim Eintritt bereits anhängige Änderungen; wäre `neu` schon vorher pending, würde
        # genau DIESER Auto-Flush eine Kollision auslösen, AUSSERHALB der Savepoint-Absicherung
        # (s. Docstring von flush_or_duplicate).
        if flush_or_duplicate(session, lambda: session.add(neu)):
            comp = neu
        else:
            # Echte Race (zwei fast gleichzeitige Schreiber legen dieselbe Firma an) — die jetzt
            # existierende Zeile nachschlagen statt mit einem 500er zu crashen.
            comp = next((c for c in session.exec(select(Company)).all() if c.name.strip().lower() == key), None)
    cache[key] = comp
    return comp


_VERIF_STATUS = {"BESTÄTIGT", "KORRIGIERT", "QUELLE_VERTRAUT"}


def _valid_verifikation(rec):
    """Gibt den gültigen verifikation-Block zurück, sonst None (Vier-Augen-Gate, Phase 14).

    Ein Treffer darf nur in die DB, wenn der Prüf-Agent ihn belegt hat:
      BESTÄTIGT / KORRIGIERT = Anzeige live gesehen bzw. kanonische URL ersetzt.
      QUELLE_VERTRAUT        = nicht live prüfbar (403/Login-Wall), NUR mit authentischer
                               Herkunft (apify|mail-alert|nejo|arbeitsagentur) — sonst
                               potenziell halluziniert.
    """
    v = rec.get("verifikation")
    if not isinstance(v, dict):
        return None
    if v.get("status") not in _VERIF_STATUS:
        return None
    if not str(v.get("beleg") or "").strip():
        return None
    if v.get("status") == "QUELLE_VERTRAUT" and v.get("herkunft") not in ("apify", "mail-alert", "nejo", "arbeitsagentur"):
        return None
    return v


def ingest_records(records, run_type="jobsearch", portals=None, erlaube_unverifiziert=False,
                   texte=None):
    """Insert new jobs, skipping duplicates. Returns a summary dict.

    Vier-Augen-Gate: Records ohne gültigen `verifikation`-Block werden übersprungen
    (Zähler `unverifiziert`). `erlaube_unverifiziert=True` umgeht das Gate NUR für Alt-Importe.

    `texte` (Phase 38, optional): {url: anzeigentext} aus `verify_jobs.check()`
    (`<records>_texte.json`) — je neu angelegtem Job wird sofort ein deterministischer
    Basis-Snapshot erzeugt (`posting_snapshot.render_basis`). Fehlt der Text zu einer URL,
    entsteht trotzdem ein Snapshot (nur Metadaten, Badge amber) — nie raten, nie verwerfen.
    Snapshot-Fehler brechen den Ingest NIE ab (Design-Entscheidung 6 der Spec)."""
    from pipeline.posting_snapshot import render_basis
    from pipeline import suchprofil
    texte = texte or {}
    init_db()
    today = datetime.date.today().isoformat()
    with Session(engine) as s:
        run = Run(run_type=run_type, portals=portals or "", jobs_found=len(records))
        s.add(run)
        s.flush()

        # P2-51 (V7): EINMAL je Lauf gelesen, nicht je Record — der Umkreis-Bezeichnungswechsel
        # kann sich während eines laufenden Ingests nicht ändern (kein anderer Prozess schreibt
        # parallel in dieselbe SuchEinstellung-Zeile).
        umkreis_label_aktuell = suchprofil.aktuelles_umkreis_label(s)

        # Bestehende Schlüssel einmal laden (Dedup nach URL, dedup_key und bereinigtem
        # Firma+Titel-Schlüssel). P2-36: seen_dk/seen_ct (reine Sets) durch Verzeichnisse
        # Schlüssel -> [Job, ...] ersetzt — die Neuausschreibungs-Entscheidung (`_einordnen`)
        # muss wissen, AN WELCHE Jobs (Status/Papierkorb) ein Schlüssel vergeben ist, nicht nur
        # OB. seen_url bleibt ein Set wie bisher (§2.1 Schritt 1 ist unverändert).
        all_jobs = s.exec(select(Job)).all()
        seen_url = {j.url for j in all_jobs if j.url}
        jobs_by_dk = defaultdict(list)
        jobs_by_stellenschluessel = defaultdict(list)
        for j in all_jobs:
            jobs_by_dk[j.dedup_key].append(j)
            jobs_by_stellenschluessel[_stellen_schluessel(j.company_name, j.title)].append(j)

        # Phase 44 Stufe B: Vergleichspool für die Repost-Erkennung — EINMAL aus den schon
        # geladenen all_jobs aufgebaut (kein Extra-Query je Record). Nur Jobs mit Snapshot,
        # nicht-terminalem Status, nicht soft-gelöscht — "Geparkt" zählt bewusst NICHT als
        # terminal (ein Echtfall landete genau dort).
        # P2-39 (12.09.2026): Schlüssel auf N.firma_key umgestellt (statt N.slug_parts) — sonst
        # vergleicht der Textvergleich weiterhin nur innerhalb EINER Firmen-Schreibweise
        # (Echtfall: gleiche Firma, unterschiedliche Schreibweise, s.
        # tasks/spec_p2-39_firmen_schluessel.md).
        dedup_cfg = D.konfiguration()
        jobs_je_firma = defaultdict(list)
        for j in all_jobs:
            if j.posting_snapshot_path and not j.deleted_at and j.status not in _TERMINAL_STATUSES:
                jobs_je_firma[N.firma_key(j.company_name)].append(j)

        cache = {}
        new_ids, dup, skipped, unverifiziert = [], 0, 0, 0
        snapshots = snapshot_fehler = 0
        dubletten_verdacht = 0
        neuausschreibungen = 0
        for rec in records:
            company = (rec.get("company") or "").strip()
            title = (rec.get("title") or "").strip()
            if not company or not title:
                skipped += 1
                continue
            loc = rec.get("location")
            url = rec.get("url")
            dk = N.dedup_key(company, title, loc)
            stellen_schluessel = _stellen_schluessel(company, title)

            # P2-36 (Echtfall 11.09.2026): Stufe 3 (roher ct_key) griff bisher nicht, wenn zwei
            # Anzeigen derselben Stelle sich nur im Gender-Zusatz des Titels unterschieden
            # ("Manager, ..." vs. "Manager (m/f/d), ..."). Der
            # bereinigte Firma+Titel-Schlüssel (_stellen_schluessel) fängt das jetzt zusätzlich
            # ab — ABER eine im Endstatus aussortierte Stelle darf eine NEUE Anzeige (neuer Link)
            # nicht länger stumm verschlucken (Entscheidung des Nutzers, 11.09.2026: die Stelle,
            # auf die er sich tatsächlich beworben hatte, wäre sonst nie angelegt worden). Schritt
            # 1 (URL schon bekannt) bleibt unverändert eine Dublette; die eigentliche Einordnung
            # übernimmt die reine Funktion `_einordnen()` (s. o., Tabelle in der Spec §2.1).
            if url and url in seen_url:
                dup += 1
                continue

            treffer_map = {}
            for j in jobs_by_dk.get(dk, ()):
                treffer_map[j.id] = j
            for j in jobs_by_stellenschluessel.get(stellen_schluessel, ()):
                treffer_map[j.id] = j
            lage, vorgaenger = _einordnen(url, list(treffer_map.values()))
            if lage == "dublette":
                dup += 1
                continue

            # Vier-Augen-Gate (Phase 14): kein Insert ohne belegten verifikation-Block.
            # VOR der Registrierung von seen_url/den Trefferverzeichnissen prüfen, damit ein
            # späterer, verifizierter Zwilling im selben Batch nicht fälschlich als Dublette
            # wegfällt.
            verif = _valid_verifikation(rec)
            if verif is None and not erlaube_unverifiziert:
                unverifiziert += 1
                continue

            if url:
                seen_url.add(url)

            # P2-36 §2.4: dedup_key trägt den UNIQUE-Index ux_job_dedup_key — hat die
            # Neuausschreibung exakt Titel UND Ort des Vorgängers, wäre der berechnete Schlüssel
            # schon vergeben (der Vorgänger selbst steckt dann in jobs_by_dk[dk]) und der Insert
            # schiene still als Dublette. Nur in diesem Fall den URL-Rest anhängen; sonst der
            # normale Schlüssel. Kollidiert selbst das noch (praktisch ausgeschlossen), greift
            # der bestehende flush_or_duplicate-Zweig unten (Zähler dup, kein Absturz).
            if jobs_by_dk.get(dk):
                dk_effektiv = f"{dk}|{N.slug_parts(url)[-40:]}"
            else:
                dk_effektiv = dk

            verified_at = verify_note = None
            dublette_ziel = None      # Phase 44: für den JobLog-Eintrag nach dem Flush (braucht job.id)
            if verif:
                verified_at = verif.get("geprueft_am") or datetime.datetime.utcnow().isoformat()
                verify_note = f"{verif.get('status')}: {verif.get('beleg')}"
                # Phase 21: Quellen-Konflikte des Records ans verify_note anhängen — NACH dem
                # Badge-Präfix (das Frontend liest das Präfix vorne), jeder Eintrag im Format
                # "KONFLIKT <Feld>: …". Der Vier-Augen-Prüf-Subagent liefert sie in rec["konflikte"].
                for kf in (rec.get("konflikte") or []):
                    kf = str(kf).strip()
                    if kf and kf not in verify_note:          # defensiv gegen Doppel-Anhang
                        verify_note += f" | {kf}"

                # Phase 44 Stufe B: Repost-Text-Vergleich — NACH dem Vier-Augen-Gate, VOR dem
                # Insert. Nur Records mit Anzeigentext (kein --texte/Snapshot nur Metadaten/
                # zu kurz → D.pruefen() liefert None, still übersprungen, nie geraten).
                kandidat = D.kandidat_text(texte.get(url)) if url and texte.get(url) else ""
                if kandidat:
                    bester_job, bester_score = None, 0.0
                    for besteh in jobs_je_firma.get(N.firma_key(company), []):
                        besteh_text = D.rollen_relevanter_text(besteh.posting_snapshot_path)
                        score = D.pruefen(title, kandidat, besteh.title, besteh_text, dedup_cfg)
                        if score is not None and score >= dedup_cfg["schwelle"] and score > bester_score:
                            bester_job, bester_score = besteh, score
                    if bester_job:
                        dubletten_verdacht += 1
                        geprueft = datetime.date.today().isoformat()
                        titel_kurz = _titel_kurz(bester_job.title)   # P2-42: Wortgrenze + „…“
                        dublette_hinweis = (f' | DUBLETTE? Job {bester_job.id} „{titel_kurz}“ — '
                                            f'Text-Ähnlichkeit {round(bester_score * 100)} % '
                                            f'(geprüft {geprueft})')
                        verify_note += dublette_hinweis
                        dublette_ziel = (bester_job.id, dublette_hinweis.strip(" |"))

            # P2-36 §2.3: Neuausschreibungs-Hinweis — NACH den KONFLIKT-Anhängen, unabhängig vom
            # Phase-44-DUBLETTE?-Hinweis (beide dürfen gemeinsam auftreten). Wirkt auch im
            # --erlaube-unverifiziert-Altimport-Pfad, in dem verify_note bis hier None ist.
            neuausschreibung_hinweis = None
            if lage == "neuausschreibung":
                neuausschreibung_hinweis = _neuausschreibung_hinweis(vorgaenger)
                if verify_note is None:
                    verify_note = neuausschreibung_hinweis
                else:
                    verify_note += f" | {neuausschreibung_hinweis}"

            situ_norm, situ_raw = N.norm_situation(rec.get("situation"))
            comp = _get_or_create_company(
                s, cache, company,
                situation=situ_norm, situation_raw=situ_raw, region=rec.get("region"),
            )
            senior_norm, senior_raw = N.norm_seniority(rec.get("seniority"))
            job = Job(
                company_id=comp.id if comp else None,
                company_name=company,
                title=title,
                seniority=senior_norm or rec.get("seniority"),
                seniority_raw=senior_raw or rec.get("seniority"),
                location=loc,
                work_model=N.norm_work_model(rec.get("work_model")) or rec.get("work_model"),
                relocation_needed=rec.get("relocation_needed"),
                # P2-51 (V7): eine mitgeschickte, aber inzwischen umbenannte Umkreis-Bezeichnung
                # landet auf der aktuellen statt einer zweiten, veralteten Kennung.
                tab=suchprofil.tab_normalisieren(rec.get("tab"), umkreis_label_aktuell),
                plan_ab=rec.get("plan_ab"),
                portal=rec.get("portal") or N.norm_portal(url),
                url=url,
                salary=rec.get("salary"),
                published_date=rec.get("published_date"),
                found_date=today,
                match_score=rec.get("match_score"),
                match_rationale=rec.get("match_rationale"),
                status="Neu",
                next_step=rec.get("next_step"),
                source_note=rec.get("source_note"),
                verified_at=verified_at,
                verify_note=verify_note,
                dedup_key=dk_effektiv,
                raw_json=json.dumps(rec, ensure_ascii=False),
            )
            if not flush_or_duplicate(s, lambda: s.add(job)):
                # P2-3 (Phase 67F): dedup_key ist jetzt UNIQUE indiziert. Die in-memory seen_*-
                # Sets oben fangen Dubletten INNERHALB dieses Batches bereits ab — dieser Zweig
                # greift nur bei einer echten Race (ein zweiter, fast gleichzeitig laufender
                # Ingest/Prozess hat denselben dedup_key gerade eben committet). Wie ein normaler
                # Dubletten-Treffer zählen, NICHT mit 500 abbrechen — der Rest des Batches muss
                # weiterlaufen (s. tests/test_unique_constraints.py).
                dup += 1
                continue
            new_ids.append(job.id)
            # Erst NACH dem erfolgreichen Insert zählen — scheitert er im Race-Zweig oben, zählt
            # der Record nur als Dublette, nicht zusätzlich als Neuausschreibung.
            if lage == "neuausschreibung":
                neuausschreibungen += 1

            if dublette_ziel:
                _, hinweis_text = dublette_ziel
                s.add(JobLog(job_id=job.id, art="auto", eintrag=hinweis_text))

            if neuausschreibung_hinweis:
                s.add(JobLog(job_id=job.id, art="auto", eintrag=neuausschreibung_hinweis))

            if url:
                if render_basis(job, texte.get(url)):
                    snapshots += 1
                else:
                    snapshot_fehler += 1
                s.add(job)

            # P2-8 (Phase 67D): den gerade angelegten Job in denselben Vergleichspool aufnehmen,
            # den die Schleife oben aus dem DB-Bestand gebaut hat — sonst wird ein zweiter Repost
            # IM SELBEN LAUF nie gegen den ersten geprüft (Reihenfolge/dedup_cfg/Titel-Vorfilter
            # bleiben identisch, s. Docstring oben). Gleicher Schlüssel wie beim Poolaufbau
            # (`N.firma_key(j.company_name)`, P2-39) und dieselbe Bedingung (Snapshot vorhanden,
            # nicht gelöscht, nicht terminal) — für einen frischen "Neu"-Job ist Bedingung 2+3
            # immer erfüllt, Bedingung 1 (posting_snapshot_path) erst NACH dem
            # render_basis()-Aufruf oben, deshalb hier und nicht direkt nach dem s.flush().
            if job.posting_snapshot_path and not job.deleted_at and job.status not in _TERMINAL_STATUSES:
                jobs_je_firma[N.firma_key(job.company_name)].append(job)

            # P2-36 §2.6: den erfolgreich angelegten Job SOFORT in beide Trefferverzeichnisse
            # aufnehmen — mit dem TATSÄCHLICH gespeicherten dedup_key (ggf. dem Kollisions-
            # Schlüssel aus §2.4), nicht dem ursprünglich berechneten `dk`. Sonst würde eine
            # zweite neue Anzeige derselben aussortierten Stelle IM SELBEN LAUF nie gegen den
            # gerade erst angelegten, jetzt laufenden Job geprüft und liefe fälschlich noch
            # einmal als Neuausschreibung statt als Dublette durch (analog zum P2-8-Fix oben für
            # jobs_je_firma).
            jobs_by_dk[job.dedup_key].append(job)
            jobs_by_stellenschluessel[stellen_schluessel].append(job)

            c = rec.get("contact")
            if c and comp:
                s.add(Contact(company_id=comp.id, job_id=job.id, name=c.get("name"),
                              email=c.get("email"), role=c.get("role"), notes=c.get("notes")))

        run.jobs_new = len(new_ids)
        run.finished_at = datetime.datetime.utcnow()
        run.summary = (f"{len(new_ids)} neu · {dup} Dubletten · {skipped} unvollständig · "
                       f"{unverifiziert} unverifiziert (von {len(records)}) · "
                       f"{snapshots} Anzeigen-Snapshots ({snapshot_fehler} Fehler) · "
                       f"{dubletten_verdacht} Dubletten-Verdacht (Text-Ähnlichkeit) · "
                       f"{neuausschreibungen} Neuausschreibungen (früher aussortiert)")
        s.add(run)
        s.commit()
        return {"new": len(new_ids), "dup": dup, "skipped": skipped,
                "unverifiziert": unverifiziert, "snapshots": snapshots,
                "snapshot_fehler": snapshot_fehler, "dubletten_verdacht": dubletten_verdacht,
                "neuausschreibungen": neuausschreibungen,
                "total": len(records), "new_ids": new_ids, "run_id": run.id}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(prog="pipeline.ingest", description=__doc__.split("\n")[0])
    ap.add_argument("records_json")
    ap.add_argument("portals", nargs="?", default=None, help='z. B. "LinkedIn,Indeed,StepStone"')
    ap.add_argument("--erlaube-unverifiziert", action="store_true",
                    help="AUSNAHME (Alt-Importe): Vier-Augen-Gate umgehen — normal NIE setzen.")
    ap.add_argument("--texte", default=None,
                    help="Phase 38: <records>_texte.json aus verify_jobs check ({url: Anzeigentext}) "
                         "— erzeugt sofort einen Basis-Snapshot je neuem Job mit URL.")
    a = ap.parse_args()
    with open(a.records_json, encoding="utf-8") as fh:
        recs = json.load(fh)
    texte = None
    if a.texte:
        try:
            with open(a.texte, encoding="utf-8") as fh:
                texte = json.load(fh)
        except OSError as e:
            print(f"[ingest] --texte {a.texte} nicht lesbar ({e}) — Ingest läuft ohne Snapshot-Texte weiter.",
                  file=sys.stderr)
    result = ingest_records(recs, portals=a.portals, erlaube_unverifiziert=a.erlaube_unverifiziert,
                            texte=texte)
    print(json.dumps(result, ensure_ascii=False))
