"""LinkedIn-Profil aus eingefügtem Text oder PDF: zwischengespeicherte Eingabe, Prüfung des KI-Vorschlags, Vorschau.

Ablauf: Die Eingabe landet in `data/tmp/`, der Lauf `profil-einlesen` holt sie über die lokale API und schickt
einen strukturierten Vorschlag zurück. Gespeichert wird erst, wenn der Nutzer ihn in der Vorschau übernimmt, und
dann additiv wie beim ZIP-Import (`linkedin_import._additiv_schreiben`). Ein automatischer Abruf der Profil-URL
scheidet aus: LinkedIn sperrt ihn (HTTP 999), und der Nutzervertrag untersagt Skripte und Plug-ins dafür.
"""
from __future__ import annotations

import io
import json

from sqlmodel import Session, select

from app.models import CareerEntry, Profile, ProfileSkill
from pipeline import linkedin_import

MAX_TEXT = 60_000
_MAX_SKILLS = 200
_MAX_EINTRAEGE = 100
_MAX_EINZEILIG = 300
_MAX_FREITEXT = 5000
_ARTEN = ("Beruf", "Ausbildung", "Zertifizierung", "Projekt", "Sonstiges")
_EINZEILIG = ("firma", "rolle", "von", "bis")
FELDER = {"headline": "Headline", "standort": "Standort", "positionierung": "Positionierung"}


class EingabeFehler(ValueError):
    """Meldung für den Nutzer oder den KI-Lauf, ohne technischen Ballast."""


def _ordner():
    from app.db import DATA_DIR
    return DATA_DIR / "tmp"


def _eingabe_pfad():
    return _ordner() / "linkedin_eingabe.txt"


def _vorschlag_pfad():
    return _ordner() / "linkedin_vorschlag.json"


def pdf_zu_text(inhalt: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise EingabeFehler("Der Baustein für PDF-Dateien fehlt. Bitte die Python-Umgebung aktualisieren "
                            "oder den Text einfügen.") from exc
    try:
        text = "\n".join((seite.extract_text() or "") for seite in PdfReader(io.BytesIO(inhalt)).pages)
    except Exception as exc:
        raise EingabeFehler("Die Datei lässt sich nicht als PDF lesen.") from exc
    if not text.strip():
        raise EingabeFehler("Im PDF steht kein lesbarer Text. Bitte den Text von LinkedIn einfügen.")
    return text


def eingabe_speichern(text: str) -> None:
    text = (text or "").strip()
    if not text:
        raise EingabeFehler("Bitte den Profiltext einfügen oder ein PDF auswählen.")
    if len(text) > MAX_TEXT:
        raise EingabeFehler(f"Der Text ist zu lang (höchstens {MAX_TEXT} Zeichen).")
    _ordner().mkdir(parents=True, exist_ok=True)
    _eingabe_pfad().write_text(text, encoding="utf-8")
    verwerfen()


def eingabe_lesen() -> str | None:
    pfad = _eingabe_pfad()
    return pfad.read_text(encoding="utf-8") if pfad.exists() else None


def _text(wert, grenze: int, name: str) -> str:
    if wert is None:
        return ""
    if not isinstance(wert, str):
        raise EingabeFehler(f"{name} muss Text sein.")
    wert = wert.strip()
    if len(wert) > grenze:
        raise EingabeFehler(f"{name} ist zu lang (höchstens {grenze} Zeichen).")
    return wert


def vorschlag_pruefen(roh) -> dict:
    """Prüft den Vorschlag der KI, bevor er gespeichert wird: nur bekannte Felder, begrenzte Längen."""
    if not isinstance(roh, dict):
        raise EingabeFehler("Der Vorschlag muss ein JSON-Objekt sein.")
    skills = roh.get("skills") or []
    werdegang = roh.get("werdegang") or []
    if not isinstance(skills, list) or not isinstance(werdegang, list):
        raise EingabeFehler("skills und werdegang müssen Listen sein.")
    if len(skills) > _MAX_SKILLS or len(werdegang) > _MAX_EINTRAEGE:
        raise EingabeFehler("Der Vorschlag enthält zu viele Einträge.")
    eintraege = []
    for e in werdegang:
        if not isinstance(e, dict) or e.get("art") not in _ARTEN:
            raise EingabeFehler(f"Jeder Werdegang-Eintrag braucht eine art aus {', '.join(_ARTEN)}.")
        eintrag = {"art": e["art"], **{k: _text(e.get(k), _MAX_EINZEILIG, k) for k in _EINZEILIG},
                   "beschreibung": _text(e.get("beschreibung"), _MAX_FREITEXT, "beschreibung")}
        if eintrag["firma"] or eintrag["rolle"]:
            eintraege.append(eintrag)
    return {
        "headline": _text(roh.get("headline"), _MAX_EINZEILIG, "headline"),
        "standort": _text(roh.get("standort"), _MAX_EINZEILIG, "standort"),
        "positionierung": _text(roh.get("positionierung"), _MAX_FREITEXT, "positionierung"),
        "skills": [s for s in (_text(x, _MAX_EINZEILIG, "skill") for x in skills) if s],
        "werdegang": eintraege,
    }


def vorschlag_speichern(roh) -> dict:
    vorschlag = vorschlag_pruefen(roh)
    _ordner().mkdir(parents=True, exist_ok=True)
    _vorschlag_pfad().write_text(json.dumps(vorschlag, ensure_ascii=False), encoding="utf-8")
    # Die KI hat die Eingabe verarbeitet: Den rohen Profiltext nicht länger liegen lassen als nötig.
    _eingabe_pfad().unlink(missing_ok=True)
    return vorschlag


def vorschlag_lesen() -> dict | None:
    pfad = _vorschlag_pfad()
    return json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else None


def verwerfen() -> None:
    _vorschlag_pfad().unlink(missing_ok=True)


def vorschau(vorschlag: dict, session: Session) -> dict:
    """Was `uebernehmen` tun würde: dieselben Regeln wie `_additiv_schreiben`, ohne etwas zu schreiben."""
    profile = session.get(Profile, 1)
    felder, behalten = [], []
    for feld, label in FELDER.items():
        if vorschlag[feld]:
            if getattr(profile, feld, None):
                behalten.append(label)
            else:
                felder.append({"label": label, "wert": vorschlag[feld]})

    vorhanden = {s.name.strip().lower() for s in session.exec(select(ProfileSkill)).all()}
    skills_neu = []
    for name in vorschlag["skills"]:
        if name.lower() not in vorhanden:
            vorhanden.add(name.lower())
            skills_neu.append(name)

    schluessel = {linkedin_import._career_key(c.art, c.firma, c.rolle, c.von, c.bis)
                  for c in session.exec(select(CareerEntry)).all()}
    werdegang_neu = []
    for e in vorschlag["werdegang"]:
        key = linkedin_import._career_key(e["art"], e["firma"], e["rolle"], e["von"], e["bis"])
        if key not in schluessel:
            schluessel.add(key)
            werdegang_neu.append(e)

    return {"vorhanden": True, "felder": felder, "felder_behalten": behalten,
            "skills_neu": skills_neu, "skills_vorhanden": len(vorschlag["skills"]) - len(skills_neu),
            "werdegang_neu": werdegang_neu, "werdegang_vorhanden": len(vorschlag["werdegang"]) - len(werdegang_neu)}


def uebernehmen(vorschlag: dict, session: Session) -> dict:
    felder = {feld: vorschlag[feld] for feld in FELDER}
    ergebnis = linkedin_import._additiv_schreiben(session, felder, vorschlag["skills"], vorschlag["werdegang"])
    verwerfen()
    return ergebnis
