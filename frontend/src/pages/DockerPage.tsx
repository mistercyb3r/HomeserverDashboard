import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { fetchDocker } from "../api";
import type { DockerContainer, DockerDetailResponse, SystemHealth } from "../types";
import { Header } from "../components/Header";
import { StatusDot } from "../components/StatusDot";
import type { ServiceStatus } from "../types";

const REFRESH_MS = 10_000;

function toneToStatus(tone: string): ServiceStatus {
  if (tone === "good") return "online";
  if (tone === "warn") return "degraded";
  if (tone === "bad") return "offline";
  return "not_configured";
}

export function DockerPage() {
  const [data, setData] = useState<DockerDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [now, setNow] = useState(() => new Date());
  const dataRef = useRef<DockerDetailResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    async function load() {
      try {
        const detail = await fetchDocker();
        if (cancelled) return;
        dataRef.current = detail;
        setData(detail);
        setError(null);
        setStale(false);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load Docker");
        if (dataRef.current) setStale(true);
      } finally {
        if (!cancelled) {
          timer = window.setTimeout(() => {
            void load();
          }, REFRESH_MS);
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

  const health: SystemHealth | null = data
    ? {
        level: !data.configured
          ? "unknown"
          : data.available
            ? "operational"
            : "attention",
        label: !data.configured
          ? "Docker not configured"
          : data.available
            ? "Docker online"
            : "Docker degraded",
        online_count: data.available ? 1 : 0,
        attention_count: data.configured && !data.available ? 1 : 0,
        offline_count: 0,
        not_configured_count: data.configured ? 0 : 1,
        total_enabled: 1,
      }
    : null;

  return (
    <div className="min-h-svh">
      <Header
        serverName="Home Server"
        health={health}
        now={now}
        updatedAt={data?.generated_at ?? null}
        stale={stale}
        showRefreshMeta
      />

      <div className="mx-auto w-full max-w-6xl px-4 py-7 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-ink">Docker</h1>
            <p className="mt-1.5 max-w-2xl text-sm text-muted">
              Read-only container status. The socket stays on the backend.
            </p>
          </div>
        </div>

        {!data && error ? <p className="mt-8 text-sm text-bad">{error}</p> : null}
        {!data && !error ? <p className="mt-10 text-sm text-muted">Loading…</p> : null}

        {data && !data.configured ? (
          <div className="mt-8 rounded-2xl border border-border/80 bg-surface/40 p-5">
            <div className="flex items-center gap-2 text-sm text-muted">
              <StatusDot status="not_configured" />
              Not configured
            </div>
            <p className="mt-3 text-sm text-faint">
              Docker socket has not been enabled.
            </p>
            <Link
              to="/settings"
              className="mt-4 inline-flex rounded-lg border border-border px-3 py-1.5 text-xs text-muted transition hover:border-ink/25 hover:text-ink"
            >
              Configure
            </Link>
          </div>
        ) : null}

        {data && data.configured && !data.available ? (
          <div className="mt-8 rounded-2xl border border-warn/25 bg-warn/5 p-5">
            <div className="flex items-center gap-2 text-sm text-warn">
              <StatusDot status="degraded" />
              Degraded
            </div>
            <p className="mt-3 text-sm text-muted">
              {data.error || error || "Could not reach the Docker daemon."}
            </p>
          </div>
        ) : null}

        {data?.available && data.overview ? (
          <>
            <section className="mt-7 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
              <Stat label="Daemon" value="Online" />
              <Stat
                label="Version"
                value={data.overview.version ? `v${data.overview.version}` : "Unavailable"}
              />
              <Stat label="Running" value={String(data.overview.running)} />
              <Stat label="Stopped" value={String(data.overview.stopped)} />
              <Stat
                label="Images"
                value={data.overview.images == null ? "Unavailable" : String(data.overview.images)}
              />
              <Stat
                label="Volumes"
                value={
                  data.overview.volumes == null ? "Unavailable" : String(data.overview.volumes)
                }
              />
            </section>

            {data.overview.restarting > 0 ? (
              <p className="mt-3 text-xs text-warn">
                {data.overview.restarting} container(s) restarting
              </p>
            ) : null}

            <section className="mt-8">
              <h2 className="text-sm font-semibold text-ink">Containers</h2>
              <p className="mt-1 text-xs text-muted">{data.containers.length} total</p>

              <div className="mt-3 space-y-2">
                {data.containers.map((container) => (
                  <ContainerRow key={container.id} container={container} />
                ))}
                {data.containers.length === 0 ? (
                  <p className="rounded-xl border border-border bg-surface/40 px-4 py-6 text-sm text-faint">
                    No containers found.
                  </p>
                ) : null}
              </div>
            </section>
          </>
        ) : null}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border/70 bg-surface/55 px-3 py-2.5">
      <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-faint">{label}</div>
      <div className="mt-1 font-mono text-base tabular-nums text-ink sm:text-lg">{value}</div>
    </div>
  );
}

function ContainerRow({ container }: { container: DockerContainer }) {
  const ports = container.ports.map((p) => p.display).join(", ");

  return (
    <article className="rounded-xl border border-border bg-surface/60 px-4 py-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <StatusDot status={toneToStatus(container.status_tone)} />
            <h3 className="truncate text-sm font-semibold text-ink">{container.name}</h3>
          </div>
          <p className="mt-1 truncate font-mono text-xs text-faint">{container.image}</p>
          <p className="mt-2 text-xs text-muted">
            {container.uptime || container.status}
            {container.exit_code != null && container.state.toLowerCase() !== "running"
              ? ` · Exit ${container.exit_code}`
              : ""}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-x-5 gap-y-1 font-mono text-xs tabular-nums text-muted sm:text-right">
          <span>CPU {container.cpu_display}</span>
          <span>RAM {container.memory_display}</span>
          <span>
            Restarts {container.restart_count == null ? "Unavailable" : container.restart_count}
          </span>
          <span className="truncate sm:max-w-[14rem]">{ports || "No ports"}</span>
        </div>
      </div>
    </article>
  );
}
