"""
Application configuration management using Pydantic settings.
Loads configuration from environment variables and .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str

    # Security
    secret_key: str

    # Environment
    environment: str = "development"

    # Server
    port: int = 7006

    # Geocoding
    google_maps_api_key: Optional[str] = None

    # CORS
    allowed_origins: str = "http://localhost:8000"

    # Logging
    log_level: str = "INFO"

    # Optimization
    optimization_time_limit_seconds: int = 120
    max_customers_per_route: int = 50

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.allowed_origins.split(",")]


# Global settings instance
settings = Settings()
