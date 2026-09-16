"""Where a patient's files live.

The database cannot hold them. It is one SQLite file that every Lambda
instance downloads and a mutating request re-uploads (``app/aws/storage.py``),
so a single wound photo in a table would be paid for on every cold start and
every write. Bytes therefore go to object storage beside that file, under
their own prefix, and the database keeps a row pointing at them.

Two backends, one interface:

* **S3**, when ``S3_BUCKET`` is set. Objects land under ``attachments/`` —
  never ``web/``, which the bucket policy makes readable by CloudFront and
  is how the SPA is served. Nothing about this prefix is public: a reader
  gets a short-lived presigned URL minted per request, after the API has
  checked they may see that patient's thread.
* **A directory**, otherwise. A laptop and the test suite keep the same code
  paths without an AWS account, and the API streams the bytes itself.

Deliberately not in ``app/aws/``: that package is the database's own
persistence machinery, with a lock and an ETag dance this has no part in.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.aws.config import aws_settings
from app.config import BACKEND_DIR

logger = logging.getLogger(__name__)

# Everything this module writes lives under here, and it is never the SPA's
# prefix: web/* is world-readable through the distribution.
PREFIX = "attachments"

# What a patient or a clinician may attach. Deliberately short: an image of a
# wound, a document from the clinic. Anything executable or scriptable is
# refused at the door rather than sanitised later.
ALLOWED_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}
MAX_BYTES = 12 * 1024 * 1024  # 12 MB: a modern phone photo with room to spare
# How long a download link is good for. Long enough to open an image in a
# browser or app, short enough that a leaked URL in a log or a history entry
# stops working before anyone finds it.
DOWNLOAD_TTL_S = 300
UPLOAD_TTL_S = 300


class BlobError(ValueError):
    """A refusal the API turns into a 4xx (bad type, too large, gone)."""


@dataclass(frozen=True)
class StoredBlob:
    key: str
    byte_size: int
    sha256: str


def enabled_s3() -> bool:
    return bool(aws_settings.s3_bucket)


def local_root() -> Path:
    """Where the directory backend keeps its files."""
    return Path(os.environ.get("ATTACHMENT_DIR") or (BACKEND_DIR / "data" / "attachments"))


def check_type(content_type: str | None) -> str:
    """The stored content type, or a refusal.

    The client's claim is never trusted as-is: it decides the extension and,
    on download, the ``Content-Type`` header a browser will act on.
    """
    normalized = (content_type or "").split(";")[0].strip().lower()
    if normalized not in ALLOWED_TYPES:
        allowed = ", ".join(sorted(ALLOWED_TYPES))
        raise BlobError(f"{content_type or 'that file type'} is not one we accept ({allowed})")
    return normalized


def check_size(byte_size: int) -> int:
    if byte_size <= 0:
        raise BlobError("That file is empty")
    if byte_size > MAX_BYTES:
        raise BlobError(f"That file is larger than {MAX_BYTES // (1024 * 1024)} MB")
    return byte_size


def new_key(patient_id: str, content_type: str) -> str:
    """An opaque key. The patient id is a path segment for operability — a
    per-patient purge is one prefix — and the rest is random, so a key is
    never guessable from anything a reader knows."""
    return f"{PREFIX}/{patient_id}/{uuid.uuid4().hex}{ALLOWED_TYPES[content_type]}"


# --- writing -------------------------------------------------------------------


def put(key: str, data: bytes, content_type: str) -> StoredBlob:
    """Store bytes under ``key``. Overwrites, so a retry of the same upload
    is idempotent rather than a second object."""
    check_size(len(data))
    digest = hashlib.sha256(data).hexdigest()
    if enabled_s3():
        from app.aws.storage import client

        client().put_object(
            Bucket=aws_settings.s3_bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            # A browser must render or download this, never run it.
            ContentDisposition="inline",
            ServerSideEncryption="AES256",
        )
    else:
        path = local_root() / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return StoredBlob(key=key, byte_size=len(data), sha256=digest)


def put_stream(key: str, stream: BinaryIO, content_type: str) -> StoredBlob:
    """Store from a file-like object, refusing anything over ``MAX_BYTES``
    without holding the whole of an oversized upload in memory."""
    digest = hashlib.sha256()
    total = 0
    chunks: list[bytes] = []
    while True:
        chunk = stream.read(256 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_BYTES:
            raise BlobError(f"That file is larger than {MAX_BYTES // (1024 * 1024)} MB")
        digest.update(chunk)
        chunks.append(chunk)
    if total == 0:
        raise BlobError("That file is empty")
    return put(key, b"".join(chunks), content_type)


# --- reading -------------------------------------------------------------------


def read(key: str) -> bytes:
    if enabled_s3():
        from app.aws.storage import client

        try:
            obj = client().get_object(Bucket=aws_settings.s3_bucket, Key=key)
        except Exception as exc:  # noqa: BLE001 — a missing object is a 404, not a 500
            raise BlobError("That file is no longer available") from exc
        return obj["Body"].read()
    path = local_root() / key
    if not path.is_file():
        raise BlobError("That file is no longer available")
    return path.read_bytes()


def download_url(key: str, filename: str | None = None) -> str | None:
    """A short-lived URL a client can fetch the bytes from directly, or None
    when there is no object store to presign against (the laptop path, where
    the API streams instead)."""
    if not enabled_s3():
        return None
    from app.aws.storage import client

    params: dict[str, str] = {"Bucket": aws_settings.s3_bucket, "Key": key}
    if filename:
        # Quotes and newlines out: this lands in a response header.
        safe = "".join(c for c in filename if c.isalnum() or c in " ._-")[:80]
        params["ResponseContentDisposition"] = f'inline; filename="{safe}"'
    return client().generate_presigned_url(
        "get_object", Params=params, ExpiresIn=DOWNLOAD_TTL_S
    )


def upload_url(key: str, content_type: str) -> str | None:
    """A short-lived URL the client may PUT bytes to, bypassing the API's own
    payload ceiling. None without an object store.

    The signature pins the content type, so a client cannot promise a JPEG
    and upload something else, and it must send that exact header.
    """
    if not enabled_s3():
        return None
    from app.aws.storage import client

    return client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": aws_settings.s3_bucket,
            "Key": key,
            "ContentType": content_type,
            "ServerSideEncryption": "AES256",
        },
        ExpiresIn=UPLOAD_TTL_S,
    )


def stat(key: str) -> int | None:
    """The stored size, or None when there is no object. What a confirm step
    checks before it trusts that an upload happened."""
    if enabled_s3():
        from app.aws.storage import client

        try:
            head = client().head_object(Bucket=aws_settings.s3_bucket, Key=key)
        except Exception:  # noqa: BLE001
            return None
        return int(head.get("ContentLength") or 0)
    path = local_root() / key
    return path.stat().st_size if path.is_file() else None


# --- removing ------------------------------------------------------------------


def delete(key: str) -> bool:
    """Remove the bytes. Returns whether anything was there.

    A row can be tombstoned in the database, but a photo a patient withdrew
    has to actually stop existing, so the object goes too.
    """
    if enabled_s3():
        from app.aws.storage import client

        try:
            client().delete_object(Bucket=aws_settings.s3_bucket, Key=key)
        except Exception:  # noqa: BLE001 — already gone is the desired state
            logger.warning("Could not delete blob %s", key, exc_info=True)
            return False
        return True
    path = local_root() / key
    if not path.is_file():
        return False
    path.unlink()
    return True


def delete_patient_blobs(patient_id: str) -> int:
    """Every file for one patient, for a chart that is being removed."""
    prefix = f"{PREFIX}/{patient_id}/"
    if enabled_s3():
        from app.aws.storage import client

        removed = 0
        token: str | None = None
        while True:
            kwargs = {"Bucket": aws_settings.s3_bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            page = client().list_objects_v2(**kwargs)
            keys = [{"Key": row["Key"]} for row in page.get("Contents", [])]
            if keys:
                client().delete_objects(
                    Bucket=aws_settings.s3_bucket, Delete={"Objects": keys}
                )
                removed += len(keys)
            if not page.get("IsTruncated"):
                return removed
            token = page.get("NextContinuationToken")
    directory = local_root() / prefix
    if not directory.is_dir():
        return 0
    count = sum(1 for _ in directory.rglob("*") if _.is_file())
    shutil.rmtree(directory, ignore_errors=True)
    return count
