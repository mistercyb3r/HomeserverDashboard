"""Persistent non-secret configuration stored under /data."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from threading import Lock
from typing import Any

from app.config import Settings
from app.docker_engine import DEFAULT_SOCKET

DEFAULT_CONFIG: dict[str, Any] = {
    "server_name": "Home Server",
    "refresh_interval_seconds": 10,
    "services": {
        "server": {"enabled": True, "url": None, "socket": None},
        "jellyfin": {"enabled": True, "url": None, "socket": None},
        "starpulse": {"enabled": True, "url": None, "socket": None},
        "starlink": {"enabled": True, "url": None, "socket": None},
        "docker": {"enabled": True, "url": None, "socket": DEFAULT_SOCKET},
        "portainer": {"enabled": True, "url": None, "socket": None},
        "router": {"enabled": True, "url": None, "socket": None},
        "tailscale": {
            "enabled": True,
            "url": None,
            "socket": "/var/run/tailscale/tailscaled.sock",
        },
        # Future adapters — listed for settings UI, not implemented yet.
        "transmission": {"enabled": False, "url": None, "socket": None},
        "homeassistant": {"enabled": False, "url": None, "socket": None},
        "plex": {"enabled": False, "url": None, "socket": None},
        "nextcloud": {"enabled": False, "url": None, "socket": None},
        "immich": {"enabled": False, "url": None, "socket": None},
        "ollama": {"enabled": False, "url": None, "socket": None},
        "uptimekuma": {"enabled": False, "url": None, "socket": None},
        "pihole": {"enabled": False, "url": None, "socket": None},
        "adguard": {"enabled": False, "url": None, "socket": None},
        "syncthing": {"enabled": False, "url": None, "socket": None},
        "prometheus": {"enabled": False, "url": None, "socket": None},
    },
}

_lock = Lock()


def _normalize_entry(
    defaults: dict[str, Any], override: dict[str, Any]
) -> dict[str, Any]:
    entry = deepcopy(defaults)
    entry["enabled"] = bool(override.get("enabled", defaults.get("enabled", False)))
    url = override.get("url", defaults.get("url"))
    entry["url"] = None if url in (None, "") else str(url).rstrip("/")
    socket = override.get("socket", defaults.get("socket"))
    entry["socket"] = None if socket in (None, "") else str(socket)
    return entry


class ConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._ensure()

    def _ensure(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.write(deepcopy(DEFAULT_CONFIG))

    def read(self) -> dict[str, Any]:
        with _lock:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        return self._merge_defaults(raw)

    def write(self, data: dict[str, Any]) -> None:
        with _lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        current = self.read()
        if "server_name" in patch and patch["server_name"] is not None:
            current["server_name"] = (
                str(patch["server_name"]).strip() or current["server_name"]
            )
        if (
            "refresh_interval_seconds" in patch
            and patch["refresh_interval_seconds"] is not None
        ):
            current["refresh_interval_seconds"] = int(patch["refresh_interval_seconds"])
        services_patch = patch.get("services") or {}
        for service_id, updates in services_patch.items():
            if service_id not in current["services"]:
                current["services"][service_id] = {
                    "enabled": False,
                    "url": None,
                    "socket": None,
                }
            entry = current["services"][service_id]
            if isinstance(updates, dict):
                if "enabled" in updates and updates["enabled"] is not None:
                    entry["enabled"] = bool(updates["enabled"])
                if "url" in updates:
                    url = updates["url"]
                    entry["url"] = None if url in (None, "") else str(url).rstrip("/")
                if "socket" in updates:
                    socket = updates["socket"]
                    entry["socket"] = None if socket in (None, "") else str(socket)
        self.write(current)
        return current

    @staticmethod
    def _merge_defaults(raw: dict[str, Any]) -> dict[str, Any]:
        merged = deepcopy(DEFAULT_CONFIG)
        merged["server_name"] = raw.get("server_name") or merged["server_name"]
        merged["refresh_interval_seconds"] = int(
            raw.get("refresh_interval_seconds") or merged["refresh_interval_seconds"]
        )
        raw_services = raw.get("services") or {}
        for service_id, defaults in DEFAULT_CONFIG["services"].items():
            override = raw_services.get(service_id) or {}
            merged["services"][service_id] = _normalize_entry(defaults, override)
        for service_id, override in raw_services.items():
            if service_id not in merged["services"]:
                merged["services"][service_id] = _normalize_entry(
                    {"enabled": False, "url": None, "socket": None},
                    override,
                )
        return merged


def build_config_store(settings: Settings) -> ConfigStore:
    return ConfigStore(settings.config_path)
