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
        className="flex items-center gap-2 rounded-btn border border-line bg-panel py-1.5 pl-2.5 pr-1.5 shadow-card transition-[border-color,box-shadow] duration-150 focus-within:border-brand focus-within:shadow-[0_0_0_1px_rgb(var(--brand))]"
      >
        <span className="grid h-10 w-10 shrink-0 place-items-center text-brand" aria-hidden>
          <Sparkles size={18} />
        </span>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about your patients — symptoms, progress, adherence, data gaps…"
          aria-label="Ask about your patients"
          className="min-w-0 flex-1 bg-transparent text-[15px] text-ink placeholder:text-faint focus:outline-none"
        />
        {(question || result) && (
          <button
            type="button"
            aria-label="Clear question"
            onClick={() => {
              setQuestion('')
              onClear()
            }}
            className="grid h-9 w-9 cursor-pointer place-items-center rounded-btn text-muted transition-colors duration-150 hover:bg-soft hover:text-ink"
          >
            <X size={16} />
          </button>
        )}
        <button
          type="submit"
          disabled={question.trim().length < 3 || ask.isPending}
          className="qa-btn !flex-none px-3.5"
        >
          <Search size={15} className="text-brand" />
          {ask.isPending ? 'Thinking…' : 'Ask'}
        </button>
      </form>

      {!result && !ask.isPending && (
        <div className="mt-2.5 flex flex-wrap items-center gap-2 px-1">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => submit(s)}
              className="cursor-pointer rounded-btn border border-line bg-panel px-3.5 py-1.5 text-[13px] font-medium text-body transition-colors duration-150 hover:border-brand/40 hover:bg-brand-tint hover:text-brand"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {ask.isPending && (
        <div className="mt-3 animate-fadeIn space-y-2.5 rounded-card border border-line bg-panel p-5 shadow-card">
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
          <p className="text-[15px] leading-[1.6] text-body">{result.answer}</p>
        </SectionCard>
      )}
    </div>
  )
}
