#!/bin/zsh
# Coach-Login anlegen/ändern (Phase 81): schreibt den bcrypt-Hash nach
# ~/.bewerbung_mgmt_secrets/coach_htpasswd — das Klartext-Passwort sieht nur, wer es hier
# eintippt (htpasswd fragt interaktiv, nichts landet in Shell-History oder Chat).
#
# Normalweg ist jetzt Einstellungen → Coach-Site (Benutzer + Passwort) in der App — das legt
# denselben ~/.bewerbung_mgmt_secrets/coach_htpasswd per bcrypt an (Phase 82). Dieses Skript
# ist der Notnagel ohne laufende App (z. B. Passwort ändern direkt am Terminal).
set -e
SECRETS="$HOME/.bewerbung_mgmt_secrets"
mkdir -p "$SECRETS"
if [ -z "$1" ]; then
  echo "Aufruf: scripts/coach_passwort.sh <benutzername>"
  echo "Beispiel: scripts/coach_passwort.sh coach"
  exit 2
fi
# -c legt die Datei neu an (genau EIN Coach-Login); -B = bcrypt (Apache 2.4 auf IONOS)
htpasswd -cB "$SECRETS/coach_htpasswd" "$1"
chmod 600 "$SECRETS/coach_htpasswd"
echo "✓ $SECRETS/coach_htpasswd geschrieben (Benutzer: $1) — wird beim nächsten Deploy als .htpasswd hochgeladen."
