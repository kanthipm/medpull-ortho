import { ArrowUp, LoaderCircle, Sparkles, X } from 'lucide-react'
import { useId } from 'react'
import { NarrativeTile } from '../../components/AIAttribution'
import SectionCard from '../../components/SectionCard'
import { SkeletonLine } from '../../components/Skeleton'
import { relativeTime } from '../../lib/format'
import type { AskState } from './useAskState'

const SUGGESTIONS = [
  'Who reported fever this week?',
  'Which patients are behind schedule?',
  'Anyone not wearing their device?',
]

/** The ask field, ON THE SKY (it lives in the worklist's page head).
 *
 *  A 52px glass capsule (`.field.field-pill.field-glass`): the glass fill is
 *  at the .78 / .86 floor computed over the decor sky's most saturated point,
 *  so the ink value and the placeholder hold 4.5:1 with no blur credit (the
 *  placeholder is --body here, because the page head flips --muted to body:
 *  6.117 light / 6.103 dark). Its only boundary is the 1px --line-strong edge
 *  (1.4.11). It turns opaque on focus. Leading teal sparkle, trailing filled
 *  round send button.
 *
 *  Suggestions are Aside's hairline-ring capsules (`.badge-ring`, the same
 *  glass-lite fill), grown to a 32px target and the 14px UI size. Under
 *  Increase Contrast, reduced transparency and data-glass="off" every glass
 *  alpha is 1, so both become opaque panels. */
export function AskField({ state }: { state: AskState }) {
  const { question, setQuestion, result, pending, submit, clear } = state
  const inputId = useId()
  const canSend = question.trim().length >= 3 && !pending
  const showClear = Boolean(question || result)

  return (
    <div>
      <form
        role="search"
        onSubmit={(e) => {
          e.preventDefault()
          submit(question)
        }}
        className="relative"
      >
        <label htmlFor={inputId} className="sr-only">
          Ask about your patients
        </label>
        <Sparkles
          aria-hidden
          size={20}
          className="pointer-events-none absolute left-4 top-1/2 z-[1] -translate-y-1/2 text-cat-teal-ink"
        />
        <input
          id={inputId}
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask anything about your patients…"
          autoComplete="off"
          enterKeyHint="send"
          className={`field field-pill field-glass text-copy-lg ${showClear ? '!pr-[92px]' : ''}`}
        />
        <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1">
          {showClear && (
            <button type="button" aria-label="Clear question" onClick={clear} className="btn-icon btn-sm">
              <X />
            </button>
          )}
          <button
            type="submit"
            aria-label={pending ? 'Asking…' : 'Ask'}
            disabled={!canSend}
            className="btn-send"
          >
            {pending ? (
              <LoaderCircle size={16} aria-hidden className="animate-spin motion-reduce:animate-none" />
            ) : (
              <ArrowUp size={16} aria-hidden />
            )}
          </button>
        </div>
      </form>

      {!result && !pending && (
        <ul className="mt-3 flex flex-wrap items-center gap-2" aria-label="Suggested questions">
          {SUGGESTIONS.map((s) => (
            <li key={s}>
              <button
                type="button"
                onClick={() => submit(s)}
                className="badge-ring min-h-8 px-3 text-copy font-normal"
              >
                {s}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** The answer to the ask field, BELOW the page head on an opaque brand-tint
 *  card (it floats over the sky's tail). While the answer is being written
 *  the header carries the shimmer, the one loading motion allowed. The
 *  answer both explains and filters the list below. */
export function AskAnswer({ state }: { state: AskState }) {
  const { result, pending, clear } = state
  const matches = result?.patient_ids.length ?? 0
  const rulesBased = result?.provider === 'fallback'

  if (!pending && !result) return null

  return (
    <div aria-live="polite" aria-busy={pending}>
      {pending && (
        <SectionCard
          sum
          className="animate-fadeIn"
          title="Answer"
          aside={
            <span role="status" className="shimmer-text text-label font-medium tracking-label">
              Looking through your patients…
            </span>
          }
        >
          <div aria-hidden className="space-y-2.5 pt-1">
            <SkeletonLine className="h-3.5 w-full" />
            <SkeletonLine className="h-3.5 w-3/4" />
          </div>
        </SectionCard>
      )}

      {result && !pending && (
        <SectionCard
          sum
          className="rise"
          title="Answer"
          icon={<NarrativeTile provider={result.provider} />}
          aside={
            <span className="meta tabular-nums">
              {rulesBased ? 'Rules-based' : 'AI'}
              <span aria-hidden> · </span>
              <span className="sr-only">, </span>
              {relativeTime(result.generated_at)}
              {matches > 0 && (
                <>
                  <span aria-hidden> · </span>
                  <span className="sr-only">, </span>
                  Showing {matches} {matches === 1 ? 'match' : 'matches'}
                </>
              )}
            </span>
          }
          action={
            <button type="button" onClick={clear} className="btn-plain btn-sm">
              Show everyone
            </button>
          }
        >
          <p className="max-w-[64ch] text-copy-lg text-ink">{result.answer}</p>
        </SectionCard>
      )}
    </div>
  )
}
