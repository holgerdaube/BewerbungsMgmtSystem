import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import AgentTaskButton from './AgentTaskButton'

function fmt(iso: string | null) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

const STATUS_VORSCHLAG: Record<string, string> = { 'Absage': 'Absage', 'Angebot': 'Angebot', 'Einladung': 'Interview' }

/** Zuordnen-Picker für E-Mails ohne Stelle (Phase 36) — Suche gegen /api/jobs?q=,
 *  „+ Stelle anlegen" mit Vorbefüllung. Der Status-Vorschlag nach dem Zuordnen lebt in
 *  EmailDetail (nicht hier) — sobald `onChanged()` die Mail-Liste neu lädt, bekommt diese
 *  Komponente `email.job_id` gesetzt und wird durch den „Lösen"-Zweig ersetzt; ein hier
 *  lokal gehaltener Hinweis würde dabei mit verschwinden. */
function AssignPicker({ email, onAssigned }: { email: any; onAssigned: (hinweis: string | null) => void }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [results, setResults] = useState<any[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open || q.trim().length < 2) { setResults([]); return }
    const t = setTimeout(() => {
      api<any[]>(`/jobs?q=${encodeURIComponent(q.trim())}`).then((rs) => setResults(rs.slice(0, 8))).catch(() => setResults([]))
    }, 250)
    return () => clearTimeout(t)
  }, [q, open])

  const assign = async (jobId: number) => {
    setBusy(true)
    try {
      const r = await api<{ email: any; hinweis: string | null }>(`/emails/${email.id}/assign`, {
        method: 'POST', body: JSON.stringify({ job_id: jobId }),
      })
      setOpen(false); setQ(''); setResults([])
      onAssigned(r.hinweis)
    } finally { setBusy(false) }
  }

  const anlegenHref = `/jobs/neu?company=${encodeURIComponent(email.company_name || '')}&notes=${encodeURIComponent(`Aus E-Mail „${email.subject || ''}“`)}`

  return (
    <div className="mt-2">
      {!open ? (
        <button onClick={() => setOpen(true)} className="rounded-lg border border-brand-cyan/40 px-2.5 py-1 text-xs font-medium text-brand-cyan hover:bg-brand-cyan/5">
          📎 Stelle zuordnen
        </button>
      ) : (
        <div className="max-w-sm rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Firma oder Titel suchen…"
                 className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none" />
          {results.length > 0 && (
            <ul className="mt-2 max-h-48 divide-y divide-slate-100 overflow-y-auto">
              {results.map((r) => (
                <li key={r.id}>
                  <button disabled={busy} onClick={() => assign(r.id)}
                          className="w-full px-1 py-1.5 text-left text-xs hover:bg-brand-cyan/5 disabled:opacity-40">
                    <span className="font-medium text-brand-navy">{r.company_name}</span> — {r.title}
                    <span className="ml-1 text-slate-400">({r.status}{r.match_score ? ` · ${r.match_score}/5` : ''})</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-2 flex items-center justify-between">
            <Link to={anlegenHref} className="text-xs text-brand-cyan hover:underline">+ Stelle anlegen</Link>
            <button onClick={() => { setOpen(false); setQ(''); setResults([]) }} className="text-xs text-slate-400 hover:text-slate-600">Abbrechen</button>
          </div>
        </div>
      )}
    </div>
  )
}

/** Aufgeklappter Mail-Volltext + „Antwort entwerfen"-Button (Phase 27) + Zuordnen/Lösen
 *  (Phase 36). Gemeinsam für Inbox.tsx UND JobDetail.tsx „E-Mail-Verlauf" — nicht zweimal
 *  implementiert. */
export default function EmailDetail({ email, jobId, onChanged }: {
  email: any; jobId?: number; onChanged?: () => void
}) {
  const [body, setBody] = useState<{ body: string | null; hinweis?: string } | null>(null)
  const [loading, setLoading] = useState(true)
  const [loesenBusy, setLoesenBusy] = useState(false)
  const [zuordnungHinweis, setZuordnungHinweis] = useState<string | null>(null)
  // P2-52 — Archivieren für Mails ohne Stelle: nur in der App, Gmail bleibt unberührt.
  const [archivBusy, setArchivBusy] = useState(false)
  const [archivFehler, setArchivFehler] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    api<{ body: string | null; hinweis?: string }>(`/emails/${email.id}/body`)
      .then(setBody)
      .catch((e: any) => setBody({ body: null, hinweis: e?.message || 'Volltext konnte nicht geladen werden' }))
      .finally(() => setLoading(false))
  }, [email.id])

  const loesen = async () => {
    setLoesenBusy(true)
    try {
      await api(`/emails/${email.id}/assign`, { method: 'POST', body: JSON.stringify({ job_id: null }) })
      setZuordnungHinweis(null)
      onChanged?.()
    } finally { setLoesenBusy(false) }
  }

  const setzeStatus = async (status: string) => {
    if (!email.job_id) return
    await api(`/jobs/${email.job_id}`, { method: 'PATCH', body: JSON.stringify({ status }) })
    setZuordnungHinweis(null)
    onChanged?.()
  }

  // P2-52 — nur für Mails ohne Stelle (409 sonst, kommt hier gar nicht erst vor: der Knopf
  // erscheint nur bei email.ohne_stelle). Keine Rückfrage, umkehrbar über das Archiv-Panel.
  const archivieren = async () => {
    setArchivBusy(true); setArchivFehler(null)
    try {
      await api(`/emails/${email.id}/archive`, { method: 'POST' })
      onChanged?.()
    } catch (e: any) {
      setArchivFehler(e?.message || 'Archivieren fehlgeschlagen')
    } finally {
      setArchivBusy(false)
    }
  }

  return (
    <div className="bg-slate-50/70 px-4 py-4">
      {loading ? (
        <div className="text-sm text-slate-400">Lade…</div>
      ) : body?.body ? (
        <div className="max-h-96 overflow-y-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-700">
          {body.body}
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-slate-200 p-3 text-sm text-slate-400">
          {body?.hinweis || 'Kein Volltext verfügbar'}
        </div>
      )}

      {email.job_id ? (
        <button onClick={loesen} disabled={loesenBusy} className="mt-2 text-xs text-slate-400 hover:text-rose-600 disabled:opacity-40">
          🔓 Zuordnung lösen
        </button>
      ) : (
        <>
          <AssignPicker email={email} onAssigned={(hinweis) => { setZuordnungHinweis(hinweis); onChanged?.() }} />
          {email.ohne_stelle && !email.archived_at && (
            <div className="mt-2">
              <button onClick={archivieren} disabled={archivBusy}
                      className="rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40">
                {archivBusy ? 'Wird archiviert…' : '🗄 Archivieren'}
              </button>
              <p className="mt-1 text-xs text-slate-400">Nur in der App. Gmail bleibt unverändert.</p>
              {archivFehler && <p className="mt-1 text-xs text-rose-600">{archivFehler}</p>}
            </div>
          )}
        </>
      )}

      {zuordnungHinweis && (
        <div className="mt-2 max-w-sm rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-xs text-amber-800">
          <p>{zuordnungHinweis}</p>
          {STATUS_VORSCHLAG[email.category] && (
            <button onClick={() => setzeStatus(STATUS_VORSCHLAG[email.category])}
                    className="mt-1.5 rounded-lg bg-amber-600 px-2 py-1 text-xs font-medium text-white hover:brightness-110">
              Status auf „{STATUS_VORSCHLAG[email.category]}“ setzen
            </button>
          )}
          <button onClick={() => setZuordnungHinweis(null)} className="ml-2 text-xs text-amber-700 hover:underline">nicht jetzt</button>
        </div>
      )}

      {email.direction === 'incoming' && (
        <div className="mt-3 max-w-sm">
          {email.reply_draft_at && (
            <div className="mb-2 text-xs text-amber-700">
              ⚠ Entwurf liegt in Gmail seit {fmt(email.reply_draft_at)} — vor erneutem Anlegen prüfen (Doppel-Entwurf).
            </div>
          )}
          <AgentTaskButton
            kind="mail-antwort"
            jobId={jobId}
            params={{ email_id: email.id }}
            label="↩ Antwort entwerfen"
            subtle={!email.needs_reply}
            onFinished={onChanged}
          />
        </div>
      )}
    </div>
  )
}
