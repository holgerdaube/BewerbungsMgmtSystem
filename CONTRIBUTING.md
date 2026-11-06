# Contributing

**English** · [Deutsch](CONTRIBUTING.de.md)

Thank you for wanting to work on BMS – Job Application Management System. This page sums up the rules for
contributions. If you have only found a bug, an issue is enough:
https://github.com/holgerdaube/BewerbungsMgmtSystem/issues. Please do not report a **security vulnerability**
there, follow [`SECURITY.md`](SECURITY.md) instead.

## Licence and proof of origin (DCO)

BMS is under the Apache License 2.0 (`LICENSE`). A contribution you submit is under the same licence
(section 5 of the licence).

The project also requires the **Developer Certificate of Origin** (DCO, version 1.1,
https://developercertificate.org). With it you confirm that you wrote the contribution yourself or have the
right to submit it under this licence. You do this by signing every commit with `-s`:

```sh
git commit -s -m "Kurze Beschreibung der Änderung"
```

Git then adds the line `Signed-off-by: Your Name <your@address>` to the commit message. Name and address come
from `git config user.name` and `git config user.email`. If you do not want to publish your private email
address, use the noreply address of your GitHub account. If you forgot to sign, `git commit --amend -s` helps
for the last commit, and `git rebase --signoff` for several commits.

## Setting up development

[`docs/en/INSTALLATION.md`](docs/en/INSTALLATION.md) explains how to set up the source code on macOS and Windows
(Python environment, building the interface, starting). [`docs/en/DOKUMENTATION.md`](docs/en/DOKUMENTATION.md)
describes the architecture, data model and conventions. Before a larger change, read the sections “Basic
principles” and “Tests & CI” there.

## Language

- **Interface:** Texts always exist in both languages (`frontend/src/i18n/de` and `en`, in the backend `tx()`).
  CI checks this.
- **User documentation:** English and German in the same commit, confirmed with
  `scripts/uebersetzung.sh --bestaetigen <English file>`.
- **Terminal:** Messages from the tools in `scripts/`, the start and stop scripts and the server (`tt()`) exist in both languages and follow the language of the operating system, not the interface.
- **Source:** German is the source of the documentation. The technical documentation may lag until the next
  release.
- **Code:** Code comments, docstrings, commit messages and skills are in German. English issues and pull requests
  are welcome.
- **Form of address and spelling:** German texts in the interface and in `CHANGELOG.md` use the formal “Sie”,
  English texts use British English.

## Tests before the pull request

Every change in behaviour needs a test, and the whole suite must be green before you open the pull request:

```sh
scripts/test.sh                      # backend tests (once: install backend/requirements-dev.txt)
cd frontend && npm run typecheck && npm run build   # if you changed the interface
```

The tests run against their own throwaway database and do not touch your real `data/bewerbung.sqlite`. CI
repeats the check on every pull request on Linux and Windows, plus type checking, the build and a secret scan.

## No real personal data

Code, tests, examples, documentation and commit messages contain **no real personal data and no real application
data**: no names, addresses, email addresses or phone numbers of real people, no company names, jobs or numbers
from your own job search, no CVs, no credentials. Use invented values: Max Mustermann or Benno Bewerbaer as a
person, Beispiel GmbH or Firma A as a company, addresses under `beispiel.de`. Check your change with `git diff`
for data you picked up by accident before you submit it.

## Guardrails for new features

- **Only for the person applying.** BMS supports only the side that applies. Features that let employers score,
  sort or select applicants will not be accepted (basic principle 8 in `docs/en/DOKUMENTATION.md`).
- **The human decides.** BMS does not apply on its own and sends no email, it only creates drafts (basic principle
  1). A sending code path has no place in the project, and a test (`test_kein_sendcodepfad.py`) enforces this.
- **No invented facts.** AI texts work from evidence. What the system does not know, it marks instead of guessing
  (basic principle 2).
- **Two AIs, one wording.** The AI runs go through either Claude Code or the Codex CLI (ChatGPT). The skills in
  `.claude/skills` are the only source: BMS mirrors them to `.agents/skills` (not versioned) before every run, and
  `AGENTS.md` translates the tool names. Never change the copy under `.agents/skills`, and write skills so that they
  run under both AIs.

## Documentation

The documents in `docs/` are Markdown files (`.md`, the source). Each has a generated `.html` file for printing
and passing on. After every change to an `.md`, regenerate the HTML version and submit both files together:

```sh
scripts/docs_html.sh
```

A test (`backend/tests/test_docs_html.py`) fails if an `.html` is missing or out of date. Changes that users notice
also go into `CHANGELOG.md` and `CHANGELOG.en.md` under “Unreleased” (`Unveröffentlicht` in the German file), in one
or two sentences and without internal numbers.

## Pull request

1. Create a fork and work on your own branch.
2. Keep the pull request small and on one topic. Describe what changes and why.
3. Sign every commit (`git commit -s`), see above.
4. Run `scripts/test.sh` and wait for CI. A pull request can only be merged when CI is green.
