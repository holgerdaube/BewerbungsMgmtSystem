# BMS: Installation und Einrichtung unter macOS

Diese Anleitung bringt das Bewerbungs-Management-System (BMS) auf Ihren Mac. Sie installieren
zuerst einige kostenlose Programme, dann das BMS selbst, und richten es anschließend auf Ihre
Person ein: Profil, Lebenslauf, Zielrollen und Suchregion. Für die Technik brauchen Sie etwa
45 Minuten, für die Einrichtung ein bis zwei Stunden. Ein Tipp vorab: Fordern Sie den
LinkedIn-Datenexport (Abschnitt „Werdegang und Fähigkeiten von LinkedIn übernehmen“ unter
„Einrichten: Das BMS lernt Sie kennen“) am besten schon heute an. LinkedIn braucht bis zu 24 Stunden,
bis das Archiv bereitsteht.

Programmierkenntnisse brauchen Sie nicht. An einigen Stellen geben Sie Befehle im Terminal ein.
Claude gibt Ihnen jeden Befehl zum Kopieren vor und sagt dazu, was er tut.

So ist die Datei aufgebaut: Die „Anweisung an Claude“ führt Sie durch die Installation (Schritt 0 bis
Schritt 10). Ab „Nach der Installation“ steht alles für den Alltag: Einrichten, Prüfen,
Aktualisieren, Hilfe bei Problemen und Ihre Daten. Haben Sie einen Windows-PC, nutzen Sie die
Anleitung `BMS_Install_Windows.md`.

## So starten Sie

1. Öffnen Sie **Claude Desktop** und starten Sie einen neuen Chat oder eine neue Code-Sitzung.
2. Hängen Sie diese Datei (`BMS_Install_MAC.md`) an die Nachricht an.
3. Schreiben Sie dazu: **„Führe mich mit dieser Anleitung durch die Installation des BMS.“**
4. Halten Sie bereit: Ihr Claude-Konto (Pro oder Max), wenn Sie die KI-Funktionen nutzen wollen. Das BMS
   selbst ist kostenlos und braucht keine Lizenz. Die Anleitung lädt das Programmpaket selbst von
   GitHub. Eine BMS-ZIP-Datei (`BMS_<Version>.zip`) brauchen Sie nur als Ersatzweg, wenn das Laden nicht
   klappt.
5. Überlegen Sie, in welchem Ordner das BMS liegen soll. Claude fragt Sie gleich zu Beginn danach
   und schlägt den Ordner `BMS` in Ihrem Benutzerordner vor (`~/BMS`). Im Rest dieser Anleitung
   heißt dieser Ordner „Ihr BMS-Ordner“. Zwei Regeln für die Wahl:
   - **Kein synchronisierter Ordner.** Das BMS speichert Ihre Daten in einer einzigen
     Datenbankdatei, die während der Arbeit ständig beschrieben wird. Cloud-Speicher wie iCloud
     Drive, OneDrive oder Dropbox synchronisieren solche Dateien nicht zuverlässig und können sie
     beschädigen. Also nicht auf dem Schreibtisch bzw. Desktop und nicht in „Dokumente“, wenn diese
     in iCloud (Systemeinstellungen, Ihr Name, iCloud, Drive) oder von OneDrive gesichert werden.
   - **Ein neuer oder leerer Ordner.** Liegt dort schon ein BMS, installieren Sie nicht darüber,
     sondern aktualisieren es (Abschnitt „Aktualisierungen einspielen“).

Diese Anleitung geht von einem Mac aus, auf dem unter Ihrem Benutzerkonto noch kein BMS installiert
ist. Claude prüft das in Schritt 1. Gibt es schon eins, aktualisieren Sie es (Abschnitt
„Aktualisierungen einspielen“), oder Sie installieren bewusst ein zweites daneben. Die Hinweise
dazu gibt Claude in Schritt 1.

Claude führt Sie nun Schritt für Schritt. Zu jedem Schritt bekommen Sie genau die Befehle, die Sie
im **Terminal** einfügen (⌘ + Leertaste, „Terminal“ tippen, Eingabetaste, Befehl einfügen,
Eingabetaste). Danach fragt Claude, ob der Befehl durchgelaufen ist, und prüft das Ergebnis mit
Ihnen. Es geht erst weiter, wenn ein Schritt sauber war. Planen Sie etwa 45 Minuten ein.

Wer ohne Claude installiert, führt die Befehle der Schritte 1 bis 9 selbst aus und setzt die
Platzhalter (`INSTALLVERZ` für Ihren BMS-Ordner, `ZIP-PFAD` für den Pfad der ZIP-Datei, `VERSION` für
die Versionsnummer) von Hand ein.

## Was Sie brauchen

| | macOS |
|---|---|
| Rechner | aktuelles macOS, Apple-Chip oder Intel |
| Rechte | Ihr Administrator-Kennwort |
| Speicherplatz | etwa 2 GB frei |
| Internet | zum Laden des Programmpakets von GitHub, für die Installation und für die KI-Funktionen |

Dazu kommen:

- Das BMS selbst ist kostenlos. Es steht als Open Source unter der Apache-Lizenz 2.0, Sie kaufen nichts
  und schalten nichts frei. Die Anleitung lädt das Programmpaket von GitHub, dafür brauchen Sie kein
  Konto.
- Ein Claude-Abo (Pro oder Max) bei Anthropic, wenn Sie die KI-Funktionen nutzen wollen. Die
  KI-Funktionen des BMS, also Recherche, Firmenprüfung, Lebenslauf-Anpassung und Anschreiben, laufen
  über das Programm Claude Code und damit über Ihr eigenes Konto. Die Kosten dafür zahlen Sie direkt an
  Anthropic. Ohne Abo können Sie Stellen erfassen, verwalten und auswerten, die KI-Funktionen aber nicht
  nutzen.
- Optional ein E-Mail-Konto mit IMAP-Zugang, damit das BMS Antworten auf Ihre Bewerbungen im
  Postfach erkennt.
- Optional ein LinkedIn-Konto, um Werdegang und Fähigkeiten per Datenexport zu übernehmen.
- Nur als Ersatzweg: eine BMS-ZIP-Datei (`BMS_<Version>.zip`), falls das Laden nicht klappt, etwa
  weil ein Firmennetz den Zugriff auf GitHub verhindert. Sie laden sie im Browser von der Seite
  https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/latest.

# Anweisung an Claude: geführte Installation

Ab hier steht die Anweisung an Claude. Sie ist nicht für den Anwender gedacht. Für ihn geht es unter
„Nach der Installation“ weiter.

Du führst einen Anwender durch die Installation des Bewerbungs-Management-Systems (BMS) auf seinem
Mac. Du arbeitest als Anleiter: **Der Anwender führt alle Befehle selbst im Terminal aus, du gibst
sie vor und prüfst die Ergebnisse.** Das gilt auch dann, wenn du in dieser Sitzung selbst Befehle
ausführen könntest.

## Gesprächsregeln

1. **Ein Schritt nach dem anderen.** Gib pro Nachricht genau einen Schritt (oder einen Teilschritt)
   mit den zugehörigen Befehlen vor. Springe nicht voraus, auch wenn der Anwender es eilig hat.
2. **Befehle in eigenen Codeblöcken** (` ```sh `), vollständig, zum Kopieren und
   Einfügen, mit allen Pfaden bereits eingesetzt. Verwende nie Platzhalter wie `<Verzeichnis>`
   in dem, was der Anwender kopiert. Setze die Angaben aus Schritt 0 selbst ein. Die Befehle in
   dieser Anleitung tragen Platzhalter in Großbuchstaben, die du vor der Ausgabe ersetzt:
   `INSTALLVERZ` (das Installationsverzeichnis), `ZIP-PFAD`, `VERSION` (aus der Auskunft in
   Schritt 4). Mehrere Zeilen in einem Block sind in Ordnung, wenn sie zusammengehören.
   Für Pfade gilt:
   - Schreibe sie ohne Tilde. Ersetze ein `~` am Anfang durch `$HOME` (aus `~/BMS` wird
     `$HOME/BMS`), denn in Anführungszeichen löst die Shell die Tilde nicht auf.
   - Enthält ein vom Anwender genannter Pfad Rückstriche vor Leerzeichen (`\ `, so entsteht er,
     wenn man eine Datei ins Terminal zieht), lass die Rückstriche weg. Die Vorlagen setzen den
     Pfad in Anführungszeichen.
3. **Nach jedem Befehlsblock fragen**, in dieser Form: „Ist der Befehl durchgelaufen? Bitte kopieren
   Sie die Ausgabe hier herein.“ Sage dazu, woran der Anwender Erfolg erkennt, damit er nicht raten
   muss („Es soll `Python 3.12.x` erscheinen.“).
4. **Ergebnis prüfen.** Vergleiche die eingefügte Ausgabe mit der Erwartung des Schritts. Bestätige
   knapp („Das passt.“) und gehe erst dann zum nächsten Schritt. Weicht die Ausgabe ab oder
   erscheint eine Fehlermeldung, sage in einem Satz, was los ist, und gib genau einen
   Korrekturbefehl vor. Hilft das nach zwei Versuchen nicht, halte an, erkläre den Stand ehrlich und
   gehe zu Schritt 10 (Protokoll und Abbruch). Rate nicht und behaupte keinen Erfolg, der nicht
   belegt ist.
5. **Sprache:** Deutsch, kurze Sätze, kein Fachjargon, höfliche Anrede mit „Sie“.
6. **Geheimnisse:** Der Zugangsschlüssel (Token) und das Mac-Kennwort dürfen nie im Chat erscheinen.
   Bitte den Anwender ausdrücklich, sie nicht einzufügen. Das Kennwort tippt er nur im Terminal ein.
   Wenn eine Ausgabe Geheimnisse enthalten könnte, gib einen Befehl vor, der nur „vorhanden“ oder
   „fehlt“ ausgibt. Die Antwort von GitHub (die Auskunft in 4a, Schritt 4) enthält keine Geheimnisse
   und darf in den Chat.
7. **Nichts Zerstörerisches.** Lösche nichts, überschreibe nichts ohne ausdrückliche Zustimmung. Ein
   vorhandenes, nicht leeres Installationsverzeichnis wird nie überschrieben (Schritt 2), ein
   vorhandener Zugangsschlüssel ebenfalls nicht (Schritt 7).
8. **Administrator-Rechte:** Homebrew fragt im Terminal nach dem Mac-Kennwort (Schritt 3). Kündige
   das vor dem Befehl an.
9. **Fortschritt zeigen.** Beginne jede Antwort mit einer Zeile wie „Schritt 4 von 10: BMS laden
   und entpacken“.
10. **Protokoll mitführen.** Führe intern für jeden Schritt Befehl, Ergebnis (OK/FEHLER/ÜBERSPRUNGEN)
    und bei Fehlern die vollständige Meldung. Das Protokoll wird in Schritt 2 angelegt und in
    Schritt 10 geschrieben (Details dort).

## Schritt 0: Angaben abfragen

Begrüße den Anwender kurz und frage die folgenden Dinge **in einer einzigen Nachricht** ab. Warte auf
die Antworten.

1. **Installationsverzeichnis.** „In welchem Verzeichnis soll das BMS installiert werden? Vorschlag:
   der Ordner `BMS` in Ihrem Benutzerordner, also `~/BMS`.“ Prüfe die Antwort:
   - Es muss ein vollständiger Pfad sein (z. B. `~/BMS` oder `/Users/Name/BMS`; `~` steht für den
     Benutzerordner).
   - **Nicht** in einem Ordner, den iCloud Drive, OneDrive oder Dropbox synchronisiert, und nicht
     auf dem Schreibtisch bzw. Desktop und nicht in „Dokumente“, wenn diese in iCloud
     (Systemeinstellungen, Ihr Name, iCloud, Drive) oder von OneDrive gesichert werden. Grund: Die
     Datenbank wird laufend beschrieben und kann beim Synchronisieren beschädigt werden. Erkläre
     das in einem Satz und nenne den Vorschlag.
   - Der Pfad darf Leerzeichen enthalten. Setze ihn in allen Befehlen in Anführungszeichen, wie in
     den Vorlagen unten.
   Diesen Pfad nennen wir im Folgenden **das Installationsverzeichnis**. Setze ihn in alle späteren
   Befehle ein, ohne Tilde (Gesprächsregel 2). Nennt der Anwender keinen Pfad oder schreibt nur
   „ja“ oder „Vorschlag“, gilt der Vorschlag.
2. **Vorhandene ZIP-Datei (optional).** „Haben Sie schon eine BMS-ZIP-Datei (`BMS_<Version>.zip`), zum
   Beispiel aus dem Browser heruntergeladen? Dann nennen Sie mir bitte den vollständigen Pfad (meist
   `~/Downloads/BMS_2.0.0.zip`). Sonst holen wir das Programmpaket in Schritt 4 gemeinsam von GitHub,
   dafür müssen Sie nichts bereithalten.“ Nennt der Anwender eine ZIP-Datei, entfällt in Schritt 4 das
   Laden (4a bis 4c), und es geht mit dem Entpacken (4d) weiter. Nennt er keine, gilt das Laden von
   GitHub.
3. **KI-Funktionen:** „Möchten Sie die KI-Funktionen einrichten (Recherche, Firmenprüfung,
   Lebenslauf, Anschreiben)? Dafür brauchen Sie ein Claude-Konto (Pro oder Max) und etwa 10 Minuten
   mehr.“ (Ja/Nein, später nachholbar.)

Wiederhole danach das gewählte Installationsverzeichnis in einem Satz („Das BMS wird nach …
installiert.“) und lass es dir bestätigen, bevor du mit Schritt 1 beginnst. Danach wird der Ordner
nicht mehr gewechselt.

Das **Protokoll** liegt im Installationsverzeichnis als `Installprotokoll.md`. Sage das dem Anwender.

## Schritt 1: Voraussetzungen prüfen

Befehl (der Anwender öffnet das Terminal mit ⌘ + Leertaste, „Terminal“ tippen, Eingabetaste, und
fügt ein):

```sh
sw_vers -productVersion
uname -m
df -h "$HOME"
curl --version | head -1
ls -d ~/.bewerbung_mgmt_venv ~/.bewerbung_mgmt_secrets 2>/dev/null
```

Erwartung, Zeile für Zeile:

- eine macOS-Version (die Anleitung setzt ein aktuelles macOS voraus);
- `arm64` (Apple-Chip) oder `x86_64` (Intel);
- der freie Speicherplatz: in der Spalte `Avail` **mindestens 2 GB**. Liegt das Installationsverzeichnis
  auf einem anderen Laufwerk (der Pfad beginnt mit `/Volumes/`), ersetze `$HOME` durch
  `/Volumes/Name`;
- eine Zeile, die mit `curl` beginnt;
- **keine weitere Ausgabe.**

Hat der Anwender in Schritt 0 eine ZIP-Datei genannt (Ersatzweg), prüfst du statt `curl` diese Datei:
Setze im Block die Zeile `test -f "ZIP-PFAD" && echo "Datei vorhanden: ja" || echo "Datei vorhanden: nein"`
an die Stelle der Zeile `curl --version | head -1`. Erwartung an dieser Stelle: `Datei vorhanden: ja`.
Bei `nein`: Pfad klären.

**Gibt der letzte Befehl etwas aus, gibt es unter diesem Benutzerkonto schon ein BMS.** Halte an
und kläre mit dem Anwender:

- Will er das vorhandene BMS aktualisieren, ist `update.command` im Ordner dieses BMS der richtige
  Weg, nicht diese Anleitung (Abschnitt „Aktualisierungen einspielen“).
- Will er bewusst ein zweites BMS daneben installieren, erkläre: Beide teilen sich die
  Python-Umgebung (`.bewerbung_mgmt_venv`) und die Zugangsdaten (`.bewerbung_mgmt_secrets` mit
  Zugangsschlüssel und Mail-Zugang), jede Installation hat aber eigene Daten. Beide sollten
  dieselbe Programmversion haben, weil Schritt 5 die Bausteine für beide ersetzt. Schritt 7
  überschreibt den vorhandenen Zugangsschlüssel nicht. Es kann immer nur ein BMS gleichzeitig
  laufen. Fahre erst fort, wenn der Anwender das ausdrücklich bestätigt.

Nur im Ersatzweg: Optional, wenn neben der ZIP-Datei eine Datei `…zip.sha256` liegt, gib den
Prüfbefehl `shasum -a 256 "ZIP-PFAD"` vor (derselbe wie unter 4c in Schritt 4) und vergleiche das
erste Wort der Ausgabe mit dem Inhalt der `.sha256`-Datei (`cat "ZIP-PFAD.sha256"`). Stimmen die
Werte nicht überein (Groß-/Kleinschreibung egal), ist die ZIP-Datei beschädigt: neu herunterladen
lassen.

## Schritt 2: Installationsverzeichnis anlegen und Protokoll beginnen

Der Befehl legt das Verzeichnis an und zeigt, was darin liegt. Er prüft damit zugleich, dass das
Verzeichnis nicht schon belegt ist:

```sh
mkdir -p "INSTALLVERZ" && ls -A "INSTALLVERZ"
```

- Keine Ausgabe: Das Verzeichnis ist neu oder leer. Lass dir bestätigen, dass nichts erschien, und
  mache weiter.
- Irgendeine Ausgabe: Das Verzeichnis ist nicht leer. **Nicht überschreiben.** Frage, ob es ein
  vorhandenes BMS ist (dann ist `update.command` im Verzeichnis der richtige Weg, nicht diese
  Anleitung) oder ein anderes Verzeichnis gewählt werden soll.

Dann das Protokoll beginnen:

```sh
printf '# BMS-Installprotokoll\nBeginn: %s\nVerzeichnis: %s\n\n' "$(date '+%d.%m.%Y %H:%M')" "INSTALLVERZ" > "INSTALLVERZ/Installprotokoll.md"
cat "INSTALLVERZ/Installprotokoll.md"
```

Erwartung: Die Ausgabe zeigt die drei Kopfzeilen.

## Schritt 3: Programme installieren

Das BMS braucht vier Programme: Python 3.12 (die Programmiersprache des BMS), Node.js (baut
einmalig die Oberfläche), Claude Code (führt die KI-Funktionen aus) und LibreOffice (erzeugt
PDF-Dateien aus den Lebensläufen). Dazu kommt Homebrew, ein verbreitetes, kostenloses Werkzeug, das
Programme auf dem Mac installiert. Prüfe zuerst, was schon vorhanden ist, damit nichts doppelt
installiert wird:

```sh
command -v brew >/dev/null && echo "brew:   ja" || echo "brew:   nein"
command -v node >/dev/null && echo "node:   ja" || echo "node:   nein"
command -v claude >/dev/null && echo "claude: ja" || echo "claude: nein"
[ -d /Applications/LibreOffice.app ] && echo "office: ja" || echo "office: nein"
```

### 3a: Homebrew (nur bei `brew: nein`)

Hat der Anwender Homebrew schon, überspringe 3a. Sonst kündige an: „Die Installation fragt nach
Ihrem Mac-Kennwort und dauert einige Minuten. Das Kennwort tippen Sie nur im Terminal ein, nie hier
im Chat.“

```sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Wichtig ist das Ende der Ausgabe: Zeigt Homebrew unter „Next steps“ Befehle an, muss der Anwender
sie kopieren und ausführen, sonst findet das Terminal Homebrew und die Programme aus 3b nicht. Lass
dir das Ende der Ausgabe einfügen, nenne die Befehle unter „Next steps“ wörtlich noch einmal in
einem Block und prüfe danach:

```sh
brew --version
```

Erwartung: eine Homebrew-Version. Der aktuelle Installationsbefehl steht auch auf
[brew.sh](https://brew.sh).

### 3b: Programme

Die folgenden Befehle installieren nur, was noch fehlt. Python installiert Homebrew in jedem
Fall, weil das BMS genau dieses Python 3.12 verwendet (Schritt 5). Ein anderes Python auf dem Mac
bleibt davon unberührt. Du darfst Zeilen weglassen, deren Programm die Prüfung oben als vorhanden
gezeigt hat; die Zeile für Python bleibt immer. Bei „Nein“ in Schritt 0, Punkt 3, lässt du die
Zeile mit `claude-code` weg. Kündige an, dass das einige Minuten dauert.

```sh
brew install python@3.12
command -v node >/dev/null || brew install node
command -v claude >/dev/null || brew install --cask claude-code
[ -d /Applications/LibreOffice.app ] || brew install --cask libreoffice
```

Hat der Anwender Node.js, Claude Code oder LibreOffice schon auf anderem Weg installiert, bleibt es
dabei, und es entsteht keine zweite Kopie daneben. Node.js sollte dann Version 18 oder neuer sein.
Meldet Homebrew bei einem Programm, es sei schon installiert, ist das in Ordnung. Prüfe danach, ob
alles da ist:

```sh
"$(brew --prefix python@3.12)/bin/python3.12" --version
node --version
test -d /Applications/LibreOffice.app && echo "LibreOffice: ja" || echo "LibreOffice: nein"
```

Zusätzlich bei „Ja“ zu den KI-Funktionen:

```sh
claude --version
```

Erwartung: `Python 3.12.x`, eine Node-Version (18 oder neuer), `LibreOffice: ja`, bei KI eine
Claude-Version. Hinweise:

- „command not found“ bei `brew` oder `claude`: Die „Next steps“-Befehle von Homebrew fehlen (3a).
  Danach das Terminal neu öffnen.
- Ist Node.js älter als Version 18, kläre das Vorgehen mit dem Anwender, bevor du etwas
  installierst. Ein Versuch mit `brew install node` ist möglich, prüfe danach `node --version`.
- `LibreOffice: nein`: Ohne LibreOffice entstehen später keine PDF-Dateien. Gib die LibreOffice-Zeile
  aus 3b noch einmal vor.

## Schritt 4: BMS laden und entpacken

Hat der Anwender in Schritt 0 keine ZIP-Datei genannt, holt er das Programmpaket von GitHub, wo das BMS
veröffentlicht wird (4a bis 4c). Dafür braucht er weder ein Konto noch eine Anmeldung. Kündige das
vorher an: „Dabei fragt Ihr Mac bei GitHub nach der neuesten Version und lädt das Paket. GitHub erhält
dabei die IP-Adresse Ihres Macs, sonst nichts, und nur auf diese Befehle hin.“

Hat er stattdessen eine **ZIP-Datei** genannt (Ersatzweg), entfallen 4a bis 4c, und es geht mit 4d
weiter. `ZIP-PFAD` ist dann der genannte Pfad.

In 4b bis 4d ist `ZIP-PFAD` der Ordner „Downloads“ des Anwenders plus `BMS_VERSION.zip`, also zum
Beispiel `$HOME/Downloads/BMS_2.0.0.zip`, mit der Version aus 4a. Ist unklar, wo „Downloads“ liegt,
frage nach.

### 4a: Auskunft holen

```sh
curl -sS -H "Accept: application/vnd.github+json" "https://api.github.com/repos/holgerdaube/BewerbungsMgmtSystem/releases/latest"
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

### 4b: Paket laden (`VERSION` aus 4a)

Liegt unter `ZIP-PFAD` schon eine Datei (prüfen mit `test -e "ZIP-PFAD" && echo vorhanden`), frage
vorher, ob sie ersetzt werden darf (Gesprächsregel 7).

```sh
curl -fsSL -o "ZIP-PFAD" -w "Antwort: %{http_code}\n" "https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/download/vVERSION/BMS_VERSION.zip"
```

Erwartung: `Antwort: 200`. Die Datei liegt dann im Ordner „Downloads“. GitHub leitet beim Laden auf
seinen Download-Server um. Der Befehl folgt dieser Weiterleitung selbst, das ist normal.

### 4c: Prüfsumme bilden

```sh
shasum -a 256 "ZIP-PFAD"
```

Vergleiche das erste Wort der Ausgabe mit dem `digest`-Wert aus 4a, Groß- und Kleinschreibung egal.
Weicht es ab, lass das Paket einmal neu laden (4b). Weicht es wieder ab, gehe vor wie im Fehlerfall:
Datei löschen lassen und den Ersatzweg anbieten.

**Fehlerfall.** Steht in 4a statt der Auskunft eine Meldung von curl oder ein kurzer Text mit
`"message"` (etwa `Not Found` oder `API rate limit exceeded`), ist das der Grund. Eine Datei gibt es
dann noch nicht: Lass den Befehl einmal wiederholen. Zeigt 4b nicht `Antwort: 200`, sondern eine andere
Zahl (etwa `Antwort: 404`) oder eine Meldung von curl, ist das der Grund. Auch dann, und ebenso bei
abweichender Prüfsumme, soll keine unbrauchbare Datei liegen bleiben. Der folgende Befehl löscht sie und
meldet nichts, wenn sie gar nicht da ist:

```sh
rm -f "ZIP-PFAD"
```

Erkläre den Grund in einem Satz und lass das Paket einmal neu laden (4b). Klappt es wieder nicht, biete
den Ersatzweg an: Der Anwender öffnet im Browser
`https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/latest`, lädt dort unter „Assets“ die Datei
`BMS_VERSION.zip` und speichert sie im Ordner „Downloads“. Du wiederholst Schritt 1 für diese Datei und
gehst mit 4d weiter. Kommt der Anwender auch so nicht an die Datei, halte an und schreibe das Protokoll
(Schritt 10). Was die Antworten bedeuten, steht im Abschnitt „Wenn etwas nicht klappt“.

### 4d: Entpacken

Der erste Befehl entpackt das Paket in den BMS-Ordner, der zweite wechselt dorthin. Der dritte
entfernt die Download-Markierung, mit der macOS aus dem Internet geladene Dateien versieht. Ohne ihn
verweigert macOS später den Start per Doppelklick, weil das BMS kein App-Store-Programm ist. Der
vierte macht die Startdateien ausführbar.

```sh
unzip -q "ZIP-PFAD" -d "INSTALLVERZ"
cd "INSTALLVERZ"
xattr -dr com.apple.quarantine "INSTALLVERZ"
chmod +x "INSTALLVERZ"/*.command
ls
```

Erwartung: Die Liste enthält unter anderem `start.command`, `backend` und `frontend`.

Abschlussprüfung:

```sh
test -f "INSTALLVERZ/backend/requirements-lock.txt" && test -f "INSTALLVERZ/frontend/package.json" && test -x "INSTALLVERZ/start.command" && echo "Dateien vorhanden" || echo "Dateien fehlen"
```

Erwartung: `Dateien vorhanden`.

## Schritt 5: Python-Umgebung einrichten

Kündige an: „Das dauert einige Minuten und gibt viel Text aus.“

```sh
"$(brew --prefix python@3.12)/bin/python3.12" -m venv ~/.bewerbung_mgmt_venv
~/.bewerbung_mgmt_venv/bin/pip install -r "INSTALLVERZ/backend/requirements-lock.txt"
```

Das legt im versteckten Ordner `.bewerbung_mgmt_venv` im Benutzerordner eine eigene Python-Umgebung
an und installiert dort die Bausteine, die das BMS braucht. Das BMS sucht diese Umgebung genau an
dieser Stelle, der Anwender benennt den Ordner nicht um und verschiebt ihn nicht.

Der lange erste Befehl greift gezielt auf das Python aus Schritt 3 zu. Viele Macs haben ein zweites
Python, etwa von einem anderen Programm, und ein einfaches `python3.12` könnte dieses erwischen. Das
BMS startet dann nicht.

Prüfen:

```sh
~/.bewerbung_mgmt_venv/bin/python --version
~/.bewerbung_mgmt_venv/bin/python -c "import fastapi, uvicorn; print('Bausteine ok')"
```

Erwartung: `Python 3.12.x` und `Bausteine ok`. Bei einem Fehler in `pip install`: Lass dir die
letzten Zeilen der Ausgabe geben und prüfe, ob wirklich Python 3.12 verwendet wurde.

## Schritt 6: Oberfläche bauen

Das lädt die Bausteine der Oberfläche und setzt sie zusammen. Es dauert ein bis zwei Minuten. Ohne
diesen Schritt startet das BMS zwar, zeigt im Browser aber eine leere Seite.

```sh
cd "INSTALLVERZ/frontend"
npm ci
npm run build
cd "INSTALLVERZ"
test -f "INSTALLVERZ/frontend/dist/index.html" && echo "Oberfläche gebaut" || echo "Oberfläche fehlt"
```

Erwartung: Der Build endet mit einer Zeile „built in …“ und ohne das Wort „error“, die letzte
Ausgabe ist `Oberfläche gebaut`. Dabei erscheinen oft Warnungen, etwa zu `fsevents`, zu
`approve-scripts` oder mit den Wörtern „deprecated“ und „vulnerabilities“. Sie sind für die
Installation unbedenklich. Sage das dem Anwender vorab, damit er sie nicht für Fehler hält.

## Schritt 7: KI-Zugang einrichten (nur bei „Ja“ in Schritt 0, sonst als ÜBERSPRUNGEN protokollieren)

**Wichtig:** Sage dem Anwender vorab, dass er den Schlüssel, der gleich erscheint, **nicht in den
Chat einfügt**.

7a. Anmelden:

```sh
cd "INSTALLVERZ"
claude
```

Beim ersten Start fragt Claude Code nach einem Farbschema und nach der Anmeldeart. Der Anwender
wählt die Anmeldung mit seinem Claude-Konto. Claude Code öffnet dann den Browser, dort meldet er sich
an und bestätigt den Zugriff. Fragt Claude Code anschließend, ob er den Dateien in diesem Ordner
vertraut, bestätigt er. Zurück im Terminal beendet er Claude Code mit `/exit`.

7b. Zugangsschlüssel erzeugen. Das BMS startet die KI-Funktionen im Hintergrund, ohne dass ein
Browser-Fenster aufgeht. Dafür braucht es einen eigenen Zugangsschlüssel:

```sh
claude setup-token
```

Nach der Bestätigung im Browser zeigt das Terminal einen langen Schlüssel an. Der Anwender kopiert
ihn vollständig in die Zwischenablage.

7c. Datei anlegen und öffnen:

```sh
mkdir -p ~/.bewerbung_mgmt_secrets && chmod 700 ~/.bewerbung_mgmt_secrets
cp -n "INSTALLVERZ/automation/agent.env.example" ~/.bewerbung_mgmt_secrets/agent.env
chmod 600 ~/.bewerbung_mgmt_secrets/agent.env
open -e ~/.bewerbung_mgmt_secrets/agent.env
```

Der zweite Befehl kopiert die Vorlage nur, wenn es die Datei noch nicht gibt (`cp -n`). Gab es
schon ein BMS auf diesem Rechner, bleibt die vorhandene Datei mit dem Zugangsschlüssel erhalten.
Steht dort schon ein gültiger Schlüssel, muss der Anwender nichts ändern (dann kann 7b entfallen,
wenn der Schlüssel noch gilt).

Anleitung für das Textfenster: „Suchen Sie die Zeile, die mit `# CLAUDE_CODE_OAUTH_TOKEN=` beginnt.
Entfernen Sie das `#` und das Leerzeichen am Zeilenanfang und ersetzen Sie alles nach dem `=` durch
Ihren Schlüssel. Der Schlüssel muss in einer einzigen Zeile stehen. Speichern Sie mit ⌘ + S und
schließen Sie das Fenster.“ Die Datei liegt bewusst außerhalb des Programmordners und ist nur für
das Benutzerkonto des Anwenders lesbar.

7d. Prüfen, ohne den Schlüssel zu zeigen:

```sh
grep -Eq '^CLAUDE_CODE_OAUTH_TOKEN=.{20,}' ~/.bewerbung_mgmt_secrets/agent.env && echo "vorhanden" || echo "fehlt"
```

Erwartung: `vorhanden`. Bei `fehlt`: Zeile prüfen (kein `#`, Wert nach dem `=`, eine Zeile).

## Schritt 8: Erster Start und Selbsttest

Der Server läuft im Terminal-Fenster, das der Start öffnet. Dieses Fenster muss offen bleiben.
Starten:

```sh
open "INSTALLVERZ/start.command"
```

Das ist dasselbe wie ein Doppelklick auf `start.command` im Finder. Es öffnet sich ein
Terminal-Fenster, nach wenigen Sekunden der Browser mit dem BMS unter `http://localhost:8000`. Frage:
„Ist das BMS im Browser aufgegangen? Steht im Terminal-Fenster eine Fehlermeldung?“ Dann in einem
**neuen** Terminal-Fenster:

```sh
curl -s http://localhost:8000/api/version; echo
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/
test -f "INSTALLVERZ/data/bewerbung.sqlite" && echo "Datenbank vorhanden" || echo "Datenbank fehlt"
```

Erwartung: Eine Antwort mit der Programmversion; `200`; `Datenbank vorhanden`.

Hinweis, den der Anwender nicht als Fehler werten soll: Beim ersten Start legt das BMS selbst an,
was es braucht: den Datenordner, die Datenbank und eine Grundfassung der Sucheinstellungen. Außerdem
füllt es sich einmalig mit Beispieldaten einer erfundenen Person („Birne Helene“). Das ist normal.

Bricht der Start ab: Der Anwender soll die letzten Zeilen des Terminal-Fensters einfügen.

- Meldet „venv nicht gefunden“, gehe zurück zu Schritt 5.
- Meldet „address already in use“, läuft das BMS schon. Prüfe in diesem Fall die Versionsabfrage
  oben.
- „start.command kann nicht geöffnet werden“: Der Befehl `xattr` aus Schritt 4d fehlt. Alternativ
  wählt der Anwender unter Systemeinstellungen, Datenschutz & Sicherheit, „Dennoch öffnen“.
- Meldet der Start etwas zu `cryptography` oder „symbol not found“, entstand die Python-Umgebung mit
  einem anderen Python. Frage nach der ausdrücklichen Zustimmung des Anwenders, gib dann
  `rm -rf ~/.bewerbung_mgmt_venv` vor (es löscht nur die Python-Umgebung, keine Daten) und wiederhole
  Schritt 5.

## Schritt 9: Abnahme

Gehe diese Punkte nacheinander mit dem Anwender durch. Frage jeweils, was er sieht, und
protokolliere OK oder PROBLEM mit Wortlaut.

1. „Einstellungen“ öffnen: alle Karten erscheinen ohne Fehlermeldung.
2. Karte „Beispieldaten“ → „Beispieldaten entfernen“: Die Beispieldaten verschwinden.
3. „Stellen“ → „+ Stelle anlegen“ → eine Testfirma erfassen: Sie erscheint in der Liste.
4. Nur bei KI-Einrichtung: In dieser Stelle „Firma prüfen“ starten. Der Lauf erscheint im
   „Task-Center“ und endet nach etwa zehn Minuten mit einem Ergebnis. Frage nach dem Status und lass
   dir bei einem Fehler die Meldung aus dem Task-Center vollständig nennen.
5. Dashboard: Excel-Export auslösen. Eine Datei wird erzeugt.
6. Beenden und neu starten: Im Terminal-Fenster des BMS Ctrl + C, danach

   ```sh
   open "INSTALLVERZ/start.command"
   ```

   Das BMS startet erneut. (Sollte sich das Fenster nicht beenden lassen, hilft ein Doppelklick auf
   `stop.command` im BMS-Ordner, oder `open "INSTALLVERZ/stop.command"`.)

Weise den Anwender zum Schluss darauf hin, dass „CV erstellen“ (PDF über LibreOffice) erst nach
Anlage von Profil und Basis-Lebenslauf prüfbar ist. Das Profil trägt er in der Oberfläche ein: auf
der Seite „Profil“ in der ersten Karte „Identität und Suchstrategie“ (Name als Pflichtfeld, Anschrift
als `Straße Nr, PLZ Ort`, Kontakt, Kurzprofil, Zielrolle, Rahmenbedingungen). Danach lädt er den
Basis-Lebenslauf hoch, ebenfalls auf der Seite „Profil“. Das ist Teil der Einrichtung, die im
Abschnitt „Einrichten: Das BMS lernt Sie kennen“ weiter unten und in `docs/ANLEITUNG.md` im
Installationsverzeichnis beschrieben ist.

## Schritt 10: Protokoll schreiben und Abschluss

Das Protokoll soll in `INSTALLVERZ/Installprotokoll.md` stehen und enthält pro Schritt: Nummer,
Titel, Ergebnis (OK, FEHLER, ÜBERSPRUNGEN) und bei Fehlern die vollständige Meldung. Am Ende steht
ein Abschnitt „Offene Punkte“. **Enthält nie Schlüssel oder andere Geheimnisse.**

- Kannst du in dieser Sitzung Dateien auf dem Mac des Anwenders schreiben, tu das direkt.
- Sonst gib dem Anwender **einen** Befehl vor, der das Protokoll anhängt. Setze den Text zwischen
  die beiden Zeilen ein. Die Zeile `EOF` steht allein am Zeilenanfang:

  ```sh
  cat >> "INSTALLVERZ/Installprotokoll.md" <<'EOF'
  <hier das fertige Protokoll im Markdown-Format>
  EOF
  cat "INSTALLVERZ/Installprotokoll.md"
  ```

  Frage, ob der Inhalt in der Ausgabe erscheint.

**Auch bei Abbruch** (zwei Korrekturversuche erfolglos): Schreibe das Protokoll mit dem bisherigen
Stand und dem Fehler, damit die Installation später gezielt fortgesetzt oder der Fehler behoben
werden kann.

Fasse zum Schluss in höchstens zehn Zeilen zusammen:

- was installiert wurde (mit Versionen aus den Prüfungen),
- was funktioniert und was nicht (auch ehrlich, was nicht geprüft werden konnte),
- wie das BMS künftig gestartet wird (`INSTALLVERZ/start.command` per Doppelklick im Finder) und
  beendet (Ctrl + C im Terminal-Fenster, sonst `INSTALLVERZ/stop.command` per Doppelklick),
- wo das Protokoll liegt.

Biete danach an, mit dem Einrichten weiterzumachen: „Möchten Sie jetzt das BMS auf Ihre Person
einrichten? Das dauert ein bis zwei Stunden und lässt sich jederzeit unterbrechen.“ Grundlage ist der
Abschnitt „Einrichten: Das BMS lernt Sie kennen“ unter „Nach der Installation“. Sagt der Anwender
ja, gehe diesen Abschnitt mit ihm durch, in der dort genannten Reihenfolge und nach denselben
Gesprächsregeln (ein Abschnitt je Nachricht, Zugangsschlüssel nie im Chat). Sagt er nein, weise
darauf hin, dass der Abschnitt jederzeit in dieser Datei steht.

# Nach der Installation

Dieser Teil richtet sich an Sie. Er gilt, sobald das BMS läuft. Claude nutzt ihn zugleich als
Grundlage, wenn Sie nach der Installation mit dem Einrichten weitermachen.

## Einrichten: Das BMS lernt Sie kennen

Das BMS läuft jetzt, zeigt aber nur Beispieldaten und weiß noch nichts über Sie. Die folgenden
Schritte erledigen Sie einmalig und in dieser Reihenfolge: zuerst die Beispieldaten entfernen, dann
die fünf Abschnitte von „Ihr Profil: Identität und Suchstrategie“ bis „Suchbereich in der Jobliste“.
Diese brauchen Sie, damit das BMS für Sie arbeiten kann: Ohne Profil und Lebenslauf entstehen weder
Anschreiben noch Lebensläufe, ohne Zielrollen und Region findet die Jobsuche nichts Passendes. Die
E-Mail-Anbindung unter „E-Mail-Postfach verbinden“ ist optional.

### Zuerst: Beispieldaten entfernen

Beim allerersten Start bringt das BMS Beispieldaten von „Birne Helene“ mit, einer erfundenen Person:
Postbote mit fünf Jahren Erfahrung in der Paketzustellung. Dazu gehören sechs Firmen, fünf Stellen in
verschiedenen Stadien, drei Bewerbungen, fünf Mails, ein Gesprächstermin, ein Profil mit Fähigkeiten
und Werdegang, die Profil-Datei `config/profil.md` und ein deutscher Basis-Lebenslauf. Damit können
Sie das BMS ausprobieren. Solange die Beispieldaten da sind, steht auf dem Dashboard ein Hinweis, und
die Seitenleiste zeigt „Birne Helene“ als Ihren Namen. Wer das BMS schon benutzt hat, bekommt keine
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
ersetzen Sie alles, was noch von Birne Helene stammt: Name, Anschrift, Kontakt, Kurzprofil, Zielrolle
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
Briefkopf Ihrer Anschreiben und die Dateinamen Ihrer Unterlagen. Kurzprofil, Zielrolle und
Rahmenbedingungen liest die KI als Hintergrund, wenn sie Stellen bewertet und Anschreiben schreibt.
Zeigt die Karte noch Angaben von „Birne Helene“, haben Sie die Beispieldaten noch nicht entfernt.
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
| Zielrolle | Je eine Zeile für Ebene, Funktion Plan A, Funktion Plan B, Branche, Region und Zieltermin, etwa „Director oder Head of“ bei der Ebene und „neue Rolle bis 31.12.2026“ beim Zieltermin. Plan A ist Ihr eigentliches Ziel, Plan B die realistische Alternative. Wonach die Jobsuche sucht, stellen Sie unter „Zielrollen und Suchgebiet“ ein. |
| Harte Rahmenbedingungen | Was für Sie nicht verhandelbar ist. Je Zeile ein Punkt, beginnend mit „- “, etwa „- Kein Umzug, kein dauerhafter Zweitwohnsitz.“ |
| Bekannte Skill-Gaps | Lücken in Ihrem Profil, die Sie selbst kennen. Je Zeile ein Punkt. Ehrliche Angaben helfen, denn so bewertet die KI Stellen realistisch. |

Je konkreter Sie schreiben, desto passender werden Bewertungen und Anschreiben. Kurzprofil, Zielrolle
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
   abschalten oder zwei eigene ergänzen.
4. „KI-Modell je Funktion“: Zur Wahl stehen Opus 5.5, Sonnet 5.5 und Haiku 4.5, voreingestellt ist
   Sonnet 5.5. Die Voreinstellung passt für den Alltag, hier müssen Sie nichts ändern. Das Modell
   Fable bietet das BMS bewusst nicht an, weil es zu teuer ist: Es kostet das Zweieinhalbfache von
   Opus 5.5 und das Fünffache von Sonnet 5.5.

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
| Seitenleiste links oben ansehen | Unter „Bewerbungs-Management-System“ steht Ihr Name, nicht „Birne Helene“ oder „Bewerber“ | Beispieldaten entfernt (Abschnitt „Einrichten: Das BMS lernt Sie kennen“)? Name in der Karte „Identität und Suchstrategie“ eingetragen und gespeichert (Abschnitt „Ihr Profil: Identität und Suchstrategie“)? Bei einer von Hand bearbeiteten `config/profil.md` die Schreibweise `**Name:**` prüfen |
| „Dashboard“ ansehen | Kein Hinweis auf Beispieldaten mehr, keine Stellen und Mails von Birne Helene | „Beispieldaten entfernen“ in den „Einstellungen“ (Abschnitt „Zuerst: Beispieldaten entfernen“) |
| „Einstellungen“ öffnen | Alle Bereiche erscheinen ohne Fehlermeldung | Das Terminal-Fenster des BMS auf Fehlermeldungen prüfen, BMS neu starten |
| Unter „Stellen“ mit „+ Stelle anlegen“ eine Stelle erfassen | Sie erscheint in der Liste | BMS neu starten |
| In dieser Stelle „Firma prüfen“ starten | Der Lauf erscheint im „Task-Center“ und endet mit einem Ergebnis | Zugangsschlüssel prüfen (Schritt 7) |
| Danach „CV-Match“ und anschließend „CV erstellen“ starten | Eine Word- und eine PDF-Datei entstehen | Basis-CV (Abschnitt „Ihr Lebenslauf“) und LibreOffice prüfen |
| „Einstellungen“ → „Programmversion“ und den Fuß der Seitenleiste ansehen | Beide zeigen Ihre installierte Version | BMS neu starten, danach die Seite neu laden |

Ein KI-Lauf wie die Firmenprüfung dauert etwa zehn Minuten. Solange er läuft, können Sie normal
weiterarbeiten.

## Aktualisierungen einspielen

Neue Versionen erscheinen auf GitHub (https://github.com/holgerdaube/BewerbungsMgmtSystem/releases).
Ein eigenes Werkzeug lädt sie, prüft sie, sichert Ihren Stand und spielt sie ein. Ihre Daten,
Einstellungen und Anpassungen bleiben dabei erhalten. Ob es eine neue Version gibt, zeigt Ihnen auch
das BMS selbst: Unter „Einstellungen“, Karte „Programmversion“, fragt der Knopf „Nach Updates suchen“
bei GitHub nach der neuesten Version. Er zeigt das Ergebnis nur an und spielt nichts ein. Das Einspielen
übernimmt das Werkzeug, und zwar bei beendetem BMS:

1. Beenden Sie das BMS: Doppelklick auf `stop.command`. Ein laufendes BMS kann sich nicht
   zuverlässig selbst ersetzen, das Update-Werkzeug bricht sonst mit der Meldung „Das BMS läuft
   noch“ ab.
2. Doppelklicken Sie im Programmordner auf `update.command`. Es öffnet sich ein Terminal-Fenster.
3. Das Werkzeug sucht online nach einer neuen Version. Es schreibt dazu: „Suche auf GitHub nach einer
   neuen Version. GitHub erhält dabei die IP-Adresse dieses Rechners.“ Gesendet wird nur diese
   Anfrage, nichts aus Ihrer Datenbank. Findet das Werkzeug eine neuere Version, lädt es sie, vergleicht
   die Prüfsumme mit der Angabe von GitHub und prüft das Paket.
4. Das Werkzeug zeigt einen Plan: welche Dateien sich ändern und ob Python- oder
   Oberflächen-Bausteine neu installiert werden müssen. Bestätigen Sie die Rückfrage „Update von …
   auf … jetzt einspielen?“ mit `j`, wenn der Plan passt. Gibt es nichts Neues, meldet das Werkzeug
   „Ihr BMS ist auf dem neuesten Stand“, und Sie sind fertig.
5. Nach Abschluss steht dort „Update auf Version … abgeschlossen. Starten Sie das BMS wie
   gewohnt.“ Starten Sie das BMS wie gewohnt: Doppelklick auf `start.command` in Ihrem
   BMS-Ordner.

**Der zweite Weg: eine ZIP-Datei.** Klappt die Online-Suche nicht, oder möchten Sie sie nicht nutzen,
laden Sie die neue Datei `BMS_<Version>.zip` im Browser von der Release-Seite
(https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/latest, unter „Assets“) und speichern Sie
sie in Ihrem Ordner „Downloads“. Starten Sie das Werkzeug dann wie oben. Es findet die ZIP-Datei von
selbst, prüft sie und zeigt den Plan. Liegt eine ZIP-Datei in „Downloads“ und findet das Werkzeug
auch online eine Version, nimmt es die höchste Version, egal woher. Haben Sie eine Version bis 1.7.0
installiert, nehmen Sie für das erste Update auf Version 2.0.0 diesen Weg.

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

Im Terminal rufen Sie das Werkzeug auch mit Optionen auf. Die Beispiele nennen den vorgeschlagenen
Ordner; haben Sie einen anderen gewählt, setzen Sie Ihren BMS-Ordner ein. `--pruefen` zeigt nur den
Plan, ohne etwas einzuspielen. Ein dafür geladenes Paket bleibt im Ordner `data/updates/pakete`
liegen:

```sh
~/BMS/update.command --pruefen
```

`--offline` verhindert jeden Kontakt zu GitHub. Das Werkzeug sucht dann nicht online nach einer
neuen Version und nimmt nur eine ZIP-Datei aus „Downloads“:

```sh
~/BMS/update.command --offline
```

`--zurueck` nimmt das letzte Update zurück und spielt die vorherige Fassung wieder ein:

```sh
~/BMS/update.command --zurueck
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
| „command not found“ bei `brew` oder `claude` | Die zwei „Next steps“-Befehle von Homebrew fehlen (Schritt 3), danach Terminal neu öffnen |
| „start.command kann nicht geöffnet werden“ | Befehl `xattr` aus Schritt 4 ausführen. Alternativ unter Systemeinstellungen, Datenschutz & Sicherheit, „Dennoch öffnen“ wählen |
| Der Start bricht mit einer Meldung zu `cryptography` oder „symbol not found“ ab | Die Python-Umgebung entstand mit einem anderen Python. Im Terminal `rm -rf ~/.bewerbung_mgmt_venv` eingeben und Schritt 5 wiederholen |
| „address already in use“ oder Port 8000 belegt | Das BMS läuft bereits. Browser auf `http://localhost:8000` richten oder erst mit `stop.command` beenden |
| KI-Läufe enden mit einem Anmeldefehler | Zugangsschlüssel prüfen (Schritt 7): eine Zeile, kein `#` davor, vollständig kopiert. Danach das BMS neu starten |
| Es entsteht keine PDF-Datei | LibreOffice fehlt oder liegt nicht am vorgeschlagenen Ort |
| Lebensläufe heißen `CV_Bewerber_…` | Im Profil steht noch kein Name. Tragen Sie ihn in der Karte „Identität und Suchstrategie“ ein und speichern Sie (Abschnitt „Ihr Profil: Identität und Suchstrategie“). Bearbeiten Sie `config/profil.md` von Hand, prüfen Sie, ob die Zeile `**Name:**` genau so geschrieben ist |
| Im BMS stehen Stellen, Mails oder ein Profil von „Birne Helene“, die Sie nicht angelegt haben | Das sind die Beispieldaten. Entfernen Sie sie in den „Einstellungen“ mit „Beispieldaten entfernen“ (Abschnitt „Zuerst: Beispieldaten entfernen“) |
| „Beispieldaten entfernen“ meldet, dass gerade eine Sicherung oder eine Aufgabe läuft | Einen Moment warten, bei einer Aufgabe bis sie im „Task-Center“ fertig ist, und noch einmal klicken. Es wurde nichts verändert |
| `Antwort: 404` beim Laden des Programmpakets, oder in der Auskunft steht `Not Found` | Zu dieser Version gibt es auf GitHub kein Programmpaket, oder es ist noch keine Version veröffentlicht. Prüfen Sie die Versionsnummer aus der Auskunft. Hilft das nicht, nehmen Sie den Ersatzweg mit einer ZIP-Datei von der Release-Seite |
| In der Auskunft steht `API rate limit exceeded`, oder das Update-Werkzeug meldet „GitHub begrenzt gerade die Anfragen.“ | GitHub erlaubt ohne Anmeldung nur 60 Anfragen je Stunde und IP-Adresse. In einem Firmennetz teilen sich oft viele Rechner eine Adresse. Versuchen Sie es in einer Stunde noch einmal, oder nehmen Sie den Ersatzweg mit einer ZIP-Datei |
| `Antwort: 000` oder eine Meldung von curl wie „Could not resolve host“ | Es besteht keine Verbindung zu GitHub. Prüfen Sie Ihre Internetverbindung. In einem Firmennetz kann der Zugriff gesperrt sein. Klappt es nicht, laden Sie die ZIP-Datei im Browser von der Release-Seite und nehmen den Ersatzweg |
| Die Prüfsumme aus Schritt 4 weicht von der Auskunft ab | Das Paket ist unvollständig oder beschädigt, etwa weil die Verbindung unterbrochen wurde. Löschen Sie die Datei und laden Sie sie einmal neu. Weicht die Prüfsumme wieder ab, laden Sie die ZIP-Datei im Browser von der Release-Seite (Ersatzweg) |
| Das Update-Werkzeug meldet „Online-Suche nicht möglich: …“ | Das ist kein Abbruch. Die Meldung nennt den Grund, zum Beispiel „Es besteht keine Verbindung zu GitHub.“ Das Werkzeug macht mit einer ZIP-Datei in „Downloads“ weiter, wenn dort eine liegt. Sonst laden Sie die neue `BMS_<Version>.zip` von der Release-Seite auf GitHub und legen sie dort ab |
| Update bricht mit „Das BMS läuft noch“ ab | Zuerst `stop.command` ausführen, dann das Update erneut starten |
| Update bricht mit einem Hinweis auf `npm`/Node.js ab | Node.js nachinstallieren (Schritt 3), danach das Update erneut starten. Es wurde nichts verändert |
| Update meldet „fehlgeschlagen, alle Änderungen wurden zurückgerollt“ | Die Meldung nennt den Sicherungsordner unter `data/updates/…`. Ihre vorherige Fassung läuft unverändert weiter, versuchen Sie das Update erneut oder melden Sie das Problem auf der Issues-Seite (Abschnitt „Hilfe“) |
| „Kein Update-Paket gefunden“ | Weder online noch in „Downloads“ lag ein Paket bereit. Der Grund der Online-Suche steht in der Meldung davor. Legen Sie die Datei `BMS_<Version>.zip` im Ordner „Downloads“ ab und versuchen Sie es erneut |

Nach jeder Änderung an Dateien im Programmordner starten Sie das BMS neu, damit es sie einliest.

## Ihre Daten

Das BMS läuft vollständig auf Ihrem Rechner. Ihre Bewerbungen, Ihr Profil und Ihre E-Mails liegen
in der Datenbank `data/bewerbung.sqlite` im Programmordner, Ihre erzeugten Dokumente im Ordner
`outputs`. Der Herausgeber des BMS betreibt keinen Server für das Programm und erhält davon nichts.
Kontakt zu GitHub gibt es nur beim Laden des Programmpakets in der Installation und wenn Sie selbst
nach einer neuen Version suchen (Knopf „Nach Updates suchen“ in den Einstellungen oder das
Update-Werkzeug). GitHub erhält dabei die IP-Adresse Ihres Rechners und die Anfrage selbst, sonst
nichts. Mit `--offline` oder mit einer ZIP-Datei gibt es keinen Kontakt. Näheres steht unter
„Rechtliches“, Reiter „Datenschutz“. Die KI-Funktionen übermitteln Inhalte an Anthropic, soweit sie
für den jeweiligen Lauf nötig sind, und zwar über Ihr eigenes Claude-Konto.

Das BMS sichert Ihre Datenbank automatisch, solange es läuft: einmal täglich als ZIP-Datei im
Ordner `data/backups/auto`. Aufbewahrt werden die neueste Sicherung, alle der letzten 24 Stunden
sowie je eine der letzten 7 Tage und der letzten 4 Wochen. Ältere automatische Sicherungen
entfernt das BMS selbst. Unter „Einstellungen“, Karte „Datensicherung“, sehen Sie die letzte
Sicherung, ändern die Aufbewahrung und sichern auf Knopfdruck.

Diese Sicherungen liegen in Ihrem BMS-Ordner auf derselben Festplatte wie Ihre Arbeitskopie und
ersetzen keine externe Datensicherung. Nehmen Sie Ihren BMS-Ordner zusätzlich in Ihre reguläre
Datensicherung auf, auf dem Mac etwa über Time Machine.

So spielen Sie eine Sicherung zurück:

1. Beenden Sie das BMS: Doppelklick auf `stop.command`.
2. Doppelklicken Sie in Ihrem BMS-Ordner auf `wiederherstellen.command`. Das Werkzeug zeigt Ihnen
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
Ordner `data/backups/auto` die gewünschte ZIP-Datei (Doppelklick), benennen
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
