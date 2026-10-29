import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'

/** Gemeinsame Nav-Zähler: „Neu"-Treffer (Review) + überfällige Follow-ups.
 *  Hält Nav-Badges, Review- und Follow-up-Seite synchron. */
const Ctx = createContext<{ count: number; overdue: number; refresh: () => void }>({
  count: 0, overdue: 0, refresh: () => {},
})

export const useReviewCount = () => useContext(Ctx)

export function ReviewCountProvider({ children }: { children: ReactNode }) {
  const [count, setCount] = useState(0)
  const [overdue, setOverdue] = useState(0)
  const location = useLocation()

  const refresh = () => {
    api<any[]>('/review').then((r) => setCount(r.length)).catch(() => {})
    // Phase 22: /followups ist zweiteilig ({jobs, netzwerk}); das Badge zählt beide überfälligen Sätze.
    api<any>('/followups').then((r) => {
      const alle = [...(r.jobs || []), ...(r.netzwerk || [])]
      setOverdue(alle.filter((f: any) => f.overdue).length)
    }).catch(() => {})
  }

  // Bei jedem Seitenwechsel neu holen (fängt auch externe Änderungen, z. B. neue Jobsuche)
  useEffect(() => { refresh() }, [location.pathname])

  return <Ctx.Provider value={{ count, overdue, refresh }}>{children}</Ctx.Provider>
}
