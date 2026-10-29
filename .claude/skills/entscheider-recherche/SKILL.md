---
name: entscheider-recherche
description: Recherchiert für eine Stelle oder Firma aus dem Bewerbungs-Management-System die tatsächlichen Fachentscheider (VP/Head/C-Level für Professional Services, Customer Success oder Delivery — statt HR-Sammeladresse) und optional die Vorbesetzung der Zielrolle (wer hatte sie vorher, welches Profil), ausschließlich über öffentliche Quellen. Legt Treffer dedupliziert als Kontakte am Job an und empfiehlt die Ansprache. Nutze diesen Skill bei "Entscheider für Job <id>", "wer ist der Hiring Manager bei <Firma>", "Entscheider-Recherche für <Firma>", "Vorbesetzungs-Recherche für Job <id>", "wen soll ich ansprechen bei <Firma>".
---

# Entscheider-Recherche (Fachentscheider statt HR-Flaschenhals)

Beantwortet: **Wer entscheidet wirklich über diese Rolle — und wie erreiche ich ihn/sie?** Baustein für
`anschreiben-erstellen` (Empfänger), `initiativ-bewerbung` (Schritt 3) und `interview-vorbereiten`
(Interviewer-Kontext).

## Ablauf

### 1. Kontext laden
```sh
curl -s http://localhost:8000/api/jobs/<id>          # bzw. Firma aus dem Auslöser
curl -s "http://localhost:8000/api/network-check?company=<Firma>"
```
Zielrolle/Funktion bestimmen (PS / CS / Delivery / Implementation) und vorhandene Kontakte + warme Pfade
kennen, bevor recherchiert wird — ein warmer Kontakt schlägt jede Kalt-Recherche.

### 2. Fachentscheider recherchieren (WebSearch — NUR öffentliche Quellen)
Suchmuster (kombinieren, DE + EN):
- `<Firma> "VP Professional Services" OR "Head of Professional Services" OR "Director Services" site:linkedin.com`
- Leadership-/Team-Seite der Firma, Pressemitteilungen (Neubesetzungen!), Konferenz-Speaker, Podcasts, Handelsregister-Signale.
- Gesucht: **Fachverantwortliche der Zielfunktion** (nicht HR) + deren Chef (Reporting-Linie), Name, exakte
  Rolle, LinkedIn-URL, 1–2 Kontextpunkte (Posts, Vorträge, Schwerpunkte) für die persönliche Ansprache.

### 3. Optional: Vorbesetzung (auf Wunsch oder bei Initiativ/Interview-Prep)
- Wer hatte die Zielrolle vorher inne? (`"<Rollentitel>" <Firma> site:linkedin.com`, News, Archiv.)
- Profil der Vorbesetzung = implizites Anforderungsprofil: Seniorität, Herkunft, Verweildauer, Wohin-gewechselt
  (Warnsignal bei kurzer Verweildauer?). Ehrlich kennzeichnen, wenn nicht auffindbar.

### 4. Grenzen (verbindlich)
- **Kein Login-Scraping, keine Umgehung von Paywalls/LinkedIn-Limits** — nur, was Suche/öffentliche Seiten hergeben.
- Jede Person mit Quelle belegen; Unsicherheit markieren („vermutlich", „Stand: <Datum>").
- Keine privaten Daten (nur berufliche Rolle/Profil-URL); keine E-Mail-Adressen raten.

### 5. Als Kontakte registrieren (dedupliziert)
Python-Einzeiler (Muster `gespraech-debrief` Schritt 4): `Contact(company_id, job_id, name, role,
linkedin_url, notes="recherchiert <Datum>, Quelle: <URL>")` — Rolle z. B. „Entscheider (recherchiert)" oder
„Vorbesetzung (recherchiert)". Case-insensitives Name-Dedupe gegen bestehende Kontakte.

### 6. Bericht an den Nutzer
Entscheider (mit Quelle + Kontextpunkt), Reporting-Linie falls bekannt, Vorbesetzungs-Erkenntnis,
**empfohlene Ansprache-Route** (warmer Pfad aus network-check > direkt an Entscheider) und der nächste
Schritt (meist: „Anschreiben für Job <id>" mit diesem Empfänger).

## Abgrenzung
- Recherche + Kontaktpflege — **keine Ansprache, kein Anschreiben** (das ist `anschreiben-erstellen`), kein Versand.
- Firmen-/Markt-Analyse = `firma-pruefen`; kompletter Initiativ-Ablauf = `initiativ-bewerbung` (nutzt diesen Baustein).
