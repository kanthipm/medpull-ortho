#!/usr/bin/env bash
#
# Deploy the Recovery Copilot to AWS. Idempotent — run it again to ship a change.
#
#   ./infra/deploy.sh                 # build, deploy, seed on first run
#   ./infra/deploy.sh --reseed        # rebuild the demo database too
#   ./infra/deploy.sh --backend-only  # skip the frontend build/upload
#
# Requires: aws CLI (authenticated), uv, node 20+, zip.
# AWS CloudShell has all four, which is the easiest way to run this without
# creating long-lived access keys.
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

STACK_NAME="${STACK_NAME:-recovery-copilot}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
GROQ_PARAM="${GROQ_PARAM:-/recovery-copilot/groq-api-key}"
ORIGIN_SECRET_PARAM="${ORIGIN_SECRET_PARAM:-/recovery-copilot/origin-verify-secret}"
GROQ_MODEL="${GROQ_MODEL:-llama-3.3-70b-versatile}"
# Junction (wearable aggregator). Both secrets are optional: absent, the
# connector stays idle and the console says "Needs setup". The non-secret
# settings come from the environment, else recovery-copilot/.env, else the
# sandbox defaults.
dotenv_value() {  # dotenv_value VAR -> its value in $ROOT/.env, or nothing; never fails
  [ -f "$ROOT/.env" ] || return 0
  # \042 = double quote, \047 = single quote — spelled in octal to keep the
  # nesting of quotes readable. `|| true` because an absent key is not an error.
  grep -E "^$1=" "$ROOT/.env" | tail -1 | cut -d= -f2- | tr -d '\042\047 ' || true
}
JUNCTION_PARAM="${JUNCTION_PARAM:-/recovery-copilot/junction-api-key}"
JUNCTION_WEBHOOK_PARAM="${JUNCTION_WEBHOOK_PARAM:-/recovery-copilot/junction-webhook-secret}"
JUNCTION_ENVIRONMENT="${JUNCTION_ENVIRONMENT:-$(dotenv_value JUNCTION_ENVIRONMENT)}"
JUNCTION_ENVIRONMENT="${JUNCTION_ENVIRONMENT:-sandbox}"
JUNCTION_REGION="${JUNCTION_REGION:-$(dotenv_value JUNCTION_REGION)}"
JUNCTION_REGION="${JUNCTION_REGION:-us}"
JUNCTION_LINK_REDIRECT_URL="${JUNCTION_LINK_REDIRECT_URL:-$(dotenv_value JUNCTION_LINK_REDIRECT_URL)}"
BUDGET_EMAIL="${BUDGET_EMAIL:-}"

RESEED=false
BACKEND_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --reseed) RESEED=true ;;
    --backend-only) BACKEND_ONLY=true ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 1 ;;
  esac
done

log()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\033[31merror: %s\033[0m\n' "$*" >&2; exit 1; }

aws_() { aws --region "$REGION" "$@"; }

# --------------------------------------------------------------------------
log "Preflight"
# --------------------------------------------------------------------------
for tool in aws uv zip; do
  command -v "$tool" >/dev/null || die "$tool is required but not installed"
done
$BACKEND_ONLY || command -v npm >/dev/null || die "npm is required (or pass --backend-only)"

ACCOUNT_ID="$(aws_ sts get-caller-identity --query Account --output text 2>/dev/null)" \
  || die "no valid AWS credentials. In CloudShell they are automatic; locally run 'aws configure'."
CALLER="$(aws_ sts get-caller-identity --query Arn --output text)"
info "account $ACCOUNT_ID in $REGION"
info "as      $CALLER"
case "$CALLER" in
  *":root") info "note: you are the account root user. AWS recommends an IAM"
            info "      user or role with AdministratorAccess for day-to-day work." ;;
esac

# Lambda refuses to reserve concurrency if it would leave the account with
# fewer than 100 unreserved executions. New accounts often start at a limit of
# 10, where any reservation is rejected — detect that and leave it unreserved
# rather than failing the stack halfway through.
ACCOUNT_LIMIT="$(aws_ lambda get-account-settings \
  --query 'AccountLimit.ConcurrentExecutions' --output text 2>/dev/null || echo 1000)"
case "$ACCOUNT_LIMIT" in ''|*[!0-9]*) ACCOUNT_LIMIT=1000 ;; esac
RESERVED="${API_RESERVED_CONCURRENCY:-5}"
if [ "$ACCOUNT_LIMIT" -lt $((RESERVED + 100)) ]; then
  info "account concurrency limit is $ACCOUNT_LIMIT — too low to reserve; leaving unreserved"
  RESERVED=-1
else
  info "capping the API at $RESERVED concurrent executions (limit $ACCOUNT_LIMIT)"
fi

ARTIFACT_BUCKET="${ARTIFACT_BUCKET:-${STACK_NAME}-artifacts-${ACCOUNT_ID}-${REGION}}"

# --------------------------------------------------------------------------
log "Artifact bucket"
# --------------------------------------------------------------------------
if aws_ s3api head-bucket --bucket "$ARTIFACT_BUCKET" 2>/dev/null; then
  info "$ARTIFACT_BUCKET (exists)"
else
  info "creating $ARTIFACT_BUCKET"
  if [ "$REGION" = "us-east-1" ]; then
    aws_ s3api create-bucket --bucket "$ARTIFACT_BUCKET" >/dev/null
  else
    aws_ s3api create-bucket --bucket "$ARTIFACT_BUCKET" \
      --create-bucket-configuration "LocationConstraint=$REGION" >/dev/null
  fi
  aws_ s3api put-public-access-block --bucket "$ARTIFACT_BUCKET" \
    --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
  # Old zips are near-pure cost — but a stack rollback re-points the function
  # at the previous zip, so keep 90 days of them (a few cents) rather than 30
  # and risk UPDATE_ROLLBACK_FAILED on a stack that hasn't shipped in a month.
  aws_ s3api put-bucket-lifecycle-configuration --bucket "$ARTIFACT_BUCKET" \
    --lifecycle-configuration '{"Rules":[{"ID":"expire-old-artifacts","Status":"Enabled","Prefix":"lambda/","Expiration":{"Days":90}}]}'
fi

# --------------------------------------------------------------------------
log "Secrets"
# --------------------------------------------------------------------------
# The origin-verify secret must survive redeploys — CloudFront injects it and
# the function compares against it, so regenerating one without the other would
# 403 every request. Parameter Store is the source of truth.
if ! ORIGIN_SECRET="$(aws_ ssm get-parameter --name "$ORIGIN_SECRET_PARAM" \
      --with-decryption --query 'Parameter.Value' --output text 2>/dev/null)"; then
  info "generating a new origin-verify secret"
  ORIGIN_SECRET="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  aws_ ssm put-parameter --name "$ORIGIN_SECRET_PARAM" --type SecureString \
    --value "$ORIGIN_SECRET" --description "CloudFront -> Lambda shared secret" >/dev/null
else
  info "reusing the stored origin-verify secret"
fi

# Groq key: an existing SSM value wins, then $GROQ_API_KEY, then the local .env,
# then a prompt. Never echoed.
if aws_ ssm get-parameter --name "$GROQ_PARAM" >/dev/null 2>&1; then
  info "Groq key already in SSM at $GROQ_PARAM (delete the parameter to change it)"
else
  KEY="${GROQ_API_KEY:-}"
  if [ -z "$KEY" ] && [ -f "$ROOT/.env" ]; then
    # \042 = double quote, \047 = single quote — spelled in octal to keep the
    # nesting of quotes in this line readable.
    KEY="$(grep -E '^GROQ_API_KEY=' "$ROOT/.env" | tail -1 | cut -d= -f2- | tr -d '\042\047 ')"
  fi
  if [ -z "$KEY" ]; then
    printf '    Groq API key (console.groq.com, free tier; blank = deterministic fallback only): '
    read -rs KEY; echo
  fi
  if [ -n "$KEY" ]; then
    aws_ ssm put-parameter --name "$GROQ_PARAM" --type SecureString \
      --value "$KEY" --description "Groq API key for Recovery Copilot" >/dev/null
    info "stored the Groq key in SSM ($GROQ_PARAM)"
  else
    info "no Groq key — the app will render every narrative with the deterministic engine"
  fi
  unset KEY
fi

# Junction secrets: an existing SSM value wins, then the environment, then the
# local .env. Never prompted for — both are optional and a deploy without them
# is a deploy with the connector idle, which is a valid state.
store_optional_secret() {
  local param="$1" var="$2" label="$3" value
  if aws_ ssm get-parameter --name "$param" >/dev/null 2>&1; then
    info "$label already in SSM at $param (delete the parameter to change it)"
    return
  fi
  value="${!var:-}"
  [ -n "$value" ] || value="$(dotenv_value "$var")"
  if [ -n "$value" ]; then
    aws_ ssm put-parameter --name "$param" --type SecureString \
      --value "$value" --description "$label for Recovery Copilot" >/dev/null
    info "stored the $label in SSM ($param)"
  else
    info "no $label — the Junction connector stays idle until one is stored"
  fi
}
store_optional_secret "$JUNCTION_PARAM" JUNCTION_API_KEY "Junction API key"
store_optional_secret "$JUNCTION_WEBHOOK_PARAM" JUNCTION_WEBHOOK_SECRET "Junction webhook secret"

# --------------------------------------------------------------------------
log "Building the Lambda package"
# --------------------------------------------------------------------------
"$HERE/build-lambda.sh"
ZIP="$HERE/.build/recovery-copilot-lambda.zip"
# Content-addressed key: CloudFormation only updates the function when the S3
# key changes, so a same-named object would silently ship stale code.
ZIP_HASH="$(sha256sum "$ZIP" | cut -c1-16)"
ZIP_KEY="lambda/recovery-copilot-${ZIP_HASH}.zip"
info "uploading s3://$ARTIFACT_BUCKET/$ZIP_KEY"
aws_ s3 cp "$ZIP" "s3://$ARTIFACT_BUCKET/$ZIP_KEY" --only-show-errors

# --------------------------------------------------------------------------
log "Deploying the stack"
# --------------------------------------------------------------------------
PARAMS=(
  "LambdaCodeBucket=$ARTIFACT_BUCKET"
  "LambdaCodeKey=$ZIP_KEY"
  "OriginVerifySecret=$ORIGIN_SECRET"
  "GroqApiKeyParameter=$GROQ_PARAM"
  "GroqModel=$GROQ_MODEL"
  "JunctionApiKeyParameter=$JUNCTION_PARAM"
  "JunctionWebhookSecretParameter=$JUNCTION_WEBHOOK_PARAM"
  "JunctionEnvironment=$JUNCTION_ENVIRONMENT"
  "JunctionRegion=$JUNCTION_REGION"
  "JunctionLinkRedirectUrl=$JUNCTION_LINK_REDIRECT_URL"
  "ApiReservedConcurrency=$RESERVED"
)
[ -n "$BUDGET_EMAIL" ] && PARAMS+=("BudgetAlertEmail=$BUDGET_EMAIL")

aws_ cloudformation deploy \
  --stack-name "$STACK_NAME" \
  --template-file "$HERE/cloudformation.yaml" \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides "${PARAMS[@]}"

outputs() {
  aws_ cloudformation describe-stacks --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}
SITE_URL="$(outputs SiteUrl)"
DATA_BUCKET="$(outputs DataBucketName)"
DIST_ID="$(outputs DistributionId)"
SEED_FN="$(outputs SeedFunctionName)"
info "site   $SITE_URL"
info "bucket $DATA_BUCKET"

# --------------------------------------------------------------------------
if ! $BACKEND_ONLY; then
log "Building and uploading the frontend"
# --------------------------------------------------------------------------
  (cd "$ROOT/frontend" && npm ci --no-audit --no-fund && npm run build)
  DIST="$ROOT/frontend/dist"
  [ -f "$DIST/index.html" ] || die "frontend build produced no dist/index.html"

  aws_ s3 sync "$DIST/" "s3://$DATA_BUCKET/web/" --delete --only-show-errors \
    --cache-control "public,max-age=3600"
  # Vite content-hashes everything under assets/, so those can be immutable.
  aws_ s3 cp "$DIST/assets/" "s3://$DATA_BUCKET/web/assets/" --recursive --only-show-errors \
    --metadata-directive REPLACE --cache-control "public,max-age=31536000,immutable"
  # index.html points at hashed bundles; a cached copy would pin a stale build.
  aws_ s3 cp "$DIST/index.html" "s3://$DATA_BUCKET/web/index.html" --only-show-errors \
    --cache-control "no-cache" --content-type "text/html; charset=utf-8"
fi

# --------------------------------------------------------------------------
log "Demo database"
# --------------------------------------------------------------------------
DB_EXISTS=true
aws_ s3api head-object --bucket "$DATA_BUCKET" --key db/recovery.db >/dev/null 2>&1 || DB_EXISTS=false

if ! $DB_EXISTS || $RESEED; then
  $DB_EXISTS && info "reseeding on request" || info "no database yet — seeding"
  info "this warms every insight through Groq and takes a few minutes"
  # Async invoke + polling, not a synchronous wait: holding one HTTP response
  # open for minutes can hang the CLI long past its read timeout on some
  # networks, and the seed's outcome is visible in S3 anyway — the function's
  # last act is uploading the database.
  BEFORE_MODIFIED="$(aws_ s3api head-object --bucket "$DATA_BUCKET" --key db/recovery.db \
    --query 'LastModified' --output text 2>/dev/null || true)"
  aws_ lambda invoke \
    --function-name "$SEED_FN" \
    --invocation-type Event \
    --payload '{"action":"seed","reset":true}' \
    --cli-binary-format raw-in-base64-out \
    /dev/null >/dev/null
  SEED_OK=false
  for _ in $(seq 1 60); do  # up to 15 minutes — the seed function's timeout
    sleep 15
    NOW_MODIFIED="$(aws_ s3api head-object --bucket "$DATA_BUCKET" --key db/recovery.db \
      --query 'LastModified' --output text 2>/dev/null || true)"
    if [ -n "$NOW_MODIFIED" ] && [ "$NOW_MODIFIED" != "$BEFORE_MODIFIED" ]; then
      SEED_OK=true
      break
    fi
    printf '.'
  done
  echo
  $SEED_OK && info "seeded — the database object landed in S3" \
    || die "seed did not finish in 15 minutes. Check: aws logs tail /aws/lambda/$SEED_FN"
else
  info "database already present — pass --reseed to rebuild it"
fi

# --------------------------------------------------------------------------
log "Invalidating the CDN"
# --------------------------------------------------------------------------
# One path per deploy, against a free allowance of 1,000 paths/month.
aws_ cloudfront create-invalidation --distribution-id "$DIST_ID" --paths '/*' \
  --query 'Invalidation.Id' --output text | sed 's/^/    invalidation /'

# --------------------------------------------------------------------------
log "Smoke test"
# --------------------------------------------------------------------------
sleep 5
if HEALTH="$(curl -fsS --max-time 60 "$SITE_URL/api/health" 2>/dev/null)"; then
  info "$HEALTH"
else
  info "health check did not answer yet — a new distribution takes a few"
  info "minutes to propagate. Retry: curl $SITE_URL/api/health"
fi

log "Done"
info "$SITE_URL"
