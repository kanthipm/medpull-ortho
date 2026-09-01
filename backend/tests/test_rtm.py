"""RTM compliance engine + API contracts (SPEC.md §§1, 6, 7, 8, 9).

Readiness stages are pinned per seeded patient (see seed/rtm.py's roster
story). The seeded DB is session-scoped and never rolled back, so every test
below the "mutations" banner obeys one convention: assert a delta against a
value read in the same test, or put back what it changed before it returns.
Nothing enforces that mechanically — a test that leaves the roster altered
breaks the pinned stages above it for the rest of the session.
"""

from datetime import date, timedelta

from app.models.enums import GUARDRAIL_SENTENCE
from app.models.patient import Patient
from app.rtm.coverage import WINDOW_DAYS
from app.rtm.readiness import compute_readiness


def _readiness(db, patient_id: str) -> dict:
    patient = db.get(Patient, patient_id)
    return compute_readiness(db, patient, date.today())


# --- golden readiness stages -------------------------------------------------

def test_marcus_needs_interactive_call(db):
    """The spec's own showcase: enrolled, 14 minutes, no live interaction."""
    r = _readiness(db, "marcus")
    assert r["enrollment"]["complete"] is True
    assert r["treatment_management"]["minutes"] == 14
    assert r["treatment_management"]["interactive_communication"] is False
    assert r["ready_to_bill"] is False
    # the call is provider-actionable NOW; monitoring days accrue on their own
    assert "call" in r["suggested_action"].lower()


def test_monitoring_days_start_at_enrollment(db):
    """Pre-enrollment device wear builds engine baselines but never counts
    toward the 16-of-30 monitoring threshold. Marcus enrolled 8 days ago, so
    despite ~3 weeks of device data his monitoring count is at most 9 days."""
    r = _readiness(db, "marcus")
    assert r["monitoring"]["enrolled"] is True
    assert 0 < r["monitoring"]["days"] <= 9
    assert r["monitoring"]["eligible"] is False


def test_unenrolled_patients_accrue_no_monitoring_days(db):
    for patient_id in ("grace", "robert"):
        r = _readiness(db, patient_id)
        assert r["monitoring"]["enrolled"] is False
        assert r["monitoring"]["days"] == 0
        monitoring_codes = {e["cpt"]: e for e in r["billing"]}
        assert monitoring_codes["98985"]["eligible"] is False
        assert "enrollment" in monitoring_codes["98985"]["note"].lower()


def test_grace_consent_pending(db):
    r = _readiness(db, "grace")
    assert r["enrollment"]["education_complete"] is True
    assert r["enrollment"]["consent_complete"] is False
    assert r["enrollment"]["complete"] is False
    assert "consent" in r["suggested_action"].lower()


def test_robert_baseline_pending(db):
    r = _readiness(db, "robert")
    assert r["enrollment"]["consent_complete"] is True
    assert r["enrollment"]["baseline_complete"] is False
    assert "baseline" in r["suggested_action"].lower()


def test_david_ready_to_bill(db):
    """Enrolled, ≥16 monitoring days, 45 min incl. call, docs approved."""
    r = _readiness(db, "david")
    assert r["enrollment"]["complete"] is True
    assert r["monitoring"]["eligible"] is True
    assert r["treatment_management"]["minutes"] == 45
    assert r["treatment_management"]["interactive_communication"] is True
    assert r["documentation_ready"] is True
    assert r["ready_to_bill"] is True
    assert "ready to bill" in r["suggested_action"].lower()
    cpts = {e["cpt"] for e in r["billing"] if e["eligible"]}
    # 98975 is NOT here: david enrolled 32 days ago, so his one-time setup
    # code belongs to the window that has already closed. Ready to Bill is
    # about the recurring codes.
    assert {"98977", "98980", "98981"} <= cpts
    assert "98975" not in cpts


def test_setup_code_is_billed_once(db):
    """98975 covers the one-time setup. It is offered for the window that
    follows enrollment and never again — otherwise it adds its rate to every
    patient's estimated value every month, forever."""
    fresh = {e["cpt"]: e for e in _readiness(db, "marcus")["billing"]}
    assert fresh["98975"]["eligible"] is True  # marcus enrolled 8 days ago

    settled = {e["cpt"]: e for e in _readiness(db, "david")["billing"]}
    assert settled["98975"]["eligible"] is False  # david enrolled 32 days ago
    assert "one-time" in settled["98975"]["note"].lower()


def test_billing_never_mixes_tiers(db):
    """98980 eligible implies no 98979 row; 98981 units are the 20-min excess."""
    r = _readiness(db, "david")
    eligible = {e["cpt"]: e for e in r["billing"] if e["eligible"]}
    assert "98979" not in eligible
    assert eligible["98981"]["units"] == (45 - 20) // 20


def test_elena_partial_treatment_tier(db):
    """12 min with a call → 98979 territory, not yet 98980."""
    r = _readiness(db, "elena")
    assert r["treatment_management"]["minutes"] == 12
    assert r["treatment_management"]["interactive_communication"] is True
    eligible = {e["cpt"] for e in r["billing"] if e["eligible"]}
    assert "98979" in eligible
    assert "98980" not in eligible


# --- API contracts -----------------------------------------------------------

def test_rtm_endpoint_contract(client):
    body = client.get("/api/patients/marcus/rtm").json()
    for key in (
        "enrollment", "monitoring", "treatment_management", "documentation_ready",
        "billing", "ready_to_bill", "suggested_action", "recent_interactions",
    ):
        assert key in body
    assert body["monitoring"]["target"] == 16
    assert body["monitoring"]["window_days"] == 30


def test_patient_detail_rtm_block_unchanged(client):
    """The pre-P1 rtm block stays shape-compatible (window_days pinned)."""
    body = client.get("/api/patients/marcus").json()
    assert body["rtm"]["window_days"] == 30
    assert "days_with_data" in body["rtm"]


def test_practice_overview(client):
    body = client.get("/api/practice/overview").json()
    assert body["rtm_patients"] == 10
    assert body["ready_to_bill"] >= 2  # david + james seeded ready
    assert body["needs_review"] >= 1
    assert body["estimated_revenue"] > 0



def test_documents_generated_with_guardrail(client):
    """Fallback provider (tests force it) still yields valid, guarded docs."""
    body = client.get("/api/patients/linda/rtm/documents").json()
    kinds = {d["kind"] for d in body["documents"]}
    # SPEC.md §7 asks for five document types; DocumentKind has two. This
    # equality pins the shortfall deliberately — widen it when the other
    # three (recovery summary, outreach, treatment management) are built.
    assert kinds == {"encounter_note", "monthly_summary"}
    for doc in body["documents"]:
        assert doc["status"] == "draft"
        assert doc["body"].endswith(GUARDRAIL_SENTENCE)
        lowered = doc["body"].replace(GUARDRAIL_SENTENCE, "").lower()
        assert "detect" not in lowered and "diagnos" not in lowered


def test_approved_documents_survive(client):
    """Seeded approved docs are returned as-is, never regenerated."""
    body = client.get("/api/patients/david/rtm/documents").json()
    assert all(d["status"] == "approved" for d in body["documents"])
    assert all(d["approved_at"] is not None for d in body["documents"])


# --- mutations (deltas only; keep these last) --------------------------------

def _force_stale(db, patient_id: str) -> None:
    """Put a patient into the state every surface is in on the first request
    of a new calendar day: an assessment whose input hash no longer matches,
    and no monitoring window for today. The next recompute restores both."""
    from sqlalchemy import delete

    from app.engine.pipeline import latest_assessment
    from app.models.rtm import MonitoringWindow

    db.execute(delete(MonitoringWindow).where(MonitoringWindow.patient_id == patient_id))
    latest_assessment(db, patient_id).input_hash = "forced-stale"
    db.commit()


def test_practice_overview_agrees_with_the_worklist(client, db):
    """The strip renders directly above the worklist it summarises. Reading
    stored assessments while the worklist recomputed them let the strip report
    nobody needing review on the same screen that listed one."""
    from sqlalchemy import delete

    from app.models.insight import RiskAssessment

    db.execute(delete(RiskAssessment).where(RiskAssessment.patient_id == "marcus"))
    db.commit()
    strip = client.get("/api/practice/overview").json()
    worklist = client.get("/api/worklist").json()
    assert strip["rtm_patients"] == worklist["stats"]["total"]
    assert strip["needs_review"] == worklist["stats"]["high"] > 0


def test_worklist_and_patient_page_agree_on_monitoring_days(client, db):
    """The row chip links to the card. Reading the monitoring window before
    the recompute that writes it made the chip say 15/16d on the exact day the
    card said Complete."""
    _force_stale(db, "linda")
    row = next(
        r for r in client.get("/api/worklist").json()["patients"] if r["id"] == "linda"
    )
    detail = client.get("/api/patients/linda").json()["rtm"]
    assert row["rtm"]["days"] == detail["days_with_data"] > 0
    assert row["rtm"]["eligible"] == detail["qualifies"]


def test_readiness_card_refreshes_the_monitoring_window(client, db):
    """compute_readiness only reads the stored window, so the endpoint has to
    recompute first or it serves a count nothing else on the page agrees
    with."""
    _force_stale(db, "linda")
    card = client.get("/api/patients/linda/rtm").json()
    detail = client.get("/api/patients/linda").json()["rtm"]
    assert card["monitoring"]["days"] == detail["days_with_data"] > 0


def test_unenrolled_patients_cannot_bill_treatment_management(db):
    """Provider minutes on an unenrolled patient are real work but not
    billable work — without the gate they reached estimated_value and the
    practice strip's revenue."""
    from datetime import datetime, time

    from app.models.rtm import ProviderTimeLog

    grace = db.get(Patient, "grace")
    before = _readiness(db, "grace")
    assert before["enrollment"]["complete"] is False
    log = ProviderTimeLog(
        patient_id="grace",
        provider_id=grace.assigned_provider_id,
        activity="call",
        seconds=25 * 60,
        interactive=True,
        occurred_at=datetime.combine(date.today() - timedelta(days=1), time(14, 0)),
        month="{:04d}-{:02d}".format(date.today().year, date.today().month),
    )
    db.add(log)
    db.commit()
    try:
        r = _readiness(db, "grace")
        assert r["treatment_management"]["minutes"] == (
            before["treatment_management"]["minutes"] + 25
        )
        assert r["treatment_management"]["interactive_communication"] is True
        eligible = {e["cpt"] for e in r["billing"] if e["eligible"]}
        assert eligible == set()
        assert r["estimated_value"] == 0.0
    finally:
        db.delete(log)
        db.commit()


def test_documentation_credit_follows_approval_not_the_month_label(db):
    """Every gate on the card measures the same rolling window. Scoping
    documentation by RtmDocument.month instead dropped a patient's approval
    at midnight on the 1st while their minutes carried over."""
    from sqlalchemy import select

    from app.models.rtm import RtmDocument

    documents = db.scalars(
        select(RtmDocument).where(RtmDocument.patient_id == "david")
    ).all()
    saved = {d.id: d.month for d in documents}
    for document in documents:
        document.month = "1999-01"  # approved_at untouched; only the label moves
    db.commit()
    try:
        r = _readiness(db, "david")
        assert r["documentation_ready"] is True
        assert r["ready_to_bill"] is True
    finally:
        for document in documents:
            document.month = saved[document.id]
        db.commit()


def test_monitoring_days_cannot_exceed_the_window(db):
    """readiness.py reads ">= 16" as the spec's "16-30" because the count is
    bounded by the window itself. That only holds while coverage bounds the
    query on today — a future-dated delivery must not accrue a day."""
    from sqlalchemy import select

    from app.models.observation import Observation
    from app.rtm.coverage import update_window

    today = date.today()
    rows = db.scalars(
        select(Observation).where(Observation.patient_id == "david").limit(40)
    ).all()
    saved = [(o.id, o.local_date, o.qualifies_for_rtm) for o in rows]
    for offset, observation in enumerate(rows, start=1):
        observation.local_date = today + timedelta(days=offset)
        observation.qualifies_for_rtm = True
    db.commit()
    try:
        window = update_window(db, "david", today)
        assert window.days_with_data <= WINDOW_DAYS
    finally:
        for observation, (_, local_date, qualifies) in zip(rows, saved):
            observation.local_date = local_date
            observation.qualifies_for_rtm = qualifies
        db.commit()
        update_window(db, "david", today)


def test_one_monitoring_window_row_per_window(db):
    """get_current() serves the newest row for a patient, so a second row for
    the same window lets it serve a stale count. The schema now refuses the
    twin; update_window collapses any a pre-constraint database already holds,
    since there are no migrations to add the constraint retroactively."""
    from sqlalchemy import select

    from app.models.rtm import MonitoringWindow
    from app.rtm.coverage import get_current, update_window

    today = date.today()
    window_start = today - timedelta(days=WINDOW_DAYS - 1)
    update_window(db, "linda", today)
    rows = db.scalars(
        select(MonitoringWindow).where(
            MonitoringWindow.patient_id == "linda",
            MonitoringWindow.window_start == window_start,
        )
    ).all()
    assert len(rows) == 1
    assert get_current(db, "linda").id == rows[0].id


def test_call_logs_time_and_interaction(client):
    before = client.get("/api/patients/linda/rtm").json()
    resp = client.post(
        "/api/patients/linda/actions/call", json={"minutes": 6, "note": "Test call"}
    )
    assert resp.status_code == 200
    after = client.get("/api/patients/linda/rtm").json()
    assert after["treatment_management"]["minutes"] == (
        before["treatment_management"]["minutes"] + 6
    )
    assert after["treatment_management"]["interactive_communication"] is True
    assert after["recent_interactions"][0]["kind"] == "call"


def test_review_time_batches(client):
    before = client.get("/api/patients/linda/rtm").json()["treatment_management"]["minutes"]
    resp = client.post("/api/patients/linda/rtm/review-time", json={"seconds": 120})
    assert resp.json()["logged_seconds"] == 120
    after = client.get("/api/patients/linda/rtm").json()["treatment_management"]["minutes"]
    assert after == before + 2
    # sub-15s pings are ignored, not logged
    resp = client.post("/api/patients/linda/rtm/review-time", json={"seconds": 5})
    assert resp.json()["logged_seconds"] == 0


def test_schedule_followup_requires_time(client):
    resp = client.post(
        "/api/patients/linda/actions/schedule-followup", json={"when": "  "}
    )
    assert resp.status_code == 422


def test_approve_then_regenerate_conflict(client):
    docs = client.get("/api/patients/sofia/rtm/documents").json()["documents"]
    note = next(d for d in docs if d["kind"] == "encounter_note")
    resp = client.post(f"/api/patients/sofia/rtm/documents/{note['id']}/approve")
    assert resp.json()["status"] == "approved"
    # approved documentation is signed — regeneration must refuse
    resp = client.post(f"/api/patients/sofia/rtm/documents/{note['id']}/regenerate")
    assert resp.status_code == 409
    # and sofia's documentation requirement is now satisfied
    assert client.get("/api/patients/sofia/rtm").json()["documentation_ready"] is True


def _enroll(db, patient_id: str, days_ago: int):
    """Complete a patient's enrollment as of `days_ago`, returning a callable
    that puts the row back exactly as it was."""
    from datetime import datetime, time

    from app.models.rtm import EnrollmentStatus

    enrollment = db.get(EnrollmentStatus, patient_id)
    saved = (
        enrollment.education_complete, enrollment.consent_complete,
        enrollment.baseline_complete, enrollment.complete, enrollment.enrolled_at,
    )
    enrollment.education_complete = True
    enrollment.consent_complete = True
    enrollment.baseline_complete = True
    enrollment.complete = True
    enrollment.enrolled_at = datetime.combine(
        date.today() - timedelta(days=days_ago), time(11, 15)
    )
    db.commit()

    def restore() -> None:
        (
            enrollment.education_complete, enrollment.consent_complete,
            enrollment.baseline_complete, enrollment.complete, enrollment.enrolled_at,
        ) = saved
        db.commit()

    return restore


def _time_log(db, patient_id: str, days_ago: int, minutes: int):
    from datetime import datetime, time

    from app.models.rtm import ProviderTimeLog

    patient = db.get(Patient, patient_id)
    occurred = datetime.combine(date.today() - timedelta(days=days_ago), time(14, 0))
    log = ProviderTimeLog(
        patient_id=patient_id,
        provider_id=patient.assigned_provider_id,
        activity="call",
        seconds=minutes * 60,
        interactive=True,
        occurred_at=occurred,
        month=f"{occurred.year:04d}-{occurred.month:02d}",
    )
    db.add(log)
    db.commit()
    return log


def test_minutes_logged_before_enrollment_are_never_billable(db):
    """The gate checked enrollment status NOW and summed minutes from the
    window floor, so completing enrollment turned every earlier minute
    billable at once — the exact 98980 / $50 the unenrolled gate exists to
    prevent, one moment later.

    It is the ordinary workflow, not a contrived state: the suggested action
    for an unenrolled patient is to call them, and the call writes an
    interactive time log.
    """
    restore = _enroll(db, "grace", days_ago=5)
    log = _time_log(db, "grace", days_ago=15, minutes=25)  # before enrollment
    try:
        r = _readiness(db, "grace")
        eligible = {e["cpt"] for e in r["billing"] if e["eligible"]}
        assert "98980" not in eligible
        assert "98981" not in eligible
        assert r["treatment_management"]["minutes"] == 0
        assert r["estimated_value"] == 20.0  # 98975 only — the setup code
        # the same 25 minutes, logged after enrollment, do count
        log.occurred_at = log.occurred_at + timedelta(days=14)
        db.commit()
        after = _readiness(db, "grace")
        assert after["treatment_management"]["minutes"] == 25
        assert {e["cpt"] for e in after["billing"] if e["eligible"]} >= {"98980"}
        assert after["estimated_value"] == 70.0
    finally:
        db.delete(log)
        db.commit()
        restore()


def test_documentation_approved_before_enrollment_does_not_count(db):
    """Same hole, same fix: a note approved before the patient was enrolled
    cannot document a period of RTM service that had not started."""
    from datetime import datetime, time

    from app.models.enums import DocumentKind, DocumentStatus
    from app.models.rtm import RtmDocument

    restore = _enroll(db, "grace", days_ago=5)
    patient = db.get(Patient, "grace")
    document = RtmDocument(
        patient_id="grace",
        kind=DocumentKind.ENCOUNTER_NOTE,
        content={"title": "t", "body": "b"},
        llm_provider="fallback",
        status=DocumentStatus.APPROVED,
        month=f"{date.today().year:04d}-{date.today().month:02d}",
        created_at=datetime.combine(date.today() - timedelta(days=15), time(9, 0)),
        approved_at=datetime.combine(date.today() - timedelta(days=15), time(10, 0)),
        approved_by=patient.assigned_provider_id,
    )
    db.add(document)
    db.commit()
    try:
        assert _readiness(db, "grace")["documentation_ready"] is False
        document.approved_at = document.approved_at + timedelta(days=14)
        db.commit()
        assert _readiness(db, "grace")["documentation_ready"] is True
    finally:
        db.delete(document)
        db.commit()
        restore()


def test_a_complete_enrollment_with_no_date_does_not_500(db):
    """Every gate measures from the enrollment date, and the 98975 branch
    formatted it unguarded — so `complete` with a NULL `enrolled_at` raised
    AttributeError out of GET /rtm and, through practice_overview, out of the
    whole practice strip."""
    from app.models.rtm import EnrollmentStatus

    enrollment = db.get(EnrollmentStatus, "robert")
    saved = (enrollment.complete, enrollment.enrolled_at)
    enrollment.complete = True
    enrollment.enrolled_at = None
    db.commit()
    try:
        r = _readiness(db, "robert")
        assert r["enrollment"]["complete"] is False  # not a datable enrollment
        assert r["ready_to_bill"] is False
        assert r["estimated_value"] == 0.0
    finally:
        enrollment.complete, enrollment.enrolled_at = saved
        db.commit()


def test_a_missing_monitoring_window_heals_on_the_next_read(client, db):
    """run_patient writes two things — the assessment and the monitoring
    window — and the read path only checked the first. Today's input hash
    stays fresh all day, so an empty or yesterday-ended window meant every RTM
    surface agreed on a count that no longer matched the observations, with
    nothing to make it self-heal."""
    from sqlalchemy import delete

    from app.models.rtm import MonitoringWindow

    before = client.get("/api/patients/david/rtm").json()["monitoring"]["days"]
    assert before > 0
    db.execute(delete(MonitoringWindow).where(MonitoringWindow.patient_id == "david"))
    db.commit()

    row = next(
        r for r in client.get("/api/worklist").json()["patients"] if r["id"] == "david"
    )
    detail = client.get("/api/patients/david").json()["rtm"]
    card = client.get("/api/patients/david/rtm").json()["monitoring"]
    assert row["rtm"]["days"] == detail["days_with_data"] == card["days"] == before
