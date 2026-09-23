import {
  ArrowRight,
  CheckCheck,
  ChevronDown,
  ClipboardList,
  ExternalLink,
  MessageSquare,
  Phone,
  Send,
  Sparkles,
  TriangleAlert,
  Users,
} from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import type { CSSProperties, MouseEvent, ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { NextStep, NextStepActionType, WorklistRowWithStep } from '../../api/plan'
import { useCompleteNextStep, useExecuteNextStep } from '../../api/plan'
import { useWorklist } from '../../api/queries'
import type { WorklistResponse } from '../../api/types'
import DotLine from '../patient/DotLine'
import MessageComposerModal from '../patient/plan/MessageComposerModal'
import { AskAnswer, AskField } from './AskBar'
import { useAskState } from './useAskState'
import { NarrativeTile } from '../../components/AIAttribution'
import Avatar from '../../components/Avatar'
import ConfidenceChip from '../../components/ConfidenceChip'
import EmptyState from '../../components/EmptyState'
import GuardrailFootnote from '../../components/GuardrailFootnote'
import { ListGroup } from '../../components/ListRow'
import SectionCard from '../../components/SectionCard'
import SegmentedControl from '../../components/SegmentedControl'
import { SkeletonCard, SkeletonLine } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { longDate, relativeTime } from '../../lib/format'
import { PRIORITY, type Priority } from '../../lib/risk'

type Filter = 'all' | 'high' | 'missing_data'

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'high', label: 'High risk' },
  { key: 'missing_data', label: 'Missing data' },
]

const TIER_ORDER: Priority[] = ['high', 'medium', 'missing_data', 'low']

/** Charts whose numbers come from a real person using the app. Everything
 *  else on this roster is generated for the demo, and the two are banded
 *  apart so nobody in the room reads a persona's vitals as clinical truth.
 *  Ids, not hospitals: the demo personas carry placeholder phones and sit on
 *  the same roster, so there is no field on the row that tells them apart. */
const REAL_PATIENT_IDS = new Set(['steve'])

/** The two bands, real first — the real chart is what the demo opens on. */
const SOURCE_BANDS = [
  { key: 'real', label: 'Real data', real: true },
  { key: 'demo', label: 'Fake data', real: false },
] as const

/** How long the first-load rise runs before rows stop animating in. Rows
 *  that remount later (filter changes, ask results) appear without motion. */
const INTRO_MS = 1400

/** The briefing and the first tier card arrive with a slightly fuller
 *  "lift and settle" than the rows' plain rise: the existing modalIn frames
 *  (8px up, .97 scale, fading in), 360ms ease-out, no overshoot. It is
 *  `motion-safe:` only, so under Reduce Motion there is no animation class at
 *  all. Fill is `backwards` (not `both`), so no transform is left on the card
 *  afterwards to become a containing block. */
const SETTLE = 'motion-safe:animate-[modalIn_360ms_cubic-bezier(.22,.61,.36,1)_backwards]'

function greeting(d: Date = new Date()): string {
  const h = d.getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

/** The page's one big line. Warm, but it only says what the numbers say. */
function headline(stats: { high: number; medium: number; missing: number }): string {
  if (stats.high === 1) return '1 patient needs you today'
  if (stats.high > 1) return `${stats.high} patients need you today`
  if (stats.missing > 0) {
    return `Nothing urgent — ${stats.missing} ${stats.missing === 1 ? 'patient has' : 'patients have'} data gaps`
  }
  if (stats.medium > 0) {
    return `Nothing urgent — ${stats.medium} to review when you can`
  }
  return 'Everyone’s on track today'
}

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

export default function WorklistPage() {
  const { data, isLoading, isError, isFetching } = useWorklist()
  const [filter, setFilter] = useState<Filter>('all')
  const askState = useAskState()
  const askResult = askState.result
  // A row's "Message" next step opens the composer for that patient; the
  // send is logged back as the step's completion.
  const [composer, setComposer] = useState<{ patient: WorklistRowWithStep; step: NextStep } | null>(
    null,
  )
  // Cards and rows rise in on the first load only.
  const [intro, setIntro] = useState(true)
  const ready = Boolean(data)
  useEffect(() => {
    if (!ready) return
    const t = window.setTimeout(() => setIntro(false), INTRO_MS)
    return () => window.clearTimeout(t)
  }, [ready])
  const patientsHeadingId = useId()
  const briefingRef = useRef<HTMLDivElement>(null)

  const showBriefing = () => {
    const el = briefingRef.current
    if (!el) return
    el.scrollIntoView({ block: 'center', behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
    el.focus({ preventScroll: true })
  }

  // First-load entrance: `.rise` plus a staggered delay; nothing afterwards.
  const riseCls = intro ? 'rise' : ''
  const riseAt = (ms: number) =>
    intro ? ({ '--rise-delay': `${ms}ms` } as CSSProperties) : undefined
  const settleAt = (ms: number) =>
    intro ? ({ animationDelay: `${ms}ms` } as CSSProperties) : undefined
  const settleCls = intro ? SETTLE : ''

  // The briefing is written server-side with the worklist, so the worklist
  // request IS the briefing being generated (first load and refreshes).
  const generating = isLoading || (isFetching && !isError)

  const hero = (
    <PageHead
      data={data}
      generating={generating}
      onShowBriefing={showBriefing}
      askField={<AskField state={askState} />}
      className={riseCls}
      style={riseAt(0)}
    />
  )

  if (isLoading) {
    return (
      <div className="pb-4 pt-8">
        {hero}
        <div className="mt-10 space-y-stack" role="status" aria-label="Loading the worklist">
          <SkeletonCard lines={3} />
          <SkeletonCard rows={4} />
        </div>
      </div>
    )
  }
  if (isError || !data) {
    return (
      <div className="pb-4 pt-8">
        {hero}
        <div className="mt-10">
          <EmptyState title="The worklist couldn’t be loaded." family="blue">
            Check that the API is running, then reload this page.
          </EmptyState>
        </div>
      </div>
    )
  }

  const askIds = askResult && askResult.patient_ids.length > 0 ? new Set(askResult.patient_ids) : null
  const visible = data.patients.filter((p) =>
    askIds ? askIds.has(p.id) : filter === 'all' || p.priority === filter,
  )
  // Two bands, each still grouped by tier inside: the source of the numbers
  // is the outer question, triage the inner one.
  const bands = SOURCE_BANDS.map((band) => {
    const patients = visible.filter((p) => REAL_PATIENT_IDS.has(p.id) === band.real)
    return {
      ...band,
      count: patients.length,
      groups: TIER_ORDER.map((tier) => ({
        tier,
        patients: patients.filter((p) => p.priority === tier),
      })).filter((g) => g.patients.length > 0),
    }
  }).filter((band) => band.count > 0)
  const shown = bands.reduce((n, band) => n + band.count, 0)

  // "Start with": the top patient of the most urgent non-calm tier.
  const startWith =
    TIER_ORDER.slice(0, 2)
      .map((t) => data.patients.find((p) => p.priority === t))
      .find(Boolean) ?? null

  let riseIndex = 0

  return (
    <div className="pb-4 pt-8">
      {hero}

      {(askState.pending || askResult) && (
        <div className="mt-10">
          <AskAnswer state={askState} />
        </div>
      )}

      {/* The briefing floats over the sky's tail, like Aside's app window:
          opaque brand-tint card, ink prose. */}
      <div
        ref={briefingRef}
        tabIndex={-1}
        className={`${askState.pending || askResult ? 'mt-stack' : 'mt-10'} outline-0 [outline-style:none] ${settleCls}`}
        style={settleAt(80)}
      >
        <BriefingCard briefing={data.briefing} startWith={startWith} />
      </div>

      <div
        className={`mt-10 flex flex-wrap items-center justify-between gap-3 ${riseCls}`}
        style={riseAt(140)}
      >
        <h2 id={patientsHeadingId} className="text-subhead font-medium text-ink">
          {askIds ? 'Matching patients' : 'Patients'}
          <span className="ml-2 text-copy-lg font-normal tabular-nums text-secondary">
            {askIds ? shown : data.patients.length}
          </span>
        </h2>
        {/* On the canvas, below the sky: the default brand thumb, not glass. */}
        {!askIds && (
          <SegmentedControl
            options={FILTERS}
            value={filter}
            onChange={setFilter}
            role="radiogroup"
            aria-label="Filter patients"
            className="flex-none"
          />
        )}
      </div>

      {bands.length === 0 ? (
        <div className="mt-4">
          <EmptyState
            icon={<Users />}
            title={askIds ? 'No patients matched that question' : 'No patients match this filter'}
          >
            {askIds
              ? 'Clear the question to see the full roster.'
              : 'Switch back to All to see the full roster.'}
          </EmptyState>
        </div>
      ) : (
        <div className="mt-4 space-y-8" aria-labelledby={patientsHeadingId} role="region">
          {bands.map((band, bi) => (
            <SourceBand key={band.key} label={band.label} count={band.count}>
              {band.groups.map(({ tier, patients }, gi) => {
                const first = bi === 0 && gi === 0
                return (
                  <TierGroup
                    key={tier}
                    tier={tier}
                    count={patients.length}
                    className={first ? settleCls : ''}
                    style={first ? settleAt(180) : undefined}
                  >
                    {patients.map((p) => (
                      <WorklistRow
                        key={p.id}
                        patient={p}
                        rise={intro ? 260 + riseIndex++ * 40 : null}
                        onMessage={(step) => setComposer({ patient: p, step })}
                      />
                    ))}
                  </TierGroup>
                )
              })}
            </SourceBand>
          ))}
        </div>
      )}

      <GuardrailFootnote className="mt-8" />

      {composer && (
        <WorklistComposer
          patient={composer.patient}
          step={composer.step}
          onClose={() => setComposer(null)}
        />
      )}
    </div>
  )
}

/** THE PAGE HEAD, inside AppShell's sky window (`data-hero` sizes it).
 *
 *    [✦ AI daily briefing ⌄]                       ┌ Today ─────── 18 ┐
 *    Good evening · Wednesday, September 16         │ ● High risk     1 │
 *    1 patient needs you today                      │ ● Needs review  3 │
 *    [✦ Ask anything about your patients…   (↑)]    │ …                 │
 *    (Who reported fever…) (Which patients…)        └───────────────────┘
 *
 *  TEXT CONTRACT. Everything in the left column is on the SAFE sky: ink,
 *  --body (secondary and muted are flipped to body in the page head
 *  automatically), teal-ink glyphs, and glass capsules/fields at their
 *  computed floors. At >= 1024px the left column is capped at 58% of the
 *  column (and 600px): the decor layer only ramps in from 58% of the WINDOW,
 *  which starts --sky-pad left of the column and is 2 x --sky-pad wider, so
 *  58% of the column always ends left of it (at 1024: column 972.8, decor
 *  from x592.6, column text ends at x589.8).
 *
 *  The right side (the decor zone) holds ONE opaque panel: the tier counts,
 *  each a dot + word + number (risk is never colour alone), with Aside's
 *  elliptical ground shadow under it. Below 1024px it is hidden; the tier
 *  headers carry the same counts.
 *
 *  The head starts at y 88 (bar 56 + pt-8), under the 84px bar band. */
function PageHead({
  data,
  generating,
  onShowBriefing,
  askField,
  className = '',
  style,
}: {
  data: WorklistResponse | undefined
  generating: boolean
  onShowBriefing: () => void
  askField: ReactNode
  className?: string
  style?: CSSProperties
}) {
  return (
    <header
      data-hero
      className={`lg:flex lg:items-start lg:justify-between lg:gap-10 ${className}`}
      style={style}
    >
      <div className="min-w-0 lg:max-w-[min(600px,58%)] lg:flex-1">
        <BriefingBadge
          provider={data?.briefing.provider}
          generating={generating}
          onClick={onShowBriefing}
        />
        {/* --body on the sky: 6.073 light / 4.642 dark at its most
            saturated point. */}
        <p className="mt-5 text-copy-lg text-body">
          {greeting()}
          <span aria-hidden> · </span>
          <span className="sr-only">, </span>
          {longDate()}
        </p>
        {data ? (
          <Headline stats={data.stats} />
        ) : (
          <>
            <h1 className="sr-only">Worklist</h1>
            <SkeletonLine className="mt-3 h-10 w-96 max-w-full" />
          </>
        )}
        <div className="mt-6">{askField}</div>
      </div>

      {data && <TodayPanel stats={data.stats} />}
    </header>
  )
}

/** Aside's capsule badge ("Backed by Y Combinator ›") for the briefing.
 *  While the worklist (and so the briefing) is being generated it is a
 *  status with the shimmer text; once it is ready it is a button that
 *  brings the briefing card into view and moves focus to it.
 *  The renderer's work is never headlined as AI. */
function BriefingBadge({
  provider,
  generating,
  onClick,
}: {
  provider: string | undefined
  generating: boolean
  onClick: () => void
}) {
  const glyph = <Sparkles aria-hidden className="!text-cat-teal-ink" />
  const writing = <span className="shimmer-text inline-block py-px leading-body">Writing today’s briefing…</span>
  if (!provider) {
    return (
      <span className="badge-ring" role="status">
        {glyph}
        {writing}
      </span>
    )
  }
  // A refresh keeps the button (focus is not lost) and swaps only its label.
  const rulesBased = provider === 'fallback'
  return (
    <button type="button" className="badge-ring" onClick={onClick} aria-busy={generating}>
      {rulesBased ? null : glyph}
      {generating ? writing : rulesBased ? 'Today’s briefing · rules-based' : 'AI daily briefing'}
      <ChevronDown aria-hidden />
    </button>
  )
}

/** The worklist's headline, the site's dashboard KPI: when someone needs
 *  the team today, a big light count beside the sentence and the calm
 *  remainder under it; otherwise one display sentence. */
function Headline({ stats }: { stats: WorklistResponse['stats'] }) {
  if (stats.high > 0) {
    const rest = [
      stats.medium > 0 && `${stats.medium} to review`,
      stats.missing > 0 && `${stats.missing} with data gaps`,
      stats.low > 0 && `${stats.low} on track`,
    ].filter(Boolean) as string[]
    return (
      <h1 className="mt-2 flex items-center gap-4 text-ink">
        <span className="big-num text-[5.5rem] leading-[.9]">{stats.high}</span>
        <span className="min-w-0">
          <span className="display-title block text-[1.75rem] leading-tight lg:text-[2rem]">
            {stats.high === 1 ? 'patient needs you today' : 'patients need you today'}
          </span>
          {rest.length > 0 && (
            <DotLine
              className="mt-1 block text-copy-lg font-normal tracking-copy-lg text-body"
              parts={rest}
            />
          )}
        </span>
      </h1>
    )
  }
  return <h1 className="display-title mt-2 text-section text-ink lg:text-display">{headline(stats)}</h1>
}

/** The head's right-hand summary, as a gradient tile: the roster size in
 *  light type on sage, a white meter of the tiers, and the counts on a solid
 *  glass caption — each tier a dot + word + number, so risk is never colour
 *  alone. The meter repeats the counts and is aria-hidden. */
function TodayPanel({ stats }: { stats: WorklistResponse['stats'] }) {
  const rows: { tier: Priority; n: number }[] = [
    { tier: 'high', n: stats.high },
    { tier: 'medium', n: stats.medium },
    { tier: 'missing_data', n: stats.missing },
    { tier: 'low', n: stats.low },
  ]
  const total = Math.max(1, stats.total)
  return (
    <div className="hidden w-[300px] shrink-0 lg:block">
      <section aria-label="Today at a glance" className="gtile g-sage spotlight rise" data-loop>
        <div className="gtile-top">
          <div>
            <span className="gtile-kicker block">Today</span>
            <span className="gtile-num big-num">
              {stats.total}
              <small>{stats.total === 1 ? 'patient' : 'patients'}</small>
            </span>
          </div>
          <div className="gtile-side">
            <b>{stats.low}</b>
            on track
          </div>
        </div>
        <div aria-hidden className="relative z-[1] mx-5 mb-3 mt-4 flex h-2 gap-1">
          {rows
            .filter((r) => r.n > 0)
            .map(({ tier, n }, i) => (
              <span
                key={tier}
                className={`meter-fill h-full rounded-pill ${
                  tier === 'high' ? 'bg-lime shadow-[0_0_10px_rgb(212_241_74_/_.7)]' : tier === 'low' ? 'bg-white/90' : 'bg-white/45'
                }`}
                style={{ flexGrow: n / total, flexBasis: 0, backgroundImage: 'none', animationDelay: `${0.3 + i * 0.08}s` }}
              />
            ))}
        </div>
        <ul className="gtile-cap !pb-2 !pt-1.5">
          {rows.map(({ tier, n }) => (
            <li key={tier} className="flex min-h-8 items-center gap-2">
              <span
                aria-hidden
                className={`h-2 w-2 shrink-0 rounded-pill ${
                  tier === 'missing_data' ? 'border-[1.5px] border-risk-missing-ink' : PRIORITY[tier].dot
                }`}
              />
              <span className="flex-1 text-copy text-ink">{PRIORITY[tier].label}</span>
              <span className="big-num text-[1.375rem] text-ink">{n}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

/** Today's briefing: the opaque brand-tint card under the head.
 *  At >= 1024px the prose keeps its 64ch measure and the space to its right
 *  (the judge's empty 40%) holds a "Start with" shortcut: an opaque panel
 *  link to the most urgent patient, with the tier in words. When there is no
 *  one to start with, the card is capped to its text instead. */
function BriefingCard({
  briefing,
  startWith,
}: {
  briefing: WorklistResponse['briefing']
  startWith: WorklistRowWithStep | null
}) {
  const rulesBased = briefing.provider === 'fallback'
  return (
    <SectionCard
      sum
      title="Today’s briefing"
      className={startWith ? '' : 'lg:w-fit lg:min-w-[480px]'}
      icon={<NarrativeTile provider={briefing.provider} />}
      aside={
        <span className="meta tabular-nums">
          {rulesBased ? 'Rules-based' : 'AI'}
          <span aria-hidden> · </span>
          <span className="sr-only">, </span>
          {relativeTime(briefing.generated_at)}
        </span>
      }
    >
      <div
        className={
          startWith
            ? 'lg:grid lg:grid-cols-[minmax(0,64ch)_minmax(220px,300px)] lg:items-start lg:justify-between lg:gap-8'
            : ''
        }
      >
        <p className="max-w-[64ch] text-copy-lg text-ink">{briefing.text}</p>
        {startWith && <StartWith patient={startWith} />}
      </div>
    </SectionCard>
  )
}

function StartWith({ patient: p }: { patient: WorklistRowWithStep }) {
  const day = p.postop_day == null ? null : p.mode === 'general' ? `day ${p.postop_day}` : `post-op day ${p.postop_day}`
  return (
    <Link
      to={`/patients/${p.id}`}
      className="spotlight group mt-4 flex items-start gap-3 rounded-control bg-panel/80 p-4 shadow-soft transition-[box-shadow,transform] duration-spring ease-spring hover:-translate-y-0.5 hover:shadow-float focus-visible:outline motion-reduce:transform-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:[outline-color:rgb(var(--focus))] lg:mt-0"
    >
      <Avatar name={p.name} tier={p.priority} />
      <span className="min-w-0 flex-1">
        <span className="block text-label font-medium tracking-label text-secondary">Start with</span>
        <span className="mt-0.5 block truncate text-copy-lg font-medium text-ink">{p.name}</span>
        <span className="mt-0.5 block text-label tracking-label text-body">
          {PRIORITY[p.priority].label}
          {day && (
            <span className="whitespace-nowrap">
              <span aria-hidden> · </span>
              <span className="sr-only">, </span>
              <span className="tabular-nums">{day}</span>
            </span>
          )}
        </span>
        <span className="mt-1.5 line-clamp-2 block text-copy text-ink">{p.reason}</span>
        <span className="mt-2 inline-flex items-center gap-1 text-copy font-medium text-brand-ink">
          Open chart
          <ArrowRight
            aria-hidden
            size={14}
            className="transition-transform duration-state ease-apple motion-safe:group-hover:translate-x-0.5"
          />
        </span>
      </span>
    </Link>
  )
}

/** One source band — "Real data" over Steve's own chart, "Fake data" over
 *  the generated roster. A quiet caption over the tier cards rather than
 *  another card: the tier groups keep the visual weight, and the band only
 *  answers "whose numbers am I looking at".
 *
 *  Nothing is disclosed to the patient by this label; it is a demo aid for
 *  the room, which is why it is plain words and not a risk-coloured badge. */
function SourceBand({
  label,
  count,
  children,
}: {
  label: string
  count: number
  children: ReactNode
}) {
  const id = useId()
  return (
    <section aria-labelledby={id}>
      <h3
        id={id}
        className="flex items-baseline gap-2 px-1 pb-2 text-label font-medium uppercase tracking-label text-secondary"
      >
        {label}
        <span className="tabular-nums normal-case tracking-normal">
          <span className="sr-only">, </span>
          {count}
          <span className="sr-only"> {count === 1 ? 'patient' : 'patients'}</span>
        </span>
      </h3>
      <div className="space-y-stack">{children}</div>
    </section>
  )
}

/** One tier: its own rounded group with a dot + word header that replaces
 *  the per-row risk badge (R4). The header is NOT sticky (judge #7): each
 *  tier is a short card, and a sticky header outlived its card and hung
 *  under the glass bar as an orphan strip. */
function TierGroup({
  tier,
  count,
  children,
  className = '',
  style,
}: {
  tier: Priority
  count: number
  children: ReactNode
  className?: string
  style?: CSSProperties
}) {
  const id = useId()
  return (
    <section className={`card-group ${className}`} style={style} aria-labelledby={id}>
      <div className="flex items-center gap-2 px-4 pb-1.5 pt-3.5">
        <span
          aria-hidden
          className={`h-2 w-2 shrink-0 rounded-pill ${
            tier === 'missing_data' ? 'border-[1.5px] border-risk-missing-ink' : PRIORITY[tier].dot
          }`}
        />
        <h4 id={id} className="text-[15px] font-medium text-ink">
          {PRIORITY[tier].label}
        </h4>
        <span className="text-copy tabular-nums text-secondary">
          <span className="sr-only">, </span>
          {count}
          <span className="sr-only"> {count === 1 ? 'patient' : 'patients'}</span>
        </span>
      </div>
      <ListGroup embedded inset="avatar" aria-labelledby={id}>
        {children}
      </ListGroup>
    </section>
  )
}

/** The composer for a row's message step. Its own component so the
 *  completion hook is bound to the row's patient id. */
function WorklistComposer({
  patient,
  step,
  onClose,
}: {
  patient: WorklistRowWithStep
  step: NextStep
  onClose: () => void
}) {
  const complete = useCompleteNextStep(patient.id)
  const phone = step.action.tel ?? null
  return (
    <MessageComposerModal
      patientId={patient.id}
      patientName={patient.name}
      phone={phone}
      prefill={step.action.prefill ?? ''}
      onClose={onClose}
      onSent={(r) =>
        complete.mutate({
          key: step.key,
          result: { message_id: r.message?.id ?? null, status: r.status },
        })
      }
    />
  )
}

/** Row grid (R4). At ≥1024px five fixed columns, so names, reasons, actions
 *  and times each share one x:
 *
 *    [avatar 32] [name 188] [reason 1fr] [action 264] [time 128]
 *
 *  At the 1080px worklist cap the reason keeps ~400px and WRAPS to two
 *  lines instead of truncating (the old 288px action column sat half empty
 *  on most rows while reasons were cut). 264 fits the longest step capsule
 *  ("Ask how they are feeling today") beside "Send now" with the capsule
 *  truncating last; 128 fits "Yesterday · 10:27 PM".
 *
 *  Narrower, the action and time wrap under the reason. The row is an <li>;
 *  the patient name is its only link, stretched over the row, and the action
 *  controls sit above that overlay. Nothing interactive nests in the <a>. */
const ROW_GRID = [
  'grid items-center gap-x-3 gap-y-2',
  "grid-cols-[32px_minmax(0,1fr)_auto] [grid-template-areas:'av_id_tm'_'._rs_rs'_'._ac_ac']",
  "lg:grid-cols-[32px_180px_minmax(0,1fr)_296px_120px] lg:[grid-template-areas:'av_id_rs_ac_tm']",
].join(' ')

function WorklistRow({
  patient: p,
  rise,
  onMessage,
}: {
  patient: WorklistRowWithStep
  /** Rise delay in ms on the first load; null once the intro is over. */
  rise: number | null
  onMessage: (step: NextStep) => void
}) {
  const high = p.priority === 'high'
  const step = p.next_step && p.next_step.state.status === 'open' ? p.next_step : null
  const procedure = p.procedure_display.replace(/\s*\(.*\)$/, '')
  // "D6" means post-op day six, which says nothing true about a patient who
  // never had an operation.
  const day = p.postop_day == null ? null : p.mode === 'general' ? `${p.postop_day}d` : `D${p.postop_day}`
  // Low confidence is a muted meta line, never a chip, and only when the
  // reason does not already say it.
  const showConfidence =
    p.data_confidence.level !== 'high' && !/confidence/i.test(p.reason)

  // `.row-risk-high` carries the tint and flips secondary text to --body
  // (R8: dark muted on the risk tint is 3.698, body 5.013).
  // Interaction-state guards (secondary text must hold 4.5:1 while the row
  // is hovered or pressed):
  //  - pressed row (--hairline fill): muted is 4.260 light / 3.655 dark, so
  //    it flips to --body (5.705 / 4.955);
  //  - dark high-risk hover (--risk-high-tint-strong #45353C): body is 4.444,
  //    so it lifts to n-300 (7.397).
  const stateGuard = high
    ? 'dark:hover:[--text-secondary:var(--n-300)]'
    : 'active:[--text-secondary:var(--body)]'
  return (
    <li
      className={`card-row ${high ? 'row-risk-high' : ''} ${stateGuard} ${ROW_GRID} ${rise != null ? 'rise' : ''}`}
      style={rise != null ? ({ '--rise-delay': `${rise}ms` } as CSSProperties) : undefined}
    >
      <span className="flex [grid-area:av]">
        <Avatar name={p.name} tier={p.priority} />
      </span>

      <div className="min-w-0 [grid-area:id]">
        <Link
          to={`/patients/${p.id}`}
          className="stretched-link block truncate text-copy-lg font-medium text-ink"
        >
          {p.name}
          {high && <span className="sr-only">, high risk</span>}
        </Link>
        <p className="meta mt-0.5 truncate">
          {procedure}
          {day && (
            <>
              <span aria-hidden> · </span>
              <span className="sr-only">, </span>
              <span className="tabular-nums">{day}</span>
            </>
          )}
        </p>
      </div>

      <div className="min-w-0 [grid-area:rs]">
        <p className="line-clamp-2 text-copy text-ink" title={p.reason}>
          {p.reason}
        </p>
        {showConfidence && (
          <p className="mt-0.5 truncate">
            <ConfidenceChip level={p.data_confidence.level} variant="meta" />
          </p>
        )}
      </div>

      <div className="flex min-w-0 items-center gap-1 [grid-area:ac] empty:hidden">
        {step && (
          <RowAction patientId={p.id} step={step} canText={p.can_text} high={high} onMessage={onMessage} />
        )}
      </div>

      <div className="min-w-0 text-right [grid-area:tm]">
        <p className="meta truncate font-medium tabular-nums">{relativeTime(p.last_checkin_at)}</p>
        <p className="meta mt-0.5 truncate">{p.assigned_provider.name}</p>
      </div>
    </li>
  )
}

const ACTION_ICON = {
  message: MessageSquare,
  assign_tasks: ClipboardList,
  send_checkin: Send,
  escalate: TriangleAlert,
  call: Phone,
  open: ExternalLink,
  acknowledge: CheckCheck,
} as const satisfies Record<NextStepActionType, unknown>

/** The row's ONE capsule, labelled with the next step itself (R4), plus at
 *  most one plain text button beside it for the step's direct shortcut:
 *
 *    message       [Nudge the device sync] opens the composer   · Send now
 *    call (tel)    [Call the patient today] tel: link            · Log call
 *    call (no tel) [Call the patient today] opens the chart      · Log call
 *    escalate      [Escalate …] danger capsule, executes
 *    open          [step] navigates and marks it done
 *    other         [step] executes (assign, check-in, reviewed)
 *
 *  "Send now" stays a ONE-click plain button; the clinical workflow is
 *  unchanged. On the high-risk row the capsule is panel-filled (R1), since
 *  the row already wears the risk tint. */
function RowAction({
  patientId,
  step,
  canText,
  high,
  onMessage,
}: {
  patientId: string
  step: NextStep
  canText: boolean
  high: boolean
  onMessage: (step: NextStep) => void
}) {
  const navigate = useNavigate()
  const toast = useToast()
  const execute = useExecuteNextStep(patientId)
  const complete = useCompleteNextStep(patientId)
  const type = step.action.type
  const Icon = ACTION_ICON[type] ?? CheckCheck
  const busy = execute.isPending || complete.isPending
  const danger = type === 'escalate'
  const capsule = `${
    danger ? (high ? 'btn-danger-on-tint' : 'btn-danger') : high ? 'btn-on-tint' : 'btn-tinted'
  } btn-sm above-stretch min-w-0 max-w-full`
  const plain = 'btn-plain btn-sm above-stretch shrink-0'
  const tel = type === 'call' ? step.action.tel ?? null : null

  const runExecute = () =>
    execute.mutate(
      { key: step.key },
      {
        onSuccess: (r) => {
          // A check-in for a patient with no phone comes back as a tokenized
          // link; put it on the clipboard so the toast is actionable.
          const url = (r.result as Record<string, unknown> | null)?.url
          if (typeof url === 'string' && url) void navigator.clipboard?.writeText(url).catch(() => {})
          toast(resultToast(step, r.result), danger ? 'warning' : 'success')
        },
        onError: (err) => toast(`${step.title} failed — ${err.message}`, 'warning'),
      },
    )

  const onPrimary = (e: MouseEvent) => {
    e.stopPropagation()
    if (type === 'message') return onMessage(step)
    if (type === 'call') {
      // No number on file: the chart is where one gets added.
      navigate(`/patients/${patientId}`)
      return
    }
    if (type === 'open') {
      const target = step.action.target ?? ''
      navigate(`/patients/${patientId}`)
      complete.mutate({ key: step.key, result: { target } })
      return
    }
    runExecute()
  }

  const sendNow = (e: MouseEvent) => {
    e.stopPropagation()
    execute.mutate(
      { key: step.key },
      {
        onSuccess: () => toast('Sent as drafted', 'success'),
        onError: (err) => toast(`Could not send — ${err.message}`, 'warning'),
      },
    )
  }

  const label = (
    <>
      <Icon aria-hidden />
      <span className="truncate">{busy ? 'Working…' : step.title}</span>
    </>
  )
  const hint = step.detail || step.title
  // A check-in the patient can't receive by text is handed over as a link.
  const primaryName =
    type === 'send_checkin' && !canText ? `${step.title} (opens a check-in link to copy)` : undefined

  return (
    <>
      {tel ? (
        <a href={`tel:${tel}`} className={capsule} title={`Call ${tel}`}>
          {label}
        </a>
      ) : (
        <button
          type="button"
          className={capsule}
          disabled={busy}
          onClick={onPrimary}
          title={hint}
          aria-label={primaryName}
        >
          {label}
        </button>
      )}
      {type === 'message' && step.action.prefill && (
        <button
          type="button"
          className={plain}
          disabled={busy}
          onClick={sendNow}
          title="Send the drafted text as-is"
        >
          Send now
        </button>
      )}
      {type === 'call' && (
        <button
          type="button"
          className={plain}
          disabled={busy}
          onClick={(e) => {
            e.stopPropagation()
            runExecute()
          }}
        >
          Log call
        </button>
      )}
    </>
  )
}

// Mirrors NextSteps.tsx's toast copy (that helper is not exported).
function resultToast(step: NextStep, result: Record<string, unknown> | null): string {
  const sms = (result?.sms as { sent?: boolean } | undefined)?.sent
  switch (step.action.type) {
    case 'assign_tasks': {
      const n = Array.isArray(result?.task_ids) ? result.task_ids.length : null
      return `${n != null ? `${n} task${n === 1 ? '' : 's'}` : 'Tasks'} assigned${sms ? ' — texted' : ''}`
    }
    case 'send_checkin':
      if (sms) return 'Check-in sent by text'
      return typeof result?.url === 'string'
        ? `Check-in link ready — copied: ${result.url}`
        : 'Check-in created — waiting in the app'
    case 'escalate':
      return 'Escalated — care team notified'
    case 'call':
      return 'Call logged'
    case 'acknowledge':
      return 'Marked reviewed'
    default:
      return `Done — ${step.title}`
  }
}
