import { Search, Sparkles, X } from 'lucide-react'
import { useState } from 'react'
import { useAsk, type AskResult } from '../../api/queries'
import AIAttribution from '../../components/AIAttribution'
import SectionCard from '../../components/SectionCard'
import { SkeletonLine } from '../../components/Skeleton'

const SUGGESTIONS = [
  'Who reported fever this week?',
  'Which patients are behind schedule?',
  'Anyone not wearing their device?',
]

/** Natural-language questions over the roster — answer both explains and filters. */
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

  const submit = (q: string) => {
    const trimmed = q.trim()
    if (trimmed.length < 3 || ask.isPending) return
    setQuestion(trimmed)
    ask.mutate(trimmed, { onSuccess: onResult })
  }

  return (
    <div>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          submit(question)
        }}
        className="flex items-center gap-2 rounded-card border border-line bg-panel p-1.5 transition-[border-color,box-shadow] duration-150 focus-within:border-brand/40 focus-within:shadow-[0_0_0_3px_rgba(91,104,223,.14)]"
      >
        <span className="grid h-8 w-8 shrink-0 place-items-center text-brand" aria-hidden>
          <Sparkles size={15} />
        </span>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about your patients — symptoms, progress, adherence, data gaps…"
          aria-label="Ask about your patients"
          className="min-w-0 flex-1 bg-transparent text-[13.5px] font-medium text-ink placeholder:text-faint focus:outline-none"
        />
        {(question || result) && (
          <button
            type="button"
            aria-label="Clear question"
            onClick={() => {
              setQuestion('')
              onClear()
            }}
            className="grid h-7 w-7 cursor-pointer place-items-center rounded-btn text-faint transition-colors duration-150 hover:bg-soft hover:text-ink"
          >
            <X size={14} />
          </button>
        )}
        <button
          type="submit"
          disabled={question.trim().length < 3 || ask.isPending}
          className="qa-btn !flex-none px-3.5"
        >
          <Search size={13} className="text-brand" />
          {ask.isPending ? 'Thinking…' : 'Ask'}
        </button>
      </form>

      {!result && !ask.isPending && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 px-0.5">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => submit(s)}
              className="cursor-pointer rounded-btn border border-line bg-panel px-2.5 py-1 text-[11.5px] font-medium text-muted transition-colors duration-150 hover:border-brand/30 hover:text-ink"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {ask.isPending && (
        <div className="mt-3 animate-fadeIn space-y-2.5 rounded-card border border-line bg-panel p-4">
          <SkeletonLine className="h-3 w-1/5" />
          <SkeletonLine className="h-3.5 w-full" />
          <SkeletonLine className="h-3.5 w-3/4" />
        </div>
      )}

      {result && !ask.isPending && (
        <SectionCard
          sum
          spine="bg-brand"
          className="rise mt-3"
          eyebrow={<AIAttribution kind="answer" generatedAt={result.generated_at} provider={result.provider} />}
          aside={
            result.patient_ids.length > 0 ? (
              <span className="chip bg-brand-tint text-brand">
                Showing {result.patient_ids.length} match
                {result.patient_ids.length === 1 ? '' : 'es'}
              </span>
            ) : undefined
          }
        >
          <p className="text-[13.5px] font-medium leading-[1.55] text-body">{result.answer}</p>
        </SectionCard>
      )}
    </div>
  )
}
