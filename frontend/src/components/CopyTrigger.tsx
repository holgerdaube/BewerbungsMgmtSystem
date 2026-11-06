import { useState } from 'react'
import { useKiAnbieter } from './ui'
import { t } from '../i18n'

/** Kopiert einen Auslöser-Satz für die KI-Session (Claude oder ChatGPT) in die Zwischenablage (Claude-in-the-Loop). */
export default function CopyTrigger({ phrase, label, done }: { phrase: string; label: string; done?: string }) {
  const [copied, setCopied] = useState(false)
  const { name } = useKiAnbieter()
  const copy = async () => {
    try { await navigator.clipboard.writeText(phrase) } catch { /* Fallback: Hinweis trotzdem zeigen */ }
    setCopied(true)
    setTimeout(() => setCopied(false), 4000)
  }
  return (
    <button onClick={copy}
      className={`w-full rounded-lg px-3 py-2 text-sm font-semibold transition ${copied ? 'bg-emerald-500 text-white' : 'bg-brand-cyan text-brand-aufAktion hover:bg-brand-cyanHover'}`}>
      {copied ? (done || t('common:ui.copy_trigger_ok', { name })) : label}
    </button>
  )
}
