## Datenschutz

### Kernaussage

Diese Software läuft **lokal auf dem Rechner des Nutzers**. Der Herausgeber betreibt
keinen Server für das Programm und erhält **keine Daten** aus der Nutzung — es gibt schlicht
keinen Codepfad, über den Bewerbungs-, Profil- oder E-Mail-Daten an den Herausgeber
übertragen werden. Fragt der Nutzer nach neuen Programmversionen, geht die Anfrage an GitHub
(siehe „Nach Updates suchen“), nicht an den Herausgeber.

Alle Bewerbungs-, Profil- und E-Mail-Daten liegen ausschließlich in lokalen Dateien und
einer lokalen SQLite-Datenbank auf dem Gerät des Nutzers.

### Verantwortliche Stelle

Verantwortlich für die Verarbeitung der in der Software erzeugten Daten ist **der Nutzer
selbst**, da er die Software lokal betreibt und die Verarbeitung nicht im Auftrag des
Herausgebers erfolgt. Für rein persönliche Zwecke der eigenen Jobsuche greift regelmäßig die
Haushaltsausnahme (Art. 2 Abs. 2 lit. c DSGVO).

### Vom Nutzer angebundene Drittdienste

Die Software kann optionale Drittdienste einbinden — diese werden vom **Nutzer mit
eigenen Konten** verbunden, nicht vom Herausgeber bereitgestellt:

- **Anthropic (Claude / Claude Code)** — für die KI-gestützten Funktionen (Recherche,
  Textentwürfe, Matching), wenn Claude als KI gewählt ist (Standard).
- **OpenAI (ChatGPT / Codex CLI)** — für dieselben Funktionen, wenn der Nutzer ChatGPT als KI
  wählt. Die Anmeldung ist die des ChatGPT-Kontos des Nutzers, ein API-Schlüssel ist dafür nicht nötig.
- **Google Gmail** — für das Lesen relevanter Bewerbungs-Mails und das Anlegen von
  E-Mail-Entwürfen. Verwendete Scopes: **readonly** und **compose**. Es existiert **kein
  Sende-Codepfad** — die Software kann keine E-Mails verschicken, sie legt ausschließlich
  Entwürfe an, die der Nutzer selbst prüft und versendet.
- **Apify** (optional) — für die automatisierte Stellensuche.
- **Jobsuche der Bundesagentur für Arbeit** (ohne Konto) — für die Stellensuche. Die
  Software ruft die öffentliche Suchseite arbeitsagentur.de/jobsuche ab. Übermittelt werden
  Suchbegriff, Ort, Umkreis, Zeitraum und der Homeoffice-Filter. Technisch bedingt fällt
  dabei die IP-Adresse des Rechners an.
- **OpenAI** (optional) — für den Beirat-Funktionsbereich, falls konfiguriert.

Für jeden dieser Dienste gelten die **Datenschutzbestimmungen des jeweiligen Anbieters**.
Der Nutzer ist für den datenschutzkonformen Einsatz dieser Drittdienste **selbst
verantwortlich**, da er die Konten selbst anlegt, verbindet und die entsprechenden
Zustimmungen gegenüber diesen Anbietern selbst erteilt.

### KI-Läufe: Claude oder ChatGPT

Die KI-gestützten Funktionen führt wahlweise Claude Code oder die Codex CLI von OpenAI aus. Die
Auswahl trifft der Nutzer bei der Installation oder später in den Einstellungen (Karte „KI“),
Standard ist Claude. Beide Programme laufen auf dem Rechner des Nutzers und melden sich mit dessen
eigenem Konto an.

- **Empfänger:** der Anbieter der gewählten KI, bei Claude Anthropic, bei ChatGPT OpenAI. Der
  Herausgeber betreibt dafür keinen Server und erhält weder die Anfragen noch die Antworten. Der
  Anbieter verarbeitet sie in eigener Verantwortung; es gilt dessen Datenschutzerklärung.
  Anthropic: https://www.anthropic.com/legal/privacy
  OpenAI: https://openai.com/policies/privacy-policy/
- **Daten:** die Inhalte, die ein Lauf braucht, soweit sie für den jeweiligen Lauf nötig sind, etwa
  Teile von Profil, Lebenslauf, Stellenanzeigen und gelesenen E-Mails, dazu die Anweisungen des
  Laufs. Bei ChatGPT gehen sie an OpenAI statt an Anthropic.
- **Zweck:** Recherche, Bewertung und Textentwürfe, die der Nutzer in der App anstößt.
- **Auslöser:** Läufe, die der Nutzer in der App startet, und Schritte, die auf eine seiner Aktionen
  folgen.
- **Aufbewahrung und Training:** Dazu trifft die Software keine Aussage. Es gelten die Bedingungen des
  jeweiligen Anbieters und der Tarif des Nutzerkontos, nachzulesen in dessen Datenschutzerklärung und
  Nutzungsbedingungen.

### Nach Updates suchen

Drei Vorgänge fragen bei GitHub nach der neuesten Programmversion oder laden das
Programmpaket, und alle löst der Nutzer selbst aus: der Knopf „Nach Updates suchen“ in den
Einstellungen, das Update-Werkzeug (update.command bzw. update_windows.bat) und der Ladebefehl
in der Installationsanleitung. Die laufende Software im Hintergrund, der Tageslauf und die
Skills tun das nie. Der Knopf zeigt nur an, ob es eine neue Version gibt; eingespielt wird
sie nie ohne den Nutzer.

- **Empfänger:** GitHub, über api.github.com (Frage nach der neuesten Version) und
  github.com (Download des Programmpakets). Der Herausgeber betreibt dafür keinen Server und
  erhält weder die Anfrage noch deren Ergebnis. GitHub verarbeitet die Anfrage in eigener
  Verantwortung; es gilt dessen Datenschutzerklärung:
  https://docs.github.com/de/site-policy/privacy-policies/github-general-privacy-statement
- **Daten:** die IP-Adresse des anfragenden Rechners und die Anfrage selbst, also die
  abgefragte Adresse und die Kennung „BMS-Update“ als Programmname. Es gibt keine Anmeldung
  und kein Token. Nicht übertragen werden die installierte Programmversion, das
  Betriebssystem, eine Rechnerkennung sowie Bewerbungs-, Profil- und E-Mail-Daten.
- **Zweck:** die neueste veröffentlichte Version erfragen und das Programmpaket laden.
- **Auslöser:** nur der Nutzer. Neben dem Knopf steht der Hinweis, dass GitHub dabei die
  IP-Adresse des Rechners erhält, das Update-Werkzeug schreibt ihn vor jeder Suche. Das
  Update-Werkzeug fragt mit der Option „--offline“ nicht online nach, und wer ein
  Programmpaket als ZIP-Datei einspielt, löst damit keinen Kontakt zu GitHub aus.

### Welche Daten die Software lokal verarbeitet

Zur eigenen Übersicht — alle folgenden Daten verbleiben in der lokalen SQLite-Datenbank
bzw. im lokalen Dateisystem des Nutzers:

- Stammdaten und Werdegang des Nutzers (Profil-Bereich).
- Bewerbungsdaten (Stellen, Firmen, Kontakte, Status, Kommunikationsverlauf).
- Lokal zwischengespeicherte E-Mail-Inhalte, soweit sie über den Gmail-Import gelesen
  wurden.
- Von der Software erzeugte Dokumente (Lebenslauf-Fassungen, Anschreiben, Exporte).

### Datensicherheit

Zugangsdaten zu Drittdiensten (z. B. OAuth-Tokens) werden lokal auf dem Gerät des Nutzers
gespeichert, nicht an den Herausgeber übertragen. Für die Absicherung des eigenen Geräts
(Festplattenverschlüsselung, Benutzerkonto-Schutz, Backups) ist der Nutzer selbst
verantwortlich.
