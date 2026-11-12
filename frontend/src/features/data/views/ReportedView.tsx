import { ClipboardList, Download, Film } from 'lucide-react'
import { useState } from 'react'
import {
  downloadExport,
  useReported,
  type ReportedExerciseDay,
  type ReportedQuestion,
  type ReportedResponse,
  type ReportedRow,
} from '../../../api/data'
import SectionCard from '../../../components/SectionCard'
import SegmentedControl from '../../../components/SegmentedControl'
import Tile from '../../../components/Tile'
import { useToast } from '../../../components/Toast'
import { shortDate } from '../../../lib/format'
import { Fact, Facts, ViewState } from '../DataBits'
import { loadText, num } from '../dataFormat'

/** The grid a clinic otherwise keeps in a spreadsheet: one row per day,
 *  newest first, with what the person answered in their check-in and what
 *  they did on the exercise calendar that day, prescribed against done. A
 *  day with nothing on it is still a row: a gap is information. */

type Window = '14' | '30' | '60'

const WORDS: Record<string, string> = {
  yes: 'Yes',
  no: 'No',
  well: 'Well',
  rough: 'Rough',
  all: 'All',
  some: 'Some',
  none: 'None',
}

function answer(value: string | number | undefined, question: ReportedQuestion): string {
  if (value === undefined || value === null || value === '') return '—'
  if (typeof value === 'number') return question.kind === 'scale' ? `${value}` : value.toLocaleString()
  return WORDS[value] ?? value
}

/** An answer that a reader should not have to hunt for: yes to new swelling
 *  or new pain. Marked with a tint and the word, never colour alone. */
function isRaised(question: ReportedQuestion, value: string | number | undefined): boolean {
  return (question.id === 'new_pain' || question.id === 'swelling') && value === 'yes'
}

function ExerciseCell({ day, unit }: { day: ReportedExerciseDay | null; unit: 'kg' | 'lb' }) {
  if (!day) return <span className="text-copy text-secondary">—</span>
  const over = day.items.filter((i) => i.over)
  return (
    <div className="min-w-[14rem]">
      <p className="text-copy text-ink">
        <span className="tabular-nums">
          {day.done} of {day.assigned}
        </span>{' '}
        done
        {day.skipped > 0 && <span className="text-secondary"> · {day.skipped} skipped</span>}
        {day.missed > 0 && <span className="text-secondary"> · {day.missed} missed</span>}
      </p>
      {day.done > 0 && (
        <p className="meta">
          {day.pain_before != null && day.pain_after != null
            ? `Pain ${num(day.pain_before, 0)} → ${day.pain_after}`
            : day.pain_after != null
              ? `Pain after ${day.pain_after}`
              : 'No pain score'}
          {day.effort != null &&
            ` · effort ${day.effort}${day.effort_target != null ? ` (target ${day.effort_target})` : ''}`}
          {day.minutes != null && ` · ${day.minutes} min`}
          {day.load_done > 0 && ` · ${loadText(day.load_done, unit)} moved`}
        </p>
      )}
      {over.map((item) => (
        <p key={item.id} className="mt-1">
          <span className="chip bg-risk-med-tint normal-case tracking-label text-risk-med-ink">
            More than prescribed
          </span>{' '}
          <span className="text-label text-ink">
            {item.title}: {item.line}
          </span>
        </p>
      ))}
      {day.clips > 0 && (
        <p className="meta mt-1 inline-flex items-center gap-1">
          <Film aria-hidden size={12} /> {day.clips} {day.clips === 1 ? 'clip' : 'clips'} sent
        </p>
      )}
    </div>
  )
}

function Grid({ data }: { data: ReportedResponse }) {
  const columns = data.questions.filter((q) => q.kind !== 'text')
  const note = data.questions.find((q) => q.kind === 'text')
  const hasLoad = data.rows.some((r) => r.load != null)
  const hasExercises = data.rows.some((r) => r.exercises)
  return (
    <div className="max-h-[40rem] overflow-auto">
      <table className="w-full min-w-[820px] border-separate border-spacing-0 text-left">
        <caption className="sr-only">What was reported and done, one row per day, newest first</caption>
        <thead className="sticky top-0 z-10 bg-panel">
          <tr>
            <th scope="col" className="px-4 pb-2 pt-3 text-label font-medium text-secondary">
              Day
            </th>
            {columns.map((q) => (
              <th key={q.id} scope="col" className="px-3 pb-2 pt-3 text-label font-medium text-secondary" title={q.prompt}>
                {q.label}
              </th>
            ))}
            {hasLoad && (
              <th scope="col" className="px-3 pb-2 pt-3 text-label font-medium text-secondary" title="Effort × minutes, as reported">
                Training load
              </th>
            )}
            {hasExercises && (
              <th scope="col" className="px-3 pb-2 pt-3 text-label font-medium text-secondary">
                Exercise calendar
              </th>
            )}
            {note && (
              <th scope="col" className="px-4 pb-2 pt-3 text-label font-medium text-secondary">
                Note
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row) => (
            <Row
              key={row.date}
              row={row}
              columns={columns}
              note={note}
              hasLoad={hasLoad}
              hasExercises={hasExercises}
              unit={data.load_unit}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Row({
  row,
  columns,
  note,
  hasLoad,
  hasExercises,
  unit,
}: {
  row: ReportedRow
  columns: ReportedQuestion[]
  note: ReportedQuestion | undefined
  hasLoad: boolean
  hasExercises: boolean
  unit: 'kg' | 'lb'
}) {
  const checked = row.checkins.length > 0
  return (
    <tr className="align-top">
      <th scope="row" className="whitespace-nowrap border-t border-hairline px-4 py-2.5 text-left font-normal">
        <span className="text-copy tabular-nums text-ink">{shortDate(row.date)}</span>
        <span className="meta block">{checked ? `Day ${row.day}` : 'No check-in'}</span>
      </th>
      {columns.map((q) => {
        const value = row.answers[q.id]
        return (
          <td key={q.id} className="border-t border-hairline px-3 py-2.5 text-copy tabular-nums">
            {isRaised(q, value) ? (
              <span className="chip bg-risk-med-tint normal-case tracking-label text-risk-med-ink">Yes</span>
            ) : (
              <span className={value === undefined ? 'text-secondary' : 'text-ink'}>{answer(value, q)}</span>
            )}
          </td>
        )
      })}
      {hasLoad && (
        <td className="border-t border-hairline px-3 py-2.5 text-copy tabular-nums text-ink">
          {row.load == null ? <span className="text-secondary">—</span> : `${num(row.load, 0)} AU`}
        </td>
      )}
      {hasExercises && (
        <td className="border-t border-hairline px-3 py-2.5">
          <ExerciseCell day={row.exercises} unit={unit} />
        </td>
      )}
      {note && (
        <td className="max-w-[22rem] border-t border-hairline px-4 py-2.5 text-copy text-ink">
          {row.answers[note.id] ?? <span className="text-secondary">—</span>}
        </td>
      )}
    </tr>
  )
}

export default function ReportedView({ patientId }: { patientId: string }) {
  const [window, setWindow] = useState<Window>('30')
  const [exporting, setExporting] = useState(false)
  const toast = useToast()
  const reported = useReported(patientId, Number(window))
  const data = reported.data
  const empty =
    data != null && data.summary.checkin_days === 0 && data.summary.exercises.assigned === 0

  const onExport = async () => {
    setExporting(true)
    try {
      await downloadExport(patientId, { kind: 'reported', days: window }, `${patientId}-reported.csv`)
    } catch {
      toast('The export could not be made. Try again.', 'warning')
    } finally {
      setExporting(false)
    }
  }

  return (
    <ViewState
      loading={reported.isLoading}
      error={reported.isError}
      onRetry={() => void reported.refetch()}
      what="The reported grid"
    >
      {data && (
        <div className="space-y-stack">
          <SectionCard
            title="Reported, day by day"
            icon={<Tile size="sm" family="blue" icon={<ClipboardList />} />}
            aside={`${shortDate(data.since)} to ${shortDate(data.as_of)}`}
            action={
              <span className="flex items-center gap-2">
                <SegmentedControl<Window>
                  options={[
                    { key: '14', label: '14 days' },
                    { key: '30', label: '30 days' },
                    { key: '60', label: '60 days' },
                  ]}
                  value={window}
                  onChange={setWindow}
                  size="sm"
                  role="radiogroup"
                  aria-label="Window"
                />
                <button type="button" className="btn-plain btn-sm" onClick={onExport} disabled={exporting || empty}>
                  <Download aria-hidden size={16} /> {exporting ? 'Preparing…' : 'Export CSV'}
                </button>
              </span>
            }
          >
            {empty ? (
              <p className="text-copy text-secondary">
                Nothing was reported and nothing was on the exercise calendar in this window.
              </p>
            ) : (
              <Facts>
                <Fact label="Days with a check-in" value={data.summary.checkin_days} hint={`of ${data.days}`} />
                {data.summary.pain && (
                  <Fact
                    label="Pain, this week"
                    value={num(data.summary.pain.mean_7, 1)}
                    hint={
                      data.summary.pain.mean_prior_7 != null
                        ? `${num(data.summary.pain.mean_prior_7, 1)} the week before`
                        : 'of 10'
                    }
                  />
                )}
                {data.summary.exercises.assigned > 0 && (
                  <Fact
                    label="Exercises done"
                    value={data.summary.exercises.done}
                    hint={`of ${data.summary.exercises.assigned}`}
                  />
                )}
                {data.summary.exercises.over > 0 && (
                  <Fact label="More than prescribed" value={data.summary.exercises.over} hint="sessions" />
                )}
              </Facts>
            )}
          </SectionCard>
          {!empty && (
            <SectionCard flush>
              <Grid data={data} />
            </SectionCard>
          )}
          <p className="meta px-1">
            Check-in answers are read back from the conversation as the person gave them; the
            training columns are their own training, apart from the clinic’s program on the
            exercise calendar. “More than prescribed” compares what they logged with the dose
            written for that day; it describes the session and makes no judgement about it.
          </p>
        </div>
      )}
    </ViewState>
  )
}
