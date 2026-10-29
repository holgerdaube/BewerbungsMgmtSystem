import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api, type BeiratMitglied, type Einstellungen as EinstellungenT, type NeuesteVersion, type Umkreisumbenennung, type VersionInfo,
  type Plan, type Portal, type SicherungStatus } from '../api'
import AgentTaskButton from '../components/AgentTaskButton'
import { suchTabsNeuLaden } from '../suchbereich'
import { PROFIL_GEAENDERT } from '../profil'
import { deDatum } from '../zeit'

const INPUT = 'rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none'

// §18.6-Kategorienpalette (Phase 80-Nachtrag, Entscheidung 10.08.2026, Muster
// Profil.tsx::BEREICH_FARBEN) — Cyan/Indigo/Violet statt der gedämpften Eigen-Töne;
// Rollback-Werte: tasks/spec_phase80_styleguide_v18_theme.md, WP-D.
const PLAN_FARBEN: Record<string, string> = { A: '#00B4D8', B: '#5B61E6', C: '#7C4DFF' }

// Phase 50 — Reihenfolge + Anzeigenamen der 6 Kern-Funktionen (Keys spiegeln
// agent_runner.py::FUNKTION_KINDS + "beirat").
const FUNKTIONEN: { key: string; label: string }[] = [
  { key: 'jobsuche', label: 'Jobsuche' },
  { key: 'company-fit', label: 'Company Fit' },
  { key: 'beirat', label: 'Beirat' },
  { key: 'cv-match', label: 'CV Match' },
  { key: 'ats-scan', label: 'ATS Scan' },
  { key: 'anschreiben', label: 'Anschreiben' },
]

// ── Chip-Liste: rein lokale State-Mutation (add/remove ohne eigenen API-Call) — erst der
// Karten-„Speichern"-Button persistiert den ganzen Plan in einem PATCH. Anders als
// Profil.tsx::Skills (dort sind Skills eigene DB-Zeilen mit sofortigem Add/Remove). ──────
function ChipListe({ label, werte, onChange }: { label: string; werte: string[]; onChange: (werte: string[]) => void }) {
  const [neu, setNeu] = useState('')
  const add = () => {
    const t = neu.trim()
    if (!t || werte.includes(t)) return
    onChange([...werte, t])
    setNeu('')
  }
  return (
    <div>
      <div className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mb-1.5 flex flex-wrap gap-1.5">
        {werte.map((w) => (
          <span key={w} className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700">
            {w}
            <button onClick={() => onChange(werte.filter((x) => x !== w))} className="ml-0.5 text-slate-400 hover:text-rose-600">×</button>
          </span>
        ))}
        {werte.length === 0 && <span className="text-xs text-slate-400">–</span>}
      </div>
      <div className="flex gap-1.5">
        <input className={`${INPUT} flex-1 text-xs`} placeholder={`${label} hinzufügen…`} value={neu}
          onChange={(e) => setNeu(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } }} />
        <button onClick={add} className="rounded-lg border border-slate-300 px-2.5 text-xs text-slate-600 hover:bg-slate-50">+</button>
      </div>
    </div>
  )
}

// ── Plan-Karte A/B/C: Label, aktiv-Schalter, drei Chip-Listen, eigener Speichern-Button ──
function PlanKarte({ plan, onSaved }: { plan: Plan; onSaved: () => void }) {
  const [f, setF] = useState(plan)
  const [original, setOriginal] = useState(plan)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const dirty = JSON.stringify(f) !== JSON.stringify(original)
  const farbe = PLAN_FARBEN[f.plan] || '#858F9C'

  const save = async () => {
    setSaving(true); setErr(null)
    try {
      // NUR diesen einen Plan senden — das Backend upserted nach `plan`-Schlüssel (main.py),
      // die anderen beiden Pläne bleiben unangetastet.
      await api('/einstellungen', { method: 'PATCH', body: JSON.stringify({ plaene: [f] }) })
      setOriginal(f)
      setSaved(true); setTimeout(() => setSaved(false), 2000)
      onSaved()
    } catch (e: any) { setErr(e?.message || 'Speichern fehlgeschlagen') }
    finally { setSaving(false) }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center gap-2">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white"
          style={{ backgroundColor: farbe }}>{f.plan}</span>
        <input className={`${INPUT} flex-1 font-semibold text-brand-navy`} value={f.label}
          onChange={(e) => setF({ ...f, label: e.target.value })} />
        <label className="flex shrink-0 items-center gap-1.5 text-xs text-slate-500">
          <input type="checkbox" checked={f.aktiv} onChange={(e) => setF({ ...f, aktiv: e.target.checked })} />
          aktiv
        </label>
      </div>
      <div className="space-y-3">
        <ChipListe label="Titel" werte={f.titel} onChange={(titel) => setF({ ...f, titel })} />
        <ChipListe label="Seniorität" werte={f.senioritaet} onChange={(senioritaet) => setF({ ...f, senioritaet })} />
        <ChipListe label="Branche" werte={f.branche} onChange={(branche) => setF({ ...f, branche })} />
      </div>
      <div className="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3">
        <button onClick={save} disabled={saving || !dirty}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? 'Speichern…' : 'Speichern'}
        </button>
        {saved && <span className="text-sm text-emerald-600">✓ Gespeichert</span>}
        {err && <span className="text-sm text-rose-600">{err}</span>}
      </div>
    </div>
  )
}

// ── Suchbereich & Firmengröße (global, gilt für alle Pläne) ──────────────────────────────
// P2-51: `umkreisLabel` kommt vom Backend (V7, „<Stadt-Kurzform> +<km>km") statt einer fest
// verdrahteten Bezeichnung — zeigt nach dem Speichern den zuletzt vom Server bestätigten Stand,
// nicht die gerade eingegebenen, noch ungespeicherten Werte.
function SuchbereichKarte({ suchbereich, minMitarbeiter, umkreisLabel, onSaved }:
  { suchbereich: EinstellungenT['suchbereich']; minMitarbeiter: number; umkreisLabel: string | null; onSaved: () => void }) {
  const initial = { ...suchbereich, min_mitarbeiter: minMitarbeiter }
  const [f, setF] = useState(initial)
  const [original, setOriginal] = useState(initial)
  const [label, setLabel] = useState(umkreisLabel)
  const [umbenennung, setUmbenennung] = useState<Umkreisumbenennung | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const dirty = JSON.stringify(f) !== JSON.stringify(original)

  const save = async () => {
    setSaving(true); setErr(null); setUmbenennung(null)
    try {
      const out = await api<EinstellungenT & { umbenennung?: Umkreisumbenennung }>('/einstellungen', {
        method: 'PATCH',
        body: JSON.stringify({
          min_mitarbeiter: f.min_mitarbeiter,
          suchbereich: {
            remote: { aktiv: f.remote.aktiv },
            deutschlandweit: { aktiv: f.deutschlandweit.aktiv },
            umkreis: { aktiv: f.umkreis.aktiv, stadt: f.umkreis.stadt, umkreis_km: f.umkreis.umkreis_km },
          },
        }),
      })
      setOriginal(f)
      setLabel(out.umkreis_label)
      if (out.umbenennung) setUmbenennung(out.umbenennung)
      setSaved(true); setTimeout(() => setSaved(false), 2000)
      suchTabsNeuLaden()
      onSaved()
    } catch (e: any) { setErr(e?.message || 'Speichern fehlgeschlagen') }
    finally { setSaving(false) }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 text-sm font-semibold text-brand-navy">Suchbereich &amp; Firmengröße</div>
      <div className="space-y-2">
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={f.remote.aktiv}
            onChange={(e) => setF({ ...f, remote: { aktiv: e.target.checked } })} />
          Remote
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={f.deutschlandweit.aktiv}
            onChange={(e) => setF({ ...f, deutschlandweit: { aktiv: e.target.checked } })} />
          Deutschlandweit
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={f.umkreis.aktiv}
              onChange={(e) => setF({ ...f, umkreis: { ...f.umkreis, aktiv: e.target.checked } })} />
            Stadt + Umkreis
          </label>
          {f.umkreis.aktiv && (
            <>
              <input className={`${INPUT} w-48`} value={f.umkreis.stadt} placeholder="z. B. Köln"
                onChange={(e) => setF({ ...f, umkreis: { ...f.umkreis, stadt: e.target.value } })} />
              <span className="text-sm text-slate-500">+</span>
              <input type="number" className={`${INPUT} w-20`} value={f.umkreis.umkreis_km}
                onChange={(e) => setF({ ...f, umkreis: { ...f.umkreis, umkreis_km: Number(e.target.value) || 0 } })} />
              <span className="text-sm text-slate-500">km</span>
            </>
          )}
        </div>
      </div>
      <div className="mt-3 border-t border-slate-100 pt-3">
        <label className="flex items-center gap-2 text-sm text-slate-700">
          Mindest-Firmengröße
          <input type="number" className={`${INPUT} w-24`} value={f.min_mitarbeiter}
            onChange={(e) => setF({ ...f, min_mitarbeiter: Number(e.target.value) || 0 })} />
          Mitarbeiter
        </label>
      </div>
      {label && <div className="mt-2 text-xs text-slate-400">In der Jobliste: {label}</div>}
      {umbenennung && (
        <div className="mt-2 text-xs text-emerald-600">
          {umbenennung.jobs} Stellen von „{umbenennung.von}“ auf „{umbenennung.nach}“ umgestellt.
        </div>
      )}
      <div className="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3">
        <button onClick={save} disabled={saving || !dirty}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? 'Speichern…' : 'Speichern'}
        </button>
        {saved && <span className="text-sm text-emerald-600">✓ Gespeichert</span>}
        {err && <span className="text-sm text-rose-600">{err}</span>}
      </div>
    </div>
  )
}

// ── KI-Modell je Funktion (Phase 50, ab P2-51 mit Optionen/Standard vom Backend) ─────────────
function ModelleKarte({ modelle, modellOptionen, modellStandard, onSaved }: {
  modelle: EinstellungenT['modelle']
  modellOptionen: EinstellungenT['modell_optionen']
  modellStandard: string
  onSaved: () => void
}) {
  const [f, setF] = useState(modelle)
  const [original, setOriginal] = useState(modelle)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const dirty = JSON.stringify(f) !== JSON.stringify(original)
  const standardLabel = modellOptionen.find((m) => m.alias === modellStandard)?.label || modellStandard

  const save = async () => {
    setSaving(true); setErr(null)
    try {
      await api('/einstellungen', { method: 'PATCH', body: JSON.stringify({ modelle: f }) })
      setOriginal(f)
      setSaved(true); setTimeout(() => setSaved(false), 2000)
      onSaved()
    } catch (e: any) { setErr(e?.message || 'Speichern fehlgeschlagen') }
    finally { setSaving(false) }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 text-sm font-semibold text-brand-navy">KI-Modell je Funktion</div>
      <p className="mb-3 text-xs text-slate-500">
        Gilt für die per Button/Task-Center gestarteten Läufe. Standard: {standardLabel}.
      </p>
      <div className="space-y-2">
        {FUNKTIONEN.map(({ key, label }) => (
          <div key={key} className="flex items-center justify-between gap-2">
            <span className="text-sm text-slate-700">{label}</span>
            <select className={`${INPUT} w-40`} value={f[key] || modellStandard}
              onChange={(e) => setF({ ...f, [key]: e.target.value })}>
              {modellOptionen.map((m) => <option key={m.alias} value={m.alias}>{m.label}</option>)}
            </select>
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3">
        <button onClick={save} disabled={saving || !dirty}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? 'Speichern…' : 'Speichern'}
        </button>
        {saved && <span className="text-sm text-emerald-600">✓ Gespeichert</span>}
        {err && <span className="text-sm text-rose-600">{err}</span>}
      </div>
    </div>
  )
}

// ── Suchportale (Phase 87) — Name/URL je Portal, dreistufige Prüf-Ampel je Zeile ─────────
// Zugriffsart ist fest (bestimmt der jobsuche-Skill, nicht die Oberfläche) und erscheint nur
// als kleiner Hinweis: "websearch" sucht per WebSearch mit Domain-Anker (Bot-Schutz bei
// LinkedIn/Indeed/StepStone/Xing), "fetch" ruft die URL direkt ab (Nejo/Arbeitsagentur).
const ZUGRIFF_LABEL: Record<Portal['zugriff'], string> = {
  websearch: 'per Websuche',
  fetch: 'direkter Abruf',
}

interface PruefErgebnis {
  status: 'gruen' | 'amber' | 'rot'
  http: number | null
  bytes: number | null
  meldung: string
  final_url: string | null
}

// Ampelfarben aus der etablierten Palette der App (Budget.tsx::BALKEN, JobDetail.tsx
// AVAILABILITY_LABELS) — keine neuen Hex-Werte, nur die vorhandenen Tailwind-Statusfarben.
const PRUEF_DOT: Record<PruefErgebnis['status'], string> = {
  gruen: 'bg-emerald-500', amber: 'bg-amber-500', rot: 'bg-rose-500',
}
const PRUEF_TEXT: Record<PruefErgebnis['status'], string> = {
  gruen: 'text-emerald-600', amber: 'text-amber-600', rot: 'text-rose-600',
}

function PortaleKarte({ portale, onSaved }: { portale: Portal[]; onSaved: () => void }) {
  const [f, setF] = useState(portale)
  const [original, setOriginal] = useState(portale)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const dirty = JSON.stringify(f) !== JSON.stringify(original)

  // Prüf-Zustand je Zeile (Schlüssel = Portal-key), NICHT global — sonst überschreibt eine
  // zweite gleichzeitig gestartete Prüfung das Ergebnis der ersten (Spec Phase 87, D2).
  const [pruefung, setPruefung] = useState<Record<string, { loading: boolean; ergebnis?: PruefErgebnis; fehler?: string }>>({})

  const save = async () => {
    setSaving(true); setErr(null)
    try {
      // Ganze Liste senden — das Backend merged per `key` (main.py), unveränderte Einträge
      // bleiben unangetastet (Muster ModelleKarte, dort ist es ohnehin ein einziges Objekt).
      await api('/einstellungen', { method: 'PATCH', body: JSON.stringify({ portale: f }) })
      setOriginal(f)
      setSaved(true); setTimeout(() => setSaved(false), 2000)
      onSaved()
    } catch (e: any) { setErr(e?.message || 'Speichern fehlgeschlagen') }
    finally { setSaving(false) }
  }

  // Prüft die AKTUELL im Feld stehende URL (f), nicht die gespeicherte (original) — so kann
  // man eine geänderte URL testen, bevor man sie speichert.
  const pruefen = async (key: string) => {
    const p = f.find((x) => x.key === key)
    if (!p || !p.url.trim()) return
    setPruefung((cur) => ({ ...cur, [key]: { loading: true } }))
    try {
      const out = await api<PruefErgebnis>('/einstellungen/portale/pruefen', {
        method: 'POST', body: JSON.stringify({ url: p.url }),
      })
      setPruefung((cur) => ({ ...cur, [key]: { loading: false, ergebnis: out } }))
    } catch (e: any) {
      setPruefung((cur) => ({ ...cur, [key]: { loading: false, fehler: e?.message || 'Prüfung fehlgeschlagen' } }))
    }
  }

  const setZeile = (key: string, patch: Partial<Portal>) =>
    setF((cur) => cur.map((p) => (p.key === key ? { ...p, ...patch } : p)))

  const zeile = (p: Portal) => {
    const status = pruefung[p.key]
    return (
      <div key={p.key} className="py-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <input type="checkbox" checked={p.aktiv} title="aktiv"
            onChange={(e) => setZeile(p.key, { aktiv: e.target.checked })} />
          <input className={`${INPUT} w-32 shrink-0 text-sm`} value={p.name}
            onChange={(e) => setZeile(p.key, { name: e.target.value })}
            placeholder={p.standard ? undefined : 'Weiteres Portal'} />
          <input className={`${INPUT} min-w-0 flex-1 text-sm`} value={p.url}
            onChange={(e) => setZeile(p.key, { url: e.target.value })}
            placeholder={p.standard ? undefined : 'https://…'} />
          <span className="w-28 shrink-0 text-[11px] text-slate-400">{ZUGRIFF_LABEL[p.zugriff]}</span>
          <button onClick={() => pruefen(p.key)} disabled={status?.loading || !p.url.trim()}
            className="shrink-0 rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40">
            {status?.loading ? 'Prüfe…' : 'Prüfen'}
          </button>
        </div>
        {status?.ergebnis && (
          <div className="ml-6 mt-1 flex items-center gap-1.5">
            <span className={`h-2 w-2 shrink-0 rounded-full ${PRUEF_DOT[status.ergebnis.status]}`} />
            <span className={`text-xs ${PRUEF_TEXT[status.ergebnis.status]}`}>{status.ergebnis.meldung}</span>
          </div>
        )}
        {status?.fehler && <div className="ml-6 mt-1 text-xs text-rose-600">{status.fehler}</div>}
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 text-sm font-semibold text-brand-navy">Suchportale</div>
      <p className="mb-3 text-xs text-slate-500">
        Der Tageslauf durchsucht nur aktive Portale. Voreingestellt sind die in Deutschland
        üblichen — Name und URL lassen sich anpassen, zwei Zeilen sind für weitere Portale frei.
      </p>
      <div className="divide-y divide-slate-100">
        {f.filter((p) => p.standard).map(zeile)}
      </div>
      <div className="mt-2 divide-y divide-slate-100 border-t border-slate-200 pt-2">
        {f.filter((p) => !p.standard).map(zeile)}
      </div>
      <div className="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3">
        <button onClick={save} disabled={saving || !dirty}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? 'Speichern…' : 'Speichern'}
        </button>
        {saved && <span className="text-sm text-emerald-600">✓ Gespeichert</span>}
        {err && <span className="text-sm text-rose-600">{err}</span>}
      </div>
    </div>
  )
}

// ── Bewerbungspaket — Standardumfang (P2-41) — Vorbelegung des Pakethäkchens am Job-Detail;
// pro Stelle jederzeit übersteuerbar. Der Beirat hat hier bewusst KEINEN Schalter — er ist
// kein Kettenglied und ein Schalter hätte heute keine Wirkung (Spec P2-41, Stufe 1). ─────────
function UnterlagenKarte({ unterlagen, onSaved }: { unterlagen: EinstellungenT['unterlagen']; onSaved: () => void }) {
  const [f, setF] = useState(unterlagen)
  const [original, setOriginal] = useState(unterlagen)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const dirty = JSON.stringify(f) !== JSON.stringify(original)

  const save = async () => {
    setSaving(true); setErr(null)
    try {
      await api('/einstellungen', { method: 'PATCH', body: JSON.stringify({ unterlagen: f }) })
      setOriginal(f)
      setSaved(true); setTimeout(() => setSaved(false), 2000)
      onSaved()
    } catch (e: any) { setErr(e?.message || 'Speichern fehlgeschlagen') }
    finally { setSaving(false) }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 text-sm font-semibold text-brand-navy">Bewerbungspaket — Standardumfang</div>
      <p className="mb-3 text-xs text-slate-500">
        Vorbelegung des Häkchens am Job-Detail; pro Stelle jederzeit übersteuerbar. Der
        Beirats-Check ist ein eigener, optionaler Schritt und kein Kettenglied.
      </p>
      <label className="flex items-center gap-2 text-sm text-slate-700">
        <input type="checkbox" checked={f.anschreiben}
          onChange={(e) => setF({ ...f, anschreiben: e.target.checked })} />
        Anschreiben im Paket
      </label>
      <div className="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3">
        <button onClick={save} disabled={saving || !dirty}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? 'Speichern…' : 'Speichern'}
        </button>
        {saved && <span className="text-sm text-emerald-600">✓ Gespeichert</span>}
        {err && <span className="text-sm text-rose-600">{err}</span>}
      </div>
    </div>
  )
}

// ── Beirat — Besetzung (Phase 90) ─────────────────────────────────────────────────────────
// Eigener Endpunkt (/api/beirat/mitglieder, s. backend/beirat_engine.py), deshalb wie
// MailKontoKarte/CoachSiteKarte ein eigener, in sich geschlossener Lade-Zyklus — die sieben
// Mitglieder sind KEIN Teil von /api/einstellungen und laufen daher nicht über die `data`-Props
// von PlanKarte/ModelleKarte/PortaleKarte. Farbe/Vorsitz stehen im Frontmatter der
// `.claude/agents/beirat-*.md`-Dateien (einzige Quelle der Wahrheit) — hier nur Metadaten
// (Anzeige, Kurz-Perspektive, Farbe, Vorsitz) plus der Start-Knopf für „Neu besetzen".
// Sieben feste Plätze, kein Aktiv-Schalter (Design-Entscheidung 2 der Spec): die
// Abstimmungs-Schwellen im Stellen-Check sind auf sieben Stimmen kalibriert.
const NEU_LEER = { offen: false, name: '', perspektive: '', starting: false, err: null as string | null, taskId: null as number | null }
type NeuBesetzenZustand = typeof NEU_LEER

function BeiratKarte() {
  const [f, setF] = useState<BeiratMitglied[]>([])
  const [original, setOriginal] = useState<BeiratMitglied[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const dirty = JSON.stringify(f) !== JSON.stringify(original)

  // Start-Formular „Neu besetzen" je Platz — rein lokale UI-Zustände, unabhängig vom
  // Metadaten-Formular oben (Muster PortaleKarte::pruefung, dort ebenfalls ein Zustand je Zeile
  // statt global, damit zwei Plätze nicht gegenseitig ihren Stand überschreiben).
  const [neu, setNeu] = useState<Record<string, NeuBesetzenZustand>>({})

  const load = () =>
    api<BeiratMitglied[]>('/beirat/mitglieder')
      .then((data) => { setF(data); setOriginal(data) })
      .finally(() => setLoading(false))
  useEffect(() => { load() }, [])

  const save = async () => {
    setSaving(true); setErr(null)
    try {
      // Kein Sammel-Endpunkt vorgesehen (API-Vertrag: PATCH nimmt genau EIN Mitglied) — je
      // geänderten Platz ein PATCH, nur die tatsächlich veränderten Felder. `vorsitz` wird NIE
      // explizit auf false gesetzt: „vorsitz: true nimmt es allen anderen ab" ist der einzige
      // vom Backend vorgesehene Weg (B2) — ein explizites false auf den bisherigen Vorsitz würde
      // dessen eigenen 422-Schutz auslösen, solange der neue Vorsitz noch nicht gespeichert ist.
      for (const m of f) {
        const o = original.find((x) => x.id === m.id)
        if (!o) continue
        const patch: Partial<BeiratMitglied> = {}
        if (m.anzeige !== o.anzeige) patch.anzeige = m.anzeige
        if (m.perspektive !== o.perspektive) patch.perspektive = m.perspektive
        if (m.farbe !== o.farbe) patch.farbe = m.farbe
        if (m.vorsitz && !o.vorsitz) patch.vorsitz = true
        if (Object.keys(patch).length) {
          await api(`/beirat/mitglieder/${m.id}`, { method: 'PATCH', body: JSON.stringify(patch) })
        }
      }
      await load()
      setSaved(true); setTimeout(() => setSaved(false), 2000)
    } catch (e: any) { setErr(e?.message || 'Speichern fehlgeschlagen') }
    finally { setSaving(false) }
  }

  const setZeile = (id: string, patch: Partial<BeiratMitglied>) =>
    setF((cur) => cur.map((m) => (m.id === id ? { ...m, ...patch } : m)))

  const vorsitzWaehlen = (id: string) =>
    setF((cur) => cur.map((m) => ({ ...m, vorsitz: m.id === id })))

  const neuFeld = (id: string, patch: Partial<NeuBesetzenZustand>) =>
    setNeu((cur) => ({ ...cur, [id]: { ...(cur[id] || NEU_LEER), ...patch } }))

  const neuBesetzen = async (id: string) => {
    const n = neu[id] || NEU_LEER
    if (!n.name.trim() || !n.perspektive.trim()) return
    neuFeld(id, { starting: true, err: null })
    try {
      const out = await api<{ task_id: number }>(`/beirat/mitglieder/${id}/neu-besetzen`, {
        method: 'POST', body: JSON.stringify({ name: n.name.trim(), perspektive: n.perspektive.trim() }),
      })
      neuFeld(id, { starting: false, taskId: out.task_id })
    } catch (e: any) {
      neuFeld(id, { starting: false, err: e?.message || 'Start fehlgeschlagen' })
    }
  }

  const zeile = (m: BeiratMitglied) => {
    const n = neu[m.id] || NEU_LEER
    return (
      <div key={m.id} className="py-2">
        <div className="flex flex-wrap items-start gap-2">
          <span className="mt-2.5 h-3 w-3 shrink-0 rounded-full" style={{ backgroundColor: m.farbe }} title={m.farbe} />
          <input className={`${INPUT} w-40 shrink-0 text-sm font-medium`} value={m.anzeige}
            onChange={(e) => setZeile(m.id, { anzeige: e.target.value })} />
          <textarea className={`${INPUT} min-w-0 flex-1 text-sm`} rows={2} value={m.perspektive}
            onChange={(e) => setZeile(m.id, { perspektive: e.target.value })} />
          <label className="mt-2 flex shrink-0 items-center gap-1.5 text-xs text-slate-500">
            <input type="radio" name="beirat-vorsitz" checked={m.vorsitz} onChange={() => vorsitzWaehlen(m.id)} />
            Vorsitz
          </label>
          <button onClick={() => neuFeld(m.id, { ...NEU_LEER, offen: !n.offen })}
            className="shrink-0 rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50">
            Neu besetzen
          </button>
        </div>
        {n.offen && (
          <div className="ml-5 mt-1.5 space-y-1.5 rounded-lg border border-slate-200 bg-slate-50 p-2.5">
            <p className="text-xs text-slate-500">
              Name und Perspektive (1–2 Sätze) für den neuen Kopf — den vollen Persona-Text
              erzeugt der Lauf, nicht dieses Feld.
            </p>
            <input className={`${INPUT} w-full text-sm`} placeholder="Name" value={n.name}
              onChange={(e) => neuFeld(m.id, { name: e.target.value })} />
            <textarea className={`${INPUT} w-full text-sm`} rows={2} placeholder="Perspektive (1–2 Sätze)"
              value={n.perspektive} onChange={(e) => neuFeld(m.id, { perspektive: e.target.value })} />
            <div className="flex items-center gap-2">
              <button onClick={() => neuBesetzen(m.id)} disabled={n.starting || !n.name.trim() || !n.perspektive.trim()}
                className="rounded-lg bg-brand-cyan px-3 py-1.5 text-xs font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
                {n.starting ? 'Startet…' : 'Bestätigen'}
              </button>
              <button onClick={() => neuFeld(m.id, { ...NEU_LEER, offen: false })} disabled={n.starting}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40">
                Abbrechen
              </button>
            </div>
            {n.err && <div className="text-xs text-rose-600">{n.err}</div>}
            {n.taskId != null && (
              <div className="text-xs text-emerald-600">
                ✓ Lauf gestartet — Fortschritt im <Link to="/tasks" className="text-brand-cyan hover:underline">Task-Center</Link>.
              </div>
            )}
          </div>
        )}
      </div>
    )
  }

  if (loading) {
    return <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-400 shadow-sm">Lade Beirat…</div>
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 text-sm font-semibold text-brand-navy">Beirat — Besetzung</div>
      <p className="mb-3 text-xs text-slate-500">
        Die sieben Mitglieder sind fiktive Archetypen, keine realen Personen. Der eigentliche
        Persona-Text (Denkschule, Prüffragen, Grenzen) entsteht ausschließlich über „Neu
        besetzen" per Lauf — hier werden nur Anzeige, Kurzperspektive, Farbe und Vorsitz
        gepflegt. Es bleibt bei genau sieben Plätzen: Die Abstimmung im Stellen-Check ist auf
        sieben Stimmen kalibriert.
      </p>
      <div className="divide-y divide-slate-100">
        {f.map(zeile)}
      </div>
      <div className="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3">
        <button onClick={save} disabled={saving || !dirty}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? 'Speichern…' : 'Speichern'}
        </button>
        {saved && <span className="text-sm text-emerald-600">✓ Gespeichert</span>}
        {err && <span className="text-sm text-rose-600">{err}</span>}
      </div>
    </div>
  )
}

// ── E-Mail-Konto (Phase 71F) — Provider-Wahl Gmail-API/IMAP ──────────────────────────────
// Eigener Endpunkt (/api/settings/mail, s. app/routes_mail_settings.py), deshalb eigener,
// in sich geschlossener Lade-Zyklus statt Props vom Eltern-`data` (das speist ausschliesslich
// /api/einstellungen — eine andere Ressource).
interface MailSettings {
  provider: 'gmail' | 'imap'
  host: string
  port: number
  security: 'ssl' | 'starttls'
  username: string
  drafts_folder: string
  password_set: boolean
}

const MAIL_DEFAULTS: MailSettings = {
  provider: 'gmail', host: '', port: 993, security: 'ssl', username: '',
  drafts_folder: 'Drafts', password_set: false,
}

function MailKontoKarte() {
  const [f, setF] = useState<MailSettings>(MAIL_DEFAULTS)
  const [original, setOriginal] = useState<MailSettings>(MAIL_DEFAULTS)
  const [passwort, setPasswort] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [testing, setTesting] = useState(false)
  const [testErgebnis, setTestErgebnis] = useState<{ ok: boolean; text: string } | null>(null)
  const dirty = JSON.stringify(f) !== JSON.stringify(original) || passwort !== ''

  useEffect(() => {
    api<MailSettings>('/settings/mail')
      .then((data) => { setF(data); setOriginal(data) })
      .finally(() => setLoading(false))
  }, [])

  // Nur die fuer den gewaehlten Provider relevanten Felder mitschicken -- password_set (nur
  // Anzeige) darf NIE mitgesendet werden, das Backend lehnt unbekannte Felder ab (422).
  const imapKoerper = () => ({
    host: f.host, port: f.port, security: f.security, username: f.username,
    drafts_folder: f.drafts_folder, ...(passwort ? { password: passwort } : {}),
  })

  const save = async () => {
    setSaving(true); setErr(null); setTestErgebnis(null)
    try {
      const body = f.provider === 'imap' ? { provider: 'imap', ...imapKoerper() } : { provider: 'gmail' }
      const out = await api<MailSettings>('/settings/mail', { method: 'PUT', body: JSON.stringify(body) })
      setF(out); setOriginal(out); setPasswort('')
      setSaved(true); setTimeout(() => setSaved(false), 2000)
    } catch (e: any) { setErr(e?.message || 'Speichern fehlgeschlagen') }
    finally { setSaving(false) }
  }

  const testen = async () => {
    setTesting(true); setErr(null); setTestErgebnis(null)
    try {
      const body = f.provider === 'imap' ? { provider: 'imap', ...imapKoerper() } : { provider: 'gmail' }
      const out = await api<{ ok: boolean; meldung: string }>('/settings/mail/test', {
        method: 'POST', body: JSON.stringify(body),
      })
      setTestErgebnis({ ok: true, text: out.meldung })
    } catch (e: any) {
      setTestErgebnis({ ok: false, text: e?.message || 'Verbindungstest fehlgeschlagen' })
    } finally { setTesting(false) }
  }

  if (loading) {
    return <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-400 shadow-sm">Lade E-Mail-Konto…</div>
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 text-sm font-semibold text-brand-navy">E-Mail-Konto</div>
      <p className="mb-3 text-xs text-slate-500">
        Es wird nie automatisch gesendet — nur gelesen und Entwürfe im gewählten Ordner
        abgelegt. Empfohlener Standard ist IMAP mit einem App-Passwort des Anbieters (nicht
        das normale Kontopasswort) — das funktioniert auch für Gmail. Die Gmail-API ist die
        Power-Variante mit voller Suchsyntax und braucht ein eigenes Google-Cloud-Projekt.
        Outlook.com/Microsoft-Konten werden mangels IMAP-Basic-Auth derzeit nicht
        unterstützt. Schritt-für-Schritt: docs/SETUP-EMAIL.md.
      </p>
      <div className="flex flex-wrap gap-4">
        <label className="flex items-center gap-1.5 text-sm text-slate-700">
          <input type="radio" name="mail-provider" checked={f.provider === 'gmail'}
            onChange={() => setF({ ...f, provider: 'gmail' })} />
          Gmail (API)
        </label>
        <label className="flex items-center gap-1.5 text-sm text-slate-700">
          <input type="radio" name="mail-provider" checked={f.provider === 'imap'}
            onChange={() => setF({ ...f, provider: 'imap' })} />
          IMAP (Gmail, GMX, Web.de, mailbox.org, Posteo, iCloud-Mail, …)
        </label>
      </div>

      {f.provider === 'imap' && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <label className="text-xs text-slate-500">
            Host
            <input className={`${INPUT} mt-0.5 w-full`} value={f.host}
              onChange={(e) => setF({ ...f, host: e.target.value })} placeholder="imap.gmx.net" />
          </label>
          <label className="text-xs text-slate-500">
            Port
            <input type="number" className={`${INPUT} mt-0.5 w-full`} value={f.port}
              onChange={(e) => setF({ ...f, port: Number(e.target.value) || 993 })} />
          </label>
          <label className="text-xs text-slate-500">
            Sicherheit
            <select className={`${INPUT} mt-0.5 w-full`} value={f.security}
              onChange={(e) => setF({ ...f, security: e.target.value as MailSettings['security'] })}>
              <option value="ssl">SSL/TLS</option>
              <option value="starttls">STARTTLS</option>
            </select>
          </label>
          <label className="text-xs text-slate-500">
            Benutzer
            <input className={`${INPUT} mt-0.5 w-full`} value={f.username}
              onChange={(e) => setF({ ...f, username: e.target.value })} placeholder="ich@gmx.de" />
          </label>
          <label className="text-xs text-slate-500">
            Passwort
            <input type="password" className={`${INPUT} mt-0.5 w-full`} value={passwort}
              onChange={(e) => setPasswort(e.target.value)}
              placeholder={f.password_set ? 'gespeichert' : 'App-Passwort'} />
            {f.password_set && (
              <span className="mt-0.5 block text-[11px] text-slate-400">Leer lassen, um das gespeicherte Passwort zu behalten.</span>
            )}
          </label>
          <label className="text-xs text-slate-500">
            Entwürfe-Ordner
            <input className={`${INPUT} mt-0.5 w-full`} value={f.drafts_folder}
              onChange={(e) => setF({ ...f, drafts_folder: e.target.value })} placeholder="Entwürfe" />
          </label>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
        <button onClick={testen} disabled={testing || saving}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40">
          {testing ? 'Testet…' : 'Verbindung testen'}
        </button>
        <button onClick={save} disabled={saving || testing || !dirty}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? 'Speichern…' : 'Speichern'}
        </button>
        {saved && <span className="text-sm text-emerald-600">✓ Gespeichert</span>}
        {err && <span className="text-sm text-rose-600">{err}</span>}
      </div>
      {testErgebnis && (
        <div className={`mt-2 text-sm ${testErgebnis.ok ? 'text-emerald-600' : 'text-rose-600'}`}>
          {testErgebnis.ok ? '✓ ' : '✗ '}{testErgebnis.text}
        </div>
      )}
    </div>
  )
}

// ── Beispieldaten (P2-59) — die erfundenen Daten einer frischen Paket-Installation, per Knopf zu
// entfernen. Eigener Endpunkt (/api/beispieldaten, s. app/routes_beispieldaten.py), deshalb wie
// MailKontoKarte ein eigener, in sich geschlossener Lade-Zyklus; die Typen stehen bewusst lokal hier.
// Die Karte erscheint nur, wenn es etwas zu sagen gibt (vorhanden oder entfernt). Ein Ladefehler
// zählt als „keine Karte“: lieber nichts als eine falsche Aussage.
interface BeispieldatenStatus {
  status: 'keine' | 'vorhanden' | 'entfernt'
  name: string | null
  angelegt_am: string | null
  entfernt_am: string | null
  anzahl: Record<string, number>
}

interface BeispieldatenErgebnis {
  ok: boolean
  entfernt: Record<string, number>
  geloest: { mails: number; aufgaben: number }
  behalten: string[]
  sicherung: string
  status: BeispieldatenStatus
}

// Anzeigenamen der Arten in der Reihenfolge des Backends (beispieldaten.py::_ARTEN, dazu die Dateien).
const BEISPIEL_ARTEN: [string, string, string][] = [
  ['stellen', 'Stelle', 'Stellen'], ['firmen', 'Firma', 'Firmen'],
  ['bewerbungen', 'Bewerbung', 'Bewerbungen'], ['mails', 'Mail', 'Mails'],
  ['gespraeche', 'Gesprächstermin', 'Gesprächstermine'], ['kontakte', 'Ansprechperson', 'Ansprechpersonen'],
  ['netzwerk', 'Netzwerk-Kontakt', 'Netzwerk-Kontakte'], ['skills', 'Skill', 'Skills'],
  ['werdegang', 'Werdegang-Eintrag', 'Werdegang-Einträge'], ['dateien', 'Datei', 'Dateien'],
]

// „5 Stellen, 6 Firmen, …“ — nur Arten mit Anzahl > 0; `nur` schränkt auf einzelne Arten ein.
function beispielZaehlung(zahlen: Record<string, number>, nur?: string[]): string {
  return BEISPIEL_ARTEN
    .filter(([art]) => (zahlen[art] ?? 0) > 0 && (!nur || nur.includes(art)))
    .map(([art, einzahl, mehrzahl]) => `${zahlen[art]} ${zahlen[art] === 1 ? einzahl : mehrzahl}`)
    .join(', ')
}

function BeispieldatenKarte() {
  const [info, setInfo] = useState<BeispieldatenStatus | null>(null)
  const [frage, setFrage] = useState(false)
  const [busy, setBusy] = useState(false)
  const [fehler, setFehler] = useState<string | null>(null)
  const [ergebnis, setErgebnis] = useState<BeispieldatenErgebnis | null>(null)

  useEffect(() => {
    api<BeispieldatenStatus>('/beispieldaten').then(setInfo).catch(() => setInfo(null))
  }, [])

  const entfernen = async () => {
    setBusy(true); setFehler(null)
    try {
      const out = await api<BeispieldatenErgebnis>('/beispieldaten/entfernen', { method: 'POST' })
      setErgebnis(out); setInfo(out.status); setFrage(false)
      // Seitenleiste und Adress-Cache zeigen sonst bis zum Neuladen noch den Beispielnamen.
      window.dispatchEvent(new Event(PROFIL_GEAENDERT))
    } catch (e: any) {
      setFehler(e?.message || 'Entfernen fehlgeschlagen')
    } finally {
      setBusy(false)
    }
  }

  if (!info || info.status === 'keine') return null

  if (info.status === 'entfernt') {
    // Direkt nach dem Entfernen: Ergebnis mit Sicherung. Nach einem Neuladen nur noch die kleine Zeile.
    if (!ergebnis) {
      return (
        <p className="px-1 text-xs text-slate-400">
          Beispieldaten entfernt am {deDatum((info.entfernt_am ?? '').slice(0, 10))}.
        </p>
      )
    }
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-1 text-sm font-semibold text-brand-navy">Beispieldaten</div>
        <p className="text-sm text-emerald-700">✓ Beispieldaten entfernt: {beispielZaehlung(ergebnis.entfernt)}.</p>
        <p className="mt-1 text-xs text-slate-500">
          Vorher gesichert: <code className="rounded bg-slate-100 px-1">{ergebnis.sicherung}</code>
        </p>
        {ergebnis.behalten.length > 0 && (
          <p className="mt-1 text-xs text-slate-500">
            Diese Dateien wurden nicht entfernt, weil Sie sie geändert haben oder sie in Benutzung sind:{' '}
            {ergebnis.behalten.map((pfad, i) => (
              <span key={pfad}>{i > 0 ? ', ' : ''}<code className="rounded bg-slate-100 px-1">{pfad}</code></span>
            ))}.
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 text-sm font-semibold text-brand-navy">Beispieldaten</div>
      <p className="mb-3 text-sm text-slate-700">
        Diese Installation enthält Beispieldaten von {info.name ?? 'Birne Helene'} zum Ausprobieren:{' '}
        {beispielZaehlung(info.anzahl, ['stellen', 'firmen', 'bewerbungen', 'mails', 'gespraeche'])}, dazu
        Profil, Werdegang und ein Lebenslauf. Entfernen Sie sie, bevor Sie Ihre eigenen Daten eintragen.
        Vorher legt das BMS eine Sicherung an. Eigene Einträge bleiben erhalten.
      </p>
      {frage ? (
        <div className="space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-2.5 text-sm text-amber-900">
          <p><b>Beispieldaten jetzt entfernen?</b> Das BMS sichert vorher Ihre Datenbank.</p>
          <div className="flex gap-2">
            <button onClick={entfernen} disabled={busy}
              className="rounded-md bg-amber-600 px-2.5 py-1 text-xs font-medium text-white hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50">
              {busy ? 'Entfernt…' : 'Ja, entfernen'}
            </button>
            <button onClick={() => setFrage(false)} disabled={busy}
              className="rounded-md border border-amber-300 px-2.5 py-1 text-xs hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50">
              Abbrechen
            </button>
          </div>
        </div>
      ) : (
        <button onClick={() => { setFehler(null); setFrage(true) }}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover">
          Beispieldaten entfernen
        </button>
      )}
      {fehler && <div className="mt-2 text-sm text-rose-600">{fehler}</div>}
    </div>
  )
}

export default function Einstellungen() {
  const [data, setData] = useState<EinstellungenT | null>(null)
  const [loading, setLoading] = useState(true)

  const load = () => api<EinstellungenT>('/einstellungen').then(setData).finally(() => setLoading(false))
  useEffect(() => { load() }, [])

  if (loading || !data) return <div className="text-slate-400">Lade…</div>

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">Einstellungen</h1>
        <p className="text-sm text-slate-500">
          Grundsätzliche Parameter für die Jobsuche — Pläne A/B/C sowie Suchbereich und
          Firmengröße. Wird beim Speichern in <code className="rounded bg-slate-100 px-1">config/suchprofile.yaml</code> übernommen.
        </p>
      </div>
      <BeispieldatenKarte />
      <MailKontoKarte />
      <div className="grid gap-4 md:grid-cols-2">
        <SuchbereichKarte suchbereich={data.suchbereich} minMitarbeiter={data.min_mitarbeiter}
          umkreisLabel={data.umkreis_label} onSaved={load} />
        <ModelleKarte modelle={data.modelle} modellOptionen={data.modell_optionen} modellStandard={data.modell_standard} onSaved={load} />
      </div>
      <div>
        <div className="mb-2 text-xs text-slate-500">Reihenfolge der Jobsuche: Plan A → B → C</div>
        <div className="grid gap-4 md:grid-cols-3">
          {data.plaene.map((p) => <PlanKarte key={p.plan} plan={p} onSaved={load} />)}
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <PortaleKarte portale={data.portale} onSaved={load} />
        <UnterlagenKarte unterlagen={data.unterlagen} onSaved={load} />
      </div>
      <BeiratKarte />
      <CoachSiteKarte />
      <SicherungKarte />
      <VersionKarte />
    </div>
  )
}

// ── Coach-Site (Phase 81, ab Phase 82 konfigurierbar): Read-only-Spiegel für den Coach ────────
// Eigener Endpunkt (/api/settings/coach, s. app/routes_coach_settings.py), deshalb wie
// MailKontoKarte ein eigener, in sich geschlossener Lade-Zyklus statt Props vom Eltern-`data`.
// Export deterministisch (Whitelist, s. config/coach_export.yaml + Spec Phase 81), Upload per
// SFTP; läuft zusätzlich automatisch am Ende jedes Tageslaufs (Aktiv-Schalter + vollständige
// Konfiguration vorausgesetzt — sonst überspringt der Tageslauf grün, s. docs/COACH_SITE.md).
interface CoachSettings {
  aktiv: boolean
  site_url: string
  sftp_host: string
  sftp_user: string
  sftp_dir: string
  authuserfile: string
  coach_user: string
  sftp_password_set: boolean
  coach_password_set: boolean
  quelle: string
}

const COACH_DEFAULTS: CoachSettings = {
  aktiv: false, site_url: '', sftp_host: '', sftp_user: '', sftp_dir: '',
  authuserfile: '', coach_user: '', sftp_password_set: false, coach_password_set: false, quelle: 'leer',
}

// Nur die editierbaren Felder aus dem Formular schneiden (Muster MailKontoKarte::imapKoerper) —
// die *_set-Flags und `quelle` sind reine Anzeige und dürfen laut API-Kontrakt nicht mitgesendet
// werden (PUT lehnt unbekannte Felder mit 422 ab). Passwörter nur bei echter Neueingabe dabei,
// sonst behält das Backend das gespeicherte (Spec Phase 82, Abschnitt 1.4).
function coachKoerper(f: CoachSettings, sftpPasswort: string, coachPasswort: string) {
  return {
    aktiv: f.aktiv, site_url: f.site_url, sftp_host: f.sftp_host, sftp_user: f.sftp_user,
    sftp_dir: f.sftp_dir, authuserfile: f.authuserfile, coach_user: f.coach_user,
    ...(sftpPasswort ? { sftp_password: sftpPasswort } : {}),
    ...(coachPasswort ? { coach_password: coachPasswort } : {}),
  }
}

// Deckt sich mit `fehlende_felder()` im Backend (Spec 1.4) — bestimmt, ob der
// „Coach-Site jetzt aktualisieren"-Button erscheinen darf.
function coachVollstaendig(s: CoachSettings): boolean {
  return !!(s.site_url && s.sftp_host && s.sftp_user && s.sftp_password_set
    && s.sftp_dir && s.authuserfile && s.coach_user && s.coach_password_set)
}

function CoachSiteKarte() {
  const [f, setF] = useState<CoachSettings>(COACH_DEFAULTS)
  const [original, setOriginal] = useState<CoachSettings>(COACH_DEFAULTS)
  const [sftpPasswort, setSftpPasswort] = useState('')
  const [coachPasswort, setCoachPasswort] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [testing, setTesting] = useState(false)
  const [testErgebnis, setTestErgebnis] = useState<{ ok: boolean; text: string } | null>(null)
  const [ermitteln, setErmitteln] = useState(false)
  const [ermittelnErr, setErmittelnErr] = useState<string | null>(null)
  const dirty = JSON.stringify(f) !== JSON.stringify(original) || sftpPasswort !== '' || coachPasswort !== ''

  useEffect(() => {
    api<CoachSettings>('/settings/coach')
      .then((data) => { setF(data); setOriginal(data) })
      .finally(() => setLoading(false))
  }, [])

  const save = async () => {
    setSaving(true); setErr(null); setTestErgebnis(null)
    try {
      const out = await api<CoachSettings>('/settings/coach', {
        method: 'PUT', body: JSON.stringify(coachKoerper(f, sftpPasswort, coachPasswort)),
      })
      setF(out); setOriginal(out); setSftpPasswort(''); setCoachPasswort('')
      setSaved(true); setTimeout(() => setSaved(false), 2000)
    } catch (e: any) { setErr(e?.message || 'Speichern fehlgeschlagen') }
    finally { setSaving(false) }
  }

  const testen = async () => {
    setTesting(true); setErr(null); setTestErgebnis(null)
    try {
      const out = await api<{ ok: boolean; meldung: string }>('/settings/coach/test', {
        method: 'POST', body: JSON.stringify(coachKoerper(f, sftpPasswort, coachPasswort)),
      })
      setTestErgebnis({ ok: true, text: out.meldung })
    } catch (e: any) {
      setTestErgebnis({ ok: false, text: e?.message || 'Verbindungstest fehlgeschlagen' })
    } finally { setTesting(false) }
  }

  // Serverpfad-Automatik (Spec 1.4, POST /serverpfad): läuft nur im leeren Zielverzeichnis (sonst
  // 409 mit langer, bewusst vollständig sichtbarer Meldung) — Erfolg füllt nur das Feld, „Speichern"
  // bleibt trotzdem nötig (derselbe Dirty/Save-Fluss wie bei jedem anderen Feld dieser Karte).
  const serverpfadErmitteln = async () => {
    setErmitteln(true); setErmittelnErr(null)
    try {
      const out = await api<{ authuserfile: string; serverpfad: string }>('/settings/coach/serverpfad', {
        method: 'POST', body: JSON.stringify(coachKoerper(f, sftpPasswort, coachPasswort)),
      })
      setF((cur) => ({ ...cur, authuserfile: out.authuserfile }))
    } catch (e: any) {
      setErmittelnErr(e?.message || 'Serverpfad konnte nicht ermittelt werden')
    } finally { setErmitteln(false) }
  }

  if (loading) {
    return <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-400 shadow-sm">Lade Coach-Site…</div>
  }

  // Der Aktualisieren-Button setzt einen echten Upload-Lauf in Gang, der die GESPEICHERTE
  // Konfiguration liest — deshalb gegen `original` prüfen (letzter bekannter Server-Stand), nicht
  // gegen `f` (kann ungespeicherte Änderungen enthalten, die der Lauf so noch nicht sehen würde).
  const bereit = original.aktiv && coachVollstaendig(original)

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 text-sm font-semibold text-brand-navy">Coach-Site</div>
      <p className="mb-3 text-xs text-slate-500">
        Passwortgeschützter Read-only-Spiegel für den Coach{f.site_url ? <> unter{' '}
          <a href={f.site_url} target="_blank" rel="noreferrer" className="font-semibold text-brand-cyan">
            {f.site_url.replace(/^https:\/\//, '')}
          </a>
        </> : ''}: Übersicht, aktive Bewerbungen UND Sichtung/Prüfung (Neu + Prüfen) — je Stelle mit
        Company-Fit, Match und Stellenausschreibung (ohne internen Erfassungs-Kontext) — plus
        Absagen mit Gründen. Keine E-Mails, Notizen, Beirats-Checks, Gehälter oder Transkripte.
        Aktualisiert sich automatisch am Ende des Tageslaufs — oder hier sofort.
        Schritt-für-Schritt: docs/ANLEITUNG_COACH_SITE.md.
      </p>

      <label className="flex items-center gap-2 text-sm text-slate-700">
        <input type="checkbox" checked={f.aktiv} onChange={(e) => setF({ ...f, aktiv: e.target.checked })} />
        Coach-Site aktiv
      </label>

      <div className="mt-3 border-t border-slate-100 pt-3">
        <label className="text-xs text-slate-500">
          Adresse der Seite
          <input className={`${INPUT} mt-0.5 w-full`} value={f.site_url}
            onChange={(e) => setF({ ...f, site_url: e.target.value })} placeholder="https://coach.meine-domain.de" />
        </label>
      </div>

      <div className="mt-3 border-t border-slate-100 pt-3">
        <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">Upload-Ziel (SFTP)</div>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="text-xs text-slate-500">
            Host
            <input className={`${INPUT} mt-0.5 w-full`} value={f.sftp_host}
              onChange={(e) => setF({ ...f, sftp_host: e.target.value })} placeholder="access-xyz.webspace-host.com" />
          </label>
          <label className="text-xs text-slate-500">
            Benutzer
            <input className={`${INPUT} mt-0.5 w-full`} value={f.sftp_user}
              onChange={(e) => setF({ ...f, sftp_user: e.target.value })} />
          </label>
          <label className="text-xs text-slate-500">
            Passwort
            <input type="password" className={`${INPUT} mt-0.5 w-full`} value={sftpPasswort}
              onChange={(e) => setSftpPasswort(e.target.value)}
              placeholder={f.sftp_password_set ? 'gespeichert' : 'SFTP-Passwort'} />
            {f.sftp_password_set && (
              <span className="mt-0.5 block text-[11px] text-slate-400">Leer lassen, um das gespeicherte Passwort zu behalten.</span>
            )}
          </label>
          <label className="text-xs text-slate-500">
            Zielverzeichnis
            <input className={`${INPUT} mt-0.5 w-full`} value={f.sftp_dir}
              onChange={(e) => setF({ ...f, sftp_dir: e.target.value })} placeholder="/coach" />
          </label>
        </div>
      </div>

      <div className="mt-3 border-t border-slate-100 pt-3">
        <label className="text-xs text-slate-500">
          Serverpfad zur Zugangsdatei
          <div className="mt-0.5 flex gap-2">
            <input className={`${INPUT} flex-1`} value={f.authuserfile}
              onChange={(e) => setF({ ...f, authuserfile: e.target.value })} placeholder="/serverpfad/zum/verzeichnis/.htpasswd" />
            <button onClick={serverpfadErmitteln} disabled={ermitteln}
              className="shrink-0 rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40">
              {ermitteln ? 'Ermittelt…' : 'automatisch ermitteln'}
            </button>
          </div>
        </label>
        {ermittelnErr && <div className="mt-1 text-xs text-rose-600">{ermittelnErr}</div>}
      </div>

      <div className="mt-3 border-t border-slate-100 pt-3">
        <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Coach-Login</div>
        <p className="mb-1.5 mt-0.5 text-[11px] text-slate-400">Damit meldet sich dein Coach auf der Seite an.</p>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="text-xs text-slate-500">
            Benutzer
            <input className={`${INPUT} mt-0.5 w-full`} value={f.coach_user}
              onChange={(e) => setF({ ...f, coach_user: e.target.value })} />
          </label>
          <label className="text-xs text-slate-500">
            Passwort
            <input type="password" className={`${INPUT} mt-0.5 w-full`} value={coachPasswort}
              onChange={(e) => setCoachPasswort(e.target.value)}
              placeholder={f.coach_password_set ? 'gespeichert' : 'Coach-Passwort'} />
            {f.coach_password_set && (
              <span className="mt-0.5 block text-[11px] text-slate-400">Leer lassen, um das gespeicherte Passwort zu behalten.</span>
            )}
          </label>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
        <button onClick={testen} disabled={testing || saving}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40">
          {testing ? 'Testet…' : 'Verbindung testen'}
        </button>
        <button onClick={save} disabled={saving || testing || !dirty}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? 'Speichern…' : 'Speichern'}
        </button>
        {saved && <span className="text-sm text-emerald-600">✓ Gespeichert</span>}
        {err && <span className="text-sm text-rose-600">{err}</span>}
      </div>
      {testErgebnis && (
        <div className={`mt-2 text-sm ${testErgebnis.ok ? 'text-emerald-600' : 'text-rose-600'}`}>
          {testErgebnis.ok ? '✓ ' : '✗ '}{testErgebnis.text}
        </div>
      )}

      <div className="mt-3 border-t border-slate-100 pt-3">
        {bereit ? (
          <AgentTaskButton kind="coach-site" label="Coach-Site jetzt aktualisieren" />
        ) : (
          <div className="text-xs text-slate-400">Erst aktivieren und speichern, dann kann die Seite hochgeladen werden.</div>
        )}
      </div>
    </div>
  )
}

// ── Datensicherung (P2-52) — automatischer täglicher Sicherungslauf im Server (Backend:
// app/sicherung.py, Router app/routes_sicherung.py). Eigener Endpunkt (/api/sicherung,
// GET/POST/PATCH), deshalb wie MailKontoKarte/CoachSiteKarte ein eigener, in sich geschlossener
// Lade-Zyklus statt Props vom Eltern-`data` (das speist ausschliesslich /api/einstellungen —
// eine andere Ressource). Zwischen Coach-Site und Programmversion einsortiert (Spec P2-52, F1).
type SicherungEinstellungen = { aktiv: boolean; taeglich: number; woechentlich: number; monatlich: number }

// MB-Anzeige (Spec F1): ganze MB ab 10 MB, sonst eine Nachkommastelle mit Komma (deutsches
// Format, Muster Dashboard.tsx::dePercentProsa). Dezimale MB wie im Finder, damit die Zahl mit
// dem übereinstimmt, was der Nutzer im Ordner sieht.
function mb(bytes: number): string {
  const m = bytes / 1_000_000
  return m >= 10 ? `${Math.round(m)} MB` : `${m.toFixed(1).replace('.', ',')} MB`
}

// Datum + Uhrzeit aus dem ISO-Zeitpunkt mit Offset (V4: `.astimezone().isoformat()`) — anders als
// `deDatum()` (reines Datum ohne Uhrzeit) hier über `toLocaleString`, Muster Inbox.tsx::fmt.
function fmtZeitpunkt(iso: string): string {
  try {
    return new Date(iso).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

function SicherungKarte() {
  const [status, setStatus] = useState<SicherungStatus | null>(null)
  const [ladeFehler, setLadeFehler] = useState(false)
  const [loading, setLoading] = useState(true)
  const [f, setF] = useState<SicherungEinstellungen>({ aktiv: true, taeglich: 7, woechentlich: 4, monatlich: 0 })
  const [original, setOriginal] = useState<SicherungEinstellungen>(f)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saveErr, setSaveErr] = useState<string | null>(null)
  const dirty = JSON.stringify(f) !== JSON.stringify(original)
  const [sichernBusy, setSichernBusy] = useState(false)
  const [sichernErgebnis, setSichernErgebnis] = useState<string | null>(null)
  const [sichernErr, setSichernErr] = useState<string | null>(null)

  // Status UND die Aufbewahrungs-Felder gemeinsam übernehmen (Muster PlanKarte/ModelleKarte:
  // nach jedem erfolgreichen Laden/Speichern ist `f` wieder der Server-Stand, `dirty` also false).
  const uebernehmen = (data: SicherungStatus) => {
    setStatus(data)
    const einst = { aktiv: data.aktiv, taeglich: data.taeglich, woechentlich: data.woechentlich, monatlich: data.monatlich }
    setF(einst); setOriginal(einst)
  }

  const load = () =>
    api<SicherungStatus>('/sicherung')
      .then((data) => { uebernehmen(data); setLadeFehler(false) })
      .catch(() => setLadeFehler(true))
      .finally(() => setLoading(false))
  useEffect(() => { load() }, [])

  const save = async () => {
    setSaving(true); setSaveErr(null)
    try {
      const out = await api<SicherungStatus>('/sicherung/einstellungen', { method: 'PATCH', body: JSON.stringify(f) })
      uebernehmen(out)
      setSaved(true); setTimeout(() => setSaved(false), 2000)
    } catch (e: any) { setSaveErr(e?.message || 'Speichern fehlgeschlagen') }
    finally { setSaving(false) }
  }

  // Läuft unabhängig von `aktiv` (Spec V4/Entscheidung 4) und liefert die neue Datei direkt in
  // der Antwort — kein zweiter GET nötig, `status` kommt gleich mit (`out.status`, wie `out` bei
  // PATCH oben).
  const jetztSichern = async () => {
    setSichernBusy(true); setSichernErr(null); setSichernErgebnis(null)
    try {
      const out = await api<{ neu: { datei: string; zeitpunkt: string; groesse: number }; entfernt: string[]; status: SicherungStatus }>(
        '/sicherung', { method: 'POST' })
      setSichernErgebnis(`${out.neu.datei} (${mb(out.neu.groesse)})`)
      setStatus(out.status)
    } catch (e: any) {
      setSichernErr(e?.message || 'Sicherung fehlgeschlagen')
    } finally {
      setSichernBusy(false)
    }
  }

  if (loading) {
    return <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-400 shadow-sm">Lade Datensicherung…</div>
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 text-sm font-semibold text-brand-navy">Datensicherung</div>
      <p className="mb-3 text-xs text-slate-500">
        Das BMS sichert Ihre Datenbank einmal täglich als ZIP-Datei, solange es läuft. Ältere
        automatische Sicherungen entfernt es nach der Aufbewahrungsregel.
      </p>

      {ladeFehler && <div className="mb-3 text-sm text-rose-600">Sicherungsstatus konnte nicht geladen werden.</div>}

      {!ladeFehler && status && (
        <>
          <div className="space-y-1 text-sm text-slate-700">
            <div>
              {status.letzte
                ? `Letzte Sicherung: ${fmtZeitpunkt(status.letzte.zeitpunkt)} (${mb(status.letzte.groesse)})`
                : 'Noch keine automatische Sicherung.'}
            </div>
            <div className="text-xs text-slate-500">
              {status.anzahl} automatische {status.anzahl === 1 ? 'Sicherung' : 'Sicherungen'}, zusammen {mb(status.gesamtgroesse)}
            </div>
            {status.weitere.anzahl > 0 && (
              <div className="text-xs text-slate-500">
                Dazu {status.weitere.anzahl} {status.weitere.anzahl === 1 ? 'weitere Sicherung' : 'weitere Sicherungen'} direkt
                in data/backups ({mb(status.weitere.gesamtgroesse)}). Diese entfernt das BMS nie.
              </div>
            )}
          </div>

          {status.warnung && (
            <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-sm text-amber-800">
              {status.warnung}
            </div>
          )}
          {/* Bei ausgeschalteter Automatik gibt das Backend bewusst keine Warnung (V4) — die Karte
              sagt es trotzdem ausdrücklich, sonst wirkt eine alte „Letzte Sicherung" aktuell. */}
          {!status.aktiv && (
            <div className="mt-2 text-sm text-slate-500">Die automatische Sicherung ist ausgeschaltet.</div>
          )}

          <div className="mt-3 space-y-2 border-t border-slate-100 pt-3">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={f.aktiv} onChange={(e) => setF({ ...f, aktiv: e.target.checked })} />
              Täglich automatisch sichern
            </label>
            <div className="flex flex-wrap items-center gap-1.5 text-sm text-slate-700">
              <span>Aufbewahren:</span>
              <input type="number" className={`${INPUT} w-16`} value={f.taeglich}
                onChange={(e) => setF({ ...f, taeglich: Number(e.target.value) || 0 })} />
              <span>tägliche,</span>
              <input type="number" className={`${INPUT} w-16`} value={f.woechentlich}
                onChange={(e) => setF({ ...f, woechentlich: Number(e.target.value) || 0 })} />
              <span>wöchentliche,</span>
              <input type="number" className={`${INPUT} w-16`} value={f.monatlich}
                onChange={(e) => setF({ ...f, monatlich: Number(e.target.value) || 0 })} />
              <span>monatliche</span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button onClick={save} disabled={saving || !dirty}
                className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
                {saving ? 'Speichern…' : 'Speichern'}
              </button>
              {saved && <span className="text-sm text-emerald-600">✓ Gespeichert</span>}
              {saveErr && <span className="text-sm text-rose-600">{saveErr}</span>}
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
            <button onClick={jetztSichern} disabled={sichernBusy}
              className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
              {sichernBusy ? 'Sichere…' : 'Jetzt sichern'}
            </button>
            {sichernErgebnis && <span className="text-sm text-emerald-600">✓ Gesichert: {sichernErgebnis}</span>}
            {sichernErr && <span className="text-sm text-rose-600">{sichernErr}</span>}
          </div>

          <div className="mt-3 border-t border-slate-100 pt-3 text-xs text-slate-500">
            Ordner: <code className="break-all rounded bg-slate-100 px-1">{status.ordner}</code>
          </div>
        </>
      )}

      <p className="mt-3 border-t border-slate-100 pt-3 text-xs text-slate-500">
        Zurückspielen: BMS beenden und wiederherstellen.command (Mac) bzw.
        wiederherstellen_windows.bat (Windows) doppelklicken. Schritt für Schritt steht es in der
        Anleitung unter „Datensicherung“.
      </p>
    </div>
  )
}

// ── Programmversion (P2-51) — Update-/Versionsanzeige, letzte Karte der Einstellungen. Eigener
// Endpunkt (GET /api/version, s. backend/app/version.py und routes_version.py), deshalb wie
// MailKontoKarte/CoachSiteKarte ein eigener, in sich geschlossener Lade-Zyklus statt Props vom
// Eltern-`data` (das speist ausschliesslich /api/einstellungen — eine andere Ressource).
function versionHauptzeile(v: VersionInfo): string {
  if (v.installation === 'git') {
    return v.entwicklungsstand ? `Entwicklungsstand: ${v.entwicklungsstand}` : 'Entwicklungsstand: unbekannt'
  }
  if (!v.version || v.version === '0.0.0') return 'Noch keine freigegebene Version'
  return v.datum ? `Version ${v.version} · Stand ${deDatum(v.datum)}` : `Version ${v.version}`
}

// CHANGELOG-Abschnitt (V2 in der Spec) roh in <li> zerlegen — nur „- "-Zeilen, Backticks als
// <code>, sonst reiner Text. Bewusst kein Markdown-Paket: die Kundentexte in CHANGELOG.md sind
// als einfache Aufzählung festgelegt (Bau-Spec, Abschnitt V2).
function aenderungenListe(text: string | null): ReactNode {
  const zeilen = (text || '').split('\n').filter((z) => z.startsWith('- '))
  if (!zeilen.length) return null
  return (
    <ul className="list-disc space-y-0.5 pl-4">
      {zeilen.map((z, i) => (
        <li key={i}>
          {z.slice(2).split('`').map((teil, j) =>
            j % 2 === 1 ? <code key={j} className="rounded bg-slate-100 px-1">{teil}</code> : teil)}
        </li>
      ))}
    </ul>
  )
}

// Anleitung nur für das Betriebssystem der jeweiligen Installation (kein „bzw." mit beiden
// Varianten nebeneinander) — Skript-Namen aus U1 (scripts/bms_update.py-Startdateien).
// P2-82: Das Update-Werkzeug lädt die neue Version selbst von GitHub; die ZIP-Datei im
// Download-Ordner ist nur noch der Weg ohne Internet.
function updateAnleitung(betriebssystem: VersionInfo['betriebssystem'], installationsordner: string): ReactNode {
  const stop = betriebssystem === 'windows' ? 'stop_windows.bat' : 'stop.command'
  const update = betriebssystem === 'windows' ? 'update_windows.bat' : 'update.command'
  return (
    <>
      <ol className="list-decimal space-y-0.5 pl-4">
        <li>BMS beenden (<code className="rounded bg-slate-100 px-1">{stop}</code>).</li>
        <li>Im Programmordner (<code className="rounded bg-slate-100 px-1">{installationsordner}</code>) <code className="rounded bg-slate-100 px-1">{update}</code> doppelklicken. Es lädt die neue Version selbst von GitHub; folgen Sie den Anweisungen.</li>
        <li>BMS wie gewohnt starten.</li>
      </ol>
      <p className="mt-1.5 text-xs text-slate-500">
        Ohne Internet: die Datei <code className="rounded bg-slate-100 px-1">BMS_&lt;Version&gt;.zip</code> von
        der GitHub-Seite in den Download-Ordner legen, dann Schritt 2.
      </p>
    </>
  )
}

// ── Nach Updates suchen (P2-82) — Knopf in der Programmversion. Fragt nur auf Klick bei GitHub
// nach der neuesten Version (GET /api/version/neueste, s. backend/app/update_pruefen.py): kein Abruf
// beim Laden der Seite, kein Hintergrund-Abruf. Die App zeigt nur an; eingespielt wird weiter mit
// dem Update-Werkzeug bei beendetem Server. Die Änderungen sind reiner Text (aenderungenListe,
// kein HTML); der Link zur GitHub-Seite erscheint nur bei einer https-Adresse.
function updateErgebnis(e: NeuesteVersion): ReactNode {
  if (e.fehler) return <div className="text-sm text-rose-600">{e.fehler}</div>
  if (e.neuer === null || !e.neueste) return <div className="text-sm text-rose-600">Die Antwort ist ungültig.</div>
  if (!e.neuer) {
    return <div className="text-sm text-emerald-600">✓ Ihr BMS ist auf dem neuesten Stand (Version {e.installiert ?? e.neueste}).</div>
  }
  return (
    <div className="space-y-1.5 text-sm text-slate-700">
      <div className="font-medium text-brand-navy">
        Version {e.neueste} ist erschienen{e.veroeffentlicht ? ` (${deDatum(e.veroeffentlicht)})` : ''}.
      </div>
      {e.aenderungen && aenderungenListe(e.aenderungen)}
      {e.seite && e.seite.startsWith('https://') && (
        <a href={e.seite} target="_blank" rel="noopener noreferrer"
          className="inline-block font-semibold text-brand-cyan hover:underline">
          Auf GitHub ansehen ↗
        </a>
      )}
    </div>
  )
}

function UpdateSuche() {
  const [sucht, setSucht] = useState(false)
  const [ergebnis, setErgebnis] = useState<NeuesteVersion | null>(null)
  const [fehler, setFehler] = useState<string | null>(null)

  const suchen = async () => {
    setSucht(true); setErgebnis(null); setFehler(null)
    try {
      setErgebnis(await api<NeuesteVersion>('/version/neueste'))
    } catch {
      // Der Endpunkt antwortet bei GitHub-Problemen mit 200 und `fehler`; hierher kommt nur, wenn
      // das BMS selbst nicht antwortet.
      setFehler('Die Suche ließ sich nicht ausführen. Das BMS antwortet nicht.')
    } finally {
      setSucht(false)
    }
  }

  return (
    <div className="mt-3 border-t border-slate-100 pt-3">
      <button onClick={suchen} disabled={sucht}
        className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40">
        {sucht ? 'Suche …' : 'Nach Updates suchen'}
      </button>
      <p className="mt-1.5 text-xs text-slate-500">
        Fragt bei GitHub nach der neuesten Version. GitHub erhält dabei die IP-Adresse dieses Rechners.
      </p>
      <div className="mt-2" role="status" aria-live="polite">
        {ergebnis && updateErgebnis(ergebnis)}
        {fehler && <div className="text-sm text-rose-600">{fehler}</div>}
      </div>
    </div>
  )
}

function VersionKarte() {
  const [info, setInfo] = useState<VersionInfo | null>(null)
  const [ladeFehler, setLadeFehler] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api<VersionInfo>('/version')
      .then((data) => { setInfo(data); setLadeFehler(false) })
      .catch(() => setLadeFehler(true))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-400 shadow-sm">Lade Programmversion…</div>
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 text-sm font-semibold text-brand-navy">Programmversion</div>

      {ladeFehler || !info ? (
        <div className="text-sm text-slate-400">Versionsstand konnte nicht geladen werden.</div>
      ) : (
        <>
          <p className="text-sm text-slate-700">
            {versionHauptzeile(info)}
            {info.installation === 'git' && info.commit ? ` · Commit ${info.commit}` : ''}
          </p>
          {info.letztes_update && (
            <p className="mt-1 text-xs text-slate-500">
              Zuletzt aktualisiert am {deDatum(info.letztes_update.zeitpunkt.slice(0, 10))} von{' '}
              {info.letztes_update.von ?? 'unbekannt'} auf {info.letztes_update.nach}.
            </p>
          )}
          {info.aenderungen && (
            <div className="mt-3 border-t border-slate-100 pt-3">
              <div className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">
                {/* Git-Installation: der Abschnitt „Unveröffentlicht“ (V5), also noch nicht freigegeben */}
                {info.installation === 'git' ? 'Seit der letzten Freigabe' : 'Neu in dieser Version'}
              </div>
              <div className="text-sm text-slate-700">{aenderungenListe(info.aenderungen)}</div>
            </div>
          )}
          <UpdateSuche />
          {info.installation === 'git' ? (
            <div className="mt-3 border-t border-slate-100 pt-3 text-sm text-slate-700">
              Entwicklungsinstallation: Updates kommen über Git.
            </div>
          ) : (
            <div className="mt-3 border-t border-slate-100 pt-3 text-sm text-slate-700">
              <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">Update einspielen</div>
              {updateAnleitung(info.betriebssystem, info.installationsordner)}
              <p className="mt-1.5 text-xs text-slate-500">Vor dem Einspielen sichert das Update Datenbank und ersetzte Dateien.</p>
            </div>
          )}
        </>
      )}
    </div>
  )
}
