# Security

**English** · [Deutsch](SECURITY.de.md)

BMS – Job Application Management System runs locally on the user's computer and processes personal data (CV,
application history, emails). We therefore take security vulnerabilities seriously. Thank you for reporting one.

## Reporting a vulnerability

Please do **not** report vulnerabilities in a public issue, a pull request or a discussion. Use GitHub's private
vulnerability reporting instead:

1. Open https://github.com/holgerdaube/BewerbungsMgmtSystem/security.
2. Choose **Report a vulnerability**.
3. Describe the problem. Only you and the people responsible for the project can see the report.

We confirm receipt, get back to you with a first assessment and agree with you when a bug will be described
publicly. We cannot promise a fixed response time.

## What belongs in the report

- Which version is affected (bottom of the sidebar or the `VERSION` file) and on which system (macOS or Windows)
  you use it.
- What happens and what you expected, if possible with the steps to reproduce it.
- What consequences you see, such as which data an attacker could read or change.
- If you have a suggested fix, that too.

**Do not send any credentials or real personal data:** no passwords, tokens, API keys, CVs, emails or database
files. Black out such parts in excerpts and screenshots, or invent sample values that still show the problem.

## Supported versions

Security fixes are released only for the **latest version**. Before reporting, check whether the problem still
occurs there. How to update is in the [README](README.md), section “Updates”.

## What does not belong here

Please report bugs without a security aspect as a normal issue:
https://github.com/holgerdaube/BewerbungsMgmtSystem/issues. Please report problems in services that BMS only
connects to (Claude, ChatGPT, Gmail, Apify, GitHub) to the provider concerned.
