"""Kontrakt-Tests für `pipeline.user_profile.anschrift()` und `GET /api/profil` → `adresse`
(P2-50, Kundenpaket — Arbeitspaket B1).

Der Startpunkt der Routenplanung zu Vorstellungsgesprächen stand bisher fest im Frontend
(`FollowUps.tsx`/`JobDetail.tsx`: `'Musterweg 1, 12345 Musterstadt'`) — falsch für jeden anderen
Nutzer. `anschrift()` liefert denselben Wert jetzt aus `config/profil.md`
(`**Standort:**`), mit derselben Klammerzusatz-Normalisierung wie `briefkopf()`
(`_standort_ohne_klammerzusatz()`). Hier per Monkeypatch auf Fixture-Dateien umgebogen — die
echte `config/profil.md` wird in diesen Tests nie gelesen (Muster `test_user_profile.py`).

Kein app.*/pipeline.*-Import auf Modulebene (conftest.py-Konvention).
"""


def test_anschrift_entfernt_klammerzusatz(tmp_path, monkeypatch):
    import pipeline.user_profile as up

    profil = tmp_path / "profil.md"
    profil.write_text(
        "## Identität\n- **Standort:** Musterweg 3, 12345 Musterstadt (Rhein-Main)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(up, "_PROFIL_MD", profil)

    assert up.anschrift() == "Musterweg 3, 12345 Musterstadt"


def test_anschrift_ohne_klammerzusatz_bleibt_unveraendert(tmp_path, monkeypatch):
    import pipeline.user_profile as up

    profil = tmp_path / "profil.md"
    profil.write_text("## Identität\n- **Standort:** Musterweg 3, 12345 Musterstadt\n", encoding="utf-8")
    monkeypatch.setattr(up, "_PROFIL_MD", profil)

    assert up.anschrift() == "Musterweg 3, 12345 Musterstadt"


def test_anschrift_fehlende_datei(tmp_path, monkeypatch):
    import pipeline.user_profile as up

    monkeypatch.setattr(up, "_PROFIL_MD", tmp_path / "nicht_vorhanden.md")

    assert up.anschrift() == ""


def test_anschrift_fehlendes_feld(tmp_path, monkeypatch):
    """Profil existiert, hat aber keine `**Standort:**`-Zeile -> leerer String, kein Crash."""
    import pipeline.user_profile as up

    profil = tmp_path / "profil.md"
    profil.write_text("## Identität\n- **Name:** Max Muster\n", encoding="utf-8")
    monkeypatch.setattr(up, "_PROFIL_MD", profil)

    assert up.anschrift() == ""


def test_get_api_profil_liefert_adresse(client, tmp_path, monkeypatch):
    """Ende zu Ende: `GET /api/profil` reicht `anschrift()` unter dem Feld `adresse` durch —
    dieselbe Quelle, die `frontend/src/profil.ts` für den Maps-Link abruft."""
    import pipeline.user_profile as up

    profil = tmp_path / "profil.md"
    profil.write_text(
        "## Identität\n- **Name:** Max Muster\n"
        "- **Standort:** Musterweg 3, 12345 Musterstadt (Rhein-Main)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(up, "_PROFIL_MD", profil)

    r = client.get("/api/profil")
    assert r.status_code == 200
    assert r.json()["profile"]["adresse"] == "Musterweg 3, 12345 Musterstadt"


def test_get_api_profil_adresse_leer_ohne_feld(client, tmp_path, monkeypatch):
    """Fehlt `**Standort:**`, liefert der Endpunkt einen leeren String statt zu crashen oder das
    Feld wegzulassen (Frontend-Hook erwartet immer den Schlüssel `adresse`)."""
    import pipeline.user_profile as up

    monkeypatch.setattr(up, "_PROFIL_MD", tmp_path / "nicht_vorhanden.md")

    r = client.get("/api/profil")
    assert r.status_code == 200
    assert r.json()["profile"]["adresse"] == ""
