"""Operator sign-in uses a signed HttpOnly cookie through the existing Vercel rewrite."""

import hmac
import time

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from src.config import get_settings
from src.services.experiment_auth import COOKIE, session_value

router = APIRouter(prefix="/experiment-access", tags=["experiment-access"])


class AccessRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


@router.post("")
def sign_in(body: AccessRequest, response: Response):
    settings = get_settings()
    if not settings.experiment_api_enabled_in_production and settings.app_env == "production":
        raise HTTPException(503, "Interactive experiments are disabled")
    if len(settings.experiment_access_token) < 32 or not hmac.compare_digest(body.token, settings.experiment_access_token):
        raise HTTPException(401, "Invalid experiment access token")
    expires = int(time.time()) + 8 * 3600
    response.set_cookie(COOKIE, session_value(expires), httponly=True, secure=settings.app_env == "production",
                        samesite="strict", max_age=8 * 3600, path="/api/v1")
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": True}


@router.delete("")
def sign_out(response: Response):
    response.delete_cookie(COOKIE, path="/api/v1")
    return {"authenticated": False}
