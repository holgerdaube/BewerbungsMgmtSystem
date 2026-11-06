# Release — Versions and Sign-off (internal, P2-51, P2-82, P2-84)

How you sign off a new BMS version and publish it as a package in a GitHub release. The
BMS is open source (Apache-2.0): since P2-82 there is no licence file and no package service any more.
Users find new versions in the GitHub release of the public repo
`holgerdaube/BewerbungsMgmtSystem`. This documentation is for the project lead, not for users, and it is
not shipped (`docs/RELEASE.md` is dropped from every package by the documentation allow list in
`pipeline/kundenpaket.py::DOKU_ERLAUBT`).

**Two repositories.** Development happens in a non-public development repository; the public
repo is created from an export of the checked state (section "Publishing" below). A sign-off
(`freigeben`) creates the version, CHANGELOG, commit and tag in the development repo; no release is created
there: `release.yml` runs on a tag push only in the public repo (both jobs check the repo name).
The trial build via `workflow_dispatch` runs in every repo. The update button and update tool always ask the
public repo; if there is no release there yet, they find nothing ("No version has been
published yet." or a connection error).

Short version, details below:

```sh
scripts/release.sh freigeben patch --probe        # nur pruefen
scripts/release.sh freigeben patch                # Entwicklungs-Repo: Version, CHANGELOG, Commit, Tag, Push
scripts/veroeffentlichen.sh --ziel <Arbeitskopie> --ref v1.1.0   # geprueften Stand in die Arbeitskopie des oeffentlichen Repos
# … committen, pushen, CI abwarten, taggen, Tag pushen (Abschnitt „Veröffentlichen“): das Tag startet das Release …
scripts/release.sh abholen 1.1.0                  # downloads ZIP + .sha256 (also BMS_latest.zip) from the release (check only)
# … Das GitHub-Release im öffentlichen Repo ist die Veroeffentlichung, danach folgt kein weiterer Schritt (Schritt 5 unten) …
```

`scripts/release.sh` and `scripts/veroeffentlichen.sh` pass all arguments 1:1 on to `python -m pipeline.release`
and `python -m pipeline.veroeffentlichung` respectively (from `backend/`). The examples below use the scripts.

## Version scheme

SemVer; the source is the file `VERSION` in the project root (one line `MAJOR.MINOR.PATCH`). `0.0.0`
means "no sign-off yet". Only `pipeline/release.py::freigeben()` writes this file; never
touch it by hand. Every sign-off additionally creates an annotated Git tag `vX.Y.Z`; the tag and
`VERSION` must always match (`release.yml` checks this once more on
every tag push).

Rule of thumb for the level:
- **patch** — bug fix, no visible new function.
- **minor** — new function, nothing existing breaks.
- **major** — something that a user could experience as a break (2.0.0: the licence requirement was dropped and
  a new update route via GitHub, see P2-82).

`scripts/release.sh freigeben <X.Y.Z|patch|minor|major>` accepts both: a fixed version or
a level that is counted up from the current `VERSION`.

## CHANGELOG rules

`CHANGELOG.md` is user text (formal "Sie" form) and ships with every package. Structure:

```
# Änderungen

<Einleitung>

## Unveröffentlicht

- Punkt, der mit der nächsten Freigabe ausgeliefert wird

## 1.2.0 (28.09.2026)

- Punkt
```

**Every phase with a customer-visible change adds to the section "## Unveröffentlicht"** one
to two sentences from the user's point of view, right at the change itself (not collected
retrospectively at sign-off). Rules for the entries:

- Formal "Sie" form, no filler phrases, the most important thing first. The same customer-text rules as the rest of the
  customer documentation.
- **No phase numbers** (P2-51, Phase 90 … are internal references, not customer information) and
  **no company names** from your application history.
- One place, no changelog for internal rebuilds (refactorings, test coverage, comments);
  only what a customer actually notices.

`pipeline/changelog.py` is the only place that knows the format: `version_tupel(s)`,
`abschnitte(text)`, `abschnitt(text, version | None)`, `pruefen(text)` (format errors as a list,
empty = fine), `freigeben(text, version, datum)` (turns "Unveröffentlicht" into the
version section and creates a new empty "Unveröffentlicht" section). The same API is also read
by `app/version.py` for the Program version card in Settings. A wrongly formatted
section is not noticed there, but only at the next sign-off (`freigeben` then refuses
with an exact message about which heading line does not fit).

## Release procedure

**1. Trial run.** Shows the planned version, the resulting CHANGELOG section and the tag,
changes nothing:

```sh
scripts/release.sh freigeben patch --probe
```

A whole series of checks runs BEFORE any change, each with its own message on rejection:
branch `main`; no changed, versioned working tree (unversioned files are only a
hint, not an abort); `git fetch origin` and HEAD == `origin/main`; a completed,
successful CI run (`ci.yml`) for exactly this commit (`gh run list --commit <full SHA>`);
the new version greater than `VERSION`; the tag `vX.Y.Z` exists neither locally nor on `origin`;
`CHANGELOG.md` correctly formatted and "Unveröffentlicht" not empty; the customer package check for HEAD
without findings (on your machine it automatically runs WITH the company-name rule, see below; in CI the
local database is missing, so the check runs there without that one rule).

**2. Real sign-off.** The same checks, after which the tool writes `VERSION` and
`CHANGELOG.md`, commits "Release X.Y.Z", creates the annotated tag `vX.Y.Z` (message =
version text + the CHANGELOG section) and pushes first `main`, then the tag:

```sh
scripts/release.sh freigeben patch
```

The push goes to the development repo (`origin`). The final message names the next step:
`scripts/veroeffentlichen.sh --ziel <Arbeitskopie> --ref vX.Y.Z`. No release is created there (see "Two
repositories").

If a step fails AFTER the commit (network, the tag already exists after all, push rejected),
the tool **reverts nothing automatically**, as that could delete objects that have already been
fetched elsewhere. Instead it prints the exact `git` commands with which you
continue by hand.

**3. CI builds the customer package (in the public repo).** The tag push in the public repo
(section "Publishing") triggers `.github/workflows/release.yml`; in the development repo both
jobs stay skipped. The job `tests` calls `ci.yml` as a complete test run against exactly this state (`secret-scan` deliberately does not run
again there: the commit was already scanned on the push to `main`, and a
tag push gives the gitleaks action no commit list anyway). The job `paket` then builds the ZIP with
`python -m pipeline.kundenpaket --ref HEAD --ziel-ordner …`, puts a byte-identical copy `BMS_latest.zip`
next to it, creates a `.sha256` file for both (`sha256sum` format), fetches the release notes via `pipeline.release notizen` and
publishes a GitHub release `vX.Y.Z` with both ZIPs, their checksums and the installation guides
(`BMS_Install_MAC.en.md`, `BMS_Install_Windows.en.md` from the checkout; if one is missing, the step fails) as
attachments. You can see progress on the Actions page of the public repo. **With this release the
version is published.**

**4. Fetch the package (optional).** The release is already the publication; you only need to fetch it
to check the package yourself (for example for the update trial below) or to pass it on as a ZIP. As soon as the
release is green:

```sh
scripts/release.sh abholen 1.1.0
```

Downloads the attachments of release `v1.1.0` from the public repo (`gh release download --repo …`, not
from the development repo) to `outputs/kundenpaket/` (override with `--ziel DIR`), checks `BMS_1.1.0.zip`
against `BMS_1.1.0.zip.sha256` and prints the path. If the release carries `BMS_latest.zip` (from the first release
after 2.2.0), it checks that file too: checksum, file name in the `.sha256` line and byte-identical with `BMS_1.1.0.zip`.

**5. Nothing more to do.** There is no server on which a package is placed. The update button and
update tool find the version via `releases/latest` of the repo `holgerdaube/BewerbungsMgmtSystem`
(GitHub returns only published releases there, no drafts and no pre-releases):

- **The "Check for updates" button** (Settings, "Program version" card): `GET /api/version/neueste`
  in `app/update_pruefen.py`, shows the version, date and the release notes (text from `CHANGELOG.md`, only
  "- " lines are kept). It installs nothing.
- **Update tool** (`update.command`, `update_windows.bat`): downloads `BMS_<Version>.zip` from the
  release and compares it with the `digest` of the asset (fallback: the asset `BMS_<Version>.zip.sha256`;
  if both are missing, nothing is installed).
- **Installation guides** (`BMS_Install_MAC.en.md`, `BMS_Install_Windows.en.md`): first ask
  `releases/latest` (step 4a) and then download `releases/download/vVERSION/BMS_VERSION.zip`; `VERSION`
  is read by Claude from `tag_name` in the response. Checksum: the `digest` of the asset (step 4c). The user
  downloads the guides themselves as an attachment of the release (README, step 1); that is why
  `release.yml` attaches them.

`release.yml` must produce the names `BMS_<Version>.zip` and `BMS_<Version>.zip.sha256` exactly like this,
otherwise the button and the tool will not find the package. Do not change anything about file names in the workflow without
also updating `scripts/bms_update.py` and the guides.

**`BMS_latest.zip` for the product page.** The release also carries `BMS_latest.zip` (a byte-identical copy of
`BMS_<Version>.zip`) and `BMS_latest.zip.sha256` (with `BMS_latest.zip` in the line, so `shasum -a 256 -c` works
directly). Reason: bms.daube.tech links permanently to `releases/latest/download/BMS_latest.zip` and
`…/BMS_latest.zip.sha256` in its "Installation" section, without updating the link after every release. The copy is
only made on a tag push (step "Fester Name fuer die Produktseite"); the trial build does not have it. The update tool,
the button and the guides do not use it; they stay with `BMS_<Version>.zip`. If a user puts `BMS_latest.zip` in the
downloads folder, the update tool still finds it: it looks for `BMS_*.zip` there and reads the version from the
manifest, not from the file name. Never rename it to `BMS.zip`, the tool would not find that. The link works from the
first release after 2.2.0.

**The trust anchor is your GitHub account.** Whoever takes it over could publish a release with foreign code;
`digest` and manifest would then come from the same place. Protection: two-factor sign-in and
releases only via `release.yml`, never packages uploaded by hand.

**Old installations up to 1.7.0** keep asking the former package service and never learn about 2.0.0 there.
There is no bridge package: they get 2.0.0 once as a ZIP file in the download folder (from the
release page) and update themselves from then on.

## Short language check

Before every release, in addition to the dry run: `scripts/test.sh` and CI green, `scripts/uebersetzung.sh --pruefen --alle`
without findings, `backend/tests/abnahme/design_vergleich.py` for German against the last release, plus in a test copy the
first start in English, the tour of all pages and one chain from `firma-pruefen` to `anschreiben-erstellen`.
`veroeffentlichen.sh --pruefen` only runs on `main`. The description and topics of the public repo are in English.

## Trial build

To check the release workflow itself without creating a real release (for example after a
change to `kundenpaket.py`, `release.py` or `release.yml`, or once before the very first
real sign-off): `workflow_dispatch` on `release.yml`, with an optional `ref` (empty = the
current state of `main`). It runs the same two jobs (`tests` + `paket`), also in the development repo,
but without a tag and without a GitHub release. The finished ZIP including checksum ends up as a
workflow artefact instead:

```sh
gh workflow run release.yml
gh workflow run release.yml -f ref=<commit-oder-branch>
```

## Testing the update before distribution

Before a user actually receives an update, a dry run with the real
update tool is worthwhile, not just the test suite: install an older version in a throwaway folder
(own port, so that it does not disturb an existing installation), create a little test data,
change an Advisory Board persona via the interface, then install the new `BMS_<Version>.zip` using
`update.command` and check: the data and the changed persona are still there, the
Program version card shows the new version, and `--zurueck` cleanly undoes the update. You
pass the ZIP as a path: then there is no contact with GitHub; without a path and without
`--offline` the tool queries online. Exactly
this scenario was an acceptance step in the build spec of P2-51 (section "Abnahme", point 6)
and is the yardstick for every future sign-off that touches the update mechanism itself. For
a pure feature sign-off without changes to `bms_update.py`/`kundenpaket.py`, the
test suite is enough.

## Withdrawal

A pushed tag should **never** be deleted retroactively once someone could already have downloaded
the ZIP: the update tool expects ascending versions, and a release changed after the fact would
have no effect anyway for a user who already has it and would only cause confusion. If, however, an error is found AFTER the tag push but BEFORE anyone can have downloaded the ZIP
(the release is offered immediately via `releases/latest`, so only a short window remains), then:

```sh
gh release delete v1.1.0 --repo holgerdaube/BewerbungsMgmtSystem --cleanup-tag --yes
```

deletes the GitHub release including the tag in the public repo (the tag in the development repo stays, as does the
commit "BMS 1.1.0" in the public repo). Fix the error in the development repo, then sign off
and publish with a new version number (section "Publishing"): the public repo gets one more
commit.

If the ZIP has already been downloaded or installed, the rule is different: do not delete a tag, but sign off a new
patch with the fix. The update tool on the user's machine installs the fix like any
other update.

**Stop offering a version.** If a faulty version should no longer be offered, you set
the release on GitHub to "Draft" (edit the release, or
`gh release edit v1.1.0 --repo holgerdaube/BewerbungsMgmtSystem --draft`).
`releases/latest` returns only published releases, so the button and tool then offer the
previous version again. This has not been tested; try it out on a test release in a
separate trial repo before it is needed in earnest. Anyone who has already downloaded or installed the faulty version keeps it. For
them, the new patch from above applies.

## Building the customer package

A customer package is a ZIP with the delivery state of a revision, without development files and without
personal data, with a few neutralised files (`README.md`, `config/profil_struktur.md`,
`automation/agent_settings.json`) plus a manifest `bms_manifest.json` (path → SHA-256 of every
delivered file, version, whether it is a sign-off):

```sh
scripts/kundenpaket.sh
```

The script builds from the last commit (`HEAD`), applies the exclusion and replacement rules, then checks the
result for personal data. If the check finds even a single hit, **no** ZIP is created
(fail-closed). It places the finished package under `outputs/kundenpaket/` (gitignored, like the rest of
`outputs/`). The file name carries the version (`BMS_1.1.0.zip` for a sign-off, otherwise additionally the date and
short SHA).

- `--pruefen` — only check and print the findings, without writing a ZIP.
- `--arbeitsbaum` — the source is the current working tree instead of `HEAD` (preview before the next commit,
  including new files that have not yet been added; the test suite also checks this way). Produces
  `BMS_VORSCHAU_<Datum>.zip`.
- `--ziel-ordner DIR` / `--ref REF` — a different target folder or a different revision.

If `data/bewerbung.sqlite` exists locally, the company-name rule runs as well. In CI without
a data set it is missing accordingly, and the output says so.

**Customer packages are created exclusively through this script.** Never copy the project folder and never
issue a GitHub invitation to the development repository: both would hand over personal data and the
development history.

## Customer package check rules

`pipeline/kundenpaket.py` builds every package fail-closed: a finding means **no** ZIP, however
small. The rules themselves are in `pipeline/personendaten.py`; the same module checks the export for the
public repo (section "Publishing"). All delivered text files are checked for:

- **Anschrift**, **Private Kontaktdaten**, **Dritte Personen** and **Name des Nutzers**. Their patterns are
  not in the code, but come from local sources (section "Check patterns" below).
- **E-Mail-Adressen** (except the domains in `ERLAUBTE_DOMAINS`, the endings reserved for examples
  `.example`/`.invalid`/`.test`/`.localhost` and the individual addresses in `ERLAUBTE_ADRESSEN`),
  **Telefonnummern** (except the one example number in `BMS_Install_MAC.en.md` and
  `BMS_Install_Windows.en.md`).
- In the scope "paket" (customer package), the user's name applies in only three places, each with its own
  rule name: **"Name des Nutzers in Kundentexten"** (documentation/interface/skills, see `NAME_KUNDENTEXT_PFADE`),
  **"Name des Nutzers im Python-Programmtext"** (string literals, docstrings excluded) and
  **"Name des Nutzers im TS/TSX-Programmtext"** (code without comments). In the scope "oeffentlich" (export),
  the single rule **"Name des Nutzers"** applies instead: everywhere, including in comments and docstrings.
- **Bestands-IDs** (inventory IDs) — in EVERY delivered text file: every pattern
  "Job/Jobs/Task/Tasks/Mail/Mails/Lauf/Bewerbung/Firma + at least two digits".
- **Firmennamen from the installation's application history** (ONLY locally against the real
  `data/bewerbung.sqlite`, read-only): company names from `company`/`job`/`targetcompany`/
  `headhunter` are reduced to their core form (legal form removed) and
  searched for as a whole word, case-sensitively. `ERLAUBTE_FIRMENNAMEN` excludes functional
  mentions (portals, ATS, infrastructure such as LinkedIn, Workday, Google …), each entry with a
  justification in the code. In CI (no data set in the checkout) this one rule does not run;
  the output says so explicitly.
- **Zeilenenden** (line endings): `.bat` files need CRLF, `.command`/`.sh`/`.py` must not contain CR.

In addition there are two package-wide rules: **Pflichtdateien fehlen** (mandatory files missing) and **Import eines ausgeschlossenen
Moduls** (a delivered `.py` imports something that was dropped during exclusion), and
since P2-51 **Startdatei nicht ausführbar** (start file not executable; `update.command` counts here).

**One exception per path** (`_FREMDER_WORTLAUT`, P2-77): In `frontend/src/rechtliches/drittlizenzen_texte.txt`
exactly the rules "E-Mail-Adressen", "Firmennamen" and (on export) the user's name are dropped, because the
wording of third-party licences with author addresses and copyright lines must not be altered; all other
rules continue to apply there.

### Check patterns: from local sources only

The code contains neither an address nor an email address nor names. `personendaten.muster_laden` builds the patterns
at runtime from:

1. `config/profil.md` (not in Git), read with the app's parser (`pipeline/profil_datei.py`): name,
   location as address (from it street and postcode as separate patterns), contact (email, phone)
   and LinkedIn profile.
2. the local database `data/bewerbung.sqlite`, read-only: the company names (rule "Firmennamen") and
   the names of the contacts (rule "Dritte Personen").
3. optionally `pruefmuster.txt` in the secrets folder (`~/.bewerbung_mgmt_secrets/`, override
   `BMS_SECRETS_DIR`): one term per line, `#` at the start of a line = comment. For former addresses and
   names that appear nowhere else. A term is assigned to a rule according to its form: with `@`,
   `linkedin.` or `://` = Private Kontaktdaten, with a digit or street ending = Anschrift, everything
   else = Dritte Personen.

If the profile or database is missing (for example in CI), the personal rules are silently dropped; the general ones
(email with exceptions, phone format, inventory IDs, absolute user paths) continue to run, and the output
says what was missing. In this case the export tool aborts. No finding and no test output shows a
pattern; findings name the file, line and rule with a shortened excerpt of the file.

**The author's name** counts as a finding as a whole word everywhere, except in the attribution list (`NOTICE`,
`LICENSE`, `frontend/src/rechtliches/ueber.md`, `ueber.en.md` and the author and licence sections of `README.md` and `README.de.md`).
"Daube.Tech" does not count as a surname, and `holgerdaube/BewerbungsMgmtSystem` is the only permitted form
of the account name.

**On a finding:** never post-process the ZIP by hand. Fix the cause in the real source
(neutralise the comment/example or, if it is a legitimate functional mention,
add the entry with a justification to the appropriate exception list:
`ERLAUBTE_DOMAINS`/`ERLAUBTE_ADRESSEN`/`ERLAUBTE_FIRMENNAMEN`/`_PERSONA_PFADE` in
`pipeline/personendaten.py`, depending on which rule triggered), then check again locally before you
even think of `freigeben`. Tests should contain invented values (`beispiel.de`, `example.org`,
`*.example`); if a real provider domain carries the test logic (detecting freemail, portal or
ATS senders), only the single test address goes into `ERLAUBTE_ADRESSEN`, never a whole freemail domain:

```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.kundenpaket --arbeitsbaum --pruefen
```

`--arbeitsbaum` checks the current state (including unversioned, new files) before you
commit; the company-name rule runs automatically as soon as `data/bewerbung.sqlite`
exists locally.


## Publishing

The public repo `holgerdaube/BewerbungsMgmtSystem` never gets the history of the development repository,
but one checked state per version as **one** commit "BMS X.Y.Z" with the tag `vX.Y.Z`. Development
continues in the development repo; in the public repo something changes only at a sign-off.
`scripts/veroeffentlichen.sh` (calls `python -m pipeline.veroeffentlichung`) creates the state in a
local working copy of the public repo:

```sh
scripts/veroeffentlichen.sh --ziel <Arbeitskopie des öffentlichen Repos> [--ref <Commit>] [--pruefen]
```

How the tool proceeds:

1. `--ref` (default `HEAD`) must be contained in `main`. If `HEAD` has unsaved changes, the
   tool warns: the commit is exported, not the working tree.
2. The entries come from the commit via `git archive` (as in the package build), minus the short
   exclusion list `NICHT_OEFFENTLICH` (`tasks/`, `.claude/launch.json`). There is no second,
   separately maintained tree and no replacement files on export: what must not be public is cleaned up in the
   development repo.
3. The check uses the rules of `pipeline/personendaten.py` in the scope "oeffentlich" (all files, no
   path exceptions apart from the third-party wording and the attribution list) with the local check patterns from above,
   plus a quick search for secrets (API keys, GitHub tokens, OAuth client secrets,
   private keys). If the profile or database is missing, the tool aborts: "Without a profile and database
   it is not possible to check whether personal data is in the export." Every finding is output as in the
   package check (file, line, rule, shortened excerpt), the result is exit code 1, and
   nothing is written.
4. `--pruefen` ends here.
5. The target must be a folder with `.git` whose `origin` points to `github.com/holgerdaube/BewerbungsMgmtSystem`
   (https or ssh), without unsaved changes and with a GitHub noreply address as the
   commit identity (section "Once only" below). Otherwise the tool aborts without writing anything.
6. Mirroring: all files in the target except `.git/` are deleted, and the entries are written with their permissions
   (executable yes/no). Files deleted in the development repo thus also disappear in the target.
7. Output: the number of files, the target's `git status --short` (shortened) and the next steps with
   the real target and real version: review, commit, push `main`, wait for CI, tag, push the tag,
   check the release (the commands from "Per version" below).

**The tool never commits or pushes.** Commit, tag and push are done by hand following "Per version".

### Once only: account, working copy and commit identity

Without this setup, your private email address would appear in every public commit and tag. That is why
`veroeffentlichen.sh` checks it before mirroring and otherwise aborts.

**Account** (GitHub → Settings → Emails): switch on "Keep my email addresses private" and show no
public email address in the profile. Do not switch on "Block command line pushes that expose my email": GitHub
would otherwise also reject pushes to the development repo, whose commits carry the private address.

**Clone the working copy**, outside an iCloud folder (it can be cloned again at any time):

```sh
git clone https://github.com/holgerdaube/BewerbungsMgmtSystem <Arbeitskopie>
```

**Set the identity**, in the working copy only (in the development repo it stays with your usual address),
and verify:

```sh
git -C <Arbeitskopie> config user.name "<Anzeigename>"
git -C <Arbeitskopie> config user.email <ID>+<Konto>@users.noreply.github.com
git -C <Arbeitskopie> config user.email
```

`<ID>` is the account number (`gh api user --jq .id`), `<Konto>` the account name. The last command shows the
address that has been set.

What is checked is the **effective** identity, as `git commit` and `git tag` use it
(`git var GIT_AUTHOR_IDENT` and `GIT_COMMITTER_IDENT`): local and global configuration and the
environment variables `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_EMAIL` and `EMAIL`, which take precedence over the setting.
Both addresses must match `<ID>+<Konto>@users.noreply.github.com` or `<Konto>@users.noreply.github.com`.
In addition, all existing commits (author and committer, all branches) and annotated tags
(tagger) must carry a noreply address or one of GitHub's own addresses (the general
sender address for commits from the web interface, the bot form of Dependabot and co.). An empty repo
passes this check.

- "The working copy's commit address is not a GitHub noreply address": set the address as above. If an
  environment variable is behind it, the message names it; remove it.
- "A commit or tag in the target carries an address other than the GitHub noreply address": the history of the
  working copy is tainted. Clone the working copy again; if the address is already in the history on GitHub, delete and recreate the
  repo (section "The first time").

Neither message ever names the address found.

### Per version

```sh
scripts/release.sh freigeben <Stufe>
scripts/veroeffentlichen.sh --ziel <Arbeitskopie> --ref vX.Y.Z
git -C <Arbeitskopie> add -A
git -C <Arbeitskopie> commit -s -m "BMS X.Y.Z"
git -C <Arbeitskopie> push origin main
# … CI im öffentlichen Repo abwarten, sie muss grün sein …
git -C <Arbeitskopie> tag -a vX.Y.Z -m "BMS X.Y.Z"
git -C <Arbeitskopie> push origin vX.Y.Z
scripts/release.sh abholen X.Y.Z
```

1. `freigeben` in the development repo (section "Release procedure"): version, CHANGELOG, commit, tag,
   push. No release is created.
2. `veroeffentlichen.sh --ref vX.Y.Z` exports exactly the signed-off state into the working copy. Use
   `git -C <Arbeitskopie> status` and `diff` to review what changes compared with the last version.
3. One commit with `-s` (adds "Signed-off-by" with the noreply address), message "BMS X.Y.Z".
4. Push `main` first and wait for CI: `ci.yml` tests the state before a tag triggers the release.
5. Then set and push the annotated tag. The tag push starts `release.yml` in the public repo: test,
   package build, release with ZIP, `BMS_latest.zip`, checksums and the installation guides.
6. Check the release: `scripts/release.sh abholen X.Y.Z` downloads from the public repo and compares the
   checksum. On GitHub, the release page shows the notes from the CHANGELOG and eight attachments (two ZIPs, two checksums, four guides).

### Third-party contributions

A pull request is **never merged in the public repo**: the next export would overwrite it. It goes through
the development repo:

1. Take it into the development repo as a patch:
   `gh pr diff <Nr> --repo holgerdaube/BewerbungsMgmtSystem | git apply`.
2. Commit with the trailers `Co-authored-by` and `Signed-off-by` of the contributor (name and address are
   in the pull request).
3. The contribution appears with the next version. Close the pull request with a note about this
   (`gh pr close <Nr> --repo holgerdaube/BewerbungsMgmtSystem --comment "…"`).

### The first time

The repo is first created as **private** and filled using the procedure above (export, commit, CI, tag, release).
Then comes the review on GitHub: home page, file list (no `tasks/`), release with all attachments,
Actions, and in the commit view the `.patch` file (the "From" line names only the noreply address). If
something has slipped through, the repo is deleted and recreated, not patched up: the release,
Actions logs and tags would keep the old state. Only after that is it made public; after that
nothing can be taken back.

When switching, the security features are added that are not available, or only to a limited extent, for private repos on the free plan:
private security reporting (`SECURITY.md` points to it),
Dependabot alerts, secret scanning with push protection, a ruleset for `main` (no force push, no
deletion) and one for the tags `v*` (no moving, no deletion), read-only workflow permissions and the
approval of workflow runs for all external contributors. Wiki and Projects stay off, Issues on.

**Honest limit:** The check finds only what it knows. The profile, database and `pruefmuster.txt` cover today's
data; a name that appears nowhere slips through. That is why reviewing the export before the first switch of the repo to
public remains mandatory.
