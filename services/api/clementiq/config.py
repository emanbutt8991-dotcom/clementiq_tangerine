"""Central configuration. Every secret and endpoint comes from environment variables.

Development defaults are safe for a local laptop (SQLite, demo access codes, no external
credentials). Production must override them — see `.env.example` and docs/DEPLOYMENT.md.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    environment: str = Field("development", alias="CLEMENTIQ_ENV")
    database_url: str = Field(
        f"sqlite:///{(REPO_ROOT / 'data' / 'processed' / 'clementiq.db').as_posix()}",
        alias="DATABASE_URL",
    )
    data_dir: Path = Field(REPO_ROOT / "data", alias="DATA_DIR")
    public_web_url: str = Field("http://localhost:3000", alias="PUBLIC_WEB_URL")
    cors_origins: str = Field("http://localhost:3000,http://127.0.0.1:3000", alias="CORS_ORIGINS")

    # --- auth ---
    jwt_secret: str = Field("dev-only-change-me-dev-only-change-me", alias="JWT_SECRET")
    jwt_ttl_minutes: int = Field(720, alias="JWT_TTL_MINUTES")
    judge_access_code: str = Field("tangerine-judge", alias="JUDGE_ACCESS_CODE")
    admin_access_code: str = Field("tangerine-admin", alias="ADMIN_ACCESS_CODE")
    demo_customer_access_code: str = Field("tangerine-customer", alias="DEMO_CUSTOMER_ACCESS_CODE")
    rate_limit_per_minute: int = Field(240, alias="RATE_LIMIT_PER_MINUTE")
    ai_rate_limit_per_minute: int = Field(20, alias="AI_RATE_LIMIT_PER_MINUTE")

    # --- Clement Core reference values (Tangerine challenge README) ---
    reference_date: str = Field("2025-12-31", alias="REFERENCE_DATE")
    runway_cap_months: float = 120.0
    buffer_window_months: int = 6

    # --- Gemini ---
    gemini_api_key: str | None = Field(None, alias="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-flash-latest", alias="GEMINI_MODEL")
    gemini_grounding: bool = Field(False, alias="GEMINI_GROUNDING")
    gemini_timeout_s: float = Field(30.0, alias="GEMINI_TIMEOUT_S")
    # Image model for the optional, consent-based orchard avatar.
    gemini_image_model: str = Field("gemini-2.5-flash-image", alias="GEMINI_IMAGE_MODEL")
    max_upload_bytes: int = Field(5 * 1024 * 1024, alias="MAX_UPLOAD_BYTES")

    # --- Snowflake Cortex (optional) ---
    snowflake_account_url: str | None = Field(None, alias="SNOWFLAKE_ACCOUNT_URL")
    snowflake_pat: str | None = Field(None, alias="SNOWFLAKE_PAT")
    snowflake_model: str = Field("mistral-large3", alias="SNOWFLAKE_MODEL")
    snowflake_warehouse: str | None = Field(None, alias="SNOWFLAKE_WAREHOUSE")

    # --- WorldPulse providers ---
    worldpulse_live: bool = Field(True, alias="WORLDPULSE_LIVE")
    news_api_key: str | None = Field(None, alias="NEWS_API_KEY")
    alpha_vantage_key: str | None = Field(None, alias="ALPHA_VANTAGE_KEY")
    http_timeout_s: float = Field(12.0, alias="HTTP_TIMEOUT_S")

    # --- Solana ---
    solana_mainnet_rpc: str = Field("https://api.mainnet-beta.solana.com", alias="SOLANA_MAINNET_RPC")
    solana_devnet_rpc: str = Field("https://api.devnet.solana.com", alias="SOLANA_DEVNET_RPC")

    # --- outbound notifications (opt-in only) ---
    smtp_host: str | None = Field(None, alias="SMTP_HOST")
    smtp_port: int = Field(587, alias="SMTP_PORT")
    smtp_user: str | None = Field(None, alias="SMTP_USER")
    smtp_password: str | None = Field(None, alias="SMTP_PASSWORD")
    smtp_from: str = Field("alerts@clementiq.local", alias="SMTP_FROM")

    # --- EI assumptions (extended mode only; judging mode never applies the cap) ---
    # 2025 maximum insurable earnings $65,700 -> max weekly benefit $695 (canada.ca).
    ei_max_weekly_benefit: float = Field(695.0, alias="EI_MAX_WEEKLY_BENEFIT")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def snowflake_enabled(self) -> bool:
        return bool(self.snowflake_account_url and self.snowflake_pat)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_production and s.jwt_secret.startswith("dev-only"):
        raise RuntimeError("JWT_SECRET must be set in production")
    return s
