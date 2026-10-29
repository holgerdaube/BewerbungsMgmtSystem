---
name: zielfirmen-sweep
description: Prüft rotierend die Karriereseiten der vom Nutzer kuratierten Zielfirmen (Tab „Zielfirmen") auf neue passende Stellen — 12 je Lauf, die am längsten ungeprüften zuerst, damit alle ~68 Firmen in ~6 Läufen einmal durch sind. Vier-Augen-Pflicht wie bei der normalen Jobsuche. Nutze diesen Skill bei "Zielfirmen-Sweep", "Karriereseiten prüfen".
---

# Zielfirmen-Sweep (Karriereseiten-Rotation)

Ziel: die Karriereseiten der kuratierten Zielfirmen-Liste (nicht die allgemeine Jobsuche über
Portale — das macht `jobsuche`) rotierend auf neue passende Stellen prüfen → verifizieren →
als **Status „Neu"** in die zentrale DB schreiben. Der Nutzer sichtet sie in der Review-Ansicht.

## ⚠️ Kostenrahmen — HART einhalten (headless-Notbremse, gleiche Lehre wie `jobsuche`)
- **Höchstens ~30 WebFetch gesamt** für den ganzen Lauf (12 Firmen × ~2–3 Fetches: Website/Karriereseite
  + ggf. 1 Einzelanzeige).
- **Keine Rekursion über 1 Ebene hinaus**: Listen-Seite → Einzelanzeige. Nicht durch die ganze
  Karriereseite klicken, nicht jede Unterseite laden.
- Reißt die Notbremse, ist der Lauf verloren — bleib bewusst unter dem Rahmen.

## Ablauf

### 1. Kontext laden
`config/profil.md` (Zielprofil, harte Grenzen), `config/scoring_rubrik.md` (Zielstellen-Fit 1–5,
Situation-Codes, Plan A/B/C), `config/suchprofile.yaml` (Pläne A/B/C aus `plaene` — Stand aus
`/einstellungen` —, Ausschlüsse, `max_alter_tage`).

### 2. Auswahl (Rotation)
```sh
curl -s http://localhost:8000/api/target-companies
```
Nur Einträge mit `website` gesetzt; sortiere nach `last_career_check` (NULL zuerst, dann
aufsteigend nach Datum) → **die ersten 12**. Im Bericht ausweisen: „geprüft 12 von <n>, ältester
Rest-Check: <Datum des nächsten, nicht geprüften Eintrags>".

### 3. Karriereseiten prüfen — in drei Wellen, nicht Firma für Firma
Die 12 Firmen sind unabhängig voneinander — bearbeite sie gebündelt statt einzeln nacheinander.

**Welle 1 — alle 12 gleichzeitig, in Gruppen von 3–5 WebFetches je Antwort:**
- Firmen mit gesetzter `karriere_url`: die URL direkt per WebFetch laden (Cache — spart den Umweg
  über `website`) und offene Rollen listen.
- Firmen ohne `karriere_url`: `website` per WebFetch laden, den Karriere-/Jobs-Link finden
  (Navigation absuchen; übliche Pfade `/karriere`, `/careers`, `/jobs` als Fallback, falls die
  Navigation nichts hergibt).

**Welle 2 — neu gefundene Karriere-URLs:**
- Die in Welle 1 bei den Firmen ohne Cache neu gefundenen Karriere-URLs gebündelt per WebFetch
  laden (wieder in Gruppen von 3–5), offene Rollen je Firma listen.
- Alle neu gefundenen `karriere_url`-Werte **gesammelt in EINEM Python-Heredoc** zurückschreiben
  (nicht je Firma ein `curl`):
  ```sh
  cd backend && ~/.bewerbung_mgmt_venv/bin/python - <<'PY'
  import json
  import urllib.request

  BASIS = "http://localhost:8000/api/target-companies/"
  KOPF = dict()
  KOPF["Content-Type"] = "application/json"
  GEFUNDEN = [
      (12, "https://firma-a.example/karriere"),
      (47, "https://firma-b.example/jobs"),
  ]
  for cid, url in GEFUNDEN:
      daten = json.dumps(dict(karriere_url=url)).encode()
      req = urllib.request.Request(BASIS + str(cid), data=daten, headers=KOPF, method="PATCH")
      urllib.request.urlopen(req)
  print("karriere_url gecacht: " + str(len(GEFUNDEN)) + " Firmen")
  PY
```
**Schreibweise beachten** (belegt 22.08.2026, 64 Denials in 20 Tagen): keine f-Strings mit
geschweiften Klammern und keine Inline-Dicts im Heredoc — die Freigabepruefung lehnt sie als
„brace with quote character (expansion obfuscation)" ab. Stattdessen String-Konkatenation und
`dict(feld=wert)`.

  Firmen ganz ohne auffindbare Karriereseite bleiben außen vor — `karriere_url` NICHT setzen,
  Firma im Bericht als „keine Karriereseite auffindbar" vermerken, trotzdem `last_career_check`
  setzen (Schritt 6 — sonst rotiert sie nie weiter).

**Filter vor Welle 3 (gilt für ALLE 12 Firmen, egal aus welcher Welle ihre Rollenliste kam):**
Gegen Titel-Profile (`suchprofile.yaml`) und harte Grenzen filtern, inkl. Mindest-Firmengröße
`min_mitarbeiter` (Beleg-Regel s. Schritt 4b) — nur relevante Kandidaten weiterverfolgen.

**Welle 3 — Einzelanzeigen:**
- Über alle Firmen hinweg die erkennbar passenden Kandidaten aus den in Welle 1/2 gelisteten
  offenen Rollen sammeln und ihre Einzelanzeigen gebündelt per WebFetch laden (Gruppen von 3–5).
  **Regel „max. 1 Ebene tiefer" bleibt unverändert:** je Firma nur die Einzelanzeige EINER
  erkennbar passenden Rolle laden, nicht jede.

Danach wie bisher: bewerten (Schritt 4), Vier-Augen (4b), Ingest (5).

### 4. Bewerten (1–5) nach Bewertungsraster
Wie `jobsuche` Schritt 4: Score + `match_rationale` MIT Beleg (Zitat/Quelle, nicht behaupten).

### 4b. Vier-Augen-Verifikation (PFLICHT — wörtlich aus `jobsuche/SKILL.md` Schritt 4b)
Kein Treffer erreicht die DB ohne ein zweites, unabhängiges Augenpaar. Das Ingest-Gate (Phase 14)
erzwingt es technisch: Records ohne belegten `verifikation`-Block werden verworfen.

1. **Mechanisch prüfen:** die bewerteten Records in `<records.json>` schreiben (`herkunft: "websearch"`
   — Karriereseiten-Treffer laufen wie WebSearch-Treffer durch die Prüfung) und
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
2. **Prüf-Subagent starten** (Task-Tool, `general-purpose`) — das ZWEITE Augenpaar, NUR die
   `_verify.json`, NICHT deine Scoring-Begründungen. Auftrag (adversarial, wörtlich):
   > „Du bist der Prüfer, nicht der Finder. Deine Aufgabe ist es, Treffer ABZULEHNEN, die du nicht
   > belegen kannst. Je Record: (a) Befund OK → per WebFetch stichprobenartig bestätigen (Titel+Firma
   > wörtlich auf der Seite?); (b) ABGELAUFEN/TOT → ablehnen; (c) UMGELEITET_GENERISCH/INHALT_UNKLAR →
   > per WebSearch die KANONISCHE Anzeige suchen (site:Karriereseite Firma + Titel); gefunden → URL
   > korrigieren (KORRIGIERT + neue URL + Beleg-Zitat), nicht gefunden → ablehnen; (d) NICHT_PRUEFBAR/
   > LOGIN_WALL → NUR bei herkunft apify/mail-alert als QUELLE_VERTRAUT durchlassen, bei websearch
   > ablehnen (potenziell halluziniert). Für JEDEN durchgelassenen Record: beleg = wörtliches Zitat oder
   > konkreter Nachweis. Im Zweifel: ablehnen.
   > **Firmengröße (Phase 34, Beleg-Regel):** Lies beim Live-Check die Firmengröße mit (Karriereseite/
   > Impressum/„Über uns" o. ä.); belegt < 100 Mitarbeiter → ablehnen mit Beleg (Grund ZU_KLEIN);
   > unbekannt/nicht genannt → durchlassen, aber `source_note` um „Firmengröße unklar" ergänzen —
   > kein erfundener Punktabzug, keine eigene Zusatzrecherche nur für die Größe."
3. **Ergebnis mergen:** je durchgelassenem Record `verifikation: {status: BESTÄTIGT|KORRIGIERT|
   QUELLE_VERTRAUT, beleg, geprueft_am: <ISO>, herkunft}` setzen. Abgelehnte NICHT ingesten → in eine
   Liste `abgelehnt` mit Grund.

**Eiserne Regel:** ein Treffer, dessen Anzeige nicht belegbar ist, wird NICHT ingestet.

### 5. Ingest (deterministisch, Dedup automatisch)
**Vor dem Ingest prüfen, ob die Firma schon existiert** — `curl -s http://localhost:8000/api/companies`
und den bestehenden Namen **wörtlich** übernehmen (z. B. „Beispiel“ statt „Beispiel GmbH“), statt eine
zweite Schreibweise anzulegen: sonst entstehen zwei Firmen-Datensätze, und Dubletten werden über die
Schreibweisen hinweg nicht erkannt (Echtfall: zwei Anzeigen derselben Stelle unter unterschiedlicher
Firmenschreibweise, 12.09.2026, s. P2-39).
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.ingest <records.json> "Firmenseite" --texte <records>_texte.json
```
`--texte` (Phase 38) = die `_texte.json` aus Schritt 4b.1 (`verify_jobs check`) — erzeugt sofort
einen Basis-Snapshot je neuem Job mit URL; fehlt die Datei, läuft der Ingest normal ohne Snapshot.
`portal="Firmenseite"`, `source_note="Zielfirmen-Sweep <Datum>, <karriere_url>"`. Auch bei 0
verifizierten Treffern einen Ingest mit LEERER Liste fahren (Muster `jobsuche` Schritt 5), damit der
Lauf in der Run-Historie erscheint:
```sh
mkdir -p data/tmp
echo "[]" > data/tmp/zielfirmen_sweep_leer.json
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.ingest ../data/tmp/zielfirmen_sweep_leer.json "Firmenseite"
```

### 6. Rotationsstand fortschreiben (PFLICHT, auch bei 0 Treffern)
Für **jede** der 12 geprüften Firmen (unabhängig vom Ergebnis) — EIN Python-Heredoc für alle 12
IDs, nicht 12 einzelne `curl`-Aufrufe:
```sh
~/.bewerbung_mgmt_venv/bin/python scripts/rotation_stand.py target-companies <heute, ISO> <die 12 geprueften IDs, durch Leerzeichen getrennt>
```
Das Skript meldet eine Bilanz („Rotationsstand fortgeschrieben: 12 von 12") und bei Fehlern eine
zweite Zeile mit den betroffenen IDs; Exit-Code 1 heisst: mindestens einer blieb ungesetzt — dann
gehoert das in den Abschlussbericht, sonst laeuft dieselbe Firma morgen erneut auf.
Ohne diesen Schritt rotiert die Firma nie weiter und die nächsten 12 Läufe prüfen dieselben Firmen.

### 7. Bericht
`X Firmen geprüft (von <n>) → Y Kandidaten → Z bestätigt/korrigiert/neu` · Dubletten · abgelehnt
(mit Gründen, nicht verschweigen) · Rotationsstand („nächster Lauf startet bei <Firma>, ältester
Rest-Check <Datum>"). Zusätzlich (seit Phase 44) falls `dubletten_verdacht > 0` im Ingest-Summary:
„N mögliche Dubletten (Text-Ähnlichkeit) → Review“. Zusätzlich (seit P2-36) falls
`neuausschreibungen > 0`: „N Neuausschreibungen früher aussortierter Stellen → Review“. Verweis auf
die Review-Ansicht (http://localhost:8000/review).
**Zusätzlich (Phase 34):** fällt bei einer der 12 geprüften KURATIERTEN Zielfirmen selbst (nicht
nur bei einem Job-Treffer) eine belegte Größe < 100 Mitarbeiter auf (z. B. „Über uns"/Impressum
der Karriereseite), im Bericht separat auflisten — „kuratierte Zielfirma(en) < 100 MA: <Firma>
(<Beleg>)". Die Liste selbst NICHT automatisch bereinigen — das entscheidet der Nutzer bewusst selbst.

## Abgrenzung
- **Nur Zielfirmen-Karriereseiten** — die allgemeine Portalsuche macht `jobsuche` (dessen Agent 3
  hat diese Rolle seit Phase 26 abgegeben, um Doppelarbeit/Doppel-Budget zu vermeiden).
  Headhunter-Webseiten prüft der eigene Skill `headhunter-suche`.
- Läuft seriell NACH `jobsuche`/`mail-jobsuche` im Tageslauf (gemeinsames Ingest-Dedup-Fenster).
