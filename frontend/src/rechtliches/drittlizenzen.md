## Drittanbieter-Lizenzen

Diese Software verwendet Open-Source-Bestandteile. Für jeden gilt seine eigene Lizenz. Die Installation lädt die Pakete in genau diesen Versionen aus den öffentlichen Paketverzeichnissen PyPI und npm. Den vollständigen Wortlaut aller Lizenzen zeigt „Lizenztexte anzeigen“ unten. Im Programmordner steht er in der Datei frontend/src/rechtliches/drittlizenzen_texte.txt.

### Backend (Python), direkt verwendet

- **bcrypt** 5.0.0 — Apache-2.0 — Passwort-Hash der Coach-Site
- **fastapi** 0.140.0 — MIT — Web-Schnittstelle des Backends
- **google-auth** 2.56.2 — Apache-2.0 — Gmail-Anbindung
- **google-auth-oauthlib** 1.4.0 — Apache-2.0 — Anmeldung bei Gmail
- **httpx** 0.28.1 — BSD-3-Clause — Abrufe bei Apify, Arbeitsagentur, OpenAI
- **Markdown** 3.10.3 — BSD-3-Clause — Dokumentation nach HTML
- **openpyxl** 3.1.5 — MIT — Excel-Import (Netzwerk, Listen)
- **pypdf** 6.21.4 — BSD-3-Clause — Text aus dem PDF des LinkedIn-Profils lesen
- **python-docx** 1.2.0 — MIT — Word-Dateien (Lebenslauf, Anschreiben)
- **python-multipart** 0.0.32 — Apache-2.0 — Datei-Uploads
- **PyYAML** 6.0.3 — MIT — Konfiguration (Suchprofile, Budgets)
- **sqlmodel** 0.0.39 — MIT — Datenmodell und Datenbankzugriff
- **uvicorn** 0.51.0 — BSD-3-Clause — lokaler Webserver

### Backend (Python), von diesen Paketen mitgebracht

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

### Oberfläche (läuft im Browser), direkt verwendet

- **@fontsource/inter** 5.3.0 — OFL-1.1 — Schrift Inter (Fließtext)
- **@fontsource/montserrat** 5.3.0 — OFL-1.1 — Schrift Montserrat (Überschriften)
- **react** 18.3.1 — MIT — Grundgerüst der Oberfläche
- **react-dom** 18.3.1 — MIT — Darstellung im Browser
- **react-router-dom** 7.18.5 — MIT — Seitennavigation

### Oberfläche, mitgebracht

- **cookie** 1.1.1 — MIT
- **js-tokens** 4.0.0 — MIT
- **loose-envify** 1.4.0 — MIT
- **react-router** 7.18.5 — MIT
- **scheduler** 0.23.2 — MIT
- **set-cookie-parser** 2.7.3 — MIT

### Zum Bauen der Oberfläche

- **@types/react** 18.3.31 — MIT
- **@types/react-dom** 18.3.7 — MIT
- **@vitejs/plugin-react** 4.7.0 — MIT
- **autoprefixer** 10.5.4 — MIT
- **postcss** 8.5.23 — MIT
- **tailwindcss** 3.4.19 — MIT
- **typescript** 5.9.3 — Apache-2.0
- **vite** 6.4.5 — MIT

Dazu kommen 173 weitere Werkzeuge, die diese mitbringen. Sie laufen nur beim Bauen und sind nicht Teil der fertigen Oberfläche. Lizenzen aller 181: 165 × MIT, 10 × ISC, 4 × Apache-2.0, 1 × BSD-3-Clause, 1 × CC-BY-4.0.

### Separat vom Nutzer installierte Programme

- **Python** — PSF-2.0 — Laufzeit des Backends
- **SQLite** — Public Domain — Datenbank (in Python enthalten)
- **Node.js** — MIT — baut die Oberfläche bei Installation und Update
- **Claude Code** — proprietär (Anthropic) — führt die KI-Funktionen aus, wenn Claude gewählt ist
- **Codex CLI** — Apache-2.0 — führt die KI-Funktionen aus, wenn ChatGPT gewählt ist
- **LibreOffice** — MPL-2.0 — wandelt Lebensläufe in PDF um
- **Homebrew** — BSD-2-Clause — installiert die Programme (macOS)
- **winget** — MIT — installiert die Programme (Windows)
- **Git for Windows** — GPL-2.0 — wird von Claude Code unter Windows gebraucht
- **lftp** — GPL-3.0 — lädt die Coach-Site per SFTP hoch (optional)
- **htpasswd (Apache httpd)** — Apache-2.0 — Passwortdatei der Coach-Site (optional)

Sie sind nicht Bestandteil dieser Software. Das BMS ruft sie als eigenständige Programme auf.

### Von Nutzern angebundene Drittdienste

Diese Dienste sind keine Bestandteile dieser Software. Ihre Nutzung unterliegt den Bedingungen des jeweiligen Anbieters, s. Datenschutzerklärung.

- **Anthropic (Claude, Claude Code)**: KI-Funktionen, wenn Claude gewählt ist, mit eigenem Konto oder eigenem API-Schlüssel
- **OpenAI (ChatGPT, Codex CLI)**: KI-Funktionen, wenn ChatGPT gewählt ist, mit eigenem ChatGPT-Konto; außerdem optional zweiter Motor für den Beirat, mit eigenem API-Schlüssel
- **Apify** (optional): Portal-Suche mit Scrapern von Drittentwicklern, mit eigenem Konto
- **Jobsuche der Bundesagentur für Arbeit**: Abruf der öffentlichen Suchseite, ohne Konto
- **E-Mail-Anbieter des Nutzers** (IMAP) oder **Google Gmail**: Antworten und Job-Alerts lesen
- **Google Drive** (optional): Export des Outreach-Trackers
- **GitHub**: Suche nach Updates und Laden neuer Versionen, nur auf Start des Nutzers, ohne Konto

---

Diese Übersicht wird aus den Paketlisten des Programms erzeugt.
