#!/usr/bin/env bash
#
# Build the Lambda deployment zip for the Recovery Copilot API.
#
# The dependency list is derived from backend/uv.lock rather than maintained by
# hand, so the function can never drift from what `make test` ran against.
# Three groups are then dropped:
#
#   * boto3/botocore/s3transfer/jmespath — the python3.12 runtime ships them.
#     Bundling botocore's service data would add ~80 MB for nothing.
#   * uvicorn and everything only it pulls in (uvloop, httptools, watchfiles,
#     websockets, pyyaml, click) — Mangum replaces the ASGI server on Lambda.
#     h11 and python-dotenv look like uvicorn deps but httpcore and
#     pydantic-settings need them, so they stay.
#   * scipy — declared in pyproject but imported nowhere in app/ (verified by
#     the grep guard below), and it is the single largest wheel in the tree.
#
# Wheels are fetched for aarch64: Graviton bills ~20% fewer GB-seconds, which
# stretches the always-free 400,000 GB-s/month further.
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$(cd "$HERE/../backend" && pwd)"
BUILD="$HERE/.build"
PKG="$BUILD/pkg"
ZIP="${LAMBDA_ZIP:-$BUILD/recovery-copilot-lambda.zip}"

ARCH="${LAMBDA_ARCH:-aarch64}"
PY_VERSION="3.12"
# The python3.12 runtime images are Amazon Linux 2023 (glibc 2.34), so 2.28 is
# the right floor: manylinux2014 would be too strict — greenlet, for one,
# publishes no 2.17 aarch64 wheel — and older-tagged wheels still resolve here.
GLIBC_TAG="${LAMBDA_GLIBC_TAG:-manylinux_2_28}"

EXCLUDE='^(boto3|botocore|s3transfer|jmespath|uvicorn|uvloop|httptools|watchfiles|websockets|pyyaml|click|colorama|scipy)=='

command -v uv >/dev/null || { echo "error: uv is required (https://docs.astral.sh/uv/)" >&2; exit 1; }

echo "==> Verifying the excluded packages really are unused"
if grep -rqE '^\s*(import|from)\s+scipy' "$BACKEND/app"; then
  echo "error: app/ imports scipy but the build excludes it — update EXCLUDE." >&2
  exit 1
fi

echo "==> Resolving dependencies from uv.lock"
rm -rf "$BUILD"
mkdir -p "$PKG"
REQ="$BUILD/requirements.txt"
(cd "$BACKEND" && uv export --frozen --no-dev --group aws --no-emit-project --no-hashes) \
  | grep -vE '^\s*#' \
  | grep -E '==' \
  | grep -vE "$EXCLUDE" \
  > "$REQ"
echo "    $(wc -l < "$REQ") packages"

echo "==> Downloading ${ARCH} ${GLIBC_TAG} wheels for python${PY_VERSION}"
(cd "$BACKEND" && uv pip install \
  --target "$PKG" \
  --python-platform "${ARCH}-${GLIBC_TAG}" \
  --python-version "$PY_VERSION" \
  --only-binary=:all: \
  --no-compile-bytecode \
  --quiet \
  -r "$REQ")

echo "==> Adding application code"
# Only app/ ships. Tests, the local .env and backend/data/*.db stay out of the
# artifact — the database comes from S3 at runtime, never from the zip.
# cp rather than rsync: CloudShell and the slimmer CI images have cp. The
# __pycache__ this drags along is removed by the strip pass below.
cp -R "$BACKEND/app" "$PKG/"

echo "==> Stripping build residue"
find "$PKG" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$PKG" -type d -name 'tests' -path '*/numpy/*' -prune -exec rm -rf {} +
find "$PKG" -type d -name 'tests' -path '*/pandas/*' -prune -exec rm -rf {} +
find "$PKG" -type f -name '*.pyc' -delete
find "$PKG" -type f -name '*.pyx' -delete
find "$PKG" -type f -name '*.c' -delete
find "$PKG" -type d -name '*.dist-info' -exec rm -f {}/RECORD \;
# Debug symbols in the numpy/pandas shared objects are ~30% of their size and
# nothing on Lambda reads them.
find "$PKG" -name '*.so' -exec strip --strip-unneeded {} + 2>/dev/null || true

echo "==> Zipping"
rm -f "$ZIP"
(cd "$PKG" && zip -qr9 "$ZIP" .)

UNZIPPED=$(du -sm "$PKG" | cut -f1)
ZIPPED=$(du -m "$ZIP" | cut -f1)
echo "==> ${ZIP}"
echo "    ${ZIPPED} MB zipped / ${UNZIPPED} MB unzipped (Lambda limits: 50 MB direct, 250 MB unzipped)"

if [ "$UNZIPPED" -gt 250 ]; then
  echo "error: unzipped size exceeds the 250 MB Lambda limit" >&2
  exit 1
fi
