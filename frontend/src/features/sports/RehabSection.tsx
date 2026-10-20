import { Bandage } from 'lucide-react'
import { useState } from 'react'
import type { AthleteRehab, RehabCriterion, RehabFocus, RehabInjury, RehabMeasure } from '../../api/sports'
import Disclosure from '../../components/Disclosure'
import EmptyState from '../../components/EmptyState'
import SectionCard from '../../components/SectionCard'
import { shortDate } from '../../lib/format'
import DotLine from '../patient/DotLine'
import { CriterionMark, Meter, MiniSpark } from './SportsBits'
import { DASH, TONE_TEXT, dateWithYear, fmt, lsiTone, weekLabel, words } from './sportsFormat'

/** One card per active injury: where it stands, the phase and its gates,
 *  the return-to-sport criteria, this block's focus, and the measures with
 *  the involved side's trend. */
export default function RehabSection({ rehab }: { rehab: AthleteRehab }) {
  if (rehab.active.length === 0) {
    return (
      <SectionCard title="Rehab">
        <EmptyState variant="inline" icon={<Bandage />} family="violet" title="No active injury">
          An injury logged in the app, or by the medical staff, opens its phases and criteria here.
        </EmptyState>
      </SectionCard>
    )
  }
  return (
    <div className="space-y-stack">
      {rehab.active.map((inj) => (
        <InjuryCard key={inj.id} inj={inj} />
      ))}
    </div>
  )
}

function InjuryCard({ inj }: { inj: RehabInjury }) {
  const phase = inj.phase
  const rts = inj.rts
  const rtsPct =
    rts.pct ?? (rts.met != null && rts.total ? Math.round((100 * rts.met) / rts.total) : null)
  const since =
    inj.anchor === 'surgery' && inj.date_of_surgery
      ? `since surgery on ${shortDate(inj.date_of_surgery)}`
      : inj.date_of_injury
        ? `since the injury on ${shortDate(inj.date_of_injury)}`
        : null
  return (
    <SectionCard
      title={inj.label}
      aside={
        <DotLine className="meta" parts={[inj.side ? `${words(inj.side)} side` : null, weekLabel(inj.weeks)]} />
      }
    >
      <DotLine as="p" className="text-copy text-body" parts={[since, inj.graft, inj.clinician]} />
      {inj.note && <p className="mt-1.5 text-copy text-ink">{inj.note}</p>}

      {phase && (
        <section className="mt-5 border-t border-hairline pt-4" aria-label={`Phase ${phase.number} of ${phase.of}`}>
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <h3 className="text-copy-lg font-medium text-ink">
              Phase {phase.number} of {phase.of}
              <span className="font-normal text-secondary"> — {phase.name}</span>
            </h3>
            <span className="meta">{phase.window}</span>
          </div>
          <ol className="mt-2 flex gap-1" aria-hidden>
            {Array.from({ length: phase.of }, (_, i) => (
              <li key={i} className={`h-1.5 flex-1 rounded-pill ${i < phase.number ? 'bg-brand' : 'bg-line'}`} />
            ))}
          </ol>
          <p className="meta mt-1.5 tabular-nums">
            {phase.met} of {phase.total} gates met
            {phase.override != null ? ' · phase set by the clinician' : ''}
          </p>
          {phase.criteria.length > 0 && (
            <ul className="mt-2 divide-y divide-hairline" aria-label="Gates for this phase">
              {phase.criteria.map((c) => (
                <CriterionRow key={`${c.measure_key}-${c.label}`} c={c} />
              ))}
            </ul>
          )}
          {phase.avoid.length > 0 && <p className="meta mt-2.5">Avoid: {phase.avoid.join(', ')}</p>}
        </section>
      )}

      <section className="mt-5 border-t border-hairline pt-4" aria-label="Return to sport">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <h3 className="text-copy-lg font-medium text-ink">Return to sport</h3>
          <span className="meta tabular-nums">
            {rts.met ?? DASH} of {rts.total ?? DASH} criteria · {rtsPct == null ? DASH : `${rtsPct}%`}
          </span>
        </div>
        <Meter pct={rtsPct} className="mt-2" />
        <DotLine
          as="p"
          className="meta mt-1.5"
          parts={[
            rts.projected && `Projected ${dateWithYear(rts.projected)}`,
            rts.window && `window ${shortDate(rts.window[0])} – ${dateWithYear(rts.window[1])}`,
            rts.typical_weeks && `typically ${rts.typical_weeks[0]}–${rts.typical_weeks[1]} weeks`,
          ]}
        />
        {rts.criteria.length > 0 && (
          <Disclosure className="mt-2" label={`All ${rts.criteria.length} criteria`}>
            <ul className="divide-y divide-hairline">
              {rts.criteria.map((c) => (
                <CriterionRow key={`${c.measure_key}-${c.label}`} c={c} />
              ))}
            </ul>
          </Disclosure>
        )}
        {rts.reinjury_note && (
          <Disclosure className="mt-1" label="Why the gates matter">
            <p className="text-copy text-body">{rts.reinjury_note}</p>
          </Disclosure>
        )}
      </section>

      {inj.focus.length > 0 && (
        <section className="mt-5 border-t border-hairline pt-4" aria-label="Focus">
          <h3 className="text-copy-lg font-medium text-ink">This block’s focus</h3>
          <ul className="mt-2 space-y-3">
            {inj.focus.map((f, i) => (
              <FocusItem key={i} f={f} />
            ))}
          </ul>
        </section>
      )}

      {inj.measures.length > 0 && <Measures measures={inj.measures} />}
    </SectionCard>
  )
}

function CriterionRow({ c }: { c: RehabCriterion }) {
  return (
    <li className="flex items-center gap-2.5 py-2">
      <CriterionMark met={c.met} />
      <span className="min-w-0 flex-1 text-copy text-ink">{c.label}</span>
      <span className={`meta shrink-0 tabular-nums ${c.met ? TONE_TEXT.low : ''}`}>
        {c.value_text ?? DASH}
        {c.date && <span className="text-secondary"> · {shortDate(c.date)}</span>}
      </span>
    </li>
  )
}

function FocusItem({ f }: { f: RehabFocus }) {
  return (
    <li>
      <p className="text-copy font-medium text-ink">{f.title}</p>
      {f.why && <p className="mt-0.5 text-copy text-body">{f.why}</p>}
      {f.actions.length > 0 && (
        <ul className="mt-1 space-y-0.5">
          {f.actions.map((a, i) => (
            <li key={i} className="flex gap-1.5 text-copy text-ink">
              <span aria-hidden className="text-brand-ink">→</span>
              <span>{a}</span>
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}

const SHOW_MEASURES = 8

function Measures({ measures }: { measures: RehabMeasure[] }) {
  const [all, setAll] = useState(false)
  const rows = all ? measures : measures.slice(0, SHOW_MEASURES)
  return (
    <section className="mt-5 border-t border-hairline pt-4" aria-label="Measures">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="text-copy-lg font-medium text-ink">Measures</h3>
        <span className="meta">involved · uninvolved · symmetry</span>
      </div>
      <ul className="mt-1 divide-y divide-hairline">
        {rows.map((m) => (
          <MeasureRow key={m.key} m={m} />
        ))}
      </ul>
      {measures.length > SHOW_MEASURES && (
        <div className="mt-2 flex justify-center">
          <button type="button" className="btn-plain btn-sm" onClick={() => setAll((a) => !a)}>
            {all ? 'Show fewer' : `Show all ${measures.length} measures`}
          </button>
        </div>
      )}
    </section>
  )
}

function MeasureRow({ m }: { m: RehabMeasure }) {
  const dp = m.decimals ?? (Number.isInteger(m.latest ?? 0) ? 0 : 1)
  const tone = lsiTone(m.lsi)
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
      <div className="min-w-0 flex-1 basis-[160px]">
        <span className="block truncate text-copy text-ink">{m.label}</span>
        <span className="meta block truncate">
          {m.latest_date ? shortDate(m.latest_date) : 'Not logged'}
          {m.unit ? ` · ${m.unit}` : ''}
        </span>
      </div>
      <span className="w-16 text-right text-copy tabular-nums text-ink">{fmt(m.latest, dp)}</span>
      <span className="w-16 text-right text-copy tabular-nums text-secondary">
        {m.uninvolved_latest == null ? DASH : fmt(m.uninvolved_latest, dp)}
      </span>
      <span className={`w-20 text-right text-copy tabular-nums ${tone ? TONE_TEXT[tone] : 'text-secondary'}`}>
        {m.lsi == null ? DASH : `${fmt(m.lsi)}% LSI`}
      </span>
      <MiniSpark
        values={m.involved.map((p) => p.value)}
        width={64}
        height={22}
        label={`${m.label}, involved side`}
      />
    </li>
  )
}
