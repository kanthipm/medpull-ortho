import type { LoadUnit } from '../../api/hep'

/** Loads as the clinic reads them. Every load is stored, sent and received
 *  in kilograms; a clinic that works in pounds sees and types pounds, and
 *  the conversion happens here, with the same factor the server words its
 *  own lines with (`hep/service.LB_PER_KG`). */

export const LB_PER_KG = 2.20462

/** The largest load the server takes, in kilograms. */
export const LOAD_MAX_KG = 500

function trim(n: number, places: number): string {
  return String(Number(n.toFixed(places)))
}

/** "25 lb", "11.5 kg": pounds to a tenth, as the server prints them, so
 *  25 lb typed comes back 25 lb. */
export function loadText(kg: number, unit: LoadUnit): string {
  return unit === 'lb' ? `${trim(kg * LB_PER_KG, 1)} lb` : `${trim(kg, 1)} kg`
}

/** A week's or a session's load moved, in whole units: "1,050 lb". */
export function movedText(kg: number, unit: LoadUnit): string {
  const value = unit === 'lb' ? kg * LB_PER_KG : kg
  return `${Math.round(value).toLocaleString()} ${unit}`
}

/** A stored load as the field shows it, or the empty string. */
export function loadField(kg: number | null | undefined, unit: LoadUnit): string {
  if (kg == null) return ''
  return unit === 'lb' ? trim(kg * LB_PER_KG, 1) : trim(kg, 1)
}

/** What a load field holds, as kilograms to two places (as fine as a tenth
 *  of a pound), or null when it is empty or not a number. */
export function loadKg(field: string, unit: LoadUnit): number | null {
  const text = field.trim()
  if (!text) return null
  const n = Number(text)
  if (!Number.isFinite(n) || n < 0) return null
  return Number((unit === 'lb' ? n / LB_PER_KG : n).toFixed(2))
}

/** The field's ceiling and step in the clinic's unit. */
export function loadBounds(unit: LoadUnit): { max: number; step: number } {
  return unit === 'lb' ? { max: Math.floor(LOAD_MAX_KG * LB_PER_KG), step: 2.5 } : { max: LOAD_MAX_KG, step: 0.5 }
}

export function unitOf(clinic: { load_unit?: string } | null | undefined): LoadUnit {
  return clinic?.load_unit === 'lb' ? 'lb' : 'kg'
}
