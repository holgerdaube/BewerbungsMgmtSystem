import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { spracheErmitteln } from './sprache'

// P2-88: Oberfläche auf Deutsch und Englisch. Die Sprache steht fest, bevor die App gerendert wird
// (main.tsx), und ein Wechsel lädt die Seite neu (sprache.ts). Deshalb reicht das schlichte `t()`, auch
// außerhalb von Komponenten; die Seiten müssen nicht auf einen Wechsel reagieren.
//
// Eine Sprachdatei je Bereich, der Dateiname ist der Namespace: `t('jobs:spalte.firma')`.
const dateien = import.meta.glob('./*/*.json', { eager: true }) as Record<string, { default: object }>

const resources: Record<string, Record<string, object>> = {}
for (const [pfad, inhalt] of Object.entries(dateien)) {
  const [, sprache, bereich] = pfad.match(/^\.\/(\w+)\/(\w+)\.json$/) as RegExpMatchArray
  ;(resources[sprache] ||= {})[bereich] = inhalt.default
}

export async function i18nStarten(): Promise<void> {
  const lng = await spracheErmitteln()
  await i18n.use(initReactI18next).init({
    resources,
    lng,
    fallbackLng: 'de',
    defaultNS: 'common',
    returnNull: false,
    interpolation: { escapeValue: false },   // React escaped selbst
  })
  document.documentElement.lang = lng
}

/** Text zum Schlüssel, immer mit Namespace: `t('common:nav.jobs')`. */
export const t = (schluessel: string, werte?: Record<string, unknown>): string => i18n.t(schluessel, werte as any) as string

export const aktuelleSprache = (): string => i18n.language
