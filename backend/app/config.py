"""
Application configuration loaded from environment variables via pydantic-settings.
"""
from __future__ import annotations

from typing import Any
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All required environment variables for TrafficVision AI backend."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/trafficvision"

    # MinIO / S3 Storage
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_PUBLIC_ENDPOINT: str | None = None
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "traffic-images"
    MINIO_SECURE: bool = False

    # AWS / S3 / R2 Environment Variable Overrides
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_ENDPOINT_URL: str | None = None
    AWS_REGION: str = "us-east-1"

    # CORS
    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173"

    # ML Models
    MODEL_DIR: str = "trained_models"

    # Application
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def validate_database_url(cls, v: Any) -> Any:
        """Ensure the database URL uses the asyncpg driver, even if neon/render provides postgresql://."""
        if isinstance(v, str):
            if v.startswith("postgres://"):
                v = v.replace("postgres://", "postgresql+asyncpg://", 1)
            elif v.startswith("postgresql://"):
                v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @model_validator(mode="before")
    @classmethod
    def resolve_storage_env(cls, data: Any) -> Any:
        """Resolve AWS/R2 variables and map them to standard storage variables."""
        if not isinstance(data, dict):
            return data

        import os
        from urllib.parse import urlparse

        aws_endpoint = data.get("AWS_ENDPOINT_URL") or os.getenv("AWS_ENDPOINT_URL")
        aws_access_key = data.get("AWS_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret_key = data.get("AWS_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY")

        if aws_endpoint:
            parsed = urlparse(aws_endpoint)
            # Minio client expects endpoint host (+ optional port), not the full URL scheme.
            endpoint_host = parsed.netloc if parsed.netloc else aws_endpoint
            if endpoint_host.startswith("http://"):
                endpoint_host = endpoint_host[7:]
            elif endpoint_host.startswith("https://"):
                endpoint_host = endpoint_host[8:]

            data["MINIO_ENDPOINT"] = endpoint_host
            data["MINIO_SECURE"] = parsed.scheme == "https" if parsed.scheme else True
            if "r2.cloudflarestorage.com" in endpoint_host:
                data["MINIO_SECURE"] = True

            if aws_access_key:
                data["MINIO_ACCESS_KEY"] = aws_access_key
            if aws_secret_key:
                data["MINIO_SECRET_KEY"] = aws_secret_key

            # Clean public endpoint if present
            pub_endpoint = data.get("MINIO_PUBLIC_ENDPOINT") or aws_endpoint
            if pub_endpoint:
                if "://" in pub_endpoint:
                    parsed_pub = urlparse(pub_endpoint)
                    pub_endpoint = parsed_pub.netloc if parsed_pub.netloc else pub_endpoint
                data["MINIO_PUBLIC_ENDPOINT"] = pub_endpoint

        return data

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS_ALLOWED_ORIGINS as a parsed list."""
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]


# Module-level singleton — imported everywhere as `from app.config import settings`
settings = Settings()
