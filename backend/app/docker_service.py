"""Assemble sanitized Docker detail payloads for the /docker page."""

from __future__ import annotations

import asyncio
from typing import Any

from app.adapters.base import utcnow
from app.docker_engine import (
    DockerEngineClient,
    DockerEngineError,
    container_name,
    cpu_percent_from_stats,
    format_bytes,
    format_uptime_from_status,
    memory_from_stats,
    sanitize_ports,
    status_tone,
)
from app.schemas import (
    DockerContainer,
    DockerDetailResponse,
    DockerOverview,
    DockerPort,
)


def _empty_detail(*, configured: bool, error: str | None) -> DockerDetailResponse:
    return DockerDetailResponse(
        available=False,
        configured=configured,
        generated_at=utcnow(),
        error=error,
        overview=None,
        containers=[],
    )


async def collect_docker_detail(
    *,
    enabled: bool,
    socket_path: str | None,
    timeout: float = 5.0,
) -> DockerDetailResponse:
    if not enabled or not socket_path:
        return _empty_detail(
            configured=False,
            error="Docker is not configured",
        )

    client = DockerEngineClient(socket_path, timeout=timeout)
    try:
        version_data, info_data, containers_raw = await asyncio.gather(
            client.version(),
            client.info(),
            client.containers(all_containers=True),
        )
    except DockerEngineError as exc:
        return _detail_from_engine_error(exc)
    except Exception as exc:  # noqa: BLE001 - never 500 the dashboard on Docker I/O
        return _empty_detail(configured=True, error=str(exc) or "Docker unavailable")

    images_count: int | None = None
    volumes_count: int | None = None
    try:
        images_count = len(await client.images())
    except DockerEngineError:
        images_count = info_data.get("Images")
        if images_count is not None:
            try:
                images_count = int(images_count)
            except (TypeError, ValueError):
                images_count = None
    except Exception:  # noqa: BLE001
        images_count = None
    try:
        volumes_payload = await client.volumes()
        volumes = volumes_payload.get("Volumes") or []
        volumes_count = len(volumes) if isinstance(volumes, list) else None
    except Exception:  # noqa: BLE001
        volumes_count = None

    running = stopped = restarting = paused = 0
    for item in containers_raw:
        state = str(item.get("State") or "").lower()
        if state == "running":
            running += 1
        elif state == "restarting":
            restarting += 1
        elif state == "paused":
            paused += 1
        else:
            stopped += 1

    overview = DockerOverview(
        daemon_status="online",
        version=version_data.get("Version"),
        api_version=version_data.get("ApiVersion"),
        running=running,
        stopped=stopped,
        restarting=restarting,
        paused=paused,
        total=len(containers_raw),
        images=images_count,
        volumes=volumes_count,
        containers_from_info=info_data.get("Containers"),
    )

    enrich_ids = [
        str(item.get("Id"))
        for item in containers_raw
        if item.get("Id")
        and str(item.get("State") or "").lower() in {"running", "restarting"}
    ]
    try:
        inspect_map, stats_map = await _enrich_containers(client, enrich_ids)
    except Exception:  # noqa: BLE001 - detail page still useful without enrichment
        inspect_map, stats_map = {}, {}

    containers = [
        _to_container(item, inspect_map, stats_map) for item in containers_raw
    ]
    order = {"running": 0, "restarting": 1, "paused": 2, "exited": 3, "dead": 4}
    containers.sort(key=lambda c: (order.get(c.state.lower(), 9), c.name.lower()))

    return DockerDetailResponse(
        available=True,
        configured=True,
        generated_at=utcnow(),
        error=None,
        overview=overview,
        containers=containers,
    )


def _detail_from_engine_error(exc: DockerEngineError) -> DockerDetailResponse:
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
        return _empty_detail(configured=False, error="Docker socket not available")
    return _empty_detail(configured=True, error=message or "Docker unavailable")


async def _enrich_containers(
    client: DockerEngineClient,
    container_ids: list[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    inspect_map: dict[str, dict[str, Any]] = {}
    stats_map: dict[str, dict[str, Any]] = {}

    async def _inspect(cid: str) -> None:
        try:
            inspect_map[cid] = await client.inspect_container(cid)
        except DockerEngineError:
            return

    async def _stats(cid: str) -> None:
        try:
            stats_map[cid] = await client.container_stats(cid)
        except DockerEngineError:
            return

    await asyncio.gather(
        *[_inspect(cid) for cid in container_ids], return_exceptions=True
    )
    await asyncio.gather(
        *[_stats(cid) for cid in container_ids], return_exceptions=True
    )
    return inspect_map, stats_map


def _to_container(
    raw: dict[str, Any],
    inspect_map: dict[str, dict[str, Any]],
    stats_map: dict[str, dict[str, Any]],
) -> DockerContainer:
    cid = str(raw.get("Id") or "")
    state = str(raw.get("State") or "unknown")
    status = str(raw.get("Status") or state)
    inspect = inspect_map.get(cid) or {}
    stats = stats_map.get(cid) or {}

    restart_count = None
    exit_code = None
    started_at = None
    if inspect:
        restart_count = inspect.get("RestartCount")
        state_block = inspect.get("State") or {}
        if isinstance(state_block, dict):
            exit_code = state_block.get("ExitCode")
            started_at = state_block.get("StartedAt")

    if exit_code is None and "Exited (" in status:
        try:
            exit_code = int(status.split("Exited (", 1)[1].split(")", 1)[0])
        except (IndexError, ValueError):
            exit_code = None

    cpu = cpu_percent_from_stats(stats) if stats else None
    mem_usage, mem_limit = memory_from_stats(stats) if stats else (None, None)
    mem_display = format_bytes(mem_usage) if mem_usage is not None else "Unavailable"

    uptime = format_uptime_from_status(
        status, started_at if isinstance(started_at, str) else None
    )
    if state.lower() not in {"running", "restarting"}:
        uptime = status

    ports = [DockerPort(**port) for port in sanitize_ports(raw.get("Ports"))]

    return DockerContainer(
        id=cid[:12],
        name=container_name(raw),
        image=str(raw.get("Image") or "unknown"),
        state=state,
        status=status,
        status_tone=status_tone(state),
        uptime=uptime,
        cpu_percent=cpu,
        cpu_display="Unavailable" if cpu is None else f"{cpu:.1f}%",
        memory_usage=mem_usage,
        memory_limit=mem_limit,
        memory_display=mem_display or "Unavailable",
        restart_count=int(restart_count) if restart_count is not None else None,
        ports=ports,
        exit_code=int(exit_code) if exit_code is not None else None,
    )
