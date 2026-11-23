from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import get_settings

# auto_error=False + no WWW-Authenticate: browser must not steal the SPA login form
# with a native Basic dialog when /api/* returns 401.
security = HTTPBasic(auto_error=False)


def require_basic_auth(
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> str:
    settings = get_settings()
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    user_ok = secrets.compare_digest(credentials.username, settings.app_basic_user)
    pass_ok = secrets.compare_digest(credentials.password, settings.app_basic_password)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return credentials.username
