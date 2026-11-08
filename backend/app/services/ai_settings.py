"""AI engine settings stored in the database and edited from Settings -> AI Engine.

The app always works with the built-in engine. An LLM provider can be enabled later from the UI;
its API key is stored encrypted and never returned in full.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.db.models import SystemSetting

KEY = "ai_engine"

PROVIDERS = {
    "anthropic": {"label": "Anthropic Claude", "default_model": "claude-sonnet-5-5",
                  "models": ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"]},
    "openai": {"label": "OpenAI", "default_model": "gpt-4o-mini",
               "models": ["gpt-4o-mini", "gpt-4o"]},
}


@dataclass
class AIConfig:
    llm_enabled: bool = False
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None  # decrypted, only used server-side
    fallback_to_builtin: bool = True
    timeout_s: int = 60

    @property
    def active_engine(self) -> str:
        if self.llm_enabled and self.provider and self.api_key:
            return self.provider
        return "builtin"


def load_ai_config(db: Session) -> AIConfig:
    row = db.get(SystemSetting, KEY)
    if not row:
        return AIConfig()
    v = row.value or {}
    return AIConfig(
        llm_enabled=bool(v.get("llm_enabled")),
        provider=v.get("provider"),
        model=v.get("model"),
        api_key=decrypt_secret(v["api_key_enc"]) if v.get("api_key_enc") else None,
        fallback_to_builtin=v.get("fallback_to_builtin", True),
        timeout_s=int(v.get("timeout_s", 60)),
    )


def save_ai_config(db: Session, *, user_id, llm_enabled: bool, provider: str | None, model: str | None,
                   api_key: str | None, clear_api_key: bool, fallback_to_builtin: bool, timeout_s: int) -> AIConfig:
    row = db.get(SystemSetting, KEY)
    current = dict(row.value) if row else {}
    if provider is not None and provider not in PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'")
    current.update(
        llm_enabled=llm_enabled,
        provider=provider,
        model=model or (PROVIDERS[provider]["default_model"] if provider else None),
        fallback_to_builtin=fallback_to_builtin,
        timeout_s=timeout_s,
    )
    if clear_api_key:
        current.pop("api_key_enc", None)
    elif api_key:
        current["api_key_enc"] = encrypt_secret(api_key.strip())
    if llm_enabled and not (current.get("provider") and current.get("api_key_enc")):
        raise ValueError("Choose a provider and enter an API key before enabling the LLM")
    if row:
        row.value = current
        row.updated_by = user_id
    else:
        db.add(SystemSetting(key=KEY, value=current, updated_by=user_id))
    db.flush()
    return load_ai_config(db)


def public_view(cfg: AIConfig) -> dict:
    return {
        "llm_enabled": cfg.llm_enabled,
        "provider": cfg.provider,
        "model": cfg.model,
        "api_key_set": bool(cfg.api_key),
        "api_key_masked": mask_secret(cfg.api_key),
        "fallback_to_builtin": cfg.fallback_to_builtin,
        "timeout_s": cfg.timeout_s,
        "active_engine": cfg.active_engine,
        "providers": PROVIDERS,
    }
