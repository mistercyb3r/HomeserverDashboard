import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import type { Metric, PlaybackSession, ServiceSnapshot } from "../types";
import { ServiceIcon } from "./ServiceIcon";
import { StatusDot } from "./StatusDot";
import { formatRelativeTime } from "../lib/format";
import { emptyStateCopy, serviceStatusLabel } from "../lib/status";
import { JellyfinNowPlaying } from "./JellyfinNowPlaying";

function pickMetrics(service: ServiceSnapshot): Metric[] {
  const primary = service.metrics.filter((m) => m.primary && m.key !== "uptime");
  if (primary.length > 0) return primary.slice(0, 4);
  return service.metrics.filter((m) => m.key !== "uptime").slice(0, 4);
}

interface ServiceCardProps {
  service: ServiceSnapshot;
  now: Date;
}

export function ServiceCard({ service, now }: ServiceCardProps) {
  const showNowPlaying = service.id === "jellyfin" && service.now_playing !== null && service.now_playing !== undefined;
  const metrics = showNowPlaying
    ? pickMetrics(service).filter((m) => m.key === "users" || m.key === "version")
    : pickMetrics(service);
  const href = service.href || service.url;
  const isInternal = Boolean(href?.startsWith("/"));
  const isIdle = service.status === "not_configured";
  const statusText = service.status_label || serviceStatusLabel(service.status);

  const actionClass =
    "inline-flex shrink-0 items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted transition hover:border-ink/25 hover:text-ink active:scale-[0.98]";

  const action = isIdle ? (
    <Link to="/settings" className={actionClass}>
      Configure
    </Link>
  ) : href ? (
    isInternal ? (
      <Link to={href} className={actionClass}>
        Open
        <ArrowUpRight className="h-3 w-3" strokeWidth={1.75} />
      </Link>
    ) : (
      <a href={href} target="_blank" rel="noreferrer" className={actionClass}>
        Open
        <ArrowUpRight className="h-3 w-3" strokeWidth={1.75} />
      </a>
    )
  ) : null;

  return (
    <article
      className={`group flex min-h-[10.5rem] flex-col rounded-2xl border p-4 transition duration-200 ${
        isIdle
          ? "border-border/70 bg-surface/30"
          : "border-border bg-surface/70 hover:border-ink/15 hover:bg-surface"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div
            className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border ${
              isIdle
                ? "border-border/70 bg-transparent text-faint"
                : "border-border bg-surface-2 text-muted"
            }`}
          >
            <ServiceIcon name={service.icon} />
          </div>
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold tracking-tight text-ink">
              {service.name}
            </h3>
            <div className="mt-1 flex items-center gap-2 text-xs text-muted">
              <StatusDot status={service.status} />
              <span className="truncate">{statusText}</span>
            </div>
            {!isIdle && service.uptime ? (
              <p className="mt-1 text-xs text-faint">Uptime: {service.uptime}</p>
            ) : null}
          </div>
        </div>
        {action}
      </div>

      {isIdle ? (
        <p className="mt-4 text-[13px] leading-relaxed text-faint">
          {emptyStateCopy(service.id, service.error)}
        </p>
      ) : (
        <div className="mt-4 space-y-3">
          {showNowPlaying ? (
            <JellyfinNowPlaying sessions={service.now_playing as PlaybackSession[]} />
          ) : null}

          {metrics.length > 0 ? (
            <ul className="space-y-1.5">
              {metrics.map((m) => (
                <li
                  key={m.key}
                  className="flex items-baseline justify-between gap-3 text-[13px]"
                >
                  <span className="truncate text-faint">{m.label}</span>
                  <span
                    className={`shrink-0 font-mono tabular-nums ${
                      m.available ? "text-ink/90" : "text-faint"
                    }`}
                  >
                    {m.available ? m.display : "—"}
                  </span>
                </li>
              ))}
            </ul>
          ) : !showNowPlaying ? (
            <p className="text-[13px] text-faint">
              {service.error || "No metrics available"}
            </p>
          ) : null}
        </div>
      )}

      <div className="mt-auto pt-4 text-[11px] text-faint">
        {isIdle ? (
          <span>Waiting for configuration</span>
        ) : (
          <span>Updated {formatRelativeTime(service.last_updated, now)}</span>
        )}
      </div>
    </article>
  );
}
