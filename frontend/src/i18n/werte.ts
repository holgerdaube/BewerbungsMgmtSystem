import { t } from './index'

// P2-88: Status, Kategorien und ähnliche Werte bleiben in Datenbank und API deutsch, übersetzt wird nur die
// Anzeige. Der Wert ist der Schlüssel in common.json. Ein unbekannter Wert (etwa der vom Nutzer benannte
// Umkreis) kommt unverändert zurück, nichts bricht.
export type WerteBereich = 'status' | 'situation' | 'work_model' | 'seniority' | 'tab' | 'verfuegbarkeit' | 'mail_kategorie' | 'portal'

export const wert = (bereich: WerteBereich, dbWert: string): string =>
  t(`common:${bereich}.${dbWert}`, { defaultValue: dbWert })
