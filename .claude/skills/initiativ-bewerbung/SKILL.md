---
name: initiativ-bewerbung
description: Startet den Initiativbewerbungs-Workflow für eine Zielfirma OHNE ausgeschriebene Stelle (Hidden Job Market) — prüft warme Pfade im Netzwerk (Netzwerk-Kontakte, Outreach, Headhunter, bestehende Kontakte), legt eine Initiativ-Stelle im Tracker an (portal=Initiativ, Status Prüfen), recherchiert den Fachentscheider und empfiehlt die Ansprache-Route; danach übernehmen firma-pruefen und anschreiben-erstellen. Ohne Firmennamen: liefert eine priorisierte Kandidaten-Shortlist aus Zielfirmen/Radar mit Netzwerk-Abdeckung. Nutze diesen Skill bei "Initiativbewerbung für <Firma>", "initiativ bewerben bei <Firma>", "verfolge <Firma> initiativ", "Hidden Job Market", "welche Zielfirmen soll ich initiativ angehen", "Initiativ-Kandidaten".
---

# Initiativbewerbung (Hidden Job Market)

Verwandelt eine Zielfirma ohne Ausschreibung in einen trackbaren Bewerbungsvorgang — mit Netzwerk-Check
zuerst (warme Pfade schlagen kalte Bewerbungen: Outreach-Response 70,5 % vs. 44 %, siehe Empirie in
`config/profil.md`). Datenbasis existiert bereits: 69 Zielfirmen (`/api/target-companies`, mit Tier/
Wachstumssignal/Key-Contact), 82 Radar-Firmen (`/api/companies?radar=true`), Netzwerk & Outreach.

## Ablauf

### 0. Ohne Firmennamen: Shortlist statt Einzelfirma
Wenn der Auslöser keine Firma nennt („welche Zielfirmen initiativ angehen?"):
alle Zielfirmen laden, je Firma `GET /api/network-check?company=<name>` — priorisieren nach
**warm (Netzwerk-Pfad vorhanden) > Tier > Wachstumssignal**; Radar-Firmen mit „Rebuild"-Signal ergänzen.
Top 5–8 mit Begründung präsentieren, der Nutzer wählt. Dann ab Schritt 1.

### 1. Netzwerk-Check (immer zuerst)
```sh
curl -s "http://localhost:8000/api/network-check?company=<Firma>"
```
Liefert `warm` + Details: `network_contacts` (wer arbeitet dort/kennt die Firma), `outreach`
(bisherige Ansprachen + Status!), `headhunters` (Fokus-Match), `contacts` (aus früheren Bewerbungen),
`target_entry` (Tier, Szenario, Wachstumssignal, Key-Contact). **Bereits laufende Outreach-Ansprache?
Dann dort andocken statt parallel kalt anzuschreiben.**

### 2. Initiativ-Stelle anlegen
```sh
curl -s -X POST http://localhost:8000/api/initiativ -H 'Content-Type: application/json' \
  -d '{"company":"<Firma>","title":"<Wunschrolle>","notes":"<optional>"}'
```
- **Wunschrolle** aus dem Zielprofil (`config/profil.md`): PS-/Service-Delivery-Leitung auf
  Director/VP/Head-Ebene — konkret auf die Firma zugeschnitten (z. B. „Head of Professional Services DACH").
- Legt Firma an, falls unbekannt (mit Branche/HQ aus der Zielfirmen-Liste), Job mit `portal='Initiativ'`,
  `status='Prüfen'`, Wachstumssignal in `source_note`. `{"existing": true}` → vorhandenen Job weiterverwenden.
- Der Job läuft ab jetzt im normalen Board (Pipeline/Stellen/Follow-ups).

### 3. Entscheider recherchieren (WebSearch — öffentliche Quellen, kein Scraping)
Wer verantwortet Professional Services / Customer Success / Delivery? Gesucht: **Fachentscheider**
(VP/C-Level/Head), nicht HR — Name, Rolle, LinkedIn-URL, ggf. 1–2 Kontextpunkte (Posts, Vorträge).
Als Kontakt anlegen (Dedupe-Muster wie `gespraech-debrief` Schritt 4, role z. B. „Entscheider (recherchiert)").
Ehrlich bleiben: nur öffentlich Belegbares, Unsicherheiten kennzeichnen.

### 4. Ansprache-Route empfehlen (Priorität)
1. **Warm:** Intro über Netzwerk-Kontakt/Outreach-Beziehung erbitten (konkreten Namen + Formulierungsvorschlag liefern).
2. **Headhunter:** wenn Fokus passt und Beziehung existiert.
3. **Kalt direkt an den Entscheider** (nie an HR-Sammeladressen): dann gilt die Empirie-Regel —
   Scope statt Titel, firmenspezifischer Hook aufs Wachstumssignal.

### 5. Übergabe an die bestehenden Skills
- Kein `fit_analysis_path` an der Firma? → **erst** „Firma prüfen für Job <id>" (`firma-pruefen`).
- Dann „Anschreiben für Job <id>" (`anschreiben-erstellen`) — Hook = Wachstumssignal/Szenario statt
  Ausschreibung; Empfänger = recherchierter Entscheider bzw. Intro-Kontakt.
- Nach Versand: Status „Beworben" + `applied_date` (UI), `follow_up_date` +7 Tage setzen.

### 6. Bericht an den Nutzer
Route (warm/Headhunter/kalt) mit konkretem nächsten Schritt, Entscheider (mit Quelle), Job-Link
(http://localhost:8000/jobs/<id>) und was noch fehlt (Firma-Check? Anschreiben?).

## Abgrenzung
- **Sendet nichts und bewirbt nicht** — bereitet vor und trackt; anschreiben/bewerben tut der Nutzer.
- Firmen-Analyse = `firma-pruefen` · Anschreiben = `anschreiben-erstellen` · laufende Netzwerk-Pflege = Outreach-Tracker.
- UI-Einstieg: „🚀 Initiativ"-Chip auf /netzwerk (Zielfirmen) und /radar kopiert den Auslöser hierher.
