import React, { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useReviewCount } from '../context/ReviewCount'
import TageslaufButton from './TageslaufButton'
import { api, type VersionInfo } from '../api'
import { PROFIL_GEAENDERT } from '../profil'
import { aktuelleSprache, t } from '../i18n'
import SpracheUmschalter from './SpracheUmschalter'

// P2-51: eine Zeile im Sidebar-Fuß (s. GET /api/version, backend/app/version.py).
// P2-59: Sie nennt immer die Versionsnummer, auch bei einer Git-Arbeitskopie (z. B. die laufende
// Entwicklungsinstallation). Gewünscht war die Nummer, nicht der Commit-Abstand
// ("3 Commits nach 1.1.3") — der stand bis dahin dort im Text. Den Entwicklungsstand gibt es
// nur noch als Tooltip (`hinweis`) auf der Zeile: auffindbar für die Entwicklung, aber ohne
// die Nummer zu verdrängen. Ohne bekannte Version (leer oder 0.0.0) entfällt die Zeile samt
// Tooltip, denn ein Tooltip braucht eine Zeile, an der er hängt.
function versionFusszeile(v: VersionInfo): { text: string; hinweis?: string } | null {
  if (!v.version || v.version === '0.0.0') return null
  const hinweis = v.installation === 'git' && v.entwicklungsstand ? t('common:layout.entwicklungsstand', { stand: v.entwicklungsstand }) : undefined
  return { text: t('common:layout.version', { version: v.version }), hinweis }
}

const NAV = [
  { to: '/', labelKey: 'common:nav.dashboard', icon: '📊', end: true },
  { to: '/suche', labelKey: 'common:nav.suche', icon: '🔍' },
  { to: '/review', labelKey: 'common:nav.review', icon: '✨' },
  { to: '/followups', labelKey: 'common:nav.followups', icon: '⏰' },
  { to: '/pipeline', labelKey: 'common:nav.pipeline', icon: '📋' },
  { to: '/jobs', labelKey: 'common:nav.jobs', icon: '💼' },
  { to: '/inbox', labelKey: 'common:nav.inbox', icon: '📧' },
  // P2-61: Outreach zeigt eine einmalige Übernahme aus einer früheren Excel-Liste; im BMS lässt sich dort
  // nichts anlegen. Der Punkt erscheint deshalb nur, wenn es Outreach-Zeilen gibt (s. outreachDa).
  { to: '/outreach', labelKey: 'common:nav.outreach', icon: '📇' },
  { to: '/netzwerk', labelKey: 'common:nav.netzwerk', icon: '🌐' },
  // P2-61: Phase 40 hatte den Beirat aus der Leiste genommen, weil die Stellenprüfung in die
  // Stellenansicht wanderte. Die freie Debatte ohne Stellenbezug war seitdem nur über die Adresse
  // erreichbar, für Kunden also eine versteckte Funktion.
  { to: '/beirat', labelKey: 'common:nav.beirat', icon: '🏛️' },
  { to: '/companies', labelKey: 'common:nav.companies', icon: '🏢' },
  { to: '/radar', labelKey: 'common:nav.radar', icon: '📡' },
  { divider: true },
  { to: '/tasks', labelKey: 'common:nav.tasks', icon: '⚙️' },
  { to: '/budget', labelKey: 'common:nav.budget', icon: '💶' },
  { divider: true },
  { to: '/profil', labelKey: 'common:nav.profil', icon: '🪪' },
  { to: '/einstellungen', labelKey: 'common:nav.einstellungen', icon: '🎯' },
  { divider: true },
  // P2-59: Dokumentation und Rechtliches sind beides Lesetexte; sie stehen zusammen im letzten
  // Block, abgesetzt von den Arbeitsbereichen darüber.
  { to: '/dokumentation', labelKey: 'common:nav.dokumentation', icon: '📖' },
  { to: '/rechtliches', labelKey: 'common:nav.rechtliches', icon: '⚖️' },
]

// P2-72: Titel des Dokuments beim Start (index.html), einmal beim Laden des Moduls gelesen und damit
// vor jeder Änderung durch die Oberfläche. Er ist der Name, der gilt, bis `GET /api/design` antwortet.
const TITEL_BEIM_START = typeof document !== 'undefined' ? document.title : ''

export default function Layout({ children }: { children: React.ReactNode }) {
  const { count: reviewCount, overdue } = useReviewCount()

  // Phase 71E (Frontend ohne feste Personendaten): Kopfzeile zeigte bislang hart einen festen
  // Namen samt Zieldatum. Geprüft (Auftrag): GET /api/profil, dieselbe Quelle, die Profil.tsx für
  // Skills/Werdegang/Positionierung nutzt. Befund laut main.py-Kommentar an Ort und Stelle
  // ("Design-Entscheidung 2"): diese Profil-DB-Tabelle ist bewusst von config/profil.md
  // getrennt (Kandidaten-Substanz fürs Matching vs. Such-Strategie) — sie enthält weder
  // einen Namen noch ein Zieldatum, beides steht nur in config/profil.md, das über keinen
  // bestehenden Endpunkt ausgeliefert wird. Ein neuer Endpunkt wäre nötig; dieses Teilpaket
  // darf das Backend aber nicht anfassen. Deshalb: `name` wird defensiv optional gelesen
  // (ergänzt ein künftiges Backend das Feld, greift es automatisch von selbst), fehlt es —
  // wie aktuell —, bleibt die Zeile leer statt eines erfundenen Werts (dieselbe "nur falls
  // Feld vorhanden"-Regel, die der Auftrag für das Ziel-Datum ausdrücklich vorgibt; ein
  // Ziel-Datum-Feld existiert ebenfalls nirgends und entfällt deshalb ganz). `headline`
  // (das einzige vorhandene Freitextfeld) wurde bewusst NICHT als Ersatz verwendet: es
  // transportiert die LinkedIn-Kurzbeschreibung, nicht den Namen — nachprüfbar an jedem
  // Profil mit LinkedIn-Überschrift.
  const [profilName, setProfilName] = useState('')
  useEffect(() => {
    const laden = () => { api<any>('/profil').then((d) => setProfilName(d?.profile?.name || '')).catch(() => {}) }
    laden()
    // P2-59: nach „Beispieldaten entfernen“ neu laden, sonst stünde der Beispielname bis zum
    // nächsten Seitenstart hier (s. PROFIL_GEAENDERT in profil.ts).
    window.addEventListener(PROFIL_GEAENDERT, laden)
    return () => window.removeEventListener(PROFIL_GEAENDERT, laden)
  }, [])
  // P2-51: Versionszeile im Sidebar-Fuß, s. versionFusszeile() oben.
  const [version, setVersion] = useState<VersionInfo | null>(null)
  useEffect(() => {
    api<VersionInfo>('/version').then(setVersion).catch(() => {})
  }, [])
  // P2-72: Der Produktname kommt aus dem geltenden Design (GET /api/design, Rolle `produktname`).
  // Bis die Antwort da ist, gilt der Anfangswert des Dokuments (TITEL_BEIM_START, aus index.html);
  // schlägt der Aufruf fehl, bleibt er stehen. Der Name steht damit nirgends im TypeScript.
  const [produktnameDesign, setProduktname] = useState(TITEL_BEIM_START)
  // P2-88: Der Name aus dem Design ist der deutsche. Er ist fest (pipeline/design.py), Englisch hat seinen eigenen.
  const produktname = aktuelleSprache() === 'de' ? produktnameDesign : t('common:produkt.name')
  useEffect(() => {
    api<{ produktname?: string }>('/design')
      .then((d) => { if (typeof d?.produktname === 'string' && d.produktname) setProduktname(d.produktname) })
      .catch(() => {})
  }, [])
  // P2-50 (Kundenpaket, B2): Browser-Titel trägt den Profil-Namen statt fest eines Namens —
  // bis der Name geladen ist (oder ohne gepflegtes Profil) bleibt er neutral.
  // P2-59: Das Produkt steht ausgeschrieben mit Bindestrichen im Titel, damit Tab und
  // Seitenleiste denselben Namen tragen. (P2-72: der Name ist jetzt `produktname`.)
  useEffect(() => {
    document.title = profilName ? `${produktname} · ${profilName}` : produktname
  }, [produktname, profilName])
  const fusszeile = version ? versionFusszeile(version) : null
  // P2-61: Gefragt wird nach den Daten, nicht nach der Installationsart. So bleibt der Punkt dort, wo Zeilen übernommen wurden,
  // und jede Installation ohne übernommene Outreach-Zeilen sieht ihn nicht, auch eine
  // Git-Arbeitskopie. Bis die Antwort da ist, fehlt er (kein kurzes Aufblitzen beim Kunden).
  const [outreachDa, setOutreachDa] = useState(false)
  useEffect(() => {
    api<unknown[]>('/outreach').then((zeilen) => setOutreachDa(zeilen.length > 0)).catch(() => {})
  }, [])
  const nav = NAV.filter((n) => n.to !== '/outreach' || outreachDa)

  return (
    <div className="flex min-h-full flex-col lg:flex-row">
      <aside className="flex w-full shrink-0 flex-col bg-brand-navy text-brand-aufMarke lg:min-h-screen lg:w-60">
        {/* P2-59: Kopf mittig. Die erste Zeile ist in text-lg (Inter 700) rund 243 px breit und
            sprengte die 240 px der Leiste; text-base mit engerem Zeichenabstand braucht rund 208 px
            und passt in den Streifen, den px-3 lässt.
            P2-72: Den Umbruch setzt der Browser selbst (nach Bindestrich oder Leerzeichen), kein
            <br /> von Hand mehr: Der Name kommt aus dem Design und kann anders lauten. Damit er unter
            lg (Leiste über die ganze Breite) genauso fällt wie in der schmalen Leiste, hat der Block
            dieselbe Breite wie der Streifen der Leiste (15rem minus 2 x px-3 = 13.5rem). break-words
            fängt ein sehr langes Wort ab, statt dass es überläuft. Mit dem Namen der Vorgabe ergibt
            das "Bewerbungs-Management-" / "System" wie vorher.
            Die Schrift des Namens bleibt reines Weiß: Die Rolle auf_marke ist ein gedämpfteres Hell. */}
        <div className="px-3 pb-2 pt-4 text-center lg:pt-5">
          <div className="mx-auto max-w-[13.5rem] break-words text-base font-bold leading-tight tracking-tight text-white">
            {produktname}
          </div>
          {profilName && <div className="mt-1 break-words text-xs text-brand-steel">{profilName}</div>}
        </div>
        <TageslaufButton />
        <nav className="mt-2 flex gap-1 overflow-x-auto px-3 pb-3 lg:flex-1 lg:flex-col lg:gap-0 lg:space-y-1 lg:overflow-visible lg:pb-0">
          {nav.map((n, i) =>
            'divider' in n ? (
              <div key={`divider-${i}`} className="mx-3 hidden border-t border-white/10 lg:my-1 lg:block" />
            ) : (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                `flex shrink-0 items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm transition lg:shrink lg:gap-3 ${
                  isActive ? 'bg-brand-cyan text-brand-navy font-semibold' : 'text-slate-300 hover:bg-white/10'
                }`
              }
            >
              <span>{n.icon}</span>
              <span className="flex-1">{t(n.labelKey)}</span>
              {n.to === '/review' && reviewCount > 0 && (
                <span className="rounded-full bg-brand-cyan px-2 py-0.5 text-xs font-bold text-brand-navy">{reviewCount}</span>
              )}
              {n.to === '/followups' && overdue > 0 && (
                <span className="rounded-full bg-rose-500 px-2 py-0.5 text-xs font-bold text-white">{overdue}</span>
              )}
            </NavLink>
            )
          )}
        </nav>
        {/* P2-88: außerhalb des Fußblocks, der unter lg verborgen ist: Der Umschalter bleibt überall erreichbar. */}
        <div className="px-5 pb-2 lg:pt-2"><SpracheUmschalter dunkel /></div>
        <div className="hidden px-5 py-4 text-[11px] leading-relaxed text-brand-steel/70 lg:block">
          {fusszeile && <div title={fusszeile.hinweis}>{fusszeile.text}</div>}
          {t('common:layout.engine')}<br />{t('common:layout.quelle')}
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-x-hidden">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 sm:py-6">
          {children}
        </div>
      </main>
    </div>
  )
}
