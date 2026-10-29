---
name: skills-sortieren
description: Ordnet automatisch importierte LinkedIn-Skills (bereich="LinkedIn (unsortiert)") kontextbasiert Themenbereichen zu — bevorzugt bestehende Bereiche, legt neue nur an, wenn nötig. Verschiebt nur, erfindet und benennt nichts um. Läuft headless, ausgelöst automatisch nach jedem ZIP-Import mit neuen Skills oder manuell über den Button "Skills neu einsortieren". Nutze diesen Skill bei "Skills automatisch sortieren".
---

# Skills automatisch sortieren

Gegenstück zum Sammelbereich, den `pipeline/linkedin_import.py` beim ZIP-Import anlegt: neue
Skills landen dort erstmal alle in `bereich="LinkedIn (unsortiert)"` (kein LLM im Import). Dieser
Skill holt sie kontextbasiert dort raus — bestehende Bereiche bevorzugt, neue nur wenn wirklich
nötig. Läuft
headless (Auto-Trigger nach ZIP-Import ODER manueller Button in der Profil-Seite), Ziel < 60 s
Laufzeit bei den üblichen Stückzahlen.

## Ablauf

### 1. Kontext laden
```sh
curl -s http://localhost:8000/api/profil
```
Aus der JSON-Antwort:
- `skills["LinkedIn (unsortiert)"]` — die zu sortierende Liste (je Skill `id`, `name`, `note`).
  **Fehlt dieser Key oder ist die Liste leer:** sofort mit der Kurzmeldung „Keine unsortierten
  Skills vorhanden." enden — kein Fehler, einfach nichts zu tun.
- Alle ÜBRIGEN Keys von `skills` — das sind die bereits bestehenden Themenbereiche.
- `profile.positionierung`, `profile.headline` — Kontext, wie der Nutzer sich selbst beschreibt.
- `werdegang` — Rollen/Firmen/Beschreibungen, zusätzlicher Kontext für plausible Bereiche.

### 2. Zuordnungstabelle bilden (auf einmal, nicht Skill für Skill)
Für ALLE unsortierten Skills gemeinsam eine Zuordnung `{skill_id: neuer_bereich}` entwerfen —
nicht Skill für Skill isoliert entscheiden, sonst entstehen leicht nahe-doppelte neue
Bereichsnamen für dieselbe Kategorie (z. B. „Kundenmanagement" vs. „Customer Management").

Je Skill:
- **Bestehenden Bereich bevorzugen**, wenn er inhaltlich passt (Skill-Name gegen die Namen der
  bestehenden Bereiche und deren bereits enthaltene Skills abgleichen).
- Sonst einen neuen, sinnvollen Bereich aus dem Kontext bilden — bezogen auf die
  Professional-Services-/Customer-Success-Domäne des Nutzers (Positionierung/Werdegang aus Schritt 1).
  Nicht die „Susanne"-Beispielnamen aus der Spec („Strategie & Führung" etc.) wörtlich
  übernehmen — die stammen aus einer fremden Demo-Instanz, nicht aus dem Feld des Nutzers.
- Kann ein Skill ehrlich keinem sinnvollen Bereich zugeordnet werden: in der Zuordnungstabelle
  weglassen (bleibt in „LinkedIn (unsortiert)") und in der Abschlussmeldung namentlich nennen —
  nicht raten, nur um die Liste leer zu bekommen.

### 3. Schreiben — Python-Einzeiler, NICHT roher curl `-d`
`bereich` ist LLM-generierter Freitext und kann Anführungszeichen/Sonderzeichen enthalten, die
ein einfach gequotetes `curl -d '...'` bricht (dieselbe Begründung, aus der `profil-einlesen`,
`gespraech-debrief` und `job-frage` für JEDE Freitext-Schreiboperation einen Python-Block statt
curl nutzen — Muster hier 1:1 übernommen, nur mit `urllib.request` statt direktem DB-Zugriff,
weil der PATCH-Endpunkt gebraucht wird, s. u.).

**⚠️ Dieselbe Begründung gilt für das Dict selbst (P2-15, Code-Review 2026-07-25):** ein `"` oder
`\` in einem `bereich`-Namen würde ein direkt im Heredoc getipptes Python-Dict-Literal genauso
brechen wie zuvor `curl -d`. Deshalb die Zuordnungstabelle aus Schritt 2 ZUERST als JSON-Datei
schreiben (Write-Tool, `data/tmp/skills_zuordnung.json`, `{"<skill_id>": "<bereich>", …}`) und im
Heredoc per `json.load` einlesen — NICHT als Python-Dict-Literal eintippen:

```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python - <<'PY'
import json
import urllib.request
from pathlib import Path

# {skill_id: neuer_bereich} — aus ../data/tmp/skills_zuordnung.json (Schritt 2), NICHT hier eingetippt
ZUORDNUNG = json.loads(Path("../data/tmp/skills_zuordnung.json").read_text(encoding="utf-8"))

for skill_id, bereich in ZUORDNUNG.items():
    req = urllib.request.Request(
        f"http://localhost:8000/api/profil/skills/{skill_id}",
        data=json.dumps({"bereich": bereich.strip()}).encode(),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    urllib.request.urlopen(req)
print(f"{len(ZUORDNUNG)} Skills gepatcht")
PY
```
`urllib.request` ist stdlib — kein `pip install` nötig (Eiserne Regel: keine neuen Pakete).
`PATCH /api/profil/skills/{id}` schreibt danach automatisch `config/profil_struktur.md` neu
(server-seitig, `_profil_struktur_schreiben`) — kein separater Schritt nötig.

### 4. Abschlussmeldung
Format wortwörtlich wie in der Spec vorgegeben:
„N Skills in M Bereiche einsortiert (davon K neue Bereiche: <Namen>)."
Blieben Skills unzugeordnet: zusätzlich ehrlich benennen, z. B. „— nicht zugeordnet: <Namen>
(zu unspezifisch)". ≤ 100 Wörter, keine Markdown-Überschriften in der Meldung selbst.

## Grenzen

- Fasst NUR Skills mit `bereich == "LinkedIn (unsortiert)"` an — bereits einsortierte (egal ob
  manuell oder aus einem früheren Lauf dieses Skills) bleiben unangetastet.
- Erfindet keine neuen Skills, benennt oder löscht keine bestehenden — reine Verschiebung
  zwischen Bereichen.
- Manuelles Hinzufügen (`POST /api/profil/skills`) triggert diesen Skill NIE — nur der
  ZIP-Import-Auto-Trigger und der manuelle „Skills neu einsortieren"-Button in der Profil-Seite
  lösen ihn aus. Die manuelle Datalist (bestehende Bereiche + neuer Bereich) bleibt unberührt.
- Filtert nach `bereich`, nicht nach `quelle` (spec-konform) — ein Skill, der manuell exakt in
  den Bereich „LinkedIn (unsortiert)" einsortiert wurde, würde beim nächsten Lauf ebenfalls
  erfasst. In der Praxis unwahrscheinlich, der Name liest sich nicht wie eine sinnvolle manuelle
  Kategorie.
- Race Conditions: der Lauf liest einmal, entscheidet, schreibt dann. Eine parallele manuelle
  Änderung an genau denselben Skills während der kurzen Laufzeit kann überschrieben werden —
  akzeptiertes, vernachlässigbares Risiko bei Solo-Nutzung, kein Locking gebaut.
- Idempotent: ein zweiter Lauf sortiert nur, was noch im Sammelbereich übrig ist — kein
  Doppel-Effekt bei mehrfachem ZIP-Import oder mehrfachem Klick auf den manuellen Button.
