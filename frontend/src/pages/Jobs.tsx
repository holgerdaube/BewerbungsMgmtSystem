import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, type JobRow } from '../api'
import { ScoreBadge, StatusBadge, STATUS_FARBEN, STATUS_FARBE_UNBEKANNT, DubletteBadge, NeuausschreibungBadge,
  parseDubletteVerdacht, parseNeuausschreibung } from '../components/ui'
import { isoTag } from '../zeit'
import { useSuchTabs } from '../suchbereich'

const STATUSES = ['', 'Neu', 'Prüfen', 'Beworben', 'Absage', 'Keine Rückmeldung', 'Kein Match', 'Beirat abgelehnt', 'Nicht verfügbar', 'Geparkt']
const STATUS_REIHENFOLGE = Object.keys(STATUS_FARBEN)

// Überschrift je nach aktivem Drill-down (vom Dashboard verlinkt)
function heading(sp: URLSearchParams): { title: string; hint?: string } {
  if (sp.get('statuses')) return { title: 'Laufende Bewerbungen', hint: 'Beworben · Interview · Angebot' }
  if (sp.get('score')) return { title: sp.get('score') === 'none' ? 'Stellen · ohne Zielstellen-Fit' : `Stellen · Zielstellen-Fit ${sp.get('score')}/5` }
  if (sp.get('situation')) {
    const plan = sp.get('plan')
    return { title: `Stellen · Situation ${sp.get('situation')}${plan ? ` · Plan ${plan}` : ''}` }
  }
  if (sp.get('plan') === 'none') return { title: 'Stellen · ohne Plan-Zuordnung' }
  if (sp.get('plan')) return { title: `Stellen · Plan ${sp.get('plan')}` }
  if (sp.get('portal')) return { title: `Stellen · Portal ${sp.get('portal')}` }
  if (sp.get('availability_status')) return { title: `Beworbene Stellen · ${sp.get('availability_status')}` }
  if (Number(sp.get('min_score')) >= 4) return { title: 'Top-Zielstellen', hint: 'Zielstellen-Fit ≥ 4' }
  if (sp.get('status')) return { title: `Stellen · ${sp.get('status')}` }
  return { title: 'Stellen' }
}

export default function Jobs() {
  const nav = useNavigate()
  const [sp, setSp] = useSearchParams()
  const [jobs, setJobs] = useState<JobRow[]>([])
  const [loading, setLoading] = useState(true)
  const [verteilung, setVerteilung] = useState<JobRow[] | null>(null)
  // P2-51: Umkreis-Tab dynamisch aus den Einstellungen statt fest „<Stadt> +100km".
  const suchTabs = useSuchTabs()

  const status = sp.get('status') || ''
  const statuses = sp.get('statuses') || ''
  const tab = sp.get('tab') || ''
  const minScore = Number(sp.get('min_score') || 0)
  const score = sp.get('score') || ''
  const situation = sp.get('situation') || ''
  const plan = sp.get('plan') || ''
  const portal = sp.get('portal') || ''
  const availabilityStatus = sp.get('availability_status') || ''
  const q = sp.get('q') || ''
  const sort = sp.get('sort') || 'score'

  // Ein Filter ändern → URL aktualisieren (leere Werte entfernen), Rest bleibt erhalten
  const upd = (patch: Record<string, string>) => {
    const next = new URLSearchParams(sp)
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    setSp(next, { replace: true })
  }

  useEffect(() => {
    // Basis-Query OHNE Status-Filter (Suche/Tab/Score bleiben) — Grundlage für den
    // Verteilungsbalken (Phase 43, Design-Entscheidung 1): „wie verteilt sich meine aktuelle
    // Auswahl über alle Status", unabhängig davon, ob gerade nach einem Status gefiltert wird.
    const basis = new URLSearchParams()
    if (tab) basis.set('tab', tab)
    if (minScore) basis.set('min_score', String(minScore))
    if (score) basis.set('score', score)
    if (situation) basis.set('situation', situation)
    if (plan) basis.set('plan', plan)
    if (portal) basis.set('portal', portal)
    if (availabilityStatus) basis.set('availability_status', availabilityStatus)
    if (q) basis.set('q', q)
    basis.set('sort', sort)

    const p = new URLSearchParams(basis)
    if (status) p.set('status', status)
    if (statuses) p.set('statuses', statuses)
    setLoading(true)
    const tabellenLauf = api<JobRow[]>(`/jobs?${p.toString()}`)
    tabellenLauf.then(setJobs).finally(() => setLoading(false))

    // Ohne aktiven Status-Filter ist die Balken-Query identisch zur Tabellen-Query —
    // dann denselben Request wiederverwenden statt ihn doppelt zu stellen.
    const verteilungLauf = (status || statuses) ? api<JobRow[]>(`/jobs?${basis.toString()}`) : tabellenLauf
    verteilungLauf.then(setVerteilung).catch(() => setVerteilung([]))
  }, [status, statuses, tab, minScore, score, situation, plan, portal, availabilityStatus, q, sort])

  const h = heading(sp)
  // P2-51 Nebenbefund: ein reiner Tab-Filter zeigte „Filter zurücksetzen" bisher nicht an.
  const filtered = statuses !== '' || (Number(sp.get('min_score')) >= 4) || status !== '' ||
    score !== '' || situation !== '' || plan !== '' || portal !== '' || availabilityStatus !== '' || tab !== ''
  const today = isoTag()
  // Ein per URL gesetzter Tab, der nicht (mehr) in der aktuellen Liste steht (z. B. nach einer
  // Umkreis-Umbenennung ein alter Bucket-Name), bleibt als Option sichtbar statt zu verschwinden.
  const tabOptions = ['', ...suchTabs, ...(tab && !suchTabs.includes(tab) ? [tab] : [])]

  const verteilungCounts = (verteilung || [])
    .reduce((acc: Record<string, number>, j) => {
      const s = j.status || 'Neu'
      acc[s] = (acc[s] || 0) + 1
      return acc
    }, {})
  const verteilungSegmente = STATUS_REIHENFOLGE
    .map((s) => ({ status: s, n: verteilungCounts[s] || 0 }))
    .filter((x) => x.n > 0)
  const verteilungGesamt = verteilungSegmente.reduce((sum, x) => sum + x.n, 0)

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-brand-navy">{h.title}</h1>
          <p className="text-sm text-slate-500">
            {jobs.length} Treffer{h.hint ? ` · ${h.hint}` : ''} · Klick auf eine Zeile öffnet die Details
          </p>
        </div>
        <div className="flex items-center gap-2">
          {filtered && (
            <button onClick={() => setSp(new URLSearchParams(), { replace: true })}
                    className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">
              ✕ Filter zurücksetzen
            </button>
          )}
          <button onClick={() => nav('/jobs/neu')}
                  className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover">
            + Stelle anlegen
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <input
          value={q}
          onChange={(e) => upd({ q: e.target.value })}
          placeholder="Suche Firma / Titel…"
          className="w-56 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-cyan focus:outline-none"
        />
        <select value={status} onChange={(e) => upd({ status: e.target.value, statuses: '' })} className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm">
          {STATUSES.map((s) => <option key={s} value={s}>{s || 'Alle Status'}</option>)}
        </select>
        <select value={tab} onChange={(e) => upd({ tab: e.target.value })} className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm">
          {tabOptions.map((s) => <option key={s} value={s}>{s || 'Alle Tabs'}</option>)}
        </select>
        <select value={minScore} onChange={(e) => upd({ min_score: e.target.value === '0' ? '' : e.target.value })} className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm">
          {[0, 3, 4, 5].map((s) => <option key={s} value={s}>{s ? `Zielstellen-Fit ≥ ${s}` : 'Alle Fit-Werte'}</option>)}
        </select>
        <div className="ml-auto flex items-center gap-1.5 text-sm text-slate-500">
          <span>Sortieren:</span>
          <select value={sort} onChange={(e) => upd({ sort: e.target.value })} className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm">
            <option value="score">Zielstellen-Fit</option>
            <option value="found">Datum (neueste zuerst)</option>
            <option value="company">Firma</option>
            <option value="status">Status</option>
          </select>
        </div>
        {statuses && (
          <span className="inline-flex items-center gap-1 rounded-full bg-brand-cyan/15 px-2.5 py-1 text-xs font-medium text-brand-navy">
            Laufende Bewerbungen
            <button onClick={() => upd({ statuses: '' })} className="text-brand-navy/60 hover:text-brand-navy">✕</button>
          </span>
        )}
        {score && (
          <span className="inline-flex items-center gap-1 rounded-full bg-brand-cyan/15 px-2.5 py-1 text-xs font-medium text-brand-navy">
            {score === 'none' ? 'ohne Zielstellen-Fit' : `Zielstellen-Fit = ${score}`}
            <button onClick={() => upd({ score: '' })} className="text-brand-navy/60 hover:text-brand-navy">✕</button>
          </span>
        )}
        {situation && (
          <span className="inline-flex items-center gap-1 rounded-full bg-brand-cyan/15 px-2.5 py-1 text-xs font-medium text-brand-navy">
            Situation: {situation}
            <button onClick={() => upd({ situation: '' })} className="text-brand-navy/60 hover:text-brand-navy">✕</button>
          </span>
        )}
        {plan && (
          <span className="inline-flex items-center gap-1 rounded-full bg-brand-cyan/15 px-2.5 py-1 text-xs font-medium text-brand-navy">
            Plan: {plan === 'none' ? 'ohne Zuordnung' : plan}
            <button onClick={() => upd({ plan: '' })} className="text-brand-navy/60 hover:text-brand-navy">✕</button>
          </span>
        )}
        {portal && (
          <span className="inline-flex items-center gap-1 rounded-full bg-brand-cyan/15 px-2.5 py-1 text-xs font-medium text-brand-navy">
            Portal: {portal}
            <button onClick={() => upd({ portal: '' })} className="text-brand-navy/60 hover:text-brand-navy">✕</button>
          </span>
        )}
        {availabilityStatus && (
          <span className="inline-flex items-center gap-1 rounded-full bg-brand-cyan/15 px-2.5 py-1 text-xs font-medium text-brand-navy">
            Verfügbarkeit: {availabilityStatus}
            <button onClick={() => upd({ availability_status: '' })} className="text-brand-navy/60 hover:text-brand-navy">✕</button>
          </span>
        )}
      </div>

      {verteilung === null ? (
        <div className="h-7 animate-pulse rounded-lg bg-slate-100" />
      ) : verteilungGesamt > 0 && (
        <div className="flex h-7 overflow-hidden rounded-lg border border-slate-200">
          {verteilungSegmente.map(({ status: s, n }) => {
            const anteil = (n / verteilungGesamt) * 100
            const farbe = STATUS_FARBEN[s] || STATUS_FARBE_UNBEKANNT
            const aktiv = status === s
            const gedimmt = status !== '' && !aktiv
            const label = anteil >= 10 ? `${s} ${n}` : anteil >= 4 ? `${n}` : ''
            return (
              <button
                key={s}
                onClick={() => upd({ status: aktiv ? '' : s, statuses: '' })}
                title={`${s}: ${n} (${Math.round(anteil)} %)`}
                style={{
                  flexGrow: n, minWidth: 14,
                  backgroundColor: farbe.bg, color: farbe.text,
                  opacity: gedimmt ? 0.55 : 1,
                }}
                className={`flex items-center justify-center overflow-hidden whitespace-nowrap px-1 text-[11px] font-semibold transition-opacity hover:opacity-90 ${
                  aktiv ? 'ring-2 ring-inset ring-brand-navy' : ''}`}
              >
                {label}
              </button>
            )
          })}
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Fit</th>
              <th className="px-3 py-2">Firma</th>
              <th className="px-3 py-2">Rolle</th>
              <th className="px-3 py-2">Ebene</th>
              <th className="px-3 py-2">Standort</th>
              <th className="px-3 py-2">Gefunden</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr><td colSpan={8} className="px-3 py-8 text-center text-slate-400">Lade…</td></tr>
            ) : jobs.length === 0 ? (
              <tr><td colSpan={8} className="px-3 py-8 text-center text-slate-400">Keine Treffer</td></tr>
            ) : (
              jobs.map((j) => (
                <tr key={j.id} className="cursor-pointer hover:bg-brand-cyan/5" onClick={() => nav(`/jobs/${j.id}`)}>
                  <td className="px-3 py-2"><ScoreBadge score={j.match_score} /></td>
                  <td className="px-3 py-2 font-medium text-brand-navy">{j.company_name}</td>
                  <td className="px-3 py-2 text-slate-700">
                    {j.title}
                    {j.follow_up_date && (
                      <span className={`ml-2 whitespace-nowrap rounded px-1.5 py-0.5 text-[11px] font-medium ${
                        j.follow_up_date <= today ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700'}`}
                        title="Follow-up fällig">⏰ {j.follow_up_date}</span>
                    )}
                    {j.availability_status === 'offline' && (
                      <span className="ml-2 whitespace-nowrap rounded bg-rose-100 px-1.5 py-0.5 text-[11px] font-medium text-rose-700"
                        title={`Verfügbarkeit geprüft am ${j.availability_checked_at || '–'}`}>⛔ offline</span>
                    )}
                    {/* P2-42: dieselben Etiketten wie in Review und Job-Detail (der Hinweis stand im
                        Vermerk, die Liste zeigte ihn bislang nicht). stopPropagation: ein Klick aufs
                        Etikett führt zum Vorgänger, nicht über die Zeile zu dieser Stelle. */}
                    {(parseDubletteVerdacht(j.verify_note) || parseNeuausschreibung(j.verify_note)) && (
                      <span className="ml-2 inline-flex flex-wrap gap-1 align-middle" onClick={(e) => e.stopPropagation()}>
                        <DubletteBadge verifyNote={j.verify_note} />
                        <NeuausschreibungBadge verifyNote={j.verify_note} />
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-slate-500">{j.seniority || '–'}</td>
                  <td className="px-3 py-2 text-slate-500">{j.location || '–'}</td>
                  <td className="px-3 py-2 whitespace-nowrap text-slate-500 tabular-nums">{j.found_date || '–'}</td>
                  <td className="px-3 py-2"><StatusBadge status={j.status} /></td>
                  <td className="px-3 py-2 text-right">
                    {j.url && (
                      <a href={j.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="text-brand-cyan hover:underline">↗</a>
                    )}
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
