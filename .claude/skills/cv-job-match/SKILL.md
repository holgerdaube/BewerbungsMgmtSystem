---
name: cv-job-match
description: Analysiert einen Lebenslauf (.docx) gegen EINE konkrete Stellenbeschreibung aus Recruiter-Sicht und überarbeitet die Berufserfahrung wahrheitstreu nach der Google-XYZ-Formel. Liefert den Match-Score 0–100 mit offengelegten Gewichten, die wichtigsten fehlenden Keywords, Red Flags, eine angepasste Arbeitskopie der Basis-CV (nur Text, Layout und Foto bleiben) und ein Änderungsprotokoll für die Vorher/Nachher-Gegenüberstellung. Wird von cv-match (Schritt 1) und job-deepdive aufgerufen und ist auch direkt nutzbar, etwa bei "passe ich auf diese Stelle", "Lebenslauf für diese Stelle überarbeiten", "Keywords aus der Anzeige einbauen" oder "Match-Analyse". Schreibt selbst keine HTML-Berichte und macht keinen ATS-Scan, das tun cv-match (Match-Dashboard) und cv-erstellen (ATS-Scan). NICHT für "CV-Match für Job <id>" (das ist cv-match) und NICHT für die Firmenprüfung (das ist firma-pruefen).
---

# CV ↔ Job Match

Bewertet einen Lebenslauf gegen eine Stellenbeschreibung wie ein erfahrener Senior Recruiter, der diese
Stelle besetzt, und liefert konkret umsetzbare, wahrheitstreue Verbesserungen.

## Einsatz und Abgrenzung

- **Aus `cv-match` (Normalfall).** `cv-match` legt die frische Arbeitskopie an, beschafft die Anzeige,
  stellt das Keyword-Protokoll auf und ruft diesen Skill auf. Danach schreibt `cv-match` das
  Match-Dashboard (gewichtetes Anforderungs-Matching, Keyword-Protokoll, Vorher/Nachher) und registriert
  den Entwurf. Dieser Lauf hat meist **keinen Rückkanal** (Hintergrundlauf): keine Rückfragen, siehe Schritt 2.
- **Aus `job-deepdive`.** Ebenso; den Ablageort der Arbeitskopie nennt der Aufrufer.
- **Direkt** (interaktiv, `/cv-job-match` oder eine der Formulierungen aus der Beschreibung): Der Nutzer
  liefert Lebenslauf und Stellenbeschreibung. Das Ergebnis kommt als Text in den Chat (Schritt 6).

**Was dieser Skill nicht tut:**
- Keine HTML-Berichte. Das Match-Dashboard schreibt `cv-match` (dort Schritt 1b bis 1d), den ATS-Scan
  `cv-erstellen` (dort Schritt 4). Den Look der Berichte setzt zentral `bericht_stil` aus
  `assets/report_theme_bms.html`; eine zweite Gestaltungsquelle gibt es hier bewusst nicht.
- Keinen ATS-Score und keine Parse-Rate. Die Methodik (Score-Formel, feste Keyword-Liste) liegt in
  `cv-erstellen`; eine zweite Zahl daneben würde ihr widersprechen.
- Kein PDF, keine Namenskonvention, keine Registrierung in der Datenbank. Das erledigen `cv-match`
  (Entwurf registrieren) und `cv-erstellen` (Word, PDF, ATS).
- Kein Abruf der Anzeige aus dem Netz. Die Stellenbeschreibung kommt vom Aufrufer oder vom Nutzer.

## Grundprinzipien (nicht verhandelbar)

Diese Regeln tragen jeden Schritt. Sie schützen den Bewerber vor Schaden im Gespräch und sichern die
Glaubwürdigkeit der Unterlagen.

1. **Wahrheitstreue über alles.** Niemals Erfahrung, Zahlen, Titel oder Skills erfinden. Verändert werden
   Rahmung, Reihenfolge und Wortwahl, nie die Substanz. Wenn ein Keyword nicht durch echte Erfahrung
   gedeckt ist, wird es nicht eingebaut. Das ehrlich benennen.
2. **Echte Lücken ehrlich benennen, nicht wegschreiben.** Fehlt eine harte Anforderung (z. B.
   Hochschulabschluss, Pflicht-Zertifikat), wird sie nicht versteckt. Stattdessen abfedern
   (Äquivalenz-Argumente, Anschreiben) und offen als Risiko markieren.
3. **Bei Unsicherheit fragen, ohne Rückkanal nicht raten.** Trifft ein Keyword nur "teilweise" zu (z. B.
   regionales Netzwerk, Branchenbezug), nicht raten. Interaktiv den Bewerber fragen, wie sichtbar es
   wahrheitsgemäß gemacht werden darf (Schritt 2). Im Hintergrundlauf wird es nicht eingebaut und als
   offener Punkt zurückgemeldet.
4. **Die Basis-CV bleibt unangetastet.** Gearbeitet wird nur in einer Arbeitskopie. Wird dieselbe
   Arbeitskopie bei direktem Aufruf mehrfach bearbeitet, die Versionsnummer hochzählen (v5 → v6 → v7) und
   nie die vorherige Fassung überschreiben.
5. **Format respektieren.** Das Originalformat des CV ist die Basis, kein zusätzliches Branding.
6. **Änderungen unsichtbar im CV.** Eingebaute Keywords und umgeschriebene Bullets erscheinen in der
   finalen `.docx` in normaler Textstärke, nicht fett, unterstrichen oder farbig markiert. Für eine
   außenstehende Person (Recruiter, ATS-Leser) darf nicht erkennbar sein, was überarbeitet wurde;
   sichtbare Markierungen verraten die Optimierung und untergraben die Glaubwürdigkeit. Vorhandene
   strukturelle Hervorhebungen des Original-CV (z. B. fette Jobtitel oder Firmennamen) bleiben
   unverändert erhalten. Welche Stellen geändert wurden, zeigt ausschließlich die Vorher/Nachher-Sektion
   im Bericht des Aufrufers.

## Sprachregeln (strikte Trennung, gelten für jeden Schritt)

Die Stellensprache (Schritt 0) bestimmt die Sprache **aller bewerbungsrelevanten Artefakte**. Ein
englischer Prozess bleibt durchgehend englisch, ein deutscher durchgehend deutsch, ein französischer,
italienischer, spanischer oder portugiesischer ebenso. Niemals mischen:

**Folgt der Stellensprache:**
- Der Input-CV (passende Sprachfassung wählen, siehe Schritt 0)
- Alle umgeschriebenen XYZ-Bullets und die Summary (Schritt 3): englische Stelle heißt englische Bullets,
  deutsche Stelle deutsche Bullets, französische Stelle französische Bullets usw.
- Die bearbeitete `.docx` (Schritt 4), inklusive Abschnittsüberschriften des CV
- Die Vorher/Nachher-Zitate im Änderungsprotokoll (Schritt 5): beide Seiten zitieren den CV wörtlich, also
  in dessen Sprache

**Folgt der Ausgabesprache (Vorgabe im Auftrag, ohne Vorgabe Deutsch):**
- Die Kommunikation im Chat (Zusammenfassung, Klärungsfragen, Einordnung)
- Erklärende Meta-Texte (Begründungen, Lösungshinweise, Score-Herleitung). CV-Zitate darin bleiben in der
  CV-Sprache.

**Sprachwahl für den Basis-CV.** Der Basis-CV ist `data/cv_basis/base_<sprache>.docx` mit dem kleingeschriebenen
Kürzel der Stellensprache (`de`, `en`, `fr`, `it`, `es`, `pt`). Bei gemischten Anzeigen zählt die dominante Sprache
des Fließtexts. Die Stellensprache folgt der Anzeige, nie der Sprache der Oberfläche. Fehlt bei einer französischen,
italienischen, spanischen oder portugiesischen Stelle die Fassung dieser Sprache: nichts übersetzen, zuerst
`base_en.docx` nehmen, falls vorhanden, sonst `base_de.docx`, und den Sprachbruch melden. Das Sprachkürzel der
CV-Version (`language`) wird großgeschrieben angegeben (`DE`, `EN`, `FR`, `IT`, `ES`, `PT`) und nennt die Sprache der
Fassung, die tatsächlich benutzt wurde.

**Keywords werden NIE übersetzt.** Ein Keyword wird exakt in der Schreibweise eingebaut, in der es in der
Stellenanzeige steht, auch wenn das in einem deutschen CV ein englischer Begriff ist ("Professional
Services", "P&L", "Stakeholder Management"). ATS-Systeme matchen den Wortlaut; eine Übersetzung zerstört
den Treffer. Steht dasselbe Keyword in der Anzeige in beiden Sprachen, die Variante der dominanten
Anzeigensprache nehmen.

## Kandidat und Basis-CV

Der Kandidat ist der Nutzer des Systems. Nichts annehmen, was nicht in seinen Dateien steht:

- **Basis-CV:** `data/cv_basis/base_<sprache>.docx`, also `base_de.docx` (Deutsch), `base_en.docx` (Englisch) und,
  falls vorhanden, `base_fr.docx`, `base_it.docx`, `base_es.docx`, `base_pt.docx`. Welche Fassungen es gibt,
  steht in `config/profil.md` im Abschnitt "Sprachen / CV-Fassungen" und im Ordner `data/cv_basis/`. Genutzt wird
  je Lauf **nur eine** Fassung, passend zur Sprache der Stelle (Sprachwahl oben, Schritt 0).
- **Substanz und Positionierung:** `config/profil_struktur.md` (strukturierter Werdegang, Skills,
  Zertifikate), falls der Aufrufer sie nicht ohnehin mitgibt.
- **Rahmenbedingungen:** `config/profil.md`, Abschnitte "Harte Rahmenbedingungen" (Region, Umzug,
  Arbeitsmodell, Ausschlüsse) und "Bekannte Skill-Gaps / Red Flags". Die Dimension Region/Arbeitsmodell
  (Schritt 1) wird gegen diese Angaben bewertet. Präferenzen nie raten.

**Zwei CV-Varianten, am Dateinamen oder an der Angabe des Aufrufers erkennbar:**
- **Design-Variante** (ohne `_ATS` im Namen): mit Foto und Layout, für menschliche Leser. Hier gilt der
  Bild- und Layout-Erhalt aus Schritt 4 uneingeschränkt.
- **ATS-Variante** (`_ATS` im Dateinamen, im Projekt auch die Basis-CVs `base_<sprache>.docx`
  laut `cv-match`): schlicht, einspaltig, **bereits für ATS-Parser gebaut**. Struktur und Layout sind
  fertig. Der Skill baut hier ausschließlich Text ein (Keywords, XYZ-Bullets) und fasst die Struktur nicht
  an: kein Umbau der Rubriken, keine Änderung der Zeilenfolge einer Station, keine ATS-"Verbesserung".

Im Zweifel, welche Variante gemeint ist, interaktiv kurz fragen; im Hintergrundlauf gilt die Angabe des
Aufrufers. Nie eine ATS-Datei strukturell umbauen und nie eine Design-Datei ihres Fotos berauben.

## Workflow

Standardmäßig die Schritte 0 bis 6 in dieser Reihenfolge. Wird nur ein Teil verlangt (z. B. nur die
Match-Analyse), den entsprechenden Schritt isoliert ausführen.

### Schritt 0 – Material sichten

- **Stellenbeschreibung** einlesen (Text oder Datei, vom Aufrufer oder vom Nutzer). Dieser Skill holt sie
  nicht selbst und recherchiert nicht im Netz. Ist der Text nur eine Teilquelle (Zusammenfassung, nur Titel
  und Firma), das im Ergebnis ausweisen (Zeile "Quellenlage" in Schritt 6) und den Score entsprechend
  vorsichtig herleiten.
- **Sprache der Stelle bestimmen** (Deutsch, Englisch, Französisch, Italienisch, Spanisch oder Portugiesisch). Bei
  gemischten Anzeigen (deutscher Text mit
  englischem Titel oder englischen Fachbegriffen, der Normalfall im DACH-Raum) entscheidet die **dominante
  Sprache des Fließtexts**. Die Stellensprache steuert, welche CV-Fassung als Input dient: deutsche Stelle,
  deutscher Lebenslauf; englische Stelle, englischer Lebenslauf; ebenso für Französisch, Italienisch, Spanisch
  und Portugiesisch (`base_<sprache>.docx`, Sprachwahl in den Sprachregeln).
- **Liegt nur die falsche Sprachfassung vor** (z. B. englische Stelle, aber nur ein deutscher CV): nicht
  stillschweigend weitermachen. Interaktiv fragen, ob die fehlende Fassung als neue Version entstehen soll
  (wahrheitstreue Übersetzung, gleiche Substanz) oder ob die vorhandene bewusst genutzt wird. Ohne
  Rückkanal: mit der vorhandenen Fassung arbeiten (bei einer französischen, italienischen, spanischen oder
  portugiesischen Stelle zuerst die englische, sonst die deutsche), nichts übersetzen und den Sprachbruch ausdrücklich unter
  "Offene Punkte" in Schritt 6 melden. Nur die Analyse (Score, Lücken) darf sprachübergreifend laufen.
- **Genau einen Lebenslauf** lesen: die zur Stellensprache passende Fassung (Text mit python-docx, siehe
  Schritt 4). Liegt der CV nur als PDF vor, mit dem Lese-Werkzeug der Umgebung lesen (es kann PDF), nicht
  aus dem Dateinamen raten. Aus einer reinen Text-Extraktion lässt sich analysieren; die Datei in Schritt 4
  entsteht dann nicht.
- Aus der Stelle die **harten Anforderungen** (K.-o.-Kriterien: Abschluss, Pflicht-Erfahrung, Region) und
  die **Keyword-Liste** (Skills, Tools, Begriffe) extrahieren. **Gibt der Aufrufer eine feste Keyword-Liste
  mit** (`cv-match`: das Keyword-Protokoll mit 15 Begriffen und der Kennzeichnung `abdeckbar`), gilt genau
  diese Liste, ohne zweite, abweichende Extraktion. Eingebaut werden dann nur die als `abdeckbar` belegten
  Begriffe.

### Schritt 1 – Match-Analyse

Inhalt (ein Ergebnis in Textform, die Gestaltung übernimmt der Aufrufer). Aufgerufen aus `cv-match` ist dieses Ergebnis
kein Abschluss des Laufs: `cv-match` macht danach sofort mit Dashboard und Registrierung weiter.

- **Match-Score 0–100**, gewichtet aus diesen Default-Dimensionen (bei Bedarf an die Stelle anpassen, aber
  die Gewichte offenlegen): fachliche Eignung 35 % · Führung/Scope 25 % · Region/Arbeitsmodell 15 % ·
  Vertrieb/Kundennähe (Presales, Kundenkontakt, Umsatzbezug) 10 % · formale Kriterien 15 %. Je Dimension
  Wert 0–100, Beitrag = Wert × Gewicht, Summe = Score (ganze Zahl). Score ehrlich herleiten: fachliche
  Stärke darf formale Lücken nicht überdecken. Die Herleitung kurz erklären, damit der Nutzer der Zahl
  nicht blind vertraut. Dieselbe CV/Stellen-Kombination muss bei erneutem Lauf in etwa denselben Score
  ergeben, deshalb strikt entlang der Gewichte rechnen, nicht nach Gefühl. Aus `cv-match` aufgerufen
  genügen die Tabelle der Dimensionen und zwei Sätze; die Einzelanforderungen wertet `cv-match` in 1b.
- **Bis zu fünf fehlende Keywords**, je mit Wichtigkeit (kritisch, hoch, mittel), Begründung und
  Lösungshinweis. Mit fester Keyword-Liste vom Aufrufer sind das die wichtigsten `abdeckbar: false`-Begriffe
  und die abdeckbaren, die im Basis-CV noch fehlen.
- **Die 3 größten Red Flags** im 10-Sekunden-Test eines Hiring Managers, je mit konkretem Fix. Der Fix ist
  entweder in Schritt 3 umgesetzt oder als ehrliche Lücke markiert.

### Schritt 2 – Klärungsfragen (vor der CV-Überarbeitung)

**Mit Rückkanal (interaktiv):** Bevor Keywords eingebaut werden, die unsicheren Punkte klären, gebündelt in
einer Runde mit dem Frage-Werkzeug der Umgebung: Welche "teilweise"-Keywords dürfen wie sichtbar werden?
Die **Sprache** wird nicht erfragt, sie folgt aus der Stelle. Ein Branding gibt es nicht (Grundprinzip 5).

**Ohne Rückkanal (Hintergrundlauf, z. B. aus `cv-match`):** Nicht fragen. Ein Lauf, der mit einer Frage
endet, hat nichts geliefert. Stattdessen konservativ entscheiden: "teilweise"-Keywords werden nicht
eingebaut und unter "Offene Punkte" (Schritt 6) mit dem Satz zurückgemeldet, was der Nutzer klären müsste.

### Schritt 3 – Berufserfahrung nach XYZ überarbeiten

Die Berufserfahrung nach der **Google-XYZ-Formel** umschreiben (Details und Beispiele:
`references/xyz-formula.md`): *Erreichtes Ergebnis (X), gemessen an Kennzahl (Y), durch Maßnahme (Z).* Die
neuen Bullets entstehen **in der Sprache des CV** (= Stellensprache, siehe Sprachregeln), nie in der
Chat-Sprache. Dabei die fehlenden Keywords natürlich und wahrheitstreu integrieren und die identifizierten
Red Flags entschärfen. Echte Zahlen aus dem CV beibehalten. Die eingebauten Keywords werden **nahtlos** in
den Fließtext der Bullets eingewoben, ohne Fett-, Unterstreich- oder Farbmarkierung (Grundprinzip 6).
Welche Wörter neu sind, gehört nur in die Notiz "Eingebaut" des Änderungsprotokolls (Schritt 5), nicht in
den CV-Text.

**Stationszeilen sind Fakten und bleiben unverändert:** Jobtitel, Firma, Zeitraum, Ort, Ausbildung,
Zertifikate. Überarbeitet werden Beschreibungen, Bullets und die Summary.

### Schritt 4 – Arbeitskopie bearbeiten (.docx)

**Nur Texte ändern, alles andere bleibt.** Das Foto, Grafiken, Linien, Tabellen-Layout, Kopf- und
Fußzeilen und sämtliche Layoutelemente des Original-CV werden nie entfernt oder neu erzeugt. Deshalb ist
das Vorgehen: **die Arbeitskopie in place bearbeiten** und die bestehenden Text-Runs ändern. Die Datei wird
NICHT von Grund auf neu gebaut, ein Neuaufbau verliert eingebettete Bilder und Layoutdetails. Gibt es kein
binäres Original (nur eine Text-Extraktion), entsteht keine Datei: die neuen Bullets nur als Text liefern
und im Ergebnis sagen, dass Foto und Layout nicht geprüft werden konnten.

**Werkzeug und Ablage.** Bearbeitet wird mit `python-docx` über `~/.bewerbung_mgmt_venv/bin/python`
(`import docx`). Die Arbeitskopie legt der Aufrufer an und nennt ihren Pfad. Bei direktem Aufruf zuerst
selbst eine Kopie anlegen (Python statt `cp`, `cp` ist im Hintergrundlauf nicht freigegeben):

```sh
~/.bewerbung_mgmt_venv/bin/python -c "import pathlib, shutil; z = pathlib.Path('data/cv_basis/entwuerfe'); z.mkdir(parents=True, exist_ok=True); shutil.copy('data/cv_basis/base_<lang>.docx', z / '<arbeitsname>.docx')"
```
`<lang>` ist das Kürzel der Fassung, die nach der Sprachwahl benutzt wird (`de`, `en`, `fr`, `it`, `es`, `pt`).

**Ablage nur in einem freigegebenen Ordner:** Standard ist `data/cv_basis/entwuerfe/`. Nennt der Aufrufer
einen anderen freigegebenen Zielordner (`job-deepdive`: `outputs/cv/`), gilt dieser. Die Oberfläche öffnet
Dateien nur aus freigegebenen Ordnern; eine Datei anderswo (neben der Basis, im Projekt-Root, außerhalb des
Projekts) liefert beim Öffnen einen Fehler. Die Basis-CV selbst wird nie geschrieben. Befehle vom
Projekt-Root aus ausführen; stand ein früherer Befehl in `backend/`, die Pfade mit `../` beginnen oder den
Ordner wechseln.

**Absatzgerüst bleibt.** Der Entwurf wird danach als Absatzliste gelesen (Absatzstil "List Paragraph" =
Bullet, ein Tabulator kennzeichnet die Stationszeile "Firma, Zeitraum"). Deshalb: Absätze nicht löschen,
umordnen oder zusammenlegen, keinen Tabulator in andere Zeilen setzen, Absatzstile nicht ändern. Braucht
eine Station einen zusätzlichen Bullet, den Absatz eines vorhandenen Bullets derselben Datei kopieren
(Absatz-Element klonen, damit Stil und Nummerierung mitkommen) und dann den Text setzen, keinen Absatz neu
bauen.

**4a – Stilinventar zuerst (Pflicht, bevor irgendein Text geschrieben wird).** Aus dem Original-CV die
tatsächlich verwendeten Formatierungen auslesen (python-docx: Runs iterieren, `font.name`, `font.size`,
`bold` einsammeln) und daraus eine **Stilkarte mit genau diesen Klassen** ableiten. Jede Klasse hat
exakt EINE Kombination aus Schriftart, Größe und Schnitt:

| Klasse | Beispiel im CV |
|---|---|
| H1 / Name | Name im Kopf |
| H2 / Sektionsüberschrift | "Berufserfahrung", "Ausbildung" |
| Subtitle / Jobtitel-Zeile | Rolle, Firma, Zeitraum |
| Meta | Ort, Datumszeilen, Kontaktdaten |
| Fließtext / Bullets | alle Aufzählungspunkte und Absätze |

Warum das zwingend ist: Jeder Run, der ohne explizite Font-Angabe erzeugt wird, fällt still auf die
Word-Defaults zurück (Calibri 11). Genau so entsteht der Flickenteppich aus Schriftarten und -größen.
Deshalb: **Text in den bestehenden Run schreiben (er behält seine Formatierung); wo ein neuer Run
unvermeidlich ist, Schriftart UND Größe aus der Stilkarte explizit setzen.** Umgeschriebene Bullets
bekommen immer die Klasse "Fließtext / Bullets", nie eine eigene Formatierung.

**4b – Keine Hervorhebung der Änderungen.** Die neuen und umgeschriebenen Bullets übernehmen exakt die
Textstärke und Formatierung des umgebenden Originaltexts. Fett wird nur, was laut Stilkarte fett ist (z. B.
Jobtitel). Vor dem Speichern prüfen, dass keine eingebauten Keywords versehentlich fett oder markiert sind.

**4c und 4d – Audit nach dem Bauen (Pflicht).** Ein Befehl prüft beides: die (Schriftart, Größe, fett)-
Kombinationen der neuen Datei gegen das Original und die Zahl der eingebetteten Bilder. Pfade anpassen
(`<lang>` und `<arbeitsname>` wie oben):

```sh
~/.bewerbung_mgmt_venv/bin/python - <<'PY'
import zipfile
from collections import Counter
from pathlib import Path
from docx import Document

cwd = Path.cwd()
wurzel = cwd.parent if cwd.name == "backend" else cwd    # Projekt-Root, auch nach einem früheren `cd backend`
original = wurzel / "data/cv_basis/base_<lang>.docx"
neu = wurzel / "data/cv_basis/entwuerfe/<arbeitsname>.docx"

def kombinationen(pfad):
    doc = Document(str(pfad))
    absaetze = list(doc.paragraphs)
    for tabelle in doc.tables:
        for zeile in tabelle.rows:
            for zelle in zeile.cells:
                absaetze += zelle.paragraphs
    zaehler = Counter()
    for p in absaetze:
        for r in p.runs:
            if r.text.strip():
                zaehler[(r.font.name, r.font.size.pt if r.font.size else None, r.bold)] += 1
    return zaehler

def bilder(pfad):
    with zipfile.ZipFile(pfad) as z:
        return sum(1 for n in z.namelist() if n.startswith("word/media/"))

alt, jetzt = kombinationen(original), kombinationen(neu)
for kombi, n in jetzt.most_common():
    print(n, kombi)       # None bei Name/Größe = erbt vom Absatzstil, im Original genauso
print("Nur in der neuen Datei:", sorted(set(jetzt) - set(alt), key=str) or "keine")
print("Bilder: Original", bilder(original), "- neu", bilder(neu))
PY
```

- **Typografie (4c):** "Nur in der neuen Datei" muss **keine** sein. Jede neue Kombination ist ein Fehler:
  Fundstelle lokalisieren, korrigieren, erneut prüfen. Mehr Kombinationen als Stilklassen heißt
  Flickenteppich, nicht abliefern.
- **Bilder (4d):** Die Zahl muss identisch sein. Fehlt ein Bild, ist der falsche Weg gewählt worden: auf
  das Bearbeiten der Kopie in place zurückwechseln.

### Schritt 5 – Änderungsprotokoll (Grundlage der Vorher/Nachher-Sektion)

**Während** der Bullet-Anpassung protokollieren, nicht hinterher aus der fertigen `.docx` rekonstruieren.
Je geänderter Zeile ein Eintrag:

- Station (Firma, Rolle, Zeitraum)
- **Vorher:** wörtliches Zitat aus dem Basis-CV
- **Nachher:** wörtliches Zitat aus der tatsächlich gespeicherten Datei (nach dem Speichern aus der Datei
  nachlesen und abgleichen, keine Paraphrase)
- **Eingebaut:** nur Keywords, die wörtlich aus der Stellenanzeige stammen und neu hinzugekommen sind, nie
  Bestandstext
- **XYZ:** ja oder nein ("Ergebnis zuerst" umgesetzt)

Nur tatsächlich geänderte Bullets aufnehmen; unveränderte Stationen höchstens in einer Sammelzeile
nennen. Keine Zahl nennen, die nicht in einer der beiden Fassungen steht. Hervorgehoben werden eingebaute
Keywords ausschließlich im Bericht des Aufrufers, nie in der Datei.

### Schritt 6 – Ergebnis zurückgeben

Der Aufrufer baut daraus seinen Bericht. Aus `cv-match` oder `job-deepdive` aufgerufen: **keine eigene
Abschlussmeldung** an den Nutzer, `cv-match` schreibt die Meldung in seinem festen Kompaktformat. Das
Ergebnis in dieser Reihenfolge bereitstellen:

1. **Datei:** Pfad der Arbeitskopie, Sprache der Fassung, Ergebnis der Audits (4c: keine neuen Kombinationen;
   4d: Bilder n von n)
2. **Match-Score:** ganze Zahl, dazu die Dimensionen (Gewicht, Wert, Beitrag) und zwei Sätze Herleitung
3. **Fehlende Keywords** (bis zu fünf) und **Red Flags** (drei) aus Schritt 1, je mit Fix oder ehrlicher Lücke
4. **Änderungsprotokoll** aus Schritt 5
5. **Quellenlage** (Volltext der Anzeige oder Teilquelle) und **Offene Punkte**: nicht eingebaute
   "teilweise"-Keywords, harte K.-o.-Lücken, Sprachbruch, fehlendes Original

**Direkter Aufruf, Reihenfolge im Chat:** zuerst Score und die zwei, drei wichtigsten ehrlichen Befunde in
Prosa (knapp, ohne den Nutzer mit Formatierung zu überladen), dann die XYZ-Überarbeitung als Text, dann der
Pfad der Datei. Soll daraus ein gestalteter Bericht werden, ist das der Weg über `cv-match` und
`cv-erstellen` für eine Stelle im System.

## Niemals

- Erfahrung, Zahlen, Titel, Skills oder Netzwerk-Claims erfinden, auch nicht "ein bisschen".
- Ein nicht gedecktes Keyword einbauen, nur um den Score zu heben.
- Die Basis-CV überschreiben oder Änderungen im CV sichtbar markieren.
- Den Match-Score aus dem Bauch vergeben statt entlang der offengelegten Gewichte.
- Harte K.-o.-Lücken (Abschluss, Pflicht-Zertifikat) verschweigen oder kaschieren.
- Sprachen im CV mischen: englische Stelle heißt durchgehend englischer CV samt Bullets und Überschriften,
  deutsche Stelle durchgehend deutscher CV, ebenso für Französisch, Italienisch, Spanisch und Portugiesisch.
- Keywords aus der Stellenanzeige übersetzen. Sie werden im Original-Wortlaut eingebaut, sonst matcht das
  ATS nicht.
- Bei fehlender Sprachfassung stillschweigend die falsche verwenden. Interaktiv erst fragen, im
  Hintergrundlauf den Sprachbruch ausdrücklich melden.
- Einen Text-Run ohne explizite Schriftart und -größe aus der Stilkarte neu erzeugen. Das erzeugt stille
  Calibri-11-Rückfälle und den Schriften-Flickenteppich.
- Eine `.docx` abliefern, die das Typografie-Audit (4c) nicht bestanden hat oder deren Bildanzahl vom
  Original abweicht (4d).
- Das Foto oder andere eingebettete Objekte entfernen oder verlieren. Es werden nur Texte geändert.
- Eine ATS-Datei strukturell umbauen oder ihr Layout "optimieren". Hier wird nur Text eingebaut.
- Einen HTML-Bericht selbst gestalten oder einen ATS-Score nennen. Beides liegt bei `cv-match` und
  `cv-erstellen`.
- Eine Datei außerhalb der freigegebenen Ordner ablegen.
- Im Hintergrundlauf eine Rückfrage stellen und damit ohne Ergebnis enden.

## Referenzdateien

- `references/xyz-formula.md` – die XYZ-Logik mit Vorher/Nachher-Beispielen (erfundene Zahlen), Keyword-
  Integrationsmustern und der wahrheitstreuen Entschärfung typischer Red Flags.
