import { useEffect, useRef, useState } from 'react'
import { t } from '../i18n'

/** Gemeinsame Live-Ansicht einer Beirats-Debatte (Phase 39, aus Beirat.tsx extrahiert für den
 *  Stellen-Check in JobDetail — Phase 40, Design-Entscheidung 7: „kein Fork"). Verbindet sich
 *  selbst mit dem SSE-Strom und rendert Moderation/Beiträge/Abstimmung/Synthese live; die
 *  umgebende Seite steuert nur ihr eigenes Drumherum (Start-Formular, Fortschrittsanzeige,
 *  Fehlermeldung) über die optionalen Callbacks. */

type Zeile =
  | { art: 'moderation'; text: string }
  | { art: 'status'; text: string }
  | { art: 'beitrag'; kopf: string; anzeige: string; farbe: string; frage: string; text: string; nr: number; fertig: boolean }
  | { art: 'votum'; kopf: string; anzeige: string; farbe: string; stimme: any; enthaltung: boolean }
  | { art: 'synthese'; text: string; fertig: boolean }

function Initialen({ name, farbe, klein }: { name: string; farbe: string; klein?: boolean }) {
  const ini = name.split(' ').map((t) => t[0]).slice(0, 2).join('')
  const size = klein ? 'h-6 w-6 text-[10px]' : 'h-8 w-8 text-xs'
  return (
    <span className={`flex ${size} shrink-0 items-center justify-center rounded-full font-bold text-white`}
      style={{ backgroundColor: farbe }}>{ini}</span>
  )
}

const VOTUM_STYLE: Record<string, string> = {
  Bewerben: 'bg-emerald-100 text-emerald-800', Bedingt: 'bg-amber-100 text-amber-800', Nicht: 'bg-rose-100 text-rose-700',
}

export default function BeiratLive({ debatteId, compact, onFortschritt, onFertig, onFehler, onEntscheidung }: {
  debatteId: string
  /** Kompakte Darstellung (JobDetail-Workflow-Karte): kleinere Schrift, begrenzte Höhe + Scroll. */
  compact?: boolean
  onFortschritt?: (f: { nr: number; min: number; max: number }) => void
  onFertig?: (debatte: any) => void
  onFehler?: (msg: string) => void
  /** Stellen-Check (Phase 40): feuert sobald die deterministische Entscheidung berechnet ist —
   *  noch VOR der Synthese, damit die aufrufende Seite früh reagieren kann. */
  onEntscheidung?: (e: any) => void
}) {
  const [zeilen, setZeilen] = useState<Zeile[]>([])
  const esRef = useRef<EventSource | null>(null)
  const endeRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    setZeilen([])
    esRef.current?.close()
    const es = new EventSource(`/api/beirat/debatten/${debatteId}/stream`)
    esRef.current = es
    es.onmessage = (e) => {
      const ev = JSON.parse(e.data)
      setZeilen((z) => {
        const n = [...z]
        if (ev.typ === 'stand' || ev.typ === 'archiv') {
          const d = ev.debatte
          const neu: Zeile[] = []
          d.moderationen?.forEach((m: any, i: number) => {
            neu.push({ art: 'moderation', text: m.text })
            const b = d.beitraege?.[i]
            if (b) neu.push({ art: 'beitrag', kopf: b.kopf, anzeige: b.anzeige, farbe: b.farbe, frage: b.frage, text: b.text, nr: i + 1, fertig: true })
          })
          if (d.abstimmung) {
            Object.entries(d.abstimmung).forEach(([kopf, stimme]: any) => {
              const teilnehmer = d.teilnehmer?.find((t: any) => t.id === kopf)
              neu.push({ art: 'votum', kopf, anzeige: teilnehmer?.anzeige || kopf, farbe: teilnehmer?.farbe || '#64748b', stimme, enthaltung: !stimme })
            })
          }
          if (d.synthese) neu.push({ art: 'synthese', text: d.synthese, fertig: true })
          else if (d.check_synthese) neu.push({ art: 'synthese', text: d.check_synthese.begruendung || '', fertig: true })
          if (ev.typ === 'archiv') { onFertig?.(d); if (d.entscheidung) onEntscheidung?.(d.entscheidung) }
          return neu
        }
        if (ev.typ === 'status') n.push({ art: 'status', text: ev.text })
        if (ev.typ === 'moderation') n.push({ art: 'moderation', text: ev.text })
        if (ev.typ === 'beitrag_start') {
          onFortschritt?.({ nr: ev.nr, min: ev.min, max: ev.max })
          n.push({ art: 'beitrag', kopf: ev.kopf, anzeige: ev.anzeige, farbe: ev.farbe, frage: ev.frage, text: '', nr: ev.nr, fertig: false })
        }
        if (ev.typ === 'delta') {
          const letzte = ev.kopf === 'synthese'
            ? [...n].reverse().find((x) => x.art === 'synthese' && !x.fertig)
            : [...n].reverse().find((x) => x.art === 'beitrag' && !x.fertig && (x as any).kopf === ev.kopf)
          if (letzte) (letzte as any).text += ev.text
        }
        if (ev.typ === 'beitrag_ende') {
          const b = [...n].reverse().find((x) => x.art === 'beitrag' && !x.fertig) as any
          if (b) { b.text = ev.text; b.fertig = true }
        }
        if (ev.typ === 'abstimmung_start') n.push({ art: 'status', text: t('beirat:live.abstimmung_start') })
        if (ev.typ === 'votum') n.push({ art: 'votum', kopf: ev.kopf, anzeige: ev.anzeige, farbe: ev.farbe, stimme: ev.stimme, enthaltung: ev.enthaltung })
        if (ev.typ === 'entscheidung') { onEntscheidung?.(ev.entscheidung) }
        if (ev.typ === 'synthese_start') n.push({ art: 'synthese', text: '', fertig: false })
        if (ev.typ === 'synthese_ende') {
          const s = [...n].reverse().find((x) => x.art === 'synthese') as any
          if (s) { s.fertig = true; if (!s.text) { try { s.text = JSON.parse(ev.text).begruendung || ev.text } catch { s.text = ev.text } } }
        }
        if (ev.typ === 'fertig') onFertig?.(null)
        if (ev.typ === 'fehler') onFehler?.(ev.text)
        return n
      })
    }
    es.onerror = () => { es.close() }
    return () => es.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debatteId])

  useEffect(() => { endeRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [zeilen])

  if (zeilen.length === 0) return null

  return (
    <div className={compact
      ? 'space-y-2 overflow-y-auto rounded-lg border border-slate-200 bg-white p-3'
      : 'space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm'}
      style={compact ? { maxHeight: 320 } : undefined}>
      {zeilen.map((z, i) => {
        if (z.art === 'status') return <div key={i} className="text-center text-xs text-slate-400">{z.text}</div>
        if (z.art === 'moderation') return (
          <div key={i} className={`flex items-start gap-2 rounded-lg bg-slate-50 px-2.5 py-1.5 text-slate-600 ${compact ? 'text-xs' : 'text-sm'}`}>
            <span className="mt-0.5 shrink-0 rounded-full bg-brand-navy px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-white">{t('beirat:live.vorsitz')}</span>
            <span>{z.text}</span>
          </div>
        )
        if (z.art === 'votum') return (
          <div key={i} className="flex items-center gap-2 text-xs">
            <Initialen name={z.anzeige} farbe={z.farbe} klein />
            <span className="font-medium text-slate-600">{z.anzeige}</span>
            {z.enthaltung
              ? <span className="rounded-full bg-slate-100 px-2 py-0.5 italic text-slate-400">{t('beirat:live.enthaltung')}</span>
              : <span className={`rounded-full px-2 py-0.5 font-semibold ${VOTUM_STYLE[z.stimme?.votum] || 'bg-slate-100 text-slate-500'}`}>{z.stimme?.votum ? t(`beirat:wert.${z.stimme.votum}`, { defaultValue: z.stimme.votum }) : z.stimme?.votum}</span>}
          </div>
        )
        if (z.art === 'beitrag') return (
          <div key={i} className="flex items-start gap-2.5">
            <Initialen name={z.anzeige} farbe={z.farbe} klein={compact} />
            <div className={`min-w-0 flex-1 rounded-xl border px-3 py-2 ${compact ? 'py-1.5' : ''}`} style={{ borderColor: z.farbe + '55', backgroundColor: z.farbe + '0d' }}>
              <div className="mb-1 flex items-baseline gap-2">
                <span className={`font-semibold ${compact ? 'text-xs' : 'text-sm'}`} style={{ color: z.farbe }}>{z.anzeige}</span>
                {!compact && <span className="text-xs text-slate-400">{t('beirat:live.beitrag_nr', { nr: z.nr })}</span>}
                {!z.fertig && <span className="animate-pulse text-xs text-slate-400">{t('beirat:live.schreibt')}</span>}
              </div>
              <div className={`whitespace-pre-wrap text-slate-700 ${compact ? 'text-xs' : 'text-sm'}`}>{z.text}{!z.fertig && <span className="animate-pulse">▋</span>}</div>
            </div>
          </div>
        )
        return (
          <div key={i} className={`rounded-xl border-2 border-brand-cyan/50 bg-brand-cyan/5 ${compact ? 'p-2.5' : 'p-4'}`}>
            <div className={`mb-1.5 font-bold uppercase tracking-wide text-brand-navy ${compact ? 'text-xs' : 'text-sm'}`}>
              {t('beirat:live.synthese')}{!z.fertig && <span className="ml-2 animate-pulse font-normal normal-case text-slate-400">{t('beirat:live.entsteht')}</span>}
            </div>
            <div className={`whitespace-pre-wrap text-slate-700 ${compact ? 'text-xs' : 'text-sm'}`}>{z.text}{!z.fertig && <span className="animate-pulse">▋</span>}</div>
          </div>
        )
      })}
      <div ref={endeRef} />
    </div>
  )
}
