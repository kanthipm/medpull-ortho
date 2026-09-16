from fastapi import APIRouter
from sqlalchemy import text

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
        "llm_provider": provider_name(),
        "model": model_name(),
        # Keys present is not the same as able to send: the sending number has
        # to be one Sendblue issued to the account. `config_fault` carries the
        # provider's own words once a send in this process has hit that.
        "sms": sendblue.status(),
    }
