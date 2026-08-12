"""Adapter registry and future-service catalog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.adapters.base import ServiceAdapter
from app.adapters.docker import DockerAdapter
from app.adapters.jellyfin import JellyfinAdapter
from app.adapters.portainer import PortainerAdapter
from app.adapters.server import ServerAdapter
from app.adapters.starlink import StarlinkAdapter
from app.adapters.starpulse import StarPulseAdapter
from app.config import Settings
from app.config_store import ConfigStore
from app.docker_engine import DEFAULT_SOCKET
from app.schemas import ServiceDefinition


@dataclass(frozen=True)
class ServiceMeta:
    id: str
    name: str
    description: str
    icon: str
    implemented: bool
    configurable: bool = True
    config_kind: str = "url"


SERVICE_CATALOG: list[ServiceMeta] = [
    ServiceMeta("server", "Server", "Host system metrics", "server", True, False),
    ServiceMeta("jellyfin", "Jellyfin", "Media server", "play", True),
    ServiceMeta(
        "starpulse", "StarPulse", "Starlink telemetry dashboard", "satellite", True
    ),
    ServiceMeta("starlink", "Starlink", "Dish connection via StarPulse", "wifi", True),
    ServiceMeta(
        "docker",
        "Docker",
        "Container runtime",
        "box",
        True,
        True,
        "socket",
    ),
    ServiceMeta("portainer", "Portainer", "Container management UI", "layout", True),
    ServiceMeta("transmission", "Transmission", "Torrent client", "download", False),
    ServiceMeta("homeassistant", "Home Assistant", "Home automation", "home", False),
    ServiceMeta("plex", "Plex", "Media server", "play", False),
    ServiceMeta("nextcloud", "Nextcloud", "Files and collaboration", "cloud", False),
    ServiceMeta("immich", "Immich", "Photo library", "image", False),
    ServiceMeta("ollama", "Ollama", "Local LLMs", "cpu", False),
    ServiceMeta("uptimekuma", "Uptime Kuma", "Uptime monitoring", "activity", False),
    ServiceMeta("pihole", "Pi-hole", "DNS ad blocking", "shield", False),
    ServiceMeta("adguard", "AdGuard Home", "DNS ad blocking", "shield", False),
    ServiceMeta("syncthing", "Syncthing", "File sync", "refresh", False),
    ServiceMeta("prometheus", "Prometheus / Grafana", "Metrics stack", "chart", False),
]


class AdapterRegistry:
    def __init__(
        self, adapters: dict[str, ServiceAdapter], catalog: list[ServiceMeta]
    ) -> None:
        self._adapters = adapters
        self._catalog = catalog

    def get(self, service_id: str) -> ServiceAdapter | None:
        return self._adapters.get(service_id)

    def enabled_adapters(self, config: dict[str, Any]) -> list[ServiceAdapter]:
        services = config.get("services") or {}
        enabled: list[ServiceAdapter] = []
        for meta in self._catalog:
            if not meta.implemented:
                continue
            entry = services.get(meta.id) or {}
            if entry.get("enabled", True) and meta.id in self._adapters:
                enabled.append(self._adapters[meta.id])
        return enabled

    def definitions(
        self, config: dict[str, Any], settings: Settings
    ) -> list[ServiceDefinition]:
        services = config.get("services") or {}
        defs: list[ServiceDefinition] = []
        for meta in self._catalog:
            entry = services.get(meta.id) or {
                "enabled": False,
                "url": None,
                "socket": None,
            }
            adapter = self._adapters.get(meta.id)
            configured = adapter.is_configured() if adapter else False
            url = entry.get("url")
            if not url and adapter and meta.config_kind == "url":
                url = adapter.open_url()
                if url and url.startswith("/"):
                    url = None
            socket = entry.get("socket")
            if meta.id == "docker" and not socket:
                socket = settings.docker_socket or DEFAULT_SOCKET
            has_secret = False
            if meta.id == "jellyfin":
                has_secret = bool(settings.jellyfin_api_key)
            defs.append(
                ServiceDefinition(
                    id=meta.id,
                    name=meta.name,
                    description=meta.description,
                    icon=meta.icon,
                    enabled=bool(entry.get("enabled", False)),
                    configured=configured,
                    configurable=meta.configurable,
                    implemented=meta.implemented,
                    url=url,
                    socket=socket,
                    config_kind=meta.config_kind,
                    has_secret=has_secret,
                )
            )
        return defs


def _resolve_url(
    config: dict[str, Any], service_id: str, fallback: str | None
) -> str | None:
    entry = (config.get("services") or {}).get(service_id) or {}
    url = entry.get("url")
    if url:
        return str(url).rstrip("/")
    return (fallback or "").rstrip("/") or None


def _resolve_socket(config: dict[str, Any], settings: Settings) -> str | None:
    entry = (config.get("services") or {}).get("docker") or {}
    socket = entry.get("socket") or settings.docker_socket or DEFAULT_SOCKET
    return str(socket) if socket else None


def build_registry(settings: Settings, store: ConfigStore) -> AdapterRegistry:
    config = store.read()
    jellyfin_url = _resolve_url(config, "jellyfin", settings.jellyfin_url)
    starpulse_url = _resolve_url(config, "starpulse", settings.starpulse_url)
    starlink_source = _resolve_url(config, "starlink", starpulse_url)
    portainer_url = _resolve_url(config, "portainer", settings.portainer_url)
    docker_entry = (config.get("services") or {}).get("docker") or {}
    docker_enabled = bool(docker_entry.get("enabled", False))
    docker_socket = _resolve_socket(config, settings)

    adapters: dict[str, ServiceAdapter] = {
        "server": ServerAdapter(),
        "jellyfin": JellyfinAdapter(
            base_url=jellyfin_url,
            api_key=settings.jellyfin_api_key,
            timeout=settings.http_timeout_seconds,
        ),
        "starpulse": StarPulseAdapter(
            base_url=starpulse_url,
            timeout=settings.http_timeout_seconds,
        ),
        "starlink": StarlinkAdapter(
            starpulse_url=starlink_source,
            timeout=settings.http_timeout_seconds,
        ),
        "docker": DockerAdapter(
            enabled=docker_enabled,
            socket_path=docker_socket,
            timeout=settings.http_timeout_seconds,
        ),
        "portainer": PortainerAdapter(
            base_url=portainer_url,
            timeout=settings.http_timeout_seconds,
        ),
    }
    return AdapterRegistry(adapters, SERVICE_CATALOG)
