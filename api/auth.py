"""JWT authentication for RouteMonitor API.

Token format: Bearer JWT (HS256)
Payload: {sub: username, role: operator|admin|readonly, exp: unix_timestamp}

Roles:
  readonly  — GET endpoints only
  operator  — GET + POST /anomalies/*/acknowledge
  admin     — all endpoints including DELETE and webhook management
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt

from core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

ROLE_LEVELS = {"readonly": 0, "operator": 1, "admin": 2}


def create_access_token(
    username: str,
    role: str = "operator",
    expires_minutes: int = 60,
) -> str:
    """Create a signed JWT access token."""
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises HTTPException 401 on invalid/expired token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        if payload.get("sub") is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Validate Bearer token and return user dict."""
    payload = decode_token(token)
    return {"username": payload["sub"], "role": payload.get("role", "readonly")}


def require_role(minimum_role: str) -> Callable:
    """Role-based access control dependency factory."""

    async def _check(user: dict = Depends(get_current_user)) -> dict:
        user_level = ROLE_LEVELS.get(user.get("role", "readonly"), 0)
        min_level = ROLE_LEVELS.get(minimum_role, 99)
        if user_level < min_level:
            raise HTTPException(
                status_code=403,
                detail=f"Requires role '{minimum_role}', you have '{user['role']}'",
            )
        return user

    return _check


auth_router = APIRouter(prefix="/api/auth", tags=["auth"])

_USERS = {
    "admin": {"password": "admin123", "role": "admin"},
    "operator": {"password": "operator123", "role": "operator"},
    "readonly": {"password": "readonly123", "role": "readonly"},
}


@auth_router.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> dict:
    """POST /api/auth/token — exchange username+password for Bearer token."""
    user = _USERS.get(form_data.username)
    if not user or user["password"] != form_data.password:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(
        username=form_data.username,
        role=user["role"],
    )
    return {"access_token": token, "token_type": "bearer"}


@auth_router.get("/me")
async def whoami(current_user: dict = Depends(get_current_user)) -> dict:
    """GET /api/auth/me — return currently authenticated user info."""
    return current_user
