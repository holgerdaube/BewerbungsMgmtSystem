"""Tests fuer scripts/bms_update.py (P2-51, Arbeitspaket U1 -- das Update-Werkzeug beim Kunden).

Das Skript importiert NICHTS aus app/pipeline (es laeuft neben einer halb ersetzten
Installation) -- diese Testdatei tut das konsequent auch nicht: sie laedt scripts/bms_update.py
per `importlib.util.spec_from_file_location` (wie ein ganz normales, App-unabhaengiges Modul)
und baut ihre eigenen Kunden-ZIPs + Installationsordner unter `tmp_path` nach, statt auf
`pipeline.kundenpaket` zurueckzugreifen (das Manifestformat V3 ist der gemeinsame Vertrag, s.
Bau-Spec -- kundenpaket.py liefert es zum Zeitpunkt dieser Arbeit noch nicht, U2a baut das
parallel). Die echte Installation (data/, outputs/, config/, ~/.bewerbung_mgmt_*,
~/Downloads) wird NIE beruehrt: jeder Test arbeitet in `tmp_path`, HOME/USERPROFILE werden fuer
die Download-Suche gemockt, und die venv-/Server-Pruefungen laufen ueber gezielt monkeypatchbare
Hilfsfunktionen statt ueber den echten Hostzustand (s. `_sichere_grundannahmen` unten).
"""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import zipfile
from hashlib import sha256
from pathlib import Path

import pytest

_PROJEKT_ROOT = Path(__file__).resolve().parent.parent.parent
_SKRIPT_PFAD = _PROJEKT_ROOT / "scripts" / "bms_update.py"


def _lade_bms_update():
    spec = importlib.util.spec_from_file_location("bms_update_unter_test", _SKRIPT_PFAD)
    modul = importlib.util.module_from_spec(spec)
    # VOR exec_module in sys.modules eintragen: dataclasses.dataclass() loest bei "from
    # __future__ import annotations" Typ-Strings ueber sys.modules[cls.__module__] auf (Python
    # 3.12-Interna) -- ohne den Eintrag schlaegt schon der Modul-Import mit einem
    # AttributeError auf None fehl, lange bevor irgendein Test laeuft.
    sys.modules[spec.name] = modul
    spec.loader.exec_module(modul)
    return modul


bms_update = _lade_bms_update()
_EIGENES_SKRIPT = _SKRIPT_PFAD.read_bytes()
# Referenz auf die UNGEPATCHTE Funktion, festgehalten VOR der autouse-Fixture unten (die
# bms_update._laeuft_nicht_in_venv() fuer alle anderen Tests durch ein Lambda ersetzt) -- der
# eine Test, der die echte sys.prefix-Logik selbst beweist, braucht die Originalfunktion.
_ECHTES_LAEUFT_NICHT_IN_VENV = bms_update._laeuft_nicht_in_venv


# ── Autouse-Grundannahmen ────────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _bms_data_dir_zuruecksetzen(monkeypatch):
    """conftest.py setzt BMS_DATA_DIR fuer die GESAMTE Pytest-Session (schuetzt die echte
    data/bewerbung.sqlite, s. dortiger Docstring) -- bms_update.py._data_dir() wuerde diesen Wert
    sonst uebernehmen und ALLE Tests hier in denselben, sessionweiten Ordner schreiben lassen statt
    in ihr eigenes tmp_path. Diese Testdatei ist komplett app/pipeline-unabhaengig, die Variable
    also irrelevant -- geloescht faellt `_data_dir()` auf ihren dokumentierten Normalfall zurueck:
    <installation>/data."""
    monkeypatch.delenv("BMS_DATA_DIR", raising=False)


@pytest.fixture(autouse=True)
def _sichere_grundannahmen(monkeypatch):
    """Alle Tests laufen automatisch 'in einer venv' und 'ohne laufenden BMS-Server' -- die
    Testsuite selbst laeuft in CI ggf. OHNE echte venv (s. bms_update.py::_laeuft_nicht_in_venv)
    und ein echter Netzwerk-Call waere ein T4-Verstoss. Der jeweils EINE Test, der genau diese
    Grundannahme widerlegt, hebt den Patch gezielt wieder auf.

    P2-82: Auch die Online-Suche (Schritt 2) ist aus, damit KEIN bestehender Test je GitHub
    anspricht. Die Faelle mit Probeserver stehen in test_bms_update_github.py."""
    monkeypatch.setattr(bms_update, "_laeuft_nicht_in_venv", lambda: False)
    monkeypatch.setattr(bms_update, "_server_laeuft", lambda port=None: False)
    monkeypatch.setattr(bms_update, "_online_suchen",
                        lambda *a, **k: (None, "Online-Suche in diesem Test abgeschaltet."))


# ── Bau-Hilfsfunktionen (Manifest V3, Paket, Installation) ──────────────────────────────────
def _sha256(daten: bytes) -> str:
    return sha256(daten).hexdigest()


def _manifest_bauen(version: str, dateien: dict[str, bytes], *, anpassbar=(), vorschau=False,
                     freigabe=True, ausfuehrbare: frozenset[str] = frozenset()) -> dict:
    return {
        "anpassbar": list(anpassbar),
        "commit": "a" * 40,
        "commit_datum": "2026-09-28",
        "dateien": {
            pfad: {"ausfuehrbar": pfad in ausfuehrbare, "groesse": len(inhalt), "sha256": _sha256(inhalt)}
            for pfad, inhalt in dateien.items()
        },
        "format": 1,
        "freigabe": freigabe,
        "produkt": "Bewerbungs-Management-System",
        "version": version,
        "vorschau": vorschau,
    }


def _paket_bauen(ziel_ordner: Path, dateiname: str, version: str, dateien: dict[str, bytes],
                  **kwargs) -> Path:
    manifest = _manifest_bauen(version, dateien, **kwargs)
    zip_pfad = ziel_ordner / dateiname
    with zipfile.ZipFile(zip_pfad, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("bms_manifest.json",
                     json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        for pfad, inhalt in dateien.items():
            zf.writestr(pfad, inhalt)
    return zip_pfad


def _zip_eintrag_ersetzen(zip_pfad: Path, name: str, neuer_inhalt: bytes) -> None:
    with zipfile.ZipFile(zip_pfad) as zf:
        eintraege = {info.filename: zf.read(info.filename) for info in zf.infolist()}
    eintraege[name] = neuer_inhalt
    with zipfile.ZipFile(zip_pfad, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, inhalt in eintraege.items():
            zf.writestr(n, inhalt)


def _installation_bauen(tmp_path: Path, ordnername: str, version: str, dateien: dict[str, bytes],
                         *, anpassbar=(), mit_manifest: bool = True,
                         ausfuehrbare: frozenset[str] = frozenset(),
                         mit_frontend_platzhalter: bool = True) -> Path:
    installation = tmp_path / ordnername
    installation.mkdir(parents=True, exist_ok=True)
    for pfad, inhalt in dateien.items():
        ziel = installation / pfad
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(inhalt)
        if pfad in ausfuehrbare and os.name != "nt":
            ziel.chmod(0o755)
    if mit_manifest:
        manifest = _manifest_bauen(version, dateien, anpassbar=anpassbar, ausfuehrbare=ausfuehrbare)
        (installation / "bms_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    if mit_frontend_platzhalter and "frontend/dist/index.html" not in dateien:
        # Verhindert, dass Tests ausserhalb der Abhaengigkeiten-Faelle an "build_noetig" (fehlendes
        # dist/) bzw. an einem fehlenden echten npm auf dem Test-Runner scheitern -- s. Moduldoc.
        (installation / "frontend" / "dist").mkdir(parents=True, exist_ok=True)
        (installation / "frontend" / "dist" / "index.html").write_bytes(b"<html></html>")
    return installation


def _verzeichnis_hashes(basis: Path, *, ausschluss=("data",)) -> dict[str, str]:
    ergebnis = {}
    for pfad in basis.rglob("*"):
        if pfad.is_file():
            rel = pfad.relative_to(basis)
            if rel.parts and rel.parts[0] in ausschluss:
                continue
            ergebnis[str(rel)] = _sha256(pfad.read_bytes())
    return ergebnis


GRUNDDATEIEN = {
    "scripts/bms_update.py": _EIGENES_SKRIPT,
    "backend/requirements-lock.txt": b"fastapi==1.0.0\n",
    "frontend/package-lock.json": b"{}\n",
}


def _bericht_lesen(installation: Path) -> dict:
    """Neuester (per Ordnername sortiert) bericht.json unter data/updates/."""
    ordner = sorted((installation / "data" / "updates").iterdir())
    ordner = [o for o in ordner if o.is_dir()]
    return json.loads((ordner[-1] / "bericht.json").read_text(encoding="utf-8"))


# ── Schritt 1: Installation pruefen ─────────────────────────────────────────────────────────
def test_installation_pruefen_bricht_bei_fehlendem_ordner_ab(tmp_path):
    with pytest.raises(bms_update.Abbruch):
        bms_update._installation_pruefen(tmp_path / "existiert_nicht")


def test_installation_pruefen_bricht_bei_git_ordner_ab(tmp_path):
    installation = tmp_path / "BMS"
    installation.mkdir()
    (installation / ".git").mkdir()
    with pytest.raises(bms_update.Abbruch) as exc:
        bms_update._installation_pruefen(installation)
    assert "Git" in exc.value.nachricht


def test_installation_pruefen_bricht_bei_git_zeigerdatei_ab(tmp_path):
    """`.git` ist bei einem Worktree-Checkout eine Zeiger-DATEI, kein Ordner -- die Pruefung muss
    BEIDE Formen erkennen (s. backend/pipeline/kundenpaket.py::_git fuer denselben Sonderfall).
    Niemals das Werkzeug gegen den echten Projektordner laufen lassen: dieser Test beweist den
    Abbruch stellvertretend an einer FAKE-Installation in tmp_path."""
    installation = tmp_path / "BMS"
    installation.mkdir()
    (installation / ".git").write_text("gitdir: ../anderswo/.git\n", encoding="utf-8")
    with pytest.raises(bms_update.Abbruch):
        bms_update._installation_pruefen(installation)


def test_installation_pruefen_bricht_ohne_venv_ab(tmp_path, monkeypatch):
    monkeypatch.setattr(bms_update, "_laeuft_nicht_in_venv", lambda: True)
    installation = tmp_path / "BMS"
    installation.mkdir()
    with pytest.raises(bms_update.Abbruch) as exc:
        bms_update._installation_pruefen(installation)
    assert "Python-Umgebung" in exc.value.nachricht


def test_laeuft_nicht_in_venv_spiegelt_sys_prefix(monkeypatch):
    monkeypatch.setattr(sys, "base_prefix", "/gleich")
    monkeypatch.setattr(sys, "prefix", "/gleich")
    assert _ECHTES_LAEUFT_NICHT_IN_VENV() is True
    monkeypatch.setattr(sys, "prefix", "/venv")
    assert _ECHTES_LAEUFT_NICHT_IN_VENV() is False


# ── Schritt 2: Paket finden ──────────────────────────────────────────────────────────────────
def test_paket_suche_findet_hoechste_version_im_download_ordner(tmp_path, monkeypatch):
    downloads = tmp_path / "home" / "Downloads"
    downloads.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))

    _paket_bauen(downloads, "BMS_1.0.0.zip", "1.0.0", GRUNDDATEIEN)
    hoechstes = _paket_bauen(downloads, "BMS_1.2.0.zip", "1.2.0", GRUNDDATEIEN)
    _paket_bauen(downloads, "BMS_1.1.0.zip", "1.1.0", GRUNDDATEIEN)

    assert bms_update._paket_finden(None) == hoechstes


def test_paket_suche_ohne_treffer_nennt_download_ordner(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    with pytest.raises(bms_update.Abbruch) as exc:
        bms_update._paket_finden(None)
    assert "Download" in exc.value.nachricht


def test_paket_suche_mit_explizitem_pfad_ignoriert_downloads(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "leer"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "leer"))
    eigenes = _paket_bauen(tmp_path, "irgendwo.zip", "1.0.0", GRUNDDATEIEN)
    assert bms_update._paket_finden(str(eigenes)) == eigenes


def test_paket_suche_mit_fehlendem_explizitem_pfad_bricht_ab(tmp_path):
    with pytest.raises(bms_update.Abbruch):
        bms_update._paket_finden(str(tmp_path / "nicht_da.zip"))


# ── Schritt 4: Paket pruefen ──────────────────────────────────────────────────────────────────
def test_paket_pruefen_akzeptiert_gueltiges_paket(tmp_path):
    paket = _paket_bauen(tmp_path, "BMS_1.0.0.zip", "1.0.0", GRUNDDATEIEN)
    manifest = bms_update._paket_lesen_und_pruefen(paket)
    assert manifest["version"] == "1.0.0"


def test_paket_pruefen_erkennt_kaputtes_zip(tmp_path):
    kaputt = tmp_path / "kaputt.zip"
    kaputt.write_bytes(b"das ist kein zip")
    with pytest.raises(bms_update.Abbruch):
        bms_update._paket_lesen_und_pruefen(kaputt)


def test_paket_pruefen_erkennt_falsche_pruefsumme(tmp_path):
    paket = _paket_bauen(tmp_path, "BMS_1.0.0.zip", "1.0.0",
                          {**GRUNDDATEIEN, "backend/x.py": b"original8\n"})
    # Gleiche Laenge wie das Original (10 Bytes) -- sonst schlaegt schon die Groessen-Pruefung
    # an, nicht die hier gezielt getestete Pruefsummen-Pruefung.
    _zip_eintrag_ersetzen(paket, "backend/x.py", b"manipulrt\n")
    with pytest.raises(bms_update.Abbruch) as exc:
        bms_update._paket_lesen_und_pruefen(paket)
    assert "Prüfsumme" in exc.value.nachricht


def test_paket_pruefen_erkennt_falsche_groesse(tmp_path):
    paket = _paket_bauen(tmp_path, "BMS_1.0.0.zip", "1.0.0",
                          {**GRUNDDATEIEN, "backend/x.py": b"original\n"})
    _zip_eintrag_ersetzen(paket, "backend/x.py", b"ein ganz anderer, laengerer Inhalt\n")
    with pytest.raises(bms_update.Abbruch) as exc:
        bms_update._paket_lesen_und_pruefen(paket)
    assert "Größe" in exc.value.nachricht


def test_paket_pruefen_erkennt_unerwarteten_eintrag(tmp_path):
    paket = _paket_bauen(tmp_path, "BMS_1.0.0.zip", "1.0.0", GRUNDDATEIEN)
    with zipfile.ZipFile(paket, "a") as zf:
        zf.writestr("nicht_im_manifest.txt", b"ueberraschung\n")
    with pytest.raises(bms_update.Abbruch) as exc:
        bms_update._paket_lesen_und_pruefen(paket)
    assert "unerwartete" in exc.value.nachricht.lower()


@pytest.mark.parametrize("unsicherer_pfad", ["../evil.txt", "/etc/passwd", "a\\b.txt", "C:/x.txt"])
def test_paket_pruefen_lehnt_unsichere_pfade_ab(tmp_path, unsicherer_pfad):
    paket = _paket_bauen(tmp_path, "BMS_1.0.0.zip", "1.0.0", {unsicherer_pfad: b"boese\n"})
    with pytest.raises(bms_update.Abbruch) as exc:
        bms_update._paket_lesen_und_pruefen(paket)
    assert "unsicher" in exc.value.nachricht.lower()


@pytest.mark.parametrize("geschuetzter_pfad", [
    "data/bewerbung.sqlite", "outputs/cv/x.docx", "config/profil.md",
    "config/suchprofile.yaml", "config/zielfirmen.md", "config/budgets.yaml",
    "frontend/node_modules/x.js", "frontend/dist/index.html", ".git/HEAD",
])
def test_paket_pruefen_lehnt_geschuetzte_pfade_ab(tmp_path, geschuetzter_pfad):
    paket = _paket_bauen(tmp_path, "BMS_1.0.0.zip", "1.0.0", {geschuetzter_pfad: b"x\n"})
    with pytest.raises(bms_update.Abbruch) as exc:
        bms_update._paket_lesen_und_pruefen(paket)
    assert "geschützt" in exc.value.nachricht.lower()


def test_vorschau_paket_ohne_erzwingen_wird_abgelehnt():
    with pytest.raises(bms_update.Abbruch):
        bms_update._paket_gegen_installation_pruefen({"vorschau": True, "version": "1.0.0"}, None, False)


def test_vorschau_paket_mit_erzwingen_geht_durch():
    bms_update._paket_gegen_installation_pruefen({"vorschau": True, "version": "1.0.0"}, None, True)


def test_gleiche_version_ohne_erzwingen_wird_abgelehnt():
    with pytest.raises(bms_update.Abbruch):
        bms_update._paket_gegen_installation_pruefen({"vorschau": False, "version": "1.0.0"}, "1.0.0", False)


def test_aeltere_version_ohne_erzwingen_wird_abgelehnt():
    with pytest.raises(bms_update.Abbruch):
        bms_update._paket_gegen_installation_pruefen({"vorschau": False, "version": "1.0.0"}, "1.1.0", False)


def test_version_pruefung_mit_erzwingen_geht_immer_durch():
    bms_update._paket_gegen_installation_pruefen({"vorschau": False, "version": "1.0.0"}, "1.2.0", True)


def test_neuere_version_ohne_installierte_version_wird_akzeptiert():
    bms_update._paket_gegen_installation_pruefen({"vorschau": False, "version": "1.0.0"}, None, False)


# ── Schritt 5: laufender Server ───────────────────────────────────────────────────────────────
def test_laufender_server_bricht_ab_ohne_aenderung(tmp_path, monkeypatch):
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", GRUNDDATEIEN)
    paket = _paket_bauen(tmp_path, "BMS_1.1.0.zip", "1.1.0",
                          {**GRUNDDATEIEN, "backend/app/main.py": b"neu\n"})
    monkeypatch.setattr(bms_update, "_server_laeuft", lambda port=None: True)

    vorher = _verzeichnis_hashes(installation)
    code = bms_update.main([str(paket), "--installation", str(installation), "--ja",
                             "--ohne-abhaengigkeiten", "--ohne-selbsttest"])
    assert code == bms_update.EXIT_ABGEBROCHEN
    assert _verzeichnis_hashes(installation) == vorher


# ── --pruefen ─────────────────────────────────────────────────────────────────────────────────
def test_pruefen_aendert_nichts(tmp_path, capsys):
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", GRUNDDATEIEN)
    paket = _paket_bauen(tmp_path, "BMS_1.1.0.zip", "1.1.0",
                          {**GRUNDDATEIEN, "backend/app/main.py": b"neu\n"})
    vorher = _verzeichnis_hashes(installation)

    code = bms_update.main([str(paket), "--installation", str(installation), "--pruefen"])

    assert code == bms_update.EXIT_OK
    assert _verzeichnis_hashes(installation) == vorher
    ausgabe = capsys.readouterr().out
    assert "1.0.0" in ausgabe and "1.1.0" in ausgabe
    assert not (installation / "data").exists()  # nicht mal der Sicherungsordner entsteht


# ── Aufruf falsch ─────────────────────────────────────────────────────────────────────────────
def test_main_ohne_installation_argument_ist_aufruf_fehler():
    assert bms_update.main(["--ja"]) == bms_update.EXIT_AUFRUF_FALSCH


# ── Sperrdatei ────────────────────────────────────────────────────────────────────────────────
def test_bestehende_sperre_verhindert_update(tmp_path):
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", GRUNDDATEIEN)
    paket = _paket_bauen(tmp_path, "BMS_1.1.0.zip", "1.1.0",
                          {**GRUNDDATEIEN, "backend/app/main.py": b"neu\n"})
    sperr_ordner = installation / "data" / "updates"
    sperr_ordner.mkdir(parents=True)
    (sperr_ordner / bms_update.SPERR_NAME).touch()

    vorher = _verzeichnis_hashes(installation)
    code = bms_update.main([str(paket), "--installation", str(installation), "--ja",
                             "--ohne-abhaengigkeiten", "--ohne-selbsttest"])
    assert code == bms_update.EXIT_ABGEBROCHEN
    assert _verzeichnis_hashes(installation) == vorher


# ── Rueckfrage ────────────────────────────────────────────────────────────────────────────────
def test_rueckfrage_nein_bricht_ohne_aenderung_ab(tmp_path, monkeypatch):
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", GRUNDDATEIEN)
    paket = _paket_bauen(tmp_path, "BMS_1.1.0.zip", "1.1.0",
                          {**GRUNDDATEIEN, "backend/app/main.py": b"neu\n"})
    monkeypatch.setattr(bms_update, "_rueckfrage", lambda frage: False)

    vorher = _verzeichnis_hashes(installation)
    code = bms_update.main([str(paket), "--installation", str(installation),
                             "--ohne-abhaengigkeiten", "--ohne-selbsttest"])
    assert code == bms_update.EXIT_ABGEBROCHEN
    assert _verzeichnis_hashes(installation) == vorher


# ── Dateiregeln: alle acht Zeilen der Tabelle in einem Durchlauf ────────────────────────────
def test_dateiregeln_alle_zeilen_der_tabelle(tmp_path):
    anpassbar_muster = (".claude/agents/beirat-*.md", "config/profil_struktur.md")

    alte_dateien = {
        **GRUNDDATEIEN,
        "backend/app/main.py": b"v1 main\n",                       # Zeile 1 (lokal=alt)
        "backend/app/edited.py": b"v1 edited\n",                   # Zeile 2 (lokal!=alt, nicht anpassbar)
        "backend/app/deleted_by_user.py": b"v1 wird geloescht\n",  # Zeile 3 (lokal fehlt)
        "backend/app/removed_in_v2.py": b"v1 wird entfernt\n",     # Zeile 4 (nicht anpassbar)
        ".claude/agents/beirat-customized.md": b"v1 persona\n",    # Zeile 4 anpassbar (lokal!=alt -> behalten)
        ".claude/agents/beirat-untouched.md": b"v1 unveraendert\n",  # Zeile 1 anpassbar (lokal=alt -> ersetzen)
        ".claude/agents/beirat-vanished.md": b"v1 wird geloescht\n",  # Zeile 3 anpassbar (nicht wieder anlegen)
        ".claude/agents/beirat-edited.md": b"v1 edited-persona\n",  # Zeile 2 anpassbar (behalten + neue Fassung)
    }
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", alte_dateien, anpassbar=anpassbar_muster)

    # Lokalen Stand nach "Kundennutzung" herstellen, bevor das Update laeuft:
    (installation / "backend/app/edited.py").write_bytes(b"KUNDE hat das editiert\n")
    (installation / "backend/app/deleted_by_user.py").unlink()
    (installation / ".claude/agents/beirat-customized.md").write_bytes(b"KUNDE hat die Persona geaendert\n")
    (installation / ".claude/agents/beirat-vanished.md").unlink()
    (installation / ".claude/agents/beirat-edited.md").write_bytes(b"KUNDE editiert diese Persona auch\n")
    # Kollision: ein Pfad, den der KUNDE schon hat, der aber im alten Manifest NICHT vorkam.
    (installation / "backend/app/collide.py").write_bytes(b"kollidierende lokale Datei\n")

    neue_dateien = {
        **GRUNDDATEIEN,
        "backend/app/main.py": b"v2 main\n",                        # Zeile 1
        "backend/app/edited.py": b"v2 edited\n",                    # Zeile 2
        "backend/app/deleted_by_user.py": b"v2 wiederhergestellt\n",  # Zeile 3
        # "backend/app/removed_in_v2.py" entfaellt -> Zeile 4
        "backend/app/new_feature.py": b"v2 ganz neu\n",             # Zeile 5
        "backend/app/collide.py": b"v2 kollidiert mit Kundendatei\n",  # Zeile 6
        ".claude/agents/beirat-customized.md": b"v2 persona\n",     # Zeile 4 anpassbar
        ".claude/agents/beirat-untouched.md": b"v2 unveraendert\n",  # Zeile 1 anpassbar
        ".claude/agents/beirat-vanished.md": b"v2 persona weiter im Produkt\n",  # Zeile 3 anpassbar
        ".claude/agents/beirat-edited.md": b"v2 persona-update\n",  # Zeile 2 anpassbar
        "config/profil_struktur.md": b"v2 struktur (neu im Paket)\n",  # Zeile 6 anpassbar
    }
    (installation / "config").mkdir(exist_ok=True)
    (installation / "config" / "profil_struktur.md").write_bytes(b"KUNDE hat eigene Struktur\n")

    paket = _paket_bauen(tmp_path, "BMS_1.1.0.zip", "1.1.0", neue_dateien, anpassbar=anpassbar_muster)

    code = bms_update.main([str(paket), "--installation", str(installation), "--ja",
                             "--ohne-abhaengigkeiten", "--ohne-selbsttest"])
    assert code == bms_update.EXIT_OK

    def inhalt(pfad: str) -> bytes:
        return (installation / pfad).read_bytes()

    # Zeile 1: unveraendert -> ersetzt (beide Varianten).
    assert inhalt("backend/app/main.py") == b"v2 main\n"
    assert inhalt(".claude/agents/beirat-untouched.md") == b"v2 unveraendert\n"

    # Zeile 2 nicht anpassbar: Kundenaenderung gesichert, dann ersetzt.
    assert inhalt("backend/app/edited.py") == b"v2 edited\n"
    # Zeile 2 anpassbar: Kundenfassung bleibt, neue Fassung liegt zum Nachschlagen bereit.
    assert inhalt(".claude/agents/beirat-edited.md") == b"KUNDE editiert diese Persona auch\n"

    # Zeile 3 nicht anpassbar: vom Kunden geloeschte Programmdatei wird wiederhergestellt.
    assert inhalt("backend/app/deleted_by_user.py") == b"v2 wiederhergestellt\n"
    # Zeile 3 anpassbar: bleibt geloescht (nicht wieder angelegt).
    assert not (installation / ".claude/agents/beirat-vanished.md").exists()

    # Zeile 4 nicht anpassbar: aus dem Produkt entfernt -> Datei weg.
    assert not (installation / "backend/app/removed_in_v2.py").exists()
    # Zeile 4 anpassbar, vom Kunden veraendert -> bleibt trotz Entfernung aus dem Produkt.
    assert inhalt(".claude/agents/beirat-customized.md") == b"KUNDE hat die Persona geaendert\n"

    # Zeile 5: ganz neu, lokal gab es nichts.
    assert inhalt("backend/app/new_feature.py") == b"v2 ganz neu\n"

    # Zeile 6 nicht anpassbar: neu im Paket, kollidierende lokale Datei wird gesichert+ersetzt.
    assert inhalt("backend/app/collide.py") == b"v2 kollidiert mit Kundendatei\n"
    # Zeile 6 anpassbar: neu im Paket, Kundenfassung bleibt, neue Fassung nur abgelegt.
    assert inhalt("config/profil_struktur.md") == b"KUNDE hat eigene Struktur\n"

    # Zeile 8 (implizit): unveraendertes GRUNDDATEIEN-requirements-lock.txt wurde NICHT als
    # "geaendert" gemeldet (echter No-op).
    bericht = _bericht_lesen(installation)
    assert "backend/requirements-lock.txt" not in bericht["geaendert"]

    # Report-Stichproben. "deleted_by_user.py" ist bucket "neu" (nicht "geaendert"): ohne lokale
    # Vorlage entsteht KEINE Sicherung unter dateien/ -- ein spaeteres --zurueck muss den Pfad
    # ueber bericht["neu"] wieder loeschen koennen (Nachbesserung Abnahme P2-51).
    assert set(bericht["neu"]) >= {"backend/app/new_feature.py", "backend/app/collide.py",
                                    "backend/app/deleted_by_user.py"}
    assert set(bericht["geaendert"]) >= {"backend/app/main.py", "backend/app/edited.py",
                                          ".claude/agents/beirat-untouched.md"}
    assert set(bericht["entfernt"]) == {"backend/app/removed_in_v2.py"}
    assert "backend/app/edited.py" in bericht["lokal_geaendert_gesichert"]
    assert set(bericht["anpassbar_behalten"]) == {
        ".claude/agents/beirat-customized.md", ".claude/agents/beirat-edited.md",
        "config/profil_struktur.md",
    }
    assert any("beirat-vanished" in h for h in bericht["hinweise"])

    # Neues Manifest ist jetzt die installierte Version.
    neues_manifest = json.loads((installation / "bms_manifest.json").read_text(encoding="utf-8"))
    assert neues_manifest["version"] == "1.1.0"

    # Sicherungsordner enthaelt die vorherigen Fassungen und die neuen Fassungen zum Nachschlagen.
    sicherung_ordner = [p for p in (installation / "data" / "updates").iterdir() if p.is_dir()][0]
    assert (sicherung_ordner / "dateien" / "backend" / "app" / "edited.py").read_bytes() == b"KUNDE hat das editiert\n"
    assert (sicherung_ordner / "neue_fassungen" / "config" / "profil_struktur.md").read_bytes() \
        == b"v2 struktur (neu im Paket)\n"
    assert (sicherung_ordner / "bms_manifest.alt.json").is_file()


def test_kein_altes_manifest_zeile7(tmp_path):
    """Zeile "kein altes Manifest": eine Installation von VOR dieser Funktion (kein
    bms_manifest.json) bekommt trotzdem ein korrektes erstes Update."""
    anpassbar_muster = ("config/scoring_rubrik.md",)
    alte_dateien = {
        **GRUNDDATEIEN,
        "backend/app/main.py": b"vorher\n",
        "config/scoring_rubrik.md": b"eigene rubrik des kunden\n",
    }
    installation = _installation_bauen(tmp_path, "BMS", "0.0.0", alte_dateien, mit_manifest=False)

    neue_dateien = {
        **GRUNDDATEIEN,
        "backend/app/main.py": b"nachher\n",
        "config/scoring_rubrik.md": b"neue standard-rubrik\n",
        "backend/app/brandneu.py": b"ganz neue datei ohne lokale entsprechung\n",
    }
    paket = _paket_bauen(tmp_path, "BMS_1.0.0.zip", "1.0.0", neue_dateien, anpassbar=anpassbar_muster)

    code = bms_update.main([str(paket), "--installation", str(installation), "--ja",
                             "--ohne-abhaengigkeiten", "--ohne-selbsttest"])
    assert code == bms_update.EXIT_OK

    assert (installation / "backend/app/main.py").read_bytes() == b"nachher\n"
    assert (installation / "config/scoring_rubrik.md").read_bytes() == b"eigene rubrik des kunden\n"
    assert (installation / "backend/app/brandneu.py").read_bytes() \
        == b"ganz neue datei ohne lokale entsprechung\n"

    sicherung_ordner = [p for p in (installation / "data" / "updates").iterdir() if p.is_dir()][0]
    assert (sicherung_ordner / "neue_fassungen" / "config" / "scoring_rubrik.md").read_bytes() \
        == b"neue standard-rubrik\n"
    assert (sicherung_ordner / "dateien" / "backend" / "app" / "main.py").read_bytes() == b"vorher\n"

    # bucket-Stichprobe (Nachbesserung Abnahme P2-51): "brandneu.py" hatte KEINE lokale
    # Entsprechung -> bucket "neu" (keine Sicherung unter dateien/, --zurueck muss sie loeschen
    # koennen); "main.py" gab es lokal -> bucket "geaendert" (Sicherung existiert, --zurueck
    # stellt sie wieder her).
    bericht = _bericht_lesen(installation)
    assert "backend/app/brandneu.py" in bericht["neu"]
    assert "backend/app/main.py" in bericht["geaendert"]
    assert not (sicherung_ordner / "dateien" / "backend" / "app" / "brandneu.py").exists()


def test_anpassbare_datei_ohne_produktaenderung_bekommt_keine_neue_fassung(tmp_path):
    """Optionale Nachbesserung Abnahme P2-51: hat sich NUR die lokale (Kunden-)Kopie vom
    unveraenderten Original entfernt (alt == neu, das Produkt hat die Datei zwischen den
    Versionen also gar nicht geaendert), gibt es nichts Neues zum Nachschlagen --
    neue_fassungen/ bleibt fuer diesen Pfad leer, die Kundenfassung bleibt unangetastet."""
    anpassbar_muster = ("config/scoring_rubrik.md",)
    alte_dateien = {**GRUNDDATEIEN, "config/scoring_rubrik.md": b"standard rubrik\n"}
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", alte_dateien, anpassbar=anpassbar_muster)
    (installation / "config" / "scoring_rubrik.md").write_bytes(b"KUNDE hat eigene Kriterien\n")

    # Byte-identisch mit "alt": das Produkt hat diese Datei zwischen den Versionen NICHT
    # geaendert, nur der Kunde hat seine lokale Kopie angepasst.
    neue_dateien = {**GRUNDDATEIEN, "config/scoring_rubrik.md": b"standard rubrik\n"}
    paket = _paket_bauen(tmp_path, "BMS_1.1.0.zip", "1.1.0", neue_dateien, anpassbar=anpassbar_muster)

    code = bms_update.main([str(paket), "--installation", str(installation), "--ja",
                             "--ohne-abhaengigkeiten", "--ohne-selbsttest"])
    assert code == bms_update.EXIT_OK
    assert (installation / "config/scoring_rubrik.md").read_bytes() == b"KUNDE hat eigene Kriterien\n"

    sicherung_ordner = [p for p in (installation / "data" / "updates").iterdir() if p.is_dir()][0]
    assert not (sicherung_ordner / "neue_fassungen" / "config" / "scoring_rubrik.md").exists()


# ── Geschuetzte Pfade / Datenbank-Sicherung ─────────────────────────────────────────────────
def test_datenbank_wird_gesichert_und_nicht_veraendert(tmp_path):
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", GRUNDDATEIEN)
    db_pfad = installation / "data" / "bewerbung.sqlite"
    db_pfad.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_pfad))
    conn.execute("CREATE TABLE company (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO company (name) VALUES ('Muster GmbH')")
    conn.commit()
    conn.close()
    db_vorher = db_pfad.read_bytes()

    paket = _paket_bauen(tmp_path, "BMS_1.1.0.zip", "1.1.0",
                          {**GRUNDDATEIEN, "backend/app/main.py": b"neu\n"})
    code = bms_update.main([str(paket), "--installation", str(installation), "--ja",
                             "--ohne-abhaengigkeiten", "--ohne-selbsttest"])
    assert code == bms_update.EXIT_OK

    assert db_pfad.read_bytes() == db_vorher  # das Werkzeug fasst die LIVE-Datenbank nie an

    sicherung_ordner = [p for p in (installation / "data" / "updates").iterdir() if p.is_dir()][0]
    gesicherte_db = sicherung_ordner / "datenbank.sqlite"
    assert gesicherte_db.is_file()
    conn = sqlite3.connect(str(gesicherte_db))
    zeile = conn.execute("SELECT name FROM company").fetchone()
    conn.close()
    assert zeile == ("Muster GmbH",)


def test_paket_mit_geschuetztem_pfad_wird_gar_nicht_erst_eingespielt(tmp_path):
    """End-zu-Ende-Gegenprobe zur Manifest-Einzelpruefung oben: ein Paket, das versucht, eine
    geschuetzte Datei mitzuliefern, bricht VOR jeder Aenderung ab -- der Programmordner bleibt
    byte-gleich."""
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", GRUNDDATEIEN)
    vorher = _verzeichnis_hashes(installation)
    boesartig = {**GRUNDDATEIEN, "config/suchprofile.yaml": b"uebernommen\n"}
    paket = _paket_bauen(tmp_path, "BMS_1.1.0.zip", "1.1.0", boesartig)

    code = bms_update.main([str(paket), "--installation", str(installation), "--ja",
                             "--ohne-abhaengigkeiten", "--ohne-selbsttest"])
    assert code == bms_update.EXIT_ABGEBROCHEN
    assert _verzeichnis_hashes(installation) == vorher


# ── Fehler ab Schritt 10: vollstaendiges Zurueckrollen ──────────────────────────────────────
def test_fehler_in_abhaengigkeiten_rollt_vollstaendig_zurueck(tmp_path, monkeypatch):
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", GRUNDDATEIEN)
    neue_dateien = {
        **GRUNDDATEIEN,
        "backend/app/main.py": b"neu\n",
        "backend/requirements-lock.txt": b"fastapi==2.0.0\n",  # -> pip_noetig True
    }
    paket = _paket_bauen(tmp_path, "BMS_1.1.0.zip", "1.1.0", neue_dateien)
    vorher = _verzeichnis_hashes(installation)

    def _fehlschlagendes_pip(befehl, cwd, capture_output, text, timeout):
        import subprocess
        return subprocess.CompletedProcess(befehl, 1, stdout="", stderr="pip ist explodiert")

    monkeypatch.setattr(bms_update.subprocess, "run", _fehlschlagendes_pip)

    code = bms_update.main([str(paket), "--installation", str(installation), "--ja", "--ohne-selbsttest"])

    assert code == bms_update.EXIT_ZURUECKGEROLLT
    # Programmordner exakt wie vorher -- schliesst auch bms_manifest.json ein: die ALTE Fassung
    # (Version 1.0.0) blieb unangetastet, die NEUE wurde nie uebernommen (erst Schritt 13).
    assert _verzeichnis_hashes(installation) == vorher

    bericht = _bericht_lesen(installation)
    assert bericht["ergebnis"] == "zurueckgerollt"


def test_fehler_im_selbsttest_rollt_vollstaendig_zurueck(tmp_path, monkeypatch):
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", GRUNDDATEIEN)
    neue_dateien = {
        **GRUNDDATEIEN,
        "backend/app/main.py": b"neu\n",
        "backend/app/selbsttest.py": b"# platzhalter\n",
    }
    paket = _paket_bauen(tmp_path, "BMS_1.1.0.zip", "1.1.0", neue_dateien)
    vorher = _verzeichnis_hashes(installation)

    def _fehlschlagender_selbsttest(befehl, cwd, env, capture_output, text, timeout):
        import subprocess
        return subprocess.CompletedProcess(befehl, 1, stdout="Selbsttest fehlgeschlagen: X\n", stderr="")

    monkeypatch.setattr(bms_update.subprocess, "run", _fehlschlagender_selbsttest)

    code = bms_update.main([str(paket), "--installation", str(installation), "--ja",
                             "--ohne-abhaengigkeiten"])

    assert code == bms_update.EXIT_ZURUECKGEROLLT
    assert _verzeichnis_hashes(installation) == vorher

    bericht = _bericht_lesen(installation)
    assert bericht["ergebnis"] == "zurueckgerollt"


def test_fehler_mitten_in_dateien_schreiben_laesst_nie_erreichte_dateien_unangetastet(
        tmp_path, monkeypatch):
    """KRITISCHE Nachbesserung (Abnahme P2-51): schlaegt _atomar_schreiben() beim DRITTEN Aufruf
    fehl (z. B. PermissionError unter Windows bei gesperrter Datei, volle Platte), duerfen nur
    die PATHS, die _dateien_schreiben() wirklich schon angefasst hat, zurueckgerollt werden.

    Der urspruengliche Rollback ging stattdessen ueber ALLE Plan-Aktionen und nahm bei jeder
    ohne Sicherung an, sie sei "neu angelegt, also loeschen" -- das traf auch auf eine Datei zu,
    die schreiben() nie erreicht hatte (planmaessig "ersetzen", aber als VIERTER Schreibversuch
    alphabetisch NACH dem misslungenen dritten) und die deshalb noch ihren VOLLSTAENDIG
    UNVERAENDERTEN Originalinhalt trug: der alte Rollback haette sie geloescht, obwohl an ihr nie
    etwas geschah. (Eine Datei mit GLEICHEM Inhalt in altem und neuem Paket waere KEIN Beweis --
    die landet schon in der Planung als Aktion "nichts", nie als "schreiben".)"""
    alte_dateien = {**GRUNDDATEIEN,
                     "backend/app/d_vierte.py": b"ALT, unveraendert vom Kunden\n"}
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", alte_dateien)
    neue_dateien = {
        **GRUNDDATEIEN,
        # lokal == alt (Kunde hat sie nie angefasst) UND alt != neu: geplante Aktion ist
        # "schreiben"/"ersetzen" (Zeile 1 der Dateiregeln), NICHT "nichts" (Zeile 8 greift nur
        # bei lokal == NEU, hier bewusst nicht der Fall) -- schreiben() erreicht sie als VIERTEN
        # Versuch aber nie, weil der dritte vorher scheitert.
        "backend/app/d_vierte.py": b"NEU, sollte diese Datei nie erreichen\n",
        "backend/app/a_erste.py": b"neu a\n",     # 1. Schreibversuch
        "backend/app/b_zweite.py": b"neu b\n",    # 2. Schreibversuch
        "backend/app/c_dritte.py": b"neu c\n",    # 3. Schreibversuch -- schlaegt fehl
    }
    paket = _paket_bauen(tmp_path, "BMS_1.1.0.zip", "1.1.0", neue_dateien)
    vorher = _verzeichnis_hashes(installation)

    echtes_atomar_schreiben = bms_update._atomar_schreiben
    zaehler = {"n": 0}

    def _drittes_schreiben_schlaegt_fehl(ziel, inhalt, ausfuehrbar):
        zaehler["n"] += 1
        if zaehler["n"] == 3:
            raise PermissionError("simulierte gesperrte Datei (Windows) / volle Platte")
        return echtes_atomar_schreiben(ziel, inhalt, ausfuehrbar)

    monkeypatch.setattr(bms_update, "_atomar_schreiben", _drittes_schreiben_schlaegt_fehl)

    code = bms_update.main([str(paket), "--installation", str(installation), "--ja",
                             "--ohne-selbsttest"])

    assert code == bms_update.EXIT_ZURUECKGEROLLT
    assert zaehler["n"] == 3, "Testaufbau stimmt nicht: falsche Anzahl Schreibversuche vor dem Fehler"
    # Der Kern der Nachbesserung: die NIE erreichte Datei (geplant "ersetzen", aber vierter
    # Schreibversuch -- schreiben() bricht schon beim dritten ab) traegt nach dem Rollback exakt
    # ihren Originalinhalt -- keine Loeschung, keine Veraenderung.
    assert (installation / "backend/app/d_vierte.py").read_bytes() == b"ALT, unveraendert vom Kunden\n"
    # Vollstaendiger Beweis: der GESAMTE Programmordner ist byte-gleich wie vor dem Versuch
    # (a_erste.py und b_zweite.py, die VOR dem Fehler erfolgreich neu angelegt wurden, sind
    # wieder weg; c_dritte.py wurde nie erzeugt).
    assert _verzeichnis_hashes(installation) == vorher


# ── Abhaengigkeiten/Selbsttest mit gemocktem subprocess.run (Erfolgsfall) ───────────────────
def test_abhaengigkeiten_und_selbsttest_werden_bei_bedarf_aufgerufen(tmp_path, monkeypatch):
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", GRUNDDATEIEN)
    neue_dateien = {
        **GRUNDDATEIEN,
        "backend/app/main.py": b"neu\n",
        "backend/requirements-lock.txt": b"fastapi==2.0.0\n",
        "backend/app/selbsttest.py": b"# platzhalter\n",
    }
    paket = _paket_bauen(tmp_path, "BMS_1.1.0.zip", "1.1.0", neue_dateien)

    aufrufe = []

    def _erfolgreicher_subprocess(befehl, **kwargs):
        import subprocess
        aufrufe.append(befehl)
        return subprocess.CompletedProcess(befehl, 0, stdout="Selbsttest bestanden\n", stderr="")

    monkeypatch.setattr(bms_update.subprocess, "run", _erfolgreicher_subprocess)

    code = bms_update.main([str(paket), "--installation", str(installation), "--ja"])

    assert code == bms_update.EXIT_OK
    befehls_texte = [" ".join(b) for b in aufrufe]
    assert any("pip" in t and "requirements-lock.txt" in t for t in befehls_texte)
    assert any("app.selbsttest" in t for t in befehls_texte)


def test_selbsttest_wird_uebersprungen_wenn_nicht_im_paket(tmp_path, capsys):
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", GRUNDDATEIEN)
    paket = _paket_bauen(tmp_path, "BMS_1.1.0.zip", "1.1.0",
                          {**GRUNDDATEIEN, "backend/app/main.py": b"neu\n"})

    code = bms_update.main([str(paket), "--installation", str(installation), "--ja",
                             "--ohne-abhaengigkeiten"])
    assert code == bms_update.EXIT_OK
    assert "übersprungen" in capsys.readouterr().out


# ── --zurueck ─────────────────────────────────────────────────────────────────────────────────
def test_zurueck_stellt_vorherigen_stand_und_datenbank_wieder_her(tmp_path):
    alte_dateien = {**GRUNDDATEIEN, "backend/app/main.py": b"v1\n", "backend/app/wird_entfernt.py": b"v1\n"}
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", alte_dateien)

    db_pfad = installation / "data" / "bewerbung.sqlite"
    db_pfad.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_pfad))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()

    neue_dateien = {**GRUNDDATEIEN, "backend/app/main.py": b"v2\n", "backend/app/neu.py": b"v2\n"}
    paket = _paket_bauen(tmp_path, "BMS_1.1.0.zip", "1.1.0", neue_dateien)
    code = bms_update.main([str(paket), "--installation", str(installation), "--ja",
                             "--ohne-abhaengigkeiten", "--ohne-selbsttest"])
    assert code == bms_update.EXIT_OK
    assert (installation / "backend/app/main.py").read_bytes() == b"v2\n"
    assert (installation / "backend/app/neu.py").exists()
    assert not (installation / "backend/app/wird_entfernt.py").exists()

    # "Kundenaenderung" an der Datenbank NACH dem Update.
    conn = sqlite3.connect(str(db_pfad))
    conn.execute("INSERT INTO t VALUES (2)")
    conn.commit()
    conn.close()

    # "--mit-datenbank" noetig: "--ja" allein beantwortet die Datenbank-Rueckfrage bewusst NICHT
    # mehr (Nachbesserung Abnahme P2-51, Datenverlust-Schutz).
    code = bms_update.main(["--installation", str(installation), "--zurueck", "--ja",
                             "--mit-datenbank", "--ohne-abhaengigkeiten"])
    assert code == bms_update.EXIT_OK

    assert (installation / "backend/app/main.py").read_bytes() == b"v1\n"
    assert (installation / "backend/app/wird_entfernt.py").read_bytes() == b"v1\n"
    assert not (installation / "backend/app/neu.py").exists()

    # "--ja" bestaetigt auch die DB-Ruecknahme -- logischer Inhalt vor dem Update, nicht
    # Byte-Gleichheit: die sqlite3-Backup-API aendert den Change-Counter im Datei-Header, die
    # Zeilen selbst sind aber exakt der Stand vor dem allerersten Update (ohne die Zeile x=2,
    # die "danach" als Kundenaenderung eingefuegt wurde).
    conn = sqlite3.connect(str(db_pfad))
    zeilen = conn.execute("SELECT x FROM t ORDER BY x").fetchall()
    conn.close()
    assert zeilen == [(1,)]

    manifest = json.loads((installation / "bms_manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "1.0.0"

    # Der zurueckgenommene Bericht ist jetzt markiert -- ein zweites --zurueck faende nichts mehr.
    code2 = bms_update.main(["--installation", str(installation), "--zurueck", "--ja"])
    assert code2 == bms_update.EXIT_ABGEBROCHEN


def test_zurueck_ohne_vorheriges_update_bricht_ab(tmp_path):
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", GRUNDDATEIEN)
    code = bms_update.main(["--installation", str(installation), "--zurueck", "--ja"])
    assert code == bms_update.EXIT_ABGEBROCHEN


def test_zurueck_mit_ja_allein_laesst_datenbank_unangetastet(tmp_path, monkeypatch):
    """Nachbesserung Abnahme P2-51: "--ja" bestaetigt bei --zurueck NUR "jetzt ausfuehren", NIE
    die separate Datenbank-Rueckfrage (Datenverlust-Schutz) -- nur --mit-datenbank darf das
    nicht-interaktiv tun. Die Rueckfrage wird gezielt auf "Nein" gepatcht, um nicht von leerem
    stdin (EOFError -> False) abzuhaengen -- das Verhalten soll UNABHAENGIG von --ja sein, nicht
    nur zufaellig durch die stdin-Situation im Test dasselbe Ergebnis liefern."""
    alte_dateien = {**GRUNDDATEIEN, "backend/app/main.py": b"v1\n"}
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", alte_dateien)
    db_pfad = installation / "data" / "bewerbung.sqlite"
    db_pfad.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_pfad))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()

    neue_dateien = {**GRUNDDATEIEN, "backend/app/main.py": b"v2\n"}
    paket = _paket_bauen(tmp_path, "BMS_1.1.0.zip", "1.1.0", neue_dateien)
    code = bms_update.main([str(paket), "--installation", str(installation), "--ja",
                             "--ohne-abhaengigkeiten", "--ohne-selbsttest"])
    assert code == bms_update.EXIT_OK

    # "Kundenaenderung" an der Datenbank NACH dem Update.
    conn = sqlite3.connect(str(db_pfad))
    conn.execute("INSERT INTO t VALUES (2)")
    conn.commit()
    conn.close()

    rueckfrage_aufrufe = []

    def _rueckfrage_immer_nein(frage):
        rueckfrage_aufrufe.append(frage)
        return False

    monkeypatch.setattr(bms_update, "_rueckfrage", _rueckfrage_immer_nein)

    code = bms_update.main(["--installation", str(installation), "--zurueck", "--ja",
                             "--ohne-abhaengigkeiten"])
    assert code == bms_update.EXIT_OK
    assert rueckfrage_aufrufe, "die Datenbank-Rueckfrage haette gestellt werden muessen"

    conn = sqlite3.connect(str(db_pfad))
    zeilen = conn.execute("SELECT x FROM t ORDER BY x").fetchall()
    conn.close()
    assert zeilen == [(1,), (2,)]  # Datenbank UNVERAENDERT -- "x=2" blieb trotz "--ja" erhalten


# ── Verteidigung in der Tiefe: das ALTE Manifest ist nicht vertrauenswuerdig ────────────────
def test_geschuetzter_pfad_im_alten_manifest_wird_nie_angefasst(tmp_path):
    """Nachbesserung Abnahme P2-51: das ALTE Manifest liegt beim Kunden auf der Platte und
    koennte manipuliert oder korrumpiert sein bzw. aus einer aelteren Werkzeug-Fassung stammen,
    die diese Pruefung noch nicht kannte. Ein geschuetzter Pfad darin (hier als Zeile-4-Fall:
    "im neuen Paket nicht mehr enthalten", wuerde also normalerweise entfernt) darf NIE zu einer
    echten Datei-Operation fuehren."""
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", GRUNDDATEIEN)
    manifest_pfad = installation / "bms_manifest.json"
    manifest = json.loads(manifest_pfad.read_text(encoding="utf-8"))
    manifest["dateien"]["data/x.txt"] = {"ausfuehrbar": False, "groesse": 2,
                                          "sha256": _sha256(b"ja")}
    manifest_pfad.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (installation / "data").mkdir(parents=True, exist_ok=True)
    (installation / "data" / "x.txt").write_bytes(b"ja")  # "echte Kundendaten"

    paket = _paket_bauen(tmp_path, "BMS_1.1.0.zip", "1.1.0",
                          {**GRUNDDATEIEN, "backend/app/main.py": b"neu\n"})

    code = bms_update.main([str(paket), "--installation", str(installation), "--ja",
                             "--ohne-abhaengigkeiten", "--ohne-selbsttest"])
    assert code == bms_update.EXIT_OK
    assert (installation / "data" / "x.txt").read_bytes() == b"ja"  # unangetastet

    bericht = _bericht_lesen(installation)
    assert any("data/x.txt" in h for h in bericht["hinweise"])


def test_unsicherer_pfad_im_alten_manifest_wird_nie_angefasst(tmp_path):
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", GRUNDDATEIEN)
    manifest_pfad = installation / "bms_manifest.json"
    manifest = json.loads(manifest_pfad.read_text(encoding="utf-8"))
    manifest["dateien"]["../ausserhalb.txt"] = {"ausfuehrbar": False, "groesse": 2,
                                                 "sha256": _sha256(b"ja")}
    manifest_pfad.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    ausserhalb = tmp_path / "ausserhalb.txt"
    ausserhalb.write_bytes(b"ja")  # liegt AUSSERHALB des Programmordners

    paket = _paket_bauen(tmp_path, "BMS_1.1.0.zip", "1.1.0",
                          {**GRUNDDATEIEN, "backend/app/main.py": b"neu\n"})

    code = bms_update.main([str(paket), "--installation", str(installation), "--ja",
                             "--ohne-abhaengigkeiten", "--ohne-selbsttest"])
    assert code == bms_update.EXIT_OK
    assert ausserhalb.read_bytes() == b"ja"  # nie angefasst


# ── Selbstaktualisierung ─────────────────────────────────────────────────────────────────────
_STUB_SKRIPT = (
    "def main(argv=None):\n"
    "    print('STUB-WERKZEUG-LAEUFT')\n"
    "    return 42\n"
    "if __name__ == '__main__':\n"
    "    import sys\n"
    "    sys.exit(main())\n"
).encode("utf-8")


def test_selbstaktualisierung_delegiert_an_neue_fassung_im_paket(tmp_path):
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", GRUNDDATEIEN)
    paket = _paket_bauen(tmp_path, "BMS_1.1.0.zip", "1.1.0",
                          {**GRUNDDATEIEN, "scripts/bms_update.py": _STUB_SKRIPT})

    code = bms_update.main([str(paket), "--installation", str(installation), "--ja",
                             "--ohne-abhaengigkeiten", "--ohne-selbsttest"])

    assert code == 42  # nur der Stub gibt diesen Code zurueck -- beweist die Delegation


def test_delegiert_flag_unterdrueckt_selbstaktualisierung(tmp_path, capsys):
    installation = _installation_bauen(tmp_path, "BMS", "1.0.0", GRUNDDATEIEN)
    paket = _paket_bauen(tmp_path, "BMS_1.1.0.zip", "1.1.0",
                          {**GRUNDDATEIEN, "scripts/bms_update.py": _STUB_SKRIPT})

    code = bms_update.main([str(paket), "--installation", str(installation), "--pruefen", "--delegiert"])

    assert code == bms_update.EXIT_OK
    assert "STUB-WERKZEUG-LAEUFT" not in capsys.readouterr().out
