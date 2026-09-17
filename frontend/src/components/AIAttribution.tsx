import { LayoutList, Sparkles } from 'lucide-react'
import { relativeTime } from '../lib/format'
import Tile from './Tile'

/** The small leading tile for a generated narrative (briefing, recovery
 *  summary): a teal Sparkles tile when a model wrote it, a neutral
 *  brand-tint list glyph when the deterministic renderer did. (The old
 *  indigo Σ read as statistics, not care, and was the only purple on the
 *  page.) Glyph on tile: teal 5.171 / 8.142, blue 4.963 / 5.624.
 *
 *    <SectionCard sum title="Today's briefing"
 *                 icon={<NarrativeTile provider={briefing.provider} />} …/> */
export function NarrativeTile({ provider }: { provider: string }) {
  const rulesBased = provider === 'fallback'
  return (
    <Tile
      size="sm"
      family={rulesBased ? 'blue' : 'teal'}
      icon={rulesBased ? <LayoutList /> : <Sparkles />}
    />
  )
}

/** A quiet label marking generated narrative and naming what generated it,
 *  in sentence case: [teal sparkle tile] "AI recovery summary · 12 min ago".
 *
 *  `provider` is the row's `llm_provider`: "groq" and "ollama" mean a model
 *  wrote the line, "fallback" means the deterministic renderer did — and the
 *  renderer's work must not be headlined as AI (it gets the neutral list
 *  tile and "Rules-based …"). The prop is required, so a narrative whose
 *  provenance the API does not return carries no label at all rather than a
 *  borrowed one.
 *
 *  `generating`: the narrative is being written right now. The label reads
 *  "Writing AI summary…" in `.shimmer-text` (Aside's AI signature: the
 *  secondary colour with an ink highlight sweeping through it, so every
 *  frame is at least secondary contrast). Under Reduce Motion and forced
 *  colours it is plain static secondary text. It is a status, so it is
 *  announced politely.
 *
 *  Text is 12/500 + 12/400 in the secondary colour, which flips to --body on
 *  the brand-tint card (R8): 6.237 light / 5.513 dark there. */
export default function AIAttribution({
  kind = 'summary',
  generatedAt,
  provider,
  generating = false,
  className = '',
}: {
  /** What the narrative is — "recovery summary". The source is prefixed. */
  kind?: string
  generatedAt?: string
  provider: string
  /** Show the shimmering "Writing …" state instead of the timestamp. */
  generating?: boolean
  className?: string
}) {
  const rulesBased = provider === 'fallback'
  const source = rulesBased ? 'Rules-based' : 'AI'
  return (
    <span className={`inline-flex items-center gap-2 text-label tracking-label text-secondary ${className}`}>
      <NarrativeTile provider={provider} />
      {generating ? (
        <span role="status" className="shimmer-text font-medium">
          Writing {source === 'AI' ? 'AI' : 'rules-based'} {kind}…
        </span>
      ) : (
        <>
          <span className="font-medium">
            {source} {kind}
          </span>
          {generatedAt && (
            <span className="tabular-nums">
              <span aria-hidden>· </span>
              {relativeTime(generatedAt)}
            </span>
          )}
        </>
      )}
    </span>
  )
}
