# Bewerbungs-Management-System

Das Bewerbungs-Management-System (kurz BMS, Kurzform BewerbungsMgmtSystem) ist eine lokale Web-App für
Ihre eigene Jobsuche. Es findet und bewertet Stellen, prüft Firmen, bereitet Lebenslauf und Anschreiben
vor und verfolgt die Antworten in Ihrem Postfach. Das BMS läuft auf Ihrem Rechner und ist kostenlos und
Open Source (Apache License 2.0).

## Für wen ist das BMS?

Für Bewerbende, die ihre Jobsuche selbst steuern und dabei Hilfe von KI wollen. Die KI-Arbeit
(Recherche, Bewertung, Textentwürfe) erledigt Claude von Anthropic über Ihr eigenes Claude-Konto. Dafür
brauchen Sie keine eigenen API-Schlüssel, und ohne KI laufen Erfassen, Verwalten und Auswerten trotzdem.

Das BMS unterstützt ausschließlich die Seite, die sich bewirbt. Funktionen, mit denen Arbeitgeber
Bewerbende bewerten, sortieren oder auswählen, gibt es nicht und sind nicht vorgesehen. Sie behalten die
Entscheidung: Das BMS bewirbt sich nie selbst und verschickt keine E-Mail, es legt nur Entwürfe an, die
Sie prüfen und selbst senden.

## Was das BMS kann

- **Stellen finden und bewerten:** Suchläufe über Jobportale, Karriereseiten und Job-Benachrichtigungen,
  mit einem Zielstellen-Fit von 1 bis 5 samt Beleg aus der Anzeige.
- **Firmen prüfen:** Geschäftsmodell, Markt, Wettbewerber und der Einfluss der Rolle auf die Firma.
- **Unterlagen vorbereiten:** Lebenslauf passend zur Stelle (Word und PDF, mit ATS-Scan) und
  Anschreiben, ohne erfundene Angaben.
- **Postfach auswerten:** Antworten auf Bewerbungen erkennen, Antwortzeiten messen, Antwortentwürfe
  anlegen.
- **Gespräche begleiten:** Briefing vor dem Gespräch, Auswertung danach, Follow-ups und Netzwerk.
- **Überblick behalten:** Dashboard, Pipeline, Excel-Export, Kosten- und Budgetanzeige für die KI-Läufe.

Eine Übersicht nach Arbeitsschritten steht in [`docs/FUNKTIONEN.md`](docs/FUNKTIONEN.md), die Bedienung
beschreibt [`docs/ANLEITUNG.md`](docs/ANLEITUNG.md).

## Voraussetzungen

- Ein Mac (macOS) oder ein Windows-PC mit etwa 2 GB freiem Speicher und Internetverbindung.
- Für die KI-Funktionen ein Claude-Konto (Pro oder Max) bei Anthropic. Die Kosten zahlen Sie direkt an
  Anthropic, das BMS selbst kostet nichts.
- Optional ein E-Mail-Konto mit IMAP-Zugang (auch Gmail), damit das BMS Antworten im Postfach erkennt.
- Optional ein LinkedIn-Datenexport, um Werdegang und Fähigkeiten zu übernehmen.

Python, Node.js und die übrigen Programme müssen Sie nicht vorab installieren: Die Installationsanleitung
richtet ein, was fehlt. Programmierkenntnisse brauchen Sie nicht.

## Installation

Die Installation führt Claude mit einer Anleitungsdatei Schritt für Schritt aus Ihrer Sicht durch:

1. Laden Sie die Anleitung für Ihr System von https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/latest
   herunter: `BMS_Install_MAC.md` für macOS oder `BMS_Install_Windows.md` für Windows. Beide liegen auch
   im Hauptordner dieses Repositorys.
2. Öffnen Sie Claude Desktop, starten Sie einen neuen Chat und hängen Sie die Datei an.
3. Schreiben Sie dazu: „Führe mich mit dieser Anleitung durch die Installation des BMS.“

Claude gibt Ihnen jeden Befehl zum Kopieren vor und prüft das Ergebnis mit Ihnen. Die Anleitung lädt das
Programmpaket selbst aus dem GitHub-Release und prüft dessen Prüfsumme. Danach richtet sie mit Ihnen
Profil, Lebenslauf, Zielrollen und Suchregion ein. Rechnen Sie mit etwa 45 Minuten für die Technik und
ein bis zwei Stunden für die Einrichtung.

## Updates

In den Einstellungen zeigt die Karte „Programmversion“ mit dem Knopf **Nach Updates suchen**, ob es eine
neuere Version gibt, und nennt, was sich ändert. Der Knopf fragt nur, wenn Sie darauf klicken, und
spielt nichts ein. Eingespielt wird bei beendetem BMS mit `update.command` (macOS) oder
`update_windows.bat` (Windows): Das Werkzeug lädt die neue Version von GitHub, prüft sie, sichert vorher
Ihre Daten und macht bei einem Fehler alles rückgängig. Was sich je Version ändert, steht in
[`CHANGELOG.md`](CHANGELOG.md).

## Datenschutz

Das BMS läuft vollständig auf Ihrem Rechner: Ihre Bewerbungs-, Profil- und E-Mail-Daten bleiben in
lokalen Dateien und einer lokalen Datenbank, und der Herausgeber betreibt keinen Server und erhält keine
Daten. Nur wenn Sie nach Updates suchen oder ein Update laden, fragt das BMS bei GitHub an, und GitHub
erhält dabei die IP-Adresse Ihres Rechners. Dienste, die Sie selbst anbinden (Claude, Ihr Postfach,
optional Apify), verarbeiten Daten nach ihren eigenen Datenschutzbestimmungen; Einzelheiten stehen im
Reiter „Datenschutz“ unter „Rechtliches“ in der App.

## Hinweis zur KI

Texte, Bewertungen und Entwürfe erzeugt das BMS mit KI (Claude). Sie sind Vorschläge und müssen vor dem
Versand geprüft werden.

## Lizenz und Haftung

Das Bewerbungs-Management-System (kurz BewerbungsMgmtSystem) ist Open Source und steht unter der
**Apache License 2.0** (Datei `LICENSE`, Herkunftsangaben in `NOTICE`). Es darf genutzt, verändert
und weitergegeben werden, auch umbenannt und gewerblich. Wer es weitergibt, legt `LICENSE` bei,
übernimmt die Hinweise aus `NOTICE` und kennzeichnet geänderte Dateien. Rechte an Namen und Marken,
insbesondere an „Daube.Tech“, gewährt die Lizenz nicht (Abschnitt 6).

**Haftung nach deutschem Recht:** Das Programm wird unentgeltlich überlassen. Für eine
unentgeltliche Überlassung gilt: Der Urheber haftet nur für Vorsatz und grobe Fahrlässigkeit
(§ 521 BGB), für Mängel nur, wenn er sie arglistig verschwiegen hat (§§ 523, 524 BGB). Die Haftung
nach dem Produkthaftungsgesetz bleibt unberührt. Dieser Hinweis ändert die Lizenz nicht.

## Autor

Entwickelt von Holger Daube. Impressum: https://daube.tech/impressum.html

## Mitmachen

- **Fehler und Wünsche:** Bitte als Issue melden: https://github.com/holgerdaube/BewerbungsMgmtSystem/issues
- **Sicherheitslücken:** Bitte nicht als öffentliches Issue, sondern wie in [`SECURITY.md`](SECURITY.md)
  beschrieben.
- **Beiträge:** Pull Requests sind willkommen. Die Regeln (Lizenz, Sprache, Tests) stehen in
  [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Für Entwickler

Das BMS ist ein FastAPI-Backend mit SQLite, ein React-Frontend und eine Sammlung von Claude-Skills. Wie
Sie den Quellcode einrichten, starten und testen, steht in [`docs/INSTALLATION.md`](docs/INSTALLATION.md)
(Entwickler-Installation unter macOS und Windows). Aufbau, Datenmodell, Skills, Betrieb und Sicherheit
beschreibt [`docs/DOKUMENTATION.md`](docs/DOKUMENTATION.md), den Ablauf einer Freigabe
[`docs/RELEASE.md`](docs/RELEASE.md).
