import { ArrowRight, Check, CircleHelp, Flag, Inbox, MessageSquare } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useMoveQuestion, usePtCatalog, useQuestions, type PtQuestion } from '../../api/pt'
import Avatar from '../../components/Avatar'
import EmptyState from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { relativeTime } from '../../lib/format'
import ExercisesNav from '../hep/ExercisesNav'
import { CALENDAR } from '../hep/paths'
import { GroupFooter, GroupHeader, SettingsHero } from '../settings/Switch'
import { ActingAs, Pill } from './ptBits'
import { errorText, useActingAs } from './ptWords'

/** `/calendar/questions` — what the clinic's people asked, sorted into the
 *  ones for today and the ones for the weekly block. A rule sorts them (the
 *  clinic's word list, under Rules); a clinician can move any line either
 *  way, or mark it dealt with. Nothing on this page replies to anyone: the
 *  answer is written on the chart, by a person. */
export default function QuestionsPage() {
  const questions = useQuestions()
  const catalog = usePtCatalog()
  const team = catalog.data?.care_team ?? []
  const [by, setBy] = useActingAs(team)
  const today = questions.data?.today ?? []
  const weekly = questions.data?.weekly ?? []
  const done = questions.data?.done ?? []

  return (
    <div className="pb-10">
      <SettingsHero
        nav={<ExercisesNav />}
        icon={<CircleHelp />}
        title="Questions"
        decor={[<MessageSquare key="m" />, <Inbox key="i" />, <Check key="c" />]}
      >
        What your lifters asked, sorted by rule: the ones that should not wait, and the ones that can sit until your
        weekly block. Move a line if the rule got it wrong. Nothing here answers anyone; open the chart to reply.
      </SettingsHero>

      <div className="mt-6 flex justify-end">
        <ActingAs team={team} value={by} onChange={setBy} />
      </div>

      {questions.isLoading ? (
        <div className="mt-4 grid gap-6 lg:grid-cols-2">
          <SkeletonCard rows={3} />
          <SkeletonCard rows={3} />
        </div>
      ) : (
        <div className="mt-4 grid items-start gap-6 lg:grid-cols-2">
          <Column
            title="Today"
            note="A question with one of your always-today words in it, or a line that matched a red flag."
            items={today}
            other="weekly"
            otherLabel="Can wait for the weekly block"
            by={by}
            empty="Nothing for today."
          />
          <Column
            title="Weekly block"
            note="Questions that can be answered together, once a week."
            items={weekly}
            other="today"
            otherLabel="Move to today"
            by={by}
            empty="Nothing waiting for the weekly block."
          />
        </div>
      )}

      {done.length > 0 && (
        <section className="mt-8">
          <GroupHeader>Dealt with</GroupHeader>
          <ul className="panel divide-y divide-line">
            {done.map((q) => (
              <li key={q.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-copy">
                <span className="font-medium text-ink">{q.patient_name}</span>
                <span className="min-w-0 flex-1 truncate text-secondary">{q.text}</span>
                <span className="meta">{relativeTime(q.done_at)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <GroupFooter>
        The words that send a question to today are the clinic’s own:{' '}
        <Link to={CALENDAR.rules} className="font-medium text-brand-ink">
          edit them under Rules
        </Link>
        .
      </GroupFooter>
    </div>
  )
}

function Column({
  title,
  note,
  items,
  other,
  otherLabel,
  by,
  empty,
}: {
  title: string
  note: string
  items: PtQuestion[]
  other: 'today' | 'weekly'
  otherLabel: string
  by: string
  empty: string
}) {
  const toast = useToast()
  const move = useMoveQuestion()
  const fail = (e: unknown) => toast(errorText(e), 'warning')
  return (
    <section>
      <GroupHeader aside={<span className="meta tabular-nums">{items.length}</span>}>{title}</GroupHeader>
      {items.length === 0 ? (
        <EmptyState variant="card" icon={<Inbox />} title={empty} className="!py-8" />
      ) : (
        <ul className="space-y-3">
          {items.map((q) => (
            <li key={q.id} className={`panel px-4 py-3.5 ${q.red_flag ? 'ring-1 ring-risk-high-ink/40' : ''}`}>
              <div className="flex items-center gap-2.5">
                <Avatar name={q.patient_name} size="sm" />
                <Link to={`/patients/${encodeURIComponent(q.patient_id)}#messages`} className="min-w-0 truncate text-copy font-medium text-ink hover:underline">
                  {q.patient_name}
                </Link>
                {q.red_flag && (
                  <Pill tone="alert">
                    <Flag aria-hidden size={12} /> Red flag
                  </Pill>
                )}
                <span className="meta ml-auto shrink-0">
                  {relativeTime(q.created_at)} · {q.channel === 'sms' ? 'by text' : 'in the app'}
                </span>
              </div>
              <p className="mt-2 text-copy-lg text-ink">{q.text}</p>
              <div className="mt-2.5 flex flex-wrap items-center gap-2">
                <Link to={`/patients/${encodeURIComponent(q.patient_id)}#messages`} className="btn-tinted btn-sm">
                  Open the chart to answer <ArrowRight aria-hidden size={14} />
                </Link>
                {!q.red_flag && (
                  <button
                    type="button"
                    className="btn-plain btn-sm"
                    disabled={move.isPending}
                    onClick={() => move.mutate({ id: q.id, triage: other, by }, { onError: fail })}
                  >
                    {otherLabel}
                  </button>
                )}
                <button
                  type="button"
                  className="btn-plain btn-sm"
                  disabled={move.isPending}
                  onClick={() => move.mutate({ id: q.id, done: true, by }, { onError: fail })}
                >
                  <Check aria-hidden size={14} /> Dealt with
                </button>
                <span className="meta ml-auto">
                  {q.sorted_by === 'rule' ? 'sorted by rule' : `moved by ${q.sorted_by_name ?? 'a clinician'}`}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
      <p className="meta mt-2 px-1">{note}</p>
    </section>
  )
}
