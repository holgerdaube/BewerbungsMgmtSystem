"""Kontrakt-Tests für `pipeline/user_profile.py` (Phase 71A, Name aus dem Profil).

`user_name()`/`user_first_name()` lesen `config/profil.md` — hier per Monkeypatch auf
Fixture-Dateien umgebogen, damit die meisten Tests unabhängig vom echten Profil laufen.
GENAU EIN Test (die Regression) prüft bewusst OHNE Monkeypatch gegen das echte
`config/profil.md` — das ist der Kern-Beweis, dass ein laufender Betrieb nach der
Umstellung auf das Profil identisch bleibt (Leitplanke aus der Phase-71-Spec). Modul-Import bewusst
funktionslokal (conftest.py-Konvention: App-/Pipeline-Module nie auf Modulebene importieren).
"""


def test_user_name_liest_profil_fixture(tmp_path, monkeypatch):
    import pipeline.user_profile as up

    profil = tmp_path / "profil.md"
    profil.write_text("## Identität\n- **Name:** Max Muster\n", encoding="utf-8")
    monkeypatch.setattr(up, "_PROFIL_MD", profil)

    assert up.user_name() == "Max Muster"
    assert up.user_first_name() == "Max"


def test_user_name_fallback_ohne_namenszeile(tmp_path, monkeypatch):
    """Profil existiert, hat aber keine `**Name:**`-Zeile -> Fallback "Bewerber" (nicht mehr
    ein fremder Name -- Kern der Umstellung: ohne Profil kein fremder Name)."""
    import pipeline.user_profile as up

    profil = tmp_path / "profil.md"
    profil.write_text("## Identität\n- Kein Name-Feld in dieser Datei.\n", encoding="utf-8")
    monkeypatch.setattr(up, "_PROFIL_MD", profil)

    assert up.user_name() == "Bewerber"
    assert up.user_first_name() == "Bewerber"


def test_user_name_fallback_leere_namenszeile(tmp_path, monkeypatch):
    """`**Name:**` vorhanden, aber ohne Wert (nur Whitespace) -> auch das faellt auf den
    Fallback zurueck, statt einen leeren String zurueckzugeben (Aufrufer verlassen sich auf
    einen nicht-leeren Namen, z. B. `_camel_name`/`user_first_name`)."""
    import pipeline.user_profile as up

    profil = tmp_path / "profil.md"
    profil.write_text("## Identität\n- **Name:**    \n", encoding="utf-8")
    monkeypatch.setattr(up, "_PROFIL_MD", profil)

    assert up.user_name() == "Bewerber"


def test_user_name_fallback_fehlende_datei(tmp_path, monkeypatch):
    """Profil-Datei existiert gar nicht -> Fallback statt Crash (OSError abgefangen)."""
    import pipeline.user_profile as up

    monkeypatch.setattr(up, "_PROFIL_MD", tmp_path / "nicht_vorhanden.md")

    assert up.user_name() == "Bewerber"


def test_user_name_regression_echtes_profil():
    """KERN-REGRESSION (Spec Phase 71A, Leitplanke): das ECHTE config/profil.md (kein
    Monkeypatch, `_PROFIL_MD` zeigt auf den echten Projekt-Pfad) liefert den Namen aus seiner
    `**Name:**`-Zeile -- der laufende Betrieb darf nach der Umstellung nicht brechen. Reine Lese-
    Operation, config/profil.md wird an keiner Stelle geschrieben. Der Name selbst steht hier
    bewusst nicht: Der Test liest ihn selbst aus der Datei und vergleicht."""
    import pytest
    import pipeline.user_profile as up

    if not up._PROFIL_MD.exists():
        pytest.skip("config/profil.md (Bereich 2) existiert nur auf einer eingerichteten Installation, nie im CI-Checkout")
    import re

    zeile = re.search(r"\*\*Name:\*\*\s*(.+)", up._PROFIL_MD.read_text(encoding="utf-8"))
    if not zeile or not zeile.group(1).strip():
        pytest.skip("config/profil.md hat keine ausgefüllte Name-Zeile")
    erwartet = zeile.group(1).strip()
    assert up.user_name() == erwartet
    assert up.user_first_name() == erwartet.split()[0]


def test_user_name_projekt_root_relativ_nicht_bms_data_dir():
    """`_PROFIL_MD` haengt am Projekt-Root (Path(__file__)-relativ), NICHT an BMS_DATA_DIR --
    conftest.py setzt BMS_DATA_DIR auf ein pytest-tmp-Verzeichnis; waere user_profile davon
    abhaengig, wuerde der Regressionstest oben fehlschlagen (das echte Profil laege dann
    ausserhalb des ueberwachten Pfads). Gegenprobe: der Pfad zeigt wirklich auf die echte
    Projektwurzel (existiert, endet auf config/profil.md)."""
    import os
    import pipeline.user_profile as up

    assert up._PROFIL_MD.as_posix().endswith("config/profil.md")
    # Anker fuer "echte Projektwurzel" ist die VERSIONIERTE Schwester-Datei scoring_rubrik.md
    # (im Git) — profil.md selbst gehoert nicht ins Git und fehlt im CI-Checkout.
    assert (up._PROFIL_MD.parent / "scoring_rubrik.md").exists()
    assert os.environ.get("BMS_DATA_DIR", "") not in str(up._PROFIL_MD)


def test_cv_filename_end_zu_end_ueber_user_name_mock(monkeypatch):
    """Verbindet naming.cv_filename() explizit mit user_profile.user_name() (spiegelt die
    Spec-Vorgabe "naming: 'Max Muster' -> CV_MaxMuster_...")."""
    import pipeline.user_profile as up
    from app.naming import cv_filename

    monkeypatch.setattr(up, "user_name", lambda: "Max Muster")
    assert cv_filename("Test AG", "Manager", "DE") == "CV_MaxMuster_Test_Manager_DE"


def test_cv_filename_regression_ohne_mock():
    """Spec-Vorgabe: der Name aus dem ECHTEN Profil (kein Mock) bildet den Dateinamen
    CV_<Vorname><Nachname>_... (Regression); der erwartete Name wird aus der Datei gelesen."""
    import pytest
    import pipeline.user_profile as up
    from app.naming import cv_filename

    if not up._PROFIL_MD.exists():
        pytest.skip("config/profil.md (Bereich 2) existiert nur auf einer eingerichteten Installation, nie im CI-Checkout")
    import re

    zeile = re.search(r"\*\*Name:\*\*\s*(.+)", up._PROFIL_MD.read_text(encoding="utf-8"))
    if not zeile or not zeile.group(1).strip():
        pytest.skip("config/profil.md hat keine ausgefüllte Name-Zeile")
    camel = re.sub(r"[^A-Za-z0-9]", "", zeile.group(1).strip())    # ASCII-Name: Umlaute decken die Mock-Tests ab
    if camel != re.sub(r"\s+", "", zeile.group(1).strip()):
        pytest.skip("Name mit Sonderzeichen: Transliteration prüft test_cv_filename_umlaut_name_aus_profil_mock")
    assert cv_filename("Test AG", "Manager", "DE") == f"CV_{camel}_Test_Manager_DE"


def test_cv_filename_umlaut_name_aus_profil_mock(monkeypatch):
    """Spec-Vorgabe: Umlaut-Name ('Jörg Müller' -> JoergMueller)."""
    import pipeline.user_profile as up
    from app.naming import cv_filename

    monkeypatch.setattr(up, "user_name", lambda: "Jörg Müller")
    assert cv_filename("Test AG", "Manager", "DE") == "CV_JoergMueller_Test_Manager_DE"
