import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import NetzwerkGespraechForm from '../components/NetzwerkGespraechForm'
import { isoTag } from '../zeit'
import { t } from '../i18n'
import { datumZeit } from '../i18n/format'
import { verlaufZeile } from '../i18n/verlauf'

const STATUSES = ['Initiated', 'Responded', 'In Dialogue', 'Meeting Scheduled', 'Opportunity', 'On Hold', 'Closed Positive', 'Closed Negative']
const STATUS_STYLE: Record<string, string> = {
  Initiated: 'bg-slate-100 text-slate-600', Responded: 'bg-sky-100 text-sky-800',
  'In Dialogue': 'bg-indigo-100 text-indigo-800', 'Meeting Scheduled': 'bg-violet-100 text-violet-800',
  Opportunity: 'bg-emerald-100 text-emerald-800', 'On Hold': 'bg-amber-100 text-amber-800',
  'Closed Positive': 'bg-green-100 text-green-800', 'Closed Negative': 'bg-rose-100 text-rose-700',
}
// Sichtbarer Name eines Outreach-Status bzw. Log-Typs; der DB-Wert (englisch bzw. `auto`/`manuell`) bleibt der Wert.
const wertText = (s: string) => t(`outreach:wert.${s}`, { defaultValue: s })
const inputCls = 'rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none'

function logTime(iso: string) {
  // P2-20: Die API kennzeichnet ihre Zeitstempel seit 28.08.2026 als UTC (`app/zeit.py`),
  // das Anhaengen von 'Z' ist damit ueberfluessig geworden.
  const d = new Date(iso)
  return datumZeit(d, { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })
}

/** Aufgeklappte Zeile: nächster Schritt + Fälligkeit bearbeiten, Aktivitäten-Log führen. */
function Detail({ item, onSaved }: { item: any; onSaved: () => void }) {
  const [step, setStep] = useState(item.next_step || '')
  const [due, setDue] = useState(item.next_action_datum || '')
  // Phase 69 (Stufe B) — Netzwerk-Bewerbung: NUR setzen, wenn zur selben Bewerbung KEINE
  // Application-Row existiert (Pflege-Regel, s. Tooltip unten + gesamtprozess.py-Docstring).
  const [beworbenAm, setBeworbenAm] = useState(item.bewerbung_datum || '')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [log, setLog] = useState<any[]>([])
  const [neu, setNeu] = useState('')

  const loadLog = () => api<any[]>(`/outreach/${item.id}/log`).then(setLog).catch(() => {})
  useEffect(() => { loadLog() }, [item.id])

  const dirty = step !== (item.next_step || '') || due !== (item.next_action_datum || '')
    || beworbenAm !== (item.bewerbung_datum || '')
  const save = async () => {
    setSaving(true)
    await api(`/outreach/${item.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ next_step: step || null, next_action_datum: due || null, bewerbung_datum: beworbenAm || null }),
    })
    await loadLog()
    onSaved()
    setSaving(false)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }
  const addLog = async () => {
    if (!neu.trim()) return
    await api(`/outreach/${item.id}/log`, { method: 'POST', body: JSON.stringify({ eintrag: neu.trim() }) })
    setNeu('')
    await loadLog()
  }

  return (
    <div className="grid grid-cols-1 gap-4 bg-slate-50/70 px-4 py-4 lg:grid-cols-2">
      <div>
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{t('outreach:detail.aktion_bearbeiten')}</div>
        <div className="space-y-2">
          <input className={`${inputCls} w-full`} value={step} placeholder={t('outreach:detail.naechster_schritt_platzhalter')}
                 onChange={(e) => setStep(e.target.value)} />
          <div className="flex items-center gap-2">
            <input type="date" className={inputCls} value={due} onChange={(e) => setDue(e.target.value)} />
            {due && <button onClick={() => setDue('')} className="text-xs text-slate-400 hover:text-slate-600">{t('outreach:detail.datum_loeschen')}</button>}
          </div>
          <label className="flex flex-col text-xs text-slate-500">
            <span title={t('outreach:detail.beworben_am_hinweis')}>
              {t('outreach:detail.beworben_am')}
            </span>
            <div className="mt-1 flex items-center gap-2">
              <input type="date" className={inputCls} value={beworbenAm} onChange={(e) => setBeworbenAm(e.target.value)}
                     title={t('outreach:detail.beworben_am_titel')} />
              {beworbenAm && <button onClick={() => setBeworbenAm('')} className="text-xs text-slate-400 hover:text-slate-600">{t('outreach:detail.datum_loeschen')}</button>}
            </div>
          </label>
          <div className="flex items-center gap-2">
            <button onClick={save} disabled={saving || !dirty}
                    className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
              {saving ? t('outreach:detail.speichern_laeuft') : t('outreach:detail.speichern')}
            </button>
            {saved && <span className="text-sm text-emerald-600">{t('outreach:detail.gespeichert')}</span>}
          </div>
          {(item.notizen || item.template) && (
            <div className="mt-2 rounded-lg border border-slate-200 bg-white p-2.5 text-xs text-slate-500">
              {item.template && <div><span className="text-slate-400">{t('outreach:detail.template')}</span> {item.template}</div>}
              {item.notizen && <div className="mt-1 whitespace-pre-wrap"><span className="text-slate-400">{t('outreach:detail.notizen')}</span> {item.notizen}</div>}
            </div>
          )}
        </div>
      </div>
      <div>
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{t('outreach:detail.log_titel', { anzahl: log.length })}</div>
        <div className="mb-2 flex gap-2">
          <input className={`${inputCls} flex-1`} value={neu} placeholder={t('outreach:detail.log_platzhalter')}
                 onChange={(e) => setNeu(e.target.value)}
                 onKeyDown={(e) => { if (e.key === 'Enter') addLog() }} />
          <button onClick={addLog} disabled={!neu.trim()}
                  className="rounded-lg border border-brand-cyan/40 px-3 py-1.5 text-sm font-medium text-brand-navy hover:bg-brand-cyan/10 disabled:opacity-40">
            {t('outreach:detail.eintrag')}
          </button>
        </div>
        {log.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-200 p-3 text-center text-xs text-slate-400">
            {t('outreach:detail.log_leer')}
          </div>
        ) : (
          <div className="max-h-56 space-y-1.5 overflow-y-auto pr-1">
            {log.map((l) => (
              <div key={l.id} className="flex items-start gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs">
                <span className="whitespace-nowrap tabular-nums text-slate-400">{logTime(l.created_at)}</span>
                <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${l.art === 'auto' ? 'bg-slate-100 text-slate-500' : 'bg-brand-cyan/15 text-brand-navy'}`}>{wertText(l.art)}</span>
                <span className="text-slate-700">{verlaufZeile(l.eintrag, l.art, wertText)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="lg:col-span-2">
        <NetzwerkGespraechForm outreachId={item.id} defaultUnternehmen={item.unternehmen} defaultPerson={item.kontakt} />
      </div>
    </div>
  )
}

export default function Outreach() {
  const [sp, setSp] = useSearchParams()
  const [items, setItems] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [open, setOpen] = useState<number | null>(null)
  const overdueOnly = sp.get('filter') === 'overdue'
  const today = isoTag()

  const load = () => api<any[]>('/outreach').then(setItems).finally(() => setLoading(false))
  useEffect(() => { load() }, [])

  const setStatus = async (id: number, status: string) => {
    setItems((xs) => xs.map((x) => (x.id === id ? { ...x, status } : x)))
    await api(`/outreach/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) })
  }

  const isOverdue = (x: any) => x.next_action_datum && x.next_action_datum < today

  const stats = useMemo(() => {
    const total = items.length
    const antworten = items.filter((x) => (x.antwort || '').toLowerCase() === 'ja').length
    const rate = total ? Math.round((antworten / total) * 1000) / 10 : 0
    const overdue = items.filter(isOverdue).length
    return { total, antworten, rate, overdue }
  }, [items])

  const rows = items
    .filter((x) => (filter ? x.status === filter : true))
    .filter((x) => (overdueOnly ? isOverdue(x) : true))

  const toggleOverdue = () => {
    const next = new URLSearchParams(sp)
    if (overdueOnly) next.delete('filter')
    else next.set('filter', 'overdue')
    setSp(next, { replace: true })
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-brand-navy">{t('outreach:titel')}</h1>
          {/* P2-61: „Gespiegelt“ stimmte nicht mehr. Die Zeilen kamen einmal per Import, seitdem
              gleicht nichts mit der Tabelle ab; der Knopf rechts schreibt nur auf Wunsch zurück. */}
          <p className="text-sm text-slate-500">{t('outreach:untertitel')}</p>
        </div>
        <a href="/api/export/outreach" className="rounded-lg bg-brand-cyan px-3 py-2 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover">
          {t('outreach:export')}
        </a>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="text-xs uppercase tracking-wide text-slate-500">{t('outreach:kachel.kontakte')}</div><div className="mt-1 text-3xl font-bold text-brand-navy">{stats.total}</div></div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="text-xs uppercase tracking-wide text-slate-500">{t('outreach:kachel.antworten')}</div><div className="mt-1 text-3xl font-bold text-brand-navy">{stats.antworten}</div></div>
        <div className="rounded-xl border border-brand-cyan/40 bg-white p-4 shadow-sm"><div className="text-xs uppercase tracking-wide text-slate-500">{t('outreach:kachel.response_rate')}</div><div className="mt-1 text-3xl font-bold text-brand-cyan">{stats.rate}%</div></div>
        <button onClick={toggleOverdue}
                className={`group rounded-xl border p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md ${
                  overdueOnly ? 'border-rose-400 bg-rose-50 ring-2 ring-rose-200' : stats.overdue ? 'border-rose-300 bg-white hover:border-rose-400' : 'border-slate-200 bg-white'}`}>
          <div className="flex items-center justify-between">
            <div className="text-xs uppercase tracking-wide text-slate-500">{t('outreach:kachel.ueberfaellig')}</div>
            <span className="text-slate-300 transition group-hover:text-rose-400">{overdueOnly ? '✕' : '→'}</span>
          </div>
          <div className={`mt-1 text-3xl font-bold ${stats.overdue ? 'text-rose-600' : 'text-brand-navy'}`}>{stats.overdue}</div>
          <div className="mt-1 text-xs text-slate-400">{overdueOnly ? t('outreach:kachel.filter_aktiv') : t('outreach:kachel.filter_hinweis')}</div>
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <select value={filter} onChange={(e) => setFilter(e.target.value)} className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm">
          <option value="">{t('outreach:alle_status', { anzahl: items.length })}</option>
          {STATUSES.map((s) => <option key={s} value={s}>{wertText(s)} ({items.filter((x) => x.status === s).length})</option>)}
        </select>
        {overdueOnly && (
          <span className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-2.5 py-1 text-xs font-medium text-rose-700">
            {t('outreach:chip_ueberfaellig')}
            <button onClick={toggleOverdue} className="text-rose-500 hover:text-rose-700">✕</button>
          </span>
        )}
        <span className="ml-auto text-xs text-slate-400">{t('outreach:eintraege', { count: rows.length })}</span>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="w-8 px-3 py-2"></th>
              <th className="px-3 py-2">{t('outreach:spalte.datum')}</th><th className="px-3 py-2">{t('outreach:spalte.kontakt')}</th><th className="px-3 py-2">{t('outreach:spalte.unternehmen')}</th>
              <th className="px-3 py-2">{t('outreach:spalte.position')}</th><th className="px-3 py-2">{t('outreach:spalte.kanal')}</th><th className="px-3 py-2">{t('outreach:spalte.status')}</th>
              <th className="px-3 py-2">{t('outreach:spalte.naechster_schritt')}</th><th className="px-3 py-2">{t('outreach:spalte.next_action')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr><td colSpan={9} className="px-3 py-8 text-center text-slate-400">{t('outreach:lade')}</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={9} className="px-3 py-8 text-center text-slate-400">{overdueOnly ? t('outreach:keine_eintraege_nichts_ueberfaellig') : t('outreach:keine_eintraege')}</td></tr>
            ) : rows.map((x) => {
              const overdue = isOverdue(x)
              const isOpen = open === x.id
              return (
                <>
                  <tr key={x.id} onClick={() => setOpen(isOpen ? null : x.id)}
                      className={`cursor-pointer align-top hover:bg-brand-cyan/5 ${isOpen ? 'bg-brand-cyan/5' : ''}`}>
                    <td className="px-3 py-2 text-slate-400">{isOpen ? '▾' : '▸'}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-slate-500">{x.datum || '–'}</td>
                    <td className="px-3 py-2 font-medium text-brand-navy">{x.kontakt || '–'}</td>
                    <td className="px-3 py-2 text-slate-700">{x.unternehmen}</td>
                    <td className="px-3 py-2 text-slate-500">{x.position}</td>
                    <td className="px-3 py-2 text-slate-500">{x.kanal}</td>
                    <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                      <select value={x.status || ''} onChange={(e) => setStatus(x.id, e.target.value)}
                              className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[x.status] || 'bg-slate-100'}`}>
                        {STATUSES.map((s) => <option key={s} value={s}>{wertText(s)}</option>)}
                      </select>
                    </td>
                    <td className="max-w-xs px-3 py-2 text-slate-600">{x.next_step}</td>
                    <td className={`whitespace-nowrap px-3 py-2 ${overdue ? 'font-semibold text-rose-600' : 'text-slate-500'}`}>{x.next_action_datum || '–'}</td>
                  </tr>
                  {isOpen && (
                    <tr key={`${x.id}-detail`}>
                      <td colSpan={9} className="p-0"><Detail item={x} onSaved={load} /></td>
                    </tr>
                  )}
                </>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
