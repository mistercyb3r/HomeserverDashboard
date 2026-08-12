import { useEffect, useRef, useState } from "react";
import { fetchDashboard } from "../api";
import type { DashboardResponse } from "../types";
import { Header } from "../components/Header";
import { HeroOverview } from "../components/HeroOverview";
import { RecentActivity } from "../components/RecentActivity";
import { ServiceCard } from "../components/ServiceCard";

const DEFAULT_REFRESH_MS = 10_000;
const HISTORY_LENGTH = 24;

function pushHistory(prev: number[], next: number | null | undefined): number[] {
  if (next == null || Number.isNaN(next)) return prev;
  const updated = [...prev, next];
  return updated.length > HISTORY_LENGTH ? updated.slice(-HISTORY_LENGTH) : updated;
}

function numericOverview(data: DashboardResponse, key: string): number | null {
  const item = data.overview.find((m) => m.key === key);
  if (!item?.available || item.value == null) return null;
  const value = typeof item.value === "number" ? item.value : Number(item.value);
  return Number.isFinite(value) ? value : null;
}

export function DashboardPage() {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [now, setNow] = useState(() => new Date());
  const [cpuHistory, setCpuHistory] = useState<number[]>([]);
  const [networkHistory, setNetworkHistory] = useState<number[]>([]);
  const refreshMs = useRef(DEFAULT_REFRESH_MS);
  const dataRef = useRef<DashboardResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    async function load() {
      setRefreshing(true);
      try {
        const dashboard = await fetchDashboard();
        if (cancelled) return;
        dataRef.current = dashboard;
        setData(dashboard);
        setError(null);
        setStale(false);
        setCpuHistory((prev) => pushHistory(prev, numericOverview(dashboard, "cpu")));
        setNetworkHistory((prev) => pushHistory(prev, numericOverview(dashboard, "network")));
        refreshMs.current = Math.max(5, Math.min(15, dashboard.refresh_interval_seconds)) * 1000;
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load dashboard");
        if (dataRef.current) setStale(true);
      } finally {
        if (!cancelled) {
          setRefreshing(false);
          timer = window.setTimeout(() => {
            void load();
          }, refreshMs.current);
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    const clock = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(clock);
  }, []);

  const activeServices = data?.services.filter((s) => s.status !== "not_configured") ?? [];
  const idleServices = data?.services.filter((s) => s.status === "not_configured") ?? [];

  return (
    <div className="min-h-svh">
      <Header
        serverName={data?.server_name ?? "Home Server"}
        health={data?.system_health ?? null}
        now={now}
        updatedAt={data?.generated_at ?? null}
        refreshing={refreshing}
        stale={stale}
      />

      <div className="mx-auto w-full max-w-6xl pb-10">
        {error && !data ? (
          <div className="px-4 py-16 text-center sm:px-6">
            <p className="text-sm text-bad">Could not reach the dashboard API.</p>
            <p className="mt-2 text-xs text-faint">{error}</p>
          </div>
        ) : null}

        {data ? (
          <>
            {stale ? (
              <div className="mx-4 mt-4 rounded-xl border border-warn/25 bg-warn/5 px-3 py-2 text-xs text-warn sm:mx-6 lg:mx-8">
                Showing last successful data · {error || "temporary refresh failure"}
              </div>
            ) : null}

            <HeroOverview
              health={data.system_health}
              overview={data.overview}
              services={data.services}
              cpuHistory={cpuHistory}
              networkHistory={networkHistory}
            />

            <div className="mt-4 sm:mt-5">
              <RecentActivity items={data.activity ?? []} />
            </div>

            <section className="px-4 py-6 sm:px-6 sm:py-7 lg:px-8">
              <div className="mb-3.5">
                <h2 className="text-sm font-semibold tracking-tight text-ink">Services</h2>
              </div>

              <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                {activeServices.map((service) => (
                  <ServiceCard key={service.id} service={service} now={now} />
                ))}
              </div>

              {idleServices.length > 0 ? (
                <div className="mt-7">
                  <p className="mb-3 text-[11px] font-medium uppercase tracking-[0.14em] text-faint">
                    Not configured
                  </p>
                  <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                    {idleServices.map((service) => (
                      <ServiceCard key={service.id} service={service} now={now} />
                    ))}
                  </div>
                </div>
              ) : null}
            </section>
          </>
        ) : !error ? (
          <div className="px-4 py-16 text-center text-sm text-muted sm:px-6">Loading…</div>
        ) : null}
      </div>
    </div>
  );
}
