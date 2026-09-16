/** Human wording for the evidence codes the next-step planner cites.
 *
 *  `NextStep.source` is a list of machine identifiers — risk-reason codes from
 *  backend/app/engine/risk.py (`COMPOSITE_HIGH`, `STEPS_FALLING`, …) and care
 *  metric ids from backend/app/engine/care/catalog.py (`M12`, `C4`, …). They are
 *  the API contract and stay as they are; this map is display only. A code with
 *  no entry here is humanised (underscores to spaces, sentence case) so a bare
 *  identifier never reaches the clinician.
 *
 *  Metric names are the catalog's `name` field, verbatim. */
const SOURCE_LABELS: Record<string, string> = {
  // Risk-reason codes (engine/risk.py, plan/next_steps.py)
  COMPOSITE_HIGH: 'Composite risk high',
  TRAJECTORY_BEHIND: 'Behind expected trajectory',
  STEPS_FALLING: 'Steps falling',
  RHR_RISING: 'Resting heart rate rising',
  TEMP_RISING: 'Skin temperature rising',
  HRV_FALLING: 'HRV falling',
  WALKING_SLOWING: 'Walking speed slowing',
  SLEEP_DISRUPTED: 'Sleep disrupted',
  SPO2_LOW: 'Blood oxygen low',
  RR_RISING: 'Respiratory rate rising',
  GAIT_ASYMMETRY_HIGH: 'Gait asymmetry high',
  DRIFT_DETECTED: 'Gradual drift detected',
  LOW_COVERAGE: 'Low data coverage',
  ADHERENCE_LOW: 'Low task adherence',
  ON_TRACK: 'On track',
  CHECKIN_OVERDUE: 'Check-in overdue',

  // Care metrics M1–M18, C1–C4 (engine/care/catalog.py)
  M1: 'Acute:chronic load ratio',
  M2: 'Symptom–load sensitivity',
  M3: 'Loading asymmetry decay',
  M4: 'Walking economy',
  M5: 'Endurance-fade index',
  M6: 'Sit-to-stand frequency',
  M7: 'Cadence recovery curve',
  M8: 'Stair reintroduction & flight tolerance',
  M9: 'Nocturnal disruption',
  M10: 'Autonomic recovery trend',
  M11: 'Circadian rest–activity amplitude',
  M12: 'Multi-signal deterioration index',
  M13: 'Thermal–cardiac coupling',
  M14: 'Verified adherence',
  M15: 'Disengagement risk',
  M16: 'Data confidence',
  M17: 'Recovery-trajectory fit',
  M18: 'Plateau / regression change-point',
  C1: 'Weight trend & fluid-gain signal',
  C2: 'Oxygen saturation & desaturation burden',
  C3: 'Glucose time-in-range',
  C4: 'Blood-pressure control',
}

/** `WALKING_SLOWING` → "Walking slowing"; unknown codes never render raw. */
function humanise(code: string): string {
  const words = code.replace(/[_-]+/g, ' ').trim().toLowerCase()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

export function sourceLabel(code: string): string {
  return SOURCE_LABELS[code] ?? SOURCE_LABELS[code.toUpperCase()] ?? humanise(code)
}
