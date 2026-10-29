"""Tests für `cv_export._ist_eigener_zielname()` — die Weiche „Re-Export DERSELBEN CVVersion-Row
vs. echte Namenskollision" (09.08.2026).

Hintergrund: `export()` behält beim erneuten Lauf für dieselbe Row den vorhandenen Dateinamen
(sonst wandert die eigene .docx nach `…_2.docx` und das erste PDF bleibt als Waise — Befund
24.07.2026). Die Erkennung dieses Falls hing an
`stem.startswith(wunsch + "_")` und war damit zu weitmaschig: JEDE Datei, deren Name mit dem
Wunschnamen plus Unterstrich beginnt, hätte als „gehört zu dieser Row" gegolten — auch eine
fremde `…_EN`- oder `…_final`-Variante, die dann überschrieben worden wäre. Der Fix engt auf
den NUMERISCHEN Kollisions-Suffix ein, den `_unique_base()` selbst vergibt.

Diese Tests halten genau diese Grenze fest; die Funktion ist rein (kein I/O, keine DB), die
Tests brauchen daher weder Fixtures noch Dateien. App-Import wie üblich in der Testfunktion
(conftest-Konvention).
"""


def _f():
    from pipeline.cv_export import _ist_eigener_zielname
    return _ist_eigener_zielname


WUNSCH = "CV_MaxMustermann_Beispiel_Delivery_Executive_Beispiel_Cloud_Consulting_EN"


def test_exakter_konventionsname_gehoert_zur_row():
    assert _f()(WUNSCH, WUNSCH) is True


def test_numerischer_kollisions_suffix_gehoert_zur_row():
    """`_2`/`_3`/`_10` stammen von `_unique_base()` — das ist die eigene Datei aus einem
    früheren Lauf derselben Row."""
    for n in ("2", "3", "10"):
        assert _f()(f"{WUNSCH}_{n}", WUNSCH) is True, n


def test_fremder_wortsuffix_gehoert_NICHT_zur_row():
    """Der Kern des Fixes: `…_EN`/`…_final` sind ANDERE Dokumente. Vor dem Fix hätte
    `startswith()` sie eingesammelt und beim Re-Export überschrieben."""
    for suffix in ("EN", "DE", "final", "alt", "2b", "v2"):
        assert _f()(f"{WUNSCH}_{suffix}", WUNSCH) is False, suffix


def test_voellig_anderer_name_gehoert_nicht_zur_row():
    assert _f()("Irgendein_anderes_Dokument", WUNSCH) is False


def test_praefix_ohne_trenner_gehoert_nicht_zur_row():
    """`…Consulting_ENX` beginnt zwar mit dem Wunschnamen, ist aber weder er selbst noch ein
    nummerierter Suffix."""
    assert _f()(WUNSCH + "X", WUNSCH) is False


def test_regex_sonderzeichen_im_wunschnamen_werden_escaped():
    """Wunschnamen enthalten Firmen-/Rollentexte; ein `.` oder `+` darin darf NICHT als
    Regex-Platzhalter wirken (sonst würde `CV_Firma.AG` auch auf `CV_FirmaXAG_2` passen)."""
    wunsch = "CV_MaxMustermann_Firma.AG_Head_of_C+S_DE"
    assert _f()(wunsch, wunsch) is True
    assert _f()(wunsch + "_2", wunsch) is True
    assert _f()(wunsch.replace(".", "X") + "_2", wunsch) is False
