# Was ist neu? — Änderungsprotokoll (neueste Änderungen zuerst)

Diese Datei wächst mit jeder größeren Bau-Session — neuester Zeitraum immer oben, ältere
Abschnitte bleiben darunter erhalten. Feinheiten & Verifikationen zu jedem Punkt stehen im Projektverlauf
des Autors (je Bau-Session ein abgehakter Plan mit „Review“-Absatz; das ist die Quelle dieses Protokolls).
Er gehört nicht zum öffentlichen Repository.

---

## 13.08.2026 — Mehr Gesprächsrunden, klarere Namen

(Phase 84.)

### Für die tägliche Arbeit

- **Beliebig viele Gesprächsrunden — direkt beim Transkript.** Im Transkript-Dialog steht unter
  der Rundenauswahl jetzt „**+ Neue Runde anlegen…**": Nummer und Gesprächsart eintragen, fertig —
  kein Umweg mehr über einen zweiten Dialog. Neu dabei ist die Art „**Headhunter-Screen**" für das
  Vorgespräch mit einem Personalberater. Das Feld „Gegenüber" füllt sich passend zur Art von
  selbst (Fachgespräch → Fachbereich, Headhunter-Screen → Headhunter); wenn du bewusst etwas
  anderes einstellst, bleibt deine Wahl stehen. Angelegt wird die Runde erst beim Speichern —
  brichst du ab, bleibt nichts zurück.
- **Der Stellen-Score heißt jetzt „Zielstellen-Fit".** Bisher hießen drei verschiedene Bewertungen
  im System alle „Match": die Bewertung der *Stelle* (1–5), die Bewertung deines *CVs* gegen die
  Anzeige (0–100) und der ATS-Wert. Der Stellen-Score trägt deshalb jetzt einen eigenen Namen:
  **Zielstellen-Fit** — er misst die Stelle gegen dein Zielprofil (Situation · Funktion · Region).
  So erkennst du's: Dashboard-Kachel „**Top-Zielstellen (≥4)**" und Balken „**Nach
  Zielstellen-Fit**", in der Stellen-Liste Filter (`Zielstellen-Fit ≥ 4`) und Sortierung, der
  Tooltip auf der farbigen Zahl, das Feld beim manuellen Anlegen einer Stelle und die Kachel im
  Tages-Digest. Eine Übersicht aller drei Bewertungen steht in `ANLEITUNG.md`, Abschnitt 4.
  **Nichts an der Bewertung selbst hat sich geändert** — dasselbe Bewertungsraster, dieselben gespeicherten
  Werte. Auch der Status „Kein Match" heißt weiter so.

---

## 25.07.–12.08.2026 — Coach-Zugang, robusteres Bewerbungs-Tracking, einheitliches Design

(Phase 73–82.)

### Für die tägliche Arbeit

- **Karriereseiten-Fallback, wenn ein Portal zu ist:** Erkennt die Firma-Prüfung, dass eine
  Stelle auf dem ursprünglichen Portal nicht mehr aktiv ist, sucht das System automatisch auf
  der Firmen-Karriereseite nach derselben Stelle. So erkennst du's: Job-Detail → Eckdaten — neue
  Zeile „Karriereseite" (Link) und, falls zutreffend, eine rote Zeile „Portal-Bewerbung:
  geschlossen". Beides lässt sich im Edit-Modus auch von Hand setzen.
- **Wöchentlicher Beworben-Check:** Für jede laufende Bewerbung (Beworben/Interview) prüft das
  System automatisch im Tageslauf, ob die Stelle noch ausgeschrieben ist — dein Bewerbungsstatus
  selbst wird dabei nie angetastet, das bleibt allein deine Entscheidung. So erkennst du's:
  Job-Detail → Eckdaten-Zeile „Verfügbarkeit" (mit Prüfdatum); Stellen-Liste → Badge
  „⛔ offline"; Dashboard → Kachel „Beworbene offline" (nur sichtbar, wenn es welche gibt).
  Manuell anstoßen: Review-Seite → Button „Beworben-Check".
- **Anzeigen-Snapshots wieder klar gegliedert:** Der Schnappschuss einer Stellenanzeige trennt
  jetzt wieder zuverlässig Aufgaben, Anforderungen, Benefits, „Über das Unternehmen" und Kontext
  voneinander, inklusive eines eigenen Abschnitts „⚠️ Widersprüche", falls Anzeige und erfasste
  Eckdaten auseinanderlaufen. So erkennst du's: Job-Detail → Anzeigen-Snapshot (nach der
  Firma-Prüfung).
- **Excel-Export mit echtem Aussortier-Grund:** Im Blatt „Aussortiert" zeigt die Spalte „Grund"
  jetzt den tatsächlichen Grund (aus deinen Notizen bzw. der Match-Begründung) statt der immer
  leeren Spalte „Nächster Schritt". Beide Stellen-Blätter zeigen zusätzlich den Match-Score als
  Zahl von 0–100, die Beirat-Spalte ist auf Zahl + Ampelfarbe eingedampft. So erkennst du's:
  Dashboard → „⬇ Excel-Export".
- **KI-Fragen an einer Stelle lassen sich abbrechen:** Läuft die Antwort auf „Stelle fragen (KI)"
  zu lange, beendet ein neuer „Abbrechen"-Button sie sofort — auch nach einem Seiten-Reload
  während die Antwort noch läuft, findet die Seite die laufende Anfrage wieder und der
  Abbrechen-Button bleibt verfügbar. So erkennst du's: Job-Detail → Abschnitt
  „Stelle fragen (KI)".
- **Neuer Button „E-Mail-Check":** Der tägliche Gmail-Check lässt sich jetzt auch von Hand
  anstoßen, ohne auf den nächsten Tageslauf zu warten. So erkennst du's: Review-Seite →
  Button-Zeile, direkt neben „Beworben-Check".

### Neu: Coach-Site

Ein externer Coach kann jetzt — falls gewünscht — schreibgeschützt mitlesen: Übersicht, aktive
Bewerbungen sowie Sichtung/Prüfung (Neu + Prüfen) mit Company-Fit, Match und Stellenausschreibung
je Stelle, dazu Absagen mit Gründen. E-Mails, Notizen, Beirats-Checks, Gehälter und Transkripte
bekommt der Coach **nie** zu sehen.

- **Komplett über die Einstellungen konfigurierbar** (vorher nur über eine lokale
  Konfigurationsdatei einrichtbar): Einstellungen → Karte „Coach-Site" — Adresse der Seite, Upload-Ziel
  (SFTP-Host/Benutzer/Passwort/Zielverzeichnis), Serverpfad zur Zugangsdatei (Button
  „automatisch ermitteln" statt Werte von Hand suchen), eigener Coach-Login (Benutzer + Passwort,
  lokal sicher gehasht) sowie ein Ein/Aus-Schalter. Dazu „Verbindung testen" und
  „Coach-Site jetzt aktualisieren" — sie aktualisiert sich sonst automatisch am Ende jedes
  Tageslaufs.
- **Eigenes Favicon:** Jede Coach-Seite und jedes für den Coach exportierte Dokument zeigt jetzt
  das App-Icon im Browser-Tab statt eines leeren Platzhalters.
- **Eigene Anleitung:** Eine Schritt-für-Schritt-Anleitung inklusive „Wenn etwas nicht
  klappt"-Abschnitt liegt unter `docs/ANLEITUNG_COACH_SITE.md` (aus der Einstellungen-Karte
  verlinkt) sowie zusätzlich als druckbares HTML-Handbuch.

### Unter der Haube

- **Design durchgängig auf den Styleguide gebracht:** App-Oberfläche und alle generierten
  Berichte (Company-Fit, Digest, Beirats-Synthese) nutzen jetzt konsistent dieselbe Farb- und
  Schrift-Basis (u. a. Primärbuttons Cyan statt Navy, echte Montserrat/Inter-Schriftarten statt
  Browser-Standard) — du merkst es an einem einheitlicheren Bild über die ganze App und alle
  Reports hinweg.
- **Workday-taugliche Basis-Lebensläufe:** Die Basis-CVs (Ausgangspunkt für jeden CV-Match) sind
  so umgebaut, dass Workday-Bewerbungsformulare („Autofill with Resume") Titel, Firma und
  Zeitraum je Station korrekt herauslesen, statt den Titel um eine Station zu verschieben.
- **cv-match baut jetzt immer neu:** Ein „CV-Match"- bzw. „neu matchen"-Lauf nimmt garantiert die
  aktuelle Basis-CV-Datei als Ausgangspunkt und legt einen frischen Entwurf an — nie mehr wird
  dabei unbemerkt eine ältere Entwurfsfassung recycelt.
- **Einheitliche Anmeldung für Hintergrund-Läufe:** Beirats-Läufe nutzen jetzt denselben
  Anmeldeweg wie die anderen Skills. Das verhindert, dass mehrere gleichzeitig gestartete
  Hintergrund-Läufe sich gegenseitig aussperren, wie es zuvor vereinzelt vorkam.

---

## 09.07.2026 — Rundgang durch die Änderungen vom großen Ausbau-Tag

Alles vom großen Ausbau-Tag: Follow-ups, Interviews, Absagen-Analyse, Anschreiben, Initiativ-Workflow,
Mobile. **So erkennst du jede Änderung in der App** — einfach die Klickpfade abgehen.
(Phase 6–8.)

---

### 1. Dashboard — http://localhost:8000
- **Alles ist jetzt klickbar:** Jede KPI-Kachel hat einen →-Pfeil und führt zur passenden Liste
  (Stellen, Top-Matches, laufende Bewerbungen, Firmen, Inbox). Auch die Funnel-Balken sind Links.
- **Auch die vier Balken-Kacheln** (Nach Status / Match-Score / Situation / Portal, „· klickbar" im Titel):
  jeder Balken öffnet die Stellen-Liste mit genau diesem Filter — inkl. Filter-Chip zum Abwählen.
- **Neu oben: der Follow-up-Banner** („⏰ Follow-ups im Blick / 12 offen") → führt zur neuen Follow-up-Seite.
- **Neue Kachel „Bewerbungen (laufend)"** — zählt nur Beworben/Interview/Angebot, nicht Historie.
- **Zahlen sind bereinigt:** Dubletten-Paare wurden (mit deiner Freigabe) zusammengeführt.

### 2. Sidebar — neuer Menüpunkt
- **„⏰ Follow-ups"** zwischen Review und Pipeline. Roter Badge = Anzahl überfälliger Follow-ups.

### 3. Follow-ups-Seite — /followups (komplett neu)
- **🎙️ Anstehende Gespräche** ganz oben: alle geplanten Interviews mit Briefing-Link, ggf. 🗺️ Route,
  und „Termin fehlt"-Warnung (ein Gespräch ohne Termin mahnt dort).
- **🔴 Überfällig & heute** / **⏳ Anstehend**: alle Jobs mit Fälligkeitsdatum. Unbeantwortete
  Bewerbungen sind automatisch eingeplant.
- **✉️ Nachfass-Chip** an jeder Zeile: kopiert „Nachfass-Entwurf für Job X" — in die Claude-Session
  einfügen → fertiger Gmail-Entwurf (wird NIE automatisch gesendet).

### 4. Stellen-Liste — /jobs
- **„+ Stelle anlegen"** (Button oben rechts, neu): manuell gefundene Stellen mit allen Daten erfassen —
  Formular unter `/jobs/neu`. Status wählbar: **Neu** (Review-Liste) · **Prüfen** (aktive Pipeline) ·
  **Beworben** (legt die Bewerbung mit Datum gleich mit an). Dubletten werden erkannt und verlinkt statt doppelt angelegt.
- Neue Spalte **„Gefunden"** + Sortier-Dropdown (**Datum**, Score, Firma, Status) — Datum jetzt korrekt
  chronologisch trotz gemischter Formate.
- **⏰-Badge** am Titel, wenn ein Follow-up fällig ist (rot = überfällig).
- Drill-down-Überschriften: Kommst du vom Dashboard, heißt die Seite z. B. „Laufende Bewerbungen"
  (mit Chip + „Filter zurücksetzen").

### 5. Job-Detail — das meiste Neue steckt hier
Rechte Spalte, von oben nach unten:
- **Status ändern:** jetzt inkl. **Interview** und **Angebot**. Darunter neu:
  - **Bauchgefühl ★★★★★** — dein subjektiver 1–5-Score neben dem Bewertungsraster-Score (erneuter Klick löscht).
  - Bei Status Absage: **„❓ Nach Grund fragen"** → höfliche Feedback-Mail als Entwurf.
- **Nächste Schritte & Follow-up:** Fälligkeitsdatum, nächster Schritt, Notizen — direkt editierbar,
  „überfällig"-Badge auch oben im Kopf.
- **Interviews & Gespräche (neu):** Gespräche anlegen (Runde/Art/Termin/Interviewer), Status-Pills,
  **📋 Briefing öffnen**, **🗺️ Route** (bei Vor-Ort-Jobs),
  **🎯 Interview vorbereiten**-Knopf, darunter **Transkripte einfügen/öffnen**.
- **Bewerbung:** neu **„Absagegrund"** (aus den echten Absage-Mails gefüllt) und
  **„⬇ Anschreiben (.docx)"**.

### 6. Netzwerk & Radar — /netzwerk und /radar
- **„🚀 Initiativ"-Chip** in jeder Zeile (Zielfirmen-Tab bzw. Radar): kopiert „Initiativbewerbung für
  <Firma>" → startet in der Claude-Session den Hidden-Job-Market-Workflow (Netzwerk-Check zuerst!).
- Der Zielfirmen-Check zeigt, bei welchen Zielfirmen schon ein warmer Pfad besteht (Kontakt mit Status
  „In Dialogue“ oder „Responded“).

### 6b. Outreach — /outreach (überarbeitet)
- **Überfällig-Kachel ist klickbar:** filtert die Liste auf überfällige Follow-ups (nochmal klicken oder ✕ hebt auf).
- **Jede Zeile ist aufklappbar (▸):** dort bearbeitest du **Nächster Schritt + Fälligkeitsdatum** direkt —
  und führst das neue **Aktivitäten-Log**: Status-/Schritt-Änderungen werden automatisch protokolliert
  (grauer AUTO-Badge), eigene Einträge tippst du einfach ein (Enter). Chronologisch, neueste zuerst.
- Das Log lebt nur in der App — der Excel-Export (Original-Format) bleibt unverändert.

### 7. Handy — neu: `start_lan.command`
Doppelklick statt `start.command` → Terminal zeigt die Handy-Adresse (z. B. `http://<dein-mac>.local:8000`).
Navigation liegt mobil oben (wischbar), Tabellen wischst du seitlich. ⚠️ Kein Login — nur im eigenen WLAN.

### 8. Die neuen Sätze für die Claude-Session (der „Motor")
| Du sagst … | Es passiert … |
|---|---|
| `Interview vorbereiten für Job <id>` | Call-Briefing (Fragen+STAR, Fragen an die Firma, Spickzettel) → am Interview verlinkt |
| `Debrief für Job <id>` | Transkript auswerten: Summary, To-dos, Kontakte, Fragenbank, Danke-Mail-ENTWURF |
| `Absagen-Analyse` | Lost-Order-Auswertung über alle Absagen → Bericht + Empirie in profil.md |
| `Anschreiben für Job <id>` | Firmenspezifisches Anschreiben (.docx) → an der Bewerbung („Vorbereitet") |
| `Initiativbewerbung für <Firma>` | Netzwerk-Check → Initiativ-Stelle → Entscheider → Ansprache-Route |
| `welche Zielfirmen soll ich initiativ angehen` | Priorisierte Shortlist (warm > Tier > Signal) |
| `Nachfass-Entwurf für Job <id>` | Höfliches Nachfassen bei Funkstille (Gmail-Entwurf) |
| `Nach Absagegrund fragen für Job <id>` | Feedback-Nachfrage nach Absage (Gmail-Entwurf) |
| `Entscheider für Job <id>` / `wer ist der Hiring Manager bei <Firma>` | Fachentscheider + Vorbesetzung recherchieren |
| `Angebot bewerten für Job <id>` | Benefits-Punkteliste / Offer-Matrix (sobald Status „Angebot") |
Bestehende Sätze (`Tageslauf`, `Firma prüfen…`, `CV anpassen…`, `Deep-Dive…`, `prüf mein Postfach`,
`such nach neuen Stellen`) funktionieren unverändert — `Firma prüfen` liefert jetzt zusätzlich den
Abschnitt **„Arbeitgeber-Realität"** (kununu-Signal, echt-vs-behauptet-modern, Aktivität, Geschäftsentwicklung),
`CV anpassen` zusätzlich das **gewichtete Anforderungs-Matching** (Muss/Soll/Kann × 1–10 mit Beleg).

### 9. Berichte & Dateien (über die App abrufbar)
- **Absagen-Analyse:** `data/analysen/<Datum>_Absagen_Analyse.html` — die 5 Muster + Empfehlungen
  (Kurzfassung der Erkenntnisse steht auch in `config/profil.md` → „Empirie").
- **Vollständiges Paket je Stelle:** Company-Fit + Briefing (`data/interview_prep/…`) + angepasster CV + Anschreiben
  (`cv/cover/…`) — alles am Job-Detail verlinkt.

### 10. Woran du künftige Änderungen erkennst
Jede Bau-Session hinterlässt im Projektverlauf des Autors (nicht Teil des öffentlichen Repositorys) einen
abgehakten Plan + „Review“-Absatz (was, warum, wie verifiziert) — das ist das Änderungsprotokoll des Systems.
