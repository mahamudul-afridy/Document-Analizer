"""Authentication: login, refresh (httpOnly cookie), logout, first-run setup, profile."""
import uuid
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.ratelimit import limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models import Role, User
from app.db.session import get_db
from app.schemas.common import LoginIn, ProfileUpdate, SetupIn, TokenOut, UserOut
from app.services.audit import audit

router = APIRouter(prefix="/auth", tags=["Authentication"])
COOKIE = "dm_refresh"


def _is_https(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def _issue(user: User, request: Request, response: Response) -> TokenOut:
    response.set_cookie(COOKIE, create_refresh_token(str(user.id)), httponly=True, samesite="strict",
                        secure=_is_https(request), max_age=settings.jwt_refresh_ttl_days * 86400,
                        path="/api/v1/auth")
    return TokenOut(access_token=create_access_token(str(user.id), user.role.value),
                    expires_in=settings.jwt_access_ttl_min * 60, user=UserOut.model_validate(user))


@router.get("/setup-status")
def setup_status(db: Session = Depends(get_db)):
    """Whether the first admin account still needs to be created (fresh install)."""
    return {"needs_setup": db.scalar(select(func.count()).select_from(User)) == 0}


@router.post("/setup", response_model=TokenOut)
@limiter.limit("5/minute")
def setup(request: Request, response: Response, body: SetupIn, db: Session = Depends(get_db)):
    """Create the first admin. Only works while there are no users."""
    if db.scalar(select(func.count()).select_from(User)) > 0:
        raise HTTPException(409, "Setup has already been completed")
    user = User(email=body.email.lower(), full_name=body.full_name, password_hash=hash_password(body.password),
                role=Role.admin, last_login_at=datetime.now(timezone.utc))
    db.add(user)
    db.flush()
    audit(db, "auth.setup", user=user, entity_type="user", entity_id=user.id, request=request)
    db.commit()
    return _issue(user, request, response)


@router.post("/login", response_model=TokenOut)
@limiter.limit(settings.rate_limit_login)
def login(request: Request, response: Response, body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        audit(db, "auth.login_failed", request=request, details={"email": body.email})
        db.commit()
        raise HTTPException(401, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(403, "Account is disabled")
    user.last_login_at = datetime.now(timezone.utc)
    audit(db, "auth.login", user=user, entity_type="user", entity_id=user.id, request=request)
    db.commit()
    return _issue(user, request, response)


@router.post("/refresh", response_model=TokenOut)
@limiter.limit("30/minute")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "No refresh token")
    try:
        payload = decode_token(token, "refresh")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid refresh token")
    user = db.get(User, uuid.UUID(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(401, "User not available")
    return _issue(user, request, response)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/api/v1/auth")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdate, request: Request, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.new_password:
        if not body.current_password or not verify_password(body.current_password, user.password_hash):
            raise HTTPException(400, "Current password is incorrect")
        user.password_hash = hash_password(body.new_password)
        audit(db, "auth.password_changed", user=user, entity_type="user", entity_id=user.id, request=request)
    db.add(user)
    db.commit()
    return user
