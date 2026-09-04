import hmac
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings


def verify_password(password: str) -> bool:
    expected = settings.admin_password
    return hmac.compare_digest(str(password).encode(), expected.encode())


def create_admin_token() -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "admin",
        "scope": "admin",
        "iat": now,
        "exp": now + timedelta(hours=12),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_admin_token(token: str) -> bool:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        return payload.get("scope") == "admin"
    except Exception:
        return False
