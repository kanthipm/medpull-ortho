import { CalendarClock, Check, ChevronRight, Flag, Plus, Route, Send, X } from 'lucide-react'
import { useState } from 'react'
import { ApiError } from '../../api/client'
import {
  dayText,
  firstName,
  useProtocols,
  usePtAction,
  usePtCatalog,
  usePtChart,
  visitText,
  type PtChart,
  type PtMorning,
  type PtPhase,
} from '../../api/pt'
import { useHealth } from '../../api/queries'
import Disclosure from '../../components/Disclosure'
import SectionCard from '../../components/SectionCard'
import SegmentedControl from '../../components/SegmentedControl'
import { SkeletonCard } from '../../components/Skeleton'
import Tile from '../../components/Tile'
import { useToast } from '../../components/Toast'
import ProgramFunction from './ProgramFunction'
import ProgramTests from './ProgramTests'
import ProgramTrainer from './ProgramTrainer'
import { ActingAs, Group, Pill } from './ptBits'
import { errorText, sentLine, useActingAs } from './ptWords'

type Tab = 'overview' | 'function' | 'tests' | 'trainer'

/** The chart's Program card: what the clinic keeps about this person between
 *  visits, beyond the exercise calendar. Four views of one record.
 *
 *    Overview   the phase and its criteria (a clinician ticks them and moves
 *               the person on: the software never does), the visits, where
 *               it hurts (and any area named since the evaluation), how the
 *               mornings after loaded sessions have settled, the week's word
 *    Function   the person's own goals and how they rate them
 *    Tests      test-day numbers, timed holds, outcome measures
 *    Trainer    the page a trainer reads, once the person agrees to share it
 *
 *  Shown on a clinic chart whenever the exercise calendar is on. Nothing
 *  here is written by a model, and nothing here says what a number means. */
export default function ProgramCard({ patientId, patientName }: { patientId: string; patientName: string }) {
  const hep = useHealth().data?.hep === true
  const chart = usePtChart(patientId, hep)
  const catalog = usePtCatalog(hep)
  const [tab, setTab] = useState<Tab>('overview')
  const team = catalog.data?.care_team ?? []
  const [by, setBy] = useActingAs(team)
  if (!hep) return null
  if (chart.isLoading) return <SkeletonCard rows={3} />
  if (chart.isError || !chart.data) return null
  const data = chart.data
  const first = firstName(patientName)
  const phase = data.phases.current
  const waiting = data.asks.length

  return (
    <SectionCard
      title="Program"
      icon={<Tile size="sm" family="violet" icon={<Route />} />}
      aside={
        <span className="flex flex-wrap items-center justify-end gap-2">
          {phase && data.phases.number != null && (
            <Pill tone="brand">
              Phase {data.phases.number} of {data.phases.count}
            </Pill>
          )}
          {waiting > 0 && (
            <Pill title={data.asks.map((a) => a.title).join(' · ')}>
              {waiting} asked, not answered
            </Pill>
          )}
          <ActingAs team={team} value={by} onChange={setBy} />
        </span>
      }
    >
      <SegmentedControl<Tab>
        options={[
          { key: 'overview', label: 'Overview' },
          { key: 'function', label: 'Function' },
          { key: 'tests', label: 'Tests & measures' },
          { key: 'trainer', label: 'Trainer' },
        ]}
        value={tab}
        onChange={setTab}
        size="sm"
        aria-label="Program views"
        className="mb-4"
      />
      {tab === 'overview' && <Overview patientId={patientId} first={first} data={data} by={by} />}
      {tab === 'function' && <ProgramFunction patientId={patientId} first={first} data={data} by={by} />}
      {tab === 'tests' && (
        <ProgramTests patientId={patientId} first={first} data={data} by={by} catalog={catalog.data} />
      )}
      {tab === 'trainer' && <ProgramTrainer patientId={patientId} first={first} data={data} by={by} />}
    </SectionCard>
  )
}

function Overview({ patientId, first, data, by }: { patientId: string; first: string; data: PtChart; by: string }) {
  return (
    <div className="grid gap-x-8 gap-y-6 lg:grid-cols-2">
      <Phases patientId={patientId} first={first} data={data} by={by} />
      <div className="space-y-6">
        <Visits patientId={patientId} data={data} by={by} />
        <Areas patientId={patientId} first={first} data={data} by={by} />
      </div>
      <Mornings patientId={patientId} first={first} data={data} by={by} />
      <Week patientId={patientId} first={first} data={data} by={by} />
    </div>
  )
}

// --- phases ---------------------------------------------------------------------------

function Phases({ patientId, first, data, by }: { patientId: string; first: string; data: PtChart; by: string }) {
  const toast = useToast()
  const act = usePtAction(patientId)
  const protocols = useProtocols(data.phases.count === 0)
  const [pick, setPick] = useState('')
  const [unmet, setUnmet] = useState<string | null>(null)
  const { phases, current, number, count, finished, protocol_name } = data.phases

  if (count === 0) {
    const list = protocols.data?.protocols ?? []
    return (
      <Group label="Phase">
        <p className="text-copy text-secondary">
          {first} is not on a protocol. Start one and its phases show here, each with the criteria
          you tick before the next.
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <select
            className="field !w-auto min-w-[14rem] flex-1"
            value={pick}
            onChange={(e) => setPick(e.target.value)}
            aria-label="Protocol"
          >
            <option value="">{list.length ? 'Choose a protocol' : 'No protocols yet: add one under Calendar → Rules'}</option>
            {list.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn-tinted btn-sm"
            disabled={!pick || act.isPending}
            onClick={() =>
              act.mutate(
                { path: '/phases', method: 'PUT', body: { protocol_id: Number(pick), by } },
                { onError: (e) => toast(errorText(e), 'warning') },
              )
            }
          >
            Start
          </button>
        </div>
      </Group>
    )
  }

  const advance = (withUnmet: boolean) =>
    act.mutate(
      { path: '/phases/advance', body: { by, with_unmet: withUnmet } },
      {
        onSuccess: () => {
          setUnmet(null)
          toast(`${first} is on the next phase`, 'success')
        },
        onError: (e) => {
          if (e instanceof ApiError && e.status === 409) setUnmet(e.message)
          else toast(errorText(e), 'warning')
        },
      },
    )

  return (
    <Group
      label={protocol_name ?? 'Phase'}
      aside={
        <ol className="flex items-center gap-1" aria-label={`Phase ${number ?? count} of ${count}`}>
          {phases.map((p) => (
            <li
              key={p.id}
              title={`${p.name} · ${p.status}`}
              className={`h-1.5 w-6 rounded-pill ${
                p.status === 'done' ? 'bg-brand' : p.status === 'current' ? 'bg-brand/50' : 'bg-line-strong'
              }`}
            />
          ))}
        </ol>
      }
    >
      {current ? (
        <CurrentPhase patientId={patientId} phase={current} number={number ?? 1} count={count} by={by} />
      ) : (
        <p className="text-copy text-secondary">
          {finished ? `Every phase is done. ${first} has finished this protocol.` : 'No phase is under way.'}
        </p>
      )}
      {unmet && (
        <div className="mt-3 rounded-surface bg-risk-med-tint px-3 py-2.5 text-copy text-risk-med-ink" role="alert">
          <p>{unmet}</p>
          <div className="mt-2 flex gap-2">
            <button type="button" className="btn-gray btn-sm" disabled={act.isPending} onClick={() => advance(true)}>
              Move on anyway
            </button>
            <button type="button" className="btn-plain btn-sm" onClick={() => setUnmet(null)}>
              Not yet
            </button>
          </div>
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {current && !unmet && (
          <button type="button" className="btn-tinted btn-sm" disabled={!by || act.isPending} onClick={() => advance(false)}>
            {number === count ? 'Finish this phase' : 'Move to the next phase'} <ChevronRight aria-hidden size={14} />
          </button>
        )}
        {phases.some((p) => p.status === 'done') && (
          <button
            type="button"
            className="btn-plain btn-sm"
            disabled={!by || act.isPending}
            onClick={() =>
              act.mutate({ path: '/phases/back', body: { by } }, { onError: (e) => toast(errorText(e), 'warning') })
            }
          >
            Back a phase
          </button>
        )}
      </div>
      <p className="meta mt-2">A clinician moves the phase. Nothing here moves by itself.</p>
    </Group>
  )
}

function CurrentPhase({
  patientId,
  phase,
  number,
  count,
  by,
}: {
  patientId: string
  phase: PtPhase
  number: number
  count: number
  by: string
}) {
  const toast = useToast()
  const act = usePtAction(patientId)
  return (
    <div>
      <p className="text-copy-lg font-medium text-ink">
        <span className="tabular-nums text-secondary">
          {number} of {count} ·{' '}
        </span>
        {phase.name}
      </p>
      {phase.goal && <p className="text-copy text-secondary">{phase.goal}</p>}
      {phase.criteria.length > 0 ? (
        <ul className="mt-2 space-y-1.5">
          {phase.criteria.map((c, i) => (
            <li key={i}>
              <label className="flex cursor-pointer items-start gap-2.5 text-copy text-ink">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 shrink-0 accent-brand"
                  checked={c.met}
                  disabled={!by || act.isPending}
                  onChange={(e) =>
                    act.mutate(
                      { path: `/phases/${phase.id}/criteria/${i}`, body: { by, met: e.target.checked } },
                      { onError: (err) => toast(errorText(err), 'warning') },
                    )
                  }
                />
                <span>
                  {c.text}
                  {c.met && c.met_by_name && (
                    <span className="meta ml-1.5">
                      {c.met_by_name}
                      {c.met_at ? ` · ${dayText(c.met_at)}` : ''}
                    </span>
                  )}
                </span>
              </label>
            </li>
          ))}
        </ul>
      ) : (
        <p className="meta mt-2">This phase has no criteria written.</p>
      )}
    </div>
  )
}

// --- visits ---------------------------------------------------------------------------

function Visits({ patientId, data, by }: { patientId: string; data: PtChart; by: string }) {
  const toast = useToast()
  const act = usePtAction(patientId)
  const [on, setOn] = useState('')
  const [at, setAt] = useState('')
  const [kind, setKind] = useState('visit')
  const { last, next, days_since_last, days_to_next } = data.visits
  const add = () =>
    act.mutate(
      { path: '/visits', body: { on, at: at || null, kind, by } },
      {
        onSuccess: () => {
          setOn('')
          setAt('')
          toast('On the calendar', 'success')
        },
        onError: (e) => toast(errorText(e), 'warning'),
      },
    )
  return (
    <Group label="Visits">
      <dl className="space-y-1 text-copy">
        <div className="flex gap-2">
          <dt className="w-14 shrink-0 text-secondary">Next</dt>
          <dd className="text-ink">
            {next ? (
              <>
                {visitText(next)}
                {days_to_next != null && (
                  <span className="meta ml-1.5">
                    {days_to_next === 0 ? 'today' : days_to_next === 1 ? 'tomorrow' : `in ${days_to_next} days`}
                  </span>
                )}
                {next.note && <span className="block text-secondary">{next.note}</span>}
              </>
            ) : (
              <span className="text-secondary">None on the calendar</span>
            )}
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-14 shrink-0 text-secondary">Last</dt>
          <dd className="text-ink">
            {last ? (
              <>
                {visitText(last)}
                {days_since_last != null && <span className="meta ml-1.5">{days_since_last} days ago</span>}
              </>
            ) : (
              <span className="text-secondary">None on file</span>
            )}
          </dd>
        </div>
      </dl>
      <Disclosure label="Add a visit" className="mt-1.5">
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <input type="date" className="field !w-auto" value={on} onChange={(e) => setOn(e.target.value)} aria-label="Day" />
          <input type="time" className="field !w-auto" value={at} onChange={(e) => setAt(e.target.value)} aria-label="Time" />
          <select className="field !w-auto" value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Kind">
            <option value="visit">Visit</option>
            <option value="evaluation">Evaluation</option>
            <option value="test_day">Test day</option>
          </select>
          <button type="button" className="btn-tinted btn-sm" disabled={!on || act.isPending} onClick={add}>
            <CalendarClock aria-hidden /> Add
          </button>
        </div>
      </Disclosure>
    </Group>
  )
}

// --- where it hurts -------------------------------------------------------------------

function Areas({ patientId, first, data, by }: { patientId: string; first: string; data: PtChart; by: string }) {
  const toast = useToast()
  const act = usePtAction(patientId)
  const [area, setArea] = useState('')
  const [side, setSide] = useState('')
  const [source, setSource] = useState<'evaluation' | 'reported'>('evaluation')
  const { evaluation, reported, areas, midline } = data.areas
  const fresh = reported.filter((a) => a.new)
  const fail = (e: unknown) => toast(errorText(e), 'warning')
  return (
    <Group
      label="Where it hurts"
      aside={
        fresh.length > 0 ? (
          <Pill tone="warn">
            <Flag aria-hidden size={12} /> New since the last visit
          </Pill>
        ) : undefined
      }
    >
      <div className="flex flex-wrap items-center gap-1.5">
        {evaluation.length === 0 && reported.length === 0 && (
          <span className="text-copy text-secondary">No areas recorded at the evaluation yet.</span>
        )}
        {evaluation.map((a) => (
          <Pill key={a.id} title={`Recorded ${dayText(a.noted_on)}`}>
            {a.label}
            <button
              type="button"
              className="-mr-1 grid h-4 w-4 place-items-center rounded-full text-secondary hover:text-ink"
              aria-label={`Remove ${a.label}`}
              onClick={() => act.mutate({ path: `/areas/${a.id}`, method: 'DELETE' }, { onError: fail })}
            >
              <X aria-hidden size={12} />
            </button>
          </Pill>
        ))}
      </div>
      {reported.length > 0 && (
        <ul className="mt-2 space-y-1.5">
          {reported.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-copy">
              <Pill tone={a.new ? 'warn' : 'plain'}>{a.label}</Pill>
              <span className="text-secondary">
                {first} named it {dayText(a.noted_on)}
                {a.seen_on ? ` · seen ${dayText(a.seen_on)}` : ''}
                {a.note ? ` · “${a.note}”` : ''}
              </span>
              {a.new && (
                <button
                  type="button"
                  className="btn-plain btn-sm"
                  onClick={() => act.mutate({ path: `/areas/${a.id}/seen`, body: { by } }, { onError: fail })}
                >
                  <Check aria-hidden size={14} /> Seen
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      <Disclosure label="Add an area" className="mt-1.5">
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <select className="field !w-auto" value={area} onChange={(e) => setArea(e.target.value)} aria-label="Area">
            <option value="">Area</option>
            {areas.map((a) => (
              <option key={a} value={a}>
                {a[0].toUpperCase() + a.slice(1)}
              </option>
            ))}
          </select>
          {area && !midline.includes(area) && (
            <select className="field !w-auto" value={side} onChange={(e) => setSide(e.target.value)} aria-label="Side">
              <option value="">Side</option>
              <option value="left">Left</option>
              <option value="right">Right</option>
              <option value="both">Both</option>
            </select>
          )}
          <select
            className="field !w-auto"
            value={source}
            onChange={(e) => setSource(e.target.value as 'evaluation' | 'reported')}
            aria-label="When"
          >
            <option value="evaluation">At the evaluation</option>
            <option value="reported">Reported since</option>
          </select>
          <button
            type="button"
            className="btn-tinted btn-sm"
            disabled={!area || act.isPending}
            onClick={() =>
              act.mutate(
                { path: '/areas', body: { area, side: side || null, source, by } },
                {
                  onSuccess: () => {
                    setArea('')
                    setSide('')
                  },
                  onError: fail,
                },
              )
            }
          >
            <Plus aria-hidden /> Add
          </button>
        </div>
      </Disclosure>
    </Group>
  )
}

// --- the morning after ----------------------------------------------------------------

function MorningDot({ m }: { m: PtMorning }) {
  const tone =
    m.read === 'waiting'
      ? 'border border-dashed border-line-strong'
      : m.settled
        ? 'bg-brand'
        : 'bg-risk-high-ink'
  const said =
    m.read === 'waiting'
      ? 'asked, no answer yet'
      : `pain ${m.pain}/10${m.stiffer ? ', stiffer than usual' : ''} · ${m.read}`
  return (
    <li
      title={`After ${dayText(m.session_day)}: ${said}`}
      className={`h-3.5 w-3.5 rounded-full ${tone}`}
      aria-label={`After ${dayText(m.session_day)}: ${said}`}
    />
  )
}

function Mornings({ patientId, first, data, by }: { patientId: string; first: string; data: PtChart; by: string }) {
  const toast = useToast()
  const act = usePtAction(patientId)
  const { recent, answered, settled, last, can_ask } = data.morning
  const setting = data.settings.morning_check
  const ordered = [...recent].reverse()
  const fail = (e: unknown) => toast(errorText(e), 'warning')
  return (
    <Group
      label="The morning after a loaded session"
      aside={
        <label className="inline-flex items-center gap-1.5 text-label text-secondary">
          <input
            type="checkbox"
            className="h-3.5 w-3.5 accent-brand"
            checked={setting.on}
            onChange={(e) =>
              act.mutate(
                { path: '/settings', method: 'PATCH', body: { morning_check: { on: e.target.checked }, by } },
                { onError: fail },
              )
            }
          />
          Ask each time
        </label>
      }
    >
      {recent.length === 0 ? (
        <p className="text-copy text-secondary">
          Nobody has asked yet. After a session with load on it, {first} can be asked two things the next morning: the
          pain now, and whether they are stiffer than usual.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <ol className="flex items-center gap-1.5">{ordered.map((m) => <MorningDot key={m.id} m={m} />)}</ol>
            <span className="text-copy text-ink">
              {settled} of {answered} settled
            </span>
          </div>
          {last && last.read !== 'waiting' && (
            <p className="mt-1.5 text-copy text-secondary">
              After {dayText(last.session_day)}: pain {last.pain}/10
              {last.stiffer ? ', stiffer than usual' : ''} —{' '}
              <span className={last.settled ? 'text-ink' : 'font-medium text-risk-high-ink'}>{last.read}</span>
            </p>
          )}
          {last && last.read === 'waiting' && (
            <p className="mt-1.5 text-copy text-secondary">Asked about {dayText(last.session_day)}; no answer yet.</p>
          )}
        </>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
        {can_ask && (
          <button
            type="button"
            className="btn-tinted btn-sm"
            disabled={act.isPending}
            onClick={() =>
              act.mutate(
                { path: '/morning/ask', body: { by } },
                { onSuccess: (r) => toast(...sentLine(first, r.sent, 'The morning check')), onError: fail },
              )
            }
          >
            <Send aria-hidden /> Ask about this morning
          </button>
        )}
        <label className="inline-flex items-center gap-1.5 text-label text-secondary">
          Settled means pain at or under
          <input
            type="number"
            min={0}
            max={10}
            className="field !h-8 !min-h-0 !w-14 !px-2 !py-0 text-center text-label"
            defaultValue={setting.ceiling}
            key={setting.ceiling}
            aria-label="Pain ceiling"
            onBlur={(e) => {
              const ceiling = Number(e.target.value)
              if (ceiling !== setting.ceiling && ceiling >= 0 && ceiling <= 10) {
                act.mutate(
                  { path: '/settings', method: 'PATCH', body: { morning_check: { ceiling }, by } },
                  { onError: fail },
                )
              }
            }}
          />
          and no stiffer
        </label>
      </div>
    </Group>
  )
}

// --- the week -------------------------------------------------------------------------

const WENT: Record<string, string> = { better: 'Better than the week before', same: 'About the same', worse: 'Worse than the week before' }

function Week({ patientId, first, data, by }: { patientId: string; first: string; data: PtChart; by: string }) {
  const toast = useToast()
  const act = usePtAction(patientId)
  const { latest, this_week } = data.week
  const setting = data.settings.week_checkin
  const fail = (e: unknown) => toast(errorText(e), 'warning')
  const answeredThisWeek = latest?.week_start === this_week && latest.answered_at != null
  return (
    <Group
      label="The week, in their words"
      aside={
        <label className="inline-flex items-center gap-1.5 text-label text-secondary">
          <input
            type="checkbox"
            className="h-3.5 w-3.5 accent-brand"
            checked={setting.on}
            onChange={(e) =>
              act.mutate(
                { path: '/settings', method: 'PATCH', body: { week_checkin: { on: e.target.checked }, by } },
                { onError: fail },
              )
            }
          />
          Ask every Friday
        </label>
      }
    >
      {!latest ? (
        <p className="text-copy text-secondary">
          Not asked yet. Two questions before next week is written: how this week went, and what is different about the
          next one.
        </p>
      ) : latest.answered_at ? (
        <div className="text-copy">
          <p className="text-ink">
            <span className="text-secondary">Week of {dayText(latest.week_start)} · </span>
            {WENT[latest.went ?? ''] ?? 'Answered'}
          </p>
          {latest.change_note && <p className="mt-0.5 text-ink">“{latest.change_note}”</p>}
        </div>
      ) : (
        <p className="text-copy text-secondary">
          Asked {dayText(latest.asked_at)} about the week of {dayText(latest.week_start)}; no answer yet.
        </p>
      )}
      {!answeredThisWeek && (
        <button
          type="button"
          className="btn-tinted btn-sm mt-2"
          disabled={act.isPending}
          onClick={() =>
            act.mutate(
              { path: '/week/ask', body: { by } },
              { onSuccess: (r) => toast(...sentLine(first, r.sent, 'The week’s check-in')), onError: fail },
            )
          }
        >
          <Send aria-hidden /> Ask about this week
        </button>
      )}
    </Group>
  )
}

