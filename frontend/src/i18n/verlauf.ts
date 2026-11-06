import { aktuelleSprache, t } from './index'
import { wert } from './werte'

// Verlaufszeilen stehen so in der Datenbank, wie sie geschrieben wurden, und die Status darin sind
// Maschinenwerte (der Tagesbericht liest `Status: a → b`). Übersetzt wird deshalb nur die Anzeige und nur
// bei automatischen Einträgen: Was der Nutzer selbst schreibt oder die KI antwortet, bleibt unberührt.
const WERT_ZEILE = /^([^:]+): (.+?) → (.+?)( \(Review\))?$/
const NAECHSTER_SCHRITT = /^Nächster Schritt: „(.*)“$/s // i18n-ok: Muster für alte Zeilen
const NEUAUSSCHREIBUNG = /^NEUAUSSCHREIBUNG\? Job (\d+) „([^“]*)“ — ([^,]+), zuerst gefunden (.+)$/ // i18n-ok: Marker
const DUBLETTE = /^DUBLETTE\? Job (\d+) „([^“]*)“ — Text-Ähnlichkeit (\d+) % \(geprüft ([^)]+)\)$/ // i18n-ok: Marker

const statusWert = (s: string) => wert('status', s)

function segment(s: string, wertText: (w: string) => string): string {
  const fest = t(`common:verlauf.fest.${s}`, { defaultValue: '' })
  if (fest) return fest
  let m = s.match(NAECHSTER_SCHRITT)
  if (m) return t('common:verlauf.naechster_schritt', { wert: m[1] })
  m = s.match(NEUAUSSCHREIBUNG)
  if (m) return t('common:verlauf.neuausschreibung', { id: m[1], titel: m[2], status: statusWert(m[3]), datum: m[4] })
  m = s.match(DUBLETTE)
  if (m) return t('common:verlauf.dublette', { id: m[1], titel: m[2], prozent: m[3], datum: m[4] })
  m = s.match(WERT_ZEILE)
  if (!m) return s
  const anzeige = (w: string) => (w === 'Ja' ? t('common:verlauf.ja') : w === 'Nein' ? t('common:verlauf.nein') : wertText(w))
  const label = t(`common:verlauf.label.${m[1]}`, { defaultValue: m[1] })
  return `${label}: ${anzeige(m[2])} → ${anzeige(m[3])}${m[4] ? ` ${t('common:verlauf.review')}` : ''}`
}

/** Anzeige einer Verlaufszeile. Auf Deutsch kommt sie unverändert zurück. */
export function verlaufZeile(eintrag: string, art: string, wertText: (w: string) => string = statusWert): string {
  if (art !== 'auto' || aktuelleSprache() === 'de') return eintrag
  return eintrag.split(' · ').map((s) => segment(s, wertText)).join(' · ')
}
