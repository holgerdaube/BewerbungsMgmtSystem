import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type AgentStatus, type AgentTaskRow } from '../api'
import { codexZeile, laufKosten, tokenText, useKiAnbieter } from '../components/ui'

const ACTIVE = ['queued', 'running']
const CHIP: Record<string, string> = {
  queued: 'bg-slate-100 text-slate-600', running: 'bg-indigo-100 text-indigo-800',
  done: 'bg-emerald-100 text-emerald-800', failed: 'bg-rose-100 text-rose-700',
  cancelled: 'bg-slate-100 text-slate-500',
}
const CHIP_TEXT: Record<string, string> = {
  queued: 'wartet', running: 'läuft', done: 'fertig', failed: 'fehlgeschlagen', cancelled: 'abgebrochen',
}
const FILTERS = [
  { id: 'alle', label: 'Alle' },
  { id: 'aktiv', label: 'Aktiv' },
  { id: 'failed', label: 'Fehlgeschlagen' },
] as const

function pretty(line: string): string | null {
  try {
    const ev = JSON.parse(line)
    if (ev.type === 'system') {
      // stream-json kennt mehrere system-Subtypen — nur `init` ist der Lauf-Start mit Tool-Liste.
      // (Bug bis 11.07.: JEDE system-Zeile wurde als „Lauf gestartet (0 Tools)" gerendert.)
      if (ev.subtype === 'init') return `· Lauf gestartet (${(ev.tools || []).length} Tools)`
      if (ev.subtype === 'task_started') return `⤷ Subagent: ${String(ev.description || 'gestartet').slice(0, 140)}`
      if (ev.subtype === 'task_notification' && ev.summary) return `⤷ Subagent fertig: ${String(ev.summary).slice(0, 140)}`
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
  return new Date(iso)
    .toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export default function Tasks() {
  const { anbieter } = useKiAnbieter()
  const chatgpt = anbieter === 'chatgpt'
  const [tasks, setTasks] = useState<AgentTaskRow[] | null>(null)
  const [budget, setBudget] = useState<AgentStatus | null>(null)
  const [filter, setFilter] = useState<typeof FILTERS[number]['id']>('alle')
  const [open, setOpen] = useState<number | null>(null)
  const [log, setLog] = useState<string[]>([])

  const load = () => {
    api<AgentTaskRow[]>('/tasks?limit=100').then(setTasks).catch(() => {})
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

  const stats = useMemo(() => {
    const all = tasks || []
    return {
      gesamt: all.length,
      aktiv,
      fehler: all.filter((t) => t.status === 'failed').length,
      kosten: all.reduce((s, t) => s + (t.cost_usd || 0), 0),
      token: all.reduce((s, t) => s + (t.tokens || 0), 0),
    }
  }, [tasks, aktiv])

  if (!tasks) return <div className="text-slate-400">Lade…</div>

  const rows = tasks.filter((t) =>
    filter === 'alle' ? true : filter === 'aktiv' ? ACTIVE.includes(t.status) : t.status === 'failed')

  const cancel = async (id: number) => {
    await api(`/tasks/${id}/cancel`, { method: 'POST' }).catch(() => {})
    load()
  }
  const rerun = async (t: AgentTaskRow) => {
    try {
      await api('/tasks', {
        method: 'POST',
        body: JSON.stringify(t.job_id ? { kind: t.kind, job_id: t.job_id } : { kind: t.kind }),
      })
      load()
    } catch (e: any) { alert(e?.message || 'Neustart nicht möglich') }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">Task-Center</h1>
        <p className="text-sm text-slate-500">
          Skills, die das Backend headless ausführt
          {budget && (chatgpt
            // ChatGPT (P2-86): Es gibt weder USD-Kosten noch eine Budgetgrenze je Lauf, begrenzt wird
            // durch Zeitlimit, Abo-Grenzen und die Zahl der Läufe am Tag.
            ? <> · max. {budget.max_parallel} parallel · max. {budget.max_tasks} Läufe am Tag · Zeitlimit statt Budget je Lauf</>
            : <> · max. {budget.max_parallel} parallel
              {budget.per_run_budget != null && <> · Notbremse ${budget.per_run_budget.toFixed(2)} je Lauf</>}
              {' '}· Tagesbudget ${budget.daily_budget.toFixed(2)} / {budget.max_tasks} Läufe</>)}
        </p>
        {budget?.warnung && (
          <p className="mt-1 text-xs text-amber-600">⚠ {budget.warnung}</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="text-xs uppercase tracking-wide text-slate-500">Läufe gesamt</div><div className="mt-1 text-3xl font-bold text-brand-navy">{stats.gesamt}</div></div>
        <div className="rounded-xl border border-indigo-200 bg-white p-4 shadow-sm"><div className="text-xs uppercase tracking-wide text-slate-500">Aktiv</div><div className={`mt-1 text-3xl font-bold ${stats.aktiv ? 'text-indigo-700' : 'text-brand-navy'}`}>{stats.aktiv}</div></div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="text-xs uppercase tracking-wide text-slate-500">Fehlgeschlagen</div><div className={`mt-1 text-3xl font-bold ${stats.fehler ? 'text-rose-600' : 'text-brand-navy'}`}>{stats.fehler}</div></div>
        {budget && (() => {
          // ChatGPT (P2-86): Dollar gibt es nicht, die Kachel zählt die Läufe gegen die Tagesgrenze.
          const anteil = chatgpt
            ? (budget.max_tasks ? budget.tasks_today / budget.max_tasks : 0)
            : (budget.daily_budget ? budget.spent_today / budget.daily_budget : 0)
          const knapp = anteil >= 0.8
          return (
            <div className={`rounded-xl border bg-white p-4 shadow-sm ${knapp ? 'border-amber-300' : 'border-slate-200'}`}
              title={`${budget.tasks_today} von ${budget.max_tasks} Läufen heute`}>
              <div className="text-xs uppercase tracking-wide text-slate-500">{chatgpt ? 'Läufe heute' : 'Heute verbraucht'}</div>
              <div className={`mt-1 text-3xl font-bold ${knapp ? 'text-amber-600' : 'text-brand-navy'}`}>
                {chatgpt ? budget.tasks_today : `$${budget.spent_today.toFixed(2)}`}
              </div>
              <div className="mt-1 text-xs text-slate-400">
                {chatgpt
                  ? `von max. ${budget.max_tasks} Läufen`
                  : <>von ${budget.daily_budget.toFixed(2)} · {budget.tasks_today}/{budget.max_tasks} Läufe</>}
              </div>
            </div>
          )
        })()}
        {chatgpt ? (
          <div className="rounded-xl border border-brand-cyan/40 bg-white p-4 shadow-sm"
            title="Neue Token aller Läufe: Eingabe ohne Cache plus Ausgabe">
            <div className="text-xs uppercase tracking-wide text-slate-500">Token gesamt</div>
            <div className="mt-1 text-3xl font-bold text-brand-cyan">{tokenText(stats.token)}</div>
            <div className="mt-1 text-xs text-slate-400">Kosten in USD meldet ChatGPT nicht</div>
          </div>
        ) : (
          <div className="rounded-xl border border-brand-cyan/40 bg-white p-4 shadow-sm"><div className="text-xs uppercase tracking-wide text-slate-500">Kosten gesamt</div><div className="mt-1 text-3xl font-bold text-brand-cyan">${stats.kosten.toFixed(2)}</div></div>
        )}
      </div>

      <div className="flex items-center gap-1 rounded-xl border border-slate-200 bg-white p-2 shadow-sm">
        {FILTERS.map((f) => (
          <button key={f.id} onClick={() => setFilter(f.id)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${filter === f.id ? 'bg-brand-cyan text-brand-aufAktion hover:bg-brand-cyanHover' : 'text-slate-600 hover:bg-slate-100'}`}>
            {f.label}
          </button>
        ))}
        <span className="ml-auto pr-2 text-xs text-slate-400">{rows.length} Einträge</span>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">#</th><th className="px-3 py-2">Aufgabe</th><th className="px-3 py-2">Stelle</th>
              <th className="px-3 py-2">Status</th><th className="px-3 py-2">Gestartet</th>
              <th className="px-3 py-2 text-right">Dauer</th><th className="px-3 py-2 text-right">Kosten</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 ? (
              <tr><td colSpan={8} className="px-3 py-8 text-center text-slate-400">Keine Läufe</td></tr>
            ) : rows.map((t) => (
              <>
                <tr key={t.id} className="align-top hover:bg-brand-cyan/5">
                  <td className="px-3 py-2 text-slate-400">{t.id}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-brand-navy">{t.label}</span>
                      {t.retry_count > 0 && (
                        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800"
                          title="Der erste Versuch schlug fehl und wurde wiederholt">
                          Versuch {t.retry_count + 1}/{t.max_retries + 1}
                        </span>
                      )}
                    </div>
                    {t.chain_id && <div className="text-xs text-indigo-700">{t.chain_label} · Schritt {t.chain_pos}</div>}
                    {t.status === 'failed' && t.error && <div className="mt-0.5 max-w-md text-xs text-rose-600">{t.error}</div>}
                  </td>
                  <td className="px-3 py-2">
                    {t.job_id ? (
                      <Link to={`/jobs/${t.job_id}`} className="text-brand-cyan hover:underline">
                        {t.company_name || t.job_title ? `${t.company_name || '–'} · ${t.job_title || '–'}` : `Job ${t.job_id}`}
                      </Link>
                    ) : <span className="text-slate-400">–</span>}
                  </td>
                  <td className="px-3 py-2"><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${CHIP[t.status]}`}>{CHIP_TEXT[t.status]}</span></td>
                  <td className="whitespace-nowrap px-3 py-2 text-slate-500">{zeit(t.started_at || t.created_at)}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-500">{t.duration_s != null ? `${t.duration_s}s` : '–'}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-500"
                    title={t.tokens ? 'Neue Token des Laufs: Eingabe ohne Cache plus Ausgabe' : undefined}>{laufKosten(t, anbieter) ?? '–'}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right text-xs">
                    <button onClick={() => setOpen(open === t.id ? null : t.id)} className="text-brand-cyan hover:underline">
                      {open === t.id ? 'Log zu' : 'Log'}
                    </button>
                    {ACTIVE.includes(t.status) ? (
                      <button onClick={() => cancel(t.id)} className="ml-2 text-slate-500 hover:text-rose-600">Abbrechen</button>
                    ) : (
                      <button onClick={() => rerun(t)} className="ml-2 text-slate-500 hover:text-brand-navy">Erneut</button>
                    )}
                  </td>
                </tr>
                {open === t.id && (
                  <tr key={`${t.id}-log`}>
                    <td colSpan={8} className="bg-slate-50 p-3">
                      <div className="max-h-64 overflow-y-auto rounded-lg border border-slate-200 bg-white p-2 font-mono text-[11px] leading-relaxed text-slate-600">
                        {log.length === 0
                          ? <span className="text-slate-400">Noch keine Ausgabe…</span>
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
