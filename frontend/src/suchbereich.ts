import { useEffect, useState } from 'react'
import { api, type Einstellungen } from './api'

// P2-51: Der Umkreis-Tab (z. B. „<Stadt> +100km") stand bisher fest in drei
// Frontend-Listen (Jobs.tsx, JobNew.tsx, JobDetail.tsx) — bei jeder anderen Stadt falsch. Die
// Bezeichnung kommt jetzt aus den Einstellungen (GET /api/einstellungen -> umkreis_label, s.
// backend/pipeline/suchprofil.py::umkreis_label). Modul-Cache nach dem Muster von profil.ts:
// mehrere Seiten teilen sich denselben Request, statt ihn je einzeln zu stellen.
let ladeVersuch: Promise<string[]> | null = null

function ladeTabs(): Promise<string[]> {
  if (!ladeVersuch) {
    ladeVersuch = api<Einstellungen>('/einstellungen')
      .then((e) => (e.umkreis_label ? ['Remote', 'Deutschlandweit', e.umkreis_label] : ['Remote', 'Deutschlandweit']))
      .catch(() => ['Remote', 'Deutschlandweit'])
  }
  return ladeVersuch
}

/** Such-Tabs für Filter/Auswahlfelder — bis /api/einstellungen geladen ist, die beiden festen
 *  Tabs ohne den Umkreis (der braucht eine in den Einstellungen gepflegte Stadt). Mehrere
 *  Aufrufer teilen sich denselben Request (s. ladeTabs-Modul-Cache oben). */
export function useSuchTabs(): string[] {
  const [tabs, setTabs] = useState<string[]>(['Remote', 'Deutschlandweit'])
  useEffect(() => {
    ladeTabs().then(setTabs)
  }, [])
  return tabs
}

/** Cache verwerfen — nach dem Speichern eines neuen Umkreises (Stadt/Radius) in den
 *  Einstellungen, damit der nächste Aufruf von useSuchTabs() die aktuelle Bezeichnung neu lädt. */
export function suchTabsNeuLaden() {
  ladeVersuch = null
}
