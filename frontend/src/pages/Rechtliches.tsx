import { useState } from 'react'
import ueberMd from '../rechtliches/ueber.md?raw'
import lizenzMd from '../rechtliches/lizenz.md?raw'
import lizenzTxt from '../rechtliches/lizenz.txt?raw'
import datenschutzMd from '../rechtliches/datenschutz.md?raw'
import drittlizenzenMd from '../rechtliches/drittlizenzen.md?raw'

// ── Mini-Markdown-Renderer (Phase 71E) ──────────────────────────────────────────────
// Bewusst von Hand statt einer npm-Dependency (Spec-Vorgabe: kein neues Paket nur für
// wenige statische Rechtstexte). Deckt genau das ab, was diese Texte brauchen: h1/h2/h3,
// Absätze, Listen, **fett**, https-Adressen als Link, Blockquote, Trennlinie. Rendert
// React-Elemente (kein dangerouslySetInnerHTML) — die Texte kommen zwar aus eigenen Dateien,
// nicht aus Nutzereingaben, aber echte Elemente sind ohnehin die sauberere Lösung.
type MdBlock =
  | { kind: 'h1' | 'h2' | 'h3'; text: string }
  | { kind: 'p'; text: string }
  | { kind: 'ul'; items: string[] }
  | { kind: 'blockquote'; paragraphs: string[] }
  | { kind: 'hr' }

const HEADING_RE = /^(#{1,3})\s+(.*)$/
const HR_RE = /^(-{3,}|\*{3,})\s*$/
const LIST_RE = /^[-*]\s+(.*)$/
const QUOTE_RE = /^>\s?(.*)$/

function parseMarkdown(src: string): MdBlock[] {
  const lines = src.replace(/\r\n/g, '\n').split('\n')
  const blocks: MdBlock[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    if (line.trim() === '') { i++; continue }

    const heading = line.match(HEADING_RE)
    if (heading) {
      const level = heading[1].length
      blocks.push({ kind: level === 1 ? 'h1' : level === 2 ? 'h2' : 'h3', text: heading[2].trim() })
      i++
      continue
    }

    if (HR_RE.test(line)) {
      blocks.push({ kind: 'hr' })
      i++
      continue
    }

    if (LIST_RE.test(line)) {
      const items: string[] = []
      while (i < lines.length && LIST_RE.test(lines[i])) {
        const parts = [(lines[i].match(LIST_RE) as RegExpMatchArray)[1].trim()]
        i++
        // Weich umgebrochene Folgezeilen (kein eigenes '-', keine Leerzeile, kein neuer
        // Block) gehören noch zum selben Punkt — sonst reißt z. B. "Google Gmail — für das
        // Lesen … und das Anlegen von" (datenschutz.md) mitten im Satz ab.
        while (
          i < lines.length && lines[i].trim() !== '' &&
          !LIST_RE.test(lines[i]) && !HEADING_RE.test(lines[i]) &&
          !HR_RE.test(lines[i]) && !QUOTE_RE.test(lines[i])
        ) {
          parts.push(lines[i].trim())
          i++
        }
        items.push(parts.join(' '))
      }
      blocks.push({ kind: 'ul', items })
      continue
    }

    if (QUOTE_RE.test(line)) {
      // Aufeinanderfolgende '>'-Zeilen gehören zu EINEM Blockquote; eine leere '>'-Zeile
      // markiert darin einen Absatzumbruch.
      const raw: string[] = []
      while (i < lines.length && QUOTE_RE.test(lines[i])) {
        raw.push((lines[i].match(QUOTE_RE) as RegExpMatchArray)[1])
        i++
      }
      const paragraphs: string[] = []
      let cur: string[] = []
      for (const r of raw) {
        if (r.trim() === '') {
          if (cur.length) { paragraphs.push(cur.join(' ')); cur = [] }
        } else {
          cur.push(r.trim())
        }
      }
      if (cur.length) paragraphs.push(cur.join(' '))
      blocks.push({ kind: 'blockquote', paragraphs })
      continue
    }

    // Absatz: alles bis zur nächsten Leerzeile oder dem Beginn eines anderen Blocktyps.
    const buf: string[] = []
    while (
      i < lines.length && lines[i].trim() !== '' &&
      !HEADING_RE.test(lines[i]) && !HR_RE.test(lines[i]) &&
      !LIST_RE.test(lines[i]) && !QUOTE_RE.test(lines[i])
    ) {
      buf.push(lines[i].trim())
      i++
    }
    blocks.push({ kind: 'p', text: buf.join(' ') })
  }

  return blocks
}

/** Inline-Stile innerhalb eines Textblocks: **fett** wird <strong>, eine nackte https-Adresse
 *  (ueber.md: Repo, datenschutz.md: GitHub-Datenschutzerklärung) ein Link in einem neuen Tab.
 *  Ein Satzzeichen direkt hinter der Adresse gehört nicht mehr zu ihr. Mehr brauchen diese
 *  Texte nicht, Markdown-Links `[…](…)` kennt der Renderer bewusst nicht. */
const INLINE_RE = /(\*\*[^*]+\*\*|https:\/\/[^\s)]*[^\s).,;:!?])/g

function renderInline(text: string, keyPrefix: string) {
  const parts = text.split(INLINE_RE).filter((p) => p.length > 0)
  return parts.map((part, idx) => {
    const key = `${keyPrefix}-${idx}`
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={key}>{part.slice(2, -2)}</strong>
    if (part.startsWith('https://')) {
      return (
        <a key={key} href={part} target="_blank" rel="noopener noreferrer"
           className="break-words text-brand-cyan hover:underline">{part}</a>
      )
    }
    return part
  })
}

function renderMarkdown(src: string) {
  return parseMarkdown(src).map((b, i) => {
    const key = `blk-${i}`
    switch (b.kind) {
      case 'h1':
        return <h1 key={key} className="text-lg font-bold text-brand-navy">{renderInline(b.text, key)}</h1>
      case 'h2':
        return <h2 key={key} className="text-lg font-bold text-brand-navy">{renderInline(b.text, key)}</h2>
      case 'h3':
        return <h3 key={key} className="pt-2 text-sm font-bold uppercase tracking-wide text-brand-navy/70">{renderInline(b.text, key)}</h3>
      case 'hr':
        return <hr key={key} className="border-slate-200" />
      case 'ul':
        return (
          <ul key={key} className="list-disc space-y-1 pl-5 text-sm leading-relaxed text-slate-600">
            {b.items.map((it, j) => <li key={j}>{renderInline(it, `${key}-${j}`)}</li>)}
          </ul>
        )
      case 'blockquote':
        return (
          <blockquote key={key} className="space-y-2 rounded-r-lg border-l-4 border-brand-cyan/50 bg-brand-cyan/5 px-4 py-3 text-sm leading-relaxed text-slate-700">
            {b.paragraphs.map((p, j) => <p key={j}>{renderInline(p, `${key}-${j}`)}</p>)}
          </blockquote>
        )
      case 'p':
      default:
        return <p key={key} className="text-sm leading-relaxed text-slate-600">{renderInline(b.text, key)}</p>
    }
  })
}

// ── Lizenztexte (P2-77) ───────────────────────────────────────────────────────────────
// Der Wortlaut aller Drittanbieter-Lizenzen (~150 KB) steht in drittlizenzen_texte.txt, die
// der Generator pipeline/drittlizenzen.py erzeugt. Er wird bewusst NICHT statisch importiert:
// Der dynamische import() macht daraus einen eigenen Chunk, der erst beim ersten Klick auf
// „Lizenztexte anzeigen“ geladen wird — das Haupt-Bundle wächst nicht. Nach dem Laden hält
// die Komponente den Text im State, Aus- und Einblenden lädt nichts nach.
const LIZENZTEXTE_DATEI = 'frontend/src/rechtliches/drittlizenzen_texte.txt'

function Lizenztexte() {
  const [offen, setOffen] = useState(false)
  const [laedt, setLaedt] = useState(false)
  const [fehler, setFehler] = useState(false)
  const [text, setText] = useState<string | null>(null)

  function umschalten() {
    if (offen) { setOffen(false); return }
    setOffen(true)
    if (text !== null || laedt) return
    setLaedt(true)
    setFehler(false)
    import('../rechtliches/drittlizenzen_texte.txt?raw')
      .then((m) => setText(m.default))
      .catch(() => setFehler(true))
      .finally(() => setLaedt(false))
  }

  return (
    <div className="space-y-3">
      <button type="button" onClick={umschalten} aria-expanded={offen} aria-controls="lizenztexte"
        className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50">
        {offen ? 'Lizenztexte ausblenden' : 'Lizenztexte anzeigen'}
      </button>

      {offen && (
        <div id="lizenztexte">
          {laedt && <p role="status" className="text-sm text-slate-500">Lädt …</p>}
          {fehler && (
            <p role="alert" className="text-sm text-rose-600">
              Die Lizenztexte konnten nicht geladen werden. Den Wortlaut enthält die Datei{' '}
              {LIZENZTEXTE_DATEI} im Programmordner.
            </p>
          )}
          {text !== null && (
            <pre tabIndex={0} aria-label="Lizenztexte der Open-Source-Bestandteile"
              className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-100 p-3 font-mono text-xs leading-relaxed text-slate-700">
              {text}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

// ── Seite ─────────────────────────────────────────────────────────────────────────────
const SECTIONS = [
  { id: 'ueber', label: 'Über dieses Programm', md: ueberMd },
  { id: 'lizenz', label: 'Open-Source-Lizenz', md: lizenzMd },
  { id: 'datenschutz', label: 'Datenschutz', md: datenschutzMd },
  { id: 'drittlizenzen', label: 'Drittanbieter-Lizenzen', md: drittlizenzenMd },
] as const

export default function Rechtliches() {
  const [activeId, setActiveId] = useState<(typeof SECTIONS)[number]['id']>(SECTIONS[0].id)
  const active = SECTIONS.find((s) => s.id === activeId) ?? SECTIONS[0]

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">Rechtliches</h1>
        <p className="text-sm text-slate-500">
          Herausgeber, Lizenz des Programms, Hinweise zum Datenschutz und die Lizenzen der
          Open-Source-Bestandteile.
        </p>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {SECTIONS.map((s) => (
          <button key={s.id} onClick={() => setActiveId(s.id)}
            className={`rounded-t-lg px-4 py-2 text-sm font-medium ${
              activeId === s.id ? 'border-b-2 border-brand-cyan text-brand-navy' : 'text-slate-500 hover:text-slate-700'
            }`}>
            {s.label}
          </button>
        ))}
      </div>

      <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        {renderMarkdown(active.md)}
        {/* Wortlaut der eigenen Lizenz: lizenz.txt ist eine Kopie von LICENSE im Projektordner, die
            der Build-Spiegel (frontend/build.sh kopiert nur frontend/) sonst nicht sähe. Ein Test
            hält beide bytegleich (test_open_source_lizenz.py). */}
        {active.id === 'lizenz' && (
          <pre tabIndex={0} aria-label="Wortlaut der Apache License 2.0"
            className="max-h-[32rem] overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-100 p-3 font-mono text-xs leading-relaxed text-slate-700">
            {lizenzTxt}
          </pre>
        )}
        {/* P2-77: Wortlaut der Lizenzen nur im Abschnitt Drittanbieter-Lizenzen, unter der Übersicht. */}
        {active.id === 'drittlizenzen' && <Lizenztexte />}
      </div>
    </div>
  )
}
