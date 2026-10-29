"""Phase 67E (P2-17, Code-Review 2026-07-25) — `beirat_engine._turn_anthropic()` startete den
Subprozess bisher mit ZWEI GETRENNTEN Pipes (`stdout=PIPE, stderr=PIPE`), leerte aber nur stdout
aktiv (`_lesen()` liest ausschließlich `proc.stdout`). Füllt der Kindprozess den stderr-Puffer
(OS-Pipe, typ. 16–64 KB) — z. B. weil `claude -p` bei einem Fehler viel auf stderr schreibt —,
blockiert sein `write()`-Syscall dauerhaft: der Read-Loop wartet auf stdout, das nie mehr kommt,
solange das Kind blockiert bleibt. Begrenzt nur durch `MAX_TURN_SEKUNDEN` (300 s echt) — danach
`asyncio.TimeoutError` statt einer brauchbaren Fehlermeldung. `agent_runner._run_task()` löst das
bereits über `stderr=asyncio.subprocess.STDOUT` (ein gemeinsamer Stream, den derselbe Read-Loop
mit abdeckt).

Fix hier: dasselbe Muster übernehmen. ZWEITE Invariante (explizit von der Spec verlangt): die
„leerer Turn"-Diagnose las stderr bisher SEPARAT (`await proc.stderr.read()`), um dem Fehler
Text mitzugeben. Nach dem Merge ist `proc.stderr` IMMER `None` (asyncio-Garantie bei
`stderr=STDOUT`) — ein Fix, der nur die Pipes mergt, würde diese Diagnose stillschweigend auf ""
zurückfallen lassen. Der Test unten prüft deshalb zusätzlich, dass eine unverwechselbare
stderr-Kennung aus dem allerletzten Kindprozess-Schrieb weiterhin in der Fehlermeldung auftaucht.

B1 (Q3, kein echter Beirats-/API-Lauf): `CLAUDE_BIN` zeigt auf ein lokales, harmloses
Python-Stub-Skript — kein Subprozess ruft je eine echte API oder liest echte Keys/Daten.
`WORK_DIR` wird auf `tmp_path` umgebogen (kein Schreiben unter ~/.bewerbung_beirat/work).

────────────────────────────────────────────────────────────────────────────────────────────
P2-19 (27.08.2026) — ZWEI BEFUNDE AN DIESER DATEI SELBST, beide behoben:

1. **Der Test flackerte.** Er brach mit einer festen `timeout=8`-Wanduhrgrenze ab. Gemessen
   braucht er gesund **0,42 s**, unter 36 Rechenprozessen auf 18 Kernen sogar nur 0,24 s — der
   Puffer war also 19-fach und riss trotzdem einmal (vermutlich I/O-Stau; das Projekt liegt in
   iCloud). Eine 8-Sekunden-Grenze auf einer 0,4-Sekunden-Operation ist keine Verhaltensaussage,
   sondern eine Wette auf die Maschine. Das ist gravierend, weil im Projekt die Regel gilt:
   Eine Abnahme braucht grünes CI — ein zufällig roter Test erzieht dazu, rote Läufe zu ignorieren.

2. **Die dokumentierte Notbremse existierte gar nicht.** Der Docstring behauptete,
   `monkeypatch.setattr(be, "MAX_TURN_SEKUNDEN", 5)` begrenze den Lauf auf wenige Sekunden.
   Tatsächlich steht der Wert in der Signatur (`timeout: int = MAX_TURN_SEKUNDEN`) und wird beim
   DEFINIEREN der Funktion einmalig an 300 gebunden — ein späteres Setzen des Modul-Attributs
   ändert den Default nicht mehr (nachgemessen über `inspect.signature`). Bei einer echten
   Regression hätte die Engine also 300 s gelaufen; einziger wirksamer Riegel war das `timeout=8`.
   Beide Tests übergeben den Wert jetzt EXPLIZIT als Parameter.

Konsequenz für den Aufbau: Der eigentliche Beweis („stdout und stderr laufen in EINEM Stream")
steckt jetzt in `test_subprozess_legt_stderr_mit_stdout_zusammen` — der kommt komplett OHNE
Wanduhr aus und schlägt bei einer Regression sofort fehl. Die beiden Verhaltenstests bleiben als
Rückfallebene und behalten eine Zeitgrenze, weil sich „hängt nicht" ohne irgendeine Schranke
nicht beweisen lässt. Diese Schranken sind jetzt aber großzügig (60 s in der Engine, 120 s im
Test) und ausdrücklich HÄNGEN-Erkennung, keine Laufzeitzusage.
"""
import asyncio
import os
import stat

import pytest

pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX-only: Shebang-Python-Stub als CLAUDE_BIN (Windows kennt keinen Shebang-Exec)",
)

# Notbremsen gegen ein HÄNGEN — keine Leistungszusage (s. P2-19 im Modul-Docstring). Der gesunde
# Lauf liegt bei rund 0,4 s; diese Werte lassen also das ~150-Fache zu, bevor der Test anschlägt.
# ENGINE_NOTBREMSE muss KLEINER als TEST_NOTBREMSE bleiben: Sonst greift die Notbremse des Tests
# zuerst und verdeckt die aussagekräftigere Meldung der Engine.
ENGINE_NOTBREMSE = 60
TEST_NOTBREMSE = 120

# Stub-"claude"-Binary: ignoriert alle CLI-Argumente, flutet NUR stderr weit über jede
# realistische OS-Pipe-Kapazität (viele KURZE Zeilen -- keine einzelne überlang, sonst greift
# eine ANDERE Grenze, das asyncio-StreamReader-Zeilenlimit, statt der hier gemeinten
# Pipe-Kapazität), schreibt absichtlich KEIN gültiges stream-json auf stdout (-> `voll` bleibt
# leer -> die "leerer Turn"-Diagnose greift) und endet mit einem festen, erkennbaren Exit-Code.
_STUB = """#!/usr/bin/env python3
import sys
for _ in range(4000):
    print("F" * 200, file=sys.stderr)
print("STDERR-DIAGNOSE-MARKIERUNG-9f3a", file=sys.stderr)
sys.exit(3)
"""


def _stub_schreiben(tmp_path):
    pfad = tmp_path / "fake_claude.py"
    pfad.write_text(_STUB, encoding="utf-8")
    pfad.chmod(pfad.stat().st_mode | stat.S_IEXEC)
    return pfad


async def _noop_delta(_text: str) -> None:
    pass


def _engine_praeparieren(monkeypatch, tmp_path, stub_pfad):
    """Hermetische Ausgangslage: kein echter Key, kein Schreiben außerhalb von `tmp_path`.

    `MAX_TURN_SEKUNDEN` wird BEWUSST NICHT gepatcht — das war wirkungslos (P2-19, Befund 2).
    Die Zeitgrenze übergeben die Tests stattdessen explizit als `timeout=`-Parameter.
    """
    import beirat_engine as be

    monkeypatch.setattr(be, "CLAUDE_BIN", str(stub_pfad))
    monkeypatch.setattr(be, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(be, "keys_lesen", lambda: {})
    return be


class _Abbruch(Exception):
    """Bricht den Turn direkt nach dem Subprozess-Aufruf ab — der Test braucht nur die Argumente."""


def test_subprozess_legt_stderr_mit_stdout_zusammen(monkeypatch, tmp_path):
    """DER Kernbeweis für P2-17 — und zwar ohne jede Wanduhr.

    Geprüft wird die Ursache selbst: `_turn_anthropic` muss den Subprozess mit
    `stderr=asyncio.subprocess.STDOUT` starten. Genau daran hängt alles — mit einer zweiten,
    nie geleerten stderr-Pipe blockiert das Kind im `write()`, sobald es den Puffer füllt.

    Der Test fängt den Aufruf ab und bricht sofort ab: Es wird kein Prozess gestartet, nichts
    gelesen, nichts abgewartet. Bei einer Regression schlägt er in Millisekunden fehl statt nach
    einer Zeitgrenze — und er kann unter Last nicht zufällig rot werden.
    """
    be = _engine_praeparieren(monkeypatch, tmp_path, _stub_schreiben(tmp_path))
    aufrufe = []

    async def _aufzeichnen(*_args, **kwargs):
        aufrufe.append(kwargs)
        raise _Abbruch()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _aufzeichnen)

    with pytest.raises(_Abbruch):
        asyncio.run(be._turn_anthropic("Systemprompt (Test)", "Userprompt (Test)",
                                       "irrelevant-modell", _noop_delta, task_id=None))

    assert aufrufe, "create_subprocess_exec wurde gar nicht aufgerufen — Test greift ins Leere"
    assert aufrufe[0].get("stderr") is asyncio.subprocess.STDOUT, (
        "stderr muss mit stdout in EINEN Stream laufen. Eine zweite Pipe, die niemand leert, "
        "lässt das Kind im write() blockieren, sobald es den Puffer füllt (P2-17).")
    assert aufrufe[0].get("stdout") is asyncio.subprocess.PIPE, (
        "stdout bleibt die gelesene Pipe — sonst kommt beim Read-Loop nichts an")


def test_turn_anthropic_deadlockt_nicht_bei_vollem_stderr_puffer(monkeypatch, tmp_path):
    """Verhaltensbeweis P2-17: ein Kindprozess, der NUR stderr flutet (kein brauchbares stdout),
    darf den Turn nicht hängen lassen. Vor dem Fix: `TimeoutError` (der Read-Loop wartet ewig auf
    stdout, das Kind hängt im write() auf stderr). Nach dem Fix: schneller, sauberer
    `RuntimeError` („Leerer Anthropic-Turn"), weil kein echter Beitrag zustande kam — UND die
    Fehlermeldung trägt weiterhin den stderr-Inhalt (zweite Invariante der Spec: die Diagnose
    darf durch den Pipes-Merge nicht verstummen).

    Die Zeitgrenzen sind reine Hängen-Erkennung, keine Laufzeitzusage — s. P2-19 oben.
    """
    be = _engine_praeparieren(monkeypatch, tmp_path, _stub_schreiben(tmp_path))

    async def _lauf():
        return await asyncio.wait_for(
            be._turn_anthropic("Systemprompt (Test)", "Userprompt (Test)", "irrelevant-modell",
                               _noop_delta, task_id=None, timeout=ENGINE_NOTBREMSE),
            timeout=TEST_NOTBREMSE,
        )

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(_lauf())

    meldung = str(exc_info.value)
    assert "Leerer Anthropic-Turn" in meldung
    assert "exit 3" in meldung
    assert "STDERR-DIAGNOSE-MARKIERUNG-9f3a" in meldung   # Diagnose überlebt den Pipes-Merge


def test_turn_anthropic_erfolgsfall_unveraendert(monkeypatch, tmp_path):
    """Q5-Gegenprobe: ein Kind, das normal ein `result`-Event mit Text auf stdout schreibt (kein
    Stress auf stderr), liefert weiterhin Text+Kosten wie vor dem Fix — der Stream-Merge ändert
    am Erfolgsfall nichts."""
    import json as _json  # noqa: F401  (Symmetrie zum Stub unten, bewusst behalten)

    stub = tmp_path / "fake_claude_ok.py"
    stub.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, "
        "'result': 'Echter Beitrag (synthetisch).', 'total_cost_usd': 0.01}))\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)

    be = _engine_praeparieren(monkeypatch, tmp_path, stub)

    text, kosten = asyncio.run(asyncio.wait_for(
        be._turn_anthropic("Systemprompt (Test)", "Userprompt (Test)", "irrelevant-modell",
                           _noop_delta, task_id=None, timeout=ENGINE_NOTBREMSE),
        timeout=TEST_NOTBREMSE,
    ))
    assert text == "Echter Beitrag (synthetisch)."
    assert kosten == 0.01
