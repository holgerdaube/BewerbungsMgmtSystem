import { useEffect, useState } from 'react'
import { api } from './api'

// P2-50 (Kundenpaket): Der Startpunkt der Routenplanung zu Vorstellungsgesprächen stand bisher
// als feste Adresse im Code (FollowUps.tsx/JobDetail.tsx) — falsch für jeden
// anderen Nutzer. Ab jetzt kommt die Adresse aus config/profil.md (GET /api/profil ->
// adresse, s. backend/pipeline/user_profile.py::anschrift). Modul-Cache: mehrere Seiten
// (FollowUps, JobDetail) teilen sich denselben Request, statt je einmal selbst zu laden.
let ladeVersuch: Promise<string> | null = null

// P2-59: Wer Name oder Anschrift aus config/profil.md ändert (heute: „Beispieldaten entfernen“ in
// den Einstellungen), löst dieses Ereignis aus. Der Modul-Cache oben verwirft dann seine Adresse,
// und die Seitenleiste (Layout.tsx) lädt den Namen neu, statt bis zum nächsten Seitenstart die
// alten Werte zu zeigen.
export const PROFIL_GEAENDERT = 'bms:profil-geaendert'
window.addEventListener(PROFIL_GEAENDERT, () => { ladeVersuch = null })

function ladeAdresse(): Promise<string> {
  if (!ladeVersuch) {
    ladeVersuch = api<any>('/profil').then((d) => d?.profile?.adresse || '').catch(() => '')
  }
  return ladeVersuch
}

/** Adresse aus dem Profil — leer, bis /api/profil geladen ist bzw. wenn kein Standort gepflegt
 *  ist. Mehrere Aufrufer teilen sich denselben Request (s. ladeAdresse-Modul-Cache oben). */
export function useProfilAdresse(): string {
  const [adresse, setAdresse] = useState('')
  useEffect(() => {
    ladeAdresse().then(setAdresse)
  }, [])
  return adresse
}

/** Google-Maps-Routenlink zu `ziel`. `origin` nur, wenn eine Adresse vorliegt — ohne Profil-
 *  Adresse lässt Google Maps das Feld leer und nimmt beim Öffnen den aktuellen Standort. */
export function mapsRouteUrl(adresse: string, ziel: string): string {
  const origin = adresse ? `origin=${encodeURIComponent(adresse)}&` : ''
  return `https://www.google.com/maps/dir/?api=1&${origin}destination=${encodeURIComponent(ziel)}`
}
