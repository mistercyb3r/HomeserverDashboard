"""Jellyfin media server adapter."""

from __future__ import annotations

from typing import Any

import httpx

from app.adapters.base import (
    ServiceAdapter,
    metric,
    not_configured_snapshot,
    offline_snapshot,
    utcnow,
)
from app.schemas import Metric, ServiceSnapshot, ServiceStatus


class JellyfinAdapter(ServiceAdapter):
    id = "jellyfin"
    name = "Jellyfin"
    description = "Media server status and active streams"
    icon = "play"

    def __init__(
        self,
        *,
        base_url: str | None,
        api_key: str | None,
        timeout: float = 5.0,
    ) -> None:
        self._base_url = (base_url or "").rstrip("/") or None
        self._api_key = api_key or None
        self._timeout = timeout

    def is_configured(self) -> bool:
        return bool(self._base_url)

    def open_url(self) -> str | None:
        return self._base_url

    async def fetch(self) -> ServiceSnapshot:
        if not self.is_configured():
            return not_configured_snapshot(
                service_id=self.id,
                name=self.name,
                description=self.description,
                icon=self.icon,
                message="Set JELLYFIN_URL (and optionally JELLYFIN_API_KEY)",
            )

        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["X-Emby-Token"] = self._api_key

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, headers=headers
            ) as client:
                version = None
                online = False

                # Prefer authenticated system info when a key is present.
                if self._api_key:
                    info_resp = await client.get(f"{self._base_url}/System/Info")
                    if info_resp.status_code == 200:
                        online = True
                        payload = info_resp.json()
                        version = payload.get("Version")
                    elif info_resp.status_code in {401, 403}:
                        return offline_snapshot(
                            service_id=self.id,
                            name=self.name,
                            description=self.description,
                            icon=self.icon,
                            url=self._base_url,
                            href=self._base_url,
                            open_label="Open Jellyfin",
                            error="Jellyfin rejected the API key",
                            status=ServiceStatus.DEGRADED,
                            status_label="Unable to reach Jellyfin",
                        )

                if not online:
                    ping = await client.get(f"{self._base_url}/System/Ping")
                    if ping.status_code == 200:
                        online = True
                    else:
                        # Some reverse proxies may not expose Ping; try root.
                        root = await client.get(self._base_url)
                        online = root.status_code < 500

                if not online:
                    return offline_snapshot(
                        service_id=self.id,
                        name=self.name,
                        description=self.description,
                        icon=self.icon,
                        url=self._base_url,
                        href=self._base_url,
                        open_label="Open Jellyfin",
                        error=f"Jellyfin unreachable at {self._base_url}",
                        status=ServiceStatus.DEGRADED,
                        status_label="Unable to reach Jellyfin",
                    )

                streams: int | None = None
                users: int | None = None
                if self._api_key:
                    sessions_resp = await client.get(f"{self._base_url}/Sessions")
                    if sessions_resp.status_code == 200:
                        sessions = sessions_resp.json()
                        streams, users = self._summarize_sessions(sessions)
                    if version is None:
                        public = await client.get(
                            f"{self._base_url}/System/Info/Public"
                        )
                        if public.status_code == 200:
                            version = public.json().get("Version")
                else:
                    public = await client.get(f"{self._base_url}/System/Info/Public")
                    if public.status_code == 200:
                        version = public.json().get("Version")

        except httpx.HTTPError as exc:
            return offline_snapshot(
                service_id=self.id,
                name=self.name,
                description=self.description,
                icon=self.icon,
                url=self._base_url,
                href=self._base_url,
                open_label="Open Jellyfin",
                error=str(exc),
                status=ServiceStatus.DEGRADED,
                status_label="Unable to reach Jellyfin",
            )

        metrics: list[Metric] = [
            metric(
                "streams",
                "Active streams",
                streams,
                display=None if streams is None else f"{streams} active streams",
                primary=True,
            ),
            metric(
                "users",
                "Connected users",
                users,
                display=None if users is None else f"{users} users",
                primary=True,
            ),
            metric(
                "version",
                "Version",
                version,
                display=None if version is None else f"v{version}",
                primary=True,
            ),
        ]
        if not self._api_key:
            metrics.append(
                metric(
                    "auth",
                    "API key",
                    None,
                    display="API key not configured",
                    available=False,
                )
            )

        return ServiceSnapshot(
            id=self.id,
            name=self.name,
            description=self.description,
            icon=self.icon,
            status=ServiceStatus.ONLINE,
            status_label="Online",
            metrics=metrics,
            version=version,
            url=self._base_url,
            href=self._base_url,
            open_label="Open Jellyfin",
            last_updated=utcnow(),
            last_success_at=utcnow(),
            configured=True,
            error=None if self._api_key else "Streams require JELLYFIN_API_KEY",
        )

    @staticmethod
    def _summarize_sessions(sessions: Any) -> tuple[int, int]:
        if not isinstance(sessions, list):
            return 0, 0
        active_streams = 0
        user_ids: set[str] = set()
        for session in sessions:
            if not isinstance(session, dict):
                continue
            user_id = session.get("UserId") or session.get("UserName")
            if user_id:
                user_ids.add(str(user_id))
            now_playing = session.get("NowPlayingItem")
            is_playing = bool(
                session.get("PlayState", {}).get("IsPaused") is False and now_playing
            )
            if now_playing or is_playing:
                active_streams += 1
            elif session.get("NowPlayingItem") is not None:
                active_streams += 1
        # Count sessions that have a NowPlayingItem as streams (includes paused).
        if active_streams == 0:
            active_streams = sum(
                1
                for s in sessions
                if isinstance(s, dict) and s.get("NowPlayingItem") is not None
            )
        return active_streams, len(user_ids)
