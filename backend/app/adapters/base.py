"""Service adapter contract and helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from app.schemas import Metric, ServiceSnapshot, ServiceStatus


def utcnow() -> datetime:
    return datetime.now(UTC)


def metric(
    key: str,
    label: str,
    value: Any | None = None,
    *,
    unit: str | None = None,
    display: str | None = None,
    available: bool | None = None,
    primary: bool = False,
    detail: str | None = None,
) -> Metric:
    is_available = available if available is not None else value is not None
    if not is_available:
        return Metric(
            key=key,
            label=label,
            value=None,
            display="Unavailable",
            unit=unit,
            available=False,
            primary=primary,
            detail=None,
        )
    if display is not None:
        text = display
    elif isinstance(value, float):
        text = f"{value:.1f}"
    else:
        text = str(value)
    return Metric(
        key=key,
        label=label,
        value=value,
        display=text,
        unit=unit,
        available=True,
        primary=primary,
        detail=detail,
    )


def not_configured_snapshot(
    *,
    service_id: str,
    name: str,
    description: str,
    icon: str,
    message: str = "Not configured",
    href: str | None = None,
    open_label: str | None = None,
) -> ServiceSnapshot:
    return ServiceSnapshot(
        id=service_id,
        name=name,
        description=description,
        icon=icon,
        status=ServiceStatus.NOT_CONFIGURED,
        status_label="Not configured",
        metrics=[],
        version=None,
        url=None,
        href=href,
        open_label=open_label,
        last_updated=utcnow(),
        last_success_at=None,
        configured=False,
        error=message,
    )


def offline_snapshot(
    *,
    service_id: str,
    name: str,
    description: str,
    icon: str,
    url: str | None,
    error: str,
    metrics: list[Metric] | None = None,
    status: ServiceStatus = ServiceStatus.OFFLINE,
    status_label: str = "Offline",
    href: str | None = None,
    open_label: str | None = None,
    last_success_at: datetime | None = None,
) -> ServiceSnapshot:
    return ServiceSnapshot(
        id=service_id,
        name=name,
        description=description,
        icon=icon,
        status=status,
        status_label=status_label,
        metrics=metrics or [],
        version=None,
        url=url,
        href=href or url,
        open_label=open_label,
        last_updated=utcnow(),
        last_success_at=last_success_at,
        configured=True,
        error=error,
    )


class ServiceAdapter(ABC):
    """Plugin interface for integrating a home-server service."""

    id: str
    name: str
    description: str
    icon: str = "server"
    implemented: bool = True
    configurable: bool = True

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True when enough config/secrets exist to attempt a fetch."""

    @abstractmethod
    async def fetch(self) -> ServiceSnapshot:
        """Collect a live snapshot. Must never raise for expected outages."""

    def open_url(self) -> str | None:
        return None
