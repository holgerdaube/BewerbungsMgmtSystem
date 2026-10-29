"""Negativ-Wächter „kein Sende-Codepfad" (Phase 71F).

`tasks/lessons.md` Abschnitt „Gmail": **Sicherheit durch fehlenden Codepfad, nicht durch
Disziplin.** Der Google-Scope `gmail.compose` erlaubt der API technisch auch das Senden; die
Garantie „Mails verlassen das Postfach nie" hängt AUSSCHLIESSLICH daran, dass kein Modul einen
Send-Aufruf besitzt. Bisher nur als manuelles Grep-Rezept dokumentiert
(`grep -nE "cl\\.(post|put|delete|patch)" pipeline/gmail_client.py` → genau EIN Treffer,
`POST /drafts`) — dieser Test macht daraus einen automatisierten Wächter UND erweitert ihn
sinngemäß um den neuen IMAP-Provider (Phase 71F Spec-Vorgabe): `smtplib` darf NIRGENDS unter
`backend/pipeline/` importiert werden, auch nicht auskommentiert „für später".

Reine Dateisystem-/Regex-Prüfung, kein App-Import nötig.
"""
import re
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent / "pipeline"
PROJECT_ROOT = PIPELINE_DIR.parent.parent

# Absichtlich NICHT auf Zeilenanfang verankert (`^\s*import …`) -- das wuerde einen
# auskommentierten Import (`# import smtplib  # fuer spaeter`, genau das Spec-Verbot "auch
# nicht auskommentiert 'fuer spaeter'") als False Negative durchlassen. `\b` an beiden Enden
# verhindert dafuer, dass die Wortgruppe "import"/"from" + "smtplib" IRGENDWO im Fliesstext
# (z. B. dieser eigene Modul-Docstring, oder gmail_client/imap_mail-Docstrings, die die
# Abwesenheit von smtplib DOKUMENTIEREN) faelschlich anschlaegt -- "importiert NIRGENDS
# `smtplib`" enthaelt die Zeichenkette "import smtplib" NICHT (dazwischen steht "iert
# NIRGENDS `"), waehrend "# import smtplib" sie enthaelt.
_SMTPLIB_RE = re.compile(r"\b(?:import|from)\s+smtplib\b")
_HTTPX_WRITE_RE = re.compile(r"\bcl\.(post|put|delete|patch)\b")


def _alle_python_dateien(verzeichnis: Path):
    return sorted(p for p in verzeichnis.rglob("*.py") if p.is_file())


def test_kein_smtplib_import_irgendwo_unter_backend_pipeline():
    """Spec-Vorgabe wörtlich: `smtplib wird nirgends in backend/pipeline/ importiert` --
    auch nicht in `imap_mail.py`, auch nicht auskommentiert als `# import smtplib  # fuer
    spaeter`."""
    treffer = []
    for py in _alle_python_dateien(PIPELINE_DIR):
        text = py.read_text(encoding="utf-8")
        if _SMTPLIB_RE.search(text):
            treffer.append(str(py.relative_to(PROJECT_ROOT)))
    assert treffer == [], (
        f"'smtplib'-Import gefunden (verboten -- kein Sende-Codepfad, s. tasks/lessons.md "
        f"Abschnitt Gmail, 'Sicherheit durch fehlenden Codepfad'): {treffer}"
    )


def test_smtplib_guard_erkennt_einen_gepflanzten_treffer():
    """Gegenprobe zum Positiv-Test oben (Lehre 'Verifikation': ein Wächter, der nie feuert,
    ist kein Beweis) -- derselbe Scan MUSS auf einer synthetischen Zeile anschlagen, egal ob
    auskommentiert oder nicht, aber NICHT auf blossem Fliesstext ueber das Thema."""
    assert _SMTPLIB_RE.search("import os\nimport smtplib\n")
    assert _SMTPLIB_RE.search("import os\n# import smtplib  # fuer spaeter\n")
    assert _SMTPLIB_RE.search("from smtplib import SMTP")
    assert not _SMTPLIB_RE.search("Dieses Modul importiert NIRGENDS `smtplib`.")


def test_gmail_client_hat_genau_einen_schreibenden_httpx_aufruf():
    """Automatisierte Fassung des bisherigen manuellen Grep-Rezepts (tasks/lessons.md):
    `cl.(post|put|delete|patch)` darf in `gmail_client.py` GENAU EINMAL auftauchen -- das ist
    `POST /drafts` in `cmd_draft`'s Gmail-Zweig. Jeder weitere Treffer wäre ein neuer,
    unbeabsichtigter Schreib-/Sende-/Lösch-/Änderungs-Aufruf gegen die Gmail-API."""
    datei = PIPELINE_DIR / "gmail_client.py"
    text = datei.read_text(encoding="utf-8")
    treffer = _HTTPX_WRITE_RE.findall(text)
    assert treffer == ["post"], (
        f"Erwartet genau EINEN 'cl.post'-Treffer (POST /drafts), gefunden: {treffer}"
    )


def test_imap_mail_hat_genau_einen_append_aufruf():
    """Sinngemäße Entsprechung des obigen Wächters für den neuen IMAP-Provider: der einzige
    schreibende IMAP-Aufruf ist `imap.append(...)` (Entwurf mit `\\Draft`-Flag) in
    `cmd_draft`. Kein `store`/`copy`/`expunge`/`uid('STORE', ...)` o. ä. irgendwo sonst."""
    datei = PIPELINE_DIR / "imap_mail.py"
    text = datei.read_text(encoding="utf-8")
    append_treffer = re.findall(r"\bimap\.append\(", text)
    assert len(append_treffer) == 1, (
        f"Erwartet genau EINEN 'imap.append('-Aufruf (Entwurf anlegen), gefunden: {len(append_treffer)}"
    )
    verboten = re.findall(r"\.uid\(\s*[\"']STORE|\.store\(|\.expunge\(|\.copy\(", text)
    assert verboten == [], f"Unerwarteter schreibender/loeschender IMAP-Aufruf: {verboten}"


def test_imap_mail_appended_ausschliesslich_mit_draft_flag():
    """Der eine erlaubte Schreibaufruf muss das \\Draft-Flag tragen -- ein APPEND ohne dieses
    Flag würde in machen Postfächern als normale (potenziell auffindbare/zustellbare)
    Nachricht landen statt eindeutig als Entwurf erkennbar zu sein."""
    datei = PIPELINE_DIR / "imap_mail.py"
    text = datei.read_text(encoding="utf-8")
    m = re.search(r"imap\.append\(([^\n]*)", text)
    assert m is not None
    assert r"\Draft" in m.group(1)
