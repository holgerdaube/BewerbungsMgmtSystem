# Setting up the email account (customer guide)

The system **reads** application emails and saves reply **drafts** in your mailbox.
It never sends anything itself — there is no sending code path anywhere in the program (secured
by a test). Two routes are open to you; **Route A is the recommended default.**

| | Route A: IMAP (recommended) | Route B: Gmail API (power users) |
|---|---|---|
| Suitable for | Gmail, GMX, Web.de, mailbox.org, Posteo, iCloud Mail | Gmail only |
| Setup | ~5 minutes, app password only | ~30–45 min, Google Cloud console |
| Search | Date window + post-filtering, inbox only | full Gmail search syntax, all labels |
| Google formalities | none | your own Google Cloud project |
| Not possible | Outlook.com/Microsoft (no IMAP basic auth) | — |

---

## Route A — IMAP with an app password (recommended)

1. **Create an app password with your provider** (your normal account password does NOT work
   and does not belong in third-party software either):
   - **Gmail:** turn on two-factor authentication in your Google account → myaccount.google.com
     → “Security” → “App passwords” → create a new password (16 characters).
     Note: with the “Advanced Protection Program” switched on, Google offers no app passwords
     — use Route B then.
   - **GMX / Web.de:** Settings → Security → “Application-specific passwords”
     (also switch on “Allow IMAP/POP3 access” there).
   - **mailbox.org / Posteo:** Settings → Security → app password.
   - **iCloud Mail:** appleid.apple.com → Sign-In & Security → “App-specific passwords”.
2. **Enter it in the app:** Settings → “Email account” card → choose “IMAP”:

   | Provider | Host | Port | Security | Drafts folder |
   |---|---|---|---|---|
   | Gmail | imap.gmail.com | 993 | SSL | `[Gmail]/Entwürfe` (for an English-language account: `[Gmail]/Drafts`) |
   | GMX | imap.gmx.net | 993 | SSL | `Entwürfe` |
   | Web.de | imap.web.de | 993 | SSL | `Entwürfe` |
   | mailbox.org | imap.mailbox.org | 993 | SSL | `Drafts` |
   | Posteo | posteo.de | 993 | SSL | `Drafts` |
   | iCloud | imap.mail.me.com | 993 | SSL | `Drafts` |

   Username = full email address, password = the app password from step 1.
3. Click **“Test connection”** — the login and the drafts folder are checked. If you get
   “folder not found”, use the exact folder name from your mail program
   (with some providers it depends on the language). Then **Save**.

Your credentials are then stored only locally in
`~/.bewerbung_mgmt_secrets/mail_settings.json` (file permissions 600) — never in the database,
never in the provider's cloud.

**Known limits of Route A:** Only the inbox is searched (the system does not see archived/moved
emails — leave application emails in the inbox until they have been processed);
the results list shows no preview snippets.

---

## Route B — Gmail API with your own Google Cloud project

For Gmail users who want the full search syntax and a search across labels. You create
your OWN, private Google project — the software provider is not in the middle and
sees nothing. The later warning “Google hasn't verified this app” is normal and correct for a
private project you created yourself (you are the “developer”).

1. **Create a project:** console.cloud.google.com → new project (any name, e.g. “My-BMS”).
2. **Enable the Gmail API:** “APIs & Services” → “Library” → “Gmail API” → Enable.
3. **OAuth consent screen:** type “External”, enter an app name + your own email.
   Add scopes: `gmail.readonly` and `gmail.compose` (the software needs and wants no more —
   by design it cannot send).
   **Important: set the publishing status to “In production”** — in “Testing” status
   the access tokens expire every 7 days and the mail functions die weekly.
4. **Create a client ID:** “Credentials” → “OAuth client ID” → type **“Desktop app”** →
   download the JSON.
5. **Save the file** as `~/.bewerbung_mgmt_secrets/gmail_credentials.json`
   (directory with `chmod 700`, file with `chmod 600`).
6. **Sign in once:**
   ```sh
   ~/.bewerbung_mgmt_venv/bin/python -m pipeline.gmail_client auth
   ```
   (from the `backend/` folder; opens the browser). At the warning “App not
   verified”: “Advanced” → “Continue” — see above, for your own project this is the
   intended way. Then in the app: Settings → “Email account” → “Gmail (API)”.

**Google Workspace accounts** (company mailboxes): The Workspace admin can mark the client of the
organisation as “internal” (no warning, no verification) or allow app passwords for
Route A. The admin clarifies the details.
