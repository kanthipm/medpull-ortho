"""HEP tables. Every table is new and every column nullable or scalar-
defaulted, so ``ensure_schema`` can add them to a live database.

The clinic is the ``Hospital`` row (``hospital_id``). A standard exercise
has no clinic and every clinic sees it; a custom one belongs to the clinic
that wrote it and is never listed elsewhere.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

BODY_REGIONS = ("knee", "hip", "ankle", "shoulder", "back_core", "full_body")
REGION_LABELS = {
    "knee": "Knee", "hip": "Hip", "ankle": "Ankle & foot", "shoulder": "Shoulder",
    "back_core": "Back & core", "full_body": "Full body",
}
CATEGORIES = ("mobility", "strengthening", "balance", "functional")
CATEGORY_LABELS = {
    "mobility": "Mobility", "strengthening": "Strengthening", "balance": "Balance",
    "functional": "Functional",
}
ORIGINS = ("standard", "custom")
EXERCISE_STATUSES = ("draft", "review", "approved", "archived")
SIDES = ("left", "right", "both", "not_applicable")
MEDIA_STATUSES = ("pending", "approved", "rejected")
PLAN_STATUSES = ("draft", "active", "superseded", "archived")
INVITATION_STATUSES = ("pending", "sent", "failed", "claimed", "expired", "revoked")
ASSIGNMENT_STATUSES = ("assigned", "done", "skipped")
# What the therapist asks for with an exercise: a clip of the attempt, and
# the wearable on during it. "required" holds the completion until it is there.
REQUIREMENTS = ("off", "optional", "required")


class Exercise(Base):
    __tablename__ = "exercises"
    __table_args__ = (Index("ix_exercises_hospital_origin", "hospital_id", "origin"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # catalog slug ("knee_heel_slides"); None for a clinic's custom exercise
    key: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    origin: Mapped[str] = mapped_column(String, default="custom")  # standard | custom
    hospital_id: Mapped[str | None] = mapped_column(
        ForeignKey("hospitals.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String)
    synonyms: Mapped[list[Any]] = mapped_column(JSON, default=list)
    body_region: Mapped[str] = mapped_column(String, default="full_body")
    category: Mapped[str] = mapped_column(String, default="mobility")
    # patient-facing, plain: numbered steps joined by newlines
    instructions: Mapped[str] = mapped_column(String, default="")
    equipment: Mapped[str] = mapped_column(String, default="")
    precautions: Mapped[str] = mapped_column(String, default="")
    media_id: Mapped[int | None] = mapped_column(
        ForeignKey("exercise_media.id"), nullable=True
    )
    # draft | review | approved | archived — clinical review state of the
    # text and media; assignment is allowed from any state but archived
    status: Mapped[str] = mapped_column(String, default="draft")
    # bumped on every wording change; a plan snapshots the version it used
    version: Mapped[int] = mapped_column(Integer, default=1)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String, default="library")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ExerciseMedia(Base):
    """A demonstration: a short H.264 MP4 loop plus a poster frame. Playback
    is served only once ``approval_status`` is approved."""

    __tablename__ = "exercise_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hospital_id: Mapped[str | None] = mapped_column(
        ForeignKey("hospitals.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String, default="video")  # video | image
    # The exercise a clinic's own clip demonstrates (its therapist doing it),
    # so a standard exercise can carry one demonstration per clinic without
    # being copied. Library clips are reached through Exercise.media_id and
    # leave this empty. A plain integer, not a foreign key: exercises already
    # point here through media_id and a cycle would stall table creation.
    exercise_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # "public:<path>" under the SPA bucket for standard clips, or an
    # attachments blob key for a clinic upload
    storage_key: Mapped[str] = mapped_column(String)
    poster_key: Mapped[str | None] = mapped_column(String, nullable=True)
    content_type: Mapped[str] = mapped_column(String, default="video/mp4")
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approval_status: Mapped[str] = mapped_column(String, default="pending")
    reviewed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    uploaded_by: Mapped[str] = mapped_column(String, default="provider")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ExercisePlan(Base):
    __tablename__ = "exercise_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    patient_id: Mapped[str | None] = mapped_column(
        ForeignKey("patients.id"), nullable=True, index=True
    )
    # the invitation this plan waits on; a plain id, since the invitation
    # already points back at the plan and two foreign keys would be a cycle
    invitation_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String, default="Home exercise plan")
    status: Mapped[str] = mapped_column(String, default="draft")
    notes: Mapped[str] = mapped_column(String, default="")  # patient-facing
    assigned_by: Mapped[str] = mapped_column(String, default="provider")
    # optimistic concurrency: PUT must carry the version it read
    version: Mapped[int] = mapped_column(Integer, default=1)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class PlanExercise(Base):
    """One prescribed exercise. ``snapshot`` freezes the library text at
    publish so a later library edit never rewrites a prescription."""

    __tablename__ = "plan_exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("exercise_plans.id"), index=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True)
    exercise_version: Mapped[int] = mapped_column(Integer, default=1)
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    sets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hold_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frequency: Mapped[str] = mapped_column(String, default="")  # "2x daily", "3x per week"
    side: Mapped[str] = mapped_column(String, default="not_applicable")
    clinician_instructions: Mapped[str] = mapped_column(String, default="")
    precautions_override: Mapped[str] = mapped_column(String, default="")


class ExerciseCompletion(Base):
    """One day done, in the patient's timezone. The unique key makes a
    second tap on the same day a no-op."""

    __tablename__ = "exercise_completions"
    __table_args__ = (
        UniqueConstraint("plan_exercise_id", "completion_date", name="uq_exercise_completion_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_exercise_id: Mapped[int] = mapped_column(
        ForeignKey("plan_exercises.id"), index=True
    )
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    completion_date: Mapped[date] = mapped_column(Date)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    source: Mapped[str] = mapped_column(String, default="app")
    feedback: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class PatientInvitation(Base):
    """A plan published to a phone number with no record yet. The token is
    stored hashed; the text carries no name and no clinical detail."""

    __tablename__ = "patient_invitations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    normalized_phone: Mapped[str] = mapped_column(String, index=True)  # E.164
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("exercise_plans.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    send_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    message_handle: Mapped[str | None] = mapped_column(String, nullable=True)
    claimed_by_patient_id: Mapped[str | None] = mapped_column(
        ForeignKey("patients.id"), nullable=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String, default="provider")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AuditEvent(Base):
    """Who did what to a HEP row: library edits, plan publishes, invitation
    sends, claims. ``actor`` is the care-team member id or "provider" until
    the console has per-clinician logins."""

    __tablename__ = "hep_audit_events"
    __table_args__ = (Index("ix_hep_audit_subject", "subject_type", "subject_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hospital_id: Mapped[str | None] = mapped_column(
        ForeignKey("hospitals.id"), nullable=True, index=True
    )
    actor: Mapped[str] = mapped_column(String, default="provider")
    action: Mapped[str] = mapped_column(String)  # exercise.create | plan.publish | ...
    subject_type: Mapped[str] = mapped_column(String)
    subject_id: Mapped[str] = mapped_column(String)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ExerciseAssignment(Base):
    """One exercise on one patient's calendar day — the clinic's schedule, as
    against a plan's standing prescription. This is what the therapist puts
    on the week grid and what the patient's Today shows. Done, the row itself
    carries what the patient reported after it: pain, a note, the clip they
    sent back (an ``attachments`` row on their thread). One row per
    patient, exercise and day; a second assignment of the same exercise on
    the same day is refused rather than stacked."""

    __tablename__ = "exercise_assignments"
    __table_args__ = (
        UniqueConstraint("patient_id", "exercise_id", "scheduled_for",
                         name="uq_exercise_assignment_day"),
        Index("ix_exercise_assignments_clinic_day", "hospital_id", "scheduled_for"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True)
    # Set when the day was generated from a plan item; the therapist's own
    # calendar entries leave it empty.
    plan_exercise_id: Mapped[int | None] = mapped_column(
        ForeignKey("plan_exercises.id"), nullable=True
    )
    scheduled_for: Mapped[date] = mapped_column(Date, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    sets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hold_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    side: Mapped[str] = mapped_column(String, default="not_applicable")
    # The lifter's dose beyond counts: the load on the bar or in hand, and
    # the effort the therapist wants it to feel like (RPE 0–10).
    load_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    rpe_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Patient-facing, in the therapist's words ("slow on the way down").
    clinician_instructions: Mapped[str] = mapped_column(String, default="")
    assigned_by: Mapped[str] = mapped_column(String, default="provider")  # care team id
    # REQUIREMENTS: what she asks for with this one.
    video_requirement: Mapped[str] = mapped_column(String, default="optional")
    wearable_requirement: Mapped[str] = mapped_column(String, default="optional")
    status: Mapped[str] = mapped_column(String, default="assigned")  # ASSIGNMENT_STATUSES
    # --- the session, when the patient started it from the phone ---
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pain_before: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0–10, at the start
    wearable_worn: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # From the wearable's heart-rate samples inside [started_at, ended_at],
    # when any arrived; the server fills these, never the phone.
    hr_avg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hr_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # --- what came back ---
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pain_after: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0–10
    effort: Mapped[int | None] = mapped_column(Integer, nullable=True)  # RPE 0–10, how it felt
    sets_done: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reps_done: Mapped[int | None] = mapped_column(Integer, nullable=True)
    load_done_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    completion_source: Mapped[str | None] = mapped_column(String, nullable=True)  # app | console
    video_attachment_id: Mapped[int | None] = mapped_column(
        ForeignKey("attachments.id"), nullable=True
    )
    skip_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    # --- the therapist's look at it ---
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String, nullable=True)  # care team id
    review_note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ExerciseTemplate(Base):
    """A program: the exercises a clinic puts on a kind of patient's week,
    with their days and doses, applied to a patient from a start date for a
    number of weeks ("Patellar tendinopathy · phase 2"). Items are the
    assignment's own fields, as JSON, with ``weekdays`` (0 = Monday … 6, or
    null for every day) in place of a date."""

    __tablename__ = "exercise_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String, default="")
    # [{"exercise_key" | "exercise_id", "weekdays": [0,2,4] | null, "sets", "reps",
    #   "hold_seconds", "side", "load_kg", "rpe_target", "clinician_instructions",
    #   "video_requirement", "wearable_requirement"}]
    items: Mapped[list[Any]] = mapped_column(JSON, default=list)
    weeks: Mapped[int] = mapped_column(Integer, default=2)
    created_by: Mapped[str] = mapped_column(String, default="provider")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
