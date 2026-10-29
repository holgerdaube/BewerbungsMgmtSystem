"""Unit-Tests für die soffice-Discovery (Phase 71D, Windows-Grundlagen) —
`pipeline.cv_export._soffice_kandidaten()` / `_soffice_bin()`.

Ziel: die WINDOWS-Ergänzung (`_SOFFICE_CANDIDATES_WINDOWS`, neue Kandidatenpfade unter
"Program Files"/"Program Files (x86)") beweisen, OHNE das bestehende macOS-Verhalten
(`_SOFFICE_CANDIDATES`, feste Installationspfade VOR PATH) anzutasten — und OHNE echten
LibreOffice-Aufruf.

WARUM `cv_export.Path` gemockt wird statt echtem `pathlib.Path` + `tmp_path`-Dateien:
`pathlib.Path.__new__` verzweigt SELBST auf `os.name` (liefert `WindowsPath` vs. `PosixPath`).
Ein per Monkeypatch gesetztes `os.name`, das nicht zum ECHTEN Betriebssystem des Test-Runners
passt (z. B. `os.name = "nt"` auf einem echten macOS-Python), erzeugt deshalb eine Pfad-Hülle
der FALSCHEN Flavour — deren `exists()` liefert dann unabhängig vom tatsächlichen
Dateisystem-Zustand immer `False` (empirisch geprüft: ein so erzeugtes `WindowsPath` meldet
selbst für einen wirklich vorhandenen Pfad `exists() == False`). Eine reine, kontrollierte
Path-Attrappe (`_FakePfad`/`_pfad_attrappe` unten) umgeht dieses Cross-Flavour-Problem und
macht die Tests unabhängig vom tatsächlich ausführenden Betriebssystem — echtes Dateisystem
bleibt in dieser Datei komplett unberührt.

Plattformneutral (Spec-Vorgabe Phase 71D — diese Datei läuft künftig auch im
`backend-windows`-CI-Job): JEDER Test setzt `os.name` EXPLIZIT per Monkeypatch, statt sich auf
den tatsächlichen Wert des Test-Runners zu verlassen.

App-Module (`pipeline.cv_export`) werden laut conftest.py-Konvention funktionslokal importiert,
nie auf Modulebene.
"""
import os


class _FakePfad:
    """Ersetzt eine `pathlib.Path`-Instanz für `_soffice_bin()`s Existenzprüfung — reine
    Attrappe, prüft nur gegen eine kontrollierte Menge "vorhandener" Werte (s. Moduldocstring
    für die Begründung, warum echtes `pathlib.Path` hier ungeeignet ist)."""

    def __init__(self, wert, vorhandene):
        self._wert = str(wert)
        self._vorhandene = vorhandene

    def exists(self):
        return self._wert in self._vorhandene


def _pfad_attrappe(vorhandene):
    """Fabrik für eine `Path`-Ersatzfunktion: nur die in `vorhandene` gelisteten (String-)Werte
    gelten als existent, alles andere nicht."""
    return lambda wert: _FakePfad(wert, vorhandene)


# ── Kandidatenliste je Plattform (reiner Tupel-Vergleich, kein Path-Zugriff) ────────────────
def test_soffice_kandidaten_posix_liefert_unveraendertes_bestandstupel(monkeypatch):
    """Kern-Regression (Spec-Vorgabe "Verhalten auf macOS unverändert"): auf Nicht-Windows
    liefert `_soffice_kandidaten()` exakt das alte `_SOFFICE_CANDIDATES`-Tupel, unverändert in
    Inhalt UND Reihenfolge — `os.name` explizit auf "posix" gepinnt, unabhängig vom
    tatsächlichen Runner-Betriebssystem."""
    from pipeline import cv_export

    monkeypatch.setattr(os, "name", "posix")

    assert cv_export._soffice_kandidaten() == cv_export._SOFFICE_CANDIDATES
    assert cv_export._soffice_kandidaten() == (
        "/opt/homebrew/bin/soffice",
        "/usr/local/bin/soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    )


def test_soffice_kandidaten_windows_liefert_windows_liste(monkeypatch):
    """Neue Windows-Liste (Spec-Vorgabe): 64-Bit "Program Files" zuerst, dann die
    "Program Files (x86)"-Variante — exakte Pfade laut Spec Phase 71D."""
    from pipeline import cv_export

    monkeypatch.setattr(os, "name", "nt")

    assert cv_export._soffice_kandidaten() == cv_export._SOFFICE_CANDIDATES_WINDOWS
    assert cv_export._soffice_kandidaten() == (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    )


# ── _soffice_bin(): Windows-Zweig ───────────────────────────────────────────────────────────
def test_soffice_bin_windows_findet_ersten_vorhandenen_kandidaten(monkeypatch):
    """Erster Kandidat fehlt, zweiter ist "vorhanden" — `_soffice_bin()` muss den ersten
    TATSÄCHLICH VORHANDENEN liefern, PATH wird gar nicht erst gefragt (`shutil.which` auf einen
    Kanarienvogel-Wert gemockt, der NIE aufgerufen werden darf)."""
    from pipeline import cv_export

    monkeypatch.setattr(os, "name", "nt")
    fehlend = r"C:\Program Files\LibreOffice\program\soffice.exe"
    vorhanden = r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"
    monkeypatch.setattr(cv_export, "_SOFFICE_CANDIDATES_WINDOWS", (fehlend, vorhanden))
    monkeypatch.setattr(cv_export, "Path", _pfad_attrappe({vorhanden}))

    def _which_darf_nicht_gerufen_werden(name):
        raise AssertionError("PATH haette hier nicht gefragt werden duerfen")

    monkeypatch.setattr(cv_export.shutil, "which", _which_darf_nicht_gerufen_werden)

    assert cv_export._soffice_bin() == vorhanden


def test_soffice_bin_windows_bevorzugt_ersten_kandidaten_wenn_beide_da_sind(monkeypatch):
    """Reihenfolge-Beweis: existieren BEIDE Windows-Kandidaten, gewinnt der ERSTE (64-Bit
    "Program Files" vor der 32-Bit-"(x86)"-Variante) — die Liste ist nach Priorität sortiert,
    nicht nur nach Existenz."""
    from pipeline import cv_export

    monkeypatch.setattr(os, "name", "nt")
    erster = r"C:\Program Files\LibreOffice\program\soffice.exe"
    zweiter = r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"
    monkeypatch.setattr(cv_export, "_SOFFICE_CANDIDATES_WINDOWS", (erster, zweiter))
    monkeypatch.setattr(cv_export, "Path", _pfad_attrappe({erster, zweiter}))

    assert cv_export._soffice_bin() == erster


def test_soffice_bin_windows_ohne_kandidat_faellt_auf_path_zurueck(monkeypatch):
    """Kein fester Kandidat vorhanden → Fallback auf PATH (`shutil.which`), wie im Bestand."""
    from pipeline import cv_export

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(cv_export, "_SOFFICE_CANDIDATES_WINDOWS",
                         (r"C:\a\soffice.exe", r"C:\b\soffice.exe"))
    monkeypatch.setattr(cv_export, "Path", _pfad_attrappe(set()))
    monkeypatch.setattr(cv_export.shutil, "which",
                         lambda name: r"C:\PATH\soffice.exe" if name == "soffice" else None)

    assert cv_export._soffice_bin() == r"C:\PATH\soffice.exe"


def test_soffice_bin_windows_kein_kandidat_kein_path_liefert_none(monkeypatch):
    """Weder fester Kandidat noch PATH-Treffer → None (Aufrufer `to_pdf()`/`_to_pdf_soffice()`
    meldet dann den bestehenden "LibreOffice nicht gefunden"-Fehler, unverändert)."""
    from pipeline import cv_export

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(cv_export, "_SOFFICE_CANDIDATES_WINDOWS", (r"C:\a\soffice.exe",))
    monkeypatch.setattr(cv_export, "Path", _pfad_attrappe(set()))
    monkeypatch.setattr(cv_export.shutil, "which", lambda name: None)

    assert cv_export._soffice_bin() is None


# ── _soffice_bin(): POSIX-Zweig bleibt wie bisher ───────────────────────────────────────────
def test_soffice_bin_posix_bevorzugt_festen_pfad_vor_path_wie_bisher(monkeypatch):
    """Regression des BESTEHENDEN Verhaltens (Beleg für "Verhalten auf macOS unverändert"): ein
    vorhandener fester Kandidat gewinnt gegen PATH, auch wenn PATH ebenfalls einen soffice
    liefern würde — exakt wie vor Phase 71D."""
    from pipeline import cv_export

    monkeypatch.setattr(os, "name", "posix")
    fester_pfad = "/opt/homebrew/bin/soffice"
    monkeypatch.setattr(cv_export, "_SOFFICE_CANDIDATES",
                         (fester_pfad, "/usr/local/bin/soffice",
                          "/Applications/LibreOffice.app/Contents/MacOS/soffice"))
    monkeypatch.setattr(cv_export, "Path", _pfad_attrappe({fester_pfad}))
    monkeypatch.setattr(cv_export.shutil, "which", lambda name: "/pfad/aus/PATH/soffice")

    assert cv_export._soffice_bin() == fester_pfad


def test_soffice_bin_posix_ohne_kandidat_faellt_auf_path_zurueck(monkeypatch):
    """Regression: kein fester Kandidat vorhanden → PATH-Fallback, wie im Bestand vor 71D."""
    from pipeline import cv_export

    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(cv_export, "_SOFFICE_CANDIDATES", ("/nope1/soffice", "/nope2/soffice"))
    monkeypatch.setattr(cv_export, "Path", _pfad_attrappe(set()))
    monkeypatch.setattr(cv_export.shutil, "which",
                         lambda name: "/pfad/aus/PATH/soffice" if name == "soffice" else None)

    assert cv_export._soffice_bin() == "/pfad/aus/PATH/soffice"
