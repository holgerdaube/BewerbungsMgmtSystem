#!/usr/bin/env python3
"""Suchlisten für Schritt 1b des Gmail-Checks: bekannte Kontakt-Adressen und Firmendomains (P2-80).

Die Stichwort-Suche des Skills `email-check` fängt nur Mails, deren Betreff oder Absender ein Muster
trifft. Persönliche Post von einem bekannten Kontakt trifft oft keins. Schritt 1b sucht deshalb
zusätzlich nach den Adressen und Domains, die das BMS schon kennt. Bis P2-80 stand diese Logik als
Python-Schnipsel im Skill-Text; hier steht sie einmal, getestet, und der Skill ruft nur noch auf.

Anlass P2-80 (19.10.2026): Eine Absage nach einem Gespräch kam vom Recruiter persönlich, Betreff ohne
Stichwort, Absender ohne ATS-Muster. Der Recruiter stand als Kontakt OHNE Adresse in der DB, und die
Firmendomain wurde nur für Personalberater durchsucht. Die Mail fiel durch beide Netze. Neu kommen
deshalb auch die Firmendomains LAUFENDER Bewerbungen (`LAUFEND`) in die Domain-Suche, abgeleitet aus
Mails, die schon an der Stelle hängen, und aus Kontaktadressen der Stelle.

Regeln (unverändert aus Phase 80 übernommen, bis auf die laufenden Bewerbungen):
  * `ADRESSEN`: alle Kontakt-Adressen außer an terminalen Stellen. Berater-Rollen (`BERATER_ROLLE`)
    bleiben immer drin — bei einem Headhunter endet mit dem Job das Mandat, nicht die Beziehung.
  * `DOMAINS`: Firmendomains der Berater-Kontakte und (P2-80) der laufenden Bewerbungen, gefiltert
    gegen `SPERRLISTE_DOMAINS` (ATS, Freemail und — P2-80 — große Jobportale, die sonst ihre ganze
    übrige Post in die Suche spülen würden).
  * `OHNE_MAIL`: Namen der Berater-Kontakte ohne Adresse, für die Berichtszeile des Skills.

  * Fremdsprachen (FR, IT, ES, PT): Wörter für Betreff und Absender stehen in
    `pipeline/bewerbungssprache.py`. Sie kommen NICHT in die Haupt-Query des Skills, sondern in eine
    eigene zweite Suche, und nur, wenn der Nutzer in einer dieser Sprachen bewirbt: Basis-CV
    `data/cv_basis/base_<sprache>.docx` oder eine laufende Bewerbung mit CV bzw. Anschreiben in der
    Sprache (`sprachen()`). Ohne solche Sprachen läuft der Skill wie bisher.

CLI (aus backend/), nur lesend:
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.mail_suchlisten
Ausgabe: drei beschriftete Zeilen `ADRESSEN:`, `DOMAINS:`, `OHNE_MAIL:` (Format wie bisher im Skill).
    ~/.bewerbung_mgmt_venv/bin/python -m pipeline.mail_suchlisten --sprachen
Ausgabe: `SPRACHEN:` (Codes, leer ohne Fremdsprache) und nur dann `SPRACHEN_BETREFF:` und
`SPRACHEN_ABSENDER:` (Wörter, mit ` OR ` verbunden). Eigener Aufruf, damit die Ausgabe ohne Schalter für
alle Nutzer bleibt, wie sie war.
"""
import argparse
import re
from typing import Optional

from sqlmodel import Session, select

from app.db import DATA_DIR, engine, init_db
from app.models import Application, Contact, CVVersion, Email, Job
from pipeline import bewerbungssprache

# Bewusst dieselbe Menge wie `main.py::TERMINAL_STATUSES` (Pipeline-Module importieren main.py nicht).
TERMINAL = {"Absage", "Kein Match", "Nicht verfügbar", "Beirat abgelehnt", "Keine Rückmeldung"}
# P2-80: Stellen, an denen Post der Firma zu erwarten ist.
LAUFEND = {"Beworben", "Interview", "Angebot"}
BERATER_ROLLE = re.compile(r"headhunter|personalberat|recruiter|talent acquisition|consultant", re.IGNORECASE)
SPERRLISTE_DOMAINS = {
    "myworkday.com", "successfactors.eu", "m.personio.de", "teamtailor-mail.com", "beesite.de",
    "greenhouse-mail.io", "ashbyhq.com", "lever.co", "icims.com", "softgarden.io", "personio.de",
    "gmail.com", "googlemail.com", "gmx.de", "gmx.net", "gmx.at", "gmx.ch", "web.de",
    "outlook.com", "outlook.de", "hotmail.com", "hotmail.de", "t-online.de", "yahoo.com", "yahoo.de",
    # P2-80: Jobportale. Ihre Bewerbungsbestätigungen hängen an Stellen, die Domain ist aber kein
    # Arbeitgeber — eine Domain-Suche würde jede Portal-Mitteilung einsammeln.
    "linkedin.com", "xing.com", "indeed.com", "stepstone.de", "glassdoor.com",
}
# Sprachen der zweiten Suche: alle Tabellensprachen außer DE und EN (deren Wörter stehen in der
# Haupt-Query des Skills).
FREMDSPRACHEN = tuple(c for c in bewerbungssprache.CODES if c not in ("DE", "EN"))
# Absender-Teile unter dieser Länge kommen nicht in die Suche: `rh` träfe in Gmail jeden Absender, der
# „RH“ im Namen trägt, und im IMAP-Weg (Teilstring-Vergleich, `imap_mail._matches_leaf`) auch „Gerhard“,
# „Rhein…“. Gemessen am echten Postfach ist es nicht; die Domain-Suche (Schritt 1b) und die Betreff-Wörter
# fangen die Post laufender Bewerbungen. Das Wort bleibt in der Tabelle.
ABSENDER_MIN_LAENGE = 4
_ADRESSE_RE = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")


def domain_von(adresse: Optional[str]) -> Optional[str]:
    """Domain einer Adresse, auch aus „Name <a@b.de>“; ohne erkennbare Adresse None."""
    m = _ADRESSE_RE.search(adresse or "")
    return m.group(1).lower() if m else None


def gesperrt(domain: str) -> bool:
    if domain.split(".")[0] == "jobalerts" and domain.count(".") == 1:
        return True
    return any(domain == b or domain.endswith("." + b) for b in SPERRLISTE_DOMAINS)


def suchlisten() -> dict:
    """`{"adressen": [...], "domains": [...], "ohne_mail": [...]}`, je sortiert. Nur lesend."""
    init_db()
    with Session(engine) as s:
        status = {j.id: j.status for j in s.exec(select(Job).where(Job.deleted_at.is_(None))).all()}
        laufend = [jid for jid, st in status.items() if st in LAUFEND]
        adressen, domains, ohne_mail = set(), set(), set()
        for c in s.exec(select(Contact)).all():
            berater = bool(c.role and BERATER_ROLLE.search(c.role))
            terminal = status.get(c.job_id) in TERMINAL
            if c.email:
                if berater or not terminal:
                    adressen.add(c.email)
                d = domain_von(c.email)
                # P2-80: neben Berater-Kontakten auch Kontakte laufender Bewerbungen
                if d and not gesperrt(d) and (berater or c.job_id in laufend):
                    domains.add(d)
            elif berater:
                ohne_mail.add(c.name or f"Kontakt#{c.id}")
        # P2-80: Absender-Domains der Mails, die schon an einer laufenden Bewerbung hängen
        if laufend:
            for e in s.exec(select(Email).where(Email.job_id.in_(laufend),
                                                Email.direction == "incoming")).all():
                d = domain_von(e.from_addr)
                if d and not gesperrt(d):
                    domains.add(d)
    return {"adressen": sorted(adressen), "domains": sorted(domains), "ohne_mail": sorted(ohne_mail)}


def sprachen() -> list:
    """Fremdsprachen (`FREMDSPRACHEN`), in denen der Nutzer bewirbt, in Tabellenreihenfolge: Basis-CV
    `base_<sprache>.docx` in `data/cv_basis/` oder ein CV (`CVVersion.language`) bzw. Anschreiben
    (`Application.cover_letter_language`) an einer laufenden Bewerbung (`LAUFEND`). Nur lesend."""
    init_db()
    gefunden = {c for c in FREMDSPRACHEN if (DATA_DIR / "cv_basis" / f"base_{c.lower()}.docx").is_file()}
    with Session(engine) as s:
        laufend = [j.id for j in s.exec(select(Job).where(Job.deleted_at.is_(None),
                                                          Job.status.in_(LAUFEND))).all()]
        if laufend:
            angaben = [cv.language for cv in s.exec(select(CVVersion).where(CVVersion.job_id.in_(laufend))).all()]
            angaben += [a.cover_letter_language
                        for a in s.exec(select(Application).where(Application.job_id.in_(laufend))).all()]
            gefunden |= {c for c in map(bewerbungssprache.normiere_code, angaben) if c in FREMDSPRACHEN}
    return [c for c in FREMDSPRACHEN if c in gefunden]


def sprachen_woerter(codes) -> dict:
    """`{"betreff": [...], "absender": [...]}` der genannten Sprachen aus der Sprachtabelle, ohne Doppelte.
    Absender-Teile kürzer als `ABSENDER_MIN_LAENGE` fehlen (siehe dort)."""
    return {"betreff": list(bewerbungssprache.alle_marker("mail_betreff", codes)),
            "absender": [w for w in bewerbungssprache.alle_marker("mail_absender", codes)
                         if len(w) >= ABSENDER_MIN_LAENGE]}


def main(argv=()) -> None:
    ap = argparse.ArgumentParser(description="Suchlisten für den Gmail-Check (nur lesend)")
    ap.add_argument("--sprachen", action="store_true",
                    help="stattdessen die Sprachen und Suchwörter der zweiten Suche ausgeben")
    args = ap.parse_args(argv)
    if args.sprachen:
        codes = sprachen()
        print("SPRACHEN:", " ".join(codes))
        if codes:
            woerter = sprachen_woerter(codes)
            print("SPRACHEN_BETREFF:", " OR ".join(woerter["betreff"]))
            print("SPRACHEN_ABSENDER:", " OR ".join(woerter["absender"]))
        return
    listen = suchlisten()
    print("ADRESSEN:", " OR ".join(listen["adressen"]))
    print("DOMAINS:", " OR ".join(f"@{d}" for d in listen["domains"]))
    print("OHNE_MAIL:", ", ".join(listen["ohne_mail"]))


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
