import { useQuery } from '@tanstack/react-query'
import { fetchJson } from './client'

/** The glossary behind every "i" icon (`GET /api/explain`): one entry per
 *  care metric (by id), per wearable signal (by metric_key) and per page
 *  section. Static for the life of a deploy, so it is fetched once and kept
 *  for the whole session. */

export interface Explanation {
  title: string
  /** What the number is. */
  what: string
  /** The data it takes in. */
  inputs: string
  /** How it is computed, in words. */
  how: string
  /** How to read the statuses and the chart. */
  reading: string
  /** The minimum history before it says anything. */
  shows_after: string
  patient_what: string
  patient_why: string
  patient_help: string
}

export type SectionKey = 'trajectory' | 'composite' | 'adherence' | 'confidence' | 'risk_tier'

export interface Glossary {
  metrics: Record<string, Explanation>
  signals: Record<string, Explanation>
  sections: Record<SectionKey, Explanation>
}

export function useExplain() {
  return useQuery({
    queryKey: ['explain'],
    queryFn: () => fetchJson<Glossary>('/api/explain'),
    staleTime: Infinity,
    gcTime: Infinity,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  })
}

/** The entry for a care metric (`M1` … `C6`), or undefined while loading. */
export function explainMetric(g: Glossary | undefined, id: string): Explanation | undefined {
  return g?.metrics[id]
}

/** The entry for a wearable signal card (`steps`, `resting_hr`, …). */
export function explainSignal(g: Glossary | undefined, key: string): Explanation | undefined {
  return g?.signals[key]
}

/** The entry for a page-level chart or readout. */
export function explainSection(g: Glossary | undefined, key: SectionKey): Explanation | undefined {
  return g?.sections[key]
}
