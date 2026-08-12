"""Application settings from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    data_dir: Path = Field(default=Path("./data"))
    server_name: str = Field(default="Home Server")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8080)
    cors_origins: str = Field(default="*")

    # Service base URLs (non-secret). Can also be overridden via /data/config.json.
    jellyfin_url: str | None = Field(default=None)
    jellyfin_api_key: str | None = Field(default=None)
    starpulse_url: str | None = Field(default=None)
    docker_socket: str | None = Field(default=None)

    http_timeout_seconds: float = Field(default=5.0)

    @property
    def config_path(self) -> Path:
        return self.data_dir / "config.json"

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
