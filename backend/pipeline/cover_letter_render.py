#!/usr/bin/env python3
"""Anschreiben-Klartext → schlichte Brief-.docx + PDF (Phase 48 Stufe A).

Deterministisch, KEIN LLM: der vom Nutzer editierte `Application.cover_letter_text` (Fließtext,
Absätze durch Leerzeile getrennt — bereits inkl. **Briefkopf** (Name + Kontaktzeile),
Ort/Datum, Betreff, Anrede und Grußformel, so wie `anschreiben-erstellen` ihn laut
`SKILL.md` verfasst) wird 1:1 zu Word-Absätzen. Das Anschreiben ist NICHT ATS-gescannt
(Design-Entscheidung 3 der Spec) — anders als `cv_export.py` also KEINE Seitenumbruch-/
Fußzeilen-Dokument-Engine nötig, keine Style-Feinheiten.

BRIEFKOPF (P2-24, 31.08.2026): Der Renderer stellt sicher, dass der Brief einen hat — er
setzt ihn aus `config/profil.md` davor, WENN der Text noch keinen trägt. Bis dahin erwartete
er ihn im Text, und der Skill listete ihn in seinem `Aufbau` nicht auf; er stand dort nur
beiläufig in einer Klammer, die klang, als erzeuge ihn der Renderer. Zwei Läufe am selben
Tag gingen deshalb verschieden aus — einmal mit Kopf, einmal ohne (Rückmeldung des Nutzers:
„Da fehlt komplett der Kopf des Schreibens mit allen meinen Daten").

Zusätzlich richtete das Fehlen Schaden an: Der erste Absatz wird als Absendername gesetzt
(fett, 16 pt) — ohne Kopf traf das die BETREFFZEILE.

Die Doppelung, wegen der der eigene Kopf am 23.07.2026 entfernt wurde, kann nicht
zurückkommen: `_hat_briefkopf()` erkennt einen vorhandenen Kopf an der ersten Zeile
(Name aus dem Profil) und lässt den Text dann unangetastet.

Umbenennung + PDF-Erzeugung übernimmt unverändert `pipeline.cv_export.export_cover_letter()`
(Spiegel-Logik, nicht dupliziert) — dieses Modul rendert nur die rohe Arbeitsdatei.

CLI (auch der `cover-letter-render`-Task-kind ruft das so auf):
    cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.cover_letter_render <job_id>
"""
import datetime
import json
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from pipeline.user_profile import briefkopf, briefkopf_ort, user_name
from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import Application
from pipeline import bewerbungssprache, cv_export

# Schrift/Ränder bewusst identisch zum CV (`data/cv_basis/base_*.docx`: docDefault Calibri, 21 half-pt =
# 10,5 pt) — Anschreiben und Lebenslauf sollen beim Empfänger wie EIN Satz aussehen. Bis
# 23.07.2026 setzte dieses Modul nur die GRÖSSE (11 pt) und keine Schriftart; dadurch zog die
# python-docx-Standardvorlage ihre Theme-Schrift **Cambria (Serif)** — das PDF sah völlig anders
# aus als der CV. Die Ränder sind ebenfalls die des CV (python-docx-Default wäre 2,54 cm rundum,
# das kostete rund eine halbe Seite).
# Typo-Hierarchie (Styleguide-Vorgabe 23.07.2026): Fließtext 10–12 pt, Überschriften 12–14 pt
# (meist fett), Name 18–24 pt im CV. Im Brief bleibt der Absendername bewusst unter dem
# CV-Wert (20 pt) — als Briefkopf soll er den Seitenanfang gliedern, nicht wie ein Titelblatt
# wirken. Alles andere erbt vom Normal-Style, es gibt also nur diese drei bewussten Größen.
_BRIEF_PT = Pt(10.5)      # Fließtext (Normal-Style) — untere Hälfte des 10–12-pt-Bandes,
                          # damit das Anschreiben sicher auf EINE Seite passt
_NAME_PT = Pt(16)         # Absendername, fett
_BETREFF_PT = Pt(12)      # Betreffzeile, fett — unteres Ende des Überschriften-Bandes
_BRIEF_FONT = "Calibri"
_ABSATZ_ABSTAND = Pt(6)
_RAND_LR, _RAND_TOP, _RAND_BOTTOM = Cm(1.94), Cm(1.76), Cm(1.59)

# Betreff soll unten eine Leerzeile Luft haben, oben DREI (Vorgabe 23.07.2026 und 31.08.2026:
# „vor der Kopfzeile Bewerbung als … sollen noch 2 Leerzeilen mehr rein"). Umgesetzt über
# Absatzabstände statt leerer Absätze — die würden bei Umbrüchen mitwandern und ATS-Parser irritieren.
# Word ADDIERT space_after des Vorgängers und space_before des Folgeabsatzes, daher asymmetrische
# Werte: davor 6 pt (Datumszeile) + 36 = 42 pt ≈ Basisabstand + drei Leerzeilen (eine Leerzeile
# entspricht in dieser Schriftgröße rund 12 pt), danach 18 pt + 0 (die Anrede hat kein
# space_before) = 18 pt ≈ Basisabstand + eine Leerzeile.
_TITEL_ABSTAND_VOR = Pt(36)
_TITEL_ABSTAND_NACH = Pt(18)

_JAHR = re.compile(r"\b(19|20)\d{2}\b")

# Grußformeln und Betreffzeile aller Sprachen (DE, EN, FR, IT, ES, PT) aus `bewerbungssprache`.
# Nach der Grußformel folgt der Name, der eng darunter stehen soll (Briefkonvention); die
# Betreffzeile wird fett und leicht größer gesetzt (Überschriften-Band).
_GRUSSFORMEL = bewerbungssprache.grussformel_re()
_BETREFF = bewerbungssprache.betreff_re()


def _basis_layout(doc) -> None:
    """Schrift, Schriftgröße, Absatzabstände und Seitenränder einmalig am Normal-Style setzen.

    Alle Absätze erben davon — deshalb ist im ganzen Dokument garantiert EINE Schrift in EINER
    Größe aktiv (kein Run setzt eigene Werte). `rFonts` wird vollständig gesetzt (ascii/hAnsi/cs/
    eastAsia), sonst fällt LibreOffice beim PDF-Export auf die Theme-Schrift zurück und das PDF
    weicht vom Word-Dokument ab.
    """
    style = doc.styles["Normal"]
    style.font.name = _BRIEF_FONT
    style.font.size = _BRIEF_PT
    rfonts = style.element.get_or_add_rPr().get_or_add_rFonts()
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), _BRIEF_FONT)

    pf = style.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = _ABSATZ_ABSTAND
    pf.line_spacing = 1.0

    for sec in doc.sections:
        sec.left_margin = sec.right_margin = _RAND_LR
        sec.top_margin, sec.bottom_margin = _RAND_TOP, _RAND_BOTTOM


def _ist_ort_datum(absatz: str, index: int) -> bool:
    """Ort-/Datumszeile des Briefkopfs erkennen (z. B. „Musterstadt, 23 July 2026").

    Bewusst eng gefasst, damit kein Fließtext-Absatz versehentlich rechts landet:
    nur in den ersten Absätzen, EINZEILIG (der Adressblock darüber ist mehrzeilig und
    fällt damit raus), kurz, mit Komma UND einer vierstelligen Jahreszahl.
    """
    return (
        index <= 3
        and "\n" not in absatz
        and len(absatz) <= 60
        and "," in absatz
        and bool(_JAHR.search(absatz))
    )


def _hat_briefkopf(text: str) -> bool:
    """Traegt der Text schon einen Absenderblock?

    Erkannt an der ERSTEN Zeile: Ein Briefkopf beginnt mit dem Namen aus dem Profil. Bewusst
    nicht an Adresse oder Mail — die koennen im Fliesstext vorkommen, der Name in Zeile 1 nicht.
    """
    erste = text.lstrip().split("\n", 1)[0].strip()
    name = user_name()
    return bool(erste) and erste.casefold() == name.casefold()


def mit_briefkopf(text: str, heute: datetime.date | None = None, sprache: str | None = None) -> str:
    """Stellt Briefkopf und Ort-/Datumszeile voran, falls sie fehlen — sonst unveraendert.

    `sprache` bestimmt das Datumsformat (`bewerbungssprache.datum_text`): `3 November 2026`,
    `3 novembre 2026`, `3 de noviembre de 2026` usw. Ohne Sprache oder bei DE bleibt es
    `03.11.2026` wie bisher. Eine unbekannte Sprache bekommt das ISO-Datum, nie das deutsche.

    Der Kopf sind reine Profildaten (`user_profile.briefkopf()`); ihn ein Modell schreiben zu
    lassen hiesse, eine Konstante jedes Mal neu zu wuerfeln. Genau das ging in der Praxis schon einmal schief.

    Ohne gepflegtes Profil (kein Name) bleibt der Text unveraendert — ein Kopf aus Platzhaltern
    waere schlechter als keiner.
    """
    if _hat_briefkopf(text):
        return text
    kopf = briefkopf()
    if not kopf:
        return text
    tag = heute or datetime.date.today()
    ort = briefkopf_ort()
    ort_datum = (ort + ", " if ort else "") + bewerbungssprache.datum_text(tag, sprache)
    return kopf + "\n\n" + ort_datum + "\n\n" + text.lstrip()


def render_cover_letter(text: str, out_path: Path, sprache: str | None = None) -> None:
    """Fließtext (Absätze durch Leerzeile getrennt) → schlichte Brief-.docx: ein Word-Absatz je
    Text-Absatz, einheitliche Schrift. Der Text trägt den kompletten Brief bereits selbst
    (Briefkopf, Ort/Datum, Betreff, Anrede, Grußformel) — diese Funktion erfindet nichts dazu
    und fügt insbesondere KEINEN eigenen Namens-/Datumskopf mehr an (das doppelte den Briefkopf).
    Layout-Zutaten: Absendername (erste Zeile) groß+fett, Betreff fett, Ort-/Datumszeile
    rechtsbündig, und nach der Grußformel kein Absatzabstand, damit der Name direkt darunter
    steht (Briefkonvention) statt mit Leerzeile abgesetzt.

    `sprache` (Sprache des Anschreibens, `DE`/`EN`/`FR`/…) gibt nur das Datumsformat der
    ergänzten Ort-/Datumszeile vor; ohne Angabe bleibt es das deutsche."""
    text = mit_briefkopf(text) if sprache is None else mit_briefkopf(text, sprache=sprache)
    doc = Document()
    _basis_layout(doc)

    for index, absatz in enumerate(text.split("\n\n")):
        absatz = absatz.strip()
        if not absatz:
            continue

        # Briefkopf: NUR die erste Zeile ist der Name (groß+fett); Kontaktzeile/LinkedIn
        # darunter bleiben Fließtext im selben Absatz (Zeilenumbrüche, keine Leerzeilen).
        if index == 0:
            zeilen = absatz.split("\n")
            p = doc.add_paragraph()
            name_run = p.add_run(zeilen[0])
            name_run.bold = True
            name_run.font.size = _NAME_PT
            if len(zeilen) > 1:
                p.add_run("\n" + "\n".join(zeilen[1:]))
            continue

        if _ist_ort_datum(absatz, index):
            doc.add_paragraph(absatz).alignment = WD_ALIGN_PARAGRAPH.RIGHT
            continue

        if _BETREFF.match(absatz):
            p = doc.add_paragraph()
            betreff_run = p.add_run(absatz)
            betreff_run.bold = True
            betreff_run.font.size = _BETREFF_PT
            p.paragraph_format.space_before = _TITEL_ABSTAND_VOR
            p.paragraph_format.space_after = _TITEL_ABSTAND_NACH
            continue

        p = doc.add_paragraph(absatz)
        if _GRUSSFORMEL.match(absatz):
            p.paragraph_format.space_after = Pt(0)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))


def extract_text_from_docx(docx_path) -> str:
    """.docx → reiner Fließtext (Absätze durch Leerzeile getrennt) — Fallback „Text aus
    vorhandener .docx laden" für Bestandsanschreiben ohne `cover_letter_text`."""
    doc = Document(str(docx_path))
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


def render_and_export(job_id) -> dict:
    """Task-kind-Einstieg: Application zu `job_id` laden, `cover_letter_text` in eine rohe
    Arbeitsdatei rendern, danach `cv_export.export_cover_letter()` unverändert für Umbenennung +
    PDF aufrufen (keine Duplizierung der Namens-/PDF-Logik). Die rohe Datei trägt einen stabilen
    Scratch-Namen (`_raw_<application_id>.docx`) — wird bei jedem Lauf überschrieben, nicht
    akkumuliert; `export_cover_letter` benennt sie danach nach Konvention um."""
    init_db()
    with Session(engine) as s:
        app = s.exec(select(Application).where(Application.job_id == job_id)).first()
        if not app:
            raise SystemExit(f"Application zu Job {job_id} nicht gefunden")
        if not app.cover_letter_text:
            raise SystemExit(f"Application {app.id} hat keinen cover_letter_text")

        cover_dir = cv_export.PROJECT_ROOT / "outputs" / "anschreiben"
        raw_path = cover_dir / f"_raw_{app.id}.docx"
        # Sprache wie in `cv_export.export_cover_letter`: gespeichert, sonst aus dem Text (Grußformel).
        render_cover_letter(app.cover_letter_text, raw_path,
                            sprache=app.cover_letter_language or cv_export._sprache_aus_text(app, raw_path))

        app.cover_letter_path = cv_export._rel(raw_path)
        s.add(app)
        s.commit()
        application_id, language = app.id, app.cover_letter_language

    return cv_export.export_cover_letter(application_id, language)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit("Nutzung: python -m pipeline.cover_letter_render <job_id>")
    result = render_and_export(int(args[0]))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("pdf_fehler"):
        print(f"\nHinweis: PDF nicht erzeugt — {result['pdf_fehler']}", file=sys.stderr)
