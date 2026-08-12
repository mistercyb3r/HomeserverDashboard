"""Shared API and adapter response models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ServiceStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    NOT_CONFIGURED = "not_configured"


class SystemHealthLevel(StrEnum):
    OPERATIONAL = "operational"
    ATTENTION = "attention"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class Metric(BaseModel):
    """A single display metric for a service card or overview strip."""

    key: str
    label: str
    value: Any | None = None
    display: str = "Unavailable"
    unit: str | None = None
    available: bool = False
    primary: bool = False
    detail: str | None = None


class PlaybackSession(BaseModel):
    """Safe Jellyfin now-playing row for the dashboard card."""

    id: str
    user: str
    title: str
    subtitle: str | None = None
    progress: str | None = None
    paused: bool = False
    artwork_url: str | None = None


class ServiceSnapshot(BaseModel):
    """Normalized snapshot produced by any ServiceAdapter."""

    id: str
    name: str
    description: str = ""
    icon: str = "server"
    status: ServiceStatus
    status_label: str
    metrics: list[Metric] = Field(default_factory=list)
    version: str | None = None
    uptime: str | None = None
    url: str | None = None
    href: str | None = None
    open_label: str | None = None
    now_playing: list[PlaybackSession] | None = None
    last_updated: datetime
    last_success_at: datetime | None = None
    configured: bool = True
    error: str | None = None


class StorageMount(BaseModel):
    """One real mounted filesystem (never folder-size scans)."""

    mountpoint: str
    device: str | None = None
    fstype: str | None = None
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent: float
    total_display: str
    used_display: str
    free_display: str
    summary: str
    tone: str = "good"  # good | warn | bad


class OverviewMetric(BaseModel):
    key: str
    label: str
    value: float | int | str | None = None
    display: str = "Unavailable"
    unit: str | None = None
    available: bool = False
    bar: float | None = None
    detail: str | None = None
    tone: str | None = None


class SystemHealth(BaseModel):
    level: SystemHealthLevel
    label: str
    online_count: int
    attention_count: int
    offline_count: int
    not_configured_count: int
    total_enabled: int


class ActivityItem(BaseModel):
    """Ephemeral status line derived from the current snapshot — not stored."""

    tone: str  # good | warn | bad | muted
    text: str


class DashboardResponse(BaseModel):
    server_name: str
    generated_at: datetime
    refresh_interval_seconds: int = 10
    system_health: SystemHealth
    overview: list[OverviewMetric]
    storage: list[StorageMount] = Field(default_factory=list)
    services: list[ServiceSnapshot]
    activity: list[ActivityItem] = Field(default_factory=list)


class ServiceDefinition(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    enabled: bool
    configured: bool
    configurable: bool
    implemented: bool
    url: str | None = None
    socket: str | None = None
    config_kind: str = "url"
    has_secret: bool = False


class SettingsResponse(BaseModel):
    server_name: str
    refresh_interval_seconds: int
    services: list[ServiceDefinition]


class ServiceSettingsUpdate(BaseModel):
    enabled: bool | None = None
    url: str | None = None
    socket: str | None = None


class SettingsUpdateRequest(BaseModel):
    server_name: str | None = None
    refresh_interval_seconds: int | None = Field(default=None, ge=5, le=3600)
    services: dict[str, ServiceSettingsUpdate] | None = None


class DockerPort(BaseModel):
    private_port: int
    public_port: int | None = None
    type: str = "tcp"
    ip: str | None = None
    display: str


class DockerContainer(BaseModel):
    id: str
    name: str
    image: str
    state: str
    status: str
    status_tone: str
    uptime: str | None = None
    cpu_percent: float | None = None
    cpu_display: str = "Unavailable"
    memory_usage: int | None = None
    memory_limit: int | None = None
    memory_display: str = "Unavailable"
    restart_count: int | None = None
    ports: list[DockerPort] = Field(default_factory=list)
    exit_code: int | None = None


class DockerOverview(BaseModel):
    daemon_status: str
    version: str | None = None
    api_version: str | None = None
    running: int = 0
    stopped: int = 0
    restarting: int = 0
    paused: int = 0
    total: int = 0
    images: int | None = None
    volumes: int | None = None
    containers_from_info: int | None = None


class DockerDetailResponse(BaseModel):
    available: bool
    configured: bool
    generated_at: datetime
    error: str | None = None
    overview: DockerOverview | None = None
    containers: list[DockerContainer] = Field(default_factory=list)
