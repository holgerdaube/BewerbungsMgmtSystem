"""P2-24 (31.08.2026): Jedes Anschreiben trägt einen Briefkopf.

Fall A (Rückmeldung aus dem Betrieb): „Da fehlt komplett der Kopf des Schreibens
mit allen meinen Daten." Der Text begann direkt mit „Bewerbung als …" — kein Name, keine
Anschrift, kein Kontakt, kein Datum.

URSACHE — eine Lücke in der Zuständigkeit, kein Codefehler:
`cover_letter_render.py` erwartete den Briefkopf IM TEXT (sein Docstring sagte das auch). Der
Skill `anschreiben-erstellen` listete ihn in seinem `Aufbau` aber NICHT auf; er stand dort nur
beiläufig in einer Klammer bei Schritt 5, die klang, als erzeuge ihn der Renderer. Damit hing es
am Lauf, ob ein Kopf entstand: Am 31.08. schrieb der Lauf für Stelle B einen, der für Stelle A
nicht.

ZWEITER SCHADEN, den das Fehlen anrichtete: Der Renderer setzt den ERSTEN Absatz als
Absendername (fett, 16 pt). Ohne Briefkopf traf das die BETREFFZEILE — deshalb sah das Ergebnis
nicht nur unvollständig, sondern falsch aus (`test_ohne_briefkopf_wuerde_der_betreff_...`).

FIX: Der Briefkopf besteht aus reinen Profildaten. Ihn ein Modell schreiben zu lassen heisst,
eine Konstante jedes Mal neu zu würfeln. `cover_letter_render` setzt ihn deshalb selbst aus
`config/profil.md` davor — idempotent, damit die Doppelung nicht zurückkommt, wegen der der
eigene Kopf am 23.07.2026 einmal entfernt worden war.

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention).
"""
import datetime

import pytest

PROFIL = """# Kandidatenprofil — Test

## Identität
- **Name:** Erika Mustermann
- **Standort:** Musterweg 3, 12345 Musterstadt (Rhein-Main)
- **Kontakt:** erika@example.com · +49-170-1234567
- **LinkedIn:** https://www.linkedin.com/in/erika-mustermann/
"""

BRIEF_OHNE_KOPF = ("Bewerbung als Director Professional Services\n\n"
                   "Liebes Team,\n\n"
                   "mit der Übernahme von Beispielsoft baut Musterwerk seine Position aus.\n\n"
                   "Mit freundlichen Grüßen\nErika Mustermann")


@pytest.fixture()
def profil(tmp_path, monkeypatch):
    """Synthetisches `config/profil.md` — die echte Datei wird NIE gelesen."""
    import pipeline.user_profile as up

    datei = tmp_path / "profil.md"
    datei.write_text(PROFIL, encoding="utf-8")
    monkeypatch.setattr(up, "_PROFIL_MD", datei)
    return datei


def test_briefkopf_aus_dem_profil(profil):
    """Name, Anschrift, Kontakt und LinkedIn — genau die vier Zeilen, nichts erfunden."""
    from pipeline.user_profile import briefkopf

    zeilen = briefkopf().split("\n")

    assert zeilen[0] == "Erika Mustermann"
    assert zeilen[1] == "Musterweg 3, 12345 Musterstadt", "der (Rhein-Main)-Zusatz gehört nicht in den Kopf"
    assert zeilen[2] == "erika@example.com | +49-170-1234567"
    assert zeilen[3] == "LinkedIn: https://www.linkedin.com/in/erika-mustermann/"


def test_ort_fuer_die_datumszeile(profil):
    """Aus der Anschrift die Stadt, ohne Postleitzahl."""
    from pipeline.user_profile import briefkopf_ort

    assert briefkopf_ort() == "Musterstadt"


def test_fehlender_briefkopf_wird_ergaenzt(profil):
    """DER Kernfall: Was in Fall A passiert ist, darf nicht mehr passieren."""
    from pipeline.cover_letter_render import mit_briefkopf

    ergebnis = mit_briefkopf(BRIEF_OHNE_KOPF, heute=datetime.date(2026, 8, 31))

    assert ergebnis.startswith("Erika Mustermann\n")
    assert "Musterweg 3, 12345 Musterstadt" in ergebnis
    assert "erika@example.com" in ergebnis
    assert "Musterstadt, 31.08.2026" in ergebnis
    assert "Bewerbung als Director Professional Services" in ergebnis, "der Brief bleibt erhalten"


def test_vorhandener_briefkopf_wird_nicht_verdoppelt(profil):
    """Die Doppelung war der Grund, warum der Renderer seinen eigenen Kopf am 23.07.2026
    verloren hat. Sie darf nicht zurückkommen — auch nicht bei zweimaligem Rendern."""
    from pipeline.cover_letter_render import mit_briefkopf

    einmal = mit_briefkopf(BRIEF_OHNE_KOPF, heute=datetime.date(2026, 8, 31))
    zweimal = mit_briefkopf(einmal, heute=datetime.date(2026, 8, 31))

    assert zweimal == einmal
    assert einmal.count("Erika Mustermann\nMusterweg") == 1


def test_selbst_geschriebener_kopf_bleibt_unangetastet(profil):
    """Ein Lauf (oder der Nutzer von Hand) darf den Kopf weiterhin selbst schreiben — dann gilt
    seiner. So bleiben die bestehenden Anschreiben unverändert."""
    from pipeline.cover_letter_render import mit_briefkopf

    eigener = ("Erika Mustermann\nAndere Straße 7, 99999 Anderswo\n\n"
               "Anderswo, 01.01.2026\n\nBewerbung als Testrolle\n\nText.")

    assert mit_briefkopf(eigener) == eigener


def test_ohne_gepflegtes_profil_kein_platzhalter_kopf(tmp_path, monkeypatch):
    """Fehlt das Profil, bleibt der Text unverändert — ein Kopf aus „Bewerber" ohne Anschrift
    wäre schlechter als keiner."""
    import pipeline.user_profile as up
    from pipeline.cover_letter_render import mit_briefkopf

    monkeypatch.setattr(up, "_PROFIL_MD", tmp_path / "gibts-nicht.md")

    assert mit_briefkopf(BRIEF_OHNE_KOPF) == BRIEF_OHNE_KOPF


def test_gerendertes_dokument_beginnt_mit_dem_namen(profil, tmp_path):
    """Ende zu Ende: Der erste Absatz der .docx trägt den Namen — groß und fett, wie es der
    Renderer für den Absender vorsieht."""
    from docx import Document

    from pipeline.cover_letter_render import render_cover_letter

    ziel = tmp_path / "brief.docx"
    render_cover_letter(BRIEF_OHNE_KOPF, ziel)
    doc = Document(str(ziel))

    erster = doc.paragraphs[0]
    assert erster.text.split("\n")[0] == "Erika Mustermann"
    assert erster.runs[0].bold is True
    assert erster.runs[0].font.size.pt == 16


def test_ohne_briefkopf_wuerde_der_betreff_als_absender_gesetzt(profil, tmp_path):
    """Der zweite Schaden, den das Fehlen anrichtete — und der Beleg, dass der Fix ihn behebt.

    Der Renderer setzt den ERSTEN Absatz als Absendername (16 pt, fett). Ohne Briefkopf ist das
    die Betreffzeile. Der Test zeigt beides: den alten Zustand (Kopf-Ergänzung übersprungen) und
    den neuen."""
    from docx import Document

    import pipeline.cover_letter_render as clr

    # Alter Zustand nachgestellt: Ergänzung ausgeschaltet.
    ohne_fix = tmp_path / "alt.docx"
    original = clr.mit_briefkopf
    try:
        clr.mit_briefkopf = lambda text, heute=None: text
        clr.render_cover_letter(BRIEF_OHNE_KOPF, ohne_fix)
    finally:
        clr.mit_briefkopf = original
    alt = Document(str(ohne_fix)).paragraphs[0]
    assert alt.text.startswith("Bewerbung als"), "Prämisse: ohne Fix landet der Betreff auf Platz 1"
    assert alt.runs[0].font.size.pt == 16, "…und wird als Absendername gesetzt — genau der Fehler"

    # Neuer Zustand
    mit_fix = tmp_path / "neu.docx"
    clr.render_cover_letter(BRIEF_OHNE_KOPF, mit_fix)
    neu = Document(str(mit_fix)).paragraphs[0]
    assert neu.text.split("\n")[0] == "Erika Mustermann"
