# Änderungen

Hier steht zu jeder Version, was sich für Sie ändert. Welche Version installiert ist, sehen Sie unten in der Seitenleiste und in den Einstellungen unter „Programmversion“.

## Unveröffentlicht

## 2.2.1 (06.11.2026)

- Das Programmpaket hängt an jeder Version jetzt zusätzlich unter dem festen Namen `BMS_latest.zip`, samt Prüfsumme. Der Download-Link auf bms.daube.tech zeigt damit immer auf die neueste Version. Für Installation und Update ändert sich nichts.

## 2.2.0 (06.11.2026)

- Das BMS gibt es jetzt auf Deutsch und Englisch: Oberfläche, Meldungen, Berichte, Exporte, Beispieldaten und Dokumentation. Umschalten können Sie in der Seitenleiste oder in den Einstellungen. Die KI-Berichte folgen dieser Einstellung, Lebenslauf und Anschreiben weiter der Sprache der Stellenanzeige.
- Lebenslauf und Anschreiben entstehen jetzt auch auf Französisch, Italienisch, Spanisch und Portugiesisch, wenn die Anzeige in dieser Sprache steht und Sie einen passenden Basis-CV hochgeladen haben. Fehlt er, nimmt das BMS die englische, sonst die deutsche Fassung, übersetzt nichts und nennt das im Bericht des Laufs. Fußzeile, Datum und Grußformel folgen der Sprache des Dokuments, Akzente bleiben in Dateinamen als Grundbuchstabe erhalten (`Société` wird `Societe`).
- Im englischen Anschreiben steht das Datum jetzt als `3 November 2026`.
- Geschlossene Anzeigen, Anmeldeseiten, Gender-Zusätze, Rechtsformen und Arbeitsmodelle werden auch in diesen vier Sprachen erkannt. Die Postfach-Suche sucht zusätzlich nach Wörtern in diesen Sprachen, sobald Sie dort einen Basis-CV oder eine laufende Bewerbung haben.
- Neue Installationen starten im Suchprofil ohne Mindest-Seniorität. Ein vorhandener Wert bleibt.
- Meldungen im Terminal (Update, Start, Stopp, Wiederherstellen, Server-Fenster) folgen der Sprache Ihres Systems: Deutsch auf einem deutschen System, sonst Englisch.
- Die Seite des Projekts auf GitHub ist jetzt auf Englisch, eine deutsche Fassung ist einen Klick entfernt. Im Programmpaket steht das README in beiden Sprachen.
- Die Seiten Netzwerk, Firmen und Radar haben oben ein Suchfeld, das die Liste schon beim Tippen eingrenzt.
- Der Beirat zeigt auf Englisch auch die Titel früherer deutscher Stellen-Checks englisch. Inhalte früherer Debatten lassen sich mit `python -m pipeline.beirat_uebersetzen` übersetzen, die Originale bleiben erhalten.
- Im Task-Center zählen die Kacheln jetzt alle Läufe. Bisher blieben „Läufe gesamt“, „Fehlgeschlagen“ und die Kosten bei den letzten 100 stehen. Die Liste zeigt weiter die letzten 100 und sagt das, der Filter „Fehlgeschlagen“ reicht jetzt auch weiter zurück.
- Firmenprüfung, CV-Match, CV erstellen und Anschreiben melden jetzt einen Fehler, wenn der Lauf endet, ohne sein Ergebnis anzulegen. Bisher galten sie als erfolgreich.
- Im Tages-Digest zeigt „Heute geändert“ jetzt auch die Änderungen kurz nach Mitternacht. Bisher fehlten sie den ganzen Tag, in Deutschland die der ersten ein bis zwei Stunden.
- Mails aus Gmail, deren Absender eine ältere Zeichenkodierung angibt (etwa Outlook mit ISO-8859-1), kommen beim Postfach-Check jetzt mit richtigen Umlauten und Akzenten an. Bisher stand dort „Ã¤“ statt „ä“, was das Einordnen solcher Antworten erschweren konnte.

## 2.1.0 (02.11.2026)

- Das BMS läuft jetzt wahlweise mit Claude oder als Vorschau mit ChatGPT. Die Wahl treffen Sie bei der Installation oder unter „Einstellungen“ auf der Karte „KI“. Unter ChatGPT nutzt das BMS Ihr ChatGPT-Abo über die Codex-Kommandozeile (`codex login`), und die Inhalte der KI-Läufe gehen an OpenAI statt an Anthropic. Kosten in USD und eine Budgetgrenze je Lauf gibt es dort nicht, es gelten die Grenzen Ihres Abos. Wer Claude nutzt, muss nichts tun.
- Skills sind von Annahmen zu einem bestimmten Beruf befreit und überspringen optionale Dateien, statt abzubrechen.
- LinkedIn-Profil übernehmen geht jetzt sofort: Unter „Profil“ fügen Sie den Text Ihres Profils ein oder laden das PDF hoch, das LinkedIn über „Als PDF speichern“ erzeugt. Ihre KI strukturiert den Text, Sie prüfen das Ergebnis in einer Vorschau, und erst dann ergänzt das BMS Ihr Profil. Der bisherige Knopf „Profil einlesen“ über die Adresse entfällt, weil LinkedIn solche Abrufe sperrt. Der Datenexport bleibt der vollständigste Weg.
- Der Block „Zielrolle“ auf der Profil-Seite ist entfallen, er doppelte sich mit den Suchplänen. Titel, Ebene und Branche tragen Sie unter „Einstellungen“ ein, auf der Profil-Seite bleibt der Zieltermin. Vorhandene Angaben in Ihrer Profil-Datei bleiben stehen. Weichen sie ab, gelten die Suchpläne.
- Sicherheit: Mitgelieferte Bausteine sind aktualisiert, darunter `certifi` (Stammzertifikate), `urllib3`, `cryptography`, `oauthlib` und `pyasn1` sowie React Router und Vite in der Oberfläche. Das Update installiert sie automatisch, es kann deshalb etwas länger dauern.
- Beim manuellen Anlegen einer Stelle warnt das BMS jetzt schon beim Ausfüllen: „URL bereits erfasst in Stelle …“ oder „Stelle bereits erfasst“, mit Link zur vorhandenen Stelle. Die URL wird dabei ohne Tracking-Zusätze verglichen, Firma und Titel auch in anderer Schreibweise, etwa ohne Rechtsform oder „(m/w/d)“.
- Gelöschte Stellen zählen beim manuellen Anlegen nicht mehr als vorhanden: Eine gelöschte Stelle lässt sich von Hand neu erfassen. Die automatische Suche holt sie weiterhin nicht von selbst zurück.
- Die Seniorität kennt jetzt alle üblichen Stufen, von Praktikant, Werkstudent, Auszubildender und Trainee über Berufseinsteiger, Angestellter, Erfahrener Mitarbeiter und Experte bis C-Level. Das gilt für das Formular „Neue Stelle“, die Eckdaten einer Stelle und als Vorschläge in den Suchplänen.
- Beim Basis-Lebenslauf steht Portugiesisch jetzt direkt in der Sprachauswahl.
- Die Beispieldaten einer neuen Installation gehören jetzt Benno Bewerbaer. Vorhandene Beispieldaten bleiben, wie sie sind, und lassen sich weiter entfernen.
- Die Installationsanleitungen nennen den Knopf „Company-Fit prüfen“ so, wie er im Programm heißt.

## 2.0.0 (01.11.2026)

- Unter „Rechtliches“ lassen sich Internetadressen jetzt anklicken, etwa der Link zum Quelltext bei GitHub in „Über dieses Programm“ und der zur Datenschutzerklärung von GitHub. Sie öffnen sich in einem neuen Tab.
- Windows: Die Installationsanleitung schlägt jetzt den Ordner `BMS` in Ihrem Benutzerordner vor (`%USERPROFILE%\BMS`, wie beim Mac) statt im Programme-Ordner. Dort können andere Benutzerkonten des Rechners Ihre Daten und Lebensläufe nicht lesen, und das Anlegen braucht keine Administrator-Rechte mehr. Eine bestehende Installation bleibt, wo sie ist.
- Windows: Das Fenster des BMS bleibt nach dem Start sichtbar. Bisher konnte es nach einer Sekunde verschwinden, dann ließ sich das BMS nur noch über den Task-Manager beenden. Endet der Server mit einem Fehler, bleibt das Fenster mit der Meldung offen.
- Windows: `stop_windows.bat` findet das laufende BMS jetzt auch auf einem deutschen Windows und fragt wieder nach, bevor es laufende Agent-Läufe abbricht.
- Die Installationsanleitungen prüfen den Zugangsschlüssel genauer: Bleibt das Beispiel `sk-ant-oat01-...` in der Zeile stehen, meldet die Prüfung jetzt „fehlt“ statt „vorhanden“. Unter Windows ermittelt die Anleitung den echten Ordner „Downloads“, auch wenn OneDrive ihn umleitet, prüft Windows-Version und Bauart und erklärt die Rückfrage „Batchvorgang abbrechen (J/N)?“ beim Beenden.

## 1.9.0 (29.10.2026)

- Das BMS wird nicht mehr verkauft, sondern ist Open Source unter der Apache License 2.0 (Dateien `LICENSE` und `NOTICE` im Programmordner). Unter „Rechtliches“ stehen jetzt „Über dieses Programm“ mit Herausgeber und Haftungshinweis, der Wortlaut der Lizenz, Datenschutz und die Drittanbieter-Lizenzen. Nutzungsbedingungen (AGB/EULA), Widerrufsbelehrung, Vertriebs-Checkliste und das Impressum in der App sind entfallen; das Impressum steht auf daube.tech.
- Das BMS braucht keine Lizenz mehr. Alle Funktionen stehen Ihnen ohne Lizenzdatei zur Verfügung; Suchen, KI-Auswertungen und Änderungen sind nie mehr gesperrt. Die Beschränkung auf Ansehen und Exportieren ohne Lizenz, das Band über den Seiten und die Karte „Lizenz“ in den Einstellungen gibt es nicht mehr. Eine vorhandene Lizenzdatei (`lizenz.json`, gegebenenfalls auch `lizenz_stand.json` im Ordner `.bewerbung_mgmt_secrets` in Ihrem Benutzerordner) wird nicht mehr gebraucht. Sie dürfen sie löschen; das BMS löscht sie nicht von selbst.
- Neu in den Einstellungen, Karte „Programmversion“: der Knopf „Nach Updates suchen“. Er fragt bei GitHub nach der neuesten Version und zeigt, ob es eine neuere gibt, mit Datum, Änderungen und einem Link zur Seite bei GitHub. Er fragt nur, wenn Sie darauf klicken. GitHub erhält dabei die IP-Adresse Ihres Rechners, sonst nichts. Eingespielt wird eine neue Version weiterhin mit `update.command` bzw. `update_windows.bat`.
- Das Update-Werkzeug (`update.command` bzw. `update_windows.bat`) lädt neue Versionen jetzt von GitHub und prüft das Paket mit der Prüfsumme von GitHub. Vor der Suche schreibt es, dass GitHub die IP-Adresse des Rechners erhält. Mit `--offline` sucht es nicht online, eine ZIP-Datei im Ordner „Downloads“ findet es weiterhin. Die Installationsanleitungen laden das Programmpaket ebenfalls von GitHub; der Schritt „Lizenz einspielen“ entfällt.
- Installationen bis Version 1.7.0 suchen weiter auf dem früheren Server des Anbieters und finden diese Version dort nicht. Laden Sie für den Wechsel einmal die Datei `BMS_<Version>.zip` von https://github.com/holgerdaube/BewerbungsMgmtSystem/releases/latest in den Ordner „Downloads“, beenden Sie das BMS und doppelklicken Sie `update.command` bzw. `update_windows.bat`. Danach sucht das Werkzeug selbst bei GitHub.
- Berichte, die Claude für Sie schreibt (Match-Dashboard, ATS-Scan, Briefing, Absagen-Analyse, Angebotsvergleich), bekommen ihr Aussehen jetzt in einem festen Arbeitsschritt. Bisher schrieb Claude die Gestaltung bei jedem Bericht neu ab, dabei gingen gelegentlich Teile verloren. Neue Berichte sehen dadurch von Lauf zu Lauf gleich aus. Im Match-Dashboard zeigt das Keyword-Protokoll jetzt dieselben Farben wie im ATS-Scan. Bereits erzeugte Berichte bleiben, wie sie sind.
- Bremst LinkedIn die Abrufe, versucht das BMS es jetzt mehrmals mit Pausen, statt die Anzeige als „nicht abrufbar“ zu speichern. Suchläufe können dadurch etwas länger dauern.
- Fehlt einer Stelle der Anzeigentext, holt das BMS ihn vor Firma-Prüfung, CV-Match, CV und Anschreiben nach. Klappt das nicht, fragt es, ob der Lauf trotzdem starten soll.
- Ob ein Portal noch Bewerbungen annimmt, prüfen Firma-Prüfung und Beworben-Check jetzt mit demselben Abruf wie die Suchläufe, mit Wiederholung bei Drosselung. Geschlossene LinkedIn-Anzeigen erkennt das BMS jetzt auch auf deutschen Seiten.
- Antwortet ein Portal auf automatische Abrufe gar nicht (etwa StepStone), meldet das BMS „nicht prüfbar“ statt „nicht mehr online“. Treffer aus Job-Mails bleiben dadurch erhalten.
- In „Neu / Review“ ist „Jobsuche + Apify“ jetzt genauso aufgebaut wie die Jobsuche daneben: großer Knopf, darunter in zwei Zeilen Status und Herkunft sowie Dauer, Turns und Kosten, dann die Abschlussmeldung des letzten Laufs. Die Meldungen beider Suchen stehen auf einer Höhe.
- Unter Rechtliches → Drittanbieter-Lizenzen stehen jetzt alle Open-Source-Pakete, die das BMS mitinstalliert, mit Version und Lizenz. Den vollständigen Wortlaut der Lizenzen zeigt der Knopf „Lizenztexte anzeigen“. Die Datenschutzerklärung beschreibt die Jobsuche der Arbeitsagentur jetzt richtig.
- Die Budget-Seite zeigt den Eintrag „Perplexity (Suche)“ nicht mehr. Das BMS hat diesen Dienst nie aufgerufen.
- Die Coach-Site hat neben der Übersicht den Reiter „Tages-Digest“. Er zeigt neue Treffer, Absagen und Bewerbungen der letzten vier Tage und die Änderungen des Tages und wird mit jedem Tageslauf hochgeladen. Mails, die auf Antwort warten, Ihre offenen Aktionen und Ihre Notizen enthält er nicht. Unter „Absagen & Muster“ steht beim Muster-Bericht jetzt sein Datum.
- Die Absagen-Analyse läuft jetzt einmal pro Woche im Tageslauf. Das kostet einen Modell-Lauf pro Woche, an den übrigen Tagen überspringt der Tageslauf den Schritt ohne Kosten. Auf dem Dashboard führt ein Link zum neuesten Bericht, ein Knopf startet die Analyse von Hand. Die Empirie-Zeilen in Ihrem Profil, die in Jobsuche und Unterlagen einfließen, ersetzt nur ein Start von Hand; der Wochenlauf schreibt seinen Vorschlag in den Bericht. Scheitert die Analyse, laufen die übrigen Schritte des Tageslaufs trotzdem.
- Der Gmail-Check findet jetzt auch persönliche Mails von Firmen, bei denen Sie sich beworben haben, wenn Betreff und Absender keines der üblichen Stichworte tragen, etwa eine Absage direkt vom Recruiter. Dafür durchsucht er zusätzlich die Absender-Domains Ihrer laufenden Bewerbungen. Große Jobportale wie LinkedIn bleiben dabei außen vor. Kommt eine Mail von einem Kontakt, der bisher ohne E-Mail-Adresse gespeichert war, trägt das BMS die Adresse dort nach, statt den Kontakt doppelt anzulegen.
- Die mitgelieferten Bewertungsregeln (`config/scoring_rubrik.md`) richten die Ebene jetzt nach Ihren Einstellungen: Nennt Plan A unter „Seniorität“ auch Manager oder Senior Manager, zählt eine solche Rolle mit Teamführung zu Plan A und nicht mehr zum Auffang-Plan C. Haben Sie die Datei selbst angepasst, bleibt Ihre Fassung erhalten.
- Der Excel-Export hat das neue Blatt „Bewerbungen“ gleich hinter „Stellen“. Es zeigt jede Stelle, auf die Sie sich beworben haben, in einer Zeile: Firma, Bezeichnung, Fit, Match-100, ATS, gefunden am, beworben am, das Datum jeder Gesprächsrunde (Runde 1 bis 6) und das Absagedatum. Die neueste Bewerbung steht oben. Hat ein Gespräch keinen Termin, nimmt das BMS das Datum seines Transkripts. Als Absagedatum gilt der Tag der Absage-Mail, ohne Mail der Tag, an dem die Stelle auf „Absage“ gesetzt wurde.
- Der Tages-Digest hat oben links den Link „← Zurück zum Dashboard“. Bisher führte aus dem Digest nur der Zurück-Knopf des Browsers wieder in die App.
- Unter „Rechtliches“ → „Über dieses Programm“ steht jetzt ein Hinweis zur KI: Texte, Bewertungen und Entwürfe erzeugt das BMS mit KI (Claude), Sie sind Vorschläge und müssen vor dem Versand geprüft werden.
- Im Reiter „Datenschutz“ entfällt der Abschnitt „Kontakt für Datenschutzfragen“, in „Über dieses Programm“ der Impressum-Eintrag beim Herausgeber. Für Ihre Daten ändert sich nichts: Der Herausgeber erhält aus der Nutzung des BMS keine Daten.

## 1.7.0 (13.10.2026)

- Die Suchläufe sortieren eine Stelle nur noch aus, wenn Anzeige oder Mail eine Ihrer harten Grenzen belegt verletzen. Hybrid-Stellen außerhalb Ihres Umkreises erscheinen unter „Deutschlandweit“, und Stellen mit schwacher Passung werden mit Score 1 oder 2 angelegt statt weggelassen. In der Review-Ansicht kommen dadurch wieder deutlich mehr Stellen an; die Mail-Jobsuche prüft dafür mehr Anzeigen und läuft entsprechend länger.
- Die Suchportale Nejo und Arbeitsagentur haben neue Adressen. Das BMS stellt die vorbelegten Adressen beim nächsten Start selbst um; eine Adresse, die Sie selbst geändert haben, bleibt unverändert. Die Schaltfläche zum Prüfen eines Portals zeigt jetzt Gelb, wenn eine Adresse nur noch auf eine andere weiterleitet, und nennt die neue.
- Die Jobsuche wertet bei Nejo im Suchbereich „Remote“ jetzt auch Stellen mit Homeoffice-Anteil aus: Liefert Nejos eigener Remote-Filter kaum Treffer, wird dieselbe Suche einmal ohne ihn wiederholt. Bei der Arbeitsagentur werden alle hinterlegten deutschen Titel abgefragt, nicht mehr nur die ersten beiden. Beides wirkt nur, wenn Sie dafür Feinparameter in der Suchprofil-Datei hinterlegt haben.
- Die Installation lädt das Programmpaket jetzt selbst: Die Anleitung holt es mit Ihrer Lizenzdatei von bms.daube.tech, eine ZIP-Datei brauchen Sie dafür nicht mehr. Dabei geht Ihre Lizenzdatei an den Anbieter, sonst nichts, und nur, wenn Sie den Ladebefehl selbst ausführen. Eine ZIP-Datei im Ordner „Downloads“ bleibt als zweiter Weg.
- Das Update-Werkzeug (`update.command` bzw. `update_windows.bat`) sucht jetzt online nach einer neuen Version und lädt sie. Vorher schreibt es, dass Ihre Lizenzdatei an bms.daube.tech übertragen wird, sonst nichts. Mit `--offline` sucht es nicht online. Eine ZIP-Datei im Ordner „Downloads“ findet es weiterhin, die höchste Version gewinnt. Endet Ihr Anspruch auf Aktualisierungen, bekommen Sie die letzte Version bis dahin und einen Hinweis auf die neuere. Die Lizenzprüfung selbst läuft weiter ohne Internet. Die Datenschutzerklärung und die Anleitung zur Lizenz beschreiben den neuen Kontakt zum Anbieter.
- Die Installationsanleitung gibt es jetzt je System: `BMS_Install_MAC.md` für macOS und `BMS_Install_Windows.md` für Windows. Beide führen mit Claude durch die Installation und enthalten danach das Einrichten, das Aktualisieren, die Hilfe und die Angaben zu Ihren Daten. Sie ersetzen `BMS_Install.md` und `BMS_Install_Auto.md`; das Update entfernt die beiden alten Dateien.

## 1.6.3 (11.10.2026)

- Die Installationsanleitung ist neu gegliedert: Teil 1 beschreibt die Installation unter macOS, Teil 2 die unter Windows, ab Teil 3 gilt alles für beide Systeme. Verweise in den übrigen Anleitungen nennen jetzt diese Teile.
- Unter Windows schlägt die Installation jetzt den Ordner `BMS` im Programme-Ordner vor (in der Regel `C:\Program Files\BMS`) und richtet dort einmalig Schreibrechte für Ihr Benutzerkonto ein. Ihre bestehende Installation bleibt, wo sie ist.
- Die Installation prüft jetzt zuerst, ob es auf dem Rechner schon ein BMS gibt, installiert nur Programme, die noch fehlen, und überschreibt einen vorhandenen Zugangsschlüssel nicht mehr. Warnungen beim Bauen der Oberfläche sind als unbedenklich erklärt.
- Neu auf der Seite „Profil“: die Karte „Identität und Suchstrategie“. Dort tragen Sie Name, Anschrift, E-Mail, Telefon, LinkedIn, Kurzprofil, Zielrolle, harte Rahmenbedingungen und bekannte Skill-Gaps direkt in der Oberfläche ein, statt die Datei `config/profil.md` von Hand anzulegen. Speichern schreibt diese Datei. Was die Karte nicht kennt, etwa der Abschnitt „Empirie aus dem Bewerbungsverlauf“ oder eigene Abschnitte, bleibt unverändert, und die vorherige Fassung landet im Papierkorb. Wurde die Datei zwischenzeitlich geändert, bittet die Karte um Neuladen. Ohne Lizenz können Sie die Karte ansehen, aber nicht speichern. Eine vorhandene Profil-Datei zeigt die Karte an und ändert sie erst, wenn Sie speichern. Die Installationsanleitung und die Anleitung beschreiben den neuen Weg.

## 1.6.2 (11.10.2026)

- Die Installationsanleitung fragt jetzt, in welchen Ordner das BMS installiert werden soll, und setzt Ihre Antwort in die weiteren Befehle ein. Vorgeschlagen bleibt `~/BMS` (Mac) bzw. `C:\BMS` (Windows). Für Ihre bestehende Installation ändert sich nichts.
- Neu im Paket: `BMS_Install_Auto.md`. Damit führt Sie Claude unter Windows Schritt für Schritt durch die Installation.
- Die Anleitungen sagen jetzt richtig, dass Lizenzen aus der Zeit vor Version 1.6.1 nicht mehr gelten.

## 1.6.1 (09.10.2026)

- Der frühere Prüfschlüssel ist gesperrt. Lizenzen, die damit ausgestellt wurden, gelten nicht mehr. Meldet die Karte „Lizenz“ in den Einstellungen nach dem Update einen gesperrten Schlüssel, fordern Sie bitte beim Anbieter eine neue Lizenz an. Haben Sie Ihre Lizenz schon neu erhalten und eingespielt, ändert sich für Sie nichts.

## 1.6.0 (09.10.2026)

- Die Lizenzprüfung kennt jetzt mehrere Prüfschlüssel. Für Sie ändert sich nichts; Ihre Lizenz gilt weiter.
- Die Nutzungsbedingungen (unter „Rechtliches“) und die Anleitungen sagen jetzt einheitlich: Eine Lizenz gilt für eine Person, nicht für einen Rechner. Sie dürfen das BMS auf allen Rechnern nutzen, die Sie selbst verwenden, und spielen dort jeweils dieselbe Lizenzdatei ein. Bisher nannten die Nutzungsbedingungen an einer Stelle einen, an einer anderen zwei Rechner.

## 1.5.1 (09.10.2026)

- Die Anleitung zur Lizenz (Dokumentation, Reiter „Lizenz“) ist kürzer und übersichtlicher: die drei Lizenzarten, das Einspielen in drei Schritten, was im Ansichtsmodus geht und was gesperrt ist, und was das Band oben in der App jeweils anzeigt, jeweils in einer Tabelle. Technische Einzelheiten zum Lizenzformat stehen dort nicht mehr.

## 1.5.0 (09.10.2026)

- Das BMS braucht jetzt eine gültige Lizenz, damit Suchen, KI-Auswertungen und Änderungen laufen. Ohne Lizenz arbeitet es im Ansichtsmodus: Sie sehen weiterhin alles, öffnen Berichte, Lebensläufe und Anschreiben, exportieren nach Excel, rufen den Tages-Digest ab, legen Sicherungen an und spielen sie zurück. Ihre Daten bleiben dabei vollständig erhalten. Gesperrt sind Suchläufe, KI-Auswertungen und Änderungen, auch im Terminal und in Skills. Versuchen Sie es trotzdem, nennt das BMS den Grund und führt Sie zum Einspielen der Lizenz. Es gibt drei Lizenzarten: die Kauflizenz (einmalig, unbefristet nutzbar, Updates 24 Monate ab Ausstellung), eine kostenlose Testlizenz für 14 Tage, die Sie beim Anbieter anfordern, und die befristete Lizenz für Unternehmen und Programme mit 6 oder 12 Monaten. Eine neue Installation startet im Ansichtsmodus, bis Sie Ihre Lizenz einspielen. Ein Band oben auf jeder Seite zeigt den Stand: im Ansichtsmodus mit Links zum Einspielen und Kaufen, bei der Testlizenz mit den verbleibenden Tagen, bei einer befristeten Lizenz in den letzten 14 Tagen mit dem Ablaufdatum. Die Karte „Lizenz“ in den Einstellungen nennt Art, Gültigkeit und Update-Zeitraum. Bereits ausgestellte Lizenzen gelten unverändert weiter, als unbefristete Kauflizenz. Bei Test- und befristeten Lizenzen behandelt das BMS ein zurückgestelltes Systemdatum als abgelaufen.

## 1.4.0 (05.10.2026)

- Eine Sicherung spielen Sie jetzt mit einem Werkzeug zurück, statt Dateien von Hand zu tauschen: Beenden Sie das BMS und doppelklicken Sie auf `wiederherstellen.command` (Mac) bzw. `wiederherstellen_windows.bat` (Windows). Das Werkzeug zeigt Ihre Sicherungen, prüft die gewählte und sichert vorher Ihren aktuellen Stand. Wenn Sie es sich anders überlegen, starten Sie es noch einmal und wählen den Eintrag „vor Wiederherstellung“. Es betrifft nur die Datenbank, Ihre Dokumente bleiben unverändert.
- Das Dashboard zeigt oben nur noch die Kacheln zu Stellen und Bewerbungen. Die Kachel „Firmen“ entfällt; Ihre Firmen erreichen Sie wie bisher über „Firmen“ in der Seitenleiste.
- Nach einem Update zeigt der Browser sofort die neue Oberfläche. Bisher konnte eine Seite, die Sie schon einmal geöffnet hatten, etwa über ein Lesezeichen, danach noch eine Weile die alte Fassung zeigen oder leer bleiben. Beim Update auf diese Version kann das ein letztes Mal vorkommen: Laden Sie eine solche Seite dann einmal neu (Mac: ⌘ + R, Windows: F5).

## 1.3.0 (01.10.2026)

- Zielfirmen, Headhunter und Netzwerk-Kontakte importieren Sie jetzt aus einer Datei: In „Netzwerk“ steht dafür in jedem Reiter der Knopf „Aus Datei importieren“. Er liest CSV- und Excel-Dateien, erkennt die Spalten an ihrer Überschrift und bietet je Liste eine Vorlage zum Herunterladen. Für Netzwerk-Kontakte funktioniert auch die Datei Connections.csv aus dem LinkedIn-Datenexport. Eine Vorschau zeigt vorher, was neu angelegt, ergänzt oder übersprungen wird. Vorhandene Einträge ergänzt der Import nur in leeren Feldern, in der App gelöschte bleiben gelöscht, und vorher legt das BMS eine Sicherung an.
- Der Excel-Export und der Schritt „Ansichten aktualisieren“ im Tageslauf funktionieren jetzt auch, solange noch keine Stellen erfasst sind, etwa direkt nach dem Entfernen der Beispieldaten.
- Die Dateinamen von Berichten, Lebensläufen und Anschreiben sind kürzer: Das Datum steht als JJJJMMTT vorne, Firmennamen verlieren Klammerzusätze und Rechtsformen wie GmbH oder AG, lange Firmen- und Stellentitel werden an einer Wortgrenze gekürzt, und die Typen heißen Anzeige, Auswertung und Beirat. Ältere Dateien mit dem bisherigen Datumsformat erkennt das BMS weiterhin.
- Neu in der Seitenleiste: „Beirat“, direkt unter „Netzwerk“. Dort stellen Sie den sieben Köpfen Fragen ohne Bezug zu einer bestimmten Stelle; bisher war die Seite nur über ihre Adresse erreichbar. Sie nennt jetzt auch den Vorsitz, den Sie in den Einstellungen bestimmt haben.
- Der Menüpunkt „Outreach“ entfällt. Er zeigte eine Liste, die sich im BMS nicht füllen ließ; Ihre Kontakte pflegen Sie unter „Netzwerk“. Die Seite „Netzwerk“ beschreibt jetzt ihre drei Listen, statt auf eine Excel-Tabelle zu verweisen, die Headhunter-Liste zeigt nicht mehr überall die Quelle „Blatt“, und das Dashboard meldet nicht mehr dauerhaft „Netzwerk-Historie unvollständig“.

## 1.2.0 (01.10.2026)

- Neu in der Seitenleiste: „Dokumentation“. Dort lesen Sie die Änderungen je Version, eine Übersicht der Funktionen, die Anleitung und die Hilfen zu Installation und Updates, E-Mail, Windows, Coach-Site, Beirat und Lizenz, ohne das BMS zu verlassen.
- Eine neue Installation startet mit Beispieldaten, damit Sie das BMS gleich ausprobieren können: Birne Helene, Postbote mit 5 Jahren Erfahrung in der Paketzustellung, mit Profil, Basis-Lebenslauf, fünf Stellen in verschiedenen Stadien, Mails und einem Gesprächstermin. Bevor Sie eigene Daten eintragen, entfernen Sie die Beispieldaten in den Einstellungen mit einem Klick. Vorher legt das BMS eine Sicherung an, und Ihre eigenen Einträge bleiben erhalten. Bestehende Installationen bekommen keine Beispieldaten.
- In den Einstellungen wählen Sie je Funktion zwischen Opus 5.5, Sonnet 5.5 und Haiku 4.5, voreingestellt ist Sonnet 5.5. Fable 5.1 steht nicht mehr zur Wahl, weil es das Zweieinhalbfache von Opus 5.5 und das Fünffache von Sonnet 5.5 kostet. Wo Sie Fable gewählt hatten, arbeitet das BMS jetzt mit Sonnet 5.5. Auch die übrigen KI-Läufe, etwa die Mail-Prüfung und die Fragen zu einer Stelle, laufen mit Sonnet 5.5, unabhängig vom Standardmodell Ihrer Claude-Installation.
- Die Seitenleiste zeigt oben „Bewerbungs-Management-System“ und darunter Ihren Namen, unten steht die installierte Version.
- Die Windows-Anleitung (Dokumentation, Reiter „Windows“) folgt jetzt der Einrichtung aus dem Programmpaket und nennt genauer, was unter Windows noch nicht geht. So endet der Tageslauf unter Windows mit einem fehlgeschlagenen Schritt „Ansichten aktualisieren“; Excel-Export, Tages-Digest und Suchindex holen Sie dort über die Knöpfe in Dashboard und Suche.

## 1.1.3 (29.09.2026)

- Andere Webseiten, die Sie im selben Browser geöffnet haben, können im BMS nichts mehr auslösen, etwa Stellen verwerfen, Ihren Basis-Lebenslauf ersetzen oder Sicherungen anlegen, und Ihre Daten auch nicht über einen umgeleiteten Adressnamen lesen. Dazu antwortet das BMS nur noch unter localhost, einer IP-Adresse, einem Namen auf .local oder einem Rechnernamen ohne Punkt. Die Adressen, die das Startfenster im WLAN-Modus anzeigt, funktionieren wie bisher; weitere Namen geben Sie mit der Umgebungsvariablen BMS_HOSTS frei.
- Berichte, die Sie aus dem BMS öffnen (Company-Fit, Match-Dashboard, ATS-Scan, Stellenausschreibung, Briefing, Beirats-Check, Analyse, Transkript-Bericht), und der Tages-Digest laufen im Browser getrennt vom BMS. Ein Skript, das über recherchierte Webinhalte in einen Bericht geraten ist, kann damit Ihre Daten nicht mehr lesen und nichts mehr verändern. Die Berichte sehen aus wie bisher, Quellen und Original-Anzeigen öffnen weiter in einem neuen Tab, und Drucken funktioniert wie gewohnt.

## 1.1.2 (28.09.2026)

- Im WLAN-Modus (`start_lan.command`) kann ein Gerät im selben Netz Ihre Datenbank und Ihre Sicherungen nicht mehr in den Papierkorb schieben und über die Suche keine anderen Dateien Ihres Rechners mehr einsehen. Beim Löschen wandern nur noch Ihre Unterlagen in den Papierkorb: Berichte, Lebensläufe, Anschreiben, Stellenausschreibungen und Dateien an Stellen und im Profil. Löschen, Lebensläufe und Anschreiben arbeiten wie bisher.

## 1.1.1 (28.09.2026)

- Das BMS gibt nur noch die Dokumente heraus, die Sie in der Oberfläche öffnen: Berichte, Lebensläufe, Anschreiben, Stellenausschreibungen, Dateien an Stellen und im Profil sowie Transkripte. Ihre Datenbank, Ihre Sicherungen und andere Dateien Ihres Rechners lassen sich darüber nicht mehr abrufen. Bisher konnte im WLAN-Modus (`start_lan.command`) jedes Gerät im selben Netz mit einer passenden Adresse die komplette Datenbank herunterladen.
- Andere Webseiten, die Sie im selben Browser geöffnet haben, können Ihre Daten im BMS nicht mehr lesen und keine Stellen mehr löschen. Bisher gab das BMS seine Schnittstelle für jede Webseite frei. Oberfläche, WLAN-Modus und KI-Läufe arbeiten unverändert.

## 1.1.0 (28.09.2026)

- Das BMS sichert Ihre Datenbank einmal täglich automatisch, solange es läuft, als ZIP-Datei im Ordner `data/backups/auto`. Es bewahrt je eine Sicherung der letzten 7 Tage und 4 Wochen auf und entfernt ältere automatische Sicherungen selbst. In den Einstellungen unter „Datensicherung“ sehen Sie die letzte Sicherung, ändern die Aufbewahrung und sichern auf Knopfdruck.
- Mails ohne Stelle, die nichts mit Ihren Bewerbungen zu tun haben, archivieren Sie in der Inbox mit einem Klick. Sie verschwinden aus der Inbox, aus der Mail-Zahl im Dashboard und aus dem Tagesbericht. Im Archiv holen Sie sie jederzeit zurück. In Gmail bleiben sie unverändert.
- Zwischendateien der KI-Läufe entfernt das BMS nach 30 Tagen selbst, mit derselben Frist wie die Protokolle der Läufe. Dateien, die zu gespeicherten Unterlagen gehören, bleiben erhalten.

## 1.0.0 (28.09.2026)

- Erste freigegebene Version des Bewerbungs-Management-Systems.
- Updates spielen Sie mit `update.command` (Mac) oder `update_windows.bat` (Windows) ein. Ihre Daten, Einstellungen und Anpassungen bleiben dabei erhalten, vorher entsteht eine Sicherung.
- Der Umkreis-Filter trägt Stadt und Radius aus Ihren Einstellungen. Programmdateien müssen Sie dafür nicht mehr anpassen.
- In den Einstellungen wählen Sie je Funktion zwischen Fable 5.1, Opus 5.5, Sonnet 5 und Haiku 4.5. Voreingestellt bleibt Sonnet 5.
- Die Einstellungen zeigen die installierte Version und die Änderungen dieser Version.
