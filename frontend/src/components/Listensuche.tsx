import { t } from '../i18n'
import { zahl } from '../i18n/format'

const ohneAkzente = (text: string): string => text.normalize('NFD').replace(/\p{M}/gu, '').replace(/ß/g, 'ss').toLowerCase()
const mitUmschrift = (text: string): string =>
  ohneAkzente(text.toLowerCase().replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue'))

/** Passt die Zeile zur Eingabe? Jedes Wort muss in einem der Textfelder vorkommen. Groß- und Kleinschreibung und Akzente
 *  zählen nicht, „grün“, „grun“ und „gruen“ finden alle „Grünwald“. `zusatz` nimmt angezeigte Werte auf, die anders in der
 *  Datenbank stehen. */
export function passtZurSuche(zeile: Record<string, unknown>, suche: string, zusatz: string[] = []): boolean {
  const woerter = suche.split(/\s+/).filter(Boolean)
  if (!woerter.length) return true
  const texte = Object.values(zeile).filter((w): w is string => typeof w === 'string')
  const alles = [...texte, ...zusatz].join(' ')
  const einfach = ohneAkzente(alles)
  const umschrift = mitUmschrift(alles)
  return woerter.every((w) => einfach.includes(ohneAkzente(w)) || umschrift.includes(mitUmschrift(w)))
}

/** Suchfeld über einer Liste. Es grenzt sofort beim Tippen ein, die Seite filtert die Zeilen selbst. */
export function Listensuche({ wert, onChange, treffer, gesamt }: {
  wert: string; onChange: (wert: string) => void; treffer: number; gesamt: number
}) {
  return (
    <div className="flex items-center gap-3">
      <input
        type="search"
        value={wert}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t('common:listensuche.platzhalter')}
        aria-label={t('common:listensuche.platzhalter')}
        className="w-full max-w-md rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm focus:border-brand-cyan focus:outline-none"
      />
      {wert.trim() && (
        <span className="whitespace-nowrap text-sm text-slate-500">
          {t('common:listensuche.treffer', { treffer: zahl(treffer), gesamt: zahl(gesamt) })}
        </span>
      )}
    </div>
  )
}
