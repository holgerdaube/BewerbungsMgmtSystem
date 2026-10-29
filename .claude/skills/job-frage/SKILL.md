---
name: job-frage
description: Beantwortet eine konkrete Frage zu einer Stelle aus dem Bewerbungs-Management-System des Nutzers ausschließlich aus den vorliegenden Job-Daten und Artefakten (Company-Fit, Snapshot, Briefing, Verlauf, Transkripte) — kein Web. Schreibt die Antwort in den Job-Chat UND als Eintrag in „Notizen & Verlauf". Nutze diesen Skill bei "Frage zu Job <id>: <frage>".
---

# Job-Frage (KI-Chat am Job-Detail)

Beantwortet EINE Frage zu einer Stelle, ausschließlich aus dem, was im System bereits vorliegt.
Läuft headless (Chat-UI am Job-Detail), Ziel < 60 s Laufzeit. **Kein WebSearch/WebFetch** (per
Runner-Konfiguration — `disallowed_tools` in `agent_runner.PROMPTS["job-frage"]` — technisch
gesperrt) — das ist Absicht: schneller, billiger, und die Antwort ist an echten Belegen aus der
DB/den Artefakten festmachbar statt an einer Web-Recherche, die die vorliegenden Daten überschreiben
könnte.

## Ablauf

### 1. Kontext laden (nur was die Frage braucht)
```sh
curl -s http://localhost:8000/api/jobs/<job_id>
curl -s http://localhost:8000/api/jobs/<job_id>/chat
```
Aus der Job-Antwort verfügbare Artefakt-Pfade sichten (nicht alle lesen — nur die, die die Frage
tatsächlich betrifft):
- `company.fit_analysis_path` — Company-Fit-Dashboard (Geschäftsmodell/Markt/Fit/Red Flags)
- `job.posting_snapshot_path` — Original-Stellenausschreibung (Snapshot)
- `interviews[].prep_path` — Interview-Briefings
- `transcripts[].debrief_path`, `transcripts[].summary` — Gesprächsauswertungen
- `cv_versions[].match_dashboard_path`, `cv_versions[].ats_scan_path` — CV-Match/ATS
- `application.cover_letter_pdf_path` — Anschreiben
- die Job-/Company-Felder selbst (`status`, `next_step`, `notes`, `salary`, `situation`, …)

Die letzten ~10 Einträge aus `/chat` sind der Folgefragen-Kontext ("und im Vergleich zu Firma X?").
Company-Fit-Dashboards sind JS-gerendert (`<div id="root"><script>const DATA = {…}</script>`) — beim
Lesen den Inhalt aus dem `DATA`-Objekt im `<script>`-Block entnehmen, nicht aus dem sichtbaren
`<body>`-Text (der ist leer).

Nur EIN, maximal ZWEI der obigen Artefakte tatsächlich mit dem Read-Tool öffnen — die, die zur
konkreten Frage passen. Pauschal alles lesen kostet Zeit und Budget ohne Nutzen.

### 2. Antwort formulieren
- Kompaktregeln (wie job-deepdive/firma-pruefen): keine Vorrede, keine Markdown-Überschriften,
  **≤ 150 Wörter**.
- Faktentreu: nur behaupten, was in den geladenen Quellen tatsächlich steht. Steht die Antwort
  NICHT in den Quellen: das ehrlich sagen ("Dazu liegt im System nichts vor") und, wenn plausibel,
  einen passenden nächsten Schritt nennen (z. B. „Firma prüfen ausführen", „Interview vorbereiten").
  Niemals eine Zahl oder Tatsache erfinden, um die Frage „vollständiger" aussehen zu lassen.
- **Letzte Zeile immer:** `Quellen: <kurz, z. B. Company-Fit, Snapshot, Verlauf>` (oder
  `Quellen: keine — liegt im System nicht vor`, wenn nichts einschlägig war).

### 3. Antwort speichern — ki-Row im Job-Chat + Eintrag in „Notizen & Verlauf"
**⚠️ Dieser Schritt ist AUSNAHMSLOS Pflicht — auch wenn die „Frage" eigentlich ein Auftrag
für einen anderen Skill ist** (Echtfall 30.07.2026: der Nutzer bat im Chat um eine
Antwort auf eine Absage-Mail; der Lauf erstellte hilfreich den Gmail-Entwurf über den
mail-antwort-Weg, ließ aber die ki-Row weg — für den Nutzer sah es aus, als sei NICHTS passiert,
denn der Chat ist der einzige Ort, den er nach einer Chat-Frage ansieht; die
Abschlussmeldung landet nur im Task-Center). In so einem Fall: das Sinnvolle tun (bzw. auf
den passenden Skill/Trigger verweisen) UND die ki-Row schreiben — mit dem Ergebnis und wo
es liegt (z. B. „Entwurf liegt in Gmail bereit …"). Ein Lauf ohne ki-Row ist ein
gescheiterter Lauf, egal was er sonst erledigt hat.
**⚠️ Frage/Antwort NIE als Python-String-Literal einsetzen (P2-15, Code-Review 2026-07-25):** ein
`"` oder `\` im Text (z. B. ein zitierter Firmenname) würde das folgende Python sonst brechen.
Zuerst als JSON schreiben (Write-Tool, `data/tmp/job_frage_<job_id>.json`,
`{"frage": "…", "antwort": "…"}`), dann im Heredoc per `json.load` einlesen — beide
Schreibvorgänge zusammen (Muster `gespraech-debrief`):
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python - <<'PY'
import json
from pathlib import Path
from sqlmodel import Session
from app.db import engine
from app.models import JobChat, JobLog

JOB_ID = <job_id>
TASK_ID = <task_id oder None>   # aus dem Trigger-Kontext, falls bekannt — sonst None
daten = json.loads(Path("../data/tmp/job_frage_<job_id>.json").read_text(encoding="utf-8"))
FRAGE, ANTWORT = daten["frage"], daten["antwort"]

with Session(engine) as s:
    chat = JobChat(job_id=JOB_ID, rolle="ki", text=ANTWORT, task_id=TASK_ID)
    s.add(chat)
    log = JobLog(job_id=JOB_ID, art="ki-chat",
                 eintrag=f"Frage: {FRAGE}\n\nAntwort: {ANTWORT}")
    s.add(log)
    s.commit()
    print("JobChat", chat.id, "· JobLog", log.id, "angelegt")
PY
```
Die Anzeige-Kompaktheit im Job-Log regelt die Web-App (Klapp-Regel, Phase 28 F) — hier wird NICHTS
gekürzt, der volle Frage+Antwort-Text landet in `JobLog.eintrag`.

### 4. Abschlussmeldung des Laufs = die Chat-Antwort selbst
Die Meldung an den Nutzer IST die Antwort aus Schritt 2 — kein zusätzlicher Kommentar, keine
"Erledigt"-Vorrede. Der Lauf endet mit genau dem Text, der auch im Chat und in „Notizen & Verlauf"
steht (identisches `result`, Zeile 1 = das allererste Zeichen — Muster `job-deepdive`).

## Grenzen
- Genau eine Frage pro Lauf, kein Multi-Turn innerhalb eines Laufs (Folgefragen sind neue Läufe,
  die den Chat-Verlauf aus Schritt 1 als Kontext lesen).
- Keine Web-Recherche — reine Auskunft aus dem System. Braucht die Frage neue Fakten von außen,
  ehrlich auf den passenden Recherche-Skill verweisen (`firma-pruefen`, `entscheider-recherche`, …),
  nicht raten.
- Keine DB-Änderungen außer der eigenen ki-Row + dem JobLog-Eintrag — keine Status-/Feld-Änderungen
  am Job selbst (dafür gibt es die PATCH-Endpoints/andere Skills).
