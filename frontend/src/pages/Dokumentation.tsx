import { useEffect, useState } from 'react'
import { api, type DokuEintrag, type VersionInfo } from '../api'
import { t } from '../i18n'

// P2-59: Dokumentationsseite im Muster von Rechtliches.tsx (Tabs), aber ohne eigenen
// Markdown-Renderer: Das Backend rendert die Dokumente dieser Installation mit demselben
// Renderer wie die HTML-Dateien in docs/ (GET /api/doku/<id>, backend/app/doku.py), und die
// Seite steht in einem Rahmen. Welche Tabs es gibt, entscheidet die Installation: Das
// Kundenpaket enthält die internen Dokumente nicht, also fehlen ihre Tabs dort von selbst.
//
// Der Rahmen läuft in einer Sandbox (Gedanke wie bei den Berichten, P2-58): ohne
// allow-same-origin hat das Dokument einen eigenen Ursprung und erreicht die API nicht, ohne
// allow-scripts läuft darin kein Skript. allow-popups lässt Webadressen in einem neuen Tab
// öffnen, und allow-popups-to-escape-sandbox sorgt dafür, dass dieser Tab eine normale Seite
// ist und nicht selbst in der Sandbox steckt. Die Rechte nicht erweitern: Ein allow-same-origin
// zusammen mit Skripten höbe die Sandbox auf (tests/test_doku.py hält das fest). Der Server
// schickt dieselbe Sandbox zusätzlich als Kopf mit, sie gilt also auch beim direkten Öffnen.

// Zeile über dem Rahmen im Tab „Version“: die laufende Version aus GET /api/version, bei einer
// Git-Installation zusätzlich der Entwicklungsstand (dort gilt keine feste Version).
function InstalliertZeile({ info, fehler }: { info: VersionInfo | null; fehler: boolean }) {
  if (fehler) return <span className="text-sm text-slate-400">{t('doku:version_fehler')}</span>
  if (!info) return null
  const bekannt = !!info.version && info.version !== '0.0.0'
  return (
    <span className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
      <span className="text-sm font-semibold text-brand-navy">
        {bekannt ? t('doku:installiert_version', { version: info.version }) : t('doku:installiert_keine')}
      </span>
      {info.installation === 'git' && info.entwicklungsstand && (
        <span className="text-xs text-slate-500">{t('common:layout.entwicklungsstand', { stand: info.entwicklungsstand })}</span>
      )}
    </span>
  )
}

export default function Dokumentation() {
  const [liste, setListe] = useState<DokuEintrag[] | null>(null)
  const [ladeFehler, setLadeFehler] = useState(false)
  const [aktivId, setAktivId] = useState('')
  const [version, setVersion] = useState<VersionInfo | null>(null)
  const [versionFehler, setVersionFehler] = useState(false)

  useEffect(() => {
    api<DokuEintrag[]>('/doku')
      .then((d) => { setListe(d); setLadeFehler(false) })
      .catch(() => setLadeFehler(true))
    api<VersionInfo>('/version')
      .then((d) => { setVersion(d); setVersionFehler(false) })
      .catch(() => setVersionFehler(true))
  }, [])

  const eintraege = liste ?? []
  const kunde = eintraege.filter((e) => e.gruppe !== 'intern')
  const intern = eintraege.filter((e) => e.gruppe === 'intern')
  const aktiv = eintraege.find((e) => e.id === aktivId) ?? kunde[0] ?? intern[0] ?? null

  const tab = (e: DokuEintrag) => (
    <button key={e.id} onClick={() => setAktivId(e.id)} aria-current={aktiv?.id === e.id ? 'true' : undefined}
      className={`rounded-t-lg px-4 py-2 text-sm font-medium ${
        aktiv?.id === e.id ? 'border-b-2 border-brand-cyan text-brand-navy' : 'text-slate-500 hover:text-slate-700'
      }`}>
      {e.titel}
    </button>
  )

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">{t('doku:titel')}</h1>
        <p className="text-sm text-slate-500">
          {t('doku:einleitung')}
        </p>
      </div>

      {ladeFehler && (
        <p className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {t('doku:lade_fehler')}
        </p>
      )}
      {liste === null && !ladeFehler && <p className="text-sm text-slate-400">{t('doku:laden')}</p>}
      {liste !== null && !aktiv && <p className="text-sm text-slate-500">{t('doku:leer')}</p>}

      {aktiv && (
        <>
          <div className="flex flex-wrap gap-1 border-b border-slate-200">
            {kunde.map(tab)}
            {intern.length > 0 && (
              <span className="ml-2 self-center border-l border-slate-200 pl-3 pr-1 text-[11px] font-medium uppercase tracking-wide text-slate-400">
                {t('doku:intern')}
              </span>
            )}
            {intern.map(tab)}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
            {aktiv.id === 'version' && <InstalliertZeile info={version} fehler={versionFehler} />}
            <a href={`/api/doku/${encodeURIComponent(aktiv.id)}`} target="_blank" rel="noopener"
              className="ml-auto text-sm text-brand-cyan hover:underline">
              {t('doku:neuer_tab')}
            </a>
          </div>

          {/* key: Beim Tabwechsel entsteht ein neuer Rahmen. Ein geänderter src auf demselben Rahmen
              fügte dem Verlauf des Browsers Einträge hinzu, und Zurück spränge dann im Rahmen statt
              auf die vorige Seite. */}
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <iframe key={aktiv.id} title={t('doku:rahmen_titel', { titel: aktiv.titel })}
              src={`/api/doku/${encodeURIComponent(aktiv.id)}`}
              sandbox="allow-popups allow-popups-to-escape-sandbox"
              className="block h-[75vh] min-h-[420px] w-full border-0" />
          </div>
        </>
      )}
    </div>
  )
}
