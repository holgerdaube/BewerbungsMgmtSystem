---
name: nachfass-mail
description: Erzeugt für eine Stelle aus dem Bewerbungs-Management-System einen Mail-ENTWURF in Gmail (nie senden) — Modus A "Nachfassen" bei Funkstille (höfliche Statusanfrage mit Wert-Anker, wenn auf eine Bewerbung keine Antwort kam) oder Modus B "Absage-Nachfrage" (dankende Bitte um konkretes Feedback nach einer Absage, füllt rejection_reason mit echten Signalen). Wählt den Modus automatisch nach Job-Status. Nutze diesen Skill bei "Nachfass-Entwurf für Job <id>", "fass bei Job <id> nach", "Nach Absagegrund fragen für Job <id>", "Absage-Nachfrage für Job <id>", "Feedback erfragen für Job <id>".
---

# Nachfass-Mail (Funkstille & Absage-Nachfrage)

Zwei Modi, ein Prinzip: **kurz, höflich, konkret — und immer nur als Gmail-ENTWURF.** Gesendet wird nie
automatisch; der Nutzer prüft, personalisiert und sendet selbst.

## Ablauf

### 1. Stelle laden & Modus bestimmen
```sh
curl -s http://localhost:8000/api/jobs/<id>
```
- Status **„Absage"** → **Modus B (Absage-Nachfrage)**.
- Status **„Beirat abgelehnt"** → **kein Modus, kein Entwurf.** Das ist keine externe Absage,
  sondern die eigene Entscheidung des Nutzers nach dem Beirats-Check — es gibt niemanden bei der Firma,
  bei dem nachzufassen wäre.
- Sonst (Beworben/Interview ohne Antwort) → **Modus A (Nachfassen)**.
- Kontext einsammeln: `application` (applied_date, Kanal), `emails` (letzter Kontakt, Sprache!),
  `contacts` (Empfänger-Adresse?), `job.next_step`/`follow_up_date`.

### 2. Entwurf schreiben (≤120 Wörter, Sprache = bisherige Korrespondenz, sonst Anzeigen-Sprache)
**Modus A — Nachfassen (Funkstille):**
- Bezug: Rolle + Bewerbungsdatum („am 01.07. beworben").
- Interesse bekräftigen mit EINEM konkreten Wert-Anker (aus CV/Company-Fit — z. B. der Scope-Beleg).
- Freundliche Frage nach dem Stand + Gesprächsangebot. Kein Vorwurf, kein Druck.

**Modus B — Absage-Nachfrage:**
- Dank für die Rückmeldung, Absage sportlich nehmen (keine Diskussion der Entscheidung).
- **Eine** konkrete Bitte: kurzes Feedback zum ausschlaggebenden Grund (Screening-Kriterium? Seniorität?
  interner Kandidat?) — als Lernchance gerahmt.
- Tür offen halten (künftige Rollen, Netzwerk).

### 3. Gmail-Entwurf anlegen (NIE senden)
Mailtext in eine Datei schreiben, dann:
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.gmail_client draft \
  --to "recruiter@firma.de" --subject "…" --body-file ../data/tmp/nachfass.txt \
  [--in-reply-to <gmail_message_id>]
```
- **Empfänger:** echte Adresse NUR wenn in den Kontakten/Mails bekannt (z. B. Recruiter der Absage-Mail).
  Achtung: Gmail verlangt ≥1 Empfänger auch bei Entwürfen → ohne bekannte Adresse **die eigene Adresse
  des verbundenen Mail-Kontos als Platzhalter** (selbst-adressiert; bei Gmail die authentifizierte
  Adresse) eintragen und im Bericht auf das Ersetzen hinweisen.
- Bei Antwort auf eine vorhandene Mail: `--in-reply-to` mit der `gmail_message_id` der Absage-/
  Bestätigungsmail — setzt `In-Reply-To`/`References` und hängt den Entwurf in den Thread.
- Der Client kennt kein Senden. Es bleibt zwangsläufig bei einem Entwurf.

### 4. Job fortschreiben (PATCH /api/jobs/<id>)
- **Modus A:** `next_step` = „Nachfass-Entwurf in Gmail prüfen & senden", `follow_up_date` = heute + 3 Tage.
- **Modus B:** `next_step` = „Feedback-Nachfrage prüfen & senden". Kommt später eine Antwort mit echtem Grund:
  `application.rejection_reason` aktualisieren (Python-Einzeiler, Muster `absagen-analyse`) — der `email-check`
  erfasst die Antwort ohnehin.

### 5. Bericht an den Nutzer
Modus, Entwurf-Kurzfassung (1 Satz), Empfänger-Status (echt vs. Platzhalter), Hinweis auf den
Entwürfe-Ordner. Nichts wurde gesendet.

## Abgrenzung
- **Sendet nie.** Ein Entwurf pro Aufruf — kein Massen-Nachfassen (bei mehreren Jobs: einzeln aufrufen,
  der Nutzer behält die Kontrolle).
- Danke-Mail NACH einem Gespräch = `gespraech-debrief` (Schritt 6), nicht dieser Skill.
- UI-Einstiege: „✉️ Nachfass"-Chip in /followups, „❓ Nach Grund fragen" am Job-Detail bei Status Absage.
