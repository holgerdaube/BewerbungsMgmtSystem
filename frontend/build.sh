#!/bin/zsh
# Baut das Frontend AUSSERHALB von iCloud und kopiert nur dist/ zurück.
# Grund: iCloud synct/re-materialisiert node_modules im Projekt und zerstört Symlinks.
# Quelle bleibt in iCloud, node_modules lebt dauerhaft unter ~/.bewerbung_mgmt_node/frontend_build.
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
BUILD="$HOME/.bewerbung_mgmt_node/frontend_build"
mkdir -p "$BUILD"

# Quelle spiegeln (ohne node_modules/dist), node_modules im Build-Spiegel bleibt erhalten
rsync -a --delete --exclude node_modules --exclude dist "$SRC"/ "$BUILD"/

cd "$BUILD"
# Install auch, wenn package.json NEUER ist als der letzte Install-Stand — sonst werden
# nachträglich ergänzte Dependencies nie installiert (Phase 80: @fontsource-Pakete fehlten,
# Rollup konnte die Font-Importe nicht auflösen).
if [ ! -x node_modules/.bin/vite ] || [ package.json -nt node_modules/.package-lock.json ]; then
  echo "Installiere Dependencies…"
  npm install --no-audit --no-fund
  # Lockfile ZURÜCK ins Projekt spiegeln — die CI läuft mit `npm ci` gegen die versionierte
  # package-lock.json; ohne Rücksync bricht sie bei jeder neuen Dependency (Phase 80, CI-Lauf
  # 31381624608: "Missing: @fontsource/… from lock file").
  cp package-lock.json "$SRC/package-lock.json"
fi

npm run build

# fertiges dist/ zurück nach iCloud (klein, statisch)
mkdir -p "$SRC/dist"
rsync -a --delete "$BUILD"/dist/ "$SRC"/dist/
echo "✓ Build fertig → $SRC/dist"
