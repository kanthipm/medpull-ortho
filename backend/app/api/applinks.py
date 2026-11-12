"""The two files that let a phone open https links straight in the app:
apple-app-site-association for iOS (once the app's entitlement lists this
host) and assetlinks.json for Android App Links. Each is served only when
its platform's identity is configured, because an association file naming
an app that has not shipped is noise. Mounted at the site root, outside
/api; on AWS, where only /api/* reaches the function, deploy.sh uploads the
same JSON beside the SPA and the CloudFront rewrite exempts /.well-known/.

The iOS file names every app that may open this host's links: the patient
app (``IOS_TEAM_ID`` + ``IOS_BUNDLE_ID``) and any listed in
``IOS_LINK_APP_IDS``. The demo stack sets only the second, so the demo app
is the one that opens its links and a phone carrying both apps never has
two contending for a path. ``IOS_LINK_PATHS`` are the paths they open: the
task link (``/t/*``) and the links a text carries (``/a/*``, app/links.py).
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.config import settings

router = APIRouter(include_in_schema=False)

# What an empty IOS_LINK_PATHS means: a file that claims no path opens
# nothing, which is never what a deployment that names an app intends.
DEFAULT_LINK_PATHS = ("/t/*", "/a/*")


def _listed(raw: str) -> list[str]:
    """A comma-separated setting as its entries, in order, without repeats."""
    return list(dict.fromkeys(part.strip() for part in (raw or "").split(",") if part.strip()))


def app_ids() -> list[str]:
    """Every iOS app id ("<TEAMID>.<bundle id>") this host's links may open."""
    team, bundle = settings.ios_team_id.strip(), settings.ios_bundle_id.strip()
    own = [f"{team}.{bundle}"] if team and bundle else []
    return list(dict.fromkeys([*own, *_listed(settings.ios_link_app_ids)]))


def link_paths() -> list[str]:
    return _listed(settings.ios_link_paths) or list(DEFAULT_LINK_PATHS)


def association() -> dict:
    ids = app_ids()
    return {
        "applinks": {
            "details": [{"appIDs": ids, "components": [{"/": path} for path in link_paths()]}],
        },
        "webcredentials": {"apps": ids},
    }


def asset_links() -> list[dict]:
    fingerprints = [f.strip().upper() for f in settings.android_cert_sha256.split(",") if f.strip()]
    return [{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app",
            "package_name": settings.android_package,
            "sha256_cert_fingerprints": fingerprints,
        },
    }]


@router.get("/.well-known/apple-app-site-association")
@router.get("/apple-app-site-association")
def aasa() -> JSONResponse:
    if not app_ids():
        raise HTTPException(status_code=404, detail="Not Found")
    return JSONResponse(association(), media_type="application/json")


@router.get("/.well-known/assetlinks.json")
def assetlinks() -> JSONResponse:
    if not settings.android_cert_sha256.strip():
        raise HTTPException(status_code=404, detail="Not Found")
    return JSONResponse(asset_links(), media_type="application/json")
