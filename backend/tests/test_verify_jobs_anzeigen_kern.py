"""Tests für den Anzeigen-Kern-Schnitt (Fix 07.08.2026, Fall A):
LinkedIn-Guest-Seiten liefern die komplette Seiten-Chrome (Cookie-Banner, Login-Formulare,
„Ähnliche Jobs", Sprach-Footer) — der Basis-Snapshot soll nur den eigentlichen Anzeigentext
aus dem `show-more-less-html__markup`-Container zeigen. Konvention conftest.py: keine
app.*/pipeline.*-Importe auf Modulebene."""


_KERN_HTML = (
    '<p>Minimum qualifications:</p><ul><li>Bachelor degree in Computer Science</li>'
    '<li>10 years of experience in technical project management roles</li></ul>'
    '<p>About the job</p><p>As a Delivery Executive you will work with customers on '
    'large multi-year transformational engagements underpinned by Google Cloud Platform '
    'to drive business value, providing delivery management and consulting skills.</p>'
)

_LINKEDIN_SEITE = (
    '<html><body>'
    '<p>LinkedIn nimmt den Schutz Ihrer Privatsphäre sehr ernst</p>'
    '<p>Akzeptieren</p><p>Ablehnen</p><p>Einloggen</p><p>Mitglied werden</p>'
    '<div class="show-more-less-html__markup show-more-less-html__markup--clamp-after-5 '
    'relative overflow-hidden">' + _KERN_HTML + '</div>'
    '<p>Ähnliche Jobs</p><p>Customer Engineer, Sovereignty (German, English)</p>'
    '<p>Director-Jobs</p><p>73.946 freie Stellen</p>'
    '</body></html>'
)


def test_linkedin_container_wird_geschnitten():
    from pipeline.verify_jobs import _anzeigen_kern
    from pipeline import gmail_client

    volltext = gmail_client._entkleiden(_LINKEDIN_SEITE)
    kern = _anzeigen_kern(_LINKEDIN_SEITE, volltext)

    assert "Minimum qualifications" in kern
    assert "Delivery Executive" in kern
    # Die Seiten-Chrome ist draußen:
    assert "Privatsphäre" not in kern
    assert "Einloggen" not in kern
    assert "Ähnliche Jobs" not in kern
    assert "freie Stellen" not in kern


def test_ohne_container_bleibt_der_volltext():
    """Anderes Portal / geändertes Markup → ehrlicher Fallback, kein Inhaltsverlust."""
    from pipeline.verify_jobs import _anzeigen_kern

    html = "<html><body><p>Stellenanzeige direkt im Body ohne LinkedIn-Container.</p></body></html>"
    volltext = "Stellenanzeige direkt im Body ohne LinkedIn-Container."
    assert _anzeigen_kern(html, volltext) == volltext


def test_verdaechtig_kurzer_treffer_faellt_auf_volltext_zurueck():
    """Ein Mini-Fragment im Container (<300 Zeichen) ist kein glaubwürdiger Anzeigentext."""
    from pipeline.verify_jobs import _anzeigen_kern

    html = '<div class="show-more-less-html__markup">Zu kurz.</div>'
    volltext = "Der komplette Seitentext als Fallback, deutlich informativer als das Fragment."
    assert _anzeigen_kern(html, volltext) == volltext


def test_besetzt_marker_ausserhalb_des_containers_bleibt_wirksam(monkeypatch):
    """Die Verfügbarkeits-Prüfung läuft weiter über den VOLLTEXT: ein Besetzt-Marker in der
    Seiten-Chrome (außerhalb des Beschreibungs-Containers) muss weiterhin ABGELAUFEN ergeben —
    der Kern-Schnitt betrifft ausschließlich das anzeigentext-Feld. P2-76: Passen Titel und Firma,
    kommt der Text der noch sichtbaren Anzeige trotzdem mit, und zwar nur der Kern."""
    import httpx
    from pipeline import verify_jobs

    seite = ('<html><body><p>No longer accepting applications</p>'
             '<div class="show-more-less-html__markup">' + _KERN_HTML + '</div></body></html>')

    def _fake_get(self, url):
        return httpx.Response(200, text=seite, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", _fake_get)
    befund = verify_jobs.check_url("https://example.com/jobs/view/123", "Google",
                                   "Delivery Executive", return_text=True)
    assert befund["befund"] == "ABGELAUFEN"
    assert "Minimum qualifications" in befund["anzeigentext"]
    assert "No longer accepting" not in befund["anzeigentext"]
