import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  api, type Dashboard as DashboardData, type GesamtprozessRow, type GesamtprozessFunnel,
} from '../api'
import { Stat, BarList, SITU_COLORS, STATUS_FARBEN, SCORE_COLORS } from '../components/ui'
import AgentTaskButton from '../components/AgentTaskButton'
import { isoTag } from '../zeit'
import { t } from '../i18n'
import { wert } from '../i18n/werte'
import { datum, zahl } from '../i18n/format'

// Anzeige für Werte aus dem Server, die keine Status sind (Kanal, Trichterstufe, Gesprächspartner, Portal).
// Der Wert bleibt der DB-Wert, nur die Anzeige wird übersetzt; Unbekanntes kommt unverändert zurück.
const anzeigeWert = (x: string): string => t(`dashboard:wert.${x}`, { defaultValue: x })

// Stand der Lost-Order-Analyse (P2-79, GET /api/absagen-analyse) — der Typ steht bewusst lokal hier
// (Muster BeispieldatenBanner): neuester Bericht mit Datum und Link, oder `datei: null`.
type AbsagenStand = { datei: string | null; datum?: string; url?: string }

// Balken mit übersetzter Beschriftung: Die Anzeige-Namen werden zu Schlüsseln, `db()` liefert den DB-Wert
// zurück (für Farbe und Link). Fällt eine Übersetzung mit einer anderen zusammen, bleibt der DB-Wert stehen.
function beschriftet(data: Record<string, number>, anzeige: (k: string) => string) {
  const neu: Record<string, number> = {}
  const zurueck: Record<string, string> = {}
  for (const [k, v] of Object.entries(data)) {
    const label = anzeige(k) in neu ? k : anzeige(k)
    neu[label] = v
    zurueck[label] = k
  }
  return { data: neu, db: (label: string): string => zurueck[label] ?? label }
}

// Heute + 7 Tage als ISO-Datum — Basis für den Dashboard-Button "Wiedervorlage +7 Tage"
// (Phase 69, Stufe B).
function plus7Tage(): string {
  const d = new Date()
  d.setDate(d.getDate() + 7)
  return isoTag(d)
}

/** Eine aufklappbare Drilldown-Liste der Karte "Keine Reaktion" (<details>-Muster laut Spec).
 *  Netzwerk-Zeilen bekommen zusätzlich den "Wiedervorlage +7 Tage"-Button (setzt
 *  outreach.next_action_datum -- das ist das "Wieder-Aufrollen" der Nirvana-Fälle). */
function KeineReaktionListe({ title, rows, busyId, onWiedervorlage }: {
  title: string; rows: GesamtprozessRow[]; busyId?: number | null
  onWiedervorlage?: (row: GesamtprozessRow) => void
}) {
  return (
    <details className="rounded-lg border border-slate-200">
      <summary className="cursor-pointer select-none px-3 py-2 text-sm font-medium text-brand-navy hover:bg-slate-50">
        {title} ({rows.length})
      </summary>
      <div className="divide-y divide-slate-100 border-t border-slate-100">
        {rows.length === 0 ? (
          <div className="px-3 py-2 text-xs text-slate-400">{t('dashboard:keine_reaktion.leer')}</div>
        ) : rows.map((r) => (
          <div key={`${r.kanal}-${r.id}`} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
            <div className="min-w-0">
              <Link to={r.kanal === 'Ausschreibung' ? `/jobs/${r.id}` : '/outreach'}
                    className="font-medium text-brand-navy hover:underline">
                {r.label || '–'}
              </Link>
              <span className="ml-2 text-xs text-slate-400">{anzeigeWert(r.kanal)}</span>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span className="whitespace-nowrap text-xs font-medium text-rose-600">{t('dashboard:keine_reaktion.tage', { count: r.tage })}</span>
              {r.kanal === 'Netzwerk' && onWiedervorlage && (
                <button onClick={() => onWiedervorlage(r)} disabled={busyId === r.id}
                        className="whitespace-nowrap rounded-lg border border-brand-cyan/40 px-2 py-1 text-xs font-medium text-brand-navy hover:bg-brand-cyan/10 disabled:cursor-not-allowed disabled:opacity-40">
                  {busyId === r.id ? t('dashboard:keine_reaktion.speichert') : t('dashboard:keine_reaktion.wiedervorlage')}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </details>
  )
}

// Trichter-Farbleiter (Phase 70) — dieselben fünf Töne wie im Excel-Blatt „Funnel"
// (export_excel.py::FUNNEL_FARBEN): Navy → Violett → Cyan → Amber → Grün. Kein neuer Hex-Wert:
// Violett/Cyan/Amber/Grün sind wörtlich STATUS_FARBEN-Einträge (Prüfen/Beworben/Geparkt/
// Angebot), Navy ist die bestehende brand-navy-Marke. Kontrastregel §18.8: Weiß nur auf
// Navy/Violett, sonst Navy-Text.
// P2-72: Die Farbe der ersten Stufe trägt Bedeutung (Trichterstufe 1), keine Markenrolle: Sie bleibt
// auch unter einem anderen Design stehen und steht deshalb als Literal hier (Positivliste des Wächters).
const FUNNEL_FARBEN: { bg: string; text: string }[] = [
  { bg: '#0B1F3A', text: '#ffffff' },                                       // 1 Gesichtet (brand-navy)
  { bg: STATUS_FARBEN['Prüfen'].bg, text: STATUS_FARBEN['Prüfen'].text },     // 2 Relevant // i18n-ok: DB-Wert
  { bg: STATUS_FARBEN['Beworben'].bg, text: STATUS_FARBEN['Beworben'].text }, // 3 Beworben
  { bg: STATUS_FARBEN['Geparkt'].bg, text: STATUS_FARBEN['Geparkt'].text },   // 4 Antworten
  { bg: STATUS_FARBEN['Angebot'].bg, text: STATUS_FARBEN['Angebot'].text },   // 5 Interviews
]
// Dieselbe Farbleiter dient den Split-Chips (Zeile 2) als Punktfarbe je Kategorie.
const FUNNEL_FARBLEITER = FUNNEL_FARBEN.map((f) => f.bg)

// Deutsches Prozent-Fließtextformat ("37,3 %", mit Leerzeichen vor %) — Pendant zu
// export_excel.py::_de_pct_prosa, dieselbe Konvention wie im Excel-Export.
function dePercentProsa(p: number | null): string {
  return p == null ? '—' : t('dashboard:prozent', { wert: zahl(p, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) })
}

// Je Nicht-Gewinner-Stufe (2-5) der feste Satzbaustein fürs Engstellen-Panel — wortgleich zu
// export_excel.py::FUNNEL_ENGSTELLEN_ZEILEN/_ENGSTELLEN_SATZ (Spec: „dieselbe Wortwahl").
const ENGSTELLEN_ZEILEN: {
  stufe: string
  key: 'screening' | 'bewerbungsquote' | 'antwortquote' | 'interview_konversion'
  text: (p: string, basis: number) => string
}[] = [
  { stufe: 'Relevant', key: 'screening', text: (p) => t('dashboard:engstellen.screening', { prozent: p }) },
  { stufe: 'Beworben', key: 'bewerbungsquote', text: (p) => t('dashboard:engstellen.bewerbungsquote', { prozent: p }) },
  { stufe: 'Antworten', key: 'antwortquote', text: (p, basis) => t('dashboard:engstellen.antwortquote', { prozent: p, count: basis }) },
  { stufe: 'Interviews', key: 'interview_konversion', text: (p) => t('dashboard:engstellen.interview_konversion', { prozent: p }) },
]

// Zeile 1 (2/3 Breite): der Trichter selbst — 5 horizontal zentrierte Balken, Breite proportional
// zur Anzahl mit Mindestbreite (CSS max(), damit "4" auch bei winzigem Anteil lesbar bleibt).
// Stufe 1 → /jobs?sort=found, Stufe 3 → laufende Bewerbungen; Stufe 2 bleibt unverlinkt, weil
// /api/jobs keinen Nicht-Terminal-Ausschlussfilter kennt (nur exakter status= oder eine
// statuses=-Positivliste, s. main.py::list_jobs) — kein passender Filter zum Verlinken.
function ProzessTrichter({ funnel }: { funnel: GesamtprozessFunnel }) {
  const { stufen } = funnel
  const maxAnzahl = Math.max(1, ...stufen.map((s) => s.anzahl))
  const LINKS: (string | null)[] = ['/jobs?sort=found', null, '/jobs?statuses=Beworben,Interview,Angebot&sort=found', null, null]

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm lg:col-span-2">
      <h3 className="mb-3 text-sm font-semibold text-brand-navy">
        {t('dashboard:trichter.titel')} <span className="font-normal text-slate-400">{t('dashboard:trichter.untertitel')}</span>
      </h3>
      <div className="space-y-2.5">
        {stufen.map((stufe, i) => {
          const farbe = FUNNEL_FARBEN[i]
          const pct = Math.max(0, (stufe.anzahl / maxAnzahl) * 100)
          const rechtsText = i === 0 ? t('dashboard:prozent', { wert: 100 }) : t('dashboard:trichter.der_vorstufe', { prozent: dePercentProsa(stufe.vs_vorstufe) })
          const inhalt = (
            <div className="flex items-center gap-3">
              <div className="w-32 shrink-0 text-sm text-slate-600">{i + 1} · {anzeigeWert(stufe.stufe)}</div>
              <div className="flex flex-1 justify-center">
                <div
                  className="flex items-center justify-center rounded-lg px-3 py-2 text-sm font-bold tabular-nums"
                  style={{ width: `max(64px, ${pct}%)`, backgroundColor: farbe.bg, color: farbe.text }}
                  title={stufe.kommentar}
                >
                  {stufe.anzahl}
                </div>
              </div>
              <div className="w-32 shrink-0 text-right text-xs text-slate-400">{rechtsText}</div>
            </div>
          )
          const link = LINKS[i]
          return link ? (
            <Link key={stufe.stufe} to={link} className="block rounded transition hover:bg-slate-50">{inhalt}</Link>
          ) : (
            <div key={stufe.stufe}>{inhalt}</div>
          )
        })}
      </div>
    </div>
  )
}

// Zeile 1 (1/3 Breite): „Engstellen im Funnel" — dieselbe Wortwahl wie das Excel-Blatt
// (_funnel_sheet), größter Verlust rot+fett, Ende-zu-Ende gedämpft grau.
function EngstellenPanel({ funnel }: { funnel: GesamtprozessFunnel }) {
  const { stufen, engstellen } = funnel
  const idxByStufe = new Map(stufen.map((s, i) => [s.stufe, i]))
  const gv = engstellen.groesster_verlust

  const zeilen = ENGSTELLEN_ZEILEN.map(({ stufe, key, text }) => {
    if (gv && gv.stufe === stufe) return { text: gv.text, rot: true }
    const p = engstellen[key]
    if (p == null) return { text: t('dashboard:engstellen.keine_daten', { stufe: anzeigeWert(stufe) }), rot: false }
    const idx = idxByStufe.get(stufe)!
    const basis = stufen[idx - 1].anzahl
    return { text: text(dePercentProsa(p), basis), rot: false }
  })
  const endeZuEnde = t('dashboard:engstellen.ende_zu_ende', {
    prozent: dePercentProsa(engstellen.ende_zu_ende),
    stellen: t('dashboard:engstellen.n_stellen', { count: stufen[0].anzahl }),
    interviews: t('dashboard:engstellen.n_interviews', { count: stufen[4].anzahl }),
  })

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-brand-navy">{t('dashboard:engstellen.titel')}</h3>
      <div className="space-y-2 text-sm">
        {zeilen.map((z, i) => (
          <div key={i} className={z.rot ? 'font-bold' : 'text-slate-600'} style={z.rot ? { color: '#E5484D' } : undefined}>
            {z.text}
          </div>
        ))}
        <div className="pt-1 text-xs italic text-slate-400">{endeZuEnde}</div>
      </div>
    </div>
  )
}

// Zeile 2: gedämpfte Chip-Reihe für die KPI-Splits — Punktfarbe je Kategorie aus der
// Funnel-Farbleiter (Reihenfolge = API-Reihenfolge der Splits). "davon_vor_Ort" ist kein
// eigener Split-Wert, sondern eine Zusatzinfo zu "Gespräche" -- eigener Chip mit 📍 statt Punkt.
function SplitChips({ splits }: { splits: Record<string, number> }) {
  const LABEL_UEBERSCHREIBUNG: Record<string, string> = { Positionsausschreibungen: 'Ausschreibungen' }
  const entries = Object.entries(splits).filter(([k]) => k !== 'davon_vor_Ort')
  const vorOrt = splits.davon_vor_Ort
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {entries.map(([label, value], i) => (
        <span key={label} className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: FUNNEL_FARBLEITER[i % FUNNEL_FARBLEITER.length] }} />
          {anzeigeWert(LABEL_UEBERSCHREIBUNG[label] ?? label)} {value}
        </span>
      ))}
      {vorOrt != null && (
        <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">
          {t('dashboard:chips.vor_ort', { anzahl: vorOrt })}
        </span>
      )}
    </div>
  )
}

// Gesamtprozess seit Beginn (Phase 69, Stufe B; Phase 70, Stufe B umgebaut) — Zeile 1: Trichter
// (2/3) + Engstellen-Panel (1/3) erzählen die Geschichte, Zeile 2: die vier Coach-KPI-Karten mit
// Chip-Splits. Drilldown "Keine Reaktion" + "Wiedervorlage +7 Tage" unverändert (Phase 69).
function GesamtprozessSection({ d, onReload }: { d: DashboardData; onReload: () => void }) {
  const gp = d.gesamtprozess
  const [busy, setBusy] = useState<number | null>(null)

  const wiedervorlage = async (row: GesamtprozessRow) => {
    setBusy(row.id)
    try {
      await api(`/outreach/${row.id}`, { method: 'PATCH', body: JSON.stringify({ next_action_datum: plus7Tage() }) })
      await onReload()
    } finally {
      setBusy(null)
    }
  }

  const ausschreibungRows = gp.keine_reaktion.rows.filter((r) => r.kanal === 'Ausschreibung')
  const netzwerkRows = gp.keine_reaktion.rows.filter((r) => r.kanal === 'Netzwerk')
  // P2-61: Karte 1 trug eine Fußnote „Netzwerk-Historie unvollständig, Backfill offen“, solange
  // der Netzwerk-Anteil 0 war. Der Nachtrag ist erledigt, und ohne übernommene Outreach-Zeilen
  // (jede neue Installation) bleibt der Anteil immer 0: Die Warnung stand dort dauerhaft und ließ
  // sich nicht beheben.

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-brand-navy">{t('dashboard:gesamtprozess.titel')}</h2>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <ProzessTrichter funnel={gp.funnel} />
        <EngstellenPanel funnel={gp.funnel} />
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{t('dashboard:gesamtprozess.bewerbungen')}</div>
          <div className="mt-1 text-3xl font-bold text-brand-navy">{gp.bewerbungen.wert}</div>
          <SplitChips splits={gp.bewerbungen.splits} />
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{t('dashboard:gesamtprozess.gespraeche')}</div>
          <div className="mt-1 text-3xl font-bold text-brand-navy">{gp.gespraeche.wert}</div>
          <SplitChips splits={gp.gespraeche.splits} />
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{t('dashboard:gesamtprozess.absagen')}</div>
          <div className="mt-1 text-3xl font-bold text-brand-navy">{gp.absagen.wert}</div>
          <SplitChips splits={gp.absagen.splits} />
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{t('dashboard:gesamtprozess.keine_reaktion')}</div>
          <div className="mt-1 text-3xl font-bold text-rose-600">{gp.keine_reaktion.wert}</div>
          <SplitChips splits={gp.keine_reaktion.splits} />
          <div className="mt-2 space-y-1.5">
            <KeineReaktionListe title={t('dashboard:gesamtprozess.ausschreibungen')} rows={ausschreibungRows} />
            <KeineReaktionListe title={t('dashboard:gesamtprozess.netzwerk')} rows={netzwerkRows} busyId={busy} onWiedervorlage={wiedervorlage} />
          </div>
        </div>
      </div>
    </div>
  )
}

// Funnel + „Nach Status" nutzen dieselbe kanonische STATUS_FARBEN-Map (ui.tsx) wie Pipeline-
// Kanban und der Status-Verteilungsbalken auf /jobs — Dashboard-Farbmodell V2 (Style Guide v5.0
// §18.1: „Gleiche Bedeutung erhält in allen Dashboards immer die gleiche Farbe").
function Funnel({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data)
  const max = Math.max(1, ...entries.map(([, v]) => v))
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm lg:col-span-2">
      <h3 className="mb-3 text-sm font-semibold text-brand-navy">{t('dashboard:pipeline_funnel.titel')} <span className="font-normal text-slate-400">{t('dashboard:pipeline_funnel.untertitel')}</span></h3>
      <div className="space-y-2">
        {entries.map(([stage, v]) => (
          <Link key={stage} to={`/jobs?status=${encodeURIComponent(stage)}`}
                className="flex items-center gap-2 rounded text-sm transition hover:bg-slate-50">
            <div className="w-20 shrink-0 text-slate-600">{wert('status', stage)}</div>
            <div className="relative h-6 flex-1 overflow-hidden rounded" style={{ backgroundColor: 'var(--spur-farbe)' /* ui.track.bar = Rolle spur */ }}>
              <div className="absolute inset-y-0 left-0 rounded"
                   style={{ width: `${Math.max((v / max) * 100, v ? 3 : 0)}%`, backgroundColor: STATUS_FARBEN[stage]?.bg || '#94A3B8' }} />
            </div>
            <div className="w-8 shrink-0 text-right font-medium tabular-nums text-slate-700">{v}</div>
          </Link>
        ))}
      </div>
    </div>
  )
}

function FollowUpBanner({ overdue, open, nOverdue, nOpen }: { overdue: number; open: number; nOverdue: number; nOpen: number }) {
  if (open === 0 && nOpen === 0) {
    return (
      <Link to="/followups" className="group flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-brand-cyan/60 hover:shadow-md">
        <div className="flex items-center gap-3">
          <span className="text-2xl">⏰</span>
          <div>
            <div className="text-sm font-semibold text-brand-navy">{t('dashboard:followup.titel')}</div>
            <div className="text-xs text-slate-500">{t('dashboard:followup.leer')}</div>
          </div>
        </div>
        <span className="text-slate-300 transition group-hover:text-brand-cyan">→</span>
      </Link>
    )
  }
  const totalOverdue = overdue + nOverdue
  const danger = totalOverdue > 0
  return (
    <Link to="/followups"
          className={`group flex items-center justify-between rounded-xl border p-4 shadow-sm transition hover:shadow-md ${
            danger ? 'border-rose-300 bg-rose-50 hover:border-rose-400' : 'border-brand-cyan/40 bg-white hover:border-brand-cyan/60'}`}>
      <div className="flex items-center gap-3">
        <span className="text-2xl">{danger ? '🔴' : '⏰'}</span>
        <div>
          <div className="text-sm font-semibold text-brand-navy">
            {danger ? t('dashboard:followup.faellig', { count: totalOverdue }) : t('dashboard:followup.im_blick')}
          </div>
          <div className="text-xs text-slate-500">
            {[
              t('dashboard:followup.stellen_offen', { anzahl: open }),
              overdue > 0 && t('dashboard:followup.faellig_n', { anzahl: overdue }),
              nOpen > 0 && t('dashboard:followup.netzwerk_offen', { anzahl: nOpen }),
              nOpen > 0 && nOverdue > 0 && t('dashboard:followup.faellig_n', { anzahl: nOverdue }),
            ].filter(Boolean).join(' · ')}
          </div>
        </div>
      </div>
      <span className="text-slate-300 transition group-hover:text-brand-cyan">→</span>
    </Link>
  )
}

// Beispieldaten-Hinweis (P2-59) — eigener, in sich geschlossener Fetch gegen /api/beispieldaten
// (der Typ steht bewusst lokal hier). Rendert NUR, solange die Beispieldaten
// einer frischen Installation noch vorhanden sind; ein Fetch-Fehler zählt als „kein Hinweis“.
function BeispieldatenBanner() {
  const [name, setName] = useState<string | null>(null)
  useEffect(() => {
    api<{ status: string; name: string | null }>('/beispieldaten')
      .then((d) => setName(d.status === 'vorhanden' ? (d.name ?? 'Benno Bewerbaer') : null))
      .catch(() => setName(null))
  }, [])
  if (!name) return null
  return (
    <Link to="/einstellungen"
          className="flex items-center justify-between rounded-lg border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm text-amber-800 shadow-sm transition hover:border-amber-400">
      <span>{t('dashboard:beispieldaten', { name })}</span>
      <span className="text-amber-400">→</span>
    </Link>
  )
}

// Sicherungs-Hinweis (P2-52) — eigener, in sich geschlossener Fetch gegen /api/sicherung (Muster
// BeispieldatenBanner). Rendert NUR bei gesetzter `warnung` (Kundentext kommt fertig vom Backend, s.
// sicherung.py::status, Vertrag V4). Ein Fetch-Fehler zählt als „kein Hinweis", nicht als eigene
// Fehlermeldung — dieselbe Vorsicht wie beim Beispieldaten-Hinweis: lieber kein Hinweis als ein falscher.
function SicherungBanner() {
  const [warnung, setWarnung] = useState<string | null>(null)
  useEffect(() => {
    api<{ warnung: string | null }>('/sicherung').then((d) => setWarnung(d.warnung)).catch(() => setWarnung(null))
  }, [])
  if (!warnung) return null
  return (
    <Link to="/einstellungen"
          className="flex items-center justify-between rounded-lg border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm text-amber-800 shadow-sm transition hover:border-amber-400">
      <span>{warnung}</span>
      <span className="text-amber-400">→</span>
    </Link>
  )
}

export default function Dashboard() {
  const [d, setD] = useState<DashboardData | null>(null)
  const [err, setErr] = useState<string | null>(null)
  // P2-79: neuester Absagen-Bericht für die Kopfzeile. Ein Fehler beim Laden zählt als „kein Bericht“
  // (nur der Link fehlt), nie als Fehlermeldung des ganzen Dashboards.
  const [absagen, setAbsagen] = useState<AbsagenStand | null>(null)
  const ladeAbsagen = () => api<AbsagenStand>('/absagen-analyse').then(setAbsagen).catch(() => setAbsagen(null))
  useEffect(() => { ladeAbsagen() }, [])
  // Ziel für Status und Meldung des Absagen-Analyse-Knopfs (statusTarget): Die Lauf-Anzeige soll unter
  // der Kopfzeile stehen, nicht in der schmalen Knopfgruppe (Muster Review.tsx, `empty:hidden`).
  const [laufBereich, setLaufBereich] = useState<HTMLElement | null>(null)

  // Eigene Funktion statt inline im useEffect — wird auch nach "Wiedervorlage +7 Tage" erneut
  // aufgerufen (GesamtprozessSection::onReload), damit die Karten sofort den neuen Stand zeigen.
  const load = () => api<DashboardData>('/dashboard').then(setD).catch((e) => setErr(String(e)))
  useEffect(() => { load() }, [])

  if (err) return <div className="rounded-lg bg-rose-50 p-4 text-rose-700">{t('dashboard:fehler', { meldung: err })}</div>
  if (!d) return <div className="text-slate-400">{t('dashboard:lade')}</div>

  const tot = d.totals
  // Gemeinsamer Maßstab über die drei Plan-Karten — sonst sähe Plan C (oft nur 1 Job) mit
  // seinem kartenlokalen Maximum wie ein Vollbalken aus und würde neben Plan A täuschen.
  const planMax = Math.max(1, ...(['A', 'B', 'C'] as const).flatMap((p) => Object.values(d.by_situation_plan[p])))
  // BarList zeigt den Schlüssel selbst als Beschriftung; Farben und Links brauchen weiter den DB-Wert.
  const nachStatus = beschriftet(d.by_status, (k) => wert('status', k))
  const nachPortal = beschriftet(d.by_portal, (p) => wert('portal', p))
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-brand-navy">{t('common:nav.dashboard')}</h1>
          <p className="text-sm text-slate-500">{t('dashboard:untertitel')}</p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {absagen?.datei && absagen.url && (
            <a href={absagen.url} title={t('dashboard:absagen.titel')}
               className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50">
              {t('dashboard:absagen.link', { datum: datum(absagen.datum) })}
            </a>
          )}
          <AgentTaskButton kind="absagen-analyse" label={t('dashboard:absagen.neu')} subtle
                           statusTarget={laufBereich} onFinished={ladeAbsagen} />
          <a href="/api/digest" className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50">{t('dashboard:digest')}</a>
          <a href="/api/export/excel" className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover">{t('dashboard:excel_export')}</a>
        </div>
      </div>
      <div ref={setLaufBereich} className="space-y-2 empty:hidden" />

      <BeispieldatenBanner />
      <SicherungBanner />
      <FollowUpBanner overdue={tot.followups_overdue} open={tot.followups_open} nOverdue={tot.netzwerk_overdue} nOpen={tot.netzwerk_open} />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label={t('dashboard:stat.stellen')} value={tot.jobs} to="/jobs?sort=found" />
        <Stat label={t('dashboard:stat.top')} value={tot.top_matches} accent to="/jobs?min_score=4&sort=found" />
        <Stat label={t('dashboard:stat.bewerbungen')} value={tot.active_applications} sub={t('dashboard:stat.bewerbungen_sub', { anzahl: tot.applications })} to="/jobs?statuses=Beworben,Interview,Angebot&sort=found" />
        {tot.applied_offline > 0 && <Stat label={t('dashboard:stat.offline')} value={tot.applied_offline} danger to="/jobs?availability_status=offline" />}
      </div>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label={t('dashboard:stat.emails')} value={tot.emails} to="/inbox" />
        <Stat label={t('dashboard:stat.antworten')} value={tot.responses} to="/inbox" />
        <Stat label={t('dashboard:stat.antwortzeit')} value={tot.avg_response_hours != null ? `${tot.avg_response_hours} h` : '–'} />
        <Stat label={t('dashboard:stat.antwortquote')} value={tot.response_rate != null ? t('dashboard:prozent_kompakt', { wert: tot.response_rate }) : '–'} accent />
      </div>

      <GesamtprozessSection d={d} onReload={load} />

      <Funnel data={d.funnel} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="space-y-4">
          <BarList title={t('dashboard:balken.status')} data={nachStatus.data} colorFn={(k) => STATUS_FARBEN[nachStatus.db(k)]?.bg || '#94A3B8'}
                   linkFn={(k) => `/jobs?status=${encodeURIComponent(nachStatus.db(k))}`} />
          <BarList title={t('dashboard:balken.fit')} data={d.by_score} colorFn={(k) => SCORE_COLORS[Number(k)] || '#94A3B8'}
                   linkFn={(k) => `/jobs?score=${k === '—' ? 'none' : encodeURIComponent(k)}`} />
          <BarList title={t('dashboard:balken.portal')} data={nachPortal.data} linkFn={(k) => `/jobs?portal=${encodeURIComponent(nachPortal.db(k))}`} />
        </div>
        <div className="space-y-4">
          {(['A', 'B', 'C'] as const).map((p) => {
            const nachSituation = beschriftet(d.by_situation_plan[p], (k) => wert('situation', k))
            return (
              <BarList key={p} title={t('dashboard:balken.situation', { plan: p })} data={nachSituation.data}
                       colorFn={(k) => SITU_COLORS[nachSituation.db(k)] || 'var(--aktion-farbe)'} maxValue={planMax}
                       linkFn={(k) => `/jobs?situation=${encodeURIComponent(nachSituation.db(k))}&plan=${p}`} />
            )
          })}
          {Object.keys(d.by_situation_plan.ohne).length > 0 && (
            <Link to="/jobs?plan=none" className="block px-1 text-xs text-slate-400 hover:text-brand-cyan">
              {t('dashboard:balken.ohne_plan', { count: Object.values(d.by_situation_plan.ohne).reduce((a, b) => a + b, 0) })}
            </Link>
          )}
        </div>
      </div>
    </div>
  )
}
