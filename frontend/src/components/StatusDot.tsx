import type { ServiceStatus, SystemHealthLevel } from "../types";

const STATUS_COLOR: Record<ServiceStatus | SystemHealthLevel, string> = {
  online: "bg-good",
  operational: "bg-good",
  degraded: "bg-warn",
  attention: "bg-warn",
  offline: "bg-bad",
  critical: "bg-bad",
  unknown: "bg-faint",
  not_configured: "bg-faint",
};

interface StatusDotProps {
  status: ServiceStatus | SystemHealthLevel;
  pulse?: boolean;
  size?: "sm" | "md";
}

export function StatusDot({ status, pulse = false, size = "sm" }: StatusDotProps) {
  const dim = size === "md" ? "h-2.5 w-2.5" : "h-2 w-2";
  return (
    <span className="relative inline-flex items-center justify-center">
      {pulse && (status === "online" || status === "operational") ? (
        <span
          className={`absolute inline-flex ${dim} rounded-full ${STATUS_COLOR[status]} opacity-40 animate-ping`}
        />
      ) : null}
      <span className={`relative inline-flex ${dim} rounded-full ${STATUS_COLOR[status]}`} />
    </span>
  );
}
