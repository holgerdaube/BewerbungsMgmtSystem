#!/usr/bin/env python3
"""LinkedIn-Datenexport-ZIP → Profil-Tabellen (Phase 45 Stufe C, Design-Entscheidung 4a).

Robuster Primärweg — Gegenstück zum best-effort URL-Button (`profil-einlesen`-Skill), der an
LinkedIns Login-Wall scheitert (dasselbe Problem wie in jobsuche/mail-jobsuche dokumentiert).
LinkedIn → Einstellungen → „Get a copy of your data" liefert ein ZIP mit u. a. `Profile.csv`,
`Positions.csv`, `Skills.csv`, `Certifications.csv`, `Education.csv`. Deterministisch: stdlib
`zipfile`+`csv`, KEIN LLM, KEIN Netzzugriff.

ADDITIV + zerstörungsfrei (Design-Entscheidung 4, gilt für BEIDE LinkedIn-Wege):
- `Profile`-Felder (headline/standort/positionierung) werden NUR gefüllt, wenn sie leer sind.
- Skills/Werdegang-Einträge werden nur angelegt, wenn noch KEIN inhaltsgleicher Eintrag
  existiert (einfache Dedup nach Name bzw. Art+Firma+Rolle+Zeitraum, unabhängig von `quelle`) —
  ein zweiter Import desselben Exports erzeugt keine Duplikate, und manuell gepflegte Einträge
  werden nie verändert oder gelöscht. Die Dedup ist bewusst simpel (exakter, case-insensitiver
  Textvergleich) — leicht abweichend formatierte Duplikate (z. B. "2020" vs. "Jan 2020") sichtet
  der Nutzer von Hand (Human-in-the-Loop, s. Spec).

Fehlt eine der fünf Dateien im ZIP (z. B. weil der Nutzer nur einen Teilexport gewählt hat) oder hat
LinkedIn eine Spalte umbenannt: wird sie/die Spalte still übersprungen — kein Crash, kein
Pflicht-Fünferpack, keine geratenen Werte.
"""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import date, datetime

from sqlmodel import Session, select

from app.models import CareerEntry, Profile, ProfileSkill


class LinkedinImportError(Exception):
    pass


# P2-16 (Code-Review 2026-07-25): der ZIP-Import-Endpunkt (app/main.py::profil_import_zip) prüft
# nur die KOMPRIMIERTE Upload-Größe (_MAX_UPLOAD, 25 MB) — eine einzelne Entry mit hoher
# Kompressionsrate bleibt darunter und konnte bisher unbegrenzt entpacken (`list(csv.DictReader(
# …))` liest bis EOF, egal wie groß). Ein LinkedIn-Datenexport ist Freitext EINER Person —
# Skills/Positions/Education/Certifications bleiben selbst bei sehr aktiven Profilen im KB- bis
# niedrigen MB-Bereich. 20 MB je Datei ist großzügiger Puffer (>100x realistischer Größen) und
# trotzdem klein genug, dass eine böswillige oder beschädigte Entry den Server-Prozess nicht in
# die Knie zwingt.
_MAX_ENTRY_UNCOMPRESSED = 20 * 1024 * 1024


def _lese_csv(zf: zipfile.ZipFile, dateiname: str) -> list[dict]:
    """Case-insensitive Namenssuche (LinkedIn-Exporte liegen mal im Root, mal in einem
    Unterordner) — erste passende Datei gewinnt. Fehlt sie: leere Liste (kein Crash).

    P2-16: zwei unabhängige Sperren gegen eine Zip-Bombe, statt nur einer.
    (1) `ZipInfo.file_size` (deklarierte unkomprimierte Größe, Zentralverzeichnis) VORAB prüfen —
        günstig, verwirft den Normalfall (ehrlich riesige Datei), ohne die Entry überhaupt zu
        entpacken.
    (2) `read(_MAX_ENTRY_UNCOMPRESSED + 1)` als harte Grenze BEIM Lesen: ein einzelner
        `ZipExtFile.read(n)`-Aufruf mit explizitem `n` dekomprimiert nachweislich nur so viele
        Bytes, wie angefordert, unabhängig von der Gesamtgröße der Entry (empirisch geprüft,
        Report Phase 67E: `read(1024)` gegen eine ehrliche 60-MB-Entry lieferte exakt 1024 Bytes
        in <0,01 s) — das fängt auch eine Entry ab, deren deklarierte Größe von der beim Lesen
        tatsächlich anfallenden abweicht, ohne dass Sperre (1) sich allein auf die Metadaten
        verlassen muss."""
    treffer = next((n for n in zf.namelist()
                    if n.lower() == dateiname.lower() or n.lower().endswith("/" + dateiname.lower())),
                   None)
    if not treffer:
        return []
    info = zf.getinfo(treffer)
    if info.file_size > _MAX_ENTRY_UNCOMPRESSED:
        raise LinkedinImportError(
            f"{dateiname} zu groß entpackt ({info.file_size // 1024 // 1024} MB, Limit "
            f"{_MAX_ENTRY_UNCOMPRESSED // 1024 // 1024} MB) — kein realistischer LinkedIn-Export")
    with zf.open(treffer) as f:
        roh = f.read(_MAX_ENTRY_UNCOMPRESSED + 1)
    if len(roh) > _MAX_ENTRY_UNCOMPRESSED:
        raise LinkedinImportError(
            f"{dateiname} entpackt auf mehr als {_MAX_ENTRY_UNCOMPRESSED // 1024 // 1024} MB — "
            "Lesen abgebrochen (kein realistischer LinkedIn-Export)")
    text = io.TextIOWrapper(io.BytesIO(roh), encoding="utf-8-sig", errors="replace")
    return list(csv.DictReader(text))


def _get(row: dict, *keys: str) -> str:
    """Erste vorhandene, nicht-leere Spalte (Groß/Klein-tolerant — LinkedIn ändert
    Schreibweisen gelegentlich zwischen Export-Versionen)."""
    lower = {k.lower(): v for k, v in row.items()}
    for k in keys:
        v = (lower.get(k.lower()) or "").strip()
        if v:
            return v
    return ""


def _career_key(art: str, firma: str | None, rolle: str | None, von: str | None, bis: str | None) -> tuple:
    return (art, (firma or "").strip().lower(), (rolle or "").strip().lower(),
           (von or "").strip().lower(), (bis or "").strip().lower())


def _additiv_schreiben(session: Session, felder: dict, skills: list[str], eintraege: list[dict]) -> dict:
    """Gemeinsamer Kern von ZIP-Import und Textvorschlag: `felder` (headline, standort, positionierung) nur,
    wenn sie leer sind; `skills` und `eintraege` (art, firma, rolle, von, bis, weitere Felder von CareerEntry)
    nur, wenn es sie noch nicht gibt. Liefert die Bericht-Zusammenfassung fürs UI-Feedback."""
    profile = session.get(Profile, 1)
    if not profile:
        profile = Profile(id=1)
        session.add(profile)
        session.flush()

    profil_aktualisiert: list[str] = []
    for feld in ("headline", "standort", "positionierung"):
        wert = felder.get(feld)
        if wert and not getattr(profile, feld):
            setattr(profile, feld, wert)
            profil_aktualisiert.append(feld)

    bestehende_skills = {s.name.strip().lower() for s in session.exec(select(ProfileSkill)).all()}
    skills_neu = 0
    for name in skills:
        if not name or name.strip().lower() in bestehende_skills:
            continue
        # Weder der Export noch der Textvorschlag liefern eine Kategorie — Sammelbereich, der Nutzer sortiert
        # per PATCH /api/profil/skills/{id} bei Bedarf in einen passenden Bereich um.
        session.add(ProfileSkill(name=name, bereich="LinkedIn (unsortiert)", quelle="linkedin"))
        bestehende_skills.add(name.strip().lower())
        skills_neu += 1

    bestehende_career = {
        _career_key(c.art, c.firma, c.rolle, c.von, c.bis)
        for c in session.exec(select(CareerEntry)).all()
    }
    werdegang_neu = 0
    for e in eintraege:
        art, firma, rolle, von, bis = (e.get(k) or "" for k in ("art", "firma", "rolle", "von", "bis"))
        key = _career_key(art, firma, rolle, von, bis)
        if key in bestehende_career:
            continue
        rest = {k: v or None for k, v in e.items() if k not in ("art", "firma", "rolle", "von", "bis")}
        session.add(CareerEntry(art=art, firma=firma or None, rolle=rolle or None,
                                von=von or None, bis=bis or None, quelle="linkedin", **rest))
        bestehende_career.add(key)
        werdegang_neu += 1

    if profil_aktualisiert or skills_neu or werdegang_neu:
        profile.linkedin_eingelesen_am = date.today().isoformat()
        profile.updated_at = datetime.utcnow()
        session.add(profile)
    session.commit()
    session.refresh(profile)

    return {
        "profil_aktualisiert": profil_aktualisiert,
        "skills_neu": skills_neu,
        "werdegang_neu": werdegang_neu,
        "linkedin_eingelesen_am": profile.linkedin_eingelesen_am,
    }


def importiere_zip(inhalt: bytes, session: Session) -> dict:
    """Kern der Stufe C — nimmt die rohen ZIP-Bytes (vom Upload-Endpunkt gelesen) entgegen,
    schreibt additiv in Profile/ProfileSkill/CareerEntry, liefert eine Bericht-Zusammenfassung
    (auch fürs UI-Feedback nach dem Upload)."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(inhalt))
    except zipfile.BadZipFile:
        raise LinkedinImportError("Datei ist kein gültiges ZIP-Archiv")

    felder: dict = {}
    profil_rows = _lese_csv(zf, "Profile.csv")
    if profil_rows:
        p = profil_rows[0]
        felder = {"headline": _get(p, "Headline"), "standort": _get(p, "Geo Location", "Location", "Zip Code"),
                  "positionierung": _get(p, "Summary")}

    skills = [_get(row, "Name") for row in _lese_csv(zf, "Skills.csv")]

    eintraege: list[dict] = []
    for row in _lese_csv(zf, "Positions.csv"):
        eintraege.append({"art": "Beruf", "firma": _get(row, "Company Name", "Company"), "rolle": _get(row, "Title"),
                          "von": _get(row, "Started On", "Start Date"), "bis": _get(row, "Finished On", "End Date"),
                          "beschreibung": _get(row, "Description")})

    for row in _lese_csv(zf, "Education.csv"):
        rolle = " ".join(x for x in (_get(row, "Degree Name"), _get(row, "Field Of Study")) if x)
        eintraege.append({"art": "Ausbildung", "firma": _get(row, "School Name", "School"), "rolle": rolle,
                          "von": _get(row, "Start Date"), "bis": _get(row, "End Date"),
                          "beschreibung": _get(row, "Notes", "Activities")})

    for row in _lese_csv(zf, "Certifications.csv"):
        lizenz = _get(row, "License Number")
        authority = _get(row, "Authority")
        eintraege.append({"art": "Zertifizierung", "firma": authority, "rolle": _get(row, "Name"),
                          "von": _get(row, "Started On", "Start Date"), "bis": _get(row, "Finished On", "End Date"),
                          "referenzgeber": authority, "notiz": f"Lizenznummer: {lizenz}" if lizenz else ""})

    return _additiv_schreiben(session, felder, skills, eintraege)
