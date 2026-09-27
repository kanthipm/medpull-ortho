# Bump when analytics logic changes — part of the input hash, so results recompute.
# 1.2.1: the composite is told the real post-op day instead of inferring one
# from the newest reading present, and the gait rule applies the same recency
# window every other rule gets through its DeviationResult. Both can move a
# tier, so assessments stored by 1.2.0 must not survive.
# 1.3.0: the care-metrics report objects (M1-M18 + C1-C6, engine/care) join
# the analytics bundle as `care_metrics`, and the input hash now also covers
# check-ins, adherence records and tasks. Assessments stored by 1.2.x carry no
# care metrics at all, so they must not survive the upgrade.
# 1.4.0: the in-house mobility set (engine/mobility: step length, cadence,
# double support, steadiness, stair speeds, six-minute walk, joint angles), the
# derived stress index and the activity totals join the signal cards, judged
# for display only. Assessments stored by 1.3.x carry none of those cards.
ENGINE_VERSION = "1.4.0"
