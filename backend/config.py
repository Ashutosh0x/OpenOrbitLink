"""
OpenOrbitLink Backend Configuration.

All settings are loaded from environment variables with sensible defaults
for local development. Override via .env file or system environment.
"""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with env-var loading."""

    # ─── JWT ────────────────────────────────────────────────────────
    JWT_SECRET: str = secrets.token_urlsafe(64)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_HOURS: int = 72

    # ─── Database ───────────────────────────────────────────────────
    # SQLite for MVP; swap to postgresql+asyncpg://... for production
    DATABASE_URL: str = "sqlite+aiosqlite:///./openorbitlink.db"

    # ─── Ground Station ─────────────────────────────────────────────
    STATION_ID: str = "FS-GS-001"
    STATION_LAT: float = 28.6139
    STATION_LON: float = 77.2090
    LORA_FREQUENCY_HZ: float = 868_100_000.0

    # ─── ISM Duty Cycle ─────────────────────────────────────────────
    # ISM 868 MHz band: 1% duty cycle = 36 seconds TX per hour
    ISM_DUTY_CYCLE_PERCENT: float = 1.0
    MAX_TX_SECONDS_PER_HOUR: float = 36.0

    # ─── Rate Limits ────────────────────────────────────────────────
    MAX_MESSAGES_PER_USER_PER_HOUR: int = 20
    MAX_PAYLOAD_BYTES: int = 200  # LoRa frame limit practical ceiling

    # ─── Registration ───────────────────────────────────────────────
    INVITE_CODE_REQUIRED: bool = True
    DEFAULT_INVITE_CODES: str = "BETA-OOL-2026,ORBIT-ALPHA-01,DTN-TESTER-KEY"

    # ─── TinyGS ─────────────────────────────────────────────────────
    TINYGS_BASE_URL: str = "https://api.tinygs.com/v1"
    TINYGS_BEARER_TOKEN: Optional[str] = None

    # ─── Server ─────────────────────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    CORS_ORIGINS: str = "*"

    model_config = {"env_prefix": "OOL_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
