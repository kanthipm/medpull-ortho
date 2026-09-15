"""apple-app-site-association — lets iOS open https task links straight in
the MedPull app once the app's entitlement lists this host. Served only when
IOS_TEAM_ID is set, because an association file naming a team that has not
shipped the app is noise. Mounted at the site root, outside /api; on AWS,
where only /api/* reaches the function, the same JSON must be uploaded to
the SPA bucket under /.well-known/ (infra/README.md)."""

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


@router.get("/.well-known/apple-app-site-association")
@router.get("/apple-app-site-association")
def aasa() -> JSONResponse:
    if not settings.ios_team_id:
        raise HTTPException(status_code=404, detail="Not Found")
    return JSONResponse(association(), media_type="application/json")
