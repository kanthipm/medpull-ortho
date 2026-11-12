"""See and set where Sendblue delivers inbound texts for a stack.

A reply to a MedPull text (DONE, STOP, a check-in answer) reaches the app
only if Sendblue's account lists this stack's inbound route as a `receive`
webhook: `https://<host>/api/webhooks/sendblue/<webhook secret>`. This
script reads the account's list, adds the stack's own entry when it is
missing, and removes entries that point at hosts that are gone.

    cd backend
    uv run python scripts/sendblue_webhooks.py                       # list
    uv run python scripts/sendblue_webhooks.py --ensure-receive https://demo.medpull.app
    uv run python scripts/sendblue_webhooks.py --remove-host demo.medpull.org --remove-host app.medpull.org
    ... --dry-run                                                    # say what would change, change nothing

The three secrets (API key id, API secret, the webhook's path secret) come
from the stack's SSM parameters (`/<stack>/sendblue-*`, the ones deploy.sh
writes), else from SENDBLUE_API_KEY / SENDBLUE_API_SECRET /
SENDBLUE_WEBHOOK_SECRET in the environment. None is ever printed: a
webhook URL is shown with its secret path segment masked.

Sendblue's API (docs.sendblue.com, "Webhooks"): GET lists, POST appends,
DELETE removes, all on https://api.sendblue.co/api/account/webhooks with
the `sb-api-key-id` and `sb-api-secret-key` headers. An account can hold
several `receive` webhooks; each inbound text is delivered to all of them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

API = "https://api.sendblue.co/api/account/webhooks"
ROUTE = "/api/webhooks/sendblue/"


def _ssm(name: str, region: str) -> str | None:
    try:
        import boto3

        client = boto3.client("ssm", region_name=region)
        return client.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
    except Exception:  # noqa: BLE001 - absent, or no AWS access: fall back to the environment
        return None


def _secret(stack: str, region: str, suffix: str, env: str) -> str:
    value = _ssm(f"/{stack}/{suffix}", region) or os.environ.get(env, "")
    if not value:
        sys.exit(f"no {env}: not in SSM at /{stack}/{suffix} and not in the environment")
    return value


def _call(method: str, key: str, secret: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(
        API,
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={
            "sb-api-key-id": key,
            "sb-api-secret-key": secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace")[:300]
        sys.exit(f"Sendblue answered {err.code} to {method}: {detail}")
    except urllib.error.URLError as err:
        sys.exit(f"could not reach Sendblue: {err.reason}")


def _url_of(entry) -> str:
    return entry if isinstance(entry, str) else str((entry or {}).get("url") or "")


def masked(url: str) -> str:
    """A webhook URL with its path secret hidden: the host and the route are
    what a reader needs, the secret is not theirs to see."""
    parts = urlsplit(url)
    path = parts.path
    if ROUTE in path:
        path = path.split(ROUTE)[0] + ROUTE + "<secret>"
    elif path.count("/") > 3:
        path = path.rsplit("/", 1)[0] + "/<…>"
    return f"{parts.scheme}://{parts.netloc}{path}{'?<query>' if parts.query else ''}"


def show(webhooks: dict) -> None:
    kinds = [k for k in sorted(webhooks) if k != "globalSecret"]
    any_listed = False
    for kind in kinds:
        entries = webhooks.get(kind) or []
        for entry in entries:
            any_listed = True
            scoped = "" if isinstance(entry, str) else (
                f"  (numbers: {', '.join(entry.get('sendblue_numbers') or []) or 'all'})"
                f"{'  (own secret set)' if entry.get('secret') else ''}"
            )
            print(f"  {kind:18s} {masked(_url_of(entry))}{scoped}")
    if not any_listed:
        print("  (no webhooks registered)")
    if webhooks.get("globalSecret"):
        print("  a global signing secret is set")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--stack", default="recovery-copilot", help="the stack whose SSM parameters hold the secrets")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    parser.add_argument("--ensure-receive", metavar="BASE_URL",
                        help="make sure <BASE_URL>/api/webhooks/sendblue/<secret> is a receive webhook")
    parser.add_argument("--remove-host", action="append", default=[], metavar="HOST",
                        help="remove receive webhooks whose host is HOST (repeatable)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    key = _secret(args.stack, args.region, "sendblue-api-key", "SENDBLUE_API_KEY")
    secret = _secret(args.stack, args.region, "sendblue-api-secret", "SENDBLUE_API_SECRET")

    listed = _call("GET", key, secret).get("webhooks") or {}
    print("Registered at Sendblue:")
    show(listed)
    receive = [_url_of(e) for e in (listed.get("receive") or [])]

    changed = False
    if args.remove_host:
        gone = [u for u in receive if urlsplit(u).netloc.lower() in {h.lower() for h in args.remove_host}]
        if not gone:
            print(f"\nNothing to remove: no receive webhook on {', '.join(args.remove_host)}.")
        else:
            print(f"\n{'Would remove' if args.dry_run else 'Removing'} {len(gone)} receive webhook(s):")
            for url in gone:
                print(f"  {masked(url)}")
            if not args.dry_run:
                _call("DELETE", key, secret, {"webhooks": gone, "type": "receive"})
                changed = True

    if args.ensure_receive:
        path_secret = _secret(args.stack, args.region, "sendblue-webhook-secret", "SENDBLUE_WEBHOOK_SECRET")
        want = f"{args.ensure_receive.rstrip('/')}{ROUTE}{path_secret}"
        if want in receive:
            print(f"\nAlready registered: {masked(want)}")
        else:
            same_host = [u for u in receive if urlsplit(u).netloc == urlsplit(want).netloc]
            note = " (another entry on this host carries a different secret; remove it with --remove-host first if it is stale)" if same_host else ""
            print(f"\n{'Would add' if args.dry_run else 'Adding'} {masked(want)}{note}")
            if not args.dry_run:
                _call("POST", key, secret, {"webhooks": [want], "type": "receive"})
                changed = True

    if changed:
        print("\nNow registered:")
        show(_call("GET", key, secret).get("webhooks") or {})


if __name__ == "__main__":
    main()
