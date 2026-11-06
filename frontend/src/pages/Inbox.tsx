import { Fragment, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import EmailDetail from '../components/EmailDetail'
import { tagVon } from '../zeit'
import { t } from '../i18n'
import { datumZeit } from '../i18n/format'
import { wert } from '../i18n/werte'

const CAT_STYLE: Record<string, string> = {
  'Eingangsbestätigung': 'bg-sky-100 text-sky-800', // i18n-ok: DB-Wert
  'Einladung': 'bg-emerald-100 text-emerald-800',
  'Absage': 'bg-rose-100 text-rose-800',
  'Rückfrage': 'bg-amber-100 text-amber-800', // i18n-ok: DB-Wert
  'Angebot': 'bg-violet-100 text-violet-800',
  'Sonstige': 'bg-slate-100 text-slate-500',
}

function fmt(dt: string | null) {
  if (!dt) return '–'
  try {
    const d = new Date(dt)
    return datumZeit(d, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch { return dt }
}

// ── Archiv (P2-52): Mails ohne Stelle, die in der App ausgeblendet sind (Gmail bleibt
// unverändert). Muster `TrashPanel` in Netzwerk.tsx — ausklappbar, je Eintrag „Zurückholen“,
// unsichtbar wenn leer. Eigener Fetch gegen `/inbox?archived=true`, lädt neu, sobald der Zähler
// `signal` steigt (nach jedem erfolgreichen Archivieren/Zuordnen), damit frisch archivierte Mails
// sofort erscheinen.
function ArchivPanel({ signal, onRestored }: { signal: any; onRestored: () => void }) {
  const [items, setItems] = useState<any[]>([])
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<number | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const load = () => api<any[]>('/inbox?archived=true').then(setItems).catch(() => setItems([]))
  useEffect(() => { load() }, [signal])

  const restore = async (m: any) => {
    setBusy(m.id); setErr(null)
    try {
      await api(`/emails/${m.id}/restore`, { method: 'POST' })
      await load(); onRestored()
    } catch (e: any) { setErr(e?.message || t('inbox:fehler.zurueckholen')) }
    finally { setBusy(null) }
  }

  if (items.length === 0) return null

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/60">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-slate-500 hover:text-slate-700">
        <span className="text-slate-400">{open ? '▾' : '▸'}</span>
        <span className="font-medium">{t('inbox:archiv.titel', { anzahl: items.length })}</span>
        <span className="text-xs text-slate-400">{t('inbox:archiv.hinweis')}</span>
      </button>
      {open && (
        <div className="divide-y divide-slate-100 border-t border-slate-200">
          {err && <div className="px-4 py-2 text-sm text-rose-600">{err}</div>}
          {items.map((m) => (
            <div key={m.id} className="flex items-center justify-between gap-3 px-4 py-2">
              <div className="min-w-0 truncate">
                <span className="font-medium text-slate-600">{m.subject || t('inbox:archiv.kein_betreff')}</span>
                <span className="ml-2 text-xs text-slate-400">{m.from_addr}</span>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span className="text-xs text-slate-400">{t('inbox:archiv.archiviert', { datum: tagVon(m.archived_at) })}</span>
                <button onClick={() => restore(m)} disabled={busy === m.id}
                  className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-40">
                  {busy === m.id ? t('inbox:archiv.wird_zurueckgeholt') : t('inbox:archiv.zurueckholen')}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Inbox() {
  const [mails, setMails] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [cat, setCat] = useState('')
  const [onlyReply, setOnlyReply] = useState(false)
  const [onlyOhneStelle, setOnlyOhneStelle] = useState(false)
  const [open, setOpen] = useState<number | null>(null)
  // P2-52 — Archivieren-Knopf je Zeile: ein gemeinsamer busy-/Fehler-Zustand genügt (immer nur
  // ein Aufruf gleichzeitig, Muster TrashPanel).
  const [archivBusyId, setArchivBusyId] = useState<number | null>(null)
  const [archivFehler, setArchivFehler] = useState<string | null>(null)

  // Zähler für das Archiv-Panel: steigt erst NACH einem erfolgreichen Aufruf. An der Liste selbst
  // lässt sich das nicht festmachen, sie ändert sich beim optimistischen Entfernen schon vorher.
  const [archivStand, setArchivStand] = useState(0)

  const load = () => api<any[]>('/inbox').then(setMails).finally(() => setLoading(false))
  useEffect(() => { load() }, [])
  // Für EmailDetail: dort ändern Archivieren, Zuordnen und Lösen beide Listen.
  const neuLaden = () => { load(); setArchivStand((n) => n + 1) }

  // Optimistisch aus der Liste nehmen (kein window.confirm — Archivieren ist umkehrbar); bei
  // Fehler Meldung über der Tabelle und die echte Liste vom Server nachladen (Spec P2-52, F1;
  // Muster Review.tsx::act).
  const archivieren = async (id: number) => {
    setArchivBusyId(id); setArchivFehler(null)
    setMails((cur) => cur.filter((m) => m.id !== id))
    try {
      await api(`/emails/${id}/archive`, { method: 'POST' })
      setArchivStand((n) => n + 1)
    } catch (e: any) {
      setArchivFehler(e?.message || t('inbox:fehler.archivieren'))
      await load()
    } finally {
      setArchivBusyId(null)
    }
  }

  const filtered = mails.filter((m) => (!cat || m.category === cat) && (!onlyReply || m.needs_reply) && (!onlyOhneStelle || m.ohne_stelle))
  const stats = useMemo(() => {
    const resp = mails.filter((m) => m.response_time_hours != null)
    const avg = resp.length ? Math.round((resp.reduce((a, m) => a + m.response_time_hours, 0) / resp.length) * 10) / 10 : null
    const byCat: Record<string, number> = {}
    mails.forEach((m) => { byCat[m.category] = (byCat[m.category] || 0) + 1 })
    return { avg, byCat, needsReply: mails.filter((m) => m.needs_reply).length, ohneStelle: mails.filter((m) => m.ohne_stelle).length }
  }, [mails])

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">{t('inbox:titel')}</h1>
        <p className="text-sm text-slate-500">
          {loading ? t('inbox:lade') : t('inbox:kopf', { count: mails.length, antwortzeit: stats.avg != null ? t('inbox:stunden', { wert: stats.avg }) : '–', offen: stats.needsReply })}
        </p>
      </div>

      {stats.ohneStelle > 0 && (
        <button onClick={() => setOnlyOhneStelle((v) => !v)}
                className={`rounded-xl border p-3 text-left shadow-sm transition ${onlyOhneStelle ? 'border-amber-400 bg-amber-50' : 'border-amber-200 bg-amber-50/50 hover:bg-amber-50'}`}>
          <span className="text-xs font-medium uppercase tracking-wide text-amber-700">{t('inbox:ohne_stelle')}</span>
          <p className="text-lg font-bold text-amber-800">{stats.ohneStelle}</p>
          <span className="text-xs text-amber-600">{onlyOhneStelle ? t('inbox:filter_aktiv') : t('inbox:filter_hinweis')}</span>
        </button>
      )}

      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <select value={cat} onChange={(e) => setCat(e.target.value)} className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm">
          <option value="">{t('inbox:alle_kategorien')}</option>
          {Object.keys(CAT_STYLE).map((c) => <option key={c} value={c}>{wert('mail_kategorie', c)} {stats.byCat[c] ? `(${stats.byCat[c]})` : ''}</option>)}
        </select>
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          <input type="checkbox" checked={onlyReply} onChange={(e) => setOnlyReply(e.target.checked)} /> {t('inbox:nur_zu_beantworten')}
        </label>
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          <input type="checkbox" checked={onlyOhneStelle} onChange={(e) => setOnlyOhneStelle(e.target.checked)} /> {t('inbox:nur_ohne_stelle')}
        </label>
      </div>

      {archivFehler && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{archivFehler}</div>
      )}

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">{t('inbox:spalte.kategorie')}</th>
              <th className="px-3 py-2">{t('inbox:spalte.betreff')}</th>
              <th className="px-3 py-2">{t('inbox:spalte.firma_stelle')}</th>
              <th className="px-3 py-2">{t('inbox:spalte.von')}</th>
              <th className="px-3 py-2">{t('inbox:spalte.empfangen')}</th>
              <th className="px-3 py-2 text-right">{t('inbox:spalte.antwortzeit')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr><td colSpan={6} className="px-3 py-8 text-center text-slate-400">{t('inbox:lade')}</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={6} className="px-3 py-8 text-center text-slate-400">{t('inbox:keine_mails')}</td></tr>
            ) : filtered.map((m) => {
              const isOpen = open === m.id
              return (
                <Fragment key={m.id}>
                  <tr onClick={() => setOpen(isOpen ? null : m.id)}
                      className={`cursor-pointer align-top hover:bg-brand-cyan/5 ${isOpen ? 'bg-brand-cyan/5' : ''}`}>
                    <td className="px-3 py-2 whitespace-nowrap">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${CAT_STYLE[m.category] || 'bg-slate-100'}`}>{wert('mail_kategorie', m.category)}</span>
                      {m.needs_reply && <span className="ml-1 rounded-full bg-amber-500 px-1.5 py-0.5 text-[10px] font-bold text-white">{t('inbox:badge_reply')}</span>}
                      {m.reply_draft_at && <span className="ml-1 rounded-full bg-slate-200 px-1.5 py-0.5 text-[10px] font-bold text-slate-600" title={t('inbox:entwurf_seit', { datum: fmt(m.reply_draft_at) })}>{t('inbox:badge_entwurf')}</span>}
                    </td>
                    <td className="px-3 py-2 text-slate-700">
                      <span className="mr-1 text-slate-400">{m.direction === 'outgoing' ? '↗' : '↙'}</span>{m.subject}
                    </td>
                    <td className="px-3 py-2">
                      {m.job_id
                        ? <Link to={`/jobs/${m.job_id}`} onClick={(e) => e.stopPropagation()} className="font-medium text-brand-navy hover:underline">{m.company_name}</Link>
                        : m.ohne_stelle
                          ? (
                            <div>
                              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">{t('inbox:ohne_stelle')}</span>
                              <button onClick={(e) => { e.stopPropagation(); archivieren(m.id) }} disabled={archivBusyId === m.id}
                                      className="mt-1 block text-xs text-slate-400 hover:text-slate-700 disabled:opacity-40">
                                {t('inbox:archivieren')}
                              </button>
                            </div>
                          )
                          : <span className="font-medium text-brand-navy">{m.company_name || '–'}</span>}
                      {m.job_title && <div className="text-xs text-slate-400">{m.job_title}</div>}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-500">{m.from_addr}</td>
                    <td className="px-3 py-2 whitespace-nowrap text-slate-500">{fmt(m.received_at)}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-slate-600">{m.response_time_hours != null ? t('inbox:stunden', { wert: m.response_time_hours }) : '–'}</td>
                  </tr>
                  {isOpen && (
                    <tr>
                      <td colSpan={6} className="p-0">
                        <EmailDetail email={m} jobId={m.job_id || undefined} onChanged={neuLaden} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>

      <ArchivPanel signal={archivStand} onRestored={load} />
    </div>
  )
}
