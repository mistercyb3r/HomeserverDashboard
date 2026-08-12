"""Docker adapter and engine tests."""

from __future__ import annotations

import asyncio
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.adapters.docker import DockerAdapter
from app.docker_engine import (
    DockerEngineClient,
    DockerEngineError,
    cpu_percent_from_stats,
    resolve_docker_url,
    sanitize_ports,
)
from app.docker_service import collect_docker_detail
from app.schemas import ServiceStatus


class _FakeDockerAPI(BaseHTTPRequestHandler):
    """Minimal Docker Engine HTTP surface for regression tests."""

    version_payload = {"Version": "27.0.0", "ApiVersion": "1.46"}
    info_payload = {"Images": 2, "Containers": 1}
    containers_payload = [
        {
            "Id": "abc123456789",
            "Names": ["/jellyfin"],
            "Image": "jellyfin/jellyfin:latest",
            "State": "running",
            "Status": "Up 1 hour",
            "Ports": [],
        }
    ]

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/version":
            body = self.version_payload
        elif path == "/info":
            body = self.info_payload
        elif path == "/containers/json":
            body = self.containers_payload
        elif path == "/images/json":
            body = [{}, {}]
        elif path == "/volumes":
            body = {"Volumes": [{}]}
        else:
            self.send_response(404)
            self.end_headers()
            return
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture()
def fake_docker_http():
    server = HTTPServer(("127.0.0.1", 0), _FakeDockerAPI)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)


@pytest.mark.asyncio
async def test_engine_version_info_containers(fake_docker_http):
    client = DockerEngineClient(fake_docker_http, timeout=2.0)
    version, info, containers = await asyncio.gather(
        client.version(),
        client.info(),
        client.containers(all_containers=True),
    )
    assert version["Version"] == "27.0.0"
    assert info["Images"] == 2
    assert containers[0]["Names"] == ["/jellyfin"]


@pytest.mark.asyncio
async def test_engine_concurrent_calls_isolated(fake_docker_http):
    """Regression: concurrent callers must not share/close one transport."""
    client = DockerEngineClient(fake_docker_http, timeout=2.0)

    async def burst() -> dict[str, Any]:
        return await client.version()

    results = await asyncio.gather(*[burst() for _ in range(12)])
    assert all(item["Version"] == "27.0.0" for item in results)


@pytest.mark.asyncio
async def test_engine_http_error_becomes_docker_engine_error(fake_docker_http):
    client = DockerEngineClient(fake_docker_http, timeout=2.0)
    with pytest.raises(DockerEngineError, match="HTTP 404"):
        await client.get_json("/missing")


@pytest.mark.asyncio
async def test_collect_detail_via_real_http_client(fake_docker_http):
    detail = await collect_docker_detail(
        enabled=True, socket_path=fake_docker_http, timeout=2.0
    )
    assert detail.available is True
    assert detail.configured is True
    assert detail.overview is not None
    assert detail.overview.version == "27.0.0"
    assert detail.overview.running == 1
    assert detail.containers[0].name == "jellyfin"


@pytest.mark.asyncio
async def test_collect_detail_swallows_invalid_state_error():
    with patch("app.docker_service.DockerEngineClient") as cls:
        client = AsyncMock()
        client.version = AsyncMock(
            side_effect=asyncio.exceptions.InvalidStateError("invalid state")
        )
        client.info = AsyncMock(side_effect=asyncio.exceptions.InvalidStateError("x"))
        client.containers = AsyncMock(
            side_effect=asyncio.exceptions.InvalidStateError("x")
        )
        cls.return_value = client
        detail = await collect_docker_detail(
            enabled=True, socket_path="/var/run/docker.sock"
        )

    assert detail.available is False
    assert detail.configured is True
    assert "invalid state" in (detail.error or "").lower()


@pytest.mark.asyncio
async def test_docker_endpoint_never_500_on_engine_crash(client):
    with patch("app.api.collect_docker_detail", side_effect=RuntimeError("boom")):
        response = client.get("/api/docker")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert "boom" in payload["error"]


@pytest.mark.asyncio
async def test_sync_http_transport_closed_per_call(fake_docker_http):
    """Each call should construct and close its own sync client."""
    created: list[MagicMock] = []
    real_client = httpx.Client

    def factory(*args: Any, **kwargs: Any):
        instance = real_client(*args, **kwargs)
        created.append(instance)
        return instance

    with patch("app.docker_engine.httpx.Client", side_effect=factory):
        engine = DockerEngineClient(fake_docker_http, timeout=2.0)
        await asyncio.gather(engine.version(), engine.info(), engine.containers())

    assert len(created) >= 3


@pytest.mark.asyncio
async def test_docker_not_configured_when_disabled():
    adapter = DockerAdapter(enabled=False, socket_path="/var/run/docker.sock")
    snap = await adapter.fetch()
    assert snap.status == ServiceStatus.NOT_CONFIGURED
    assert snap.href == "/docker"


@pytest.mark.asyncio
async def test_docker_available_summary():
    version = {"Version": "27.0.0", "ApiVersion": "1.46"}
    containers = [
        {
            "Id": "aaa",
            "Names": ["/jellyfin"],
            "State": "running",
            "Status": "Up 2 days",
        },
        {"Id": "bbb", "Names": ["/stopped"], "State": "exited", "Status": "Exited (0)"},
    ]
    client = AsyncMock()
    client.version = AsyncMock(return_value=version)
    client.containers = AsyncMock(return_value=containers)

    with patch("app.adapters.docker.DockerEngineClient", return_value=client):
        adapter = DockerAdapter(enabled=True, socket_path="/var/run/docker.sock")
        adapter._client = client
        snap = await adapter.fetch()

    assert snap.status == ServiceStatus.ONLINE
    assert snap.href == "/docker"
    by_key = {m.key: m for m in snap.metrics}
    assert by_key["containers"].display == "2 containers"
    assert by_key["running"].display == "1 running"
    assert by_key["stopped"].display == "1 stopped"


@pytest.mark.asyncio
async def test_docker_missing_socket_is_not_configured():
    client = AsyncMock()
    client.version = AsyncMock(
        side_effect=DockerEngineError(
            "Error while fetching server API version: (2, 'CreateFile', "
            "'The system cannot find the file specified.')"
        )
    )

    adapter = DockerAdapter(enabled=True, socket_path="/var/run/docker.sock")
    adapter._client = client
    snap = await adapter.fetch()
    assert snap.status == ServiceStatus.NOT_CONFIGURED


@pytest.mark.asyncio
async def test_docker_api_failure():
    client = AsyncMock()
    client.version = AsyncMock(side_effect=DockerEngineError("connection refused"))

    adapter = DockerAdapter(enabled=True, socket_path="/var/run/docker.sock")
    adapter._client = client
    snap = await adapter.fetch()
    assert snap.status == ServiceStatus.DEGRADED
    assert snap.status_label == "Unavailable"


@pytest.mark.asyncio
async def test_docker_detail_running_and_stopped():
    version = {"Version": "27.0.0", "ApiVersion": "1.46"}
    info = {"Images": 3, "Containers": 2}
    containers = [
        {
            "Id": "abc123456789",
            "Names": ["/jellyfin"],
            "Image": "jellyfin/jellyfin:latest",
            "State": "running",
            "Status": "Up 12 days",
            "Ports": [
                {
                    "PrivatePort": 8096,
                    "PublicPort": 8096,
                    "Type": "tcp",
                    "IP": "0.0.0.0",
                }
            ],
        },
        {
            "Id": "def123456789",
            "Names": ["/old"],
            "Image": "alpine:latest",
            "State": "exited",
            "Status": "Exited (1) 2 hours ago",
            "Ports": [],
        },
        {
            "Id": "ghi123456789",
            "Names": ["/boot"],
            "Image": "busybox",
            "State": "restarting",
            "Status": "Restarting",
            "Ports": [],
        },
    ]

    async def fake_collect(**kwargs: Any):
        with patch("app.docker_service.DockerEngineClient") as cls:
            client = AsyncMock()
            client.version = AsyncMock(return_value=version)
            client.info = AsyncMock(return_value=info)
            client.containers = AsyncMock(return_value=containers)
            client.images = AsyncMock(return_value=[{}, {}, {}])
            client.volumes = AsyncMock(return_value={"Volumes": [{}, {}]})
            client.inspect_container = AsyncMock(
                return_value={
                    "RestartCount": 2,
                    "State": {"StartedAt": "2026-01-01T00:00:00Z", "ExitCode": 0},
                }
            )
            client.container_stats = AsyncMock(
                return_value={
                    "cpu_stats": {
                        "cpu_usage": {"total_usage": 200, "percpu_usage": [1, 1]},
                        "system_cpu_usage": 2000,
                        "online_cpus": 2,
                    },
                    "precpu_stats": {
                        "cpu_usage": {"total_usage": 100, "percpu_usage": [1, 1]},
                        "system_cpu_usage": 1000,
                    },
                    "memory_stats": {"usage": 1048576, "limit": 10485760},
                }
            )
            cls.return_value = client
            return await collect_docker_detail(
                enabled=True, socket_path="/var/run/docker.sock"
            )

    detail = await fake_collect()
    assert detail.available is True
    assert detail.overview is not None
    assert detail.overview.running == 1
    assert detail.overview.stopped == 1
    assert detail.overview.restarting == 1
    assert detail.overview.images == 3
    assert detail.overview.volumes == 2
    names = {c.name: c for c in detail.containers}
    assert names["jellyfin"].status_tone == "good"
    assert names["old"].status_tone == "bad"
    assert names["old"].exit_code == 1
    assert names["boot"].status_tone == "warn"
    assert names["jellyfin"].cpu_display != "Unavailable"
    assert "8096" in names["jellyfin"].ports[0].display


@pytest.mark.asyncio
async def test_docker_detail_not_configured():
    detail = await collect_docker_detail(
        enabled=False, socket_path="/var/run/docker.sock"
    )
    assert detail.configured is False
    assert detail.available is False


@pytest.mark.asyncio
async def test_docker_detail_missing_socket_file():
    with patch("app.docker_service.DockerEngineClient") as cls:
        client = AsyncMock()
        client.version = AsyncMock(
            side_effect=DockerEngineError(
                "Error while fetching server API version: (2, 'CreateFile', "
                "'The system cannot find the file specified.')"
            )
        )
        client.info = AsyncMock(side_effect=DockerEngineError("x"))
        client.containers = AsyncMock(side_effect=DockerEngineError("x"))
        cls.return_value = client
        detail = await collect_docker_detail(
            enabled=True, socket_path="/var/run/docker.sock"
        )

    assert detail.configured is False
    assert detail.available is False
    assert detail.error == "Docker socket not available"


@pytest.mark.asyncio
async def test_docker_detail_malformed_containers():
    with patch("app.docker_service.DockerEngineClient") as cls:
        client = AsyncMock()
        client.version = AsyncMock(return_value={"Version": "27"})
        client.info = AsyncMock(return_value={})
        client.containers = AsyncMock(
            side_effect=DockerEngineError("Malformed /containers/json response")
        )
        cls.return_value = client
        detail = await collect_docker_detail(
            enabled=True, socket_path="/var/run/docker.sock"
        )

    assert detail.available is False
    assert "Malformed" in (detail.error or "")


def test_sanitize_ports_and_cpu():
    ports = sanitize_ports(
        [
            {"PrivatePort": 80, "PublicPort": 8080, "Type": "tcp", "IP": "0.0.0.0"},
            {"PrivatePort": 443, "Type": "tcp"},
            "bad",
        ]
    )
    assert ports[0]["display"] == "8080->80/tcp"
    assert ports[1]["display"] == "443/tcp"

    cpu = cpu_percent_from_stats(
        {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 200, "percpu_usage": [1]},
                "system_cpu_usage": 400,
                "online_cpus": 1,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 100},
                "system_cpu_usage": 200,
            },
        }
    )
    assert cpu == 50.0


def test_resolve_docker_url_unix():
    assert (
        resolve_docker_url("unix:///var/run/docker.sock")
        == "unix:///var/run/docker.sock"
    )
    assert resolve_docker_url("tcp://127.0.0.1:2375") == "tcp://127.0.0.1:2375"
    assert resolve_docker_url("http://127.0.0.1:2375") == "http://127.0.0.1:2375"


def test_docker_endpoint_not_configured(client):
    response = client.get("/api/docker")
    assert response.status_code == 200
    payload = response.json()
    assert "available" in payload
    assert "configured" in payload
    assert "containers" in payload
    assert "Env" not in str(payload)
    assert "socket" not in payload
