# Gmail/Email Strategy (Phase 72A, as of 31 July 2026)

Decision document on the question: **How do users (local installation) get access to
their mailbox** without the publisher having to go through Google's verification and audit machinery?

## Facts (researched 31 July 2026, sources below)

1. **Gmail via IMAP with an app password still works** (as of 2026, no deprecation announced):
   You need two-factor authentication on the Google account; IMAP has been enabled by default on
   all accounts since January 2025. No Google Cloud project and no OAuth verification are needed.
   (Not available for "Advanced Protection" accounts; Workspace admins can disable it.)
2. **Google's Security Assessment (CASA) applies only to apps that process restricted-scope data "from or
   through a third-party server".** Purely local processing is exempt.
   BUT: The BMS sends email content to the Claude API (the user's account) for classification. With a
   SHARED OAuth client run by the publisher, exactly this would have to be declared in the
   verification process; the assessment risk would be real, not theoretical.
3. **Costs if an assessment does fall due:** CASA Tier 2 approx. **$540–1,800/year**, Tier 3 approx.
   $4,500, plus annual revalidation, plus the brand verification process (privacy policy,
   domain proof, demo video, review loops lasting several weeks).
4. **Verification exemptions** exist for: Personal Use (the route for own use),
   Internal Use (app only within your own Workspace organisation), Dev/Testing.
5. **An unverified SHARED client** is not an option for users:
   warning screen, user cap, shortened token lifetime.
6. **A separate Google Cloud project per user** (Personal Use exemption) works permanently and
   free of charge; the author's own setup is the proof. The price: about 15–20 steps in the
   Google Cloud console; the consent screen must be set to "In production" (otherwise refresh
   tokens die after 7 days and the sign-in then expires).

## Decision: tiered model, IMAP first

**Tier 1 — standard for all users: IMAP (for Gmail too).**
The Phase 71F provider covers Gmail, GMX, Web.de, mailbox.org, Posteo and iCloud Mail. Setup for
users: enable 2FA, create an app password, fill in three fields. Minutes instead of a
console odyssey, zero Google bureaucracy for the publisher. Known, documented drawbacks
compared with the Gmail API: search as a Python post-filter (recall is equivalent for the narrow
date windows of the skills), INBOX only (archived emails are invisible), no snippet in
search results, and the Gmail drafts folder has a localised name ("[Gmail]/Entwürfe" in German).

**Tier 2 — power-user option: Gmail API with your own Google Cloud project.**
For users who want the full Gmail query syntax and search across labels. It is supported by a
step-by-step guide (docs/SETUP-EMAIL.md, route B), including the
explanation that the "unverified app" warning is normal and correct for your OWN project. No
effort for the publisher beyond maintaining the documentation.

**Tier 3 — organisations with Google Workspace (e.g. coaching, outplacement):**
The organisation marks the OAuth client of its domain as "internal" → Internal Use exemption,
no verification, no warning screen; alternatively the admin allows app passwords for
Tier 1. This will only be worked out once such a deployment becomes concrete.

**Deliberately NOT now: a shared, verified OAuth client run by the publisher.**
Reasons: ongoing costs (assessment risk because of the transfer to the Claude API, see facts 2 and 3),
annual revalidation, brand verification upkeep, and it contradicts the central
principle ("the publisher does NOT sit between you and your mailbox").

**Reassess if** (a) many users actively demand the Gmail API instead of IMAP,
(b) Google deprecates app passwords, or (c) a large organisation demands a verified
client. In that case, first check whether the architecture can be changed so that
full email texts no longer leave the local machine (local pre-filtering and anonymising
before the Claude call). That would ease the CASA question.

## Sources

- Google: Restricted scope verification (developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification) — assessment criterion "from or through a third-party server", exemptions, consequences for unverified apps.
- DeepStrike: Google CASA Security Assessment (deepstrike.io/blog/google-casa-security-assessment-2025) — Tier 2 prices $540–1,800, Tier 3 $4,500, annual revalidation.
- Mailjerry "Create Gmail App Password 2026" (mailjerry.com/create-gmail-app-password), SMTPedia "Gmail Settings 2026" (smtpedia.com/gmail-email-settings-pop3-imap-smtp) — app passwords active, 2FA required, IMAP on by default since 01/2025.
