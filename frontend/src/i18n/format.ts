import { aktuelleSprache } from './index'

// P2-88: Datum und Zahlen je Sprache. Bewusst dünn: Die Seiten nutzen verschiedene Darstellungen, deshalb
// bleiben die Optionen frei wählbar. Deutsch liefert dieselben Ausgaben wie vor der Umstellung.
const locale = () => (aktuelleSprache() === 'en' ? 'en-GB' : 'de-DE')

export const zahl = (n: number, optionen?: Intl.NumberFormatOptions): string => n.toLocaleString(locale(), optionen)

export const datumZeit = (wert: string | number | Date, optionen?: Intl.DateTimeFormatOptions): string =>
  new Date(wert).toLocaleString(locale(), optionen)

/** Reines Datum (`YYYY-MM-DD`) ohne `new Date()`-Umweg: `Date` deutet das ISO-Datum als UTC-Mitternacht, und
 *  `toLocaleDateString()` riskiert je nach Zeitzone eine Verschiebung um einen Tag. Leer → „–“, Unlesbares kommt
 *  unverändert zurück. */
export function datum(iso: string | null | undefined): string {
  if (!iso) return '–'
  const [j, m, t] = iso.split('-')
  if (!(j && m && t)) return iso
  return aktuelleSprache() === 'en' ? `${t}/${m}/${j}` : `${t}.${m}.${j}`
}
