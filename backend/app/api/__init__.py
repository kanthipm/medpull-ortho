from fastapi import APIRouter

from app.api import ask, integrations, notifications, patients, rtm, system, webhooks, worklist

api_router = APIRouter(prefix="/api")

# Imported at module scope on purpose. A router that fails to import must take
# the process down: swallowing the ImportError leaves every one of its routes to
# the SPA catch-all, which answers 200 text/html with no log line anywhere.
api_router.include_router(system.router)
api_router.include_router(worklist.router)
api_router.include_router(patients.router)
api_router.include_router(notifications.router)
api_router.include_router(integrations.router)
api_router.include_router(webhooks.router)
api_router.include_router(ask.router)
api_router.include_router(rtm.router)
