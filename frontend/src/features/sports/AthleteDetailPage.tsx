import { ChevronLeft } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useTeamAthlete, type AthleteBrief, type Verdict } from '../../api/sports'
import { NarrativeTile } from '../../components/AIAttribution'
import Avatar from '../../components/Avatar'
import EmptyState from '../../components/EmptyState'
import SectionCard from '../../components/SectionCard'
import { SkeletonCard, SkeletonLine } from '../../components/Skeleton'
import { relativeTime } from '../../lib/format'
import DotLine from '../patient/DotLine'
import AthleteStatusControl from './AthleteStatusControl'
import AthleteThread from './AthleteThread'
import LoadCard from './LoadCard'
import PerformanceSection from './PerformanceSection'
import ReadinessCard from './ReadinessCard'
import RehabSection from './RehabSection'
import SessionsCard from './SessionsCard'
import SignalPanels from './SignalPanels'
import { AvailabilityPill, StaffGuardrail } from './SportsBits'
import SuggestionsCard from './SuggestionsCard'
import WellnessCard from './WellnessCard'
import { fmt } from './sportsFormat'

/* Layout, like the patient page (R3). AppShell caps the page at 1240px.
 *
 *   header      the page head (`data-hero`) in the sky window: the 64px
 *               avatar on a white ring, the name at the display step with
 *               the ONE availability pill, the facts line, the staff note,
 *               and the availability control (opaque) on the right.
 *   >= 1200px   grid [main 1fr | side 360px].
 *               main: brief, verdict, suggestions, load, performance, rehab,
 *               sessions, messages
 *               side: readiness, wellness, overnight signals
 *   <  1200px   one column; the wrappers become `display: contents` and
 *               `order-*` interleaves the cards in reading priority. */

const COLUMN = 'contents min-[1200px]:flex min-[1200px]:min-w-0 min-[1200px]:flex-col min-[1200px]:gap-stack'

function Block({ index, order, children }: { index: number; order: string; children: ReactNode }) {
  return (
    <div className={`rise min-w-0 ${order}`} style={{ '--rise-delay': `${index * 55}ms` } as CSSProperties}>
      {children}
    </div>
  )
}

export default function AthleteDetailPage() {
  const { teamId = '', id = '' } = useParams()
  const { data, isLoading, isError } = useTeamAthlete(teamId, id)
  const back = `/sports/teams/${teamId}`

  if (isLoading) {
    return (
      <div className="pt-6" role="status" aria-label="Loading athlete">
        <div className="flex items-center gap-4">
          <span className="h-16 w-16 shrink-0 animate-pulse rounded-pill bg-soft" />
          <div className="w-full max-w-sm space-y-2">
            <SkeletonLine className="h-6 w-2/3" />
            <SkeletonLine className="w-full" />
          </div>
        </div>
        <div className="mt-8 grid gap-stack min-[1200px]:grid-cols-[minmax(0,1fr)_360px]">
          <div className="space-y-stack">
            <SkeletonCard lines={4} />
            <SkeletonCard rows={3} />
          </div>
          <div className="space-y-stack">
            <SkeletonCard lines={3} />
            <SkeletonCard lines={4} />
          </div>
        </div>
      </div>
    )
  }
  if (isError || !data) {
    return (
      <EmptyState
        title="This athlete couldn’t be loaded"
        className="mt-6"
        action={
          <Link to={back} className="btn-tinted">
            <ChevronLeft aria-hidden size={16} /> Back to the team
          </Link>
        }
      >
        Check the link, or pick the athlete from the team board again.
      </EmptyState>
    )
  }

  const { athlete: a, profile, brief, recovery, performance, rehab, sessions, thread, team } = data
  const jersey = profile.jersey ?? a.jersey
  const facts = [
    profile.position ?? a.position,
    jersey ? `#${jersey}` : null,
    profile.class_year ?? a.class_year,
    profile.age != null ? `Age ${profile.age}` : null,
    profile.height_cm != null ? `${fmt(profile.height_cm)} cm` : null,
    profile.weight_kg != null ? `${fmt(profile.weight_kg)} kg` : null,
    `${a.days_with_data} days of data`,
  ]

  return (
    <div className="pb-4">
      <header data-hero className="rise pb-2 pt-3" style={{ '--rise-delay': '0ms' } as CSSProperties}>
        <Link to={back} className="btn-plain btn-sm -ml-3">
          <ChevronLeft aria-hidden size={16} /> {team.name}
        </Link>

        <div className="mt-4 flex flex-wrap items-start gap-x-5 gap-y-4">
          <Avatar
            name={a.name}
            tier={a.severity >= 2 ? 'high' : undefined}
            size="xl"
            className="mt-1 shrink-0 shadow-soft ring-4 ring-panel"
          />
          <div className="min-w-0 flex-1 basis-[240px] min-[1024px]:max-w-[calc(58%-76px)]">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <h1 className="display-title text-display text-ink">{a.name}</h1>
              <AvailabilityPill availability={a.availability} label={a.availability_label} />
            </div>
            <DotLine as="p" className="mt-1.5 text-copy text-body" parts={facts} />
            {a.status_note && <p className="mt-2 text-copy text-ink">{a.status_note}</p>}
          </div>
          <AthleteStatusControl
            className="w-full min-[900px]:ml-auto min-[900px]:w-auto min-[900px]:pt-1"
            teamId={teamId}
            athleteId={a.id}
            status={a.availability}
            note={a.status_note}
          />
        </div>
      </header>

      <div className="mt-8 flex flex-col gap-stack min-[1200px]:grid min-[1200px]:grid-cols-[minmax(0,1fr)_360px] min-[1200px]:items-start">
        <div className={COLUMN}>
          <Block index={1} order="order-1">
            <BriefCard brief={brief} />
          </Block>
          <Block index={2} order="order-2">
            <VerdictCard verdict={recovery.verdict} days={recovery.days_with_data} />
          </Block>
          <Block index={4} order="order-4">
            <SuggestionsCard suggestions={recovery.suggestions ?? []} />
          </Block>
          <Block index={7} order="order-7">
            <LoadCard load={recovery.load} asOf={recovery.as_of} />
          </Block>
          <Block index={8} order="order-8">
            <PerformanceSection performance={performance} />
          </Block>
          <Block index={9} order="order-9">
            <RehabSection rehab={rehab} />
          </Block>
          <Block index={10} order="order-10">
            <SessionsCard sessions={sessions} />
          </Block>
          <Block index={11} order="order-11">
            <AthleteThread teamId={teamId} athleteId={a.id} firstName={a.first_name} thread={thread} />
          </Block>
        </div>

        <div className={COLUMN}>
          <Block index={3} order="order-3">
            <ReadinessCard readiness={recovery.readiness} />
          </Block>
          <Block index={5} order="order-5">
            <WellnessCard wellness={recovery.wellness} />
          </Block>
          <Block index={6} order="order-6">
            <SignalPanels panels={recovery.panels ?? {}} />
          </Block>
        </div>
      </div>

      <StaffGuardrail className="mt-8" />
    </div>
  )
}

/** The brief as the athlete reads it in the app, on the briefing wash, with
 *  its provenance: the renderer's work is never headlined as AI. */
function BriefCard({ brief }: { brief: AthleteBrief }) {
  const rulesBased = brief.provider === 'fallback'
  return (
    <SectionCard
      sum
      title="Athlete’s brief"
      icon={<NarrativeTile provider={brief.provider} />}
      aside={
        <DotLine
          className="meta tabular-nums"
          parts={[rulesBased ? 'Rules-based' : 'Written by AI', relativeTime(brief.generated_at)]}
        />
      }
    >
      <p className="text-lede font-medium text-ink">{brief.headline}</p>
      <p className="mt-1 max-w-[68ch] text-copy-lg text-ink">{brief.brief}</p>
      <p className="meta mt-3">As the athlete reads it in the app.</p>
    </SectionCard>
  )
}

function VerdictCard({ verdict: v, days }: { verdict: Verdict; days: number }) {
  return (
    <SectionCard title="Today’s verdict" aside={days > 0 ? `${days} days of data` : undefined}>
      <p className="text-title font-light text-ink">{v.title}</p>
      {v.reason && <p className="mt-1 text-copy-lg text-ink">{v.reason}</p>}
      {v.detail && <p className="mt-1 text-copy text-body">{v.detail}</p>}
      {v.reasons.length > 0 && (
        <ul className="mt-3 space-y-1 border-t border-hairline pt-3" aria-label="Why">
          {v.reasons.map((r, i) => (
            <li key={i} className="flex gap-1.5 text-copy text-ink">
              <span aria-hidden className="text-brand-ink">→</span>
              <span>{r}</span>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  )
}
