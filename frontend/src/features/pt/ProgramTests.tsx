import { Plus, Ruler, Send, Trash2 } from 'lucide-react'
import { useState } from 'react'
import {
  dayText,
  usePtAction,
  type PtCatalog,
  type PtChart,
  type PtMeasure,
  type PtTest,
} from '../../api/pt'
import Disclosure from '../../components/Disclosure'
import { useToast } from '../../components/Toast'
import { Group, Pill } from './ptBits'
import { errorText, sentLine, signed, todayIso } from './ptWords'

/** Tests and measures: the numbers a therapist types on a test day, the
 *  holds a person times at home, and the scores of outcome measures.
 *
 *  A number is shown as a number. Two sides of one test on one day are set
 *  beside each other as a ratio; a score's change is set beside a published
 *  threshold, with its source. Nothing here says a person is ready for
 *  anything: that reading is the therapist's. */
export default function ProgramTests({
  patientId,
  first,
  data,
  by,
  catalog,
}: {
  patientId: string
  first: string
  data: PtChart
  by: string
  catalog: PtCatalog | undefined
}) {
  return (
    <div className="grid gap-x-8 gap-y-6 lg:grid-cols-2">
      <Tests patientId={patientId} first={first} data={data} by={by} catalog={catalog} />
      <Measures patientId={patientId} first={first} data={data} by={by} />
    </div>
  )
}

const num = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1))
const SIDE: Record<string, string> = { left: 'L', right: 'R', both: 'Both', na: '' }

function TestRow({ test, onRemove }: { test: PtTest; onRemove: (id: number) => void }) {
  return (
    <li>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <p className="text-copy font-medium text-ink">{test.label}</p>
        <p className="text-label text-secondary tabular-nums">
          {test.change != null && (
            <>
              {signed(Number(num(test.change)))} {test.unit} since {dayText(test.days[0].on)}
            </>
          )}
          {test.hold && <span className="ml-1.5">· timed at home</span>}
        </p>
      </div>
      <table className="mt-1 w-full text-left text-copy tabular-nums">
        <tbody>
          {test.days.map((d) => (
            <tr key={d.on} className="border-t border-line first:border-t-0">
              <th scope="row" className="w-28 py-1 pr-2 font-normal text-secondary">
                {dayText(d.on)}
              </th>
              <td className="py-1 text-ink">
                {d.results.map((r) => (
                  <span key={r.id} className="group mr-3 inline-flex items-center gap-1">
                    {SIDE[r.side] && <span className="text-secondary">{SIDE[r.side]}</span>}
                    {num(r.value)} {r.unit}
                    <button
                      type="button"
                      className="grid h-5 w-5 place-items-center rounded-full text-faint opacity-0 hover:text-risk-high-ink focus:opacity-100 group-hover:opacity-100"
                      aria-label={`Remove ${test.label} ${SIDE[r.side]} ${num(r.value)} from ${dayText(d.on)}`}
                      onClick={() => onRemove(r.id)}
                    >
                      <Trash2 aria-hidden size={12} />
                    </button>
                  </span>
                ))}
              </td>
              <td className="py-1 text-right text-secondary">
                {d.left_of_right_pct != null && `left is ${d.left_of_right_pct}% of right`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </li>
  )
}

function Tests({ patientId, first, data, by, catalog }: {
  patientId: string
  first: string
  data: PtChart
  by: string
  catalog: PtCatalog | undefined
}) {
  const toast = useToast()
  const act = usePtAction(patientId)
  const kinds = catalog?.tests ?? data.tests.kinds
  const [kind, setKind] = useState('isometric_knee_extension')
  const [left, setLeft] = useState('')
  const [right, setRight] = useState('')
  const [value, setValue] = useState('')
  const [label, setLabel] = useState('')
  const [unit, setUnit] = useState('')
  const [on, setOn] = useState(todayIso())
  const [hold, setHold] = useState('plank_hold')
  const info = kinds.find((k) => k.key === kind)
  const fail = (e: unknown) => toast(errorText(e), 'warning')
  const entries = info?.sided
    ? ([['left', left], ['right', right]] as const).filter(([, v]) => v !== '')
    : value !== '' ? ([['na', value]] as const) : []

  const save = async () => {
    try {
      for (const [side, v] of entries) {
        await act.mutateAsync({
          path: '/tests',
          body: { kind, side, value: Number(v), tested_on: on, label: label || null, unit: unit || null, by },
        })
      }
      setLeft('')
      setRight('')
      setValue('')
      toast('Result saved', 'success')
    } catch (e) {
      fail(e)
    }
  }

  return (
    <Group label="Tests">
      {data.tests.tests.length === 0 ? (
        <p className="text-copy text-secondary">
          No results yet. Type what the test day measured (a force plate, a hop, a rep max) and it sits here beside
          the load and the pain between visits.
        </p>
      ) : (
        <ul className="space-y-4">
          {data.tests.tests.map((t) => (
            <TestRow
              key={`${t.kind}-${t.label}`}
              test={t}
              onRemove={(id) => act.mutate({ path: `/tests/${id}`, method: 'DELETE' }, { onError: fail })}
            />
          ))}
        </ul>
      )}
      <Disclosure label="Add a result" className="mt-2" defaultOpen={data.tests.tests.length === 0}>
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <select className="field !w-auto max-w-full" value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Test">
            {kinds.map((k) => (
              <option key={k.key} value={k.key}>
                {k.label}
                {k.unit ? ` (${k.unit})` : ''}
              </option>
            ))}
          </select>
          {kind === 'custom' && (
            <>
              <input className="field !w-40" placeholder="Name of the test" value={label} onChange={(e) => setLabel(e.target.value)} aria-label="Name of the test" />
              <input className="field !w-20" placeholder="Unit" value={unit} onChange={(e) => setUnit(e.target.value)} aria-label="Unit" />
            </>
          )}
          {kind === 'strength_rm' && (
            <input className="field !w-40" placeholder="Lift, e.g. Squat 3RM" value={label} onChange={(e) => setLabel(e.target.value)} aria-label="Lift" />
          )}
          {info?.sided ? (
            <>
              <input type="number" min={0} className="field !w-24" placeholder="Left" value={left} onChange={(e) => setLeft(e.target.value)} aria-label="Left" />
              <input type="number" min={0} className="field !w-24" placeholder="Right" value={right} onChange={(e) => setRight(e.target.value)} aria-label="Right" />
            </>
          ) : (
            <input type="number" min={0} className="field !w-28" placeholder="Result" value={value} onChange={(e) => setValue(e.target.value)} aria-label="Result" />
          )}
          <input type="date" className="field !w-auto" value={on} max={todayIso()} onChange={(e) => setOn(e.target.value)} aria-label="Tested on" />
          <button type="button" className="btn-tinted btn-sm" disabled={entries.length === 0 || act.isPending} onClick={() => void save()}>
            <Plus aria-hidden /> Save
          </button>
        </div>
      </Disclosure>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="text-label text-secondary">Timed at home:</span>
        <select className="field !h-8 !min-h-0 !w-auto !py-0 text-label" value={hold} onChange={(e) => setHold(e.target.value)} aria-label="Hold">
          {kinds.filter((k) => k.hold).map((k) => (
            <option key={k.key} value={k.key}>
              {k.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="btn-gray btn-sm"
          disabled={act.isPending}
          onClick={() =>
            act.mutate(
              { path: '/tests/ask-hold', body: { kind: hold, by } },
              { onSuccess: (r) => toast(...sentLine(first, r.sent, 'The timed hold')), onError: fail },
            )
          }
        >
          <Send aria-hidden /> Ask {first} to time it
        </button>
      </div>
    </Group>
  )
}

function MeasureRow({ m, patientId, first, by }: { m: PtMeasure; patientId: string; first: string; by: string }) {
  const toast = useToast()
  const act = usePtAction(patientId)
  const [total, setTotal] = useState('')
  const fail = (e: unknown) => toast(errorText(e), 'warning')
  const change = m.read?.change
  return (
    <li>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="text-copy font-medium text-ink" title={m.about}>
          {m.name}
        </p>
        {m.schedule?.active && (
          <span className="meta">
            every {m.schedule.every_days} days · next {dayText(m.schedule.next_due)}
          </span>
        )}
      </div>
      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-copy tabular-nums">
        <span className="text-ink">
          {m.scores.map((s) => num(s.total)).join(' → ') || 'No score yet'}
        </span>
        <span className="text-secondary">
          {m.scores.length > 0 && `(${m.low}–${m.high}, ${m.higher_is_better ? 'higher' : 'lower'} is better)`}
        </span>
        {change && (
          <Pill
            tone={change.direction === 'worse' ? (change.past_threshold ? 'alert' : 'warn') : change.past_threshold ? 'brand' : 'plain'}
            title={m.threshold != null ? `${m.threshold_kind}: ${m.threshold} points. ${m.source}` : m.note}
          >
            {signed(change.delta)} · {change.direction}
            {m.threshold != null && ` · ${change.past_threshold ? 'past' : 'inside'} ${m.threshold}`}
          </Pill>
        )}
      </div>
      {m.threshold != null && m.source && (
        <p className="meta mt-0.5">
          {m.threshold_is_clinic ? 'The clinic’s own threshold' : m.threshold_kind}: {m.threshold} points
          {!m.threshold_is_clinic && `. ${m.source}`}
        </p>
      )}
      <div className="mt-1.5 flex flex-wrap items-center gap-2">
        {m.key !== 'psfs' && (
          <>
            <input
              type="number"
              min={m.low}
              max={m.high}
              className="field !h-8 !min-h-0 !w-24 !py-0 text-label"
              placeholder="Score"
              value={total}
              onChange={(e) => setTotal(e.target.value)}
              aria-label={`${m.short} score today`}
            />
            <button
              type="button"
              className="btn-gray btn-sm"
              disabled={total === '' || act.isPending}
              onClick={() =>
                act.mutate(
                  { path: `/outcomes/${m.key}/scores`, body: { total: Number(total), by } },
                  { onSuccess: () => setTotal(''), onError: fail },
                )
              }
            >
              Save
            </button>
          </>
        )}
        <button
          type="button"
          className="btn-plain btn-sm"
          disabled={act.isPending}
          onClick={() =>
            act.mutate(
              { path: `/outcomes/${m.key}/ask`, body: { by } },
              { onSuccess: (r) => toast(...sentLine(first, r.sent, m.short)), onError: fail },
            )
          }
        >
          <Send aria-hidden /> Ask {first}
        </button>
      </div>
    </li>
  )
}

function Measures({ patientId, first, data, by }: { patientId: string; first: string; data: PtChart; by: string }) {
  const toast = useToast()
  const act = usePtAction(patientId)
  const [add, setAdd] = useState('')
  const [every, setEvery] = useState('14')
  const { measures, instruments } = data.outcomes
  const have = new Set(measures.map((m) => m.key))
  const rest = instruments.filter((i) => !have.has(i.key) && i.key !== 'psfs')
  return (
    <Group label="Outcome measures">
      {measures.length === 0 ? (
        <p className="text-copy text-secondary">
          None yet. Put a measure on a rhythm and {first} is asked for it when it comes due; each score is read
          against a published change threshold, with its source.
        </p>
      ) : (
        <ul className="space-y-4">
          {measures.map((m) => (
            <MeasureRow key={m.key} m={m} patientId={patientId} first={first} by={by} />
          ))}
        </ul>
      )}
      {rest.length > 0 && (
        <Disclosure label="Add a measure" className="mt-2">
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <select className="field !w-auto max-w-full" value={add} onChange={(e) => setAdd(e.target.value)} aria-label="Measure">
              <option value="">Choose a measure</option>
              {rest.map((i) => (
                <option key={i.key} value={i.key}>
                  {i.name}
                </option>
              ))}
            </select>
            <label className="inline-flex items-center gap-1.5 text-label text-secondary">
              every
              <input type="number" min={1} max={180} className="field !h-8 !min-h-0 !w-16 !py-0 text-center text-label" value={every} onChange={(e) => setEvery(e.target.value)} aria-label="Days between scores" />
              days
            </label>
            <button
              type="button"
              className="btn-tinted btn-sm"
              disabled={!add || act.isPending}
              onClick={() =>
                act.mutate(
                  { path: `/outcomes/${add}/schedule`, method: 'PUT', body: { every_days: Number(every) || 14, by } },
                  { onSuccess: () => setAdd(''), onError: (e) => toast(errorText(e), 'warning') },
                )
              }
            >
              <Ruler aria-hidden /> Add
            </button>
          </div>
          {add && (
            <p className="meta mt-1.5">
              {instruments.find((i) => i.key === add)?.about} {instruments.find((i) => i.key === add)?.note}
            </p>
          )}
        </Disclosure>
      )}
    </Group>
  )
}
