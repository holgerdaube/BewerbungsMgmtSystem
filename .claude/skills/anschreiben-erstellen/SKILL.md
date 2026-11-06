---
name: anschreiben-erstellen
description: Erzeugt für eine Stelle aus dem Bewerbungs-Management-System ein wahrheitstreues, firmenspezifisches Anschreiben (DE, EN, FR, IT, ES oder PT) mit Direktansprache — konkrete Ansprechperson statt "Sehr geehrte Damen und Herren", Scope-Zahlen statt Titel (Empirie-Regel), Top-3-Mehrwerte für genau diese Firma aus CV × Company-Fit. Speichert als .docx unter outputs/anschreiben/ und registriert es an der Bewerbung (Job-Detail → Bewerbung → Anschreiben). Nutze diesen Skill bei "Anschreiben für Job <id>", "Anschreiben erstellen", "Cover Letter für Job <id>", "Direktansprache für Job <id>", "schreib das Anschreiben".
---

# Anschreiben erstellen (Direktansprache)

Adressiert die typischen Absage-Muster (die belegten des Nutzers stehen, falls vorhanden, in `config/profil.md`
→ Empirie): es scheitert im **Papier-Screening**, bei **kalten Bewerbungen**, besonders beim **Sprung auf eine
höhere Ebene**. Darum: konkrete
Ansprechperson, firmenspezifischer Hook, **Scope statt Titel** — und ausschließlich echte Belege.

## Ablauf

### 1. Stelle laden
```sh
curl -s http://localhost:8000/api/jobs/<id>
```
Liefert `job` (Titel, URL, Sprache der Anzeige ableitbar), `company` (inkl. `fit_analysis_path`),
`contacts` (**Ansprechperson!**), `cv_versions` (tailored CV), `application` (falls schon vorhanden).

### 2. Quellen lesen
- **Company-Fit** (`fit_analysis_path`): Hook-Material — Situation, erklärte Lücke/Chancen, News. Fehlt er:
  `firma-pruefen` empfehlen, aber nicht blockieren (dann Stellenanzeige + kurze Web-Recherche).
- **CV**: aktuellster tailored CV (`cv_versions[].file_path`), sonst die Basis-CV-Fassung `data/cv_basis/base_<sprache>.docx` (`de`, `en`, `fr`, `it`, `es`, `pt`) in der Sprache der Anzeige — die Belege. Fehlt bei einer französischen, italienischen, spanischen oder portugiesischen Anzeige die Fassung dieser Sprache: nichts übersetzen, zuerst `base_en.docx` nehmen, falls vorhanden, sonst `base_de.docx`, und den Sprachbruch im Bericht nennen.
- **`config/profil.md`**: Kernpositionierung, harte Grenzen und, falls vorhanden, den **Empirie-Abschnitt**
  (Scope-Zahlen führen, die CV oder Profil belegen, etwa Umsatz, Backlog, Teamgröße, Zielerreichung).
- Zusätzlich **`config/profil_struktur.md`** heranziehen, falls vorhanden (strukturierte Kandidaten-Substanz —
  ergänzt profil.md; Positionierung/Skills/Werdegang/Zertifikate aus der Profil-Seite, Phase 45).
- **Stellenanzeige** (Snapshot zuerst: `job.posting_snapshot_path`, Karte „Anzeigentext …" oder Block
  „Volltext (unbereinigt)"; fehlt der Text, einmal
  `cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.posting_snapshot nachholen --job-id <id>`
  und den Snapshot neu lesen. Exit 0 heißt immer, dass der Originaltext jetzt im Snapshot steht, auch
  bei `"befund": "ABGELAUFEN"` (Portal geschlossen, Anzeige noch sichtbar). Nur bei Exit 3 zusätzlich
  `job.url` per WebFetch als Teilquelle):
  Sprache, Muss-Anforderungen, Formulierungen.

### 3. Ansprechperson bestimmen (Direktansprache-Prinzip)
- `contacts` nach Recruiter/Hiring Manager durchsuchen → namentliche Anrede.
- Keine bekannt? **NIE „Sehr geehrte Damen und Herren"** — stattdessen Team-Anrede
  („Liebes \<Firma>-Team" / „Dear \<Firma> Talent Team") und im Bericht empfehlen, vor dem Versand den
  Fachentscheider zu recherchieren (künftig eigener Baustein, Welle 2).
- Diese Team-Anrede gilt für Deutsch und Englisch. Auf Französisch, Italienisch, Spanisch und Portugiesisch
  gilt stattdessen die Tabelle in Schritt 4, keine Team-Anrede und keine eigene Abwandlung.

### 4. Anschreiben schreiben (≤ 1 Seite, 250–350 Wörter)

**Der Briefkopf ist NICHT deine Aufgabe (P2-24, 31.08.2026).** Name, Anschrift, Kontakt,
LinkedIn und die Ort-/Datumszeile setzt `cover_letter_render.py` deterministisch aus
`config/profil.md` davor. Fang deinen Text mit dem **Betreff** an. Schreibst du trotzdem einen
Kopf (erste Zeile = Name), wird er erkannt und behalten — doppelt kommt er nie.
Hintergrund: Bis heute stand der Briefkopf hier nur beiläufig in einer Klammer bei Schritt 5,
die klang, als erzeuge ihn der Renderer. Zwei Läufe am selben Tag gingen deshalb verschieden
aus; bei einem fehlte der Kopf komplett, und die Betreffzeile wurde stattdessen als
Absendername in 16 pt fett gesetzt.

Sprache = Sprache der Ausschreibung (Deutsch, Englisch, Französisch, Italienisch, Spanisch oder Portugiesisch; bei
gemischten Anzeigen die dominante Sprache des Fließtexts, nie die Sprache der Oberfläche). Aufbau:
1. **Betreff** mit exakter Rollenbezeichnung.
2. **Hook** (2–3 Sätze): firmenspezifischer Bezug aus Company-Fit/News — warum diese Firma, warum jetzt.
   Kein generisches „mit großem Interesse habe ich gelesen".
3. **Scope-Absatz**: Zahlen zuerst (Umsatzverantwortung, Backlog, Teamgröße, Zielerreichung) — adressiert
   einen Titel-Gap zur Zielebene im Screening.
4. **Top-3-Mehrwerte für DIESE Firma** als Bullets — aus dem Schnitt CV-Stärken × Firmen-Lücke (Company-Fit).
5. **Kultur-/Motiv-Satz** (ehrlich, kurz) + **CTA** (Gespräch anbieten).

**Anrede und Schlussformel landesüblich, keine wörtliche Übertragung deutscher Muster.** Auf Deutsch und auf
Englisch gelten die bisherigen Regeln (Schritt 3). In den anderen Sprachen:

| Sprache | Anrede ohne bekannte Person | Anrede mit Name | Schlussformel |
|---|---|---|---|
| Französisch | `Madame, Monsieur,` | `Madame <Name>,` / `Monsieur <Name>,` | `Cordialement,` oder der ausführliche Schlusssatz (`Veuillez agréer …`) |
| Italienisch | `Spettabile <Firma>,` | `Gentile <Name>,` | `Cordiali saluti` |
| Spanisch | `Estimados señores:` | `Estimado/a <Name>:` | `Atentamente,` |
| Portugiesisch | `Exmos. Senhores,` (Portugal) / `Prezados,` (Brasilien) | `Exmo./Exma. <Name>,` (Portugal) / `Prezado/a <Name>,` (Brasilien) | `Com os melhores cumprimentos,` (Portugal) / `Atenciosamente,` (Brasilien) |

Die Schlussformel steht als eigener Absatz, damit der Renderer sie erkennt, und darunter als letzte Zeile der
Name des Absenders. Die Anrede ohne bekannte Person wörtlich aus der Tabelle übernehmen. Portugiesisch folgt der Schreibweise
der Anzeige (Portugal oder Brasilien). Die Ort-/Datumszeile setzt `cover_letter_render.py` in der Landessprache
(nicht von Hand schreiben, wie bisher).

**Wahrheitstreue:** nur Belege, die im CV stehen; bekannte Lücken (`skill_gaps_pruefen` in `config/suchprofile.yaml`) nicht überschminken;
harte Grenzen (z. B. kein Umzug) nicht verstecken, aber nur thematisieren, wenn die Anzeige es aufwirft.

### 5. Registrieren + deterministisch rendern (Text → docx + PDF, EIN Weg)

**⚠️ Interpreter-Regel (headless-Allowlist, Echtfall vom 24.07.2026):** Bash-Kommandos
EXAKT in dieser Schreibweise: `~/.bewerbung_mgmt_venv/bin/python` — NICHT `python3`, NICHT
`"$HOME/…"` in Anführungszeichen, KEIN `source …/activate`, KEIN direktes `sqlite3` oder
`soffice`. Abweichende Schreibweisen scheitern im headless Lauf an der Permission-Allowlist
(damals: 50 Turns Improvisation, Registrierung + PDF blieben liegen).

Die .docx wird **NICHT von Hand gebaut** (kein eigenes python-docx-Skript) — der **Fließtext ist
die Quelle** (Phase 48): er speist das Inline-Textfenster in der Web-App UND das deterministische
Rendering. `pipeline/cover_letter_render.py` erzeugt daraus Layout-Standard 23.07. (Briefkopf aus
`config/profil.md` — Name + Kontaktzeile + LinkedIn, KEINE Rollen-Zeile, s. Schritt 4;
Ort/Datum rechts; Betreff
fett; Calibri 10,5; garantiert **EINE Seite** — Budget ~2.000–2.400 Zeichen Fließtext, lieber
den Hook kürzen) und ruft den zentralen Export (Konventions-Umbenennung + PDF) selbst auf:

**⚠️ Fließtext NIE als Python-String-Literal einsetzen (P2-15, Code-Review 2026-07-25):** ein `"`
oder `\` im Anschreiben (z. B. ein zitierter Firmenname, ein Gedankenstrich-Ersatz) würde das
folgende Python sonst brechen — im ungünstigen Fall syntaktisch gültig, aber unbeabsichtigt
verändern. Deshalb ZUERST den fertigen Text in eine Datei schreiben (Write-Tool,
`data/tmp/anschreiben_<id>.txt`), dann im Heredoc per `Path(...).read_text()` einlesen (Muster
`--body-file` bei `gmail_client draft`):
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python - <<'EOF'
from pathlib import Path
from sqlmodel import Session, select
from app.db import engine
from app.models import Application
JOB_ID, LANG = <id>, "<DE|EN|FR|IT|ES|PT>"
TEXT = Path("../data/tmp/anschreiben_<id>.txt").read_text(encoding="utf-8")
with Session(engine) as s:
    app = s.exec(select(Application).where(Application.job_id == JOB_ID)).first()
    if not app:
        app = Application(job_id=JOB_ID, status="Vorbereitet")
    app.cover_letter_text = TEXT
    app.cover_letter_language = LANG
    s.add(app); s.commit(); print("APP_ID", app.id)
EOF
# dann rendern + registrieren + PDF in EINEM Aufruf (Argument ist die JOB-ID, nicht die APP_ID):
~/.bewerbung_mgmt_venv/bin/python -m pipeline.cover_letter_render <id>
```
Status **„Vorbereitet"** = liegt bereit, noch nicht abgeschickt. Der Render-Lauf gibt die finalen
Namen als JSON zurück (`docx`, `pdf`, ggf. `pdf_fehler`). Danach zeigt das Job-Detail unter
**Bewerbung → Anschreiben** die Download-Links (.docx + .pdf), und beide erscheinen in
„Dateien & Dokumente". Beim tatsächlichen Absenden: Status auf „Beworben" + `applied_date` setzen.

### 6. Bericht an den Nutzer (Kompakt-Format — landet 1:1 in einer schmalen UI-Karte)
**Grundregel:** knapp. KEINE Markdown-Überschriften, keine Aufräum-/Temp-Datei-Prosa. Genau dieses Format:
- **Zeile 1 = das ALLERERSTE Zeichen der Meldung, KEINE Vorrede davor** (kein „Registrierung erfolgreich"/
  „Fertig" o. Ä.): `Anschreiben erstellt — <Sprache>`
- **maximal 1 Zusatzsatz:** Ansprechperson-Status (namentlich vs. Team-Fallback → vor Versand prüfen)
  ODER `pdf_fehler`-Hinweis, falls gesetzt.
- **Schlusszeile:** die **finalen Dateinamen** (docx + pdf aus dem Export).

Die ⬇-Links (docx/pdf) rendert die Web-App unter der Meldung. **Entwurf** — nichts wird automatisch verschickt.

## Abgrenzung
- **Kein CV-Rewrite** (`cv-match`/`cv-erstellen`) und **keine Firmen-Analyse** (`firma-pruefen`).
- **Kein Versand** — das Anschreiben ist eine Datei; bewerben tut der Nutzer.
- Initiativbewerbungen (ohne ausgeschriebene Stelle) laufen über den Initiativ-Workflow (Welle 1 ③),
  nutzen aber diesen Skill für den Text.
