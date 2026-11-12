import { Plus, Send, Target, X } from 'lucide-react'
import { useState } from 'react'
import { dayText, usePtAction, type PtChart, type PtGoal } from '../../api/pt'
import EmptyState from '../../components/EmptyState'
import { useToast } from '../../components/Toast'
import { Group, Pill } from './ptBits'
import { errorText, sentLine, signed, todayIso } from './ptWords'

/** Function: the things the person wants to get back to, in their words,
 *  and how able they rate themselves at each (0 unable, 10 as before). The
 *  average is the patient-specific functional scale; its change is set
 *  beside the published threshold, with no word on what it means. */
export default function ProgramFunction({
  patientId,
  first,
  data,
  by,
}: {
  patientId: string
  first: string
  data: PtChart
  by: string
}) {
  const toast = useToast()
  const act = usePtAction(patientId)
  const [text, setText] = useState('')
  const [rating, setRating] = useState<Record<number, string>>({})
  const { goals, max_goals, score } = data.function
  const active = goals.filter((g) => g.active)
  const ended = goals.filter((g) => !g.active)
  const fail = (e: unknown) => toast(errorText(e), 'warning')
  const ask = (path: string, what: string) =>
    act.mutate({ path, body: { by } }, { onSuccess: (r) => toast(...sentLine(first, r.sent, what)), onError: fail })
  const filled = Object.entries(rating).filter(([, v]) => v !== '')

  if (goals.length === 0) {
    return (
      <EmptyState
        variant="inline"
        family="violet"
        icon={<Target />}
        title="No goals yet"
        action={
          <button type="button" className="btn-tinted" disabled={act.isPending} onClick={() => ask('/goals/ask', 'The question')}>
            <Send aria-hidden size={16} /> Ask {first} to name them
          </button>
        }
      >
        Up to three things {first} wants to get back to, in their own words: “pull 315 from the floor”. Progress is
        then read off what they can do.
        <AddGoal value={text} onChange={setText} busy={act.isPending} onAdd={() =>
          act.mutate({ path: '/goals', body: { text, by } }, { onSuccess: () => setText(''), onError: fail })
        } />
      </EmptyState>
    )
  }

  return (
    <div className="space-y-5">
      {score && (
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-[28px] font-medium leading-none tracking-tight text-ink tabular-nums">
            {score.latest}
            <span className="text-copy text-secondary"> /10</span>
          </span>
          <span className="text-copy text-secondary">
            functional scale, {dayText(score.latest_on)}
            {score.change && (
              <>
                {' · '}
                <span className="text-ink">
                  {signed(score.change.delta)} since {dayText(score.first_on)}
                </span>
              </>
            )}
          </span>
          {score.change && score.threshold != null && (
            <Pill
              tone={score.change.past_threshold ? 'brand' : 'plain'}
              title="Stratford et al., Physiotherapy Canada 1995: 2 points on the average (3 on one activity), 90% confidence"
            >
              {score.change.past_threshold ? 'Past' : 'Inside'} the {score.threshold}-point detectable change
            </Pill>
          )}
        </div>
      )}

      <Group label={`${first}’s goals`}>
        <ul className="space-y-3">
          {active.map((g) => (
            <GoalRow
              key={g.id}
              goal={g}
              value={rating[g.id] ?? ''}
              onRate={(v) => setRating((r) => ({ ...r, [g.id]: v }))}
              onEnd={() => act.mutate({ path: `/goals/${g.id}`, method: 'DELETE' }, { onError: fail })}
            />
          ))}
        </ul>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="btn-tinted btn-sm"
            disabled={filled.length === 0 || act.isPending}
            onClick={() =>
              act.mutate(
                {
                  path: '/goals/rate',
                  body: { scores: Object.fromEntries(filled.map(([k, v]) => [k, Number(v)])), on: todayIso(), by },
                },
                {
                  onSuccess: () => {
                    setRating({})
                    toast('Ratings saved for today', 'success')
                  },
                  onError: fail,
                },
              )
            }
          >
            Save today’s ratings
          </button>
          <button type="button" className="btn-gray btn-sm" disabled={act.isPending} onClick={() => ask('/goals/ask-rating', 'The rating')}>
            <Send aria-hidden /> Ask {first} to rate them
          </button>
          {active.length < max_goals && (
            <button type="button" className="btn-plain btn-sm" disabled={act.isPending} onClick={() => ask('/goals/ask', 'The question')}>
              Ask for another goal
            </button>
          )}
        </div>
        {active.length < max_goals && (
          <AddGoal value={text} onChange={setText} busy={act.isPending} onAdd={() =>
            act.mutate({ path: '/goals', body: { text, by } }, { onSuccess: () => setText(''), onError: fail })
          } />
        )}
      </Group>

      {ended.length > 0 && (
        <p className="meta">
          Ended: {ended.map((g) => g.text).join(' · ')}
        </p>
      )}
    </div>
  )
}

function AddGoal({ value, onChange, onAdd, busy }: { value: string; onChange: (v: string) => void; onAdd: () => void; busy: boolean }) {
  return (
    <div className="mt-3 flex w-full flex-wrap items-center gap-2">
      <input
        className="field min-w-[14rem] flex-1"
        placeholder="Add a goal in their words"
        maxLength={120}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && value.trim()) onAdd()
        }}
        aria-label="A goal in the person's words"
      />
      <button type="button" className="btn-gray btn-sm" disabled={!value.trim() || busy} onClick={onAdd}>
        <Plus aria-hidden /> Add
      </button>
    </div>
  )
}

function GoalRow({ goal, value, onRate, onEnd }: { goal: PtGoal; value: string; onRate: (v: string) => void; onEnd: () => void }) {
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1">
      <div className="min-w-0">
        <p className="text-copy text-ink">{goal.text}</p>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
          {goal.ratings.length === 0 ? (
            <span className="meta">Not rated yet</span>
          ) : (
            <>
              <ol className="flex items-end gap-1" aria-label={`Ratings: ${goal.ratings.map((r) => r.score).join(', ')}`}>
                {goal.ratings.slice(-8).map((r, i) => (
                  <li
                    key={i}
                    title={`${r.score}/10 · ${dayText(r.on)} · ${r.source === 'clinic' ? 'at a visit' : 'their own'}`}
                    className="w-2 rounded-sm bg-brand/70"
                    style={{ height: `${4 + r.score * 2}px` }}
                  />
                ))}
              </ol>
              <span className="text-label text-secondary tabular-nums">
                {goal.first !== goal.latest && goal.first != null ? `${goal.first} → ` : ''}
                <span className="font-medium text-ink">{goal.latest}</span>/10
                {goal.latest_on ? ` · ${dayText(goal.latest_on)}` : ''}
              </span>
            </>
          )}
        </div>
      </div>
      <div className="flex items-center gap-1.5">
        <input
          type="number"
          min={0}
          max={10}
          inputMode="numeric"
          placeholder="0–10"
          className="field !h-9 !min-h-0 !w-[4.5rem] !px-2 !py-0 text-center"
          value={value}
          onChange={(e) => onRate(e.target.value)}
          aria-label={`Rate today: ${goal.text}`}
        />
        <button type="button" className="btn-icon btn-sm" onClick={onEnd} aria-label={`End the goal: ${goal.text}`} title="End this goal">
          <X aria-hidden />
        </button>
      </div>
    </li>
  )
}
