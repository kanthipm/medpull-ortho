import { Lightbulb } from 'lucide-react'
import type { Suggestion } from '../../api/sports'
import EmptyState from '../../components/EmptyState'
import { ListGroup } from '../../components/ListRow'
import SectionCard from '../../components/SectionCard'
import { EvidencePill } from './SportsBits'
import { words } from './sportsFormat'

/** The engine's suggestions, most urgent first: the title, the evidence
 *  grade, the category, why, and the actions. */
export default function SuggestionsCard({ suggestions }: { suggestions: Suggestion[] }) {
  const items = [...suggestions].sort((a, b) => a.priority - b.priority)
  return (
    <SectionCard flush title="Suggestions" aside={items.length > 0 ? `${items.length}` : undefined}>
      {items.length === 0 ? (
        <EmptyState variant="inline" icon={<Lightbulb />} family="teal" title="Nothing to change today">
          The plan stands; the engine has no suggestion beyond it.
        </EmptyState>
      ) : (
        <ListGroup embedded inset="none" as="ol" aria-label="Suggestions, most urgent first">
          {items.map((s) => (
            <li key={s.key} className="card-row">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <h3 className="text-copy-lg font-medium text-ink">{s.title}</h3>
                <EvidencePill grade={String(s.evidence)} />
                <span className="meta">{words(s.category)}</span>
              </div>
              {s.why && <p className="mt-1 text-copy text-body">{s.why}</p>}
              {s.actions.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {s.actions.map((a, i) => (
                    <li key={i} className="flex gap-1.5 text-copy text-ink">
                      <span aria-hidden className="text-brand-ink">→</span>
                      <span>{a}</span>
                    </li>
                  ))}
                </ul>
              )}
              {s.source && <p className="meta mt-2">{s.source}</p>}
            </li>
          ))}
        </ListGroup>
      )}
    </SectionCard>
  )
}
