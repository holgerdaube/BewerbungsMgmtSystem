# Bewertungsraster (Zielstellen-Fit 1–5)

Formalisiert aus dem „Anleitung"-Tab des Alt-Trackers. Dieses Raster gilt für die
automatische Bewertung neuer Stellen in der Jobsuche-Pipeline (Phase 1).

**Nicht verwechseln** (Namensschärfung 13.08.2026): Der **Zielstellen-Fit (1–5)** bewertet die
**Stelle gegen das Zielprofil** — Situation, Funktion, Region. Der **CV-Match-Score (0–100)** aus
`cv-match` bewertet etwas ganz anderes, nämlich das **Dokument gegen die Anzeige**. Feld- und
API-Namen (`match_score`, `match_rationale`, Marker `LOW_MATCH`) blieben unverändert.

## Zielstellen-Fit
| Score | Bedeutung |
|-------|-----------|
| **5** | Situation **und** Funktion **und** Region passen vollständig. |
| **4** | Zwei der drei Dimensionen passen stark, die dritte akzeptabel. |
| **3** | Grundsätzlich passend, aber mit klarem Abstrich (Ebene, Region, Scope). |
| **2** | Randtreffer, nur eine Dimension passt. |
| **1** | Kaum Fit, dokumentieren warum. |

Begründung immer kurz in `match_rationale` festhalten — mit Beleg (Zitat/Quelle), nicht nur Behauptung.

## Dimension 1 — Situation (wichtigster Filter)
| Code | Beschreibung | Priorität |
|------|--------------|-----------|
| **BUILD** | Organisation wird neu aufgebaut | Plan-A-Kern |
| **CARVE-OUT** | Herauslösung aus Konzern, eigene Struktur entsteht | Plan-A-Kern |
| **POST-MERGER** | Integration nach Fusion/Übernahme | Plan-A-Kern |
| **PE** | PE-finanziert, Professionalisierungsphase | Plan-A-Kern |
| **SCALE-UP** | Wachstum, die Organisation der Zielfunktion entsteht | Plan-A-Kern |
| **RESTRUCT** | Umbau/Restrukturierung | prüfen: Rebuild oder Abbau? |
| **RUN** | Eingeschwungene, reife Orga | niedrige Priorität |
| **UNKLAR** | Signal nicht erkennbar | recherchieren |

## Dimension 2 — Funktion / Plan A vs. B vs. C
- **Plan A** = die Hauptzielrolle laut Plan A (Titel in `titel`, Ebenen in `senioritaet` des
  Plans). Es zählt die Verantwortung der Rolle, nicht der Titel: bei Leitungsrollen die Führung
  eines Teams oder einer Organisation der Zielfunktion. Nennt `senioritaet` Manager oder Senior
  Manager, ist eine Manager-Rolle mit Teamführung Plan A, nicht Plan C.
- **Plan B** = die zweite Zielfunktion laut Plan B (`titel`) — **nur wenn die Situation stimmt**.
- **Plan C** = Auffang-Plan unterhalb der Leitungsebene aus A/B: Rollen aus dem Umfeld der
  Zielfunktion, die einzelne Kunden oder Verträge verantworten statt eine Organisation (z. B.
  Service Delivery Manager).
- Konkrete Titel, Ebenen (`senioritaet`) und Branchen je Plan sind KEINE festen Zeilen hier,
  sondern werden auf `/einstellungen` gepflegt (Quelle der Wahrheit:
  `config/suchprofile.yaml::plaene`, Phase 49) — bei Zweifel dort nachsehen, nicht raten.
- Priorität A → B → C (`prioritaet`-Feld je Plan in `plaene`). Regel: **B in BUILD/CARVE-OUT
  schlägt A in RUN.** Plan C wird nur durchsucht/gewertet, wenn er in den Einstellungen
  `aktiv: true` ist, und zählt bei sonst gleicher Situation niedriger als A/B.

## Dimension 3 — Region (harte Grenze)
- **Kein Umzug, kein dauerhafter Zweitwohnsitz.**
- Onsite-Rollen zählen **nur** im Umkreis-Bucket-Tab (der Eintrag unter `buckets` in
  `config/suchprofile.yaml`, dessen Schlüssel weder „Remote" noch „Deutschlandweit" ist —
  Format „<Stadt> +<km>km").
- In „Remote" und „Deutschlandweit" ist `Umzug nötig = Ja` ein **K.o.**
- **Was als Umzug zählt:** reine Präsenz (Onsite ohne Homeoffice-Anteil) an einem Ort außerhalb
  des Umkreises, oder eine Anzeige, die den Umzug ausdrücklich verlangt. Sonst nichts — ein
  Ortsname allein belegt weder Präsenz noch Umzug.
- **Hybrid außerhalb des Umkreises ist kein Umzug.** Liegt der Ort in Deutschland, gehört die
  Stelle in den Bucket „Deutschlandweit“ (`tab`), mit `relocation_needed: "Nein"` und einem
  Abstrich bei der Region im Score (Pendeln an den Präsenztagen). Ist „Deutschlandweit“ nicht
  aktiv oder liegt der Ort im Ausland, gehört sie in keinen Bucket und fällt raus.
- **Arbeitsmodell nicht erkennbar:** wie Hybrid behandeln, `work_model: "Unklar"`, und im
  `source_note` vermerken, dass das Arbeitsmodell in der Anzeige nicht steht.

## Harte Grenzen und Score — was aussortiert und was bewertet wird
Gilt für alle Suchläufe (Jobsuche, Mail-Jobsuche, Zielfirmen- und Headhunter-Sweep). Die Grenzen
selbst stehen in `config/suchprofile.yaml` (`ausschluss_titel`, `ausschluss_bedingungen`,
`skill_gaps_pruefen`, `min_mitarbeiter`, `max_alter_tage`) und oben unter Dimension 3. Hier steht,
wie sie angewendet werden.

- **Eine harte Grenze greift nur mit Beleg.** Beleg ist eine wörtliche Angabe aus der Anzeige,
  der Mail oder dem Suchergebnis (Titel, Arbeitsmodell, Anforderung, Firmengröße). Eine Annahme
  ist kein Beleg: nicht „vermutlich unter 100 Mitarbeiter“, nicht „klingt nach Vertrieb“, nicht
  „anderer Ort, also Umzug“.
- **Reicht die Mail oder das Suchergebnis für einen Beleg nicht, die Anzeige laden.** Ist sie
  nicht abrufbar (Login-Wall, Fehler), gilt die Grenze als nicht belegt: Die Stelle bleibt drin,
  wird konservativ bewertet und bekommt den Hinweis im `source_note`.
- **Lässt sich eine Region oder Grenze nicht sicher prüfen** (Ortsname unbekannt, Entfernung unklar),
  ist das kein Abbruchgrund: Sie gilt als nicht belegt, die Stelle bleibt mit Hinweis im `source_note`,
  und der Abschlussbericht nennt den Fall.
- **Der Score sortiert, er sortiert nicht aus.** Was ein Suchlauf als Kandidaten aufgenommen hat
  (Treffer der Titelsuche, Posting aus einer Alert-Mail) und was die harten Grenzen besteht, wird
  mit seinem Score angelegt, auch mit 1 oder 2. Funktion, Branche oder Situation passen nicht:
  Das ist ein niedriger Score mit Begründung, kein Grund zum Weglassen — es sei denn, eine
  ausdrückliche Ausschlussregel trifft belegt zu (eine Regel aus `ausschluss_titel` oder
  `ausschluss_bedingungen`, zum Beispiel reine Vertriebsrolle). Gesichtet wird in der
  Review-Ansicht; dort ist ein niedriger Score eine Sortierhilfe.
- **Im Abschlussbericht steht je aussortierter Stelle die Grenze und der Beleg.** „Passt nicht“
  ohne Grenze und Beleg ist kein zulässiger Ausschlussgrund.

## Layoff zweischneidig (Restructuring Radar)
Stellenabbau heißt zweierlei — in `rebuild_or_cut` einschätzen:
- **Gut (Rebuild):** Firma baut um und sucht jemanden zum Neuaufstellen.
- **Schlecht (Abbau):** Firma entkernt den Bereich der Zielfunktion, kein Budget für die Rolle.
