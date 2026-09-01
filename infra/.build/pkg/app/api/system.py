from fastapi import APIRouter
from sqlalchemy import text

from app.database import engine
from app.llm.provider import model_name, provider_name

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
    }
