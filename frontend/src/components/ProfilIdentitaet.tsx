import { useEffect, useState } from 'react'
import {
  api, ApiError,
  type ProfilFeld, type ProfilIdentitaetAntwort, type ProfilIdentitaetBody, type ProfilIdentitaetInhalt,
} from '../api'
import { PROFIL_GEAENDERT } from '../profil'
import { t } from '../i18n'

// P2-69: Karte „Identität und Suchstrategie“ — liest und schreibt config/profil.md über
// GET/PUT /api/profil/identitaet (Vertrag A der Bau-Spec). Die Datei bleibt die einzige Quelle;
// der Server ändert nur, was die Karte zeigt, alles andere bleibt in der Datei stehen. Die Karte
// sendet deshalb bewusst nichts „aufgeräumt“ zurück (kein Trimmen, keine neuen Zeilenenden), damit
// ein unverändertes Feld auch unverändert bleibt.

// Gleiche Eingabefelder wie auf der übrigen Profil-Seite (pages/Profil.tsx::INPUT).
const INPUT = 'rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand-cyan focus:outline-none'

const KURZE_FELDER = ['name', 'positionierung', 'anschrift', 'email', 'telefon', 'linkedin', 'aktuell'] as const
const FREITEXT_FELDER = ['kurzprofil', 'rahmenbedingungen', 'skill_gaps'] as const

// ── Reine Logik (ohne React; mit esbuild/node prüfbar) ───────────────────────────────────

/** Arbeitskopie der Antwort für die Eingabefelder (tief kopiert, damit die Antwort unberührt bleibt). */
export function formularAus(a: ProfilIdentitaetInhalt): ProfilIdentitaetInhalt {
  const kopie = (liste: ProfilFeld[] | undefined): ProfilFeld[] =>
    (liste || []).map((f) => ({ schluessel: f.schluessel, wert: f.wert ?? '' }))
  const i = a.identitaet || ({} as ProfilIdentitaetInhalt['identitaet'])
  return {
    identitaet: {
      name: i.name ?? '', positionierung: i.positionierung ?? '', anschrift: i.anschrift ?? '',
      email: i.email ?? '', telefon: i.telefon ?? '', linkedin: i.linkedin ?? '', aktuell: i.aktuell ?? '',
      weitere: kopie(i.weitere),
    },
    kurzprofil: a.kurzprofil ?? '',
    zielrolle: kopie(a.zielrolle),
    rahmenbedingungen: a.rahmenbedingungen ?? '',
    skill_gaps: a.skill_gaps ?? '',
  }
}

/** Zeilenenden vereinheitlichen: Ein Textfeld liefert immer \n, die Datei kann \r\n tragen. */
function zeilenende(text: string): string {
  return text.replace(/\r\n?/g, '\n')
}

function felderGeaendert(neu: ProfilFeld[], alt: ProfilFeld[]): boolean {
  return neu.length !== alt.length || neu.some((f, n) => f.wert !== alt[n].wert)
}

/** Weicht die Eingabe vom zuletzt geladenen/gespeicherten Stand ab? Steuert den Speichern-Knopf. */
export function istGeaendert(form: ProfilIdentitaetInhalt, basis: ProfilIdentitaetInhalt): boolean {
  return (
    KURZE_FELDER.some((k) => form.identitaet[k] !== basis.identitaet[k]) ||
    felderGeaendert(form.identitaet.weitere, basis.identitaet.weitere) ||
    felderGeaendert(form.zielrolle, basis.zielrolle) ||
    FREITEXT_FELDER.some((k) => zeilenende(form[k]) !== zeilenende(basis[k]))
  )
}

/** Ein Freitext, der nur in den Zeilenenden abweicht, geht unverändert zurück (verlustfrei). */
function freitextFuer(neu: string, alt: string): string {
  return zeilenende(neu) === zeilenende(alt) ? alt : zeilenende(neu)
}

/** PUT-Body (Vertrag A): `stand` der letzten Antwort plus der bearbeitbare Teil. Die Schlüssel der
 *  Listenfelder bleiben, wie der Server sie geliefert hat — die Karte ändert nur die Werte. */
export function bodyAus(stand: string, form: ProfilIdentitaetInhalt, basis: ProfilIdentitaetInhalt): ProfilIdentitaetBody {
  const felder = (liste: ProfilFeld[]) => liste.map((f) => ({ schluessel: f.schluessel, wert: f.wert }))
  const i = form.identitaet
  return {
    stand,
    identitaet: {
      name: i.name, positionierung: i.positionierung, anschrift: i.anschrift, email: i.email,
      telefon: i.telefon, linkedin: i.linkedin, aktuell: i.aktuell, weitere: felder(i.weitere),
    },
    kurzprofil: freitextFuer(form.kurzprofil, basis.kurzprofil),
    zielrolle: felder(form.zielrolle),
    rahmenbedingungen: freitextFuer(form.rahmenbedingungen, basis.rahmenbedingungen),
    skill_gaps: freitextFuer(form.skill_gaps, basis.skill_gaps),
  }
}

export type HinweisBereich = 'anschrift' | 'email' | 'allgemein'

/** Die Hinweise des Servers sind Klartext ohne Feldbezug; zugeordnet wird nach Stichwort, damit sie
 *  unter dem betroffenen Feld stehen. Was nicht passt, steht unter den Kurzfeldern. */
export function hinweisBereich(text: string): HinweisBereich {
  if (/ortszeile|anschrift|address line/i.test(text)) return 'anschrift'
  if (/e-?mail/i.test(text)) return 'email'
  return 'allgemein'
}

/** Hinweise des Servers gelten für den gespeicherten Stand. Sobald Anschrift oder E-Mail bearbeitet
 *  werden, verschwindet der zugehörige Hinweis, bis der neue Stand gespeichert und neu geprüft ist. */
export function sichtbareHinweise(basis: ProfilIdentitaetAntwort, form: ProfilIdentitaetInhalt, bereich: HinweisBereich): string[] {
  if (bereich === 'anschrift' && form.identitaet.anschrift !== basis.identitaet.anschrift) return []
  if (bereich === 'email' && form.identitaet.email !== basis.identitaet.email) return []
  return (basis.hinweise || []).filter((h) => hinweisBereich(h) === bereich)
}

/** Fußzeile der Karte: was die Karte nicht anfasst bzw. dass die Datei erst entsteht. */
export function fusszeile(a: Pick<ProfilIdentitaetAntwort, 'vorhanden' | 'unveraendert'>): string {
  if (!a.vorhanden) return t('profil:karte.fusszeile_leer')
  return a.unveraendert && a.unveraendert.length > 0 ? t('profil:karte.fusszeile_unveraendert', { felder: a.unveraendert.join(', ') }) : ''
}

/** Klartext aus `detail` der Server-Antwort (der Server formuliert die Kundentexte selbst). Ist kein
 *  brauchbarer Text da, etwa weil FastAPI bei einem Formatfehler eine Liste liefert, gilt `ersatz`. */
export function serverText(e: { message?: string }, ersatz: string): string {
  const t = (e.message || '').trim()
  return t && !t.includes('[object') ? t : ersatz
}

// ── Darstellung ──────────────────────────────────────────────────────────────────────────
/** Ein Eingabefeld mit Beschriftung darüber (Muster: Werdegang, `Lab`) und optionalen Hinweiszeilen
 *  darunter. Bewusst auf Modulebene: Würde die Komponente innerhalb von `ProfilIdentitaetAnsicht`
 *  stehen, baute React sie bei jedem Tastendruck neu und das Feld verlöre den Fokus. */
function Feld({ label, value, onChange, placeholder, hinweise, fehler, spanZwei }: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  hinweise?: string[]
  fehler?: string
  spanZwei?: boolean
}) {
  return (
    <div className={spanZwei ? 'md:col-span-2' : ''}>
      <label className="flex flex-col text-xs text-slate-500">
        {label}
        <input type="text" className={`${INPUT} mt-1 w-full`} placeholder={placeholder}
          value={value} onChange={(e) => onChange(e.target.value)} />
      </label>
      {fehler && <div className="mt-1 text-xs text-rose-600">{fehler}</div>}
      {hinweise && hinweise.length > 0 && (
        <div className="mt-1 space-y-1">
          {hinweise.map((h) => <div key={h} className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">{h}</div>)}
        </div>
      )}
    </div>
  )
}

/** Freitext-Bereich: Überschrift, Hinweis und Textfeld in einem Label. */
function TextBereich({ titel, hinweis, value, onChange, rows, placeholder }: {
  titel: string
  hinweis?: string
  value: string
  onChange: (v: string) => void
  rows: number
  placeholder?: string
}) {
  return (
    <label className="mt-4 block border-t border-slate-100 pt-3">
      <span className="block text-xs font-semibold text-brand-navy">{titel}</span>
      {hinweis && <span className="mt-0.5 block text-xs text-slate-400">{hinweis}</span>}
      <textarea className={`${INPUT} mt-1.5 w-full resize-y`} rows={rows} placeholder={placeholder}
        value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  )
}

export type KartenFehler = { art: 'eingabe' | 'stand' | 'sonst'; text: string; zusatz?: string }

export interface AnsichtProps {
  /** Letzte Antwort des Servers (Stand, vorhanden, Hinweise, Fußzeilen-Liste). */
  basis: ProfilIdentitaetAntwort
  form: ProfilIdentitaetInhalt
  onForm: (f: ProfilIdentitaetInhalt) => void
  saving: boolean
  saved: boolean
  fehler: KartenFehler | null
  neuLadend: boolean
  onSpeichern: () => void
  onNeuLaden: () => void
}

/** Die Karte selbst, ohne eigene Zustände und ohne Netz — so lässt sie sich mit fertigen Daten
 *  rendern und prüfen. */
export function ProfilIdentitaetAnsicht({
  basis, form, onForm, saving, saved, fehler, neuLadend, onSpeichern, onNeuLaden,
}: AnsichtProps) {
  const i = form.identitaet
  const geaendert = istGeaendert(form, basis)
  const nameLeer = i.name.trim() === ''
  // Ein leerer Name ist erst dann ein Fehler, wenn er etwas überschreibt oder schon getippt wurde;
  // die frische, leere Karte (Datei fehlt) soll nicht gleich rot sein.
  const nameFehler = nameLeer && (basis.vorhanden || geaendert) ? t('profil:karte.name_pflicht') : undefined

  const hinweise = (bereich: HinweisBereich) => sichtbareHinweise(basis, form, bereich)

  const setIdent = (k: (typeof KURZE_FELDER)[number], v: string) => onForm({ ...form, identitaet: { ...i, [k]: v } })
  const setListe = (art: 'weitere' | 'zielrolle', n: number, v: string) => {
    const setze = (liste: ProfilFeld[]) => liste.map((f, m) => (m === n ? { ...f, wert: v } : f))
    onForm(art === 'weitere'
      ? { ...form, identitaet: { ...i, weitere: setze(i.weitere) } }
      : { ...form, zielrolle: setze(form.zielrolle) })
  }
  const fuss = fusszeile(basis)

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 text-sm font-semibold text-brand-navy">{t('profil:karte.titel')}</div>
      <p className="mb-3 text-xs text-slate-500">
        {t('profil:karte.hinweis')}
      </p>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Feld label={t('profil:karte.name')} value={i.name} placeholder={t('profil:karte.name_platzhalter')} fehler={nameFehler}
          onChange={(v) => setIdent('name', v)} />
        <Feld label={t('profil:karte.anschrift')} value={i.anschrift} placeholder={t('profil:karte.anschrift_platzhalter')}
          hinweise={hinweise('anschrift')} onChange={(v) => setIdent('anschrift', v)} />
        <Feld label={t('profil:karte.positionierung')} value={i.positionierung} spanZwei
          placeholder={t('profil:karte.positionierung_platzhalter')}
          onChange={(v) => setIdent('positionierung', v)} />
        <Feld label={t('profil:karte.email')} value={i.email} placeholder={t('profil:karte.email_platzhalter')}
          hinweise={hinweise('email')} onChange={(v) => setIdent('email', v)} />
        <Feld label={t('profil:karte.telefon')} value={i.telefon} placeholder="+49 170 1234567"
          onChange={(v) => setIdent('telefon', v)} />
        <Feld label="LinkedIn" value={i.linkedin} placeholder="https://www.linkedin.com/in/…" /* i18n-ok: Eigenname, URL */
          onChange={(v) => setIdent('linkedin', v)} />
        <Feld label={t('profil:karte.aktuell')} value={i.aktuell} placeholder={t('profil:karte.aktuell_platzhalter')}
          onChange={(v) => setIdent('aktuell', v)} />
        {i.weitere.map((f, n) => (
          <Feld key={`weitere-${n}-${f.schluessel}`} label={f.schluessel} value={f.wert}
            onChange={(v) => setListe('weitere', n, v)} />
        ))}
      </div>
      {hinweise('allgemein').length > 0 && (
        <div className="mt-2 space-y-1">
          {hinweise('allgemein').map((h) => <div key={h} className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">{h}</div>)}
        </div>
      )}

      <TextBereich titel={t('profil:karte.kurzprofil')} rows={4} value={form.kurzprofil}
        placeholder={t('profil:karte.kurzprofil_platzhalter')}
        onChange={(v) => onForm({ ...form, kurzprofil: v })} />

      {form.zielrolle.length > 0 && (
        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
          {form.zielrolle.map((f, n) => (
            <Feld key={`zielrolle-${n}-${f.schluessel}`} label={f.schluessel} value={f.wert}
              placeholder={t('profil:karte.zielrolle_platzhalter')} onChange={(v) => setListe('zielrolle', n, v)} />
          ))}
        </div>
      )}

      <TextBereich titel={t('profil:karte.rahmen')} rows={4} value={form.rahmenbedingungen}
        hinweis={t('profil:karte.listenhinweis')}
        placeholder={t('profil:karte.rahmen_platzhalter')}
        onChange={(v) => onForm({ ...form, rahmenbedingungen: v })} />

      <TextBereich titel={t('profil:karte.gaps')} rows={3} value={form.skill_gaps}
        hinweis={t('profil:karte.listenhinweis')}
        placeholder={t('profil:karte.gaps_platzhalter')}
        onChange={(v) => onForm({ ...form, skill_gaps: v })} />

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
        <button onClick={onSpeichern} disabled={saving || !geaendert || nameLeer}
          className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? t('profil:aktion.speichert') : t('profil:aktion.speichern')}
        </button>
        {saved && <span className="text-sm text-emerald-600">{t('profil:aktion.gespeichert')}</span>}
      </div>

      {fehler && fehler.art !== 'stand' && (
        <div role="alert" className="mt-2 rounded-lg bg-rose-50 p-2 text-xs text-rose-700">{fehler.text}</div>
      )}
      {fehler && fehler.art === 'stand' && (
        <div role="alert" className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
          <div>{fehler.text}</div>
          {fehler.zusatz && <div className="mt-1">{fehler.zusatz}</div>}
          <button onClick={onNeuLaden} disabled={neuLadend}
            className="mt-1.5 rounded-lg border border-amber-300 bg-white px-3 py-1 text-xs font-medium text-amber-900 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50">
            {neuLadend ? t('profil:karte.neu_ladend') : t('profil:karte.neu_laden')}
          </button>
        </div>
      )}

      {fuss && <p className="mt-3 text-xs text-slate-400">{fuss}</p>}
    </div>
  )
}

// ── Karte mit Laden und Speichern ────────────────────────────────────────────────────────
export default function ProfilIdentitaet() {
  const [basis, setBasis] = useState<ProfilIdentitaetAntwort | null>(null)
  const [form, setForm] = useState<ProfilIdentitaetInhalt | null>(null)
  const [laedt, setLaedt] = useState(true)
  const [ladeFehler, setLadeFehler] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [fehler, setFehler] = useState<KartenFehler | null>(null)
  const [neuLadend, setNeuLadend] = useState(false)

  const uebernehmen = (a: ProfilIdentitaetAntwort) => { setBasis(a); setForm(formularAus(a)) }
  const holen = () => api<ProfilIdentitaetAntwort>('/profil/identitaet')

  const erstesLaden = async () => {
    setLaedt(true); setLadeFehler(null)
    try { uebernehmen(await holen()) }
    catch (e: any) { setLadeFehler(e instanceof ApiError ? serverText(e, t('profil:karte.status_code', { status: e.status })) : t('profil:karte.fehler_nicht_erreichbar')) }
    finally { setLaedt(false) }
  }
  useEffect(() => { erstesLaden() }, [])

  const speichern = async () => {
    if (!basis || !form) return
    setSaving(true); setFehler(null); setSaved(false)
    try {
      const a = await api<ProfilIdentitaetAntwort>('/profil/identitaet', {
        method: 'PUT', body: JSON.stringify(bodyAus(basis.stand, form, basis)),
      })
      uebernehmen(a)
      // Seitenleiste (Name) und Routenplanung (Anschrift) laden ihre Werte neu.
      window.dispatchEvent(new Event(PROFIL_GEAENDERT))
      setSaved(true); setTimeout(() => setSaved(false), 2000)
    } catch (e: any) {
      if (e instanceof ApiError) {
        if (e.status === 409) setFehler({ art: 'stand', text: serverText(e, t('profil:karte.fehler_stand')) })
        else if (e.status === 400) setFehler({ art: 'eingabe', text: serverText(e, t('profil:karte.fehler_eingabe')) })
        else setFehler({ art: 'sonst', text: serverText(e, t('profil:karte.fehler_speichern_status', { status: e.status })) })
      } else {
        setFehler({ art: 'sonst', text: t('profil:karte.fehler_speichern_server') })
      }
    } finally { setSaving(false) }
  }

  // Erst hier werden die lokalen Eingaben verworfen — nach dem 409 bleiben sie stehen, damit sie
  // sich vorher noch kopieren lassen.
  const neuLaden = async () => {
    setNeuLadend(true)
    try {
      uebernehmen(await holen())
      setFehler(null); setSaved(false)
    } catch {
      setFehler((f) => (f ? { ...f, zusatz: t('profil:karte.fehler_neu_laden') } : f))
    } finally { setNeuLadend(false) }
  }

  if (!basis || !form) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-2 text-sm font-semibold text-brand-navy">{t('profil:karte.titel')}</div>
        {laedt && <div className="text-sm text-slate-400">{t('profil:aktion.lade')}</div>}
        {!laedt && ladeFehler && (
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
            <span>{t('profil:karte.laden_fehler', { fehler: ladeFehler })}</span>
            <button onClick={erstesLaden}
              className="rounded-lg border border-slate-300 px-3 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50">
              {t('profil:karte.erneut')}
            </button>
          </div>
        )}
      </div>
    )
  }

  return (
    <ProfilIdentitaetAnsicht basis={basis} form={form} onForm={setForm} saving={saving} saved={saved}
      fehler={fehler} neuLadend={neuLadend} onSpeichern={speichern} onNeuLaden={neuLaden} />
  )
}
