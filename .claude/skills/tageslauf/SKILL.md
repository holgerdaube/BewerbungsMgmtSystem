---
name: tageslauf
description: Der tägliche Morgenlauf für das Bewerbungs-Management-System des Nutzers — bündelt Jobsuche, Gmail-Check und Ansichten-Refresh zu einem Durchlauf und präsentiert eine kompakte Morgen-Zusammenfassung. Nutze diesen Skill bei "Tageslauf", "mach den Morgenlauf", "neuer Tag neues Glück", "check alles", "was ist heute wichtig", "täglicher Bewerbungs-Check".
---

# Tageslauf (Claude-in-the-Loop)

Ein Befehl, der den kompletten täglichen Zyklus ausführt und dir das Ergebnis fürs
Frühstück zusammenfasst. Führt die Einzel-Skills der Reihe nach aus.

## Ablauf

### 1. Jobsuche
Führe den Skill **`jobsuche`** aus: Portale durchsuchen → dedup → Scoring 1–5 → neue Treffer
als „Neu" in die DB. (Merke dir Anzahl neuer Treffer und die mit Score ≥4.)

### 1b. Postfach-Stellen
Führe den Skill **`mail-jobsuche`** aus: Job-Alert-Mails (LinkedIn) aus dem Postfach →
Postings extrahieren → harte Grenzen + Scoring 1–5 → über denselben Ingest als „Neu" in die DB.
**NACH der Jobsuche laufen lassen (seriell):** beide schreiben über `pipeline.ingest`; parallel
liefe das Dedup-Fenster auseinander und ließe Dubletten durch. (Merke dir „X neu, davon Y Top".)

### 1c. Zielfirmen-Sweep
Führe den Skill **`zielfirmen-sweep`** aus: die 12 am längsten ungeprüften Zielfirmen-Karriereseiten
prüfen (Rotation) → Vier-Augen → über denselben Ingest als „Neu" in die DB. NACH 1/1b (seriell,
gemeinsames Dedup-Fenster). (Merke dir „X Firmen geprüft, Y neu".)

### 1d. Headhunter-Suche
Führe den Skill **`headhunter-suche`** aus: die 15 am längsten ungeprüften Headhunter-Webseiten auf
passende Mandate prüfen (Rotation, vertrauliche Mandate ohne Klientennamen möglich) → Vier-Augen →
Ingest. (Merke dir „X Headhunter geprüft, Y Mandate".)

### 1e. Beworben-Check (wöchentlich)
Eigener 7-Tage-Vorab-Check, UNABHÄNGIG von der Ketten-Erkennung im Skill selbst (die greift nur,
wenn `beworben-check` als Teil der Backend-Kette mit eigener `chain_id` läuft — im interaktiven
Tageslauf gibt es keine solche Kette, deshalb prüft dieser Schritt hier selbst vorab und spart den
Lauf im Regelfall komplett):
```sh
cd backend
curl -s "http://localhost:8000/api/jobs?statuses=Beworben,Interview" | ~/.bewerbung_mgmt_venv/bin/python -c "
import sys, json
from datetime import date

jobs = json.load(sys.stdin)
daten = sorted((j.get('availability_checked_at') for j in jobs if j.get('availability_checked_at')), reverse=True)
if not daten:
    print('RUN — noch nie geprüft')
else:
    juengste = daten[0]
    tage = (date.today() - date.fromisoformat(juengste)).days
    print(f'SKIP {juengste}' if tage < 7 else f'RUN {juengste} ({tage} Tage)')
"
```
- Ausgabe `RUN …` (älter als 7 Tage oder noch nie geprüft) → Führe den Skill **`beworben-check`**
  aus. (Merke dir aus dessen Abschlussmeldung „X geprüft, Y offline".)
- Ausgabe `SKIP <Datum>` (jünger als 7 Tage) → überspringen, fürs Fazit merken: „übersprungen
  (zuletzt <Datum>)".

### 2. Gmail-Check
Führe den Skill **`email-check`** aus: bewerbungsrelevante Mails der letzten 24–36h erfassen →
klassifizieren → zuordnen → Antwortzeiten/Kontakte/Status. (Merke dir Absagen/Einladungen,
offene „zu beantworten"-Mails und die Zahl „ohne Stelle → Inbox" aus dessen Bericht — Phase 36.)

### 3. Ansichten aktualisieren
Excel-View + Tages-Digest neu erzeugen (deterministisch, kein LLM nötig), inkl. Suchindex:
```sh
Bewerbung_Mgmt_System/scripts/refresh_views.sh
```
Erzeugt `data/exports/JJJJMMTT_Bewerbungs-Stand.xlsx` und `data/digests/JJJJMMTT_Bewerbungs-Digest.html` und
baut den Volltextsuche-Index (Phase 25) frisch (`pipeline.search_index rebuild`).

### 4. Verbrauch syncen (best effort)
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.budget sync
```
Zieht den echten Apify-Tagesverbrauch. Schlägt es fehl (kein Token, kein Netz), ist das **kein Fehler**
des Tageslaufs — kurz erwähnen und weitermachen.

### 5. Morgen-Zusammenfassung
Fasse in 5–8 Zeilen zusammen:
- **Neue Top-Treffer** (Score ≥4) mit Firma/Rolle → Link zur Review-Ansicht.
- **Aus Job-Mails:** X neu, davon Y Top (Ergebnis der Postfach-Stellen aus Schritt 1b).
- **Zielfirmen-Sweep:** X Firmen geprüft, Y neu (Rotationsstand aus Schritt 1c).
- **Headhunter-Suche:** X Headhunter geprüft, Y Mandate (Rotationsstand aus Schritt 1d).
- **Beworben-Check:** X geprüft, Y offline (Ergebnis aus Schritt 1e) bzw. „übersprungen (zuletzt
  <Datum>)", falls die 7-Tage-Regel gegriffen hat.
- **Gmail heute:** Einladungen / Absagen / offene „zu beantworten"-Mails (mit Namen). Plus, falls
  >0: „N E-Mails ohne Stelle → Inbox" (Phase 36) mit Link zur Inbox-Ansicht.
- **Offene Aktionen:** Stellen in „Prüfen" mit nächstem Schritt. **Plus fällige/überfällige
  Netzwerk-Aktionen** (Phase 22) — Quelle: `curl -s http://localhost:8000/api/followups` → `netzwerk[]`
  (jeder Eintrag mit `overdue`, `name`, `unternehmen`, `next_action`): überfällige zuerst, mit Name +
  Aktion nennen, damit der Termin nicht untergeht.
- **Wurde ein Schritt wegen des Budgets übersprungen?** (Exit-Code **2** eines Clients heißt
  „Budget erschöpft", nicht „Fehler".) Dann hier ausweisen, mit dem Grund und dem Hinweis auf
  http://localhost:8000/budget — sonst fehlt dem Bericht ein Teil, ohne dass es jemand merkt.
- **Cleanup-Check (Phase 33, nur Meldung, löscht nie):** `cd backend &&
  ~/.bewerbung_mgmt_venv/bin/python -m pipeline.cleanup scan` mitlaufen lassen (read-only) — nur
  erwähnen, wenn die Antwort `auffaellig: true` liefert (>50 MB rotierbar oder >10 Orphans), sonst
  schweigen. Aufruf ist IMMER `scan`, nie `apply`/`leeren` (die laufen nur auf Zuruf des Nutzers).
- Verweise auf Dashboard (http://localhost:8000) und den frischen Digest.

## Grenzen
- Deep-Dives (Company-Fit + CV) laufen bewusst NICHT automatisch mit — auf Zuruf per `job-deepdive`
  für die Treffer, die du wirklich verfolgen willst.
- Gmail bleibt read-only (kein Senden/Labeln).
- Zeitgesteuerte Vollautomatik ist vorbereitet, aber nicht aktiv — siehe `docs/AUTOMATION.md`.
