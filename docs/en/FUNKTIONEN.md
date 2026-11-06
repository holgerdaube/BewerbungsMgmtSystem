# Features

The BMS – Job Application Management System runs on your computer, finds suitable jobs, rates them and prepares your documents. You decide: the BMS never applies for you and sends nothing without your action.

The BMS is free and open source under the Apache License 2.0. It needs no licence file: all features are available to you from the start.

## Finding and rating jobs

- **New / Review**: “Job search (WebSearch)” searches the portals for your target roles and adds results as “New”. You set what is searched for in **Settings**.
- Each job gets a target-role fit from 1 to 5, with a reason and evidence from the posting. You accept results or discard them.
- You also start Target-company sweep, Headhunter search and Applied-jobs check (checks whether the jobs you applied for are still advertised) on **New / Review**. The **Daily run** button in the sidebar runs all of them in turn, including the mail job search and the email check.
- **Jobs** lists all results with filters, **Pipeline** shows them as a kanban board, **Search** searches them in full text. You record your own finds with “+ Add job”.

## Checking companies

- “Check company fit” in a job's “Create documents” card examines the business model, competitors, the consequences of AI for the market and employer ratings, and assesses the role's influence on the company.
- “Research decision-makers” in the “Contacts” card searches public sources for the functional decision-makers instead of the HR department.
- **Companies** lists your companies, the **Restructuring Radar** those with a fresh restructuring or downsizing signal.

## CV and cover letter

- **Profile**: Here you maintain positioning, skills, career history and references, and upload your base CVs as a Word file, in German and English. A LinkedIn data export pre-fills skills and career history. The “Identity and search strategy” card at the top of the page takes your name, address, contact details, short profile, target role and constraints: they make up the letterhead of your cover letters and the background for the AI.
- “CV match” compares your CV with the posting and creates a match dashboard and a tailored draft. The BMS invents nothing and names requirements that your CV does not support.
- You edit the draft in the text window. “Create CV” produces Word and PDF and uses an ATS scan to check whether application systems can read the CV.
- “Generate cover letter” writes a cover letter for exactly this company. You then edit the text yourself, “Create Word + PDF” produces the files.
- “Application package” does company fit, CV and, if you wish, the cover letter in one go.

## Mailbox

- **Inbox** shows application-related emails with category, response time and a note on what you should reply to. You assign emails without a job by hand or archive them; your mailbox stays unchanged.
- The “Email check” on **New / Review** reads your mailbox for responses to applications. The mail job search in the daily run reads jobs from job alerts.
- You connect the mailbox in **Settings** in the “Email account” card, via IMAP (Gmail too) or via the Gmail API.
- “Draft reply” saves a draft for an incoming email in your mailbox. You check and send the draft yourself; the BMS never sends an email.

## Preparing for and following up on conversations

- In the “Interviews & conversations” card you record appointments. “Prepare interview (briefing)” creates likely questions with answer sketches from your CV and questions for the company.
- **Follow-ups** shows upcoming conversations with briefing and route (Google Maps) as well as due steps and network actions.
- After the conversation you paste in a transcript or upload a text file. “Analyse” shows what went well, what was shaky and what remains open.

## Network

- **Network** holds three lists that you maintain in the app: target companies, headhunters and network contacts. Target-company sweep and Headhunter search check the first two in turn for suitable jobs.
- With “Import from file” you add many entries at once to each of the three lists, from a CSV or Excel file. You download a template in the import area; the BMS recognises the columns by their headings. For network contacts it also reads the file `Connections.csv` from your LinkedIn data export. A preview shows beforehand what will happen. The import only fills in empty fields of existing entries and never overwrites anything; the BMS backs up your database beforehand.
- For contacts you enter the next action with a due date; anything overdue appears under **Follow-ups**.
- You record conversations with headhunters directly on the entry; they count in the key figures on the **Dashboard**.

## Advisory Board

- “Check job (Advisory Board)” in the “Create documents” card has seven fictional board members with different areas of expertise assess the job. The result is a traffic light with a dashboard; if it is red, you can set the job to “Rejected by board”.
- For open questions without a job there is the **Advisory Board** in the sidebar. The board members debate there live, the chair closes with a synthesis.
- In **Settings** you replace one of the seven seats and decide who chairs. The Advisory Board's rules are under **Documentation**, “Advisory Board” tab.

## Overview and costs

- **Dashboard**: It shows key figures on jobs, applications, response time and response rate, plus a funnel from screening to interview. “Excel export” and “Daily digest” output the current state as a table and as a report.
- **Task Centre**: It logs every AI run with status, duration and cost estimate. You watch a run live, cancel it or restart it. The runs go through your own account with Claude or ChatGPT.
- **Budget**: It shows what paid services use and limits them with daily and monthly limits. A hard limit blocks further calls, a soft one only warns.
- In **Settings**, “AI” card, you choose whether the AI runs use Claude (default) or ChatGPT. ChatGPT is a preview: the runs without email are tested, the mail runs and the daily run not yet. The content of the runs then goes to OpenAI instead of Anthropic, and there is no budget limit per run; the limits of your subscription apply.
- In **Settings** you choose the AI model for each function: Opus 5.5, Sonnet 5.5 or Haiku 4.5 (with ChatGPT, the ChatGPT models). Sonnet 5.5 is preset.
- The **coach site** (Settings, “Coach site” card) shows your coach the current state on a password-protected web page, read-only and without emails, notes, salaries and contacts. You need your own web space for it. It is not available on Windows.

## Backups and updates

- The BMS backs up your database automatically once a day while it is running. In **Settings**, “Backup” card, you see the last backup and back up by hand with “Back up now”. This does not replace an external backup, for example with Time Machine.
- You restore a backup with the BMS closed, using `wiederherstellen.command` (Mac) or `wiederherstellen_windows.bat` (Windows). The tool first backs up your current state, so you can undo the restore with the same tool. It affects only the database; your documents stay unchanged.
- In **Settings**, “Program version” card, the “Check for updates” button asks GitHub for the latest version and shows what changes in it. This happens only when you click, and GitHub receives your computer's IP address. The button installs nothing.
- You install new versions with the BMS closed, using `update.command` (Mac) or `update_windows.bat` (Windows). The tool downloads the new version from GitHub itself and checks it; without internet, the ZIP file `BMS_<Version>.zip` in the “Downloads” folder is enough. A backup is made beforehand, and if there is an error the tool undoes everything.
- The installed version is shown at the bottom of the sidebar, the changes in each version under **Documentation**, “Version” tab.

## Sample data and documentation

- A new installation starts with sample data for Benno Bewerbaer, a fictional person with five years of experience in parcel delivery: jobs, companies, emails, profile and base CV.
- Remove the sample data in **Settings** with “Remove sample data” before you enter your own data. The BMS makes a backup automatically beforehand. Your own entries are kept.
- All guides are under **Documentation** in the sidebar.

The [user guide](ANLEITUNG.html) describes each area in detail.
