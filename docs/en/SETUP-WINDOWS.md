# Windows setup

> **Installing from scratch?** The Windows installation is described step by step in
> `BMS_Install_Windows.en.md`. Claude guides you through it, including downloading the program
> package from GitHub. You only need a ZIP file as a fallback. In BMS you will find the guide under
> “Documentation”, tab “Installation & updates”. This document goes into more detail on what works
> differently on Windows than on the Mac, what does not work and why.

BMS is developed on the Mac and used there every day. On Windows, the server and the interface run,
and managing jobs, companies, contacts and appointments works fully. Some areas, above all the AI
runs, have been adapted for Windows but not yet verified. BMS has not been tested on a real Windows
computer so far. The statements here are based on the program code and on the automated tests, which
also run on a Windows system with every change. What does not work, or only in part, is listed under
“Known limits”.

## Requirements

`BMS_Install_Windows.en.md`, step “Step 3: Install programs”, installs the programs with `winget`: Python 3.12,
Node.js (LTS), Git for Windows, LibreOffice and Claude Code (with ChatGPT, the Codex CLI instead of
Claude Code, via `npm.cmd`). Three points matter on Windows:

1. **Python 3.12:** Check the version with `py -3.12 --version`. The `py` launcher reliably picks
   Python 3.12, even if several versions are installed. A plain `python --version` may pick a
   different version, depending on the PATH order.
2. **Git for Windows is required:** The AI functions work with commands that Claude Code can only
   run on Windows in the “Git Bash” installed with Git.
3. **LibreOffice in the default location:** BMS looks for `soffice.exe` first in
   `C:\Program Files\LibreOffice\program\`, then in `C:\Program Files (x86)\LibreOffice\program\`
   and finally in the PATH. If LibreOffice is somewhere else and its `program` folder is not in the
   PATH, BMS does not find it and creates no PDF files. So keep the suggested installation location.

**Without winget:** The programs are also available on the vendors' websites:
[python.org](https://www.python.org/downloads/), [nodejs.org](https://nodejs.org/),
[git-scm.com](https://git-scm.com/download/win) and
[libreoffice.org](https://www.libreoffice.org/download/). In the Python installer, tick
“Add python.exe to PATH”, otherwise Windows will not find the `python` command later. Install Claude
Code following Anthropic's instructions.

BMS does not name a minimum version for Node.js. The automated tests build the interface with
Node.js 24.

## Set up the Python environment

If `start_windows.bat`, `update_windows.bat` or `wiederherstellen_windows.bat` reports that the
Python environment is missing, catch up on this step (`BMS_Install_Windows.en.md`, step
“Set up the Python environment”). In PowerShell, in the program folder, for example `C:\Users\Name\BMS`:

```powershell
py -3.12 -m venv "$env:USERPROFILE\.bewerbung_mgmt_venv"
& "$env:USERPROFILE\.bewerbung_mgmt_venv\Scripts\pip.exe" install -r backend\requirements-lock.txt
New-Item -ItemType Junction -Path "$env:USERPROFILE\.bewerbung_mgmt_venv\bin" -Target "$env:USERPROFILE\.bewerbung_mgmt_venv\Scripts"
```

The environment is deliberately outside the program folder, at
`%USERPROFILE%\.bewerbung_mgmt_venv`. On Windows, Python is in the `Scripts` folder there, on the
Mac in `bin`. The AI functions and the path guard (see below) always call Python as
`~/.bewerbung_mgmt_venv/bin/python`. The `bin` → `Scripts` link from the third line makes sure this
call also arrives on Windows. Without it, every database access fails in AI runs.

## Build the interface

On Windows, you build the interface directly in the `frontend` folder with `npm.cmd ci` and
`npm.cmd run build` (`BMS_Install_Windows.en.md`, step “Build the interface”). Write
`npm.cmd` and not just `npm`: on many computers PowerShell blocks the `npm.ps1` script, while
`npm.cmd` is not affected. The `frontend/build.sh` script is for Mac installations in iCloud Drive
and is not needed on Windows.

## Access key and secrets

`BMS_Install_Windows.en.md`, step “Set up AI access”, stores the access key for the background AI
runs in `%USERPROFILE%\.bewerbung_mgmt_secrets\agent.env`. The other credentials of BMS, such as
those for the email account, are kept there too. You set a different location with the environment
variable `BMS_SECRETS_DIR`.

Windows has no Unix file permissions. On the Mac, BMS restricts its credential and log files to your
user account (`chmod 600` or `700`); on Windows this call has no effect. There, only your user
profile protects these files. On start-up, the server may therefore print the warning “agent.env:
zu offene Rechte … 'chmod 600 …' ausführen” on Windows. On Windows it is irrelevant.

## Starting

In the program folder, double-click `start_windows.bat`. The file checks that the Python environment
is there, starts the server on port 8000 in the foreground and, after about two seconds, opens
`http://localhost:8000` in the default browser. Keep the window open as long as you work with BMS.
Ctrl+C stops the server.

## Stopping

Ctrl+C in the server window. If the window is closed or the server no longer responds, double-click
`stop_windows.bat`. The file uses PowerShell to ask the server whether any AI runs are active or
queued. If so, it asks whether you want to stop anyway, because stopping cancels these runs.
`stop_windows.bat --force` skips the confirmation. If the server no longer responds, the file stops
it without asking; otherwise a hung server could never be stopped. It looks for the process that is
listening on port 8000 (`netstat`) and ends it together with its child processes, first normally and
after 10 seconds forcibly (`taskkill /F /T`).

The procedure matches the `stop.command` file, which has been verified on the Mac. On Windows it
is not yet verified.

## Updating

Quit BMS and double-click `update_windows.bat` in the program folder. The procedure is described in
`BMS_Install_Windows.en.md`, section “Installing updates”. The file passes the program folder to
`scripts\bms_update.py`. The tool checks GitHub online for a new version and downloads it, checks the
new package, creates a backup, installs the update, installs new components and runs a self-test. It
uses the same Python environment as the start (`%USERPROFILE%\.bewerbung_mgmt_venv\Scripts\python.exe`).

**Online check:** Before checking, the tool prints: “Suche auf GitHub nach einer neuen Version.
GitHub erhält dabei die IP-Adresse dieses Rechners.” Only the request itself is transmitted and
nothing else, and only if you start the tool yourself. The tool compares the downloaded package with
the checksum that GitHub gives for the file. With `--offline` it does not check online. If it cannot
reach GitHub, or GitHub rejects the request, it shows the reason and takes a ZIP file
`BMS_<Version>.zip` from your “Downloads” folder. The highest version wins, wherever it comes from.
The “Check for updates” button in Settings, card “Program version”, also shows you whether there is a
new version. It installs nothing.

`update_windows.bat` runs entirely inside one block in parentheses that ends with `exit /b`. The
reason: cmd.exe re-reads a batch file line by line while it runs, and the update can replace exactly
this file. cmd.exe reads a block in parentheses in full before the first line in it runs.

**Line endings:** The `.bat` files are delivered with Windows line endings (CRLF); otherwise cmd.exe
does not reliably find labels such as `:label` and `goto` in them. Every program package is checked
for this before delivery. If you edit a `.bat` file, save it with CRLF again.

## Restoring a backup

Quit BMS and double-click `wiederherstellen_windows.bat` in the program folder. The tool shows the
available backups, restores the one you choose into the database and first backs up your current
state. Only the database is replaced; your documents stay. The procedure is described in
`BMS_Install_Windows.en.md`, section “Your data”. The file uses the same Python environment as the
start and, like `update_windows.bat`, is a block in parentheses with Windows line endings.

## AI runs: allow list and path guard

The background AI runs may only execute commands that `automation/agent_settings.json` allows. The
list compares the start of each command character by character; a wildcard would allow nothing
there. It names the environment's Python in the Mac form `~/.bewerbung_mgmt_venv/bin/python` and
`$HOME/.bewerbung_mgmt_venv/bin/python`; it contains no separate Windows form (`Scripts\python.exe`).
On Windows, Claude Code runs these commands in Git Bash, and the `bin` → `Scripts` link forwards them
to `python.exe`.

Before every write access by a run, the path guard (`automation/pfad_waechter.py`) runs through the
same file. It only allows write access inside the program folder and the temp folders. Its command
also calls Python as `$HOME/.bewerbung_mgmt_venv/bin/python`. If this command does not start, then
under the rules of Claude Code it blocks nothing. The guard then fails instead of preventing write
access. The allow list and the guard are not yet verified on Windows.

Do not edit `automation/agent_settings.json` by hand. The next update replaces the file with the
delivered version and first stores your version in the update backup under `data/updates/…`.

## Known limits

- **Scheduled automation:** The template for a daily run at a fixed time
  (`automation/com.bms.tageslauf.plist.template`) exists only for the Mac (`launchd`). There is no
  equivalent for the Windows Task Scheduler. You start the daily run with a button.
- **Helper scripts in the `scripts` folder:** The `.sh` scripts do not run unchanged on Windows, not
  even in Git Bash. `coach_deploy.sh`, `coach_passwort.sh`, `coach_site.sh`,
  `cover_letter_render.sh` and `refresh_views.sh` are zsh scripts, and zsh is not part of Git for
  Windows. `backup_db.sh` needs the command-line tool `sqlite3`. For normal operation you need none
  of these scripts.
- **Three tasks without AI** internally call such a zsh script: “Refresh views”
  (`views-refresh`: Excel export, daily digest, search index, report icons), “Create cover letter
  Word + PDF” (`cover-letter-render`, the button in the cover letter window) and “Update coach site”
  (`coach-site`). On Windows they end in the Task Centre as failed with “Binary '/bin/zsh' nicht
  gefunden”, without anything else crashing. “Refresh views” is the second-to-last step of the daily
  run. On Windows the daily run therefore ends with this failed step, and the last step (coach site)
  is cancelled. The results of the earlier steps (job search, sweeps, applied check, inbox) are kept.
  On Windows, you get the Excel export and the daily digest with the buttons on the
  dashboard, and the search index with “↻ Update index” on the Search page. Cover letters are still
  created as a Word and PDF file when you create them with “Create cover letter”. The Python modules
  behind the tasks can also be called from a command prompt in the `backend` folder, for example the
  Excel export:
  `"%USERPROFILE%\.bewerbung_mgmt_venv\Scripts\python.exe" -m pipeline.export_excel`
- **Data backup:** The automatic daily backup runs on Windows just as on the Mac; it is pure Python
  inside the server process. Only the additional helper script `scripts/backup_db.sh` for a manual
  backup runs on the Mac only. On Windows, back up by hand with “Back up now” in Settings.
- **AI runs through the Task Centre** (`backend/app/agent_runner.py`): Starting and cancelling the
  background processes have been adapted for Windows (`CREATE_NEW_PROCESS_GROUP`, `taskkill /T /F`),
  but are not yet verified. Watch the first runs closely. After a server restart, BMS on the Mac
  checks whether a process still recorded as “running” really is its own (command line and start time
  via `ps`) before it ends it. Windows has no `ps`. If the process of such a run is still alive after
  the restart, BMS therefore does not end it. It marks the run in the Task Centre as failed
  (“identity NOT confirmed (protection against foreign processes), deliberately NOT ended”) and writes a warning
  to the server window. Check the process yourself in Task Manager.
- **Finding Codex (ChatGPT):** If BMS has ChatGPT selected as the AI, the Task Centre starts the Codex
  CLI through the environment variable `CODEX_BIN` or otherwise as `codex` from the PATH. In
  PowerShell, write `codex.cmd` instead of `codex` (otherwise PowerShell often blocks the script, as
  with `npm.cmd`).
- **Finding Claude Code:** The Task Centre starts Claude Code through the environment variable
  `CLAUDE_BIN` or otherwise as `claude` from the PATH. The Advisory Board searches in this order:
  `CLAUDE_BIN`, then the PATH (on Windows also `claude.cmd` and `claude.exe`), and last
  `~/.local/bin/claude`. If Claude Code is not in the PATH, set
  `set "CLAUDE_BIN=C:\Pfad\zu\claude.exe"` in a command prompt and start BMS from the same window with
  `start_windows.bat`.
- **PDF creation on timeout:** If a conversion hangs for more than 180 seconds, BMS ends LibreOffice
  with `os.killpg`, which does not exist on Windows. In this rare case the conversion on Windows
  aborts with an internal error (`AttributeError`) instead of the usual message. Normal conversions
  are not affected.
- **File permissions:** see “Access key and secrets” above.
- **Wi-Fi mode:** For access from a phone or tablet there is `start_lan.command` on the Mac, and no
  separate file on Windows. It can be done by hand, also not verified, in a command prompt in the
  `backend` folder:
  `set "HOST=0.0.0.0" && set "PORT=8000" && "%USERPROFILE%\.bewerbung_mgmt_venv\Scripts\python.exe" run_server.py`
  The quotation marks in the `set` commands prevent the space before `&&` from ending up in the value. On the
  first start, the Windows firewall may ask for permission. Other devices open BMS at the IP address
  of the PC (`ipconfig`, for example `http://192.168.1.20:8000`) or at its computer name without a
  dot. BMS rejects other names, such as one from the router (`pc.fritz.box`), with “Address not
  allowed”. You can allow them with `set "BMS_HOSTS=pc.fritz.box"` in the same command prompt before
  the start, with several names separated by commas. BMS has no sign-in protection: use Wi-Fi mode
  only in your own trusted network.
- **Automated tests:** BMS's test suite runs with every change and before every release also on a
  Windows system with Python 3.12. A released program package is only built if it is green there. It
  skips tests there that check Mac peculiarities (Unix file permissions, process groups, symlinks,
  directly executable scripts). It does not cover PDF conversion on Windows, because no LibreOffice
  is installed on the test system.

## Support matrix (short version)

| Area | Windows | Note |
|---|---|---|
| Start the server, use the interface | Yes | `start_windows.bat` |
| Stop the server | Yes, not verified | `stop_windows.bat` (netstat and taskkill, procedure as in the verified Mac version) |
| Jobs, companies, dashboard, Excel export, daily digest, search index | Yes | runs inside the server process without Mac tools |
| Automatic data backup | Yes | pure Python inside the server process |
| PDF creation (CV, cover letter) | Yes, not verified | LibreOffice in the default location or in the PATH; timeout (over 180 s) see above |
| AI runs through the Task Centre | Adapted, not verified | needs Git Bash and the `bin` → `Scripts` link |
| AI runs with ChatGPT (Codex CLI) | Preview, not verified on Windows | `npm.cmd install -g @openai/codex`, `codex.cmd login`; OpenAI recommends Windows 11, the preferred sandbox needs administrator rights once |
| Advisory Board | Yes, not verified | Claude Code through `CLAUDE_BIN` or the PATH |
| Detect and end orphaned processes after a restart | Limited | no `ps`: nothing is ended automatically |
| Tasks “Refresh views”, “Create cover letter Word + PDF”, “Update coach site” | No | “Binary '/bin/zsh' nicht gefunden”, workaround see above |
| Scheduled automation | No | template for the Mac only (`launchd`) |
| Helper scripts `scripts/*.sh` | No | zsh or `sqlite3` needed |

## Further reading

- **`BMS_Install_Windows.en.md`**: the guided installation on Windows, then setting up, installing
  updates, “If something goes wrong” and the Windows limits in short form
  (“What is restricted on Windows”).
- **`docs/en/ANLEITUNG.md`**: everyday work with BMS.
- In BMS, “📖 Documentation” in the sidebar opens all the guides in tabs.
