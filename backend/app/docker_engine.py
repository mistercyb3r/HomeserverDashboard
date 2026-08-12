"""Read-only Docker Engine API client.

Talks to the daemon over a Unix socket, named pipe, or TCP URL.
Never exposes env vars, secrets, or sensitive labels to callers.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

DEFAULT_SOCKET = "/var/run/docker.sock"
WINDOWS_NPIPE = "npipe:////./pipe/docker_engine"


@dataclass
class DockerConnection:
    base_url: str
    transport: httpx.AsyncBaseTransport | None = None


def resolve_docker_url(socket_path: str | None) -> str | None:
    """Return an httpx/docker-compatible base URL, or None if unusable."""
    raw = (socket_path or "").strip()
    if not raw:
        return None

    if raw.startswith(("unix://", "npipe://", "tcp://", "http://", "https://")):
        return raw

    path = Path(raw)
    if path.exists():
        return f"unix://{path.as_posix()}"

    # Windows Docker Desktop fallback when the Linux default path is configured.
    if sys.platform == "win32" and raw in {DEFAULT_SOCKET, f"unix://{DEFAULT_SOCKET}"}:
        return WINDOWS_NPIPE

    # Still return a unix URL so connection errors surface as unavailable,
    # not as "not configured".
    return f"unix://{Path(raw).as_posix()}"


def socket_appears_available(socket_path: str | None) -> bool:
    url = resolve_docker_url(socket_path)
    if not url:
        return False
    if url.startswith("unix://"):
        return Path(url.removeprefix("unix://")).exists()
    if url.startswith("npipe://"):
        return sys.platform == "win32"
    return True


def _build_connection(socket_path: str | None) -> DockerConnection | None:
    url = resolve_docker_url(socket_path)
    if not url:
        return None

    if url.startswith("unix://"):
        path = url.removeprefix("unix://")
        return DockerConnection(
            base_url="http://docker.local",
            transport=httpx.AsyncHTTPTransport(uds=path),
        )

    if url.startswith("npipe://"):
        # httpx cannot speak Windows named pipes; use the Docker SDK in a thread.
        return DockerConnection(base_url=url, transport=None)

    if url.startswith("tcp://"):
        return DockerConnection(base_url="http://" + url.removeprefix("tcp://"))

    return DockerConnection(base_url=url)


class DockerEngineError(Exception):
    pass


class DockerEngineClient:
    """Minimal read-only Docker Engine wrapper."""

    def __init__(self, socket_path: str | None, timeout: float = 5.0) -> None:
        self.socket_path = socket_path
        self.timeout = timeout
        self._connection = _build_connection(socket_path)

    @property
    def configured(self) -> bool:
        return self._connection is not None

    async def _sdk_get_json(
        self, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        def _call() -> Any:
            try:
                import docker  # type: ignore[import-untyped]
            except ImportError as exc:
                raise DockerEngineError(
                    "Docker named-pipe support requires the 'docker' package"
                ) from exc
            try:
                client = docker.DockerClient(
                    base_url=self._connection.base_url,
                    timeout=self.timeout,
                )
                try:
                    api = client.api
                    if path == "/version":
                        return api.version()
                    if path == "/info":
                        return api.info()
                    if path.startswith("/containers/json"):
                        return api.containers(all=True)
                    if path.startswith("/images/json"):
                        return api.images()
                    if path.startswith("/volumes"):
                        return api.volumes()
                    if "/stats" in path:
                        container_id = path.split("/")[2]
                        return api.stats(container_id, stream=False)
                    if path.startswith("/containers/") and path.endswith("/json"):
                        container_id = path.split("/")[2]
                        return api.inspect_container(container_id)
                    raise DockerEngineError(f"Unsupported Docker SDK path: {path}")
                finally:
                    client.close()
            except DockerEngineError:
                raise
            except Exception as exc:  # noqa: BLE001 - normalize SDK failures
                raise DockerEngineError(str(exc)) from exc

        return await asyncio.to_thread(_call)

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if self._connection is None:
            raise DockerEngineError("Docker is not configured")

        if self._connection.base_url.startswith("npipe://"):
            return await self._sdk_get_json(path, params)

        try:
            async with httpx.AsyncClient(
                transport=self._connection.transport,
                base_url=self._connection.base_url,
                timeout=self.timeout,
            ) as client:
                response = await client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise DockerEngineError(str(exc)) from exc

        if response.status_code >= 400:
            raise DockerEngineError(f"Docker API returned HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise DockerEngineError("Docker API returned invalid JSON") from exc

    async def version(self) -> dict[str, Any]:
        data = await self.get_json("/version")
        if not isinstance(data, dict):
            raise DockerEngineError("Malformed /version response")
        return data

    async def info(self) -> dict[str, Any]:
        data = await self.get_json("/info")
        if not isinstance(data, dict):
            raise DockerEngineError("Malformed /info response")
        return data

    async def containers(self, all_containers: bool = True) -> list[dict[str, Any]]:
        data = await self.get_json(
            "/containers/json",
            params={"all": "true" if all_containers else "false"},
        )
        if not isinstance(data, list):
            raise DockerEngineError("Malformed /containers/json response")
        return [item for item in data if isinstance(item, dict)]

    async def images(self) -> list[dict[str, Any]]:
        data = await self.get_json("/images/json")
        if not isinstance(data, list):
            raise DockerEngineError("Malformed /images/json response")
        return [item for item in data if isinstance(item, dict)]

    async def volumes(self) -> dict[str, Any]:
        data = await self.get_json("/volumes")
        if not isinstance(data, dict):
            raise DockerEngineError("Malformed /volumes response")
        return data

    async def inspect_container(self, container_id: str) -> dict[str, Any]:
        data = await self.get_json(f"/containers/{container_id}/json")
        if not isinstance(data, dict):
            raise DockerEngineError("Malformed container inspect response")
        return data

    async def container_stats(self, container_id: str) -> dict[str, Any]:
        data = await self.get_json(
            f"/containers/{container_id}/stats", params={"stream": "false"}
        )
        if not isinstance(data, dict):
            raise DockerEngineError("Malformed container stats response")
        return data


def format_bytes(num: float | None) -> str | None:
    if num is None:
        return None
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def format_uptime_from_status(
    status: str | None, started_at: str | None = None
) -> str | None:
    if status and status.lower().startswith("up "):
        return status
    if not started_at or started_at.startswith("0001"):
        return None
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    seconds = max(0, int((datetime.now(UTC) - started.astimezone(UTC)).total_seconds()))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"Up {days}d {hours}h"
    if hours:
        return f"Up {hours}h {minutes}m"
    return f"Up {minutes}m"


def cpu_percent_from_stats(stats: dict[str, Any]) -> float | None:
    try:
        cpu = stats["cpu_stats"]
        precpu = stats["precpu_stats"]
        cpu_delta = float(cpu["cpu_usage"]["total_usage"]) - float(
            precpu["cpu_usage"]["total_usage"]
        )
        system_delta = float(cpu["system_cpu_usage"]) - float(
            precpu["system_cpu_usage"]
        )
        per_cpu = cpu["cpu_usage"].get("percpu_usage") or []
        online = float(cpu.get("online_cpus") or len(per_cpu) or 1)
        if cpu_delta > 0 and system_delta > 0:
            return round((cpu_delta / system_delta) * online * 100.0, 1)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None
    return None


def memory_from_stats(stats: dict[str, Any]) -> tuple[int | None, int | None]:
    try:
        usage = stats.get("memory_stats", {}).get("usage")
        limit = stats.get("memory_stats", {}).get("limit")
        return (
            int(usage) if usage is not None else None,
            int(limit) if limit is not None else None,
        )
    except (TypeError, ValueError):
        return None, None


def sanitize_ports(raw_ports: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_ports, list):
        return []
    ports: list[dict[str, Any]] = []
    for item in raw_ports:
        if not isinstance(item, dict):
            continue
        private = item.get("PrivatePort")
        if private is None:
            continue
        public = item.get("PublicPort")
        ptype = str(item.get("Type") or "tcp")
        ip = item.get("IP")
        if public:
            display = f"{public}->{private}/{ptype}"
        else:
            display = f"{private}/{ptype}"
        ports.append(
            {
                "private_port": int(private),
                "public_port": int(public) if public else None,
                "type": ptype,
                "ip": str(ip) if ip else None,
                "display": display,
            }
        )
    return ports


def container_name(raw: dict[str, Any]) -> str:
    names = raw.get("Names")
    if isinstance(names, list) and names:
        name = str(names[0])
        return name[1:] if name.startswith("/") else name
    return str(raw.get("Id") or "unknown")[:12]


def status_tone(state: str) -> str:
    normalized = state.lower()
    if normalized == "running":
        return "good"
    if normalized in {"restarting", "paused"}:
        return "warn"
    if normalized in {"exited", "dead"}:
        return "bad"
    return "muted"
