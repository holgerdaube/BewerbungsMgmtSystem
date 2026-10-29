import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { ScoreBadge, VerifyBadge, DubletteBadge, parseDubletteVerdacht, NeuausschreibungBadge } from '../components/ui'
import AgentTaskButton from '../components/AgentTaskButton'
import { useReviewCount } from '../context/ReviewCount'

const SUCH_KIND_LABEL: Record<string, string> = {
  'jobsuche': 'Jobsuche (WebSearch)', 'jobsuche-apify': 'Jobsuche + Apify', 'mail-jobsuche': 'Mail-Jobsuche',
  'zielfirmen-sweep': 'Zielfirmen-Sweep', 'headhunter-suche': 'Headhunter-Suche', 'beworben-check': 'Beworben-Check',
}
const SUCH_KINDS = Object.keys(SUCH_KIND_LABEL).join(',')
function suchZeit(iso: string) {
  // P2-20: Die API kennzeichnet ihre Zeitstempel seit 28.08.2026 als UTC (`app/zeit.py`),
  // das Anhaengen von 'Z' ist damit ueberfluessig geworden.
  const d = new Date(iso)
  return d.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export default function Review() {
  const [jobs, setJobs] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [letzterLauf, setLetzterLauf] = useState<any>(null)
  // P2-18 (Phase 93): Ziel-Element fuer die Lauf-Anzeige der unteren Button-Reihe. Bewusst als
  // State und nicht als useRef — der Portal-Aufruf in AgentTaskButton braucht ein Re-Render,
  // sobald das DOM-Element existiert; mit useRef bliebe das Ziel im ersten Durchlauf null und
  // der Bereich einmalig leer.
  const [laufBereich, setLaufBereich] = useState<HTMLDivElement | null>(null)
  const { refresh } = useReviewCount()

  const load = () => {
    setLoading(true)
    api<any[]>('/review').then(setJobs).finally(() => setLoading(false))
    // Phase 23: letzter Suchlauf kind-übergreifend (auch als Tageslauf-Schritt), unabhängig vom Button.
    api<any[]>(`/tasks?kinds=${SUCH_KINDS}&limit=1`)
      .then((r) => setLetzterLauf(r[0] || null)).catch(() => {})
  }
  useEffect(() => { load() }, [])

  const act = async (id: number, action: 'approve' | 'discard') => {
    setJobs((js) => js.filter((j) => j.id !== id)) // optimistic
    try {
      await api(`/jobs/${id}/${action}`, { method: 'POST' })
      refresh() // Nav-Badge synchron halten
    } catch {
      load() // rollback on error
    }
  }

  // Phase 44 Stufe B: Quick-Actions für einen Repost-Verdacht — über BESTEHENDE Endpunkte
  // (PATCH /jobs/{id}, POST /jobs/{id}/log), kein main.py-Change nötig.
  const parkenAlsDublette = async (job: any) => {
    const treffer = parseDubletteVerdacht(job.verify_note)
    if (!treffer) return
    const begruendung = `Dublette von Job ${treffer.jobId} — Text-Ähnlichkeit ${treffer.prozent} %`
    setJobs((js) => js.filter((j) => j.id !== job.id)) // optimistic — verlässt die Review-Liste
    try {
      await api(`/jobs/${job.id}`, {
        method: 'PATCH', body: JSON.stringify({ status: 'Geparkt', next_step: begruendung }),
      })
      await api(`/jobs/${job.id}/log`, {
        method: 'POST', body: JSON.stringify({ eintrag: `Als Dublette geparkt: ${begruendung}` }),
      })
      // Querverweis auch an der vermuteten Original-Stelle (Muster vom 20.07., von Hand).
      await api(`/jobs/${treffer.jobId}/log`, {
        method: 'POST',
        body: JSON.stringify({ eintrag: `Job ${job.id} („${job.title}") wurde als vermutete Dublette dieser Stelle geparkt.` }),
      })
      refresh()
    } catch {
      load()
    }
  }
  const keineDublette = async (job: any) => {
    // Exakt den " | DUBLETTE? …"-Anhang entfernen (endet vor dem nächsten "|" oder String-Ende),
    // Rest der verify_note bleibt wörtlich erhalten.
    const bereinigt = (job.verify_note || '').replace(/ \| DUBLETTE\?[^|]*/, '')
    setJobs((js) => js.map((j) => (j.id === job.id ? { ...j, verify_note: bereinigt } : j))) // optimistic
    try {
      await api(`/jobs/${job.id}`, { method: 'PATCH', body: JSON.stringify({ verify_note: bereinigt }) })
      await api(`/jobs/${job.id}/log`, { method: 'POST', body: JSON.stringify({ eintrag: 'Dublette-Verdacht verneint.' }) })
    } catch {
      load()
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">Neu / Review</h1>
        <p className="text-sm text-slate-500">
          {loading ? 'Lade…' : `${jobs.length} neue Treffer aus der Jobsuche · annehmen (→ Prüfen) oder verwerfen (→ Kein Match)`}
        </p>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-2 text-sm font-semibold text-brand-navy">Neue Jobsuche starten</div>
        {letzterLauf && (
          <div className="mb-2 truncate text-xs text-slate-500" title={letzterLauf.result || ''}>
            <span className="font-medium text-slate-600">Letzter Suchlauf:</span>{' '}
            <span className="tabular-nums">{suchZeit(letzterLauf.created_at)}</span>
            {' · '}{SUCH_KIND_LABEL[letzterLauf.kind] || letzterLauf.kind}
            {letzterLauf.chain_id ? ' · aus Tageslauf' : ''}
            {letzterLauf.result ? ` · ${letzterLauf.result.slice(0, 100)}` : ''}
          </div>
        )}
        <div className="flex flex-col gap-2 sm:flex-row">
          {/* Beide Jobsuchen gleich aufgebaut (14.10.2026): großer Knopf, darunter Status,
              Kosten und Abschlussmeldung. Vorher war „+ Apify" `subtle` und zeigte nach dem Lauf nichts.
              `zweizeilig` hält den Kopf beider Spalten gleich hoch, die Meldungen stehen auf einer Höhe. */}
          <div className="min-w-0 flex-1"><AgentTaskButton kind="jobsuche" label="Jobsuche (WebSearch)" zweizeilig onFinished={() => { load(); refresh() }} /></div>
          <div className="min-w-0 flex-1"><AgentTaskButton kind="jobsuche-apify" label="Jobsuche + Apify" zweizeilig onFinished={() => { load(); refresh() }} /></div>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          Läuft headless im Hintergrund (einige Minuten). „+ Apify" nutzt zusätzlich die Portal-Scraper —
          kostet Apify-Credits (durch das Budget gedeckelt); WebSearch ist kostenlos.
        </p>
        <div className="mt-3 flex flex-col gap-2 border-t border-slate-100 pt-3 sm:flex-row">
          <div className="min-w-0 flex-1"><AgentTaskButton kind="zielfirmen-sweep" statusTarget={laufBereich} label="Zielfirmen-Sweep" subtle onFinished={() => { load(); refresh() }} /></div>
          <div className="min-w-0 flex-1"><AgentTaskButton kind="headhunter-suche" statusTarget={laufBereich} label="Headhunter-Suche" subtle onFinished={() => { load(); refresh() }} /></div>
          <div className="min-w-0 flex-1"><AgentTaskButton kind="beworben-check" statusTarget={laufBereich} label="Beworben-Check" subtle onFinished={() => { load(); refresh() }} /></div>
          <div className="min-w-0 flex-1"><AgentTaskButton kind="email-check" statusTarget={laufBereich} label="E-Mail-Check" subtle onFinished={() => { load(); refresh() }} /></div>
        </div>
        {/* Gemeinsame Lauf-Anzeige der vier Schaltflaechen darueber (P2-18). Vorher rendert
            jeder Button Status und Log in seine eigene `flex-1`-Spalte; eine lange Log-Zeile
            zwang die Spalte auf volle Textbreite und schob sie aus der Karte heraus (gemessen
            1343 px in einer 992 px breiten Karte). Hier hat der Bericht die volle Breite.
            `empty:hidden` laesst den Bereich verschwinden, solange nichts laeuft. */}
        <div ref={setLaufBereich} className="mt-3 space-y-2 empty:hidden" />
        <p className="mt-2 text-xs text-slate-400">
          Rotierende Karriereseiten-Prüfung (Phase 26) — je Lauf ein Ausschnitt der Zielfirmen bzw.
          Headhunter, kostenlos (WebFetch). Beworben-Check: prüft wöchentlich, ob beworbene Stellen
          noch ausgeschrieben sind. E-Mail-Check: liest nur das Postfach (Antworten, Absagen,
          Termine) und ordnet Mails den Bewerbungen zu — ohne Jobsuche.
        </p>
      </div>

      {!loading && jobs.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-slate-400">
          Keine neuen Treffer. Starte oben eine Jobsuche — neue Treffer landen hier zur Sichtung.
        </div>
      )}

      <div className="space-y-3">
        {jobs.map((j) => (
          <div key={j.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-start gap-3">
              <ScoreBadge score={j.match_score} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <Link to={`/jobs/${j.id}`} className="font-semibold text-brand-navy hover:underline">{j.title}</Link>
                  <span className="text-sm text-slate-500">· {j.company_name}</span>
                  <VerifyBadge verifyNote={j.verify_note} verifiedAt={j.verified_at} />
                  <DubletteBadge verifyNote={j.verify_note} />
                  <NeuausschreibungBadge verifyNote={j.verify_note} />
                </div>
                <div className="mt-0.5 flex flex-wrap gap-2 text-xs text-slate-500">
                  {j.location && <span>📍 {j.location}</span>}
                  {j.seniority && <span>· {j.seniority}</span>}
                  {j.portal && <span>· {j.portal}</span>}
                  {j.tab && <span>· {j.tab}</span>}
                  {j.plan_ab && <span>· Plan {j.plan_ab}</span>}
                  {j.salary && <span>· 💶 {j.salary}</span>}
                </div>
                {j.match_rationale && (
                  <p className="mt-2 text-sm text-slate-600">{j.match_rationale}</p>
                )}
              </div>
              <div className="flex shrink-0 flex-col items-stretch gap-2">
                {j.url && (
                  <a href={j.url} target="_blank" rel="noreferrer" className="rounded-lg border border-slate-300 px-3 py-1 text-center text-xs text-slate-600 hover:bg-slate-50">Öffnen ↗</a>
                )}
                <button onClick={() => act(j.id, 'approve')} className="rounded-lg bg-brand-cyan px-3 py-1 text-xs font-semibold text-brand-navy hover:brightness-95">✓ Annehmen</button>
                <button onClick={() => act(j.id, 'discard')} className="rounded-lg bg-slate-100 px-3 py-1 text-xs font-medium text-slate-500 hover:bg-rose-50 hover:text-rose-600">✕ Verwerfen</button>
                {parseDubletteVerdacht(j.verify_note) && (
                  <>
                    <button onClick={() => parkenAlsDublette(j)}
                      title="Setzt Status auf Geparkt + Querverweis-Notiz an beiden Stellen. Regel: die weiter fortgeschrittene Stelle bleibt."
                      className="rounded-lg border border-amber-300 px-3 py-1 text-xs font-medium text-amber-700 hover:bg-amber-50">
                      Als Dublette parken
                    </button>
                    <button onClick={() => keineDublette(j)}
                      className="rounded-lg border border-slate-300 px-3 py-1 text-xs text-slate-500 hover:bg-slate-50">
                      Keine Dublette
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
