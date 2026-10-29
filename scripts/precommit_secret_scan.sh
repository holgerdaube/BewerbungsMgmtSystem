#!/usr/bin/env bash
# Phase 57 E3 -- lokaler Secret-Guard (Bordmittel: nur git + grep, Invariante T7 aus
# tasks/spec_phase57_tests_ci.md). Ersetzt NICHT den gitleaks-CI-Job (voller Historien-Scan,
# .github/workflows/ci.yml Job "secret-scan") -- das hier ist die schnelle lokale Vorstufe,
# die einen Fund VOR dem Commit abfaengt statt erst nach dem Push.
#
# Prueft NUR staged Aenderungen (git diff --cached, ausschliesslich neu HINZUGEFUEGTE Zeilen)
# gegen eine feste Musterliste. Bestehende, bereits committete Zeilen werden nicht erneut
# durchsucht (das ist Aufgabe des CI-Jobs mit voller Historie).
#
# SELBSTMATCH-FALLE (siehe Bau-Auftrag Phase 57 E3): jedes unserer Erkennungsmuster darf im
# Quelltext DIESER Datei nirgends als zusammenhaengende Zeichenkette auftauchen -- auch nicht
# als ausgeschriebenes Beispiel innerhalb dieses Kommentarblocks selbst (genau das waere die
# Falle: ein erklaerendes Beispiel, das das Muster nochmal zusammenhaengend hinschreibt).
# Wuerde irgendwo eine zusammenhaengende Kopie stehen, wuerde der allererste Commit dieses
# Skripts (die neu hinzugefuegten Zeilen SIND der Quelltext) das eigene Muster treffen und
# sich selbst blockieren. Loesung: jedes Muster wird unten als zwei separate Teilstrings
# geschrieben (siehe die p_*-Variablen); die Shell verkettet direkt aneinanderstossende
# Quotes zur Laufzeit zu einem einzigen Wort, im Quelltext stehen die beiden Haelften aber
# stets durch ein Anfuehrungszeichenpaar getrennt. Kein Grep-Muster (dieses eigene
# eingeschlossen) findet darin eine zusammenhaengende Treffer-Zeichenkette. Damit bleibt das
# Skript vollstaendig selbst-scannend: kein Pfad-Ausschluss, kein blinder Fleck fuer
# kuenftige Aenderungen an dieser Datei.
set -euo pipefail

p_anthropic="sk-an""t-"
p_gho="gho""_"
p_ghp="ghp""_"
p_ghpat="github_pa""t_"
p_gcp="AIza[0-9A-Za-z_-]""{20,}"
p_refresh='"refresh_toke''n"\s*:\s*"'
p_clientsecret='"client_secre''t"\s*:\s*"'
p_privkey="BEGIN [A-Z ]*PRIVATE ""KEY"
p_apify="apify_ap""i_"

pattern="${p_anthropic}|${p_gho}|${p_ghp}|${p_ghpat}|${p_gcp}|${p_refresh}|${p_clientsecret}|${p_privkey}|${p_apify}"

files="$(git diff --cached --name-only)"

if [ -z "$files" ]; then
  exit 0
fi

found=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  # -a: auch Dateien pruefen, die git/diff evtl. als "binaer" einstuft (z.B. ohne Endung) --
  # sonst koennte ein Fund in einer Datei ohne Text-Kennung stillschweigend durchrutschen.
  hits="$(git diff --cached -U0 --no-color -a -- "$f" 2>/dev/null | grep -E '^\+[^+]' | grep -E "$pattern" || true)"
  if [ -n "$hits" ]; then
    found=1
    echo "Secret-Guard: moeglicher Fund in '$f':" >&2
    printf '%s\n' "$hits" | sed 's/^+/  + /' >&2
  fi
done <<< "$files"

if [ "$found" -eq 1 ]; then
  echo "" >&2
  echo "Commit blockiert (scripts/precommit_secret_scan.sh)." >&2
  echo "Bewusste Ausnahme (z. B. gepruefter Platzhalter): git commit --no-verify" >&2
  exit 1
fi

exit 0
