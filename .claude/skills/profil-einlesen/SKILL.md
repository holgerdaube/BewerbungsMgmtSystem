---
name: profil-einlesen
description: Liest ein LinkedIn-Profil per URL best-effort ein (kein Login, kein Login-Versuch) und füllt NUR belegbar öffentlich Sichtbares additiv in die Profil-Seite des Nutzers (Positionierung/Headline/Standort) — erfindet nichts, meldet die Login-Wall ehrlich statt zu raten. Nutze diesen Skill bei "Profil einlesen von <linkedin_url>".
---

# Profil einlesen (LinkedIn-URL, best effort)

Best-effort-Gegenstück zum robusten Weg (Datenexport-ZIP → `pipeline/linkedin_import.py`,
Upload in der Profil-Seite). LinkedIn-Profilseiten sind hinter einer Login-Wall — dasselbe
Problem wie bei `jobsuche`/`mail-jobsuche` dokumentiert. Dieser Lauf holt NUR, was ohne Login
tatsächlich lesbar ist, und sagt ehrlich, wenn das nichts oder wenig ist.

## Ablauf

### 1. Profilseite laden
```
WebFetch <linkedin_url>
```
**KEIN Login-Versuch, keine Zugangsdaten, kein Umgehen der Wall.** Prüfe, was zurückkommt:
- Reine Login-Shell/Auffordung sich anzumelden, kein echter Profilinhalt (der übliche Fall)
  → weiter mit Schritt 3 (ehrlicher Fehlbericht).
- Falls tatsächlich Klartext-Inhalt lesbar ist (z. B. Headline/Kurzbeschreibung in Meta-Tags
  oder einer öffentlich freigegebenen Profilvorschau): NUR diesen tatsächlich gelesenen Text
  weiterverwenden, nichts ergänzen oder interpretieren.

### 2. Nur bei echtem Inhalt: additiv speichern
Falls Schritt 1 verwertbaren Text lieferte (Headline, Kurzbeschreibung/Summary, Standort) —
**⚠️ NIE als Python-String-Literal einsetzen (P2-15, Code-Review 2026-07-25):** der gelesene Text
ist ungeprüfter Fremdtext von einer LinkedIn-Seite — ein `"` oder `\` darin würde das folgende
Python sonst brechen. Zuerst als JSON schreiben (Write-Tool, `data/tmp/profil_einlesen.json`,
`{"headline": "…", "standort": "…", "summary": "…"}`, leer lassen was Schritt 1 nicht lieferte),
dann im Heredoc per `json.load` einlesen (Muster `job-frage`/`gespraech-debrief`), NUR leere
Felder füllen:
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python - <<'PY'
import json
from datetime import date, datetime
from pathlib import Path
from sqlmodel import Session, select
from app.db import engine
from app.models import CareerEntry, Profile, ProfileFile, ProfileSkill

gelesen = json.loads(Path("../data/tmp/profil_einlesen.json").read_text(encoding="utf-8"))
HEADLINE = gelesen.get("headline") or ""
STANDORT = gelesen.get("standort") or ""
SUMMARY = gelesen.get("summary") or ""

with Session(engine) as s:
    p = s.get(Profile, 1) or Profile(id=1)
    aktualisiert = []
    # NUR setzen, was Schritt 1 TATSÄCHLICH gelesen hat, und NUR wenn das Feld noch leer ist —
    # additiv, nie überschreiben (Design-Entscheidung 4).
    if HEADLINE and not p.headline:
        p.headline = HEADLINE; aktualisiert.append("headline")
    if STANDORT and not p.standort:
        p.standort = STANDORT; aktualisiert.append("standort")
    if SUMMARY and not p.positionierung:
        p.positionierung = SUMMARY; aktualisiert.append("positionierung")
    if aktualisiert:
        p.linkedin_eingelesen_am = date.today().isoformat()
        p.updated_at = datetime.utcnow()
        s.add(p)
        s.commit()
        s.refresh(p)

        # Stufe D (Design-Entscheidung 3): config/profil_struktur.md bei JEDEM Profil-Save neu
        # erzeugen. Dieselbe Logik wie main.py::_profil_struktur_schreiben, hier dupliziert, weil
        # dieser Lauf ein EIGENER Prozess ist (kein main.py-Import — main.py zieht das komplette
        # FastAPI-Setup mit, s. pipeline/cleanup.py-Docstring für dieselbe Begründung an anderer
        # Stelle im Projekt).
        skills = s.exec(select(ProfileSkill).order_by(ProfileSkill.bereich, ProfileSkill.sort_order, ProfileSkill.id)).all()
        werdegang = s.exec(select(CareerEntry).order_by(CareerEntry.art, CareerEntry.sort_order, CareerEntry.id)).all()
        dateien = s.exec(select(ProfileFile).order_by(ProfileFile.created_at.desc())).all()
        z = ["# Profil-Struktur", "",
             "Automatisch aus der Profil-Seite erzeugt — NICHT von Hand editieren (wird beim "
             "nächsten Save überschrieben). Ergänzt `config/profil.md` (Such-Strategie) um die "
             "Kandidaten-Substanz für Matching/Anschreiben.",
             f"Stand: {datetime.utcnow().isoformat()}Z", "",
             "## Positionierung", (p.positionierung or "_(noch nicht erfasst)_"), "", "## Skills"]
        if not skills:
            z.append("_(noch keine erfasst)_")
        else:
            gruppen = {}
            for sk in skills:
                gruppen.setdefault(sk.bereich, []).append(sk)
            for bereich, items in gruppen.items():
                z.append(f"### {bereich}")
                z += [f"- {sk.name}" + (f" ({sk.note})" if sk.note else "") for sk in items]
                z.append("")
        z.append("## Werdegang")
        any_w = False
        for art in ("Beruf", "Ausbildung", "Zertifizierung", "Projekt", "Sonstiges"):
            eintraege = [w for w in werdegang if w.art == art]
            if not eintraege:
                continue
            any_w = True
            z.append(f"### {art}")
            for w in eintraege:
                zeit = " – ".join(x for x in (w.von, w.bis) if x)
                kopf = " · ".join(x for x in (w.rolle, w.firma, zeit) if x) or "–"
                z.append(f"- **{kopf}**")
                if w.beschreibung: z.append(f"  {w.beschreibung}")
                if w.referenzgeber or w.referenzdatum: z.append(f"  Referenz: {', '.join(x for x in (w.referenzgeber, w.referenzdatum) if x)}")
                if w.notiz: z.append(f"  Notiz: {w.notiz}")
            z.append("")
        if not any_w:
            z += ["_(noch keine Einträge)_", ""]
        z.append("## Zertifikate und Zeugnisse (Dateien)")
        if not dateien:
            z.append("_(noch keine angehängt)_")
        else:
            z += [f"- [{f.kind}] {f.filename}" + (f" — {f.note}" if f.note else "") + f" (`{f.file_path}`)" for f in dateien]
        from pathlib import Path
        pfad = Path.cwd().parent / "config" / "profil_struktur.md"   # cwd = backend/ (s. `cd` oben)
        pfad.write_text("\n".join(z) + "\n", encoding="utf-8")
    print("aktualisiert:", aktualisiert)
PY
```
Struktur-Daten (Werdegang/Skills) NIE aus dem URL-Weg schreiben — ohne Login sind Positions-/
Skills-Listen so gut wie nie lesbar, ein Rateversuch würde Falschdaten in den Werdegang
schreiben. Dafür ist der ZIP-Export da. Bei „nichts gefunden" (Login-Wall-Regelfall, s. u.)
bleibt `aktualisiert` leer — dann wird `profil_struktur.md` bewusst NICHT neu geschrieben
(kein Save ohne Änderung).

### 3. Abschlussmeldung = ehrlicher Bericht (das ist der Task-Result-Text)
- **Login-Wall-Fall (Regelfall):** klar benennen, dass die Seite ohne Login keinen Profilinhalt
  zeigt, NICHTS erfinden, und auf den robusten Weg verweisen: „LinkedIn zeigt ohne Login keinen
  Profilinhalt (Login-Wall) — bitte den Datenexport nutzen: LinkedIn → Einstellungen → ‚Get a
  copy of your data' → ZIP in der Profil-Seite hochladen." Kein Feld wurde geändert.
  Beispielhaft je nach Sichtbarkeit unterschiedliche Meldung, aber wörtlich unterscheiden zwischen
  „nichts sichtbar" und „diese Felder wurden ergänzt: …" — niemals einen Erfolg vortäuschen.
- **Teilerfolg:** knapp auflisten, was ergänzt wurde (Feld für Feld) und ausdrücklich
  erwähnen, dass die Struktur-Daten (Werdegang/Skills) davon NICHT betroffen sind und weiter
  nur über den ZIP-Weg kommen.
- ≤ 100 Wörter, keine Markdown-Überschriften (Muster `job-frage`/`job-deepdive`).

## Grenzen
- Kein Login, keine Zugangsdaten, keine Umgehung der Login-Wall — technische wie ToS-Grenze.
- Schreibt NIE Werdegang/Skills (nur `Profile`-Felder), NIE bereits gefüllte Felder.
- Genau ein Lauf pro Trigger, kein Retry (s. `agent_runner.PROMPTS["profil-einlesen"]`) — ein
  zweiter Versuch träfe dieselbe Login-Wall erneut.
