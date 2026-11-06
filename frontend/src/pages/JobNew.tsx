import React, { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Trans } from 'react-i18next'
import { api } from '../api'
import { isoTag } from '../zeit'
import { useSuchTabs } from '../suchbereich'
import { SENIORITAETEN } from '../senioritaet'
import { t } from '../i18n'
import { wert } from '../i18n/werte'

const PORTALE = ['LinkedIn', 'Indeed', 'StepStone', 'Xing', 'Firmenseite', 'Empfehlung', 'E-Mail', 'Headhunter', 'Sonstiges']
const MODELLE = ['', 'Remote', 'Hybrid', 'Onsite', 'Unbekannt']
const SENIOR = ['', ...SENIORITAETEN]
const STATI = ['Neu', 'Prüfen', 'Beworben'] // i18n-ok: DB-Werte
const KANAELE = ['', 'Portal', 'E-Mail', 'Recruiter', 'Empfehlung']

// Auswahllisten: Die Werte bleiben deutsch (gehen so an die API), nur die Anzeige wird übersetzt.
const wertJobnew = (x: string): string => t(`jobnew:wert.${x}`, { defaultValue: x })
const modellLabel = (m: string): string => (m === 'Unbekannt' ? wertJobnew(m) : wert('work_model', m))

const inputCls = 'w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none'

function Row({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-slate-500">
        {label} {required && <span className="text-rose-500">*</span>}
      </label>
      {children}
    </div>
  )
}

export default function JobNew() {
  const nav = useNavigate()
  const [params] = useSearchParams()
  const today = isoTag()
  // P2-51: Umkreis-Tab dynamisch aus den Einstellungen statt fest „<Stadt> +100km".
  const suchTabs = useSuchTabs()
  const [f, setF] = useState<any>({
    company_name: params.get('company') || '', title: params.get('title') || '', url: '', portal: 'LinkedIn', location: '', work_model: '',
    seniority: '', tab: '', plan_ab: '', salary: '', published_date: '',
    status: 'Prüfen', applied_date: today, channel: '', match_score: '', notes: params.get('notes') || '', // i18n-ok: DB-Wert
  })
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [dublette, setDublette] = useState<{ art: string; job: any } | null>(null)
  const set = (k: string, v: any) => {
    setF((s: any) => ({ ...s, [k]: v }))
    if (k === 'url' || k === 'company_name' || k === 'title') setDublette(null)
  }

  // Warnt schon beim Verlassen des Felds. Nur ein Hinweis: Ein Fehler hier stört das Anlegen nicht,
  // das Speichern prüft ohnehin noch einmal.
  const dublettePruefen = async () => {
    const abfrage = new URLSearchParams({ url: f.url.trim(), company_name: f.company_name.trim(), title: f.title.trim() })
    try {
      const r = await api<any>(`/jobs/dublette?${abfrage}`)
      setDublette(r.job ? { art: r.art, job: r.job } : null)
    } catch { /* s. o. */ }
  }
  useEffect(() => { if (f.company_name && f.title) dublettePruefen() }, [])

  const submit = async () => {
    setSaving(true); setErr(null); setDublette(null)
    try {
      const payload: any = { ...f }
      payload.match_score = f.match_score ? Number(f.match_score) : null
      if (f.status !== 'Beworben') { delete payload.applied_date; delete payload.channel }
      const r = await api<any>('/jobs', { method: 'POST', body: JSON.stringify(payload) })
      if (r.existing) setDublette({ art: r.art, job: r.job })
      else nav(`/jobs/${r.job.id}`)
    } catch (e) {
      setErr(String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-3xl space-y-4">
      <Link to="/jobs" className="text-sm text-brand-cyan hover:underline">{t('jobnew:zurueck')}</Link>
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">{t('jobnew:titel')}</h1>
        <p className="text-sm text-slate-500">
          <Trans i18nKey="jobnew:untertitel" components={{ b: <b /> }} />
        </p>
      </div>

      {err && <div className="rounded-xl border border-rose-300 bg-rose-50 p-4 text-sm text-rose-700">{t('jobnew:fehler', { meldung: err })}</div>}

      <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <Row label={t('jobnew:feld.firma')} required><input className={inputCls} value={f.company_name} onChange={(e) => set('company_name', e.target.value)} onBlur={dublettePruefen} placeholder={t('jobnew:platzhalter.firma')} /></Row>
          <Row label={t('jobnew:feld.rollen_titel')} required><input className={inputCls} value={f.title} onChange={(e) => set('title', e.target.value)} onBlur={dublettePruefen} placeholder={t('jobnew:platzhalter.rollen_titel')} /></Row>
        </div>
        <Row label={t('jobnew:feld.url')}><input className={inputCls} value={f.url} onChange={(e) => set('url', e.target.value)} onBlur={dublettePruefen} placeholder={t('jobnew:platzhalter.url')} /></Row>
        {dublette && (
          <div role="alert" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
            <b>{dublette.art === 'url' ? t('jobnew:dublette.url') : t('jobnew:dublette.stelle')}</b>{' '}
            {dublette.job.company_name} — {dublette.job.title} ({wert('status', dublette.job.status)}).{' '}
            <Link to={`/jobs/${dublette.job.id}`} className="font-medium text-brand-cyan hover:underline">{t('jobnew:dublette.zur_stelle')}</Link>
          </div>
        )}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Row label={t('jobnew:feld.portal')}>
            <select className={inputCls} value={f.portal} onChange={(e) => set('portal', e.target.value)}>{PORTALE.map((p) => <option key={p} value={p}>{wertJobnew(p)}</option>)}</select>
          </Row>
          <Row label={t('jobnew:feld.standort')}><input className={inputCls} value={f.location} onChange={(e) => set('location', e.target.value)} placeholder={t('jobnew:platzhalter.standort')} /></Row>
          <Row label={t('jobnew:feld.arbeitsmodell')}>
            <select className={inputCls} value={f.work_model} onChange={(e) => set('work_model', e.target.value)}>{MODELLE.map((m) => <option key={m} value={m}>{m ? modellLabel(m) : '–'}</option>)}</select>
          </Row>
          <Row label={t('jobnew:feld.seniority')}>
            <select className={inputCls} value={f.seniority} onChange={(e) => set('seniority', e.target.value)}>{SENIOR.map((s) => <option key={s} value={s}>{s ? wert('seniority', s) : '–'}</option>)}</select>
          </Row>
          <Row label={t('jobnew:feld.such_tab')}>
            <select className={inputCls} value={f.tab} onChange={(e) => set('tab', e.target.value)}>
              <option value="">–</option>
              {suchTabs.map((s) => <option key={s} value={s}>{wert('tab', s)}</option>)}
            </select>
          </Row>
          <Row label={t('jobnew:feld.plan')}>
            <select className={inputCls} value={f.plan_ab} onChange={(e) => set('plan_ab', e.target.value)}><option value="">–</option><option>A</option><option>B</option><option>C</option></select>
          </Row>
          <Row label={t('jobnew:feld.gehalt')}><input className={inputCls} value={f.salary} onChange={(e) => set('salary', e.target.value)} placeholder={t('jobnew:platzhalter.gehalt')} /></Row>
          <Row label={t('jobnew:feld.veroeffentlicht')}><input type="date" className={inputCls} value={f.published_date} onChange={(e) => set('published_date', e.target.value)} /></Row>
          <Row label={t('jobnew:feld.fit')}>
            <select className={inputCls} value={f.match_score} onChange={(e) => set('match_score', e.target.value)}><option value="">{t('jobnew:fit_unbewertet')}</option>{[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{n}/5</option>)}</select>
          </Row>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Row label={t('jobnew:feld.status')}>
            <select className={inputCls} value={f.status} onChange={(e) => set('status', e.target.value)}>{STATI.map((s) => <option key={s} value={s}>{wert('status', s)}</option>)}</select>
          </Row>
          {f.status === 'Beworben' && (
            <>
              <Row label={t('jobnew:feld.beworben_am')}><input type="date" className={inputCls} value={f.applied_date} onChange={(e) => set('applied_date', e.target.value)} /></Row>
              <Row label={t('jobnew:feld.kanal')}>
                <select className={inputCls} value={f.channel} onChange={(e) => set('channel', e.target.value)}>{KANAELE.map((k) => <option key={k} value={k}>{k ? wertJobnew(k) : '–'}</option>)}</select>
              </Row>
            </>
          )}
        </div>
        <Row label={t('jobnew:feld.notizen')}><textarea rows={3} className={inputCls} value={f.notes} onChange={(e) => set('notes', e.target.value)} placeholder={t('jobnew:platzhalter.notizen')} /></Row>
        <div className="flex items-center gap-2 border-t border-slate-100 pt-4">
          <button onClick={submit} disabled={saving || !f.company_name.trim() || !f.title.trim()}
            className="rounded-lg bg-brand-cyan px-4 py-2 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
            {saving ? t('jobnew:speichern') : t('jobnew:anlegen')}
          </button>
          <button onClick={() => nav('/jobs')} className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">{t('jobnew:abbrechen')}</button>
          <span className="ml-auto hidden text-xs text-slate-400 sm:block">{t('jobnew:nach_anlegen')}</span>
        </div>
      </div>
    </div>
  )
}
