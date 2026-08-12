export function formatRelativeTime(iso: string, now = new Date()): string {
  const then = new Date(iso);
  const diffSec = Math.max(0, Math.round((now.getTime() - then.getTime()) / 1000));
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const mins = Math.floor(diffSec / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function formatClock(date: Date): string {
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

export function metricText(display: string, unit?: string | null, available = true): string {
  if (!available) return display || "Unavailable";
  if (!unit) return display;
  if (display.includes(unit)) return display;
  return `${display}${unit === "%" || unit === "°C" ? unit : ` ${unit}`}`;
}

/** Compact 5-segment bar like ▰▰▱▱▱ */
export function percentBar(percent: number | null | undefined, segments = 5): string {
  if (percent == null || Number.isNaN(percent)) return "▱".repeat(segments);
  const filled = Math.max(0, Math.min(segments, Math.round((percent / 100) * segments)));
  return `${"▰".repeat(filled)}${"▱".repeat(segments - filled)}`;
}
