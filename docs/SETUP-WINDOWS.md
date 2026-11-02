# Windows-Setup

> **Neu installieren?** Die Installation unter Windows steht Schritt für Schritt in
> `BMS_Install_Windows.md`. Claude führt Sie damit durch die Installation, auch durch das Laden
> des Programmpakets von GitHub. Eine ZIP-Datei brauchen Sie nur als Ersatzweg. Im BMS
> finden Sie die Anleitung unter „Dokumentation“, Reiter „Installation & Updates“. Dieses
> Dokument vertieft, was unter Windows anders läuft als auf dem Mac, was nicht geht und warum.

Das BMS wird auf dem Mac entwickelt und dort täglich eingesetzt. Unter Windows laufen Server und
Oberfläche, und die Verwaltung von Stellen, Firmen, Kontakten und Terminen funktioniert vollständig.
Einige Bereiche, vor allem die KI-Läufe, sind für Windows umgestellt, aber noch nicht erprobt. Auf
einem echten Windows-Rechner ist das BMS bisher nicht getestet worden. Die Aussagen hier beruhen auf
dem Programmcode und auf den automatischen Tests, die bei jeder Änderung zusätzlich auf einem
Windows-System laufen. Was nicht oder nur eingeschränkt geht, steht unter „Bekannte Grenzen“.

## Voraussetzungen

`BMS_Install_Windows.md`, Schritt „Programme installieren“, installiert die Programme per
`winget`: Python 3.12, Node.js (LTS), Git für Windows, LibreOffice und Claude Code (bei ChatGPT statt
Claude Code die Codex CLI, per `npm.cmd`). Unter Windows kommt es auf drei Punkte an:

1. **Python 3.12:** Prüfen Sie die Version mit `py -3.12 --version`. Der `py`-Launcher trifft
   eindeutig Python 3.12, auch wenn mehrere Versionen installiert sind. Ein bloßes
   `python --version` kann je nach PATH-Reihenfolge eine andere Version treffen.
2. **Git für Windows ist Pflicht:** Die KI-Funktionen arbeiten mit Befehlen, die Claude Code unter
   Windows nur in der mit Git installierten „Git Bash“ ausführen kann.
3. **LibreOffice am Standardpfad:** Das BMS sucht `soffice.exe` zuerst unter
   `C:\Program Files\LibreOffice\program\`, dann unter `C:\Program Files (x86)\LibreOffice\program\`
   und zuletzt im PATH. Liegt LibreOffice woanders und steht sein Ordner `program` nicht im PATH,
   findet das BMS es nicht und erzeugt keine PDF-Dateien. Behalten Sie deshalb den vorgeschlagenen
   Installationsort bei.

**Ohne winget:** Die Programme gibt es auch auf den Seiten der Hersteller:
[python.org](https://www.python.org/downloads/), [nodejs.org](https://nodejs.org/),
[git-scm.com](https://git-scm.com/download/win) und
[libreoffice.org](https://www.libreoffice.org/download/). Kreuzen Sie im Python-Installer
„Add python.exe to PATH“ an, sonst findet Windows den Befehl `python` später nicht. Claude Code
installieren Sie nach der Anleitung von Anthropic.

Für Node.js nennt das BMS keine Mindestversion. Die automatischen Tests bauen die Oberfläche mit
Node.js 24.

## Python-Umgebung einrichten

Meldet `start_windows.bat`, `update_windows.bat` oder `wiederherstellen_windows.bat`, dass die
Python-Umgebung fehlt, holen Sie diesen Schritt nach (`BMS_Install_Windows.md`, Schritt
„Python-Umgebung einrichten“). In PowerShell im Programmordner, etwa `C:\Users\Name\BMS`:

```powershell
py -3.12 -m venv "$env:USERPROFILE\.bewerbung_mgmt_venv"
& "$env:USERPROFILE\.bewerbung_mgmt_venv\Scripts\pip.exe" install -r backend\requirements-lock.txt
New-Item -ItemType Junction -Path "$env:USERPROFILE\.bewerbung_mgmt_venv\bin" -Target "$env:USERPROFILE\.bewerbung_mgmt_venv\Scripts"
```

Die Umgebung liegt bewusst außerhalb des Programmordners, unter
`%USERPROFILE%\.bewerbung_mgmt_venv`. Unter Windows liegt Python dort im Ordner `Scripts`, auf dem
Mac in `bin`. Die KI-Funktionen und der Pfad-Wächter (s. u.) rufen Python immer als
`~/.bewerbung_mgmt_venv/bin/python` auf. Die Verknüpfung `bin` → `Scripts` aus der dritten Zeile
sorgt dafür, dass dieser Aufruf auch unter Windows ankommt. Fehlt sie, scheitert in KI-Läufen
jeder Zugriff auf die Datenbank.

## Oberfläche bauen

Unter Windows bauen Sie die Oberfläche direkt im Ordner `frontend` mit `npm.cmd ci` und
`npm.cmd run build` (`BMS_Install_Windows.md`, Schritt „Oberfläche bauen“). Schreiben Sie
`npm.cmd` und nicht nur `npm`: PowerShell blockiert auf vielen Rechnern das Skript `npm.ps1`,
`npm.cmd` ist davon nicht betroffen. Das Skript `frontend/build.sh` gehört zu Mac-Installationen
in iCloud Drive und wird unter Windows nicht gebraucht.

## Zugangsschlüssel und Secrets

Den Zugangsschlüssel für die KI-Läufe im Hintergrund legt `BMS_Install_Windows.md`, Schritt
„KI-Zugang einrichten“, in `%USERPROFILE%\.bewerbung_mgmt_secrets\agent.env` ab. Dort liegen auch
die übrigen Zugangsdaten des BMS, etwa für das E-Mail-Konto. Einen anderen Ort legen Sie mit der
Umgebungsvariablen `BMS_SECRETS_DIR` fest.

Windows kennt keine Unix-Dateirechte. Auf dem Mac beschränkt das BMS seine Zugangs- und
Protokolldateien auf Ihr Benutzerkonto (`chmod 600` bzw. `700`), unter Windows bleibt dieser
Aufruf ohne Wirkung. Dort schützt allein Ihr Benutzerprofil diese Dateien. Beim Start kann der
Server unter Windows deshalb die Warnung „agent.env: zu offene Rechte … 'chmod 600 …' ausführen“
ausgeben. Unter Windows ist sie gegenstandslos.

## Starten

Doppelklicken Sie im Programmordner auf `start_windows.bat`. Die Datei prüft, ob die
Python-Umgebung da ist, startet den Server mit Port 8000 im Vordergrund und öffnet nach etwa zwei
Sekunden `http://localhost:8000` im Standardbrowser. Lassen Sie das Fenster geöffnet, solange Sie
mit dem BMS arbeiten. Strg+C beendet den Server.

## Beenden

Strg+C im Server-Fenster. Ist das Fenster geschlossen oder reagiert der Server nicht mehr,
doppelklicken Sie auf `stop_windows.bat`. Die Datei fragt per PowerShell beim Server nach, ob gerade
KI-Läufe aktiv oder eingereiht sind. Wenn ja, fragt sie nach, ob Sie trotzdem beenden wollen,
denn ein Stopp bricht diese Läufe ab. `stop_windows.bat --force` überspringt die Rückfrage.
Antwortet der Server nicht mehr, beendet die Datei ihn ohne Rückfrage, sonst ließe sich ein
hängender Server nie stoppen. Sie sucht den Prozess, der auf Port 8000 lauscht (`netstat`),
beendet ihn samt Kindprozessen zunächst regulär und nach 10 Sekunden hart (`taskkill /F /T`).

Der Ablauf entspricht der auf dem Mac erprobten Datei `stop.command`. Unter Windows ist er noch
nicht erprobt.

## Aktualisieren

Beenden Sie das BMS und doppelklicken Sie im Programmordner auf `update_windows.bat`. Den Ablauf
beschreibt `BMS_Install_Windows.md`, Abschnitt „Aktualisierungen einspielen“. Die Datei gibt den
Programmordner an `scripts\bms_update.py` weiter. Das Werkzeug sucht online bei GitHub nach einer
neuen Version und lädt sie, prüft das neue Paket, legt eine Sicherung an, spielt das Update ein,
installiert neue Bausteine und führt einen Selbsttest aus. Es nutzt dieselbe Python-Umgebung wie
der Start (`%USERPROFILE%\.bewerbung_mgmt_venv\Scripts\python.exe`).

**Online-Suche:** Vor der Suche schreibt das Werkzeug: „Suche auf GitHub nach einer neuen Version.
GitHub erhält dabei die IP-Adresse dieses Rechners.“ Übertragen wird die Anfrage selbst und sonst
nichts, und nur, wenn Sie das Werkzeug selbst starten. Das geladene Paket vergleicht das Werkzeug mit
der Prüfsumme, die GitHub zur Datei angibt. Mit `--offline` sucht es nicht online. Erreicht es GitHub
nicht, oder lehnt GitHub die Anfrage ab, zeigt es den Grund und nimmt eine ZIP-Datei
`BMS_<Version>.zip` aus Ihrem Ordner „Downloads“. Die höchste Version gewinnt, egal woher sie kommt.
Ob es eine neue Version gibt, zeigt Ihnen auch der Knopf „Nach Updates suchen“ in den Einstellungen,
Karte „Programmversion“. Er spielt nichts ein.

`update_windows.bat` läuft vollständig in einem Block in runden Klammern, der mit `exit /b`
endet. Der Grund: cmd.exe liest eine Batch-Datei Zeile für Zeile nach, während sie läuft, und das
Update kann genau diese Datei ersetzen. Einen Block in runden Klammern liest cmd.exe vollständig
ein, bevor die erste Zeile darin läuft.

**Zeilenenden:** Die `.bat`-Dateien werden mit Windows-Zeilenenden (CRLF) ausgeliefert, sonst
findet cmd.exe Sprungmarken wie `:label` und `goto` darin nicht zuverlässig. Jedes Programmpaket
wird vor der Auslieferung darauf geprüft. Bearbeiten Sie eine `.bat`-Datei, speichern Sie sie
wieder mit CRLF.

## Sicherung zurückspielen

Beenden Sie das BMS und doppelklicken Sie im Programmordner auf `wiederherstellen_windows.bat`.
Das Werkzeug zeigt die vorhandenen Sicherungen, spielt die gewählte in die Datenbank ein und
sichert vorher Ihren aktuellen Stand. Nur die Datenbank wird ersetzt, Ihre Dokumente bleiben.
Den Ablauf beschreibt `BMS_Install_Windows.md`, Abschnitt „Ihre Daten“. Die Datei nutzt dieselbe
Python-Umgebung wie der Start und ist wie `update_windows.bat` ein Block in runden Klammern mit
Windows-Zeilenenden.

## KI-Läufe: Freigabeliste und Pfad-Wächter

Die KI-Läufe im Hintergrund dürfen nur Befehle ausführen, die `automation/agent_settings.json`
freigibt. Die Liste vergleicht den Anfang jedes Befehls Zeichen für Zeichen, ein Platzhalter gäbe
dort nichts frei. Sie nennt das Python der Umgebung in der Mac-Form
`~/.bewerbung_mgmt_venv/bin/python` und `$HOME/.bewerbung_mgmt_venv/bin/python`, eine eigene
Windows-Form (`Scripts\python.exe`) enthält sie nicht. Unter Windows führt Claude Code diese Befehle
in Git Bash aus, und die Verknüpfung `bin` → `Scripts` leitet sie an `python.exe` weiter.

Über dieselbe Datei läuft vor jedem Schreibzugriff eines Laufs der Pfad-Wächter
(`automation/pfad_waechter.py`). Er lässt Schreibzugriffe nur innerhalb des Programmordners und der
Temp-Ordner zu. Sein Befehl ruft Python ebenfalls als `$HOME/.bewerbung_mgmt_venv/bin/python` auf.
Startet dieser Befehl nicht, blockiert er nach den Regeln von Claude Code nichts. Der Wächter fällt
dann aus, statt Schreibzugriffe zu verhindern. Freigabeliste und Wächter sind unter Windows noch
nicht erprobt.

Ändern Sie `automation/agent_settings.json` nicht von Hand. Das nächste Update ersetzt die Datei
durch die ausgelieferte Fassung und legt Ihre Fassung vorher in der Update-Sicherung unter
`data/updates/…` ab.

## Bekannte Grenzen

- **Zeitgesteuerte Automatik:** Die Vorlage für einen täglichen Lauf zu fester Uhrzeit
  (`automation/com.bms.tageslauf.plist.template`) gibt es nur für den Mac (`launchd`). Eine
  Entsprechung für die Windows-Aufgabenplanung gibt es nicht. Den Tageslauf starten Sie per
  Schaltfläche.
- **Hilfsskripte im Ordner `scripts`:** Die `.sh`-Skripte laufen unter Windows nicht unverändert,
  auch nicht in Git Bash. `coach_deploy.sh`, `coach_passwort.sh`, `coach_site.sh`,
  `cover_letter_render.sh` und `refresh_views.sh` sind zsh-Skripte, und zsh gehört nicht zu Git für
  Windows. `backup_db.sh` braucht das Kommandozeilenwerkzeug `sqlite3`. Für den normalen Betrieb
  brauchen Sie keines dieser Skripte.
- **Drei Aufgaben ohne KI** rufen intern ein solches zsh-Skript auf: „Ansichten aktualisieren“
  (`views-refresh`: Excel-Export, Tages-Digest, Suchindex, Symbole der Berichte), „Anschreiben
  Word + PDF erzeugen“ (`cover-letter-render`, der Knopf im Anschreiben-Fenster) und „Coach-Site
  aktualisieren“ (`coach-site`). Unter Windows enden sie im Task-Center als fehlgeschlagen mit
  „Binary '/bin/zsh' nicht gefunden“, ohne dass sonst etwas abstürzt. „Ansichten aktualisieren“
  ist der vorletzte Schritt des Tageslaufs. Unter Windows endet der Tageslauf deshalb mit diesem
  fehlgeschlagenen Schritt, und der letzte Schritt (Coach-Site) wird abgebrochen. Die Ergebnisse
  der Schritte davor (Jobsuche, Sweeps, Beworben-Check, Postfach) bleiben erhalten. Excel-Export
  und Tages-Digest holen Sie unter Windows über die Knöpfe im
  Dashboard, den Suchindex über „↻ Index aktualisieren“ auf der Seite Suche. Anschreiben entstehen
  trotzdem als Word- und PDF-Datei, wenn Sie sie über „Anschreiben erstellen“ anlegen. Die
  Python-Module hinter den Aufgaben lassen sich auch in einer Eingabeaufforderung im Ordner
  `backend` aufrufen, etwa der Excel-Export:
  `"%USERPROFILE%\.bewerbung_mgmt_venv\Scripts\python.exe" -m pipeline.export_excel`
- **Datensicherung:** Die automatische tägliche Sicherung läuft unter Windows genauso wie auf dem
  Mac, sie ist reines Python im Server-Prozess. Nur das zusätzliche Hilfsskript
  `scripts/backup_db.sh` für eine manuelle Sicherung läuft ausschließlich auf dem Mac. Unter
  Windows sichern Sie von Hand über „Jetzt sichern“ in den Einstellungen.
- **KI-Läufe über das Task-Center** (`backend/app/agent_runner.py`): Start und Abbruch der
  Hintergrundprozesse sind für Windows umgestellt (`CREATE_NEW_PROCESS_GROUP`, `taskkill /T /F`),
  aber noch nicht erprobt. Beobachten Sie die ersten Läufe genau. Nach einem Neustart des Servers
  prüft das BMS auf dem Mac, ob ein noch als „läuft“ eingetragener Prozess wirklich der eigene ist
  (Kommandozeile und Startzeit über `ps`), bevor es ihn beendet. Windows hat kein `ps`. Lebt der
  Prozess eines solchen Laufs nach dem Neustart noch, beendet das BMS ihn deshalb nicht. Es markiert
  den Lauf im Task-Center als fehlgeschlagen („Identität NICHT bestätigt (Fremdprozess-Schutz),
  absichtlich NICHT beendet“) und schreibt eine Warnung ins Server-Fenster. Prüfen Sie den Prozess
  dann selbst im Task-Manager.
- **Codex finden (ChatGPT):** Hat das BMS die KI ChatGPT gewählt, startet das Task-Center die Codex CLI
  über die Umgebungsvariable `CODEX_BIN` oder sonst als `codex` aus dem PATH. Schreiben Sie in
  PowerShell `codex.cmd` statt `codex` (PowerShell blockiert sonst oft das Skript, wie bei `npm.cmd`).
- **Claude Code finden:** Das Task-Center startet Claude Code über die Umgebungsvariable
  `CLAUDE_BIN` oder sonst als `claude` aus dem PATH. Der Beirat sucht in dieser Reihenfolge:
  `CLAUDE_BIN`, dann der PATH (unter Windows auch `claude.cmd` und `claude.exe`), zuletzt
  `~/.local/bin/claude`. Liegt Claude Code nicht im PATH, setzen Sie in einer Eingabeaufforderung
  `set "CLAUDE_BIN=C:\Pfad\zu\claude.exe"` und starten das BMS aus demselben Fenster mit
  `start_windows.bat`.
- **PDF-Erzeugung bei Zeitüberschreitung:** Hängt eine Umwandlung länger als 180 Sekunden, beendet
  das BMS LibreOffice über `os.killpg`, und das gibt es unter Windows nicht. In diesem seltenen Fall
  bricht die Umwandlung unter Windows mit einem internen Fehler (`AttributeError`) ab statt mit der
  gewohnten Meldung. Normale Umwandlungen betrifft das nicht.
- **Datei-Rechte:** s. „Zugangsschlüssel und Secrets“ oben.
- **WLAN-Modus:** Für den Zugriff vom Handy oder Tablet gibt es auf dem Mac `start_lan.command`,
  unter Windows keine eigene Datei. Von Hand geht es, ebenfalls unerprobt, in einer
  Eingabeaufforderung im Ordner `backend`:
  `set "HOST=0.0.0.0" && set "PORT=8000" && "%USERPROFILE%\.bewerbung_mgmt_venv\Scripts\python.exe" run_server.py`
  Die Anführungszeichen bei `set` verhindern, dass das Leerzeichen vor `&&` im Wert landet. Beim
  ersten Start fragt womöglich die Windows-Firewall nach einer Freigabe. Andere Geräte öffnen das
  BMS unter der IP-Adresse des PCs (`ipconfig`, etwa `http://192.168.1.20:8000`) oder unter seinem
  Rechnernamen ohne Punkt. Andere Namen, etwa einen vom Router (`pc.fritz.box`), weist das BMS mit
  „Adresse nicht freigegeben“ ab. Freigeben lassen sie sich mit `set "BMS_HOSTS=pc.fritz.box"` in
  derselben Eingabeaufforderung vor dem Start, mehrere Namen mit Komma getrennt. Das BMS hat keinen
  Anmeldeschutz: Nutzen Sie den WLAN-Modus nur im eigenen, vertrauten Netz.
- **Automatische Tests:** Die Testsuite des BMS läuft bei jeder Änderung und vor jeder Freigabe auch
  auf einem Windows-System mit Python 3.12. Ein freigegebenes Programmpaket entsteht nur, wenn sie
  dort grün ist. Tests, die Mac-Eigenheiten prüfen (Unix-Dateirechte, Prozessgruppen, Symlinks,
  direkt ausführbare Skripte), überspringt sie dort. Die PDF-Umwandlung deckt sie unter Windows
  nicht ab, weil auf dem Testsystem kein LibreOffice installiert ist.

## Support-Matrix (Kurzfassung)

| Bereich | Windows | Anmerkung |
|---|---|---|
| Server starten, Oberfläche bedienen | Ja | `start_windows.bat` |
| Server beenden | Ja, unerprobt | `stop_windows.bat` (netstat und taskkill, Ablauf wie in der erprobten Mac-Fassung) |
| Stellen, Firmen, Dashboard, Excel-Export, Tages-Digest, Suchindex | Ja | läuft im Server-Prozess ohne Mac-Werkzeuge |
| Automatische Datensicherung | Ja | reines Python im Server-Prozess |
| PDF-Erzeugung (Lebenslauf, Anschreiben) | Ja, unerprobt | LibreOffice am Standardpfad oder im PATH; Zeitüberschreitung (über 180 s) s. oben |
| KI-Läufe über das Task-Center | Umgestellt, unerprobt | braucht Git Bash und die Verknüpfung `bin` → `Scripts` |
| KI-Läufe mit ChatGPT (Codex CLI) | Vorschau, unter Windows nicht erprobt | `npm.cmd install -g @openai/codex`, `codex.cmd login`; OpenAI empfiehlt Windows 11, die bevorzugte Sandbox braucht einmalig Administrator-Rechte |
| Beirat | Ja, unerprobt | Claude Code über `CLAUDE_BIN` oder den PATH |
| Verwaiste Prozesse nach einem Neustart erkennen und beenden | Eingeschränkt | kein `ps`: nichts wird automatisch beendet |
| Aufgaben „Ansichten aktualisieren“, „Anschreiben Word + PDF erzeugen“, „Coach-Site aktualisieren“ | Nein | „Binary '/bin/zsh' nicht gefunden“, Ersatz s. oben |
| Zeitgesteuerte Automatik | Nein | Vorlage nur für den Mac (`launchd`) |
| Hilfsskripte `scripts/*.sh` | Nein | zsh bzw. `sqlite3` nötig |

## Weiterführend

- **`BMS_Install_Windows.md`**: die geführte Installation unter Windows, dann Einrichten,
  Aktualisierungen einspielen, „Wenn etwas nicht klappt“ und die Windows-Grenzen in Kurzform
  („Was unter Windows eingeschränkt ist“).
- **`docs/ANLEITUNG.md`**: die tägliche Arbeit mit dem BMS.
- Im BMS öffnet „📖 Dokumentation“ in der Seitenleiste alle Anleitungen in Reitern.
