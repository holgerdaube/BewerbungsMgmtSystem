# Automation — Status after Phase 82 (12 Aug 2026)

The "daily run" (job search → email job search → target-company sweep → headhunter search → applied-jobs check →
mailbox check → rejection analysis (once a week) → views refresh → coach site) runs **at the
press of a button**, not on a timer.
This is a deliberate decision, not an open construction site. This document says what applies and why.

## How it works today

**The app starts the skills itself.** The agent runner (`backend/app/agent_runner.py`) spawns a headless
`claude -p` process for each task, using the existing skills (under ChatGPT it uses `codex exec` instead,
see `docs/DOKUMENTATION.md`, "Two AIs"; purely local steps such as
`views-refresh`/`coach-site` do not even need a language model, see below). 24 task kinds run this way
headless (`PROMPTS`), plus 3 chains (`RECIPES`: `deepdive`, `bewerbungspaket`, `tageslauf`). Most of them
also have their own button somewhere in the app (Review, job detail, Settings,
Inbox, Follow-ups). Copy-pasting into a Claude session is no longer NECESSARY. The classic route
(typing the trigger sentence, `docs/ANLEITUNG.md` section 2) still works for every skill as an
alternative, often expandable right next to the button.

**The ☀️ daily run button** (sidebar, reachable from every page) starts the nine-stage chain
`jobsuche → mail-jobsuche → zielfirmen-sweep → headhunter-suche → beworben-check → email-check →
absagen-analyse → views-refresh → coach-site` directly in the app, headless in the background.
`views-refresh` (Excel + digest) and `coach-site` (deterministic export + SFTP mirror, Phase 81)
need no language model and therefore cost nothing; `coach-site` is deliberately
non-fatal as the last link (see "Guardrails" below). `absagen-analyse` (P2-79) runs only once per calendar week: Before
starting the model, the runner asks `pipeline.absagen_bericht.faellig()` (PROMPTS key
`in_kette_nur_wenn`) and otherwise closes the step at no cost as "Skipped: …". A start
by hand (dashboard) never checks this.

## What does NOT run headless (and why)

- `angebot-vergleich` — needs follow-up questions about the terms. Headless, the run would guess.
- `outreach-drive-upload` — Google Drive upload cannot be automated (`create_file` requires
  base64 inline, ~100 KB exceeds the tool argument limit). Generate the file from the app and upload it manually.
- The **Advisory Board** (`beirat-stellen-check`, `beirat-debatte`) runs through its own engine live in the
  server (Server-Sent Events, chat-like live experience), not through this runner. Both kinds
  appear in `PROMPTS` only for the label list/error message; a "Retry" in the Task Centre fails
  there on purpose with an explanatory error instead of starting `claude -p` for something the runner cannot
  execute at all.

**Headless, but deliberately not part of the daily run:**
- `jobsuche-apify` is **opt-in**: Apify costs real money (the free plan includes about $5 per month), and the
  actors charge per result (`kostet_geld` marker → its own budget guard before the start). The normal
  `jobsuche` run (WebSearch) costs no Apify credits and runs in the daily run; you start Apify
  separately via the second button in Review.

**Outdated (as of ≤ 8.2):** Earlier versions of this document warned that the Gmail connector might
"possibly not" work headless. That was true, and it has been solved since 8.3: Gmail runs through the local
`pipeline/gmail_client.py` with its own OAuth, not through the claude.ai connector. Verified on 10 July:
a `claude -p` run sees **zero MCP tools**.

## Guardrails

| Limit | Default | Configurable via |
|---|---|---|
| Emergency brake per run (aborts a running process) | $15 | Env `AGENT_MAX_BUDGET_USD` |
| Daily budget (new runs) | $100 | App → 💶 Budget → "Claude (agent runs)"; Env `AGENT_DAILY_BUDGET_USD` only as a fallback if the DB row is missing |
| Runs per day | 100 | ditto (`max_runs_per_day`); Env `AGENT_MAX_TASKS_PER_DAY` only as a fallback |
| Monthly budget | no limit (default) | ditto, optional |
| Parallel runs | 2 | Env `AGENT_MAX_PARALLEL` |
| Keep task logs | 30 days | Env `AGENT_LOG_RETENTION_DAYS` |
| Keep intermediate files in `data/tmp/` (P2-53; files with a DB reference always stay) | 30 days, same period | Env `AGENT_LOG_RETENTION_DAYS` |

The daily budget, runs limit and monthly budget are NO LONGER hard-coded. They sit in a
database row (`BudgetLimit`, provider `claude-runs`), visible and editable on the Budget page
as the service "Claude (agent runs)". Two controls there act on ALL three numbers at the same time:
- Unticking **"Service active"** = emergency stop. It always blocks runs, regardless of hard/soft.
- **hard/soft** — the default is **soft** (explicit wish of the author, 11 July 2026): the daily budget,
  runs limit and monthly budget then only warn (`warnung` in `GET /api/agent-status`), but block
  nothing. Only "hard" makes the 409 rejection take effect. The $15 emergency brake per run
  is independent of this and always armed.
- The day begins at **local midnight** (not UTC — `AgentTask.created_at` is UTC, and it is
  converted).
- **Running runs are never shot down.** The guards only block NEW starts.

**Double-run lock per job** (`main.py::_guard_doppellauf`): For the same `job_id`, the same
task kind (or, for chains, none of its steps) must not run twice at the same time; a second
start gets **HTTP 409** with the id of the task that is already running. Runs that do not belong to a job (job search,
sweeps, applied-jobs check, daily run, …) are affected in the same way as job-bound ones.

**Target-role fit ≤ 2 confirmation** (`main.py::_guard_low_match`, 27 July 2026): Document runs (`firma-pruefen`,
`cv-match`, `cv-erstellen`, `anschreiben-erstellen`, as well as the chains `deepdive`/`bewerbungspaket`)
for a job with a target-role fit ≤ 2 get **HTTP 409** with the marker `LOW_MATCH` instead of
starting without further ado. The app shows this inline as the question "Are you really sure?"; "Yes, start
anyway" repeats the same start with `params.low_match_ok=true`. Unrated jobs (without a
target-role fit) are not affected.

**The rejection analysis does not cost you the day if it fails** (P2-79): A chain step that has
failed for good otherwise cancels all its successors (`_release_dependents`). For
`absagen-analyse`, `kette_weiter_bei_fehler` is set: if it fails (also by timeout), `views-refresh`
and `coach-site` still run; a cancellation by the user still cancels the rest of the chain.
This also holds after a server restart (`start_workers`). The ☀️ button shows the status of the last
link (`coach-site`); a failed analysis step is therefore visible only in the Task Centre.

**The coach site never turns the daily run red:** Without a complete configuration, or with the switch
turned off, the last chain step ends green (local export only, exit 0). As long as the coach site
has not been set up, the daily run stays completely green. A real SFTP error AFTER setup
marks only the `coach-site` task as `failed`; all previous steps remain untouched (last
link of the chain, see `docs/COACH_SITE.md`).

**Retry:** A failed run is repeated exactly once, but only for task kinds that
duplicate nothing: `firma-pruefen`, `absagen-analyse`, `skills-sortieren`, `email-check`,
`jobsuche`, `mail-jobsuche`, `zielfirmen-sweep`, `headhunter-suche`, `beworben-check` as well as the three
local, free steps `views-refresh`, `cover-letter-render`, `coach-site`. Anything that creates
rows, files or **Gmail drafts** (including `cv-match`, `anschreiben-erstellen`,
`nachfass-mail`, `gespraech-debrief`, `mail-antwort`) is never repeated automatically. Timeout,
budget emergency brake and user cancellation also trigger no retry.

The current status is in the **Task Centre** (`/tasks`) and at `GET /api/agent-status`.

## Scheduling — deliberately not built

**Decision (10 July 2026): the daily run stays manual.** This still holds: as of
12 Aug 2026, `automation/` still contains only the (inactive) refresh-only template from back then, and no
new scheduler has been added. Anyone who wants to change this later should know the two routes and their costs:

**Since P2-52 there is exactly ONE timer of this kind in the backend** (`app/sicherung.py::starten()`,
an asyncio task in the running server process, pattern (a) below), deliberately narrowly limited to the daily
database backup and not a blueprint for the daily run. The cost trade-off below
(the condition "app is running", catching up on missed runs) remained decisive in the decision against an
extended scheduler: a missed backup run has no consequences (the next
30-minute tick catches it up as soon as the app is running again); a missed daily run with
job search/mail check would not be harmless.

**a) Scheduler in the backend** (asyncio loop in the running FastAPI process). Simple, no
disk access grant needed, ~60 lines. Condition: the app is running (`start.command` open). If it is
off, nothing fires. On a laptop you would have to catch up on missed runs, which needs its own semantics
(which run counts as "already done today"?).

**b) launchd.** Also runs without an open app, but costs this:
- launchd **cannot read iCloud Drive** without a manual "Full Disk Access" grant.
  This affects every project that lives in iCloud.
- The Mac must be awake **and** unlocked.
- A second startup path next to `start.command` that is hard to test.

The existing template `automation/com.bms.tageslauf.plist.template` does **not** start
the daily run, only the LLM-free views refresh (`scripts/refresh_views.sh`, daily 07:00).
It is **not activated** (before loading, replace `[PFAD_ZUM_PROJEKT]` in the template with the absolute
project path). If you only want fresh Excel/digest files in the morning, you can load it:

```sh
cp automation/com.bms.tageslauf.plist.template \
   ~/Library/LaunchAgents/com.bms.tageslauf.plist
launchctl load ~/Library/LaunchAgents/com.bms.tageslauf.plist
```
Deactivate: `launchctl unload …` · Test manually: `scripts/refresh_views.sh`
The iCloud/FDA caveat applies here too: before relying on the job, check once that it really ran.

## Unchanged: no auto-applying

At no stage. The system searches, evaluates, researches and prepares. Emails remain **drafts**
(`gmail_client` has no send command). Status decisions and sending remain with the user.
