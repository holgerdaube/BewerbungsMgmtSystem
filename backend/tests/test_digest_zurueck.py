"""Rückweg aus dem Tages-Digest: Oben links führt „← Zurück zum Dashboard“ in die App.

Der Digest öffnet sich über den Knopf auf dem Dashboard im selben Tab (`/api/digest`) und hatte keinen
Weg zurück. Den Link trägt nur die Ansicht der App. Die Datei des Tageslaufs (`data/digests/`) wird aus
dem Finder geöffnet; ein Link auf „/“ führte dort ins Leere, sie bleibt deshalb ohne ihn.

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention).
"""
import re

_LINK = '<a class="zurueck" href="/">← Zurück zum Dashboard</a>'


def test_digest_der_app_hat_oben_links_den_link_zum_dashboard(client):
    html = client.get("/api/digest").text

    assert _LINK in html
    koerper = html[html.index('<div class="wrap">'):]
    assert koerper.index(_LINK) < koerper.index("<h1>"), "der Link steht über der Überschrift"
    assert re.search(r"\.zurueck\{[^}]*color:#[0-9A-Fa-f]{3,6}", html), "die Regel trägt die Aktionsfarbe"


def test_datei_des_tageslaufs_bleibt_ohne_link(client):
    from pipeline.digest import build_digest_html

    html = build_digest_html()

    assert "zurueck" not in html and "Zurück zum Dashboard" not in html
