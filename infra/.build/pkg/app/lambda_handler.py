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

from app.main import app  # noqa: E402

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
    from app.seed.seed import run_seed

    reset = bool(event.get("reset", True))
    with storage.write_lock():
        # Start from whatever is durable so a non-reset seed tops up the real
        # database rather than a stale copy left in this instance's /tmp.
        storage.hydrate(force=True)
        summary = run_seed(reset=reset)
        uploaded = storage.persist(conditional=False)
    logger.info("Seed complete: %s (uploaded=%s)", summary, uploaded)
    return {"ok": True, "uploaded": uploaded, "counts": summary}


def handler(event, context):
    # Function URL / API Gateway events always carry requestContext; a direct
    # invoke of an admin action never does.
    if isinstance(event, dict) and "requestContext" not in event and event.get("action"):
        action = event["action"]
        if action == "seed":
            return _seed(event)
        return {"ok": False, "error": f"Unknown action: {action}"}

    if not _origin_is_cloudfront(event):
        return _forbidden()

    return _asgi(event, context)
