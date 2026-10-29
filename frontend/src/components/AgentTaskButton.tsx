import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { api, type AgentTaskRow } from '../api'

const ACTIVE = ['queued', 'running']

const CHIP: Record<string, string> = {
  queued: 'bg-slate-100 text-slate-600',
  running: 'bg-indigo-100 text-indigo-800',
  done: 'bg-emerald-100 text-emerald-800',
  failed: 'bg-rose-100 text-rose-700',
  cancelled: 'bg-slate-100 text-slate-500',
}
const CHIP_TEXT: Record<string, string> = {
  queued: 'wartet…', running: 'läuft…', done: '✓ fertig', failed: '✗ fehlgeschlagen', cancelled: 'abgebrochen',
}

/** Eine Zeile des stream-json-Logs lesbar machen. */
function pretty(line: string): string | null {
  try {
    const ev = JSON.parse(line)
    if (ev.type === 'system') {
      // stream-json kennt mehrere system-Subtypen — nur `init` ist der Lauf-Start mit Tool-Liste.
      // (Bug bis 11.07.: JEDE system-Zeile wurde als „Lauf gestartet (0 Tools)" gerendert.)
      if (ev.subtype === 'init') return `· Lauf gestartet (${(ev.tools || []).length} Tools)`
      if (ev.subtype === 'task_started') return `⤷ Subagent: ${String(ev.description || 'gestartet').slice(0, 140)}`
      if (ev.subtype === 'task_notification' && ev.summary) return `⤷ Subagent fertig: ${String(ev.summary).slice(0, 140)}`
      return null // task_progress/thinking_tokens etc. — Rauschen, nicht anzeigen
    }
    if (ev.type === 'assistant') {
      const parts = ev.message?.content || []
      const text = parts.filter((p: any) => p.type === 'text').map((p: any) => p.text).join(' ').trim()
      const tools = parts.filter((p: any) => p.type === 'tool_use').map((p: any) => p.name)
      if (tools.length) return `🔧 ${tools.join(', ')}`
      return text ? `💬 ${text.slice(0, 160)}` : null
    }
    if (ev.type === 'result') return `${ev.is_error ? '✗' : '✓'} ${String(ev.result || '').slice(0, 200)}`
    return null
  } catch {
    return line.trim() ? line.slice(0, 160) : null
  }
}

/** P2-75: Server-Begründung der Rückfrage „Anzeigentext fehlt" für die Anzeige aufbereiten —
 *  ohne Marker `ANZEIGE_FEHLT: ` und ohne die technische Klammer `(params.…)` am Ende (die
 *  gehört in den API-Kontrakt, nicht vor die Augen des Nutzers). */
function anzeigeRueckfrageText(msg: string): string {
  const text = msg.replace(/^ANZEIGE_FEHLT:\s*/, '').replace(/\s*\(params\.[^)]*\)\s*$/, '').trim()
  return text || msg
}

/** Startet einen Skill (oder eine Kette) headless im Backend und zeigt Status + Log. */
export default function AgentTaskButton({ kind, jobId, label, onFinished, watchKinds, subtle, resultLinks, params, statusTarget, zweizeilig }: {
  kind: string
  /** Ohne jobId: job-unabhängige Läufe wie der Tageslauf oder die Absagen-Analyse. */
  jobId?: number
  label: string; onFinished?: () => void
  /** Bei Ketten: welche Task-Arten für den Status beobachtet werden (Default: [kind]). */
  watchKinds?: string[]
  subtle?: boolean
  /** Artefakt-Links, die nach `done` unter der Abschlussmeldung erscheinen (Phase 18 D2). */
  resultLinks?: { href: string; label: string; download?: boolean }[]
  /** Zusätzliche Parameter für needs_params-Skills (Phase 27, z. B. { email_id }) — in den POST-Body gemergt. */
  params?: Record<string, any>
  /** Ziel-Element für Status/Meldung/Log (P2-18, Phase 93). Ohne die Prop bleibt alles wie
   *  bisher DIREKT unter dem Button. Mit ihr wandert nur der Statusteil per Portal dorthin —
   *  gedacht für Button-REIHEN, in denen jeder Button in einer schmalen `flex-1`-Spalte sitzt:
   *  Dort sprengte eine lange Log-Zeile die Spalte und damit die Karte (gemessen 1343 px in
   *  einer 992 px breiten Karte). Der Button bleibt an seinem Platz, der Bericht bekommt die
   *  volle Breite. Opt-in, damit die übrigen 18 Verwendungsstellen unberührt bleiben. */
  statusTarget?: HTMLElement | null
  /** Lauf-Werte in zwei festen Zeilen statt einer umbrechenden (14.10.2026): oben Status
   *  und Herkunft (bei Platzmangel einzeilig gekürzt), unten Dauer, Turns, Kosten und Log. So
   *  ist der Kopf immer gleich hoch und die Abschlussmeldungen zweier Knöpfe nebeneinander
   *  beginnen auf derselben Höhe. Opt-in wie `statusTarget`. */
  zweizeilig?: boolean
}) {
  const [task, setTask] = useState<AgentTaskRow | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  // Text der Zielstellen-Fit-≤2-Rückfrage (Server-Begründung ohne Marker) — gesetzt heißt:
  // Nachfrage offen. Variablen-/Marker-Namen bleiben `lowMatch`/`LOW_MATCH` (API-Kontrakt).
  const [lowMatch, setLowMatch] = useState<string | null>(null)
  // P2-75: Text der Rückfrage „Anzeigentext fehlt" (Server-Begründung ohne Marker und ohne
  // `(params.…)`) — gesetzt heißt: Nachfrage offen. Marker `ANZEIGE_FEHLT` ist API-Kontrakt.
  const [anzeigeFehlt, setAnzeigeFehlt] = useState<string | null>(null)
  // P2-75: Bereits bestätigte Overrides (`low_match_ok`, `ohne_anzeigentext_ok`). Sie werden bei
  // jedem Start mitgesendet, damit zwei Rückfragen nacheinander ohne Ping-Pong beantwortbar sind.
  // Geleert nach Erfolg, bei Abbrechen, bei einem anderen Fehler und beim Wechsel der Stelle.
  const [bestaetigt, setBestaetigt] = useState<Record<string, unknown>>({})
  // P2-75: Der Start wartet länger als 3 s — der Server holt dann gerade den Anzeigentext nach.
  const [nachholHinweis, setNachholHinweis] = useState(false)
  const nachholTimer = useRef<number | null>(null)
  const [showLog, setShowLog] = useState(false)
  // Kompakt-Ansicht (18.07., Popup zu groß): Abschlussmeldung und Log zeigen
  // eingeklappt je 3 Zeilen, „mehr anzeigen" holt den vollen Text.
  const [showFullResult, setShowFullResult] = useState(false)
  const [showFullLog, setShowFullLog] = useState(false)
  const prevStatus = useRef<string | null>(null)

  const isChain = !!(watchKinds && watchKinds.length)
  const kinds = isChain ? watchKinds! : [kind]

  // Letzten passenden Lauf laden (Phase 23): kind-Filter serverseitig (kinds-Param), kein 40er-Fenster
  // mehr. Asymmetrisch: Ketten-Buttons zeigen NUR Ketten-Tasks; Einzel-Buttons zeigen den jüngsten Lauf
  // ihres kinds — egal ob einzeln ODER als Ketten-Schritt (Tageslauf) gelaufen.
  useEffect(() => {
    api<AgentTaskRow[]>(`/tasks?${jobId ? `job_id=${jobId}&` : ''}kinds=${encodeURIComponent(kinds.join(','))}&limit=10`)
      .then((all) => {
        const mine = isChain ? all.filter((t) => !!t.chain_id) : all
        setTask(mine.find((t) => ACTIVE.includes(t.status)) || mine[0] || null)
      })
      .catch(() => {})
  }, [jobId, kind])

  // P2-75: Eine Bestätigung gilt nur für die Stelle, bei der gefragt wurde — beim Wechsel der Stelle
  // (oder Art) verfallen offene Rückfragen und gesammelte Overrides.
  useEffect(() => {
    setLowMatch(null); setAnzeigeFehlt(null)
    setBestaetigt((alt) => (Object.keys(alt).length ? {} : alt))   // kein Extra-Render beim ersten Einblenden
  }, [jobId, kind])

  // P2-75: Timer für den Nachhol-Hinweis beim Ausblenden der Komponente aufräumen.
  useEffect(() => () => {
    if (nachholTimer.current != null) window.clearTimeout(nachholTimer.current)
  }, [])

  // Polling, solange der Lauf aktiv ist
  useEffect(() => {
    if (!task || !ACTIVE.includes(task.status)) {
      if (prevStatus.current && ACTIVE.includes(prevStatus.current) && task && !ACTIVE.includes(task.status)) {
        onFinished?.()          // Lauf gerade beendet → Job-Detail neu laden
      }
      prevStatus.current = task?.status ?? null
      return
    }
    prevStatus.current = task.status
    const iv = setInterval(() => {
      api<AgentTaskRow>(`/tasks/${task.id}`).then(setTask).catch(() => {})
    }, 3000)
    return () => clearInterval(iv)
  }, [task?.id, task?.status])

  const start = async (extra?: Record<string, unknown>) => {
    setBusy(true); setErr(null); setLowMatch(null); setAnzeigeFehlt(null)
    // P2-75: `extra` kommt nur aus den Rückfrage-Knöpfen und baut auf den bisherigen Bestätigungen
    // auf. Der Hauptknopf ruft ohne `extra` auf = frischer Start ohne alte Bestätigungen.
    const ueberschreibt = extra ? { ...bestaetigt, ...extra } : {}
    const merged = { ...(params || {}), ...ueberschreibt }
    // P2-75: Holt der Server den Anzeigentext nach, kann der Start gut eine halbe Minute dauern.
    // Nach 3 s erscheint der Hinweis; mit `ohne_anzeigentext_ok` holt der Server nichts nach.
    if (nachholTimer.current != null) window.clearTimeout(nachholTimer.current)
    nachholTimer.current = merged.ohne_anzeigentext_ok
      ? null
      : window.setTimeout(() => setNachholHinweis(true), 3000)
    try {
      const r = await api<any>('/tasks', {
        method: 'POST',
        body: JSON.stringify({ kind, ...(jobId ? { job_id: jobId } : {}), ...(Object.keys(merged).length ? { params: merged } : {}) }),
      })
      setTask(r.tasks ? r.tasks[0] : r)      // Ketten liefern {chain_id, tasks:[…]}
      setShowLog(true)
      setBestaetigt({})
    } catch (e: any) {
      const msg = e?.message || 'Start fehlgeschlagen'
      // Zielstellen-Fit-≤2-Guard (27.07.2026): Server antwortet 409 „LOW_MATCH: …" → Rückfrage INLINE
      // statt `window.confirm` (27.07.: der Browser-Dialog erschien im eingebetteten
      // Fenster gar nicht, der Lauf war damit faktisch blockiert). Bestätigung startet
      // denselben Task mit ausdrücklichem Override — Warnung mit Ausweg, kein Verbot.
      // P2-75: Geprüft wird gegen die tatsächlich gesendeten Overrides (`merged`, nicht nur `extra`):
      // Wer `low_match_ok` schon bestätigt hat und danach `ANZEIGE_FEHLT` beantwortet, sendet es
      // weiter mit. Käme trotz gesendetem Override dieselbe Rückfrage erneut, ist das ein Fehler
      // und keine Endlosschleife aus Rückfragen.
      if (msg.startsWith('LOW_MATCH') && !merged.low_match_ok) {
        setLowMatch(msg.replace('LOW_MATCH: ', ''))
        setBestaetigt(ueberschreibt)
      } else if (msg.startsWith('ANZEIGE_FEHLT') && !merged.ohne_anzeigentext_ok) {
        // P2-75: Anzeigentext fehlt und ließ sich nicht nachholen → Rückfrage inline, Muster LOW_MATCH.
        setAnzeigeFehlt(anzeigeRueckfrageText(msg))
        setBestaetigt(ueberschreibt)
      } else {
        // Der Server sagt genau, warum (läuft bereits / Tagesbudget / nicht headless) — das zeigen wir.
        setErr(msg)
        setBestaetigt({})
      }
    } finally {
      if (nachholTimer.current != null) window.clearTimeout(nachholTimer.current)
      nachholTimer.current = null
      setNachholHinweis(false)
      setBusy(false)
    }
  }

  // P2-75: Rückfrage abbrechen = auch alle gesammelten Bestätigungen verwerfen.
  const rueckfrageAbbrechen = () => {
    setLowMatch(null); setAnzeigeFehlt(null); setBestaetigt({})
  }

  const cancel = async () => {
    if (!task) return
    await api(`/tasks/${task.id}/cancel`, { method: 'POST' }).catch(() => {})
    api<AgentTaskRow>(`/tasks/${task.id}`).then(setTask).catch(() => {})
  }

  const active = task && ACTIVE.includes(task.status)
  const lines = (task?.log || []).map(pretty).filter(Boolean) as string[]

  // Kopf des Laufs aus zwei Bausteinen: Status und Herkunft (`laufChips`), Werte und Log-Schalter
  // (`laufWerte`). Ohne `zweizeilig` stehen beide in einer umbrechenden Zeile, mit in zwei festen.
  const kette = task?.chain_id
    ? (isChain ? `${task.chain_label} · Schritt ${task.chain_pos}: ${task.label}` : `aus: ${task.chain_label}`)
    : null
  const laufChips = task && (
    <>
      <span className={`rounded-full px-2 py-0.5 font-medium ${zweizeilig ? 'shrink-0 ' : ''}${CHIP[task.status]}`}>{CHIP_TEXT[task.status]}</span>
      {kette && (
        <span className={`rounded-full bg-indigo-100 px-2 py-0.5 font-medium text-indigo-800${zweizeilig ? ' min-w-0 truncate' : ''}`}
          {...(zweizeilig ? { title: kette } : {})}>
          {kette}
        </span>
      )}
    </>
  )
  const laufWerte = task && (
    <>
      {task.duration_s != null && <span className="text-slate-400">{task.duration_s}s</span>}
      {task.num_turns != null && <span className="text-slate-400">· {task.num_turns} Turns</span>}
      {task.cost_usd != null && <span className="text-slate-400">· ${task.cost_usd.toFixed(3)}</span>}
      {(task.log?.length || active) && (
        <button onClick={() => setShowLog((v) => !v)} className="ml-auto text-brand-cyan hover:underline">
          {showLog ? 'Log ausblenden' : 'Log anzeigen'}
        </button>
      )}
    </>
  )

  // P2-18 (Phase 93): Der Statusteil ist eine eigene Einheit, damit er bei gesetztem
  // `statusTarget` per Portal aus der schmalen Button-Spalte in einen gemeinsamen,
  // volle Breite habenden Bereich unter der Button-Reihe wandern kann. Der React-Baum
  // bleibt derselbe — nur der DOM-Ort wechselt, State und Events verhalten sich gleich.
  const statusTeil = (
    <>
      {/* P2-75: Direkt unter dem Knopf — der Start wartet, weil der Server den Anzeigentext der
          Stelle nachholt (LinkedIn bremst manchmal und der Abruf wird mit Pausen wiederholt). */}
      {nachholHinweis && (
        <div role="status" className="px-1 text-xs text-slate-500">Anzeigentext wird nachgeholt …</div>
      )}
      {/* Kompakt-Modus: Meta/Meldung/Links nur bei laufendem Lauf zeigen (Live-Feedback) —
          im Fertig-Zustand bleibt allein der kleine Button; Details liefert das Task-Center. */}
      {task && (!subtle || active) && (zweizeilig ? (
        <div className="space-y-1 text-xs">
          <div className="flex min-w-0 items-center gap-2">{laufChips}</div>
          {/* min-h-4: die Zeile bleibt auch ohne Werte (Lauf wartet noch) eine Zeile hoch. */}
          <div className="flex min-h-4 items-center gap-2">{laufWerte}</div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2 text-xs">{laufChips}{laufWerte}</div>
      ))}

      {task?.status === 'failed' && task.error && (
        <div className="rounded-lg bg-rose-50 p-2 text-xs text-rose-700">{task.error}</div>
      )}
      {!subtle && task?.status === 'done' && task.result && (
        // Bewusst neutral: die Abschlussmeldung des Laufs ist KEIN verlässlicher Erfolgsnachweis
        // (kann „Recherche läuft im Hintergrund…" lauten). Maßgeblich sind Status-Chip + Artefakt.
        // Eingeklappt exakt 3 Zeilen (CSS-line-clamp statt Zeichenzählen — 18.07., Popup zu groß);
        // „mehr anzeigen" holt den vollen Text. Nichts wird abgeschnitten, nur eingeklappt.
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs text-slate-500">
          <span className="font-medium text-slate-400">Abschlussmeldung des Laufs:</span>
          <div
            className="mt-0.5 whitespace-pre-wrap"
            style={showFullResult ? undefined : { display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}
          >
            {task.result}
          </div>
          {(task.result.length > 220 || (task.result.match(/\n/g)?.length ?? 0) >= 3) && (
            <button onClick={() => setShowFullResult((v) => !v)} className="mt-1 text-brand-cyan hover:underline">
              {showFullResult ? '▴ weniger anzeigen' : '▸ mehr anzeigen'}
            </button>
          )}
        </div>
      )}
      {!subtle && task?.status === 'done' && resultLinks && resultLinks.length > 0 && (
        <div className="flex flex-wrap gap-3 px-1 text-xs">
          {resultLinks.map((l, i) => (
            <a key={i} href={l.href}
              {...(l.download ? { download: true } : {})}
              className="text-brand-cyan hover:underline">{l.label}</a>
          ))}
        </div>
      )}
      {err && <div className="rounded-lg bg-amber-50 p-2 text-xs text-amber-800">{err}</div>}

      {/* Zielstellen-Fit-≤2-Rückfrage inline (27.07.2026): „Bist du dir wirklich sicher?" mit
          Ja/Abbrechen. Bewusst KEIN window.confirm — der Dialog erschien im eingebetteten
          Fenster nicht und blockierte den Lauf faktisch. „Ja" startet denselben Task mit
          Override; der Klick des Nutzers IST die Freigabe (Human-in-the-Loop, Muster Phase 40). */}
      {lowMatch && (
        <div className="space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900">
          <p><b>Bist du dir wirklich sicher?</b> {lowMatch}</p>
          <div className="flex gap-2">
            <button onClick={() => start({ low_match_ok: true })} disabled={busy}
              className="rounded-md bg-amber-600 px-2.5 py-1 font-medium text-white hover:brightness-110 disabled:opacity-50">
              Ja, trotzdem starten
            </button>
            <button onClick={rueckfrageAbbrechen} disabled={busy}
              className="rounded-md border border-amber-300 px-2.5 py-1 hover:bg-amber-100 disabled:opacity-50">
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {/* P2-75: Rückfrage „Anzeigentext fehlt" — gleicher Aufbau wie die Zielstellen-Fit-Rückfrage.
          Der Server hat versucht, den Text nachzuholen, und es ist nicht gelungen; „Trotzdem
          starten" sendet `ohne_anzeigentext_ok` (zusammen mit schon bestätigten Overrides). */}
      {anzeigeFehlt && (
        <div className="space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900">
          <p><b>Ohne Anzeigentext starten?</b> {anzeigeFehlt}</p>
          <div className="flex gap-2">
            <button onClick={() => start({ ohne_anzeigentext_ok: true })} disabled={busy}
              className="rounded-md bg-amber-600 px-2.5 py-1 font-medium text-white hover:brightness-110 disabled:opacity-50">
              Trotzdem starten
            </button>
            <button onClick={rueckfrageAbbrechen} disabled={busy}
              className="rounded-md border border-amber-300 px-2.5 py-1 hover:bg-amber-100 disabled:opacity-50">
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {showLog && (
        <div className="max-h-48 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-2 font-mono text-[11px] leading-relaxed text-slate-600">
          {lines.length === 0
            ? <span className="text-slate-400">Noch keine Ausgabe…</span>
            : (showFullLog ? lines : lines.slice(-3)).map((l, i) => <div key={i} className="truncate" title={l}>{l}</div>)}
          {/* Eingeklappt die LETZTEN 3 Zeilen (beim Live-Lauf zählt das Neueste); „mehr anzeigen"
              holt die volle Liste in den bestehenden Scroll-Container (18.07., Popup zu groß). */}
          {lines.length > 3 && (
            <button onClick={() => setShowFullLog((v) => !v)} className="mt-1 font-sans text-brand-cyan hover:underline">
              {showFullLog ? '▴ weniger anzeigen' : `▸ mehr anzeigen (${lines.length - 3} weitere Zeilen)`}
            </button>
          )}
        </div>
      )}
    </>
  )

  return (
    <div className="min-w-0 space-y-1.5">
      <div className="flex items-center gap-2">
        {/* subtle = echte Kompakt-Variante (20.07., „nicht im Sync"): exakt die Klassen des
            Beirats-„neu prüfen"-Buttons, kein flex-1, kein ▶ — sonst sprengt der Re-Run-Button
            die Fertig-Zeile der Workflow-Karte. */}
        <button onClick={() => start()} disabled={busy || !!active}
          className={subtle
            ? 'whitespace-nowrap rounded-lg border border-brand-cyan/40 px-3 py-1.5 text-xs font-medium text-brand-navy transition hover:bg-brand-cyan/10 disabled:cursor-not-allowed disabled:opacity-50'
            : 'flex-1 rounded-lg bg-brand-cyan px-3 py-2 text-sm font-semibold text-brand-aufAktion transition hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-50'}>
          {active ? '⏳ Läuft…' : busy ? 'Starte…' : subtle ? label : `▶ ${label}`}
        </button>
        {active && (
          <button onClick={cancel} className="rounded-lg border border-slate-300 px-2.5 py-2 text-xs text-slate-600 hover:bg-slate-50">
            Abbrechen
          </button>
        )}
      </div>

      {statusTarget
        ? createPortal(<div className="space-y-1.5">{statusTeil}</div>, statusTarget)
        : statusTeil}
    </div>
  )
}
