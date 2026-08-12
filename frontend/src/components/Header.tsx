import { NavLink, Link } from "react-router-dom";
import { RefreshCw, Settings } from "lucide-react";
import type { SystemHealth } from "../types";
import { StatusDot } from "./StatusDot";
import { formatClock, formatRelativeTime } from "../lib/format";

interface HeaderProps {
  serverName: string;
  health: SystemHealth | null;
  now: Date;
  updatedAt?: string | null;
  refreshing?: boolean;
  stale?: boolean;
  showRefreshMeta?: boolean;
}

const navClass = ({ isActive }: { isActive: boolean }) =>
  [
    "rounded-lg px-2.5 py-1.5 text-xs font-medium transition",
    isActive ? "bg-surface-2 text-ink" : "text-muted hover:text-ink",
  ].join(" ");

export function Header({
  serverName,
  health,
  now,
  updatedAt = null,
  refreshing = false,
  stale = false,
  showRefreshMeta = true,
}: HeaderProps) {
  return (
    <header className="sticky top-0 z-20 border-b border-border-subtle/90 bg-canvas/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-2.5 sm:px-6 sm:py-3 lg:px-8">
        <div className="flex min-w-0 items-center gap-2.5 sm:gap-3">
          <Link
            to="/"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-surface-2 text-ink transition hover:border-ink/20"
            aria-label="Dashboard"
          >
            <span className="text-[11px] font-semibold tracking-tight">HS</span>
          </Link>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold tracking-tight text-ink">
              {serverName}
            </div>
            <div className="mt-0.5 flex min-w-0 items-center gap-2 text-xs text-muted">
              {health ? (
                <>
                  <StatusDot status={health.level} pulse />
                  <span className="truncate">{health.label}</span>
                </>
              ) : (
                <span>Connecting…</span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5 sm:gap-3">
          <nav className="hidden items-center gap-0.5 rounded-xl border border-border/80 bg-surface/50 p-0.5 sm:flex">
            <NavLink to="/" end className={navClass}>
              Dashboard
            </NavLink>
            <NavLink to="/docker" className={navClass}>
              Docker
            </NavLink>
            <NavLink to="/settings" className={navClass}>
              Settings
            </NavLink>
          </nav>

          {showRefreshMeta ? (
            <div className="hidden items-center gap-2 text-xs text-faint md:flex">
              <RefreshCw
                className={`h-3.5 w-3.5 transition ${refreshing ? "animate-spin text-muted" : ""}`}
                strokeWidth={1.75}
              />
              <span className={`tabular-nums ${stale ? "text-warn" : ""}`}>
                {updatedAt
                  ? stale
                    ? `Last updated ${formatRelativeTime(updatedAt, now)}`
                    : `Updated ${formatRelativeTime(updatedAt, now)}`
                  : "Waiting…"}
              </span>
            </div>
          ) : null}

          <time className="hidden font-mono text-xs text-muted lg:block tabular-nums">
            {formatClock(now)}
          </time>

          <Link
            to="/settings"
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-surface text-muted transition hover:border-ink/20 hover:text-ink sm:hidden"
            aria-label="Settings"
          >
            <Settings className="h-4 w-4" strokeWidth={1.75} />
          </Link>
        </div>
      </div>

      <nav className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-4 pb-3 sm:hidden">
        <NavLink to="/" end className={navClass}>
          Dashboard
        </NavLink>
        <NavLink to="/docker" className={navClass}>
          Docker
        </NavLink>
        <NavLink to="/settings" className={navClass}>
          Settings
        </NavLink>
      </nav>
    </header>
  );
}
