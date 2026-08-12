import type { ServiceStatus, SystemHealthLevel } from "../types";

const SERVICE_STATUS_LABEL: Record<ServiceStatus, string> = {
  online: "Online",
  degraded: "Degraded",
  offline: "Offline",
  not_configured: "Not configured",
  unknown: "Unknown",
};

export function serviceStatusLabel(status: ServiceStatus): string {
  return SERVICE_STATUS_LABEL[status] ?? "Unknown";
}

export function emptyStateCopy(serviceId: string, error: string | null): string {
  switch (serviceId) {
    case "jellyfin":
      return "Add a Jellyfin URL in Settings to enable this card.";
    case "starpulse":
      return "Add a StarPulse URL in Settings to enable this card.";
    case "starlink":
      return "Configure StarPulse to show live Starlink status.";
    case "docker":
      return "Docker socket has not been enabled.";
    case "portainer":
      return "Add a Portainer URL in Settings to enable this card.";
    case "router":
      return "Add TPLINK_URL and local TPLINK_PASSWORD in .env (not TP-Link ID).";
    case "tailscale":
      return "Enable Tailscale and mount the tailscaled socket to show VPN status.";
    default:
      return error || "This service has not been configured yet.";
  }
}

export function isHealthyLevel(level: SystemHealthLevel | null | undefined): boolean {
  return level === "operational";
}
