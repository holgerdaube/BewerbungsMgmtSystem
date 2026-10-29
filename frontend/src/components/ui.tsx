import React, { useState } from 'react'
import { Link } from 'react-router-dom'

// P2-72 (Design aus einer Quelle): Schrift auf den Zustandsflächen (Status, Score, Situation, Tier,
// Szenario). Der Wert ist geprüft (18.8, Kontrast auf jeder dieser Flächen) und trägt Bedeutung, nicht
// Marke: Er hängt an KEINER Markenrolle und ändert sich mit einem anderen Design nicht. Vorher stand er
// 29-mal als Literal in diesen Tabellen.
export const TEXT_AUF_ZUSTAND = '#0B1F3A'

// Dashboard-Farbmodell V2 (Daube.Tech Style Guide v5.0, Abschnitt 18) — normative Token,
// wörtlich übernommen (18.10 maschinenlesbare Spezifikation). Nicht dekorativ: gleiche
// Bedeutung = gleiche Farbe in jedem Dashboard/jeder Statusanzeige (18.1).
export const SCORE_COLORS: Record<number, string> = {
  5: '#18A957', // score.5 — sehr gut
  4: '#84C83D', // score.4 — gut
  3: '#E8B319', // score.3 — mittel
  2: '#F07C24', // score.2 — schwach
  1: '#D9364F', // score.1 — sehr schwach
}
const SCORE_NONE = '#94A3B8' // score.none — nicht bewertet
// Textfarbe je Score, WCAG-kontrastgeprüft (18.8) — NUR score.1 (Rot) verträgt Weiß
// (4,58:1); score.2-5 sind Orange/Gelb/Grün-Töne und brauchen Navy-Text (5,4-8,6:1),
// sonst versteckt sich die Zahl fast unsichtbar auf hellem Grün/Gelb.
const SCORE_TEXT: Record<number, string> = { 5: TEXT_AUF_ZUSTAND, 4: TEXT_AUF_ZUSTAND, 3: TEXT_AUF_ZUSTAND, 2: TEXT_AUF_ZUSTAND, 1: '#ffffff' }

// Phase 51 — geteilter Export (vorher lokal in Dashboard.tsx dupliziert je Plan-Karte gebraucht).
// Situationsmodell (18.5): jede Situation bekommt eine EIGENE Farbe — löst die alte
// "Plan-A-Kern grün"-Gruppierung ab (BUILD/CARVE-OUT/POST-MERGER waren zuvor identisch grün).
export const SITU_COLORS: Record<string, string> = {
  BUILD: '#00B4D8', 'CARVE-OUT': '#0EA5A4', 'POST-MERGER': '#7C4DFF', PE: '#5B61E6',
  'SCALE-UP': '#18A957', RESTRUCT: '#E4A11B', RUN: '#64748B', UNKLAR: '#B7C2D0',
}
// Textfarbe je Situationsfarbe, WCAG-kontrastgeprüft (18.8: keine weiße Schrift auf
// Gelb/Orange/Cyan/hellem Grün) — nur für Badges/Pillen mit Text auf der Farbfläche nötig
// (die Dashboard-Balken selbst tragen keinen Text auf der Fläche, s. BarList).
export const SITU_TEXT: Record<string, string> = {
  BUILD: TEXT_AUF_ZUSTAND, 'CARVE-OUT': TEXT_AUF_ZUSTAND, 'POST-MERGER': '#ffffff', PE: '#ffffff',
  'SCALE-UP': TEXT_AUF_ZUSTAND, RESTRUCT: TEXT_AUF_ZUSTAND, RUN: '#ffffff', UNKLAR: TEXT_AUF_ZUSTAND,
}

export function ScoreBadge({ score }: { score: number | null }) {
  if (!score) {
    return (
      <span
        className="inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold"
        style={{ backgroundColor: SCORE_NONE, color: TEXT_AUF_ZUSTAND }}
        title="Nicht bewertet"
      >–</span>
    )
  }
  return (
    <span
      className="inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold"
      style={{ backgroundColor: SCORE_COLORS[score] || SCORE_NONE, color: SCORE_TEXT[score] || TEXT_AUF_ZUSTAND }}
      title={`Zielstellen-Fit ${score}/5`}
    >
      {score}
    </span>
  )
}

// Kanonische Farb-Map — für den Status-Verteilungsbalken auf /jobs, den Pipeline-Kanban
// (Pipeline.tsx::COL_ACCENT leitet sich hieraus ab), den Dashboard-Funnel (Dashboard.tsx)
// UND die Status-Pille (StatusBadge, s. u.) — EINE Farbe je Status, überall im Produkt.
// Ab Style Guide v5.0 Abschnitt 18.3/18.7: semantische Statusfarben statt Cyan/Navy-Leiter
// (löst die Phase-43/Style_Guide_v4-Stufung ab, die vor dem Dashboard-Farbmodell V2 galt).
// „Beirat abgelehnt" → status.rejected_internal (intern gestoppt, vor der Bewerbung).
// „Nicht verfügbar" → ui.state.unknown (kein bewertetes Ergebnis, Stelle nur nicht mehr da).
// „Keine Rückmeldung" → kein Token in §18.10 (geprüft, Phase 85); eigener Wert #7A5C5C,
// Kontrast 5,98:1 gg. Weiß (WCAG AA). Passives negatives Ergebnis (Ghosting) — gedämpftes Rot,
// unterscheidbar von Absage/Kein Match/Nicht verfügbar. IDENTISCH zu coach_export.py.
// Textfarbe je Hintergrund WCAG-kontrastgeprüft (18.8: keine weiße Schrift auf
// Gelb/Orange/Cyan/hellem Grün).
export const STATUS_FARBEN: Record<string, { bg: string; text: string }> = {
  Neu: { bg: '#94A3B8', text: TEXT_AUF_ZUSTAND },                // status.new
  Prüfen: { bg: '#5B61E6', text: '#ffffff' },                    // status.review
  Beworben: { bg: '#00B4D8', text: TEXT_AUF_ZUSTAND },           // status.active
  Interview: { bg: '#7C4DFF', text: '#ffffff' },                 // status.advanced
  Angebot: { bg: '#18A957', text: TEXT_AUF_ZUSTAND },            // status.positive
  Absage: { bg: '#E5484D', text: '#ffffff' },                    // status.negative
  'Keine Rückmeldung': { bg: '#7A5C5C', text: '#ffffff' },       // kein §18.10-Token, s.o.
  'Kein Match': { bg: '#64748B', text: '#ffffff' },              // status.no_match
  'Beirat abgelehnt': { bg: '#D97706', text: TEXT_AUF_ZUSTAND }, // status.rejected_internal
  'Nicht verfügbar': { bg: '#A8B4C4', text: TEXT_AUF_ZUSTAND },  // ui.state.unknown
  Geparkt: { bg: '#E4A11B', text: TEXT_AUF_ZUSTAND },            // status.parked
}
export const STATUS_FARBE_UNBEKANNT = { bg: '#94A3B8', text: TEXT_AUF_ZUSTAND } // Fallback für nicht gelistete Status-Strings

// Vorher eigene, pastellene Tailwind-Palette (STATUS_STYLE) — hatte "Interview"/"Angebot"
// gar nicht erst gelistet (fielen auf ein generisches Grau). Jetzt dieselben Tokens wie
// Balken/Kanban/Funnel (18.1: „gleiche Bedeutung erhält immer die gleiche Farbe").
// „Nicht verfügbar" behält zusätzlich den Durchstrich — Farbe ist nie der einzige
// Informationsträger (18.1), der Durchstrich markiert zusätzlich „nicht mehr da".
export function StatusBadge({ status }: { status: string | null }) {
  const s = status || 'Neu'
  const f = STATUS_FARBEN[s] || STATUS_FARBE_UNBEKANNT
  return (
    <span
      className={`inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${s === 'Nicht verfügbar' ? 'line-through' : ''}`}
      style={{ backgroundColor: f.bg, color: f.text }}
    >
      {s}
    </span>
  )
}

/** Vier-Augen-Badge (Phase 14): aus dem verify_note-Präfix. Alt-Einträge ohne
 *  verified_at bekommen bewusst KEIN Badge. Der volle Befund steht im title-Tooltip. */
export function VerifyBadge({ verifyNote, verifiedAt }: { verifyNote?: string | null; verifiedAt?: string | null }) {
  if (!verifiedAt) return null
  const status = (verifyNote || '').split(':')[0].trim()
  let cls = '', label = ''
  if (status === 'BESTÄTIGT' || status === 'KORRIGIERT') { cls = 'bg-emerald-100 text-emerald-800'; label = '✓ geprüft' }
  else if (status === 'QUELLE_VERTRAUT') { cls = 'bg-amber-100 text-amber-800'; label = '~ Quelle vertraut' }
  else return null
  return (
    <span title={verifyNote || undefined} className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {label}
    </span>
  )
}

/** Phase 44: Repost-Verdacht aus verify_note parsen (Muster identisch zur bestehenden
 *  KONFLIKT-Anzeige, s. JobDetail.tsx) — festes Schlüsselwort DUBLETTE?, vom Ingest-Hook
 *  gesetzt (`pipeline/ingest.py`): " | DUBLETTE? Job <id> „<Titel>" — Text-Ähnlichkeit <XX> %
 *  (geprüft <ISO>)". Exportiert, weil sowohl die Badge hier als auch die Review-Quick-Actions
 *  (Ziel-Job-Id für „Als Dublette parken") denselben Parse brauchen — ein Regex, zwei Nutzer. */
export function parseDubletteVerdacht(verifyNote?: string | null): { jobId: number; prozent: number } | null {
  if (!verifyNote) return null
  const m = verifyNote.match(/DUBLETTE\?\s*Job\s*(\d+)[^—]*—\s*Text-Ähnlichkeit\s*(\d+)\s*%/)
  return m ? { jobId: Number(m[1]), prozent: Number(m[2]) } : null
}

export function DubletteBadge({ verifyNote }: { verifyNote?: string | null }) {
  const treffer = parseDubletteVerdacht(verifyNote)
  if (!treffer) return null
  return (
    <Link to={`/jobs/${treffer.jobId}`}
      title={`Text-Ähnlichkeitsverdacht ${treffer.prozent} % — vermuteter Repost, s. Notizen & Verlauf`}
      className="inline-block whitespace-nowrap rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 hover:bg-amber-200">
      Dublette? → Job {treffer.jobId}
    </Link>
  )
}

/** P2-36: Neuausschreibung einer früher aussortierten Stelle aus verify_note parsen —
 *  fester Anhang vom Ingest (`pipeline/ingest.py`, Format: tasks/spec_p2-36 §2.3):
 *  " | NEUAUSSCHREIBUNG? Job <id> „<Titel>“ — <Status>, zuerst gefunden <ISO>". Anders als
 *  DUBLETTE? ist das hier kein Verdacht, sondern eine Tatsache (URL war neu, Stelle stand
 *  schon einmal im Tracker) — daher eigener Badge statt Wiederverwendung von DubletteBadge.
 *  Der Regex hält sich an die Anführungszeichen „…“, nicht an den ersten Gedankenstrich: ein
 *  Titel wie „Director — Consulting“ schöbe sonst ein Stück Titel in den Status. */
export function parseNeuausschreibung(verifyNote?: string | null): { jobId: number; status: string } | null {
  if (!verifyNote) return null
  const m = verifyNote.match(/NEUAUSSCHREIBUNG\?\s*Job\s*(\d+)\s*„[^“]*“\s*—\s*([^,|]+)/)
  return m ? { jobId: Number(m[1]), status: m[2].trim() } : null
}

export function NeuausschreibungBadge({ verifyNote }: { verifyNote?: string | null }) {
  const treffer = parseNeuausschreibung(verifyNote)
  if (!treffer) return null
  return (
    <Link to={`/jobs/${treffer.jobId}`}
      title={`Diese Stelle war schon im Tracker (${treffer.status}). Neue Anzeige mit neuem Link — bitte neu entscheiden.`}
      className="inline-block whitespace-nowrap rounded-full bg-sky-100 px-2 py-0.5 text-xs font-medium text-sky-800 hover:bg-sky-200">
      Neuausschreibung → Job {treffer.jobId}
    </Link>
  )
}

export function Stat({ label, value, sub, accent, to, danger }: {
  label: string; value: React.ReactNode; sub?: string; accent?: boolean; to?: string; danger?: boolean
}) {
  const border = danger ? 'border-rose-300' : accent ? 'border-brand-cyan/40' : 'border-slate-200'
  const valueColor = danger ? 'text-rose-600' : accent ? 'text-brand-cyan' : 'text-brand-navy'
  const inner = (
    <>
      <div className="flex items-center justify-between">
        <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
        {to && <span className="text-slate-300 transition group-hover:text-brand-cyan">→</span>}
      </div>
      <div className={`mt-1 text-3xl font-bold ${valueColor}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-400">{sub}</div>}
    </>
  )
  const base = `block rounded-xl border p-4 shadow-sm bg-white ${border}`
  if (to) {
    return (
      <Link to={to} className={`group ${base} transition hover:-translate-y-0.5 hover:shadow-md hover:border-brand-cyan/60`}>
        {inner}
      </Link>
    )
  }
  return <div className={base}>{inner}</div>
}

export function BarList({ title, data, colorFn, linkFn, maxValue }: {
  title: string; data: Record<string, number>; colorFn?: (k: string) => string; linkFn?: (k: string) => string
  maxValue?: number
}) {
  const entries = Object.entries(data)
  const max = maxValue ?? Math.max(1, ...entries.map(([, v]) => v))
  const row = (k: string, v: number) => (
    <>
      <div className="w-40 shrink-0 truncate text-slate-600" title={k}>{k}</div>
      <div className="relative h-5 flex-1 overflow-hidden rounded" style={{ backgroundColor: 'var(--spur-farbe)' /* ui.track.bar = Rolle spur */ }}>
        <div
          className="absolute inset-y-0 left-0 rounded"
          style={{ width: `${(v / max) * 100}%`, backgroundColor: colorFn ? colorFn(k) : 'var(--aktion-farbe)' }}
        />
      </div>
      <div className="w-8 shrink-0 text-right font-medium tabular-nums text-slate-700">{v}</div>
    </>
  )
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-brand-navy">
        {title}{linkFn && <span className="font-normal text-slate-400"> · klickbar</span>}
      </h3>
      <div className="space-y-2">
        {entries.length === 0 ? (
          <div className="text-xs text-slate-400">keine Stellen</div>
        ) : entries.map(([k, v]) =>
          linkFn ? (
            <Link key={k} to={linkFn(k)} className="flex items-center gap-2 rounded text-sm transition hover:bg-slate-50">
              {row(k, v)}
            </Link>
          ) : (
            <div key={k} className="flex items-center gap-2 text-sm">{row(k, v)}</div>
          )
        )}
      </div>
    </div>
  )
}

/** Kompakter Auslöser-Kopierer für Tabellenzeilen (Claude-in-the-Loop, kleines Pendant zu CopyTrigger). */
export function CopyChip({ phrase, label = '🚀 Initiativ' }: { phrase: string; label?: string }) {
  const [ok, setOk] = useState(false)
  const copy = async (e: React.MouseEvent) => {
    e.stopPropagation()
    try { await navigator.clipboard.writeText(phrase) } catch { /* Hinweis trotzdem zeigen */ }
    setOk(true)
    setTimeout(() => setOk(false), 2500)
  }
  return (
    <button onClick={copy} title={`Kopiert „${phrase}" — in der Claude-Session einfügen & senden`}
      className={`whitespace-nowrap rounded-lg border px-2 py-1 text-xs font-medium transition ${
        ok ? 'border-emerald-300 bg-emerald-50 text-emerald-700' : 'border-brand-cyan/40 text-brand-navy hover:bg-brand-cyan/10'}`}>
      {ok ? '✓ kopiert' : label}
    </button>
  )
}

export function Section({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <h3 className="text-sm font-semibold text-brand-navy">{title}</h3>
        {right}
      </div>
      <div className="p-4">{children}</div>
    </div>
  )
}
