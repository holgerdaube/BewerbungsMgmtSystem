"""Phase 89 — abgeschnittenes Synthese-JSON kostet keine Debatte mehr.

Fall A, 23.08.2026 (4,00 USD): Die Vorsitz-Synthese kam mit 5.249
Zeichen und `stop_reason: end_turn` zurueck, hatte aber 13 oeffnende und nur 12 schliessende
Klammern -- dem Modell fehlte am Ende genau ein `}`. `_json_extrahieren` suchte per Regex
`\\{.*\\}`, fand dadurch nur einen unvollstaendigen Ausschnitt, `json.loads` scheiterte, und der
Lauf brach ab: `raise RuntimeError(...)`. Verworfen wurde damit eine vollstaendig gelaufene
Runde -- Debatte, Abstimmung und Ampel standen laengst und waren gespeichert, die Synthese ist
Schritt 4 von 4.

Zwei Massnahmen, hier abgesichert:
  1. `_klammern_balancieren` haengt fehlende `}`/`]` an, ohne Inhalt zu erfinden. Klammern
     INNERHALB von Strings zaehlen nicht mit; endet die Antwort mitten in einem String, wird
     bewusst NICHT repariert (dann fehlt echter Text).
  2. Scheitert die Synthese trotzdem, ist das kein Abbruchgrund mehr -- das Dashboard wird mit
     einem offenen Hinweis gerendert (Ampel/Score/Voten haengen nicht an diesem Text).

Konvention wie in der uebrigen Suite (s. conftest.py): keine app.*/pipeline.*/beirat_engine-
Importe auf Modulebene, rein synthetische Daten, kein echter Lauf.
"""
import json


def test_reparatur_ergaenzt_genau_eine_fehlende_klammer():
    """Der Echtfall in klein: ein verschachteltes Objekt, dem das letzte `}` fehlt."""
    from beirat_engine import Debatte

    roh = '{"begruendung": "Score 6,4/10", "risiko_board": [{"punkt": "Auftraggeber unklar"}]'

    ergebnis = Debatte._json_extrahieren(roh)

    assert ergebnis is not None
    assert ergebnis["begruendung"] == "Score 6,4/10"
    assert ergebnis["risiko_board"][0]["punkt"] == "Auftraggeber unklar"


def test_reparatur_ignoriert_klammern_innerhalb_von_strings():
    """Eine `{` im Fliesstext darf die Bilanz nicht verschieben — sonst haengt die Reparatur
    zu viele Klammern an und erzeugt neues, kaputtes JSON."""
    from beirat_engine import Debatte

    roh = '{"begruendung": "Der Score {gewichtet} liegt bei 6,4", "empfehlung": "Nachfragen"'

    ergebnis = Debatte._json_extrahieren(roh)

    assert ergebnis is not None
    assert ergebnis["begruendung"] == "Der Score {gewichtet} liegt bei 6,4"
    assert ergebnis["empfehlung"] == "Nachfragen"


def test_keine_reparatur_wenn_die_antwort_mitten_im_string_endet():
    """Hier fehlt echter INHALT, nicht nur ein Schlusszeichen. Ein geratenes `"` wuerde einen
    halben Satz als vollstaendige Begruendung ausgeben — lieber ehrlich scheitern."""
    from beirat_engine import Debatte

    roh = '{"begruendung": "Der gewichtete Gesamtscore von 6,4/10 spiegelt die Debatte'

    assert Debatte._json_extrahieren(roh) is None


def test_vollstaendiges_json_bleibt_unveraendert():
    """Der Normalfall darf durch die Reparatur nicht angefasst werden."""
    from beirat_engine import Debatte

    original = {"begruendung": "alles gut", "risiko_board": [{"punkt": "kein Risiko"}]}

    ergebnis = Debatte._json_extrahieren(json.dumps(original, ensure_ascii=False))

    assert ergebnis == original


def test_json_mit_vor_und_nachtext_wird_weiterhin_gefunden():
    """Modelle rahmen JSON gern mit Prosa oder Markdown-Zaeunen — das konnte der Regex vorher
    schon und muss er weiterhin koennen."""
    from beirat_engine import Debatte

    roh = 'Hier das Ergebnis:\n```json\n{"begruendung": "ok"}\n```\nSoweit meine Einordnung.'

    assert Debatte._json_extrahieren(roh) == {"begruendung": "ok"}


def test_ohne_jede_klammer_bleibt_es_bei_none():
    from beirat_engine import Debatte

    assert Debatte._json_extrahieren("Ich kann dazu leider nichts sagen.") is None
