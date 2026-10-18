"""
Centralized application configuration.

All environment-driven settings live here so the rest of the codebase
never reads `os.environ` directly. Values are loaded from a `.env` file
in local development and from real environment variables in production.
"""

import re
from functools import lru_cache
from typing import List

from pydantic import Field, SecretStr, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_WEBHOOK_SECRET_LENGTH = 16

class Settings(BaseSettings):
    # --- App metadata ---
    APP_NAME: str = "Healthy Harvest API"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:3000"

    # --- Database ---
    POSTGRES_USER: str = "healthy_harvest"
    POSTGRES_PASSWORD: str = "changeme"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str = "healthy_harvest_db"
    DATABASE_URL: str | None = None

    # --- JWT ---
    SECRET_KEY: str = "insecure-development-secret-please-override-in-env"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Phase 5: Cart pricing (Decisions D & E) ---
    GST_RATE: float = 0.05
    """Flat rate applied to the post-discount product subtotal (0.05 = 5%).
    This is a PLACEHOLDER default, not a tax determination - packaged food
    GST rates in India vary by product classification (0%/5%/12%/18%).
    Confirm the real applicable rate for Pramanika's actual product mix
    before this matters financially; until then this only affects
    calculated totals in development/testing.
    Per Decision D: flat rate now, not per-category - architecture stays
    flexible for a future `Category.gst_rate` column if that's ever needed,
    but no such column exists yet."""

    FREE_DELIVERY_THRESHOLD: float = 500.0
    """Post-discount subtotal at or above which delivery is free."""

    DELIVERY_CHARGE: float = 49.0
    """Flat delivery fee applied when the post-discount subtotal is below
    FREE_DELIVERY_THRESHOLD. Never taxed - GST is calculated on the
    taxable product amount only, per the confirmed calculation order."""

    # --- Phase 7: Razorpay payments ---
    # Credentials come ONLY from the environment / .env (never hardcoded,
    # never committed). The two secrets are `SecretStr`, so printing the
    # settings object or logging it shows "**********", not the value.
    # Only RAZORPAY_KEY_ID is ever sent to the browser (Razorpay Checkout
    # needs it); the key secret and the webhook secret stay on the server.
    RAZORPAY_KEY_ID: str = ""
    """Public key id, e.g. rzp_test_xxxxxxxxxxxxxx (Dashboard > API Keys)."""

    RAZORPAY_KEY_SECRET: SecretStr = SecretStr("")
    """Server-side API secret that pairs with RAZORPAY_KEY_ID. Used to call
    Razorpay and to verify the checkout signature."""

    RAZORPAY_WEBHOOK_SECRET: SecretStr = SecretStr("")
    """Secret you type into the Razorpay webhook settings. Used only to
    verify webhook signatures. A different value from the key secret."""

    RAZORPAY_API_BASE_URL: str = "https://api.razorpay.com/v1"
    RAZORPAY_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0, le=60)
    """Hard limit on every call to Razorpay so a slow gateway can never hold
    a database transaction or a worker open indefinitely."""

    ORDER_PAYMENT_WINDOW_MINUTES: int = Field(default=30, ge=1, le=1440)
    """How long an unpaid order keeps its reserved stock before it expires."""

    ORDER_EXPIRY_WORKER_ENABLED: bool = True
    """Run the expiry job inside the web server. Set false if you run
    `python -m app.jobs.expire_orders` from cron instead."""
    ORDER_EXPIRY_INTERVAL_SECONDS: float = Field(default=60.0, ge=1, le=3600)
    """How often the expiry job looks for orders past their deadline."""
    ORDER_EXPIRY_BATCH_SIZE: int = Field(default=50, ge=1, le=500)
    """How many due orders one pass handles before looking again."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        # A validation error normally prints the raw input, which here includes the Razorpay
        # secrets exactly as typed in .env. Startup errors end up in terminals and logs.
        hide_input_in_errors=True,
    )

    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field
    @property
    def CORS_ORIGINS_LIST(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @computed_field
    @property
    def RAZORPAY_TEST_MODE(self) -> bool:
        """True when the configured key id is a Razorpay TEST key."""
        return self.RAZORPAY_KEY_ID.startswith("rzp_test_")

    @model_validator(mode="after")
    def _validate_razorpay_settings(self) -> "Settings":
        key_id = self.RAZORPAY_KEY_ID.strip()
        if key_id != self.RAZORPAY_KEY_ID:
            object.__setattr__(self, "RAZORPAY_KEY_ID", key_id)
        if key_id:
            if not (key_id.startswith("rzp_test_") or key_id.startswith("rzp_live_")) or len(key_id) <= len("rzp_test_"):
                raise ValueError("RAZORPAY_KEY_ID must look like rzp_test_xxxxxxxx or rzp_live_xxxxxxxx.")
            # Safety net: a live key outside production could charge real money
            # from a developer machine or a test run.
            if key_id.startswith("rzp_live_") and self.APP_ENV != "production":
                raise ValueError(
                    "RAZORPAY_KEY_ID is a LIVE key but APP_ENV is not 'production'. "
                    "Use Razorpay TEST keys (rzp_test_...) for development and testing."
                )
                # The webhook is authenticated by nothing but this secret: whoever can guess it can
        # "pay" orders. So a short one is refused outright (the dashboard accepts anything).
        webhook_secret = self.RAZORPAY_WEBHOOK_SECRET.get_secret_value().strip()
        if webhook_secret:
            if len(webhook_secret) < MIN_WEBHOOK_SECRET_LENGTH:
                raise ValueError(
                    f"RAZORPAY_WEBHOOK_SECRET is too short (minimum {MIN_WEBHOOK_SECRET_LENGTH} characters). "
                    'Generate one: python -c "import secrets; print(secrets.token_urlsafe(32))"'
                )
            if webhook_secret == self.RAZORPAY_KEY_SECRET.get_secret_value().strip():
                raise ValueError("RAZORPAY_WEBHOOK_SECRET must differ from RAZORPAY_KEY_SECRET.")

        # The API key is sent to this address with every request: only over https
        # (plain http is allowed just for a mock server on this machine).
        base = self.RAZORPAY_API_BASE_URL.strip()
        local_http = re.match(r"^http://(localhost|127\.0\.0\.1)(:\d+)?(/|$)", base)
        if not (base.startswith("https://") or local_http):
            raise ValueError("RAZORPAY_API_BASE_URL must start with https:// (http:// only for localhost).")
        return self

    @model_validator(mode="after")
    def _require_real_secret_key_in_production(self) -> "Settings":
        if self.APP_ENV == "production" and self.SECRET_KEY == "insecure-development-secret-please-override-in-env":
            raise ValueError(
                "SECRET_KEY is still the development placeholder but APP_ENV=production. "
                "Set a real SECRET_KEY in your environment before deploying."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
