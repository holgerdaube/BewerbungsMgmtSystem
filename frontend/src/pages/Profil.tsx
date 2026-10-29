import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, apiUpload } from '../api'
import AgentTaskButton from '../components/AgentTaskButton'
import ProfilIdentitaet from '../components/ProfilIdentitaet'
import { tagVon } from '../zeit'

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

// ── LinkedIn-Zeile: URL-Button (best effort) + ZIP-Upload (robuster Weg) ────────────────
const TASK_ACTIVE = ['queued', 'running']
const TASK_CHIP: Record<string, string> = {
  queued: 'bg-slate-100 text-slate-600', running: 'bg-indigo-100 text-indigo-800',
  done: 'bg-emerald-100 text-emerald-800', failed: 'bg-rose-100 text-rose-700', cancelled: 'bg-slate-100 text-slate-500',
}
const TASK_CHIP_TEXT: Record<string, string> = {
  queued: 'wartet…', running: 'läuft…', done: '✓ fertig', failed: '✗ fehlgeschlagen', cancelled: 'abgebrochen',
}

/** Schlanke Live-Status-Anzeige für den „Profil einlesen"-Button — bewusst NICHT AgentTaskButton
 *  wiederverwendet (das startet immer gegen POST /tasks; hier braucht es den dedizierten
 *  Endpunkt POST /api/profil/einlesen, der zusätzlich die URL am Profil speichert — s. Spec
 *  Design-Entscheidung 5. AgentTaskButton.tsx steht nicht auf der Phase-45-Datei-Whitelist). */
function LinkedinEinlesenButton({ url, onFinished }: { url: string; onFinished: () => void }) {
  const [task, setTask] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (!task || !TASK_ACTIVE.includes(task.status)) return
    const iv = setInterval(() => {
      api<any>(`/tasks/${task.id}`).then((t) => {
        setTask(t)
        if (!TASK_ACTIVE.includes(t.status)) onFinished()
      }).catch(() => {})
    }, 3000)
    return () => clearInterval(iv)
  }, [task?.id, task?.status])

  const start = async () => {
    if (!url.trim()) { setErr('LinkedIn-URL fehlt'); return }
    setBusy(true); setErr(null)
    try {
      const r = await api<any>('/profil/einlesen', { method: 'POST', body: JSON.stringify({ linkedin_url: url }) })
      setTask(r.task)
    } catch (e: any) { setErr(e?.message || 'Start fehlgeschlagen') }
    finally { setBusy(false) }
  }

  const active = task && TASK_ACTIVE.includes(task.status)
  return (
    <div className="space-y-1.5">
      <button onClick={start} disabled={busy || !!active}
        className="whitespace-nowrap rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-50">
        {active ? '⏳ Läuft…' : busy ? 'Starte…' : '▶ Profil einlesen'}
      </button>
      {task && (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className={`rounded-full px-2 py-0.5 font-medium ${TASK_CHIP[task.status]}`}>{TASK_CHIP_TEXT[task.status]}</span>
          {task.duration_s != null && <span className="text-slate-400">{task.duration_s}s</span>}
        </div>
      )}
      {task?.status === 'failed' && task.error && <div className="rounded-lg bg-rose-50 p-2 text-xs text-rose-700">{task.error}</div>}
      {task?.status === 'done' && task.result && (
        <div className="max-w-xl rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs text-slate-600 whitespace-pre-wrap">{task.result}</div>
      )}
      {err && <div className="text-xs text-rose-600">{err}</div>}
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
    } catch (e: any) { setZipErr(e?.message || 'Import fehlgeschlagen') }
    finally { setZipUploading(false) }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex min-w-[16rem] flex-1 flex-col text-xs text-slate-500">
          LinkedIn-Profil-URL
          <input className={`${INPUT} mt-1`} placeholder="https://www.linkedin.com/in/…"
            value={url} onChange={(e) => setUrl(e.target.value)} onBlur={() => url !== (profile.linkedin_url || '') && saveUrl()} />
        </label>
        <LinkedinEinlesenButton url={url} onFinished={onSaved} />
      </div>
      {saving && <div className="mt-1 text-xs text-slate-400">Speichert URL…</div>}
      <div className="mt-3 border-t border-slate-100 pt-3">
        <div className="flex flex-wrap items-center gap-2">
          <input type="file" accept=".zip" onChange={(e) => setZipFile(e.target.files?.[0] || null)}
            className="text-xs text-slate-600 file:mr-2 file:rounded-lg file:border file:border-slate-300 file:bg-white file:px-2.5 file:py-1 file:text-xs file:font-medium file:text-slate-600 hover:file:bg-slate-50" />
          <button onClick={uploadZip} disabled={!zipFile || zipUploading}
            className="rounded-lg border border-brand-cyan/40 px-3 py-1.5 text-xs font-medium text-brand-navy hover:bg-brand-cyan/10 disabled:cursor-not-allowed disabled:opacity-50">
            {zipUploading ? 'Importiert…' : 'Datenexport-ZIP hochladen'}
          </button>
        </div>
        <p className="mt-1 text-xs text-slate-400">
          LinkedIn → Einstellungen → Datenschutz → „Get a copy of your data" → oberste Option
          „Download larger data archive" (NICHT die Schnellauswahl „Profile" — die enthält nur die
          Positionierung). Das große Archiv umfasst Skills, Berufserfahrung, Ausbildung und
          Zertifizierungen; Bereitstellung dauert bei LinkedIn bis zu ~24 h. Additiv: erneuter
          Import überschreibt nichts manuell Gepflegtes.
        </p>
        {zipErr && <div className="mt-1 text-xs text-rose-600">{zipErr}</div>}
        {zipResult && (
          <div className="mt-1 text-xs text-emerald-700">
            ✓ Import: {zipResult.skills_neu} neue Skills · {zipResult.werdegang_neu} neue Werdegang-Einträge
            {zipResult.profil_aktualisiert?.length ? ` · Profil ergänzt (${zipResult.profil_aktualisiert.join(', ')})` : ''}
            {zipResult.task_id != null && (
              <> · Skills werden automatisch einsortiert (<Link to="/tasks" className="text-brand-cyan hover:underline">Task-Center</Link>)</>
            )}
          </div>
        )}
        <div className="mt-2">
          <AgentTaskButton kind="skills-sortieren" label="Skills neu einsortieren" subtle
            onFinished={onSaved} key={zipResult?.task_id ?? 'skills-sortieren'} />
        </div>
      </div>
      {profile.linkedin_eingelesen_am && (
        <div className="mt-2 text-xs text-slate-400">Zuletzt eingelesen: {profile.linkedin_eingelesen_am}</div>
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
      <div className="mb-2 text-sm font-semibold text-brand-navy">Positionierung</div>
      <textarea className={`${INPUT} w-full`} rows={5}
        placeholder="Wie stellst du dich vor? Fließtext — wird fürs Matching und die Anschreiben verwendet."
        value={text} onChange={(e) => setText(e.target.value)} />
      <div className="mt-2 flex items-center gap-2">
        <button onClick={save} disabled={saving || !dirty}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? 'Speichern…' : 'Speichern'}
        </button>
        {saved && <span className="text-sm text-emerald-600">✓ Gespeichert</span>}
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
    if (!name.trim() || !bereich.trim()) { setErr('Skill und Bereich sind Pflicht'); return }
    setSaving(true); setErr(null)
    try {
      await api('/profil/skills', { method: 'POST', body: JSON.stringify({ name: name.trim(), bereich: bereich.trim() }) })
      setName(''); onChanged()
    } catch (e: any) { setErr(e?.message || 'Anlegen fehlgeschlagen') }
    finally { setSaving(false) }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 text-sm font-semibold text-brand-navy">Skills{gesamt > 0 && ` (${gesamt})`}</div>
      {bereiche.length === 0 && <div className="text-sm text-slate-400">Noch keine Skills erfasst.</div>}
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
        <input className={`${INPUT} min-w-[12rem] flex-1`} placeholder="Neuer Skill" value={name}
          onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && add()} />
        <input list="profil-bereiche" className={`${INPUT} w-48`} placeholder="Bereich (bestehend oder neu)"
          value={bereich} onChange={(e) => setBereich(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && add()} />
        <button onClick={add} disabled={saving}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:opacity-40">
          Hinzufügen
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
    if (!window.confirm(`„${item.rolle || item.firma || 'Eintrag'}" wirklich löschen?`)) return
    await api(`/profil/werdegang/${item.id}`, { method: 'DELETE' })
    onSaved()
  }
  const Lab = (label: string, node: any) => <label className="flex flex-col text-xs text-slate-500">{label}<div className="mt-1">{node}</div></label>
  return (
    <div className="grid grid-cols-1 gap-3 bg-slate-50/70 px-4 py-4 md:grid-cols-2">
      {Lab('Firma/Institution', <input className={`${INPUT} w-full`} value={f.firma} onChange={(e) => set('firma', e.target.value)} />)}
      {Lab('Rolle/Titel', <input className={`${INPUT} w-full`} value={f.rolle} onChange={(e) => set('rolle', e.target.value)} />)}
      {Lab('Ort', <input className={`${INPUT} w-full`} value={f.ort} onChange={(e) => set('ort', e.target.value)} />)}
      <div className="grid grid-cols-2 gap-3">
        {Lab('Von', <input className={`${INPUT} w-full`} placeholder="z. B. 2020" value={f.von} onChange={(e) => set('von', e.target.value)} />)}
        {Lab('Bis', <input className={`${INPUT} w-full`} placeholder="z. B. heute" value={f.bis} onChange={(e) => set('bis', e.target.value)} />)}
      </div>
      <div className="md:col-span-2">{Lab('Beschreibung', <textarea className={`${INPUT} w-full`} rows={2} value={f.beschreibung} onChange={(e) => set('beschreibung', e.target.value)} />)}</div>
      {Lab('Referenzgeber', <input className={`${INPUT} w-full`} value={f.referenzgeber} onChange={(e) => set('referenzgeber', e.target.value)} />)}
      {Lab('Referenzdatum', <input className={`${INPUT} w-full`} value={f.referenzdatum} onChange={(e) => set('referenzdatum', e.target.value)} />)}
      <div className="md:col-span-2">{Lab('Notiz', <input className={`${INPUT} w-full`} value={f.notiz} onChange={(e) => set('notiz', e.target.value)} />)}</div>
      <div className="flex items-center gap-2 md:col-span-2">
        <button onClick={save} disabled={saving || !dirty} className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">{saving ? 'Speichern…' : 'Speichern'}</button>
        {saved && <span className="text-sm text-emerald-600">✓ Gespeichert</span>}
        {item.quelle === 'linkedin' && <span className="text-xs text-slate-400">Quelle: LinkedIn</span>}
        <button onClick={remove} className="ml-auto rounded-lg border border-rose-200 px-3 py-1.5 text-sm font-medium text-rose-600 hover:bg-rose-50">🗑 Löschen</button>
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
        <input className={INPUT} placeholder="Firma/Institution" value={f.firma} onChange={(e) => set('firma', e.target.value)} />
        <input className={INPUT} placeholder="Rolle/Titel" value={f.rolle} onChange={(e) => set('rolle', e.target.value)} />
        <input className={INPUT} placeholder="Ort" value={f.ort} onChange={(e) => set('ort', e.target.value)} />
        <input className={INPUT} placeholder="Von" value={f.von} onChange={(e) => set('von', e.target.value)} />
        <input className={INPUT} placeholder="Bis" value={f.bis} onChange={(e) => set('bis', e.target.value)} />
        <textarea className={`${INPUT} md:col-span-3`} rows={2} placeholder="Beschreibung" value={f.beschreibung} onChange={(e) => set('beschreibung', e.target.value)} />
      </div>
      <div className="mt-2 flex items-center gap-2">
        <button onClick={save} disabled={saving} className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:opacity-40">{saving ? 'Anlegen…' : 'Anlegen'}</button>
        <button onClick={onClose} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">Abbrechen</button>
      </div>
    </div>
  )
}

function Werdegang({ werdegang, onChanged }: { werdegang: any[]; onChanged: () => void }) {
  const [open, setOpen] = useState<number | null>(null)
  const [showNewFor, setShowNewFor] = useState<string | null>(null)
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 text-sm font-semibold text-brand-navy">Werdegang</div>
      <div className="space-y-4">
        {CAREER_ARTEN.map((art) => {
          const entries = werdegang.filter((w) => w.art === art)
          if (entries.length === 0 && showNewFor !== art) return (
            <div key={art} className="flex items-center justify-between text-xs text-slate-400">
              <span className="font-medium uppercase tracking-wide">{art}</span>
              <button onClick={() => setShowNewFor(art)} className="text-brand-cyan hover:underline">+ Eintrag</button>
            </div>
          )
          return (
            <div key={art}>
              <div className="mb-1 flex items-center justify-between">
                <span className="text-xs font-medium uppercase tracking-wide text-slate-500">{art}</span>
                {showNewFor !== art && <button onClick={() => setShowNewFor(art)} className="text-xs text-brand-cyan hover:underline">+ Eintrag</button>}
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
    } catch (e: any) { setErr(e?.message || 'Upload fehlgeschlagen') }
    finally { setUploading(false) }
  }
  const remove = async (id: number) => {
    await api(`/profil/dateien/${id}`, { method: 'DELETE' })
    onChanged()
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 text-sm font-semibold text-brand-navy">Zertifikate und Zeugnisse</div>
      <div className="space-y-1">
        {dateien.map((f) => (
          <div key={f.id} className="flex items-center gap-2 border-b border-slate-100 py-2 text-sm last:border-0">
            <span className="shrink-0">📄</span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate font-medium text-brand-navy" title={f.filename}>{f.filename}</span>
                <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">{f.kind}</span>
              </div>
              <div className="text-xs text-slate-400">{humanSize(f.size_bytes)}{f.created_at ? ` · ${tagVon(f.created_at)}` : ''}</div>
            </div>
            <a href={artifactUrl(f.file_path)} className="shrink-0 text-xs text-brand-cyan hover:underline">Öffnen</a>
            <a href={artifactUrl(f.file_path, true)} className="shrink-0 text-xs text-brand-cyan hover:underline">⬇</a>
            <button onClick={() => remove(f.id)} className="shrink-0 text-slate-400 hover:text-rose-600" title="In den Papierkorb">🗑</button>
          </div>
        ))}
        {dateien.length === 0 && <div className="text-sm text-slate-400">Noch keine Dateien angehängt.</div>}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
        <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="text-xs text-slate-600 file:mr-2 file:rounded-lg file:border file:border-slate-300 file:bg-white file:px-2.5 file:py-1 file:text-xs file:font-medium file:text-slate-600 hover:file:bg-slate-50" />
        <select className={INPUT} value={kind} onChange={(e) => setKind(e.target.value)}>
          {FILE_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
        </select>
        <button onClick={upload} disabled={!file || uploading}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {uploading ? 'Lädt…' : 'Hochladen'}
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
const CV_LABELS: Record<string, string> = {
  de: 'Deutsch', en: 'Englisch', fr: 'Französisch', es: 'Spanisch', it: 'Italienisch',
  nl: 'Niederländisch', pt: 'Portugiesisch', pl: 'Polnisch', da: 'Dänisch', sv: 'Schwedisch',
}
const CV_SPRACH_OPTIONEN = ['de', 'en', 'fr', 'es', 'it', 'nl']
const CV_SPRACH_RE = /^[a-z]{2}$/

// `tagVon` liefert `YYYY-MM-DD` (Vorbild aus zeit.ts); die Rückfrage in §2.4 der Spec braucht
// das vertraute deutsche Format — deshalb hier lokal umgeformt statt ein zweites Mal `Date`
// zu bemühen.
function datumDE(iso?: string | null): string {
  const tag = tagVon(iso)
  const teile = tag.split('-')
  return teile.length === 3 ? `${teile[2]}.${teile[1]}.${teile[0]}` : tag
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
      const frage =
        `Für ${CV_LABELS[stand.sprache] || stand.sprache?.toUpperCase() || effektiverCode} liegt ` +
        `bereits ein CV vom ${datumDE(stand.updated_at)} (${humanSize(stand.size_bytes)}, ` +
        `${stand.stationen ?? '?'} Stationen). Überschreiben? Die bisherige Datei wandert in den Papierkorb.`
      if (window.confirm(frage)) await sendeUpload(true)
      return
    }
    if (!res.ok) throw new Error((typeof body.detail === 'string' && body.detail) || `${res.status} ${res.statusText}`)
    setFile(null); setAndereCode(''); setSprache('de'); load()
  }

  const upload = async () => {
    if (!file) return
    if (!CV_SPRACH_RE.test(effektiverCode)) {
      setErr('Sprachcode muss aus zwei Kleinbuchstaben bestehen (z. B. de, en, fr).')
      return
    }
    setUploading(true); setErr(null)
    try {
      await sendeUpload(false)
    } catch (e: any) { setErr(e?.message || 'Upload fehlgeschlagen') }
    finally { setUploading(false) }
  }

  const remove = async (code: string) => {
    if (!window.confirm(`Basis-CV ${CV_LABELS[code] || code.toUpperCase()} in den Papierkorb legen?`)) return
    await api(`/profil/cv-basis/${code}`, { method: 'DELETE' })
    load()
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 text-sm font-semibold text-brand-navy">Basis-CVs</div>
      <p className="mb-2 text-xs text-slate-500">
        Die Vorlagen, aus denen jeder auf eine Stelle zugeschnittene Lebenslauf entsteht. Deutsch
        und Englisch zieht das System selbst heran; andere Sprachen liegen bereit, werden aber von
        keinem Skill automatisch benutzt.
      </p>
      {loading ? (
        <div className="text-sm text-slate-400">Lade…</div>
      ) : (
        <div className="space-y-1">
          {liste.map((cv) => (
            <div key={cv.sprache} className="flex items-center gap-2 border-b border-slate-100 py-2 text-sm last:border-0">
              <span className="shrink-0">📄</span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-brand-navy">{CV_LABELS[cv.sprache] || cv.sprache.toUpperCase()}</span>
                  <span className="truncate text-xs text-slate-400" title={cv.filename}>{cv.filename}</span>
                  {cv.automatisch ? (
                    <span className="shrink-0 rounded bg-emerald-50 px-1.5 py-0.5 text-xs text-emerald-700">wird automatisch verwendet</span>
                  ) : (
                    <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600"
                      title="Deutsch und Englisch zieht das System selbst heran; andere Sprachen liegen bereit, werden aber von keinem Skill automatisch benutzt.">
                      nur manuell
                    </span>
                  )}
                </div>
                <div className="text-xs text-slate-400">
                  {humanSize(cv.size_bytes)} · {datumDE(cv.updated_at)}
                  {cv.stationen != null ? ` · ${cv.stationen} Stationen` : ''}
                </div>
                {cv.warnung && (
                  <div className="mt-1 rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">{cv.warnung}</div>
                )}
              </div>
              <a href={artifactUrl(cv.path, true)} className="shrink-0 text-xs text-brand-cyan hover:underline">⬇</a>
              <button onClick={() => remove(cv.sprache)} className="shrink-0 text-slate-400 hover:text-rose-600" title="In den Papierkorb">🗑</button>
            </div>
          ))}
          {liste.length === 0 && <div className="text-sm text-slate-400">Noch kein Basis-CV hochgeladen.</div>}
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
        <input type="file" accept=".docx" onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="text-xs text-slate-600 file:mr-2 file:rounded-lg file:border file:border-slate-300 file:bg-white file:px-2.5 file:py-1 file:text-xs file:font-medium file:text-slate-600 hover:file:bg-slate-50" />
        <select className={INPUT} value={sprache} onChange={(e) => setSprache(e.target.value)}>
          {CV_SPRACH_OPTIONEN.map((c) => <option key={c} value={c}>{CV_LABELS[c]}</option>)}
          <option value="andere">Andere…</option>
        </select>
        {sprache === 'andere' && (
          <input type="text" maxLength={2} placeholder="z. B. pt" value={andereCode}
            onChange={(e) => setAndereCode(e.target.value)} className={`${INPUT} w-20`} />
        )}
        <button onClick={upload} disabled={!file || uploading}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {uploading ? 'Lädt…' : 'Hochladen'}
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

  if (loading || !data) return <div className="text-slate-400">Lade…</div>

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">Profil</h1>
        <p className="text-sm text-slate-500">
          Positionierung, Skills, Werdegang und Zeugnisse — wird für das Matching und die Anschreiben verwendet.
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
