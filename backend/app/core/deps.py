"""FastAPI dependencies: current user (JWT or API key) and role checks."""
import uuid
from datetime import datetime, timezone

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_token, hash_api_key
from app.db.models import ApiKey, Role, User
from app.db.session import get_db

bearer = HTTPBearer(auto_error=False)

ROLE_RANK = {Role.viewer: 0, Role.reviewer: 1, Role.admin: 2}


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail,
                         headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    user: User | None = None

    if x_api_key:
        key = db.scalar(select(ApiKey).where(ApiKey.key_hash == hash_api_key(x_api_key), ApiKey.revoked_at.is_(None)))
        if not key:
            raise _unauthorized("Invalid API key")
        key.last_used_at = datetime.now(timezone.utc)
        db.commit()
        user = key.user
    elif creds:
        try:
            payload = decode_token(creds.credentials, "access")
        except jwt.ExpiredSignatureError:
            raise _unauthorized("Token expired")
        except jwt.InvalidTokenError:
            raise _unauthorized("Invalid token")
        user = db.get(User, uuid.UUID(payload["sub"]))
    else:
        # SSE (EventSource) cannot send headers: allow ?token= for GET streams only
        token = request.query_params.get("token")
        if token and request.method == "GET":
            try:
                payload = decode_token(token, "access")
                user = db.get(User, uuid.UUID(payload["sub"]))
            except jwt.InvalidTokenError:
                raise _unauthorized("Invalid token")

    if not user:
        raise _unauthorized()
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is disabled")
    request.state.user_id = str(user.id)
    return user


def require_role(minimum: Role):
    def checker(user: User = Depends(get_current_user)) -> User:
        if ROLE_RANK[user.role] < ROLE_RANK[minimum]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Requires role '{minimum.value}' or higher")
        return user

    return checker


require_reviewer = require_role(Role.reviewer)
require_admin = require_role(Role.admin)
