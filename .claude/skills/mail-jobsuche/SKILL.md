---
name: mail-jobsuche
description: Verarbeitet Job-Alert-Mails (LinkedIn u. a.) aus dem Gmail-Postfach des Nutzers zu Stellen im Bewerbungs-Management-System — sammelt die Alert-Mails ein, extrahiert je Digest MEHRERE Postings, wendet die harten Grenzen an, bewertet den Zielstellen-Fit 1–5 nach Bewertungsraster (mit Beleg) und schreibt neue Treffer über den normalen Ingest (Dedup gegen die Apify/WebSearch-Treffer) als "Neu" in die zentrale DB. Jede Mail wird genau EINMAL angefasst. Nutze diesen Skill bei "Mail-Jobsuche", "Postfach-Stellen prüfen", "Job-Alerts verarbeiten", "prüfe die Job-Mails".
---

# Mail-Jobsuche — Stellen aus dem Postfach

Ziel: Job-Alert-Mails (LinkedIn, künftig Xing/Jobgether) → enthaltene Postings extrahieren →
harte Grenzen + 1–5 bewerten → über den **normalen Ingest** als **Status "Neu"** in die zentrale DB
(`data/bewerbung.sqlite`). Der Nutzer sichtet sie in der **Review-Ansicht**. **Kein Auto-Bewerben.**

Läuft headless (Task/Runner) wie interaktiv. Der Gmail-Zugang ist **read-only** (`pipeline.gmail_client`
kann nicht senden/labeln) und **kostenlos** — kein Budget-Guard. Die eigentliche Beurteilung
(Extraktion, Grenzen, Scoring) machst DU; das mechanische Einsammeln + der Einmal-Schutz kommen aus
`pipeline.mail_alerts`, das Schreiben aus `pipeline.ingest`.

## Eiserne Regel: URLs kommen aus der Mail
Jede Stellen-URL stammt aus den `links` der Mail (bereits normalisiert auf
`https://www.linkedin.com/jobs/view/<id>/`). **Niemals URLs raten oder konstruieren.** Findest du zu
einem Titel keine passende Link-URL in der Mail, lass das `url`-Feld leer — der Ingest-Dedup arbeitet
dann über Firma+Titel.

## Ablauf

### 1. Kontext laden
- `config/profil.md` — Zielprofil, harte Grenzen, Skill-Gaps.
- `config/scoring_rubrik.md` — Zielstellen-Fit 1–5, Situation-Codes, Plan A/B/C, harte
  Regionsgrenze und der Abschnitt „Harte Grenzen und Score“ (wann aussortiert, wann bewertet wird).
- `config/suchprofile.yaml` — Pläne A/B/C aus `plaene` (Phase 49, Stand aus `/einstellungen`),
  Ausschlüsse (`ausschluss_titel`/`ausschluss_bedingungen`), `max_alter_tage`, `buckets` (die
  aktiven Suchbereiche — ihr Schlüssel ist der Wert für `tab`).

### 2. Alert-Mails einsammeln
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.mail_alerts fetch
```
Gibt `{"neu": n, "offen": k, "uebersprungen": m, "datei": "…/…_Mail_Alerts.json"}` aus.
- **`datei == null`** (bzw. `offen == 0`) → keine offenen Mails, alles bereits verarbeitet.
  Kurzer Bericht, **Ende**.
- Sonst die genannte `datei` lesen: Liste von
  `{gmail_message_id, from, subject, received_at, body_text, links:[{url,text}]}`.
**`offen`, nicht `neu`, ist das Arbeitssignal:** die Datei enthält alle noch nicht per `done`
abgeschlossenen Mails — auch solche aus einem abgebrochenen Vorlauf. Verarbeite genau diese
(idempotent: der Ingest dedupliziert, `done` schließt jede Mail ab).
(Zeitfenster steuert `mail_alerts.max_age_tage`; für einen größeren Nachlauf `fetch --days 7`.)

### 3. Postings extrahieren (je Mail können MEHRERE Stellen stecken — Digests!)
LinkedIn-Alert-Digests listen oft 5–10 Stellen in EINER Mail. Aus **Betreff + `body_text` + `links`**
je Posting herausziehen:
- **Firma**, **Titel**, **Ort**, **work_model** (Remote/Hybrid/Onsite, falls erkennbar),
- **normalisierte URL** = der zum Titel gehörende `links[].url` (die `/jobs/view/<id>/`-Links sind die
  Stellen; Anker-`text` hilft bei der Zuordnung),
- **Gehalt** falls genannt (LinkedIn-Alerts schreiben z. T. „up to €165K/year").
Nicht-Stellen-Inhalte ignorieren: Newsletter-Artikel, „X hat dich erwähnt", „Y hat einen Beitrag
geteilt", Footer-/Hilfe-/Abmelde-Links.

### 4. Harte Grenzen anwenden (aus `suchprofile.yaml`) — nur mit Beleg
Die Grenzen: Ausschluss-Titel (reine Sales-/IC-Rollen), Umzugspflicht, die Kriterien aus
`ausschluss_bedingungen` und `skill_gaps_pruefen`, Mindest-Firmengröße `min_mitarbeiter`
(Beleg-Regel s. Schritt 5b — hier noch keine Ablehnung ohne Beleg), `max_alter_tage` (bei
Mail-Alerts ist die Veröffentlichung meist frisch — im Zweifel Empfangsdatum als Näherung). Was
rausfällt, wird nicht angelegt.

Wie die Grenzen angewendet werden, steht in `config/scoring_rubrik.md` („Harte Grenzen und Score“
und Dimension 3) und gilt hier ohne Abstriche:
- **Aussortiert wird nur, was eine dieser Grenzen BELEGT verletzt.** Beleg ist eine wörtliche
  Angabe aus Mail oder Anzeige, keine Annahme. Die Mail nennt meist nur Titel, Firma und Ort;
  reicht das für einen Beleg nicht, die Anzeige laden (Schritt 5). Ist sie nicht abrufbar, ist
  die Grenze nicht belegt und die Stelle bleibt drin.
- **Ein Ort außerhalb des Umkreises ist für sich kein Ausschlussgrund.** Umzugspflicht heißt:
  reine Präsenz dort oder ein ausdrücklich verlangter Umzug. Hybrid oder ein unbekanntes
  Arbeitsmodell an einem Ort in Deutschland → `tab: "Deutschlandweit"`,
  `relocation_needed: "Nein"`, Abstrich bei der Region im Score. Nur wenn der Bucket
  „Deutschlandweit“ in `buckets` fehlt oder der Ort im Ausland liegt, fällt die Stelle raus.
- **Schwache Passung ist kein Ausschlussgrund.** Passen Funktion, Branche oder Situation nicht,
  bekommt die Stelle Score 1 oder 2 mit Begründung und wird angelegt. Weggelassen wird sie nur,
  wenn eine ausdrückliche Ausschlussregel belegt zutrifft (reine Vertriebsrolle, Rolle ohne
  Führung).
- Ein Posting, das in mehreren Digests steht, zählt einmal.

Je aussortiertem Posting Grenze und Beleg notieren — beides gehört in den Bericht (Schritt 8).

### 5. Zielstellen-Fit bewerten (1–5) nach Bewertungsraster — mit Beleg
Für jede verbleibende Stelle Score + `match_rationale` **mit Beleg** (Zitat aus der Mail/Anzeige).
Die Mail nennt oft nur Titel + Firma + Ort — reicht das für ein fundiertes Urteil **nicht**:
- Stellen-URL **per WebFetch** nachladen (die `/jobs/view/<id>/`-URL aus der Mail). Müssen
  mehrere Postings nachgeladen werden, sind sie voneinander unabhängig — die WebFetch-Aufrufe
  gebündelt absetzen (Gruppen von 3–5 je Antwort), nicht Posting für Posting nacheinander.
- LinkedIn kann eine **Login-Wall** zeigen → dann **konservativ scoren** und `source_note` um
  „nur Mail-Info, Anzeige nicht abrufbar" ergänzen. **KEIN Login-Versuch**, keine erfundenen Details.
Sparsam nachladen (nur wo es das Urteil wirklich braucht) — WebFetch kostet Zeit/Tokens. Aber
immer dort, wo sonst eine Grenze ohne Beleg greifen würde (Schritt 4).

**Jede verbleibende Stelle geht weiter in Schritt 5b und den Ingest, unabhängig vom Score** —
auch mit 1 oder 2.

### 5b. Vier-Augen-Verifikation (PFLICHT — zwischen Scoring und Ingest)
Kein Treffer erreicht die DB ohne ein zweites, unabhängiges Augenpaar. Das Ingest-Gate (Phase 14)
erzwingt es technisch: Records ohne belegten `verifikation`-Block werden verworfen.

1. **Mechanisch prüfen:** die bewerteten Records in `<records.json>` schreiben (je Record ein Feld
   `herkunft`: `mail-alert`) und
   `cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.verify_jobs check <records.json>` —
   erzeugt `<name>_verify.json` mit `pruefung`-Block je Record (befund ∈ TOT/ABGELAUFEN/
   UMGELEITET_GENERISCH/NICHT_PRUEFBAR/LOGIN_WALL/OK/INHALT_UNKLAR · http_status · final_url · beleg).
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
2. **Prüf-Subagenten starten** (Task-Tool, `general-purpose`) — das ZWEITE Augenpaar. Gib ihm NUR die
   `_verify.json`, NICHT deine Scoring-Begründungen. Auftrag (adversarial, wörtlich):
   > „Du bist der Prüfer, nicht der Finder. Deine Aufgabe ist es, Treffer ABZULEHNEN, die du nicht
   > belegen kannst. Je Record: (a) Befund OK → per WebFetch stichprobenartig bestätigen (Titel+Firma
   > wörtlich auf der Seite?); (b) ABGELAUFEN/TOT → ablehnen; (c) UMGELEITET_GENERISCH/INHALT_UNKLAR →
   > per WebSearch die KANONISCHE Anzeige suchen (site:Karriereseite Firma + Titel); gefunden → URL
   > korrigieren (KORRIGIERT + neue URL + Beleg-Zitat), nicht gefunden → ablehnen; (d) NICHT_PRUEFBAR/
   > LOGIN_WALL → als QUELLE_VERTRAUT durchlassen (herkunft mail-alert = authentisch: die Anzeige
   > existierte nachweislich im Alert), sonst ablehnen. Für JEDEN durchgelassenen Record: beleg =
   > wörtliches Zitat oder konkreter Nachweis. Im Zweifel: ablehnen.
   > **Konflikt-Check (Phase 21):** Vergleiche beim Live-Check zusätzlich die STRUKTURIERTEN Merkmale
   > der Anzeige (LinkedIn-Chips: Workplace-Type On-site/Remote/Hybrid, Standort, Seniority; bei anderen
   > Portalen die Metadaten-Zeile) mit dem ANZEIGENTEXT. Widersprechen sie sich bei Arbeitsmodell,
   > Standort oder Seniorität (nur wenn BEIDE Seiten belegt sind, kein „könnte"): wähle für die Eckdaten
   > die inhaltlich belegte Quelle (Text vor Chip), aber verschweige den Konflikt nicht — trage ihn ins
   > Feld `konflikte` des Records ein, Format
   > `KONFLIKT <Feld>: <Quelle A sagt X> vs. <Quelle B sagt Y> — im Gespräch klären (geprüft <ISO>)`.
   > **Firmengröße (Phase 34, Beleg-Regel):** Lies beim Live-Check die Firmengröße mit
   > (LinkedIn-Größen-Chip/Anzeigentext o. ä.); belegt < 100 Mitarbeiter → ablehnen mit Beleg (Grund
   > ZU_KLEIN); Bracket 51–200 oder unbekannt/nicht genannt → durchlassen, aber `source_note` um
   > „Firmengröße unklar (<Beleg, z. B. LinkedIn 51–200>)" ergänzen — kein erfundener Punktabzug,
   > keine eigene Zusatzrecherche nur für die Größe."
3. **Ergebnis mergen:** je durchgelassenem Record den Block
   `verifikation: {status: BESTÄTIGT|KORRIGIERT|QUELLE_VERTRAUT, beleg, geprueft_am: <ISO>, herkunft: "mail-alert"}`
   setzen (herkunft nur bei QUELLE_VERTRAUT; bei KORRIGIERT ist `url` bereits die korrigierte)
   sowie — falls vorhanden — `konflikte: ["KONFLIKT …"]` (der Ingest hängt sie ans `verify_note` an).
   Abgelehnte NICHT ingesten → in eine Liste `abgelehnt` mit Grund.

**Eiserne Regel:** Ein Treffer, dessen Anzeige nicht belegbar ist, wird NICHT ingestet — auch nicht
„mit Warnhinweis in `source_note`". (Genau das ging am 10.07. schief: 3 tote Treffer trotz Warnung.)

### 6. Ingest (deterministisch, Dedup automatisch)
Ingeste die in 5b **verifizierten** Records (jeder mit `verifikation`-Block). Ingest-Schema
(Schema siehe `backend/pipeline/ingest.py`-Docstring bzw. unten):
- `portal` aus Absender/Inhalt: `/jobs/view/`-URL → **LinkedIn**; jobgether.com → **Jobgether**;
  xing.com → **Xing**.
- `source_note` = „Mail-Alert vom <received_at>" (bei Login-Wall-Fällen s. Schritt 5 ergänzen).
- `published_date` falls in der Mail erkennbar; sonst Empfangsdatum als Näherung — und im
  `source_note` so kennzeichnen („Datum = Mail-Eingang").
Dann je Portal-Mix eine Datei schreiben und:
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.ingest <datei.json> "LinkedIn,Xing,Jobgether" --texte <datei>_texte.json
```
`--texte` (Phase 38) = die `_texte.json` aus Schritt 5b.1 (`verify_jobs check`) — erzeugt sofort
einen Basis-Snapshot je neuem Job mit URL; fehlt die Datei, läuft der Ingest normal ohne Snapshot.
**Auch bei 0 verifizierten Treffern** einen Ingest mit LEERER Liste fahren (Phase 23), damit der Lauf
in der Run-Historie erscheint — sonst ist ein ergebnisloser Mail-Lauf unsichtbar:
```sh
mkdir -p data/tmp
echo "[]" > data/tmp/mailjobsuche_leer.json
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.ingest ../data/tmp/mailjobsuche_leer.json "LinkedIn"
```
Der Ingest dedupliziert automatisch (URL + Firma+Titel) — Stellen, die die Apify/WebSearch-Suche
schon kennt, werden übersprungen und im Ergebnis als Dubletten ausgewiesen. Behalten-Status wie
„Kein Match“ und (seit Phase 41) „Beirat abgelehnt“ sind Tombstones fürs Dedup: derselbe Alert-Link
taucht nie wieder als „Neu“ auf. Seit P2-36: ein NEUER Alert derselben Stelle (Firma+Titel,
Gender-Zusatz egal) im Endstatus erscheint als „Neu“ mit Hinweis `NEUAUSSCHREIBUNG?` — Dubletten
laufender Stellen und Papierkorb-Treffer werden weiter übersprungen.

### 7. Jede Mail als verarbeitet markieren (Einmal-Schutz)
Nach dem Ingest **je Mail**:
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.mail_alerts done <gmail_message_id> --postings <n>
```
`<n>` = Anzahl der aus dieser Mail extrahierten Stellen — **auch `0`** (Newsletter-Fehlfänge nicht
ewig neu anfassen). Ohne diesen Schritt taucht die Mail beim nächsten `fetch` wieder auf.

### 8. Bericht
`X Mails → Y Postings extrahiert → G nach harten Grenzen aussortiert → V4A: A bestätigt /
B korrigiert / C Quelle-vertraut / R abgelehnt (mit Gründen — NICHT verschweigen) → Z neu (davon W
mit Score ≥ 4) · D Dubletten · U unverifiziert`, dazu die Liste der G aussortierten Postings, je
Posting mit Grenze und Beleg (Schritt 4),
plus (seit Phase 44) falls `dubletten_verdacht > 0` im Ingest-Summary: „N mögliche Dubletten
(Text-Ähnlichkeit) → Review" (Repost-Verdacht bei neu angelegten Jobs, kein exakter Dedup-Treffer),
plus (seit P2-36) falls `neuausschreibungen > 0`: „N Neuausschreibungen früher aussortierter Stellen
→ Review“, plus Verweis auf die **Review-Ansicht** (http://localhost:8000/review).

## Record-Schema (ein Objekt je Stelle)
**Vor dem Ingest prüfen, ob die Firma schon existiert** — `curl -s http://localhost:8000/api/companies`
und den bestehenden Namen **wörtlich** übernehmen (z. B. „Beispiel“ statt „Beispiel GmbH“), statt eine
zweite Schreibweise anzulegen: sonst entstehen zwei Firmen-Datensätze, und Dubletten werden über die
Schreibweisen hinweg nicht erkannt (Echtfall: zwei Anzeigen derselben Stelle unter unterschiedlicher
Firmenschreibweise, 12.09.2026, s. P2-39).
```json
{
  "company": "…", "title": "…", "location": "…", "url": "https://www.linkedin.com/jobs/view/<id>/",
  "portal": "LinkedIn|Xing|Jobgether",
  "work_model": "Remote|Hybrid|Onsite", "relocation_needed": "Nein",
  "tab": "<Bucket-Schlüssel aus buckets: Remote | Deutschlandweit | Umkreis-Bucket>", "plan_ab": "A|B",
  "seniority": "Director|VP|Head|Senior Manager|Manager",
  "salary": null, "published_date": "…",
  "situation": "BUILD|SCALE-UP|POST-MERGER|PE|CARVE-OUT|RESTRUCT|RUN|UNKLAR",
  "match_score": 1, "match_rationale": "… mit Beleg …",
  "next_step": "…", "source_note": "Mail-Alert vom <received_at>"
}
```

## Grenzen
- URLs stammen ausschließlich aus der Mail (nur normalisiert) — nie geraten.
- LinkedIn-Anzeigen hinter Login-Wall werden konservativer gescort und in `source_note` gekennzeichnet;
  den Feinschliff macht der Nutzer in der Review.
- Neue Alert-Quellen (Xing/Jobgether direkt): nur die Absenderliste in `config/suchprofile.yaml`
  (`mail_alerts.absender`) erweitern — Absender vorher per `pipeline.gmail_client search` verifizieren.
  Kein Code-Eingriff nötig.
- Reiner Ingest-Lauf. Company-Fit & angepasster CV kommen on demand (`job-deepdive`/`cv-match`/
  `cv-erstellen`); Antwort-Tracking ist `email-check`.
