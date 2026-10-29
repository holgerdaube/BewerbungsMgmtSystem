"""Wache über die eigene Open-Source-Lizenz (29.10.2026, Entscheidung: Apache-2.0).

- `LICENSE` ist der unveränderte Wortlaut von https://www.apache.org/licenses/LICENSE-2.0.txt.
  Die Prüfsumme hält ihn fest; die Herkunftsangabe gehört in `NOTICE`, nie in `LICENSE`.
- `frontend/src/rechtliches/lizenz.txt` ist eine Kopie für den Reiter „Open-Source-Lizenz“, weil
  der Build-Spiegel (`frontend/build.sh`) nur `frontend/` sieht. Sie muss bytegleich bleiben.
- `NOTICE` nennt Programm und Urheber; „Über dieses Programm“ sagt dasselbe.

Kein app.*/pipeline.*-Import auf Modulebene (conftest-Konvention, s. tests/conftest.py)."""
import hashlib
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
APACHE_2_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"


def test_license_ist_der_unveraenderte_apache_wortlaut():
    roh = (PROJECT_ROOT / "LICENSE").read_bytes()
    assert hashlib.sha256(roh).hexdigest() == APACHE_2_SHA256, \
        "LICENSE weicht vom Apache-2.0-Wortlaut ab; Copyright und Herkunft gehören in NOTICE"


def test_kopie_in_der_oberflaeche_ist_bytegleich():
    assert (PROJECT_ROOT / "frontend/src/rechtliches/lizenz.txt").read_bytes() == \
        (PROJECT_ROOT / "LICENSE").read_bytes(), "cp LICENSE frontend/src/rechtliches/lizenz.txt"


def test_notice_und_ueber_nennen_programm_urheber_und_lizenz():
    notice = (PROJECT_ROOT / "NOTICE").read_text(encoding="utf-8")
    zeilen = notice.splitlines()
    assert zeilen[0] == "Bewerbungs-Management-System (BewerbungsMgmtSystem)"
    urheberzeile = re.fullmatch(r"Copyright 2026 (\S.*\S)", zeilen[1])
    assert urheberzeile, "NOTICE nennt in Zeile 2 kein Copyright mit Jahr und Urheber"
    urheber = urheberzeile.group(1)
    ueber = (PROJECT_ROOT / "frontend/src/rechtliches/ueber.md").read_text(encoding="utf-8")
    for teil in ("Bewerbungs-Management-System", urheber, "Apache License 2.0", "NOTICE"):
        assert teil in ueber, f"„Über dieses Programm“ nennt {teil!r} nicht"
