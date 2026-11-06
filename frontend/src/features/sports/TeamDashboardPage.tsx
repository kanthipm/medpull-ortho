import { ChevronLeft } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useTeamDashboard, type TeamDashboard, type TeamSummary } from '../../api/sports'
import { NarrativeTile } from '../../components/AIAttribution'
import EmptyState from '../../components/EmptyState'
import SectionCard from '../../components/SectionCard'
import { SkeletonCard, SkeletonLine } from '../../components/Skeleton'
import { PRIORITY } from '../../lib/risk'
import DotLine from '../patient/DotLine'
import AttentionList from './AttentionList'
import InjuryBoard from './InjuryBoard'
import RosterTable from './RosterTable'
import ScheduleStrip from './ScheduleStrip'
import { StaffGuardrail } from './SportsBits'
import StaffCard from './StaffCard'
import TeamLoadChart from './TeamLoadChart'
import { DASH, fmt, longDateOf, words } from './sportsFormat'

/* Layout. AppShell caps the page at the patient width (1240px) and adds the
 * gutter. The head sits in the sky window (`data-hero`): the org badge, the
 * team name at the display step and the facts line on the left; the roster
 * gradient tile on the right at >= 1024px. The briefing floats over the
 * sky's tail like the worklist's, then the week, the attention list, the
 * roster, the injury board, and load beside the staff list. */

/** The briefing card's "lift and settle" (the worklist's). */
const SETTLE = 'motion-safe:animate-[modalIn_360ms_cubic-bezier(.22,.61,.36,1)_backwards]'

function Block({ index, children, className = '' }: { index: number; children: ReactNode; className?: string }) {
  return (
    <div className={`rise min-w-0 ${className}`} style={{ '--rise-delay': `${index * 55}ms` } as CSSProperties}>
      {children}
    </div>
  )
}

export default function TeamDashboardPage() {
  const { teamId = '' } = useParams()
  const { data: d, isLoading, isError } = useTeamDashboard(teamId)

  if (isLoading) {
    return (
      <div className="pb-4 pt-8">
        <header data-hero className="pt-3">
          <SkeletonLine className="h-4 w-20" />
          <SkeletonLine className="mt-6 h-11 w-96 max-w-full" />
          <SkeletonLine className="mt-3 h-4 w-72 max-w-full" />
        </header>
        <div className="mt-10 space-y-stack" role="status" aria-label="Loading the team">
          <SkeletonCard lines={3} />
          <SkeletonCard rows={4} />
          <SkeletonCard rows={6} />
        </div>
      </div>
    )
  }
  if (isError || !d) {
    return (
      <div className="pb-4 pt-8">
        <header data-hero className="pt-3">
          <Link to="/sports" className="btn-plain btn-sm -ml-3">
            <ChevronLeft aria-hidden size={16} /> Teams
          </Link>
          <h1 className="display-title mt-4 text-section text-ink">Team</h1>
        </header>
        <EmptyState
          className="mt-10"
          title="This team couldn’t be loaded"
          action={
            <Link to="/sports" className="btn-tinted">
              <ChevronLeft aria-hidden size={16} /> Back to teams
            </Link>
          }
        >
          Check the link, or pick the team from the list again.
        </EmptyState>
      </div>
    )
  }

  const { team, org } = d
  return (
    <div className="pb-4 pt-8">
      <header
        data-hero
        className="rise lg:flex lg:items-start lg:justify-between lg:gap-10"
        style={{ '--rise-delay': '0ms' } as CSSProperties}
      >
        <div className="min-w-0 lg:max-w-[min(640px,58%)] lg:flex-1">
          <Link to="/sports" className="btn-plain btn-sm -ml-3">
            <ChevronLeft aria-hidden size={16} /> Teams
          </Link>
          {org && (
            <div className="mt-4">
              <span
                className="badge-ring max-w-full"
                style={
                  org.colors
                    ? ({ backgroundColor: org.colors.primary, color: '#fff', borderColor: org.colors.primary } as CSSProperties)
                    : undefined
                }
              >
                <span
                  aria-hidden
                  className="dot-lime"
                  style={org.colors ? ({ backgroundColor: org.colors.secondary, boxShadow: 'none' } as CSSProperties) : undefined}
                />
                <span className="min-w-0 truncate">{org.name}</span>
              </span>
            </div>
          )}
          <h1 className="display-title mt-3 text-section text-ink lg:text-display">{team.name}</h1>
          {org?.colors && (
            <div aria-hidden className="mt-3 flex h-1.5 w-24 overflow-hidden rounded-full">
              <span className="flex-1" style={{ backgroundColor: org.colors.primary }} />
              <span className="flex-1" style={{ backgroundColor: org.colors.secondary }} />
            </div>
          )}
          <DotLine
            as="p"
            className="mt-2 text-copy-lg text-body"
            parts={[
              team.sport_label,
              `${team.season} ${words(team.phase).toLowerCase()}`,
              org?.level_label,
              longDateOf(d.as_of),
            ]}
          />
        </div>
        <RosterTile s={d.summary} />
      </header>

      <div className={`mt-10 ${SETTLE}`} style={{ animationDelay: '80ms' }}>
        <BriefingCard d={d} />
      </div>

      <div className="mt-stack space-y-stack">
        <Block index={2}>
          <ScheduleStrip events={d.events} asOf={d.as_of} />
        </Block>
        <Block index={3}>
          <AttentionList rows={d.attention} teamId={team.id} />
        </Block>
        <Block index={4}>
          <RosterTable rows={d.roster} teamId={team.id} />
        </Block>
        <Block index={5}>
          <InjuryBoard injuries={d.injuries} teamId={team.id} />
        </Block>
        <div className="grid gap-stack min-[1200px]:grid-cols-[minmax(0,1fr)_360px] min-[1200px]:items-start">
          <Block index={6}>
            <TeamLoadChart load={d.load} asOf={d.as_of} />
          </Block>
          <Block index={7}>
            <StaffCard staff={d.staff} />
          </Block>
        </div>
      </div>

      <StaffGuardrail text={d.guardrail} className="mt-8" />
    </div>
  )
}

/** The morning briefing: the opaque briefing-wash card under the head, the
 *  headline at the lede step, the sentence, and the day's counts as a
 *  stats row — roster, availability, mean readiness, who has answered, flags. */
function BriefingCard({ d }: { d: TeamDashboard }) {
  const s = d.summary
  const availHint = [
    s.modified > 0 ? `${s.modified} modified` : null,
    s.out > 0 ? `${s.out} out` : null,
  ]
    .filter(Boolean)
    .join(' · ')
  return (
    <SectionCard
      sum
      title="Morning briefing"
      icon={<NarrativeTile provider="fallback" />}
      aside={<DotLine className="meta tabular-nums" parts={['Rules-based', longDateOf(d.as_of)]} />}
    >
      <p className="text-lede font-medium text-ink">{d.briefing.headline}</p>
      <p className="mt-1 max-w-[64ch] text-copy-lg text-ink">{d.briefing.text}</p>
      <dl className="mt-5 flex flex-wrap gap-x-10 gap-y-4 border-t border-hairline pt-5">
        <Stat label="Roster" value={String(s.roster)} hint={s.roster === 1 ? 'athlete' : 'athletes'} />
        <Stat label="Available" value={String(s.available)} hint={availHint || undefined} />
        <Stat label="Mean readiness" value={fmt(s.mean_readiness)} hint={s.mean_readiness == null ? 'no scores yet' : undefined} />
        <Stat label="Answered this morning" value={`${s.answered_today}`} hint={`of ${s.roster}`} />
        <Stat label="Flags" value={String(s.flags)} hint={s.flags === 0 ? 'none' : 'across the roster'} />
      </dl>
    </SectionCard>
  )
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex min-w-0 flex-col">
      <dt className="text-copy text-secondary">{label}</dt>
      <dd className="mt-0.5 flex items-baseline gap-1.5">
        <span className="big-num text-[2rem] text-ink">{value}</span>
        {hint && <span className="text-copy text-secondary">{hint}</span>}
      </dd>
    </div>
  )
}

/** The head's right-hand tile, like the worklist's: the roster size in light
 *  type on sage, a white meter of availability, and the counts on a solid
 *  glass caption — each a dot + word + number. Hidden under 1024px, where the
 *  briefing's stats row carries the same counts. */
function RosterTile({ s }: { s: TeamSummary }) {
  const rows = [
    { key: 'available', label: 'Available', n: s.available, dot: PRIORITY.low.dot, bar: 'bg-white/90' },
    { key: 'modified', label: 'Modified', n: s.modified, dot: PRIORITY.medium.dot, bar: 'bg-white/45' },
    {
      key: 'out',
      label: 'Out',
      n: s.out,
      dot: PRIORITY.high.dot,
      bar: 'bg-lime shadow-[0_0_10px_rgb(212_241_74_/_.7)]',
    },
  ]
  const total = Math.max(1, s.roster)
  return (
    <div className="hidden w-[300px] shrink-0 lg:block">
      <section aria-label="Roster at a glance" className="gtile g-sage spotlight" data-loop>
        <div className="gtile-top">
          <div>
            <span className="gtile-kicker block">Roster</span>
            <span className="gtile-num big-num">
              {s.roster}
              <small>{s.roster === 1 ? 'athlete' : 'athletes'}</small>
            </span>
          </div>
          <div className="gtile-side">
            <b>{s.mean_readiness ?? DASH}</b>
            mean readiness
          </div>
        </div>
        <div aria-hidden className="relative z-[1] mx-5 mb-3 mt-4 flex h-2 gap-1">
          {rows
            .filter((r) => r.n > 0)
            .map((r, i) => (
              <span
                key={r.key}
                className={`meter-fill h-full rounded-pill ${r.bar}`}
                style={{
                  flexGrow: r.n / total,
                  flexBasis: 0,
                  backgroundImage: 'none',
                  animationDelay: `${0.3 + i * 0.08}s`,
                }}
              />
            ))}
        </div>
        <ul className="gtile-cap !pb-2 !pt-1.5">
          {rows.map((r) => (
            <li key={r.key} className="flex min-h-8 items-center gap-2">
              <span aria-hidden className={`h-2 w-2 shrink-0 rounded-pill ${r.dot}`} />
              <span className="flex-1 text-copy text-ink">{r.label}</span>
              <span className="big-num text-[1.375rem] text-ink">{r.n}</span>
            </li>
          ))}
          <li className="mt-1 flex min-h-8 items-center gap-2 border-t border-hairline pt-1">
            <span aria-hidden className="h-2 w-2 shrink-0 rounded-pill bg-brand" />
            <span className="flex-1 text-copy text-ink">Answered this morning</span>
            <span className="big-num text-[1.375rem] text-ink">
              {s.answered_today}
              <span className="text-copy text-secondary">/{s.roster}</span>
            </span>
          </li>
        </ul>
      </section>
    </div>
  )
}
