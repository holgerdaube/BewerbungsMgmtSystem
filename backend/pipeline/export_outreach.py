"""Format-erhaltender Export des Outreach-Trackers.

Nutzt die Vorlage data/templates/outreach_tracker_vorlage.xlsx (P2-50: neutraler Name statt des
Original-Dateinamens mit dem Namen des Nutzers; auf dessen Rechner eine Kopie des Originals) als Vorlage
und ersetzt AUSSCHLIESSLICH die Datenzeilen im Blatt 'Outreach Tracker' (sheet3.xml) mit dem
aktuellen DB-Stand. Alles andere (Dashboard mit Drawings, Dropdowns, Formeln, alle übrigen Blätter,
Styles) wird byte-genau kopiert — openpyxl würde die Drawings verlieren, daher gezielte XML-Chirurgie.
"""
import datetime
import re
import zipfile
from pathlib import Path

from sqlmodel import Session, select

from app.db import engine
from app.models import Outreach
from app.naming import tracker_filename

ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE = ROOT / "data" / "templates" / "outreach_tracker_vorlage.xlsx"
EXPORT_DIR = ROOT / "data" / "exports"
SHEET_XML = "xl/worksheets/sheet3.xml"   # 'Outreach Tracker' (siehe workbook.xml)

# Spaltenreihenfolge im Blatt (A..N) → Outreach-Feld ("_formel" = berechnete Spalte I)
COLS = ["datum", "kontakt", "unternehmen", "typ", "kanal", "template", "antwort",
        "antwort_datum", "_formel", "next_step", "next_action_datum", "status", "notizen", "position"]
DATE_COLS = {"datum", "antwort_datum", "next_action_datum"}
LETTERS = "ABCDEFGHIJKLMN"
_EPOCH = datetime.date(1899, 12, 30)  # Excel-1900-Datumssystem


_HEADERS = ["Datum", "Kontakt", "Unternehmen", "Typ", "Kanal", "Template", "Antwort", "Antwort-Datum",
            "Tage seit Kontakt", "Nächster Schritt", "Next-Action-Datum", "Status", "Notizen", "Position"]
# Obergrenze je Spalte (Langtext-Spalten brechen um, daher gedeckelt)
_CAP = [12, 24, 24, 18, 18, 16, 10, 13, 11, 46, 14, 20, 56, 40]


def _xml_escape(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _col_widths(entries):
    """Optimale Spaltenbreite je Spalte aus dem Inhalt (Header wrappt → zählt max. 12), gedeckelt."""
    widths = []
    for c, field in enumerate(COLS):
        if field == "_formel":
            maxlen = 4
        else:
            maxlen = max([len(str(getattr(e, field))) for e in entries if getattr(e, field, None) not in (None, "")] + [0])
        base = max(maxlen, min(len(_HEADERS[c]), 12))
        widths.append(round(min(max(base + 2, 8), _CAP[c]), 2))
    return widths


def _serial(iso):
    try:
        d = datetime.date.fromisoformat(str(iso)[:10])
        return (d - _EPOCH).days
    except (ValueError, TypeError):
        return None


def _extract_styles(sheet_xml):
    """Style-Index je Spalte aus der ersten Datenzeile (row r=2) der Vorlage."""
    m = re.search(r'<row r="2"[^>]*>(.*?)</row>', sheet_xml, re.S)
    styles = {}
    if m:
        for cell in re.finditer(r'<c r="([A-N])2"(?:\s+s="(\d+)")?', m.group(1)):
            styles[cell.group(1)] = cell.group(2) or "0"
    # Fallback (aus Vorlagen-Analyse), falls Zeile 2 fehlt
    default = {"A": "16", "B": "17", "C": "17", "D": "12", "E": "12", "F": "12", "G": "12",
               "H": "12", "I": "12", "J": "18", "K": "12", "L": "12", "M": "18", "N": "19"}
    for k, v in default.items():
        styles.setdefault(k, v)
    return styles


def _cell(letter, rownum, style, field, entry, date_style):
    ref = f'{letter}{rownum}'
    if field == "_formel":  # Spalte I: Tage seit Kontakt
        s = f' s="{style}"' if style else ''
        return f'<c r="{ref}"{s}><f>IF(A{rownum}=&quot;&quot;,&quot;&quot;,TODAY()-A{rownum})</f></c>'
    if field in DATE_COLS:  # A/H/K immer mit Datums-Style (rendern als dd.mm.yyyy)
        ds = date_style or style
        s = f' s="{ds}"' if ds else ''
        val = getattr(entry, field, None)
        ser = _serial(val) if val not in (None, "") else None
        return f'<c r="{ref}"{s}><v>{ser}</v></c>' if ser is not None else f'<c r="{ref}"{s}/>'
    s = f' s="{style}"' if style else ''
    val = getattr(entry, field, None)
    if val in (None, ""):
        return f'<c r="{ref}"{s}/>'
    return f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">{_xml_escape(val)}</t></is></c>'


def build(path=None) -> Path:
    tpl = Path(path) if path else TEMPLATE
    if not tpl.exists():
        raise FileNotFoundError(f"Vorlage fehlt: {tpl}")

    with zipfile.ZipFile(tpl) as z:
        names = z.namelist()
        sheet_xml = z.read(SHEET_XML).decode("utf-8")

    styles = _extract_styles(sheet_xml)
    # Vereinheitlichung: Spalte N (Position) hat in der Vorlage Arial 12 ohne Rahmen —
    # auf den Standard-Datenstil (Arial 10 + Rahmen, wie Spalte B) angleichen, damit alle
    # Datenzeilen dieselbe Schriftart und -größe haben.
    styles["N"] = styles.get("B") or "17"
    header = re.search(r'<row r="1".*?</row>', sheet_xml, re.S)
    header_xml = header.group(0) if header else ''

    with Session(engine) as s:
        entries = s.exec(select(Outreach).order_by(Outreach.id)).all()

    date_style = styles.get("A") or "16"   # Spalte A „Datum" nutzt das Datums-Style (dd.mm.yyyy)
    rows = [header_xml]
    for i, e in enumerate(entries, start=2):
        cells = "".join(_cell(LETTERS[c], i, styles.get(LETTERS[c]), f, e, date_style) for c, f in enumerate(COLS))
        rows.append(f'<row r="{i}">{cells}</row>')
    new_sheetdata = "<sheetData>" + "".join(rows) + "</sheetData>"

    # <sheetData>…</sheetData> ersetzen (Rest des Blatts unangetastet)
    new_sheet = re.sub(r'<sheetData>.*?</sheetData>', lambda _: new_sheetdata, sheet_xml, count=1, flags=re.S)
    # Dimension aktualisieren (falls vorhanden)
    last = len(entries) + 1
    new_sheet = re.sub(r'<dimension ref="[^"]*"/>', f'<dimension ref="A1:N{last}"/>', new_sheet, count=1)

    # Spaltenbreiten auf optimale Breite (aus Inhalt) setzen; Spalten hinter N wie Vorlage
    widths = _col_widths(entries)
    cols_xml = ("<cols>" + "".join(f'<col customWidth="1" min="{i + 1}" max="{i + 1}" width="{w}"/>'
                                    for i, w in enumerate(widths))
                + '<col customWidth="1" min="15" max="26" width="8.71"/></cols>')
    new_sheet = re.sub(r'<cols>.*?</cols>', lambda _: cols_xml, new_sheet, count=1, flags=re.S)

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    from pipeline.user_profile import user_name
    out = EXPORT_DIR / tracker_filename(user_name(), "xlsx")

    with zipfile.ZipFile(tpl) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in names:
            data = new_sheet.encode("utf-8") if item == SHEET_XML else zin.read(item)
            zout.writestr(item, data)
    return out


if __name__ == "__main__":
    print("Gespeichert:", build())
