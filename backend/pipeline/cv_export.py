#!/usr/bin/env python3
"""CV-Export: angepasste .docx nach der Namenskonvention des Nutzers umbenennen + PDF erzeugen.

Sobald eine CVVersion registriert wird (pipeline.deepdive.register), benennt dieses
Modul die .docx nach CV_<Name>_<Firma>_<Position>[_DE|_EN] um und erzeugt daneben ein
PDF gleichen Namens. Beide landen in outputs/cv/ und erscheinen am Job-Detail.

PDF-Konvertierung: **AUSSCHLIESSLICH LibreOffice headless** (soffice --convert-to pdf) — kein
sichtbares Fenster, keine macOS-Automation-Freigabe, deterministisch, voll headless-tauglich.
Installiert via `brew install --cask libreoffice` (Stand 2026-07-11: LibreOffice 26.2.x).
Es gibt bewusst KEINEN Word/AppleScript-Fallback mehr (entfernt 2026-07-11 auf Vorgabe):
Word braucht ein sichtbares Fenster und eine manuelle Automation-Freigabe — das widerspricht
headless-Läufen (Runner/Skills ohne Nutzer-Interaktion). Fehlt `soffice`, schlägt die
PDF-Erzeugung kontrolliert fehl (docx bleibt trotzdem registriert, s. `export()`).

Dokument-Engine (Phase 46 Stufe A, 21.07.2026) — `_nachbearbeiten()` läuft in `export()` auf
der umbenannten .docx VOR der PDF-Konvertierung (.docx UND PDF profitieren beide):
  1. Seitenumbruch-Schutz: Abschnitts-Überschriften (`keep_with_next`) + Berufserfahrungs-/
     Ausbildungs-Stationen (Ketten aus `keep_with_next` + `keep_together`) — verhindert, dass
     eine Station unsauber mitten am Seitenende bricht. Erkennung GEGEN die echte
     `data/cv_basis/base_de.docx`/`base_en.docx`-Struktur geprüft (nicht geraten): Abschnitts-Überschriften
     tragen den Style „Heading 1“; der Anker jeder Station ist die „Normal“-Zeile mit TAB-Zeichen
     (Muster „<Firma>\t<Zeitraum>“, z. B. „Beispiel GmbH\tNov. 2024 – heute“ — in BEIDEN
     Sprachvarianten identisch, kommt NUR an Stations-Ankern vor). Seit Phase 76 (Workday-
     Optimierung „v9 ATS") steht der JOBTITEL als eigene fette Normal-Zeile DIREKT VOR dieser
     Tab-Zeile (Reihenfolge: Titel → Firma\tZeitraum → kursive Firmenbeschreibung → Bullets) —
     die Ketten-Logik nimmt ihn über `_stationsgrenzen()` mit in die Station auf. Alt-Format
     (Titel NACH der Tab-Zeile, bis v7) und die einzeiligen Ausbildungszeilen funktionieren
     unverändert.
  2. Fußzeile „<Name> · Seite {PAGE} von {NUMPAGES}“ — echte Word-Feldcodes (oxml), damit
     LibreOffice/Word die Werte selbst berechnen. Name aus `config/profil.md` (## Identität →
     „**Name:**“ via `pipeline/user_profile.py`), Fallback „Bewerber“ (Phase 71A).
Fehlertolerant: schlägt die Nachbearbeitung bei einer ungewöhnlichen Vorlage fehl, wird sie
übersprungen (Grund im Rückgabe-Dict, Muster `pdf_fehler`) — Umbenennung/PDF laufen trotzdem.
Idempotent: ein zweiter Lauf auf derselben Datei baut die Fußzeile neu (nicht additiv) und
setzt dieselben keep-Eigenschaften erneut (kein Duplizieren möglich, reine Bool-Flags).

CLI (Re-Export / Nachrüsten alter Versionen jederzeit möglich):
    cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.cv_export <cv_version_id>
"""
import contextlib
import copy
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph
from sqlmodel import Session

from app import naming
from app.db import engine, init_db
from app.models import Application, Company, CVVersion, Job
from pipeline import bewerbungssprache

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Bewerbung_Mgmt_System/

def _rel(path):
    """Pfad relativ zum Projekt-Root speichern (portabel). Immer mit '/'-Separator
    (as_posix) — die Werte landen in der DB und werden zu Download-URLs; unter Windows
    waeren os-native Backslashes dort falsch (Phase 71 Abnahme, Windows-CI-Befund)."""
    if not path:
        return None
    p = Path(path)
    if p.is_absolute():
        try:
            return p.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return p.as_posix()
    return Path(path).as_posix()


# P2-56: Woraus ein Export seine Quelle nehmen darf. `CVVersion.file_path` und
# `Application.cover_letter_path` stehen in der DB; `export()` und `export_cover_letter()`
# verschieben die Datei dahinter, `entwurf_anwenden()` überschreibt sie. Ohne Eingrenzung träfe
# das jede Datei, auf die der Pfad zeigt: data/bewerbung.sqlite landete in outputs/cv, der
# Basis-CV (Vorlage aller Skills) ebenso oder mit Entwurfstext überschrieben. Heute setzen diese
# Felder nur Skills (deepdive.register_entwurf, cover_letter_render), keine API; die Grenze ist
# Härtung. Die Ordner sind ein Teil der Positivliste `main._ARTEFAKT_ORDNER`
# (test_cv_quellordner_liegen_in_der_positivliste hält beides zusammen).
_CV_QUELLEN = ("data/cv_basis/entwuerfe", "data/tmp", "outputs/cv_entwuerfe", "outputs/cv")
_ANSCHREIBEN_QUELLEN = ("outputs/anschreiben", "data/tmp")


def _im_ordner(rel_path, ordner, endung) -> Optional[Path]:
    """Aufgelöster Pfad, wenn `rel_path` (aus der DB, projekt-relativ oder absolut) in einem der
    `ordner` liegt und die `endung` hat, sonst None. Strukturell über `parents` wie
    `main._erlaubter_artefakt`: `..` und Symlinks zählen dort, wo sie hinzeigen, und
    data/cv_basis/base_de.docx liegt nicht in data/cv_basis/entwuerfe."""
    try:
        p = (PROJECT_ROOT / rel_path).resolve()
    except (OSError, RuntimeError, ValueError):   # Nullbyte, Symlink-Schleife
        return None
    if p.suffix.lower() == endung and any((PROJECT_ROOT / o).resolve() in p.parents for o in ordner):
        return p
    return None


# --- Konverter 1 (primär): LibreOffice headless -----------------------------
# Kandidatenpfade für die soffice-Binary (brew-Symlink zuerst, dann App-Bundle) — macOS,
# Reihenfolge/Verhalten unverändert seit je her (Phase 71D ergänzt NUR die Windows-Liste
# darunter, rührt diese hier nicht an).
_SOFFICE_CANDIDATES = (
    "/opt/homebrew/bin/soffice",
    "/usr/local/bin/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
)
# Windows-Standardinstallationspfade (Phase 71D, Windows-Grundlagen) — 64-Bit-Programme zuerst,
# dann die 32-Bit-Variante ("Program Files (x86)", der übliche Ort für ein 32-Bit-LibreOffice
# auf einem 64-Bit-Windows). PATH (`shutil.which`) bleibt auf JEDER Plattform der letzte
# Fallback, s. _soffice_bin() unten.
_SOFFICE_CANDIDATES_WINDOWS = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)


def _soffice_kandidaten() -> tuple:
    """Plattform-Kandidatenliste für `_soffice_bin()`.

    Eigene Funktion statt eines Inline-Checks, damit das macOS-Verhalten Byte-für-Byte
    unverändert bleibt (Spec-Vorgabe Phase 71D): `_SOFFICE_CANDIDATES` wird auf macOS/Linux in
    UNVERÄNDERTER Reihenfolge durchsucht (feste Installationsorte VOR PATH, wie bisher);
    Windows bekommt eine eigene, additive Liste nach demselben Muster (feste Installationsorte
    zuerst, PATH-Fallback identisch für beide Plattformen in `_soffice_bin()`)."""
    if os.name == "nt":
        return _SOFFICE_CANDIDATES_WINDOWS
    return _SOFFICE_CANDIDATES


def _soffice_bin():
    for c in _soffice_kandidaten():
        if Path(c).exists():
            return c
    return shutil.which("soffice")


def _to_pdf_soffice(docx_abs: str, pdf_abs: str):
    """docx → pdf via `soffice --headless --convert-to pdf`. Kein Fenster, keine Freigabe.

    soffice benennt die Ausgabe nach dem INPUT-Stem in --outdir. Wir konvertieren in ein
    temporäres Verzeichnis und verschieben die erzeugte PDF exakt auf pdf_abs — so ist der
    Zielname garantiert korrekt, auch wenn docx- und pdf-Stem mal abweichen.
    Ein eigenes UserInstallation-Profil (im Temp) macht den Lauf konfliktfrei und
    unabhängig von einer evtl. offenen GUI-LibreOffice.

    P2-18: eigene Prozessgruppe (`start_new_session=True`) + `os.killpg` beim Timeout — Muster
    1:1 aus `agent_runner` übernommen (dortiger Spawn mit `start_new_session=True` + dessen
    `_kill(pid)`, Phase 65). soffice spaltet bekanntermaßen Kindprozesse ab; `subprocess.run(
    timeout=…)` killt beim Timeout nur die von IHM gestartete Top-Level-PID — etwaige
    Kindprozesse würden als Waisen weiterlaufen. Deshalb hier bewusst `Popen` statt der
    komfortableren `run()`: nur mit der PID selbst in der Hand lässt sich beim Timeout die
    GANZE Gruppe treffen. Die Timeout-Fehlermeldung bleibt wortgleich (nur das Aufräumen ändert
    sich).
    """
    soffice = _soffice_bin()
    if not soffice:
        return False, (
            "LibreOffice (soffice) nicht gefunden — PDF-Erzeugung ist headless-only "
            "und braucht `brew install --cask libreoffice`. Kein interaktiver Fallback "
            "(Word) mehr vorhanden."
        )

    with tempfile.TemporaryDirectory(prefix="cvpdf_") as tmp:
        profile = f"file://{tmp}/profile"
        outdir = str(Path(tmp) / "out")
        Path(outdir).mkdir()
        proc = subprocess.Popen(
            [soffice, "--headless", "--nologo", "--nofirststartwizard",
             f"-env:UserInstallation={profile}",
             "--convert-to", "pdf", "--outdir", outdir, docx_abs],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=True,   # eigene Prozessgruppe -> beim Timeout gezielt killbar
        )
        try:
            stdout, stderr = proc.communicate(timeout=180)
            returncode = proc.returncode
        except subprocess.TimeoutExpired:
            # os.killpg statt proc.kill(): trifft die GANZE Prozessgruppe, nicht nur proc selbst
            # (Muster agent_runner._kill(), Phase 65). contextlib.suppress wie dort — ein Prozess,
            # der zwischen Timeout und Kill bereits von selbst beendet ist, ist kein Fehler.
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait()   # Zombie vermeiden — Prozess ist nach dem killpg bereits tot
            return False, "LibreOffice-Konvertierung nach 180 s abgebrochen (Timeout)."
        produced = Path(outdir) / (Path(docx_abs).stem + ".pdf")
        if not (produced.exists() and produced.stat().st_size > 0):
            return False, (f"LibreOffice erzeugte keine PDF. [rc={returncode}] "
                           f"{(stderr or stdout or '').strip()[:200]}")
        Path(pdf_abs).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(produced), pdf_abs)
        return True, None


def to_pdf(docx_path, pdf_path):
    """docx → pdf via LibreOffice headless. Kein Fallback (bewusst — headless-only).
    Rückgabe: (ok: bool, fehler: str|None)."""
    docx_abs = str(Path(docx_path).resolve())
    pdf_abs = str(Path(pdf_path).resolve())
    if os.environ.get("BMS_PDF_UEBER_SERVER"):
        return _pdf_ueber_server(docx_abs, pdf_abs)
    return _to_pdf_soffice(docx_abs, pdf_abs)


def _pdf_ueber_server(docx_abs: str, pdf_abs: str):
    """Unter ChatGPT läuft der Skill in der Sandbox von Codex, dort bricht LibreOffice mit Abort trap ab (rc 134, auf
    macOS geprüft). Der BMS-Server läuft außerhalb der Sandbox und wandelt deshalb um (`POST /api/intern/pdf`)."""
    url = f"http://127.0.0.1:{os.environ.get('PORT') or '8000'}/api/intern/pdf"
    daten = json.dumps({"docx": docx_abs, "pdf": pdf_abs}).encode("utf-8")
    anfrage = urllib.request.Request(url, data=daten, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(anfrage, timeout=240) as antwort:
            ergebnis = json.load(antwort)
    except (OSError, ValueError) as exc:
        return False, f"PDF über den BMS-Server nicht möglich: {exc}"
    return bool(ergebnis.get("ok")), ergebnis.get("fehler")


def _ist_eigener_zielname(stem: str, wunsch: str) -> bool:
    r"""Gehört die vorhandene Datei `stem` zu GENAU dieser CVVersion-Row (Re-Export derselben
    Row, s. Weiche in `export()`)? Erlaubt ist nur der Konventionsname selbst oder sein
    NUMERISCHER Kollisions-Suffix (`…_2`, `…_3` — von `_unique_base()` vergeben).

    Ein reines `stem.startswith(wunsch + "_")` wäre zu weit: es würde auch fremde Dateien
    einsammeln, deren Name zufällig mit dem Wunschnamen beginnt (z. B. eine `…_EN`- oder
    `…_final`-Variante) — die Row würde dann deren Datei überschreiben statt sich einen
    eigenen freien Namen zu holen. Deshalb `fullmatch` gegen `_\d+`, mit `re.escape` auf dem
    Wunschnamen (er enthält Firmen-/Rollentexte, in denen Regex-Sonderzeichen vorkommen)."""
    return stem == wunsch or bool(re.fullmatch(re.escape(wunsch) + r"_\d+", stem))


def _unique_base(directory: Path, base: str) -> str:
    """Basename finden, der weder als .docx noch als .pdf existiert (beide gemeinsam
    nummeriert). Kollision → _2, _3, … — nie überschreiben."""
    cand = base
    i = 2
    while (directory / f"{cand}.docx").exists() or (directory / f"{cand}.pdf").exists():
        cand = f"{base}_{i}"
        i += 1
    return cand


# --- Dokument-Engine (Phase 46 Stufe A): Seitenumbruch-Schutz + Fußzeile ----------------
def _ist_ueberschrift(p) -> bool:
    """Abschnitts-Titel (EXECUTIVE SUMMARY, BERUFSERFAHRUNG, …) — Style „Heading 1“ (gegen die
    echte base_de.docx/base_en.docx-Struktur geprüft, 21.07.2026: alle 9 Rubriken beider
    Sprachvarianten tragen exakt diesen Style, sonst nichts)."""
    return bool(p.style) and p.style.name.startswith("Heading")


def _ist_stationsstart(p) -> bool:
    """Der ANKER einer Berufserfahrungs-/Ausbildungs-Station: eine „Normal“-Zeile mit TAB
    (Muster „<Firma/Institution>\t<Zeitraum>“). Gegen die echte Vorlage geprüft: dieses Muster
    kommt AUSSCHLIESSLICH an Stations-Ankern vor (BERUFSERFAHRUNG + AUSBILDUNG, DE wie EN) —
    Rubriken ohne Stationen (SCHWERPUNKTE, SPRACHEN, …) nutzen „ • “ als Trenner, nie TAB.
    Seit Phase 76 ist der visuelle Stationsbeginn die TITEL-Zeile davor (s. `_stationsgrenzen`);
    der Tab-Detektor hier bleibt unverändert der verlässliche Anker."""
    return bool(p.style) and p.style.name == "Normal" and "\t" in p.text and p.text.strip()


def _ist_stationstitel(p) -> bool:
    """Die Jobtitel-Zeile im v9-Stationsformat (Phase 76): „Normal“-Style, nicht leer, KEIN
    TAB, mindestens ein fetter Run. Gegen die echte v9-Struktur geprüft: direkt vor einer
    Tab-Ankerzeile steht sonst nur ein Heading-1-Abschnittstitel, ein Bullet (List Paragraph) oder
    eine weitere Tab-Zeile (Ausbildung) — kein False-Positive-Kandidat."""
    if not (bool(p.style) and p.style.name == "Normal" and p.text.strip() and "\t" not in p.text):
        return False
    return any(r.bold for r in p.runs)


def _stationsgrenzen(paragraphs) -> list:
    """Start-Indizes aller Stationen: je Tab-Anker (`_ist_stationsstart`) beginnt die Station
    an der Titel-Zeile DAVOR, falls vorhanden (v9-Format, Phase 76), sonst am Anker selbst
    (Alt-Format bis v7; Ausbildungszeilen haben nie einen Titel davor). Ein Index wird nie
    doppelt vergeben — zwei aufeinanderfolgende Tab-Zeilen (AUSBILDUNG) bleiben zwei Stationen."""
    grenzen = []
    for i, p in enumerate(paragraphs):
        if not _ist_stationsstart(p):
            continue
        if i > 0 and _ist_stationstitel(paragraphs[i - 1]) and (i - 1) not in grenzen:
            grenzen.append(i - 1)
        else:
            grenzen.append(i)
    return grenzen


def _seitenumbrueche_schuetzen(doc) -> int:
    """Design-Entscheidung 1: Überschriften nie vom folgenden Absatz trennen; eine Station
    (Stationsgrenze bis zum Absatz vor der nächsten Grenze/Überschrift) als Kette aus
    `keep_with_next` bündeln, zusätzlich `keep_together` je Absatz (schützt auch einen
    einzelnen, mehrzeilig umgebrochenen Bullet vor einem Seitenumbruch mittendrin). Reine
    „keep“-Eigenschaften — Word/LibreOffice übernehmen die tatsächliche Pagination; eine
    Station, die von Natur aus länger als eine Seite ist, fließt normal weiter (kein Fehler,
    keine Endlosschleife — Standard-Word-Verhalten bei nicht erfüllbarem keep_with_next).

    Phase 76: Grenzen über `_stationsgrenzen()` — damit hängt die v9-Titel-Zeile MIT in der
    Kette ihrer Station und die Kette endet VOR dem Titel der Folgestation (sonst klebte der
    fremde Titel am letzten Bullet der Vorgänger-Station). Rückgabe: Anzahl erkannter
    Stationen — 0 bedeutet, dass der Schutz wirkungslos blieb (Vorlage prüfen, s.
    `_nachbearbeiten`).

    P2-47 (25.09.2026): ZUERST alle „keep“-Eigenschaften zurücksetzen, dann neu setzen. Diese
    Funktion ist damit die alleinige Quelle dieser Flags — vorher setzte sie nur und löschte nie,
    und fremde Flags überlebten jeden Lauf. Echtfall: Nach dem zweiten
    `cv-erstellen` trugen 109 statt 87 Absätze `keep_with_next`, darunter der LETZTE Absatz jeder
    Station sowie die Listen „Zertifikate“/„Vorträge“ außerhalb aller Stationen. Damit wurden
    Stationen zu einem unteilbaren Block verkettet, den Word komplett auf die nächste Seite
    schiebt — sichtbar als große Lücke am Seitenende („zu viel auf Seite 2“).
    HERKUNFT der fremden Flags: `_bullet_gruppe_anwenden()` klont für neue Bullets einen
    bestehenden Bullet-Absatz per `copy.deepcopy` — inklusive `pPr`, also inklusive der Flags,
    die ein früherer Lauf dort gesetzt hat (`_bullet_vorlage` liefert den ERSTEN Bullet des
    Dokuments, und der steht mitten in Station 1). Ein Zurücksetzen dort allein würde nicht
    reichen: Auch von Hand gesetzte oder aus einer Vorlage geerbte Flags gehören bereinigt."""
    paragraphs = doc.paragraphs
    n = len(paragraphs)
    for p in paragraphs:
        p.paragraph_format.keep_with_next = None
        p.paragraph_format.keep_together = None
    for p in paragraphs:
        if _ist_ueberschrift(p):
            p.paragraph_format.keep_with_next = True

    grenzen = _stationsgrenzen(paragraphs)
    grenzen_set = set(grenzen)
    for i in grenzen:
        j = i + 1
        while j < n and j not in grenzen_set and not _ist_ueberschrift(paragraphs[j]):
            j += 1
        # Station = paragraphs[i:j] — j ist bereits die nächste Grenze/die nächste Überschrift.
        for k in range(i, j):
            paragraphs[k].paragraph_format.keep_together = True
            if k < j - 1:
                paragraphs[k].paragraph_format.keep_with_next = True
    return len(grenzen)


_FUSSZEILE_PT = Pt(9)   # etwas kleiner als der Body (10,5pt Standard-Vorlagenschrift)


def _add_field(paragraph, instr: str, fallback: str) -> None:
    """Echten Word-Feldcode einfügen (PAGE/NUMPAGES) — Standard-oxml-Rezept: begin/instrText/
    separate/Cache-Fallback-Text/end. `fallback` ist NUR der Anzeige-Cache, bevor Word/
    LibreOffice den Wert neu berechnet — kein echter Wert. Jeder Feld-Run bekommt dieselbe
    Fußzeilen-Schriftgröße wie der umgebende Text (sonst würde ein Feld in Word-Standardgröße
    aus der Zeile herausspringen)."""
    def _fld_char(kind: str):
        el = OxmlElement("w:fldChar")
        el.set(qn("w:fldCharType"), kind)
        return el

    r1 = paragraph.add_run()
    r1._r.append(_fld_char("begin"))

    r2 = paragraph.add_run()
    instr_el = OxmlElement("w:instrText")
    instr_el.set(qn("xml:space"), "preserve")
    instr_el.text = instr
    r2._r.append(instr_el)

    r3 = paragraph.add_run()
    r3._r.append(_fld_char("separate"))

    r4 = paragraph.add_run(fallback)

    r5 = paragraph.add_run()
    r5._r.append(_fld_char("end"))

    for r in (r1, r2, r3, r4, r5):
        r.font.size = _FUSSZEILE_PT


def _fusszeilen_labels(language: Optional[str]) -> tuple:
    """Sprache der CVVersion („DE“, „EN“, „FR“ …) → Fußzeilen-Wörter aus `bewerbungssprache`.
    Tolerant gegen Kleinschreibung und Zusätze („fr“, „en-US“). Fehlt die Sprache ganz (None, leer),
    bleibt es Deutsch (Altbestand). Eine unbekannte Sprache bekommt „x / y“, nicht Deutsch."""
    return bewerbungssprache.fusszeilen_labels(language)


def _fusszeile_setzen(doc, name: str, language: Optional[str] = None) -> None:
    """Design-Entscheidung 1: „<Name> · Seite {PAGE} von {NUMPAGES}“ in ALLEN Sections —
    bestehende Fußzeile wird ERSETZT (nicht ergänzt, sonst nicht idempotent). `is_linked_to_previous`
    explizit False setzen (python-docx-Rezept) — sonst übernimmt Word/LibreOffice bei der ersten
    Section ggf. eine leere Vorlagen-Fußzeile statt der eigenen.

    Die Wörter richten sich nach der CV-Sprache (Vorgabe 23.07.2026): englischer Lebenslauf →
    „Page X of Y“, deutscher → „Seite X von Y“, französischer → „Page X sur Y“ (Tabelle in
    `pipeline.bewerbungssprache`). Nur die Wörter sind sprachabhängig; die PAGE/NUMPAGES-Feldcodes
    bleiben identisch."""
    seite_wort, von_wort = _fusszeilen_labels(language)
    for section in doc.sections:
        footer = section.footer
        footer.is_linked_to_previous = False
        # Bestehenden Inhalt vollständig ersetzen (idempotent — kein Anhängen bei erneutem Export).
        p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        for extra in footer.paragraphs[1:]:
            extra._element.getparent().remove(extra._element)
        for run in list(p.runs):
            run._element.getparent().remove(run._element)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        r_praefix = p.add_run(f"{name} · {seite_wort}")
        r_praefix.font.size = _FUSSZEILE_PT
        _add_field(p, "PAGE", "1")
        r_von = p.add_run(von_wort)
        r_von.font.size = _FUSSZEILE_PT
        _add_field(p, "NUMPAGES", "1")


def _nachbearbeiten(docx_path: Path, language: Optional[str] = None) -> tuple:
    """Öffnet die .docx, wendet Seitenumbruch-Schutz + Fußzeile an, speichert. Fehlertolerant:
    JEDE Exception (ungewöhnliche Vorlage) → übersprungen, Original bleibt unangetastet (nichts
    wird gespeichert, solange nicht ALLE Schritte durchgelaufen sind). Rückgabe:
    `(fehler, warnung)` — fehler None = ok, sonst Kurzgrund für
    `docx_nachbearbeitung: "übersprungen: <grund>"`; warnung (Phase 76) meldet den vormals
    STILLEN Ausfall des Seitenumbruch-Schutzes (0 erkannte Stationen — z. B. eine Vorlage
    ohne die erwarteten Tab-Ankerzeilen), ohne den Export zu blockieren.

    `language` steuert nur die Fußzeilen-Wörter (DE „Seite/von", EN „Page/of", FR, IT, ES, PT)."""
    from pipeline.user_profile import user_name
    try:
        doc = Document(str(docx_path))
        name = user_name()
        stationen = _seitenumbrueche_schuetzen(doc)
        _fusszeile_setzen(doc, name, language)
        doc.save(str(docx_path))
        warnung = None
        if stationen == 0:
            warnung = "0 Stationen erkannt — Seitenumbruch-Schutz wirkungslos, Vorlage prüfen"
        return None, warnung
    except Exception as e:  # noqa: BLE001 — bewusst breit, s. Docstring
        return f"{type(e).__name__}: {str(e)[:150]}", None


# --- P2-9: Anschreiben-Sprache aus dem TATSÄCHLICHEN Text ableiten -------------------------
# Die Grußformeln aller Sprachen stehen in `pipeline.bewerbungssprache` (eine Quelle, vorher je
# eine EN-Kopie hier und in `cover_letter_render`).
def _sprache_aus_text(app: Application, docx_path: Path) -> str:
    """Anschreiben-Sprache aus dem TATSÄCHLICHEN Text ableiten (P2-9-Fix) — wird nur erreicht,
    wenn weder ein expliziter Parameter noch `cover_letter_language` gesetzt sind (Aufrufer
    nutzt Kurzschluss-`or`, s. `export_cover_letter`).

    Bevorzugt `Application.cover_letter_text` (DB-Feld, exakt der Text, den
    `cover_letter_render.render_cover_letter` gerendert hat — keine Datei-I/O nötig). Ohne dieses
    Feld (z. B. Altbestand ohne Phase-48-Text) wird der Absatztext der tatsächlichen .docx
    gelesen. Sucht darin zeilenweise die Schluss-Grußformel aller Sprachen aus
    `pipeline.bewerbungssprache` (DE, EN, FR, IT, ES, PT; dieselbe Liste wie
    `cover_letter_render._GRUSSFORMEL`, nur noch an einem Ort); kein Treffer → Default „DE“ —
    unverändert ggü. dem bisherigen Systemverhalten, das Deutsch als Normalfall behandelt.
    Best effort: JEDE Exception beim Datei-Lesen (kaputte/fehlende .docx) fällt ebenfalls auf „DE“
    zurück statt `export_cover_letter` abzubrechen."""
    text = app.cover_letter_text
    if not text:
        try:
            text = "\n\n".join(p.text for p in Document(str(docx_path)).paragraphs if p.text.strip())
        except Exception:  # noqa: BLE001 — Erkennung ist best effort, darf export() nie brechen
            return "DE"
    return bewerbungssprache.sprache_aus_grussformel(text) or "DE"


# --- P2-10: alte PDF aufräumen, wenn sich der Zieldateiname ändert ------------------------
def _noch_referenziert(session: Session, pfad: Optional[str], ausser: tuple) -> bool:
    """True, wenn `pfad` (projekt-root-relativ) laut `cleanup._alle_referenzen` — der EINEN
    kanonischen Referenz-Sammlung über alle Pfadfelder im System, s. dort — noch von einer
    ANDEREN Zeile als `ausser` (modell, id) gehalten wird.

    Sicherheitsnetz für P2-10: bevor eine alte PDF in den Papierkorb wandert, ausschließen, dass
    sie (z. B. durch eine Dublette oder eine manuelle DB-Änderung) noch aktiv referenziert ist.
    `ausser` schließt die eigene, gerade bearbeitete Zeile aus — ihr ALTER Pfad wurde von
    `export()`/`export_cover_letter()` bereits (in-memory) durch den neuen ersetzt und zählt
    hier deshalb nicht als Fremdreferenz. Lazy Import von `cleanup` (Muster wie
    `cleanup.leeren()` selbst mit `pipeline.search_index` verfährt) — vermeidet einen
    Modulebene-Import zwischen zwei gleichrangigen `pipeline/*.py`-Modulen."""
    if not pfad:
        return False
    from pipeline import cleanup

    ziel = cleanup._norm(pfad)
    return any(p == ziel and (m, i) != ausser for (m, i, _, p) in cleanup._alle_referenzen(session))


def export(cv_version_id) -> dict:
    """CVVersion nach Konvention umbenennen (.docx) + PDF erzeugen. Eigene DB-Session.

    Rückgabe: {"cv_version_id", "docx", "pdf"|None, "pdf_fehler"|None}
    PDF-Fehlschlag ist NICHT fatal: pdf_path bleibt None, die docx-Registrierung gilt weiter.
    """
    init_db()
    with Session(engine) as s:
        cv = s.get(CVVersion, cv_version_id)
        if not cv:
            raise SystemExit(f"CVVersion {cv_version_id} nicht gefunden")
        if not cv.file_path:
            raise SystemExit(f"CVVersion {cv_version_id} hat kein file_path")
        job = s.get(Job, cv.job_id) if cv.job_id else None
        if not job:
            raise SystemExit(f"Job zu CVVersion {cv_version_id} nicht gefunden")

        company = job.company_name
        if not company and job.company_id:
            comp = s.get(Company, job.company_id)
            company = comp.name if comp else None
        position = job.title or ""

        src = _im_ordner(cv.file_path, _CV_QUELLEN, ".docx")
        if src is None:
            raise SystemExit(f"Entwurf liegt nicht in einem CV-Ordner "
                             f"({', '.join(_CV_QUELLEN)}): {cv.file_path}")
        if not src.exists():
            raise SystemExit(f"Quelldatei fehlt: {cv.file_path}")

        tailored_dir = PROJECT_ROOT / "outputs" / "cv"
        tailored_dir.mkdir(parents=True, exist_ok=True)

        wunsch = naming.cv_filename(company, position, cv.language)
        # Re-Export DERSELBEN Row (Phase 55 Feedback-Schleife / „CV erneut erstellen"): liegt
        # die Quelldatei bereits unter ihrem Konventionsnamen (ggf. nummeriert) im Zielordner,
        # denselben Basename BEHALTEN und die eigenen Dateien überschreiben. Ohne diese Weiche
        # kollidierte der zweite export()-Lauf mit sich selbst: die eigene .docx wurde zu
        # `_2.docx` umbenannt, das erste PDF blieb als Waise (Befund 24.07.2026 — mehrere reale
        # Fälle). _unique_base bleibt für ECHTE Kollisionen (ANDERE Row,
        # z. B. zweite CVVersion desselben Jobs — ein weiterer echter Fall vom 23.07.) unverändert zuständig.
        # P2-63: Eine Datei derselben Stelle nach der FRÜHEREN (ungekürzten) Konvention fällt hier
        # bewusst in den else-Zweig: der neue Name ist frei, `_unique_base` vergibt ihn, die .docx
        # wird umbenannt und die alte PDF räumt der Papierkorb-Schritt unten ab (Zielname geändert).
        # Es entsteht kein Waise und kein `_2` (Test: test_p2_63_leser.py).
        if src.parent == tailored_dir and _ist_eigener_zielname(src.stem, wunsch):
            base = src.stem
        else:
            base = _unique_base(tailored_dir, wunsch)
        docx_target = tailored_dir / f"{base}.docx"
        pdf_target = tailored_dir / f"{base}.pdf"

        # (3) Umbenennen auf Zielnamen (nie überschreiben — _unique_base garantiert freien Namen).
        if src != docx_target:
            shutil.move(str(src), str(docx_target))
        cv.file_path = _rel(docx_target)

        # (3b) Dokument-Engine (Phase 46 Stufe A): Seitenumbruch-Schutz + Fußzeile, VOR der
        # PDF-Konvertierung, damit .docx UND PDF profitieren. Fehlschlag ist NICHT fatal.
        nachbearbeitung_fehler, struktur_warnung = _nachbearbeiten(docx_target, cv.language)

        # (4) PDF erzeugen — Fehlschlag nicht fatal.
        alte_pdf = cv.pdf_path                # P2-10: vor dem Zurücksetzen merken
        cv.pdf_path = None
        ok, err = to_pdf(docx_target, pdf_target)
        out = {"cv_version_id": cv.id, "docx": cv.file_path, "pdf": None, "pdf_fehler": None,
              "docx_nachbearbeitung": f"übersprungen: {nachbearbeitung_fehler}" if nachbearbeitung_fehler else "ok"}
        if struktur_warnung:
            # Phase 76: der vormals stille Ausfall des Umbruch-Schutzes wird sichtbar gemeldet.
            out["struktur_warnung"] = struktur_warnung
        if ok:
            cv.pdf_path = _rel(pdf_target)
            out["pdf"] = cv.pdf_path
        else:
            out["pdf_fehler"] = err

        # P2-10: hat sich der Zieldateiname geändert (Titel-/Firmenkorrektur), bleibt die alte
        # PDF sonst unreferenziert mit veraltetem Inhalt liegen — der Nutzer könnte sie versehentlich
        # verschicken. In den Papierkorb verschieben (Hausmuster, NIE hart löschen), aber nur,
        # wenn sie tatsächlich umbenannt wurde (gleicher Pfad = reines Überschreiben, nichts zu
        # tun) UND nirgends mehr referenziert ist (_noch_referenziert — Sicherheitsnetz gegen
        # eine Dublette/manuelle DB-Änderung, die denselben Pfad noch aktiv braucht).
        # P2-56: nur eine alte PDF aus outputs/cv; ein Altwert, der woandershin zeigt, bleibt liegen.
        neuer_pdf_pfad = _rel(pdf_target)     # geplanter Zielpfad, unabhängig vom Erfolg von to_pdf()
        if (alte_pdf and alte_pdf != neuer_pdf_pfad
                and _im_ordner(alte_pdf, ("outputs/cv",), ".pdf") is not None
                and not _noch_referenziert(s, alte_pdf, ("CVVersion", cv.id))):
            from pipeline import cleanup
            cleanup._in_papierkorb(alte_pdf)

        s.add(cv)
        s.commit()
        return out


# --- Editier-Checkpoint (Phase 46 Stufe B, Design-Entscheidung 4) --------------------------
def entwurf_extrahieren(docx_path) -> list:
    """`.docx` → geordnete Absatz-Liste `[{i, style, text, ist_bullet}]` (leere Absätze
    übersprungen). `i` = Index in `doc.paragraphs`.
    `ist_bullet` (Phase 48 Stufe B, additiv): Style „List Paragraph“ — echte Bullets in
    `base_de.docx`/`base_en.docx` (verifiziert: 64/64 Absätze mit diesem Style tragen dieselbe
    `numPr`-Formatierung). Fixed-Einträge (Heading/Normal) bleiben index-stabil wie v1 —
    `entwurf_zurueckschreiben()` schreibt NUR Bullet-Gruppen frei um, alles andere in-place
    (s. dort). Bestehende Konsumenten, die `ist_bullet` ignorieren, funktionieren unverändert."""
    doc = Document(str(docx_path))
    out = []
    for i, p in enumerate(doc.paragraphs):
        if not p.text.strip():
            continue
        style_name = p.style.name if p.style else "Normal"
        out.append({"i": i, "style": style_name, "text": p.text, "ist_bullet": style_name == "List Paragraph"})
    return out


def _text_ersetzen(paragraph, neuer_text: str) -> None:
    """Ersetzt den GESAMTEN sichtbaren Text eines Absatzes, OHNE Styling/Struktur zu ändern:
    der Text landet im ERSTEN Run (dessen Formatierung — z. B. Fett bei Rollentiteln — erhalten
    bleibt), alle weiteren Runs werden geleert (nicht gelöscht — Löschen/Neuanlage von Runs kann
    rPr-Reste zerstören, ein leerer Run ist unschädlich).
    ⚠️ Hat ein Absatz MEHRERE Runs mit UNTERSCHIEDLICHER Formatierung (z. B. „<Firma>" fett +
    „<Zeitraum>" nicht-fett in derselben Zeile — real in base_de/en.docx so vorhanden), geht bei
    einer Bearbeitung dieser Zeile die interne Fett-Aufteilung verloren (der ganze Text bekommt
    die Formatierung von Run 1). Bewusster v1-Kompromiss: passiert NUR, wenn der Nutzer genau diese
    Zeile aktiv editiert — unveränderte Absätze bleiben (s. `entwurf_zurueckschreiben`) komplett
    unangetastet. Die betroffenen Zeilen (Firma/Zeitraum-Kopf, „Label: "-Zeilen) sind ohnehin
    Fakten statt getailorter Wortwahl — ein größerer Rich-Text-Editor wäre der nächste Schritt,
    falls der Nutzer genau das braucht (s. Veto-Punkt in der Spec)."""
    runs = paragraph.runs
    if not runs:
        paragraph.add_run(neuer_text)
        return
    runs[0].text = neuer_text
    for r in runs[1:]:
        r.text = ""


def _bullet_vorlage(doc):
    """Erster Absatz mit Style „List Paragraph“ im Dokument — Klon-Referenz fürs Einfügen neuer
    Bullets. KEIN Hardcoding von numId/abstractNumId: `base_de.docx` und `base_en.docx` haben
    ihre numId→abstractNumId-Zuordnung vertauscht, aber alle 64 Bullet-Absätze JE Datei teilen
    exakt dieselbe pPr/numPr-XML (verifiziert per Skript, 22.07.2026, ein MD5-Hash je Datei) —
    ein beliebiger bestehender Bullet-Absatz DERSELBEN Datei ist daher ein sicheres Vorbild."""
    for p in doc.paragraphs:
        if p.style and p.style.name == "List Paragraph":
            return p
    return None


def _bullet_gruppe_anwenden(anchor_p, vorlage_p, bullet_texte: list) -> None:
    """Ersetzt ALLE unmittelbar auf `anchor_p` folgenden Bullet-Absätze (Style „List Paragraph“)
    durch `len(bullet_texte)` neu geklonte Absätze (Vorbild `vorlage_p`, `copy.deepcopy` des
    kompletten `<w:p>`-Elements inkl. `pPr`/`numPr` — reiner Style-Name reicht NICHT, das
    Bullet-Zeichen kommt aus `numPr`, s. `_bullet_vorlage`). Reihenfolge: erst die neuen Absätze
    direkt hinter dem Anker einfügen, DANACH die alten entfernen — an keinem Punkt eine Lücke.
    Text wird wie bei `_text_ersetzen` nur im ersten Run gesetzt (dieselbe Formatierungs-
    Einschränkung wie beim In-Place-Edit, s. dort — bewusst konsistent, kein Sonderfall)."""
    p_tag = qn("w:p")
    alte = []
    el = anchor_p._p.getnext()
    while el is not None and el.tag == p_tag:
        kandidat = Paragraph(el, anchor_p._parent)
        if not (kandidat.style and kandidat.style.name == "List Paragraph"):
            break
        alte.append(el)
        el = el.getnext()

    ref = anchor_p._p
    for text in bullet_texte:
        neu_element = copy.deepcopy(vorlage_p._p)
        neuer_absatz = Paragraph(neu_element, anchor_p._parent)
        _text_ersetzen(neuer_absatz, text)
        ref.addnext(neu_element)
        ref = neu_element

    for el in alte:
        el.getparent().remove(el)


def entwurf_zurueckschreiben(docx_path, entwurf_text: list) -> int:
    """Schreibt den editierten Entwurf zurück — zwei Eintrags-Arten (Phase 48 Stufe B):
    - Fixed `{i, text}` (Heading/Normal, wie v1): an den ORIGINAL-Absatz-Index zurückschreiben,
      NUR in-place, nie hinzufügen/entfernen. Ein nicht mehr gültiger Index wird übersprungen
      statt zu crashen.
    - Bullet-Gruppe `{anchor_i, bullet_texte}`: die Bullet-Absätze DIREKT NACH dem Fixed-Absatz
      `anchor_i` werden komplett neu aufgebaut (`_bullet_gruppe_anwenden`) — der Nutzer darf hier
      Zeilen ändern, hinzufügen UND entfernen. Gruppen werden ABSTEIGEND nach `anchor_i`
      verarbeitet, damit die (index-basierten) Anker der noch nicht verarbeiteten Gruppen gültig
      bleiben — die Fixed-Absätze selbst werden nie verschoben/gelöscht, ihre Indizes aus dem
      EINMAL zu Beginn geladenen `doc.paragraphs` bleiben deshalb während der ganzen Funktion
      korrekt referenzierbar, unabhängig davon, wie viele Bullets an anderer Stelle eingefügt/
      entfernt werden.
    Rückgabe: Anzahl tatsächlich geänderter Fixed-Absätze + verarbeiteter Bullet-Gruppen."""
    doc = Document(str(docx_path))
    paragraphs = doc.paragraphs
    geaendert = 0

    for eintrag in entwurf_text:
        if "anchor_i" in eintrag:
            continue
        i = eintrag.get("i")
        neuer_text = eintrag.get("text", "")
        if i is None or i < 0 or i >= len(paragraphs):
            continue
        p = paragraphs[i]
        if p.text == neuer_text:
            continue
        _text_ersetzen(p, neuer_text)
        geaendert += 1

    gruppen = sorted((e for e in entwurf_text if "anchor_i" in e),
                      key=lambda g: g["anchor_i"], reverse=True)
    if gruppen:
        vorlage = _bullet_vorlage(doc)
        for gruppe in gruppen:
            i = gruppe.get("anchor_i")
            if i is None or i < 0 or i >= len(paragraphs):
                continue
            texte = [t for t in gruppe.get("bullet_texte", []) if t.strip()]
            if vorlage is None and texte:
                continue  # keine Bullet-Vorlage im Dokument -> kann nicht sicher geklont werden
            _bullet_gruppe_anwenden(paragraphs[i], vorlage, texte)
            geaendert += 1

    if geaendert:
        doc.save(str(docx_path))
    return geaendert


def entwurf_anwenden(cv_version_id) -> dict:
    """cv-erstellen Schritt 1 (VOR `export()`): den in der DB gespeicherten (ggf. editierten)
    Entwurf aus `CVVersion.entwurf_text` in die noch unbenannte Entwurfs-`.docx` zurückschreiben.
    Eigene Session (Muster `export()`)."""
    init_db()
    with Session(engine) as s:
        cv = s.get(CVVersion, cv_version_id)
        if not cv:
            raise SystemExit(f"CVVersion {cv_version_id} nicht gefunden")
        if not cv.file_path:
            raise SystemExit(f"CVVersion {cv_version_id} hat kein file_path")
        if not cv.entwurf_text:
            return {"cv_version_id": cv.id, "geaendert": 0, "hinweis": "kein Entwurf-Text vorhanden"}
        docx_path = _im_ordner(cv.file_path, _CV_QUELLEN, ".docx")
        if docx_path is None:
            raise SystemExit(f"Entwurf liegt nicht in einem CV-Ordner "
                             f"({', '.join(_CV_QUELLEN)}): {cv.file_path}")
        if not docx_path.exists():
            raise SystemExit(f"Entwurfsdatei fehlt: {cv.file_path}")
        eintraege = json.loads(cv.entwurf_text)
        geaendert = entwurf_zurueckschreiben(docx_path, eintraege)
        return {"cv_version_id": cv.id, "geaendert": geaendert}


def export_cover_letter(application_id, language=None) -> dict:
    """Anschreiben nach Konvention umbenennen (.docx) + PDF erzeugen — Spiegel von export().

    Rückgabe: {"application_id", "docx", "pdf"|None, "pdf_fehler"|None}
    PDF-Fehlschlag ist NICHT fatal: cover_letter_pdf_path bleibt None, die docx-Registrierung gilt weiter.
    """
    init_db()
    with Session(engine) as s:
        app = s.get(Application, application_id)
        if not app:
            raise SystemExit(f"Application {application_id} nicht gefunden")
        if not app.cover_letter_path:
            raise SystemExit(f"Application {application_id} hat kein cover_letter_path")
        job = s.get(Job, app.job_id) if app.job_id else None
        if not job:
            raise SystemExit(f"Job zu Application {application_id} nicht gefunden")

        company = job.company_name
        if not company and job.company_id:
            comp = s.get(Company, job.company_id)
            company = comp.name if comp else None
        position = job.title or ""

        src = _im_ordner(app.cover_letter_path, _ANSCHREIBEN_QUELLEN, ".docx")
        if src is None:
            raise SystemExit(f"Anschreiben liegt nicht in einem Anschreiben-Ordner "
                             f"({', '.join(_ANSCHREIBEN_QUELLEN)}): {app.cover_letter_path}")
        if not src.exists():
            raise SystemExit(f"Quelldatei fehlt: {app.cover_letter_path}")

        # Sprache: Parameter > gespeichert > aus dem TATSÄCHLICHEN Text abgeleitet (P2-9-Fix) >
        # DE. Die frühere Heuristik prüfte stattdessen den Namen der Zwischendatei
        # (`_raw_<id>.docx`, von `cover_letter_render` unmittelbar VOR diesem Aufruf gesetzt) —
        # die kann strukturell NIE „_EN" enthalten, ein englisches Anschreiben fiel deshalb immer
        # auf „DE" zurück (Datei UND DB dauerhaft falsch beschriftet). `_sprache_aus_text` liest
        # stattdessen den echten Inhalt (DB-Textfeld oder .docx). `src` muss deshalb VOR `lang`
        # berechnet werden (Reihenfolge verifiziert: `app.cover_letter_path` zeigt an dieser
        # Stelle noch auf die Quelldatei, die Umbenennung passiert erst weiter unten).
        lang = (language or app.cover_letter_language or _sprache_aus_text(app, src)).upper()

        cover_dir = PROJECT_ROOT / "outputs" / "anschreiben"
        cover_dir.mkdir(parents=True, exist_ok=True)

        # Gleiche Re-Export-Weiche wie in export() (s. dort): eigener Konventionsname → behalten
        # und überschreiben, sonst erzeugt jede Anschreiben-Regeneration ein _2-Waisenpaar.
        wunsch = naming.cover_letter_filename(company, position, lang)
        # P2-63: Altname derselben Stelle (ungekürzt) → else-Zweig, `_unique_base` vergibt den freien
        # neuen Namen, die alte PDF räumt der Schritt unten ab.
        if src.parent == cover_dir and (src.stem == wunsch or src.stem.startswith(wunsch + "_")):
            base = src.stem
        else:
            base = _unique_base(cover_dir, wunsch)
        docx_target = cover_dir / f"{base}.docx"
        pdf_target = cover_dir / f"{base}.pdf"

        if src != docx_target:
            shutil.move(str(src), str(docx_target))
        app.cover_letter_path = _rel(docx_target)
        app.cover_letter_language = lang

        alte_pdf = app.cover_letter_pdf_path   # P2-10: vor dem Zurücksetzen merken
        app.cover_letter_pdf_path = None
        ok, err = to_pdf(docx_target, pdf_target)
        out = {"application_id": app.id, "docx": app.cover_letter_path, "pdf": None, "pdf_fehler": None}
        if ok:
            app.cover_letter_pdf_path = _rel(pdf_target)
            out["pdf"] = app.cover_letter_pdf_path
        else:
            out["pdf_fehler"] = err

        # P2-10: alte PDF aufräumen, wenn der Zieldateiname sich geändert hat (s. export()
        # für die ausführliche Begründung — identisches Vorgehen, Spiegel-Logik wie der Rest
        # dieser Funktion).
        neuer_pdf_pfad = _rel(pdf_target)
        if (alte_pdf and alte_pdf != neuer_pdf_pfad
                and _im_ordner(alte_pdf, ("outputs/anschreiben",), ".pdf") is not None   # P2-56
                and not _noch_referenziert(s, alte_pdf, ("Application", app.id))):
            from pipeline import cleanup
            cleanup._in_papierkorb(alte_pdf)

        s.add(app)
        s.commit()
        return out


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "cover":
        import argparse
        ap = argparse.ArgumentParser(prog="pipeline.cv_export cover")
        ap.add_argument("application_id", type=int)
        ap.add_argument("--language", choices=list(bewerbungssprache.CODES), default=None)
        a = ap.parse_args(args[1:])
        result = export_cover_letter(a.application_id, a.language)
    elif args and args[0] == "entwurf-schreiben":
        if len(args) < 2:
            sys.exit("Nutzung: python -m pipeline.cv_export entwurf-schreiben <cv_version_id>")
        result = entwurf_anwenden(int(args[1]))
    elif args:
        result = export(int(args[0]))
    else:
        sys.exit("Nutzung: python -m pipeline.cv_export <cv_version_id>  |  "
                 "cover <application_id> [--language DE|EN|FR|IT|ES|PT]  |  "
                 "entwurf-schreiben <cv_version_id>")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("pdf_fehler"):
        print(f"\nHinweis: PDF nicht erzeugt — {result['pdf_fehler']}", file=sys.stderr)
