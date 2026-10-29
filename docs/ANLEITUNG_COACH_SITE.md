# Coach-Site einrichten — Schritt für Schritt

Diese Anleitung richtet sich an alle, die noch nie eine Subdomain angelegt oder Dateien per
SFTP (dazu gleich mehr) hochgeladen haben. Du brauchst keine Programmierkenntnisse. Fast alles
passiert in der App, in den **Einstellungen**; nur ganz am Ende gibt es einen einzigen
Terminal-Befehl für den Notfall.

Alle Bildschirmtexte in dieser Anleitung sind die echten Beschriftungen aus der App. Adressen,
Benutzernamen und Passwörter sind überall **Platzhalter** (z. B. `access-xyz.webspace-host.com`)
— trag dort deine eigenen Werte ein.

---

## Was ist die Coach-Site?

Die Coach-Site ist eine eigene, passwortgeschützte Webseite, auf der dein Coach deinen
Bewerbungsstand einsehen kann — ohne Zugriff auf die App selbst zu bekommen. Die Seite wird
automatisch aus deinen Daten erzeugt und ist eine reine Momentaufnahme: dein Coach kann nichts
verändern, nur lesen.

**Was dein Coach sieht:**
- Eine Übersicht mit Kennzahlen (wie viele Stellen, wie viele laufende Bewerbungen usw.)
- Den Tages-Digest: neue Treffer, Absagen und Bewerbungen der letzten vier Tage und was sich
  am Tag des Laufs geändert hat. Er wird mit jedem Tageslauf neu erzeugt. Anders als dein eigener
  Digest in der App enthält er weder die Mails, die auf Antwort warten, noch deine offenen
  Aktionen; bei Änderungen nennt er nur Statuswechsel, nie den Text deiner Notizen.
- Die Liste deiner Stellen und Bewerbungen — aktive Bewerbungen (Beworben/Interview/Angebot)
  und die Stellen, die du noch prüfst — je Stelle mit Company-Fit-Analyse, CV-Match und der
  Stellenausschreibung selbst
- Deine Absagen mit den erfassten Absagegründen und den neuesten Muster-Bericht der
  Absagen-Analyse mit seinem Datum (er wird einmal je Woche im Tageslauf erneuert)

**Was dein Coach garantiert NIE sieht:** deine E-Mails, deine privaten Notizen und den
Bewerbungsverlauf, Beirats-Auswertungen, Gehaltsangaben, interne Prüfvermerke, Interview-
Transkripte/Debriefs/Briefings, deine CVs und Anschreiben als Dateien, ATS-Scans, dein Netzwerk
und deine Kontakte. Diese Sperrliste ist fest im Code verankert und automatisiert getestet —
sie lässt sich nicht versehentlich aufweichen.

## Sicherheit auf einen Blick

- Deine Zugangsdaten (SFTP-Passwort, Coach-Zugang) landen **ausschließlich lokal** auf deinem
  Rechner unter `~/.bewerbung_mgmt_secrets/` — nie im Projektordner, nie in einem Git-Repository.
- Das Coach-Passwort wird **nur als Hash** gespeichert (eine Art digitaler Fingerabdruck, aus
  dem sich das Passwort nicht zurückrechnen lässt). Selbst du kannst es dir hinterher nicht
  wieder anzeigen lassen — hast du es vergessen, vergib einfach ein neues (siehe unten
  „Passwort ändern").
- Die Seite ist für Suchmaschinen gesperrt (kein Google-Fund). Das schützt aber nicht vor
  Weitergabe: **Wer Adresse und Passwort kennt, sieht den Inhalt.** Gib beides nur direkt und
  vertraulich an deinen Coach weiter — nicht in einer öffentlichen Nachricht, einem Forum oder
  Social-Media-Post.

## Voraussetzungen

Bevor es losgeht, brauchst du:

1. **Ein eigenes Webhosting-Paket mit eigener Domain**, bei dem du selbst Subdomains anlegen
   kannst (dazu gleich mehr). Fast jedes Hosting-Paket (IONOS, Strato, All-Inkl, …) kann das.
2. **Einen SFTP-Zugang** zu diesem Hosting. SFTP ist ein sicherer, verschlüsselter Kanal, über
   den Dateien auf deinen Webspace hochgeladen werden — vergleichbar mit einer verschlüsselten
   Kopierverbindung. Jedes Hosting-Paket bringt das mit.
3. **Das Programm `lftp` lokal installiert** — es erledigt im Hintergrund den eigentlichen
   Upload. Ohne `lftp` funktionieren weder „Verbindung testen" noch das spätere Hochladen. Auf
   dem Mac installierst du es im Terminal mit:
   ```
   brew install lftp
   ```
   (Fehlt der Befehl `brew` selbst, ist zuerst Homebrew nötig — Installationsanleitung auf
   https://brew.sh. Auf einem bereits eingerichteten BMS-Rechner ist Homebrew in aller Regel
   schon vorhanden.)
4. Einen Browser mit einem privaten Fenster/Inkognito-Fenster (für den Abnahme-Schritt am
   Ende).

---

## Schritt 1 — Subdomain anlegen und SSL aktivieren

Eine **Subdomain** ist ein zusätzlicher Adressteil vor deiner Domain, z. B. `coach.` vor
`meine-domain.de` — ein eigener, abgetrennter Bereich innerhalb deiner Webseite, mit eigenem
Verzeichnis auf dem Server.

Das folgende Beispiel zeigt IONOS; bei anderen Hostern heißen die Menüpunkte leicht anders,
der Ablauf ist aber praktisch überall gleich: Subdomain anlegen → Zielverzeichnis festlegen →
SSL aktivieren.

**Was du tust (IONOS-Beispiel):**
1. Im IONOS-Kundencenter einloggen → Menü „Domains & SSL" → deine Domain auswählen.
2. „Subdomain anlegen" wählen, z. B. `coach` eingeben → ergibt `coach.meine-domain.de`.
3. Als Verwendung/Ziel „Webspace" wählen und ein Zielverzeichnis eintragen, z. B. `/coach`.
   **Diesen Ordnernamen dir merken** — er kommt in Schritt 3 wieder als „Zielverzeichnis" vor.
4. In der Zeile der neuen Subdomain SSL aktivieren (Button/Toggle „SSL aktivieren", meist im
   Paket kostenlos enthalten). SSL sorgt dafür, dass die Seite verschlüsselt über `https://`
   erreichbar ist — Pflicht, weil sonst das Passwort deines Coaches beim Einloggen unverschlüsselt
   übertragen würde.
5. Etwas warten (meist wenige Minuten, selten bis zu einer Stunde), bis Zertifikat und
   Adressauflösung (DNS) greifen.

Ergebnis: Du hast jetzt eine Adresse wie `https://coach.meine-domain.de` und ein leeres
Zielverzeichnis dafür auf deinem Webspace.

## Schritt 2 — SFTP-Zugangsdaten beim Hoster finden

**Was du tust (IONOS-Beispiel):**
1. Im Kundencenter → Menü „Hosting" → „SFTP & SSH" (oder „FTP-Zugänge").
2. Dort findest du den **Host** (z. B. `access-xyz.webspace-host.com`) und deinen
   **Benutzernamen** (oft `uNNNNNNN` oder dein Hauptbenutzer).
3. Falls dein Paket es anbietet, kannst du optional einen eigenen Benutzer nur für das
   Coach-Verzeichnis anlegen (etwas mehr Sicherheit, aber kein Muss).
4. Das zugehörige **Passwort** kennst du entweder schon, oder du vergibst/setzt es dort neu
   zurück.

Notiere dir Host, Benutzer und Passwort kurz — du trägst sie im nächsten Schritt in die App
ein (danach kannst du diese Notiz löschen, die App speichert sie sicher lokal für dich).

## Schritt 3 — Adresse und Zugangsdaten in der App eintragen

**Was du siehst:** In der App unter **Einstellungen**, ganz unten, die Karte **„Coach-Site"**
mit einem Erklärtext und dem Hinweis „Schritt für Schritt: docs/ANLEITUNG_COACH_SITE.md" —
also genau dieser Anleitung.

**Was du tust:**
1. Den Haken **„Coach-Site aktiv"** noch **nicht** setzen — das kommt erst ganz am Ende
   (Schritt 7), wenn alles ausgefüllt ist.
2. Feld **„Adresse der Seite"**: die Subdomain-Adresse aus Schritt 1 eintragen, z. B.
   `https://coach.meine-domain.de`. Wichtig: **muss mit `https://` beginnen** — mit `http://`
   lehnt die App den Eintrag ab (Begründung: sonst würde das Passwort deines Coaches
   unverschlüsselt übertragen).
3. Im Bereich **„Upload-Ziel (SFTP)"** vier Felder ausfüllen:
   - **Host** — aus Schritt 2, z. B. `access-xyz.webspace-host.com`
   - **Benutzer** — aus Schritt 2
   - **Passwort** — aus Schritt 2 (Eingabefeld zeigt nur Punkte, wie jedes Passwortfeld)
   - **Zielverzeichnis** — der Ordner aus Schritt 1, z. B. `/coach` (muss mit `/` beginnen)

Noch nicht auf „Speichern" klicken — erst testen (nächster Schritt).

## Schritt 4 — Verbindung testen

**Was du siehst:** Button **„Verbindung testen"** unterhalb der Formularfelder.

**Was du tust:** Klicken. Der Button zeigt kurz „Testet…", dann eine Ergebniszeile:
- Erfolg (grün): z. B. „✓ Verbunden. Zielverzeichnis /coach erreichbar (leer)."
- Fehler (rot): eine Klartext-Fehlermeldung, z. B. wenn Host/Benutzer/Passwort nicht
  zusammenpassen. Passwörter erscheinen darin **nie** — das ist Absicht.

Der Test prüft direkt die Felder, die gerade im Formular stehen — du musst dafür nicht erst
speichern. Klappt der Test nicht, Host/Benutzer/Passwort/Zielverzeichnis noch einmal mit
Schritt 2 abgleichen.

## Schritt 5 — Serverpfad zur Zugangsdatei ermitteln

Damit die Passwortabfrage auf dem Server funktioniert, braucht Apache (die Server-Software)
den **absoluten Pfad** zur Zugangsdatei auf dem Server — ein technisches Detail, das du dir
normalerweise nicht selbst merken musst: Die App kann es automatisch herausfinden.

**Was du siehst:** Feld „Serverpfad zur Zugangsdatei" mit Platzhalter
`/serverpfad/zum/verzeichnis/.htpasswd` und daneben der Button **„automatisch ermitteln"**.

**Was du tust:** Auf „automatisch ermitteln" klicken. Der Button zeigt kurz „Ermittelt…", dann:
- **Erfolg:** das Feld füllt sich von selbst mit dem passenden Pfad.
- **Fehler „Im Zielverzeichnis liegen bereits Dateien…" (409):** Die Automatik funktioniert nur
  in einem **leeren** Zielverzeichnis (aus Sicherheitsgründen, s. u.). Liegt dort schon etwas —
  z. B. weil du es zuvor schon einmal befüllt hast — trage den Pfad **manuell** ein (weiter
  unten steht, wie).
- **Fehler „Die Datei war nicht erreichbar oder PHP ist nicht aktiv…" (400):** Ebenfalls von
  Hand eintragen.

**Pfad manuell finden**, falls die Automatik nicht klappt:
- **Variante A — Datei-Manager des Hosters:** Im Kundencenter gibt es meist einen
  browserbasierten Datei-Manager für den Webspace. Navigiere dort in dein Zielverzeichnis
  (z. B. `/coach`) — der volle Pfad wird häufig in der Adresszeile/Brotkrumen-Navigation oder
  in den Dateieigenschaften angezeigt.
- **Variante B — grafisches SFTP-Programm** (z. B. FileZilla oder Cyberduck, kostenlos): mit
  denselben Zugangsdaten wie in Schritt 2 verbinden, in den Zielordner wechseln — der
  angezeigte Pfad in der Adressleiste ist der gesuchte absolute Pfad.
- Bei IONOS sieht dieser Pfad häufig so aus (nur als Beispiel für die Form, deine Kennung ist
  natürlich eine andere): `/homepages/12/dNNNNNNNNN/htdocs/coach`.
- In das Feld trägst du den Pfad **plus** `/.htpasswd` ein, z. B.
  `/homepages/12/dNNNNNNNNN/htdocs/coach/.htpasswd`.

## Schritt 6 — Coach-Login vergeben

**Was du siehst:** Bereich **„Coach-Login"** mit dem Hinweis „Damit meldet sich dein Coach auf
der Seite an." und zwei Feldern.

**Was du tust:**
1. **Benutzer** — ein Login-Name für deinen Coach, frei wählbar, z. B. `coach`.
2. **Passwort** — ein Passwort für deinen Coach. Tipp: ein eigenes, nicht wiederverwendetes
   Passwort vergeben, das du separat (z. B. mündlich oder per Messenger) an deinen Coach
   weitergibst. Sobald du speicherst, wird nur der Hash abgelegt (s. „Sicherheit auf einen
   Blick") — das Passwort selbst siehst danach niemand mehr, auch du nicht.

## Schritt 7 — Aktivieren und Coach-Site aktualisieren

**Was du tust:**
1. Jetzt den Haken **„Coach-Site aktiv"** setzen.
2. Auf **„Speichern"** klicken.
   - Fehlt noch etwas, meldet die App das in Klartext, z. B. „Zum Aktivieren fehlen noch:
     site_url, Coach-Passwort" — kein Grund zur Sorge, einfach die genannten Felder ergänzen
     und erneut speichern.
   - Erfolg: „✓ Gespeichert" erscheint neben den Buttons.
3. **Erst nach erfolgreichem Speichern** erscheint darunter ein neuer Button:
   **„Coach-Site jetzt aktualisieren"**. (Vorher steht dort nur der graue Hinweis „Erst
   aktivieren und speichern, dann kann die Seite hochgeladen werden.")
4. Diesen Button klicken. Er baut die Seite aus deinen aktuellen Daten und lädt sie per SFTP
   hoch. Während der Lauf arbeitet, zeigt der Button „⏳ Läuft…" und daneben ein
   „Abbrechen"-Button; ein kleiner Status-Chip zeigt „läuft…". Am Ende steht dort „✓ fertig"
   (oder „✗ fehlgeschlagen" mit einer Fehlermeldung darunter — dann hilft der Abschnitt „Wenn
   etwas nicht klappt").

## Schritt 8 — Abnahme im privaten Browserfenster

Jetzt prüfst du, ob wirklich alles wie gewünscht funktioniert — am besten in einem privaten
Fenster (Safari: „Neues privates Fenster", Chrome: „Neues Inkognito-Fenster"), damit keine
gespeicherten Zugangsdaten den Test verfälschen.

**Was du tust:**
1. Die konfigurierte Adresse aufrufen, z. B. `https://coach.meine-domain.de`.
2. **Es muss sofort eine Login-Abfrage des Browsers erscheinen** (ein natives Popup nach
   Benutzername/Passwort — keine hübsche Anmeldeseite, sondern der Browser selbst fragt). Kommt
   diese Abfrage nicht, ist etwas nicht korrekt eingerichtet (siehe unten).
3. Mit dem Coach-Login aus Schritt 6 einloggen. Danach solltest du die Übersicht, den
   Tages-Digest, deine Stellen und deine Absagen sehen.
4. Im Browser-Tab prüfen, ob das kleine **Favicon** (Icon neben dem Seitentitel im Tab)
   erscheint — das ist dasselbe Symbol wie in der App.
5. Suchmaschinen sind automatisch ausgesperrt, dafür musst du nichts tun. Wer es technisch
   nachprüfen möchte: `curl -sI https://coach.meine-domain.de` zeigt den Header
   `x-robots-tag: noindex` und ohne Login-Angabe den Status `401` — das ist optional und nur
   für technisch Interessierte.

---

## Täglicher Betrieb

Einmal eingerichtet, musst du dich um nichts mehr kümmern: Die Coach-Site aktualisiert sich
**automatisch am Ende jedes Tageslaufs** mit deinem aktuellen Stand. Willst du sie sofort
aktualisieren (z. B. nach einer wichtigen Änderung), klicke jederzeit erneut auf
„Coach-Site jetzt aktualisieren" in den Einstellungen.

## Passwort ändern

Das Coach-Passwort lässt sich jederzeit ändern, ohne sonst etwas anzufassen:
1. Einstellungen → Karte „Coach-Site" → Bereich „Coach-Login".
2. Neues Passwort in das Feld „Passwort" eintragen (der Benutzername kann unverändert bleiben).
3. „Speichern" klicken — danach gilt sofort das neue Passwort, das alte funktioniert nicht mehr.
4. Optional danach „Coach-Site jetzt aktualisieren" klicken, damit die neue Zugangsdatei sofort
   auf dem Server liegt (sonst passiert das spätestens beim nächsten Tageslauf).

## Vorübergehend abschalten

Haken **„Coach-Site aktiv"** entfernen und „Speichern" klicken. Damit werden **künftige**
Aktualisierungen (Button wie Tageslauf) übersprungen — die App meldet das jeweils ehrlich mit
„Coach-Site ist in den Einstellungen abgeschaltet — übersprungen." Wichtig zu wissen: Der
zuletzt hochgeladene Stand **bleibt dabei auf dem Server liegen** und ist weiterhin (passwort-
geschützt) erreichbar, bis du entweder wieder aktivierst oder den Not-Aus unten benutzt.

## Not-Aus: Seite komplett vom Server entfernen

Für den Fall, dass du die Coach-Site sofort und vollständig vom Server entfernen willst (nicht
nur pausieren), gibt es einen einzigen Terminal-Befehl. Das ist der einzige Schritt in dieser
ganzen Anleitung, der ein Terminal braucht:

1. Terminal-App öffnen.
2. In den Projektordner wechseln (Pfad wie auf deinem Rechner eingerichtet), z. B.:
   ```
   cd Pfad/zu/deinem/Bewerbung_Mgmt_System
   ```
3. Ausführen:
   ```
   scripts/coach_deploy.sh --wipe
   ```
4. Das leert das Zielverzeichnis auf dem Server vollständig (Inhalte **und** die
   Zugangsschutz-Dateien) — die Seite ist danach nicht mehr aufrufbar. Das funktioniert auch,
   wenn „Coach-Site aktiv" bereits ausgeschaltet ist. Nur wenn noch **nie** SFTP-Zugangsdaten
   eingetragen wurden, kann der Befehl naturgemäß nichts löschen und meldet das.

---

## Wenn etwas nicht klappt

**„Internal Server Error" direkt nach der Passwort-Eingabe**
- *Ursache:* Der Server kann die Zugangsdatei nicht lesen — meist, weil der eingetragene
  Serverpfad nicht exakt auf die tatsächliche Datei zeigt, oder weil deren Dateirechte auf dem
  Server nicht passen (die App setzt beim Hochladen automatisch die richtigen Rechte, manche
  Hoster überschreiben das aber in Ausnahmefällen).
- *Was zu tun ist:* In der Karte „Coach-Site" den Serverpfad prüfen bzw. neu ermitteln (Schritt
  5), dann „Coach-Site jetzt aktualisieren" erneut klicken. Bleibt der Fehler bestehen, beim
  Hoster nachfragen, ob sich die Dateirechte der `.htpasswd` im Zielverzeichnis ändern lassen.

**Login-Popup erscheint bereits bei `http://` (ohne „s")**
- *Ursache:* Die Weiterleitung von unverschlüsseltem `http://` auf das sichere `https://`
  müsste greifen, **bevor** überhaupt eine Passwortabfrage erscheint. Erscheint sie trotzdem
  schon bei `http://`, wurde entweder eine ältere Schutz-Datei nicht überschrieben, oder dein
  Hoster unterstützt die dafür nötige Serverfunktion nicht.
- *Was zu tun ist:* Einmal „Coach-Site jetzt aktualisieren" klicken, damit sicher die aktuelle
  Schutz-Konfiguration hochgeladen wird. Tritt das Problem danach weiter auf, beim Hoster
  nachfragen, ob „SSL erzwingen" oder eine vergleichbare Einstellung pauschal für die Subdomain
  aktivierbar ist.

**„Upload wurde übersprungen"**
- *Ursache:* Entweder ist „Coach-Site aktiv" ausgeschaltet, oder es fehlt noch mindestens ein
  Pflichtfeld (Adresse, SFTP-Zugang, Serverpfad oder Coach-Login).
- *Was zu tun ist:* Die genaue Meldung zeigt, was fehlt. In den Einstellungen den Haken bzw.
  das genannte Feld ergänzen und erneut speichern.

**„lftp fehlt"**
- *Ursache:* Das Programm, das den Datei-Upload erledigt, ist auf diesem Rechner nicht
  installiert. Diese Meldung kann schon bei „Verbindung testen" oder „automatisch ermitteln"
  erscheinen, nicht erst beim Hochladen.
- *Was zu tun ist:* Terminal öffnen, `brew install lftp` ausführen (s. „Voraussetzungen"),
  danach den Schritt einfach erneut anklicken.

**Die Seite zeigt eine falsche/leere Seite oder 404, obwohl alles gespeichert ist**
- *Ursache:* Die Subdomain aus Schritt 1 zeigt auf ein **anderes** Verzeichnis auf dem Server
  als das, was du als „Zielverzeichnis" in der Coach-Karte eingetragen hast — die beiden
  müssen exakt übereinstimmen.
- *Was zu tun ist:* Beim Hoster nachsehen, welches Verzeichnis der Subdomain zugewiesen ist
  (bei IONOS: „Domains & SSL" → Subdomain → Einstellungen zeigt das Verzeichnis), und in der
  Coach-Karte unter „Zielverzeichnis" exakt denselben Pfad eintragen.
