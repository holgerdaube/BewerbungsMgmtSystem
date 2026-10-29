import { useEffect, useState } from 'react'
import { api, type BudgetProvider, type BudgetReport } from '../api'
import { Section, Stat, BarList } from '../components/ui'

const STATUS_STIL: Record<string, string> = {
  ok: 'bg-emerald-100 text-emerald-800',
  warn: 'bg-amber-100 text-amber-800',
  over: 'bg-rose-100 text-rose-700',
  pausiert: 'bg-slate-100 text-slate-500',
}
const STATUS_TEXT: Record<string, string> = {
  ok: 'im Rahmen', warn: '⚠ ≥ 80 %', over: 'über Limit', pausiert: 'pausiert',
}
const BALKEN: Record<string, string> = {
  ok: 'bg-emerald-400', warn: 'bg-amber-400', over: 'bg-rose-400', pausiert: 'bg-slate-300',
}

const eur = (n: number) => `${n.toFixed(2)} €`
const usd = (n: number) => `$${n.toFixed(n < 1 ? 4 : 2)}`

/** Fortschrittsbalken „0.32 $ / 0.50 $ heute · Rest 0.18 $". Ohne Limit: nichts anzeigen. */
function Balken({ label, verbraucht, limit, rest, status }: {
  label: string; verbraucht: number; limit: number | null; rest: number | null; status: string
}) {
  if (limit == null) return <div className="text-xs text-slate-400">{label}: kein Limit gesetzt</div>
  const prozent = Math.min(100, (verbraucht / limit) * 100)
  return (
    <div>
      <div className="flex justify-between text-xs text-slate-500">
        <span>{label}</span>
        <span className="tabular-nums">
          {usd(verbraucht)} / {usd(limit)}{rest != null && <> · Rest {usd(rest)}</>}
        </span>
      </div>
      <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full rounded-full ${BALKEN[status] || 'bg-slate-300'}`} style={{ width: `${prozent}%` }} />
      </div>
    </div>
  )
}

/** Eine Steuerungs-Karte je Verbrauchs-Dienst. Speichern nur wenn geändert (Muster: JobDetail). */
function SteuerKarte({ p, onSaved }: { p: BudgetProvider; onSaved: () => void }) {
  const l = p.limit!
  const istClaude = p.provider === 'claude-runs'
  const [tag, setTag] = useState<string>(l.daily_limit_usd?.toString() ?? '')
  const [monat, setMonat] = useState<string>(l.monthly_limit_usd?.toString() ?? '')
  const [modus, setModus] = useState<'hart' | 'weich'>(l.enforcement)
  const [aktiv, setAktiv] = useState(l.active)
  const [laeufe, setLaeufe] = useState<string>(l.max_runs_per_day?.toString() ?? '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [ok, setOk] = useState(false)

  const dirty = tag !== (l.daily_limit_usd?.toString() ?? '') ||
    monat !== (l.monthly_limit_usd?.toString() ?? '') ||
    modus !== l.enforcement || aktiv !== l.active ||
    (istClaude && laeufe !== (l.max_runs_per_day?.toString() ?? ''))

  const speichern = async () => {
    setBusy(true); setErr(null); setOk(false)
    try {
      await api(`/budget/limits/${p.provider}`, {
        method: 'PATCH',
        body: JSON.stringify({
          daily_limit_usd: tag === '' ? null : Number(tag),
          monthly_limit_usd: monat === '' ? null : Number(monat),
          enforcement: modus, active: aktiv,
          ...(istClaude ? { max_runs_per_day: laeufe === '' ? null : Number(laeufe) } : {}),
        }),
      })
      setOk(true); setTimeout(() => setOk(false), 3000)
      onSaved()
    } catch (e: any) {
      setErr(e?.message || 'Speichern fehlgeschlagen')
    } finally { setBusy(false) }
  }

  return (
    <div className={`rounded-xl border border-slate-200 p-4 ${aktiv ? '' : 'bg-slate-50 opacity-70'}`}>
      <div className="flex items-center justify-between">
        <div className="font-medium text-brand-navy">{p.label}</div>
        <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-600">
          <input type="checkbox" checked={aktiv} onChange={(e) => setAktiv(e.target.checked)}
            className="h-4 w-4 rounded border-slate-300 accent-brand-cyan" />
          Dienst aktiv
        </label>
      </div>
      {p.hinweis && <p className="mt-0.5 text-xs text-slate-400">{p.hinweis}</p>}

      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="text-xs text-slate-500">
          Tageslimit ($)
          <input type="number" min="0" step="0.5" value={tag} onChange={(e) => setTag(e.target.value)}
            placeholder="kein Limit"
            className="mt-1 block w-28 rounded-lg border border-slate-300 px-2 py-1 text-sm text-brand-navy" />
        </label>
        <label className="text-xs text-slate-500">
          Monatslimit ($)
          <input type="number" min="0" step="0.5" value={monat} onChange={(e) => setMonat(e.target.value)}
            placeholder="kein Limit"
            className="mt-1 block w-28 rounded-lg border border-slate-300 px-2 py-1 text-sm text-brand-navy" />
        </label>
        {istClaude && (
          <label className="text-xs text-slate-500">
            Max. Läufe/Tag
            <input type="number" min="0" step="1" value={laeufe} onChange={(e) => setLaeufe(e.target.value)}
              placeholder="100"
              className="mt-1 block w-24 rounded-lg border border-slate-300 px-2 py-1 text-sm text-brand-navy" />
          </label>
        )}
        <div className="flex gap-1">
          {(['hart', 'weich'] as const).map((m) => (
            <button key={m} onClick={() => setModus(m)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                modus === m ? 'bg-brand-cyan text-brand-aufAktion hover:bg-brand-cyanHover' : 'border border-slate-300 text-slate-600 hover:bg-slate-50'}`}>
              {m}
            </button>
          ))}
        </div>
      </div>
      <p className="mt-1 text-xs text-slate-400">hart = Aufrufe werden blockiert · weich = nur Warnung</p>

      <div className="mt-3 space-y-2">
        <Balken label="Heute" verbraucht={p.heute_usd} limit={l.daily_limit_usd} rest={l.rest_heute_usd} status={l.status} />
        <Balken label="Monat" verbraucht={p.monat_usd} limit={l.monthly_limit_usd} rest={l.rest_monat_usd} status={l.status} />
        {istClaude && p.runs_heute != null && (
          <p className="text-xs text-slate-400">{p.runs_heute} Läufe heute</p>
        )}
      </div>

      <div className="mt-3 flex items-center gap-3">
        <button onClick={speichern} disabled={!dirty || busy}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-semibold text-brand-aufAktion transition hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {busy ? 'Speichert…' : 'Speichern'}
        </button>
        {ok && <span className="text-xs font-medium text-emerald-600">✓ Gespeichert</span>}
        {err && <span className="text-xs text-rose-600">{err}</span>}
      </div>
    </div>
  )
}

export default function Budget() {
  const [d, setD] = useState<BudgetReport | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)

  const load = () => api<BudgetReport>('/budget').then(setD).catch(() => {})
  useEffect(() => { load() }, [])

  const sync = async () => {
    setSyncing(true); setSyncMsg(null)
    try {
      const r = await api<any>('/budget/sync', { method: 'POST' })
      setSyncMsg(r.ok ? `✓ ${r.rows} Tage übernommen` : `⚠ ${r.fehler}`)
      load()
    } catch (e: any) {
      setSyncMsg(`⚠ ${e?.message || 'Sync fehlgeschlagen'}`)
    } finally { setSyncing(false) }
  }

  if (!d) return <div className="text-slate-400">Lade…</div>

  const verbrauch = d.providers.filter((p) => p.art === 'verbrauch' && p.limit)
  const monatsverlauf: Record<string, number> = {}
  d.providers.forEach((p) => { if (p.monat_eur > 0) monatsverlauf[p.label] = p.monat_eur })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-brand-navy">Budget & API-Kosten</h1>
          <p className="text-sm text-slate-500">
            Letzter Sync: {d.letzter_sync ? new Date(d.letzter_sync).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : 'nie'}
            {syncMsg && <span className="ml-2 text-slate-600">{syncMsg}</span>}
          </p>
        </div>
        <button onClick={sync} disabled={syncing}
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-brand-navy transition hover:bg-slate-50 disabled:opacity-50">
          {syncing ? 'Synct…' : '🔄 Verbrauch syncen'}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Heute" value={eur(d.totals.heute_eur)} sub={usd(d.totals.heute_usd)} />
        <Stat label="Dieser Monat" value={eur(d.totals.monat_eur)} sub={usd(d.totals.monat_usd)} accent />
        <Stat label="Jahres-Prognose" value={eur(d.totals.jahr_prognose_eur)} sub="geschätzt" />
        <Stat label="Fixkosten / Monat" value={eur(d.totals.fix_monat_eur)} sub={usd(d.totals.fix_monat_usd)} />
      </div>

      <Section title="Dienste">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
              <tr className="border-b border-slate-100">
                <th className="px-4 py-2">Dienst</th><th className="px-4 py-2">Art</th>
                <th className="px-4 py-2 text-right">Heute</th><th className="px-4 py-2 text-right">Monat</th>
                <th className="px-4 py-2 text-right">Jahr (Prognose)</th><th className="px-4 py-2">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {d.providers.map((p) => (
                <tr key={p.provider} className="hover:bg-brand-cyan/5">
                  <td className="px-4 py-2 font-medium text-brand-navy" title={p.hinweis || undefined}>{p.label}</td>
                  <td className="px-4 py-2">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${p.art === 'abo' ? 'bg-indigo-100 text-indigo-800' : 'bg-slate-100 text-slate-600'}`}>
                      {p.art === 'abo' ? 'Abo' : 'Verbrauch'}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums text-slate-600">{eur(p.heute_eur)}</td>
                  <td className="px-4 py-2 text-right tabular-nums text-slate-600">{eur(p.monat_eur)}</td>
                  <td className="px-4 py-2 text-right tabular-nums text-slate-600">
                    {eur(p.jahr_prognose_eur)}{p.geschaetzt && <span className="text-slate-400"> ~</span>}
                  </td>
                  <td className="px-4 py-2">
                    {p.limit
                      ? <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STIL[p.limit.status]}`}>{STATUS_TEXT[p.limit.status]}</span>
                      : <span className="text-slate-400">–</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Budget-Steuerung">
        <div className="grid gap-4 p-4 md:grid-cols-2">
          {verbrauch.length === 0
            ? <div className="text-sm text-slate-400">Keine steuerbaren Dienste.</div>
            : verbrauch.map((p) => <SteuerKarte key={p.provider} p={p} onSaved={load} />)}
        </div>
      </Section>

      {Object.keys(monatsverlauf).length > 0 && (
        <BarList title="Kosten diesen Monat (EUR)" data={monatsverlauf} />
      )}

      <p className="text-xs text-slate-400">
        Verbrauch: Apify per API-Sync; Abos aus config/budgets.yaml.
        Limits wirken sofort auf alle kostenpflichtigen Aufrufe dieser App (hart = blockiert).
        Ausgaben außerhalb der App (Apify-Konsole, interaktive Claude-Sessions) sieht sie erst nach dem
        nächsten Sync und kann sie nicht verhindern. Kurs USD→EUR: {d.usd_eur_rate}.
      </p>
    </div>
  )
}
