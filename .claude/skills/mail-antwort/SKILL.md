---
name: mail-antwort
description: Formuliert für eine eingegangene E-Mail aus dem Bewerbungs-Management-System eine faktentreue Antwort und legt sie als Gmail-ENTWURF im richtigen Thread an — NIE senden. Termin-/Zusage-Entscheidungen werden als [BITTE PRÜFEN: …]-Platzhalter markiert, keine Fakten erfunden. Nutze diesen Skill bei "Antwort-Entwurf für Mail <email_id>", "beantworte Mail <email_id>".
---

# Mail-Antwort (Gmail-Entwurf)

Beantwortet eine konkrete eingegangene Mail faktentreu aus dem BMS-Kontext (Job, Status, Interviews,
Verlauf) und legt die Antwort als **Gmail-ENTWURF im Original-Thread** an. **Eiserne Linie: es wird NIE
gesendet** — `gmail_client` hat konstruktiv kein Sende-Verb (Code-Garantie seit Phase 8.3), der Nutzer
prüft, personalisiert bei Bedarf und sendet selbst.

## Ablauf

### 1. Mail + Kontext laden
Email-ID aus dem Auslöser (z. B. „Antwort-Entwurf für Mail <email_id>"):
```sh
curl -s http://localhost:8000/api/emails               # Liste, die Row mit passender id finden
curl -s http://localhost:8000/api/emails/<email_id>/body   # Volltext (live aus Gmail)
```
Liefert `from_addr`, `subject`, `gmail_message_id`, `job_id`, `body`. Ist `body: null`, steht ein
`hinweis` dabei (z. B. keine Gmail-Zuordnung, Token abgelaufen) — dann **abbrechen und den Hinweis
melden**, keinen Entwurf ohne Volltext schreiben.

Ist `job_id` gesetzt:
```sh
curl -s http://localhost:8000/api/jobs/<job_id>
```
Liefert Status, Interviews, `next_step`/`follow_up_date`, bisherigen E-Mail-Verlauf (`emails[]`) —
das ist der Faktenstand, aus dem die Antwort schöpft. Zusätzlich `config/profil.md` (Ton, Empirie-
Regeln — Scope-Zahlen statt Titel, wo eine Zahl belegbar ist).

### 2. Antwort formulieren
- **Sprache = Sprache der eingehenden Mail** (Deutsch bleibt Deutsch, Englisch bleibt Englisch).
- Kurz, konkret, beantwortet GENAU die gestellten Fragen — keine Grundsatzrede.
- **Nur Fakten aus dem BMS-Kontext** (Job-Status, Verlauf, bereits gesagtes). Keine Zusagen, Termine
  oder Entscheidungen erfinden.
- Wo eine echte Entscheidung des Nutzers nötig ist (Terminvorschlag annehmen, Gehaltsvorstellung nennen,
  Verfügbarkeit zusagen): **`[BITTE PRÜFEN: <worum es geht>]`** als sichtbaren Platzhalter einsetzen
  — nie raten, nie eine Zahl/ein Datum erfinden, um die Lücke zu füllen.
- Grußformel: Name des Nutzers, keine Signatur-Fantasie (keine erfundene Telefonnummer o. Ä.).

### 3. Gmail-Entwurf anlegen (NIE senden)
Mailtext in eine Datei schreiben, dann:
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.gmail_client draft \
  --to "<from_addr der Mail>" --subject "Re: <subject>" --body-file ../data/tmp/mail-antwort.txt \
  --in-reply-to <gmail_message_id>
```
`--in-reply-to` ist hier **immer** die `gmail_message_id` der beantworteten Mail — setzt
`In-Reply-To`/`References` und hängt den Entwurf in den richtigen Thread (Mechanik in der
8.3-Rauchprobe bewiesen: Postausgang bleibt unverändert). Der Client kennt kein Senden — das Verb
existiert im Code nicht, das ist keine Prompt-Disziplin, sondern eine Code-Eigenschaft.

### 4. E-Mail-Row fortschreiben
```sh
curl -s -X PATCH http://localhost:8000/api/emails/<email_id> -H 'Content-Type: application/json' \
  -d '{"reply_draft_at": "<jetzt, ISO>"}'
```
**NICHT** `needs_reply` auf `false` setzen — der Entwurf ist noch nicht verschickt, die Mail ist erst
beantwortet, wenn der Nutzer wirklich sendet (der nächste `email-check` erkennt die ausgehende Mail dann
ganz regulär und pflegt `needs_reply` wie gewohnt fort). `reply_draft_at` ist die ehrliche Aussage:
„ein Entwurf liegt bereit", nicht „erledigt".

### 5. Bericht an den Nutzer
2–3 Sätze: an wen der Entwurf geht, die Kernaussage in einem Halbsatz, die Liste der
`[BITTE PRÜFEN: …]`-Platzhalter (falls welche gesetzt wurden). Schlusszeile: „Entwurf liegt in
Gmail — prüfen & senden."

## Abgrenzung
- **Sendet nie** — wie `nachfass-mail`, dessen Gmail-Entwurf-Mechanik dieser Skill wiederverwendet.
- Ist die Mail eine Funkstille-Situation (keine eingehende Mail, sondern der Nutzer will von sich aus
  nachfassen) oder eine Absage, bei der er nach dem Grund fragen will: das ist `nachfass-mail`, nicht
  dieser Skill. `mail-antwort` beantwortet eine KONKRETE eingegangene Mail.
- Kein Massen-Beantworten — ein Entwurf pro Aufruf, der Nutzer behält die Kontrolle über jeden Versand.
