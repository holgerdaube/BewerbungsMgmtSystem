# BMS: Installation und Einrichtung unter Windows

Diese Anleitung bringt das Bewerbungs-Management-System (BMS) auf Ihren Windows-PC. Sie installieren
zuerst einige kostenlose Programme, dann das BMS selbst, und richten es anschließend auf Ihre
Person ein: Profil, Lebenslauf, Zielrollen und Suchregion. Für die Technik brauchen Sie etwa
45 Minuten, für die Einrichtung ein bis zwei Stunden. Ein Tipp vorab: Fordern Sie den
LinkedIn-Datenexport (Abschnitt „Werdegang und Fähigkeiten von LinkedIn übernehmen“ unter
„Einrichten: Das BMS lernt Sie kennen“) am besten schon heute an. LinkedIn braucht bis zu 24 Stunden,
bis das Archiv bereitsteht.

Programmierkenntnisse brauchen Sie nicht. An einigen Stellen fügen Sie Befehle in PowerShell ein.
Der Assistent im Chat gibt Ihnen jeden Befehl zum Kopieren vor und sagt dazu, was er tut.

So ist die Datei aufgebaut: Die „Anweisung an die KI“ führt Sie durch die Installation (Schritt 0 bis
Schritt 10). Ab „Nach der Installation“ steht alles für den Alltag: Einrichten, Prüfen,
Aktualisieren, Hilfe bei Problemen und Ihre Daten. Haben Sie einen Mac, nutzen Sie die Anleitung
`BMS_Install_MAC.md`.

## So starten Sie

1. Öffnen Sie **Claude Desktop** oder **ChatGPT** (App oder chatgpt.com) und starten Sie einen neuen
   Chat, in Claude Desktop auch eine neue Code-Sitzung. Welche KI Sie hier zum Installieren nutzen und
   welche das BMS später für seine KI-Funktionen verwendet, sind zwei getrennte Entscheidungen.
2. Hängen Sie diese Datei (`BMS_Install_Windows.md`) an die Nachricht an.
3. Schreiben Sie dazu: **„Führe mich mit dieser Anleitung durch die Installation des BMS.“**
4. Halten Sie bereit: Ihr Konto bei der KI, die das BMS für seine KI-Funktionen nutzen soll: Claude (Pro
   oder Max) oder ChatGPT (Plus oder Pro). Das BMS selbst ist kostenlos und braucht keine Lizenz. Die
   Anleitung lädt das Programmpaket selbst von GitHub. Eine BMS-ZIP-Datei (`BMS_<Version>.zip`) brauchen
   Sie nur als Ersatzweg, wenn das Laden nicht klappt.
5. Überlegen Sie, in welchem Ordner das BMS liegen soll. Der Assistent fragt Sie gleich zu Beginn danach
   und schlägt den Ordner `BMS` in Ihrem Benutzerordner vor (`%USERPROFILE%\BMS`, in der Regel
   `C:\Users\<Ihr Benutzername>\BMS`). Im Rest dieser Anleitung heißt dieser Ordner „Ihr BMS-Ordner“.
   Zwei Regeln für die Wahl:
   - **Kein synchronisierter Ordner.** Das BMS speichert Ihre Daten in einer einzigen
     Datenbankdatei, die während der Arbeit ständig beschrieben wird. Cloud-Speicher wie iCloud
     Drive, OneDrive oder Dropbox synchronisieren solche Dateien nicht zuverlässig und können sie
     beschädigen. Also nicht auf dem Desktop und nicht in „Dokumente“, wenn diese von OneDrive
     gesichert werden.
   - **Ein neuer oder leerer Ordner.** Liegt dort schon ein BMS, installieren Sie nicht darüber,
     sondern aktualisieren es (Abschnitt „Aktualisierungen einspielen“).

   Ihr Benutzerordner gehört Ihrem Konto. Andere Benutzerkonten des Rechners ohne
   Administrator-Rechte können Ihre Daten dort nicht lesen, und das Anlegen des Ordners braucht
   keine Administrator-Rechte. In einem Ordner außerhalb davon (etwa `D:\BMS`) können andere
   Benutzerkonten in der Regel mitlesen.

Diese Anleitung geht von einem PC aus, auf dem unter Ihrem Benutzerkonto noch kein BMS installiert
ist. Der Assistent prüft das in Schritt 1. Gibt es schon eins, aktualisieren Sie es (Abschnitt
„Aktualisierungen einspielen“), oder Sie installieren bewusst ein zweites daneben. Die Hinweise
dazu gibt er in Schritt 1.

Der Assistent führt Sie nun Schritt für Schritt. Zu jedem Schritt bekommen Sie genau die Befehle, die
Sie in **PowerShell** einfügen (Start, „PowerShell“ tippen, „Windows PowerShell“ öffnen, Befehl
einfügen, Eingabetaste). Danach fragt er, ob der Befehl durchgelaufen ist, und prüft das
Ergebnis mit Ihnen. Es geht erst weiter, wenn ein Schritt sauber war. Planen Sie etwa 45 Minuten
ein.

Wer ohne Assistenten installiert, führt die Befehle der Schritte 1 bis 9 selbst aus und setzt die
Platzhalter (`INSTALLVERZ` für Ihren BMS-Ordner, `ZIP-PFAD` für den Pfad der ZIP-Datei, `VERSION` für
die Versionsnummer) von Hand ein.

## Was Sie brauchen

| | Windows |
|---|---|
| Rechner | Windows 10 oder 11 |
| Rechte | ein Konto mit Administrator-Rechten |
| Speicherplatz | etwa 2 GB frei |
| Internet | zum Laden des Programmpakets von GitHub, für die Installation und für die KI-Funktionen |

Das Laden des Programmpakets nutzt PowerShell und `curl.exe`. Beides ist ab Windows 10, Version
1803, vorhanden. Auf älteren Systemen nehmen Sie den Weg über die ZIP-Datei.

Dazu kommen:

- Das BMS selbst ist kostenlos. Es steht als Open Source unter der Apache-Lizenz 2.0, Sie kaufen nichts
  und schalten nichts frei. Die Anleitung lädt das Programmpaket von GitHub, dafür brauchen Sie kein
  Konto.
- Ein Abo bei einer der zwei KI, wenn Sie die KI-Funktionen nutzen wollen: **Claude** (Pro oder Max,
  Anthropic) oder **ChatGPT** (Plus oder Pro, OpenAI). Die KI-Funktionen des BMS, also Recherche,
  Firmenprüfung, Lebenslauf-Anpassung und Anschreiben, laufen bei Claude über das Programm Claude Code,
  bei ChatGPT über das Programm Codex CLI, jeweils über Ihr eigenes Konto. Die Kosten dafür zahlen Sie
  direkt an den Anbieter. Ohne Abo können Sie Stellen erfassen, verwalten und auswerten, die
  KI-Funktionen aber nicht nutzen.
- Zur Wahl der KI: Claude ist der Standard und der am besten erprobte Weg. Bei ChatGPT gehen die
  Inhalte der KI-Läufe an OpenAI statt an Anthropic. ChatGPT ist im BMS eine Vorschau: Die Läufe ohne Mail sind auf dem Mac erprobt, die Mail-Läufe und der Tageslauf noch nicht, und unter Windows noch gar nichts. Es gibt keine Budgetgrenze je Lauf, es gelten
  die Grenzen Ihres Abos, und viele Läufe hintereinander können ein Plus-Konto an die Grenze bringen. Für
  ChatGPT empfiehlt OpenAI Windows 11 (Windows 10 ab Version 1809 geht), und die bevorzugte Sandbox
  braucht einmalig ein Administrator-Setup. Der Assistent fragt Sie in Schritt 0 nach der KI. Später
  wechseln Sie sie in den „Einstellungen“, Karte „KI“.
- Optional ein E-Mail-Konto mit IMAP-Zugang, damit das BMS Antworten auf Ihre Bewerbungen im
  Postfach erkennt.
- Optional ein LinkedIn-Konto, um Werdegang und Fähigkeiten per Datenexport zu übernehmen.
- Nur als Ersatzweg: eine BMS-ZIP-Datei (`BMS_<Version>.zip`), falls das Laden nicht klappt, etwa
  weil ein Firmennetz den Zugriff auf GitHub verhindert. Sie laden sie im Browser von der Seite
  https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/latest.

# Anweisung an die KI: geführte Installation

Ab hier steht die Anweisung an die KI im Chat, die durch die Installation führt (Claude, ChatGPT oder
ein anderer Assistent). Sie ist nicht für den Anwender gedacht. Für ihn geht es unter „Nach der
Installation“ weiter.

Du führst einen Anwender durch die Installation des Bewerbungs-Management-Systems (BMS) auf seinem
Windows-PC. Du arbeitest als Anleiter: **Der Anwender führt alle Befehle selbst in PowerShell aus,
du gibst sie vor und prüfst die Ergebnisse.** Das gilt auch dann, wenn du in dieser Sitzung selbst
Befehle ausführen könntest.

Welche KI das BMS später für seine KI-Funktionen nutzt, Claude oder ChatGPT, ist davon unabhängig.
Du fragst sie in Schritt 0 ab. Wo diese Anleitung „die KI-Wahl“ sagt, meint sie diese Antwort.

## Gesprächsregeln

1. **Ein Schritt nach dem anderen.** Gib pro Nachricht genau einen Schritt (oder einen Teilschritt)
   mit den zugehörigen Befehlen vor. Springe nicht voraus, auch wenn der Anwender es eilig hat.
2. **Befehle in eigenen Codeblöcken** (` ```powershell `), vollständig, zum Kopieren und
   Einfügen, mit allen Pfaden bereits eingesetzt. Verwende nie Platzhalter wie `<Verzeichnis>`
   in dem, was der Anwender kopiert. Setze die Angaben aus Schritt 0 selbst ein. Nennt der Anwender
   einen Pfad in Anführungszeichen (so liefert ihn „Als Pfad kopieren“), setze ihn ohne diese
   Anführungszeichen ein, denn die Vorlagen setzen eigene. Die Befehle in dieser Anleitung tragen
   Platzhalter in Großbuchstaben, die du vor der Ausgabe ersetzt: `INSTALLVERZ` (das
   Installationsverzeichnis), `ZIP-PFAD`, `VERSION` (aus der Auskunft in Schritt 4), `LAUFWERK` und
   `UNTERORDNER`. Mehrere Zeilen in einem Block sind in Ordnung, wenn sie zusammengehören.
3. **Nach jedem Befehlsblock fragen**, in dieser Form: „Ist der Befehl durchgelaufen? Bitte kopieren
   Sie die Ausgabe hier herein.“ Sage dazu, woran der Anwender Erfolg erkennt, damit er nicht raten
   muss („Es soll `Python 3.12.x` erscheinen.“).
4. **Ergebnis prüfen.** Vergleiche die eingefügte Ausgabe mit der Erwartung des Schritts. Bestätige
   knapp („Das passt.“) und gehe erst dann zum nächsten Schritt. Weicht die Ausgabe ab oder
   erscheint eine Fehlermeldung, sage in einem Satz, was los ist, und gib genau einen Korrekturbefehl
   vor. Hilft das nach zwei Versuchen nicht, halte an, erkläre den Stand ehrlich und gehe zu
   Schritt 10 (Protokoll und Abbruch). Rate nicht und behaupte keinen Erfolg, der nicht belegt ist.
5. **Sprache:** Deutsch, kurze Sätze, kein Fachjargon, höfliche Anrede mit „Sie“.
6. **Geheimnisse:** Der Zugangsschlüssel (Token) darf nie im Chat erscheinen. Bitte den Anwender
   ausdrücklich, ihn nicht einzufügen. Bei ChatGPT gibt es keinen Schlüssel zum Einfügen, die Anmeldung
   läuft nur im Browser. Wenn eine Ausgabe ihn enthalten könnte, gib einen Befehl vor, der
   nur „vorhanden“ oder „fehlt“ ausgibt. Die Antwort von GitHub (die Auskunft in 4a, Schritt 4) enthält
   keine Geheimnisse und darf in den Chat.
7. **Nichts Zerstörerisches.** Lösche nichts, überschreibe nichts ohne ausdrückliche Zustimmung. Ein
   vorhandenes, nicht leeres Installationsverzeichnis wird nie überschrieben (Schritt 2), ein
   vorhandener Zugangsschlüssel ebenfalls nicht (Schritt 7).
8. **Administrator-Rechte:** Winget kann ein Fenster „Änderungen zulassen?“ öffnen. Kündige das vor
   dem Befehl an. Bei ChatGPT kann Windows in Schritt 7 noch einmal fragen (Sandbox von Codex).
9. **Fortschritt zeigen.** Beginne jede Antwort mit einer Zeile wie „Schritt 4 von 10: BMS laden
   und entpacken“.
10. **Protokoll mitführen.** Führe intern für jeden Schritt Befehl, Ergebnis (OK/FEHLER/ÜBERSPRUNGEN)
    und bei Fehlern die vollständige Meldung. Das Protokoll wird in Schritt 2 angelegt und in Schritt 10
    geschrieben (Details dort).

## Schritt 0: Angaben abfragen

Begrüße den Anwender kurz und frage die folgenden Dinge **in einer einzigen Nachricht** ab. Warte auf
die Antworten.

1. **Installationsverzeichnis.** „In welchem Verzeichnis soll das BMS installiert werden? Vorschlag:
   der Ordner `BMS` in Ihrem Benutzerordner, in der Regel `C:\Users\<Ihr Benutzername>\BMS`.“ Prüfe
   die Antwort:
   - Es muss ein vollständiger Laufwerkspfad sein (z. B. `D:\BMS`).
   - Liegt der Pfad außerhalb des Benutzerordners, sage in einem Satz, dass andere Benutzerkonten
     des Rechners dort in der Regel mitlesen können, und nenne den Vorschlag. Bleibt der Anwender
     dabei, gilt sein Pfad.
   - **Nicht** in einem Ordner, den OneDrive, iCloud oder Dropbox synchronisiert, und nicht auf dem
     Desktop oder in „Dokumente“ (oft von OneDrive gesichert). Grund: Die Datenbank wird laufend
     beschrieben und kann beim Synchronisieren beschädigt werden. Erkläre das in einem Satz und
     nenne den Vorschlag.
   - Der Pfad darf Leerzeichen enthalten. Setze ihn in allen Befehlen in Anführungszeichen, wie in
     den Vorlagen unten.
   Diesen Pfad nennen wir im Folgenden **das Installationsverzeichnis**. Setze ihn in alle späteren
   Befehle ein. Nennt der Anwender keinen Pfad oder schreibt nur „ja“ oder „Vorschlag“, gilt der
   Vorschlag. Den tatsächlichen Pfad des Benutzerordners klärt Schritt 1.
2. **Vorhandene ZIP-Datei (optional).** „Haben Sie schon eine BMS-ZIP-Datei (`BMS_<Version>.zip`), zum
   Beispiel aus dem Browser heruntergeladen? Dann nennen Sie mir bitte den vollständigen Pfad (meist
   `C:\Users\Name\Downloads\BMS_2.0.0.zip`). Sonst holen wir das Programmpaket in Schritt 4 gemeinsam
   von GitHub, dafür müssen Sie nichts bereithalten.“ Nennt der Anwender eine ZIP-Datei, entfällt in
   Schritt 4 das Laden (4a bis 4c), und es geht mit dem Entpacken (4d) weiter. Nennt er keine, gilt das
   Laden von GitHub.
3. **KI-Funktionen:** „Möchten Sie die KI-Funktionen einrichten (Recherche, Firmenprüfung,
   Lebenslauf, Anschreiben)? Dafür brauchen Sie ein Abo bei einer KI und etwa 10 Minuten mehr.“
   (Ja/Nein, später nachholbar.) Bei „Nein“ entfällt Punkt 4.
4. **Welche KI** (nur bei „Ja“ zu Punkt 3): „Welche KI soll die KI-Funktionen ausführen: **Claude**
   (Anthropic, Abo Pro oder Max) oder **ChatGPT** (OpenAI, Abo Plus oder Pro)?“ Sage dazu in wenigen
   Sätzen: Claude ist der Standard und der am besten erprobte Weg. Bei ChatGPT gehen die Inhalte der
   KI-Läufe an OpenAI statt an Anthropic. ChatGPT ist im BMS eine Vorschau: Die Läufe ohne Mail sind auf dem Mac erprobt, die Mail-Läufe und der Tageslauf noch nicht, und unter Windows noch gar nichts. Es gibt keine Budgetgrenze je Lauf, es gelten die Grenzen
   des Abos, und viele Läufe hintereinander können ein Plus-Konto an die Grenze bringen. Fragt der Anwender
   nach Gemini: Das BMS bietet es bewusst nicht an, weil Googles Regeln das Abo in Apps nicht zulassen.
   Nennt der Anwender keine Wahl, gilt Claude. Diese Antwort heißt im Folgenden **die KI-Wahl**. Sie
   bestimmt Schritt 3, 7 und 8 und die Prüfung in Schritt 9. Später lässt sie sich in den
   „Einstellungen“, Karte „KI“, wechseln. Dann müssen das Programm der anderen KI installiert und ihre
   Anmeldung erledigt sein (Schritt 3 und 7 für diese KI).

Wiederhole danach das gewählte Installationsverzeichnis und die KI-Wahl in einem Satz („Das BMS wird
nach … installiert, mit Claude als KI.“, entsprechend mit ChatGPT oder „ohne KI-Funktionen“) und lass
es dir bestätigen, bevor du mit Schritt 1 beginnst. Danach wird der Ordner nicht mehr gewechselt.

Das **Protokoll** liegt im Installationsverzeichnis als `Installprotokoll.md`. Sage das dem Anwender.

## Schritt 1: Voraussetzungen prüfen

Befehl (der Anwender öffnet PowerShell und fügt ein; ersetze `LAUFWERK` durch den Laufwerksbuchstaben
des Installationsverzeichnisses, z. B. `C`):

```powershell
winget --version
(Get-CimInstance Win32_OperatingSystem).Caption; [Environment]::OSVersion.Version.Build; $env:PROCESSOR_ARCHITECTURE
$env:USERPROFILE
(Get-PSDrive LAUFWERK).Free / 1GB
Test-Path "$env:USERPROFILE\.bewerbung_mgmt_venv", "$env:USERPROFILE\.bewerbung_mgmt_secrets"
curl.exe --version
```

Erwartung: eine winget-Version; drei Zeilen zum System: „Microsoft Windows 10 …“ oder „Microsoft
Windows 11 …“, eine Build-Nummer von mindestens 17763 und `AMD64` oder `ARM64`; der Pfad des
Benutzerordners (etwa `C:\Users\Name`; gilt der Vorschlag aus Schritt 0, ist das
Installationsverzeichnis dieser Pfad plus `\BMS`); freier Platz **mindestens 2** (GB); zweimal `False`
für die beiden Ordner im Benutzerverzeichnis; zum Schluss einige Zeilen, die mit `curl` und einer
Versionsnummer beginnen. Fehlt `winget`: Der Anwender soll im Microsoft Store den „App-Installer“
aktualisieren und es noch einmal versuchen. Meldet PowerShell bei `curl.exe --version`, den Befehl gebe
es nicht, ist Windows zu alt (vor Windows 10, Version 1803): Dann geht nur der Ersatzweg mit einer
ZIP-Datei. Ist die Build-Nummer kleiner als 17763 und soll die KI eingerichtet werden (Schritt 0),
halte an und verweise auf ein Windows-Update (Claude Code und die Codex CLI brauchen Windows 10 ab
Version 1809). Bei ChatGPT empfiehlt OpenAI Windows 11: Steht dort „Windows 10“, sage das dem Anwender,
vermerke es im Protokoll und mache weiter. Steht dort `ARM64`, mache weiter und vermerke im Protokoll,
dass diese Bauart nicht getestet ist.

Hat der Anwender in Schritt 0 eine ZIP-Datei genannt (Ersatzweg), prüfst du statt `curl` diese Datei:
Ersetze im Block die Zeile `curl.exe --version` durch `Test-Path "ZIP-PFAD"` (der genannte Pfad).
Erwartung an dieser Stelle: `True`. `False` bei der ZIP-Datei: Pfad klären.

**Steht bei einem der beiden letzten Ordner `True`, gibt es unter diesem Benutzerkonto schon ein BMS.**
Halte an und kläre mit dem Anwender:

- Will er das vorhandene BMS aktualisieren, ist `update_windows.bat` in dessen Verzeichnis der
  richtige Weg (Abschnitt „Aktualisierungen einspielen“), nicht diese Anleitung.
- Will er bewusst ein zweites BMS daneben installieren, erkläre: Beide teilen sich die
  Python-Umgebung (`.bewerbung_mgmt_venv`) und die Zugangsdaten (`.bewerbung_mgmt_secrets` mit
  Zugangsschlüssel und Mail-Zugang), jede Installation hat aber eigene Daten. Beide sollten
  dieselbe Programmversion haben, weil Schritt 5 die Bausteine für beide ersetzt. Schritt 7
  überschreibt den vorhandenen Zugangsschlüssel nicht. Es kann immer nur ein BMS gleichzeitig laufen.
  Fahre erst fort, wenn der Anwender das ausdrücklich bestätigt.

Nur im Ersatzweg: Optional, wenn neben der ZIP-Datei eine Datei `…zip.sha256` liegt, gib den
Prüfbefehl `(Get-FileHash -Algorithm SHA256 "ZIP-PFAD").Hash` vor (derselbe wie unter 4c in Schritt 4)
und vergleiche die Ausgabe mit dem Inhalt der `.sha256`-Datei (`Get-Content "ZIP-PFAD.sha256"`).
Stimmen die Werte nicht überein (Groß-/Kleinschreibung egal), ist die ZIP-Datei beschädigt:
neu herunterladen lassen.

## Schritt 2: Installationsverzeichnis anlegen und Protokoll beginnen

Prüft zugleich, dass das Verzeichnis nicht schon belegt ist:

```powershell
if (Test-Path "INSTALLVERZ") { Get-ChildItem "INSTALLVERZ" -Force | Measure-Object | Select-Object -ExpandProperty Count } else { "neu" }
```

- Ausgabe `neu` oder `0`: weiter.
- Zahl größer 0: Das Verzeichnis ist nicht leer. **Nicht überschreiben.** Frage, ob es ein vorhandenes
  BMS ist (dann ist `update_windows.bat` im Verzeichnis der richtige Weg, Abschnitt
  „Aktualisierungen einspielen“, nicht diese Anleitung) oder ein anderes Verzeichnis gewählt werden
  soll.

Dann anlegen und prüfen, dass das Benutzerkonto darin schreiben darf. Das braucht keine
Administrator-Rechte:

```powershell
New-Item -ItemType Directory -Force "INSTALLVERZ" | Out-Null
try { [IO.File]::WriteAllText("INSTALLVERZ\schreibtest.txt", "ok"); Remove-Item "INSTALLVERZ\schreibtest.txt"; "Schreibrecht: ja" } catch { "Schreibrecht: NEIN" }
```

Erwartung: `Schreibrecht: ja`. Bei einer Fehlermeldung oder `Schreibrecht: NEIN` ist das gewählte
Verzeichnis geschützt (etwa unter `C:\Program Files`). Schlage den Ordner `BMS` im Benutzerordner vor
(Pfad aus Schritt 1 plus `\BMS`), lass ihn bestätigen und beginne Schritt 2 mit dem neuen Pfad von
vorn.

Dann das Protokoll beginnen:

```powershell
"# BMS-Installprotokoll`nBeginn: $(Get-Date -Format 'dd.MM.yyyy HH:mm')`nVerzeichnis: INSTALLVERZ`n" | Set-Content -Encoding UTF8 "INSTALLVERZ\Installprotokoll.md"
Get-Content "INSTALLVERZ\Installprotokoll.md"
```

Erwartung: Die Ausgabe zeigt die drei Kopfzeilen.

## Schritt 3: Programme installieren

Prüfe zuerst, was schon vorhanden ist, damit nichts doppelt installiert wird:

```powershell
"node:   " + [bool](Get-Command node -ErrorAction SilentlyContinue)
"git:    " + [bool](Get-Command git -ErrorAction SilentlyContinue)
"claude: " + [bool](Get-Command claude -ErrorAction SilentlyContinue)
"codex:  " + [bool](Get-Command codex -ErrorAction SilentlyContinue)
"office: " + (Test-Path "$env:ProgramFiles\LibreOffice\program\soffice.exe")
```

Gib danach **nur die Zeilen für Programme vor, bei denen `False` steht**, und immer die Zeile für
Python. Ein Programm, das der Anwender schon auf anderem Weg installiert hat, bekommt so keine
zweite Kopie. Ist Node.js schon da, lass dir mit `node --version` die Version nennen: Sie sollte 18
oder neuer sein, sonst die Node-Zeile doch vorgeben.

Kündige an: „Windows fragt eventuell nach Administrator-Rechten, bitte mit ‚Ja‘ bestätigen. Das
dauert einige Minuten.“ Bei „Nein“ in Schritt 0, Punkt 3, und bei ChatGPT lässt du die letzte Zeile (Claude Code) weg.

```powershell
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
winget install -e --id Git.Git --accept-package-agreements --accept-source-agreements
winget install -e --id TheDocumentFoundation.LibreOffice --accept-package-agreements --accept-source-agreements
winget install -e --id Anthropic.ClaudeCode --accept-package-agreements --accept-source-agreements
```

Meldet winget bei einem Programm „bereits installiert“ oder „keine neuere Version“, ist das in
Ordnung. Der Anwender soll danach **PowerShell schließen und neu öffnen**, damit Windows die neuen
Programme findet. Dann prüfen:

```powershell
py -3.12 --version
node --version
git --version
Test-Path "C:\Program Files\LibreOffice\program\soffice.exe"
```

Zusätzlich bei Claude:

```powershell
claude --version
```

Zusätzlich bei ChatGPT installierst du die Codex CLI in derselben neuen PowerShell (Node.js ist jetzt
da) und prüfst sie. Stand bei `codex` oben schon `True`, lässt du die erste Zeile weg. Der Anwender
schreibt `npm.cmd` und `codex.cmd`, nie nur `npm` oder `codex` (PowerShell blockiert sonst oft das
Skript, wie bei `npm.cmd` in Schritt 6):

```powershell
npm.cmd install -g @openai/codex
codex.cmd --version
```

Erwartung: `Python 3.12.x`, eine Node-Version, eine Git-Version, `True` (LibreOffice am
Standardort), bei Claude eine Claude-Version, bei ChatGPT eine Codex-Version (getestet wurde 0.166.0).
Hinweise:
- `py` nicht gefunden: PowerShell wirklich schließen und neu öffnen. Hilft das nicht, den Rechner
  neu starten.
- `LibreOffice: False`: Es liegt womöglich unter `C:\Program Files (x86)\LibreOffice\program\`. Prüfe
  das mit `Test-Path` und akzeptiere es, sonst muss LibreOffice am Standardort neu installiert
  werden, sonst entstehen später keine PDF-Dateien.
- Git ist beim BMS Pflicht, weil die KI-Funktionen von Claude Code unter Windows Befehle nur über die
  mit Git installierte „Git Bash“ ausführen können. Auch bei ChatGPT bleibt Git Teil der Installation.

## Schritt 4: BMS laden und entpacken

Hat der Anwender in Schritt 0 keine ZIP-Datei genannt, holt er das Programmpaket von GitHub, wo das BMS
veröffentlicht wird (4a bis 4c). Dafür braucht er weder ein Konto noch eine Anmeldung. Kündige das
vorher an: „Dabei fragt Ihr PC bei GitHub nach der neuesten Version und lädt das Paket. GitHub erhält
dabei die IP-Adresse Ihres PCs, sonst nichts, und nur auf diese Befehle hin.“ Weise den Anwender
außerdem darauf hin, dass `curl.exe` mit `.exe` geschrieben wird, sonst nimmt PowerShell einen anderen
Befehl.

Hat er stattdessen eine **ZIP-Datei** genannt (Ersatzweg), entfallen 4a bis 4c, und es geht mit 4d
weiter. `ZIP-PFAD` ist dann der genannte Pfad.

Hat der Anwender keine ZIP-Datei genannt, ist `ZIP-PFAD` in 4b bis 4d der Ordner „Downloads“ des
Anwenders plus `\BMS_VERSION.zip`, mit der Version aus 4a. Den Kontonamen kennst du nicht, und OneDrive
kann „Downloads“ umleiten. Erfinde den Pfad deshalb nicht, sondern gib vor 4b diesen Befehl vor, der den
echten Ordner ausgibt:

```powershell
(New-Object -ComObject Shell.Application).NameSpace('shell:Downloads').Self.Path
```

Erwartung: eine Zeile mit einem Ordnerpfad. Daraus setzt du `ZIP-PFAD` zusammen. Lautet die Ausgabe zum
Beispiel `D:\Downloads`, ist `ZIP-PFAD` gleich `D:\Downloads\BMS_VERSION.zip`, mit eingesetzter
Version. Bleibt die Ausgabe leer oder meldet der Befehl einen Fehler, frage nach dem Ordner.

4a. Auskunft holen:

```powershell
curl.exe -sS -H "Accept: application/vnd.github+json" "https://api.github.com/repos/holgerdaube/BewerbungsMgmtSystem/releases/latest"
```

Erwartung: ein längerer Text über viele Zeilen, der mit `{` beginnt und unter anderem `"tag_name"` und
eine Liste `"assets"` enthält. Der Anwender fügt ihn vollständig ein. Daraus nimmst du zwei Werte:

- `VERSION`: der Wert von `tag_name` ohne das `v` am Anfang (aus `"tag_name": "v2.0.0"` wird `2.0.0`);
- die erwartete Prüfsumme: beim Eintrag in `assets`, dessen `name` genau `BMS_VERSION.zip` lautet, der
  Wert von `digest` ohne das Präfix `sha256:`. (Daneben gibt es einen Eintrag `BMS_VERSION.zip.sha256`.
  Den nimmst du nicht.)

Merke dir beide Werte und setze `VERSION` in die folgenden Befehle ein. Die Ausgabe enthält keine
Geheimnisse und darf im Chat stehen. Fehlt der Eintrag `BMS_VERSION.zip` oder sein `digest`, installiere
nichts, was du nicht prüfen kannst: Nimm den Ersatzweg (siehe Fehlerfall) und prüfe die ZIP-Datei in
Schritt 1 gegen die Datei `BMS_VERSION.zip.sha256` von der Release-Seite.

4b. Paket laden (`VERSION` aus 4a). Liegt unter `ZIP-PFAD` schon eine Datei (prüfen mit
`Test-Path "ZIP-PFAD"`), frage vorher, ob sie ersetzt werden darf (Gesprächsregel 7):

```powershell
curl.exe -fsSL -o "ZIP-PFAD" -w "Antwort: %{http_code}`n" "https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/download/vVERSION/BMS_VERSION.zip"
```

Erwartung: `Antwort: 200`. GitHub leitet beim Laden auf seinen Download-Server um. Der Befehl folgt dieser
Weiterleitung selbst, das ist normal.

4c. Prüfsumme bilden:

```powershell
(Get-FileHash -Algorithm SHA256 "ZIP-PFAD").Hash
```

Vergleiche die Ausgabe mit dem `digest`-Wert aus 4a, Groß- und Kleinschreibung egal. Weicht sie ab,
lass das Paket einmal neu laden (4b). Weicht sie wieder ab, gehe vor wie im Fehlerfall: Datei löschen
lassen und den Ersatzweg anbieten.

**Fehlerfall.** Steht in 4a statt der Auskunft eine Meldung von curl oder ein kurzer Text mit
`"message"` (etwa `Not Found` oder `API rate limit exceeded`), ist das der Grund. Eine Datei gibt es
dann noch nicht: Lass den Befehl einmal wiederholen. Zeigt 4b nicht `Antwort: 200`, sondern eine andere
Zahl (etwa `Antwort: 404`) oder eine Meldung von curl, ist das der Grund. Auch dann, und ebenso bei
abweichender Prüfsumme, soll keine unbrauchbare Datei liegen bleiben. Lass sie mit
`Remove-Item -ErrorAction SilentlyContinue "ZIP-PFAD"`
löschen. Der Befehl meldet nichts, wenn die Datei gar nicht da ist. Erkläre den Grund in einem Satz und
lass das Paket einmal neu laden (4b). Klappt es wieder nicht, biete den Ersatzweg an: Der Anwender
öffnet im Browser `https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/latest`, lädt dort unter
„Assets“ die Datei `BMS_VERSION.zip` und speichert sie im Ordner „Downloads“. Du wiederholst Schritt 1
für diese Datei und gehst mit 4d weiter. Kommt der Anwender auch so nicht an die Datei, halte an und
schreibe das Protokoll (Schritt 10). Was die Antworten bedeuten, steht im Abschnitt „Wenn etwas nicht
klappt“.

4d. Entpacken:

```powershell
Unblock-File "ZIP-PFAD"
Expand-Archive -Path "ZIP-PFAD" -DestinationPath "INSTALLVERZ" -Force
Get-ChildItem "INSTALLVERZ" | Select-Object -ExpandProperty Name
```

`Unblock-File` entfernt die Download-Markierung, damit Windows die Startdatei später nicht als
unbekannten Download blockiert.

Erwartung: Die Liste enthält u. a. `start_windows.bat`, `backend`, `frontend`, `config`, `docs`.

Steht stattdessen nur ein einzelner Ordner (z. B. `BMS_1.6.1`) in der Liste, liegt der Inhalt eine
Ebene zu tief. Gib dann vor, den Inhalt nach oben zu verschieben (ersetze `UNTERORDNER`):

```powershell
Move-Item "INSTALLVERZ\UNTERORDNER\*" "INSTALLVERZ" -Force
Remove-Item "INSTALLVERZ\UNTERORDNER"
Get-ChildItem "INSTALLVERZ" | Select-Object -ExpandProperty Name
```

Abschlussprüfung:

```powershell
Test-Path "INSTALLVERZ\start_windows.bat"
Test-Path "INSTALLVERZ\backend\requirements-lock.txt"
Test-Path "INSTALLVERZ\frontend\package.json"
```

Erwartung: dreimal `True`.

## Schritt 5: Python-Umgebung einrichten

Kündige an: „Das dauert einige Minuten und gibt viel Text aus.“

```powershell
py -3.12 -m venv "$env:USERPROFILE\.bewerbung_mgmt_venv"
& "$env:USERPROFILE\.bewerbung_mgmt_venv\Scripts\python.exe" -m pip install --upgrade pip
& "$env:USERPROFILE\.bewerbung_mgmt_venv\Scripts\pip.exe" install -r "INSTALLVERZ\backend\requirements-lock.txt"
New-Item -ItemType Junction -Path "$env:USERPROFILE\.bewerbung_mgmt_venv\bin" -Target "$env:USERPROFILE\.bewerbung_mgmt_venv\Scripts"
```

Meldet `New-Item`, dass bereits ein Element mit diesem Namen vorhanden ist (englisch: „An item with
the specified name … already exists“), ist das harmlos: Die Umgebung gab es schon. Prüfe in jedem Fall
mit:

```powershell
Test-Path "$env:USERPROFILE\.bewerbung_mgmt_venv\bin\python.exe"
& "$env:USERPROFILE\.bewerbung_mgmt_venv\Scripts\python.exe" -c "import fastapi, uvicorn; print('Bausteine ok')"
```

Erwartung: `True` und `Bausteine ok`. Die Verknüpfung `bin` → `Scripts` ist zwingend, ohne sie
scheitern später die KI-Läufe. Bei einem Fehler in `pip install`: Lass dir die letzten Zeilen
der Ausgabe geben und prüfe, ob wirklich Python 3.12 verwendet wurde.

## Schritt 6: Oberfläche bauen

Der Anwender schreibt `npm.cmd`, nie nur `npm` (PowerShell blockiert sonst oft das Skript).

```powershell
Set-Location "INSTALLVERZ\frontend"
npm.cmd ci
npm.cmd run build
Set-Location "INSTALLVERZ"
Test-Path "INSTALLVERZ\frontend\dist\index.html"
```

Erwartung: Der Build endet mit einer Zeile „built in …“ und ohne Zeile „error“, die letzte Ausgabe
ist `True`. Dauer: ein bis zwei Minuten. Warnungen, etwa zu `approve-scripts`, „deprecated“ oder
„vulnerabilities“, sind für die Installation unerheblich. Sage das dem Anwender vorab, damit er sie
nicht für Fehler hält.

## Schritt 7: KI-Zugang einrichten (nur bei „Ja“ in Schritt 0, sonst als ÜBERSPRUNGEN protokollieren)

Welcher Zweig gilt, bestimmt die KI-Wahl aus Schritt 0. Bei **Claude** gehst du 7a bis 7d durch, bei
**ChatGPT** 7e und 7f. Den Zweig, der nicht gilt, protokollierst du als ÜBERSPRUNGEN.

### Zweig Claude: 7a bis 7d

**Wichtig:** Sage dem Anwender vorab, dass er den Schlüssel, der gleich erscheint, **nicht in den
Chat einfügt**.

7a. Anmelden:

```powershell
Set-Location "INSTALLVERZ"
claude
```

Beim ersten Start fragt Claude Code nach einem Farbschema und nach der Anmeldeart. Der Anwender wählt
die Anmeldung mit seinem Claude-Konto. Claude Code öffnet dann den Browser, dort meldet er sich an und
bestätigt den Zugriff. Fragt Claude Code anschließend, ob er den Dateien in diesem Ordner vertraut,
bestätigt er. Zurück in PowerShell beendet er Claude Code mit `/exit`.

7b. Zugangsschlüssel erzeugen:

```powershell
claude setup-token
```

Der Anwender bestätigt im Browser und kopiert den lange angezeigten Schlüssel vollständig in die
Zwischenablage.

7c. Datei anlegen und öffnen:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.bewerbung_mgmt_secrets" | Out-Null
if (-not (Test-Path "$env:USERPROFILE\.bewerbung_mgmt_secrets\agent.env")) { Copy-Item "INSTALLVERZ\automation\agent.env.example" "$env:USERPROFILE\.bewerbung_mgmt_secrets\agent.env"; "neu angelegt" } else { "vorhanden, nicht überschrieben" }
notepad "$env:USERPROFILE\.bewerbung_mgmt_secrets\agent.env"
```

Die zweite Zeile überschreibt eine vorhandene Datei nie. Meldet sie „vorhanden, nicht überschrieben“,
gab es schon ein BMS: Steht in der Datei bereits ein Schlüssel, bleibt er, und der Anwender schließt
den Editor ohne Änderung (dann kann 7b entfallen, wenn der Schlüssel noch gilt).

Anleitung für den Editor: „Suchen Sie die Zeile, die mit `# CLAUDE_CODE_OAUTH_TOKEN=` beginnt. Löschen
Sie das `#` und das Leerzeichen am Zeilenanfang und ersetzen Sie alles nach dem `=` durch Ihren
Schlüssel, auch das Beispiel `sk-ant-oat01-...`. Der Schlüssel steht in einer einzigen Zeile, ohne
Leerzeichen. Speichern Sie mit Strg + S und schließen Sie den Editor.“

7d. Prüfen, ohne den Schlüssel zu zeigen:

```powershell
if (Select-String -Path "$env:USERPROFILE\.bewerbung_mgmt_secrets\agent.env" -Pattern '^CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-[A-Za-z0-9_-]{40,}\s*$') { "vorhanden" } else { "fehlt" }
```

Erwartung: `vorhanden`. Bei `fehlt`: Zeile prüfen (kein `#`, Wert nach dem `=`, eine Zeile). Das Beispiel
`sk-ant-oat01-...` darf nicht mehr in der Zeile stehen.

### Zweig ChatGPT: 7e und 7f

Bei ChatGPT gibt es keinen Schlüssel zum Einfügen und keine Datei `agent.env`: Die Anmeldung läuft im
Browser und bleibt im Programm Codex. Sage dem Anwender vorab: „Gleich öffnet sich der Browser. Melden
Sie sich dort mit Ihrem ChatGPT-Konto an (Plus oder Pro).“ Unter Windows braucht die bevorzugte Sandbox
von Codex nach den Angaben von OpenAI einmalig ein Administrator-Setup. Fragt Windows dabei oder beim
ersten Lauf mit „Änderungen zulassen?“ nach, bestätigt der Anwender mit „Ja“.

7e. Anmelden:

```powershell
codex.cmd login
```

Codex öffnet den Browser. Der Anwender meldet sich mit seinem ChatGPT-Konto an und bestätigt den
Zugriff. Danach kehrt der Befehl in PowerShell zur Eingabe zurück.

7f. Prüfen:

```powershell
codex.cmd login status
```

Erwartung: `Logged in using ChatGPT`. Bei einer anderen Ausgabe wiederholst du 7e. Hilft das nach zwei
Versuchen nicht, halte an (Gesprächsregel 4).

## Schritt 8: Erster Start und Selbsttest

Der Server läuft im schwarzen Fenster. Dieses Fenster muss offen bleiben. Starten:

```powershell
Start-Process "INSTALLVERZ\start_windows.bat" -WorkingDirectory "INSTALLVERZ"
```

Es öffnet sich ein schwarzes Fenster, nach wenigen Sekunden der Browser mit dem BMS unter
`http://localhost:8000`. Frage: „Ist das BMS im Browser aufgegangen? Steht im schwarzen Fenster eine
Fehlermeldung?“ Dann in einer **neuen** PowerShell:

```powershell
Invoke-RestMethod http://localhost:8000/api/version
(Invoke-WebRequest http://localhost:8000/ -UseBasicParsing).StatusCode
Test-Path "INSTALLVERZ\data\bewerbung.sqlite"
```

Erwartung: Eine Antwort mit der Programmversion; `200`; `True`.

Hinweise, die der Anwender nicht als Fehler werten soll:
- Eine Warnung „agent.env: zu offene Rechte … chmod 600“ im schwarzen Fenster ist unter Windows
  gegenstandslos.
- Beim ersten Start legt das BMS selbst an, was es braucht: den Datenordner, die Datenbank und eine
  Grundfassung der Sucheinstellungen. Außerdem füllt es sich einmalig mit Beispieldaten einer
  erfundenen Person („Benno Bewerbaer“). Das ist normal.
- Meldet Windows „Der Computer wurde durch Windows geschützt“, klickt der Anwender auf „Weitere
  Informationen“ und dann auf „Trotzdem ausführen“. Das passiert, wenn die Download-Markierung in
  Schritt 4 nicht entfernt wurde.

Bricht der Start ab: Der Anwender soll die letzten Zeilen des schwarzen Fensters einfügen. Meldet
„venv nicht gefunden“, gehe zurück zu Schritt 5. Meldet „address already in use“ oder, wie unter
Windows üblich, etwa `[Errno 10048] … nur jeweils einmal verwendet werden`, läuft das BMS schon. Prüfe
in diesem Fall die Versionsabfrage oben.

**Nur bei ChatGPT: KI umstellen.** Das BMS startet mit Claude als KI. Bei ChatGPT stellt der Anwender
jetzt einmal um, entweder in den „Einstellungen“ (Karte „KI“, ChatGPT wählen) oder in PowerShell. Gib
für PowerShell in der **neuen** Sitzung vor:

```powershell
Invoke-RestMethod -Method Patch -Uri http://localhost:8000/api/einstellungen -ContentType 'application/json' -Body '{"ki_anbieter":"chatgpt"}' | Out-Null
(Invoke-RestMethod http://localhost:8000/api/einstellungen).ki_anbieter
```

Erwartung: `chatgpt`. Bei Claude ist nichts zu tun, Claude ist der Standard.

## Schritt 9: Abnahme

Gehe diese Punkte nacheinander mit dem Anwender durch. Frage jeweils, was er sieht, und
protokolliere OK oder PROBLEM mit Wortlaut.

1. „Einstellungen“ öffnen: alle Karten erscheinen ohne Fehlermeldung.
2. Karte „Beispieldaten“ → „Beispieldaten entfernen“: Die Beispieldaten verschwinden.
3. „Stellen“ → „+ Stelle anlegen“ → eine Testfirma erfassen: Sie erscheint in der Liste.
4. Nur bei KI-Einrichtung: den Zugang der gewählten KI prüfen. Bei Claude hat 7d schon `vorhanden`
   gemeldet. Bei ChatGPT gib in PowerShell vor:

   ```powershell
   codex.cmd login status
   (Invoke-RestMethod http://localhost:8000/api/ki-status).chatgpt
   ```

   Erwartung: `Logged in using ChatGPT`, und die Auskunft des zweiten Befehls zeigt `ChatGPT` mit
   `True` bei `installiert` und bei `angemeldet`.
5. Nur bei KI-Einrichtung: In dieser Stelle „Company-Fit prüfen“ starten. Der Lauf erscheint im
   „Task-Center“ und endet nach einigen Minuten (bei Claude etwa zehn) mit einem Ergebnis. **Das ist
   unter Windows der am wenigsten erprobte Teil, mit ChatGPT ist er noch gar nicht erprobt.** Frage
   nach dem Status und lass dir bei einem Fehler die Meldung aus dem Task-Center vollständig nennen.
   Meldet ein ChatGPT-Lauf, das Nutzungslimit des Abos sei erreicht, ist das kein Installationsfehler:
   Der Lauf wird später erneut gestartet.
6. Dashboard: Excel-Export auslösen. Eine Datei wird erzeugt.
7. Beenden und neu starten: Im schwarzen Fenster Strg + C drücken. Windows fragt dann „Batchvorgang
   abbrechen (J/N)?“, der Anwender antwortet mit `J`. Danach

   ```powershell
   Start-Process "INSTALLVERZ\start_windows.bat" -WorkingDirectory "INSTALLVERZ"
   ```

   Das BMS startet erneut. (Sollte sich das Fenster nicht beenden lassen, hilft
   `Start-Process "INSTALLVERZ\stop_windows.bat"`.)

Weise den Anwender zum Schluss darauf hin, dass „CV erstellen“ (PDF über LibreOffice) erst nach
Anlage von Profil und Basis-Lebenslauf prüfbar ist. Das Profil trägt er in der Oberfläche ein: auf
der Seite „Profil“ in der ersten Karte „Identität und Suchstrategie“ (Name als Pflichtfeld, Anschrift
als `Straße Nr, PLZ Ort`, Kontakt, Kurzprofil, Zieltermin, Rahmenbedingungen). Danach lädt er den
Basis-Lebenslauf hoch, ebenfalls auf der Seite „Profil“. Das ist Teil der Einrichtung, die im
Abschnitt „Einrichten: Das BMS lernt Sie kennen“ weiter unten in dieser Datei und in
`docs/ANLEITUNG.md` im Installationsverzeichnis beschrieben ist.

Die Einschränkungen im Abschnitt „Was unter Windows eingeschränkt ist“ sind keine
Installationsfehler. Protokolliere sie nicht als FEHLER.

## Schritt 10: Protokoll schreiben und Abschluss

Das Protokoll soll in `INSTALLVERZ\Installprotokoll.md` stehen und enthält pro Schritt: Nummer,
Titel, Ergebnis (OK, FEHLER, ÜBERSPRUNGEN) und bei Fehlern die vollständige Meldung. Am Ende steht
ein Abschnitt „Offene Punkte“. **Enthält nie Schlüssel oder andere Geheimnisse.**

- Kannst du in dieser Sitzung Dateien auf dem PC des Anwenders schreiben, tu das direkt.
- Sonst gib dem Anwender **einen** Befehl vor, der das Protokoll anhängt. Setze den Text in ein
  Here-String in einfachen Anführungszeichen ein, der Abschluss `'@` steht am Zeilenanfang:

  ```powershell
  Add-Content -Encoding UTF8 -Path "INSTALLVERZ\Installprotokoll.md" -Value @'
  <hier das fertige Protokoll im Markdown-Format>
  '@
  Get-Content "INSTALLVERZ\Installprotokoll.md"
  ```

  Frage, ob der Inhalt in der Ausgabe erscheint.

**Auch bei Abbruch** (zwei Korrekturversuche erfolglos): Schreibe das Protokoll mit dem bisherigen
Stand und dem Fehler, damit die Installation später gezielt fortgesetzt oder der Fehler behoben
werden kann.

Fasse zum Schluss in höchstens zehn Zeilen zusammen:

- was installiert wurde (mit Versionen aus den Prüfungen) und welche KI gewählt ist,
- was funktioniert und was nicht (auch ehrlich, was nicht geprüft werden konnte),
- wie das BMS künftig gestartet wird (`INSTALLVERZ\start_windows.bat` per Doppelklick) und beendet
  (Strg + C im schwarzen Fenster und die Rückfrage „Batchvorgang abbrechen (J/N)?“ mit `J` beantworten,
  sonst `INSTALLVERZ\stop_windows.bat`),
- wo das Protokoll liegt.

Biete danach an, mit dem Einrichten weiterzumachen: „Möchten Sie jetzt das BMS auf Ihre Person
einrichten? Das dauert ein bis zwei Stunden und lässt sich jederzeit unterbrechen.“ Grundlage ist der
Abschnitt „Einrichten: Das BMS lernt Sie kennen“ unter „Nach der Installation“. Sagt der Anwender
ja, gehe diesen Abschnitt mit ihm durch, in der dort genannten Reihenfolge und nach denselben
Gesprächsregeln (ein Abschnitt je Nachricht, Zugangsschlüssel nie im Chat). Sagt er nein, weise
darauf hin, dass der Abschnitt jederzeit in dieser Datei steht.

# Nach der Installation

Dieser Teil richtet sich an Sie. Er gilt, sobald das BMS läuft. Der Assistent nutzt ihn zugleich als
Grundlage, wenn Sie nach der Installation mit dem Einrichten weitermachen.

## Einrichten: Das BMS lernt Sie kennen

Das BMS läuft jetzt, zeigt aber nur Beispieldaten und weiß noch nichts über Sie. Die folgenden
Schritte erledigen Sie einmalig und in dieser Reihenfolge: zuerst die Beispieldaten entfernen, dann
die fünf Abschnitte von „Ihr Profil: Identität und Suchstrategie“ bis „Suchbereich in der Jobliste“.
Diese brauchen Sie, damit das BMS für Sie arbeiten kann: Ohne Profil und Lebenslauf entstehen weder
Anschreiben noch Lebensläufe, ohne Zielrollen und Region findet die Jobsuche nichts Passendes. Die
E-Mail-Anbindung unter „E-Mail-Postfach verbinden“ ist optional.

### Zuerst: Beispieldaten entfernen

Beim allerersten Start bringt das BMS Beispieldaten von „Benno Bewerbaer“ mit, einer erfundenen Person:
Postbote mit fünf Jahren Erfahrung in der Paketzustellung. Dazu gehören sechs Firmen, fünf Stellen in
verschiedenen Stadien, drei Bewerbungen, fünf Mails, ein Gesprächstermin, ein Profil mit Fähigkeiten
und Werdegang, die Profil-Datei `config/profil.md` und ein deutscher Basis-Lebenslauf. Damit können
Sie das BMS ausprobieren. Solange die Beispieldaten da sind, steht auf dem Dashboard ein Hinweis, und
die Seitenleiste zeigt „Benno Bewerbaer“ als Ihren Namen. Wer das BMS schon benutzt hat, bekommt keine
Beispieldaten, und ein Update bringt keine.

Entfernen Sie die Beispieldaten, bevor Sie eigene Daten eintragen:

1. Öffnen Sie „Einstellungen“ und suchen Sie die Karte „Beispieldaten“.
2. Klicken Sie auf „Beispieldaten entfernen“ und bestätigen Sie mit „Ja, entfernen“.

Vorher legt das BMS eine Sicherung Ihrer Datenbank an, im Ordner `data/backups/auto`, in dem auch
„Jetzt sichern“ ablegt. Scheitert die Sicherung, bleibt alles unverändert, und die Karte nennt den
Grund. Danach gilt:

- Gelöscht werden nur die Beispieldaten und was an den Beispielstellen hängt. Was Sie selbst
  angelegt haben, bleibt, auch Mails, die Sie einer Beispielstelle zugeordnet haben: Sie bleiben als
  Mails ohne Stelle erhalten.
- Die Profil-Datei und der Basis-Lebenslauf wandern in den Papierkorb `data/papierkorb/`, aber nur,
  wenn Sie sie nicht verändert haben. Eine eigene Fassung bleibt stehen, und die Karte nennt sie
  Ihnen.
- Danach steht in der Seitenleiste „Bewerber“, bis Sie unter „Ihr Profil: Identität und
  Suchstrategie“ (siehe unten) Ihren Namen im Profil speichern.

Haben Sie Ihr Profil schon gespeichert (Karte „Identität und Suchstrategie“, siehe unten) oder die
Datei `config/profil.md` von Hand bearbeitet, bevor Sie die Beispieldaten entfernen, erkennt das BMS
die Datei als Ihre eigene und lässt sie stehen. Gehen Sie die Karte dann einmal ganz durch und
ersetzen Sie alles, was noch von Benno Bewerbaer stammt: Name, Anschrift, Kontakt, Kurzprofil, Zieltermin
und Rahmenbedingungen. Genauso bleibt ein Basis-Lebenslauf, den Sie schon hochgeladen haben.

Der Grund für die Reihenfolge: Der LinkedIn-Import (siehe „Werdegang und Fähigkeiten von LinkedIn
übernehmen“) füllt Ihr Profil nur dort, wo noch nichts steht. Mit den Beispieldaten im Profil übernähme
er Ihre Positionierung nicht und übersprünge Fähigkeiten, die als Beispiel schon dastehen. Entfernen
Sie die Beispieldaten deshalb zuerst, danach tragen Sie Ihr Profil ein („Ihr Profil: Identität und
Suchstrategie“) und laden Ihren Lebenslauf hoch („Ihr Lebenslauf“), und erst dann importieren Sie
von LinkedIn.

### Ihr Profil: Identität und Suchstrategie

Öffnen Sie in der Seitenleiste „Profil“. Die erste Karte heißt „Identität und Suchstrategie“. Dort
tragen Sie ein, wer Sie sind und wonach Sie suchen. Name, Anschrift, Kontakt und LinkedIn bilden den
Briefkopf Ihrer Anschreiben und die Dateinamen Ihrer Unterlagen. Kurzprofil, Zieltermin und
Rahmenbedingungen liest die KI als Hintergrund, wenn sie Stellen bewertet und Anschreiben schreibt.
Zeigt die Karte noch Angaben von „Benno Bewerbaer“, haben Sie die Beispieldaten noch nicht entfernt.
Holen Sie das zuerst nach (siehe oben).

Das tragen Sie ein:

| Feld | Was hineingehört |
|---|---|
| Name | **Pflichtfeld.** Ihr vollständiger Name, etwa „Max Mustermann“. Er steht in der Seitenleiste, im Briefkopf und in den Dateinamen Ihrer Lebensläufe und Anschreiben. |
| Positionierung (Kurzzeile) | Optional. Eine kurze Zeile, etwa „Service Delivery Leader, DACH“. Den ausführlichen Text zur Positionierung pflegen Sie weiter unten auf der Profil-Seite (siehe „Werdegang und Fähigkeiten von LinkedIn übernehmen“). |
| Anschrift | Schreiben Sie sie als `Straße Nr, PLZ Ort`, etwa `Musterweg 3, 12345 Musterstadt`. Daraus entsteht die Ortszeile Ihrer Anschreiben. Dieselbe Angabe ist der Startpunkt der Routenplanung zu Vorstellungsgesprächen. |
| E-Mail, Telefon | Ihre Kontaktdaten für den Briefkopf. |
| LinkedIn | Optional. Die Adresse Ihres Profils, etwa `https://www.linkedin.com/in/max-mustermann/`. |
| Aktuell | Optional. Ihre jetzige Stelle in einer Zeile, etwa „Manager Professional Services bei der Beispiel GmbH, seit 2024“. |
| Kurzprofil | Zwei bis vier Sätze über Sie. Das BMS nutzt sie als Tonvorlage für Ihre Anschreiben. |
| Zieltermin | Optional. Bis wann Sie wechseln möchten, etwa „neue Rolle bis 31.12.2026“. Titel, Ebene und Branche Ihrer Zielrollen tragen Sie unter „Einstellungen“ in die Karten „Plan A“, „Plan B“ und „Plan C“ ein (Abschnitt „Zielrollen und Suchgebiet“). |
| Harte Rahmenbedingungen | Was für Sie nicht verhandelbar ist. Je Zeile ein Punkt, beginnend mit „- “, etwa „- Kein Umzug, kein dauerhafter Zweitwohnsitz.“ |
| Bekannte Skill-Gaps | Lücken in Ihrem Profil, die Sie selbst kennen. Je Zeile ein Punkt. Ehrliche Angaben helfen, denn so bewertet die KI Stellen realistisch. |

Je konkreter Sie schreiben, desto passender werden Bewertungen und Anschreiben. Kurzprofil, Zieltermin
und Rahmenbedingungen dürfen Sie frei formulieren.

Mit „Speichern“ übernimmt das BMS Ihre Angaben. Der Knopf ist erst aktiv, wenn Sie etwas geändert
haben. Danach steht dort „✓ Gespeichert“, und die Seitenleiste und die Routenplanung zeigen die neuen
Angaben sofort. Dabei gilt:

- Der Name muss ausgefüllt sein. Solange er fehlt, lässt sich die Karte nicht speichern.
- Fehlt der Anschrift das Komma oder die Postleitzahl, oder hat die E-Mail-Adresse kein @, zeigt die
  Karte eine gelbe Zeile mit einem Hinweis. Gespeichert wird trotzdem.
- Bei jedem Speichern legt das BMS die vorherige Fassung der Datei in den Papierkorb
  `data/papierkorb/`. Nichts geht verloren.
- Haben Sie die Datei zwischenzeitlich geändert, etwa von Hand oder durch eine Auswertung des BMS,
  bittet die Karte um Neuladen. Klicken Sie auf „Neu laden“ und tragen Sie Ihre Änderung noch einmal
  ein. So überschreiben Sie nie versehentlich fremde Änderungen.

Die Angaben stehen in der Datei `config/profil.md` im BMS-Ordner. Wer mag, bearbeitet die Datei weiter
von Hand. Die Karte lässt stehen, was sie nicht kennt, etwa den Abschnitt „Empirie aus dem
Bewerbungsverlauf“, den das BMS selbst pflegt, und eigene Abschnitte. Bei Handarbeit kommt es auf die
Schreibweise an: Name, Standort, Kontakt und LinkedIn erkennt das BMS an der Fettschrift, die Sternchen
um `**Name:**` müssen also stehen bleiben. Die Anschrift heißt in der Datei `**Standort:**`, E-Mail und
Telefon stehen zusammen unter `**Kontakt:**`, getrennt mit `·`.

### Ihr Lebenslauf

Das BMS erfindet keinen Lebenslauf. Es nimmt Ihren vorhandenen als Grundlage und passt ihn für jede
Stelle an. Laden Sie ihn als Word-Datei (`.docx`) hoch: In der Oberfläche unter „Profil“, ganz unten
im Bereich „Basis-CVs“, wählen Sie die Sprache, dann die Datei, und klicken auf „Hochladen“.

Laden Sie eine deutsche und eine englische Fassung hoch. Das BMS wählt je nach Stellenanzeige
selbst die passende. Bewerben Sie sich nur auf Deutsch, darf die englische Fassung eine Kopie der
deutschen sein, sie muss aber vorhanden sein.

Damit das BMS Ihre Berufsstationen erkennt, braucht der Lebenslauf einen bestimmten Aufbau:

| Element | So muss es aussehen |
|---|---|
| Überschriften der Abschnitte | Formatvorlage „Überschrift 1“, in Großbuchstaben |
| Abschnitt für die Berufserfahrung | `BERUFSERFAHRUNG` (deutsch) oder `PROFESSIONAL EXPERIENCE` (englisch) |
| Erste Zeile jeder Station | Formatvorlage „Standard“: Firma, dann ein Tabulator, dann der Zeitraum |
| Zeile direkt darunter | Ihre Position, fett, Schriftgröße 11, ohne Tabulator |
| Danach | ein bis zwei Zeilen kursive Beschreibung der Firma |
| Danach | Ihre Erfolge als Aufzählung mit der Formatvorlage „Listenabsatz“ |

Der Tabulator zwischen Firma und Zeitraum ist das Erkennungszeichen einer Station. Verwenden Sie ihn
deshalb nirgends sonst im Dokument. In anderen Rubriken wie Ausbildung oder Zertifikate trennen Sie
Angaben mit `•`.

Nach dem Hochladen zeigt das BMS an, wie viele Stationen es erkannt hat. Erscheint ein gelber
Hinweis, stimmt der Aufbau noch nicht. Korrigieren Sie die Datei in Word und laden Sie sie erneut
hoch. Das BMS fragt vor dem Überschreiben nach und legt die alte Fassung in den Papierkorb.

### Werdegang und Fähigkeiten von LinkedIn übernehmen

Das ist der schnellste Weg, die Profil-Seite zu füllen, ohne alles abzutippen. Bei LinkedIn gehen
Sie auf Einstellungen, Datenschutz, „Eine Kopie Ihrer Daten erhalten“ und wählen die oberste
Option, das größere Datenarchiv. Die Schnellauswahl „Profil“ enthält nur Ihre Kurzbeschreibung und
reicht nicht aus. LinkedIn schickt Ihnen eine E-Mail, sobald das Archiv bereitsteht.

Die ZIP-Datei von LinkedIn laden Sie dann unter „Profil“ mit „Datenexport-ZIP hochladen“ hoch. Das
BMS übernimmt Kurzbeschreibung, Standort, Fähigkeiten, Berufsstationen, Ausbildung und Zertifikate.
Es ergänzt dabei nur und überschreibt nichts. Anschließend sortiert es Ihre Fähigkeiten im
Hintergrund in Themenbereiche. Laden Sie die Datei erst hoch, wenn die Beispieldaten entfernt sind,
denn mit ihnen übernähme das BMS nicht alles (Begründung unter „Zuerst: Beispieldaten entfernen“).

Ohne Export und ohne Wartezeit geht es unter „Profil“ mit „Profil auslesen“, wenn der KI-Zugang eingerichtet ist (Schritt 7). Öffnen Sie Ihr
Profil bei LinkedIn im Browser, markieren Sie alles, kopieren Sie es und fügen Sie es ein. Oder laden Sie das PDF hoch, das
LinkedIn über „Als PDF speichern“ erzeugt. Die KI strukturiert den Text, Sie prüfen das Ergebnis in einer Vorschau, und erst
dann ergänzt das BMS Ihr Profil. LinkedIn zeigt auf der Profilseite und im PDF nicht alles, Fähigkeiten oft nur gekürzt.
Der Export bleibt deshalb der vollständigste Weg. Einen automatischen Abruf über die Adresse Ihres Profils gibt es nicht,
denn LinkedIn sperrt ihn.

Ohne LinkedIn tragen Sie Positionierung, Werdegang und Fähigkeiten direkt auf der Profil-Seite ein.
In beiden Fällen gilt: Sehen Sie das Ergebnis einmal durch und ergänzen Sie, was fehlt. Diese
Angaben nutzt das BMS als Faktenbasis für Anschreiben und Lebensläufe.

### Zielrollen und Suchgebiet

Unter „Einstellungen“ legen Sie fest, wonach das BMS sucht. Gehen Sie die Bereiche in dieser
Reihenfolge durch:

1. „Suchbereich & Firmengröße“: ob Sie remote, deutschlandweit oder in einem Umkreis um Ihren
   Wohnort suchen, und ab welcher Mitarbeiterzahl eine Firma infrage kommt.
2. Die Karten „Plan A“, „Plan B“ und „Plan C“: Ihre Zielrollen mit Titel, Ebene und Branche.
   Plan A ist Ihr eigentliches Ziel, Plan B die realistische Alternative, Plan C eine optionale
   Auffangebene. Diese Felder sind nach der Installation leer. Solange sie leer sind, findet die
   Jobsuche nichts, weil sie nicht weiß, wonach sie suchen soll.
3. „Suchportale“: Sechs gängige Portale sind vorbelegt und eingeschaltet. Sie können einzelne
   abschalten oder zwei eigene ergänzen. Die Portale sind auf Deutschland ausgerichtet; außerhalb helfen
   die freien Zeilen, LinkedIn-Alerts und die Zielfirmen.
4. „KI-Modell je Funktion“: Zur Wahl stehen Opus 5.5, Sonnet 5.5 und Haiku 4.5, voreingestellt ist
   Sonnet 5.5. Die Voreinstellung passt für den Alltag, hier müssen Sie nichts ändern. Das Modell
   Fable bietet das BMS bewusst nicht an, weil es zu teuer ist: Es kostet das Zweieinhalbfache von
   Opus 5.5 und das Fünffache von Sonnet 5.5. Haben Sie ChatGPT als KI gewählt, stehen dort die Modelle
   von ChatGPT zur Wahl, voreingestellt ist die mittlere Stufe.

### Suchbereich in der Jobliste

Der Suchbereich aus „Zielrollen und Suchgebiet“ (Remote, Deutschlandweit, Stadt + Umkreis) taucht
automatisch in der Jobliste und in den Filtern auf, als eigener Reiter mit der Bezeichnung
„<Stadt-Kurzform> +<km>km“, etwa „München +50km“ bei der Stadt München und 50 km Radius. Die
Stadt-Kurzform lässt einen Namenszusatz wie „am“, „an der“ oder „im“ weg: Aus „Frankfurt am Main“
wird „Frankfurt“, aus „Bad Homburg vor der Höhe“ wird „Bad Homburg“. Auch die Suche selbst übernimmt
Stadt und Umkreis automatisch aus den Einstellungen. Sie müssen dafür keine Datei mehr von Hand
ändern.

Ändern Sie Stadt oder Radius später, stellt das BMS alle vorhandenen Stellen mit der alten
Bezeichnung automatisch auf die neue um und zeigt danach, wie viele Stellen betroffen waren.

### E-Mail-Postfach verbinden

Dieser Schritt ist optional, aber empfehlenswert: Mit einem verbundenen Postfach erkennt das BMS
Antworten auf Ihre Bewerbungen und liest Stellen aus Job-Benachrichtigungen. Unter „Einstellungen“,
Bereich „E-Mail-Konto“, tragen Sie die Zugangsdaten Ihres Postfachs ein. Verwenden Sie dort ein
App-Passwort Ihres Mail-Anbieters, nicht Ihr normales Kennwort. Wie Sie ein App-Passwort erzeugen
und welche Serverangaben Ihr Anbieter verlangt, steht in `docs/SETUP-EMAIL.md` im Programmordner.

Das BMS verschickt nie selbst E-Mails. Es legt ausschließlich Entwürfe an, die Sie prüfen und selbst
absenden.

Der E-Mail-Check blendet einige technische Absender bereits von selbst aus. Haben Sie eigene,
private Absender, die ähnlich klingen wie eine Bewerbungsantwort, aber nichts mit Ihrer Jobsuche zu
tun haben, tragen Sie diese in `config/suchprofile.yaml` ein. Öffnen Sie die Datei mit einem
Texteditor und ergänzen Sie unterhalb der Zeile, die mit `# <<< ENDE AUTO-GENERIERT` beginnt, einen
Block wie diesen (Domains oder vollständige Adressen, eine Zeile je Absender):

```yaml
email_check:
  ausschluss_absender:
    - beispielverein.example.org
    - newsletter@anderer-dienst.example.com
```

Dieser Bereich der Datei bleibt bei jedem Speichern in den Einstellungen unangetastet. Speichern
Sie die Datei und starten Sie das BMS neu, damit es die Änderung einliest.

## Kurz prüfen, ob alles sitzt

| Prüfung | Erwartung | Falls nicht |
|---|---|---|
| `http://localhost:8000` im Browser | Die Oberfläche mit Menü erscheint | Oberfläche bauen (Schritt 6) |
| Seitenleiste links oben ansehen | Unter „Bewerbungs-Management-System“ steht Ihr Name, nicht „Benno Bewerbaer“ oder „Bewerber“ | Beispieldaten entfernt (Abschnitt „Einrichten: Das BMS lernt Sie kennen“)? Name in der Karte „Identität und Suchstrategie“ eingetragen und gespeichert (Abschnitt „Ihr Profil: Identität und Suchstrategie“)? Bei einer von Hand bearbeiteten `config/profil.md` die Schreibweise `**Name:**` prüfen |
| „Dashboard“ ansehen | Kein Hinweis auf Beispieldaten mehr, keine Stellen und Mails von Benno Bewerbaer | „Beispieldaten entfernen“ in den „Einstellungen“ (Abschnitt „Zuerst: Beispieldaten entfernen“) |
| „Einstellungen“ öffnen | Alle Bereiche erscheinen ohne Fehlermeldung | Das Fenster des BMS auf Fehlermeldungen prüfen, BMS neu starten |
| Unter „Stellen“ mit „+ Stelle anlegen“ eine Stelle erfassen | Sie erscheint in der Liste | BMS neu starten |
| In dieser Stelle „Company-Fit prüfen“ starten | Der Lauf erscheint im „Task-Center“ und endet mit einem Ergebnis | Bei Claude den Zugangsschlüssel prüfen, bei ChatGPT `codex.cmd login status` (Schritt 7) |
| Danach „CV-Match“ und anschließend „CV erstellen“ starten | Eine Word- und eine PDF-Datei entstehen | Basis-CV (Abschnitt „Ihr Lebenslauf“) und LibreOffice prüfen |
| „Einstellungen“ → „Programmversion“ und den Fuß der Seitenleiste ansehen | Beide zeigen Ihre installierte Version | BMS neu starten, danach die Seite neu laden |

Ein KI-Lauf wie die Firmenprüfung dauert etwa zehn Minuten. Solange er läuft, können Sie normal
weiterarbeiten.

## Aktualisierungen einspielen

Meldungen im Eingabefenster folgen der Sprache Ihres Systems: Deutsch auf einem deutschen System, sonst Englisch.

Neue Versionen erscheinen auf GitHub (https://github.com/holgerdaube/BewerbungsMgmtSystem/releases).
Ein eigenes Werkzeug lädt sie, prüft sie, sichert Ihren Stand und spielt sie ein. Ihre Daten,
Einstellungen und Anpassungen bleiben dabei erhalten. Ob es eine neue Version gibt, zeigt Ihnen auch
das BMS selbst: Unter „Einstellungen“, Karte „Programmversion“, fragt der Knopf „Nach Updates suchen“
bei GitHub nach der neuesten Version. Er zeigt das Ergebnis nur an und spielt nichts ein. Das Einspielen
übernimmt das Werkzeug, und zwar bei beendetem BMS:

1. Beenden Sie das BMS: Doppelklick auf `stop_windows.bat`. Ein laufendes BMS kann sich nicht
   zuverlässig selbst ersetzen, das Update-Werkzeug bricht sonst mit der Meldung „Das BMS läuft
   noch“ ab.
2. Doppelklicken Sie im Programmordner auf `update_windows.bat`. Es öffnet sich ein Konsolenfenster.
3. Das Werkzeug sucht online nach einer neuen Version. Es schreibt dazu: „Suche auf GitHub nach einer
   neuen Version. GitHub erhält dabei die IP-Adresse dieses Rechners.“ Gesendet wird nur diese
   Anfrage, nichts aus Ihrer Datenbank. Findet das Werkzeug eine neuere Version, lädt es sie, vergleicht
   die Prüfsumme mit der Angabe von GitHub und prüft das Paket.
4. Das Werkzeug zeigt einen Plan: welche Dateien sich ändern und ob Python- oder
   Oberflächen-Bausteine neu installiert werden müssen. Bestätigen Sie die Rückfrage „Update von …
   auf … jetzt einspielen?“ mit `j`, wenn der Plan passt. Gibt es nichts Neues, meldet das Werkzeug
   „Ihr BMS ist auf dem neuesten Stand“, und Sie sind fertig.
5. Nach Abschluss steht dort „Update auf Version … abgeschlossen. Starten Sie das BMS wie
   gewohnt.“ Starten Sie das BMS wie gewohnt: Doppelklick auf `start_windows.bat` in Ihrem
   BMS-Ordner.

**Der zweite Weg: eine ZIP-Datei.** Klappt die Online-Suche nicht, oder möchten Sie sie nicht nutzen,
laden Sie die neue Datei `BMS_<Version>.zip` im Browser von der Release-Seite
(https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/latest, unter „Assets“) und speichern Sie
sie in Ihrem Ordner „Downloads“. Starten Sie das Werkzeug dann wie oben. Es findet die ZIP-Datei von
selbst, prüft sie und zeigt den Plan. Liegt eine ZIP-Datei in „Downloads“ und findet das Werkzeug
auch online eine Version, nimmt es die höchste Version, egal woher. Haben Sie eine Version bis 1.7.0
installiert, nehmen Sie für das erste Update auf eine Version ab 1.9.0 diesen Weg.

Meldet das Werkzeug „Online-Suche nicht möglich: …“, bricht es nicht ab. Es nennt den Grund, etwa
„Es besteht keine Verbindung zu GitHub.“ oder „GitHub begrenzt gerade die Anfragen. Bitte versuchen
Sie es in einer Stunde erneut.“, und macht mit der ZIP-Datei in „Downloads“ weiter, wenn dort eine
liegt.

Ihre Daten (die Datenbank und alles unter `outputs`), Ihre Einstellungen, Ihr Profil
(`config/profil.md`) und Ihr Suchprofil (`config/suchprofile.yaml`) sind nie Teil eines
Programmpakets und bleiben deshalb unverändert. Ihr Zugangsschlüssel und weitere Secrets liegen
außerhalb des Programmordners und bleiben ebenfalls unberührt. Haben Sie über die Oberfläche eine
Beirats-Persona neu besetzt oder `config/profil_struktur.md` bzw. `config/scoring_rubrik.md`
angepasst, bleibt das ebenfalls erhalten. Die neue Fassung dieser Dateien legt das Update
zusätzlich zum Vergleich ab, ohne Ihre eigene zu überschreiben.

Vor jeder Änderung legt das Werkzeug eine Sicherung an, in einem eigenen Ordner unter
`data/updates/…` (etwa `data/updates/2026-10-15_091200_1.0.0_zu_1.1.0`): eine Kopie Ihrer
Datenbank und jede Datei, die es ersetzt oder entfernt. Schlägt ein Update unterwegs fehl, macht
das Werkzeug alle Änderungen automatisch rückgängig und nennt in der Meldung den Sicherungsordner.

Ändert sich mit dem Update auch die Oberfläche, baut das Werkzeug sie neu und braucht dafür
Node.js aus der Installation (Schritt 3). Fehlt es, bricht das Werkzeug schon beim Prüfen ab, ohne
etwas zu verändern. Für neue Python- und Oberflächen-Bausteine braucht das Werkzeug eine
Internetverbindung, wie schon bei der Installation.

In PowerShell rufen Sie das Werkzeug auch mit Optionen auf. Die Beispiele nennen den vorgeschlagenen
Ordner; haben Sie einen anderen gewählt, setzen Sie Ihren BMS-Ordner ein. `--pruefen` zeigt nur den
Plan, ohne etwas einzuspielen. Ein dafür geladenes Paket bleibt im Ordner `data\updates\pakete`
liegen:

```powershell
& "$env:USERPROFILE\BMS\update_windows.bat" --pruefen
```

`--offline` verhindert jeden Kontakt zu GitHub. Das Werkzeug sucht dann nicht online nach einer
neuen Version und nimmt nur eine ZIP-Datei aus „Downloads“:

```powershell
& "$env:USERPROFILE\BMS\update_windows.bat" --offline
```

`--zurueck` nimmt das letzte Update zurück und spielt die vorherige Fassung wieder ein:

```powershell
& "$env:USERPROFILE\BMS\update_windows.bat" --zurueck
```

Dabei fragt das Werkzeug getrennt nach, ob auch die Datenbank auf den Stand vor dem Update
zurückgesetzt werden soll: „Datenbank auf den Stand vor dem Update zurücksetzen? Alle Änderungen
seit dem Update gehen verloren.“ Antworten Sie mit `N` oder der Eingabetaste, bleibt Ihre aktuelle
Datenbank unverändert und nur die Programmdateien gehen auf den vorherigen Stand zurück. Nur der
zusätzliche Schalter `--mit-datenbank` setzt die Datenbank ohne diese Rückfrage zurück.

Ihre installierte Version sehen Sie jederzeit unter Einstellungen → „Programmversion“ oder im Fuß
der Seitenleiste. Was sich in einer Version geändert hat, lesen Sie unter „Dokumentation“, Reiter
„Version“.

## Wenn etwas nicht klappt

| Was Sie sehen | Was hilft |
|---|---|
| Der Browser zeigt eine leere Seite | Die Oberfläche wurde nicht gebaut: Schritt 6 |
| Ein Befehl wird nicht gefunden, obwohl das Programm installiert ist | PowerShell schließen und neu öffnen, damit Windows neu installierte Programme findet. Hilft das nicht, den Rechner neu starten |
| „npm.ps1 kann nicht geladen werden“ (oder `codex.ps1`) | `npm.cmd` statt `npm` schreiben, wie in Schritt 6, und `codex.cmd` statt `codex` |
| `Get-FileHash` (Schritt 4c) oder `Expand-Archive` (Schritt 4d) wird nicht erkannt, oder es erscheint eine Meldung wie „…psm1 kann nicht geladen werden“ | PowerShell wurde aus einem anderen Programm heraus gestartet (etwa aus PowerShell 7). Das Fenster schließen und „Windows PowerShell“ über das Startmenü neu öffnen |
| `pip install` bricht mit einem Kompilierfehler ab | `py -3.12` benutzen, nicht Python 3.13 oder neuer |
| „Der Computer wurde durch Windows geschützt“ | „Weitere Informationen“, dann „Trotzdem ausführen“. Das passiert, wenn die Download-Markierung in Schritt 4 nicht entfernt wurde |
| „address already in use“ (unter Windows etwa `[Errno 10048] … nur jeweils einmal verwendet werden`) oder Port 8000 belegt | Das BMS läuft bereits. Browser auf `http://localhost:8000` richten oder erst mit `stop_windows.bat` beenden |
| KI-Läufe enden mit einem Anmeldefehler | Bei Claude den Zugangsschlüssel prüfen (Schritt 7): eine Zeile, kein `#` davor, vollständig kopiert. Danach das BMS neu starten. Bei ChatGPT soll `codex.cmd login status` in PowerShell `Logged in using ChatGPT` zeigen, sonst `codex.cmd login` wiederholen und den Lauf neu starten |
| Im „Task-Center“ steht, das Nutzungslimit Ihres ChatGPT-Abos sei erreicht | Es gelten die Grenzen Ihres Abos, das BMS setzt keine eigene Grenze je Lauf. Starten Sie den Lauf später erneut. Ein Tageslauf kann ein Plus-Konto schnell an die Grenze bringen |
| Sie möchten die KI wechseln, Claude oder ChatGPT | „Einstellungen“, Karte „KI“: die andere KI wählen. Ihr Programm muss vorher installiert und angemeldet sein (Schritt 3 und 7 für diese KI) |
| Es entsteht keine PDF-Datei | LibreOffice fehlt oder liegt nicht unter `C:\Program Files\LibreOffice` |
| Lebensläufe heißen `CV_Bewerber_…` | Im Profil steht noch kein Name. Tragen Sie ihn in der Karte „Identität und Suchstrategie“ ein und speichern Sie (Abschnitt „Ihr Profil: Identität und Suchstrategie“). Bearbeiten Sie `config/profil.md` von Hand, prüfen Sie, ob die Zeile `**Name:**` genau so geschrieben ist |
| Im BMS stehen Stellen, Mails oder ein Profil von „Benno Bewerbaer“, die Sie nicht angelegt haben | Das sind die Beispieldaten. Entfernen Sie sie in den „Einstellungen“ mit „Beispieldaten entfernen“ (Abschnitt „Zuerst: Beispieldaten entfernen“) |
| „Beispieldaten entfernen“ meldet, dass gerade eine Sicherung oder eine Aufgabe läuft | Einen Moment warten, bei einer Aufgabe bis sie im „Task-Center“ fertig ist, und noch einmal klicken. Es wurde nichts verändert |
| `Antwort: 404` beim Laden des Programmpakets, oder in der Auskunft steht `Not Found` | Zu dieser Version gibt es auf GitHub kein Programmpaket, oder es ist noch keine Version veröffentlicht. Prüfen Sie die Versionsnummer aus der Auskunft. Hilft das nicht, nehmen Sie den Ersatzweg mit einer ZIP-Datei von der Release-Seite |
| In der Auskunft steht `API rate limit exceeded`, oder das Update-Werkzeug meldet „GitHub begrenzt gerade die Anfragen.“ | GitHub erlaubt ohne Anmeldung nur 60 Anfragen je Stunde und IP-Adresse. In einem Firmennetz teilen sich oft viele Rechner eine Adresse. Versuchen Sie es in einer Stunde noch einmal, oder nehmen Sie den Ersatzweg mit einer ZIP-Datei |
| `Antwort: 000` oder eine Meldung von curl wie „Could not resolve host“ | Es besteht keine Verbindung zu GitHub. Prüfen Sie Ihre Internetverbindung. In einem Firmennetz kann der Zugriff gesperrt sein. Klappt es nicht, laden Sie die ZIP-Datei im Browser von der Release-Seite und nehmen den Ersatzweg |
| Die Prüfsumme aus Schritt 4 weicht von der Auskunft ab | Das Paket ist unvollständig oder beschädigt, etwa weil die Verbindung unterbrochen wurde. Löschen Sie die Datei und laden Sie sie einmal neu. Weicht die Prüfsumme wieder ab, laden Sie die ZIP-Datei im Browser von der Release-Seite (Ersatzweg) |
| Das Update-Werkzeug meldet „Online-Suche nicht möglich: …“ | Das ist kein Abbruch. Die Meldung nennt den Grund, zum Beispiel „Es besteht keine Verbindung zu GitHub.“ Das Werkzeug macht mit einer ZIP-Datei in „Downloads“ weiter, wenn dort eine liegt. Sonst laden Sie die neue `BMS_<Version>.zip` von der Release-Seite auf GitHub und legen sie dort ab |
| Update bricht mit „Das BMS läuft noch“ ab | Zuerst `stop_windows.bat` ausführen, dann das Update erneut starten |
| Update bricht mit einem Hinweis auf `npm`/Node.js ab | Node.js nachinstallieren (Schritt 3), danach das Update erneut starten. Es wurde nichts verändert |
| Update meldet „fehlgeschlagen, alle Änderungen wurden zurückgerollt“ | Die Meldung nennt den Sicherungsordner unter `data/updates/…`. Ihre vorherige Fassung läuft unverändert weiter, versuchen Sie das Update erneut oder melden Sie das Problem auf der Issues-Seite (Abschnitt „Hilfe“) |
| „Kein Update-Paket gefunden“ | Weder online noch in „Downloads“ lag ein Paket bereit. Der Grund der Online-Suche steht in der Meldung davor. Legen Sie die Datei `BMS_<Version>.zip` im Ordner „Downloads“ ab und versuchen Sie es erneut |

Nach jeder Änderung an Dateien im Programmordner starten Sie das BMS neu, damit es sie einliest.

## Was unter Windows eingeschränkt ist

Das BMS wird auf dem Mac entwickelt und dort täglich eingesetzt. Unter Windows funktioniert die
Verwaltung vollständig: Stellen, Firmen, Kontakte, Termine und Auswertungen. Die KI-Funktionen, also
Jobsuche, Firmenprüfung, Lebenslauf und Anschreiben, laufen unter Windows über dieselben Abläufe,
sind dort aber weniger erprobt als auf dem Mac. KI-Läufe, `stop_windows.bat` und die PDF-Erzeugung
sind unter Windows noch nicht auf echter Hardware erprobt. Mit ChatGPT als KI sind die KI-Läufe unter
Windows noch gar nicht erprobt, und die bevorzugte Sandbox von Codex braucht einmalig ein
Administrator-Setup. Endet ein Lauf mit einem Fehler, steht die
Meldung im Task-Center. Melden Sie sie vollständig auf der Issues-Seite (Abschnitt „Hilfe“), das hilft bei der Klärung.

Drei Dinge gibt es unter Windows nicht:

- den täglichen Lauf zu einer festen Uhrzeit. Unter Windows starten Sie ihn per Schaltfläche.
- die Aufgaben „Ansichten aktualisieren“, „Anschreiben Word + PDF erzeugen“ und „Coach-Site
  aktualisieren“. Sie melden unter Windows „Binary '/bin/zsh' nicht gefunden“. Der Tageslauf endet
  deshalb mit einem fehlgeschlagenen Schritt. Anschreiben entstehen trotzdem als Word- und
  PDF-Datei, wenn Sie sie über „Anschreiben erstellen“ anlegen.
- die mitgelieferten Hilfsskripte im Ordner `scripts`. Für den normalen Betrieb brauchen Sie sie
  nicht.

Die automatische Datensicherung (Abschnitt „Ihre Daten“) läuft unter Windows genauso wie auf dem
Mac. Nur das Hilfsskript `scripts/backup_db.sh` für eine zusätzliche manuelle Sicherung gibt es
ausschließlich auf dem Mac.

## Ihre Daten

Das BMS läuft vollständig auf Ihrem Rechner. Ihre Bewerbungen, Ihr Profil und Ihre E-Mails liegen
in der Datenbank `data/bewerbung.sqlite` im Programmordner, Ihre erzeugten Dokumente im Ordner
`outputs`. Der Herausgeber des BMS betreibt keinen Server für das Programm und erhält davon nichts.
Kontakt zu GitHub gibt es nur beim Laden des Programmpakets in der Installation und wenn Sie selbst
nach einer neuen Version suchen (Knopf „Nach Updates suchen“ in den Einstellungen oder das
Update-Werkzeug). GitHub erhält dabei die IP-Adresse Ihres Rechners und die Anfrage selbst, sonst
nichts. Mit `--offline` oder mit einer ZIP-Datei gibt es keinen Kontakt. Näheres steht unter
„Rechtliches“, Reiter „Datenschutz“. Die KI-Funktionen übermitteln Inhalte an den Anbieter der
gewählten KI, soweit sie für den jeweiligen Lauf nötig sind, und zwar über Ihr eigenes Konto: bei
Claude an Anthropic, bei ChatGPT an OpenAI.

Das BMS sichert Ihre Datenbank automatisch, solange es läuft: einmal täglich als ZIP-Datei im
Ordner `data/backups/auto`. Aufbewahrt werden die neueste Sicherung, alle der letzten 24 Stunden
sowie je eine der letzten 7 Tage und der letzten 4 Wochen. Ältere automatische Sicherungen
entfernt das BMS selbst. Unter „Einstellungen“, Karte „Datensicherung“, sehen Sie die letzte
Sicherung, ändern die Aufbewahrung und sichern auf Knopfdruck.

Diese Sicherungen liegen in Ihrem BMS-Ordner auf derselben Festplatte wie Ihre Arbeitskopie und
ersetzen keine externe Datensicherung. Nehmen Sie Ihren BMS-Ordner zusätzlich in Ihre reguläre
Datensicherung auf.

So spielen Sie eine Sicherung zurück:

1. Beenden Sie das BMS: Doppelklick auf `stop_windows.bat`.
2. Doppelklicken Sie in Ihrem BMS-Ordner auf `wiederherstellen_windows.bat`. Das Werkzeug zeigt Ihnen
   die vorhandenen Sicherungen, die neueste zuerst, mit Datum, Uhrzeit, Art und Größe.
3. Tippen Sie die Nummer der gewünschten Sicherung ein und bestätigen Sie die Rückfrage mit „j“.
   Mit Enter ohne Eingabe brechen Sie ab. Das Werkzeug prüft die Sicherung, bevor es etwas
   ändert, und legt zuerst eine Sicherung Ihres aktuellen Stands an.
4. Starten Sie das BMS wie gewohnt.

Gut zu wissen:

- **Es kommen nur die Datenbank-Daten zurück.** Alles, was Sie seit dem Zeitpunkt der Sicherung
  erfasst oder geändert haben, ist danach nicht mehr in der Datenbank. Ihre Dokumente in
  `outputs` und `data` bleiben unverändert. Dateien, die nach der Sicherung entstanden sind,
  gehören danach zu keiner Stelle mehr.
- **Rücknahme:** Ihr Stand vor dem Zurückspielen liegt als Sicherung „vor Wiederherstellung“ in
  `data/backups`. Starten Sie das Werkzeug noch einmal und wählen Sie diesen Eintrag, dann ist
  alles wieder wie vorher.
- **Welche Sicherungen erscheinen:** die automatischen aus `data/backups/auto`, die von Hand
  angelegten aus `data/backups` und die Einträge „vor Wiederherstellung“. Die Sicherungen, die ein
  Update anlegt, gehören nicht dazu. Ein Update nehmen Sie mit `--zurueck` zurück (Abschnitt
  „Aktualisierungen einspielen“).
- **Läuft das BMS noch,** bricht das Werkzeug ab und sagt es Ihnen. Beenden Sie das BMS und
  starten Sie das Werkzeug erneut.

Falls das Werkzeug nicht startet, geht es auch von Hand: Beenden Sie das BMS, entpacken Sie im
Ordner `data/backups/auto` die gewünschte ZIP-Datei (Rechtsklick und „Alle extrahieren“), benennen
Sie die vorhandene Datei `data/bewerbung.sqlite` um, statt sie zu löschen, etwa in
`bewerbung_alt.sqlite`, legen Sie die entpackte Datei `bewerbung.sqlite` in den Ordner `data` und
starten Sie das BMS.

## Hilfe

Bei Fragen zur Installation und bei Fehlern öffnen Sie auf der Seite
https://github.com/holgerdaube/BewerbungsMgmtSystem/issues ein neues Anliegen („Issue“). Dafür brauchen
Sie ein kostenloses GitHub-Konto. Nennen Sie dabei Ihr Betriebssystem, den Schritt, bei dem es hakt,
und den genauen Wortlaut der Fehlermeldung. Ein Bildschirmfoto hilft. Die Seite ist öffentlich:
Schreiben Sie keine Passwörter, Zugangsschlüssel oder persönlichen Daten hinein.

Für die tägliche Arbeit mit dem BMS finden Sie im Programmordner unter `docs/ANLEITUNG.md` eine
ausführliche Bedienungsanleitung. Alle Anleitungen lesen Sie auch im BMS selbst: In der Seitenleiste
öffnet „Dokumentation“ sie in Reitern, darunter diese Installationsanleitung („Installation &
Updates“), die Anleitung und eine Übersicht der Funktionen.
