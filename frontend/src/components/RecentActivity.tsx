import type { ActivityItem } from "../types";
import { StatusDot } from "./StatusDot";
import type { ServiceStatus } from "../types";

function toneToStatus(tone: string): ServiceStatus {
  if (tone === "good") return "online";
  if (tone === "warn") return "degraded";
  if (tone === "bad") return "offline";
  return "not_configured";
}

interface RecentActivityProps {
  items: ActivityItem[];
}

export function RecentActivity({ items }: RecentActivityProps) {
  if (items.length === 0) return null;

  return (
    <section className="px-4 sm:px-6 lg:px-8">
      <p className="mb-2 text-[10px] font-medium uppercase tracking-[0.14em] text-faint">
        Right now
      </p>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <div
            key={item.text}
            className="inline-flex max-w-full items-center gap-2 rounded-full border border-border/70 bg-surface/50 px-3 py-1.5 text-xs text-muted"
          >
            <StatusDot status={toneToStatus(item.tone)} />
            <span className="truncate text-ink/85">{item.text}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
