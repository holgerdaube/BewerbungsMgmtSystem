## Third-party licences

This software uses open-source components. Each has its own licence. The installation downloads the packages in exactly these versions from the public PyPI and npm registries. “Show licence texts” below shows the full wording of all licences. In the program folder it is in the file frontend/src/rechtliches/drittlizenzen_texte.txt.

### Backend (Python), used directly

- **bcrypt** 5.0.0 — Apache-2.0 — Password hash of the coach site
- **fastapi** 0.140.0 — MIT — Web interface of the backend
- **google-auth** 2.56.2 — Apache-2.0 — Gmail connection
- **google-auth-oauthlib** 1.4.0 — Apache-2.0 — Sign-in to Gmail
- **httpx** 0.28.1 — BSD-3-Clause — Requests to Apify, the Federal Employment Agency, OpenAI
- **Markdown** 3.10.3 — BSD-3-Clause — Documentation to HTML
- **openpyxl** 3.1.5 — MIT — Excel import (network, lists)
- **pypdf** 6.21.4 — BSD-3-Clause — Reading text from the LinkedIn profile PDF
- **python-docx** 1.2.0 — MIT — Word files (CV, cover letter)
- **python-multipart** 0.0.32 — Apache-2.0 — File uploads
- **PyYAML** 6.0.3 — MIT — Configuration (search profiles, budgets)
- **sqlmodel** 0.0.39 — MIT — Data model and database access
- **uvicorn** 0.51.0 — BSD-3-Clause — local web server

### Backend (Python), brought in by these packages

- **annotated-doc** 0.0.4 — MIT
- **annotated-types** 0.8.0 — MIT
- **anyio** 4.14.2 — MIT
- **certifi** 2026.10.23 — MPL-2.0
- **cffi** 2.1.0 — MIT-0
- **charset-normalizer** 3.4.9 — MIT
- **click** 8.4.2 — BSD-3-Clause
- **cryptography** 50.0.2 — Apache-2.0 OR BSD-3-Clause
- **et_xmlfile** 2.0.0 — MIT
- **h11** 0.16.0 — MIT
- **httpcore** 1.0.9 — BSD-3-Clause
- **idna** 3.18 — BSD-3-Clause
- **lxml** 6.1.1 — BSD-3-Clause
- **oauthlib** 4.0.1 — BSD-3-Clause
- **pyasn1** 0.6.5 — BSD-2-Clause
- **pyasn1_modules** 0.4.2 — BSD-2-Clause
- **pycparser** 3.0 — BSD-3-Clause
- **pydantic** 2.13.4 — MIT
- **pydantic_core** 2.46.4 — MIT
- **requests** 2.34.2 — Apache-2.0
- **requests-oauthlib** 2.0.0 — ISC
- **SQLAlchemy** 2.0.51 — MIT
- **starlette** 1.3.1 — BSD-3-Clause
- **typing-inspection** 0.4.2 — MIT
- **typing_extensions** 4.16.0 — PSF-2.0
- **urllib3** 2.8.0 — MIT

### Interface (runs in the browser), used directly

- **@fontsource/inter** 5.3.0 — OFL-1.1 — Inter typeface (body text)
- **@fontsource/montserrat** 5.3.0 — OFL-1.1 — Montserrat typeface (headings)
- **i18next** 26.5.3 — MIT — Interface in several languages
- **react** 18.3.1 — MIT — Basis of the interface
- **react-dom** 18.3.1 — MIT — Rendering in the browser
- **react-i18next** 17.1.0 — MIT — Multiple languages in the interface
- **react-router-dom** 7.18.5 — MIT — Page navigation

### Interface, brought in

- **@babel/runtime** 7.29.10 — MIT
- **cookie** 1.1.1 — MIT
- **html-parse-stringify** 4.0.1 — MIT
- **js-tokens** 4.0.0 — MIT
- **loose-envify** 1.4.0 — MIT
- **react-router** 7.18.5 — MIT
- **scheduler** 0.23.2 — MIT
- **set-cookie-parser** 2.7.3 — MIT
- **use-sync-external-store** 1.7.0 — MIT

### For building the interface

- **@types/react** 18.3.31 — MIT
- **@types/react-dom** 18.3.7 — MIT
- **@vitejs/plugin-react** 4.7.0 — MIT
- **autoprefixer** 10.5.4 — MIT
- **postcss** 8.5.23 — MIT
- **tailwindcss** 3.4.19 — MIT
- **typescript** 5.9.3 — Apache-2.0
- **vite** 6.4.5 — MIT

In addition there are 173 more tools that these bring in. They only run during the build and are not part of the finished interface. Licences of all 181: 165 × MIT, 10 × ISC, 4 × Apache-2.0, 1 × BSD-3-Clause, 1 × CC-BY-4.0.

### Programs installed separately by the user

- **Python** — PSF-2.0 — Runtime of the backend
- **SQLite** — Public Domain — Database (included in Python)
- **Node.js** — MIT — builds the interface during installation and updates
- **Claude Code** — proprietary (Anthropic) — runs the AI functions if Claude is selected
- **Codex CLI** — Apache-2.0 — runs the AI functions if ChatGPT is selected
- **LibreOffice** — MPL-2.0 — converts CVs to PDF
- **Homebrew** — BSD-2-Clause — installs the programs (macOS)
- **winget** — MIT — installs the programs (Windows)
- **Git for Windows** — GPL-2.0 — needed by Claude Code on Windows
- **lftp** — GPL-3.0 — uploads the coach site via SFTP (optional)
- **htpasswd (Apache httpd)** — Apache-2.0 — password file of the coach site (optional)

They are not part of this software. The BMS calls them as independent programs.

### Third-party services connected by users

These services are not part of this software. Their use is subject to the terms of the respective provider, see the privacy notice.

- **Anthropic (Claude, Claude Code)**: AI functions if Claude is selected, with your own account or API key
- **OpenAI (ChatGPT, Codex CLI)**: AI functions if ChatGPT is selected, with your own ChatGPT account; also an optional second engine for the Advisory Board, with your own API key
- **Apify** (optional): portal search with scrapers by third-party developers, with your own account
- **Job search of the German Federal Employment Agency**: fetching the public search page, no account
- **The user's email provider** (IMAP) or **Google Gmail**: reading replies and job alerts
- **Google Drive** (optional): export of the outreach tracker
- **GitHub**: checking for updates and downloading new versions, only when the user starts it, no account

---

This overview is generated from the program's package lists.
