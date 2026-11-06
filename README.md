# BMS – Job Application Management System

**English** · [Deutsch](README.de.md)

BMS – Job Application Management System (repository name BewerbungsMgmtSystem) is a local web app for
your own job search. It finds and scores jobs, checks companies, prepares your CV and cover letter and
tracks the replies in your mailbox. BMS runs on your computer and is free and open source
(Apache License 2.0).

## Who is BMS for?

For applicants who run their job search themselves and want help from AI. The AI work (research, scoring,
draft texts) is done by either Claude from Anthropic or ChatGPT from OpenAI, each through your own account.
You do not need your own API keys, and capturing, managing and evaluating jobs still work without AI.

BMS supports only the side that applies. Features that let employers score, sort or select applicants do
not exist and are not planned. The decision stays with you: BMS never applies on its own and sends no
email. It only creates drafts that you check and send yourself.

## What BMS can do

- **Find and score jobs:** Search runs across job portals, career pages and job alerts, with a target-role
  fit from 1 to 5 and evidence from the posting.
- **Check companies:** Business model, market, competitors and the role's influence on the company.
- **Prepare documents:** A CV tailored to the job (Word and PDF, with an ATS scan) and a cover letter,
  without invented details.
- **Evaluate your mailbox:** Recognise replies to applications, measure response times, create reply
  drafts.
- **Support interviews:** A briefing before the interview, an evaluation afterwards, follow-ups and your
  network.
- **Keep the overview:** Dashboard, pipeline, Excel export, cost and budget display for the AI runs.

[`docs/en/FUNKTIONEN.md`](docs/en/FUNKTIONEN.md) gives an overview by work step, and
[`docs/en/ANLEITUNG.md`](docs/en/ANLEITUNG.md) describes how to use BMS.

## Languages

The interface, documentation and AI reports are available in German and English. You can switch in the
sidebar or in the settings.

Your CV and cover letter follow the language of the job posting: German, English, French, Italian, Spanish
or Portuguese. For this you upload a base CV in that language. If it is missing, BMS takes the English,
otherwise the German version, translates nothing and says so in the run's report.

The job search has limits outside Germany. The preset portals are aimed at Germany. In the check, the search
found hardly any jobs in France, Italy and Spain, and none was run for Portugal and Brazil. Use the two free
portal rows in the settings, LinkedIn alerts and your target companies there. CVs and cover letters in French,
Italian, Spanish and Portuguese have been tried on one real posting each, with Claude. The mailbox search
for words in these languages has run on a real mailbox without false matches. Whether it finds a real reply
in these languages and classifies it correctly has not yet been tried, because that mailbox held no such
reply.

## Requirements

- A Mac (macOS) or a Windows PC with about 2 GB of free storage and an internet connection.
- For the AI features, a subscription to Claude (Pro or Max, Anthropic) or ChatGPT (Plus or Pro, OpenAI).
  You pay the provider directly. BMS itself costs nothing.
- Optionally, an email account with IMAP access (Gmail works too), so that BMS can recognise replies in
  your mailbox.
- Optionally, a LinkedIn data export, to import your career history and skills.

You do not have to install Python, Node.js or the other programs beforehand: the installation guide sets up
whatever is missing. You do not need any programming skills.

## Which AI?

BMS can run its AI features with **Claude** or with **ChatGPT**. The installation asks right at the start
which one you use and sets up exactly that one. You can switch later in the settings, on the “AI” card.

- **Claude** is the default and the best-tested route. The content of the AI runs goes to Anthropic.
- **ChatGPT** is a preview in BMS. The runs use your ChatGPT sign-in (Plus or Pro) through the Codex CLI
  program, and you do not need an API key. The content of the AI runs then goes to OpenAI instead of
  Anthropic. The runs without mail have been tested, the mail runs and the daily run have not. There is no
  budget limit per run, your subscription's limits apply, and many runs in a row can take a Plus account to
  its limit.
- **Gemini** is not available: Google's rules do not allow the Gemini subscription in apps like BMS.

## Installation

An AI takes you through the installation step by step in a chat, using a guide file:

1. Download the guide for your system from https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/latest:
   `BMS_Install_MAC.en.md` for macOS or `BMS_Install_Windows.en.md` for Windows. Both are also in the main
   folder of this repository.
2. Open Claude Desktop or ChatGPT, start a new chat and attach the file.
3. Add this message: “Guide me through installing BMS with this file.”

The assistant in the chat gives you each command to copy and checks the result with you. The guide first
asks which AI BMS should use (Claude or ChatGPT). It downloads the program package from the GitHub release
itself and verifies its checksum. It then sets up your profile, CV, target roles and search region with you.
Allow about 45 minutes for the technical part and one to two hours for the setup.

## Updates

In the settings, the “Program version” card shows with the **Check for updates** button whether there is a
newer version and says what changes. The button only asks when you click it and installs nothing. You
install an update while BMS is closed, with `update.command` (macOS) or `update_windows.bat` (Windows): the
tool downloads the new version from GitHub, checks it, backs up your data first and undoes everything if
an error occurs. What changes with each version is in [`CHANGELOG.en.md`](CHANGELOG.en.md).

## Privacy

BMS runs entirely on your computer: your application, profile and email data stay in local files and a local
database, and the publisher runs no server and receives no data. BMS contacts GitHub only when you check for
updates or download one, and GitHub then receives your computer's IP address. Services you connect yourself
(Claude or ChatGPT, your mailbox, optionally Apify) process data under their own privacy policies. The details
are in the “Privacy” tab under “Legal” in the app.

## A note on AI

BMS creates texts, ratings and drafts with AI (Claude or ChatGPT, depending on your choice). They are
suggestions and must be checked before you send them.

## Licence and liability

BMS – Job Application Management System (repository name BewerbungsMgmtSystem) is open source under the
**Apache License 2.0** (file `LICENSE`, origin notices in `NOTICE`). You may use, change and pass it on,
also under a different name and commercially. Anyone who passes it on includes `LICENSE`, keeps the notices
from `NOTICE` and marks changed files. The licence grants no rights to names and trademarks, in particular
to “Daube.Tech” (section 6).

**Liability under German law:** The program is provided free of charge. The following applies to a gift: the
author is liable only for intent and gross negligence (section 521 of the German Civil Code, BGB), and for
defects only if they were fraudulently concealed (sections 523 and 524 BGB). Liability under the German
Product Liability Act remains unaffected. This notice does not change the licence. This translation is for
convenience, the German version is authoritative.

## Author

Developed by Holger Daube. Legal notice (Impressum): https://daube.tech/impressum.html

## Contributing

- **Bugs and requests:** Please report them as an issue: https://github.com/holgerdaube/BewerbungsMgmtSystem/issues
- **Security vulnerabilities:** Please do not open a public issue, follow [`SECURITY.md`](SECURITY.md)
  instead.
- **Contributions:** Pull requests are welcome. The rules (licence, language, tests) are in
  [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Support

BMS is free and will stay free. If you would like to support the work on it, you can give something
voluntarily, with the “Sponsor” button at the top of this page or directly:

- **Buy Me a Coffee:** https://buymeacoffee.com/holgerdaube
- **PayPal:** https://paypal.me/holgerdaube

A contribution is a voluntary thank-you and not payment for the program. It unlocks nothing and gives no
claim to support, features or updates, and the program remains free of charge (see “Licence and liability”).
It is not tax-deductible.

## For developers

BMS consists of a FastAPI backend with SQLite, a React frontend and a collection of Claude skills.
[`docs/en/INSTALLATION.md`](docs/en/INSTALLATION.md) explains how to set up, start and test the source code
(developer installation on macOS and Windows). [`docs/en/DOKUMENTATION.md`](docs/en/DOKUMENTATION.md) describes
the architecture, data model, skills, operation and security, and [`docs/en/RELEASE.md`](docs/en/RELEASE.md) the
release process. Code comments, skills, tests and commit messages are in German.
