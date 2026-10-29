import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type FollowUp } from '../api'
import { ScoreBadge, StatusBadge, CopyChip } from '../components/ui'
import { isoTag } from '../zeit'
import { useProfilAdresse, mapsRouteUrl } from '../profil'

function daysLabel(dateStr: string, today: string): string {
  const d = Math.round((new Date(dateStr).getTime() - new Date(today).getTime()) / 86400000)
  if (d === 0) return 'heute fällig'
  if (d < 0) return `${-d} Tag${d === -1 ? '' : 'e'} überfällig`
  if (d === 1) return 'morgen'
  return `in ${d} Tagen`
}

function Row({ f, today }: { f: FollowUp; today: string }) {
  const nav = useNavigate()
  return (
    <div onClick={() => nav(`/jobs/${f.id}`)}
         className="flex cursor-pointer items-start gap-3 border-b border-slate-100 px-4 py-3 last:border-0 hover:bg-brand-cyan/5">
      <ScoreBadge score={f.match_score} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-brand-navy">{f.company_name || '–'}</span>
          <span className="text-slate-500">· {f.title}</span>
          <StatusBadge status={f.status} />
        </div>
        {f.next_step && <div className="mt-0.5 text-sm text-slate-700"><span className="text-slate-400">Nächster Schritt:</span> {f.next_step}</div>}
        {f.notes && <div className="mt-0.5 truncate text-xs text-slate-400">{f.notes}</div>}
      </div>
      <div className="shrink-0 text-right">
        <div className="text-sm font-medium tabular-nums text-slate-700">{f.follow_up_date}</div>
        <div className={`text-xs ${f.overdue ? 'font-semibold text-rose-600' : 'text-slate-400'}`}>{daysLabel(f.follow_up_date, today)}</div>
        <div className="mt-1.5"><CopyChip phrase={`Nachfass-Entwurf für Job ${f.id}`} label="✉️ Nachfass" /></div>
      </div>
    </div>
  )
}

export default function FollowUps() {
  const nav = useNavigate()
  const [items, setItems] = useState<FollowUp[] | null>(null)
  const [netzwerk, setNetzwerk] = useState<any[]>([])
  const [gespraeche, setGespraeche] = useState<any[]>([])
  const today = isoTag()
  // P2-50: Startpunkt der Routenplanung kommt aus dem Profil statt einer festen Adresse.
  const adresse = useProfilAdresse()

  useEffect(() => {
    // Phase 22: /followups ist zweiteilig ({jobs, netzwerk}).
    api<any>('/followups').then((r) => { setItems(r.jobs || []); setNetzwerk(r.netzwerk || []) })
    api<any[]>('/upcoming-interviews').then(setGespraeche).catch(() => {})
  }, [])

  if (!items) return <div className="text-slate-400">Lade…</div>
  const overdue = items.filter((f) => f.overdue)
  const upcoming = items.filter((f) => !f.overdue)
  const nOverdue = netzwerk.filter((n) => n.overdue)
  const nUpcoming = netzwerk.filter((n) => !n.overdue)

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">Follow-ups</h1>
        <p className="text-sm text-slate-500">
          Fällige nächste Schritte &amp; anstehende Gespräche · Fälligkeit setzt du im Job-Detail · ✉️ kopiert den Nachfass-Auslöser
        </p>
      </div>

      {gespraeche.length > 0 && (
        <div className="rounded-xl border border-indigo-200 bg-white shadow-sm">
          <div className="border-b border-indigo-100 bg-indigo-50/60 px-4 py-2.5">
            <h3 className="text-sm font-semibold text-indigo-800">🎙️ Anstehende Gespräche ({gespraeche.length})</h3>
          </div>
          {gespraeche.map((g) => (
            <div key={g.id} onClick={() => nav(`/jobs/${g.job_id}`)}
                 className="flex cursor-pointer items-start gap-3 border-b border-slate-100 px-4 py-3 last:border-0 hover:bg-brand-cyan/5">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-brand-navy">{g.company_name || '–'}</span>
                  <span className="text-slate-500">· {g.title}</span>
                  <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-800">Runde {g.runde} · {g.art || 'Gespräch'}</span>
                </div>
                {g.interviewer && <div className="mt-0.5 text-xs text-slate-500">{g.interviewer}</div>}
                <div className="mt-1 flex flex-wrap gap-2 text-xs" onClick={(e) => e.stopPropagation()}>
                  {g.prep_path && <a href={`/api/artifact?path=${encodeURIComponent(g.prep_path)}`} className="text-brand-cyan hover:underline">📋 Briefing</a>}
                  {g.location && !/remote/i.test(g.location) && (
                    <a href={mapsRouteUrl(adresse, g.location)}
                       target="_blank" rel="noreferrer" className="text-brand-cyan hover:underline" title="Route von zu Hause (Google Maps)">🗺️ Route</a>
                  )}
                </div>
              </div>
              <div className="shrink-0 text-right">
                <div className="text-sm font-medium tabular-nums text-slate-700">{g.scheduled_at ? g.scheduled_at.replace('T', ' ') : '—'}</div>
                {!g.scheduled_at && <div className="text-xs text-amber-600">Termin fehlt — im Job-Detail setzen</div>}
              </div>
            </div>
          ))}
        </div>
      )}

      {items.length === 0 && netzwerk.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-slate-400 shadow-sm">
          Noch keine Follow-ups gesetzt. Öffne eine Stelle (Fälligkeitsdatum unter „Nächste Schritte &amp; Follow-up")
          oder setze bei einem Netzwerk-Kontakt eine „Fällig am"-Aktion.
        </div>
      ) : (
        <>
          {items.length > 0 && (
            <>
              <div className="rounded-xl border border-rose-200 bg-white shadow-sm">
                <div className="flex items-center justify-between border-b border-rose-100 bg-rose-50/60 px-4 py-2.5">
                  <h3 className="text-sm font-semibold text-rose-700">🔴 Stellen — überfällig &amp; heute ({overdue.length})</h3>
                </div>
                {overdue.length === 0
                  ? <div className="px-4 py-6 text-center text-sm text-slate-400">Nichts überfällig — sauber. 👍</div>
                  : overdue.map((f) => <Row key={f.id} f={f} today={today} />)}
              </div>

              <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
                <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
                  <h3 className="text-sm font-semibold text-brand-navy">⏳ Stellen — anstehend ({upcoming.length})</h3>
                </div>
                {upcoming.length === 0
                  ? <div className="px-4 py-6 text-center text-sm text-slate-400">Keine anstehenden Follow-ups.</div>
                  : upcoming.map((f) => <Row key={f.id} f={f} today={today} />)}
              </div>
            </>
          )}

          {netzwerk.length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-4 py-2.5">
                <h3 className="text-sm font-semibold text-brand-navy">🤝 Netzwerk-Aktionen ({netzwerk.length})</h3>
              </div>
              {[...nOverdue, ...nUpcoming].map((n) => (
                <div key={n.id} onClick={() => nav('/netzwerk')}
                     className="flex cursor-pointer items-start gap-3 border-b border-slate-100 px-4 py-3 last:border-0 hover:bg-brand-cyan/5">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-brand-navy">{n.name || '–'}</span>
                      {n.unternehmen && <span className="text-slate-500">· {n.unternehmen}</span>}
                    </div>
                    {n.next_action && <div className="mt-0.5 text-sm text-slate-700"><span className="text-slate-400">Nächste Aktion:</span> {n.next_action}</div>}
                  </div>
                  <div className="shrink-0 text-right">
                    <div className="text-sm font-medium tabular-nums text-slate-700">{n.next_action_date}</div>
                    <div className={`text-xs ${n.overdue ? 'font-semibold text-rose-600' : 'text-slate-400'}`}>{daysLabel(n.next_action_date, today)}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
