---
name: jobsuche
description: Führt die tägliche Jobsuche für das Bewerbungs-Management-System des Nutzers aus — sucht über alle Portale, dedupliziert, bewertet den Zielstellen-Fit 1–5 nach Bewertungsraster und schreibt neue Treffer als "Neu" in die zentrale DB. Nutze diesen Skill, wenn der Nutzer sinngemäß sagt "such nach neuen Stellen", "Jobsuche", "neue Runde", "Tageslauf Stellen", "was gibt's Neues" oder den Tracker aktualisieren will.
---

# Jobsuche-Pipeline

Ziel: neue passende Stellen finden → deduplizieren → 1–5 bewerten → als **Status "Neu"** in die
zentrale DB (`data/bewerbung.sqlite`) schreiben. Der Nutzer sichtet sie danach in der **Review-Ansicht**
der Web-App (annehmen → Prüfen / verwerfen → Kein Match). **Kein Auto-Bewerben.**

Läuft headless (Web-App-Button) wie interaktiv. **WebSearch ist der Standardweg** — Apify ist
optional und kostet Geld (s. Schritt 2).

## ⚠️ Kostenrahmen — HART einhalten (headless-Notbremse!)
Dies ist ein **täglicher Inkrement-Lauf**, KEIN vollständiger Crawl. Ein Dutzend gezielter Suchen
schlägt hunderte. Ein früherer Lauf startete 19 Subagenten mit 200+ Suchen und riss die $1,50-
Notbremse bei effektiv $19 — der ganze Lauf schlug fehl, **nichts** wurde gefunden. Deshalb Obergrenzen:
- **Höchstens 3 parallele Subagenten** (einer je Such-Bucket, s. Schritt 2). Keine weiteren.
- **Je Subagent höchstens ~8 WebSearch + 5 WebFetch.** Kein tiefes Nachladen, keine Rekursion.
- **Insgesamt Ziel ≤ 30 Websuchen** für den ganzen Lauf — inklusive des optionalen seriellen
  Radar-Nachlaufs (3×8 + ~6 = das Limit). Lieber wenige treffsichere Queries
  (Titel × Region aus `suchprofile.yaml`) als jede Kombination.
- Reißt die Notbremse, ist der Lauf verloren — bleib bewusst unter dem Rahmen.

## Ablauf

### 1. Kontext laden
Lies zuerst:
- `config/profil.md` — Kurzprofil, harte Grenzen, Skill-Gaps. Zielrollen stehen in den Plänen (unten); weicht ein
  älterer Abschnitt „Zielrolle“ in der Datei davon ab, gelten die Pläne.
- `config/scoring_rubrik.md` — Zielstellen-Fit 1–5, Situation-Codes, Plan A/B/C, harte Regionsgrenze.
- `config/suchprofile.yaml` — **`plaene`** (Phase 49, Stand aus `/einstellungen`): Liste je Plan
  `{plan, label, aktiv, prioritaet, titel, senioritaet, branche}` — NUR Pläne mit `aktiv: true`
  durchsuchen, in `prioritaet`-Reihenfolge (Standard A→B→C, aber die Reihenfolge kommt aus dem
  Feld, nicht aus der Buchstaben-Sortierung). Daneben: Buckets, Ausschlüsse,
  `max_alter_tage`, `min_mitarbeiter`.
- `config/suchprofile.yaml` — **`portale`** (Phase 87, Stand aus `/einstellungen` → Suchportale):
  Liste je Portal `{key, name, url, zugriff, aktiv, standard}`. **NUR Portale mit `aktiv: true`
  durchsuchen** — ein abgeschalteter Eintrag darf im Abschlussbericht nicht mehr auftauchen.
  `zugriff` entscheidet über den Weg:
  - `websearch` → per WebSearch mit der Domain aus `url` als Anker (`site:…`). Diese Portale
    (LinkedIn/Indeed/StepStone/Xing) blocken direkte Abrufe per Bot-Schutz; die URL ist hier
    Domain-Anker, nicht Abruf-Adresse.
  - `fetch` → die `url` mit ersetzten Platzhaltern (`$QUERY`, `$LOCATION`, `$PAGE`) direkt
    abrufen (Nejo, Arbeitsagentur). Meldet der Abruf eine Umleitung auf einen anderen Host,
    ihr EINMAL folgen und die neue Adresse im Abschlussbericht nennen: Dann ist die hinterlegte
    Portal-Adresse veraltet und gehört in den Einstellungen angepasst.
  Die beiden Freizeilen (`key: frei1`/`frei2`) sind vollwertige Portale, kein Sonderfall — sind
  sie gefüllt und aktiv, werden sie wie die übrigen behandelt.
  Feinparameter, die die Oberfläche NICHT abbildet, stehen weiterhin unter **`portale_technik`**
  (Nejo-Filter und `max_seiten`, Arbeitsagentur-`titel_deutsch` und `max_queries_je_lauf`,
  `apify`-Portalnamen, `websearch`-Zusatzquellen).
- `config/zielfirmen.md` — priorisierte Firmen für gezielte Recherche. **Optional:** fehlt sie, ohne sie weiter.
- **Nicht immer vorhanden:** `config/profil.md` (fehlt sie oder ist leer, gelten die harten Grenzen aus
  `suchprofile.yaml` und `scoring_rubrik.md`) und einzelne technische Schlüssel in `suchprofile.yaml`
  (`portale_technik`, `radar_signale`, `ausschluss_bedingungen`, `skill_gaps_pruefen`, `apify_actors`) — eine
  frisch angelegte Datei hat sie zum Teil nicht. Das ist kein Fehler und kein Grund zum Abbruch: Was fehlt,
  entfällt (kein Nejo-Filter, kein Radar-Nachlauf; ohne `titel_deutsch` fragt die Arbeitsagentur mit den deutschen Titeln der Pläne), und der
  Bericht nennt es.
- Haben die aktiven Pläne keinen Titel, gibt es nichts zu suchen: mit dem Hinweis enden, dass die Zielrollen
  unter „Einstellungen“ fehlen. Keine Titel erfinden.

### 2. Parallel suchen (max. 3 Subagenten — ein Bucket je Agent)
Starte **höchstens drei** `general-purpose`-Subagenten, aufgeteilt nach den drei Such-Buckets aus
`suchprofile.yaml` (seit 16.07.2026 — vorher war die Aufteilung Titel×Region gemischt, wodurch
der Umkreis-Bucket nur halbherzig abgedeckt war). **Jeder Agent sucht ALLE AKTIVEN Plan-Titel-
Listen aus `plaene` in SEINEM Bucket, in `prioritaet`-Reihenfolge (Standard A→B→C)** — Pläne mit
`aktiv: false` überspringen, KEINE Titel dafür suchen — und setzt `tab` entsprechend dem Bucket
sowie `plan_ab` entsprechend dem Plan, der den Treffer geliefert hat. Gib jedem im Prompt das
Budget mit („höchstens 8 WebSearch + 5 WebFetch — unabhängige Aufrufe davon in Gruppen von 3–5 je
Antwort gebündelt absetzen, nicht einzeln nacheinander —, dann JSON-Array zurück"). Der
Bündelungs-Hinweis aus dem headless-Suffix erreicht Subagenten NICHT automatisch (der Suffix wird
nur an den Haupt-Agenten angehängt) — deshalb steht er hier wörtlich im Subagenten-Prompt:
- **Agent 1 — Bucket Remote** (die `regionen` des Buckets, z. B. Remote EMEA/DACH/Germany). Remote-Suchsyntax („remote"-Filter
  bzw. -Keyword); bei Nejo zusätzlich `filter_remote` anhängen und bei dünnem Ergebnis einmal
  ohne den Filter nachholen (Regel „Remote-Bucket, dünnes Ergebnis“ in a2 — wörtlich in den
  Prompt dieses Agenten übernehmen). `tab: "Remote"`.
- **Agent 2 — Bucket Deutschlandweit.** Hybrid-/Onsite-Stellen quer durch deutsche Städte;
  **reine Remote-Anzeigen überspringen** (die gehören Agent 1 — sonst doppelt gefundenes Budget,
  das der Dedup nur hinterher wegwirft). `tab: "Deutschlandweit"`.
- **Agent 3 — Umkreis-Bucket** (der Eintrag unter `buckets` in `suchprofile.yaml`, dessen
  Schlüssel weder „Remote" noch „Deutschlandweit" ist — Stadt = dessen `stadt`-Feld, Rückfall
  `regionen[0]`; Radius = dessen `umkreis_km`-Feld, Rückfall die Zahl im Schlüssel; der einzige
  Bucket, in dem Onsite zählt). Fehlt dieser Bucket, entfällt Agent 3 ganz. Suchraum: Orte im
  Umkreis von `<umkreis_km>` km um `<Stadt>`. Nejo hat KEINEN wirksamen Orts-Parameter
  (Phase-29-Verifikation) → Ort in die Nejo-Query aufnehmen („<Titel> <Stadt>") bzw. die
  extrahierten Treffer-Orte gegen den Radius filtern. `tab: "<Bucket-Schlüssel>"`. Lässt sich der Radius nicht
  sicher prüfen, nicht abbrechen: s. Schritt 3 (Region nicht prüfbar).
- **Optionaler Radar-Nachlauf (SERIELL, kein vierter Parallel-Agent):** nach den drei Buckets bei
  übrigem Budget `radar_signale` prüfen (Restructuring-Radar-Firmen mit frischem Signal),
  höchstens ~6 Suchen. Zielfirmen-Karriereseiten prüft seit Phase 26 der eigene, rotierende Skill
  `zielfirmen-sweep` (läuft seriell NACH diesem Skill im Tageslauf) — der Radar-Nachlauf macht das
  NICHT, sonst Doppelarbeit und doppeltes Budget für dieselben Firmen.
Weniger ist ok: bei einem ruhigen Tag reichen 1–2 Bucket-Agenten (dann Remote zuerst).

**a) WebSearch — der Standardweg, immer ausführen.** Alle aktiven Portale mit
`zugriff: websearch` aus der Liste `portale` (Phase 87 — heute LinkedIn/Indeed/StepStone/Xing,
aber die Liste entscheidet, nicht diese Aufzählung) per WebSearch + WebFetch, Domain aus der
hinterlegten `url` als `site:`-Anker. Kostet nichts und hat in Phase 1 live 13 echte Rollen
gefunden — mit einer Handvoll Suchen, nicht mit hunderten.

**a2) Nejo-Direktsuche (Phase 29).** nejo.com (bis September 2026 unter mynejo.com) ist eine
KI-Jobsuchmaschine, die direkt die Karriereseiten der Unternehmen crawlt (SSR, per WebFetch
nutzbar) — deckt auch Stellen ab, die
nicht auf LinkedIn/Indeed/StepStone stehen. Je Titel eines AKTIVEN Plans (Reihenfolge nach
`prioritaet`, Standard A→B→C) × Bucket die URL des Portals `nejo` aus der Liste `portale`
(Phase 87 — nur wenn dort `aktiv: true`; Filter und `max_seiten` weiterhin aus
`portale_technik.nejo`) fetchen: Remote-Bucket → zusätzlich `filter_remote` anhängen, immer `filter_management` anhängen (beide Filter nur, wenn in `portale_technik.nejo` gesetzt). Aus dem gefetchten HTML je Treffer Firma, Titel,
Ort, Arbeitsmodell, Alter ("vor X Tagen") und die Nejo-Job-URL extrahieren. Eiserne Regeln:
- Nejo-Job-URLs NUR wörtlich aus dem gefetchten HTML übernehmen (nie konstruieren). Steht dort
  nur der Pfad (`/de/job/…`), gehört der Host der abgerufenen Seite davor; das ist kein
  Konstruieren.
- Job-DETAILSEITEN NICHT fetchen — sind clientseitig gerendert (TanStack-Start-App), liefern per
  WebFetch nur eine leere JS-Shell, keinen Jobtext.
- Original-Anzeige der Firma per WebSearch suchen (dasselbe Muster wie unten in 4b): gefunden →
  Original-URL als Job-URL verwenden (normal BESTÄTIGT/KORRIGIERT), Nejo-URL in `source_note`
  vermerken; nicht gefunden → Nejo-URL behalten und `herkunft: nejo` setzen (QUELLE_VERTRAUT).
- **Remote-Bucket, dünnes Ergebnis:** Nejos Remote-Filter trifft nur Anzeigen, die Nejo selbst
  als „Remote“ einstuft; Stellen mit Homeoffice-Anteil führt es als „mit Homeoffice“ und blendet
  sie unter dem Filter aus (gemessen 12.10.2026 über 13 Führungstitel: mit `filter_remote` und
  `filter_management` 0–1 Treffer je Titel, nur mit `filter_management` 14–61, auf Seite 1 davon
  mindestens die Hälfte „mit Homeoffice“). Meldet die gefilterte Seite deshalb weniger als
  5 Treffer („N Jobs gefunden“), dieselbe Query EINMAL ohne `filter_remote` nachholen
  (`filter_management` bleibt) und daraus nur Treffer übernehmen, deren Arbeitsmodell „mit
  Homeoffice“ oder „Remote“ lautet UND deren Kurzbeschreibung oder Original-Anzeige
  ortsunabhängiges Arbeiten ausweist. „Vor Ort“ und Hybrid mit fester Präsenz NICHT übernehmen —
  die findet der Deutschlandweit- bzw. Umkreis-Agent in derselben Liste selbst. Das Nachholen
  zählt als ein WebFetch ins Budget.
- `max_alter_tage` gegen die "vor X Tagen"-Angabe der Trefferliste prüfen.
- `portal: "Nejo"` setzen. `max_seiten` aus der config einhalten (fehlt der Wert: 2; Budget-Leitplanke).
Nejo-Fetches zählen ins normale Subagenten-Budget (~8 WebSearch + 5 WebFetch je Subagent) —
dieses Budget wird durch Nejo NICHT erhöht.

**b) Apify — nur auf ausdrücklichen Wunsch** (Task-Art `jobsuche-apify` oder der Nutzer sagt es).
Nicht selbst nach Actors suchen: sie sind in `config/suchprofile.yaml` unter `apify_actors`
gepinnt. Vorher immer den Verbrauch prüfen — im Apify **Free Plan (~5 $/Monat)**:
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.apify_client usage
~/.bewerbung_mgmt_venv/bin/python -m pipeline.apify_client run --portal LinkedIn \
  --query "<Titel aus einem aktiven Plan>" --location "<Region aus einem Bucket>" --max-items 25
```
Regeln: erst `--dry-run`, wenn du dir beim Input unsicher bist. Höchstens **2–3 Läufe** je
Runde (Titel × Region), niemals die volle Titel×Region-Matrix — das sprengt das Monatsbudget.
Fehlt `APIFY_TOKEN`, bricht der Client sauber ab: dann nur mit (a) weitermachen, kein Blocker.
Die Rohdaten liegen in `data/apify/` — Titel-, Ausschluss- und Score-Prüfung machst du selbst.

**c) Arbeitsagentur-Direktsuche (Phase 37, seit Phase 86 auf SSR umgestellt) — DETERMINISTISCH,
KEIN eigener Subagent.** Der Client ruft NICHT mehr die REST-API auf `rest.arbeitsagentur.de` auf
— dieser Host antwortet seit Mitte August 2026 auf JEDEM Pfad mit HTTP 403 (Netzsperre, kein
Auth-Problem, live verifiziert 21.08.2026). **Ein 403 auf `rest.arbeitsagentur.de` ist deshalb
KEIN Grund, den Kanal zu überspringen** — der Client nutzt diesen Host gar nicht mehr. Stattdessen
ruft er die öffentliche Jobsuche-SUCHSEITE ab (serverseitig gerendertes HTML mit eingebettetem
JSON, kein Account, kein Secret) und holt bei Bedarf mehrere Seiten nach. Läuft im Hauptlauf (DU
rufst das CLI direkt auf, kein Subagenten-Budget nötig) mit den DEUTSCHEN Titel-Synonymen aus
`config/suchprofile.yaml` (`portale_technik.arbeitsagentur.titel_deutsch` — der BA-Bestand ist
deutschsprachig, englische Plan-Titel liefern dort meist 0 Treffer; welcher Titel
in welchem Bucket läuft, steht unten unter „Kern und Breite“):
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.arbeitsagentur_client run \
  --was "<Titel aus titel_deutsch, ersatzweise ein deutscher Titel aus den aktiven Plänen>" --days <max_alter_tage> --size 25
```
- **Remote-Bucket:** ohne `--wo` (bundesweit) — der Homeoffice-Parameter (`--arbeitszeit ho`)
  ist mechanisch wirksam UND (neu gemessen 21.08.2026 gegen die SSR-Suchseite, s. Modul-
  Docstring) inzwischen auch für enge Titel ergiebig; trotzdem zusätzlich Remote-/Hybrid-Charakter am Titel/Text der
  Treffer einschätzen, statt sich allein auf den Filter zu verlassen.
- **Deutschlandweit-Bucket:** ebenfalls ohne `--wo`.
- **Umkreis-Bucket:** `--wo "<Stadt>" --umkreis <umkreis_km>` (Felder aus dem Umkreis-Bucket,
  s. Schritt 2 Agent 3; kein Umkreis-Bucket → dieser Punkt entfällt).
`portal: "Arbeitsagentur"` setzen; Job-URL = `url` aus der Ausgabe (Original-Anzeige `externeURL`
falls vorhanden — auf der Suchseite oft gesetzt —, sonst die maschinenlesbare BA-Detailseite).

**Kern und Breite** — die Liste `titel_deutsch` ist nach Priorität geordnet:
- **Kern:** die ersten beiden Titel in JEDEM aktiven Bucket abfragen (Parameter je Bucket wie
  oben).
- **Breite:** jeden weiteren Titel genau EINMAL bundesweit (ohne `--wo`, ohne `--arbeitszeit`)
  und die Treffer anhand von Ort und Text dem passenden Bucket zuordnen. Ohne diesen Schritt
  bleibt jeder Titel ab dem dritten unabgefragt, egal wie lang die Liste ist.

Obergrenze ist `max_queries_je_lauf` aus der config (fehlt der Wert: 6) — nie die volle
Titel×Bucket-Matrix. Reicht sie nicht für Kern und Breite, erst den Kern, dann die Breite in
Listen-Reihenfolge. Die normalisierten Records aus der Ausgabe
(`vorschau` + Rohdatei unter `data/arbeitsagentur/`) gehen in denselben Trichter wie
WebSearch/Nejo/Apify: harte Grenzen (die Mindest-Firmengröße `min_mitarbeiter` greift hier besonders oft — die BA hat
viele Kleinbetriebe) → Scoring → Vier-Augen 4b → Ingest.

Jeder Subagent gibt **nur ein JSON-Array** im Record-Schema (unten) zurück, keine Prosa, keine erfundenen URLs.

### 3. Zusammenführen & harte Grenzen anwenden
- Ausschlüsse aus `suchprofile.yaml` anwenden (`ausschluss_titel`; Umzugspflicht außerhalb
  des aktiven Umkreis-Buckets; die Kriterien aus `ausschluss_bedingungen` und
  `skill_gaps_pruefen`; Mindest-Firmengröße `min_mitarbeiter` — s. Beleg-Regel in Schritt 4b,
  hier noch keine Ablehnung ohne Beleg).
- `max_alter_tage` beachten (Default 30).
- Anwendung nach `config/scoring_rubrik.md`, Abschnitt „Harte Grenzen und Score“: Eine Grenze
  greift nur mit Beleg, Hybrid außerhalb des Umkreises gehört in den Bucket „Deutschlandweit“,
  und schwache Passung ist ein niedriger Score, kein Ausschluss. Je aussortierter Stelle Grenze
  und Beleg für den Abschlussbericht notieren.
- Lässt sich eine Region oder harte Grenze nicht sicher prüfen (Ortsname unbekannt, Entfernung unklar,
  Arbeitsmodell nicht erkennbar), ist das kein Abbruchgrund: Die Grenze gilt als nicht belegt, die Stelle
  bleibt mit Hinweis im `source_note` drin, und der Bericht nennt den Fall.

### 4. Zielstellen-Fit bewerten (1–5) nach Bewertungsraster
Für jede verbleibende Stelle Score + `match_rationale` **mit Beleg** setzen (Zitat/Quelle, nicht behaupten).
Situation ist der wichtigste Filter; Plan-B in BUILD/CARVE-OUT schlägt Plan-A in RUN; Plan-C ist
der Auffang-Plan unterhalb der Leitungsebene aus A/B — eine Manager-Rolle mit Teamführung ist
Plan A, wenn dessen `senioritaet` die Ebene nennt (s. `scoring_rubrik.md` Dimension 2).

### 4b. Vier-Augen-Verifikation (PFLICHT — zwischen Scoring und Ingest)
Kein Treffer erreicht die DB ohne ein zweites, unabhängiges Augenpaar. Das Ingest-Gate (Phase 14)
erzwingt es technisch: Records ohne belegten `verifikation`-Block werden verworfen.

1. **Mechanisch prüfen:** die bewerteten Records in `<records.json>` schreiben (je Record ein Feld
   `herkunft`: `apify` bei Actor-Treffern, `arbeitsagentur` bei BA-Treffern (Phase 37), sonst
   `websearch`) und
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
   > LOGIN_WALL → NUR bei herkunft apify/mail-alert/nejo/arbeitsagentur als QUELLE_VERTRAUT
   > durchlassen, bei websearch ablehnen (potenziell halluziniert). Arbeitsagentur-Treffer
   > (Phase 37) sind meist per (a) regulär BESTÄTIGT zu bekommen — die BA-Detailseiten sind
   > maschinenlesbar; QUELLE_VERTRAUT ist dort nur der Fallback. Für JEDEN durchgelassenen
   > Record: beleg = wörtliches Zitat oder konkreter Nachweis. Im Zweifel: ablehnen.
   > **Konflikt-Check (Phase 21):** Vergleiche beim Live-Check zusätzlich die STRUKTURIERTEN Merkmale
   > der Anzeige (LinkedIn-Chips: Workplace-Type On-site/Remote/Hybrid, Standort, Seniority; bei anderen
   > Portalen die Metadaten-Zeile) mit dem ANZEIGENTEXT. Widersprechen sie sich bei Arbeitsmodell,
   > Standort oder Seniorität, dokumentiere das (nur wenn BEIDE Seiten belegt sind, kein „könnte"):
   > wähle für die Eckdaten die inhaltlich belegte Quelle (Text vor Chip), aber verschweige den
   > Konflikt nicht — trage ihn ins Feld `konflikte` des Records ein, jeder Eintrag im Format
   > `KONFLIKT <Feld>: <Quelle A sagt X> vs. <Quelle B sagt Y> — im Gespräch klären (geprüft <ISO>)`.
   > **Firmengröße (Phase 34, Beleg-Regel):** Lies beim Live-Check die Firmengröße mit
   > (LinkedIn-Größen-Chip/Anzeigentext o. ä.); belegt < <min_mitarbeiter> Mitarbeiter → ablehnen mit Beleg (Grund
   > ZU_KLEIN); ein Bracket, das die Grenze einschließt (z. B. 51–200 bei 100), oder unbekannt/nicht genannt → durchlassen, aber `source_note` um
   > „Firmengröße unklar (<Beleg, z. B. LinkedIn 51–200>)" ergänzen — kein erfundener Punktabzug,
   > keine eigene Zusatzrecherche nur für die Größe."
   (`<min_mitarbeiter>` im Auftrag durch den Wert aus `suchprofile.yaml` ersetzen, Standard 100.)
3. **Ergebnis mergen:** je durchgelassenem Record den Block
   `verifikation: {status: BESTÄTIGT|KORRIGIERT|QUELLE_VERTRAUT, beleg, geprueft_am: <ISO>, herkunft}`
   setzen (herkunft nur bei QUELLE_VERTRAUT; bei KORRIGIERT ist `url` bereits die korrigierte)
   sowie — falls vorhanden — `konflikte: ["KONFLIKT …"]` (der Ingest hängt sie ans `verify_note` an).
   Abgelehnte NICHT ingesten → in eine Liste `abgelehnt` mit Grund.

**Eiserne Regel:** Ein Treffer, dessen Anzeige nicht belegbar ist, wird NICHT ingestet — auch nicht
„mit Warnhinweis in `source_note`". (Genau das ging am 10.07. schief: 3 tote Treffer trotz Warnung.)

### 5. Ingest (deterministisch, Dedup automatisch)
Ingeste die in 4b **verifizierten** Records (jeder mit `verifikation`-Block — Unverifizierte lässt das
Gate nicht durch, es zählt sie als `unverifiziert`):
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.ingest <records.json> "LinkedIn,Indeed,StepStone,Xing,WebSearch,Nejo,Arbeitsagentur" --texte <records>_texte.json
```
`--texte` (Phase 38) übergibt die `<records>_texte.json`, die `verify_jobs check` in Schritt 4b.1
automatisch mitschreibt (Anzeigentexte der Live-Checks) — jeder neue Job mit URL bekommt sofort
einen Basis-Snapshot unter „Dateien & Dokumente", statt erst bei der Firma-Prüfung. Flag weglassen,
wenn die Datei aus irgendeinem Grund fehlt — der Ingest läuft dann normal weiter, nur ohne Snapshot.
Dedup läuft gegen `dedup_key` (Firma+Titel+Ort) und URL — Dubletten werden übersprungen. Behalten-
Status wie „Kein Match“ und (seit Phase 41) „Beirat abgelehnt“ sind Tombstones fürs Dedup: dieselbe
Anzeige (gleicher Link) taucht nie wieder als „Neu“ auf. Seit P2-36: eine NEUE Anzeige derselben Stelle
(Firma+Titel, Gender-Zusatz egal) im Endstatus erscheint als „Neu“ mit Hinweis `NEUAUSSCHREIBUNG?` —
Dubletten laufender Stellen und Papierkorb-Treffer werden weiter übersprungen.
Der Lauf wird in der Tabelle `run` protokolliert.

**Auch bei 0 verifizierten Treffern** einen Ingest mit LEERER Liste fahren (Phase 23), damit JEDER
Suchlauf in der Run-Historie erscheint — sonst ist ein ergebnisloser Lauf unsichtbar:
```sh
echo "[]" > data/tmp/jobsuche_leer.json
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.ingest ../data/tmp/jobsuche_leer.json "WebSearch"
```
Der Run wird dann mit „0 neu … (von 0)" protokolliert.

### 6. Bericht
`X gefunden → Y bestätigt / Z korrigiert / W Quelle-vertraut / V abgelehnt` (Abgelehnte mit Grund
NICHT verschweigen — der Nutzer sieht, was aussortiert wurde), plus `U unverifiziert` vom Gate falls > 0
und Dubletten. Zusätzlich (seit Phase 44) falls im Ingest-Summary `dubletten_verdacht > 0`:
„N mögliche Dubletten (Text-Ähnlichkeit) → Review" — das sind KEINE exakten dedup_key/URL-Treffer
(die werden ohnehin übersprungen), sondern neu angelegte Jobs mit Repost-Verdacht. Verweise auf die
**Review-Ansicht** (http://localhost:8000/review) zum Sichten. Ebenfalls seit P2-36: falls im
Ingest-Ergebnis `neuausschreibungen > 0`: „N Neuausschreibungen früher aussortierter Stellen → Review“.

## Record-Schema (ein Objekt je Stelle)
**Vor dem Ingest prüfen, ob die Firma schon existiert** — `curl -s http://localhost:8000/api/companies`
und den bestehenden Namen **wörtlich** übernehmen (z. B. „Beispiel“ statt „Beispiel GmbH“), statt eine
zweite Schreibweise anzulegen: sonst entstehen zwei Firmen-Datensätze, und Dubletten werden über die
Schreibweisen hinweg nicht erkannt (Echtfall: zwei Anzeigen derselben Stelle unter unterschiedlicher
Firmenschreibweise, 12.09.2026, s. P2-39).
```json
{
  "company": "…", "title": "…", "location": "…", "url": "…",
  "portal": "LinkedIn|Indeed|StepStone|Xing|Nejo|Firmenseite",
  "work_model": "Remote|Hybrid|Onsite", "relocation_needed": "Nein",
  "tab": "<Bucket-Schlüssel, z. B. Remote>", "plan_ab": "A|B|C",
  "seniority": "<Ebene wie in der Anzeige, z. B. Director|VP|Head|Manager|Experte|Berufseinsteiger>",
  "salary": null, "published_date": "…",
  "situation": "BUILD|SCALE-UP|POST-MERGER|PE|CARVE-OUT|RESTRUCT|RUN|UNKLAR",
  "match_score": 1, "match_rationale": "… mit Beleg …",
  "next_step": "…", "source_note": "…",
  "contact": {"name": "…", "email": "…", "role": "Recruiter", "notes": "…"}
}
```

## Grenzen
- Reiner Suchlauf. Company-Fit-Dashboard & angepasster CV kommen on demand (Phase 2, `job-deepdive`).
- Gmail-Antwort-Tracking ist separat (Phase 3, `email-check`).
