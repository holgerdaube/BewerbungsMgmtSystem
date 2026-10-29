"""Phase 67E (P2-16, Code-Review 2026-07-25) — der ZIP-Import-Endpunkt (`app/main.py::
profil_import_zip`) prüft nur die KOMPRIMIERTE Upload-Größe (`_MAX_UPLOAD`, main.py, 25 MB).
`pipeline.linkedin_import._lese_csv()` las eine ZIP-Entry bisher UNBEGRENZT in den Speicher
(`list(csv.DictReader(text))`, kein Größencheck) — eine Entry mit hoher Kompressionsrate bleibt
unter dem Upload-Limit und entpackt auf ein Vielfaches (klassische Zip-Bombe).

Empirisch geprüft (Report Phase 67E, nicht geraten): ein einzelner `zipfile.ZipExtFile.read(n)`-
Aufruf mit explizitem `n` dekomprimiert NACHWEISLICH nur so viele Bytes wie angefordert (Test
gegen eine ehrliche 60-MB-Entry: `read(1024)` lieferte exakt 1024 Bytes in < 0,01 s) — die
Fixtures unten nutzen deshalb gefahrlos reale (wenn auch stark komprimierbare) Test-ZIPs statt
Mocks, ohne dass ein Testlauf tatsächlich 20+ MB Arbeitsspeicher braucht.

B1 (kein Zugriff auf echte Nutzerdaten, Q3): alle ZIP-Inhalte hier sind synthetisch erzeugt.
"""
import io
import zipfile

import pytest


def _zip_mit_entry(name: str, inhalt: bytes) -> zipfile.ZipFile:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(name, inhalt)
    return zipfile.ZipFile(io.BytesIO(buf.getvalue()))


def test_zu_grosse_entry_wird_ueber_deklarierte_groesse_abgelehnt():
    """Kernfall: eine Entry, deren EHRLICH deklarierte unkomprimierte Größe (Zentralverzeichnis)
    über dem Limit liegt, wird VOR dem Parsen verworfen — ohne den Fix hätte `_lese_csv` sie
    klaglos komplett eingelesen (hier 21 MB, in der freien Wildbahn beliebig skalierbar: ein
    einzelnes hochkomprimierbares Muster erreicht leicht Kompressionsraten, bei denen ein
    Vielfaches des 25-MB-Upload-Limits entpackt)."""
    import pipeline.linkedin_import as li

    payload = b"A" * (li._MAX_ENTRY_UNCOMPRESSED + 1024)   # knapp ueber dem Limit, hochkomprimierbar
    zf = _zip_mit_entry("Skills.csv", payload)

    with pytest.raises(li.LinkedinImportError, match="Skills.csv"):
        li._lese_csv(zf, "Skills.csv")


def test_entry_exakt_am_limit_wird_noch_akzeptiert():
    """Grenzfall: exakt `_MAX_ENTRY_UNCOMPRESSED` Bytes darf NICHT fälschlich abgelehnt werden
    (Off-by-one-Absicherung — die Prüfung muss `>`, nicht `>=`, verwenden). Viele KURZE Zeilen
    statt eines einzelnen riesigen Felds — Pythons `csv`-Modul hat sein EIGENES, unabhängiges
    Feldgrößenlimit (`field_size_limit()`, Default 128 KB), das bei einem einzelnen
    Mammut-Feld zuerst greifen würde und dann fälschlich DIESEN Fix testen würde statt den
    eigentlichen Grenzfall."""
    import pipeline.linkedin_import as li

    kopf = b"Name\n"
    zeile = b"Kompetenz-Musterzeile-fuer-den-Grenzwerttest\n"   # 46 Bytes, weit unter 128 KB
    koerper_ziel = li._MAX_ENTRY_UNCOMPRESSED - len(kopf)
    n, rest = divmod(koerper_ziel, len(zeile))
    letzte_zeile = (b"x" * (rest - 1) + b"\n") if rest else b""
    payload = kopf + zeile * n + letzte_zeile
    assert len(payload) == li._MAX_ENTRY_UNCOMPRESSED
    zf = _zip_mit_entry("Skills.csv", payload)

    rows = li._lese_csv(zf, "Skills.csv")
    assert len(rows) >= n > 0   # keine Ablehnung, echte Zeilen kamen durch


def test_normale_kleine_csv_wird_weiterhin_korrekt_gelesen():
    """Erfolgsfall unverändert (Invariante Q5): eine realistisch kleine LinkedIn-Skills.csv wird
    exakt wie vor dem Fix geparst."""
    import pipeline.linkedin_import as li

    csv_text = "Name\nStakeholder Management\nDelivery Governance\n"
    zf = _zip_mit_entry("Skills.csv", csv_text.encode("utf-8"))

    rows = li._lese_csv(zf, "Skills.csv")
    assert [r["Name"] for r in rows] == ["Stakeholder Management", "Delivery Governance"]


def test_importiere_zip_end_to_end_meldet_die_ueberschreitung(session):
    """Ende-zu-Ende über die öffentliche Schnittstelle (nicht nur den internen Helper): ein
    reales ZIP mit einer normalen `Profile.csv` PLUS einer zu großen `Skills.csv` muss über
    `importiere_zip()` als `LinkedinImportError` durchschlagen — genau der Pfad, den
    `app/main.py::profil_import_zip` in ein sauberes 422 statt eines 500ers übersetzt."""
    import pipeline.linkedin_import as li

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Profile.csv", "Headline\nHead of Something\n")
        zf.writestr("Skills.csv", b"A" * (li._MAX_ENTRY_UNCOMPRESSED + 1024))

    with pytest.raises(li.LinkedinImportError):
        li.importiere_zip(buf.getvalue(), session)
