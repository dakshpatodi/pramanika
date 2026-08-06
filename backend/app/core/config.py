"""
Centralized application configuration.

All environment-driven settings live here so the rest of the codebase
never reads `os.environ` directly. Values are loaded from a `.env` file
in local development and from real environment variables in production.
"""

from functools import lru_cache
from typing import List

from pydantic import computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- App metadata ---
    APP_NAME: str = "Healthy Harvest API"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:3000"

    # --- Database (configuration only in Phase 1, no models/tables yet) ---
    POSTGRES_USER: str = "healthy_harvest"
    POSTGRES_PASSWORD: str = "changeme"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str = "healthy_harvest_db"
    DATABASE_URL: str | None = None

    # --- JWT ---
    # SECRET_KEY below is an obviously-fake placeholder so local dev works
    # out of the box. The validator further down refuses to start if this
    # placeholder is still in place while APP_ENV=production.
    SECRET_KEY: str = "insecure-development-secret-please-override-in-env"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
        """Build the SQLAlchemy connection string.

        If DATABASE_URL is explicitly set (common in hosted environments
        like Render/Railway/Docker), it takes precedence. Otherwise the
        URL is assembled from the individual POSTGRES_* fields.
        """
        if self.DATABASE_URL:
            return self.DATABASE_URL

        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field
    @property
    def CORS_ORIGINS_LIST(self) -> List[str]:
        """Split the comma-separated CORS_ORIGINS env var into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _require_real_secret_key_in_production(self) -> "Settings":
        """Fail fast on startup rather than silently signing production
        JWTs with a secret that's sitting in this file in plain text."""
        if self.APP_ENV == "production" and self.SECRET_KEY == "insecure-development-secret-please-override-in-env":
            raise ValueError(
                "SECRET_KEY is still the development placeholder but APP_ENV=production. "
                "Set a real SECRET_KEY in your environment before deploying."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance so the .env file is parsed once."""
    return Settings()


settings = get_settings()