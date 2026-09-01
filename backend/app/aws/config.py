"""AWS-specific settings, kept out of app.config so the core app stays
cloud-agnostic. Every value is optional: with S3_BUCKET unset the whole AWS
layer disables itself and the app runs off a local SQLite file as before.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import settings


class AwsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")

    # Durable home of the SQLite database. Empty => AWS persistence disabled.
    s3_bucket: str = ""
    s3_db_key: str = "db/recovery.db"

    # Distributed write lock (an S3 object created with If-None-Match: *).
    # The TTL must stay comfortably under the Lambda timeout so a function that
    # dies mid-request can never wedge the lock for longer than one request:
    # 25s against the API function's 45s, and 840s against the seed function's
    # 900s, which overrides this default through LOCK_TTL_SECONDS.
    s3_lock_key: str = "db/recovery.db.lock"
    lock_ttl_seconds: float = 25.0
    lock_acquire_timeout_seconds: float = 12.0

    # How long a hydrated database may be trusted before a read path re-checks
    # S3 for a newer version. Mutating requests always re-check under the lock,
    # so this only bounds how stale a *read* can be.
    freshness_ttl_seconds: float = 5.0

    # Shared secret injected by CloudFront so the public Function URL cannot be
    # invoked directly. Empty => no origin check (local runs, `sam local`).
    origin_verify_secret: str = ""

    # SSM Parameter Store names holding secrets as SecureStrings. Each is
    # optional and read once per cold start (app/aws/secrets.py).
    groq_api_key_parameter: str = ""
    junction_api_key_parameter: str = ""
    junction_webhook_secret_parameter: str = ""

    # The background insight warmer is a laptop convenience. On Lambda it would
    # re-run on every cold start, burn the Groq free-tier quota and race other
    # instances, so the deploy warms the database once instead.
    warm_caches_on_startup: bool = True

    @property
    def enabled(self) -> bool:
        return bool(self.s3_bucket)

    @property
    def local_db_path(self) -> Path:
        """Filesystem path SQLAlchemy is bound to.

        Derived from DATABASE_URL rather than configured separately so the
        file this module uploads is always the file the app reads.
        """
        url = settings.database_url
        if not url.startswith("sqlite:///"):
            raise RuntimeError(
                f"S3 persistence only supports SQLite; DATABASE_URL is {url!r}"
            )
        return Path(url.removeprefix("sqlite:///"))


aws_settings = AwsSettings()


def running_on_lambda() -> bool:
    import os

    return bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
