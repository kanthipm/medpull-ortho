import { Sigma, Sparkles } from 'lucide-react'
import { relativeTime } from '../lib/format'
import Tile from './Tile'

/** A quiet label marking generated narrative and naming what generated it,
 *  in sentence case: [teal sparkle tile] "AI recovery summary · 12 min ago".
 *
 *  `provider` is the row's `llm_provider`: "groq" and "ollama" mean a model
 *  wrote the line, "fallback" means the deterministic renderer did — and the
 *  renderer's work must not be headlined as AI (it gets an indigo Sigma tile
 *  and "Rules-based …"). The prop is required, so a narrative whose
 *  provenance the API does not return carries no label at all rather than a
 *  borrowed one.
 *
 *  Text is 12/500 + 12/400 in the secondary colour, which flips to --body on
 *  the brand-tint card (R8): 6.237 light / 5.513 dark there. */
export default function AIAttribution({
  kind = 'summary',
  generatedAt,
  provider,
  className = '',
}: {
  /** What the narrative is — "recovery summary". The source is prefixed. */
  kind?: string
  generatedAt?: string
  provider: string
  className?: string
}) {
  const rulesBased = provider === 'fallback'
  return (
    <span className={`inline-flex items-center gap-2 text-label tracking-label text-secondary ${className}`}>
      <Tile
        size="sm"
        family={rulesBased ? 'indigo' : 'teal'}
        icon={rulesBased ? <Sigma /> : <Sparkles />}
      />
      <span className="font-medium">
        {rulesBased ? 'Rules-based' : 'AI'} {kind}
      </span>
      {generatedAt && (
        <span className="tabular-nums">
          <span aria-hidden>· </span>
          {relativeTime(generatedAt)}
        </span>
      )}
    </span>
  )
}
