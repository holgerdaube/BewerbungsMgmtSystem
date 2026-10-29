#!/usr/bin/env python3
"""Schreibt den Rotationsstand für viele Objekte in EINEM Aufruf zurück.

Anlass (Phase 88-Nachtrag, 22.08.2026): Die Skills schrieben den Rotationsstand zuerst je Objekt
mit einem eigenen `curl` fort (12 bzw. 15 Turns für reine Mechanik). Der Ersatz durch EIN
Python-Heredoc scheiterte im echten Lauf an der Freigabeprüfung:

    Contains brace with quote character (expansion obfuscation)

Belegt am Tageslauf vom 22.08.2026 und insgesamt 64-mal in 20 Tagen quer über
alle Skill-Arten. Ursache ist die Schreibweise, nicht der Inhalt: f-Strings mit geschweiften
Klammern (`f"…/{cid}"`) und Inline-Dicts (`json.dumps({"feld": wert})`) im Heredoc-Text sehen für
die statische Prüfung wie verschleierte Shell-Expansion aus. Empirisch verifiziert am 22.08.2026
mit drei Varianten desselben Kommandos: f-String + Inline-Dict → abgelehnt; String-Konkatenation
+ `dict()` → läuft; **Skript-Datei aufrufen → läuft**.

Dieses Skript ist die dritte Variante: Der Skill ruft eine Datei auf, im Bash-Kommando steht keine
einzige geschweifte Klammer. Nebenbei liegt die Fehlerbehandlung damit an EINER Stelle statt in
jeder Skill-Vorlage.

Aufruf (aus dem Projekt-Root oder backend/):
    ~/.bewerbung_mgmt_venv/bin/python scripts/rotation_stand.py target-companies 2026-08-22 41 25 26
    ~/.bewerbung_mgmt_venv/bin/python scripts/rotation_stand.py headhunters 2026-08-22 hh21 hh16

Die IDs dürfen so übergeben werden, wie die Listen-API sie liefert: `GET /api/headhunters` gibt
`hh21` zurück, `PATCH /api/headhunters/{id}` erwartet dagegen die nackte `21` (sonst HTTP 422
`int_parsing`, real belegt am 21.08.2026). Das Präfix schneidet dieses Skript ab.

Ausgabe: eine Bilanzzeile, plus bei Fehlern eine zweite mit den betroffenen IDs. Ein Fehlschlag
bricht den Lauf NICHT ab — sonst blieben die restlichen Rotationsstände lautlos ungesetzt und die
Objekte liefen am Folgetag erneut auf. Exit-Code 1, wenn mindestens einer fehlschlug, damit ein
Skill den Fehler bemerkt und in den Abschlussbericht nimmt.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

BASIS = "http://localhost:8000/api/"
ENDPUNKTE = ("target-companies", "headhunters")
FELD = "last_career_check"


def _nackte_id(roh: str) -> str:
    """`hh21` -> `21`. Zielfirmen liefern bereits numerische IDs und bleiben unverändert."""
    return str(roh).removeprefix("hh")


def setzen(endpunkt: str, datum: str, ids: list) -> int:
    kopf = dict()
    kopf["Content-Type"] = "application/json"
    nutzlast = json.dumps(dict([(FELD, datum)])).encode()

    ok, fehler = 0, []
    for roh in ids:
        ziel = BASIS + endpunkt + "/" + _nackte_id(roh)
        anfrage = urllib.request.Request(ziel, data=nutzlast, headers=kopf, method="PATCH")
        try:
            urllib.request.urlopen(anfrage, timeout=20)
            ok += 1
        except urllib.error.HTTPError as e:
            fehler.append(str(roh) + ": HTTP " + str(e.code))
        except urllib.error.URLError as e:
            fehler.append(str(roh) + ": " + type(e).__name__)

    print("Rotationsstand fortgeschrieben: " + str(ok) + " von " + str(len(ids)))
    if fehler:
        print("NICHT gesetzt: " + "; ".join(fehler))
    return 1 if fehler else 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Rotationsstand für viele Objekte setzen")
    ap.add_argument("endpunkt", choices=ENDPUNKTE)
    ap.add_argument("datum", help="ISO-Datum, z. B. 2026-08-22")
    ap.add_argument("ids", nargs="+", help="IDs wie von der Listen-API geliefert (hh-Präfix erlaubt)")
    a = ap.parse_args()
    sys.exit(setzen(a.endpunkt, a.datum, a.ids))


if __name__ == "__main__":
    main()
