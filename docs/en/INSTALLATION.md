# Installation — BMS Job Application Management System

This guide describes a **new installation from scratch** on your own computer: a fresh
repository, an empty database, your own person. It is written for someone who has
never seen the system and assumes no knowledge of the project, but it does assume you are willing to
open a terminal (macOS) or PowerShell (Windows) once.

**No data transfer:** If you want to move an existing installation to another computer,
you follow the same technical steps, but you skip Part 3 and instead copy
`data/`, the personal `config/` files and the secrets directory from the old
computer. This guide assumes that nothing is carried over.

**For users** there is a separate version for each system without project internals: `BMS_Install_MAC.en.md`
(macOS) and `BMS_Install_Windows.en.md` (Windows) in the main folder. From the user's point of view (with
Claude), they walk through the same steps, download the program package from the GitHub release of the public
repo instead of from the repository, and add updating. The BMS does not need a licence file
(open source under Apache-2.0).

## What the system is — and what it needs

A local web application for your own job search: capture and rate jobs, check companies,
create CVs and cover letters, track application emails. It runs
entirely on your own computer (FastAPI + SQLite + React); there is no server service on the
internet that you sign in to.

The substantive work — research, text drafts, matching — is done by **Claude Code** as a
subprocess, or alternatively by OpenAI's **Codex CLI** (ChatGPT, preview, see 3.7). Without an active
Claude or ChatGPT account, the basic functions (capturing, managing,
evaluating, exporting) work, but all AI-assisted processes do not. A licence file is not needed: all
functions are available without a licence.

| Requirement | Version | Used for | Mandatory? |
|---|---|---|---|
| Python | **3.12** | Backend/server | yes |
| Node.js | **24** | Building the frontend (once) | yes |
| Git | current | Getting the repository | yes |
| Claude Code (CLI) | current | All AI functions | effectively yes |
| LibreOffice | current | Converting Word files to PDF | for PDF output |
| Claude account | Subscription or API | Running the AI functions | for AI functions |
| Codex CLI (instead of Claude Code) | current | AI functions with ChatGPT | only with ChatGPT |
| ChatGPT account | Plus or Pro | Running the AI functions with ChatGPT | only with ChatGPT |

Time needed: about 30–45 minutes for the technical part (Part 1 or 2), then one to two hours for
the personal setup (Part 3). For the LinkedIn data export that Part 3 recommends, you should
start the download at LinkedIn **a day beforehand**; it can take up to
24 hours to be made available there.

**Access to the repository:** The project is in the public GitHub repository
`holgerdaube/BewerbungsMgmtSystem`. You do not need a GitHub account to clone it; you only need one
when you want to submit changes (see `CONTRIBUTING.md`).

---

# Part 1 — Steps on Windows

The backend test suite runs regularly on `windows-latest` in the project's automation. On
a real Windows computer, the installation has not been tested so far, and some areas are restricted
on Windows (see Part 5).

## 1.1 Install the requirements

In PowerShell, one after the other:

```powershell
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
winget install Git.Git
winget install TheDocumentFoundation.LibreOffice
```

Two points decide later between success and troubleshooting:

- In the Python installer, tick **"Add python.exe to PATH"** (with `winget` this happens
  automatically). Check with `py -3.12 --version`; the `py` launcher unambiguously picks
  version 3.12, even if several Pythons are installed.
- Leave LibreOffice **at the default path** (`C:\Program Files\LibreOffice\`). The app looks for
  `soffice.exe` exactly there; if it is installed elsewhere, it does not find it and cannot create
  PDFs.

Then Claude Code:

```powershell
winget install -e --id Anthropic.ClaudeCode
```

Check: `claude --version`. Then start `claude` once and sign in; otherwise
all AI runs later fail with an authentication error.

## 1.2 Get the repository

```powershell
git clone https://github.com/holgerdaube/BewerbungsMgmtSystem C:\BMS
cd C:\BMS
```

The target folder is up to you; `C:\BMS` keeps the paths short. Do **not** put it in a
live-synchronised cloud folder (OneDrive, Dropbox): the database is a single
file that is written to constantly, and cloud sync causes conflicts there.

## 1.3 Create the Python environment

Deliberately **outside** the project folder, so that thousands of package files are not in the project:

```powershell
py -3.12 -m venv $env:USERPROFILE\.bewerbung_mgmt_venv
& "$env:USERPROFILE\.bewerbung_mgmt_venv\Scripts\pip.exe" install -r backend\requirements-lock.txt
New-Item -ItemType Junction -Path "$env:USERPROFILE\.bewerbung_mgmt_venv\bin" -Target "$env:USERPROFILE\.bewerbung_mgmt_venv\Scripts"
```

`requirements-lock.txt` pins exact versions. If you want to run the test suite,
additionally install `backend\requirements-dev.txt`.

The third line creates a directory junction `bin` → `Scripts`. The skills call Python
throughout as `~/.bewerbung_mgmt_venv/bin/python` (macOS form), and so does the path guard in
`automation/agent_settings.json`. On Windows, Claude Code runs these commands in Git Bash,
which resolves the junction and finds `python.exe`. Without it, every database
access fails in AI runs. That is why Git for Windows (1.1) is mandatory here: without Git Bash, Claude Code
falls back to PowerShell, in which the skills' heredoc commands do not run. On real Windows hardware
this route has not been tested yet.

## 1.4 Build the interface

```powershell
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
```

This creates `frontend/dist/`. **Without this step, the server does start, but shows a
blank page**; it serves the interface only if this directory exists. The
script `frontend/build.sh` is a macOS workaround and is not used on Windows.

`npm.cmd` instead of `npm` is deliberate: on many computers Windows PowerShell blocks the script
`npm.ps1` (execution policy), and `npm.cmd` is not affected by that.

## 1.5 Start

Double-click `start_windows.bat` (or run `.\start_windows.bat` in PowerShell). After about two seconds,
the browser opens `http://localhost:8000`, and the server window stays open.

On the very first start, the application creates what it is missing: the `data/` directory,
the empty database and a starter version of `config/suchprofile.yaml`.

**To stop:** `Ctrl+C` in the server window. If the window is closed or no longer responds,
`stop_windows.bat` helps. It ends the process on port 8000 and asks first if
AI runs are currently active.

## 1.6 Continue with Part 3

The application is running now, but is still empty and does not know you yet. Continue at
**Part 3 — First setup**.

---

# Part 2 — Steps on macOS

macOS is the project's reference platform: everything is tested here in everyday use.

## 2.1 Install the requirements

[Homebrew](https://brew.sh) is assumed (if you do not have it, take the install command from there):

```sh
brew install python@3.12 node git
brew install --cask libreoffice
```

Then Claude Code:

```sh
npm install -g @anthropic-ai/claude-code
```

Check with `claude --version`, then start `claude` once and sign in.

## 2.2 Get the repository

```sh
git clone https://github.com/holgerdaube/BewerbungsMgmtSystem ~/Projekte/BewerbungsMgmtSystem
cd ~/Projekte/BewerbungsMgmtSystem
```

**About iCloud Drive:** The project *can* live in iCloud (for example as a backup of the working copy), but this
requires two additional measures: the frontend build in section 2.4 and a relocated Git directory
(`.git.nosync`, see `docs/DOKUMENTATION.md`, section "Project structure and storage locations"). If you do not
need that, simply put the project outside iCloud; this guide assumes that.

## 2.3 Create the Python environment

```sh
/opt/homebrew/bin/python3.12 -m venv ~/.bewerbung_mgmt_venv
~/.bewerbung_mgmt_venv/bin/pip install -r backend/requirements-lock.txt
```

On Intel Macs, Homebrew is at `/usr/local/bin/python3.12`. For the test suite, additionally
install `backend/requirements-dev.txt`.

## 2.4 Build the interface

If the project is **outside** iCloud (the normal case):

```sh
cd frontend && npm ci && npm run build && cd ..
```

If the project is **in iCloud Drive**, use this instead:

```sh
cd frontend && ./build.sh && cd ..
```

The difference has a concrete reason: iCloud keeps re-materialising `node_modules`
and in doing so destroys the symlinks that the build needs. `build.sh` therefore works around this by moving to
`~/.bewerbung_mgmt_node/` and copies only the finished `dist/` back. Outside iCloud
this detour is unnecessary.

## 2.5 Start

Double-click `start.command` in Finder, or in the terminal:

```sh
./start.command
```

The browser opens `http://localhost:8000`. As on Windows, the first start creates `data/`, the
empty database and a starter version of `config/suchprofile.yaml` by itself.

For access from your own Wi-Fi (for example from a tablet) there is `start_lan.command`.
**To stop:** `Ctrl+C` in the server window, otherwise `stop.command`.

---

# Part 3 — First setup (both platforms)

The application is running now, but knows nothing about the person who is applying. This part is
the real core of a new installation. The order is deliberate: steps 3.1 and
3.2 are manual work on files, and everything else goes through the interface.

> **Windows paths:** Where `data/cv_basis/` appears below, `data\cv_basis\` is meant on Windows,
> relative to the project folder, so for example `C:\BMS\data\cv_basis\`.

## 3.1 Create the profile file (mandatory)

`config/profil.md` is the personal master file: name, address, contact details and the search strategy.
It is deliberately not in the repository. Since P2-69, the easiest way to maintain it is in the interface:
the **Profile** page, first card "Identity and search strategy". Saving writes the file and leaves
everything the card does not know about untouched. The route with a text editor below still works.

Without this file the system does run, but every CV it creates is then called
`CV_Bewerber_…` instead of carrying your own name, and cover letters have **no letterhead** (the
system deliberately invents nothing at this point).

Create a new file `config/profil.md` with this content and replace the values:

```markdown
# Kandidatenprofil — Max Mustermann

## Identität
- **Name:** Max Mustermann
- **Positionierung:** Service Delivery Leader · DACH
- **Standort:** Musterweg 3, 12345 Musterstadt
- **Kontakt:** max.mustermann@example.com · +49 170 1234567
- **LinkedIn:** https://www.linkedin.com/in/max-mustermann/
- **Aktuell:** Manager Professional Services @ Beispiel GmbH, seit 2024

## Kurzprofil
Zwei bis vier Sätze zur eigenen Person — diese dienen als Tonvorlage für Anschreiben.

## Zielrolle
- **Ebene:** Director / Head
- **Funktion Plan A:** Professional-Services- / Service-Delivery-Leitung
- **Funktion Plan B:** Head of Customer Success
- **Branche:** Enterprise Software, IT-Services
- **Region:** DACH
- **Zieltermin:** neue Rolle bis 31.12.2026

## Harte Rahmenbedingungen
- Kein Umzug, kein dauerhafter Zweitwohnsitz.
- Mindestens 100 Mitarbeiter beim Zielunternehmen.
- Reine Vertriebsrollen ohne Führungsverantwortung sind kein Fit.

## Sprachen / CV-Fassungen
- **Deutsch:** `data/cv_basis/base_de.docx`
- **Englisch:** `data/cv_basis/base_en.docx`

## Bekannte Skill-Gaps / Red Flags
- (noch keine)

## Empirie aus dem Bewerbungsverlauf
- (wird automatisch gepflegt — Überschrift bitte unverändert stehen lassen)
```

Three format rules that are actually evaluated:

- **Standort** (location) in the format `Straße Nr, PLZ Ort` (street no., postcode, town). For the place line in the cover letter, the last
  comma segment is taken and the postcode is split off; other formats produce a
  crooked line.
- **Kontakt** (contact): separate email and phone with `·`. In the letterhead this automatically becomes `|`.
- The four fields **Name, Standort, Kontakt, LinkedIn** are recognised by their bold formatting
  (`**Name:**`). The asterisks must stay; the order does not matter.

The remaining text (short profile, target role, constraints) is not parsed by machine,
but read as context by the AI processes. It can therefore be worded freely, but should
be specific.

## 3.2 Provide a base CV (mandatory for all CV functions)

The system does not invent a CV. It takes an existing one as its basis and adapts it for each
job. **Exactly two files with fixed names** are expected:

- `data/cv_basis/base_de.docx` — German version
- `data/cv_basis/base_en.docx` — English version

Both are Word files (`.docx`, not PDF). Since P2-27 they are uploaded through the
interface: **Profile → Base CVs**, choose the language, choose the file, "Upload". The upload counts
the positions it recognises and warns, without rejecting, if the structure does not fit; before
overwriting, it asks first, and the old version goes to the bin. If you only search in German,
upload both anyway (the English one may be a copy), otherwise English-language
runs abort.

**The structure is not arbitrary.** The adaptation logic recognises the career positions by a
fixed pattern; if the file does not follow it, positions are not found or are merged
incorrectly:

| Element | Requirement |
|---|---|
| Section headings | Paragraph style **Heading 1**, in capital letters |
| Name of the experience section | `BERUFSERFAHRUNG` (German) or `PROFESSIONAL EXPERIENCE` (English) |
| Start of a position | Paragraph style **Normal**, structure `Company` → **tab** → `Period` |
| Line directly below | Job title, Normal style, **bold**, 11 pt, without a tab |
| After that | Italic company description (one to two lines) |
| After that | Achievements as a bullet list in the **List Paragraph** style |
| Spacing before each position | at least 20 pt "Spacing before" on the tab line |

The tab between company and period is the decisive recognition feature and must **not occur
anywhere else** in the document. In other sections (education, certificates), separate
with `•`, not with a tab.

In practice: open an existing CV in Word, set the section headings to
"Heading 1", insert one `Company⇥Period` line per position and format the bullet lists
as List Paragraph.

## 3.3 Import the LinkedIn data export (recommended)

The fastest way to fill in your career history and skills without typing everything.

At LinkedIn: **Settings → Data privacy → "Get a copy of your data"** and choose the
**top** option ("larger data archive") there. The quick selection "Profile" contains only the
short description and is not enough. LinkedIn makes the archive available within up to 24 hours
and sends an email.

Then upload the ZIP you receive in the application under **Profile**. The import takes over
the short description, location, skills, career positions, education and certificates. The import
works purely mechanically, only adds and overwrites nothing that already exists. Afterwards,
a background run automatically sorts the imported skills into topic areas.

A fictitious example is in `beispiele/LinkedIn_Data_Export_Example_EN.zip` (German
`beispiele/LinkedIn_Datenexport_Beispiel_DE.zip`). It shows the structure of the export and, with
`Connections.csv`, also contains two contacts for the network import.

Then review and supplement the profile in the interface: sharpen the positioning,
complete the career positions, attach references and certificates.

> **Note:** The file `config/profil_struktur.md` is not part of the repository. The application creates it
> itself from the data on the Profile page (at startup if it is missing, and on every save, including through
> the ZIP import). It is the "substance" that the system draws on for cover letters and CVs, and
> is not edited by hand.

## 3.4 Set the settings in the interface

Under **Settings**, in this order:

1. **Search area and company size** — Remote, Germany-wide and/or city with local area;
   minimum number of employees. The local area internally creates a category such as `Musterstadt +50km`,
   which later appears on every job. If you change the city or radius again later, the
   application automatically switches existing jobs to the new label.
2. **Plans A/B/C** — the target roles: title, level and industry for each plan. Plan A is the
   actual goal, Plan B the realistic alternative, Plan C optional as a fallback level.
   **These fields are empty after installation** and must be filled in; until then
   the job search finds nothing, because it does not know what to look for.
3. **Search portals** — six portals are pre-filled and active; switch individual ones off if needed or
   add two of your own. The button for checking shows which ones respond. The portals are aimed at
   Germany; outside Germany, use the free rows, LinkedIn alerts and the target companies.
4. **AI models per function** — the default is Sonnet everywhere. That can stay as it is.

After the first save, the application rewrites `config/suchprofile.yaml` and enters
your inputs there.

## 3.5 Adapt the target profile

A file in the repository contains an example target profile and is read by the search processes. If you
do not adapt it, you get ratings according to the criteria of the example:

**`config/scoring_rubrik.md`**, section *Dimension 2 — Function*: the description of
Plan A, B and C (in the example "PS or service delivery leadership" and "Head of Customer
Success"). The rating scale 1–5 and the situation codes (BUILD, CARVE-OUT, POST-MERGER …)
are generally valid and remain unchanged.

The region itself no longer has to be adapted by hand anywhere: as soon as city and
local area are set in step 3.4, the job list, filters and the search processes (`jobsuche`,
`mail-jobsuche`, `angebot-vergleich`) take over the label automatically from the settings.

## 3.6 Connect an email account (optional, but recommended)

Without an email connection, the daily mailbox comparison and the evaluation of
job notifications do not apply. Under **Settings → Email account**; the recommended route is IMAP with
an **app password** from the mail provider (not the normal password). Host and port for the
common providers, as well as the alternative Gmail route, are described in `docs/SETUP-EMAIL.md`.

The system **never sends emails itself**. It only creates drafts, which you
check and send yourself.

## 3.7 Enable automatic runs (optional)

For processes that start in the background (daily job search, company check, mailbox comparison),
the server needs its own access token for Claude Code. Create it with:

```sh
claude setup-token
```

Write the token that is output into a file `agent.env` in the secrets directory, as one line
`CLAUDE_CODE_OAUTH_TOKEN=…`. The directory is deliberately outside the project:

- macOS: `~/.bewerbung_mgmt_secrets/agent.env`
- Windows: `%USERPROFILE%\.bewerbung_mgmt_secrets\agent.env`

`automation/agent.env.example` serves as a template. Take care when copying: if the token wraps over
several lines, the parts belong back on one line; a line without `=` is the
continuation of the previous one. Restart the server after creating it.

**With ChatGPT instead of Claude (preview):** Install the Codex CLI (`npm install -g @openai/codex`,
on macOS also `brew install --cask codex`), sign in once with the ChatGPT account (`codex login`,
check with `codex login status`, expected "Logged in using ChatGPT") and choose ChatGPT in the Settings,
in the "AI" card (or `PATCH /api/einstellungen` with `{"ki_anbieter":"chatgpt"}`). A
token and `agent.env` are not needed for this. The contents of the AI runs then go to OpenAI instead of to
Anthropic. On Windows, use `npm.cmd` and `codex.cmd`; according to OpenAI, Codex's preferred sandbox needs
a one-time administrator setup there, and this route has not been tested on Windows.

In addition, the allow list `automation/agent_settings.json` must match the path to the Python of the virtual
environment. It names it in the `~` form (`~/.bewerbung_mgmt_venv/bin/python`); if your environment is
elsewhere, enter the actual path. A placeholder is not enough at this point: the
entry must match the path exactly. If the venv path differs, also adapt the hook command in the `hooks` block of the same
file (it checks Write/Edit targets against the project root, see `docs/DOKUMENTATION.md` section 8); it calls the same venv Python installation as the allow list. If you develop on the project itself with
Claude Code and use the preview, create your own `.claude/launch.json` for it; it
is not part of the repository.

Create the secrets file like this on macOS (Windows: correspondingly in the user folder):

```sh
mkdir -p ~/.bewerbung_mgmt_secrets && chmod 700 ~/.bewerbung_mgmt_secrets
cp automation/agent.env.example ~/.bewerbung_mgmt_secrets/agent.env
chmod 600 ~/.bewerbung_mgmt_secrets/agent.env
```

The Gmail credentials (`gmail_credentials.json`, `gmail_token.json`, only for the Gmail API route from
`docs/SETUP-EMAIL.md`) end up in the same directory. The location can be changed via `BMS_SECRETS_DIR`.

## 3.8 Cosmetics

The browser tab shows the product name, followed by the name from `config/profil.md`; the sidebar also reads
the name dynamically and is correct automatically after step 3.1. The product name comes from the
design (`docs/DOKUMENTATION.md`, section "Design from one source"); the static `<title>` in
`frontend/index.html` is only the initial value until the design is loaded.

## 3.9 Optional environment variables and development tools

`.env.example` lists the settings that may deviate from the default: server port and address,
`BMS_DATA_DIR`, `BMS_SECRETS_DIR` and the limits for AI runs. The program reads them exclusively from
the environment; it does not load a `.env` file itself. Set the values therefore in the shell that starts the
server, for example `PORT=8010 ./start.command`.

If you work on the source code, install `backend/requirements-dev.txt` once, and the secret guard
(`scripts/install_hooks.sh`, checks for tokens before every commit). The tests run with `scripts/test.sh`
against a throwaway database. Details and the rules for contributions are in
`docs/DOKUMENTATION.md` (section "Tests & CI") and in `CONTRIBUTING.md`.

---

# Part 4 — Checking that everything is in place

This short round uncovers the typical installation errors:

| Check | Expectation | If not |
|---|---|---|
| Open `http://localhost:8000` | Interface with menu appears | Frontend not built (step 1.4 / 2.4) |
| Open the **Settings** page | Cards are displayed, no error | Restart the server; read the message in the server window |
| **Program version** card, button "Check for updates" | The button shows the latest version or an error text (if no release has been published yet: "No version has been published yet.") | Check the internet connection and access to GitHub (company network, proxy) |
| Open the **Profile** page | Your own name in the header | Check `config/profil.md` (spelling `**Name:**`) |
| Create a job by hand | Entry appears in the list | Check the server window for error messages |
| **Tasks** page, start a run | Run starts and ends with a result | Check the Claude sign-in and token (step 3.7) |
| Create a CV for a job | Word and PDF files are created | Check the base CV (3.2) and the LibreOffice path |

If you want to secure the technical basis completely, you can run the test suite (requires
`requirements-dev.txt`):

```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pytest tests -q
```

On Windows, use `%USERPROFILE%\.bewerbung_mgmt_venv\Scripts\python.exe` correspondingly. Some
tests skip themselves there by design, because they test Unix peculiarities. That is not an error.

On your own installation, individual tests can also turn out differently from in CI: as soon as
`config/profil.md` and the base CVs under `data/cv_basis` exist, some tests also check against
these local files. That is not an installation error; CI runs without these files and is the
yardstick.

---

# Part 5 — Limits and common stumbling blocks

**Not available on Windows** (details in `docs/SETUP-WINDOWS.md`):

- **Timed automation.** The daily run at a fixed time is macOS-specific; on
  Windows you start it via the button in the interface.
- **Three collective functions** — "Update views" (Excel export, daily digest,
  search index), "Render cover letters" and the coach site upload — call a Unix script internally
  and report "Binary not found" on Windows. The Python modules behind them can
  be called directly.
- **The helper scripts in `scripts/`** assume the Unix directory structure of the virtual environment
  and do not run unchanged even in Git Bash.

**On both platforms:**

- **No auto-reload.** After changes to backend files, the server has to be restarted.
- **The database is a single file** (`data/bewerbung.sqlite`). The BMS backs it up
  automatically: once a day as a ZIP to `data/backups/auto`, with fixed retention
  (settings in the interface under "Data backup"). Before particularly risky actions,
  additionally make a copy of your own; on macOS there is `scripts/backup_db.sh` for that.
- **Two installations do not synchronise with each other.** If you run the system on two computers,
  you keep two separate sets of data; merging them is manual work.
- **The Excel export of the contact list** falls back on a template file that does not exist in a
  new installation; this one function then reports an error. All other
  exports are unaffected.
- **Costs arise from the AI runs.** The Budget page shows usage and slows things down when the limit is
  exceeded; defaults are created automatically on first access.

**Legal:** The BMS is under the Apache License 2.0 (`LICENSE`, `NOTICE`) and needs no
licence file. Up to version 1.7.0 there was a licence requirement; it was removed in P2-82 (background
and technology: `docs/DOKUMENTATION.md`, section "Licence — removed"). Older licence files in the
secrets directory are no longer read and may be deleted.

---

# Part 6 — Further material

| File | Content |
|---|---|
| `docs/ANLEITUNG.md` | Everyday use — the best starting point after the installation |
| `docs/SETUP-EMAIL.md` | Email connection in detail (IMAP and Gmail) |
| `docs/SETUP-WINDOWS.md` | Windows specifics, limits, support matrix |
| `docs/DOKUMENTATION.md` | System structure, everyday operation (starting, stopping, backup), tests and development status |
| `docs/RELEASE.md` | Version and release workflow (only relevant if you release packages yourself) |
| `CONTRIBUTING.md` | Rules for contributions (licence, language, tests) |
| `SECURITY.md` | Reporting security vulnerabilities |
| `README.md`, `README.de.md` | Project overview for users in English and German: installation, updates, data protection, licence |
