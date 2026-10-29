/**
 * Datum und Zeit im Frontend — das Gegenstück zu `backend/app/zeit.py`.
 *
 * HINTERGRUND (P2-20/P2-21, 28.08.2026): Das Backend speichert naives UTC und kennzeichnet es
 * seit P2-20 an der API (`...+00:00`). `new Date(iso).toLocaleString()` rechnet damit von selbst
 * richtig um — für Anzeigen MIT Uhrzeit ist also nichts weiter zu tun.
 *
 * Zwei Muster brauchen trotzdem einen Helfer, weil sie an `Date` vorbeirechnen:
 *
 * 1. `iso.slice(0, 10)` schneidet den Tag aus dem ZEICHENKETTEN-Anfang — das ist der UTC-Tag.
 *    Zwischen 22:00 und 24:00 lokaler Zeit zeigt er den Vortag an. → `tagVon()`
 *
 * 2. `new Date().toISOString().slice(0, 10)` als „heute" — `toISOString()` rechnet nach UTC,
 *    zwischen 00:00 und 02:00 lokal (Sommer) kommt also GESTERN heraus. Betroffen waren
 *    Vorbelegungen von Datumsfeldern und Überfällig-Vergleiche. → `isoTag()`
 */

/** Lokales Kalenderdatum als `YYYY-MM-DD`.
 *
 *  Bewusst aus den lokalen Bestandteilen gebaut statt über `toISOString()`: Letzteres rechnet
 *  nach UTC und liefert in den frühen Morgenstunden den Vortag.
 */
export function isoTag(d: Date = new Date()): string {
  const jahr = d.getFullYear()
  const monat = String(d.getMonth() + 1).padStart(2, '0')
  const tag = String(d.getDate()).padStart(2, '0')
  return `${jahr}-${monat}-${tag}`
}

/** Lokales Kalenderdatum (`YYYY-MM-DD`) aus einem Zeitstempel des Backends.
 *
 *  Drei Fälle, bewusst unterschieden:
 *  - **Reines Datum** (`2026-08-03`) — von Hand eingetragen, schon lokal gemeint. Bleibt, wie es
 *    ist. Es als UTC-Mitternacht zu deuten würde es auf den Vortag schieben.
 *  - **Gekennzeichneter Zeitstempel** (`2026-08-28T09:18:27+00:00`) — der Normalfall seit P2-20.
 *  - **Zeitstempel ohne Kennzeichnung** (`2026-07-23T10:18:33.248500`) — die verbliebenen
 *    Text-Spalten mit Soft-Delete-Stempeln (`deleted_at`, aus `utcnow().isoformat()`). Sie sind
 *    UTC, sagen es aber nicht; hier wird es ergänzt.
 */
export function tagVon(iso: string | null | undefined): string {
  if (!iso) return ''
  const text = String(iso)
  if (!text.includes('T') && !text.includes(' ')) return text.slice(0, 10)
  const hatZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(text)
  const d = new Date(hatZone ? text : text.replace(' ', 'T') + 'Z')
  return Number.isNaN(d.getTime()) ? text.slice(0, 10) : isoTag(d)
}

/** Reines Datum (`YYYY-MM-DD`) als `TT.MM.JJJJ`, ohne `new Date()`-Umweg: `Date` deutet das
 *  ISO-Datum als UTC-Mitternacht, und `toLocaleDateString()` riskiert je nach Zeitzone eine
 *  Verschiebung um einen Tag. Leer → „–“; Unlesbares kommt unverändert zurück. */
export function deDatum(iso: string | null | undefined): string {
  if (!iso) return '–'
  const [j, m, t] = iso.split('-')
  return j && m && t ? `${t}.${m}.${j}` : iso
}
