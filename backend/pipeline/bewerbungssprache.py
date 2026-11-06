#!/usr/bin/env python3
"""Bewerbungssprachen: EINE Tabelle statt verstreuter Listen.

Unterlagen nach außen (Lebenslauf, Anschreiben) und die Erkennung fremdsprachiger Anzeigen und
Mails brauchen dieselben Wörter: Fußzeile, Datum, Grußformeln, Stoppwörter für die Spracherkennung,
Geschlossen- und Login-Texte, Mail-Betreff und -Absender. Bis dahin standen sie einzeln und nur für
Deutsch und Englisch in `cv_export`, `cover_letter_render`, `beirat_engine` und `verify_jobs`.
Eine weitere Sprache ist jetzt ein Eintrag in `SPRACHEN`.

Abdeckung: DE und EN als Vorlage für Fußzeile, Datum, Grußformeln und Stoppwörter. Die Marker für
Geschlossen, Login, Mail-Betreff und Mail-Absender von DE und EN bleiben in `verify_jobs` und im Skill
`email-check`, wo sie getestet sind; hier sind sie für DE und EN leer, damit nichts doppelt steht.
Mit `alle_marker(feld)` bekommen Aufrufer die Wörter aller Sprachen dieser Tabelle ohne Doppelte.

Regeln:
  * Kein Import aus `app.*` oder aus `cv_export` (die importieren dieses Modul, kein Zirkel).
  * Alle Listen kleingeschrieben (Aufrufer vergleichen gegen kleingeschriebenen Seitentext).
  * Maschinenwerte (Sprachcode) sind Großbuchstaben (`FR`), wie `CVVersion.language`.
  * Eine unbekannte Sprache fällt NIE auf Deutsch zurück (`fusszeilen_labels`: `x / y`,
    `datum_text`: ISO-Datum). Fehlt die Sprache ganz (None), gilt Deutsch wie im Altbestand.
"""
import datetime
import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Bewerbungssprache:
    code: str                           # "FR"
    fusszeile: tuple                    # ("Page ", " sur ") = (Präfix vor der Seitenzahl, Trenner)
    datum: str                          # Vorlage, Felder siehe `datum_text()`; nicht strftime
    monate: tuple                       # 12 Monatsnamen, so wie sie im Datum stehen
    grussformeln: tuple                 # ganze Zeile (ohne Schluss-Komma/-Punkt)
    grussformeln_anfang: tuple          # Zeile BEGINNT so (lange Schlusssätze, z. B. "veuillez agréer")
    betreff_woerter: tuple              # erstes Wort der Betreffzeile im Anschreiben ("objet")
    stoppwoerter: tuple                 # kurze, nur in dieser Sprache häufige Funktionswörter
    geschlossen: tuple                  # Seitentext-Marker "Stelle nicht mehr offen"
    login: tuple                        # Seitentext-Marker "Anmeldeseite statt Anzeige"
    mail_betreff: tuple                 # Gmail-Betreff-Stichwörter
    mail_absender: tuple                # Gmail-Absender-Teile


_EN_MONATE = ("January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December")

SPRACHEN: dict = {
    "DE": Bewerbungssprache(
        code="DE",
        fusszeile=("Seite ", " von "),
        datum="{tag2}.{monatnr2}.{jahr}",          # wie `%d.%m.%Y` bisher
        monate=("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
                "September", "Oktober", "November", "Dezember"),
        grussformeln=("mit freundlichen grüßen", "freundliche grüße", "beste grüße", "viele grüße",
                      "herzliche grüße"),
        grussformeln_anfang=(),
        betreff_woerter=("bewerbung", "betreff"),
        # Mengen unverändert aus dem bisherigen Beirat übernommen (24 Wörter).
        stoppwoerter=("und", "für", "mit", "ist", "sind", "eine", "einer", "unternehmen", "wir",
                      "sie", "unser", "unsere", "ihre", "aufgaben", "erfahrung", "kenntnisse",
                      "verantwortung", "als", "bei", "der", "die", "das", "sowie", "werden", "haben"),
        geschlossen=(), login=(), mail_betreff=(), mail_absender=(),   # bleiben in verify_jobs / Skill
    ),
    "EN": Bewerbungssprache(
        code="EN",
        fusszeile=("Page ", " of "),
        datum="{tag} {monat} {jahr}",
        monate=_EN_MONATE,
        grussformeln=("kind regards", "best regards", "warm regards", "regards", "sincerely",
                      "yours sincerely", "yours faithfully"),
        grussformeln_anfang=(),
        betreff_woerter=("application", "subject", "re"),
        # Mengen unverändert aus dem bisherigen Beirat übernommen (18 Wörter).
        stoppwoerter=("and", "for", "with", "is", "are", "our", "you", "we", "the",
                      "responsibilities", "experience", "requirements", "role", "team", "will",
                      "have", "your", "about"),
        geschlossen=(), login=(), mail_betreff=(), mail_absender=(),
    ),
    "FR": Bewerbungssprache(
        code="FR",
        fusszeile=("Page ", " sur "),
        datum="{tag} {monat} {jahr}",
        monate=("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
                "septembre", "octobre", "novembre", "décembre"),
        grussformeln=("cordialement", "bien à vous"),
        grussformeln_anfang=("veuillez agréer", "je vous prie d'agréer", "je vous prie d’agréer"),
        betreff_woerter=("objet", "candidature"),
        stoppwoerter=("et", "les", "des", "est", "sont", "vous", "nous", "une", "pour", "dans",
                      "avec", "sur", "aux", "chez", "votre", "vos", "notre", "nos", "poste",
                      "entreprise", "expérience", "équipe", "missions", "profil"),
        # `plus disponible` allein wäre zu breit („le plus disponible“); belegt ist „cette offre
        # n'est plus disponible“ (randstad.fr, geschlossene Anzeige).
        geschlossen=("n'est plus disponible", "n’est plus disponible", "offre expirée",
                     "a été pourvue", "n'est plus en ligne", "n’est plus en ligne"),
        login=("connectez-vous", "se connecter pour"),
        mail_betreff=("candidature", "entretien", "recrutement", "postuler"),
        mail_absender=("recrutement", "rh", "carrieres"),
    ),
    "IT": Bewerbungssprache(
        code="IT",
        fusszeile=("Pagina ", " di "),
        datum="{tag} {monat} {jahr}",
        monate=("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
                "settembre", "ottobre", "novembre", "dicembre"),
        grussformeln=("cordiali saluti", "distinti saluti"),
        grussformeln_anfang=(),
        betreff_woerter=("oggetto", "candidatura"),
        stoppwoerter=("il", "di", "della", "dei", "delle", "gli", "sono", "nel", "nella", "che",
                      "più", "alla", "degli", "azienda", "esperienza", "requisiti",
                      "competenze", "lavoro", "candidato", "cerchiamo", "offriamo", "siamo"),
        # „offerta di lavoro è scaduta“ belegt (randstad.it, geschlossene Anzeige)
        geschlossen=("non è più disponibile", "offerta di lavoro è scaduta", "posizione è stata chiusa",
                     "annuncio scaduto"),
        login=("accedi per",),
        mail_betreff=("candidatura", "colloquio", "selezione"),
        mail_absender=("selezione", "risorseumane", "lavoro"),
    ),
    "ES": Bewerbungssprache(
        code="ES",
        fusszeile=("Página ", " de "),
        datum="{tag} de {monat} de {jahr}",
        monate=("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                "septiembre", "octubre", "noviembre", "diciembre"),
        grussformeln=("atentamente", "un cordial saludo"),
        grussformeln_anfang=(),
        betreff_woerter=("asunto", "solicitud", "candidatura"),
        stoppwoerter=("el", "los", "las", "del", "puesto", "experiencia", "funciones", "nosotros",
                      "ofrecemos", "buscamos", "trabajo", "equipo", "también", "años", "además",
                      "nuestro", "nuestra", "usted"),
        # `ha caducado` allein trifft auch „su sesión ha caducado“ (Oberflächentexte offener Seiten)
        geschlossen=("ya no está disponible", "oferta ha caducado", "empleo ha caducado",
                     "oferta cerrada"),
        login=("inicia sesión para", "no podemos identificar tu navegador"),
        # `oferta` bewusst nicht: trifft auch Werbung (Spec P2-93, Fix 4).
        mail_betreff=("candidatura", "solicitud", "entrevista"),
        mail_absender=("seleccion", "empleo", "rrhh"),
    ),
    "PT": Bewerbungssprache(
        code="PT",
        fusszeile=("Página ", " de "),
        datum="{tag} de {monat} de {jahr}",
        monate=("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
                "setembro", "outubro", "novembro", "dezembro"),
        grussformeln=("atenciosamente", "com os melhores cumprimentos"),
        grussformeln_anfang=(),
        betreff_woerter=("assunto", "candidatura"),
        stoppwoerter=("os", "uma", "não", "são", "você", "nós", "ao", "aos", "às", "em", "tem",
                      "vaga", "experiência", "funções", "oferecemos", "procuramos", "trabalho",
                      "equipa", "também", "anos", "além", "nosso", "nossa"),
        # „já não se encontra disponível“ belegt (randstad.pt, geschlossene Anzeige)
        geschlossen=("não está mais disponível", "já não está disponível", "já não se encontra disponível",
                     "vaga está indisponível", "inscrições estão encerradas"),
        login=("inicie sessão", "faça login"),
        # `vaga` bewusst nicht: trifft auch Werbung (Spec P2-93, Fix 4).
        mail_betreff=("candidatura", "entrevista", "recrutamento"),
        mail_absender=("recrutamento", "vagas", "rh", "carreiras"),
    ),
}

CODES = tuple(SPRACHEN)                 # ("DE", "EN", "FR", "IT", "ES", "PT")
FELDER_MARKER = ("geschlossen", "login", "mail_betreff", "mail_absender")


def normiere_code(sprache) -> Optional[str]:
    """Sprachangabe → Großbuchstaben-Code. None und leer → None (Altbestand ohne Sprache).
    Tolerant gegen Kleinschreibung und Zusätze (`fr`, `en-US`, `pt_BR`): Es zählt der Teil vor
    dem ersten `-`, `_` oder Leerzeichen. Unbekannte Codes kommen unverändert (groß) zurück.
    Alt-Verhalten für Deutsch und Englisch bleibt: Alles, was mit `EN` beginnt (`ENGLISH`), ist
    EN; alles, was mit `DE` oder `GER` beginnt (`DEUTSCH`, `GERMAN`), ist DE."""
    s = str(sprache or "").strip().upper()
    if not s:
        return None
    teil = re.split(r"[-_\s]", s, maxsplit=1)[0]
    if teil in SPRACHEN:
        return teil
    if teil.startswith("EN"):
        return "EN"
    if teil.startswith(("DE", "GER")):
        return "DE"
    return teil


def sprache(code) -> Optional[Bewerbungssprache]:
    """Tabelleneintrag zu einer Sprachangabe, sonst None (unbekannt oder leer)."""
    return SPRACHEN.get(normiere_code(code) or "")


def fusszeilen_labels(code) -> tuple:
    """(Präfix vor der Seitenzahl, Trenner vor der Gesamtzahl). Fehlt die Sprache (None, leer):
    Deutsch wie im Altbestand. Eine unbekannte Sprache bekommt `("", " / ")`, also `1 / 3`."""
    c = normiere_code(code)
    if c is None:
        return SPRACHEN["DE"].fusszeile
    s = SPRACHEN.get(c)
    return s.fusszeile if s else ("", " / ")


def datum_text(datum: datetime.date, code) -> str:
    """Datum im Landesformat: `03.11.2026`, `3 November 2026`, `3 novembre 2026`,
    `3 de noviembre de 2026`. Ohne Sprache (None, leer): Deutsch. Unbekannte Sprache: ISO
    (`2026-11-03`), nie ein deutscher Punkt. Französisch schreibt den Ersten als `1er`.
    Unabhängig von der Systemsprache (kein strftime)."""
    c = normiere_code(code)
    if c is None:
        c = "DE"
    s = SPRACHEN.get(c)
    if s is None:
        return datum.isoformat()
    tag = "1er" if (c == "FR" and datum.day == 1) else str(datum.day)
    return s.datum.format(tag=tag, tag2=f"{datum.day:02d}", monatnr2=f"{datum.month:02d}",
                          monat=s.monate[datum.month - 1], jahr=datum.year)


def alle_marker(feld: str, codes=None) -> tuple:
    """Die Wörter eines Listenfelds (`geschlossen`, `login`, `mail_betreff`, `mail_absender`,
    auch `grussformeln` usw.) über alle Sprachen oder die genannten Codes, in Tabellenreihenfolge,
    ohne Doppelte (`candidatura` steht in IT, ES und PT, kommt aber einmal)."""
    gesehen = []
    for c in (codes or CODES):
        for wort in getattr(SPRACHEN[normiere_code(c)], feld):
            if wort not in gesehen:
                gesehen.append(wort)
    return tuple(gesehen)


_STOPP = {c: frozenset(s.stoppwoerter) for c, s in SPRACHEN.items()}


def stoppwoerter(code) -> frozenset:
    """Stoppwörter einer Sprache als Menge; unbekannt → leer."""
    return _STOPP.get(normiere_code(code) or "", frozenset())


_WORT_RE = re.compile(r"[^\W\d_]+")


def erkenne_sprache(text: str, standard: str = "DE") -> str:
    """Sprache eines Anzeigentexts über die Zahl der Stoppwort-Treffer je Sprache (Großbuchstaben).
    Mehr Treffer gewinnt; bei Gleichstand an der Spitze (auch bei 0 Treffern) `standard`, sofern
    es zu den Spitzenreitern gehört, sonst der erste in Tabellenreihenfolge. Die Stoppwörter
    teilen sich keine Sprachen (Test), ein Wort zählt also für genau eine Sprache. Reine
    Titel ohne Funktionswörter bleiben dadurch beim Standard."""
    woerter = _WORT_RE.findall((text or "").lower())
    treffer = {c: sum(1 for w in woerter if w in _STOPP[c]) for c in CODES}
    spitze = max(treffer.values())
    fuehrer = [c for c in CODES if treffer[c] == spitze]
    std = normiere_code(standard) or "DE"
    return std if std in fuehrer else fuehrer[0]


def grussformel_re(codes=None) -> "re.Pattern":
    """Regex für eine Schluss-Grußformel als eigene Zeile (ohne Schluss-Komma/-Punkt) oder als
    Zeilenanfang eines langen Schlusssatzes. Für DE und EN dasselbe wie die frühere
    Einzelliste (`cover_letter_render._GRUSSFORMEL`)."""
    ganz = "|".join(re.escape(w) for w in alle_marker("grussformeln", codes))
    anfang = "|".join(re.escape(w) for w in alle_marker("grussformeln_anfang", codes))
    muster = rf"^(?:{ganz})\s*[,.]?$"
    if anfang:
        muster += rf"|^(?:{anfang})\b"
    return re.compile(muster, re.IGNORECASE)


def betreff_re(codes=None) -> "re.Pattern":
    """Regex für den Anfang der Betreffzeile eines Anschreibens (`Objet : …`, `Asunto: …`)."""
    woerter = "|".join(re.escape(w) for w in alle_marker("betreff_woerter", codes))
    return re.compile(rf"^(?:{woerter})\b\s*[:\s]", re.IGNORECASE)


def sprache_aus_grussformel(text: str) -> Optional[str]:
    """Code der Sprache, in der der Text seine Schluss-Grußformel trägt (zeilenweise geprüft; bei
    mehreren Treffern zählt der letzte, also der Briefschluss), sonst None."""
    gefunden = None
    for zeile in (text or "").splitlines():
        zeile = zeile.strip()
        if not zeile:
            continue
        for c in CODES:
            if grussformel_re([c]).match(zeile):
                gefunden = c
                break
    return gefunden
