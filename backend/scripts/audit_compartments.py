#!/usr/bin/env python
"""Who is in each compartment, and what the compartments are made of.

    uv run python scripts/audit_compartments.py --local data/recovery.db
    uv run python scripts/audit_compartments.py --bucket <data bucket>
    uv run python scripts/audit_compartments.py --stack recovery-copilot   # bucket from the stack, plus AWS
    uv run python scripts/audit_compartments.py --stack medpull-demo --json

The database half is read-only: ``--bucket`` downloads ``db/recovery.db`` to a
temporary file with the client the app uses, takes no lock and uploads
nothing; ``--local`` opens the file read-only. It prints, per facet, who is
there: each hospital with its patient counts (total, with a phone, signed in
on the app, consented), each sports organisation with its teams and athlete
counts, the personal subscribers and how many are paired to a clinic chart,
and the console credentials by kind, org and label — never a hash.

With ``--stack`` it adds what AWS says about the compartment, every call a
describe, list or get: the stack's DemoMode and tags, the buckets with their
default encryption and tags, the KMS aliases, the parameter names under
/<stack>/, whether GuardDuty and a CloudTrail trail exist, and the budget.
Without credentials that half is one line saying so.

Every provider is switched off in this process: nothing here can text, call
Groq, or write.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

DB_KEY = "db/recovery.db"


# --------------------------------------------------------------------------
# the database half
# --------------------------------------------------------------------------


def _quiet_environment() -> None:
    """No provider can be reached from this process, whatever .env says."""
    for key in ("GROQ_API_KEY", "JUNCTION_API_KEY", "JUNCTION_WEBHOOK_SECRET", "SENDBLUE_API_KEY",
                "SENDBLUE_API_SECRET", "SENDBLUE_WEBHOOK_SECRET", "OLLAMA_URL", "CARE_TEAM_PHONES"):
        os.environ[key] = ""
    os.environ["WARM_CACHES_ON_STARTUP"] = "false"
    # The storage layer stays inert (no hydrate, no lock, no write-back); only
    # its S3 client is borrowed for the download.
    os.environ["S3_BUCKET"] = ""


def _download(bucket: str, key: str, target: Path) -> None:
    from app.aws import storage

    storage.client().download_file(bucket, key, str(target))


def _patient_counts(db, patient_ids_stmt) -> dict:
    """The four counts the roster questions come down to, over one set of
    patient ids: how many, how many a text can reach, how many are signed in
    on the app right now, how many have a consent on file."""
    from sqlalchemy import func, select

    from app.models.mobile import PatientSession, live_session_clause
    from app.models.patient import Patient
    from app.models.personal import Consent

    ids = patient_ids_stmt.subquery()
    total = db.scalar(select(func.count()).select_from(ids)) or 0
    with_phone = db.scalar(
        select(func.count(Patient.id)).where(Patient.id.in_(select(ids)), Patient.phone.is_not(None))
    ) or 0
    signed_in = db.scalar(
        select(func.count(func.distinct(PatientSession.patient_id))).where(
            PatientSession.patient_id.in_(select(ids)), live_session_clause()
        )
    ) or 0
    consented = db.scalar(
        select(func.count(func.distinct(Consent.patient_id))).where(
            Consent.patient_id.in_(select(ids)), Consent.withdrawn_at.is_(None)
        )
    ) or 0
    return {"patients": total, "with_phone": with_phone, "signed_in": signed_in,
            "consented": consented}


def clinic_report(db) -> dict:
    from sqlalchemy import select

    from app.models.hospital import Hospital
    from app.models.patient import Patient
    from app.personal.scope import clinic_filter

    hospitals = []
    for h in db.scalars(select(Hospital).order_by(Hospital.name)).all():
        ids = clinic_filter(select(Patient.id)).where(Patient.hospital_id == h.id)
        hospitals.append({
            "id": h.id, "name": h.name, "city": f"{h.city}, {h.state}", "active": bool(h.active),
            # Whether the old per-hospital dashboard token is still set; never its value.
            "legacy_token": h.access_token is not None,
            **_patient_counts(db, ids),
        })
    known = select(Hospital.id)
    unassigned = clinic_filter(select(Patient.id)).where(
        (Patient.hospital_id.is_(None)) | (Patient.hospital_id.not_in(known))
    )
    return {"hospitals": hospitals, "no_hospital": _patient_counts(db, unassigned)}


def sports_report(db) -> dict:
    from sqlalchemy import func, select

    from app.models.patient import Patient
    from app.models.sports import SportsOrg, SportsProfile, SportsStaff, SportsTeam

    orgs = []
    for org in db.scalars(select(SportsOrg).order_by(SportsOrg.name)).all():
        teams = []
        for team in db.scalars(
            select(SportsTeam).where(SportsTeam.org_id == org.id).order_by(SportsTeam.name)
        ).all():
            athletes = select(SportsProfile.patient_id).where(SportsProfile.team_id == team.id)
            teams.append({"id": team.id, "name": team.name, "sport": team.sport,
                          "season": team.season, **_patient_counts(db, athletes)})
        no_team = select(SportsProfile.patient_id).where(
            SportsProfile.org_id == org.id, SportsProfile.team_id.is_(None)
        )
        orgs.append({
            "id": org.id, "name": org.name, "kind": org.kind, "level": org.level,
            "join_code": org.join_code is not None,  # set or not; never the code
            "staff": db.scalar(
                select(func.count(SportsStaff.id)).where(SportsStaff.org_id == org.id)) or 0,
            "teams": teams,
            "athletes": _patient_counts(
                db, select(SportsProfile.patient_id).where(SportsProfile.org_id == org.id)),
            "no_team": _patient_counts(db, no_team)["patients"],
        })
    unaffiliated = select(Patient.id).where(
        Patient.account_kind == "sports",
        Patient.id.not_in(select(SportsProfile.patient_id).where(SportsProfile.org_id.is_not(None))),
    )
    return {"orgs": orgs, "unaffiliated": _patient_counts(db, unaffiliated)}


def personal_report(db) -> dict:
    from sqlalchemy import func, select

    from app.models.patient import Patient
    from app.models.personal import Entitlement, PersonalCredential

    subscribers = select(Patient.id).where(Patient.account_kind == "personal")
    counts = _patient_counts(db, subscribers)
    paired = db.scalar(
        select(func.count(Patient.id)).where(
            Patient.account_kind == "personal", Patient.linked_patient_id.is_not(None))
    ) or 0
    with_login = db.scalar(
        select(func.count(PersonalCredential.patient_id)).where(
            PersonalCredential.patient_id.in_(subscribers))
    ) or 0
    now = datetime.now()
    entitled = db.scalar(
        select(func.count(func.distinct(Entitlement.patient_id))).where(
            Entitlement.patient_id.in_(subscribers),
            Entitlement.status == "active",
            (Entitlement.expires_at.is_(None)) | (Entitlement.expires_at > now),
        )
    ) or 0
    return {**counts, "paired_to_chart": paired, "with_login": with_login,
            "entitled_now": entitled}


def credentials_report(db) -> dict:
    """The console_credentials table, if this database has it: kind, org,
    label and the three dates. The hash column is never selected — the
    column list is built from the schema, and token_hash is not on it."""
    from sqlalchemy import inspect, text

    try:  # registers the model if the branch has it; the query below does not need it
        import app.models.credential  # noqa: F401
    except ImportError:
        pass
    inspector = inspect(db.get_bind())
    if "console_credentials" not in inspector.get_table_names():
        return {"table": False, "rows": []}
    have = {c["name"] for c in inspector.get_columns("console_credentials")}
    wanted = [c for c in ("id", "kind", "org_id", "label", "created_at", "last_used_at",
                          "revoked_at") if c in have]
    order = "kind, org_id, created_at" if {"kind", "org_id", "created_at"} <= have else wanted[0]
    rows = db.execute(text(f"SELECT {', '.join(wanted)} FROM console_credentials ORDER BY {order}"))
    return {"table": True, "rows": [dict(zip(wanted, r, strict=True)) for r in rows]}


def database_report(db, source: str) -> dict:
    return {
        "source": source,
        "clinic": clinic_report(db),
        "sports": sports_report(db),
        "personal": personal_report(db),
        "console_credentials": credentials_report(db),
    }


# --------------------------------------------------------------------------
# the AWS half — every call read-only, every failure a line in the report
# --------------------------------------------------------------------------


def _error(e: Exception) -> str:
    code = getattr(e, "response", {}).get("Error", {}).get("Code") if hasattr(e, "response") else None
    return code or type(e).__name__


def stack_outputs(stack: str, region: str | None) -> dict:
    """Outputs and the DemoMode parameter of one stack, or {} when it is not there."""
    import boto3

    cfn = boto3.client("cloudformation", region_name=region)
    stacks = cfn.describe_stacks(StackName=stack)["Stacks"]
    if not stacks:
        return {}
    s = stacks[0]
    return {
        "status": s.get("StackStatus"),
        "params": {p["ParameterKey"]: p["ParameterValue"] for p in s.get("Parameters", [])},
        "tags": {t["Key"]: t["Value"] for t in s.get("Tags", [])},
        **{o["OutputKey"]: o["OutputValue"] for o in s.get("Outputs", [])},
    }


def aws_report(stack: str, region: str | None, stack_info: dict | None = None) -> dict:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    session = boto3.session.Session(region_name=region)
    region = session.region_name or "us-east-1"
    out: dict = {"stack": stack, "region": region}

    def attempt(name, fn):
        try:
            out[name] = fn()
        except (ClientError, BotoCoreError) as e:
            out[name] = {"error": _error(e)}

    account = session.client("sts").get_caller_identity()["Account"]
    out["account"] = account

    info = stack_info if stack_info is not None else stack_outputs(stack, region)
    if not info:
        out["stack_found"] = False
        return out
    out["stack_found"] = True
    out["status"] = info.get("status")
    demo = info.get("params", {}).get("DemoMode", "false")
    out["demo_mode"] = demo
    out["deployment"] = "demo" if demo == "true" else "real"
    out["stack_tags"] = info.get("tags", {})
    out["site"] = info.get("SiteUrl")

    s3 = session.client("s3", region_name=region)

    def bucket(name: str) -> dict:
        row: dict = {"name": name}
        try:
            rules = s3.get_bucket_encryption(Bucket=name)["ServerSideEncryptionConfiguration"]["Rules"]
            default = rules[0].get("ApplyServerSideEncryptionByDefault", {}) if rules else {}
            row["encryption"] = default.get("SSEAlgorithm")
            row["kms_key"] = default.get("KMSMasterKeyID")
            row["bucket_key"] = rules[0].get("BucketKeyEnabled") if rules else None
        except (ClientError, BotoCoreError) as e:
            row["encryption"] = f"error: {_error(e)}"
        try:
            row["tags"] = {t["Key"]: t["Value"] for t in s3.get_bucket_tagging(Bucket=name)["TagSet"]
                           if not t["Key"].startswith("aws:")}
        except ClientError as e:
            row["tags"] = {} if _error(e) == "NoSuchTagSet" else {"error": _error(e)}
        return row

    buckets = {
        "clinic": info.get("DataBucketName"),
        "personal": info.get("PersonalDataBucketName"),
        "artifacts (code)": f"{stack}-artifacts-{account}-{region}",
    }
    out["buckets"] = {facet: bucket(name) for facet, name in buckets.items() if name}

    def keys() -> list[dict]:
        kms = session.client("kms", region_name=region)
        rows = []
        for page in kms.get_paginator("list_aliases").paginate():
            for alias in page["Aliases"]:
                if not alias["AliasName"].startswith(f"alias/{stack}-"):
                    continue
                key_id = alias.get("TargetKeyId")
                row = {"alias": alias["AliasName"], "key_id": key_id}
                try:
                    meta = kms.describe_key(KeyId=key_id)["KeyMetadata"]
                    row["state"] = meta.get("KeyState")
                    row["rotation"] = kms.get_key_rotation_status(KeyId=key_id).get("KeyRotationEnabled")
                except (ClientError, BotoCoreError) as e:
                    row["state"] = f"error: {_error(e)}"
                rows.append(row)
        return rows

    attempt("kms_aliases", keys)

    def parameters() -> list[str]:
        ssm = session.client("ssm", region_name=region)
        names = []
        for page in ssm.get_paginator("describe_parameters").paginate(
            ParameterFilters=[{"Key": "Name", "Option": "BeginsWith", "Values": [f"/{stack}/"]}]
        ):
            names.extend(p["Name"] for p in page["Parameters"])
        return sorted(names)

    attempt("ssm_parameters", parameters)

    def guardduty() -> dict:
        gd = session.client("guardduty", region_name=region)
        ids = gd.list_detectors().get("DetectorIds", [])
        if not ids:
            return {"detector": None}
        status = gd.get_detector(DetectorId=ids[0]).get("Status")
        return {"detector": ids[0], "status": status}

    attempt("guardduty", guardduty)

    def trails() -> list[dict]:
        ct = session.client("cloudtrail", region_name=region)
        ours = {arn for arn in (
            f"arn:aws:s3:::{buckets['clinic']}/" if buckets.get("clinic") else None,
            f"arn:aws:s3:::{buckets['personal']}/" if buckets.get("personal") else None,
        ) if arn}
        rows = []
        for t in ct.describe_trails().get("trailList", []):
            row = {
                "name": t.get("Name"), "bucket": t.get("S3BucketName"), "prefix": t.get("S3KeyPrefix"),
                "validation": t.get("LogFileValidationEnabled"),
                "multi_region": t.get("IsMultiRegionTrail"),
            }
            try:
                row["logging"] = ct.get_trail_status(Name=t["TrailARN"]).get("IsLogging")
                selectors = ct.get_event_selectors(TrailName=t["TrailARN"])
                values = {
                    v for s in selectors.get("EventSelectors", [])
                    for d in s.get("DataResources", []) for v in d.get("Values", [])
                }
                row["management_events"] = any(
                    s.get("IncludeManagementEvents") for s in selectors.get("EventSelectors", [])
                ) or bool(selectors.get("AdvancedEventSelectors"))
                row["covers_data_buckets"] = sorted(ours & values) if ours else []
            except (ClientError, BotoCoreError) as e:
                row["logging"] = f"error: {_error(e)}"
            rows.append(row)
        return rows

    attempt("cloudtrail", trails)

    def budgets() -> list[dict]:
        b = session.client("budgets", region_name="us-east-1")
        return [
            {"name": x["BudgetName"], "limit": f"{x['BudgetLimit']['Amount']} {x['BudgetLimit']['Unit']}",
             "unit": x.get("TimeUnit")}
            for x in b.describe_budgets(AccountId=account).get("Budgets", [])
        ]

    attempt("budgets", budgets)
    return out


# --------------------------------------------------------------------------
# printing
# --------------------------------------------------------------------------


def _counts(c: dict) -> str:
    return (f"{c['patients']:>4} patients   {c['with_phone']:>4} with a phone   "
            f"{c['signed_in']:>4} signed in   {c['consented']:>4} consented")


def _when(value) -> str:
    if value is None:
        return "-"
    return str(value)[:16]


def print_report(report: dict) -> None:
    db = report.get("database")
    if db:
        print(f"Database: {db['source']}")
        print("\n== clinic (hospitals and their patients) ==")
        for h in db["clinic"]["hospitals"]:
            flags = [] if h["active"] else ["inactive"]
            if h["legacy_token"]:
                flags.append("legacy dashboard token set")
            suffix = f"  [{', '.join(flags)}]" if flags else ""
            print(f"  {h['id']:<22} {h['name']} ({h['city']}){suffix}")
            print(f"  {'':<22} {_counts(h)}")
        none = db["clinic"]["no_hospital"]
        if none["patients"]:
            print(f"  {'(no hospital)':<22} {_counts(none)}")
        if not db["clinic"]["hospitals"] and not none["patients"]:
            print("  no clinic charts")

        print("\n== sports (organisations, teams, athletes) ==")
        for org in db["sports"]["orgs"]:
            code = "join code set" if org["join_code"] else "no join code"
            print(f"  {org['id']:<22} {org['name']} ({org['kind']}, {org['level']}; "
                  f"{org['staff']} staff; {code})")
            print(f"  {'':<22} {_counts(org['athletes'])}")
            for t in org["teams"]:
                print(f"    {t['id']:<20} {t['name']} ({t['sport']}, {t['season']})")
                print(f"    {'':<20} {_counts(t)}")
            if org["no_team"]:
                print(f"    {'(no team)':<20} {org['no_team']} athletes")
        un = db["sports"]["unaffiliated"]
        if un["patients"]:
            print(f"  {'(no organisation)':<22} {_counts(un)}")
        if not db["sports"]["orgs"] and not un["patients"]:
            print("  no sports accounts")

        p = db["personal"]
        print("\n== personal (subscribers) ==")
        print(f"  {_counts(p)}")
        print(f"  {p['paired_to_chart']:>6} paired to a clinic chart (linked_patient_id)   "
              f"{p['with_login']:>4} with an email login   {p['entitled_now']:>4} entitled now")

        c = db["console_credentials"]
        print("\n== console credentials ==")
        if not c["table"]:
            print("  no console_credentials table in this database (one shared token, or none)")
        elif not c["rows"]:
            print("  table present, no credentials issued")
        else:
            print(f"  {'id':<5} {'kind':<11} {'org':<16} {'label':<24} "
                  f"{'created':<17} {'last used':<17} revoked")
            for r in c["rows"]:
                print(f"  {str(r.get('id', '')):<5} {str(r.get('kind', '')):<11} "
                      f"{str(r.get('org_id') or '-'):<16} {str(r.get('label', ''))[:24]:<24} "
                      f"{_when(r.get('created_at')):<17} {_when(r.get('last_used_at')):<17} "
                      f"{_when(r.get('revoked_at'))}")

    aws = report.get("aws")
    if aws is None:
        return
    print("\n== AWS ==")
    if "unreachable" in aws:
        print(f"  not reachable: {aws['unreachable']}")
        return
    print(f"  account {aws['account']}, region {aws['region']}, stack {aws['stack']}", end="")
    if not aws.get("stack_found"):
        print(" — no such stack")
        return
    print(f" ({aws['status']})")
    print(f"  deployment: {aws['deployment']} (DemoMode={aws['demo_mode']})   site: {aws.get('site')}")
    tags = aws.get("stack_tags") or {}
    print(f"  stack tags: {', '.join(f'{k}={v}' for k, v in sorted(tags.items())) or 'none'}")
    print("  buckets:")
    for facet, b in aws["buckets"].items():
        enc = b.get("encryption")
        if enc == "aws:kms":
            enc = f"SSE-KMS {b.get('kms_key')} (bucket key {'on' if b.get('bucket_key') else 'off'})"
        elif enc == "AES256":
            enc = "SSE-S3"
        t = b.get("tags") or {}
        tag_text = ", ".join(f"{k}={v}" for k, v in sorted(t.items())) or "no medpull tags"
        print(f"    {facet:<17} {b['name']}")
        print(f"    {'':<17} {enc}; {tag_text}")
    print("  kms aliases:")
    aliases = aws.get("kms_aliases")
    if isinstance(aliases, dict):
        print(f"    error: {aliases['error']}")
    elif not aliases:
        print(f"    none under alias/{aws['stack']}-* (deploy the current template)")
    else:
        for k in aliases:
            print(f"    {k['alias']:<40} {k['key_id']}  {k.get('state')}  "
                  f"rotation {'on' if k.get('rotation') else 'off'}")
    params = aws.get("ssm_parameters")
    if isinstance(params, dict):
        print(f"  ssm parameters: error: {params['error']}")
    else:
        print(f"  ssm parameters under /{aws['stack']}/: {len(params)}")
        for name in params:
            print(f"    {name}")
    gd = aws.get("guardduty", {})
    if "error" in gd:
        print(f"  guardduty: error: {gd['error']}")
    elif gd.get("detector"):
        print(f"  guardduty: detector {gd['detector']} ({gd.get('status')})")
    else:
        print("  guardduty: no detector (infra/account.sh)")
    trails = aws.get("cloudtrail")
    if isinstance(trails, dict):
        print(f"  cloudtrail: error: {trails['error']}")
    elif not trails:
        print("  cloudtrail: no trail")
    else:
        print("  cloudtrail:")
        for t in trails:
            covers = t.get("covers_data_buckets")
            cover_text = (f"data events for {len(covers)} of the stack's buckets" if covers
                          else "no data events for the stack's buckets")
            print(f"    {t['name']:<28} -> s3://{t['bucket']}/{t.get('prefix') or ''}")
            print(f"    {'':<28} logging {t.get('logging')}, validation {t.get('validation')}, "
                  f"multi-region {t.get('multi_region')}, management events "
                  f"{t.get('management_events')}, {cover_text}")
    budgets = aws.get("budgets")
    if isinstance(budgets, dict):
        print(f"  budgets: error: {budgets['error']}")
    elif not budgets:
        print("  budgets: none (BUDGET_EMAIL at deploy time)")
    else:
        for b in budgets:
            print(f"  budget: {b['name']} {b['limit']} {b.get('unit')}")


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    where = ap.add_mutually_exclusive_group()
    where.add_argument("--bucket", help="S3 bucket holding db/recovery.db (downloaded, read-only)")
    where.add_argument("--local", help="a SQLite file, opened read-only")
    ap.add_argument("--stack", help="CloudFormation stack to describe; also names the bucket when "
                                    "neither --bucket nor --local is given")
    ap.add_argument("--db-key", default=DB_KEY)
    ap.add_argument("--region", default=None, help="AWS region (default: the CLI's)")
    ap.add_argument("--json", action="store_true", help="the report as JSON instead of text")
    args = ap.parse_args()
    if not (args.bucket or args.local or args.stack):
        ap.error("one of --local, --bucket or --stack is required")

    _quiet_environment()
    report: dict = {}
    stack_info: dict | None = None

    # AWS first, when asked: the stack names the bucket, and a missing
    # credential chain is reported rather than raised.
    aws_unreachable: str | None = None
    if args.stack:
        try:
            stack_info = stack_outputs(args.stack, args.region)
        except Exception as e:  # noqa: BLE001 — every reason AWS is out of reach ends up here
            aws_unreachable = _error(e)
            stack_info = None

    bucket = args.bucket
    if not bucket and not args.local and args.stack:
        if aws_unreachable:
            print(f"AWS not reachable ({aws_unreachable}); pass --local or --bucket for the database",
                  file=sys.stderr)
            return 2
        bucket = (stack_info or {}).get("DataBucketName")
        if not bucket:
            print(f"stack {args.stack} has no DataBucketName output (does it exist?)", file=sys.stderr)
            return 2

    # app.database binds the engine at import, so the environment comes first.
    workdir = None
    if bucket:
        workdir = tempfile.mkdtemp(prefix="medpull-audit-")
        target = Path(workdir) / "recovery.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{target}"
        try:
            _download(bucket, args.db_key, target)
        except Exception as e:  # noqa: BLE001
            print(f"could not download s3://{bucket}/{args.db_key}: {_error(e)}", file=sys.stderr)
            return 2
        source = f"s3://{bucket}/{args.db_key} (copy in {workdir}, read-only, no lock)"
    elif args.local:
        path = Path(args.local).resolve()
        if not path.exists():
            print(f"no such file: {path}", file=sys.stderr)
            return 2
        os.environ["DATABASE_URL"] = f"sqlite:///file:{path}?mode=ro&uri=true"
        source = f"{path} (read-only)"
    else:
        source = None

    if source:
        import app.models  # noqa: F401  (register every table)
        from app.database import SessionLocal

        with SessionLocal() as db:
            report["database"] = database_report(db, source)

    if args.stack:
        if aws_unreachable:
            report["aws"] = {"unreachable": aws_unreachable}
        else:
            try:
                report["aws"] = aws_report(args.stack, args.region, stack_info)
            except Exception as e:  # noqa: BLE001
                report["aws"] = {"unreachable": _error(e)}

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
