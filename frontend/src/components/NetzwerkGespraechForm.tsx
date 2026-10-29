import { useEffect, useState } from 'react'
import { api } from '../api'
import { isoTag } from '../zeit'

// Phase 69 (Stufe B) — Gesamtprozess-KPI "Gespräche gesamt": Netzwerk-Calls und
// Headhunter-Gespräche OHNE Stelle (Interview verlangt zwingend eine job_id) über
// /api/netzwerk-gespraeche erfassen. Gemeinsame Komponente für Outreach.tsx (outreachId) UND
// Netzwerk.tsx/HeadhunterEdit (headhunterId) — Button „🎙 Gespräch erfassen" + Liste, s. Spec.
const GESPRAECH_GEGENUEBER = ['Netzwerk', 'Recruiter', 'Hiring Manager', 'Fachbereich', 'Headhunter', 'Sonstige']
const inputCls = 'rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none'

function heute(): string {
  return isoTag()
}

export default function NetzwerkGespraechForm({ outreachId, headhunterId, defaultUnternehmen, defaultPerson }: {
  outreachId?: number; headhunterId?: number; defaultUnternehmen?: string; defaultPerson?: string
}) {
  const [items, setItems] = useState<any[]>([])
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [f, setF] = useState<any>({ datum: heute(), person: defaultPerson || '', gegenueber: '', vor_ort: false, notiz: '' })

  const query = outreachId != null ? `outreach_id=${outreachId}` : headhunterId != null ? `headhunter_id=${headhunterId}` : null
  const load = () => {
    if (!query) return
    api<any[]>(`/netzwerk-gespraeche?${query}`).then(setItems).catch(() => setItems([]))
  }
  useEffect(() => { load() }, [outreachId, headhunterId])

  const save = async () => {
    if (!f.datum) { setErr('Datum ist Pflicht'); return }
    setSaving(true); setErr(null)
    try {
      await api('/netzwerk-gespraeche', {
        method: 'POST',
        body: JSON.stringify({
          datum: f.datum, person: f.person || null, unternehmen: defaultUnternehmen || null,
          gegenueber: f.gegenueber || null, vor_ort: f.vor_ort,
          outreach_id: outreachId ?? null, headhunter_id: headhunterId ?? null,
          notiz: f.notiz || null,
        }),
      })
      setF({ datum: heute(), person: defaultPerson || '', gegenueber: '', vor_ort: false, notiz: '' })
      setShowForm(false)
      await load()
    } catch (e: any) { setErr(e?.message || 'Anlegen fehlgeschlagen') }
    finally { setSaving(false) }
  }

  const remove = async (gid: number) => {
    if (!window.confirm('Dieses Gespräch wirklich löschen?')) return
    await api(`/netzwerk-gespraeche/${gid}`, { method: 'DELETE' })
    await load()
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Gespräche ({items.length})</div>
        {!showForm && (
          <button onClick={() => setShowForm(true)} className="text-xs font-medium text-brand-cyan hover:underline">🎙 Gespräch erfassen</button>
        )}
      </div>

      {items.length > 0 && (
        <div className="space-y-1">
          {items.map((g) => (
            <div key={g.id} className="flex items-start justify-between gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs">
              <div>
                <span className="whitespace-nowrap tabular-nums text-slate-500">{g.datum}</span>
                {g.person && <span className="ml-2 font-medium text-brand-navy">{g.person}</span>}
                {g.gegenueber && <span className="ml-2 rounded-full bg-slate-100 px-1.5 py-0.5 text-slate-600">{g.gegenueber}</span>}
                {g.vor_ort && <span className="ml-1 text-slate-400" title="Persönlich vor Ort">📍</span>}
                {g.notiz && <div className="mt-0.5 text-slate-500">{g.notiz}</div>}
              </div>
              <button onClick={() => remove(g.id)} className="shrink-0 text-slate-400 hover:text-rose-600" title="Löschen">✕</button>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <div className="space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-2.5">
          <div className="flex gap-2">
            <input type="date" className={inputCls} value={f.datum} onChange={(e) => setF({ ...f, datum: e.target.value })} />
            <input className={`${inputCls} flex-1`} placeholder="Person" value={f.person} onChange={(e) => setF({ ...f, person: e.target.value })} />
          </div>
          <div className="flex items-center gap-2">
            <select className={`${inputCls} flex-1`} value={f.gegenueber} onChange={(e) => setF({ ...f, gegenueber: e.target.value })}>
              <option value="">Gegenüber…</option>
              {GESPRAECH_GEGENUEBER.map((g) => <option key={g} value={g}>{g}</option>)}
            </select>
            <label className="flex items-center gap-1.5 whitespace-nowrap text-sm text-slate-600">
              <input type="checkbox" checked={f.vor_ort} onChange={(e) => setF({ ...f, vor_ort: e.target.checked })} />
              vor Ort
            </label>
          </div>
          <textarea className={`${inputCls} w-full`} rows={2} placeholder="Notiz…" value={f.notiz} onChange={(e) => setF({ ...f, notiz: e.target.value })} />
          <div className="flex items-center gap-2">
            <button onClick={save} disabled={saving} className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:opacity-40">{saving ? 'Anlegen…' : 'Anlegen'}</button>
            <button onClick={() => setShowForm(false)} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">Abbrechen</button>
            {err && <span className="text-sm text-rose-600">{err}</span>}
          </div>
        </div>
      )}
    </div>
  )
}
