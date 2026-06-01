"""Centralised configuration — every setting comes from env vars / .env file."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("spectra")
_SETTINGS_CACHE: Settings | None = None


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """All Spectra settings, loaded from environment or .env file."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # ── Google Sheets ────────────────────────────────────────────
    google_sheets_credentials_b64: str = ""
    google_sheets_credentials_file: str = "credentials.json"
    spreadsheet_id: str = ""

    # ── Base Currency ────────────────────────────────────────────
    base_currency: str = Field(default="VND")

    @field_validator("base_currency")
    @classmethod
    def _uppercase_currency(cls, v: str) -> str:
        return v.strip().upper()

    # ── AI Provider ──────────────────────────────────────────────
    ai_provider: Literal["openai", "local"] = Field(
        default="openai",
        validation_alias=AliasChoices("AI_PROVIDER", "AI_PrOVIDER"),
    )

    @field_validator("ai_provider", mode="before")
    @classmethod
    def _normalize_provider(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v

    openai_api_key: str = ""
    openai_model: str = "gpt-5.5"

    # ── Database ─────────────────────────────────────────────────
    database_url: str = Field(
        default="",
        validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_URL"),
    )

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        return str(v or "").strip()

    # Kept for compatibility with older tests/scripts; runtime DB uses DATABASE_URL.
    db_path: Path = Field(default=_PROJECT_ROOT / "data" / "prism.db")

    # ── Behaviour ────────────────────────────────────────────────
    log_level: str = "INFO"

    # Demo Auth / SSO
    sso_shared_secret: str = "change-me-for-local-demo"
    spectra_base_url: str = "http://localhost:8081"
    bank_simulator_base_url: str = "http://localhost:8000"
    session_cookie_secure: bool = False
    session_ttl_seconds: int = 28_800
    sso_token_ttl_seconds: int = 300

    # ── Validation ───────────────────────────────────────────────
    @model_validator(mode="after")
    def _check_required_secrets(self) -> "Settings":
        """Warn (don't crash) about missing secrets."""
        if not self.db_path.is_absolute():
            self.db_path = (_PROJECT_ROOT / self.db_path).resolve()

        credentials_file = Path(self.google_sheets_credentials_file)
        if not credentials_file.is_absolute():
            credentials_file = (_PROJECT_ROOT / credentials_file).resolve()
            self.google_sheets_credentials_file = str(credentials_file)

        missing: list[str] = []

        if not self.spreadsheet_id:
            missing.append("SPREADSHEET_ID")

        if not self.google_sheets_credentials_b64 and not credentials_file.exists():
            missing.append(
                "GOOGLE_SHEETS_CREDENTIALS_B64 or GOOGLE_SHEETS_CREDENTIALS_FILE"
            )

        if self.ai_provider == "openai" and not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        # 'local' mode needs no API keys

        if missing:
            logger.warning(
                "Missing secrets (some features may fail): %s", ", ".join(missing)
            )

        if not self.database_url:
            logger.warning("Missing DATABASE_URL (Postgres/Supabase database access will fail)")

        return self


def load_settings() -> Settings:
    """Load settings and configure logging."""
    global _SETTINGS_CACHE

    if _SETTINGS_CACHE is not None:
        return _SETTINGS_CACHE

    settings = Settings()  # type: ignore[call-arg]

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(name)-12s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )

    logger.info(
        "Spectra config loaded (provider=%s, database_url=%s, env=%s)",
        settings.ai_provider,
        "set" if settings.database_url else "missing",
        _ENV_FILE,
    )
    _SETTINGS_CACHE = settings
    return settings
