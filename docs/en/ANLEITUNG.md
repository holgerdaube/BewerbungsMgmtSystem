# Guide — How to work with the Job Application Management System

> **What's new?** What changes from version to version is listed under **📖 Documentation** in the
> sidebar, on the “Version” tab. The “Features” tab gives you a short overview of
> what BMS can do.

A cockpit for your job search. Basic principle: **the system finds, assesses and prepares —
you decide.** It never applies automatically and sends nothing without your action.

Two building blocks work together:
- **The skills** = the engine: search, assess, tailor your CV, check Gmail. Today you mostly start them
  with the press of a button directly in the app (they run headless in the background). The classic route via a
  Claude session (typing a trigger phrase) still works for every skill as an alternative.
- **The web app** (http://localhost:8000) = the cockpit: review, decide, manage, export
  — and the place where you start skill runs and follow them in the Task Centre.
Both work on **one** central database.

---

## 1. Starting
Double-click **`start.command`** → the app opens at http://localhost:8000.

**Using it from your phone or tablet (your own Wi-Fi):** double-click **`start_lan.command`** instead.
The terminal shows you the address for your phone (e.g. `http://<your-mac>.local:8000`). The views
work on mobile (navigation at the top, tables can be swiped sideways).
⚠️ No login protection — use it only on your own, trusted Wi-Fi; `start.command` remains the default (this Mac only).

Open BMS on your phone at one of the addresses the terminal shows: the `.local` name
or the IP address. Under other names, such as one your router assigns
(`mein-mac.fritz.box`), it answers “Address not allowed”. This stops
a foreign website from reaching your data through a redirected name. If you need such a
name anyway, start from the BMS folder in the terminal with
`BMS_HOSTS=mein-mac.fritz.box ./start_lan.command` (separate several names with a comma). You cannot
pass the approval along with a double-click.

**Quitting:** `Ctrl+C` in the terminal window that opened at start. If the window is
gone or no longer responds, double-click **`stop.command`** (Windows:
`stop_windows.bat`). The script asks first if runs are active
or queued at the moment — stopping in the middle aborts them, and a running Advisory Board debate is lost afterwards. Nothing is lost
when the app is not running, by the way: everything is in the
database, and a later start shows the same state.

### On the very first start: sample data

A fresh installation does not start empty but with sample data. **Remove it before you enter
your own data.** The sample data belongs to **Benno Bewerbaer**, a fictional person:
a postman with five years of experience in parcel delivery. This lets you try out everything before
your own data is in. It includes six companies, five jobs (one each with the status New,
To review, Applied, Interview and Rejected), three applications, five emails, an interview date three
days after the first start, one contact, one network contact, a profile with skills
and career history, the profile file `config/profil.md` and a German base CV. One of the
emails has no job: you use it to try out “Assign to job” and “Archive” in the Inbox.
The sample data creates no search plans, target companies or headhunters, and companies and jobs
have no web address. An AI run on a sample job therefore achieves nothing, because the company is
fictional. The applied-jobs check in the daily run skips the sample jobs on its own.

Only the very first start creates sample data. An existing installation and an update
get none, and once removed they never come back. As long as they are there, the
dashboard shows an amber notice, and the sidebar shows “Benno Bewerbaer” as your name.

**How to remove them:** Open **Settings**; the “Sample data” card is at the very top of
the page. Click “Remove sample data” and confirm with “Yes, remove”. Beforehand,
BMS creates a backup of your database in the folder `data/backups/auto`, where “Back up now”
also saves. If the backup fails, everything stays unchanged, and the card gives the reason.
After that, the following applies:
- Only the sample data and what hangs off the sample jobs is deleted: contacts,
  applications, interviews, Notes & history, chat, transcripts, tailored CVs and files.
  What you created yourself stays. Files from this, such as reports and CVs you generated
  on a sample job, move to the bin `data/papierkorb/`.
- Emails you assigned to a sample job are kept as emails without a job.
  AI runs on a sample job stay in the Task Centre with their costs; only the link
  to the job is dropped. If an AI run is currently running on a sample job, BMS refuses
  the removal and asks you to wait for the run.
- The profile file `config/profil.md` and the base CV also move to the bin,
  but only if you have not changed them. A version of your own stays in place, and the card
  names it for you. The positioning in the profile is only cleared as long as the sample text is still in it.
- After that, the sidebar shows “Applicant” until you save your name on the Profile page in the
  “Identity and search strategy” card.

**Order of setup:** First remove the sample data, then fill in the “Identity
and search strategy” card and upload the base CV (both in the “Profile” section further down,
details in `BMS_Install_MAC.en.md` or `BMS_Install_Windows.en.md`, section “Setup: BMS
gets to know you”), and only then the LinkedIn import. The import only fills
empty fields; with the sample data in the profile it would therefore not take over your positioning. If you
have already saved your profile or edited `config/profil.md` by hand before you remove the sample data,
BMS recognises the file as your own and leaves it in place. Then go through the card
once from top to bottom: name, address, contact details, short profile, target date and constraints should be
yours, with nothing left of Benno Bewerbaer.

---

## 2. The engine — the skills
Which AI runs the skills, Claude or ChatGPT, is set in **Settings** (“AI” card,
the default is Claude). The skills are the same for both.

Two equivalent ways to start a skill:
1. **As a button in the app** — New / Review (job search & sweeps), job details (“Create documents”),
   Settings (coach site) or the ☀️ daily run button in the sidebar start the run
   directly; it runs headless in the background, and you see progress, log and costs live in the Task Centre
   (section 3). Where available, a collapsible “Alternatively: run in a Claude session” stays next to it.
2. **As a trigger phrase in a Claude session** — you say, roughly, one of the phrases below;
   it works for **every** skill, including those (still) without a button of their own:

| Say something like … | Skill | What happens |
|---|---|---|
| “**Daily run**” | `tageslauf` | The complete chain in one go: job search → email job search → target-company sweep → headhunter search → applied-jobs check → inbox check → rejection analysis (once a week) → refresh views → coach site update (non-fatal) + morning summary. |
| “**search for new jobs**” | `jobsuche` | Searches portals → removes duplicates → rates the target-role fit 1–5 → creates results as **“New”**. |
| “**Email job search**” | `mail-jobsuche` | Turns LinkedIn and other job alert emails from your mailbox into new jobs (its own rating and duplicate pass). |
| “**Target-company sweep**” | `zielfirmen-sweep` | Checks the careers pages of 12 target companies in rotation (all of them once every ~6 runs) for new jobs. |
| “**Headhunter search**” | `headhunter-suche` | Checks 15 headhunter websites in rotation for suitable (including confidential) assignments. |
| “**Run the applied-jobs check**” | `beworben-check` | Checks weekly whether the job is still advertised for all running applications (Applied/Interview), with a careers page fallback — never changes the application status, only the availability note. |
| “**Rejection analysis**” | `absagen-analyse` | Analyses all rejections and unanswered applications (lost-order analysis) → pattern report. Runs once a week in the daily run; by hand via the dashboard (“Regenerate rejection analysis”). Only a start by hand replaces the evidence lines in your profile; the weekly run only writes its suggestion into the report. |
| “**check my mailbox**” | `email-check` | Application emails of the last 24–36 h → match, classify, response times, contacts, status. |
| “**Company check for job \<id\>**” | `firma-pruefen` | **Step 1:** business model, market, **influence of the role** → company fit dashboard. |
| “**CV match for job \<id\>**” | `cv-match` | **Step 2a (only after step 1):** match dashboard + tailored CV draft (DE/EN), editable in the job details. |
| “**Create CV for job \<id\>**” | `cv-erstellen` | **Step 2b:** creates Word + PDF + ATS scan from the (possibly edited) draft. |
| “**Cover letter for job \<id\>**” | `anschreiben-erstellen` | Company-specific cover letter (DE/EN) with a direct address → `.docx` + PDF. |
| “**Read profile from the stored text**” | `profil-einlesen` | Structures the text of your LinkedIn profile, or its PDF, pasted on the Profile page. You review the suggestion before anything is saved. |
| “**Deep dive for job \<id\>**” | `job-deepdive` | Both in one go (company + CV) — the default, though, is the two separate steps above. |

---

## 3. The areas of the app

The **sidebar** is on the left. At the top it carries the name of the program, “Job Application Management System”,
and below it your name. BMS reads that from your profile (“Identity and search strategy” card,
saved in `config/profil.md`); if the name is missing, it says “Applicant”. The browser tab carries
the same name. At the very bottom is the
installed version, for example “Version 1.1.3”. On a narrow screen such as a phone, the
bar moves to the top and the version line is dropped; the version is then shown in Settings and in
Documentation. The areas covered in this section lie in between.

### 📊 Dashboard
Your overview: key figures (jobs, top target jobs ≥4, applications, emails, responses, Ø response time,
**response rate**), the **pipeline funnel** (New → To review → Applied → … → Rejected) and distributions
(by status, target-role fit, situation, portal). Top right: **Excel export** and **Daily digest**.
As long as sample data is there, an amber notice about it is at the top. A click leads to the
“Sample data” card in Settings.

### 🔍 Search
Full-text search across the whole system — company name, place, job description, company fit dashboard,
transcripts, debriefs, briefings, notes/history. The result is always a **job**, with up to three
hit snippets including a source badge and highlighting. The index is rebuilt daily in the daily run
(“Index status” visible at the bottom) or at the press of a button (“↻ Update index”). **Limit:** CV and
cover letter contents (`.docx`) and the network lists are deliberately NOT searched.

### ✨ New / Review — your triage inbox
At the top is the **“Start a new job search”** card: **Job search (WebSearch)** and **Job search + Apify**
(additionally uses the portal scrapers, costs Apify credits) in the first row; below them
**Target-company sweep**, **Headhunter search**, **Applied-jobs check** and **Email check** — all four
free of charge. Each button starts its run directly in the app, headless in the background; “Last search
run” shows the time and result of the most recent one — even if it came from the daily run.
**Applied-jobs check** checks weekly, for all running applications (Applied/Interview), whether the
job is still advertised: first via the original URL (with the same retrieval as the search runs,
retried when throttled; if a portal does not answer at all, the job stays “unclear” rather than
“offline”), and if the portal is closed, via the company’s careers page. It only writes back the
**availability note** (key facts, dashboard tile “Applied jobs offline”, ⛔ badge in the
jobs list); **it never changes the application status**. **Email check** only reads the mailbox
(responses, rejections, appointments) and matches emails to the applications, without
starting a new job search — the same skill as “check my mailbox” above, just as a button.

Below that are the new results from the job search (status “New”). Per card:
- **Open ↗** — view the original job posting (changes nothing).
- **✓ Accept** — status → **“To review”**. Moves into the active pipeline. Next step: deep dive.
- **✕ Discard** — status → **“No match”**. Archived, **but stays in the DB** → the same
  result does **not** appear again as “New” in future searches (duplicate check).
Both are purely internal sorting, **nothing is deleted or sent**, everything is reversible.
The counter badge shows how many results are still to be reviewed.

### ⏰ Follow-ups — what is due today
Collects everything with a due date in one place. The dates are **set** elsewhere (due date
in the job details under “Next steps & follow-up”, “Due date” on the network contact) — here they only
come together. Four blocks:
- **🎙️ Upcoming conversations** — planned interviews with round/type and interviewer. **“📋 Briefing”**
  opens the preparation (if generated), **“🗺️ Route”** the Google Maps directions from your address
  to the place of work (hidden for remote jobs). If the date is missing, an amber
  **“No date yet — set it in the job details”** appears there.
- **🔴 Jobs — overdue & today** · **⏳ Jobs — upcoming** — per row fit, company, title,
  status, next step and due text (“due today”, “3 days overdue”, “in 5 days”).
  Red & bold = overdue; **“overdue” includes today**.
- **🤝 Network actions** — due contact actions, overdue first (a click leads to `/netzwerk`).

The **“✉️ Follow up”** chip ⚠️ **starts nothing** — it only copies the trigger
`Follow-up draft for job <id>` to your clipboard; you have to send it in the Claude session.
Jobs in a final status (Rejected, No match, Not available, Rejected by board) never appear here,
not even with a date. The page does **not** reload automatically — after changes in the job details,
reload it briefly.

### 📋 Pipeline — Kanban board
All active jobs as cards in columns: **New · To review · Applied · Interview · Offer · Rejected**.
Drag a card into another column with **drag & drop** = change the status. Archived jobs
(No match / Not available / Parked) do not appear here (counter “X archived” at the top).

### 💼 Jobs & job details
**Jobs** = table of all results with filters (status, search tab, fit, search). Click a row → **job details**:
- **Assessment** (why it fits, with evidence), **Key facts** (situation, work model, plan A/B/C, salary …).
  With **“✏️ Edit”** (right in the Key facts card) you can correct or add **all** of these fields by hand
  — e.g. salary or original URL — and apply them with “Save”.
  **Careful with the URL:** if you change the original URL by hand, the “✓ checked” badge disappears (the
  verification applied to the old address); the next check run sets it again for the new URL.
- **Change status** (buttons) · **Next steps & follow-up** · **Notes & history** (between Key facts
  and Email history — changes to status/follow-up/notes are logged here automatically, and you can
  also enter notes freely) · **Contacts** · **Email history** (from the Gmail check).
- **Ask about this job (AI):** a chat window of its own between “Notes & history” and “Email history” —
  the AI answers your question exclusively from the data available for this job
  (company fit, snapshot, history, transcripts, briefing), no web. Question and answer stay as
  chat history and are also added to “Notes & history”. It runs headless in the background
  (“AI is answering…” with **“Cancel”** next to it); reloading the page does not lose a running
  question — it is found again automatically, and the Cancel button reappears
  exactly where you need it.
- **Create documents** (workflow card, right column): two numbered steps,
  **1 · Check company fit** and **2 · CV match**, plus two optional building blocks without a lock:
  **Check job (Advisory Board)** and **Generate cover letter**. The CV match is locked (🔒) until the
  company fit is available; completed steps are greyed out (✓) with “check again”, “match again” or
  “regenerate”. The **Advisory Board** has the board members assess the job, ideally before the
  CV effort; if its vote comes out red, the card offers to set the status straight to
  **“Rejected by board”**. The cover letter uses the tailored CV once it is ready,
  otherwise the base CV. **“Application package”** starts company → CV match → create CV in one go, and with the
  tick box **“with cover letter”** the cover letter as well. The Advisory Board is not part of it; it runs directly
  in the server rather than as an agent task.
- **Intermediate step for your input:** After the CV match, only a **draft** is created at first.
  Under “Files & documents” the window **“Edit CV draft”** appears — the complete
  CV content as one large block of running text (one line = one paragraph). You may freely change, add
  and delete bullet lines; section headings are locked so that the finished `.docx` stays
  ATS-friendly. Only when you are satisfied does “**Create CV**” produce Word + PDF from **your** version — and
  the ATS scan then runs on the final document instead of on an unseen draft. The
  scan shows two numbers: the **ATS score** (degree of optimisation: how well what can honestly be covered has been
  worked in) and the **raw coverage rate** (x of 15
  posting keywords, regardless of whether they can be truthfully covered at all). Only the
  score counts for the ranking; the raw rate is honest fit information, not a flaw for stretch roles.
- **Edit cover letter:** A text window of its own with the letter text. “**Save cover letter**”
  saves your version, then “**Create Word + PDF**” (in that order — the
  window points this out if anything unsaved is still open). For older cover letters without
  stored text, “**Load text from existing .docx**” brings it in once.
- **Tailored CV** (last card): shows only the **facts** — language (German/English), **match** and
  **ATS score**, date. The files themselves are under “Files & documents”.
- **Files & documents**: all **generated** artefacts (company fit dashboard, CV `.docx`/`.pdf`, match/
  ATS dashboard, cover letter `.docx`/`.pdf`, briefings, transcript reports) appear here automatically with a
  **“generated”** badge (open/download) — next to your own uploads (drag & drop). Both kinds can be deleted with
  the 🗑 icon (bin, see section 7) — for the company fit entry, the dialog warns that it applies to
  **all** jobs at this company.
- **Posting copy:** The job posting is saved as early as **capture**
  (job search/email job search/target-company sweep/headhunter search), not only at the company check.
  The posting snapshot therefore appears straight after the first find, with a
  source note in the header (green = original retrieved live, amber = metadata only, no text). If
  `firma-pruefen` runs later, its verified full version replaces the same snapshot (no second
  document). Older jobs without a snapshot can be caught up once:
  `cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.posting_snapshot backfill`.
- **Missing posting text:** If a portal (mostly LinkedIn with “too many requests”) throttles the retrieval,
  BMS tries several times with pauses. If it still does not work, a snapshot can contain only the
  key facts, without the text of the posting. BMS then fetches the text **at the start** of
  company check, CV match, create CV and cover letter. With a throttled portal this can take
  half a minute; underneath the button it says “Fetching the posting text …” meanwhile.
  If fetching does not work, the run does **not** start by itself: A query
  with the reason appears underneath the button (for example “The posting is only visible when signed in”) and the
  buttons **“Start anyway”** and **“Cancel”**. With “Start anyway” the run works only with the
  title and company of the job; the CV match notes this in the dashboard as a red flag, and there is no green
  source badge. If a portal merely throttled, a later attempt usually works;
  then you choose “Cancel” and start the run again later. Jobs whose
  snapshot has no posting text can also be caught up in bulk (alongside `backfill`, which only creates
  snapshots for jobs with **none** at all):
  `cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.posting_snapshot nachholen`
  checks all active jobs (New, To review, Applied, Interview, Offer) and fetches missing text.
  With `--job-id <number>` the command applies to one job only, with `--dry-run` it only counts
  which jobs have no text, and fetches nothing. The text is structured only at the next
  company check; until then the snapshot shows the note “Posting text fetched later on …” at the top.
- **Interviews & conversations → Transcripts:** you can paste a transcript as text **or upload it as a
  file** (`.txt`/`.md`/`.vtt` — Teams/Zoom caption export, timestamps are removed automatically;
  max. 5 MB, no `.docx`). In both cases a **transcript report** is created straight away
  (“📄 Open report”) with a header/note that the debrief is still pending — on the right of the transcript row
  you then see only a 3–5 sentence summary plus date/contact/round. “🧠 Analyse” (skill
  `gespraech-debrief`) replaces the same report with the full version with findings — the file name
  stays stable, no second document is created.
- **Create the round straight from the transcript:** In the assignment selector, next to the
  rounds already recorded, there is a **“+ Add new round…”**. This means you no longer have to
  leave the dialog if the interview has not been recorded yet — number and type appear as two small
  fields (pre-filled with the next free number), and the round is only created on saving.
  It takes the conversation partner and date from the form, and the status is “Completed”.
  The interview types are HR screen, **Headhunter screen**, Technical interview, Hiring manager, Panel, Final
  and Other — the number of rounds is not limited. The **Counterpart** field (Recruiter /
  Hiring manager / Department / Headhunter / Other) fills itself in to match the type
  and stays editable; it is the measure by which the overall-process evaluation splits the conversations.
- **Recipient-friendly file names:** CV = `CV_MaxMustermann_<company>_<position>_DE|_EN`, cover letter =
  `CoverLetter_MaxMustermann_<company>_<role>_DE|_EN` (language suffix always set) — both as `.docx`
  AND `.pdf`. Company and role appear shortened (section 6). PDF creation runs via **LibreOffice** headless (no window, no macOS approval).
- **Clean layout:** In every generated CV file, a section that would otherwise be torn across two pages
  starts automatically on the next page, and the **footer** says
  “Max Mustermann · Page X of Y”. This applies to all documents generated from now on, without you having to do anything.

### 📧 Inbox
All application-related emails: **category** (acknowledgement/invitation/rejection/query/offer),
direction (↙ in / ↗ out), assigned company/job, **response time** and **“needs reply”** flag.
The header shows Ø response time. Gmail is only **read** — nothing is sent or labelled.

**Assigning emails without a job:** If the Gmail check finds no company/job (e.g. a
rejection with no recognisable reference), the email still lands in the Inbox — with the badge **“⚠ No
job”** and a KPI tile of its own at the top (clickable = filters by it). Expand the row → **“📎 Assign
to job”** opens a search against the existing records; clicking a result assigns it (including a retroactive
response-time calculation). If the job does not exist yet: **“+ Add job”** opens “Add a new job”
with company/note pre-filled from the email. If the URL, or the same company with the same title, is already
recorded, the form warns you and links the existing job; deleted jobs do not count here.
After assigning, for a rejection/offer/
invitation the system suggests the matching job status — it is only changed if you confirm. With **“🔓
Unassign”** a wrong assignment can be undone at any time.

**Archiving emails without a job:** If an email without a job no longer needs assigning,
for example an advertising or info email with no application reference, you hide it with **“Archive”**
(row under the “⚠ No job” badge, or expanded under the assign field: **“🗄
Archive”**). There is no confirmation prompt. The action can be undone at any time via the archive.
Archived emails disappear from the Inbox, from the email count in the dashboard
and from the daily digest. **“🗄 Archive”** below the table still shows them, with **“↩
Restore”** per row. In Gmail everything stays unchanged, nothing is deleted or
moved there. Assigned emails cannot be archived. Unassign them first. If
you later assign an archived email to a job, the system automatically takes it out of the
archive and back into the Inbox.

### 🌐 Network
Three tabs, all **maintainable in the app**: **Target companies** (with tier/scenario, “+ Add target company”,
click a row = full editing), **Headhunters** (“+ Add headhunter”, website field, click a row
= edit), **Network contacts** (create/edit, due-date pill on an overdue
next action). The “Careers check”/cached URL fields on target companies and headhunters are maintained
by the sweep skills automatically; they cannot be edited by hand. In the inline edit form of each of the
three lists there is a **🗑 Delete** button: The entry disappears from all lists immediately
and is no longer checked by sweeps and searches. Deleted entries are collected in the **🗑 Bin**
under the respective list, where you bring them back with **“↩ Restore”**. If you create
a deleted entry again with the same details, the old one is reactivated automatically.

#### Importing lists from a file

In all three tabs, next to the create button, there is **“⇪ Import from file”**. It lets you create many
entries at once, from a CSV or Excel file. You can repeat this at any time, even with
a file that already contains existing entries.

**Procedure:**
1. Open the tab and click **“⇪ Import from file”**. The import area opens below the buttons.
2. Click **“Choose file”** and load the file. BMS reads it immediately and shows a
   **preview**. Nothing is saved at this point.
3. Check the preview: detected columns, counters and the table of rows (explained further down).
4. Click **“Import”**. The button says what will happen, for example “Import (12 new, 3 to update)”.
   BMS first creates a backup and then writes all rows in one go. Afterwards the
   import area says “✓ 12 created, 3 updated”, and the list shows the new entries. **“Cancel”**
   closes the import area without changing anything.

**Files and templates:** BMS reads `.csv`, `.txt` and `.xlsx`. For CSV it detects the separator
(semicolon, comma, tab) and the character set itself. In the import area, under **“Template: CSV ·
Excel”**, you download a template for the respective list. It contains only the header row, and the Excel template
in addition a second sheet “Notes” with the permitted values and date formats for each column. The
template is not required: BMS recognises the columns by their headings, in German or English, in
any order and regardless of upper or lower case. “Firma”, “Company” and “firma”
are the same column. Columns BMS does not know are skipped, and it shows them in the preview
under “Unused columns”.

Only one entry per row is mandatory: for target companies the company, for headhunters the company or the
contact person, for network contacts the name (or first name and last name in two columns).

The **Excel export** of BMS (dashboard) can also be read back in. If an Excel file has several
sheets, BMS reads the sheet that has the same name as the list (“Target companies”, “Headhunter”, “Network”),
otherwise the first. Which sheet it took is shown in the preview.

**Contacts from LinkedIn:** In the “Network contacts” tab you can load the file `Connections.csv` from your
LinkedIn data export. LinkedIn supplies the export as a ZIP archive, which you unzip beforehand. How you
request it is described further down in the “Profile” section. BMS recognises the file by its
column headings (“First Name”, “Last Name”, “Connected On”) and calls it “LinkedIn export (Connections.csv)” in
the preview. What is taken over is the name, the company (“Company”), the role (“Position”) and
the channel “LinkedIn”. Profile address, email address (where LinkedIn supplies it) and connection date
are then in the notes, for example “LinkedIn: https://www.linkedin.com/in/jana-beispiel · Email:
jana@beispiel.de · connected since 12.09.2023”. Relationship, last contact, priority and next action
stay empty.

A LinkedIn export contains all your connections. The “Network contacts” list is meant for
people you actively maintain. Therefore open the file in Excel before the import and delete the rows
you do not want there. Leave the header row in place. You can save it as CSV or as an
Excel workbook (`.xlsx`); BMS recognises the LinkedIn export in both cases.

**The preview** shows what the import would do. Five counters summarise it:
- **New**: The entry is missing from the list and will be created.
- **Updated**: The entry is already there, and the file brings a value for at least one empty field.
  The table names the fields.
- **Unchanged**: The entry is already there, the file brings nothing new.
- **Deleted, skipped**: You deleted the entry in the app. It stays deleted.
- **Errors**: The row cannot be imported, for example because the company or the name is missing. The
  table gives the reason.

For each row the table shows the row number in the file (the header row counts, as in Excel), the
entry, the action and a note. Errors and deleted entries are at the top and are always
shown; of the other rows at most the first 100. Above the table are notes from BMS, for example
on the LinkedIn export or the Excel sheet that was read.

**These rules always apply:**
- **Only empty fields are filled in.** What is already in a field in the app, the import
  never overwrites. An empty cell in the file deletes nothing.
- **The same entry is defined as:** for target companies the company name, for headhunters company and contact person
  together, for network contacts name and company together. Upper and lower case, spaces
  and special characters do not count. Otherwise the comparison is literal: “Muster” and “Muster GmbH” are two
  entries.
- **Entries deleted in the app stay deleted.** The import does not create them again. In the
  **🗑 Bin** under the list you bring them back with “↩ Restore”.
- **Rows with errors are not imported**, all others are. If you correct the file and load
  it again, the rows already imported count as “Unchanged”, and the corrected ones are added.
- **If an entry appears several times in the file,** the first row counts. Later rows at most fill
  in empty fields, and the table points this out (“Duplicate in the file, see row 7”).
- **No automatic due date.** If you create a contact with “+ Add contact” without a date,
  BMS enters “Due date” ten working days later. The import does not do that, otherwise after a
  large import all the new contacts would sit on the same day in the follow-ups. Only a date that is
  in the “Due date” column is taken over. A date there that BMS cannot read stays empty and is reported in
  the table.
- BMS normalises spellings where it is unambiguous: “high” becomes “High”, “email” becomes “Email”,
  “Tier 1” becomes “1”, a lower-case “a” in the scenario becomes “A”. It reads dates as `DD.MM.YYYY` or
  `YYYY-MM-DD`.

**Backup:** If there is something to write, BMS first creates a backup of your database, in the
folder `data/backups/auto`, where “Back up now” also saves. The import area shows its name after
the import. If the backup fails, nothing is imported, and the import area gives the reason. If
a backup is running at the moment, BMS asks you to try again shortly. The import writes everything
or nothing: If something goes wrong while writing, the list stays unchanged. If there is nothing to write
because all rows already exist or are faulty, “Import” is locked, and no
backup is created.

**Limits:** A file may be at most 5 MB in size and have at most 5,000 rows of data
(the header row and empty rows do not count). You split larger lists into several files. BMS does not read the old
Excel format `.xls`: Save the file in Excel beforehand as `.xlsx` or `.csv`. The
header row must be the first row with content, for the LinkedIn export the first row with “First Name” and
“Last Name”.

**Consequences for the search runs:** Imported target companies and headhunters with a website join the
rotation of the target-company sweep and the headhunter search. Because they have never been checked, they come
first: The target-company sweep checks 12 target companies per pass, the headhunter search 15 headhunters.
A long list therefore needs a corresponding number of passes until all entries have been checked once.

### ⚙️ Task Centre — the log of all background runs
Here you see every skill run the app executes in the background (“headless”) — **nothing is started
here**, that happens in **New / Review** (job search & sweeps), in the **job details** (documents workflow,
asking about a job), in **Settings** (coach site) or via the **☀️ daily run button** (sidebar,
reachable from every page).
At the top five tiles: **Total runs · Active · Failed · Spent today · Total cost**.
Below them the filters **“All · Active · Failed”** and the table (Task, Job, Status,
Started, Duration, Cost).

You recognise the state by the status chip: `queued` · `running` · `done` · `failed` (error text
in red under the name) · `cancelled`. Each row has:
- **“Log”** — expands the live output of the run (tools used, subagents, result). The
  log updates every 3 seconds — so you can **watch a run live**.
- **“Cancel”** — only for `queued`/`running`.
- **“Run again”** — ⚠️ starts a **completely new run** of the same skill (does not resume the old one);
  for a chain, only this one step.

As long as something is active, the list refreshes itself every 3 seconds. **Guardrails:** max. 2
runs in parallel, safety cap ~$15 per run, $100 and 100 runs per day; a second run of the same skill
for the same job is rejected. With ChatGPT as the AI there are no costs in dollars and no limit
per run; the limits of your ChatGPT subscription apply. BMS records usage there in tokens. ⚠️ “Total runs” and “Total cost” refer to the
**last 100 runs** — only “Spent today” is a true daily account.

### 💶 Budget — see and cap costs
Two things in one: an overview of all paid services **and** the control panel with which the app
stops itself from spending money. At the top **Today · This month · Annual forecast · Fixed costs / month**,
on the right **“🔄 Sync usage”** (fetches the Apify usage via API; subscriptions such as Claude/Hedy come from
`config/budgets.yaml` and are **never** blocked).

In the **Services** table the status badge shows **“within limits” · “⚠ ≥ 80%” · “over limit” ·
“paused”**. Under **Budget controls** you set the following for each usage-based service:
- Deselecting **“Service active”** = paused → **all** calls are refused, regardless of the limit.
- **Daily limit ($)** and **Monthly limit ($)** — leaving it empty means “no limit”.
- **“hard”** / **“soft”**: hard = calls are **blocked**, soft = runs anyway, warning only.
  The check happens before every paid call (daily limit first, then monthly limit).

⚠️ Two stumbling blocks: The daily limit must **not exceed** the monthly limit (otherwise an error message),
and the starting values are tight at $0.50/day — that blocks quickly. Also, this is **not**
the daily budget of the Task Centre: the agent guardrails ($15/run, $100/day) are environment variables
and cannot be edited here. Spending outside the app only becomes visible after the sync, and the app cannot
prevent it.

### 🏛️ Advisory Board: open questions to the seven members
A menu item of its own, **🏛️ Advisory Board**, in the sidebar, directly under Network. For the question “should I
apply for *this job*?” you use the **Advisory Board check in the job details** (optional building block
“Check job (Advisory Board)” in the “Create documents” card, with a vote and dashboard). This
page is for **open** questions with no reference to a job (e.g. “How do I explain my change of career?”).

Under **New debate** you enter the **topic/question** (required) and optionally context, choose the
**minimum contributions** (6/10/20/30), the **engine** (Claude through your subscription, no key needed; OpenAI only
with a key) and either let the chair choose the members themselves (tick box set, with their name next to it)
or pick at least two members. Who holds the chair is set in **Settings** under the
members of the Advisory Board. **“▶ Start debate”** starts the debate live: The chair calls on the
members by name, the contributions appear word by word, and at the end comes the **📋 Synthesis**.
**“■ Stop (→ synthesis)”** ends it gently: the current contribution is finished, then the synthesis
follows straight away.
**Earlier debates** replays the saved state — that recalculates nothing and costs nothing.

⚠️ Only **one** debate can run at a time (the job check from the job details
counts too). Runs cost money (safety cap $15); **OpenAI costs are not recorded**, so the
budget control does not take effect there. If the live connection drops, reload the page — the
debate keeps running in the server and ends up in the archive. In the Task Centre it appears as
**“Advisory Board debate (free)”**; “Cancel” works there, “Run again” does not (go back to the page
**Advisory Board** for that). You store optional API keys under **“🔑 Keys & engine”**. They are only on
your computer in `~/.bewerbung_beirat/`, outside the program folder.

### 🏢 Companies · 📡 Restructuring Radar
Company database and companies with a fresh restructuring/layoff signal (your build/rebuild radar), respectively.

### 🪪 Profile
Your own candidate profile in one place — the substance that **matching and cover letters**
draw on. From top to bottom:
- **Identity and search strategy** — the first card on the page. Here you enter who you are and
  what you are looking for. The card reads and writes the file `config/profil.md`.
  - **Fields:** Name (required), Positioning (one-liner), Address, Email, Phone, LinkedIn,
    Current, Short profile, Target date,
    Hard constraints and Known skill gaps.
  - **What matters:** Name, address, contact details and LinkedIn make up the letterhead of your
    cover letters and the file names. You write the address as `Straße Nr, PLZ Ort`, for example
    `Musterweg 3, 12345 Musterstadt`. The place line of the cover letters is built from it, and it is the
    starting point of the route planning to interviews. The AI reads short profile, target date and constraints
    as background: the more concrete, the better.
  - **Save** only becomes active once you have changed something. Afterwards it says “✓ Saved”, and
    the sidebar and route planning load the new details. Yellow lines are notes, for example if the
    address is missing the comma or the postcode. It is saved anyway.
  - **Nothing gets lost:** What the card does not know, for example the section “Empirie aus dem
    Bewerbungsverlauf”, which BMS maintains itself, or sections of your own, stays unchanged. The
    previous version of the file goes to the bin (`data/papierkorb/`) every time you save. If
    the file has changed in the meantime, for example through an analysis, the card asks you to reload:
    Click “Reload” and enter your change again.
  - If you like, you can keep editing `config/profil.md` by hand. In that case the spelling `**Name:**`
    must be correct.
- **Reading in LinkedIn — two ways.** The **most complete** is the data export ZIP: LinkedIn →
  Settings → Data privacy → “Get a copy of your data” → **top option “Download larger data
  archive”** (⚠️ *not* the quick option “Profile” — it only contains the positioning). Only the
  large archive brings skills, work experience, education and certifications; LinkedIn needs up to ~24 hours
  for it. The second way works immediately: **“Read profile”**. You paste the text of your profile
  or upload the PDF that LinkedIn creates via “Save to PDF”. The AI structures it, you review the
  suggestion, and only then does BMS add to your profile. There is no retrieval via the profile address;
  LinkedIn blocks it (HTTP 999).
- **Positioning** — large block of prose, freely editable.
- **Skills as chips**, grouped by topic area. You add new skills in one line
  (enter the name + choose or create an area). **Imported skills sort themselves in:**
  after every ZIP import with new skills, a background run starts automatically
  (visible in the Task Centre) that assigns everything from the collection group “LinkedIn (unsortiert)” to a suitable
  area — preferably an existing one. It **only moves**: invents nothing, renames
  nothing, does not touch anything already sorted.
- **Career history** — roles, education, certifications as editable blocks.
- **Certificates and references** — attach, open, delete files (→ bin).

Both import ways are **additive and non-destructive**: they only fill empty fields and append,
and never overwrite anything you have maintained yourself.

**On a new installation** you first remove the sample data (section 1), then fill in the
“Identity and search strategy” card and import afterwards. If the sample data is still in the profile,
the import does not take over your positioning, because the field is already filled, and it skips
skills that are already there as examples, such as “Deutsch”. They would then disappear with the
sample data.

### 🎯 Settings
Here you set the **basic parameters of your job search** yourself, instead of editing configuration files
by hand:
- **Search area & company size** — three switches **Remote · Germany-wide · City + local area**
  (with a city field and a km figure) as well as the **minimum number of employees** of a company. The local area
  appears as a filter tab of its own, “<city> +<km>km”, in the jobs list; if you change the city or
  radius, BMS automatically switches existing jobs to the new label.
- **Email account**: choice of provider **IMAP (recommended default, also for Gmail) or
  Gmail (API)** (power option, own Google Cloud project). Which route suits what and the
  step-by-step setup are in `docs/SETUP-EMAIL.md`.
  IMAP covers Gmail, GMX, Web.de, mailbox.org, Posteo and iCloud Mail — in each case with the
  app password from the provider. IMAP needs
  host/port/security (SSL/STARTTLS), username, password and the name of the drafts folder;
  **Test connection** checks login and folder, and it is saved to the secrets directory
  (`~/.bewerbung_mgmt_secrets/mail_settings.json`, never in the DB or iCloud). In both cases it is
  **never sent** — only read, and drafts saved. Outlook.com/Microsoft accounts are currently
  not supported for lack of IMAP basic auth.
- **Sample data**: only on a fresh installation, right at the top of the page. The card
  names which sample data from Benno Bewerbaer is there, and removes it with “Remove sample data”
  and a confirmation. Beforehand BMS creates a backup. What happens is described in section 1
  under “On the very first start: sample data”. Afterwards only the small line “Sample data
  removed on …” remains.
- **AI**: Here you choose whether the AI runs use **Claude** (default) or **ChatGPT**, and
  you see whether the program of the respective AI is installed and signed in. ChatGPT is a preview:
  The runs without email are tried and tested, the email runs and the daily run not yet. The contents of the runs then go to OpenAI instead of Anthropic. There is no
  budget limit per run there, the limits of your subscription apply, and many runs in a row can bring a Plus account to its limit. For ChatGPT you need the program Codex CLI
  (`npm install -g @openai/codex`, on the Mac also `brew install --cask codex`) and, once, signing in
  with your ChatGPT account in the terminal: `codex login`. You can check it with `codex login status`; it
  should show “Logged in using ChatGPT”. You do not need a key to paste in or the file `agent.env`
  for this. There is no Gemini, because Google’s rules do not allow the subscription in apps.
- **AI model per function**: For **Job search · Company fit · Advisory Board · CV match · ATS scan ·
  Cover letter** you choose **Opus 5.5**, **Sonnet 5.5** or **Haiku 4.5** in each case; the default is
  Sonnet 5.5 everywhere. That way you use the stronger model specifically where it pays off. **Fable**
  is deliberately not available, because it is too expensive: It costs two and a half times Opus 5.5
  and five times Sonnet 5.5. If you had chosen it earlier, the function now works with
  Sonnet 5.5, and Settings shows it that way. ⚠️ The choice applies to runs you start
  **via the app buttons or the Task Centre**. If you type a skill by hand in the
  Claude session, the model set there still counts. Runs without a choice of their own, such as
  Email check, conversation analysis and rejection analysis, always run with Sonnet 5.5, not with the
  default model of your Claude installation. If you have chosen ChatGPT, the models of ChatGPT are offered here instead of Opus, Sonnet
  and Haiku. The level for each function is kept when you switch AI.
- **Three plan cards A / B / C** — each with a freely nameable label, an active switch and chip lists
  for **Titles · Level · Industry**. The job search works through the plans in the order
  **A → B → C**. Plan C is new (previously there were only A and B) and accordingly also appears in the
  selection fields in the job details, under “Add a new job” and in the Excel export.
- **Backup**: shows the last automatic backup (time, size) and their
  number, with a switch for the daily automatic backup, fields for retention (daily/
  weekly/monthly backups) and the “Back up now” button. An amber notice appears
  for a failed backup or if the last one, with automatic backup switched on, is older
  than three days (also on the dashboard). Restoring: section “Backup” further down
  in this guide.
- **Program version**: last card, shows the installed version (or, for a
  Git installation, the development state) and what has changed in this version. The button
  **“Check for updates”** asks GitHub for the latest version. The result names the
  version with date and changes and links to the page on GitHub, or it says that your BMS
  is up to date. It only checks when you click the button, never by itself.
  GitHub receives the IP address of your computer in the process, nothing else. The card installs nothing.
  You fetch and install a new version with BMS quit, via `update.command` or
  `update_windows.bat`: The tool downloads it from GitHub itself and checks the package. Beforehand it says
  that GitHub receives the IP address, and only your start triggers it. With `--offline` it does
  not search online, but it still finds a ZIP file `BMS_<version>.zip` in the “Downloads” folder.
  Details are in `BMS_Install_MAC.en.md` or `BMS_Install_Windows.en.md`, section
  “Installing updates”. The same version is shown at the bottom of the sidebar, the changes of
  all versions under **📖 Documentation**, on the “Version” tab.

When saving, the app rewrites `config/suchprofile.yaml` automatically — but **only** the upper,
managed block; all the hand-maintained technical parameters below it stay untouched. The database
is the truth, the file only the view, which all skills keep reading unchanged.

**Coach site:** a card of its own at the end of the page with its own storage location (not the
`suchprofile.yaml`). It contains an on/off switch, the **address of the site**, the
**SFTP access** (host/username/password/target directory), the **server path to the access file**
(field + button “detect automatically”) and the **coach login** (own username/password for
your coach).
“Test connection” checks the SFTP details in advance; only when it is activated AND completely saved
does the button **“Update coach site now”** appear — the same export also runs
automatically as the last link of every daily run. Result: a password-protected, read-only
mirror of your application status for an external coach — overview, active applications, screening/
review (including the job posting) and rejections with reasons; **guaranteed never** visible: emails,
Notes & history, Advisory Board checks, salaries, network/contacts, budget. Step-by-step
setup (also for non-developers): `docs/ANLEITUNG_COACH_SITE.md`.

### 📖 Documentation
All texts about BMS in one place, in tabs, without leaving BMS. The texts are on
your computer; nothing is loaded from the internet. The tabs:
- **Version**: what has changed in each version, the newest at the top. Above it is shown which
  version is installed on your machine.
- **Features**: a short overview of what BMS can do, arranged by work step.
- **User guide**: this text.
- **Installation & updates**: the installation guide with the procedure for updates and for
  backup.
- **Email setup**, **Windows**, **Coach site** and **Advisory Board** (the rules of the Advisory Board): the
  individual guides.

“Open in new tab ↗” above the text opens the chosen text in a browser tab of its own, for example
for printing. Web addresses in the text always open in a new tab.

### ⚖️ Legal
“About this program” (publisher, licence, liability, note on the AI), the wording of the open-source licence (Apache
License 2.0), notes on privacy (which data BMS sends where) and the licences of the
open-source components that BMS installs along with it.

---

## 4. The status values
| Status | Meaning | Where visible |
|---|---|---|
| **New** | Fresh result, not yet reviewed | Review, Pipeline |
| **To review** | Accepted, being actively worked on | Pipeline, Jobs |
| **Applied** | Application sent | Pipeline, Funnel |
| **Interview** | Conversation scheduled (often via Gmail check) | Pipeline |
| **Offer** | Contract/salary offer | Pipeline |
| **Rejected** | Rejection received | Pipeline |
| **Rejected by board** | The Advisory Board voted red (“Check job (Advisory Board)” in the workflow card) | archived |
| **No match** | Discarded, kept for duplicate checking. A new posting of the same job (different link) appears again as “New” with the note `NEUAUSSCHREIBUNG?` | archived |
| **Not available** | Job offline/expired | archived |
| **Parked** | Look at again later | archived |

**Target-role fit 1–5:** 5 = situation **and** function **and** region fit; 1 = marginal result.
Situation is the most important filter (BUILD/CARVE-OUT/POST-MERGER/PE/SCALE-UP = plan A core).
Every rating comes with a **rationale with evidence** (quote from the posting) — if that is not
there, the number is worthless. The rating scheme itself is in `config/scoring_rubrik.md`.

**Do not confuse the three ratings** — they measure different things:

| Rating | Scale | What is compared | Where |
|---|---|---|---|
| **Target-role fit** | 1–5 | the **job** against your **target profile** (situation · function · region) | Jobs list, dashboard, job details |
| **CV match score** | 0–100 | your **CV** against the **posting** (keywords, evidence, gaps) | Job details → match dashboard after “CV match” |
| **ATS score** | 0–100 | your **CV** against the **applicant tracking robot** (readability, degree of optimisation) | Job details → ATS scan after “Create CV” |

The target-role fit decides **whether** you deal with a job at all; the other two,
**how good your documents are for it**.

---

## 5. Your daily routine
1. **In the morning: start the daily run.** The round **☀️ button** at the top left of the app opens a dialog with
   the steps (search jobs → email job search → target-company sweep → headhunter search → applied-jobs check →
   check inbox → rejection analysis, once a week → refresh views → coach site, if
   set up) and shows the last run.
   “▶ Start daily run” makes the app run the chain **itself**, headless in the background — you
   see progress there or in the Task Centre. Prefer the classic way? The collapsible item “Start in the
   Claude session instead” copies the trigger “Daily run” to your clipboard instead.
2. **Open the app** → **New / Review**: sort through new results (Accept / Discard).
3. For accepted, genuinely interesting jobs: in the **job details** work through the “Create documents” card
   step by step (company fit → Advisory Board → CV match → *edit draft* → create CV
   → cover letter). “**Deep dive for job <id>**” does company + CV in one go — without the Advisory Board step.
4. Application sent → drag the status in the **job details** or **Kanban** to **“Applied”**.
5. Check the **Inbox**: invitations/rejections arrive automatically; work through the “needs reply” emails.
6. Go through the **Follow-ups**: chase overdue jobs (✉️ chip), prepare for upcoming conversations,
   get to due network contacts.
7. Keep an eye on the **Dashboard** (funnel, response rate), and maintain the **Network**.

---

## 6. Exports & naming convention
- **Excel status report** and **Daily digest** (dashboard buttons) — always freshly
  generated from the DB. The Excel export is a status report with eleven sheets: dashboard cockpit (KPIs as
  on the web page), Funnel, jobs **grouped by status** (with fit/Match-100/ATS/Advisory Board and a
  clickable source link), Applications, Discarded, References, Contacts, Network, Headhunter,
  Target companies, Outreach. For rejections and discarded jobs the “Next step” in the export is
  deliberately empty (old calls to action would be misleading — they are kept in the app).
- The **Applications** sheet shows every job you applied for in one row: company,
  title, fit, Match-100, ATS, when found, when applied, the date of each interview round
  (round 1 to 6, as you record the rounds in the job details) and the rejection date. The newest
  application is at the top. If an interview has no date, BMS takes the date of its transcript;
  if there is none, the cell stays empty and carries a comment. Cancelled interviews are missing. The
  rejection date is the day of the rejection email, without an email the day the job went to “Rejected”.
- Generated files begin with the date in the form **`YYYYMMDD_`** (for example `20261001_`), so that
  they sort chronologically.
- **Report style:** newly generated reports (match, ATS scan, briefing, posting copy, rejection analysis,
  analysis of a conversation, Advisory Board) look uniform (a shared design, static HTML) and
  are internally named `YYYYMMDD_<type>_<company>[_<role>]`. The type words are deliberately short: `Anzeige` for the
  copy of the job advertisement, `Auswertung` for the report on a conversation, `Beirat` for the
  Advisory Board check of a job. An example: `20261001_Auswertung_Beispiel_Software_Director_Beratung_R2.html`.
  Company fit has **no** role part; every new check deliberately creates a new, dated file.
  CV and cover letter keep their recipient-friendly name (see above).
- **Short names:** Company and role are shortened in the file name. For the company, legal forms
  (such as GmbH or AG) and additions after a comma, colon or bracket are dropped, and the rest is limited
  to 25 characters at a word boundary. For reports the role is limited to 30 characters, for CV
  and cover letter to 35. The full name is still in the app and in the document itself.
- **Older files:** Files from earlier versions are still named `YYYY_MM_DD_…` with the long
  type words. They remain fully usable, and BMS recognises both spellings of the date, also in
  the bin.

---

## 7. Deleting & the bin
Deleting in the app is **always reversible** — there is no delete command that permanently
removes anything. Three kinds of deletion, all with a confirmation dialog:
- **Individual files** (job details → “Files & documents”, 🗑 icon): whether your own upload
  or a generated artefact (company fit, CV, match/ATS dashboard, cover letter, briefing,
  transcript report) — the file moves to the central bin `data/papierkorb/`, the
  associated field in the DB is cleared. For the company fit entry the dialog warns: it belongs to the
  **company**, not the individual job, and thereby disappears from all its jobs.
- **Delete job** (job details → bottom of the Key facts card “🗑 Delete job”): all
  artefact files of the job (snapshot, CV, cover letter, briefings, transcripts including debrief/
  report) move to the bin; interviews/transcripts/application/notes history are
  removed. **Emails are kept** (mailbox history/response rate) — only the link to the
  job is removed. The job itself disappears from all lists (Jobs/Review/Dashboard/
  Follow-ups/Search), but stays internally as invisible duplicate protection — if the same
  result shows up again in a future job search, it is skipped automatically instead of being created
  anew. If an old link (e.g. from the Task Centre) calls up the deleted job, the page
  opens anyway (no dead link) instead of an error message.
- **Delete company** (Companies table, 🗑 icon): only possible if **no** active jobs remain
  at the company — otherwise the app shows an understandable message with the list of jobs that have to be
  deleted first. Without active jobs: company fit file to the bin, contacts
  of the company are removed, emails stay (only decoupled).
- **Bin** (`data/papierkorb/`): never empties automatically. Permanent removal is a matter
  for a separate cleanup run or manually by you — the app itself never hard-deletes.

**One exception:** “Remove sample data” (Settings) deletes the sample rows in the
database permanently; they do not end up in the bin. For that, BMS creates a backup beforehand
(section 8), and files from it move to the bin as above.

**System cleanup (`backend/pipeline/cleanup.py`, manually in the terminal, ~monthly):**
a deterministic command (no LLM) that finds what the app does not touch itself — orphan
files without a DB reference, dead DB paths, ageing logs/exports/DB backups, emptying the bin:
- `cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.cleanup scan` — changes NOTHING,
  prints a report and writes `data/analysen/YYYYMMDD_Analyse_Cleanup.html`.
- `... pipeline.cleanup apply [--ja] [--fix]` — moves orphans + old files (>60 days,
  configurable via `--rotate-days`) to the bin (never permanently); with `--fix` dead DB path
  fields are also nulled. Always asks before executing (except with `--ja`).
  Backs up the DB automatically beforehand.
- `... pipeline.cleanup leeren --older-days N [--ja]` — the ONLY command in the whole system that
  deletes permanently (only bin contents older than N days, N must be ≥ 30, nothing happens without
  it). Never runs automatically; the daily run only reports conspicuous `scan` figures.

**When a report looks odd (colours missing, everything grey):** The dashboards carry their CSS
in every file themselves. If a run leaves out rules in the process, the content stays correct, but the
colours disappear, for example grey instead of green and red keyword chips in an ATS scan. The check
finds this in seconds, changes nothing and costs nothing:
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.report_check ../data/company_fit/*.html
```
It tells you exactly which rule is missing in which file — adding it is enough, and the expensive skill run
does **not** have to be repeated for that. After every ATS scan the check runs automatically;
the command is only for the case that you notice something on an older report.

---

## 8. Backup

BMS backs up your database automatically while it is running: once a day as a ZIP file in the
folder `data/backups/auto`. What is kept is the newest backup, all of the last 24 hours,
and one each of the last 7 days and the last 4 weeks. BMS removes older automatic backups
itself. Settings → **“Backup”** shows the last backup, lets
you change the retention and create a new one by hand with **“Back up now”**. “Remove sample data”
(section 1) and the import of a network list (section 3, “Network”) also create
such a backup beforehand.

These backups are in the BMS folder on the same hard disk as your working copy. They
do not replace an external backup such as Time Machine. Also include the BMS folder in your
regular backup.

This is how you restore a backup, on the Mac as on Windows:

1. Quit BMS: double-click `stop.command` (Mac) or `stop_windows.bat` (Windows).
2. Double-click `wiederherstellen.command` (Mac) or `wiederherstellen_windows.bat`
   (Windows) in the BMS folder. The tool shows you the available backups, the newest
   first, with date, time, type and size.
3. Type the number of the backup you want and confirm the query with “j” (German for yes). Pressing Enter
   without typing anything cancels. The tool checks the backup before it changes anything, and first
   creates a backup of your current state.
4. Start BMS as usual.

Good to know:

- **Only the database data comes back.** Everything you recorded or changed since the time
  of the backup is no longer in the database afterwards. Your documents in `outputs`
  and `data` stay unchanged. Files created after the backup then
  belong to no job any more.
- **Undoing:** Your state before the restore is in `data/backups` as the backup “vor Wiederherstellung”
  (“before restore”). Start the tool again and choose this entry, and everything is as
  it was before.
- **Which backups appear:** the automatic ones from `data/backups/auto`, those created by
  hand in `data/backups` and the entries “vor Wiederherstellung”. The backups that an
  update creates are not included. You undo an update with `update.command --zurueck` or
  `update_windows.bat --zurueck`.
- **If BMS is still running,** the tool aborts and tells you so. Quit BMS and start the
  tool again.

If the tool does not start, it can also be done by hand: quit BMS, unzip the desired ZIP file in the folder
`data/backups/auto` (Mac: double-click, Windows: right-click and
“Extract All”), rename the existing `data/bewerbung.sqlite` instead of deleting it, for example to
`bewerbung_alt.sqlite`, put the unzipped `bewerbung.sqlite` in the folder `data` and start
BMS.

---

## 9. Limits (deliberately so)
- **No auto-applying**, no automatic sending.
- **Email: read + drafts only** — scopes `readonly` + `compose` (Gmail) or IMAP without SMTP;
  there is **no send code path** (anchored by a test), never send/label.
- **CV tailoring is truthful** — no invented skills/figures; keywords not covered are named honestly.
- **Automation** (time-controlled) is prepared but not active: You start the daily run with the
  press of a button (section 5).
- **Application languages** — CVs and cover letters are produced in German, English, French, Italian, Spanish or
  Portuguese, depending on the language of the job posting. For this you need a base CV per language (Profile page).
  If it is missing for French, Italian, Spanish or Portuguese, the system translates nothing, takes the English
  (otherwise the German) version and says so in the run's report; the job page does not show it. Portugal and
  Brazil share one version. The mailbox search knows words in these languages but has not yet been checked with
  real emails.
- **Job search outside Germany** — The preset portals are aimed at Germany; in the check, the search found hardly any
  jobs in France, Italy and Spain. Use the two free portal rows, LinkedIn alerts and your target companies there.
  Some portals do not deliver the posting text in readable form, France Travail for example, where BMS can mistake the
  page's other offers for the posting text: Check the text in the job detail before you create documents.
