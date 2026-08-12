# Changelog

## 1.0.0 — 2026-08-12

First stable release of the home server cockpit.

### Features

- Minimal dark dashboard for host health and service status
- Adapters: Server, Jellyfin, StarPulse, Starlink, Docker (read-only)
- Settings UI for enable/disable, URLs, and Docker socket path
- Secrets (`JELLYFIN_API_KEY`, etc.) via environment only
- Persistent non-secret config under `/data`
- In-memory CPU / network sparklines and ephemeral activity strip
- Intentional empty states for unconfigured services
- Storage metric shows free space and highlights when nearly full

### Ops

- Single Docker image via `docker compose`
- Optional Docker socket mount for container monitoring
