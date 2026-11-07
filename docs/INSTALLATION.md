# Installation — Bewerbungs-Management-System

Diese Anleitung beschreibt eine **Neuinstallation von Null** auf einem eigenen Rechner: frisches
Repository, leere Datenbank, eigene Person. Sie ist für jemanden geschrieben, der das System
noch nie gesehen hat, und setzt keine Kenntnis des Projekts voraus — wohl aber die Bereitschaft,
einmal ein Terminal (macOS) bzw. PowerShell (Windows) zu öffnen.

**Keine Datenübernahme:** Wer eine bestehende Installation auf einen anderen Rechner umziehen
will, folgt zwar denselben technischen Schritten, überspringt aber Teil 3 und kopiert
stattdessen `data/`, die persönlichen `config/`-Dateien und das Secrets-Verzeichnis vom alten
Rechner. Diese Anleitung geht davon aus, dass nichts übernommen wird.

**Für Anwender** gibt es je System eine eigene Fassung ohne Projektinterna: `BMS_Install_MAC.md`
(macOS) und `BMS_Install_Windows.md` (Windows) im Hauptordner. Sie führen aus Anwendersicht (mit
Claude) durch dieselben Schritte, laden das Programmpaket aus dem GitHub-Release des öffentlichen
Repos statt aus dem Repository und ergänzen die Aktualisierung. Eine Lizenzdatei braucht das BMS nicht
(Open Source unter Apache-2.0).

## Was das System ist — und was es dafür braucht

Eine lokale Web-Anwendung für die eigene Jobsuche: Stellen erfassen und bewerten, Firmen
prüfen, Lebensläufe und Anschreiben erzeugen, Bewerbungs-E-Mails verfolgen. Sie läuft
vollständig auf dem eigenen Rechner (FastAPI + SQLite + React); es gibt keinen Server-Dienst im
Netz, bei dem man sich anmeldet.

Die inhaltliche Arbeit — Recherche, Textentwürfe, Matching — erledigt **Claude Code** als
Unterprozess, wahlweise die **Codex CLI** von OpenAI (ChatGPT, Vorschau, s. 3.7). Ohne ein aktives
Claude- oder ChatGPT-Konto laufen die Grundfunktionen (Erfassen, Verwalten,
Auswerten, Exportieren), aber alle KI-gestützten Abläufe nicht. Eine Lizenzdatei ist nicht nötig: Alle
Funktionen stehen ohne Lizenz zur Verfügung.

| Voraussetzung | Version | Wozu | Pflicht? |
|---|---|---|---|
| Python | **3.12** | Backend/Server | ja |
| Node.js | **24** | Frontend bauen (einmalig) | ja |
| Git | aktuell | Repository holen | ja |
| Claude Code (CLI) | aktuell | alle KI-Funktionen | faktisch ja |
| LibreOffice | aktuell | Word-Dateien in PDF wandeln | für PDF-Ausgabe |
| Claude-Konto | Abo oder API | Betrieb der KI-Funktionen | für KI-Funktionen |
| Codex CLI (statt Claude Code) | aktuell | KI-Funktionen mit ChatGPT | nur bei ChatGPT |
| ChatGPT-Konto | Plus oder Pro | Betrieb der KI-Funktionen mit ChatGPT | nur bei ChatGPT |

Zeitbedarf: etwa 30–45 Minuten für die Technik (Teil 1 oder 2), danach ein bis zwei Stunden für
die persönliche Einrichtung (Teil 3). Für den LinkedIn-Datenexport, den Teil 3 empfiehlt, sollte
man **einen Tag vorher** den Download bei LinkedIn anstoßen — die Bereitstellung dauert dort bis
zu 24 Stunden.

**Zugang zum Repository:** Das Projekt liegt im öffentlichen GitHub-Repository
`holgerdaube/BewerbungsMgmtSystem`. Zum Klonen brauchen Sie kein GitHub-Konto; eines brauchen Sie erst,
wenn Sie Änderungen einreichen wollen (s. `CONTRIBUTING.md`).

---

# Teil 1 — Schritte unter Windows

Die Backend-Testsuite läuft in der Projekt-Automatik regelmäßig auf `windows-latest` durch. Auf
einem echten Windows-Rechner ist die Installation bisher nicht erprobt, und einzelne Bereiche sind
unter Windows eingeschränkt (siehe Teil 5).

## 1.1 Voraussetzungen installieren

In PowerShell, nacheinander:

```powershell
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
winget install Git.Git
winget install TheDocumentFoundation.LibreOffice
```

Zwei Punkte entscheiden später über Erfolg oder Fehlersuche:

- Beim Python-Installer **„Add python.exe to PATH"** ankreuzen (bei `winget` geschieht das
  automatisch). Prüfen mit `py -3.12 --version` — der `py`-Launcher trifft eindeutig die
  3.12er-Version, auch wenn mehrere Pythons installiert sind.
- LibreOffice **am Standardpfad** lassen (`C:\Program Files\LibreOffice\`). Die App sucht
  `soffice.exe` genau dort; bei abweichendem Installationsort findet sie es nicht und kann keine
  PDFs erzeugen.

Danach Claude Code:

```powershell
winget install -e --id Anthropic.ClaudeCode
```

Prüfen: `claude --version`. Anschließend einmal `claude` starten und sich anmelden — sonst
schlagen später alle KI-Läufe mit einem Authentifizierungsfehler fehl.

## 1.2 Repository holen

```powershell
git clone https://github.com/holgerdaube/BewerbungsMgmtSystem C:\BMS
cd C:\BMS
```

Der Zielordner ist frei wählbar; `C:\BMS` hält die Pfade kurz. **Nicht** in einen
live-synchronisierten Cloud-Ordner (OneDrive, Dropbox) legen — die Datenbank ist eine einzelne
Datei, die dauernd geschrieben wird, und Cloud-Sync erzeugt dort Konflikte.

## 1.3 Python-Umgebung anlegen

Bewusst **außerhalb** des Projektordners, damit Tausende Paketdateien nicht im Projekt liegen:

```powershell
py -3.12 -m venv $env:USERPROFILE\.bewerbung_mgmt_venv
& "$env:USERPROFILE\.bewerbung_mgmt_venv\Scripts\pip.exe" install -r backend\requirements-lock.txt
New-Item -ItemType Junction -Path "$env:USERPROFILE\.bewerbung_mgmt_venv\bin" -Target "$env:USERPROFILE\.bewerbung_mgmt_venv\Scripts"
```

Die `requirements-lock.txt` pinnt exakte Versionen. Wer die Testsuite laufen lassen möchte,
installiert zusätzlich `backend\requirements-dev.txt`.

Die dritte Zeile legt eine Verzeichnis-Verknüpfung `bin` → `Scripts` an. Die Skills rufen Python
durchgängig als `~/.bewerbung_mgmt_venv/bin/python` auf (macOS-Form), ebenso der Pfad-Wächter in
`automation/agent_settings.json`. Claude Code führt diese Befehle unter Windows in Git Bash aus,
das die Verknüpfung auflöst und `python.exe` findet. Ohne sie scheitert in KI-Läufen jeder
Datenbankzugriff. Deshalb ist Git für Windows (1.1) hier Pflicht: Ohne Git Bash weicht Claude Code
auf PowerShell aus, in der die Heredoc-Befehle der Skills nicht laufen. Auf echter Windows-Hardware
ist dieser Weg noch nicht erprobt.

## 1.4 Oberfläche bauen

```powershell
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
```

Das erzeugt `frontend/dist/`. **Ohne diesen Schritt startet der Server zwar, zeigt aber eine
leere Seite** — er liefert die Oberfläche nur aus, wenn dieses Verzeichnis existiert. Das
Skript `frontend/build.sh` ist ein macOS-Workaround und wird unter Windows nicht verwendet.

`npm.cmd` statt `npm` ist Absicht: Windows PowerShell blockiert auf vielen Rechnern das Skript
`npm.ps1` (Ausführungsrichtlinie), `npm.cmd` ist davon nicht betroffen.

## 1.5 Starten

Doppelklick auf `start_windows.bat` (oder in PowerShell `.\start_windows.bat`). Der Browser
öffnet nach etwa zwei Sekunden `http://localhost:8000`, das Server-Fenster bleibt offen.

Beim allerersten Start legt die Anwendung selbst an, was ihr fehlt: das Verzeichnis `data/`,
die leere Datenbank und eine Startfassung von `config/suchprofile.yaml`.

**Beenden:** `Strg+C` im Server-Fenster. Ist das Fenster geschlossen oder reagiert nicht mehr,
hilft `stop_windows.bat` — es beendet den Prozess auf Port 8000 und fragt vorher nach, falls
gerade KI-Läufe aktiv sind.

## 1.6 Weiter mit Teil 3

Die Anwendung läuft jetzt, ist aber noch leer und kennt die eigene Person nicht. Weiter bei
**Teil 3 — Erste Einrichtung**.

---

# Teil 2 — Schritte unter macOS

macOS ist die Referenzplattform des Projekts: hier ist alles im Alltagsbetrieb erprobt.

## 2.1 Voraussetzungen installieren

[Homebrew](https://brew.sh) vorausgesetzt (falls nicht vorhanden, Installationsbefehl von dort
übernehmen):

```sh
brew install python@3.12 node git
brew install --cask libreoffice
```

Danach Claude Code:

```sh
npm install -g @anthropic-ai/claude-code
```

Prüfen mit `claude --version`, dann einmal `claude` starten und anmelden.

## 2.2 Repository holen

```sh
git clone https://github.com/holgerdaube/BewerbungsMgmtSystem ~/Projekte/BewerbungsMgmtSystem
cd ~/Projekte/BewerbungsMgmtSystem
```

**Zu iCloud Drive:** Das Projekt *kann* in iCloud liegen (etwa als Backup der Arbeitskopie), aber das
erfordert zwei Zusatzmaßnahmen: den Frontend-Build in Abschnitt 2.4 und ein ausgelagertes Git-Verzeichnis
(`.git.nosync`, s. `docs/DOKUMENTATION.md`, Abschnitt „Projektstruktur und Ablageorte“). Wer das nicht
braucht, legt das Projekt schlicht außerhalb ab — diese Anleitung geht davon aus.

## 2.3 Python-Umgebung anlegen

```sh
/opt/homebrew/bin/python3.12 -m venv ~/.bewerbung_mgmt_venv
~/.bewerbung_mgmt_venv/bin/pip install -r backend/requirements-lock.txt
```

Auf Intel-Macs liegt Homebrew unter `/usr/local/bin/python3.12`. Für die Testsuite zusätzlich
`backend/requirements-dev.txt` installieren.

## 2.4 Oberfläche bauen

Liegt das Projekt **außerhalb** von iCloud (Normalfall):

```sh
cd frontend && npm ci && npm run build && cd ..
```

Liegt das Projekt **in iCloud Drive**, stattdessen:

```sh
cd frontend && ./build.sh && cd ..
```

Der Unterschied hat einen konkreten Grund: iCloud materialisiert `node_modules` immer wieder neu
und zerstört dabei die Symlinks, die der Build braucht. `build.sh` weicht deshalb nach
`~/.bewerbung_mgmt_node/` aus und kopiert nur das fertige `dist/` zurück. Außerhalb von iCloud
ist dieser Umweg unnötig.

## 2.5 Starten

Doppelklick auf `start.command` im Finder, oder im Terminal:

```sh
./start.command
```

Der Browser öffnet `http://localhost:8000`. Wie unter Windows legt der erste Start `data/`, die
leere Datenbank und eine Startfassung von `config/suchprofile.yaml` selbst an.

Für den Zugriff aus dem eigenen WLAN (etwa vom Tablet) gibt es `start_lan.command`.
**Beenden:** `Ctrl+C` im Server-Fenster, sonst `stop.command`.

---

# Teil 3 — Erste Einrichtung (beide Plattformen)

Die Anwendung läuft jetzt, weiß aber nichts über die Person, die sich bewirbt. Dieser Teil ist
der eigentliche Kern der Neuinstallation. Die Reihenfolge ist bewusst gewählt: Schritt 3.1 und
3.2 sind Handarbeit an Dateien, alles Weitere geht über die Oberfläche.

> **Windows-Pfade:** Wo unten `data/cv_basis/` steht, ist unter Windows `data\cv_basis\`
> gemeint — relativ zum Projektordner, also z. B. `C:\BMS\data\cv_basis\`.

## 3.1 Die Profil-Datei anlegen (Pflicht)

`config/profil.md` ist die persönliche Stammdatei: Name, Anschrift, Kontakt und die Suchstrategie.
Sie liegt bewusst nicht im Repository. Seit P2-69 pflegt man sie am einfachsten in der Oberfläche:
Seite **Profil**, erste Karte „Identität und Suchstrategie“. Speichern schreibt die Datei und lässt
alles stehen, was die Karte nicht kennt. Der Weg mit dem Texteditor unten funktioniert weiterhin.

Ohne diese Datei läuft das System zwar, aber jeder erzeugte Lebenslauf heißt dann
`CV_Bewerber_…` statt mit dem eigenen Namen, und Anschreiben haben **keinen Briefkopf** (das
System erfindet an dieser Stelle bewusst nichts).

Neue Datei `config/profil.md` mit diesem Inhalt anlegen und die Werte ersetzen:

```markdown
# Kandidatenprofil — Max Mustermann

## Identität
- **Name:** Max Mustermann
- **Positionierung:** Service Delivery Leader · DACH
- **Standort:** Musterweg 3, 12345 Musterstadt
- **Kontakt:** max.mustermann@example.com · +49 170 1234567
- **LinkedIn:** https://www.linkedin.com/in/max-mustermann/
- **Aktuell:** Manager Professional Services @ Beispiel GmbH, seit 2024

## Kurzprofil
Zwei bis vier Sätze zur eigenen Person — diese dienen als Tonvorlage für Anschreiben.

## Zielrolle
- **Ebene:** Director / Head
- **Funktion Plan A:** Professional-Services- / Service-Delivery-Leitung
- **Funktion Plan B:** Head of Customer Success
- **Branche:** Enterprise Software, IT-Services
- **Region:** DACH
- **Zieltermin:** neue Rolle bis 31.12.2026

## Harte Rahmenbedingungen
- Kein Umzug, kein dauerhafter Zweitwohnsitz.
- Mindestens 100 Mitarbeiter beim Zielunternehmen.
- Reine Vertriebsrollen ohne Führungsverantwortung sind kein Fit.

## Sprachen / CV-Fassungen
- **Deutsch:** `data/cv_basis/base_de.docx`
- **Englisch:** `data/cv_basis/base_en.docx`

## Bekannte Skill-Gaps / Red Flags
- (noch keine)

## Empirie aus dem Bewerbungsverlauf
- (wird automatisch gepflegt — Überschrift bitte unverändert stehen lassen)
```

Drei Formatregeln, die tatsächlich ausgewertet werden:

- **Standort** im Format `Straße Nr, PLZ Ort`. Für die Ortszeile im Anschreiben wird das letzte
  Komma-Segment genommen und die Postleitzahl abgetrennt — andere Schreibweisen ergeben eine
  schiefe Zeile.
- **Kontakt**: E-Mail und Telefon mit `·` trennen. Im Briefkopf wird daraus automatisch `|`.
- Die vier Felder **Name, Standort, Kontakt, LinkedIn** werden über ihre Fettschreibung erkannt
  (`**Name:**`). Die Sternchen müssen stehen bleiben; die Reihenfolge ist egal.

Der übrige Text (Kurzprofil, Zielrolle, Rahmenbedingungen) wird nicht maschinell geparst,
sondern von den KI-Abläufen als Kontext gelesen — er darf also frei formuliert sein, sollte aber
konkret sein.

## 3.2 Basis-Lebenslauf hinterlegen (Pflicht für alle CV-Funktionen)

Das System erfindet keinen Lebenslauf. Es nimmt einen vorhandenen als Grundlage und passt ihn je
Stelle an. Erwartet werden **genau zwei Dateien mit festen Namen**:

- `data/cv_basis/base_de.docx` — deutsche Fassung
- `data/cv_basis/base_en.docx` — englische Fassung

Beide sind Word-Dateien (`.docx`, kein PDF). Hochgeladen werden sie seit P2-27 über die
Oberfläche: **Profil → Basis-CVs**, Sprache wählen, Datei wählen, „Hochladen". Der Upload zählt
die erkannten Stationen und warnt, ohne abzulehnen, wenn der Aufbau nicht passt; vor dem
Überschreiben fragt er nach, die alte Fassung wandert in den Papierkorb. Wer nur auf Deutsch sucht,
lädt trotzdem beide hoch (die englische darf eine Kopie sein), sonst brechen englischsprachige
Läufe ab.

**Der Aufbau ist nicht beliebig.** Die Anpassungslogik erkennt die Berufsstationen an einem
festen Muster; hält sich die Datei nicht daran, werden Stationen nicht gefunden oder falsch
zusammengeführt:

| Element | Anforderung |
|---|---|
| Abschnitts-Überschriften | Absatzformat **Überschrift 1**, in Großbuchstaben |
| Name des Erfahrungs-Abschnitts | `BERUFSERFAHRUNG` (deutsch) bzw. `PROFESSIONAL EXPERIENCE` (englisch) |
| Beginn einer Station | Absatzformat **Standard**, Aufbau `Firma` → **Tabulator** → `Zeitraum` |
| Zeile direkt darunter | Positionsbezeichnung, Standard-Format, **fett**, 11 pt, ohne Tabulator |
| Danach | kursive Firmenbeschreibung (ein bis zwei Zeilen) |
| Danach | Erfolge als Aufzählung im Format **Listenabsatz** |
| Abstand vor jeder Station | mindestens 20 pt „Abstand vor" auf der Tabulator-Zeile |

Der Tabulator zwischen Firma und Zeitraum ist das entscheidende Erkennungsmerkmal und darf
**nirgends sonst** im Dokument vorkommen — in anderen Abschnitten (Ausbildung, Zertifikate) trennt
man mit `•`, nicht mit Tabulator.

Praktisch: einen vorhandenen Lebenslauf in Word öffnen, die Abschnittsüberschriften auf
„Überschrift 1" setzen, je Station eine Zeile `Firma⇥Zeitraum` einziehen und die Aufzählungen
als Listenabsatz formatieren.

## 3.3 LinkedIn-Datenexport einlesen (empfohlen)

Der schnellste Weg, Werdegang und Fähigkeiten zu befüllen, ohne alles abzutippen.

Bei LinkedIn: **Einstellungen → Datenschutz → „Eine Kopie Ihrer Daten erhalten"** und dort die
**oberste** Option („größeres Datenarchiv") wählen. Die Schnellauswahl „Profile" enthält nur die
Kurzbeschreibung und reicht nicht. LinkedIn stellt das Archiv innerhalb von bis zu 24 Stunden
bereit und schickt eine E-Mail.

Das erhaltene ZIP dann in der Anwendung unter **Profil** hochladen. Übernommen werden
Kurzbeschreibung, Standort, Fähigkeiten, Berufsstationen, Ausbildung und Zertifikate. Der Import
arbeitet rein mechanisch, ergänzt nur und überschreibt nichts Vorhandenes. Im Anschluss sortiert
ein Hintergrundlauf die importierten Fähigkeiten automatisch in Themenbereiche ein.

Ein erfundenes Beispiel liegt unter `beispiele/LinkedIn_Datenexport_Beispiel_DE.zip` (englisch
`beispiele/LinkedIn_Data_Export_Example_EN.zip`). Es zeigt den Aufbau des Exports und enthält mit
`Connections.csv` auch zwei Kontakte für den Netzwerk-Import.

Danach das Profil in der Oberfläche durchsehen und ergänzen: Positionierung schärfen,
Berufsstationen vervollständigen, Zeugnisse und Zertifikate anhängen.

> **Hinweis:** Die Datei `config/profil_struktur.md` gehört nicht zum Repository. Die Anwendung erzeugt sie
> selbst aus den Daten der Profil-Seite (beim Start, wenn sie fehlt, und bei jedem Speichern, auch durch
> den ZIP-Import). Sie ist die „Substanz", die das System bei Anschreiben und Lebenslauf heranzieht, und
> wird nicht von Hand bearbeitet.

## 3.4 Einstellungen in der Oberfläche setzen

Unter **Einstellungen**, in dieser Reihenfolge:

1. **Suchbereich und Firmengröße** — Remote, deutschlandweit und/oder Stadt mit Umkreis;
   Mindest-Mitarbeiterzahl. Der Umkreis erzeugt intern eine Kategorie wie `Musterstadt +50km`,
   die später an jeder Stelle auftaucht. Ändert man Stadt oder Radius später erneut, stellt die
   Anwendung vorhandene Stellen automatisch auf die neue Bezeichnung um.
2. **Pläne A/B/C** — die Zielrollen: Titel, Ebene und Branche je Plan. Plan A ist das
   eigentliche Ziel, Plan B die realistische Alternative, Plan C optional als Auffangebene.
   **Diese Felder sind nach der Installation leer** und müssen ausgefüllt werden — vorher findet
   die Jobsuche nichts, weil sie nicht weiß, wonach sie suchen soll.
3. **Suchportale** — sechs Portale sind vorbelegt und aktiv; bei Bedarf einzelne abschalten oder
   zwei eigene ergänzen. Die Schaltfläche zum Prüfen zeigt, welche antworten. Die Portale sind auf
   Deutschland ausgerichtet; außerhalb helfen die freien Zeilen, LinkedIn-Alerts und die Zielfirmen.
4. **KI-Modelle je Funktion** — Voreinstellung ist überall Sonnet. Das kann so bleiben.

Nach dem ersten Speichern schreibt die Anwendung `config/suchprofile.yaml` neu und trägt die
Eingaben dort ein.

## 3.5 Zielprofil anpassen

Eine Datei im Repository enthält ein Beispiel-Zielprofil und wird von den Suchabläufen gelesen. Wer sie
nicht anpasst, bekommt Bewertungen nach den Kriterien des Beispiels:

**`config/scoring_rubrik.md`**, Abschnitt *Dimension 2 — Funktion*: die Beschreibung von
Plan A, B und C (im Beispiel „PS- oder Service-Delivery-Leitung" bzw. „Head of Customer
Success"). Die Bewertungsskala 1–5 und die Situationscodes (BUILD, CARVE-OUT, POST-MERGER …)
sind allgemeingültig und bleiben unverändert.

Die Region selbst muss nirgends mehr von Hand angepasst werden: Sobald in Schritt 3.4 Stadt und
Umkreis gesetzt sind, übernehmen Jobliste, Filter und die Suchabläufe (`jobsuche`,
`mail-jobsuche`, `angebot-vergleich`) die Bezeichnung automatisch aus den Einstellungen.

## 3.6 E-Mail-Konto verbinden (optional, aber empfohlen)

Ohne E-Mail-Anbindung entfallen der tägliche Postfach-Abgleich und die Auswertung von
Job-Benachrichtigungen. Unter **Einstellungen → E-Mail-Konto**; empfohlen ist der IMAP-Weg mit
einem **App-Passwort** des Mail-Anbieters (nicht das normale Kennwort). Host und Port für die
gängigen Anbieter sowie den alternativen Gmail-Weg beschreibt `docs/SETUP-EMAIL.md`.

Das System **versendet nie selbst E-Mails**. Es legt ausschließlich Entwürfe an, die man selbst
prüft und abschickt.

## 3.7 Automatische Läufe freischalten (optional)

Für Abläufe, die im Hintergrund starten (tägliche Jobsuche, Firmenprüfung, Postfach-Abgleich),
braucht der Server ein eigenes Zugangstoken für Claude Code. Erzeugen mit:

```sh
claude setup-token
```

Das ausgegebene Token in eine Datei `agent.env` im Secrets-Verzeichnis schreiben, als eine Zeile
`CLAUDE_CODE_OAUTH_TOKEN=…`. Das Verzeichnis liegt bewusst außerhalb des Projekts:

- macOS: `~/.bewerbung_mgmt_secrets/agent.env`
- Windows: `%USERPROFILE%\.bewerbung_mgmt_secrets\agent.env`

Als Vorlage dient `automation/agent.env.example`. Achtung beim Kopieren: Bricht das Token über
mehrere Zeilen um, gehören die Teile wieder in eine Zeile — eine Zeile ohne `=` ist die
Fortsetzung der vorherigen. Nach dem Anlegen den Server neu starten.

**Mit ChatGPT statt Claude (Vorschau):** Die Codex CLI installieren (`npm install -g @openai/codex`,
unter macOS auch `brew install --cask codex`), einmal mit dem ChatGPT-Konto anmelden (`codex login`,
prüfen mit `codex login status`, erwartet „Logged in using ChatGPT“) und in den Einstellungen in der
Karte „KI“ ChatGPT wählen (oder `PATCH /api/einstellungen` mit `{"ki_anbieter":"chatgpt"}`). Ein
Token und `agent.env` sind dafür nicht nötig. Die Inhalte der KI-Läufe gehen dann an OpenAI statt an
Anthropic. Unter Windows nutzen Sie `npm.cmd` und `codex.cmd`; die bevorzugte Sandbox von Codex braucht
dort laut OpenAI einmalig ein Administrator-Setup, und der Weg ist unter Windows nicht erprobt.

Zusätzlich muss die Freigabeliste `automation/agent_settings.json` den Pfad zum Python der virtuellen
Umgebung treffen. Sie nennt ihn in der `~`-Form (`~/.bewerbung_mgmt_venv/bin/python`); liegt Ihre Umgebung
woanders, tragen Sie den tatsächlichen Pfad ein. Ein Platzhalter genügt an dieser Stelle nicht — der
Eintrag muss den Pfad exakt treffen. Weicht der venv-Pfad ab, den Hook-Befehl im `hooks`-Block derselben
Datei (prüft Write/Edit-Ziele gegen die Projektwurzel, s. `docs/DOKUMENTATION.md` Abschnitt 8) ebenfalls
anpassen — er ruft dieselbe venv-Python-Installation auf wie die Freigabeliste. Wer im Projekt selbst mit
Claude Code entwickelt und die Vorschau nutzt, legt sich dafür eine eigene `.claude/launch.json` an; sie
gehört nicht zum Repository.

Die Secrets-Datei legen Sie unter macOS so an (Windows: entsprechend im Benutzerordner):

```sh
mkdir -p ~/.bewerbung_mgmt_secrets && chmod 700 ~/.bewerbung_mgmt_secrets
cp automation/agent.env.example ~/.bewerbung_mgmt_secrets/agent.env
chmod 600 ~/.bewerbung_mgmt_secrets/agent.env
```

Die Gmail-Zugangsdaten (`gmail_credentials.json`, `gmail_token.json`, nur beim Gmail-API-Weg aus
`docs/SETUP-EMAIL.md`) landen im selben Verzeichnis. Der Ort lässt sich über `BMS_SECRETS_DIR` ändern.

## 3.8 Kosmetik

Der Browser-Tab zeigt den Produktnamen, dahinter den Namen aus `config/profil.md`; die Seitenleiste liest
den Namen ebenfalls dynamisch und stimmt nach Schritt 3.1 automatisch. Der Produktname kommt aus dem
Design (`docs/DOKUMENTATION.md`, Abschnitt „Design aus einer Quelle“); der statische `<title>` in
`frontend/index.html` ist nur der Anfangswert, bis das Design geladen ist.

## 3.9 Optionale Umgebungsvariablen und Entwicklungswerkzeuge

`.env.example` listet die Einstellungen, die vom Standard abweichen dürfen: Server-Port und -Adresse,
`BMS_DATA_DIR`, `BMS_SECRETS_DIR` und die Grenzen für KI-Läufe. Das Programm liest sie ausschließlich aus
der Umgebung; eine Datei `.env` lädt es nicht selbst. Setzen Sie die Werte deshalb in der Shell, die den
Server startet, zum Beispiel `PORT=8010 ./start.command`.

Wer am Quellcode arbeitet, installiert einmalig `backend/requirements-dev.txt` und den Secret-Guard
(`scripts/install_hooks.sh`, prüft vor jedem Commit auf Token). Die Tests laufen mit `scripts/test.sh`
gegen eine Wegwerf-Datenbank. Einzelheiten und die Regeln für Beiträge stehen in
`docs/DOKUMENTATION.md` (Abschnitt „Tests & CI“) und in `CONTRIBUTING.md`.

---

# Teil 4 — Prüfen, ob alles sitzt

Diese kurze Runde deckt die typischen Installationsfehler auf:

| Prüfung | Erwartung | Wenn nicht |
|---|---|---|
| `http://localhost:8000` öffnen | Oberfläche mit Menü erscheint | Frontend nicht gebaut (Schritt 1.4 / 2.4) |
| Seite **Einstellungen** öffnen | Karten werden angezeigt, kein Fehler | Server neu starten; Meldung im Server-Fenster lesen |
| Karte **Programmversion**, Knopf „Nach Updates suchen“ | Der Knopf zeigt die neueste Version oder einen Fehlertext (gibt es noch kein veröffentlichtes Release: „Es ist noch keine Version veröffentlicht.“) | Internetverbindung und Zugriff auf GitHub prüfen (Firmennetz, Proxy) |
| Seite **Profil** öffnen | eigener Name in der Kopfzeile | `config/profil.md` prüfen (Schreibweise `**Name:**`) |
| Eine Stelle von Hand anlegen | Eintrag erscheint in der Liste | Server-Fenster auf Fehlermeldungen prüfen |
| Seite **Aufgaben**, einen Lauf starten | Lauf beginnt und endet mit Ergebnis | Claude-Anmeldung und Token prüfen (Schritt 3.7) |
| Lebenslauf für eine Stelle erzeugen | Word- und PDF-Datei entstehen | Basis-Lebenslauf (3.2) und LibreOffice-Pfad prüfen |

Wer die technische Basis vollständig absichern will, kann die Testsuite laufen lassen (setzt
`requirements-dev.txt` voraus):

```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pytest tests -q
```

Unter Windows entsprechend mit `%USERPROFILE%\.bewerbung_mgmt_venv\Scripts\python.exe`. Einige
Tests überspringen sich dort planmäßig, weil sie Unix-Eigenheiten prüfen — das ist kein Fehler.

Auf einer eigenen Installation können außerdem einzelne Tests anders ausgehen als in der CI: Sobald
`config/profil.md` und die Basis-CVs unter `data/cv_basis` existieren, prüfen manche Tests auch gegen
diese lokalen Dateien. Das ist kein Installationsfehler; die CI läuft ohne diese Dateien und ist der
Maßstab.

---

# Teil 5 — Grenzen und häufige Stolpersteine

**Unter Windows nicht verfügbar** (Details in `docs/SETUP-WINDOWS.md`):

- **Zeitgesteuerte Automatik.** Der tägliche Lauf zu fester Uhrzeit ist macOS-spezifisch; unter
  Windows startet man ihn über die Schaltfläche in der Oberfläche.
- **Drei Sammelfunktionen** — „Ansichten aktualisieren" (Excel-Export, Tages-Digest,
  Suchindex), „Anschreiben rendern" und der Coach-Site-Upload — rufen intern ein Unix-Skript auf
  und melden unter Windows „Binary nicht gefunden". Die dahinterliegenden Python-Module lassen
  sich direkt aufrufen.
- **Die Hilfsskripte in `scripts/`** setzen die Unix-Verzeichnisstruktur der virtuellen Umgebung
  voraus und laufen auch in Git-Bash nicht unverändert.

**Auf beiden Plattformen:**

- **Kein Auto-Reload.** Nach Änderungen an Backend-Dateien muss der Server neu gestartet werden.
- **Die Datenbank ist eine einzelne Datei** (`data/bewerbung.sqlite`). Das BMS sichert sie
  automatisch: einmal täglich als ZIP nach `data/backups/auto`, mit fester Aufbewahrung
  (Einstellungen in der Oberfläche unter „Datensicherung"). Vor besonders riskanten Aktionen
  zusätzlich eine eigene Kopie anlegen; unter macOS gibt es dafür `scripts/backup_db.sh`.
- **Zwei Installationen gleichen sich nicht ab.** Wer das System auf zwei Rechnern betreibt,
  führt zwei getrennte Datenbestände — eine Zusammenführung ist Handarbeit.
- **Der Excel-Export der Kontaktliste** greift auf eine Vorlagendatei zurück, die bei einer
  Neuinstallation nicht existiert; diese eine Funktion meldet dann einen Fehler. Alle übrigen
  Exporte sind davon nicht betroffen.
- **Kosten entstehen bei den KI-Läufen.** Die Budget-Seite zeigt den Verbrauch und bremst bei
  Überschreitung; Voreinstellungen werden beim ersten Aufruf automatisch angelegt.

**Rechtliches:** Das BMS steht unter der Apache License 2.0 (`LICENSE`, `NOTICE`) und braucht keine
Lizenzdatei. Bis Version 1.7.0 gab es eine Lizenzpflicht; sie wurde in P2-82 ausgebaut (Hintergrund
und Technik: `docs/DOKUMENTATION.md`, Abschnitt „Lizenz — ausgebaut“). Ältere Lizenzdateien im
Secrets-Verzeichnis werden nicht mehr gelesen und dürfen gelöscht werden.

---

# Teil 6 — Weiterführende Unterlagen

| Datei | Inhalt |
|---|---|
| `docs/ANLEITUNG.md` | Bedienung im Alltag — der beste Einstieg nach der Installation |
| `docs/SETUP-EMAIL.md` | E-Mail-Anbindung im Detail (IMAP und Gmail) |
| `docs/SETUP-WINDOWS.md` | Windows-Besonderheiten, Grenzen, Support-Matrix |
| `docs/DOKUMENTATION.md` | Systemaufbau, Betrieb im Alltag (Starten, Beenden, Backup), Tests und Entwicklungsstand |
| `docs/RELEASE.md` | Versions- und Freigabeworkflow (nur relevant, wer selbst Pakete freigibt) |
| `CONTRIBUTING.md` | Regeln für Beiträge (Lizenz, Sprache, Tests) |
| `SECURITY.md` | Sicherheitslücken melden |
| `README.md`, `README.de.md` | Projektüberblick für Anwender auf Englisch und Deutsch: Installation, Updates, Datenschutz, Lizenz |
