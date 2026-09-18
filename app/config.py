"""Application configuration loaded exclusively from environment variables."""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings shared by local, Vercel, and Docker deployments."""

    openrouter_api_key: SecretStr | None = None
    openrouter_model: str | None = None
    openrouter_timeout_seconds: float = Field(default=15.0, gt=0, le=30)

    @field_validator("openrouter_model")
    @classmethod
    def nonblank_model(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("OPENROUTER_MODEL must not be blank")
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-by-convention settings instance per process."""

    return Settings()
