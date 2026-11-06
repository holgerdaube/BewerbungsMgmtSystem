---
name: cv-match
description: Schritt 2a nach dem Firma-Check — erzeugt für EINE Stelle das Match-Dashboard und einen angepassten CV-ENTWURF (DE, EN, FR, IT, ES oder PT), OHNE PDF und OHNE ATS-Scan. Der Entwurf landet als Absatz-Liste in der Datenbank und ist danach am Job-Detail direkt bearbeitbar; „CV erstellen" (eigener Skill/Button) macht daraus Word+PDF+ATS. Nutze diesen Skill bei "CV-Match für Job <id>", "CV-Match für diese Stelle", "Lebenslauf matchen". NICHT für die Firmen-/Fit-Prüfung (das ist Schritt 1 → firma-pruefen) und NICHT für die finale Erstellung (das ist cv-erstellen).
---

# CV-Match (Schritt 2a)

Der **zweite** Schritt der Stellen-Vorbereitung — jetzt in ZWEI Teile gesplittet (Phase 46):
dieser Skill liefert Match-Dashboard + editierbaren CV-Entwurf; `cv-erstellen` macht danach
(nach optionaler Bearbeitung durch den Nutzer) Word + PDF + ATS-Scan daraus.
**Voraussetzung:** Schritt 1 (`firma-pruefen`) ist erledigt und der Fit ist geklärt — erst dann lohnt der CV-Aufwand.

**Beirats-Votum ist Kontext, KEIN Gate (20.07.2026):** Liegt ein Beirats-Stellen-Check vor —
auch 🔴 „Nicht bewerben" — wird ein manuell angeforderter Lauf trotzdem vollständig
ausgeführt: Der Klick auf „CV-Match" ist die bewusste Überstimmung des Nutzers (Phase-40-Prinzip;
das Votum steht direkt über dem Button, er hat es gesehen). Erwähne das Votum in EINEM Satz am
Anfang des Berichts — aber stelle keine Rückfrage und stelle den Lauf nicht zurück. Headless
gibt es ohnehin keinen Rückkanal: Ein Lauf, der mit einer Frage endet, hat nichts geliefert.

**Vorhandene CV-Versionen sind Kontext, KEIN Gate (07.08.2026, Phase 78):** Existieren für
diesen Job bereits ein oder mehrere CV-Entwürfe bzw. fertige CV-Versionen, ändert das NICHTS am
Ablauf — dieser Skill baut Match-Dashboard und CV-Entwurf IMMER neu aus der aktuellen
Basis-CV-Datei (dasselbe Prinzip wie oben, Phase 40). Echtfall 07.08.2026: Nach dem v10-Umbau
der Basis-CVs erkannte ein Lauf „bereits vollständig erledigt" und
recycelte den v9-basierten Alt-Entwurf statt neu zu bauen — der anschließende ATS-Scan lief auf
der falschen Struktur. Diese „bereits erledigt"-Abkürzung ist NIE zulässig. Erwähne vorhandene
Versionen in EINEM Satz im Bericht (Schritt 3); sie sind nie ein Grund, den Lauf zu überspringen
oder Schritt 1/1b/1c/1d zu verkürzen. Lege eine NEUE CVVersion-Row an (`register_entwurf`,
Schritt 2) — die alte bleibt unangetastet.

## Ablauf

### 0. Reihenfolge prüfen
Job-ID aus dem Auslöser. Daten holen:
```sh
curl -s http://localhost:8000/api/jobs/<id>
```
Ist **kein** Company-Fit vorhanden (`company.fit_analysis_path` leer), kurz darauf hinweisen, dass zuerst
**„Firma prüfen für Job <id>"** (Schritt 1) sinnvoll ist — und nur weitermachen, wenn der Nutzer den Fit bestätigt.

### 1. CV-Match + Anpassung (Skill `cv-job-match`)
**Arbeitskopie IMMER frisch aus der Basis-Datei erzeugen** (Phase 78), vom Projekt-Root aus (per
venv-Python, weil `cp` headless nicht freigegeben ist):
```sh
~/.bewerbung_mgmt_venv/bin/python -c "import pathlib, shutil; z = pathlib.Path('data/cv_basis/entwuerfe'); z.mkdir(parents=True, exist_ok=True); shutil.copy('data/cv_basis/base_<lang>.docx', z / '<arbeitsname>.docx')"
```
`<lang>` ist das Kürzel der Basis-CV-Fassung nach der Sprachwahl aus `cv-job-match` (Abschnitt Sprachregeln): die
Sprache der Anzeige (`de`, `en`, `fr`, `it`, `es`, `pt`, bei gemischten Anzeigen die dominante Sprache des
Fließtexts). Fehlt bei einer französischen, italienischen, spanischen oder portugiesischen Anzeige die Fassung
dieser Sprache: nichts übersetzen, zuerst `base_en.docx` nehmen, falls vorhanden, sonst `base_de.docx`, und den
Sprachbruch in der Meldung nennen.
NIE eine bestehende tailored-/Entwurfs-docx (auch nicht die eigene aus einem
früheren Lauf für denselben Job) als Ausgangspunkt nehmen. Grund: Nur die frische Kopie garantiert,
dass der Entwurf auf der AKTUELLEN Basis-Struktur steht (s. „Vorhandene CV-Versionen sind Kontext,
KEIN Gate" oben). **Ablage nur in `data/cv_basis/entwuerfe/`** (P2-54): Die Oberfläche öffnet
Dateien nur aus freigegebenen Ordnern (`_ARTEFAKT_ORDNER` in `backend/app/main.py`), ein Entwurf
anderswo liefert bei „Word öffnen" 403.
Rufe — sobald die Stellenbeschreibung vorliegt (nächster Absatz) — den **Projekt-Skill `cv-job-match`** auf
(Skill-Werkzeug, `skill: cv-job-match`, ohne Namensraum; er liegt unter `.claude/skills/cv-job-match/`). Er holt
die Anzeige nicht selbst und stellt in diesem Lauf keine Rückfragen (kein Rückkanal). Übergib ihm: die frische
Arbeitskopie (Pfad in `data/cv_basis/entwuerfe/`), die zur **Stellensprache** passende Basis-CV-Datei als
Referenz für seine Audits (`data/cv_basis/base_<sprache>.docx`, dieselbe Fassung wie die Arbeitskopie — alle `_ATS`-Varianten →
nur Text einbauen, keine Strukturänderung; seit Phase 76 „v9 ATS": je Station steht der TITEL VOR der
„Firma\tZeitraum"-Zeile — Workday-Parser-Fix, diese Reihenfolge NIE zurückdrehen), den Anzeigentext samt
Quellenlage und das Keyword-Protokoll aus 1d (15 Begriffe, VOR dem Aufruf aufgestellt: die einzige Keyword-Liste,
mit der er arbeitet). Er liefert Match-Score, Befunde, die bearbeitete Arbeitskopie und das Änderungsprotokoll
zurück; Match-Dashboard (1b bis 1d) und Registrierung (Schritt 2) bleiben hier. **Sein Bericht beendet den Lauf nicht:
Mache sofort hier weiter, ohne Abschlussmeldung. Fehlen Dashboard oder Registrierung, gilt der Lauf als fehlgeschlagen.**
**Stellenbeschreibung beschaffen (in dieser Reihenfolge):**
1. **Anzeigentext aus dem Snapshot lesen** (`job.posting_snapshot_path` aus den Schritt-0-Daten, Karte
   „Anzeigentext …" oder Block „Volltext (unbereinigt)"). Der Server hat den Text beim Start dieses Laufs
   schon nachgeholt, falls er fehlte. Das ist die **Primärquelle**.
2. Fehlt der Text im Snapshot: **einmal**
   ```sh
   cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.posting_snapshot nachholen --job-id <id>
   ```
   Exit 0 → Snapshot neu lesen → Primärquelle. Exit 0 heißt immer: Der Originaltext steht jetzt im
   Snapshot, auch wenn die Ausgabe `"befund": "ABGELAUFEN"` meldet (Portal geschlossen, Anzeige noch
   sichtbar). Den Snapshot deshalb neu lesen, BEVOR du andere Quellen suchst.
3. Exit 3 (Anzeige nicht abrufbar) → **Sekundärquellen**: die gespeicherte Rolleninfo (`match_rationale`,
   `raw_json`), `source_note`, **ein** WebSearch-Versuch nach der kanonischen Anzeige und WebFetch auf
   `job.url` (liefert oft nur eine Zusammenfassung statt des Wortlauts). Was gefunden wird, ist eine
   **Teilquelle** — transparent machen.

**Liegt danach kein Anzeigentext vor** (der Lauf wurde dann bewusst bestätigt): Das Match-Dashboard
bekommt in der Tabelle aus 1b eine Red-Flag-Zeile `Anzeigentext lag nicht vor, das Match beruht auf
Titel und Firma` (Markup-Muster dort; Erfüllungs-Badge `badge neg` mit „–", Zeile zählt nicht in den
gewichteten Score), und der Abschlussbericht (Schritt 3) sagt es in einem Satz.

Wahrheitstreue strikt: keine erfundenen Skills/Zahlen; nicht gedeckte Keywords ehrlich benennen.
Zusätzlich **`config/profil_struktur.md`** heranziehen (strukturierte Kandidaten-Substanz —
ergänzt profil.md; Positionierung/Skills/Werdegang/Zertifikate aus der Profil-Seite, Phase 45).
**Kein ATS-Scan hier** (der ist Teil von `cv-erstellen`, läuft NACH einer möglichen Bearbeitung).

**Portal geschlossen?** Gilt nur, wenn Schritt 1 eine Live-Seite geladen hat (WebFetch als Teilquelle).
Kommt die Anzeige aus dem Snapshot, prüft `firma-pruefen` den Portal-Status, hier entfällt die Prüfung.
Marker wie „No longer accepting applications"/„position has been filled"/
Redirect auf die Portal-Übersicht → `PATCH /api/jobs/<id>` `{"portal_closed": 1}` → Karriereseite
ermitteln (`career_url` → Zielfirmen-Cache `GET /api/target-companies` → WebSearch) und Stelle dort
suchen → Fund: `career_url` PATCHen + JobLog; kein Fund: Übersichtsseite als `career_url` + JobLog +
Empfehlung „Nicht verfügbar" statt Status-Automatik (Details/Badge: `firma-pruefen` Schritt 3b).

### 1b. Gewichtetes Anforderungs-Matching (Pflichtteil des Match-Dashboards)
Nicht nur ein Gesamt-Score — **jede Anforderung einzeln** (Methode aus dem Community-Backlog):
1. Alle Anforderungen aus der Anzeige extrahieren (auch implizite: Sprache, Reisen, Standort).
2. Je Anforderung **Gewicht** vergeben: Muss = 3 · Soll = 2 · Kann = 1 (aus Formulierung/Position in der Anzeige).
3. Je Anforderung **Erfüllung 1–10** bewerten — mit konkretem CV-Beleg (Zitat/Station) oder ehrlichem „kein Beleg".
4. Gewichteter Score = Σ(Gewicht × Erfüllung) / Σ(Gewicht × 10) → als Prozent im Dashboard ausweisen,
   zusätzlich zum cv-job-match-Score. Muss-Anforderungen mit Erfüllung ≤ 4 sind **Red Flags** (prominent zeigen).
Die Tabelle (Anforderung · Gewicht · Erfüllung · Beleg) gehört ins Match-Dashboard-HTML — sie ist die
Argumentationsbasis fürs Anschreiben und die ehrliche Bewerben/Nicht-bewerben-Entscheidung.

**⚠️ Verbindliches Markup — GENAU dieses Muster, nicht improvisieren** (Drift-Fall 28./29.07.2026:
zwei Läufe steckten „Muss · 3" in das 26-px-Symbol-Badge `.badge` — Text brach um und wurde
abgeschnitten; `report_check` kann Zweckentfremdung einer existierenden Klasse NICHT erkennen):
```html
<h2 class="sec">Gewichtetes Anforderungs-Matching</h2>
<table class="score">
  <thead><tr><th>Anforderung</th><th>Gewicht</th><th>Erfüllung</th><th>Beleg / Begründung</th></tr></thead>
  <tbody>
    <tr>
      <td class="factor">Mehrjährige Delivery-Verantwortung</td>
      <td>Muss (3)</td>
      <td><span class="badge pos">9</span></td>
      <td>Beleg mit Zitat/Station aus dem CV.</td>
    </tr>
    <tr class="redflag">
      <td class="factor">Anforderung mit Muss-Gewicht und Erfüllung ≤ 4</td>
      <td>Muss (3)</td>
      <td><span class="badge neg">3</span></td>
      <td><b>Red Flag:</b> ehrliche Begründung, kein Schönreden.</td>
    </tr>
  </tbody>
</table>
```
Eiserne Regeln: **Gewicht IMMER als Klartext `Muss (3)` / `Soll (2)` / `Kann (1)`** — NIE in
ein Badge/eine Pille (die `.badge`-Klasse ist ein 26-px-Quadrat für EIN Zeichen bzw. eine
Zahl). **Spaltenreihenfolge wie im Muster oben: Spalte 2 = Gewicht-KLARTEXT, Spalte 3 =
Erfüllungs-BADGE — niemals vertauschen** (Drift-Fall 24.–27.07.2026: 4 Läufe hatten
Kopf und Inhalt der beiden Spalten verdreht). **Erfüllung = einzelne Zahl 1–10 im
`badge pos/neu/neg`** mit EXAKT diesen Schwellen:

| Erfüllung | Badge-Klasse |
|---|---|
| **7–10** | `badge pos` (grün) |
| **5–6** | `badge neu` (grau) |
| **1–4** | `badge neg` (rot) |

**Häufigster Bestandsfehler (14 Läufe bis 09.08.2026): die 7 wurde als `neu` eingestuft — falsch.
Die 7 ist die UNTERSTE `pos`-Stufe, `neu` endet bei 6.**
Red-Flag-Zeilen über `class="redflag"` am `<tr>` (die Regel dazu setzt `bericht_stil einsetzen`
ein, s. „Pflichtschritt vor dem Fertigstellen“ unten — nichts davon abschreiben).

### 1c. Vorher/Nachher-Gegenüberstellung (Pflichtteil des Match-Dashboards)
**Während** der Bullet-Anpassung protokollieren, nicht hinterher aus der fertigen `.docx`
rekonstruieren: zu jeder geänderten Zeile das Paar (Original-Zitat, neues Zitat, eingebaute
Keywords, XYZ-Umbau ja/nein) sofort notieren. (`cv-job-match` führt dieses Protokoll in seinem Schritt 5 und
gibt es zurück; hier wird es gegen die gespeicherte `.docx` geprüft und ins Dashboard gesetzt.)

**Wahrheits-Regeln (eisern):**
- VORHER = wörtliches Zitat aus dem Basis-CV, NACHHER = wörtliches Zitat aus der tatsächlich
  erzeugten `.docx`. Keine Paraphrase, keine Zahl, die nicht in einer der beiden Fassungen steht.
- NUR tatsächlich geänderte Bullets zeigen; unveränderte Stationen weglassen (optional eine
  Sammelzeile „unverändert: <Stationen>" am Ende).
- Markiert (`<mark>`) wird NUR, was wörtlich als Keyword aus der Stellenanzeige stammt und neu
  eingebaut wurde — nie Bestandstext. Die Markierung existiert AUSSCHLIESSLICH im Dashboard, nie in
  der `.docx` (dort normale Textstärke, Grundprinzip 6 von `cv-job-match`).
- Versions-Label aus dem Basis-CV ableiten (Dateiname/Kommentar/config/profil.md prüfen —
  z. B. „v9 ATS" → „VORHER · V9" / „NACHHER · V10"). Ist die
  Version nicht feststellbar: neutral „VORHER · Basis" / „NACHHER · Angepasst" — NICHT raten.

**Aufbau der Sektion im Match-Dashboard-HTML:** Intro-Zeile → je Station eine Überschrift
`Firma — Rolle (Zeitraum)` → Kartenpaar(e) je geändertem Bullet → Chip-Zeile mit den eingebauten
Keywords bzw. `XYZ: Ergebnis zuerst`. Die Klassen dafür (`cmp`, `pair`, `before`, `after`, `lbl`,
`pills`, `pill2` und das Element `mark`) stehen als Beispiel in `assets/report_theme_bms.html`; ihre Regeln
setzt `bericht_stil einsetzen` ein (Pflichtschritt unten) — im Dashboard kein CSS und kein eigener Style-Block.
Pro Bullet-Paar:
```html
<div class="cmp">
  <h3>Firma — Rolle (Zeitraum)</h3>
  <div class="pair">
    <div class="before"><p class="lbl">Vorher · V7</p>Wörtliches Zitat aus dem Basis-CV.</div>
    <div class="after"><p class="lbl">Nachher · V8</p>Wörtliches Zitat, neue/umformulierte Stellen mit <mark>eingebautem Keyword</mark> markiert.</div>
  </div>
  <div class="pills"><span class="pill2">+ Keyword A</span><span class="pill2">XYZ: Ergebnis zuerst</span></div>
</div>
```
Intro-Zeile direkt über der ersten Station (z. B. als eigener `<p>` unter der `h2.sec`-Überschrift
„Vorher / Nachher"): „Zitate wörtlich aus dem Basis- bzw. angepassten CV. Markiert = eingebautes
Keyword (nur hier sichtbar; in der .docx normale Textstärke). Keine Zahl erfunden."

Bericht an den Nutzer (Schritt 3 unten) erwähnt die Sektion kurz, z. B. „Vorher/Nachher: 3 Bullets in
2 Stationen" — als Teil des optionalen Zusatzsatzes, keine eigene neue Zeile.

### 1d. Keyword-Protokoll (Methodik v2, Phase 55)
Aus derselben Stellenanzeige (Snapshot bzw. Teilquelle wie Schritt 1) **GENAU 15 Begriffe** extrahieren, in
fünf festen Kategorien — das ist die EINE Keyword-Liste, gegen die sowohl dieser Entwurf optimiert
als auch später in `cv-erstellen` gescannt wird (keine zweite, abweichende Extraktion im Scan):

`titel_rolle` 2 · `fachdomaene` 5 · `fuehrung_scope` 4 · `tools_methoden` 3 ·
`zertifikate_sprache` 1 — Summe immer 15. Gibt die Anzeige eine Kategorie nicht her (z. B. keine
Zertifikate genannt), wandert der Slot nach `fachdomaene` — im JSON mit `"verschoben_von"`
dokumentieren.

**Jeden Begriff klassifizieren** (die Klassifikation passiert HIER, nicht im späteren Scan neu
erfunden):
- `abdeckbar: true` — wahrheitstreu belegbar aus Basis-CV oder `config/profil_struktur.md`, mit
  `beleg` (konkrete Station/Zitat).
- `abdeckbar: false` — strukturelle Lücke, mit `grund` (ehrlich benannt, keine Erfindung).

Format (wird unverändert als `keywords_json` gespeichert, Schritt 2):
```json
{"methodik": "v2", "sprache": "de", "begriffe": [
  {"begriff": "Customer Care", "kategorie": "fachdomaene", "abdeckbar": false,
   "grund": "CV-Domäne ist PS-Delivery, kein Care-Center"},
  {"begriff": "Führung großer Teams", "kategorie": "fuehrung_scope", "abdeckbar": true,
   "beleg": "12 Direct Reports (Beispiel GmbH)"}
]}
```
Sprache: Begriffe in Anzeigensprache (DE-Anzeige → deutsche Begriffe); bei EN-CV gegen eine
DE-Anzeige (oder eine FR-, IT-, ES-, PT-Anzeige) gilt sinngleiche Übersetzung mit Beleg als abgedeckt.

Die **CV-Anpassung aus Schritt 1** optimiert den Entwurf wahrheitstreu gegen alle
`abdeckbar: true`-Begriffe dieser Liste. Das **Match-Dashboard** (Keyword-Teil) verwendet
DIESELBEN 15 Begriffe — keine zweite, abweichende Liste im Dashboard erzeugen.

**⚠️ Verbindliches Markup für den Keyword-Teil im Dashboard — GENAU dieses Muster, nicht
improvisieren** (Design-Review 10.08.2026: ohne literales Muster driftete der Abschnitt in
4-Karten-Grids, abweichende Tag-Texte und 12 Dateien mit fehlender Tag-CSS-Regel; Referenz =
ein früherer, korrekt gerenderter Lauf). Flache Chip-Liste, ein Chip je Begriff, Tag = Abdeckungsart:
```html
<h2 class="sec">Keyword-Protokoll (15 Begriffe, Methodik v2)</h2>
<div class="comp">
  <div class="chip pos"><span class="tag direkt">Titel/Rolle</span><b>Begriff aus der Anzeige</b><span>Beleg mit Station/Zitat aus dem CV.</span></div>
  <div class="chip pos"><span class="tag indirekt">Fachdomäne</span><b>Begriff</b><span>Sinngleich belegt über &lt;Station&gt; (übertragbar, nicht wortgleich).</span></div>
  <div class="chip neg"><span class="tag direkt">Tools/Methoden</span><b>Nicht gedeckter Begriff</b><span>Ehrlicher Grund der Lücke, kein Schönreden.</span></div>
</div>
```
Tag-Text = Kategorie (`Titel/Rolle` · `Fachdomäne` · `Führung/Scope` · `Tools/Methoden` ·
`Zertifikate/Sprache`); `tag direkt` = wörtlich belegt, `tag indirekt` = sinngleich/übertragbar
belegt; `chip pos` = abdeckbar, `chip neg` = Lücke. **Die Regeln für `comp`, `chip` und `tag` setzt
`bericht_stil einsetzen` aus dem zentralen CSS ein — nichts abtippen** (früher häufigster report_check-Befund
im Bestand: Die Tag-Regeln fehlten, die Kategorie-Labels waren dann farblos). Entscheidend: JEDE im Markup
benutzte Klasse stammt aus `assets/report_theme_bms.html`. Reihenfolge im
Dashboard wie in der Referenz: Keyword-Protokoll VOR der Vorher/Nachher-Sektion.

Match-Dashboard-HTML (Phase 30 — einheitlicher Report-Style): im Look von
`assets/report_theme_bms.html` erzeugen (Datei vor dem Schreiben lesen und das Muster
wörtlich übernehmen — Aufbau/Karten/Badges aus dem Template, statisches HTML, kein
`<script>const DATA=…`; den Style-Block der Vorlage NICHT abschreiben, das Dashboard entsteht ohne
eigenen Style-Block). **Kopf (Phase 35, Typ-Tabelle im Template):** eyebrow „CV-Match" →
h1 = Rolle → sub „Firma · Job &lt;id&gt;" → Meta-Grid „Match gewichtet · cv-job-match-Score ·
CV-Sprache · Datum" (Ampel-Werte als `<span class="dot amber"></span>Gelb · …`, nicht als große
Gauge). Dateiname über den zentralen Helfer:
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -c "from app.naming import report_filename; print(report_filename('Match', '<Firma>', '<Position>'))"
# → JJJJMMTT_Match_<Firma>_<Position>  (ohne Extension; .html anhängen)
```
Speichern unter `data/company_fit/<Match-Name>.html`.

**Pflichtschritt vor dem Fertigstellen** (gleiche Regel wie in `cv-erstellen` — erst den Stil
einsetzen, dann deterministisch und kostenlos prüfen):
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.bericht_stil einsetzen "../data/company_fit/<Match-Name>.html" && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.report_check "../data/company_fit/<Match-Name>.html"
```
Meldet einer der beiden Befehle eine benutzte Klasse ohne Regel: die Klasse durch eine aus
`assets/report_theme_bms.html` ersetzen (kein eigenes CSS) und beide Befehle wiederholen.

### 2. Registrieren (als ENTWURF — kein Umbenennen, kein PDF)
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.deepdive entwurf <entwurf.json>
```
`entwurf.json` mit `job_id` und `cv` (`language` großgeschrieben: `DE`, `EN`, `FR`, `IT`, `ES` oder `PT`, die Sprache der
benutzten Fassung, `kind:"tailored"`, `file_path` — **Arbeitsname
egal**, der Ordner nicht, z. B. `data/cv_basis/entwuerfe/2026_CV_<Name>_v8_<LANG>_<slug>.docx`, wird NICHT umbenannt in diesem
Schritt —, `match_score100`, `match_dashboard_path`, **`keywords_json`** — das komplette Dict aus
Schritt 1d, EINE Liste für Match-Dashboard und späteren ATS-Scan). `register_entwurf()` extrahiert
die `.docx` selbst als Absatz-Liste (`entwurf_text`), speichert `keywords_json` unverändert als
JSON-String an der Row und legt eine `CVVersion` mit `status=entwurf` an — die Rückgabe enthält
`cv_version_id` und `absaetze` (Anzahl editierbarer Absätze).

**Kein PDF, kein ATS-Scan, keine Namenskonvention hier** — alles drei passiert erst bei
„CV erstellen" (eigener Skill `cv-erstellen`, vom Nutzer über die UI oder automatisch als
nächster Kettenschritt ausgelöst).

### 3. Bericht (Kompakt-Format — landet 1:1 in einer schmalen UI-Karte)
**Grundregel:** „Ein erledigt reicht." Alles Ausführliche (Red Flags, gewichtete Tabelle) steht im
Match-Dashboard, NICHT in der Meldung. KEINE Markdown-Überschriften, keine Aufräum-/Temp-Datei-Hinweise
(die gehören ins Log). Genau dieses Format:
- **Zeile 1 = das ALLERERSTE Zeichen der Meldung, KEINE Vorrede davor** (kein „Registrierung erfolgreich"/
  „Fertig" o. Ä.): `CV-Match — <n>/100 · <Sprache> · Entwurf bereit`
- optional **EIN** Satz zur Quellenlage/Besonderheit (z. B. „Anzeige nur über Zweitquelle rekonstruiert");
  **Pflicht, wenn kein Anzeigentext vorlag** (Schritt 1): „Anzeigentext lag nicht vor, das Match beruht
  auf Titel und Firma." — deckt bei Bedarf auch die Vorher/Nachher-Sektion knapp ab (z. B. „Vorher/Nachher: 3 Bullets in
  2 Stationen"), keine eigene zusätzliche Zeile dafür.
- **Schlusszeile:** Hinweis, dass der Entwurf jetzt unter „Dateien & Dokumente" bearbeitbar ist und
  „CV erstellen" Word+PDF+ATS daraus macht, sobald der Nutzer fertig ist (oder direkt, ohne Bearbeitung).

Das Match-Dashboard verlinkt die Web-App selbst unter der Meldung — nicht in den Text schreiben.

## Abgrenzung
- **Schritt 1 = `firma-pruefen`** (Geschäftsmodell/Markt/Rolleneinfluss). **Schritt 2a = dieser Skill** (Match+Entwurf).
  **Schritt 2b = `cv-erstellen`** (Word+PDF+ATS aus dem — ggf. bearbeiteten — Entwurf).
- `job-deepdive` macht Firma+CV in einem Rutsch über den FRÜHEREN, ungesplitteten Weg (bewusst
  unverändert, s. `pipeline.deepdive.register()`) — nutze es nur, wenn du explizit KEINEN
  Editier-Checkpoint willst.
