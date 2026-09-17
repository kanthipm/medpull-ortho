import { ArrowUp, LoaderCircle, Sigma, Sparkles, X } from 'lucide-react'
import { useId, useState } from 'react'
import { useAsk, type AskResult } from '../../api/queries'
import SectionCard from '../../components/SectionCard'
import { SkeletonLine } from '../../components/Skeleton'
import Tile from '../../components/Tile'
import { relativeTime } from '../../lib/format'

const SUGGESTIONS = [
  'Who reported fever this week?',
  'Which patients are behind schedule?',
  'Anyone not wearing their device?',
]

/** Natural-language questions over the roster; the answer both explains and
 *  filters the list below.
 *
 *  The field is the app's rounded ask field: a 52px capsule (`.field-pill`,
 *  1px --line-strong edge, which is its only boundary) with a leading teal
 *  sparkle (5.811 light / 10.825 dark on panel) and a filled round send
 *  button inside it on the right. Suggestions are gray capsules. */
export default function AskBar({
  result,
  onResult,
  onClear,
}: {
  result: AskResult | null
  onResult: (result: AskResult) => void
  onClear: () => void
}) {
  const [question, setQuestion] = useState('')
  const ask = useAsk()
  const inputId = useId()
  const pending = ask.isPending
  const canSend = question.trim().length >= 3 && !pending
  const showClear = Boolean(question || result)

  const submit = (q: string) => {
    const trimmed = q.trim()
    if (trimmed.length < 3 || pending) return
    setQuestion(trimmed)
    ask.mutate(trimmed, { onSuccess: onResult })
  }

  const clear = () => {
    setQuestion('')
    ask.reset()
    onClear()
  }

  const matches = result?.patient_ids.length ?? 0
  const rulesBased = result?.provider === 'fallback'

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
          className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-cat-teal-ink"
        />
        <input
          id={inputId}
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask anything about your patients…"
          autoComplete="off"
          enterKeyHint="send"
          className={`field field-pill text-copy-lg ${showClear ? '!pr-[92px]' : ''}`}
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
              <button type="button" onClick={() => submit(s)} className="btn-gray btn-sm font-normal">
                {s}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div aria-live="polite" aria-busy={pending}>
        {pending && (
          <div className="panel mt-3 animate-fadeIn space-y-2.5 p-5" role="status" aria-label="Finding an answer">
            <SkeletonLine className="h-3 w-1/5" />
            <SkeletonLine className="h-3.5 w-full" />
            <SkeletonLine className="h-3.5 w-3/4" />
          </div>
        )}

        {result && !pending && (
          <SectionCard
            sum
            className="rise mt-3"
            title="Answer"
            icon={
              <Tile
                size="sm"
                family={rulesBased ? 'indigo' : 'teal'}
                icon={rulesBased ? <Sigma /> : <Sparkles />}
              />
            }
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
    </div>
  )
}
