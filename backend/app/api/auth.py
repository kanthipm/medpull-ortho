"""The console's door. One shared token, compared in constant time, required
on every console router when CONSOLE_ACCESS_TOKEN is set and waived when it
is empty so the public demo stays open. Patient-app, token-link and webhook
routes have their own credentials and are never behind this."""

import secrets

from fastapi import Header, HTTPException

from app.config import settings


def console_auth_enabled() -> bool:
    return bool(settings.console_access_token)


def require_console(authorization: str | None = Header(default=None)) -> None:
    expected = settings.console_access_token
    if not expected:
        return
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in to the console to continue")
    token = authorization.split(" ", 1)[1].strip()
    if not secrets.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="That access token is not right")
