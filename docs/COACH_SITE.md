# Coach-Site (Phase 81, ab Phase 82 konfigurierbar) — Read-only-Spiegel für den Coach

Passwortgeschützte, statische Momentaufnahme des Bewerbungsstands für einen externen Coach.
Quelle der Wahrheit bleibt der Mac; Export ist deterministischer Code (KEIN LLM, 0 Kosten).
Seit Phase 82 sind Zieladresse, SFTP-Zugang und Coach-Login **pro Installation über
Einstellungen → Coach-Site konfigurierbar** — vorher war die Funktion auf eine einzelne Installation
festgenagelt (Terminal-Skripte, eine feste Adresse im Template). Adressen stehen in diesem Dokument nur
als Beispiel (`coach.example.org`).
Die Specs mit allen Entscheidungen (Phase 81: Export/Sichtbarkeit, Phase 82: Konfiguration/API) gehören
zum Projektverlauf des Autors und liegen nicht im öffentlichen Repository. Schritt-für-Schritt-Anleitung
für die Ersteinrichtung (auch für Nicht-Entwickler): `docs/ANLEITUNG_COACH_SITE.md` (gleiche
Inhalte als druckbares Handbuch: `docs/ANLEITUNG_COACH_SITE.html`) — dieses Dokument hier bleibt
die kompakte Betriebs-/Architekturseite für Entwickler.

## Was der Coach sieht / nie sieht

**Sichtbar:** Übersicht (KPIs + Status-Verteilung) · **Tages-Digest** (P2-79, Reiter direkt nach
der Übersicht; `digest.digest_inhalt(fuer_coach=True)`, also ohne „Zu beantworten“ (Absender und
Betreff), ohne „Offene Aktionen“ (Freitext `next_step`) und in „Heute geändert“ nur Statuswechsel aus
dem JobLog (`art='auto'`), nie eine Verlaufsnotiz; abschaltbar mit `tages_digest: false`) ·
Stellen & Bewerbungen in zwei Sektionen —
„Aktive Bewerbungen" (Angebot/Interview/Beworben) und „Sichtung & Prüfung" (Prüfen/Neu,
Erweiterung 10.08.) — je Stelle mit Company-Fit, Match und **Anzeigen-Snapshot** (immer ohne
den internen Erfassungs-Kontext; nicht sicher bereinigbare Alt-Formate werden übersprungen
und gemeldet) · Absagen mit Absagegründen + Lost-Order-Analyse (neuester Bericht nach dem Datum im
Dateinamen, mit Datum verlinkt; `pipeline/absagen_bericht.py`). Vertrauliche Mandate
erscheinen 1:1 wie in der App (Entscheidung 10.08.2026).
**Nie exportiert (testbewehrt, `tests/test_coach_export_sperrliste.py`):** E-Mails, Notizen &
Verlauf, Beirats-Checks, Gehälter, verify_note-/Erfassungs-Interna, Transkripte/Debriefs/
Briefings, CVs/Anschreiben, ATS-Scans, Netzwerk/Kontakte, Budget. Whitelist:
`config/coach_export.yaml`.

## Bausteine

| Was | Wo |
|---|---|
| Konfiguration (Adresse, SFTP-Ziel, Coach-Login-Hash) | `backend/pipeline/coach_settings.py` → `~/.bewerbung_mgmt_secrets/coach_settings.json` (600/700); migriert eine alte `coach_sftp.env` (Phase 81) automatisch, ohne sie zu verändern |
| API für die Einstellungen-Karte | `backend/app/routes_coach_settings.py` → `/api/settings/coach` (`GET`/`PUT`/`POST .../test`/`POST .../serverpfad`) |
| Exporter (DB → statische Site) | `backend/pipeline/coach_export.py` → `data/exports/coach_site/` |
| Upload (SFTP-Spiegel, lftp) | `scripts/coach_deploy.sh` (`--dry-run` / `--wipe` = Not-Aus) |
| Beides in einem (Task/Button) | `scripts/coach_site.sh` = AgentTask-Kind `coach-site` |
| Coach-Login anlegen/ändern | Normalweg: **Einstellungen → Coach-Site** (Benutzer + Passwort, App-UI) → bcrypt-Hash in `~/.bewerbung_mgmt_secrets/coach_htpasswd`. Terminal-Notnagel ohne laufende App: `scripts/coach_passwort.sh <benutzer>` |
| SFTP-Zugang | Normalweg: **Einstellungen → Coach-Site** (App-UI) → `coach_settings.json`. Alter Terminal-Pfad `~/.bewerbung_mgmt_secrets/coach_sftp.env` wird seit Phase 82 nur noch als Rückfallebene gelesen, nie mehr geschrieben |
| Schutz-Template | `assets/coach_htaccess.template` (Basic-Auth, HTTPS-Redirect, noindex; `{{SITE_URL}}`/`{{AUTH_USER_FILE}}` werden beim Deploy aus der Konfiguration gefüllt) |

Auslöser: Button „Coach-Site jetzt aktualisieren" (Einstellungen) UND automatisch als letztes
Tageslauf-Kettenglied. **Ohne vollständige Konfiguration bzw. bei abgeschaltetem Schalter endet
der Schritt grün** (nur lokaler Export, klare Meldung, Exit 0 — I4) — der Tageslauf wird nie
rot, solange die Coach-Site nicht eingerichtet ist; ein echter SFTP-Fehler NACH Einrichtung
markiert nur den coach-site-Task als failed (letztes Glied).

## Ein/Aus-Schalter

Checkbox „Coach-Site aktiv" in Einstellungen → Coach-Site (Feld `aktiv` in `coach_settings.json`).

- **Aus:** `coach_site.sh`/`coach_deploy.sh` melden „Coach-Site ist in den Einstellungen
  abgeschaltet — übersprungen." und beenden mit Exit 0 (I4 — der Tageslauf wird davon nie rot).
  Bereits hochgeladene Inhalte **bleiben unverändert** (weiterhin passwortgeschützt) auf dem
  Server liegen — Abschalten ist ein Pausieren künftiger Uploads, kein Löschen.
- **Ein, aber unvollständig konfiguriert:** `PUT /api/settings/coach` lehnt mit `422 "Zum
  Aktivieren fehlen noch: …"` ab (Feldliste aus `fehlende_felder()`); der Update-Button
  „Coach-Site jetzt aktualisieren" erscheint in der Karte erst gar nicht, bevor `aktiv=true`
  UND alle Pflichtfelder gespeichert sind.
- **Vollständiges Entfernen vom Server (Not-Aus, kein Pausieren):** `scripts/coach_deploy.sh
  --wipe` — läuft bedingungslos, auch bei `aktiv=false` (I5); scheitert nur, wenn noch nie
  SFTP-Zugangsdaten hinterlegt wurden.

## Einrichtung

Seit Phase 82 **über die UI**: Einstellungen → Coach-Site → Adresse, SFTP-Zugang, Serverpfad
zur `.htpasswd` (Button „automatisch ermitteln" oder manuell) und Coach-Login ausfüllen,
aktivieren, speichern, „Coach-Site jetzt aktualisieren" klicken. Die vollständige
Schritt-für-Schritt-Anleitung für Erstinstallationen (hoster-neutral, IONOS als
durchgespieltes Beispiel, für IT-Anfänger geschrieben) steht in **`docs/ANLEITUNG_COACH_SITE.md`**
(gleichwertige druckbare Fassung: `docs/ANLEITUNG_COACH_SITE.html`) — dort auch alle
Fehlerbilder aus der Live-Einrichtung mit Ursache und Lösung.

Kurzfassung für Entwickler-Diagnose (Terminal, aus `backend/`):
- Konfiguration ansehen (ohne Passwörter): `~/.bewerbung_mgmt_venv/bin/python -m
  pipeline.coach_settings zeigen`
- Shell-Kontrakt, wie ihn `coach_deploy.sh`/`coach_site.sh` selbst nutzen:
  `~/.bewerbung_mgmt_venv/bin/python -m pipeline.coach_settings shell`
- Erster Deploy: `scripts/coach_deploy.sh --dry-run` (zeigt Dateiliste) →
  `scripts/coach_site.sh` (Export + echter Upload).
- Abnahme: konfigurierte Adresse im Privatfenster öffnen → Login-Abfrage muss kommen (ohne
  Login: 401) · nach Login Übersicht/Tages-Digest/Stellen/Absagen prüfen ·
  `curl -sI -u <user>:<pass> <adresse> | grep -i x-robots` → `noindex`.

Beispiel: Eine Installation kann unter `https://coach.example.org` laufen (bei einem Hoster wie IONOS
oder Strato) — das ist nur ein Beispielwert; die Adresse ist seit Phase 82 je Installation frei wählbar
(Feld „Adresse der Seite" in der Coach-Karte).

## Betrieb & Rollback

Aktualisieren: Button oder Tageslauf (automatisch). Passwort ändern: Einstellungen →
Coach-Site → Bereich „Coach-Login" (oder Terminal-Notnagel `scripts/coach_passwort.sh
<benutzer>`) + optional ein manuelles Update, sonst greift die Änderung spätestens beim
nächsten Tageslauf.

**Rollback/Abschalten** (abgestuft):
1. **Nur künftige Uploads pausieren** (Inhalt bleibt live, s. o. „Ein/Aus-Schalter"): Haken
   „Coach-Site aktiv" entfernen + speichern.
2. **Seite vollständig vom Server entfernen (Not-Aus):** `scripts/coach_deploy.sh --wipe` +
   optional Subdomain beim Hoster deaktivieren.
3. **Konfiguration selbst zurücksetzen:** `~/.bewerbung_mgmt_secrets/coach_settings.json`
   löschen — `load_settings()` fällt danach automatisch auf eine evtl. noch vorhandene alte
   `coach_sftp.env` zurück, sonst auf leere Defaults; kein Code-Eingriff nötig.
4. **Code-Rollback:** `git revert` des Phase-82-Commits (Konfigurierbarkeit/API/UI) bzw. des
   Phase-81-Commits (ganze Funktion).
