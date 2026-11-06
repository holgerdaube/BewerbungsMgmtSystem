# Bewerbungs-Management-System

[English](README.md) · **Deutsch**

Das Bewerbungs-Management-System (kurz BMS, Kurzform BewerbungsMgmtSystem) ist eine lokale Web-App für
Ihre eigene Jobsuche. Es findet und bewertet Stellen, prüft Firmen, bereitet Lebenslauf und Anschreiben
vor und verfolgt die Antworten in Ihrem Postfach. Das BMS läuft auf Ihrem Rechner und ist kostenlos und
Open Source (Apache License 2.0).

## Für wen ist das BMS?

Für Bewerbende, die ihre Jobsuche selbst steuern und dabei Hilfe von KI wollen. Die KI-Arbeit
(Recherche, Bewertung, Textentwürfe) erledigt wahlweise Claude von Anthropic oder ChatGPT von OpenAI,
jeweils über Ihr eigenes Konto. Dafür brauchen Sie keine eigenen API-Schlüssel, und ohne KI laufen
Erfassen, Verwalten und Auswerten trotzdem.

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

## Sprachen

Oberfläche, Dokumentation und KI-Berichte gibt es auf Deutsch und Englisch. Umschalten können Sie in der
Seitenleiste oder in den Einstellungen.

Lebenslauf und Anschreiben folgen der Sprache der Stellenanzeige: Deutsch, Englisch, Französisch,
Italienisch, Spanisch oder Portugiesisch. Dafür laden Sie einen Basis-CV in dieser Sprache hoch. Fehlt er,
nimmt das BMS die englische, sonst die deutsche Fassung, übersetzt nichts und nennt das im Bericht des Laufs.

Außerhalb Deutschlands hat die Jobsuche Grenzen. Die vorbelegten Portale sind auf Deutschland ausgerichtet,
in Frankreich, Italien und Spanien fand die Suche in der Prüfung kaum Stellen, für Portugal und Brasilien
lief keine. Nutzen Sie dort die zwei freien Portal-Zeilen in den Einstellungen, LinkedIn-Alerts und Ihre
Zielfirmen. Lebenslauf und Anschreiben auf Französisch, Italienisch, Spanisch und Portugiesisch sind an je
einer echten Anzeige mit Claude erprobt. Die Postfach-Suche nach Wörtern in diesen Sprachen lief an einem
echten Postfach ohne Fehltreffer. Ob sie eine echte Antwort in diesen Sprachen findet und richtig einordnet,
ist noch nicht erprobt, weil dort keine solche Antwort vorlag.

## Voraussetzungen

- Ein Mac (macOS) oder ein Windows-PC mit etwa 2 GB freiem Speicher und Internetverbindung.
- Für die KI-Funktionen ein Abo bei Claude (Pro oder Max, Anthropic) oder bei ChatGPT (Plus oder Pro,
  OpenAI). Die Kosten zahlen Sie direkt an den Anbieter, das BMS selbst kostet nichts.
- Optional ein E-Mail-Konto mit IMAP-Zugang (auch Gmail), damit das BMS Antworten im Postfach erkennt.
- Optional ein LinkedIn-Datenexport, um Werdegang und Fähigkeiten zu übernehmen.

Python, Node.js und die übrigen Programme müssen Sie nicht vorab installieren: Die Installationsanleitung
richtet ein, was fehlt. Programmierkenntnisse brauchen Sie nicht.

## Welche KI?

Das BMS kann die KI-Funktionen mit **Claude** oder mit **ChatGPT** ausführen. Die Installation fragt gleich
zu Beginn, welche Sie nutzen, und richtet genau diese ein. In den Einstellungen, Karte „KI“, wechseln Sie
später.

- **Claude** ist der Standard und der am besten erprobte Weg. Die Inhalte der KI-Läufe gehen an Anthropic.
- **ChatGPT** ist im BMS eine Vorschau. Die Läufe nutzen Ihre Anmeldung bei ChatGPT (Plus oder Pro) über
  das Programm Codex CLI, einen API-Schlüssel brauchen Sie nicht. Die Inhalte der KI-Läufe gehen dann an
  OpenAI statt an Anthropic. Die Läufe ohne Mail sind erprobt, die Mail-Läufe und der Tageslauf noch nicht. Es gibt keine Budgetgrenze je Lauf, es
  gelten die Grenzen Ihres Abos, und viele Läufe hintereinander können ein Plus-Konto an die Grenze bringen.
- **Gemini** gibt es nicht: Googles Regeln lassen das Gemini-Abo in Apps wie dem BMS nicht zu.

## Installation

Die Installation führt eine KI im Chat mit einer Anleitungsdatei Schritt für Schritt aus Ihrer Sicht durch:

1. Laden Sie die Anleitung für Ihr System von https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/latest
   herunter: `BMS_Install_MAC.md` für macOS oder `BMS_Install_Windows.md` für Windows. Beide liegen auch
   im Hauptordner dieses Repositorys.
2. Öffnen Sie Claude Desktop oder ChatGPT, starten Sie einen neuen Chat und hängen Sie die Datei an.
3. Schreiben Sie dazu: „Führe mich mit dieser Anleitung durch die Installation des BMS.“

Der Assistent im Chat gibt Ihnen jeden Befehl zum Kopieren vor und prüft das Ergebnis mit Ihnen. Die
Anleitung fragt zuerst, welche KI das BMS nutzen soll (Claude oder ChatGPT). Sie lädt das
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
erhält dabei die IP-Adresse Ihres Rechners. Dienste, die Sie selbst anbinden (Claude oder ChatGPT, Ihr
Postfach, optional Apify), verarbeiten Daten nach ihren eigenen Datenschutzbestimmungen; Einzelheiten
stehen im Reiter „Datenschutz“ unter „Rechtliches“ in der App.

## Hinweis zur KI

Texte, Bewertungen und Entwürfe erzeugt das BMS mit KI (Claude oder ChatGPT, je nach Ihrer Wahl). Sie sind
Vorschläge und müssen vor dem Versand geprüft werden.

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
- **Sicherheitslücken:** Bitte nicht als öffentliches Issue, sondern wie in [`SECURITY.de.md`](SECURITY.de.md)
  beschrieben.
- **Beiträge:** Pull Requests sind willkommen. Die Regeln (Lizenz, Sprache, Tests) stehen in
  [`CONTRIBUTING.de.md`](CONTRIBUTING.de.md).

## Unterstützen

Das BMS ist kostenlos und bleibt es. Wer die Arbeit daran unterstützen möchte, kann freiwillig etwas
geben, über den Knopf „Sponsor“ oben auf dieser Seite oder direkt:

- **Buy Me a Coffee:** https://buymeacoffee.com/holgerdaube
- **PayPal:** https://paypal.me/holgerdaube

Eine Unterstützung ist ein freiwilliges Dankeschön und keine Gegenleistung für das Programm. Sie schaltet
nichts frei und begründet keinen Anspruch auf Support, Funktionen oder Updates; die Überlassung bleibt
unentgeltlich (siehe „Lizenz und Haftung“). Steuerlich absetzbar ist sie nicht.

## Für Entwickler

Das BMS ist ein FastAPI-Backend mit SQLite, ein React-Frontend und eine Sammlung von Claude-Skills. Wie
Sie den Quellcode einrichten, starten und testen, steht in [`docs/INSTALLATION.md`](docs/INSTALLATION.md)
(Entwickler-Installation unter macOS und Windows). Aufbau, Datenmodell, Skills, Betrieb und Sicherheit
beschreibt [`docs/DOKUMENTATION.md`](docs/DOKUMENTATION.md), den Ablauf einer Freigabe
[`docs/RELEASE.md`](docs/RELEASE.md). Code-Kommentare, Skills, Tests und Commit-Nachrichten sind deutsch.
