"""Personendaten-Prüfung (P2-83, Vertrag P): die dateibezogenen Prüfregeln, die vorher in
`pipeline/kundenpaket.py` standen, als eigenes Modul. Zwei Aufrufer: die Paketprüfung
(`kundenpaket.py`, Umfang `"paket"`) und das Export-Werkzeug für den öffentlichen Baum
(`veroeffentlichung.py`, Umfang `"oeffentlich"`).

KEINE PERSÖNLICHEN MUSTER IM CODE. Im Code stehen nur der Mechanismus und allgemeine Regeln
(E-Mail mit Ausnahmen, Telefonformat, Bestands-IDs, absolute Benutzerpfade, String-Scan). Alles, was
eine konkrete Person verrät, kommt zur Laufzeit aus lokalen Quellen (`muster_laden`):

  (a) `config/profil.md` (nicht im Git), gelesen mit dem Parser der App (`profil_datei.lesen_aus_text`):
      Name (Vor- und Nachname), Standort als Anschrift (daraus Straße und Postleitzahl als eigene
      Muster), Kontakt (E-Mail, Telefon), LinkedIn.
  (b) die lokale Datenbank (`data/bewerbung.sqlite`, NUR LESEND, sqlite-URI `mode=ro`): Firmennamen
      aus den vier Namensspalten (`_FIRMEN_SPALTEN`) und die Namen der Kontakte (`contact.name`,
      mindestens zwei Wörter) als Dritte Personen.
  (c) optional `pruefmuster.txt` im Secrets-Ordner (`BMS_SECRETS_DIR`, sonst
      `~/.bewerbung_mgmt_secrets/`): je Zeile ein Begriff, `#` am Zeilenanfang = Kommentar. Für
      frühere Anschriften und Namen, die nirgends sonst stehen. Der Begriff wird nach seiner Form
      einer Regel zugeordnet: mit `@`, `linkedin.` oder `://` = Private Kontaktdaten; mit Ziffer oder
      Straßen-Endung (…straße, …weg, …platz, …allee, …gasse, …ring, …ufer, …damm, …pfad) = Anschrift;
      alles andere = Dritte Personen. Begriffe unter drei Zeichen zählen nicht.
Fehlen Profil oder Datenbank, ist `Muster.vollstaendig` falsch, und die persönlichen Regeln entfallen
STILL (`Muster.hinweise` sagt, was fehlte). Ob das ein Abbruch ist, entscheidet der Aufrufer: die
Paketprüfung in der CI läuft so weiter, das Export-Werkzeug bricht ab.

NIE EIN MUSTER AUSGEBEN: `Muster.__repr__` nennt nur Zahlen. Auch Testausgaben dürfen kein Muster
enthalten; Funde zeigen die Zeile der Datei (`Fund.ausschnitt`), nicht das Muster.

ZWEI UMFÄNGE (`pruefen(…, umfang=…)`):
  * `"paket"` (Kundenpaket, nach Ausschließen und Ersetzen): Zeilenenden, Anschrift, Private
    Kontaktdaten, Dritte Personen, E-Mail, Telefon, Bestands-IDs, Firmennamen. Der Name des Nutzers
    gilt nur in den Kundentext-Pfaden (`NAME_KUNDENTEXT_PFADE`), in String-Literalen von
    Python-Dateien (ohne Docstrings) und im TS/TSX-Code ohne Kommentare. Kommentare und Docstrings
    dürfen ihn nennen.
  * `"oeffentlich"` (Export in das öffentliche Repo): ALLE Dateien, KEINE Pfad-Ausnahmen außer dem
    fremden Wortlaut (`_FREMDER_WORTLAUT`) und, nur für den Namen, der Zuschreibungsliste
    (`ZUSCHREIBUNG_PFADE`, README-Abschnitte zu Autor und Lizenz). Der Name zählt überall, auch in
    Kommentaren, Docstrings und Dateinamen. Dazu der absolute Benutzerpfad (`/Users/<x>/`,
    `/home/<x>/`, `C:\\Users\\<x>`) als eigene Regel, und alle Muster werden auch gegen den Dateipfad
    gehalten.

NAME DES NUTZERS: Vor- und Nachname aus dem Profil, als ganze Wörter (keine Buchstaben davor oder
dahinter; ein Genitiv-s ist erlaubt), ohne Beachtung der Schreibweise. Marke und Domain „Daube.Tech“
zählen nicht als Nachname. Der Kontoname (Vor- plus Nachname zusammengeschrieben, klein) wird als
Private Kontaktdaten gesucht, weil er in Pfaden und Repo-Adressen steckt; erlaubt ist davon nur der
Name des öffentlichen Repos (`OEFFENTLICHES_REPO`) und, nur in README und FUNDING.yml, die beiden
Spendenlinks (`SPENDEN_PFADE`).

Reine Funktionen auf einer Liste von `Eintrag`en im Speicher; das Modul fasst weder Git noch die
Platte an (außer `muster_laden`, das Profil, Datenbank und Musterdatei liest). Pfade sind IMMER
Git-Konvention (Vorwärtsschrägstrich).
"""
from __future__ import annotations

import ast
import fnmatch
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, NamedTuple

from pipeline import profil_datei

UMFANG_PAKET = "paket"
UMFANG_OEFFENTLICH = "oeffentlich"
UMFAENGE: tuple[str, ...] = (UMFANG_PAKET, UMFANG_OEFFENTLICH)


class Eintrag(NamedTuple):
    """Eine Datei im Paket-Aufbau: Pfad IMMER mit "/" (Git-Konvention, plattformunabhängig),
    Modus NUR die Unix-Rechte ohne Dateityp-Bits (0o644/0o755 — Symlinks werden nie zu einem
    Eintrag, s. kundenpaket.sammle_aus_arbeitsbaum), Inhalt roh als Bytes (kein Newline-Raten)."""
    pfad: str
    modus: int
    inhalt: bytes


class Fund(NamedTuple):
    """Ein Personendaten-Fund der fail-closed-Prüfung. `zeile` ist 0 bei paketweiten Regeln
    (Pflichtdatei fehlt, kaputter Import) und bei Funden im Dateipfad, die keiner einzelnen Zeile
    zuzuordnen sind."""
    pfad: str
    zeile: int
    regel: str
    ausschnitt: str


# ── Öffentliches Repo (die einzige erlaubte Form des Kontonamens) ─────────────────────────────
# P2-82: Das BMS wird als Open Source aus einem OEFFENTLICHEN GitHub-Repo bereitgestellt; die
# Installationsanleitungen, die Update-Auskunft der App (backend/app/update_pruefen.py), das
# Update-Werkzeug (scripts/bms_update.py) und die Kunden-Doku nennen dessen Namen. Der Kontoname
# darf dort stehen -- aber NUR in dieser einen Schreibweise: Die Zeichenfolge wird vor den Regeln,
# die den Kontonamen sonst melden („Private Kontaktdaten“, Name des Nutzers), aus der Zeile bzw. dem
# String-Literal entfernt, s. `_bereinigt`. Dieselbe Konstante steht in backend/app/update_pruefen.py
# und in scripts/bms_update.py als `GITHUB_REPO` (ein Test hält alle drei gleich).
OEFFENTLICHES_REPO = "holgerdaube/BewerbungsMgmtSystem"

# Die Ausnahme ist bewusst eng: exakte Gross-/Kleinschreibung, danach darf kein Namenszeichen und
# kein weiterer Namensteil folgen (`...SystemX`, `...System-alt`, `...System.alt` bleiben Funde).
# Davor gilt eines von beiden: ein GitHub-Host (`github.com/`, `api.github.com/repos/`, ...) als
# ganzes Wort -- oder ein bloesser Wert, dem kein Namenszeichen, Punkt, Bindestrich oder "/"
# vorausgeht. Das haelt einen lokalen Pfad (`/Users/<konto>/BewerbungsMgmtSystem`), ein fremdes
# Konto (`x<konto>/...`) und einen fremden Host (`evilgithub.com/<konto>/...`) als Fund.
_OEFFENTLICHES_REPO_RE = re.compile(
    r"(?:(?<![\w.\-])(?:www\.|api\.)?github\.com/(?:repos/)?|(?<![\w./\-]))"
    + re.escape(OEFFENTLICHES_REPO)
    + r"(?![\w\-]|\.\w)"
)

# ── Spendenlinks (die zweite erlaubte Form des Kontonamens) ───────────────────────────────────
# Freiwillige Unterstuetzung: Die Seiten bei Buy Me a Coffee und PayPal.me tragen den Kontonamen.
# Die Ausnahme ist noch enger als die fuer das Repo: Sie gilt NUR in `SPENDEN_PFADE`, NUR fuer die
# Regel „Private Kontaktdaten“ zum Kontonamen (`konten`) und NUR fuer genau diese Formen:
#   README.md und FUNDING.yml:  https://buymeacoffee.com/<konto>  und  https://paypal.me/<konto>
#   nur .github/FUNDING.yml:    die ganze Zeile  buy_me_a_coffee: <konto>
# Der Kontoname ist der aus `OEFFENTLICHES_REPO`, exakt geschrieben. Ein anderer Host, `http://`,
# `www.`, ein Pfad oder Parameter dahinter, ein laengerer Name und dieselbe Adresse in jeder anderen
# Datei bleiben Funde. Name, Anschrift, Mail, Telefon und Dritte laufen in beiden Dateien weiter.
SPENDEN_PFADE: tuple[str, ...] = ("README.md", "README.de.md", ".github/FUNDING.yml")
_SPENDEN_KONTO = OEFFENTLICHES_REPO.split("/", 1)[0]
_SPENDEN_URL_RE = re.compile(
    r"(?<![\w.\-/:])https://(?:buymeacoffee\.com|paypal\.me)/"
    + re.escape(_SPENDEN_KONTO)
    + r"(?![\w\-/?#]|\.\w)"
)
_SPENDEN_FUNDING_RE = re.compile(r"^buy_me_a_coffee:[ \t]*" + re.escape(_SPENDEN_KONTO) + r"[ \t]*$")

# Marke und Domain des Herausgebers: zaehlt nicht als Nachname, auch nicht mit Bindestrich,
# Unterstrich oder Leerzeichen statt des Punkts. Ohne Trenner geschrieben trifft die Namensregel die
# Marke ohnehin nicht, weil dort Buchstaben am Wort kleben.
MARKE = "Daube.Tech"
_MARKE_RE = re.compile(r"[\s._\-]?".join(re.escape(teil) for teil in MARKE.split(".")), re.IGNORECASE)

# ── Allgemeine Muster (kein Personenbezug, bleiben im Code) ───────────────────────────────────
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Eine deutsche Nummer: +49 und danach mindestens sechs Ziffern (Leerzeichen, "/" und "-" dazwischen sind
# erlaubt). Kuerzere Reste wie „+49 170 1“ sind Platzhalter in Beispielen, keine Nummer.
_TELEFON_RE = re.compile(r"\+49(?:[\s/-]*\d){6,}")
# Beispielnummer der Beispieldaten (app/beispieldaten.py); sie steht auch in der Profil-Vorlage der
# Anleitungen (BMS_Install_MAC.md/BMS_Install_Windows.md). Verglichen wird nur die Ziffernfolge, die
# Schreibweise (Leerzeichen, Striche) ist egal.
_ERLAUBTE_TELEFON_BEISPIEL = "+49 170 1234567"
_ERLAUBTE_TELEFON_ZIFFERN = re.sub(r"\D", "", _ERLAUBTE_TELEFON_BEISPIEL)
# Bestands-IDs in JEDER ausgelieferten Textdatei: ein Wort aus dieser Liste, gefolgt von einer Nummer
# (mit oder ohne Leerzeichen und "#"). "Jobs?"/"Mails?"/"Tasks?" deckt Singular UND Plural der
# englischen Leihwoerter ab, "Lauf"/"Läufe" die deutsche Form -- Bewerbung/Firma bleiben nur singular.
_BESTANDS_ID_RE = re.compile(r"\b(?:Jobs?|Mails?|Tasks?|Bewerbung|Firma|Läufe|Lauf)\s?#?\d{2,}\b")

# Muster fuer einen absoluten BENUTZER-Pfad: "~" und "$HOME" bleiben immer, die gelten auf jedem
# Rechner. Dient der Regel „Absoluter Benutzerpfad“ (Umfang oeffentlich) und dem Neutralisieren von
# automation/agent_settings.json in kundenpaket.py.
ABSOLUTER_PFAD_RE = re.compile(r"/Users/|/home/|[Cc]:\\Users|[Cc]:/Users")
# Fuer die Regel selbst mit dem Kontonamen dahinter (Gruppe 1). Doppelte Rueckwaertsschraegstriche
# (JSON, Python-Strings) zaehlen mit.
_BENUTZERPFAD_RE = re.compile(
    r"(?:(?<![\w.])/(?:Users|home)/|(?<![\w])[A-Za-z]:[\\/]+Users[\\/]+)([^\\/\s\"'`)<>|,;:*?]+)"
)
# Kontonamen in Beispielen, die auf keinen Menschen zeigen.
_BENUTZERPFAD_PLATZHALTER: frozenset[str] = frozenset({
    "name", "username", "user", "benutzer", "benutzername", "ihrname", "ihr-name", "dein-name",
    "mustermann", "maxmustermann", "max.mustermann", "max_mustermann", "shared", "public", "default",
    "runner", "runneradmin", "xxx", "...",
})
_BENUTZERPFAD_PLATZHALTER_ANFANG = ("<", "$", "%", "{", "[", "~", "…", "*")

# Allgemeine Platzhalter-Domains (RFC-2606-Beispieldomains + deutsche Konvention "firma.de")
# fuer Beispieladressen in Doku und Skills -- nie eine echte, erreichbare Domain. Eine Domain
# gilt als erlaubt, wenn sie einer davon GLEICHT oder auf ".<erlaubte Domain>" ENDET
# (personalberatung.example.de ok, example.de.boese.com nicht -- s. _domain_erlaubt).
ERLAUBTE_DOMAINS: tuple[str, ...] = (
    "example.com", "example.net", "example.org", "example.de", "beispiel.de", "firma.de",
)

# Die fuer Beispiele reservierten Endungen nach RFC 2606 (.example, .invalid, .test, .localhost): Es gibt
# dazu nie eine echte Domain, jede Adresse darauf ist erfunden.
_RESERVIERTE_ENDUNGEN: frozenset[str] = frozenset({"example", "invalid", "test", "localhost"})

# Einzelne erlaubte Adressen, die NICHT unter eine der Domains oben fallen: die offizielle
# Support-Adresse, generische Beispieladressen aus Doku/Skills, und die Systemabsender, auf die sich
# LinkedIn- bzw. ATS-Suchregeln FUNKTIONAL stuetzen (die bleiben deshalb woertlich erhalten).
ERLAUBTE_ADRESSEN: frozenset[str] = frozenset(a.lower() for a in (
    "info@daube.tech",
    "a@b.de", "c@d.de", "ich@gmx.de",
    "jobalerts-noreply@linkedin.com", "jobs-listings@linkedin.com", "jobs-noreply@linkedin.com",
    "newsletters-noreply@linkedin.com", "notifications-noreply@linkedin.com",
    "messaging-digest-noreply@linkedin.com",
    "no-reply@ashbyhq.com", "no-reply@us.greenhouse-mail.io", "notification@smartrecruiters.com",
    "no-reply@screenloop.com", "notifications@mail3.guide.co",
    # Testadressen fuer die Anbieter-/Absender-Erkennung, kein Personenbezug: Die Tests der Sperrlisten
    # (test_mail_suchlisten.py) brauchen einen ATS-Absender, eine Freemail-Adresse und einen
    # Portal-Absender in ihrer echten Domain, weil die Erkennung an der Domain haengt. Bewusst einzelne
    # Adressen und NICHT die Domains: `gmail.com` in ERLAUBTE_DOMAINS liesse jede private Adresse durch.
    "noreply@myworkday.com", "jemand@gmail.com", "info@mail.stepstone.de",
))

# Dateien, in denen im Umfang „paket“ selbst das blosse WORT des Nutzernamens ein Kunden-Leck waere
# (Kundentexte i. e. S. -- Doku, Oberflaeche, Skills). Praefix mit "/" = ganzer Ordner, sonst
# exakter Pfad.
NAME_KUNDENTEXT_PFADE: tuple[str, ...] = (
    ".claude/", "docs/", "assets/", "BMS_Install_MAC.md", "BMS_Install_Windows.md", "BMS_Install_MAC.en.md",
    "BMS_Install_Windows.en.md", "README.md", "README.de.md", "CHANGELOG.md", "CHANGELOG.en.md",
    "frontend/index.html", "automation/agent_settings.json",
)

# Zuschreibungsliste (Leitentscheidung 4): Hier gehoert der Name des Autors hin. Gilt NUR fuer die
# Namensregel im Umfang „oeffentlich“; alle anderen Regeln laufen in diesen Dateien weiter.
# Ganze Dateien:
ZUSCHREIBUNG_PFADE: tuple[str, ...] = ("NOTICE", "LICENSE", "frontend/src/rechtliches/ueber.md",
                                       "frontend/src/rechtliches/ueber.en.md")
# README (englisch und deutsch, P2-92): nur die Abschnitte, deren Ueberschrift eines dieser Woerter
# enthaelt, samt ihren Unterabschnitten.
ZUSCHREIBUNG_ABSCHNITT_PFADE: tuple[str, ...] = ("README.md", "README.de.md")
_ZUSCHREIBUNG_UEBERSCHRIFTEN: tuple[str, ...] = ("autor", "lizenz", "urheber", "author", "licence", "license")

# PFADGEBUNDENE Ausnahme fuer fremden WORTLAUT (P2-77): `drittlizenzen_texte.txt` gibt die
# Lizenztexte der mitinstallierten Pakete UNVERAENDERT wieder -- Wortlaut fremder Lizenzen,
# Copyright-Hinweise duerfen nicht veraendert werden. Dort stehen Autoren-Adressen und Copyright-
# Zeilen mit Firmennamen und Personennamen. Fuer genau diese Pfade entfallen DESHALB drei Regeln und
# nur diese: „E-Mail-Adressen“, „Firmennamen aus dem Bewerbungsverlauf“ und (Umfang oeffentlich)
# der Name des Nutzers -- ein Paketautor mit gleichem Vornamen darf im Lizenztext stehen. Alle uebrigen
# Regeln (Kontaktdaten, Dritte Personen, Telefon, Bestands-IDs ...) laufen weiter. Exakte Pfade, kein
# Muster: Die erzeugte Uebersicht drittlizenzen.md enthaelt keinen fremden Wortlaut und bleibt voll
# geprueft.
_FREMDER_WORTLAUT: tuple[str, ...] = ("frontend/src/rechtliches/drittlizenzen_texte.txt",)

# ── Firmennamen aus dem Bewerbungsverlauf (nur lokal gegen eine echte Datenbank) ──────────────
# Rechtsformen, die vom Firmennamen-ENDE abgetrennt werden, bevor er als Suchbegriff dient --
# mehrteilige ZUERST, sonst stoppt das Abtrennen schon bei "KG"/"KGaA" und laesst " & Co."
# haengen (s. _firmenname_kernform).
_RECHTSFORMEN: tuple[str, ...] = (
    "GmbH & Co. KGaA", "GmbH & Co. KG", "SE & Co. KGaA", "SE & Co. KG", "AG & Co. KGaA", "AG & Co. KG",
    "GmbH", "gGmbH", "mbH", "KGaA", "AG", "SE", "KG",
    "Inc.", "Inc", "Ltd.", "Ltd", "LLC", "plc", "PLC",
    "N.V.", "S.A.", "AB", "A/S", "Oy", "SARL", "Sarl", "s.r.o.",
)

# Unter dieser Laenge (nach Abtrennen der Rechtsform) prueft die Regel NICHT mehr -- ein Bestand
# enthaelt etliche Zwei- bis Vierbuchstaben-Namen, die als ganzes Wort in normalem Flusstext viel zu
# haeufig zufaellig auftauchen (Abkuerzungen, gewoehnliche Woerter). Ab 5 Zeichen plus
# GROSS-/KLEINSCHREIBUNGS-GENAUER Vergleich (kein IGNORECASE) blieben keine Fehltreffer aus
# normalem Flusstext uebrig, nur echte Nennungen.
_FIRMEN_MINDESTLAENGE = 5

# Funktionale Nennungen: kommen zufaellig auch im Bestand vor, stehen im ausgelieferten Produkt aber
# aus einem GANZ ANDEREN, legitimen Grund (Portal/ATS/Infrastruktur) -- kein Verlaufsleck.
ERLAUBTE_FIRMENNAMEN: frozenset[str] = frozenset({
    # Jobportale: als Job.portal-Wert durchgaengig in Ingest/Scoring/Oberflaeche. Jobgether zusaetzlich:
    # eigene Alert-Quelle neben LinkedIn/Xing im mail-jobsuche-Skill.
    "LinkedIn", "Indeed", "StepStone", "Xing", "Jobgether",
    # ATS (Bewerbermanagementsysteme): Parser-/Normalisierungslogik nennt sie beim Namen; ihre
    # Mail-Domains stehen bereits oben in ERLAUBTE_ADRESSEN als funktionaler Gmail-Suchfilter.
    "Workday", "Personio",
    # Infrastruktur/Grossanbieter: Google (Drive-Export/-Tracker, OAuth fuer Gmail), Microsoft
    # (Outlook-Einschraenkung in der Doku), Apify (Scraping-Actors), Anthropic (Claude selbst).
    "Google", "Microsoft", "Apify", "Anthropic",
})

# Werte, die technisch in einer der Namensspalten stehen koennen, aber KEIN Firmenname sind --
# reine Platzhalter/Sentinel-Zeichenketten der eigenen Datenmodellierung. "Unbekannt" ist der
# App-weite Ausweichwert bei ungeloester Zuordnung.
_KEIN_ECHTER_FIRMENNAME: frozenset[str] = frozenset({"unbekannt"})

# PFADGEBUNDENE Ausnahme fuer Persona-Dateien -- getrennt von ERLAUBTE_FIRMENNAMEN: Ein Firmenname aus
# dem Bestand kann zufaellig auch der Nachname einer fiktiven Beirats-Persona sein (eigene
# Denkschul-Figur des Produkts, Fiktions-Disclaimer in jeder Datei, s. .claude/agents/beirat-*.md).
# Der Nachname (letzter Teil des Dateinamens `beirat-<vorname>-<nachname>.md`, s. `_persona_nachnamen`)
# bleibt deshalb NUR in diesen Pfaden erlaubt, in denen er nachweislich die Persona meint; anderswo
# (Code-Kommentare, sonstige Doku) bleibt er ein Fund. Muster wie ANPASSBAR: fnmatch, Git-Pfade.
_PERSONA_DATEIEN = ".claude/agents/beirat-*.md"
_PERSONA_PFADE: tuple[str, ...] = (
    _PERSONA_DATEIEN,
    ".claude/commands/beirat-basis.md",
    "docs/BEIRAT-CHARTA.md",
    "docs/BEIRAT-CHARTA.html",
    "docs/en/BEIRAT-CHARTA.md",
    "docs/en/BEIRAT-CHARTA.html",
)

# Tabelle -> Spalte, exakt wie models.py sie fuehrt (Company.name, Job.company_name,
# TargetCompany.company, Headhunter.firma).
_FIRMEN_SPALTEN: tuple[tuple[str, str], ...] = (
    ("company", "name"), ("job", "company_name"), ("targetcompany", "company"), ("headhunter", "firma"),
)

# ── Namen Dritter aus der Kontakttabelle ─────────────────────────────────────────────────────
# Kontaktnamen sind oft keine Personen („Recruiting Team“, „HR Jobs“). Ein Name wird nur uebernommen,
# wenn er nach Personenname aussieht: mindestens zwei Woerter, jedes gross geschrieben (Namenszusaetze
# wie „von“ klein), ohne Ziffern und ohne eines dieser Woerter.
_KONTAKT_STOPWOERTER: frozenset[str] = frozenset({
    "team", "recruiting", "recruiter", "recruitment", "hr", "human", "resources", "people", "culture",
    "jobs", "job", "karriere", "career", "careers", "talent", "acquisition", "hiring", "sourcing",
    "support", "service", "kundenservice", "info", "personal", "personalabteilung", "bewerbung",
    "bewerbungen", "bewerbermanagement", "noreply", "no-reply", "mail", "office", "sekretariat",
    "empfang", "kontakt", "contact", "unbekannt", "anonymous", "hello", "hallo", "admin", "system",
    "manager", "management", "abteilung", "department", "group", "gruppe", "bewerber",
})
_NAMENSZUSAETZE: frozenset[str] = frozenset({
    "van", "von", "de", "der", "den", "da", "di", "du", "la", "le", "zu", "zur", "ten", "ter", "bin",
    "al", "el", "dos", "das", "vom", "af", "of",
})
_NAMENSWORT_RE = re.compile(r"^[A-ZÄÖÜ][\w'’.\-]*$")
_TITEL: frozenset[str] = frozenset({"dr", "prof", "dipl", "ing", "mag", "mba", "msc", "bsc", "ma", "ba"})

# Typische Strassen-Endungen: ordnen einen Begriff aus pruefmuster.txt der Regel „Anschrift“ zu.
_STRASSEN_ENDUNG_RE = re.compile(
    r"(?:stra(?:ß|ss)e|str\.?|weg|platz|allee|gasse|ring|ufer|damm|chaussee|pfad)$", re.IGNORECASE)
_STRASSEN_SUFFIXE: tuple[str, ...] = ("straße", "strasse", "str")

_MIN_BEGRIFF = 3          # kuerzere Begriffe aus pruefmuster.txt und dem Profil zaehlen nicht
_NICHT_BUCHSTABE_DAVOR = r"(?<![^\W\d_])"     # kein Buchstabe davor
_NICHT_BUCHSTABE_DANACH = r"(?![^\W\d_])"     # kein Buchstabe dahinter


# ── Muster ───────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True, repr=False)
class Muster:
    """Die persönlichen Prüfmuster eines Nutzers, gesammelt zur Laufzeit (s. `muster_laden`).

    Alle Felder sind Begriffe im Klartext (keine Regexe); `pruefen` baut die Suchmuster daraus. Ein
    leeres `Muster()` schaltet die persönlichen Regeln ab, die allgemeinen laufen weiter.

      anschrift  Straße (samt Schreibvarianten) und Postleitzahl
      kontakt    private Mailadressen (auch Vorderteil mit „@“), LinkedIn-Pfade, Begriffe aus der Musterdatei
      telefon    private Telefonnummern wie im Profil geschrieben
      konten     Kontoname (Vor- plus Nachname zusammen, klein), nur gross-/kleinschreibungsgenau
      namen      Vor- und Nachname des Nutzers
      dritte     Namen Dritter (Kontakte der Datenbank, Begriffe aus der Musterdatei)
      firmen     Kernformen der Firmennamen aus dem Bewerbungsbestand
      vollstaendig  wahr, wenn Profil UND Datenbank gelesen wurden
    """
    anschrift: tuple[str, ...] = ()
    kontakt: tuple[str, ...] = ()
    telefon: tuple[str, ...] = ()
    konten: tuple[str, ...] = ()
    namen: tuple[str, ...] = ()
    dritte: tuple[str, ...] = ()
    firmen: tuple[str, ...] = ()
    vollstaendig: bool = False
    profil_gelesen: bool = False
    datenbank_gelesen: bool = False
    extra_gelesen: bool = False
    db_pfad: Path | None = None
    hinweise: tuple[str, ...] = ()

    def __repr__(self) -> str:
        # Bewusst nur Zahlen: ein Muster darf nie in einer Fehlermeldung oder einem Log landen.
        return (f"Muster(vollstaendig={self.vollstaendig}, anschrift={len(self.anschrift)}, "
                f"kontakt={len(self.kontakt)}, telefon={len(self.telefon)}, konten={len(self.konten)}, "
                f"namen={len(self.namen)}, dritte={len(self.dritte)}, firmen={len(self.firmen)})")


def datenbank_pfad(projekt_root: Path) -> Path:
    """Wo die lokale Datenbank liegt: `BMS_DATA_DIR` (wie die App), sonst `data/` im Projekt."""
    basis = os.environ.get("BMS_DATA_DIR")
    ordner = Path(basis) if basis else Path(projekt_root) / "data"
    return ordner / "bewerbung.sqlite"


def pruefmuster_pfad() -> Path:
    """Wo die optionale Musterdatei liegt: `BMS_SECRETS_DIR` (wie die App), sonst
    `~/.bewerbung_mgmt_secrets/`. Zur Laufzeit gelesen, damit Tests die Umgebung setzen koennen."""
    basis = os.environ.get("BMS_SECRETS_DIR")
    ordner = Path(basis) if basis else Path.home() / ".bewerbung_mgmt_secrets"
    return ordner / "pruefmuster.txt"


def _eindeutig(begriffe: list[str], *, gross_klein_egal: bool) -> tuple[str, ...]:
    """Entfernt Dopplungen (bei Bedarf ohne Beachtung der Schreibweise) und zu kurze Begriffe,
    behaelt die Reihenfolge des ersten Auftretens."""
    gesehen: set[str] = set()
    ergebnis = []
    for b in begriffe:
        b = " ".join(b.split())
        schluessel = b.lower() if gross_klein_egal else b        # lower, nicht casefold: ß bleibt von ss verschieden
        if len(b) < _MIN_BEGRIFF or schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        ergebnis.append(b)
    return tuple(ergebnis)


# ── Profil ───────────────────────────────────────────────────────────────────────────────────

def _profil_identitaet(pfad: Path) -> dict | None:
    try:
        text = pfad.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return profil_datei.lesen_aus_text(text).get("identitaet") or {}


def _namensteile(name: str) -> list[str]:
    """Vor- und Nachname aus dem Namensfeld: erstes und letztes Wort, ohne Titel und Kuerzel mit
    Punkt („Dr.“, „M.“); Woerter unter drei Zeichen zaehlen nicht (zu haeufig im Fliesstext)."""
    woerter = [w for w in name.split() if not w.endswith(".") and w.casefold() not in _TITEL]
    woerter = [w.strip(",;") for w in woerter]
    woerter = [w for w in woerter if len(w) >= _MIN_BEGRIFF]
    if not woerter:
        return []
    return [woerter[0]] if len(woerter) == 1 else [woerter[0], woerter[-1]]


def _anschrift_begriffe(anschrift: str) -> list[str]:
    """Straße (ohne Hausnummer, samt Schreibvarianten ‚straße/strasse/str‘) und Postleitzahl aus einer
    Anschrift wie „Musterweg 1, 12345 Musterstadt (Zusatz)“. Die Stadt allein ist kein Muster
    (zu gewoehnlich); eine Anschrift ohne Strasse und PLZ ergibt keine Begriffe."""
    text = re.sub(r"\s*\([^)]*\)\s*$", "", anschrift or "").strip()
    begriffe: list[str] = []
    for teil in re.split(r"[,;|·]", text):
        teil = teil.strip()
        if not teil:
            continue
        plz = re.match(r"^(\d{5})(?!\d)", teil)
        if plz:
            begriffe.append(plz.group(1))
            continue
        strasse = re.match(r"^(?P<name>.+?)\s+\d+\s*[a-zA-Z]?(?:\s*[-–/]\s*\d+\s*[a-zA-Z]?)?$", teil)
        if strasse:
            name = strasse.group("name").strip()
        elif _STRASSEN_ENDUNG_RE.search(teil):
            name = teil
        else:
            continue
        begriffe.append(name)
        # Schreibvarianten: Musterstraße / Musterstrasse / Musterstr (die Variante ohne Punkt trifft
        # auch „Musterstr.“, der Punkt ist dann Wortende).
        m = re.match(r"^(?P<stamm>.+?)(?:stra(?:ß|ss)e|str)\.?$", name, re.IGNORECASE)
        if m and m.group("stamm").strip():
            begriffe += [m.group("stamm") + suffix for suffix in _STRASSEN_SUFFIXE]
    return begriffe


def _linkedin_pfad(wert: str) -> str | None:
    """`linkedin.com/in/<name>` aus der Profil-Angabe (URL oder nur der Name); sonst None."""
    wert = (wert or "").strip()
    if not wert:
        return None
    m = re.search(r"linkedin\.com/in/([^/?#\s]+)", wert, re.IGNORECASE)
    if m:
        return f"linkedin.com/in/{m.group(1)}"
    if re.fullmatch(r"[\w\-%.]+", wert):
        return f"linkedin.com/in/{wert}"
    return None


def _telefon_regex(roh: str) -> str | None:
    """Suchmuster fuer eine Telefonnummer in jeder ueblichen Schreibweise (Leerzeichen, Klammern,
    Punkte, Striche, Schraegstriche zwischen den Ziffern; +49, 0049 oder 0 vorn). None bei zu wenigen
    Ziffern oder bei der Beispielnummer der Anleitungen."""
    ziffern = re.sub(r"\D", "", roh or "")
    if len(ziffern) < 6:
        return None
    beispiel_kern = re.sub(r"\D", "", _ERLAUBTE_TELEFON_BEISPIEL)[2:]
    trenner = r"[\s().\-/]*"
    international = (roh or "").strip().startswith("+") or ziffern.startswith("00")
    if international and ziffern.startswith("00"):
        ziffern = ziffern[2:]
    if international and not ziffern.startswith("49"):
        kern, vorn = ziffern, r"(?:\+|00)\s*"
    else:
        if international:
            ziffern = ziffern[2:]                     # Landesvorwahl 49
        kern, vorn = ziffern.lstrip("0"), r"(?:\+\s*49|0049|0)(?:\s*\(0\))?"
    if len(kern) < 5 or kern == beispiel_kern:
        return None
    return r"(?<!\d)" + vorn + trenner + trenner.join(re.escape(z) for z in kern) + r"(?!\d)"


def _kontakt_begriffe(email: str) -> list[str]:
    """Aus der Profil-Mailadresse: die ganze Adresse und ihr Vorderteil mit „@“ (dasselbe Postfach
    bei einem anderen Anbieter). Die offizielle Support-Adresse (ERLAUBTE_ADRESSEN) zaehlt nicht."""
    email = (email or "").strip()
    if "@" not in email or email.casefold() in ERLAUBTE_ADRESSEN:
        return []
    vorn = email.split("@", 1)[0]
    return [email, vorn + "@"]


# ── Datenbank ────────────────────────────────────────────────────────────────────────────────

def _db_lesen(db: Path) -> tuple[list[str], list[str]] | None:
    """Liest die Namensspalten und die Kontaktnamen NUR LESEND (sqlite-URI-Modus „ro“ -- niemals
    Schreibzugriff auf die echte Installation) und roh. Bewusst ohne SQLModel/`app.db`: das Werkzeug
    bleibt unabhaengig vom App-Schema-Code, ein SELECT auf bekannte Tabellen/Spalten braucht kein ORM.
    Eine fehlende Tabelle wird uebersprungen (aeltere Schemas); lieferte keine einzige Abfrage etwas,
    ist die Datei keine BMS-Datenbank: None."""
    try:
        conn = sqlite3.connect(f"{Path(db).resolve().as_uri()}?mode=ro", uri=True)
    except (sqlite3.Error, OSError, ValueError):
        return None
    try:
        firmen: list[str] = []
        kontakte: list[str] = []
        gelesen = 0
        for tabelle, spalte, ziel in [(t, s, firmen) for t, s in _FIRMEN_SPALTEN] + [("contact", "name", kontakte)]:
            try:
                zeilen = conn.execute(
                    f"SELECT DISTINCT {spalte} FROM {tabelle} WHERE {spalte} IS NOT NULL").fetchall()
            except sqlite3.Error:
                continue
            gelesen += 1
            ziel.extend(wert for (wert,) in zeilen if isinstance(wert, str) and wert.strip())
        return (firmen, kontakte) if gelesen else None
    finally:
        conn.close()


def _firmenname_kernform(roh: str) -> str | None:
    """Trennt eine Rechtsform vom Ende ab (falls vorhanden) und trimmt Reste wie ", " oder "."
    danach ab -- "Muster Logistics, Inc." wird so zu "Muster Logistics". None, wenn danach nichts
    Sinnvolles oder nur ein zu kurzer Rest uebrig bleibt (_FIRMEN_MINDESTLAENGE)."""
    name = roh.strip()
    if not name:
        return None
    for rf in _RECHTSFORMEN:
        if name.endswith(rf):
            rest = name[: -len(rf)].rstrip(" ,.-")
            if rest:
                name = rest
            break
    name = name.strip()
    if len(name) < _FIRMEN_MINDESTLAENGE:
        return None
    return name


def _firmennamen_suchbegriffe(roh_namen: list[str]) -> list[str]:
    """Kernform bilden, ERLAUBTE_FIRMENNAMEN und _KEIN_ECHTER_FIRMENNAME herausnehmen,
    deduplizieren -- laengste zuerst (bei ueberlappenden Namen gewinnt sonst zufaellig der kuerzere
    Alternativzweig der Regex)."""
    kerne = {
        kern for roh in roh_namen
        if (kern := _firmenname_kernform(roh)) is not None
        and kern not in ERLAUBTE_FIRMENNAMEN
        and kern.lower() not in _KEIN_ECHTER_FIRMENNAME
    }
    return sorted(kerne, key=len, reverse=True)


def _ist_personenname(name: str) -> bool:
    """Sieht ein Kontaktname nach einem Personennamen aus (s. `_KONTAKT_STOPWOERTER`)?"""
    if len(name) > 60 or any(c in name for c in "@/\\0123456789"):
        return False
    woerter = name.split()
    if len(woerter) < 2:
        return False
    for w in woerter:
        if w.casefold().strip(".,") in _KONTAKT_STOPWOERTER:
            return False
        if w in _NAMENSZUSAETZE:
            continue
        if not _NAMENSWORT_RE.match(w):
            return False
    return True


def _kontaktnamen(roh: list[str], eigener_name: str) -> list[str]:
    ergebnis = []
    eigener = " ".join(eigener_name.split()).casefold()
    for n in roh:
        n = re.sub(r"\s*[\(\[].*$", "", n).strip().strip(",;")
        n = " ".join(n.split())
        if n.casefold() != eigener and _ist_personenname(n):
            ergebnis.append(n)
    return ergebnis


# ── Musterdatei ──────────────────────────────────────────────────────────────────────────────

def _extra_lesen(pfad: Path) -> list[str] | None:
    try:
        text = pfad.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    return [z.strip() for z in text.splitlines() if z.strip() and not z.strip().startswith("#")]


def _extra_zuordnen(begriffe: list[str]) -> tuple[list[str], list[str], list[str]]:
    """(anschrift, kontakt, dritte) nach der Form des Begriffs, s. Moduldoc (c)."""
    anschrift: list[str] = []
    kontakt: list[str] = []
    dritte: list[str] = []
    for b in begriffe:
        if "@" in b or "linkedin." in b.casefold() or "://" in b:
            kontakt.append(b)
        elif re.search(r"\d", b) or _STRASSEN_ENDUNG_RE.search(b):
            anschrift.append(b)
        else:
            dritte.append(b)
    return anschrift, kontakt, dritte


def muster_laden(projekt_root: Path, *, db_pfad: Path | None = None,
                 extra: Path | None = None) -> Muster:
    """Sammelt die persoenlichen Pruefmuster aus den lokalen Quellen (Moduldoc). `projekt_root`:
    Wurzel mit `config/profil.md`. `db_pfad`: die Datenbank (Vorgabe `BMS_DATA_DIR` bzw.
    `<projekt_root>/data/bewerbung.sqlite`). `extra`: die Musterdatei (Vorgabe `pruefmuster_pfad()`).

    Wirft nie wegen einer fehlenden oder kaputten Quelle: Was fehlt, steht in `Muster.hinweise`, und
    `vollstaendig` ist dann falsch. Die Musterdatei ist freiwillig und beruehrt `vollstaendig` nicht.
    Das Profil zaehlt als gelesen, wenn es existiert UND einen Namen enthaelt."""
    wurzel = Path(projekt_root)
    hinweise: list[str] = []
    anschrift: list[str] = []
    kontakt: list[str] = []
    telefon: list[str] = []
    konten: list[str] = []
    namen: list[str] = []
    dritte: list[str] = []
    firmen: list[str] = []

    # (a) Profil
    ident = _profil_identitaet(wurzel / "config" / "profil.md")
    profil_gelesen = False
    eigener_name = ""
    if ident is None:
        hinweise.append("Das Profil (config/profil.md) fehlt oder ist nicht lesbar.")
    else:
        eigener_name = (ident.get("name") or "").strip()
        teile = _namensteile(eigener_name)
        if not teile:
            hinweise.append("Das Profil enthaelt keinen Namen (Feld „Name“).")
        else:
            profil_gelesen = True
            namen += teile
            if len(teile) == 2:
                # Kontoname (Vor- plus Nachname zusammen) und Mail-Vorderteil vorname.nachname@
                konten.append("".join(teile).casefold())
                kontakt.append(f"{teile[0]}.{teile[1]}@")
        anschrift += _anschrift_begriffe(ident.get("anschrift") or "")
        kontakt += _kontakt_begriffe(ident.get("email") or "")
        linkedin = _linkedin_pfad(ident.get("linkedin") or "")
        if linkedin:
            kontakt.append(linkedin)
        if _telefon_regex(ident.get("telefon") or "") is not None:
            telefon.append(ident["telefon"].strip())

    # (b) Datenbank
    db = Path(db_pfad) if db_pfad is not None else datenbank_pfad(wurzel)
    datenbank_gelesen = False
    gelesen_db: Path | None = None
    if not db.is_file():
        hinweise.append("Die Datenbank (data/bewerbung.sqlite) fehlt.")
    else:
        inhalt = _db_lesen(db)
        if inhalt is None:
            hinweise.append("Die Datenbank ist nicht lesbar oder keine BMS-Datenbank.")
        else:
            datenbank_gelesen = True
            gelesen_db = db
            firmen += _firmennamen_suchbegriffe(inhalt[0])
            dritte += _kontaktnamen(inhalt[1], eigener_name)

    # (c) Musterdatei
    extra_pfad = Path(extra) if extra is not None else pruefmuster_pfad()
    extra_begriffe = _extra_lesen(extra_pfad) if extra_pfad.is_file() else None
    if extra_begriffe is not None:
        a, k, d = _extra_zuordnen(extra_begriffe)
        anschrift += a
        kontakt += k
        dritte += d

    return Muster(
        anschrift=_eindeutig(anschrift, gross_klein_egal=True),
        kontakt=_eindeutig(kontakt, gross_klein_egal=True),
        telefon=tuple(telefon),
        konten=_eindeutig(konten, gross_klein_egal=False),
        namen=_eindeutig(namen, gross_klein_egal=True),
        dritte=_eindeutig(dritte, gross_klein_egal=True),
        firmen=tuple(firmen),
        vollstaendig=profil_gelesen and datenbank_gelesen,
        profil_gelesen=profil_gelesen,
        datenbank_gelesen=datenbank_gelesen,
        extra_gelesen=extra_begriffe is not None,
        db_pfad=gelesen_db,
        hinweise=tuple(hinweise),
    )


# ── Suchmuster aus einem Muster ──────────────────────────────────────────────────────────────

def _wortmuster(begriff: str) -> str:
    """Begriff als Regex-Text; Leerraum zwischen Woertern passt auf beliebig viel Leerraum."""
    return r"\s+".join(re.escape(teil) for teil in begriff.split())


def _alternativen(begriffe) -> str:
    return "|".join(_wortmuster(b) for b in sorted(begriffe, key=len, reverse=True))


class _Regeln:
    """Aus einem `Muster` gebaute Suchmuster (einmal je `pruefen`-Aufruf). Ein leeres Feld ergibt
    None: die Regel entfaellt."""

    def __init__(self, m: Muster, persona: frozenset[str] = frozenset()):
        self.persona = persona
        # Anschrift: ganze Woerter, Schreibweise egal
        self.anschrift = (re.compile(r"(?<!\w)(?:" + _alternativen(m.anschrift) + r")(?!\w)", re.IGNORECASE)
                          if m.anschrift else None)
        # Kontakt: Teilstring, Schreibweise egal; ein Mail-Vorderteil darf nicht mitten in einem
        # laengeren Mail-Namen beginnen
        teile = []
        for b in sorted(m.kontakt, key=len, reverse=True):
            vorn = r"(?<![\w.+%\-])" if "@" in b else ""
            teile.append(vorn + re.escape(b))
        self.kontakt = re.compile("|".join(teile), re.IGNORECASE) if teile else None
        self.konten = (re.compile("|".join(re.escape(k) for k in sorted(m.konten, key=len, reverse=True)))
                       if m.konten else None)
        telefone = [r for t in m.telefon if (r := _telefon_regex(t))]
        self.telefon = re.compile("|".join(telefone)) if telefone else None
        self.dritte = self._namensregex(m.dritte)
        self.name = self._namensregex(m.namen)
        self.firmen = (re.compile(r"(?<!\w)(?:" + "|".join(re.escape(f) for f in m.firmen) + r")(?!\w)")
                       if m.firmen else None)

    @staticmethod
    def _namensregex(namen) -> re.Pattern | None:
        if not namen:
            return None
        return re.compile(
            _NICHT_BUCHSTABE_DAVOR + "(?:" + _alternativen(namen) + ")" + r"(?:[’']?s)?" + _NICHT_BUCHSTABE_DANACH,
            re.IGNORECASE)


# ── Hilfsfunktionen: Pfad-Matching und Texte ─────────────────────────────────────────────────

def pfad_trifft(pfad: str, muster: tuple[str, ...]) -> bool:
    """Ein Muster, das auf '/' endet, ist ein Ordner-Praefix; sonst ein exakter Pfad. Git-Pfade."""
    for m in muster:
        if m.endswith("/"):
            if pfad.startswith(m):
                return True
        elif pfad == m:
            return True
    return False


def _persona_nachnamen(eintraege: list[Eintrag]) -> frozenset[str]:
    """Nachnamen der Beirats-Personas aus den Dateinamen `.claude/agents/beirat-<vorname>-<nachname>.md`
    unter `eintraege` (gross geschrieben, wie im Text). Leer, wenn keine Persona-Datei dabei ist."""
    namen = set()
    for e in eintraege:
        if fnmatch.fnmatch(e.pfad, _PERSONA_DATEIEN):
            teile = e.pfad.rsplit("/", 1)[-1].removesuffix(".md").split("-")
            if len(teile) >= 3:
                namen.add(teile[-1].capitalize())
    return frozenset(namen)


def _firmenname_ausnahme_erlaubt(wort: str, pfad: str, persona: frozenset[str]) -> bool:
    return wort in persona and any(fnmatch.fnmatch(pfad, m) for m in _PERSONA_PFADE)


def _ausschnitt(zeilen: list[str], zeile: int, max_laenge: int = 160) -> str:
    if zeile < 1 or zeile > len(zeilen):
        return ""
    s = zeilen[zeile - 1].strip()
    return s if len(s) <= max_laenge else s[: max_laenge - 1] + "…"


def _ohne_oeffentliches_repo(text: str) -> str:
    """Entfernt NUR den Namen des oeffentlichen Repos (`OEFFENTLICHES_REPO`, samt GitHub-Host davor,
    falls er da steht) aus `text` -- ersetzt durch ein Leerzeichen, damit nichts zu einem neuen
    Treffer zusammenwachsen kann. Alles andere mit dem Kontonamen bleibt stehen (P2-82)."""
    return _OEFFENTLICHES_REPO_RE.sub(" ", text)


def _ohne_spendenlinks(pfad: str) -> Callable[[str], str]:
    """Vorbehandlung fuer die Kontonamen-Regel in `pfad`: ohne Repo-Namen und, NUR in `SPENDEN_PFADE`,
    ohne die Spendenlinks (s. dort). In jeder anderen Datei genau `_ohne_oeffentliches_repo`."""
    if pfad not in SPENDEN_PFADE:
        return _ohne_oeffentliches_repo

    def vorbehandlung(zeile: str) -> str:
        zeile = _SPENDEN_URL_RE.sub(" ", _ohne_oeffentliches_repo(zeile))
        if pfad == ".github/FUNDING.yml":
            zeile = _SPENDEN_FUNDING_RE.sub(" ", zeile)
        return zeile

    return vorbehandlung


def _bereinigt(text: str) -> str:
    """Fuer die Namensregel: ohne den Repo-Namen und ohne die Marke „Daube.Tech“ samt Domain."""
    return _MARKE_RE.sub(" ", _ohne_oeffentliches_repo(text))


def _zeilen_regex_funde(pfad: str, zeilen: list[str], muster: re.Pattern | None, regel: str,
                         ist_erlaubt: Callable[[str], bool] | None = None,
                         vorbehandlung: Callable[[str], str] | None = None) -> list[Fund]:
    """`vorbehandlung` wandelt die Zeile NUR fuer die Suche um; der Ausschnitt im Fund kommt weiter
    aus der unveraenderten Zeile."""
    if muster is None:
        return []
    funde = []
    for i, zeile_text in enumerate(zeilen, start=1):
        suchtext = vorbehandlung(zeile_text) if vorbehandlung else zeile_text
        for m in muster.finditer(suchtext):
            if ist_erlaubt and ist_erlaubt(m.group(0)):
                continue
            funde.append(Fund(pfad, i, regel, _ausschnitt(zeilen, i)))
    return funde


def _domain_erlaubt(domain: str) -> bool:
    domain = domain.lower()
    if domain.rsplit(".", 1)[-1] in _RESERVIERTE_ENDUNGEN:
        return True
    return any(domain == d or domain.endswith("." + d) for d in ERLAUBTE_DOMAINS)


def _adresse_erlaubt(adresse: str) -> bool:
    adresse_l = adresse.lower()
    if adresse_l in ERLAUBTE_ADRESSEN:
        return True
    return _domain_erlaubt(adresse_l.rsplit("@", 1)[-1])


def _benutzerpfad_erlaubt(konto: str) -> bool:
    k = konto.casefold().rstrip(".")
    return not k or k in _BENUTZERPFAD_PLATZHALTER or k.startswith(_BENUTZERPFAD_PLATZHALTER_ANFANG)


def _zuschreibung_zeilen(zeilen: list[str]) -> set[int]:
    """Zeilennummern (ab 1) in den Abschnitten einer Markdown-Datei, deren Ueberschrift Autor,
    Lizenz oder Urheber nennt -- samt Unterabschnitten, bis eine Ueberschrift gleicher oder hoeherer
    Ebene folgt. Ueberschriften in Codebloecken (```) zaehlen nicht."""
    erlaubt: set[int] = set()
    ebene: int | None = None
    im_code = False
    for i, zeile in enumerate(zeilen, start=1):
        if zeile.lstrip().startswith("```"):
            im_code = not im_code
        elif not im_code:
            m = re.match(r"^(#{1,6})\s+(.*)$", zeile)
            if m:
                neu = len(m.group(1))
                if ebene is not None and neu <= ebene:
                    ebene = None
                if ebene is None and any(w in m.group(2).casefold() for w in _ZUSCHREIBUNG_UEBERSCHRIFTEN):
                    ebene = neu
        if ebene is not None:
            erlaubt.add(i)
    return erlaubt


# ── Programmtext: Python-Strings und TS/TSX-Code ─────────────────────────────────────────────

_BLOCK_KOMMENTAR_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_ZEILEN_KOMMENTAR_RE = re.compile(r"//[^\n]*")


def _docstring_konstanten(baum: ast.AST) -> set[int]:
    """id()s der Constant-Knoten, die als Docstring gelten (Modul/Klasse/Funktion/Async-
    Funktion, jeweils die erste Anweisung als reiner String-Ausdruck) -- die brauchen wir als
    KNOTEN-Identitaet, nicht nur als Text, um sie beim generischen Constant-Walk gezielt
    auszunehmen. Kommentare tauchen im AST ueberhaupt nicht auf -- fuer die sind sie also
    automatisch "erlaubt", ganz ohne Sonderfall hier."""
    ids = set()
    for node in ast.walk(baum):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                ids.add(id(body[0].value))
    return ids


def _python_name_funde(pfad: str, text: str, zeilen: list[str], name_re: re.Pattern) -> list[Fund]:
    try:
        baum = ast.parse(text, filename=pfad)
    except SyntaxError:
        return []
    docstring_ids = _docstring_konstanten(baum)
    funde = []
    for node in ast.walk(baum):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstring_ids:
                continue
            # P2-82: der Name des oeffentlichen Repos ist als String-Literal erlaubt
            if name_re.search(_bereinigt(node.value)):
                zeile = getattr(node, "lineno", 0)
                funde.append(Fund(pfad, zeile, "Name des Nutzers im Python-Programmtext",
                                   _ausschnitt(zeilen, zeile)))
    return funde


def _ts_ohne_kommentare(quelltext: str) -> str:
    """Entfernt Block- (auch JSX-{/* ... */}, dessen INNERES ganz gewoehnliches /* ... */ ist)
    und Zeilenkommentare -- ausreichend fuer die Namenssuche (kein vollstaendiger Parser).
    Block-Kommentare werden durch ebenso viele Zeilenumbrueche ersetzt (nicht durch nichts),
    damit sich KEINE Zeilennummer nach der Bereinigung verschiebt."""
    ohne_block = _BLOCK_KOMMENTAR_RE.sub(lambda m: "\n" * m.group(0).count("\n"), quelltext)
    return _ZEILEN_KOMMENTAR_RE.sub("", ohne_block)


def _ts_name_funde(pfad: str, text: str, name_re: re.Pattern) -> list[Fund]:
    original_zeilen = text.splitlines()
    bereinigt_zeilen = _ts_ohne_kommentare(text).splitlines()
    funde = []
    for i, zeile in enumerate(bereinigt_zeilen, start=1):
        if name_re.search(_bereinigt(zeile)):
            funde.append(Fund(pfad, i, "Name des Nutzers im TS/TSX-Programmtext",
                               _ausschnitt(original_zeilen, i)))
    return funde


def _zeilenenden_funde(pfad: str, inhalt: bytes) -> list[Fund]:
    """Zeilenenden-Regel (nur Umfang paket): `.bat` braucht CRLF (cmd.exe verliert sonst Sprungmarken in
    LF-Dateien), `.command`/`.sh`/`.py` duerfen kein CR enthalten (ein Shebang mit \\r bricht den
    Interpreter-Aufruf unter macOS/Linux). Arbeitet auf den ROHEN BYTES, nicht auf dem dekodierten
    Text -- die Regel ist von der Kodierung unabhaengig."""
    if pfad.endswith(".bat"):
        if re.search(rb"(?<!\r)\n", inhalt):
            return [Fund(pfad, 0, "Zeilenende",
                          "bat-Datei enthaelt LF ohne vorangehendes CR (.gitattributes pruefen)")]
    elif pfad.endswith((".command", ".sh", ".py")):
        if b"\r" in inhalt:
            return [Fund(pfad, 0, "Zeilenende",
                          "Datei enthaelt CR (bricht Shebang/Interpreter unter macOS/Linux)")]
    return []


# ── Pruefen ──────────────────────────────────────────────────────────────────────────────────

_PFAD_TRENNER_RE = re.compile(r"[_\-.]+")


def _pfad_funde(pfad: str, regeln: _Regeln) -> list[Fund]:
    """Umfang oeffentlich: auch der Dateipfad darf keine persoenlichen Daten tragen. Zeile 0. Mehrteilige
    Namen und Firmen stehen in Dateinamen mit Unter-/Bindestrich oder Punkt statt Leerzeichen
    (`Vorname_Nachname.md`); fuer diese Regeln werden die Trenner vor der Suche zu Leerzeichen."""
    funde = []
    wortpfad = _PFAD_TRENNER_RE.sub(" ", pfad)
    pruefungen = (
        (regeln.anschrift, "Anschrift (Dateipfad)", wortpfad),
        (regeln.kontakt, "Private Kontaktdaten (Dateipfad)", _ohne_oeffentliches_repo(pfad)),
        (regeln.konten, "Private Kontaktdaten (Dateipfad)", _ohne_oeffentliches_repo(pfad)),
        (regeln.dritte, "Dritte Personen (Dateipfad)", wortpfad),
        (regeln.name, "Name des Nutzers (Dateipfad)", _PFAD_TRENNER_RE.sub(" ", _bereinigt(pfad))),
    )
    for muster, regel, suchtext in pruefungen:
        if muster is not None and muster.search(suchtext):
            funde.append(Fund(pfad, 0, regel, pfad))
    if regeln.firmen is not None:
        for m in regeln.firmen.finditer(wortpfad):
            if not _firmenname_ausnahme_erlaubt(m.group(0), pfad, regeln.persona):
                funde.append(Fund(pfad, 0, "Firmennamen aus dem Bewerbungsverlauf (Dateipfad)", pfad))
    return funde


def _datei_funde(e: Eintrag, regeln: _Regeln, umfang: str) -> list[Fund]:
    funde: list[Fund] = []
    oeffentlich = umfang == UMFANG_OEFFENTLICH
    if oeffentlich:
        funde += _pfad_funde(e.pfad, regeln)
    else:
        funde += _zeilenenden_funde(e.pfad, e.inhalt)
    try:
        text = e.inhalt.decode("utf-8")
    except UnicodeDecodeError:
        return funde  # Binaerdatei -- keine der folgenden Regeln kann hier greifen
    zeilen = text.splitlines()
    fremd = pfad_trifft(e.pfad, _FREMDER_WORTLAUT)

    # Seit 29.10.2026 ohne Ausnahme fuer frontend/src/rechtliches/.
    funde += _zeilen_regex_funde(e.pfad, zeilen, regeln.anschrift, "Anschrift")
    # P2-82: nur der Name des oeffentlichen Repos ist ausgenommen, s. OEFFENTLICHES_REPO.
    funde += _zeilen_regex_funde(e.pfad, zeilen, regeln.kontakt, "Private Kontaktdaten",
                                  vorbehandlung=_ohne_oeffentliches_repo)
    # Spendenlinks: nur in SPENDEN_PFADE und nur fuer den Kontonamen, s. SPENDEN_PFADE.
    funde += _zeilen_regex_funde(e.pfad, zeilen, regeln.konten, "Private Kontaktdaten",
                                  vorbehandlung=_ohne_spendenlinks(e.pfad))
    funde += _zeilen_regex_funde(e.pfad, zeilen, regeln.telefon, "Private Kontaktdaten")
    funde += _zeilen_regex_funde(e.pfad, zeilen, regeln.dritte, "Dritte Personen")
    # P2-77: fremder Wortlaut (Lizenztexte) bleibt unveraendert, auch mit Autoren-Adressen.
    if not fremd:
        funde += _zeilen_regex_funde(e.pfad, zeilen, _EMAIL_RE, "E-Mail-Adressen",
                                      ist_erlaubt=_adresse_erlaubt)
    funde += _zeilen_regex_funde(e.pfad, zeilen, _TELEFON_RE, "Telefonnummern",
                                  ist_erlaubt=lambda t: re.sub(r"\D", "", t) == _ERLAUBTE_TELEFON_ZIFFERN)

    # Name des Nutzers
    if regeln.name is not None:
        if oeffentlich:
            if not fremd and not pfad_trifft(e.pfad, ZUSCHREIBUNG_PFADE):
                gefunden = _zeilen_regex_funde(e.pfad, zeilen, regeln.name, "Name des Nutzers",
                                                vorbehandlung=_bereinigt)
                if gefunden and e.pfad in ZUSCHREIBUNG_ABSCHNITT_PFADE:
                    erlaubt = _zuschreibung_zeilen(zeilen)
                    gefunden = [f for f in gefunden if f.zeile not in erlaubt]
                funde += gefunden
        else:
            if pfad_trifft(e.pfad, NAME_KUNDENTEXT_PFADE):
                funde += _zeilen_regex_funde(e.pfad, zeilen, regeln.name, "Name des Nutzers in Kundentexten",
                                              vorbehandlung=_bereinigt)
            if e.pfad.endswith(".py"):
                funde += _python_name_funde(e.pfad, text, zeilen, regeln.name)
            if e.pfad.endswith((".ts", ".tsx")):
                funde += _ts_name_funde(e.pfad, text, regeln.name)

    # Bestands-IDs: in jeder ausgelieferten Textdatei
    funde += _zeilen_regex_funde(e.pfad, zeilen, _BESTANDS_ID_RE, "Bestands-IDs")

    if oeffentlich:
        for i, zeile in enumerate(zeilen, start=1):
            for m in _BENUTZERPFAD_RE.finditer(zeile):
                if not _benutzerpfad_erlaubt(m.group(1)):
                    funde.append(Fund(e.pfad, i, "Absoluter Benutzerpfad", _ausschnitt(zeilen, i)))
    return funde


def _firmen_funde(eintraege: list[Eintrag], regeln: _Regeln) -> list[Fund]:
    """Sucht jede Kernform GROSS-/KLEINSCHREIBUNGS-GENAU als GANZES WORT (Lookaround statt `\\b`: ein
    Name wie "Muster (X)" endet nicht auf einem Wortzeichen, `\\b` faende dort gar keine Grenze).
    `ist_erlaubt` bekommt den GETROFFENEN Text UND den Pfad DIESES Eintrags (Closure je
    Schleifendurchlauf) -- so kann `_firmenname_ausnahme_erlaubt` pfadabhaengig entscheiden."""
    if regeln.firmen is None:
        return []
    funde = []
    for e in eintraege:
        # P2-77: Copyright-Zeilen fremder Lizenztexte nennen Firmen und bleiben unveraendert --
        # fuer diese Pfade entfaellt die Regel, s. _FREMDER_WORTLAUT.
        if pfad_trifft(e.pfad, _FREMDER_WORTLAUT):
            continue
        try:
            zeilen = e.inhalt.decode("utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        ist_erlaubt = lambda wort, pfad=e.pfad: _firmenname_ausnahme_erlaubt(wort, pfad, regeln.persona)
        funde += _zeilen_regex_funde(e.pfad, zeilen, regeln.firmen, "Firmennamen aus dem Bewerbungsverlauf",
                                      ist_erlaubt=ist_erlaubt)
    return funde


def pruefen(eintraege: list[Eintrag], muster: Muster, *, umfang: str) -> list[Fund]:
    """Alle DATEIBEZOGENEN Pruefregeln ueber `eintraege` (Moduldoc, „Zwei Umfaenge“): zuerst die
    Regeln je Datei in Reihenfolge der Eintraege, danach die Firmennamen-Regel ueber alle. OHNE die
    paketweiten Regeln (Pflichtdateien, Importe, Startdateien) -- die gehoeren zu `kundenpaket.py`.

    `umfang`: `"paket"` oder `"oeffentlich"`, alles andere ist ein ValueError. Ein leeres `muster`
    laesst die persoenlichen Regeln aus; die allgemeinen laufen immer."""
    if umfang not in UMFAENGE:
        raise ValueError(f"umfang muss einer von {UMFAENGE} sein, nicht {umfang!r}")
    regeln = _Regeln(muster, _persona_nachnamen(eintraege))
    funde: list[Fund] = []
    for e in eintraege:
        funde += _datei_funde(e, regeln, umfang)
    funde += _firmen_funde(eintraege, regeln)
    return funde
