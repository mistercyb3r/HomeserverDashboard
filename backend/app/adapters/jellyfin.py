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
from app.schemas import Metric, PlaybackSession, ServiceSnapshot, ServiceStatus


def _ticks_to_display(ticks: Any) -> str | None:
    """Convert Jellyfin ticks (100-ns) to a compact duration string."""
    try:
        total_seconds = int(ticks) // 10_000_000
    except (TypeError, ValueError):
        return None
    if total_seconds < 0:
        return None
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m"
    return f"{seconds}s"


def _episode_subtitle(item: dict[str, Any]) -> str | None:
    season = item.get("ParentIndexNumber")
    episode = item.get("IndexNumber")
    episode_name = item.get("Name")
    parts: list[str] = []
    if season is not None and episode is not None:
        try:
            parts.append(f"S{int(season):02d} E{int(episode):02d}")
        except (TypeError, ValueError):
            parts.append(f"S{season} E{episode}")
    elif episode_name:
        parts.append(str(episode_name))
    if season is not None and episode is not None and episode_name:
        # Prefer "S01 E03 · Episode Title" when both exist.
        return f"{parts[0]} · {episode_name}"
    return parts[0] if parts else None


def parse_active_playback(sessions: Any) -> list[PlaybackSession]:
    """Extract currently playing items only — safe display fields."""
    if not isinstance(sessions, list):
        return []

    rows: list[PlaybackSession] = []
    for index, session in enumerate(sessions):
        if not isinstance(session, dict):
            continue
        item = session.get("NowPlayingItem")
        if not isinstance(item, dict):
            continue

        play_state = session.get("PlayState") or {}
        if not isinstance(play_state, dict):
            play_state = {}

        user = (
            session.get("UserName")
            or session.get("UserId")
            or session.get("DeviceName")
            or "Unknown"
        )
        item_type = str(item.get("Type") or "")
        series = item.get("SeriesName")
        if item_type == "Episode" and series:
            title = str(series)
            subtitle = _episode_subtitle(item)
        else:
            title = str(item.get("Name") or "Untitled")
            subtitle = None
            year = item.get("ProductionYear")
            if year:
                subtitle = str(year)

        progress = _ticks_to_display(play_state.get("PositionTicks"))
        paused = bool(play_state.get("IsPaused"))
        item_id = item.get("Id")
        artwork_url = None
        image_tags = item.get("ImageTags") or {}
        if item_id and isinstance(image_tags, dict) and image_tags.get("Primary"):
            artwork_url = f"/api/jellyfin/artwork/{item_id}"

        rows.append(
            PlaybackSession(
                id=str(session.get("Id") or item_id or index),
                user=str(user),
                title=title,
                subtitle=subtitle,
                progress=progress,
                paused=paused,
                artwork_url=artwork_url,
            )
        )
    return rows


def summarize_sessions(sessions: Any) -> tuple[int, int]:
    if not isinstance(sessions, list):
        return 0, 0
    playing = parse_active_playback(sessions)
    user_ids: set[str] = set()
    for session in sessions:
        if not isinstance(session, dict):
            continue
        user_id = session.get("UserId") or session.get("UserName")
        if user_id:
            user_ids.add(str(user_id))
    return len(playing), len(user_ids)


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

        now_playing: list[PlaybackSession] | None = None
        streams: int | None = None
        users: int | None = None
        version = None

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, headers=headers
            ) as client:
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

                if self._api_key:
                    sessions_resp = await client.get(f"{self._base_url}/Sessions")
                    if sessions_resp.status_code == 200:
                        sessions = sessions_resp.json()
                        now_playing = parse_active_playback(sessions)
                        streams, users = summarize_sessions(sessions)
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
                display=None if streams is None else f"{streams} streaming",
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
                primary=now_playing is None,
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

        if streams and streams > 0:
            status_label = f"Online · {streams} streaming"
        else:
            status_label = "Online"

        return ServiceSnapshot(
            id=self.id,
            name=self.name,
            description=self.description,
            icon=self.icon,
            status=ServiceStatus.ONLINE,
            status_label=status_label,
            metrics=metrics,
            version=version,
            url=self._base_url,
            href=self._base_url,
            open_label="Open Jellyfin",
            now_playing=now_playing,
            last_updated=utcnow(),
            last_success_at=utcnow(),
            configured=True,
            error=None if self._api_key else "Streams require JELLYFIN_API_KEY",
        )
