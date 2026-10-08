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
# The personal tier's files (app/personal). Keys under this prefix resolve to
# the personal bucket when one is configured, so a subscriber's photos and
# exports never sit beside a hospital's patient files. On a laptop it is a
# sibling directory.
PERSONAL_PREFIX = "personal"

# What a patient or a clinician may attach. Deliberately short: an image of a
# wound, a short video of a joint moving, a voice note, a document from the
# clinic. Anything executable or scriptable is refused at the door rather
# than sanitised later.
ALLOWED_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    # Video comes off a phone as MP4 or QuickTime; the app shrinks it before
    # upload (AttachmentPrep), so a clip is tens of megabytes, not hundreds.
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    # Audio: the app's voice notes (AAC in an MP4 container), and the files
    # a person is likely to already have.
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
}
# The spellings a client or a provider may use for a type we store under one
# name. Normalised before anything else looks at them.
TYPE_ALIASES: dict[str, str] = {
    "image/jpg": "image/jpeg",
    "audio/x-m4a": "audio/mp4",
    "audio/m4a": "audio/mp4",
    "audio/aac": "audio/mp4",
    "audio/mp3": "audio/mpeg",
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/vnd.wave": "audio/wav",
    "video/x-m4v": "video/mp4",
}
MAX_BYTES = 12 * 1024 * 1024  # 12 MB: a modern phone photo with room to spare
# A clip or a recording is bigger than a picture by nature. The app recodes
# video to 540p before upload, so a minute is well under this.
MAX_MEDIA_BYTES = 48 * 1024 * 1024


def kind_of(content_type: str) -> str:
    """How a client should draw it: image | video | audio | file."""
    for prefix in ("image", "video", "audio"):
        if content_type.startswith(f"{prefix}/"):
            return prefix
    return "file"


def max_bytes_for(content_type: str | None) -> int:
    """The size cap for a type: pictures and documents are small by nature,
    video and audio are not."""
    return MAX_MEDIA_BYTES if content_type and kind_of(content_type) in ("video", "audio") \
        else MAX_BYTES
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


def bucket_for(key: str) -> str:
    """Which bucket a key lives in: the personal bucket for personal keys
    when the deployment has one, else the main bucket."""
    if key.startswith(f"{PERSONAL_PREFIX}/") and aws_settings.personal_s3_bucket:
        return aws_settings.personal_s3_bucket
    return aws_settings.s3_bucket


def prefix_for(personal: bool) -> str:
    return PERSONAL_PREFIX if personal else PREFIX


def local_root() -> Path:
    """Where the directory backend keeps its files."""
    return Path(os.environ.get("ATTACHMENT_DIR") or (BACKEND_DIR / "data" / "attachments"))


def check_type(content_type: str | None) -> str:
    """The stored content type, or a refusal.

    The client's claim is never trusted as-is: it decides the extension and,
    on download, the ``Content-Type`` header a browser will act on.
    """
    normalized = (content_type or "").split(";")[0].strip().lower()
    normalized = TYPE_ALIASES.get(normalized, normalized)
    if normalized not in ALLOWED_TYPES:
        allowed = ", ".join(sorted(ALLOWED_TYPES))
        raise BlobError(f"{content_type or 'that file type'} is not one we accept ({allowed})")
    return normalized


# The first bytes of each type we accept. A declared content type decides
# the extension and the header a browser acts on, so it has to be checked
# against what actually arrived: the bytes never pass through the API on the
# presigned path, and "image/jpeg" is a claim until something reads it.
_MAGIC: dict[str, tuple[tuple[int, bytes], ...]] = {
    "image/jpeg": (((0, b"\xff\xd8\xff"),),),
    "image/png": (((0, b"\x89PNG\r\n\x1a\n"),),),
    # ISO-BMFF: a box length, then "ftyp", then a brand. The brand decides
    # whether it is a picture, a clip or a recording (``_bmff_kind``).
    "image/heic": (((4, b"ftyp"),),),
    "image/heif": (((4, b"ftyp"),),),
    "image/webp": (((0, b"RIFF"), (8, b"WEBP")),),
    "application/pdf": (((0, b"%PDF-"),),),
    "video/mp4": (((4, b"ftyp"),),),
    # A QuickTime file nearly always opens with ftyp too; the old atom-first
    # layouts are accepted because a camera roll still holds some.
    "video/quicktime": (((4, b"ftyp"),), ((4, b"moov"),), ((4, b"mdat"),), ((4, b"wide"),),
                        ((4, b"free"),)),
    "audio/mp4": (((4, b"ftyp"),),),
    # MP3: an ID3 tag, or straight into a frame sync.
    "audio/mpeg": (((0, b"ID3"),), ((0, b"\xff\xfb"),), ((0, b"\xff\xf3"),), ((0, b"\xff\xf2"),)),
    "audio/wav": (((0, b"RIFF"), (8, b"WAVE")),),
}

# ISO-BMFF major brands, by what they carry. Everything in this family
# starts with the same four bytes, so the brand is the only thing that tells
# a HEIC photograph from an MP4 clip from an M4A recording.
_BMFF_BRANDS: dict[str, str] = {
    "heic": "image", "heix": "image", "hevc": "image", "hevx": "image", "mif1": "image",
    "msf1": "image", "heim": "image", "heis": "image", "avif": "image",
    "qt  ": "video", "isom": "video", "iso2": "video", "iso4": "video", "iso5": "video",
    "iso6": "video", "mp41": "video", "mp42": "video", "avc1": "video", "M4V ": "video",
    "M4VP": "video", "mp71": "video", "dash": "video", "3gp4": "video", "3gp5": "video",
    "M4A ": "audio", "M4B ": "audio", "M4P ": "audio",
}
# Brands that legitimately hold an audio-only file too (what ffmpeg and
# some recorders write for an .m4a).
_BMFF_AUDIO_OK = {"isom", "iso2", "mp42", "M4A ", "M4B ", "M4P "}


def _bmff_kind(head: bytes) -> str | None:
    """image | video | audio for an ISO-BMFF header, or None if the brand
    is one we do not know."""
    if head[4:8] != b"ftyp":
        return None
    try:
        major = head[8:12].decode("latin-1")
    except UnicodeDecodeError:
        return None
    return _BMFF_BRANDS.get(major)


def sniff(head: bytes, content_type: str) -> None:
    """Refuse bytes that are not what they were declared to be.

    Only the front of the file is needed, which is what makes this cheap
    enough to do on a range read rather than a download.
    """
    patterns = _MAGIC.get(content_type)
    if not patterns:
        raise BlobError(f"{content_type} is not one we accept")
    for alternative in patterns:
        if all(head[offset:offset + len(marker)] == marker for offset, marker in alternative):
            if head[4:8] == b"ftyp":
                # One container, three kinds of content: the declared kind
                # has to agree with the brand, or a clip could be served
                # under an image header and the other way round.
                declared = kind_of(content_type)
                actual = _bmff_kind(head)
                major = head[8:12].decode("latin-1", "replace")
                if actual == declared or (declared == "audio" and major in _BMFF_AUDIO_OK) \
                        or (declared == "video" and actual == "audio"):
                    return
                break
            return
    raise BlobError(
        f"That file does not look like {content_type}. Try exporting it again, "
        "or send it as a JPEG, MP4, M4A or PDF."
    )


def detect_type(head: bytes, declared: str | None = None) -> str | None:
    """The stored type for bytes whose declared type is missing or wrong, or
    None. ``declared`` is tried first; after that, every type we accept,
    with the brand check settling the ISO-BMFF family."""
    candidates: list[str] = []
    if declared:
        normalized = TYPE_ALIASES.get(declared, declared)
        if normalized in ALLOWED_TYPES:
            candidates.append(normalized)
    if head[4:8] == b"ftyp":
        kind = _bmff_kind(head)
        major = head[8:12].decode("latin-1", "replace")
        preferred = "video/quicktime" if major == "qt  " else \
            {"image": "image/heic", "video": "video/mp4", "audio": "audio/mp4"}.get(kind or "")
        if preferred:
            candidates.append(preferred)
    candidates.extend(t for t in ALLOWED_TYPES if t not in candidates)
    for candidate in candidates:
        try:
            sniff(head, candidate)
            return candidate
        except BlobError:
            continue
    return None


def head_bytes(key: str, count: int = 1024) -> bytes:
    """The first bytes of a stored object, without fetching the whole thing."""
    if enabled_s3():
        from app.aws.storage import client

        try:
            obj = client().get_object(
                Bucket=bucket_for(key), Key=key, Range=f"bytes=0-{count - 1}"
            )
        except Exception as exc:  # noqa: BLE001
            raise BlobError("That file is no longer available") from exc
        return obj["Body"].read()
    path = local_root() / key
    if not path.is_file():
        raise BlobError("That file is no longer available")
    with path.open("rb") as fh:
        return fh.read(count)


def check_size(byte_size: int, content_type: str | None = None) -> int:
    if byte_size <= 0:
        raise BlobError("That file is empty")
    cap = max_bytes_for(content_type)
    if byte_size > cap:
        raise BlobError(f"That file is larger than {cap // (1024 * 1024)} MB")
    return byte_size


def new_key(patient_id: str, content_type: str, personal: bool = False) -> str:
    """An opaque key. The patient id is a path segment for operability — a
    per-patient purge is one prefix — and the rest is random, so a key is
    never guessable from anything a reader knows. ``personal`` puts it under
    the personal tier's prefix (and so its bucket)."""
    return f"{prefix_for(personal)}/{patient_id}/{uuid.uuid4().hex}{ALLOWED_TYPES[content_type]}"


def owned_by(key: str, patient_id: str) -> bool:
    """Whether a key was minted for this patient, under either prefix."""
    return key.startswith(f"{PREFIX}/{patient_id}/") or \
        key.startswith(f"{PERSONAL_PREFIX}/{patient_id}/")


# --- writing -------------------------------------------------------------------


def put(key: str, data: bytes, content_type: str) -> StoredBlob:
    """Store bytes under ``key``. Overwrites, so a retry of the same upload
    is idempotent rather than a second object."""
    check_size(len(data), content_type)
    digest = hashlib.sha256(data).hexdigest()
    if enabled_s3():
        from app.aws.storage import client

        client().put_object(
            Bucket=bucket_for(key),
            Key=key,
            Body=data,
            ContentType=content_type,
            # A browser must render or download this, never run it.
            ContentDisposition="inline",
        )
    else:
        path = local_root() / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return StoredBlob(key=key, byte_size=len(data), sha256=digest)


def put_json(key: str, data: bytes) -> StoredBlob:
    """A data export (app/personal/api.py): JSON, served as a download, not
    subject to the attachment type list or size cap."""
    digest = hashlib.sha256(data).hexdigest()
    if enabled_s3():
        from app.aws.storage import client

        client().put_object(
            Bucket=bucket_for(key), Key=key, Body=data, ContentType="application/json",
            ContentDisposition="attachment",
        )
    else:
        path = local_root() / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return StoredBlob(key=key, byte_size=len(data), sha256=digest)


def put_stream(key: str, stream: BinaryIO, content_type: str) -> StoredBlob:
    """Store from a file-like object, refusing anything over the type's cap
    without holding the whole of an oversized upload in memory."""
    digest = hashlib.sha256()
    total = 0
    chunks: list[bytes] = []
    cap = max_bytes_for(content_type)
    while True:
        chunk = stream.read(256 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > cap:
            raise BlobError(f"That file is larger than {cap // (1024 * 1024)} MB")
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
            obj = client().get_object(Bucket=bucket_for(key), Key=key)
        except Exception as exc:  # noqa: BLE001 — a missing object is a 404, not a 500
            raise BlobError("That file is no longer available") from exc
        return obj["Body"].read()
    path = local_root() / key
    if not path.is_file():
        raise BlobError("That file is no longer available")
    return path.read_bytes()


def download_url(key: str, content_type: str, filename: str | None = None) -> str | None:
    """A short-lived URL a client can fetch the bytes from directly, or None
    when there is no object store to presign against (the laptop path, where
    the API streams instead)."""
    if not enabled_s3():
        return None
    from app.aws.storage import client

    # The type the server validated, never whatever is stored on the object:
    # a file that reached S3 with a scriptable type must not come back as
    # one. Pictures, clips and recordings are shown inline; anything else
    # is a download.
    served_type = content_type if content_type in ALLOWED_TYPES or content_type == "application/json" \
        else "application/octet-stream"
    disposition = "inline" if kind_of(served_type) in ("image", "video", "audio") else "attachment"
    if filename:
        # Quotes, newlines and paths out: this lands in a response header.
        safe = "".join(c for c in filename if c.isalnum() or c in " ._-")[:80]
        disposition = f'{disposition}; filename="{safe}"'
    params: dict[str, str] = {
        "Bucket": bucket_for(key),
        "Key": key,
        "ResponseContentType": served_type,
        "ResponseContentDisposition": disposition,
        # A URL that stops working in five minutes must not be sitting in a
        # shared cache after it does.
        "ResponseCacheControl": "no-store",
    }
    return client().generate_presigned_url(
        "get_object", Params=params, ExpiresIn=DOWNLOAD_TTL_S
    )


@dataclass(frozen=True)
class UploadTicket:
    """Everything a client needs to send the bytes itself, and nothing more."""

    url: str
    fields: dict[str, str]
    max_bytes: int
    expires_in: int


def upload_ticket(key: str, content_type: str) -> UploadTicket | None:
    """A short-lived form the client posts the bytes to, bypassing the API's
    own payload ceiling. None without an object store, where the API takes
    the bytes itself.

    A presigned POST rather than a presigned PUT, because only the POST
    policy can bound the body: a signed PUT pins the key and the type but
    accepts any length up to S3's own five-gigabyte limit, so the size cap
    would have been advice rather than a rule. The policy states the cap,
    S3 enforces it, and an oversized body is refused before it lands.

    Server-side encryption is deliberately not signed: the bucket encrypts
    by default, and signing it would make every client echo an exact
    ``x-amz-server-side-encryption`` header or get SignatureDoesNotMatch.
    """
    if not enabled_s3():
        return None
    from app.aws.storage import client

    cap = max_bytes_for(content_type)
    signed = client().generate_presigned_post(
        Bucket=bucket_for(key),
        Key=key,
        Fields={"Content-Type": content_type},
        Conditions=[
            {"Content-Type": content_type},
            ["content-length-range", 1, cap],
        ],
        ExpiresIn=UPLOAD_TTL_S,
    )
    return UploadTicket(
        url=signed["url"],
        fields={str(k): str(v) for k, v in signed["fields"].items()},
        max_bytes=cap,
        expires_in=UPLOAD_TTL_S,
    )


def stat(key: str) -> int | None:
    """The stored size, or None when there is no object. What a confirm step
    checks before it trusts that an upload happened."""
    if enabled_s3():
        from app.aws.storage import client

        try:
            head = client().head_object(Bucket=bucket_for(key), Key=key)
        except Exception:  # noqa: BLE001
            return None
        return int(head.get("ContentLength") or 0)
    path = local_root() / key
    return path.stat().st_size if path.is_file() else None


# --- copying someone else's URL ------------------------------------------------

# A provider hands us an inbound picture as a link on its own CDN: no
# credential, public to anyone who has it, and alive for as long as they keep
# it. Copying it is therefore urgent, and the copy runs inside a request that
# holds the database write lock, so it is bounded hard rather than generously.
FETCH_CONNECT_S = 2.0
FETCH_READ_S = 5.0
# Hosts an inbound media link may point at. A URL from a webhook body is
# attacker-controlled input until something checks it: without this, a forged
# delivery could make the server fetch an address of the caller's choosing.
FETCH_HOSTS = ("sendblue.co", "sendblue.com", "storage.googleapis.com",
               "amazonaws.com", "twilio.com")


def fetchable(url: str) -> bool:
    """Whether this is a link we are willing to dereference at all."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in FETCH_HOSTS)


def fetch_remote(url: str) -> tuple[bytes, str]:
    """Copy a remote file, or raise BlobError. Returns (bytes, content type).

    One attempt, no redirects, no retry: a request holding the write lock
    cannot afford a second chance, and a redirect is how an allowlisted host
    would be used to reach one that is not.
    """
    import httpx

    if not fetchable(url):
        raise BlobError("That file link is not one we will follow")
    try:
        with httpx.Client(
            timeout=httpx.Timeout(FETCH_READ_S, connect=FETCH_CONNECT_S),
            follow_redirects=False,
        ) as client:
            response = client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise BlobError(f"Could not fetch that file ({exc.__class__.__name__})") from exc
    data = response.content
    if len(data) > MAX_MEDIA_BYTES:
        raise BlobError(f"That file is larger than {MAX_MEDIA_BYTES // (1024 * 1024)} MB")
    declared = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    # The provider's own header is a claim like any other; the bytes decide.
    found = detect_type(data[:1024], declared)
    if found is None:
        raise BlobError("That file is not an image, video, recording or document we can accept")
    if len(data) > max_bytes_for(found):
        raise BlobError(f"That file is larger than {max_bytes_for(found) // (1024 * 1024)} MB")
    return data, found


# --- removing ------------------------------------------------------------------


def delete(key: str) -> bool:
    """Remove the bytes. Returns whether anything was there.

    A row can be tombstoned in the database, but a photo a patient withdrew
    has to actually stop existing, so the object goes too.
    """
    if enabled_s3():
        from app.aws.storage import client

        try:
            client().delete_object(Bucket=bucket_for(key), Key=key)
        except Exception:  # noqa: BLE001 — already gone is the desired state
            logger.warning("Could not delete blob %s", key, exc_info=True)
            return False
        return True
    path = local_root() / key
    if not path.is_file():
        return False
    path.unlink()
    return True


def delete_keys(keys: list[str]) -> int:
    """Delete exactly these objects. What a chart's removal uses: a key keeps
    the patient id it was minted under, and a record merge moves the row to
    another chart without moving the object, so the rows are the truth about
    what belongs to whom."""
    removed = 0
    for key in keys:
        if delete(key):
            removed += 1
    return removed


def delete_patient_blobs(patient_id: str) -> int:
    """Everything still sitting under one patient's prefixes. A sweep for
    orphans — bytes uploaded against a ticket whose row never confirmed —
    not the authoritative delete, which is ``delete_keys``."""
    return sum(_delete_prefix(f"{p}/{patient_id}/") for p in (PREFIX, PERSONAL_PREFIX))


def _delete_prefix(prefix: str) -> int:
    if enabled_s3():
        from app.aws.storage import client

        bucket = bucket_for(prefix)
        removed = 0
        token: str | None = None
        while True:
            kwargs = {"Bucket": bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            page = client().list_objects_v2(**kwargs)
            keys = [{"Key": row["Key"]} for row in page.get("Contents", [])]
            if keys:
                client().delete_objects(Bucket=bucket, Delete={"Objects": keys})
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
