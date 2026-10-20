"""AWS Lambda entrypoint.

One deployment artifact serves two roles, selected by the shape of the event:

* an HTTP event from the Lambda Function URL (behind CloudFront) is handed to
  the FastAPI app through Mangum;
* a direct invoke carrying ``{"action": "seed"}`` rebuilds the demo database
  and uploads it to S3. That runs on a second function pointed at this same
  zip with a longer timeout, because seeding warms every insight through Groq.

Cold-start work — reading the Groq key out of SSM, pulling the database down
from S3 — happens at import time so it is paid once per execution environment
rather than once per request.
"""

import json
import logging
import os

logging.getLogger().setLevel(os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

from app.aws import secrets, storage  # noqa: E402
from app.aws.config import aws_settings  # noqa: E402

# A writable database path is not optional: /var/task is read-only, and the
# default from app.config points inside it. Fail at import with a clear message
# rather than at the first query with a mystery "unable to open database file".
_db_path = str(aws_settings.local_db_path)
if not _db_path.startswith("/tmp/"):
    raise RuntimeError(
        f"DATABASE_URL must live under /tmp on Lambda (got {_db_path!r}); "
        "only /tmp is writable in the execution environment."
    )

secrets.load()
storage.bootstrap()

from mangum import Mangum  # noqa: E402

from app.database import ensure_schema  # noqa: E402
from app.main import app  # noqa: E402

# The hydrated database may predate a table the models now declare (the
# sports tables, say). create_all(checkfirst=True) is additive and cheap.
ensure_schema()

# lifespan="off": the startup hook spawns a background insight warmer that is a
# laptop convenience. On Lambda it would re-run on every cold start, burn the
# Groq free-tier quota and race other instances — the deploy warms the database
# once, up front, instead.
_asgi = Mangum(app, lifespan="off")


def _forbidden() -> dict:
    return {
        "statusCode": 403,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"detail": "Direct access is not permitted."}),
    }


def _origin_is_cloudfront(event: dict) -> bool:
    """The Function URL is public (AuthType NONE) so CloudFront can reach it
    without SigV4 signing; CloudFront injects a shared secret header that a
    direct caller cannot guess, which is what actually gates access."""
    expected = aws_settings.origin_verify_secret
    if not expected:
        return True
    import hmac

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    return hmac.compare_digest(headers.get("x-origin-verify", ""), expected)


def _seed(event: dict) -> dict:
    from app.seed.seed import refuse_destructive_reseed, run_seed

    if not bool(event.get("reset", True)):
        # There is no incremental seed. app.seed builds one fixed roster with
        # fixed primary keys, so a second pass over a populated database dies on
        # "UNIQUE constraint failed: care_team_members.id" partway through, with
        # the write lock held and half a roster written. Refuse it up front.
        return {
            "ok": False,
            "error": "reset=false is not supported: the seed rebuilds a fixed roster, "
            "so it can only run against an empty schema.",
        }

    with storage.write_lock():
        # Start from whatever is durable rather than a stale copy left in this
        # instance's /tmp: the reset drops only the tables the models declare,
        # and everything else in the file rides along into the upload below.
        storage.hydrate(force=True)
        # A reseed drops every table. On an empty deployment that is the point;
        # on a live one it deletes real people, so it has to be asked twice.
        refusal = refuse_destructive_reseed(bool(event.get("force")))
        if refusal is not None:
            logger.warning("Seed refused: %s", refusal["error"])
            return refusal
        summary = run_seed(reset=True)
        uploaded = storage.persist(conditional=False)
    logger.info("Seed complete: %s (uploaded=%s)", summary, uploaded)
    return {"ok": True, "uploaded": uploaded, "counts": summary}


def _personal_daily(event: dict) -> dict:
    """The subscribers' morning run (app/personal/daily.py), invoked by the
    EventBridge schedule. Holds the write lock like any mutating request:
    it writes plans, thread lines and, when asked, texts."""
    from app.database import SessionLocal
    from app.personal import daily

    with storage.write_lock():
        storage.hydrate(force=True)
        db = SessionLocal()
        try:
            result = daily.run(db, text=bool(event.get("text", True)))
        finally:
            db.close()
        uploaded = storage.persist(conditional=False) if storage.is_dirty() else False
    logger.info("Personal daily complete: %s (uploaded=%s)", result, uploaded)
    return {"ok": True, "uploaded": uploaded, **result}


def _seed_sports(event: dict) -> dict:
    """Add (or refresh) the MedPull Sports demo roster on a live database.
    Additive: only the fictional athletes' rows are reset, nothing else is
    touched, so it is safe on a deployment with real people on it."""
    from app.database import SessionLocal
    from app.sports.seed import seed_sports

    with storage.write_lock():
        storage.hydrate(force=True)
        ensure_schema()
        db = SessionLocal()
        try:
            counts = seed_sports(db)
        finally:
            db.close()
        uploaded = storage.persist(conditional=False)
    logger.info("Sports seed complete: %s (uploaded=%s)", counts, uploaded)
    return {"ok": True, "uploaded": uploaded, "counts": counts}


def _fill_athlete(event: dict) -> dict:
    """Fill one athlete's account with the showcase (app/sports/showcase.py):
    ``{"action": "fill_athlete", "patient_id": "...", "org_id": "rockets", "team_id": "rockets-nba"}``.
    The account itself is untouched; the generated streams are replaced."""
    from app.database import SessionLocal
    from app.sports.showcase import fill_pro_athlete

    patient_id = str(event.get("patient_id") or "").strip()
    if not patient_id:
        return {"ok": False, "error": "patient_id is required"}
    org_id = event.get("org_id", "rockets") or None
    team_id = event.get("team_id", "rockets-nba") or None
    with storage.write_lock():
        storage.hydrate(force=True)
        ensure_schema()
        db = SessionLocal()
        try:
            try:
                counts = fill_pro_athlete(db, patient_id, org_id=org_id, team_id=team_id)
            except ValueError as e:
                db.rollback()
                return {"ok": False, "error": str(e)}
        finally:
            db.close()
        uploaded = storage.persist(conditional=False)
    logger.info("Showcase filled for %s: %s (uploaded=%s)", patient_id, counts, uploaded)
    return {"ok": True, "uploaded": uploaded, "patient_id": patient_id, "counts": counts}


def _comp(event: dict) -> dict:
    """An operator's complimentary grant for one personal space, named by
    its email login or its patient id (a space opened by phone number has
    no email): ``{"action": "comp", "email": "...", "days": 365}`` or
    ``{"action": "comp", "patient_id": "...", "days": 365}``."""
    from app.database import SessionLocal
    from app.models.patient import Patient
    from app.personal import auth, subscription
    from app.personal.scope import PERSONAL

    email = auth.normalize_email(str(event.get("email") or ""))
    patient_id = str(event.get("patient_id") or "").strip()
    if email is None and not patient_id:
        return {"ok": False, "error": "email or patient_id is required"}
    days = int(event.get("days") or 365)
    with storage.write_lock():
        storage.hydrate(force=True)
        ensure_schema()
        db = SessionLocal()
        try:
            if email is not None:
                cred = auth.credential_for_email(db, email)
                if cred is None:
                    return {"ok": False, "error": f"No account uses {email}"}
                patient_id = cred.patient_id
            patient = db.get(Patient, patient_id)
            if patient is None or patient.account_kind != PERSONAL:
                return {"ok": False, "error": f"No personal space with id {patient_id!r}"}
            row = subscription.grant_comp(db, patient, days, note=str(event.get("note") or "operator"))
            db.commit()
            expires = row.expires_at.isoformat() if row.expires_at else None
        finally:
            db.close()
        uploaded = storage.persist(conditional=False)
    logger.info("Comp granted to %s until %s (uploaded=%s)", patient_id, expires, uploaded)
    return {"ok": True, "uploaded": uploaded, "patient_id": patient_id, "email": email, "expires_at": expires}


def handler(event, context):
    # Function URL / API Gateway events always carry requestContext; a direct
    # invoke of an admin action never does.
    if isinstance(event, dict) and "requestContext" not in event and event.get("action"):
        action = event["action"]
        if action == "seed":
            return _seed(event)
        if action == "seed_sports":
            return _seed_sports(event)
        if action == "comp":
            return _comp(event)
        if action == "fill_athlete":
            return _fill_athlete(event)
        if action == "personal_daily":
            return _personal_daily(event)
        return {"ok": False, "error": f"Unknown action: {action}"}

    if not _origin_is_cloudfront(event):
        return _forbidden()

    return _asgi(event, context)
