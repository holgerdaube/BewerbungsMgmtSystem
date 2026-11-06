# BMS: Installation and Setup on macOS

This guide puts BMS – Job Application Management System on your Mac. You first install a few
free programs, then BMS itself, and then set it up for you: profile, CV, target roles and search
region. The technical part takes about 45 minutes, the setup one to two hours. One tip before you
start: request your LinkedIn data export (section “Importing career history and skills from LinkedIn”
under “Setup: BMS gets to know you”) today if you can. LinkedIn needs up to 24 hours
to make the archive available.

You do not need any programming skills. In a few places you enter commands in the Terminal.
The assistant in the chat gives you each command to copy and tells you what it does.

This is how the file is organised: the “Instructions for the AI” guide you through the installation (Step 0 to
Step 10). From “After the installation” onwards, everything is for day-to-day use: setup, checking,
updating, help with problems and your data. If you have a Windows PC, use the guide
`BMS_Install_Windows.en.md`.

For now, a few things stay in German: the terminal output of the start, stop and update scripts, the headings in `config/profil.md` and the settings in `config/scoring_rubrik.md` (the assistant helps you edit them). The preset job portals are aimed at Germany.

## How to start

1. Open **Claude Desktop** or **ChatGPT** (app or chatgpt.com) and start a new chat, in Claude Desktop
   also a new Code session. Which AI you use here for the installation and which one BMS uses later
   for its AI functions are two separate decisions.
2. Attach this file (`BMS_Install_MAC.en.md`) to the message.
3. Write with it: **“Guide me through the installation of BMS using this guide.”**
4. Have ready: your account with the AI that BMS should use for its AI functions: Claude (Pro
   or Max) or ChatGPT (Plus or Pro). BMS itself is free and needs no licence. The guide
   downloads the program package from GitHub itself. You only need a BMS ZIP file (`BMS_<Version>.zip`)
   as a fallback if the download does not work.
5. Decide which folder BMS should live in. The assistant asks you about it right at the start
   and suggests the folder `BMS` in your user folder (`~/BMS`). In the rest of this guide
   this folder is called “your BMS folder”. Two rules for the choice:
   - **No synchronised folder.** BMS stores your data in a single
     database file that is written to constantly while you work. Cloud storage such as iCloud
     Drive, OneDrive or Dropbox does not synchronise such files reliably and can
     damage them. So not on the Desktop and not in “Documents” if these are
     backed up to iCloud (System Settings, your name, iCloud, Drive) or by OneDrive.
   - **A new or empty folder.** If a BMS is already there, do not install over it,
     update it instead (section “Installing updates”).

This guide assumes a Mac on which no BMS is installed yet under your user account. The assistant
checks this in Step 1. If there is already one, update it (section
“Installing updates”), or deliberately install a second one alongside. The assistant gives you the notes
on this in Step 1.

The assistant now guides you step by step. For each step you get exactly the commands that
you paste into the **Terminal** (⌘ + Space, type “Terminal”, Return, paste the command,
Return). Afterwards it asks whether the command ran and checks the result with you. It only
moves on once a step went cleanly. Allow about 45 minutes.

If you install without the assistant, run the commands of Steps 1 to 9 yourself and fill in the
placeholders (`INSTALLVERZ` for your BMS folder, `ZIP-PFAD` for the path of the ZIP file, `VERSION` for
the version number) by hand.

## What you need

| | macOS |
|---|---|
| Computer | current macOS, Apple chip or Intel |
| Rights | your administrator password |
| Disk space | about 2 GB free |
| Internet | to download the program package from GitHub, for the installation and for the AI functions |

You also need:

- BMS itself is free. It is open source under the Apache Licence 2.0, you buy nothing
  and unlock nothing. The guide downloads the program package from GitHub; you do not need an
  account for that.
- A subscription to one of the two AIs if you want to use the AI functions: **Claude** (Pro or Max,
  Anthropic) or **ChatGPT** (Plus or Pro, OpenAI). The AI functions of BMS, that is research,
  company check, CV tailoring and cover letters, run with Claude through the program Claude Code,
  with ChatGPT through the program Codex CLI, in each case through your own account. You pay the costs
  directly to the provider. Without a subscription you can record, manage and analyse jobs, but you cannot use the
  AI functions.
- On choosing the AI: Claude is the default and the best-tested route. With ChatGPT, the
  content of the AI runs goes to OpenAI instead of Anthropic. ChatGPT is a preview in BMS: the runs without email are tested, the email runs and the daily run are not yet. There is no budget limit per run, the limits of your subscription apply, and many runs in a row can push a Plus account to its limit. The assistant asks you in Step 0
  about this. You can switch the AI later in “Settings”, card “AI”.
- Optionally an email account with IMAP access, so that BMS recognises replies to your applications in
  your mailbox.
- Optionally a LinkedIn account, to import your career history and skills from the data export.
- Only as a fallback: a BMS ZIP file (`BMS_<Version>.zip`) in case the download does not work, for example
  because a company network blocks access to GitHub. You download it in the browser from the page
  https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/latest.

# Instructions for the AI: guided installation

From here on, the instructions are for the AI in the chat that guides the installation (Claude, ChatGPT or
another assistant). They are not meant for the user. For the user, the guide continues under “After the
installation”.

You speak English with the user. You guide a user through the installation of BMS – Job Application Management System on their
Mac. You work as a guide: **The user runs all commands themselves in the Terminal, you give them
out and check the results.** This applies even if you could run commands yourself in this session.

Which AI BMS uses later for its AI functions, Claude or ChatGPT, is independent of this.
You ask about it in Step 0. Where this guide says “the AI choice”, it means that answer.

## Conversation rules

1. **One step at a time.** In each message, give exactly one step (or one sub-step)
   with its commands. Do not jump ahead, even if the user is in a hurry.
2. **Commands in their own code blocks** (` ```sh `), complete, ready to copy and
   paste, with all paths already filled in. Never use placeholders such as `<Verzeichnis>`
   in what the user copies. Fill in the details from Step 0 yourself. The commands in
   this guide carry placeholders in capital letters, which you replace before output:
   `INSTALLVERZ` (the installation folder), `ZIP-PFAD`, `VERSION` (from the information in
   Step 4). Several lines in one block are fine if they belong together.
   For paths:
   - Write them without a tilde. Replace a `~` at the start with `$HOME` (`~/BMS` becomes
     `$HOME/BMS`), because the shell does not resolve the tilde inside quotation marks.
   - If a path the user gives contains backslashes before spaces (`\ `, which is what you get when
     you drag a file into the Terminal), leave the backslashes out. The templates put the
     path in quotation marks.
3. **Ask after every command block**, in this form: “Did the command run? Please copy the output
   in here.” Say how the user can recognise success, so they do not have to guess
   (“`Python 3.12.x` should appear.”).
4. **Check the result.** Compare the pasted output with what the step expects. Confirm
   briefly (“That fits.”) and only then go to the next step. If the output differs or
   an error message appears, say in one sentence what is going on and give exactly one
   corrective command. If that does not help after two attempts, stop, explain the situation honestly and
   go to Step 10 (log and abort). Do not guess and do not claim a success that is not
   proven.
5. **Language:** short sentences, no technical jargon, polite direct address with “you”.
6. **Secrets:** The access key (token) and the Mac password must never appear in the chat.
   Explicitly ask the user not to paste them. They type the password only in the Terminal.
   With ChatGPT there is no key to paste; the sign-in only happens in the browser.
   If an output could contain secrets, give a command that only prints “present”
   or “missing”. The response from GitHub (the information in 4a, Step 4) contains no secrets
   and may go into the chat.
7. **Nothing destructive.** Do not delete or overwrite anything without explicit consent. An
   existing, non-empty installation folder is never overwritten (Step 2), and neither is an
   existing access key (Step 7).
8. **Administrator rights:** Homebrew asks for the Mac password in the Terminal (Step 3). Announce
   this before the command.
9. **Show progress.** Begin every reply with a line such as “Step 4 of 10: Download
   and unpack BMS”.
10. **Keep a log.** Internally keep for each step the command, the result (OK/ERROR/SKIPPED)
    and, for errors, the full message. The log is created in Step 2 and written in
    Step 10 (details there).

## Step 0: Collect the details

Greet the user briefly and ask the following things **in a single message**. Wait for
the answers.

1. **Installation folder.** “In which folder should BMS be installed? Suggestion:
   the folder `BMS` in your user folder, that is `~/BMS`.” Check the answer:
   - It must be a full path (e.g. `~/BMS` or `/Users/Name/BMS`; `~` stands for the
     user folder).
   - **Not** in a folder that iCloud Drive, OneDrive or Dropbox synchronises, and not
     on the Desktop and not in “Documents” if these are backed up to iCloud
     (System Settings, your name, iCloud, Drive) or by OneDrive. Reason: The
     database is written to constantly and can be damaged during synchronisation. Explain
     this in one sentence and give the suggestion.
   - The path may contain spaces. Put it in quotation marks in all commands, as in
     the templates below.
   We call this path **the installation folder** from now on. Fill it into all later
   commands, without a tilde (conversation rule 2). If the user gives no path or only writes
   “yes” or “suggestion”, the suggestion applies.
2. **Existing ZIP file (optional).** “Do you already have a BMS ZIP file (`BMS_<Version>.zip`), for
   example downloaded from the browser? Then please give me the full path (usually
   `~/Downloads/BMS_2.0.0.zip`). Otherwise we fetch the program package from GitHub together in Step 4;
   you do not need to have anything ready for that.” If the user names a ZIP file, the download is skipped in
   Step 4 (4a to 4c), and it continues with unpacking (4d). If they name none, the download from
   GitHub applies.
3. **AI functions:** “Would you like to set up the AI functions (research, company check,
   CV, cover letter)? For that you need a subscription to an AI and about 10 more minutes.”
   (Yes/No, can be done later.) With “No”, point 4 is skipped.
4. **Which AI** (only for “Yes” to point 3): “Which AI should run the AI functions: **Claude**
   (Anthropic, Pro or Max subscription) or **ChatGPT** (OpenAI, Plus or Pro subscription)?” Say in a few
   sentences: Claude is the default and the best-tested route. With ChatGPT, the content of the
   AI runs goes to OpenAI instead of Anthropic. ChatGPT is a preview in BMS: the runs without email are tested, the email runs and the daily run are not yet. There is no budget limit per run, the limits of the subscription apply, and many runs in a row can push a Plus account to its limit. If the user asks about Gemini: BMS
   deliberately does not offer it, because Google’s rules do not allow the subscription in apps. If the user makes no choice,
   Claude applies. This answer is called **the AI choice** from now on. It determines Steps 3, 7 and 8 and
   the check in Step 9. It can be changed later in “Settings”, card “AI”. Then
   the program of the other AI must be installed and its sign-in done (Steps 3 and 7 for
   that AI).

Afterwards, repeat the chosen installation folder and the AI choice in one sentence (“BMS will be
installed in …, with Claude as the AI.”, likewise with ChatGPT or “without AI functions”) and
have it confirmed before you begin Step 1. After that the folder is not changed any more.

The **log** is in the installation folder as `Installprotokoll.md`. Tell the user this.

## Step 1: Check the requirements

Command (the user opens the Terminal with ⌘ + Space, types “Terminal”, Return, and
pastes):

```sh
sw_vers -productVersion
uname -m
df -h "$HOME"
curl --version | head -1
ls -d ~/.bewerbung_mgmt_venv ~/.bewerbung_mgmt_secrets 2>/dev/null
```

What to expect, line by line:

- a macOS version (the guide assumes a current macOS);
- `arm64` (Apple chip) or `x86_64` (Intel);
- the free disk space: in the `Avail` column **at least 2 GB**. If the installation folder
  is on another drive (the path begins with `/Volumes/`), replace `$HOME` with
  `/Volumes/Name`;
- a line that begins with `curl`;
- **no further output.**

If the user named a ZIP file in Step 0 (fallback), you check that file instead of `curl`:
In the block, put the line `test -f "ZIP-PFAD" && echo "File present: yes" || echo "File present: no"`
in place of the line `curl --version | head -1`. Expected at that point: `File present: yes`.
For `no`: clarify the path.

**If the last command prints anything, there is already a BMS under this user account.** Stop
and clarify with the user:

- If they want to update the existing BMS, `update.command` in the folder of that BMS is the right
  way, not this guide (section “Installing updates”).
- If they deliberately want to install a second BMS alongside, explain: Both share the
  Python environment (`.bewerbung_mgmt_venv`) and the credentials (`.bewerbung_mgmt_secrets` with
  access key and email access), but each installation has its own data. Both should have
  the same program version, because Step 5 replaces the components for both. Step 7
  does not overwrite the existing access key. Only one BMS can run at a time. Only continue once the user
  explicitly confirms this.

Fallback only: Optionally, if there is a file `…zip.sha256` next to the ZIP file, give the
check command `shasum -a 256 "ZIP-PFAD"` (the same as under 4c in Step 4) and compare the
first word of the output with the content of the `.sha256` file (`cat "ZIP-PFAD.sha256"`). If the
values do not match (upper and lower case do not matter), the ZIP file is damaged: have it downloaded
again.

## Step 2: Create the installation folder and start the log

The command creates the folder and shows what is in it. That also checks that the
folder is not already in use:

```sh
mkdir -p "INSTALLVERZ" && ls -A "INSTALLVERZ"
```

- No output: The folder is new or empty. Have the user confirm that nothing appeared, and
  carry on.
- Any output: The folder is not empty. **Do not overwrite.** Ask whether it is an
  existing BMS (then `update.command` in the folder is the right way, not this
  guide) or whether another folder should be chosen.

Then start the log:

```sh
printf '# BMS-Installprotokoll\nBeginn: %s\nVerzeichnis: %s\n\n' "$(date '+%d.%m.%Y %H:%M')" "INSTALLVERZ" > "INSTALLVERZ/Installprotokoll.md"
cat "INSTALLVERZ/Installprotokoll.md"
```

Expected: The output shows the three header lines.

## Step 3: Install the programs

BMS needs four programs: Python 3.12 (the programming language of BMS), Node.js (builds the
interface once), the AI program (with Claude that is Claude Code, with ChatGPT the Codex CLI;
it runs the AI functions) and LibreOffice (creates PDF files from the CVs). In addition there is
Homebrew, a widely used, free tool that installs programs on the Mac. First check
what is already there, so that nothing is installed twice:

```sh
command -v brew >/dev/null && echo "brew:   yes" || echo "brew:   no"
command -v node >/dev/null && echo "node:   yes" || echo "node:   no"
command -v claude >/dev/null && echo "claude: yes" || echo "claude: no"
command -v codex >/dev/null && echo "codex:  yes" || echo "codex:  no"
[ -d /Applications/LibreOffice.app ] && echo "office: yes" || echo "office: no"
```

### 3a: Homebrew (only if `brew: no`)

If the user already has Homebrew, skip 3a. Otherwise announce: “The installation asks for
your Mac password and takes a few minutes. You type the password only in the Terminal, never here
in the chat.”

```sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

The end of the output is important: If Homebrew shows commands under “Next steps”, the user must
copy and run them, otherwise the Terminal will not find Homebrew and the programs from 3b. Have
the end of the output pasted, repeat the commands under “Next steps” word for word in
one block and then check:

```sh
brew --version
```

Expected: a Homebrew version. The current installation command is also at
[brew.sh](https://brew.sh).

### 3b: Programs

The following commands only install what is still missing. Homebrew installs Python in every
case, because BMS uses exactly this Python 3.12 (Step 5). Any other Python on the Mac
is left untouched. You may leave out lines whose program the check above has shown as present;
the line for Python always stays. For “No” in Step 0, point 3, and for ChatGPT,
you leave out the line with `claude-code`. Announce that this takes a few minutes.

```sh
brew install python@3.12
command -v node >/dev/null || brew install node
command -v claude >/dev/null || brew install --cask claude-code
[ -d /Applications/LibreOffice.app ] || brew install --cask libreoffice
```

For ChatGPT you give this line instead:

```sh
command -v codex >/dev/null || brew install --cask codex
```

If Homebrew reports an error here, it also works through Node.js:

```sh
npm install -g @openai/codex
```

If the user has already installed Node.js, Claude Code, Codex or LibreOffice another way, it stays
that way, and no second copy is created alongside. Node.js should then be version 18 or newer.
If Homebrew reports for a program that it is already installed, that is fine. Then check whether
everything is there:

```sh
"$(brew --prefix python@3.12)/bin/python3.12" --version
node --version
test -d /Applications/LibreOffice.app && echo "LibreOffice: yes" || echo "LibreOffice: no"
```

Additionally for Claude:

```sh
claude --version
```

Additionally for ChatGPT:

```sh
codex --version
```

Expected: `Python 3.12.x`, a Node version (18 or newer), `LibreOffice: yes`, with Claude a
Claude version, with ChatGPT a Codex version (0.166.0 was tested). Notes:

- “command not found” for `brew`, `claude` or `codex`: The “Next steps” commands from Homebrew are missing (3a).
  Then reopen the Terminal.
- If Node.js is older than version 18, clarify the approach with the user before you install
  anything. Trying `brew install node` is possible; afterwards check `node --version`.
- `LibreOffice: no`: Without LibreOffice, no PDF files will be created later. Give the LibreOffice line
  from 3b again.

## Step 4: Download and unpack BMS

If the user named no ZIP file in Step 0, they fetch the program package from GitHub, where BMS
is published (4a to 4c). They need neither an account nor a sign-in for this. Announce this
beforehand: “Your Mac now asks GitHub for the latest version and downloads the package. GitHub receives
your Mac’s IP address, nothing else, and only in response to these commands.”

If they named a **ZIP file** instead (fallback), 4a to 4c are skipped, and it continues with 4d.
`ZIP-PFAD` is then the path they named.

In 4b to 4d, `ZIP-PFAD` is the user’s “Downloads” folder plus `BMS_VERSION.zip`, for
example `$HOME/Downloads/BMS_2.0.0.zip`, with the version from 4a. If it is unclear where “Downloads” is,
ask.

### 4a: Get the release information

```sh
curl -sS -H "Accept: application/vnd.github+json" "https://api.github.com/repos/holgerdaube/BewerbungsMgmtSystem/releases/latest"
```

Expected: a longer text over many lines, beginning with `{` and containing, among other things, `"tag_name"` and
a list `"assets"`. The user pastes it in full. From it you take two values:

- `VERSION`: the value of `tag_name` without the `v` at the start (`"tag_name": "v2.0.0"` becomes `2.0.0`);
- the expected checksum: in the `assets` entry whose `name` is exactly `BMS_VERSION.zip`, the
  value of `digest` without the prefix `sha256:`. (Next to it there is an entry `BMS_VERSION.zip.sha256`.
  You do not use that one.)

Remember both values and put `VERSION` into the following commands. The output contains no
secrets and may go in the chat. If the entry `BMS_VERSION.zip` or its `digest` is missing, install
nothing you cannot verify: Take the fallback (see failure case) and check the ZIP file in
Step 1 against the file `BMS_VERSION.zip.sha256` from the release page.

### 4b: Download the package (`VERSION` from 4a)

If a file already exists at `ZIP-PFAD` (check with `test -e "ZIP-PFAD" && echo present`), ask
first whether it may be replaced (conversation rule 7).

```sh
curl -fsSL -o "ZIP-PFAD" -w "Response: %{http_code}\n" "https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/download/vVERSION/BMS_VERSION.zip"
```

Expected: `Response: 200`. The file is then in the “Downloads” folder. During the download, GitHub redirects to
its download server. The command follows this redirect itself; that is normal.

### 4c: Compute the checksum

```sh
shasum -a 256 "ZIP-PFAD"
```

Compare the first word of the output with the `digest` value from 4a; upper and lower case do not matter.
If it differs, have the package downloaded again once (4b). If it differs again, proceed as in the failure case:
have the file deleted and offer the fallback.

**Failure case.** If 4a shows a message from curl or a short text with
`"message"` (such as `Not Found` or `API rate limit exceeded`) instead of the information, that is the reason. There is
no file yet in that case: Have the command repeated once. If 4b does not show `Response: 200` but another
number (such as `Response: 404`) or a message from curl, that is the reason. In that case too, and equally for a
different checksum, no unusable file should be left behind. The following command deletes it and
reports nothing if it is not there at all:

```sh
rm -f "ZIP-PFAD"
```

Explain the reason in one sentence and have the package downloaded again once (4b). If that fails again, offer
the fallback: The user opens
`https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/latest` in the browser, downloads the file
`BMS_VERSION.zip` there under “Assets” and saves it in the “Downloads” folder. You repeat Step 1 for this file and
continue with 4d. If the user cannot get the file this way either, stop and write the log
(Step 10). What the responses mean is in the section “If something goes wrong”.

### 4d: Unpack

The first command unpacks the package into the BMS folder, the second changes into it. The third
removes the download mark with which macOS tags files loaded from the internet. Without it,
macOS later refuses to start by double-click, because BMS is not an App Store program. The
fourth makes the start files executable.

```sh
unzip -q "ZIP-PFAD" -d "INSTALLVERZ"
cd "INSTALLVERZ"
xattr -dr com.apple.quarantine "INSTALLVERZ"
chmod +x "INSTALLVERZ"/*.command
ls
```

Expected: The list contains, among other things, `start.command`, `backend` and `frontend`.

Final check:

```sh
test -f "INSTALLVERZ/backend/requirements-lock.txt" && test -f "INSTALLVERZ/frontend/package.json" && test -x "INSTALLVERZ/start.command" && echo "Files present" || echo "Files missing"
```

Expected: `Files present`.

## Step 5: Set up the Python environment

Announce: “This takes a few minutes and prints a lot of text.”

```sh
"$(brew --prefix python@3.12)/bin/python3.12" -m venv ~/.bewerbung_mgmt_venv
~/.bewerbung_mgmt_venv/bin/pip install -r "INSTALLVERZ/backend/requirements-lock.txt"
```

In the hidden folder `.bewerbung_mgmt_venv` in the user folder, this creates a separate Python environment
and installs the components BMS needs there. BMS looks for this environment in exactly
this place; the user does not rename the folder and does not move it.

The long first command deliberately uses the Python from Step 3. Many Macs have a second
Python, for example from another program, and a plain `python3.12` might pick that one up. BMS
then does not start.

Check:

```sh
~/.bewerbung_mgmt_venv/bin/python --version
~/.bewerbung_mgmt_venv/bin/python -c "import fastapi, uvicorn; print('Components ok')"
```

Expected: `Python 3.12.x` and `Components ok`. If `pip install` shows an error: Ask for the
last lines of the output and check whether Python 3.12 was really used.

## Step 6: Build the interface

This downloads the components of the interface and assembles them. It takes one to two minutes. Without
this step BMS does start, but shows an empty page in the browser.

```sh
cd "INSTALLVERZ/frontend"
npm ci
npm run build
cd "INSTALLVERZ"
test -f "INSTALLVERZ/frontend/dist/index.html" && echo "Interface built" || echo "Interface missing"
```

Expected: The build ends with a line “built in …” and without the word “error”; the last
output is `Interface built`. Warnings often appear along the way, for example about `fsevents`, about
`approve-scripts` or containing the words “deprecated” and “vulnerabilities”. They are harmless for the
installation. Tell the user this beforehand, so they do not mistake them for errors.

## Step 7: Set up AI access (only for “Yes” in Step 0, otherwise log as SKIPPED)

The AI choice from Step 0 decides which branch applies. With **Claude** you go through 7a to 7d, with
**ChatGPT** 7e and 7f. The branch that does not apply you log as SKIPPED.

### Branch Claude: 7a to 7d

**Important:** Tell the user beforehand that they must **not paste** the key that appears shortly
**into the chat**.

7a. Sign in:

```sh
cd "INSTALLVERZ"
claude
```

On first start, Claude Code asks for a colour scheme and for the sign-in method. The user
chooses sign-in with their Claude account. Claude Code then opens the browser, where they sign
in and confirm access. If Claude Code then asks whether they trust the files in this folder, they
confirm. Back in the Terminal they quit Claude Code with `/exit`.

7b. Create the access key. BMS starts the AI functions in the background without a
browser window opening. For that it needs its own access key:

```sh
claude setup-token
```

After confirmation in the browser, the Terminal shows a long key. The user copies
it in full to the clipboard.

7c. Create and open the file:

```sh
mkdir -p ~/.bewerbung_mgmt_secrets && chmod 700 ~/.bewerbung_mgmt_secrets
cp -n "INSTALLVERZ/automation/agent.env.example" ~/.bewerbung_mgmt_secrets/agent.env
chmod 600 ~/.bewerbung_mgmt_secrets/agent.env
open -e ~/.bewerbung_mgmt_secrets/agent.env
```

The second command only copies the template if the file does not exist yet (`cp -n`). If there was
already a BMS on this computer, the existing file with the access key is kept.
If a valid key is already in there, the user does not need to change anything (7b can then be skipped
if the key is still valid).

Instructions for the text window: “Find the line that begins with `# CLAUDE_CODE_OAUTH_TOKEN=`.
Remove the `#` and the space at the start of the line and replace everything after the `=` with
your key, including the example `sk-ant-oat01-...`. The key must be
on a single line. Save with ⌘ + S and close the window.” The file is deliberately outside the
program folder and readable only by the user’s own account.

7d. Check without showing the key:

```sh
grep -Eq '^CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-[A-Za-z0-9_-]{40,}[[:space:]]*$' ~/.bewerbung_mgmt_secrets/agent.env && echo "present" || echo "missing"
```

Expected: `present`. For `missing`: Check the line (no `#`, value after the `=`, one line). The example
`sk-ant-oat01-...` must no longer be in the line.

### Branch ChatGPT: 7e and 7f

With ChatGPT there is no key to paste and no file `agent.env`: The sign-in happens in the
browser and stays in the Codex program. Tell the user beforehand: “The browser will open shortly. Sign
in there with your ChatGPT account (Plus or Pro).”

7e. Sign in:

```sh
codex login
```

Codex opens the browser. The user signs in with their ChatGPT account and confirms
access. The command in the Terminal then returns to the prompt.

7f. Check:

```sh
codex login status
```

Expected: `Logged in using ChatGPT`. For any other output, repeat 7e. If that does not help after two
attempts, stop (conversation rule 4).

## Step 8: First start and self-test

The server runs in the Terminal window that the start opens. This window must stay open.

In the program folder, this command makes BMS start in English, with English sample data:

```sh
mkdir -p data && echo en > data/startsprache
```

Start:

```sh
open "INSTALLVERZ/start.command"
```

This is the same as a double-click on `start.command` in the Finder. A Terminal window opens, and after a few seconds the browser with BMS at `http://localhost:8000`. Ask:
“Did BMS open in the browser? Is there an error message in the Terminal window?” Then, in a
**new** Terminal window:

```sh
curl -s http://localhost:8000/api/version; echo
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/
test -f "INSTALLVERZ/data/bewerbung.sqlite" && echo "Database present" || echo "Database missing"
```

Expected: A response with the program version; `200`; `Database present`.

A note the user should not take as an error: On first start, BMS creates what
it needs itself: the data folder, the database and a basic version of the search settings. It also
fills itself once with sample data of an invented person (“Benno Bewerbaer”). That is normal.

If the start aborts: The user should paste the last lines of the Terminal window.

- If it reports “venv not found”, go back to Step 5.
- If it reports “address already in use”, BMS is already running. In that case check the version query
  above.
- “start.command cannot be opened”: The `xattr` command from Step 4d is missing. Alternatively,
  the user chooses System Settings, Privacy & Security, “Open Anyway”.
- If the start reports something about `cryptography` or “symbol not found”, the Python environment was created with
  a different Python. Ask for the user’s explicit consent, then give
  `rm -rf ~/.bewerbung_mgmt_venv` (it deletes only the Python environment, no data) and repeat
  Step 5.

**ChatGPT only: switch the AI.** BMS starts with Claude as the AI. With ChatGPT, the user switches
once now, either in “Settings” (card “AI”, choose ChatGPT) or in the Terminal. For
the Terminal, give in a **new** window:

```sh
curl -s -X PATCH http://localhost:8000/api/einstellungen -H 'Content-Type: application/json' -d '{"ki_anbieter":"chatgpt"}' > /dev/null
curl -s http://localhost:8000/api/einstellungen | grep -o '"ki_anbieter":"[a-z]*"'
```

Expected: `"ki_anbieter":"chatgpt"`. With Claude there is nothing to do; Claude is the default.

## Step 9: Acceptance

Go through these points one after another with the user. Ask each time what they see, and
log OK or PROBLEM with the wording.

1. Open “Settings”: all cards appear without an error message.
2. Card “Sample data” → “Remove sample data”: The sample data disappears.
3. “Jobs” → “+ Add job” → record a test company: It appears in the list.
4. Only with AI setup: check the access of the chosen AI. With Claude, 7d has already reported `present`.
   With ChatGPT, give in a Terminal window:

   ```sh
   codex login status
   curl -s http://localhost:8000/api/ki-status
   ```

   Expected: `Logged in using ChatGPT`, and in the response of the second command the entry
   `"chatgpt"` shows `"installiert":true,"angemeldet":true`.
5. Only with AI setup: In this job, start “Check company fit”. The run appears in the
   “Task Centre” and ends after a few minutes (with Claude about ten) with a result. Ask about
   the status and, in case of an error, have the message from the Task Centre quoted in full. If
   a ChatGPT run reports that the usage limit of the subscription has been reached, that is not an installation error: The
   run is started again later.
6. Dashboard: trigger the Excel export. A file is created.
7. Quit and restart: In the BMS Terminal window press Ctrl + C, then

   ```sh
   open "INSTALLVERZ/start.command"
   ```

   BMS starts again. (If the window cannot be closed, a double-click on
   `stop.command` in the BMS folder helps, or `open "INSTALLVERZ/stop.command"`.)

Finally, point out to the user that “Create CV” (PDF through LibreOffice) can only be checked after
a profile and base CV have been set up. They enter the profile in the interface: on
the “Profile” page in the first card “Identity and search strategy” (name as a required field, address
as `Street No, Postcode Town`, contact details, short profile, target date, constraints). Then they upload the
base CV, likewise on the “Profile” page. This is part of the setup, which is described in the
section “Setup: BMS gets to know you” further below and in `docs/en/ANLEITUNG.md` in the
installation folder.

## Step 10: Write the log and wrap up

The log should be in `INSTALLVERZ/Installprotokoll.md` and contains for each step: number,
title, result (OK, ERROR, SKIPPED) and, for errors, the full message. At the end there is
a section “Open items”. **It never contains keys or other secrets.**

- If you can write files on the user’s Mac in this session, do so directly.
- Otherwise give the user **one** command that appends the log. Insert the text between
  the two lines. The line `EOF` stands alone at the start of the line:

  ```sh
  cat >> "INSTALLVERZ/Installprotokoll.md" <<'EOF'
  <hier das fertige Protokoll im Markdown-Format>
  EOF
  cat "INSTALLVERZ/Installprotokoll.md"
  ```

  Ask whether the content appears in the output.

**Also on abort** (two correction attempts without success): Write the log with the state so far
and the error, so that the installation can be continued later in a targeted way or the error
can be fixed.

Finally, summarise in at most ten lines:

- what was installed (with versions from the checks) and which AI is chosen,
- what works and what does not (also honestly what could not be checked),
- how BMS is started in future (`INSTALLVERZ/start.command` by double-click in the Finder) and
  quit (Ctrl + C in the Terminal window, otherwise `INSTALLVERZ/stop.command` by double-click),
- where the log is.

Then offer to continue with the setup: “Would you like to set up BMS for you now?
That takes one to two hours and can be interrupted at any time.” The basis is the
section “Setup: BMS gets to know you” under “After the installation”. If the user says
yes, go through that section with them, in the order given there and following the same
conversation rules (one section per message, access key never in the chat). If they say no, point out
that the section is always in this file.

# After the installation

This part is for you. It applies as soon as BMS is running. The assistant also uses it as the
basis if you carry on with the setup after the installation.

## Setup: BMS gets to know you

BMS is running now, but only shows sample data and does not yet know anything about you. You do the following
steps once and in this order: first remove the sample data, then
the five sections from “Your profile: identity and search strategy” to “Search area in the job list”.
You need these so that BMS can work for you: Without a profile and CV, neither
cover letters nor CVs are created; without target roles and region, the job search finds nothing suitable. The
email connection under “Connect an email mailbox” is optional.

### First: remove the sample data

On the very first start, BMS brings sample data of “Benno Bewerbaer”, an invented person:
a postman with five years of experience in parcel delivery. This includes six companies, five jobs at
different stages, three applications, five emails, an interview appointment, a profile with skills
and career history, the profile file `config/profil.md` and an English base CV. With it you can
try out BMS. As long as the sample data is there, the Dashboard shows a notice, and
the sidebar shows “Benno Bewerbaer” as your name. Anyone who has already used BMS gets no
sample data, and an update brings none.

Remove the sample data before you enter your own data:

1. Open “Settings” and look for the card “Sample data”.
2. Click “Remove sample data” and confirm with “Yes, remove”.

Beforehand, BMS makes a backup of your database, in the folder `data/backups/auto`, where
“Back up now” also puts its backups. If the backup fails, everything stays unchanged, and the card names
the reason. After that:

- Only the sample data and what is attached to the sample jobs is deleted. What you created yourself stays, including emails that you
  assigned to a sample job: They are kept as
  emails without a job.
- The profile file and the base CV move to the bin `data/papierkorb/`, but only
  if you have not changed them. A version of your own stays, and the card tells you
  which.
- After that the sidebar shows “Applicant” until you save your name in the profile under “Your profile: identity and
  search strategy” (see below).

If you have already saved your profile (card “Identity and search strategy”, see below) or
edited the file `config/profil.md` by hand before you remove the sample data, BMS recognises
the file as your own and leaves it. Then go through the card once in full and
replace everything that still comes from Benno Bewerbaer: name, address, contact details, short profile, target date
and constraints. A base CV that you have already uploaded likewise stays.

The reason for the order: The LinkedIn import (see “Importing career history and skills from LinkedIn”)
fills your profile only where nothing is there yet. With the sample data in the profile, it would not take over
your positioning and would skip skills that are already there as an example. So remove
the sample data first, then enter your profile (“Your profile: identity and search strategy”)
and upload your CV (“Your CV”), and only then import from LinkedIn.

### Your profile: identity and search strategy

In the sidebar, open “Profile”. The first card is called “Identity and search strategy”. This is where you
enter who you are and what you are looking for. Name, address, contact details and LinkedIn make up the
letterhead of your cover letters and the file names of your documents. The AI reads the short profile, target date and
constraints as background when it rates jobs and writes cover letters.
If the card still shows details of “Benno Bewerbaer”, you have not yet removed the sample data.
Do that first (see above).

This is what you enter:

| Field | What goes in |
|---|---|
| Name | **Required field.** Your full name, such as “Max Mustermann”. It appears in the sidebar, in the letterhead and in the file names of your CVs and cover letters. |
| Positioning (one-liner) | Optional. A short line, such as “Service Delivery Leader, DACH”. You maintain the full positioning text further down the Profile page (see “Importing career history and skills from LinkedIn”). |
| Address | Write it as `Street No, Postcode Town`, such as `Musterweg 3, 12345 Musterstadt`. This becomes the place line of your cover letters. The same entry is the starting point of the route planning for interviews. |
| Email, Phone | Your contact details for the letterhead. |
| LinkedIn | Optional. The address of your profile, such as `https://www.linkedin.com/in/max-mustermann/`. |
| Current | Optional. Your current job in one line, such as “Manager Professional Services at Beispiel GmbH, since 2024”. |
| Short profile | Two to four sentences about you. BMS uses them as a tone template for your cover letters. |
| Target date | Optional. By when you want to change jobs, such as “new role by 31/12/2026”. You enter the title, level and industry of your target roles under “Settings” in the cards “Plan A”, “Plan B” and “Plan C” (section “Target roles and search area”). |
| Hard constraints | What is non-negotiable for you. One item per line, beginning with “- ”, such as “- No relocation, no permanent second home.” |
| Known skill gaps | Gaps in your profile that you know about yourself. One item per line. Honest entries help, because that is how the AI rates jobs realistically. |

The more specific you are, the better the ratings and cover letters fit. You can word the short profile, target date
and constraints freely.

With “Save”, BMS takes over your entries. The button is only active once you have changed something.
Afterwards it shows “✓ Saved”, and the sidebar and the route planning show the new
details straight away. In this:

- The name must be filled in. As long as it is missing, the card cannot be saved.
- If the address lacks the comma or the postcode, or the email address has no @, the
  card shows a yellow line with a note. It is saved anyway.
- Each time you save, BMS moves the previous version of the file to the bin
  `data/papierkorb/`. Nothing is lost.
- If you have changed the file in the meantime, for example by hand or through an analysis by BMS,
  the card asks you to reload. Click “Reload” and enter your change again.
  This way you never overwrite someone else’s changes by accident.

The details are in the file `config/profil.md` in the BMS folder. If you like, you can carry on editing the file
by hand. The card leaves alone what it does not know, such as the section “Empirie aus dem
Bewerbungsverlauf” (empirical data from your application history), which BMS maintains itself, and your own sections. When editing by hand,
the spelling matters: BMS recognises name, location, contact details and LinkedIn by the bold type, so the asterisks
around `**Name:**` must stay. The address is called `**Standort:**` in the file, email and
phone are together under `**Kontakt:**`, separated with `·`.

### Your CV

BMS does not invent a CV. It takes your existing one as a basis and tailors it for each
job. Upload it as a Word file (`.docx`): In the interface under “Profile”, right at the bottom
in the area “Base CVs”, choose the language, then the file, and click “Upload”.

Upload a German and an English version. BMS picks the suitable one itself, depending on the job posting.
If you only apply in German, the English version may be a copy of the
German one, but it must exist.

For BMS to recognise your positions, the CV needs a specific structure:

| Element | What it must look like |
|---|---|
| Section headings | Style “Heading 1”, in capital letters |
| Section for work experience | `BERUFSERFAHRUNG` (German) or `PROFESSIONAL EXPERIENCE` (English) |
| First line of each position | Style “Normal”: company, then a tab, then the period |
| Line directly below | Your job title, bold, font size 11, without a tab |
| Then | one to two lines of italic description of the company |
| Then | your achievements as a bulleted list with the style “List Paragraph” |

The tab between company and period is the mark of a position. So do not use it
anywhere else in the document. In other sections such as education or certificates, separate
entries with `•`.

After uploading, BMS shows how many positions it recognised. If a yellow notice appears,
the structure is still not right. Correct the file in Word and upload it again.
BMS asks before overwriting and moves the old version to the bin.

### Importing career history and skills from LinkedIn

This is the quickest way to fill the Profile page without typing everything in. On LinkedIn
go to Settings, Data privacy, “Get a copy of your data” and choose the top
option, the larger data archive. The quick option “Profile” contains only your short description and
is not enough. LinkedIn sends you an email as soon as the archive is ready.

You then upload the ZIP file from LinkedIn under “Profile” with “Upload data export ZIP”. BMS
takes over short description, location, skills, positions, education and certificates.
It only adds and overwrites nothing. Afterwards it sorts your skills in the
background into topic areas. Only upload the file once the sample data has been removed,
because with it BMS would not take over everything (reason under “First: remove the sample data”).

Without an export and without waiting, you can use “Read profile” under “Profile” if AI access is set up (Step 7). Open your
profile on LinkedIn in the browser, select everything, copy it and paste it in. Or upload the PDF that
LinkedIn creates with “Save to PDF”. The AI structures the text, you check the result in a preview, and only
then does BMS add to your profile. LinkedIn does not show everything on the profile page and in the PDF, skills often only in abbreviated form.
The export is therefore still the most complete route. There is no automatic retrieval via the address of your profile,
because LinkedIn blocks it.

Without LinkedIn, you enter positioning, career history and skills directly on the Profile page.
In both cases: Look through the result once and add what is missing. BMS uses these
details as the factual basis for cover letters and CVs.

### Target roles and search area

Under “Settings” you decide what BMS searches for. Go through the areas in this
order:

1. “Search area & company size”: whether you search remote, Germany-wide or in a local area around
   your home, and from which number of employees a company is considered.
2. The cards “Plan A”, “Plan B” and “Plan C”: your target roles with title, level and industry.
   Plan A is your actual goal, Plan B the realistic alternative, Plan C an optional
   fallback level. These fields are empty after the installation. As long as they are empty, the
   job search finds nothing, because it does not know what to look for.
3. “Search portals”: Six common portals are preset and switched on. You can switch
   individual ones off or add two of your own. The portals are aimed at Germany; outside Germany,
   use the free rows, LinkedIn alerts and the target companies.
4. “AI model per function”: The choices are Opus 5.5, Sonnet 5.5 and Haiku 4.5, and the default is
   Sonnet 5.5. The default is fine for everyday use; you do not need to change anything here. BMS
   deliberately does not offer the model Fable because it is too expensive: It costs two and a half times as much as
   Opus 5.5 and five times as much as Sonnet 5.5. If you have chosen ChatGPT as the AI, the models
   of ChatGPT are offered there, and the default is the middle tier.

### Search area in the job list

The search area from “Target roles and search area” (Remote, Germany-wide, city + local area) appears
automatically in the job list and in the filters, as its own tab labelled
“<short city name> +<km>km”, such as “München +50km” for the city München and a 50 km radius. The
short city name drops a name suffix such as “am”, “an der” or “im”: “Frankfurt am Main”
becomes “Frankfurt”, “Bad Homburg vor der Höhe” becomes “Bad Homburg”. The search itself also takes
the city and local area automatically from the Settings. You no longer need to edit a file
by hand for this.

If you change the city or radius later, BMS automatically moves all existing jobs with the old
label to the new one and then shows how many jobs were affected.

### Connect an email mailbox

This step is optional but recommended: With a connected mailbox, BMS recognises
replies to your applications and reads jobs from job notifications. Under “Settings”,
area “Email account”, you enter the access details of your mailbox. Use an
app password from your email provider there, not your normal password. How to create an app password
and which server details your provider requires is in `docs/en/SETUP-EMAIL.md` in the program folder.

BMS never sends emails itself. It only creates drafts, which you check and
send yourself.

The email check already hides some technical senders by itself. If you have private senders of your own
that sound similar to an application reply but have nothing to do with your
job search, enter them in `config/suchprofile.yaml`. Open the file with a
text editor and, below the line that begins with `# <<< ENDE AUTO-GENERIERT`, add
a block like this (domains or full addresses, one line per sender):

```yaml
email_check:
  ausschluss_absender:
    - beispielverein.example.org
    - newsletter@anderer-dienst.example.com
```

This area of the file is left untouched each time you save in the Settings. Save
the file and restart BMS so that it reads the change.

## Quick check that everything works

| Check | Expectation | If not |
|---|---|---|
| `http://localhost:8000` in the browser | The interface with menu appears | Build the interface (Step 6) |
| Look at the sidebar, top left | Under “BMS – Job Application Management System” is your name, not “Benno Bewerbaer” or “Applicant” | Sample data removed (section “Setup: BMS gets to know you”)? Name entered and saved in the card “Identity and search strategy” (section “Your profile: identity and search strategy”)? If you edited `config/profil.md` by hand, check the spelling `**Name:**` |
| Look at the “Dashboard” | No notice about sample data any more, no jobs and emails from Benno Bewerbaer | “Remove sample data” in the “Settings” (section “First: remove the sample data”) |
| Open “Settings” | All areas appear without an error message | Check the BMS Terminal window for error messages, restart BMS |
| Under “Jobs”, record a job with “+ Add job” | It appears in the list | Restart BMS |
| In this job, start “Check company fit” | The run appears in the “Task Centre” and ends with a result | With Claude check the access key, with ChatGPT `codex login status` (Step 7) |
| Then start “CV match” and afterwards “Create CV” | A Word file and a PDF file are created | Check the base CV (section “Your CV”) and LibreOffice |
| Look at “Settings” → “Program version” and the foot of the sidebar | Both show your installed version | Restart BMS, then reload the page |

An AI run such as the company check takes about ten minutes. While it runs, you can carry on
working as normal.

## Installing updates

Messages in the Terminal window follow the language of your system: German on a German system, English on any other.

New versions appear on GitHub (https://github.com/holgerdaube/BewerbungsMgmtSystem/releases).
A dedicated tool downloads them, checks them, backs up your current state and installs them. Your data,
settings and customisations are kept. BMS itself also shows you whether there is a new version: Under
“Settings”, card “Program version”, the button “Check for updates” asks
GitHub for the latest version. It only displays the result and installs nothing. The tool
does the installing, with BMS closed:

1. Quit BMS: double-click `stop.command`. A running BMS cannot replace itself
   reliably; otherwise the update tool aborts with the message “BMS is still running”.
2. In the program folder, double-click `update.command`. A Terminal window opens.
3. The tool looks online for a new version. It writes: “Searching GitHub for a new version. GitHub will see this computer’s IP address.” Only this request is sent,
   nothing from your database. If the tool finds a newer version, it downloads it, compares
   the checksum with the details from GitHub and checks the package.
4. The tool shows a plan: which files change and whether Python or
   interface components have to be reinstalled. Confirm the question “Install the update from … to … now?” with `y` if the plan is fine. If there is nothing new, the tool reports
   “Your BMS is up to date”, and you are done.
5. When it finishes, it says “Update to version … complete. Start BMS as usual.” Start BMS as usual: double-click on `start.command` in your
   BMS folder.

**The second way: a ZIP file.** If the online search does not work, or you do not want to use it,
download the new file `BMS_<Version>.zip` in the browser from the release page
(https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/latest, under “Assets”) and save
it in your “Downloads” folder. Then start the tool as above. It finds the ZIP file by
itself, checks it and shows the plan. If there is a ZIP file in “Downloads” and the tool
also finds a version online, it takes the highest version, wherever it comes from. If you have installed a version up to 1.7.0,
use this way for the first update to a version from 1.9.0.

If the tool reports “Online search not possible: …”, it does not abort. It gives the reason, such as
“There is no connection to GitHub.” or “GitHub is currently limiting requests. Please try again in an hour.”, and carries on with the ZIP file in “Downloads” if there is one
there.

Your data (the database and everything under `outputs`), your settings, your profile
(`config/profil.md`) and your search profile (`config/suchprofile.yaml`) are never part of a
program package and therefore stay unchanged. Your access key and other secrets are
outside the program folder and are likewise left untouched. If you have replaced an
Advisory Board persona through the interface or adjusted `config/profil_struktur.md` or `config/scoring_rubrik.md`,
that is kept as well. The update puts the new version of these files alongside for
comparison, without overwriting your own.

Before any change, the tool makes a backup, in a folder of its own under
`data/updates/…` (such as `data/updates/2026-10-15_091200_1.0.0_zu_1.1.0`): a copy of your
database and every file it replaces or removes. If an update fails along the way, the
tool undoes all changes automatically and names the backup folder in the message.

If the update also changes the interface, the tool rebuilds it and needs Node.js
from the installation for that (Step 3). If it is missing, the tool aborts during the check, without changing
anything. For new Python and interface components, the tool needs an
internet connection, as it did for the installation.

In the Terminal you can also call the tool with options. The examples use the suggested
folder; if you chose a different one, put in your BMS folder. `--pruefen` only shows the
plan, without installing anything. A package downloaded for this stays in the folder `data/updates/pakete`:

```sh
~/BMS/update.command --pruefen
```

`--offline` prevents any contact with GitHub. The tool then does not look online for a
new version and only takes a ZIP file from “Downloads”:

```sh
~/BMS/update.command --offline
```

`--zurueck` rolls back the last update and reinstalls the previous version:

```sh
~/BMS/update.command --zurueck
```

The tool then asks separately whether the database should also be reset to the state before the update:
“Reset the database to its state before the update? All changes made since the update will be lost.” If you answer `N` or press Return, your current
database stays unchanged and only the program files go back to the previous state. Only the
additional switch `--mit-datenbank` resets the database without this question.

You can see your installed version at any time under Settings → “Program version” or in the foot
of the sidebar. What changed in a version, you can read under “Documentation”, tab
“Version”.

## If something goes wrong

| What you see | What helps |
|---|---|
| The browser shows an empty page | The interface was not built: Step 6 |
| “command not found” for `brew`, `claude` or `codex` | The two “Next steps” commands from Homebrew are missing (Step 3), then reopen the Terminal |
| “start.command cannot be opened” | Run the `xattr` command from Step 4. Alternatively choose System Settings, Privacy & Security, “Open Anyway” |
| The start aborts with a message about `cryptography` or “symbol not found” | The Python environment was created with a different Python. Enter `rm -rf ~/.bewerbung_mgmt_venv` in the Terminal and repeat Step 5 |
| “address already in use” or port 8000 taken | BMS is already running. Point the browser to `http://localhost:8000` or quit it first with `stop.command` |
| AI runs end with a sign-in error | With Claude, check the access key (Step 7): one line, no `#` in front, copied in full. Then restart BMS. With ChatGPT, `codex login status` in the Terminal should show `Logged in using ChatGPT`; otherwise repeat `codex login` and restart the run |
| The “Task Centre” says the usage limit of your ChatGPT subscription has been reached | The limits of your subscription apply; BMS sets no limit of its own per run. Start the run again later. A daily run can quickly push a Plus account to its limit |
| You want to switch the AI, Claude or ChatGPT | “Settings”, card “AI”: choose the other AI. Its program must be installed and signed in beforehand (Steps 3 and 7 for that AI) |
| No PDF file is created | LibreOffice is missing or is not in the suggested place |
| CVs are called `CV_Applicant_…` | There is no name in the profile yet. Enter it in the card “Identity and search strategy” and save (section “Your profile: identity and search strategy”). If you edit `config/profil.md` by hand, check that the line `**Name:**` is spelled exactly like that |
| BMS shows jobs, emails or a profile of “Benno Bewerbaer” that you did not create | That is the sample data. Remove it in the “Settings” with “Remove sample data” (section “First: remove the sample data”) |
| “Remove sample data” reports that a backup or a task is running | Wait a moment, for a task until it has finished in the “Task Centre”, and click again. Nothing was changed |
| `Response: 404` when downloading the program package, or the information says `Not Found` | There is no program package on GitHub for this version, or no version has been published yet. Check the version number from the information. If that does not help, take the fallback with a ZIP file from the release page |
| The information says `API rate limit exceeded`, or the update tool reports “GitHub is currently limiting requests.” | Without signing in, GitHub allows only 60 requests per hour and IP address. In a company network, many computers often share one address. Try again in an hour, or take the fallback with a ZIP file |
| `Response: 000` or a message from curl such as “Could not resolve host” | There is no connection to GitHub. Check your internet connection. In a company network, access may be blocked. If it does not work, download the ZIP file in the browser from the release page and take the fallback |
| The checksum from Step 4 differs from the information | The package is incomplete or damaged, for example because the connection was interrupted. Delete the file and download it once more. If the checksum differs again, download the ZIP file in the browser from the release page (fallback) |
| The update tool reports “Online search not possible: …” | That is not an abort. The message gives the reason, for example “There is no connection to GitHub.” The tool carries on with a ZIP file in “Downloads” if there is one there. Otherwise download the new `BMS_<Version>.zip` from the release page on GitHub and put it there |
| Update aborts with “BMS is still running” | Run `stop.command` first, then start the update again |
| Update aborts with a note about `npm`/Node.js | Install Node.js (Step 3), then start the update again. Nothing was changed |
| Update reports “failed, all changes have been rolled back” | The message names the backup folder under `data/updates/…`. Your previous version carries on running unchanged; try the update again or report the problem on the Issues page (section “Help”) |
| “No update package found” | Neither online nor in “Downloads” was a package available. The reason for the online search is in the message before. Put the file `BMS_<Version>.zip` in the “Downloads” folder and try again |

After every change to files in the program folder, restart BMS so that it reads them.

## Your data

BMS runs entirely on your computer. Your applications, your profile and your emails are
in the database `data/bewerbung.sqlite` in the program folder, your generated documents in the folder
`outputs`. The publisher of BMS runs no server for the program and receives nothing from it.
There is contact with GitHub only when the program package is downloaded during the installation and when you yourself
look for a new version (button “Check for updates” in the Settings or the
update tool). GitHub receives the IP address of your computer and the request itself, nothing
else. With `--offline` or with a ZIP file there is no contact. More details are under
“Legal”, tab “Privacy”. The AI functions transmit content to the provider of the
chosen AI, as far as it is needed for the run in question, and through your own account: with
Claude to Anthropic, with ChatGPT to OpenAI.

BMS backs up your database automatically while it is running: once a day as a ZIP file in the
folder `data/backups/auto`. It keeps the newest backup, all from the last 24 hours,
and one each from the last 7 days and the last 4 weeks. BMS removes older automatic backups
itself. Under “Settings”, card “Backup”, you see the last
backup, change the retention and back up at the press of a button.

These backups are in your BMS folder on the same disk as your working copy and
do not replace an external backup. Include your BMS folder in your regular
backup as well, on the Mac for example through Time Machine.

This is how you restore a backup:

1. Quit BMS: double-click `stop.command`.
2. In your BMS folder, double-click `wiederherstellen.command`. The tool shows you
   the available backups, the newest first, with date, time, type and size.
3. Type the number of the backup you want and confirm the question with “j”.
   Pressing Enter with no input cancels. The tool checks the backup before it changes anything,
   and first makes a backup of your current state.
4. Start BMS as usual.

Good to know:

- **Only the database data comes back.** Everything you recorded or changed since the time of the backup
  is no longer in the database afterwards. Your documents in
  `outputs` and `data` stay unchanged. Files that were created after the backup
  no longer belong to any job afterwards.
- **Undoing it:** Your state before the restore is in `data/backups` as a backup “vor Wiederherstellung” (before restore).
  Start the tool again and choose that entry, and
  everything is as before.
- **Which backups appear:** the automatic ones from `data/backups/auto`, the ones created
  by hand in `data/backups` and the entries “vor Wiederherstellung” (before restore). The backups that an
  update creates are not included. You undo an update with `--zurueck` (section
  “Installing updates”).
- **If BMS is still running,** the tool aborts and tells you. Quit BMS and
  start the tool again.

If the tool does not start, it also works by hand: Quit BMS, unpack the desired ZIP file in the
folder `data/backups/auto` (double-click), rename the existing file `data/bewerbung.sqlite`
instead of deleting it, for example to
`bewerbung_alt.sqlite`, put the unpacked file `bewerbung.sqlite` in the folder `data` and
start BMS.

## Help

For questions about the installation and for errors, open a new issue on the page
https://github.com/holgerdaube/BewerbungsMgmtSystem/issues. For this you need
a free GitHub account. Give your operating system, the step where it gets stuck,
and the exact wording of the error message. A screenshot helps. The page is public:
Do not write any passwords, access keys or personal data in it.

For day-to-day work with BMS, you will find detailed operating instructions in the program folder under `docs/en/ANLEITUNG.md`. You can also read all the guides in BMS itself: In the sidebar,
“Documentation” opens them in tabs, including this installation guide (“Installation & updates”), the
user guide and an overview of the features.
