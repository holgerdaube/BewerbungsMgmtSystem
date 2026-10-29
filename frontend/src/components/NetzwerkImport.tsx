import { useEffect, useId, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import {
  apiUpload,
  type NetzwerkImportAktion, type NetzwerkImportAnzahl, type NetzwerkImportErgebnis, type NetzwerkImportListe,
  type NetzwerkImportVorschau, type NetzwerkImportZeile,
} from '../api'
import { TEXT_AUF_ZUSTAND } from './ui'

// P2-62: Netzwerk-Listen (Zielfirmen, Headhunter, Netzwerk-Kontakte) aus einer Datei importieren.
//
// Zwei Bausteine statt einem, weil der Knopf in die Kopfzeile des Reiters gehört (neben
// „+ … anlegen“) und das Panel darunter aufgeht, wie bei TargetNew und NcNew. Die Seite hält nur
// das Ein und Aus; Datei, Vorschau und Ergebnis leben im Panel und sind mit dem Schließen weg.
//
// Ablauf: Datei wählen, Vorschau (der Server schreibt dabei nichts), „Importieren“, Ergebnis. Der
// Server merkt sich nichts zwischen den Schritten: Der Import schickt dieselbe Datei noch einmal
// und plant neu, das Ergebnis zählt also den Stand beim Schreiben und nicht den der Vorschau.

const TEXTE: Record<NetzwerkImportListe, { titel: string; zusatz: string }> = {
  zielfirmen: { titel: 'Zielfirmen aus Datei importieren', zusatz: '' },
  headhunter: { titel: 'Headhunter aus Datei importieren', zusatz: '' },
  kontakte: {
    titel: 'Netzwerk-Kontakte aus Datei importieren',
    zusatz: ' Auch die Datei Connections.csv aus dem LinkedIn-Datenexport können Sie verwenden.',
  },
}

// Anzeigenamen für „Ergänzt: …“. Maßgeblich sind die erkannten Spalten der Vorschau (Label vom
// Server); diese Liste fängt Felder ab, die der Server ableitet statt aus einer Spalte zu lesen
// (LinkedIn-Export: Kanal, Notizen).
const FELD_NAMEN: Record<string, string> = {
  company: 'Firma', industry: 'Branche', size_ma: 'Größe (MA)', revenue: 'Umsatz', location_hq: 'HQ',
  ownership: 'Eigentümer', tier: 'Tier', scenario: 'Szenario', key_contact: 'Key Contact',
  connection_status: 'Status', website: 'Webseite', karriere_url: 'Karriereseite',
  wachstumssignal: 'Wachstumssignal', ki_readiness: 'KI-Readiness', einschaetzung: 'Einschätzung',
  ranking: 'Ranking', last_update: 'Letzte Aktualisierung',
  firma: 'Firma', ansprechpartner: 'Ansprechpartner', fokus: 'Fokus', region: 'Region', kanal: 'Kanal',
  linkedin_gefolgt: 'LinkedIn gefolgt', letzter_kontakt: 'Letzter Kontakt', status: 'Status',
  webseite: 'Webseite', notizen: 'Notizen',
  name: 'Name', beziehung: 'Beziehung', unternehmen: 'Unternehmen', rolle: 'Rolle', prioritaet: 'Priorität',
  next_action: 'Nächste Aktion', next_action_date: 'Fällig am',
}

// Dashboard-Farbmodell (Style Guide v5 §18): dieselben Tokens wie die Status-Badges der Seite, Textfarbe
// je Fläche kontrastgeprüft. Fehler nimmt das Rot mit Weiß (4,58:1) statt status.negative (3,9:1).
// Die Farbe ist nie der einzige Träger: Badge und Zähler tragen immer den Klartext.
const AKTION: Record<NetzwerkImportAktion, { text: string; bg: string; fg: string }> = {
  neu: { text: 'Neu', bg: '#18A957', fg: TEXT_AUF_ZUSTAND },                  // status.positive
  ergaenzt: { text: 'Ergänzt', bg: '#00B4D8', fg: TEXT_AUF_ZUSTAND },         // status.active
  unveraendert: { text: 'Unverändert', bg: '#94A3B8', fg: TEXT_AUF_ZUSTAND }, // status.new
  geloescht: { text: 'Gelöscht', bg: '#E4A11B', fg: TEXT_AUF_ZUSTAND },       // status.parked
  fehler: { text: 'Fehler', bg: '#D9364F', fg: '#ffffff' },                   // score.1
}

const ZAEHLER: { aktion: NetzwerkImportAktion; label: string; hilfe: string }[] = [
  { aktion: 'neu', label: 'Neu', hilfe: 'werden angelegt' },
  { aktion: 'ergaenzt', label: 'Ergänzt', hilfe: 'leere Felder werden gefüllt' },
  { aktion: 'unveraendert', label: 'Unverändert', hilfe: 'vorhanden, nichts zu ergänzen' },
  { aktion: 'geloescht', label: 'Gelöscht, übersprungen', hilfe: 'in der App gelöscht, bleiben gelöscht' },
  { aktion: 'fehler', label: 'Fehler', hilfe: 'werden nicht importiert' },
]

const LINK = 'font-medium text-brand-navy underline decoration-brand-cyan underline-offset-2 hover:decoration-2'
const SEKUNDAER = 'rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40'

const zahl = (n: number) => n.toLocaleString('de-DE')

function groesse(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${zahl(Math.round(n / 1024))} KB`
  return `${(n / (1024 * 1024)).toLocaleString('de-DE', { maximumFractionDigits: 1 })} MB`
}

function formatText(v: NetzwerkImportVorschau): string {
  if (v.format === 'linkedin') return 'LinkedIn-Export (Connections.csv)'
  if (v.format === 'xlsx') return v.blatt ? `Excel-Datei, Blatt „${v.blatt}“` : 'Excel-Datei'
  return 'CSV-Datei'
}

// Teile einer Zahlenzeile ohne die Nullen: „12 angelegt, 3 ergänzt“.
function teile(paare: [number, string][]): string {
  return paare.filter(([n]) => n > 0).map(([n, text]) => `${zahl(n)} ${text}`).join(', ')
}

// Upload mit FormData, NICHT über api(): Das setzt den JSON-Kopf, den multipart nicht verträgt
// (Muster Profil.tsx). Der Fehlertext kommt aus `detail`, so wie der Server ihn für Kunden
// formuliert hat.
async function senden<T>(pfad: string, datei: File): Promise<T> {
  const fd = new FormData()
  fd.append('datei', datei)
  const { res, body } = await apiUpload(`/api/netzwerk-import/${pfad}`, fd)
  if (!res.ok) {
    throw new Error(typeof body?.detail === 'string' && body.detail
      ? body.detail
      : `Der Server hat die Datei nicht angenommen (Status ${res.status}).`)
  }
  if (!body?.anzahl) throw new Error('Der Server hat eine unerwartete Antwort geschickt.')
  return body as T
}

function fehlerText(e: unknown): string {
  // fetch wirft einen TypeError, wenn der Server nicht antwortet oder der Browser die Datei nicht
  // mehr lesen kann, weil sie nach der Auswahl geändert wurde (typisch: in Excel korrigiert).
  if (e instanceof TypeError) {
    return 'Die Anfrage ist fehlgeschlagen. Der Server antwortet nicht, oder die Datei wurde nach der Auswahl geändert. Wählen Sie die Datei dann erneut aus.'
  }
  return e instanceof Error && e.message ? e.message : 'Die Anfrage ist fehlgeschlagen.'
}

/** Nebenknopf für die Kopfzeile des Reiters: Rahmen statt Cyan-Fläche, sitzt links vom Anlege-Knopf. */
export function NetzwerkImportKnopf({ onClick }: { onClick: () => void }) {
  // ml-auto setzt den Knopf in der Kopfzeile (justify-between) an den rechten Rand, direkt links vom
  // Anlege-Knopf. mr-2 ist der Abstand zu diesem Nachbarn; fehlt er (sein Panel ist offen), entfällt
  // der Abstand (last:mr-0) und der Knopf schließt bündig ab.
  return (
    <button type="button" onClick={onClick}
      className="ml-auto mr-2 rounded-lg border border-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-navy last:mr-0 hover:bg-brand-cyan/10">
      <span aria-hidden="true">⇪</span> Aus Datei importieren
    </button>
  )
}

function AktionBadge({ aktion }: { aktion: NetzwerkImportAktion }) {
  const f = AKTION[aktion] || { text: String(aktion), bg: '#94A3B8', fg: TEXT_AUF_ZUSTAND }
  return (
    <span className="inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium" style={{ backgroundColor: f.bg, color: f.fg }}>
      {f.text}
    </span>
  )
}

function Zaehler({ anzahl }: { anzahl: NetzwerkImportAnzahl }) {
  return (
    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
      {ZAEHLER.map((z) => {
        const n = anzahl[z.aktion] ?? 0
        const fehler = z.aktion === 'fehler' && n > 0
        return (
          <div key={z.aktion} className={`rounded-lg border px-3 py-2 ${fehler ? 'border-rose-300 bg-rose-50' : 'border-slate-200 bg-white'}`}>
            <dt className="flex items-center gap-1.5 text-xs text-slate-500">
              <span aria-hidden="true" className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: AKTION[z.aktion].bg }} />
              {z.label}
            </dt>
            <dd className={`text-lg font-semibold tabular-nums ${fehler ? 'text-rose-700' : 'text-brand-navy'}`}>{zahl(n)}</dd>
            <dd className="text-xs text-slate-500">{z.hilfe}</dd>
          </div>
        )
      })}
    </dl>
  )
}

function ZeilenTabelle({ zeilen, labelVon }: { zeilen: NetzwerkImportZeile[]; labelVon: (feld: string) => string }) {
  // Ergänzte Felder und Meldung in einer Spalte: bei „Ergänzt“ ist beides wichtig (was und warum).
  const details = (z: NetzwerkImportZeile) => {
    const t: string[] = []
    if (z.aktion === 'ergaenzt' && z.felder_ergaenzt?.length) t.push(`Ergänzt: ${z.felder_ergaenzt.map(labelVon).join(', ')}`)
    const meldung = z.meldung || (z.aktion === 'geloescht' ? 'In der App gelöscht, wird nicht wieder angelegt.' : null)
    if (meldung) t.push(meldung)
    return t.join(' · ')
  }
  // Fehler und Gelöschtes zuerst: Diese Zeilen brauchen Aufmerksamkeit und würden sonst zwischen bis zu
  // 100 unauffälligen Zeilen untergehen. Innerhalb der Gruppen bleibt die Dateireihenfolge (sort ist stabil).
  const rang = (z: NetzwerkImportZeile) => (z.aktion === 'fehler' ? 0 : z.aktion === 'geloescht' ? 1 : 2)
  const geordnet = [...zeilen].sort((x, y) => rang(x) - rang(y))
  return (
    <div className="max-h-96 overflow-auto rounded-lg border border-slate-200 bg-white">
      <table className="w-full text-sm">
        <caption className="sr-only">Zeilen der Datei mit Aktion und Hinweis</caption>
        <thead className="sticky top-0 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th scope="col" className="px-3 py-2">Zeile</th>
            <th scope="col" className="px-3 py-2">Eintrag</th>
            <th scope="col" className="px-3 py-2">Aktion</th>
            <th scope="col" className="px-3 py-2">Hinweis</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {geordnet.map((z, i) => (
            <tr key={`${z.nr}-${i}`} className={`align-top ${z.aktion === 'fehler' ? 'bg-rose-50/60' : ''}`}>
              <td className="whitespace-nowrap px-3 py-1.5 tabular-nums text-slate-500">{z.nr}</td>
              <td className="px-3 py-1.5 font-medium text-brand-navy">{z.anzeige || <span className="font-normal text-slate-500">ohne Angabe</span>}</td>
              <td className="px-3 py-1.5"><AktionBadge aktion={z.aktion} /></td>
              <td className={`px-3 py-1.5 ${z.aktion === 'fehler' ? 'text-rose-700' : 'text-slate-600'}`}>{details(z)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function NetzwerkImport({ liste, onImportiert, onClose }: {
  liste: NetzwerkImportListe
  /** Nach geschriebenem Import: die Seite lädt ihre Liste neu. */
  onImportiert: () => void
  onClose: () => void
}) {
  const [datei, setDatei] = useState<File | null>(null)
  const [vorschau, setVorschau] = useState<NetzwerkImportVorschau | null>(null)
  const [ergebnis, setErgebnis] = useState<NetzwerkImportErgebnis | null>(null)
  const [busy, setBusy] = useState<'vorschau' | 'import' | null>(null)
  const [fehler, setFehler] = useState<string | null>(null)
  const lauf = useRef(0)          // verwirft die Antwort einer überholten Vorschau (zweite Datei gewählt)
  const schreibt = useRef(false)  // Doppelklick-Schutz, bevor der State neu gerendert hat
  const aktiv = useRef(true)      // false, sobald das Panel weg ist (Reiterwechsel mitten im Import)
  const schliessenRef = useRef<HTMLButtonElement>(null)
  const id = useId()
  const t = TEXTE[liste]

  // Der Importieren-Knopf, auf dem der Fokus lag, verschwindet mit dem Ergebnis: Fokus auf „Schließen“.
  useEffect(() => { if (ergebnis) schliessenRef.current?.focus() }, [ergebnis])
  // true im Effekt selbst: Der StrictMode spielt im Entwicklungsbetrieb Aufräumen und Neustart durch.
  useEffect(() => { aktiv.current = true; return () => { aktiv.current = false } }, [])

  const waehlen = async (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null
    // Auswahl leeren: Wer die Datei nach einer Korrektur erneut wählt, löst sonst kein change aus.
    e.target.value = ''
    if (!f) return
    const nr = ++lauf.current
    setDatei(f); setVorschau(null); setErgebnis(null); setFehler(null); setBusy('vorschau')
    try {
      const out = await senden<NetzwerkImportVorschau>(`${liste}/vorschau`, f)
      if (nr === lauf.current) setVorschau(out)
    } catch (err) {
      if (nr === lauf.current) setFehler(fehlerText(err))
    } finally {
      if (nr === lauf.current) setBusy(null)
    }
  }

  const importieren = async () => {
    if (!datei || schreibt.current) return
    schreibt.current = true
    setBusy('import'); setFehler(null)
    let out: NetzwerkImportErgebnis | null = null
    try {
      out = await senden<NetzwerkImportErgebnis>(liste, datei)
    } catch (err) {
      setFehler(fehlerText(err))
    } finally {
      schreibt.current = false
      setBusy(null)
    }
    if (!out) return
    setErgebnis(out)
    // Nach einem Reiterwechsel mitten im Import nicht mehr melden: Das Neuladen der Seite hängt am
    // Reiter von damals und würde dessen Zeilen in den neuen Reiter schreiben. Der neue Reiter lädt selbst.
    if (aktiv.current) onImportiert()
  }

  const a = vorschau?.anzahl
  const schreibbar = a ? a.neu + a.ergaenzt : 0
  const erkannt = vorschau?.spalten?.erkannt ?? []
  const ignoriert = vorschau?.spalten?.ignoriert ?? []
  const hinweise = vorschau?.hinweise ?? []
  const zeilen = vorschau?.zeilen ?? []
  const labelVon = (feld: string) => erkannt.find((s) => s.feld === feld)?.label || FELD_NAMEN[feld] || feld

  const ergebnisText = ergebnis
    ? (teile([[ergebnis.anzahl.neu, 'angelegt'], [ergebnis.anzahl.ergaenzt, 'ergänzt']]) || 'Nichts angelegt oder ergänzt') + '.'
    : ''
  const uebersprungen = ergebnis
    ? teile([[ergebnis.anzahl.unveraendert, 'unverändert'], [ergebnis.anzahl.geloescht, 'in der App gelöscht'], [ergebnis.anzahl.fehler, 'mit Fehlern']])
    : ''
  // Ein Bereich, der immer im DOM steht: Nur dann sagen Screenreader die Wechsel von „wird geprüft“
  // über „Vorschau bereit“ bis zum Ergebnis an.
  const ansage = busy === 'vorschau' ? 'Datei wird geprüft.'
    : busy === 'import' ? 'Import läuft.'
    : ergebnis ? `${ergebnisText}${ergebnis.sicherung ? ` Vorher gesichert: ${ergebnis.sicherung}.` : ''}`
    : a ? `Vorschau bereit: ${teile([[a.neu, 'neu'], [a.ergaenzt, 'ergänzt'], [a.unveraendert, 'unverändert'], [a.geloescht, 'gelöscht'], [a.fehler, 'Fehler']]) || 'keine Datenzeilen'}.`
    : ''

  return (
    <section aria-labelledby={`${id}-titel`} className="rounded-xl border border-brand-cyan/40 bg-brand-cyan/5 p-4">
      <h3 id={`${id}-titel`} className="mb-1 font-sans text-sm font-semibold text-brand-navy">{t.titel}</h3>
      {!ergebnis && (
        <p id={`${id}-info`} className="mb-3 text-xs text-slate-600">
          Laden Sie eine CSV- oder Excel-Datei hoch. Die Spalten werden an ihrer Überschrift erkannt.{t.zusatz}{' '}
          Zuerst sehen Sie eine Vorschau. Vorhandene Einträge werden nur um leere Felder ergänzt, in der App gelöschte bleiben gelöscht.
        </p>
      )}
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">{ansage}</div>

      {!ergebnis && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          {/* Die native Dateiauswahl bleibt für Tastatur und Screenreader erhalten, sichtbar ist das Label.
              So steht der Dateiname neben dem Knopf, auch wenn die Auswahl nach dem Lesen geleert wird. */}
          <input id={`${id}-datei`} type="file" accept=".csv,.txt,.xlsx" onChange={waehlen}
            disabled={busy === 'import'} autoFocus aria-describedby={`${id}-info`} className="peer sr-only" />
          <label htmlFor={`${id}-datei`}
            className="cursor-pointer rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-1 peer-focus-visible:outline-brand-navy peer-disabled:cursor-not-allowed peer-disabled:opacity-50">
            Datei auswählen
          </label>
          <span className="text-xs text-slate-600 [overflow-wrap:anywhere]">{datei ? `${datei.name} (${groesse(datei.size)})` : 'Keine Datei ausgewählt'}</span>
          <span className="text-xs text-slate-600">
            Vorlage:{' '}
            <a href={`/api/netzwerk-import/${liste}/vorlage?format=csv`} download aria-label="Vorlage als CSV-Datei herunterladen" className={LINK}>CSV</a>
            {' · '}
            <a href={`/api/netzwerk-import/${liste}/vorlage?format=xlsx`} download aria-label="Vorlage als Excel-Datei herunterladen" className={LINK}>Excel</a>
          </span>
        </div>
      )}

      {busy === 'vorschau' && <p className="mt-3 text-sm text-slate-500">Datei wird geprüft…</p>}
      {fehler && !vorschau && <p role="alert" className="mt-3 text-sm text-rose-700">{fehler}</p>}

      {vorschau && a && !ergebnis && (
        <div className="mt-4 space-y-3">
          <p className="text-sm text-slate-700">
            Erkannt: <span className="font-medium text-brand-navy">{formatText(vorschau)}</span>
            {' · '}{a.zeilen === 1 ? '1 Datenzeile' : `${zahl(a.zeilen)} Datenzeilen`}
          </p>

          <div>
            <div id={`${id}-erkannt`} className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Erkannte Spalten</div>
            {erkannt.length > 0 ? (
              <ul aria-labelledby={`${id}-erkannt`} className="flex flex-wrap gap-1.5">
                {erkannt.map((s, i) => (
                  <li key={`${s.spalte}-${i}`} className="rounded-full bg-white px-2 py-0.5 text-xs text-brand-navy ring-1 ring-brand-cyan/50">
                    {s.spalte.trim().toLowerCase() === s.label.toLowerCase() ? s.label : `${s.spalte} → ${s.label}`}
                  </li>
                ))}
              </ul>
            ) : <p className="text-xs text-slate-500">Keine Spalte erkannt.</p>}
            {ignoriert.length > 0 && (
              <div className="mt-2">
                <div id={`${id}-ignoriert`} className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Nicht verwendete Spalten</div>
                <ul aria-labelledby={`${id}-ignoriert`} className="flex flex-wrap gap-1.5">
                  {ignoriert.map((s, i) => <li key={`${s}-${i}`} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{s}</li>)}
                </ul>
              </div>
            )}
          </div>

          <Zaehler anzahl={a} />

          {hinweise.length > 0 && (
            <div role="note" className="rounded-lg border border-amber-300 bg-amber-50 p-2.5 text-xs text-amber-900">
              <ul className="space-y-1">{hinweise.map((h, i) => <li key={i}>{h}</li>)}</ul>
            </div>
          )}

          {a.zeilen === 0 ? (
            // Der Server nennt den Fall meist schon in den Hinweisen; ohne diesen Hinweis bliebe die Vorschau stumm.
            hinweise.length === 0 && <p className="text-sm text-slate-600">Die Datei enthält keine Datenzeilen. Tragen Sie Einträge unter der Kopfzeile ein.</p>
          ) : zeilen.length > 0 && (
            <div className="space-y-1">
              <ZeilenTabelle zeilen={zeilen} labelVon={labelVon} />
              {vorschau.zeilen_gekuerzt && <p className="text-xs text-slate-500">Weitere Zeilen ohne Besonderheiten sind nicht aufgeführt.</p>}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2">
            {/* Während des Imports nicht disabled: Ein deaktivierter Knopf verliert den Fokus, und nach einem
                Fehler säße er auf dem Seitenanfang. Gegen Doppelklick schützt `schreibt`. */}
            <button type="button" onClick={importieren} disabled={schreibbar === 0} aria-busy={busy === 'import'}
              className={`rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40 ${busy === 'import' ? 'cursor-wait opacity-60' : ''}`}>
              {busy === 'import' ? 'Sichert und importiert…' : `Importieren${schreibbar > 0 ? ` (${teile([[a.neu, 'neu'], [a.ergaenzt, 'ergänzen']])})` : ''}`}
            </button>
            <button type="button" onClick={onClose} disabled={busy === 'import'} className={SEKUNDAER}>Abbrechen</button>
            {schreibbar === 0 && a.zeilen > 0 && (
              <span className="text-xs text-slate-600">Es gibt nichts zu importieren: Alle Zeilen sind bereits vorhanden, in der App gelöscht oder fehlerhaft.</span>
            )}
            {schreibbar > 0 && a.fehler > 0 && (
              <span className="text-xs text-slate-600">Zeilen mit Fehlern werden nicht importiert.</span>
            )}
            {fehler && <p role="alert" className="basis-full text-sm text-rose-700">{fehler}</p>}
          </div>
        </div>
      )}

      {ergebnis && (
        <div className="mt-1 space-y-3">
          <div>
            <p className="text-sm text-emerald-700">
              <span aria-hidden="true">✓</span> {ergebnisText}
              {ergebnis.sicherung && <> Vorher gesichert: <code className="rounded bg-slate-100 px-1">{ergebnis.sicherung}</code></>}
            </p>
            {uebersprungen && <p className="mt-1 text-xs text-slate-500">Übersprungen: {uebersprungen}.</p>}
          </div>
          <button ref={schliessenRef} type="button" onClick={onClose} className={SEKUNDAER}>Schließen</button>
        </div>
      )}
    </section>
  )
}
