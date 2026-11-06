import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type AgentStatus, type AgentTaskRow } from '../api'
import { codexZeile, laufKosten, tokenText, useKiAnbieter } from '../components/ui'
import { t } from '../i18n'
import { datumZeit, zahl } from '../i18n/format'

const ACTIVE = ['queued', 'running']
const LISTE_MAX = 100
type TaskSummen = { gesamt: number; fehlgeschlagen: number; kosten_usd: number; token: number }
const CHIP: Record<string, string> = {
  queued: 'bg-slate-100 text-slate-600', running: 'bg-indigo-100 text-indigo-800',
  done: 'bg-emerald-100 text-emerald-800', failed: 'bg-rose-100 text-rose-700',
  cancelled: 'bg-slate-100 text-slate-500',
}
const FILTERS = [
  { id: 'alle' },
  { id: 'aktiv' },
  { id: 'failed' },
] as const

function pretty(line: string): string | null {
  try {
    const ev = JSON.parse(line)
    if (ev.type === 'system') {
      // stream-json kennt mehrere system-Subtypen — nur `init` ist der Lauf-Start mit Tool-Liste.
      // (Bug bis 11.07.: JEDE system-Zeile wurde als „Lauf gestartet (0 Tools)" gerendert.)
      if (ev.subtype === 'init') return t('tasks:log.lauf_gestartet', { anzahl: (ev.tools || []).length })
      if (ev.subtype === 'task_started') return t('tasks:log.subagent', { text: String(ev.description || t('common:ui.subagent_gestartet')).slice(0, 140) })
      if (ev.subtype === 'task_notification' && ev.summary) return t('tasks:log.subagent_fertig', { text: String(ev.summary).slice(0, 140) })
      return null // task_progress/thinking_tokens etc. — Rauschen, nicht anzeigen
    }
    if (ev.type === 'assistant') {
      const parts = ev.message?.content || []
      const tools = parts.filter((p: any) => p.type === 'tool_use').map((p: any) => p.name)
      if (tools.length) return `🔧 ${tools.join(', ')}`
      const text = parts.filter((p: any) => p.type === 'text').map((p: any) => p.text).join(' ').trim()
      return text ? `💬 ${text.slice(0, 160)}` : null
    }
    if (ev.type === 'result') return `${ev.is_error ? '✗' : '✓'} ${String(ev.result || '').slice(0, 200)}`
    return codexZeile(ev) ?? null   // ChatGPT: das JSONL von `codex exec` (P2-86)
  } catch {
    return line.trim() ? line.slice(0, 160) : null
  }
}

function zeit(iso: string | null) {
  if (!iso) return '—'
  // P2-20 (28.08.2026): Das hier hing frueher ein 'Z' von Hand an, weil die API ihre
  // Zeitstempel ohne Zeitzone lieferte — diese Seite war die einzige, die den Fehler
  // kompensierte, ueberall sonst standen die Zeiten zwei Stunden zu frueh. Seit die API
  // UTC kennzeichnet (`app/zeit.py`), waere das Anhaengen sogar schaedlich: aus
  // '...+00:00' wuerde '...+00:00Z' und damit ein ungueltiges Datum.
  return datumZeit(iso, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export default function Tasks() {
  const { anbieter } = useKiAnbieter()
  const chatgpt = anbieter === 'chatgpt'
  const [tasks, setTasks] = useState<AgentTaskRow[] | null>(null)
  const [budget, setBudget] = useState<AgentStatus | null>(null)
  const [filter, setFilter] = useState<typeof FILTERS[number]['id']>('alle')
  const [fehlgeschlagene, setFehlgeschlagene] = useState<AgentTaskRow[] | null>(null)
  const [summen, setSummen] = useState<TaskSummen | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  const [log, setLog] = useState<string[]>([])

  const load = () => {
    api<AgentTaskRow[]>(`/tasks?limit=${LISTE_MAX}`).then(setTasks).catch(() => {})
    api<AgentTaskRow[]>(`/tasks?status=failed&limit=${LISTE_MAX}`).then(setFehlgeschlagene).catch(() => {})
    api<TaskSummen>('/tasks/summen').then(setSummen).catch(() => {})
    api<AgentStatus>('/agent-status').then(setBudget).catch(() => {})
  }
  useEffect(() => { load() }, [])

  // Solange etwas läuft: alle 3 s aktualisieren
  const aktiv = (tasks || []).filter((t) => ACTIVE.includes(t.status)).length
  useEffect(() => {
    if (!aktiv) return
    const iv = setInterval(load, 3000)
    return () => clearInterval(iv)
  }, [aktiv])

  useEffect(() => {
    if (open == null) { setLog([]); return }
    const fetchLog = () => api<AgentTaskRow>(`/tasks/${open}?tail=300`).then((t) => setLog(t.log || [])).catch(() => {})
    fetchLog()
    const iv = setInterval(fetchLog, 3000)
    return () => clearInterval(iv)
  }, [open])

  // Die Kacheln zählen alle Läufe (Server), die Liste zeigt nur die letzten. Bis die Summen da sind, gilt die Liste.
  const stats = useMemo(() => {
    const all = tasks || []
    return {
      gesamt: summen?.gesamt ?? all.length,
      aktiv,
      fehler: summen?.fehlgeschlagen ?? all.filter((t) => t.status === 'failed').length,
      kosten: summen?.kosten_usd ?? all.reduce((s, t) => s + (t.cost_usd || 0), 0),
      token: summen?.token ?? all.reduce((s, t) => s + (t.tokens || 0), 0),
    }
  }, [tasks, aktiv, summen])

  if (!tasks) return <div className="text-slate-400">{t('tasks:lade')}</div>

  const rows = filter === 'alle' ? tasks
    : filter === 'aktiv' ? tasks.filter((t) => ACTIVE.includes(t.status))
    : fehlgeschlagene ?? tasks.filter((t) => t.status === 'failed')
  const rowsGesamt = filter === 'alle' ? stats.gesamt : filter === 'aktiv' ? rows.length : stats.fehler

  const cancel = async (id: number) => {
    await api(`/tasks/${id}/cancel`, { method: 'POST' }).catch(() => {})
    load()
  }
  const rerun = async (lauf: AgentTaskRow) => {
    try {
      await api('/tasks', {
        method: 'POST',
        body: JSON.stringify(lauf.job_id ? { kind: lauf.kind, job_id: lauf.job_id } : { kind: lauf.kind }),
      })
      load()
    } catch (e: any) { alert(e?.message || t('tasks:neustart_fehler')) }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">{t('tasks:titel')}</h1>
        <p className="text-sm text-slate-500">
          {t('tasks:kopf.untertitel')}
          {budget && (chatgpt
            // ChatGPT (P2-86): Es gibt weder USD-Kosten noch eine Budgetgrenze je Lauf, begrenzt wird
            // durch Zeitlimit, Abo-Grenzen und die Zahl der Läufe am Tag.
            ? <> · {t('tasks:kopf.parallel', { anzahl: budget.max_parallel })} · {t('tasks:kopf.laeufe_tag', { anzahl: budget.max_tasks })} · {t('tasks:kopf.zeitlimit')}</>
            : <> · {t('tasks:kopf.parallel', { anzahl: budget.max_parallel })}
              {budget.per_run_budget != null && <> · {t('tasks:kopf.notbremse', { betrag: budget.per_run_budget.toFixed(2) })}</>}
              {' '}· {t('tasks:kopf.tagesbudget', { betrag: budget.daily_budget.toFixed(2), laeufe: budget.max_tasks })}</>)}
        </p>
        {budget?.warnung && (
          <p className="mt-1 text-xs text-amber-600">⚠ {budget.warnung}</p>
        )}
      </div>

      {/* Spalten nach verfügbarer Breite statt nach Fensterbreite: Die Seitenleiste nimmt Platz weg, und Beträge wie $4384.61 brauchen mehr als eine Fünftelspalte bei 1024 px. */}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(12rem,1fr))] gap-4">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="text-xs uppercase tracking-wide text-slate-500">{t('tasks:stat.gesamt')}</div><div className="mt-1 text-3xl font-bold text-brand-navy">{zahl(stats.gesamt)}</div></div>
        <div className="rounded-xl border border-indigo-200 bg-white p-4 shadow-sm"><div className="text-xs uppercase tracking-wide text-slate-500">{t('tasks:stat.aktiv')}</div><div className={`mt-1 text-3xl font-bold ${stats.aktiv ? 'text-indigo-700' : 'text-brand-navy'}`}>{stats.aktiv}</div></div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="text-xs uppercase tracking-wide text-slate-500">{t('tasks:stat.fehlgeschlagen')}</div><div className={`mt-1 text-3xl font-bold ${stats.fehler ? 'text-rose-600' : 'text-brand-navy'}`}>{stats.fehler}</div></div>
        {budget && (() => {
          // ChatGPT (P2-86): Dollar gibt es nicht, die Kachel zählt die Läufe gegen die Tagesgrenze.
          const anteil = chatgpt
            ? (budget.max_tasks ? budget.tasks_today / budget.max_tasks : 0)
            : (budget.daily_budget ? budget.spent_today / budget.daily_budget : 0)
          const knapp = anteil >= 0.8
          return (
            <div className={`rounded-xl border bg-white p-4 shadow-sm ${knapp ? 'border-amber-300' : 'border-slate-200'}`}
              title={t('tasks:stat.laeufe_heute_titel', { anzahl: budget.tasks_today, max: budget.max_tasks })}>
              <div className="text-xs uppercase tracking-wide text-slate-500">{chatgpt ? t('tasks:stat.laeufe_heute') : t('tasks:stat.heute_verbraucht')}</div>
              <div className={`mt-1 text-3xl font-bold ${knapp ? 'text-amber-600' : 'text-brand-navy'}`}>
                {chatgpt ? budget.tasks_today : `$${budget.spent_today.toFixed(2)}`}
              </div>
              <div className="mt-1 text-xs text-slate-400">
                {chatgpt
                  ? t('tasks:stat.von_max_laeufen', { max: budget.max_tasks })
                  : <>{t('tasks:stat.von_betrag', { betrag: budget.daily_budget.toFixed(2), anzahl: budget.tasks_today, max: budget.max_tasks })}</>}
              </div>
            </div>
          )
        })()}
        {chatgpt ? (
          <div className="rounded-xl border border-brand-cyan/40 bg-white p-4 shadow-sm"
            title={t('tasks:stat.token_gesamt_titel')}>
            <div className="text-xs uppercase tracking-wide text-slate-500">{t('tasks:stat.token_gesamt')}</div>
            <div className="mt-1 text-3xl font-bold text-brand-cyan">{tokenText(stats.token)}</div>
            <div className="mt-1 text-xs text-slate-400">{t('tasks:stat.keine_usd_kosten')}</div>
          </div>
        ) : (
          <div className="rounded-xl border border-brand-cyan/40 bg-white p-4 shadow-sm"><div className="text-xs uppercase tracking-wide text-slate-500">{t('tasks:stat.kosten_gesamt')}</div><div className="mt-1 text-3xl font-bold text-brand-cyan">${stats.kosten.toFixed(2)}</div></div>
        )}
      </div>

      <div className="flex items-center gap-1 rounded-xl border border-slate-200 bg-white p-2 shadow-sm">
        {FILTERS.map((f) => (
          <button key={f.id} onClick={() => setFilter(f.id)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${filter === f.id ? 'bg-brand-cyan text-brand-aufAktion hover:bg-brand-cyanHover' : 'text-slate-600 hover:bg-slate-100'}`}>
            {t(`tasks:filter.${f.id}`)}
          </button>
        ))}
        <span className="ml-auto pr-2 text-xs text-slate-400">
          {rowsGesamt > rows.length
            ? t('tasks:letzte_von', { anzahl: zahl(rows.length), gesamt: zahl(rowsGesamt) })
            : t('tasks:eintraege', { count: rows.length })}
        </span>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">#</th><th className="px-3 py-2">{t('tasks:spalte.aufgabe')}</th><th className="px-3 py-2">{t('tasks:spalte.stelle')}</th>
              <th className="px-3 py-2">{t('tasks:spalte.status')}</th><th className="px-3 py-2">{t('tasks:spalte.gestartet')}</th>
              <th className="px-3 py-2 text-right">{t('tasks:spalte.dauer')}</th><th className="px-3 py-2 text-right">{t('tasks:spalte.kosten')}</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 ? (
              <tr><td colSpan={8} className="px-3 py-8 text-center text-slate-400">{t('tasks:keine_laeufe')}</td></tr>
            ) : rows.map((lauf) => (
              <>
                <tr key={lauf.id} className="align-top hover:bg-brand-cyan/5">
                  <td className="px-3 py-2 text-slate-400">{lauf.id}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-brand-navy">{lauf.label}</span>
                      {lauf.retry_count > 0 && (
                        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800"
                          title={t('tasks:versuch_titel')}>
                          {t('tasks:versuch', { aktuell: lauf.retry_count + 1, max: lauf.max_retries + 1 })}
                        </span>
                      )}
                    </div>
                    {lauf.chain_id && <div className="text-xs text-indigo-700">{t('tasks:kette', { kette: lauf.chain_label, pos: lauf.chain_pos })}</div>}
                    {lauf.status === 'failed' && lauf.error && <div className="mt-0.5 max-w-md text-xs text-rose-600">{lauf.error}</div>}
                  </td>
                  <td className="px-3 py-2">
                    {lauf.job_id ? (
                      <Link to={`/jobs/${lauf.job_id}`} className="text-brand-cyan hover:underline">
                        {lauf.company_name || lauf.job_title ? `${lauf.company_name || '–'} · ${lauf.job_title || '–'}` : t('tasks:job_nr', { id: lauf.job_id })}
                      </Link>
                    ) : <span className="text-slate-400">–</span>}
                  </td>
                  <td className="px-3 py-2"><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${CHIP[lauf.status]}`}>{t(`tasks:chip.${lauf.status}`, { defaultValue: lauf.status })}</span></td>
                  <td className="whitespace-nowrap px-3 py-2 text-slate-500">{zeit(lauf.started_at || lauf.created_at)}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-500">{lauf.duration_s != null ? `${lauf.duration_s}s` : '–'}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-500"
                    title={lauf.tokens ? t('tasks:lauf_token_titel') : undefined}>{laufKosten(lauf, anbieter) ?? '–'}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right text-xs">
                    <button onClick={() => setOpen(open === lauf.id ? null : lauf.id)} className="text-brand-cyan hover:underline">
                      {open === lauf.id ? t('tasks:log_zu') : t('tasks:log_zeigen')}
                    </button>
                    {ACTIVE.includes(lauf.status) ? (
                      <button onClick={() => cancel(lauf.id)} className="ml-2 text-slate-500 hover:text-rose-600">{t('tasks:abbrechen')}</button>
                    ) : (
                      <button onClick={() => rerun(lauf)} className="ml-2 text-slate-500 hover:text-brand-navy">{t('tasks:erneut')}</button>
                    )}
                  </td>
                </tr>
                {open === lauf.id && (
                  <tr key={`${lauf.id}-log`}>
                    <td colSpan={8} className="bg-slate-50 p-3">
                      <div className="max-h-64 overflow-y-auto rounded-lg border border-slate-200 bg-white p-2 font-mono text-[11px] leading-relaxed text-slate-600">
                        {log.length === 0
                          ? <span className="text-slate-400">{t('tasks:noch_keine_ausgabe')}</span>
                          : log.map(pretty).filter(Boolean).map((l, i) => <div key={i} className="truncate" title={l as string}>{l}</div>)}
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
