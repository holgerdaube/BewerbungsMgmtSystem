# Automatik — Stand nach Phase 82 (12.08.2026)

Der „Tageslauf" (Jobsuche → Mail-Jobsuche → Zielfirmen-Sweep → Headhunter-Suche → Beworben-Check →
Postfach-Check → Absagen-Analyse (einmal je Woche) → Ansichten-Refresh → Coach-Site) läuft **auf
Knopfdruck**, nicht zeitgesteuert.
Das ist eine bewusste Entscheidung, keine offene Baustelle. Dieses Dokument sagt, was gilt und warum.

## Wie es heute läuft

**Die App startet die Skills selbst.** Der Agent-Runner (`backend/app/agent_runner.py`) spawnt pro Task
einen headless `claude -p`-Prozess mit den bestehenden Skills (rein lokale Schritte wie
`views-refresh`/`coach-site` brauchen nicht mal ein Sprachmodell, s. u.). 24 Task-Arten laufen so
headless (`PROMPTS`), dazu 3 Ketten (`RECIPES`: `deepdive`, `bewerbungspaket`, `tageslauf`) — die
meisten zusätzlich mit eigenem Button irgendwo in der App (Review, Job-Detail, Einstellungen,
Inbox, Follow-ups). Kein Copy-Paste in eine Claude-Session mehr NÖTIG — der klassische Weg
(Auslöser-Satz tippen, `docs/ANLEITUNG.md` Abschnitt 2) funktioniert bei jedem Skill weiterhin als
Alternative, oft direkt neben dem Button aufklappbar.

**Der ☀️-Tageslauf-Button** (Seitenleiste, auf jeder Seite erreichbar) startet die neunstufige Kette
`jobsuche → mail-jobsuche → zielfirmen-sweep → headhunter-suche → beworben-check → email-check →
absagen-analyse → views-refresh → coach-site` direkt in der App, headless im Hintergrund.
`views-refresh` (Excel + Digest) und `coach-site` (deterministischer Export + SFTP-Mirror, Phase 81)
brauchen kein Sprachmodell und kosten daher nichts; `coach-site` ist als letztes Glied bewusst
non-fatal (s. „Guardrails" unten). `absagen-analyse` (P2-79) läuft nur einmal je Kalenderwoche: Der
Runner fragt vor dem Modellstart `pipeline.absagen_bericht.faellig()` (PROMPTS-Schlüssel
`in_kette_nur_wenn`) und schließt den Schritt sonst ohne Kosten als „Übersprungen: …“ ab. Ein Start
von Hand (Dashboard) prüft das nie.

## Was NICHT headless läuft (und warum)

- `angebot-vergleich` — braucht Rückfragen zu den Konditionen. Headless würde der Lauf raten.
- `outreach-drive-upload` — Google-Drive-Upload ist nicht automatisierbar (`create_file` verlangt
  base64 inline, ~100 KB sprengen das Tool-Arg-Limit). Datei aus der App generieren, manuell hochladen.
- Der **Beirat** (`beirat-stellen-check`, `beirat-debatte`) läuft über eine eigene Engine live im
  Server (Server-Sent Events, Chat-artiges Live-Erlebnis) — nicht über diesen Runner. Beide Kinds
  stehen in `PROMPTS` nur zur Label-Auflistung/Fehlermeldung; ein „Erneut" im Task-Center scheitert
  dort absichtlich mit erklärendem Fehler statt `claude -p` für etwas zu starten, das der Runner gar
  nicht ausführen kann.

**Headless, aber bewusst nicht Teil des Tageslaufs:**
- `jobsuche-apify` ist **opt-in**: Apify kostet echtes Geld (der Free Plan umfasst rund 5 $/Monat), und die
  Actors rechnen pro Ergebnis ab (`kostet_geld`-Marke → eigener Budget-Guard vor dem Start). Der normale
  `jobsuche`-Lauf (WebSearch) kostet keine Apify-Credits und läuft im Tageslauf; Apify startet man
  einzeln über den zweiten Button in Review.

**Überholt (Stand ≤ 8.2):** Frühere Fassungen dieses Dokuments warnten, der Gmail-Connector funktioniere
headless „möglicherweise nicht". Das stimmte — und ist seit 8.3 gelöst: Gmail läuft über den lokalen
`pipeline/gmail_client.py` mit eigenem OAuth, nicht über den claude.ai-Connector. Verifiziert am 10.07.:
ein `claude -p`-Lauf sieht **null MCP-Tools**.

## Guardrails

| Grenze | Default | Konfigurierbar über |
|---|---|---|
| Notbremse je Lauf (bricht einen laufenden Prozess ab) | $15 | Env `AGENT_MAX_BUDGET_USD` |
| Tagesbudget (neue Läufe) | $100 | App → 💶 Budget → „Claude (Agent-Läufe)"; Env `AGENT_DAILY_BUDGET_USD` nur Fallback, falls die DB-Zeile fehlt |
| Läufe pro Tag | 100 | dito (`max_runs_per_day`); Env `AGENT_MAX_TASKS_PER_DAY` nur Fallback |
| Monatsbudget | kein Limit (Default) | dito, optional |
| Parallele Läufe | 2 | Env `AGENT_MAX_PARALLEL` |
| Task-Logs aufbewahren | 30 Tage | Env `AGENT_LOG_RETENTION_DAYS` |
| Zwischendateien in `data/tmp/` aufbewahren (P2-53; Dateien mit DB-Verweis bleiben immer) | 30 Tage, dieselbe Frist | Env `AGENT_LOG_RETENTION_DAYS` |

Tagesbudget/Läufe-Limit/Monatsbudget sitzen NICHT mehr fest im Code, sondern in einer
Datenbank-Zeile (`BudgetLimit`, provider `claude-runs`) — sichtbar und änderbar auf der Budget-Seite
als Dienst „Claude (Agent-Läufe)". Zwei Stellschrauben dort wirken auf ALLE drei Zahlen gleichzeitig:
- **„Dienst aktiv"** abwählen = Not-Aus — blockt Läufe immer, unabhängig von hart/weich.
- **hart/weich** — Default ist **weich** (ausdrücklicher Wunsch des Autors, 11.07.2026): Tagesbudget,
  Läufe-Limit und Monatsbudget warnen dann nur (`warnung` in `GET /api/agent-status`), blockieren
  aber nichts. Erst „hart" lässt die 409-Ablehnung tatsächlich greifen. Die $15-Notbremse je Lauf
  ist davon unabhängig und immer scharf.
- Der Tag beginnt um **lokale Mitternacht** (nicht UTC — `AgentTask.created_at` ist UTC, das wird
  umgerechnet).
- **Laufende Läufe werden nie abgeschossen** — die Guards blocken nur NEUE Starts.

**Doppellauf-Sperre je Stelle** (`main.py::_guard_doppellauf`): Für dieselbe `job_id` darf dieselbe
Task-Art — bzw. bei Ketten: keiner ihrer Schritte — nicht zweimal gleichzeitig laufen; ein zweiter
Start bekommt **HTTP 409** mit der Id des bereits laufenden Tasks. Job-unabhängige Läufe (Jobsuche,
Sweeps, Beworben-Check, Tageslauf, …) sind genauso betroffen wie job-gebundene.

**Zielstellen-Fit-≤2-Rückfrage** (`main.py::_guard_low_match`, 27.07.2026): Unterlagen-Läufe (`firma-pruefen`,
`cv-match`, `cv-erstellen`, `anschreiben-erstellen`, sowie die Ketten `deepdive`/`bewerbungspaket`)
auf eine Stelle mit Zielstellen-Fit ≤ 2 bekommen ohne Weiteres **HTTP 409** mit Marker `LOW_MATCH` statt
zu starten. Die App zeigt das inline als Rückfrage „Bist du dir wirklich sicher?"; „Ja, trotzdem
starten" wiederholt denselben Start mit `params.low_match_ok=true`. Unbewertete Stellen (ohne
Zielstellen-Fit) sind nicht betroffen.

**Die Absagen-Analyse kostet den Tag nichts, wenn sie scheitert** (P2-79): Ein endgültig
gescheiterter Kettenschritt bricht sonst alle Nachfolger ab (`_release_dependents`). Für
`absagen-analyse` ist `kette_weiter_bei_fehler` gesetzt — scheitert sie (auch per Timeout), laufen
`views-refresh` und `coach-site` trotzdem; ein Abbruch durch den Nutzer bricht die Kette weiter ab.
Gilt auch nach einem Server-Neustart (`start_workers`). Der ☀️-Knopf zeigt den Status des letzten
Glieds (`coach-site`); ein gescheiterter Analyse-Schritt ist deshalb nur im Task-Center zu sehen.

**Coach-Site macht den Tageslauf nie rot:** Ohne vollständige Konfiguration oder bei abgeschaltetem
Schalter endet der letzte Kettenschritt grün (nur lokaler Export, Exit 0) — solange die Coach-Site
nicht eingerichtet ist, bleibt der Tageslauf komplett grün. Ein echter SFTP-Fehler NACH Einrichtung
markiert nur den `coach-site`-Task als `failed`; alle vorigen Schritte bleiben unberührt (letztes
Glied der Kette, s. `docs/COACH_SITE.md`).

**Retry:** Ein fehlgeschlagener Lauf wird genau einmal wiederholt — aber nur bei Task-Arten, die
nichts duplizieren: `firma-pruefen`, `absagen-analyse`, `skills-sortieren`, `email-check`,
`jobsuche`, `mail-jobsuche`, `zielfirmen-sweep`, `headhunter-suche`, `beworben-check` sowie die drei
lokalen, kostenlosen Schritte `views-refresh`, `cover-letter-render`, `coach-site`. Alles, was
Zeilen, Dateien oder **Gmail-Entwürfe** anlegt (u. a. `cv-match`, `anschreiben-erstellen`,
`nachfass-mail`, `gespraech-debrief`, `mail-antwort`), wird nie automatisch wiederholt. Timeout,
Budget-Notbremse und Nutzer-Abbruch lösen ebenfalls keinen Retry aus.

Der aktuelle Stand steht im **Task-Center** (`/tasks`) und unter `GET /api/agent-status`.

## Zeitsteuerung — bewusst nicht gebaut

**Entscheidung (10.07.2026): Der Tageslauf bleibt manuell.** Gilt unverändert fort — Stand
12.08.2026 enthält `automation/` weiterhin nur das (inaktive) Refresh-only-Template von damals, kein
neuer Scheduler ist dazugekommen. Wer das später ändern will, sollte die beiden Wege und ihre Kosten
kennen:

**Seit P2-52 gibt es genau EINEN Takt dieser Art im Backend** (`app/sicherung.py::starten()`,
asyncio-Task im laufenden Server-Prozess, Muster (a) unten) — bewusst eng auf die tägliche
Datenbank-Sicherung begrenzt, keine Blaupause für den Tageslauf. Die Kostenabwägung unten
(Bedingung „App läuft", Nachholen verpasster Läufe) blieb bei der Entscheidung gegen einen
ausgeweiteten Scheduler ausschlaggebend: Ein verpasster Sicherungslauf ist folgenlos (der nächste
30-Minuten-Takt holt ihn nach, sobald die App wieder läuft), ein verpasster Tageslauf mit
Jobsuche/Mail-Check wäre es nicht.

**a) Scheduler im Backend** (asyncio-Loop im laufenden FastAPI-Prozess). Einfach, kein
Festplattenzugriff-Grant nötig, ~60 Zeilen. Bedingung: die App läuft (`start.command` offen). Ist sie
aus, feuert nichts — auf einem Laptop müsste man verpasste Läufe nachholen, was eine eigene Semantik
braucht (welcher Lauf gilt als „heute schon erledigt"?).

**b) launchd.** Läuft auch ohne offene App, kostet dafür:
- launchd kann **iCloud Drive nicht lesen** ohne manuellen „Vollständiger Festplattenzugriff"-Grant.
  Das betrifft jedes Projekt, das in iCloud liegt.
- Der Mac muss wach **und** entsperrt sein.
- Ein zweiter, schwer testbarer Startpfad neben `start.command`.

Das vorhandene Template `automation/com.bms.tageslauf.plist.template` startet **nicht**
den Tageslauf, sondern nur den LLM-freien Ansichten-Refresh (`scripts/refresh_views.sh`, täglich 07:00).
Es ist **nicht aktiviert** (vor dem Laden im Template `[PFAD_ZUM_PROJEKT]` durch den absoluten
Projektpfad ersetzen). Wer nur morgens frische Excel-/Digest-Dateien will, kann es laden:

```sh
cp automation/com.bms.tageslauf.plist.template \
   ~/Library/LaunchAgents/com.bms.tageslauf.plist
launchctl load ~/Library/LaunchAgents/com.bms.tageslauf.plist
```
Deaktivieren: `launchctl unload …` · Manuell testen: `scripts/refresh_views.sh`
Auch hier gilt der iCloud/FDA-Vorbehalt — vor dem Verlassen auf den Job einmal prüfen, ob er wirklich lief.

## Unverändert: kein Auto-Bewerben

In keiner Stufe. Das System sucht, bewertet, recherchiert und bereitet vor. Mails bleiben **Entwürfe**
(`gmail_client` kennt keinen Sende-Befehl). Status-Entscheidungen und der Versand bleiben beim Nutzer.
