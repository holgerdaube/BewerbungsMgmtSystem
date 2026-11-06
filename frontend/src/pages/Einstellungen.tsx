import { useEffect, useId, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api, type BeiratMitglied, type Einstellungen as EinstellungenT, type KiAnbieterStatus, type KiStatus, type NeuesteVersion,
  type Umkreisumbenennung, type VersionInfo, type Plan, type Portal, type SicherungStatus } from '../api'
import AgentTaskButton from '../components/AgentTaskButton'
import { kiAnbieterUebernehmen } from '../components/ui'
import { suchTabsNeuLaden } from '../suchbereich'
import { PROFIL_GEAENDERT } from '../profil'
import { t } from '../i18n'
import { wert } from '../i18n/werte'
import { datum, datumZeit, zahl } from '../i18n/format'
import { Trans } from 'react-i18next'
import { SpracheKarte } from '../components/SpracheUmschalter'
import { SENIORITAETEN } from '../senioritaet'

const INPUT = 'rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none'

// §18.6-Kategorienpalette (Phase 80-Nachtrag, Entscheidung 10.08.2026, Muster
// Profil.tsx::BEREICH_FARBEN) — Cyan/Indigo/Violet statt der gedämpften Eigen-Töne;
// Rollback-Werte: tasks/spec_phase80_styleguide_v18_theme.md, WP-D.
const PLAN_FARBEN: Record<string, string> = { A: '#00B4D8', B: '#5B61E6', C: '#7C4DFF' }

// Phase 50 — Reihenfolge + Anzeigenamen der 6 Kern-Funktionen (Keys spiegeln
// agent_runner.py::FUNKTION_KINDS + "beirat").
const FUNKTIONEN: string[] = ['jobsuche', 'company-fit', 'beirat', 'cv-match', 'ats-scan', 'anschreiben']

// ── Chip-Liste: rein lokale State-Mutation (add/remove ohne eigenen API-Call) — erst der
// Karten-„Speichern"-Button persistiert den ganzen Plan in einem PATCH. Anders als
// Profil.tsx::Skills (dort sind Skills eigene DB-Zeilen mit sofortigem Add/Remove). ──────
function ChipListe({ label, werte, onChange, vorschlaege, anzeige = (w) => w }: { label: string; werte: string[]; onChange: (werte: string[]) => void; anzeige?: (w: string) => string; vorschlaege?: string[] }) {
  const [neu, setNeu] = useState('')
  const listenId = useId()
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
            {anzeige(w)}
            <button onClick={() => onChange(werte.filter((x) => x !== w))} className="ml-0.5 text-slate-400 hover:text-rose-600">×</button>
          </span>
        ))}
        {werte.length === 0 && <span className="text-xs text-slate-400">–</span>}
      </div>
      <div className="flex gap-1.5">
        <input className={`${INPUT} flex-1 text-xs`} placeholder={t('einstellungen:chips.hinzufuegen', { label })} value={neu} list={vorschlaege ? listenId : undefined}
          onChange={(e) => setNeu(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } }} />
        <button onClick={add} className="rounded-lg border border-slate-300 px-2.5 text-xs text-slate-600 hover:bg-slate-50">+</button>
        {vorschlaege && <datalist id={listenId}>{vorschlaege.map((v) => <option key={v} value={v} label={anzeige(v)} />)}</datalist>}
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
    } catch (e: any) { setErr(e?.message || t('einstellungen:allgemein.speichern_fehlgeschlagen')) }
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
          {t('einstellungen:allgemein.aktiv')}
        </label>
      </div>
      <div className="space-y-3">
        <ChipListe label={t('einstellungen:plan.titel')} werte={f.titel} onChange={(titel) => setF({ ...f, titel })} />
        <ChipListe label={t('einstellungen:plan.senioritaet')} anzeige={(w) => wert('seniority', w)} werte={f.senioritaet} onChange={(senioritaet) => setF({ ...f, senioritaet })} vorschlaege={SENIORITAETEN} />
        <ChipListe label={t('einstellungen:plan.branche')} werte={f.branche} onChange={(branche) => setF({ ...f, branche })} />
      </div>
      <div className="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3">
        <button onClick={save} disabled={saving || !dirty}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? t('einstellungen:allgemein.speichern_laeuft') : t('einstellungen:allgemein.speichern')}
        </button>
        {saved && <span className="text-sm text-emerald-600">{t('einstellungen:allgemein.gespeichert')}</span>}
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
    } catch (e: any) { setErr(e?.message || t('einstellungen:allgemein.speichern_fehlgeschlagen')) }
    finally { setSaving(false) }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 text-sm font-semibold text-brand-navy">{t('einstellungen:suchbereich.titel')}</div>
      <div className="space-y-2">
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={f.remote.aktiv}
            onChange={(e) => setF({ ...f, remote: { aktiv: e.target.checked } })} />
          {wert('tab', 'Remote')}
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={f.deutschlandweit.aktiv}
            onChange={(e) => setF({ ...f, deutschlandweit: { aktiv: e.target.checked } })} />
          {wert('tab', 'Deutschlandweit')}
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={f.umkreis.aktiv}
              onChange={(e) => setF({ ...f, umkreis: { ...f.umkreis, aktiv: e.target.checked } })} />
            {t('einstellungen:suchbereich.stadt_umkreis')}
          </label>
          {f.umkreis.aktiv && (
            <>
              <input className={`${INPUT} w-48`} value={f.umkreis.stadt} placeholder={t('einstellungen:suchbereich.stadt_platzhalter')}
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
          {t('einstellungen:suchbereich.min_groesse_vor')}
          <input type="number" className={`${INPUT} w-24`} value={f.min_mitarbeiter}
            onChange={(e) => setF({ ...f, min_mitarbeiter: Number(e.target.value) || 0 })} />
          {t('einstellungen:suchbereich.min_groesse_nach')}
        </label>
      </div>
      {label && <div className="mt-2 text-xs text-slate-400">{t('einstellungen:suchbereich.in_jobliste', { label })}</div>}
      {umbenennung && (
        <div className="mt-2 text-xs text-emerald-600">
          {t('einstellungen:suchbereich.umbenennung', { count: umbenennung.jobs, von: umbenennung.von, nach: umbenennung.nach })}
        </div>
      )}
      <div className="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3">
        <button onClick={save} disabled={saving || !dirty}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? t('einstellungen:allgemein.speichern_laeuft') : t('einstellungen:allgemein.speichern')}
        </button>
        {saved && <span className="text-sm text-emerald-600">{t('einstellungen:allgemein.gespeichert')}</span>}
        {err && <span className="text-sm text-rose-600">{err}</span>}
      </div>
    </div>
  )
}

// ── KI: Claude oder ChatGPT (P2-86) ─────────────────────────────────────────────────────────────
// Die Wahl liegt in den Einstellungen (PATCH ki_anbieter). Ob das Programm da und angemeldet ist, kommt
// getrennt aus /api/ki-status, weil das Backend dafür ein Programm startet. `angemeldet: null` heißt
// „nicht bekannt“ und wird nicht als „nein“ gezeigt. Nach dem Speichern lädt die Seite neu: `modell_optionen`
// der Karte „KI-Modell je Funktion“ gehören zum Anbieter.
function KiStatusZeile({ s }: { s: KiAnbieterStatus | undefined }) {
  if (!s) return <div className="mt-1.5 text-xs text-slate-400">{t('einstellungen:ki.status_pruefe')}</div>
  const chip = 'rounded-full px-2 py-0.5 text-xs font-medium'
  const gut = 'bg-emerald-100 text-emerald-800'
  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5">
      <span className={`${chip} ${s.installiert ? gut : 'bg-rose-100 text-rose-700'}`}>
        {s.installiert ? t('einstellungen:ki.installiert') : t('einstellungen:ki.nicht_installiert')}
      </span>
      {s.installiert && (
        <span className={`${chip} ${s.angemeldet === true ? gut : s.angemeldet === false ? 'bg-rose-100 text-rose-700' : 'bg-slate-100 text-slate-500'}`}>
          {s.angemeldet === true ? t('einstellungen:ki.angemeldet') : s.angemeldet === false ? t('einstellungen:ki.nicht_angemeldet') : t('einstellungen:ki.anmeldung_unbekannt')}
        </span>
      )}
    </div>
  )
}

function KiKarte({ ki, optionen, onSaved }: {
  ki: EinstellungenT['ki_anbieter']
  optionen: EinstellungenT['ki_anbieter_optionen']
  onSaved: () => void
}) {
  const [wert, setWert] = useState(ki)
  const [original, setOriginal] = useState(ki)
  const [status, setStatus] = useState<KiStatus | null>(null)
  const [statusFehler, setStatusFehler] = useState(false)
  const [pruefen, setPruefen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const dirty = wert !== original

  const statusLaden = () => {
    setPruefen(true); setStatusFehler(false)
    api<KiStatus>('/ki-status').then(setStatus).catch(() => setStatusFehler(true)).finally(() => setPruefen(false))
  }
  useEffect(() => { statusLaden() }, [])

  const save = async () => {
    setSaving(true); setErr(null)
    try {
      const out = await api<EinstellungenT>('/einstellungen', { method: 'PATCH', body: JSON.stringify({ ki_anbieter: wert }) })
      setOriginal(wert)
      kiAnbieterUebernehmen(out)   // Texte wie „in der Claude-Session starten“ schalten sofort um
      setSaved(true); setTimeout(() => setSaved(false), 2000)
      onSaved()
    } catch (e: any) { setErr(e?.message || t('einstellungen:allgemein.speichern_fehlgeschlagen')) }
    finally { setSaving(false) }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 text-sm font-semibold text-brand-navy">{t('einstellungen:ki.titel')}</div>
      <p className="mb-3 text-xs text-slate-500">
        <Trans i18nKey="einstellungen:ki.beschreibung" components={{ code: <code className="rounded bg-slate-100 px-1" /> }} />
      </p>
      <div className="grid gap-2 md:grid-cols-2">
        {optionen.map((o) => (
          <label key={o.wert}
            className={`cursor-pointer rounded-lg border p-3 ${wert === o.wert ? 'border-brand-cyan bg-brand-cyan/5' : 'border-slate-200 hover:bg-slate-50'}`}>
            <span className="flex items-center gap-2 text-sm font-medium text-brand-navy">
              <input type="radio" name="ki-anbieter" checked={wert === o.wert} onChange={() => setWert(o.wert)} />
              {o.label}
              {o.wert === 'chatgpt' && (
                <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-800">{t('einstellungen:ki.vorschau')}</span>
              )}
            </span>
            <KiStatusZeile s={statusFehler ? undefined : status?.[o.wert]} />
          </label>
        ))}
      </div>
      {statusFehler && <div className="mt-2 text-sm text-rose-600">{t('einstellungen:ki.status_fehler')}</div>}
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
        <button onClick={save} disabled={saving || !dirty}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? t('einstellungen:allgemein.speichern_laeuft') : t('einstellungen:allgemein.speichern')}
        </button>
        <button onClick={statusLaden} disabled={pruefen}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40">
          {pruefen ? t('einstellungen:ki.pruefen_laeuft') : t('einstellungen:ki.erneut_pruefen')}
        </button>
        {saved && <span className="text-sm text-emerald-600">{t('einstellungen:allgemein.gespeichert')}</span>}
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
  // P2-86: Die Beschriftungen unter ChatGPT sind länger als die Claude-Namen und würden im schmalen Feld abgeschnitten.
  const breit = modellOptionen.some((m) => m.label.length > 20)

  const save = async () => {
    setSaving(true); setErr(null)
    try {
      await api('/einstellungen', { method: 'PATCH', body: JSON.stringify({ modelle: f }) })
      setOriginal(f)
      setSaved(true); setTimeout(() => setSaved(false), 2000)
      onSaved()
    } catch (e: any) { setErr(e?.message || t('einstellungen:allgemein.speichern_fehlgeschlagen')) }
    finally { setSaving(false) }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 text-sm font-semibold text-brand-navy">{t('einstellungen:modelle.titel')}</div>
      <p className="mb-3 text-xs text-slate-500">
        {t('einstellungen:modelle.beschreibung', { standard: standardLabel })}
      </p>
      <div className="space-y-2">
        {FUNKTIONEN.map((key) => (
          <div key={key} className="flex items-center justify-between gap-2">
            <span className="text-sm text-slate-700">{t(`einstellungen:funktion.${key}`)}</span>
            <select className={`${INPUT} ${breit ? 'w-72' : 'w-40'}`} value={f[key] || modellStandard}
              onChange={(e) => setF({ ...f, [key]: e.target.value })}>
              {modellOptionen.map((m) => <option key={m.alias} value={m.alias}>{m.label}</option>)}
            </select>
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3">
        <button onClick={save} disabled={saving || !dirty}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? t('einstellungen:allgemein.speichern_laeuft') : t('einstellungen:allgemein.speichern')}
        </button>
        {saved && <span className="text-sm text-emerald-600">{t('einstellungen:allgemein.gespeichert')}</span>}
        {err && <span className="text-sm text-rose-600">{err}</span>}
      </div>
    </div>
  )
}

// ── Suchportale (Phase 87) — Name/URL je Portal, dreistufige Prüf-Ampel je Zeile ─────────
// Zugriffsart ist fest (bestimmt der jobsuche-Skill, nicht die Oberfläche) und erscheint nur
// als kleiner Hinweis: "websearch" sucht per WebSearch mit Domain-Anker (Bot-Schutz bei
// LinkedIn/Indeed/StepStone/Xing), "fetch" ruft die URL direkt ab (Nejo/Arbeitsagentur).
const zugriffLabel = (z: Portal['zugriff']): string => t(`einstellungen:portale.zugriff.${z}`)

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
    } catch (e: any) { setErr(e?.message || t('einstellungen:allgemein.speichern_fehlgeschlagen')) }
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
      setPruefung((cur) => ({ ...cur, [key]: { loading: false, fehler: e?.message || t('einstellungen:portale.pruefung_fehlgeschlagen') } }))
    }
  }

  const setZeile = (key: string, patch: Partial<Portal>) =>
    setF((cur) => cur.map((p) => (p.key === key ? { ...p, ...patch } : p)))

  const zeile = (p: Portal) => {
    const status = pruefung[p.key]
    return (
      <div key={p.key} className="py-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <input type="checkbox" checked={p.aktiv} title={t('einstellungen:allgemein.aktiv')}
            onChange={(e) => setZeile(p.key, { aktiv: e.target.checked })} />
          <input className={`${INPUT} w-32 shrink-0 text-sm`} value={p.name}
            onChange={(e) => setZeile(p.key, { name: e.target.value })}
            placeholder={p.standard ? undefined : t('einstellungen:portale.weiteres')} />
          <input className={`${INPUT} min-w-0 flex-1 text-sm`} value={p.url}
            onChange={(e) => setZeile(p.key, { url: e.target.value })}
            placeholder={p.standard ? undefined : 'https://…'} />
          <span className="w-28 shrink-0 text-[11px] text-slate-400">{zugriffLabel(p.zugriff)}</span>
          <button onClick={() => pruefen(p.key)} disabled={status?.loading || !p.url.trim()}
            className="shrink-0 rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40">
            {status?.loading ? t('einstellungen:portale.pruefe') : t('einstellungen:portale.pruefen')}
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
      <div className="mb-1 text-sm font-semibold text-brand-navy">{t('einstellungen:portale.titel')}</div>
      <p className="mb-3 text-xs text-slate-500">
        {t('einstellungen:portale.beschreibung')}
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
          {saving ? t('einstellungen:allgemein.speichern_laeuft') : t('einstellungen:allgemein.speichern')}
        </button>
        {saved && <span className="text-sm text-emerald-600">{t('einstellungen:allgemein.gespeichert')}</span>}
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
    } catch (e: any) { setErr(e?.message || t('einstellungen:allgemein.speichern_fehlgeschlagen')) }
    finally { setSaving(false) }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 text-sm font-semibold text-brand-navy">{t('einstellungen:unterlagen.titel')}</div>
      <p className="mb-3 text-xs text-slate-500">
        {t('einstellungen:unterlagen.beschreibung')}
      </p>
      <label className="flex items-center gap-2 text-sm text-slate-700">
        <input type="checkbox" checked={f.anschreiben}
          onChange={(e) => setF({ ...f, anschreiben: e.target.checked })} />
        {t('einstellungen:unterlagen.anschreiben')}
      </label>
      <div className="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3">
        <button onClick={save} disabled={saving || !dirty}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? t('einstellungen:allgemein.speichern_laeuft') : t('einstellungen:allgemein.speichern')}
        </button>
        {saved && <span className="text-sm text-emerald-600">{t('einstellungen:allgemein.gespeichert')}</span>}
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
    } catch (e: any) { setErr(e?.message || t('einstellungen:allgemein.speichern_fehlgeschlagen')) }
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
      neuFeld(id, { starting: false, err: e?.message || t('einstellungen:beirat.start_fehlgeschlagen') })
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
            {t('einstellungen:beirat.vorsitz')}
          </label>
          <button onClick={() => neuFeld(m.id, { ...NEU_LEER, offen: !n.offen })}
            className="shrink-0 rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50">
            {t('einstellungen:beirat.neu_besetzen')}
          </button>
        </div>
        {n.offen && (
          <div className="ml-5 mt-1.5 space-y-1.5 rounded-lg border border-slate-200 bg-slate-50 p-2.5">
            <p className="text-xs text-slate-500">
              {t('einstellungen:beirat.neu_hinweis')}
            </p>
            <input className={`${INPUT} w-full text-sm`} placeholder={t('einstellungen:beirat.name')} value={n.name}
              onChange={(e) => neuFeld(m.id, { name: e.target.value })} />
            <textarea className={`${INPUT} w-full text-sm`} rows={2} placeholder={t('einstellungen:beirat.perspektive_platzhalter')}
              value={n.perspektive} onChange={(e) => neuFeld(m.id, { perspektive: e.target.value })} />
            <div className="flex items-center gap-2">
              <button onClick={() => neuBesetzen(m.id)} disabled={n.starting || !n.name.trim() || !n.perspektive.trim()}
                className="rounded-lg bg-brand-cyan px-3 py-1.5 text-xs font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
                {n.starting ? t('einstellungen:beirat.startet') : t('einstellungen:beirat.bestaetigen')}
              </button>
              <button onClick={() => neuFeld(m.id, { ...NEU_LEER, offen: false })} disabled={n.starting}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40">
                {t('einstellungen:allgemein.abbrechen')}
              </button>
            </div>
            {n.err && <div className="text-xs text-rose-600">{n.err}</div>}
            {n.taskId != null && (
              <div className="text-xs text-emerald-600">
                <Trans i18nKey="einstellungen:beirat.lauf_gestartet" components={{ a: <Link to="/tasks" className="text-brand-cyan hover:underline" /> }} />
              </div>
            )}
          </div>
        )}
      </div>
    )
  }

  if (loading) {
    return <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-400 shadow-sm">{t('einstellungen:beirat.lade')}</div>
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 text-sm font-semibold text-brand-navy">{t('einstellungen:beirat.titel')}</div>
      <p className="mb-3 text-xs text-slate-500">
        {t('einstellungen:beirat.beschreibung')}
      </p>
      <div className="divide-y divide-slate-100">
        {f.map(zeile)}
      </div>
      <div className="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3">
        <button onClick={save} disabled={saving || !dirty}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? t('einstellungen:allgemein.speichern_laeuft') : t('einstellungen:allgemein.speichern')}
        </button>
        {saved && <span className="text-sm text-emerald-600">{t('einstellungen:allgemein.gespeichert')}</span>}
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
    } catch (e: any) { setErr(e?.message || t('einstellungen:allgemein.speichern_fehlgeschlagen')) }
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
      setTestErgebnis({ ok: false, text: e?.message || t('einstellungen:allgemein.test_fehlgeschlagen') })
    } finally { setTesting(false) }
  }

  if (loading) {
    return <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-400 shadow-sm">{t('einstellungen:mail.lade')}</div>
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 text-sm font-semibold text-brand-navy">{t('einstellungen:mail.titel')}</div>
      <p className="mb-3 text-xs text-slate-500">
        {t('einstellungen:mail.beschreibung')}
      </p>
      <div className="flex flex-wrap gap-4">
        <label className="flex items-center gap-1.5 text-sm text-slate-700">
          <input type="radio" name="mail-provider" checked={f.provider === 'gmail'}
            onChange={() => setF({ ...f, provider: 'gmail' })} />
          {t('einstellungen:mail.gmail_api')}
        </label>
        <label className="flex items-center gap-1.5 text-sm text-slate-700">
          <input type="radio" name="mail-provider" checked={f.provider === 'imap'}
            onChange={() => setF({ ...f, provider: 'imap' })} />
          {t('einstellungen:mail.imap')}
        </label>
      </div>

      {f.provider === 'imap' && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <label className="text-xs text-slate-500">
            {t('einstellungen:allgemein.host')}
            <input className={`${INPUT} mt-0.5 w-full`} value={f.host}
              onChange={(e) => setF({ ...f, host: e.target.value })} placeholder={t('einstellungen:mail.host_beispiel')} />
          </label>
          <label className="text-xs text-slate-500">
            {t('einstellungen:allgemein.port')}
            <input type="number" className={`${INPUT} mt-0.5 w-full`} value={f.port}
              onChange={(e) => setF({ ...f, port: Number(e.target.value) || 993 })} />
          </label>
          <label className="text-xs text-slate-500">
            {t('einstellungen:mail.sicherheit')}
            <select className={`${INPUT} mt-0.5 w-full`} value={f.security}
              onChange={(e) => setF({ ...f, security: e.target.value as MailSettings['security'] })}>
              <option value="ssl">SSL/TLS</option>{/* i18n-ok: Protokollname */}
              <option value="starttls">STARTTLS</option>{/* i18n-ok: Protokollname */}
            </select>
          </label>
          <label className="text-xs text-slate-500">
            {t('einstellungen:allgemein.benutzer')}
            <input className={`${INPUT} mt-0.5 w-full`} value={f.username}
              onChange={(e) => setF({ ...f, username: e.target.value })} placeholder={t('einstellungen:mail.benutzer_beispiel')} />
          </label>
          <label className="text-xs text-slate-500">
            {t('einstellungen:allgemein.passwort')}
            <input type="password" className={`${INPUT} mt-0.5 w-full`} value={passwort}
              onChange={(e) => setPasswort(e.target.value)}
              placeholder={f.password_set ? t('einstellungen:allgemein.passwort_gespeichert') : t('einstellungen:mail.app_passwort')} />
            {f.password_set && (
              <span className="mt-0.5 block text-[11px] text-slate-400">{t('einstellungen:allgemein.passwort_behalten')}</span>
            )}
          </label>
          <label className="text-xs text-slate-500">
            {t('einstellungen:mail.entwuerfe_ordner')}
            <input className={`${INPUT} mt-0.5 w-full`} value={f.drafts_folder}
              onChange={(e) => setF({ ...f, drafts_folder: e.target.value })} placeholder={t('einstellungen:mail.entwuerfe_platzhalter')} />
          </label>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
        <button onClick={testen} disabled={testing || saving}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40">
          {testing ? t('einstellungen:allgemein.testet') : t('einstellungen:allgemein.verbindung_testen')}
        </button>
        <button onClick={save} disabled={saving || testing || !dirty}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? t('einstellungen:allgemein.speichern_laeuft') : t('einstellungen:allgemein.speichern')}
        </button>
        {saved && <span className="text-sm text-emerald-600">{t('einstellungen:allgemein.gespeichert')}</span>}
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
  status: 'keine' | 'vorhanden' | 'entfernt' // i18n-ok: API-Wert
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
const BEISPIEL_ARTEN: string[] = [
  'stellen', 'firmen', 'bewerbungen', 'mails', 'gespraeche', 'kontakte', 'netzwerk', 'skills', 'werdegang', 'dateien',
]

// „5 Stellen, 6 Firmen, …“ — nur Arten mit Anzahl > 0; `nur` schränkt auf einzelne Arten ein.
function beispielZaehlung(zahlen: Record<string, number>, nur?: string[]): string {
  return BEISPIEL_ARTEN
    .filter((art) => (zahlen[art] ?? 0) > 0 && (!nur || nur.includes(art)))
    .map((art) => t(`einstellungen:beispieldaten.art.${art}`, { count: zahlen[art] }))
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
      setFehler(e?.message || t('einstellungen:beispieldaten.entfernen_fehlgeschlagen'))
    } finally {
      setBusy(false)
    }
  }

  if (!info || info.status === 'keine') return null // i18n-ok: API-Wert

  if (info.status === 'entfernt') {
    // Direkt nach dem Entfernen: Ergebnis mit Sicherung. Nach einem Neuladen nur noch die kleine Zeile.
    if (!ergebnis) {
      return (
        <p className="px-1 text-xs text-slate-400">
          {t('einstellungen:beispieldaten.entfernt_am', { datum: datum((info.entfernt_am ?? '').slice(0, 10)) })}
        </p>
      )
    }
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-1 text-sm font-semibold text-brand-navy">{t('einstellungen:beispieldaten.titel')}</div>
        <p className="text-sm text-emerald-700">{t('einstellungen:beispieldaten.entfernt_ergebnis', { zaehlung: beispielZaehlung(ergebnis.entfernt) })}</p>
        <p className="mt-1 text-xs text-slate-500">
          <Trans i18nKey="einstellungen:beispieldaten.vorher_gesichert" values={{ pfad: ergebnis.sicherung }} components={{ code: <code className="rounded bg-slate-100 px-1" /> }} />
        </p>
        {ergebnis.behalten.length > 0 && (
          <p className="mt-1 text-xs text-slate-500">
            {t('einstellungen:beispieldaten.nicht_entfernt')}{' '}
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
      <div className="mb-1 text-sm font-semibold text-brand-navy">{t('einstellungen:beispieldaten.titel')}</div>
      <p className="mb-3 text-sm text-slate-700">
        {t('einstellungen:beispieldaten.beschreibung', {
          name: info.name ?? 'Birne Helene',
          zaehlung: beispielZaehlung(info.anzahl, ['stellen', 'firmen', 'bewerbungen', 'mails', 'gespraeche']),
        })}
      </p>
      {frage ? (
        <div className="space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-2.5 text-sm text-amber-900">
          <p><Trans i18nKey="einstellungen:beispieldaten.frage" components={{ b: <b /> }} /></p>
          <div className="flex gap-2">
            <button onClick={entfernen} disabled={busy}
              className="rounded-md bg-amber-600 px-2.5 py-1 text-xs font-medium text-white hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50">
              {busy ? t('einstellungen:beispieldaten.entfernt_laeuft') : t('einstellungen:beispieldaten.ja_entfernen')}
            </button>
            <button onClick={() => setFrage(false)} disabled={busy}
              className="rounded-md border border-amber-300 px-2.5 py-1 text-xs hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50">
              {t('einstellungen:allgemein.abbrechen')}
            </button>
          </div>
        </div>
      ) : (
        <button onClick={() => { setFehler(null); setFrage(true) }}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover">
          {t('einstellungen:beispieldaten.entfernen')}
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

  if (loading || !data) return <div className="text-slate-400">{t('einstellungen:allgemein.lade')}</div>

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">{t('einstellungen:seite.titel')}</h1>
        <p className="text-sm text-slate-500">
          <Trans i18nKey="einstellungen:seite.beschreibung" components={{ code: <code className="rounded bg-slate-100 px-1" /> }} />
        </p>
      </div>
      <SpracheKarte />
      <BeispieldatenKarte />
      <MailKontoKarte />
      <KiKarte ki={data.ki_anbieter} optionen={data.ki_anbieter_optionen} onSaved={load} />
      <div className="grid gap-4 md:grid-cols-2">
        <SuchbereichKarte suchbereich={data.suchbereich} minMitarbeiter={data.min_mitarbeiter}
          umkreisLabel={data.umkreis_label} onSaved={load} />
        <ModelleKarte key={data.ki_anbieter} modelle={data.modelle} modellOptionen={data.modell_optionen} modellStandard={data.modell_standard} onSaved={load} />
      </div>
      <div>
        <div className="mb-2 text-xs text-slate-500">{t('einstellungen:seite.reihenfolge')}</div>
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
    } catch (e: any) { setErr(e?.message || t('einstellungen:allgemein.speichern_fehlgeschlagen')) }
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
      setTestErgebnis({ ok: false, text: e?.message || t('einstellungen:allgemein.test_fehlgeschlagen') })
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
      setErmittelnErr(e?.message || t('einstellungen:coach.serverpfad_fehlgeschlagen'))
    } finally { setErmitteln(false) }
  }

  if (loading) {
    return <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-400 shadow-sm">{t('einstellungen:coach.lade')}</div>
  }

  // Der Aktualisieren-Button setzt einen echten Upload-Lauf in Gang, der die GESPEICHERTE
  // Konfiguration liest — deshalb gegen `original` prüfen (letzter bekannter Server-Stand), nicht
  // gegen `f` (kann ungespeicherte Änderungen enthalten, die der Lauf so noch nicht sehen würde).
  const bereit = original.aktiv && coachVollstaendig(original)

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 text-sm font-semibold text-brand-navy">{t('einstellungen:coach.titel')}</div>
      <p className="mb-3 text-xs text-slate-500">
        {f.site_url ? (
          <Trans i18nKey="einstellungen:coach.beschreibung_mit_adresse" values={{ adresse: f.site_url.replace(/^https:\/\//, '') }}
            components={{ a: <a href={f.site_url} target="_blank" rel="noreferrer" className="font-semibold text-brand-cyan" /> }} />
        ) : t('einstellungen:coach.beschreibung')}
      </p>

      <label className="flex items-center gap-2 text-sm text-slate-700">
        <input type="checkbox" checked={f.aktiv} onChange={(e) => setF({ ...f, aktiv: e.target.checked })} />
        {t('einstellungen:coach.aktiv')}
      </label>

      <div className="mt-3 border-t border-slate-100 pt-3">
        <label className="text-xs text-slate-500">
          {t('einstellungen:coach.adresse')}
          <input className={`${INPUT} mt-0.5 w-full`} value={f.site_url}
            onChange={(e) => setF({ ...f, site_url: e.target.value })} placeholder={t('einstellungen:coach.adresse_beispiel')} />
        </label>
      </div>

      <div className="mt-3 border-t border-slate-100 pt-3">
        <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">{t('einstellungen:coach.upload_ziel')}</div>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="text-xs text-slate-500">
            {t('einstellungen:allgemein.host')}
            <input className={`${INPUT} mt-0.5 w-full`} value={f.sftp_host}
              onChange={(e) => setF({ ...f, sftp_host: e.target.value })} placeholder="access-xyz.webspace-host.com" /* i18n-ok: Beispielhost */ />
          </label>
          <label className="text-xs text-slate-500">
            {t('einstellungen:allgemein.benutzer')}
            <input className={`${INPUT} mt-0.5 w-full`} value={f.sftp_user}
              onChange={(e) => setF({ ...f, sftp_user: e.target.value })} />
          </label>
          <label className="text-xs text-slate-500">
            {t('einstellungen:allgemein.passwort')}
            <input type="password" className={`${INPUT} mt-0.5 w-full`} value={sftpPasswort}
              onChange={(e) => setSftpPasswort(e.target.value)}
              placeholder={f.sftp_password_set ? t('einstellungen:allgemein.passwort_gespeichert') : t('einstellungen:coach.sftp_passwort_platzhalter')} />
            {f.sftp_password_set && (
              <span className="mt-0.5 block text-[11px] text-slate-400">{t('einstellungen:allgemein.passwort_behalten')}</span>
            )}
          </label>
          <label className="text-xs text-slate-500">
            {t('einstellungen:coach.zielverzeichnis')}
            <input className={`${INPUT} mt-0.5 w-full`} value={f.sftp_dir}
              onChange={(e) => setF({ ...f, sftp_dir: e.target.value })} placeholder="/coach" /* i18n-ok: Beispielpfad */ />
          </label>
        </div>
      </div>

      <div className="mt-3 border-t border-slate-100 pt-3">
        <label className="text-xs text-slate-500">
          {t('einstellungen:coach.serverpfad')}
          <div className="mt-0.5 flex gap-2">
            <input className={`${INPUT} flex-1`} value={f.authuserfile}
              onChange={(e) => setF({ ...f, authuserfile: e.target.value })} placeholder={t('einstellungen:coach.serverpfad_beispiel')} />
            <button onClick={serverpfadErmitteln} disabled={ermitteln}
              className="shrink-0 rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40">
              {ermitteln ? t('einstellungen:coach.ermittelt') : t('einstellungen:coach.ermitteln')}
            </button>
          </div>
        </label>
        {ermittelnErr && <div className="mt-1 text-xs text-rose-600">{ermittelnErr}</div>}
      </div>

      <div className="mt-3 border-t border-slate-100 pt-3">
        <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{t('einstellungen:coach.login')}</div>
        <p className="mb-1.5 mt-0.5 text-[11px] text-slate-400">{t('einstellungen:coach.login_hinweis')}</p>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="text-xs text-slate-500">
            {t('einstellungen:allgemein.benutzer')}
            <input className={`${INPUT} mt-0.5 w-full`} value={f.coach_user}
              onChange={(e) => setF({ ...f, coach_user: e.target.value })} />
          </label>
          <label className="text-xs text-slate-500">
            {t('einstellungen:allgemein.passwort')}
            <input type="password" className={`${INPUT} mt-0.5 w-full`} value={coachPasswort}
              onChange={(e) => setCoachPasswort(e.target.value)}
              placeholder={f.coach_password_set ? t('einstellungen:allgemein.passwort_gespeichert') : t('einstellungen:coach.coach_passwort_platzhalter')} />
            {f.coach_password_set && (
              <span className="mt-0.5 block text-[11px] text-slate-400">{t('einstellungen:allgemein.passwort_behalten')}</span>
            )}
          </label>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
        <button onClick={testen} disabled={testing || saving}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40">
          {testing ? t('einstellungen:allgemein.testet') : t('einstellungen:allgemein.verbindung_testen')}
        </button>
        <button onClick={save} disabled={saving || testing || !dirty}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? t('einstellungen:allgemein.speichern_laeuft') : t('einstellungen:allgemein.speichern')}
        </button>
        {saved && <span className="text-sm text-emerald-600">{t('einstellungen:allgemein.gespeichert')}</span>}
        {err && <span className="text-sm text-rose-600">{err}</span>}
      </div>
      {testErgebnis && (
        <div className={`mt-2 text-sm ${testErgebnis.ok ? 'text-emerald-600' : 'text-rose-600'}`}>
          {testErgebnis.ok ? '✓ ' : '✗ '}{testErgebnis.text}
        </div>
      )}

      <div className="mt-3 border-t border-slate-100 pt-3">
        {bereit ? (
          <AgentTaskButton kind="coach-site" label={t('einstellungen:coach.jetzt_aktualisieren')} />
        ) : (
          <div className="text-xs text-slate-400">{t('einstellungen:coach.erst_aktivieren')}</div>
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
  return m >= 10 ? `${Math.round(m)} MB` : `${zahl(m, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} MB`
}

// Datum + Uhrzeit aus dem ISO-Zeitpunkt mit Offset (V4: `.astimezone().isoformat()`) — anders als
// `datum()` (reines Datum ohne Uhrzeit) hier über `toLocaleString`, Muster Inbox.tsx::fmt.
function fmtZeitpunkt(iso: string): string {
  try {
    return datumZeit(iso, { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
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
    } catch (e: any) { setSaveErr(e?.message || t('einstellungen:allgemein.speichern_fehlgeschlagen')) }
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
      setSichernErr(e?.message || t('einstellungen:sicherung.fehlgeschlagen'))
    } finally {
      setSichernBusy(false)
    }
  }

  if (loading) {
    return <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-400 shadow-sm">{t('einstellungen:sicherung.lade')}</div>
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 text-sm font-semibold text-brand-navy">{t('einstellungen:sicherung.titel')}</div>
      <p className="mb-3 text-xs text-slate-500">
        {t('einstellungen:sicherung.beschreibung')}
      </p>

      {ladeFehler && <div className="mb-3 text-sm text-rose-600">{t('einstellungen:sicherung.status_fehler')}</div>}

      {!ladeFehler && status && (
        <>
          <div className="space-y-1 text-sm text-slate-700">
            <div>
              {status.letzte
                ? t('einstellungen:sicherung.letzte', { zeitpunkt: fmtZeitpunkt(status.letzte.zeitpunkt), groesse: mb(status.letzte.groesse) })
                : t('einstellungen:sicherung.noch_keine')}
            </div>
            <div className="text-xs text-slate-500">
              {t('einstellungen:sicherung.anzahl', { count: status.anzahl, groesse: mb(status.gesamtgroesse) })}
            </div>
            {status.weitere.anzahl > 0 && (
              <div className="text-xs text-slate-500">
                {t('einstellungen:sicherung.weitere', { count: status.weitere.anzahl, groesse: mb(status.weitere.gesamtgroesse) })}
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
            <div className="mt-2 text-sm text-slate-500">{t('einstellungen:sicherung.ausgeschaltet')}</div>
          )}

          <div className="mt-3 space-y-2 border-t border-slate-100 pt-3">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={f.aktiv} onChange={(e) => setF({ ...f, aktiv: e.target.checked })} />
              {t('einstellungen:sicherung.taeglich_sichern')}
            </label>
            <div className="flex flex-wrap items-center gap-1.5 text-sm text-slate-700">
              <span>{t('einstellungen:sicherung.aufbewahren')}</span>
              <input type="number" className={`${INPUT} w-16`} value={f.taeglich}
                onChange={(e) => setF({ ...f, taeglich: Number(e.target.value) || 0 })} />
              <span>{t('einstellungen:sicherung.taegliche')}</span>
              <input type="number" className={`${INPUT} w-16`} value={f.woechentlich}
                onChange={(e) => setF({ ...f, woechentlich: Number(e.target.value) || 0 })} />
              <span>{t('einstellungen:sicherung.woechentliche')}</span>
              <input type="number" className={`${INPUT} w-16`} value={f.monatlich}
                onChange={(e) => setF({ ...f, monatlich: Number(e.target.value) || 0 })} />
              <span>{t('einstellungen:sicherung.monatliche')}</span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button onClick={save} disabled={saving || !dirty}
                className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
                {saving ? t('einstellungen:allgemein.speichern_laeuft') : t('einstellungen:allgemein.speichern')}
              </button>
              {saved && <span className="text-sm text-emerald-600">{t('einstellungen:allgemein.gespeichert')}</span>}
              {saveErr && <span className="text-sm text-rose-600">{saveErr}</span>}
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
            <button onClick={jetztSichern} disabled={sichernBusy}
              className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
              {sichernBusy ? t('einstellungen:sicherung.sichere') : t('einstellungen:sicherung.jetzt_sichern')}
            </button>
            {sichernErgebnis && <span className="text-sm text-emerald-600">{t('einstellungen:sicherung.gesichert', { datei: sichernErgebnis })}</span>}
            {sichernErr && <span className="text-sm text-rose-600">{sichernErr}</span>}
          </div>

          <div className="mt-3 border-t border-slate-100 pt-3 text-xs text-slate-500">
            {t('einstellungen:sicherung.ordner')} <code className="break-all rounded bg-slate-100 px-1">{status.ordner}</code>
          </div>
        </>
      )}

      <p className="mt-3 border-t border-slate-100 pt-3 text-xs text-slate-500">
        {t('einstellungen:sicherung.zurueckspielen')}
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
    return t('common:layout.entwicklungsstand', { stand: v.entwicklungsstand || t('einstellungen:version.unbekannt') })
  }
  if (!v.version || v.version === '0.0.0') return t('einstellungen:version.keine_freigabe')
  return v.datum ? t('einstellungen:version.mit_stand', { version: v.version, datum: datum(v.datum) }) : t('common:layout.version', { version: v.version })
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
        <li><Trans i18nKey="einstellungen:version.schritt_beenden" values={{ datei: stop }} components={{ code: <code className="rounded bg-slate-100 px-1" /> }} /></li>
        <li><Trans i18nKey="einstellungen:version.schritt_update" values={{ ordner: installationsordner, datei: update }} components={{ code: <code className="rounded bg-slate-100 px-1" /> }} /></li>
        <li>{t('einstellungen:version.schritt_starten')}</li>
      </ol>
      <p className="mt-1.5 text-xs text-slate-500">
        <Trans i18nKey="einstellungen:version.ohne_internet" components={{ code: <code className="rounded bg-slate-100 px-1" /> }} shouldUnescape />
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
  if (e.neuer === null || !e.neueste) return <div className="text-sm text-rose-600">{t('einstellungen:update.ungueltig')}</div>
  if (!e.neuer) {
    return <div className="text-sm text-emerald-600">{t('einstellungen:update.aktuell', { version: e.installiert ?? e.neueste })}</div>
  }
  return (
    <div className="space-y-1.5 text-sm text-slate-700">
      <div className="font-medium text-brand-navy">
        {e.veroeffentlicht
          ? t('einstellungen:update.erschienen_datum', { version: e.neueste, datum: datum(e.veroeffentlicht) })
          : t('einstellungen:update.erschienen', { version: e.neueste })}
      </div>
      {e.aenderungen && aenderungenListe(e.aenderungen)}
      {e.seite && e.seite.startsWith('https://') && (
        <a href={e.seite} target="_blank" rel="noopener noreferrer"
          className="inline-block font-semibold text-brand-cyan hover:underline">
          {t('einstellungen:update.github_ansehen')}
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
      setFehler(t('einstellungen:update.nicht_ausfuehrbar'))
    } finally {
      setSucht(false)
    }
  }

  return (
    <div className="mt-3 border-t border-slate-100 pt-3">
      <button onClick={suchen} disabled={sucht}
        className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40">
        {sucht ? t('einstellungen:update.sucht') : t('einstellungen:update.suchen')}
      </button>
      <p className="mt-1.5 text-xs text-slate-500">
        {t('einstellungen:update.hinweis')}
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
    return <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-400 shadow-sm">{t('einstellungen:version.lade')}</div>
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-1 text-sm font-semibold text-brand-navy">{t('einstellungen:version.titel')}</div>

      {ladeFehler || !info ? (
        <div className="text-sm text-slate-400">{t('einstellungen:version.fehler')}</div>
      ) : (
        <>
          <p className="text-sm text-slate-700">
            {versionHauptzeile(info)}
            {info.installation === 'git' && info.commit ? ` · ${t('einstellungen:version.commit', { commit: info.commit })}` : ''}
          </p>
          {info.letztes_update && (
            <p className="mt-1 text-xs text-slate-500">
              {t('einstellungen:version.zuletzt', {
                datum: datum(info.letztes_update.zeitpunkt.slice(0, 10)),
                von: info.letztes_update.von ?? t('einstellungen:version.unbekannt'),
                nach: info.letztes_update.nach,
              })}
            </p>
          )}
          {info.aenderungen && (
            <div className="mt-3 border-t border-slate-100 pt-3">
              <div className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">
                {/* Git-Installation: der Abschnitt „Unveröffentlicht“ (V5), also noch nicht freigegeben */}
                {info.installation === 'git' ? t('einstellungen:version.seit_freigabe') : t('einstellungen:version.neu_in_version')}
              </div>
              <div className="text-sm text-slate-700">{aenderungenListe(info.aenderungen)}</div>
            </div>
          )}
          <UpdateSuche />
          {info.installation === 'git' ? (
            <div className="mt-3 border-t border-slate-100 pt-3 text-sm text-slate-700">
              {t('einstellungen:version.entwicklung')}
            </div>
          ) : (
            <div className="mt-3 border-t border-slate-100 pt-3 text-sm text-slate-700">
              <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">{t('einstellungen:version.update_einspielen')}</div>
              {updateAnleitung(info.betriebssystem, info.installationsordner)}
              <p className="mt-1.5 text-xs text-slate-500">{t('einstellungen:version.vor_einspielen')}</p>
            </div>
          )}
        </>
      )}
    </div>
  )
}
