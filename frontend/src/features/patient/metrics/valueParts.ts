import type { CareMetric } from '../../../api/care'

/** The number and its unit, with the unit printed once. Some engine values
 *  already end in their unit ("12.3%" with unit "%"); the unit then moves out
 *  of the number rather than printing twice. Kept out of the component files
 *  so they export components only. */
export function valueParts(m: Pick<CareMetric, 'value' | 'unit'>): { value: string; unit: string } {
  const raw = m.value == null ? '—' : String(m.value).trim()
  const unit = (m.unit ?? '').trim()
  if (unit && raw.endsWith(unit)) {
    return { value: raw.slice(0, -unit.length).trimEnd(), unit }
  }
  return { value: raw, unit }
}
