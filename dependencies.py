# dependencies.py
# JWT authentication utilities for FastAPI Depends injection

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

SECRET_KEY         = os.getenv("JWT_SECRET_KEY", "carboniq-dev-secret-2026-change-in-prod")
ALGORITHM          = "HS256"
TOKEN_EXPIRE_DAYS  = 7

_security = HTTPBearer(auto_error=False)


def create_access_token(user_id: int, email: str, secteur: str = "") -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": str(user_id), "email": email, "secteur": secteur or "", "exp": expire},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def _decode(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_security),
) -> dict:
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = _decode(creds.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
        )
    return {
        "user_id": int(payload["sub"]),
        "email":   payload["email"],
        "secteur": payload.get("secteur", ""),
    }


def get_optional_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_security),
) -> Optional[dict]:
    """Returns user dict if valid token present, else None."""
    if not creds:
        return None
    payload = _decode(creds.credentials)
    if not payload:
        return None
    return {
        "user_id": int(payload["sub"]),
        "email":   payload["email"],
        "secteur": payload.get("secteur", ""),
    }
