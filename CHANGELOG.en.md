# Changes

Here you will find, for each version, what changes for you. You can see which version is installed at the bottom of the sidebar and in Settings under “Program version”.

## Unreleased

## 2.2.1 (06.11.2026)

- Each release now also carries the program package under the fixed name `BMS_latest.zip`, with its checksum. The download link on bms.daube.tech therefore always points to the newest version. Nothing changes for installing and updating.

## 2.2.0 (06.11.2026)

- BMS is now available in German and English: interface, messages, reports, exports, sample data and documentation. You can switch in the sidebar or in the settings. The AI reports follow this setting; your CV and cover letter still follow the language of the job posting.
- CVs and cover letters are now also produced in French, Italian, Spanish and Portuguese if the job posting is in that language and you have uploaded a matching base CV. If it is missing, BMS takes the English, otherwise the German version, translates nothing and says so in the run's report. Footer, date and closing follow the language of the document, and accented letters stay in file names as their base letter (`Société` becomes `Societe`).
- In English cover letters the date now reads `3 November 2026`.
- Closed postings, sign-in pages, gender suffixes, legal forms and work models are also recognised in these four languages. The mailbox search also looks for words in these languages as soon as you have a base CV or a running application there.
- New installations start without a minimum seniority in the search profile. An existing value stays.
- Messages in the terminal (update, start, stop, restore, server window) follow the language of your system: German on a German system, English on any other.
- The project's page on GitHub is now in English, with a German version one click away. The README in the program package is in both languages.
- The Network, Companies and Radar pages have a search box at the top that narrows the list as you type.
- On English, the Advisory Board also shows the titles of earlier German job checks in English. The content of earlier debates can be translated with `python -m pipeline.beirat_uebersetzen`, and the originals are kept.
- In the Task Centre, the tiles now count all runs. Until now “Total runs”, “Failed” and the costs stopped at the last 100. The list still shows the last 100 and says so, and the “Failed” filter now also reaches further back.
- Company check, CV match, create CV and cover letter now report an error if the run ends without creating its result. Until now they counted as successful.
- In the daily digest, “Changed today” now also shows changes made shortly after midnight. Until now they were missing all day; in Germany that affected the first one to two hours.
- Gmail messages whose sender declares an older character encoding (such as Outlook with ISO-8859-1) now arrive in the mailbox check with correct umlauts and accents. Until now they showed “Ã¤” instead of “ä”, which could make such replies harder to classify.

## 2.1.0 (02.11.2026)

- BMS now runs with either Claude or, as a preview, ChatGPT. You make the choice during installation or under “Settings” on the “AI” card. With ChatGPT, BMS uses your ChatGPT subscription through the Codex command line (`codex login`), and the contents of the AI runs go to OpenAI instead of Anthropic. There are no costs in USD and no budget limit per run there; the limits of your subscription apply. If you use Claude, you do not need to do anything.
- Skills are freed from assumptions about a specific occupation and skip optional files instead of aborting.
- Taking over your LinkedIn profile now works immediately: Under “Profile”, you paste the text of your profile or upload the PDF that LinkedIn creates with “Save to PDF”. Your AI structures the text, you check the result in a preview, and only then does BMS add to your profile. The previous “Import profile” button that worked from the address is removed, because LinkedIn blocks such requests. The data export remains the most complete route.
- The “Target role” block on the Profile page is removed; it duplicated the search plans. You enter title, level and industry under “Settings”, and the target date stays on the Profile page. Existing entries in your profile file stay in place. If they differ, the search plans apply.
- Security: Bundled components have been updated, including `certifi` (root certificates), `urllib3`, `cryptography`, `oauthlib` and `pyasn1`, as well as React Router and Vite in the interface. The update installs them automatically, so it may take a little longer.
- When you add a job by hand, BMS now warns you while you are filling in the form: “URL already recorded in job …” or “Job already recorded”, with a link to the existing job. The URL is compared without tracking additions, company and title also in a different spelling, for example without legal form or “(m/w/d)”.
- Deleted jobs no longer count as existing when you add a job by hand: You can record a deleted job again by hand. The automatic search still does not bring it back by itself.
- The level now includes all the usual stages, from intern, working student, apprentice and trainee through entry level, employee, experienced professional and expert to C-level. This applies to the “Add a new job” form, the key facts of a job and as suggestions in the search plans.
- In the base CV, Portuguese is now directly in the language selection.
- The sample data of a new installation now belongs to Benno Bewerbaer. Existing sample data stays as it is and can still be removed.
- The installation guides now call the “Check company fit” button what it is called in the program.

## 2.0.0 (01.11.2026)

- Under “Legal”, web addresses can now be clicked, for example the link to the source code on GitHub in “About this program” and the one to GitHub's privacy statement. They open in a new tab.
- Windows: The installation guide now suggests the folder `BMS` in your user folder (`%USERPROFILE%\BMS`, as on the Mac) instead of in the Programs folder. There, other user accounts on the computer cannot read your data and CVs, and creating it no longer needs administrator rights. An existing installation stays where it is.
- Windows: The BMS window stays visible after start-up. Before, it could disappear after a second; then BMS could only be ended through Task Manager. If the server ends with an error, the window stays open with the message.
- Windows: `stop_windows.bat` now also finds the running BMS on a German Windows and asks again before it cancels running agent runs.
- The installation guides check the access key more closely: If the example `sk-ant-oat01-...` stays in the line, the check now reports “missing” instead of “present”. On Windows, the guide finds the real “Downloads” folder, even if OneDrive redirects it, checks the Windows version and architecture, and explains the prompt “Batchvorgang abbrechen (J/N)?” when you quit.

## 1.9.0 (29.10.2026)

- BMS is no longer sold but is open source under the Apache License 2.0 (files `LICENSE` and `NOTICE` in the program folder). Under “Legal” there are now “About this program” with publisher and disclaimer, the full text of the licence, privacy and the third-party licences. Terms of use (T&Cs/EULA), right-of-withdrawal notice, sales checklist and the imprint in the app have been removed; the imprint is on daube.tech.
- BMS no longer needs a licence. All functions are available to you without a licence file; searches, AI evaluations and changes are never locked any more. The restriction to viewing and exporting without a licence, the band above the pages and the “Licence” card in Settings no longer exist. An existing licence file (`lizenz.json`, and possibly `lizenz_stand.json` in the `.bewerbung_mgmt_secrets` folder in your user folder) is no longer needed. You may delete it; BMS does not delete it by itself.
- New in Settings, card “Program version”: the “Check for updates” button. It asks GitHub for the latest version and shows whether there is a newer one, with date, changes and a link to the page on GitHub. It only asks when you click it. GitHub receives your computer's IP address, nothing else. A new version is still installed with `update.command` or `update_windows.bat`.
- The update tool (`update.command` or `update_windows.bat`) now downloads new versions from GitHub and checks the package with the checksum from GitHub. Before checking, it prints that GitHub receives the computer's IP address. With `--offline` it does not check online; it still finds a ZIP file in the “Downloads” folder. The installation guides also download the program package from GitHub; the step “Install the licence” is dropped.
- Installations up to version 1.7.0 keep searching on the vendor's former server and do not find this version there. To switch, download the file `BMS_<Version>.zip` from https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/latest once into the “Downloads” folder, quit BMS and double-click `update.command` or `update_windows.bat`. After that, the tool searches GitHub by itself.
- Reports that Claude writes for you (match dashboard, ATS scan, briefing, rejection analysis, offer comparison) now get their appearance in a fixed work step. Before, Claude rewrote the design for every report, and parts were occasionally lost. As a result, new reports look the same from run to run. In the match dashboard, the keyword log now shows the same colours as in the ATS scan. Reports already created stay as they are.
- If LinkedIn throttles requests, BMS now tries several times with pauses instead of saving the posting as “not retrievable”. Search runs may take a little longer as a result.
- If a job is missing its posting text, BMS fetches it before company check, CV match, CV and cover letter. If that fails, it asks whether the run should start anyway.
- Whether a portal still accepts applications is now checked by the company check and the applied check with the same fetch as the search runs, with a retry when throttled. BMS now also recognises closed LinkedIn postings on German pages.
- If a portal does not respond to automatic requests at all (for example StepStone), BMS reports “not checkable” instead of “no longer online”. Results from job emails are kept as a result.
- In “New / Review”, “Job search + Apify” is now built exactly like the job search next to it: large button, below it in two lines status and origin as well as duration, turns and cost, then the final message of the last run. The messages of both searches are at the same height.
- Under Legal → Third-party licences, all the open-source packages that BMS installs with it are now listed, with version and licence. The “Show licence texts” button shows the full text of the licences. The privacy statement now describes the job search of the Arbeitsagentur correctly.
- The Budget page no longer shows the entry “Perplexity (search)”. BMS never called this service.
- Next to the overview, the coach site has the tab “Daily digest”. It shows new results, rejections and applications of the last four days and the changes of the day, and is uploaded with every daily run. It does not contain emails awaiting a reply, your open actions or your notes. Under “Rejections & patterns”, the pattern report now shows its date.
- The rejection analysis now runs once a week in the daily run. That costs one model run per week; on the other days the daily run skips the step at no cost. On the dashboard, a link leads to the latest report, and a button starts the analysis by hand. Only a manual start replaces the empirical lines in your profile that feed into the job search and documents; the weekly run writes its suggestion into the report. If the analysis fails, the other steps of the daily run still run.
- The Gmail check now also finds personal emails from companies you have applied to when the subject and sender carry none of the usual keywords, for example a rejection straight from the recruiter. To do this, it additionally searches the sender domains of your ongoing applications. Large job portals such as LinkedIn stay excluded. If an email comes from a contact that was previously saved without an email address, BMS adds the address there instead of creating the contact twice.
- The bundled scoring rules (`config/scoring_rubrik.md`) now align the level with your Settings: If plan A under “Level” also names Manager or Senior Manager, such a role with team leadership counts as plan A and no longer as the fallback plan C. If you have adapted the file yourself, your version is kept.
- The Excel export has the new sheet “Applications” right after “Jobs”. It shows every job you applied for in one row: company, title, fit, Match-100, ATS, found on, applied on, the date of each interview round (Round 1 to 6) and the rejection date. The newest application is at the top. If an interview has no date, BMS takes the date of its transcript. The rejection date is the day of the rejection email; without an email, it is the day on which the job was set to “Rejected”.
- The daily digest has the link “← Back to the dashboard” at the top left. Before, only the browser's back button led from the digest back into the app.
- Under “Legal” → “About this program” there is now a note on AI: BMS creates texts, evaluations and drafts with AI (Claude); they are suggestions and must be checked before sending.
- In the “Privacy” tab, the section “Contact for privacy questions” is removed, and in “About this program” the imprint entry under the publisher. For your data nothing changes: The publisher receives no data from your use of BMS.

## 1.7.0 (13.10.2026)

- The search runs now only sort a job out if the posting or email provides evidence that it violates one of your hard limits. Hybrid jobs outside your local area appear under “Germany-wide”, and jobs with a weak fit are created with score 1 or 2 instead of being left out. As a result, clearly more jobs arrive in the Review view again; the email job search checks more postings for this and takes correspondingly longer.
- The search portals Nejo and Arbeitsagentur have new addresses. BMS switches the preset addresses over by itself at the next start; an address you changed yourself stays unchanged. The button for checking a portal now shows yellow if an address only redirects to another one, and names the new one.
- For Nejo in the search area “Remote”, the job search now also evaluates jobs with a home-office share: If Nejo's own remote filter returns hardly any results, the same search is repeated once without it. For the Arbeitsagentur, all stored German titles are queried, not just the first two. Both only take effect if you have stored fine parameters for this in the search profile file.
- The installation now downloads the program package itself: The guide fetches it with your licence file from bms.daube.tech; you no longer need a ZIP file for it. Your licence file goes to the vendor, nothing else, and only if you run the download command yourself. A ZIP file in the “Downloads” folder remains as a second route.
- The update tool (`update.command` or `update_windows.bat`) now checks online for a new version and downloads it. Before that, it prints that your licence file is transmitted to bms.daube.tech, nothing else. With `--offline` it does not check online. It still finds a ZIP file in the “Downloads” folder; the highest version wins. If your entitlement to updates ends, you get the last version up to that point and a note about the newer one. The licence check itself still runs without internet. The privacy statement and the licence guide describe the new contact with the vendor.
- The installation guide now exists for each system: `BMS_Install_MAC.en.md` for macOS and `BMS_Install_Windows.en.md` for Windows. Both guide you through the installation with Claude and then contain setting up, updating, help and the details on your data. They replace `BMS_Install.md` and `BMS_Install_Auto.md`; the update removes the two old files.

## 1.6.3 (11.10.2026)

- The installation guide is restructured: Part 1 describes the installation on macOS, Part 2 the one on Windows, and from Part 3 everything applies to both systems. References in the other guides now name these parts.
- On Windows, the installation now suggests the folder `BMS` in the Programs folder (usually `C:\Program Files\BMS`) and sets up write permission for your user account there once. Your existing installation stays where it is.
- The installation now first checks whether a BMS already exists on the computer, installs only programs that are still missing, and no longer overwrites an existing access key. Warnings when building the interface are explained as harmless.
- New on the “Profile” page: the card “Identity and search strategy”. There you enter name, address, email, phone, LinkedIn, short profile, target role, hard constraints and known skill gaps directly in the interface, instead of creating the file `config/profil.md` by hand. Saving writes this file. What the card does not know, for example the section “Empirie aus dem Bewerbungsverlauf” or custom sections, stays unchanged, and the previous version goes to the bin. If the file was changed in the meantime, the card asks you to reload. Without a licence you can view the card but not save. The card shows an existing profile file and only changes it when you save. The installation guide and the user guide describe the new route.

## 1.6.2 (11.10.2026)

- The installation guide now asks which folder BMS should be installed in and inserts your answer into the following commands. `~/BMS` (Mac) or `C:\BMS` (Windows) is still suggested. For your existing installation nothing changes.
- New in the package: `BMS_Install_Auto.md`. With it, Claude guides you step by step through the installation on Windows.
- The guides now correctly say that licences from before version 1.6.1 are no longer valid.

## 1.6.1 (09.10.2026)

- The former verification key is revoked. Licences issued with it are no longer valid. If the “Licence” card in Settings reports a revoked key after the update, please request a new licence from the vendor. If you have already received and installed your licence anew, nothing changes for you.

## 1.6.0 (09.10.2026)

- The licence check now knows several verification keys. For you nothing changes; your licence remains valid.
- The terms of use (under “Legal”) and the guides now say consistently: A licence is valid for one person, not for one computer. You may use BMS on all computers you use yourself, and you install the same licence file on each. Before, the terms of use named one computer in one place and two in another.

## 1.5.1 (09.10.2026)

- The guide to the licence (Documentation, tab “Licence”) is shorter and clearer: the three licence types, installing in three steps, what works in view mode and what is locked, and what the band at the top of the app shows in each case, each in a table. Technical details on the licence format are no longer there.

## 1.5.0 (09.10.2026)

- BMS now needs a valid licence for searches, AI evaluations and changes to run. Without a licence it works in view mode: You can still see everything, open reports, CVs and cover letters, export to Excel, retrieve the daily digest, create backups and restore them. Your data stays fully intact. Locked are search runs, AI evaluations and changes, also in the terminal and in skills. If you try anyway, BMS names the reason and leads you to installing the licence. There are three licence types: the purchase licence (one-off, usable without time limit, updates for 24 months from issue), a free trial licence for 14 days, which you request from the vendor, and the fixed-term licence for companies and programmes with 6 or 12 months. A new installation starts in view mode until you install your licence. A band at the top of every page shows the status: in view mode with links to installing and buying, with the trial licence with the remaining days, with a fixed-term licence in the last 14 days with the expiry date. The “Licence” card in Settings names type, validity and update period. Licences already issued remain valid unchanged, as an unlimited purchase licence. For trial and fixed-term licences, BMS treats a system date set back as expired.

## 1.4.0 (05.10.2026)

- You now restore a backup with a tool instead of swapping files by hand: Quit BMS and double-click `wiederherstellen.command` (Mac) or `wiederherstellen_windows.bat` (Windows). The tool shows your backups, checks the one you choose and first backs up your current state. If you change your mind, start it again and choose the entry “vor Wiederherstellung”. It only affects the database; your documents stay unchanged.
- At the top, the dashboard now shows only the tiles for jobs and applications. The “Companies” tile is removed; you reach your companies as before via “Companies” in the sidebar.
- After an update, the browser shows the new interface immediately. Before, a page you had already opened, for example through a bookmark, could still show the old version for a while afterwards or stay blank. When updating to this version, this can happen one last time: Reload such a page once (Mac: ⌘ + R, Windows: F5).

## 1.3.0 (01.10.2026)

- You now import target companies, headhunters and network contacts from a file: In “Network”, every tab has the button “Import from file” for this. It reads CSV and Excel files, recognises the columns by their heading and offers a template to download for each list. For network contacts, the file Connections.csv from the LinkedIn data export also works. A preview shows beforehand what will be created new, updated or skipped. The import only fills empty fields of existing entries, entries deleted in the app stay deleted, and BMS creates a backup beforehand.
- The Excel export and the step “Refresh views” in the daily run now also work while no jobs have been recorded yet, for example right after removing the sample data.
- The file names of reports, CVs and cover letters are shorter: The date comes first as YYYYMMDD, company names lose parenthetical additions and legal forms such as GmbH or AG, long company and job titles are shortened at a word boundary, and the types are called “Anzeige”, “Auswertung” and “Beirat”. BMS still recognises older files with the previous date format.
- New in the sidebar: “Advisory Board”, directly under “Network”. There you ask the seven board members questions unrelated to a specific job; before, the page could only be reached by its address. It now also names the chair you set in Settings.
- The menu item “Outreach” is removed. It showed a list that could not be filled in BMS; you maintain your contacts under “Network”. The “Network” page now describes its three lists instead of pointing to an Excel sheet, the headhunter list no longer shows the source “Blatt” everywhere, and the dashboard no longer permanently reports “Network history incomplete”.

## 1.2.0 (01.10.2026)

- New in the sidebar: “Documentation”. There you read the changes for each version, an overview of the functions, the user guide and the help on installation and updates, email, Windows, coach site, Advisory Board and licence, without leaving BMS.
- A new installation starts with sample data so you can try BMS straight away: Birne Helene, a postman with 5 years of experience in parcel delivery, with profile, base CV, five jobs at various stages, emails and an interview. Before you enter your own data, remove the sample data in Settings with one click. BMS creates a backup first, and your own entries are kept. Existing installations do not get sample data.
- In Settings, you choose between Opus 5.5, Sonnet 5.5 and Haiku 4.5 for each function; Sonnet 5.5 is preset. Fable 5.1 is no longer available, because it costs two and a half times as much as Opus 5.5 and five times as much as Sonnet 5.5. Where you had chosen Fable, BMS now works with Sonnet 5.5. The other AI runs, such as the email check and the questions about a job, also run with Sonnet 5.5, regardless of the default model of your Claude installation.
- At the top, the sidebar shows “Job Application Management System” and below it your name; the installed version is at the bottom.
- The Windows guide (Documentation, tab “Windows”) now follows the setup from the program package and states more precisely what does not yet work on Windows. For example, on Windows the daily run ends with a failed step “Refresh views”; you get the Excel export, daily digest and search index there with the buttons on the dashboard and in Search.

## 1.1.3 (29.09.2026)

- Other websites that you have open in the same browser can no longer trigger anything in BMS, such as discarding jobs, replacing your base CV or creating backups, nor read your data via a redirected address name. To do this, BMS now only responds at localhost, an IP address, a name ending in .local or a computer name without a dot. The addresses that the start window shows in Wi-Fi mode work as before; you allow further names with the environment variable BMS_HOSTS.
- Reports that you open from BMS (company fit, match dashboard, ATS scan, job posting, briefing, Advisory Board check, analysis, transcript report) and the daily digest run in the browser separately from BMS. A script that ended up in a report through researched web content can therefore no longer read your data or change anything. The reports look as before, sources and original postings still open in a new tab, and printing works as usual.

## 1.1.2 (28.09.2026)

- In Wi-Fi mode (`start_lan.command`), a device on the same network can no longer move your database and your backups to the bin or view other files on your computer through the search. When deleting, only your documents now go to the bin: reports, CVs, cover letters, job postings and files attached to jobs and in the profile. Deleting, CVs and cover letters work as before.

## 1.1.1 (28.09.2026)

- BMS now only releases the documents that you open in the interface: reports, CVs, cover letters, job postings, files attached to jobs and in the profile, and transcripts. Your database, your backups and other files on your computer can no longer be retrieved through it. Before, in Wi-Fi mode (`start_lan.command`), any device on the same network with a suitable address could download the complete database.
- Other websites that you have open in the same browser can no longer read your data in BMS or delete jobs. Before, BMS opened its programming interface to every website. The interface, Wi-Fi mode and AI runs work unchanged.

## 1.1.0 (28.09.2026)

- BMS backs up your database automatically once a day, as long as it is running, as a ZIP file in the folder `data/backups/auto`. It keeps one backup each of the last 7 days and 4 weeks and removes older automatic backups itself. In Settings under “Backup”, you see the last backup, change the retention and back up at the push of a button.
- You archive emails without a job that have nothing to do with your applications in the Inbox with one click. They disappear from the Inbox, from the email count on the dashboard and from the daily report. In the archive you can bring them back at any time. In Gmail they stay unchanged.
- BMS removes intermediate files of the AI runs itself after 30 days, with the same period as the logs of the runs. Files that belong to stored documents are kept.

## 1.0.0 (28.09.2026)

- First released version of the Job Application Management System.
- You install updates with `update.command` (Mac) or `update_windows.bat` (Windows). Your data, settings and customisations are kept, and a backup is created beforehand.
- The local-area filter takes city and radius from your Settings. You no longer need to adapt program files for this.
- In Settings, you choose between Fable 5.1, Opus 5.5, Sonnet 5 and Haiku 4.5 for each function. Sonnet 5 stays preset.
- Settings show the installed version and the changes in this version.
