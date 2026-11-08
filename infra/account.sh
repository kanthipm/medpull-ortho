#!/usr/bin/env bash
#
# Account hygiene for the AWS account the stacks live in: the things no stack
# owns. Who can sign in and how (an admins group that is useless until MFA is
# on), GuardDuty, the cost allocation tags, and the policy that lets CloudTrail
# write to its log bucket. Idempotent: every step says what it is about to do
# and skips what is already there; --dry-run only says.
#
#   ./infra/account.sh --dry-run                                   # what would change
#   ./infra/account.sh --user steve --user kanthi                  # group + users
#   ./infra/account.sh --trail-bucket medpull-cloudtrail-logs-1759818803
#
# Run as the root user the first time: someone has to make the first IAM
# user, and that is the one job root is for. Afterwards sign in as that user
# and leave root alone. Details in infra/README.md, "Account setup".
#
set -euo pipefail

DRY_RUN=false
USERS=()
TRAIL_BUCKET=""
want_user=false
want_bucket=false
for arg in "$@"; do
  if $want_user; then USERS+=("$arg"); want_user=false; continue; fi
  if $want_bucket; then TRAIL_BUCKET="$arg"; want_bucket=false; continue; fi
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --user) want_user=true ;;
    --user=*) USERS+=("${arg#--user=}") ;;
    --trail-bucket) want_bucket=true ;;
    --trail-bucket=*) TRAIL_BUCKET="${arg#--trail-bucket=}" ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 1 ;;
  esac
done
$want_user && { echo "--user needs a name" >&2; exit 1; }
$want_bucket && { echo "--trail-bucket needs a name" >&2; exit 1; }

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
GROUP="${ADMIN_GROUP:-medpull-admins}"
MFA_POLICY_NAME="${MFA_POLICY_NAME:-medpull-require-mfa}"
# The tags the template and deploy.sh put on every resource. Cost Explorer
# can split the bill by them once they are activated here.
COST_TAGS=(medpull:facet medpull:deployment medpull:stack)

log()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
skip() { printf '    \033[2malready: %s\033[0m\n' "$*"; }
die()  { printf '\033[31merror: %s\033[0m\n' "$*" >&2; exit 1; }
# act WHAT: prints the step; true when it should now be carried out.
act() {
  if $DRY_RUN; then printf '    would: %s\n' "$*"; return 1; fi
  printf '    doing: %s\n' "$*"
}
aws_() { aws --region "$REGION" "$@"; }

# --------------------------------------------------------------------------
log "Preflight"
# --------------------------------------------------------------------------
command -v aws >/dev/null || die "the aws CLI is required"
ACCOUNT_ID="$(aws_ sts get-caller-identity --query Account --output text 2>/dev/null)" \
  || die "no valid AWS credentials (aws configure, or run this in CloudShell)"
CALLER="$(aws_ sts get-caller-identity --query Arn --output text)"
info "account $ACCOUNT_ID in $REGION"
info "as      $CALLER"
$DRY_RUN && info "dry run: nothing below is carried out"
case "$CALLER" in
  *":root") info "root: right for the first run. Once a user below has MFA, sign in as them instead." ;;
esac
ROOT_MFA="$(aws_ iam get-account-summary --query 'SummaryMap.AccountMFAEnabled' --output text 2>/dev/null || echo 0)"
ROOT_KEYS="$(aws_ iam get-account-summary --query 'SummaryMap.AccountAccessKeysPresent' --output text 2>/dev/null || echo 0)"
if [ "$ROOT_MFA" = 1 ]; then
  skip "root has MFA"
else
  info "TO DO by hand: turn on MFA for the root user (console: account menu -> Security credentials)"
fi
[ "$ROOT_KEYS" = 0 ] || info "TO DO by hand: root has access keys; delete them once a user from $GROUP works with MFA"

# --------------------------------------------------------------------------
log "Admins group $GROUP"
# --------------------------------------------------------------------------
# AdministratorAccess plus a policy that denies everything but setting up MFA
# while no MFA is present. The deny wins, so a freshly created user can sign
# in, change the password, register a device — and nothing else until they
# sign in again with the code.
if aws_ iam get-group --group-name "$GROUP" >/dev/null 2>&1; then
  skip "group exists"
elif act "create IAM group $GROUP"; then
  aws_ iam create-group --group-name "$GROUP" >/dev/null
fi

group_has() {  # group_has POLICY_ARN -> 0 when attached
  [ "$(aws_ iam list-attached-group-policies --group-name "$GROUP" \
    --query "length(AttachedPolicies[?PolicyArn=='$1'])" --output text 2>/dev/null || echo 0)" != 0 ]
}
ADMIN_ARN="arn:aws:iam::aws:policy/AdministratorAccess"
if group_has "$ADMIN_ARN"; then
  skip "AdministratorAccess attached"
elif act "attach AdministratorAccess to $GROUP"; then
  aws_ iam attach-group-policy --group-name "$GROUP" --policy-arn "$ADMIN_ARN"
fi

MFA_POLICY_ARN="arn:aws:iam::$ACCOUNT_ID:policy/$MFA_POLICY_NAME"
# ${aws:username} is an IAM policy variable, not a shell one: the heredoc is quoted.
MFA_POLICY_DOC="$(cat <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowViewAccountInfo",
      "Effect": "Allow",
      "Action": ["iam:GetAccountPasswordPolicy", "iam:GetAccountSummary", "iam:ListVirtualMFADevices"],
      "Resource": "*"
    },
    {
      "Sid": "AllowManageOwnPasswordAndMFA",
      "Effect": "Allow",
      "Action": [
        "iam:ChangePassword", "iam:GetUser", "iam:GetLoginProfile", "iam:UpdateLoginProfile",
        "iam:CreateVirtualMFADevice", "iam:EnableMFADevice", "iam:GetMFADevice",
        "iam:ListMFADevices", "iam:ResyncMFADevice"
      ],
      "Resource": ["arn:aws:iam::*:user/${aws:username}", "arn:aws:iam::*:mfa/*"]
    },
    {
      "Sid": "AllowRemoveOwnMFAOnlyWithMFA",
      "Effect": "Allow",
      "Action": ["iam:DeactivateMFADevice", "iam:DeleteVirtualMFADevice"],
      "Resource": ["arn:aws:iam::*:user/${aws:username}", "arn:aws:iam::*:mfa/*"],
      "Condition": {"Bool": {"aws:MultiFactorAuthPresent": "true"}}
    },
    {
      "Sid": "DenyEverythingElseWithoutMFA",
      "Effect": "Deny",
      "NotAction": [
        "iam:ChangePassword", "iam:GetUser", "iam:GetLoginProfile", "iam:UpdateLoginProfile",
        "iam:CreateVirtualMFADevice", "iam:EnableMFADevice", "iam:GetMFADevice",
        "iam:ListMFADevices", "iam:ResyncMFADevice", "iam:ListVirtualMFADevices",
        "iam:GetAccountPasswordPolicy", "iam:GetAccountSummary", "sts:GetSessionToken"
      ],
      "Resource": "*",
      "Condition": {"BoolIfExists": {"aws:MultiFactorAuthPresent": "false"}}
    }
  ]
}
JSON
)"
if aws_ iam get-policy --policy-arn "$MFA_POLICY_ARN" >/dev/null 2>&1; then
  skip "policy $MFA_POLICY_NAME exists"
elif act "create policy $MFA_POLICY_NAME (deny everything but MFA setup while no MFA is present)"; then
  aws_ iam create-policy --policy-name "$MFA_POLICY_NAME" --policy-document "$MFA_POLICY_DOC" \
    --description "MedPull: nothing but password and MFA self-service until MFA is present" >/dev/null
fi
if group_has "$MFA_POLICY_ARN"; then
  skip "$MFA_POLICY_NAME attached"
elif act "attach $MFA_POLICY_NAME to $GROUP"; then
  aws_ iam attach-group-policy --group-name "$GROUP" --policy-arn "$MFA_POLICY_ARN"
fi

# --------------------------------------------------------------------------
# Users, from --user flags. A console password only (no access keys: the
# deploy runs from CloudShell or with the user's own short-lived credentials),
# generated here, printed once, and replaced at first sign-in.
# --------------------------------------------------------------------------
new_password() {
  # 16 random letters and digits, then a dash, a letter, a digit and a mark:
  # four classes and 20 characters satisfies any account password policy.
  # cut rather than head on the far end, so tr is never cut off mid-write
  # (pipefail would turn that SIGPIPE into an error).
  local alnum
  alnum="$(head -c 400 /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9' | cut -c1-16)"
  printf '%s-Q%d!' "$alnum" "$((RANDOM % 10))"
}
ALIAS="$(aws_ iam list-account-aliases --query 'AccountAliases[0]' --output text 2>/dev/null || echo None)"
[ "$ALIAS" = None ] && ALIAS="$ACCOUNT_ID"
SIGNIN_URL="https://$ALIAS.signin.aws.amazon.com/console"

for user in ${USERS[@]+"${USERS[@]}"}; do
  log "User $user"
  if aws_ iam get-user --user-name "$user" >/dev/null 2>&1; then
    skip "user exists"
  elif act "create IAM user $user"; then
    aws_ iam create-user --user-name "$user" \
      --tags Key=medpull:managed-by,Value=infra/account.sh >/dev/null
  fi
  in_group="$(aws_ iam list-groups-for-user --user-name "$user" \
    --query "length(Groups[?GroupName=='$GROUP'])" --output text 2>/dev/null || echo 0)"
  if [ "$in_group" != 0 ]; then
    skip "in $GROUP"
  elif act "add $user to $GROUP"; then
    aws_ iam add-user-to-group --user-name "$user" --group-name "$GROUP"
  fi
  if aws_ iam get-login-profile --user-name "$user" >/dev/null 2>&1; then
    skip "console password set"
  elif act "set a one-time console password for $user (change required at first sign-in)"; then
    PASSWORD="$(new_password)"
    # Through a private temp file rather than an argument, so it never shows
    # in a process list. (Not a pipe: the CLI refuses --cli-input-json from
    # /dev/stdin on macOS, "Invalid JSON received".)
    PROFILE_JSON="$(mktemp)"
    chmod 600 "$PROFILE_JSON"
    printf '{"UserName":"%s","Password":"%s","PasswordResetRequired":true}' "$user" "$PASSWORD" \
      > "$PROFILE_JSON"
    if ! aws_ iam create-login-profile --cli-input-json "file://$PROFILE_JSON" >/dev/null; then
      rm -f "$PROFILE_JSON"; unset PASSWORD
      die "could not set the console password for $user"
    fi
    rm -f "$PROFILE_JSON"
    info "one-time password for $user (shown once, stored nowhere): $PASSWORD"
    unset PASSWORD
  fi
  info "MFA is the person's own step, in the console:"
  info "  1. sign in at $SIGNIN_URL as $user with the one-time password; set a new one"
  info "  2. account menu (top right) -> Security credentials -> Assign MFA device"
  info "     (an authenticator app, or a passkey / security key)"
  info "  3. sign out and back in with the code. Until then the group's deny policy"
  info "     allows nothing but steps 1 and 2."
done
[ ${#USERS[@]} -gt 0 ] || info "(no --user given; the group is in place for when one is)"

# --------------------------------------------------------------------------
log "GuardDuty"
# --------------------------------------------------------------------------
# Reads the CloudTrail, DNS and VPC flow logs the account already produces
# and raises findings on them; nothing to configure per stack. 30 days free,
# then a few dollars a month at this volume.
DETECTOR="$(aws_ guardduty list-detectors --query 'DetectorIds[0]' --output text 2>/dev/null || echo None)"
if [ -n "$DETECTOR" ] && [ "$DETECTOR" != None ]; then
  STATUS="$(aws_ guardduty get-detector --detector-id "$DETECTOR" --query Status --output text 2>/dev/null || echo UNKNOWN)"
  if [ "$STATUS" = ENABLED ]; then
    skip "detector $DETECTOR enabled in $REGION"
  elif act "enable detector $DETECTOR ($STATUS)"; then
    aws_ guardduty update-detector --detector-id "$DETECTOR" --enable
  fi
elif act "create and enable a GuardDuty detector in $REGION"; then
  aws_ guardduty create-detector --enable --finding-publishing-frequency SIX_HOURS \
    --query DetectorId --output text | sed 's/^/    detector /'
fi

# --------------------------------------------------------------------------
log "Cost allocation tags"
# --------------------------------------------------------------------------
# A tag key can only be activated after it has appeared on a bill, which is
# up to 24 hours after the first tagged deploy — until then Cost Explorer has
# never heard of it and this step says so. Rerun once it has. The Cost
# Explorer API is global and lives in us-east-1 whatever the stack's region.
for tag in "${COST_TAGS[@]}"; do
  status="$(aws --region us-east-1 ce list-cost-allocation-tags --tag-keys "$tag" \
    --query 'CostAllocationTags[0].Status' --output text 2>/dev/null || echo None)"
  case "$status" in
    Active) skip "$tag active" ;;
    Inactive)
      if act "activate $tag"; then
        errors="$(aws --region us-east-1 ce update-cost-allocation-tags-status \
          --cost-allocation-tags-status "TagKey=$tag,Status=Active" --query 'Errors' --output text)"
        [ -z "$errors" ] || [ "$errors" = None ] || info "Cost Explorer answered: $errors"
      fi ;;
    *) info "$tag has not appeared on a bill yet (up to 24 h after the first tagged deploy); rerun then" ;;
  esac
done

# --------------------------------------------------------------------------
if [ -n "$TRAIL_BUCKET" ]; then
log "CloudTrail log bucket $TRAIL_BUCKET"
# --------------------------------------------------------------------------
  # What a trail needs from its bucket: to read the ACL and to put objects
  # it owns outright — from this account only, over TLS only. Prefix-free on
  # purpose: each stack's trail writes under its own <stack>/ prefix.
  aws_ s3api head-bucket --bucket "$TRAIL_BUCKET" >/dev/null 2>&1 \
    || die "no bucket named $TRAIL_BUCKET in this account"
  TRAIL_POLICY_DOC="$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AWSCloudTrailAclCheck",
      "Effect": "Allow",
      "Principal": {"Service": "cloudtrail.amazonaws.com"},
      "Action": "s3:GetBucketAcl",
      "Resource": "arn:aws:s3:::$TRAIL_BUCKET",
      "Condition": {"StringEquals": {"aws:SourceAccount": "$ACCOUNT_ID"}}
    },
    {
      "Sid": "AWSCloudTrailWrite",
      "Effect": "Allow",
      "Principal": {"Service": "cloudtrail.amazonaws.com"},
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::$TRAIL_BUCKET/*",
      "Condition": {
        "StringEquals": {
          "s3:x-amz-acl": "bucket-owner-full-control",
          "aws:SourceAccount": "$ACCOUNT_ID"
        }
      }
    },
    {
      "Sid": "DenyInsecureTransport",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": ["arn:aws:s3:::$TRAIL_BUCKET", "arn:aws:s3:::$TRAIL_BUCKET/*"],
      "Condition": {"Bool": {"aws:SecureTransport": "false"}}
    }
  ]
}
JSON
)"
  EXISTING="$(aws_ s3api get-bucket-policy --bucket "$TRAIL_BUCKET" --query Policy --output text 2>/dev/null || true)"
  if printf '%s' "$EXISTING" | grep -q 'cloudtrail.amazonaws.com' \
     && printf '%s' "$EXISTING" | grep -q 's3:PutObject'; then
    skip "the bucket policy lets CloudTrail write"
  elif [ -n "$EXISTING" ]; then
    # Never replace a policy that is doing something else; show the two.
    info "the bucket has a policy that says nothing about CloudTrail. Add these statements to it by hand:"
    printf '%s\n' "$TRAIL_POLICY_DOC" | sed 's/^/      /'
    info "current policy:"
    printf '%s\n' "$EXISTING" | sed 's/^/      /'
  elif act "put the CloudTrail bucket policy on $TRAIL_BUCKET"; then
    printf '%s' "$TRAIL_POLICY_DOC" | aws_ s3api put-bucket-policy --bucket "$TRAIL_BUCKET" --policy file:///dev/stdin
  else
    printf '%s\n' "$TRAIL_POLICY_DOC" | sed 's/^/      /'
  fi
  info "then, per stack: TRAIL_BUCKET=$TRAIL_BUCKET in its env file and ./infra/deploy.sh --stack-only"
fi

log "Done"
$DRY_RUN && info "nothing was changed (--dry-run)"
info "the stacks themselves: ./infra/deploy.sh (tags, keys, trail); the picture afterwards: make audit-compartments"
