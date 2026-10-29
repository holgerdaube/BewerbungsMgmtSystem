"""P2-22 (28.08.2026): Jede erzeugte HTML-Seite trägt das App-Icon.

ANLASS (Rückmeldung): „Alle sollen das Favicon nutzen, keine Webseite und kein Report mehr, der im
Browser nicht das Favicon nutzt." Die Bestandsaufnahme ergab: drei von elf Erzeugern hatten
eines (Coach-Site, Doku-Seiten, die App), sieben nicht.

DREI EBENEN sichern das ab, und diese Datei bewacht alle drei:
  1. Die Erzeuger binden das Icon in ihre Vorlage ein → `test_erzeugt_*`.
  2. `/api/artifact` setzt es beim Ausliefern nach → `test_artefakt_endpunkt_*`.
  3. `pipeline.favicon_nachruesten` schreibt es in bestehende Dateien → `test_nachruesten_*`.

DIE EINFÜGESTELLE IST NICHT BELIEBIG (`test_zeichensatz_bleibt_im_ersten_kilobyte`): Der
Data-URI ist mit 3,3 KB grösser als die 1024 Bytes, innerhalb derer der HTML-Standard das
`<meta charset>` erwartet. Setzt man das Icon davor, rutscht die Zeichensatz-Angabe aus diesem
Fenster und der Browser darf die Kodierung raten — bei einem deutschen Bericht heisst das
kaputte Umlaute. Genau so war die erste Fassung gebaut; der Test hält die Korrektur fest.

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention).
"""
import datetime

import pytest


def _hat_icon(html: str) -> bool:
    from app.favicon import hat_favicon

    return hat_favicon(html)


# ── Ebene 1: die Erzeuger ─────────────────────────────────────────────────────────────────
def test_erzeugt_tages_digest_mit_icon(session):
    from pipeline.digest import build_digest_html

    assert _hat_icon(build_digest_html())


def test_erzeugt_company_fit_mit_icon():
    """Stellvertretend für die Vorlagen-Erzeuger: Das Icon steckt als `{_FAVICON}` in der
    f-String-Vorlage, es genügt also, dass die Konstante gefüllt ist und die Vorlage sie nutzt."""
    from pathlib import Path

    import pipeline.company_fit as cf

    quelle = Path(cf.__file__).read_text(encoding="utf-8")
    assert "{_FAVICON}" in quelle, "die Vorlage bindet das Icon nicht ein"
    assert "from app.favicon import" in quelle


@pytest.mark.parametrize("modul", [
    "pipeline.digest", "beirat_engine", "pipeline.posting_snapshot", "pipeline.cleanup",
    "pipeline.migrate_reports", "pipeline.transcript_report", "pipeline.company_fit",
    "pipeline.coach_export", "pipeline.docs_render",
])
def test_jeder_html_erzeuger_kennt_das_favicon(modul):
    """DER Wächter für Ebene 1: Wer künftig einen HTML-Erzeuger baut und das Icon vergisst,
    fällt hier auf — vorausgesetzt, er trägt sich in diese Liste ein. Die Liste ist bewusst
    explizit: Ein automatisches Absuchen aller Module würde auch Test-Fixtures und Fragmente
    erwischen und wäre damit entweder löchrig oder voller Ausnahmen."""
    import importlib
    from pathlib import Path

    m = importlib.import_module(modul)
    quelle = Path(m.__file__).read_text(encoding="utf-8")

    assert "favicon" in quelle.lower(), (
        f"{modul} erzeugt HTML, bindet aber kein Favicon ein. `from app.favicon import "
        "FAVICON_LINK as _FAVICON` und `{_FAVICON}` hinter `<meta charset=…>` setzen.")


def test_report_vorlage_traegt_das_icon():
    """Aus `assets/report_theme_bms.html` entstehen ALLE Skill-Berichte (Match, ATS-Scan,
    Briefing, Absagen-Analyse …). Fehlt das Icon dort, fehlt es in jedem davon."""
    from pathlib import Path

    from app.favicon import PROJEKT_ROOT

    vorlage = (PROJEKT_ROOT / "assets" / "report_theme_bms.html").read_text(encoding="utf-8")

    assert _hat_icon(vorlage)


# ── Ebene 2: der Auslieferungsweg ─────────────────────────────────────────────────────────
def test_artefakt_endpunkt_setzt_fehlendes_icon_nach(client, tmp_path, monkeypatch):
    """Deckt den Bestand ab: Berichte von vor der Umstellung liegen ohne Icon auf der Platte.
    Beim Ausliefern kostet das Ergänzen nichts."""
    import app.main as main

    bericht = tmp_path / "data" / "company_fit" / "alter_bericht.html"
    bericht.parent.mkdir(parents=True)
    bericht.write_text('<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">'
                       "<title>Alt</title></head><body><p>Inhalt</p></body></html>",
                       encoding="utf-8")
    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)

    antwort = client.get("/api/artifact", params={"path": "data/company_fit/alter_bericht.html"})

    assert antwort.status_code == 200
    assert _hat_icon(antwort.text)
    assert "<p>Inhalt</p>" in antwort.text, "der Inhalt darf sich nicht verändern"


def test_artefakt_download_bleibt_unveraendert(client, tmp_path, monkeypatch):
    """Ein Download soll die Datei liefern, wie sie ist — das Nachsetzen gilt nur der Anzeige."""
    import app.main as main

    bericht = tmp_path / "data" / "company_fit" / "download.html"
    bericht.parent.mkdir(parents=True)
    inhalt = '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>X</body></html>'
    bericht.write_text(inhalt, encoding="utf-8")
    monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)

    antwort = client.get("/api/artifact", params={"path": "data/company_fit/download.html",
                                                  "download": "true"})

    assert antwort.status_code == 200
    assert not _hat_icon(antwort.text)


# ── Ebene 3: die Nachrüstung ──────────────────────────────────────────────────────────────
def test_nachruesten_ist_idempotent(tmp_path):
    """Zweimal laufen darf keine zwei Links erzeugen — sonst wüchse jede Datei bei jedem
    Tageslauf um 3,3 KB."""
    from app.favicon import mit_favicon

    roh = '<html><head><meta charset="utf-8"><title>T</title></head><body>x</body></html>'
    einmal = mit_favicon(roh)
    zweimal = mit_favicon(einmal)

    assert einmal.count('rel="icon"') == 1
    assert zweimal == einmal


def test_fremdes_icon_wird_durch_das_bms_icon_ersetzt():
    """P2-44 (23.09.2026) — GEÄNDERTE REGEL. Bis dahin ließ `mit_favicon` jede Datei in Ruhe, die
    irgendein Icon trug („test_nachruesten_laesst_fremde_icons_in_ruhe“). Am 23.09. fiel im
    ATS-Scan ein fremdes Icon; die Messung am Bestand ergab 26 von 496 Skill-Berichten mit einem
    selbst geschriebenen Icon — es wäre für immer geblieben. Jetzt gewinnt unser Icon."""
    from app.favicon import FAVICON_LINK, mit_favicon

    roh = '<html><head><meta charset="utf-8"><link rel="shortcut icon" href="/eigen.ico"></head></html>'

    neu = mit_favicon(roh)

    assert neu.count(FAVICON_LINK) == 1
    assert "/eigen.ico" not in neu


def test_verstuemmeltes_base64_wird_ersetzt():
    """Der reale Fehlerfall: das Modell kopiert den Data-URI der Vorlage abgeschnitten mit —
    der Browser zeigt dann gar kein Bild. Genau diese Dateien müssen heilbar sein."""
    from app.favicon import FAVICON_LINK, mit_favicon

    roh = ('<html><head><meta charset="utf-8">'
           '<link rel="icon" type="image/png" href="data:image/png;base64,iVBORw0KGgoAAAANS">'
           "</head><body>x</body></html>")

    neu = mit_favicon(roh)

    assert neu.count(FAVICON_LINK) == 1
    assert "iVBORw0KGgoAAAANS\"" not in neu


def test_mehrere_icon_links_werden_auf_eines_reduziert():
    from app.favicon import FAVICON_LINK, mit_favicon

    roh = ('<html><head><meta charset="utf-8">'
           '<link rel="icon" href="/a.png"><link rel="shortcut icon" href="/b.ico">'
           "</head></html>")

    neu = mit_favicon(roh)

    assert neu.count(FAVICON_LINK) == 1
    assert "/a.png" not in neu and "/b.ico" not in neu


def test_apple_touch_icon_bleibt_unberuehrt():
    """`apple-touch-icon` dient dem Home-Bildschirm, nicht dem Browser-Tab — das ersetzt
    dieses Modul bewusst nicht (s. `_ICON_TAG_RE`)."""
    from app.favicon import FAVICON_LINK, mit_favicon

    roh = ('<html><head><meta charset="utf-8">'
           '<link rel="apple-touch-icon" href="/touch.png"></head></html>')

    neu = mit_favicon(roh)

    assert '<link rel="apple-touch-icon" href="/touch.png">' in neu
    assert neu.count(FAVICON_LINK) == 1


def test_eigenes_icon_bleibt_unveraendert():
    """Gegenprobe zur neuen Regel: Trägt die Datei bereits unser Icon, wird nichts angefasst —
    sonst wüchse jede Datei bei jedem Tageslauf."""
    from app.favicon import FAVICON_LINK, hat_bms_favicon, mit_favicon

    roh = f'<html><head><meta charset="utf-8">{FAVICON_LINK}</head><body>x</body></html>'

    assert hat_bms_favicon(roh)
    assert mit_favicon(roh) == roh


def test_nachruesten_zaehlt_ersetzte_icons_getrennt(tmp_path, monkeypatch, capsys):
    """Das Nachrüst-Skript weist Korrekturen getrennt aus — sonst sähe ein Tageslauf so aus,
    als hätte er nichts getan, obwohl er 26 Berichte repariert hat."""
    from app.favicon import FAVICON_LINK
    from pipeline import favicon_nachruesten as fn

    wurzel = tmp_path / "data"
    wurzel.mkdir()
    (wurzel / "fremd.html").write_text(
        '<html><head><meta charset="utf-8"><link rel="icon" href="/fremd.png"></head></html>',
        encoding="utf-8")
    (wurzel / "ohne.html").write_text(
        '<html><head><meta charset="utf-8"></head></html>', encoding="utf-8")
    (wurzel / "gut.html").write_text(
        f'<html><head><meta charset="utf-8">{FAVICON_LINK}</head></html>', encoding="utf-8")
    monkeypatch.setattr(fn, "PROJEKT_ROOT", tmp_path)
    monkeypatch.setattr(fn, "ORDNER", ["data"])

    fn.main([])
    ausgabe = capsys.readouterr().out

    assert "fremdes Icon ersetzt : 1" in ausgabe
    assert "Icon ergaenzt        : 1" in ausgabe
    assert "hatten schon ein Icon: 1" in ausgabe
    assert (wurzel / "fremd.html").read_text(encoding="utf-8").count(FAVICON_LINK) == 1
    assert "/fremd.png" not in (wurzel / "fremd.html").read_text(encoding="utf-8")


def test_fragment_ohne_kopf_bleibt_unveraendert():
    """Nicht jede HTML-Datei ist ein Dokument — Fragmente haben keinen `<head>`."""
    from app.favicon import mit_favicon

    fragment = "<div class='karte'><p>nur ein Schnipsel</p></div>"

    assert mit_favicon(fragment) == fragment


def test_header_wird_nicht_mit_head_verwechselt():
    """`<header class=…>` im `<body>` darf nicht als `<head>` durchgehen — mehrere Erzeuger
    nutzen genau dieses Element."""
    from app.favicon import mit_favicon

    roh = "<html><body><header class='head'><h1>Titel</h1></header></body></html>"

    assert mit_favicon(roh) == roh, "ein <header> ist kein <head>"


# ── Die Einfügestelle ─────────────────────────────────────────────────────────────────────
def test_zeichensatz_bleibt_im_ersten_kilobyte():
    """Der Data-URI ist 3,3 KB gross. Vor dem `<meta charset>` eingefügt, schöbe er die
    Zeichensatz-Angabe aus den ersten 1024 Bytes — der Browser dürfte die Kodierung dann raten,
    und deutsche Umlaute brächen. Genau so war die erste Fassung gebaut."""
    from app.favicon import mit_favicon

    roh = ('<!DOCTYPE html><html lang="de"><head>\n<meta charset="utf-8">\n'
           "<title>Bericht über Grüße</title></head><body>x</body></html>")

    ergebnis = mit_favicon(roh)

    assert ergebnis.lower().index("charset") < 1024, (
        "die Zeichensatz-Angabe muss im ersten Kilobyte bleiben")
    assert ergebnis.index('rel="icon"') > ergebnis.lower().index("charset"), (
        "das Icon gehört HINTER die Zeichensatz-Angabe")


def test_kein_backreference_unfall_durch_base64():
    """`re.sub` deutet in String-Ersetzungen Backslash-Ziffern-Folgen als Rückverweis. Base64
    ist davor nicht gefeit, deshalb wird eine ErsetzungsFUNKTION übergeben. Der Test prüft, dass
    der eingefügte Link vollständig und unverfälscht ankommt."""
    from app.favicon import FAVICON_LINK, mit_favicon

    if not FAVICON_LINK:
        pytest.skip("kein Icon im Design lesbar")
    ergebnis = mit_favicon('<html><head><meta charset="utf-8"></head></html>')

    assert FAVICON_LINK in ergebnis


def test_ohne_favicon_datei_kein_absturz(monkeypatch, tmp_path):
    """Fehlt das Icon (z. B. weil die Design-Vorgabe beschädigt ist), soll es eben kein Icon
    geben statt eines Absturzes — der Digest muss weiter bauen. P2-72: Das Icon kommt aus dem
    Design (`pipeline/design.py`), nicht mehr aus `frontend/public/favicon-32.png`; die Vorgabe wird
    deshalb auf eine fehlende Datei umgelenkt (vorher: `FAVICON_DATEI`)."""
    import app.favicon as fav
    from pipeline import design

    monkeypatch.setattr(design, "VORGABE_DATEI", tmp_path / "gibts-nicht.json")

    assert fav.favicon_link() == ""
    assert fav.gueltige_links() == ()
