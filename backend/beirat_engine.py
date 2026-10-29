"""Beirats-Debatten-Engine (18.07.2026) — live orchestrierte Debatte des Bewerbungs-Beirats.

Architektur-Entscheidungen (bewusst, bitte nicht "vereinfachen"):
- Personas = `.claude/agents/beirat-*.md` — EINE Quelle der Wahrheit für den interaktiven
  Weg (/beirat-basis in Claude-Sessions) UND diese Web-Engine. Keine Kopien.
- Anthropic-Turns laufen über das **Agent SDK im Headless-Modus** (`claude -p
  --output-format stream-json --include-partial-messages`). Das venv ist Python 3.9, das
  pip-Paket `claude-agent-sdk` verlangt >=3.10 — der CLI-Headless-Modus ist die offizielle
  SDK-Schnittstelle und läuft OHNE Key aufs Abo; ein in der App hinterlegter
  ANTHROPIC_API_KEY wird als Env durchgereicht (nie hartkodiert).
- OpenAI-Turns (optional, Key nötig) via httpx-Streaming — kein neues Paket.
- Die Vorsitzende (Brandt) orchestriert AUTONOM: Sie entscheidet nach jedem Beitrag, WER als
  Nächstes mit WELCHER gezielten Frage drankommt (Charta: namentlicher Dispatch, MiroFish).
  Kein starres Round-Robin — genau daraus entsteht die live sichtbare Dynamik.
- `min_beitraege` ist ein hartes Gate: Vorher darf die Vorsitzende nicht abschließen.
  Harte Obergrenze = min*1.5+2 (Ausreißer-Bremse, Muster Phase 8.4).
- Keys liegen in `~/.bewerbung_beirat/keys.json` (chmod 600) — außerhalb Projekt & iCloud.
- Persistenz als JSON unter `data/beirat/` — bewusst KEINE DB-Tabelle (kein Schema-Change);
  aktive Debatten leben in einem In-Memory-Registry, die SSE-Queue hängt daran.
- Turns laufen mit cwd=~/.bewerbung_beirat/work (leerer Ordner), damit die CLI NICHT die
  BMS-CLAUDE.md/Skills lädt — die Persona soll pur sprechen.
- Phase 62B: Ein `result`-Event mit `is_error` wirft (statt die Fehlermeldung als Beitragstext
  zurückzugeben, s. `_result_event_auswerten`). Dispatch- und Persona-Turn haben dafür je
  "1 Versuch + 1 Retry" (Muster wie Abstimmung/Synthese) — bleibt der Dispatch danach kaputt,
  bricht die Debatte ehrlich ab; ein Persona-Kopf wird stattdessen ausgelassen, die Debatte
  läuft weiter (sonst würde reine Fehlererkennung ohne Retry mehr Debatten sterben lassen als
  vorher, s. tasks/spec_phase62_beirat_budget_fehler.md).
- Phase 77 (Echtfall 07.08.2026 09:16): EIN Auth-Weg für alle headless-`claude`-
  Läufe im System. Vorher strippte `_turn_anthropic()` vor jedem Turn ALLE `CLAUDE*`-Variablen
  (Identitäts-Trennung, bleibt so) und warf damit auch das stabile `CLAUDE_CODE_OAUTH_TOKEN` aus
  `agent.env` weg — ohne `keys.json`-Key fiel der Turn auf die fragile Keychain-Abo-Session
  zurück, deren Access-Token beim Ablauf refresht (Refresh-Token wird dabei ROTIERT). Zwei
  gleichzeitig gestartete Debatten trafen so auf ein abgelaufenes Access-Token, refreshten
  parallel, die Rotation invalidierte die Session dauerhaft ("could not be refreshed"). Jetzt:
  `_turn_env()` reicht das Runner-Token gezielt NACH dem Stripping durch (Auth-Priorität
  keys.json-Key > agent.env-Token > Keychain, s. `_bestimme_auth_weg()`); nur im verbleibenden
  Keychain-Fall läuft vor dem ersten Turn einer Debatte eine serielle Vorwärm-Schleuse
  (`_keychain_vorwaermen()`, Lock + 5-Minuten-Erfolgscache) gegen genau dieses Refresh-Race.
  Auth-Fehlertexte werden je Auth-Weg in Klartext übersetzt (`_auth_fehler_uebersetzen()`) statt
  als kryptischer CLI-Rohtext in `AgentTask.error`/`Debatte.fehler` zu landen. Details/Ist-Analyse:
  tasks/spec_phase77_beirat_auth.md.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx
from sqlmodel import Session

from app import agent_runner  # Phase 77: ENV_FILE zur LAUFZEIT übers Modul lesen (s. _headless_token)
from app.agent_runner import LOG_DIR as AGENT_LOG_DIR, modell_fuer_beirat, neue_log_datei
from app.db import artefakt_pfad, engine
from app.models import AgentTask, JobFile
from app.naming import report_filename
from pipeline import zustandsfarben
from pipeline.htmltext import entkleiden
from app.favicon import favicon_link
from pipeline.bericht_stil import DRUCK_SEITENFARBE_BEHALTEN, bericht_css

PROJEKT_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = PROJEKT_ROOT / ".claude" / "agents"
CHARTA_PFAD = PROJEKT_ROOT / "docs" / "BEIRAT-CHARTA.md"
DATEN_DIR = PROJEKT_ROOT / "data" / "beirat"
# AGENT_LOG_DIR = agent_runner.LOG_DIR (importiert, s. o.) — Phase 42: EIN Log-Ordner für ALLE
# Aktivitäten, Runner-Prozess wie In-Server-Engine. Seit Phase 63B liegt er außerhalb von
# Projekt & iCloud (Override BMS_LOG_DIR) — der Import garantiert, dass beide NIE
# auseinanderlaufen, statt die Env-Override-Logik ein zweites Mal zu duplizieren.
NOTBREMSE_USD = 15.0  # Ausreißer-Bremse je Lauf, gleiche Philosophie/Höhe wie agent_runner.MAX_BUDGET_USD
KEY_DIR = Path.home() / ".bewerbung_beirat"
KEY_PFAD = KEY_DIR / "keys.json"
WORK_DIR = KEY_DIR / "work"          # leeres cwd für CLI-Turns (kein Projekt-Kontext)


def _claude_bin_ermitteln() -> str:
    """Pfad zur Claude-CLI — Env-Override, dann PATH, dann der bisherige feste Pfad.

    Phase 100: Bis hierher stand hier NUR `~/.local/bin/claude` (macOS-Installationsort). Auf
    einer Windows-Neuinstallation existiert dieser Pfad nie — die CLI liegt dort nach
    `npm install -g` unter `%APPDATA%\\npm\\claude.cmd` — und der Beirat meldete deshalb
    dauerhaft `cli_verfuegbar: False`, ohne dass eine Einstellung geholfen hätte. Reihenfolge
    und Env-Name identisch zu `agent_runner.CLAUDE_BIN`, damit BEIDE CLI-Aufrufpfade des
    Systems mit derselben Variable umgebogen werden; die PATH-Suche steht davor, weil sie unter
    Windows `.cmd`/`.exe` über PATHEXT mitfindet.
    """
    explizit = os.environ.get("CLAUDE_BIN")
    if explizit:
        return explizit
    im_pfad = shutil.which("claude")
    if im_pfad:
        return im_pfad
    return str(Path.home() / ".local" / "bin" / "claude")


CLAUDE_BIN = _claude_bin_ermitteln()

VORSITZ_ID = "beirat-vera-brandt"    # Brandt moderiert; ihre Fach-Brille ist ein normaler Kopf
MAX_TURN_SEKUNDEN = 300
# Phase 80: Palette = Styleguide v5 §18.10 (Rollback: tasks/spec_phase80_styleguide_v18_theme.md)
FARBEN = {                           # feste UI-Farben je Kopf (Frontend nutzt sie 1:1)
    "beirat-vera-brandt": "#00B4D8", "beirat-ingrid-salvesen": "#7C4DFF", "beirat-adrian-osei": "#0B1F3A",
    "beirat-mateo-vidal": "#0EA5A4", "beirat-ray-calloway": "#5E7894",
    "beirat-felicity-marsh": "#C4478C", "beirat-katrin-vollmer": "#5B61E6",
}

# ── Stellen-Check (Phase 40) — Scoring & Abstimmung nach docs/BEIRAT-CHARTA.md ────────────────
# "Stellen-Check: Scoring & Abstimmungsverfahren". Gewichte + Reihenfolge sind Charta-Wortlaut.
ABSTIMMUNGS_BEREICHE = ["rollenfit", "cv_ergebnisse", "unternehmen",
                        "uebertragbarkeit", "karrierewirkung", "interview_chance"]
GEWICHTE = {"rollenfit": 0.20, "cv_ergebnisse": 0.20, "unternehmen": 0.20,
            "uebertragbarkeit": 0.15, "karrierewirkung": 0.15, "interview_chance": 0.10}
BEREICHS_LABEL = {
    "rollenfit": "Fachlicher/funktionaler Rollenfit", "cv_ergebnisse": "Nachweisbare CV-Ergebnisse",
    "unternehmen": "Unternehmen/Geschäftsmodell", "uebertragbarkeit": "Übertragbarkeit der Erfahrungen",
    "karrierewirkung": "Langfristige Karrierewirkung", "interview_chance": "Chance auf Interview/Angebot",
}
BEREICHS_KURZ = {   # für enge Tabellenspalten (Abstimmungs-Matrix)
    "rollenfit": "Rollenfit", "cv_ergebnisse": "CV-Ergebnisse", "unternehmen": "Unternehmen",
    "uebertragbarkeit": "Übertragb.", "karrierewirkung": "Karriere", "interview_chance": "Interview",
}
STIMMEN_WERTE = ("Bewerben", "Bedingt", "Nicht")

# ── Personas laden ────────────────────────────────────────────────────────────────────

def _frontmatter_parsen(text: str) -> tuple[str, str] | None:
    """Zerlegt eine Persona-Datei in (Frontmatter-Rumpf ohne die `---`-Grenzen, Body). Gemeinsame
    Naht für `lade_mitglieder()` UND die B2-Schreibfunktionen unten — beide dürfen NIE eigene,
    leicht abweichende Regexe pflegen, sonst könnte ein Leseweg etwas parsen, das der Schreibweg
    anders zurückschreibt."""
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    return (m.group(1), m.group(2)) if m else None


def _frontmatter_feld(front: str, k: str) -> str | None:
    """EIN Feld aus dem Frontmatter-Rumpf lesen, symmetrische An-/Ausführungszeichen (einfach
    ODER doppelt) abstreifen — `farbe: "#00B4D8"` liefert `#00B4D8`, nicht die Anführungszeichen
    mit. Reine Zeilen-Werte (kein YAML-Parser nötig, das Frontmatter ist bewusst flach)."""
    fm = re.search(rf"^{k}:\s*(.+)$", front, re.M)
    if not fm:
        return None
    wert = fm.group(1).strip()
    if len(wert) >= 2 and wert[0] == wert[-1] and wert[0] in "\"'":
        return wert[1:-1]
    return wert


def lade_mitglieder() -> list[dict]:
    """Alle beirat-*.md parsen: Frontmatter (name/description/model/farbe/vorsitz) + Body als
    Persona. Phase 90: `farbe`/`vorsitz` kommen bevorzugt aus dem Frontmatter (Design-Entscheidung
    1 — die Datei ist die einzige Quelle der Wahrheit); `FARBEN`/leeres `vorsitz` bleiben NUR
    Fallback für Altbestand ohne die neuen Felder. `perspektive` liefert die VOLLE `description`
    (ungekürzt, für die Einstellungen-Karte, B1) — `beschreibung` bleibt wie bisher auf 300
    Zeichen gekappt (Live-Ansicht der Debatte, unverändertes Verhalten)."""
    out = []
    for f in sorted(AGENTS_DIR.glob("beirat-*.md")):
        geparst = _frontmatter_parsen(f.read_text(encoding="utf-8"))
        if not geparst:
            continue
        front, body = geparst
        name_id = _frontmatter_feld(front, "name") or f.stem
        # Anzeigename aus der Rollen-Zeile ("Du bist **<Name>** (…)")
        nm = re.search(r"Du bist \*\*(.+?)\*\*", body)
        anzeige = nm.group(1) if nm else name_id.replace("beirat-", "").title()
        beschreibung_voll = _frontmatter_feld(front, "description") or ""
        out.append({
            "id": name_id, "anzeige": anzeige,
            "beschreibung": beschreibung_voll[:300],
            "perspektive": beschreibung_voll,
            "model": _frontmatter_feld(front, "model") or "sonnet",
            "farbe": _frontmatter_feld(front, "farbe") or FARBEN.get(name_id, "#64748b"),
            "vorsitz": (_frontmatter_feld(front, "vorsitz") or "").strip().lower() == "true",
            "persona": body.strip(),
        })
    return out


def vorsitz_id(mitglieder: dict[str, dict] | list[dict]) -> str:
    """ID des Mitglieds mit `vorsitz: true` im Frontmatter (Phase 90, A2 — ersetzt die vorherige
    hart verdrahtete Konstante als PRIMÄREN Weg). Ist keines markiert oder sind es mehrere —
    beides ein Datenfehler, den B2 beim Schreiben verhindert, den eine von Hand editierte Datei
    aber trotzdem herstellen kann —, greift `VORSITZ_ID` als Fallback UND es gibt eine laute
    Warnung ins Task-Log (Muster: der `print(f"[beirat] KRITISCH: …")` in `Debatte.laufen()`s
    finally-Block). Ohne Vorsitz kann die Engine nicht dispatchen (`_vorsitz_system()` braucht
    IMMER genau einen Namen) — deshalb hier niemals werfen, sondern robust auf die Konstante
    zurückfallen und laut sein, statt die ganze Debatte an einem Frontmatter-Tippfehler
    scheitern zu lassen."""
    alle = mitglieder.values() if isinstance(mitglieder, dict) else mitglieder
    markiert = [m["id"] for m in alle if m.get("vorsitz")]
    if len(markiert) == 1:
        return markiert[0]
    grund = "kein Mitglied markiert" if not markiert else f"{len(markiert)} Mitglieder markiert ({', '.join(markiert)})"
    print(f"[beirat] WARNUNG: vorsitz_id() — {grund}, Fallback auf VORSITZ_ID={VORSITZ_ID!r}. "
          "Frontmatter der Beirats-Personas prüfen (genau EIN `vorsitz: true` erwartet).", flush=True)
    return VORSITZ_ID


# ── Mitglieder-Verwaltung — Metadaten-PATCH (Phase 90, B2) ────────────────────────────
# Schreibt AUSSCHLIESSLICH das Frontmatter neu (Marker-Prinzip wie
# pipeline/suchprofil.py::schreibe_suchprofile — hier ist der Marker die `---`-Frontmatter-
# Grenze statt eines `# MARKER`-Kommentars); der Body bleibt byte-genau erhalten. Die 8 KB
# kalibrierter Persona-Text je Kopf sind das Wertvollste am ganzen Feature (Spec-Fallstricke) —
# jede Funktion hier fasst den Body NUR in der einen dokumentierten Ausnahme an
# (`_anzeige_umbenennen`).

class MitgliedNichtGefunden(LookupError):
    """PATCH-/Neubesetzungs-Ziel existiert nicht — main.py übersetzt dies in HTTP 404."""


class MitgliedFehler(ValueError):
    """Eingabefehler beim Ändern eines Beiratsplatzes (Farbe/Vorsitz/Perspektive/Anzeige) —
    main.py übersetzt dies 1:1 (Meldungstext ist bereits nutzerfertig) in HTTP 422."""


_HEX_FARBE_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _mitglieder_dateien() -> dict[str, Path]:
    """id → Pfad, dieselbe Auflösung wie `lade_mitglieder()` (Frontmatter-`name`, sonst
    Datei-Stamm), aber mit dem Pfad statt der geparsten Persona — Grundlage für B2, das gezielt
    EINE Datei anfassen muss, ohne den kompletten Persona-Text ein zweites Mal zu parsen."""
    out = {}
    for f in sorted(AGENTS_DIR.glob("beirat-*.md")):
        geparst = _frontmatter_parsen(f.read_text(encoding="utf-8"))
        if not geparst:
            continue
        front, _body = geparst
        name_id = _frontmatter_feld(front, "name") or f.stem
        out[name_id] = f
    return out


def _frontmatter_feld_setzen(pfad: Path, feld: str, wert: str) -> None:
    """Setzt/ergänzt EIN Feld im Frontmatter einer Persona-Datei; der Body bleibt dabei
    byte-genau unangetastet. Existiert das Feld schon, wird nur der Wert ersetzt; sonst wird die
    Zeile ans Ende des Frontmatters angehängt — genau so sind `farbe`/`vorsitz` in Stufe A3
    selbst entstanden, ein neu geschriebenes Feld reiht sich also stilgleich ein."""
    text = pfad.read_text(encoding="utf-8")
    geparst = _frontmatter_parsen(text)
    if not geparst:
        raise MitgliedFehler(f"„{pfad.name}“ hat kein gültiges Frontmatter — Datei beschädigt?")
    front, body = geparst
    zeilen = front.split("\n")
    neue_zeile = f"{feld}: {wert}"
    for i, z in enumerate(zeilen):
        if re.match(rf"^{feld}:\s*", z):
            zeilen[i] = neue_zeile
            break
    else:
        zeilen.append(neue_zeile)
    pfad.write_text("---\n" + "\n".join(zeilen) + "\n---\n" + body, encoding="utf-8")


def _anzeige_umbenennen(pfad: Path, neue_anzeige: str) -> None:
    """Zieht beim Umbenennen die EINE Body-Zeile „Du bist **<Name>**“ auf den neuen Namen mit —
    sonst widersprechen sich Anzeige (Frontend/DB-Ableitung) und System-Prompt (Body). Exaktes
    Ersetzen, genau eine Fundstelle (Spec-Vorgabe); taucht die Rollen-Zeile nicht in der
    erwarteten Form auf, bleibt der Body lieber unangetastet, als an der falschen Stelle zu
    raten — dann läuft nur die Anzeige (aus dem Frontmatter-`name` abgeleitet) auseinander, was
    harmlos ist, statt den kalibrierten Text zu beschädigen."""
    text = pfad.read_text(encoding="utf-8")
    geparst = _frontmatter_parsen(text)
    if not geparst:
        raise MitgliedFehler(f"„{pfad.name}“ hat kein gültiges Frontmatter — Datei beschädigt?")
    front, body = geparst
    nm = re.search(r"Du bist \*\*(.+?)\*\*", body)
    if nm and nm.group(1) != neue_anzeige:
        body = body.replace(f"Du bist **{nm.group(1)}**", f"Du bist **{neue_anzeige}**", 1)
    pfad.write_text("---\n" + front + "\n---\n" + body, encoding="utf-8")


UEBERNAHME_DIR = PROJEKT_ROOT / "data" / "tmp" / "beirat_neubesetzung"
BACKUP_DIR = DATEN_DIR / "personas_backup"
PFLICHT_ABSCHNITTE = (
    "# Rolle im Beirat", "# Mentales Betriebssystem", "# Frameworks, Prinzipien & Formeln",
    "# Charakteristische Prüffragen", "# Was wir an dir schätzen", "# Grenzen & blinde Flecken",
    "# Im Austausch (MiroFish)", "# Ton & Sprache",
)
PERSONA_MIN_BYTES = 4000
PERSONA_MAX_BYTES = 20000


def _kurzpfad(pfad: Path) -> str:
    """Projekt-relativer Pfad für Meldungen — faellt auf den absoluten zurueck, wenn der Pfad
    ausserhalb liegt (`relative_to` wirft dort). Betrifft real nur Tests, die die Verzeichnisse
    auf ein tmp-Verzeichnis biegen; eine Meldung darf daran nie scheitern."""
    try:
        return str(pfad.relative_to(PROJEKT_ROOT))
    except ValueError:
        return str(pfad)


def _persona_pruefen(text: str, erlaubte_ids: set[str]) -> str:
    """Validiert eine übergebene Persona-Datei und liefert ihre Platz-ID zurück.

    Wirft `MitgliedFehler` mit nutzerfertigem Text, wenn etwas nicht stimmt. Die Prüfung ist
    bewusst streng: Über diesen Weg gelangt Inhalt aus einem Skill-Lauf in `.claude/agents/`,
    also an eine Stelle, die die Sandbox dem Lauf selbst verwehrt (s. Modul-Kommentar bei
    `uebernehme_neubesetzung`). Erlaubt ist deshalb ausschließlich eine vollständige Persona
    für einen EXISTIERENDEN Platz.
    """
    laenge = len(text.encode("utf-8"))
    if not PERSONA_MIN_BYTES <= laenge <= PERSONA_MAX_BYTES:
        raise MitgliedFehler(
            "Persona-Datei hat " + str(laenge) + " Bytes — erwartet werden "
            + str(PERSONA_MIN_BYTES) + " bis " + str(PERSONA_MAX_BYTES)
            + " (eine vollständige Persona ist rund 8 KB groß)")
    geparst = _frontmatter_parsen(text)
    if not geparst:
        raise MitgliedFehler("Persona-Datei hat kein gültiges Frontmatter")
    front, body = geparst
    platz_id = _frontmatter_feld(front, "name")
    if not platz_id:
        raise MitgliedFehler("Im Frontmatter fehlt das Feld `name` (die Platz-ID)")
    if platz_id not in erlaubte_ids:
        raise MitgliedFehler(
            "`name: " + platz_id + "` ist kein bestehender Beiratsplatz — über diesen Weg "
            "lassen sich nur vorhandene Plätze neu besetzen, keine neuen anlegen")
    fehlend = [a for a in PFLICHT_ABSCHNITTE if a not in body]
    if fehlend:
        raise MitgliedFehler("In der Persona fehlen Pflichtabschnitte: " + ", ".join(fehlend))
    return platz_id


def uebernehme_neubesetzung(platz_id: str) -> dict:
    """Übernimmt die Ergebnisse eines `beirat-persona`-Laufs nach `.claude/agents/`.

    WARUM ÜBER DEN SERVER (Testlauf 1162, 23.08.2026): Der Skill-Lauf kann die Dateien nicht
    selbst ablegen — jeder Schreibversuch nach `.claude/` wird von der Sandbox abgelehnt
    (Selbstmodifikations-Schutz von Claude Code, keine Einstellungsfrage). Schreiben nach
    `data/` funktioniert. Der Lauf legt deshalb alles unter `data/tmp/beirat_neubesetzung/` ab
    und ruft anschließend diesen Weg über die API; der Server-Prozess unterliegt der Sandbox
    nicht.

    Erwartet wird in `UEBERNAHME_DIR`: die neue Persona für `platz_id` und optional die
    überarbeiteten Dateien der übrigen Köpfe (deren Verweise auf den ersetzten Kopf der Lauf
    repariert hat). Jede Datei wird einzeln validiert (`_persona_pruefen`); schlägt EINE fehl,
    wird NICHTS übernommen — ein halb ausgetauschtes Ensemble mit toten Verweisen wäre
    schlimmer als ein fehlgeschlagener Lauf.

    Jede ersetzte Datei wird vorher nach `data/beirat/personas_backup/` gesichert.
    """
    dateien = _mitglieder_dateien()
    if platz_id not in dateien:
        raise MitgliedNichtGefunden("Beiratsplatz '" + platz_id + "' nicht gefunden")
    if not UEBERNAHME_DIR.is_dir():
        raise MitgliedFehler(
            "Kein Übernahme-Verzeichnis " + _kurzpfad(UEBERNAHME_DIR)
            + " — der Lauf hat dort nichts abgelegt")

    kandidaten = sorted(p for p in UEBERNAHME_DIR.glob("beirat-*.md") if p.is_file())
    if not kandidaten:
        raise MitgliedFehler("Im Übernahme-Verzeichnis liegt keine `beirat-*.md`")

    # ALLES zuerst prüfen, dann schreiben (Muster `aktualisiere_mitglied`).
    geprueft = []
    erlaubte = set(dateien)
    for quelle in kandidaten:
        text = quelle.read_text(encoding="utf-8")
        ziel_id = _persona_pruefen(text, erlaubte)
        geprueft.append((quelle, ziel_id, text))
    if platz_id not in [z for _q, z, _t in geprueft]:
        raise MitgliedFehler(
            "Für den neu zu besetzenden Platz '" + platz_id + "' liegt keine Datei bereit "
            "(gefunden: " + ", ".join(sorted(z for _q, z, _t in geprueft)) + ")")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stempel = datetime.now().strftime("%Y_%m_%d_%H%M")
    uebernommen, gesichert = [], []
    for _quelle, ziel_id, text in geprueft:
        ziel = dateien[ziel_id]
        sicherung = BACKUP_DIR / (stempel + "_" + ziel_id + ".md")
        if not sicherung.exists():
            sicherung.write_text(ziel.read_text(encoding="utf-8"), encoding="utf-8")
            gesichert.append(sicherung.name)
        ziel.write_text(text, encoding="utf-8")
        uebernommen.append(ziel_id)

    return dict(platz_id=platz_id, uebernommen=uebernommen, gesichert=gesichert,
                hinweis="Backup unter " + _kurzpfad(BACKUP_DIR))


def aktualisiere_mitglied(platz_id: str, felder: dict) -> dict:
    """PATCH-Kern für EINEN Beiratsplatz (B2). Erlaubte Felder in `felder`: `anzeige`,
    `perspektive`, `farbe`, `vorsitz` — andere Schlüssel werden ignoriert (main.py filtert
    ohnehin vorher). Validiert ALLES zuerst, bevor irgendetwas geschrieben wird — ein
    ungültiges Feld darf kein anderes, gültiges Feld halb angewendet lassen (z. B. Farbe schon
    geschrieben, aber Vorsitz-Regel verletzt).

    Regeln:
    - Farbe muss `#RRGGBB` sein, sonst `MitgliedFehler` (→ 422).
    - `vorsitz: true` nimmt es ALLEN anderen Mitgliedern ab (genau einer, immer einer) — die
      übrigen Dateien werden dafür mit angefasst (einzige Stelle, an der B2 mehr als EINE Datei
      schreibt).
    - `vorsitz: false` auf den aktuell (und einzigen) Vorsitz → `MitgliedFehler`: ohne Vorsitz
      kann die Engine nicht dispatchen (s. `vorsitz_id()`-Docstring).
    - `anzeige` ändert NICHT das Frontmatter, sondern zieht die Body-Zeile „Du bist **<Name>**“
      mit (`_anzeige_umbenennen()`) — die einzige Body-Änderung, die dieser Pfad vornehmen darf.
    """
    dateien = _mitglieder_dateien()
    if platz_id not in dateien:
        raise MitgliedNichtGefunden(f"Beiratsplatz '{platz_id}' nicht gefunden")

    farbe = None
    if "farbe" in felder:
        farbe = (felder.get("farbe") or "").strip()
        if not _HEX_FARBE_RE.match(farbe):
            raise MitgliedFehler("Farbe muss ein Hex-Wert im Format #RRGGBB sein")

    perspektive = None
    if "perspektive" in felder:
        perspektive = (felder.get("perspektive") or "").strip()
        if not perspektive:
            raise MitgliedFehler("perspektive darf nicht leer sein")

    neue_anzeige = None
    if "anzeige" in felder:
        neue_anzeige = (felder.get("anzeige") or "").strip()
        if not neue_anzeige:
            raise MitgliedFehler("anzeige darf nicht leer sein")

    neuer_vorsitz_wert = None
    andere_zu_entfernen: list[str] = []
    if "vorsitz" in felder:
        neuer_vorsitz_wert = bool(felder["vorsitz"])
        aktuell = {m["id"]: m["vorsitz"] for m in lade_mitglieder()}
        bisherige_vorsitzende = [i for i, v in aktuell.items() if v]
        ist_bisheriger_vorsitz = aktuell.get(platz_id, False)
        if not neuer_vorsitz_wert and ist_bisheriger_vorsitz and len(bisherige_vorsitzende) <= 1:
            raise MitgliedFehler(
                "Der Beirat braucht eine Vorsitzende — markiere zuerst ein anderes Mitglied als "
                "Vorsitz. Ohne Vorsitz kann die Engine nicht dispatchen."
            )
        if neuer_vorsitz_wert:
            andere_zu_entfernen = [i for i in bisherige_vorsitzende if i != platz_id]

    # ── Ab hier nur noch Schreiben — alle Validierungen sind durch ──
    for anderer_id in andere_zu_entfernen:
        _frontmatter_feld_setzen(dateien[anderer_id], "vorsitz", "false")
    if farbe is not None:
        _frontmatter_feld_setzen(dateien[platz_id], "farbe", f'"{farbe}"')
    if perspektive is not None:
        _frontmatter_feld_setzen(dateien[platz_id], "description", perspektive)
    if neuer_vorsitz_wert is not None:
        _frontmatter_feld_setzen(dateien[platz_id], "vorsitz", "true" if neuer_vorsitz_wert else "false")
    if neue_anzeige is not None:
        _anzeige_umbenennen(dateien[platz_id], neue_anzeige)

    aktualisiert = {m["id"]: m for m in lade_mitglieder()}
    return aktualisiert[platz_id]


def _charta_kern() -> str:
    """Die Charta vollständig — sie ist kompakt genug für jeden System-Prompt."""
    return CHARTA_PFAD.read_text(encoding="utf-8") if CHARTA_PFAD.exists() else ""


# ── Kontext-Sammler für Stellen-Checks (Phase 40, Design-Entscheidung 3a) ───────────────
# DETERMINISTISCH — läuft im Endpoint, KEIN LLM-Turn. Fehlende Quellen werden ausdrücklich
# als fehlend markiert (Anti-Halluzination), nie stillschweigend weggelassen oder erraten —
# die Köpfe tragen das dann selbst als ❓ ins Risiko-Board.

_DE_WOERTER = {"und", "für", "mit", "ist", "sind", "eine", "einer", "unternehmen", "wir", "sie",
              "unser", "unsere", "ihre", "aufgaben", "erfahrung", "kenntnisse", "verantwortung",
              "als", "bei", "der", "die", "das", "sowie", "werden", "haben"}
_EN_WOERTER = {"and", "for", "with", "is", "are", "our", "you", "we", "the", "responsibilities",
              "experience", "requirements", "role", "team", "will", "have", "your", "about"}


def _erkenne_sprache(text: str) -> str:
    """Grobe DE/EN-Heuristik über Stopwort-Häufigkeit — reicht, um zwischen base_de.docx und
    base_en.docx zu wählen. Bei Gleichstand/leer: Default Deutsch (Kernmarkt DACH)."""
    woerter = re.findall(r"[a-zA-ZäöüÄÖÜß]+", (text or "").lower())
    de = sum(1 for w in woerter if w in _DE_WOERTER)
    en = sum(1 for w in woerter if w in _EN_WOERTER)
    return "en" if en > de else "de"


def _html_text(rel_path: str, limit: int) -> str:
    p = artefakt_pfad(rel_path)
    # Phase 79: gemeinsame Auflösung (data/ → aktive Datenwurzel) statt PROJECT_ROOT — s. app/db.py::artefakt_pfad
    if not p.is_file():
        return "(Datei nicht gefunden)"
    text = entkleiden(p.read_text(encoding="utf-8", errors="replace"))
    return text[:limit] + ("…" if len(text) > limit else "")


def _cv_text(sprache: str, limit: int) -> tuple[str, str]:
    rel = f"data/cv_basis/base_{'en' if sprache == 'en' else 'de'}.docx"
    # Phase 79: gemeinsame Auflösung — schließt auch den LESENDEN Zugriff auf die echten
    # Basis-CVs unter Test-Isolation (s. app/db.py::artefakt_pfad).
    p = artefakt_pfad(rel)
    if not p.is_file():
        return "", rel
    import docx
    d = docx.Document(str(p))
    text = "\n".join(par.text for par in d.paragraphs if par.text.strip())
    return text[:limit] + ("…" if len(text) > limit else ""), rel


def sammle_stellen_kontext(job, company) -> tuple[str, bool]:
    """Job-Eckdaten + Anzeigentext (posting_snapshot_path) + sprachpassender Basis-CV-Text +
    Company-Fit (fit_ampel + Text-Extrakt) + verify_note (inkl. KONFLIKT-Anhänge). KEIN Web —
    die Köpfe debattieren ausschließlich auf dieser Basis (Design-Entscheidung 3a).
    Rückgabe: (kontext_text, company_fit_fehlt) — Letzteres steuert das Warn-Event im Endpoint."""
    teile = [f"STELLE: {job.title or '(kein Titel)'} bei {job.company_name or '(unbekannte Firma)'} (Job {job.id})"]

    eckdaten = []
    if job.location:
        eckdaten.append(f"Ort: {job.location}")
    if job.work_model:
        eckdaten.append(f"Arbeitsmodell: {job.work_model}")
    if job.seniority:
        eckdaten.append(f"Seniorität: {job.seniority}")
    if job.salary:
        eckdaten.append(f"Gehalt: {job.salary}")
    if job.status:
        eckdaten.append(f"Status im System: {job.status}")
    if job.match_score:
        eckdaten.append(f"Bisheriger Zielstellen-Fit (Bewertungsraster): {job.match_score}/5"
                        + (f" — {job.match_rationale}" if job.match_rationale else ""))
    if eckdaten:
        teile.append("ECKDATEN: " + " · ".join(eckdaten))
    if job.verify_note:
        teile.append(f"VERIFIKATIONS-VERMERK (ggf. inkl. KONFLIKT-Anhängen): {job.verify_note}")

    if job.posting_snapshot_path:
        anzeige = _html_text(job.posting_snapshot_path, 5000)
        teile.append(f"ANZEIGENTEXT (Original-Snapshot):\n{anzeige}")
    else:
        anzeige = ""
        teile.append("ANZEIGENTEXT: NICHT VERFÜGBAR (kein Snapshot hinterlegt) — echte Lücke, nicht erraten.")

    sprache = _erkenne_sprache(anzeige or job.title or "")
    cv, cv_pfad = _cv_text(sprache, 6000)
    if cv:
        teile.append(f"CV-BASIS ({sprache.upper()}, {cv_pfad}):\n{cv}")
    else:
        teile.append(f"CV-BASIS: NICHT VERFÜGBAR ({cv_pfad} nicht gefunden) — echte Lücke.")

    company_fit_fehlt = True
    if company and company.fit_analysis_path:
        fit_text = _html_text(company.fit_analysis_path, 3500)
        teile.append(f"COMPANY-FIT (Ampel: {company.fit_ampel or 'nicht gesetzt'}):\n{fit_text}")
        company_fit_fehlt = False
    else:
        teile.append("COMPANY-FIT: NICHT VERFÜGBAR — noch keine Firmen-Prüfung gelaufen. Echte Lücke "
                     "(gehört ins Risiko-Board, nicht durch Vermutungen ersetzen).")

    return "\n\n".join(teile), company_fit_fehlt


# ── Key-Store (lokal, nie im Projekt/iCloud) ─────────────────────────────────────────

def keys_lesen() -> dict:
    try:
        return json.loads(KEY_PFAD.read_text())
    except Exception:
        return {}


def keys_schreiben(anthropic: str | None, openai: str | None) -> None:
    """None = unverändert lassen, "" = löschen, sonst setzen."""
    KEY_DIR.mkdir(mode=0o700, exist_ok=True)
    k = keys_lesen()
    for feld, wert in (("anthropic", anthropic), ("openai", openai)):
        if wert is None:
            continue
        if wert == "":
            k.pop(feld, None)
        else:
            k[feld] = wert.strip()
    KEY_PFAD.write_text(json.dumps(k))
    os.chmod(KEY_PFAD, 0o600)


def keys_status() -> dict:
    k = keys_lesen()
    def _mask(v):
        return f"…{v[-4:]}" if v else None
    return {
        "anthropic_gesetzt": bool(k.get("anthropic")), "anthropic_maske": _mask(k.get("anthropic")),
        "openai_gesetzt": bool(k.get("openai")), "openai_maske": _mask(k.get("openai")),
        # Phase 100: `which` zuerst, damit auch ein blosser Befehlsname (Env-Override
        # CLAUDE_BIN=claude) als verfügbar gilt; `.exists()` bleibt als Fallback für eine
        # vorhandene, aber nicht als ausführbar markierte Datei.
        "cli_verfuegbar": bool(shutil.which(CLAUDE_BIN)) or Path(CLAUDE_BIN).exists(),
    }


# ── Task-Center-Log (Phase 42): EIN Aktivitäts-Log fürs ganze System ─────────────────
# Jede Hintergrund-Aktivität schreibt AgentTask-Rows + ein task_<id>.jsonl in AGENT_LOG_DIR
# (seit Phase 63B: ~/.bewerbung_mgmt_logs/, s. Import oben) — egal ob Runner-Prozess
# (agent_runner.py) oder In-Server-Engine (hier). Der bestehende
# Log-Viewer im Task-Center (Tasks.tsx::pretty) kennt nur type=system/assistant/result
# (Claude-CLI-stream-json-Konvention) — Zeilen mit anderem `type` liefert er als `null` und
# blendet sie stillschweigend aus. Eigene Notiz-Zeilen werden daher bewusst als
# `type:"assistant"` verpackt, damit sie ohne jede Frontend-Änderung sichtbar sind.

def _log_zeile(task_id: int | None, zeile: str) -> None:
    """Rohe Zeile ans Task-Log anhängen. Append-per-Write (kein offener Handle über
    await-Punkte) — ein Debattenlauf hat nur ~15-30 Turns, kein Hot-Path (deshalb hier auch
    ok: `neue_log_datei()` setzt bei JEDEM Schreiben erneut chmod 600 statt nur beim ersten
    Mal — s. dort für die mit agent_runner.py geteilte Rechte-Logik, Phase 63B/P1-3). Darf
    den Lauf nie zum Scheitern bringen (Log ist Diagnose, nicht Fachlogik)."""
    if not task_id:
        return
    try:
        _, pfad = neue_log_datei(task_id)
        with open(pfad, "a", encoding="utf-8") as f:
            f.write(zeile if zeile.endswith("\n") else zeile + "\n")
    except Exception:
        pass


def _log_notiz(task_id: int | None, text: str) -> None:
    """Ein Beirats-eigenes Ereignis (Moderation/Votum/Entscheidung/…) als Log-Zeile — verpackt
    als `assistant`-Nachricht, s. o."""
    _log_zeile(task_id, json.dumps(
        {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}},
        ensure_ascii=False))


def _ev_log_text(typ: str, daten: dict) -> str | None:
    """Nur die erzählerisch wertvollen SSE-Events als Log-Notiz — beitrag_start/delta/
    beitrag_ende/synthese_start sind über den rohen Turn-Stream (_turn_anthropic) bereits
    vollständig im Log enthalten, eine Doppelung würde ihn nur aufblähen."""
    if typ == "status" or typ == "moderation":
        return daten.get("text") or None
    if typ == "votum":
        if daten.get("enthaltung"):
            return f"{daten.get('anzeige')}: Enthaltung"
        stimme = daten.get("stimme") or {}
        return f"{daten.get('anzeige')}: {stimme.get('votum')}"
    if typ == "entscheidung":
        e = daten.get("entscheidung") or {}
        return f"Entscheidung: {e.get('ampel')} ({e.get('gesamt')}/10)"
    if typ == "fehler":
        return f"Fehler: {daten.get('text', '')}"
    if typ == "fertig":
        return f"Fertig — {daten.get('beitraege', '?')} Beiträge."
    return None


# ── Modell-Turns (Anthropic via Agent-SDK-Headless / OpenAI via httpx) ───────────────

def _result_event_auswerten(obj: dict) -> tuple[str, float, str | None]:
    """Wertet EIN bereits geparstes `result`-Event aus dem stream-json des Agent-SDK-Headless-CLI
    aus (`claude -p --output-format stream-json`). Reine Funktion — kein I/O, kein Subprozess,
    direkt testbar (s. backend/tests/test_beirat_fehler.py).

    Phase 62B / P1-4: Vorher wurden nur `result` und `total_cost_usd` gelesen; `is_error` und
    `api_error_status` blieben ungeprüft. Dadurch wurde eine echte API-Fehlermeldung (z. B.
    Session-/Rate-Limit) als Wortlaut eines Beirats-Kopfs gespeichert (Beleg:
    data/beirat/2026_07_23_2126_0e843f.json — der gespeicherte Beitrag der damaligen
    Vorsitzenden ist reiner Fehlertext; die Datei liegt aus Historiengründen unverändert unter
    data/beirat/, der damals verwendete Persona-Name ist seit Phase 71C nicht mehr aktiv).
    WICHTIG: `subtype` bleibt bei einem API-Fehler oft weiterhin "success" (real beobachtet in
    data/agent_logs/task_342.jsonl: is_error=True, api_error_status=429, subtype="success") —
    nur `is_error` ist verlässlich, `subtype` darf dafür NICHT herangezogen werden.

    Rückgabe: (text, kosten_usd, fehlermeldung|None). Bei einem Fehler ist `text` bewusst leer
    (der Aufrufer darf ihn nicht als Beitragsinhalt verwenden) und `fehlermeldung` gesetzt."""
    kosten = obj.get("total_cost_usd") or 0.0
    if obj.get("is_error"):
        status = obj.get("api_error_status")
        praefix = f"API-Fehler {status}" if status else "API-Fehler"
        meldung = obj.get("result") or "(keine Fehlermeldung im result-Feld)"
        return "", kosten, f"{praefix}: {meldung}"
    return (obj.get("result") or ""), kosten, None


# ── Phase 77 — Headless-Auth vereinheitlicht (Echtfall 07.08.2026 09:16) ─────────────────────
# Ein Auth-Weg für alle headless-`claude`-Läufe: Beirats-Turns nutzen dieselbe Token-Quelle wie
# der Runner (agent_runner._child_env()), Keychain bleibt nur noch LETZTER Fallback — geschützt
# durch die Vorwärm-Schleuse weiter unten. Details: tasks/spec_phase77_beirat_auth.md.

def _headless_token() -> str | None:
    """Liest `CLAUDE_CODE_OAUTH_TOKEN` aus `agent.env` — dieselbe Quelle wie
    `agent_runner._child_env()` ("die eine universelle Ausnahme", s. dort). `agent_runner.ENV_FILE`
    wird bewusst zur LAUFZEIT übers Modul referenziert (`agent_runner.ENV_FILE`, NICHT
    `from app.agent_runner import ENV_FILE`), damit Tests per `monkeypatch.setattr(agent_runner,
    "ENV_FILE", tmp_pfad)` einen isolierten Pfad setzen können, ohne dieses Modul neu zu
    importieren. Parsing-Muster (Kommentar-/Leerzeilen überspringen, Anführungszeichen strippen)
    1:1 aus `agent_runner._child_env()`/`check_env_file()` übernommen, NICHT dupliziert erfunden.
    Rückgabe: der Token-WERT (nie geloggt — Aufrufer setzen ihn nur als Env-Wert) oder None,
    wenn die Datei fehlt oder keine Zeile passt."""
    env_file = agent_runner.ENV_FILE
    if not env_file.exists():
        return None
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == "CLAUDE_CODE_OAUTH_TOKEN":
            wert = v.strip().strip('"').strip("'")
            return wert or None
    return None


def _bestimme_auth_weg() -> str:
    """Reine Ermittlung des Auth-Wegs (Entscheidung 1: a) keys.json-Key > b) agent.env-Token >
    c) Keychain), OHNE Env aufzubauen oder zu loggen — von `_turn_env()` (baut daraus das
    Subprozess-Env) UND `Debatte.laufen()` (Vorwärm-Gate: NUR im Keychain-Fall c) genutzt, damit
    beide Stellen niemals auseinanderlaufen können."""
    if keys_lesen().get("anthropic"):
        return "keys.json"
    if _headless_token():
        return "agent.env-Token"
    return "keychain"


_AUTH_WEG_LOG_TEXT = {
    "keys.json": "Auth: keys.json",
    "agent.env-Token": "Auth: agent.env-Token",
    "keychain": "Auth: Keychain-Fallback (vorgewärmt)",
}


def _turn_env(task_id: int | None) -> tuple[dict, str]:
    """Env für EINEN Anthropic-CLI-Turn. Das `CLAUDE*`-Stripping (Identitäts-Trennung, s.
    Moduldocstring) BLEIBT unverändert; danach greift Entscheidung 1: a) ein eingegebener
    `keys.json`-Key schlägt weiterhin alles (unverändertes Verhalten), b) NEU — ohne Key wird
    das Runner-Token gezielt NACH dem Stripping wieder gesetzt (exakt die eine bewusste Ausnahme
    aus `agent_runner._child_env()`, sonst wirft das Stripping das stabile Runner-Token
    versehentlich mit weg), c) ohne Key UND ohne Token bleibt `env` unverändert → Fallback auf
    die Keychain-Abo-Session (nur noch hinter der Vorwärm-Schleuse, s. `_keychain_vorwaermen()`).
    Token-/Key-WERTE werden NIE geloggt — nur der gewählte Weg (Schlüssel-Name, kein Wert)
    landet als Klartext-Zeile im Task-Log (Echt-Nachweis für die Abnahme)."""
    env = {n: v for n, v in os.environ.items() if not n.startswith("CLAUDE")}
    auth_weg = _bestimme_auth_weg()
    if auth_weg == "keys.json":
        env["ANTHROPIC_API_KEY"] = keys_lesen()["anthropic"]     # eingegebener Key schlägt Abo-Auth
    elif auth_weg == "agent.env-Token":
        env["CLAUDE_CODE_OAUTH_TOKEN"] = _headless_token()
    _log_notiz(task_id, _AUTH_WEG_LOG_TEXT[auth_weg])
    return env, auth_weg


_AUTH_FEHLER_MUSTER = ("failed to authenticate", "oauth session expired")


def _auth_fehler_uebersetzen(rohtext: str, auth_weg: str) -> str | None:
    """Entscheidung 3: erkennt einen rohen Auth-Fehlertext ("Failed to authenticate"/"OAuth
    session expired", von der CLI bzw. via `_result_event_auswerten` durchgereicht) und
    übersetzt ihn je nach genutztem Auth-Weg in eine für den Nutzer verständliche Klartext-Meldung.
    Der rohe Text bleibt UNVERÄNDERT im Task-Log erhalten (landet dort bereits über
    `_log_zeile`) — nur die Task-/Debatten-Meldung (`AgentTask.error`/`Debatte.fehler`) wird
    übersetzt. Kein Auth-Fehler erkannt (z. B. Rate-Limit, Timeout) → None, der Aufrufer behält
    dann den rohen Text (unverändertes Verhalten wie vor Phase 77). Reine Funktion, direkt
    testbar — kein I/O."""
    tief = (rohtext or "").lower()
    if not any(m in tief for m in _AUTH_FEHLER_MUSTER):
        return None
    if auth_weg == "keychain":
        return ("Claude-Abo-Login abgelaufen — im Terminal `claude` öffnen und per /login neu "
                "anmelden, dann den Check erneut starten.")
    return (f"CLAUDE_CODE_OAUTH_TOKEN in {agent_runner.ENV_FILE} ist ungültig/abgelaufen — "
            "mit `claude setup-token` erneuern.")


_VORWAERM_LOCK = asyncio.Lock()
_vorwaerm_ok_bis = 0.0   # time.monotonic()-Zeitstempel; 0.0 = noch nie erfolgreich vorgewärmt


async def _keine_delta(_: str) -> None:
    """No-Op-Callback für Turns ohne Live-Streaming (hier: die Vorwärmung — nur das Ergebnis
    zählt, kein Beitragstext)."""
    return


async def _keychain_vorwaermen(task_id: int | None = None) -> tuple[str | None, float]:
    """Vorwärm-Schleuse (Entscheidung 2 — Echtfall 07.08.2026 09:16): GENAU EIN
    serieller Mini-Turn (Haiku, `--max-turns 1`/`--tools ""` kommen bereits aus
    `_turn_anthropic()`, 30-Sekunden-Timeout, Prompt "Antworte nur: OK") gegen die Keychain-Abo-
    Session, BEVOR eine Debatte im Keychain-Fallback (Auth-Weg c) in den Persona-Fan-out geht.
    Läuft über `_turn_anthropic()` selbst (nicht dupliziert) — dieselbe `_turn_env()`-Logik
    wärmt dadurch garantiert exakt die Identität vor, die der folgende echte Turn auch benutzt.

    Ein modulweiter `asyncio.Lock` + 5-Minuten-Erfolgscache (an `time.monotonic()`, NICHT
    `datetime.now()` — kein Sommerzeit-/Uhrumstellungs-Sprung) sorgt dafür, dass zwei
    gleichzeitig startende Debatten NACHEINANDER (bzw. nur einmal, wenn der Cache noch gültig
    ist) vorwärmen: der Access-Token-Refresh der Keychain-Session passiert dadurch konkurrenzlos,
    statt dass — wie am 07.08. um 09:16 beim Echtfall oben — mehrere parallele `claude`-
    Prozesse gleichzeitig auf ein abgelaufenes Access-Token treffen, parallel refreshen und die
    Rotation des Refresh-Tokens die Abo-Session dauerhaft invalidiert ("could not be refreshed").

    Fehlschläge werden NICHT gecacht (Entscheidung 2) — die nächste Debatte versucht es erneut.
    Rückgabe: (Klartext-Fehler|None, Kosten-USD des Mini-Turns) — der Aufrufer (`Debatte.laufen()`)
    verbucht die Kosten auch bei einem Fehlschlag über `_erfassen()`."""
    global _vorwaerm_ok_bis
    async with _VORWAERM_LOCK:
        if time.monotonic() < _vorwaerm_ok_bis:
            return None, 0.0          # Cache noch gültig — die zweite Debatte spart sich den Turn
        try:
            _, kosten = await _turn_anthropic("", "Antworte nur: OK", "haiku", _keine_delta,
                                              task_id=task_id, timeout=30)
        except Exception as ex:
            kosten = getattr(ex, "kosten_usd", 0.0) or 0.0
            fehler = _auth_fehler_uebersetzen(str(ex), "keychain") or (
                f"Vorwärmung der Claude-Abo-Session fehlgeschlagen ({str(ex)[:200]}) — im "
                "Terminal `claude` öffnen und per /login neu anmelden, dann erneut versuchen.")
            return fehler, kosten
        _vorwaerm_ok_bis = time.monotonic() + 300     # 5 Minuten, s. Entscheidung 2
        return None, kosten


async def _turn_anthropic(system_prompt: str, user_prompt: str, model: str, on_delta,
                          task_id: int | None = None,
                          timeout: int = MAX_TURN_SEKUNDEN) -> tuple[str, float]:
    """Ein Redebeitrag über `claude -p` (Agent-SDK headless), Token-Deltas live an on_delta.
    Rückgabe (Text, Kosten-USD des Turns aus dem result-Event). Bei gesetztem task_id landet
    jede rohe stdout-Zeile zusätzlich im Task-Center-Log (Phase 42, gleiches Format wie
    agent_runner._drain — der Log-Viewer versteht es unverändert).

    Phase 62B (P1-4): Ein `result`-Event mit `is_error` löst eine RuntimeError aus, STATT den
    (dann untrauenswürdigen) Text als Beitragsinhalt zurückzugeben — s. _result_event_auswerten.
    Die Exception trägt die bereits ausgelesenen Kosten als `.kosten_usd`-Attribut, damit ein
    Retry-Aufrufer in laufen() sie trotz des Fehlschlags erfassen kann (self._erfassen).

    Phase 67E (P2-17): stdout/stderr laufen in EINEM gemeinsamen Stream (`stderr=STDOUT`,
    Muster aus `agent_runner._run_task()`) statt in zwei getrennten Pipes — vorher wurde nur
    stdout aktiv geleert; füllte das Kind den stderr-Puffer (typ. 16–64 KB), blockierte sein
    write() dauerhaft (begrenzt nur durch den 300-s-Timeout, danach TimeoutError statt eines
    hilfreichen Fehlers). Die „leerer Turn“-Diagnose kann sich deshalb nicht mehr separat aus
    `proc.stderr` bedienen (das gibt es bei zusammengelegten Streams nicht mehr, `proc.stderr`
    ist dann `None`) — sie sammelt stattdessen während `_lesen()` laufend die Rohzeilen mit und
    nutzt deren Ende als Ersatz, sobald sich `voll` als leer erweist."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    sysfile = WORK_DIR / f"sys_{uuid.uuid4().hex[:8]}.md"
    sysfile.write_text(system_prompt, encoding="utf-8")
    # CLAUDE*-Variablen NICHT erben: der Server läuft selbst als Kindprozess einer laufenden
    # Claude-Code-Session (CLAUDE_CODE_SESSION_ID etc.) — Absicherung gegen Identitäts-Verwechslung
    # bei verschachtelten CLI-Aufrufen. Sauberer env wie bei einem eigenständigen Terminal-Aufruf.
    # Phase 77: `_turn_env()` bündelt das Stripping + die Auth-Priorität aus Entscheidung 1
    # (keys.json-Key > agent.env-Token > Keychain) und loggt (ohne Wert) den gewählten Weg.
    env, auth_weg = _turn_env(task_id)
    cmd = [CLAUDE_BIN, "-p", user_prompt, "--system-prompt-file", str(sysfile),
           "--model", model, "--output-format", "stream-json", "--include-partial-messages",
           "--verbose", "--max-turns", "1",
           # "--tools", "" statt Deny-Liste: root-caused 18.07.2026 — bei --max-turns 1 verbraucht
           # JEDER Tool-Aufruf (z.B. ToolSearch, das die Köpfe-Namen fälschlich für echte Subagenten
           # hält) den einzigen erlaubten Turn, der Lauf endet mit error_max_turns und LEERER
           # Ausgabe ("Leerer Anthropic-Turn"). Eine Deny-Liste (vorher: Bash/Read/Write/Edit/
           # WebSearch/WebFetch/Task/Agent) erwischt nur bekannte Tools — ToolSearch und 20+ weitere
           # Bordmittel-Tools (Skill, Glob, Grep, TaskCreate, Workflow, …) waren nicht erfasst.
           # --tools "" ist eine Allow-Liste von NICHTS: robust gegen jedes künftig neu hinzukommende
           # Tool, passt auch inhaltlich (Design-Entscheidung 3a: diese Turns sind reine Text-/JSON-
           # Vervollständigung ohne jeden Werkzeugzugriff).
           "--tools", ""]
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(WORK_DIR), env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    text, result_text, kosten, api_fehler = [], None, 0.0, None
    # P2-17: Rohzeilen (stdout+stderr gemeinsam) laufend mitschneiden — einzige verbliebene
    # Quelle für die "leerer Turn"-Diagnose unten, seit `proc.stderr` durch den Stream-Merge
    # (s. Docstring) nicht mehr separat existiert.
    roh_ausgabe: list[str] = []
    try:
        async def _lesen():
            nonlocal result_text, kosten, api_fehler
            assert proc.stdout is not None
            while True:
                zeile = await proc.stdout.readline()
                if not zeile:
                    break
                dekodiert = zeile.decode("utf-8", "ignore")
                _log_zeile(task_id, dekodiert)
                roh_ausgabe.append(dekodiert)
                try:
                    obj = json.loads(zeile)
                except Exception:
                    continue
                if obj.get("type") == "stream_event":
                    ev = obj.get("event") or {}
                    if ev.get("type") == "content_block_delta":
                        d = ev.get("delta") or {}
                        if d.get("type") == "text_delta" and d.get("text"):
                            text.append(d["text"])
                            await on_delta(d["text"])
                elif obj.get("type") == "result":
                    result_text, kosten, api_fehler = _result_event_auswerten(obj)
        await asyncio.wait_for(_lesen(), timeout=timeout)
    finally:
        if proc.returncode is None:
            proc.kill()
        try:
            sysfile.unlink()
        except Exception:
            pass
    if api_fehler:
        # Phase 77 / Entscheidung 3: ein roher Auth-Fehler ("Failed to authenticate"/"OAuth
        # session expired") wird je nach genutztem Auth-Weg in Klartext übersetzt — der rohe
        # Text bleibt unverändert im Task-Log (s. _log_zeile oben), nur die Exception-Message
        # (landet in Debatte.fehler/AgentTask.error) wird verständlich. Kein Auth-Fehler
        # erkannt → unverändertes Verhalten wie vor Phase 77 (roher api_fehler-Text).
        ex = RuntimeError(_auth_fehler_uebersetzen(api_fehler, auth_weg) or api_fehler)
        ex.kosten_usd = kosten     # s. Docstring: Retry-Aufrufer erfasst Kosten trotz Fehlschlag
        raise ex
    voll = "".join(text).strip() or (result_text or "").strip()
    if not voll:
        diagnose = "".join(roh_ausgabe)[-500:]
        ex = RuntimeError(f"Leerer Anthropic-Turn (exit {proc.returncode}): {diagnose}")
        ex.kosten_usd = kosten
        raise ex
    return voll, kosten


async def _turn_openai(system_prompt: str, user_prompt: str, model: str, on_delta,
                       task_id: int | None = None) -> tuple[str, float]:
    """Ein Redebeitrag über die OpenAI-API (Streaming). Braucht hinterlegten Key.
    Kosten werden NICHT berechnet (Phase 42, Design-Entscheidung 2 „best effort"): OpenAI liefert
    im Stream keine Dollar-Summe, nur Token-Counts — ein Preis-pro-Modell fest zu verdrahten wäre
    fragil und driftet (OpenAI ist ohnehin der Nebenpfad, Standard ist das Abo über Anthropic).
    Rückgabe (Text, 0.0)."""
    key = keys_lesen().get("openai")
    if not key:
        raise RuntimeError("Kein OpenAI-Key hinterlegt (Beirat → Schlüssel).")
    text = []
    async with httpx.AsyncClient(timeout=MAX_TURN_SEKUNDEN) as client:
        async with client.stream(
            "POST", "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "stream": True,
                  "messages": [{"role": "system", "content": system_prompt},
                               {"role": "user", "content": user_prompt}]},
        ) as r:
            if r.status_code != 200:
                body = (await r.aread())[:300].decode("utf-8", "ignore")
                raise RuntimeError(f"OpenAI {r.status_code}: {body}")
            async for zeile in r.aiter_lines():
                if not zeile.startswith("data: "):
                    continue
                data = zeile[6:]
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"].get("content")
                except Exception:
                    delta = None
                if delta:
                    text.append(delta)
                    await on_delta(delta)
    voll = "".join(text).strip()
    if not voll:
        raise RuntimeError("Leerer OpenAI-Turn")
    _log_notiz(task_id, voll[:2000])   # kein rohes SSE-Format wie bei Anthropic, aber sichtbar
    return voll, 0.0


async def _turn(provider: str, openai_model: str, system_prompt: str, user_prompt: str,
                persona_model: str, on_delta, task_id: int | None = None) -> tuple[str, float]:
    if provider == "openai":
        return await _turn_openai(system_prompt, user_prompt, openai_model, on_delta, task_id)
    return await _turn_anthropic(system_prompt, user_prompt, persona_model, on_delta, task_id)


# ── Debatte: Zustand + Registry ───────────────────────────────────────────────────────

DEBATTEN: dict[str, "Debatte"] = {}


class _HartAbbruch(Exception):
    """Sentinel für den Task-Center-Cancel (Phase 42 Stufe B) — anders als der sanfte
    /debatten/{id}/stop (Design bereits in Phase 39: läuft noch in die Synthese), bricht dies
    OHNE Abstimmung/Synthese ab. Eigene Exception statt eines Flags, damit laufen() an jedem
    Checkpoint einfach `self._abbruch_pruefen()` aufrufen kann, ohne den Rückweg selbst zu
    bauen — das except-Handling übernimmt das Aufräumen zentral."""


class Debatte:
    def __init__(self, thema: str, kontext: str, min_beitraege: int,
                 teilnehmer_ids: list[str] | None, provider: str, openai_model: str,
                 modus: str = "frei", job_id: int | None = None,
                 job_titel: str = "", job_firma: str = "", company_fit_fehlt: bool = False):
        self.id = f"{datetime.now().strftime('%Y_%m_%d_%H%M')}_{uuid.uuid4().hex[:6]}"
        self.thema, self.kontext = thema.strip(), (kontext or "").strip()
        self.min_beitraege = max(2, int(min_beitraege))
        self.max_beitraege = int(self.min_beitraege * 1.5) + 2
        self.provider, self.openai_model = provider, openai_model
        self.modus = modus                   # "frei" | "stellen_check" (Phase 40)
        self.job_id = job_id
        self.job_titel, self.job_firma = job_titel, job_firma
        self.company_fit_fehlt = company_fit_fehlt
        self.status = "läuft"
        self.gestartet = datetime.now().isoformat(timespec="seconds")
        alle = lade_mitglieder()
        # Phase 50 (P2-51: Klarstellung) — Einstellungen-Seite kann für ALLE Personas einheitlich
        # ein Modell erzwingen: modell_fuer_beirat() liest den DB-Wert (Rückfall
        # agent_runner.MODELL_STANDARD) und wird hier bedingungslos über jedes Frontmatter-
        # `model` gelegt. Die Web-Engine nutzt den Frontmatter-Rückfall damit NIE — anders als der
        # interaktive Weg (/beirat-basis in einer normalen Claude-Code-Session), der die
        # Persona-Datei direkt liest und deren `model`-Feld selbst auswertet.
        db_modell = modell_fuer_beirat()
        for m in alle:
            m["model"] = db_modell
        self.mitglieder = {m["id"]: m for m in alle}
        # Phase 90 (A2): EINMAL je Debatte aufgelöst (nicht je Zugriff) — vorsitz_id() ist eine
        # reine Funktion über self.mitglieder, ein zweiter Aufruf mitten in laufen() könnte bei
        # einer parallel laufenden B2-Änderung der Frontmatter-Dateien ein ANDERES Ergebnis als
        # beim Start liefern; die Debatte soll aber mit EINEM konsistenten Vorsitz durchlaufen.
        self.vorsitz_id = vorsitz_id(self.mitglieder)
        self.teilnehmer = [m for m in alle if not teilnehmer_ids or m["id"] in teilnehmer_ids]
        self.beitraege: list[dict] = []      # {kopf, anzeige, farbe, frage, text, ts}
        self.moderationen: list[dict] = []   # {text, ts}
        self.synthese: str | None = None     # Freitext-Synthese (Modus "frei")
        self.abstimmung: dict | None = None  # {kopf_id: {scores,votum,begruendung}|None} (stellen_check)
        self.entscheidung: dict | None = None  # {ampel,gesamt,bereichs_avg,stimmen,enthaltungen} (stellen_check)
        self.check_synthese: dict | None = None  # strukturierte Synthese-JSON (stellen_check)
        # Phase 89: Die Synthese ist der LETZTE von vier Schritten. Scheitert sie, sind Debatte,
        # Abstimmung und Ampel längst berechnet und gespeichert — ein Abbruch würde eine
        # vollständige, bezahlte Runde verwerfen (Echtfall 23.08.2026). Stattdessen
        # wird der Grund hier vermerkt und im Dashboard offen ausgewiesen.
        self.synthese_fehler: str | None = None
        self.dashboard_pfad: str | None = None
        self.fehler: str | None = None
        self.stop_gewuenscht = False
        self.hart_abgebrochen = False  # Phase 42 Stufe B: Task-Center-Cancel (s. _HartAbbruch)
        self.queue: asyncio.Queue = asyncio.Queue()
        self.task: asyncio.Task | None = None
        # Phase 42: Task-Center ist DAS eine Aktivitäts-Log — die Engine pflegt ihre eigene
        # AgentTask-Row selbst (task_id wird von debatte_starten() nach dem Anlegen gesetzt).
        self.task_id: int | None = None
        self.num_turns = 0
        self.kosten_usd = 0.0

    # — Events —
    async def _ev(self, typ: str, **daten):
        ev = {"typ": typ, "ts": time.time(), **daten}
        await self.queue.put(ev)
        text = _ev_log_text(typ, daten)
        if text:
            _log_notiz(self.task_id, text)

    def _erfassen(self, kosten: float) -> None:
        """Kosten/Turns EINES Modell-Turns verbuchen. Prüft NICHT selbst die Notbremse — das
        passiert an den Checkpoints in laufen() (s. _notbremse_pruefen), sonst würde ein
        Budget-Überschreiten mitten in der parallelen Abstimmung von deren eigenem
        try/except verschluckt und nur als einzelne Enthaltung sichtbar, statt den ganzen
        Lauf sauber abzubrechen."""
        self.num_turns += 1
        self.kosten_usd += kosten or 0.0

    def _notbremse_pruefen(self) -> None:
        if self.kosten_usd >= NOTBREMSE_USD:
            raise RuntimeError(
                f"Notbremse: Kosten-Limit ${NOTBREMSE_USD:.2f} je Lauf erreicht "
                f"(${self.kosten_usd:.2f} nach {self.num_turns} Turns) — Lauf abgebrochen. "
                "Artefakte können unvollständig sein.")

    def _abbruch_pruefen(self) -> None:
        if self.hart_abgebrochen:
            raise _HartAbbruch()

    # — Prompts —
    def _transkript(self) -> str:
        teile = []
        for b in self.beitraege:
            teile.append(f"### {b['anzeige']} (auf die Frage: {b['frage']})\n{b['text']}")
        return "\n\n".join(teile) if teile else "(noch keine Beiträge)"

    def _vorsitz_system(self) -> str:
        vorsitz_name = self.mitglieder[self.vorsitz_id]["anzeige"]
        return (
            f"Du bist {vorsitz_name}, die VORSITZENDE des Bewerbungs-Beirats. Im Vorsitz beziehst du "
            "KEINE inhaltliche Position — du steuerst Prozess, Reihenfolge, Konvergenz und Synthese. "
            "Es gelten die Regeln der folgenden Charta.\n\n" + _charta_kern()
        )

    def _dispatch_prompt(self) -> str:
        koepfe = "\n".join(f"- {m['id']}: {m['anzeige']} — {m['beschreibung']}" for m in self.teilnehmer)
        n = len(self.beitraege)
        abschluss_regel = (
            f"Das Mindestmaß von {self.min_beitraege} Beiträgen ist ERREICHT — du DARFST abschließen, "
            f"wenn die Debatte konvergiert (harte Obergrenze: {self.max_beitraege})."
            if n >= self.min_beitraege else
            f"Erst {n} von mindestens {self.min_beitraege} Beiträgen — Abschluss ist NOCH NICHT erlaubt."
        )
        stellen_check_hinweis = (
            "\nSTELLEN-CHECK — Köpfe-Auswahl (Charta/Schritt 3): Richtwert 3–5 Köpfe INSGESAMT über "
            "die ganze Debatte (mehr nur, wenn wirklich jede Brille etwas Eigenes beiträgt) — wähle "
            "die relevanten Brillen für DIESE Stelle, nicht reihum alle sieben. Wähle AUSSCHLIESSLICH "
            "aus der Liste oben; sie ist die aktuelle Besetzung. Achte auf Spannung: mindestens eine "
            "Brille, die der erwartbaren Mehrheitsmeinung widersprechen könnte. Und lass KEINEN Kopf "
            "mehr als zwei Beiträge halten, solange eine andere passende Brille noch nicht dran war — "
            "sonst kippt die Runde zum Monolog. NACH der Debatte stimmen ohnehin ALLE sieben Köpfe "
            "unabhängig ab (Charta-Scoring) — hier geht es nur um die Debatten-Teilnahme.\n"
            if self.modus == "stellen_check" else ""
        )
        return (
            f"DEBATTEN-STEUERUNG.\n\nThema der Debatte:\n{self.thema}\n\n"
            f"Kontext des Nutzers:\n{self.kontext or '(keiner)'}\n\n"
            f"Köpfe am Tisch:\n{koepfe}\n{stellen_check_hinweis}\n"
            f"Bisheriger Verlauf ({n} Beiträge):\n{self._transkript()}\n\n"
            f"{abschluss_regel}\n\n"
            "Entscheide als Vorsitzende den NÄCHSTEN Schritt. Dispatch gezielt und namentlich "
            "(Charta): Wähle den Kopf, dessen Brille jetzt am meisten fehlt oder die größte Spannung "
            "zum letzten Beitrag verspricht — nicht einfach reihum. Formuliere ihm EINE gezielte "
            "Frage, die konkret auf den bisherigen Verlauf Bezug nimmt.\n\n"
            "Antworte NUR mit einem JSON-Objekt, ohne Markdown:\n"
            '{"aktion": "dispatch", "kopf": "<id aus der Liste>", "frage": "<gezielte Frage>", '
            '"begruendung": "<1 Satz, warum dieser Kopf jetzt>"}\n'
            'oder — nur wenn erlaubt — {"aktion": "abschluss", "begruendung": "<1 Satz>"}'
        )

    def _persona_system(self, m: dict) -> str:
        return (
            f"{m['persona']}\n\n---\n\nDu sitzt in einer MODERIERTEN DEBATTE des Bewerbungs-Beirats. "
            "Es gelten Antwortformat (Position → Brille → Empfehlung, max. ~120 Wörter) und "
            "MiroFish-Regeln der folgenden Charta. Sprich als dein Kopf, in der Ich-Form, auf Deutsch.\n\n"
            + _charta_kern()
        )

    def _persona_prompt(self, m: dict, frage: str) -> str:
        mirofish = (
            "Reagiere NAMENTLICH auf mindestens einen konkreten Vorbeitrag (zustimmen / widersprechen / "
            "ergänzen / hinterfragen / umdeuten) — kein Monolog, keine Wiederholung."
            if self.beitraege else
            "Du eröffnest die Debatte — beziehe klar Position zur Frage."
        )
        vorsitz_name = self.mitglieder[self.vorsitz_id]["anzeige"]
        return (
            f"Thema der Debatte:\n{self.thema}\n\nKontext des Nutzers:\n{self.kontext or '(keiner)'}\n\n"
            f"Bisherige Beiträge:\n{self._transkript()}\n\n"
            f"Die Vorsitzende {vorsitz_name} ruft dich auf: „{frage}“\n\n{mirofish}"
        )

    def _synthese_prompt(self) -> str:
        return (
            f"Die Debatte ist beendet ({len(self.beitraege)} Beiträge). Erstelle als Vorsitzende die "
            "SYNTHESE nach dem Charta-Format (Titel · Fazit · Begründung · Kern je Kopf · Empfehlung · "
            "Offene Punkte; Risiken gern als Board). Markdown erlaubt. Bevorzuge keinen Kopf heimlich.\n\n"
            f"Thema:\n{self.thema}\n\nKontext:\n{self.kontext or '(keiner)'}\n\n"
            f"Vollständiger Verlauf:\n{self._transkript()}"
        )

    # — Stellen-Check: Abstimmung ALLER 7 Köpfe (Charta „Stellen-Check: Scoring &
    #   Abstimmungsverfahren") — unabhängig, auch die, die nicht in der Debatte saßen ─────

    def _abstimmung_system(self, m: dict) -> str:
        return (
            f"{m['persona']}\n\n---\n\nDu gibst deine unabhängige SCHLUSSABSTIMMUNG zu einem "
            "Stellen-Check des Bewerbungs-Beirats ab (Charta-Abschnitt „Stellen-Check: Scoring & "
            "Abstimmungsverfahren“). Antworte NUR mit deinem Kopf, in der Ich-Form.\n\n" + _charta_kern()
        )

    def _abstimmung_prompt(self, m: dict) -> str:
        bereiche_text = "\n".join(f'- "{b}" ({int(GEWICHTE[b]*100)}%): {BEREICHS_LABEL[b]}'
                                  for b in ABSTIMMUNGS_BEREICHE)
        return (
            f"STELLE: {self.thema}\n\nKontext (Anzeigentext, CV-Basis, Company-Fit, Eckdaten):\n"
            f"{self.kontext or '(keiner)'}\n\n"
            f"Debatten-Digest — Kernaussagen der Debatte (falls du selbst nicht dabei warst, ist das "
            f"deine einzige Sicht auf die Diskussion der anderen Köpfe):\n{self._transkript()}\n\n"
            "Vergib jetzt unabhängig Bewertungen von 0 bis 10 je Prüfbereich:\n" + bereiche_text + "\n\n"
            "Plus ein Votum: \"Bewerben\" · \"Bedingt\" · \"Nicht\" (bewerben) — und 2–3 Sätze "
            "Begründung aus deiner eigenen Brille. Unsicherheit gehört in die Begründung, nicht "
            "heimlich in den Score versteckt. Erfinde keine Fakten, die nicht im Kontext stehen.\n\n"
            "Antworte AUSSCHLIESSLICH mit einem JSON-Objekt, kein Markdown, kein Fließtext davor/danach:\n"
            '{"scores": {"rollenfit": 0-10, "cv_ergebnisse": 0-10, "unternehmen": 0-10, '
            '"uebertragbarkeit": 0-10, "karrierewirkung": 0-10, "interview_chance": 0-10}, '
            '"votum": "Bewerben|Bedingt|Nicht", "begruendung": "<2-3 Sätze aus deiner Brille>"}'
        )

    @staticmethod
    def _stimme_gueltig(parsed: dict | None) -> bool:
        if not isinstance(parsed, dict):
            return False
        scores = parsed.get("scores")
        if not isinstance(scores, dict):
            return False
        for b in ABSTIMMUNGS_BEREICHE:
            v = scores.get(b)
            if not isinstance(v, (int, float)) or not (0 <= v <= 10):
                return False
        return parsed.get("votum") in STIMMEN_WERTE

    async def _abstimmung_durchfuehren(self) -> dict:
        """ALLE 7 Köpfe (nicht nur Debatten-Teilnehmer) stimmen unabhängig, parallel ab —
        Semaphore 3 gleichzeitige Turns. Kaputtes JSON → 1 Retry → dann „Enthaltung" (nie raten,
        im Dashboard sichtbar ausgewiesen)."""
        sem = asyncio.Semaphore(3)
        alle = list(self.mitglieder.values())

        async def _eine_stimme(m: dict):
            async with sem:
                for _ in range(2):          # 1 Versuch + 1 Retry
                    try:
                        roh, kosten = await _turn(self.provider, self.openai_model, self._abstimmung_system(m),
                                          self._abstimmung_prompt(m), m["model"], self._nix,
                                          task_id=self.task_id)
                        self._erfassen(kosten)     # kein Notbremse-Raise hier — s. _erfassen-Docstring
                        parsed = self._json_extrahieren(roh)
                        if self._stimme_gueltig(parsed):
                            await self._ev("votum", kopf=m["id"], anzeige=m["anzeige"], farbe=m["farbe"],
                                          stimme=parsed, enthaltung=False)
                            return m["id"], parsed
                    except Exception:
                        pass
                await self._ev("votum", kopf=m["id"], anzeige=m["anzeige"], farbe=m["farbe"],
                              stimme=None, enthaltung=True)
                return m["id"], None

        ergebnisse = await asyncio.gather(*(_eine_stimme(m) for m in alle))
        return dict(ergebnisse)

    @staticmethod
    def _entscheidung_berechnen(abstimmung: dict) -> dict:
        """DETERMINISTISCH im Code (Charta-Entscheidungsregel, kein Modell rechnet mit).
        Reihenfolge der Prüfung ist Absicht: Score>=7.0 UND Quorum zuerst (klarer Fall
        „Bewerben"), dann Score<6.0 (klarer Fall „Nicht bewerben"), alles dazwischen —
        inkl. des Randfalls Score>=7.0 OHNE das 5/7-Quorum — fällt auf „Bedingt": die Charta
        nennt „Bedingt" explizit für „wesentliche Informationen fehlen" bzw. Uneinigkeit, und
        ein hoher Score ohne Stimmenmehrheit ist genau das — Uneinigkeit unter den Köpfen."""
        gueltige = {k: v for k, v in abstimmung.items() if v is not None}
        enthaltungen = [k for k, v in abstimmung.items() if v is None]
        bereichs_avg = {}
        for bereich in ABSTIMMUNGS_BEREICHE:
            werte = [v["scores"][bereich] for v in gueltige.values()]
            bereichs_avg[bereich] = (sum(werte) / len(werte)) if werte else 0.0
        gesamt = sum(bereichs_avg[b] * GEWICHTE[b] for b in ABSTIMMUNGS_BEREICHE)
        stimmen = {w: sum(1 for v in gueltige.values() if v["votum"] == w) for w in STIMMEN_WERTE}

        if gesamt >= 7.0 and stimmen["Bewerben"] >= 5:
            ampel = "Bewerben"
        elif gesamt < 6.0:
            ampel = "Nicht"
        else:
            ampel = "Bedingt"

        return {"ampel": ampel, "gesamt": round(gesamt, 2),
                "bereichs_avg": {b: round(v, 2) for b, v in bereichs_avg.items()},
                "stimmen": stimmen, "enthaltungen": enthaltungen}

    def _check_synthese_system(self) -> str:
        vorsitz_name = self.mitglieder[self.vorsitz_id]["anzeige"]
        return (
            f"Du bist {vorsitz_name}, die VORSITZENDE des Bewerbungs-Beirats. Im Vorsitz beziehst du "
            "KEINE inhaltliche Position — du fasst zusammen. Es gelten die Regeln der folgenden "
            "Charta, insbesondere der Abschnitt „Synthese-Format … Bei Stellen-Checks dreistufig“.\n\n"
            + _charta_kern()
        )

    def _check_synthese_prompt(self) -> str:
        """Die Vorsitzende bekommt die BEREITS BERECHNETE Entscheidung (Design-Entscheidung 4: das
        Dashboard wird deterministisch gerendert, kein LLM-HTML — sie darf die Zahlen NICHT neu erfinden,
        nur einordnen) und liefert strukturiertes JSON statt freiem Markdown, damit der Renderer
        das Risiko-Board/die Kern-Zeilen robust in HTML gießen kann, ohne Markdown zu parsen."""
        e = self.entscheidung
        stimmen_text = " · ".join(f"{w}: {n}" for w, n in e["stimmen"].items())
        bereiche_text = "\n".join(f"- {BEREICHS_LABEL[b]}: {e['bereichs_avg'][b]:.1f}/10"
                                  for b in ABSTIMMUNGS_BEREICHE)
        stimmen_detail = []
        for kopf_id, stimme in self.abstimmung.items():
            m = self.mitglieder[kopf_id]
            if stimme:
                stimmen_detail.append(f"- {m['anzeige']} ({stimme['votum']}): {stimme['begruendung']}")
            else:
                stimmen_detail.append(f"- {m['anzeige']}: ENTHALTUNG (Abstimmung technisch fehlgeschlagen)")
        koepfe_liste = ", ".join(f"{m['id']} = {m['anzeige']}" for m in self.mitglieder.values())
        return (
            f"STELLE: {self.thema}\n\nKontext:\n{self.kontext or '(keiner)'}\n\n"
            f"Debatten-Verlauf ({len(self.beitraege)} Beiträge):\n{self._transkript()}\n\n"
            f"BEREITS BERECHNETE ENTSCHEIDUNG (übernimm diese Zahlen EXAKT, erfinde keine eigenen):\n"
            f"Gesamtscore: {e['gesamt']:.1f}/10 · Ampel: {e['ampel']} · Stimmen: {stimmen_text}"
            + (f" · Enthaltungen: {len(e['enthaltungen'])}" if e["enthaltungen"] else "") + "\n"
            f"Score je Bereich:\n{bereiche_text}\n\n"
            f"Alle Voten mit Begründung:\n" + "\n".join(stimmen_detail) + "\n\n"
            f"Köpfe-IDs (für kern_je_kopf, GENAU diese IDs verwenden): {koepfe_liste}\n\n"
            "Erstelle die dreistufige Stellen-Check-Synthese der Charta als STRUKTURIERTES JSON "
            "(kein Markdown, kein Fließtext davor/danach):\n"
            '{"begruendung": "<wie aus Debatte+Scores das Ergebnis folgt, 3-5 Sätze>", '
            '"bedingt_bedingungen": ["<nur falls Ampel=Bedingt: konkrete Bedingung>", ...], '
            '"risiko_board": [{"risiko": "<Text>", "schwere": "hoch|mittel|gering", '
            '"status": "ungeklaert|in_klaerung|geklaert", "naechster_schritt": "<wer/was klärt es>"}], '
            '"kern_je_kopf": [{"kopf": "<id aus der Liste oben>", "kern": "<1 Satz: stärkster Beitrag '
            'bzw. Votum-Grund>"}], '
            '"empfehlung": "<konkret, umsetzbar, greift die 🔴/🟡-Zeilen des Boards auf>"}\n\n'
            "Risiko-Board PFLICHT (Charta: „Ein Board ohne einziges 🔴/🟡 ist verdächtig — dann wurde "
            "nicht ehrlich geprüft“): mindestens 2 Zeilen, 🔴 zuerst sortieren übernimmt der Renderer. "
            "kern_je_kopf für ALLE sieben Köpfe aus der Liste, auch wer nicht in der Debatte saß "
            "(dann aus dem Votum-Grund)."
        )

    # — Hauptlauf —
    async def laufen(self):
        try:
            await self._ev("status", text=f"Debatte eröffnet — mindestens {self.min_beitraege} Beiträge, "
                                          f"{len(self.teilnehmer)} Köpfe am Tisch.")
            # Phase 77 (Bau-Stufe B): Vorwärm-Schleuse NUR im Keychain-Fallback (Auth-Weg c,
            # Entscheidung 1 — weder keys.json-Key noch agent.env-Token vorhanden). Bei
            # vorhandenem Key/Token läuft der Turn ohnehin über eine stabile, nicht-rotierende
            # Auth-Quelle — eine Vorwärmung wäre dort wirkungslose Zusatzkosten. Scheitert die
            # Vorwärmung, bricht die Debatte SOFORT ab (kein Persona-Fan-out, kein
            # Retry-Gewitter) — die Klartext-Meldung landet über die äußere except-Klausel wie
            # jeder andere Fehler in self.fehler/AgentTask.error.
            if _bestimme_auth_weg() == "keychain":
                vorwaerm_fehler, vorwaerm_kosten = await _keychain_vorwaermen(self.task_id)
                self._erfassen(vorwaerm_kosten)
                if vorwaerm_fehler:
                    raise RuntimeError(vorwaerm_fehler)
                self._notbremse_pruefen()
                self._abbruch_pruefen()   # falls während der bis zu 30s laufenden Vorwärmung
                                          # bereits hart abgebrochen wurde (Task-Center-Cancel)
            while len(self.beitraege) < self.max_beitraege and not self.stop_gewuenscht:
                # 1) Vorsitzende entscheidet (autonome Orchestrierung, live sichtbar).
                #    Retry-Muster "1 Versuch + 1 Retry" (Phase 62B/P2-5, Vorbild:
                #    _abstimmung_durchfuehren/Stellen-Check-Synthese unten) — ein transienter
                #    API-Fehler (jetzt erkannt, s. _turn_anthropic) soll nicht die gesamte
                #    bereits bezahlte Debatte verwerfen. Bleibt der Dispatch nach dem Retry
                #    weiter kaputt, bricht die Debatte ehrlich ab (status="fehler" unten im
                #    äußeren except) — die Vorsitzende darf nicht raten, wer als Nächstes dran ist.
                entscheidung, letzter_fehler = None, ""
                for versuch in range(2):
                    try:
                        zusatz = ("" if versuch == 0 else "\n\nWICHTIG: Antworte NUR mit dem "
                                 "JSON-Objekt, keine Erklärung davor/danach.")
                        roh, kosten = await _turn(self.provider, self.openai_model, self._vorsitz_system(),
                                          self._dispatch_prompt() + zusatz, "sonnet", self._nix,
                                          task_id=self.task_id)
                        self._erfassen(kosten)
                        entscheidung = self._json_extrahieren(roh)
                        if entscheidung:
                            break
                        letzter_fehler = f"nicht als JSON parsebar: {roh[:200]}"
                    except Exception as ex:
                        self._erfassen(getattr(ex, "kosten_usd", 0.0) or 0.0)
                        letzter_fehler = str(ex)[:300]
                self._notbremse_pruefen()
                self._abbruch_pruefen()
                if not entscheidung:
                    raise RuntimeError(f"Vorsitz-Antwort fehlgeschlagen (nach Retry): {letzter_fehler}")
                if entscheidung.get("aktion") == "abschluss":
                    if len(self.beitraege) >= self.min_beitraege:
                        vorsitz_name = self.mitglieder[self.vorsitz_id]["anzeige"]
                        await self._ev("moderation", text=f"{vorsitz_name} schließt die Debatte: "
                                                          f"{entscheidung.get('begruendung', '')}")
                        break
                    entscheidung = None  # verfrühter Abschluss → ignorieren, weiter dispatchen
                if not entscheidung or entscheidung.get("kopf") not in self.mitglieder:
                    # Fallback: seltenst — nimm den Kopf mit den wenigsten Beiträgen
                    zaehler = {m["id"]: 0 for m in self.teilnehmer}
                    for b in self.beitraege:
                        zaehler[b["kopf"]] = zaehler.get(b["kopf"], 0) + 1
                    kopf_id = min(zaehler, key=lambda k: zaehler[k])
                    frage, begruendung = f"Deine Sicht auf: {self.thema}", "Reihum-Fallback"
                else:
                    kopf_id = entscheidung["kopf"]
                    frage = entscheidung.get("frage") or f"Deine Sicht auf: {self.thema}"
                    begruendung = entscheidung.get("begruendung", "")
                m = self.mitglieder[kopf_id]
                vorsitz_name = self.mitglieder[self.vorsitz_id]["anzeige"]
                mod_text = f"{vorsitz_name} ruft {m['anzeige']} auf — {begruendung} „{frage}“"
                mod_ts = datetime.now().isoformat(timespec="seconds")
                await self._ev("moderation", text=mod_text)

                # 2) Der Kopf antwortet — Token-Deltas live. Retry-Muster "1 Versuch + 1 Retry"
                #    (Phase 62B/P1-4+P2-5): ein API-Fehler darf NIE als Beitragstext gespeichert
                #    werden (_turn_anthropic wirft jetzt, statt ihn zurückzugeben). Bleibt der
                #    Kopf nach dem Retry weiter kaputt, wird NUR DIESER Beitrag ausgelassen —
                #    die Debatte läuft weiter, statt komplett zu verwerfen, was ein einzelner
                #    Fehler vor 62B getan hätte (s. Modul-Docstring). moderationen/beitraege
                #    bleiben dabei STRIKT parallel (gleiche Länge): mod_text wird deshalb erst
                #    UNTEN, zusammen mit dem Beitrag, angehängt — _verlauf_html() paart beide
                #    Listen positionsbasiert per zip(); ein einseitig angehängter Moderations-
                #    Eintrag würde jedes folgende Paar um eins verschieben.
                nr = len(self.beitraege) + 1
                await self._ev("beitrag_start", kopf=kopf_id, anzeige=m["anzeige"],
                               farbe=m["farbe"], frage=frage, nr=nr,
                               min=self.min_beitraege, max=self.max_beitraege)
                async def _delta(t, _kopf=kopf_id):
                    await self._ev("delta", kopf=_kopf, text=t)
                text, letzter_fehler = None, ""
                for versuch in range(2):
                    try:
                        # Nur der erste Versuch streamt live wie bisher; ein Retry läuft still
                        # (self._nix) — gleiche Idee wie beim Abstimmungs-/Synthese-Retry, sonst
                        # zeigt die Live-Ansicht Text aus zwei Versuchen hintereinander in
                        # derselben Bubble.
                        callback = _delta if versuch == 0 else self._nix
                        text, kosten = await _turn(self.provider, self.openai_model, self._persona_system(m),
                                           self._persona_prompt(m, frage), m["model"], callback,
                                           task_id=self.task_id)
                        self._erfassen(kosten)
                        break
                    except Exception as ex:
                        self._erfassen(getattr(ex, "kosten_usd", 0.0) or 0.0)
                        letzter_fehler = str(ex)[:300]

                if text is None:
                    # Kopf auslassen (P2-5-Pendant für Personas): kein Beitrag, keine
                    # Moderation, kein _speichern() — es gibt nichts Neues zu persistieren.
                    # Die Live-Ansicht bekommt trotzdem ein ehrliches Ende für die offene
                    # "schreibt…"-Bubble (beitrag_ende), statt für immer hängen zu bleiben.
                    await self._ev("beitrag_ende", kopf=kopf_id, nr=nr,
                                   text=f"(kein Beitrag — nach Fehler übersprungen: {letzter_fehler})")
                    await self._ev("status", text=f"{m['anzeige']} übersprungen (Fehler nach Retry).")
                    self._notbremse_pruefen()
                    self._abbruch_pruefen()
                    continue

                self.moderationen.append({"text": mod_text, "ts": mod_ts})
                self.beitraege.append({"kopf": kopf_id, "anzeige": m["anzeige"], "farbe": m["farbe"],
                                       "frage": frage, "text": text,
                                       "ts": datetime.now().isoformat(timespec="seconds")})
                await self._ev("beitrag_ende", kopf=kopf_id, nr=nr, text=text)
                self._speichern()
                self._notbremse_pruefen()
                self._abbruch_pruefen()

            if self.stop_gewuenscht:
                await self._ev("status", text="Debatte auf Wunsch gestoppt.")
            self._abbruch_pruefen()   # hart abgebrochen während/nach der letzten Runde? → raus,
                                      # OHNE Abstimmung/Synthese (anders als der sanfte Stopp oben)

            if self.modus == "stellen_check":
                # 3) Abstimmung ALLER 7 Köpfe (Charta-Scoring, unabhängig von der Debatten-Teilnahme)
                await self._ev("abstimmung_start")
                self.abstimmung = await self._abstimmung_durchfuehren()
                self._notbremse_pruefen()   # Kosten der 7 Voten wurden in _erfassen() gesammelt
                self._abbruch_pruefen()
                self.entscheidung = self._entscheidung_berechnen(self.abstimmung)
                await self._ev("entscheidung", entscheidung=self.entscheidung)
                self._speichern()

                # 4) Vorsitz-Synthese als strukturiertes JSON (Design-Entscheidung 4: Dashboard wird
                #    deterministisch gerendert — die Zahlen kommen aus self.entscheidung, nicht vom Modell)
                await self._ev("synthese_start")
                parsed, letzter_fehler = None, ""
                for versuch in range(2):        # 1 Versuch + 1 Retry — fängt BEIDE Fehlerarten ab:
                    try:                         # (a) Turn wirft (leer/Timeout), (b) Turn liefert kaputtes JSON
                        zusatz = ("" if versuch == 0 else "\n\nWICHTIG: Antworte NUR mit dem "
                                 "JSON-Objekt, keine Erklärung davor/danach.")
                        roh, kosten = await _turn(self.provider, self.openai_model, self._check_synthese_system(),
                                          self._check_synthese_prompt() + zusatz, "sonnet", self._nix,
                                          task_id=self.task_id)
                        self._erfassen(kosten)     # kein Notbremse-Raise hier — s. _erfassen-Docstring
                        parsed = self._json_extrahieren(roh)
                        if parsed:
                            break
                        letzter_fehler = f"nicht als JSON parsebar: {roh[:200]}"
                    except Exception as ex:
                        letzter_fehler = str(ex)[:300]
                self._notbremse_pruefen()
                self._abbruch_pruefen()
                if not parsed:
                    # Bewusst KEIN raise (Phase 89): Ampel, Gesamtscore und alle sieben Voten
                    # stehen bereits und sind deterministisch aus den Stimmen berechnet — sie
                    # hängen nicht an diesem Text. Der Lauf endet daher regulär, weist die Lücke
                    # aber im Dashboard aus, statt das Ergebnis wegzuwerfen.
                    self.synthese_fehler = letzter_fehler
                    parsed = {
                        "begruendung": ("Die zusammenfassende Einordnung der Vorsitzenden konnte "
                                        "technisch nicht erzeugt werden. Ampel, Gesamtscore und die "
                                        "sieben Einzelvoten unten sind davon unberührt — sie werden "
                                        "deterministisch aus der Abstimmung berechnet, nicht aus "
                                        "diesem Text."),
                        "empfehlung": ("Die Einzelbeiträge der Runde und die Voten unten geben den "
                                       "Diskussionsstand vollständig wieder."),
                    }
                self.check_synthese = parsed
                await self._ev("synthese_ende", text=json.dumps(parsed, ensure_ascii=False))

                # 5) Dashboard deterministisch rendern + JobFile registrieren (kein LLM-HTML)
                self.dashboard_pfad = _dashboard_speichern(self)
                _jobfile_registrieren(self)
                await self._ev("dashboard", pfad=self.dashboard_pfad, entscheidung=self.entscheidung)
            else:
                # Synthese der Vorsitzenden (Modus "frei")
                await self._ev("synthese_start")
                async def _sdelta(t):
                    await self._ev("delta", kopf="synthese", text=t)
                self.synthese, kosten = await _turn(self.provider, self.openai_model, self._vorsitz_system(),
                                            self._synthese_prompt(), "sonnet", _sdelta, task_id=self.task_id)
                self._erfassen(kosten)
                self._notbremse_pruefen()
                self._abbruch_pruefen()
                await self._ev("synthese_ende", text=self.synthese)

            self.status = "fertig"
            await self._ev("fertig", beitraege=len(self.beitraege))
        except _HartAbbruch:
            self.status = "abgebrochen"
            self.fehler = "Vom Nutzer über das Task-Center abgebrochen."
            await self._ev("fehler", text=self.fehler)
        except Exception as e:
            self.status = "fehler"
            self.fehler = str(e)[:500]
            await self._ev("fehler", text=self.fehler)
        finally:
            self._speichern()
            # P2-20: _task_abschliessen() committet ungeschützt in die DB — scheitert der Commit
            # (z. B. "database is locked"), darf das NICHT verhindern, dass das SSE-Ende-Signal
            # unten ankommt. Vorher riss eine Exception hier den kompletten finally-Block ab: die
            # AgentTask-Zeile blieb auf "running" hängen (blockiert den Doppellauf-Guard für
            # diesen Job bis zum nächsten Serverneustart) UND der SSE-Stream zur Oberfläche endete
            # nie (hängende "lädt…"-Anzeige). Jetzt: laut melden, aber weiterlaufen — das Ende-
            # Signal unten läuft dadurch in JEDEM Fall.
            try:
                _task_abschliessen(self)      # Phase 42: AgentTask-Row abschließen
            except Exception as e:            # noqa: BLE001 — s. Kommentar oben (P2-20)
                print(f"[beirat] KRITISCH: _task_abschliessen(Debatte {self.id}, "
                      f"Task {self.task_id}) fehlgeschlagen: {type(e).__name__}: {e} — "
                      f"AgentTask-Zeile bleibt auf 'running' hängen, bis der Server neu startet",
                      flush=True)
            await self.queue.put(None)  # SSE-Ende-Signal — MUSS in JEDEM Fall laufen (P2-20)

    async def _nix(self, _):             # Moderations-Deltas nicht streamen (nur Ergebnis zählt)
        return

    @staticmethod
    def _json_extrahieren(roh: str) -> dict | None:
        """JSON aus einer Modellantwort ziehen — mit Reparatur fehlender Schluss-Klammern.

        Echtfall 23.08.2026: Die Synthese kam mit 5.249 Zeichen
        und `stop_reason: end_turn` zurück, hatte aber 13 öffnende und nur 12 schließende
        Klammern — dem Modell fehlte am Ende genau ein `}`. Der Regex unten fand daraufhin nur
        einen unvollständigen Block, `json.loads` scheiterte, und eine vollständig gelaufene
        Debatte samt Abstimmung wurde verworfen. Ein fehlendes Schlusszeichen ist reparierbar,
        ohne etwas zu erfinden: Es wird NUR balanciert, was oben offen geblieben ist.
        """
        m = re.search(r"\{.*\}", roh, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        repariert = Debatte._klammern_balancieren(roh)
        if repariert:
            try:
                return json.loads(repariert)
            except Exception:
                return None
        return None

    @staticmethod
    def _klammern_balancieren(roh: str) -> str | None:
        """Hängt fehlende `}`/`]` an, wenn die Antwort sonst wohlgeformt ist.

        Klammern INNERHALB von Strings zählen nicht mit (sonst zerlegt ein `{` im Fließtext die
        Bilanz). Endet die Antwort mitten in einem String, wird NICHT repariert — dann fehlt
        echter Inhalt und ein geratenes Anführungszeichen würde einen halben Satz als vollständig
        ausgeben.
        """
        start = roh.find("{")
        if start < 0:
            return None
        offen: list[str] = []
        im_string = False
        maskiert = False
        for zeichen in roh[start:]:
            if im_string:
                if maskiert:
                    maskiert = False
                elif zeichen == "\\":
                    maskiert = True
                elif zeichen == '"':
                    im_string = False
                continue
            if zeichen == '"':
                im_string = True
            elif zeichen in "{[":
                offen.append(zeichen)
            elif zeichen in "}]" and offen:
                offen.pop()
        if im_string or not offen:
            return None
        schluss = "".join("}" if z == "{" else "]" for z in reversed(offen))
        return roh[start:].rstrip() + schluss

    # — Persistenz —
    def _speichern(self):
        DATEN_DIR.mkdir(parents=True, exist_ok=True)
        (DATEN_DIR / f"{self.id}.json").write_text(json.dumps(self.als_dict(), ensure_ascii=False, indent=1))

    def als_dict(self) -> dict:
        return {"id": self.id, "thema": self.thema, "kontext": self.kontext,
                "min_beitraege": self.min_beitraege, "max_beitraege": self.max_beitraege,
                "provider": self.provider, "status": self.status, "gestartet": self.gestartet,
                "modus": self.modus, "job_id": self.job_id,
                "teilnehmer": [{k: m[k] for k in ("id", "anzeige", "farbe")} for m in self.teilnehmer],
                "beitraege": self.beitraege, "moderationen": self.moderationen,
                "synthese": self.synthese, "abstimmung": self.abstimmung,
                "entscheidung": self.entscheidung, "check_synthese": self.check_synthese,
                "dashboard_pfad": self.dashboard_pfad, "fehler": self.fehler}


# ── Task-Center-Anbindung (Phase 42 Stufe A) ──────────────────────────────────────────
# Architektur-Regel (s. lessons.md): AgentTask ist DAS eine Aktivitäts-Log des Systems — jede
# Hintergrund-Aktivität schreibt ihre eigene Row, egal ob Runner-Prozess oder In-Server-Engine
# wie hier. Kurzlebige Session je Statuswechsel (kein Halten über await-Punkte hinweg).
#
# PHASE 65 (P1-6) — BEWUSSTE ENTSCHEIDUNG: diese AgentTask-Zeile bekommt NIE eine `pid`
# hinterlegt (bleibt NULL, fällt bei einem Server-Neustart also in Fall 1 der Crash-Recovery,
# s. agent_runner._running_wiederherstellen() — exakt das bisherige Verhalten, unverändert).
# Begründung, warum das hier RICHTIG ist und keine übersehene Lücke (anders als der Phase-63B-
# Fund, dass diese Engine anfangs GAR KEINE AgentTask-Zeilen schrieb):
#   1. Eine Debatte läuft als asyncio.Task IM Server-Prozess selbst (s. debatte_starten() unten:
#      `asyncio.create_task(d.laufen())`) — es gibt keinen einzelnen Kindprozess, dessen Leben
#      mit der "running"-Dauer dieser Zeile übereinstimmt. Stattdessen spawnt `_turn_anthropic()`
#      (oben) je Diskussionsbeitrag/Dispatch-Entscheidung/Abstimmung/Synthese einen EIGENEN,
#      kurzlebigen `claude -p`-Subprozess (`--max-turns 1`) — pro Debatte oft ein Dutzend Mal.
#      Ein einzelnes `pid`-Feld müsste bei JEDEM dieser Turns neu geschrieben werden statt wie
#      bei agent_runner (ein Subprozess pro Task, einmal gesetzt/einmal geleert) — ein
#      grundsätzlich anderes, invasiveres Muster für ein sehr viel kleineres Risiko (Punkt 3).
#   2. Stirbt der Server-Prozess, stirbt mit ihm auch die Python-Coroutine `laufen()` — es gibt
#      keine externe Instanz, die die Debatte "unbemerkt weiterlaufen" lassen könnte. Das ist der
#      Kernunterschied zu einem agent_runner-Skill: DORT lebt der komplette Skill-Ablauf (inkl.
#      DB-/Dateischreibzugriffen) IM Kindprozess und läuft nach dem Serverende unbeaufsichtigt
#      weiter — HIER lebt die Ablauflogik im Server selbst und endet mit ihm.
#   3. Selbst der EINE Turn-Subprocess, der im ungünstigsten Moment gerade aktiv sein könnte,
#      kann strukturell keinen Schaden anrichten, falls er den Serverabsturz kurzzeitig überlebt:
#      er läuft mit `--tools ""` (Allow-Liste von NICHTS, s. _turn_anthropic weiter oben) UND
#      `cwd=WORK_DIR` (ein leeres Scratch-Verzeichnis AUSSERHALB des Projekts) — er hat also
#      weder Bash/Write/Edit-Zugriff noch überhaupt einen Pfad zur Datenbank oder zu `outputs/`.
#      Das genau ist der Schaden, den P1-6 verhindern soll ("weiter in dieselbe Datenbank und
#      nach outputs/ schreiben") — hier technisch ausgeschlossen, nicht nur unwahrscheinlich.
#      Zusätzlich ist er über `MAX_TURN_SEKUNDEN` (300s) auf eine Bruchteilslaufzeit eines
#      agent_runner-Skills (bis zu 2400s) begrenzt.
#   4. `_turn_anthropic()` startet OHNE `start_new_session=True` — anders als agent_runner
#      bewusst NICHT von der Prozessgruppe des Servers abgekoppelt. Das genau in der Spec
#      benannte Ctrl+C-Szenario (SIGINT an die gesamte Vordergrund-Prozessgruppe) erreicht einen
#      aktiven Turn-Subprocess damit i. d. R. direkt mit — er stirbt meist zusammen mit dem
#      Server, statt (wie ein claude-p-Skill von agent_runner) davon isoliert zu überleben.
# Fazit: eine PID hier zu pflegen würde Komplexität (Schreiben bei jedem Turn) gegen ein Risiko
# eintauschen, das strukturell (Tool-/Pfad-Sperre) bereits ausgeschlossen ist. Sollte sich diese
# Architektur künftig ändern (z. B. Turns bekommen Tool-Zugriff), gehört diese Entscheidung neu
# geprüft.

def _task_anlegen(d: Debatte) -> int:
    kind = "beirat-stellen-check" if d.modus == "stellen_check" else "beirat-debatte"
    params = {"debatte_id": d.id, "min_beitraege": d.min_beitraege,
              "teilnehmer": [m["id"] for m in d.teilnehmer], "provider": d.provider}
    with Session(engine) as s:
        t = AgentTask(kind=kind, job_id=d.job_id, prompt=d.thema,
                      params_json=json.dumps(params, ensure_ascii=False),
                      status="running", started_at=datetime.utcnow())
        s.add(t)
        s.commit()
        s.refresh(t)
        # Phase 63B (D3): nur noch der Basename — log_path ist ein Bezeichner, kein wörtlicher
        # Pfad mehr (s. agent_runner.py Konstanten-Block/resolve_log_path() für die Begründung).
        t.log_path = f"task_{t.id}.jsonl"
        s.add(t)
        s.commit()
        return t.id


def _task_abschliessen(d: Debatte) -> None:
    if not d.task_id:
        return
    if d.modus == "stellen_check" and d.entscheidung:
        result = {"debatte_id": d.id, "ampel": d.entscheidung.get("ampel"),
                  "score": d.entscheidung.get("gesamt"), "stimmen": d.entscheidung.get("stimmen"),
                  "dashboard_path": d.dashboard_pfad}
    else:
        result = {"debatte_id": d.id, "beitraege": len(d.beitraege)}
    if d.provider == "openai":
        result["hinweis"] = "OpenAI-Kosten nicht erfasst (nur Anthropic-Turns fließen in cost_usd ein)"
    with Session(engine) as s:
        t = s.get(AgentTask, d.task_id)
        if not t:
            return
        jetzt = datetime.utcnow()
        t.status = {"fertig": "done", "abgebrochen": "cancelled"}.get(d.status, "failed")
        t.finished_at = jetzt
        t.duration_s = round((jetzt - (t.started_at or jetzt)).total_seconds(), 1)
        t.num_turns = d.num_turns
        t.cost_usd = round(d.kosten_usd, 4)
        t.error = d.fehler
        t.result_json = json.dumps(result, ensure_ascii=False)[:20000]
        s.add(t)
        s.commit()


def debatte_starten(thema, kontext, min_beitraege, teilnehmer_ids, provider, openai_model,
                    modus="frei", job_id=None, job_titel="", job_firma="",
                    company_fit_fehlt=False) -> Debatte:
    d = Debatte(thema, kontext, min_beitraege, teilnehmer_ids, provider, openai_model,
               modus=modus, job_id=job_id, job_titel=job_titel, job_firma=job_firma,
               company_fit_fehlt=company_fit_fehlt)
    DEBATTEN[d.id] = d
    d.task_id = _task_anlegen(d)
    d.task = asyncio.create_task(d.laufen())   # Aufrufer ist ein async-Endpunkt → Loop läuft
    # Registry klein halten: fertige alte Debatten rauswerfen (Dateien bleiben)
    fertige = [k for k, v in DEBATTEN.items() if v.status != "läuft"]
    for k in fertige[:-5]:
        DEBATTEN.pop(k, None)
    return d


def laufende_stellen_check_fuer_job(job_id: int) -> Debatte | None:
    """Für den 409-Check im Endpoint — Design-Entscheidung 6: pro JOB, nicht global (anders als
    der bestehende Free-Debatten-Endpunkt, der jede zweite Debatte global blockt)."""
    for d in DEBATTEN.values():
        if d.status == "läuft" and d.modus == "stellen_check" and d.job_id == job_id:
            return d
    return None


def stop(debatte_id: str) -> bool:
    """Task-Center-Cancel-Weiche (Phase 42 Stufe B, aufgerufen aus main.py::cancel_task).

    ACHTUNG Namensverwechslung vermeiden: das ist NICHT derselbe Pfad wie der bestehende
    sanfte `POST /debatten/{id}/stop` (Design aus Phase 39, „■ Stoppen"-Button auf /beirat —
    beendet den laufenden Beitrag und geht dann regulär in Abstimmung/Synthese, endet als
    „fertig"). Diese Funktion ist ein HARTER Abbruch: spätestens am nächsten Checkpoint
    (s. `_abbruch_pruefen`) bricht `laufen()` OHNE Abstimmung/Synthese ab, die AgentTask-Row
    landet auf 'cancelled'. Gibt False zurück, wenn die Debatte nicht (mehr) läuft — der
    Aufrufer meldet das wie beim Runner als 409."""
    d = DEBATTEN.get(debatte_id)
    if not d or d.status != "läuft":
        return False
    d.hart_abgebrochen = True
    d.stop_gewuenscht = True   # verlässt auch die while-Schleife sofort, falls sie noch läuft
    return True


def debatten_liste() -> list[dict]:
    """Alle gespeicherten Debatten (Dateien), neueste zuerst — schlank für die Übersicht."""
    out = []
    if DATEN_DIR.exists():
        for f in sorted(DATEN_DIR.glob("*.json"), reverse=True):
            try:
                d = json.loads(f.read_text())
                out.append({"id": d["id"], "thema": d["thema"], "status": d["status"],
                            "gestartet": d["gestartet"], "beitraege": len(d.get("beitraege", [])),
                            "min_beitraege": d.get("min_beitraege"),
                            "modus": d.get("modus", "frei"), "job_id": d.get("job_id")})
            except Exception:
                continue
    return out


def debatte_lesen(debatte_id: str) -> dict | None:
    d = DEBATTEN.get(debatte_id)
    if d:
        return d.als_dict()
    f = DATEN_DIR / f"{debatte_id}.json"
    if f.exists() and f.resolve().parent == DATEN_DIR.resolve():
        return json.loads(f.read_text())
    return None


# ── Dashboard-Renderer (Phase 40, Design-Entscheidung 4) — DETERMINISTISCH, kein LLM-HTML ──
# Das CSS kommt seit P2-72 aus `pipeline/bericht_stil.py` (Muster pipeline/transcript_report.py)
# + eine kleine, projektspezifische Ergänzung für Ampel-Banner/Score-Balken/Risiko-/Stimmen-Tabelle.

_REPORT_DIR = PROJEKT_ROOT / "data" / "beirat"

# P2-72: Das gemeinsame Thema kommt aus `pipeline/bericht_stil.py`, mit den Werten des geltenden
# Designs. Hier steht nur, worin das Dashboard davon abweicht — so, dass es genauso aussieht wie vor
# der Umstellung (Leitentscheidung 8: nichts „bereinigen“):
#   * `.dot` ist 10 statt 14 px (die Ampel steht in einer Meta-Zeile, nicht im Fließtext),
#   * `details.volltext .inner` (Innenabstand des aufgeklappten Verlaufs),
#   * der Block „Beirats-Stellen-Check“ (Ampel-Banner, Score-Balken, Risiko- und Stimmen-Tabelle),
#   * `.caveat`: Die Hinweiszeilen des Dashboards tragen die Klasse, hatten aber nie eine Regel und
#     sahen ungestaltet aus. Die Vorlage hat einen amber Hinweiskasten; `revert` nimmt ihn für dieses
#     Dashboard zurück, damit es genauso aussieht wie bisher (eine Zeile streichen, um ihn zu bekommen).
# Die Ampel-Pastelle und Statusfarben im Block bleiben feste Werte (Bedeutung, Leitentscheidung 2);
# Spur, Rahmen und Karte sind Variablen des Designs.
_CSS_ZUSATZ = """
.dot{width:10px;height:10px}
details.volltext .inner{padding:0 18px 18px}
.caveat{margin-top:revert;background:revert;border:revert;border-radius:revert;padding:revert;font-size:revert;color:revert}
.caveat b{color:revert}
.ampel-banner{border-radius:12px;padding:20px 24px;margin-bottom:4px;display:flex;
align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}
.ampel-banner.gruen{background:#eafaf1;border:1px solid #bfe4cd}
.ampel-banner.gelb{background:#fbf3e6;border:1px solid #ecd9b3}
.ampel-banner.rot{background:#fbe9e7;border:1px solid #f0c4bc}
.ampel-banner .titel{font-size:20px;font-weight:800}
.ampel-banner.gruen .titel{color:#18A957} .ampel-banner.gelb .titel{color:#8a5b0c} .ampel-banner.rot .titel{color:#E5484D}
.ampel-banner .sub{font-size:13.5px;color:var(--muted);margin-top:4px}
.scorebars{display:flex;flex-direction:column;gap:9px;margin-top:16px}
.scorebar-row{display:grid;grid-template-columns:220px 1fr 42px;align-items:center;gap:10px;font-size:13.5px}
.scorebar-track{background:var(--spur);border-radius:6px;height:10px;overflow:hidden}
.scorebar-fill{height:100%;border-radius:6px;background:var(--accent)}
.scorebar-val{text-align:right;font-weight:700}
table.risiko td.schwere-hoch{color:var(--red);font-weight:700}
table.risiko td.schwere-mittel{color:var(--amber);font-weight:700}
table.risiko td.schwere-gering{color:var(--green);font-weight:700}
table.stimmen{width:100%;border-collapse:collapse;background:var(--paper-2);border:1px solid var(--rahmen);
border-radius:12px;overflow:hidden;box-shadow:var(--shadow);font-size:12px}
table.stimmen th{text-align:center;background:var(--spur);color:var(--muted);font-size:9.5px;letter-spacing:.03em;
text-transform:uppercase;padding:8px 5px;border-bottom:1px solid var(--rahmen)}
table.stimmen th:first-child{text-align:left}
table.stimmen td{padding:8px 5px;border-bottom:1px solid var(--spur);text-align:center}
table.stimmen td:first-child{text-align:left;font-weight:600;font-size:12.5px}
table.stimmen tr:last-child td{border-bottom:none}
.votum-bewerben{color:var(--green);font-weight:700} .votum-bedingt{color:var(--amber);font-weight:700}
.votum-nicht{color:var(--red);font-weight:700} .enthaltung{color:var(--muted);font-style:italic}
.verlauf-eintrag{margin-bottom:16px} .verlauf-eintrag:last-child{margin-bottom:0}
.verlauf-eintrag .sprecher{font-weight:700;font-size:13px;margin-bottom:2px}
.verlauf-eintrag .frage{font-size:12px;color:var(--muted);margin-bottom:5px;font-style:italic}
.verlauf-eintrag p{margin:0;font-size:13.5px;white-space:pre-wrap}
@media print{table.risiko,table.stimmen{box-shadow:none}}
""" + DRUCK_SEITENFARBE_BEHALTEN + "\n"


def _css() -> str:
    """Das CSS des Dashboards, bei jedem Aufruf mit dem Design, das gerade gilt."""
    return bericht_css(_CSS_ZUSATZ)

_AMPEL_META = {"Bewerben": ("🟢", "gruen", "green", "BEWERBEN"),
              "Bedingt": ("🟡", "gelb", "amber", "BEDINGT BEWERBEN"),
              "Nicht": ("🔴", "rot", "red", "NICHT BEWERBEN")}
_SCHWERE_KLASSE = {"hoch": "schwere-hoch", "mittel": "schwere-mittel", "gering": "schwere-gering"}
_SCHWERE_ICON = {"hoch": "🔴", "mittel": "🟡", "gering": "🟢"}
_STATUS_ICON = {"ungeklaert": "❓", "in_klaerung": "🔄", "geklaert": "✅"}
_VOTUM_KLASSE = {"Bewerben": "votum-bewerben", "Bedingt": "votum-bedingt", "Nicht": "votum-nicht"}
# Phase 80 (§18.4): Scorebar-Füllfarbe wertabhängig statt einfarbig — Score (0-10) gerundet und
# auf 1..5 geklemmt, je Stufe eine Statusfarbe (Rollback: tasks/spec_phase80_styleguide_v18_theme.md).
# P2-72: Die Skala steht in `pipeline/zustandsfarben.py` (eine Tabelle, gleich der in ui.tsx), nicht
# mehr als eigene Kopie hier.


def _esc(s) -> str:
    return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _de_zahl(x: float, nachkomma: int = 1) -> str:
    return f"{x:.{nachkomma}f}".replace(".", ",")


def _score_balken_html(bereichs_avg: dict) -> str:
    zeilen = []
    for bereich in ABSTIMMUNGS_BEREICHE:
        wert = bereichs_avg.get(bereich, 0.0)
        pct = max(0, min(100, wert / 10 * 100))
        stufe = max(1, min(5, round(wert)))   # Phase 80 §18.4: Score 0-10 → Stufe 1..5 für die Fill-Farbe
        zeilen.append(
            f'<div class="scorebar-row"><span>{_esc(BEREICHS_LABEL[bereich])}</span>'
            f'<div class="scorebar-track"><div class="scorebar-fill" '
            f'style="width:{pct:.0f}%;background:{zustandsfarben.score_farbe(stufe)[0]}"></div></div>'
            f'<span class="scorebar-val">{_de_zahl(wert)}</span></div>'
        )
    return "\n".join(zeilen)


def _risiko_board_html(zeilen: list) -> str:
    if not zeilen:
        return '<p class="kv">Kein Risiko-Board geliefert — im Zweifel selbst nachfragen.</p>'
    zeilen = sorted(zeilen, key=lambda z: {"hoch": 0, "mittel": 1, "gering": 2}.get(z.get("schwere"), 3))
    rows = []
    for z in zeilen:
        klasse = _SCHWERE_KLASSE.get(z.get("schwere"), "")
        icon = _SCHWERE_ICON.get(z.get("schwere"), "⚪")
        status_icon = _STATUS_ICON.get(z.get("status"), "❓")
        rows.append(
            f'<tr><td>{icon}</td><td>{_esc(z.get("risiko"))}</td>'
            f'<td class="{klasse}">{_esc((z.get("schwere") or "").capitalize())}</td>'
            f'<td>{status_icon}</td><td>{_esc(z.get("naechster_schritt") or "—")}</td></tr>'
        )
    return (
        '<table class="score risiko"><thead><tr><th></th><th>Risiko / Offener Punkt</th>'
        '<th>Schwere</th><th>Status</th><th>Nächster Schritt</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def _stimmen_matrix_html(abstimmung: dict, mitglieder: dict) -> str:
    kopf_ids = sorted(mitglieder.keys())
    head_labels = "".join(f'<th>{_esc(BEREICHS_KURZ[b])}</th>' for b in ABSTIMMUNGS_BEREICHE)
    rows = []
    for kid in kopf_ids:
        m = mitglieder[kid]
        stimme = abstimmung.get(kid)
        if not stimme:
            rows.append(f'<tr><td>{_esc(m["anzeige"])}</td>' + "<td>—</td>" * len(ABSTIMMUNGS_BEREICHE)
                       + '<td class="enthaltung">Enthaltung</td></tr>')
            continue
        scores = stimme.get("scores", {})
        score_cells = "".join(f'<td>{scores.get(b, 0):.0f}</td>' for b in ABSTIMMUNGS_BEREICHE)
        votum = stimme.get("votum", "")
        klasse = _VOTUM_KLASSE.get(votum, "")
        rows.append(f'<tr><td>{_esc(m["anzeige"])}</td>{score_cells}<td class="{klasse}">{_esc(votum)}</td></tr>')
    return (
        f'<table class="stimmen"><thead><tr><th>Kopf</th>{head_labels}<th>Votum</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def _kern_je_kopf_html(kern_liste: list, mitglieder: dict) -> str:
    kern_map = {k.get("kopf"): k.get("kern") for k in (kern_liste or [])}
    items = []
    for kid in sorted(mitglieder.keys()):
        m = mitglieder[kid]
        kern = kern_map.get(kid) or "(kein Kern geliefert)"
        items.append(f'<li><b>{_esc(m["anzeige"])}:</b> {_esc(kern)}</li>')
    return f'<ul class="clean">{"".join(items)}</ul>'


def _verlauf_html(beitraege: list, moderationen: list) -> str:
    teile = []
    for mod, b in zip(moderationen, beitraege):
        farbe = b.get("farbe") or "#333"
        teile.append(
            f'<div class="verlauf-eintrag"><p class="sprecher" style="color:{_esc(farbe)}">'
            f'{_esc(b.get("anzeige"))}</p><p class="frage">{_esc(mod.get("text"))}</p>'
            f'<p>{_esc(b.get("text"))}</p></div>'
        )
    return "\n".join(teile) if teile else "<p>(keine Debatten-Beiträge)</p>"


def _dashboard_html(d: "Debatte") -> str:
    e, cs = d.entscheidung, d.check_synthese
    emoji, klasse, dotklasse, label = _AMPEL_META[e["ampel"]]
    heute_iso = datetime.now().strftime("%Y-%m-%d")
    heute_de = datetime.now().strftime("%d.%m.%Y %H:%M")
    n_enthaltungen = len(e["enthaltungen"])
    stimmen_text = f'{e["stimmen"]["Bewerben"]}/7 Bewerben'
    if n_enthaltungen:
        stimmen_text += f" ({n_enthaltungen} Enthaltung{'en' if n_enthaltungen != 1 else ''})"

    bedingt_html = ""
    if e["ampel"] == "Bedingt" and cs.get("bedingt_bedingungen"):
        punkte = "".join(f"<li>{_esc(p)}</li>" for p in cs["bedingt_bedingungen"])
        bedingt_html = f'<div style="margin-top:12px"><p class="kv">Bedingungen</p><ul class="clean">{punkte}</ul></div>'

    titel_seite = f"Beirats-Stellen-Check · {_esc(d.job_firma)}"
    meta_html = (
        f'<div><p class="k">Ampel</p><p class="v"><span class="dot {dotklasse}"></span>{label}</p></div>'
        f'<div><p class="k">Gesamtscore</p><p class="v">{_de_zahl(e["gesamt"])} / 10</p></div>'
        f'<div><p class="k">Stimmen</p><p class="v">{_esc(stimmen_text)}</p></div>'
        f'<div><p class="k">Datum</p><p class="v">{heute_iso}</p></div>'
    )
    warn_html = ""
    if d.company_fit_fehlt:
        warn_html = ('<div class="caveat"><b>Hinweis:</b> Für diese Firma lag noch kein '
                     "Company-Fit-Check vor — der Beirat hat auf dieser Lücke ausdrücklich debattiert, "
                     "keine Annahmen ersetzt.</div>")
    if getattr(d, "synthese_fehler", None):
        warn_html += ('<div class="caveat"><b>Hinweis:</b> Die zusammenfassende Einordnung der '
                      "Vorsitzenden fehlt — sie konnte technisch nicht erzeugt werden ("
                      + _esc(str(d.synthese_fehler)[:160]) + "). Ampel, Gesamtscore und die sieben "
                      "Voten sind davon unberührt.</div>")

    _FAVICON = favicon_link()      # P2-72: Icon des geltenden Designs, bei jedem Dashboard frisch
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">{_FAVICON}
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titel_seite}</title>
<style>{_css()}</style>
</head>
<body>
<div class="wrap">
  <header class="head">
    <p class="eyebrow">Beirats-Stellen-Check</p>
    <h1>{_esc(d.job_titel) or "Unbekannte Rolle"}</h1>
    <p class="sub">{_esc(d.job_firma)} · Job {d.job_id} · {heute_iso}</p>
    <div class="meta">{meta_html}</div>
  </header>

  {warn_html}

  <h2 class="sec">1. Kurzentscheidung</h2>
  <div class="ampel-banner {klasse}">
    <div><div class="titel">{emoji} {label}</div>
      <div class="sub">Gesamtscore {_de_zahl(e["gesamt"])} / 10 · {_esc(stimmen_text)}</div></div>
  </div>
  <div class="scorebars">{_score_balken_html(e["bereichs_avg"])}</div>
  {bedingt_html}

  <h2 class="sec">2. Risiko-Board</h2>
  {_risiko_board_html(cs.get("risiko_board"))}

  <h2 class="sec">3. Begründung, Kern je Kopf &amp; Empfehlung</h2>
  <div class="card">
    <p class="kv">Begründung</p>
    <p>{_esc(cs.get("begruendung"))}</p>
    <p class="kv" style="margin-top:14px">Kern je Kopf</p>
    {_kern_je_kopf_html(cs.get("kern_je_kopf"), d.mitglieder)}
    <p class="kv" style="margin-top:14px">Empfehlung</p>
    <p>{_esc(cs.get("empfehlung"))}</p>
  </div>

  <h2 class="sec">4. Abstimmungs-Matrix (alle 7 Köpfe)</h2>
  {_stimmen_matrix_html(d.abstimmung, d.mitglieder)}

  <h2 class="sec">5. Debatten-Verlauf</h2>
  <details class="volltext">
    <summary>{len(d.beitraege)} Beiträge anzeigen/verbergen</summary>
    <div class="inner">{_verlauf_html(d.beitraege, d.moderationen)}</div>
  </details>

  <div class="foot">
    <span>Bewerbungs-Mgmt · erzeugt am {heute_de}</span>
    <span>Beirats-Einschätzung — empfiehlt, entscheidet nicht. Das letzte Wort hast du.</span>
  </div>
</div>
</body>
</html>
"""


def _freier_name(ordner: Path, fname: str) -> str:
    """Kollision → _2, _3 … (identisches Muster wie app/main.py::_freier_name)."""
    if not (ordner / fname).exists():
        return fname
    stem, punkt, ext = fname.rpartition(".")
    n = 2
    while (ordner / f"{stem}_{n}{punkt}{ext}").exists():
        n += 1
    return f"{stem}_{n}{punkt}{ext}"


def _dashboard_speichern(d: "Debatte") -> str:
    """Rendert + speichert das Dashboard-HTML UND die Rohdaten (Nachvollziehbarkeit/Verifikation)
    unter data/beirat/. Gibt den projekt-root-relativen Pfad der HTML-Datei zurück."""
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    base = report_filename("Beirat", d.job_firma, d.job_titel)
    html_name = _freier_name(_REPORT_DIR, f"{base}.html")
    (_REPORT_DIR / html_name).write_text(_dashboard_html(d), encoding="utf-8")
    roh_name = html_name[:-5] + "_rohdaten.json"
    rohdaten = {
        "debatte_id": d.id, "job_id": d.job_id, "job_titel": d.job_titel, "job_firma": d.job_firma,
        "gewichte": GEWICHTE, "entscheidung": d.entscheidung, "abstimmung": d.abstimmung,
        "check_synthese": d.check_synthese,
    }
    (_REPORT_DIR / roh_name).write_text(json.dumps(rohdaten, ensure_ascii=False, indent=1), encoding="utf-8")
    return f"data/beirat/{html_name}"


def _jobfile_registrieren(d: "Debatte") -> None:
    """Neue JobFile-Row (kind='Beirats-Check') — erscheint automatisch unter 'Dateien & Dokumente'
    (main.py::get_job liest alle JobFile-Rows), löschbar über den bestehenden Papierkorb-Weg.
    Frische Session (Hintergrund-Task, kein Request-Kontext mehr) — Muster wie pipeline/*.py."""
    emoji = _AMPEL_META[d.entscheidung["ampel"]][0]
    label = _AMPEL_META[d.entscheidung["ampel"]][3]
    stimmen = d.entscheidung["stimmen"]["Bewerben"]
    # Format-Kontrakt: pipeline/export_excel.py::_BEIRAT_NOTE_RE parst "EMOJI ZAHL ·…" zu
    # Ampel-Zahl-Zellen (Phase 75) — bei Format-Änderung hier dort den Regex nachziehen
    # (Abweichung degradiert im Export nur zum Rohtext, kein Crash).
    note = f"{emoji} {_de_zahl(d.entscheidung['gesamt'])} · {stimmen}/7 {label.title()}"
    with Session(engine) as s:
        row = JobFile(job_id=d.job_id, kind="Beirats-Check",
                      filename=Path(d.dashboard_pfad).name, file_path=d.dashboard_pfad, note=note)
        s.add(row)
        s.commit()
