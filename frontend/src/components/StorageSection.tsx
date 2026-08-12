import type { StorageMount } from "../types";
import { StatusDot } from "./StatusDot";
import type { ServiceStatus } from "../types";

function toneToStatus(tone: string): ServiceStatus {
  if (tone === "good") return "online";
  if (tone === "warn") return "degraded";
  if (tone === "bad") return "offline";
  return "not_configured";
}

function UsageBar({ percent, tone }: { percent: number; tone: string }) {
  const width = Math.max(0, Math.min(100, percent));
  const color =
    tone === "bad" ? "bg-bad" : tone === "warn" ? "bg-warn" : "bg-good/80";
  return (
    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-2">
      <div className={`h-full rounded-full ${color}`} style={{ width: `${width}%` }} />
    </div>
  );
}

interface StorageSectionProps {
  mounts: StorageMount[];
}

export function StorageSection({ mounts }: StorageSectionProps) {
  if (!mounts.length) return null;

  return (
    <section className="px-4 sm:px-6 lg:px-8">
      <div className="mb-3">
        <h2 className="text-sm font-semibold tracking-tight text-ink">Storage</h2>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {mounts.map((mount) => (
          <article
            key={mount.mountpoint}
            className="rounded-xl border border-border/70 bg-surface/55 px-3.5 py-3"
          >
            <div className="flex items-center justify-between gap-2">
              <p className="truncate font-mono text-sm text-ink">{mount.mountpoint}</p>
              <div className="flex shrink-0 items-center gap-1.5 text-xs text-muted">
                <StatusDot status={toneToStatus(mount.tone)} />
                <span
                  className={
                    mount.tone === "bad"
                      ? "text-bad"
                      : mount.tone === "warn"
                        ? "text-warn"
                        : "text-muted"
                  }
                >
                  {mount.percent.toFixed(0)}%
                </span>
              </div>
            </div>
            <p className="mt-1.5 font-mono text-[13px] tabular-nums text-ink/90">
              {mount.summary}
            </p>
            <p className="mt-1 text-xs text-faint">
              {mount.percent.toFixed(0)}% used · {mount.free_display} free
            </p>
            <UsageBar percent={mount.percent} tone={mount.tone} />
          </article>
        ))}
      </div>
    </section>
  );
}
