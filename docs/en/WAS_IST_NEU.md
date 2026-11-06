# What's New? — Change Log (latest changes first)

This file grows with every larger build session. The latest period is always at the top, and older
sections are kept below. Details and verifications for each item are in the author's project history
(one ticked-off plan per build session with a "Review" paragraph; that is the source of this log).
It is not part of the public repository.

---

## 13 Aug 2026 — More interview rounds, clearer names

(Phase 84.)

### For everyday work

- **Any number of interview rounds, right at the transcript.** In the transcript dialog, below
  the round selection, there is now "**+ Create new round…**": enter the number and interview type, done.
  No more detour through a second dialog. New here is the type "**Headhunter screen**" for the
  preliminary conversation with a recruiter. The "Counterpart" field fills itself to match the type
  (technical interview → department, headhunter screen → headhunter); if you deliberately set
  something else, your choice stays. The round is only created when you save,
  so if you cancel, nothing is left behind.
- **The job score is now called "target-role fit".** Until now, three different ratings
  in the system were all called "match": the rating of the *job* (1–5), the rating of your *CV* against the
  posting (0–100) and the ATS value. The job score therefore now has its own name:
  **target-role fit**. It measures the job against your target profile (situation · function · region).
  Here is how you recognise it: dashboard tile "**Top target roles (≥4)**" and bar "**By
  target-role fit**", in the job list the filter (`Zielstellen-Fit ≥ 4`) and sorting, the
  tooltip on the coloured number, the field when creating a job manually, and the tile in the
  daily digest. An overview of all three ratings is in `ANLEITUNG.md`, section 4.
  **Nothing about the rating itself has changed**: the same rating grid, the same stored
  values. The status "No match" is still called that, too.

---

## 25 Jul–12 Aug 2026 — Coach access, more robust application tracking, uniform design

(Phases 73–82.)

### For everyday work

- **Career page fallback when a portal is closed:** If the company check detects that a
  job is no longer active on the original portal, the system automatically searches
  the company's career page for the same job. Here is how you recognise it: job detail → key facts — a new
  "Career page" row (link) and, if applicable, a red row "Portal application:
  closed". You can also set both by hand in edit mode.
- **Weekly applied-jobs check:** For every running application (Applied/Interview), the
  system automatically checks in the daily run whether the job is still advertised. Your application status
  itself is never touched; that remains your decision alone. Here is how you recognise it:
  job detail → key facts row "Availability" (with check date); job list → badge
  "⛔ offline"; dashboard → tile "Applied jobs offline" (only visible if there are any).
  Trigger it manually: Review page → button "Applied-jobs check".
- **Posting snapshots clearly structured again:** The snapshot of a job posting now once more reliably separates
  tasks, requirements, benefits, "About the company" and context
  from one another, including a separate section "⚠️ Contradictions" if the posting and the captured
  key facts diverge. Here is how you recognise it: job detail → posting snapshot (after the
  company check).
- **Excel export with the real screening-out reason:** In the "Screened out" sheet, the "Reason" column
  now shows the actual reason (from your notes or the match rationale) instead of the always
  empty "Next step" column. Both job sheets also show the match score as a
  number from 0–100, and the Advisory Board column is condensed to a number + traffic-light colour. Here is how you recognise it:
  dashboard → "⬇ Excel export".
- **AI questions about a job can be cancelled:** If the answer to "Ask about this job (AI)"
  takes too long, a new "Cancel" button ends it immediately. Even after a page reload
  while the answer is still running, the page finds the running request again and the
  Cancel button stays available. Here is how you recognise it: job detail → section
  "Ask about this job (AI)".
- **New "Email check" button:** The daily Gmail check can now also be
  triggered by hand, without waiting for the next daily run. Here is how you recognise it: Review page →
  button row, right next to "Applied-jobs check".

### New: Coach site

An external coach can now read along, if you want, with read-only access: overview, active
applications and screening/review (New + To review) with company fit, match and job posting
for each job, plus rejections with reasons. The coach **never** gets to see emails, notes, Advisory Board checks, salaries
and transcripts.

- **Fully configurable via Settings** (previously it could only be set up via a local
  configuration file): Settings → "Coach site" card — address of the site, upload target
  (SFTP host/user/password/target directory), server path to the credentials file (button
  "detect automatically" instead of looking up values by hand), a separate coach login (user + password,
  hashed securely on your machine) and an on/off switch. In addition, "Test connection" and
  "Update coach site now". Otherwise it updates itself automatically at the end of every
  daily run.
- **Own favicon:** Every coach page and every document exported for the coach now shows
  the app icon in the browser tab instead of an empty placeholder.
- **Own guide:** A step-by-step guide including an "If something doesn't
  work" section is at `docs/ANLEITUNG_COACH_SITE.md` (linked from the Settings card)
  and also as a printable HTML manual.

### Under the hood

- **Design brought fully in line with the style guide:** The app interface and all generated
  reports (company fit, digest, Advisory Board synthesis) now consistently use the same colour and
  font basis (including cyan primary buttons instead of navy, real Montserrat/Inter fonts instead of the
  browser default). You notice it as a more uniform look across the whole app and all
  reports.
- **Workday-compatible base CVs:** The base CVs (the starting point for every CV match) have been
  rebuilt so that Workday application forms ("Autofill with Resume") read title, company and
  period for each position correctly instead of shifting the title by one position.
- **cv-match now always rebuilds:** A "CV match" or "match again" run is guaranteed to take the
  current base CV file as its starting point and creates a fresh draft, so an older draft version is
  never silently recycled any more.
- **Uniform sign-in for background runs:** Advisory Board runs now use the same
  sign-in route as the other skills. This prevents several background runs started at the same time
  from locking each other out, as occasionally happened before.

---

## 9 Jul 2026 — Walkthrough of the changes from the big expansion day

Everything from the big expansion day: follow-ups, interviews, rejection analysis, cover letters, speculative-application workflow,
mobile. **Here is how you recognise each change in the app**: just walk through the click paths.
(Phases 6–8.)

---

### 1. Dashboard — http://localhost:8000
- **Everything is clickable now:** Every KPI tile has a → arrow and leads to the matching list
  (jobs, top matches, running applications, companies, inbox). The funnel bars are links too.
- **The four bar tiles as well** (By status / Match score / Situation / Portal, "· clickable" in the title):
  each bar opens the job list with exactly that filter, including a filter chip to deselect it.
- **New at the top: the follow-up banner** ("⏰ Follow-ups at a glance / 12 open") → leads to the new follow-up page.
- **New tile "Applications (running)"**: counts only Applied/Interview/Offer, not history.
- **Numbers are cleaned up:** Duplicate pairs were merged (with your approval).

### 2. Sidebar — new menu item
- **"⏰ Follow-ups"** between Review and Pipeline. A red badge = number of overdue follow-ups.

### 3. Follow-ups page — /followups (completely new)
- **🎙️ Upcoming interviews** right at the top: all scheduled interviews with a briefing link, if applicable 🗺️ Route,
  and a "Date missing" warning (an interview without a date is flagged there).
- **🔴 Overdue & today** / **⏳ Upcoming**: all jobs with a due date. Unanswered
  applications are scheduled automatically.
- **✉️ Follow-up chip** on every row: copies "Follow-up draft for job X" — paste it into the Claude
  session → finished Gmail draft (is NEVER sent automatically).

### 4. Job list — /jobs
- **"+ Create job"** (button at the top right, new): capture jobs you found manually with all their data;
  the form is at `/jobs/neu`. Selectable status: **New** (Review list) · **To review** (active pipeline) ·
  **Applied** (creates the application with its date straight away). Duplicates are detected and linked instead of being created twice.
- New column **"Found"** + sort dropdown (**Date**, score, company, status). Dates are now correctly
  chronological despite mixed formats.
- **⏰ badge** on the title when a follow-up is due (red = overdue).
- Drill-down headings: if you come from the dashboard, the page is called, for example, "Running applications"
  (with chip + "Reset filter").

### 5. Job detail — most of the new things are here
Right-hand column, from top to bottom:
- **Change status:** now including **Interview** and **Offer**. New below it:
  - **Gut feeling ★★★★★**: your subjective 1–5 score next to the rating grid score (click again to clear).
  - For status Rejected: **"❓ Ask for the reason"** → polite feedback email as a draft.
- **Next steps & follow-up:** due date, next step, notes, directly editable;
  an "overdue" badge also at the top in the header.
- **Interviews & conversations (new):** create conversations (round/type/date/interviewer), status pills,
  **📋 Open briefing**, **🗺️ Route** (for on-site jobs),
  the **🎯 Prepare interview** button, below it **Paste/open transcripts**.
- **Application:** new **"Reason for rejection"** (filled from the real rejection emails) and
  **"⬇ Cover letter (.docx)"**.

### 6. Network & Radar — /netzwerk and /radar
- **"🚀 Speculative" chip** in every row (target companies tab or Radar): copies "Speculative application for
  <company>" → starts the hidden-job-market workflow in the Claude session (network check first!).
- The target-company check shows which target companies already have a warm path (contact with status
  "In Dialogue" or "Responded").

### 6b. Outreach — /outreach (revised)
- **The Overdue tile is clickable:** filters the list to overdue follow-ups (click again or ✕ to clear).
- **Every row can be expanded (▸):** there you edit **Next step + due date** directly,
  and keep the new **activity log**: status/step changes are logged automatically
  (grey AUTO badge); you simply type your own entries (Enter). Chronological, newest first.
- The log lives only in the app; the Excel export (original format) remains unchanged.

### 7. Phone — new: `start_lan.command`
Double-click instead of `start.command` → the terminal shows the phone address (e.g. `http://<dein-mac>.local:8000`).
On mobile, navigation is at the top (swipeable), and you swipe tables sideways. ⚠️ No login — only on your own Wi-Fi.

### 8. The new sentences for the Claude session (the "engine")
| You say … | What happens … |
|---|---|
| `Interview vorbereiten für Job <id>` | Call briefing (questions + STAR, questions to the company, cheat sheet) → linked at the interview |
| `Debrief für Job <id>` | Evaluate the transcript: summary, to-dos, contacts, question bank, thank-you email DRAFT |
| `Absagen-Analyse` | Lost-order evaluation across all rejections → report + empirical findings in profil.md |
| `Anschreiben für Job <id>` | Company-specific cover letter (.docx) → at the application ("Prepared") |
| `Initiativbewerbung für <Firma>` | Network check → speculative job → decision-maker → approach route |
| `welche Zielfirmen soll ich initiativ angehen` | Prioritised shortlist (warm > tier > signal) |
| `Nachfass-Entwurf für Job <id>` | Polite follow-up when there is radio silence (Gmail draft) |
| `Nach Absagegrund fragen für Job <id>` | Feedback request after a rejection (Gmail draft) |
| `Entscheider für Job <id>` / `wer ist der Hiring Manager bei <Firma>` | Research the functional decision-makers + previous holder of the role |
| `Angebot bewerten für Job <id>` | Benefits points list / offer matrix (once status is "Offer") |
Existing sentences (`Tageslauf`, `Firma prüfen…`, `CV anpassen…`, `Deep-Dive…`, `prüf mein Postfach`,
`such nach neuen Stellen`) work unchanged. `Firma prüfen` now additionally delivers the
section **"Employer reality"** (kununu signal, genuinely-modern vs. claimed-modern, activity, business development),
and `CV anpassen` additionally delivers the **weighted requirements matching** (must/should/could × 1–10 with evidence).

### 9. Reports & files (retrievable via the app)
- **Rejection analysis:** `data/analysen/<Datum>_Absagen_Analyse.html` — the 5 patterns + recommendations
  (a short version of the findings is also in `config/profil.md` → "Empirie").
- **Complete package per job:** company fit + briefing (`data/interview_prep/…`) + tailored CV + cover letter
  (`cv/cover/…`), all linked at the job detail.

### 10. How to recognise future changes
Every build session leaves in the author's project history (not part of the public repository) a
ticked-off plan + "Review" paragraph (what, why, how verified). That is the system's change log.
