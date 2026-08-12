"""Adapter package."""

from app.adapters.base import ServiceAdapter
from app.adapters.docker import DockerAdapter
from app.adapters.jellyfin import JellyfinAdapter
from app.adapters.portainer import PortainerAdapter
from app.adapters.registry import AdapterRegistry, build_registry
from app.adapters.server import ServerAdapter
from app.adapters.starlink import StarlinkAdapter
from app.adapters.starpulse import StarPulseAdapter
from app.adapters.tailscale import TailscaleAdapter

__all__ = [
    "AdapterRegistry",
    "DockerAdapter",
    "JellyfinAdapter",
    "PortainerAdapter",
    "ServerAdapter",
    "ServiceAdapter",
    "StarPulseAdapter",
    "StarlinkAdapter",
    "TailscaleAdapter",
    "build_registry",
]
