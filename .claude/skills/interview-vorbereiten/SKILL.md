---
name: interview-vorbereiten
description: Erstellt für eine Stelle aus dem Bewerbungs-Management-System ein Call-Briefing für das nächste Gespräch — erwartbare Fragen mit STAR-Antwortskizzen aus dem echten CV des Nutzers, priorisierte offene Fragen AN die Firma, Einwand-Handling und Spickzettel. Zieht Company-Fit, CV, Profil, bisherige Transkripte und aktuelle News heran, erzeugt ein self-contained HTML-Briefing und verlinkt es am Interview im Job-Detail. Nutze diesen Skill bei "Interview vorbereiten für Job <id>", "bereite mich auf das Gespräch vor", "Briefing für Job <id>", "Call-Vorbereitung", "auf das Interview vorbereiten".
---

# Interview vorbereiten (Call-Briefing)

Beantwortet für ein konkretes Gespräch: **Womit gehe ich rein?** — erwartbare Fragen mit belegten
Antworten, kluge Rückfragen an die Firma, Einwand-Handling, Kernbotschaften. Erzeugt ein self-contained
HTML-Briefing und hängt es an das Interview im Cockpit. Claude-in-the-Loop: der Skill recherchiert und
schreibt die Datei, `pipeline/interview.py` registriert sie deterministisch.

## Ablauf

### 1. Stelle + Gespräch laden
Job-ID aus dem Auslöser (z. B. „Interview vorbereiten für Job <id>"). Daten holen:
```sh
curl -s http://localhost:8000/api/jobs/<id>
```
Liefert `job`, `company` (inkl. `fit_analysis_path`), `contacts`, `cv_versions`, `interviews`, `transcripts`.

**Zielrunde bestimmen:** das Interview mit Status „Geplant" mit der höchsten `runde`. Existiert keins,
lege eins an und weise den Nutzer im Bericht darauf hin:
```sh
curl -s -X POST http://localhost:8000/api/jobs/<id>/interviews -H 'Content-Type: application/json' \
  -d '{"art":"HR-Screen","runde":1,"status":"Geplant"}'
```
Die `id` dieses Interviews ist die **Zielrunde** — sie wird in Schritt 5 registriert.

### 2. Quellen lesen (Pflichtinput)
- **(a) Company-Fit:** die HTML unter `company.fit_analysis_path` (falls vorhanden) — Chancen, Risiken und
  Klärungsfragen herausziehen (`/api/artifact?path=<fit_analysis_path>` oder Datei direkt lesen).
- **(b) CV:** den aktuellsten angepassten CV lesen (`cv_versions[].file_path`, .docx) — sonst `data/cv_basis/base_<sprache>.docx`
  in der Sprache der Anzeige bzw. des Gesprächs (`de`, `en`, `fr`, `it`, `es`, `pt`; läuft das Gespräch auf Englisch,
  `base_en.docx`). Fehlt bei einer französischen, italienischen, spanischen oder portugiesischen Anzeige die Fassung
  dieser Sprache: nichts übersetzen, zuerst `base_en.docx` nehmen, falls vorhanden, sonst `base_de.docx`, und den
  Sprachbruch im Bericht nennen. Liefert die echten Belege für die Antwortskizzen.
- **(c) Profil:** `config/profil.md` — Kurzprofil, Kernbotschaften und **harte Grenzen** (rote Linien).
- **(d) Bisherige Transkripte:** ALLE `transcripts[].file_path` dieses Jobs lesen. **Bei Runde ≥ 2 sind die
  unbeantworteten Punkte / offenen To-dos aus der/den Vorrunde(n) Pflichtinput** — sie gehören in einen
  eigenen Abschnitt „Aus Runde n-1 offen".
- **(e) Fragenbank:** `data/interview_prep/fragenbank.md`, falls vorhanden (wird von `gespraech-debrief`,
  Stufe C, gepflegt) — tatsächlich gestellte Fragen ähnlicher Gespräche.

### 3. Zusätzlich recherchieren (WebSearch/WebFetch)
Aktuelle Firmen-News der letzten ~8 Wochen (Funding, M&A, Produkt, Führungswechsel, Presse) + typische
Interviewfragen für Rolle/Branche/Seniorität. Wenn Interviewer-Namen bekannt sind (aus `interviewer` oder
`contacts`): kurz per LinkedIn/Web recherchieren (Rolle, Hintergrund, mögliche Perspektive). Kein Muss bei
akutem Zeitdruck, aber Standard.

### 3b. Konflikt-Scan (PFLICHT — vor dem Briefing)
Quellen-Widersprüche dürfen im Gespräch nicht untergehen (Anlassfall: Anzeigentext
„Remote-first across Europe" vs. LinkedIn-Chip „On-site München"). Ablauf:
1. **`job.verify_note` + `source_note`** auf das feste Schlüsselwort **`KONFLIKT`** scannen (aus
   `curl -s http://localhost:8000/api/jobs/<id>`). Jeder `| KONFLIKT <Feld>: …`-Anhang ist ein Thema.
2. **Aktiv gegenprüfen** (auch ohne vorhandenen Vermerk — Konflikte können nach der Erfassung entstehen):
   Eckdaten (`work_model`, `location`, `seniority`) gegen den **Snapshot** (`job.posting_snapshot_path`,
   inkl. dessen Abschnitt „⚠️ Widersprüche", falls vorhanden) und die Company-Fit-Aussagen. Neu gefundener,
   BELEGTER Konflikt → sofort per **read-then-append**-PATCH ans `verify_note` anhängen (Format wie
   firma-pruefen 3b: `| KONFLIKT <Feld>: <A> vs. <B> — im Gespräch klären (geprüft <ISO>)`; bestehenden
   Wert erst lesen, kein Doppel) — die Erfassung nachziehen, nicht nur verwenden.
3. Jeder gefundene Konflikt wird in Schritt 4 zur **ersten** offenen Frage (Abschnitt 2) UND zum
   **⚠️-Merker** im Spickzettel (Abschnitt 4) — s. dort. Kein Konflikt → nichts erzwingen (kein leerer Abschnitt).

### 4. Briefing-HTML erzeugen
Self-contained (keine externen Abhängigkeiten — wird lokal ausgeliefert), Aufbau und Klassen aus
`assets/report_theme_bms.html` (Phase 30 — Datei lesen und das Muster wörtlich übernehmen; gleiche
Farbwelt wie die Company-Fit-Dashboards, aber statisches HTML). Kein CSS und keine Farbwerte
abschreiben: Das Briefing entsteht ohne eigenen Style-Block, den Stil setzt der Pflichtschritt unten ein.

**Kopf (Phase 35, `header.head` — ersetzt die bisherige eigene „Gesprächskontext"-Karte):** eyebrow
„Interview-Briefing" → h1 = Rolle → sub „Firma · Job &lt;id&gt; · Runde n" → beschriftetes Meta-Grid
„Termin · Art/Runde · Interviewer · Fit-Ampel". **Pflicht-Element (Phase 24 F) bleibt: Fit-Ampel als
farbiger Punkt + Text**, jetzt als Meta-Wert (nicht mehr eigener Abschnitt):
- Quelle **zuerst** `company.fit_ampel` (aus den in Schritt 1 geladenen Job-Daten) — `gruen`/`gelb`/`rot`.
- **Alt-Bestand ohne das Feld:** aus der bereits gelesenen Dashboard-HTML (Schritt 2a) die
  Ampel-Zeile suchen (Muster „Ampel-Fit: 🟢|🟡|🔴 — …“, steht dort im Kopf/Fazit) und daraus ableiten.
- Weder Feld noch Dashboard-Aussage vorhanden → **grau, „nicht bewertet"** (nie einen Wert erfinden).
- Rendering: `<span class="dot amber"></span>` (Klassen `.dot.green/.amber/.red/.grau`, aus dem
  Template) direkt vor dem Text im Meta-Wert: „**Ampel-Fit: Grün|Gelb|Rot — <Kernbegründung aus dem
  Dashboard>**" (bzw. „nicht bewertet" ohne Begründung). Interviewer-Kurzrecherche (falls Name
  bekannt), die nicht in den Kopf passt, wird zur ERSTEN Content-Karte unter dem Kopf.

**Pflicht-Abschnitte (Content-Karten unterhalb des Kopfs):**

1. **Erwartbare Fragen + Antwortskizzen** — 8–12 Fragen, rollen- und runden-spezifisch (HR-Screen anders als
   Fachgespräch/Final). Je Frage eine **STAR-Antwortskizze mit ECHTEN Belegen aus dem CV des Nutzers** — keine
   Erfindungen. Bei Runde ≥ 2 zusätzlich einen Block „Aus Runde n-1 offen" aus den Transkript-Lücken.
2. **Offene Fragen AN die Firma** — 6–10 Stück, priorisiert; gespeist aus Company-Fit-Risiken/-Klärungsfragen,
   Unklarheiten der Stellenanzeige und aktuellen News. Als **Checkliste** (zum Abhaken im Call).
   **Konflikte zuerst (Phase 21):** Jeder in Schritt 3b gefundene Quellen-Konflikt steht als **ERSTE**
   Frage(n) der Liste — beide Quellen WÖRTLICH zitiert, z. B. „Die Anzeige beschreibt die Rolle als
   ‚Remote-first across Europe', das LinkedIn-Posting ist als On-site München markiert — wie sieht die
   reale Präsenz-Erwartung aus?"
3. **Einwand-Handling** — Gehalt, Wechselmotiv, evtl. Lücken/Seniorität — je 2–3 Formulierungshilfen.
4. **Spickzettel** — 5 Kernbotschaften + 3 rote Linien (aus `config/profil.md`). **Plus (Phase 21):**
   jeder Konflikt aus Schritt 3b als Merker **„⚠️ Unbedingt klären: <Feld — Kern des Widerspruchs>"** —
   damit er im Gespräch nicht untergeht, auch wenn Abschnitt 2 nicht abgearbeitet wird.
5. **Test-/Assessment-Vorbereitung (nur wenn im Prozess erwähnt** — Mail, Anzeige oder Transkript):
   typische Formate für Senior-Leadership einordnen (Management-Case/Fallstudie, Postkorb, Logik-/Numerik-Tests,
   Persönlichkeits-/Kultur-Fragebogen, Panel-Präsentation) + je Format 2–3 konkrete Übungsempfehlungen und
   was die Firma damit prüft. Weglassen, wenn kein Test angekündigt ist — kein Raum verschwenden.

**Speichern** unter `data/interview_prep/<dateiname>`. Den Basisnamen liefert der zentrale Report-
Namens-Helfer (Phase 30 — löst das bisherige `Briefing_Job<id>_R<runde>_<Firma>`-Muster ab; die
Job-ID ist bewusst NICHT mehr im Namen, sie steht in der DB):
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -c "from app.naming import report_filename; print(report_filename('Briefing', '<Firma>', '<Rolle>', runde=<runde>))"
# → JJJJMMTT_Briefing_<Firma>_<Rolle>_R<runde>   (ohne Extension; .html anhängen)
```

**Pflichtschritt nach dem Schreiben** — erst den Stil einsetzen, dann prüfen:
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.bericht_stil einsetzen "../data/interview_prep/<datei>.html" && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.report_check "../data/interview_prep/<datei>.html"
```
Meldet einer der beiden Befehle eine Klasse ohne Regel: die Klasse durch eine aus der Vorlage ersetzen
(kein eigenes CSS) und beide Befehle wiederholen. Erst danach registrieren.

### 5. Registrieren
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -c "from pipeline.interview import register; print(register(<id>, interview_id=<runde-id>, prep_path='data/interview_prep/<datei>.html'))"
```
Danach zeigt das Interview im Job-Detail den Link **„📋 Briefing öffnen"**.

### 6. Bericht an den Nutzer
3–5 wichtigste Punkte: die kritischste erwartbare Frage, die Top-Fragen an die Firma, die Kernbotschaft.
Plus Hinweis: Briefing hängt am Job-Detail (http://localhost:8000/jobs/<id>). Wenn in Schritt 1 ein Interview
neu angelegt wurde, das erwähnen (Art/Runde ggf. korrigieren).

## Abgrenzung
- **Kein CV-Rewrite** — das sind `cv-match` („CV-Match für Job <id>") und `cv-erstellen`.
- **Keine Firmen-Analyse von Grund auf** — das ist `firma-pruefen`. Fehlt `fit_analysis_path`, empfehle, den
  zuerst laufen zu lassen (bessere firmenspezifische Fragen), aber **blockiere nicht** — arbeite dann mit
  Stellenanzeige + Web-Recherche.
- Wahrheitstreue vor Vollständigkeit: **nur echte CV-Belege** in den Antwortskizzen, keine erfundenen Projekte/Zahlen.
