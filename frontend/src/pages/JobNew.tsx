import React, { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { isoTag } from '../zeit'
import { useSuchTabs } from '../suchbereich'

const PORTALE = ['LinkedIn', 'Indeed', 'StepStone', 'Xing', 'Firmenseite', 'Empfehlung', 'E-Mail', 'Headhunter', 'Sonstiges']
const MODELLE = ['', 'Remote', 'Hybrid', 'Onsite', 'Unbekannt']
const SENIOR = ['', 'VP', 'Senior Director', 'Director', 'Head', 'Senior Manager', 'Manager']
const STATI = ['Neu', 'Prüfen', 'Beworben']
const KANAELE = ['', 'Portal', 'E-Mail', 'Recruiter', 'Empfehlung']

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
    status: 'Prüfen', applied_date: today, channel: '', match_score: '', notes: params.get('notes') || '',
  })
  const set = (k: string, v: any) => setF((s: any) => ({ ...s, [k]: v }))
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [existing, setExisting] = useState<any>(null)

  const submit = async () => {
    setSaving(true); setErr(null); setExisting(null)
    try {
      const payload: any = { ...f }
      payload.match_score = f.match_score ? Number(f.match_score) : null
      if (f.status !== 'Beworben') { delete payload.applied_date; delete payload.channel }
      const r = await api<any>('/jobs', { method: 'POST', body: JSON.stringify(payload) })
      if (r.existing) setExisting(r.job)
      else nav(`/jobs/${r.job.id}`)
    } catch (e) {
      setErr(String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-3xl space-y-4">
      <Link to="/jobs" className="text-sm text-brand-cyan hover:underline">← Zurück zu Stellen</Link>
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">Neue Stelle anlegen</h1>
        <p className="text-sm text-slate-500">
          Manuell gefundene Stelle erfassen — <b>Neu</b> = landet in der Review-Liste ·
          <b> Prüfen</b> = direkt in die aktive Pipeline · <b>Beworben</b> = legt die Bewerbung gleich mit an.
        </p>
      </div>

      {existing && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800">
          <b>Schon vorhanden:</b> {existing.company_name} — {existing.title} ({existing.status}).{' '}
          <Link to={`/jobs/${existing.id}`} className="font-medium text-brand-cyan hover:underline">Zum bestehenden Job →</Link>
        </div>
      )}
      {err && <div className="rounded-xl border border-rose-300 bg-rose-50 p-4 text-sm text-rose-700">Fehler: {err}</div>}

      <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <Row label="Firma" required><input className={inputCls} value={f.company_name} onChange={(e) => set('company_name', e.target.value)} placeholder="z. B. Muster GmbH" /></Row>
          <Row label="Rollen-Titel" required><input className={inputCls} value={f.title} onChange={(e) => set('title', e.target.value)} placeholder="z. B. Head of Professional Services DACH" /></Row>
        </div>
        <Row label="Stellen-URL"><input className={inputCls} value={f.url} onChange={(e) => set('url', e.target.value)} placeholder="https://…" /></Row>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Row label="Portal / Quelle">
            <select className={inputCls} value={f.portal} onChange={(e) => set('portal', e.target.value)}>{PORTALE.map((p) => <option key={p}>{p}</option>)}</select>
          </Row>
          <Row label="Standort"><input className={inputCls} value={f.location} onChange={(e) => set('location', e.target.value)} placeholder="z. B. Köln oder Remote" /></Row>
          <Row label="Arbeitsmodell">
            <select className={inputCls} value={f.work_model} onChange={(e) => set('work_model', e.target.value)}>{MODELLE.map((m) => <option key={m} value={m}>{m || '–'}</option>)}</select>
          </Row>
          <Row label="Seniorität">
            <select className={inputCls} value={f.seniority} onChange={(e) => set('seniority', e.target.value)}>{SENIOR.map((s) => <option key={s} value={s}>{s || '–'}</option>)}</select>
          </Row>
          <Row label="Such-Tab">
            <select className={inputCls} value={f.tab} onChange={(e) => set('tab', e.target.value)}>
              <option value="">–</option>
              {suchTabs.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </Row>
          <Row label="Plan A/B/C">
            <select className={inputCls} value={f.plan_ab} onChange={(e) => set('plan_ab', e.target.value)}><option value="">–</option><option>A</option><option>B</option><option>C</option></select>
          </Row>
          <Row label="Gehalt (falls gelistet)"><input className={inputCls} value={f.salary} onChange={(e) => set('salary', e.target.value)} placeholder="z. B. 120–140k" /></Row>
          <Row label="Veröffentlicht am"><input type="date" className={inputCls} value={f.published_date} onChange={(e) => set('published_date', e.target.value)} /></Row>
          <Row label="Zielstellen-Fit (optional)">
            <select className={inputCls} value={f.match_score} onChange={(e) => set('match_score', e.target.value)}><option value="">– noch nicht bewertet –</option>{[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{n}/5</option>)}</select>
          </Row>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Row label="Status">
            <select className={inputCls} value={f.status} onChange={(e) => set('status', e.target.value)}>{STATI.map((s) => <option key={s}>{s}</option>)}</select>
          </Row>
          {f.status === 'Beworben' && (
            <>
              <Row label="Beworben am"><input type="date" className={inputCls} value={f.applied_date} onChange={(e) => set('applied_date', e.target.value)} /></Row>
              <Row label="Bewerbungs-Kanal">
                <select className={inputCls} value={f.channel} onChange={(e) => set('channel', e.target.value)}>{KANAELE.map((k) => <option key={k} value={k}>{k || '–'}</option>)}</select>
              </Row>
            </>
          )}
        </div>
        <Row label="Notizen"><textarea rows={3} className={inputCls} value={f.notes} onChange={(e) => set('notes', e.target.value)} placeholder="Woher der Tipp kommt, erste Einschätzung, Ansprechpartner…" /></Row>
        <div className="flex items-center gap-2 border-t border-slate-100 pt-4">
          <button onClick={submit} disabled={saving || !f.company_name.trim() || !f.title.trim()}
            className="rounded-lg bg-brand-cyan px-4 py-2 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
            {saving ? 'Speichern…' : '✓ Stelle anlegen'}
          </button>
          <button onClick={() => nav('/jobs')} className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">Abbrechen</button>
          <span className="ml-auto hidden text-xs text-slate-400 sm:block">Nach dem Anlegen: Job-Detail → „Unterlagen erstellen" startet den Workflow</span>
        </div>
      </div>
    </div>
  )
}
