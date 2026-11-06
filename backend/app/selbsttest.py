"""Selbsttest fuer eine frisch eingespielte Installation (P2-51, Update-Werkzeug Schritt 12).

`scripts/bms_update.py` ruft dieses Modul NACH dem Schreiben der neuen Programmdateien als
EIGENEN Subprozess auf (`sys.executable -m app.selbsttest`), mit BMS_DATA_DIR/BMS_LOG_DIR/
BMS_SECRETS_DIR auf Temp-Verzeichnisse gesetzt (Kopie der gesicherten Datenbank, s. dortiger
Docstring). Ein eigener Prozess deshalb, weil `app.db` (und `app.agent_runner`) ihre Datenpfade
beim IMPORT an die Umgebung binden (s. deren Docstrings) -- das Update-Werkzeug selbst darf
laut Bau-Spec NIE app/pipeline importieren, ein Import HIER waere also so oder so der einzige
Weg, und ein Subprozess haelt beide Welten sauber getrennt.

Zwei Pruefungen:
  1. `import app.main` -- faengt fehlende Python-Pakete (Abhaengigkeiten-Schritt schiefgelaufen)
     und Syntaxfehler in der neuen Fassung ab, ohne dass der Kunde das erst beim naechsten
     Doppelklick auf start.command bemerkt. Reiner Modul-Import: kein Lifespan-Start, kein
     Port wird geoeffnet, kein Worker startet (s. app/main.py -- `@app.on_event("startup")`
     feuert nur bei einem echten ASGI-Lifespan, nicht beim blossen Import).
  2. `init_db()` gegen die (Kopie der) Datenbank, danach fuer jede Tabelle aus SQLModel.metadata:
     jede Modellspalte muss in `PRAGMA table_info(...)` stehen. Ein `_ADD_COLUMNS`-Eintrag
     (app/db.py), der unter der neuen Version scheitert (z. B. Tippfehler im ALTER TABLE),
     waere sonst erst beim naechsten echten Serverstart als "no such column" sichtbar --
     mitten in der Arbeit des Kunden, nicht waehrend eines kontrollierten Updates.
"""
import sys

from app.terminal import tt


def selbsttest() -> list[str]:
    """Gibt die Liste der fehlenden Spalten zurueck (leer = bestanden). Import-/Syntaxfehler
    werden bewusst NICHT abgefangen -- `main()` unten faengt sie zu einer Kundentext-Zeile."""
    import app.main  # noqa: F401  -- Smoke-Test, s. Moduldoc Punkt 1
    from app.db import engine, init_db
    from sqlmodel import SQLModel

    init_db()

    fehlende: list[str] = []
    with engine.connect() as conn:
        for name, tabelle in SQLModel.metadata.tables.items():
            vorhandene_spalten = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({name})")}
            for spalte in tabelle.columns:
                if spalte.name not in vorhandene_spalten:
                    fehlende.append(f"{name}.{spalte.name}")
    return fehlende


def main() -> int:
    try:
        fehlende = selbsttest()
    except Exception as exc:  # Import-/Syntaxfehler/DB-Fehler -- Ursache fuer den Kunden lesbar machen
        print(tt("Selbsttest fehlgeschlagen: {art}: {fehler}", art=type(exc).__name__, fehler=exc))
        return 1
    if fehlende:
        print(tt("Selbsttest fehlgeschlagen. Fehlende Spalten: {spalten}", spalten=", ".join(fehlende)))
        return 1
    print(tt("Selbsttest bestanden"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
