# Setting up the coach site — step by step

This guide is for anyone who has never created a subdomain or uploaded files via
SFTP (more on that shortly). You need no programming knowledge. Almost everything
happens in the app, in **Settings**; only at the very end is there a single
terminal command for emergencies.

All on-screen texts in this guide are the real labels from the app. Addresses,
usernames and passwords are **placeholders** throughout (e.g. `access-xyz.webspace-host.com`)
— enter your own values there.

---

## What is the coach site?

The coach site is a separate, password-protected web page on which your coach can see
your application status — without getting access to the app itself. The page is generated
automatically from your data and is purely a snapshot: your coach cannot change anything,
only read.

**What your coach sees:**
- An overview with key figures (how many jobs, how many ongoing applications, etc.)
- The daily digest: new results, rejections and applications of the last four days and what changed
  on the day of the run. It is regenerated with every daily run. Unlike your own
  digest in the app, it contains neither the emails awaiting a reply nor your open
  actions; for changes it names only status changes, never the text of your notes.
- The list of your jobs and applications — active applications (Applied/Interview/Offer)
  and the jobs you are still reviewing — for each job with company fit analysis, CV match and
  the job posting itself
- Your rejections with the recorded rejection reasons and the latest pattern report of the
  rejection analysis with its date (it is renewed once a week in the daily run)

**What your coach NEVER sees, guaranteed:** your emails, your private notes and the
application history, Advisory Board assessments, salary details, internal review notes, interview
transcripts/debriefs/briefings, your CVs and cover letters as files, ATS scans, your network
and your contacts. This block list is anchored in the code and automatically tested —
it cannot be loosened by accident.

## Security at a glance

- Your credentials (SFTP password, coach login) end up **only locally** on your
  computer under `~/.bewerbung_mgmt_secrets/` — never in the project folder, never in a Git repository.
- The coach password is stored **only as a hash** (a kind of digital fingerprint from
  which the password cannot be calculated back). Even you cannot have it shown to you
  afterwards — if you have forgotten it, simply assign a new one (see below
  “Changing the password”).
- The page is blocked for search engines (no Google hit). But that does not protect against
  passing it on: **Anyone who knows the address and password sees the content.** Give both only directly and
  confidentially to your coach — not in a public message, a forum or a
  social media post.

## Prerequisites

Before you start, you need:

1. **Your own web hosting package with your own domain**, where you can create subdomains
   yourself (more on that shortly). Almost any hosting package (IONOS, Strato, All-Inkl, …) can do this.
2. **SFTP access** to this hosting. SFTP is a secure, encrypted channel through which
   files are uploaded to your web space — comparable to an encrypted
   copy connection. Every hosting package includes it.
3. **The program `lftp` installed locally** — it does the actual upload in the background. Without `lftp`, neither “Test connection” nor the later upload works. On
   the Mac you install it in the terminal with:
   ```
   brew install lftp
   ```
   (If the `brew` command itself is missing, Homebrew is needed first — installation guide at
   https://brew.sh. On a computer where the BMS is already set up, Homebrew is usually
   already present.)
4. A browser with a private window/incognito window (for the acceptance step at the
   end).

---

## Step 1 — Create a subdomain and enable SSL

A **subdomain** is an additional part of the address in front of your domain, e.g. `coach.` in front of
`meine-domain.de` — a separate, self-contained area within your website, with its own
directory on the server.

The following example shows IONOS; with other hosts the menu items are named slightly differently,
but the procedure is practically the same everywhere: create subdomain → set target directory →
enable SSL.

**What you do (IONOS example):**
1. Log in to the IONOS customer centre → menu “Domains & SSL” → select your domain.
2. Choose “Create subdomain”, enter e.g. `coach` → gives `coach.meine-domain.de`.
3. Choose “Web space” as use/target and enter a target directory, e.g. `/coach`.
   **Remember this folder name** — it comes up again in step 3 as “Target directory”.
4. In the row of the new subdomain, enable SSL (button/toggle “Enable SSL”, usually
   included free in the package). SSL ensures the page can be reached encrypted via `https://` — mandatory, because otherwise your coach's password would be
   transmitted unencrypted at login.
5. Wait a little (usually a few minutes, rarely up to an hour) until the certificate and
   address resolution (DNS) take effect.

Result: You now have an address like `https://coach.meine-domain.de` and an empty
target directory for it on your web space.

## Step 2 — Find the SFTP credentials with your host

**What you do (IONOS example):**
1. In the customer centre → menu “Hosting” → “SFTP & SSH” (or “FTP accesses”).
2. There you find the **host** (e.g. `access-xyz.webspace-host.com`) and your
   **username** (often `uNNNNNNN` or your main user).
3. If your package offers it, you can optionally create a separate user just for the
   coach directory (slightly more security, but not a must).
4. You either already know the matching **password**, or you assign/reset it there.

Briefly note down host, username and password — you will enter them into the app in the next step
(afterwards you can delete this note, the app stores them securely locally for you).

## Step 3 — Enter the address and credentials in the app

**What you see:** In the app under **Settings**, right at the bottom, the **“Coach site”** card
with an explanatory text and the note “Step by step: docs/ANLEITUNG_COACH_SITE.md”
— that is, exactly this guide.

**What you do:**
1. Do **not** tick “Coach site active” yet — that comes only at the very end
   (step 7), when everything is filled in.
2. “Site address” field: enter the subdomain address from step 1, e.g.
   `https://coach.meine-domain.de`. Important: it **must start with `https://`** — with `http://`
   the app rejects the entry (reason: otherwise your coach's password would be transmitted
   unencrypted).
3. In the **“Upload target (SFTP)”** area, fill in four fields:
   - **Host** — from step 2, e.g. `access-xyz.webspace-host.com`
   - **Username** — from step 2
   - **Password** — from step 2 (the input field shows only dots, like any password field)
   - **Target directory** — the folder from step 1, e.g. `/coach` (must start with `/`)

Do not click “Save” yet — test first (next step).

## Step 4 — Test the connection

**What you see:** The **“Test connection”** button below the form fields.

**What you do:** Click it. The button briefly shows “Testing…”, then a result line:
- Success (green): e.g. “✓ Connected. Target directory /coach is reachable (empty).”
- Error (red): a plain-text error message, e.g. if host/username/password do not
  match. Passwords **never** appear in it — that is intentional.

The test checks the fields currently in the form directly — you do not have to save first.
If the test does not work, compare host/username/password/target directory once more with
step 2.

## Step 5 — Find the server path to the access file

For the password prompt to work on the server, Apache (the server software)
needs the **absolute path** to the access file on the server — a technical detail that you
normally do not have to remember yourself: the app can find it out automatically.

**What you see:** The “Server path to the access file” field with placeholder
`/server/path/to/directory/.htpasswd` and next to it the **“detect automatically”** button.

**What you do:** Click “detect automatically”. The button briefly shows “Detecting…”, then:
- **Success:** the field fills itself with the matching path.
- **Error “The target directory already contains files…” (409):** The automatic detection only works
  in an **empty** target directory (for security reasons, see below). If something is already there —
  e.g. because you filled it once before — enter the path **manually** (below
  is how).
- **Error “The file could not be reached or PHP is not active…” (400):** Likewise enter it
  by hand.

**Finding the path manually**, if the automatic detection does not work:
- **Option A — your host's file manager:** In the customer centre there is usually a
  browser-based file manager for the web space. Navigate there to your target directory
  (e.g. `/coach`) — the full path is often shown in the address bar/breadcrumb navigation or
  in the file properties.
- **Option B — graphical SFTP program** (e.g. FileZilla or Cyberduck, free): connect with
  the same credentials as in step 2, change to the target folder — the
  path shown in the address bar is the absolute path you are looking for.
- With IONOS this path often looks like this (only as an example of the form, your ID
  is of course different): `/homepages/12/dNNNNNNNNN/htdocs/coach`.
- In the field you enter the path **plus** `/.htpasswd`, e.g.
  `/homepages/12/dNNNNNNNNN/htdocs/coach/.htpasswd`.

## Step 6 — Assign the coach login

**What you see:** The **“Coach login”** area with the note “Your coach uses this to sign in to
the site.” and two fields.

**What you do:**
1. **Username** — a login name for your coach, freely selectable, e.g. `coach`.
2. **Password** — a password for your coach. Tip: assign a separate, not reused
   password that you pass on to your coach separately (e.g. verbally or by messenger). As soon as you save, only the
   hash is stored (see “Security at a glance”) — nobody sees the password itself afterwards, not even you.

## Step 7 — Activate and update the coach site

**What you do:**
1. Now tick **“Coach site active”**.
2. Click **“Save”**.
   - If something is still missing, the app says so in plain text, e.g. “Still missing before you can activate:
     site_url, Coach password” — no cause for concern, just add the named fields
     and save again.
   - Success: “✓ Saved” appears next to the buttons.
3. **Only after a successful save** a new button appears below:
   **“Update coach site now”**. (Before that, only the grey note “Activate and save first, then the site can be uploaded.” is there.)
4. Click this button. It builds the page from your current data and uploads it via SFTP. While the run is working, the button shows “⏳ Running…” and next to it a
   “Cancel” button; a small status chip shows “running…”. At the end it says “✓ done”
   (or “✗ failed” with an error message below — then the section “If something
   does not work” helps).

## Step 8 — Acceptance in a private browser window

Now you check whether everything really works as intended — best in a private
window (Safari: “New Private Window”, Chrome: “New Incognito Window”) so that no
saved credentials distort the test.

**What you do:**
1. Open the configured address, e.g. `https://coach.meine-domain.de`.
2. **A login prompt from the browser must appear immediately** (a native popup asking for
   username/password — not a pretty sign-in page, but the browser itself asking). If
   this prompt does not come, something is not set up correctly (see below).
3. Log in with the coach login from step 6. Afterwards you should see the overview, the
   daily digest, your jobs and your rejections.
4. In the browser tab, check whether the small **favicon** (icon next to the page title in the tab)
   appears — it is the same symbol as in the app.
5. Search engines are blocked automatically, you need to do nothing for that. If you want to check it
   technically: `curl -sI https://coach.meine-domain.de` shows the header
   `x-robots-tag: noindex` and, without login details, the status `401` — this is optional and only
   for the technically interested.

---

## Daily operation

Once set up, you do not have to take care of anything any more: the coach site updates
**automatically at the end of every daily run** with your current status. If you want to update it immediately
(e.g. after an important change), click “Update coach site now” in Settings again at any time.

## Changing the password

You can change the coach password at any time without touching anything else:
1. Settings → “Coach site” card → “Coach login” area.
2. Enter the new password in the “Password” field (the username can stay unchanged).
3. Click “Save” — the new password applies immediately, the old one no longer works.
4. Optionally click “Update coach site now” afterwards so that the new access file
   is on the server immediately (otherwise this happens at the latest at the next daily run).

## Switching off temporarily

Untick **“Coach site active”** and click “Save”. This skips **future**
updates (button and daily run alike) — the app reports this honestly each time with
“Coach site is switched off in Settings — skipped.” Important to know: the
most recently uploaded state **stays on the server** and can still be reached (password-
protected) until you either activate again or use the emergency stop below.

## Emergency stop: remove the site from the server completely

In case you want to remove the coach site from the server immediately and completely (not
just pause it), there is a single terminal command. It is the only step in this whole
guide that needs a terminal:

1. Open the Terminal app.
2. Change to the project folder (path as set up on your computer), e.g.:
   ```
   cd Pfad/zu/deinem/Bewerbung_Mgmt_System
   ```
3. Run:
   ```
   scripts/coach_deploy.sh --wipe
   ```
4. This empties the target directory on the server completely (contents **and** the
   access-protection files) — the page can no longer be opened afterwards. This also works
   if “Coach site active” is already switched off. Only if SFTP credentials have **never** been
   entered can the command naturally delete nothing, and it says so.

---

## If something does not work

**“Internal Server Error” right after entering the password**
- *Cause:* The server cannot read the access file — usually because the server path entered
  does not point exactly to the actual file, or because its file permissions on the
  server do not fit (the app automatically sets the right permissions when uploading, but some
  hosts overwrite this in exceptional cases).
- *What to do:* In the “Coach site” card, check the server path or detect it again (step
  5), then click “Update coach site now” again. If the error persists, ask the
  host whether the file permissions of the `.htpasswd` in the target directory can be changed.

**Login popup already appears at `http://` (without the “s”)**
- *Cause:* The redirect from unencrypted `http://` to the secure `https://`
  should take effect **before** any password prompt appears. If it appears anyway
  at `http://`, either an older protection file was not overwritten, or your
  host does not support the server function needed for it.
- *What to do:* Click “Update coach site now” once so that the current
  protection configuration is definitely uploaded. If the problem still occurs afterwards, ask the host
  whether “force SSL” or a comparable setting can be enabled across the board for the subdomain.

**“Upload was skipped”**
- *Cause:* Either “Coach site active” is switched off, or at least one
  required field is still missing (address, SFTP access, server path or coach login).
- *What to do:* The exact message shows what is missing. In Settings, add the tick or
  the named field and save again.

**“lftp is missing”**
- *Cause:* The program that does the file upload is not installed on this computer. This message can already
  appear at “Test connection” or “detect automatically”,
  not only when uploading.
- *What to do:* Open the terminal, run `brew install lftp` (see “Prerequisites”),
  then simply click the step again.

**The page shows a wrong/empty page or 404 although everything is saved**
- *Cause:* The subdomain from step 1 points to a **different** directory on the server
  than the one you entered as “Target directory” in the coach card — the two
  must match exactly.
- *What to do:* Check with your host which directory is assigned to the subdomain
  (with IONOS: “Domains & SSL” → subdomain → settings shows the directory), and in the
  coach card under “Target directory” enter exactly the same path.
