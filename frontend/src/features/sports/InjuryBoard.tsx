import { Bandage } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { InjuryBoardRow } from '../../api/sports'
import Avatar from '../../components/Avatar'
import EmptyState from '../../components/EmptyState'
import SectionCard from '../../components/SectionCard'
import DotLine from '../patient/DotLine'
import { Meter } from './SportsBits'
import { DASH, dateWithYear, weekLabel, words } from './sportsFormat'

/** One tile per active injury: who, what, the phase as a small stepper and
 *  the return-to-sport criteria as a meter with the projected date. The
 *  athlete's name is the tile's link. */
export default function InjuryBoard({ injuries, teamId }: { injuries: InjuryBoardRow[]; teamId: string }) {
  return (
    <SectionCard title="Injury board" aside={injuries.length > 0 ? `${injuries.length} active` : undefined}>
      {injuries.length === 0 ? (
        <EmptyState variant="inline" icon={<Bandage />} family="violet" title="No active injuries">
          An injury logged in the app, or by the medical staff, shows its phase and criteria here.
        </EmptyState>
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2 min-[1200px]:grid-cols-3">
          {injuries.map((inj) => (
            <InjuryTile key={`${inj.athlete_id}-${inj.id}`} inj={inj} teamId={teamId} />
          ))}
        </ul>
      )}
    </SectionCard>
  )
}

function InjuryTile({ inj, teamId }: { inj: InjuryBoardRow; teamId: string }) {
  const phase = inj.phase
  const rtsPct =
    inj.rts.pct ??
    (inj.rts.met != null && inj.rts.total ? Math.round((100 * inj.rts.met) / inj.rts.total) : null)
  return (
    <li className="relative flex flex-col rounded-control bg-soft p-4">
      <div className="flex items-center gap-2.5">
        <Avatar name={inj.name} size="sm" />
        <div className="min-w-0 flex-1">
          <Link
            to={`/sports/teams/${teamId}/athletes/${inj.athlete_id}`}
            className="stretched-link block truncate text-copy font-medium text-ink"
          >
            {inj.name}
          </Link>
          <p className="meta truncate">{inj.position ?? ''}</p>
        </div>
      </div>

      <p className="mt-3 text-copy-lg font-medium text-ink">{inj.label}</p>
      <DotLine
        as="p"
        className="meta mt-0.5"
        parts={[inj.side ? `${words(inj.side)} side` : null, weekLabel(inj.weeks)]}
      />

      {phase && (
        <div className="mt-3">
          <p className="text-copy text-ink">
            Phase {phase.number} of {phase.of}
            <span className="text-secondary"> — {phase.name}</span>
          </p>
          <ol className="mt-1.5 flex gap-1" aria-label={`Phase ${phase.number} of ${phase.of}`}>
            {Array.from({ length: phase.of }, (_, i) => (
              <li
                key={i}
                aria-current={i + 1 === phase.number ? 'step' : undefined}
                className={`h-1.5 flex-1 rounded-pill ${i < phase.number ? 'bg-brand' : 'bg-line'}`}
              />
            ))}
          </ol>
          <p className="meta mt-1 tabular-nums">
            {phase.met} of {phase.total} gates met · {phase.window}
          </p>
        </div>
      )}

      <div className="mt-3 border-t border-hairline pt-3">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-copy text-ink">Return to sport</span>
          <span className="meta tabular-nums">
            {inj.rts.met ?? DASH} of {inj.rts.total ?? DASH} criteria
          </span>
        </div>
        <Meter pct={rtsPct} className="mt-1.5" />
        <p className="meta mt-1">
          {inj.rts.projected ? `Projected ${dateWithYear(inj.rts.projected)}` : 'No projected date yet'}
        </p>
      </div>
    </li>
  )
}
