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
# 1.4.1: the signal panel is always whole (a never-measured metric is a card
# that says so), a stale metric shows its last reading, and the stress index
# accepts the clustered sync cadence a phone-linked wearable really has.
# 1.4.2: stale cards show pre-op history too, the band-read cards judge any
# current reading, and a stress reading on under a week of baseline is an
# early estimate that cannot flag.
# 1.5.0: metrics with less data. A personal baseline starts at two days
# (provisional until three), the trajectory compares from three days of index,
# every care metric carries a provisional minimum, data confidence judges the
# panel the patient's sources actually report, and every card, care metric and
# the trajectory carry a `readiness` countdown. Assessments stored by 1.4.x
# carry none of that and must not survive.
ENGINE_VERSION = "1.5.0"
