from fastapi import APIRouter

from app.api import system

api_router = APIRouter(prefix="/api")
api_router.include_router(system.router)

# Routers added as they are built (worklist, patients, notifications,
# integrations, webhooks) are wired here.
try:  # pragma: no cover - wiring
    from app.api import ask, integrations, notifications, patients, rtm, webhooks, worklist

    api_router.include_router(worklist.router)
    api_router.include_router(patients.router)
    api_router.include_router(notifications.router)
    api_router.include_router(integrations.router)
    api_router.include_router(webhooks.router)
    api_router.include_router(ask.router)
    api_router.include_router(rtm.router)
except ImportError:
    pass
