import { useState } from 'react'
import { Trans } from 'react-i18next'
import { Link } from 'react-router-dom'
import { api } from '../api'
import AgentTaskButton from './AgentTaskButton'
import CopyTrigger from './CopyTrigger'
import { useKiAnbieter } from './ui'
import { t } from '../i18n'
import { datumZeit } from '../i18n/format'

/** Die Schritte der Kette `tageslauf` (RECIPES in backend/app/agent_runner.py).
 *  Dient zugleich als Beobachtungsliste (watchKinds) — fehlt hier ein Schritt, meldet der
 *  Button „fertig", während die Kette noch läuft: genau das passierte seit Phase 81 mit
 *  `coach-site` (Doku-Abgleich 12.08.2026). */
const SCHRITTE = ['jobsuche', 'mail-jobsuche', 'zielfirmen-sweep', 'headhunter-suche', 'beworben-check', 'email-check', 'absagen-analyse', 'views-refresh', 'coach-site']

export default function TageslaufButton() {
  const [open, setOpen] = useState(false)
  const [lastRun, setLastRun] = useState<any>(null)
  const [fallback, setFallback] = useState(false)
  const { name } = useKiAnbieter()

  const openModal = () => {
    setOpen(true)
    api<any[]>('/runs').then((r) => setLastRun(r[0] || null)).catch(() => {})
  }

  return (
    <>
      <button onClick={openModal} className="group mx-auto my-2 flex flex-col items-center gap-1" title={t('tasks:tageslauf.starten')}>
        <span className="flex h-14 w-14 items-center justify-center rounded-full bg-brand-cyan text-2xl shadow-lg shadow-brand-cyan/30 ring-2 ring-white/10 transition group-hover:scale-105 group-hover:brightness-90">
          ☀️
        </span>
        <span className="text-xs font-semibold text-brand-steel">{t('tasks:tageslauf.name')}</span>
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setOpen(false)}>
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2 text-lg font-bold text-brand-navy">☀️ {t('tasks:tageslauf.starten')}</div>
            <p className="mt-2 text-sm text-slate-600">
              <Trans i18nKey="tasks:tageslauf.schritte" components={{ b: <b /> }} />
            </p>

            <div className="mt-4">
              <AgentTaskButton kind="tageslauf" label={t('tasks:tageslauf.starten')} watchKinds={SCHRITTE} />
            </div>

            <p className="mt-2 text-xs text-slate-400">
              {t('tasks:tageslauf.hinweis')}
            </p>

            {lastRun && (
              <div className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
                <span className="font-medium text-slate-700">{t('tasks:tageslauf.letzter_lauf')}</span>{' '}
                {lastRun.started_at ? datumZeit(lastRun.started_at, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '–'}
                {lastRun.summary && <> · {lastRun.summary}</>}
              </div>
            )}

            <div className="mt-4 border-t border-slate-100 pt-3">
              <button onClick={() => setFallback((v) => !v)} className="text-xs text-slate-400 hover:text-slate-600">
                {fallback ? '▾' : '▸'} {t('tasks:tageslauf.lieber_session', { name })}
              </button>
              {fallback && (
                <div className="mt-2">
                  <CopyTrigger phrase={t('common:ausloeser.tageslauf')} label={t('tasks:tageslauf.ausloeser')} />
                </div>
              )}
            </div>

            <div className="mt-4 flex items-center justify-between">
              <Link to="/tasks" onClick={() => setOpen(false)} className="text-sm font-medium text-brand-cyan hover:underline">{t('tasks:tageslauf.task_center')}</Link>
              <div className="flex items-center gap-4">
                <Link to="/review" onClick={() => setOpen(false)} className="text-sm font-medium text-brand-cyan hover:underline">{t('tasks:tageslauf.treffer')}</Link>
                <button onClick={() => setOpen(false)} className="text-sm text-slate-500 hover:text-slate-700">{t('tasks:tageslauf.schliessen')}</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
