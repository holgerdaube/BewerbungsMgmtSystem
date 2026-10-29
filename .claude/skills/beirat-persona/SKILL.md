---
name: beirat-persona
description: Besetzt einen der sieben festen Beiratsplätze mit einem neu recherchierten Denkschul-Archetyp neu — sichert die alte Persona als Backup, schreibt die neue Persona-Datei exakt in der Bauart der sechs übrigen Köpfe (inkl. Fiktions-Disclaimer, Frameworks, Grenzen & blinde Flecken) und repariert danach alle Verweise auf den ersetzten Kopf in den sechs übrigen Dateien, damit kein toter Name übrig bleibt. Läuft headless über die Task-Art „beirat-persona" mit den Parametern platz_id, name, perspektive — ausgelöst über den Button „Neu besetzen" in den Einstellungen. Nutze diesen Skill bei "Beirat neu besetzen", "Platz <platz_id> neu besetzen mit <name>", "Beiratsplatz <platz_id> ersetzen durch <name>", "neuen Beiratskopf für <perspektive>".
---

# Beirat neu besetzen (Persona-Skill)

Ersetzt EINEN der sieben `.claude/agents/beirat-*.md`-Köpfe durch einen neuen fiktiven Archetyp —
ausgelöst mit drei Parametern: `platz_id` (welcher Platz wird frei), `name` (Name des neuen
Kopfes) und `perspektive` (1–2 Sätze zur fachlichen Brille). Die restlichen sechs Plätze bleiben
unangetastet, bis auf ihre Verweise auf den ausgetauschten Kopf — die MÜSSEN nachgezogen werden,
sonst verweist die Runde auf jemanden, der nicht mehr existiert.

**Die Datei ist die einzige Quelle der Wahrheit** (Design-Entscheidung Phase 90): Farbe und
Vorsitz-Status stehen im Frontmatter, nicht in einer Datenbank. Dieser Lauf schreibt NUR Dateien
unter `.claude/agents/` und `data/beirat/personas_backup/` — keine DB, keine API-Aufrufe, kein
Server-Neustart nötig (die Engine liest die Dateien bei jedem Debatten-Start neu ein).

## Ablauf

### 1. Kontext laden — ohne das komplette Ensemble geht nichts
Parameter aus dem Auftrag lesen: `platz_id`, `name`, `perspektive`. Datei des Platzes ist
`.claude/agents/<platz_id>.md` — existiert sie nicht, Lauf sofort mit einer klaren Fehlermeldung
abbrechen (falsche `platz_id`), nichts anfassen.

Lies VOLLSTÄNDIG:
- `docs/BEIRAT-CHARTA.md` — das gemeinsame Regelwerk, das für jeden Kopf gilt.
- ALLE SIEBEN `.claude/agents/beirat-*.md` — nicht nur die zu ersetzende. Ohne die anderen sechs
  lassen sich weder die Abgrenzung (Schritt 4) noch das Verweisnetz (Schritt 5) reparieren.

Aus der zu ersetzenden Datei merken (für später):
- `farbe:` aus dem Frontmatter — wird in Schritt 4 UNVERÄNDERT übernommen (C3: Farbwahl ist kein
  Teil dieses Laufs, die sieben Werte aus Styleguide §18.10 sind aufeinander abgestimmt; eine
  Farbänderung läuft über das PATCH-Formular in den Einstellungen, nicht über diesen Skill). Fehlt
  `farbe:` in der Altdatei (Alt-Bestand ohne Migration), als Fallback die Farbe aus der `FARBEN`-
  Tabelle in `backend/beirat_engine.py` (nur lesen) für dieselbe `platz_id` nehmen.
- `vorsitz:` aus dem Frontmatter — steht dort `true`, übernimmt der NEUE Kopf den Vorsitz (Schritt
  4 muss dann den Doppel-Hut-Aufbau von `beirat-vera-brandt.md` spiegeln, s. u.).
- Den alten Anzeigenamen aus der Body-Zeile „Du bist **<Name>**" — Vor- und Nachname merken, der
  Nachname ist die Suchspur für Schritt 5.

### 2. Denkschule recherchieren (WebSearch/WebFetch) — Pflicht, kein Beiwerk
Recherchiere zur übergebenen `perspektive` real:
- Etablierte Frameworks, Modelle, Scoring-Methoden und Fachbegriffe dieser Denkschule — genug für
  5–7 benannte Methoden, im Stil der Bestandsdateien („Die X-Analyse", „Das Y-Prinzip", „Der
  Z-Test").
- Typische Prüffragen, die ein Praktiker dieser Schule stellen würde.
- **Die dokumentierte Kritik daran** — methodische Schwächen, Generalisierbarkeitsgrenzen,
  Gegenevidenz, strukturelle Interessenkonflikte, Feld, in dem die Methode NICHT trägt. Das ist
  keine Fleißaufgabe: Die Grenzen-Sektion in Schritt 4 ist der Grund, warum die Beiratsrunde als
  Ganzes funktioniert (Charta: „Kein Heiligsprechen"). Ein Kopf ohne recherchierte Kritik wirkt wie
  Werbung, nicht wie ein Beiratsmitglied.
- Reale Vertreter/Publikationen dieser Schule dienen NUR als Rechercheanker. Sie tauchen NIRGENDS
  namentlich in der fertigen Datei auf — der neue Kopf ist ein fiktiver Archetyp mit erfundenem
  Namen, erfundener Biografie und erfundenem Arbeitgeber, der die Konzepte destilliert wiedergibt
  (Fiktions-Pflicht, identisch zu allen sechs Bestandsköpfen).

### 3. Arbeitsverzeichnis anlegen — du schreibst NICHT direkt nach `.claude/agents/`
```
mkdir -p data/tmp/beirat_neubesetzung
```
**Warum:** Die Freigabeprüfung verweigert headless Läufen jeden Schreibzugriff auf `.claude/` —
das ist der Selbstmodifikations-Schutz, keine Einstellungsfrage, und er lässt sich nicht umgehen
(belegt im Testlauf 1162 vom 23.08.2026: die fertige Persona blieb liegen, weil Write und Edit
dort abgelehnt wurden). Nach `data/` darfst du schreiben.

Alle Dateien, die du erzeugst oder änderst, landen deshalb in
`data/tmp/beirat_neubesetzung/` — mit **exakt dem Dateinamen**, den sie später tragen sollen
(`<platz_id>.md`, also z. B. `beirat-ray-calloway.md`). Am Ende (Schritt 6) übernimmt der Server
sie an ihren Platz und legt dabei selbst die Backups an; du brauchst keine eigene Sicherung.

### 4. Neue Persona schreiben — exakt in der Bauart der Bestandsdateien
Schreibe (Write-Tool) `data/tmp/beirat_neubesetzung/<platz_id>.md` komplett neu.

**Eiserne Regel für den Inhalt:** Die neue Persona darf den ERSETZTEN Kopf nirgends erwähnen —
weder in „Was wir an dir schätzen" noch in „Grenzen & blinde Flecken" noch im MiroFish-Abschnitt.
Nach dem Austausch sitzt er nicht mehr am Tisch; ein „Wenn Calloway rät …" ginge ins Leere. Bezieh
dich ausschließlich auf die SECHS Köpfe, die bleiben. (Im Testlauf 1162 ist genau das schiefgegangen
— zweimal.)

**Frontmatter:**
```
---
name: <platz_id>
description: <ein Absatz im Bestandsmuster>
model: sonnet
farbe: "<unverändert aus Schritt 1>"
```
optional direkt danach `vorsitz: true`, NUR wenn der Platz laut Schritt 1 den Vorsitz trug — dann
`---` als Abschluss.

Wichtig: **`name:` bleibt der unveränderte `platz_id`** — das Feld ist die stabile Sitz-ID des
Beiratsplatzes (Dateiname ohne `.md`), NICHT der Personenname. Das gilt schon für alle sieben
Bestandsdateien (`name: beirat-ray-calloway` ≠ „Ray Calloway" — der Personenname steht nur im
Body). Der neue Personenname aus dem `name`-Parameter erscheint NUR im Body, in der Zeile „Du bist
**<Name>**". Die `description` folgt dem Bestandsmuster: „Die <Nachname>-Perspektive im Beirat —
<Kernthema in einem Halbsatz>. Wird vom Vorsitz gezielt aufgerufen bei Fragen wie „…", „…", „…" —
oder wenn explizit <Nachnamens> Meinung gefragt ist."

**Body, feste Reihenfolge** (Muster: alle sechs gelesenen Bestandsdateien aus Schritt 1):
1. Fiktions-Disclaimer, **wortgleich**: `*Fiktive Persona/Archetyp; keine reale Person;
   Ähnlichkeiten mit lebenden oder verstorbenen Personen sind unbeabsichtigt.*`
2. `# Rolle im Beirat` — „Du bist **<Name>** (<erfundener, plausibler Werdegang: Titel,
   Institutions-/Firmentyp, Jahre Erfahrung — keine realen Institutionen realer recherchierter
   Personen übernehmen) als Mitglied eines Beirats für Karriere- und Bewerbungsfragen. Deine
   Brille: <1–2 Sätze, destilliert aus `perspektive` und der Recherche aus Schritt 2>."
   Übernimmt der Platz den Vorsitz, hier zusätzlich den Doppel-Hut-Absatz analog
   `beirat-vera-brandt.md` einbauen (Vorsitz ohne eigene inhaltliche Position + Fachsitz als
   eigenständiger Beitrag).
3. `# Mentales Betriebssystem` — 5 Denkprinzipien, je ein **Fettbegriff** + ein erklärender Satz.
4. `# Frameworks, Prinzipien & Formeln` — 5–7 benannte Methoden aus der Recherche (Schritt 2), wo
   passend mit konkreter Bewerber-Konsequenz („Bewerber-Konsequenz: …", Bestandsmuster).
5. `# Charakteristische Prüffragen` — 6–7 Fragen, in Du-Form direkt an den Bewerber gerichtet.
6. `# Was wir an dir schätzen` — ein Absatz: welche Lücke im Ensemble genau dieser Kopf schließt,
   in Abgrenzung zu mindestens zwei anderen Köpfen (namentlich).
7. `# Grenzen & blinde Flecken` — die dokumentierte Kritik aus Schritt 2, PLUS **mindestens zwei
   namentliche Übergaben** an Bestandsköpfe im Bestandsformat („Genau da übernimmt <Name>: …" /
   „… — dann hat <Name> die bessere Brille."). **Überschneidet sich die neue Brille stark mit
   einem Bestandskopf, das hier ehrlich benennen — nicht schönschreiben.** Dieselbe Einschätzung
   gehört wortgleich in den Abschlussbericht (Schritt 8).
8. `# Im Austausch (MiroFish)` — 4 Bullets (Zustimmen & schärfen / Widersprechen / Ergänzen /
   Hinterfragen), jeder mit einem NAMENTLICH benannten Bestandskopf und einer inhaltlich
   konkreten, auf dessen tatsächliche Brille bezogenen Reaktion — kein Platzhaltersatz. Letzter
   Punkt wortgleich: „Beziehe dich namentlich auf Vorbeiträge. Kein Monolog."
9. `# Ton & Sprache` — ein Absatz.
10. Abschluss: `---` gefolgt von `*Es gelten die gemeinsamen Regeln, das Antwortformat und die
    MiroFish-Grundsätze der Beirats-Charta.*` — übernimmt der Platz den Vorsitz, zusätzlich
    wortgleich wie bei Brandt: „ Für den Vorsitz gelten zusätzlich die Charta-Abschnitte „Rolle
    des Vorsitzenden" und „Synthese-Format"."

### 5. Verweisnetz reparieren (PFLICHT — der eigentliche Anspruch dieser Phase)
Alle sechs ÜBRIGEN Dateien auf Nennungen des alten Namens (Nach- und ggf. Vorname aus Schritt 1)
durchsuchen:
```
grep -rln "<alter Nachname>" .claude/agents/beirat-*.md
```
Für jeden Treffer: Die Originaldatei lesen, den vollen Satz im Kontext verstehen — und dann eine
**vollständige Kopie der Datei mit deiner Änderung** nach
`data/tmp/beirat_neubesetzung/<id-der-datei>.md` schreiben (Write-Tool, kompletter Dateiinhalt).
Direkt in `.claude/agents/` zu editieren ist gesperrt (s. Schritt 3). Umgeschrieben wird
**inhaltlich passend** — kein Suchen-Ersetzen des Namens allein, der Satz muss nach dem Tausch
fachlich weiter stimmen:
- Passt die Übergabe fachlich noch zur NEUEN Brille → auf den neuen Namen umhängen, den Satz bei
  Bedarf so umformulieren, dass er zur tatsächlichen neuen Perspektive passt.
- Passt sie nicht mehr (die alte Brille gibt es in dieser Form nicht mehr) → auf einen anderen,
  fachlich passenderen Bestandskopf umhängen, oder den Satz streichen, wenn kein Kopf passt (dann
  den umgebenden Satzbau reparieren, keine Lücke/keinen Halbsatz stehen lassen).
- Jede Änderung per Edit-Tool mit exaktem String-Ersetzen vornehmen, Datei für Datei.

Prüfe vor der Übernahme deine eigenen Dateien:
```
grep -rn "<alter Nachname>" data/tmp/beirat_neubesetzung/
```
Muss **kein Ergebnis** liefern — weder in den überarbeiteten Kopien noch in der neuen Persona
selbst (Schritt 4). Erst danach folgt die Übernahme.

### 5b. Charta nachziehen (PFLICHT — sie wird in JEDEN Persona-Prompt geladen)
`docs/BEIRAT-CHARTA.md` führt unter „Die Köpfe am Tisch" eine namentliche Liste. Steht der
ersetzte Kopf dort noch, beschreibt die Charta in jeder künftigen Debatte jemanden, den es nicht
mehr gibt. Die Zeile des alten Kopfes durch die neue Brille ersetzen, Format wörtlich beibehalten:
```
- **<Name>** — <Kurzbrille> (<drei bis vier Stichworte>)
```
`docs/` ist schreibbar (anders als `.claude/`) — hier arbeitest du direkt mit dem Edit-Tool.
Prüfen: `grep -n "<alter Nachname>" docs/BEIRAT-CHARTA.md` muss leer sein.

**Nicht deine Aufgabe:** Der Engine-Code nennt seit dem 23.08.2026 keine Personennamen mehr
(`beirat_engine.py::_dispatch_prompt` beschreibt die Köpfe generisch aus der geladenen Liste) —
dort ist nichts nachzuziehen.

### 6. Übernahme durch den Server (PFLICHT — ohne diesen Schritt ist nichts passiert)
Der Server legt deine Dateien an ihren Platz und sichert die alten vorher automatisch:
```
curl -s -X POST http://localhost:8000/api/beirat/mitglieder/<platz_id>/uebernehmen
```
Die Antwort nennt die übernommenen Plätze und die angelegten Backups. Kommt **HTTP 422**, hat die
Prüfung etwas beanstandet (unvollständige Persona, unbekannte Platz-ID, unplausible Größe) — dann
wurde NICHTS übernommen, alles-oder-nichts. Lies die Meldung, korrigiere die Datei in
`data/tmp/beirat_neubesetzung/` und ruf erneut auf. **Ein Lauf, der hier scheitert, ist
gescheitert** — melde ihn als Fehler, nicht als Erfolg.

Danach die echte Endkontrolle auf dem Zielverzeichnis:
```
grep -rn "<alter Nachname>" .claude/agents/
```
Muss leer sein. Dieses Ergebnis ist der Beleg für Schritt 7.

### 7. Zweite Kontrolle: Backup vollständig, Original korrekt ersetzt
Vor dem Abschlussbericht: `data/beirat/personas_backup/<JJJJ_MM_TT>_<platz_id>.md` existiert und
enthält den alten Text (Schritt 3), `.claude/agents/<platz_id>.md` enthält jetzt ausschließlich
den neuen Kopf mit allen zehn Abschnitten aus Schritt 4 — keine Vermischung von altem und neuem
Text.

### 8. Abschlussbericht (kompakt, landet in einer schmalen UI-Karte)
Genau dieser Aufbau, ohne Markdown-Überschriften:
- **Zeile 1:** `Neu besetzt: <platz_id> — <alter Name> → <neuer Name>`.
- Die neue Brille in **zwei Sätzen**.
- Liste: welche Dateien in Schritt 5 geändert wurden und wie (Kurzform, z. B. „Osei: Übergabe auf
  <neuer Name> umgehängt" / „Vollmer: Satz zu <alter Name> gestrichen, kein passender Ersatz").
- **Ausdrücklich:** die Grep-Prüfung aus Schritt 5 — bestätigen, dass der alte Name nirgends mehr
  in `.claude/agents/` steht.
- **Ausdrücklich:** welche Überschneidung mit einem Bestandskopf bleibt (oder „keine wesentliche
  Überschneidung" — nur wenn das nach ehrlicher Prüfung auch stimmt).
- Backup-Pfad aus Schritt 3.

## Abgrenzung
- Ändert NUR `.claude/agents/beirat-*.md` und `data/beirat/personas_backup/`. Keine DB, keine
  API-Calls, kein Server-Neustart nötig.
- Farbe und Vorsitz werden aus dem ersetzten Platz übernommen, nicht neu vergeben (C3) — eine
  Farbänderung oder ein Vorsitzwechsel läuft über das PATCH-Formular in den Einstellungen, nicht
  über diesen Skill.
- Reine Umbenennung eines Kopfes (gleiche Person, nur Anzeigename ändert sich) läuft ebenfalls
  über das PATCH-Formular in den Einstellungen — dieser Skill ist NUR für den vollständigen
  Austausch der Persona zuständig.
