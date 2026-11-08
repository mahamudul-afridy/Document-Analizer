"""Password hashing, JWT tokens, API keys and secret encryption."""
import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_hasher = PasswordHasher()
ALGORITHM = "HS256"


# ---------- passwords ----------
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, Exception):
        return False


# ---------- JWT ----------
def _create_token(subject: str, token_type: str, ttl: timedelta, extra: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
        "jti": uuid.uuid4().hex,
        **(extra or {}),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: str, role: str) -> str:
    return _create_token(user_id, "access", timedelta(minutes=settings.jwt_access_ttl_min), {"role": role})


def create_refresh_token(user_id: str) -> str:
    return _create_token(user_id, "refresh", timedelta(days=settings.jwt_refresh_ttl_days))


def decode_token(token: str, expected_type: str) -> dict:
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    return payload


# ---------- API keys ----------
API_KEY_PREFIX = "dm_"


def generate_api_key() -> tuple[str, str, str]:
    """Returns (full_key, prefix_for_display, sha256_hash)."""
    raw = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return raw, raw[:10], hash_api_key(raw)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


# ---------- secret encryption (LLM API keys stored in DB) ----------
def _fernet() -> Fernet:
    digest = hashlib.sha256(("documind-secrets:" + settings.secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "••••"
    return f"{value[:4]}…{value[-4:]}"
