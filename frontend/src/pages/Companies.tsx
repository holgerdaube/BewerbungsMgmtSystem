import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { Listensuche, passtZurSuche } from '../components/Listensuche'
import { CopyChip, SITU_COLORS, SITU_TEXT } from '../components/ui'
import { t } from '../i18n'
import { wert } from '../i18n/werte'

// Auslöser-Satz für den Skill (CopyChip kopiert ihn in die Claude-Session): bleibt deutsch.
const initiativPhrase = (name: string): string => t('common:ausloeser.initiativ', { name })

export default function Companies({ radar = false }: { radar?: boolean }) {
  const [comps, setComps] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [suche, setSuche] = useState('')
  const sichtbar = comps.filter((c) => passtZurSuche(c, suche, c.situation ? [wert('situation', c.situation)] : []))

  const load = () => {
    setLoading(true)
    api<any[]>(`/companies${radar ? '?radar=true' : ''}`).then(setComps).finally(() => setLoading(false))
  }

  useEffect(load, [radar])

  const remove = async (c: any) => {
    if (!window.confirm(t('companies:loeschen_frage', { name: c.name }))) return
    setErr(null)
    try {
      await api(`/companies/${c.id}`, { method: 'DELETE' })
      load()
    } catch (e: any) {
      // 409 = noch aktive Stellen an der Firma — verständliche Meldung statt "409 Conflict".
      setErr(e instanceof ApiError ? e.message : (e?.message || t('companies:loeschen_fehlgeschlagen')))
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">{radar ? t('common:nav.radar') : t('common:nav.companies')}</h1>
        <p className="text-sm text-slate-500">
          {t(radar ? 'companies:anzahl_radar' : 'companies:anzahl', { count: comps.length })}
        </p>
      </div>

      <Listensuche wert={suche} onChange={setSuche} treffer={sichtbar.length} gesamt={comps.length} />

      {err && <div className="rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{err}</div>}

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">{t('companies:spalte.firma')}</th>
              <th className="px-3 py-2">{t('companies:spalte.situation')}</th>
              {radar ? (
                <>
                  <th className="px-3 py-2">{t('companies:spalte.signal')}</th>
                  <th className="px-3 py-2">{t('companies:spalte.rebuild_abbau')}</th>
                  <th className="px-3 py-2">{t('companies:spalte.rolle_offen')}</th>
                  <th className="px-3 py-2"></th>
                </>
              ) : (
                <>
                  <th className="px-3 py-2">{t('companies:spalte.branche')}</th>
                  <th className="px-3 py-2">{t('companies:spalte.region')}</th>
                </>
              )}
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr><td colSpan={radar ? 7 : 5} className="px-3 py-8 text-center text-slate-400">{t('companies:lade')}</td></tr>
            ) : suche.trim() && sichtbar.length === 0 ? (
              <tr><td colSpan={radar ? 7 : 5} className="px-3 py-8 text-center text-slate-400">{t('common:listensuche.keine')}</td></tr>
            ) : (
              sichtbar.map((c) => (
                <tr key={c.id} className="align-top hover:bg-brand-cyan/5">
                  <td className="px-3 py-2 font-medium text-brand-navy">{c.name}</td>
                  <td className="px-3 py-2">
                    {c.situation && (
                      <span
                        className="rounded-full px-2 py-0.5 text-xs font-medium"
                        style={{
                          backgroundColor: SITU_COLORS[c.situation] || SITU_COLORS.UNKLAR,
                          color: SITU_TEXT[c.situation] || SITU_TEXT.UNKLAR,
                        }}
                      >
                        {wert('situation', c.situation)}
                      </span>
                    )}
                  </td>
                  {radar ? (
                    <>
                      <td className="px-3 py-2 text-slate-600">{c.restructuring_signal}</td>
                      <td className="px-3 py-2 text-slate-500">{c.rebuild_or_cut}</td>
                      <td className="px-3 py-2 text-slate-500">{c.radar_role_open}</td>
                      <td className="px-3 py-2"><CopyChip phrase={initiativPhrase(c.name)} /></td>
                    </>
                  ) : (
                    <>
                      <td className="px-3 py-2 text-slate-500">{c.industry || '–'}</td>
                      <td className="px-3 py-2 text-slate-500">{c.region || '–'}</td>
                    </>
                  )}
                  <td className="px-3 py-2 text-right">
                    <button onClick={() => remove(c)} className="text-slate-400 hover:text-rose-600" title={t('companies:loeschen_titel')}>🗑</button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
