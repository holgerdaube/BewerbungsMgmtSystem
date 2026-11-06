"""`seniority_min`: Neue Installationen starten leer, ein vorhandener Wert bleibt beim Speichern erhalten."""
import yaml

from pipeline import suchprofil

_SUCHBEREICH = {"remote": {"aktiv": True}, "deutschlandweit": {"aktiv": True},
                "umkreis": {"aktiv": False, "stadt": "", "umkreis_km": 100}}
_PLAENE = [{"plan": n, "label": f"Plan {n}", "aktiv": True, "prioritaet": 1, "titel": [], "senioritaet": [], "branche": []}
           for n in "ABC"]


def _kopf(pfad):
    text = pfad.read_text(encoding="utf-8")
    return yaml.safe_load(text[:text.index(suchprofil.MARKER)])


def test_neue_installation_startet_leer(tmp_path):
    pfad = tmp_path / "suchprofile.yaml"
    assert suchprofil.sicherstellen(pfad) is True
    assert not _kopf(pfad)["seniority_min"]


def test_speichern_behaelt_vorhandenen_wert(tmp_path):
    pfad = tmp_path / "suchprofile.yaml"
    pfad.write_text("seniority_min: Manager\n" + suchprofil.MARKER + "\nmax_alter_tage: 30\n", encoding="utf-8")
    suchprofil.schreibe_suchprofile(suchprofil.baue_managed(100, _SUCHBEREICH, _PLAENE), pfad)
    assert _kopf(pfad)["seniority_min"] == "Manager"
    assert pfad.read_text(encoding="utf-8").endswith("max_alter_tage: 30\n")


def test_speichern_ohne_vorhandenen_wert_bleibt_leer(tmp_path):
    pfad = tmp_path / "suchprofile.yaml"
    assert suchprofil.sicherstellen(pfad) is True
    suchprofil.schreibe_suchprofile(suchprofil.baue_managed(100, _SUCHBEREICH, _PLAENE), pfad)
    assert not _kopf(pfad)["seniority_min"]
