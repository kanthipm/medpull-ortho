#!/usr/bin/env bash
#
# Tear the Recovery Copilot stack down. The data bucket is created with
# DeletionPolicy: Retain, so the demo database survives unless you pass
# --delete-data, and the SSM parameters are kept unless you pass
# --delete-secrets: deploy.sh reuses both, so removing them turns every
# redeploy into a re-entry of the Groq key.
#
#   ./infra/destroy.sh                   # delete the stack, keep data + secrets
#   ./infra/destroy.sh --delete-data     # also delete the database bucket
#   ./infra/destroy.sh --delete-secrets  # also delete the SSM parameters
#
set -euo pipefail

STACK_NAME="${STACK_NAME:-recovery-copilot}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
GROQ_PARAM="${GROQ_PARAM:-/recovery-copilot/groq-api-key}"
ORIGIN_SECRET_PARAM="${ORIGIN_SECRET_PARAM:-/recovery-copilot/origin-verify-secret}"

DELETE_DATA=false
DELETE_SECRETS=false
for arg in "$@"; do
  case "$arg" in
    --delete-data) DELETE_DATA=true ;;
    --delete-secrets) DELETE_SECRETS=true ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 1 ;;
  esac
done

log()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
aws_() { aws --region "$REGION" "$@"; }

ACCOUNT_ID="$(aws_ sts get-caller-identity --query Account --output text)"
ARTIFACT_BUCKET="${ARTIFACT_BUCKET:-${STACK_NAME}-artifacts-${ACCOUNT_ID}-${REGION}}"

DATA_BUCKET="$(aws_ cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='DataBucketName'].OutputValue" \
  --output text 2>/dev/null || true)"

log "About to delete stack '$STACK_NAME' in $REGION"
[ -n "$DATA_BUCKET" ] && info "data bucket: $DATA_BUCKET $($DELETE_DATA && echo '(WILL BE DELETED)' || echo '(retained)')"
info "artifact bucket: $ARTIFACT_BUCKET (will be emptied and deleted)"
info "SSM parameters: $($DELETE_SECRETS && echo 'WILL BE DELETED' || echo 'retained')"
printf '    Type the stack name to confirm: '
read -r CONFIRM
[ "$CONFIRM" = "$STACK_NAME" ] || { echo "aborted"; exit 1; }

# CloudFormation cannot delete a non-empty bucket; the data bucket is retained
# by policy so only the artifact bucket needs emptying up front.
log "Emptying the artifact bucket"
aws_ s3 rm "s3://$ARTIFACT_BUCKET" --recursive --only-show-errors 2>/dev/null || true

log "Deleting the stack (CloudFront takes several minutes to disable)"
aws_ cloudformation delete-stack --stack-name "$STACK_NAME"
aws_ cloudformation wait stack-delete-complete --stack-name "$STACK_NAME"

log "Cleaning up"
aws_ s3api delete-bucket --bucket "$ARTIFACT_BUCKET" 2>/dev/null || true
if $DELETE_SECRETS; then
  aws_ ssm delete-parameter --name "$ORIGIN_SECRET_PARAM" 2>/dev/null || true
  aws_ ssm delete-parameter --name "$GROQ_PARAM" 2>/dev/null || true
  info "removed the SSM parameters"
else
  # Standard parameters cost nothing to keep, and deploy.sh reuses both: the
  # origin secret has to survive anyway (CloudFront and the function compare
  # against the same value), and deleting the Groq key means typing it in again.
  info "kept the SSM parameters — rerun with --delete-secrets to remove them"
fi

if $DELETE_DATA && [ -n "$DATA_BUCKET" ]; then
  log "Deleting the data bucket"
  # Versioning is on, so every version and delete marker has to go explicitly.
  aws_ s3api delete-objects --bucket "$DATA_BUCKET" --delete "$(aws_ s3api list-object-versions \
    --bucket "$DATA_BUCKET" --output json \
    --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}')" >/dev/null 2>&1 || true
  aws_ s3api delete-objects --bucket "$DATA_BUCKET" --delete "$(aws_ s3api list-object-versions \
    --bucket "$DATA_BUCKET" --output json \
    --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}')" >/dev/null 2>&1 || true
  aws_ s3api delete-bucket --bucket "$DATA_BUCKET" 2>/dev/null || true
  info "deleted $DATA_BUCKET"
elif [ -n "$DATA_BUCKET" ]; then
  info "kept $DATA_BUCKET — delete it by hand, or rerun with --delete-data"
fi

log "Done — nothing left billing"
