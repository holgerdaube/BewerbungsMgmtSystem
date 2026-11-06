# BMS – Job Application Management System — System Documentation

*Developer documentation · local web app for your own job search · last updated 29.10.2026*

> **Context.** This file is the technical documentation of the project. It cites build specs (e.g. “P2-75”) and
> phases as development history. The underlying material (`tasks/`) is the author's working material and does not belong in the
> public repository; the description here is self-contained. The code is always authoritative: where this file and
> the code contradict each other, the code applies.

---

## 1. What is the system?

The BMS – Job Application Management System (BMS) is a **local web app** that brings the entire
job search of one person together in one place: finding and scoring jobs, checking companies, producing application
documents, preparing for and following up interviews, tracking email replies, maintaining the network
and learning from all of it.

It is deliberately not an autonomous application robot but a **human-in-the-loop** tool:
the system finds, scores and manages — **the user decides**. Nothing is sent without approval,
no application is made without review, no facts are invented.

### The central idea: Claude-in-the-Loop

Instead of external API keys and expensive services, the “intelligence” of the system is Claude itself.
So-called **skills** (search, scoring, company check, CV tailoring, Gmail analysis …) are triggered
by a plain-text sentence and write their results to **the same central database** that
the web app reads from. There are two modes of operation:

- **Interactive** — In a Claude session, the user says e.g. “Company check for job <no.>”, and Claude
  runs the skill.
- **Headless** — the web app uses the agent runner to start the same skill as a background run
  (`claude -p "<trigger sentence>"`), e.g. via the “▶ Run” button on the job.

Both ways use exactly the same skills and write to the same DB — there is no second
source of truth.

### Two AIs: Claude or ChatGPT (P2-86)

Runs go either through Claude Code (`claude -p`, the default) or through OpenAI's Codex CLI
(`codex exec`, ChatGPT, a preview in the first release). The choice is made in `sucheinstellung.ki_anbieter`
(`claude` | `chatgpt`) via `GET/PATCH /api/einstellungen` and the “AI” card in Settings; the
installation guides ask for it in step 0. `GET /api/ki-status` reports for each provider whether the
program is installed and signed in, and never reads a key. Queue, chains, timeout and
cancellation remain shared in `agent_runner`; `app/ki_anbieter.py` holds what differs:

- **Call and environment:** `codex_argv` builds `codex exec --json` with the `workspace-write` sandbox, network on
  and the prompt via standard input. `codex_prompt` names the skill explicitly,
  `codex_umgebung` removes `OPENAI_API_KEY`, `CODEX_API_KEY` and the Claude variables: the
  machine's sign-in applies (`codex login`, the subscription), never a separately billed key. The
  program finds the BMS via `CODEX_BIN` or the PATH.
- **Skills:** `.claude/skills` remains the only source. `skills_spiegeln` copies them before every run
  to `.agents/skills` (not versioned), where Codex looks. `AGENTS.md` in the project translates the
  tool names of the skills (WebSearch, WebFetch, Read, Write, Edit, Task); the skills themselves
  still use those of Claude Code.
- **Evaluation:** `CodexAuswertung` turns the JSONL stream into the result that the runner knows from
  `claude -p`. It recognises a reached subscription limit and a missing sign-in from the error text
  (`abo_limit`, `anmeldung`).
- **PDF:** LibreOffice aborts in the Codex sandbox. `codex_umgebung` therefore sets `BMS_PDF_UEBER_SERVER`, and
  `cv_export` has the server convert outside the sandbox (`POST /api/intern/pdf`, only Word files from the program and data folders).
- **Costs:** Codex reports no costs in dollars, and tokens only at the end of the turn. Under ChatGPT,
  `AgentTask.cost_usd` stays 0, usage is recorded in `AgentTask.tokens`, and there is no budget limit per
  run. Protection comes from the run's timeout, the limits of the subscription and the daily limit for runs.
- **Models:** The tiers `opus`, `sonnet`, `haiku` remain what is stored; `CODEX_MODELL` maps them to the
  Codex models (§8 “AI models”). Fable is never selectable.
- **Permissions:** The hooks and approvals from `automation/agent_settings.json` and the path guard apply only to
  Claude Code. Under ChatGPT, the sandbox restricts writing to the project, the log folder (plus
  the data folder, if it is outside the project) and, for email runs, the credentials folder. It allows reading across the whole user folder, including
  `~/.bewerbung_mgmt_secrets`: a run has no need to go there, but it is not prevented.

### Guide to the documents

In the running app, the menu item **“📖 Documentation”** shows the user documents in tabs: Version
(`CHANGELOG.md`), Features, Guide, Installation & Updates (the file for the running system:
`BMS_Install_Windows.md` on Windows, otherwise `BMS_Install_MAC.md`), Set up email, Windows, Coach site
and Advisory Board. In a development installation, after the “Internal” separator come Technology (this file),
Automation, Release and Developer installation. Which file sits behind which tab is set by the catalogue
in `backend/app/doku.py`; only the user documents go into the user package (`DOKU_ERLAUBT` in
`backend/pipeline/kundenpaket.py`). They therefore never refer to internal files and carry no
phase numbers (guard: `backend/tests/test_kundendoku.py`).

- **`docs/ANLEITUNG.md`** — Operation & daily processes (what the skills do, what each area of the
  interface does).
- **`docs/FUNKTIONEN.md`** — Short overview: what the BMS can do, organised by work step.
- **`docs/INSTALLATION.md`** — Developer installation from scratch (Windows and macOS) and setting up
  your own person. The versions for users (formal “Sie” form, guided by Claude, with updating) are
  `BMS_Install_MAC.md` and `BMS_Install_Windows.md` in the main folder.
- **`docs/DOKUMENTATION.md`** — this file: architecture, data model, skills, operation, security.
- **`docs/AUTOMATION.md`** — Status of the time-based automation (prepared, not active).
- **`docs/RELEASE.md`** — Versions, approval, package build, publishing.
- **`docs/BEIRAT-CHARTA.md`** / **`docs/BEIRAT-PERSONA-TEMPLATE.md`** — Rules and persona template of the
  application Advisory Board.
- **`docs/SETUP-WINDOWS.md`** — Windows specifics from the user's point of view: start, stop, update, known
  limits, support matrix. The installation itself is in `BMS_Install_Windows.md`; the developer route
  under Windows is in `docs/INSTALLATION.md` part 1.
- **`docs/SETUP-EMAIL.md`** — Setting up the email account (route A: IMAP with app password, also for Gmail; route B:
  Gmail API with your own Google Cloud project). Strategic background: **`docs/GMAIL-STRATEGIE.md`**.
- **`docs/ANLEITUNG_COACH_SITE.md`** — Setting up the coach site, step by step and without prior knowledge
  (own subdomain, SFTP, coach login). Technical background and operation: **`docs/COACH_SITE.md`**.
- **`docs/WAS_IST_NEU.md`** — Change log of the larger development steps, newest first.

**Every document in `docs/` exists twice:** the `.md` is the source, the `.html` of the same name is generated
from it (printable, for passing on). After every change to an `.md`, run
`scripts/docs_html.sh`. A test (`backend/tests/test_docs_html.py`) checks that every `.md` has a
matching, current `.html` — anyone who forgets to generate it will see it from a red CI.

---

## 2. Architecture & technology

| Layer | Technology |
|---|---|
| **Backend** | FastAPI (Python) + SQLite — `data/bewerbung.sqlite` is the **single source of truth** (~9 MB, 27 tables + FTS5 search index) |
| **Frontend** | React + Vite + TypeScript + Tailwind; status colours derived canonically from the Daube.Tech style guide (`ui.tsx::STATUS_FARBEN`, cyan→navy ladder); brand colours, fonts, icon and product name come from the design at runtime (`GET /api/design.css`, see §8 “Design from a single source”); built to `frontend/dist`, served by the backend |
| **Deterministic logic** | 32 pipeline modules in `backend/pipeline/` (ingest, dedup, mail [Gmail/IMAP], export, search, verification, LinkedIn import, search profile writer, report check, coach site export …) — no LLM, reproducible |
| **Intelligence** | 24 skills in `.claude/skills/` (Claude format; for ChatGPT mirrored to `.agents/skills` before every run, see “Two AIs”) |
| **API** | 137 REST endpoints |

**Why SQLite as the single source?** Everything — jobs, companies, applications, emails, contacts,
interviews, transcripts, budget, agent runs — lives in one file. Skills and web app share it;
what a skill writes appears in the app immediately. No synchronisation, no server zoo.

### Starting

```
start.command              (Doppelklick — lokal, http://localhost:8000)
start_lan.command          (fürs Handy im selben WLAN — keine Auth, nur vertrautes Netz)
```

or manually:

```
cd backend && PORT=8000 ~/.bewerbung_mgmt_venv/bin/python run_server.py
```

### Environment pitfalls (important)

- **iCloud Drive (only if the project is located there):** Sandboxed processes (Claude Code preview panel,
  launchd/cron without “Full Disk Access”) **cannot** read iCloud. The app
  then runs only via Terminal / `start.command`. Outside iCloud the restriction does not apply.
- **Frontend build in iCloud:** There, NEVER run `npm run build` directly in the project — iCloud rematerialises
  `node_modules` and destroys symlinks. Use `frontend/build.sh` instead (it builds outside iCloud under
  `~/.bewerbung_mgmt_node/` and copies only `dist` back). If the project is not in iCloud, `npm ci && npm run build` in `frontend/` is enough.
- **venv** is located outside the project, under `~/.bewerbung_mgmt_venv`.
- **PDF export:** LibreOffice headless (`soffice --headless --convert-to pdf`), not Word —
  deterministic, no window, no automation approval.

### Project structure and storage locations

The project folder separates the versioned code from the personal content of an installation.
`.gitignore` is always authoritative, not the folder name.

- **Code, versioned (Git):** `backend/` (FastAPI app, pipelines, DB layer), `frontend/` (React/Vite source),
  `.claude/` (skills, slash commands, Advisory Board subagents), `docs/` (guide, system documentation, Advisory Board charter),
  `assets/` (report theme as CSS master, logo/icon), `scripts/` (operation scripts), `automation/`
  (template `agent.env.example`, guardrail configuration `agent_settings.json`), `.env.example`,
  `.gitignore`, the start files (`start*.command`, `start_windows.bat`, …) and `README.md`.
- **Personal content, purely local (never in Git):** `data/` (the SQLite DB, backups, company fit dashboards,
  digests, transcripts, Advisory Board minutes, bin …), `outputs/` (generated CVs and cover letters as
  `.docx`/`.pdf`) and the personal files in `config/` (`profil.md`, `zielfirmen.md`,
  `suchprofile.yaml`, `budgets.yaml`). `config/` is mixed: `scoring_rubrik.md` (scoring rubric, with
  an example target profile) and `coach_export.yaml` are versioned; `profil_struktur.md` is generated by the app
  itself from the database (at start-up if it is missing, and on every save of the profile page) and
  is not versioned, because it contains the career history.
- **Secrets, outside the project:** `agent.env` (Claude OAuth, Apify token; ChatGPT does not need them,
  the sign-in is held by Codex itself), the Gmail tokens
  (`gmail_credentials.json`, `gmail_token.json`), the mail account settings (`mail_settings.json`) and
  the coach site configuration (`coach_settings.json` together with the coach credentials file `coach_htpasswd`; the older
  `coach_sftp.env` remains as a fallback) are located under `~/.bewerbung_mgmt_secrets/` (directory
  `chmod 700`, files `chmod 600`; override `BMS_SECRETS_DIR`), not under `automation/`. Reason: anything in the
  project folder would otherwise sit on every device of the same account when stored in a sync folder (e.g. iCloud).
- **Task logs, outside the project:** The raw output stream of every agent run (runner process as well as
  Advisory Board engine) — including CV contents read and full email texts in plain text — is located under
  `~/.bewerbung_mgmt_logs/` (directory `chmod 700`, files `chmod 600`; override `BMS_LOG_DIR`).
  Since then, `AgentTask.log_path` is an IDENTIFIER, not a directly usable path;
  `agent_runner.resolve_log_path()` resolves it (new location first, old project-relative path as
  fallback).
- **Git internals when stored in iCloud:** If the project is in iCloud Drive, the Git directory can be moved out as
  `.git.nosync/` (`git init --separate-git-dir`; `.git` in the project root is then only a
  pointer file), because Git internals (objects, refs, locks) do not tolerate live sync. Outside iCloud this is
  not necessary.

---

## 3. Basic principles

These principles run through the whole system and explain many design decisions:

1. **Human-in-the-loop.** Nothing irreversible happens without the user's approval. Emails are
   **never sent**, only created as a Gmail **draft**. No automatic applications
   (phase 15 “Auto-apply” was deliberately dropped).

2. **Anti-hallucination.** Skills with a research component work with evidence and verbatim quotes. “Not
   available” instead of guessing. Decisions the system must not make (appointments, acceptances) are
   marked as `[BITTE PRÜFEN: …]` placeholders (“please check”).

3. **Four-eyes principle for job hits.** Every job found must pass a **verification gate**
   before it may enter the DB: a mechanical URL checker (`verify_jobs.py`) plus a
   separate, adversarial review subagent confirm existence and currency. A mere
   free-text warning in the finding does not protect — only a gate that the ingest enforces.
   Trust matrix: Apify, mail alert and Nejo URLs are treated as authentic; URLs constructed by WebSearch
   need a canonical posting, otherwise they are not ingested.

4. **Dedup depends on retained rows.** “Discarded → No match” remains in the DB as a tombstone,
   so that the same hit (same link) does not reappear as “New” the next day. The same
   logic applies when deleting jobs (soft delete, phase 32). Since P2-36 the ingest distinguishes:
   the same posting (same link), every further posting for a job that is still running, and
   hits in the bin remain blocked. A NEW posting of the same job (company + title, gender suffix ignored) for a job in a final status, however, appears as “New” again, with the note
   `NEUAUSSCHREIBUNG?` (“re-posting?”). Case A: A job “Head of Customer Success (m/w/d)” had been sorted out as No
   match; the new posting “(m/f/d)” came two weeks later and led to an
   application. A plain block would have silently discarded it. Since P2-39 the company name is additionally
   normalised for the comparison (legal-form and region suffixes such as GmbH/SE/Deutschland/EMEA
   removed), so that two spellings of the same company do not slip past two different company rows (measured on a real data set, 12.09.2026: 15 company groups collapse, 5 genuine
   job pairs now come together, 0 false alarms). Case B: Two spellings of the same company
   (“Beispiel” and “Beispiel GmbH”) — three jobs hung on two company rows for the same employer;
   every duplicate stage missed the match until the company spelling itself was normalised.

5. **Budget guardrails.** Real money (Apify) has hard daily limits ($0.50/day,
   `BudgetLimit` table). The headless Claude runner runs on the Max subscription (virtual money),
   but has outlier brakes (per-run cap, tasks/day). Under ChatGPT there are no costs in dollars
   and no cap per run (Codex reports tokens only at the end of the turn); the brakes are timeout,
   subscription limit and tasks/day.

6. **Derived views instead of write triggers.** Excel export, daily digest, full-text search index and,
   since phase 81, the coach site export can all be rebuilt completely (`refresh_views.sh` and
   `coach_site.sh` respectively), instead of being spread across ten write points. Their build state is visible (staleness
   is shown, not hidden). The Excel export itself now additionally shows the
   0–100 CV match score, the reason for sorting out (from “Notes & history” instead of an empty column) and
   the Advisory Board rating as a coloured number (phase 75). Since P2-81 the “Applications” sheet shows,
   for each job applied for, the date found, the application date, the date of each interview round 1–6
   (`interview.scheduled_at`, alternatively `transcript.recorded_at`) and the rejection date (earliest
   rejection email, alternatively the status change in the history, as a local calendar day).

7. **One activity log for everything.** Every background activity — runner skill as well as
   in-server engine (Advisory Board) — writes its own `AgentTask` row (status, log, duration,
   cost). The Task Centre reads only this table and thus shows EVERYTHING automatically;
   no parallel bookkeeping (phase 42).

8. **Only for the applicant.** The BMS supports only the side that is applying. Functions with which employers evaluate, sort or select applicants are not
   included: they would fall under the high-risk rules of the AI Regulation (AI Act, Annex III
   no. 4). Taken over from the former sales checklist when it was dropped on 29.10.2026.

---

## 4. Data model


27 SQLModel tables in `backend/app/models.py`, plus an FTS5 full-text search index. Core relationships:

```
Company 1─* Job 1─* Application 1─* Email
Company/Job 1─* Contact
Job 1─* CVVersion · Interview · Transcript · JobFile · JobLog · JobChat
```

One pattern runs through it: “messy” real-world values (status, situation, level) are stored
**twice** — a normalised field for filtering/analysis plus a `*_raw` field
that preserves the original text.

### The most important tables

| Table | Purpose | Key fields |
|---|---|---|
| **Company** | Company | `situation` (BUILD/CARVE-OUT/PE/…), `fit_analysis_path`, `fit_ampel` (`grün`/`gelb`/`rot`: green/yellow/red), `is_radar` |
| **Job** | Job | `match_score` (1–5 = **target-role fit**, scoring rubric `config/scoring_rubrik.md`; not to be confused with `CVVersion.match_score100`), `gut_feeling` (1–5), `status`, `follow_up_date`, `verify_note` (four-eyes finding + source conflicts), `posting_snapshot_path`, `dedup_key`, `career_url`/`portal_closed` (career page fallback, phase 73), `availability_status`/`availability_checked_at` (applied-jobs check, phase 74) |
| **Application** | Application | `channel`, `cover_letter_path` (+PDF), `status`, `rejection_reason` |
| **Email** | Mailbox entry | `direction`, `category` (`Einladung`/`Absage`/…: invitation/rejection/…), `response_time_hours`, `needs_reply`, `reply_draft_at` |
| **Contact** | Contact person | `role` (`Recruiter`/`Hiring Manager`), `email`, `linkedin_url` |
| **CVVersion** | Tailored CV | `language`, `file_path` (docx) + `pdf_path`, `ats_score`, `match_score100`, `match_dashboard_path`, `ats_scan_path` |
| **Interview** | Interview | `runde` (round), `art` (`HR-Screen`/`Fachgespräch`/…: HR screen/technical interview/…), `scheduled_at`, `status`, `prep_path` (briefing) |
| **NetzwerkGespraech** *(phase 69)* | Conversation without a job | Counterpart to `Interview` without the `job_id` requirement — network/headhunter calls without a posting; `gegenueber` additionally `"Netzwerk"` |
| **Transcript** | Notes of a conversation | `file_path`, `summary`, `todos_json`, `report_path` (transcript report), `debrief_path` (legacy) |
| **JobFile** | Attached file | generic (transcript/job description/presentation), optionally linked to a Transcript row |
| **JobLog / JobChat** | History & AI chat per job | chronological notes (`auto`/`manuell`/`ki-chat`: auto/manual/AI chat); question–answer history |
| **Outreach / OutreachLog** | Networking tracker | taken over once from an Excel list (former one-off migration, the tool has been removed), maintained in the app since then, no create endpoint; activity log |
| **TargetCompany / Headhunter / NetworkContact** | the three network lists | `karriere_url`, `last_career_check` (sweep rotation), `deleted_at` (soft delete) |
| **AgentTask** | Headless agent run | `kind`, `status`, `cost_usd`, `duration_s`, chain fields (`chain_id`, `depends_on`) |
| **ApiCost / BudgetLimit** | Budget | costs per service & day; editable limits (hard/soft) |
| **AlertMail** | Job alert processing | guarantees single processing (`gmail_message_id` unique) |
| **Run** | Run log | per job search/email check: found/new, response times |
| **Profile** *(phase 45)* | Candidate profile (singleton id=1) | `linkedin_url`, `headline`, `standort`, `positionierung`, `linkedin_eingelesen_am` |
| **ProfileSkill** *(45)* | Skill chip | `bereich` (topic category), `name`, `note`, `quelle` (`manuell`/`linkedin`: manual/LinkedIn) |
| **CareerEntry** *(45)* | Career history | `art` (`Beruf`/`Ausbildung`/`Zertifizierung`/…: job/education/certification/…), `firma`, `rolle`, `von`/`bis`, `beschreibung` |
| **ProfileFile** *(45)* | Reference/certificate | `kind`, `file_path` (`data/profil/dateien/`), `mime`, `size_bytes` |
| **SuchEinstellung** *(49/50)* | Search settings (singleton id=1) | `min_mitarbeiter`, `suchbereich_json`, `plaene_json` (plans A/B/C), `modelle_json` (AI model per function) |

---

## 5. The application workflow

A job moves through fixed statuses (Kanban on the Pipeline page):

```
Neu → Prüfen → Beworben → Interview → Angebot → (Zusage / Absage)
                                          ↘ Kein Match / Beirat abgelehnt / Nicht verfügbar / Geparkt
```

(In English: New → To review → Applied → Interview → Offer → (Acceptance / Rejected); No match / Rejected by board / Not available / Parked.)

### The daily flow (daily run)

The **daily run** is the morning run and orchestrates serially:

1. **Job search** (WebSearch + Nejo + Arbeitsagentur, optionally Apify) — three runs by bucket (Remote ·
   Germany-wide · city + local area), new hits as “New” after the four-eyes check
2. **Mail job search** — process job alert emails from the mailbox into jobs
3. **Target company sweep** — check 12 career pages in rotation
4. **Headhunter search** — check 15 headhunter pages in rotation (separate agent)
5. **Applied-jobs check** *(phase 74)* — weekly availability check of all running applications
   (Applied/Interview): first the original URL, and if the portal is closed, the career page
   (phase 73 mechanism); a separate 7-day pre-check usually saves the run. Writes only
   availability status + check date — **never changes the application status itself**
6. **Email check** — mailbox of the last 24–36 h, assigning replies to applications
7. **Views refresh** — rebuild Excel export, daily digest, full-text search index
8. **Budget sync**

The headless/automatic chain behind the daily run (`agent_runner.RECIPES["tageslauf"]`) inserts,
after the email check, the **rejection analysis** once per calendar week *(P2-79; pre-check without
starting a model, a failure does not stop the chain, see `docs/AUTOMATION.md`)* and additionally appends
**Update coach site** *(phase 81/82)* as the last, deliberately non-fatal link
— without complete configuration or with the switch turned off, the step ends green (exit 0);
a real error after that marks only this one task, and the rest of the chain is left untouched.

Result: a compact morning summary (top hits, rotation states, applied-jobs check,
Gmail, open/overdue actions).

### Per job: the application package — mandatory core and optional components

*(P2-41, 15.09.2026 — previously “four-step preparation”: the Advisory Board check was step 2 with a
lock in front of `cv-match`, and the cover letter was always the last chain step. Both are now
optional, without a lock, and run independently of the mandatory core.)*

**Mandatory core** (sequential, real data dependency — company fit as context for the match,
the draft from `cv-match` as the basis for `cv-erstellen`):

1. **Step 1 — `firma-pruefen`**: company fit dashboard (business model, market, AI disruption,
   role influence, employer reality) + verbatim job posting snapshot. Both layouts
   are rendered deterministically from code (`pipeline/company_fit.py`/`pipeline/posting_snapshot.py`
   ::`render_full()`, phase 79) — the model now supplies only content, never HTML, so that the layout
   no longer drifts across runs. For a job whose portal is closed, the step determines
   the company's career page automatically (phase 73).
2. **Step 2 — `cv-match` → `cv-erstellen`**: match dashboard with a weighted
   requirements table + tailored CV **draft** (DE/EN), directly editable on the job detail page.
   Rebuilds from the current base CV file on EVERY run (phase 78 — an earlier “already
   done” shortcut could leave a draft standing on an outdated structure). Then the button
   **“Create CV”** (`cv-erstellen`) → Word + PDF + ATS scan from the (possibly edited) draft.
   Now waits only for company fit (step 1) — no longer for the Advisory Board.

**Optional components** — own marker (○ open / ✓ done), **no lock**, neither for itself
nor for any other step:

- **Check job (Advisory Board)** (phase 40): the 7-member application Advisory Board checks the job description
  + CV according to the charter procedure — moderated live debate (3–5 members, followable on the job detail page via SSE)
  + vote of all 7 (6 weighted review areas), decision calculated deterministically → HTML dashboard with traffic light (🟢 Apply / 🟡 Conditional / 🔴 Do not apply), registered
  under “Files & documents”. On 🔴 the card offers the one-click status “Rejected by board”
  (phase 41) — the user decides. Stays at its logical position (triage BEFORE the
  CV effort), but continues to run in-server via `beirat_engine.py`, NOT as a chain link of the
  runner — stage 1 of the P2-41 decision; chaining is not built.
- **`anschreiben-erstellen`**: truthful cover letter with direct address. Uses the
  tailored CV once the mandatory core has run — without a finished CV the skill falls back to
  the base CV, without company fit to the posting + its own research.

**Application package** (`agent_runner.RECIPES["bewerbungspaket"]`): ONE button starts the
mandatory core; a tick box “with cover letter” appends the optional component to the chain
(pre-set from the Settings card “Application package — default scope”, off by default). The
former recipe `deepdive` is dropped without replacement — identical in content to the application package
without a cover letter.

`job-deepdive` (interactive skill, not to be confused with the dropped recipe) does
company fit + CV in one go. Afterwards, optionally: `entscheider-recherche`,
`interview-vorbereiten`.

---

## 6. The skills (the “intelligence”)

24 skills, grouped by workflow phase. Triggered by a plain-text sentence (interactive) or a button
(headless, where marked).

### Search — finding new jobs (→ status “New”)

- **jobsuche** — “search for new jobs” · WebSearch (default) + Nejo + Arbeitsagentur (German title synonyms) + optionally Apify,
  one run per bucket, hard limits (including only companies with 100+ employees, evidence rule),
  target-role fit 1–5, four-eyes, ingest. *Headless-capable.*
- **mail-jobsuche** — “Mail job search” · job alert emails from Gmail → several postings per digest,
  dedup against the job search. *Headless-capable.*
- **zielfirmen-sweep** — “Target company sweep” · 12 career pages in rotation out of the ~68 target companies.
- **headhunter-suche** — “Headhunter search” · 15 headhunter pages in rotation; confidential
  assignments as `[vertraulich] <Headhunter>`. *Separate agent.*

**Hard limits and score (P2-74).** The same rule applies to all four search runs; it is set out in
`config/scoring_rubrik.md`: a hard limit applies only with evidence from a posting, email or
search result, never on an assumption. Hybrid outside the local area is not a relocation and belongs
in the bucket “Germany-wide”. The score sorts, it does not filter out: whatever passes the limits
is created with its score, even with 1 or 2. The final report names, for each
job sorted out, the limit and the evidence. For `mail-jobsuche` the core of the rule is additionally in
the runner's task template (`agent_runner.PROMPTS`), because that is where the drop was measured:
after a model change, only 10 % instead of 44 % of the extracted postings reached the ingest.

### Preparing an application (per job)

- **firma-pruefen** *(step 1)* — company fit dashboard + posting snapshot (both rendered deterministically
  from code, phase 79/design review — the model supplies only content) → `data/company_fit/`,
  `data/job_postings/`. For a job whose portal is closed: automatic career page fallback
  (`career_url`/`portal_closed`, phase 73).
- **cv-match** *(step 2a)* — match dashboard + tailored CV draft (editable), rebuilds on every
  run from the base CV instead of reusing an old draft (phase 78) →
  `outputs/cv/`.
- **cv-erstellen** *(step 2b)* — from the (possibly edited) draft: Word/PDF + ATS scan.
  Since P2-45 the draft is also editable AFTER creation: expand the text window, change,
  save, “Recreate CV” — same record, same file, Word/PDF/ATS are produced anew.
  The page-break protection resets its “keep” properties on every run (P2-47) — otherwise
  flags accumulated over several runs until a whole position slid onto the
  following page as an indivisible block
  (methodology v2, phase 55: score = degree of optimisation over ONE 15-keyword list generated in `cv-match`,
  raw ratio separately visible, one-off feedback loop) → `outputs/cv/`.
  Base CVs are structured to be Workday/ATS-parser compatible (title directly before the company line,
  phase 76 — previously “Autofill with Resume” read title and position shifted by one position).
- **job-deepdive** — both together. *Claude-in-the-Loop.*
- **entscheider-recherche** — real functional decision-makers (VP/Head/C-level) + previous incumbent, public
  sources only → `Contact` rows.
- **anschreiben-erstellen** — truthful, company-specific cover letter with direct address
  (DE/EN, docx + PDF) → `outputs/anschreiben/`, application status “Prepared”.
- **initiativ-bewerbung** — hidden job market: network check → create speculative job →
  decision-maker → warm/headhunter/cold route.

**Securing the posting text (P2-75).** Background: A job from a job email received HTTP 429 (“too many requests”) from
LinkedIn on capture. The base snapshot stayed without posting text
(finding `QUELLE_VERTRAUT`); company check, CV match and CV creation ran through anyway
and did not know the requirements of the job. What was measured was throttling per request, not a block
(3 of 12, 3 of 11 and 9 of 18 LinkedIn retrievals in the most recent mail job searches, scattered across the
run). The remedy has three parts; the snapshot remains the one place for the posting text, and
no second structuring route is created. Spec: P2-75.

- **Retry (`pipeline/verify_jobs.py`).** `check_url()` retries only on HTTP 429, with the
  pauses `_PAUSEN_429 = (3, 8, 20)` seconds; a `Retry-After` as whole seconds up to 30 replaces
  the respective pause. If it is still 429 after the fourth attempt, the finding is, as before,
  `NICHT_PRUEFBAR` (evidence “HTTP 429 after 4 attempts (rate limit)”). 403 (bot block), login wall,
  404/410 and expired markers are not retried; waiting does not help there. The result carries
  `versuche`; `wiederholen=False` gives the earlier behaviour with exactly one attempt. The pauses
  run through the module function `_schlafen` so that tests can replace them. The batches
  (`check`, `bestand`) first fetch all addresses and retry only the blocked ones in up to three
  further **rounds** after the pauses `_RUNDEN_PAUSEN = (5, 10, 20)`; the pauses per run thus remain
  at 35 s at most (measurement on 14.10.2026 with 24 addresses: 9 → 2 → 0 blocked in 58 s). The
  summary names `wiederholt` and `rate_limit_offen`. The four search skills therefore call
  `verify_jobs check` with a timeout of 300000 ms.
- **Catching up (`pipeline/posting_snapshot.py`).** `hat_anzeigentext(job)` is a pure
  read function: true if the snapshot carries text (base card, block “Full text (unedited)”,
  full-text candidates of older snapshots or a green structured version). `anzeigentext_sichern(job_id)`
  returns `vorhanden` (no network retrieval), `nachgeholt` or `fehlt` with a reason in plain text.
  The snapshot is replaced only on finding `OK` with text (`render_basis(job, text, hinweis=…)`, in
  place, plus a `JobLog` of kind `auto`); every other finding leaves the file
  byte-identical. A job without a snapshot gets its first one the same way. The text is structured
  only at the next company check. For existing data there is
  `python -m pipeline.posting_snapshot nachholen [--job-id N | --status CSV] [--dry-run]` alongside
  `backfill` (which only creates snapshots for jobs with none at all); with `--job-id` the exit code is 3 if
  the text is missing.
- **Stop at start (`app/main.py`).** The constant `ANZEIGE_KINDS` (`firma-pruefen`, `cv-match`,
  `cv-erstellen`, `anschreiben-erstellen`) is deliberately the same set as `LOW_MATCH_KINDS`, but
  a separate constant. `_guard_anzeigentext()` runs in `create_task()` directly after
  `_guard_low_match()` with the same resolved set of steps, so it applies to single tasks, chains
  and “Again”. It calls `anzeigentext_sichern` via `run_in_threadpool`, because the retrieval with
  pauses can take a good 30 s and would otherwise halt the whole server. On `fehlt` it responds with
  409 and the marker `ANZEIGE_FEHLT`; the confirmation is `params.ohne_anzeigentext_ok=true`
  (pattern `LOW_MATCH`, no Claude run and no costs before the decision).
  `AgentTaskButton` shows the query inline with “Start anyway” and “Cancel”; confirmed
  overrides accumulate, so anyone who confirms `LOW_MATCH` and `ANZEIGE_FEHLT` one after the other starts with
  both. That the company check also stops is a decision of 14.10.2026: without a posting,
  it rated the role blind.
- **Skills read the snapshot first.** `firma-pruefen` (step 3b), `cv-match` (step 1),
  `cv-erstellen` and `anschreiben-erstellen` take the posting text from `job.posting_snapshot_path`.
  If it is missing despite the server catching up, they call `nachholen --job-id` once. WebFetch on
  `job.url` is now only a partial source (amber badge). Without posting text there is no green badge;
  if `cv-match` runs without text after the confirmation, this appears as a red flag in the dashboard and in the
  final report. Company research via WebSearch/WebFetch and the “Portal
  closed?” check remain unchanged.

Not part of P2-75: a button “Fetch posting again” on the job detail page (every documents run
catches up anyway, and `nachholen` handles existing data), recognising a recruitment agency as the
company posting the job (a topic of its own) and automatic regeneration of existing
company fit dashboards (a new company check catches up structure and rating).

**Portal status (P2-76).** Background: `firma-pruefen` and `beworben-check` loaded `job.url` via WebFetch and
searched the text for markers; on LinkedIn HTTP 429 the status stayed unchecked. In addition,
`check_url()` read the timeout at StepStone (connection established, then no response) as `TOT`,
although the postings are live. Since P2-76 the portal status comes from the same retrieval with retry
as in the search runs. Spec: P2-76.

- **Markers (`pipeline/verify_jobs.py`).** `BESETZT_TEXT_MARKERS` additionally knows “keine bewerbungen
  mehr angenommen” (LinkedIn on German pages) and “nimmt keine bewerbungen mehr entgegen” (both meaning that the job no longer accepts applications). The
  markers exist only in the code; the skills evaluate the result.
- **Exception rule.** `httpx.ReadTimeout` and `httpx.RemoteProtocolError` (the portal accepts the
  connection but does not respond or closes it without a response) result in `NICHT_PRUEFBAR` with
  evidence that names the bot protection, no longer `TOT`. Failed connection set-up
  (`ConnectError`, `ConnectTimeout`) and the remaining timeouts stay `TOT`. Bot protection
  is not circumvented; the portal is honestly reported as blocking. Consequence: a StepStone hit
  from a mail alert or Apify is no longer rejected in the four-eyes check, and
  `anzeigentext_sichern` says “Das Portal blockiert automatische Abrufe.” (“The portal blocks automatic retrievals.”)
- **Text when the portal is closed.** If a page shows a text marker and the job's title (from 60 %) and
  company can still be read, the result carries the posting text along. The finding remains
  `ABGELAUFEN`. `anzeigentext_sichern` accepts this text (status `nachgeholt`, note “Das Portal
  nimmt laut Abruf keine Bewerbungen mehr an”, i.e. the portal no longer accepts applications according to the retrieval). In the case of a redirect to an expired page there is never any text.
- **`portal_status()` and CLI `portal`.** `portal_status(pr)` is a pure function: `OK` gives
  `offen` (open); `ABGELAUFEN`, `UMGELEITET_GENERISCH` and `TOT` with HTTP 404/410 give `geschlossen` (closed);
  everything else (`NICHT_PRUEFBAR`, `LOGIN_WALL`, `INHALT_UNKLAR`, `TOT` without status, `KEINE_URL`)
  gives `unklar` (unclear). `python -m pipeline.verify_jobs portal <job_id> [<job_id> …]` loads the jobs
  from the database read-only, retrieves them via the round retry of P2-75 and outputs a
  JSON list (`job_id`, `url`, `portal`, `befund`, `beleg`, `http_status`, `versuche`). An
  unknown or deleted ID gives `befund` `UNBEKANNT` without retrieval. The command writes neither
  database nor files.
- **Skills.** In the mandatory step “Portal closed?”, `firma-pruefen` calls `portal <id>` once,
  `beworben-check` (step 3) calls `portal` once for the whole set to be checked. `geschlossen` leads into the
  existing career page fallback (`portal_closed`, `verify_note`), `offen` ends the check;
  only on `unklar` does WebFetch on `job.url` follow as before (at most two per job). Writing back
  `portal_closed` and `availability_status` remains with the skills.

### Interview

- **interview-vorbereiten** — call briefing (expected questions with STAR from the real CV, questions
  to the company, conflict scan, objection handling, cheat sheet) → `data/interview_prep/`.
  *Claude-in-the-Loop.*
- **gespraech-debrief** — evaluate a transcript (guiding questions, signals, red flags), interviewers as
  contacts, maintain the question bank, thank-you email as a Gmail **draft**. *Headless-capable.*

### Following up / communication — always only a Gmail DRAFT, never sent

- **mail-antwort** — fact-true reply to an incoming email, `[BITTE PRÜFEN]` placeholders,
  draft in the original thread.
- **nachfass-mail** — mode A (silence → status enquiry with value anchor) / mode B (rejection →
  ask for feedback, fills `rejection_reason`).

### Analysis / decision

- **absagen-analyse** — lost-order evaluation (what do rejections have in common, screening vs. interview);
  maintains the empirical section in `config/profil.md` (feeds back into scoring/CV tailoring).
  Since P2-79 once per calendar week in the daily run and via a button on the dashboard. The empirical section
  is replaced only by a manual start; the weekly run (`chain_id` set) writes its proposal as
  a separate card in the report and leaves the profile unchanged (decision of 16.10.2026).
- **angebot-vergleich** — on status “Offer”: weighted benefits points list, red lines = knock-out,
  matrix.
- **job-frage** — “Question on job <id>: …” · answer **only** from local job data (no web), in
  job chat + history. *Headless.*

### Operation / orchestration

- **email-check** — daily scan of the mailbox (Gmail or IMAP, configurable per installation,
  phase 71F), assignment, response times, contacts; relevant emails also land in the inbox WITHOUT an assignable
  job (“Without job”). An email reported as “acknowledgement of receipt” that arrives later
  than 7 days after the application is checked by the ingest itself against the full text and upgraded to
  “Rejection” if it contains an unambiguous rejection wording (P2-48, entry in the history
  of the job). If several jobs fit, the email stays without a job —
  exception since P2-43: if all candidates are twins of the same role (duplicates, titles without
  gender suffix identical), the one application still running (Applied/Interview/Offer)
  takes the email. In addition to the keyword search, step 1b searches for known addresses and domains; since P2-80 the
  lists come from `pipeline/mail_suchlisten.py` (previously a snippet in the skill): contact
  addresses, domains of the recruiter contacts and of the running applications (Applied/Interview/Offer,
  from emails on the job and contact addresses), filtered against ATS, freemail and large job portals.
  Step 1c additionally searches for words in French, Italian, Spanish and Portuguese, but only if
  `mail_suchlisten --sprachen` reports such a language (base CV or running application).
  The ingest adds the address to a contact of the same name at the same company that has no address,
  instead of creating a duplicate (P2-80). *Headless-capable, read-only.*
- **beworben-check** *(phase 74)* — weekly availability check of all running applications
  (Applied/Interview): first the original URL, and if the portal is closed, the career page
  (phase 73 mechanism); writes availability status + check date, never changes the application status
  itself. *Headless-capable.*
- **tageslauf** — the morning run (orchestrates job search + sweeps + applied-jobs check + email check +
  refresh). *Claude-in-the-Loop.*
- **outreach-drive-upload** — outreach tracker to Google Drive in true-to-format form (in practice:
  the app button produces the file, the user places it in Drive manually).

### Profile (phase 45/47)

- **profil-einlesen** — “Read profile from the stored text” · structures the pasted
  profile text or the text of the profile PDF into a proposal that the user checks before additive saving
  (`pipeline/linkedin_text.py`). No web: LinkedIn blocks automatic retrievals (HTTP 999). The
  most complete route remains the data export ZIP
  (`pipeline/linkedin_import.py`, deterministic, no LLM). *Headless.*
- **skills-sortieren** — assigns imported skills from “LinkedIn (unsorted)” to topic areas based on context
  (preferring existing ones, creating new ones only when needed). **Only moves** —
  invents nothing, renames nothing. Starts automatically after every ZIP import with new skills,
  manually via “Re-sort skills”. *Headless.*

---

## 7. The interface (19 pages)

| Page | Purpose |
|---|---|
| **Dashboard** | KPIs (jobs, top target roles, running applications, response rate, follow-up banner, “Applied jobs offline” warning tile since phase 74, note “Sample data” with a link to Settings for as long as it is present, P2-59), clickable funnel stages and bar tiles |
| **Search** | Full-text search across everything (jobs, descriptions, company fit, transcripts, debriefs, briefings, history) — the result is always a job; index state + “↻ Update index” |
| **New / Review** | review new hits from the pipeline (Accept → To review / Discard → No match) with verification badges; manual search/check buttons (job search, target company sweep, headhunter search, applied-jobs check, email check) with the state of the last run |
| **Follow-ups** | overdue (red) + upcoming actions, upcoming interviews, follow-up chips |
| **Pipeline** | Kanban with drag & drop across the statuses |
| **Jobs** | all jobs, URL-controlled filters, sorting, “+ Create job”; **status distribution bar** above the table (segments proportional + clickable as a filter, style guide colours); badge “⛔ offline” + filter for applications that, according to the applied-jobs check, are no longer online; labels “Duplicate? → Job X” and “Re-posting → Job X” next to the role title as in Review and Job detail (P2-42) — a click leads to the predecessor job |
| **Job detail** | Command centre per job: key facts (including career page when the portal is closed, phase 73, and availability status from the applied-jobs check, phase 74), status, follow-up, contacts, “Create documents” (mandatory core company fit → CV with gating; Advisory Board job check and cover letter as optional components without a lock, P2-41), CV draft editable at any time (also after creation, P2-45), application, interviews & conversations, tailored CV, “Files & documents”, AI chat, notes & history |
| **Inbox** | email history, full text, AI reply drafts; “Without job” badge/filter + assigning/detaching a job; **Archive** (P2-52): hide emails without a job (button on the row or in the detail view), expandable archive panel with restore, Gmail remains unchanged |
| **Companies** | all companies with fit traffic light |
| **Radar** | Restructuring radar (companies with upheaval signals) |
| **Network** | 3 tabs: target companies · headhunters · network contacts (with delete, sweep/speculative chips); per tab an expandable **bin** with restore. The headhunter column “Source” (sheet/outreach) with the addition “sheet only” appears only if an outreach row is in the list (P2-61, otherwise “Sheet” would be shown everywhere) |
| **Outreach** | Networking tracker (expandable rows, editor, activity log, Drive export). Menu item only if `GET /api/outreach` returns rows (P2-61): creating is not possible; at the customer the page was empty and the export without `data/templates/outreach_tracker_vorlage.xlsx` was a 500 error |
| **Advisory Board** | 7-member application Advisory Board (charter-based): topic + context + minimum contributions go in, the chair orchestrates autonomously (name from `GET /api/beirat/mitglieder`, field `vorsitz`), debate runs live via SSE (speaker cards, moderation lines), synthesis at the end; key panel (Anthropic/OpenAI, local), debate archive. Phase 40 removed the menu item, P2-61 put it back as “🏛️ Advisory Board” under Network, because customers otherwise found the free debate only via the address; page texts since then in the formal “Sie” form without file paths. The job check runs on the Job detail page |
| **Tasks** | Task Centre = the ONE activity log: all background activities (runner skills AND Advisory Board runs, phase 42) with KPIs, costs, live log, cancel, again |
| **Budget** | costs per service & day, editable limits |
| **Profile** *(phase 45/47)* | The candidate substance for matching/cover letters: LinkedIn import (data export ZIP = most complete route, profile text or PDF = immediate, via AI with preview), positioning, skills as chips by topic area (automatic sorting of imported skills), career history, reference/certificate files. Both import routes additive & non-destructive; derivation to `config/profil_struktur.md` on every save. Since P2-69 the first card is “Identity and search strategy” (`components/ProfilIdentitaet.tsx`): it reads and writes `config/profil.md` (name, address, contact, LinkedIn, short profile, target role, conditions, skill gaps) via `GET/PUT /api/profil/identitaet`, losslessly and with a bin copy (§8 “Profile file”) |
| **Settings** *(phase 49/50, P2-51)* | Control panel of the search strategy: **AI card** *(P2-86)*: choice of Claude or ChatGPT (`ki_anbieter`) with status per provider (`GET /api/ki-status`) · search area (Remote · Germany-wide · city + local area, label “<city short form> +<km>km” also as a filter tab in the job list) & minimum company size · **AI model per function** (job search/company fit/Advisory Board/CV match/ATS scan/cover letter — Opus 5.5/Sonnet 5.5/Haiku 4.5, under ChatGPT the Codex models, Fable locked (see §8 “AI models”), list + display names come exclusively from the backend, default Sonnet) · **three plan cards A/B/C** (label, active, role title/level/industry), search order A→B→C · **Coach site card** *(phase 82)*: address/SFTP access/server path (button “determine automatically”) + coach login (bcrypt) + on/off switch, button “Update coach site now”, connection test. **Search portals** *(phase 87)*: eight rows — the six portals customary in Germany (LinkedIn, Indeed, StepStone, Xing, Nejo, Arbeitsagentur) pre-filled with name + URL, plus two free rows. Each row has an active switch, an editable URL (placeholders `$QUERY`/`$LOCATION`/`$PAGE`) and a **check button** that retrieves the URL on the server side and rates it in three levels: green (responds with content), amber (reachable, but bot protection or an almost empty response — still usable as a web search channel; since P2-73 also: the address redirects to a different host, in which case the new address should be entered, because the retrieval by the search agents does not follow such a redirect itself), red (not reachable). If a default address changes, the server start carries it over into the database and the search profile file, provided the stored address is still literally the earlier default address (`suchprofil.PORTALE_FRUEHERE_STANDARDS`); an address changed by the user stays as it is. The access type per portal is shown alongside and is fixed: “via web search” for portals with bot protection, “direct retrieval” for Nejo/Arbeitsagentur. Only active portals are searched in the daily run. **Advisory Board — line-up** *(phase 90)*: the seven seats with name, perspective, colour and chair marker; button “Fill seat anew” starts the skill `beirat-persona`, which researches the persona, writes it in the same build as the other board members and then repairs the references in the six other files. Seven seats are fixed (traffic light calibrated to seven votes); the chair can be reassigned but not withdrawn. **Application package — default scope** *(P2-41)*: a card with one switch “Cover letter in package” (default off) — pre-sets the tick box on the Job detail page, can be overridden per job at any time; no switch for the Advisory Board, as it would have no effect in stage 1. **Data backup** *(P2-52)*: shows the last automatic backup (time, size) and their total number, switch for the daily automation, fields for retention (daily/weekly/monthly), button “Back up now”; amber warning on a failed backup or if, with automation switched on, the last one is older than 3 days (`GET/POST /api/sicherung`, `PATCH /api/sicherung/einstellungen`). **Sample data** *(P2-59)*: first card on the page (until 1.7.0 the licence card stood in front of it), only on status `vorhanden` or `entfernt` (`GET /api/beispieldaten`): count of the sample data, button “Remove sample data” with inline confirmation query (`POST /api/beispieldaten/entfernen`), afterwards the result with backup file and the files that the customer has changed and that therefore remain; triggers `PROFIL_GEAENDERT` (see Sidebar below, §8 “Sample data”). **Program version** *(P2-51)*: last card, its own endpoint `GET /api/version` instead of the other `/api/einstellungen` data — installed version or, for a Git installation, the development state, date of the last update, the CHANGELOG section “New in this version” and, for a package installation, update instructions (`update.command`/`update_windows.bat`). Since P2-82 it carries the button **“Check for updates”** (only on click, `GET /api/version/neueste`, section “Update information via GitHub releases”) with the note that GitHub receives the IP address in the process; the footer of the “Data backup” card names `wiederherstellen.command`/`wiederherstellen_windows.bat` for restoring (P2-66) | Every save regenerates the managed block of `config/suchprofile.yaml` — `unterlagen` (application package default scope) is excluded, it is not a search parameter |
| **Documentation** *(P2-59)* | The reading texts of the installation in tabs (`pages/Dokumentation.tsx`, menu item before “Legal”): Version (`CHANGELOG.md`, above it “Installed: Version …” from `GET /api/version`), Features, Guide, Installation & Updates (the file for the running system: `BMS_Install_Windows.md` on Windows, otherwise `BMS_Install_MAC.md`), Set up email, Windows, Coach site, Advisory Board (the “Licence” tab was dropped with P2-82); in a development installation, after a separator “Internal”, additionally Technology (this file), Automation, Release, Developer installation. The backend renders the documents (`GET /api/doku/{name}`), the page shows them in a frame with a sandbox (§8 “Documentation page”) |
| **Legal** *(phase 71E)* | Four tabs: About this program (publisher, licence, disclaimer, AI notice under Art. 50 AI Act; replaces the imprint since 29.10.2026), Open-source licence (`lizenz.txt`, byte-identical copy of `LICENSE`, guard `test_open_source_lizenz.py`), Privacy, Third-party licences — maintained as Markdown under `frontend/src/rechtliches/` and displayed by a small renderer of its own (deliberately without an npm package). EULA, withdrawal notice and sales checklist were dropped on 29.10.2026 because the BMS is no longer sold |

**Sidebar** *(`components/Layout.tsx`, P2-51, P2-59)*: The header is centred and carries the product name from the design (`GET /api/design`, role `produktname`; until the response is there, the title from `frontend/index.html`). The browser sets the line break in a block 13.5 rem wide; with the name from the default it breaks as before after “Bewerbungs-Management-” (`text-base tracking-tight`: in `text-lg` the first line is around 243 px wide and burst the 240 px of the bar, measured in Chrome from 320 to 1280 px width). Below it stands the name from `GET /api/profil` (`profile.name`, read from `config/profil.md`, fallback “Bewerber”). The browser title is `<product name> · <name>`, without a name only the product name; the static title in `frontend/index.html` is the initial value until the design has loaded. The footer always shows `Version <x>` as soon as `GET /api/version` knows a version other than `0.0.0`; the development state of a Git installation is now only available as a tooltip (`title`) on this line; until P2-59 it stood in the text (“3 commits after 1.1.3” displaced the number). The menu item “📖 Documentation” is in the last block directly before “⚖️ Legal”. “🏛️ Advisory Board” has stood directly below “🌐 Network” since P2-61; “📇 Outreach” appears only if `GET /api/outreach` returns rows at start-up (a question about the data rather than about the type of installation, so that even a Git working copy without transferred rows does not show the empty item). The event `PROFIL_GEAENDERT` (`frontend/src/profil.ts`) is triggered by anyone who changes name or address from `config/profil.md` (today: “Remove sample data” in Settings and, since P2-69, saving the card “Identity and search strategy” on the Profile page): the sidebar reloads the name, and the address cache (follow-ups, Job detail) discards its value, instead of showing the old details until the next page start.

---
## 8. Operations, Automation & Security

### Everyday operation

**Starting and stopping** (no auto-reload — restart after every backend change):

| | macOS | Windows |
|---|---|---|
| Start | `start.command` · `start_lan.command` (Wi-Fi) | `start_windows.bat` |
| Stop | `Ctrl+C` in the server window, otherwise `stop.command` | `Ctrl+C`, otherwise `stop_windows.bat` |

The stop scripts are for the case where the server window can no longer be reached (closed,
started in the background, hung). They end the process on the server port (default 8000), first
politely and after 10 s by force — **but before that they check whether agent runs are active or queued,
and ask for confirmation.** Reason: skill runs hang off the server as child processes, and an Advisory Board debate runs
inside the server itself; a restart aborts them. `--force` skips the confirmation; a different
port works via `PORT=8010 ./stop.command`.

For script/terminal use without a double-click:
```sh
lsof -ti :8000 -sTCP:LISTEN | xargs -r kill; sleep 1
cd backend && nohup ~/.bewerbung_mgmt_venv/bin/python run_server.py > /tmp/bms_server.log 2>&1 & disown
```

**Environment variables.** `.env.example` lists the settings that may deviate from the default
(server port and address, `BMS_DATA_DIR`, `BMS_SECRETS_DIR`, limits for agent runs). The program reads
them only from the environment (`os.environ`); it does not load a `.env` file itself. The values must
therefore be set in every shell that starts the server.

**Backup & restore, manual** via `scripts/backup_db.sh` (copy using SQLite's online backup API,
consistent even with concurrent writes). The automatic backup is described below in the section
"Backups".
```sh
scripts/backup_db.sh                    # Backup anlegen: data/backups/bewerbung_backup_<JJJJMMTT_HHMMSS>.sqlite
scripts/backup_db.sh --label vor_x       # mit Suffix, z. B. vor einer riskanten Operation
scripts/backup_db.sh --rotate            # + Rotations-Kandidaten auflisten (Dry-Run, löscht nichts)
scripts/backup_db.sh --rotate --apply    # + Kandidaten wirklich löschen (behält die neuesten 15)
scripts/backup_db.sh --rotate --apply --keep 20   # andere Aufbewahrungsmenge
```
To restore, there are `wiederherstellen.command` and `wiederherstellen_windows.bat` (section
"Backups"); by hand it works like this: stop the server, copy the desired backup back
(`cp data/backups/<datei>.sqlite data/bewerbung.sqlite`), check integrity
(`sqlite3 data/bewerbung.sqlite "PRAGMA integrity_check;"` → `ok`), restart the server. Manual backups
are never deleted automatically — rotation deletes only with an explicit `--apply`.

**`sqlite3` CLI against the RUNNING app (Phase 67F):** The app sets an explicit `busy_timeout` (15 s,
`backend/app/db.py`). The `sqlite3` CLI does not know this value (separate process, separate connection) and has
**0** by default — an ad-hoc query against `data/bewerbung.sqlite` while the server is running and writing
can abort immediately with "database is locked". For a query against the running app, therefore
prepend:
```sh
sqlite3 data/bewerbung.sqlite "PRAGMA busy_timeout=5000; SELECT ...;"
```
This is not needed for a restore (the server is deliberately stopped then).

**Outbound check** (`scripts/outbound_check.py`, Phase 66B) reads the agent task logs under
`~/.bewerbung_mgmt_logs/` (read-only) and lists where headless skills actually opened outbound
connections (curl/WebFetch), against a maintained list of expected destinations:
```sh
python3 scripts/outbound_check.py            # Kurzübersicht + auffällige Treffer
python3 scripts/outbound_check.py --all       # vollständige Host-Liste statt Top-20
python3 scripts/outbound_check.py --days 7    # nur die letzten 7 Tage
```
No automatism, no cron, no alerting — a tool that runs manually when needed. It is
detection, not prevention (honest assessment: "What the skill allowlist achieves — and what it does not"
below).

### Naming conventions (`backend/app/naming.py`)

- **External** (recipients see them): `CV_<Name>_<Firma>_<Rolle>_DE|EN`,
  `CoverLetter_<Name>_<Firma>_<Rolle>_DE|EN` (the name comes from the profile, e.g. `CV_MaxMustermann_<Firma>_<Rolle>_DE`).
- **Internal**: `JJJJMMTT_<Typ>_<Firma>[_<Rolle>]` (type = CompanyFit / Match / ATSscan / Briefing /
  Auswertung / Anzeige / Beirat / Analyse; `Transkript_<JJJJMMTT>_<Teilnehmer>_<Firma>_<Rolle>[_Rn]` for
  the upload). Standard for new items since Phase 30; the existing items were migrated in Phase 31. P2-63 shortened the
  date from `JJJJ_MM_TT_` to `JJJJMMTT_` and replaced the type words (`Stellenausschreibung` →
  `Anzeige`, `TranskriptReport` → `Auswertung`, `BeiratsCheck` → `Beirat`). `report_filename` still accepts the
  old type words as input and maps them to the new ones; `posting_filename`, like
  all reports, returns `<Datum>_Anzeige_<Firma>_<Rolle>`.
- **Shortening (P2-63)**: The company goes through `_firma_kurz` (everything from the first `(`, `:`, `,`, `;`, `|` or
  ` - ` is dropped, as are legal forms at the end; then clean-up and at most 25 characters at a
  word boundary), also for CV and cover letter. The role has 30 characters (reports, posting, transcript) or
  35 (CV, cover letter); gender suffixes and region suffixes after ` - ` are dropped. Not affected:
  backups, debate IDs and persona backups in the Advisory Board, the outreach tracker (`<JJJJ>_Job_Search_Tracker_…`,
  year only).
- **Readers understand both date formats**: bin age (`cleanup`), `migrate_reports`, the
  reuse test for CV and cover letter export (a name under the old convention for the same
  job counts as separate, so no orphan arises) and the skills (`recheck_von` reads the date
  of the predecessor dashboard from both formats).
- **Renaming existing items (internal, `backend/pipeline/namen_umstellen.py`, P2-63)**: The source of truth is
  the database. For each path field, the new name is built from company, role, round and language from the DB and the date
  of the old name; linked files (CV and cover letter as `.docx` plus `.pdf`, Advisory Board HTML
  with `_rohdaten.json`, transcript upload) move together; uploads without a DB reference get only the
  new date format. Links in the HTML reports are replaced as well. Not touched are
  `data/papierkorb/`, `data/backups/`, `data/cv_basis/`, drafts, persona backups and the
  history fields (task results, job chat, notes). Call in the `backend` folder:
  - `python -m pipeline.namen_umstellen --probe [--bericht <pfad.json>]` changes nothing, opens the DB read-only
    and writes a report (old → new per field and file, collisions, missing files,
    link replacements).
  - `python -m pipeline.namen_umstellen --ausfuehren` checks that no task is running, creates a
    backup (DB plus ZIP of the affected folders to `data/backups/vor_p2-63_<zeit>.zip`), renames,
    logs every rename immediately (`data/backups/namen_p2-63_<zeit>.json`), sets the
    DB fields in one transaction and replaces the links. On an error everything is rolled back
    (exit code not 0). A second run changes nothing.
  - `python -m pipeline.namen_umstellen --zurueck <protokoll.json>` replays a log in reverse
    (files and DB fields). The tool leaves missing files unchanged and names them in the report.
  The server should be stopped for this.

### Licence — removed (P2-82)

Up to version 1.7.0, the BMS required a signed licence file (Phase 72B, P2-67, P2-68): without it,
it ran read-only, with locks in the server, on the command line, in the runner and in the Advisory Board engine,
plus a licence card, a notice banner and a purchase link in the interface. Since 29.10.2026 the BMS is no longer
sold; it is open source under the Apache License 2.0 (`LICENSE`, `NOTICE`).
**P2-82 removed the licence requirement completely** (contracts L and O
of the P2-82 build spec):

- The BMS runs without a licence file with its full range of functions. No route answers with 402 any more, the
  command-line tools no longer know exit code 4, and the licence module, licence endpoints,
  licence card, banner and the test licence in `tests/conftest.py` are deleted.
- No part of the BMS contacts the former platform server any more. An existing licence file
  in the secrets directory is neither read nor deleted; the CHANGELOG says that it is no longer
  needed.
- `cryptography` is no longer a direct dependency and remains only transitively via `google-auth` in the
  lock file.
- `tests/test_ohne_lizenz.py` records the state: no shipped module imports the old
  licence module, the names of the former licence check no longer occur under `backend/`, `frontend/src/`,
  `scripts/` and `.claude/`, and a writing route answers with 200 without a licence file.
- The earlier state (versions up to 1.7.0, spec P2-67) belongs to the private development history and is not contained in the
  public repository.

**Legal.** There has been no EULA since 29.10.2026: the BMS is no longer sold and
is under the Apache License 2.0 (`LICENSE`, `NOTICE`). The licence requirement has been removed since P2-82.

### AI models: one source for aliases and display names, Fable blocked (P2-51, P2-59)

CLI aliases are stored (`opus`/`sonnet`/`haiku` in `sucheinstellung.modelle_json`, no
migration needed — the CLI always resolves an alias to the current model). The list
itself with alias AND display name (`agent_runner.MODELLE`: `opus` "Opus 5.5", `sonnet` "Sonnet 5.5",
`haiku` "Haiku 4.5", default `MODELL_STANDARD = "sonnet"`) has been maintained exclusively by the backend since P2-51;
`main.py::_einstellungen_out` returns it unchanged as `modell_optionen` with
`modell_standard`. The labels name the version that the short name points to in the installed CLI
today (`sonnet` → `claude-sonnet-5-5`); the app still calls the CLI with the short name and
does not pin a model ID. The former separate copy in `frontend/src/api.ts` (outdated display name,
`fable` missing) is removed without replacement. Under ChatGPT, `ki_anbieter.modell_optionen` returns the
Codex models (`CODEX_MODELL_OPTIONEN`) at this point; the same tiers remain stored.

**Fable cannot be selected (P2-59, rule of 01.10.2026).** The reason is cost: Fable 5.1
costs $10 input and $50 output per million tokens, Opus 5.5 $4/$20, Sonnet 5.5 $2/$10 and
Haiku 4.5 $1/$5 (as of the claude-api reference of 25.09.2026), so 2.5 times Opus and
five times Sonnet. The rule appears in four places, and `tests/test_modellwahl.py` locks in each one:

- `agent_runner.GESPERRTE_MODELLE = ("fable",)` records what is deliberately kept out. A guard
  test ensures the list never overlaps with `MODELL_ALIASE` and no label
  mentions Fable.
- Allowlist instead of blocklist: `main.py::_validiere_modelle` rejects every value outside
  `MODELL_ALIASE` with 422, including `fable`. `PATCH /api/einstellungen` then changes nothing in the
  database, and the message (built from `MODELL_ALIASE`) does not mention Fable.
- `agent_runner.wirksames_modell(alias)` returns the alias if it is in `MODELL_ALIASE`, otherwise
  `MODELL_STANDARD`. `modell_fuer_kind` and `modell_fuer_beirat` go through it: a previously
  stored `fable` starts with Sonnet without the stored row being touched, and one line per
  process and value is written to the server log (`[agent-runner] Modell 'fable' ist gesperrt …`).
  `_einstellungen_out` shows the same EFFECTIVE values, so the selection never carries a value that does not exist
  there.
- `agent_runner._argv` sets an explicit `--model` for EVERY `claude -p` run: the choice of the
  function from the settings (`modell_override`), otherwise the fixed entry in `PROMPTS`, otherwise
  `MODELL_STANDARD`. Until P2-59, runs without their own function in the model choice (e.g.
  `email-check`, `gespraech-debrief`, `absagen-analyse`) ran entirely without `--model`, i.e. with the
  default model of the installed CLI, and at a customer that can be Fable (in the development installation
  it had pointed to Sonnet since September according to `modelUsage`, so nothing changed there). The only fixed
  entry in `PROMPTS` is `job-frage`; since P2-59 it names the short name `sonnet` instead of
  `claude-sonnet-5`, and every `PROMPTS[*]["model"]` must be an alias from `MODELL_ALIASE`
  (guard test). The job view accordingly shows "Modell: Sonnet" below the chat. The Advisory Board
  (`beirat_engine`) has always passed its model, via `modell_fuer_beirat()` and thus likewise
  through `wirksames_modell`.

### Version, update and release (P2-51)

`VERSION` (project root, one line `MAJOR.MINOR.PATCH`, "0.0.0" means "no release yet") is
the only source of the version number; only `pipeline/release.py::freigeben()` writes it.
`CHANGELOG.md` is customer text (formal "you" form, shipped): the section "## Unveröffentlicht" (Unreleased) becomes
the new version section "## X.Y.Z (TT.MM.JJJJ)" at every release, and a new empty
"Unveröffentlicht" section is created directly above it. `pipeline/changelog.py` handles both
(`version_tupel`, `abschnitte`, `abschnitt`, `pruefen`, `freigeben`) — the same API is read by both
the release (`pipeline/release.py`) and the running app (`app/version.py`, section of the
installed version for the Settings page).

Every customer package additionally gets `bms_manifest.json` (contract V3 of the build spec, built by
`pipeline/kundenpaket.py::bauen()` AFTER the customer files are replaced, BEFORE the
personal-data check — the manifest is itself checked): path → `{ausfuehrbar, groesse,
sha256}` of every shipped file, plus `commit`/`commit_datum`, `version` (from `VERSION` of the
packed state, not from the working tree), `freigabe` (does the commit carry the tag `v<version>`?),
`vorschau` (true with `--arbeitsbaum`) and `anpassbar` (fnmatch patterns for files that an
installation may change after unpacking, e.g. `.claude/agents/beirat-*.md`,
`config/profil_struktur.md`, `config/scoring_rubrik.md`). It replaces the former `VERSION.txt`
(P2-50) without substitute — `datetime.now()` made that file non-reproducible, whereas the manifest can be rebuilt identically from
the same commit at any time.

At the customer's, `scripts/bms_update.py` (standard library only, no import from `app`/
`pipeline` — the script runs alongside a half-replaced installation) installs a new package:
check the installation (no Git checkout, runs in the venv) → find the package (P2-82: a path argument
applies without any network contact; otherwise the highest version from the latest GitHub release
and from `~/Downloads/BMS_*.zip` wins; a downloaded package lies under `data/updates/pakete/` and
afterwards counts like a package passed in; details in the section "Update information from GitHub releases" below) →
self-update (if the script in the package differs from the running one, control is handed to the
new version with `--delegiert`, so that the update LOGIC of the new version always applies; it
gets the path of the package explicitly as an argument, otherwise it would search and download a second time) → check the package (manifest, SHA-256, no unsafe/
protected paths, version/preview) → server-off check (`GET /api/health`) → create and
show the plan (`--pruefen` ends here) → confirmation prompt (skipped with `--ja`) → lock → backup
(database copy via the sqlite3 backup API, every replaced/removed file, old manifest, if applicable
old `frontend/dist`) → write files atomically → dependencies (`pip install`, `npm ci`,
rebuild the interface, depending on what has changed) → self-test → completion (new
manifest, `bericht.json`, release the lock). Every error from "write files" onwards rolls back
completely (exit 2) rather than leaving a customer installation half finished. The self-test
(`backend/app/selbsttest.py`, `python -m app.selbsttest`) runs in its OWN subprocess against
a copy of the backed-up database (`BMS_DATA_DIR`/`BMS_LOG_DIR`/`BMS_SECRETS_DIR` pointing to
temporary directories) — it imports `app.main` (catches missing packages/syntax errors) and checks
`init_db()` against `SQLModel.metadata` (catches a forgotten `_ADD_COLUMNS` migration). It is started
via `update.command` (zsh) or `update_windows.bat` (CRLF, see below) — both only pass the
program folder through and run entirely within one function or one bracketed block, because the
update can replace the calling file itself while it is still running. `--zurueck` reverts the
last successful update; the question whether the database is also reset to its previous state
is answered **exclusively** by the separate switch `--mit-datenbank` — `--ja`
applies only to the install confirmation, never to the database question (two separate
risk levels).

`GET /api/version` (`app/version.py` + thin router `app/routes_version.py`) answers which
version is currently running: "paket" (if `bms_manifest.json` is in the program folder, values from there,
`commit` shortened to 7 characters), "git" (if `.git` exists, `version` from `VERSION`, `commit`/`datum`
via `git rev-parse`/`git show`, `entwicklungsstand` from `git describe --tags --long --dirty`) or
"unbekannt" (unknown). Every Git call runs with a 5 s timeout and catches every error — the
Settings page must never fail with a 500 on this information.

The release itself is the publisher's tool (`pipeline/release.py` via `scripts/release.sh`:
`freigeben`/`notizen`/`abholen`) and the workflow `.github/workflows/release.yml` (tag push
`v*.*.*` or `workflow_dispatch` for a trial build). Since P2-82 the package reaches the user through the
GitHub release itself: the release ends with the GitHub release, and there is no longer any upload to a server
(the package service of P2-71 has been removed). The update tool and the installation guides
download the package from there; the button in Settings shows the latest version (section
"Update information from GitHub releases"). Details in `docs/RELEASE.md`.

### Update information from GitHub releases (P2-82)

New versions appear as a GitHub release of the public repo `holgerdaube/BewerbungsMgmtSystem`.
Two places query it, both only at the user's request: the button "Nach Updates suchen" (Check for updates) in
the app (contract A of the build spec P2-82) and the update tool
`scripts/bms_update.py` (contract U). As long as the repo carries no published release, the
button shows "No version has been published yet."

- **Repo and address are constants, not environment variables.** `GITHUB_REPO` appears in exactly two
  places, in `app/update_pruefen.py` and in `scripts/bms_update.py` (the tool must not import anything from
  `app`); `tests/test_update_pruefen.py` keeps both identical. Plus `GITHUB_API =
  "https://api.github.com"`. Anyone who could redirect the address could slip in a foreign package.
  Only tests replace the constants in the process, using a trial server on 127.0.0.1; no test
  contacts GitHub.
- **Only on request.** There is no query at start-up, no background query and no reminder.
  The running app asks only on click, the tool only after a double-click on
  `update.command`/`update_windows.bat`, the installation guides only with their download command. The
  daily run and the skills never talk to GitHub. A path argument and `--offline` prevent any
  contact by the tool.
- **What GitHub sees.** Anonymously, without token and without identifier: the IP address of the computer and the
  request itself, with `User-Agent: BMS-Update` (for the information query also `Accept:
  application/vnd.github+json` and `X-GitHub-Api-Version: 2022-11-28`). No version, no
  system name, no machine identifier, nothing from the database. This is stated next to the button (
  "GitHub receives this computer's IP address."), before every search by the tool and in the tab
  "Datenschutz" (Privacy) (`frontend/src/rechtliches/datenschutz.md`). The publisher runs no server
  for the program and receives no data.
- **Button, backend.** `GET /api/version/neueste` (`app/routes_version.py`, deliberately `def` instead of
  `async`, so that the blocking query runs in the thread pool) calls `update_pruefen.neueste_version(
  installiert)`: a GET on `{GITHUB_API}/repos/{GITHUB_REPO}/releases/latest` with `httpx`,
  `follow_redirects=False`, certificate verification on, at most 10 seconds (`ZEIT_S`) and at most 1 MB
  of response. The computer's proxy settings apply. The endpoint stores nothing, has no
  cache and writes no IP address and no response content to the log. The response is always
  200 and carries `installiert`, `neueste` (from `tag_name` of the form `vX.Y.Z`), `neuer` (comparison of the
  number tuples, `1.10.0` is newer than `1.9.0`; if the installed version is unknown or `0.0.0`,
  `neuer` is true), `veroeffentlicht` (date from `published_at`), `seite` (`html_url`, only if it
  starts with `https://github.com/{GITHUB_REPO}/releases/`, otherwise `null`), `aenderungen` (`body` of the
  release, at most 4000 characters, text only) and `fehler`. On an error a customer text is in
  `fehler` and all fields except `installiert` are `null`: "There is no connection to GitHub.",
  "GitHub is not responding in time.", "The connection to GitHub was interrupted.", "The secure
  connection to GitHub could not be verified.", "The response from GitHub is invalid.", on 404 "No
  version has been published yet." and on 403/429 "GitHub is currently limiting requests. Please
  try again in an hour." (without sign-in, 60 requests per hour and IP address apply).
- **Button, interface.** `VersionKarte` in `pages/Einstellungen.tsx` shows the button "Check for
  updates" (during the query "Searching …" and disabled) with the note on the IP address below it. The
  result reads "Your BMS is up to date (version X).", or "Version X has been released
  (DD.MM.YYYY)." with the changes and the link "View on GitHub ↗" (`target="_blank"`,
  `rel="noopener noreferrer"`, only if `seite` is set), or the error text. `aenderungenListe` shows the changes
  as plain text: only "- " lines, backticks as `<code>`, no HTML. For a
  package installation, the instructions for installing follow below it (quit the BMS, double-click `update.command` or
  `update_windows.bat`, start the BMS; without internet, put the ZIP file in the Downloads folder),
  for a Git installation "Development installation: updates come via Git." **The app
  never installs.** Installing works only with the server stopped, via the tool (its step 5 checks
  this).
- **Tool, information.** `online_auskunft()` queries the same address and checks the response strictly:
  `version` from `tag_name` without a leading `v` (form `X.Y.Z`, at most 9 digits per part); `url` is
  the `browser_download_url` of the asset `BMS_<version>.zip` and must read exactly `https://github.com/
  {GITHUB_REPO}/releases/download/v<version>/BMS_<version>.zip`; `groesse` (`size`) lies
  between 1 and `PAKET_MAX_BYTES` (200 MB); `sha256` comes from `digest` (form `sha256:<64 hex>`, calculated by
  GitHub on upload) and, if `digest` is missing, from the first string of the asset
  `BMS_<version>.zip.sha256`. If both are missing, nothing is installed ("The checksum for the latest version is missing.
  It will not be installed."). `seite` is `html_url` under the same conditions as
  above. The query follows no redirect. The two module-level functions are fixed as
  `online_auskunft` and `online_laden`.
- **Tool, download.** `online_laden(auskunft, ziel)` downloads to `data/updates/pakete/BMS_<Version>.zip.teil`;
  the file name comes solely from the verified version number, never from a response header.
  At most `groesse` bytes are read; size and SHA-256 are checked against the information before renaming to `.zip`
  ("The downloaded package is incomplete or damaged."); a
  damaged package never appears under the final name. Other `BMS_*.zip` and `*.teil` files in the
  folder are deleted beforehand, a file that is already present and matches is not downloaded again, and a package downloaded with
  `--pruefen` stays in place. After that the tool checks the manifest as for any package
  (version 3, SHA-256 per file).
- **Redirect rule.** When downloading, the tool follows at most `UMLEITUNGEN_MAX = 3` redirects. Each
  only to `https://`, to the standard port, without credentials in the address, and only to `github.com`
  or a host whose name ends in `.githubusercontent.com` (`_ziel_erlaubt`); any other destination
  is an error to which no request is ever sent. GitHub in fact redirects the download to
  `release-assets.githubusercontent.com`. This also applies to the `.sha256` asset.
- **Selection sequence.** The offer wins if it is higher than the installed version (with
  `--erzwingen` equal is enough) and higher than the best candidate in "Downloads". Every error of the
  online search is a notice, not an abort: it continues with the candidate from "Downloads". Without a
  candidate: if GitHub has answered and offers nothing higher, it says "Your BMS is up to
  date (version …)" with exit 0. If GitHub could not be reached or was not asked, the tool
  aborts with "No update package found …", followed by the reason.
- **Network.** The tool uses only the standard library (`urllib.request` with
  `ssl.create_default_context()`). Certificate verification is never switched off and is never repeated without verification after an
  error; the opener has no redirect handler; the computer's proxy settings
  apply. Time limits `ZEIT_AUSKUNFT_S = 10` and `ZEIT_LADEN_S = 120`. The text of a
  server response is never displayed: every response is mapped to a fixed customer text. Source-code guards
  (`tests/test_bms_update_github.py`): no `_create_unverified_context`, no `CERT_NONE`,
  `os.environ` only for the known names, no imports outside the standard library.
- **Old installations.** Installations up to 1.7.0 keep querying the former package service and
  never get 2.0.0 there. There is no bridge package: anyone with such an installation downloads 2.0.0 once
  as a ZIP file from the release page into the Downloads folder; after that the tool searches GitHub itself.

Honest limits: **The trust anchor is the publisher's GitHub account.** Anyone who takes it over can publish a release with
foreign code; `digest` and manifest would then come from the same place. Protection is
two-factor sign-in and releases only via `release.yml`. Possible later: proof of origin via a
GitHub attestation (`actions/attest-build-provenance`) and its verification in the tool. The
request limit of 60 requests per hour is enough for one button; behind a shared
company exit it can become tight. The release notes come from `CHANGELOG.md` and are shown only as
text; formatting other than "- " lines is lost.

### Local area: the label stays the identifier (P2-51)

`pipeline/suchprofil.py::stadt_kurzform()`/`umkreis_label()` (contract V7 of the build spec) form from
city and radius the label "<city short form> +<km>km" (short form = city name without
name suffix such as " am ", " an der ", " im "; "Frankfurt am Main" → "Frankfurt"). This label
is both display text AND IDENTIFIER — `Job.tab`/`Company.region` store it literally, exactly
as before with a fixed string containing city and radius, only now dynamically from the settings
(decision 5 of the build spec, cf. the lesson "blast radius" of 28.08.).

If an installation changes city or radius, `main.py::update_einstellungen` in the SAME
transaction converts `job.tab` and `company.region` from the old to the new label (including jobs
in the bin) before `suchprofil.regenerieren()` runs; the PATCH response additionally carries
`umbenennung` (`von`/`nach`/`jobs`/`firmen`), and the interface shows it as confirmation.
`tab_normalisieren()` also maps a DIFFERING old local-area name (any pattern
`<Text> +<Zahl>km`) to the CURRENT label when a job is written (ingest, `POST`/`PATCH /api/jobs`),
and normalises "remote"/"deutschlandweit" in any spelling to the canonical
form.

The local-area bucket in `config/suchprofile.yaml` (managed header) carries the label as
key under `buckets`, value `{regionen: [stadt], onsite_ok: true, stadt, umkreis_km}`. The
search runs read `stadt`/`umkreis_km` directly; an older header without these fields falls back to
`regionen[0]` or the number in the key.

### Mail provider: Gmail or IMAP (Phase 71F)

`pipeline/gmail_client.py` remains the facade that all mail skills call; it dispatches according to
`mail_settings.json` (secrets directory) either into the existing Gmail OAuth code path or
to `pipeline/imap_mail.py` — the latter opens the system to customers without Gmail (GMX, Web.de,
mailbox.org, Posteo, iCloud Mail with app password …), using only the Python stdlib
(`imaplib`/`email`, no third-party library). Only `INBOX` is searched; Gmail's search syntax
(`after:`/`from:`/`newer_than:`/…) is translated to IMAP; anything without an IMAP equivalent (e.g.
Gmail categories/labels) is skipped and reported rather than silently ignored. The same
security guarantee as for Gmail applies here too: exactly three verbs (`search`/`get`/`draft`),
no `smtplib` import anywhere in `backend/pipeline/` — backed by a test as a negative guard
(`tests/test_kein_sendcodepfad.py`).

### Automation limits (honest)

True scheduling (launchd/cron) fails when the project is in iCloud Drive: a background job can
**not** read iCloud Drive without a manual "Full Disk Access" grant (security setting,
user only). For that reason Excel/digest/search index are kept fresh manually via the `tageslauf` skill or
dashboard buttons. The deterministic refresh (`scripts/refresh_views.sh`) is
prepared to be cron-capable, but is not actively enabled.

Since P2-52 there is ONE exception: the backup schedule (`app/sicherung.py::starten()`) runs as an
asyncio task directly in the server process itself, independent of launchd/cron and thus without the
iCloud access problem above (the process is already running, with the rights of the terminal start).
Deliberately kept narrow: it backs up only the database, nothing else — Excel/digest/search index remain
manual, as described above.

### What the skill allowlist achieves — and what it does not (Phase 66)

`automation/agent_settings.json` activates a permission list for headless skills (`claude -p`):
only explicitly allowed tools/commands may run, everything else
is automatically forbidden. An honest limit matters here (see build spec Phase 66,
"The honest starting point"):

- **What it achieves:** protection against **accidents**. A skill that would inadvertently trigger `rm`, `git push`
  or `chmod` is stopped before anything happens — demonstrated in the real run of
  10.07.2026, when `Artifact` (publication to the outside) was correctly blocked.
- **What it does NOT achieve:** no boundary against a **targeted prompt injection**. The skills
  process foreign text unattended (job postings, incoming emails, company websites);
  `Bash(python:*)` is deliberately left unrestricted, because the documented pattern for
  DB write access is a Python heredoc. A Python one-liner can do everything `curl` can, and
  more — blocking only `curl` would be theatre; the same exfiltration would work two lines later via
  Python. This list therefore reduces only the damage from a mistake, not the
  risk of deliberate circumvention.

**What Phase 66 delivers instead** (damage limitation, labelling, detection instead of a
pretended security boundary):
- **66A — damage radius:** `agent_runner._child_env(kind)` passes on to each skill subprocess only
  the secrets from `agent.env` released for THAT kind (table `SECRET_KEYS_BY_KIND`,
  only mapping at present: `jobsuche-apify` → `APIFY_TOKEN`), instead of giving every key to
  every subprocess as before — with a loud message in the task log if a skill needs more after all.
  9 of 22 headless kinds additionally get `disallowed_tools` (WebSearch/WebFetch blocked where
  the skill demonstrably does not use them).
- **66B — labelling:** `agent_runner.HEADLESS_SUFFIX` (appended to EVERY headless prompt) explicitly marks
  every foreign text loaded via WebFetch/WebSearch/curl/gmail_client as
  data material, not as an instruction, with the request to ignore embedded instructions
  and report them in the report — supplemented at the two most concrete embedding points (`firma-pruefen`/
  SKILL.md job posting snapshot, `email-check`/SKILL.md email classification). This is **hygiene, not a
  guarantee** — a behavioural rule for the model, not a technical barrier.
- **66B — detection:** `scripts/outbound_check.py` reads the agent logs (read-only) and lists
  outbound destinations (curl/WebFetch) against a maintained list of expected hosts — no automatism,
  no cron, no alerting, a tool for a manual look when needed.

**Expressly open** (not part of Phase 66, only named here rather than defined away):
- **`gmail.compose` scope:** technically allows the Google API more than drafts (also sending) — the
  only boundary is the missing code path in `pipeline/gmail_client.py` (no `send` function,
  no `/send` endpoint), not the technology. Since Phase 71F the same guarantee applies to the
  IMAP provider `pipeline/imap_mail.py` (drafts only via APPEND, no `smtplib` import in
  `backend/pipeline/` — anchored as a negative guard in `tests/test_kein_sendcodepfad.py`).
  As long as a skill subprocess runs with free `python`/`curl`, this code path can in principle
  be bypassed.
- **Gmail access is file-based, not env-based:** `gmail_client.py` reads `gmail_credentials.json`/
  `gmail_token.json` directly from the secrets directory. `_child_env(kind)` (66A) therefore
  structurally CANNOT restrict this access — every skill subprocess runs as the signed-in user and can
  read the files like any other local program.
- **Options for this, without Phase 66 implementing them:** gradually move skills from free Python
  heredocs to a narrow, verified interface (e.g. a CLI with a fixed,
  auditable set of commands instead of arbitrary code) — that would make `Bash(python:*)` restrictable in the first place,
  but it is a separate, large phase, not an extension of this list.

### Path guard for Write/Edit (P2-38)

The occasion was a finding of 11.09.2026: a file `Bewerbung_Mgmt_System_inspect.py` next to the project folder
instead of inside it, written by a headless `cv-match` run that omitted a folder when assembling the project path
and turned a `/` into a `_`. No BMS code uses this wrong
path; the AI creates it itself in background runs — measured 109 of roughly 880 logged runs
since 13.08. across eight skills, mostly harmless, but 18 Write/Edit calls actually landed
outside the project. Until then the allowlist above permitted `Write`/`Edit` without any
path restriction.

Since then `automation/agent_settings.json` additionally carries a `PreToolUse` hook
(`automation/pfad_waechter.py`) for `Write`/`Edit`/`MultiEdit`/`NotebookEdit`. For each
call the hook checks the write target against the project root and known temp folders (`os.path.commonpath`, no
string prefix comparison — a neighbouring folder such as `Bewerbung_Mgmt_System_alt/` does NOT count as
"in the project") and blocks everything else with exit code 2. **Limit:** write paths via Bash (a
Python heredoc with `open(...)`, shell redirect `>`) are not covered by the guard — it checks only the
four tools named; as measured, however, all 18 mistakes went exactly that way. **Fail-open
by design:** an error in the guard itself (broken JSON, unexpected structure) blocks nothing
but lets the call through — it is a safety net against mistakes, not a mandatory route for
every write access. Details: build spec P2-38.

**Lingering `cd backend` (P2-53):** In Claude Code a `cd` applies to all FOLLOWING commands
of a run. After a `cd backend`, a relative `data/tmp/…` therefore ended up in
`backend/data/tmp/`, and the run searched for its own file there for several steps. Since then
the guard blocks `Write`/`Edit` to `backend/data/` and, through a second hook entry
(matcher `Bash`), checks exactly ONE shell pattern: working folder under `backend/` and a relative
`data/tmp` in the command. If the command itself begins with `cd`, it does not check. The message names the
right place (`../data/tmp/…` or the absolute path). Demonstrated in a real headless trial run:
the hook input `cwd` contains the lingering working folder, and the write attempt was blocked.
`HEADLESS_SUFFIX` additionally warns the runs in advance. All other Bash write paths remain unchecked.

**Intermediate files (P2-53):** `agent_runner.cleanup_tmp()` deletes in `data/tmp/` and in the mistaken location
`backend/data/tmp/` everything older than the log retention period (`AGENT_LOG_RETENTION_DAYS`, 30 days),
at server start and throttled after task completions, like `cleanup_logs()`. Files that a
tracked path field of the DB points to stay (`pipeline.cleanup._alle_referenzen`); without a readable
reference list the function deletes nothing.

### Headless authentication unified (Phase 77)

Occasion (07.08.2026): two Advisory Board runs started in parallel globally broke the shared subscription session
(Keychain) (new login required), while runner skill runs continued unaffected — the Advisory Board
engine and the skill runner checked authentication in a different order. Since Phase 77 the same priority applies to
both: **key from `keys.json` > runner token from `agent.env` > Keychain session**.
Only in the Keychain case does a serial **warm-up gate** run before the fan-out of an Advisory Board debate
(a short mini-turn behind a module-wide lock, 5-minute success cache,
failures are never cached) — it prevents several personas from requesting the same
session for the first time at the same time and wrecking it.

### Backups

**Automatic backup (P2-52, `app/sicherung.py`):** an asyncio schedule in the server (60 s after
start, then every 30 min) creates one backup per calendar day — SQLite online backup from
a source opened read-only, `PRAGMA integrity_check`, ZIP (`ZIP_DEFLATED`, level 6),
atomic rename — to `data/backups/auto/bewerbung_JJJJ-MM-TT_HHMMSS.zip`. A separate
subfolder, deliberately: three existing readers (`cleanup._backup_dateien`, `backup_db.sh --rotate`,
`agent_runner._backup_hinweis`) know only `data/backups/bewerbung_backup_*.sqlite` directly in
`data/backups/` and must not pick up the new series. Retention (pure function `zu_entfernen()`, testable without
file access): always the newest, all from the last 24 h, the newest per
calendar day for 7 days, per ISO week for 4 weeks, monthly adjustable (default
0) — thinning happens only AFTER a successful new backup. Settings in
`data/sicherung.json` (`GET/POST /api/sicherung`, `PATCH /api/sicherung/einstellungen`, router
`app/routes_sicherung.py`, card "Datensicherung" (Data backup) in Settings); dashboard notice on
failure or when the last backup is older than 3 days with automatic backup switched on.
Pure Python, no `sqlite3` CLI tool — runs unchanged on macOS and Windows. This module never touches the
EXISTING, manually created backups below; it only counts them for the
status information.

Before risky operations (dedup merges, migrations) the SQLite DB is backed up
(`backup_JJJJMMTT_HHMMSS`). Files are never hard-deleted but moved to the central
bin `data/papierkorb/` (Phase 32 — applies to file, job and
company deletion, each with a confirmation dialog; jobs remain as invisible
dedup tombstones). Deleted **network entries** (target companies, headhunters,
contacts) have been visible since 18.07. per tab in a collapsible bin panel and can be
restored with a click — deliberately without permanent deletion in the UI, because the
tombstones prevent an earlier Drive import or the file import (P2-62) from reviving deleted items. Permanent
emptying exists only manually via the cleanup command (`pipeline/cleanup.py`,
Phase 33: `scan` → `apply` → `leeren`).

**Restoring a backup (P2-66, `scripts/bms_wiederherstellen.py`):** standard-library tool
like `bms_update.py`, started via `wiederherstellen.command` (zsh) or
`wiederherstellen_windows.bat` (CRLF, block in round brackets) with
`--installation <ordner> [--liste] [--datei <name>] [--ja]`. It uses helpers from `bms_update`
(`_server_laeuft`, `_data_dir`, `_sperren`/`_entsperren`, `_rueckfrage`, `_pfad_unsicher`,
`_selbsttest_ausfuehren`) and deliberately also runs in a Git installation, because it affects only data.
Sequence: server check (`GET /api/health`; if it is running, abort) → lock
`data/updates/.update.lock`, shared with the update so that the two exclude each other →
collect candidates (automatic backups `data/backups/auto/*.zip`, manual `*.sqlite`/`*.zip`
directly in `data/backups`, ZIPs there only with exactly `bewerbung.sqlite` as content, so that folder backups
of other tools do not appear; not the update backups in `data/updates`, for those there is
`update --zurueck`) → numbered list, newest first (`--liste` ends here) → selection → check
in a temp directory (exactly one entry `bewerbung.sqlite`, SQLite header,
`PRAGMA integrity_check`, table `job`, self-test on a copy that migrates an older DB additively)
→ confirmation prompt (skipped with `--ja`) → back up the current state as
`data/backups/bewerbung_backup_<JJJJMMTT_HHMMSS>_vor_wiederherstellung.sqlite` (name pattern matches
`cleanup._backup_dateien`) → install via temp file and `os.replace`; existing
`-wal`/`-shm` files are renamed with a timestamp, not deleted → log
`data/backups/wiederherstellung_<stempel>.json` (`zeitpunkt`, `quelle`, `quelle_zeitpunkt`,
`sicherung_vorher`, `ergebnis`; within the same second with `_2`, `_3`). On an error after the replacement, the backup from the start
is copied back. Undo without a switch of its own: the backup "vor Wiederherstellung" (before restore) appears
in the list on the next call. Exit codes: 0 = OK or list only, 1 = aborted (No,
server running, lock taken, no backup, check failed, `data/` unchanged),
2 = error during installation (initial state restored), 3 = wrong call. Only the
database is replaced; `outputs/` and uploads remain. **Why no button in the app:**
`app/db.py` binds the database at import time in a single engine without `dispose`/reinit; a
swap while running would be risky. Both launchers and the script are in
`PFLICHTDATEIEN`, the `.command` in `_STARTDATEIEN_AUSFUEHRBAR` (`pipeline/kundenpaket.py`).

### Sample data of a fresh package installation (P2-59)

Anyone starting the BMS for the first time would see empty pages. `app/beispieldaten.py` therefore creates, on the
very first start, the fictional application history of "Benno Bewerbaer" (postman, five years of
parcel delivery). The data is CREATED at start-up rather than shipped: the update tool
never writes to `data/` and rejects packages containing `data/` or `config/profil.md`.

**First-start rule** (`einspielen_falls_neu(db_war_da)`): data is created only if ALL of the following hold:
(1) the database file did not exist before the start, (2) the marker `data/beispieldaten.json`
is missing (even "removed" counts, never twice), (3) the installation is a package (`app/version.py`)
or `BMS_BEISPIELDATEN=1` is set (for tests and acceptance; a Git installation
therefore never gets any) and (4) the tables `job`, `company`, `email` and `application` are empty.
The function never raises: an error results in a log line and `False`, and because all rows are created in ONE
transaction, nothing half-finished is left behind.

**Start order** (`main.py::_startup`): `db_war_da = db.DB_PATH.exists()` BEFORE `init_db()` (which
creates the file), then `init_db()`, `suchprofil.sicherstellen()`,
`beispieldaten.einspielen_falls_neu(db_war_da)` (on `True`, `_profil_struktur_schreiben` follows,
because skills and career history flow into `config/profil_struktur.md`), `agent_runner.start_workers()`
and `sicherung.starten()`. Within `einspielen_falls_neu`, first the rows are created, then
`config/profil.md` and `data/cv_basis/base_de.docx` (each only if still missing, each individually
protected) and finally the marker. If a file fails, the marker is still
written: without it the existing rows could never be removed again.

**Content:** 6 companies (`notes="Beispieldaten"`), 5 jobs (`dedup_key="beispiel|…"`, one each in New,
To review, Applied, Interview and Rejected, times relative to the start, `url=None`), 3 applications, 5 emails
without a Gmail ID (sender under `*.beispiel.de`, response times calculated as in the email ingest, one
email without a job for trying out the archive), 1 interview appointment in 3 days including counterpart,
1 network contact, 14 skills and 5 career-history entries (`quelle="beispiel"`), the profile fields
`headline`/`standort`/`positionierung` (only if empty), `config/profil.md` in the structure of the template from
`pipeline/profil_datei.py` (until P2-68 it was in `BMS_Install.md`) and a German base CV in the v10 structure that `pipeline/cv_export.py` expects.
NOT created: search plans and search areas (otherwise the daily run would perform real searches), target companies,
headhunters and CV versions. Companies and jobs carry no web address, so that no background run
fetches them. The skill `beworben-check` (part of the daily run) filters jobs with `portal`
"Beispieldaten" out of the check set and the skip check, otherwise it would search the career pages of the fictional
companies (guard `test_beworben_check_laesst_die_beispielstellen_aus`). All texts of the module pass the package check (email addresses under `beispiel.de`, the
example number, no existing IDs), because they are shipped as string constants.

**Marker** `data/beispieldaten.json` (written atomically): `status` (`vorhanden` (present) or
`entfernt` (removed)), `angelegt_am`, `name`, `ids` (the created IDs per table, also `joblog`), `dateien`
(relative path → SHA-256 of the created file) and `profil_werte` (the profile fields actually
set). After removal it contains `status="entfernt"` with `entfernt_am` and `sicherung`;
`ids` and `dateien` are empty. `GET /api/beispieldaten` turns this into `status` (`keine`, `vorhanden`,
`entfernt`), `name`, the two timestamps and the count per kind; the card in Settings and
the notice in the dashboard (only when `vorhanden`) read it.

**Removal** (`POST /api/beispieldaten/entfernen`, `beispieldaten.entfernen()`, a lock against
a double call):

1. Only when `vorhanden`, otherwise `ValueError` → 409. If a task is running on a sample job
   (`queued`/`running`), likewise 409: after the deletion it would write to a job that no longer
   exists.
2. Backup via `app.sicherung.anlegen()`, i.e. in the series of automatic backups under
   `data/backups/auto`, like "Back up now". `SicherungLaeuft` → 409, any other error → 500. In
   both cases everything remains unchanged.
3. One transaction. Only rows that carry the ID AND a second attribute are deleted (`_beispiel_bedingungen`:
   `job.dedup_key LIKE 'beispiel|%'`, company name from the list,
   `email.from_addr LIKE '%beispiel.de%'`, `contact.email LIKE '%beispiel.de'`, network contact by
   name, for skills and career history `quelle = 'beispiel'`). Reason: SQLite reissues the ID of the most recently
   deleted row. If a customer deleted the last sample skill by hand and then entered
   one of their own, they would get the same ID. In addition, everything attached to a sample job: every
   table with `job_id` except `email` and `agenttask`, determined from `models.py`, children first. Emails without a sample attribute
   on a sample job and tasks (cost history in the Task Centre) are detached (`job_id` and
   `application_id` emptied), not deleted. The customer's own rows with `company_id` pointing to a sample company
   lose only the reference. The profile fields are emptied only as long as they still
   match the sample values. This is hard deletion without a tombstone, unlike "delete job" (Phase 32): the
   backup is the way back.
4. Files only AFTER the commit: if a move fails, a file is left behind rather than a
   database pointing to deleted items. `config/profil.md` and the base CV go to
   the bin only if their SHA-256 still matches the one created; otherwise they stay and are listed in
   `behalten`. The move is its own (`data/papierkorb/<JJJJMMTT>_<Name>` (older entries still carry `JJJJ_MM_TT_`)), not the
   helper of the delete endpoints: that one admits only the folders of the allowlist, and the profile file lies in
   `config/`. The artefacts that a customer created on a sample job (path columns
   `*_path` of the deleted rows) also go to the bin, checked by `_artefaktpfad_pruefen`:
   only files under `data/` and `outputs/` (the resolved path counts), never `data/papierkorb/`,
   `data/backups/`, the database or the base CVs.
5. Marker to `entfernt`. The router then rewrites `config/profil_struktur.md`
   (`_profil_struktur_schreiben`, imported locally within the function) and answers with `entfernt` (count per
   kind), `geloest` (emails, tasks), `behalten`, `sicherung` and `status`. The interface then
   triggers `PROFIL_GEAENDERT`.

After removal the sidebar shows the fallback name "Applicant" (`user_profile.user_name()`)
until a `config/profil.md` of the user's own with a name exists (since P2-69 the card "Identity and
search strategy" creates it, see the next section). The LinkedIn import (`pipeline/linkedin_import.py`)
fills profile fields only if they are empty and skips skills and career-history entries that already
exist, regardless of `quelle`. With sample data in the profile, it would therefore not adopt the user's own positioning;
for that reason the customer documentation says "first remove sample data, then import". Tests:
`tests/test_beispieldaten.py` (conditions, content, base CV, removal, router and the first start
in a subprocess following the pattern of `tests/test_neuinstallation.py`).

### Profile file: the "Identity and search strategy" form (P2-69)

Until P2-68 the customer created `config/profil.md` by hand in a text editor, and the spelling
`**Name:**` mattered. No endpoint wrote the file. Only `app/beispieldaten.py` touched it (creates the
sample file and removes it again) and the skill `absagen-analyse` (replaces the section
`## Empirie aus dem Bewerbungsverlauf`). Since P2-69 the first card of the Profile page,
"Identity and search strategy" (`components/ProfilIdentitaet.tsx`), reads and writes the file. The file remains the
only source; readers and skills do not change. Contracts F (format), A (API), O (interface)
and D (documentation) are in the build spec P2-69.

**Modules.** `pipeline/profil_datei.py` (contract F: pure functions for splitting and assembling
plus `lesen()` and `schreiben()`, no import from `app`) and `app/routes_profil_identitaet.py` (contract A,
router like `routes_sicherung.py`, in `main.py` only import and `include_router`). The reader
`pipeline/user_profile.py` stays unchanged: it reads name, location, contact and LinkedIn by regex
(from which letterhead, file names, sidebar and the start point of route planning are derived), and the form produces
exactly the spelling `- **Name:** …` that these regexes expect. `profil_datei` reads the path at
runtime from `user_profile._PROFIL_MD`, so that tests can redirect it with the same patch as before.

**Lossless splitting.** The form changes only what it displays. Everything else stays byte for byte
the same: unknown sections, unknown lines in known sections, `Sprachen / CV-Fassungen`,
the empirical section, blank lines, line endings (LF or CRLF) and the file header. The only exception in the header: the title line `# Kandidatenprofil: <Name>` follows along if the name is changed in the form and the line carries exactly the previous name. Saving without a change in the
form produces exactly the same file.

- The file is split into the header (everything before the first line `## `) and the sections. They are recognised by
  their heading text (trimmed, case-insensitive, "starts with"): `Identität`
  (field lines: name, positioning, location as "address", contact as email and phone,
  LinkedIn, current; further field lines as `weitere` with an editable value), `Kurzprofil`,
  `Harte Rahmenbedingungen` and `Bekannte Skill-Gaps` (each free text) and, from `Zielrolle`, only the
  line `Zieltermin`. Older lines such as level or industry stay untouched in the file; title, level and
  industry come from the search plans. All other sections stay unchanged; the API reports only their heading
  (`unveraendert`).
- A field line is `^(\s*[-*]\s*)\*\*(.+?):\*\*[ \t]*(.*)$`. When changing, only the value is
  replaced; indentation, bullet and key stay. A new field goes after the last
  field line of the section. An existing field with an empty value keeps its line; only for the
  optional fields positioning, LinkedIn and current is it removed. A new field with an empty value
  is not created.
- Contact: when reading, the text is split at `·` or `|`; the first part with `@` is the email, the rest
  (joined with ` · `) is the phone. What is written is `E-Mail · Telefon`, without a
  separator if there is only one value.
- Free-text sections go to the form without the blank lines at the start and end. When writing, the
  previous number of blank lines before and after the body is kept; an unchanged text leaves the
  section byte-identical. New lines get the line ending that predominates in the file.
- If the file is missing, `lesen()` returns `vorhanden=False`, empty values and the target date, and `schreiben()` creates the template (structure as in `beispieldaten._profil_md_text()`,
  with the sections Identität, Kurzprofil, Zielrolle, Harte Rahmenbedingungen, Sprachen /
  CV-Fassungen, Bekannte Skill-Gaps / Red Flags and Empirie). If a known section is missing from an existing file,
  `schreiben()` creates it only if the form supplies content, before the empirical section
  or otherwise at the end of the file.

**Writing and checks.** `schreiben()` replaces atomically (temp file in the same folder, `os.replace`,
UTF-8). Beforehand a copy of the old file goes into the bin `data/papierkorb/` (date prefix
`JJJJMMTT_` as with `_freier_name`); nothing is hard-deleted. A `ValueError` with customer text (formal "you" form)
reports: name missing (required), line break in a single-line field, length over 300 characters (single-line)
or 5000 (free text), a key in `weitere` or `zielrolle` that exists neither in the file nor among
the standard keys, and a free-text line that begins with `## ` (it would create a new
section). Non-blocking `hinweise`: the address has no comma or no postcode
(the place line of the cover letters is built from `Straße Nr, PLZ Ort`), or the email has no `@`.

**API** (`GET/PUT /api/profil/identitaet`). The response carries `vorhanden`, `stand`, `identitaet`
(`name`, `positionierung`, `anschrift`, `email`, `telefon`, `linkedin`, `aktuell`, `weitere`),
`kurzprofil`, `zielrolle` (list of `schluessel` and `wert`), `rahmenbedingungen`, `skill_gaps`,
`unveraendert` and `hinweise`. `stand` is the SHA-256 of the file content, empty if the file is missing. The
PUT accepts the same structure with `stand`. An outdated `stand` results in 409 ("The profile file
has been changed in the meantime. …") and leaves the file unchanged: between loading and saving a
skill may have replaced the empirical section, and the card must not silently overwrite that. A
`ValueError` results in 400 with the text in `detail`. On success the PUT answers in the form of the GET
(freshly read) plus `papierkorb` (path of the backup copy or `null`).

**Origin check.** The PUT is a writing call and falls under the origin check (foreign
requests get 403); the guard test in `test_herkunftspruefung.py` itself also counts the route via
`app.openapi()`. There has been no licence lock since P2-82.

**Interface.** After "✓ Saved", the card triggers `PROFIL_GEAENDERT` (sidebar and
route planning reload). `hinweise` appear as amber lines, 400 shows the text, 409 the text with
the button "Reload". Anyone who saves the file in the card changes
its SHA-256: "Remove sample data" then treats it as the user's own version and leaves it in place
(`behalten`).

**Tests.** `tests/test_profil_datei.py` (round trip byte-identical for the template, the sample file and an
extensive fictional file including CRLF and a missing line ending at the end, line diff for
changed fields, contact, optional fields, all checks and notices, atomic writing,
bin copy) and `tests/test_profil_identitaet_api.py` (GET without a file, PUT creates, 409, 400,
saving without a licence file). All paths lie under `tmp_path`.

### File delivery: documents only, only from `frontend/dist` (P2-54)

The server delivers files in exactly two places. `GET /api/artifact` releases only files from the
folders of the allowlist `_ARTEFAKT_ORDNER` in `main.py`, and there only the file types that
the interface opens: reports (`.html`) from `company_fit`, `job_postings`, `interview_prep`,
`beirat`, `analysen` and `transcripts` (there also `.md`), upload types from `job_files` and
`profil/dateien`, Word/PDF from `cv_basis`, `tmp` (registered CV drafts), `outputs/cv`,
`outputs/cv_entwuerfe` and `outputs/anschreiben`. Everything else returns 403, even if the file
exists: database, backups, updates, `sicherung.json`, raw data, bin. The resolved path
(`..`, symlinks, backslashes) is checked, and before existence is checked. **Anyone who introduces a new
folder for artefacts must register it there**, otherwise it stays unreachable. The
SPA fallback (`main.spa`) delivers only files inside `frontend/dist`; anything else gets
`index.html`. Until P2-54, `%2e%2e` and `%2F` paths passed through there, i.e. every readable file of the
computer. LAN mode nevertheless remains without sign-in: interface and API are open on the network, only
whole databases, backups and foreign files can no longer be retrieved.
`GET /api/doku/{name}` (P2-59) is not part of this: it delivers no file but the page for
an entry from a fixed catalogue; the name from the address is never used as a path (see
"Documentation page" below).

### No release for foreign websites (CORS, P2-55)

The backend sends no `Access-Control-Allow-Origin` header. A foreign website in the same
browser therefore does not get to see the API's responses, and requests that need a preflight (JSON content, PATCH, DELETE) are not even sent by the browser. The app's own callers
need no release: the interface comes from the same server, also in LAN mode at
`http://<name>.local:8000`; the Vite dev server forwards `/api` via proxy; skills and scripts
use curl or Python, to which CORS does not apply. Until P2-55, `main.py` contained a
`CORSMiddleware` with `allow_origins=["*"]` and all methods: any website could read jobs, emails
and profile, start AI runs and delete jobs, even a locally opened HTML file
(`Origin: null`). **Anyone who must release an origin enters it individually, never `*`**, and adjusts
`tests/test_keine_cors_freigabe.py`. What CORS never protected against has been caught since P2-57 by the
origin check (next section): simple requests without a preflight (POST without content, as a
form or upload) are still sent by the browser; only the response stays hidden from the foreign page.

### Origin and host check (P2-57)

Before every route, the middleware `_Herkunftspruefung` in `main.py` checks two things; on a
violation it answers with 403 and a message in `detail`.

**Host (every request, including interface and assets):** The server answers only under an
IP address, `localhost`, a name ending in `.local` or a computer name without a dot. A foreign domain
cannot fake these names via DNS rebinding: if it switches its DNS entry to `127.0.0.1` after
loading, its page is the same origin for the browser and would read the API
without any CORS release, in local as well as LAN mode. The addresses that `start_lan.command`
displays always work. Further names (router name such as `mac.fritz.box`, Tailscale, reverse proxy)
are released by the environment variable **`BMS_HOSTS`**, separated by comma or space: on the Mac
in the terminal `BMS_HOSTS=mac.fritz.box ./start_lan.command` (with a double-click in Finder no
environment variable arrives), on Windows `set BMS_HOSTS=mac.fritz.box` in the same
command prompt before starting.

**Origin (everything except GET, HEAD, OPTIONS):** If the browser sends an `Origin`, host and
port must match the `Host` header. The scheme does not count, and a missing port counts as the
default port of the origin's scheme, so that a proxy with TLS in front works. `Origin: null`
(locally opened HTML file, sandboxed iframe, since P2-58 every report) is blocked. Without an
`Origin` (curl, skills, scripts, Python) the request passes. The only exception is
`http://localhost:5173`, the Vite dev server via its proxy: only to host `localhost` (the proxy
rewrites the host to that) and only with `Sec-Fetch-Site: same-origin` or without this header.
Another project on port 5173 that addresses the server directly reports `same-site`; browsers send no `Sec-Fetch-Site` at all to a
`.local` name or a LAN IP, hence the binding to
`localhost`. **Port 5173 is part of the exception:** `vite.config.ts` sets `strictPort`, so that
Vite aborts if the port is taken instead of silently moving to 5174 (every
write access would then get 403).

Until P2-57, any website could blindly trigger 21 routes, including `discard` (every job to
"No match"), replacing the base CV with `overwrite`, the ZIP import (run `skills-sortieren`),
`POST /api/sicherung` and the connection tests for coach site and email. Behind a
reverse proxy, the proxy must pass the host header through including the port (Caddy does this by itself,
nginx needs `proxy_set_header Host $http_host;`), and its name belongs in `BMS_HOSTS`.
Residual risk: anyone on the same network who forges mDNS or LLMNR responses can still redirect via a `.local` or
dotless name; in LAN mode such a person has direct access anyway. Contract:
`tests/test_herkunftspruefung.py`, with a guard over all operations from the
OpenAPI schema. The licence check that sat inside this check (402) from P2-67 to 1.7.0 has been
removed since P2-82 (section "Licence — removed").

### Reports in the sandbox (P2-58)

HTML reports from `/api/artifact` and the daily digest (`/api/digest`) carry the header
`Content-Security-Policy: sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox`
(`_BERICHT_SANDBOX` in `main.py`). This gives the browser its own opaque
origin (`null`) for them instead of that of the API. A script in a report, for instance via a prompt injection
from web content that an AI run has picked up, then no longer reaches the API: reading fails
for lack of a CORS release (P2-55), writing at the origin check (`Origin: null` → 403,
P2-57). Until P2-58, such a script ran in the origin of the API, read jobs, emails and profile and wrote
past the check with a suitable origin; reproduced in the browser, a trial report discarded a
job. In addition there is `Cache-Control: no-cache` (both in `_BERICHT_KOPF`): without it Chrome
showed a previously opened report from the cache with the old headers, i.e. without sandbox.

Still allowed (measured in Chrome 154): scripts (71 older reports up to 08.08.2026 build their
content by script), links in new tabs (these tabs are normal pages, hence
`allow-popups-to-escape-sandbox`), links in the same tab, printing via the browser menu and the
embedded favicon. No longer allowed, used by no report: forms, `alert` and
`confirm`, `window.print()` from a script (would need `allow-modals`), `localStorage`, cookies,
fonts or data via `fetch` from the BMS server (both need CORS). **Anyone who builds something like that into a
report needs a separate release; never `allow-same-origin`**, it would cancel the protection.
PDF, images, Word and downloads (`download=true`) remain without the header, as does the interface itself
(`index.html`, `/assets`). A new HTML route sets `_BERICHT_KOPF`; a guard in
`tests/test_bericht_sandbox.py` reports every `HTMLResponse` outside `artifact`, `digest` and
(since P2-59) `routes_doku.dokument`, the documentation page (next section).
Residual risks: an injected script can still send the content of its own report to the outside
or redirect the page. Reports that the browser had already cached before P2-58
come without sandbox until their cache period expires (for older reports a good week);
reloading (Cmd+R) or clearing the browser cache once fixes that. Inventory and
measurements: build spec P2-58.

### Documentation page (P2-59)

The page `/dokumentation` (menu item "📖 Documentation", `frontend/src/pages/Dokumentation.tsx`)
shows the installation's documents in tabs, without a Markdown renderer of its own in the frontend: the
backend renders them with the same renderer as the `docs/*.html` twins
(`pipeline/docs_render.py`), and the page shows the result in a frame (`iframe`).

**Catalogue instead of folder scan** (`app/doku.py::KATALOG`, the order is that of the tabs). Each
entry has an identifier, title, group and file relative to the project root. Group `kunde` (customer): `version`
(`CHANGELOG.md`), `funktionen` (`docs/FUNKTIONEN.md`), `anleitung`, `installation` (the file of the
running system: `BMS_Install_Windows.md` on Windows, otherwise `BMS_Install_MAC.md`), `email`
(SETUP-EMAIL), `windows` (SETUP-WINDOWS), `coach-site` (ANLEITUNG_COACH_SITE), `beirat`
(BEIRAT-CHARTA); the former tab `lizenz` was dropped with P2-82. Group `intern` (internal): `technik` (this file), `automatik`, `release` and
`entwicklung` (`docs/INSTALLATION.md`). `verfuegbar()` omits every entry whose file is missing:
the customer package does not contain the internal files, so their tabs are missing there automatically, without an
identifier for the installation type. Not in the catalogue are COACH_SITE, GMAIL-STRATEGIE, WAS_IST_NEU and
BEIRAT-PERSONA-TEMPLATE (the template is shipped but has no tab).

`eintrag_fuer(name)` resolves an identifier (without a dot) or a file name (`.md` or `.html`, case-insensitive,
ASCII only) exclusively against the catalogue: the name
from the address is never used as a path, anything else is unknown (also `..`, slashes and
names that exist as a file but are not in the catalogue). File names are allowed so that relative
links between rendered documents work: `SETUP-EMAIL.html` resolves under `/api/doku/…` to
`/api/doku/SETUP-EMAIL.html`, whereas in a directly opened `docs/*.html` the same link points to the
neighbouring file. The two guides `BMS_Install_MAC.md` and `BMS_Install_Windows.md` (each `.md` and
`.html`) both resolve to the tab `installation`, even though the tab shows only the file of the
running system; since P2-71 the resolution no longer knows the former names `BMS_Install.md` and `BMS_Install_Auto.md`. `rendern()` reads only catalogue entries (otherwise `ValueError`), hides an empty section "Unveröffentlicht" in the CHANGELOG (it
would remain as an empty card in first place after every release, and that is exactly what every customer would see first) and adds
`target="_blank" rel="noopener noreferrer"` to every link to a web address, otherwise a click would load the foreign page into the frame,
and many pages forbid that.

**Router** (`app/routes_doku.py`, prefix `/api`): `GET /api/doku` returns `[{id, titel, gruppe}]` of the
available documents, `GET /api/doku/{name}` the rendered page as `HTMLResponse` with
`_BERICHT_KOPF` (sandbox and `no-cache`, P2-58; imported from `app.main` locally within the function, at the top of the
module it would be a circular import; this way the header remains a single source). Unknown or not readable: 404
"Dokument nicht gefunden" (Document not found).

**Frame with sandbox:** The page sits in a frame with
`sandbox="allow-popups allow-popups-to-escape-sandbox"`, i.e. neither `allow-scripts` nor
`allow-same-origin`. With the header (`allow-scripts allow-popups …`) the intersection applies: in the frame
no script runs, the document has its own origin and does not reach the API, and a link to
a web page opens in a normal new tab. "Open in new tab ↗" loads the same address
directly, where only the header applies. **Do not extend the rights:** `allow-same-origin` together with
scripts would cancel the sandbox, and `tests/test_doku.py::test_rahmen_der_oberflaeche_bleibt_in_der_sandbox`
fixes the list at exactly these two rights. In the tab "Version", above the frame, is
"Installed: version …" from `GET /api/version`, and for a Git installation the
development state next to it in small type. When the tab is switched, a new frame is created (`key`), otherwise the
browser history would get an entry for each switch.

**Guard:** `tests/test_bericht_sandbox.py::test_waechter_html_nur_aus_artifact_digest_und_doku`
expects exactly three HTML deliveries with `headers=` (`artifact`, `digest`, `routes_doku.dokument`);
a fourth without a sandbox header makes it fail. `tests/test_doku.py` covers the rest: catalogue
against `pipeline.kundenpaket`, resolution including foreign names, rendering, router, frame and the integration
into the real app.

**In the customer package:** `pipeline/kundenpaket.py::DOKU_ERLAUBT` is the allowlist of the shipped
`docs/` documents (each `.md` and `.html`): ANLEITUNG, ANLEITUNG_COACH_SITE, BEIRAT-CHARTA,
BEIRAT-PERSONA-TEMPLATE, FUNKTIONEN, SETUP-EMAIL and SETUP-WINDOWS. In addition, in the package root
`BMS_Install_MAC.md`, `BMS_Install_Windows.md` and `CHANGELOG.md`. `docs/FUNKTIONEN.md` is the short overview of the functions by
work step, without phase numbers, and is additionally in `PFLICHTDATEIEN`: if it is missing from the finished
package, the package is broken, because the tab "Funktionen" (Functions) would be missing.

### Network import: lists from a file (P2-62)

Target companies, headhunters and network contacts can be created from a file at any time: button "⇪ Import
from file" in all three tabs of the Network page. Requirements of 01.10.2026: CSV and Excel
(`.xlsx`) with a template per list, plus the LinkedIn export `Connections.csv` (network contacts only);
existing entries are completed only in empty fields and never overwritten, entries deleted in the app
stay deleted. This is the rule of the earlier one-off migration from Excel (Phase 22, the tool has been removed; principle 4
in §3: dedup lives on retained rows). The module imports no internal script (a test enforces this). Spec: P2-62.

**Building blocks:** `app/netzwerk_import.py` (the core, knows no FastAPI and raises `ImportFehler(status,
text)`), `app/routes_netzwerk_import.py` (router with prefix `/api`: reads the file with the limit of 5 MB
before parsing and translates `ImportFehler` into `HTTPException`; the routes are synchronous and run in the
thread pool, so parsing, backup and writing do not block the event loop), the integration in
`main.py` (`include_router`), the interface (see below) and `tests/test_netzwerk_import.py`. The core
offers three public functions: `vorlage(liste, format)`, `vorschau(liste, dateiname, inhalt, *,
session)` and `importieren(liste, dateiname, inhalt, *, session, daten_dir=None)`.

**Endpoints** (`{liste}` is `zielfirmen`, `headhunter` or `kontakte`, otherwise 404; errors come as
`{"detail": <customer text>}`):

- `GET /api/netzwerk-import/{liste}/vorlage?format=csv` (or `xlsx`, `csv` if not specified): the template for
  download (`Content-Disposition: attachment`, file name `Vorlage_Zielfirmen.csv`,
  `Vorlage_Headhunter.xlsx`, `Vorlage_Netzwerk-Kontakte.csv` etc.). It contains only the header row with the
  German column names, the required column first. CSV with semicolon and UTF-8 with BOM (so that Excel in
  German-speaking regions displays the umlauts correctly); XLSX with the sheet of the list (header row bold and frozen) and a
  second sheet "Hinweise" (notes) (per column: required or not, permitted values and formats, further recognised names).
  Unknown `format`: 422.
- `POST /api/netzwerk-import/{liste}/vorschau` (multipart field `datei`): reads and plans, writes NOTHING
  (no database change, no backup). Response: `liste`, `format` (`csv`, `xlsx` or `linkedin`),
  `blatt` (Excel only), `spalten` (`erkannt` with `spalte`, `feld`, `label`; `ignoriert`), `anzahl`
  (`zeilen`, `neu`, `ergaenzt`, `unveraendert`, `geloescht`, `fehler`), `zeilen` (`nr`, `aktion`, `anzeige`,
  `felder_ergaenzt`, `meldung`), `zeilen_gekuerzt` and `hinweise`. `nr` is the row number in the file,
  counting the header row. `zeilen` contains all error and deleted rows plus the first 100 others
  (`ZEILEN_UEBRIGE`) in file order.
- `POST /api/netzwerk-import/{liste}` (multipart field `datei`): plans again (the file comes once more; the
  server remembers nothing between the steps), backs up and writes. Response: `{"anzahl": {…as for
  the preview…}, "sicherung": <file name> or null}`.

**Error codes** (preview and import): 413 if the file is over 5 MB (`MAX_BYTES`; the router checks
`UploadFile.size` and reads at most 5 MB plus one byte; `_einlesen` checks once more for direct calls).
400 for a missing file in the field, an extension other than `.csv`, `.txt` and `.xlsx` (`.xls` with the note to save as
`.xlsx` or `.csv`), an empty or unreadable file (binary data as CSV; broken Excel file;
over 200 MB when unpacked, protection against zip bombs), a missing header row, a missing required column
(`Liste.spalte_fehlt`, e.g. "No column for the company found. For example, "Firma" is expected.")
and more than 5,000 data rows (`MAX_ZEILEN`, excluding header row and blank rows). 404 for an unknown list.
409 only on import: a backup is currently running, or the database is busy. 422 for an unknown
`format` of the template. 500 if the backup fails ("The backup before the import failed;
nothing was imported. Reason: …") or writing fails ("The import failed; nothing
was imported. Reason: …"); in both cases nothing is changed.

**Configuration per list** (`LISTEN`, ONE table instead of branches): one `Liste` (frozen
dataclass) per list with model, fields, sheet names, key fields, required columns and required values, display,
error texts and default values for new entries (`standard_neu`: for target companies `last_update` = today);
one `Feld` per field with template name, synonyms, hint text, normaliser (`norm`), `in_vorlage`,
`modellfeld` and `nicht_gleich`. The backend derives from this one table the column recognition, the
templates (CSV and the sheet "Hinweise"), the planning and the display of the preview; there is no second list there that
could drift apart. Helper fields (`modellfeld=False`: first name, last name and the three LinkedIn columns)
are resolved before planning and never written to the model. The key is the same as for the
create endpoints in `main.py` (`app.normalize.slug_parts`): target company `company`, headhunter `firma` and
`ansprechpartner`, contact `name` and `unternehmen`. An imported entry and one created by hand
can thus never stand side by side. The comparison is literal according to `slug_parts` (lower case, only `a-z0-9`); a
fuzzy comparison as in the job ingest (legal-form suffixes, P2-39) does not take place: "Muster" and "Muster GmbH"
are two entries.

**Formats** (`_einlesen`; checks are made in this order: size, extension, empty):
- **CSV and TXT:** UTF-8 with or without BOM, UTF-16 with BOM (Excel "Unicode text"), otherwise cp1252, as a last resort
  latin-1. `_trennzeichen` decides the delimiter from the header row: `csv.Sniffer` counts only if
  its result occurs there at least as often as any other; otherwise the most frequent of `;`, `,`
  and tab applies (semicolon in a tie). The row number is the running record, which is how Excel counts too.
- **XLSX** (`openpyxl`, `read_only=True`, `data_only=True`): sheet selection takes the first name from
  `Liste.blaetter` (target companies: "Zielfirmen", "Target Companies"; headhunters: "Headhunter", "Headhunters";
  contacts: "Netzwerk", "Netzwerk-Kontakte", "Network Contacts", "Kontakte"; compared via the same
  key as the columns), otherwise the first sheet, and adds a note if there are several sheets. The
  rank of the names decides, not the order in the file: the app's Excel export has a sheet "Kontakte" before
  "Netzwerk" (the job contacts), which is not meant here. `reset_dimensions()`
  protects against files with an incorrect dimension entry (some programs write "A1" and would otherwise cut off
  rows). The header row is the first row with content.
- **LinkedIn** (list `kontakte` only, CSV or `.xlsx`): `Connections.csv` has note lines ("Notes: …") before the
  header row. The header row is the first row with "First Name" and "Last Name" among the first 30 non-empty
  rows (`_KOPF_SUCHE`); the file counts as `linkedin` if, in addition, "Connected On" or "URL" is in the
  header row. What is mapped: name (first name plus last name), company ("Company"), role
  ("Position"), channel "LinkedIn" (only if the channel cell is empty) and notes from "LinkedIn: <URL> · E-Mail:
  <address> · verbunden seit TT.MM.JJJJ" (connected since DD.MM.YYYY) (only what is present, `_kontakt_aufloesen`). Relationship, last
  contact, priority, next action and due date stay empty. In addition there is the note that LinkedIn supplies all
  connections and that the list is intended for actively maintained contacts. The recognition also applies
  to an `.xlsx` (acceptance: the note advises trimming in Excel, and Excel then often saves as a
  workbook; a "Connected On" converted into a date in the process is read like any date cell).
  For `zielfirmen` and `headhunter`, a LinkedIn file is an ordinary CSV; the
  required column is then missing, hence 400.

**Column recognition** (`_spalten_zuordnen`): `_schluessel()` turns a heading into the
comparison key (NFC, lower case, ä/ö/ü/ß to ae/oe/ue/ss, only `a-z0-9`; NFC first, because a "ü" from
macOS files can consist of "u" and a diaeresis) and compares it with the template name and the synonyms
of the fields. The first matching column per field wins; every further one for the same field and every one without
a mapping ends up under `spalten.ignoriert`. At least one of the `pflicht_spalten` is required (target companies
`company`; headhunters `firma` or `ansprechpartner`; contacts `name`, `vorname` or `nachname`), otherwise
400. If the name cell of a row is empty, `name` is derived from "first name last name".

**Values:** Cells are trimmed (also non-breaking spaces and BOM), empty becomes `None`, whole floats from
Excel lose the ".0", Excel dates become ISO. Dates stay ISO or are read from `TT.MM.JJJJ`, `T.M.JJ`
(from 2000) and LinkedIn's "12 Sep 2023" (`_datum_iso`; a day that does not exist is not readable).
If not readable: `letzter_kontakt` and `last_update` stay as text (`_datum_text`),
`next_action_date` stays empty (`_datum_streng`), because the field is monitored (due actions appear
under follow-ups), and the row gets a message. What is harmonised: priority (Hoch, Mittel,
Niedrig — high, medium, low — also in English), the channel of the contacts (LinkedIn, E-Mail, Telefon, Persönlich — in person), tier ("1", "1.0"
and "Tier 1" result in "1") and scenario (capital letter, also "a/b"); anything unknown stays as it is.
`last_update` of a target company is the file value; for NEW entries without a value it is today (`_heute()`, a
separate function so that a test can fix the date).

**No automatic `next_action_date`:** `POST /api/network-contacts` sets today plus ten
working days if nothing is specified. The import deliberately does not: after an import with hundreds of rows, all of them would be
due on the same day as an action under follow-ups. The counter-test (automation built in) turns four cases red.

**Plan** (`_planen`, writes nothing): For each data row, the values (`_zeilenwerte`), the display
(`_anzeige`, "A · B", at most 120 characters) and the required-value check (`_pflicht_fehler`) are created: the `slug_parts`
of a required value must not be empty, otherwise `fehler`; a value consisting only of characters outside
`a-z0-9` (for instance Cyrillic) gets a message of its own, because `slug_parts` would turn it into an empty
key. Completely empty rows are silently dropped. The key is checked against ALL rows of the table
(including tombstones) and against the rows before it in the same file: no entry results in `neu` (new), a
tombstone in `geloescht` (deleted; skipped, never revived), an existing entry in `ergaenzt` (supplemented) if at least
one empty field gets a file value (`_luecken`, `felder_ergaenzt` names them), otherwise `unveraendert` (unchanged).
A filled value is never overwritten, an empty cell deletes nothing. A second row with the same
key acts on the result of the first (message "Duplicate in the file, see row N") and can only
fill its empty fields. The default values for new entries come only at the end, so that a later
row for the same entry can still supply the value.

**Career-page rule** (`Feld.nicht_gleich`): The Excel export writes the website into the column "Karriereseite" (career page)
as a substitute (`karriere_url or website`). The target-company sweep loads a set
`karriere_url` directly (cache) and then no longer searches for the career link on the website; it would
read the home page as the career page. A career page that equals the website of the existing company
(`_url_vergleich`: without scheme, without "www.", without trailing slash) therefore does not supplement `karriere_url`.
A NEW company keeps both values if the file carries both columns. The counter-test without the
rule turns two cases red.

**Writing** (`importieren`):
1. Read and first planning, read-only. If there is no job (`neu + ergaenzt == 0`), the call ends
   here with `sicherung: null`: no backup, no write access.
2. Backup via `app.sicherung.anlegen()`, i.e. in the series of automatic backups under
   `data/backups/auto`. The database comes from the engine path of the session
   (`session.get_bind().engine.url.database`), the data folder from `daten_dir`; this way a test backs up exactly
   the database it writes to. `SicherungLaeuft` results in 409, any other error in 500; in both cases
   nothing is changed.
3. `BEGIN IMMEDIATE` (`_schreibtransaktion_beginnen`): write lock from here. If the database is busy
   (SQLite reports "locked" or "busy" after the wait of 15 seconds from `db.CONNECT_ARGS`), this results in
   409 instead of a hanging import. If the connection is already in a transaction, it stays that way.
4. `session.expire_all()` and second planning under the lock, so that the state written is
   the state planned: the backup lies between the first planning and the writing, and in that time another
   process may have filled the same field. The response counts from this second planning.
5. `_schreiben`: a supplement sets only the planned fields and `updated_at`. New entries are created
   with `dedup_key` via `flush_or_duplicate` (SAVEPOINT per row, `session.add` only in the callback, see its
   docstring). If a job fails because of a duplicate, because a concurrent import has
   created the same key, it acts like a supplement (as in the earlier one-off migration), and the counters of the response
   are rebooked (`neu` minus one, `ergaenzt`, `unveraendert` or `geloescht` plus one). Then
   `session.commit()`.
6. Any other error while writing results in `rollback()` and 500. A log line `[netzwerk-import]
   <liste>: <n> neu, <n> ergänzt, Sicherung <Datei>` goes to the server's standard output.

**Why `BEGIN IMMEDIATE` explicitly:** `flush_or_duplicate` alone is not atomic under pysqlite.
pysqlite opens a transaction itself only before INSERT, UPDATE and DELETE, not before a SAVEPOINT. The
SAVEPOINT starts one, and its RELEASE closes it again with a COMMIT. Without the explicit
transaction, after an error in the middle of writing some of the rows would remain: if the import fails
at the third row, the first two would be in the database (demonstrated in
`test_flush_or_duplicate_allein_ist_unter_pysqlite_nicht_atomar`; the behaviour in the import is tested by
`test_eine_transaktion_fehler_mitten_im_schreiben_schreibt_nichts`). If the first test ever fails, the
behaviour of Python or SQLAlchemy has changed and the safeguard is obsolete. Starting with a
write lock also closes the gap between planning and writing. Counter-tests: without
`BEGIN IMMEDIATE` two cases turn red, without `expire_all()` one.

**Interface** (`frontend/src/components/NetzwerkImport.tsx`): Two building blocks, because the button belongs in the
header row of the tab and the panel opens below it, as with `TargetNew` and `NcNew`:
`NetzwerkImportKnopf` (secondary button with a border instead of a cyan fill, to the left of the create button) and the panel
`NetzwerkImport` (props `liste`, `onImportiert`, `onClose`). `pages/Netzwerk.tsx` holds only the on/off switch
(`showImport`; 12 lines inserted and none changed, so that merging with the changes of
P2-61 to the same file stayed easy): in `Netzwerk` for the tabs target companies and headhunters, with an
effect that closes the panel when the tab is switched, and in `NetzwerkKontakte` for the third. `onImportiert`
reloads the page's list (`loadRows` or `load`). Sequence in the panel: choose file, `POST …/vorschau`,
preview (recognised columns as chips, "column → field" if the heading differs; unused
columns; five counters; notes; table of the rows with errors and deleted rows first), "Import (12
new, 3 to supplement)" (disabled when `neu + ergaenzt == 0`), `POST …` with the same file, result line "✓ 12
created, 3 supplemented. Backed up beforehand: <file>" and "Close". Uploads use `fetch` and `FormData`,
not `api()`: that sets the JSON header, which multipart cannot tolerate (pattern `Profil.tsx`). Three
safeguards: against double-click (`schreibt`), against the response of an outdated preview (`lauf`)
and against reporting after a tab switch in the middle of the import (`aktiv`; the reload would otherwise hang on the tab
of that time and write its rows into the new one). A `TypeError` from `fetch` means that the server
is not responding or that the file was changed after selection (typical: corrected in Excel); the
error text says both. Accessibility: an always-present live region (`role="status"`) announces "File
is being checked", "Preview ready …" and the result, the table has a caption, and the badges
always carry plain text (colour is never the only carrier; errors: red with white, 4.58:1). The
display names in "Supplemented: …" come from the labels of the recognised columns (`spalten.erkannt`); the list
`FELD_NAMEN` in the component catches only fields that the server derives rather than reads from a column
(for the LinkedIn export, channel and notes); it is the only second list of the import fields. Types in
`api.ts`: `NetzwerkImportVorschau`, `NetzwerkImportErgebnis`, plus `NetzwerkImportAnzahl`,
`NetzwerkImportZeile`, `NetzwerkImportListe` and `NetzwerkImportAktion`.

**Tests** (`tests/test_netzwerk_import.py`, 341 cases, everything under `tmp_path` and in a test database;
the tests create Excel files with `openpyxl`): column configuration and synonyms, CSV (delimiters, encodings,
line endings, row numbers), read errors, XLSX (sheet selection, dates, wrong dimension, zip bomb),
LinkedIn, values, no automatic `next_action_date`, the rules against the database,
preview/backup/transaction, templates, the round trip via the real Excel export
(`pipeline.export_excel`; reading it back yields only "unchanged" and no backup, into an empty
installation it creates everything), router and the package rules for all customer texts of the module (formal "you" form,
no dashes, no author's name, email addresses only under `beispiel.de`). A separate test against the REAL app checks the integration in `main.py`
(`test_router_ist_in_der_app_eingebunden`): the `client` fixture
of the file builds its own app with only this router and overrides the one of the same name from `conftest.py`, so a
test using it would not notice a missing `include_router`. Counter-tests (each briefly reverted, then red
cases): without tombstone rule 9, with overwriting 7, with automatic due date 4, without `BEGIN
IMMEDIATE` 2, without `expire_all()` 1, without career-page rule 2.

**Side findings** (both fixed in the same commit):
- **Excel export without jobs:** `funnel_kpi()` returns `groesster_verlust = None` when there are no jobs. The
  funnel sheet caught this, but the compact funnel on the dashboard sheet (`_dashboard_funnel_block`) still
  accessed it, and the data validation of the CV dropdown yielded "M2:M1". The whole export aborted,
  on a fresh installation as well as after "Remove sample data" (P2-59), and with it also the step
  "Refresh views" of the daily run. It was noticed while building the round-trip test; on the trial server, export, digest, search index and favicons
  then ran without errors after "Remove sample data". Test:
  `test_export_laeuft_auch_ohne_stellen` (`tests/test_export_excel_funnel.py`).
- **Key of the sample contact:** The network contact of the sample data carried
  `dedup_key = "beispiel|paul-paket"` instead of the app key `slug_parts(Name, Unternehmen)`. A
  file import (round trip via the export) or creating it by hand therefore created the same contact a
  second time. Now the app key applies (`beispieldaten._zeilen_anlegen`); removing the
  sample data recognises the contact by name anyway (`_beispiel_bedingungen`). Test:
  `test_beispiel_kontakt_traegt_den_schluessel_der_app` (`tests/test_beispieldaten.py`).

**Consequences for the sweeps:** New rows have `last_career_check = NULL`. The target-company sweep and the
headhunter search select only entries with a website and sort NULL first (12 and 15 entries per run,
see the two `SKILL.md` files, section "Selection (rotation)"). A large import with websites
therefore moves to the front of the rotation and lengthens the cycle accordingly.

Deliberately not part of the import: overwriting existing values, deleting, reviving deleted
entries and fuzzy matching of names.

### Stored file paths: only server and skills, moved only from the allowlist (P2-56)

The server and the skills write paths in the database. A client may set exactly one:
`prep_path` on the interview (`PATCH /api/interviews/{id}`), and only to an existing briefing in
`data/interview_prep/` (`.html`), stored in the canonical form
`data/interview_prep/<datei>.html`; anything else is 422, `null` empties the field. The interface
never sends the field; interview-vorbereiten registers briefings via
`pipeline.interview.register`. Anyone who moves stored paths checks them themselves:
`_in_papierkorb` (all delete endpoints) moves only files from the allowlist
`_ARTEFAKT_ORDNER`, with the same check as `/api/artifact` (`_erlaubter_artefakt`); any other
path counts as `dateien_fehlgeschlagen`, and the file stays where it is. `cv_export` accepts drafts only
from `data/cv_basis/entwuerfe`, `data/tmp`, `outputs/cv_entwuerfe` and `outputs/cv`, cover letters only
from `outputs/anschreiben` and `data/tmp`, and clears away an old PDF only from the target folder; a
base CV is never a source. `cleanup._in_papierkorb` stays within `data/` and `outputs/` (it cannot be tighter,
because the rotation also puts old backups into the bin). Until P2-56, two
calls were enough, setting `prep_path` to `data/bewerbung.sqlite` and deleting the briefing, to push the live DB into
the bin; via the same value the search index took up any readable file.
**Anyone who opens a path field to clients checks it with `_erlaubter_artefakt` against the matching
folder.** A guard in `tests/test_pfadfelder_sicherheit.py` reports every other path field from the
request, a second one every new write, move or delete location in `main.py` and the
routers.

### Design from one source (P2-72)

Colours, fonts, icon and display name of the brand are in **one design file**. Interface,
new reports, digest, coach site, Excel export and the documentation view take their brand values only from
there. With the default, everything looks as it did before the rebuild.

**Two locations, one rule.** The default lies in the package: `assets/design/standard.json` with
`icon-32.png` and `icon-180.png` beside it. An override lies under `data/design/`
(`design.json`, plus own icons). `data/` is locked for every update, so the override
survives it. Reading is done role by role: whatever the override does not name, or names invalidly, comes
from the default. There is no interface for changing it; the file is created by hand.

**Roles instead of colour values** (`pipeline/design.py`): `marke`, `auf_marke`, `aktion`, `aktion_hover`,
`auf_aktion`, `stahl`, `flaeche`, `karte`, `rahmen`, `spur`, `text`, `text_gedaempft`, `trenner`,
plus the fonts `ueberschrift` and `text` (Inter, Montserrat or system font), `produktname`
and the icons. **The product name is fixed:** only the default names it; an override cannot
change it (otherwise the default applies, with a warning). Colours only as `#RRGGBB`. A pair of surface and font (`marke`/`auf_marke`,
`aktion`/`auf_aktion`, `flaeche`/`text`, `karte`/`text`) applies only together and only with a
contrast of at least 4.5:1, otherwise the default applies for that pair. **An invalid design never makes
the BMS unusable:** every rejection is a warning in the log and in the information, never an error.

```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.design zeigen
```
shows the design in force, the source of each entry, the contrasts of the pairs and all warnings.

**Meaning is not design.** Status, score, situation, tier, scenario, area, plan, the
header colours of the Advisory Board and the font on these surfaces are fixed values, even where they happen to equal the
action or brand colour. "Applied" stays cyan if a design brings orange as the action colour.
In Python, status and score are in **one** table (`pipeline/zustandsfarben.py`);
`tests/test_zustandsfarben.py` reads `frontend/src/components/ui.tsx` and keeps the two identical. One
named exception: digest and coach site write white font on score 5
(`digest.SCORE_SCHRIFT_AUSNAHME`), as before the rebuild.

**Who reads the source, and how:**

| Output | Route |
|---|---|
| Interface | `frontend/index.html` loads `GET /api/design.css` before its own CSS. Tailwind takes the roles as `rgb(var(--marke) / <alpha-value>)`; the class names (`bg-brand-cyan` and the others) have remained. Another design needs no rebuild; reloading the page is enough. Icon: `GET /api/design/icon/32` and `/180`. |
| Reports of the theme family (company fit, interview evaluation, posting copy, clean-up report, Advisory Board) | `pipeline/bericht_stil.py::bericht_css(zusatz)` returns the whole CSS with the spelled-out values of the design in force. Each renderer passes in only its own rules as an addition. |
| Reports that a model writes (match, ATS scan, briefing, rejection analysis, offer comparison) | The skill writes HTML with classes and without `<style>`. Then `python -m pipeline.bericht_stil einsetzen <Datei>` inserts style and icon (see below). |
| Digest, coach site, Excel | read the design at every call (`design.laden()`), state colours from the table. |
| Documentation | The app's documentation view renders with the design in force. `pipeline/docs_render.py` always renders the shipped `docs/*.html` with the default, so that the comparison test does not depend on an installation's design. |

The design is read everywhere **at run time, in the call**, never held in a module constant at import.
`design.laden()` remembers the result and detects changed files, so a new design file takes effect
without a restart. Guards in `tests/test_design_ausgaben.py` and `tests/test_bericht_stil.py` fail
if a module holds on to the design or icon at import again.

**`bericht_stil einsetzen`** replaces the `<style>` block in a finished report with
`bericht_css()` and inserts the icon. Otherwise the command changes nothing in the document; applied twice is
the same as once. It belongs to the creation of a report. Exit 0 = fine, 2 = file unusable, 3 = classes without
a rule (the file is written nonetheless).

```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.bericht_stil einsetzen ../data/company_fit/<Datei>.html
```
`assets/report_theme_bms.html` is the template for structure and classes. Its `<style>` block is generated from
`bericht_css()` with the default (`python -m pipeline.bericht_stil vorlage`); a test keeps
the two identical. No skill carries a colour value or a piece of CSS any more
(`tests/test_skills_ohne_css.py`).

**Reports remain self-contained and existing items remain as they are.** The values are spelled out
in the `<style>` of every new report; no report refers to a file or address. Reports already created
are not recoloured. `app/favicon.py` recognises two icons as valid, that of the default and
that of the design in force. Only an icon that is neither of the two is replaced. The footer text
"Bewerbungs-Mgmt · erzeugt am …" (created on) is fixed wording, because the duplicate detection recognises reports by it.

**Limits:** On the brand surface in the sidebar, documentation header and Excel header row, fixed
light values still apply. With a light brand colour they are hard to read. The reports already solve this
(`bericht_stil.schrift_auf_marke`: white as long as legible, otherwise `auf_marke`). Cards in the interface
remain white; the role `karte` has an effect only in the reports. The full list is in
the build spec P2-72 under "Honest limits".

### Third-party licences (P2-77)

The Legal → "Third-party licences" page is generated, not maintained by hand. The **source**
is the lock files: `backend/requirements-lock.txt` (Python) and `frontend/package-lock.json` (npm).
`backend/pyproject.toml` and `frontend/package.json` supply only the division into "direct" and
"bundled" (transitive). The generator `pipeline/drittlizenzen.py` writes two files, neither of which is ever changed by hand:

- `frontend/src/rechtliches/drittlizenzen.md`: the overview with package, version and licence identifier, with
  purpose for direct packages. In addition the build tools as a count per licence, as well as the lists of the separately
  installed programs and the connected third-party services.
- `frontend/src/rechtliches/drittlizenzen_texte.txt`: the unchanged wording of all shipped
  licences. Packages with identical text are in one block. Only two adjustments are permitted:
  line endings to LF and no trailing spaces at the end of lines. The page loads the file only on click
  ("Show licence texts") as a chunk of its own; the main bundle stays small.

**Command** (from the project root; the wrapper follows the pattern of `scripts/docs_html.sh`):

```sh
scripts/drittlizenzen.sh              # erzeugt beide Dateien
scripts/drittlizenzen.sh --pruefen    # vergleicht nur, schreibt nichts
```
Exit 0 = generated or up to date, 1 = only with `--pruefen`: at least one file is out of date (the output
names it), 2 = error, the message names the package and next step. The generator reads the
metadata and licence files from the venv and from the build mirror
`~/.bewerbung_mgmt_node/frontend_build/node_modules` (`frontend/build.sh`). If either of the two does not match
the lock file, it aborts with exit 2 and names the command that fixes it. It runs only in development
(`AUSSCHLUESSE` in `pipeline/kundenpaket.py`); the two generated files, in contrast, are mandatory files
of the customer package.

**When:** after every change to a lock file or to `pyproject.toml` or `package.json`, before the
commit. The output is deterministic (no date, no version, no path); two runs produce
byte-identical files.

**Licence identifier, never guessed:** first `License-Expression`, then the field `License` if it contains exactly one
identifier from the allowlist, finally the table `LIZENZ_FESTGELEGT` (identifier plus the first
twelve hex characters of the SHA-256 of the licence wording). If no stage matches or the wording has
changed, the generator aborts and names the text that has to be read.

**What the guard checks:** `tests/test_drittlizenzen.py` runs in CI (`backend` and `backend-windows`)
and needs neither venv metadata nor `node_modules`. It compares the contents of the page (package lines
of the overview, `Gilt für` lines of the texts) with the lock files, and checks every identifier against the allowlist
and the form of both files (UTF-8, LF only, exactly one line ending at the end). It turns red as soon as a
lock file changes and the page was not regenerated, or a licence outside the allowlist
appears.

**What it does not check:** the wording. Only `--pruefen` does that, and it runs only locally (it needs the installed environment), not in CI. If
a package changes its licence text at the same version, it goes unnoticed; published versions on PyPI
and npm are immutable, so the risk is small. Also open: the texts come from a
macOS installation; packages for Windows or Linux may carry other licence files. "Direct" and
"bundled" follow `pyproject.toml` and `package.json`, not the actual imports.

**Maintenance by hand** (all in `pipeline/drittlizenzen.py`):

- `ZWECK`: a short purpose per direct package. A new direct package without an entry makes the
  generator abort with exit 2; the message names the package.
- `LIZENZ_FESTGELEGT`: only for packages whose metadata name no unambiguous identifier (currently
  google-auth, google-auth-oauthlib, pyasn1_modules). Read the licence text in `*.dist-info`, determine the identifier,
  then enter identifier and hash. Do not adopt it without looking.
- `PROGRAMME` and `DIENSTE`: the lists of separately installed programs and connected
  services. If a service connection changes, `datenschutz.md` also needs to be reviewed.

**The allowlist is a decision of the project lead** (16.10.2026): MIT, MIT-0, ISC, BSD-2-Clause, BSD-3-Clause,
Apache-2.0, PSF-2.0, MPL-2.0 (certifi) and OFL-1.1, for build tools only additionally CC-BY-4.0. In an
expression, brackets group, and `AND` binds more strongly than `OR`: `A OR B` is permitted if one side is
permitted, `A AND B` only if both are. Unknown components (`WITH`, `+`) count as not permitted. A new licence turns CI red, and the project lead decides whether it goes on the list.
Do not extend the list without him.

**Package check:** The wording contains authors' addresses and company names from the copyright lines and
must not be altered. A path-bound exception therefore applies to `drittlizenzen_texte.txt`
(`_FREMDER_WORTLAUT`, see `docs/RELEASE.md`). Build tools appear in the overview without wording.
The page stays under the notice "DRAFT VERSION" (ENTWURFSFASSUNG) and is not legal advice.

### Report self-check (`pipeline/report_check.py`, 23.07.2026)

The generated HTML reports (ATS scan, match, company fit, Advisory Board check, transcript report …)
are **self-contained files**: `assets/report_theme_bms.html` is not linked, so its
CSS is copied into the `<style>` block of every report. If an LLM run shortens the CSS in the process, the
markup stays correct, but the presentation breaks **silently** — this is exactly how an ATS scan lost
its green/red keyword chips on 23.07. (`class="chip pos"` 9 times in the markup, `.chip.pos` missing from the
`<style>`); it was noticed only in the browser.

The check is the countermeasure: deterministic, free, without prior knowledge of report types.

**The same pattern with the app icon (P2-44, 23.09.2026):** The template carries the icon as a 3.3 KB
data URI, which every report copies along. In 37 of 2,701 files this string was
mangled or replaced by a foreign icon — and stayed that way, because `app/favicon.py` left every file
alone that carried *any* icon. Since then the app icon wins: a foreign icon link is
replaced, multiple ones are reduced to one (`apple-touch-icon` remains untouched). All three levels — generator, `/api/artifact` on delivery and `pipeline.favicon_nachruesten`
in the daily run — therefore also heal a wrong icon, not just a missing one.
It compares **used class combinations against existing CSS rules** and reports every
class that remains without effect. Since P2-72 no model writes CSS any more: the skill writes the
report without `<style>`, `bericht_stil einsetzen` inserts the complete CSS, and the check runs
directly afterwards. Both steps appear as one line in all six skills whose reports a model
writes (`job-deepdive`, `cv-match`, `cv-erstellen`, `interview-vorbereiten`, `absagen-analyse`,
`angebot-vergleich`). If either of the two reports a class without a rule, the model replaces the class
with one from the template.

```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.report_check ../data/company_fit/*.html
```
Exit code 0 = clean, 1 = at least one rule is missing. Repair is cheap (`bericht_stil
einsetzen` inserts the complete CSS); an expensive re-run of the skill is never necessary for this. On the first run over
the whole stock (289 reports) it found, besides this case, two old transcript reports with
ineffective `.signal`/`.amber` classes; since then the stock has been completely green.

⚠️ Two deliberate exclusions, otherwise false alarms arise: JS template literals
(`class="${badgeClass(...)}"` in company-fit reports) and foreign markup in the job posting snapshots
(`data/job_postings/` contains the copied original HTML including the company site's Tailwind classes)
are skipped.

### Coach site: read-only mirror for an external viewer (Phase 81/82)

Optional, password-protected static export of the application status for an external coach —
rendered deterministically from the DB (`pipeline/coach_export.py`, no LLM, zero cost), uploaded via an
SFTP mirror (`scripts/coach_deploy.sh`, lftp). **Allowlist rather than blocklist principle:** The
exporter does not read the blocked fields (salary, notes & history, Advisory Board checks, `verify_note` internals,
transcripts/debriefs/briefings, CVs/cover letters, ATS scans, network/contacts, budget, emails)
from the DB in the first place — backed by tests in `tests/test_coach_export_sperrliste.py`. Visible are
overview KPIs, the daily digest in a version without emails, open actions and history notes
(P2-79), jobs in two sections "Active applications" and "Screening & review" (each
with company fit, match and posting snapshot without the internal capture context) as well as rejections
with reasons for rejection and the lost-order analysis including report date.

Since Phase 82 the function is **configurable per installation under Settings → Coach site**
(address, SFTP access, server-path automation, coach login) instead of being hard-wired to a
single installation as in Phase 81: `pipeline/coach_settings.py` stores
`~/.bewerbung_mgmt_secrets/coach_settings.json` (600/700) and automatically migrates an older, purely
terminal-based `coach_sftp.env` without changing it (rollback path remains
available). The coach login uses bcrypt (prefix normalised to `$2y$`, Apache/APR-
compatible) — the plain-text password is stored nowhere. Triggered by: the button "Update coach site
now" (Settings) and automatically as the last, non-fatal link of the daily run —
without a complete configuration or with the switch turned off, the step ends green (exit 0),
and the daily run never turns red because of it. Details: `docs/COACH_SITE.md`.

### Four languages

- **Interface and AI output:** `de` or `en`, setting in `sucheinstellung.sprache` (`app/sprache.py`, `frontend/src/i18n`).
- **Application:** CV and cover letter follow the posting (`pipeline/bewerbungssprache.py`).
- **Terminal:** Messages follow the operating system, independently of the app: German on a German system, otherwise English. `BMS_TERMINAL_SPRACHE` (`de`, `en`) takes precedence. Sources: `app/terminal.py` with `texte/en_terminal.json` for the server, separate tables in `scripts/bms_update.py` and `scripts/bms_wiederherstellen.py`, branches in the `.command` and `.bat` files.
- **Machine values** in the database, skills and personas stay German.

### Tests & CI (`backend/tests/`, `.github/workflows/ci.yml`, Phase 57)

Currently **more than 2,000 pytest tests** (Phase 57 started with 36) run isolated from the live DB: `conftest.py`
sets `BMS_DATA_DIR` to a fresh `tempfile.mkdtemp()` directory at the very top of
module level — before any import of `app.*`/`pipeline.*`. The reason is an import-time trap:
`app/db.py` binds `DATA_DIR`/`DB_PATH` at the very first module import; if any
test file imported an app module at module level before the env variable is set,
the whole suite would irreversibly bind to `data/bewerbung.sqlite` (Python caches modules,
a later re-import no longer helps). All test files therefore import app modules
only locally within functions, in fixtures/tests, never at module level — and a safety net
in `conftest.py` aborts the run hard if `DB_PATH` should nevertheless lie outside the tmp directory. For the same reason fixtures (`seed`) are deliberately purely synthetic (`Musterfirma GmbH`,
`Test AG`, invented titles) — never rows copied from the real DB, otherwise the repo would smuggle personal data in via
the tests (I2 from Phase 56 applies to test data just as much).

Phase 79 closed the same gap for **artefact paths**: several modules (including `dedup_text`,
`search_index`, `beirat_engine`) still resolved `data/…` paths against the project root,
while the writers already wrote against `DATA_DIR` — identical in production, but under
test isolation divergent (older tests were green there only because they benefited from the same leak).
Since then every resolution of a `data/` path goes through a shared function
in `app/db.py` (which follows `BMS_DATA_DIR`); `outputs/` paths are deliberately still
resolved against the project root — the user's documents are not meant to be isolated.

CI (four jobs on every push to `main` and every pull request: `backend`, `backend-windows`,
`frontend`, `secret-scan`) runs this suite on Python 3.12, on Linux and on Windows.
The pin deliberately follows the local venv reality, not the other way round. Until
Phase 57 that was Python 3.9 (EOL since October 2025); Phase 58 switched the venv at the same path
with an identical lock (zero deviations) to Python 3.12.13 from Homebrew — the
EOL debt is thereby settled. CI also builds the frontend against Node 24. PDF rendering
(LibreOffice/`soffice`) remains an open test gap: covered neither locally nor in CI
by `skipif` tests, not a silent CI skip but simply untested — a candidate
for a later phase.

**`backend-windows`** (since Phase 71D) runs the same suite on `windows-latest`
(`working-directory: backend`, `python -m pytest tests -q`); `release.yml` calls `ci.yml` via
`workflow_call`, so without a green Windows run no release package is created. Tests that require POSIX
carry `@pytest.mark.skipif(os.name == "nt", …)` and are skipped there:
`test_prozess_tracking.py` (whole module: real `sleep` process groups, `ps`/`os.killpg`),
`test_beirat_stderr_deadlock.py` (whole module: stub via `chmod +x`, starts without an interpreter via
the shebang line), one test in `test_cv_export.py` (timeout kill via `os.killpg`), two
permission asserts in `test_log_pfade.py` (`st_mode == 0o600/0o700`) and one test in
`test_tmp_aufraeumen.py` (symlinks need special rights under Windows). No LibreOffice is installed on the Windows runner,
so the Windows path of PDF generation never ran there. The
customer's view of these limits is in `docs/SETUP-WINDOWS.md` (known limits, support matrix),
the developer route under Windows in `docs/INSTALLATION.md` part 1. `.gitattributes` keeps
text files on LF (otherwise `test_docs_html.py` would fail on Windows runners) and `.bat`/`.cmd`
on CRLF.

**Running tests locally.** `scripts/test.sh` calls pytest in the venv against `backend/tests/` (install once with
`~/.bewerbung_mgmt_venv/bin/pip install -r backend/requirements-dev.txt`). Isolation from the
live DB works via `BMS_DATA_DIR`: `conftest.py` sets it itself to a fresh tmp directory before
any app module is imported. `data/bewerbung.sqlite` stays untouched; the server on port 8000
can keep running in parallel.

**Secret-guard hook** (once per clone): `scripts/install_hooks.sh` writes a wrapper to
`$(git rev-parse --git-dir)/hooks/pre-commit` (hooks are not versioned; this script is the
reproducible way to get there) which, before every commit, checks the staged changes against a few token patterns
(<0.1 s) and blocks on a hit. Deliberate exception: `git commit --no-verify`.

**Rebuilding the Python environment.** If the venv breaks (typical symptom after a `brew upgrade`/`cleanup` of
`python@3.12`: `bad interpreter`), rebuilding from the lock helps:
```sh
rm -rf ~/.bewerbung_mgmt_venv
/opt/homebrew/bin/python3.12 -m venv ~/.bewerbung_mgmt_venv
~/.bewerbung_mgmt_venv/bin/pip install -r backend/requirements-lock.txt -r backend/requirements-dev.txt
```

The `secret-scan` job replaces GitHub Secret Scanning, which is not available on this repo
(422, plan limitation), with a two-stage chain: locally a pre-commit hook
(`scripts/precommit_secret_scan.sh`, plain built-in tools git+grep, checks only staged changes,
<0.1 s), in CI `gitleaks` over the full commit history (`.gitleaks.toml`). Important for
interpreting a green run: the `secret-scan` job on a push checks only whether anything was found in the
NEW commit — with this trigger the action scans only the
newly pushed commits. The scan of the ENTIRE history runs separately via the
`workflow_dispatch` trigger (`gh workflow run ci.yml`). Both variants have been verified green.

---

## 9. API overview (140 endpoints)

Selected categories (all under `/api/…`; the backend also serves the frontend; no
CORS release for foreign websites, write access only from the own origin, responses only under
released names, see §8, P2-55 and P2-57). Counted are the combinations of method and path
under `/api` in the app's OpenAPI schema (as of P2-72, with `/api/doku*`, `/api/design*`, `/api/beispieldaten*`,
`/api/netzwerk-import*` and `/api/profil/identitaet`; the earlier figure of 121 had only been updated by hand and was already seven below
the actual figure of 128 before P2-59, P2-59 added four endpoints, P2-62
three, P2-69 two, P2-72 three for the design):

- **Jobs:** `GET/POST /jobs`, `GET/PATCH/DELETE /jobs/{id}` (soft delete + bin),
  `/jobs/{id}/approve|discard`, `/jobs/{id}/interviews|transcripts|transcripts/upload|files|chat|log`,
  `DELETE /files/virtual/{quelle}/{pk}/{slot}` (generated artefacts), `DELETE /companies/{id}`
- **Companies & contacts:** `GET /companies`, `PATCH /companies/{id}`, `GET /contacts`
- **Design (P2-72):** `GET /design` (design in force with source and warnings), `GET /design.css`
  (the roles as CSS variables for the interface), `GET /design/icon/{groesse}` (`32` or `180`).
  All three are pure read accesses without a lock (see §8 "Design from one source")
- **Network:** `GET/POST/PATCH/DELETE /target-companies|headhunters|network-contacts`,
  `POST /…/{id}/restore` + `GET /netzwerk/papierkorb` (bin),
  `GET /network-check`, `POST /initiativ`
- **Network import (P2-62):** `GET /netzwerk-import/{liste}/vorlage?format=csv|xlsx` (template for
  download), `POST /netzwerk-import/{liste}/vorschau` (field `datei`, writes nothing) and
  `POST /netzwerk-import/{liste}` (field `datei`, first backup, then one transaction); `{liste}` is
  `zielfirmen`, `headhunter` or `kontakte`, otherwise 404. Errors 400, 409, 413, 422 and 500 (see §8
  "Network import")
- **Email:** `GET /inbox|emails`, `GET /emails/{id}/body`, `PATCH /emails/{id}`, `POST /emails/{id}/assign` (assign/detach job),
  `POST /emails/{id}/archive|restore` (P2-52, archive for emails without a job)
- **Search:** `GET /search`, `GET /search/meta`, `POST /search/rebuild`
- **Tasks (headless):** `GET/POST /tasks`, `GET /tasks/{id}`, `/tasks/{id}/cancel`, `/task-kinds`,
  `/agent-status`
- **Advisory Board:** `GET /beirat/mitglieder|debatten|debatten/{id}`, `POST /beirat/debatten` +
  `/{id}/stop`, `GET /beirat/debatten/{id}/stream` (SSE live), `POST /beirat/stellen-check` (job check), `GET/POST /beirat/keys`
  (local in `~/.bewerbung_beirat/`, only masked status via the API)
- **Budget:** `GET /budget`, `/budget/check/{provider}`, `PATCH /budget/limits/{provider}`,
  `POST /budget/sync`
- **Views:** `GET /dashboard|followups|upcoming-interviews|review|runs|digest`
  (`digest` as HTML in the sandbox, P2-58), `GET /export/excel|export/outreach`
- **Profile (Phase 45):** `GET/PATCH /profil`, `POST/PATCH/DELETE /profil/skills[/{id}]`,
  `POST/PATCH/DELETE /profil/werdegang[/{id}]`, `POST/DELETE /profil/dateien[/{id}]`,
  `POST /profil/import-zip` (LinkedIn data export), `POST /profil/linkedin-einlesen` (text or PDF → headless task), `GET`/`DELETE /profil/linkedin-vorschlag`, `POST /profil/linkedin-vorschlag/uebernehmen`
- **Profile file (P2-69):** `GET/PUT /profil/identitaet` — reads and writes `config/profil.md` via the
  card "Identity and search strategy". The response carries `stand` (SHA-256 of the file content); a PUT with an
  outdated `stand` is 409, a validation error 400. Before overwriting, the old file goes into the bin (see §8 "Profile file")
- **Settings (Phase 49/50, P2-51):** `GET/PATCH /einstellungen` — search area, company size,
  plans A/B/C and AI model choice per function; additionally `umkreis_label`, `modell_optionen`,
  `modell_standard` in both responses, `umbenennung` in the PATCH response on a
  local-area change; every PATCH regenerates the managed block of `config/suchprofile.yaml`.
  Since P2-59 without Fable: `modell_optionen` names only Opus, Sonnet and Haiku, `modelle` shows the
  effective values, and a PATCH with `fable` is 422 (see §8 "AI models")
- **Documentation (P2-59):** `GET /doku` (the documents of this installation as a list of `id`,
  `titel` and `gruppe`), `GET /doku/{name}` (the rendered page as HTML in the sandbox; `name` is
  an identifier or a file name from the catalogue, otherwise 404; see §8 "Documentation page")
- **Sample data (P2-59):** `GET /beispieldaten` (status `keine`/`vorhanden`/`entfernt`, count per
  kind), `POST /beispieldaten/entfernen` (first backup, then delete; 409 if there is nothing to remove,
  a backup is running or a task is working on a sample job, 500 if the
  backup failed; see §8 "Sample data")
- **Version (P2-51):** `GET /version` — installation type (paket/git/unbekannt), version or
  development state, commit/date, last update, CHANGELOG section of the installed version;
  never a 500 (every internal error yields null fields)
- **Latest version (P2-82):** `GET /version/neueste` — on request, asks GitHub releases for
  the latest version and compares it with the installed one; always answers 200, errors appear as
  customer text in the field `fehler` (see §8 "Update information from GitHub releases"). The licence endpoints
  `/lizenz` and the 402 response have not existed since P2-82
- **Backup (P2-52):** `GET /sicherung` (status: last backup, count, warning), `POST
  /sicherung` ("Back up now", also runs when automatic backup is switched off), `PATCH
  /sicherung/einstellungen` (retention, on/off)
- **Coach site settings (Phase 82):** `GET/PUT /settings/coach`, `POST /settings/coach/test`
  (connection test against form values that may not yet be saved), `POST
  /settings/coach/serverpfad` (automatic determination of the `.htpasswd`, only in an empty target directory)
- **CV draft (Phase 46/48):** `GET/PATCH /cv-versions/{id}/entwurf` (editing checkpoint),
  cover letter text at the application endpoint
- **Artefacts:** `GET /artifact` (delivers only documents from the allowlist `_ARTEFAKT_ORDNER`,
  otherwise 403; see §8 "File delivery", P2-54; HTML for display in the sandbox, see §8 "Reports
  in the sandbox", P2-58)

---

## 10. Development history & roadmap

The system has grown in phases. Rough chronology:

| Phases | Content | Status |
|---|---|---|
| 0–5 | Basic framework, DB, first skills (job search, email check, deep dive, daily run) | ✅ |
| 6 | Follow-up tracking & interactive dashboard | ✅ |
| 7 | Interviews, call preparation & transcripts | ✅ (Hedy deferred) |
| 8 | Community backlog + agents from the web app (Task Centre, chains) | ✅ |
| 9 / 17 | Perplexity as a second search engine | ⏸ deferred (NO-GO after measurement), removed with P2-78 |
| 10–14 | Budget control · files on the job · CV PDF export · email job search · **four-eyes principle** | ✅ |
| 15 | Auto-apply | ⛔ rejected |
| 16 | Job detail workflow layout | ✅ |
| 18–25 | Posting snapshot · key-facts edit · source conflicts · network contacts · search-run display · notes history · **full-text search** | ✅ |
| 26–28 | Headhunter website + career-page sweeps · inbox full text + AI reply · network deletion + AI chat | ✅ |
| **29** | **Nejo portal · index status always visible · favicon** (meanwhile the v2 icon) | ✅ |
| **30** | Uniform report style (template) · internal naming convention · **transcript report + file upload** | ✅ |
| **31** | Migration of existing documents to new names/style | ✅ executed |
| **32** | **Deletion with confirmation**: jobs (soft-delete tombstone) · companies · generated files — central bin, orphan-free | ✅ |
| **33** | System clean-up command (`scan` → `apply` → `leeren`: orphans, rotation, final emptying of the bin) | ✅ |
| **34** | CV match **before/after comparison** back · artefacts in the same tab · search criterion **minimum company size 100+ employees** | ✅ |
| **35** | Uniform **report header** (debrief pattern for all templates) · ATS scan: keyword comparison + score derivation back · footer without "Daube.Tech" | ✅ |
| **36** | **Unassigned emails** visible in the inbox (badge/filter "No job") · **assign/detach** manually to a job · email-check never again discards relevant emails | ✅ |
| **37** | **Arbeitsagentur as a portal** (German title synonyms, own deterministic search step) · daily digest in the same tab | ✅ |
| **39** | **Application Advisory Board**: 7 personas + charter integrated (interactive via `/beirat-basis` AND web page `/beirat`); Brandt orchestrates autonomously, live debate via SSE, Agent SDK headless (keyless via subscription or entered key), OpenAI optional | ✅ built directly |
| **40** | **Advisory Board job check in the job workflow**: nav entry removed, new step "2 · Check job (Advisory Board)" in the documents card (charter vote of all 7, deterministic decision, HTML dashboard type BeiratsCheck (`Beirat` since P2-63), JobFile registration with traffic-light note) | ✅ |
| **41** | New job status **"Rejected by board"** (terminal, self-sorted out after the Advisory Board check — separate from "No match"/"Rejected"; normalisation exception, own badge colour, one-click suggestion at the 🔴 check, skill delimitations) | ✅ |
| **42** | **Task Centre as the only activity log**: Advisory Board engine writes its own AgentTask rows (cost per turn summed, log in viewer format, cancel switch, guardrails count too, backfill of the existing stock) — architecture principle laid down | ✅ |
| **43** | **Status distribution bar** on the jobs page (proportional, clickable segments; colours re-derived by direct fix from the Daube.Tech style guide — cyan→navy ladder, one canonical map for bar AND pipeline) · pipeline headline names "Rejected by board" | ✅ |
| **38** | **Posting snapshot already at capture** (base snapshot from the four-eyes fetch at ingest, firma-pruefen later replaces it with the full version; backfill over the existing stock) | ✅ |
| **44** | **Re-posting detection** in dedup: two-stage from title word Jaccard (mandatory pre-filter) + text score, calibrated against the real stock | ✅ |
| **45** | **Profile page**: positioning · skills as chips by area · career history · reference files; LinkedIn import in two ways (data export ZIP deterministic, URL best effort/honest at the login wall), both additive & non-destructive; derivation `config/profil_struktur.md` for CV/cover-letter skills | ✅ (A–D) |
| **46** | **CV process with editing checkpoint** (`cv-anpassen` → `cv-match` + `cv-erstellen`: edit the draft first, then Word/PDF **and afterwards** ATS scan on the final document) · **document engine**: page-break protection + footer "Name · Page X of Y" for all generated CVs | ✅ (A+B) |
| **47** | LinkedIn export note corrected ("Download larger data archive" instead of the quick selection "Profile") · **automatic skill sorting** (`skills-sortieren` runs after every ZIP import, only moves, invents nothing) | ✅ (A+B) |
| **48** | **Inline text window** for CV content (one continuous text instead of many individual fields, full bullet freedom, headings locked → ATS stays intact) and **new cover-letter editor** (previously only the generated file; "Load text from existing .docx" for the existing stock) | ✅ (A+B) |
| **49** | **Settings page**: search area (Remote/Germany-wide/city+radius) & minimum company size · **plans A/B/C** (title/level/industry per plan, order A→B→C, plan C new). The DB is the truth, `config/suchprofile.yaml` the derived view — marker-split writer preserves all hand-maintained technical parameters verbatim, all 9 YAML consumers remain unchanged | ✅ (A+B+C) |
| **50** | **AI model choice per function** (job search · company fit · Advisory Board · CV match · ATS scan · cover letter → Opus 4.8 / Sonnet 5 / Haiku 4.5, default Sonnet) in `sucheinstellung.modelle_json`; takes effect via `agent_runner._argv` (headless task kinds) and `beirat_engine` (all 7 personas) | ✅ (A+B) |
| **51** | Dashboard rebuild: status/match score/portal on the left, **situation per plan A/B/C** on the right (including `norm_plan()` for polluted `plan_ab` values and a real `plan` filter in the job listing) | ✅ (A+B) |
| **52** | Cover-letter editor moved from the narrow sidebar into the **wide centre column** (below the CV editor) + text sync when a new run replaces the cover letter (without discarding unsaved input) | ✅ (A+B) |
| **53** | **Excel export V2 "Application status"** (model: Claudia's tracker cockpit): 8 sheets — dashboard KPIs (identical to `/api/dashboard`) · jobs **grouped by status** (match coloured, ATS, Advisory Board traffic light, source as hyperlink, next step) · sorted out · contacts · network · headhunters · target companies · outreach; colour model V2 from `ui.tsx`, terminal statuses without the old "next step", file name `JJJJ_MM_TT_Bewerbungs-Stand.xlsx` (`JJJJMMTT_…` since P2-63) (inbox sheet dropped) | ✅ |
| — | **Dashboard colour model V2** (style guide v5.0 §18) carried through: semantic status/score/situation tokens instead of the cyan ladder, shared map for bar · funnel · kanban · status pills · network pills; contrasts WCAG-checked (ScoreBadge/status pills needed navy instead of white) | ✅ |
| — | **Cover-letter document** revised: duplicate header removed, place/date right-aligned, closing and name close together, guaranteed **1 page**, Calibri 10.5 pt as in the CV, typographic hierarchy (name 16 pt · subject 12 pt bold); CV footer now language-dependent ("Page X of Y" / "Seite X von Y") | ✅ |
| — | **Report self-check** `pipeline/report_check.py` against the silent CSS drift of generated reports (see section 8) + mandatory step in `cv-erstellen`; entire stock (289 reports) cleaned up | ✅ |
| **55** | **ATS score v2**: score = degree of optimisation instead of a bare keyword coverage rate (formula 60 % keyword optimisation + 25 % title alignment + 15 % format; raw rate x/15 remains visible separately) · **ONE keyword list** (15 terms, fixed categories, classified `abdeckbar` (coverable) true/false with evidence/reason), generated in `cv-match` (`CVVersion.keywords_json`), reused in `cv-erstellen` instead of a second extraction · **one-time feedback loop** for coverable terms that were not worked in. Fallback for old drafts without `keywords_json` (methodology v1, one-time survey in the scan) | ✅ |
| **56** | **Repo structure & Git**: three-level separation (code area versioned · personal content local in `data/`+`outputs/` · Git internals excluded from sync in `.git.nosync/` for iCloud storage) · DB to `data/bewerbung.sqlite` (`BMS_DATA_DIR` override) · documents to `outputs/cv|anschreiben|exports` · docs to `docs/`, report theme to `assets/` · `backup_db.sh` with rotation | ✅ |
| **57** | **Tests & CI**: 36 pytest tests (isolation via a throwaway DB under `BMS_DATA_DIR`, purely synthetic fixtures) · GitHub Actions CI with 3 jobs (backend py3.9 · frontend node24 · secret-scan gitleaks) · pre-commit secret hook from built-in tools · process rule "acceptance requires green CI" (see section 8, "Tests & CI") | ✅ |
| **58** | **Python upgrade 3.9 → 3.12**: venv rebuild at the same path (`~/.bewerbung_mgmt_venv`) on Homebrew Python 3.12.13, identical lock (`requirements-lock.txt`, zero deviations) · CI pin raised to 3.12 · rollback venv `~/.bewerbung_mgmt_venv_py39_backup` retained · PDF smoke test (LibreOffice conversion) really checked under 3.12 for the first time | ✅ |
| **59** | **Dependency update**: backend lock freshly resolved (`fastapi` 0.128.8→0.140.0, `uvicorn`→0.51.0, `sqlmodel`→0.0.39 · `starlette` 0.49→1.3.1 transitive MAJOR · `pytest`→9.1.1 MAJOR, tests green; `pydantic`/SQLAlchemy/`cryptography` unchanged) · 8 never-used `uvicorn[standard]` leftovers removed (uvloop/websockets/watchfiles/httptools/jinja2/python-dotenv/MarkupSafe/exceptiongroup — no code import, `loop="asyncio"/http="h11"` remains hard-set anyway) · production `venv` rebuilt following the README recipe "Rollback & repair" (validated live) · frontend **semver-safe** (`npm update` within existing `^` ranges; React 18 / Vite 5 / Tailwind 3 / TS 5.x deliberately kept, major bumps postponed) | ✅ |
| **61** | **Email assignment repaired (P0-1 from the code review)**: `gmail_ingest._match_job` now uses a uniqueness rule instead of guessing — deleted jobs are never a candidate, exact `ct_key` comparison first, then calibrated `dedup_text.titel_aehnlichkeit()` (threshold 0.5, measured against the 8 real collision cases of the live DB) instead of the old 20-character prefix fallback; several equivalent candidates → sentinel `_MEHRDEUTIG` (ambiguous) instead of a guess, the email stays company-related without a job, own counter in the ingest summary (stage A) · **legacy diagnosis** (stage B, read-only, `mode=ro` write protection): systematic title-similarity scan of all companies with ≥ 2 jobs (12 clusters, 26 jobs) plus targeted check of the 3 cases named in the code itself for the other bug cause (deleted jobs as candidate) — 5 candidates with an actual email link checked, 4 unremarkable, 1 finding (Atos: 2 emails parked on a job that was deleted in the meantime, no status overwritten, recommendation to reassign manually) · full finding including the reconstructability analysis in `tasks/phase61b_altbestand_diagnose.md` | ✅ |
| **62** | **Advisory Board: budget guard + honest error handling** (P1-4/P1-5/P2-5 from the code review): 62A — `_guard_tagesbudget()` (daily/monthly limit + emergency stop) now also applies at both Advisory Board entry points (`beirat_debatte_starten`, `_beirat_stellen_check_starten`, according to the docstring a common core with `create_task`) — previously 72 runs/$129.62 passed the guard unchecked · 62B — `_turn_anthropic` now checks `is_error`/`api_error_status` (new pure helper function `_result_event_auswerten`, a testable seam; `subtype` often stays misleadingly `"success"` on an API error, demonstrated in `data/agent_logs/task_342.jsonl`) and raises instead of storing the error message as contribution text (happened in reality: `data/beirat/2026_07_23_2126_0e843f.json`, the chair's contribution = pure session-limit error text); dispatch and persona turn get the pattern "1 attempt + 1 retry" established in the file for this (as with vote/synthesis) — if the dispatch remains broken after that, the debate aborts honestly (`status="fehler"`), a persona board member is omitted instead and the debate continues (moderationen/beitraege remain strictly parallel lists) · 7 new tests (`test_beirat_fehler.py`), 54→61 green | ✅ (A+B) |
| **63A** | **Privacy hardening: secrets out of the sync area** (P1-2 from the code review): the four path constants for Gmail secrets (`gmail_client.CRED_FILE`/`TOKEN_FILE`) and `agent.env` (`agent_runner.ENV_FILE`, `apify_client.ENV_FILE`) now point to `~/.bewerbung_mgmt_secrets/` (directory `chmod 700`, files `chmod 600`, override `BMS_SECRETS_DIR`) instead of `automation/` in the iCloud-synchronised project folder — same pattern as `beirat_engine.KEY_DIR`. Migration in D1 order (copy → verify via the credential chain, NO mailbox access → move originals to `data/papierkorb/phase63_secrets/` → verify again); the token-refresh WRITE path (`gmail_client._save_token`) was moved along at the same time (directory is recreated with 700 if needed) and a consequential error in `cmd_auth()` was fixed (`TOKEN_FILE.relative_to(PROJECT_ROOT)` would have raised after the move). 6 new tests (`test_secrets_pfade.py`), 61→67 green | ✅ |
| **63B** | **Privacy hardening: agent logs out of the sync area** (P1-3 from the code review): `agent_runner.LOG_DIR` now points to `~/.bewerbung_mgmt_logs/` (directory `chmod 700`, files `chmod 600`, override `BMS_LOG_DIR`) instead of `data/agent_logs/` in the iCloud-synchronised project folder — the raw output stream of every run contains CV contents read and full email texts in plain text. **Core of the stage (invariant D3):** the 377 `AgentTask.log_path` values already in the DB at the time of migration are NOT rewritten (risk without return) — instead the new function `agent_runner.resolve_log_path()` resolves every stored value (first `LOG_DIR / <Basename>`, otherwise the old project-relative path as fallback); `log_path` is thus semantically an IDENTIFIER, no longer a literal path — new rows store only the basename. Both writers (runner `_run_task` AND the in-server Advisory Board engine `beirat_engine._task_anlegen`/`_log_zeile`, which had previously hard-coded the same folder independently) now share `neue_log_datei()` (chmod 700/600, pattern from `gmail_client.py`) and import `LOG_DIR` from a single source. Rotation (`cleanup_logs()`, 30 days unchanged) previously ran only at server start — now additionally runs after every task completion, throttled to at most once per hour (`_cleanup_logs_gedrosselt()`, no new background task). Migration: 379 existing files (111 MB) moved, `data/agent_logs/` empty afterwards, all files `chmod 600`; verified live via `GET /api/tasks/{id}?tail=…` (existing stock returns HTTP 200 with content via the fallback path, a freshly created task lies directly in the new location, `log_path` is only the basename). 15 new tests (`test_log_pfade.py`, including resolution new/old/priority/missing, permissions, rotation, time lock), additionally `backend/tests/conftest.py` extended with the same `BMS_LOG_DIR` tmp isolation as `BMS_DATA_DIR` (closes a documented T1 risk path in the `client` fixture docstring), 67→82 green | ✅ |
| **64** | **Errors in the error path: visible and survivable instead of silent** (P1-7, P2-1, P2-19, P2-20 from the code review; guiding principle: an error may be loud and abort, but never be invisible or paralyse something permanently) — 64A: all six delete endpoints now commit the DB change BEFORE the file move instead of after (if a move fails, an orphaned file results instead of a dead DB reference — orphans already feed into the clean-up alarm threshold, dead references did not so far); every move failure is caught PER FILE, counted and reported loudly, instead of blocking the remaining files or rolling back the commit; `pipeline/cleanup.py` additionally includes `dangling_referenzen > 3` in the `auffaellig` (conspicuous) threshold · 64B — three further silent failures made audible: the `while True` loop of `agent_runner._worker()` now survives any exception escaping from `_run_task()` (P2-1; previously a failure in the error path itself — e.g. a failing DB commit — ended the loop FOREVER, `_workers` is never read again, no supervisor; all future tasks silently stayed "queued"), additionally the error-path helpers `_update`/`_fehlschlag`/`_finish` themselves swallow a failed commit and report it loudly instead of rethrowing it (residual risk documented: the affected task row may stay in the old state until the next server restart) · `db._ensure_columns()` now reports a failed `PRAGMA table_info` call with the table name instead of skipping it without trace (P2-19); the inner `ALTER TABLE` branch is newly secured idempotently against the multi-process case (since Phase 63 every skill run starts `init_db()` in its own subprocess; SQLite has no `ADD COLUMN IF NOT EXISTS`) — "duplicate column" stays deliberately quiet, every other error is loud · the `finally` block of `beirat_engine.Debatte.laufen()` now catches a failing `_task_abschliessen()` commit and reports it loudly; `await self.queue.put(None)` (SSE end signal) therefore runs in EVERY case (P2-20; previously the AgentTask row stayed "running" on a failure — blocks the double-run guard until restart — AND the stream to the interface never ended). 20 new tests (`test_loeschen_reihenfolge.py` 13 cases + `test_fehlerpfade.py` 7 cases, error paths themselves forced by monkeypatch, no real Advisory Board/skill run), 82→102 green | ✅ (A+B) |
| **65** | **Process tracking across server restarts (P1-6 from the code review)**: new additive column `AgentTask.pid` — set+committed directly after the subprocess starts, cleared again on every completion (success/failure) and before every retry requeue · new shutdown hook (`@app.on_event("shutdown")`, `agent_runner.shutdown_kill_all()`) ends all child processes still on record at an orderly restart — deliberately WITHOUT an identity check (own handles of the same process lifetime, justification in the code as an asymmetry to the startup check) · crash recovery at start replaces the previous unconditional "running" → "failed" (whose comment "an earlier process is dead" was demonstrably wrong — an ordinary Ctrl+C is enough to leave a `claude -p` process running orphaned because of `start_new_session=True`) with four cases: no PID on record / PID dead / PID alive but foreign / PID alive and confirmed. **P1 — foreign-process protection** (the toughest rule of this phase): a stored PID is not a permanent credential, since after a restart it may long since belong to a foreign Mac program — a process is ended ONLY if TWO independent attributes match (command line via `ps -p <pid> -o command=` against the command expected for the task kind AND start time not before `started_at`, 2 s tolerance against second rounding), otherwise the process is left untouched and there is a loud warning; own testable function `_ist_unser_prozess()`, no `psutil` (only `ps` + `os.kill`) · `beirat_engine` deliberately gets NO PID tracking (detailed justification in the code at `_task_anlegen()`: debates run as an in-server coroutine without a single long-lived child process, every turn subprocess has `--tools ""` and an empty `cwd` outside the project — it structurally cannot write to DB/`outputs/`, even if it briefly survives a crash). 7 new tests (`test_prozess_tracking.py`, central: a real harmless throwaway process (`sleep`) survives the recovery unterminated, the row still becomes `failed`), 102→109 green | ✅ |
| **66** | **Sandbox hardening (P1-1 from the code review) — damage limitation instead of a pretended security boundary:** 66A — `agent_runner._child_env(kind)` passes on to each skill subprocess only the secrets from `agent.env` released for this kind (`SECRET_KEYS_BY_KIND`, currently the only row `jobsuche-apify` → `APIFY_TOKEN`) instead of every key to every subprocess as before, with a loud message in the task log for withheld keys; 9 of 22 headless kinds additionally get `disallowed_tools` (WebSearch/WebFetch blocked where, according to code/SKILL.md/log history, the skill demonstrably does not need them) — allowlist itself (`Bash(curl:*)`/`Bash(python:*)`) deliberately unchanged (justification: "The honest starting point" in the build spec Phase 66, see section 8 above) · 66B — foreign-text labelling: `agent_runner.HEADLESS_SUFFIX` explicitly marks every foreign text loaded via WebFetch/WebSearch/curl/gmail_client as data material rather than an instruction (applies to EVERY headless prompt), supplemented at the two most concrete embedding points (`firma-pruefen`/SKILL.md posting snapshot, `email-check`/SKILL.md email classification) — hygiene, not a guarantee; new `scripts/outbound_check.py` (read-only, no automatism) lists outbound destinations from the agent logs against a maintained expectation list, described in this document under "Everyday operation"; residual risk expressly documented (this section + `automation/agent_settings.json` `$comment`) — still open are the `gmail.compose` scope (the boundary is the missing code path) and the file-based Gmail access gap (66A structurally cannot close it). 21 new tests (`test_outbound_check.py`), 124→145 green | ✅ (A+B) |

The table deliberately ends at Phase 66: changes since then (Phase 67 ff., including career-page
fallback, applied-jobs check, posting-snapshot renderer, style-guide §18 rollout, coach site) have been
worked directly into sections 1–9 rather than appended here as a growing list — the running
change log per phase is kept by the author in his project history (not part of the public repository), compactly mirrored in `docs/WAS_IST_NEU.md`.

### Working mode

Features are planned as a **self-contained build spec** (in the author's project history, not in the public
repository); another AI session builds them. Small fixes are done directly. Rejected phases remain documented with
their reasons (measurement data as reference).

---

*Last updated on 01.10.2026 (P2-59, P2-60, P2-62); the section "Licence" on 29.10.2026
(P2-82, removed) and the section "Update information from GitHub releases" on 29.10.2026 (P2-82, previously
"Package service and network rules", 13.10.2026, P2-71), the section "Profile file" on 11.10.2026 (P2-69), the paragraphs "Saving the posting text" and "Portal status" on 14.10.2026 (P2-75, P2-76). Since parallel build sessions are running,
the authoritative source is always the code itself, not this file.*
