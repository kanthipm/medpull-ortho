from fastapi import APIRouter, Depends

from app.api import (
    apple_notifications,
    ask,
    attachments,
    auth,
    care,
    checkin,
    explain,
    integrations,
    mobile,
    mobility,
    narratives,
    notifications,
    overview,
    patients,
    plan,
    sendblue_webhook,
    system,
    webhooks,
    worklist,
)
from app.api.auth import require_console
from app.hep import api as hep
from app.personal import api as personal
from app.sports import api as sports

api_router = APIRouter(prefix="/api")

# Imported at module scope on purpose. A router that fails to import must take
# the process down: swallowing the ImportError leaves every one of its routes to
# the SPA catch-all, which answers 200 text/html with no log line anywhere.
#
# Console routers sit behind the console's door (app/api/auth.py): the staff
# token or a minted org credential, waived only while the console is open.
# Every route behind it reads the resolved ConsoleScope and narrows itself to
# it (app/api/scope.py). Everything a patient, a phone or a provider's
# webhook reaches has its own credential and is wired without it.
CONSOLE = [Depends(require_console)]

api_router.include_router(system.router)
api_router.include_router(auth.router, dependencies=CONSOLE)
api_router.include_router(worklist.router, dependencies=CONSOLE)
api_router.include_router(patients.router, dependencies=CONSOLE)
api_router.include_router(overview.router, dependencies=CONSOLE)
api_router.include_router(notifications.router, dependencies=CONSOLE)
api_router.include_router(integrations.router, dependencies=CONSOLE)
api_router.include_router(webhooks.router)
api_router.include_router(apple_notifications.router)
api_router.include_router(ask.router, dependencies=CONSOLE)
api_router.include_router(checkin.router)
api_router.include_router(checkin.console_router, dependencies=CONSOLE)
api_router.include_router(mobile.router)
api_router.include_router(mobile.public_router)
api_router.include_router(mobility.router)
api_router.include_router(sendblue_webhook.router)
api_router.include_router(care.router, dependencies=CONSOLE)
api_router.include_router(explain.router, dependencies=CONSOLE)
api_router.include_router(narratives.router, dependencies=CONSOLE)
api_router.include_router(plan.router, dependencies=CONSOLE)
api_router.include_router(hep.router, dependencies=CONSOLE)
api_router.include_router(attachments.router)
api_router.include_router(attachments.console_router, dependencies=CONSOLE)
api_router.include_router(personal.router)
api_router.include_router(sports.router)
api_router.include_router(sports.team_router, dependencies=CONSOLE)
