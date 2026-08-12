"""Application settings from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
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
    portainer_url: str | None = Field(default=None)
    docker_socket: str | None = Field(default=None)

    # Host filesystem bind inside the container (e.g. /hostfs) for Storage.
    host_fs_root: str | None = Field(default=None)
    # Optional sysfs root for temperatures when /sys is remapped.
    host_sys_root: str | None = Field(default=None)

    # Weather (Open-Meteo — no API key). Does not affect system health.
    weather_enabled: bool = Field(default=True)
    weather_location: str = Field(default="Thetford, Norfolk, UK")
    weather_latitude: float | None = Field(default=None)
    weather_longitude: float | None = Field(default=None)
    weather_cache_seconds: int = Field(default=600, ge=60, le=3600)

    http_timeout_seconds: float = Field(default=5.0)

    @field_validator(
        "jellyfin_url",
        "jellyfin_api_key",
        "starpulse_url",
        "portainer_url",
        "docker_socket",
        "host_fs_root",
        "host_sys_root",
        mode="before",
    )
    @classmethod
    def _blank_str_to_none(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("weather_latitude", "weather_longitude", mode="before")
    @classmethod
    def _blank_coord_to_none(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

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
