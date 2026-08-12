"""Docker service adapter — summary metrics for the dashboard card."""

from __future__ import annotations

from datetime import datetime

from app.adapters.base import (
    ServiceAdapter,
    metric,
    not_configured_snapshot,
    offline_snapshot,
    utcnow,
)
from app.docker_engine import DockerEngineClient, DockerEngineError
from app.schemas import Metric, ServiceSnapshot, ServiceStatus

_LAST_SUCCESS: dict[str, datetime] = {}


class DockerAdapter(ServiceAdapter):
    id = "docker"
    name = "Docker"
    description = "Container runtime"
    icon = "box"
    configurable = True

    def __init__(
        self,
        *,
        enabled: bool,
        socket_path: str | None,
        timeout: float = 5.0,
    ) -> None:
        self._enabled = enabled
        self._socket_path = socket_path
        self._timeout = timeout
        self._client = DockerEngineClient(socket_path, timeout=timeout)

    def is_configured(self) -> bool:
        return bool(self._enabled and self._socket_path)

    def open_url(self) -> str | None:
        return "/docker" if self._enabled else None

    async def fetch(self) -> ServiceSnapshot:
        if not self.is_configured():
            return not_configured_snapshot(
                service_id=self.id,
                name=self.name,
                description=self.description,
                icon=self.icon,
                message="Enable Docker and set the socket path in Settings",
                href="/docker",
                open_label="Open Docker",
            )

        try:
            version = await self._client.version()
            containers = await self._client.containers(all_containers=True)
        except DockerEngineError as exc:
            message = str(exc)
            lowered = message.lower()
            missing_socket = any(
                token in lowered
                for token in (
                    "no such file",
                    "cannot find the file",
                    "filenotfounderror",
                    "does not exist",
                )
            )
            if missing_socket:
                return not_configured_snapshot(
                    service_id=self.id,
                    name=self.name,
                    description=self.description,
                    icon=self.icon,
                    message="Docker socket not available",
                    href="/docker",
                    open_label="Open Docker",
                )
            return offline_snapshot(
                service_id=self.id,
                name=self.name,
                description=self.description,
                icon=self.icon,
                url=None,
                href="/docker",
                open_label="Open Docker",
                error=message,
                status=ServiceStatus.DEGRADED,
                status_label="Unavailable",
                last_success_at=_LAST_SUCCESS.get(self.id),
                metrics=[
                    metric("containers", "Containers", None, primary=True),
                    metric("running", "Running", None, primary=True),
                    metric("stopped", "Stopped", None, primary=True),
                ],
            )

        running = 0
        stopped = 0
        restarting = 0
        for item in containers:
            state = str(item.get("State") or "").lower()
            if state == "running":
                running += 1
            elif state == "restarting":
                restarting += 1
            elif state in {"exited", "dead", "created"}:
                stopped += 1
            else:
                stopped += 1

        total = len(containers)
        version_str = version.get("Version")
        _LAST_SUCCESS[self.id] = utcnow()

        status = ServiceStatus.ONLINE
        status_label = "Online"
        if restarting > 0:
            status = ServiceStatus.DEGRADED
            status_label = f"{restarting} restarting"

        metrics: list[Metric] = [
            metric(
                "containers",
                "Containers",
                total,
                display=f"{total} containers",
                primary=True,
            ),
            metric(
                "running",
                "Running",
                running,
                display=f"{running} running",
                primary=True,
            ),
            metric(
                "stopped",
                "Stopped",
                stopped,
                display=f"{stopped} stopped",
                primary=True,
            ),
        ]
        if restarting:
            metrics.append(
                metric(
                    "restarting",
                    "Restarting",
                    restarting,
                    display=f"{restarting} restarting",
                    primary=True,
                )
            )
        metrics.append(
            metric(
                "version",
                "Version",
                version_str,
                display=None if version_str is None else f"v{version_str}",
            )
        )

        return ServiceSnapshot(
            id=self.id,
            name=self.name,
            description=self.description,
            icon=self.icon,
            status=status,
            status_label=status_label,
            metrics=metrics,
            version=version_str,
            url=None,
            href="/docker",
            open_label="Open Docker",
            last_updated=utcnow(),
            last_success_at=_LAST_SUCCESS.get(self.id),
            configured=True,
            error=None,
        )
