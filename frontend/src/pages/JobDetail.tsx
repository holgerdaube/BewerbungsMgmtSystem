import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { api, apiUpload, type Einstellungen } from '../api'
import { ScoreBadge, StatusBadge, VerifyBadge, DubletteBadge, NeuausschreibungBadge, Section, CopyChip } from '../components/ui'
import CopyTrigger from '../components/CopyTrigger'
import AgentTaskButton from '../components/AgentTaskButton'
import EmailDetail from '../components/EmailDetail'
import BeiratCheckButton from '../components/BeiratCheckButton'
import { useReviewCount } from '../context/ReviewCount'
import { isoTag, tagVon } from '../zeit'
import { useProfilAdresse, mapsRouteUrl } from '../profil'
import { useSuchTabs } from '../suchbereich'

const STATUSES = ['Neu', 'Prüfen', 'Beworben', 'Interview', 'Angebot', 'Absage', 'Keine Rückmeldung', 'Kein Match', 'Beirat abgelehnt', 'Nicht verfügbar', 'Geparkt']

// „Headhunter-Screen" ergänzt 13.08.2026: Ein Screening über einen Personalberater ist
// eine eigene Gesprächsform und hieß bisher notgedrungen „Sonstiges".
const IV_ARTEN = ['HR-Screen', 'Headhunter-Screen', 'Fachgespräch', 'Hiring Manager', 'Panel', 'Final', 'Sonstiges']
// Phase 69 (Stufe B) — Interview.gegenueber, dieselbe Werteliste wie app/gesamtprozess.py
// (Gesamtprozess-KPI "Gespräche gesamt", Splits je Gegenüber-Typ).
const IV_GEGENUEBER = ['Recruiter', 'Hiring Manager', 'Fachbereich', 'Headhunter', 'Sonstige']
// Sentinel-Wert der Runden-Auswahl im Transkript-Dialog: kein echter Datensatz, sondern die
// Aufforderung „lege beim Speichern eine neue Runde an" (s. RundenWahl/interviewIdFuer).
const NEUE_RUNDE = '__neu'
// Welches Gegenüber gehört üblicherweise zu welcher Gesprächsart? Dieselbe Zuordnung, die der
// einmalige Backfill in Phase 69 verwendet hat (HR-Screen → Recruiter, „Hiring Manager" → Hiring
// Manager). Zweck: `gegenueber` ist die Auswertungs-Dimension der Gesamtprozess-KPIs, `art` nur
// Beschriftung — wer die Art wählt, soll die KPI-Dimension nicht extra pflegen müssen. Der
// Vorschlag ist überschreibbar: eine bewusst abweichende Wahl bleibt beim Artwechsel stehen
// (s. artWechsel()).
const GEGENUEBER_ZU_ART: Record<string, string> = {
  'HR-Screen': 'Recruiter',
  'Headhunter-Screen': 'Headhunter',
  'Fachgespräch': 'Fachbereich',
  'Hiring Manager': 'Hiring Manager',
  'Panel': 'Fachbereich',
  'Final': 'Hiring Manager',
}
const IV_STATUS_STYLE: Record<string, string> = {
  Geplant: 'bg-amber-100 text-amber-700',
  Absolviert: 'bg-emerald-100 text-emerald-800',
  Abgesagt: 'bg-slate-100 text-slate-500',
}

// Phase 74 — Anzeige-Label + Farbe für die Verfügbarkeitsprüfung (Design-Entscheidung 2/5),
// identisch zu den Backend-Log-Labels — ein Text, zwei Stellen.
const AVAILABILITY_LABELS: Record<string, { label: string; cls: string }> = {
  offen: { label: 'noch ausgeschrieben', cls: 'text-emerald-600' },
  karriereseite_offen: { label: 'Portal zu, Karriereseite offen', cls: 'text-amber-600' },
  offline: { label: 'nicht mehr ausgeschrieben', cls: 'text-rose-600' },
  unklar: { label: 'unklar', cls: 'text-slate-500' },
}

function artifactUrl(path: string, download = false) {
  return `/api/artifact?path=${encodeURIComponent(path)}${download ? '&download=true' : ''}`
}

/** Lange Anzeige-URL kürzen (wie im Phase-18-Snapshot): Host ohne "www." + gekürzter Pfad. */
function shortUrl(u: string): string {
  try {
    const url = new URL(u)
    const host = url.hostname.replace(/^www\./, '')
    const p = url.pathname
    if (!p || p === '/') return host
    return host + (p.length <= 24 ? p : '/…' + p.slice(-12))
  } catch {
    return u.length > 40 ? u.slice(0, 40) + '…' : u
  }
}

const FILE_KINDS = ['Transkript', 'Stellenbeschreibung', 'Präsentation', 'Sonstiges']
const GESPRAECHS_ARTEN = ['Telefonat', 'Video-Call', 'Vor-Ort-Gespräch']

/** kind aus der Dateiendung/-name vorschlagen (Spec B1). */
function guessKind(name: string): string {
  const n = name.toLowerCase()
  const ext = n.includes('.') ? n.split('.').pop()! : ''
  if (['vtt', 'srt', 'txt', 'md'].includes(ext)) return 'Transkript'
  if (['pptx', 'ppt'].includes(ext)) return 'Präsentation'
  if (['pdf', 'docx'].includes(ext) && /stellen|jd|job/.test(n)) return 'Stellenbeschreibung'
  return 'Sonstiges'
}

function fileIcon(kind: string, name: string): string {
  if (kind === 'Transkript') return '🎙'
  if (kind === 'Stellenbeschreibung' || kind === 'Stellenausschreibung') return '📋'
  if (kind === 'Präsentation' || /\.pptx?$/i.test(name)) return '📊'
  return '📄'
}

function humanSize(bytes?: number | null): string {
  if (!bytes) return ''
  const kb = bytes / 1024
  return kb >= 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb.toFixed(0)} kB`
}

/** Muster aus Outreach.tsx::logTime — Log-Zeitstempel als lokales de-DE-Datum+Zeit. */
function logTime(iso: string) {
  if (!iso) return ''
  // P2-20: Die API kennzeichnet ihre Zeitstempel seit 28.08.2026 als UTC (`app/zeit.py`),
  // das Anhaengen von 'Z' ist damit ueberfluessig geworden.
  const d = new Date(iso)
  return d.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })
}

/** Ein Schritt der Workflow-Karte „Unterlagen erstellen" (Phase 16): Nummer/✓/🔒-Kreis + Inhalt.
 *  P2-41: `optional` markiert einen Baustein, der kein Kettenglied ist und nie `locked` trägt —
 *  offen zeigt er einen leeren, gestrichelten Kreis statt Ziffer oder Schloss. */
function WfStep({ n, done, locked, lockedTitle, optional, children }: {
  n?: string; done?: boolean; locked?: boolean; lockedTitle?: string; optional?: boolean; children: any
}) {
  const base = 'flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs'
  const circle = done
    ? <span className={`${base} bg-emerald-500 font-bold text-white`}>✓</span>
    : optional
    ? <span className={`${base} border border-dashed border-slate-300`} />
    : locked
    ? <span className={`${base} bg-slate-100 text-slate-300`}>🔒</span>
    : <span className={`${base} bg-brand-navy font-semibold text-white`}>{n}</span>
  return (
    <div className="flex items-start gap-3 py-1.5" title={locked ? lockedTitle : undefined}>
      {circle}
      <div className={`min-w-0 flex-1 ${done ? 'text-slate-400' : locked ? 'text-slate-300' : ''}`}>{children}</div>
    </div>
  )
}

type Pending = {
  file: File; kind: string
  kontakt: string; gespraechsart: string; interview_id: string; recorded_at: string; auswerten: boolean
}

const DEBRIEF_CHIP: Record<string, string> = {
  queued: 'Auswertung wartet…', running: 'Auswertung läuft…',
  done: '✓ ausgewertet', failed: '✗ fehlgeschlagen', cancelled: 'abgebrochen',
}

/** Runden-Auswahl für ein Transkript (Einfügen wie Datei-Upload nutzen dieselbe). Die Option
 *  „Neue Runde anlegen…" blendet zwei Zusatzfelder ein (NeueRundeFelder) und wird beim Speichern
 *  in eine echte Runde übersetzt (JobDetail::interviewIdFuer) — vorher passierte hier nichts,
 *  damit ein abgebrochener Dialog keine leere Runde hinterlässt. */
function RundenWahl({ form, setForm, interviews, className }: {
  form: any; setForm: (f: any) => void; interviews: any[]; className?: string
}) {
  const waehle = (wert: string) => {
    if (wert !== NEUE_RUNDE) { setForm({ ...form, interview_id: wert }); return }
    // Vorschlag: nächste freie Nummer; erste Runde ist meist ein HR-Screen, jede weitere eher
    // ein Fachgespräch. Bereits Getipptes wird nicht überschrieben.
    setForm({
      ...form, interview_id: NEUE_RUNDE,
      neu_runde: form.neu_runde || String((interviews?.length || 0) + 1),
      neu_art: form.neu_art || ((interviews?.length || 0) === 0 ? 'HR-Screen' : 'Fachgespräch'),
    })
  }
  return (
    <select value={form.interview_id} onChange={(e) => waehle(e.target.value)}
      className={className || 'w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none'}>
      <option value="">— ohne Zuordnung —</option>
      {(interviews || []).map((iv: any) => <option key={iv.id} value={iv.id}>Runde {iv.runde} · {iv.art}</option>)}
      <option value={NEUE_RUNDE}>+ Neue Runde anlegen…</option>
    </select>
  )
}

/** Nummer + Art der neu anzulegenden Runde; rendert nichts, solange „Neue Runde…" nicht gewählt
 *  ist. Das Gegenüber (KPI-Dimension) leitet sich beim Anlegen aus der Art ab, s. GEGENUEBER_ZU_ART. */
function NeueRundeFelder({ form, setForm }: { form: any; setForm: (f: any) => void }) {
  if (form.interview_id !== NEUE_RUNDE) return null
  const feld = 'rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none'
  return (
    <div className="flex items-center gap-2 rounded-lg border border-brand-cyan/40 bg-white p-2">
      <span className="text-xs text-slate-500">Neue Runde:</span>
      <input type="number" min={1} title="Rundennummer" value={form.neu_runde}
        onChange={(e) => setForm({ ...form, neu_runde: e.target.value })} className={`${feld} w-16`} />
      <select value={form.neu_art} onChange={(e) => setForm({ ...form, neu_art: e.target.value })}
        className={`${feld} flex-1`}>
        {IV_ARTEN.map((a) => <option key={a} value={a}>{a}</option>)}
      </select>
    </div>
  )
}

/** „🧠 Auswerten"-Trigger + Status-Chip für ein Transkript (Phase 30: der Report selbst — Basis
    oder Vollversion — ist jetzt IMMER über den „📄 Report öffnen"-Link an der Transkript-Zeile
    erreichbar, s. u.; dieser Button startet/wiederholt nur den Debrief-Skill). */
function DebriefBadge({ t, task, onStart }: { t: any; task: any; onStart: (t: any) => void }) {
  const active = task && ['queued', 'running'].includes(task.status)
  return (
    <span className="flex items-center gap-2 text-xs">
      <button onClick={() => onStart(t)} disabled={active} className="text-brand-cyan hover:underline disabled:opacity-50">
        🧠 {t.summary ? 'Erneut auswerten' : 'Auswerten'}
      </button>
      {task && <span className="text-slate-400">{DEBRIEF_CHIP[task.status] || task.status}</span>}
    </span>
  )
}

/** Zerlegt die flache Absatz-Liste `[{i, style, text, ist_bullet}]` in „Blöcke": Fixed-Absätze
 *  (Heading/Normal, bleiben index-stabil) und Bullet-Gruppen (zusammenhängende `ist_bullet`-Läufe,
 *  verankert am `i` des vorangehenden Fixed-Absatzes) — Grundlage sowohl fürs Rendern als EIN
 *  Textarea als auch fürs Zurück-Parsen beim Speichern (Phase 48 Stufe B). Wird EINMAL beim Mount
 *  berechnet (Struktur ändert sich durch Editieren nicht — nur Bullet-TEXTE/-Anzahl sind frei). */
function buildBloecke(absaetze: any[]): any[] {
  const bloecke: any[] = []
  let letzterFixedI: number | null = null
  let aktuelleGruppe: any = null
  for (const a of absaetze) {
    if (a.ist_bullet) {
      if (!aktuelleGruppe) {
        aktuelleGruppe = { anchor_i: letzterFixedI, texte: [] as string[] }
        bloecke.push(aktuelleGruppe)
      }
      aktuelleGruppe.texte.push(a.text)
    } else {
      aktuelleGruppe = null
      bloecke.push({ i: a.i, style: a.style, text: a.text })
      letzterFixedI = a.i
    }
  }
  return bloecke
}

/** Blöcke → EIN zusammenhängender Text: Heading `### …`, Bullet `- …`, sonst reiner Text
 *  (eine Zeile = ein Absatz, wie in der Spec festgelegt — keine Leerzeilen zwischen Blöcken). */
function bloeckeZuText(bloecke: any[]): string {
  return bloecke.map((b) => {
    if ('anchor_i' in b) return b.texte.map((t: string) => `- ${t}`).join('\n')
    const istUeberschrift = String(b.style || '').startsWith('Heading')
    return (istUeberschrift ? '### ' : '') + b.text
  }).join('\n')
}

/** Text → editierter Entwurf zurückparsen, gegen dieselben Blöcke validiert: Fixed-Zeilen MÜSSEN
 *  1:1 in Anzahl+Reihenfolge erhalten bleiben (kein Add/Delete von Überschriften/Fließzeilen) —
 *  bei Abweichung wird NICHT still verschoben, sondern ein Klartextfehler geliefert. Nur
 *  Bullet-Zeilen (Präfix „- ") dürfen frei geändert/hinzugefügt/entfernt werden. */
function textZuEntwurf(text: string, bloecke: any[]): { entwurf: any[] } | { fehler: string } {
  const zeilen = text.split('\n')
  let idx = 0
  const entwurf: any[] = []
  for (const b of bloecke) {
    if ('anchor_i' in b) {
      const texte: string[] = []
      while (idx < zeilen.length && zeilen[idx].startsWith('- ')) {
        texte.push(zeilen[idx].slice(2))
        idx++
      }
      entwurf.push({ anchor_i: b.anchor_i, bullet_texte: texte })
      continue
    }
    // Ein Word-Absatz kann MEHRZEILIG sein: Ein weicher Umbruch (Shift+Enter, `<w:br/>`) trennt
    // zwei Zeilen INNERHALB eines Absatzes, python-docx liefert ihn als EINEN Block mit `\n`.
    // Im Textarea erscheint er dadurch über mehrere Zeilen — der Parser muss genau so viele
    // wieder einsammeln, sonst verrutscht ab hier die Zuordnung Zeile↔Block.
    // Beobachtet 10.09.2026: Zwei Unterpunkte standen in base_en.docx in EINEM Absatz statt in
    // zweien. Mehrere Entwürfe liessen sich dadurch nicht mehr speichern — die Fehlermeldung
    // zeigte auf den zweiten Unterpunkt, obwohl dort nichts falsch war: Der Parser war schlicht
    // eine Zeile voraus und erwartete bereits die nächste Überschrift.
    const zeilenImBlock = String(b.text ?? '').split('\n').length
    if (idx + zeilenImBlock > zeilen.length) {
      return { fehler: `Zeile fehlt (erwartet: „${b.text.slice(0, 40)}…") — nur Bullet-Zeilen („- ") dürfen frei hinzugefügt/entfernt werden.` }
    }
    let zeile = zeilen.slice(idx, idx + zeilenImBlock).join('\n')
    const istUeberschrift = String(b.style || '').startsWith('Heading')
    if (istUeberschrift) {
      if (!zeile.startsWith('### ')) {
        return { fehler: `Überschrift-Markierung „### " fehlt vor „${zeile.slice(0, 40)}…" — bitte nicht entfernen.` }
      }
      zeile = zeile.slice(4)
    } else if (zeile.startsWith('- ') || zeile.startsWith('### ')) {
      return { fehler: `Zeile „${zeile.slice(0, 40)}…" darf kein „- "/„### "-Präfix haben — nur Überschriften bzw. Bullet-Zeilen dürfen das. Wurde eine Überschrift/Fließzeile gelöscht?` }
    }
    entwurf.push({ i: b.i, text: zeile })
    idx += zeilenImBlock
  }
  if (zeilen.slice(idx).some((z) => z.trim())) {
    return { fehler: 'Zusätzliche Zeile am Ende gefunden, die zu keiner Überschrift/keinem Absatz gehört — nur Bullet-Zeilen („- ") dürfen frei hinzugefügt werden.' }
  }
  return { entwurf }
}

/** CV-Editier-Checkpoint (Phase 46 Stufe B, Umbau Phase 48 Stufe B): zeigt die jüngste CVVersion
 *  mit entwurf_text unter „Dateien & Dokumente" — solange status=entwurf editierbar, danach nur
 *  noch Links + „erneut erstellen". EIN Textarea statt Absatz-Felder: Überschriften als `### `,
 *  Bullets als `- ` markiert; Bullet-Zeilen dürfen frei geändert/hinzugefügt/entfernt werden,
 *  Überschriften/Fließtext bleiben strikt in-place (s. `buildBloecke`/`textZuEntwurf` oben und
 *  `cv_export.py::entwurf_zurueckschreiben`). */
/** Editor für den CV-Entwurf (Phase 46 Stufe B). P2-45 (25.09.2026): auch nach „CV erstellen"
 *  editierbar — der gespeicherte Entwurfstext überlebt den Export, `cv_export.entwurf_anwenden`
 *  schreibt ihn in die fertige `.docx` zurück, und Umbenennen/PDF/ATS sind idempotent. Zugeklappt
 *  startet die fertige Version weiterhin (die Datei ist der Normalfall, nicht die Nachbearbeitung). */
function CvEntwurfFenster({ cv, jobId, onSaved }: { cv: any; jobId: number; onSaved: () => void }) {
  const istFertig = cv.status === 'fertig'
  const [open, setOpen] = useState(!istFertig)
  const [bloecke] = useState<any[]>(() => {
    try { return buildBloecke(JSON.parse(cv.entwurf_text || '[]')) } catch { return [] }
  })
  const [text, setTextRaw] = useState(() => bloeckeZuText(bloecke))
  const [original, setOriginal] = useState(text)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const dirty = text !== original
  const zeilenAnzahl = text.split('\n').filter((z) => z.trim()).length

  const setText = (v: string) => { setTextRaw(v); if (err) setErr(null) }

  const save = async () => {
    const geparst = textZuEntwurf(text, bloecke)
    if ('fehler' in geparst) { setErr(geparst.fehler); return }
    setSaving(true); setErr(null)
    try {
      await api(`/cv-versions/${cv.id}/entwurf`, { method: 'PATCH', body: JSON.stringify({ entwurf_text: geparst.entwurf }) })
      setOriginal(text)
      setSaved(true); setTimeout(() => setSaved(false), 2000)
    } catch (e: any) { setErr(e?.message || 'Speichern fehlgeschlagen') }
    finally { setSaving(false) }
  }

  return (
    <div className="mt-3 rounded-xl border border-slate-200">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm hover:bg-slate-50">
        <span className="text-slate-400">{open ? '▾' : '▸'}</span>
        <span className="font-medium text-brand-navy">
          {istFertig ? 'CV fertig — Word/PDF/ATS erzeugt' : 'CV-Entwurf bearbeiten'}
        </span>
        <span className="text-xs text-slate-400">({zeilenAnzahl} Zeilen)</span>
      </button>
      {open && (
        <div className="space-y-3 border-t border-slate-100 p-4">
          {/* P2-45: Das Textfeld gibt es in BEIDEN Zuständen — Vorgabe vom 25.09.: Änderungen
              sollen jederzeit in diesem Fenster möglich sein. Im fertigen Zustand stehen die Datei-Links
              darüber; der Lauf darunter baut Word/PDF/ATS aus dem gespeicherten Stand neu. */}
          {istFertig && (
            <div className="flex flex-wrap gap-3 text-sm">
              <a href={artifactUrl(cv.file_path)} className="text-brand-cyan hover:underline">Word öffnen</a>
              <a href={artifactUrl(cv.file_path, true)} className="text-brand-cyan hover:underline">⬇ Word</a>
              {cv.pdf_path && <a href={artifactUrl(cv.pdf_path)} className="text-brand-cyan hover:underline">PDF ansehen</a>}
              {cv.pdf_path && <a href={artifactUrl(cv.pdf_path, true)} className="text-brand-cyan hover:underline">⬇ PDF</a>}
              {cv.ats_scan_path && <a href={artifactUrl(cv.ats_scan_path)} className="text-brand-cyan hover:underline">ATS-Scan öffnen</a>}
            </div>
          )}
          <div className="text-xs text-slate-400">
            <code className="rounded bg-slate-100 px-1">### Überschrift</code> nicht entfernen · <code className="rounded bg-slate-100 px-1">- Bullet</code> frei änderbar/hinzufügbar/entfernbar · sonstige Zeilen: Fließtext (in-place)
          </div>
          {bloecke.length === 0 ? (
            <div className="text-sm text-slate-400">Kein editierbarer Entwurf-Text vorhanden.</div>
          ) : (
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={26} spellCheck={false}
              className="w-full rounded-lg border border-slate-300 px-2.5 py-2 font-mono text-xs leading-relaxed focus:border-brand-cyan focus:outline-none" />
          )}
          <div className="flex items-center gap-2 border-t border-slate-100 pt-3">
            <button onClick={save} disabled={saving || !dirty}
              className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
              {saving ? 'Speichern…' : 'Speichern'}
            </button>
            {saved && <span className="text-sm text-emerald-600">✓ Gespeichert</span>}
          </div>
          {err && <div className="rounded-lg bg-rose-50 p-2 text-xs text-rose-700">{err}</div>}
          <div className="border-t border-slate-100 pt-3">
            {dirty ? (
              <div className="rounded-lg bg-amber-50 p-2 text-xs text-amber-800">
                Ungespeicherte Änderungen — erst „Speichern", dann den Lauf starten.
              </div>
            ) : (
              <AgentTaskButton kind="cv-erstellen" jobId={jobId} onFinished={onSaved}
                label={istFertig ? 'CV neu erstellen (Word + PDF + ATS)' : 'CV erstellen (Word + PDF + ATS)'} />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/** Anschreiben-Editor (Phase 48 Stufe A): Inline-Textfenster für `Application.cover_letter_text`,
 *  Vorbild `CvEntwurfFenster` — anders als der CV-Entwurf OHNE Status-Gate (freier Text, jederzeit
 *  editierbar, auch nach bereits erzeugtem Word/PDF). */
function CoverLetterEditor({ application, jobId, onSaved }: { application: any; jobId: number; onSaved: () => void }) {
  const [open, setOpen] = useState(true)
  const [text, setText] = useState(application.cover_letter_text || '')
  const [original, setOriginal] = useState(text)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [loadingDocx, setLoadingDocx] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const dirty = text !== original

  // Phase 52 Stufe B: kein `key` am Aufruf (anders als CvEntwurfFenster — dort legt jeder
  // cv-match eine NEUE CVVersion-Row an, hier wird dieselbe Application-Row überschrieben, ihre
  // id bleibt konstant; Application hat auch kein updated_at). Stattdessen gezielter Sync: ein
  // frischer Lauf (anschreiben-erstellen) aktualisiert application.cover_letter_text über load()
  // (29 Aufrufstellen im Job-Detail) — das Fenster übernimmt den neuen Text automatisch, AUSSER
  // es steht noch Ungespeichertes im Feld (dirty gewinnt, s. Bedingung unten).
  const extern = application.cover_letter_text || ''
  useEffect(() => {
    if (text !== original) return
    setText(extern); setOriginal(extern)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [extern])
  const externGeaendert = dirty && extern !== original

  const uebernehmen = () => { setText(extern); setOriginal(extern) }

  const save = async () => {
    setSaving(true); setErr(null)
    try {
      await api(`/applications/${application.id}`, { method: 'PATCH', body: JSON.stringify({ cover_letter_text: text }) })
      setOriginal(text)
      setSaved(true); setTimeout(() => setSaved(false), 2000)
    } catch (e: any) { setErr(e?.message || 'Speichern fehlgeschlagen') }
    finally { setSaving(false) }
  }

  const ausDocxLaden = async () => {
    setLoadingDocx(true); setErr(null)
    try {
      const r = await api<{ text: string }>(`/applications/${application.id}/cover-letter-text-from-docx`)
      setText(r.text)
    } catch (e: any) { setErr(e?.message || 'Laden fehlgeschlagen') }
    finally { setLoadingDocx(false) }
  }

  return (
    <div className="mt-3 rounded-xl border border-slate-200">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm hover:bg-slate-50">
        <span className="text-slate-400">{open ? '▾' : '▸'}</span>
        <span className="font-medium text-brand-navy">Anschreiben bearbeiten</span>
      </button>
      {open && (
        <div className="space-y-3 border-t border-slate-100 p-4">
          {!text && application.cover_letter_path && (
            <button onClick={ausDocxLaden} disabled={loadingDocx}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40">
              {loadingDocx ? 'Lädt…' : 'Text aus vorhandener .docx laden'}
            </button>
          )}
          {externGeaendert && (
            <div className="flex items-center justify-between gap-2 rounded-lg bg-amber-50 p-2 text-xs text-amber-800">
              <span>Ein neuer Lauf hat das Anschreiben ersetzt — deine ungespeicherten Änderungen stehen noch hier.</span>
              <button onClick={uebernehmen} className="shrink-0 rounded-lg border border-amber-300 px-2 py-1 font-medium text-amber-800 hover:bg-amber-100">
                Neuen Text übernehmen
              </button>
            </div>
          )}
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={24}
            placeholder="Noch kein Anschreiben-Text vorhanden."
            className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none" />
          <div className="flex items-center gap-2 border-t border-slate-100 pt-3">
            <button onClick={save} disabled={saving || !dirty}
              className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
              {saving ? 'Speichern…' : 'Anschreiben speichern'}
            </button>
            {saved && <span className="text-sm text-emerald-600">✓ Gespeichert</span>}
            {err && <span className="text-sm text-rose-600">{err}</span>}
          </div>
          <div className="border-t border-slate-100 pt-3">
            {dirty ? (
              <div className="rounded-lg bg-amber-50 p-2 text-xs text-amber-800">
                Ungespeicherte Änderungen — erst „Anschreiben speichern", dann „Word + PDF erzeugen".
              </div>
            ) : text ? (
              <AgentTaskButton kind="cover-letter-render" jobId={jobId} label="Word + PDF erzeugen" onFinished={onSaved} />
            ) : null}
          </div>
        </div>
      )}
    </div>
  )
}

function Field({ label, value, href, fallback, warn }: {
  label: string; value: any; href?: string; fallback?: string; warn?: string
}) {
  const leer = value === null || value === undefined || value === ''
  if (leer && !fallback) return null                       // bisheriges Verhalten
  const anzeige = leer ? fallback : String(value)
  return (
    <div className="flex gap-2 py-1 text-sm">
      <div className="w-40 shrink-0 text-slate-400">{label}</div>
      <div className={leer ? 'italic text-slate-400' : 'text-slate-700'}>
        {href && !leer
          ? <a href={href} target="_blank" rel="noreferrer" className="break-all text-brand-cyan hover:underline" title={href}>{anzeige}</a>
          : anzeige}
        {warn && <span className="ml-1 cursor-help" title={warn}>⚠️</span>}
      </div>
    </div>
  )
}

type Edit = { next_step: string; notes: string; follow_up_date: string }

export default function JobDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  // P2-51: Umkreis-Tab dynamisch aus den Einstellungen statt fest „<Stadt> +100km". MUSS vor
  // dem frühen return unten stehen (Hook-Reihenfolge).
  const suchTabs = useSuchTabs()
  const [data, setData] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [statusErr, setStatusErr] = useState<string | null>(null)
  const [edit, setEdit] = useState<Edit>({ next_step: '', notes: '', follow_up_date: '' })
  const [fuSaving, setFuSaving] = useState(false)
  const [fuSaved, setFuSaved] = useState(false)
  const [fuErr, setFuErr] = useState<string | null>(null)
  const [showIvForm, setShowIvForm] = useState(false)
  const [showTrForm, setShowTrForm] = useState(false)
  const [showTrUpload, setShowTrUpload] = useState(false)
  const [ivForm, setIvForm] = useState<any>({ art: 'HR-Screen', runde: '', scheduled_at: '', interviewer: '', notes: '', gegenueber: '', vor_ort: false })
  const [trForm, setTrForm] = useState<any>({ title: '', interview_id: '', recorded_at: '', language: 'DE', content: '', kontakt: '', neu_runde: '', neu_art: '' })
  const [trUpload, setTrUpload] = useState<any>({ file: null as File | null, kontakt: '', recorded_at: '', interview_id: '', title: '', neu_runde: '', neu_art: '' })
  const [trUploading, setTrUploading] = useState(false)
  const [trUploadErr, setTrUploadErr] = useState<string | null>(null)
  const [dragActive, setDragActive] = useState(false)
  const [pending, setPending] = useState<Pending[]>([])
  const [uploading, setUploading] = useState(false)
  const [fileErr, setFileErr] = useState<string | null>(null)
  const [debriefTasks, setDebriefTasks] = useState<Record<string, any>>({})
  const [openEmail, setOpenEmail] = useState<number | null>(null)
  // P2-41: Vorbelegung des Pakethäkchens „mit Anschreiben" aus Einstellungen.unterlagen.anschreiben.
  const [mitAnschreiben, setMitAnschreiben] = useState<boolean>(false)
  // Eckdaten-Edit-Modus (Phase 20)
  const [eckEdit, setEckEdit] = useState(false)
  const [eck, setEck] = useState<any>({})
  const [eckSaving, setEckSaving] = useState(false)
  const [eckSaved, setEckSaved] = useState(false)
  const [eckUrlErr, setEckUrlErr] = useState(false)
  const [eckCareerUrlErr, setEckCareerUrlErr] = useState(false)
  const [eckErr, setEckErr] = useState<string | null>(null)
  // Notizen & Verlauf (Phase 24 A) — eigener State, lädt separat über /jobs/{id}/log
  const [log, setLog] = useState<any[]>([])
  const [logInput, setLogInput] = useState('')
  // Stelle fragen (KI) (Phase 28 F) — eigener State, lädt separat über /jobs/{id}/chat
  const [chat, setChat] = useState<any[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatTask, setChatTask] = useState<any>(null)   // laufende Frage (Poll-Ziel)
  const [chatErr, setChatErr] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const { refresh } = useReviewCount()
  // P2-50: Startpunkt der Routenplanung kommt aus dem Profil statt einer festen Adresse.
  const adresse = useProfilAdresse()

  const loadLog = () => api<any[]>(`/jobs/${id}/log`).then(setLog).catch(() => {})
  const loadChat = () => api<any[]>(`/jobs/${id}/chat`).then(setChat).catch(() => {})
  // Phase 82 (Befund vom 12.08.): laufende KI-Frage nach einem Reload wiederfinden —
  // chatTask lebte bisher nur im Speicher, ein Reload kappte den Bezug und der nächste Klick
  // brachte nur noch den 409 „läuft bereits" ohne Weg zum Abbrechen. Nur bei queued/running
  // übernehmen — das bestehende Polling (useEffect weiter unten) greift dann von selbst.
  const loadChatTask = () =>
    api<any[]>(`/tasks?job_id=${id}&kinds=job-frage&limit=1`)
      .then((r) => { const t = r[0]; if (t && ['queued', 'running'].includes(t.status)) setChatTask(t) })
      .catch(() => {})

  const load = () => {
    setErr(null)
    api(`/jobs/${id}`).then((d: any) => {
      setData(d)
      setEdit({
        next_step: d.job.next_step || '',
        notes: d.job.notes || '',
        follow_up_date: d.job.follow_up_date || '',
      })
    }).catch((e) => setErr(String(e)))
    loadLog()
    loadChat()
    loadChatTask()
  }
  useEffect(() => { load() }, [id])

  // Laufende Frage (KI-Chat, Phase 28 F) verfolgen. MUSS vor dem frühen return stehen.
  useEffect(() => {
    if (!chatTask || !['queued', 'running'].includes(chatTask.status)) return
    const iv = setInterval(async () => {
      try {
        const neu = await api<any>(`/tasks/${chatTask.id}`)
        setChatTask(neu)
        if (neu.status === 'done') { setChatTask(null); await Promise.all([loadChat(), loadLog()]) }
        if (neu.status === 'failed') setChatErr(neu.error || 'Frage fehlgeschlagen')
      } catch { /* nächster Tick */ }
    }, 3000)
    return () => clearInterval(iv)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatTask?.id, chatTask?.status])

  const askChat = async () => {
    if (!chatInput.trim()) return
    setChatErr(null)
    const frage = chatInput.trim()
    setChatInput('')
    try {
      const res = await api<any>(`/jobs/${id}/chat`, { method: 'POST', body: JSON.stringify({ frage }) })
      setChat((c) => [...c, res.user_row])
      setChatTask(res.task)
    } catch (e: any) {
      const msg = e?.message || 'Frage konnte nicht gestellt werden'
      setChatErr(msg)
      setChatInput(frage)
      // Phase 82: 409 „'job-frage' läuft für diesen Job bereits (Task <id>)" (main.py::_guard_doppellauf)
      // — Task-Id per Regex ziehen und laden, damit der Abbrechen-Button genau dort erscheint, wo
      // der Nutzer feststeckt, statt nur über das Task-Center erreichbar zu sein. Fehlermeldung
      // bleibt zusätzlich sichtbar (chatErr oben).
      const m = /Task (\d+)/.exec(msg)
      if (m) {
        api<any>(`/tasks/${m[1]}`)
          .then((t) => { if (['queued', 'running'].includes(t.status)) setChatTask(t) })
          .catch(() => {})
      }
    }
  }

  // Aktiver Lauf = wirklich queued/running — ein `failed`-Task blieb bisher als chatTask stehen
  // (der Poll-Fehlerpfad unten setzt ihn nicht zurück auf null) und sperrte das Eingabefeld dauerhaft.
  const chatAktiv = !!chatTask && ['queued', 'running'].includes(chatTask.status)

  const cancelChat = async () => {
    if (!chatTask) return
    await api(`/tasks/${chatTask.id}/cancel`, { method: 'POST' }).catch(() => {})
    setChatTask(null)
    await loadChat()
  }

  // Laufende Debriefs verfolgen. MUSS vor dem frühen return stehen (Hook-Reihenfolge).
  useEffect(() => {
    const laufend = Object.entries(debriefTasks).filter(([, t]: any) => ['queued', 'running'].includes(t.status))
    if (!laufend.length) return
    const iv = setInterval(async () => {
      for (const [tid, t] of laufend) {
        try {
          const neu = await api<any>(`/tasks/${(t as any).id}`)
          setDebriefTasks((d) => ({ ...d, [tid]: neu }))
          if (neu.status === 'done') load()
        } catch { /* nächster Tick */ }
      }
    }, 3000)
    return () => clearInterval(iv)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(Object.entries(debriefTasks).map(([k, t]: any) => [k, t.status]))])

  // P2-41: Einstellungen-Vorbelegung fürs Pakethäkchen einmalig beim Mount laden.
  // MUSS vor dem frühen return stehen (Hook-Reihenfolge).
  useEffect(() => {
    api<Einstellungen>('/einstellungen').then((e) => setMitAnschreiben(!!e.unterlagen?.anschreiben)).catch(() => {})
  }, [])

  if (!data) {
    if (err) return <div className="rounded-lg bg-rose-50 p-4 text-rose-700">Fehler: {err}</div>
    return <div className="text-slate-400">Lade…</div>
  }
  const { job, company, contacts, application, emails, cv_versions, interviews, transcripts, files } = data
  const today = isoTag()
  const fuOverdue = job.follow_up_date && job.follow_up_date <= today

  // Workflow-Zustände (Phase 16, abgeleitet — keine neuen API-Felder).
  const fitDa = !!company?.fit_analysis_path
  const cvDa = (cv_versions?.length || 0) > 0
  // Phase 46 Stufe B: „fertig" ist enger als „existiert" — ein reiner Entwurf (status=entwurf,
  // noch kein Word/PDF/ATS) zählt nicht als fertig. Seit P2-41 sperrt das nichts mehr (das
  // Anschreiben ist optional), es steuert nur den Hinweis „Entwurf wartet auf Bearbeitung".
  const cvFertigDa = (cv_versions || []).some((c: any) => c.status === 'fertig')
  const anschreibenDa = !!application?.cover_letter_path
  // Phase 40: Beirats-Check ist eine echte JobFile-Row (kind="Beirats-Check", kein neues
  // API-Feld) — jüngste Zeile zieht (gleiches reduce-Muster wie cvNeu unten).
  const beiratFiles = (files || []).filter((f: any) => f.kind === 'Beirats-Check')
  const beiratNeu = beiratFiles.reduce((a: any, b: any) => (a && a.id > b.id ? a : b), null)
  const beiratDa = !!beiratNeu

  // Artefakt-Links je Workflow-Schritt (Phase 18 D2) — erscheinen nach `done` unter der
  // Abschlussmeldung des AgentTaskButton. Nach onFinished/load() sind die Pfade frisch.
  const cvNeu = (cv_versions || []).reduce((a: any, b: any) => (a && a.id > b.id ? a : b), null)
  const fitLinks = company?.fit_analysis_path
    ? [{ href: artifactUrl(company.fit_analysis_path), label: '🏢 Company-Fit-Dashboard öffnen' }]
    : undefined
  // Phase 46 Stufe B: WfStep 3 (CV-Match) liefert einen ENTWURF (noch kein Word/PDF) — der Link
  // unter der Abschlussmeldung zeigt deshalb aufs Match-Dashboard, nicht auf CV-Downloads (die
  // gibt's erst nach „CV erstellen", s. CvEntwurfFenster in „Dateien & Dokumente").
  const matchLinks = cvNeu?.match_dashboard_path
    ? [{ href: artifactUrl(cvNeu.match_dashboard_path), label: '📊 Match-Dashboard öffnen' }]
    : undefined
  const anschreibenLinks = application?.cover_letter_path
    ? [
        { href: artifactUrl(application.cover_letter_path, true), label: '⬇ Anschreiben (.docx)', download: true },
        ...(application.cover_letter_pdf_path ? [{ href: artifactUrl(application.cover_letter_pdf_path, true), label: '⬇ Anschreiben (.pdf)', download: true }] : []),
        ...(application.cover_letter_pdf_path ? [{ href: artifactUrl(application.cover_letter_pdf_path), label: 'Ansehen' }] : []),
      ]
    : undefined

  const setStatus = async (status: string) => {
    setSaving(true); setStatusErr(null)
    try {
      await api(`/jobs/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) })
      await load()
      refresh()
    } catch (e: any) { setStatusErr(e?.message || 'Speichern fehlgeschlagen') }
    finally { setSaving(false) }
  }

  const setGutFeeling = async (v: number | null) => {
    setSaving(true); setStatusErr(null)
    try {
      await api(`/jobs/${id}`, { method: 'PATCH', body: JSON.stringify({ gut_feeling: v }) })
      await load()
    } catch (e: any) { setStatusErr(e?.message || 'Speichern fehlgeschlagen') }
    finally { setSaving(false) }
  }

  const addLogEntry = async () => {
    if (!logInput.trim()) return
    await api(`/jobs/${id}/log`, { method: 'POST', body: JSON.stringify({ eintrag: logInput.trim() }) })
    setLogInput('')
    await loadLog()
  }

  // Fahrtzeit pragmatisch: Maps-Route von zu Hause, nur bei echten Vor-Ort-Standorten sinnvoll
  const routeUrl = job?.location && !/remote/i.test(job.location)
    ? mapsRouteUrl(adresse, job.location)
    : null

  const saveFollowup = async () => {
    setFuSaving(true); setFuErr(null)
    try {
      await api(`/jobs/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          next_step: edit.next_step || null,
          notes: edit.notes || null,
          follow_up_date: edit.follow_up_date || null,
        }),
      })
      await load()
      refresh()
      setFuSaved(true)
      setTimeout(() => setFuSaved(false), 2000)
    } catch (e: any) { setFuErr(e?.message || 'Speichern fehlgeschlagen') }
    finally { setFuSaving(false) }
  }
  const fuDirty = edit.next_step !== (job.next_step || '') ||
    edit.notes !== (job.notes || '') ||
    edit.follow_up_date !== (job.follow_up_date || '')

  // ── Eckdaten-Edit (Phase 20) ──
  // Ausgangswerte aus job/company (Anzeige bevorzugt die *_raw-Felder).
  const eckFromData = () => ({
    seniority: job.seniority_raw || job.seniority || '',
    work_model: job.work_model || '',
    relocation_needed: job.relocation_needed || '',
    plan_ab: job.plan_ab || '',
    situation: company ? (company.situation_raw || company.situation || '') : '',
    tab: job.tab || '',
    portal: job.portal || '',
    url: job.url || '',
    career_url: job.career_url ?? '',
    portal_closed: job.portal_closed ? '1' : '0',
    salary: job.salary || '',
    published_date: job.published_date || '',
    found_date: job.found_date || '',
    status_raw: job.status_raw || '',
  })
  const eckOrig = eckFromData()
  const eckDirty = eckEdit && Object.keys(eckOrig).some((k) => (eck[k] ?? '') !== (eckOrig as any)[k])
  const urlGeaendert = eck.url !== eckOrig.url
  const startEck = () => { setEck(eckFromData()); setEckUrlErr(false); setEckCareerUrlErr(false); setEckEdit(true) }

  const saveEck = async () => {
    if (eck.url && !/^https?:\/\//i.test(eck.url)) { setEckUrlErr(true); return }
    if (eck.career_url && !/^https?:\/\//i.test(eck.career_url)) { setEckCareerUrlErr(true); return }
    setEckSaving(true); setEckErr(null)
    const jobKeys = ['seniority', 'work_model', 'relocation_needed', 'plan_ab', 'tab', 'portal',
      'url', 'salary', 'published_date', 'found_date', 'status_raw', 'career_url', 'portal_closed']
    const jobPatch: any = {}
    jobKeys.forEach((k) => {
      if ((eck[k] ?? '') !== (eckOrig as any)[k]) {
        jobPatch[k] = k === 'portal_closed' ? (eck[k] === '1' ? 1 : 0) : (eck[k] || null)
      }
    })
    // Zwei sequenzielle Requests: scheitert erst der zweite, sind die Job-Felder bereits
    // gespeichert — das muss sichtbar werden statt stumm zu bleiben (P2-22 Sonderfall saveEck).
    let jobGespeichert = false
    try {
      if (Object.keys(jobPatch).length) {
        await api(`/jobs/${id}`, { method: 'PATCH', body: JSON.stringify(jobPatch) })
      }
      jobGespeichert = true
      if (company && (eck.situation ?? '') !== eckOrig.situation) {
        await api(`/companies/${company.id}`, { method: 'PATCH', body: JSON.stringify({ situation: eck.situation || null }) })
      }
      await load()
      refresh()
      setEckEdit(false); setEckSaved(true)
      setTimeout(() => setEckSaved(false), 2000)
    } catch (e: any) {
      const msg = e?.message || 'Speichern fehlgeschlagen'
      setEckErr(jobGespeichert ? `Job-Felder gespeichert — Situation nicht gespeichert: ${msg}` : msg)
      // Job-Felder können bereits persistiert sein — neu laden, sonst zeigt die Eckdaten-Ansicht
      // nach Abbrechen fälschlich den alten Stand, obwohl der Server schon den neuen hat.
      await load()
      refresh()
    } finally {
      setEckSaving(false)
    }
  }
  const eckInp = 'w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none'
  const eckRow = (label: string, input: ReactNode, title?: string) => (
    <div className="flex gap-2 py-1 text-sm" key={label}>
      <div className="w-40 shrink-0 text-slate-400" title={title}>{label}</div>
      <div className="min-w-0 flex-1">{input}</div>
    </div>
  )
  const eckSel = (key: string, opts: string[]) => (
    <select className={eckInp} value={eck[key] || ''} onChange={(e) => setEck({ ...eck, [key]: e.target.value })}>
      <option value="">–</option>
      {opts.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  )
  const eckTxt = (key: string, extra: any = {}) => (
    <input className={eckInp} value={eck[key] || ''} onChange={(e) => setEck({ ...eck, [key]: e.target.value })} {...extra} />
  )

  // ── Quellen-Konflikte (Phase 21): aus verify_note parsen → ⚠️ an der betroffenen Eckdaten-Zeile ──
  const warnFuer: Record<string, string> = {}
  if (job.verify_note && job.verify_note.includes('KONFLIKT')) {
    const re = /KONFLIKT\s+([^:]+):\s*([^|]+)/g
    // Feld-Name → Eckdaten-Zeilen-Label; unbekanntes Feld → Original-URL-Zeile (immer sichtbar).
    const LABEL_FUER: Record<string, string> = {
      arbeitsmodell: 'Arbeitsmodell', 'work model': 'Arbeitsmodell',
      seniorität: 'Seniorität', senioritaet: 'Seniorität', seniority: 'Seniorität',
    }
    let m: RegExpExecArray | null
    while ((m = re.exec(job.verify_note)) !== null) {
      const feld = m[1].trim()
      const text = `KONFLIKT ${feld}: ${m[2].trim()}`
      const label = LABEL_FUER[feld.toLowerCase()] || 'Original-URL'
      warnFuer[label] = warnFuer[label] ? `${warnFuer[label]}\n${text}` : text
    }
  }

  // ── Interviews & Transkripte ──
  const openIvForm = () => {
    // Erste Runde ist typischerweise ein HR-Screen, jede weitere eher ein Fachgespräch — der
    // Vorschlag spart den häufigsten Klick, ohne etwas festzulegen. `gegenueber` kommt aus der
    // Art (GEGENUEBER_ZU_ART), damit die KPI-Dimension nicht leer bleibt.
    const art = (interviews?.length || 0) === 0 ? 'HR-Screen' : 'Fachgespräch'
    setIvForm({ art, runde: String((interviews?.length || 0) + 1), scheduled_at: '', interviewer: '',
                notes: '', gegenueber: GEGENUEBER_ZU_ART[art] || '', vor_ort: false })
    setShowIvForm(true)
  }
  /** Artwechsel: zieht das passende Gegenüber mit — außer der Nutzer hat dort bewusst etwas
   *  anderes als den bisherigen Vorschlag stehen; dann bleibt seine Wahl unangetastet. */
  const artWechsel = (form: any, setForm: (f: any) => void, neueArt: string, feldArt = 'art', feldGegen = 'gegenueber') => {
    const alterVorschlag = GEGENUEBER_ZU_ART[form[feldArt]] || ''
    const eigeneWahl = form[feldGegen] && form[feldGegen] !== alterVorschlag
    setForm({ ...form, [feldArt]: neueArt,
              [feldGegen]: eigeneWahl ? form[feldGegen] : (GEGENUEBER_ZU_ART[neueArt] || '') })
  }
  const createInterview = async () => {
    await api(`/jobs/${id}/interviews`, {
      method: 'POST',
      body: JSON.stringify({
        art: ivForm.art, runde: Number(ivForm.runde) || undefined,
        scheduled_at: ivForm.scheduled_at || null,
        interviewer: ivForm.interviewer || null, notes: ivForm.notes || null,
        gegenueber: ivForm.gegenueber || null, vor_ort: ivForm.vor_ort,
      }),
    })
    setShowIvForm(false)
    await load()
  }
  const setIvStatus = async (ivId: number, status: string) => {
    await api(`/interviews/${ivId}`, { method: 'PATCH', body: JSON.stringify({ status }) })
    await load()
  }
  // Phase 69 (Stufe B) — Pflege-UI für bereits angelegte Gespräche (Muster setIvStatus:
  // sofortiges PATCH statt eines Speichern-Buttons).
  const setIvGegenueber = async (ivId: number, gegenueber: string) => {
    await api(`/interviews/${ivId}`, { method: 'PATCH', body: JSON.stringify({ gegenueber: gegenueber || null }) })
    await load()
  }
  const toggleIvVorOrt = async (iv: any) => {
    await api(`/interviews/${iv.id}`, { method: 'PATCH', body: JSON.stringify({ vor_ort: !iv.vor_ort }) })
    await load()
  }
  const deleteInterview = async (ivId: number) => {
    if (!window.confirm('Dieses Gespräch löschen? Zugeordnete Transkripte bleiben erhalten.')) return
    await api(`/interviews/${ivId}`, { method: 'DELETE' })
    await load()
  }
  /** Liefert die interview_id für ein Transkript-Formular und legt bei „Neue Runde…" die Runde
   *  vorher an (13.08.2026: bis dahin musste man den Dialog verlassen, das Gespräch an
   *  anderer Stelle anlegen und von vorn beginnen — ein Transkript gehört aber praktisch immer
   *  zu einer Runde, die es noch nicht gibt). Angelegt wird bewusst erst beim Speichern: ein
   *  abgebrochener Dialog soll keine leere Runde hinterlassen. Gesprächspartner und Datum kommen
   *  aus dem Formular, der Status ist „Absolviert" — ein Transkript gibt es nur zu einem
   *  geführten Gespräch. */
  const interviewIdFuer = async (form: any): Promise<number | null> => {
    if (form.interview_id !== NEUE_RUNDE) return form.interview_id ? Number(form.interview_id) : null
    const iv = await api<any>(`/jobs/${id}/interviews`, {
      method: 'POST',
      body: JSON.stringify({
        art: form.neu_art, runde: Number(form.neu_runde) || undefined,
        gegenueber: GEGENUEBER_ZU_ART[form.neu_art] || null,
        interviewer: form.kontakt || null,
        // recorded_at ist ein reines Datum, scheduled_at erwartet einen Zeitpunkt.
        scheduled_at: form.recorded_at ? `${form.recorded_at}T00:00` : null,
        status: 'Absolviert',
      }),
    })
    return iv?.id ?? null
  }
  const createTranscript = async () => {
    if (!trForm.content.trim()) return
    const ivId = await interviewIdFuer(trForm)
    await api(`/jobs/${id}/transcripts`, {
      method: 'POST',
      body: JSON.stringify({
        content: trForm.content, title: trForm.title || null,
        interview_id: ivId,
        recorded_at: trForm.recorded_at || null, language: trForm.language || null,
        kontakt: trForm.kontakt || null,
      }),
    })
    setTrForm({ title: '', interview_id: '', recorded_at: '', language: 'DE', content: '', kontakt: '', neu_runde: '', neu_art: '' })
    setShowTrForm(false)
    await load()
  }
  const deleteTranscript = async (tId: number) => {
    if (!window.confirm('Dieses Transkript löschen? Die Datei(en) wandern in den Papierkorb.')) return
    await api(`/transcripts/${tId}`, { method: 'DELETE' })
    await load()
  }

  // ── Transkript per Datei-Upload (Phase 30 Stufe C) ─────────────────────────
  const uploadTranscriptFile = async () => {
    if (!trUpload.file) return
    setTrUploading(true); setTrUploadErr(null)
    try {
      const ivId = await interviewIdFuer(trUpload)   // legt bei „Neue Runde…" vorher die Runde an
      const fd = new FormData()
      fd.append('file', trUpload.file)
      if (trUpload.kontakt) fd.append('kontakt', trUpload.kontakt)
      if (trUpload.recorded_at) fd.append('recorded_at', trUpload.recorded_at)
      if (ivId) fd.append('interview_id', String(ivId))
      if (trUpload.title) fd.append('title', trUpload.title)
      // NICHT über api() — das setzt einen JSON-Header, den multipart nicht verträgt (Muster wie uploadPend).
      const { res, body } = await apiUpload(`/api/jobs/${id}/transcripts/upload`, fd)
      if (!res.ok) throw new Error(body.detail || `${res.status} ${res.statusText}`)
      setTrUpload({ file: null, kontakt: '', recorded_at: '', interview_id: '', title: '' })
      setShowTrUpload(false)
      await load()
    } catch (e: any) {
      setTrUploadErr(e?.message || 'Upload fehlgeschlagen')
    } finally {
      setTrUploading(false)
    }
  }

  // ── Dateien (Phase 11) ────────────────────────────────────────────────────
  const queueFiles = (list: FileList | null) => {
    if (!list) return
    const heute = isoTag()
    const neu: Pending[] = Array.from(list).map((file) => ({
      file, kind: guessKind(file.name),
      kontakt: '', gespraechsart: 'Video-Call', interview_id: '', recorded_at: heute, auswerten: true,
    }))
    setPending((p) => [...p, ...neu])
  }

  const setPend = (idx: number, patch: Partial<Pending>) =>
    setPending((p) => p.map((x, i) => (i === idx ? { ...x, ...patch } : x)))
  const dropPend = (idx: number) => setPending((p) => p.filter((_, i) => i !== idx))

  const uploadPend = async (idx: number) => {
    const m = pending[idx]
    setUploading(true); setFileErr(null)
    try {
      const fd = new FormData()
      fd.append('file', m.file)
      fd.append('kind', m.kind)
      if (m.kind === 'Transkript') {
        if (m.kontakt) fd.append('kontakt', m.kontakt)
        if (m.gespraechsart) fd.append('gespraechsart', m.gespraechsart)
        if (m.interview_id) fd.append('interview_id', m.interview_id)
        if (m.recorded_at) fd.append('recorded_at', m.recorded_at)
      }
      // NICHT über api() — das setzt einen JSON-Header, den multipart nicht verträgt.
      const { res, body } = await apiUpload(`/api/jobs/${id}/files`, fd)
      if (!res.ok) throw new Error(body.detail || `${res.status} ${res.statusText}`)
      dropPend(idx)
      await load()
      // Auto-Auswertung: nur bei Transkript + angehakter Checkbox.
      if (m.kind === 'Transkript' && m.auswerten && body.transcript_id) {
        await startDebrief({ id: body.transcript_id, kontakt: m.kontakt, gespraechsart: m.gespraechsart })
      }
    } catch (e: any) {
      setFileErr(e?.message || 'Upload fehlgeschlagen')
    } finally {
      setUploading(false)
    }
  }

  const deleteFile = async (fileId: number) => {
    if (!window.confirm('Datei in den Papierkorb verschieben?')) return
    await api(`/files/${fileId}`, { method: 'DELETE' })
    await load()
  }

  // ── Generierte Artefakte löschen (Phase 32 A/C) — virt-<quelle>-<pk>-<slot> auflösen. ────────
  const deleteVirtualFile = async (f: any) => {
    const [, quelle, pk, slot] = String(f.id).split('-')   // 'virt-<quelle>-<pk>-<slot>'
    const text = slot === 'fit'
      ? `„${f.filename}" in den Papierkorb verschieben? Die Company-Fit-Analyse gilt für ALLE Stellen dieser Firma — sie verschwindet überall, nicht nur hier.`
      : `„${f.filename}" in den Papierkorb verschieben?`
    if (!window.confirm(text)) return
    await api(`/files/virtual/${quelle}/${pk}/${slot}`, { method: 'DELETE' })
    await load()
  }

  // ── Stelle löschen (Phase 32 B/C) — Zähler VOR dem confirm aus den geladenen Job-Daten bauen,
  // die Zähler aus der DELETE-Antwort kommen zu spät für den Bestätigungsdialog. ───────────────
  const deleteJob = async () => {
    const nDateien = files?.length || 0
    const nInterviews = interviews?.length || 0
    const nTranskripte = transcripts?.length || 0
    const text = `Stelle „${job.title}" bei ${job.company_name || '–'} löschen? Mit ihr wandern `
      + `${nDateien} Datei(en) in den Papierkorb; ${nInterviews} Interview(s), ${nTranskripte} `
      + `Transkript(e), Bewerbung und Verlauf werden entfernt. Der Eintrag bleibt unsichtbar als `
      + `Dublettenschutz erhalten.`
    if (!window.confirm(text)) return
    await api(`/jobs/${id}`, { method: 'DELETE' })
    navigate('/jobs')
  }

  // ── Gespräch-Debrief starten (Phase 11 Stufe C) ─────────────────────────────
  // Status zentral je transcript_id, damit Transkript-Liste UND Dateiliste denselben
  // laufenden Task zeigen und nicht zweimal starten (der Runner sperrt Doppelläufe je Job).
  const startDebrief = async (t: any) => {
    const cur = debriefTasks[t.id]
    if (cur && ['queued', 'running'].includes(cur.status)) return
    try {
      const r = await api<any>('/tasks', {
        method: 'POST',
        body: JSON.stringify({ kind: 'gespraech-debrief', job_id: Number(id),
          params: { transcript_id: t.id, kontakt: t.kontakt || '', gespraechsart: t.gespraechsart || '' } }),
      })
      setDebriefTasks((d) => ({ ...d, [t.id]: r.tasks ? r.tasks[0] : r }))
    } catch (e: any) {
      setFileErr(String(e?.message || e).includes('409')
        ? 'Ein Debrief für diese Stelle läuft bereits.' : (e?.message || 'Auswertung konnte nicht starten'))
    }
  }

  return (
    <div className="space-y-5">
      <Link to="/jobs" className="text-sm text-brand-cyan hover:underline">← Zurück zu Stellen</Link>

      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <ScoreBadge score={job.match_score} />
          <div>
            <h1 className="text-xl font-bold text-brand-navy">{job.title}</h1>
            <div className="text-slate-500">{job.company_name} · {job.location || '–'}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {job.follow_up_date && (
            <span className={`whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-medium ${
              fuOverdue ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700'}`}
              title="Follow-up fällig">⏰ {job.follow_up_date}</span>
          )}
          <StatusBadge status={job.status} />
          <VerifyBadge verifyNote={job.verify_note} verifiedAt={job.verified_at} />
          <DubletteBadge verifyNote={job.verify_note} />
          <NeuausschreibungBadge verifyNote={job.verify_note} />
          {job.url && (
            <a href={job.url} target="_blank" rel="noreferrer" className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-navy hover:brightness-95">
              Stelle öffnen ↗
            </a>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4">
          <Section title="Bewertung">
            <p className="whitespace-pre-wrap text-sm text-slate-700">{job.match_rationale || 'Keine Begründung erfasst.'}</p>
          </Section>

          <Section title="Eckdaten" right={!eckEdit
            ? <button onClick={startEck} className="text-xs text-brand-cyan hover:underline">✏️ Bearbeiten</button>
            : null}>
            {!eckEdit ? (
              <>
                <Field label="Seniorität" value={job.seniority_raw || job.seniority} warn={warnFuer['Seniorität']} />
                <Field label="Arbeitsmodell" value={job.work_model} warn={warnFuer['Arbeitsmodell']} />
                <Field label="Umzug nötig?" value={job.relocation_needed} />
                <Field label="Plan A/B/C" value={job.plan_ab} />
                <Field label="Situation" value={company?.situation_raw || company?.situation} />
                <Field label="Suche-Tab" value={job.tab} />
                <Field label="Portal" value={job.portal} />
                <Field label="Original-URL" value={job.url ? shortUrl(job.url) : null} href={job.url} fallback="–" warn={warnFuer['Original-URL']} />
                <Field label="Karriereseite" value={job.career_url ? shortUrl(job.career_url) : null} href={job.career_url || undefined} fallback="–" />
                {job.portal_closed ? (
                  <div className="flex gap-2 py-1 text-sm">
                    <div className="w-40 shrink-0 text-slate-400">Portal-Bewerbung</div>
                    <div className="text-rose-600">geschlossen — Bewerbung ggf. über die Karriereseite</div>
                  </div>
                ) : null}
                {job.availability_status ? (
                  <div className="flex gap-2 py-1 text-sm">
                    <div className="w-40 shrink-0 text-slate-400">Verfügbarkeit</div>
                    <div className={AVAILABILITY_LABELS[job.availability_status]?.cls || 'text-slate-600'}>
                      {AVAILABILITY_LABELS[job.availability_status]?.label || job.availability_status}
                      {job.availability_checked_at && ` · geprüft ${job.availability_checked_at}`}
                    </div>
                  </div>
                ) : null}
                <Field label="Gehalt" value={job.salary} fallback="keine Angabe" />
                <Field label="Veröffentlicht" value={job.published_date} />
                <Field label="Gefunden am" value={job.found_date} />
                <Field label="Status (Original)" value={job.status_raw} />
              </>
            ) : (
              <>
                {eckRow('Seniorität', eckTxt('seniority'))}
                {eckRow('Arbeitsmodell', eckSel('work_model', ['Remote', 'Hybrid', 'Onsite', 'Unbekannt']))}
                {eckRow('Umzug nötig?', eckSel('relocation_needed', ['Ja', 'Nein', 'Unklar']))}
                {eckRow('Plan A/B/C', eckSel('plan_ab', ['A', 'B', 'C']))}
                {eckRow('Situation', company
                  ? eckTxt('situation')
                  : <span className="italic text-slate-400" title="Keine Firma verknüpft">–</span>)}
                {/* P2-51: der aktuelle job.tab bleibt als Option sichtbar, auch wenn er (z. B. nach
                    einer Umkreis-Umbenennung) nicht mehr in der aktuellen Liste steht. */}
                {eckRow('Suche-Tab', eckSel('tab', job.tab && !suchTabs.includes(job.tab) ? [...suchTabs, job.tab] : suchTabs))}
                {eckRow('Portal', <>
                  <input className={eckInp} list="eck-portale" value={eck.portal || ''}
                    onChange={(e) => setEck({ ...eck, portal: e.target.value })} />
                  <datalist id="eck-portale">
                    {['LinkedIn', 'Indeed', 'StepStone', 'Xing', 'Glassdoor', 'Firmenseite', 'E-Mail', 'Initiativ']
                      .map((p) => <option key={p} value={p} />)}
                  </datalist>
                </>)}
                {eckRow('Original-URL', eckTxt('url', {
                  type: 'url', placeholder: 'https://…',
                  onChange: (e: any) => { setEck({ ...eck, url: e.target.value }); setEckUrlErr(false) },
                }))}
                {eckRow('Karriereseite', eckTxt('career_url', {
                  type: 'url', placeholder: 'https://…',
                  onChange: (e: any) => { setEck({ ...eck, career_url: e.target.value }); setEckCareerUrlErr(false) },
                }))}
                {eckRow('Portal geschlossen?', (
                  <select className={eckInp} value={eck.portal_closed || '0'}
                    onChange={(e) => setEck({ ...eck, portal_closed: e.target.value })}>
                    <option value="0">Nein</option>
                    <option value="1">Ja</option>
                  </select>
                ))}
                {eckRow('Gehalt', eckTxt('salary', { placeholder: 'z. B. 90.000–110.000 € p. a.' }))}
                {eckRow('Veröffentlicht', eckTxt('published_date', { type: 'date' }))}
                {eckRow('Gefunden am', eckTxt('found_date', { type: 'date' }), 'Systemwert — nur bei Bedarf ändern')}
                {eckRow('Status (Original)', eckTxt('status_raw'), 'Systemwert — Originaltext der Quelle')}
                {eckUrlErr && <div className="mt-1 text-xs text-rose-600">URL muss mit http:// oder https:// beginnen.</div>}
                {eckCareerUrlErr && <div className="mt-1 text-xs text-rose-600">Karriereseite: URL muss mit http(s):// beginnen.</div>}
                {urlGeaendert && job.verified_at &&
                  <div className="mt-1 text-xs text-amber-700">URL geändert — Verifikations-Badge wird zurückgesetzt.</div>}
                <div className="mt-2 flex gap-2">
                  <button onClick={saveEck} disabled={eckSaving || !eckDirty}
                    className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-semibold text-brand-aufAktion transition hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-50">
                    {eckSaving ? 'Speichert…' : 'Speichern'}
                  </button>
                  <button onClick={() => setEckEdit(false)}
                    className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">Abbrechen</button>
                </div>
              </>
            )}
            {eckErr && <div className="mt-1 rounded-lg bg-rose-50 p-2 text-xs text-rose-700">{eckErr}</div>}
            {eckSaved && <div className="mt-1 text-xs text-emerald-600">✓ Gespeichert</div>}
            <div className="mt-3 border-t border-slate-100 pt-3 text-right">
              <button onClick={deleteJob} className="text-xs text-slate-400 hover:text-rose-600">🗑 Stelle löschen</button>
            </div>
          </Section>

          <Section title={`Notizen & Verlauf (${log.length})`}>
            <div className="mb-3 flex gap-2">
              <input className="flex-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none"
                     value={logInput} placeholder="Notiz hinzufügen…"
                     onChange={(e) => setLogInput(e.target.value)}
                     onKeyDown={(e) => { if (e.key === 'Enter') addLogEntry() }} />
              <button onClick={addLogEntry} disabled={!logInput.trim()}
                      className="rounded-lg border border-brand-cyan/40 px-3 py-1.5 text-sm font-medium text-brand-navy hover:bg-brand-cyan/10 disabled:opacity-40">
                Hinzufügen
              </button>
            </div>
            {log.length === 0 ? (
              <div className="text-sm text-slate-400">Noch keine Einträge — Änderungen an Status/Follow-up erscheinen hier automatisch.</div>
            ) : (
              <div className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
                {log.map((l) => {
                  const lang = l.eintrag.length > 160 || (l.eintrag.match(/\n/g) || []).length > 1
                  const isChat = l.art === 'ki-chat'
                  const firstLine = l.eintrag.split('\n')[0]
                  const summary = (isChat ? '💬 ' : '') + (firstLine.length > 100 ? firstLine.slice(0, 100) + '…' : firstLine)
                  const badge = <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${l.art === 'auto' ? 'bg-slate-100 text-slate-500' : 'bg-brand-cyan/15 text-brand-navy'}`}>{l.art}</span>
                  const zeit = <span className="shrink-0 whitespace-nowrap tabular-nums text-xs text-slate-400">{logTime(l.created_at)}</span>
                  return (
                    <div key={l.id} className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm">
                      {lang ? (
                        <details>
                          <summary className="flex cursor-pointer items-start gap-2">
                            {zeit}{badge}<span className="text-slate-700">{summary}</span>
                          </summary>
                          <div className="mt-1.5 whitespace-pre-wrap pl-1 text-slate-700">{l.eintrag}</div>
                        </details>
                      ) : (
                        <div className="flex items-start gap-2">
                          {zeit}{badge}<span className="whitespace-pre-wrap text-slate-700">{l.eintrag}</span>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </Section>

          <Section title="Stelle fragen (KI)">
            {chat.length === 0 && !chatTask ? (
              <div className="text-sm text-slate-400">Stell eine Frage zu dieser Stelle — die KI antwortet aus den vorliegenden Analysen und Daten.</div>
            ) : (
              <div className="max-h-96 space-y-2 overflow-y-auto pr-1">
                {chat.map((c) => (
                  <div key={c.id} className={`flex ${c.rolle === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${c.rolle === 'user' ? 'bg-brand-cyan/10 text-brand-navy' : 'bg-slate-50 text-slate-700 whitespace-pre-wrap'}`}>
                      {c.text}
                      <div className="mt-1 text-[10px] text-slate-400">{logTime(c.created_at)}</div>
                    </div>
                  </div>
                ))}
                {chatAktiv && (
                  <div className="flex items-center justify-start gap-2">
                    <div className="max-w-[80%] rounded-lg bg-slate-50 px-3 py-2 text-sm italic text-slate-400">KI antwortet…</div>
                    <button onClick={cancelChat}
                      className="shrink-0 rounded-lg border border-slate-300 px-2.5 py-2 text-xs text-slate-600 hover:bg-slate-50">
                      Abbrechen
                    </button>
                  </div>
                )}
              </div>
            )}
            {chatErr && <div className="mt-2 text-sm text-rose-600">{chatErr}</div>}
            <div className="mt-3 flex gap-2">
              <input className="flex-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none"
                     value={chatInput} placeholder="Frage zu dieser Stelle…"
                     onChange={(e) => setChatInput(e.target.value)}
                     onKeyDown={(e) => { if (e.key === 'Enter') askChat() }} />
              <button onClick={askChat} disabled={!chatInput.trim() || chatAktiv}
                      className="rounded-lg border border-brand-cyan/40 px-3 py-1.5 text-sm font-medium text-brand-navy hover:bg-brand-cyan/10 disabled:opacity-40">
                Fragen
              </button>
            </div>
            {chat.length > 0 && (
              <div className="mt-2 text-[11px] text-slate-400">
                {/* P2-59: nur der Kurzname. Die Frage läuft über den Alias `sonnet` (agent_runner.PROMPTS),
                    also mit dem Sonnet, das die CLI gerade bereitstellt; eine feste Modellnummer würde hier veralten. */}
                Modell: Sonnet{chatTask?.cost_usd != null ? ` · $${chatTask.cost_usd.toFixed(3)}` : ''}
              </div>
            )}
          </Section>

          <Section title={`E-Mail-Verlauf (${emails?.length || 0})`}>
            {(!emails || emails.length === 0)
              ? <div className="text-sm text-slate-400">Noch keine zugeordneten E-Mails. Wird über den Gmail-Check (Phase 3) gefüllt.</div>
              : emails.map((e: any) => {
                const isOpen = openEmail === e.id
                return (
                  <div key={e.id} className="border-b border-slate-100 last:border-0">
                    <div onClick={() => setOpenEmail(isOpen ? null : e.id)}
                         className={`cursor-pointer py-2 text-sm hover:bg-brand-cyan/5 ${isOpen ? 'bg-brand-cyan/5' : ''}`}>
                      <div className="flex justify-between">
                        <span className="font-medium">{e.subject}</span>
                        <span className="text-slate-400">{e.category}</span>
                      </div>
                      <div className="text-slate-500">
                        {e.from_addr} · {e.received_at} {e.response_time_hours != null && `· ${e.response_time_hours}h`}
                        {e.reply_draft_at && <span className="ml-2 rounded-full bg-slate-200 px-1.5 py-0.5 text-[10px] font-bold text-slate-600">Entwurf</span>}
                      </div>
                    </div>
                    {isOpen && <EmailDetail email={e} jobId={job.id} onChanged={load} />}
                  </div>
                )
              })}
          </Section>

          <Section title={`Dateien & Dokumente (${files?.length || 0})`}>
            <div
              onDragOver={(e) => { e.preventDefault(); setDragActive(true) }}
              onDragLeave={() => setDragActive(false)}
              onDrop={(e) => { e.preventDefault(); setDragActive(false); queueFiles(e.dataTransfer.files) }}
              onClick={() => fileInput.current?.click()}
              className={`cursor-pointer rounded-lg border-2 border-dashed p-4 text-center text-sm transition ${
                dragActive ? 'border-brand-cyan bg-brand-cyan/5 text-brand-navy' : 'border-slate-300 text-slate-400 hover:border-slate-400'}`}
            >
              Dateien hierher ziehen oder <span className="font-medium text-brand-cyan">auswählen</span> (PDF, PPT, DOCX, Transkript …)
              <input ref={fileInput} type="file" multiple className="hidden"
                onChange={(e) => { queueFiles(e.target.files); e.target.value = '' }} />
            </div>

            {fileErr && <div className="mt-2 rounded-lg bg-rose-50 p-2 text-xs text-rose-700">{fileErr}</div>}

            {pending.map((m, i) => (
              <div key={i} className="mt-2 space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-2.5">
                <div className="flex items-center justify-between text-sm">
                  <span className="truncate font-medium text-brand-navy" title={m.file.name}>{m.file.name}</span>
                  <span className="ml-2 shrink-0 text-xs text-slate-400">{humanSize(m.file.size)}</span>
                </div>
                <select value={m.kind} onChange={(e) => setPend(i, { kind: e.target.value })}
                  className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none">
                  {FILE_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
                </select>
                {m.kind === 'Transkript' && (
                  <div className="space-y-2">
                    <div className="flex gap-2">
                      <input list={`kontakte-${i}`} placeholder="Gesprächspartner…" value={m.kontakt}
                        onChange={(e) => setPend(i, { kontakt: e.target.value })}
                        className="flex-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none" />
                      <datalist id={`kontakte-${i}`}>
                        {(contacts || []).map((c: any) => <option key={c.id} value={c.name} />)}
                      </datalist>
                      <select value={m.gespraechsart} onChange={(e) => setPend(i, { gespraechsart: e.target.value })}
                        className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none">
                        {GESPRAECHS_ARTEN.map((a) => <option key={a} value={a}>{a}</option>)}
                      </select>
                    </div>
                    <div className="flex gap-2">
                      <select value={m.interview_id} onChange={(e) => setPend(i, { interview_id: e.target.value })}
                        className="flex-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none">
                        <option value="">— Gespräch zuordnen (optional) —</option>
                        {(interviews || []).map((iv: any) => <option key={iv.id} value={iv.id}>Runde {iv.runde} · {iv.art}</option>)}
                      </select>
                      <input type="date" value={m.recorded_at} onChange={(e) => setPend(i, { recorded_at: e.target.value })}
                        className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none" />
                    </div>
                    <label className="flex items-center gap-2 text-xs text-slate-500">
                      <input type="checkbox" checked={m.auswerten} onChange={(e) => setPend(i, { auswerten: e.target.checked })}
                        className="h-4 w-4 rounded border-slate-300 accent-brand-cyan" />
                      nach Upload auswerten
                    </label>
                  </div>
                )}
                <div className="flex gap-2">
                  <button onClick={() => uploadPend(i)} disabled={uploading}
                    className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:opacity-40">
                    {uploading ? 'Lädt…' : 'Hochladen'}
                  </button>
                  <button onClick={() => dropPend(i)} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">Verwerfen</button>
                </div>
              </div>
            ))}

            <div className="mt-3 space-y-1">
              {(files || []).map((f: any) => (
                <div key={f.id} className="flex items-center gap-2 border-b border-slate-100 py-2 text-sm last:border-0">
                  <span className="shrink-0">{fileIcon(f.kind, f.filename)}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-medium text-brand-navy" title={f.filename}>{f.filename}</span>
                      {/* "generiert"-Chip = vom System erzeugt, kein manueller Upload. Beirats-Check ist
                          zwar technisch eine echte JobFile-Row (kein virtuelles Konstrukt — erlaubt mehrere
                          Prüf-Läufe über die Zeit), aber inhaltlich genauso agentengeneriert wie die
                          virtuellen Dashboards (Company-Fit, Stellenausschreibung) — kein Kind in FILE_KINDS,
                          also nie manuell hochgeladen. Bekommt daher denselben Chip. */}
                      {(() => {
                        const generiert = f.virtual || f.kind === 'Beirats-Check'
                        return (
                          <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs ${generiert ? 'bg-brand-cyan/15 text-brand-navy' : 'bg-slate-100 text-slate-600'}`}
                            title={generiert ? f.note : undefined}>{f.kind}{generiert ? ' · generiert' : ''}</span>
                        )
                      })()}
                    </div>
                    <div className="text-xs text-slate-400">{f.virtual ? (f.note || '') : humanSize(f.size_bytes)}{f.created_at ? ` · ${tagVon(f.created_at)}` : ''}</div>
                    {!f.virtual && f.transcript_id && (() => {
                      const lt = (transcripts || []).find((x: any) => x.id === f.transcript_id)
                      return lt ? <div className="mt-0.5"><DebriefBadge t={lt} task={debriefTasks[lt.id]} onStart={startDebrief} /></div> : null
                    })()}
                  </div>
                  <a href={artifactUrl(f.file_path)} className="shrink-0 text-xs text-brand-cyan hover:underline">Öffnen</a>
                  <a href={artifactUrl(f.file_path, true)} className="shrink-0 text-xs text-brand-cyan hover:underline">⬇</a>
                  <button onClick={() => (f.virtual ? deleteVirtualFile(f) : deleteFile(f.id))}
                    className="shrink-0 text-slate-400 hover:text-rose-600" title="In den Papierkorb">🗑</button>
                </div>
              ))}
              {(!files || files.length === 0) && <div className="text-sm text-slate-400">Noch keine Dateien angehängt.</div>}
            </div>

            {/* Phase 46 Stufe B: Editier-Checkpoint — sobald ein CV-Match gelaufen ist (Entwurf
                ODER schon fertig), Bearbeitungs-/Erstellungsfenster. `key=cv.id` erzwingt einen
                echten Remount bei einem frischen Entwurf (sonst bliebe lokaler Edit-State nach
                „neu matchen" stehen — React würde die Instanz sonst nur mit neuen Props updaten).
                Phase 52: der Anschreiben-Editor zieht direkt darunter ein — beide Editier-
                Checkpoints (CV-Entwurf, Anschreiben) liegen jetzt am selben Ort
                bei den erzeugten Dateien, in der breiten Mittelspalte statt der schmalen Leiste. */}
            {cvNeu && <CvEntwurfFenster key={cvNeu.id} cv={cvNeu} jobId={job.id} onSaved={load} />}
            {application && (application.cover_letter_path || application.cover_letter_text) && (
              <CoverLetterEditor application={application} jobId={job.id} onSaved={load} />
            )}
          </Section>
        </div>

        <div className="space-y-4">
          <Section title="Status ändern">
            <div className="flex flex-wrap gap-2">
              {STATUSES.map((s) => (
                <button
                  key={s}
                  disabled={saving}
                  onClick={() => setStatus(s)}
                  className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                    job.status === s ? 'bg-brand-cyan text-brand-aufAktion hover:bg-brand-cyanHover' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
            <div className="mt-3 border-t border-slate-100 pt-3">
              <div className="mb-1 text-xs font-medium text-slate-500">Bauchgefühl <span className="font-normal text-slate-400">· subjektiv, ergänzt den Zielstellen-Fit</span></div>
              <div className="flex items-center gap-0.5">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button key={n} disabled={saving}
                    onClick={() => setGutFeeling(job.gut_feeling === n ? null : n)}
                    className={`text-xl leading-none transition ${(job.gut_feeling || 0) >= n ? 'text-amber-400' : 'text-slate-200 hover:text-amber-200'}`}
                    title={`${n}/5${job.gut_feeling === n ? ' — erneut klicken zum Löschen' : ''}`}>
                    ★
                  </button>
                ))}
                {job.gut_feeling && <span className="ml-2 text-xs text-slate-400">{job.gut_feeling}/5</span>}
              </div>
            </div>
            {statusErr && <div className="mt-3 rounded-lg bg-rose-50 p-2 text-xs text-rose-700">{statusErr}</div>}
            {job.status === 'Absage' && (
              <div className="mt-3 border-t border-slate-100 pt-3">
                <CopyChip phrase={`Nach Absagegrund fragen für Job ${job.id}`} label="❓ Nach Grund fragen (Mail-Entwurf)" />
                <p className="mt-1 text-xs text-slate-400">Höfliche Feedback-Nachfrage als Gmail-Entwurf — füllt den Absagegrund mit echten Signalen.</p>
              </div>
            )}
          </Section>

          <Section title="Nächste Schritte & Follow-up">
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">Fälligkeitsdatum</label>
                <div className="flex items-center gap-2">
                  <input
                    type="date"
                    value={edit.follow_up_date}
                    onChange={(e) => setEdit({ ...edit, follow_up_date: e.target.value })}
                    className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none"
                  />
                  {edit.follow_up_date && (
                    <button onClick={() => setEdit({ ...edit, follow_up_date: '' })}
                            className="text-xs text-slate-400 hover:text-slate-600">✕ löschen</button>
                  )}
                  {fuOverdue && (
                    <span className="rounded-full bg-rose-100 px-2 py-0.5 text-xs font-medium text-rose-700">überfällig</span>
                  )}
                </div>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">Nächster Schritt</label>
                <input
                  type="text"
                  value={edit.next_step}
                  placeholder="z. B. Recruiter nachfassen, Interview vorbereiten…"
                  onChange={(e) => setEdit({ ...edit, next_step: e.target.value })}
                  className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">Notizen / Zwischenstände</label>
                <textarea
                  value={edit.notes}
                  rows={4}
                  placeholder="Gesprächsnotizen, Ansprechpartner, offene Punkte…"
                  onChange={(e) => setEdit({ ...edit, notes: e.target.value })}
                  className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none"
                />
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={saveFollowup}
                  disabled={fuSaving || !fuDirty}
                  className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {fuSaving ? 'Speichern…' : 'Speichern'}
                </button>
                {fuSaved && <span className="text-sm text-emerald-600">✓ Gespeichert</span>}
              </div>
              {fuErr && <div className="rounded-lg bg-rose-50 p-2 text-xs text-rose-700">{fuErr}</div>}
            </div>
          </Section>

          <Section title={`Kontakte (${contacts?.length || 0})`}>
            {(!contacts || contacts.length === 0)
              ? <div className="text-sm text-slate-400">Keine Kontakte erfasst.</div>
              : contacts.map((c: any) => (
                <div key={c.id} className="border-b border-slate-100 py-2 text-sm last:border-0">
                  <div className="font-medium text-slate-700">{c.name || 'Unbenannt'}</div>
                  <div className="text-slate-500">{[c.role, c.email, c.phone].filter(Boolean).join(' · ') || '–'}</div>
                </div>
              ))}
            <div className="mt-3 border-t border-slate-100 pt-3">
              <AgentTaskButton kind="entscheider-recherche" jobId={job.id} label="Entscheider recherchieren" subtle onFinished={load} />
              <p className="mt-1 text-xs text-slate-400">Fachentscheider statt HR — nur öffentliche Quellen.</p>
            </div>
          </Section>

          {/* Unterlagen erstellen — Workflow (Phase 16, ersetzt „Firma prüfen") */}
          <Section title="Unterlagen erstellen">
            <div className="space-y-1">
              <WfStep n="1" done={fitDa}>
                {fitDa ? (
                  <>
                    <div className="text-sm">Company-Fit geprüft</div>
                    <div className="mt-1 flex flex-wrap items-center gap-3 text-xs">
                      <a href={artifactUrl(company.fit_analysis_path)} className="text-brand-cyan hover:underline">Dashboard öffnen</a>
                      <AgentTaskButton kind="firma-pruefen" jobId={job.id} subtle label="neu erzeugen" onFinished={load} resultLinks={fitLinks} />
                    </div>
                  </>
                ) : (
                  <AgentTaskButton kind="firma-pruefen" jobId={job.id} label="1 · Company-Fit prüfen" onFinished={load} resultLinks={fitLinks} />
                )}
              </WfStep>

              {/* P2-41: Beirat ist optionaler Baustein, kein Kettenglied mehr — nie locked. */}
              <WfStep optional done={beiratDa}>
                {beiratDa ? (
                  <>
                    <div className="text-sm">Beirat: {beiratNeu.note}</div>
                    <div className="mt-1 flex flex-wrap items-center gap-3 text-xs">
                      <a href={artifactUrl(beiratNeu.file_path)} className="text-brand-cyan hover:underline">Dashboard öffnen</a>
                      <BeiratCheckButton jobId={job.id} onFinished={load} subtle label="neu prüfen" />
                      {beiratNeu.note?.startsWith('🔴') && job.status !== 'Beirat abgelehnt' && (
                        <button onClick={() => setStatus('Beirat abgelehnt')} disabled={saving}
                          className="rounded-lg border border-violet-200 px-2.5 py-1 font-medium text-violet-700 hover:bg-violet-50 disabled:opacity-50">
                          Status auf „Beirat abgelehnt" setzen
                        </button>
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="text-sm">
                      Stelle prüfen (Beirat)
                      <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-500">optional</span>
                    </div>
                    <p className="mt-1 text-xs text-slate-400">Empfohlen vor dem CV-Aufwand — nutzt den Company-Fit, wenn er vorliegt.</p>
                    <div className="mt-1">
                      <BeiratCheckButton jobId={job.id} onFinished={load} subtle label="▶ Stelle prüfen (Beirat)" />
                    </div>
                  </>
                )}
              </WfStep>

              {/* Pflichtkern-Reihenfolge bleibt Firma → CV-Match → CV erstellen; die Sperre hängt
                  seit P2-41 wieder an fitDa statt am (jetzt optionalen) Beirat. */}
              <WfStep n="2" done={cvDa} locked={!fitDa} lockedTitle="Erst Company-Fit prüfen">
                {cvDa ? (
                  <>
                    <div className="text-sm">CV-Match erledigt{cvFertigDa ? '' : ' — Entwurf wartet auf Bearbeitung/Erstellung'}</div>
                    <div className="mt-1"><AgentTaskButton kind="cv-match" jobId={job.id} subtle label="neu matchen" onFinished={load} resultLinks={matchLinks} /></div>
                  </>
                ) : !fitDa ? (
                  <div className="text-sm">CV-Match (Match-Dashboard + Entwurf)</div>
                ) : (
                  <AgentTaskButton kind="cv-match" jobId={job.id} label="2 · CV-Match" onFinished={load} resultLinks={matchLinks} />
                )}
              </WfStep>

              {/* P2-41: Anschreiben ist optionaler Baustein, kein Kettenglied mehr — nie locked. */}
              <WfStep optional done={anschreibenDa}>
                {anschreibenDa ? (
                  <>
                    <div className="text-sm">Anschreiben erstellt</div>
                    <div className="mt-1"><AgentTaskButton kind="anschreiben-erstellen" jobId={job.id} subtle label="neu erzeugen" onFinished={load} resultLinks={anschreibenLinks} /></div>
                  </>
                ) : (
                  <>
                    <div className="text-sm">
                      Anschreiben
                      <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-500">optional</span>
                    </div>
                    <p className="mt-1 text-xs text-slate-400">Nutzt den angepassten CV, sobald er fertig ist — sonst den Basis-CV.</p>
                    <div className="mt-1">
                      <AgentTaskButton kind="anschreiben-erstellen" jobId={job.id} subtle label="Anschreiben generieren" onFinished={load} resultLinks={anschreibenLinks} />
                    </div>
                  </>
                )}
              </WfStep>
            </div>

            <div className="mt-3 border-t border-slate-100 pt-2">
              <div className="mb-1 text-xs font-medium text-slate-500">Bewerbungspaket — Pflichtkern Firma → CV-Match → CV erstellen. Der Beirat läuft in-server und ist kein Kettenglied.</div>
              <label className="mb-2 flex items-center gap-2 text-xs text-slate-600">
                <input type="checkbox" checked={mitAnschreiben} onChange={(e) => setMitAnschreiben(e.target.checked)} />
                mit Anschreiben
              </label>
              <AgentTaskButton
                kind="bewerbungspaket"
                jobId={job.id}
                label={mitAnschreiben ? 'Bewerbungspaket (Firma → CV → Anschreiben)' : 'Bewerbungspaket (Firma → CV)'}
                params={{ mit_anschreiben: mitAnschreiben }}
                watchKinds={['firma-pruefen', 'cv-match', 'cv-erstellen', 'anschreiben-erstellen']}
                subtle
                onFinished={load}
              />
            </div>

            <details className="mt-2 text-xs text-slate-400">
              <summary className="cursor-pointer hover:text-slate-600">Alternativ: in Claude-Session ausführen</summary>
              <div className="mt-2">
                <CopyTrigger phrase={`Firma prüfen für Job ${job.id}`} label="📋 Auslöser kopieren" />
              </div>
            </details>
          </Section>

          {/* Bewerbung (rutscht hoch: erst bewerben, dann Gespräche) */}
          {application && (
            <Section title="Bewerbung">
              <Field label="Status" value={application.status} />
              <Field label="Beworben am" value={application.applied_date} />
              <Field label="Kanal" value={application.channel} />
              <Field label="Absagegrund" value={application.rejection_reason} />
              {application.cover_letter_path && (
                <div className="flex gap-2 py-1 text-sm">
                  <div className="w-40 shrink-0 text-slate-400">Anschreiben</div>
                  <div className="flex flex-wrap gap-3">
                    <a href={artifactUrl(application.cover_letter_path, true)} className="text-brand-cyan hover:underline">⬇ Anschreiben (.docx)</a>
                    {application.cover_letter_pdf_path && <a href={artifactUrl(application.cover_letter_pdf_path, true)} className="text-brand-cyan hover:underline">⬇ Anschreiben (.pdf)</a>}
                    {application.cover_letter_pdf_path && <a href={artifactUrl(application.cover_letter_pdf_path)} className="text-brand-cyan hover:underline">Ansehen</a>}
                  </div>
                </div>
              )}
              <Field label="Notiz" value={application.notes} />
            </Section>
          )}

          <Section title={`Interviews & Gespräche (${interviews?.length || 0})`}>
            <div className="space-y-2">
              {(interviews || []).map((iv: any) => (
                <div key={iv.id} className="rounded-lg border border-slate-200 p-2.5 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-brand-navy">Runde {iv.runde} · {iv.art || 'Gespräch'}</span>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${IV_STATUS_STYLE[iv.status] || 'bg-slate-100 text-slate-500'}`}>{iv.status}</span>
                  </div>
                  {(iv.scheduled_at || iv.interviewer) && (
                    <div className="mt-0.5 text-xs text-slate-500">
                      {iv.scheduled_at ? iv.scheduled_at.replace('T', ' ') : ''}
                      {iv.scheduled_at && iv.interviewer ? ' · ' : ''}
                      {iv.interviewer || ''}
                    </div>
                  )}
                  {/* Phase 69 (Stufe B) — Gegenüber + vor Ort, sofortiges PATCH wie die Status-Buttons unten. */}
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs">
                    <select value={iv.gegenueber || ''} onChange={(e) => setIvGegenueber(iv.id, e.target.value)}
                            className="rounded-lg border border-slate-300 px-2 py-1 text-xs focus:border-brand-cyan focus:outline-none">
                      <option value="">Gegenüber…</option>
                      {IV_GEGENUEBER.map((g) => <option key={g} value={g}>{g}</option>)}
                    </select>
                    <label className="flex items-center gap-1 text-slate-500">
                      <input type="checkbox" checked={!!iv.vor_ort} onChange={() => toggleIvVorOrt(iv)} />
                      vor Ort
                    </label>
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs">
                    {iv.prep_path && <a href={artifactUrl(iv.prep_path)} className="text-brand-cyan hover:underline">📋 Briefing öffnen</a>}
                    {routeUrl && <a href={routeUrl} target="_blank" rel="noreferrer" className="text-brand-cyan hover:underline" title="Route von zu Hause (Google Maps)">🗺️ Route</a>}
                    {iv.status !== 'Absolviert' && <button onClick={() => setIvStatus(iv.id, 'Absolviert')} className="text-slate-500 hover:text-emerald-700">Absolviert</button>}
                    {iv.status !== 'Abgesagt' && <button onClick={() => setIvStatus(iv.id, 'Abgesagt')} className="text-slate-500 hover:text-slate-700">Abgesagt</button>}
                    <button onClick={() => deleteInterview(iv.id)} className="ml-auto text-slate-400 hover:text-rose-600" title="Gespräch löschen">✕</button>
                  </div>
                </div>
              ))}
              {(!interviews || interviews.length === 0) && <div className="text-sm text-slate-400">Noch keine Gespräche erfasst.</div>}
            </div>

            {showIvForm ? (
              <div className="mt-3 space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-2.5">
                <div className="flex gap-2">
                  <select value={ivForm.art} onChange={(e) => artWechsel(ivForm, setIvForm, e.target.value)} className="flex-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none">
                    {IV_ARTEN.map((a) => <option key={a} value={a}>{a}</option>)}
                  </select>
                  <input type="number" min={1} value={ivForm.runde} onChange={(e) => setIvForm({ ...ivForm, runde: e.target.value })} className="w-20 rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none" title="Runde" />
                </div>
                <input type="datetime-local" value={ivForm.scheduled_at} onChange={(e) => setIvForm({ ...ivForm, scheduled_at: e.target.value })} className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none" />
                <input type="text" placeholder="Interviewer (Name, Rolle)…" value={ivForm.interviewer} onChange={(e) => setIvForm({ ...ivForm, interviewer: e.target.value })} className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none" />
                <div className="flex items-center gap-2">
                  <select value={ivForm.gegenueber} onChange={(e) => setIvForm({ ...ivForm, gegenueber: e.target.value })} className="flex-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none">
                    <option value="">Gegenüber…</option>
                    {IV_GEGENUEBER.map((g) => <option key={g} value={g}>{g}</option>)}
                  </select>
                  <label className="flex items-center gap-1.5 whitespace-nowrap text-sm text-slate-600">
                    <input type="checkbox" checked={ivForm.vor_ort} onChange={(e) => setIvForm({ ...ivForm, vor_ort: e.target.checked })} />
                    vor Ort
                  </label>
                </div>
                <textarea rows={2} placeholder="Notizen…" value={ivForm.notes} onChange={(e) => setIvForm({ ...ivForm, notes: e.target.value })} className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none" />
                <div className="flex gap-2">
                  <button onClick={createInterview} className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:opacity-40">Anlegen</button>
                  <button onClick={() => setShowIvForm(false)} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">Abbrechen</button>
                </div>
              </div>
            ) : (
              <button onClick={openIvForm} className="mt-2 text-sm text-brand-cyan hover:underline">+ Gespräch anlegen</button>
            )}

            <div className="mt-3">
              <AgentTaskButton kind="interview-vorbereiten" jobId={job.id} label="Interview vorbereiten (Briefing)" onFinished={load} />
            </div>

            <div className="mt-3 text-xs font-medium text-slate-500">Transkripte ({transcripts?.length || 0})</div>
            <div className="mt-1 space-y-2">
              {(transcripts || []).map((t: any) => {
                // Phase 30: rechts nur noch Summary (3–5 Sätze) + Meta-Zeile + Report-Link + Rohtext-Link
                // — der bisherige Volltext-/Langkontext ist raus (steht jetzt vollständig im Report selbst).
                const iv = (interviews || []).find((x: any) => x.id === t.interview_id)
                const reportHref = t.report_path || t.debrief_path   // Fallback: Altbestand ohne report_path
                const metaTeile = [t.recorded_at, t.kontakt, iv ? `Runde ${iv.runde}` : null].filter(Boolean)
                return (
                  <div key={t.id} className="rounded-lg border border-slate-200 p-2.5 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-brand-navy">{t.title || 'Transkript'}</span>
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500">{t.source}</span>
                    </div>
                    <div className="mt-0.5 text-xs text-slate-500">{metaTeile.length ? metaTeile.join(' · ') : '–'}</div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs">
                      {reportHref && <a href={artifactUrl(reportHref)} className="text-brand-cyan hover:underline">📄 Report öffnen</a>}
                      {t.file_path && <a href={artifactUrl(t.file_path)} className="text-slate-400 hover:underline" title="Original-Rohtext">Rohtext</a>}
                      <DebriefBadge t={t} task={debriefTasks[t.id]} onStart={startDebrief} />
                      <button onClick={() => deleteTranscript(t.id)} className="ml-auto text-slate-400 hover:text-rose-600" title="Zuordnung löschen (Datei bleibt)">✕</button>
                    </div>
                    {t.summary && <div className="mt-1 text-xs text-slate-500">{t.summary}</div>}
                  </div>
                )
              })}
              {(!transcripts || transcripts.length === 0) && <div className="text-sm text-slate-400">Noch keine Transkripte.</div>}
            </div>

            {showTrForm ? (
              <div className="mt-2 space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-2.5">
                <input type="text" placeholder="Titel (z. B. 1. Gespräch — HR-Screen)" value={trForm.title} onChange={(e) => setTrForm({ ...trForm, title: e.target.value })} className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none" />
                <div className="flex gap-2">
                  <input list="kontakte-paste" placeholder="Gesprächspartner…" value={trForm.kontakt} onChange={(e) => setTrForm({ ...trForm, kontakt: e.target.value })} className="flex-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none" />
                  <datalist id="kontakte-paste">
                    {(contacts || []).map((c: any) => <option key={c.id} value={c.name} />)}
                  </datalist>
                  <input type="date" value={trForm.recorded_at} onChange={(e) => setTrForm({ ...trForm, recorded_at: e.target.value })} className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none" />
                </div>
                <div className="flex gap-2">
                  <RundenWahl form={trForm} setForm={setTrForm} interviews={interviews}
                    className="flex-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none" />
                  <select value={trForm.language} onChange={(e) => setTrForm({ ...trForm, language: e.target.value })} className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none">
                    <option value="DE">DE</option><option value="EN">EN</option>
                  </select>
                </div>
                <NeueRundeFelder form={trForm} setForm={setTrForm} />
                <textarea rows={8} placeholder="Transkript hier einfügen (aus Teams/Zoom/Notizen)…" value={trForm.content} onChange={(e) => setTrForm({ ...trForm, content: e.target.value })} className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none" />
                <div className="flex gap-2">
                  <button onClick={createTranscript} disabled={!trForm.content.trim()} className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:opacity-40">Einfügen</button>
                  <button onClick={() => setShowTrForm(false)} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">Abbrechen</button>
                </div>
              </div>
            ) : !showTrUpload && (
              <div className="mt-2 flex gap-3">
                <button onClick={() => setShowTrForm(true)} className="text-sm text-brand-cyan hover:underline">+ Transkript einfügen</button>
                <button onClick={() => setShowTrUpload(true)} className="text-sm text-brand-cyan hover:underline">+ Datei hochladen</button>
              </div>
            )}

            {showTrUpload && (
              <div className="mt-2 space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-2.5">
                <input type="file" accept=".txt,.md,.vtt"
                  onChange={(e) => setTrUpload({ ...trUpload, file: e.target.files?.[0] || null })}
                  className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none" />
                <p className="text-xs text-slate-400">.txt, .md oder .vtt (Teams/Zoom-Untertitel — Zeitstempel werden automatisch entfernt), max. 5 MB.</p>
                <input type="text" placeholder="Titel (optional)" value={trUpload.title} onChange={(e) => setTrUpload({ ...trUpload, title: e.target.value })} className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none" />
                <div className="flex gap-2">
                  <input list="kontakte-upload" placeholder="Gesprächspartner…" value={trUpload.kontakt} onChange={(e) => setTrUpload({ ...trUpload, kontakt: e.target.value })} className="flex-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none" />
                  <datalist id="kontakte-upload">
                    {(contacts || []).map((c: any) => <option key={c.id} value={c.name} />)}
                  </datalist>
                  <input type="date" value={trUpload.recorded_at} onChange={(e) => setTrUpload({ ...trUpload, recorded_at: e.target.value })} className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none" />
                </div>
                <RundenWahl form={trUpload} setForm={setTrUpload} interviews={interviews} />
                <NeueRundeFelder form={trUpload} setForm={setTrUpload} />
                {trUploadErr && <div className="text-xs text-rose-600">{trUploadErr}</div>}
                <div className="flex gap-2">
                  <button onClick={uploadTranscriptFile} disabled={!trUpload.file || trUploading} className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:opacity-40">
                    {trUploading ? 'Lädt…' : 'Hochladen'}
                  </button>
                  <button onClick={() => { setShowTrUpload(false); setTrUploadErr(null) }} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">Abbrechen</button>
                </div>
              </div>
            )}
          </Section>

          {/* „Firma prüfen" → jetzt in der Workflow-Karte „Unterlagen erstellen" (oben). */}

          {/* Angepasster CV — nur Fakten (letzte Karte); Downloads liegen in „Dateien & Dokumente". */}
          <Section title="Angepasster CV">
            {cv_versions && cv_versions.length > 0 ? (
              <div className="space-y-2">
                {cv_versions.map((c: any) => (
                  <div key={c.id} className="rounded-lg border border-slate-200 p-2.5 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-brand-navy">Angepasster CV · {({ DE: 'Deutsch', EN: 'Englisch' } as any)[(c.language || '').toUpperCase()] ?? c.language}</span>
                      <div className="flex gap-1.5">
                        {c.status === 'entwurf' && <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800">Entwurf</span>}
                        {c.match_score100 != null && <span className="rounded bg-brand-cyan/15 px-1.5 py-0.5 text-xs text-brand-navy">Match {c.match_score100}</span>}
                        {c.ats_score != null && <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-800">ATS {c.ats_score}</span>}
                      </div>
                    </div>
                    <div className="mt-1 text-xs text-slate-400">{tagVon(c.created_at)} · Dateien unter „Dateien &amp; Dokumente"</div>
                  </div>
                ))}
              </div>
            ) : fitDa ? (
              // P2-41: der CV-Match wartet nur noch auf den Company-Fit — der Beirats-Check ist
              // ein optionaler Baustein und kein Vorschritt mehr.
              <div className="rounded-lg bg-slate-50 p-3 text-sm text-slate-500">
                <b>Schritt 2</b> in „Unterlagen erstellen": CV-Match, ATS-Scan und angepasster CV (DE/EN).
              </div>
            ) : (
              <div className="rounded-lg bg-slate-50 p-3 text-sm text-slate-500">
                <b>Erst Schritt 1</b> in „Unterlagen erstellen" (Company-Fit prüfen). Danach folgen hier Match &amp; ATS.
              </div>
            )}
          </Section>

          {/* „Bewerbung" ist nach oben gerückt (hinter die Workflow-Karte); Anschreiben-Button
              lebt als optionaler Baustein in der Workflow-Karte (P2-41). */}
        </div>
      </div>
    </div>
  )
}
