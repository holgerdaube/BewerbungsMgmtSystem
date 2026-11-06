import { api } from '../api'

interface SpracheAntwort { sprache: string; gewaehlt: boolean }

const ausBrowser = () => ((navigator.language || '').toLowerCase().startsWith('de') ? 'de' : 'en')

const speichern = (sprache: string) =>
  api<SpracheAntwort>('/sprache', { method: 'PUT', body: JSON.stringify({ sprache }) })

/** Die Sprache für diesen Seitenaufruf. Eine neue Installation nimmt einmal die Browsersprache und
 *  merkt sie sich auf dem Server. Scheitert die Anfrage, gilt Deutsch, die App startet trotzdem. */
export async function spracheErmitteln(): Promise<string> {
  try {
    const stand = await api<SpracheAntwort>('/sprache')
    if (stand.gewaehlt) return stand.sprache
    const sprache = ausBrowser()
    await speichern(sprache).catch(() => {})
    return sprache
  } catch {
    return 'de'
  }
}

/** Sprache wechseln. Die Seite lädt neu, damit auch alle Texte vom Server sofort stimmen. */
export async function spracheWechseln(sprache: string): Promise<void> {
  await speichern(sprache)
  window.location.reload()
}
