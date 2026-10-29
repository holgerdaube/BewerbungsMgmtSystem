---
name: cv-erstellen
description: Schritt 2b — übernimmt den (ggf. vom Nutzer am Job-Detail bearbeiteten) CV-Entwurf aus cv-match, schreibt Änderungen in die .docx zurück, erzeugt Word+PDF nach Namenskonvention (inkl. Seitenumbruch-Schutz + Fußzeile, Phase 46 Stufe A) und führt DANACH den ATS-Scan durch. Nutze diesen Skill bei "CV erstellen für Job <id>". NICHT für den Match-Schritt selbst (das ist cv-match) und NICHT für die Firmen-/Fit-Prüfung (das ist firma-pruefen).
---

# CV erstellen (Schritt 2b)

Der **Abschluss** der CV-Vorbereitung: nimmt den Entwurf aus `cv-match` — unverändert oder vom
Nutzer am Job-Detail bearbeitet —, macht daraus die finale `.docx` + PDF (Namenskonvention +
Seitenumbruch-Schutz + Fußzeile, s. `pipeline/cv_export.py`) und danach den ATS-Scan.
**Voraussetzung:** eine `CVVersion` mit `status=entwurf` existiert für diesen Job (aus `cv-match`).

**Beirats-Votum ist Kontext, KEIN Gate** (wie bei `cv-match`/`firma-pruefen`) — kein Rückfragen,
kein Zurückstellen; ein Klick auf „CV erstellen" ist die bewusste Freigabe des Nutzers.

## Ablauf

### 1. Entwurf laden
```sh
curl -s http://localhost:8000/api/jobs/<job_id>/cv-entwurf
```
Liefert die JÜNGSTE `CVVersion` mit gespeichertem `entwurf_text` — bewusst UNABHÄNGIG vom
aktuellen `status` (deckt auch „erneut erstellen" auf einer bereits `status=fertig`-Version ab,
der Entwurf bleibt gespeichert; die folgenden Schritte sind idempotent). `null`, falls noch
keine CVVersion existiert — dann ehrlich abbrechen: „Kein CV-Entwurf für Job <id> gefunden,
zuerst CV-Match ausführen", keine eigene Match-Logik hier nachbauen. Merke dir `cv_version_id`
und `file_path`.

**`status=fertig` ist NIE ein Abbruchgrund (P2-45, 25.09.2026).** Seit diesem Datum bearbeitet
der Nutzer den Entwurf auch NACH dem Erstellen weiter (Textfenster am Job-Detail) und startet danach
diesen Lauf erneut — die Edits stecken dann in `entwurf_text` und kämen ohne Schritt 2 nie in die
Datei. Echtfall: Ein Lauf meldete „war schon heute abgeschlossen …, nichts neu erzeugt,
nur verifiziert" und ließ die Änderungen des Nutzers liegen. Also: immer durchlaufen (Schritte 2–5),
dieselbe `CVVersion`-Row aktualisieren, keine neue anlegen. Im Bericht steht, was neu erzeugt
wurde und wie viele Absätze aus den Edits übernommen wurden.

### 2. Entwurf zurückschreiben (übernimmt die Edits des Nutzers, falls vorhanden)
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.cv_export entwurf-schreiben <cv_version_id>
```
Schreibt jeden in der DB gespeicherten Absatz-Text an seinen ORIGINAL-Index in der Entwurfs-
`.docx` zurück (NUR tatsächlich geänderte Absätze, Struktur/Styling der `.docx` bleibt
unangetastet — v1-Editor, kein Struktur-Umbau, s. `cv_export.py::_text_ersetzen`). Antwort
`{"geaendert": N}` — **merke dir N für den Bericht** („ediert" ja/nein, s. Schritt 5).

### 3. Umbenennen + Seitenumbruch-Schutz + Fußzeile + PDF
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.cv_export <cv_version_id>
```
Das ist die BESTEHENDE Export-Funktion (unverändert seit Phase 12, seit Phase 46 Stufe A mit
Dokument-Engine): benennt die `.docx` nach `CV_<Name>_<Firma>_<Position>[_<Sprache>]` um,
schützt Stationen/Abschnitts-Überschriften vor unsauberen Seitenumbrüchen, setzt die Fußzeile
„<Name> · Seite X von Y" und erzeugt das PDF (LibreOffice headless). Die finalen Namen stehen
im Rückgabe-JSON unter `docx`/`pdf` (ggf. `pdf_fehler` — nicht fatal, s. u.).

### 4. ATS-Scan — Pflichtinhalt (Phase 35, Schema verschärft Phase 49, Score-Methodik v2 seit Phase 55), jetzt gegen die FINALE .docx
Erst JETZT, nach Schritt 3 — der Scan muss den Text prüfen, den der Nutzer am Ende tatsächlich
verschickt (inkl. seiner Edits aus Schritt 2). Inhalt der fertigen `.docx` lesen:
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -c "
from pipeline.cv_export import entwurf_extrahieren
import json
print(json.dumps(entwurf_extrahieren('<finaler docx-Pfad aus Schritt 3>'), ensure_ascii=False))
"
```
(Dieselbe Funktion wie die Entwurf-Extraktion in `cv-match` — hier nur zum LESEN genutzt, kein
Zurückschreiben.)

**Keyword-Liste: aus `keywords_json` der in Schritt 1 geladenen CVVersion-Row lesen — KEINE
Neu-Extraktion.** `cv-match` hat die 15 Begriffe in Schritt 1d erzeugt und der Entwurf wurde
bereits dagegen optimiert; eine zweite, unabhängige Extraktion hier würde gegen eine andere Liste
messen, als gebaut wurde (genau der Fehler, den Phase 55 behebt). **Fallback** (Entscheidung 5):
fehlt `keywords_json` (Alt-Entwurf vor Phase 55) → das Keyword-Protokoll aus `cv-match` Schritt 1d
EINMALIG hier selbst ausführen (gleiche 15er/Kategorien/Klassifikations-Regeln, Stellenanzeige
über dieselbe Quelle wie in `cv-match` Schritt 1 — Snapshot zuerst, dann `nachholen`, WebFetch auf `job.url` nur als Teilquelle) und im Report
vermerken: „Keyword-Liste beim Scan erhoben — Entwurf stammt aus Methodik v1".

Jeden Begriff aus der Liste gegen die FINALE `.docx` prüfen — wörtlich oder sinngleich mit
konkretem Beleg (eiserne Regel unverändert, kein erfundener Treffer, um die Quote zu heben). Drei
Eimer:
- **abgedeckt** — `abdeckbar: true` UND im finalen Text gefunden.
- **nicht abgedeckt (strukturelle Lücke)** — `abdeckbar: false` aus der Liste, `grund` übernehmen.
- **abdeckbar, aber nicht eingearbeitet** — `abdeckbar: true`, im finalen Text (noch) nicht
  gefunden → Auslöser für die Feedback-Schleife, Schritt 4b direkt im Anschluss.

**Score-Formel (deterministisch, im Report vorrechnen):**
`ATS-Score = round(0.60 · K + 0.25 · T + 0.15 · F)`
- **K** = abgedeckte abdeckbare Keywords ÷ alle abdeckbaren Keywords × 100 (Basis NUR
  `abdeckbar: true`-Begriffe; Basis 0 → K=0 + Pflicht-Hinweis im Report „keine abdeckbaren
  Keywords — Bewerbung überdenken").
- **T** = Titel-/Rollen-Alignment, drei Stufen mit Beleg: **100** = Anzeigen-Titel wörtlich/nahezu
  wörtlich in Positionierung, Executive Summary oder einem Stationstitel · **60** = verwandter
  Titel (gleiche Funktion, andere Worte; Beleg nennen) · **20** = fern.
- **F** = Format/Parsbarkeit, 5 Checks à 20 Punkte: einspaltig ohne Tabellen/Textboxen · native
  Word-Überschriften/Listen · Kontaktdaten in den ersten Zeilen · Standard-Rubriken erkannt
  (Executive Summary, Berufserfahrung, …) · Datei ist .docx mit korrekter Namenskonvention (die
  Dokument-Engine aus Phase 46 garantiert das normalerweise → typisch 100; trotzdem echt prüfen,
  nicht pauschal vergeben).

Die **Abdeckungsquote roh** (abgedeckt ÷ 15, unabhängig von `abdeckbar`) bleibt daneben sichtbar —
ehrliche Fit-Info, drückt aber NICHT mehr den Score. `ats_score` bleibt int 0–100 (Excel-Export,
Unterlagen-Karte, Abschlussmeldung funktionieren unverändert).

Im Look von `assets/report_theme_bms.html` (Datei vor dem Schreiben lesen, Muster
wörtlich übernehmen, Klassennamen unverändert; den Style-Block der Vorlage NICHT abschreiben, der
ATS-Scan entsteht ohne eigenen Style-Block). Kopf: eyebrow „ATS-Scan" → h1 = Rolle → sub
„Firma · Job &lt;id&gt; · geprüfte CV-Datei · Methodik v2" → Meta-Grid „ATS-Score (v2) ·
Abdeckung roh (x/15) · Sprache · Datum".

**⚠️ KLASSEN-PFLICHT — nur Klassen aus der Vorlage, kein eigenes CSS.** Der Report ist eine
EIGENSTÄNDIGE Datei; den Style-Block schreibst du nicht und kopierst du nicht, ihn setzt nach dem
Speichern `bericht_stil einsetzen` ein (s. „Pflicht-Endkontrolle“ unten). Klassen im Markup sehen
ohne die passende Regel grau/farblos aus, obwohl das HTML korrekt ist (Rückfall 23.07.2026, bei einer
Firma: `class="chip pos"` 9× im Markup, aber die Regel `.chip.pos` fehlte → alle Chips neutral).
Deshalb nur die Klassen aus der Vorlage und aus den Bausteinen unten benutzen (`chip pos`/`neg`/`warn`,
`badge pos`/`neu`/`neg`, `tag direkt`/`indirekt`, …; `chip warn` ist die dritte Chip-Gruppe aus
Baustein 3): **verwendete Klasse ⇒ Regel im zentralen CSS.** Fehlt eine, melden `bericht_stil einsetzen`
und `report_check` sie.

**⚠️ Verbindliches Layout — GENAU diese fünf Bausteine, in dieser Reihenfolge, NICHT durch eigene
Freitext-Karten ersetzen oder vereinfachen.** Grund: ohne feste Bausteine driftet das Layout von
Lauf zu Lauf (beobachtet 22.07.2026 — ein Lauf verlor gegenüber dem Referenzlauf sowohl
die farbigen Keyword-Chips als auch die Schwachstellen-Tabelle, weil beides nur als Freitext
improvisiert wurde). **Referenz-Beispiel, an dem sich JEDER Lauf messen lassen muss:**
`data/templates/referenz_atsscan_v2.html`, falls vorhanden (Design-Review 10.08.2026: vollständig
Methodik-v2-konform, alle 5 Bausteine korrekt, 0 report_check-Befunde; ersetzt die ältere
v1-Referenz) — bei Zweifel diese Datei zum Vergleich öffnen (Aufbau und Markup; ihren Style-Block nicht
übernehmen). Fehlt sie (neue Installation), gelten
allein die fünf Bausteine unten; dann NICHT ersatzweise den neuesten Bericht als Vorlage nehmen,
sonst pflanzen sich dessen Abweichungen fort. (Historie: die frühere Referenz
war noch Methodik v1 — zwei Chip-Gruppen, Prosa-Score-
Herleitung — und ist damit überholt; Methodik v2 = Phase 55, real verifiziert
am 24.07.2026 — Testartefakte danach aus DB und Papierkorb-Historie aufgeräumt). Sobald ein
regulärer v2-Report aus echter Bewerbungsarbeit vorliegt, diesen Verweis durch ihn ersetzen.

**Baustein 1 — BLUF direkt unter dem Kopf** (ein bis zwei Sätze Kernaussage):
```html
<div class="bluf">
  <p class="fitlabel">Kernaussage in einem Satz</p>
  <p>Ein bis zwei Sätze: wie gut passt der CV zur Anzeige, wo sitzen die Kernbegriffe, wo sind die echten Lücken.</p>
</div>
```

**Baustein 2 — Sektions-Erkennung, IMMER als Zwei-Karten-Grid** (nie eine einzelne Karte):
```html
<h2 class="sec">Sektions-Erkennung</h2>
<div class="grid">
  <div class="card">
    <h3>Struktur</h3>
    <p class="kv">Erkannte Rubriken (Heading-1-Stil)</p>
    <p>Executive Summary · Berufserfahrung · Ausbildung · Zertifizierungen &amp; Weiterbildung · Schwerpunkte · Technische Fähigkeiten · Sprachen · …</p>
  </div>
  <div class="card">
    <h3>Parsbarkeit</h3>
    <p class="kv">Format</p>
    <p>Einspaltig, native Word-Überschriften/Listen (kein Tabellen-Layout, keine Textboxen) — für Standard-ATS-Parser gut lesbar. Kontaktdaten stehen einzeln in den ersten Zeilen, wie von ATS-Parsern erwartet. Bewerbungsfoto im Kopfblock vorhanden (bewusste Entscheidung, Phase 76 — die PDF-Textreihenfolge bleibt davon nachweislich unberührt); seit v9 steht je Station der Jobtitel VOR Firma und Zeitraum (Workday-Parser-Fix).</p>
  </div>
</div>
```

**Baustein 3 — Keyword-Abgleich**, jetzt DREI Chip-Gruppen mit den festen Klassen `chip pos` /
`chip neg` / `chip warn` (NIE Inline-Farben, NIE ungefärbte Chips ohne Klasse — genau das ist
22.07. verlorengegangen):
```html
<h2 class="sec">Keyword-Abgleich</h2>
<div class="card">
  <p class="kv">Abgedeckt (10 von 15)</p>
  <div class="comp">
    <span class="chip pos"><b>Führung großer Teams</b> <span>(16/24/18/15 Direct Reports)</span></span>
  </div>
  <p class="kv" style="margin-top:14px">Nicht abgedeckt — strukturelle Lücke (ehrlich, keine Erfindung)</p>
  <div class="comp">
    <span class="chip neg"><b>Second-Level-Organisation</b> <span>(kein Support-Tiering im CV)</span></span>
  </div>
  <p class="kv" style="margin-top:14px">Abdeckbar, aber nicht eingearbeitet (nach Feedback-Schleife normalerweise leer)</p>
  <div class="comp">
    <span class="chip warn"><b>Customer Experience</b> <span>(Beleg vorhanden, Einarbeitung würde Nutzer-Edit berühren)</span></span>
  </div>
</div>
```
**Eiserne Regel:** ein Begriff gilt nur als „abgedeckt", wenn er WÖRTLICH im CV steht ODER
sinngleich mit konkret benennbarem CV-Beleg (Station/Zitat) — sonst „abdeckbar, aber nicht
eingearbeitet" (`chip warn`, dann Schritt 4b) oder „nicht abgedeckt" (`chip neg`, `abdeckbar:
false` aus der Liste). KEIN erfundener Treffer, um die Quote zu heben. Die Chip-Zählung „Abgedeckt
(x von 15)" muss mit der Kopf-Meta-Spalte „Abdeckung roh (x/15)" übereinstimmen.

**Baustein 4 — Score-Herleitung (Methodik v2)**, Komponenten-Tabelle statt Prosa — jede Zeile
rechnet Wert × Gewicht = Beitrag vor, letzte Zeile summiert:
```html
<h2 class="sec">Score-Herleitung (Methodik v2)</h2>
<div class="card">
  <table class="score">
    <thead><tr><th>Komponente</th><th>Wert</th><th>Gewicht</th><th>Beitrag</th></tr></thead>
    <tbody>
      <tr><td class="factor">Keyword-Optimierung (abdeckbare Begriffe: 9 von 10 drin)</td><td>90</td><td>60 %</td><td>54,0</td></tr>
      <tr><td class="factor">Titel-/Rollen-Alignment (Beleg: „Head of …" in Positionierung)</td><td>100</td><td>25 %</td><td>25,0</td></tr>
      <tr><td class="factor">Format &amp; Parsbarkeit (5/5 Checks)</td><td>100</td><td>15 %</td><td>15,0</td></tr>
      <tr><td class="factor"><b>ATS-Score</b></td><td colspan="2"></td><td><b>94</b></td></tr>
    </tbody>
  </table>
  <p>Abdeckungsquote roh: <b>10 von 15</b> (67 %) — die 5 strukturellen Lücken (…) zählen bewusst
  NICHT gegen den Optimierungsgrad; sie sind Fit-Befunde und stehen im Match-Dashboard/
  Company-Fit. Keine Erfindung, kein Keyword-Stuffing.</p>
</div>
```
Die K-Komponente rechnet NUR über die abdeckbare Teilmenge (Nenner = Anzahl `abdeckbar: true`,
NICHT 15) — das ist eine andere Zahl als die Roh-Quote im Absatz darunter, beide müssen aber in
sich konsistent zur Chip-Zählung (Baustein 3) und zum Kopf-Meta sein.

**Baustein 5 — Schwachstellen & Rewrites, IMMER als Tabelle** (`table.score`, NIE als Karten-Grid
mit Fließtext) — vier Spalten, Ampel-Badges `badge pos`/`badge neu`/`badge neg`:
```html
<h2 class="sec">Schwachstellen &amp; Rewrites</h2>
<table class="score">
  <thead><tr><th>Schwachstelle</th><th>Wert</th><th>Einordnung</th><th>Handlungsoption</th></tr></thead>
  <tbody>
    <tr>
      <td class="factor">Titel-Diskrepanz</td>
      <td><span class="badge neg">−</span></td>
      <td>Kurzbegründung mit Beleg/Zitat, warum das ATS-relevant ist.</td>
      <td class="rel">Konkreter Rewrite-Vorschlag ODER — falls keine Formulierung die Lücke schließt (z. B. fehlender Abschluss, fehlende Branche) — ehrlich „keine Erfindung, im Anschreiben/Gespräch adressieren".</td>
    </tr>
    <tr>
      <td class="factor">Offener Punkt ohne Rewrite-Option</td>
      <td><span class="badge neu">0</span></td>
      <td>Erwartbar (z. B. Plattformwechsel), kein Automatik-Ausschluss.</td>
      <td class="rel">Transferierbare Erfahrung im Anschreiben als Analogie nutzen.</td>
    </tr>
  </tbody>
</table>
```
Je Zeile EIN konkreter Befund (Titel-Diskrepanz, fehlende Ausbildung/Zertifizierung, Scope-Bruch,
fehlende Produkt-/Branchenerfahrung, …) — 2 bis 5 Zeilen je nach echtem Befund, keine
Pflichtanzahl. `badge neg` nur wenn es eine ECHTE, im CV nicht kaschierbare Lücke ist; `badge neu`
für erwartbare/neutrale Punkte ohne Rewrite-Option; `badge pos` nur, falls eine Stärke explizit
hervorgehoben werden soll (selten in dieser Sektion, meist im Keyword-Abgleich abgedeckt).

Dateiname:
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -c "from app.naming import report_filename; print(report_filename('ATSscan', '<Firma>', '<Position>'))"
# → JJJJMMTT_ATSscan_<Firma>_<Position>  (ohne Extension; .html anhängen)
```
Speichern unter `data/company_fit/<ATSscan-Name>.html`.

**Pflicht-Endkontrolle NACH dem Speichern** (deterministisch, kostet nichts — erst den Stil
einsetzen, dann prüfen; fängt genau den Fall vom 23.07.2026 ab, bei dem die Chips farblos blieben):
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.bericht_stil einsetzen "../data/company_fit/<ATSscan-Name>.html" && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.report_check "../data/company_fit/<ATSscan-Name>.html"
```
Meldet einer der beiden Befehle eine Klasse ohne Regel, die Klasse durch eine aus der Vorlage
ersetzen (kein eigenes CSS) und beide Befehle wiederholen — **erst dann** Schritt 5 (bzw. 4b, falls
unten ausgelöst). Nie mit einem roten Check weitermachen.

### 4b. Feedback-Schleife (max. 1 Iteration, Phase 55)
Steht nach Schritt 4 mindestens ein Begriff in der `chip warn`-Gruppe (`abdeckbar: true`, aber im
finalen Text nicht gefunden) → GENAU EINMAL nachbessern, dann fertig — **kein Loop bis 100, ein
zweiter Re-Scan zählt nicht mehr**:

1. Für jeden `warn`-Begriff den passenden Rewrite-Vorschlag aus Baustein 5 (Schwachstellen &
   Rewrites) **minimal-invasiv** in eine bestehende Bullet einarbeiten (ergänzen/leicht
   umformulieren, nicht ersetzen). **Die eigenen Edit-Zeilen des Nutzers NIE löschen oder umformulieren** —
   im Zweifel, welche Zeile vom Nutzer stammt (keine Autor-Markierung im `entwurf_text`), lieber
   eine ohnehin von `cv-match` angepasste Bullet wählen oder eine zusätzliche Zeile innerhalb einer
   Bullet-Gruppe ergänzen, statt eine bestehende Zeile zu überschreiben. Lässt sich ein Begriff ohne
   Eingriff in eine mutmaßliche Nutzer-Zeile nicht sauber einarbeiten → weglassen, in Baustein 5
   dokumentiert lassen und der Begriff bleibt `chip neg` (nicht `warn`) im finalen Report.
2. Änderung in die DB schreiben: `PATCH /api/cv-versions/<cv_version_id>/entwurf` mit dem
   aktualisierten `entwurf_text`. Status ist zu diesem Zeitpunkt noch `entwurf` (Schritt 5 setzt
   `fertig` erst danach) — das Status-Gate der Route greift also nicht.
3. Bestehenden Weg erneut durchlaufen: Schritt 2 wiederholen (`entwurf-schreiben`, schreibt in den
   aktuellen `file_path` — nach Schritt 3 bereits die final umbenannte `.docx`) + Schritt 3 erneut
   (Umbenennen/Seitenumbruch-Schutz/Fußzeile/PDF — idempotent gemäß `cv_export.export()`).
4. Schritt 4 EINMAL komplett wiederholen (Text erneut aus der jetzt aktualisierten finalen `.docx`
   lesen, Abgleich gegen dieselbe `keywords_json`-Liste) und den bereits gespeicherten Report mit
   den NEUEN Werten überschreiben (Kopf-Meta, Baustein 3 Chip-Gruppen, Baustein 4
   Score-Herleitung) — danach `bericht_stil einsetzen` und `report_check.py` erneut gegen die aktualisierte
   Datei laufen lassen.
   Die `warn`-Chip-Gruppe ist danach im Normalfall leer.

Kein `warn`-Begriff nach Schritt 4 → Schritt 4b komplett überspringen, direkt zu Schritt 5.

### 5. Fertigstellen
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.deepdive fertigstellen <cv_version_id> --ats-score <N> --ats-scan-path <data/company_fit/....html>
```
Setzt `status=fertig` und trägt ATS-Score/-Pfad ein. **Erst danach** wird die CV in der UI als
„fertig" angezeigt und Schritt 4 (Anschreiben) am Job-Detail entsperrt.

### 6. Bericht (Kompakt-Format — landet 1:1 in einer schmalen UI-Karte)
**Grundregel:** „Ein erledigt reicht." KEINE Markdown-Überschriften, keine Aufräum-/Temp-Datei-Hinweise.
- **Zeile 1 = das ALLERERSTE Zeichen der Meldung, KEINE Vorrede davor:**
  `CV erstellt — ATS <n> % · <Sprache>`
- optional **EIN** Satz — erwähnt AUSDRÜCKLICH, ob der Entwurf des Nutzers bearbeitet wurde
  (`geaendert` aus Schritt 2 > 0 → „<n> Absätze wurden vor der Erstellung bearbeitet"; sonst
  „unverändert aus dem Entwurf übernommen").
- **Schlusszeile:** die **finalen Dateinamen** (docx + pdf aus Schritt 3).

Die ⬇-Links (docx/pdf/Ansehen) rendert die Web-App selbst unter der Meldung — nicht in den Text schreiben.
Ist `pdf_fehler` gesetzt (z. B. LibreOffice fehlt): den Text als den EINEN Zusatzsatz weitergeben —
die `.docx` gilt trotzdem, das PDF lässt sich mit `python -m pipeline.cv_export <cv_version_id>` nachrüsten.

## Abgrenzung
- **Schritt 2a = `cv-match`** (Match-Dashboard + editierbarer Entwurf). **Schritt 2b = dieser
  Skill** (Übernahme + Word/PDF/ATS). Ohne vorherigen `cv-match`-Lauf gibt es nichts zu erstellen.
- Läuft in der Kette `bewerbungspaket`/`deepdive` automatisch NACH `cv-match` durch — dort
  bearbeitet niemand den Entwurf (kein Rückkanal headless), das Ergebnis entspricht dann exakt
  dem alten `cv-anpassen`-Ein-Klick-Fluss.
