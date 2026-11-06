import { useState } from 'react'
import { Trans } from 'react-i18next'
import { t } from '../i18n'
import { api } from '../api'
import BeiratLive from './BeiratLive'

/** Optionaler Baustein der Workflow-Karte (P2-41): startet den Beirats-
 *  Stellen-Check (POST /api/beirat/stellen-check) und zeigt währenddessen das kompakte
 *  Live-Panel (BeiratLive, geteilt mit /beirat). Der „fertig"-Zustand (Ampel/Score + Dashboard-
 *  Link) wird NICHT hier gehalten, sondern von JobDetail selbst aus der jüngsten
 *  Beirats-Check-JobFile-Row abgeleitet (Muster wie fitDa/cvDa/anschreibenDa) — dieselbe
 *  Quelle der Wahrheit wie bei den anderen Schritten, kein Duplikat-Zustand. */
export default function BeiratCheckButton({ jobId, onFinished, subtle, label }: {
  jobId: number
  onFinished?: () => void
  /** Re-Check-Variante (Schritt bereits fertig, Muster wie AgentTaskButton „neu erzeugen"). */
  subtle?: boolean
  label?: string
}) {
  const [debatteId, setDebatteId] = useState<string | null>(null)
  const [laeuft, setLaeuft] = useState(false)
  const [fortschritt, setFortschritt] = useState<{ nr: number; min: number; max: number } | null>(null)
  const [fehler, setFehler] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const start = async () => {
    setBusy(true); setFehler(null); setFortschritt(null)
    try {
      const r = await api<any>('/beirat/stellen-check', { method: 'POST', body: JSON.stringify({ job_id: jobId }) })
      setDebatteId(r.id); setLaeuft(true)
    } catch (e: any) {
      setFehler(e?.message || t('beirat:start_fehlgeschlagen'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2">
      <button onClick={start} disabled={busy || laeuft}
        className={subtle
          ? 'whitespace-nowrap rounded-lg border border-brand-cyan/40 px-3 py-1.5 text-xs font-medium text-brand-navy transition hover:bg-brand-cyan/10 disabled:cursor-not-allowed disabled:opacity-50'
          : 'w-full rounded-lg bg-brand-cyan px-3 py-2 text-sm font-semibold text-brand-aufAktion transition hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-50'}>
        {laeuft ? t('beirat:check.laeuft') : busy ? t('beirat:check.start') : (label || t('beirat:check.label'))}
      </button>
      {laeuft && fortschritt && (
        <div className="text-xs text-slate-500"><Trans i18nKey="beirat:fortschritt" values={{ nr: fortschritt.nr, min: fortschritt.min, max: fortschritt.max }} components={{ b: <b /> }} /></div>
      )}
      {debatteId && laeuft && (
        <BeiratLive
          debatteId={debatteId}
          compact
          onFortschritt={setFortschritt}
          onFertig={() => { setLaeuft(false); onFinished?.() }}
          onFehler={(m) => { setFehler(m); setLaeuft(false) }}
        />
      )}
      {fehler && <div className="rounded-lg bg-amber-50 p-2 text-xs text-amber-800">{fehler}</div>}
    </div>
  )
}
