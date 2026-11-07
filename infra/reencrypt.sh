#!/usr/bin/env bash
#
# Re-encrypt a stack's existing objects under its facet keys.
#
# SSE-KMS as a bucket default applies to objects written from then on; what
# was uploaded before keeps SSE-S3 until something rewrites it. The database
# rewrites itself (every write-back is a new object, stored under the
# default) and every deploy rewrites the SPA, so this is for the files
# nothing rewrites: attachments/ in the clinic bucket, personal/ in the
# personal bucket. An object already on the right key is left alone, which
# is what makes a second run a no-op.
#
#   ./infra/reencrypt.sh                   # the real app, from .env
#   ./infra/reencrypt.sh --env .env.demo   # the demo stack
#   ./infra/reencrypt.sh --dry-run         # list what would be rewritten
#   ./infra/reencrypt.sh --prefix db/      # one prefix instead (repeatable)
#
# Versioning is on, so each rewrite is a new version and the lifecycle rules
# expire the SSE-S3 one (a day for files, a week under db/). The lock object
# is never touched: changing its ETag would tell a writer it lost the lock.
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

DRY_RUN=false
PREFIXES=()
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
want_env=false
want_prefix=false
for arg in "$@"; do
  if $want_env; then ENV_FILE="$arg"; want_env=false; continue; fi
  if $want_prefix; then PREFIXES+=("$arg"); want_prefix=false; continue; fi
  case "$arg" in
    --env) want_env=true ;;
    --env=*) ENV_FILE="${arg#--env=}" ;;
    --prefix) want_prefix=true ;;
    --prefix=*) PREFIXES+=("${arg#--prefix=}") ;;
    --dry-run) DRY_RUN=true ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 1 ;;
  esac
done
$want_env && { echo "--env needs a file" >&2; exit 1; }
$want_prefix && { echo "--prefix needs a value" >&2; exit 1; }
case "$ENV_FILE" in /*) ;; *) ENV_FILE="$PWD/$ENV_FILE" ;; esac
[ ${#PREFIXES[@]} -gt 0 ] || PREFIXES=(attachments/ personal/)

dotenv_value() {
  [ -f "$ENV_FILE" ] || return 0
  grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '\042\047 ' || true
}

STACK_NAME="${STACK_NAME:-$(dotenv_value STACK_NAME)}"
STACK_NAME="${STACK_NAME:-recovery-copilot}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"

log()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\033[31merror: %s\033[0m\n' "$*" >&2; exit 1; }
aws_() { aws --region "$REGION" "$@"; }

output() {
  aws_ cloudformation describe-stacks --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text 2>/dev/null || true
}

log "Stack $STACK_NAME in $REGION"
DATA_BUCKET="$(output DataBucketName)"
PERSONAL_BUCKET="$(output PersonalDataBucketName)"
CLINIC_KEY="$(output ClinicKeyArn)"
PERSONAL_KEY="$(output PersonalKeyArn)"
[ -n "$DATA_BUCKET" ] && [ "$DATA_BUCKET" != None ] || die "no such stack (env file $ENV_FILE)"
[ -n "$CLINIC_KEY" ] && [ "$CLINIC_KEY" != None ] \
  || die "the stack has no facet keys yet — deploy the current template first (./infra/deploy.sh --stack-only)"
info "clinic   $DATA_BUCKET  <- $CLINIC_KEY"
info "personal $PERSONAL_BUCKET  <- $PERSONAL_KEY"
$DRY_RUN && info "dry run: nothing is rewritten"

REWRITTEN=0
ALREADY=0
SKIPPED=0

# reencrypt BUCKET KEY_ARN PREFIX: every object under PREFIX onto KEY_ARN.
# One HEAD per object decides; the copy is the CLI's in-place cp, which S3
# accepts because the encryption changes. The bucket-key setting is the
# bucket's default, so the copy inherits it.
reencrypt() {
  local bucket="$1" key_arn="$2" prefix="$3" key current
  log "s3://$bucket/$prefix"
  # One key per line (tabs would split a key with a space in it), fed through
  # process substitution so the loop runs here and the counters survive it.
  while IFS= read -r key; do
    [ -n "$key" ] && [ "$key" != None ] || continue
    case "$key" in *.lock) SKIPPED=$((SKIPPED + 1)); continue ;; esac
    current="$(aws_ s3api head-object --bucket "$bucket" --key "$key" \
      --query 'SSEKMSKeyId' --output text 2>/dev/null || echo None)"
    if [ "$current" = "$key_arn" ]; then
      ALREADY=$((ALREADY + 1))
      continue
    fi
    if $DRY_RUN; then
      info "would rewrite $key (now: ${current/None/SSE-S3})"
    else
      aws_ s3 cp "s3://$bucket/$key" "s3://$bucket/$key" --only-show-errors \
        --sse aws:kms --sse-kms-key-id "$key_arn"
      info "rewrote $key"
    fi
    REWRITTEN=$((REWRITTEN + 1))
  done < <(aws_ s3api list-objects-v2 --bucket "$bucket" --prefix "$prefix" \
    --query 'Contents[].[Key]' --output text 2>/dev/null || true)
}

for prefix in "${PREFIXES[@]}"; do
  case "$prefix" in
    personal/*|personal) reencrypt "$PERSONAL_BUCKET" "$PERSONAL_KEY" "$prefix" ;;
    *) reencrypt "$DATA_BUCKET" "$CLINIC_KEY" "$prefix" ;;
  esac
done

log "Done"
if $DRY_RUN; then
  info "$REWRITTEN to rewrite, $ALREADY already on the key, $SKIPPED lock objects left alone"
  info "rerun without --dry-run to rewrite them"
else
  info "$REWRITTEN rewritten, $ALREADY already on the key, $SKIPPED lock objects left alone"
fi
info "db/recovery.db lands on the key by itself at its next write-back; web/ at the next deploy"
