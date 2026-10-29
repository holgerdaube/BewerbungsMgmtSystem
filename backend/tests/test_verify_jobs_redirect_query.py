"""Regressionstest für P2-13 (Phase 67D): `verify_jobs._norm_url()` baute den Vergleichsstring
bisher nur aus `scheme://netloc + path` -- die Query wurde komplett verworfen. Portale, die die
Job-ID NUR in der Query führen (real in der DB: Indeed „?jk=…"/„?vjk=…", s. Abschlussbericht
Phase 67D für die volle Beleg-Tabelle), konnten so eine abgelaufene Anzeige als „OK"
durchrutschen lassen: läuft die URL auf eine generische Seite MIT DEMSELBEN PFAD um, blieb
`redirected` `False`.

Fix (zwei Teile, beide nötig -- s. Report):
  1. `_norm_url()` bezieht die (tracking-bereinigte) Query in den Vergleich ein
     (`_clean_query_pairs` + `_TRACKING_QUERY_PARAMS`).
  2. `check_url()`s „Redirect auf generische Seite"-Check (bisher NUR der letzte Pfad-Teil)
     prüft zusätzlich, ob die identitätstragenden Query-Werte der Original-URL komplett aus der
     finalen URL verschwunden sind -- sonst bliebe der Fix wirkungslos: bei einem Portal mit
     GENERISCHEM, geteiltem Pfad (z. B. Indeed „/rc/clk") und Job-ID NUR in der Query würde der
     alte, rein pfadbasierte Check niemals greifen, selbst wenn `redirected` jetzt korrekt
     `True` ist (der Pfad bleibt ja unverändert).

Kein app.*-Import auf Modulebene nötig für die reinen `_norm_url`-Tests (kein DB-Zugriff);
`check_url()`-Tests mocken `httpx.Client` komplett -- kein echter Netzzugriff (Q3)."""


# ── _norm_url(): reine Funktion, kein Netzzugriff ────────────────────────────────────────────
def test_norm_url_job_id_nur_in_der_query_wird_nicht_mehr_verworfen():
    """Kernfall aus dem Befund: Indeed führt die Job-ID nur in der Query ('jk='), der Pfad
    ('/rc/clk') ist für JEDEN Job identisch. Ohne den Fix wären beide Strings gleich (Query
    komplett ignoriert) -- mit dem Fix unterscheiden sie sich, weil 'jk' NICHT auf der
    Tracking-Liste steht (identitätstragend, s. Modul-Kommentar)."""
    from pipeline.verify_jobs import _norm_url

    mit_id = _norm_url("https://de.indeed.com/rc/clk?jk=6c239a837eaf1c0a")
    ohne_id = _norm_url("https://de.indeed.com/rc/clk")

    assert mit_id != ohne_id, "P2-13: eine Job-ID-tragende Query darf nicht verworfen werden"


def test_norm_url_reale_bestands_urls_ohne_tracking_unterschied():
    """Empirisch aus der Live-DB (read-only, Stand 26.07.2026, s. Abschlussbericht): zwei
    Aufrufe DERSELBEN Anzeige mit unterschiedlichem Sprach-/Analytics-Anhängsel müssen trotz
    Query-Vergleich als IDENTISCH gelten -- sonst würde jede Anzeige mit Tracking-/
    Sprachparametern fälschlich als „umgeleitet" gelten (die im Befund benannte Gefahr)."""
    from pipeline.verify_jobs import _norm_url

    # Karriereseite mit Sprachauswahl: nur die Sprachauswahl (?lang=…) unterscheidet sich
    assert (_norm_url("https://jobs.beispiel.de/jobs/2625?lang=en-us")
            == _norm_url("https://jobs.beispiel.de/jobs/2625?lang=de-de"))

    # LinkedIn: reines Klick-Analytics (trackingId/alternateChannel), Job-Identität steht im Pfad
    a = _norm_url("https://www.linkedin.com/jobs/view/4441624574/?alternateChannel=search&trackingId=abc123")
    b = _norm_url("https://www.linkedin.com/jobs/view/4441624574/?alternateChannel=email&trackingId=xyz999")
    assert a == b

    # Generische UTM-Parameter (im Befundtext ausdrücklich genannt)
    c = _norm_url("https://example.com/job/123?utm_source=newsletter&utm_medium=email")
    d = _norm_url("https://example.com/job/123")
    assert c == d


def test_norm_url_identitaetstragende_indeed_suchquery_bleibt_erhalten():
    """Indeed-Suchergebnis-URL ('/jobs?q=…&vjk=…'): Suchkontext (q/l/radius/sort/fromage) ist
    Rauschen, 'vjk' (die konkrete Anzeige innerhalb der Trefferliste) bleibt identitätstragend."""
    from pipeline.verify_jobs import _norm_url

    a = _norm_url("https://de.indeed.com/jobs?q=Head+of+CS&l=Frankfurt&radius=100&sort=date&fromage=30&vjk=93ab5c7d0ffe8fbf")
    b = _norm_url("https://de.indeed.com/jobs?q=Head+of+CS&l=Frankfurt&radius=100&sort=date&fromage=30")  # vjk verschwunden
    assert a != b, "'vjk' ist die einzige identitätstragende Query in dieser URL-Familie"


def test_norm_url_parameter_reihenfolge_aendert_nichts():
    """Ein Redirect, der dieselben (bereinigten) Query-Parameter nur umsortiert, darf keinen
    künstlichen Unterschied erzeugen."""
    from pipeline.verify_jobs import _norm_url

    a = _norm_url("https://example.com/job/123?jobId=9&foo=bar")
    b = _norm_url("https://example.com/job/123?foo=bar&jobId=9")
    assert a == b


# ── check_url(): end-to-end mit gemocktem httpx.Client (Q3 -- kein echter Netzzugriff) ───────
class _FakeResponse:
    def __init__(self, status_code, url, text=""):
        self.status_code = status_code
        self.url = url
        self.text = text


class _FakeClient:
    """Ersetzt httpx.Client komplett -- konstant EINE Antwort, unabhängig von der angefragten
    URL (wie es `follow_redirects=True` aus Sicht des Aufrufers ohnehin abstrahiert: man sieht
    nur den Endzustand `r.url`)."""

    def __init__(self, final_url, status_code=200, text=""):
        self._final_url = final_url
        self._status = status_code
        self._text = text

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url):
        return _FakeResponse(self._status, self._final_url, self._text)


def test_check_url_erkennt_verlorene_query_job_id_auf_generischer_seite(monkeypatch):
    """End-to-End-Beleg des Befunds: Original-URL trägt die Job-ID NUR in der Query, der
    Redirect landet auf DEMSELBEN Pfad ohne diese Query UND mit generischem (nicht
    Titel/Firma-tragendem) Seitentext. Ohne den Fix: `redirected` bliebe False (Query
    verworfen) -> Sprung zu Schritt 5, dort weder Absage-Marker noch Login-Wall noch
    Titel/Firma-Treffer -> „INHALT_UNKLAR", NICHT „UMGELEITET_GENERISCH" -- der Befund selbst
    bliebe unentdeckt als eigener, benannter Redirect-Fall."""
    import pipeline.verify_jobs as verify_jobs

    original = "https://de.indeed.com/rc/clk?jk=6c239a837eaf1c0a"
    final = "https://de.indeed.com/rc/clk"   # gleicher Pfad, Job-ID-Query verschwunden

    monkeypatch.setattr(
        verify_jobs.httpx, "Client",
        lambda **kw: _FakeClient(final, status_code=200,
                                  text="Diese Suche ergab leider keine passenden Treffer."),
    )

    result = verify_jobs.check_url(original, "Beispiel GmbH", "Head of Customer Success")

    assert result["befund"] == "UMGELEITET_GENERISCH", (
        f"P2-13: verlorene Job-ID-Query auf generischer Seite hätte erkannt werden müssen: {result}"
    )
    assert "6c239a837eaf1c0a" in result["beleg"]


def test_check_url_kein_redirect_mit_passendem_text_bleibt_ok(monkeypatch):
    """Gegenprobe (Q5): dieselbe URL, kein Redirect, Seitentext passt zu Titel/Firma -> muss
    weiterhin OK bleiben (Erfolgsfall darf sich durch den Fix nicht ändern)."""
    import pipeline.verify_jobs as verify_jobs

    url = "https://de.indeed.com/rc/clk?jk=6c239a837eaf1c0a"
    monkeypatch.setattr(
        verify_jobs.httpx, "Client",
        lambda **kw: _FakeClient(url, status_code=200,
                                  text="Beispiel GmbH sucht: Head of Customer Success. "
                                       "Aufgaben: Kundenerfolg verantworten, Team führen."),
    )

    result = verify_jobs.check_url(url, "Beispiel GmbH", "Head of Customer Success")

    assert result["befund"] == "OK", result


def test_check_url_nur_tracking_parameter_beim_redirect_loest_keinen_fehlalarm_aus(monkeypatch):
    """Gegenprobe zur Überreaktions-Gefahr, die der Befund selbst benennt: kommt beim Redirect
    NUR ein Tracking-Parameter hinzu (utm_source), darf das NICHT als „umgeleitet" gelten --
    sonst würde das Vier-Augen-Gate gute Stellen blockieren."""
    import pipeline.verify_jobs as verify_jobs

    original = "https://de.indeed.com/rc/clk?jk=6c239a837eaf1c0a"
    final = "https://de.indeed.com/rc/clk?jk=6c239a837eaf1c0a&utm_source=email"

    monkeypatch.setattr(
        verify_jobs.httpx, "Client",
        lambda **kw: _FakeClient(final, status_code=200,
                                  text="Beispiel GmbH sucht: Head of Customer Success. "
                                       "Aufgaben: Kundenerfolg verantworten, Team führen."),
    )

    result = verify_jobs.check_url(original, "Beispiel GmbH", "Head of Customer Success")

    assert result["befund"] == "OK", (
        f"nur ein Tracking-Parameter kam hinzu -- darf NICHT als Redirect gelten: {result}"
    )


def test_check_url_query_ohne_identitaetstragenden_wert_faellt_auf_pfad_check_zurueck(monkeypatch):
    """Regressionsschutz: eine URL ohne Query (oder nur mit Tracking-Query) verhält sich exakt
    wie vor dem Fix -- der bisherige, rein pfadbasierte 'Redirect auf generische Seite'-Check
    bleibt unverändert wirksam."""
    import pipeline.verify_jobs as verify_jobs

    original = "https://portal.example.com/jobs/senior-manager-customer-success-12345"
    final = "https://portal.example.com/jobs"   # Pfad-Segment komplett verschwunden

    monkeypatch.setattr(
        verify_jobs.httpx, "Client",
        lambda **kw: _FakeClient(final, status_code=200, text="Alle offenen Stellen im Überblick."),
    )

    result = verify_jobs.check_url(original, "Beispiel GmbH", "Senior Manager Customer Success")

    assert result["befund"] == "UMGELEITET_GENERISCH", result
