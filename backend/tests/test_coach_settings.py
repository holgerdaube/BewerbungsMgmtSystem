"""Tests für `pipeline/coach_settings.py` (Phase 82, Arbeitspaket A1) — Settings-Rundlauf,
env-Migration aus Phase 81, Shell-Kontrakt (1.3), Coach-Login-Hashing, Geheimnis-Filterung (I2).

SICHERHEITSREGEL: diese Tests rühren das echte
`~/.bewerbung_mgmt_secrets/` NIE an. Die drei Pfad-Konstanten `SETTINGS_FILE`/`ENV_FILE`/
`HTPASSWD_FILE` sind beim Modul-Import an `SECRETS_DIR` gebunden (s. Kopf von
`coach_settings.py`) — ein reiner `BMS_SECRETS_DIR`-Envvar-Override griffe hier zu spät (das
Modul wurde ja evtl. schon vorher von einem anderen Test importiert). Deshalb werden alle drei
Konstanten einzeln per `monkeypatch` auf `tmp_path` umgelenkt.

App-/Pipeline-Importe innerhalb der Fixture bzw. Testfunktionen (Konvention aus
conftest.py-Docstring).
"""
import os
import stat

import pytest

# NTFS bildet chmod 600/700 nicht ab (Windows-CI-Fund 12.08.2026: 0o666 statt 0o600) — die
# Rechte-Asserts laufen deshalb nur unter POSIX, alles andere im selben Test bleibt auf beiden
# Plattformen scharf. Gleiche Begründung wie tests/test_log_pfade.py, s. docs/SETUP-WINDOWS.md;
# dort reicht ein skipif für den ganzen Test, hier nicht: diese Tests prüfen zusätzlich
# Rundlauf, Hash-Format und checkpw — Prüfungen, die auf Windows gelten müssen.
_POSIX_RECHTE = os.name != "nt"


@pytest.fixture()
def coach_secrets(tmp_path, monkeypatch):
    """Patcht `SETTINGS_FILE`/`ENV_FILE`/`HTPASSWD_FILE` auf `tmp_path` und gibt das Modul
    selbst zurück (Muster `test_mail_settings_api.py::settings_file`, hier für drei
    zusammengehörige Pfade statt einem)."""
    import pipeline.coach_settings as coach_settings

    monkeypatch.setattr(coach_settings, "SETTINGS_FILE", tmp_path / "coach_settings.json")
    monkeypatch.setattr(coach_settings, "ENV_FILE", tmp_path / "coach_sftp.env")
    monkeypatch.setattr(coach_settings, "HTPASSWD_FILE", tmp_path / "coach_htpasswd")
    return coach_settings


VOLLSTAENDIGE_SETTINGS = {
    "aktiv": True,
    "site_url": "https://coach.meine-domain.de",
    "sftp_host": "access-xyz.webspace-host.com",
    "sftp_user": "u1234567",
    "sftp_password": "geheimes-sftp-passwort",
    "sftp_dir": "/coach",
    "authuserfile": "/srv/www/coach/.htpasswd",
    "coach_user": "berater",
}


# ── 1. save_settings/load_settings: Rundlauf + Rechte ───────────────────────────────────
def test_save_settings_schreibt_600_und_700_load_liest_zurueck(coach_secrets):
    coach_secrets.save_settings(VOLLSTAENDIGE_SETTINGS)

    assert coach_secrets.SETTINGS_FILE.exists()
    if _POSIX_RECHTE:
        mode_datei = stat.S_IMODE(coach_secrets.SETTINGS_FILE.stat().st_mode)
        assert mode_datei == 0o600, f"erwarte chmod 600, gefunden {oct(mode_datei)}"
        mode_dir = stat.S_IMODE(coach_secrets.SETTINGS_FILE.parent.stat().st_mode)
        assert mode_dir == 0o700, f"erwarte chmod 700, gefunden {oct(mode_dir)}"

    zurueck = coach_secrets.load_settings()
    assert zurueck == VOLLSTAENDIGE_SETTINGS
    assert coach_secrets.quelle() == "settings"


def test_save_settings_verwirft_unbekannte_felder_und_ergaenzt_fehlende(coach_secrets):
    coach_secrets.save_settings({"aktiv": True, "site_url": "https://x.example", "unfug": "raus"})

    zurueck = coach_secrets.load_settings()
    assert zurueck["aktiv"] is True
    assert zurueck["site_url"] == "https://x.example"
    assert "unfug" not in zurueck
    assert zurueck["sftp_host"] == ""   # fehlend -> Default ergaenzt


def test_load_settings_ohne_jede_datei_liefert_defaults_und_quelle_leer(coach_secrets):
    assert not coach_secrets.SETTINGS_FILE.exists()
    assert not coach_secrets.ENV_FILE.exists()

    zurueck = coach_secrets.load_settings()
    assert zurueck["aktiv"] is False
    assert zurueck["site_url"] == ""
    assert coach_secrets.quelle() == "leer"


# ── 2. env-Migration aus Phase 81 ────────────────────────────────────────────────────────
def test_env_migration_liefert_werte_aktiv_true_und_quelle_env_migriert(coach_secrets):
    env_inhalt = (
        "# Coach SFTP Zugang (Phase 81)\n"
        "\n"
        'export COACH_SFTP_HOST="access-abc.webspace-host.com"\n'
        "COACH_SFTP_USER=u7654321\n"
        "COACH_SFTP_PASS='geheim mit leerzeichen'\n"
        "COACH_SFTP_DIR=/coach\n"
        "COACH_AUTHUSERFILE=/srv/www/coach/.htpasswd\n"
    )
    coach_secrets.ENV_FILE.write_text(env_inhalt, encoding="utf-8")

    zurueck = coach_secrets.load_settings()
    assert zurueck["aktiv"] is True
    assert zurueck["sftp_host"] == "access-abc.webspace-host.com"
    assert zurueck["sftp_user"] == "u7654321"
    assert zurueck["sftp_password"] == "geheim mit leerzeichen"
    assert zurueck["sftp_dir"] == "/coach"
    assert zurueck["authuserfile"] == "/srv/www/coach/.htpasswd"
    assert zurueck["site_url"] == ""    # gab es in Phase 81 noch nicht
    assert zurueck["coach_user"] == ""  # dito
    assert coach_secrets.quelle() == "env-migriert"

    # env-Datei bleibt byte-identisch -- sie wird NUR gelesen (Rollback-Pfad, Bau-Spec 1.2):
    assert coach_secrets.ENV_FILE.read_text(encoding="utf-8") == env_inhalt


def test_env_migration_parser_vertraegt_export_kommentare_leerzeilen(coach_secrets):
    env_inhalt = "\n\n# Kommentar\n#noch einer ohne Leerzeichen\n\nCOACH_SFTP_HOST=host.example\n"
    coach_secrets.ENV_FILE.write_text(env_inhalt, encoding="utf-8")

    zurueck = coach_secrets.load_settings()
    assert zurueck["sftp_host"] == "host.example"
    assert coach_secrets.quelle() == "env-migriert"


def test_settings_datei_hat_vorrang_vor_env_datei(coach_secrets):
    coach_secrets.ENV_FILE.write_text("COACH_SFTP_HOST=aus-env\n", encoding="utf-8")
    coach_secrets.save_settings({**VOLLSTAENDIGE_SETTINGS, "sftp_host": "aus-settings"})

    zurueck = coach_secrets.load_settings()
    assert zurueck["sftp_host"] == "aus-settings"
    assert coach_secrets.quelle() == "settings"


# ── 3. shell_zeilen (Shell-Kontrakt 1.3) ─────────────────────────────────────────────────
def test_shell_zeilen_ohne_konfiguration_liefert_aktiv_0_und_alle_sieben_zeilen(coach_secrets):
    ausgabe = coach_secrets.shell_zeilen(coach_secrets.load_settings())
    zeilen = ausgabe.strip().splitlines()

    assert "COACH_AKTIV='0'" in ausgabe
    assert len(zeilen) == 7
    for name in ("COACH_AKTIV", "COACH_SITE_URL", "COACH_SFTP_HOST", "COACH_SFTP_USER",
                 "COACH_SFTP_PASS", "COACH_SFTP_DIR", "COACH_AUTHUSERFILE"):
        assert any(z.startswith(f"{name}=") for z in zeilen), f"{name} fehlt in shell_zeilen()"


def test_shell_zeilen_ist_eval_sicher_mit_sonderzeichen_im_passwort(coach_secrets):
    import shlex

    daten = {**VOLLSTAENDIGE_SETTINGS, "sftp_password": "a b'c$d"}
    ausgabe = coach_secrets.shell_zeilen(daten)
    assert "COACH_AKTIV='1'" in ausgabe

    pass_zeile = next(z for z in ausgabe.splitlines() if z.startswith("COACH_SFTP_PASS="))
    # shlex.split simuliert, wie eine POSIX-Shell die Zeile per `eval` einliest -- muss GENAU
    # ein Token ergeben (kein durch das Leerzeichen im Passwort aufgebrochener zweiter Token)
    # und exakt den Originalwert zurueckgeben:
    (token,) = shlex.split(pass_zeile)
    assert token == "COACH_SFTP_PASS=a b'c$d"


# ── 4. set_coach_login ───────────────────────────────────────────────────────────────────
def test_set_coach_login_schreibt_600_eine_zeile_2y_hash_checkpw_true(coach_secrets):
    import bcrypt

    coach_secrets.set_coach_login("berater", "sehr-geheimes-passwort")

    assert coach_secrets.HTPASSWD_FILE.exists()
    if _POSIX_RECHTE:
        mode = stat.S_IMODE(coach_secrets.HTPASSWD_FILE.stat().st_mode)
        assert mode == 0o600, f"erwarte chmod 600, gefunden {oct(mode)}"

    inhalt = coach_secrets.HTPASSWD_FILE.read_text(encoding="utf-8")
    zeilen = inhalt.splitlines()
    assert len(zeilen) == 1
    assert inhalt.endswith("\n")
    benutzer, hash_teil = zeilen[0].split(":", 1)
    assert benutzer == "berater"
    assert hash_teil.startswith("$2y$")
    # beweist, dass das Umschreiben des Praefixes ($2b$ -> $2y$) den Hash nicht kaputt macht:
    assert bcrypt.checkpw(b"sehr-geheimes-passwort", hash_teil.encode("ascii"))

    assert coach_secrets.coach_login_gesetzt() is True
    assert coach_secrets.coach_login_benutzer() == "berater"


def test_set_coach_login_ueberschreibt_vorherigen_login_mit_genau_einer_zeile(coach_secrets):
    coach_secrets.set_coach_login("erst", "passwort-eins")
    coach_secrets.set_coach_login("dann", "passwort-zwei")

    zeilen = coach_secrets.HTPASSWD_FILE.read_text(encoding="utf-8").splitlines()
    assert len(zeilen) == 1
    assert coach_secrets.coach_login_benutzer() == "dann"


def test_set_coach_login_leerer_benutzername_wirft_valueerror(coach_secrets):
    with pytest.raises(ValueError):
        coach_secrets.set_coach_login("", "irgendein-passwort")
    assert not coach_secrets.HTPASSWD_FILE.exists()


def test_set_coach_login_passwort_ueber_72_byte_wirft_valueerror(coach_secrets):
    with pytest.raises(ValueError):
        coach_secrets.set_coach_login("berater", "x" * 73)
    assert not coach_secrets.HTPASSWD_FILE.exists()


def test_coach_login_gesetzt_und_benutzer_ohne_datei(coach_secrets):
    assert coach_secrets.coach_login_gesetzt() is False
    assert coach_secrets.coach_login_benutzer() == ""


# ── 5. ohne_geheimnisse (I2) ──────────────────────────────────────────────────────────────
def test_ohne_geheimnisse_entfernt_sftp_url_zeile_und_klartext_passwort(coach_secrets):
    daten = {"sftp_password": "geheim123"}
    text = (
        "cd /coach: Login OK\n"
        "cd sftp://u1234567:geheim123@sftp.beispiel.de: Verbindung\n"
        "put fehlgeschlagen, Passwort war geheim123 falsch\n"
    )
    gefiltert = coach_secrets.ohne_geheimnisse(text, daten)
    assert "sftp://" not in gefiltert
    assert "geheim123" not in gefiltert
    assert "cd /coach: Login OK" in gefiltert
    assert "put fehlgeschlagen, Passwort war *** falsch" in gefiltert


def test_ohne_geheimnisse_ohne_passwort_in_data_entfernt_trotzdem_sftp_zeile(coach_secrets):
    text = "sftp://user:pass@host: Fehler beim Verbinden\nweitere unschuldige Zeile"
    gefiltert = coach_secrets.ohne_geheimnisse(text, {})
    assert "sftp://" not in gefiltert
    assert "weitere unschuldige Zeile" in gefiltert
