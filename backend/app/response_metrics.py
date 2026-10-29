"""Response-Rate / Ø-Antwortzeit — EINE Berechnung für Dashboard UND Excel-Export (Phase 67B, P2-7).

Vorher lebte dieselbe Formel textgleich an zwei Stellen (`app/main.py::dashboard()` und
`pipeline/export_excel.py::build_workbook()`) und zählte JEDE qualifizierende Antwort-Mail
einzeln. Bekommt eine Bewerbung mehrere Antworten (Eingangsbestätigung → Einladung → Absage),
zählte sie mehrfach — die Quote konnte über 100 % steigen, und der Zeit-Durchschnitt verzerrte
sich zugunsten von Bewerbungen mit viel Mailverkehr. Live-DB-Beleg (25./26.07.2026): 22
qualifizierende Mails von nur 13 EINDEUTIGEN Bewerbungen — die alte Formel zeigte
40 % Response Rate statt der tatsächlichen 24 %.

Fix: auf Bewerbungsebene deduplizieren (`Email.application_id`) — eine Bewerbung zählt für die
Rate höchstens einmal, für die Zeit zählt ihre FRÜHESTE qualifizierende Antwort. Mails ohne
`application_id` (Firma erkannt, aber keiner konkreten Stelle zuordenbar — der „Ohne Stelle"-Fall
aus `gmail_ingest.py`) zählen nicht mit: es gibt keine Bewerbung, gegen die man sie zählen könnte,
und der Nenner (`len(apps)`) zählt ausschließlich echte `Application`-Zeilen.

BEWUSST reine Funktion ohne DB-/FastAPI-Import: `export_excel.py` läuft als eigenständiges CLI
(`refresh_views.sh`) und darf NICHT die ganze FastAPI-App importieren (Kommentar dort bei
TERMINAL_STATUSES) — dieses Modul importiert deshalb nichts aus `app.main`, nur Stdlib, und
nimmt bereits geladene `Email`/`Application`-Listen entgegen statt selbst zu lesen.

EINZIGE Stelle dieser Berechnung — main.py UND export_excel.py rufen `response_kpis()` auf.
Bei einer künftigen Änderung dieser Formel gibt es nur noch einen Ort zu ändern.
"""
from typing import Iterable


def response_kpis(emails: Iterable, apps: Iterable) -> dict:
    """Response Rate + Ø Antwortzeit auf Bewerbungsebene.

    `emails`: Iterable von Objekten mit `.is_response`, `.response_time_hours`, `.application_id`
    (z. B. `Email`-Zeilen). `apps`: Iterable von `Application`-Zeilen (nur für die Anzahl gebraucht).

    Rückgabe: {"responses": int, "avg_response_hours": float|None, "response_rate": int|None}
    `responses` ist die Anzahl EINDEUTIGER Bewerbungen mit mindestens einer qualifizierenden
    Antwort (Vertragsänderung ggü. der alten Mail-Zählung ist der Sinn dieses Fixes).
    """
    apps = list(apps)
    fruehste_je_bewerbung: dict = {}
    for e in emails:
        if not e.is_response or e.response_time_hours is None or e.application_id is None:
            continue
        bisher = fruehste_je_bewerbung.get(e.application_id)
        if bisher is None or e.response_time_hours < bisher:
            fruehste_je_bewerbung[e.application_id] = e.response_time_hours

    n = len(fruehste_je_bewerbung)
    avg_resp = round(sum(fruehste_je_bewerbung.values()) / n, 1) if n else None
    response_rate = round(n / len(apps) * 100) if apps else None
    return {"responses": n, "avg_response_hours": avg_resp, "response_rate": response_rate}
