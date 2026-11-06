import { useState } from 'react'
import { aktuelleSprache, t } from '../i18n'
import { spracheWechseln } from '../i18n/sprache'

const SPRACHEN = ['de', 'en']

/** `DE | EN`. Keine Fahnen: Eine Sprache ist kein Land. Nach dem Wechsel lädt die Seite neu. */
export default function SpracheUmschalter({ dunkel = false }: { dunkel?: boolean }) {
  const [fehler, setFehler] = useState(false)
  const aktiv = aktuelleSprache()
  const wechseln = (s: string) => {
    if (s === aktiv) return
    setFehler(false)
    spracheWechseln(s).catch(() => setFehler(true))
  }
  const ruhe = dunkel ? 'text-slate-300 hover:bg-white/10' : 'text-slate-600 hover:bg-slate-100'
  return (
    <div>
      <div role="group" aria-label={t('common:sprache.umschalter')} className={`inline-flex overflow-hidden rounded-lg border ${dunkel ? 'border-white/20' : 'border-slate-300'}`}>
        {SPRACHEN.map((s) => (
          <button key={s} type="button" aria-pressed={s === aktiv} onClick={() => wechseln(s)}
            className={`px-2.5 py-1 text-xs font-semibold uppercase transition ${s === aktiv ? 'bg-brand-cyan text-brand-navy' : ruhe}`}>
            {s}
          </button>
        ))}
      </div>
      {fehler && <div role="alert" className={`mt-1 text-xs ${dunkel ? 'text-rose-300' : 'text-rose-600'}`}>{t('common:sprache.fehler')}</div>}
    </div>
  )
}

/** Karte in den Einstellungen, dieselbe Einstellung wie der Umschalter in der Seitenleiste. */
export function SpracheKarte() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 text-sm font-semibold text-brand-navy">{t('common:sprache.karte_titel')}</div>
      <p className="mb-3 text-xs text-slate-500">{t('common:sprache.karte_text')}</p>
      <SpracheUmschalter />
    </div>
  )
}
