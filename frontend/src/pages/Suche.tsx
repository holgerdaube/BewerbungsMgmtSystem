import { useEffect, useRef, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { api } from '../api'
import { ScoreBadge, StatusBadge } from '../components/ui'

const QUELLE_LABEL: Record<string, string> = {
  stelle: 'Stelle', stellenbeschreibung: 'Stellenbeschreibung', 'company-fit': 'Company-Fit',
  transkript: 'Transkript', debrief: 'Debrief', briefing: 'Briefing', verlauf: 'Verlauf',
}

function QuelleBadge({ quelle }: { quelle: string }) {
  return (
    <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold uppercase text-slate-500">
      {QUELLE_LABEL[quelle] || quelle}
    </span>
  )
}

function formatBuiltAt(iso: string | null): string {
  if (!iso) return '–'
  const d = new Date(iso)
  return d.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export default function Suche() {
  const [sp, setSp] = useSearchParams()
  const [input, setInput] = useState(sp.get('q') || '')
  const [results, setResults] = useState<any>(null)
  const [meta, setMeta] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const firstRun = useRef(true)

  const loadMeta = async () => {
    try {
      const res = await api<any>('/search/meta')
      setMeta(res)
    } catch (e: any) {
      setMeta({ built_at: null, dokumente: 0, hinweis: e?.message || 'Index-Stand nicht ladbar' })
    }
  }

  // Index-Stand beim Mount laden — immer sichtbar, unabhängig von einer aktiven Suche.
  useEffect(() => { loadMeta() }, [])

  const runSearch = async (q: string) => {
    setLoading(true)
    setSp({ q }, { replace: true })
    try {
      const res = await api<any>(`/search?q=${encodeURIComponent(q)}`)
      setResults(res)
    } catch (e: any) {
      setResults({ q, built_at: null, ergebnisse: [], hinweis: e?.message || 'Suche fehlgeschlagen' })
    } finally {
      setLoading(false)
    }
  }

  // Debounce (400 ms) ab 2 Zeichen; beim ersten Render (Reload mit ?q=) sofort, ohne Wartezeit.
  useEffect(() => {
    const q = input.trim()
    if (timerRef.current) clearTimeout(timerRef.current)
    if (q.length < 2) { setResults(null); return }
    const delay = firstRun.current ? 0 : 400
    timerRef.current = setTimeout(() => { firstRun.current = false; runSearch(q) }, delay)
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [input])

  const onEnter = () => {
    if (timerRef.current) clearTimeout(timerRef.current)
    firstRun.current = false
    const q = input.trim()
    if (q.length >= 2) runSearch(q)
  }

  const doRebuild = async () => {
    setRebuilding(true)
    try {
      await api('/search/rebuild', { method: 'POST' })
      await loadMeta()
      const q = input.trim()
      if (q.length >= 2) await runSearch(q)
    } finally {
      setRebuilding(false)
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">Suche</h1>
        <p className="text-sm text-slate-500">Volltextsuche über Stellen, Stellenbeschreibungen, Company-Fit, Transkripte, Debriefs, Briefings und Verlauf — Ergebnis ist immer eine Stelle.</p>
      </div>

      <div className="relative">
        <input
          autoFocus
          className="w-full rounded-xl border border-slate-300 px-4 py-3 text-lg focus:border-brand-cyan focus:outline-none"
          placeholder="Suchbegriff — Firma, Ort, Stichwort aus einer Stellenbeschreibung oder einem Company-Fit-Dashboard…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') onEnter() }}
        />
        {loading && <div className="absolute right-4 top-1/2 -translate-y-1/2 text-sm text-slate-400">Sucht…</div>}
      </div>

      {/* Index-Stand + Rebuild-Button: immer sichtbar, unabhängig von einer aktiven Suche (Phase 29). */}
      {meta && (
        meta.built_at === null ? (
          <div className="rounded-xl border border-dashed border-amber-300 bg-amber-50 p-4 text-sm text-amber-800">
            {meta.hinweis || 'Index noch nicht gebaut'} —{' '}
            <button onClick={doRebuild} disabled={rebuilding}
                    className="font-semibold underline decoration-dotted hover:decoration-solid disabled:opacity-50">
              {rebuilding ? 'Baut Index…' : 'Index jetzt bauen'}
            </button>
          </div>
        ) : (
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Index-Stand: {formatBuiltAt(meta.built_at)} · {meta.dokumente} Dokumente</span>
            <button onClick={doRebuild} disabled={rebuilding}
                    className="rounded-lg border border-slate-300 px-2.5 py-1 text-slate-600 hover:bg-slate-50 disabled:opacity-50">
              {rebuilding ? 'Baut Index…' : '↻ Index aktualisieren'}
            </button>
          </div>
        )
      )}

      {input.trim().length > 0 && input.trim().length < 2 && (
        <div className="text-sm text-slate-400">Mindestens 2 Zeichen eingeben…</div>
      )}

      {results && (
        results.ergebnisse.length === 0 ? (
          results.built_at !== null && (
            <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-400">
              Keine Stelle gefunden für „{results.q}" — Index-Stand prüfen?
            </div>
          )
        ) : (
          <div className="space-y-3">
            {results.ergebnisse.map((e: any) => (
              <Link key={e.job_id} to={`/jobs/${e.job_id}`}
                    className="block rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-brand-cyan/60 hover:shadow-md">
                <div className="flex items-start gap-3">
                  <ScoreBadge score={e.job.match_score} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-brand-navy">{e.job.title}</span>
                      <StatusBadge status={e.job.status} />
                    </div>
                    <div className="text-sm text-slate-500">{e.job.company_name || '–'} · {e.job.location || '–'}</div>
                  </div>
                </div>
                <div className="mt-3 space-y-1.5">
                  {e.treffer.map((t: any, i: number) => (
                    <div key={i} className="flex items-start gap-2 text-sm text-slate-600">
                      <QuelleBadge quelle={t.quelle} />
                      {/* Inhalt stammt aus dem eigenen FTS5-Index (server-generierte Snippets), nicht aus Nutzereingabe. */}
                      <span className="[&_mark]:rounded [&_mark]:bg-brand-cyan/30 [&_mark]:px-0.5" dangerouslySetInnerHTML={{ __html: t.snippet }} />
                    </div>
                  ))}
                </div>
              </Link>
            ))}
          </div>
        )
      )}
    </div>
  )
}
