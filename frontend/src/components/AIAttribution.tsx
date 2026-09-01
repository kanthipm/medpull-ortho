import { Sigma, Sparkles } from 'lucide-react'
import { relativeTime } from '../lib/format'

/** Quiet microlabel marking generated narrative, and naming what generated it.
 *
 *  `provider` is the row's `llm_provider`: "groq" and "ollama" mean a model
 *  wrote the line, "fallback" means the deterministic renderer did — and the
 *  renderer's work must not be headlined as AI. The prop is required, so a
 *  narrative whose provenance the API does not return carries no label at all
 *  rather than a borrowed one. */
export default function AIAttribution({
  kind = 'summary',
  generatedAt,
  provider,
}: {
  /** What the narrative is — "recovery summary". The source is prefixed. */
  kind?: string
  generatedAt?: string
  provider: string
}) {
  const rulesBased = provider === 'fallback'
  const Icon = rulesBased ? Sigma : Sparkles
  const accent = rulesBased ? 'text-muted' : 'text-brand'
  return (
    <span className="inline-flex items-center gap-1.5 text-[10.5px] font-medium uppercase tracking-[.1em] text-faint">
      <Icon size={11} className={accent} aria-hidden />
      <span className={accent}>
        {rulesBased ? 'Rules-based' : 'AI'} {kind}
      </span>
      {generatedAt && (
        <span className="font-mono normal-case tracking-normal text-faint">
          · {relativeTime(generatedAt)}
        </span>
      )}
    </span>
  )
}
