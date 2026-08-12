"""HTTP API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app import __version__
from app.adapters.registry import AdapterRegistry, build_registry
from app.config import Settings, get_settings
from app.config_store import ConfigStore
from app.dashboard import collect_dashboard
from app.docker_engine import DEFAULT_SOCKET
from app.docker_service import collect_docker_detail
from app.schemas import (
    DashboardResponse,
    DockerDetailResponse,
    ServiceSnapshot,
    SettingsResponse,
    SettingsUpdateRequest,
)

router = APIRouter(prefix="/api")


def get_store(request: Request) -> ConfigStore:
    return request.app.state.store


def get_registry(
    request: Request, settings: Settings = Depends(get_settings)
) -> AdapterRegistry:
    store: ConfigStore = request.app.state.store
    return build_registry(settings, store)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    settings: Settings = Depends(get_settings),
    store: ConfigStore = Depends(get_store),
    registry: AdapterRegistry = Depends(get_registry),
) -> DashboardResponse:
    config = store.read()
    server_name = config.get("server_name") or settings.server_name
    return await collect_dashboard(
        registry=registry, config=config, server_name=server_name
    )


@router.get("/services/{service_id}", response_model=ServiceSnapshot)
async def service_detail(
    service_id: str,
    store: ConfigStore = Depends(get_store),
    registry: AdapterRegistry = Depends(get_registry),
) -> ServiceSnapshot:
    config = store.read()
    adapter = registry.get(service_id)
    if adapter is None:
        raise HTTPException(status_code=404, detail="Unknown service")
    services = config.get("services") or {}
    entry = services.get(service_id) or {}
    if not entry.get("enabled", True):
        raise HTTPException(status_code=404, detail="Service disabled")
    return await adapter.fetch()


@router.get("/docker", response_model=DockerDetailResponse)
async def docker_detail(
    settings: Settings = Depends(get_settings),
    store: ConfigStore = Depends(get_store),
) -> DockerDetailResponse:
    config = store.read()
    entry = (config.get("services") or {}).get("docker") or {}
    enabled = bool(entry.get("enabled", False))
    socket = entry.get("socket") or settings.docker_socket or DEFAULT_SOCKET
    return await collect_docker_detail(
        enabled=enabled,
        socket_path=socket,
        timeout=settings.http_timeout_seconds,
    )


@router.get("/settings", response_model=SettingsResponse)
async def get_settings_route(
    settings: Settings = Depends(get_settings),
    store: ConfigStore = Depends(get_store),
    registry: AdapterRegistry = Depends(get_registry),
) -> SettingsResponse:
    config = store.read()
    return SettingsResponse(
        server_name=config.get("server_name") or settings.server_name,
        refresh_interval_seconds=int(config.get("refresh_interval_seconds") or 10),
        services=registry.definitions(config, settings),
    )


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(
    payload: SettingsUpdateRequest,
    settings: Settings = Depends(get_settings),
    store: ConfigStore = Depends(get_store),
    registry: AdapterRegistry = Depends(get_registry),
) -> SettingsResponse:
    services_patch: dict[str, dict] = {}
    if payload.services:
        for service_id, update in payload.services.items():
            services_patch[service_id] = update.model_dump(exclude_unset=True)

    config = store.update(
        {
            "server_name": payload.server_name,
            "refresh_interval_seconds": payload.refresh_interval_seconds,
            "services": services_patch,
        }
    )
    registry = build_registry(settings, store)
    return SettingsResponse(
        server_name=config.get("server_name") or settings.server_name,
        refresh_interval_seconds=int(config.get("refresh_interval_seconds") or 10),
        services=registry.definitions(config, settings),
    )
