#!/usr/bin/env python3
"""Repost-Erkennung: Text-Ähnlichkeits-Dedup für umbenannte Neuausschreibungen (Phase 44).

Echtfall (20.07.2026): eine Stelle („Stelle A") war ein REPOST einer anderen, bereits im
Interview stehenden Stelle („Stelle B") derselben Firma — LinkedIn hat dieselbe Anzeige mit
erweitertem Titel und neuer Job-ID erneut veröffentlicht. Der mechanische Dedup (dedup_key +
URL, s. normalize.py/ingest.py) vergleicht beides exakt — ändert sich beim Repost, die Dublette
rutschte durch, der Nutzer bewarb sich doppelt auf dieselbe reale Rolle.

Deterministisch, KEIN LLM. ZWEI kombinierte Signale (beide Pflicht — s. `titel_aehnlichkeit`-
Docstring für die Begründung, warum Text allein beim Bau NICHT ausreichte):
1. `titel_aehnlichkeit()` — Wort-Jaccard auf den TITELN (Pflicht-Vorfilter).
2. `aehnlichkeit()` — 5-Wort-Shingle-Jaccard auf dem rollen-relevanten ANZEIGENTEXT
   (`rollen_relevanter_text()`, aus dem Phase-38-Snapshot `job.posting_snapshot_path`).

Verdacht wird GEFLAGGT, nie automatisch verworfen (Human-in-the-Loop, s. Stufe B) — eine
False-Positive-Verwerfung würde eine echte neue Rolle still verlieren.

## Kalibrierungs-Historie (20.07.2026, drei Iterationen — s. tasks/todo.md Phase 44 für die
vollständige Beweisführung mit allen Zwischenständen):

1. **Naiver Ganzdokument-Vergleich scheiterte:** der echte Repost (der Echtfall von oben) scorte
   NIEDRIGER (0,03) als mehrere echte Nicht-Dubletten (0,14–0,25) — bei JEDER getesteten
   Shingle-Größe. Root Cause: Snapshot-Texte sind je nach Erfassungspfad entweder unabhängig
   LLM-paraphrasiert (→ echte Reposts driften textlich auseinander) oder roh/„unbereinigt"
   erfasst (→ enthalten variables Portal-Chrome, das über verschiedene Stellen hinweg mehr
   Überlappung erzeugt als der echte Anzeigeninhalt).
2. **Abschnitts-Filter (`rollen_relevanter_text`) verbesserte, löste aber nicht vollständig:**
   Firmen-Blurb/Benefits/Portal-Chrome ausgeschlossen hob den Score des Echtfalls auf 0,05 — aber
   ein SAUBERES (nicht kontaminiertes) Negativ-Paar (zwei verschiedene vertrauliche
   Executive-Search-Mandate desselben Headhunters, beide für dieselbe C-Level-Rolle) scorte
   trotzdem höher (0,33). Exec-Search-Ausschreibungen für denselben Rollentyp lesen sich
   sprachlich sehr ähnlich, auch wenn es echte unterschiedliche Mandate sind — keine
   Kontamination, sondern eine Eigenschaft des Genres.
3. **Titel-Pflicht-Vorfilter (finale Lösung):** Titel-Jaccard trennt sauber (der Echtfall 0,667 vs.
   höchstes Negativ-Paar 0,364 — Marge 0,30) UND fängt zusätzlich den verbliebenen
   Text-Fehlalarm ab (die beiden Executive-Search-Mandate teilen kaum Titel-Wörter mit
   einem DRITTEN, textlich unauffälligen Mandat). Erst wenn der Titel-Vorfilter passiert,
   entscheidet der Text-Score — genau das Verfahren, das ein Mensch intuitiv anwenden würde
   (erst grob nach Rollentyp filtern, dann den Inhalt vergleichen).
4. **Rohtext-Vorrang statt Abschnittsfilter (11.09.2026, P2-37, s.
   tasks/spec_p2-37_rohtext_textvergleich.md):** Anlass war eine echte Dublette bei einer Firma
   — der Textvergleich lag bei 0,9 % Ähnlichkeit, obwohl beide Anzeigen denselben Text trugen.
   Der ältere Snapshot war inzwischen von der Firmenprüfung angereichert (Aufgaben/
   Anforderungen als deutsche Zusammenfassung, danach „Volltext (unbereinigt)“ mit dem
   englischen Original) — der Abschnittsfilter behielt nur `^volltext$` EXAKT, „Volltext
   (unbereinigt)“ passte nicht, der Originaltext fiel weg. Verglichen wurde also deutsche
   Zusammenfassung gegen englisches Original, obwohl der Ingest-Kandidat (`kandidat_text()`)
   immer der VOLLE Rohtext ist — statt gleich gegen gleich.

   Maßgebliche Messung (V3, Abnahme-Korrektur 11.09., echte Ingest-Richtung: Kandidat = voller
   Rohtext, Bestand = `rollen_relevanter_text_aus()`, Schwelle 0,045): die bestätigten Dubletten
   liegen bei 100 %, 100 %, 75 %, 26 %, 21 % und 5 % (der letzte Fall
   ohne eigenen Rohtext, Rückfall auf den Abschnittsfilter) — alle sechs werden bei 0,045
   gemeldet, VOR P2-37 drei davon gar nicht.
   Verneinte bzw. beide beworben liegen bei 14–64 % — das Trennwerkzeug für Rollentypen bleibt
   der Titel-Vorfilter, nicht der Text (Vorlagen derselben Firma lesen sich textlich ähnlich,
   unabhängig von der Rohtext-Extraktion). Pool bei 0,045: 12 statt 6 Paare mit Hinweis; schon
   0,10 verliert den Fall ohne eigenen Rohtext (der Echtfall von oben).

   **Messfehler der ersten Kalibrierung (in dieser Fassung bereits korrigiert):** Dort lief der
   Ingest-Kandidat testweise durch dieselbe Extraktion wie der Bestand statt durch den echten,
   VOLLEN Kandidatenpfad — UND `rohtext_aus()` schnitt den Rohtext zusätzlich an jeder
   BEHALTEN-/VERWERFEN-Überschrift der Abschnitts-Filterung ab, die aber oft IM Anzeigentext
   selbst steht („Requirements“/„Aufgaben“/„Key Responsibilities“/„Qualifications“/„Benefits“
   — 127 von 381 gemessenen Rohtexten behielten dadurch weniger als die Hälfte; einer der
   bestätigten Fälle fiel in echter Ingest-Richtung auf 14 % statt 100 %). Korrektur: `rohtext_aus()`
   endet nur noch an `_ROHTEXT_ENDE` („Erfassungs-Kontext“/„Quellen“ — der tatsächlichen
   Vorlagen-Grenze beider Renderer vor jeder Zusammenfassung, gemessen an 361/6/8 von 381
   Snapshots), nicht mehr an `_ABSCHNITT_BEHALTEN`/`_ABSCHNITT_VERWERFEN`. Preis unverändert:
   ein Hinweis kostet einen Klick („Keine Dublette“), eine übersehene Wiederholung eine
   doppelte Bewerbung (Echtfall, s. Punkt 1 oben).
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import yaml
from sqlmodel import Session, select

from app import normalize as N
from app.db import artefakt_pfad, engine
from app.models import Job
from pipeline.htmltext import entkleiden

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Bewerbung_Mgmt_System/
CONFIG_FILE = PROJECT_ROOT / "config" / "suchprofile.yaml"

# Drittes Duplikat (main.py/ingest.py/hier) aus demselben Grund wie in ingest.py dokumentiert:
# main.py darf laut Phase-44-Whitelist nicht importiert werden, die Abhängigkeitsrichtung soll
# nicht umgedreht werden.
# Phase 85: "Keine Rückmeldung" ergänzt (Ghosting-Endstatus).
_TERMINAL_STATUSES = {"Absage", "Kein Match", "Nicht verfügbar", "Beirat abgelehnt", "Keine Rückmeldung"}

_WORT_RE = re.compile(r"[a-zäöüß0-9]+", re.IGNORECASE)


def text_aus_snapshot(pfad: str) -> str:
    """Anzeigen-Snapshot-HTML (projekt-relativer Pfad, z. B. job.posting_snapshot_path) zu
    Klartext, ROH (keine Abschnitts-Filterung — dafür `rollen_relevanter_text()`). Teilt sich
    den Stripper mit search_index.py (pipeline.htmltext.entkleiden), keine zweite
    HTML-Extraktion pflegen. Fehlende Datei → leerer String (kein Crash, der Aufrufer
    entscheidet über den Kurztext-Gate, was „kein Text" bedeutet)."""
    p = artefakt_pfad(pfad)
    # Phase 79: gemeinsame Auflösung (data/ → aktive Datenwurzel) statt PROJECT_ROOT — s. app/db.py::artefakt_pfad
    if not p.is_file():
        return ""
    raw = p.read_text(encoding="utf-8", errors="replace")
    return entkleiden(raw)


# ── Abschnitts-Filter (Kalibrierungs-Iteration 2) ─────────────────────────────────────────
# Snapshots kommen aus zwei Erzeugern mit unterschiedlicher Struktur: dem deterministischen
# Phase-38-Basis-Renderer (EIN Block „Anzeigentext (automatisch extrahiert, unbereinigt)") und
# der firma-pruefen-Anreicherung (LLM, strukturiert in Aufgaben/Anforderungen/Über das
# Unternehmen/Benefits/Volltext). BEHALTEN = rollenspezifischer Inhalt, VERWERFEN = Firma/
# Kontext/Footer — alles VOR dem ersten erkannten Marker ist Meta-Grid-Präambel (Firma/Ort/
# Gehalt-Label+Wert) und wird verworfen. Zeilen-exakt nach strip(), Groß/Klein ignoriert.
_ABSCHNITT_BEHALTEN = [re.compile(p, re.I) for p in (
    r"^aufgaben\b", r"^anforderungen\b", r"^main responsibilities:?$", r"^qualifications:?$",
    r"^key responsibilities:?$", r"^requirements:?$", r"^anzeigentext\b", r"^volltext\b",
)]
_ABSCHNITT_VERWERFEN = [re.compile(p, re.I) for p in (
    r"^über (das unternehmen|[a-zäöü]+:)$", r"^benefits:?$", r"^erfassungs-kontext$",
    r"^capture context$", r"^about the company$",
    r"^quellen$", r"^hinweis\b", r"^gehalt$",
)]
# Bekannte LinkedIn-Login-Wall-/Cookie-/Widget-Fragmente (11 von 66 Bestands-Snapshots
# betroffen, 20.07.2026 gemessen) — Teilstring-Erkennung, da LinkedIn Rollen-/Firmennamen in
# die Vorlage einsetzt (nie exakt gleiche Zeile). KEIN abschließender Anspruch — neue Varianten
# bei Bedarf ergänzen, das ist der bewusste Kompromiss ggü. einem fragilen HTML-Parser für eine
# fremde, sich ändernde Portal-Seite.
_PORTAL_CHROME_TEILSTRING = (
    "linkedin nimmt den schutz", "essenzielle und nicht zwingend erforderliche cookies",
    "weiter zum hauptinhalt", "suche erweitern", "werden sie mitglied",
    "passwort vergessen", "mit e-mail einloggen", "neu bei linkedin",
    "wenn sie auf „weiter“ klicken", "sehen sie, wen", "ähnliche jobs",
    "wen kennen sie bereits", "diesen job melden", "ihre eignung", "eignung mit ki",
    "weitere jobs bei", "jobempfehlungen", "nutzervereinbarung", "passwort einblenden",
    "loggen sie sich ein", "kenntnisse zu bewerten", "lebenslauf anzupassen",
)
# Unsere eigenen Template-Label (Meta-Grid/Nav) — auf JEDEM Snapshot identisch, tragen nie
# Rollen-Signal.
_RAUSCH_ZEILEN = {
    "anzeigen-snapshot", "stellenausschreibung", "stellenausschreibung · snapshot",
    "stellenausschreibungs-snapshot", "firma", "ort", "portal", "gehalt", "quelle",
    "original-url", "abrufdatum", "veröffentlicht", "work model", "seniorität",
    "jobs", "personen", "learning", "einloggen", "mitglied werden", "oder", "show more",
    "ort / modell", "karrierestufe", "tätigkeitsbereich", "branchen", "passwort",
    "einblenden", "ebenfalls angesehen", "original-text anzeigen/verbergen", "bewerben",
    "speichern", "akzeptieren", "ablehnen",
}

# ── Rohtext-Vorrang (P2-37, Kalibrierungs-Historie Punkt 4) ────────────────────────────────
# Beide Rohtext-Überschriften, die ein Snapshot tragen kann: der Basis-Renderer schreibt
# „Anzeigentext (automatisch extrahiert, unbereinigt)“, die firma-pruefen-Anreicherung
# „Volltext (unbereinigt)“ (oder knapp „Volltext“). `\b` statt `$`, weil beide Überschriften
# einen Klammer-Zusatz tragen — anders als _ABSCHNITT_BEHALTEN oben (dort bis P2-37 exakt
# `^volltext$`, s. 3.3) griff das nie.
_ROHTEXT_MARKER = re.compile(r"^(volltext|anzeigentext|full text|job posting text)\b", re.I)
# Korrektur 11.09. (Abnahme, s. Moduldocstring Punkt 4): NICHT dieselben BEHALTEN-/
# VERWERFEN-Marker wie der Abschnittsfilter zum Beenden verwenden — „Requirements“/„Aufgaben“/
# „Key Responsibilities“/„Qualifications“/„Benefits“ stehen oft IM Anzeigentext selbst (127 von
# 381 gemessenen Rohtexten hätten weniger als die Hälfte behalten; einer der bestätigten Fälle
# fiel in echter Ingest-Richtung auf 14 % statt 100 %). Beide Vorlagen setzen den Rohtext stattdessen
# als LETZTEN Inhaltsabschnitt vor „Erfassungs-Kontext“ (Basis-Renderer posting_snapshot.py;
# firma-pruefen: … → Volltext → Erfassungs-Kontext) — der einzige verlässliche Endpunkt
# (gemessen: 361/381 enden an „Erfassungs-Kontext“, 6 an „Quellen“, 8 ältere Snapshots ohne
# beides laufen bis zum Textende — in keinem folgt danach noch eine Zusammenfassung).
_ROHTEXT_ENDE = re.compile(r"^(erfassungs-kontext|quellen|capture context|sources)$", re.I)
# Gleicher Wert wie der Default von konfiguration()["min_text_zeichen"] — bewusst als eigene
# Modulkonstante dupliziert, nicht aus konfiguration() gelesen: `rollen_relevanter_text_aus()`
# ist eine reine Funktion ohne Config-/Dateizugriff (s. Docstring dort).
_ROHTEXT_MIN_ZEICHEN = 400


def _rauschen_filtern(text: str) -> str:
    """Zeilen-Filter für Portal-Chrome/eigene Template-Label — OHNE die Abschnitts-KEEP/
    DISCARD-Logik (die braucht strukturierte Aufgaben/Anforderungen-Marker, die im rohen,
    noch nicht in ein Snapshot-Template gegossenen Kandidatentext nicht existieren). Von
    `rollen_relevanter_text()` UND `kandidat_text()` genutzt — ein Filter, zwei Aufrufer."""
    behalten: list[str] = []
    for zeile in text.split("\n"):
        zt = zeile.strip()
        if not zt:
            continue
        zl = zt.lower()
        if zl in _RAUSCH_ZEILEN or any(m in zl for m in _PORTAL_CHROME_TEILSTRING):
            continue
        if zt.startswith("Bewerbungs-Mgmt"):
            continue
        behalten.append(zt)
    return "\n".join(behalten)


def kandidat_text(roh_anzeigentext: str) -> str:
    """Für einen frisch eingehenden Ingest-Record (Stufe B): der rohe Anzeigentext aus der
    `--texte`-Datei (`verify_jobs.check()`) hat noch KEINEN Snapshot-Pfad — er WIRD gerade
    erst der „Anzeigentext (automatisch extrahiert, unbereinigt)"-Karte des künftigen
    Snapshots entsprechen (s. posting_snapshot.py::_build_html). Deshalb nur den
    Rauschen-Filter anwenden (kein Abschnitts-Split nötig, der Text ist bereits auf
    Anzeigeninhalt beschränkt — anders als ein VOLLES, bereits gerendertes Snapshot-HTML mit
    Firma-Blurb/Benefits drumherum)."""
    return _rauschen_filtern(roh_anzeigentext or "")


def rohtext_aus(text: str) -> str:
    """Reine Textfunktion (P2-37 §3.2, Korrektur 11.09. aus der Abnahme, s. Moduldocstring
    Punkt 4): sammelt die Zeilen nach einer Rohtext-Überschrift (`_ROHTEXT_MARKER` —
    „Volltext…“/„Anzeigentext…“) bis zur nächsten VORLAGEN-Überschrift NACH dem Rohtext
    (`_ROHTEXT_ENDE` — „Erfassungs-Kontext“/„Quellen“); fehlt sie, läuft die Sammlung bis zum
    Textende. Bewusst NICHT an BEHALTEN-/VERWERFEN-Markern der Abschnitts-Filterung beenden
    (das war die erste, in der Abnahme korrigierte Fassung) — Überschriften wie „Requirements“/
    „Aufgaben“/„Key Responsibilities“/„Qualifications“/„Benefits“ stehen oft IM Anzeigentext
    selbst, nicht nur als Snapshot-Vorlagenmarker; ein Abbruch dort schnitt echten Rohtext ab.
    Eine weitere Rohtext-Überschrift beendet die Sammlung NICHT, sondern startet nur einen
    neuen Abschnitt — mehrere Rohtext-Abschnitte im selben Snapshot werden aneinandergehängt.
    Kein eigener Rausch-Filter beim Sammeln — der läuft einmal am Ende (`_rauschen_filtern`,
    geteilt mit `rollen_relevanter_text_aus()`/`kandidat_text()`)."""
    gesammelt: list[str] = []
    aktiv = False
    for zeile in text.split("\n"):
        zt = zeile.strip()
        if not zt:
            continue
        if _ROHTEXT_MARKER.match(zt):
            aktiv = True
            continue
        if aktiv and _ROHTEXT_ENDE.match(zt):
            aktiv = False
            continue
        if aktiv:
            gesammelt.append(zt)
    return _rauschen_filtern("\n".join(gesammelt))


def rollen_relevanter_text_aus(text: str) -> str:
    """Reine Textfunktion (P2-37 §3.1, kein Dateizugriff) — enthält die gesamte Logik von
    `rollen_relevanter_text()`. Rohtext-Vorrang (P2-37 §3.2, s. Moduldocstring Punkt 4): hat
    der Rohtext (`rohtext_aus()`) mindestens `_ROHTEXT_MIN_ZEICHEN` Zeichen, wird NUR er
    zurückgegeben — der Ingest-Kandidat (`kandidat_text()`) ist immer Rohtext, also Rohtext
    gegen Rohtext statt Rohtext gegen eine ggf. angereicherte Zusammenfassung. Sonst der
    bisherige Abschnittsfilter als Rückfall (z. B. der Echtfall von oben ohne Rohtext): nur
    rollenspezifischer Inhalt (Aufgaben/Anforderungen/unstrukturierter Anzeigentext),
    Firmen-Blurb/Benefits/Erfassungs-Kontext/Footer/Portal-Chrome/eigene Template-Label
    ausgeschlossen."""
    rohtext = rohtext_aus(text)
    if len(rohtext) >= _ROHTEXT_MIN_ZEICHEN:
        return rohtext

    behalten: list[str] = []
    aktiv = False
    for zeile in text.split("\n"):
        zt = zeile.strip()
        if not zt:
            continue
        if any(m.match(zt) for m in _ABSCHNITT_BEHALTEN):
            aktiv = True
            continue
        if any(m.match(zt) for m in _ABSCHNITT_VERWERFEN):
            aktiv = False
            continue
        if not aktiv:
            continue
        behalten.append(zt)
    return _rauschen_filtern("\n".join(behalten))


def rollen_relevanter_text(pfad: str) -> str:
    """`text_aus_snapshot()` + `rollen_relevanter_text_aus()` (P2-37 §3.1: dünne Hülle, die
    gesamte Logik liegt in der reinen Textfunktion oben — unveränderte Signatur für die
    Aufrufer `pipeline/ingest.py` Z. 292 und `scan()` hier). `text_aus_snapshot()` bleibt als
    roher Baustein für andere Zwecke bestehen (Muster wie search_index.py)."""
    return rollen_relevanter_text_aus(text_aus_snapshot(pfad))


def _normalisieren(text: str) -> list[str]:
    """lowercase, Satzzeichen raus, in Wörter zerlegt (Umlaute bleiben Wortzeichen)."""
    return _WORT_RE.findall(text.lower())


def _shingles(woerter: list[str], n: int) -> set[str]:
    if len(woerter) < n:
        return set()
    return {" ".join(woerter[i:i + n]) for i in range(len(woerter) - n + 1)}


def aehnlichkeit(text_a: str, text_b: str, shingle_woerter: int = 5) -> float:
    """Jaccard-Ähnlichkeit auf N-Wort-Shingles: |A∩B| / |A∪B|, 0.0–1.0.

    Reine Funktion ohne Config-Zugriff (direkt testbar). Der Kurztext-Gate (min_text_zeichen)
    ist bewusst NICHT hier drin — das ist eine Aufrufer-Entscheidung (s. `pruefen()`), diese
    Funktion soll immer einen ehrlichen Score liefern, auch für kurze Texte (nur eben einen
    wenig aussagekräftigen)."""
    a = _shingles(_normalisieren(text_a), shingle_woerter)
    b = _shingles(_normalisieren(text_b), shingle_woerter)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def titel_aehnlichkeit(titel_a: str, titel_b: str) -> float:
    """Wort-Jaccard (unigram, nicht Shingle — Titel sind zu kurz für 5-Wort-Fenster) auf den
    STELLENTITELN. PFLICHT-Vorfilter (Kalibrierungs-Iteration 3, s. Moduldocstring): reiner
    Text-Vergleich trennte echte Reposts nicht zuverlässig von sprachlich ähnlichen, aber
    echten anderen Ausschreibungen (z. B. zwei verschiedene Executive-Search-Mandate für
    denselben Rollentyp) — Titel-Überlappung ist das stärkere, robustere Signal (kalibriert:
    echter Repost 0,667, schlechtester Negativ-Fall 0,364 — Marge 0,30)."""
    a = set(_normalisieren(titel_a))
    b = set(_normalisieren(titel_b))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def konfiguration() -> dict:
    """`dedup_text`-Block aus config/suchprofile.yaml, mit denselben Defaults wie dort
    dokumentiert (falls der Block fehlt — z. B. in einem älteren Config-Stand)."""
    if not CONFIG_FILE.exists():
        raise SystemExit(f"{CONFIG_FILE} fehlt.")
    data = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
    cfg = data.get("dedup_text") or {}
    return {
        "schwelle": float(cfg.get("schwelle", 0.045)),
        "titel_schwelle": float(cfg.get("titel_schwelle", 0.45)),
        "min_text_zeichen": int(cfg.get("min_text_zeichen", 400)),
        "shingle_woerter": int(cfg.get("shingle_woerter", 5)),
    }


def pruefen(titel_a: str, text_a: str, titel_b: str, text_b: str,
           cfg: dict | None = None) -> float | None:
    """Kombinierte Prüfung — Titel-Vorfilter ZUERST (billig, entscheidet meist), Text-Ähnlichkeit
    nur wenn er passiert. Liefert `None`, wenn KEIN VERGLEICH MÖGLICH war (Titel-Vorfilter nicht
    bestanden, oder einer der Texte unter `min_text_zeichen` — s. Design-Entscheidung 3: „still
    überspringen, kein Fehler, kein Raten"). Sonst den rohen TEXT-Score (0.0–1.0) — der
    Schwellenvergleich (`score >= cfg['schwelle']`) ist bewusst NICHT hier drin, sondern
    Aufgabe des Aufrufers (Ingest-Hook in Stufe B), damit ein Test wie
    `pruefen(...) >= schwelle` von außen genauso lesbar bleibt wie `aehnlichkeit(...) >=
    schwelle` in Verifikation A — pruefen() unterscheidet sich von aehnlichkeit() NUR durch die
    zwei Vorfilter, nicht durch eine zusätzliche Schwellen-Entscheidung."""
    cfg = cfg or konfiguration()
    if titel_aehnlichkeit(titel_a, titel_b) < cfg["titel_schwelle"]:
        return None
    min_zeichen = cfg["min_text_zeichen"]
    if len(text_a) < min_zeichen or len(text_b) < min_zeichen:
        return None
    return aehnlichkeit(text_a, text_b, cfg["shingle_woerter"])


# ── Stufe C — Bestand-Scan (read-only) ─────────────────────────────────────────────────────
def _aktive_jobs_je_firma(session: Session) -> dict:
    """Gruppiert aktive Jobs (kein Tombstone, nicht-terminal, mit Snapshot) nach Firma —
    IDENTISCHE Poolbildung wie der Ingest-Hook (`pipeline/ingest.py`), damit der Bestand-Scan
    (Stufe C) dieselben Paare sieht, die der Ingest-Hook (Stufe B) für künftige Treffer
    automatisch prüft. Schlüssel `N.firma_key` (P2-39, statt `N.slug_parts`) — bereinigt um
    Rechtsform-/Regionszusätze, sonst würden zwei Schreibweisen derselben Firma (Echtfall
    „Beispiel“/„Beispiel GmbH“) hier in getrennten Töpfen landen und nie miteinander
    verglichen, obwohl der Ingest-Hook seit P2-39 genau das jetzt tut (s.
    tasks/spec_p2-39_firmen_schluessel.md)."""
    jobs_je_firma: dict = defaultdict(list)
    for j in session.exec(select(Job)).all():
        if j.posting_snapshot_path and not j.deleted_at and j.status not in _TERMINAL_STATUSES:
            jobs_je_firma[N.firma_key(j.company_name)].append(j)
    return jobs_je_firma


def scan(schwelle: float | None = None) -> dict:
    """Stufe C (Design-Entscheidung 6) — read-only Bestand-Scan: prüft aktive Jobs paarweise
    JE FIRMA gegen dieselbe `pruefen()`-Logik wie der Ingest-Hook und liefert einen Bericht.
    Handelt NIE selbst (Muster `cleanup scan`) — nur `select`-Queries, kein `session.add`/
    `commit`, kein Datei-Write. Werkzeug für ALTFÄLLE auf Zuruf; Neufälle fängt der Ingest-Hook
    (Stufe B) künftig automatisch beim Anlegen ab."""
    cfg = konfiguration()
    if schwelle is not None:
        cfg = {**cfg, "schwelle": schwelle}
    with Session(engine) as session:
        jobs_je_firma = _aktive_jobs_je_firma(session)

    firmen_mit_mind_2 = 0
    treffer = []
    for jobs in jobs_je_firma.values():
        if len(jobs) < 2:
            continue
        firmen_mit_mind_2 += 1
        texte = {j.id: rollen_relevanter_text(j.posting_snapshot_path) for j in jobs}
        for i in range(len(jobs)):
            for k in range(i + 1, len(jobs)):
                a, b = jobs[i], jobs[k]
                score = pruefen(a.title, texte[a.id], b.title, texte[b.id], cfg)
                if score is not None and score >= cfg["schwelle"]:
                    treffer.append({
                        "firma": a.company_name,
                        "job_a": {"id": a.id, "titel": a.title, "status": a.status},
                        "job_b": {"id": b.id, "titel": b.title, "status": b.status},
                        "text_aehnlichkeit_prozent": round(score * 100),
                    })
    treffer.sort(key=lambda t: -t["text_aehnlichkeit_prozent"])
    return {
        "schwelle_prozent": round(cfg["schwelle"] * 100, 1),
        "titel_schwelle_prozent": round(cfg["titel_schwelle"] * 100, 1),
        "firmen_mit_mind_2_aktiven_jobs": firmen_mit_mind_2,
        "anzahl_treffer": len(treffer),
        "treffer": treffer,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(prog="pipeline.dedup_text")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_scan = sub.add_parser("scan", help="read-only Bestand-Scan je Firma — ändert nichts")
    p_scan.add_argument("--schwelle", type=float, default=None,
                        help="Text-Schwelle überschreiben (Default aus config/suchprofile.yaml)")
    a = ap.parse_args()
    out = scan(schwelle=a.schwelle)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
