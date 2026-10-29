import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { CopyChip, SITU_COLORS, SITU_TEXT } from '../components/ui'

export default function Companies({ radar = false }: { radar?: boolean }) {
  const [comps, setComps] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    api<any[]>(`/companies${radar ? '?radar=true' : ''}`).then(setComps).finally(() => setLoading(false))
  }

  useEffect(load, [radar])

  const remove = async (c: any) => {
    if (!window.confirm(`„${c.name}" wirklich löschen? (Contacts der Firma werden mitgelöscht, die Company-Fit-Datei wandert in den Papierkorb.)`)) return
    setErr(null)
    try {
      await api(`/companies/${c.id}`, { method: 'DELETE' })
      load()
    } catch (e: any) {
      // 409 = noch aktive Stellen an der Firma — verständliche Meldung statt "409 Conflict".
      setErr(e instanceof ApiError ? e.message : (e?.message || 'Löschen fehlgeschlagen'))
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">{radar ? 'Restructuring-Radar' : 'Firmen'}</h1>
        <p className="text-sm text-slate-500">
          {comps.length} {radar ? 'Firmen mit Umbau-/Layoff-Signal' : 'Firmen in der Datenbank'}
        </p>
      </div>

      {err && <div className="rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{err}</div>}

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Firma</th>
              <th className="px-3 py-2">Situation</th>
              {radar ? (
                <>
                  <th className="px-3 py-2">Signal</th>
                  <th className="px-3 py-2">Rebuild/Abbau</th>
                  <th className="px-3 py-2">Rolle offen?</th>
                  <th className="px-3 py-2"></th>
                </>
              ) : (
                <>
                  <th className="px-3 py-2">Branche</th>
                  <th className="px-3 py-2">Region</th>
                </>
              )}
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr><td colSpan={radar ? 7 : 5} className="px-3 py-8 text-center text-slate-400">Lade…</td></tr>
            ) : (
              comps.map((c) => (
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
                        {c.situation}
                      </span>
                    )}
                  </td>
                  {radar ? (
                    <>
                      <td className="px-3 py-2 text-slate-600">{c.restructuring_signal}</td>
                      <td className="px-3 py-2 text-slate-500">{c.rebuild_or_cut}</td>
                      <td className="px-3 py-2 text-slate-500">{c.radar_role_open}</td>
                      <td className="px-3 py-2"><CopyChip phrase={`Initiativbewerbung für ${c.name}`} /></td>
                    </>
                  ) : (
                    <>
                      <td className="px-3 py-2 text-slate-500">{c.industry || '–'}</td>
                      <td className="px-3 py-2 text-slate-500">{c.region || '–'}</td>
                    </>
                  )}
                  <td className="px-3 py-2 text-right">
                    <button onClick={() => remove(c)} className="text-slate-400 hover:text-rose-600" title="Firma löschen">🗑</button>
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
