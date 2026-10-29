"""Tests fuer pipeline.cleanup (Phase 68A / P3-7): data/beirat im Orphan-Scan.

Es gab bisher KEINE Tests fuer pipeline.cleanup ueberhaupt (Phase-57-Prozessregel verlangt einen
echten Test je Befund, der Code aendert -- dies ist die erste Testdatei fuer das Modul).

Hintergrund des Befunds: `data/beirat` fehlte in BEIDEN Whitelists von cleanup.py. Der Review
schlug vor, den Ordner "analog data/agent_logs" in die altersbasierte ROTATIONS-Whitelist zu
nehmen -- das waere falsch gewesen: `data/beirat` enthaelt auch die per JobFile verlinkten
Dashboard-HTMLs (main.py::get_job zeigt sie unter "Dateien & Dokumente"), eine Alters-Loeschung
haette funktionierende Links zerstoert. Der Orphan-Scan (DB-Referenz statt Alter) ist der
richtige Mechanismus, braucht aber eine Sonderbehandlung fuer zwei Dateiarten, die NIE per
DB-Pfadfeld referenziert werden (s. `pipeline.cleanup._beirat_ausnahme` Docstring):
  (a) "<...>_rohdaten.json" -- Rohdaten-Zwilling eines Dashboard-HTML, exempt nur solange das
      Geschwister-HTML noch existiert.
  (b) "<debatte_id>.json" -- das Debatten-Zustandsjournal, bewusst ohne DB-Tabelle, IMMER exempt.

Zwei Ebenen:
  1. `_beirat_ausnahme()` direkt -- reine Funktion auf einem Path, komplett isoliert ueber
     pytest `tmp_path`, keinerlei Beruehrung mit den echten Projekt-Ordnern/DB.
  2. `_orphan_kandidaten()` mit `cleanup.PROJECT_ROOT`/`cleanup._ORPHAN_DIRS` per `monkeypatch`
     komplett auf einen synthetischen `tmp_path`-Ordner umgebogen (gleiches Prinzip wie
     test_loeschen_reihenfolge.py: `monkeypatch.setattr(main, "_PROJECT_ROOT", tmp_path)`, hier
     fuer `cleanup.PROJECT_ROOT` + volle Ersetzung von `_ORPHAN_DIRS` statt nur einem Eintrag,
     damit die Schleife NIE auf einen echten Ordner trifft) -- niemals gegen die echten 202
     Dateien im echten `data/beirat` (T1/R3/R4: Dummy-Dateien in einer isolierten Kopie statt
     gegen den echten Bestand, dasselbe Prinzip wie beim Backup-Rotationstest aus demselben
     Phasen-Auftrag).

App-Importe ausschliesslich innerhalb der Testfunktionen (Konvention aus conftest.py).
"""


def _schreibe(pfad, inhalt="phase68a pytest probe\n"):
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(inhalt, encoding="utf-8")
    return pfad


# ── Wiring-Regression: der Whitelist-Eintrag selbst darf nicht wieder verschwinden ──────────
def test_data_beirat_ist_in_orphan_whitelist():
    from pipeline import cleanup

    assert "data/beirat" in cleanup._ORPHAN_DIRS
    assert "data/beirat" not in cleanup._ROTATIONS_DIRS, (
        "ACHTUNG: data/beirat gehoert NICHT in die altersbasierte Rotation -- das war der "
        "Review-Vorschlag, den Phase 68A bewusst abgelehnt hat (s. Moduldocstring)."
    )


# ── Ebene 1: _beirat_ausnahme() direkt ──────────────────────────────────────────────────────
def test_beirat_ausnahme_rohdaten_mit_lebendem_geschwister_html_ist_exempt(tmp_path):
    from pipeline.cleanup import _beirat_ausnahme

    _schreibe(tmp_path / "2026_07_18_BeiratsCheck_Testfirma_Rolle.html")
    roh = _schreibe(tmp_path / "2026_07_18_BeiratsCheck_Testfirma_Rolle_rohdaten.json")

    assert _beirat_ausnahme(roh) is True


def test_beirat_ausnahme_rohdaten_ohne_geschwister_html_ist_kein_exempt(tmp_path):
    """Das Geschwister-HTML wurde (z. B. durch main.py::delete_job) bereits entfernt/verschoben
    -- die verwaiste Rohdaten-Datei muss jetzt korrekt NICHT mehr exempt sein (= Orphan-Kandidat
    in _orphan_kandidaten, s. Ebene 2 unten)."""
    from pipeline.cleanup import _beirat_ausnahme

    roh = _schreibe(tmp_path / "2026_07_18_BeiratsCheck_Testfirma_Rolle_rohdaten.json")

    assert _beirat_ausnahme(roh) is False


def test_beirat_ausnahme_bare_debatten_json_immer_exempt(tmp_path):
    """Das Debatten-Zustandsjournal (<debatte_id>.json, bewusst ohne DB-Tabelle) darf NIE als
    Orphan gelten -- unabhaengig davon, ob irgendein HTML danebenliegt (hier: keins)."""
    from pipeline.cleanup import _beirat_ausnahme

    zustand = _schreibe(tmp_path / "2026_07_23_1932_0c15d6.json")

    assert _beirat_ausnahme(zustand) is True


def test_beirat_ausnahme_html_selbst_nicht_zustaendig(tmp_path):
    """Der Orphan-Status des Dashboard-HTML selbst laeuft AUSSCHLIESSLICH ueber die normale
    referenz_menge-Pruefung (JobFile.file_path), nicht ueber diese Funktion -- sie ist fuer
    .html-Pfade grundsaetzlich nicht zustaendig und gibt deshalb immer False zurueck."""
    from pipeline.cleanup import _beirat_ausnahme

    html = _schreibe(tmp_path / "2026_07_18_BeiratsCheck_Testfirma_Rolle.html")

    assert _beirat_ausnahme(html) is False


# ── Ebene 2: _orphan_kandidaten() gegen einen isolierten data/beirat-Ordner ─────────────────
def test_orphan_kandidaten_data_beirat_isoliert(tmp_path, monkeypatch):
    """Voller Integrationstest der neuen Whitelist-Zeile + _beirat_ausnahme() zusammen, gegen
    einen komplett synthetischen Ordner -- niemals gegen die echten 202 Dateien in data/beirat.

    PROJECT_ROOT UND _ORPHAN_DIRS werden beide umgebogen (nicht nur ein einzelner Eintrag),
    damit die Schleife in _orphan_kandidaten() garantiert auf KEINEN echten Ordner trifft
    (sonst wuerde schon das erste `p.relative_to(PROJECT_ROOT)` fuer eine echte Datei aus
    data/company_fit o.ae. mit ValueError crashen, weil deren Pfad nicht mehr unter dem
    (dann versetzten) PROJECT_ROOT liegt).

    Aufbau (5 Dateien unter tmp_path/data/beirat/):
      - referenziert.html + referenziert_rohdaten.json   (beide sollen ueberleben)
      - verwaist.html     + verwaist_rohdaten.json        (html: Orphan; rohdaten: in DIESEM
        Lauf noch exempt, weil das Geschwister-HTML noch auf der Platte liegt)
      - 2026_07_23_1932_0c15d6.json                       (bare Zustandsjournal, nie Orphan)
    """
    from pipeline import cleanup

    beirat_ordner = tmp_path / "data" / "beirat"
    _schreibe(beirat_ordner / "referenziert.html")
    _schreibe(beirat_ordner / "referenziert_rohdaten.json")
    _schreibe(beirat_ordner / "verwaist.html")
    _schreibe(beirat_ordner / "verwaist_rohdaten.json")
    _schreibe(beirat_ordner / "2026_07_23_1932_0c15d6.json")

    monkeypatch.setattr(cleanup, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cleanup, "_ORPHAN_DIRS", {"data/beirat": beirat_ordner})

    referenz_menge = {"data/beirat/referenziert.html"}  # simuliert die eine lebende JobFile-Row
    kandidaten = {k["pfad"] for k in cleanup._orphan_kandidaten(referenz_menge)}

    # ── referenziertes Paar ueberlebt komplett ──
    assert "data/beirat/referenziert.html" not in kandidaten
    assert "data/beirat/referenziert_rohdaten.json" not in kandidaten
    # ── Zustandsjournal ist NIE Kandidat ──
    assert "data/beirat/2026_07_23_1932_0c15d6.json" not in kandidaten
    # ── verwaistes HTML wird korrekt erkannt (keine JobFile-Referenz in referenz_menge) ──
    assert "data/beirat/verwaist.html" in kandidaten
    # ── seine Rohdaten-Datei ist in DIESEM Lauf noch exempt (Geschwister-HTML liegt noch da) ──
    assert "data/beirat/verwaist_rohdaten.json" not in kandidaten

    # Naechster Lauf, NACHDEM ein apply() das verwaiste HTML in den Papierkorb verschoben haette
    # (main.py::delete_job / cleanup.apply verschieben Orphan-Dateien) -- hier nur das HTML
    # geloescht, um genau diesen Folgezustand nachzustellen, OHNE apply() selbst aufzurufen:
    (beirat_ordner / "verwaist.html").unlink()
    kandidaten_2 = {k["pfad"] for k in cleanup._orphan_kandidaten(referenz_menge)}
    assert "data/beirat/verwaist_rohdaten.json" in kandidaten_2, (
        "Nach dem Verschwinden des Geschwister-HTML muss die Rohdaten-Datei beim naechsten "
        "Scan als Orphan erkannt werden -- sonst bliebe sie fuer immer liegen."
    )
