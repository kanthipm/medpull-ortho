from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.capabilities import CAPABILITIES, GAIT
from app.connectors.registry import PROVIDERS, get_provider_info
from app.database import get_db
from app.models.enums import SourceProvider
from app.models.patient import Device

router = APIRouter(tags=["integrations"])


@router.get("/integrations")
def list_integrations(db: Session = Depends(get_db)) -> dict:
    device_counts = dict(
        db.execute(select(Device.source_provider, func.count(Device.id)).group_by(Device.source_provider)).all()
    )
    providers = []
    for info in PROVIDERS:
        capabilities = CAPABILITIES.get(info.key, [])
        providers.append(
            {
                "key": str(info.key),
                "name": info.name,
                "status": info.status,
                "capabilities": [str(m) for m in capabilities],
                "connected_patients": int(device_counts.get(info.key, 0)),
                "gait_capable": any(m in capabilities for m in GAIT),
            }
        )
    return {"providers": providers}


@router.post("/integrations/{provider}/connect")
def connect(provider: str) -> dict:
    try:
        key = SourceProvider(provider)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
    info = get_provider_info(key)
    if info is None or info.connector is None:
        raise HTTPException(
            status_code=501,
            detail=f"{info.name if info else provider} integration is scaffolded but not yet implemented.",
        )
    return {"status": info.status}
