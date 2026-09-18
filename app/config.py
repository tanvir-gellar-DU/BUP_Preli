"""Application configuration loaded exclusively from environment variables."""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings shared by local, Vercel, and Docker deployments."""

    openrouter_api_key: SecretStr | None = None
    openrouter_api_keys: list[SecretStr] = Field(default_factory=list)
    openrouter_model: str | None = None
    openrouter_fallback_model: str | None = None
    openrouter_timeout_seconds: float = Field(default=15.0, gt=0, le=30)

    @field_validator("openrouter_model", "openrouter_fallback_model")
    @classmethod
    def nonblank_model(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("OPENROUTER_MODEL must not be blank")
        return value

    def configured_api_keys(self) -> list[SecretStr]:
        """Return the key pool in configured order, without duplicate secrets."""

        candidates = [*self.openrouter_api_keys]
        if self.openrouter_api_key is not None:
            candidates.append(self.openrouter_api_key)
        unique: list[SecretStr] = []
        seen: set[str] = set()
        for candidate in candidates:
            secret = candidate.get_secret_value()
            if secret not in seen:
                seen.add(secret)
                unique.append(candidate)
        return unique

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-by-convention settings instance per process."""

    return Settings()
