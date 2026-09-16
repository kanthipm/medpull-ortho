import { Search, Sparkles, X } from 'lucide-react'
import { useState } from 'react'
import { useAsk, type AskResult } from '../../api/queries'
import AIAttribution from '../../components/AIAttribution'
import SentenceCase from './SentenceCase'
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
        className="flex items-center gap-seam rounded-control border border-line-strong bg-panel py-el pl-seam pr-el outline-2 outline-offset-0 outline-brand transition-[border-color,outline-color] duration-150 focus-within:border-brand focus-within:outline"
      >
        <span className="grid h-10 w-10 shrink-0 place-items-center text-brand-ink" aria-hidden>
          <Sparkles size={18} />
        </span>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about your patients — symptoms, progress, adherence, data gaps…"
          aria-label="Ask about your patients"
          className="min-w-0 flex-1 bg-transparent text-copy-lg text-ink placeholder:text-muted focus:outline-none"
        />
        {(question || result) && (
          <button
            type="button"
            aria-label="Clear question"
            onClick={() => {
              setQuestion('')
              onClear()
            }}
            className="grid h-9 w-9 cursor-pointer place-items-center rounded-control text-muted transition-colors duration-150 hover:bg-soft hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            <X size={16} />
          </button>
        )}
        <button
          type="submit"
          disabled={question.trim().length < 3 || ask.isPending}
          className="qa-btn !flex-none"
        >
          <Search size={15} />
          {ask.isPending ? 'Thinking…' : 'Ask'}
        </button>
      </form>

      {!result && !ask.isPending && (
        <div className="mt-seam flex flex-wrap items-center gap-seam px-1">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => submit(s)}
              className="qa-btn"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {ask.isPending && (
        <div className="mt-tight animate-fadeIn space-y-seam rounded-surface border border-line bg-panel p-block">
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
          eyebrow={(
            <SentenceCase>
              <AIAttribution kind="answer" generatedAt={result.generated_at} provider={result.provider} />
            </SentenceCase>
          )}
          aside={
            result.patient_ids.length > 0 ? (
              <span className="chip bg-brand-tint text-on-brand-tint">
                Showing {result.patient_ids.length} match
                {result.patient_ids.length === 1 ? '' : 'es'}
              </span>
            ) : undefined
          }
        >
          <p className="text-copy-lg text-body">{result.answer}</p>
        </SectionCard>
      )}
    </div>
  )
}
