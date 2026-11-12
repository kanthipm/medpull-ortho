import { ArrowUp, CalendarCheck, Check, HeartPulse, MessagesSquare, NotebookText, Sparkles } from 'lucide-react'
import { useState, type CSSProperties, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { CareMetric } from '../../api/care'
import { ApiError } from '../../api/client'
import {
  useCoachTurn,
  usePersonalInsight,
  usePersonalOverview,
  type DeepDive,
  type PersonalOverview,
  type ReadinessComponent,
} from '../../api/personal'
import { NarrativeTile } from '../../components/AIAttribution'
import SectionCard from '../../components/SectionCard'
import SegmentedControl from '../../components/SegmentedControl'
import Tile from '../../components/Tile'
import { useToast } from '../../components/Toast'
import { relativeTime, shortDate } from '../../lib/format'
import MetricCard from '../patient/metrics/MetricCard'
import { MemberHead, MiniLine, PanelCard, PersonalState, WritingBlock } from './PersonalBits'
import { VERDICT_TILE, VERDICT_WORD, panelChip, panelsInOrder, values } from './personalFormat'

/** `/personal/:memberId` — a demo member's Today, as their phone shows it:
 *  the verdict for the day and the readiness number behind it, the morning
 *  brief, what goes into the number, today's plan, the three deep dives,
 *  every readout in the order their goal puts them, the care section a
 *  recovery goal adds, and the coach.
 *
 *  It is their space. The console reads it and changes nothing, with one
 *  exception that says so where it is: a question to the coach is asked as
 *  the member and lands on the member's thread. */
export default function PersonalTodayPage() {
  const { memberId = '' } = useParams()
  const overview = usePersonalOverview(memberId)
  return (
    <div className="pb-10">
      <PersonalState
        loading={overview.isLoading}
        error={overview.isError || (!overview.isLoading && !overview.data)}
        onRetry={() => void overview.refetch()}
      >
        {overview.data && <Today memberId={memberId} o={overview.data} />}
      </PersonalState>
    </div>
  )
}

function Today({ memberId, o }: { memberId: string; o: PersonalOverview }) {
  const d = o.dashboard
  const first = o.member.name.split(' ')[0]
  const readiness = d.panels.readiness
  const components = ((readiness?.extra?.components as ReadinessComponent[] | undefined) ?? []).filter(
    (c) => typeof c.contribution === 'number',
  )
  const series = values(readiness?.series)
  const others = panelsInOrder(d.sections, d.panels).filter((p) => p.key !== 'readiness')
  const care = o.care as { headline?: string[]; metrics?: CareMetric[]; postop_day?: number } | null
  const careCards = care?.metrics
    ? (care.headline ?? []).map((id) => care.metrics!.find((m) => m.id === id)).filter((m): m is CareMetric => !!m)
    : []

  return (
    <>
      <MemberHead overview={o} />

      {/* ── The day: the verdict and the number behind it ─────────────────── */}
      <div className="mt-8 grid gap-3 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <section
          aria-label="Today’s verdict"
          className={`gtile ${VERDICT_TILE[d.verdict.kind] ?? 'g-dusk'} rise min-h-[17rem]`}
          style={{ '--rise-delay': '60ms' } as CSSProperties}
        >
          <div className="gtile-top">
            <span className="min-w-0">
              <span className="gtile-kicker block">Today · {VERDICT_WORD[d.verdict.kind] ?? 'Today'}</span>
              <span className="display-title mt-2 block text-[2.5rem] leading-none text-white">{d.verdict.title}</span>
            </span>
          </div>
          <div className="gtile-art" />
          <div className="gtile-cap">
            <p className="text-copy-lg font-medium text-ink">{d.verdict.reason}</p>
            <p className="mt-1 text-copy text-body">{d.verdict.detail}</p>
          </div>
        </section>

        {readiness && (
          <section
            aria-label="Readiness"
            className="gtile g-sage rise min-h-[17rem]"
            style={{ '--rise-delay': '100ms' } as CSSProperties}
          >
            <div className="gtile-top">
              <span className="min-w-0">
                <span className="gtile-kicker block">Readiness</span>
                <span className="gtile-num big-num">
                  {readiness.headline}
                  <small>of 100</small>
                </span>
              </span>
              <span className="gtile-side shrink-0">
                <b>{series.length}</b>
                days shown
              </span>
            </div>
            <div className="gtile-art !block">
              <MiniLine
                points={series}
                height={72}
                onTile
                reference={50}
                label={`Readiness over the last ${series.length} days; 50 is ${first}’s own normal`}
              />
            </div>
            <div className="gtile-cap">
              <p className="flex flex-wrap items-center gap-2">
                <span className={`chip ${panelChip(readiness.status)}`}>{readiness.status_text}</span>
                <span className="meta">50 is {first}’s own normal · {readiness.coverage}</span>
              </p>
              <p className="mt-2 text-copy text-body">{readiness.finding}</p>
            </div>
          </section>
        )}
      </div>

      <div className="mt-stack grid gap-stack lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:items-start">
        <div className="space-y-stack">
          {/* ── The brief ───────────────────────────────────────────────── */}
          <SectionCard
            sum
            title={o.brief.headline || 'This morning'}
            icon={<NarrativeTile provider={o.brief.provider} />}
            aside={`The morning brief · ${relativeTime(o.brief.generated_at)}`}
          >
            <WritingBlock writing={o.brief} text={o.brief.brief ?? ''} />
          </SectionCard>

          {/* ── What goes into the number ───────────────────────────────── */}
          {components.length > 0 && (
            <SectionCard
              title="What goes into the number"
              aside="each signal against their own 28-day baseline"
            >
              <Components rows={components} />
              <p className="meta mt-4">{readiness?.method}</p>
            </SectionCard>
          )}

          <DeepDives memberId={memberId} />
        </div>

        <div className="space-y-stack">
          <Plan o={o} first={first} />
          <Coach memberId={memberId} o={o} first={first} />
        </div>
      </div>

      {/* ── The care section a recovery goal adds ───────────────────────── */}
      {careCards.length > 0 && (
        <SectionCard
          className="mt-stack"
          title="Recovery"
          icon={<Tile size="sm" family="violet" icon={<HeartPulse />} />}
          aside={[o.profile.injury, care?.postop_day != null ? `day ${care.postop_day}` : null].filter(Boolean).join(' · ')}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            {careCards.map((m) => (
              <MetricCard key={m.id} m={m} />
            ))}
          </div>
          <p className="meta mt-4">
            The same recovery metrics a clinic would see, shown to the member in their own space.
            For review and conversation with their care team; not a diagnosis.
          </p>
        </SectionCard>
      )}

      {/* ── Every readout, in the order their goal puts them ────────────── */}
      <section className="mt-stack" aria-labelledby="personal-readouts">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3 px-1">
          <h2 id="personal-readouts" className="text-subhead font-medium text-ink">
            {first}’s readouts
          </h2>
          <Link to={`/personal/${encodeURIComponent(memberId)}/data`} className="btn-plain btn-sm -mr-2">
            How each is worked out
          </Link>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {others.map((panel) => (
            <PanelCard key={panel.key} panel={panel} />
          ))}
        </div>
      </section>

      <p className="meta mt-8 px-1">
        {o.brief.guardrail} Readouts are computed from {d.days_with_data} days of {first}’s own data.
      </p>
    </>
  )
}

/** Each signal's push on the readiness number: a bar to the right when it
 *  lifts it, to the left when it lowers it, with the reading and what it is
 *  compared with. The direction is also said in words. */
function Components({ rows }: { rows: ReadinessComponent[] }) {
  const most = Math.max(0.05, ...rows.map((r) => Math.abs(r.contribution)))
  return (
    <ul className="divide-y divide-hairline">
      {rows.map((r) => {
        const share = Math.min(1, Math.abs(r.contribution) / most)
        const lifts = r.contribution > 0.005
        const lowers = r.contribution < -0.005
        return (
          <li key={r.key} className="grid grid-cols-[minmax(0,1fr)_minmax(96px,160px)] items-center gap-4 py-2.5 first:pt-0 last:pb-0">
            <div className="min-w-0">
              <p className="text-copy text-ink">
                <span className="font-medium">{r.label}</span>{' '}
                <span className="tabular-nums">{r.value}</span>
              </p>
              <p className="meta">
                {r.text} · {Math.round(r.weight * 100)}% of the number ·{' '}
                {lifts ? 'lifting it' : lowers ? 'lowering it' : 'neutral'}
              </p>
            </div>
            <div className="relative h-2 rounded-pill bg-[rgb(var(--fill))]" aria-hidden>
              <span className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
              {(lifts || lowers) && (
                <span
                  className={`absolute inset-y-0 rounded-pill ${lifts ? 'left-1/2 bg-chart-s1' : 'right-1/2 bg-risk-med-ink'}`}
                  style={{ width: `${share * 50}%` }}
                />
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}

function Plan({ o, first }: { o: PersonalOverview; first: string }) {
  const open = o.plan.open
  const done = o.plan.recent.filter((t) => t.completed_at)
  return (
    <SectionCard
      title="Today’s plan"
      icon={<Tile size="sm" family="teal" icon={<CalendarCheck />} />}
      aside={open.length > 0 ? `${open.length} open` : 'nothing open'}
    >
      {open.length === 0 ? (
        <p className="text-copy text-secondary">Nothing on {first}’s plan right now.</p>
      ) : (
        <ul className="divide-y divide-hairline">
          {open.map((t) => (
            <li key={t.id} className="py-2.5 first:pt-0 last:pb-0">
              <p className="flex flex-wrap items-baseline gap-x-2 text-copy text-ink">
                <span className="font-medium">{t.title}</span>
                <span className="chip bg-soft text-secondary">{t.kind_label}</span>
              </p>
              <p className="meta mt-0.5">{t.why}</p>
            </li>
          ))}
        </ul>
      )}
      {done.length > 0 && (
        <p className="meta mt-4 inline-flex items-center gap-1.5">
          <Check aria-hidden size={12} /> {done.length} done lately, the last “{done[0].title}”
          {done[0].completed_at ? ` ${relativeTime(done[0].completed_at).toLowerCase()}` : ''}
        </p>
      )}
      <p className="meta mt-3">The app writes the plan each morning from the readouts; {first} ticks it off on their phone.</p>
    </SectionCard>
  )
}

const DIVES: { key: DeepDive; label: string }[] = [
  { key: 'recovery', label: 'Recovery' },
  { key: 'training', label: 'Training' },
  { key: 'sleep', label: 'Sleep' },
]

function DeepDives({ memberId }: { memberId: string }) {
  const [domain, setDomain] = useState<DeepDive>('recovery')
  const dive = usePersonalInsight(memberId, domain)
  return (
    <SectionCard
      title="A closer read"
      icon={<Tile size="sm" family="indigo" icon={<NotebookText />} />}
      action={
        <SegmentedControl<DeepDive>
          options={DIVES}
          value={domain}
          onChange={setDomain}
          size="sm"
          role="radiogroup"
          aria-label="Which deep dive"
        />
      }
    >
      {dive.isLoading ? (
        <p className="meta">Reading…</p>
      ) : dive.isError || !dive.data ? (
        <p className="text-copy text-secondary">This read is not available right now.</p>
      ) : (
        <>
          <h3 className="text-copy-lg font-medium text-ink">{dive.data.title}</h3>
          <div className="mt-1.5">
            <WritingBlock writing={dive.data} text={dive.data.body ?? ''} />
          </div>
        </>
      )}
    </SectionCard>
  )
}

/** The coach, as the member has it: the last lines of their thread, and a
 *  field. A question asked here is asked as the member and is written to
 *  their thread, which the caption says before anything is sent. */
function Coach({ memberId, o, first }: { memberId: string; o: PersonalOverview; first: string }) {
  const toast = useToast()
  const turn = useCoachTurn(memberId)
  const [text, setText] = useState('')
  const lines = [...o.thread].sort((a, b) => a.created_at.localeCompare(b.created_at)).slice(-6)

  const ask = (e: FormEvent) => {
    e.preventDefault()
    const question = text.trim()
    if (!question || turn.isPending) return
    turn.mutate(question, {
      onSuccess: () => setText(''),
      onError: (err) =>
        toast(err instanceof ApiError && err.message ? err.message : 'The coach did not answer. Try again.', 'warning'),
    })
  }

  return (
    <SectionCard
      title="Coach"
      icon={<Tile size="sm" family="blue" icon={<MessagesSquare />} />}
      aside={lines.length > 0 ? `last ${relativeTime(lines[lines.length - 1].created_at).toLowerCase()}` : undefined}
    >
      {lines.length === 0 ? (
        <p className="text-copy text-secondary">No conversation yet.</p>
      ) : (
        <ol className="space-y-2" aria-label={`${first}’s conversation with the coach, oldest first`}>
          {lines.map((line) => {
            const mine = line.sender === 'patient'
            return (
              <li key={line.id} className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[88%] rounded-control px-3 py-2 text-copy ${
                    mine ? 'bg-action text-on-action' : 'bg-soft text-ink'
                  }`}
                >
                  <span className="sr-only">{mine ? `${first}: ` : 'Coach: '}</span>
                  {line.text}
                  <span className={`mt-1 block text-micro ${mine ? 'text-on-action/80' : 'text-secondary'}`}>
                    {mine ? first : 'Coach'} · {shortDate(line.created_at)}
                  </span>
                </div>
              </li>
            )
          })}
        </ol>
      )}
      <form onSubmit={ask} className="mt-4">
        <label htmlFor="coach-ask" className="sr-only">
          Ask the coach as {first}
        </label>
        <div className="flex items-center gap-2 rounded-pill bg-soft py-1 pl-4 pr-1 ring-1 ring-inset ring-hairline focus-within:ring-2 focus-within:ring-focus">
          <Sparkles aria-hidden size={16} className="shrink-0 text-secondary" />
          <input
            id="coach-ask"
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={1000}
            placeholder={`Ask as ${first}, e.g. Should I train today?`}
            className="h-10 min-w-0 flex-1 bg-transparent text-copy-lg text-ink placeholder:text-secondary focus:outline-none"
          />
          <button type="submit" className="btn-send" disabled={!text.trim() || turn.isPending} aria-label="Ask the coach">
            <ArrowUp aria-hidden size={16} />
          </button>
        </div>
        <p className="meta mt-2 px-1">
          {turn.isPending
            ? 'The coach is answering…'
            : `Asked as ${first}, with today’s readouts in hand. Both lines are written to ${first}’s thread, as they would be from the phone.`}
        </p>
      </form>
    </SectionCard>
  )
}
