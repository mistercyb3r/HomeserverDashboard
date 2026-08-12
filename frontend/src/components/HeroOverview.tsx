import type { OverviewMetric, ServiceSnapshot, SystemHealth } from "../types";
import { StatusDot } from "./StatusDot";
import { Sparkline } from "./Sparkline";
import { metricText, percentBar } from "../lib/format";
import { serviceStatusLabel } from "../lib/status";
import type { ServiceStatus } from "../types";

interface HeroOverviewProps {
  health: SystemHealth;
  overview: OverviewMetric[];
  services: ServiceSnapshot[];
  cpuHistory: number[];
  networkHistory: number[];
}

function toneToStatus(tone: string | null | undefined): ServiceStatus | null {
  if (tone === "good") return "online";
  if (tone === "warn") return "degraded";
  if (tone === "bad") return "offline";
  return null;
}

function OverviewTile({
  item,
  sparkline,
}: {
  item: OverviewMetric;
  sparkline?: number[];
}) {
  const wantsSpark = sparkline !== undefined;
  const showBar = item.bar != null && item.available && !wantsSpark && !item.detail;
  const showSpark = wantsSpark && item.available;
  const status = toneToStatus(item.tone);
  const valueClass =
    item.tone === "bad"
      ? "text-bad"
      : item.tone === "warn"
        ? "text-warn"
        : item.available
          ? "text-ink"
          : "text-faint";

  return (
    <div className="rounded-xl border border-border/70 bg-surface/55 px-3 py-2.5 sm:px-3.5 sm:py-3">
      <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-faint">
        {item.label}
      </div>
      <div
        className={`mt-1 flex items-center gap-2 font-mono text-base tracking-tight tabular-nums sm:text-lg ${valueClass}`}
      >
        {status ? <StatusDot status={status} /> : null}
        <span>{metricText(item.display, item.unit, item.available)}</span>
      </div>
      {showSpark ? (
        <div className="mt-1.5 text-muted">
          <Sparkline values={sparkline} className="h-5 w-full sm:h-6" />
        </div>
      ) : item.detail && item.available ? (
        <div className="mt-1.5 text-xs text-faint">{item.detail}</div>
      ) : showBar ? (
        <div className="mt-1.5 font-mono text-[10px] tracking-[0.14em] text-faint" aria-hidden>
          {percentBar(item.bar)}
        </div>
      ) : (
        <div className="mt-1.5 h-5 sm:h-6" />
      )}
    </div>
  );
}

export function HeroOverview({
  health,
  overview,
  services,
  cpuHistory,
  networkHistory,
}: HeroOverviewProps) {
  const orderedKeys = ["cpu", "ram", "disk", "network", "uptime", "load"];
  const primary = orderedKeys
    .map((key) => overview.find((m) => m.key === key))
    .filter((m): m is OverviewMetric => Boolean(m));

  const starlink = services.find((s) => s.id === "starlink");
  const internetAvailable = Boolean(
    starlink && starlink.status !== "not_configured" && starlink.status !== "unknown",
  );
  const internetDisplay = internetAvailable
    ? starlink!.status_label || serviceStatusLabel(starlink!.status)
    : "Starlink status appears once StarPulse is configured.";
  const internetStatus = starlink?.status ?? "not_configured";

  return (
    <section className="px-4 pt-5 sm:px-6 sm:pt-7 lg:px-8">
      <div className="flex flex-col gap-4 sm:gap-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between sm:gap-4">
          <div className="max-w-xl">
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-faint">
              Home server
            </p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
              Cockpit
            </h1>
          </div>
          <div className="inline-flex w-fit items-center gap-2.5 rounded-full border border-border bg-surface/80 px-3 py-1.5 text-sm">
            <StatusDot status={health.level} size="md" pulse />
            <span className="text-ink">{health.label}</span>
          </div>
        </div>

        <div className="rounded-xl border border-border/70 bg-surface/40 px-3.5 py-2.5">
          <div className="flex items-center justify-between gap-3">
            <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-faint">
              Internet
            </span>
            <div className="flex items-center gap-2 text-xs text-muted">
              <StatusDot status={internetStatus} />
              <span className={internetAvailable ? "text-ink" : "text-faint"}>
                {serviceStatusLabel(internetStatus)}
              </span>
            </div>
          </div>
          <div
            className={`mt-1.5 text-sm ${
              internetAvailable ? "font-mono tabular-nums text-ink" : "text-faint"
            }`}
          >
            {internetDisplay}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {primary.map((item) => (
            <OverviewTile
              key={item.key}
              item={item}
              sparkline={
                item.key === "cpu"
                  ? cpuHistory
                  : item.key === "network"
                    ? networkHistory
                    : undefined
              }
            />
          ))}
        </div>
      </div>
    </section>
  );
}
