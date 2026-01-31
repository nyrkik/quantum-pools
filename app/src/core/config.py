"""
QuantumPools Configuration
Loads and validates environment variables with sensible defaults.
"""

from typing import Optional, List
from pydantic_settings import BaseSettings
from pydantic import Field, AliasChoices
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "QuantumPools"
    environment: str = Field(default="development", env="ENVIRONMENT")
    debug: bool = Field(default=False, env="DEBUG")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    secret_key: str = Field(default="change-me-in-production", env="SECRET_KEY")

    # Database
    database_url: str = Field(
        default="postgresql://quantumpools:quantumpools@localhost:5434/quantumpools",
        env="DATABASE_URL",
    )
    sql_echo: bool = Field(default=False, env="SQL_ECHO")

    # Redis
    redis_url: str = Field(default="redis://localhost:6380/0", env="REDIS_URL")

    # Security & Auth
    jwt_access_token_expire_hours: int = Field(default=24, env="JWT_ACCESS_TOKEN_EXPIRE_HOURS")
    jwt_refresh_token_expire_days: int = Field(default=7, env="JWT_REFRESH_TOKEN_EXPIRE_DAYS")
    min_password_length: int = Field(default=10, env="MIN_PASSWORD_LENGTH")
    max_login_attempts: int = Field(default=5, env="MAX_LOGIN_ATTEMPTS")
    login_lockout_minutes: int = Field(default=15, env="LOGIN_LOCKOUT_MINUTES")

    # Cookie Settings
    cookie_domain: Optional[str] = Field(default=None, env="COOKIE_DOMAIN")
    cookie_secure: bool = Field(default=False, env="COOKIE_SECURE")

    # CORS
    cors_origins_raw: str = Field(
        default="http://localhost:7061,http://localhost:3000",
        validation_alias=AliasChoices("CORS_ORIGINS", "cors_origins"),
    )

    # Rate Limiting
    rate_limit_enabled: bool = Field(default=True, env="RATE_LIMIT_ENABLED")
    rate_limit_per_minute: int = Field(default=100, env="RATE_LIMIT_PER_MINUTE")

    # Email
    smtp_host: Optional[str] = Field(default=None, env="SMTP_HOST")
    smtp_port: int = Field(default=587, env="SMTP_PORT")
    smtp_user: Optional[str] = Field(default=None, env="SMTP_USER")
    smtp_password: Optional[str] = Field(default=None, env="SMTP_PASSWORD")
    smtp_from_email: Optional[str] = Field(default=None, env="SMTP_FROM_EMAIL")
    smtp_from_name: str = Field(default="QuantumPools", env="SMTP_FROM_NAME")
    frontend_url: str = Field(default="http://localhost:7061", env="FRONTEND_URL")

    # AI Services
    anthropic_api_key: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")

    # Geocoding
    google_maps_api_key: Optional[str] = Field(default=None, env="GOOGLE_MAPS_API_KEY")

    # QuantumTax Integration
    quantumtax_sync_url: str = Field(
        default="http://localhost:7050/api/sync/quantumpools",
        env="QUANTUMTAX_SYNC_URL",
    )
    quantum_sync_secret: str = Field(default="", env="QUANTUM_SYNC_SECRET")

    # File Storage
    upload_dir: str = Field(default="./uploads", env="UPLOAD_DIR")
    max_upload_size_mb: int = Field(default=25, env="MAX_UPLOAD_SIZE_MB")

    # DO Spaces (prod file storage)
    spaces_access_key: Optional[str] = Field(default=None, env="SPACES_ACCESS_KEY")
    spaces_secret_key: Optional[str] = Field(default=None, env="SPACES_SECRET_KEY")
    spaces_bucket: Optional[str] = Field(default=None, env="SPACES_BUCKET")
    spaces_region: str = Field(default="nyc3", env="SPACES_REGION")
    spaces_endpoint: Optional[str] = Field(default=None, env="SPACES_ENDPOINT")

    # Monitoring
    sentry_dsn: Optional[str] = Field(default=None, env="SENTRY_DSN")

    # API Docs
    api_docs_enabled: bool = Field(default=True, env="API_DOCS_ENABLED")

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",")]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    model_config = {
        "env_file": Path(__file__).parent.parent.parent / ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


settings = get_settings()
