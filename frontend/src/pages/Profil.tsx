import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, apiUpload } from '../api'
import AgentTaskButton from '../components/AgentTaskButton'
import ProfilIdentitaet from '../components/ProfilIdentitaet'
import { tagVon } from '../zeit'
import { Trans } from 'react-i18next'
import { t } from '../i18n'
import { datum } from '../i18n/format'

// Muster JobDetail.tsx::artifactUrl — bewusst lokal statt aus ui.tsx importiert (Phase-45-
// Datei-Whitelist erlaubt ui.tsx nicht anzufassen; JobDetail.tsx hält denselben Helfer ebenso lokal).
function artifactUrl(path: string, download = false) {
  return `/api/artifact?path=${encodeURIComponent(path)}${download ? '&download=true' : ''}`
}

function humanSize(bytes?: number | null): string {
  if (!bytes) return ''
  const kb = bytes / 1024
  return kb >= 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb.toFixed(0)} kB`
}

const INPUT = 'rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none'
const CAREER_ARTEN = ['Beruf', 'Ausbildung', 'Zertifizierung', 'Projekt', 'Sonstiges']
const CAREER_FIELDS = ['art', 'firma', 'rolle', 'ort', 'von', 'bis', 'beschreibung',
  'referenzgeber', 'referenzdatum', 'notiz']
const FILE_KINDS = ['Zeugnis', 'Zertifikat', 'Sonstiges']
// Anzeige für DB-Werte (Art im Werdegang, Dateiart): Deutsch ist der Wert selbst.
const wertP = (x: string): string => t(`profil:wert.${x}`, { defaultValue: x })

// ── LinkedIn-Zeile: URL, Profiltext oder PDF (KI, Vorschau), ZIP-Upload (vollständigster Weg) ────────────────
const TASK_ACTIVE = ['queued', 'running']
const TASK_CHIP: Record<string, string> = {
  queued: 'bg-slate-100 text-slate-600', running: 'bg-indigo-100 text-indigo-800',
  done: 'bg-emerald-100 text-emerald-800', failed: 'bg-rose-100 text-rose-700', cancelled: 'bg-slate-100 text-slate-500',
}
const TASK_CHIP_TEXT_KEYS = ['queued', 'running', 'done', 'failed', 'cancelled']
const taskText = (status: string): string | undefined =>
  TASK_CHIP_TEXT_KEYS.includes(status) ? t(`profil:task.${status}`) : undefined

/** Profil aus eingefügtem Text oder PDF: Die KI strukturiert, gespeichert wird erst nach der Vorschau. */
function LinkedinText({ onSaved }: { onSaved: () => void }) {
  const [text, setText] = useState('')
  const [pdf, setPdf] = useState<File | null>(null)
  const [task, setTask] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [vorschau, setVorschau] = useState<any>(null)
  const [ergebnis, setErgebnis] = useState<any>(null)

  const vorschauLaden = () => api<any>('/profil/linkedin-vorschlag').then((v) => setVorschau(v.vorhanden ? v : null)).catch(() => {})
  useEffect(() => { vorschauLaden() }, [])

  useEffect(() => {
    if (!task || !TASK_ACTIVE.includes(task.status)) return
    const iv = setInterval(() => {
      api<any>(`/tasks/${task.id}`).then((t) => {
        setTask(t)
        // Der eingefügte Text bleibt stehen, bis der Lauf durch ist: Scheitert er, geht nichts verloren.
        if (t.status === 'done') { vorschauLaden(); setText(''); setPdf(null) }
      }).catch(() => {})
    }, 3000)
    return () => clearInterval(iv)
  }, [task?.id, task?.status])

  const start = async () => {
    setBusy(true); setErr(null); setVorschau(null); setErgebnis(null)
    try {
      const fd = new FormData()
      if (pdf) fd.append('file', pdf)
      else fd.append('text', text)
      // NICHT über api(), Muster uploadZip unten.
      const { res, body } = await apiUpload('/api/profil/linkedin-einlesen', fd)
      if (!res.ok) throw new Error(body.detail || `${res.status} ${res.statusText}`)
      setTask(body.task)
    } catch (e: any) { setErr(e?.message || t('profil:linkedin.start_fehler')) }
    finally { setBusy(false) }
  }

  const uebernehmen = async () => {
    setBusy(true); setErr(null)
    try {
      setErgebnis(await api<any>('/profil/linkedin-vorschlag/uebernehmen', { method: 'POST' }))
      setVorschau(null); setTask(null)
      onSaved()
    } catch (e: any) { setErr(e?.message || t('profil:linkedin.uebernehmen_fehler')) }
    finally { setBusy(false) }
  }

  const verwerfen = async () => {
    setBusy(true); setErr(null)
    try {
      await api('/profil/linkedin-vorschlag', { method: 'DELETE' })
      setVorschau(null); setTask(null)
    } catch (e: any) { setErr(e?.message || t('profil:linkedin.verwerfen_fehler')) }
    finally { setBusy(false) }
  }

  const active = task && TASK_ACTIVE.includes(task.status)
  return (
    <div className="mt-3 border-t border-slate-100 pt-3">
      <div className="mb-1 text-xs font-medium text-slate-500">{t('profil:linkedin.text_titel')}</div>
      <p className="mb-2 text-xs text-slate-400">
        {t('profil:linkedin.text_hinweis')}
      </p>
      <textarea className={`${INPUT} w-full`} rows={4} value={text} disabled={!!pdf}
        placeholder={t('profil:linkedin.text_platzhalter')} onChange={(e) => setText(e.target.value)} />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input type="file" accept=".pdf" onChange={(e) => setPdf(e.target.files?.[0] || null)}
          className="text-xs text-slate-600 file:mr-2 file:rounded-lg file:border file:border-slate-300 file:bg-white file:px-2.5 file:py-1 file:text-xs file:font-medium file:text-slate-600 hover:file:bg-slate-50" />
        <button onClick={start} disabled={busy || !!active || (!pdf && !text.trim())}
          className="whitespace-nowrap rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {active ? t('profil:linkedin.laeuft') : busy ? t('profil:linkedin.startet') : t('profil:linkedin.auslesen')}
        </button>
        {task && (
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${TASK_CHIP[task.status]}`}>{taskText(task.status)}</span>
        )}
      </div>
      {task?.status === 'failed' && task.error && <div className="mt-2 rounded-lg bg-rose-50 p-2 text-xs text-rose-700">{task.error}</div>}
      {err && <div className="mt-1 text-xs text-rose-600">{err}</div>}
      {ergebnis && (
        <div className="mt-2 text-xs text-emerald-700">
          {t('profil:ergebnis.uebernommen', {
            skills: t('profil:ergebnis.skills', { count: ergebnis.skills_neu }),
            werdegang: t('profil:ergebnis.werdegang', { count: ergebnis.werdegang_neu }),
          })}
          {ergebnis.profil_aktualisiert?.length ? ` · ${t('profil:ergebnis.profil_ergaenzt', { felder: ergebnis.profil_aktualisiert.join(', ') })}` : ''}
          {ergebnis.task_id != null && (
            <> · <Trans i18nKey="profil:ergebnis.einsortiert" components={{ tasks: <Link to="/tasks" className="text-brand-cyan hover:underline" /> }} /></>
          )}
        </div>
      )}
      {vorschau && (
        <div className="mt-3 space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
          <div className="font-semibold text-brand-navy">{t('profil:vorschau.titel')}</div>
          {vorschau.felder.map((f: any) => (
            <div key={f.label}><b>{f.label}:</b> <span className="whitespace-pre-wrap">{f.wert}</span></div>
          ))}
          {vorschau.felder_behalten.length > 0 && (
            <div className="text-slate-400">{t('profil:vorschau.behalten', { felder: vorschau.felder_behalten.join(', ') })}</div>
          )}
          <div>
            <b>{t('profil:vorschau.neue_skills', { anzahl: vorschau.skills_neu.length })}</b> {vorschau.skills_neu.join(', ') || '–'}
            {vorschau.skills_vorhanden > 0 && <span className="text-slate-400"> · {t('profil:vorschau.schon_vorhanden', { count: vorschau.skills_vorhanden })}</span>}
          </div>
          <div>
            <b>{t('profil:vorschau.neue_eintraege', { anzahl: vorschau.werdegang_neu.length })}</b>
            {vorschau.werdegang_vorhanden > 0 && <span className="text-slate-400"> {t('profil:vorschau.schon_vorhanden', { count: vorschau.werdegang_vorhanden })}</span>}
            <ul className="mt-1 list-disc pl-4">
              {vorschau.werdegang_neu.map((e: any, n: number) => (
                <li key={n}>{[e.rolle, e.firma].filter(Boolean).join(' · ')} ({wertP(e.art)}{e.von || e.bis ? `, ${[e.von, e.bis].filter(Boolean).join(' – ')}` : ''})</li>
              ))}
            </ul>
          </div>
          <div className="flex gap-2 pt-1">
            <button onClick={uebernehmen} disabled={busy}
              className="rounded-lg bg-brand-cyan px-3 py-1.5 text-xs font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:opacity-40">{t('profil:vorschau.alles_uebernehmen')}</button>
            <button onClick={verwerfen} disabled={busy}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 disabled:opacity-40">{t('profil:vorschau.verwerfen')}</button>
          </div>
        </div>
      )}
    </div>
  )
}

function LinkedinZeile({ profile, onSaved }: { profile: any; onSaved: () => void }) {
  const [url, setUrl] = useState(profile.linkedin_url || '')
  const [saving, setSaving] = useState(false)
  const [zipFile, setZipFile] = useState<File | null>(null)
  const [zipUploading, setZipUploading] = useState(false)
  const [zipErr, setZipErr] = useState<string | null>(null)
  const [zipResult, setZipResult] = useState<any>(null)

  const saveUrl = async () => {
    setSaving(true)
    try { await api('/profil', { method: 'PATCH', body: JSON.stringify({ linkedin_url: url }) }); onSaved() }
    finally { setSaving(false) }
  }

  const uploadZip = async () => {
    if (!zipFile) return
    setZipUploading(true); setZipErr(null); setZipResult(null)
    try {
      const fd = new FormData()
      fd.append('file', zipFile)
      // NICHT über api() — das setzt einen JSON-Header, den multipart nicht verträgt (Muster JobDetail.tsx).
      const { res, body } = await apiUpload('/api/profil/import-zip', fd)
      if (!res.ok) throw new Error(body.detail || `${res.status} ${res.statusText}`)
      setZipResult(body)
      setZipFile(null)
      onSaved()
    } catch (e: any) { setZipErr(e?.message || t('profil:linkedin.zip_fehler')) }
    finally { setZipUploading(false) }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <label className="flex flex-col text-xs text-slate-500">
        {t('profil:linkedin.profil_url')}
        <input className={`${INPUT} mt-1`} placeholder="https://www.linkedin.com/in/…" /* i18n-ok: URL */
          value={url} onChange={(e) => setUrl(e.target.value)} onBlur={() => url !== (profile.linkedin_url || '') && saveUrl()} />
      </label>
      {saving && <div className="mt-1 text-xs text-slate-400">{t('profil:linkedin.url_speichert')}</div>}
      <LinkedinText onSaved={onSaved} />
      <div className="mt-3 border-t border-slate-100 pt-3">
        <div className="flex flex-wrap items-center gap-2">
          <input type="file" accept=".zip" onChange={(e) => setZipFile(e.target.files?.[0] || null)}
            className="text-xs text-slate-600 file:mr-2 file:rounded-lg file:border file:border-slate-300 file:bg-white file:px-2.5 file:py-1 file:text-xs file:font-medium file:text-slate-600 hover:file:bg-slate-50" />
          <button onClick={uploadZip} disabled={!zipFile || zipUploading}
            className="rounded-lg border border-brand-cyan/40 px-3 py-1.5 text-xs font-medium text-brand-navy hover:bg-brand-cyan/10 disabled:cursor-not-allowed disabled:opacity-50">
            {zipUploading ? t('profil:linkedin.zip_importiert') : t('profil:linkedin.zip_hochladen')}
          </button>
        </div>
        <p className="mt-1 text-xs text-slate-400">
          {t('profil:linkedin.zip_hinweis')}
        </p>
        {zipErr && <div className="mt-1 text-xs text-rose-600">{zipErr}</div>}
        {zipResult && (
          <div className="mt-1 text-xs text-emerald-700">
            {t('profil:ergebnis.import', {
              skills: t('profil:ergebnis.skills', { count: zipResult.skills_neu }),
              werdegang: t('profil:ergebnis.werdegang', { count: zipResult.werdegang_neu }),
            })}
            {zipResult.profil_aktualisiert?.length ? ` · ${t('profil:ergebnis.profil_ergaenzt', { felder: zipResult.profil_aktualisiert.join(', ') })}` : ''}
            {zipResult.task_id != null && (
              <> · <Trans i18nKey="profil:ergebnis.einsortiert" components={{ tasks: <Link to="/tasks" className="text-brand-cyan hover:underline" /> }} /></>
            )}
          </div>
        )}
        <div className="mt-2">
          <AgentTaskButton kind="skills-sortieren" label={t('profil:linkedin.skills_einsortieren')} subtle
            onFinished={onSaved} key={zipResult?.task_id ?? 'skills-sortieren'} />
        </div>
      </div>
      {profile.linkedin_eingelesen_am && (
        <div className="mt-2 text-xs text-slate-400">{t('profil:linkedin.eingelesen_am', { datum: profile.linkedin_eingelesen_am })}</div>
      )}
    </div>
  )
}

// ── Positionierung ───────────────────────────────────────────────────────────────────
function Positionierung({ profile, onSaved }: { profile: any; onSaved: () => void }) {
  const [text, setText] = useState(profile.positionierung || '')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const dirty = text !== (profile.positionierung || '')
  const save = async () => {
    setSaving(true)
    try {
      await api('/profil', { method: 'PATCH', body: JSON.stringify({ positionierung: text }) })
      onSaved(); setSaved(true); setTimeout(() => setSaved(false), 2000)
    } finally { setSaving(false) }
  }
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 text-sm font-semibold text-brand-navy">{t('profil:positionierung.titel')}</div>
      <textarea className={`${INPUT} w-full`} rows={5}
        placeholder={t('profil:positionierung.platzhalter')}
        value={text} onChange={(e) => setText(e.target.value)} />
      <div className="mt-2 flex items-center gap-2">
        <button onClick={save} disabled={saving || !dirty}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? t('profil:aktion.speichert') : t('profil:aktion.speichern')}
        </button>
        {saved && <span className="text-sm text-emerald-600">{t('profil:aktion.gespeichert')}</span>}
      </div>
    </div>
  )
}

// ── Bereich-Farbleiter = §18.6-Kategorienpalette (Phase 80-Nachtrag, Entscheidung
// 10.08.2026 per Vorher/Nachher-Grafik) — Kerntöne exakt aus dem Styleguide v5, Chip-Fläche
// (bg) und Textfarbe daraus abgeleitet und kontrastgeprüft. Löst die gedämpfte Eigen-Palette
// vom 21.07.2026 ab (Rollback-Werte: tasks/spec_phase80_styleguide_v18_theme.md, WP-D).
// Zyklisch: mehr als 6 Bereiche wiederholen sich, fällt in der Praxis kaum auf.
const BEREICH_FARBEN = [
  { dot: '#00B4D8', bg: '#E3F6FB', text: '#075E73' }, // category.1 Cyan (unverändert)
  { dot: '#5B61E6', bg: '#E9EAFC', text: '#383D96' }, // category.2 Indigo
  { dot: '#0EA5A4', bg: '#E1F4F4', text: '#0A6A69' }, // category.4 Teal
  { dot: '#C4478C', bg: '#F8E8F1', text: '#832F5D' }, // category.5 Magenta
  { dot: '#7C4DFF', bg: '#EFEAFF', text: '#4F2FA8' }, // category.3 Violet
  { dot: '#5E7894', bg: '#EDF1F5', text: '#435669' }, // category.6 Steel Blue
]
function bereichFarbe(index: number) {
  return BEREICH_FARBEN[index % BEREICH_FARBEN.length]
}

// ── Skills nach Bereich gruppiert ────────────────────────────────────────────────────
function Skills({ skills, onChanged }: { skills: Record<string, any[]>; onChanged: () => void }) {
  const [name, setName] = useState('')
  const [bereich, setBereich] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const bereiche = Object.keys(skills)
  const gesamt = bereiche.reduce((n, b) => n + skills[b].length, 0)

  const remove = async (id: number) => {
    await api(`/profil/skills/${id}`, { method: 'DELETE' })
    onChanged()
  }
  const add = async () => {
    if (!name.trim() || !bereich.trim()) { setErr(t('profil:skills.pflicht')); return }
    setSaving(true); setErr(null)
    try {
      await api('/profil/skills', { method: 'POST', body: JSON.stringify({ name: name.trim(), bereich: bereich.trim() }) })
      setName(''); onChanged()
    } catch (e: any) { setErr(e?.message || t('profil:skills.anlegen_fehler')) }
    finally { setSaving(false) }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 text-sm font-semibold text-brand-navy">{t('profil:skills.titel')}{gesamt > 0 && ` (${gesamt})`}</div>
      {bereiche.length === 0 && <div className="text-sm text-slate-400">{t('profil:skills.leer')}</div>}
      <div className="space-y-3">
        {bereiche.map((b, i) => {
          const farbe = bereichFarbe(i)
          return (
            <div key={b}>
              <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold" style={{ color: farbe.text }}>
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: farbe.dot }} />
                {b}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {skills[b].map((s) => (
                  <span key={s.id} className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium"
                    style={{ backgroundColor: farbe.bg, color: farbe.text }}>
                    {s.name}{s.note && <span className="opacity-60">({s.note})</span>}
                    <button onClick={() => remove(s.id)} className="ml-0.5 opacity-50 hover:text-rose-600 hover:opacity-100">×</button>
                  </span>
                ))}
              </div>
            </div>
          )
        })}
      </div>
      <datalist id="profil-bereiche">{bereiche.map((b) => <option key={b} value={b} />)}</datalist>
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
        <input className={`${INPUT} min-w-[12rem] flex-1`} placeholder={t('profil:skills.neu')} value={name}
          onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && add()} />
        <input list="profil-bereiche" className={`${INPUT} w-48`} placeholder={t('profil:skills.bereich')}
          value={bereich} onChange={(e) => setBereich(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && add()} />
        <button onClick={add} disabled={saving}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:opacity-40">
          {t('profil:skills.hinzufuegen')}
        </button>
      </div>
      {err && <div className="mt-1 text-xs text-rose-600">{err}</div>}
    </div>
  )
}

// ── Werdegang: editierbare Blöcke je Art (Muster NcEdit) ────────────────────────────
function CareerBlock({ item, onSaved }: { item: any; onSaved: () => void }) {
  const [f, setF] = useState<any>(() => Object.fromEntries(CAREER_FIELDS.map((k) => [k, item[k] || ''])))
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const set = (k: string, v: string) => setF((x: any) => ({ ...x, [k]: v }))
  const dirty = CAREER_FIELDS.some((k) => (f[k] || '') !== (item[k] || ''))
  const save = async () => {
    setSaving(true)
    try {
      const patch: any = {}
      CAREER_FIELDS.forEach((k) => { if ((f[k] || '') !== (item[k] || '')) patch[k] = f[k] || null })
      await api(`/profil/werdegang/${item.id}`, { method: 'PATCH', body: JSON.stringify(patch) })
      onSaved(); setSaved(true); setTimeout(() => setSaved(false), 2000)
    } finally { setSaving(false) }
  }
  const remove = async () => {
    if (!window.confirm(t('profil:werdegang.loeschen_frage', { name: item.rolle || item.firma || t('profil:werdegang.eintrag') }))) return
    await api(`/profil/werdegang/${item.id}`, { method: 'DELETE' })
    onSaved()
  }
  const Lab = (label: string, node: any) => <label className="flex flex-col text-xs text-slate-500">{label}<div className="mt-1">{node}</div></label>
  return (
    <div className="grid grid-cols-1 gap-3 bg-slate-50/70 px-4 py-4 md:grid-cols-2">
      {Lab(t('profil:werdegang.feld.firma'), <input className={`${INPUT} w-full`} value={f.firma} onChange={(e) => set('firma', e.target.value)} />)}
      {Lab(t('profil:werdegang.feld.rolle'), <input className={`${INPUT} w-full`} value={f.rolle} onChange={(e) => set('rolle', e.target.value)} />)}
      {Lab(t('profil:werdegang.feld.ort'), <input className={`${INPUT} w-full`} value={f.ort} onChange={(e) => set('ort', e.target.value)} />)}
      <div className="grid grid-cols-2 gap-3">
        {Lab(t('profil:werdegang.feld.von'), <input className={`${INPUT} w-full`} placeholder={t('profil:werdegang.feld.von_platzhalter')} value={f.von} onChange={(e) => set('von', e.target.value)} />)}
        {Lab(t('profil:werdegang.feld.bis'), <input className={`${INPUT} w-full`} placeholder={t('profil:werdegang.feld.bis_platzhalter')} value={f.bis} onChange={(e) => set('bis', e.target.value)} />)}
      </div>
      <div className="md:col-span-2">{Lab(t('profil:werdegang.feld.beschreibung'), <textarea className={`${INPUT} w-full`} rows={2} value={f.beschreibung} onChange={(e) => set('beschreibung', e.target.value)} />)}</div>
      {Lab(t('profil:werdegang.feld.referenzgeber'), <input className={`${INPUT} w-full`} value={f.referenzgeber} onChange={(e) => set('referenzgeber', e.target.value)} />)}
      {Lab(t('profil:werdegang.feld.referenzdatum'), <input className={`${INPUT} w-full`} value={f.referenzdatum} onChange={(e) => set('referenzdatum', e.target.value)} />)}
      <div className="md:col-span-2">{Lab(t('profil:werdegang.feld.notiz'), <input className={`${INPUT} w-full`} value={f.notiz} onChange={(e) => set('notiz', e.target.value)} />)}</div>
      <div className="flex items-center gap-2 md:col-span-2">
        <button onClick={save} disabled={saving || !dirty} className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">{saving ? t('profil:aktion.speichert') : t('profil:aktion.speichern')}</button>
        {saved && <span className="text-sm text-emerald-600">{t('profil:aktion.gespeichert')}</span>}
        {item.quelle === 'linkedin' && <span className="text-xs text-slate-400">{t('profil:werdegang.quelle_linkedin')}</span>}
        <button onClick={remove} className="ml-auto rounded-lg border border-rose-200 px-3 py-1.5 text-sm font-medium text-rose-600 hover:bg-rose-50">{t('profil:werdegang.loeschen')}</button>
      </div>
    </div>
  )
}

function CareerNew({ art, onCreated, onClose }: { art: string; onCreated: () => void; onClose: () => void }) {
  const [f, setF] = useState<any>({ firma: '', rolle: '', ort: '', von: '', bis: '', beschreibung: '' })
  const [saving, setSaving] = useState(false)
  const set = (k: string, v: string) => setF((x: any) => ({ ...x, [k]: v }))
  const save = async () => {
    setSaving(true)
    try {
      const body: any = { art }
      Object.keys(f).forEach((k) => { if (f[k]) body[k] = f[k] })
      await api('/profil/werdegang', { method: 'POST', body: JSON.stringify(body) })
      onCreated(); onClose()
    } finally { setSaving(false) }
  }
  return (
    <div className="rounded-xl border border-brand-cyan/40 bg-brand-cyan/5 p-4">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <input className={INPUT} placeholder={t('profil:werdegang.feld.firma')} value={f.firma} onChange={(e) => set('firma', e.target.value)} />
        <input className={INPUT} placeholder={t('profil:werdegang.feld.rolle')} value={f.rolle} onChange={(e) => set('rolle', e.target.value)} />
        <input className={INPUT} placeholder={t('profil:werdegang.feld.ort')} value={f.ort} onChange={(e) => set('ort', e.target.value)} />
        <input className={INPUT} placeholder={t('profil:werdegang.feld.von')} value={f.von} onChange={(e) => set('von', e.target.value)} />
        <input className={INPUT} placeholder={t('profil:werdegang.feld.bis')} value={f.bis} onChange={(e) => set('bis', e.target.value)} />
        <textarea className={`${INPUT} md:col-span-3`} rows={2} placeholder={t('profil:werdegang.feld.beschreibung')} value={f.beschreibung} onChange={(e) => set('beschreibung', e.target.value)} />
      </div>
      <div className="mt-2 flex items-center gap-2">
        <button onClick={save} disabled={saving} className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:opacity-40">{saving ? t('profil:aktion.legt_an') : t('profil:aktion.anlegen')}</button>
        <button onClick={onClose} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">{t('profil:aktion.abbrechen')}</button>
      </div>
    </div>
  )
}

function Werdegang({ werdegang, onChanged }: { werdegang: any[]; onChanged: () => void }) {
  const [open, setOpen] = useState<number | null>(null)
  const [showNewFor, setShowNewFor] = useState<string | null>(null)
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 text-sm font-semibold text-brand-navy">{t('profil:werdegang.titel')}</div>
      <div className="space-y-4">
        {CAREER_ARTEN.map((art) => {
          const entries = werdegang.filter((w) => w.art === art)
          if (entries.length === 0 && showNewFor !== art) return (
            <div key={art} className="flex items-center justify-between text-xs text-slate-400">
              <span className="font-medium uppercase tracking-wide">{wertP(art)}</span>
              <button onClick={() => setShowNewFor(art)} className="text-brand-cyan hover:underline">{t('profil:werdegang.eintrag_neu')}</button>
            </div>
          )
          return (
            <div key={art}>
              <div className="mb-1 flex items-center justify-between">
                <span className="text-xs font-medium uppercase tracking-wide text-slate-500">{wertP(art)}</span>
                {showNewFor !== art && <button onClick={() => setShowNewFor(art)} className="text-xs text-brand-cyan hover:underline">{t('profil:werdegang.eintrag_neu')}</button>}
              </div>
              {showNewFor === art && (
                <div className="mb-2">
                  <CareerNew art={art} onCreated={onChanged} onClose={() => setShowNewFor(null)} />
                </div>
              )}
              <div className="divide-y divide-slate-100 overflow-hidden rounded-lg border border-slate-200">
                {entries.map((w) => {
                  const isOpen = open === w.id
                  return (
                    <div key={w.id}>
                      <button onClick={() => setOpen(isOpen ? null : w.id)}
                        className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-slate-50 ${isOpen ? 'bg-brand-cyan/5' : ''}`}>
                        <span className="text-slate-400">{isOpen ? '▾' : '▸'}</span>
                        <span className="font-medium text-brand-navy">{w.rolle || '–'}</span>
                        <span className="text-slate-500">{w.firma ? `· ${w.firma}` : ''}</span>
                        <span className="ml-auto shrink-0 text-xs text-slate-400">{[w.von, w.bis].filter(Boolean).join(' – ')}</span>
                      </button>
                      {isOpen && <CareerBlock item={w} onSaved={onChanged} />}
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Dateien: Zeugnisse/Zertifikate ───────────────────────────────────────────────────
function Dateien({ dateien, onChanged }: { dateien: any[]; onChanged: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [kind, setKind] = useState('Zeugnis')
  const [uploading, setUploading] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const upload = async () => {
    if (!file) return
    setUploading(true); setErr(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('kind', kind)
      const { res, body } = await apiUpload('/api/profil/dateien', fd)
      if (!res.ok) throw new Error(body.detail || `${res.status} ${res.statusText}`)
      setFile(null); onChanged()
    } catch (e: any) { setErr(e?.message || t('profil:aktion.upload_fehler')) }
    finally { setUploading(false) }
  }
  const remove = async (id: number) => {
    await api(`/profil/dateien/${id}`, { method: 'DELETE' })
    onChanged()
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 text-sm font-semibold text-brand-navy">{t('profil:dateien.titel')}</div>
      <div className="space-y-1">
        {dateien.map((f) => (
          <div key={f.id} className="flex items-center gap-2 border-b border-slate-100 py-2 text-sm last:border-0">
            <span className="shrink-0">📄</span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate font-medium text-brand-navy" title={f.filename}>{f.filename}</span>
                <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">{wertP(f.kind)}</span>
              </div>
              <div className="text-xs text-slate-400">{humanSize(f.size_bytes)}{f.created_at ? ` · ${tagVon(f.created_at)}` : ''}</div>
            </div>
            <a href={artifactUrl(f.file_path)} className="shrink-0 text-xs text-brand-cyan hover:underline">{t('profil:dateien.oeffnen')}</a>
            <a href={artifactUrl(f.file_path, true)} className="shrink-0 text-xs text-brand-cyan hover:underline">⬇</a>
            <button onClick={() => remove(f.id)} className="shrink-0 text-slate-400 hover:text-rose-600" title={t('profil:aktion.in_papierkorb')}>🗑</button>
          </div>
        ))}
        {dateien.length === 0 && <div className="text-sm text-slate-400">{t('profil:dateien.leer')}</div>}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
        <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="text-xs text-slate-600 file:mr-2 file:rounded-lg file:border file:border-slate-300 file:bg-white file:px-2.5 file:py-1 file:text-xs file:font-medium file:text-slate-600 hover:file:bg-slate-50" />
        <select className={INPUT} value={kind} onChange={(e) => setKind(e.target.value)}>
          {FILE_KINDS.map((k) => <option key={k} value={k}>{wertP(k)}</option>)}
        </select>
        <button onClick={upload} disabled={!file || uploading}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {uploading ? t('profil:aktion.laedt_hoch') : t('profil:aktion.hochladen')}
        </button>
      </div>
      {err && <div className="mt-1 text-xs text-rose-600">{err}</div>}
    </div>
  )
}

// ── Basis-CVs: die Vorlagen, aus denen jeder tailored CV entsteht ──────────────────────
// Sprach-Labels für die Anzeige — Vorbild `_CV_LABELS` in main.py. Ein Code, den diese Liste
// nicht kennt (von Hand im Ordner abgelegt), zeigt einfach seinen Großbuchstaben-Code statt
// eines Labels, statt die Karte scheitern zu lassen.
const CV_LABEL_CODES = ['de', 'en', 'fr', 'es', 'it', 'nl', 'pt', 'pl', 'da', 'sv']
const cvLabel = (code?: string): string | undefined =>
  code && CV_LABEL_CODES.includes(code) ? t(`profil:cv_sprache.${code}`) : undefined
const CV_SPRACH_OPTIONEN = ['de', 'en', 'fr', 'es', 'it', 'nl', 'pt']
const CV_SPRACH_RE = /^[a-z]{2}$/

// `tagVon` liefert `YYYY-MM-DD` (Vorbild aus zeit.ts); die Rückfrage in §2.4 der Spec braucht
// das vertraute deutsche Format — deshalb hier lokal umgeformt statt ein zweites Mal `Date`
// zu bemühen.
function datumDE(iso?: string | null): string {
  const tag = tagVon(iso)
  return tag ? datum(tag) : tag
}

function BasisCVs() {
  const [liste, setListe] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [file, setFile] = useState<File | null>(null)
  const [sprache, setSprache] = useState('de')
  const [andereCode, setAndereCode] = useState('')
  const [uploading, setUploading] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const load = () => api<any[]>('/profil/cv-basis').then(setListe).finally(() => setLoading(false))
  useEffect(() => { load() }, [])

  const effektiverCode = sprache === 'andere' ? andereCode.trim().toLowerCase() : sprache

  const sendeUpload = async (overwrite: boolean) => {
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    fd.append('sprache', effektiverCode)
    fd.append('overwrite', overwrite ? 'true' : 'false')
    const { res, body } = await apiUpload('/api/profil/cv-basis', fd)
    if (res.status === 409) {
      const stand = body.detail || {}
      const frage = t('profil:basis_cv.ueberschreiben_frage', {
        sprache: cvLabel(stand.sprache) || stand.sprache?.toUpperCase() || effektiverCode,
        datum: datumDE(stand.updated_at),
        groesse: humanSize(stand.size_bytes),
        stationen: stand.stationen ?? '?',
      })
      if (window.confirm(frage)) await sendeUpload(true)
      return
    }
    if (!res.ok) throw new Error((typeof body.detail === 'string' && body.detail) || `${res.status} ${res.statusText}`)
    setFile(null); setAndereCode(''); setSprache('de'); load()
  }

  const upload = async () => {
    if (!file) return
    if (!CV_SPRACH_RE.test(effektiverCode)) {
      setErr(t('profil:basis_cv.code_fehler'))
      return
    }
    setUploading(true); setErr(null)
    try {
      await sendeUpload(false)
    } catch (e: any) { setErr(e?.message || t('profil:aktion.upload_fehler')) }
    finally { setUploading(false) }
  }

  const remove = async (code: string) => {
    if (!window.confirm(t('profil:basis_cv.loeschen_frage', { sprache: cvLabel(code) || code.toUpperCase() }))) return
    await api(`/profil/cv-basis/${code}`, { method: 'DELETE' })
    load()
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 text-sm font-semibold text-brand-navy">{t('profil:basis_cv.titel')}</div>
      <p className="mb-2 text-xs text-slate-500">
        {t('profil:basis_cv.hinweis')}
      </p>
      {loading ? (
        <div className="text-sm text-slate-400">{t('profil:aktion.lade')}</div>
      ) : (
        <div className="space-y-1">
          {liste.map((cv) => (
            <div key={cv.sprache} className="flex items-center gap-2 border-b border-slate-100 py-2 text-sm last:border-0">
              <span className="shrink-0">📄</span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-brand-navy">{cvLabel(cv.sprache) || cv.sprache.toUpperCase()}</span>
                  <span className="truncate text-xs text-slate-400" title={cv.filename}>{cv.filename}</span>
                  {cv.automatisch ? (
                    <span className="shrink-0 rounded bg-emerald-50 px-1.5 py-0.5 text-xs text-emerald-700">{t('profil:basis_cv.automatisch')}</span>
                  ) : (
                    <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600"
                      title={t('profil:basis_cv.nur_manuell_hinweis')}>
                      {t('profil:basis_cv.nur_manuell')}
                    </span>
                  )}
                </div>
                <div className="text-xs text-slate-400">
                  {humanSize(cv.size_bytes)} · {datumDE(cv.updated_at)}
                  {cv.stationen != null ? ` · ${t('profil:basis_cv.stationen', { count: cv.stationen })}` : ''}
                </div>
                {cv.warnung && (
                  <div className="mt-1 rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">{cv.warnung}</div>
                )}
              </div>
              <a href={artifactUrl(cv.path, true)} className="shrink-0 text-xs text-brand-cyan hover:underline">⬇</a>
              <button onClick={() => remove(cv.sprache)} className="shrink-0 text-slate-400 hover:text-rose-600" title={t('profil:aktion.in_papierkorb')}>🗑</button>
            </div>
          ))}
          {liste.length === 0 && <div className="text-sm text-slate-400">{t('profil:basis_cv.leer')}</div>}
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
        <input type="file" accept=".docx" onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="text-xs text-slate-600 file:mr-2 file:rounded-lg file:border file:border-slate-300 file:bg-white file:px-2.5 file:py-1 file:text-xs file:font-medium file:text-slate-600 hover:file:bg-slate-50" />
        <select className={INPUT} value={sprache} onChange={(e) => setSprache(e.target.value)}>
          {CV_SPRACH_OPTIONEN.map((c) => <option key={c} value={c}>{cvLabel(c)}</option>)}
          <option value="andere">{t('profil:basis_cv.andere')}</option>
        </select>
        {sprache === 'andere' && (
          <input type="text" maxLength={2} placeholder={t('profil:basis_cv.code_platzhalter')} value={andereCode}
            onChange={(e) => setAndereCode(e.target.value)} className={`${INPUT} w-20`} />
        )}
        <button onClick={upload} disabled={!file || uploading}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {uploading ? t('profil:aktion.laedt_hoch') : t('profil:aktion.hochladen')}
        </button>
      </div>
      {err && <div className="mt-1 text-xs text-rose-600">{err}</div>}
    </div>
  )
}

// ── Seite ─────────────────────────────────────────────────────────────────────────────
export default function Profil() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  const load = () => api<any>('/profil').then(setData).finally(() => setLoading(false))
  useEffect(() => { load() }, [])

  if (loading || !data) return <div className="text-slate-400">{t('profil:aktion.lade')}</div>

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">{t('profil:seite.titel')}</h1>
        <p className="text-sm text-slate-500">
          {t('profil:seite.untertitel')}
        </p>
      </div>
      {/* P2-69: liest und schreibt config/profil.md, lädt sich selbst (eigener Endpunkt). */}
      <ProfilIdentitaet />
      <LinkedinZeile profile={data.profile} onSaved={load} />
      <Positionierung profile={data.profile} onSaved={load} />
      <Skills skills={data.skills} onChanged={load} />
      <Werdegang werdegang={data.werdegang} onChanged={load} />
      <Dateien dateien={data.dateien} onChanged={load} />
      <BasisCVs />
    </div>
  )
}
