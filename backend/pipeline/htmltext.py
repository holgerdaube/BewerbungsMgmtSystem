"""HTML zu lesbarem Text — gemeinsamer Stripper für gmail_client UND search_index (Phase 25).

Ursprünglich in gmail_client._entkleiden (Phase 8.3, Mail-Body-Dekodierung). Hierher gezogen,
damit search_index.py (Company-Fit-/Snapshot-/Debrief-/Briefing-HTML indexieren) ihn mitnutzt,
statt ihn zu duplizieren. Verhalten unverändert.
"""
import html
import re


def entkleiden(html_text: str) -> str:
    """Kein Raten, nur Auszeichnung entfernen — Markup raus, Inhalt bleibt."""
    text = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", html_text)
    text = re.sub(r"(?i)<(br|/p|/div|/tr|/li)\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[^\S\n]+", " ", text)     # NBSP/Zero-width aus Mail-/Report-Templates
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
