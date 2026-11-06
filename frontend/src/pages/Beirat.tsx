import { useEffect, useState } from 'react'
import { api, type BeiratMitglied } from '../api'
import { Trans } from 'react-i18next'
import BeiratLive from '../components/BeiratLive'
import { t } from '../i18n'

/** Bewerbungs-Beirat (18.07.2026) — live orchestrierte Debatte der 7 Köpfe.
 *  Der Vorsitz dispatcht autonom; jeder Zug kommt als SSE-Event
 *  (Moderation → Beitrag-Start → Token-Deltas → Beitrag-Ende → … → Synthese).
 *  Die Live-Ansicht selbst lebt in components/BeiratLive.tsx (Phase 40 — geteilt mit dem
 *  Stellen-Check in JobDetail, kein Fork). Diese Seite steuert nur Start-Formular + Archiv.
 *  P2-61: Seit die Seite wieder in der Seitenleiste steht, sehen Kunden sie. Deshalb Sie-Form,
 *  keine Dateipfade, und der Name des Vorsitzes kommt aus der Besetzung: Seit Phase 90 lässt er
 *  sich in den Einstellungen umhängen, ein fester Name wäre dann falsch. */

const INPUT = 'rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-cyan focus:outline-none'

/** P2-86: Welche KI in den Einstellungen gewählt ist. Sie bestimmt, wie der Abo-Motor heißt (Claude-Abo oder
 *  ChatGPT-Abo) und ob ein Anthropic-Key etwas bewirkt (nur unter Claude). Bis die Einstellung geladen ist, gilt Claude. */
type Ki = 'claude' | 'chatgpt'

function useKi(): Ki {
  const [ki, setKi] = useState<Ki>('claude')
  useEffect(() => {
    api<any>('/einstellungen').then((e) => setKi(e?.ki_anbieter === 'chatgpt' ? 'chatgpt' : 'claude')).catch(() => {})
  }, [])
  return ki
}

// ── Schlüssel-Panel ───────────────────────────────────────────────────────────────
function KeyPanel({ ki }: { ki: Ki }) {
  const [offen, setOffen] = useState(false)
  const [status, setStatus] = useState<any>(null)
  const [anthropic, setAnthropic] = useState('')
  const [openai, setOpenai] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  const laden = () => api('/beirat/keys').then(setStatus).catch(() => {})
  useEffect(() => { laden() }, [])
  const speichern = async () => {
    const body: any = {}
    if (anthropic) body.anthropic = anthropic
    if (openai) body.openai = openai
    const s = await api('/beirat/keys', { method: 'POST', body: JSON.stringify(body) })
    setStatus(s); setAnthropic(''); setOpenai(''); setMsg(t('beirat:schluessel.gespeichert'))
    setTimeout(() => setMsg(null), 5000)
  }
  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <button onClick={() => setOffen(!offen)} className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-slate-600 hover:text-slate-800">
        <span className="text-slate-400">{offen ? '▾' : '▸'}</span><span className="font-medium">{t('beirat:schluessel.titel')}</span>
        {status && (
          <span className="ml-2 flex gap-2 text-xs">
            <span className={`rounded-full px-2 py-0.5 ${status.cli_verfuegbar ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
              {t(`beirat:schluessel.abo_${ki === 'chatgpt' ? 'chatgpt' : 'claude'}_${status.cli_verfuegbar ? 'ok' : 'fehlt'}`)}</span>
            {ki === 'claude' && (
              <span className={`rounded-full px-2 py-0.5 ${status.anthropic_gesetzt ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                {status.anthropic_gesetzt ? t('beirat:schluessel.anthropic_gesetzt', { maske: status.anthropic_maske }) : t('beirat:schluessel.anthropic_leer')}</span>
            )}
            <span className={`rounded-full px-2 py-0.5 ${status.openai_gesetzt ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
              {status.openai_gesetzt ? t('beirat:schluessel.openai_gesetzt', { maske: status.openai_maske }) : t('beirat:schluessel.openai_leer')}</span>
          </span>
        )}
      </button>
      {offen && (
        <div className="space-y-2 border-t border-slate-100 p-4 text-sm">
          {ki === 'chatgpt' ? (
            <p className="text-xs text-slate-500"><Trans i18nKey="beirat:schluessel.text_chatgpt" components={{ b: <b /> }} /></p>
          ) : (
            <p className="text-xs text-slate-500"><Trans i18nKey="beirat:schluessel.text_claude" components={{ b: <b /> }} /></p>
          )}
          <div className="grid gap-2 md:grid-cols-2">
            {ki === 'claude' && (
              <input type="password" className={INPUT} placeholder={t('beirat:schluessel.placeholder_anthropic')} value={anthropic} onChange={(e) => setAnthropic(e.target.value)} />
            )}
            <input type="password" className={INPUT} placeholder={t('beirat:schluessel.placeholder_openai')} value={openai} onChange={(e) => setOpenai(e.target.value)} />
          </div>
          <div className="flex items-center gap-3">
            <button onClick={speichern} className="rounded-lg bg-brand-cyan px-3 py-1.5 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover">{t('beirat:schluessel.speichern')}</button>
            {msg && <span className="text-xs text-emerald-600">{msg}</span>}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Hauptseite ────────────────────────────────────────────────────────────────────
export default function Beirat() {
  const ki = useKi()
  const [mitglieder, setMitglieder] = useState<BeiratMitglied[]>([])
  const [thema, setThema] = useState('')
  const [kontext, setKontext] = useState('')
  const [minB, setMinB] = useState(10)
  const [provider, setProvider] = useState<'anthropic' | 'openai'>('anthropic')
  const [auswahl, setAuswahl] = useState<Record<string, boolean>>({})
  const [alleKoepfe, setAlleKoepfe] = useState(true)

  const [debatteId, setDebatteId] = useState<string | null>(null)
  const [laeuft, setLaeuft] = useState(false)
  const [fortschritt, setFortschritt] = useState<{ nr: number; min: number; max: number } | null>(null)
  const [fehler, setFehler] = useState<string | null>(null)
  const [archiv, setArchiv] = useState<any[]>([])

  useEffect(() => {
    api<BeiratMitglied[]>('/beirat/mitglieder').then(setMitglieder).catch(() => {})
    api('/beirat/debatten').then(setArchiv).catch(() => {})
  }, [])
  // Bis die Besetzung geladen ist (oder falls sie nicht lädt), steht dort die Rolle statt eines Namens.
  const vorsitz = mitglieder.find((m) => m.vorsitz)?.anzeige

  const starten = async () => {
    setFehler(null); setFortschritt(null)
    try {
      const teilnehmer = alleKoepfe ? null : Object.keys(auswahl).filter((k) => auswahl[k])
      if (teilnehmer && teilnehmer.length < 2) { setFehler(t('beirat:formular.mind_zwei', { vorsitz: vorsitz ?? t('beirat:vorsitz.den') })); return }
      const r = await api<any>('/beirat/debatten', {
        method: 'POST',
        body: JSON.stringify({ thema, kontext, min_beitraege: minB, provider, teilnehmer }),
      })
      setDebatteId(r.id); setLaeuft(true)
    } catch (e: any) { setFehler(e?.message || t('beirat:start_fehlgeschlagen')) }
  }

  const stoppen = async () => { if (debatteId) await api(`/beirat/debatten/${debatteId}/stop`, { method: 'POST' }).catch(() => {}) }

  const archivOeffnen = (id: string) => { setFehler(null); setDebatteId(id); setLaeuft(false) }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">{t('beirat:seite.titel')}</h1>
        <p className="text-sm text-slate-500">{t('beirat:seite.einleitung', { vorsitz: vorsitz ?? t('beirat:vorsitz.der') })}</p>
      </div>

      <KeyPanel ki={ki} />

      {/* Start-Formular */}
      <div className="rounded-xl border border-brand-cyan/40 bg-brand-cyan/5 p-4">
        <div className="mb-2 text-sm font-semibold text-brand-navy">{t('beirat:formular.titel')}</div>
        <div className="space-y-2">
          <input className={`${INPUT} w-full`} placeholder={t('beirat:formular.thema_placeholder')} value={thema} onChange={(e) => setThema(e.target.value)} disabled={laeuft} />
          <textarea className={`${INPUT} w-full`} rows={3} placeholder={t('beirat:formular.kontext_placeholder')} value={kontext} onChange={(e) => setKontext(e.target.value)} disabled={laeuft} />
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <label className="flex items-center gap-2">{t('beirat:formular.min_beitraege')}
              <select className={INPUT} value={minB} onChange={(e) => setMinB(Number(e.target.value))} disabled={laeuft}>
                {[6, 10, 20, 30].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <label className="flex items-center gap-2">{t('beirat:formular.motor')}
              <select className={INPUT} value={provider} onChange={(e) => setProvider(e.target.value as any)} disabled={laeuft}>
                <option value="anthropic">{ki === 'chatgpt' ? t('beirat:formular.motor_chatgpt') : t('beirat:formular.motor_claude')}</option>
                <option value="openai">{t('beirat:formular.motor_openai')}</option>
              </select>
            </label>
            {ki === 'chatgpt' && provider === 'anthropic' && (
              <span className="text-xs text-slate-500">{t('beirat:formular.chatgpt_hinweis')}</span>
            )}
            <label className="flex items-center gap-2 text-slate-600">
              <input type="checkbox" checked={alleKoepfe} onChange={(e) => setAlleKoepfe(e.target.checked)} disabled={laeuft} />
              {t('beirat:formular.vorsitz_waehlt', { vorsitz: vorsitz ?? t('beirat:vorsitz.der') })}
            </label>
          </div>
          {!alleKoepfe && (
            <div className="flex flex-wrap gap-2">
              {mitglieder.map((m) => (
                <label key={m.id} title={m.beschreibung}
                  className={`flex cursor-pointer items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${auswahl[m.id] ? 'border-transparent text-white' : 'border-slate-300 bg-white text-slate-600'}`}
                  style={auswahl[m.id] ? { backgroundColor: m.farbe } : undefined}>
                  <input type="checkbox" className="hidden" checked={!!auswahl[m.id]}
                    onChange={(e) => setAuswahl((a) => ({ ...a, [m.id]: e.target.checked }))} />
                  {m.anzeige}
                </label>
              ))}
            </div>
          )}
          <div className="flex items-center gap-2">
            <button onClick={starten} disabled={laeuft || !thema.trim()}
              className="rounded-lg bg-brand-cyan px-4 py-2 text-sm font-medium text-brand-aufAktion hover:bg-brand-cyanHover disabled:opacity-40">
              {laeuft ? t('beirat:formular.laeuft') : t('beirat:formular.starten')}
            </button>
            {laeuft && <button onClick={stoppen} className="rounded-lg border border-rose-300 px-3 py-2 text-sm text-rose-600 hover:bg-rose-50">{t('beirat:formular.stoppen')}</button>}
            {fortschritt && laeuft && (
              <span className="text-sm text-slate-500"><Trans i18nKey="beirat:fortschritt" values={{ nr: fortschritt.nr, min: fortschritt.min, max: fortschritt.max }} components={{ b: <b /> }} /></span>
            )}
            {fehler && <span className="text-sm text-rose-600">{fehler}</span>}
          </div>
        </div>
      </div>

      {/* Live-Debatte (geteilte Komponente, Phase 40) */}
      {debatteId && (
        <BeiratLive
          debatteId={debatteId}
          onFortschritt={setFortschritt}
          onFertig={() => { setLaeuft(false); api('/beirat/debatten').then(setArchiv).catch(() => {}) }}
          onFehler={(m) => { setFehler(m); setLaeuft(false) }}
        />
      )}

      {/* Archiv */}
      {archiv.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 px-4 py-2.5 text-sm font-semibold text-brand-navy">{t('beirat:archiv.titel')}</div>
          <div className="divide-y divide-slate-100">
            {archiv.map((d) => (
              <button key={d.id} onClick={() => archivOeffnen(d.id)} className="flex w-full items-center justify-between gap-3 px-4 py-2 text-left hover:bg-slate-50">
                <span className="min-w-0 truncate text-sm text-slate-700">{d.thema}</span>
                <span className="flex shrink-0 items-center gap-2 text-xs text-slate-400">
                  <span>{t('beirat:archiv.beitraege', { count: d.beitraege })}</span>
                  <span className={`rounded-full px-2 py-0.5 ${d.status === 'fertig' ? 'bg-emerald-100 text-emerald-700' : d.status === 'fehler' ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700'}`}>{d.status ? t(`beirat:wert.${d.status}`, { defaultValue: d.status }) : d.status}</span>
                  <span>{String(d.gestartet || '').slice(0, 16).replace('T', ' ')}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
