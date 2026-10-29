---
name: absagen-analyse
description: Wertet alle Absagen und unbeantworteten Bewerbungen aus dem Bewerbungs-Management-System systematisch aus (Lost-Order-Analyse) — was haben sie gemeinsam, wo fällt der Nutzer raus (Screening vs. Gespräch), welcher Kanal/Level/Score-Zusammenhang zeigt sich — füllt Absagegründe aus den Mail-Texten nach application.rejection_reason, erzeugt einen Muster-Bericht als HTML und übernimmt beim Start von Hand die Empirie-Zeilen in config/profil.md (im automatischen Wochenlauf des Tageslaufs nur als Vorschlag im Bericht). Nutze diesen Skill bei "Absagen-Analyse", "analysiere die Absagen", "was haben die Absagen gemeinsam", "Lost-Order-Analyse", "Absagen auswerten", "warum werde ich abgelehnt".
---

# Absagen-Analyse (Lost-Order / Lessons Learned)

Beantwortet: **Woran scheitern die Bewerbungen wirklich — und was ändern wir?** Vergleicht drei Gruppen:
Absagen, Funkstille (beworben, nie Antwort — inkl. als „Keine Rückmeldung" markierter Stellen) und
Positiv (Interview/Angebot). Nur belegte Muster, keine
Spekulation; kleine Stichproben ehrlich als Hypothese kennzeichnen.

## Ablauf

### 1. Lauf-Art erkennen (automatischer Wochenlauf oder Start von Hand?)
```sh
curl -s "http://localhost:8000/api/tasks?kinds=absagen-analyse&limit=5"
```
Die Liste ist absteigend nach ID sortiert. Der oberste Eintrag mit `"status": "running"` ist dein
eigener, gerade laufender Task — der Agent-Runner setzt den Status auf `running`, bevor dieser
Skill-Lauf beginnt. Ältere Einträge (`status` done/failed/cancelled) sind vergangene Läufe, für
diese Erkennung irrelevant.

- **`chain_id` dieses Eintrags ist gesetzt** (ein Hex-String) → **automatischer Wochenlauf**
  (Schritt des Tageslaufs).
- **`chain_id` ist `null`** (Button „Absagen-Analyse“ im Dashboard) **oder kein Eintrag mit
  `status: "running"` auffindbar** (Direktaufruf im Chat ohne Task-Infrastruktur) → **Start von
  Hand**.

Ob der Wochenlauf fällig ist, hat der Runner schon vor dem Start entschieden (ein Bericht je
Kalenderwoche; gibt es nichts auszuwerten, startet der Skill gar nicht). Prüfe es hier **nicht
noch einmal** — wenn du läufst, wird ausgewertet. Merke dir die Lauf-Art für Schritt 5 und 6.

### 2. Datenzug (SQLite, read-only)
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python  # sqlite3 auf data/bewerbung.sqlite
```
- **Beispieldaten und gelöschte Stellen ausschließen:** Stellen mit `job.portal = 'Beispieldaten'`
  (die erfundenen Stellen einer frischen Installation) und gelöschte Stellen (`job.deleted_at` gesetzt,
  etwa zusammengeführte Dubletten) gehören in keine Gruppe und in keine Basisrate — in jeder Abfrage
  `COALESCE(job.portal, '') != 'Beispieldaten' AND job.deleted_at IS NULL`.
- **Absagen:** `job.status='Absage'` + zugehörige `application` + `email.category='Absage'` (Snippets!).
- **Funkstille:** `status='Beworben'` ohne eingehende Mail (NOT EXISTS auf `email.direction='incoming'`)
  **ODER** `status='Keine Rückmeldung'` (Phase 85 — der vom Nutzer manuell gesetzte Ghosting-
  Endstatus IST die bestätigte Funkstille, nicht ihr Gegenteil; ohne diese Erweiterung würden genau
  die Fälle aus der Analyse fallen, die der Nutzer explizit als Ghosting markiert hat).
- **Positiv:** `status IN ('Interview','Angebot')`.
- Dimensionen: match_score, seniority, portal, work_model/tab, plan_ab, company.situation,
  response_time_hours (Zeit bis Absage), applied_date.
- **Basisraten mitziehen** (Pflicht!): jede Verteilung der Absagen gegen die Verteilung ALLER beworbenen
  Vorgänge stellen — sonst Scheinkorrelationen (Beispiel 09.07.: Scale-up 43 % ≈ Gesamt 39 % → kein Muster).
- **„Beirat abgelehnt" ist KEINE Absage** (Phase 41): explizit aus der Absagen-Basisrate ausschließen —
  das ist die eigene Entscheidung des Nutzers nach dem Beirats-Stellen-Check, keine Firmen-Ablehnung, würde die
  Absagequote sonst künstlich verzerren. Optional als eigene, getrennte Zeile im Bericht nennen: „Selbst
  aussortiert nach Beirats-Check: N" (reine Information, fließt in keine Absage-Statistik ein).
- Dubletten identifizieren (gleiche Rolle, mehrere Job-IDs — z. B. Gmail-erkannte vs. Tracker-Jobs): **nur melden,
  nie selbst löschen/mergen.**

### 3. Absagegründe → `application.rejection_reason`
Aus den Absage-Mail-Snippets klassifizieren — **nur was der Mailtext belegt**:
Standard-Absage ohne Grund · Stelle geschlossen/gestrichen · interner Kandidat · Seniorität/Erfahrung ·
Standort · Sonstiges (Zitat). Mail vorhanden, aber ohne Volltext → „Absage per E-Mail (Volltext nicht erfasst)".
Keine Mail → NULL lassen. Schreiben per Python-Einzeiler (Session auf `Application`, Muster wie `gespraech-debrief`).
Wird im Job-Detail unter Bewerbung → „Absagegrund" angezeigt.

### 4. Muster prüfen (mit Evidenz, gegen Basisraten)
Mindestens: Score↔Outcome (schützt der Zielstellen-Fit?) · Screening vs. Gespräch (Zeit bis Absage; kam
irgendeine Absage NACH einem Interview?) · Kanal (kalte Portal-Bewerbung vs. Netzwerk — Outreach-Response-Rate
als Vergleich) · Seniorität (VP/Director vs. Head/Manager) · Funkstille-Alter (wie lange unbeantwortet,
follow_up_date gesetzt?) · CV-Version (Basis-CV vs. getailort — `cvversion` je Job).

### 5. Bericht erzeugen
Self-contained HTML im Stil von `assets/report_theme_bms.html` (Phase 30 — Datei lesen und
das Muster wörtlich übernehmen: Aufbau und Klassen; kein CSS und keine Farbwerte abschreiben, der
Bericht entsteht ohne eigenen Style-Block) nach `data/analysen/`.
Dateiname über den zentralen Report-Namens-Helfer (löst `dated_filename('Absagen_Analyse','html')` ab):
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -c "from app.naming import report_filename; print(report_filename('Analyse', 'Absagen'))"
# → JJJJMMTT_Analyse_Absagen   (ohne Extension; .html anhängen)
```
**Kopf (Phase 35, `header.head`):** eyebrow „Analyse" → h1 „Absagen" (Thema, kein Firmenbezug) → sub
kurze Datenbasis („N Absagen / M unbeantwortet, Stand JJJJ-MM-TT") → Meta-Grid „Zeitraum ·
Datensätze · Datum" (Quellen weglassen, falls nichts zu verlinken ist).

Pflicht-Abschnitte (Content-Karten unterhalb des Kopfs):
KPI-Lage · Muster mit Evidenz · **Was NICHT belastbar ist** (Limitationen) · Empfehlungen (verknüpft mit
vorhandenen Features: cv-match/cv-erstellen, Follow-ups, Anschreiben/Initiativ) · Datenqualität/Dubletten ·
Absagegrund-Tabelle · **Empirie-Zeilen**. Abrufbar über `/api/artifact?path=data/analysen/<datei>`.

**Karte „Empirie-Zeilen“ (immer, in beiden Lauf-Arten):** die 2–4 datenbasierten Zeilen aus den Mustern
(Schritt 4), wie sie in Schritt 6 ins Profil gehen würden. Gebaut wird sie wie die übrigen
Content-Karten aus `assets/report_theme_bms.html`, nur mit Klassen von dort (kein CSS); der
Pflichtschritt unten (`bericht_stil` und `report_check`) gilt unverändert.
- **Start von Hand:** Überschrift „Empirie-Zeilen (ins Profil übernommen)“.
- **Automatischer Wochenlauf:** Überschrift „Vorschlag für die Empirie-Zeilen (nicht übernommen)“
  und darunter ein Satz: Das Profil bleibt im automatischen Lauf unverändert, ein Start von Hand
  (Dashboard → „Absagen-Analyse“) übernimmt diese Zeilen.

**Pflichtschritt nach dem Schreiben** — erst den Stil einsetzen, dann prüfen:
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.bericht_stil einsetzen "../data/analysen/<datei>.html" && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.report_check "../data/analysen/<datei>.html"
```
Meldet einer der beiden Befehle eine Klasse ohne Regel: die Klasse durch eine aus der Vorlage ersetzen
(kein eigenes CSS) und beide Befehle wiederholen.

### 6. `config/profil.md` pflegen — nur beim Start von Hand
**Start von Hand:** Abschnitt `## Empirie aus dem Bewerbungsverlauf` **ersetzen** (nicht anhängen —
immer aktueller Stand, mit Datum). 2–4 Bullets, nur datenbasiert, dieselben Zeilen wie in der
Bericht-Karte. Fließt in Scoring (`jobsuche`) und CV-Tailoring ein.

**Automatischer Wochenlauf:** `config/profil.md` nicht anfassen — weder den Abschnitt noch das Datum.
Der Vorschlag steht im Bericht; übernehmen kann ihn nur ein Start von Hand.

### 7. Bericht an den Nutzer
Kurzfassung im Chat: die 3–5 wichtigsten Muster + konkrete nächste Schritte (z. B. „für 14 Funkstille-
Bewerbungen follow_up_date setzen — soll ich?"). Vorschlagen, nicht ungefragt ausführen.

## Abgrenzung
- **Ändert keine Job-Status** und löscht nichts. Schreibzugriffe je Lauf-Art:
  - Start von Hand: `application.rejection_reason`, der Bericht und der profil.md-Empirie-Abschnitt.
  - Automatischer Wochenlauf: `application.rejection_reason` und der Bericht; `config/profil.md`
    bleibt unverändert.
- Dubletten-Bereinigung, Nachfass-Mails, Anpassungen am Bewertungsraster: nur als Empfehlung an den Nutzer.
- Kleine n ehrlich benennen; Hypothese ≠ Befund.
