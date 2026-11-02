# Bewerbungs-Management-System — Systemdokumentation

*Entwicklerdokumentation · lokale Web-App für die eigene Jobsuche · zuletzt nachgezogen am 29.10.2026*

> **Zur Einordnung.** Diese Datei ist die technische Dokumentation des Projekts. Sie nennt Bau-Specs (z. B. „P2-75“) und
> Phasen als Entstehungsgeschichte. Die Unterlagen dazu (`tasks/`) sind Arbeitsmaterial des Autors und gehören nicht zum
> öffentlichen Repository; die Beschreibung hier ist in sich vollständig. Maßgeblich ist immer der Code: Wo diese Datei und
> der Code sich widersprechen, gilt der Code.

---

## 1. Was ist das System?

Das Bewerbungs-Management-System (BMS) ist eine **lokale Web-App**, die die gesamte
Jobsuche einer Person an einem Ort bündelt: Stellen finden und bewerten, Firmen prüfen, Bewerbungsunterlagen
erzeugen, Interviews vorbereiten und nachbereiten, E-Mail-Antworten tracken, das Netzwerk pflegen
und aus allem lernen.

Es ist bewusst kein autonomer Bewerbungs-Roboter, sondern ein **Human-in-the-Loop**-Werkzeug:
Das System findet, bewertet und verwaltet — **der Nutzer entscheidet**. Kein Versand ohne Freigabe,
keine Bewerbung ohne Sichtung, keine erfundenen Fakten.

### Die zentrale Idee: Claude-in-the-Loop

Statt externer API-Keys und teurer Dienste ist die „Intelligenz" des Systems Claude selbst.
Sogenannte **Skills** (Suche, Scoring, Firmen-Prüfung, CV-Anpassung, Gmail-Auswertung …) werden
per Klartext-Satz ausgelöst und schreiben ihre Ergebnisse in **dieselbe zentrale Datenbank**, aus
der die Web-App liest. Es gibt zwei Betriebsarten:

- **Interaktiv** — Der Nutzer sagt in einer Claude-Session z. B. „Firma prüfen für Job <Nr>", Claude
  führt den Skill aus.
- **Headless** — die Web-App startet über den Agent-Runner denselben Skill als Hintergrund-Lauf
  (`claude -p "<Trigger-Satz>"`), z. B. per „▶ Ausführen"-Button an der Stelle.

Beide Wege nutzen exakt dieselben Skills und schreiben in dieselbe DB — es gibt keine zweite
Wahrheit.

### Zwei KI: Claude oder ChatGPT (P2-86)

Die Läufe gehen wahlweise über Claude Code (`claude -p`, Standard) oder über die Codex CLI von OpenAI
(`codex exec`, ChatGPT, im ersten Release eine Vorschau). Gewählt wird in `sucheinstellung.ki_anbieter`
(`claude` | `chatgpt`) über `GET/PATCH /api/einstellungen` und die Karte „KI“ der Einstellungen; die
Installationsanleitungen fragen sie in Schritt 0 ab. `GET /api/ki-status` meldet je Anbieter, ob das
Programm installiert und angemeldet ist, und liest nie einen Schlüssel. Queue, Ketten, Timeout und
Abbruch bleiben in `agent_runner` gemeinsam, `app/ki_anbieter.py` hält, was sich unterscheidet:

- **Aufruf und Umgebung:** `codex_argv` baut `codex exec --json` mit Sandbox `workspace-write`, Netz an
  und dem Prompt über die Standardeingabe. `codex_prompt` nennt den Skill ausdrücklich,
  `codex_umgebung` entfernt `OPENAI_API_KEY`, `CODEX_API_KEY` und die Claude-Variablen: Es gilt die
  Anmeldung des Rechners (`codex login`, das Abo), nie ein getrennt abgerechneter Schlüssel. Das
  Programm findet das BMS über `CODEX_BIN` oder den PATH.
- **Skills:** `.claude/skills` bleibt die einzige Quelle. `skills_spiegeln` kopiert sie vor jedem Lauf
  nach `.agents/skills` (nicht versioniert), dort sucht Codex. `AGENTS.md` im Projekt übersetzt die
  Werkzeugnamen der Skills (WebSearch, WebFetch, Read, Write, Edit, Task), die Skills selbst nennen
  weiter die von Claude Code.
- **Auswertung:** `CodexAuswertung` macht aus dem JSONL-Strom das Ergebnis, das der Runner von
  `claude -p` kennt. Ein erreichtes Abo-Limit und eine fehlende Anmeldung erkennt es am Fehlertext
  (`abo_limit`, `anmeldung`).
- **PDF:** LibreOffice bricht in der Sandbox von Codex ab. `codex_umgebung` setzt deshalb `BMS_PDF_UEBER_SERVER`, und
  `cv_export` lässt den Server außerhalb der Sandbox umwandeln (`POST /api/intern/pdf`, nur Word-Dateien aus Programm- und Datenordner).
- **Kosten:** Codex meldet keine Kosten in Dollar und Token erst am Ende des Turns. Unter ChatGPT bleibt
  `AgentTask.cost_usd` 0, der Verbrauch steht in `AgentTask.tokens`, und es gibt keine Budgetgrenze je
  Lauf. Schutz sind das Zeitlimit des Laufs, die Grenzen des Abos und die Tagesgrenze für Läufe.
- **Modelle:** Gespeichert bleiben die Stufen `opus`, `sonnet`, `haiku`, `CODEX_MODELL` ordnet ihnen die
  Codex-Modelle zu (§8 „KI-Modelle“). Fable bleibt nie wählbar.
- **Rechte:** Die Hooks und Freigaben aus `automation/agent_settings.json` und der Pfadwächter gelten nur
  für Claude Code. Unter ChatGPT begrenzt die Sandbox das Schreiben auf das Projekt, den Log-Ordner (dazu
  den Datenordner, wenn er außerhalb des Projekts liegt) und bei Mail-Läufen den Ordner der Zugangsdaten. Das Lesen lässt sie im ganzen Benutzerordner zu, auch unter
  `~/.bewerbung_mgmt_secrets`: Ein Lauf muss dorthin nicht, verhindert wird es aber nicht.

### Wegweiser durch die Dokumente

In der laufenden App zeigt der Menüpunkt **„📖 Dokumentation“** die Anwender-Dokumente in Reitern: Version
(`CHANGELOG.md`), Funktionen, Anleitung, Installation & Updates (die Datei des laufenden Systems:
`BMS_Install_Windows.md` unter Windows, sonst `BMS_Install_MAC.md`), E-Mail einrichten, Windows, Coach-Site
und Beirat. In einer Entwicklungsinstallation folgen nach dem Trenner „Intern“ Technik (diese Datei),
Automatik, Release und Entwickler-Installation. Welche Datei hinter welchem Reiter steht, legt der Katalog
in `backend/app/doku.py` fest; ins Anwenderpaket kommen nur die Anwender-Dokumente (`DOKU_ERLAUBT` in
`backend/pipeline/kundenpaket.py`). Sie verweisen deshalb nie auf interne Dateien und tragen keine
Phasen-Nummern (Wächter: `backend/tests/test_kundendoku.py`).

- **`docs/ANLEITUNG.md`** — Bedienung & tägliche Prozesse (was tun die Skills, was macht jeder Bereich der
  Oberfläche).
- **`docs/FUNKTIONEN.md`** — Kurzübersicht: was das BMS kann, nach Arbeitsschritten geordnet.
- **`docs/INSTALLATION.md`** — Entwickler-Installation von Null (Windows und macOS) und die Einrichtung der
  eigenen Person. Die Fassungen für Anwender (Sie-Form, von Claude geführt, mit Aktualisierung) sind
  `BMS_Install_MAC.md` und `BMS_Install_Windows.md` im Hauptordner.
- **`docs/DOKUMENTATION.md`** — diese Datei: Architektur, Datenmodell, Skills, Betrieb, Sicherheit.
- **`docs/AUTOMATION.md`** — Stand der (vorbereiteten, nicht aktiven) Zeitautomatik.
- **`docs/RELEASE.md`** — Versionen, Freigabe, Paketbau, Veröffentlichen.
- **`docs/BEIRAT-CHARTA.md`** / **`docs/BEIRAT-PERSONA-TEMPLATE.md`** — Regeln und Persona-Vorlage des
  Bewerbungs-Beirats.
- **`docs/SETUP-WINDOWS.md`** — Windows-Besonderheiten aus Anwendersicht: Start, Stopp, Update, bekannte
  Grenzen, Support-Matrix. Die Installation selbst steht in `BMS_Install_Windows.md`, der Entwicklerweg
  unter Windows in `docs/INSTALLATION.md` Teil 1.
- **`docs/SETUP-EMAIL.md`** — E-Mail-Konto einrichten (Weg A: IMAP mit App-Passwort, auch für Gmail; Weg B:
  Gmail-API mit eigenem Google-Cloud-Projekt). Strategie-Hintergrund: **`docs/GMAIL-STRATEGIE.md`**.
- **`docs/ANLEITUNG_COACH_SITE.md`** — Coach-Site einrichten, Schritt für Schritt und ohne Vorwissen
  (eigene Subdomain, SFTP, Coach-Login). Technischer Hintergrund und Betrieb: **`docs/COACH_SITE.md`**.
- **`docs/WAS_IST_NEU.md`** — Änderungsprotokoll der größeren Ausbauschritte, neueste zuerst.

**Jedes Dokument in `docs/` gibt es zweimal:** Die `.md` ist die Quelle, die gleichnamige `.html` wird
daraus erzeugt (druckbar, zum Weitergeben). Nach jeder Änderung an einer `.md` läuft
`scripts/docs_html.sh`. Ein Test (`backend/tests/test_docs_html.py`) prüft, dass zu jeder `.md` eine
passende, aktuelle `.html` gehört — wer das Erzeugen vergisst, sieht es an einer roten CI.

---

## 2. Architektur & Technik

| Schicht | Technik |
|---|---|
| **Backend** | FastAPI (Python) + SQLite — `data/bewerbung.sqlite` ist die **einzige Quelle der Wahrheit** (~9 MB, 27 Tabellen + FTS5-Suchindex) |
| **Frontend** | React + Vite + TypeScript + Tailwind; Status-Farben kanonisch aus dem Daube.Tech-Styleguide abgeleitet (`ui.tsx::STATUS_FARBEN`, Cyan→Navy-Leiter); Markenfarben, Schriften, Icon und Produktname kommen zur Laufzeit aus dem Design (`GET /api/design.css`, s. §8 „Design aus einer Quelle“); gebaut nach `frontend/dist`, vom Backend ausgeliefert |
| **Deterministische Logik** | 32 Pipeline-Module in `backend/pipeline/` (Ingest, Dedup, Mail [Gmail/IMAP], Export, Suche, Verifikation, LinkedIn-Import, Suchprofil-Writer, Report-Check, Coach-Site-Export …) — kein LLM, reproduzierbar |
| **Intelligenz** | 24 Skills in `.claude/skills/` (Claude-Format; für ChatGPT vor jedem Lauf nach `.agents/skills` gespiegelt, s. „Zwei KI“) |
| **API** | 137 REST-Endpunkte |

**Warum SQLite als einzige Quelle?** Alles — Stellen, Firmen, Bewerbungen, E-Mails, Kontakte,
Interviews, Transkripte, Budget, Agent-Läufe — lebt in einer Datei. Skills und Web-App teilen sie;
was ein Skill schreibt, erscheint sofort in der App. Keine Synchronisation, kein Server-Zoo.

### Starten

```
start.command              (Doppelklick — lokal, http://localhost:8000)
start_lan.command          (fürs Handy im selben WLAN — keine Auth, nur vertrautes Netz)
```

oder manuell:

```
cd backend && PORT=8000 ~/.bewerbung_mgmt_venv/bin/python run_server.py
```

### Umgebungs-Fallstricke (wichtig)

- **iCloud Drive (nur wenn das Projekt dort liegt):** Sandboxed-Prozesse (Claude-Code-Preview-Panel,
  launchd/cron ohne „Vollständiger Festplattenzugriff") können iCloud **nicht** lesen. Die App
  läuft dann nur über Terminal / `start.command`. Außerhalb von iCloud entfällt die Einschränkung.
- **Frontend-Build in iCloud:** Dort NIE `npm run build` direkt im Projekt — iCloud re-materialisiert
  `node_modules` und zerstört Symlinks. Stattdessen `frontend/build.sh` (baut außerhalb von iCloud unter
  `~/.bewerbung_mgmt_node/` und kopiert nur `dist` zurück). Liegt das Projekt nicht in iCloud, genügt
  `npm ci && npm run build` in `frontend/`.
- **venv** liegt außerhalb des Projekts unter `~/.bewerbung_mgmt_venv`.
- **PDF-Export:** LibreOffice headless (`soffice --headless --convert-to pdf`), nicht Word —
  deterministisch, kein Fenster, keine Automation-Freigabe.

### Projektstruktur und Ablageorte

Der Projektordner trennt den versionierten Code von den persönlichen Inhalten einer Installation.
Maßgeblich ist immer `.gitignore`, nicht der Ordnername.

- **Code, versioniert (Git):** `backend/` (FastAPI-App, Pipelines, DB-Layer), `frontend/` (React/Vite-Quelle),
  `.claude/` (Skills, Slash-Commands, Beirat-Subagenten), `docs/` (Anleitung, Systemdoku, Beirat-Charta),
  `assets/` (Report-Theme als CSS-Master, Logo/Icon), `scripts/` (Betriebs-Skripte), `automation/`
  (Vorlage `agent.env.example`, Guardrail-Konfiguration `agent_settings.json`), `.env.example`,
  `.gitignore`, die Startdateien (`start*.command`, `start_windows.bat`, …) und `README.md`.
- **Persönliche Inhalte, rein lokal (nie in Git):** `data/` (die SQLite-DB, Backups, Company-Fit-Dashboards,
  Digests, Transkripte, Beirat-Protokolle, Papierkorb …), `outputs/` (generierte CVs und Anschreiben als
  `.docx`/`.pdf`) sowie die persönlichen Dateien in `config/` (`profil.md`, `zielfirmen.md`,
  `suchprofile.yaml`, `budgets.yaml`). `config/` ist gemischt: `scoring_rubrik.md` (Bewertungsraster, mit
  einem Beispiel-Zielprofil) und `coach_export.yaml` sind versioniert, `profil_struktur.md` erzeugt die App
  selbst aus der Datenbank (beim Start, wenn sie fehlt, und bei jedem Speichern der Profil-Seite) und
  versioniert sie nicht, weil sie den Werdegang enthält.
- **Secrets, außerhalb des Projekts:** `agent.env` (Claude-OAuth-, Apify-Token; ChatGPT braucht sie nicht,
  die Anmeldung liegt bei Codex selbst), die Gmail-Tokens
  (`gmail_credentials.json`, `gmail_token.json`), die Mail-Konto-Einstellungen (`mail_settings.json`) und
  die Coach-Site-Konfiguration (`coach_settings.json` samt Coach-Zugangsdatei `coach_htpasswd`; die ältere
  `coach_sftp.env` bleibt als Rückfallweg liegen) liegen unter `~/.bewerbung_mgmt_secrets/` (Verzeichnis
  `chmod 700`, Dateien `chmod 600`; Override `BMS_SECRETS_DIR`), nicht unter `automation/`. Grund: Alles im
  Projektordner läge sonst bei Ablage in einem Sync-Ordner (z. B. iCloud) auf jedem Gerät desselben Kontos.
- **Task-Logs, außerhalb des Projekts:** Der rohe Ausgabestrom jedes Agent-Laufs (Runner-Prozess wie
  Beirats-Engine) — u. a. gelesene CV-Inhalte und Mail-Volltexte im Klartext — liegt unter
  `~/.bewerbung_mgmt_logs/` (Verzeichnis `chmod 700`, Dateien `chmod 600`; Override `BMS_LOG_DIR`).
  `AgentTask.log_path` ist seither ein BEZEICHNER, kein direkt verwendbarer Pfad;
  `agent_runner.resolve_log_path()` löst ihn auf (neuer Ort zuerst, alter projektrelativer Pfad als
  Fallback).
- **Git-Interna bei iCloud-Ablage:** Liegt das Projekt in iCloud Drive, kann das Git-Verzeichnis als
  `.git.nosync/` ausgelagert werden (`git init --separate-git-dir`; `.git` im Projektroot ist dann nur eine
  Zeiger-Datei), weil Git-Interna (Objekte, Refs, Locks) keinen Live-Sync vertragen. Außerhalb von iCloud ist
  das nicht nötig.

---

## 3. Grundprinzipien

Diese Prinzipien ziehen sich durch das ganze System und erklären viele Design-Entscheidungen:

1. **Human-in-the-Loop.** Nichts Unumkehrbares passiert ohne Freigabe des Nutzers. E-Mails werden
   **nie gesendet**, nur als Gmail-**Entwurf** angelegt. Keine automatischen Bewerbungen
   (Phase 15 „Auto-Bewerben" wurde bewusst verworfen).

2. **Anti-Halluzination.** Skills mit Rechercheanteil arbeiten belegt und wörtlich. „Liegt nicht
   vor" statt Raten. Entscheidungen, die das System nicht treffen darf (Termine, Zusagen), werden
   als `[BITTE PRÜFEN: …]`-Platzhalter markiert.

3. **Vier-Augen-Prinzip für Job-Treffer.** Jeder gefundene Job muss ein **Verifikations-Gate**
   passieren, bevor er in die DB darf: Ein mechanischer URL-Prüfer (`verify_jobs.py`) plus ein
   separater, adversarialer Prüf-Subagent bestätigen Existenz und Aktualität. Eine bloße
   Freitext-Warnung im Fundtext schützt nicht — nur ein Gate, das der Ingest erzwingt.
   Vertrauensmatrix: Apify-/Mail-Alert-/Nejo-URLs gelten als authentisch; WebSearch-konstruierte
   URLs brauchen eine kanonische Anzeige, sonst werden sie nicht ingestet.

4. **Dedup lebt von behaltenen Rows.** „Verworfen → Kein Match“ bleibt als Tombstone in der DB,
   damit derselbe Treffer (gleicher Link) nicht am nächsten Tag wieder als „Neu“ auftaucht. Gleiche
   Logik beim Löschen von Stellen (Soft-Delete, Phase 32). Seit P2-36 unterscheidet der Ingest:
   Dieselbe Anzeige (gleicher Link), jede weitere Anzeige zu einer noch laufenden Stelle und
   Treffer im Papierkorb bleiben gesperrt. Eine NEUE Anzeige derselben Stelle (Firma + Titel,
   Gender-Zusatz egal) zu einer Stelle im Endstatus erscheint dagegen wieder als „Neu“, mit Hinweis
   `NEUAUSSCHREIBUNG?`. Fall A: Eine Stelle „Head of Customer Success (m/w/d)“ war als Kein
   Match aussortiert, die neue Anzeige „(m/f/d)“ kam zwei Wochen später und führte zu einer
   Bewerbung. Eine reine Sperre hätte sie still verworfen. Seit P2-39 wird für den Abgleich
   zusätzlich der Firmenname bereinigt (Rechtsform-/Regionszusätze wie GmbH/SE/Deutschland/EMEA
   entfernt), damit zwei Schreibweisen derselben Firma nicht an zwei verschiedenen Firmen-Rows
   vorbeilaufen (Messung an einem Echtbestand, 12.09.2026: 15 Firmen-Gruppen fallen zusammen, 5 echte
   Stellen-Paare kommen dadurch neu zusammen, 0 Fehlalarme). Fall B: Zwei Schreibweisen derselben Firma
   („Beispiel“ und „Beispiel GmbH“) — drei Stellen hingen an zwei Firmen-Rows für denselben Arbeitgeber,
   jede Dublettenstufe verfehlte den Treffer, bis die Firmen-Schreibweise selbst bereinigt wurde.

5. **Budget-Leitplanken.** Echtes Geld (Apify) hat harte Tageslimits ($0,50/Tag,
   `BudgetLimit`-Tabelle). Der headless Claude-Runner läuft aufs Max-Abo (virtuelles Geld),
   hat aber Ausreißer-Bremsen (Pro-Lauf-Deckel, Tasks/Tag). Unter ChatGPT gibt es keine Kosten in Dollar
   und keinen Deckel je Lauf (Codex meldet Token erst am Ende des Turns), die Bremsen sind Zeitlimit,
   Abo-Grenze und Tasks/Tag.

6. **Abgeleitete Sichten statt Write-Trigger.** Excel-Export, Tages-Digest, Volltext-Suchindex und
   seit Phase 81 der Coach-Site-Export sind komplett neu baubar (`refresh_views.sh` bzw.
   `coach_site.sh`), nicht an zehn Schreibstellen verteilt. Ihr Baustand ist sichtbar (Staleness
   wird gezeigt, nicht versteckt). Der Excel-Export selbst bildet inzwischen zusätzlich den
   0–100-CV-Match-Score, den Aussortier-Grund (aus „Notizen & Verlauf" statt einer leeren Spalte) und
   die Beirats-Bewertung als gefärbte Zahl ab (Phase 75). Seit P2-81 zeigt das Blatt „Bewerbungen"
   je beworbener Stelle Funddatum, Bewerbungsdatum, das Datum jeder Gesprächsrunde 1–6
   (`interview.scheduled_at`, ersatzweise `transcript.recorded_at`) und das Absagedatum (früheste
   Absage-Mail, ersatzweise der Statuswechsel im Verlauf, als lokaler Kalendertag).

7. **Ein Aktivitäts-Log für alles.** Jede Hintergrund-Aktivität — Runner-Skill wie
   In-Server-Engine (Beirat) — schreibt ihre `AgentTask`-Row selbst (Status, Log, Dauer,
   Kosten). Das Task-Center liest nur diese Tabelle und zeigt damit automatisch ALLES;
   keine Parallel-Buchführung (Phase 42).

8. **Nur für die bewerbende Person.** Das BMS unterstützt ausschließlich die Seite, die sich
   bewirbt. Funktionen, mit denen Arbeitgeber Bewerbende bewerten, sortieren oder auswählen, kommen
   nicht hinein: Sie fielen unter die Hochrisiko-Regeln der KI-Verordnung (AI Act, Anhang III
   Nr. 4). Aus der früheren Vertriebs-Checkliste übernommen, als sie am 29.10.2026 entfiel.

---

## 4. Datenmodell

27 SQLModel-Tabellen in `backend/app/models.py`, plus ein FTS5-Volltext-Suchindex. Kernbeziehung:

```
Company 1─* Job 1─* Application 1─* Email
Company/Job 1─* Contact
Job 1─* CVVersion · Interview · Transcript · JobFile · JobLog · JobChat
```

Ein Muster zieht sich durch: „unsaubere" Realwerte (Status, Situation, Seniorität) werden
**doppelt** gespeichert — ein normalisiertes Feld zum Filtern/Auswerten plus ein `*_raw`-Feld,
das den Originaltext bewahrt.

### Die wichtigsten Tabellen

| Tabelle | Zweck | Kernfelder |
|---|---|---|
| **Company** | Firma | `situation` (BUILD/CARVE-OUT/PE/…), `fit_analysis_path`, `fit_ampel` (grün/gelb/rot), `is_radar` |
| **Job** | Stelle | `match_score` (1–5 = **Zielstellen-Fit**, Bewertungsraster `config/scoring_rubrik.md`; nicht zu verwechseln mit `CVVersion.match_score100`), `gut_feeling` (1–5), `status`, `follow_up_date`, `verify_note` (Vier-Augen-Befund + Quellen-Konflikte), `posting_snapshot_path`, `dedup_key`, `career_url`/`portal_closed` (Karriereseiten-Fallback, Phase 73), `availability_status`/`availability_checked_at` (Beworben-Check, Phase 74) |
| **Application** | Bewerbung | `channel`, `cover_letter_path` (+PDF), `status`, `rejection_reason` |
| **Email** | Postfach-Eintrag | `direction`, `category` (Einladung/Absage/…), `response_time_hours`, `needs_reply`, `reply_draft_at` |
| **Contact** | Ansprechpartner | `role` (Recruiter/Hiring Manager), `email`, `linkedin_url` |
| **CVVersion** | angepasster CV | `language`, `file_path` (docx) + `pdf_path`, `ats_score`, `match_score100`, `match_dashboard_path`, `ats_scan_path` |
| **Interview** | Gespräch | `runde`, `art` (HR-Screen/Fachgespräch/…), `scheduled_at`, `status`, `prep_path` (Briefing) |
| **NetzwerkGespraech** *(Phase 69)* | Gespräch ohne Stelle | Pendant zu `Interview` ohne `job_id`-Pflicht — Netzwerk-/Headhunter-Calls ohne Ausschreibung; `gegenueber` zusätzlich `"Netzwerk"` |
| **Transcript** | Mitschrift | `file_path`, `summary`, `todos_json`, `report_path` (Transkript-Report), `debrief_path` (Altbestand) |
| **JobFile** | angehängte Datei | generisch (Transkript/Stellenbeschreibung/Präsentation), verknüpft optional eine Transcript-Row |
| **JobLog / JobChat** | Verlauf & KI-Chat je Stelle | chronologische Notizen (auto/manuell/ki-chat); Frage-Antwort-Verlauf |
| **Outreach / OutreachLog** | Networking-Tracker | einmal aus einer Excel-Liste übernommen (frühere Einmal-Migration, das Werkzeug ist entfernt), seitdem in der App gepflegt, kein Anlegen-Endpunkt; Aktivitäten-Log |
| **TargetCompany / Headhunter / NetworkContact** | die drei Netzwerk-Listen | `karriere_url`, `last_career_check` (Sweep-Rotation), `deleted_at` (Soft-Delete) |
| **AgentTask** | headless Agent-Lauf | `kind`, `status`, `cost_usd`, `duration_s`, Ketten-Felder (`chain_id`, `depends_on`) |
| **ApiCost / BudgetLimit** | Budget | Kosten je Dienst & Tag; editierbare Limits (hart/weich) |
| **AlertMail** | Job-Alert-Verarbeitung | garantiert Einmal-Verarbeitung (`gmail_message_id` unique) |
| **Run** | Lauf-Protokoll | je Jobsuche/Email-Check: gefunden/neu, Antwortzeiten |
| **Profile** *(Phase 45)* | Kandidaten-Profil (Singleton id=1) | `linkedin_url`, `headline`, `standort`, `positionierung`, `linkedin_eingelesen_am` |
| **ProfileSkill** *(45)* | Skill-Chip | `bereich` (Themenkategorie), `name`, `note`, `quelle` (manuell/linkedin) |
| **CareerEntry** *(45)* | Werdegang | `art` (Beruf/Ausbildung/Zertifizierung/…), `firma`, `rolle`, `von`/`bis`, `beschreibung` |
| **ProfileFile** *(45)* | Zeugnis/Zertifikat | `kind`, `file_path` (`data/profil/dateien/`), `mime`, `size_bytes` |
| **SuchEinstellung** *(49/50)* | Sucheinstellungen (Singleton id=1) | `min_mitarbeiter`, `suchbereich_json`, `plaene_json` (Pläne A/B/C), `modelle_json` (KI-Modell je Funktion) |

---

## 5. Der Bewerbungs-Workflow

Eine Stelle wandert durch feste Status (Kanban auf der Pipeline-Seite):

```
Neu → Prüfen → Beworben → Interview → Angebot → (Zusage / Absage)
                                          ↘ Kein Match / Beirat abgelehnt / Nicht verfügbar / Geparkt
```

### Der tägliche Ablauf (Tageslauf)

Der **Tageslauf** ist der Morgenlauf und orchestriert seriell:

1. **Jobsuche** (WebSearch + Nejo + Arbeitsagentur, optional Apify) — drei Läufe nach Bucket (Remote ·
   Deutschlandweit · Stadt +Umkreis), neue Treffer nach Vier-Augen als „Neu"
2. **Mail-Jobsuche** — Job-Alert-Mails aus dem Postfach zu Stellen verarbeiten
3. **Zielfirmen-Sweep** — rotierend 12 Karriereseiten prüfen
4. **Headhunter-Suche** — rotierend 15 Headhunter-Seiten prüfen (eigener Agent)
5. **Beworben-Check** *(Phase 74)* — wöchentliche Verfügbarkeitsprüfung aller laufenden Bewerbungen
   (Beworben/Interview): zuerst die Original-URL, bei geschlossenem Portal die Karriereseite
   (Phase-73-Mechanik); ein eigener 7-Tage-Vorab-Check spart den Lauf im Regelfall. Schreibt nur
   Verfügbarkeitsstatus + Prüfdatum — **ändert nie den Bewerbungsstatus selbst**
6. **Email-Check** — Postfach der letzten 24–36 h, Antworten Bewerbungen zuordnen
7. **Ansichten-Refresh** — Excel-Export, Tages-Digest, Volltext-Suchindex neu bauen
8. **Budget-Sync**

Die headless/automatische Kette hinter dem Tageslauf (`agent_runner.RECIPES["tageslauf"]`) setzt
nach dem Email-Check einmal je Kalenderwoche die **Absagen-Analyse** ein *(P2-79; Vorprüfung ohne
Modellstart, ein Fehlschlag hält die Kette nicht auf, s. `docs/AUTOMATION.md`)* und hängt
zusätzlich **Coach-Site aktualisieren** *(Phase 81/82)* als letztes, bewusst nicht-fatales Glied an
— ohne vollständige Konfiguration oder bei abgeschaltetem Schalter endet der Schritt grün (Exit 0),
ein echter Fehler danach markiert nur diesen einen Task, der Rest der Kette bleibt unberührt.

Ergebnis: eine kompakte Morgen-Zusammenfassung (Top-Treffer, Rotationsstände, Beworben-Check,
Gmail, offene/überfällige Aktionen).

### Pro Stelle: das Bewerbungspaket — Pflichtkern und optionale Bausteine

*(P2-41, 15.09.2026 — vorher „Vier-Schritt-Vorbereitung“: der Beiratscheck war Schritt 2 mit
Schloss vor `cv-match`, das Anschreiben immer der letzte Kettenschritt. Beides ist jetzt
optional, ohne Schloss, und läuft unabhängig vom Pflichtkern.)*

**Pflichtkern** (sequenziell, echte Datenabhängigkeit — Company-Fit als Kontext für den Match,
der Entwurf aus `cv-match` als Grundlage für `cv-erstellen`):

1. **Schritt 1 — `firma-pruefen`**: Company-Fit-Dashboard (Geschäftsmodell, Markt, KI-Disruption,
   Rolleneinfluss, Arbeitgeber-Realität) + wörtlicher Stellenausschreibungs-Snapshot. Beide Layouts
   werden deterministisch aus Code gerendert (`pipeline/company_fit.py`/`pipeline/posting_snapshot.py`
   ::`render_full()`, Phase 79) — das Modell liefert nur noch Inhalte, nie HTML, damit das Layout
   nicht mehr über Läufe hinweg driftet. Bei geschlossener Portal-Stelle ermittelt der Schritt
   automatisch die Firmen-Karriereseite (Phase 73).
2. **Schritt 2 — `cv-match` → `cv-erstellen`**: Match-Dashboard mit gewichteter
   Anforderungs-Tabelle + angepasster CV-**Entwurf** (DE/EN), direkt am Job-Detail bearbeitbar.
   Baut bei JEDEM Lauf neu aus der aktuellen Basis-CV-Datei auf (Phase 78 — eine frühere „bereits
   erledigt“-Abkürzung konnte einen Entwurf auf veralteter Struktur stehen lassen). Danach Button
   **„CV erstellen“** (`cv-erstellen`) → Word + PDF + ATS-Scan aus dem (ggf. editierten) Entwurf.
   Wartet nur noch auf Company-Fit (Schritt 1) — nicht mehr auf den Beirat.

**Optionale Bausteine** — eigener Marker (○ offen / ✓ erledigt), **kein Schloss**, weder für sich
noch für einen anderen Schritt:

- **Stelle prüfen (Beirat)** (Phase 40): der 7-köpfige Bewerbungs-Beirat prüft Stellenbeschreibung
  + CV nach dem Charta-Verfahren — moderierte Live-Debatte (3–5 Köpfe, im Job-Detail per SSE
  mitzuverfolgen) + Abstimmung aller 7 (6 gewichtete Prüfbereiche), Entscheidung deterministisch
  gerechnet → HTML-Dashboard mit Ampel (🟢 Bewerben / 🟡 Bedingt / 🔴 Nicht bewerben), registriert
  unter „Dateien & Dokumente“. Bei 🔴 bietet die Karte den Ein-Klick-Status „Beirat abgelehnt“ an
  (Phase 41) — entscheiden tut der Nutzer. Bleibt an seiner logischen Position (Triage VOR dem
  CV-Aufwand), läuft aber weiterhin in-server über `beirat_engine.py`, NICHT als Kettenglied des
  Runners — Stufe 1 der P2-41-Entscheidung, eine Verkettung ist nicht gebaut.
- **`anschreiben-erstellen`**: wahrheitstreues Anschreiben mit Direktansprache. Nutzt den
  angepassten CV, sobald der Pflichtkern durchgelaufen ist — ohne fertigen CV fällt der Skill auf
  den Basis-CV zurück, ohne Company-Fit auf Anzeige + eigene Recherche.

**Bewerbungspaket** (`agent_runner.RECIPES["bewerbungspaket"]`): EIN Button startet den
Pflichtkern; ein Häkchen „mit Anschreiben“ hängt den optionalen Baustein an die Kette an
(Vorbelegung aus der Einstellungen-Karte „Bewerbungspaket — Standardumfang“, ab Werk aus). Das
frühere Rezept `deepdive` entfällt ersatzlos — inhaltlich deckungsgleich mit dem Bewerbungspaket
ohne Anschreiben.

`job-deepdive` (interaktiver Skill, nicht zu verwechseln mit dem entfallenen Rezept) macht
Company-Fit + CV in einem Rutsch. Danach optional: `entscheider-recherche`,
`interview-vorbereiten`.

---

## 6. Die Skills (die „Intelligenz")

24 Skills, gruppiert nach Workflow-Phase. Auslösung per Klartext-Satz (interaktiv) oder Button
(headless, wo markiert).

### Suche — neue Stellen finden (→ Status „Neu")

- **jobsuche** — „such nach neuen Stellen" · WebSearch (Standard) + Nejo + Arbeitsagentur (deutsche Titel-Synonyme) + optional Apify,
  ein Lauf je Bucket, harte Grenzen (u. a. nur Firmen mit 100+ Mitarbeitern, Beleg-Regel),
  Zielstellen-Fit 1–5, Vier-Augen, Ingest. *Headless-fähig.*
- **mail-jobsuche** — „Mail-Jobsuche" · Job-Alert-Mails aus Gmail → mehrere Postings je Digest,
  Dedup gegen Jobsuche. *Headless-fähig.*
- **zielfirmen-sweep** — „Zielfirmen-Sweep" · rotierend 12 Karriereseiten der ~68 Zielfirmen.
- **headhunter-suche** — „Headhunter-Suche" · rotierend 15 Headhunter-Seiten; vertrauliche
  Mandate als `[vertraulich] <Headhunter>`. *Eigener Agent.*

**Harte Grenzen und Score (P2-74).** Für alle vier Suchläufe gilt dieselbe Regel, sie steht in
`config/scoring_rubrik.md`: Eine harte Grenze greift nur mit Beleg aus Anzeige, Mail oder
Suchergebnis, nie auf eine Annahme hin. Hybrid außerhalb des Umkreises ist kein Umzug und gehört
in den Bucket „Deutschlandweit“. Der Score sortiert, er sortiert nicht aus: Was die Grenzen
besteht, wird mit seinem Score angelegt, auch mit 1 oder 2. Der Abschlussbericht nennt je
aussortierter Stelle Grenze und Beleg. Bei `mail-jobsuche` steht der Kern der Regel zusätzlich in
der Auftragsvorlage des Runners (`agent_runner.PROMPTS`), weil dort der Einbruch gemessen wurde:
Nach einem Modellwechsel erreichten nur noch 10 % statt 44 % der extrahierten Postings den Ingest.

### Bewerbung vorbereiten (pro Stelle)

- **firma-pruefen** *(Schritt 1)* — Company-Fit-Dashboard + Anzeigen-Snapshot (beide deterministisch
  aus Code gerendert, Phase 79/Design-Review — das Modell liefert nur Inhalte) → `data/company_fit/`,
  `data/job_postings/`. Bei geschlossener Portal-Stelle: automatischer Karriereseiten-Fallback
  (`career_url`/`portal_closed`, Phase 73).
- **cv-match** *(Schritt 2a)* — Match-Dashboard + angepasster CV-Entwurf (bearbeitbar), baut jeden
  Lauf neu aus der Basis-CV auf statt einen Alt-Entwurf wiederzuverwenden (Phase 78) →
  `outputs/cv/`.
- **cv-erstellen** *(Schritt 2b)* — aus dem (ggf. editierten) Entwurf: Word/PDF + ATS-Scan.
  Seit P2-45 ist der Entwurf auch NACH dem Erstellen editierbar: Textfenster aufklappen, ändern,
  speichern, „CV neu erstellen" — derselbe Datensatz, dieselbe Datei, Word/PDF/ATS entstehen neu.
  Der Seitenumbruch-Schutz setzt seine „keep"-Eigenschaften bei jedem Lauf neu (P2-47) — sonst
  sammelten sich über mehrere Läufe Flags an, bis eine ganze Station als unteilbarer Block auf die
  Folgeseite rutschte
  (Methodik v2, Phase 55: Score = Optimierungsgrad über EINE in `cv-match` erzeugte
  15-Keyword-Liste, Roh-Quote separat sichtbar, einmalige Feedback-Schleife) → `outputs/cv/`.
  Basis-CVs sind Workday-/ATS-Parser-kompatibel strukturiert (Titel direkt vor der Firmenzeile,
  Phase 76 — vorher las „Autofill with Resume" Titel und Station um eine Station verschoben).
- **job-deepdive** — beides zusammen. *Claude-in-the-Loop.*
- **entscheider-recherche** — echte Fachentscheider (VP/Head/C-Level) + Vorbesetzung, nur
  öffentliche Quellen → `Contact`-Rows.
- **anschreiben-erstellen** — wahrheitstreues, firmenspezifisches Anschreiben mit Direktansprache
  (DE/EN, docx + PDF) → `outputs/anschreiben/`, Application-Status „Vorbereitet".
- **initiativ-bewerbung** — Hidden Job Market: Netzwerk-Check → Initiativ-Stelle anlegen →
  Entscheider → warme/Headhunter/kalte Route.

**Anzeigentext sichern (P2-75).** Anlass: Eine Stelle aus einer Job-Mail bekam beim Erfassen von
LinkedIn HTTP 429 („zu viele Anfragen"). Der Basis-Snapshot blieb ohne Anzeigentext
(Befund `QUELLE_VERTRAUT`), Firma-Prüfung, CV-Match und CV erstellen liefen trotzdem durch und
kannten die Anforderungen der Stelle nicht. Gemessen wurde eine Drosselung je Anfrage, keine Sperre
(3 von 12, 3 von 11 und 9 von 18 LinkedIn-Abrufen in den letzten Mail-Jobsuchen, verstreut über den
Lauf). Das Gegenmittel hat drei Teile; der Snapshot bleibt der eine Ort für den Anzeigentext, es
entsteht kein zweiter Gliederungsweg. Spec: P2-75.

- **Wiederholen (`pipeline/verify_jobs.py`).** `check_url()` wiederholt nur bei HTTP 429, mit den
  Pausen `_PAUSEN_429 = (3, 8, 20)` Sekunden; ein `Retry-After` als ganze Sekunden bis 30 ersetzt
  die jeweilige Pause. Bleibt es nach dem vierten Versuch bei 429, ist der Befund wie bisher
  `NICHT_PRUEFBAR` (Beleg „HTTP 429 nach 4 Versuchen (Rate-Limit)"). 403 (Bot-Block), Login-Wall,
  404/410 und Abgelaufen-Marker werden nicht wiederholt, dort hilft Warten nicht. Das Ergebnis trägt
  `versuche`; `wiederholen=False` ergibt das frühere Verhalten mit genau einem Versuch. Die Pausen
  laufen über die Modulfunktion `_schlafen`, damit Tests sie ersetzen können. Die Stapel
  (`check`, `bestand`) holen erst alle Adressen und wiederholen nur die geblockten in bis zu drei
  weiteren **Runden** nach den Pausen `_RUNDEN_PAUSEN = (5, 10, 20)`; die Pausen je Lauf bleiben
  so bei höchstens 35 s (Messung am 14.10.2026 mit 24 Adressen: 9 → 2 → 0 geblockt in 58 s). Die
  Zusammenfassung nennt `wiederholt` und `rate_limit_offen`. Die vier Such-Skills rufen
  `verify_jobs check` deshalb mit einem Zeitlimit von 300000 ms auf.
- **Nachholen (`pipeline/posting_snapshot.py`).** `hat_anzeigentext(job)` ist eine reine
  Lesefunktion: wahr, wenn der Snapshot Text trägt (Basis-Karte, Block „Volltext (unbereinigt)",
  Volltext-Kandidaten älterer Snapshots oder eine grün gegliederte Fassung). `anzeigentext_sichern(job_id)`
  liefert `vorhanden` (kein Netzabruf), `nachgeholt` oder `fehlt` mit einem Grund in Klartext.
  Ersetzt wird der Snapshot nur bei Befund `OK` mit Text (`render_basis(job, text, hinweis=…)`, an
  Ort und Stelle, dazu ein `JobLog` der Art `auto`); jeder andere Befund lässt die Datei
  bytegleich. Eine Stelle ohne Snapshot bekommt auf demselben Weg ihren ersten. Gegliedert wird der
  Text erst bei der nächsten Firma-Prüfung. Für den Bestand gibt es
  `python -m pipeline.posting_snapshot nachholen [--job-id N | --status CSV] [--dry-run]` neben
  `backfill` (der nur Stellen ganz ohne Snapshot anlegt); mit `--job-id` ist der Exit-Code 3, wenn
  der Text fehlt.
- **Halt beim Start (`app/main.py`).** Die Konstante `ANZEIGE_KINDS` (`firma-pruefen`, `cv-match`,
  `cv-erstellen`, `anschreiben-erstellen`) ist bewusst dieselbe Menge wie `LOW_MATCH_KINDS`, aber
  eine eigene Konstante. `_guard_anzeigentext()` läuft in `create_task()` direkt nach
  `_guard_low_match()` mit derselben aufgelösten Schrittmenge, gilt also für Einzel-Tasks, Ketten
  und „Erneut". Er ruft `anzeigentext_sichern` über `run_in_threadpool` auf, weil der Abruf mit
  Pausen gut 30 s dauern kann und sonst den ganzen Server anhielte. Bei `fehlt` antwortet er mit
  409 und dem Marker `ANZEIGE_FEHLT`; die Bestätigung ist `params.ohne_anzeigentext_ok=true`
  (Muster `LOW_MATCH`, kein Claude-Lauf und keine Kosten vor der Entscheidung).
  `AgentTaskButton` zeigt die Rückfrage inline mit „Trotzdem starten" und „Abbrechen"; bestätigte
  Overrides sammeln sich, wer `LOW_MATCH` und `ANZEIGE_FEHLT` nacheinander bestätigt, startet mit
  beiden. Dass Firma-Prüfung ebenfalls anhält, ist eine Entscheidung vom 14.10.2026: Ohne Anzeige
  bewertete sie die Rolle blind.
- **Skills lesen den Snapshot zuerst.** `firma-pruefen` (Schritt 3b), `cv-match` (Schritt 1),
  `cv-erstellen` und `anschreiben-erstellen` nehmen den Anzeigentext aus `job.posting_snapshot_path`.
  Fehlt er trotz Server-Nachholen, rufen sie einmal `nachholen --job-id` auf. WebFetch auf
  `job.url` ist nur noch Teilquelle (Badge amber). Ohne Anzeigentext gibt es kein grünes Badge;
  läuft `cv-match` nach der Bestätigung ohne Text, steht das als Red Flag im Dashboard und im
  Abschlussbericht. Die Firmen-Recherche per WebSearch/WebFetch und die Prüfung „Portal
  geschlossen?" bleiben unverändert.

Nicht Teil von P2-75: ein Knopf „Anzeige erneut abrufen" im Job-Detail (jeder Unterlagen-Lauf holt
ohnehin nach, den Bestand erledigt `nachholen`), die Erkennung einer Personalberatung als
ausschreibende Firma (eigenes Thema) und eine automatische Neuerzeugung bestehender
Company-Fit-Dashboards (eine neue Firma-Prüfung holt Gliederung und Bewertung nach).

**Portal-Status (P2-76).** Anlass: `firma-pruefen` und `beworben-check` luden `job.url` per WebFetch und
suchten im Text nach Markern; bei LinkedIn-HTTP-429 blieb der Status ungeprüft. Außerdem las
`check_url()` die Zeitüberschreitung bei StepStone (Verbindung steht, dann keine Antwort) als `TOT`,
obwohl die Anzeigen leben. Seit P2-76 kommt der Portal-Status aus demselben Abruf mit Wiederholung
wie bei den Suchläufen. Spec: P2-76.

- **Marker (`pipeline/verify_jobs.py`).** `BESETZT_TEXT_MARKERS` kennt zusätzlich „keine bewerbungen
  mehr angenommen“ (LinkedIn auf deutschen Seiten) und „nimmt keine bewerbungen mehr entgegen“. Die
  Marker stehen nur im Code; die Skills werten das Ergebnis aus.
- **Ausnahme-Regel.** `httpx.ReadTimeout` und `httpx.RemoteProtocolError` (das Portal nimmt die
  Verbindung an, antwortet aber nicht oder schließt sie ohne Antwort) ergeben `NICHT_PRUEFBAR` mit
  einem Beleg, der den Bot-Schutz benennt, nicht mehr `TOT`. Gescheiterter Verbindungsaufbau
  (`ConnectError`, `ConnectTimeout`) und die übrigen Zeitüberschreitungen bleiben `TOT`. Bot-Schutz
  wird nicht umgangen, das Portal wird ehrlich als blockierend gemeldet. Folge: Ein StepStone-Treffer
  aus Mail-Alert oder Apify wird in der Vier-Augen-Prüfung nicht mehr abgelehnt, und
  `anzeigentext_sichern` nennt „Das Portal blockiert automatische Abrufe.“
- **Text bei geschlossenem Portal.** Zeigt eine Seite einen Text-Marker und sind Titel (ab 60 %) und
  Firma der Stelle noch zu lesen, trägt das Ergebnis den Anzeigentext mit. Der Befund bleibt
  `ABGELAUFEN`. `anzeigentext_sichern` nimmt diesen Text an (Status `nachgeholt`, Hinweis „Das Portal
  nimmt laut Abruf keine Bewerbungen mehr an“). Bei Umleitung auf eine Abgelaufen-Seite gibt es nie Text.
- **`portal_status()` und CLI `portal`.** `portal_status(pr)` ist eine reine Funktion: `OK` ergibt
  `offen`; `ABGELAUFEN`, `UMGELEITET_GENERISCH` und `TOT` mit HTTP 404/410 ergeben `geschlossen`;
  alles andere (`NICHT_PRUEFBAR`, `LOGIN_WALL`, `INHALT_UNKLAR`, `TOT` ohne Status, `KEINE_URL`)
  ergibt `unklar`. `python -m pipeline.verify_jobs portal <job_id> [<job_id> …]` lädt die Stellen
  nur lesend aus der Datenbank, ruft sie über die Runden-Wiederholung von P2-75 ab und gibt eine
  JSON-Liste aus (`job_id`, `url`, `portal`, `befund`, `beleg`, `http_status`, `versuche`). Eine
  unbekannte oder gelöschte ID ergibt `befund` `UNBEKANNT` ohne Abruf. Der Befehl schreibt weder
  Datenbank noch Dateien.
- **Skills.** `firma-pruefen` ruft im Pflichtschritt „Portal geschlossen?“ einmal `portal <id>` auf,
  `beworben-check` (Schritt 3) einmal `portal` für die ganze Prüfmenge. `geschlossen` führt in den
  bisherigen Karriereseiten-Fallback (`portal_closed`, `verify_note`), `offen` beendet die Prüfung;
  nur bei `unklar` folgt wie bisher WebFetch auf `job.url` (höchstens zwei je Stelle). Das
  Rückschreiben von `portal_closed` und `availability_status` bleibt bei den Skills.

### Interview

- **interview-vorbereiten** — Call-Briefing (erwartbare Fragen mit STAR aus echtem CV, Rückfragen
  an die Firma, Konflikt-Scan, Einwand-Handling, Spickzettel) → `data/interview_prep/`.
  *Claude-in-the-Loop.*
- **gespraech-debrief** — Transkript auswerten (Leitfragen, Signale, Red Flags), Interviewer als
  Kontakte, Fragenbank pflegen, Danke-Mail als Gmail-**Entwurf**. *Headless-fähig.*

### Nachfassen / Kommunikation — immer nur Gmail-ENTWURF, nie senden

- **mail-antwort** — faktentreue Antwort auf eine eingegangene Mail, `[BITTE PRÜFEN]`-Platzhalter,
  Entwurf im Original-Thread.
- **nachfass-mail** — Modus A (Funkstille → Statusanfrage mit Wert-Anker) / Modus B (Absage →
  Feedback erbitten, füllt `rejection_reason`).

### Analyse / Entscheidung

- **absagen-analyse** — Lost-Order-Auswertung (was haben Absagen gemeinsam, Screening vs. Gespräch);
  pflegt die Empirie-Sektion in `config/profil.md` (fließt zurück ins Scoring/CV-Tailoring).
  Seit P2-79 einmal je Kalenderwoche im Tageslauf und per Button auf dem Dashboard. Die Empirie-Sektion
  ersetzt nur ein Start von Hand; der Wochenlauf (`chain_id` gesetzt) schreibt seinen Vorschlag als
  eigene Karte in den Bericht und lässt das Profil unverändert (Entscheidung vom 16.10.2026).
- **angebot-vergleich** — bei Status „Angebot": gewichtete Benefits-Punkteliste, rote Linien = K.o.,
  Matrix.
- **job-frage** — „Frage zu Job <id>: …" · Antwort **nur** aus lokalen Job-Daten (kein Web), in
  Job-Chat + Verlauf. *Headless.*

### Betrieb / Orchestrierung

- **email-check** — täglicher Scan des Postfachs (Gmail oder IMAP, je Installation konfigurierbar,
  Phase 71F), Zuordnung, Antwortzeiten, Kontakte; relevante Mails landen auch OHNE zuordenbare
  Stelle in der Inbox („Ohne Stelle“). Eine als „Eingangsbestätigung“ gemeldete Mail, die später
  als 7 Tage nach der Bewerbung kommt, prüft der Ingest selbst am Volltext und stuft sie auf
  „Absage“ herauf, wenn dort eine eindeutige Absage-Formulierung steht (P2-48, Eintrag im Verlauf
  der Stelle). Passen mehrere Stellen, bleibt die Mail ohne Stelle —
  Ausnahme seit P2-43: sind alle Kandidaten Zwillinge derselben Rolle (Dubletten, Titel ohne
  Gender-Zusatz gleich), trägt die eine noch laufende Bewerbung (Beworben/Interview/Angebot)
  die Mail. Neben der Stichwort-Suche sucht Schritt 1b nach bekannten Adressen und Domains; die
  Listen liefert seit P2-80 `pipeline/mail_suchlisten.py` (vorher ein Schnipsel im Skill): Kontakt-
  Adressen, Domains der Berater-Kontakte und der laufenden Bewerbungen (Beworben/Interview/Angebot,
  aus Mails an der Stelle und Kontaktadressen), gefiltert gegen ATS, Freemail und große Jobportale.
  Der Ingest trägt die Adresse an einem gleichnamigen Kontakt derselben Firma ohne Adresse nach,
  statt eine Dublette anzulegen (P2-80). *Headless-fähig, read-only.*
- **beworben-check** *(Phase 74)* — wöchentliche Verfügbarkeitsprüfung aller laufenden Bewerbungen
  (Beworben/Interview): erst die Original-URL, bei geschlossenem Portal die Karriereseite
  (Phase-73-Mechanik); schreibt Verfügbarkeitsstatus + Prüfdatum, ändert nie den Bewerbungsstatus
  selbst. *Headless-fähig.*
- **tageslauf** — der Morgenlauf (orchestriert Jobsuche + Sweeps + Beworben-Check + Email-Check +
  Refresh). *Claude-in-the-Loop.*
- **outreach-drive-upload** — Outreach-Tracker format-getreu nach Google Drive (praktisch:
  App-Button erzeugt die Datei, der Nutzer legt sie manuell in Drive ab).

### Profil (Phase 45/47)

- **profil-einlesen** — „Profil einlesen aus dem hinterlegten Text" · strukturiert den eingefügten
  Profiltext oder den Text des Profil-PDFs zu einem Vorschlag, den der Nutzer vor dem additiven Speichern
  prüft (`pipeline/linkedin_text.py`). Kein Web: LinkedIn sperrt automatische Abrufe (HTTP 999). Der
  vollständigste Weg bleibt das Datenexport-ZIP
  (`pipeline/linkedin_import.py`, deterministisch, kein LLM). *Headless.*
- **skills-sortieren** — ordnet importierte Skills aus „LinkedIn (unsortiert)" kontextbasiert
  Themenbereichen zu (bevorzugt bestehende, legt neue nur bei Bedarf an). **Verschiebt nur** —
  erfindet nichts, benennt nichts um. Startet automatisch nach jedem ZIP-Import mit neuen Skills,
  manuell über „Skills neu einsortieren". *Headless.*

---

## 7. Die Oberfläche (19 Seiten)

| Seite | Zweck |
|---|---|
| **Dashboard** | KPIs (Stellen, Top-Zielstellen, laufende Bewerbungen, Antwortquote, Follow-up-Banner, „Beworbene offline"-Warnkachel seit Phase 74, Hinweis „Beispieldaten“ mit Link zu den Einstellungen, solange sie vorhanden sind, P2-59), klickbare Funnel-Stufen und Balken-Kacheln |
| **Suche** | Volltextsuche über alles (Stellen, Beschreibungen, Company-Fit, Transkripte, Debriefs, Briefings, Verlauf) — Ergebnis ist immer eine Stelle; Index-Stand + „↻ Index aktualisieren" |
| **Neu / Review** | neue Treffer aus der Pipeline sichten (Annehmen → Prüfen / Verwerfen → Kein Match) mit Verifikations-Badges; manuelle Such-/Prüf-Buttons (Jobsuche, Zielfirmen-Sweep, Headhunter-Suche, Beworben-Check, E-Mail-Check) mit Stand des letzten Laufs |
| **Follow-ups** | überfällige (rot) + anstehende Aktionen, anstehende Gespräche, Nachfass-Chips |
| **Pipeline** | Kanban mit Drag & Drop über die Status |
| **Stellen** | alle Stellen, URL-gesteuerte Filter, Sortierung, „+ Stelle anlegen"; **Status-Verteilungsbalken** über der Tabelle (Segmente proportional + klickbar als Filter, Styleguide-Farben); Badge „⛔ offline" + Filter für Bewerbungen, die laut Beworben-Check nicht mehr online sind; Etiketten „Dublette? → Job X“ und „Neuausschreibung → Job X“ neben dem Rollentitel wie in Review und Job-Detail (P2-42) — Klick führt zur Vorgänger-Stelle |
| **Job-Detail** | Kommandozentrale je Stelle: Eckdaten (inkl. Karriereseite bei geschlossenem Portal, Phase 73, und Verfügbarkeitsstatus aus dem Beworben-Check, Phase 74), Status, Follow-up, Kontakte, „Unterlagen erstellen“ (Pflichtkern Company-Fit → CV mit Gating; Beirats-Stellen-Check und Anschreiben als optionale Bausteine ohne Schloss, P2-41), CV-Entwurf jederzeit nachbearbeitbar (auch nach dem Erstellen, P2-45), Bewerbung, Interviews & Gespräche, angepasster CV, „Dateien & Dokumente“, KI-Chat, Notizen & Verlauf |
| **Inbox** | E-Mail-Verlauf, Volltext, KI-Antwort-Entwürfe; „Ohne Stelle“-Badge/-Filter + Zuordnen/Lösen einer Stelle; **Archivieren/Archiv** (P2-52): Mails ohne Stelle ausblenden (Knopf an der Zeile bzw. in der Detailansicht), aufklappbares Archiv-Panel mit Zurückholen, Gmail bleibt unverändert |
| **Firmen** | alle Firmen mit Fit-Ampel |
| **Radar** | Restructuring-Radar (Firmen mit Umbruch-Signalen) |
| **Netzwerk** | 3 Tabs: Zielfirmen · Headhunter · Netzwerk-Kontakte (mit Löschen, Sweep-/Initiativ-Chips); je Tab ein aufklappbarer **Papierkorb** mit Wiederherstellen. Die Headhunter-Spalte „Quelle“ (Blatt/Outreach) samt Zusatz „nur Blatt“ erscheint nur, wenn eine Outreach-Zeile in der Liste steht (P2-61, sonst stünde überall „Blatt“) |
| **Outreach** | Networking-Tracker (aufklappbare Zeilen, Editor, Aktivitäten-Log, Drive-Export). Menüpunkt nur, wenn `GET /api/outreach` Zeilen liefert (P2-61): Anlegen geht nicht, beim Kunden war die Seite leer und der Export ohne `data/templates/outreach_tracker_vorlage.xlsx` ein 500er |
| **Beirat** | 7-köpfiger Bewerbungs-Beirat (Charta-basiert): Thema + Kontext + Mindest-Beiträge rein, der Vorsitz orchestriert autonom (Name aus `GET /api/beirat/mitglieder`, Feld `vorsitz`), Debatte läuft live per SSE (Sprecher-Karten, Moderations-Zeilen), Synthese am Ende; Key-Panel (Anthropic/OpenAI, lokal), Debatten-Archiv. Phase 40 nahm den Menüpunkt heraus, P2-61 setzte ihn als „🏛️ Beirat“ unter Netzwerk zurück, weil Kunden die freie Debatte sonst nur über die Adresse fanden; Seitentexte seitdem in Sie-Form ohne Dateipfade. Der Stellen-Check läuft am Job-Detail |
| **Tasks** | Task-Center = das EINE Aktivitäts-Log: alle Hintergrund-Aktivitäten (Runner-Skills UND Beirat-Läufe, Phase 42) mit KPIs, Kosten, Live-Log, Abbrechen, Erneut |
| **Budget** | Kosten je Dienst & Tag, editierbare Limits |
| **Profil** *(Phase 45/47)* | Die Kandidaten-Substanz für Matching/Anschreiben: LinkedIn-Import (Datenexport-ZIP = vollständigster Weg, Profiltext oder PDF = sofort, per KI mit Vorschau), Positionierung, Skills als Chips nach Themenbereichen (Auto-Einsortierung importierter Skills), Werdegang, Zeugnis-/Zertifikat-Dateien. Beide Import-Wege additiv & zerstörungsfrei; Ableitung nach `config/profil_struktur.md` bei jedem Save. Seit P2-69 steht als erste Karte „Identität und Suchstrategie“ (`components/ProfilIdentitaet.tsx`): Sie liest und schreibt `config/profil.md` (Name, Anschrift, Kontakt, LinkedIn, Kurzprofil, Zielrolle, Rahmenbedingungen, Skill-Gaps) über `GET/PUT /api/profil/identitaet`, verlustfrei und mit Papierkorb-Kopie (§8 „Profil-Datei“) |
| **Einstellungen** *(Phase 49/50, P2-51)* | Steuerpult der Suchstrategie: **KI-Karte** *(P2-86)*: Wahl Claude oder ChatGPT (`ki_anbieter`) mit Status je Anbieter (`GET /api/ki-status`) · Suchbereich (Remote · Deutschlandweit · Stadt +Umkreis, Bezeichnung „<Stadt-Kurzform> +<km>km" auch als Filter-Reiter in der Jobliste) & Mindest-Firmengröße · **KI-Modell je Funktion** (Jobsuche/Company Fit/Beirat/CV Match/ATS Scan/Anschreiben — Opus 5.5/Sonnet 5.5/Haiku 4.5, unter ChatGPT die Codex-Modelle, Fable gesperrt (s. §8 „KI-Modelle“), Liste + Anzeigenamen kommen ausschließlich vom Backend, Default Sonnet) · **drei Plan-Karten A/B/C** (Label, aktiv, Rollentitel/Seniorität/Branche), Suchreihenfolge A→B→C · **Coach-Site-Karte** *(Phase 82)*: Adresse/SFTP-Zugang/Serverpfad (Button „automatisch ermitteln") + Coach-Login (bcrypt) + Ein/Aus-Schalter, Button „Coach-Site jetzt aktualisieren", Verbindungstest. **Suchportale** *(Phase 87)*: acht Zeilen — die sechs in Deutschland ueblichen Portale (LinkedIn, Indeed, StepStone, Xing, Nejo, Arbeitsagentur) vorbelegt mit Name + URL, dazu zwei Freizeilen. Je Zeile ein Aktiv-Schalter, editierbare URL (Platzhalter `$QUERY`/`$LOCATION`/`$PAGE`) und ein **Pruef-Button**, der die URL serverseitig abruft und dreistufig bewertet: gruen (antwortet mit Inhalt), amber (erreichbar, aber Bot-Schutz oder fast leere Antwort — als Websuche-Kanal trotzdem nutzbar; seit P2-73 auch: die Adresse leitet auf einen anderen Host um, dann gehoert die neue Adresse eingetragen, weil der Abruf der Such-Agenten einer solchen Umleitung nicht selbst folgt), rot (nicht erreichbar). Aendert sich eine Standard-Adresse, zieht der Serverstart sie in Datenbank und Suchprofil-Datei nach, sofern die gespeicherte Adresse noch woertlich die fruehere Standard-Adresse ist (`suchprofil.PORTALE_FRUEHERE_STANDARDS`); eine selbst geaenderte Adresse bleibt stehen. Die Zugriffsart je Portal steht daneben und ist fest: „per Websuche“ fuer Portale mit Bot-Schutz, „direkter Abruf“ fuer Nejo/Arbeitsagentur. Nur aktive Portale werden im Tageslauf durchsucht **Beirat — Besetzung** *(Phase 90)*: die sieben Plaetze mit Name, Perspektive, Farbe und Vorsitz-Markierung; Button „Neu besetzen“ startet den Skill `beirat-persona`, der die Persona recherchiert, in der Bauart der uebrigen Koepfe schreibt und danach die Verweise in den sechs anderen Dateien repariert. Sieben Plaetze sind fix (Ampel auf sieben Stimmen kalibriert), der Vorsitz laesst sich umhaengen, aber nicht entziehen. **Bewerbungspaket — Standardumfang** *(P2-41)*: eine Karte mit einem Schalter „Anschreiben im Paket“ (Standard aus) — Vorbelegung des Häkchens am Job-Detail, pro Stelle jederzeit übersteuerbar; kein Schalter für den Beirat, der hätte in Stufe 1 keine Wirkung. **Datensicherung** *(P2-52)*: zeigt die letzte automatische Sicherung (Zeitpunkt, Größe) und ihre Gesamtzahl, Schalter für die tägliche Automatik, Felder für die Aufbewahrung (täglich/wöchentlich/monatlich), Knopf „Jetzt sichern"; amber Warnung bei einer fehlgeschlagenen Sicherung oder wenn die letzte bei eingeschalteter Automatik älter als 3 Tage ist (`GET/POST /api/sicherung`, `PATCH /api/sicherung/einstellungen`). **Beispieldaten** *(P2-59)*: erste Karte der Seite (bis 1.7.0 stand die Lizenzkarte davor), nur bei Status `vorhanden` oder `entfernt` (`GET /api/beispieldaten`): Zählung der Beispieldaten, Knopf „Beispieldaten entfernen“ mit Inline-Rückfrage (`POST /api/beispieldaten/entfernen`), danach das Ergebnis mit Sicherungsdatei und den Dateien, die der Kunde geändert hat und die deshalb bleiben; löst `PROFIL_GEAENDERT` aus (s. u. Seitenleiste, §8 „Beispieldaten“). **Programmversion** *(P2-51)*: letzte Karte, eigener Endpunkt `GET /api/version` statt der übrigen `/api/einstellungen`-Daten — installierte Version bzw. bei einer Git-Installation der Entwicklungsstand, Datum des letzten Updates, der CHANGELOG-Abschnitt „Neu in dieser Version“ und bei einer Paket-Installation eine Update-Anleitung (`update.command`/`update_windows.bat`). Seit P2-82 trägt sie den Knopf **„Nach Updates suchen“** (nur auf Klick, `GET /api/version/neueste`, Abschnitt „Update-Auskunft über GitHub-Releases“) mit dem Hinweis, dass GitHub dabei die IP-Adresse erhält; die Fußzeile der Karte „Datensicherung“ nennt `wiederherstellen.command`/`wiederherstellen_windows.bat` zum Zurückspielen (P2-66) | Jeder Save regeneriert den verwalteten Block von `config/suchprofile.yaml` — `unterlagen` (Bewerbungspaket-Standardumfang) ist davon ausgenommen, kein Such-Parameter |
| **Dokumentation** *(P2-59)* | Die Lesetexte der Installation in Reitern (`pages/Dokumentation.tsx`, Menüpunkt vor „Rechtliches“): Version (`CHANGELOG.md`, darüber „Installiert: Version …“ aus `GET /api/version`), Funktionen, Anleitung, Installation & Updates (die Datei des laufenden Systems: `BMS_Install_Windows.md` unter Windows, sonst `BMS_Install_MAC.md`), E-Mail einrichten, Windows, Coach-Site, Beirat (der Reiter „Lizenz“ entfiel mit P2-82); in einer Entwicklungsinstallation nach einem Trenner „Intern“ zusätzlich Technik (diese Datei), Automatik, Release, Entwickler-Installation. Das Backend rendert die Dokumente (`GET /api/doku/{name}`), die Seite zeigt sie in einem Rahmen mit Sandbox (§8 „Dokumentationsseite“) |
| **Rechtliches** *(Phase 71E)* | Vier Reiter: Über dieses Programm (Herausgeber, Lizenz, Haftungshinweis, KI-Hinweis nach Art. 50 AI Act; ersetzt seit 29.10.2026 das Impressum), Open-Source-Lizenz (`lizenz.txt`, bytegleiche Kopie von `LICENSE`, Wächter `test_open_source_lizenz.py`), Datenschutz, Drittanbieter-Lizenzen — als Markdown unter `frontend/src/rechtliches/` gepflegt und von einem kleinen eigenen Renderer angezeigt (bewusst ohne npm-Paket). EULA, Widerrufsbelehrung und Vertriebs-Checkliste sind am 29.10.2026 entfallen, weil das BMS nicht mehr verkauft wird |

**Seitenleiste** *(`components/Layout.tsx`, P2-51, P2-59)*: Der Kopf ist zentriert und trägt den Produktnamen aus dem Design (`GET /api/design`, Rolle `produktname`; bis die Antwort da ist, den Titel aus `frontend/index.html`). Den Umbruch setzt der Browser in einem Block von 13,5 rem Breite, mit dem Namen der Vorgabe fällt er wie bisher nach „Bewerbungs-Management-“ (`text-base tracking-tight`: In `text-lg` ist die erste Zeile rund 243 px breit und sprengte die 240 px der Leiste, gemessen in Chrome von 320 bis 1280 px Breite). Darunter steht der Name aus `GET /api/profil` (`profile.name`, gelesen aus `config/profil.md`, Rückfall „Bewerber“). Der Browser-Titel heißt `<Produktname> · <Name>`, ohne Namen nur der Produktname; der statische Titel in `frontend/index.html` ist der Anfangswert, bis das Design geladen ist. Der Fuß zeigt immer `Version <x>`, sobald `GET /api/version` eine Version ungleich `0.0.0` kennt; den Entwicklungsstand einer Git-Installation gibt es nur noch als Tooltip (`title`) auf dieser Zeile, bis P2-59 stand er im Text („3 Commits nach 1.1.3“ verdrängte die Nummer). Der Menüpunkt „📖 Dokumentation“ steht im letzten Block direkt vor „⚖️ Rechtliches“. „🏛️ Beirat“ steht seit P2-61 direkt unter „🌐 Netzwerk“; „📇 Outreach“ erscheint nur, wenn `GET /api/outreach` beim Start Zeilen liefert (Frage nach den Daten statt nach der Installationsart, damit auch eine Git-Arbeitskopie ohne übernommene Zeilen den leeren Punkt nicht zeigt). Das Ereignis `PROFIL_GEAENDERT` (`frontend/src/profil.ts`) löst aus, wer Name oder Anschrift aus `config/profil.md` ändert (heute: „Beispieldaten entfernen“ in den Einstellungen und, seit P2-69, das Speichern der Karte „Identität und Suchstrategie“ auf der Profil-Seite): Die Seitenleiste lädt den Namen neu, und der Adress-Cache (Follow-ups, Job-Detail) verwirft seinen Wert, statt bis zum nächsten Seitenstart die alten Angaben zu zeigen.

---

## 8. Betrieb, Automatik & Sicherheit

### Betrieb im Alltag

**Starten und Beenden** (kein Auto-Reload — nach jeder Backend-Änderung ist ein Neustart nötig):

| | macOS | Windows |
|---|---|---|
| Starten | `start.command` · `start_lan.command` (WLAN) | `start_windows.bat` |
| Beenden | `Ctrl+C` im Server-Fenster, sonst `stop.command` | `Strg+C`, sonst `stop_windows.bat` |

Die Stop-Skripte sind für den Fall gedacht, dass das Server-Fenster nicht mehr erreichbar ist (geschlossen,
im Hintergrund gestartet, hängend). Sie beenden den Prozess auf dem Server-Port (Standard 8000) erst
freundlich und nach 10 s hart — **vorher prüfen sie aber, ob gerade Agent-Läufe aktiv oder eingereiht sind,
und fragen nach.** Grund: Skill-Läufe hängen als Kindprozesse am Server, und eine Beirats-Debatte läuft
sogar in ihm selbst; ein Neustart bricht sie ab. Mit `--force` überspringt man die Rückfrage; ein anderer
Port geht über `PORT=8010 ./stop.command`.

Für Skript-/Terminal-Nutzung ohne Doppelklick:
```sh
lsof -ti :8000 -sTCP:LISTEN | xargs -r kill; sleep 1
cd backend && nohup ~/.bewerbung_mgmt_venv/bin/python run_server.py > /tmp/bms_server.log 2>&1 & disown
```

**Umgebungsvariablen.** `.env.example` listet die Einstellungen, die vom Standard abweichen dürfen
(Server-Port und -Adresse, `BMS_DATA_DIR`, `BMS_SECRETS_DIR`, Grenzen für Agent-Läufe). Das Programm liest
sie ausschließlich aus der Umgebung (`os.environ`); eine Datei `.env` lädt es nicht selbst. Die Werte müssen
deshalb in jeder Shell gesetzt sein, die den Server startet.

**Backup & Restore, manuell** über `scripts/backup_db.sh` (Kopie über SQLites Online-Backup-API,
konsistent auch bei parallelen Schreibzugriffen). Die automatische Sicherung steht unten im Abschnitt
„Backups“.
```sh
scripts/backup_db.sh                    # Backup anlegen: data/backups/bewerbung_backup_<JJJJMMTT_HHMMSS>.sqlite
scripts/backup_db.sh --label vor_x       # mit Suffix, z. B. vor einer riskanten Operation
scripts/backup_db.sh --rotate            # + Rotations-Kandidaten auflisten (Dry-Run, löscht nichts)
scripts/backup_db.sh --rotate --apply    # + Kandidaten wirklich löschen (behält die neuesten 15)
scripts/backup_db.sh --rotate --apply --keep 20   # andere Aufbewahrungsmenge
```
Für das Zurückspielen gibt es `wiederherstellen.command` bzw. `wiederherstellen_windows.bat` (Abschnitt
„Backups“); von Hand geht es so: Server stoppen, gewünschtes Backup zurückkopieren
(`cp data/backups/<datei>.sqlite data/bewerbung.sqlite`), Integrität prüfen
(`sqlite3 data/bewerbung.sqlite "PRAGMA integrity_check;"` → `ok`), Server neu starten. Manuelle Backups
werden nie automatisch gelöscht — Rotation löscht ausschließlich mit explizitem `--apply`.

**`sqlite3`-CLI gegen die LAUFENDE App (Phase 67F):** Die App setzt einen expliziten `busy_timeout` (15 s,
`backend/app/db.py`), die `sqlite3`-CLI kennt diesen Wert nicht (eigener Prozess, eigene Verbindung) und hat
von Haus aus **0** — eine Ad-hoc-Abfrage gegen `data/bewerbung.sqlite`, während der Server läuft und gerade
schreibt, kann sofort mit „database is locked“ abbrechen. Bei einer Abfrage gegen die laufende App deshalb
voranstellen:
```sh
sqlite3 data/bewerbung.sqlite "PRAGMA busy_timeout=5000; SELECT ...;"
```
Beim Restore ist das nicht nötig (der Server ist dann bewusst gestoppt).

**Outbound-Check** (`scripts/outbound_check.py`, Phase 66B) liest die Agent-Task-Logs unter
`~/.bewerbung_mgmt_logs/` (nur lesend) und listet, wohin headless laufende Skills tatsächlich ausgehende
Verbindungen (curl/WebFetch) aufgebaut haben, gegen eine gepflegte Liste erwarteter Ziele:
```sh
python3 scripts/outbound_check.py            # Kurzübersicht + auffällige Treffer
python3 scripts/outbound_check.py --all       # vollständige Host-Liste statt Top-20
python3 scripts/outbound_check.py --days 7    # nur die letzten 7 Tage
```
Kein Automatismus, kein Cron, keine Alarmierung — ein Werkzeug, das bei Bedarf manuell läuft. Es ist
Erkennung, keine Vorbeugung (ehrliche Einordnung: „Was die Skill-Freigabeliste leistet — und was nicht“
unten).

### Namenskonventionen (`backend/app/naming.py`)

- **Extern** (Empfänger sehen sie): `CV_<Name>_<Firma>_<Rolle>_DE|EN`,
  `CoverLetter_<Name>_<Firma>_<Rolle>_DE|EN` (der Name kommt aus dem Profil, z. B. `CV_MaxMustermann_<Firma>_<Rolle>_DE`).
- **Intern**: `JJJJMMTT_<Typ>_<Firma>[_<Rolle>]` (Typ = CompanyFit / Match / ATSscan / Briefing /
  Auswertung / Anzeige / Beirat / Analyse; `Transkript_<JJJJMMTT>_<Teilnehmer>_<Firma>_<Rolle>[_Rn]` für
  den Upload). Seit Phase 30 Standard für Neues, der Bestand wurde in Phase 31 migriert. P2-63 hat das
  Datum von `JJJJ_MM_TT_` auf `JJJJMMTT_` verkürzt und die Typ-Wörter ersetzt (`Stellenausschreibung` →
  `Anzeige`, `TranskriptReport` → `Auswertung`, `BeiratsCheck` → `Beirat`). `report_filename` nimmt die
  alten Typ-Wörter weiter als Eingabe und bildet sie auf die neuen ab; `posting_filename` liefert wie
  alle Berichte `<Datum>_Anzeige_<Firma>_<Rolle>`.
- **Kürzung (P2-63)**: Die Firma geht durch `_firma_kurz` (alles ab der ersten `(`, `:`, `,`, `;`, `|` oder
  ` - ` fällt weg, Rechtsformen am Ende ebenso, dann Bereinigung und höchstens 25 Zeichen an einer
  Wortgrenze), auch für CV und Anschreiben. Die Rolle hat 30 Zeichen (Berichte, Anzeige, Transkript) bzw.
  35 (CV, Anschreiben), Gender-Zusätze und Regionszusätze nach ` - ` fallen weg. Nicht betroffen:
  Sicherungen, Debatten-IDs und Persona-Backups im Beirat, der Outreach-Tracker (`<JJJJ>_Job_Search_Tracker_…`,
  nur das Jahr).
- **Leser verstehen beide Datumsformate**: Papierkorb-Alter (`cleanup`), `migrate_reports`, der
  Wiederverwendungs-Test beim CV- und Anschreiben-Export (ein Name nach alter Konvention derselben
  Stelle gilt als eigener, damit keine Waise entsteht) und die Skills (`recheck_von` liest das Datum
  des Vorgänger-Dashboards aus beiden Formaten).
- **Bestand umbenennen (intern, `backend/pipeline/namen_umstellen.py`, P2-63)**: Quelle der Wahrheit ist
  die Datenbank. Je Pfadfeld wird der neue Name aus Firma, Rolle, Runde und Sprache der DB und dem Datum
  des alten Namens gebildet, gekoppelte Dateien (CV und Anschreiben als `.docx` plus `.pdf`, Beirat-HTML
  mit `_rohdaten.json`, Transkript-Upload) ziehen gemeinsam um, Uploads ohne DB-Bezug bekommen nur das
  neue Datumsformat. Links in den HTML-Berichten werden mitersetzt. Nicht angefasst werden
  `data/papierkorb/`, `data/backups/`, `data/cv_basis/`, Entwürfe, Persona-Backups und die
  Verlaufsfelder (Aufgaben-Ergebnisse, Job-Chat, Notizen). Aufruf im Ordner `backend`:
  - `python -m pipeline.namen_umstellen --probe [--bericht <pfad.json>]` ändert nichts, öffnet die DB nur
    lesend und schreibt einen Bericht (alt → neu je Feld und Datei, Kollisionen, fehlende Dateien,
    Linkersetzungen).
  - `python -m pipeline.namen_umstellen --ausfuehren` prüft, dass keine Aufgabe läuft, legt eine
    Sicherung an (DB plus ZIP der betroffenen Ordner nach `data/backups/vor_p2-63_<zeit>.zip`), benennt
    um und protokolliert jede Umbenennung sofort (`data/backups/namen_p2-63_<zeit>.json`), setzt die
    DB-Felder in einer Transaktion und ersetzt die Links. Bei einem Fehler wird alles zurückgedreht
    (Exit-Code ungleich 0). Ein zweiter Lauf ändert nichts mehr.
  - `python -m pipeline.namen_umstellen --zurueck <protokoll.json>` spielt ein Protokoll rückwärts ab
    (Dateien und DB-Felder). Fehlende Dateien lässt das Werkzeug unverändert und nennt sie im Bericht.
  Der Server sollte dafür gestoppt sein.

### Lizenz — ausgebaut (P2-82)

Bis Version 1.7.0 verlangte das BMS eine signierte Lizenzdatei (Phase 72B, P2-67, P2-68): Ohne sie
lief es nur lesend, mit Sperren im Server, in der Kommandozeile, im Runner und in der Beirat-Engine,
dazu Lizenzkarte, Hinweisband und Kauf-Link in der Oberfläche. Seit dem 29.10.2026 wird das BMS nicht
mehr verkauft, sondern steht als Open Source unter der Apache License 2.0 (`LICENSE`, `NOTICE`).
**P2-82 hat die Lizenzpflicht vollständig ausgebaut** (Verträge L und O
der Bau-Spec P2-82):

- Das BMS läuft ohne Lizenzdatei mit vollem Funktionsumfang. Keine Route antwortet mehr mit 402, die
  Kommandozeilen-Werkzeuge kennen den Exit-Code 4 nicht mehr, Lizenzmodul, Lizenz-Endpunkte,
  Lizenzkarte, Band und die Test-Lizenz in `tests/conftest.py` sind gelöscht.
- Kein Teil des BMS spricht mehr den früheren Server der Plattform an. Eine vorhandene Lizenzdatei
  im Secrets-Verzeichnis wird weder gelesen noch gelöscht; der CHANGELOG sagt, dass sie nicht mehr
  gebraucht wird.
- `cryptography` ist keine direkte Abhängigkeit mehr und bleibt nur transitiv über `google-auth` im
  Lock.
- `tests/test_ohne_lizenz.py` hält den Zustand fest: kein ausgeliefertes Modul importiert das alte
  Lizenzmodul, die Namen der früheren Lizenzprüfung kommen unter `backend/`, `frontend/src/`,
  `scripts/` und `.claude/` nicht mehr vor, und eine schreibende Route antwortet ohne Lizenzdatei
  mit 200.
- Der frühere Stand (Versionen bis 1.7.0, Spec P2-67) gehört zur privaten Entwicklungshistorie und ist im
  öffentlichen Repository nicht enthalten.

**Recht.** Eine EULA gibt es seit dem 29.10.2026 nicht mehr: Das BMS wird nicht mehr verkauft und
steht unter der Apache License 2.0 (`LICENSE`, `NOTICE`). Die Lizenzpflicht ist seit P2-82 ausgebaut.

### KI-Modelle: eine Quelle für Aliase und Anzeigenamen, Fable gesperrt (P2-51, P2-59)

Gespeichert werden CLI-Aliase (`opus`/`sonnet`/`haiku` in `sucheinstellung.modelle_json`, keine
Migration nötig — die CLI löst einen Alias immer auf das jeweils aktuelle Modell auf). Die Liste
selbst mit Alias UND Anzeigename (`agent_runner.MODELLE`: `opus` „Opus 5.5“, `sonnet` „Sonnet 5.5“,
`haiku` „Haiku 4.5“, Standard `MODELL_STANDARD = "sonnet"`) pflegt seit P2-51 ausschließlich das
Backend; `main.py::_einstellungen_out` liefert sie unverändert als `modell_optionen` mit
`modell_standard` aus. Die Labels nennen die Version, auf die der Kurzname in der installierten CLI
heute zeigt (`sonnet` → `claude-sonnet-5-5`); die App ruft die CLI weiter mit dem Kurznamen auf und
pinnt keine Modell-ID. Die frühere, eigene Kopie in `frontend/src/api.ts` (veralteter Anzeigename,
`fable` fehlte) entfällt ersatzlos. Unter ChatGPT liefert `ki_anbieter.modell_optionen` an dieser Stelle
die Codex-Modelle (`CODEX_MODELL_OPTIONEN`), gespeichert bleiben dieselben Stufen.

**Fable ist nicht wählbar (P2-59, Vorgabe vom 01.10.2026).** Grund sind die Kosten: Fable 5.1
kostet $10 Eingabe und $50 Ausgabe je Million Tokens, Opus 5.5 $4/$20, Sonnet 5.5 $2/$10 und
Haiku 4.5 $1/$5 (Stand claude-api-Referenz vom 25.09.2026), also das 2,5-Fache von Opus und das
Fünffache von Sonnet. Die Regel steht an vier Stellen, `tests/test_modellwahl.py` hält jede fest:

- `agent_runner.GESPERRTE_MODELLE = ("fable",)` hält fest, was bewusst draußen bleibt. Ein
  Wächter-Test sorgt dafür, dass die Liste sich nie mit `MODELL_ALIASE` überschneidet und kein Label
  Fable nennt.
- Erlaubnisliste statt Sperrliste: `main.py::_validiere_modelle` lehnt jeden Wert außerhalb von
  `MODELL_ALIASE` mit 422 ab, auch `fable`. `PATCH /api/einstellungen` ändert dann nichts in der
  Datenbank, und die Meldung (aus `MODELL_ALIASE` gebaut) nennt Fable nicht.
- `agent_runner.wirksames_modell(alias)` liefert den Alias, wenn er in `MODELL_ALIASE` steht, sonst
  `MODELL_STANDARD`. `modell_fuer_kind` und `modell_fuer_beirat` laufen darüber: Ein früher
  gespeichertes `fable` startet mit Sonnet, ohne dass die gespeicherte Zeile angefasst wird, und je
  Prozess und Wert steht eine Zeile im Server-Log (`[agent-runner] Modell 'fable' ist gesperrt …`).
  `_einstellungen_out` zeigt dieselben WIRKSAMEN Werte, damit die Auswahl nie einen Wert trägt, den es
  dort nicht gibt.
- `agent_runner._argv` setzt für JEDEN `claude -p`-Lauf ein ausdrückliches `--model`: die Wahl der
  Funktion aus den Einstellungen (`modell_override`), sonst die feste Angabe in `PROMPTS`, sonst
  `MODELL_STANDARD`. Bis P2-59 liefen die Läufe ohne eigene Funktion in der Modellwahl (z. B.
  `email-check`, `gespraech-debrief`, `absagen-analyse`) ganz ohne `--model`, also mit dem
  Standardmodell der installierten CLI, und das kann bei einem Kunden Fable sein (in der Entwicklungsinstallation
  zeigte es laut `modelUsage` seit September auf Sonnet, dort änderte sich nichts). Die einzige feste
  Angabe in `PROMPTS` ist `job-frage`; sie nennt seit P2-59 den Kurznamen `sonnet` statt
  `claude-sonnet-5`, und jedes `PROMPTS[*]["model"]` muss ein Alias aus `MODELL_ALIASE` sein
  (Wächter-Test). Die Stellenansicht zeigt unter dem Chat entsprechend „Modell: Sonnet“. Der Beirat
  (`beirat_engine`) übergibt sein Modell schon immer, über `modell_fuer_beirat()` und damit ebenfalls
  durch `wirksames_modell`.

### Version, Update und Freigabe (P2-51)

`VERSION` (Projekt-Root, eine Zeile `MAJOR.MINOR.PATCH`, „0.0.0" heißt „noch keine Freigabe") ist
die einzige Quelle der Versionsnummer; nur `pipeline/release.py::freigeben()` schreibt sie.
`CHANGELOG.md` ist Kundentext (Sie-Form, ausgeliefert): der Abschnitt „## Unveröffentlicht" wird
bei jeder Freigabe zum neuen Versionsabschnitt „## X.Y.Z (TT.MM.JJJJ)", ein leerer neuer
„Unveröffentlicht"-Abschnitt entsteht direkt darüber. Beides regelt `pipeline/changelog.py`
(`version_tupel`, `abschnitte`, `abschnitt`, `pruefen`, `freigeben`) — dieselbe API liest sowohl
die Freigabe (`pipeline/release.py`) als auch die laufende App (`app/version.py`, Abschnitt der
installierten Version für die Einstellungen-Seite).

Jedes Kundenpaket bekommt zusätzlich `bms_manifest.json` (Vertrag V3 der Bau-Spec, gebaut von
`pipeline/kundenpaket.py::bauen()` NACH dem Ersetzen der Kundendateien, VOR der
Personendaten-Prüfung — das Manifest wird selbst mitgeprüft): Pfad → `{ausfuehrbar, groesse,
sha256}` jeder ausgelieferten Datei, dazu `commit`/`commit_datum`, `version` (aus `VERSION` des
gepackten Stands, nicht vom Arbeitsbaum), `freigabe` (trägt der Commit das Tag `v<version>`?),
`vorschau` (true bei `--arbeitsbaum`) und `anpassbar` (fnmatch-Muster für Dateien, die eine
Installation nach dem Auspacken verändern darf, z. B. `.claude/agents/beirat-*.md`,
`config/profil_struktur.md`, `config/scoring_rubrik.md`). Ersetzt das frühere `VERSION.txt`
(P2-50) ersatzlos — `datetime.now()` machte es nicht reproduzierbar, das Manifest lässt sich aus
demselben Commit jederzeit identisch neu bauen.

Beim Kunden spielt `scripts/bms_update.py` (nur Standardbibliothek, kein Import aus `app`/
`pipeline` — das Skript läuft neben einer halb ersetzten Installation) ein neues Paket ein:
Installation prüfen (kein Git-Checkout, läuft in der venv) → Paket finden (P2-82: ein Pfad-Argument
gilt ohne jeden Netzkontakt; sonst gewinnt die höchste Version aus dem neuesten GitHub-Release
und aus `~/Downloads/BMS_*.zip`, ein geladenes Paket liegt unter `data/updates/pakete/` und gilt
danach wie ein übergebenes, Einzelheiten im Abschnitt „Update-Auskunft über GitHub-Releases“ unten) →
Selbstaktualisierung (weicht das Skript im Paket vom laufenden ab, wird mit `--delegiert` an die
neue Fassung übergeben, damit immer die Update-LOGIK der neuen Version gilt; den Pfad des Pakets
bekommt sie ausdrücklich als Argument, sonst suchte und lüde sie ein zweites Mal) → Paket prüfen (Manifest, SHA-256, keine unsicheren/
geschützten Pfade, Version/Vorschau) → Server-aus-Check (`GET /api/health`) → Plan erstellen und
zeigen (`--pruefen` endet hier) → Rückfrage (übersprungen mit `--ja`) → Sperre → Sicherung
(Datenbank-Kopie über die sqlite3-Backup-API, jede ersetzte/entfernte Datei, altes Manifest, ggf.
alter `frontend/dist`) → Dateien atomar schreiben → Abhängigkeiten (`pip install`, `npm ci`,
Oberfläche neu bauen, je nach dem, was sich geändert hat) → Selbsttest → Abschluss (neues
Manifest, `bericht.json`, Sperre lösen). Jeder Fehler ab „Dateien schreiben" rollt vollständig
zurück (Exit 2) statt eine Kundeninstallation halb fertig zu lassen. Der Selbsttest
(`backend/app/selbsttest.py`, `python -m app.selbsttest`) läuft in einem EIGENEN Subprozess gegen
eine Kopie der gesicherten Datenbank (`BMS_DATA_DIR`/`BMS_LOG_DIR`/`BMS_SECRETS_DIR` auf
Temp-Verzeichnisse) — er importiert `app.main` (fängt fehlende Pakete/Syntaxfehler) und prüft
`init_db()` gegen `SQLModel.metadata` (fängt eine vergessene `_ADD_COLUMNS`-Migration). Gestartet
wird über `update.command` (zsh) bzw. `update_windows.bat` (CRLF, s. u.) — beide reichen nur den
Programmordner durch und laufen komplett in einer Funktion bzw. einem geklammerten Block, weil das
Update die aufrufende Datei selbst ersetzen kann, während sie noch läuft. `--zurueck` nimmt das
letzte erfolgreiche Update zurück; die Rückfrage, ob dabei auch die Datenbank auf den Stand davor
zurückgesetzt wird, beantwortet **ausschließlich** der eigene Schalter `--mit-datenbank` — `--ja`
gilt nur für die Einspiel-Rückfrage, nie für die Datenbank-Rückfrage (zwei getrennte
Risikostufen).

`GET /api/version` (`app/version.py` + dünner Router `app/routes_version.py`) beantwortet, welche
Fassung gerade läuft: „paket" (liegt `bms_manifest.json` im Programmordner, Werte von dort,
`commit` auf 7 Zeichen gekürzt), „git" (liegt `.git`, `version` aus `VERSION`, `commit`/`datum`
über `git rev-parse`/`git show`, `entwicklungsstand` aus `git describe --tags --long --dirty`) oder
„unbekannt". Jeder Git-Aufruf läuft mit 5-s-Timeout und fängt jeden Fehler ab — die
Einstellungen-Seite darf an dieser Auskunft nie mit einem 500 scheitern.

Die Freigabe selbst ist das Werkzeug des Herausgebers (`pipeline/release.py` über `scripts/release.sh`:
`freigeben`/`notizen`/`abholen`) und der Workflow `.github/workflows/release.yml` (Tag-Push
`v*.*.*` oder `workflow_dispatch` für einen Probebau). Zum Anwender gelangt das Paket seit P2-82 über das
GitHub-Release selbst: Die Freigabe endet mit dem Release, ein Ablegen auf einem Server gibt es nicht
mehr (der Paketdienst von P2-71 ist ausgebaut). Das Update-Werkzeug und die Installationsanleitungen
laden das Paket dort, der Knopf in den Einstellungen zeigt die neueste Version an (Abschnitt
„Update-Auskunft über GitHub-Releases“). Ausführlich in `docs/RELEASE.md`.

### Update-Auskunft über GitHub-Releases (P2-82)

Neue Versionen erscheinen als GitHub-Release des öffentlichen Repos `holgerdaube/BewerbungsMgmtSystem`.
Zwei Stellen fragen dort nach, beide nur auf Anstoß des Anwenders: der Knopf „Nach Updates suchen“ in
der App (Vertrag A der Bau-Spec P2-82) und das Update-Werkzeug
`scripts/bms_update.py` (Vertrag U). Solange das Repo kein veröffentlichtes Release trägt, zeigt der
Knopf „Es ist noch keine Version veröffentlicht.“

- **Repo und Adresse sind Konstanten, keine Umgebungsvariablen.** `GITHUB_REPO` steht an genau zwei
  Stellen, in `app/update_pruefen.py` und in `scripts/bms_update.py` (das Werkzeug darf nichts aus
  `app` importieren); `tests/test_update_pruefen.py` hält beide gleich. Dazu `GITHUB_API =
  "https://api.github.com"`. Wer die Adresse umbiegen könnte, könnte ein fremdes Paket unterschieben.
  Nur Tests ersetzen die Konstanten im Prozess, durch einen Probeserver auf 127.0.0.1; kein Test
  spricht GitHub an.
- **Nur auf Anstoß.** Es gibt keinen Abruf beim Start, keinen Hintergrund-Abruf und keine Erinnerung.
  Die laufende App fragt nur auf den Klick, das Werkzeug nur nach dem Doppelklick auf
  `update.command`/`update_windows.bat`, die Installationsanleitungen nur mit ihrem Ladebefehl. Der
  Tageslauf und die Skills sprechen nie mit GitHub. Ein Pfad-Argument und `--offline` unterbinden jeden
  Kontakt des Werkzeugs.
- **Was GitHub sieht.** Anonym, ohne Token und ohne Kennung: die IP-Adresse des Rechners und die
  Anfrage selbst, mit dem `User-Agent: BMS-Update` (bei der Auskunft dazu `Accept:
  application/vnd.github+json` und `X-GitHub-Api-Version: 2022-11-28`). Keine Version, kein
  Systemname, keine Rechnerkennung, nichts aus der Datenbank. Das steht neben dem Knopf (
  „GitHub erhält dabei die IP-Adresse dieses Rechners.“), vor jeder Suche des Werkzeugs und im Reiter
  „Datenschutz“ (`frontend/src/rechtliches/datenschutz.md`). Der Herausgeber betreibt keinen Server
  für das Programm und erhält keine Daten.
- **Knopf, Backend.** `GET /api/version/neueste` (`app/routes_version.py`, absichtlich `def` statt
  `async`, damit der blockierende Abruf im Threadpool läuft) ruft `update_pruefen.neueste_version(
  installiert)`: ein GET auf `{GITHUB_API}/repos/{GITHUB_REPO}/releases/latest` mit `httpx`,
  `follow_redirects=False`, Zertifikatsprüfung an, höchstens 10 Sekunden (`ZEIT_S`) und höchstens 1 MB
  Antwort. Die Proxy-Einstellungen des Rechners gelten. Der Endpunkt speichert nichts, hat keinen
  Zwischenspeicher und schreibt keine IP und keinen Antwortinhalt ins Protokoll. Die Antwort ist immer
  200 und trägt `installiert`, `neueste` (aus `tag_name` der Form `vX.Y.Z`), `neuer` (Vergleich der
  Zahlentupel, `1.10.0` ist neuer als `1.9.0`; ist die installierte Version unbekannt oder `0.0.0`,
  ist `neuer` wahr), `veroeffentlicht` (Datum aus `published_at`), `seite` (`html_url`, nur wenn sie
  mit `https://github.com/{GITHUB_REPO}/releases/` beginnt, sonst `null`), `aenderungen` (`body` des
  Release, höchstens 4000 Zeichen, nur Text) und `fehler`. Bei einem Fehler steht ein Kundentext in
  `fehler` und alle Felder außer `installiert` sind `null`: „Es besteht keine Verbindung zu GitHub.“,
  „GitHub antwortet nicht rechtzeitig.“, „Die Verbindung zu GitHub wurde unterbrochen.“, „Die sichere
  Verbindung zu GitHub ließ sich nicht prüfen.“, „Die Antwort von GitHub ist ungültig.“, bei 404 „Es
  ist noch keine Version veröffentlicht.“ und bei 403/429 „GitHub begrenzt gerade die Anfragen. Bitte
  versuchen Sie es in einer Stunde erneut.“ (ohne Anmeldung gelten 60 Anfragen je Stunde und
  IP-Adresse).
- **Knopf, Oberfläche.** `VersionKarte` in `pages/Einstellungen.tsx` zeigt den Knopf „Nach Updates
  suchen“ (während der Abfrage „Suche …“ und gesperrt) mit dem Hinweis zur IP-Adresse darunter. Das
  Ergebnis lautet „Ihr BMS ist auf dem neuesten Stand (Version X).“, oder „Version X ist erschienen
  (TT.MM.JJJJ).“ mit den Änderungen und dem Link „Auf GitHub ansehen ↗“ (`target="_blank"`,
  `rel="noopener noreferrer"`, nur bei gesetzter `seite`), oder der Fehlertext. Die Änderungen zeigt
  `aenderungenListe` als reinen Text: nur „- “-Zeilen, Backticks als `<code>`, kein HTML. Bei einer
  Paket-Installation steht darunter die Anleitung zum Einspielen (BMS beenden, `update.command` bzw.
  `update_windows.bat` doppelklicken, BMS starten; ohne Internet die ZIP-Datei in den Download-Ordner
  legen), bei einer Git-Installation „Entwicklungsinstallation: Updates kommen über Git.“ **Die App
  spielt nie ein.** Einspielen geht nur bei beendetem Server über das Werkzeug (sein Schritt 5 prüft
  das).
- **Werkzeug, Auskunft.** `online_auskunft()` fragt dieselbe Adresse und prüft die Antwort streng:
  `version` aus `tag_name` ohne führendes `v` (Form `X.Y.Z`, je Teil höchstens 9 Ziffern); `url` ist
  die `browser_download_url` des Assets `BMS_<version>.zip` und muss genau `https://github.com/
  {GITHUB_REPO}/releases/download/v<version>/BMS_<version>.zip` lauten; `groesse` (`size`) liegt
  zwischen 1 und `PAKET_MAX_BYTES` (200 MB); `sha256` kommt aus `digest` (Form `sha256:<64 Hex>`, von
  GitHub beim Hochladen berechnet) und, wenn `digest` fehlt, aus der ersten Zeichenfolge des Assets
  `BMS_<version>.zip.sha256`. Fehlt beides, wird nichts eingespielt („Zur neuesten Version fehlt die
  Prüfsumme. Sie wird nicht eingespielt.“). `seite` ist `html_url` unter denselben Bedingungen wie
  oben. Die Auskunft folgt keiner Umleitung. Die beiden Funktionen auf Modulebene heißen fest
  `online_auskunft` und `online_laden`.
- **Werkzeug, Laden.** `online_laden(auskunft, ziel)` lädt nach `data/updates/pakete/BMS_<Version>.zip.teil`;
  der Dateiname entsteht allein aus der geprüften Versionsnummer, nie aus einer Kopfzeile der Antwort.
  Gelesen werden höchstens `groesse` Byte, Größe und SHA-256 werden vor dem Umbenennen auf `.zip`
  gegen die Auskunft geprüft („Das geladene Paket ist unvollständig oder beschädigt.“); ein
  beschädigtes Paket erscheint nie unter dem endgültigen Namen. Andere `BMS_*.zip` und `*.teil` im
  Ordner werden vorher gelöscht, eine schon vorhandene, passende Datei wird nicht neu geladen, ein mit
  `--pruefen` geladenes Paket bleibt liegen. Danach prüft das Werkzeug wie bei jedem Paket das
  Manifest (Version 3, SHA-256 je Datei).
- **Umleitungsregel.** Beim Laden folgt das Werkzeug höchstens `UMLEITUNGEN_MAX = 3` Umleitungen. Jede
  nur nach `https://`, zum Standardport, ohne Zugangsdaten in der Adresse, und nur zu `github.com`
  oder einem Host, dessen Name auf `.githubusercontent.com` endet (`_ziel_erlaubt`); jedes andere Ziel
  ist ein Fehler, zu dem nie eine Anfrage geht. GitHub leitet den Download tatsächlich nach
  `release-assets.githubusercontent.com` um. Gilt auch für das Asset `.sha256`.
- **Ablauf der Auswahl.** Das Angebot gewinnt, wenn es höher ist als die installierte Version (mit
  `--erzwingen` genügt gleich hoch) und höher als der beste Kandidat in „Downloads“. Jeder Fehler der
  Online-Suche ist ein Hinweis, kein Abbruch: Es geht mit dem Kandidaten aus „Downloads“ weiter. Ohne
  Kandidat gilt: Hat GitHub geantwortet und bietet nichts Höheres, steht dort „Ihr BMS ist auf dem
  neuesten Stand (Version …)“ mit Exit 0. War GitHub nicht erreichbar oder wurde nicht gefragt, bricht
  das Werkzeug mit „Kein Update-Paket gefunden …“ ab, ergänzt um den Grund.
- **Netz.** Das Werkzeug nutzt nur die Standardbibliothek (`urllib.request` mit
  `ssl.create_default_context()`). Die Zertifikatsprüfung ist nie abgeschaltet und wird nach einem
  Fehler nie ohne Prüfung wiederholt, der Opener hat keinen Umleitungs-Handler, die Proxy-Einstellungen
  des Rechners gelten. Zeitgrenzen `ZEIT_AUSKUNFT_S = 10` und `ZEIT_LADEN_S = 120`. Der Text einer
  Serverantwort wird nie angezeigt: Jede Antwort wird auf einen festen Kundentext abgebildet. Wächter im
  Quelltext (`tests/test_bms_update_github.py`): kein `_create_unverified_context`, kein `CERT_NONE`,
  `os.environ` nur für die bekannten Namen, keine Importe außerhalb der Standardbibliothek.
- **Alte Installationen.** Installationen bis 1.7.0 fragen weiter den früheren Paketdienst und
  bekommen dort nie 2.0.0. Ein Brückenpaket gibt es nicht: Wer so eine Installation hat, lädt 2.0.0 einmal
  als ZIP-Datei von der Release-Seite in den Download-Ordner, danach sucht das Werkzeug selbst bei GitHub.

Ehrliche Grenzen: **Vertrauensanker ist das GitHub-Konto des Herausgebers.** Wer es übernimmt, kann ein Release mit
fremdem Code veröffentlichen; `digest` und Manifest kämen dann vom selben Ort. Schutz sind die
Zwei-Faktor-Anmeldung und Releases nur über `release.yml`. Später möglich: ein Herkunftsnachweis per
GitHub-Attestierung (`actions/attest-build-provenance`) und seine Prüfung im Werkzeug. Die
Anfragegrenze von 60 Anfragen je Stunde reicht für einen Knopf, hinter einem gemeinsamen
Firmen-Ausgang kann sie knapp werden. Die Release-Notizen kommen aus `CHANGELOG.md` und werden nur als
Text gezeigt; Formatierungen außer „- “-Zeilen gehen verloren.

### Umkreis: Bezeichnung bleibt Kennung (P2-51)

`pipeline/suchprofil.py::stadt_kurzform()`/`umkreis_label()` (Vertrag V7 der Bau-Spec) bilden aus
Stadt und Radius die Bezeichnung „<Stadt-Kurzform> +<km>km" (Kurzform = Stadtname ohne
Namenszusatz wie „ am ", „ an der ", „ im "; „Frankfurt am Main" → „Frankfurt"). Diese Bezeichnung
ist zugleich Anzeigetext UND KENNUNG — `Job.tab`/`Company.region` speichern sie wörtlich, genau
wie zuvor eine feste Zeichenkette mit Stadt und Radius, nur jetzt dynamisch aus den Einstellungen
(Entscheidung 5 der Bau-Spec, vgl. Lehre „Blast-Radius" vom 28.08.).

Ändert eine Installation Stadt oder Radius, stellt `main.py::update_einstellungen` in DERSELBEN
Transaktion `job.tab` und `company.region` von der alten auf die neue Bezeichnung um (auch Stellen
im Papierkorb), bevor `suchprofil.regenerieren()` läuft; die PATCH-Antwort trägt zusätzlich
`umbenennung` (`von`/`nach`/`jobs`/`firmen`), die Oberfläche zeigt sie als Bestätigung an.
`tab_normalisieren()` bildet daneben einen ABWEICHENDEN alten Umkreis-Namen (jedes Muster
`<Text> +<Zahl>km`) beim Schreiben eines Jobs (Ingest, `POST`/`PATCH /api/jobs`) auf das AKTUELLE
Label ab, und normalisiert „remote"/„deutschlandweit" in beliebiger Schreibung auf die kanonische
Form.

Der Umkreis-Bucket in `config/suchprofile.yaml` (verwalteter Kopf) trägt die Bezeichnung als
Schlüssel unter `buckets`, Wert `{regionen: [stadt], onsite_ok: true, stadt, umkreis_km}`. Die
Suchabläufe lesen `stadt`/`umkreis_km` direkt; ein älterer Kopf ohne diese Felder fällt auf
`regionen[0]` bzw. die Zahl im Schlüssel zurück.

### Mail-Provider: Gmail oder IMAP (Phase 71F)

`pipeline/gmail_client.py` bleibt die Fassade, die alle Mail-Skills aufrufen; sie dispatcht nach
`mail_settings.json` (Secrets-Verzeichnis) entweder in den bestehenden Gmail-OAuth-Codepfad oder
nach `pipeline/imap_mail.py` — Letzteres öffnet das System für Kunden ohne Gmail (GMX, Web.de,
mailbox.org, Posteo, iCloud-Mail mit App-Passwort …), ausschließlich mit Python-Stdlib
(`imaplib`/`email`, keine dritte Bibliothek). Durchsucht wird nur `INBOX`; Gmails Suchsyntax
(`after:`/`from:`/`newer_than:`/…) wird nach IMAP übersetzt, alles ohne IMAP-Äquivalent (z. B.
Gmail-Kategorien/Labels) wird übersprungen und gemeldet statt stillschweigend ignoriert. Dieselbe
Sicherheitsgarantie wie bei Gmail gilt hier ebenso: genau drei Verben (`search`/`get`/`draft`),
kein `smtplib`-Import irgendwo in `backend/pipeline/` — testbewehrt als Negativ-Wächter
(`tests/test_kein_sendcodepfad.py`).

### Automatik-Grenzen (ehrlich)

Echte Zeitsteuerung (launchd/cron) scheitert, wenn das Projekt in iCloud Drive liegt: Ein Hintergrund-Job kann iCloud Drive
**nicht** lesen ohne manuellen „Vollständiger Festplattenzugriff"-Grant (Sicherheitseinstellung,
nur der User). Deshalb werden Excel/Digest/Suchindex manuell über den `tageslauf`-Skill bzw.
Dashboard-Buttons frisch gehalten. Der deterministische Refresh (`scripts/refresh_views.sh`) ist
cron-tauglich vorbereitet, aber nicht aktiv scharfgeschaltet.

Seit P2-52 gibt es EINE Ausnahme: der Sicherungstakt (`app/sicherung.py::starten()`) läuft als
asyncio-Task direkt im Server-Prozess selbst, unabhängig von launchd/cron und damit ohne das
iCloud-Zugriffsproblem oben (der Prozess läuft ja bereits, mit den Rechten des Terminal-Starts).
Bewusst eng gehalten: er sichert nur die Datenbank, nichts sonst — Excel/Digest/Suchindex bleiben
wie oben beschrieben manuell.

### Was die Skill-Freigabeliste leistet — und was nicht (Phase 66)

`automation/agent_settings.json` schaltet für headless laufende Skills (`claude -p`) eine
Berechtigungsliste scharf: nur explizit erlaubte Werkzeuge/Kommandos dürfen laufen, alles andere
ist automatisch verboten. Wichtig ist hier eine ehrliche Grenze (s. Bau-Spec Phase 66,
„Die ehrliche Ausgangslage"):

- **Was sie leistet:** Schutz gegen **Unfälle**. Ein Skill, der versehentlich `rm`, `git push`
  oder `chmod` auslösen würde, wird gestoppt, bevor etwas passiert — belegt im echten Lauf vom
  10.07.2026, als `Artifact` (Veröffentlichung nach außen) korrekt geblockt wurde.
- **Was sie NICHT leistet:** keine Grenze gegen eine **gezielte Prompt-Injection**. Die Skills
  verarbeiten unbeaufsichtigt fremden Text (Stellenanzeigen, eingehende Mails, Firmenwebsites);
  `Bash(python:*)` bleibt bewusst uneingeschränkt erlaubt, weil das dokumentierte Muster für
  DB-Schreibzugriffe ein Python-Heredoc ist. Ein Python-Einzeiler kann alles, was `curl` kann, und
  mehr — nur `curl` zu sperren wäre Theater, dieselbe Exfiltration ginge zwei Zeilen später über
  Python. Diese Liste verkleinert also ausschließlich den Schaden bei einem Fehler, nicht das
  Risiko einer absichtlichen Umgehung.

**Was Phase 66 stattdessen liefert** (Schadensbegrenzung, Kennzeichnung, Erkennung statt einer
vorgetäuschten Sicherheitsgrenze):
- **66A — Schadensradius:** `agent_runner._child_env(kind)` reicht pro Skill-Subprozess nur noch
  die für DIESE Art freigegebenen Secrets aus `agent.env` weiter (Tabelle `SECRET_KEYS_BY_KIND`,
  einzige Zuordnung aktuell: `jobsuche-apify` → `APIFY_TOKEN`), statt wie bisher jeden Schlüssel an
  jeden Subprozess zu geben — mit lauter Meldung im Task-Log, falls ein Skill doch mehr braucht.
  9 von 22 headless-Arten bekommen zusätzlich `disallowed_tools` (WebSearch/WebFetch gesperrt, wo
  der Skill sie nachweislich nicht nutzt).
- **66B — Kennzeichnung:** `agent_runner.HEADLESS_SUFFIX` (hängt an JEDEM headless-Prompt) markiert
  jeden per WebFetch/WebSearch/curl/gmail_client geladenen Fremdtext ausdrücklich als
  Datenmaterial, nicht als Anweisung, mit der Aufforderung, eingebettete Anweisungen zu ignorieren
  und im Bericht zu melden — ergänzt an den zwei konkretesten Einbettungsstellen (`firma-pruefen`/
  SKILL.md Anzeigen-Snapshot, `email-check`/SKILL.md Mail-Klassifikation). Das ist **Hygiene, keine
  Garantie** — eine Verhaltensregel für das Modell, keine technische Schranke.
- **66B — Erkennung:** `scripts/outbound_check.py` liest die Agent-Logs (nur lesend) und listet
  ausgehende Ziele (curl/WebFetch) gegen eine gepflegte Liste erwarteter Hosts — kein Automatismus,
  kein Cron, keine Alarmierung, ein Werkzeug für den manuellen Blick bei Bedarf.

**Ausdrücklich offen** (nicht Teil von Phase 66, hier nur benannt statt wegdefiniert):
- **`gmail.compose`-Scope:** erlaubt der Google-API technisch mehr als Entwürfe (auch Senden) — die
  einzige Grenze ist der fehlende Codepfad in `pipeline/gmail_client.py` (keine `send`-Funktion,
  kein `/send`-Endpunkt), nicht die Technik. Seit Phase 71F gilt dieselbe Garantie für den
  IMAP-Provider `pipeline/imap_mail.py` (Entwürfe nur per APPEND, kein `smtplib`-Import in
  `backend/pipeline/` — als Negativ-Wächter in `tests/test_kein_sendcodepfad.py` verankert).
  Solange ein Skill-Subprozess mit freiem `python`/`curl` läuft, ist dieser Codepfad grundsätzlich
  umgehbar.
- **Gmail-Zugriff ist datei-, nicht env-basiert:** `gmail_client.py` liest `gmail_credentials.json`/
  `gmail_token.json` direkt aus dem Secrets-Verzeichnis. `_child_env(kind)` (66A) kann diesen
  Zugriff deshalb strukturell NICHT einschränken — jeder Skill-Subprozess läuft als der angemeldete Benutzer und kann
  die Dateien lesen wie jedes andere lokale Programm auch.
- **Optionen dafür, ohne dass Phase 66 sie umsetzt:** Skills schrittweise von freien Python-
  Heredocs auf eine schmale, geprüfte Schnittstelle umstellen (z. B. ein CLI mit fester,
  auditierbarer Befehlsmenge statt beliebigem Code) — das würde `Bash(python:*)` überhaupt erst
  einschränkbar machen, ist aber eine eigene, große Phase, keine Erweiterung dieser Liste.

### Pfad-Wächter für Write/Edit (P2-38)

Anlass war ein Fund vom 11.09.2026: eine Datei `Bewerbung_Mgmt_System_inspect.py` neben dem Projektordner
statt darin, geschrieben von einem headless `cv-match`-Lauf, der beim Zusammenbau des Projektpfads
einen Ordner ausließ und aus einem `/` ein `_` machte. Kein BMS-Code nutzt diesen falschen
Pfad, die KI erzeugt ihn selbst in Hintergrund-Läufen — gemessen 109 von rund 880 geloggten Läufen
seit 13.08. quer durch acht Skills, meist harmlos, aber 18 Write/Edit-Aufrufe landeten tatsächlich
außerhalb des Projekts. Die Freigabeliste oben erlaubte `Write`/`Edit` bis dahin ohne jede
Pfadbeschränkung.

Seither trägt `automation/agent_settings.json` zusätzlich einen `PreToolUse`-Hook
(`automation/pfad_waechter.py`) für `Write`/`Edit`/`MultiEdit`/`NotebookEdit` ein. Der Hook prüft je
Aufruf das Schreibziel gegen die Projektwurzel und bekannte Temp-Ordner (`os.path.commonpath`, kein
Zeichenketten-Präfixvergleich — ein Nachbarordner wie `Bewerbung_Mgmt_System_alt/` zählt NICHT als
„im Projekt") und sperrt alles andere mit Exit-Code 2. **Grenze:** Schreibwege über Bash (ein
Python-Heredoc mit `open(...)`, Shell-Redirect `>`) deckt der Wächter nicht ab — er prüft nur die
vier genannten Werkzeuge; gemessen liefen aber alle 18 Fehlgriffe genau darüber. **Fail-open
bewusst:** Ein Fehler im Wächter selbst (kaputtes JSON, unerwartete Struktur) blockiert nichts,
sondern lässt den Aufruf durch — er ist ein Sicherheitsnetz gegen Fehlgriffe, kein Pflichtweg für
jeden Schreibzugriff. Details: Bau-Spec P2-38.

**Nachwirkendes `cd backend` (P2-53):** Ein `cd` gilt in Claude Code für alle FOLGENDEN Befehle
eines Laufs. Nach einem `cd backend` landete ein relatives `data/tmp/…` deshalb in
`backend/data/tmp/`, und der Lauf suchte seine eigene Datei danach mehrere Schritte lang. Seither
sperrt der Wächter `Write`/`Edit` nach `backend/data/` und prüft über einen zweiten Hook-Eintrag
(Matcher `Bash`) genau EIN Shell-Muster: Arbeitsordner unter `backend/` und ein relatives
`data/tmp` im Befehl. Beginnt der Befehl selbst mit `cd`, prüft er nicht. Die Meldung nennt den
richtigen Ort (`../data/tmp/…` oder den absoluten Pfad). Belegt in einem echten headless-Probelauf:
Die Hook-Eingabe `cwd` enthält den nachwirkenden Arbeitsordner, der Schreibversuch wurde gesperrt.
`HEADLESS_SUFFIX` warnt die Läufe zusätzlich vorab. Alle übrigen Bash-Schreibwege bleiben ungeprüft.

**Zwischendateien (P2-53):** `agent_runner.cleanup_tmp()` löscht in `data/tmp/` und im Fehlgriff-Ort
`backend/data/tmp/` alles, was älter als die Log-Frist ist (`AGENT_LOG_RETENTION_DAYS`, 30 Tage),
beim Serverstart und gedrosselt nach Task-Abschlüssen wie `cleanup_logs()`. Dateien, auf die ein
verfolgtes Pfadfeld der DB zeigt, bleiben (`pipeline.cleanup._alle_referenzen`); ohne lesbare
Verweisliste löscht die Funktion nichts.

### Headless-Authentifizierung vereinheitlicht (Phase 77)

Anlass (07.08.2026): zwei parallel gestartete Beirats-Läufe rissen die geteilte Abo-Session
(Keychain) global ab (Neu-Login nötig), während Runner-Skill-Läufe unberührt durchliefen — Beirat-
Engine und Skill-Runner prüften Auth in unterschiedlicher Reihenfolge. Seit Phase 77 gilt für
beide dieselbe Priorität **Key aus `keys.json` > Runner-Token aus `agent.env` > Keychain-Session**.
Nur im Keychain-Fall läuft vor dem Fan-out einer Beirats-Debatte eine serielle
**Vorwärm-Schleuse** (ein kurzer Mini-Turn hinter einem modulweiten Lock, 5-Minuten-Erfolgscache,
Fehlschläge werden nie gecacht) — sie verhindert, dass mehrere Personas gleichzeitig dieselbe
Session zum ersten Mal anfragen und sie dabei zerschießen.

### Backups

**Automatische Sicherung (P2-52, `app/sicherung.py`):** ein asyncio-Takt im Server (60 s nach dem
Start, danach alle 30 min) legt einmal je Kalendertag eine Sicherung an — SQLite-Online-Backup aus
einer read-only geöffneten Quelle, `PRAGMA integrity_check`, ZIP (`ZIP_DEFLATED`, Level 6),
atomares Umbenennen — nach `data/backups/auto/bewerbung_JJJJ-MM-TT_HHMMSS.zip`. Eigener
Unterordner bewusst: drei bestehende Leser (`cleanup._backup_dateien`, `backup_db.sh --rotate`,
`agent_runner._backup_hinweis`) kennen nur `data/backups/bewerbung_backup_*.sqlite` direkt in
`data/backups/` und dürfen die neue Reihe nicht miterfassen. Aufbewahrung (reine, ohne
Dateizugriff testbare Funktion `zu_entfernen()`): immer die neueste, alle der letzten 24 h, je
Kalendertag die neueste für 7 Tage, je ISO-Woche für 4 Wochen, monatlich einstellbar (Standard
0) — ausgedünnt wird nur NACH einer erfolgreichen neuen Sicherung. Einstellungen in
`data/sicherung.json` (`GET/POST /api/sicherung`, `PATCH /api/sicherung/einstellungen`, Router
`app/routes_sicherung.py`, Karte „Datensicherung" in den Einstellungen); Dashboard-Hinweis bei
Fehlschlag oder wenn die letzte Sicherung bei eingeschalteter Automatik älter als 3 Tage ist.
Reines Python, kein `sqlite3`-CLI-Tool — läuft unverändert unter macOS und Windows. Die
BESTEHENDEN, manuell angelegten Sicherungen unten fasst dieses Modul nie an, es zählt sie nur für
die Statusauskunft.

Vor riskanten Operationen (Dedup-Merges, Migrationen) wird die SQLite-DB gesichert
(`backup_JJJJMMTT_HHMMSS`). Dateien werden nie hart gelöscht, sondern in den zentralen
Papierkorb `data/papierkorb/` verschoben (Phase 32 — gilt für Datei-, Stellen- und
Firmen-Löschen, jeweils mit Bestätigungsdialog; Stellen bleiben als unsichtbare
Dedup-Tombstones erhalten). Gelöschte **Netzwerk-Einträge** (Zielfirmen, Headhunter,
Kontakte) sind seit 18.07. je Tab in einem aufklappbaren Papierkorb-Panel sichtbar und
per Klick wiederherstellbar — bewusst ohne Endgültig-Löschen in der UI, denn die
Tombstones verhindern, dass ein früherer Drive-Import oder der Datei-Import (P2-62) Gelöschtes wiederbelebt. Endgültiges
Leeren gibt es nur manuell über das Cleanup-Kommando (`pipeline/cleanup.py`,
Phase 33: `scan` → `apply` → `leeren`).

**Sicherung zurückspielen (P2-66, `scripts/bms_wiederherstellen.py`):** Standardbibliothek-Werkzeug
wie `bms_update.py`, gestartet über `wiederherstellen.command` (zsh) bzw.
`wiederherstellen_windows.bat` (CRLF, Block in runden Klammern) mit
`--installation <ordner> [--liste] [--datei <name>] [--ja]`. Es nutzt Helfer aus `bms_update`
(`_server_laeuft`, `_data_dir`, `_sperren`/`_entsperren`, `_rueckfrage`, `_pfad_unsicher`,
`_selbsttest_ausfuehren`) und läuft bewusst auch in einer Git-Installation, weil es nur Daten
betrifft. Ablauf: Server-Check (`GET /api/health`, läuft er, Abbruch) → Sperre
`data/updates/.update.lock`, geteilt mit dem Update, sodass sich beide ausschließen →
Kandidaten sammeln (automatische Sicherungen `data/backups/auto/*.zip`, manuelle `*.sqlite`/`*.zip`
direkt in `data/backups`, ZIPs dort nur mit genau `bewerbung.sqlite` als Inhalt, damit Ordner-Sicherungen
anderer Werkzeuge nicht erscheinen; nicht die Update-Sicherungen in `data/updates`, dafür gibt es
`update --zurueck`) → nummerierte Liste, neueste zuerst (`--liste` endet hier) → Auswahl → Prüfung
in einem Temp-Verzeichnis (genau ein Eintrag `bewerbung.sqlite`, SQLite-Header,
`PRAGMA integrity_check`, Tabelle `job`, Selbsttest auf einer Kopie, der eine ältere DB additiv
migriert) → Rückfrage (übersprungen mit `--ja`) → aktuellen Stand sichern als
`data/backups/bewerbung_backup_<JJJJMMTT_HHMMSS>_vor_wiederherstellung.sqlite` (Namensmuster passt
zu `cleanup._backup_dateien`) → Einsetzen über Temp-Datei und `os.replace`, vorhandene
`-wal`/`-shm` werden mit Zeitstempel umbenannt, nicht gelöscht → Protokoll
`data/backups/wiederherstellung_<stempel>.json` (`zeitpunkt`, `quelle`, `quelle_zeitpunkt`,
`sicherung_vorher`, `ergebnis`; in derselben Sekunde mit `_2`, `_3`). Bei einem Fehler nach dem Ersetzen wird die Sicherung vom Beginn
zurückkopiert. Rücknahme ohne eigenen Schalter: Die Sicherung „vor Wiederherstellung“ erscheint
beim nächsten Aufruf in der Liste. Exit-Codes: 0 = OK oder nur Liste, 1 = abgebrochen (Nein,
Server läuft, Sperre belegt, keine Sicherung, Prüfung fehlgeschlagen, `data/` unverändert),
2 = Fehler beim Einsetzen (Ausgangszustand wiederhergestellt), 3 = falscher Aufruf. Nur die
Datenbank wird ersetzt, `outputs/` und Uploads bleiben. **Warum kein Knopf in der App:**
`app/db.py` bindet die Datenbank beim Import in einer einzigen Engine ohne `dispose`/Reinit, ein
Tausch im laufenden Betrieb wäre riskant. Beide Starter und das Skript stehen in
`PFLICHTDATEIEN`, die `.command` in `_STARTDATEIEN_AUSFUEHRBAR` (`pipeline/kundenpaket.py`).

### Beispieldaten einer frischen Paket-Installation (P2-59)

Wer das BMS zum ersten Mal startet, sähe leere Seiten. `app/beispieldaten.py` legt deshalb beim
allerersten Start die erfundene Bewerbungsgeschichte von „Benno Bewerbaer“ an (Postbote, fünf Jahre
Paketzustellung). Die Daten werden beim Start ERZEUGT statt mitgeliefert: Das Update-Werkzeug
schreibt nie nach `data/` und lehnt Pakete mit `data/` oder `config/profil.md` ab.

**Erst-Start-Regel** (`einspielen_falls_neu(db_war_da)`): Angelegt wird nur, wenn ALLES gilt:
(1) die Datenbank-Datei gab es vor dem Start nicht, (2) die Markierung `data/beispieldaten.json`
fehlt (auch „entfernt“ zählt, nie zweimal), (3) die Installation ist ein Paket (`app/version.py`)
oder `BMS_BEISPIELDATEN=1` ist gesetzt (für Tests und die Abnahme; eine Git-Installation
bekommt also nie welche) und (4) die Tabellen `job`, `company`, `email` und `application` sind leer.
Die Funktion wirft nie: Ein Fehler ergibt eine Logzeile und `False`, und weil alle Zeilen in EINER
Transaktion entstehen, bleibt nichts Halbes zurück.

**Startreihenfolge** (`main.py::_startup`): `db_war_da = db.DB_PATH.exists()` VOR `init_db()` (das
legt die Datei an), dann `init_db()`, `suchprofil.sicherstellen()`,
`beispieldaten.einspielen_falls_neu(db_war_da)` (bei `True` folgt `_profil_struktur_schreiben`,
denn Skills und Werdegang fließen in `config/profil_struktur.md`), `agent_runner.start_workers()`
und `sicherung.starten()`. Innerhalb von `einspielen_falls_neu` entstehen erst die Zeilen, dann
`config/profil.md` und `data/cv_basis/base_de.docx` (jede nur, wenn sie noch fehlt, jede einzeln
abgesichert) und zuletzt die Markierung. Scheitert eine Datei, wird die Markierung trotzdem
geschrieben: Ohne sie ließen sich die vorhandenen Zeilen nie wieder entfernen.

**Inhalt:** 6 Firmen (`notes="Beispieldaten"`), 5 Stellen (`dedup_key="beispiel|…"`, je eine in Neu,
Prüfen, Beworben, Interview und Absage, Zeiten relativ zum Start, `url=None`), 3 Bewerbungen, 5 Mails
ohne Gmail-Kennung (Absender unter `*.beispiel.de`, Antwortzeiten gerechnet wie im Mail-Ingest, eine
Mail ohne Stelle zum Ausprobieren des Archivs), 1 Gesprächstermin in 3 Tagen samt Ansprechperson,
1 Netzwerk-Kontakt, 14 Skills und 5 Werdegang-Einträge (`quelle="beispiel"`), die Profilfelder
`headline`/`standort`/`positionierung` (nur, wenn leer), `config/profil.md` im Aufbau der Vorlage von
`pipeline/profil_datei.py` (bis P2-68 stand sie in `BMS_Install.md`) und ein deutscher Basis-CV im v10-Aufbau, den `pipeline/cv_export.py` erwartet.
NICHT angelegt: Suchpläne und Suchbereich (sonst liefe der Tageslauf echte Suchen), Zielfirmen,
Headhunter und CV-Versionen. Firmen und Stellen tragen keine Webadresse, damit kein Hintergrund-Lauf
sie abruft. Der Skill `beworben-check` (Teil des Tageslaufs) filtert Stellen mit `portal`
„Beispieldaten“ aus Prüfmenge und Skip-Check, sonst suchte er die Karriereseiten der erfundenen
Firmen (Wächter `test_beworben_check_laesst_die_beispielstellen_aus`). Alle Texte des Moduls bestehen die Paketprüfung (Mailadressen unter `beispiel.de`, die
Beispielnummer, keine Bestands-IDs), weil sie als String-Konstanten ausgeliefert werden.

**Markierung** `data/beispieldaten.json` (atomar geschrieben): `status` (`vorhanden` oder
`entfernt`), `angelegt_am`, `name`, `ids` (je Tabelle die angelegten Ids, auch `joblog`), `dateien`
(relativer Pfad → SHA-256 der angelegten Datei) und `profil_werte` (die tatsächlich gesetzten
Profilfelder). Nach dem Entfernen steht dort `status="entfernt"` mit `entfernt_am` und `sicherung`,
`ids` und `dateien` sind leer. `GET /api/beispieldaten` macht daraus `status` (`keine`, `vorhanden`,
`entfernt`), `name`, die beiden Zeitpunkte und die Anzahl je Art; die Karte in den Einstellungen und
der Hinweis im Dashboard (nur bei `vorhanden`) lesen es.

**Entfernen** (`POST /api/beispieldaten/entfernen`, `beispieldaten.entfernen()`, ein Lock gegen
doppelten Aufruf):

1. Nur bei `vorhanden`, sonst `ValueError` → 409. Läuft an einer Beispielstelle eine Aufgabe
   (`queued`/`running`), ebenfalls 409: Sie schriebe nach dem Löschen an eine Stelle, die es nicht mehr
   gibt.
2. Sicherung über `app.sicherung.anlegen()`, also in der Reihe der automatischen Sicherungen unter
   `data/backups/auto`, wie „Jetzt sichern“. `SicherungLaeuft` → 409, jeder andere Fehler → 500. In
   beiden Fällen bleibt alles unverändert.
3. Eine Transaktion. Gelöscht wird nur, was Id UND Zweitmerkmal trägt (`_beispiel_bedingungen`:
   `job.dedup_key LIKE 'beispiel|%'`, Firmenname aus der Liste,
   `email.from_addr LIKE '%beispiel.de%'`, `contact.email LIKE '%beispiel.de'`, Netzwerk-Kontakt nach
   Name, bei Skills und Werdegang `quelle = 'beispiel'`). Grund: SQLite vergibt die Id der zuletzt
   gelöschten Zeile erneut. Löschte ein Kunde den letzten Beispiel-Skill von Hand und trüge danach
   einen eigenen ein, bekäme er dieselbe Id. Dazu kommt alles, was an einer Beispielstelle hängt: jede
   Tabelle mit `job_id` außer `email` und `agenttask`, aus `models.py` ermittelt und Kinder zuerst. Mails ohne Beispielmerkmal an
   einer Beispielstelle und Aufgaben (Kosten-Historie im Task-Center) werden gelöst (`job_id` und
   `application_id` leer), nicht gelöscht. Eigene Zeilen mit `company_id` auf eine Beispielfirma
   verlieren nur den Verweis. Die Profilfelder werden nur geleert, solange sie noch den Beispielwerten
   entsprechen. Das ist hartes Löschen ohne Tombstone, anders als „Stelle löschen“ (Phase 32): Die
   Sicherung ist der Rückweg.
4. Dateien erst NACH dem Commit: Scheitert ein Verschieben, bleibt eine Datei liegen statt einer
   Datenbank, die auf Gelöschtes zeigt. `config/profil.md` und der Basis-CV wandern nur in den
   Papierkorb, wenn ihr SHA-256 noch dem angelegten entspricht, sonst bleiben sie und stehen in
   `behalten`. Die Verschiebung ist eine eigene (`data/papierkorb/<JJJJMMTT>_<Name>` (ältere Einträge tragen noch `JJJJ_MM_TT_`)), nicht der
   Helfer der Lösch-Endpunkte: Der lässt nur die Ordner der Positivliste zu, die Profil-Datei liegt in
   `config/`. Auch die Artefakte, die ein Kunde an einer Beispielstelle erzeugt hat (Pfadspalten
   `*_path` der gelöschten Zeilen), wandern in den Papierkorb, geprüft von `_artefaktpfad_pruefen`:
   nur Dateien unter `data/` und `outputs/` (der aufgelöste Pfad zählt), nie `data/papierkorb/`,
   `data/backups/`, die Datenbank oder die Basis-CVs.
5. Markierung auf `entfernt`. Der Router schreibt danach `config/profil_struktur.md` neu
   (`_profil_struktur_schreiben`, funktionslokal importiert) und antwortet mit `entfernt` (Anzahl je
   Art), `geloest` (Mails, Aufgaben), `behalten`, `sicherung` und `status`. Die Oberfläche löst
   danach `PROFIL_GEAENDERT` aus.

Nach dem Entfernen zeigt die Seitenleiste den Rückfallnamen „Bewerber“ (`user_profile.user_name()`),
bis eine eigene `config/profil.md` mit Namen existiert (seit P2-69 legt sie die Karte „Identität und
Suchstrategie“ an, s. den nächsten Abschnitt). Der LinkedIn-Import (`pipeline/linkedin_import.py`)
füllt Profilfelder nur, wenn sie leer sind, und überspringt Skills und Werdegang-Einträge, die es
schon gibt, unabhängig von `quelle`. Mit Beispieldaten im Profil übernähme er die eigene Positionierung
also nicht; deshalb gilt in der Kundendoku „erst Beispieldaten entfernen, dann importieren“. Tests:
`tests/test_beispieldaten.py` (Bedingungen, Inhalt, Basis-CV, Entfernen, Router und der Erst-Start
im Subprozess nach dem Muster von `tests/test_neuinstallation.py`).

### Profil-Datei: Maske „Identität und Suchstrategie“ (P2-69)

Bis P2-68 legte der Kunde `config/profil.md` von Hand im Texteditor an, und es kam auf die Schreibweise
`**Name:**` an. Kein Endpunkt schrieb die Datei. Angefasst haben sie nur `app/beispieldaten.py` (legt die
Beispiel-Datei an und entfernt sie wieder) und der Skill `absagen-analyse` (ersetzt den Abschnitt
`## Empirie aus dem Bewerbungsverlauf`). Seit P2-69 liest und schreibt die erste Karte der Profil-Seite,
„Identität und Suchstrategie“ (`components/ProfilIdentitaet.tsx`), die Datei. Die Datei bleibt die
einzige Quelle, Leser und Skills ändern sich nicht. Die Verträge F (Format), A (API), O (Oberfläche)
und D (Doku) stehen in der Bau-Spec P2-69.

**Module.** `pipeline/profil_datei.py` (Vertrag F: reine Funktionen für Zerlegen und Zusammensetzen
plus `lesen()` und `schreiben()`, kein Import aus `app`) und `app/routes_profil_identitaet.py` (Vertrag A,
Router wie `routes_sicherung.py`, in `main.py` nur Import und `include_router`). Der Leser
`pipeline/user_profile.py` bleibt unverändert: Er liest Name, Standort, Kontakt und LinkedIn per Regex
(daraus Briefkopf, Dateinamen, Seitenleiste und Startpunkt der Routenplanung), und die Maske erzeugt
genau die Schreibweise `- **Name:** …`, die diese Regexe erwarten. Den Pfad liest `profil_datei` zur
Laufzeit aus `user_profile._PROFIL_MD`, damit Tests ihn mit demselben Patch umlenken wie bisher.

**Verlustfreie Zerlegung.** Die Maske ändert nur, was sie anzeigt. Alles andere bleibt Byte für Byte
gleich: unbekannte Abschnitte, unbekannte Zeilen in bekannten Abschnitten, `Sprachen / CV-Fassungen`,
die Empirie, Leerzeilen, Zeilenenden (LF oder CRLF) und der Dateikopf. Einzige Ausnahme im Kopf: Die Titelzeile `# Kandidatenprofil: <Name>` zieht mit, wenn der Name in der Maske geändert wird und die Zeile genau den bisherigen Namen trägt. Speichern ohne Änderung in der
Maske ergibt exakt dieselbe Datei.

- Zerlegt wird in den Kopf (alles vor der ersten Zeile `## `) und die Abschnitte. Erkannt werden sie am
  Überschriftentext (getrimmt, ohne Rücksicht auf Groß-/Kleinschreibung, „beginnt mit“): `Identität`
  (Feldzeilen: Name, Positionierung, Standort als „Anschrift“, Kontakt als E-Mail und Telefon,
  LinkedIn, Aktuell; weitere Feldzeilen als `weitere` mit editierbarem Wert), `Kurzprofil`,
  `Harte Rahmenbedingungen` und `Bekannte Skill-Gaps` (jeweils Freitext) sowie aus `Zielrolle` nur die
  Zeile `Zieltermin`. Ältere Zeilen wie Ebene oder Branche bleiben unberührt in der Datei, Titel, Ebene und
  Branche kommen aus den Suchplänen. Alle anderen Abschnitte bleiben unverändert, die API meldet nur ihre Überschrift
  (`unveraendert`).
- Eine Feldzeile ist `^(\s*[-*]\s*)\*\*(.+?):\*\*[ \t]*(.*)$`. Beim Ändern wird nur der Wert
  ersetzt, Einrückung, Aufzählungszeichen und Schlüssel bleiben. Ein neues Feld kommt hinter die letzte
  Feldzeile des Abschnitts. Ein vorhandenes Feld mit leerem Wert behält seine Zeile, nur bei den
  optionalen Feldern Positionierung, LinkedIn und Aktuell entfällt sie. Ein neues Feld mit leerem Wert
  wird nicht angelegt.
- Kontakt: Beim Lesen wird an `·` oder `|` geteilt, der erste Teil mit `@` ist die E-Mail, der Rest
  (mit ` · ` verbunden) das Telefon. Geschrieben wird `E-Mail · Telefon`, bei nur einem Wert ohne
  Trenner.
- Freitext-Abschnitte gehen ohne die Leerzeilen an Anfang und Ende an die Maske. Beim Schreiben bleibt
  die bisherige Zahl der Leerzeilen vor und nach dem Rumpf erhalten, ein unveränderter Text lässt den
  Abschnitt bytegleich. Neue Zeilen erhalten das in der Datei vorherrschende Zeilenende.
- Fehlt die Datei, liefert `lesen()` `vorhanden=False`, leere Werte und den Zieltermin, und `schreiben()` erzeugt die Vorlage (Aufbau wie in `beispieldaten._profil_md_text()`,
  mit den Abschnitten Identität, Kurzprofil, Zielrolle, Harte Rahmenbedingungen, Sprachen /
  CV-Fassungen, Bekannte Skill-Gaps / Red Flags und Empirie). Fehlt in einer vorhandenen Datei ein
  bekannter Abschnitt, legt `schreiben()` ihn nur an, wenn die Maske Inhalt liefert, vor der Empirie
  oder sonst am Dateiende.

**Schreiben und Prüfungen.** `schreiben()` ersetzt atomar (Temp-Datei im selben Ordner, `os.replace`,
UTF-8). Vorher geht eine Kopie der alten Datei in den Papierkorb `data/papierkorb/` (Datumspräfix
`JJJJMMTT_` wie bei `_freier_name`); nichts wird hart gelöscht. Ein `ValueError` mit Kundentext (Sie-Form)
meldet: Name fehlt (Pflicht), Zeilenumbruch in einem einzeiligen Feld, Länge über 300 Zeichen (einzeilig)
bzw. 5000 (Freitext), ein Schlüssel in `weitere` oder `zielrolle`, den es weder in der Datei noch unter
den Standard-Schlüsseln gibt, und eine Freitext-Zeile, die mit `## ` beginnt (sie würde einen neuen
Abschnitt anlegen). Nicht blockierende `hinweise`: Die Anschrift hat kein Komma oder keine Postleitzahl
(die Ortszeile der Anschreiben entsteht aus `Straße Nr, PLZ Ort`), oder die E-Mail hat kein `@`.

**API** (`GET/PUT /api/profil/identitaet`). Die Antwort trägt `vorhanden`, `stand`, `identitaet`
(`name`, `positionierung`, `anschrift`, `email`, `telefon`, `linkedin`, `aktuell`, `weitere`),
`kurzprofil`, `zielrolle` (Liste aus `schluessel` und `wert`), `rahmenbedingungen`, `skill_gaps`,
`unveraendert` und `hinweise`. `stand` ist der SHA-256 des Dateiinhalts, leer bei fehlender Datei. Das
PUT nimmt denselben Aufbau mit `stand` entgegen. Ein veralteter `stand` ergibt 409 („Die Profil-Datei
wurde inzwischen geändert. …“) und lässt die Datei unverändert: Zwischen Laden und Speichern kann ein
Skill die Empirie ersetzt haben, und das darf die Karte nicht stillschweigend überschreiben. Ein
`ValueError` ergibt 400 mit dem Text im `detail`. Bei Erfolg antwortet das PUT in der Form des GET
(frisch gelesen) plus `papierkorb` (Pfad der Sicherungskopie oder `null`).

**Herkunftsprüfung.** Das PUT ist ein schreibender Aufruf und fällt unter die Herkunftsprüfung (fremde
Anfragen bekommen 403); der Wächter-Test in `test_herkunftspruefung.py` zählt die Route über
`app.openapi()` selbst mit. Eine Lizenzsperre gibt es seit P2-82 nicht mehr.

**Oberfläche.** Nach „✓ Gespeichert“ löst die Karte `PROFIL_GEAENDERT` aus (Seitenleiste und
Routenplanung laden neu). `hinweise` erscheinen als amber Zeilen, 400 zeigt den Text, 409 den Text mit
dem Knopf „Neu laden“. Wer die Datei in der Karte speichert, ändert
ihren SHA-256: „Beispieldaten entfernen“ behandelt sie dann als eigene Fassung und lässt sie stehen
(`behalten`).

**Tests.** `tests/test_profil_datei.py` (Rundweg bytegleich für Vorlage, Beispiel-Datei und eine
umfangreiche erfundene Datei einschließlich CRLF und fehlendem Zeilenende am Schluss, Zeilen-Diff bei
geänderten Feldern, Kontakt, optionale Felder, alle Prüfungen und Hinweise, atomares Schreiben,
Papierkorb-Kopie) und `tests/test_profil_identitaet_api.py` (GET ohne Datei, PUT legt an, 409, 400,
Speichern ohne Lizenzdatei). Alle Pfade liegen unter `tmp_path`.

### Dateiauslieferung: nur Dokumente, nur aus `frontend/dist` (P2-54)

Der Server liefert Dateien an genau zwei Stellen aus. `GET /api/artifact` gibt nur Dateien aus den
Ordnern der Positivliste `_ARTEFAKT_ORDNER` in `main.py` heraus, und dort nur die Dateitypen, die
die Oberfläche öffnet: Berichte (`.html`) aus `company_fit`, `job_postings`, `interview_prep`,
`beirat`, `analysen` und `transcripts` (dort auch `.md`), Upload-Typen aus `job_files` und
`profil/dateien`, Word/PDF aus `cv_basis`, `tmp` (registrierte CV-Entwürfe), `outputs/cv`,
`outputs/cv_entwuerfe` und `outputs/anschreiben`. Alles andere liefert 403, auch wenn die Datei
existiert: Datenbank, Sicherungen, Updates, `sicherung.json`, Rohdaten, Papierkorb. Geprüft wird
der aufgelöste Pfad (`..`, Symlinks, Backslashes), und zwar vor der Existenz. **Wer einen neuen
Ordner für Artefakte einführt, muss ihn dort eintragen**, sonst bleibt er unerreichbar. Der
SPA-Fallback (`main.spa`) liefert nur Dateien innerhalb von `frontend/dist`, alles andere bekommt
`index.html`. Bis P2-54 gingen dort `%2e%2e`- und `%2F`-Pfade durch, also jede lesbare Datei des
Rechners. Der LAN-Modus bleibt trotzdem ohne Anmeldung: Oberfläche und API sind im Netz offen, nur
ganze Datenbanken, Sicherungen und fremde Dateien lassen sich nicht mehr abrufen.
`GET /api/doku/{name}` (P2-59) gehört nicht dazu: Es liefert keine Datei, sondern die Seite zu
einem Eintrag aus einem festen Katalog, der Name aus der Adresse wird nie als Pfad benutzt (s.
„Dokumentationsseite“ unten).

### Keine Freigabe für fremde Webseiten (CORS, P2-55)

Das Backend sendet keinen `Access-Control-Allow-Origin`-Header. Eine fremde Webseite im selben
Browser bekommt die Antworten der API deshalb nicht zu sehen, und Anfragen, die einen Preflight
brauchen (JSON-Inhalt, PATCH, DELETE), schickt der Browser gar nicht erst ab. Die eigenen Aufrufer
brauchen keine Freigabe: Die Oberfläche kommt vom selben Server, auch im LAN-Modus unter
`http://<name>.local:8000`; der Vite-Dev-Server leitet `/api` per Proxy weiter; Skills und Skripte
nutzen curl oder Python, für die CORS nicht gilt. Bis P2-55 stand in `main.py` eine
`CORSMiddleware` mit `allow_origins=["*"]` und allen Methoden: Jede Webseite konnte Stellen, Mails
und Profil lesen, KI-Läufe starten und Stellen löschen, sogar eine lokal geöffnete HTML-Datei
(`Origin: null`). **Wer eine Herkunft freigeben muss, trägt sie einzeln ein, nie `*`**, und passt
`tests/test_keine_cors_freigabe.py` an. Was CORS nie geschützt hat, fängt seit P2-57 die
Herkunftsprüfung ab (nächster Abschnitt): Einfache Anfragen ohne Preflight (POST ohne Inhalt, als
Formular oder Upload) schickt der Browser trotzdem ab, nur die Antwort bleibt der fremden Seite
verborgen.

### Herkunfts- und Host-Prüfung (P2-57)

Vor jeder Route prüft die Middleware `_Herkunftspruefung` in `main.py` zwei Dinge, bei einem
Verstoß antwortet sie mit 403 und einer Meldung in `detail`.

**Host (jede Anfrage, auch Oberfläche und Assets):** Der Server antwortet nur unter einer
IP-Adresse, `localhost`, einem Namen auf `.local` oder einem Rechnernamen ohne Punkt. Diese Namen
kann eine fremde Domain nicht per DNS-Rebinding vortäuschen: Stellt sie ihren DNS-Eintrag nach
dem Laden auf `127.0.0.1` um, ist ihre Seite für den Browser derselbe Ursprung und läse die API
ohne jede CORS-Freigabe, im lokalen wie im LAN-Modus. Die Adressen, die `start_lan.command`
anzeigt, gehen immer. Weitere Namen (Router-Name wie `mac.fritz.box`, Tailscale, Reverse-Proxy)
gibt die Umgebungsvariable **`BMS_HOSTS`** frei, getrennt durch Komma oder Leerzeichen: am Mac
im Terminal `BMS_HOSTS=mac.fritz.box ./start_lan.command` (per Doppelklick im Finder kommt keine
Umgebungsvariable an), unter Windows `set BMS_HOSTS=mac.fritz.box` in derselben
Eingabeaufforderung vor dem Start.

**Origin (alles außer GET, HEAD, OPTIONS):** Schickt der Browser einen `Origin`, müssen Host und
Port zum `Host`-Header passen. Das Schema zählt nicht, und ein fehlender Port gilt als
Standardport des Origin-Schemas, damit ein Proxy mit TLS davor funktioniert. `Origin: null`
(lokal geöffnete HTML-Datei, Sandbox-iframe, seit P2-58 jeder Bericht) ist gesperrt. Ohne
`Origin` (curl, Skills, Skripte, Python) geht die Anfrage durch. Einzige Ausnahme ist
`http://localhost:5173`, der Vite-Dev-Server über seinen Proxy: nur an Host `localhost` (darauf
schreibt der Proxy den Host um) und nur mit `Sec-Fetch-Site: same-origin` oder ohne diesen Header.
Ein anderes Projekt auf Port 5173, das den Server direkt anspricht, meldet `same-site`; an einen
`.local`-Namen oder eine LAN-IP schicken Browser gar kein `Sec-Fetch-Site`, deshalb die Bindung an
`localhost`. **Der Port 5173 gehört zur Ausnahme:** `vite.config.ts` setzt `strictPort`, damit
Vite bei belegtem Port abbricht, statt still auf 5174 auszuweichen (dann bekäme jeder
Schreibzugriff 403).

Bis P2-57 konnte jede Webseite 21 Routen blind auslösen, darunter `discard` (jede Stelle auf
„Kein Match"), den Basis-CV mit `overwrite` ersetzen, den ZIP-Import (Lauf `skills-sortieren`),
`POST /api/sicherung` und die Verbindungstests für Coach-Site und Mail. Hinter einem
Reverse-Proxy muss dieser den Host-Header samt Port durchreichen (Caddy tut das von sich aus,
nginx braucht `proxy_set_header Host $http_host;`), und sein Name gehört in `BMS_HOSTS`.
Restrisiko: Wer im selben Netz mDNS- oder LLMNR-Antworten fälscht, kann über einen `.local`- oder
punktlosen Namen weiter umbiegen; im LAN-Modus hat so jemand ohnehin direkten Zugriff. Vertrag:
`tests/test_herkunftspruefung.py`, mit einem Wächter über alle Operationen aus dem
OpenAPI-Schema. Die Lizenzprüfung, die von P2-67 bis 1.7.0 innerhalb dieser Prüfung saß (402), ist
seit P2-82 ausgebaut (Abschnitt „Lizenz — ausgebaut“).

### Berichte in der Sandbox (P2-58)

HTML-Berichte aus `/api/artifact` und der Tages-Digest (`/api/digest`) tragen den Header
`Content-Security-Policy: sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox`
(`_BERICHT_SANDBOX` in `main.py`). Der Browser gibt ihnen damit einen eigenen, undurchsichtigen
Ursprung (`null`) statt dem der API. Ein Skript in einem Bericht, etwa über eine Prompt-Injection
aus Webinhalten, die ein KI-Lauf übernommen hat, erreicht die API dann nicht mehr: Lesen scheitert
an der fehlenden CORS-Freigabe (P2-55), Schreiben an der Herkunftsprüfung (`Origin: null` → 403,
P2-57). Bis P2-58 lief so ein Skript im Ursprung der API, las Stellen, Mails und Profil und schrieb
mit passendem Origin an der Prüfung vorbei; im Browser nachgestellt verwarf ein Probebericht eine
Stelle. Dazu kommt `Cache-Control: no-cache` (beides in `_BERICHT_KOPF`): Ohne ihn zeigte Chrome
einen früher geöffneten Bericht mit den alten Headern aus dem Cache, also ohne Sandbox.

Weiter gehen (in Chrome 154 gemessen): Skripte (71 ältere Berichte bis 08.08.2026 bauen ihren
Inhalt per Skript auf), Links in neuen Tabs (diese Tabs sind normale Seiten, dafür
`allow-popups-to-escape-sandbox`), Links im selben Tab, Drucken über das Browsermenü und das
eingebettete Favicon. Nicht mehr gehen, von keinem Bericht genutzt: Formulare, `alert` und
`confirm`, `window.print()` aus einem Skript (bräuchte `allow-modals`), `localStorage`, Cookies,
Schriften oder Daten per `fetch` vom BMS-Server (beides braucht CORS). **Wer so etwas in einen
Bericht einbaut, braucht eine eigene Freigabe; `allow-same-origin` nie**, es höbe den Schutz auf.
PDF, Bilder, Word und Downloads (`download=true`) bleiben ohne Header, ebenso die Oberfläche selbst
(`index.html`, `/assets`). Eine neue HTML-Route setzt `_BERICHT_KOPF`; ein Wächter in
`tests/test_bericht_sandbox.py` meldet jede `HTMLResponse` außerhalb von `artifact`, `digest` und
(seit P2-59) `routes_doku.dokument`, der Dokumentationsseite (nächster Abschnitt).
Restrisiken: Ein eingeschleustes Skript kann den Inhalt seines eigenen Berichts weiter nach außen
schicken oder die Seite umleiten. Berichte, die der Browser schon vor P2-58 zwischengespeichert
hat, kommen bis zum Ablauf ihrer Cache-Frist (bei älteren Berichten gut eine Woche) noch ohne
Sandbox; Neuladen (Cmd+R) oder einmal den Browser-Cache leeren behebt das. Bestandsaufnahme und
Messungen: Bau-Spec P2-58.

### Dokumentationsseite (P2-59)

Die Seite `/dokumentation` (Menüpunkt „📖 Dokumentation“, `frontend/src/pages/Dokumentation.tsx`)
zeigt die Dokumente der Installation in Reitern, ohne eigenen Markdown-Renderer im Frontend: Das
Backend rendert sie mit demselben Renderer wie die `docs/*.html`-Zwillinge
(`pipeline/docs_render.py`), die Seite zeigt das Ergebnis in einem Rahmen (`iframe`).

**Katalog statt Ordner-Scan** (`app/doku.py::KATALOG`, die Reihenfolge ist die der Reiter). Je
Eintrag Kennung, Titel, Gruppe und Datei relativ zum Projekt-Root. Gruppe `kunde`: `version`
(`CHANGELOG.md`), `funktionen` (`docs/FUNKTIONEN.md`), `anleitung`, `installation` (die Datei des
laufenden Systems: `BMS_Install_Windows.md` unter Windows, sonst `BMS_Install_MAC.md`), `email`
(SETUP-EMAIL), `windows` (SETUP-WINDOWS), `coach-site` (ANLEITUNG_COACH_SITE), `beirat`
(BEIRAT-CHARTA); der frühere Reiter `lizenz` entfiel mit P2-82. Gruppe `intern`: `technik` (diese Datei), `automatik`, `release` und
`entwicklung` (`docs/INSTALLATION.md`). `verfuegbar()` lässt jeden Eintrag weg, dessen Datei fehlt:
Das Kundenpaket enthält die internen Dateien nicht, ihre Reiter fehlen dort also von selbst, ohne eine
Kennung der Installationsart. Nicht im Katalog stehen COACH_SITE, GMAIL-STRATEGIE, WAS_IST_NEU und
BEIRAT-PERSONA-TEMPLATE (die Vorlage wird ausgeliefert, hat aber keinen Reiter).

`eintrag_fuer(name)` löst eine Kennung (ohne Punkt) oder einen Dateinamen (`.md` oder `.html`, ohne
Unterscheidung von Groß- und Kleinschreibung, nur ASCII) ausschließlich gegen den Katalog auf: Der Name
aus der Adresse wird nie als Pfad benutzt, alles andere ist unbekannt (auch `..`, Schrägstriche und
Namen, die es als Datei gibt, aber nicht im Katalog stehen). Dateinamen sind erlaubt, damit relative
Links zwischen gerenderten Dokumenten laufen: `SETUP-EMAIL.html` löst unter `/api/doku/…` zu
`/api/doku/SETUP-EMAIL.html` auf, in einer direkt geöffneten `docs/*.html` zeigt derselbe Link auf die
Nachbardatei. Die beiden Anleitungen `BMS_Install_MAC.md` und `BMS_Install_Windows.md` (je `.md` und
`.html`) lösen beide auf den Reiter `installation` auf, auch wenn der Reiter nur die Datei des
laufenden Systems zeigt; die früheren Namen `BMS_Install.md` und `BMS_Install_Auto.md` kennt die
Auflösung seit P2-71 nicht mehr. `rendern()` liest nur Katalogeinträge (sonst `ValueError`), blendet im CHANGELOG einen
leeren Abschnitt „Unveröffentlicht“ aus (er bliebe nach jeder Freigabe als leere Karte an erster
Stelle stehen, und genau die sähe jeder Kunde zuerst) und setzt an jeden Link auf eine Webadresse
`target="_blank" rel="noopener noreferrer"`, sonst lüde ein Klick die fremde Seite in den Rahmen,
und viele Seiten verbieten das.

**Router** (`app/routes_doku.py`, Präfix `/api`): `GET /api/doku` liefert `[{id, titel, gruppe}]` der
vorhandenen Dokumente, `GET /api/doku/{name}` die gerenderte Seite als `HTMLResponse` mit
`_BERICHT_KOPF` (Sandbox und `no-cache`, P2-58; funktionslokal aus `app.main` importiert, oben im
Modul wäre es ein Zirkelimport, so bleibt der Kopf eine Quelle). Unbekannt oder nicht lesbar: 404
„Dokument nicht gefunden“.

**Rahmen mit Sandbox:** Die Seite steht in einem Rahmen mit
`sandbox="allow-popups allow-popups-to-escape-sandbox"`, also weder mit `allow-scripts` noch mit
`allow-same-origin`. Mit dem Kopf (`allow-scripts allow-popups …`) gilt die Schnittmenge: Im Rahmen
läuft kein Skript, das Dokument hat einen eigenen Ursprung und erreicht die API nicht, und ein Link auf
eine Webseite öffnet in einem normalen neuen Tab. „In neuem Tab öffnen ↗“ lädt dieselbe Adresse
direkt, dort gilt nur der Kopf. **Die Rechte nicht erweitern:** `allow-same-origin` zusammen mit
Skripten höbe die Sandbox auf, und `tests/test_doku.py::test_rahmen_der_oberflaeche_bleibt_in_der_sandbox`
hält die Liste auf genau diese zwei Rechte fest. Im Reiter „Version“ steht über dem Rahmen
„Installiert: Version …“ aus `GET /api/version`, bei einer Git-Installation daneben klein der
Entwicklungsstand. Beim Reiterwechsel entsteht ein neuer Rahmen (`key`), sonst bekäme der
Browserverlauf je Wechsel einen Eintrag.

**Wächter:** `tests/test_bericht_sandbox.py::test_waechter_html_nur_aus_artifact_digest_und_doku`
erwartet genau drei HTML-Auslieferungen mit `headers=` (`artifact`, `digest`, `routes_doku.dokument`);
eine vierte ohne Sandbox-Kopf lässt ihn scheitern. `tests/test_doku.py` deckt den Rest ab: Katalog
gegen `pipeline.kundenpaket`, Auflösung samt Fremdnamen, Rendern, Router, Rahmen und die Einbindung
in die echte App.

**Im Kundenpaket:** `pipeline/kundenpaket.py::DOKU_ERLAUBT` ist die Positivliste der ausgelieferten
`docs/`-Dokumente (je `.md` und `.html`): ANLEITUNG, ANLEITUNG_COACH_SITE, BEIRAT-CHARTA,
BEIRAT-PERSONA-TEMPLATE, FUNKTIONEN, SETUP-EMAIL und SETUP-WINDOWS. Dazu kommen im Paket-Root
`BMS_Install_MAC.md`, `BMS_Install_Windows.md` und `CHANGELOG.md`. `docs/FUNKTIONEN.md` ist die Kurzübersicht der Funktionen nach
Arbeitsschritten, ohne Phasennummern, und steht zusätzlich in `PFLICHTDATEIEN`: Fehlt sie im fertigen
Paket, ist das Paket kaputt, denn der Reiter „Funktionen“ fehlte.

### Netzwerk-Import: Listen aus einer Datei (P2-62)

Zielfirmen, Headhunter und Netzwerk-Kontakte lassen sich jederzeit aus einer Datei anlegen: Knopf „⇪ Aus
Datei importieren“ in allen drei Reitern der Seite Netzwerk. Vorgaben vom 01.10.2026: CSV und Excel
(`.xlsx`) mit Vorlage je Liste, dazu der LinkedIn-Export `Connections.csv` (nur Netzwerk-Kontakte);
bestehende Einträge werden nur in leeren Feldern ergänzt und nie überschrieben, in der App gelöschte
bleiben gelöscht. Das ist die Regel der früheren Einmal-Migration aus Excel (Phase 22, das Werkzeug ist entfernt; Prinzip 4
in §3: Dedup lebt von behaltenen Rows). Das Modul importiert kein internes Skript (ein Test hält das fest). Spec: P2-62.

**Bausteine:** `app/netzwerk_import.py` (der Kern, kennt kein FastAPI und wirft `ImportFehler(status,
text)`), `app/routes_netzwerk_import.py` (Router mit Präfix `/api`: liest die Datei mit der Grenze von 5 MB,
bevor geparst wird, und übersetzt `ImportFehler` in `HTTPException`; die Routen sind synchron und laufen im
Threadpool, Parsen, Sicherung und Schreiben blockieren den Event-Loop also nicht), die Einbindung in
`main.py` (`include_router`), die Oberfläche (s. unten) und `tests/test_netzwerk_import.py`. Der Kern
bietet drei öffentliche Funktionen: `vorlage(liste, format)`, `vorschau(liste, dateiname, inhalt, *,
session)` und `importieren(liste, dateiname, inhalt, *, session, daten_dir=None)`.

**Endpunkte** (`{liste}` ist `zielfirmen`, `headhunter` oder `kontakte`, sonst 404; Fehler kommen als
`{"detail": <Kundentext>}`):

- `GET /api/netzwerk-import/{liste}/vorlage?format=csv` (oder `xlsx`, ohne Angabe `csv`): die Vorlage zum
  Herunterladen (`Content-Disposition: attachment`, Dateiname `Vorlage_Zielfirmen.csv`,
  `Vorlage_Headhunter.xlsx`, `Vorlage_Netzwerk-Kontakte.csv` usw.). Sie enthält nur die Kopfzeile mit den
  deutschen Spaltennamen, die Pflichtspalte zuerst. CSV mit Semikolon und UTF-8 mit BOM (so zeigt Excel im
  deutschen Raum die Umlaute richtig); XLSX mit dem Blatt der Liste (Kopfzeile fett und fixiert) und einem
  zweiten Blatt „Hinweise“ (je Spalte Pflicht, erlaubte Werte und Formate, weitere erkannte Namen).
  Unbekanntes `format`: 422.
- `POST /api/netzwerk-import/{liste}/vorschau` (Multipart-Feld `datei`): liest und plant, schreibt NICHTS
  (keine Datenbankänderung, keine Sicherung). Antwort: `liste`, `format` (`csv`, `xlsx` oder `linkedin`),
  `blatt` (nur bei Excel), `spalten` (`erkannt` mit `spalte`, `feld`, `label`; `ignoriert`), `anzahl`
  (`zeilen`, `neu`, `ergaenzt`, `unveraendert`, `geloescht`, `fehler`), `zeilen` (`nr`, `aktion`, `anzeige`,
  `felder_ergaenzt`, `meldung`), `zeilen_gekuerzt` und `hinweise`. `nr` ist die Zeilennummer in der Datei,
  die Kopfzeile mitgezählt. `zeilen` enthält alle Fehler- und Gelöscht-Zeilen plus die ersten 100 übrigen
  (`ZEILEN_UEBRIGE`) in Dateireihenfolge.
- `POST /api/netzwerk-import/{liste}` (Multipart-Feld `datei`): plant neu (die Datei kommt noch einmal, der
  Server merkt sich nichts zwischen den Schritten), sichert und schreibt. Antwort: `{"anzahl": {…wie bei
  der Vorschau…}, "sicherung": <Dateiname> oder null}`.

**Fehlercodes** (Vorschau und Import): 413, wenn die Datei über 5 MB liegt (`MAX_BYTES`; der Router prüft
`UploadFile.size` und liest höchstens 5 MB plus ein Byte, `_einlesen` prüft für Direktaufrufe noch einmal).
400 bei fehlender Datei im Feld, Endung außer `.csv`, `.txt` und `.xlsx` (`.xls` mit dem Hinweis, als
`.xlsx` oder `.csv` zu speichern), leerer oder unlesbarer Datei (Binärdaten als CSV; kaputte Excel-Datei;
entpackt über 200 MB, Schutz vor Zip-Bomben), fehlender Kopfzeile, fehlender Pflichtspalte
(`Liste.spalte_fehlt`, etwa „Keine Spalte für die Firma gefunden. Erwartet wird zum Beispiel „Firma“.“)
und mehr als 5.000 Datenzeilen (`MAX_ZEILEN`, ohne Kopfzeile und Leerzeilen). 404 bei unbekannter Liste.
409 nur beim Import: Es läuft gerade eine Sicherung, oder die Datenbank ist belegt. 422 bei unbekanntem
`format` der Vorlage. 500, wenn die Sicherung scheitert („Die Sicherung vor dem Import ist fehlgeschlagen,
es wurde nichts importiert. Grund: …“) oder das Schreiben scheitert („Der Import ist fehlgeschlagen, es
wurde nichts importiert. Grund: …“); in beiden Fällen ist nichts geändert.

**Konfiguration je Liste** (`LISTEN`, EINE Tabelle statt Verzweigungen): Je Liste ein `Liste` (frozen
dataclass) mit Modell, Feldern, Blattnamen, Schlüsselfeldern, Pflichtspalten und Pflichtwerten, Anzeige,
Fehlertexten und Standardwerten für neue Einträge (`standard_neu`: bei Zielfirmen `last_update` = heute);
je Feld ein `Feld` mit Vorlagenname, Synonymen, Hinweistext, Normalisierer (`norm`), `in_vorlage`,
`modellfeld` und `nicht_gleich`. Aus dieser einen Tabelle entstehen im Backend die Spaltenerkennung, die
Vorlagen (CSV und das Blatt „Hinweise“), die Planung und die Anzeige der Vorschau, eine zweite Liste, die
auseinanderlaufen könnte, gibt es dort nicht. Hilfsfelder (`modellfeld=False`: Vorname, Nachname und die drei LinkedIn-Spalten)
werden vor dem Planen aufgelöst und nie ins Modell geschrieben. Der Schlüssel ist derselbe wie bei den
Anlege-Endpunkten in `main.py` (`app.normalize.slug_parts`): Zielfirma `company`, Headhunter `firma` und
`ansprechpartner`, Kontakt `name` und `unternehmen`. Ein importierter und ein von Hand angelegter Eintrag
können so nie nebeneinander stehen. Der Abgleich ist wörtlich nach `slug_parts` (klein, nur `a-z0-9`), ein
unscharfer wie im Job-Ingest (Rechtsformzusätze, P2-39) findet nicht statt: „Muster“ und „Muster GmbH“
sind zwei Einträge.

**Formate** (`_einlesen`, geprüft wird in dieser Reihenfolge: Größe, Endung, leer):
- **CSV und TXT:** UTF-8 mit oder ohne BOM, UTF-16 mit BOM (Excel „Unicode-Text“), sonst cp1252, im Notfall
  latin-1. Das Trennzeichen entscheidet `_trennzeichen` an der Kopfzeile: `csv.Sniffer` zählt nur, wenn
  sein Ergebnis dort mindestens so oft vorkommt wie jedes andere, sonst gilt das häufigste von `;`, `,`
  und Tab (bei Gleichstand das Semikolon). Die Zeilennummer ist der laufende Datensatz, so zählt auch
  Excel.
- **XLSX** (`openpyxl`, `read_only=True`, `data_only=True`): Die Blattwahl nimmt den ersten Namen aus
  `Liste.blaetter` (Zielfirmen: „Zielfirmen“, „Target Companies“; Headhunter: „Headhunter“, „Headhunters“;
  Kontakte: „Netzwerk“, „Netzwerk-Kontakte“, „Network Contacts“, „Kontakte“; verglichen über denselben
  Schlüssel wie die Spalten), sonst das erste Blatt, und hängt bei mehreren Blättern einen Hinweis an. Der
  Rang der Namen entscheidet, nicht die Reihenfolge in der Datei: Der Excel-Export der App hat vor
  „Netzwerk“ ein Blatt „Kontakte“ (die Stellen-Kontakte), das hier nicht gemeint ist. `reset_dimensions()`
  schützt vor Dateien mit falscher Dimensionsangabe (manche Programme schreiben „A1“ und schnitten sonst
  Zeilen ab). Kopfzeile ist die erste Zeile mit Inhalt.
- **LinkedIn** (nur Liste `kontakte`, CSV oder `.xlsx`): `Connections.csv` hat Hinweiszeilen („Notes: …“) vor der
  Kopfzeile. Kopfzeile ist die erste Zeile mit „First Name“ und „Last Name“ unter den ersten 30 nicht
  leeren (`_KOPF_SUCHE`); als `linkedin` gilt die Datei, wenn zusätzlich „Connected On“ oder „URL“ in der
  Kopfzeile steht. Abgebildet werden Name (Vorname plus Nachname), Unternehmen („Company“), Rolle
  („Position“), Kanal „LinkedIn“ (nur bei leerer Kanalzelle) und Notizen aus „LinkedIn: <URL> · E-Mail:
  <Adresse> · verbunden seit TT.MM.JJJJ“ (nur, was vorhanden ist, `_kontakt_aufloesen`). Beziehung, letzter
  Kontakt, Priorität, nächste Aktion und Fälligkeit bleiben leer. Dazu kommt der Hinweis, dass LinkedIn alle
  Verbindungen liefert und die Liste für aktiv gepflegte Kontakte gedacht ist. Die Erkennung gilt auch
  für eine `.xlsx` (Abnahme: der Hinweis rät zum Kürzen in Excel, und Excel speichert dann oft als
  Arbeitsmappe; ein dabei in ein Datum verwandeltes „Connected On“ wird wie jede Datumszelle gelesen).
  Bei `zielfirmen` und `headhunter` ist eine LinkedIn-Datei eine gewöhnliche CSV; die
  Pflichtspalte fehlt dann, also 400.

**Spaltenerkennung** (`_spalten_zuordnen`): `_schluessel()` macht aus einer Überschrift den
Vergleichsschlüssel (NFC, klein, ä/ö/ü/ß zu ae/oe/ue/ss, nur `a-z0-9`; NFC zuerst, weil ein „ü“ aus
macOS-Dateien aus „u“ und Trema bestehen kann) und vergleicht ihn mit dem Vorlagennamen und den Synonymen
der Felder. Die erste passende Spalte je Feld gewinnt, jede weitere für dasselbe Feld und jede ohne
Zuordnung landet unter `spalten.ignoriert`. Pflicht ist mindestens eine der `pflicht_spalten` (Zielfirmen
`company`; Headhunter `firma` oder `ansprechpartner`; Kontakte `name`, `vorname` oder `nachname`), sonst
400. Ist die Namenszelle einer Zeile leer, ergibt sich `name` aus „Vorname Nachname“.

**Werte:** Zellen werden getrimmt (auch geschützte Leerzeichen und BOM), leer wird `None`, ganze Floats aus
Excel verlieren das „.0“, Excel-Daten werden ISO. Daten bleiben ISO oder werden aus `TT.MM.JJJJ`, `T.M.JJ`
(ab 2000) und LinkedIns „12 Sep 2023“ gelesen (`_datum_iso`; ein Tag, den es nicht gibt, ist nicht lesbar).
Nicht lesbar: `letzter_kontakt` und `last_update` bleiben als Text stehen (`_datum_text`),
`next_action_date` bleibt leer (`_datum_streng`), denn das Feld wird überwacht (fällige Aktionen erscheinen
unter Follow-ups), und die Zeile bekommt eine Meldung. Angeglichen werden Priorität (Hoch, Mittel,
Niedrig, auch englisch), der Kanal der Kontakte (LinkedIn, E-Mail, Telefon, Persönlich), Tier („1“, „1.0“
und „Tier 1“ ergeben „1“) und Szenario (Großbuchstabe, auch „a/b“); Unbekanntes bleibt, wie es ist.
`last_update` einer Zielfirma ist der Dateiwert, bei NEUEN Einträgen ohne Wert heute (`_heute()`, eine
eigene Funktion, damit ein Test das Datum festlegen kann).

**Kein automatisches `next_action_date`:** `POST /api/network-contacts` setzt ohne Angabe heute plus zehn
Werktage. Der Import tut das bewusst nicht: Nach einem Import mit hunderten Zeilen stünden alle am selben
Tag als fällige Aktion unter den Follow-ups. Die Gegenprobe (Automatik eingebaut) macht vier Fälle rot.

**Plan** (`_planen`, schreibt nichts): Je Datenzeile entstehen die Werte (`_zeilenwerte`), die Anzeige
(`_anzeige`, „A · B“, höchstens 120 Zeichen) und die Pflichtprüfung (`_pflicht_fehler`): Der `slug_parts`
eines Pflichtwerts darf nicht leer sein, sonst `fehler`; ein Wert, der nur aus Zeichen außerhalb von
`a-z0-9` besteht (etwa kyrillisch), bekommt eine eigene Meldung, weil `slug_parts` ihn zu einem leeren
Schlüssel machte. Komplett leere Zeilen fallen still weg. Der Schlüssel wird gegen ALLE Zeilen der Tabelle
(auch Tombstones) und gegen die Zeilen davor in derselben Datei gehalten: kein Eintrag ergibt `neu`, ein
Tombstone `geloescht` (übersprungen, nie wiederbelebt), ein vorhandener Eintrag `ergaenzt`, wenn mindestens
ein leeres Feld einen Dateiwert bekommt (`_luecken`, `felder_ergaenzt` nennt sie), sonst `unveraendert`.
Ein gefüllter Wert wird nie überschrieben, eine leere Zelle löscht nichts. Eine zweite Zeile mit demselben
Schlüssel wirkt auf das Ergebnis der ersten (Meldung „Doppelt in der Datei, siehe Zeile N“) und kann nur
noch deren leere Felder füllen. Die Standardwerte für neue Einträge kommen erst am Ende, damit eine spätere
Zeile desselben Eintrags den Wert noch liefern kann.

**Karriereseiten-Regel** (`Feld.nicht_gleich`): Der Excel-Export schreibt in die Spalte „Karriereseite“
ersatzweise die Webseite (`karriere_url or website`). Der Zielfirmen-Sweep lädt eine gesetzte
`karriere_url` direkt (Cache) und sucht dann nicht mehr nach dem Karriere-Link auf der Webseite; er läse
also die Startseite als Karriereseite. Eine Karriereseite, die der Webseite der vorhandenen Firma gleicht
(`_url_vergleich`: ohne Schema, ohne „www.“, ohne Schrägstrich am Ende), ergänzt `karriere_url` deshalb
nicht. Eine NEUE Firma behält beide Werte, wenn die Datei beide Spalten trägt. Die Gegenprobe ohne die
Regel macht zwei Fälle rot.

**Schreiben** (`importieren`):
1. Einlesen und erste Planung, nur lesend. Gibt es keinen Auftrag (`neu + ergaenzt == 0`), endet der Aufruf
   hier mit `sicherung: null`: keine Sicherung, kein Schreibzugriff.
2. Sicherung über `app.sicherung.anlegen()`, also in der Reihe der automatischen Sicherungen unter
   `data/backups/auto`. Die Datenbank kommt aus dem Engine-Pfad der Session
   (`session.get_bind().engine.url.database`), der Datenordner aus `daten_dir`; so sichert ein Test genau
   die Datenbank, in die er schreibt. `SicherungLaeuft` ergibt 409, jeder andere Fehler 500, beide Male
   ist nichts geändert.
3. `BEGIN IMMEDIATE` (`_schreibtransaktion_beginnen`): Schreibsperre ab hier. Ist die Datenbank belegt
   (SQLite meldet „locked“ oder „busy“ nach der Wartezeit von 15 Sekunden aus `db.CONNECT_ARGS`), ergibt
   das 409 statt eines hängenden Imports. Steht die Verbindung schon in einer Transaktion, bleibt es dabei.
4. `session.expire_all()` und zweite Planung unter der Sperre, damit der geschriebene Stand der geplante
   ist: Zwischen der ersten Planung und dem Schreiben liegt die Sicherung, in der Zeit kann ein anderer
   Prozess dasselbe Feld gefüllt haben. Die Antwort zählt aus dieser zweiten Planung.
5. `_schreiben`: Eine Ergänzung setzt nur die geplanten Felder und `updated_at`. Neue Einträge entstehen
   mit `dedup_key` über `flush_or_duplicate` (SAVEPOINT je Zeile, `session.add` erst im Callback, s. dessen
   Docstring). Scheitert ein Auftrag an einer Dublette, weil ein gleichzeitiger Import denselben Schlüssel
   angelegt hat, wirkt er wie eine Ergänzung (wie bei der früheren Einmal-Migration), und die Zähler der Antwort
   werden umgebucht (`neu` minus eins, dafür `ergaenzt`, `unveraendert` oder `geloescht` plus eins). Dann
   `session.commit()`.
6. Jeder andere Fehler beim Schreiben ergibt `rollback()` und 500. Eine Logzeile `[netzwerk-import]
   <liste>: <n> neu, <n> ergänzt, Sicherung <Datei>` geht auf die Standardausgabe des Servers.

**Warum `BEGIN IMMEDIATE` ausdrücklich:** `flush_or_duplicate` allein ist unter pysqlite nicht atomar.
pysqlite eröffnet nur vor INSERT, UPDATE und DELETE selbst eine Transaktion, nicht vor einem SAVEPOINT. Der
SAVEPOINT startet sie, und sein RELEASE schließt sie wieder mit einem COMMIT. Ohne die ausdrückliche
Transaktion bliebe nach einem Fehler mitten im Schreiben ein Teil der Zeilen stehen: Scheitert der Import
bei der dritten Zeile, stünden die beiden ersten in der Datenbank (belegt in
`test_flush_or_duplicate_allein_ist_unter_pysqlite_nicht_atomar`, das Verhalten im Import prüft
`test_eine_transaktion_fehler_mitten_im_schreiben_schreibt_nichts`). Schlüge der erste Test einmal an, hat
sich das Verhalten von Python oder SQLAlchemy geändert und die Vorkehrung ist überholt. Der Beginn mit
Schreibsperre schließt außerdem die Lücke zwischen Planung und Schreiben. Gegenproben: Ohne
`BEGIN IMMEDIATE` werden zwei Fälle rot, ohne `expire_all()` einer.

**Oberfläche** (`frontend/src/components/NetzwerkImport.tsx`): Zwei Bausteine, weil der Knopf in die
Kopfzeile des Reiters gehört und das Panel darunter aufgeht, wie bei `TargetNew` und `NcNew`:
`NetzwerkImportKnopf` (Nebenknopf mit Rahmen statt Cyan-Fläche, links vom Anlege-Knopf) und das Panel
`NetzwerkImport` (Props `liste`, `onImportiert`, `onClose`). `pages/Netzwerk.tsx` hält nur das Ein und Aus
(`showImport`; 12 eingefügte Zeilen und keine geänderte, damit das Zusammenführen mit den Änderungen von
P2-61 an derselben Datei leicht blieb): in `Netzwerk` für die Reiter Zielfirmen und Headhunter, mit einem
Effekt, der das Panel beim Reiterwechsel schließt, und in `NetzwerkKontakte` für den dritten. `onImportiert`
lädt die Liste der Seite neu (`loadRows` bzw. `load`). Ablauf im Panel: Datei wählen, `POST …/vorschau`,
Vorschau (erkannte Spalten als Chips, „Spalte → Feld“, wenn die Überschrift abweicht; nicht verwendete
Spalten; fünf Zähler; Hinweise; Tabelle der Zeilen mit Fehlern und Gelöschten zuerst), „Importieren (12
neu, 3 ergänzen)“ (gesperrt bei `neu + ergaenzt == 0`), `POST …` mit derselben Datei, Ergebniszeile „✓ 12
angelegt, 3 ergänzt. Vorher gesichert: <Datei>“ und „Schließen“. Uploads laufen mit `fetch` und `FormData`,
nicht über `api()`: Das setzt den JSON-Kopf, den Multipart nicht verträgt (Muster `Profil.tsx`). Drei
Schutzvorrichtungen: gegen Doppelklick (`schreibt`), gegen die Antwort einer überholten Vorschau (`lauf`)
und gegen das Melden nach einem Reiterwechsel mitten im Import (`aktiv`; das Neuladen hinge sonst am Reiter
von damals und schriebe dessen Zeilen in den neuen). Ein `TypeError` von `fetch` heißt, dass der Server
nicht antwortet oder die Datei nach der Auswahl geändert wurde (typisch: in Excel korrigiert), der
Fehlertext sagt beides. Zugänglichkeit: eine immer vorhandene Live-Region (`role="status"`) sagt „Datei
wird geprüft“, „Vorschau bereit …“ und das Ergebnis an, die Tabelle hat eine Caption, und die Badges
tragen immer den Klartext (die Farbe ist nie der einzige Träger; Fehler: Rot mit Weiß, 4,58:1). Die
Anzeigenamen in „Ergänzt: …“ kommen aus den Labels der erkannten Spalten (`spalten.erkannt`); die Liste
`FELD_NAMEN` in der Komponente fängt nur Felder ab, die der Server ableitet statt aus einer Spalte zu lesen
(beim LinkedIn-Export Kanal und Notizen); sie ist die einzige zweite Liste der Importfelder. Typen in
`api.ts`: `NetzwerkImportVorschau`, `NetzwerkImportErgebnis`, dazu `NetzwerkImportAnzahl`,
`NetzwerkImportZeile`, `NetzwerkImportListe` und `NetzwerkImportAktion`.

**Tests** (`tests/test_netzwerk_import.py`, 341 Fälle, alles unter `tmp_path` und in einer Test-Datenbank;
Excel-Dateien erzeugen die Tests mit `openpyxl`): Spaltenkonfiguration und Synonyme, CSV (Trennzeichen, Kodierungen,
Zeilenenden, Zeilennummern), Fehler beim Lesen, XLSX (Blattwahl, Daten, falsche Dimension, Zip-Bombe),
LinkedIn, Werte, kein automatisches `next_action_date`, die Regeln gegen die Datenbank,
Vorschau/Sicherung/Transaktion, Vorlagen, der Rundweg über den echten Excel-Export
(`pipeline.export_excel`; wieder einlesen ergibt nur „unverändert“ und keine Sicherung, in eine leere
Installation legt es alles an), Router und die Paketregeln für alle Kundentexte des Moduls (Sie-Form,
keine Gedankenstriche, kein Name des Autors, Mailadressen nur unter `beispiel.de`). Die Einbindung in `main.py`
prüft ein eigener Test gegen die ECHTE App (`test_router_ist_in_der_app_eingebunden`): Das Fixture `client`
der Datei baut eine eigene App mit nur diesem Router und überdeckt das gleichnamige aus `conftest.py`, ein
Test darüber bemerkte ein fehlendes `include_router` nicht. Gegenproben (je kurz zurückgebaut, dann rote
Fälle): ohne Tombstone-Regel 9, mit Überschreiben 7, mit automatischer Fälligkeit 4, ohne `BEGIN
IMMEDIATE` 2, ohne `expire_all()` 1, ohne Karriereseiten-Regel 2.

**Nebenbefunde** (beide im selben Commit behoben):
- **Excel-Export ohne Stellen:** `funnel_kpi()` liefert ohne Stellen `groesster_verlust = None`. Das
  Funnel-Blatt fing das ab, der kompakte Trichter auf dem Dashboard-Blatt (`_dashboard_funnel_block`) griff
  trotzdem darauf zu, und die Datenvalidierung des CV-Dropdowns ergab „M2:M1“. Der ganze Export brach ab,
  auf einer frischen Installation wie nach „Beispieldaten entfernen“ (P2-59), und damit auch der Schritt
  „Ansichten aktualisieren“ des Tageslaufs. Aufgefallen ist es beim Bau des Rundweg-Tests; am Probeserver
  liefen Export, Digest, Suchindex und Favicons nach „Beispieldaten entfernen“ danach fehlerfrei. Test:
  `test_export_laeuft_auch_ohne_stellen` (`tests/test_export_excel_funnel.py`).
- **Schlüssel des Beispiel-Kontakts:** Der Netzwerk-Kontakt der Beispieldaten trug
  `dedup_key = "beispiel|paul-paket"` statt des App-Schlüssels `slug_parts(Name, Unternehmen)`. Ein
  Datei-Import (Rundweg über den Export) oder das Anlegen von Hand legte denselben Kontakt deshalb ein
  zweites Mal an. Jetzt gilt der App-Schlüssel (`beispieldaten._zeilen_anlegen`); das Entfernen der
  Beispieldaten erkennt den Kontakt ohnehin am Namen (`_beispiel_bedingungen`). Test:
  `test_beispiel_kontakt_traegt_den_schluessel_der_app` (`tests/test_beispieldaten.py`).

**Folgen für die Sweeps:** Neue Zeilen haben `last_career_check = NULL`. Der Zielfirmen-Sweep und die
Headhunter-Suche wählen nur Einträge mit Webseite und sortieren NULL zuerst (12 bzw. 15 Einträge je Lauf,
s. die beiden `SKILL.md`, Abschnitt „Auswahl (Rotation)“). Ein großer Import mit Webseiten schiebt sich
also an die Spitze der Rotation und verlängert den Durchlauf entsprechend.

Bewusst nicht Teil des Imports: Überschreiben vorhandener Werte, Löschen, Wiederbeleben gelöschter
Einträge und ein unscharfer Abgleich der Namen.

### Gespeicherte Dateipfade: nur Server und Skills, verschoben nur aus der Positivliste (P2-56)

Pfade in der Datenbank schreiben der Server und die Skills. Ein Client darf genau einen setzen:
`prep_path` am Interview (`PATCH /api/interviews/{id}`), und nur auf ein vorhandenes Briefing in
`data/interview_prep/` (`.html`), gespeichert in der kanonischen Form
`data/interview_prep/<datei>.html`; alles andere ist 422, `null` leert das Feld. Die Oberfläche
schickt das Feld nie, interview-vorbereiten registriert Briefings über
`pipeline.interview.register`. Wer gespeicherte Pfade verschiebt, prüft sie selbst:
`_in_papierkorb` (alle Lösch-Endpunkte) verschiebt nur Dateien aus der Positivliste
`_ARTEFAKT_ORDNER`, mit derselben Prüfung wie `/api/artifact` (`_erlaubter_artefakt`); jeder andere
Pfad zählt als `dateien_fehlgeschlagen`, die Datei bleibt liegen. `cv_export` nimmt Entwürfe nur
aus `data/cv_basis/entwuerfe`, `data/tmp`, `outputs/cv_entwuerfe` und `outputs/cv`, Anschreiben nur
aus `outputs/anschreiben` und `data/tmp`, und räumt eine alte PDF nur aus dem Zielordner weg; ein
Basis-CV ist nie Quelle. `cleanup._in_papierkorb` bleibt in `data/` und `outputs/` (enger geht
nicht, weil die Rotation auch alte Sicherungen in den Papierkorb legt). Bis P2-56 reichten zwei
Aufrufe, `prep_path` auf `data/bewerbung.sqlite` setzen und das Briefing löschen, um die Live-DB in
den Papierkorb zu schieben; über denselben Wert nahm der Suchindex jede lesbare Datei auf.
**Wer ein Pfadfeld für Clients öffnet, prüft es mit `_erlaubter_artefakt` gegen den passenden
Ordner.** Ein Wächter in `tests/test_pfadfelder_sicherheit.py` meldet jedes andere Pfadfeld aus dem
Request, ein zweiter jede neue Schreib-, Verschiebe- oder Löschstelle in `main.py` und den
Routern.

### Design aus einer Quelle (P2-72)

Farben, Schriften, Icon und Anzeigename der Marke stehen in **einer Design-Datei**. Oberfläche,
neue Berichte, Digest, Coach-Site, Excel-Export und die Doku-Ansicht nehmen ihre Markenwerte nur von
dort. Mit der Vorgabe sieht alles aus wie vor dem Umbau.

**Zwei Orte, eine Regel.** Die Vorgabe liegt im Paket: `assets/design/standard.json` mit
`icon-32.png` und `icon-180.png` daneben. Eine Überschreibung liegt unter `data/design/`
(`design.json`, dazu eigene Icons). `data/` ist für jedes Update gesperrt, die Überschreibung
übersteht es. Gelesen wird Rolle für Rolle: Was die Überschreibung nicht oder ungültig nennt, kommt
aus der Vorgabe. Eine Oberfläche zum Ändern gibt es nicht, die Datei legt man von Hand an.

**Rollen statt Farbwerte** (`pipeline/design.py`): `marke`, `auf_marke`, `aktion`, `aktion_hover`,
`auf_aktion`, `stahl`, `flaeche`, `karte`, `rahmen`, `spur`, `text`, `text_gedaempft`, `trenner`,
dazu die Schriften `ueberschrift` und `text` (Inter, Montserrat oder Systemschrift), `produktname`
und die Icons. **Der Produktname ist fest:** Nur die Vorgabe nennt ihn, eine Überschreibung kann ihn
nicht ändern (sonst gilt die Vorgabe, dazu eine Warnung). Farben nur als `#RRGGBB`. Ein Paar aus Fläche und Schrift (`marke`/`auf_marke`,
`aktion`/`auf_aktion`, `flaeche`/`text`, `karte`/`text`) gilt nur gemeinsam und nur mit einem
Kontrast von mindestens 4,5:1, sonst gilt für dieses Paar die Vorgabe. **Ein ungültiges Design macht
das BMS nie unbenutzbar:** Jede Ablehnung ist eine Warnung im Log und in der Auskunft, nie ein Fehler.

```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.design zeigen
```
zeigt das geltende Design, die Quelle jeder Angabe, die Kontraste der Paare und alle Warnungen.

**Bedeutung ist kein Design.** Status, Score, Situation, Tier, Szenario, Bereich, Plan, die
Kopffarben des Beirats und die Schrift auf diesen Flächen sind feste Werte, auch wo sie zufällig der
Aktions- oder Markenfarbe gleichen. „Beworben“ bleibt cyan, wenn ein Design Orange als Aktionsfarbe
mitbringt. In Python stehen Status und Score in **einer** Tabelle (`pipeline/zustandsfarben.py`);
`tests/test_zustandsfarben.py` liest `frontend/src/components/ui.tsx` und hält beide gleich. Eine
benannte Ausnahme: Digest und Coach-Site schreiben auf Score 5 weiße Schrift
(`digest.SCORE_SCHRIFT_AUSNAHME`), wie vor dem Umbau.

**Wer die Quelle wie liest:**

| Ausgabe | Weg |
|---|---|
| Oberfläche | `frontend/index.html` lädt `GET /api/design.css` vor dem eigenen CSS. Tailwind bezieht die Rollen als `rgb(var(--marke) / <alpha-value>)`, die Klassennamen (`bg-brand-cyan` und die übrigen) sind geblieben. Ein anderes Design braucht keinen Neubau, ein Neuladen der Seite genügt. Icon: `GET /api/design/icon/32` und `/180`. |
| Berichte der Themen-Familie (Company-Fit, Auswertung eines Gesprächs, Anzeigen-Kopie, Aufräum-Bericht, Beirat) | `pipeline/bericht_stil.py::bericht_css(zusatz)` liefert das ganze CSS mit den ausgeschriebenen Werten des geltenden Designs. Jeder Renderer reicht nur seine eigenen Regeln als Zusatz mit. |
| Berichte, die ein Modell schreibt (Match, ATS-Scan, Briefing, Absagen-Analyse, Angebotsvergleich) | Der Skill schreibt HTML mit Klassen und ohne `<style>`. Danach setzt `python -m pipeline.bericht_stil einsetzen <Datei>` Stil und Icon ein (s. u.). |
| Digest, Coach-Site, Excel | lesen das Design bei jedem Aufruf (`design.laden()`), Zustandsfarben aus der Tabelle. |
| Doku | Die Doku-Ansicht der App rendert mit dem geltenden Design. Die mitgelieferten `docs/*.html` rendert `pipeline/docs_render.py` immer mit der Vorgabe, damit der Vergleichstest nicht vom Design einer Installation abhängt. |

Das Design wird überall **zur Laufzeit im Aufruf** gelesen, nie beim Import in eine Modulkonstante.
`design.laden()` merkt sich das Ergebnis und erkennt geänderte Dateien, eine neue Design-Datei wirkt
ohne Neustart. Wächter in `tests/test_design_ausgaben.py` und `tests/test_bericht_stil.py` schlagen
an, wenn ein Modul Design oder Icon wieder beim Import festhält.

**`bericht_stil einsetzen`** ersetzt in einem fertigen Bericht den `<style>`-Block durch
`bericht_css()` und setzt das Icon. Sonst ändert der Befehl nichts am Dokument, zweimal angewandt ist
gleich einmal. Er gehört zum Erzeugen eines Berichts. Exit 0 = in Ordnung, 2 = Datei unbrauchbar, 3 = Klassen ohne
Regel (die Datei ist trotzdem geschrieben).

```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.bericht_stil einsetzen ../data/company_fit/<Datei>.html
```
`assets/report_theme_bms.html` ist die Vorlage für Aufbau und Klassen. Ihr `<style>`-Block wird aus
`bericht_css()` mit der Vorgabe erzeugt (`python -m pipeline.bericht_stil vorlage`), ein Test hält
beides gleich. Kein Skill trägt mehr einen Farbwert oder ein CSS-Stück
(`tests/test_skills_ohne_css.py`).

**Berichte bleiben eigenständig und der Bestand bleibt, wie er ist.** Die Werte stehen ausgeschrieben
im `<style>` jedes neuen Berichts, kein Bericht verweist auf eine Datei oder Adresse. Schon erzeugte
Berichte werden nicht umgefärbt. `app/favicon.py` erkennt zwei Icons als gültig, das der Vorgabe und
das des geltenden Designs. Ersetzt wird nur ein Icon, das keines von beiden ist. Der Fußtext
„Bewerbungs-Mgmt · erzeugt am …“ ist fester Wortlaut, weil die Dublettenerkennung Berichte daran
erkennt.

**Grenzen:** Auf der Markenfläche stehen in Seitenleiste, Doku-Kopf und Excel-Kopfzeile noch feste
helle Werte. Mit einer hellen Markenfarbe sind sie schlecht lesbar. Die Berichte lösen das schon
(`bericht_stil.schrift_auf_marke`: Weiß, solange lesbar, sonst `auf_marke`). Karten der Oberfläche
bleiben weiß, die Rolle `karte` wirkt nur in den Berichten. Die vollständige Liste steht in
der Bau-Spec P2-72 unter „Ehrliche Grenzen“.

### Drittanbieter-Lizenzen (P2-77)

Die Seite Rechtliches → „Drittanbieter-Lizenzen“ wird erzeugt und nicht von Hand gepflegt. **Quelle**
sind die Lockfiles: `backend/requirements-lock.txt` (Python) und `frontend/package-lock.json` (npm).
`backend/pyproject.toml` und `frontend/package.json` liefern nur die Einteilung in „direkt“ und
„mitgebracht“. Der Generator `pipeline/drittlizenzen.py` schreibt zwei Dateien, beide werden nie von Hand
geändert:

- `frontend/src/rechtliches/drittlizenzen.md`: die Übersicht mit Paket, Version und Lizenzkennung, bei
  direkten Paketen mit Zweck. Dazu die Bauwerkzeuge als Zählung je Lizenz sowie die Listen der separat
  installierten Programme und der angebundenen Drittdienste.
- `frontend/src/rechtliches/drittlizenzen_texte.txt`: der unveränderte Wortlaut aller mitgelieferten
  Lizenzen. Pakete mit wortgleichem Text stehen in einem Block. Erlaubt sind nur zwei Angleichungen:
  Zeilenenden auf LF und keine Leerzeichen am Zeilenende. Die Seite lädt die Datei erst auf Klick
  („Lizenztexte anzeigen“) als eigenen Chunk, das Haupt-Bundle bleibt klein.

**Befehl** (vom Projekt-Root, der Wrapper folgt dem Muster von `scripts/docs_html.sh`):

```sh
scripts/drittlizenzen.sh              # erzeugt beide Dateien
scripts/drittlizenzen.sh --pruefen    # vergleicht nur, schreibt nichts
```
Exit 0 = erzeugt bzw. aktuell, 1 = nur bei `--pruefen`: mindestens eine Datei ist veraltet (die Ausgabe
nennt sie), 2 = Fehler, die Meldung nennt Paket und nächsten Schritt. Der Generator liest die
Metadaten und Lizenzdateien aus dem venv und aus dem Build-Spiegel
`~/.bewerbung_mgmt_node/frontend_build/node_modules` (`frontend/build.sh`). Passt einer von beiden nicht
zum Lockfile, bricht er mit Exit 2 ab und nennt den Befehl, der es behebt. Er läuft nur in der Entwicklung
(`AUSSCHLUESSE` in `pipeline/kundenpaket.py`), die beiden erzeugten Dateien sind dagegen Pflichtdateien
des Kundenpakets.

**Wann:** nach jeder Änderung an einem Lockfile oder an `pyproject.toml` bzw. `package.json`, vor dem
Commit. Die Ausgabe ist deterministisch (kein Datum, keine Version, kein Pfad), zwei Läufe ergeben
byte-gleiche Dateien.

**Lizenzkennung, nie geraten:** erst `License-Expression`, dann das Feld `License`, wenn es genau eine
Kennung der Positivliste enthält, zuletzt die Tabelle `LIZENZ_FESTGELEGT` (Kennung plus die ersten
zwölf Hex-Zeichen des SHA-256 des Lizenzwortlauts). Passt keine Stufe oder hat sich der Wortlaut
geändert, bricht der Generator ab und nennt den Text, den man lesen muss.

**Was die Wache prüft:** `tests/test_drittlizenzen.py` läuft in der CI (`backend` und `backend-windows`)
und braucht weder venv-Metadaten noch `node_modules`. Sie vergleicht den Bestand der Seite (Paketzeilen
der Übersicht, `Gilt für`-Zeilen der Texte) mit den Lockfiles, prüft jede Kennung gegen die Positivliste
und die Form beider Dateien (UTF-8, nur LF, genau ein Zeilenende am Schluss). Sie wird rot, sobald ein
Lockfile sich ändert und die Seite nicht neu erzeugt wurde oder eine Lizenz außerhalb der Positivliste
auftaucht.

**Was sie nicht prüft:** den Wortlaut. Das leistet nur `--pruefen`, und das läuft nur lokal (es braucht die installierte Umgebung), nicht in der CI. Ändert
ein Paket bei gleicher Version seinen Lizenztext, fällt es nicht auf; veröffentlichte Versionen auf PyPI
und npm sind unveränderlich, das Risiko ist klein. Ebenfalls offen: Die Texte stammen aus einer
macOS-Installation, Pakete für Windows oder Linux können andere Lizenzdateien tragen. „Direkt“ und
„mitgebracht“ folgen `pyproject.toml` und `package.json`, nicht den tatsächlichen Imports.

**Pflege von Hand** (alles in `pipeline/drittlizenzen.py`):

- `ZWECK`: je direktes Paket ein kurzer Zweck. Ein neues direktes Paket ohne Eintrag bricht den
  Generator mit Exit 2 ab, die Meldung nennt das Paket.
- `LIZENZ_FESTGELEGT`: nur für Pakete, deren Metadaten keine eindeutige Kennung nennen (heute
  google-auth, google-auth-oauthlib, pyasn1_modules). Den Lizenztext im `*.dist-info` lesen, die Kennung
  bestimmen, dann Kennung und Hash eintragen. Nicht ohne Hinsehen übernehmen.
- `PROGRAMME` und `DIENSTE`: die Listen der separat installierten Programme und der angebundenen
  Dienste. Ändert sich eine Dienstanbindung, gehört auch `datenschutz.md` auf den Prüfstand.

**Die Positivliste ist eine Entscheidung der Projektleitung** (16.10.2026): MIT, MIT-0, ISC, BSD-2-Clause, BSD-3-Clause,
Apache-2.0, PSF-2.0, MPL-2.0 (certifi) und OFL-1.1, nur für Bauwerkzeuge zusätzlich CC-BY-4.0. Bei einem
Ausdruck gruppieren Klammern, `AND` bindet stärker als `OR`: `A OR B` ist erlaubt, wenn eine Seite
erlaubt ist, `A AND B` nur, wenn beide es sind. Unbekannte Bestandteile (`WITH`, `+`) gelten als nicht erlaubt. Eine neue Lizenz macht die CI rot, und die Projektleitung entscheidet, ob sie auf die Liste kommt.
Die Liste nicht ohne ihn erweitern.

**Paketprüfung:** Der Wortlaut enthält Autoren-Adressen und Firmennamen aus den Copyright-Zeilen und
darf nicht verändert werden. Deshalb gilt für `drittlizenzen_texte.txt` eine pfadgebundene Ausnahme
(`_FREMDER_WORTLAUT`, s. `docs/RELEASE.md`). Bauwerkzeuge erscheinen in der Übersicht ohne Wortlaut.
Die Seite bleibt unter dem Hinweis „ENTWURFSFASSUNG“ und ist keine Rechtsberatung.

### Report-Selbstprüfung (`pipeline/report_check.py`, 23.07.2026)

Die generierten HTML-Reports (ATS-Scan, Match, Company-Fit, Beirats-Check, Transkript-Report …)
sind **eigenständige Dateien**: `assets/report_theme_bms.html` wird nicht verlinkt, sein
CSS also in den `<style>`-Block jedes Reports kopiert. Kürzt ein LLM-Lauf dabei das CSS, bleibt das
Markup korrekt, aber die Darstellung bricht **lautlos** — genau so verlor ein ATS-Scan am
23.07. seine grün/roten Keyword-Chips (`class="chip pos"` 9× im Markup, `.chip.pos` fehlte im
`<style>`); aufgefallen ist es nur im Browser.

Der Check ist die Gegenmaßnahme: deterministisch, kostenlos, ohne Vorwissen über Report-Typen.

**Dasselbe Muster beim App-Icon (P2-44, 23.09.2026):** Die Vorlage trägt das Icon als 3,3 KB
langen Data-URI, den jeder Bericht mitkopiert. In 37 von 2.701 Dateien war diese Zeichenkette
verstümmelt oder durch ein fremdes Icon ersetzt — und blieb es, weil `app/favicon.py` jede Datei
in Ruhe ließ, die *irgendein* Icon trug. Seitdem gewinnt das App-Icon: ein fremder Icon-Link wird
ersetzt, mehrfache werden auf einen reduziert (`apple-touch-icon` bleibt unberührt). Damit heilen
alle drei Ebenen — Erzeuger, `/api/artifact` beim Ausliefern und `pipeline.favicon_nachruesten`
im Tageslauf — auch ein falsches Icon, nicht nur ein fehlendes.
Er vergleicht **benutzte Klassen-Kombinationen gegen vorhandene CSS-Regeln** und meldet jede
Klasse, die wirkungslos bleibt. Seit P2-72 schreibt kein Modell mehr CSS: Der Skill schreibt den
Bericht ohne `<style>`, `bericht_stil einsetzen` setzt das vollständige CSS ein, und der Check läuft
direkt danach. Beide Schritte stehen als eine Zeile in allen sechs Skills, deren Berichte ein Modell
schreibt (`job-deepdive`, `cv-match`, `cv-erstellen`, `interview-vorbereiten`, `absagen-analyse`,
`angebot-vergleich`). Meldet einer der beiden eine Klasse ohne Regel, ersetzt das Modell die Klasse
durch eine aus der Vorlage.

```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.report_check ../data/company_fit/*.html
```
Exit-Code 0 = sauber, 1 = mindestens eine Regel fehlt. Reparatur ist billig (`bericht_stil
einsetzen` setzt das vollständige CSS ein), ein teurer Neu-Lauf des Skills ist dafür nie nötig. Beim Erstlauf über
den Gesamtbestand (289 Reports) fand er neben diesem Fall zwei alte Transkript-Reports mit
wirkungslosen `.signal`/`.amber`-Klassen; seither ist der Bestand vollständig grün.

⚠️ Zwei bewusste Abgrenzungen, sonst entstehen Fehlalarme: JS-Template-Literale
(`class="${badgeClass(...)}"` in Company-Fit-Reports) und Fremd-Markup in den Anzeigen-Snapshots
(`data/job_postings/` enthält den kopierten Original-HTML samt Tailwind-Klassen der Firmenseite)
werden übersprungen.

### Coach-Site: Read-only-Spiegel für einen externen Betrachter (Phase 81/82)

Optionaler, passwortgeschützter statischer Export des Bewerbungsstands für einen externen Coach —
deterministisch aus der DB gerendert (`pipeline/coach_export.py`, kein LLM, 0 Kosten), Upload per
SFTP-Spiegel (`scripts/coach_deploy.sh`, lftp). **Whitelist- statt Sperrlisten-Prinzip:** Der
Exporter liest die Sperrfelder (Gehalt, Notizen & Verlauf, Beirats-Checks, `verify_note`-Interna,
Transkripte/Debriefs/Briefings, CVs/Anschreiben, ATS-Scans, Netzwerk/Kontakte, Budget, E-Mails)
gar nicht erst aus der DB — testbewehrt in `tests/test_coach_export_sperrliste.py`. Sichtbar sind
Übersicht-KPIs, der Tages-Digest in einer Fassung ohne Mails, offene Aktionen und Verlaufsnotizen
(P2-79), Stellen in zwei Sektionen „Aktive Bewerbungen" und „Sichtung & Prüfung" (jeweils
mit Company-Fit, Match und Anzeigen-Snapshot ohne den internen Erfassungs-Kontext) sowie Absagen
mit Absagegründen und der Lost-Order-Analyse samt Berichtsdatum.

Seit Phase 82 ist die Funktion **pro Installation über Einstellungen → Coach-Site konfigurierbar**
(Adresse, SFTP-Zugang, Serverpfad-Automatik, Coach-Login) statt wie in Phase 81 fest auf eine
einzelne Installation verdrahtet: `pipeline/coach_settings.py` speichert
`~/.bewerbung_mgmt_secrets/coach_settings.json` (600/700) und migriert eine ältere, rein
terminalbasierte `coach_sftp.env` automatisch, ohne sie zu verändern (Rollback-Pfad bleibt
erhalten). Der Coach-Login läuft über bcrypt (Präfix auf `$2y$` normalisiert, Apache/APR-
kompatibel) — das Klartext-Passwort wird nirgends gespeichert. Auslöser: Button „Coach-Site jetzt
aktualisieren" (Einstellungen) und automatisch als letztes, nicht-fatales Glied des Tageslaufs —
ohne vollständige Konfiguration bzw. bei abgeschaltetem Schalter endet der Schritt grün (Exit 0),
der Tageslauf wird davon nie rot. Details: `docs/COACH_SITE.md`.

### Tests & CI (`backend/tests/`, `.github/workflows/ci.yml`, Phase 57)

Aktuell **mehr als 2000 pytest-Tests** (Phase 57 startete mit 36) laufen isoliert von der Live-DB: `conftest.py`
setzt `BMS_DATA_DIR` auf ein frisches `tempfile.mkdtemp()`-Verzeichnis ganz oben auf
Modulebene — vor jedem Import von `app.*`/`pipeline.*`. Grund ist eine Import-Zeit-Falle:
`app/db.py` bindet `DATA_DIR`/`DB_PATH` beim allerersten Modul-Import; würde irgendeine
Testdatei ein App-Modul auf Modulebene importieren, bevor die Env-Variable gesetzt ist,
bindet sich die gesamte Suite unumkehrbar an `data/bewerbung.sqlite` (Python cached Module,
ein späterer Re-Import hilft nicht mehr). Deshalb importieren alle Testdateien App-Module
ausschließlich funktionslokal in Fixtures/Tests, nie auf Modulebene — und ein Sicherheitsnetz
in `conftest.py` bricht den Lauf hart ab, falls `DB_PATH` doch außerhalb des tmp-Verzeichnisses
läge. Aus demselben Grund sind Fixtures (`seed`) bewusst rein synthetisch (`Musterfirma GmbH`,
`Test AG`, erfundene Titel) — nie Zeilen aus der echten DB kopiert, sonst würde das Repo über
die Tests personenbezogene Daten einschleusen (I2 aus Phase 56 gilt für Testdaten genauso).

Phase 79 schloss dieselbe Lücke für **Artefakt-Pfade**: mehrere Module (u. a. `dedup_text`,
`search_index`, `beirat_engine`) lösten `data/…`-Pfade weiterhin gegen den Projekt-Root auf,
während die Schreiber bereits gegen `DATA_DIR` schrieben — in Produktion identisch, unter
Testisolation aber divergent (ältere Tests waren dort nur grün, weil sie vom selben Leck
profitierten). Seither läuft jede Auflösung eines `data/`-Pfads über eine gemeinsame Funktion
in `app/db.py` (folgt `BMS_DATA_DIR`); `outputs/`-Pfade bleiben bewusst gegen den Projekt-Root
aufgelöst — die Dokumente des Nutzers sollen nicht isoliert werden.

CI (vier Jobs bei jedem Push nach `main` und jedem Pull Request: `backend`, `backend-windows`,
`frontend`, `secret-scan`) führt diese Suite auf Python 3.12 aus, unter Linux und unter Windows.
Der Pin folgt bewusst der lokalen venv-Realität, nicht umgekehrt. Bis
Phase 57 war das Python 3.9 (seit Oktober 2025 EOL); Phase 58 hat das venv am selben Pfad
mit identischem Lock (null Abweichungen) auf Python 3.12.13 aus Homebrew umgestellt — die
EOL-Schuld ist damit beglichen. CI baut außerdem das Frontend gegen Node 24. PDF-Rendering
(LibreOffice/`soffice`) ist dabei weiterhin eine offene Testlücke: weder lokal noch in CI
durch `skipif`-Tests abgedeckt, kein stiller CI-Skip, sondern schlicht ungetestet — Kandidat
für eine spätere Phase.

**`backend-windows`** (seit Phase 71D) führt dieselbe Suite auf `windows-latest` aus
(`working-directory: backend`, `python -m pytest tests -q`); `release.yml` ruft `ci.yml` per
`workflow_call` auf, ohne grünen Windows-Lauf entsteht also kein Release-Paket. Tests, die POSIX
voraussetzen, tragen `@pytest.mark.skipif(os.name == "nt", …)` und überspringen dort:
`test_prozess_tracking.py` (ganzes Modul: echte `sleep`-Prozessgruppen, `ps`/`os.killpg`),
`test_beirat_stderr_deadlock.py` (ganzes Modul: Stub per `chmod +x`, startet ohne Interpreter über
die Shebang-Zeile), ein Test in `test_cv_export.py` (Timeout-Kill über `os.killpg`), zwei
Rechte-Asserts in `test_log_pfade.py` (`st_mode == 0o600/0o700`) und ein Test in
`test_tmp_aufraeumen.py` (Symlinks brauchen unter Windows Sonderrechte). Auf dem Windows-Runner
ist kein LibreOffice installiert, der Windows-Pfad der PDF-Erzeugung lief dort also nie. Die
Kundensicht dieser Grenzen steht in `docs/SETUP-WINDOWS.md` (Bekannte Grenzen, Support-Matrix),
der Entwicklerweg unter Windows in `docs/INSTALLATION.md` Teil 1. `.gitattributes` hält
Textdateien auf LF (sonst schlüge `test_docs_html.py` auf Windows-Runnern fehl) und `.bat`/`.cmd`
auf CRLF.

**Tests lokal ausführen.** `scripts/test.sh` ruft pytest im venv gegen `backend/tests/` auf (einmalig
`~/.bewerbung_mgmt_venv/bin/pip install -r backend/requirements-dev.txt`). Die Isolation gegen die
Live-DB läuft über `BMS_DATA_DIR`: `conftest.py` setzt es selbst auf ein frisches tmp-Verzeichnis, bevor
irgendein App-Modul importiert wird. `data/bewerbung.sqlite` bleibt unangetastet, der Server auf Port 8000
kann parallel weiterlaufen.

**Secret-Guard-Hook** (einmalig pro Klon): `scripts/install_hooks.sh` schreibt einen Wrapper nach
`$(git rev-parse --git-dir)/hooks/pre-commit` (Hooks sind nicht versioniert, dieses Skript ist der
reproduzierbare Weg dorthin), der vor jedem Commit die staged Änderungen gegen ein paar Token-Muster prüft
(<0,1 s) und bei einem Fund blockt. Bewusste Ausnahme: `git commit --no-verify`.

**Python-Umgebung neu aufbauen.** Bricht das venv (typisches Symptom nach einem `brew upgrade`/`cleanup` von
`python@3.12`: `bad interpreter`), hilft der Neubau aus dem Lock:
```sh
rm -rf ~/.bewerbung_mgmt_venv
/opt/homebrew/bin/python3.12 -m venv ~/.bewerbung_mgmt_venv
~/.bewerbung_mgmt_venv/bin/pip install -r backend/requirements-lock.txt -r backend/requirements-dev.txt
```

Der Job `secret-scan` ersetzt das auf diesem Repo nicht verfügbare GitHub Secret
Scanning (422, Plan-Limitierung) durch eine zweistufige Kette: lokal ein pre-commit-Hook
(`scripts/precommit_secret_scan.sh`, reine Bordmittel git+grep, prüft nur staged Änderungen,
<0,1 s), in CI `gitleaks` über die volle Commit-Historie (`.gitleaks.toml`). Wichtig für die
Interpretation eines grünen Laufs: der `secret-scan`-Job bei einem Push prüft nur, ob im
NEUEN Commit etwas gefunden wurde — die Action scannt bei diesem Trigger ausschließlich die
neu gepushten Commits. Der Scan der GESAMTEN Historie läuft separat über den
`workflow_dispatch`-Trigger (`gh workflow run ci.yml`). Beide Varianten sind grün verifiziert.

---

## 9. API-Überblick (140 Endpunkte)

Ausgewählte Kategorien (alle unter `/api/…`, Backend liefert auch das Frontend aus; keine
CORS-Freigabe für fremde Webseiten, Schreibzugriffe nur vom eigenen Ursprung, Antworten nur unter
freigegebenen Namen, s. §8, P2-55 und P2-57). Gezählt sind die Kombinationen aus Methode und Pfad
unter `/api` im OpenAPI-Schema der App (Stand P2-72, mit `/api/doku*`, `/api/design*`, `/api/beispieldaten*`,
`/api/netzwerk-import*` und `/api/profil/identitaet`; die frühere Angabe 121 war nur von Hand fortgeschrieben worden und lag vor
P2-59 schon sieben unter dem tatsächlichen Stand von 128, P2-59 brachte vier Endpunkte dazu, P2-62
drei, P2-69 zwei, P2-72 drei für das Design):

- **Stellen:** `GET/POST /jobs`, `GET/PATCH/DELETE /jobs/{id}` (Soft-Delete + Papierkorb),
  `/jobs/{id}/approve|discard`, `/jobs/{id}/interviews|transcripts|transcripts/upload|files|chat|log`,
  `DELETE /files/virtual/{quelle}/{pk}/{slot}` (generierte Artefakte), `DELETE /companies/{id}`
- **Firmen & Kontakte:** `GET /companies`, `PATCH /companies/{id}`, `GET /contacts`
- **Design (P2-72):** `GET /design` (geltendes Design mit Quelle und Warnungen), `GET /design.css`
  (die Rollen als CSS-Variablen für die Oberfläche), `GET /design/icon/{groesse}` (`32` oder `180`).
  Alle drei sind reine Lesezugriffe ohne Sperre (s. §8 „Design aus einer Quelle“)
- **Netzwerk:** `GET/POST/PATCH/DELETE /target-companies|headhunters|network-contacts`,
  `POST /…/{id}/restore` + `GET /netzwerk/papierkorb` (Papierkorb),
  `GET /network-check`, `POST /initiativ`
- **Netzwerk-Import (P2-62):** `GET /netzwerk-import/{liste}/vorlage?format=csv|xlsx` (Vorlage zum
  Herunterladen), `POST /netzwerk-import/{liste}/vorschau` (Feld `datei`, schreibt nichts) und
  `POST /netzwerk-import/{liste}` (Feld `datei`, erst Sicherung, dann eine Transaktion); `{liste}` ist
  `zielfirmen`, `headhunter` oder `kontakte`, sonst 404. Fehler 400, 409, 413, 422 und 500 (s. §8
  „Netzwerk-Import“)
- **E-Mail:** `GET /inbox|emails`, `GET /emails/{id}/body`, `PATCH /emails/{id}`, `POST /emails/{id}/assign` (Stelle zuordnen/lösen),
  `POST /emails/{id}/archive|restore` (P2-52, Archiv für Mails ohne Stelle)
- **Suche:** `GET /search`, `GET /search/meta`, `POST /search/rebuild`
- **Tasks (headless):** `GET/POST /tasks`, `GET /tasks/{id}`, `/tasks/{id}/cancel`, `/task-kinds`,
  `/agent-status`
- **Beirat:** `GET /beirat/mitglieder|debatten|debatten/{id}`, `POST /beirat/debatten` +
  `/{id}/stop`, `GET /beirat/debatten/{id}/stream` (SSE live), `POST /beirat/stellen-check` (Job-Check), `GET/POST /beirat/keys`
  (lokal in `~/.bewerbung_beirat/`, nur maskierter Status über die API)
- **Budget:** `GET /budget`, `/budget/check/{provider}`, `PATCH /budget/limits/{provider}`,
  `POST /budget/sync`
- **Sichten:** `GET /dashboard|followups|upcoming-interviews|review|runs|digest`
  (`digest` als HTML in der Sandbox, P2-58), `GET /export/excel|export/outreach`
- **Profil (Phase 45):** `GET/PATCH /profil`, `POST/PATCH/DELETE /profil/skills[/{id}]`,
  `POST/PATCH/DELETE /profil/werdegang[/{id}]`, `POST/DELETE /profil/dateien[/{id}]`,
  `POST /profil/import-zip` (LinkedIn-Datenexport), `POST /profil/linkedin-einlesen` (Text oder PDF → headless Task), `GET`/`DELETE /profil/linkedin-vorschlag`, `POST /profil/linkedin-vorschlag/uebernehmen`
- **Profil-Datei (P2-69):** `GET/PUT /profil/identitaet` — liest und schreibt `config/profil.md` über die
  Karte „Identität und Suchstrategie“. Die Antwort trägt `stand` (SHA-256 des Dateiinhalts); ein PUT mit
  veraltetem `stand` ist 409, ein Prüffehler 400. Vor dem Überschreiben geht die alte Datei in den Papierkorb (s. §8 „Profil-Datei“)
- **Einstellungen (Phase 49/50, P2-51):** `GET/PATCH /einstellungen` — Suchbereich, Firmengröße,
  Pläne A/B/C und KI-Modellwahl je Funktion; zusätzlich `umkreis_label`, `modell_optionen`,
  `modell_standard` in beiden Antworten, `umbenennung` in der PATCH-Antwort bei einem
  Umkreis-Wechsel; jeder PATCH regeneriert den verwalteten Block von `config/suchprofile.yaml`.
  Seit P2-59 ohne Fable: `modell_optionen` nennt nur Opus, Sonnet und Haiku, `modelle` zeigt die
  wirksamen Werte, und ein PATCH mit `fable` ist 422 (s. §8 „KI-Modelle“)
- **Dokumentation (P2-59):** `GET /doku` (die Dokumente dieser Installation als Liste aus `id`,
  `titel` und `gruppe`), `GET /doku/{name}` (die gerenderte Seite als HTML in der Sandbox; `name` ist
  eine Kennung oder ein Dateiname aus dem Katalog, sonst 404; s. §8 „Dokumentationsseite“)
- **Beispieldaten (P2-59):** `GET /beispieldaten` (Status `keine`/`vorhanden`/`entfernt`, Anzahl je
  Art), `POST /beispieldaten/entfernen` (erst Sicherung, dann Löschen; 409, wenn nichts zu entfernen
  ist, eine Sicherung läuft oder an einer Beispielstelle eine Aufgabe arbeitet, 500 bei
  gescheiterter Sicherung; s. §8 „Beispieldaten“)
- **Version (P2-51):** `GET /version` — Installationsart (paket/git/unbekannt), Version bzw.
  Entwicklungsstand, Commit/Datum, letztes Update, CHANGELOG-Abschnitt der installierten Version;
  nie ein 500 (jeder interne Fehler ergibt null-Felder)
- **Neueste Version (P2-82):** `GET /version/neueste` — fragt auf Anforderung bei GitHub-Releases nach
  der neuesten Version und vergleicht sie mit der installierten; antwortet immer 200, Fehler stehen als
  Kundentext im Feld `fehler` (s. §8 „Update-Auskunft über GitHub-Releases“). Die Lizenz-Endpunkte
  `/lizenz` und die Antwort 402 gibt es seit P2-82 nicht mehr
- **Sicherung (P2-52):** `GET /sicherung` (Status: letzte Sicherung, Zahl, Warnung), `POST
  /sicherung` („Jetzt sichern", läuft auch bei ausgeschalteter Automatik), `PATCH
  /sicherung/einstellungen` (Aufbewahrung, an/aus)
- **Coach-Site-Einstellungen (Phase 82):** `GET/PUT /settings/coach`, `POST /settings/coach/test`
  (Verbindungstest gegen ggf. noch ungespeicherte Formularwerte), `POST
  /settings/coach/serverpfad` (Automatik-Ermittlung der `.htpasswd`, nur im leeren Zielverzeichnis)
- **CV-Entwurf (Phase 46/48):** `GET/PATCH /cv-versions/{id}/entwurf` (Editier-Checkpoint),
  Anschreiben-Text am Application-Endpunkt
- **Artefakte:** `GET /artifact` (liefert nur Dokumente aus der Positivliste `_ARTEFAKT_ORDNER`,
  sonst 403; s. §8 „Dateiauslieferung", P2-54; HTML zur Anzeige in der Sandbox, s. §8 „Berichte
  in der Sandbox", P2-58)

---

## 10. Entwicklungs-Historie & Roadmap

Das System ist in Phasen gewachsen. Grobe Chronik:

| Phasen | Inhalt | Stand |
|---|---|---|
| 0–5 | Grundgerüst, DB, erste Skills (Jobsuche, Email-Check, Deep-Dive, Tageslauf) | ✅ |
| 6 | Follow-up-Tracking & interaktives Dashboard | ✅ |
| 7 | Interviews, Call-Vorbereitung & Transkripte | ✅ (Hedy zurückgestellt) |
| 8 | Community-Backlog + Agenten aus der Web-App (Task-Center, Ketten) | ✅ |
| 9 / 17 | Perplexity als zweite Such-Engine | ⏸ zurückgestellt (NO-GO nach Messung), entfernt mit P2-78 |
| 10–14 | Budget-Steuerung · Dateien am Job · CV-PDF-Export · Mail-Jobsuche · **Vier-Augen-Prinzip** | ✅ |
| 15 | Auto-Bewerben | ⛔ verworfen |
| 16 | Job-Detail-Workflow-Layout | ✅ |
| 18–25 | Anzeigen-Snapshot · Eckdaten-Edit · Quellen-Konflikte · Netzwerk-Kontakte · Suchlauf-Anzeige · Notizen-Verlauf · **Volltextsuche** | ✅ |
| 26–28 | Headhunter-Webseite + Karriereseiten-Sweeps · Inbox-Volltext + KI-Antwort · Netzwerk-Löschen + KI-Chat | ✅ |
| **29** | **Nejo-Portal · Index-Stand immer sichtbar · Favicon** (inzwischen v2-Icon) | ✅ |
| **30** | Einheitlicher Report-Style (Template) · interne Namenskonvention · **Transkript-Report + Datei-Upload** | ✅ |
| **31** | Migration Bestandsdokumente auf neue Namen/Style | ✅ ausgeführt |
| **32** | **Löschen mit Bestätigung**: Stellen (Soft-Delete-Tombstone) · Firmen · generierte Dateien — zentraler Papierkorb, orphan-frei | ✅ |
| **33** | System-Cleanup-Kommando (`scan` → `apply` → `leeren`: Orphans, Rotation, Papierkorb-Endleerung) | ✅ |
| **34** | CV-Match **Vorher/Nachher-Gegenüberstellung** zurück · Artefakte im selben Tab · Suchkriterium **Mindest-Firmengröße 100+ MA** | ✅ |
| **35** | Einheitlicher **Report-Kopf** (Debrief-Muster für alle Vorlagen) · ATS-Scan: Keyword-Abgleich + Score-Herleitung zurück · Footer ohne „Daube.Tech" | ✅ |
| **36** | **Unzugeordnete E-Mails** sichtbar in der Inbox (Badge/Filter „Ohne Stelle") · manuell einer Stelle **zuordnen/lösen** · email-check verwirft relevante Mails nie mehr | ✅ |
| **37** | **Arbeitsagentur als Portal** (deutsche Titel-Synonyme, eigener deterministischer Suchschritt) · Tages-Digest im selben Tab | ✅ |
| **39** | **Bewerbungs-Beirat**: 7 Personas + Charta integriert (interaktiv via `/beirat-basis` UND Web-Seite `/beirat`); Brandt orchestriert autonom, Live-Debatte per SSE, Agent SDK headless (keyless via Abo oder eingegebener Key), OpenAI optional | ✅ direkt gebaut |
| **40** | **Beirats-Stellen-Check im Job-Workflow**: Nav-Eintrag raus, neuer Schritt „2 · Stelle prüfen (Beirat)" in der Unterlagen-Karte (Charta-Abstimmung aller 7, deterministische Entscheidung, HTML-Dashboard Typ BeiratsCheck (seit P2-63 `Beirat`), JobFile-Registrierung mit Ampel-Note) | ✅ |
| **41** | Neuer Job-Status **„Beirat abgelehnt"** (terminal, selbst aussortiert nach Beirats-Check — getrennt von „Kein Match"/„Absage"; Normalisierungs-Ausnahme, eigene Badge-Farbe, Ein-Klick-Vorschlag am 🔴-Check, Skill-Abgrenzungen) | ✅ |
| **42** | **Task-Center als einziges Aktivitäts-Log**: Beirat-Engine schreibt eigene AgentTask-Rows (Kosten je Turn summiert, Log im Viewer-Format, Cancel-Weiche, Guardrails zählen mit, Backfill des Bestands) — Architektur-Prinzip festgeschrieben | ✅ |
| **43** | **Status-Verteilungsbalken** auf der Stellen-Seite (proportionale, klickbare Segmente; Farben per Direkt-Fix aus dem Daube.Tech-Styleguide neu abgeleitet — Cyan→Navy-Leiter, eine kanonische Map für Balken UND Pipeline) · Pipeline-Headline nennt „Beirat abgelehnt" | ✅ |
| **38** | **Anzeigen-Snapshot schon bei der Erfassung** (Basis-Snapshot aus dem Vier-Augen-Fetch beim Ingest, firma-pruefen ersetzt später durch die Vollversion; Backfill über den Bestand) | ✅ |
| **44** | **Repost-Erkennung** im Dedup: zweistufig aus Titel-Wort-Jaccard (Pflicht-Vorfilter) + Text-Score, gegen den echten Bestand kalibriert | ✅ |
| **45** | **Profil-Seite**: Positionierung · Skills als Chips nach Bereichen · Werdegang · Zeugnis-Dateien; LinkedIn-Import auf zwei Wegen (Datenexport-ZIP deterministisch, URL best effort/ehrlich an der Login-Wall), beide additiv & zerstörungsfrei; Ableitung `config/profil_struktur.md` für CV-/Anschreiben-Skills | ✅ (A–D) |
| **46** | **CV-Prozess mit Editier-Checkpoint** (`cv-anpassen` → `cv-match` + `cv-erstellen`: Entwurf erst bearbeiten, dann Word/PDF **und danach** ATS-Scan auf dem finalen Dokument) · **Dokument-Engine**: Seitenumbruch-Schutz + Fußzeile „Name · Seite X von Y" für alle erzeugten CVs | ✅ (A+B) |
| **47** | LinkedIn-Export-Hinweis korrigiert („Download larger data archive" statt Schnellauswahl „Profile") · **automatische Skill-Einsortierung** (`skills-sortieren` läuft nach jedem ZIP-Import, verschiebt nur, erfindet nichts) | ✅ (A+B) |
| **48** | **Inline-Textfenster** für CV-Inhalt (ein Fließtext statt vieler Einzelfelder, volle Bullet-Freiheit, Überschriften gesperrt → ATS bleibt intakt) und **neuer Anschreiben-Editor** (vorher nur generierte Datei; „Text aus vorhandener .docx laden" für Altbestand) | ✅ (A+B) |
| **49** | **Einstellungen-Seite**: Suchbereich (Remote/Deutschlandweit/Stadt+Umkreis) & Mindest-Firmengröße · **Pläne A/B/C** (Titel/Seniorität/Branche je Plan, Reihenfolge A→B→C, Plan C neu). DB ist die Wahrheit, `config/suchprofile.yaml` die abgeleitete Sicht — Marker-Split-Writer erhält alle handgepflegten Technik-Parameter wörtlich, alle 9 YAML-Konsumenten bleiben unverändert | ✅ (A+B+C) |
| **50** | **KI-Modellwahl je Funktion** (Jobsuche · Company Fit · Beirat · CV Match · ATS Scan · Anschreiben → Opus 4.8 / Sonnet 5 / Haiku 4.5, Default Sonnet) in `sucheinstellung.modelle_json`; greift über `agent_runner._argv` (headless Task-kinds) und `beirat_engine` (alle 7 Personas) | ✅ (A+B) |
| **51** | Dashboard-Umbau: links Status/Match-Score/Portal, rechts **Situation je Plan A/B/C** (inkl. `norm_plan()` für verschmutzte `plan_ab`-Werte und echtem `plan`-Filter im Job-Listing) | ✅ (A+B) |
| **52** | Anschreiben-Editor aus der schmalen Seitenleiste in die **breite Mittelspalte** (unter den CV-Editor) + Text-Sync, wenn ein neuer Lauf das Anschreiben ersetzt (ohne ungespeicherte Eingaben zu verwerfen) | ✅ (A+B) |
| **53** | **Excel-Export V2 „Bewerbungs-Stand"** (Vorbild: Claudias Tracker-Cockpit): 8 Blätter — Dashboard-KPIs (identisch zu `/api/dashboard`) · Stellen **pro Status gruppiert** (Match farbig, ATS, Beirats-Ampel, Quelle als Hyperlink, nächster Schritt) · Aussortiert · Kontakte · Netzwerk · Headhunter · Zielfirmen · Outreach; Farbmodell V2 aus `ui.tsx`, terminale Status ohne alten „Nächster Schritt", Dateiname `JJJJ_MM_TT_Bewerbungs-Stand.xlsx` (seit P2-63 `JJJJMMTT_…`) (Inbox-Blatt entfällt) | ✅ |
| — | **Dashboard-Farbmodell V2** (Style Guide v5.0 §18) durchgezogen: semantische Status-/Score-/Situations-Token statt Cyan-Leiter, gemeinsame Map für Balken · Funnel · Kanban · Status-Pillen · Netzwerk-Pillen; Kontraste WCAG-geprüft (ScoreBadge/Status-Pillen brauchten Navy statt Weiß) | ✅ |
| — | **Anschreiben-Dokument** überarbeitet: doppelter Kopf raus, Ort/Datum rechtsbündig, Grußformel+Name eng, garantiert **1 Seite**, Calibri 10,5 pt wie im CV, Typo-Hierarchie (Name 16 pt · Betreff 12 pt fett); CV-Fußzeile jetzt sprachabhängig („Page X of Y" / „Seite X von Y") | ✅ |
| — | **Report-Selbstprüfung** `pipeline/report_check.py` gegen den lautlosen CSS-Drift generierter Reports (s. Abschnitt 8) + Pflichtschritt in `cv-erstellen`; Gesamtbestand (289 Reports) bereinigt | ✅ |
| **55** | **ATS-Score v2**: Score = Optimierungsgrad statt nackter Keyword-Abdeckungsquote (Formel 60 % Keyword-Optimierung + 25 % Titel-Alignment + 15 % Format; Roh-Quote x/15 bleibt separat sichtbar) · **EINE Keyword-Liste** (15 Begriffe, feste Kategorien, klassifiziert `abdeckbar` true/false mit Beleg/Grund), erzeugt in `cv-match` (`CVVersion.keywords_json`), wiederverwendet in `cv-erstellen` statt zweiter Extraktion · **einmalige Feedback-Schleife** für abdeckbare, aber nicht eingearbeitete Begriffe. Fallback für Alt-Entwürfe ohne `keywords_json` (Methodik v1, einmalige Erhebung im Scan) | ✅ |
| **56** | **Repo-Struktur & Git**: Drei-Ebenen-Trennung (Code-Bereich versioniert · persönliche Inhalte lokal in `data/`+`outputs/` · Git-Interna bei iCloud-Ablage in `.git.nosync/` vom Sync ausgenommen) · DB nach `data/bewerbung.sqlite` (`BMS_DATA_DIR`-Override) · Dokumente nach `outputs/cv|anschreiben|exports` · Doku nach `docs/`, Report-Theme nach `assets/` · `backup_db.sh` mit Rotation | ✅ |
| **57** | **Tests & CI**: 36 pytest-Tests (Isolation über `BMS_DATA_DIR`-Wegwerf-DB, rein synthetische Fixtures) · GitHub-Actions-CI mit 3 Jobs (backend py3.9 · frontend node24 · secret-scan gitleaks) · pre-commit-Secret-Hook aus Bordmitteln · Prozessregel „Abnahme erfordert grünes CI" (s. Abschnitt 8, „Tests & CI") | ✅ |
| **58** | **Python-Upgrade 3.9 → 3.12**: venv-Neubau am selben Pfad (`~/.bewerbung_mgmt_venv`) auf Homebrew-Python 3.12.13, identisches Lock (`requirements-lock.txt`, null Abweichungen) · CI-Pin auf 3.12 gehoben · Rollback-venv `~/.bewerbung_mgmt_venv_py39_backup` bleibt erhalten · PDF-Smoke (LibreOffice-Konvertierung) unter 3.12 erstmals real geprüft | ✅ |
| **59** | **Dependency-Update**: Backend-Lock frisch aufgelöst (`fastapi` 0.128.8→0.140.0, `uvicorn`→0.51.0, `sqlmodel`→0.0.39 · `starlette` 0.49→1.3.1 transitiv MAJOR · `pytest`→9.1.1 MAJOR, Tests grün; `pydantic`/SQLAlchemy/`cryptography` unverändert) · 8 nie gebrauchte `uvicorn[standard]`-Altreste raus (uvloop/websockets/watchfiles/httptools/jinja2/python-dotenv/MarkupSafe/exceptiongroup — kein Code-Import, `loop="asyncio"/http="h11"` bleibt ohnehin hart gesetzt) · Produktiv-`venv` nach dem README-Rezept „Rollback & Reparatur" neu gebaut (live validiert) · Frontend **semver-safe** (`npm update` innerhalb bestehender `^`-Ranges; React 18 / Vite 5 / Tailwind 3 / TS 5.x bewusst gehalten, Major-Bumps vertagt) | ✅ |
| **61** | **Mail-Zuordnung repariert (P0-1 aus dem Code-Review)**: `gmail_ingest._match_job` nutzt jetzt eine Eindeutigkeitsregel statt Raten — gelöschte Jobs sind nie Kandidat, exakter `ct_key`-Vergleich zuerst, dann kalibrierte `dedup_text.titel_aehnlichkeit()` (Schwelle 0.5, gegen die 8 realen Kollisionsfälle der Live-DB gemessen) statt des alten 20-Zeichen-Präfix-Fallbacks; mehrere gleichwertige Kandidaten → Sentinel `_MEHRDEUTIG` statt Rateentscheidung, Mail bleibt firmenbezogen ohne Stelle, eigener Zähler in der Ingest-Zusammenfassung (Stufe A) · **Altbestand-Diagnose** (Stufe B, read-only, `mode=ro`-Schreibschutz): systematischer Titel-Ähnlichkeits-Scan aller Firmen mit ≥ 2 Jobs (12 Cluster, 26 Jobs) plus gezielte Prüfung der 3 im Code selbst benannten Fälle für die andere Bugursache (gelöschte Jobs als Kandidat) — 5 Kandidaten mit tatsächlicher Mail-Anbindung geprüft, 4 unauffällig, 1 Fund (Atos: 2 Mails an einem zwischenzeitlich gelöschten Job geparkt, keine Statusüberschreibung, Empfehlung zum manuellen Umhängen) · vollständiger Befund inkl. der Rekonstruierbarkeits-Analyse in `tasks/phase61b_altbestand_diagnose.md` | ✅ |
| **62** | **Beirat: Budget-Guard + ehrliche Fehlerbehandlung** (P1-4/P1-5/P2-5 aus dem Code-Review): 62A — `_guard_tagesbudget()` (Tages-/Monatslimit + Not-Aus) greift jetzt auch an beiden Beirats-Einstiegen (`beirat_debatte_starten`, `_beirat_stellen_check_starten`, laut Docstring gemeinsamer Kern mit `create_task`) — vorher liefen 72 Läufe/129,62 $ ungeprüft am Guard vorbei · 62B — `_turn_anthropic` prüft jetzt `is_error`/`api_error_status` (neue reine Hilfsfunktion `_result_event_auswerten`, testbare Naht; `subtype` bleibt bei einem API-Fehler oft irreführend `"success"`, real belegt in `data/agent_logs/task_342.jsonl`) und wirft statt die Fehlermeldung als Beitragstext zu speichern (real vorgekommen: `data/beirat/2026_07_23_2126_0e843f.json`, Beitrag der Vorsitzenden = reiner Session-Limit-Fehlertext); Dispatch- und Persona-Turn bekommen dafür das im File etablierte Muster „1 Versuch + 1 Retry" (wie Abstimmung/Synthese) — bleibt der Dispatch danach kaputt, bricht die Debatte ehrlich ab (`status="fehler"`), ein Persona-Kopf wird stattdessen ausgelassen und die Debatte läuft weiter (moderationen/beitraege bleiben dabei strikt parallele Listen) · 7 neue Tests (`test_beirat_fehler.py`), 54→61 grün | ✅ (A+B) |
| **63A** | **Datenschutz-Härtung: Secrets aus dem Sync-Bereich** (P1-2 aus dem Code-Review): die vier Pfad-Konstanten für Gmail-Secrets (`gmail_client.CRED_FILE`/`TOKEN_FILE`) und `agent.env` (`agent_runner.ENV_FILE`, `apify_client.ENV_FILE`) zeigen jetzt auf `~/.bewerbung_mgmt_secrets/` (Verzeichnis `chmod 700`, Dateien `chmod 600`, Override `BMS_SECRETS_DIR`) statt auf `automation/` im iCloud-synchronisierten Projektordner — gleiches Muster wie `beirat_engine.KEY_DIR`. Migration nach D1-Reihenfolge (kopieren → über die Credential-Kette verifizieren, KEIN Postfachzugriff → Originale nach `data/papierkorb/phase63_secrets/` verschieben → erneut verifizieren); dabei den Token-Refresh-SCHREIBpfad (`gmail_client._save_token`) mitgezogen (Verzeichnis wird bei Bedarf mit 700 neu angelegt) und einen Folgefehler in `cmd_auth()` behoben (`TOKEN_FILE.relative_to(PROJECT_ROOT)` hätte nach dem Umzug geworfen). 6 neue Tests (`test_secrets_pfade.py`), 61→67 grün | ✅ |
| **63B** | **Datenschutz-Härtung: Agent-Logs aus dem Sync-Bereich** (P1-3 aus dem Code-Review): `agent_runner.LOG_DIR` zeigt jetzt auf `~/.bewerbung_mgmt_logs/` (Verzeichnis `chmod 700`, Dateien `chmod 600`, Override `BMS_LOG_DIR`) statt auf `data/agent_logs/` im iCloud-synchronisierten Projektordner — der rohe Ausgabestrom jedes Laufs enthält gelesene CV-Inhalte und Mail-Volltexte im Klartext. **Kern der Stufe (Invariante D3):** die 377 zum Migrationszeitpunkt bereits in der DB stehenden `AgentTask.log_path`-Werte werden NICHT umgeschrieben (Risiko ohne Gegenwert) — stattdessen löst die neue Funktion `agent_runner.resolve_log_path()` jeden gespeicherten Wert auf (zuerst `LOG_DIR / <Basename>`, sonst der alte projekt-relative Pfad als Fallback); `log_path` ist damit semantisch ein BEZEICHNER, kein wörtlicher Pfad mehr — neue Zeilen speichern nur noch den Basename. Beide Schreiber (Runner `_run_task` UND die In-Server-Beirats-Engine `beirat_engine._task_anlegen`/`_log_zeile`, die bisher unabhängig denselben Ordner hart kodiert hatte) teilen sich jetzt `neue_log_datei()` (chmod 700/600, Muster aus `gmail_client.py`) und importieren `LOG_DIR` aus einer einzigen Quelle. Rotation (`cleanup_logs()`, 30 Tage unverändert) lief bisher nur beim Serverstart — läuft jetzt zusätzlich nach jedem Task-Abschluss, gedrosselt auf höchstens 1×/Stunde (`_cleanup_logs_gedrosselt()`, kein neuer Hintergrund-Task). Migration: 379 Bestandsdateien (111 MB) verschoben, `data/agent_logs/` danach leer, alle Dateien `chmod 600`; live über `GET /api/tasks/{id}?tail=…` verifiziert (Altbestand liefert HTTP 200 mit Inhalt über den Fallback-Pfad, ein frisch angelegter Task liegt direkt im neuen Ort, `log_path` ist nur der Basename). 15 neue Tests (`test_log_pfade.py`, u. a. Auflösung neu/alt/Priorität/fehlend, Rechte, Rotation, Zeitsperre), zusätzlich `backend/tests/conftest.py` um dieselbe `BMS_LOG_DIR`-Tmp-Isolation wie `BMS_DATA_DIR` ergänzt (schließt einen dokumentierten T1-Risikopfad im `client`-Fixture-Docstring), 67→82 grün | ✅ |
| **64** | **Fehler im Fehlerpfad: sichtbar und überlebbar statt still** (P1-7, P2-1, P2-19, P2-20 aus dem Code-Review; Leitsatz: ein Fehler darf laut sein und abbrechen, aber nie unsichtbar sein oder etwas dauerhaft lähmen) — 64A: alle sechs Lösch-Endpunkte committen die DB-Änderung jetzt VOR dem Datei-Move statt danach (scheitert ein Move, entsteht eine verwaiste Datei statt einer toten DB-Referenz — Orphans fließen bereits in die Cleanup-Alarmschwelle, tote Referenzen bisher nicht); jeder Move-Fehlschlag wird PRO DATEI gefangen, gezählt und laut gemeldet, statt die übrigen Dateien zu blockieren oder den Commit zurückzurollen; `pipeline/cleanup.py` nimmt `dangling_referenzen > 3` zusätzlich in die `auffaellig`-Schwelle auf · 64B — drei weitere stille Fehlschläge hörbar gemacht: `agent_runner._worker()`s `while True`-Schleife übersteht jetzt jede Exception, die aus `_run_task()` entkommt (P2-1; vorher beendete ein Fehlschlag im Fehlerpfad selbst — z. B. ein scheiternder DB-Commit — die Schleife FÜR IMMER, `_workers` wird nie wieder gelesen, kein Supervisor; alle künftigen Tasks blieben lautlos „queued"), zusätzlich schlucken die Fehlerpfad-Helfer `_update`/`_fehlschlag`/`_finish` selbst einen gescheiterten Commit und melden ihn laut statt ihn weiterzuwerfen (Restrisiko dokumentiert: die betroffene Task-Zeile kann bis zum nächsten Serverneustart auf altem Stand hängen bleiben) · `db._ensure_columns()` meldet einen fehlgeschlagenen `PRAGMA table_info`-Aufruf jetzt mit Tabellenname statt ihn spurlos zu überspringen (P2-19); der innere `ALTER TABLE`-Zweig ist neu idempotent gegen den Mehrprozess-Fall abgesichert (seit Phase 63 startet jeder Skill-Lauf `init_db()` im eigenen Subprozess, SQLite kennt kein `ADD COLUMN IF NOT EXISTS`) — „duplicate column" bleibt bewusst leise, jeder andere Fehler ist laut · `beirat_engine.Debatte.laufen()`s `finally`-Block fängt einen scheiternden `_task_abschliessen()`-Commit jetzt ab und meldet ihn laut; `await self.queue.put(None)` (SSE-Ende-Signal) läuft dadurch in JEDEM Fall (P2-20; vorher blieb die AgentTask-Zeile bei einem Fehlschlag auf „running" hängen — blockiert den Doppellauf-Guard bis zum Neustart — UND der Stream zur Oberfläche endete nie). 20 neue Tests (`test_loeschen_reihenfolge.py` 13 Fälle + `test_fehlerpfade.py` 7 Fälle, Fehlerpfade selbst per Monkeypatch erzwungen, kein echter Beirats-/Skill-Lauf), 82→102 grün | ✅ (A+B) |
| **65** | **Prozess-Tracking über Server-Neustarts (P1-6 aus dem Code-Review)**: neue additive Spalte `AgentTask.pid` — direkt nach dem Subprozess-Start gesetzt+committet, bei jedem Abschluss (Erfolg/Fehlschlag) und vor jedem Retry-Requeue wieder geleert · neuer Shutdown-Hook (`@app.on_event("shutdown")`, `agent_runner.shutdown_kill_all()`) beendet beim geordneten Neustart alle noch verzeichneten Kindprozesse — bewusst OHNE Identitätsprüfung (eigene Handles derselben Prozess-Lebenszeit, Begründung im Code als Asymmetrie zur Startup-Prüfung) · Crash-Recovery beim Start ersetzt das bisherige bedingungslose „running" → „failed" (dessen Kommentar „ein früherer Prozess ist tot" nachweislich falsch war — ein gewöhnliches Ctrl+C genügt, um einen `claude -p`-Prozess wegen `start_new_session=True` verwaist weiterlaufen zu lassen) durch vier Fälle: keine PID hinterlegt / PID tot / PID lebt aber fremd / PID lebt und bestätigt. **P1 — Fremdprozess-Schutz** (die härteste Regel dieser Phase): eine gespeicherte PID ist kein dauerhafter Ausweis, da sie nach einem Neustart längst einem fremden Mac-Programm gehören kann — beendet wird NUR, wenn ZWEI unabhängige Merkmale übereinstimmen (Kommandozeile per `ps -p <pid> -o command=` gegen das für die Task-Art erwartete Kommando UND Startzeitpunkt nicht vor `started_at`, 2s Toleranz gegen Sekundenrundung), sonst bleibt der Prozess unangetastet und es gibt eine laute Warnung; eigene testbare Funktion `_ist_unser_prozess()`, kein `psutil` (nur `ps` + `os.kill`) · `beirat_engine` bekommt bewusst KEIN PID-Tracking (ausführliche Begründung im Code bei `_task_anlegen()`: Debatten laufen als In-Server-Coroutine ohne einen einzelnen langlebigen Kindprozess, jeder Turn-Subprozess hat `--tools ""` und ein leeres `cwd` außerhalb des Projekts — kann strukturell nicht in DB/`outputs/` schreiben, selbst wenn er einen Absturz kurz überlebt). 7 neue Tests (`test_prozess_tracking.py`, zentral: ein echter harmloser Wegwerf-Prozess (`sleep`) übersteht die Recovery unbeendet, Zeile wird trotzdem `failed`), 102→109 grün | ✅ |
| **66** | **Sandbox-Härtung (P1-1 aus dem Code-Review) — Schadensbegrenzung statt vorgetäuschter Sicherheitsgrenze:** 66A — `agent_runner._child_env(kind)` reicht pro Skill-Subprozess nur noch die für diese Art freigegebenen Secrets aus `agent.env` weiter (`SECRET_KEYS_BY_KIND`, aktuell einzige Zeile `jobsuche-apify` → `APIFY_TOKEN`) statt bisher jeden Schlüssel an jeden Subprozess, mit lauter Meldung im Task-Log bei zurückgehaltenen Schlüsseln; 9 von 22 headless-Arten bekommen zusätzlich `disallowed_tools` (WebSearch/WebFetch gesperrt, wo der Skill sie laut Code/SKILL.md/Log-Historie nachweislich nicht braucht) — Freigabeliste selbst (`Bash(curl:*)`/`Bash(python:*)`) bewusst unverändert (Begründung: „Die ehrliche Ausgangslage" in der Bau-Spec Phase 66, s. Abschnitt 8 oben) · 66B — Fremdtext-Kennzeichnung: `agent_runner.HEADLESS_SUFFIX` markiert jeden per WebFetch/WebSearch/curl/gmail_client geladenen Fremdtext ausdrücklich als Datenmaterial statt Anweisung (gilt für JEDEN headless-Prompt), ergänzt an den zwei konkretesten Einbettungsstellen (`firma-pruefen`/SKILL.md Anzeigen-Snapshot, `email-check`/SKILL.md Mail-Klassifikation) — Hygiene, keine Garantie; neues `scripts/outbound_check.py` (nur lesend, kein Automatismus) listet ausgehende Ziele aus den Agent-Logs gegen eine gepflegte Erwartungsliste, in diesem Dokument unter „Betrieb im Alltag“ beschrieben; Restrisiko ausdrücklich dokumentiert (dieser Abschnitt + `automation/agent_settings.json`-`$comment`) — offen bleiben der `gmail.compose`-Scope (Grenze ist der fehlende Codepfad) und die datei-basierte Gmail-Zugriffslücke (66A kann sie strukturell nicht schließen). 21 neue Tests (`test_outbound_check.py`), 124→145 grün | ✅ (A+B) |

Die Tabelle endet bewusst bei Phase 66: Änderungen seither (Phase 67 ff., u. a. Karriereseiten-
Fallback, Beworben-Check, Anzeigen-Snapshot-Renderer, Styleguide-§18-Rollout, Coach-Site) sind
direkt in die Abschnitte 1–9 eingearbeitet statt hier als wachsende Liste angehängt — das laufende
Änderungsprotokoll je Phase führt der Autor in seinem Projektverlauf (nicht Teil des öffentlichen Repositorys), kompakt gespiegelt in `docs/WAS_IST_NEU.md`.

### Arbeitsmodus

Features werden als **self-contained Bau-Spec** geplant (im Projektverlauf des Autors, nicht im öffentlichen
Repository); eine andere KI-Session baut sie um. Kleine Fixes werden direkt erledigt. Verworfene Phasen bleiben mit
Begründung dokumentiert (Messdaten als Referenz).

---

*Zuletzt nachgezogen am 01.10.2026 (P2-59, P2-60, P2-62); der Abschnitt „Lizenz“ am 29.10.2026
(P2-82, ausgebaut) und der Abschnitt „Update-Auskunft über GitHub-Releases“ am 29.10.2026 (P2-82, vorher
„Paketdienst und Netzregeln“, 13.10.2026, P2-71), der Abschnitt „Profil-Datei“ am 11.10.2026 (P2-69), die Absätze „Anzeigentext sichern" und „Portal-Status" am 14.10.2026 (P2-75, P2-76). Da parallele Bau-Sessions laufen,
ist die zentrale Quelle immer der Code selbst, nicht diese Datei.*
