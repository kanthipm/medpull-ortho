# Bump when analytics logic changes — part of the input hash, so results recompute.
# 1.2.1: the composite is told the real post-op day instead of inferring one
# from the newest reading present, and the gait rule applies the same recency
# window every other rule gets through its DeviationResult. Both can move a
# tier, so assessments stored by 1.2.0 must not survive.
ENGINE_VERSION = "1.2.1"
