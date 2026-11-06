#!/bin/zsh
# Coach-Site zu IONOS hochladen (Phase 81; Konfiguration seit Phase 82 aus den
# Einstellungen) — lftp-SFTP-Spiegel von data/exports/coach_site/.
#   scripts/coach_deploy.sh            # echter Upload (mirror -R --delete)
#   scripts/coach_deploy.sh --dry-run  # zeigt nur, was übertragen würde
#   scripts/coach_deploy.sh --wipe     # leert das Zielverzeichnis (Rollback), lädt NICHTS hoch
# Zugang kommt über den Shell-Kontrakt aus pipeline.coach_settings (Einstellungen → Coach-
# Site in der App); die alte ~/.bewerbung_mgmt_secrets/coach_sftp.env (Phase 81) ist nur noch
# der Rollback-Pfad und wird von coach_settings.py automatisch migriert, wenn keine
# coach_settings.json existiert — dieses Skript kennt die Datei gar nicht mehr direkt.
# Ist die Funktion abgeschaltet oder unvollständig konfiguriert, endet der Upload mit
# Exit 0 (Tageslauf bleibt grün, s. docs/COACH_SITE.md) — NUR --wipe läuft bedingungslos
# (Not-Aus, auch bei abgeschalteter Funktion).
set -euo pipefail
# P2-95: Sprache der Meldungen. Der Runner setzt BMS_TERMINAL_SPRACHE auf die Sprache der Oberfläche, weil die Ausgabe
# im Task-Center landet; von Hand gestartet folgt das Skript dem Betriebssystem.
if [ -z "${BMS_TERMINAL_SPRACHE:-}" ]; then
  _bms_lang=$({ defaults read -g AppleLanguages 2>/dev/null || true; } | sed -n '2p' | tr -d ' ",')
  [ -n "$_bms_lang" ] || _bms_lang=$(defaults read -g AppleLocale 2>/dev/null || true)
  [ -n "$_bms_lang" ] || _bms_lang="${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}"
  case "$_bms_lang" in
    de*|De*|DE*) BMS_TERMINAL_SPRACHE=de ;;
    *) BMS_TERMINAL_SPRACHE=en ;;
  esac
fi
_m() { if [ "$BMS_TERMINAL_SPRACHE" = "de" ]; then print -r -- "$1"; else print -r -- "$2"; fi; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SECRETS="$HOME/.bewerbung_mgmt_secrets"
VENV="$HOME/.bewerbung_mgmt_venv/bin/python"
EXPORT_DIR="$ROOT/data/exports/coach_site"

# Shell-Kontrakt statt "source coach_sftp.env" (Phase 82): liest coach_settings.json, fällt
# ohne sie auf die alte env-Datei zurück, gibt IMMER Exit 0 zurück (auch ohne jede
# Konfiguration, dann COACH_AKTIV='0' und leere Werte) — sonst würde ein reines set -e hier
# den Tageslauf abreißen, noch bevor wir überhaupt "abgeschaltet" melden können.
eval "$(cd "$ROOT/backend" && "$VENV" -m pipeline.coach_settings shell)"
# Defensive Defaults: falls der Kontrakt aus irgendeinem Grund NICHTS ausgibt (z. B. das Modul
# fehlt noch), sollen die Variablen leer/aus sein statt "unbound variable" unter set -u —
# das führt sauber in die "abgeschaltet/nicht eingerichtet"-Zweige statt in einen Absturz.
: "${COACH_AKTIV:=0}"
: "${COACH_SITE_URL:=}"
: "${COACH_SFTP_HOST:=}"
: "${COACH_SFTP_USER:=}"
: "${COACH_SFTP_PASS:=}"
: "${COACH_SFTP_DIR:=}"
: "${COACH_AUTHUSERFILE:=}"

# --wipe zuerst und BEDINGUNGSLOS (I5, Not-Aus) — die Aktiv-Prüfung steht bewusst dahinter,
# denn --wipe soll auch bei aktiv=false noch etwas vom Server räumen können. Nur ganz ohne
# Zugangsdaten ist es tatsächlich unmöglich (dann Exit 1 mit klarer Meldung — --wipe ist ein
# manueller Terminal-Befehl, kein Tageslauf-Schritt, I4 verlangt hier kein Exit 0).
if [ "${1:-}" = "--wipe" ]; then
  if ! command -v lftp >/dev/null 2>&1; then
    _m "coach_deploy: lftp fehlt — installieren mit: brew install lftp" "coach_deploy: lftp is missing, install it with: brew install lftp" >&2
    exit 1
  fi
  if [ -z "$COACH_SFTP_HOST" ] || [ -z "$COACH_SFTP_USER" ] || [ -z "$COACH_SFTP_PASS" ] || [ -z "$COACH_SFTP_DIR" ]; then
    _m "coach_deploy: --wipe kann nicht laufen — keine SFTP-Zugangsdaten hinterlegt (Einstellungen → Coach-Site)." "coach_deploy: --wipe cannot run, no SFTP credentials stored (Settings → Coach site)." >&2
    exit 1
  fi
  lftp -u "$COACH_SFTP_USER","$COACH_SFTP_PASS" "sftp://$COACH_SFTP_HOST" -e "
    set sftp:auto-confirm yes;
    rm -rf $COACH_SFTP_DIR/*; rm -f $COACH_SFTP_DIR/.htaccess $COACH_SFTP_DIR/.htpasswd;
    bye" && echo "✓ Zielverzeichnis geleert (Rollback)."
  exit 0
fi

# Ab hier normaler Deploy: Aktiv-Prüfung VOR dem Upload (I4) — abgeschaltet ist kein Fehler.
if [ "$COACH_AKTIV" != "1" ]; then
  _m "Coach-Site ist in den Einstellungen abgeschaltet — übersprungen." "The coach site is switched off in the settings, skipped."
  exit 0
fi

# Pflichtfelder einzeln prüfen (bisherige ": ${VAR:?…}"-Guards sinngemäß erhalten, aber jetzt
# Exit 0 statt Exit 1 — dieses Skript läuft seit Phase 81 auch am Ende des Tageslaufs, I4 gilt
# hier genauso wie beim Abschalten). COACH_SFTP_HOST zuerst: das ist "noch gar nicht
# eingerichtet", die anderen sind "unvollständig eingerichtet".
if [ -z "$COACH_SFTP_HOST" ]; then
  _m "coach_deploy: SFTP-Zugang ist noch nicht eingerichtet — Upload übersprungen." "coach_deploy: SFTP access is not set up yet, upload skipped."
  _m "Einrichten unter: Einstellungen → Coach-Site (in der App)." "Set it up under: Settings → Coach site (in the app)."
  exit 0
fi
if [ -z "$COACH_SFTP_USER" ]; then
  _m "coach_deploy: SFTP-Benutzer fehlt — bitte in Einstellungen → Coach-Site ergänzen. Upload übersprungen." "coach_deploy: SFTP user is missing, please add it under Settings → Coach site. Upload skipped."
  exit 0
fi
if [ -z "$COACH_SFTP_PASS" ]; then
  _m "coach_deploy: SFTP-Passwort fehlt — bitte in Einstellungen → Coach-Site ergänzen. Upload übersprungen." "coach_deploy: SFTP password is missing, please add it under Settings → Coach site. Upload skipped."
  exit 0
fi
if [ -z "$COACH_SFTP_DIR" ]; then
  _m "coach_deploy: SFTP-Zielverzeichnis fehlt — bitte in Einstellungen → Coach-Site ergänzen (z. B. /coach). Upload übersprungen." "coach_deploy: SFTP target folder is missing, please add it under Settings → Coach site (for example /coach). Upload skipped."
  exit 0
fi
if [ -z "$COACH_AUTHUSERFILE" ]; then
  _m "coach_deploy: Serverpfad zur .htpasswd fehlt — bitte in Einstellungen → Coach-Site ergänzen (automatisch ermitteln oder manuell eintragen). Upload übersprungen." "coach_deploy: server path to .htpasswd is missing, please add it under Settings → Coach site (detect automatically or enter by hand). Upload skipped."
  exit 0
fi

if ! command -v lftp >/dev/null 2>&1; then
  _m "coach_deploy: lftp fehlt — installieren mit: brew install lftp" "coach_deploy: lftp is missing, install it with: brew install lftp" >&2
  exit 1
fi

[ -d "$EXPORT_DIR" ] || { echo "coach_deploy: $EXPORT_DIR fehlt — erst 'python -m pipeline.coach_export'." >&2; exit 1; }

# .htaccess aus Template + Serverpfad + Zieladresse erzeugen; .htpasswd aus den Secrets dazulegen.
# Fehlt COACH_SITE_URL (z. B. Alt-Migration aus coach_sftp.env, s. coach_settings.py), wird die
# ErrorDocument-Zeile ersatzlos gelöscht statt einen kaputten {{SITE_URL}}-Platzhalter
# hochzuladen — Require all denied schützt HTTP-Zugriffe trotzdem weiter (s. Template-Kommentar).
if [ -z "$COACH_SITE_URL" ]; then
  sed -e "s|{{AUTH_USER_FILE}}|$COACH_AUTHUSERFILE|" -e '/{{SITE_URL}}/d' \
    "$ROOT/assets/coach_htaccess.template" > "$EXPORT_DIR/.htaccess"
else
  sed -e "s|{{AUTH_USER_FILE}}|$COACH_AUTHUSERFILE|" -e "s|{{SITE_URL}}|$COACH_SITE_URL|" \
    "$ROOT/assets/coach_htaccess.template" > "$EXPORT_DIR/.htaccess"
fi
if [ -f "$SECRETS/coach_htpasswd" ]; then
  cp "$SECRETS/coach_htpasswd" "$EXPORT_DIR/.htpasswd"
  # 644 statt der geerbten 600: mirror überträgt Permissions, und Apaches Auth-Prozess läuft
  # bei IONOS unter anderem User als SFTP/PHP — 600 ergab "Internal Server Error" NACH der
  # Login-Eingabe (Live-Befund 10.08.2026). Browser-Zugriff auf .htpasswd bleibt trotzdem
  # gesperrt (Apache-Default für .ht*, verifiziert: 403).
  chmod 644 "$EXPORT_DIR/.htpasswd"
else
  _m "coach_deploy: WARNUNG — $SECRETS/coach_htpasswd fehlt (Coach-Login setzen: Einstellungen → Coach-Site, oder scripts/coach_passwort.sh <user>)." "coach_deploy: WARNING: $SECRETS/coach_htpasswd is missing (set the coach login: Settings → Coach site, or scripts/coach_passwort.sh <user>)." >&2
  _m "Ohne .htpasswd verweigert der Server JEDEN Zugriff (500) — Upload abgebrochen." "Without .htpasswd the server refuses EVERY request (500), upload stopped." >&2
  exit 1
fi

MODE_FLAGS=""
[ "${1:-}" = "--dry-run" ] && MODE_FLAGS="--dry-run"

# auto-confirm: IONOS-Hostkey beim Erstkontakt annehmen (Shared-Hosting-Pragmatik; wer strenger
# will, verbindet einmal manuell mit lftp und entfernt die Zeile).
# Quelle ist "." nach cd — lftp zerlegt gequotete Pfade mit Leerzeichen (iCloud: "Mobile
# Documents") sonst am Space (Abnahme-Befund 10.08.2026).
cd "$EXPORT_DIR"
lftp -u "$COACH_SFTP_USER","$COACH_SFTP_PASS" "sftp://$COACH_SFTP_HOST" -e "
  set sftp:auto-confirm yes;
  mirror -R --delete $MODE_FLAGS . $COACH_SFTP_DIR;
  bye"
_m "✓ coach_deploy ${1:-upload} abgeschlossen → ${COACH_SITE_URL:-<Zieladresse nicht gesetzt>}" "✓ coach_deploy ${1:-upload} complete → ${COACH_SITE_URL:-<target address not set>}"
