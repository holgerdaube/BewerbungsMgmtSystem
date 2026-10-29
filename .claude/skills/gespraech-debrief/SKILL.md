---
name: gespraech-debrief
description: Wertet nach einem Interview ein Transkript einer Stelle aus dem Bewerbungs-Management-System aus — nach der Leitfrage des Nutzers (was gesagt/nicht gesagt wurde, Stimmung, vergessene Themen, offene Fragen) plus was gut/wackelig lief, gestellte Fragen, Signale & Red Flags. Ersetzt den Transkript-Report durch die Vollversion (Findings gefüllt, Summary 3–5 Sätze), setzt den Interview-Status, pflegt Interviewer als Kontakte und die zentrale Fragenbank, setzt Job-Follow-up und legt einen Danke-Mail-ENTWURF in Gmail an (nie senden). Nutze diesen Skill bei "Debrief für Job <id>", "Debrief für Job <id> Transkript <tid>", "werte das Gespräch aus", "Transkript auswerten für Job <id>", "Gespräch nachbereiten", "Debriefing".
---

# Gespräch-Debrief (Auswertung & Lernschleife)

Schließt den Kreis nach einem Gespräch: **Was habe ich gelernt, was ist offen, was folgt?**
Der Skill analysiert das Transkript nach den fünf Leitfragen des Nutzers und ERSETZT den Basis-Report unter
`transcript.report_path` (existiert bereits seit Anlage/Upload des Transkripts, Phase 30) durch die
Vollversion mit gefüllten Findings — kein separates Debrief-HTML mehr. Bereitet außerdem die
Danke-Mail als Entwurf vor — gesendet wird nie. Läuft headless (Web-App-Button) wie interaktiv.

## Ablauf

### 1. Job + Transkript laden
Job-ID aus dem Auslöser (z. B. „Debrief für Job <id>"):
```sh
curl -s http://localhost:8000/api/jobs/<id>
```
**Welches Transkript?**
- Trigger nennt **„Transkript <tid>"** → genau dieses aus `transcripts` (Feld `id == tid`).
  So startet der „🧠 Auswerten"/„🧠 Erneut auswerten"-Button aus dem Job-Detail.
- Trigger nennt kein Transkript → `transcripts[0]` (das neueste, absteigend sortiert).
- **Kein Transkript vorhanden: abbrechen** — Hinweis, erst eins hochzuladen/einzufügen.
- Jedes Transkript hat bereits `report_path` (Basis-Report, automatisch bei Anlage/Upload erzeugt,
  Phase 30) — diesen NICHT ignorieren: er wird in Schritt 3 durch die Vollversion ersetzt, nicht neu
  angelegt.

Die Transkript-DATEI unter `file_path` lesen. **Das kann seit Phase 11 auch `.pdf`/`.docx`/`.vtt` sein**
(hochgeladen statt eingefügt) — direkt lesen (Read-Tool kann pdf/docx). Merke dir `tid`, `job.company_name`,
`job.title` und aus der Transkript-Row `kontakt` + `gespraechsart` (Gesprächspartner/-art, falls gesetzt).

### 2. Analyse erzeugen — fünf Leitfragen des Nutzers (PFLICHT)
Vorgabe des Nutzers, wörtlich als Leitfaden:
> „Ich hatte gerade ein Telefonat / Video-Call / Gespräch mit **<Kontakt>** zur Stelle **<Stelle>** bei der
> Firma **<Firma>**. Hier das Transkript. Fasse zusammen, **was gesagt wurde**, **was nicht gesagt wurde**,
> **wie die Stimmung war**, **welche Themen vergessen wurden** und **welche Fragen ich noch hätte stellen sollen**."

Daraus die fünf PFLICHT-Abschnitte (in dieser Reihenfolge, mit Belegen/Zitaten aus dem Transkript):
1. **Was gesagt wurde** — Kernaussagen beider Seiten, Zusagen, vereinbarte nächste Schritte, Prozess-Infos.
2. **Was NICHT gesagt wurde** — erwartbare, aber ausgebliebene Punkte (Gehalt, Entscheidungsweg, Team-Größe,
   Warum ist die Stelle offen, Zeitplan …), je mit Einschätzung: neutral oder ein Signal?
3. **Stimmung** — Tonalität, Interesse-Signale, Zurückhaltung/Skepsis, Gesprächsanteile (wer redete wie viel),
   belegt durch kurze Zitate.
4. **Vergessene Themen** — was der Nutzer platzieren wollte und nicht platziert hat. **Wenn ein Briefing der Runde
   existiert** (`interviews[].prep_path`), dagegen abgleichen: welche geplanten Botschaften/Fragen fehlen?
5. **Fragen, die noch zu stellen gewesen wären** — konkret ausformuliert; wandern in die Fragenbank UND werden
   Kandidaten für die Follow-up-Mail / das nächste Gespräch.

Ergänzend (kurz, für DB/Follow-up): gestellte Fragen der Firma (vollständig → Fragenbank), offene Punkte
beidseitig (→ `todos_json`), Signale & Red Flags inkl. Gehalt/Prozess/Zeitplan, empfohlener nächster Schritt
mit Datum (→ Job-`next_step` + `follow_up_date`).

### 3. Report ersetzen + Transcript aktualisieren (PFLICHT, EIN Aufruf)
**⚠️ ERSETZEN, NIEMALS ANHÄNGEN (Phase 35 — eiserne Regel, ein Bug in freier Wildbahn hat genau das
verletzt: eine Session hat ihr Debrief-HTML per eigenem Python/Shell-Snippet in die bestehende
Report-Datei GEHÄNGT statt sie zu ersetzen — Ergebnis war ein Dokument mit ZWEI Köpfen). Der EINZIGE
korrekte Weg, den Report zu schreiben, ist der `render_full()`-Aufruf unten — niemals selbst Dateien
unter `report_path` öffnen/schreiben/anhängen, kein eigenes HTML zusammenbauen.**
Kein PATCH-Endpoint für Transcripts nötig — `pipeline.transcript_report.render_full()` (Phase 30,
Kopf seit Phase 35 im Debrief-Referenz-Look — eyebrow „Gesprächs-Debrief" → h1=Rolle → sub → Meta-
Grid Kontakt/Art/Datum/Status danach, automatisch aus Job/Interview/Transcript befüllt, NICHTS davon
selbst bauen) übernimmt in einem Rutsch: Report-HTML neu rendern, **dieselbe Datei unter
`report_path` überschreiben** (Dateiname bleibt stabil, kein Duplikat, kein separates Debrief-HTML
mehr), `summary` (**Pflicht, 3–5 Sätze** — die einzige Inhaltsanzeige rechts im Job-Detail) und
`todos_json` setzen. `debrief_path` wird für Neufälle bewusst NICHT gesetzt. Optional `status_danach`
mitgeben (Meta-Spalte „Status danach" im Kopf) — z. B. „Absolviert · Feedback zugesagt bis ca.
24.07."; ohne Angabe fällt es auf den reinen Interview-Status zurück. `sections` bildet die
**fünf Pflicht-Abschnitte aus Schritt 2** ab (in dieser Reihenfolge) plus die ergänzenden Inhalte —
`summary` erscheint automatisch als erste Karte „Zusammenfassung" im Report, muss also nicht separat
in `sections` wiederholt werden.

**⚠️ Fließtext/Zitate NIE als Python-Literal einsetzen (P2-15, Code-Review 2026-07-25):** die
Abschnitte, `summary` und `todos` enthalten wörtliche Transkript-Zitate — ein `"` oder `\` darin
würde das folgende Python sonst brechen (im ungünstigen Fall syntaktisch gültig, aber
unbeabsichtigt verändern). Deshalb ZUERST ALLES zusammen als EINE JSON-Datei schreiben (Write-Tool,
`data/tmp/debrief_<TID>.json`):
```json
{
  "sections": [
    {"title": "Was gesagt wurde", "html": "<p>…Kernaussagen, Zusagen, nächste Schritte, mit Zitaten…</p>"},
    {"title": "Was NICHT gesagt wurde", "html": "<ul class='clean'><li>…</li></ul>"},
    {"title": "Stimmung", "html": "<p>…Tonalität, Interesse-Signale, belegt durch Zitate…</p>"},
    {"title": "Vergessene Themen", "html": "<p>…ggf. Abgleich gegen das Briefing der Runde…</p>"},
    {"title": "Fragen, die noch zu stellen gewesen wären", "html": "<ul class='clean'><li>…</li></ul>"},
    {"title": "Gestellte Fragen der Firma", "html": "<ul class='clean'><li>…</li></ul>"},
    {"title": "Signale & Red Flags", "html": "<p>…Gehalt/Prozess/Zeitplan…</p>"},
    {"title": "Nächste Schritte", "html": "<p>…empfohlener nächster Schritt mit Datum…</p>"}
  ],
  "summary": "<3–5 Sätze Kurz-Zusammenfassung — landet als Karte im Report UND rechts im Job-Detail>",
  "todos": ["<offener Punkt 1>", "<offener Punkt 2>"],
  "status_danach": "<optional, z. B. 'Absolviert · Feedback zugesagt bis ca. JJJJ-MM-TT'>"
}
```
Dann EIN Aufruf, der die Datei einliest statt den Inhalt einzutippen:
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python - <<'PY'
import json
from pathlib import Path
from pipeline.transcript_report import render_full

daten = json.loads(Path("../data/tmp/debrief_<TID>.json").read_text(encoding="utf-8"))
result = render_full(
    <TID>, daten["sections"], summary=daten["summary"],
    todos=daten.get("todos"), status_danach=daten.get("status_danach"),
)
print(result)   # {"transcript_id": …, "report_path": …, "summary": …}
PY
```
**Interview-Status:** `curl -s -X PATCH http://localhost:8000/api/interviews/<iid> -H 'Content-Type: application/json' -d '{"status":"Absolviert"}'`
**Job fortschreiben:** `curl -s -X PATCH http://localhost:8000/api/jobs/<id> -H 'Content-Type: application/json' -d '{"next_step":"…","follow_up_date":"JJJJ-MM-TT"}'`

Das Job-Detail zeigt danach den vollständigen Report über „📄 Report öffnen" an der Transkript-Zeile
(gleicher Link wie vorher, jetzt mit gefüllten Findings statt „Debrief ausstehend").

### 4. Interviewer → Kontakte (ohne Duplikate)
Im Transkript genannte Gesprächspartner gegen `contacts` aus Schritt 1 abgleichen
(**Name-Match, case-insensitive** — job- UND firmenweite Kontakte). Nur NEUE anlegen — Name/Rolle
zuerst als JSON schreiben (Write-Tool, `data/tmp/kontakt_<id>.json`, `{"name": "…", "role": "…"}`),
NICHT als Python-String-Literal einsetzen (P2-15, Code-Review 2026-07-25 — derselbe Grund wie in
Schritt 3: ein `"`/`\` im Namen würde das Python sonst brechen):
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python - <<'PY'
import json
from pathlib import Path
from sqlmodel import Session, select
from app.db import engine
from app.models import Contact, Job
JOB_ID = <id>
kontakt = json.loads(Path("../data/tmp/kontakt_<id>.json").read_text(encoding="utf-8"))
NAME, ROLE = kontakt["name"], kontakt["role"]
with Session(engine) as s:
    job = s.get(Job, JOB_ID)
    vorhanden = s.exec(select(Contact).where((Contact.job_id == JOB_ID) | (Contact.company_id == job.company_id))).all()
    if any((c.name or "").strip().lower() == NAME.strip().lower() for c in vorhanden):
        print("Kontakt existiert bereits — übersprungen")
    else:
        c = Contact(company_id=job.company_id, job_id=JOB_ID, name=NAME, role=ROLE)
        s.add(c); s.commit(); print("Kontakt angelegt:", c.id, NAME)
PY
```

### 5. Fragenbank pflegen
`data/interview_prep/fragenbank.md` (anlegen, falls fehlt) — pro Gespräch EINEN Abschnitt anhängen:
```md
## JJJJ-MM-TT — <Firma> — Runde <n> (<Art>)
- <tatsächlich gestellte Frage 1>
- <Frage 2>
```
Diese Datei liest `interview-vorbereiten` (Stufe B) als Input für künftige Briefings — echte Fragen
schlagen erwartete Fragen.

### 6. Danke-/Follow-up-Mail als ENTWURF (nie senden)
Sprache = Gesprächssprache (DE/EN). Inhalt: Dank + Bezug auf **1–2 konkrete Gesprächspunkte** +
eine offene Frage elegant nachgeschoben + Ausblick auf den vereinbarten nächsten Schritt. Kurz (≤150 Wörter).
Mailtext in eine Datei schreiben, dann:
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.gmail_client draft \
  --to "interviewer@firma.de" --subject "…" --body-file ../data/tmp/danke.txt
```
**NIEMALS senden, nur Entwurf** — der Client kennt kein Senden; der Nutzer prüft und sendet selbst.
**Empfänger:** die echte Adresse NUR setzen, wenn sie in den Kontakten bekannt ist. Achtung: Gmail
verlangt mindestens einen Empfänger auch bei Entwürfen (getestet 09.07.2026) — ist keine Adresse bekannt,
als Platzhalter **die eigene Adresse des verbundenen Mail-Kontos** (selbst-adressiert; bei Gmail die
authentifizierte Adresse) eintragen und im Bericht darauf
hinweisen, dass der Nutzer sie vor dem Senden ersetzt (selbst-adressiert = versehentliches Senden harmlos).

### 7. Bericht an den Nutzer
Die fünf Leitfragen-Abschnitte aus Schritt 2 kompakt, plus: **Link auf den Transkript-Report**
(`report_path`), was in DB/Fragenbank/Gmail gelandet ist und der Hinweis, für Runde n+1 „Interview vorbereiten für Job <id>"
zu starten (liest Transkript + Fragenbank automatisch → Abschnitt „Aus Runde n offen").
Der Gmail-Entwurf-Schritt (6) läuft **auch headless** — `pipeline.gmail_client draft` braucht keinen
interaktiven Connector (Phase 8.3), kann aber nur Entwürfe, nie senden.

## Abgrenzung
- **Kein neues Briefing** — das ist `interview-vorbereiten` (danach für die Folgerunde empfehlen).
- **Keine Firmen-Analyse** — das ist `firma-pruefen`.
- **Nie E-Mails senden, nur Entwürfe.** Kontakte nur aus dem Transkript übernehmen, nichts spekulieren.
- Read-only gegenüber Gmail bleibt Standard (`email-check`) — dieser Skill schreibt ausschließlich EINEN Entwurf.
