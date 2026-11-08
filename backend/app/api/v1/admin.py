"""Users (admin), API keys, AI engine settings and audit log."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.llm.providers import LLMError, test_connection
from app.core.config import settings
from app.core.deps import get_current_user, require_admin
from app.core.security import generate_api_key, hash_password
from app.db.models import ApiKey, AuditLog, Role, User
from app.db.session import get_db
from app.processing.ocr import tesseract_available
from app.schemas.common import (
    AISettingsIn,
    AITestIn,
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    Page,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.services.ai_settings import PROVIDERS, load_ai_config, public_view, save_ai_config
from app.services.audit import audit

router = APIRouter(tags=["Administration"])


# ---------------------------------------------------------------- users
@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.scalars(select(User).order_by(User.created_at)).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    if db.scalar(select(User).where(func.lower(User.email) == body.email.lower())):
        raise HTTPException(409, "A user with this email already exists")
    user = User(email=body.email.lower(), full_name=body.full_name, password_hash=hash_password(body.password),
                role=Role(body.role))
    db.add(user)
    db.flush()
    audit(db, "user.created", user=admin, entity_type="user", entity_id=user.id, request=request,
          details={"email": user.email, "role": body.role})
    db.commit()
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, body: UserUpdate, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == admin.id and (body.role not in (None, "admin") or body.is_active is False):
        raise HTTPException(400, "You cannot demote or disable your own account")
    changes = body.model_dump(exclude_unset=True, exclude={"password"})
    for k, v in changes.items():
        setattr(user, k, Role(v) if k == "role" else v)
    if body.password:
        user.password_hash = hash_password(body.password)
        changes["password"] = "reset"
    audit(db, "user.updated", user=admin, entity_type="user", entity_id=user.id, request=request, details=changes)
    db.commit()
    return user


# ---------------------------------------------------------------- API keys
@router.get("/api-keys", response_model=list[ApiKeyOut])
def list_keys(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())).all()


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
def create_key(body: ApiKeyCreate, request: Request, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    raw, prefix, digest = generate_api_key()
    key = ApiKey(user_id=user.id, name=body.name, key_prefix=prefix, key_hash=digest)
    db.add(key)
    db.flush()
    audit(db, "api_key.created", user=user, entity_type="api_key", entity_id=key.id, request=request,
          details={"name": body.name})
    db.commit()
    return ApiKeyCreated(**ApiKeyOut.model_validate(key).model_dump(), key=raw)


@router.delete("/api-keys/{key_id}", response_model=ApiKeyOut)
def revoke_key(key_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    key = db.get(ApiKey, key_id)
    if not key or (key.user_id != user.id and user.role != Role.admin):
        raise HTTPException(404, "API key not found")
    key.revoked_at = key.revoked_at or datetime.now(timezone.utc)
    audit(db, "api_key.revoked", user=user, entity_type="api_key", entity_id=key.id, request=request)
    db.commit()
    return key


# ---------------------------------------------------------------- AI engine settings
@router.get("/settings/ai")
def get_ai_settings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return public_view(load_ai_config(db))


@router.put("/settings/ai")
def put_ai_settings(body: AISettingsIn, request: Request, db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    try:
        cfg = save_ai_config(db, user_id=admin.id, llm_enabled=body.llm_enabled, provider=body.provider,
                             model=body.model, api_key=body.api_key, clear_api_key=body.clear_api_key,
                             fallback_to_builtin=body.fallback_to_builtin, timeout_s=body.timeout_s)
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    audit(db, "settings.ai_updated", user=admin, entity_type="setting", entity_id="ai_engine", request=request,
          details={"llm_enabled": body.llm_enabled, "provider": body.provider, "model": cfg.model,
                   "api_key_changed": bool(body.api_key) or body.clear_api_key})
    db.commit()
    return public_view(cfg)


@router.post("/settings/ai/test")
def test_ai(body: AITestIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    cfg = load_ai_config(db)
    key = body.api_key or (cfg.api_key if cfg.provider == body.provider else None)
    if not key:
        raise HTTPException(400, "Enter an API key to test")
    model = body.model or PROVIDERS[body.provider]["default_model"]
    try:
        reply = test_connection(body.provider, key, model)
    except LLMError as e:
        return {"ok": False, "message": str(e)}
    return {"ok": True, "message": f"Connected to {PROVIDERS[body.provider]['label']} ({model}). Reply: {reply}"}


@router.get("/settings/system")
def system_settings(_: User = Depends(get_current_user)):
    return {
        "app_env": settings.app_env,
        "max_upload_mb": settings.max_upload_mb,
        "validation_tolerance": settings.validation_tolerance,
        "tax_tolerance_pct": settings.tax_tolerance_pct,
        "low_confidence_threshold": settings.low_confidence_threshold,
        "embedding_model": settings.embedding_model,
        "ocr_engine": "tesseract (eng)",
        "ocr_available": tesseract_available(),
        "allowed_extensions": [".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".xlsx", ".xls", ".csv"],
    }


# ---------------------------------------------------------------- audit log
@router.get("/audit-logs", response_model=Page[dict])
def audit_logs(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), db: Session = Depends(get_db),
               _: User = Depends(require_admin)):
    total = db.scalar(select(func.count()).select_from(AuditLog))
    rows = db.execute(select(AuditLog, User.email).outerjoin(User, User.id == AuditLog.user_id)
                      .order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    items = [{"id": a.id, "created_at": a.created_at, "user_email": email, "action": a.action,
              "entity_type": a.entity_type, "entity_id": a.entity_id, "ip": a.ip, "details": a.details}
             for a, email in rows]
    return Page(items=items, total=total, page=page, page_size=page_size)
