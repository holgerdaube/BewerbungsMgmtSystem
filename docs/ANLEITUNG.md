# Anleitung — So arbeitest du mit dem Bewerbungs-Management-System

> **Was ist neu?** Was sich von Version zu Version ändert, steht unter **📖 Dokumentation** in der
> Seitenleiste, im Reiter „Version“. Im Reiter „Funktionen“ findest du eine kurze Übersicht dessen,
> was das BMS kann.

Ein Cockpit für deine Jobsuche. Grundprinzip: **das System findet, bewertet und bereitet vor —
du entscheidest.** Es bewirbt sich nie automatisch und verschickt nichts ohne dein Zutun.

Zwei Bausteine greifen ineinander:
- **Die Skills** = der Motor: suchen, bewerten, CV anpassen, Gmail prüfen. Du startest sie heute meist
  per Knopfdruck direkt in der App (läuft headless im Hintergrund) — der klassische Weg über eine
  Claude-Session (Auslöser-Satz tippen) funktioniert bei jedem Skill weiterhin als Alternative.
- **Die Web-App** (http://localhost:8000) = das Cockpit: sichten, entscheiden, verwalten, exportieren
  — und der Ort, an dem du Skill-Läufe startest und im Task-Center verfolgst.
Beide arbeiten auf **einer** zentralen Datenbank.

---

## 1. Starten
Doppelklick auf **`start.command`** → die App öffnet unter http://localhost:8000.

**Vom Handy/Tablet nutzen (eigenes WLAN):** stattdessen **`start_lan.command`** doppelklicken —
das Terminal zeigt dir die Adresse fürs Handy (z. B. `http://<dein-mac>.local:8000`). Die Ansichten
sind mobil-tauglich (Navigation oben, Tabellen seitlich wischbar).
⚠️ Kein Login-Schutz — nur im eigenen, vertrauten WLAN verwenden; `start.command` bleibt der Standard (nur dieser Mac).

Öffne das BMS auf dem Handy unter einer der Adressen, die das Terminal anzeigt: dem `.local`-Namen
oder der IP-Adresse. Unter anderen Namen, etwa einem, den dein Router vergibt
(`mein-mac.fritz.box`), antwortet es mit „Adresse nicht freigegeben“. Das verhindert, dass eine
fremde Webseite über einen umgeleiteten Namen an deine Daten kommt. Brauchst du einen solchen
Namen trotzdem, starte im Terminal aus dem BMS-Ordner mit
`BMS_HOSTS=mein-mac.fritz.box ./start_lan.command` (mehrere Namen mit Komma trennen). Per
Doppelklick lässt sich die Freigabe nicht mitgeben.

**Beenden:** `Ctrl+C` im Terminal-Fenster, das beim Start aufgegangen ist. Ist das Fenster
weg oder reagiert nicht mehr, hilft Doppelklick auf **`stop.command`** (Windows:
`stop_windows.bat`). Das Skript fragt vorher nach, wenn gerade Läufe aktiv oder eingereiht
sind — ein Stopp mittendrin bricht sie ab, und eine laufende Beirats-Debatte ist danach
verloren. Die App muss übrigens nicht laufen, damit nichts verloren geht: Alles steht in der
Datenbank, ein späterer Start zeigt denselben Stand.

### Beim allerersten Start: Beispieldaten

Eine frische Installation startet nicht leer, sondern mit Beispieldaten. **Entferne sie, bevor du
eigene Daten einträgst.** Die Beispieldaten gehören zu **Birne Helene**, einer erfundenen Person:
Postbote mit fünf Jahren Erfahrung in der Paketzustellung. So kannst du alles ausprobieren, bevor
deine eigenen Daten drin sind. Dazu gehören sechs Firmen, fünf Stellen (je eine im Status Neu,
Prüfen, Beworben, Interview und Absage), drei Bewerbungen, fünf Mails, ein Gesprächstermin drei
Tage nach dem ersten Start, eine Ansprechperson, ein Netzwerk-Kontakt, ein Profil mit Fähigkeiten
und Werdegang, die Profil-Datei `config/profil.md` und ein deutscher Basis-Lebenslauf. Eine der
Mails hat keine Stelle: An ihr probierst du in der Inbox „Stelle zuordnen“ und „Archivieren“ aus.
Suchpläne, Zielfirmen und Headhunter legen die Beispieldaten nicht an, und Firmen wie Stellen
haben keine Webadresse. Ein KI-Lauf an einer Beispielstelle bringt deshalb nichts, die Firma ist
erfunden. Der Beworben-Check im Tageslauf lässt die Beispielstellen von sich aus weg.

Nur der allererste Start legt Beispieldaten an. Eine bestehende Installation und ein Update
bekommen keine, und nach dem Entfernen kommen sie nie wieder. Solange sie da sind, steht auf dem
Dashboard ein amberfarbener Hinweis, und die Seitenleiste zeigt „Birne Helene“ als deinen Namen.

**So entfernst du sie:** Öffne die **Einstellungen**, die Karte „Beispieldaten“ steht ganz oben auf
der Seite. Klicke auf „Beispieldaten entfernen“ und bestätige mit „Ja, entfernen“. Vorher
legt das BMS eine Sicherung deiner Datenbank an, im Ordner `data/backups/auto`, in dem auch „Jetzt
sichern“ ablegt. Scheitert die Sicherung, bleibt alles unverändert, und die Karte nennt den Grund.
Danach gilt:
- Gelöscht werden nur die Beispieldaten und was an den Beispielstellen hängt: Ansprechpersonen,
  Bewerbungen, Gespräche, Notizen & Verlauf, Chat, Transkripte, angepasste Lebensläufe und Dateien.
  Was du selbst angelegt hast, bleibt. Dateien daraus, etwa Berichte und Lebensläufe, die du an
  einer Beispielstelle erzeugt hast, wandern in den Papierkorb `data/papierkorb/`.
- Mails, die du einer Beispielstelle zugeordnet hast, bleiben als Mails ohne Stelle erhalten.
  KI-Läufe an einer Beispielstelle bleiben mit ihren Kosten im Task-Center stehen, nur der Verweis
  auf die Stelle entfällt. Läuft gerade ein KI-Lauf an einer Beispielstelle, lehnt das BMS das
  Entfernen ab und bittet dich, den Lauf abzuwarten.
- Die Profil-Datei `config/profil.md` und der Basis-Lebenslauf wandern ebenfalls in den Papierkorb,
  aber nur, wenn du sie nicht verändert hast. Eine eigene Fassung bleibt stehen, und die Karte
  nennt sie dir. Die Positionierung im Profil wird nur geleert, solange noch der Beispieltext darin
  steht.
- In der Seitenleiste steht danach „Bewerber“, bis du auf der Profil-Seite in der Karte
  „Identität und Suchstrategie“ deinen Namen speicherst.

**Reihenfolge bei der Einrichtung:** Erst die Beispieldaten entfernen, dann die Karte „Identität
und Suchstrategie“ ausfüllen und den Basis-CV hochladen (beides im Abschnitt „Profil“ weiter unten,
Einzelheiten in `BMS_Install_MAC.md` bzw. `BMS_Install_Windows.md`, Abschnitt „Einrichten: Das
BMS lernt Sie kennen“), danach erst den LinkedIn-Import. Der Import füllt nur
Leeres, mit den Beispieldaten im Profil übernähme er deshalb deine Positionierung nicht. Hast du dein
Profil schon gespeichert oder `config/profil.md` von Hand bearbeitet, bevor du die Beispieldaten
entfernst, erkennt das BMS die Datei als deine eigene und lässt sie stehen. Gehe die Karte dann
einmal ganz durch: Name, Anschrift, Kontakt, Kurzprofil, Zielrolle und Rahmenbedingungen sollen von
dir sein, nichts mehr von Birne Helene.

---

## 2. Der Motor — die Skills
Zwei gleichwertige Wege, einen Skill zu starten:
1. **Als Button in der App** — Review (Jobsuche & Sweeps), Job-Detail („Unterlagen erstellen"),
   Einstellungen (Coach-Site) oder der ☀️-Tageslauf-Button in der Seitenleiste starten den Lauf
   direkt; er läuft headless im Hintergrund, Fortschritt/Log/Kosten siehst du live im Task-Center
   (Abschnitt 3). Wo verfügbar, bleibt daneben ein aufklappbares „Alternativ: in Claude-Session
   ausführen".
2. **Als Auslöser-Satz in einer Claude-Session** — du sagst sinngemäß einen der Sätze unten;
   funktioniert bei **jedem** Skill, auch denen (noch) ohne eigenen Button:

| Sag sinngemäß … | Skill | Was passiert |
|---|---|---|
| „**Tageslauf**" | `tageslauf` | Die komplette Kette an einem Stück: Jobsuche → Mail-Jobsuche → Zielfirmen-Sweep → Headhunter-Suche → Beworben-Check → Postfach-Check → Absagen-Analyse (einmal je Woche) → Ansichten-Refresh → Coach-Site-Update (non-fatal) + Morgen-Zusammenfassung. |
| „**such nach neuen Stellen**" | `jobsuche` | Durchsucht Portale → dedupliziert → bewertet den Zielstellen-Fit 1–5 → legt Treffer als **„Neu"** an. |
| „**Mail-Jobsuche**" | `mail-jobsuche` | Verarbeitet LinkedIn- u. a. Job-Alert-Mails aus dem Postfach zu neuen Stellen (eigener Bewertungs-/Dedup-Durchlauf). |
| „**Zielfirmen-Sweep**" | `zielfirmen-sweep` | Prüft rotierend 12 Zielfirmen-Karriereseiten (alle ~6 Läufe einmal durch) auf neue Stellen. |
| „**Headhunter-Suche**" | `headhunter-suche` | Prüft rotierend 15 Headhunter-Webseiten auf passende (auch vertrauliche) Mandate. |
| „**Beworben-Check ausführen**" | `beworben-check` | Prüft wöchentlich alle laufenden Bewerbungen (Beworben/Interview), ob die Stelle noch ausgeschrieben ist (mit Karriereseiten-Fallback) — ändert nie den Bewerbungsstatus, nur den Verfügbarkeitshinweis. |
| „**Absagen-Analyse**" | `absagen-analyse` | Wertet alle Absagen und unbeantworteten Bewerbungen aus (Lost-Order-Analyse) → Muster-Bericht. Läuft einmal je Woche im Tageslauf; von Hand über das Dashboard („Absagen-Analyse neu erstellen“). Nur ein Start von Hand ersetzt die Empirie-Zeilen in deinem Profil, der Wochenlauf schreibt seinen Vorschlag nur in den Bericht. |
| „**prüf mein Postfach**" | `email-check` | Bewerbungs-Mails der letzten 24–36h → zuordnen, klassifizieren, Antwortzeiten, Kontakte, Status. |
| „**Firma prüfen für Job \<id\>**" | `firma-pruefen` | **Schritt 1:** Geschäftsmodell, Markt, **Einfluss der Rolle** → Company-Fit-Dashboard. |
| „**CV-Match für Job \<id\>**" | `cv-match` | **Schritt 2a (erst nach Schritt 1):** Match-Dashboard + angepasster CV-Entwurf (DE/EN), am Job-Detail bearbeitbar. |
| „**CV erstellen für Job \<id\>**" | `cv-erstellen` | **Schritt 2b:** aus dem (ggf. editierten) Entwurf Word + PDF + ATS-Scan erzeugen. |
| „**Anschreiben für Job \<id\>**" | `anschreiben-erstellen` | Firmenspezifisches Anschreiben (DE/EN) mit Direktansprache → `.docx` + PDF. |
| „**Profil einlesen von \<URL\>**" | `profil-einlesen` | Liest ein LinkedIn-Profil best-effort ein (Profil-Seite) — meldet die Login-Wall ehrlich, statt zu raten. |
| „**Deep-Dive für Job \<id\>**" | `job-deepdive` | Beides in einem Rutsch (Firma + CV) — Standard sind aber die zwei getrennten Schritte oben. |

---

## 3. Die Bereiche der App

Links steht die **Seitenleiste**. Oben trägt sie den Namen des Programms, „Bewerbungs-Management-System“,
und darunter deinen Namen. Den liest das BMS aus deinem Profil (Karte „Identität und Suchstrategie“,
gespeichert in `config/profil.md`), fehlt der Name, steht dort „Bewerber“. Der Browser-Tab trägt
denselben Namen. Ganz unten steht die
installierte Version, etwa „Version 1.1.3“. Auf einem schmalen Bildschirm wie dem Handy rückt die
Leiste nach oben und die Versionszeile entfällt, die Version zeigen dann die Einstellungen und die
Dokumentation. Dazwischen liegen die Bereiche dieses Abschnitts.

### 📊 Dashboard
Dein Überblick: Kennzahlen (Stellen, Top-Zielstellen ≥4, Bewerbungen, E-Mails, Antworten, Ø-Antwortzeit,
**Antwortquote**), der **Pipeline-Funnel** (Neu → Prüfen → Beworben → … → Absage) und Verteilungen
(nach Status, Zielstellen-Fit, Situation, Portal). Oben rechts: **Excel-Export** und **Tages-Digest**.
Solange Beispieldaten da sind, steht oben ein amberfarbener Hinweis darauf. Ein Klick führt zur Karte
„Beispieldaten“ in den Einstellungen.

### 🔍 Suche
Volltextsuche über das gesamte System — Firmenname, Ort, Stellenbeschreibung, Company-Fit-Dashboard,
Transkripte, Debriefs, Briefings, Notizen/Verlauf. Ergebnis ist immer eine **Stelle**, mit bis zu drei
Fundstellen-Snippets samt Quelle-Badge und Hervorhebung. Der Index baut sich täglich im Tageslauf neu
(„Index-Stand" unten sichtbar) oder auf Knopfdruck („↻ Index aktualisieren"). **Grenze:** CV- und
Anschreiben-Inhalte (`.docx`) sowie die Netzwerk-Listen werden bewusst NICHT durchsucht.

### ✨ Neu / Review — dein Triage-Posteingang
Oben die Karte **„Neue Jobsuche starten"**: **Jobsuche (WebSearch)** und **Jobsuche + Apify**
(nutzt zusätzlich die Portal-Scraper, kostet Apify-Credits) in der ersten Reihe; darunter
**Zielfirmen-Sweep**, **Headhunter-Suche**, **Beworben-Check** und **E-Mail-Check** — alle vier
kostenlos. Jeder Button startet seinen Lauf direkt in der App, headless im Hintergrund; „Letzter
Suchlauf" zeigt Zeitpunkt und Ergebnis des jüngsten — auch wenn er aus dem Tageslauf kam.
**Beworben-Check** prüft wöchentlich für alle laufenden Bewerbungen (Beworben/Interview), ob die
Stelle noch ausgeschrieben ist: erst über die Original-URL (mit demselben Abruf wie die Suchläufe,
bei Drosselung mit Wiederholung; antwortet ein Portal gar nicht, bleibt die Stelle „unklar“ statt
„offline“), bei geschlossenem Portal über die Firmen-Karriereseite. Er schreibt nur den
**Verfügbarkeitshinweis** zurück (Eckdaten, Dashboard-Kachel „Beworbene offline", ⛔-Badge in der
Stellen-Liste); **den Bewerbungsstatus ändert er nie**. **E-Mail-Check** liest nur das Postfach
(Antworten, Absagen, Termine) und ordnet Mails den Bewerbungen zu, ohne eine neue Jobsuche
anzustoßen — derselbe Skill wie „prüf mein Postfach" oben, nur als Button.

Darunter die neuen Treffer aus der Jobsuche (Status „Neu"). Pro Karte:
- **Öffnen ↗** — Original-Stellenanzeige ansehen (ändert nichts).
- **✓ Annehmen** — Status → **„Prüfen"**. Wandert in die aktive Pipeline. Nächster Schritt: Deep-Dive.
- **✕ Verwerfen** — Status → **„Kein Match"**. Wird archiviert, **bleibt aber in der DB** → derselbe
  Treffer taucht bei künftigen Suchen **nicht wieder** als „Neu" auf (Dedup).
Beides ist reine interne Sortierung, **nichts wird gelöscht oder verschickt**, alles ist reversibel.
Der Zähler-Badge zeigt, wie viele Treffer noch zu sichten sind.

### ⏰ Follow-ups — was heute dran ist
Sammelt alles mit Fälligkeit an einem Ort. **Gesetzt** werden die Termine woanders (Fälligkeitsdatum
im Job-Detail unter „Nächste Schritte & Follow-up", „Fällig am" beim Netzwerk-Kontakt) — hier laufen
sie nur zusammen. Vier Blöcke:
- **🎙️ Anstehende Gespräche** — geplante Interviews mit Runde/Art und Interviewer. **„📋 Briefing"**
  öffnet die Vorbereitung (falls erzeugt), **„🗺️ Route"** die Google-Maps-Anfahrt von deiner Adresse
  zum Einsatzort (bei Remote-Stellen ausgeblendet). Fehlt der Termin, steht dort ein bernsteinfarbenes
  **„Termin fehlt — im Job-Detail setzen"**.
- **🔴 Stellen — überfällig & heute** · **⏳ Stellen — anstehend** — je Zeile Score, Firma, Titel,
  Status, nächster Schritt und Fälligkeitstext („heute fällig", „3 Tage überfällig", „in 5 Tagen").
  Rot & fett = überfällig; **„überfällig" schließt heute mit ein**.
- **🤝 Netzwerk-Aktionen** — fällige Kontakt-Aktionen, überfällige zuerst (Klick führt auf `/netzwerk`).

Der Chip **„✉️ Nachfass"** ⚠️ **startet nichts** — er kopiert dir nur den Auslöser
`Nachfass-Entwurf für Job <id>` in die Zwischenablage; senden musst du ihn in der Claude-Session.
Stellen in einem Endstatus (Absage, Kein Match, Nicht verfügbar, Beirat abgelehnt) erscheinen hier
nie, auch mit Datum nicht. Die Seite lädt **nicht** automatisch nach — nach Änderungen im Job-Detail
kurz neu laden.

### 📋 Pipeline — Kanban-Board
Alle aktiven Stellen als Karten in Spalten: **Neu · Prüfen · Beworben · Interview · Angebot · Absage**.
Karte per **Drag & Drop** in eine andere Spalte ziehen = Status ändern. Archivierte Stellen
(Kein Match / Nicht verfügbar / Geparkt) erscheinen hier nicht (Zähler „X archiviert" oben).

### 💼 Stellen & Job-Detail
**Stellen** = Tabelle aller Treffer mit Filtern (Status, Such-Tab, Score, Suche). Klick auf eine Zeile → **Job-Detail**:
- **Bewertung** (Warum passt es, mit Beleg), **Eckdaten** (Situation, Arbeitsmodell, Plan A/B/C, Gehalt …).
  Über **„✏️ Bearbeiten"** (rechts in der Eckdaten-Karte) kannst du **alle** dieser Felder manuell
  korrigieren oder nachtragen — z. B. Gehalt oder Original-URL — und mit „Speichern" übernehmen.
  **Achtung URL:** Änderst du die Original-URL von Hand, verschwindet das „✓ geprüft"-Badge (die
  Verifikation galt der alten Adresse); der nächste Prüf-Lauf setzt es für die neue URL wieder.
- **Status ändern** (Buttons) · **Nächste Schritte & Follow-up** · **Notizen & Verlauf** (zwischen Eckdaten
  und E-Mail-Verlauf — Status-/Follow-up-/Notizen-Änderungen protokollieren sich hier automatisch, du kannst
  zusätzlich frei Notizen eintragen) · **Kontakte** · **E-Mail-Verlauf** (aus dem Gmail-Check).
- **Stelle fragen (KI):** eigenes Chat-Fenster zwischen „Notizen & Verlauf" und „E-Mail-Verlauf" —
  deine Frage beantwortet die KI ausschließlich aus den vorliegenden Daten dieser Stelle
  (Company-Fit, Snapshot, Verlauf, Transkripte, Briefing), kein Web. Frage und Antwort bleiben als
  Chat-Verlauf stehen und landen zusätzlich in „Notizen & Verlauf". Läuft headless im Hintergrund
  („KI antwortet…" mit **„Abbrechen"** daneben); ein Neuladen der Seite verliert eine laufende
  Frage nicht — sie wird automatisch wiedergefunden und der Abbrechen-Button erscheint wieder
  genau dort, wo du ihn brauchst.
- **Unterlagen erstellen** (Workflow-Karte, rechte Spalte): zwei nummerierte Schritte,
  **① Company-Fit prüfen** und **② CV-Match**, dazu zwei optionale Bausteine ohne Sperre:
  **Stelle prüfen (Beirat)** und **Anschreiben generieren**. Der CV-Match ist gesperrt (🔒), bis der
  Company-Fit vorliegt; erledigte Schritte sind ausgegraut (✓) mit „neu prüfen", „neu matchen" oder
  „neu erzeugen". Der **Beirat** lässt die Stelle von den Beiratsköpfen bewerten, am besten vor dem
  CV-Aufwand; fällt sein Votum rot aus, bietet die Karte direkt an, den Status auf
  **„Beirat abgelehnt"** zu setzen. Das Anschreiben nutzt den angepassten CV, sobald er fertig ist,
  sonst den Basis-CV. **„Bewerbungspaket"** startet Firma → CV-Match → CV erstellen am Stück, mit dem
  Haken **„mit Anschreiben"** auch das Anschreiben. Der Beirat gehört nicht dazu, er läuft direkt im
  Server statt als Agent-Task.
- **Zwischenschritt zum Mitreden:** Nach dem CV-Match entsteht zuerst nur ein **Entwurf**.
  Unter „Dateien & Dokumente" erscheint das Fenster **„CV-Entwurf bearbeiten"** — der komplette
  CV-Inhalt als ein großer Fließtext (eine Zeile = ein Absatz). Bullet-Zeilen darfst du frei ändern,
  ergänzen und löschen; Abschnitts-Überschriften sind gesperrt, damit die fertige `.docx` ATS-tauglich
  bleibt. Erst wenn du zufrieden bist, erzeugt „**CV erstellen**" Word + PDF aus **deinem** Stand — und
  der ATS-Scan läuft danach auf dem finalen Dokument statt auf einem ungesehenen Entwurf. Der
  Scan zeigt zwei Zahlen: den **ATS-Score** (Optimierungsgrad: wie gut ist ehrlich Abdeckbares
  eingearbeitet) und die **Abdeckungsquote roh** (x von 15
  Anzeigen-Keywords, unabhängig davon, ob sie überhaupt wahrheitstreu abdeckbar sind). Nur der
  Score zählt fürs Ranking; die Roh-Quote ist ehrliche Fit-Info, kein Makel bei Stretch-Rollen.
- **Anschreiben bearbeiten:** Ein eigenes Textfenster mit dem Brieftext. „**Anschreiben
  speichern**" sichert deine Fassung, danach „**Word + PDF erzeugen**" (in dieser Reihenfolge — das
  Fenster weist dich darauf hin, wenn noch Ungespeichertes offen ist). Bei älteren Anschreiben ohne
  hinterlegten Text holt „**Text aus vorhandener .docx laden**" ihn einmalig herein.
- **Angepasster CV** (letzte Karte): zeigt nur die **Fakten** — Sprache (Deutsch/Englisch), **Match-** und
  **ATS-Score**, Datum. Die Dateien selbst liegen unter „Dateien & Dokumente".
- **Dateien & Dokumente**: alle **erzeugten** Artefakte (Company-Fit-Dashboard, CV `.docx`/`.pdf`, Match-/
  ATS-Dashboard, Anschreiben `.docx`/`.pdf`, Briefings, Transkript-Reports) erscheinen hier automatisch mit
  **„generiert"**-Badge (öffnen/laden) — neben deinen eigenen Uploads (Drag & Drop). Beide Arten sind über
  das 🗑-Icon löschbar (Papierkorb, s. Abschnitt 7) — beim Company-Fit-Eintrag warnt der Dialog, dass er
  für **alle** Stellen dieser Firma gilt.
- **Anzeige-Kopie:** Die Stellenanzeige wird schon bei der **Erfassung** gesichert
  (Jobsuche/Mail-Jobsuche/Zielfirmen-Sweep/Headhunter-Suche), nicht erst bei der Firma-Prüfung.
  Der Anzeigen-Snapshot taucht also direkt nach dem ersten Fund auf, mit einem
  Quellen-Hinweis im Kopf (grün = Original live abgerufen, amber = nur Metadaten, kein Text). Läuft
  später `firma-pruefen`, ersetzt dessen geprüfte Vollversion denselben Snapshot (kein zweites
  Dokument). Ältere Stellen ohne Snapshot lassen sich einmalig nachziehen:
  `cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.posting_snapshot backfill`.
- **Fehlender Anzeigentext:** Bremst ein Portal (meist LinkedIn mit „zu viele Anfragen") den Abruf,
  versucht das BMS es mehrmals mit Pausen. Gelingt es trotzdem nicht, kann ein Snapshot nur die
  Eckdaten enthalten, ohne den Text der Anzeige. Dann holt das BMS den Text **beim Start** von
  Firma-Prüfung, CV-Match, CV erstellen und Anschreiben nach. Das kann bei einem gebremsten Portal
  gut eine halbe Minute dauern; unter dem Knopf steht solange „Anzeigentext wird nachgeholt …".
  Klappt das Nachholen nicht, startet der Lauf **nicht** von selbst: Unter dem Knopf erscheint eine
  Rückfrage mit dem Grund (zum Beispiel „Die Anzeige ist nur mit Anmeldung sichtbar") und den
  Knöpfen **„Trotzdem starten"** und **„Abbrechen"**. Mit „Trotzdem starten" arbeitet der Lauf nur mit
  Titel und Firma der Stelle; der CV-Match vermerkt das im Dashboard als Red Flag, ein grünes
  Quellen-Badge gibt es dann nicht. Hat ein Portal nur gebremst, klappt ein späterer Versuch meist;
  dann wählst du „Abbrechen" und startest den Lauf später noch einmal. Stellen, deren
  Snapshot keinen Anzeigentext hat, kannst du auch gesammelt nachholen (neben `backfill`, das nur
  Stellen ganz **ohne** Snapshot anlegt):
  `cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.posting_snapshot nachholen`
  prüft alle aktiven Stellen (Neu, Prüfen, Beworben, Interview, Angebot) und holt fehlenden Text
  nach. Mit `--job-id <Nummer>` gilt der Befehl nur für eine Stelle, mit `--dry-run` zählt er nur,
  welche Stellen keinen Text haben, und ruft nichts ab. Der Text wird erst bei der nächsten
  Firma-Prüfung gegliedert; bis dahin zeigt der Snapshot oben den Hinweis „Anzeigentext am …
  nachgeholt".
- **Interviews & Gespräche → Transkripte:** ein Transkript kannst du per Text einfügen **oder per
  Datei hochladen** (`.txt`/`.md`/`.vtt` — Teams/Zoom-Untertitel-Export, Zeitstempel werden automatisch
  entfernt; max. 5 MB, kein `.docx`). In beiden Fällen entsteht sofort ein **Transkript-Report**
  („📄 Report öffnen") mit Kopf/Hinweis, dass der Debrief noch aussteht — rechts an der Transkript-Zeile
  siehst du nur noch eine 3–5-Sätze-Zusammenfassung plus Datum/Kontakt/Runde. „🧠 Auswerten" (Skill
  `gespraech-debrief`) ersetzt denselben Report durch die Vollversion mit Findings — der Dateiname
  bleibt stabil, es entsteht kein zweites Dokument.
- **Runde direkt beim Transkript anlegen:** In der Zuordnungs-Auswahl steht neben den
  bereits erfassten Runden ein **„+ Neue Runde anlegen…"**. Damit musst du den Dialog nicht mehr
  verlassen, wenn das Gespräch noch nicht erfasst ist — Nummer und Art erscheinen als zwei kleine
  Felder (vorbelegt mit der nächsten freien Nummer), und die Runde entsteht erst beim Speichern.
  Gesprächspartner und Datum übernimmt sie aus dem Formular, der Status ist „Absolviert".
  Gesprächsarten sind HR-Screen, **Headhunter-Screen**, Fachgespräch, Hiring Manager, Panel, Final
  und Sonstiges — die Zahl der Runden ist nicht begrenzt. Das Feld **Gegenüber** (Recruiter /
  Hiring Manager / Fachbereich / Headhunter / Sonstige) füllt sich passend zur Art von selbst und
  bleibt änderbar; es ist die Größe, nach der die Gesamtprozess-Auswertung die Gespräche aufteilt.
- **Empfängerfreundliche Dateinamen:** CV = `CV_MaxMustermann_<Firma>_<Position>_DE|_EN`, Anschreiben =
  `CoverLetter_MaxMustermann_<Firma>_<Rolle>_DE|_EN` (Sprach-Suffix immer gesetzt) — beide als `.docx`
  UND `.pdf`. Firma und Rolle erscheinen gekürzt (Abschnitt 6). Die PDF-Erzeugung läuft über **LibreOffice** headless (kein Fenster, keine macOS-Freigabe).
- **Sauberer Satz:** In jeder erzeugten CV-Datei beginnt ein Abschnitt, der sonst über zwei Seiten
  zerrissen würde, automatisch auf der nächsten Seite, und in der **Fußzeile** steht
  „Max Mustermann · Seite X von Y". Das gilt für alle künftig erzeugten Dokumente, ohne dass du etwas tun musst.

### 📧 Inbox
Alle bewerbungsrelevanten E-Mails: **Kategorie** (Eingangsbestätigung/Einladung/Absage/Rückfrage/Angebot),
Richtung (↙ ein / ↗ aus), zugeordnete Firma/Stelle, **Antwortzeit** und **„zu beantworten"-Flag**.
Kopf zeigt Ø-Antwortzeit. Gmail wird nur **gelesen** — nichts wird gesendet oder gelabelt.

**E-Mails ohne Stelle zuordnen:** Findet der Gmail-Check keine Firma/Stelle (z. B. eine
Absage ohne erkennbaren Bezug), landet die Mail trotzdem in der Inbox — mit Badge **„⚠ Ohne
Stelle"** und eigener KPI-Kachel oben (klickbar = filtert darauf). Zeile aufklappen → **„📎 Stelle
zuordnen"** öffnet eine Suche gegen den Bestand; Treffer anklicken ordnet zu (inkl. rückwirkender
Antwortzeit-Berechnung). Gibt es die Stelle noch nicht: **„+ Stelle anlegen"** öffnet „Neue Stelle"
mit Firma/Notiz aus der Mail vorbefüllt. Nach dem Zuordnen schlägt das System bei Absage/Angebot/
Einladung den passenden Job-Status vor — geändert wird nur, wenn du bestätigst. Über **„🔓
Zuordnung lösen"** lässt sich eine Fehlzuordnung jederzeit rückgängig machen.

**E-Mails ohne Stelle archivieren:** Braucht eine Mail ohne Stelle keine Zuordnung mehr,
etwa eine Werbe- oder Info-Mail ohne Bewerbungsbezug, blendest du sie mit **„Archivieren"** aus
(Zeile unter dem Badge „⚠ Ohne Stelle", oder aufgeklappt unter dem Zuordnen-Feld: **„🗄
Archivieren"**). Es gibt keine Rückfrage. Über das Archiv lässt sich die Aktion jederzeit
rückgängig machen. Archivierte Mails verschwinden aus der Inbox, aus der Mail-Zahl im Dashboard
und aus dem Tages-Digest. **„🗄 Archiv"** unter der Tabelle zeigt sie weiterhin, mit **„↩
Zurückholen"** je Zeile. In Gmail bleibt dabei alles unverändert, nichts wird dort gelöscht oder
verschoben. Zugeordnete Mails lassen sich nicht archivieren. Löse zuerst die Zuordnung. Ordnest
du eine archivierte Mail nachträglich einer Stelle zu, holt das System sie automatisch aus dem
Archiv zurück in die Inbox.

### 🌐 Netzwerk
Drei Tabs, alle **in der App pflegbar**: **Zielfirmen** (mit Tier/Szenario, „+ Zielfirma anlegen",
Zeile anklicken = volles Bearbeiten), **Headhunter** („+ Headhunter anlegen", Webseite-Feld, Zeile
anklicken = bearbeiten), **Netzwerk-Kontakte** (anlegen/editieren, Fälligkeits-Pill bei überfälliger
nächster Aktion). Die Felder „Karriere-Check"/gecachte URL bei Zielfirmen und Headhuntern pflegen
die Sweep-Skills automatisch, von Hand sind sie nicht editierbar. Im Inline-Edit-Formular jeder der
drei Listen gibt es einen **🗑 Löschen**-Button: Der Eintrag verschwindet sofort aus allen Listen
und wird von Sweeps und Suchen nicht mehr geprüft. Gelöschte Einträge sammelt der **🗑 Papierkorb**
unter der jeweiligen Liste, dort holst du sie mit **„↩ Wiederherstellen"** zurück. Legst du einen
gelöschten Eintrag mit denselben Angaben neu an, wird der alte automatisch reaktiviert.

#### Listen aus einer Datei importieren

In allen drei Reitern steht neben dem Anlege-Knopf **„⇪ Aus Datei importieren“**. Damit legst du viele
Einträge auf einmal an, aus einer CSV- oder Excel-Datei. Du kannst das jederzeit wiederholen, auch mit
einer Datei, in der schon vorhandene Einträge stehen.

**Ablauf:**
1. Den Reiter öffnen und **„⇪ Aus Datei importieren“** anklicken. Unter den Knöpfen öffnet sich der
   Importbereich.
2. **„Datei auswählen“** anklicken und die Datei laden. Das BMS liest sie sofort und zeigt eine
   **Vorschau**. Dabei wird nichts gespeichert.
3. Die Vorschau prüfen: erkannte Spalten, Zähler und die Tabelle der Zeilen (Erklärung weiter unten).
4. **„Importieren“** anklicken. Der Knopf nennt, was passiert, etwa „Importieren (12 neu, 3 ergänzen)“.
   Das BMS legt zuerst eine Sicherung an und schreibt dann alle Zeilen in einem Zug. Danach steht im
   Importbereich „✓ 12 angelegt, 3 ergänzt“, und die Liste zeigt die neuen Einträge. **„Abbrechen“**
   schließt den Importbereich, ohne etwas zu ändern.

**Dateien und Vorlagen:** Das BMS liest `.csv`, `.txt` und `.xlsx`. Bei CSV erkennt es Trennzeichen
(Semikolon, Komma, Tabulator) und Zeichensatz selbst. Im Importbereich lädst du unter **„Vorlage: CSV ·
Excel“** eine Vorlage für die jeweilige Liste herunter. Sie enthält nur die Kopfzeile, die Excel-Vorlage
zusätzlich ein zweites Blatt „Hinweise“ mit den erlaubten Werten und Datumsformaten je Spalte. Nötig ist
die Vorlage nicht: Das BMS erkennt die Spalten an ihrer Überschrift, auf Deutsch oder Englisch, in
beliebiger Reihenfolge und ohne Rücksicht auf Groß- und Kleinschreibung. „Firma“, „Company“ und „firma“
sind dieselbe Spalte. Spalten, die das BMS nicht kennt, überspringt es und zeigt sie in der Vorschau
unter „Nicht verwendete Spalten“.

Pflicht ist je Zeile nur eine Angabe: bei Zielfirmen die Firma, bei Headhuntern die Firma oder der
Ansprechpartner, bei Netzwerk-Kontakten der Name (oder Vorname und Nachname in zwei Spalten).

Auch der **Excel-Export** des BMS (Dashboard) lässt sich wieder einlesen. Hat eine Excel-Datei mehrere
Blätter, liest das BMS das Blatt, das so heißt wie die Liste („Zielfirmen“, „Headhunter“, „Netzwerk“),
sonst das erste. Welches Blatt es genommen hat, steht in der Vorschau.

**Kontakte aus LinkedIn:** Im Reiter „Netzwerk-Kontakte“ kannst du die Datei `Connections.csv` aus deinem
LinkedIn-Datenexport laden. LinkedIn liefert den Export als ZIP-Archiv, das du vorher entpackst. Wie du
ihn beantragst, steht weiter unten im Abschnitt „Profil“. Das BMS erkennt die Datei an ihren
Spaltenüberschriften („First Name“, „Last Name“, „Connected On“) und nennt sie in der Vorschau
„LinkedIn-Export“. Übernommen werden der Name, das Unternehmen („Company“), die Rolle („Position“) und
der Kanal „LinkedIn“. Profil-Adresse, E-Mail-Adresse (soweit LinkedIn sie liefert) und Verbindungsdatum
stehen danach in den Notizen, etwa „LinkedIn: https://www.linkedin.com/in/jana-beispiel · E-Mail:
jana@beispiel.de · verbunden seit 12.09.2023“. Beziehung, letzter Kontakt, Priorität und nächste Aktion
bleiben leer.

Ein LinkedIn-Export enthält alle deine Verbindungen. Die Liste „Netzwerk-Kontakte“ ist für Menschen
gedacht, die du aktiv pflegst. Öffne die Datei deshalb vor dem Import in Excel und lösche die Zeilen, die
du dort nicht haben willst. Lass die Kopfzeile stehen. Speichern kannst du sie als CSV oder als
Excel-Arbeitsmappe (`.xlsx`), das BMS erkennt den LinkedIn-Export in beiden Fällen.

**Die Vorschau** zeigt, was der Import tun würde. Fünf Zähler fassen es zusammen:
- **Neu**: Der Eintrag fehlt in der Liste und wird angelegt.
- **Ergänzt**: Der Eintrag ist schon da, und die Datei bringt für mindestens ein leeres Feld einen Wert.
  Die Tabelle nennt die Felder.
- **Unverändert**: Der Eintrag ist schon da, die Datei bringt nichts Neues.
- **Gelöscht, übersprungen**: Du hast den Eintrag in der App gelöscht. Er bleibt gelöscht.
- **Fehler**: Die Zeile lässt sich nicht importieren, etwa weil die Firma oder der Name fehlt. Die
  Tabelle nennt den Grund.

Die Tabelle zeigt je Zeile die Zeilennummer in der Datei (die Kopfzeile zählt mit, wie in Excel), den
Eintrag, die Aktion und einen Hinweis. Fehler und gelöschte Einträge stehen oben und werden immer
gezeigt, von den übrigen Zeilen höchstens die ersten 100. Über der Tabelle stehen Hinweise des BMS, etwa
zum LinkedIn-Export oder zum gelesenen Excel-Blatt.

**Diese Regeln gelten immer:**
- **Nur leere Felder werden ergänzt.** Was in der App schon in einem Feld steht, überschreibt der Import
  nie. Eine leere Zelle in der Datei löscht nichts.
- **Als derselbe Eintrag gilt:** bei Zielfirmen der Firmenname, bei Headhuntern Firma und Ansprechpartner
  zusammen, bei Netzwerk-Kontakten Name und Unternehmen zusammen. Groß- und Kleinschreibung, Leerzeichen
  und Sonderzeichen zählen nicht. Sonst ist der Abgleich wörtlich: „Muster“ und „Muster GmbH“ sind zwei
  Einträge.
- **In der App gelöschte Einträge bleiben gelöscht.** Der Import legt sie nicht neu an. Im
  **🗑 Papierkorb** unter der Liste holst du sie mit „↩ Wiederherstellen“ zurück.
- **Zeilen mit Fehlern werden nicht importiert**, alle anderen schon. Korrigierst du die Datei und lädst
  sie erneut, zählen die bereits importierten Zeilen als „Unverändert“, und die korrigierten kommen dazu.
- **Steht ein Eintrag mehrmals in der Datei,** zählt die erste Zeile. Spätere Zeilen füllen höchstens
  noch leere Felder, die Tabelle weist darauf hin („Doppelt in der Datei, siehe Zeile 7“).
- **Keine automatische Fälligkeit.** Legst du einen Kontakt mit „+ Kontakt anlegen“ ohne Termin an,
  trägt das BMS „Fällig am“ zehn Werktage später ein. Der Import tut das nicht, sonst stünden nach einem
  großen Import alle neuen Kontakte am selben Tag unter den Follow-ups. Übernommen wird nur ein Datum, das
  in der Spalte „Fällig am“ steht. Ein Datum dort, das das BMS nicht lesen kann, bleibt leer und wird in
  der Tabelle gemeldet.
- Schreibweisen gleicht das BMS an, wo es eindeutig ist: „high“ wird zu „Hoch“, „email“ zu „E-Mail“,
  „Tier 1“ zu „1“, ein kleines „a“ beim Szenario zu „A“. Daten liest es als `TT.MM.JJJJ` oder
  `JJJJ-MM-TT`.

**Sicherung:** Gibt es etwas zu schreiben, legt das BMS vorher eine Sicherung deiner Datenbank an, im
Ordner `data/backups/auto`, in dem auch „Jetzt sichern“ ablegt. Ihren Namen zeigt der Importbereich nach
dem Import. Scheitert die Sicherung, wird nichts importiert, und der Importbereich nennt den Grund. Läuft
gerade eine Sicherung, bittet das BMS dich, es gleich noch einmal zu versuchen. Der Import schreibt alles
oder nichts: Geht beim Schreiben etwas schief, bleibt die Liste unverändert. Gibt es nichts zu schreiben,
weil alle Zeilen schon vorhanden oder fehlerhaft sind, ist „Importieren“ gesperrt, und es entsteht keine
Sicherung.

**Grenzen:** Eine Datei darf höchstens 5 MB groß sein und höchstens 5.000 Zeilen mit Daten haben
(Kopfzeile und leere Zeilen zählen nicht). Größere Listen teilst du auf mehrere Dateien auf. Das alte
Excel-Format `.xls` liest das BMS nicht: Speichere die Datei in Excel vorher als `.xlsx` oder `.csv`. Die
Kopfzeile muss die erste Zeile mit Inhalt sein, beim LinkedIn-Export die erste Zeile mit „First Name“ und
„Last Name“.

**Folgen für die Suchläufe:** Importierte Zielfirmen und Headhunter mit einer Webseite nehmen
Zielfirmen-Sweep und Headhunter-Suche in ihre Rotation auf. Weil sie noch nie geprüft wurden, kommen sie
zuerst dran: Der Zielfirmen-Sweep prüft 12 Zielfirmen pro Durchgang, die Headhunter-Suche 15 Headhunter.
Eine lange Liste braucht deshalb entsprechend viele Durchgänge, bis alle Einträge einmal geprüft sind.

### ⚙️ Task-Center — das Protokoll aller Hintergrund-Läufe
Hier siehst du jeden Skill-Lauf, den die App im Hintergrund („headless") ausführt — **gestartet wird
hier nichts**, das passiert in **Review** (Jobsuche & Sweeps), im **Job-Detail** (Unterlagen-Workflow,
Stelle fragen), in den **Einstellungen** (Coach-Site) oder über den **☀️-Tageslauf-Button** (Seitenleiste,
auf jeder Seite erreichbar).
Oben fünf Kacheln: **Läufe gesamt · Aktiv · Fehlgeschlagen · Heute verbraucht · Kosten gesamt**.
Darunter die Filter **„Alle · Aktiv · Fehlgeschlagen"** und die Tabelle (Aufgabe, Stelle, Status,
Gestartet, Dauer, Kosten).

Den Zustand erkennst du am Status-Chip: `wartet` · `läuft` · `fertig` · `fehlgeschlagen` (Fehlertext
steht rot unter dem Namen) · `abgebrochen`. Je Zeile gibt es:
- **„Log"** — klappt die Live-Ausgabe des Laufs auf (benutzte Werkzeuge, Subagenten, Ergebnis). Das
  Log aktualisiert sich alle 3 Sekunden — du kannst einem Lauf also **live zuschauen**.
- **„Abbrechen"** — nur bei `wartet`/`läuft`.
- **„Erneut"** — ⚠️ startet einen **komplett neuen Lauf** desselben Skills (setzt den alten nicht
  fort); bei einer Kette nur diesen einen Schritt.

Solange etwas aktiv ist, frischt sich die Liste alle 3 Sekunden selbst auf. **Leitplanken:** max. 2
Läufe parallel, Notbremse ~$15 je Lauf, $100 und 100 Läufe pro Tag; ein zweiter Lauf desselben Skills
für dieselbe Stelle wird abgelehnt. ⚠️ „Läufe gesamt" und „Kosten gesamt" beziehen sich auf die
**letzten 100 Läufe** — nur „Heute verbraucht" ist eine echte Tagesabrechnung.

### 💶 Budget — Kosten sehen und deckeln
Zwei Dinge in einem: Überblick über alle bezahlten Dienste **und** das Steuerpult, mit dem die App
sich selbst am Geldausgeben hindert. Oben **Heute · Dieser Monat · Jahres-Prognose · Fixkosten/Monat**,
rechts **„🔄 Verbrauch syncen"** (holt den Apify-Verbrauch per API; Abos wie Claude/Hedy kommen aus
`config/budgets.yaml` und werden **nie** blockiert).

In der Tabelle **Dienste** zeigt das Status-Badge **„im Rahmen" · „⚠ ≥ 80 %" · „über Limit" ·
„pausiert"**. Unter **Budget-Steuerung** stellst du je Verbrauchs-Dienst ein:
- **„Dienst aktiv"** abwählen = pausiert → **alle** Aufrufe werden verweigert, unabhängig vom Limit.
- **Tageslimit ($)** und **Monatslimit ($)** — leer lassen heißt „kein Limit".
- **„hart"** / **„weich"**: hart = Aufrufe werden **blockiert**, weich = läuft trotzdem, nur Warnung.
  Geprüft wird vor jedem kostenpflichtigen Aufruf (erst Tages-, dann Monatslimit).

⚠️ Zwei Stolpersteine: Das Tageslimit darf **nicht über** dem Monatslimit liegen (sonst Fehlermeldung),
und die Startwerte sind mit $0,50/Tag knapp — das blockiert schnell. Außerdem ist das hier **nicht**
das Tagesbudget des Task-Centers: die Agenten-Leitplanken ($15/Lauf, $100/Tag) sind Umgebungsvariablen
und hier nicht editierbar. Ausgaben außerhalb der App sieht sie erst nach dem Sync und kann sie nicht
verhindern.

### 🏛️ Beirat: freie Fragen an die sieben Köpfe
Eigener Menüpunkt **🏛️ Beirat** in der Seitenleiste, direkt unter Netzwerk. Für die Frage „soll ich
mich auf *diese Stelle* bewerben?" nimmst du den **Beirats-Check im Job-Detail** (optionaler Baustein
„Stelle prüfen (Beirat)" in der Karte „Unterlagen erstellen", mit Abstimmung und Dashboard). Diese
Seite ist für **freie** Fragen ohne Stellenbezug (z. B. „Wie erkläre ich meinen Wechsel?").

Unter **Neue Debatte** gibst du **Thema/Frage** (Pflicht) und optional Kontext ein, wählst
**Mindest-Beiträge** (6/10/20/30), den **Motor** (Claude über dein Abo, kein Key nötig; OpenAI nur
mit Key) und lässt entweder den Vorsitz die Köpfe selbst wählen (Haken gesetzt, dort steht sein Name)
oder pickst mindestens zwei Köpfe. Wer den Vorsitz hat, legst du in den **Einstellungen** bei der
Besetzung des Beirats fest. **„▶ Debatte starten"** startet die Debatte live: Der Vorsitz ruft die
Köpfe namentlich auf, die Beiträge erscheinen Wort für Wort, am Ende steht die **📋 Synthese**.
**„■ Stoppen (→ Synthese)"** beendet sanft: der laufende Beitrag wird fertiggeschrieben, dann folgt
direkt die Synthese.
**Frühere Debatten** gibt den gespeicherten Stand wieder — das rechnet nichts neu und kostet nichts.

⚠️ Es kann immer nur **eine** Debatte gleichzeitig laufen (auch der Stellen-Check aus dem Job-Detail
zählt dazu). Läufe kosten Geld (Notbremse $15); **OpenAI-Kosten werden nicht erfasst**, die
Budget-Kontrolle greift dort also nicht. Bricht die Live-Verbindung ab, hilft Seite neu laden — die
Debatte läuft im Server weiter und landet im Archiv. Im Task-Center erscheint sie als
**„Beirats-Debatte (frei)"**; „Abbrechen" geht dort, „Erneut" nicht (dafür zurück auf die Seite
**Beirat**). Optionale API-Schlüssel legst du unter **„🔑 Schlüssel & Motor"** ab. Sie liegen nur auf
deinem Rechner in `~/.bewerbung_beirat/`, außerhalb des Programmordners.

### 🏢 Firmen · 📡 Restructuring-Radar
Firmen-Datenbank bzw. Firmen mit frischem Umbau-/Layoff-Signal (dein Build/Rebuild-Radar).

### 🪪 Profil
Dein eigenes Kandidaten-Profil an einer Stelle — die Substanz, aus der **Matching und Anschreiben**
schöpfen. Von oben nach unten:
- **Identität und Suchstrategie** — die erste Karte der Seite. Hier trägst du ein, wer du bist und
  wonach du suchst. Die Karte liest und schreibt die Datei `config/profil.md`.
  - **Felder:** Name (Pflicht), Positionierung (Kurzzeile), Anschrift, E-Mail, Telefon, LinkedIn,
    Aktuell, Kurzprofil, Zielrolle (Ebene, Funktion Plan A und Plan B, Branche, Region, Zieltermin),
    harte Rahmenbedingungen und bekannte Skill-Gaps.
  - **Worauf es ankommt:** Name, Anschrift, Kontakt und LinkedIn bilden den Briefkopf deiner
    Anschreiben und die Dateinamen. Die Anschrift schreibst du als `Straße Nr, PLZ Ort`, etwa
    `Musterweg 3, 12345 Musterstadt`. Daraus entsteht die Ortszeile der Anschreiben, und sie ist der
    Startpunkt der Routenplanung zu Gesprächen. Kurzprofil, Zielrolle und Rahmenbedingungen liest die KI
    als Hintergrund: je konkreter, desto besser.
  - **Speichern** ist erst aktiv, wenn du etwas geändert hast. Danach steht dort „✓ Gespeichert“, und
    Seitenleiste und Routenplanung laden die neuen Angaben. Gelbe Zeilen sind Hinweise, etwa wenn der
    Anschrift das Komma oder die Postleitzahl fehlt. Gespeichert wird trotzdem.
  - **Nichts geht verloren:** Was die Karte nicht kennt, etwa den Abschnitt „Empirie aus dem
    Bewerbungsverlauf“, den das BMS selbst pflegt, oder eigene Abschnitte, bleibt unverändert. Die
    vorherige Fassung der Datei landet bei jedem Speichern im Papierkorb (`data/papierkorb/`). Hat sich
    die Datei zwischenzeitlich geändert, etwa durch eine Auswertung, bittet dich die Karte, neu zu
    laden: Klicke auf „Neu laden“ und trage deine Änderung noch einmal ein.
  - Wer mag, bearbeitet `config/profil.md` weiter von Hand. Dann muss die Schreibweise `**Name:**`
    stimmen.
- **LinkedIn einlesen — zwei Wege.** Der **empfohlene** ist das Datenexport-ZIP: LinkedIn →
  Einstellungen → Datenschutz → „Get a copy of your data" → **oberste Option „Download larger data
  archive"** (⚠️ *nicht* die Schnellauswahl „Profile" — die enthält nur die Positionierung). Nur das
  große Archiv bringt Skills, Berufserfahrung, Ausbildung und Zertifizierungen; LinkedIn braucht dafür
  bis zu ~24 Stunden. Der zweite Weg ist der Button **„Profil einlesen"** neben dem URL-Feld — der ist
  *best effort*: was hinter LinkedIns Login-Wall liegt, meldet er ehrlich als nicht lesbar, statt es
  zu erfinden.
- **Positionierung** — großer Prosa-Block, frei editierbar.
- **Skills als Chips**, nach Themenbereichen gruppiert. Neue Skills trägst du in einer Zeile nach
  (Name + Bereich wählen oder neu anlegen). **Importierte Skills sortieren sich selbst ein:**
  nach jedem ZIP-Import mit neuen Skills läuft automatisch ein Hintergrund-Lauf
  (sichtbar im Task-Center), der alles aus dem Sammeltopf „LinkedIn (unsortiert)" einem passenden
  Bereich zuordnet — bevorzugt einem vorhandenen. Er **verschiebt nur**: erfindet nichts, benennt
  nichts um, fasst bereits Einsortiertes nicht an.
- **Werdegang** — Rollen, Ausbildung, Zertifizierungen als editierbare Blöcke.
- **Zertifikate & Zeugnisse** — Dateien anhängen, öffnen, löschen (→ Papierkorb).

Beide Import-Wege sind **additiv und zerstörungsfrei**: sie füllen nur Leeres und hängen an,
überschreiben nie etwas, das du selbst gepflegt hast.

**Auf einer neuen Installation** entfernst du zuerst die Beispieldaten (Abschnitt 1), füllst dann die
Karte „Identität und Suchstrategie“ und importierst danach. Stehen die Beispieldaten noch im Profil,
übernimmt der Import deine Positionierung nicht, denn das Feld ist schon gefüllt, und er überspringt
Fähigkeiten, die als Beispiel schon dastehen, etwa „Deutsch“. Sie verschwänden dann mit den
Beispieldaten.

### 🎯 Einstellungen
Hier stellst du die **grundsätzlichen Parameter deiner Jobsuche** selbst ein, statt Konfigurationsdateien
von Hand zu editieren:
- **Suchbereich & Firmengröße** — drei Schalter **Remote · Deutschlandweit · Stadt + Umkreis**
  (mit Stadt-Feld und km-Zahl) sowie die **Mindest-Mitarbeiterzahl** einer Firma. Der Umkreis
  erscheint als eigener Filter-Reiter „<Stadt> +<km>km" in der Jobliste; änderst du Stadt oder
  Radius, stellt das BMS vorhandene Stellen automatisch auf die neue Bezeichnung um.
- **E-Mail-Konto**: Provider-Wahl **IMAP (empfohlener Standard, auch für Gmail) oder
  Gmail-API** (Power-Variante, eigenes Google-Cloud-Projekt). Welcher Weg wofür passt und die
  Einrichtung Schritt für Schritt stehen in `docs/SETUP-EMAIL.md`.
  IMAP deckt Gmail, GMX, Web.de, mailbox.org, Posteo und iCloud-Mail ab — jeweils mit
  App-Passwort des Anbieters. IMAP braucht
  Host/Port/Sicherheit (SSL/STARTTLS), Benutzer, Passwort und den Namen des Entwürfe-Ordners;
  **Verbindung testen** prüft Login und Ordner, gespeichert wird ins Secrets-Verzeichnis
  (`~/.bewerbung_mgmt_secrets/mail_settings.json`, nie in DB oder iCloud). In beiden Fällen wird
  **nie gesendet** — nur gelesen und Entwürfe abgelegt. Outlook.com/Microsoft-Konten werden
  mangels IMAP-Basic-Auth derzeit nicht unterstützt.
- **Beispieldaten**: nur auf einer frischen Installation, ganz oben auf der Seite. Die Karte
  nennt, was an Beispieldaten von Birne Helene da ist, und entfernt es mit „Beispieldaten entfernen“
  und einer Rückfrage. Vorher legt das BMS eine Sicherung an. Was dabei passiert, steht in Abschnitt 1
  unter „Beim allerersten Start: Beispieldaten“. Danach bleibt nur die kleine Zeile „Beispieldaten
  entfernt am …“.
- **KI-Modell je Funktion**: Für **Jobsuche · Company Fit · Beirat · CV Match · ATS Scan ·
  Anschreiben** wählst du jeweils **Opus 5.5**, **Sonnet 5.5** oder **Haiku 4.5**, Standard ist
  überall Sonnet 5.5. So setzt du das stärkere Modell gezielt dort ein, wo es sich lohnt. **Fable**
  steht bewusst nicht zur Wahl, weil es zu teuer ist: Es kostet das Zweieinhalbfache von Opus 5.5
  und das Fünffache von Sonnet 5.5. Hattest du es früher gewählt, arbeitet die Funktion jetzt mit
  Sonnet 5.5, und die Einstellungen zeigen das auch so an. ⚠️ Die Wahl gilt für Läufe, die du
  **über die App-Buttons oder das Task-Center** startest. Tippst du einen Skill von Hand in der
  Claude-Session, zählt weiterhin das dort eingestellte Modell. Läufe ohne eigene Auswahl, etwa
  E-Mail-Check, Gesprächs-Auswertung und Absagen-Analyse, laufen immer mit Sonnet 5.5, nicht mit dem
  Standardmodell deiner Claude-Installation.
- **Drei Plan-Karten A / B / C** — je ein frei benennbares Label, ein Aktiv-Schalter und Chip-Listen
  für **Rollentitel · Seniorität · Branche**. Die Jobsuche arbeitet die Pläne in der Reihenfolge
  **A → B → C** ab. Plan C ist neu (vorher gab es nur A und B) und taucht entsprechend auch in den
  Auswahlfeldern im Job-Detail, unter „Neue Stelle" und im Excel-Export auf.
- **Datensicherung**: zeigt die letzte automatische Sicherung (Zeitpunkt, Größe) und ihre
  Zahl, mit einem Schalter für die tägliche Automatik, Feldern für die Aufbewahrung (tägliche/
  wöchentliche/monatliche Sicherungen) und dem Knopf „Jetzt sichern". Ein amber Hinweis erscheint
  bei einer fehlgeschlagenen Sicherung oder wenn die letzte bei eingeschalteter Automatik älter
  als drei Tage ist (auch auf dem Dashboard). Zurückspielen: Abschnitt „Datensicherung" weiter
  unten in dieser Anleitung.
- **Programmversion**: letzte Karte, zeigt die installierte Version (bzw. bei einer
  Git-Installation den Entwicklungsstand) und was sich in dieser Version geändert hat. Der Knopf
  **„Nach Updates suchen“** fragt bei GitHub nach der neuesten Version. Das Ergebnis nennt die
  Version mit Datum und Änderungen und verlinkt auf die Seite bei GitHub, oder es sagt, dass dein BMS
  auf dem neuesten Stand ist. Gesucht wird nur, wenn du auf den Knopf klickst, nie von allein.
  GitHub erhält dabei die IP-Adresse deines Rechners, sonst nichts. Die Karte spielt nichts ein.
  Eine neue Version holst und spielst du bei beendetem BMS über `update.command` bzw.
  `update_windows.bat` ein: Das Werkzeug lädt sie selbst von GitHub und prüft das Paket. Vorher sagt
  es, dass GitHub die IP-Adresse erhält, und nur dein Start löst es aus. Mit `--offline` sucht es
  nicht online, eine ZIP-Datei `BMS_<Version>.zip` im Ordner „Downloads“ findet es weiterhin.
  Einzelheiten dazu stehen in `BMS_Install_MAC.md` bzw. `BMS_Install_Windows.md`, Abschnitt
  „Aktualisierungen einspielen“. Dieselbe Version steht unten in der Seitenleiste, die Änderungen
  aller Versionen unter **📖 Dokumentation**, Reiter „Version“.

Beim Speichern schreibt die App `config/suchprofile.yaml` automatisch neu — aber **nur** den oberen,
verwalteten Block; alle handgepflegten Technik-Parameter darunter bleiben unangetastet. Die Datenbank
ist die Wahrheit, die Datei nur die Sicht, die alle Skills unverändert weiterlesen.

**Coach-Site:** eine eigene Karte am Seitenende mit eigenem Speicherort (nicht die
`suchprofile.yaml`). Sie enthält einen Ein/Aus-Schalter, die **Adresse der Seite**, den
**SFTP-Zugang** (Host/Benutzer/Passwort/Zielverzeichnis), den **Serverpfad zur Zugangsdatei**
(Feld + Button „automatisch ermitteln") und den **Coach-Login** (eigener Benutzer/Passwort für
deinen Coach).
„Verbindung testen" prüft die SFTP-Daten vorab; erst wenn aktiviert UND vollständig gespeichert
ist, erscheint der Button **„Coach-Site jetzt aktualisieren"** — derselbe Export läuft zusätzlich
automatisch als letztes Glied jedes Tageslaufs. Ergebnis: ein passwortgeschützter, rein lesender
Spiegel deines Bewerbungsstands für einen externen Coach — Übersicht, aktive Bewerbungen, Sichtung/
Prüfung (inkl. Stellenausschreibung) und Absagen mit Gründen; **garantiert nie** sichtbar: E-Mails,
Notizen & Verlauf, Beirats-Checks, Gehälter, Netzwerk/Kontakte, Budget. Schritt-für-Schritt-
Einrichtung (auch für Nicht-Entwickler): `docs/ANLEITUNG_COACH_SITE.md`.

### 📖 Dokumentation
Alle Texte zum BMS an einem Ort, in Reitern, ohne dass du das BMS verlässt. Die Texte liegen auf
deinem Rechner, es wird nichts aus dem Internet geladen. Die Reiter:
- **Version**: was sich in jeder Version geändert hat, die neueste oben. Darüber steht, welche
  Version bei dir installiert ist.
- **Funktionen**: eine kurze Übersicht dessen, was das BMS kann, nach Arbeitsschritten geordnet.
- **Anleitung**: dieser Text.
- **Installation & Updates**: die Installationsanleitung mit dem Ablauf für Updates und für die
  Datensicherung.
- **E-Mail einrichten**, **Windows**, **Coach-Site** und **Beirat** (die Regeln des Beirats): die
  Einzelanleitungen.

„In neuem Tab öffnen ↗“ über dem Text öffnet den gewählten Text in einem eigenen Browser-Tab, etwa
zum Drucken. Webadressen im Text öffnen immer in einem neuen Tab.

### ⚖️ Rechtliches
„Über dieses Programm“ (Herausgeber, Lizenz, Haftung, Hinweis zur KI), der Wortlaut der Open-Source-Lizenz (Apache
License 2.0), Hinweise zum Datenschutz (welche Daten das BMS wohin schickt) und die Lizenzen der
Open-Source-Bestandteile, die das BMS mitinstalliert.

---

## 4. Die Status-Werte
| Status | Bedeutung | Wo sichtbar |
|---|---|---|
| **Neu** | Frischer Treffer, noch nicht gesichtet | Review, Pipeline |
| **Prüfen** | Angenommen, in aktiver Bearbeitung | Pipeline, Stellen |
| **Beworben** | Bewerbung raus | Pipeline, Funnel |
| **Interview** | Gespräch terminiert (oft via Gmail-Check) | Pipeline |
| **Angebot** | Vertrags-/Gehaltsangebot | Pipeline |
| **Absage** | Absage erhalten | Pipeline |
| **Beirat abgelehnt** | Der Beirat hat rot votiert („Stelle prüfen (Beirat)" in der Workflow-Karte) | archiviert |
| **Kein Match** | Verworfen, bleibt für Dedup. Eine neue Anzeige derselben Stelle (anderer Link) erscheint wieder als „Neu“ mit Hinweis `NEUAUSSCHREIBUNG?` | archiviert |
| **Nicht verfügbar** | Stelle offline/abgelaufen | archiviert |
| **Geparkt** | Später nochmal ansehen | archiviert |

**Zielstellen-Fit 1–5:** 5 = Situation **und** Funktion **und** Region passen; 1 = Randtreffer.
Situation ist der wichtigste Filter (BUILD/CARVE-OUT/POST-MERGER/PE/SCALE-UP = Plan-A-Kern).
Zu jeder Bewertung gehört eine **Begründung mit Beleg** (Zitat aus der Anzeige) — steht die nicht
da, taugt die Zahl nichts. Das Bewertungsraster selbst liegt in `config/scoring_rubrik.md`.

**Die drei Bewertungen nicht verwechseln** — sie messen verschiedene Dinge:

| Bewertung | Skala | Was verglichen wird | Wo |
|---|---|---|---|
| **Zielstellen-Fit** | 1–5 | die **Stelle** gegen dein **Zielprofil** (Situation · Funktion · Region) | Stellen-Liste, Dashboard, Job-Detail |
| **Match-Score** | 0–100 | dein **CV** gegen die **Anzeige** (Keywords, Belege, Lücken) | Job-Detail → Match-Dashboard nach „CV-Match" |
| **ATS-Score** | 0–100 | dein **CV** gegen den **Bewerbungsroboter** (Lesbarkeit, Optimierungsgrad) | Job-Detail → ATS-Scan nach „CV erstellen" |

Der Zielstellen-Fit entscheidet, **ob** du dich mit einer Stelle beschäftigst; die anderen beiden,
**wie gut deine Unterlagen dafür sind**.

---

## 5. Dein täglicher Ablauf
1. **Morgens: Tageslauf starten.** Der runde **☀️-Button** oben links in der App öffnet einen Dialog mit
   den Schritten (Stellen suchen → Mail-Jobsuche → Zielfirmen-Sweep → Headhunter-Suche → Beworben-Check →
   Postfach prüfen → Absagen-Analyse, einmal je Woche → Ansichten aktualisieren → Coach-Site, sofern
   eingerichtet) und zeigt den letzten Lauf.
   „▶ Tageslauf starten" lässt die App die Kette **selbst** headless im Hintergrund laufen — Fortschritt
   siehst du dort oder im Task-Center. Lieber klassisch? Der aufklappbare Punkt „Lieber in der
   Claude-Session starten" kopiert dir stattdessen den Auslöser „Tageslauf" in die Zwischenablage.
2. **App öffnen** → **Neu / Review**: neue Treffer durchsortieren (Annehmen / Verwerfen).
3. Für angenommene, wirklich interessante Stellen: im **Job-Detail** die Karte „Unterlagen erstellen"
   Schritt für Schritt durchgehen (Company-Fit → Beirat → CV-Match → *Entwurf bearbeiten* → CV erstellen
   → Anschreiben). „**Deep-Dive für Job <id>**" macht Firma + CV in einem Rutsch — ohne Beirats-Schritt.
4. Bewerbung raus → Status im **Job-Detail** oder **Kanban** auf **„Beworben"** ziehen.
5. **Inbox** prüfen: Einladungen/Absagen laufen automatisch ein; „zu beantworten"-Mails abarbeiten.
6. **Follow-ups** durchgehen: überfällige Stellen nachfassen (✉️-Chip), anstehende Gespräche vorbereiten,
   fällige Netzwerk-Kontakte angehen.
7. **Dashboard** im Blick behalten (Funnel, Antwortquote), **Netzwerk** pflegen.

---

## 6. Exporte & Namenskonvention
- **Excel-Stand-Report** und **Tages-Digest** (Dashboard-Buttons) — jederzeit frisch aus der DB
  generiert. Der Excel-Export ist ein Stand-Report mit elf Blättern: Dashboard-Cockpit (KPIs wie
  auf der Web-Seite), Funnel, Stellen **pro Status gruppiert** (mit Fit/Match-100/ATS/Beirat und
  klickbarem Quelle-Link), Bewerbungen, Aussortiert, Referenzen, Kontakte, Netzwerk, Headhunter,
  Zielfirmen, Outreach. Bei Absagen und aussortierten Stellen ist der „Nächste Schritt" im Export
  bewusst leer (alte Handlungsaufrufe wären irreführend — in der App bleiben sie erhalten).
- Das Blatt **Bewerbungen** zeigt jede Stelle, auf die du dich beworben hast, in einer Zeile: Firma,
  Bezeichnung, Fit, Match-100, ATS, wann gefunden, wann beworben, das Datum jeder Gesprächsrunde
  (Runde 1 bis 6, so wie du die Runden im Job-Detail erfasst) und das Absagedatum. Die neueste
  Bewerbung steht oben. Hat ein Gespräch keinen Termin, nimmt das BMS das Datum seines Transkripts;
  gibt es keins, bleibt die Zelle leer und trägt einen Kommentar. Abgesagte Gespräche fehlen. Das
  Absagedatum ist der Tag der Absage-Mail, ohne Mail der Tag, an dem die Stelle auf „Absage“ ging.
- Generierte Dateien beginnen mit dem Datum in der Form **`JJJJMMTT_`** (zum Beispiel `20261001_`), damit
  sie sich chronologisch sortieren lassen.
- **Report-Style:** neu erzeugte Reports (Match, ATS-Scan, Briefing, Anzeige-Kopie, Absagen-Analyse,
  Auswertung eines Gesprächs, Beirat) sehen einheitlich aus (ein gemeinsames Design, statisches HTML) und
  heißen intern `JJJJMMTT_<Typ>_<Firma>[_<Rolle>]`. Die Typ-Wörter sind bewusst kurz: `Anzeige` für die
  Kopie der Stellenausschreibung, `Auswertung` für den Bericht zu einem Gespräch, `Beirat` für die
  Beirats-Prüfung einer Stelle. Ein Beispiel: `20261001_Auswertung_Beispiel_Software_Director_Beratung_R2.html`.
  Company-Fit hat **keinen** Rollen-Teil, jede Neu-Prüfung legt bewusst eine neue, datierte Datei an.
  CV und Anschreiben behalten ihren empfängerfreundlichen Namen (s. o.).
- **Kurze Namen:** Firma und Rolle werden im Dateinamen gekürzt. Bei der Firma fallen Rechtsformen
  (wie GmbH oder AG) und Zusätze nach einem Komma, Doppelpunkt oder Klammerzeichen weg, der Rest wird
  auf 25 Zeichen an einer Wortgrenze begrenzt. Die Rolle bleibt bei Berichten bei 30 Zeichen, bei CV
  und Anschreiben bei 35. Die volle Bezeichnung steht weiterhin in der App und im Dokument selbst.
- **Ältere Dateien:** Dateien aus früheren Versionen heißen noch `JJJJ_MM_TT_…` mit den langen
  Typ-Wörtern. Sie bleiben vollständig nutzbar, das BMS erkennt beide Schreibweisen des Datums, auch im
  Papierkorb.

---

## 7. Löschen & Papierkorb
Löschen ist in der App **immer reversibel** — es gibt keinen Löschbefehl, der endgültig etwas
entfernt. Drei Löscharten, alle mit Bestätigungsdialog:
- **Einzelne Dateien** (Job-Detail → „Dateien & Dokumente", 🗑-Icon): egal ob dein eigener Upload
  oder ein generiertes Artefakt (Company-Fit, CV, Match-/ATS-Dashboard, Anschreiben, Briefing,
  Transkript-Report) — die Datei wandert in den zentralen Papierkorb `data/papierkorb/`, das
  zugehörige Feld in der DB wird geleert. Beim Company-Fit-Eintrag warnt der Dialog: er gehört der
  **Firma**, nicht der einzelnen Stelle, und verschwindet damit von allen ihren Stellen.
- **Stelle löschen** (Job-Detail → unten in der Eckdaten-Karte „🗑 Stelle löschen"): alle
  Artefakt-Dateien der Stelle (Snapshot, CV, Anschreiben, Briefings, Transkripte inkl. Debrief/
  Report) wandern in den Papierkorb; Interviews/Transkripte/Bewerbung/Notizen-Verlauf werden
  entfernt. **E-Mails bleiben erhalten** (Postfach-Historie/Antwortquote) — nur die Verknüpfung zur
  Stelle wird gelöst. Die Stelle selbst verschwindet aus allen Listen (Stellen/Review/Dashboard/
  Follow-ups/Suche), bleibt aber intern als unsichtbarer Dublettenschutz erhalten — taucht derselbe
  Treffer bei einer künftigen Jobsuche erneut auf, wird er automatisch übersprungen statt neu
  angelegt. Ruft ein alter Link (z. B. aus dem Task-Center) die gelöschte Stelle auf, öffnet sich
  die Seite trotzdem (kein toter Link) statt einer Fehlermeldung.
- **Firma löschen** (Firmen-Tabelle, 🗑-Icon): nur möglich, wenn **keine** aktiven Stellen mehr an
  der Firma hängen — sonst zeigt die App eine verständliche Meldung mit der Liste der Stellen, die
  zuerst gelöscht werden müssen. Ohne aktive Stellen: Company-Fit-Datei in den Papierkorb, Kontakte
  der Firma werden entfernt, E-Mails bleiben (nur entkoppelt).
- **Papierkorb** (`data/papierkorb/`): läuft nie automatisch leer. Endgültiges Entfernen ist Sache
  eines separaten Cleanup-Laufs bzw. manuell durch dich — die App selbst löscht nie hart.

**Eine Ausnahme:** „Beispieldaten entfernen“ (Einstellungen) löscht die Beispielzeilen in der
Datenbank endgültig, sie landen nicht im Papierkorb. Dafür legt das BMS vorher eine Sicherung an
(Abschnitt 8), und Dateien daraus wandern wie oben in den Papierkorb.

**System-Cleanup (`backend/pipeline/cleanup.py`, manuell im Terminal, ~monatlich):**
ein deterministisches Kommando (kein LLM), das findet, was die App selbst nicht anfasst — Orphan-
Dateien ohne DB-Referenz, tote DB-Pfade, alternde Logs/Exporte/DB-Backups, Papierkorb-Endleerung:
- `cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.cleanup scan` — ändert NICHTS,
  druckt einen Bericht und schreibt `data/analysen/JJJJMMTT_Analyse_Cleanup.html`.
- `... pipeline.cleanup apply [--ja] [--fix]` — verschiebt Orphans + alte Dateien (>60 Tage,
  konfigurierbar über `--rotate-days`) in den Papierkorb (nie endgültig), mit `--fix` werden dazu
  tote DB-Pfadfelder genullt. Fragt vor der Ausführung immer nach (außer mit `--ja`).
  Sichert die DB vorher automatisch.
- `... pipeline.cleanup leeren --older-days N [--ja]` — der EINZIGE Befehl im ganzen System, der
  endgültig löscht (nur Papierkorb-Inhalte älter als N Tage, N muss ≥ 30 sein, ohne Angabe passiert
  nichts). Läuft nie automatisch, der Tageslauf meldet nur auffällige `scan`-Kennzahlen.

**Wenn ein Report komisch aussieht (Farben fehlen, alles grau):** Die Dashboards bringen ihr CSS
in jeder Datei selbst mit. Lässt ein Lauf dabei Regeln weg, bleibt der Inhalt richtig, aber die
Farben verschwinden, etwa graue statt grüner und roter Keyword-Chips in einem ATS-Scan. Der Check
findet das in Sekunden, ändert nichts und kostet nichts:
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.report_check ../data/company_fit/*.html
```
Er sagt dir genau, welche Regel in welcher Datei fehlt — nachtragen reicht, der teure Skill-Lauf
muss dafür **nicht** wiederholt werden. Nach jedem ATS-Scan läuft die Prüfung automatisch mit;
der Befehl ist nur für den Fall, dass dir an einem älteren Report etwas auffällt.

---

## 8. Datensicherung

Das BMS sichert deine Datenbank automatisch, solange es läuft: einmal täglich als ZIP-Datei im
Ordner `data/backups/auto`. Aufbewahrt werden die neueste Sicherung, alle der letzten 24 Stunden
sowie je eine der letzten 7 Tage und der letzten 4 Wochen. Ältere automatische Sicherungen
entfernt das BMS selbst. Einstellungen → **„Datensicherung"** zeigt die letzte Sicherung, lässt
dich die Aufbewahrung ändern und mit **„Jetzt sichern"** von Hand eine neue anlegen. Auch „Beispieldaten
entfernen“ (Abschnitt 1) und der Import einer Netzwerk-Liste (Abschnitt 3, „Netzwerk“) legen vorher
eine solche Sicherung an.

Diese Sicherungen liegen im BMS-Ordner auf derselben Festplatte wie deine Arbeitskopie. Sie
ersetzen keine externe Datensicherung wie Time Machine. Nimm den BMS-Ordner zusätzlich in deine
reguläre Datensicherung auf.

So spielst du eine Sicherung zurück, auf dem Mac wie unter Windows:

1. BMS beenden: Doppelklick auf `stop.command` (Mac) bzw. `stop_windows.bat` (Windows).
2. Doppelklick auf `wiederherstellen.command` (Mac) bzw. `wiederherstellen_windows.bat`
   (Windows) im BMS-Ordner. Das Werkzeug zeigt dir die vorhandenen Sicherungen, die neueste
   zuerst, mit Datum, Uhrzeit, Art und Größe.
3. Tippe die Nummer der gewünschten Sicherung ein und bestätige die Rückfrage mit „j“. Mit Enter
   ohne Eingabe brichst du ab. Das Werkzeug prüft die Sicherung, bevor es etwas ändert, und legt
   zuerst eine Sicherung deines aktuellen Stands an.
4. BMS starten wie gewohnt.

Gut zu wissen:

- **Es kommen nur die Datenbank-Daten zurück.** Alles, was du seit dem Zeitpunkt der Sicherung
  erfasst oder geändert hast, ist danach nicht mehr in der Datenbank. Deine Dokumente in `outputs`
  und `data` bleiben unverändert. Dateien, die nach der Sicherung entstanden sind, gehören danach
  zu keiner Stelle mehr.
- **Rücknahme:** Dein Stand vor dem Zurückspielen liegt als Sicherung „vor Wiederherstellung“ in
  `data/backups`. Starte das Werkzeug noch einmal und wähle diesen Eintrag, dann ist alles wieder
  wie vorher.
- **Welche Sicherungen erscheinen:** die automatischen aus `data/backups/auto`, die von Hand
  angelegten aus `data/backups` und die Einträge „vor Wiederherstellung“. Die Sicherungen, die ein
  Update anlegt, gehören nicht dazu. Ein Update nimmst du mit `update.command --zurueck` bzw.
  `update_windows.bat --zurueck` zurück.
- **Läuft das BMS noch,** bricht das Werkzeug ab und sagt es dir. Beende das BMS und starte das
  Werkzeug erneut.

Falls das Werkzeug nicht startet, geht es auch von Hand: BMS beenden, im Ordner
`data/backups/auto` die gewünschte ZIP-Datei entpacken (Mac: Doppelklick, Windows: Rechtsklick und
„Alle extrahieren"), die vorhandene `data/bewerbung.sqlite` umbenennen statt löschen, etwa in
`bewerbung_alt.sqlite`, die entpackte `bewerbung.sqlite` in den Ordner `data` legen und das BMS
starten.

---

## 9. Grenzen (bewusst so)
- **Kein Auto-Bewerben**, kein automatischer Versand.
- **E-Mail: nur lesen + Entwürfe** — Scopes `readonly` + `compose` (Gmail) bzw. IMAP ohne SMTP;
  es gibt **keinen Sende-Codepfad** (per Test verankert), nie senden/labeln.
- **CV-Tailoring wahrheitstreu** — keine erfundenen Skills/Zahlen; nicht gedeckte Keywords werden ehrlich benannt.
- **Automatik** (zeitgesteuert) ist vorbereitet, aber nicht aktiv: Den Tageslauf startest du per
  Knopfdruck (Abschnitt 5).
