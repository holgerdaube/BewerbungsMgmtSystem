---
name: job-deepdive
description: Erzeugt für EINE passende Stelle aus dem Bewerbungs-Management-System des Nutzers den Deep-Dive — Company-Fit-Dashboard + angepasster CV (DE/EN) + ATS-Score — und verlinkt die Artefakte am Job-Detail. Nutze diesen Skill bei "Deep-Dive für Job <id>", "mach den Deep-Dive für <Firma>", "angepassten CV für diese Stelle", "Company-Fit für <Firma>", "bereite die Bewerbung für <Stelle> vor".
---

# Job Deep-Dive (Claude-in-the-Loop)

Bündelt die bestehenden Skills des Nutzers zu einem Bewerbungs-Paket für eine konkrete Stelle und
registriert die Ergebnisse in der zentralen DB, sodass die Web-App sie am Job-Detail zeigt.

## Ablauf

### 1. Stelle laden
Job-ID vom Nutzer (oder aus dem Kontext). Daten holen:
```sh
curl -s http://localhost:8000/api/jobs/<id>
```
Liefert Titel, Firma, URL, Situation, Sprache-Hinweise. Stellensprache bestimmen
(deutscher Fließtext → DE-CV, englischer → EN-CV; siehe cv-job-match Schritt 0).

### 2. Stellenbeschreibung besorgen
JD über `job.url` per WebFetch holen. Bei Login-Wall/Blockade: Firmen-Karriereseite suchen
oder die im Job gespeicherte Rollen-Zusammenfassung (`match_rationale`, `raw_json`) als Basis
nehmen und das im Bericht transparent machen.

**Portal geschlossen?** Marker wie „No longer accepting applications"/„position has been filled"/
Redirect auf die Portal-Übersicht → `PATCH /api/jobs/<id>` `{"portal_closed": 1}` → Karriereseite
ermitteln (`career_url` → Zielfirmen-Cache `GET /api/target-companies` → WebSearch) und Stelle dort
suchen → Fund: `career_url` PATCHen + JobLog; kein Fund: Übersichtsseite als `career_url` + JobLog +
Empfehlung „Nicht verfügbar" statt Status-Automatik (Details/Badge: `firma-pruefen` Schritt 3b).

### 3. Company-Fit (Skill `company-fit-analysis`)
Für die Firma das Firmen-Dashboard erzeugen — Ablauf exakt wie in `firma-pruefen` Schritt 3: Die
Datei entsteht über `pipeline.company_fit.render_full()` (kein Markup von Hand; Aufbau, Stil,
Dateiname `JJJJMMTT_CompanyFit_<Firma>` und Ablage unter `data/company_fit/` macht der Renderer,
IMMER mit Datum, NIE mit Rolle). Der `company_fit_path` aus der Rückgabe ist der Wert für
Schritt 5. Jede Neu-Prüfung erzeugt bewusst eine neue Datei, `fit_analysis_path` zeigt auf die
aktuellste.
Zusätzlich die **Stellenausschreibung als Snapshot** sichern — Ablauf und Regeln exakt wie in
`firma-pruefen` Schritt 3b (Quellen-Kaskade URL→raw_json→WebSearch, Inhalte WÖRTLICH,
Quellen-Badge grün/amber/rot). Die Datei entsteht über `pipeline.posting_snapshot.render_full()`
(kein Markup von Hand, Dateiname und Ablage macht der Renderer); der `posting_snapshot_path`
aus der Rückgabe ist der `posting_path` für Schritt 5. Die JD ist in Schritt 2 ohnehin geladen.
Und wie in `firma-pruefen` Schritt 3c: nennt die Anzeige ein **Gehalt** und ist `job.salary` LEER, per
`PATCH /api/jobs/<id> {"salary": "<wörtlich>"}` nachtragen (nie überschreiben, keine Schätzung).

### 4. Angepasster CV (Skill `cv-job-match`)
Mit der zur Stellensprache passenden Basis-CV-Datei (`data/cv_basis/base_de.docx` bzw. `data/cv_basis/base_en.docx` —
beides `_ATS`-Varianten, also nur Text-Einbau, keine Strukturänderung; seit Phase 76 „v9 ATS":
Titel VOR der „Firma\tZeitraum"-Zeile, Workday-Fix — Reihenfolge nie zurückdrehen). Ergebnis:
- angepasste `.docx` → `outputs/cv/` — **Arbeitsname egal**; die Registrierung benennt sie automatisch
  nach `CV_<Name>_<Firma>_<Position>[_<Sprache>]` um und erzeugt daneben das **PDF** (kein Namensbau nötig).
- Match-Dashboard und ATS-Scan nach dem Muster von `assets/report_theme_bms.html` (lesen, Aufbau und
  Klassen übernehmen; kein CSS und keine Farbwerte abschreiben, die Berichte entstehen ohne eigenen
  Style-Block), Dateinamen über `naming.report_filename('Match', firma, position)` bzw.
  `naming.report_filename('ATSscan', firma, position)` → `data/company_fit/JJJJMMTT_Match_<Firma>_<Position>.html`
  bzw. `…_ATSscan_….html` (löst den bisherigen freien `<slug>_match/_ats.html` ab, s. `cv-match`).
- **Pflichtschritt nach dem Schreiben beider Berichte** — erst den Stil einsetzen, dann prüfen:
  ```sh
  cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.bericht_stil einsetzen "../data/company_fit/<Match-Name>.html" "../data/company_fit/<ATSscan-Name>.html" && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.report_check "../data/company_fit/<Match-Name>.html" "../data/company_fit/<ATSscan-Name>.html"
  ```
  Meldet einer der beiden Befehle eine Klasse ohne Regel: die Klasse durch eine aus der Vorlage
  ersetzen (kein eigenes CSS) und beide Befehle wiederholen.
- **Vorher/Nachher-Gegenüberstellung ist Pflichtteil des Match-Dashboards** (Phase 34, gespiegelt
  aus `cv-match` Schritt 1c — dort steht das fertige HTML-Muster + die Wahrheits-Regeln,
  hier gilt dasselbe wörtlich: je geändertem Bullet Original-Zitat/neues Zitat/eingebaute Keywords
  beim Anpassen mitprotokollieren, nicht rekonstruieren; nur tatsächlich geänderte Bullets zeigen;
  `<mark>` nur für echte, aus der Anzeige eingebaute Keywords, nie in der `.docx`).
Wahrheitstreue strikt beachten (keine erfundenen Skills/Zahlen; Keywords im Original-Wortlaut).

### 5. Registrieren
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.deepdive <deepdive.json>
```
`deepdive.json` (Schema siehe Kopf von `backend/pipeline/deepdive.py`) mit `job_id`,
`company_fit_path`, `posting_path` (Snapshot aus Schritt 3, `data/job_postings/<name>.html`),
`fit_ampel` (Phase 24 F, optional, `gruen|gelb|rot` — deine Bewertung aus Schritt 3 strukturiert
mitgeben, nur zusammen mit `company_fit_path` sinnvoll), `cv` (language, file_path, ats_score,
match_score100, match_dashboard_path, ats_scan_path) und optional `next_step`. `register()` benennt
die `.docx` um und erzeugt das PDF (LibreOffice headless); die finalen Namen stehen im Rückgabe-JSON
unter `export` (`docx`, `pdf`, ggf. `pdf_fehler`).

### 6. Bericht (Kompakt-Format — landet 1:1 in einer schmalen UI-Karte)
**Grundregel:** Ausführliches gehört in die Artefakte, nicht in die Meldung. KEINE Markdown-
Überschriften, keine Beleg-/Aufräum-Prosa. Gesamt **≤150 Wörter**:
- **Zeile 1 = das ALLERERSTE Zeichen der Meldung, KEINE Vorrede davor** (kein „Registrierung erfolgreich"/
  „Fertig" o. Ä.): `Ampel-Fit: 🟢|🟡|🔴 — <Halbsatz>`
- **Zeile 2:** `CV angepasst — Match <n>/100 · ATS <n> % · <Sprache>`
- optional 1 Satz wichtigster Vorbehalt; **Schlusszeile** mit den finalen CV-Dateinamen (docx + pdf aus
  `export`; bei `pdf_fehler` den Text weitergeben) + Verweis „Details an der Stelle verlinkt".

## Grenzen
- Ein Job pro Lauf. Wahrheitstreue vor Score (cv-job-match Grundprinzipien gelten).
- Nur für Stellen, die der Nutzer vorher angenommen/als passend markiert hat.
- Macht Firma-Check **und** CV in einem Rutsch. **Standard ist die getrennte Reihenfolge:**
  erst `firma-pruefen` (Schritt 1), und nur wenn der Fit klar ist, `cv-match` (Schritt 2a) +
  `cv-erstellen` (Schritt 2b).
