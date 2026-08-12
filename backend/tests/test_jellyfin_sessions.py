"""Jellyfin now-playing / Sessions parsing tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.jellyfin import (
    JellyfinAdapter,
    parse_active_playback,
    summarize_sessions,
)
from app.schemas import ServiceStatus


def _movie_session(
    *,
    user: str = "Aurimas",
    title: str = "Interstellar",
    item_id: str = "movie1",
    position_ticks: int = 46_800_000_000,  # 1h 18m
    has_art: bool = True,
) -> dict:
    tags = {"Primary": "abc"} if has_art else {}
    return {
        "Id": f"sess-{item_id}",
        "UserName": user,
        "NowPlayingItem": {
            "Id": item_id,
            "Name": title,
            "Type": "Movie",
            "ProductionYear": 2014,
            "ImageTags": tags,
        },
        "PlayState": {"PositionTicks": position_ticks, "IsPaused": False},
    }


def _episode_session() -> dict:
    return {
        "Id": "sess-ep1",
        "UserName": "Aurimas",
        "NowPlayingItem": {
            "Id": "ep1",
            "Name": "Long, Long Time",
            "Type": "Episode",
            "SeriesName": "The Last of Us",
            "ParentIndexNumber": 1,
            "IndexNumber": 3,
            "ImageTags": {"Primary": "xyz"},
        },
        "PlayState": {
            "PositionTicks": 25_200_000_000,  # 42m
            "IsPaused": False,
        },
    }


def test_no_active_streams():
    sessions = [
        {"Id": "idle", "UserName": "Aurimas", "NowPlayingItem": None},
        {"Id": "idle2", "UserName": "Sandra"},
    ]
    assert parse_active_playback(sessions) == []
    streams, users = summarize_sessions(sessions)
    assert streams == 0
    assert users == 2


def test_one_active_movie():
    rows = parse_active_playback([_movie_session()])
    assert len(rows) == 1
    assert rows[0].user == "Aurimas"
    assert rows[0].title == "Interstellar"
    assert rows[0].progress == "1h 18m"
    assert rows[0].artwork_url == "/api/jellyfin/artwork/movie1"


def test_multiple_active_sessions():
    rows = parse_active_playback(
        [
            _episode_session(),
            _movie_session(user="Sandra", title="Interstellar", item_id="m2"),
        ]
    )
    assert len(rows) == 2
    assert {r.user for r in rows} == {"Aurimas", "Sandra"}


def test_tv_episode_metadata():
    rows = parse_active_playback([_episode_session()])
    assert rows[0].title == "The Last of Us"
    assert rows[0].subtitle == "S01 E03 · Long, Long Time"
    assert rows[0].progress == "42m"


def test_missing_artwork():
    rows = parse_active_playback([_movie_session(has_art=False)])
    assert rows[0].artwork_url is None
    assert rows[0].title == "Interstellar"


@pytest.mark.asyncio
async def test_jellyfin_unavailable():
    adapter = JellyfinAdapter(
        base_url="http://jellyfin.local", api_key="secret", timeout=1.0
    )
    import httpx

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("offline"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.adapters.jellyfin.httpx.AsyncClient", return_value=mock_client):
        snap = await adapter.fetch()

    assert snap.status == ServiceStatus.DEGRADED
    assert snap.now_playing is None
    assert "secret" not in (snap.error or "")


@pytest.mark.asyncio
async def test_api_key_unavailable_omits_now_playing():
    adapter = JellyfinAdapter(
        base_url="http://jellyfin.local", api_key=None, timeout=1.0
    )

    ping = MagicMock()
    ping.status_code = 200
    public = MagicMock()
    public.status_code = 200
    public.json.return_value = {"Version": "10.9.0"}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[ping, public])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.adapters.jellyfin.httpx.AsyncClient", return_value=mock_client):
        snap = await adapter.fetch()

    assert snap.status == ServiceStatus.ONLINE
    assert snap.now_playing is None
    assert snap.error is not None
    assert "API_KEY" in (snap.error or "")


@pytest.mark.asyncio
async def test_adapter_returns_active_sessions_without_leaking_key():
    adapter = JellyfinAdapter(
        base_url="http://jellyfin.local", api_key="super-secret-key", timeout=1.0
    )

    info = MagicMock()
    info.status_code = 200
    info.json.return_value = {"Version": "10.9.0"}
    sessions = MagicMock()
    sessions.status_code = 200
    sessions.json.return_value = [_episode_session(), _movie_session(user="Sandra")]

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[info, sessions])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.adapters.jellyfin.httpx.AsyncClient", return_value=mock_client):
        snap = await adapter.fetch()

    assert snap.status == ServiceStatus.ONLINE
    assert snap.status_label == "Online · 2 streaming"
    assert snap.now_playing is not None
    assert len(snap.now_playing) == 2
    payload = snap.model_dump()
    assert "super-secret-key" not in str(payload)
    assert all(
        (row.artwork_url or "").startswith("/api/jellyfin/artwork/")
        for row in snap.now_playing
    )


@pytest.mark.asyncio
async def test_adapter_empty_sessions_list():
    adapter = JellyfinAdapter(
        base_url="http://jellyfin.local", api_key="key", timeout=1.0
    )
    info = MagicMock()
    info.status_code = 200
    info.json.return_value = {"Version": "10.9.0"}
    sessions = MagicMock()
    sessions.status_code = 200
    sessions.json.return_value = [{"Id": "x", "UserName": "A"}]

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[info, sessions])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.adapters.jellyfin.httpx.AsyncClient", return_value=mock_client):
        snap = await adapter.fetch()

    assert snap.now_playing == []
    assert snap.status_label == "Online"
