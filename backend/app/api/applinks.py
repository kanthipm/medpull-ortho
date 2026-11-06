"""The two files that let a phone open https task links straight in the app:
apple-app-site-association for iOS (once the app's entitlement lists this
host) and assetlinks.json for Android App Links. Each is served only when
its platform's identity is configured, because an association file naming
an app that has not shipped is noise. Mounted at the site root, outside
/api; on AWS, where only /api/* reaches the function, deploy.sh uploads the
same JSON beside the SPA and the CloudFront rewrite exempts /.well-known/."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.config import settings

router = APIRouter(include_in_schema=False)


def association() -> dict:
    app_id = f"{settings.ios_team_id}.{settings.ios_bundle_id}"
    return {
        "applinks": {
            "details": [{"appIDs": [app_id], "components": [{"/": "/t/*"}]}],
        },
        "webcredentials": {"apps": [app_id]},
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
    if not settings.ios_team_id:
        raise HTTPException(status_code=404, detail="Not Found")
    return JSONResponse(association(), media_type="application/json")


@router.get("/.well-known/assetlinks.json")
def assetlinks() -> JSONResponse:
    if not settings.android_cert_sha256.strip():
        raise HTTPException(status_code=404, detail="Not Found")
    return JSONResponse(asset_links(), media_type="application/json")
