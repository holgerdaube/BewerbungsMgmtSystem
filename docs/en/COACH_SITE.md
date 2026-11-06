# Coach Site (Phase 81, configurable since Phase 82) — Read-only Mirror for the Coach

A password-protected, static snapshot of your application status for an external coach.
The source of truth remains the Mac; the export is deterministic code (NO LLM, zero cost).
Since Phase 82, the target address, SFTP access and coach login are **configurable per installation
under Settings → Coach site**. Before that, the feature was
fixed to a single installation (terminal scripts, one fixed address in the template). Addresses appear in this document only
as an example (`coach.example.org`).
The specs with all decisions (Phase 81: export/visibility, Phase 82: configuration/API) belong
to the author's project history and are not in the public repository. A step-by-step guide
for the initial setup (also for non-developers): `docs/ANLEITUNG_COACH_SITE.md` (same
content as a printable manual: `docs/ANLEITUNG_COACH_SITE.html`). This document
remains the compact operations and architecture page for developers.

## What the coach sees / never sees

**Visible:** Overview (KPIs + status distribution) · **Daily digest** (P2-79, tab directly after
the overview; `digest.digest_inhalt(fuer_coach=True)`, so without "To answer" (sender and
subject), without "Open actions" (free text `next_step`), and in "Changed today" only status changes from
the JobLog (`art='auto'`), never a history note; can be switched off with `tages_digest: false`) ·
Jobs & applications in two sections —
"Active applications" (Offer/Interview/Applied) and "Screening & review" (To review/New,
extension of 10 Aug 2026) — for each job with company fit, match and **posting snapshot** (always without
the internal capture context; legacy formats that cannot be cleaned safely are skipped
and reported) · Rejections with reasons for rejection + lost-order analysis (latest report by the date in the
file name, linked with its date; `pipeline/absagen_bericht.py`). Confidential assignments
appear exactly as in the app (decision of 10 Aug 2026).
**Never exported (covered by tests, `tests/test_coach_export_sperrliste.py`):** emails, notes &
history, board checks, salaries, verify_note/capture internals, transcripts/debriefs/
briefings, CVs/cover letters, ATS scans, network/contacts, budget. Whitelist:
`config/coach_export.yaml`.

## Components

| What | Where |
|---|---|
| Configuration (address, SFTP target, coach login hash) | `backend/pipeline/coach_settings.py` → `~/.bewerbung_mgmt_secrets/coach_settings.json` (600/700); automatically migrates an old `coach_sftp.env` (Phase 81) without modifying it |
| API for the Settings card | `backend/app/routes_coach_settings.py` → `/api/settings/coach` (`GET`/`PUT`/`POST .../test`/`POST .../serverpfad`) |
| Exporter (DB → static site) | `backend/pipeline/coach_export.py` → `data/exports/coach_site/` |
| Upload (SFTP mirror, lftp) | `scripts/coach_deploy.sh` (`--dry-run` / `--wipe` = emergency stop) |
| Both in one (task/button) | `scripts/coach_site.sh` = AgentTask kind `coach-site` |
| Create/change coach login | Normal route: **Settings → Coach site** (user + password, app UI) → bcrypt hash in `~/.bewerbung_mgmt_secrets/coach_htpasswd`. Terminal fallback without a running app: `scripts/coach_passwort.sh <benutzer>` |
| SFTP access | Normal route: **Settings → Coach site** (app UI) → `coach_settings.json`. The old terminal path `~/.bewerbung_mgmt_secrets/coach_sftp.env` has only been read as a fallback since Phase 82 and is never written any more |
| Protection template | `assets/coach_htaccess.template` (Basic Auth, HTTPS redirect, noindex; `{{SITE_URL}}`/`{{AUTH_USER_FILE}}` are filled from the configuration on deploy) |

Triggers: the "Update coach site now" button (Settings) AND automatically as the last
link in the daily run chain. **Without a complete configuration, or with the switch turned off,
the step ends green** (local export only, clear message, exit 0 — I4). The daily run never
turns red as long as the coach site has not been set up; a real SFTP error AFTER setup
marks only the coach-site task as failed (last link).

## On/Off Switch

Checkbox "Coach site active" in Settings → Coach site (field `aktiv` in `coach_settings.json`).

- **Off:** `coach_site.sh`/`coach_deploy.sh` report "Coach site is switched off in Settings
  — skipped." and finish with exit 0 (I4 — the daily run never turns red because of it).
  Content that has already been uploaded **stays unchanged** on the
  server (still password-protected). Switching off pauses future uploads; it does not delete anything.
- **On, but incompletely configured:** `PUT /api/settings/coach` rejects with `422 "Zum
  Aktivieren fehlen noch: …"` (field list from `fehlende_felder()`); the update button
  "Update coach site now" does not even appear in the card until `aktiv=true`
  AND all required fields are saved.
- **Removing everything from the server (emergency stop, not a pause):** `scripts/coach_deploy.sh
  --wipe` — runs unconditionally, even with `aktiv=false` (I5); fails only if SFTP credentials
  have never been stored.

## Setup

Since Phase 82 **via the UI**: Settings → Coach site → fill in the address, SFTP access, server path
to the `.htpasswd` (button "detect automatically" or manually) and coach login,
activate, save, click "Update coach site now". The complete
step-by-step guide for first installations (hoster-neutral, IONOS as a
worked example, written for IT beginners) is in **`docs/ANLEITUNG_COACH_SITE.md`**
(equivalent printable version: `docs/ANLEITUNG_COACH_SITE.html`), which also covers all
error cases from the live setup with cause and solution.

Short version for developer diagnosis (terminal, from `backend/`):
- View the configuration (without passwords): `~/.bewerbung_mgmt_venv/bin/python -m
  pipeline.coach_settings zeigen`
- Shell contract as `coach_deploy.sh`/`coach_site.sh` use it themselves:
  `~/.bewerbung_mgmt_venv/bin/python -m pipeline.coach_settings shell`
- First deploy: `scripts/coach_deploy.sh --dry-run` (shows the file list) →
  `scripts/coach_site.sh` (export + real upload).
- Acceptance: open the configured address in a private window → the login prompt must appear (without
  login: 401) · after login, check overview/daily digest/jobs/rejections ·
  `curl -sI -u <user>:<pass> <adresse> | grep -i x-robots` → `noindex`.

Example: An installation can run at `https://coach.example.org` (at a hoster such as IONOS
or Strato). This is only an example value; since Phase 82 the address can be chosen freely per installation
(field "Address of the site" in the coach card).

## Operation & Rollback

Update: button or daily run (automatic). Change password: Settings →
Coach site → "Coach login" section (or the terminal fallback `scripts/coach_passwort.sh
<benutzer>`) + optionally a manual update; otherwise the change takes effect at the latest on the
next daily run.

**Rollback/switching off** (in stages):
1. **Pause future uploads only** (content stays live, see "On/Off Switch" above): untick
   "Coach site active" and save.
2. **Remove the site completely from the server (emergency stop):** `scripts/coach_deploy.sh --wipe` +
   optionally deactivate the subdomain at the hoster.
3. **Reset the configuration itself:** delete `~/.bewerbung_mgmt_secrets/coach_settings.json`;
   `load_settings()` then automatically falls back to an old `coach_sftp.env`, if one still exists, otherwise to
   empty defaults; no code change needed.
4. **Code rollback:** `git revert` of the Phase 82 commit (configurability/API/UI) or of the
   Phase 81 commit (the whole feature).
