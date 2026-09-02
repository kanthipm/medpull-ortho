"""Shared domain enums — single source of truth for backend + API contracts."""

from enum import StrEnum


class ProcedureType(StrEnum):
    TKA = "TKA"                    # total knee arthroplasty
    THA = "THA"                    # total hip arthroplasty
    ACL = "ACL"                    # ACL reconstruction
    ROTATOR_CUFF = "ROTATOR_CUFF"
    LUMBAR = "LUMBAR"              # lumbar decompression/fusion
    ANKLE = "ANKLE"                # ankle fracture ORIF
    MENISCUS = "MENISCUS"          # meniscus repair


class SourceProvider(StrEnum):
    APPLE = "apple"
    FITBIT = "fitbit"
    GARMIN = "garmin"
    OURA = "oura"
    WHOOP = "whoop"
    DEXCOM = "dexcom"
    WITHINGS = "withings"
    POLAR = "polar"
    SAMSUNG = "samsung"
    MOCK = "mock"
    # Aggregators are providers in their own right — an aggregator-delivered
    # row must never masquerade as MOCK (or as the underlying device brand,
    # which lands in value_json/raw_payload for provenance instead).
    TERRA = "terra"
    JUNCTION = "junction"
    # The Fitbit app/API became Google Health (2026); non-transferable tokens,
    # so FITBIT stays for historical rows and this is NOT a rename.
    GOOGLE_HEALTH = "google_health"
    # Samsung wearables are reachable only through Health Connect on-device.
    HEALTH_CONNECT = "health_connect"
    # The RTM-qualifying streams: pain/ROM/HEP adherence are patient-reported,
    # in-clinic 6MWT/goniometry are clinician-entered.
    PATIENT_REPORTED = "patient_reported"
    CLINICIAN_ENTERED = "clinician_entered"


class ConnectionStatus(StrEnum):
    """Lifecycle of a patient's aggregator account (models/connection.py)."""

    PENDING_LINK = "pending_link"  # aggregator user exists; no device linked yet
    LINKED = "linked"  # at least one provider connected
    ERROR = "error"  # the aggregator reported a terminal provider error
    DISCONNECTED = "disconnected"  # deregistered by an operator


class MetricType(StrEnum):
    STEPS = "steps"
    RESTING_HR = "resting_hr"
    HR_SAMPLE = "hr_sample"
    HRV_RMSSD = "hrv_rmssd"
    SLEEP_DURATION = "sleep_duration"
    SLEEP_STAGES = "sleep_stages"
    ACTIVE_ENERGY = "active_energy"
    EXERCISE_SESSION = "exercise_session"
    SPO2 = "spo2"
    RESPIRATORY_RATE = "respiratory_rate"
    SKIN_TEMP = "skin_temp"
    WALKING_SPEED = "walking_speed"
    STEP_LENGTH = "step_length"
    DOUBLE_SUPPORT_PCT = "double_support_pct"
    WALKING_ASYMMETRY_PCT = "walking_asymmetry_pct"
    WALKING_STEADINESS = "walking_steadiness"
    STAIR_SPEED_UP = "stair_speed_up"
    STAIR_SPEED_DOWN = "stair_speed_down"
    SIX_MIN_WALK = "six_min_walk"
    CALORIES = "calories"
    # --- P0 correctness: separate statistics that must never share a series ---
    # Apple ships SDNN only (heartRateVariabilitySDNN); there is no RMSSD
    # identifier and no conversion constant between the two.
    HRV_SDNN = "hrv_sdnn"
    # Apple/Oura/Garmin/Health Connect skin temperature is a DELTA from a
    # personal baseline (can be negative); WHOOP/Withings are ABSOLUTE degC.
    # SKIN_TEMP keeps the absolute convention; deltas land here.
    SKIN_TEMP_DELTA = "skin_temp_delta"
    # Distinguishes "not worn" from "worn 40 minutes" from "not synced", and is
    # the evidence an RTM auditor asks for on each qualifying day. Declared
    # ahead of its use: no connector emits it, and engine/confidence.py gates on
    # KEY_METRICS coverage instead, which does not include it.
    WEAR_TIME_MINUTES = "wear_time_minutes"
    # --- The RTM-qualifying patient-reported stream (SPEC.md §2, unbuilt) ---
    # Declared so the vocabulary is settled, but nothing produces or consumes
    # these yet: there is no patient-facing capture path and the engine analyzes
    # device metrics only (engine/pipeline.py ANALYZED_METRICS).
    PAIN_NRS = "pain_nrs"                    # 0-10 numeric rating scale
    RANGE_OF_MOTION = "range_of_motion"      # degrees; details in value_json
    THERAPY_ADHERENCE = "therapy_adherence"  # HEP sessions completed per day
    EXERCISE_REPS = "exercise_reps"          # count
    PROM_SCORE = "prom_score"                # value_json {instrument, score, ceiling}


class Granularity(StrEnum):
    INSTANT = "instant"
    INTERVAL = "interval"
    # A bounded clinical event (sleep episode, workout, PT session) — distinct
    # from INTERVAL's fixed-width buckets so dataload can tell a 15-minute
    # activity bucket from an 8-hour sleep episode.
    SESSION = "session"
    DAILY_SUMMARY = "daily_summary"


class RiskLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MISSING_DATA = "missing_data"


class TrajectoryState(StrEnum):
    BEHIND = "behind"
    ON_TRACK = "on"
    AHEAD = "ahead"
    UNKNOWN = "unknown"


class MetricStatus(StrEnum):
    FLAG = "flag"
    WATCH = "watch"
    OK = "ok"
    NODATA = "nodata"


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "med"
    LOW = "low"


class InsightKind(StrEnum):
    WORKLIST_REASON = "worklist_reason"
    PATIENT_SUMMARY = "patient_summary"
    SUGGESTED_ACTIONS = "suggested_actions"
    DAILY_BRIEFING = "daily_briefing"
    ASK = "ask"  # roster-level natural-language Q&A (cached per question)


class TimeLogActivity(StrEnum):
    CHART_REVIEW = "chart_review"
    MESSAGING = "messaging"
    CALL = "call"
    DOCUMENTATION = "documentation"
    CARE_COORDINATION = "care_coordination"


class InteractionKind(StrEnum):
    MESSAGE = "message"
    CALL = "call"
    SCHEDULE_FOLLOWUP = "schedule_followup"
    ESCALATE = "escalate"
    UPDATE_PLAN = "update_plan"
    ASSIGN_TASK = "assign_task"


class DocumentKind(StrEnum):
    ENCOUNTER_NOTE = "encounter_note"
    MONTHLY_SUMMARY = "monthly_summary"


class DocumentStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    SMS = "sms"
    EMAIL = "email"


class NotificationStatus(StrEnum):
    UNREAD = "unread"
    READ = "read"
    SENT_STUB = "sent_stub"


class AdherenceStatus(StrEnum):
    VERIFIED = "verified"
    SELF_ATTESTED = "self_attested"
    MISSED = "missed"


class CareRole(StrEnum):
    SURGEON = "surgeon"
    NURSE = "nurse"
    PT = "pt"
    ADMIN = "admin"


# The guardrail sentence used across the product. AI output that omits it (or
# uses diagnostic language) is replaced by the deterministic fallback.
GUARDRAIL_SENTENCE = "Monitoring signals for clinician review — not a diagnosis."
