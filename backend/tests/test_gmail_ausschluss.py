"""P2-51 (Vertrag V8): `pipeline.gmail_client search --suchprofil-ausschluesse` haengt
`email_check.ausschluss_absender` aus `config/suchprofile.yaml` als ` -from:(a OR b)` an die
Query an — die privaten Rausch-Absender einer Installation stehen seither dort, nicht mehr fest
im Skill-Text (`.claude/skills/email-check/SKILL.md`).

Reine Funktionstests gegen `pipeline.gmail_client._suchprofil_ausschluss_query_teil()` (kein
Netz-/Gmail-Zugriff), YAML-Pfad je Test per `monkeypatch` auf `tmp_path` (Projekt-Konvention,
s. `tests/test_einstellungen_portale.py`) — NIE gegen die echte `config/suchprofile.yaml`.
App-/Pipeline-Module bewusst nur funktionslokal importiert (s. `tests/conftest.py`).

Der letzte Fall prueft zusaetzlich, dass der angehaengte Block sich durch die BESTEHENDE
IMAP-Uebersetzung (`pipeline.imap_mail.translate_query`) korrekt als negatives `from`-Kriterium
lesen laesst — der Schalter gilt fuer Gmail UND IMAP (s. Moduldocstring von `imap_mail.py`).
"""
import pytest


@pytest.fixture()
def _suchprofile_pfad(tmp_path, monkeypatch):
    """Isoliert `suchprofil.SUCHPROFILE_PATH` auf `tmp_path` (nie die echte Datei lesen)."""
    from pipeline import suchprofil

    pfad = tmp_path / "suchprofile.yaml"
    monkeypatch.setattr(suchprofil, "SUCHPROFILE_PATH", pfad)
    return pfad


def _schreibe(pfad, text: str) -> None:
    pfad.write_text(text, encoding="utf-8")


def test_ohne_liste_bleibt_die_query_unveraendert(_suchprofile_pfad):
    """`email_check.ausschluss_absender` fehlt im Kopf (aber die Datei existiert) → leerer
    Rueckgabewert, die aufrufende Query bleibt unveraendert."""
    from pipeline.gmail_client import _suchprofil_ausschluss_query_teil

    _schreibe(_suchprofile_pfad, "min_mitarbeiter: 100\n")

    assert _suchprofil_ausschluss_query_teil() == ""


def test_leere_liste_bleibt_die_query_unveraendert(_suchprofile_pfad):
    """Schluessel vorhanden, aber leer — Vertrag V8: „Fehlt der Schlüssel, gilt eine leere
    Liste“, eine explizit leere Liste verhaelt sich identisch."""
    from pipeline.gmail_client import _suchprofil_ausschluss_query_teil

    _schreibe(_suchprofile_pfad, "email_check:\n  ausschluss_absender: []\n")

    assert _suchprofil_ausschluss_query_teil() == ""


def test_fehlende_datei_bleibt_die_query_unveraendert(tmp_path, monkeypatch):
    """Datei/Schluessel fehlt komplett (frische Installation ohne eigenes Rauschen) →
    unveraendert, kein Fehler."""
    from pipeline import suchprofil
    from pipeline.gmail_client import _suchprofil_ausschluss_query_teil

    monkeypatch.setattr(suchprofil, "SUCHPROFILE_PATH", tmp_path / "fehlt_ganz.yaml")

    assert _suchprofil_ausschluss_query_teil() == ""


def test_mit_liste_haengt_from_block_an(_suchprofile_pfad):
    """Kernfall: nicht-leere Liste → ` -from:(a OR b)`, Reihenfolge wie in der YAML."""
    from pipeline.gmail_client import _suchprofil_ausschluss_query_teil

    _schreibe(_suchprofile_pfad, (
        "email_check:\n"
        "  ausschluss_absender:\n"
        "    - github.com\n"
        "    - email.apple.com\n"
    ))

    assert _suchprofil_ausschluss_query_teil() == " -from:(github.com OR email.apple.com)"


def test_eintraege_mit_leerzeichen_klammern_oder_anfuehrungszeichen_werden_uebersprungen(
    _suchprofile_pfad, capsys,
):
    """Vertrag: solche Eintraege wuerden die Gmail-/IMAP-Query-Syntax zerlegen — sie werden mit
    Warnung auf stderr uebersprungen, gueltige Eintraege bleiben erhalten."""
    from pipeline.gmail_client import _suchprofil_ausschluss_query_teil

    _schreibe(_suchprofile_pfad, (
        "email_check:\n"
        "  ausschluss_absender:\n"
        "    - github.com\n"
        "    - \"mit leerzeichen.de\"\n"
        "    - \"mit(klammer).de\"\n"
        "    - 'mit\"anfuehrung.de'\n"
    ))

    ergebnis = _suchprofil_ausschluss_query_teil()

    assert ergebnis == " -from:(github.com)"
    fehler = capsys.readouterr().err
    assert "mit leerzeichen.de" in fehler
    assert "mit(klammer).de" in fehler
    assert 'mit"anfuehrung.de' in fehler


def test_nur_fehlerhafte_eintraege_ergibt_unveraenderte_query(_suchprofile_pfad, capsys):
    """Bleibt nach dem Ueberspringen nichts Gueltiges uebrig, ist der Zusatz leer — nicht
    `-from:()` (das waere eine kaputte Query)."""
    from pipeline.gmail_client import _suchprofil_ausschluss_query_teil

    _schreibe(_suchprofile_pfad, (
        "email_check:\n"
        "  ausschluss_absender:\n"
        "    - \"nur (klammern)\"\n"
    ))

    assert _suchprofil_ausschluss_query_teil() == ""
    assert "wird uebersprungen" in capsys.readouterr().err


def test_imap_uebersetzung_erkennt_den_angehaengten_block(_suchprofile_pfad):
    """Gilt fuer Gmail UND IMAP (Spec-Vorgabe): der Query-Zusatz muss sich durch die
    BESTEHENDE Uebersetzungsfunktion `pipeline.imap_mail.translate_query` als negatives
    `from`-Kriterium lesen lassen, genau wie ein von Hand geschriebenes `-from:(...)`."""
    from pipeline.gmail_client import _suchprofil_ausschluss_query_teil
    from pipeline.imap_mail import translate_query

    _schreibe(_suchprofile_pfad, (
        "email_check:\n"
        "  ausschluss_absender:\n"
        "    - github.com\n"
        "    - email.apple.com\n"
    ))

    basis_query = 'newer_than:2d subject:(Bewerbung OR interview)'
    volle_query = basis_query + _suchprofil_ausschluss_query_teil()
    geparst = translate_query(volle_query)

    assert set(geparst["negative"]) == {("from", "github.com"), ("from", "email.apple.com")}
    assert ("subject", "Bewerbung") in geparst["positive"]
    assert ("subject", "interview") in geparst["positive"]
