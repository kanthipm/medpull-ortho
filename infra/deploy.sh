#!/usr/bin/env bash
#
# Deploy the Recovery Copilot to AWS. Idempotent — run it again to ship a change.
#
#   ./infra/deploy.sh                 # the real app: build, deploy, never seed
#   ./infra/deploy.sh --env .env.demo # the public demo stack (seeds on first run)
#   ./infra/deploy.sh --reseed        # rebuild the demo database (demo stack only)
#   ./infra/deploy.sh --backend-only  # skip the frontend builds/uploads (console and patient app)
#   ./infra/deploy.sh --stack-only    # template/parameters only: ships no code
#
# Custom domain: set SITE_DOMAIN and SITE_CERTIFICATE_ARN (environment or
# the env file) once the ACM certificate is ISSUED. See infra/README.md.
#
# Requires: aws CLI (authenticated), uv, node 20+, zip.
# AWS CloudShell has all four, which is the easiest way to run this without
# creating long-lived access keys.
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

RESEED=false
BACKEND_ONLY=false
STACK_ONLY=false
# Which env file: --env FILE, else $ENV_FILE, else the repo's .env (the real
# app). .env.demo is the public demo stack; the two differ in STACK_NAME,
# DEMO_MODE, the domain and which secrets are present.
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
want_env=false
for arg in "$@"; do
  if $want_env; then ENV_FILE="$arg"; want_env=false; continue; fi
  case "$arg" in
    --env) want_env=true ;;
    --env=*) ENV_FILE="${arg#--env=}" ;;
    --reseed) RESEED=true ;;
    --backend-only) BACKEND_ONLY=true ;;
    --stack-only) STACK_ONLY=true; BACKEND_ONLY=true ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 1 ;;
  esac
done
$want_env && { echo "--env needs a file" >&2; exit 1; }
case "$ENV_FILE" in /*) ;; *) ENV_FILE="$PWD/$ENV_FILE" ;; esac

dotenv_value() {  # dotenv_value VAR -> its value in $ENV_FILE, or nothing; never fails
  [ -f "$ENV_FILE" ] || return 0
  # \042 = double quote, \047 = single quote — spelled in octal to keep the
  # nesting of quotes readable. `|| true` because an absent key is not an error.
  grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '\042\047 ' || true
}

STACK_NAME="${STACK_NAME:-$(dotenv_value STACK_NAME)}"
STACK_NAME="${STACK_NAME:-recovery-copilot}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
# Every secret lives under the stack's own SSM prefix, so a second stack can
# never read the first one's console token or webhook secrets.
GROQ_PARAM="${GROQ_PARAM:-/$STACK_NAME/groq-api-key}"
ORIGIN_SECRET_PARAM="${ORIGIN_SECRET_PARAM:-/$STACK_NAME/origin-verify-secret}"
# The public demo or the real app. The demo shows the welcome screen and the
# roster caption, may open the unsigned mock webhook, and is the only stack
# the seed function will rebuild.
DEMO_MODE="${DEMO_MODE:-$(dotenv_value DEMO_MODE)}"
DEMO_MODE="${DEMO_MODE:-false}"
case "$DEMO_MODE" in true|false) ;; *) echo "DEMO_MODE must be true or false" >&2; exit 1 ;; esac
# The personal tier's trial and App Store paywall. Off until there is a paid
# product; on, the apps show the plan step and lapsed accounts are closed.
PERSONAL_PAYWALL="${PERSONAL_PAYWALL:-$(dotenv_value PERSONAL_PAYWALL)}"
PERSONAL_PAYWALL="${PERSONAL_PAYWALL:-false}"
case "$PERSONAL_PAYWALL" in true|false) ;; *) echo "PERSONAL_PAYWALL must be true or false" >&2; exit 1 ;; esac
ALLOW_MOCK_WEBHOOK="${ALLOW_MOCK_WEBHOOK:-$(dotenv_value ALLOW_MOCK_WEBHOOK)}"
ALLOW_MOCK_WEBHOOK="${ALLOW_MOCK_WEBHOOK:-false}"
# demo | none: whether this script ever invokes the seed function. Defaults
# from DEMO_MODE, so the real app never seeds unless told to in so many words.
SEED="${SEED:-$(dotenv_value SEED)}"
if [ -z "$SEED" ]; then [ "$DEMO_MODE" = true ] && SEED=demo || SEED=none; fi
case "$SEED" in demo|none) ;; *) echo "SEED must be demo or none" >&2; exit 1 ;; esac
# Junction (wearable aggregator). Both secrets are optional: absent, the
# connector stays idle and the console says "Needs setup". The non-secret
# settings come from the environment, else the env file, else the sandbox
# defaults.
GROQ_MODEL="${GROQ_MODEL:-$(dotenv_value GROQ_MODEL)}"
GROQ_MODEL="${GROQ_MODEL:-openai/gpt-oss-120b}"
JUNCTION_PARAM="${JUNCTION_PARAM:-/$STACK_NAME/junction-api-key}"
JUNCTION_WEBHOOK_PARAM="${JUNCTION_WEBHOOK_PARAM:-/$STACK_NAME/junction-webhook-secret}"
JUNCTION_ENVIRONMENT="${JUNCTION_ENVIRONMENT:-$(dotenv_value JUNCTION_ENVIRONMENT)}"
JUNCTION_ENVIRONMENT="${JUNCTION_ENVIRONMENT:-sandbox}"
JUNCTION_REGION="${JUNCTION_REGION:-$(dotenv_value JUNCTION_REGION)}"
JUNCTION_REGION="${JUNCTION_REGION:-us}"
JUNCTION_LINK_REDIRECT_URL="${JUNCTION_LINK_REDIRECT_URL:-$(dotenv_value JUNCTION_LINK_REDIRECT_URL)}"
# Sendblue SMS. Same shape as Junction: two SSM secrets (optional — absent,
# the SMS channel stays on its logging stub) and two plain settings.
SENDBLUE_KEY_PARAM="${SENDBLUE_KEY_PARAM:-/$STACK_NAME/sendblue-api-key}"
SENDBLUE_SECRET_PARAM="${SENDBLUE_SECRET_PARAM:-/$STACK_NAME/sendblue-api-secret}"
# The inbound webhook's secret path segment (patient app). Optional: absent,
# inbound texts answer 503 while outbound SMS keeps working.
SENDBLUE_WEBHOOK_PARAM="${SENDBLUE_WEBHOOK_PARAM:-/$STACK_NAME/sendblue-webhook-secret}"
# The console's shared access token (see "Console access" below).
CONSOLE_TOKEN_PARAM="${CONSOLE_TOKEN_PARAM:-/$STACK_NAME/console-access-token}"
SENDBLUE_FROM_NUMBER="${SENDBLUE_FROM_NUMBER:-$(dotenv_value SENDBLUE_FROM_NUMBER)}"
CARE_TEAM_PHONES="${CARE_TEAM_PHONES:-$(dotenv_value CARE_TEAM_PHONES)}"
# Apple team id of the patient app. Set, the API serves the app-site-
# association file and the same JSON is uploaded beside the SPA, so
# https://<host>/t/<token> opens in the app. Blank: links open the web page.
IOS_TEAM_ID="${IOS_TEAM_ID:-$(dotenv_value IOS_TEAM_ID)}"
# The Android app's signing-certificate fingerprint(s): same idea, assetlinks.json.
ANDROID_CERT_SHA256="${ANDROID_CERT_SHA256:-$(dotenv_value ANDROID_CERT_SHA256)}"
# Custom domain. Both or neither: the template ignores one without the other.
# The certificate must already be ISSUED (CloudFront rejects a pending one),
# and the DNS record lives in whichever account hosts the zone — not here.
# `-` rather than `:-`: an explicitly empty SITE_DOMAIN= on the command line
# overrides the env file, so a deploy without the domain is possible while
# the file keeps the values staged for the cutover.
SITE_DOMAIN="${SITE_DOMAIN-$(dotenv_value SITE_DOMAIN)}"
SITE_CERTIFICATE_ARN="${SITE_CERTIFICATE_ARN-$(dotenv_value SITE_CERTIFICATE_ARN)}"
BUDGET_EMAIL="${BUDGET_EMAIL:-}"
# The personal tier (app/personal). How App Store transactions are checked
# and which environment a strict check accepts; lenient/Sandbox until App
# Store Connect is live. The morning run's schedule, in UTC.
APPLE_SUBSCRIPTION_VERIFY="${APPLE_SUBSCRIPTION_VERIFY:-$(dotenv_value APPLE_SUBSCRIPTION_VERIFY)}"
APPLE_SUBSCRIPTION_VERIFY="${APPLE_SUBSCRIPTION_VERIFY:-lenient}"
APPLE_ENVIRONMENT="${APPLE_ENVIRONMENT:-$(dotenv_value APPLE_ENVIRONMENT)}"
APPLE_ENVIRONMENT="${APPLE_ENVIRONMENT:-Sandbox}"
PERSONAL_DAILY_CRON="${PERSONAL_DAILY_CRON:-$(dotenv_value PERSONAL_DAILY_CRON)}"
PERSONAL_DAILY_CRON="${PERSONAL_DAILY_CRON:-cron(0 12 * * ? *)}"
SPORTS_DAILY_CRON="${SPORTS_DAILY_CRON:-$(dotenv_value SPORTS_DAILY_CRON)}"
SPORTS_DAILY_CRON="${SPORTS_DAILY_CRON:-cron(0 11 * * ? *)}"

log()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\033[31merror: %s\033[0m\n' "$*" >&2; exit 1; }

aws_() { aws --region "$REGION" "$@"; }

# --------------------------------------------------------------------------
log "Preflight"
# --------------------------------------------------------------------------
for tool in aws uv zip; do
  $STACK_ONLY && [ "$tool" != aws ] && continue
  command -v "$tool" >/dev/null || die "$tool is required but not installed"
done
$BACKEND_ONLY || command -v npm >/dev/null || die "npm is required (or pass --backend-only)"

ACCOUNT_ID="$(aws_ sts get-caller-identity --query Account --output text 2>/dev/null)" \
  || die "no valid AWS credentials. In CloudShell they are automatic; locally run 'aws configure'."
CALLER="$(aws_ sts get-caller-identity --query Arn --output text)"
info "account $ACCOUNT_ID in $REGION"
info "as      $CALLER"
info "stack   $STACK_NAME ($([ "$DEMO_MODE" = true ] && echo 'the public demo' || echo 'the real app'); env file $ENV_FILE)"
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

# Custom domain: refuse early rather than let CloudFormation fail mid-update.
# ACM is queried in us-east-1 regardless of REGION — CloudFront only accepts
# certificates from there.
if [ -n "$SITE_DOMAIN" ] || [ -n "$SITE_CERTIFICATE_ARN" ]; then
  [ -n "$SITE_DOMAIN" ] && [ -n "$SITE_CERTIFICATE_ARN" ] \
    || die "SITE_DOMAIN and SITE_CERTIFICATE_ARN must be set together (see infra/README.md, 'Custom domain')"
  CERT_STATUS="$(aws --region us-east-1 acm describe-certificate \
    --certificate-arn "$SITE_CERTIFICATE_ARN" --query 'Certificate.Status' --output text 2>/dev/null \
    || echo NOT_FOUND)"
  if [ "$CERT_STATUS" != "ISSUED" ]; then
    info "certificate for $SITE_DOMAIN is $CERT_STATUS — CloudFront needs ISSUED"
    aws --region us-east-1 acm describe-certificate --certificate-arn "$SITE_CERTIFICATE_ARN" \
      --query 'Certificate.DomainValidationOptions[].ResourceRecord.[Name,Type,Value]' \
      --output text 2>/dev/null | sed 's/^/    validation record needed: /'
    die "add that record in the medpull.org zone and rerun; or unset SITE_DOMAIN to deploy without the domain"
  fi
  info "custom domain $SITE_DOMAIN (certificate issued)"
fi

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

# Groq key: an existing SSM value wins, then $GROQ_API_KEY, then the env file,
# then a prompt. Never echoed.
if aws_ ssm get-parameter --name "$GROQ_PARAM" >/dev/null 2>&1; then
  info "Groq key already in SSM at $GROQ_PARAM (delete the parameter to change it)"
else
  KEY="${GROQ_API_KEY:-}"
  [ -n "$KEY" ] || KEY="$(dotenv_value GROQ_API_KEY)"
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
# env file. Never prompted for — both are optional and a deploy without them
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
    info "no $label — that integration stays idle until one is stored"
  fi
}
store_optional_secret "$JUNCTION_PARAM" JUNCTION_API_KEY "Junction API key"
store_optional_secret "$JUNCTION_WEBHOOK_PARAM" JUNCTION_WEBHOOK_SECRET "Junction webhook secret"
store_optional_secret "$SENDBLUE_KEY_PARAM" SENDBLUE_API_KEY "Sendblue API key"
store_optional_secret "$SENDBLUE_SECRET_PARAM" SENDBLUE_API_SECRET "Sendblue API secret"
store_optional_secret "$SENDBLUE_WEBHOOK_PARAM" SENDBLUE_WEBHOOK_SECRET "Sendblue webhook secret"

# Console access. Unlike the integrations above this is never generated on
# its own: an absent parameter is an open console, which only the demo
# stack should run with. Set
# CONSOLE_ACCESS_TOKEN to lock the console with that value (a new value
# replaces the stored one), or CONSOLE_ACCESS_TOKEN=generate to mint one and
# print it once.
CONSOLE_ACCESS_TOKEN="${CONSOLE_ACCESS_TOKEN:-$(dotenv_value CONSOLE_ACCESS_TOKEN)}"
if [ "$CONSOLE_ACCESS_TOKEN" = "generate" ]; then
  CONSOLE_ACCESS_TOKEN="$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  aws_ ssm put-parameter --name "$CONSOLE_TOKEN_PARAM" --type SecureString --overwrite \
    --value "$CONSOLE_ACCESS_TOKEN" --description "Console access token for Recovery Copilot" >/dev/null
  info "console access token (shown once, keep it): $CONSOLE_ACCESS_TOKEN"
elif [ -n "$CONSOLE_ACCESS_TOKEN" ]; then
  aws_ ssm put-parameter --name "$CONSOLE_TOKEN_PARAM" --type SecureString --overwrite \
    --value "$CONSOLE_ACCESS_TOKEN" --description "Console access token for Recovery Copilot" >/dev/null
  info "stored the console access token in SSM ($CONSOLE_TOKEN_PARAM)"
elif aws_ ssm get-parameter --name "$CONSOLE_TOKEN_PARAM" >/dev/null 2>&1; then
  info "console locked with the token already in SSM (delete the parameter to reopen it)"
elif [ "$DEMO_MODE" = true ]; then
  info "no console access token — the demo console stays open"
else
  info "WARNING: no console access token and DEMO_MODE=false — the real console is open."
  info "         Set CONSOLE_ACCESS_TOKEN=generate in $ENV_FILE and redeploy."
fi

# --------------------------------------------------------------------------
if $STACK_ONLY; then
log "Reusing the deployed Lambda package (--stack-only)"
# --------------------------------------------------------------------------
  # Ship the template and parameters only. The function keeps whatever zip
  # the stack already points at, so a working tree mid-change cannot leak
  # into production through an infrastructure-only update.
  stack_param() {
    aws_ cloudformation describe-stacks --stack-name "$STACK_NAME" \
      --query "Stacks[0].Parameters[?ParameterKey=='$1'].ParameterValue" --output text 2>/dev/null
  }
  ARTIFACT_BUCKET="$(stack_param LambdaCodeBucket)"
  ZIP_KEY="$(stack_param LambdaCodeKey)"
  [ -n "$ARTIFACT_BUCKET" ] && [ -n "$ZIP_KEY" ] \
    || die "--stack-only needs an existing stack; run a full deploy first"
  info "s3://$ARTIFACT_BUCKET/$ZIP_KEY"
else
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
fi

# --------------------------------------------------------------------------
log "Deploying the stack"
# --------------------------------------------------------------------------
# Without a custom domain the links in patient texts need the distribution's
# host, which the template cannot reference from the function (a cycle). Take
# it from the previous deploy's output; a first deploy leaves it blank and the
# next one fills it in.
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-$(aws_ cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='SiteUrl'].OutputValue" --output text 2>/dev/null || true)}"
[ "$PUBLIC_BASE_URL" = "None" ] && PUBLIC_BASE_URL=""
[ -n "$PUBLIC_BASE_URL" ] && info "public base URL for patient links: $PUBLIC_BASE_URL"

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
  "SendblueApiKeyParameter=$SENDBLUE_KEY_PARAM"
  "SendblueApiSecretParameter=$SENDBLUE_SECRET_PARAM"
  "SendblueWebhookSecretParameter=$SENDBLUE_WEBHOOK_PARAM"
  "ConsoleAccessTokenParameter=$CONSOLE_TOKEN_PARAM"
  "DemoMode=$DEMO_MODE"
  "PersonalPaywall=$PERSONAL_PAYWALL"
  "AllowMockWebhook=$ALLOW_MOCK_WEBHOOK"
  "PublicBaseUrl=$PUBLIC_BASE_URL"
  "SendblueFromNumber=$SENDBLUE_FROM_NUMBER"
  "CareTeamPhones=$CARE_TEAM_PHONES"
  "IosTeamId=$IOS_TEAM_ID"
  "AndroidCertSha256=$ANDROID_CERT_SHA256"
  "ApiReservedConcurrency=$RESERVED"
  # Passed even when empty so clearing them in .env removes the alias.
  "CustomDomainName=$SITE_DOMAIN"
  "CertificateArn=$SITE_CERTIFICATE_ARN"
  "AppleSubscriptionVerify=$APPLE_SUBSCRIPTION_VERIFY"
  "AppleEnvironment=$APPLE_ENVIRONMENT"
  "PersonalDailyCron=$PERSONAL_DAILY_CRON"
  "SportsDailyCron=$SPORTS_DAILY_CRON"
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
PERSONAL_BUCKET="$(outputs PersonalDataBucketName)"
DIST_ID="$(outputs DistributionId)"
DIST_DOMAIN="$(outputs DistributionDomainName)"
SEED_FN="$(outputs SeedFunctionName)"
info "site   $SITE_URL"
info "bucket $DATA_BUCKET"
info "personal bucket $PERSONAL_BUCKET (subscribers' files; separate from the clinic bucket)"

# --------------------------------------------------------------------------
if ! $BACKEND_ONLY; then
log "Building and uploading the frontend"
# --------------------------------------------------------------------------
  (cd "$ROOT/frontend" && npm ci --no-audit --no-fund && npm run build)
  DIST="$ROOT/frontend/dist"
  [ -f "$DIST/index.html" ] || die "frontend build produced no dist/index.html"

  # patient/ is the patient web app's prefix, uploaded below; --delete must
  # not take it out.
  aws_ s3 sync "$DIST/" "s3://$DATA_BUCKET/web/" --delete --only-show-errors \
    --exclude "patient/*" --cache-control "public,max-age=3600"
  # Vite content-hashes everything under assets/, so those can be immutable.
  aws_ s3 cp "$DIST/assets/" "s3://$DATA_BUCKET/web/assets/" --recursive --only-show-errors \
    --metadata-directive REPLACE --cache-control "public,max-age=31536000,immutable"
  # index.html points at hashed bundles; a cached copy would pin a stale build.
  aws_ s3 cp "$DIST/index.html" "s3://$DATA_BUCKET/web/index.html" --only-show-errors \
    --cache-control "no-cache" --content-type "text/html; charset=utf-8"

  # App links. Only /api/* reaches the function, so the association files
  # the backend can serve never get a request on AWS: the same JSON is
  # uploaded as static objects instead (after the sync, which would delete
  # them). The CloudFront rewrite exempts /.well-known/.
  put_json() {  # put_json KEY JSON
    printf '%s' "$2" | aws_ s3 cp - "s3://$DATA_BUCKET/$1" --only-show-errors \
      --cache-control "no-cache" --content-type "application/json"
  }
  if [ -n "$IOS_TEAM_ID" ]; then
    AASA="$(cd "$ROOT/backend" && IOS_TEAM_ID="$IOS_TEAM_ID" uv run python -c \
      'import json; from app.api.applinks import association; print(json.dumps(association()))')"
    put_json web/.well-known/apple-app-site-association "$AASA"
    put_json web/apple-app-site-association "$AASA"
    info "uploaded apple-app-site-association for team $IOS_TEAM_ID"
  else
    info "IOS_TEAM_ID not set — task links open the web page on iPhone, not the app"
  fi
  if [ -n "$ANDROID_CERT_SHA256" ]; then
    LINKS="$(cd "$ROOT/backend" && ANDROID_CERT_SHA256="$ANDROID_CERT_SHA256" uv run python -c \
      'import json; from app.api.applinks import asset_links; print(json.dumps(asset_links()))')"
    put_json web/.well-known/assetlinks.json "$LINKS"
    info "uploaded assetlinks.json"
  else
    info "ANDROID_CERT_SHA256 not set — task links open the web page on Android, not the app"
  fi

# --------------------------------------------------------------------------
log "Building and uploading the patient web app"
# --------------------------------------------------------------------------
  # Served at $SITE_URL/patient/ (vite base, router basename); the CloudFront
  # function sends its extensionless routes to web/patient/index.html.
  (cd "$ROOT/patient-web" && npm ci --no-audit --no-fund && npm run build)
  PDIST="$ROOT/patient-web/dist"
  [ -f "$PDIST/index.html" ] || die "patient-web build produced no dist/index.html"

  aws_ s3 sync "$PDIST/" "s3://$DATA_BUCKET/web/patient/" --delete --only-show-errors \
    --cache-control "public,max-age=3600"
  aws_ s3 cp "$PDIST/assets/" "s3://$DATA_BUCKET/web/patient/assets/" --recursive --only-show-errors \
    --metadata-directive REPLACE --cache-control "public,max-age=31536000,immutable"
  aws_ s3 cp "$PDIST/index.html" "s3://$DATA_BUCKET/web/patient/index.html" --only-show-errors \
    --cache-control "no-cache" --content-type "text/html; charset=utf-8"
fi

# --------------------------------------------------------------------------
log "Database"
# --------------------------------------------------------------------------
DB_EXISTS=true
aws_ s3api head-object --bucket "$DATA_BUCKET" --key db/recovery.db >/dev/null 2>&1 || DB_EXISTS=false

if [ "$SEED" = none ]; then
  # The real app. Its database is whatever is in the bucket: the first
  # request creates an empty schema, and charts arrive from the app and the
  # clinic. The seed function would refuse anyway (app/seed/seed.py), but
  # not invoking it at all is the clearer statement.
  $DB_EXISTS && info "database present; this stack is never seeded (SEED=none)" \
    || info "no database yet — the first request creates an empty one (SEED=none)"
elif ! $DB_EXISTS || $RESEED; then
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
  if ! $SEED_OK; then
    # A refusal (live patients, or a stack that is not the demo) shows up
    # only in the function's log, so print its tail before giving up.
    aws_ logs tail "/aws/lambda/$SEED_FN" --since 20m --format short 2>/dev/null | tail -20 | sed 's/^/    /'
    die "seed did not finish in 15 minutes (see the log lines above, or: aws logs tail /aws/lambda/$SEED_FN)"
  fi
  info "seeded — the database object landed in S3"
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
# Against the distribution's own hostname: it answers whether or not the
# custom domain's DNS record exists yet.
sleep 5
if HEALTH="$(curl -fsS --max-time 60 "https://$DIST_DOMAIN/api/health" 2>/dev/null)"; then
  info "$HEALTH"
else
  info "health check did not answer yet — a new distribution takes a few"
  info "minutes to propagate. Retry: curl https://$DIST_DOMAIN/api/health"
fi

log "Done"
info "$SITE_URL"
if [ -n "$SITE_DOMAIN" ]; then
  info "DNS: $SITE_DOMAIN  CNAME  $DIST_DOMAIN   (in the account that hosts the medpull.org zone)"
fi
