import { useEffect, useState } from 'react'
import { Listensuche, passtZurSuche } from '../components/Listensuche'
import { api } from '../api'
import { CopyChip, TEXT_AUF_ZUSTAND } from '../components/ui'
import NetzwerkGespraechForm from '../components/NetzwerkGespraechForm'
import NetzwerkImport, { NetzwerkImportKnopf } from '../components/NetzwerkImport'
import { isoTag, tagVon } from '../zeit'
import { t } from '../i18n'

type Col = { key: string; wide?: boolean }

const TABS: { id: string; path: string; cols: Col[] }[] = [
  {
    id: 'targets', path: '/target-companies',
    cols: [
      { key: 'company' }, { key: 'tier' }, { key: 'scenario' },
      { key: 'industry' }, { key: 'ownership' }, { key: 'location_hq' },
      { key: 'connection_status' }, { key: 'key_contact', wide: true },
      { key: 'wachstumssignal', wide: true },
      { key: '_aktion' },
    ],
  },
  {
    id: 'hh', path: '/headhunters',
    cols: [
      { key: 'firma' }, { key: 'source' }, { key: 'ansprechpartner' },
      { key: 'fokus' }, { key: 'webseite' },
      { key: 'letzter_kontakt' }, { key: 'status' },
      { key: 'notizen', wide: true },
    ],
  },
  {
    id: 'nc', path: '/network-contacts',
    cols: [
      { key: 'name' }, { key: 'unternehmen' }, { key: 'rolle' },
      { key: 'letzter_kontakt' }, { key: 'prioritaet' }, { key: 'notizen', wide: true },
    ],
  },
]

// Dashboard-Farbmodell V2 (Style Guide v5.0 §18) — Tier ist eine Bewertung (1 = Top-Priorität
// … 3 = niedrig), bekommt daher dieselbe Grün/Gold/Grau-Werteskala wie Zielstellen-Fit/Status
// (status.positive/parked/new), nur exakte Tokens statt der alten Pastell-Klassen.
function tierColor(tier: string | null): { bg: string; text: string } {
  if (!tier) return { bg: '#A8B4C4', text: TEXT_AUF_ZUSTAND } // ui.state.unknown — kein Tier gesetzt
  const d = String(tier).trim()[0]
  if (d === '1') return { bg: '#18A957', text: TEXT_AUF_ZUSTAND } // status.positive — Top-Priorität
  if (d === '2') return { bg: '#E4A11B', text: TEXT_AUF_ZUSTAND } // status.parked — mittlere Priorität
  return { bg: '#94A3B8', text: TEXT_AUF_ZUSTAND } // status.new — niedrige/sonstige Priorität
}

// Szenario ist eine reine Kategorie ohne positive/negative Bedeutung (kein Ranking) — bewusst
// die Kategorienpalette (18.6), NICHT die Situationsmodell-Farben: Zielfirmen-Szenario A/B/C
// ist ein anderes Konzept als die Suchprofil-Pläne A/B/C (Einstellungen) und darf farblich
// nicht danach aussehen, als wäre es dasselbe.
function scenarioColor(scenario: string | null): { bg: string; text: string } {
  const d = scenario ? String(scenario).trim()[0].toUpperCase() : ''
  if (d === 'A') return { bg: '#00B4D8', text: TEXT_AUF_ZUSTAND } // category.1 Cyan
  if (d === 'B') return { bg: '#5B61E6', text: '#ffffff' } // category.2 Indigo
  if (d === 'C') return { bg: '#7C4DFF', text: '#ffffff' } // category.3 Violet
  return { bg: '#A8B4C4', text: TEXT_AUF_ZUSTAND } // ui.state.unknown — kein Szenario gesetzt
}

/** Lange Webseiten-/Karriere-URL kürzen (Muster Job-Detail Original-URL, Phase 19). */
function shortUrl(u: string): string {
  try {
    const url = new URL(u)
    return url.hostname.replace(/^www\./, '')
  } catch {
    return u.length > 30 ? u.slice(0, 30) + '…' : u
  }
}

// ── Netzwerk-Kontakte: pflegbar (Phase 22) ──────────────────────────────────────
const NC_INPUT = 'rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none'
const KANAELE = ['LinkedIn', 'E-Mail', 'Telefon', 'Persönlich'] // i18n-ok: DB-Wert
const PRIOS = ['Hoch', 'Mittel', 'Niedrig']
// Sichtbar wird die Übersetzung, gespeichert und verglichen wird der deutsche DB-Wert.
const prioAnzeige = (p: string) => t(`netzwerk:wert.${p}`, { defaultValue: p })

// Nur für die Vorbefüllung des Formulars — maßgeblich bleibt der Backend-Default (Mo–Fr).
function ncPlusWerktage(n: number): string {
  const d = new Date()
  let added = 0
  while (added < n) { d.setDate(d.getDate() + 1); const wd = d.getDay(); if (wd !== 0 && wd !== 6) added++ }
  return isoTag(d)
}

const NC_FIELDS = ['name', 'beziehung', 'unternehmen', 'rolle', 'letzter_kontakt', 'kanal',
  'prioritaet', 'notizen', 'next_action', 'next_action_date']

function NcEdit({ item, onSaved }: { item: any; onSaved: () => void }) {
  const [f, setF] = useState<any>(() => Object.fromEntries(NC_FIELDS.map((k) => [k, item[k] || ''])))
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const set = (k: string, v: string) => setF((x: any) => ({ ...x, [k]: v }))
  const dirty = NC_FIELDS.some((k) => (f[k] || '') !== (item[k] || ''))
  const save = async () => {
    setSaving(true); setErr(null)
    try {
      const patch: any = {}
      NC_FIELDS.forEach((k) => { if ((f[k] || '') !== (item[k] || '')) patch[k] = f[k] || null })
      await api(`/network-contacts/${item.id}`, { method: 'PATCH', body: JSON.stringify(patch) })
      onSaved(); setSaved(true); setTimeout(() => setSaved(false), 2000)
    } catch (e: any) { setErr(e?.message || t('netzwerk:fehler.speichern')) }
    finally { setSaving(false) }
  }
  const remove = async () => {
    if (!window.confirm(t('netzwerk:loeschen_bestaetigung', { name: item.name }))) return
    await api(`/network-contacts/${item.id}`, { method: 'DELETE' })
    onSaved()
  }
  const Lab = (label: string, node: any) => <label className="flex flex-col text-xs text-slate-500">{label}<div className="mt-1">{node}</div></label>
  return (
    <div className="grid grid-cols-1 gap-3 bg-slate-50/70 px-4 py-4 md:grid-cols-2">
      {Lab(t('netzwerk:feld.name'), <input className={`${NC_INPUT} w-full`} value={f.name} onChange={(e) => set('name', e.target.value)} />)}
      {Lab(t('netzwerk:feld.unternehmen'), <input className={`${NC_INPUT} w-full`} value={f.unternehmen} onChange={(e) => set('unternehmen', e.target.value)} />)}
      {Lab(t('netzwerk:feld.rolle'), <input className={`${NC_INPUT} w-full`} value={f.rolle} onChange={(e) => set('rolle', e.target.value)} />)}
      {Lab(t('netzwerk:feld.beziehung'), <input className={`${NC_INPUT} w-full`} value={f.beziehung} onChange={(e) => set('beziehung', e.target.value)} />)}
      {Lab(t('netzwerk:feld.kanal'), <input list="nc-kanaele" className={`${NC_INPUT} w-full`} value={f.kanal} onChange={(e) => set('kanal', e.target.value)} />)}
      {Lab(t('netzwerk:feld.prioritaet'), <select className={`${NC_INPUT} w-full`} value={f.prioritaet} onChange={(e) => set('prioritaet', e.target.value)}><option value="">–</option>{PRIOS.map((p) => <option key={p} value={p}>{prioAnzeige(p)}</option>)}</select>)}
      {Lab(t('netzwerk:feld.letzter_kontakt'), <input type="date" className={`${NC_INPUT} w-full`} value={(f.letzter_kontakt || '').slice(0, 10)} onChange={(e) => set('letzter_kontakt', e.target.value)} />)}
      {Lab(t('netzwerk:feld.next_action'), <input className={`${NC_INPUT} w-full`} value={f.next_action} onChange={(e) => set('next_action', e.target.value)} />)}
      {Lab(t('netzwerk:feld.next_action_date'), <input type="date" className={`${NC_INPUT} w-full`} value={(f.next_action_date || '').slice(0, 10)} onChange={(e) => set('next_action_date', e.target.value)} />)}
      <div className="md:col-span-2">{Lab(t('netzwerk:feld.notizen'), <textarea className={`${NC_INPUT} w-full`} rows={2} value={f.notizen} onChange={(e) => set('notizen', e.target.value)} />)}</div>
      <div className="flex items-center gap-2 md:col-span-2">
        <button onClick={save} disabled={saving || !dirty} className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">{saving ? t('netzwerk:knopf.speichern_laeuft') : t('netzwerk:knopf.speichern')}</button>
        {saved && <span className="text-sm text-emerald-600">{t('netzwerk:knopf.gespeichert')}</span>}
        {err && <span className="text-sm text-rose-600">{err}</span>}
        <button onClick={remove} className="ml-auto rounded-lg border border-rose-200 px-3 py-1.5 text-sm font-medium text-rose-600 hover:bg-rose-50">{t('netzwerk:knopf.loeschen')}</button>
      </div>
    </div>
  )
}

function NcNew({ onCreated, onClose }: { onCreated: () => void; onClose: () => void }) {
  const [f, setF] = useState<any>({ name: '', unternehmen: '', rolle: '', beziehung: '', kanal: '', prioritaet: '', notizen: '', next_action: '', next_action_date: ncPlusWerktage(10) })
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const set = (k: string, v: string) => setF((x: any) => ({ ...x, [k]: v }))
  const save = async () => {
    if (!f.name.trim()) { setErr(t('netzwerk:fehler.name_pflicht')); return }
    setSaving(true); setErr(null)
    try {
      const body: any = {}
      Object.keys(f).forEach((k) => { if (f[k]) body[k] = f[k] })
      await api('/network-contacts', { method: 'POST', body: JSON.stringify(body) })
      onCreated(); onClose()
    } catch (e: any) { setErr(e?.message || t('netzwerk:fehler.anlegen')) }
    finally { setSaving(false) }
  }
  return (
    <div className="rounded-xl border border-brand-cyan/40 bg-brand-cyan/5 p-4">
      <div className="mb-2 text-sm font-semibold text-brand-navy">{t('netzwerk:nc.neu_titel')}</div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <input className={NC_INPUT} placeholder={t('netzwerk:platzhalter.name_pflicht')} value={f.name} onChange={(e) => set('name', e.target.value)} />
        <input className={NC_INPUT} placeholder={t('netzwerk:feld.unternehmen')} value={f.unternehmen} onChange={(e) => set('unternehmen', e.target.value)} />
        <input className={NC_INPUT} placeholder={t('netzwerk:feld.rolle')} value={f.rolle} onChange={(e) => set('rolle', e.target.value)} />
        <input className={NC_INPUT} placeholder={t('netzwerk:feld.beziehung')} value={f.beziehung} onChange={(e) => set('beziehung', e.target.value)} />
        <input list="nc-kanaele" className={NC_INPUT} placeholder={t('netzwerk:feld.kanal')} value={f.kanal} onChange={(e) => set('kanal', e.target.value)} />
        <select className={NC_INPUT} value={f.prioritaet} onChange={(e) => set('prioritaet', e.target.value)}><option value="">{t('netzwerk:platzhalter.prioritaet')}</option>{PRIOS.map((p) => <option key={p} value={p}>{prioAnzeige(p)}</option>)}</select>
        <input className={NC_INPUT} placeholder={t('netzwerk:feld.next_action')} value={f.next_action} onChange={(e) => set('next_action', e.target.value)} />
        <label className="flex flex-col text-xs text-slate-500">{t('netzwerk:form.faellig_default')}<input type="date" className={`${NC_INPUT} mt-1`} value={f.next_action_date} onChange={(e) => set('next_action_date', e.target.value)} /></label>
        <textarea className={`${NC_INPUT} md:col-span-3`} rows={2} placeholder={t('netzwerk:feld.notizen')} value={f.notizen} onChange={(e) => set('notizen', e.target.value)} />
      </div>
      <div className="mt-2 flex items-center gap-2">
        <button onClick={save} disabled={saving} className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:opacity-40">{saving ? t('netzwerk:knopf.anlegen_laeuft') : t('netzwerk:knopf.anlegen')}</button>
        <button onClick={onClose} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">{t('netzwerk:knopf.abbrechen')}</button>
        {err && <span className="text-sm text-rose-600">{err}</span>}
      </div>
    </div>
  )
}

// ── Zielfirmen: „+ Zielfirma anlegen" (Phase 24 B) ──────────────────────────────
const TC_INPUT = 'rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none'
const TC_TIERS = ['1', '2', '3']
const TC_SZENARIEN = ['A', 'B', 'C']

function TargetNew({ onCreated, onClose }: { onCreated: () => void; onClose: () => void }) {
  const [f, setF] = useState<any>({
    company: '', industry: '', tier: '', scenario: '', ownership: '', location_hq: '',
    connection_status: t('netzwerk:wert.Offen'), key_contact: '', website: '', einschaetzung: '',
  })
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const set = (k: string, v: string) => setF((x: any) => ({ ...x, [k]: v }))
  const save = async () => {
    if (!f.company.trim()) { setErr(t('netzwerk:fehler.firma_pflicht')); return }
    setSaving(true); setErr(null)
    try {
      const body: any = {}
      Object.keys(f).forEach((k) => { if (f[k]) body[k] = f[k] })
      await api('/target-companies', { method: 'POST', body: JSON.stringify(body) })
      onCreated(); onClose()
    } catch (e: any) { setErr(e?.message || t('netzwerk:fehler.anlegen')) }
    finally { setSaving(false) }
  }
  return (
    <div className="rounded-xl border border-brand-cyan/40 bg-brand-cyan/5 p-4">
      <div className="mb-2 text-sm font-semibold text-brand-navy">{t('netzwerk:tc.neu_titel')}</div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <input className={TC_INPUT} placeholder={t('netzwerk:platzhalter.firma_pflicht')} value={f.company} onChange={(e) => set('company', e.target.value)} />
        <input className={TC_INPUT} placeholder={t('netzwerk:feld.industry')} value={f.industry} onChange={(e) => set('industry', e.target.value)} />
        <select className={TC_INPUT} value={f.tier} onChange={(e) => set('tier', e.target.value)}>
          <option value="">{t('netzwerk:platzhalter.tier')}</option>{TC_TIERS.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select className={TC_INPUT} value={f.scenario} onChange={(e) => set('scenario', e.target.value)}>
          <option value="">{t('netzwerk:platzhalter.szenario')}</option>{TC_SZENARIEN.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <input className={TC_INPUT} placeholder={t('netzwerk:feld.ownership')} value={f.ownership} onChange={(e) => set('ownership', e.target.value)} />
        <input className={TC_INPUT} placeholder={t('netzwerk:feld.location_hq')} value={f.location_hq} onChange={(e) => set('location_hq', e.target.value)} />
        <input className={TC_INPUT} placeholder={t('netzwerk:feld.status')} value={f.connection_status} onChange={(e) => set('connection_status', e.target.value)} />
        <input className={TC_INPUT} placeholder={t('netzwerk:feld.key_contact')} value={f.key_contact} onChange={(e) => set('key_contact', e.target.value)} />
        <input className={TC_INPUT} placeholder={t('netzwerk:form.website')} value={f.website} onChange={(e) => set('website', e.target.value)} />
        <textarea className={`${TC_INPUT} md:col-span-3`} rows={2} placeholder={t('netzwerk:feld.einschaetzung')} value={f.einschaetzung} onChange={(e) => set('einschaetzung', e.target.value)} />
      </div>
      <div className="mt-2 flex items-center gap-2">
        <button onClick={save} disabled={saving} className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:opacity-40">{saving ? t('netzwerk:knopf.anlegen_laeuft') : t('netzwerk:knopf.anlegen')}</button>
        <button onClick={onClose} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">{t('netzwerk:knopf.abbrechen')}</button>
        {err && <span className="text-sm text-rose-600">{err}</span>}
      </div>
    </div>
  )
}

// ── Headhunter: „+ Headhunter anlegen" (Phase 24 C) ──────────────────────────────
function HeadhunterNew({ onCreated, onClose }: { onCreated: () => void; onClose: () => void }) {
  const [f, setF] = useState<any>({
    firma: '', ansprechpartner: '', fokus: '', region: '', kanal: '', letzter_kontakt: '',
    status: '', webseite: '', notizen: '',
  })
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const set = (k: string, v: string) => setF((x: any) => ({ ...x, [k]: v }))
  const save = async () => {
    if (!f.firma.trim()) { setErr(t('netzwerk:fehler.firma_pflicht')); return }
    setSaving(true); setErr(null)
    try {
      const body: any = {}
      Object.keys(f).forEach((k) => { if (f[k]) body[k] = f[k] })
      await api('/headhunters', { method: 'POST', body: JSON.stringify(body) })
      onCreated(); onClose()
    } catch (e: any) { setErr(e?.message || t('netzwerk:fehler.anlegen')) }
    finally { setSaving(false) }
  }
  return (
    <div className="rounded-xl border border-brand-cyan/40 bg-brand-cyan/5 p-4">
      {/* P2-61: Der Hinweis auf /outreach fiel weg. Dort entsteht nichts mehr (Outreach ist eine
          einmalige Übernahme), und beim Kunden gibt es die Seite im Menü nicht. */}
      <div className="mb-2 text-sm font-semibold text-brand-navy">{t('netzwerk:hh.neu_titel')}</div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <input className={TC_INPUT} placeholder={t('netzwerk:platzhalter.firma_pflicht')} value={f.firma} onChange={(e) => set('firma', e.target.value)} />
        <input className={TC_INPUT} placeholder={t('netzwerk:feld.ansprechpartner')} value={f.ansprechpartner} onChange={(e) => set('ansprechpartner', e.target.value)} />
        <input className={TC_INPUT} placeholder={t('netzwerk:feld.fokus')} value={f.fokus} onChange={(e) => set('fokus', e.target.value)} />
        <input className={TC_INPUT} placeholder={t('netzwerk:feld.region')} value={f.region} onChange={(e) => set('region', e.target.value)} />
        <input className={TC_INPUT} placeholder={t('netzwerk:feld.kanal')} value={f.kanal} onChange={(e) => set('kanal', e.target.value)} />
        <input type="date" className={TC_INPUT} value={f.letzter_kontakt} onChange={(e) => set('letzter_kontakt', e.target.value)} />
        <input className={TC_INPUT} placeholder={t('netzwerk:feld.status')} value={f.status} onChange={(e) => set('status', e.target.value)} />
        <input className={TC_INPUT} placeholder={t('netzwerk:platzhalter.webseite_hh')} value={f.webseite} onChange={(e) => set('webseite', e.target.value)} />
        <textarea className={`${TC_INPUT} md:col-span-3`} rows={2} placeholder={t('netzwerk:feld.notizen')} value={f.notizen} onChange={(e) => set('notizen', e.target.value)} />
      </div>
      <div className="mt-2 flex items-center gap-2">
        <button onClick={save} disabled={saving} className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:opacity-40">{saving ? t('netzwerk:knopf.anlegen_laeuft') : t('netzwerk:knopf.anlegen')}</button>
        <button onClick={onClose} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">{t('netzwerk:knopf.abbrechen')}</button>
        {err && <span className="text-sm text-rose-600">{err}</span>}
      </div>
    </div>
  )
}

// ── Zielfirmen: volles Zeilen-Edit (Phase 26 B, Muster NcEdit) ──────────────────
const TC_EDIT_FIELDS = ['company', 'industry', 'size_ma', 'revenue', 'tier', 'scenario',
  'ownership', 'location_hq', 'connection_status', 'key_contact', 'website', 'einschaetzung']

function TargetEdit({ item, onSaved }: { item: any; onSaved: () => void }) {
  const [f, setF] = useState<any>(() => Object.fromEntries(TC_EDIT_FIELDS.map((k) => [k, item[k] || ''])))
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const set = (k: string, v: string) => setF((x: any) => ({ ...x, [k]: v }))
  const dirty = TC_EDIT_FIELDS.some((k) => (f[k] || '') !== (item[k] || ''))
  const save = async () => {
    setSaving(true); setErr(null)
    try {
      const patch: any = {}
      TC_EDIT_FIELDS.forEach((k) => { if ((f[k] || '') !== (item[k] || '')) patch[k] = f[k] || null })
      await api(`/target-companies/${item.id}`, { method: 'PATCH', body: JSON.stringify(patch) })
      onSaved(); setSaved(true); setTimeout(() => setSaved(false), 2000)
    } catch (e: any) { setErr(e?.message || t('netzwerk:fehler.speichern')) }
    finally { setSaving(false) }
  }
  const remove = async () => {
    if (!window.confirm(t('netzwerk:loeschen_bestaetigung', { name: item.company }))) return
    await api(`/target-companies/${item.id}`, { method: 'DELETE' })
    onSaved()
  }
  const Lab = (label: string, node: any) => <label className="flex flex-col text-xs text-slate-500">{label}<div className="mt-1">{node}</div></label>
  return (
    <div className="grid grid-cols-1 gap-3 bg-slate-50/70 px-4 py-4 md:grid-cols-3">
      {Lab(t('netzwerk:feld.company'), <input className={`${TC_INPUT} w-full`} value={f.company} onChange={(e) => set('company', e.target.value)} />)}
      {Lab(t('netzwerk:feld.industry'), <input className={`${TC_INPUT} w-full`} value={f.industry} onChange={(e) => set('industry', e.target.value)} />)}
      {Lab(t('netzwerk:form.groesse'), <input className={`${TC_INPUT} w-full`} value={f.size_ma} onChange={(e) => set('size_ma', e.target.value)} />)}
      {Lab(t('netzwerk:feld.revenue'), <input className={`${TC_INPUT} w-full`} value={f.revenue} onChange={(e) => set('revenue', e.target.value)} />)}
      {Lab(t('netzwerk:feld.tier'), <select className={`${TC_INPUT} w-full`} value={f.tier} onChange={(e) => set('tier', e.target.value)}><option value="">–</option>{TC_TIERS.map((t) => <option key={t} value={t}>{t}</option>)}</select>)}
      {Lab(t('netzwerk:feld.scenario'), <select className={`${TC_INPUT} w-full`} value={f.scenario} onChange={(e) => set('scenario', e.target.value)}><option value="">–</option>{TC_SZENARIEN.map((s) => <option key={s} value={s}>{s}</option>)}</select>)}
      {Lab(t('netzwerk:feld.ownership'), <input className={`${TC_INPUT} w-full`} value={f.ownership} onChange={(e) => set('ownership', e.target.value)} />)}
      {Lab(t('netzwerk:feld.location_hq'), <input className={`${TC_INPUT} w-full`} value={f.location_hq} onChange={(e) => set('location_hq', e.target.value)} />)}
      {Lab(t('netzwerk:feld.connection_status'), <input className={`${TC_INPUT} w-full`} value={f.connection_status} onChange={(e) => set('connection_status', e.target.value)} />)}
      {Lab(t('netzwerk:feld.key_contact'), <input className={`${TC_INPUT} w-full`} value={f.key_contact} onChange={(e) => set('key_contact', e.target.value)} />)}
      {Lab(t('netzwerk:form.website'), <input className={`${TC_INPUT} w-full`} value={f.website} onChange={(e) => set('website', e.target.value)} />)}
      <div className="md:col-span-3">{Lab(t('netzwerk:feld.einschaetzung'), <textarea className={`${TC_INPUT} w-full`} rows={2} value={f.einschaetzung} onChange={(e) => set('einschaetzung', e.target.value)} />)}</div>
      {item.last_career_check && (
        <div className="text-xs text-slate-400 md:col-span-3">
          {t('netzwerk:karriere.pruefung', { datum: item.last_career_check.slice(0, 10) })}{item.karriere_url && <> · <a href={item.karriere_url} target="_blank" rel="noreferrer" className="text-brand-cyan hover:underline">{shortUrl(item.karriere_url)}</a></>}
          {' '}{t('netzwerk:karriere.zielfirmen_sweep')}
        </div>
      )}
      <div className="flex items-center gap-2 md:col-span-3">
        <button onClick={save} disabled={saving || !dirty} className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">{saving ? t('netzwerk:knopf.speichern_laeuft') : t('netzwerk:knopf.speichern')}</button>
        {saved && <span className="text-sm text-emerald-600">{t('netzwerk:knopf.gespeichert')}</span>}
        {err && <span className="text-sm text-rose-600">{err}</span>}
        <button onClick={remove} className="ml-auto rounded-lg border border-rose-200 px-3 py-1.5 text-sm font-medium text-rose-600 hover:bg-rose-50">{t('netzwerk:knopf.loeschen')}</button>
      </div>
    </div>
  )
}

// ── Headhunter: volles Zeilen-Edit (Phase 26 A, Muster NcEdit) — nur Blatt-Zeilen ─
const HH_EDIT_FIELDS = ['firma', 'ansprechpartner', 'fokus', 'region', 'kanal', 'letzter_kontakt', 'status', 'notizen', 'webseite']

function HeadhunterEdit({ item, onSaved }: { item: any; onSaved: () => void }) {
  const [f, setF] = useState<any>(() => Object.fromEntries(HH_EDIT_FIELDS.map((k) => [k, item[k] || ''])))
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const set = (k: string, v: string) => setF((x: any) => ({ ...x, [k]: v }))
  const dirty = HH_EDIT_FIELDS.some((k) => (f[k] || '') !== (item[k] || ''))
  const save = async () => {
    setSaving(true); setErr(null)
    try {
      const patch: any = {}
      HH_EDIT_FIELDS.forEach((k) => { if ((f[k] || '') !== (item[k] || '')) patch[k] = f[k] || null })
      await api(`/headhunters/${item.real_id}`, { method: 'PATCH', body: JSON.stringify(patch) })
      onSaved(); setSaved(true); setTimeout(() => setSaved(false), 2000)
    } catch (e: any) { setErr(e?.message || t('netzwerk:fehler.speichern')) }
    finally { setSaving(false) }
  }
  const remove = async () => {
    if (!window.confirm(t('netzwerk:loeschen_bestaetigung', { name: item.firma }))) return
    await api(`/headhunters/${item.real_id}`, { method: 'DELETE' })
    onSaved()
  }
  const Lab = (label: string, node: any) => <label className="flex flex-col text-xs text-slate-500">{label}<div className="mt-1">{node}</div></label>
  return (
    <div className="grid grid-cols-1 gap-3 bg-slate-50/70 px-4 py-4 md:grid-cols-3">
      {Lab(t('netzwerk:feld.firma'), <input className={`${TC_INPUT} w-full`} value={f.firma} onChange={(e) => set('firma', e.target.value)} />)}
      {Lab(t('netzwerk:feld.ansprechpartner'), <input className={`${TC_INPUT} w-full`} value={f.ansprechpartner} onChange={(e) => set('ansprechpartner', e.target.value)} />)}
      {Lab(t('netzwerk:feld.fokus'), <input className={`${TC_INPUT} w-full`} value={f.fokus} onChange={(e) => set('fokus', e.target.value)} />)}
      {Lab(t('netzwerk:feld.region'), <input className={`${TC_INPUT} w-full`} value={f.region} onChange={(e) => set('region', e.target.value)} />)}
      {Lab(t('netzwerk:feld.kanal'), <input className={`${TC_INPUT} w-full`} value={f.kanal} onChange={(e) => set('kanal', e.target.value)} />)}
      {Lab(t('netzwerk:feld.letzter_kontakt'), <input type="date" className={`${TC_INPUT} w-full`} value={(f.letzter_kontakt || '').slice(0, 10)} onChange={(e) => set('letzter_kontakt', e.target.value)} />)}
      {Lab(t('netzwerk:feld.status'), <input className={`${TC_INPUT} w-full`} value={f.status} onChange={(e) => set('status', e.target.value)} />)}
      {Lab(t('netzwerk:feld.webseite'), <input className={`${TC_INPUT} w-full`} placeholder="https://…" value={f.webseite} onChange={(e) => set('webseite', e.target.value)} />)}{/* i18n-ok: URL-Muster */}
      <div className="md:col-span-3">{Lab(t('netzwerk:feld.notizen'), <textarea className={`${TC_INPUT} w-full`} rows={2} value={f.notizen} onChange={(e) => set('notizen', e.target.value)} />)}</div>
      {item.last_career_check && (
        <div className="text-xs text-slate-400 md:col-span-3">
          {t('netzwerk:karriere.pruefung', { datum: item.last_career_check.slice(0, 10) })}{item.karriere_url && <> · <a href={item.karriere_url} target="_blank" rel="noreferrer" className="text-brand-cyan hover:underline">{shortUrl(item.karriere_url)}</a></>}
          {' '}{t('netzwerk:karriere.headhunter_suche')}
        </div>
      )}
      <div className="flex items-center gap-2 md:col-span-3">
        <button onClick={save} disabled={saving || !dirty} className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">{saving ? t('netzwerk:knopf.speichern_laeuft') : t('netzwerk:knopf.speichern')}</button>
        {saved && <span className="text-sm text-emerald-600">{t('netzwerk:knopf.gespeichert')}</span>}
        {err && <span className="text-sm text-rose-600">{err}</span>}
        <button onClick={remove} className="ml-auto rounded-lg border border-rose-200 px-3 py-1.5 text-sm font-medium text-rose-600 hover:bg-rose-50">{t('netzwerk:knopf.loeschen')}</button>
      </div>
      {/* Phase 69 (Stufe B) — Gespräche ohne Stelle (z. B. ein Gespräch mit einem Headhunter). */}
      <div className="md:col-span-3">
        <NetzwerkGespraechForm headhunterId={item.real_id} defaultUnternehmen={item.firma} defaultPerson={item.ansprechpartner} />
      </div>
    </div>
  )
}

function NetzwerkKontakte() {
  const [suche, setSuche] = useState('')
  const [rows, setRows] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState<number | null>(null)
  const [showNew, setShowNew] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const today = isoTag()
  const load = () => api<any[]>('/network-contacts').then(setRows).finally(() => setLoading(false))
  useEffect(() => { load() }, [])
  const overdue = (x: any) => x.next_action_date && x.next_action_date.slice(0, 10) <= today
  const sichtbar = rows.filter((x) => passtZurSuche(x, suche, [x.prioritaet, x.kanal].filter(Boolean).map((w: string) => t(`netzwerk:wert.${w}`, { defaultValue: w }))))
  const sorted = [...sichtbar].sort((a, b) => {
    const ao = overdue(a) ? 0 : 1, bo = overdue(b) ? 0 : 1
    if (ao !== bo) return ao - bo
    const ad = a.next_action_date || '', bd = b.next_action_date || ''
    if (ad && bd && ad !== bd) return ad < bd ? -1 : 1
    if (ad && !bd) return -1
    if (!ad && bd) return 1
    return (a.name || '').localeCompare(b.name || '')
  })
  return (
    <div className="space-y-3">
      <Listensuche wert={suche} onChange={setSuche} treffer={sichtbar.length} gesamt={rows.length} />
      <datalist id="nc-kanaele">{KANAELE.map((k) => <option key={k} value={k} label={t(`netzwerk:wert.${k}`, { defaultValue: k })} />)}</datalist>
      <div className="flex items-center justify-between">
        <div className="text-sm text-slate-500">{t('netzwerk:nc.zaehler', { count: rows.length })}</div>
        {!showImport && <NetzwerkImportKnopf onClick={() => setShowImport(true)} />}
        {!showNew && <button onClick={() => setShowNew(true)} className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover">{t('netzwerk:nc.anlegen')}</button>}
      </div>
      {showNew && <NcNew onCreated={load} onClose={() => setShowNew(false)} />}
      {showImport && <NetzwerkImport liste="kontakte" onImportiert={load} onClose={() => setShowImport(false)} />}
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="w-8 px-3 py-2"></th><th className="px-3 py-2">{t('netzwerk:feld.name')}</th><th className="px-3 py-2">{t('netzwerk:feld.unternehmen')}</th>
              <th className="px-3 py-2">{t('netzwerk:feld.rolle')}</th><th className="px-3 py-2">{t('netzwerk:feld.letzter_kontakt')}</th><th className="px-3 py-2">{t('netzwerk:feld.prioritaet')}</th>
              <th className="px-3 py-2">{t('netzwerk:feld.next_action')}</th><th className="px-3 py-2">{t('netzwerk:feld.notizen')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr><td colSpan={8} className="px-3 py-8 text-center text-slate-400">{t('netzwerk:lade')}</td></tr>
            ) : sorted.length === 0 ? (
              <tr><td colSpan={8} className="px-3 py-8 text-center text-slate-400">{t(suche.trim() ? 'common:listensuche.keine' : 'netzwerk:nc.leer')}</td></tr>
            ) : sorted.map((x) => {
              const isOpen = open === x.id
              const od = overdue(x)
              return (
                <>
                  <tr key={x.id} onClick={() => setOpen(isOpen ? null : x.id)} className={`cursor-pointer align-top hover:bg-brand-cyan/5 ${isOpen ? 'bg-brand-cyan/5' : ''}`}>
                    <td className="px-3 py-2 text-slate-400">{isOpen ? '▾' : '▸'}</td>
                    <td className="px-3 py-2 font-medium text-brand-navy">{x.name || '–'}</td>
                    <td className="px-3 py-2 text-slate-700">{x.unternehmen || '–'}</td>
                    <td className="px-3 py-2 text-slate-500">{x.rolle || '–'}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-slate-500">{(x.letzter_kontakt || '–').slice(0, 10)}</td>
                    <td className="px-3 py-2 text-slate-500">{x.prioritaet ? prioAnzeige(x.prioritaet) : '–'}</td>
                    <td className="px-3 py-2">
                      {x.next_action_date ? (
                        <span className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${od ? 'bg-rose-100 text-rose-700' : 'bg-slate-100 text-slate-600'}`}>
                          {x.next_action_date.slice(0, 10)}{od ? ' ⚠' : ''}
                        </span>
                      ) : <span className="text-slate-400">–</span>}
                      {x.next_action && <div className="mt-0.5 max-w-[14rem] truncate text-xs text-slate-500" title={x.next_action}>{x.next_action}</div>}
                    </td>
                    <td className="max-w-md whitespace-pre-wrap break-words px-3 py-2 text-slate-600">{x.notizen || '–'}</td>
                  </tr>
                  {isOpen && <tr key={`${x.id}-edit`}><td colSpan={8} className="p-0"><NcEdit item={x} onSaved={load} /></td></tr>}
                </>
              )
            })}
          </tbody>
        </table>
      </div>
      <TrashPanel kind="nc" signal={rows} onRestored={load} />
    </div>
  )
}

// ── Papierkorb (17.07.2026): Soft-Delete-Tombstones (Phase 28 A) je Tab sichtbar + wiederherstellbar.
// Analog zum Datei-Papierkorb (Phase 32): nur anzeigen + wiederherstellen — endgültiges Entfernen
// bleibt beim Cleanup (Phase 33), die Tombstones sichern das Import-Dedup.
function TrashPanel({ kind, signal, onRestored }: { kind: 'targets' | 'hh' | 'nc'; signal: any; onRestored: () => void }) {
  const [items, setItems] = useState<any[]>([])
  const [openTrash, setOpenTrash] = useState(false)
  const [busy, setBusy] = useState<number | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const load = () => api<any>('/netzwerk/papierkorb')
    .then((d) => setItems(kind === 'targets' ? d.zielfirmen : kind === 'hh' ? d.headhunter : d.kontakte))
    .catch(() => setItems([]))
  useEffect(() => { load() }, [kind, signal])
  const restorePath = kind === 'targets' ? 'target-companies' : kind === 'hh' ? 'headhunters' : 'network-contacts'
  const restore = async (it: any) => {
    setBusy(it.id); setErr(null)
    try {
      await api(`/${restorePath}/${it.id}/restore`, { method: 'POST' })
      await load(); onRestored()
    } catch (e: any) { setErr(e?.message || t('netzwerk:fehler.wiederherstellen')) }
    finally { setBusy(null) }
  }
  if (items.length === 0) return null
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/60">
      <button onClick={() => setOpenTrash(!openTrash)} className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-slate-500 hover:text-slate-700">
        <span className="text-slate-400">{openTrash ? '▾' : '▸'}</span>
        <span className="font-medium">{t('netzwerk:papierkorb.titel', { anzahl: items.length })}</span>
        <span className="text-xs text-slate-400">{t('netzwerk:papierkorb.hinweis')}</span>
      </button>
      {openTrash && (
        <div className="divide-y divide-slate-100 border-t border-slate-200">
          {err && <div className="px-4 py-2 text-sm text-rose-600">{err}</div>}
          {items.map((it) => (
            <div key={it.id} className="flex items-center justify-between gap-3 px-4 py-2">
              <div className="min-w-0 truncate">
                <span className="font-medium text-slate-600">{it.label}</span>
                {it.detail && <span className="ml-2 text-xs text-slate-400">{it.detail}</span>}
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span className="text-xs text-slate-400">{t('netzwerk:papierkorb.geloescht', { datum: tagVon(it.deleted_at) })}</span>
                <button onClick={() => restore(it)} disabled={busy === it.id}
                  className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-40">
                  {busy === it.id ? t('netzwerk:papierkorb.wiederherstellen_laeuft') : t('netzwerk:papierkorb.wiederherstellen')}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Netzwerk() {
  const [tab, setTab] = useState(TABS[0])
  const [suche, setSuche] = useState('')
  const [rows, setRows] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showNewTarget, setShowNewTarget] = useState(false)
  const [showNewHH, setShowNewHH] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [open, setOpen] = useState<any>(null)

  const loadRows = () => {
    if (tab.id === 'nc') return          // Netzwerk-Kontakte lädt seine eigene interaktive Komponente
    setLoading(true)
    api<any[]>(tab.path).then(setRows).finally(() => setLoading(false))
  }
  useEffect(() => { loadRows(); setShowNewTarget(false); setShowNewHH(false); setOpen(null); setSuche('') }, [tab])
  useEffect(() => { setShowImport(false) }, [tab])  // P2-62: Import-Panel gehört zum Reiter, schließt beim Wechsel

  // Zielfirmen: jede Zeile editierbar (real_id = id). Headhunter: nur „Blatt"-Zeilen (real_id gesetzt) —
  // Outreach-Zeilen gehören /outreach, s. Spec Phase 26 A.
  const editable = (r: any) => tab.id === 'targets' || (tab.id === 'hh' && r.real_id != null)
  // P2-61: Die Spalte „Quelle“ trennt eigene Headhunter („Blatt“, Begriff aus der Excel-Zeit) von
  // übernommenen Outreach-Zeilen. Ohne Outreach-Zeile stünde dort überall „Blatt“, also entfällt
  // sie samt Hinweis darauf; mit übernommenen Zeilen bleibt beides.
  const mitOutreach = rows.some((r) => r.source === 'Outreach')
  const sichtbar = rows.filter((r) => passtZurSuche(r, suche))
  const cols = tab.cols.filter((c) => c.key !== 'source' || mitOutreach)

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">{t('common:nav.netzwerk')}</h1>
        {/* P2-61: „Gespiegelt aus dem Job-Search-Tracker“ stimmte nur für einen einmaligen
            Import, bei neuen Installationen nie. Der Untertitel sagt jetzt, was die Seite ist. */}
        <p className="text-sm text-slate-500">{t('netzwerk:untertitel')}</p>
      </div>

      <div className="flex gap-1 border-b border-slate-200">
        {TABS.map((tb) => (
          <button key={tb.id} onClick={() => setTab(tb)}
            className={`rounded-t-lg px-4 py-2 text-sm font-medium ${tab.id === tb.id ? 'border-b-2 border-brand-cyan text-brand-navy' : 'text-slate-500 hover:text-slate-700'}`}>
            {t(`netzwerk:tab.${tb.id}`)}
          </button>
        ))}
      </div>

      {tab.id !== 'nc' && <Listensuche wert={suche} onChange={setSuche} treffer={sichtbar.length} gesamt={rows.length} />}

      {tab.id === 'targets' && (
        <div className="flex items-center justify-between">
          <div className="text-sm text-slate-500">{t('netzwerk:tc.zaehler', { count: rows.length })}</div>
          {!showImport && <NetzwerkImportKnopf onClick={() => setShowImport(true)} />}
          {!showNewTarget && <button onClick={() => setShowNewTarget(true)} className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover">{t('netzwerk:tc.anlegen')}</button>}
        </div>
      )}
      {tab.id === 'targets' && showNewTarget &&
        <TargetNew onCreated={loadRows} onClose={() => setShowNewTarget(false)} />}
      {tab.id === 'targets' && showImport &&
        <NetzwerkImport liste="zielfirmen" onImportiert={loadRows} onClose={() => setShowImport(false)} />}

      {tab.id === 'hh' && (
        <div className="flex items-center justify-between">
          <div className="text-sm text-slate-500">{t(mitOutreach ? 'netzwerk:hh.zaehler_blatt' : 'netzwerk:hh.zaehler', { count: rows.length })}</div>
          {!showImport && <NetzwerkImportKnopf onClick={() => setShowImport(true)} />}
          {!showNewHH && <button onClick={() => setShowNewHH(true)} className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover">{t('netzwerk:hh.anlegen')}</button>}
        </div>
      )}
      {tab.id === 'hh' && showNewHH &&
        <HeadhunterNew onCreated={loadRows} onClose={() => setShowNewHH(false)} />}
      {tab.id === 'hh' && showImport &&
        <NetzwerkImport liste="headhunter" onImportiert={loadRows} onClose={() => setShowImport(false)} />}

      {tab.id === 'nc' ? <NetzwerkKontakte /> : (
      <>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>{cols.map((c) => <th key={c.key} className="px-3 py-2">{c.key === '_aktion' ? '' : t(`netzwerk:feld.${c.key}`)}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr><td colSpan={cols.length} className="px-3 py-8 text-center text-slate-400">{t('netzwerk:lade')}</td></tr>
            ) : (
              <>
                {suche.trim() && sichtbar.length === 0 && (
                  <tr><td colSpan={cols.length} className="px-3 py-8 text-center text-slate-400">{t('common:listensuche.keine')}</td></tr>
                )}
                {sichtbar.map((r) => {
                  const canEdit = editable(r)
                  const isOpen = canEdit && open === r.id
                  return (
                    <>
                      <tr key={r.id} onClick={() => canEdit && setOpen(isOpen ? null : r.id)}
                          title={!canEdit ? t('netzwerk:zeile_outreach_tooltip') : undefined}
                          className={`align-top ${canEdit ? 'cursor-pointer hover:bg-brand-cyan/5' : ''} ${isOpen ? 'bg-brand-cyan/5' : ''}`}>
                        {cols.map((c) => {
                          const v = r[c.key]
                          if (c.key === '_aktion') return <td key={c.key} className="px-3 py-2"><CopyChip phrase={t('common:ausloeser.initiativ', { name: r.company })} /></td> // i18n-ok: Auslöser-Phrase des Skills initiativ-bewerbung
                          if (c.key === 'tier') { const f = tierColor(v); return <td key={c.key} className="px-3 py-2"><span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ backgroundColor: f.bg, color: f.text }}>{v || '–'}</span></td> }
                          if (c.key === 'scenario') { const f = scenarioColor(v); return <td key={c.key} className="px-3 py-2"><span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ backgroundColor: f.bg, color: f.text }}>{v || '–'}</span></td> }
                          if (c.key === 'source') return <td key={c.key} className="px-3 py-2"><span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${v === 'Outreach' ? 'bg-brand-cyan/15 text-brand-navy' : 'bg-slate-100 text-slate-500'}`}>{v}</span></td>
                          if (c.key === 'company' || c.key === 'firma' || c.key === 'name')
                            return <td key={c.key} className="px-3 py-2 font-medium text-brand-navy">{v || '–'}</td>
                          if (c.key === 'webseite')
                            return <td key={c.key} className="whitespace-nowrap px-3 py-2">{v ? <a href={v} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="text-brand-cyan hover:underline">{shortUrl(v)}</a> : <span className="text-slate-400">–</span>}</td>
                          return <td key={c.key} className={`px-3 py-2 text-slate-600 ${c.wide ? 'min-w-[16rem] max-w-md' : 'whitespace-nowrap'}`}>{v || '–'}</td>
                        })}
                      </tr>
                      {isOpen && (
                        <tr key={`${r.id}-edit`}>
                          <td colSpan={cols.length} className="p-0">
                            {tab.id === 'targets'
                              ? <TargetEdit item={r} onSaved={loadRows} />
                              : <HeadhunterEdit item={r} onSaved={loadRows} />}
                          </td>
                        </tr>
                      )}
                    </>
                  )
                })}
                <tr><td colSpan={cols.length} className="px-3 py-2 text-xs text-slate-400">{t('netzwerk:eintraege', { count: sichtbar.length })}</td></tr>
              </>
            )}
          </tbody>
        </table>
      </div>
      <TrashPanel kind={tab.id as 'targets' | 'hh'} signal={rows} onRestored={loadRows} />
      </>
      )}
    </div>
  )
}
