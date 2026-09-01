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


class Granularity(StrEnum):
    INSTANT = "instant"
    INTERVAL = "interval"
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
