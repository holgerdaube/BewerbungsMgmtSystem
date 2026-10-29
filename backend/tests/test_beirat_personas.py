"""Phase 71C -- Beirat: reale Personen -> fiktive Archetypen (tasks/spec_phase71_produktisierung.md,
Abschnitt 71C). Die 7 Koepfe modellierten bis dahin real existierende, lebende Personen namentlich
-- fuer ein an Dritte vertriebenes Produkt persoenlichkeitsrechtlich nicht haltbar (Namensrecht
Art. 12 BGB, APR). Ersatz durch 7 fiktive Archetypen mit identischer fachlicher Brille, Vorsitz
neu: Vera Brandt.

Dieser Test ist der mechanische Nachweis, dass die Persona-Registry (`beirat_engine.lade_mitglieder()`,
liest ausschliesslich `.claude/agents/beirat-*.md`) nach dem Rename weiterhin genau 7 Koepfe liefert,
KEINER der 7 realen Nachnamen mehr in id/anzeige/beschreibung/persona-Text auftaucht, und der Vorsitz
(`beirat_engine.VORSITZ_ID`) auf die neue fiktive Vorsitzende zeigt.

Wie in conftest.py beschrieben: KEIN app.*/pipeline.*-Import auf Modulebene, nur in Testfunktionen
(gilt auch fuer `beirat_engine` selbst, s. Vorbild test_beirat_fehler.py -- das Modul zieht
transitiv app.agent_runner/app.db/app.models nach). `lade_mitglieder()` liest ausschliesslich
lokale Persona-Markdown-Dateien von der Platte -- kein Subprozess, keine echte API, keine Kosten.
"""

# Sperrliste der realen Nachnamen der Vor-71C-Besetzung (Charta-Historie), damit sie in keiner
# Persona mehr auftauchen. Die Namen selbst stehen bewusst nirgends im Repo: Die Liste enthaelt
# nur den SHA-256 des klein geschriebenen, getrimmten Namens (UTF-8). Der Test zerlegt den
# Persona-Text in Woerter (mit und ohne Bindestrich-Verbund, damit auch liegen gebliebene alte
# Datei-IDs wie "beirat-<name>" auffallen), hasht jedes Wort genauso und vergleicht.
_ALTE_NAMEN_SHA256 = frozenset({
    "7e611b1c227fe8d46b404e8180b444d40cca63fb45ebd3f27b45e60906f1ac4b",
    "d99c64b981d77924edc73b97c9a019bcda65d3a53679364c57d03886a444b0af",
    "1966f10c3e03c0fb58db6b8c6ff3f5cab3083ccdc0db6729f7aa019792ee049b",
    "ecdc16b9b68b6eb581e354b32ecebeee07dd3f52e58d39dbc121830613193cf3",
    "0ceccb44585cc9349cbdf88edc900a6fc68fd1c31b1524193f05a529806bd7b5",
    "243c7b40e12b92b6aea5d3f77fe57e2b5599b8daec4b4186c9bba12c391b7a3f",
    "55a98135a545800eec2f9d0141d49730f21daa463285070dc9dcfe1aa6022ecb",
    "e96e35a376f8bb39cd7cb24e11f9efbfbe372aba9477a9e90bd094915c71fa9c",
})


def _gesperrte_woerter(text: str, sperrliste: frozenset = _ALTE_NAMEN_SHA256) -> list[str]:
    """Alle Woerter des Textes, deren SHA-256 (klein geschrieben, getrimmt) auf der Sperrliste steht.
    Geprueft werden die einzelnen Woerter UND die Bindestrich-Verbuende (Doppelnamen)."""
    import hashlib
    import re

    klein = text.lower()
    kandidaten = set(re.findall(r"\w+", klein)) | set(re.findall(r"\w+(?:-\w+)*", klein))
    return sorted(
        w for w in kandidaten
        if hashlib.sha256(w.strip().encode("utf-8")).hexdigest() in sperrliste
    )


def test_genau_sieben_personas_geladen(_db_ready):
    from beirat_engine import lade_mitglieder

    mitglieder = lade_mitglieder()
    assert len(mitglieder) == 7


def test_keine_der_sieben_realen_namen_mehr_vorhanden(_db_ready):
    """Grep-Aequivalent als Test: durchsucht id/anzeige/beschreibung/persona jedes geladenen
    Kopfes (case-insensitiv) nach jedem der realen Nachnamen aus der Vor-71C-Besetzung
    (Sperrliste als SHA-256, s. oben)."""
    from beirat_engine import lade_mitglieder

    mitglieder = lade_mitglieder()
    volltext = "\n".join(
        f"{m['id']}\n{m['anzeige']}\n{m['beschreibung']}\n{m['persona']}" for m in mitglieder
    )
    treffer = _gesperrte_woerter(volltext)
    assert not treffer, f"Gesperrter realer Name noch in einer geladenen Persona gefunden: {treffer}"


def test_sperrliste_erkennt_woerter_doppelnamen_und_dateiids():
    """Gegenprobe fuer den Hash-Vergleich selbst, mit einer erfundenen Sperrliste."""
    import hashlib

    sperrliste = frozenset(hashlib.sha256(w.encode("utf-8")).hexdigest()
                           for w in ("musterfrau", "mustermann-beispiel"))
    assert _gesperrte_woerter("Die Beraterin Musterfrau sagt", sperrliste) == ["musterfrau"]
    assert _gesperrte_woerter("beirat-musterfrau", sperrliste) == ["musterfrau"]
    assert _gesperrte_woerter("Doppelname Mustermann-Beispiel im Text", sperrliste) == ["mustermann-beispiel"]
    assert _gesperrte_woerter("Vera Brandt und Max Mustermann", sperrliste) == []


def test_vorsitz_ist_vera_brandt(_db_ready):
    from beirat_engine import VORSITZ_ID, lade_mitglieder

    mitglieder = {m["id"]: m for m in lade_mitglieder()}
    assert VORSITZ_ID in mitglieder
    assert mitglieder[VORSITZ_ID]["anzeige"] == "Vera Brandt"


def test_alle_personas_tragen_den_fiktiv_hinweis(_db_ready):
    """Spec-Vorgabe (71C): jede Persona-Datei bekommt im Kopf den Fiktiv-Satz -- hier ueber den
    vollstaendig geladenen Persona-Text (Frontmatter-Body, inkl. der Zeile direkt nach dem
    Frontmatter) geprueft, nicht nur stichprobenartig an einer Datei."""
    from beirat_engine import lade_mitglieder

    for m in lade_mitglieder():
        assert "fiktive persona" in m["persona"].lower(), (
            f"Kopf {m['id']} traegt keinen erkennbaren Fiktiv-Hinweis am Kopf der Datei"
        )
        assert "keine reale person" in m["persona"].lower(), (
            f"Kopf {m['id']}: Fiktiv-Hinweis fehlt der Halbsatz 'keine reale Person'"
        )
