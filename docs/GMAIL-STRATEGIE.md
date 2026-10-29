# Gmail-/E-Mail-Strategie (Phase 72A, Stand 31.07.2026)

Entscheidungsdokument zu der Frage: **Wie bekommen Anwender (lokale Installation) Zugang zu
ihrem Postfach**, ohne dass der Herausgeber in Googles Verifizierungs-/Audit-Maschinerie muss?

## Faktenlage (recherchiert 31.07.2026, Quellen unten)

1. **Gmail per IMAP + App-Passwort funktioniert weiterhin** (Stand 2026, keine Abkündigung):
   Voraussetzung ist 2-Faktor-Authentifizierung im Google-Konto; IMAP ist seit Januar 2025 bei
   allen Konten standardmäßig aktiv. Kein Google-Cloud-Projekt, keine OAuth-Verifizierung nötig.
   (Nicht verfügbar bei „Advanced Protection"-Konten; Workspace-Admins können es deaktivieren.)
2. **Googles Security Assessment (CASA) gilt nur für Apps, die restricted-scope-Daten „from or
   through a third-party server" verarbeiten.** Rein lokale Verarbeitung ist davon ausgenommen.
   ABER: Das BMS übermittelt Mail-Inhalte zur Klassifikation an die Claude-API (Konto des
   Nutzers) — bei einem GEMEINSAMEN, vom Herausgeber betriebenen OAuth-Client müsste genau das im
   Verifizierungsprozess deklariert werden; das Assessment-Risiko wäre real, nicht theoretisch.
3. **Kosten, falls Assessment doch fällig:** CASA Tier 2 ca. **$540–1.800/Jahr**, Tier 3 ca.
   $4.500 — plus jährliche Revalidierung, plus Brand-Verification-Prozess (Datenschutzerklärung,
   Domain-Nachweis, Demo-Video, mehrwöchige Review-Schleifen).
4. **Verifizierungs-Ausnahmen** existieren für: Personal Use (der Weg bei Eigennutzung),
   Internal Use (App nur innerhalb der eigenen Workspace-Organisation), Dev/Testing.
5. **Unverifizierter GEMEINSAMER Client** ist keine Option für Anwender:
   Warnbildschirm, User-Cap, verkürzte Token-Lebensdauer.
6. **Eigenes Google-Cloud-Projekt je Anwender** (Personal-Use-Ausnahme) funktioniert dauerhaft und
   kostenlos — der Betrieb des Autors ist der Beweis. Preis: ~15–20 Schritte in der
   Google-Cloud-Console; Zustimmungsbildschirm muss auf „In Produktion" stehen (sonst sterben
   Refresh-Tokens nach 7 Tagen, dann läuft die Anmeldung ab).

## Entscheidung: Stufenmodell, IMAP-first

**Stufe 1 — Standard für alle Anwender: IMAP (auch für Gmail).**
Der Phase-71F-Provider deckt Gmail, GMX, Web.de, mailbox.org, Posteo, iCloud-Mail ab. Setup für
die Anwender: 2FA aktivieren, App-Passwort erzeugen, drei Felder ausfüllen — Minuten statt
Console-Odyssee, null Google-Bürokratie für den Herausgeber. Bekannte, dokumentierte Abstriche
gegenüber der Gmail-API: Suche als Python-Nachfilter (Recall gleichwertig bei den engen
Datumsfenstern der Skills), nur INBOX (archivierte Mails unsichtbar), kein Snippet in
Suchergebnissen, Gmail-Entwürfe-Ordner heißt lokalisiert „[Gmail]/Entwürfe".

**Stufe 2 — Power-User-Option: Gmail-API mit eigenem Google-Cloud-Projekt.**
Für Anwender, die die volle Gmail-Query-Syntax und Label-übergreifende Suche wollen. Wird durch
eine Schritt-für-Schritt-Anleitung getragen (docs/SETUP-EMAIL.md, Weg B) — inklusive der
Erklärung, dass die „nicht verifizierte App"-Warnung beim EIGENEN Projekt normal und richtig
ist. Kein Aufwand für den Herausgeber außer Doku-Pflege.

**Stufe 3 — Organisationen mit Google Workspace (z. B. Coaching, Outplacement):**
Die Organisation markiert den OAuth-Client ihrer Domain als „intern" → Internal-Use-Ausnahme,
keine Verifizierung, kein Warnbildschirm; alternativ erlaubt der Admin App-Passwörter für
Stufe 1. Wird erst ausgearbeitet, wenn ein solcher Einsatz konkret wird.

**Bewusst NICHT jetzt: ein gemeinsamer, verifizierter OAuth-Client des Herausgebers.**
Gründe: laufende Kosten (Assessment-Risiko wegen Claude-API-Übermittlung, s. Fakt 2/3),
jährliche Revalidierung, Brand-Verification-Pflege, und er widerspricht dem zentralen
Grundsatz („der Herausgeber sitzt NICHT zwischen dir und deinem Postfach").

**Neubewertung, wenn** (a) viele Anwender aktiv Gmail-API statt IMAP verlangen,
(b) Google App-Passwörter abkündigt, oder (c) eine große Organisation einen verifizierten
Client fordert. Dann zuerst prüfen, ob die Architektur so umgebaut werden kann,
dass Mail-Volltexte die lokale Maschine nicht mehr verlassen (lokales Vorfiltern/Anonymisieren
vor dem Claude-Aufruf) — das würde die CASA-Frage entschärfen.

## Quellen

- Google: Restricted scope verification (developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification) — Assessment-Kriterium „from or through a third-party server", Ausnahmen, Folgen unverifizierter Apps.
- DeepStrike: Google CASA Security Assessment (deepstrike.io/blog/google-casa-security-assessment-2025) — Tier-2-Preise $540–1.800, Tier 3 $4.500, jährliche Revalidierung.
- Mailjerry „Create Gmail App Password 2026" (mailjerry.com/create-gmail-app-password), SMTPedia „Gmail Settings 2026" (smtpedia.com/gmail-email-settings-pop3-imap-smtp) — App-Passwörter aktiv, 2FA-Pflicht, IMAP default-on seit 01/2025.
