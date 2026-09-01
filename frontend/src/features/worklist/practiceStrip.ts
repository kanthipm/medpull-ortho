import type { ReadoutItem } from '../../components/MetricCluster'
import type { PracticeOverview } from '../../api/types'

/** The practice overview strip: five numbers, every one of them the practice
 *  endpoint's own. Its `needs_review` counts the same tier the headline above
 *  it counts, which is the whole reason to read it here rather than recount
 *  the worklist — two counts of one thing eventually disagree.
 *
 *  The revenue figure is priced from demo CPT rates (national averages, not a
 *  contracted fee schedule), so it says so. */
export function practiceReadout(practice: PracticeOverview): ReadoutItem[] {
  return [
    { key: 'patients', label: 'on RTM', value: practice.rtm_patients },
    {
      key: 'review',
      label: 'high risk',
      value: practice.needs_review,
      tone: practice.needs_review > 0 ? 'high' : undefined,
    },
    {
      key: 'bill',
      label: 'ready to bill',
      value: practice.ready_to_bill,
      tone: practice.ready_to_bill > 0 ? 'low' : undefined,
    },
    {
      key: 'adh',
      label: 'adherence',
      value: practice.therapy_adherence_pct != null ? `${practice.therapy_adherence_pct}%` : '—',
    },
    {
      key: 'rev',
      label: 'est. revenue',
      value: `$${practice.estimated_revenue.toLocaleString('en-US', { maximumFractionDigits: 0 })}`,
      hint: 'demo rates',
    },
  ]
}
