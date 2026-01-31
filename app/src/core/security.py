"""Security utilities for JWT tokens and password hashing."""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple
import bcrypt
import uuid
from jose import JWTError, jwt
from src.core.config import get_settings
from src.core.exceptions import AuthenticationError

JWT_ALGORITHM = "HS256"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    settings = get_settings()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=settings.jwt_access_token_expire_hours))
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "access"})
    return jwt.encode(to_encode, settings.secret_key, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> Tuple[str, str, datetime]:
    """Returns (encoded_jwt, jti, expiration_datetime)."""
    to_encode = data.copy()
    jti = str(uuid.uuid4())
    settings = get_settings()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=settings.jwt_refresh_token_expire_days))
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "refresh", "jti": jti})
    encoded = jwt.encode(to_encode, settings.secret_key, algorithm=JWT_ALGORITHM)
    return encoded, jti, expire


def decode_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=[JWT_ALGORITHM])
    except JWTError as e:
        raise AuthenticationError(f"Invalid token: {str(e)}")


def verify_token_type(payload: Dict[str, Any], expected_type: str) -> bool:
    token_type = payload.get("type")
    if token_type != expected_type:
        raise AuthenticationError(f"Invalid token type. Expected {expected_type}, got {token_type}")
    return True
