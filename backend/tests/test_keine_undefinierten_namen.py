"""Wächter: kein Modul im Backend benutzt einen Namen, den es nicht kennt.

Anlass: Mit dem Übersetzungslauf P2-88 bis P2-90 rief agent_runner.py `tx(...)` statt
`sprache.tx(...)` auf. Python merkt das erst, wenn die Zeile läuft, und das war nur bei einer
Warnung zur agent.env der Fall, unter Windows bei jedem Start (2.2.2). Ein statischer Blick mit
pyflakes findet solche Stellen, ohne dass ein Test den Zweig treffen muss.

Bewusste Ausnahmen tragen `# noqa: F821` in der Zeile (etwa Rückgabetypen als String).
"""
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ZIELE = [BACKEND / "app", BACKEND / "pipeline", BACKEND / "beirat_engine.py", BACKEND / "run_server.py"]


def _dateien():
    for ziel in ZIELE:
        if ziel.is_file():
            yield ziel
        else:
            yield from sorted(p for p in ziel.rglob("*.py") if "__pycache__" not in p.parts)


def test_keine_undefinierten_namen():
    from pyflakes import checker, messages
    import ast

    funde = []
    for datei in _dateien():
        quelle = datei.read_text(encoding="utf-8")
        zeilen = quelle.splitlines()
        baum = ast.parse(quelle, filename=str(datei))
        for m in checker.Checker(baum, filename=str(datei)).messages:
            if not isinstance(m, messages.UndefinedName):
                continue
            if "noqa: F821" in zeilen[m.lineno - 1]:
                continue
            funde.append(f"{datei.relative_to(BACKEND)}:{m.lineno}: {m.message % m.message_args}")
    assert not funde, "Undefinierte Namen:\n" + "\n".join(funde)
