"""Separate operator and worker credentials. Never put worker credentials in the UI."""

import hashlib
import hmac
import json
import re
import time

from fastapi import HTTPException, Request

from src.config import get_settings

COOKIE = "p027_experiment_access"


def session_value(expires):
    digest = hmac.new(get_settings().experiment_access_token.encode(), str(expires).encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{digest}"


def operator_authenticated(request: Request):
    key = get_settings().experiment_access_token
    if not key:
        return False
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer ") and hmac.compare_digest(authorization[7:], key):
        return True
    cookie = request.cookies.get(COOKIE, "")
    try:
        expires = int(cookie.split(".", 1)[0])
    except ValueError:
        return False
    return time.time() < expires <= time.time() + 86400 and hmac.compare_digest(cookie, session_value(expires))


def require_operator(request: Request):
    settings = get_settings()
    if settings.experiment_execution_mode == "remote" and len(settings.experiment_access_token) < 32:
        raise HTTPException(503, "Remote experiments require an operator access token of at least 32 characters")
    if settings.experiment_access_token and not operator_authenticated(request):
        raise HTTPException(401, "Experiment access required")


def authenticate_worker(request: Request):
    settings = get_settings()
    if settings.experiment_execution_mode != "remote" or not settings.experiment_api_enabled_in_production and settings.app_env == "production":
        raise HTTPException(503, "Remote workers are disabled")
    worker = request.headers.get("x-worker-id", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", worker):
        raise HTTPException(401, "Invalid worker identity")
    try:
        tokens = json.loads(settings.remote_worker_tokens)
    except ValueError as exc:
        raise HTTPException(503, "Worker authentication is not configured") from exc
    expected = tokens.get(worker) if isinstance(tokens, dict) else None
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
    if not isinstance(expected, str) or len(expected) < 32 or not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, "Invalid worker credentials")
    return worker
