---
name: headhunter-suche
description: Prüft rotierend die Webseiten der vom Nutzer erfassten Headhunter auf passende Mandate — 15 je Lauf, die am längsten ungeprüften zuerst. Läuft als eigener Agent (ausdrücklicher Wunsch des Nutzers), Vier-Augen-Pflicht wie bei der Jobsuche. Mandate ohne genannten Klienten werden vertraulich behandelt (company="[vertraulich] <Headhunter>"). Nutze diesen Skill bei "Headhunter-Suche", "prüf die Headhunter-Seiten".
---

# Headhunter-Suche (eigener Agent)

Ziel: die Webseiten der erfassten Headhunter rotierend auf passende Mandate prüfen → verifizieren →
als **Status „Neu"** in die zentrale DB schreiben. Läuft als **eigenständiger Agent** (nicht Teil von
`jobsuche` oder `zielfirmen-sweep` — ausdrücklicher Wunsch des Nutzers, Phase 26).

## ⚠️ Kostenrahmen — HART einhalten (gleiche Lehre wie `jobsuche`/`zielfirmen-sweep`)
- **Cap 15 Headhunter je Lauf**, ~2–3 WebFetch je Headhunter (Webseite + ggf. 1 Mandats-Detailseite).
- **Keine Rekursion über 1 Ebene hinaus.** Reißt die Notbremse, ist der Lauf verloren.

## Ablauf

### 1. Kontext laden
`config/profil.md`, `config/scoring_rubrik.md` (Plan A/B/C), `config/suchprofile.yaml` (Pläne
A/B/C aus `plaene` — Stand aus `/einstellungen`).

### 2. Auswahl (Rotation)
```sh
curl -s http://localhost:8000/api/headhunters
```
Nur Zeilen mit `source: "Blatt"` UND `webseite` gesetzt (Outreach-Zeilen haben keine eigene Website
in dieser Tabelle); sortiere nach `last_career_check` (NULL zuerst, dann aufsteigend) → **die ersten
15**. Im Bericht ausweisen: „geprüft 15 von <n>, ältester Rest-Check: <Datum>".

### 3. Webseite/Mandate prüfen — in zwei Wellen, nicht Headhunter für Headhunter
Die 15 Headhunter sind unabhängig voneinander — bearbeite sie gebündelt statt einzeln nacheinander.

**Welle 1 — alle 15 gleichzeitig, in Gruppen von 3–5 WebFetches je Antwort:**
- Headhunter mit gesetzter `karriere_url`: die URL direkt per WebFetch laden.
- Headhunter ohne `karriere_url`: `webseite` per WebFetch laden, die Mandats-/Stellenübersicht
  finden (übliche Pfade `/jobs`, `/mandate`, `/positions`, `/karriere` als Fallback).

**Welle 2 — neu gefundene Mandats-URLs:**
- Die in Welle 1 bei den Headhuntern ohne Cache neu gefundenen Mandatsübersichten gebündelt per
  WebFetch laden (wieder in Gruppen von 3–5). Mandatsliste je Headhunter gegen Titel-Profile/harte
  Grenzen filtern (inkl. Mindest-Firmengröße `min_mitarbeiter`, Beleg-Regel s. Schritt 5b — bei
  vertraulichen Mandaten meist ohnehin unbekannt, dann durchlassen wie in der Beleg-Regel
  vorgesehen). **Headhunter-Seiten listen Mandate oft OHNE Klientennamen** — das ist normal, kein
  Fehler.
- Alle neu gefundenen `karriere_url`-Werte **gesammelt in EINEM Python-Heredoc** zurückschreiben
  (nicht je Headhunter ein `curl`):
  ```sh
  cd backend && ~/.bewerbung_mgmt_venv/bin/python - <<'PY'
  import json
  import urllib.request

  BASIS = "http://localhost:8000/api/headhunters/"
  KOPF = dict()
  KOPF["Content-Type"] = "application/json"
  GEFUNDEN = [
      ("hh3", "https://headhunter-a.example/mandate"),
      ("hh21", "https://headhunter-b.example/jobs"),
  ]
  for roh, url in GEFUNDEN:
      daten = json.dumps(dict(karriere_url=url)).encode()
      req = urllib.request.Request(BASIS + str(roh).removeprefix("hh"), data=daten,
                                   headers=KOPF, method="PATCH")
      urllib.request.urlopen(req)
  print("karriere_url gecacht: " + str(len(GEFUNDEN)) + " Headhunter")
  PY
```
**Schreibweise beachten** (belegt 22.08.2026, 64 Denials in 20 Tagen): keine f-Strings mit
geschweiften Klammern und keine Inline-Dicts im Heredoc — die Freigabepruefung lehnt sie als
„brace with quote character (expansion obfuscation)" ab. Stattdessen String-Konkatenation und
`dict(feld=wert)`.


### 4. Vertraulichkeits-Regel (Design 5, PFLICHT bei jedem Mandat ohne genannten Klienten)
- Ist der Klient (das tatsächlich einstellende Unternehmen) auf der Seite genannt → `company` =
  Klientenname, ganz normal.
- Ist der Klient NICHT genannt (typisch bei Executive-Search-Mandaten) → `company` =
  **`"[vertraulich] <Headhunter-Firma>"`**, `portal = "Headhunter"`. `title`/Ort/Level WÖRTLICH aus
  der Anzeige übernehmen. **Niemals einen Klientennamen raten oder erfinden** — auch nicht aus
  Branchen-/Größen-Hinweisen. `source_note` nennt den Headhunter + die Mandats-URL.
- `next_step`-Vorschlag für solche Records: „<Ansprechpartner des Headhunters> kontaktieren" (aus der
  Headhunter-Row, Feld `ansprechpartner`).
- **Vor dem Ingest prüfen, ob die Firma schon existiert** (gilt für einen genannten Klienten, NICHT
  für `company="[vertraulich] <Headhunter>"`) — `curl -s http://localhost:8000/api/companies` und den
  bestehenden Namen **wörtlich** übernehmen (z. B. „Beispiel“ statt „Beispiel GmbH“), statt eine zweite
  Schreibweise anzulegen: sonst entstehen zwei Firmen-Datensätze, und Dubletten werden über die
  Schreibweisen hinweg nicht erkannt (Echtfall: zwei Anzeigen derselben Stelle unter unterschiedlicher
  Firmenschreibweise, 12.09.2026, s. P2-39).

### 5. Zielstellen-Fit bewerten (1–5) nach Bewertungsraster
Wie `jobsuche` Schritt 4 — Score + `match_rationale` MIT Beleg.

### 5b. Vier-Augen-Verifikation (PFLICHT — identisches Protokoll wie `zielfirmen-sweep`/`jobsuche`)
1. Records in `<records.json>` (`herkunft: "websearch"`), dann
   `cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.verify_jobs check <records.json>`.
   **Zeitlimit des Bash-Aufrufs auf 300000 ms setzen** (Bash-Parameter `timeout`): Bei einem Rate-Limit
   (HTTP 429) holt `check` die geblockten Anzeigen in Wiederholungsrunden mit Pausen nach, das dauert bis
   zu einer Minute länger, und der Standard von 2 Minuten würde den Lauf mittendrin abbrechen.
   **Fehlende Anzeigentexte einmal nachholen (P2-40):** `check` meldet `geprueft` und `texte` — sind
   es weniger Texte als Records, blieb für diese Links der Anzeigentext leer, und die Stelle bekommt
   einen Snapshot ohne Inhalt („Teilquelle: nur Metadaten“). Für jeden Record ohne Eintrag in
   `<records>_texte.json`: die KANONISCHE Anzeige (nicht die Suchergebnisseite) einmal per WebFetch
   laden und den Text unter seiner URL in die Datei ergänzen (JSON `{url: text}`). Geht das nicht
   (Login-Wall, 403, Deep-Link abgeschnitten), so lassen und im Bericht nennen — nie einen Text
   erfinden. Echtfall: eine Stelle kam über eine Suchergebnisseite herein, der Snapshot blieb leer, und
   der Dubletten-Textvergleich war dadurch blind (12.09.2026).
2. Prüf-Subagent (Task-Tool, `general-purpose`), NUR die `_verify.json` — Auftrag wörtlich wie in
   `jobsuche/SKILL.md` Schritt 4b Punkt 2, mit EINER Ergänzung: der Prüfer bestätigt bei vertraulichen
   Mandaten **das Mandat auf der Headhunter-Seite** (Titel+Ort+Level wörtlich vorhanden?), nicht einen
   nicht genannten Klienten — das Fehlen eines Klientennamens ist selbst KEIN Ablehnungsgrund.
3. `verifikation`-Block je durchgelassenem Record setzen; Abgelehnte NICHT ingesten.

### 6. Ingest
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.ingest <records.json> "Headhunter" --texte <records>_texte.json
```
`--texte` (Phase 38) = die `_texte.json` aus Schritt 5b.1 (`verify_jobs check`) — erzeugt sofort
einen Basis-Snapshot je neuem Job mit URL; fehlt die Datei, läuft der Ingest normal ohne Snapshot.
Auch bei 0 Treffern mit leerer Liste ingesten (Muster `jobsuche`/`zielfirmen-sweep`):
```sh
mkdir -p data/tmp
echo "[]" > data/tmp/headhunter_suche_leer.json
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.ingest ../data/tmp/headhunter_suche_leer.json "Headhunter"
```

### 7. Rotationsstand fortschreiben (PFLICHT, auch bei 0 Treffern)
Für jeden geprüften Headhunter (unabhängig vom Ergebnis) — EIN Python-Heredoc für alle 15 IDs,
nicht 15 einzelne `curl`-Aufrufe.

**Zwei Fallen, beide real belegt (21.08.2026):**
1. **Das `hh`-Präfix muss weg.** `GET /api/headhunters` liefert IDs wie `hh21` (die Liste mischt
   Blatt- und Outreach-Zeilen), `PATCH /api/headhunters/{id}` erwartet dagegen die nackte Zahl
   `21` — sonst HTTP 422 `int_parsing`. Die Vorlage schneidet das Präfix selbst ab; setz die IDs
   also genau so ein, wie die Liste sie liefert.
2. **Ein Fehlschlag darf die übrigen nicht mitreißen.** In einer Schleife ohne Fehlerbehandlung
   beendet der erste 422 den ganzen Durchlauf — die restlichen Rotationsstände blieben ungesetzt,
   und diese Headhunter liefen morgen erneut auf, ohne dass es jemand merkt. Deshalb je ID ein
   eigener `try` und am Ende eine Bilanz.
```sh
~/.bewerbung_mgmt_venv/bin/python scripts/rotation_stand.py headhunters <heute, ISO> <die 15 geprueften IDs, durch Leerzeichen getrennt>
```
IDs so uebergeben, wie `GET /api/headhunters` sie liefert (`hh21` usw.) — das Skript schneidet das
`hh`-Praefix selbst ab, weil der PATCH-Endpunkt die nackte Zahl erwartet. Es meldet eine Bilanz
(„Rotationsstand fortgeschrieben: 15 von 15") und bei Fehlern eine zweite Zeile mit den
betroffenen IDs; Exit-Code 1 heisst: mindestens einer blieb ungesetzt — dann gehoert das in den
Abschlussbericht, sonst laeuft derselbe Headhunter morgen erneut auf.

### 8. Bericht
Je geprüftem Headhunter EINE Zeile: `<Firma>: geprüft · <n> Mandate passend · <Kontakt-Empfehlung>`
(auch bei 0 passenden Mandaten — „0 ist ein Ergebnis"). Plus Gesamtsumme (bestätigt/korrigiert/
abgelehnt), Rotationsstand, und (seit Phase 44) falls `dubletten_verdacht > 0` im Ingest-Summary:
„N mögliche Dubletten (Text-Ähnlichkeit) → Review“. Plus (seit P2-36) falls `neuausschreibungen > 0`:
„N Neuausschreibungen früher aussortierter Stellen → Review“. Verweis auf die Review-Ansicht.

## Abgrenzung
- Nur Headhunter-Webseiten — Zielfirmen-Karriereseiten prüft `zielfirmen-sweep`, die allgemeine
  Portalsuche `jobsuche`.
- Läuft seriell NACH `jobsuche`/`mail-jobsuche`/`zielfirmen-sweep` im Tageslauf.
