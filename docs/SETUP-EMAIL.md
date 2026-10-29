# E-Mail-Konto einrichten (Kunden-Anleitung)

Das System **liest** Bewerbungs-Mails und legt Antwort-**Entwürfe** in deinem Postfach ab.
Es versendet nie selbst — es gibt im gesamten Programm keinen Sende-Codepfad (per Test
abgesichert). Zwei Wege stehen offen; **Weg A ist der empfohlene Standard.**

| | Weg A: IMAP (empfohlen) | Weg B: Gmail-API (Power-User) |
|---|---|---|
| Geeignet für | Gmail, GMX, Web.de, mailbox.org, Posteo, iCloud-Mail | nur Gmail |
| Einrichtung | ~5 Minuten, nur App-Passwort | ~30–45 Min, Google-Cloud-Console |
| Suche | Datumsfenster + Nachfilterung, nur Posteingang | volle Gmail-Suchsyntax, alle Labels |
| Google-Formalitäten | keine | eigenes Google-Cloud-Projekt |
| Nicht möglich | Outlook.com/Microsoft (kein IMAP-Basic-Auth) | — |

---

## Weg A — IMAP mit App-Passwort (empfohlen)

1. **App-Passwort beim Anbieter erzeugen** (das normale Kontopasswort funktioniert NICHT und
   gehört auch nicht in fremde Software):
   - **Gmail:** 2-Faktor-Authentifizierung im Google-Konto aktivieren → myaccount.google.com
     → „Sicherheit" → „App-Passwörter" → neues Passwort (16 Zeichen) erzeugen.
     Hinweis: Bei aktiviertem „Advanced Protection Program" bietet Google keine App-Passwörter
     an — dann Weg B nutzen.
   - **GMX / Web.de:** Einstellungen → Sicherheit → „Anwendungsspezifische Passwörter"
     (dort auch „IMAP/POP3-Zugriff erlauben" aktivieren).
   - **mailbox.org / Posteo:** Einstellungen → Sicherheit → App-Passwort.
   - **iCloud-Mail:** appleid.apple.com → Anmeldung & Sicherheit → „App-spezifische Passwörter".
2. **In der App eintragen:** Einstellungen → Karte „E-Mail-Konto" → „IMAP" wählen:

   | Anbieter | Host | Port | Sicherheit | Entwürfe-Ordner |
   |---|---|---|---|---|
   | Gmail | imap.gmail.com | 993 | SSL | `[Gmail]/Entwürfe` (bei englischem Konto: `[Gmail]/Drafts`) |
   | GMX | imap.gmx.net | 993 | SSL | `Entwürfe` |
   | Web.de | imap.web.de | 993 | SSL | `Entwürfe` |
   | mailbox.org | imap.mailbox.org | 993 | SSL | `Drafts` |
   | Posteo | posteo.de | 993 | SSL | `Drafts` |
   | iCloud | imap.mail.me.com | 993 | SSL | `Drafts` |

   Benutzername = vollständige E-Mail-Adresse, Passwort = das App-Passwort aus Schritt 1.
3. **„Verbindung testen"** klicken — geprüft werden Login und Entwürfe-Ordner. Bei
   „Ordner nicht gefunden" den exakten Ordnernamen aus deinem Mail-Programm übernehmen
   (er ist bei manchen Anbietern sprachabhängig). Dann **Speichern**.

Die Zugangsdaten liegen danach ausschließlich lokal in
`~/.bewerbung_mgmt_secrets/mail_settings.json` (Dateirechte 600) — nie in der Datenbank,
nie in einer Cloud des Anbieters.

**Bekannte Grenzen von Weg A:** Durchsucht wird nur der Posteingang (archivierte/verschobene
Mails sieht das System nicht — Bewerbungs-Mails bis zur Verarbeitung im Posteingang lassen);
die Trefferliste zeigt keine Vorschau-Schnipsel.

---

## Weg B — Gmail-API mit eigenem Google-Cloud-Projekt

Für Gmail-Nutzer, die die volle Suchsyntax und Label-übergreifende Suche wollen. Du legst dabei
ein EIGENES, privates Google-Projekt an — der Software-Anbieter sitzt nicht dazwischen und
sieht nichts. Die spätere Warnung „Google hat diese App nicht überprüft" ist bei einem
selbst angelegten Privat-Projekt normal und korrekt (du bist selbst der „Entwickler").

1. **Projekt anlegen:** console.cloud.google.com → neues Projekt (Name egal, z. B. „Mein-BMS").
2. **Gmail-API aktivieren:** „APIs & Dienste" → „Bibliothek" → „Gmail API" → Aktivieren.
3. **OAuth-Zustimmungsbildschirm:** Typ „Extern", App-Name + eigene E-Mail eintragen.
   Scopes hinzufügen: `gmail.readonly` und `gmail.compose` (mehr braucht und will die
   Software nicht — sie kann konstruktionsbedingt nicht senden).
   **Wichtig: Veröffentlichungsstatus auf „In Produktion" stellen** — im Status „Testing"
   verfallen die Zugriffstoken alle 7 Tage und die Mail-Funktionen sterben wöchentlich.
4. **Client-ID erzeugen:** „Anmeldedaten" → „OAuth-Client-ID" → Typ **„Desktop-App"** →
   JSON herunterladen.
5. **Datei ablegen** als `~/.bewerbung_mgmt_secrets/gmail_credentials.json`
   (Verzeichnis mit `chmod 700`, Datei mit `chmod 600`).
6. **Einmalig anmelden:**
   ```sh
   ~/.bewerbung_mgmt_venv/bin/python -m pipeline.gmail_client auth
   ```
   (aus dem `backend/`-Ordner heraus; öffnet den Browser). Bei der Warnung „App nicht
   überprüft": „Erweitert" → „Fortfahren" — s. o., bei deinem eigenen Projekt ist das der
   vorgesehene Weg. Danach in der App: Einstellungen → „E-Mail-Konto" → „Gmail (API)".

**Google-Workspace-Konten** (Firmen-Postfächer): Der Workspace-Admin kann den Client der
eigenen Organisation als „intern" markieren (keine Warnung, keine Verifizierung) oder für
Weg A App-Passwörter erlauben. Details klärt der Admin.
