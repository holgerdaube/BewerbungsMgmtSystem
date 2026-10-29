#!/usr/bin/env bash
# Phase 57 E3 -- installiert den lokalen Secret-Guard als pre-commit-Hook.
#
# Hooks liegen NICHT im Repo (git versioniert .git/hooks nicht) und leben hier zudem unter
# .git.nosync/hooks/ (separate-git-dir, .git ist nur eine Zeiger-Datei -- siehe
# tasks/lessons.md "Git + iCloud"). Dieses Skript ist der versionierte Weg dorthin: einmal
# pro Klon ausfuehren. "git rev-parse --absolute-git-dir" loest die Zeiger-Datei korrekt auf
# (git-eigener, robuster Mechanismus -- kein manuelles Parsen von .git noetig).
#
# Idempotent: ein von DIESEM Installer gesetzter Hook (erkennbar am MARKER unten) wird
# anstandslos ueberschrieben. Ein FREMDER pre-commit-Hook (vom Nutzer oder einem anderen
# Tool angelegt) wird NICHT ueberschrieben -- das Skript bricht dann mit Hinweis ab.
#
# Der installierte Hook ist nur ein duenner Wrapper, der das versionierte
# scripts/precommit_secret_scan.sh aufruft (ein Quellcode, kein Duplikat) -- Aenderungen an
# der Musterliste wirken damit sofort, ohne Neu-Installation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOK_SOURCE="$PROJECT_ROOT/scripts/precommit_secret_scan.sh"

if [ ! -x "$HOOK_SOURCE" ]; then
  echo "Abbruch: $HOOK_SOURCE fehlt oder ist nicht ausfuehrbar." >&2
  exit 1
fi

GIT_DIR="$(cd "$PROJECT_ROOT" && git rev-parse --absolute-git-dir)"
HOOKS_DIR="$GIT_DIR/hooks"
TARGET="$HOOKS_DIR/pre-commit"
MARKER="# Installiert von scripts/install_hooks.sh (Phase 57 E3) -- Quelle: scripts/precommit_secret_scan.sh, nicht manuell editieren"

mkdir -p "$HOOKS_DIR"

if [ -e "$TARGET" ] && ! grep -qF "$MARKER" "$TARGET" 2>/dev/null; then
  echo "Abbruch: $TARGET existiert bereits und stammt nicht von diesem Installer." >&2
  echo "Bitte pruefen und ggf. manuell zusammenfuehren, dann erneut versuchen." >&2
  exit 1
fi

{
  printf '#!/usr/bin/env bash\n'
  printf '%s\n' "$MARKER"
  printf 'exec "%s" "$@"\n' "$HOOK_SOURCE"
} > "$TARGET"

chmod +x "$TARGET"
echo "pre-commit-Hook installiert: $TARGET"
echo "  -> ruft auf: $HOOK_SOURCE"
