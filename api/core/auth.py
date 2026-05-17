"""JWT Authentication for SKULD API."""

import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from api.core.config import settings

ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# User passwords from environment (fallback to secure defaults)
_ADMIN_PASSWORD = os.getenv("SKULD_ADMIN_PASSWORD", "Kx9$mTr!vQ4pNw2z")
_VIEWER_PASSWORD = os.getenv("SKULD_VIEWER_PASSWORD", "Vw7#hLs@jR3bYf8x")

# Simple user store - in production, move to DB
USERS = {
    "admin": {
        "username": "admin",
        "hashed_password": pwd_context.hash(_ADMIN_PASSWORD),
        "role": "admin",
    },
    "viewer": {
        "username": "viewer",
        "hashed_password": pwd_context.hash(_VIEWER_PASSWORD),
        "role": "viewer",
    },
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = USERS.get(username)
    if user is None:
        raise credentials_exception
    return user
