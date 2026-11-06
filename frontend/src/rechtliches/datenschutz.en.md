## Privacy

This translation is for convenience. The German version is authoritative.

### Key points

This software runs **locally on the user's computer**. The publisher operates no server for the
program and receives **no data** from its use: there is simply no code path through which application,
profile or email data would be sent to the publisher. If the user asks for new program versions, the
request goes to GitHub (see “Check for updates”), not to the publisher.

All application, profile and email data is stored only in local files and a local SQLite database on
the user's device.

### Controller

The **user themselves** is responsible for processing the data created in the software, because they run
the software locally and the processing is not carried out on the publisher's behalf. For purely
personal purposes of one's own job search, the household exemption regularly applies (Art. 2(2)(c) GDPR).

### Third-party services connected by the user

The software can include optional third-party services. The **user connects them with their own
accounts**, the publisher does not provide them:

- **Anthropic (Claude / Claude Code)**: for the AI-based functions (research, text drafts, matching)
  if Claude is selected as the AI (default).
- **OpenAI (ChatGPT / Codex CLI)**: for the same functions if the user selects ChatGPT as the AI. Sign-in
  uses the user's ChatGPT account, no API key is needed.
- **Google Gmail**: for reading relevant application emails and creating email drafts. Scopes used:
  **readonly** and **compose**. There is **no code path for sending**: the software cannot send
  emails, it only creates drafts that the user checks and sends themselves.
- **Apify** (optional): for automated job searches.
- **Job search of the German Federal Employment Agency** (no account): for job searches. The software
  fetches the public search page arbeitsagentur.de/jobsuche. It transmits the search term, location,
  radius, time period and the home-office filter. For technical reasons, the computer's IP address is
  also processed.
- **OpenAI** (optional): for the Advisory Board feature, if configured.

The **privacy terms of the respective provider** apply to each of these services. The user is
**responsible** for using these third-party services in line with data protection law, because they
create and connect the accounts and give the relevant consents to these providers themselves.

### AI runs: Claude or ChatGPT

The AI-based functions are carried out either by Claude Code or by the OpenAI Codex CLI. The user makes
this choice during installation or later in the settings (“AI” card); the default is Claude. Both
programs run on the user's computer and sign in with the user's own account.

- **Recipient:** the provider of the selected AI, Anthropic for Claude and OpenAI for ChatGPT. The
  publisher operates no server for this and receives neither the requests nor the responses. The
  provider processes them under its own responsibility; its privacy policy applies.
  Anthropic: https://www.anthropic.com/legal/privacy
  OpenAI: https://openai.com/policies/privacy-policy/
- **Data:** the content a run needs, as far as necessary for that run, such as parts of the profile, CV,
  job postings and emails read, plus the instructions for the run. With ChatGPT it goes to OpenAI
  instead of Anthropic.
- **Purpose:** research, rating and text drafts that the user initiates in the app.
- **Trigger:** runs that the user starts in the app and steps that follow one of the user's actions.
- **Retention and training:** The software makes no statement on this. The terms of the respective
  provider and the plan of the user's account apply, as set out in its privacy policy and terms of use.

### Check for updates

Three actions ask GitHub for the latest program version or download the program package, and the user
triggers all of them: the “Check for updates” button in the settings, the update tool (update.command
or update_windows.bat) and the download command in the installation guide. The software running in the
background, the daily run and the skills never do this. The button only shows whether a new version
exists; it is never installed without the user.

- **Recipient:** GitHub, via api.github.com (query for the latest version) and github.com (download of
  the program package). The publisher operates no server for this and receives neither the request
  nor its result. GitHub processes the request under its own responsibility; its privacy statement
  applies:
  https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement
- **Data:** the IP address of the requesting computer and the request itself, that is the address queried
  and the identifier “BMS-Update” as the program name. There is no sign-in and no token. The installed
  program version, operating system, a computer identifier and application, profile and email data
  are not transmitted.
- **Purpose:** to ask for the latest published version and to download the program package.
- **Trigger:** only the user. Next to the button is the notice that GitHub receives the computer's IP
  address, and the update tool prints it before each check. With the “--offline” option the update tool
  does not query online, and installing a program package as a ZIP file causes no contact with GitHub.

### Which data the software processes locally

For your overview: all of the following data remains in the user's local SQLite database or local file
system:

- The user's master data and career history (profile area).
- Application data (jobs, companies, contacts, status, communication history).
- Locally cached email content, as far as it was read through the Gmail import.
- Documents created by the software (CV versions, cover letters, exports).

### Data security

Credentials for third-party services (such as OAuth tokens) are stored locally on the user's device and
are not sent to the publisher. The user is responsible for securing their own device (disk encryption,
user account protection, backups).
