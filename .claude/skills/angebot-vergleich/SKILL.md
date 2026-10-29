---
name: angebot-vergleich
description: Bewertet ein Jobangebot strukturiert gegen das Zielprofil des Nutzers und rote Linien (Benefits-Punkteliste mit Gewichtung) und vergleicht mehrere Angebote als Matrix — Vergütung (fix/variabel/Equity), Rolle/Scope, Remote-Regelung, Kultur-Fit, Sicherheit, Pendeln, Nebenleistungen. Erzeugt ein HTML-Artefakt unter data/analysen/. Nutze diesen Skill bei "Angebot bewerten für Job <id>", "Angebot vergleichen", "Offer-Vergleich", "Benefits bewerten", "soll ich das Angebot annehmen", sobald ein Job den Status Angebot hat.
---

# Angebot-Vergleich (Benefits-Punkteliste & Offer-Matrix)

Macht aus einem Bauchgefühl eine belastbare Entscheidung: **ein** Angebot wird gegen Zielprofil + rote
Linien geprüft; **mehrere** Angebote werden als gewichtete Matrix verglichen. Aktiviert sich, sobald
ein Job auf **Status „Angebot"** steht.

## Ablauf

### 1. Angebote einsammeln
```sh
curl -s "http://localhost:8000/api/jobs?status=Angebot"
```
Je Angebot die Konditionen vom Nutzer erfragen (nicht raten!): Fixum, variabel (OTE, Logik), Equity/VSOP,
Urlaubstage, Remote-Regelung/Präsenzpflicht, Titel + Reporting-Linie, Team-/Budget-Verantwortung,
Kündigungsfrist/Probezeit, Nebenleistungen (Auto/Mobility, bAV, Weiterbildung, Hardware), Startdatum.
Vorhandene Quellen nutzen: `firma-pruefen`-Dashboard (Situation/Risiken), `gut_feeling`, Interview-Notizen/Transkripte.

### 2. Benefits-Punkteliste (gewichtete Bewertung, je Kriterium 1–10)
| Kriterium | Standard-Gewicht |
|---|---|
| Gesamtvergütung (fix + realistisch variabel + Equity-Wert) | 3 |
| Rolle & Scope (Ebene, Mandat, Team-/Budget-Verantwortung — Flughöhen-Check!) | 3 |
| Remote-/Standort-Fit (rote Linie: kein Umzug; Onsite nur im aktiven Umkreis-Bucket aus `config/suchprofile.yaml`) | 3 |
| Zukunftssicherheit (Situation, Funding, Markt — aus firma-pruefen) | 2 |
| Kultur-Fit (Arbeitgeber-Realität, Interview-Eindruck, gut_feeling) | 2 |
| Entwicklung (Karrierepfad, Lernkurve, Sichtbarkeit) | 2 |
| Nebenleistungen (Urlaub, bAV, Mobility, Weiterbildung) | 1 |
| Pendel-/Reiseaufwand (Route/Häufigkeit) | 1 |
Gewichte sind Startwerte — mit dem Nutzer abstimmen, wenn er anders priorisiert. **Rote Linien sind K.-o.,
keine Punkte** (Umzugspflicht, IC-Zuschnitt, Scope-Downgrade → Angebot fällt durch, egal wie der Score ist).

### 3. Auswerten
- **Ein Angebot:** gewichteter Score in % + K.-o.-Check + die 3 stärksten/schwächsten Punkte + was
  nachverhandelt werden sollte (konkret, mit Begründung aus der Tabelle).
- **Mehrere Angebote:** Matrix (Kriterium × Angebot, gewichtete Summen) + Sensitivität („Angebot B gewinnt
  nur, wenn Equity ≥ X wert ist").
- Ehrlichkeit: Unbekanntes als „offen — nachfragen" führen, nicht schätzen.

### 4. Artefakt + Registrierung
Self-contained HTML im Look von `assets/report_theme_bms.html` (Phase 30 — Datei lesen und
das Muster wörtlich übernehmen: Aufbau und Klassen; kein CSS und keine Farbwerte abschreiben, der
Bericht entsteht ohne eigenen Style-Block) → `data/analysen/` mit
`dated_filename('Angebot_Vergleich_<Firma(n)>','html')` (abrufbar über `/api/artifact`).
**Kopf (Phase 35, `header.head`):** eyebrow „Analyse" → h1 „Angebotsvergleich" (bzw. Firmenname bei
genau einem Angebot) → sub kurze Einordnung („<N> Angebot(e) · Stand JJJJ-MM-TT") → Meta-Grid
„Zeitraum · Datensätze · Datum". Kern-Empfehlung zusätzlich in `job.notes` (PATCH), `next_step` z. B.
„Nachverhandeln: <Punkt>" + `follow_up_date` (Antwortfrist!).

**Pflichtschritt nach dem Schreiben** — erst den Stil einsetzen, dann prüfen:
```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.bericht_stil einsetzen "../data/analysen/<datei>.html" && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.report_check "../data/analysen/<datei>.html"
```
Meldet einer der beiden Befehle eine Klasse ohne Regel: die Klasse durch eine aus der Vorlage ersetzen
(kein eigenes CSS) und beide Befehle wiederholen.

### 5. Bericht an den Nutzer
Score/K.-o.-Ergebnis, Top-3-Erkenntnisse, Verhandlungs-Empfehlung, Link aufs Artefakt. **Keine
Annahme-/Absage-Entscheidung treffen** — die trifft der Nutzer; der Skill liefert die Grundlage.

## Abgrenzung
- Gehaltsverhandlungs-Briefing (Marktbenchmarks, Argumentationslinie) = separate 7.4-Idee — hier nur
  angebotsbezogene Hinweise.
- Firmen-Analyse = `firma-pruefen` (Voraussetzung, falls noch nicht gelaufen).
- Kein Versand, keine Zusagen — reine Entscheidungs-Vorbereitung.
