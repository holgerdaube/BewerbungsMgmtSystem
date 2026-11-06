import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type JobRow } from '../api'
import { ScoreBadge, STATUS_FARBEN } from '../components/ui'
import { useReviewCount } from '../context/ReviewCount'
import { t } from '../i18n'
import { wert } from '../i18n/werte'

const COLUMNS = ['Neu', 'Prüfen', 'Beworben', 'Interview', 'Angebot', 'Absage'] // i18n-ok: DB-Werte
// Spaltenpunkte aus der kanonischen Styleguide-Map (18.07.) — Kanban und Status-Balken
// sprechen dieselbe Farbsprache.
const COL_ACCENT: Record<string, string> =
  Object.fromEntries(COLUMNS.map((c) => [c, STATUS_FARBEN[c]?.bg || '#858F9C']))

export default function Pipeline() {
  const nav = useNavigate()
  const [jobs, setJobs] = useState<JobRow[]>([])
  const [dragId, setDragId] = useState<number | null>(null)
  const [over, setOver] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const { refresh } = useReviewCount()

  useEffect(() => { api<JobRow[]>('/jobs').then(setJobs).catch((e) => setErr(String(e))) }, [])

  const move = async (id: number, status: string) => {
    const job = jobs.find((j) => j.id === id)
    if (!job || job.status === status) return
    setJobs((js) => js.map((j) => (j.id === id ? { ...j, status } : j))) // optimistic
    try {
      await api(`/jobs/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) })
      refresh()
    } catch {
      api<JobRow[]>('/jobs').then(setJobs) // rollback
    }
  }

  if (err) return <div className="rounded-lg bg-rose-50 p-4 text-rose-700">{t('pipeline:fehler', { meldung: err })}</div>

  const archived = jobs.filter((j) => !COLUMNS.includes(j.status || '')).length

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">{t('common:nav.pipeline')}</h1>
        <p className="text-sm text-slate-500">{t('pipeline:untertitel', {
          anzahl: archived,
          stati: ['Keine Rückmeldung', 'Kein Match', 'Beirat abgelehnt', 'Nicht verfügbar', 'Geparkt'].map((s) => wert('status', s)).join(' / '), // i18n-ok: DB-Werte
        })}</p>
      </div>

      <div className="flex gap-3 overflow-x-auto pb-2">
        {COLUMNS.map((col) => {
          const items = jobs.filter((j) => (j.status || 'Neu') === col)
          return (
            <div
              key={col}
              onDragOver={(e) => { e.preventDefault(); setOver(col) }}
              onDragLeave={() => setOver((o) => (o === col ? null : o))}
              onDrop={(e) => { e.preventDefault(); if (dragId != null) move(dragId, col); setOver(null); setDragId(null) }}
              className={`flex w-72 shrink-0 flex-col rounded-xl border bg-slate-50 ${over === col ? 'border-brand-cyan ring-2 ring-brand-cyan/30' : 'border-slate-200'}`}
            >
              <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
                <span className="flex items-center gap-2 text-sm font-semibold text-brand-navy">
                  <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: COL_ACCENT[col] }} />{wert('status', col)}
                </span>
                <span className="rounded-full bg-white px-2 text-xs font-medium text-slate-500">{items.length}</span>
              </div>
              <div className="flex-1 space-y-2 overflow-y-auto p-2" style={{ maxHeight: '68vh' }}>
                {items.map((j) => (
                  <div
                    key={j.id}
                    draggable
                    onDragStart={() => setDragId(j.id)}
                    onDragEnd={() => setDragId(null)}
                    onClick={() => nav(`/jobs/${j.id}`)}
                    className="cursor-grab rounded-lg border border-slate-200 bg-white p-2.5 shadow-sm hover:border-brand-cyan active:cursor-grabbing"
                  >
                    <div className="flex items-start gap-2">
                      <ScoreBadge score={j.match_score} />
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium text-brand-navy">{j.company_name}</div>
                        <div className="line-clamp-2 text-xs text-slate-500">{j.title}</div>
                        <div className="mt-1 text-[11px] text-slate-400">{j.portal ? wert('portal', j.portal) : ''}{j.location ? ` · ${j.location}` : ''}</div>
                      </div>
                    </div>
                  </div>
                ))}
                {items.length === 0 && <div className="px-1 py-6 text-center text-xs text-slate-300">{t('pipeline:leer')}</div>}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
