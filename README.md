# Home Server Dashboard

**v1.0.0** — a lightweight personal home-server cockpit.

FastAPI + React (Vite/Tailwind). One container. Persistent config in `/data`.

At a glance: host health, internet/Starlink via StarPulse, Jellyfin, Docker containers, and a settings UI for enablement and URLs.

## What it does

- Live dashboard for host CPU / RAM / storage / network
- Service cards with consistent status: Online · Degraded · Offline · Not configured
- In-memory sparklines (CPU, network) and a short “right now” strip
- Read-only Docker container overview (`/docker`)
- Settings for non-secret config; API keys stay in environment variables

It does **not** include auth, historical metrics, alerts, or remote control.

## Supported integrations

| Service   | Config                         | Notes                                      |
|-----------|--------------------------------|--------------------------------------------|
| Server    | always on                      | Local metrics via psutil                   |
| Jellyfin  | URL + `JELLYFIN_API_KEY`       | Key is env-only; never returned by the API |
| StarPulse | URL                            | Health / version / Starlink summary        |
| Starlink  | via StarPulse URL              | Card links out to StarPulse                |
| Docker    | socket path + enable toggle    | Engine API over socket; read-only          |

Future adapters (Immich, Home Assistant, …) appear in Settings as unimplemented placeholders.

## Quick start (Docker)

```bash
cp .env.example .env
# Set JELLYFIN_URL, JELLYFIN_API_KEY, STARPULSE_URL as needed
docker compose up -d --build
```

Open [http://localhost:8080](http://localhost:8080).

Config persists in `./data` → `/data` inside the container (`config.json`).

## Configuration

**Environment (secrets + defaults)** — see `.env.example`:

- `DATA_DIR` — config directory (default `./data`, `/data` in Docker)
- `SERVER_NAME` — header title
- `JELLYFIN_URL` / `JELLYFIN_API_KEY`
- `STARPULSE_URL`
- `DOCKER_SOCKET` — default `/var/run/docker.sock`

**Persistent `/data/config.json`** (non-secret):

- Server name, refresh interval
- Per-service `enabled`, `url`, `socket`

URLs and enable/disable can also be edited in the Settings UI. Secrets are never written there or returned by `GET /api/settings`.

## Docker socket

`docker compose` mounts the host Docker socket into the container.

- Frontend never talks to Docker; only sanitized `GET /api/docker`
- Monitoring is **read-only** (no start/stop/restart)
- **Warning:** socket access is powerful even when mounted read-only. Use only on a private network you trust. Disable Docker in Settings if unused.

## Architecture / future adapters

```
ServiceAdapter → ServiceSnapshot → DashboardResponse → ServiceCard
```

To add a service:

1. Implement `ServiceAdapter` under `backend/app/adapters/`
2. Register it in `SERVICE_CATALOG` and `build_registry`
3. Add a default entry in `config_store.DEFAULT_CONFIG` if needed

The dashboard and settings UI pick it up automatically.

## Local development

```bash
# Backend
cd backend
python -m venv .venv && .venv\Scripts\activate   # or source .venv/bin/activate
pip install -r requirements.txt
set PYTHONPATH=.                                 # export on Unix
uvicorn app.main:app --reload --port 8080

# Frontend
cd frontend
npm install
npm run dev   # proxies /api → :8080
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Liveness + version |
| GET | `/api/dashboard` | Overview + service snapshots |
| GET | `/api/services/{id}` | Single snapshot |
| GET | `/api/docker` | Docker detail (sanitized) |
| GET/PUT | `/api/settings` | Non-secret settings |

Missing integrations show **Not configured** — never fake metrics.

## Tests

```bash
cd backend && pytest && ruff check app tests && black --check app tests
cd frontend && npm run build && npm run lint
```
