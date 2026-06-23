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

    # ── Storage backend selector ───────────────────────────────────────────
    # "minio"    — local dockerized MinIO (development default)
    # "supabase" — Supabase object storage (production)
    STORAGE_BACKEND: str = "minio"

    # MinIO / S3 Storage (used when STORAGE_BACKEND=minio)
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_PUBLIC_ENDPOINT: str | None = None
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "traffic-images"
    MINIO_SECURE: bool = False

    # Supabase S3-compatible Storage (used when STORAGE_BACKEND=supabase)
    # Credentials from Supabase dashboard: Storage → S3 Access
    SUPABASE_PROJECT_REF: str = ""           # e.g. "abcdefghijklmnop"
    SUPABASE_S3_ACCESS_KEY_ID: str = ""      # S3 Access Key ID
    SUPABASE_S3_SECRET_ACCESS_KEY: str = ""  # S3 Secret Access Key
    SUPABASE_S3_REGION: str = "ap-south-1"   # region shown in S3 Access panel
    SUPABASE_BUCKET: str = "traffic-images"

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
        """
        Ensure the database URL uses the asyncpg driver and translate
        psycopg2-style query params to asyncpg-compatible ones.

        - postgres:// / postgresql:// → postgresql+asyncpg://
        - sslmode=require → ssl=require  (asyncpg uses 'ssl', not 'sslmode')
        - channel_binding=require is dropped (not supported by asyncpg)
        """
        if isinstance(v, str):
            if v.startswith("postgres://"):
                v = v.replace("postgres://", "postgresql+asyncpg://", 1)
            elif v.startswith("postgresql://"):
                v = v.replace("postgresql://", "postgresql+asyncpg://", 1)

            # Translate sslmode → ssl (asyncpg-compatible)
            from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
            parsed = urlparse(v)
            params = parse_qs(parsed.query, keep_blank_values=True)

            # Drop unsupported params
            sslmode = params.pop("sslmode", [None])[0]
            params.pop("channel_binding", None)

            # Map sslmode values to asyncpg ssl values
            if sslmode in ("require", "verify-ca", "verify-full"):
                params["ssl"] = ["require"]
            elif sslmode == "disable":
                params["ssl"] = ["disable"]

            new_query = urlencode({k: v[0] for k, v in params.items()})
            v = urlunparse(parsed._replace(query=new_query))

        return v

    @model_validator(mode="before")
    @classmethod
    def resolve_storage_env(cls, data: Any) -> Any:
        """
        Normalise storage environment variables.

        Supports two input conventions:
        1. Native vars: MINIO_* / SUPABASE_* (local dev and clean prod setup)
        2. AWS-style vars: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_ENDPOINT_URL
           plus optional BUCKET_NAME — used when deploying via Render/Railway with
           Supabase S3-compatible credentials entered as AWS_* keys.

        When AWS_ENDPOINT_URL is present, its host is extracted and written into
        MINIO_ENDPOINT so that MinioStorageBackend receives a clean host:port/path
        string regardless of which convention was used.
        """
        if not isinstance(data, dict):
            return data

        import os
        from urllib.parse import urlparse

        aws_endpoint = data.get("AWS_ENDPOINT_URL") or os.getenv("AWS_ENDPOINT_URL")
        aws_access_key = data.get("AWS_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret_key = data.get("AWS_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY")
        bucket_name = data.get("BUCKET_NAME") or os.getenv("BUCKET_NAME")

        if aws_endpoint:
            parsed = urlparse(aws_endpoint)
            # MinIO client expects host (+ path), not the full URL with scheme.
            endpoint_host = parsed.netloc if parsed.netloc else aws_endpoint
            # Strip any accidental scheme prefix
            for prefix in ("https://", "http://"):
                if endpoint_host.startswith(prefix):
                    endpoint_host = endpoint_host[len(prefix):]

            # Append path component for Supabase S3 endpoint
            # e.g. dvibhmdfprwxqjupoxfw.supabase.co/storage/v1/s3
            if parsed.path and parsed.path != "/":
                endpoint_host = endpoint_host.rstrip("/") + parsed.path

            data["MINIO_ENDPOINT"] = endpoint_host
            data["MINIO_SECURE"] = (parsed.scheme == "https") if parsed.scheme else True

            if aws_access_key:
                data["MINIO_ACCESS_KEY"] = aws_access_key
                data["SUPABASE_S3_ACCESS_KEY_ID"] = aws_access_key
            if aws_secret_key:
                data["MINIO_SECRET_KEY"] = aws_secret_key
                data["SUPABASE_S3_SECRET_ACCESS_KEY"] = aws_secret_key

            # Derive SUPABASE_PROJECT_REF from the endpoint host if not already set
            if not data.get("SUPABASE_PROJECT_REF"):
                # e.g. dvibhmdfprwxqjupoxfw.supabase.co → dvibhmdfprwxqjupoxfw
                host_part = (parsed.netloc or aws_endpoint).split(".")[0]
                data["SUPABASE_PROJECT_REF"] = host_part

        # Map BUCKET_NAME → both bucket fields so either STORAGE_BACKEND works
        if bucket_name:
            if not data.get("MINIO_BUCKET"):
                data["MINIO_BUCKET"] = bucket_name
            if not data.get("SUPABASE_BUCKET"):
                data["SUPABASE_BUCKET"] = bucket_name

        return data

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS_ALLOWED_ORIGINS as a parsed list."""
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def supabase_s3_endpoint(self) -> str:
        """
        Derive the Supabase S3-compatible endpoint from the project ref.

        Format: ``<project-ref>.supabase.co/storage/v1/s3``
        The MinIO SDK strips the scheme, so we return the host+path only.
        """
        if not self.SUPABASE_PROJECT_REF:
            raise ValueError("SUPABASE_PROJECT_REF must be set when STORAGE_BACKEND=supabase")
        return f"{self.SUPABASE_PROJECT_REF}.supabase.co/storage/v1/s3"


# Module-level singleton — imported everywhere as `from app.config import settings`
try:
    settings = Settings()
except Exception:  # noqa: BLE001
    import sys, traceback
    print("=" * 60, file=sys.stderr)
    print("FATAL: Failed to load application settings from environment", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    sys.stderr.flush()
    raise
