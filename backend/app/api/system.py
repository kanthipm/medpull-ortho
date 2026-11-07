from fastapi import APIRouter
from sqlalchemy import text

from app.api.auth import console_auth_enabled
from app.config import settings
from app.database import engine
from app.llm.provider import model_name, provider_name
from app.notifications import sendblue

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "ok",
        "db_ok": db_ok,
        # Tells the SPA whether to ask for the console token before loading.
        "console_auth": console_auth_enabled(),
        # The public demo or the real app; the console keys its demo-only
        # surfaces on this rather than on a hostname.
        "demo": settings.demo_mode,
        # The console shows the Exercise Plans nav only while this is on.
        "hep": settings.hep_enabled,
        "llm_provider": provider_name(),
        "model": model_name(),
        # Keys present is not the same as able to send: the sending number has
        # to be one Sendblue issued to the account. `config_fault` carries the
        # provider's own words once a send in this process has hit that.
        "sms": sendblue.status(),
    }
