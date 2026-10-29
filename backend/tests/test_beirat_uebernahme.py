"""Phase 90-Nachtrag — Übernahme einer Neubesetzung nach `.claude/agents/`.

Anlass (Testlauf 1162, 23.08.2026): Der `beirat-persona`-Lauf erzeugte eine vollstaendige,
inhaltlich gute Persona — und legte sie nirgends ab. Jeder Write/Edit auf `.claude/` wurde von
der Sandbox verweigert (Selbstmodifikations-Schutz von Claude Code; Schreiben nach `data/` ging,
das Backup wurde korrekt angelegt). Der Lauf meldete trotzdem Erfolg.

Konsequenz: Der Lauf sammelt seine Ergebnisse unter `data/tmp/beirat_neubesetzung/` und der
Server uebernimmt sie — der Server-Prozess unterliegt der Sandbox nicht. Damit das keine offene
Tuer nach `.claude/` wird, prueft `uebernehme_neubesetzung()` streng; diese Pruefung ist der
Gegenstand dieser Tests.

Der wichtigste Fall ist `..._eine_kaputte_datei_verhindert_die_ganze_uebernahme`: Ein halb
ausgetauschtes Ensemble mit toten Verweisen waere schlimmer als ein fehlgeschlagener Lauf.

Konvention wie in der uebrigen Suite (conftest.py): keine Modulebenen-Importe von
app.*/pipeline.*/beirat_engine, rein synthetische Dateien in `tmp_path`, kein echter Lauf. Die
echten Persona-Dateien werden NIE angefasst — `AGENTS_DIR`/`UEBERNAHME_DIR`/`DATEN_DIR` zeigen in
jedem Test auf ein pytest-Temp-Verzeichnis.
"""
import pytest

ABSCHNITTE = (
    "# Rolle im Beirat", "# Mentales Betriebssystem", "# Frameworks, Prinzipien & Formeln",
    "# Charakteristische Prüffragen", "# Was wir an dir schätzen", "# Grenzen & blinde Flecken",
    "# Im Austausch (MiroFish)", "# Ton & Sprache",
)


def _persona(platz_id: str, anzeige: str, fuellung: int = 5000, ohne=None) -> str:
    """Synthetische Persona in der Bauart der Bestandsdateien, gross genug fuer die Pruefung."""
    koepfe = "\n".join(a + "\nInhalt fuer " + a + ". " + "x" * (fuellung // len(ABSCHNITTE))
                       for a in ABSCHNITTE if a != ohne)
    return ("---\nname: " + platz_id + "\ndescription: Perspektive von " + anzeige
            + "\nmodel: sonnet\nfarbe: \"#123456\"\n---\n\n"
            + "Du bist **" + anzeige + "** als Mitglied eines Beirats.\n\n" + koepfe + "\n")


@pytest.fixture()
def beirat(tmp_path, monkeypatch):
    """Isolierte Welt: zwei bestehende Plaetze, leeres Uebernahme-Verzeichnis."""
    import beirat_engine as be

    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "beirat-alt-eins.md").write_text(_persona("beirat-alt-eins", "Alt Eins"), encoding="utf-8")
    (agents / "beirat-alt-zwei.md").write_text(_persona("beirat-alt-zwei", "Alt Zwei"), encoding="utf-8")
    uebernahme = tmp_path / "uebernahme"
    uebernahme.mkdir()
    monkeypatch.setattr(be, "AGENTS_DIR", agents)
    monkeypatch.setattr(be, "UEBERNAHME_DIR", uebernahme)
    monkeypatch.setattr(be, "BACKUP_DIR", tmp_path / "backup")
    return be, agents, uebernahme


def test_uebernimmt_neue_persona_und_sichert_die_alte(beirat):
    be, agents, uebernahme = beirat
    (uebernahme / "beirat-alt-eins.md").write_text(_persona("beirat-alt-eins", "Neu Eins"), encoding="utf-8")

    ergebnis = be.uebernehme_neubesetzung("beirat-alt-eins")

    assert ergebnis["uebernommen"] == ["beirat-alt-eins"]
    assert "Neu Eins" in (agents / "beirat-alt-eins.md").read_text(encoding="utf-8")
    assert "Alt Eins" not in (agents / "beirat-alt-eins.md").read_text(encoding="utf-8")
    gesichert = list((be.BACKUP_DIR).glob("*beirat-alt-eins.md"))
    assert len(gesichert) == 1, "die alte Persona muss gesichert sein"
    assert "Alt Eins" in gesichert[0].read_text(encoding="utf-8")


def test_uebernimmt_auch_die_reparierten_verweis_dateien(beirat):
    """Der Lauf liefert nicht nur den neuen Kopf, sondern auch die uebrigen Dateien, in denen er
    die Verweise auf den ersetzten Kopf umgeschrieben hat."""
    be, agents, uebernahme = beirat
    (uebernahme / "beirat-alt-eins.md").write_text(_persona("beirat-alt-eins", "Neu Eins"), encoding="utf-8")
    (uebernahme / "beirat-alt-zwei.md").write_text(_persona("beirat-alt-zwei", "Alt Zwei repariert"), encoding="utf-8")

    ergebnis = be.uebernehme_neubesetzung("beirat-alt-eins")

    assert sorted(ergebnis["uebernommen"]) == ["beirat-alt-eins", "beirat-alt-zwei"]
    assert "Alt Zwei repariert" in (agents / "beirat-alt-zwei.md").read_text(encoding="utf-8")


def test_eine_kaputte_datei_verhindert_die_ganze_uebernahme(beirat):
    """Der wichtigste Fall: alles-oder-nichts. Ein halb ausgetauschtes Ensemble haette tote
    Verweise — schlimmer als ein fehlgeschlagener Lauf."""
    be, agents, uebernahme = beirat
    vorher_eins = (agents / "beirat-alt-eins.md").read_text(encoding="utf-8")
    vorher_zwei = (agents / "beirat-alt-zwei.md").read_text(encoding="utf-8")
    (uebernahme / "beirat-alt-eins.md").write_text(_persona("beirat-alt-eins", "Neu Eins"), encoding="utf-8")
    (uebernahme / "beirat-alt-zwei.md").write_text(
        _persona("beirat-alt-zwei", "Kaputt", ohne="# Grenzen & blinde Flecken"), encoding="utf-8")

    with pytest.raises(be.MitgliedFehler, match="Grenzen"):
        be.uebernehme_neubesetzung("beirat-alt-eins")

    assert (agents / "beirat-alt-eins.md").read_text(encoding="utf-8") == vorher_eins
    assert (agents / "beirat-alt-zwei.md").read_text(encoding="utf-8") == vorher_zwei


def test_unbekannter_platz_im_frontmatter_wird_abgewiesen(beirat):
    """Ueber diesen Weg duerfen nur BESTEHENDE Plaetze ersetzt werden — sonst waere es ein
    Schreibzugriff auf beliebige Dateien in `.claude/agents/`."""
    be, _agents, uebernahme = beirat
    (uebernahme / "beirat-alt-eins.md").write_text(_persona("beirat-fremd", "Fremd"), encoding="utf-8")

    with pytest.raises(be.MitgliedFehler, match="kein bestehender Beiratsplatz"):
        be.uebernehme_neubesetzung("beirat-alt-eins")


def test_zu_kleine_datei_wird_abgewiesen(beirat):
    be, _agents, uebernahme = beirat
    (uebernahme / "beirat-alt-eins.md").write_text("---\nname: beirat-alt-eins\n---\nzu kurz\n",
                                                   encoding="utf-8")

    with pytest.raises(be.MitgliedFehler, match="Bytes"):
        be.uebernehme_neubesetzung("beirat-alt-eins")


def test_datei_fuer_den_gemeldeten_platz_muss_dabei_sein(beirat):
    """Liefert der Lauf nur reparierte Fremd-Dateien, aber nicht den neu besetzten Platz, ist er
    unvollstaendig — dann darf gar nichts uebernommen werden."""
    be, agents, uebernahme = beirat
    vorher = (agents / "beirat-alt-zwei.md").read_text(encoding="utf-8")
    (uebernahme / "beirat-alt-zwei.md").write_text(_persona("beirat-alt-zwei", "Alt Zwei neu"), encoding="utf-8")

    with pytest.raises(be.MitgliedFehler, match="beirat-alt-eins"):
        be.uebernehme_neubesetzung("beirat-alt-eins")

    assert (agents / "beirat-alt-zwei.md").read_text(encoding="utf-8") == vorher


def test_leeres_uebernahme_verzeichnis(beirat):
    be, _agents, _uebernahme = beirat

    with pytest.raises(be.MitgliedFehler, match="keine `beirat-\\*.md`"):
        be.uebernehme_neubesetzung("beirat-alt-eins")


def test_unbekannter_platz_liefert_nicht_gefunden(beirat):
    be, _agents, _uebernahme = beirat

    with pytest.raises(be.MitgliedNichtGefunden):
        be.uebernehme_neubesetzung("beirat-gibts-nicht")
