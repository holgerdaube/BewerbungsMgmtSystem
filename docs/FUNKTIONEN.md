# Funktionen

Das Bewerbungs-Management-System (BMS) läuft auf Ihrem Rechner, findet passende Stellen, bewertet sie und bereitet Ihre Unterlagen vor. Sie entscheiden: Das BMS bewirbt sich nie selbst und verschickt nichts ohne Ihr Zutun.

Das BMS ist kostenlos und steht als Open Source unter der Apache License 2.0. Es braucht keine Lizenzdatei: Alle Funktionen stehen Ihnen von Anfang an zur Verfügung.

## Stellen finden und bewerten

- **Neu / Review**: „Jobsuche (WebSearch)“ durchsucht die Portale nach Ihren Zielrollen und legt Treffer als „Neu“ an. Wonach gesucht wird, stellen Sie in den **Einstellungen** ein.
- Jede Stelle erhält einen Zielstellen-Fit von 1 bis 5, mit Begründung und Beleg aus der Anzeige. Treffer nehmen Sie an oder verwerfen sie.
- Ebenfalls auf **Neu / Review** starten Sie Zielfirmen-Sweep, Headhunter-Suche und Beworben-Check (prüft, ob beworbene Stellen noch ausgeschrieben sind). Der Knopf **Tageslauf** in der Seitenleiste führt alle Läufe samt Mail-Jobsuche und E-Mail-Check nacheinander aus.
- **Stellen** listet alle Treffer mit Filtern, **Pipeline** zeigt sie als Kanban-Tafel, **Suche** durchsucht sie im Volltext. Eigene Funde erfassen Sie mit „+ Stelle anlegen“.

## Firmen prüfen

- „Company-Fit prüfen“ in der Karte „Unterlagen erstellen“ einer Stelle untersucht Geschäftsmodell, Wettbewerber, Folgen von KI für den Markt und Arbeitgeber-Bewertungen und beurteilt den Einfluss der Rolle auf die Firma.
- „Entscheider recherchieren“ in der Karte „Kontakte“ sucht in öffentlichen Quellen die Fachentscheider statt der Personalabteilung.
- **Firmen** listet Ihre Firmen, der **Restructuring-Radar** jene mit frischem Umbau- oder Abbausignal.

## Lebenslauf und Anschreiben

- **Profil**: Hier pflegen Sie Positionierung, Fähigkeiten, Werdegang und Zeugnisse und laden Ihre Basis-Lebensläufe als Word-Datei hoch, deutsch und englisch. Ein LinkedIn-Datenexport füllt Fähigkeiten und Werdegang vor. Die Karte „Identität und Suchstrategie“ oben auf der Seite nimmt Name, Anschrift, Kontakt, Kurzprofil, Zielrolle und Rahmenbedingungen auf: Daraus entstehen der Briefkopf Ihrer Anschreiben und der Hintergrund für die KI.
- „CV-Match“ vergleicht Ihren Lebenslauf mit der Anzeige und erstellt ein Match-Dashboard sowie einen angepassten Entwurf. Das BMS erfindet nichts und nennt Anforderungen, die Ihr Lebenslauf nicht belegt.
- Den Entwurf bearbeiten Sie im Textfenster. „CV erstellen“ erzeugt Word und PDF und prüft per ATS-Scan, ob Bewerbungssysteme den Lebenslauf lesen können.
- „Anschreiben generieren“ schreibt ein Anschreiben für genau diese Firma. Den Text bearbeiten Sie danach selbst, „Word + PDF erzeugen“ erstellt die Dateien.
- „Bewerbungspaket“ erledigt Company-Fit, CV und auf Wunsch das Anschreiben in einem Zug.

## Postfach

- **Inbox** zeigt bewerbungsrelevante Mails mit Kategorie, Antwortzeit und Hinweis, was Sie beantworten sollten. Mails ohne Stelle ordnen Sie von Hand zu oder archivieren sie, Ihr Postfach bleibt dabei unverändert.
- Der „E-Mail-Check“ auf **Neu / Review** liest Ihr Postfach nach Antworten auf Bewerbungen. Die Mail-Jobsuche im Tageslauf liest Stellen aus Job-Benachrichtigungen.
- Das Postfach verbinden Sie in den **Einstellungen** in der Karte „E-Mail-Konto“, per IMAP (auch Gmail) oder über die Gmail-API.
- „Antwort entwerfen“ legt zu einer eingegangenen Mail einen Entwurf in Ihrem Postfach ab. Den Entwurf prüfen und senden Sie selbst, das BMS verschickt nie eine Mail.

## Gespräche vorbereiten und nachbereiten

- In der Karte „Interviews & Gespräche“ halten Sie Termine fest. „Interview vorbereiten (Briefing)“ erstellt erwartbare Fragen mit Antwortskizzen aus Ihrem Lebenslauf und Fragen an die Firma.
- **Follow-ups** zeigt anstehende Gespräche mit Briefing und Route (Google Maps) sowie fällige Schritte und Netzwerk-Aktionen.
- Nach dem Gespräch fügen Sie ein Transkript ein oder laden eine Textdatei hoch. „Auswerten“ zeigt, was gut lief, was wackelig war und was offen bleibt.

## Netzwerk

- **Netzwerk** führt drei Listen, die Sie in der App pflegen: Zielfirmen, Headhunter und Netzwerk-Kontakte. Zielfirmen-Sweep und Headhunter-Suche prüfen die ersten beiden reihum auf passende Stellen.
- Mit „Aus Datei importieren“ legen Sie in jeder der drei Listen viele Einträge auf einmal an, aus einer CSV- oder Excel-Datei. Eine Vorlage laden Sie im Importbereich herunter, die Spalten erkennt das BMS an der Überschrift. Für Netzwerk-Kontakte liest es auch die Datei `Connections.csv` aus Ihrem LinkedIn-Datenexport. Eine Vorschau zeigt vorher, was passiert. Vorhandene Einträge ergänzt der Import nur in leeren Feldern und überschreibt nie etwas, vorab sichert das BMS Ihre Datenbank.
- Zu Kontakten tragen Sie die nächste Aktion mit Fälligkeit ein, Überfälliges erscheint unter **Follow-ups**.
- Gespräche mit Headhuntern erfassen Sie direkt am Eintrag, sie zählen in den Kennzahlen des **Dashboards** mit.

## Beirat

- „Stelle prüfen (Beirat)“ in der Karte „Unterlagen erstellen“ lässt sieben fiktive Köpfe mit verschiedenen Fachperspektiven die Stelle bewerten. Das Ergebnis ist eine Ampel mit Dashboard, bei Rot können Sie die Stelle auf „Beirat abgelehnt“ setzen.
- Für freie Fragen ohne Stellenbezug gibt es den **Beirat** in der Seitenleiste. Die Köpfe debattieren dort live, der Vorsitz schließt mit einer Synthese.
- In den **Einstellungen** besetzen Sie einen der sieben Plätze neu und bestimmen den Vorsitz. Die Regeln des Beirats stehen unter **Dokumentation**, Reiter „Beirat“.

## Überblick und Kosten

- **Dashboard**: Es zeigt Kennzahlen zu Stellen, Bewerbungen, Antwortzeit und Antwortquote, dazu einen Trichter vom Sichten bis zum Interview. „Excel-Export“ und „Tages-Digest“ geben den Stand als Tabelle und als Bericht aus.
- **Task-Center**: Es protokolliert jeden KI-Lauf mit Status, Dauer und Kostenschätzung. Sie sehen einem Lauf live zu, brechen ihn ab oder starten ihn neu. Die Läufe gehen über Ihr eigenes Konto bei Claude oder ChatGPT.
- **Budget**: Es zeigt, was kostenpflichtige Dienste verbrauchen, und begrenzt sie mit Tages- und Monatslimits. Ein hartes Limit blockiert weitere Aufrufe, ein weiches warnt nur.
- In den **Einstellungen**, Karte „KI“, wählen Sie, ob die KI-Läufe mit Claude (Standard) oder mit ChatGPT laufen. ChatGPT ist eine Vorschau: Die Läufe ohne Mail sind erprobt, die Mail-Läufe und der Tageslauf noch nicht. Die Inhalte der Läufe gehen dann an OpenAI statt an Anthropic, und es gibt keine Budgetgrenze je Lauf, es gelten die Grenzen Ihres Abos.
- In den **Einstellungen** wählen Sie je Funktion das KI-Modell: Opus 5.5, Sonnet 5.5 oder Haiku 4.5 (mit ChatGPT die Modelle von ChatGPT). Voreingestellt ist Sonnet 5.5.
- Die **Coach-Site** (Einstellungen, Karte „Coach-Site“) zeigt Ihrem Coach den Stand auf einer passwortgeschützten Webseite, nur lesend und ohne E-Mails, Notizen, Gehälter und Kontakte. Dafür brauchen Sie eigenen Webspace. Unter Windows ist sie nicht verfügbar.

## Datensicherung und Updates

- Das BMS sichert Ihre Datenbank einmal täglich automatisch, solange es läuft. In den **Einstellungen**, Karte „Datensicherung“, sehen Sie die letzte Sicherung und sichern mit „Jetzt sichern“ von Hand. Eine externe Sicherung, etwa mit Time Machine, ersetzt das nicht.
- Eine Sicherung spielen Sie bei beendetem BMS mit `wiederherstellen.command` (Mac) oder `wiederherstellen_windows.bat` (Windows) zurück. Das Werkzeug sichert vorher Ihren aktuellen Stand, sodass Sie das Zurückspielen mit demselben Werkzeug wieder rückgängig machen können. Es betrifft nur die Datenbank, Ihre Dokumente bleiben unverändert.
- In den **Einstellungen**, Karte „Programmversion“, fragt der Knopf „Nach Updates suchen“ bei GitHub nach der neuesten Version und zeigt, was sich darin ändert. Das geschieht nur auf Ihren Klick, GitHub erhält dabei die IP-Adresse Ihres Rechners. Einspielen tut der Knopf nichts.
- Neue Versionen spielen Sie bei beendetem BMS mit `update.command` (Mac) oder `update_windows.bat` (Windows) ein. Das Werkzeug lädt die neue Version selbst von GitHub und prüft sie; ohne Internet genügt die ZIP-Datei `BMS_<Version>.zip` im Ordner „Downloads“. Vorher entsteht eine Sicherung, bei einem Fehler macht das Werkzeug alles rückgängig.
- Die installierte Version steht im Fuß der Seitenleiste, die Änderungen je Version unter **Dokumentation**, Reiter „Version“.

## Beispieldaten und Dokumentation

- Eine neue Installation startet mit Beispieldaten von Benno Bewerbaer, einer fiktiven Person mit fünf Jahren Erfahrung in der Paketzustellung: Stellen, Firmen, Mails, Profil und Basis-Lebenslauf.
- Entfernen Sie die Beispieldaten in den **Einstellungen** mit „Beispieldaten entfernen“, bevor Sie eigene Daten eintragen. Vorher legt das BMS automatisch eine Sicherung an. Eigene Einträge bleiben erhalten.
- Alle Anleitungen stehen unter **Dokumentation** in der Seitenleiste.

Jeden Bereich beschreibt die [Anleitung](ANLEITUNG.html) im Detail.
