import { useEffect, useState, type FormEvent } from "react";
import { fetchSettings, updateSettings } from "../api";
import type { ServiceDefinition, SettingsResponse, SystemHealth } from "../types";
import { Header } from "../components/Header";
import { ServiceIcon } from "../components/ServiceIcon";

export function SettingsPage() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [serverName, setServerName] = useState("");
  const [refreshSeconds, setRefreshSeconds] = useState(10);
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [sockets, setSockets] = useState<Record<string, string>>({});
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    void (async () => {
      try {
        const data = await fetchSettings();
        applySettings(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load settings");
      }
    })();
  }, []);

  useEffect(() => {
    const clock = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(clock);
  }, []);

  function applySettings(data: SettingsResponse) {
    setSettings(data);
    setServerName(data.server_name);
    setRefreshSeconds(data.refresh_interval_seconds);
    const nextEnabled: Record<string, boolean> = {};
    const nextUrls: Record<string, string> = {};
    const nextSockets: Record<string, string> = {};
    for (const service of data.services) {
      nextEnabled[service.id] = service.enabled;
      nextUrls[service.id] = service.url ?? "";
      nextSockets[service.id] = service.socket ?? "";
    }
    setEnabled(nextEnabled);
    setUrls(nextUrls);
    setSockets(nextSockets);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!settings) return;
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const services: Record<
        string,
        { enabled?: boolean; url?: string | null; socket?: string | null }
      > = {};
      for (const service of settings.services) {
        if (!service.implemented) {
          services[service.id] = { enabled: false };
          continue;
        }
        const patch: { enabled?: boolean; url?: string | null; socket?: string | null } = {
          enabled: enabled[service.id] ?? false,
        };
        if (service.configurable && service.config_kind === "socket") {
          patch.socket = sockets[service.id] || null;
        } else if (service.configurable) {
          patch.url = urls[service.id] || null;
        }
        services[service.id] = patch;
      }
      const updated = await updateSettings({
        server_name: serverName,
        refresh_interval_seconds: refreshSeconds,
        services,
      });
      applySettings(updated);
      setMessage("Settings saved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  const implemented = settings?.services.filter((s) => s.implemented) ?? [];
  const future = settings?.services.filter((s) => !s.implemented) ?? [];
  const health: SystemHealth = {
    level: "unknown",
    label: "Configuration",
    online_count: 0,
    attention_count: 0,
    offline_count: 0,
    not_configured_count: 0,
    total_enabled: 0,
  };

  return (
    <div className="min-h-svh">
      <Header
        serverName={serverName || "Home Server"}
        health={health}
        now={now}
        showRefreshMeta={false}
      />

      <div className="mx-auto w-full max-w-3xl px-4 py-7 sm:px-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Settings</h1>
        <p className="mt-1.5 text-sm text-muted">
          Enable services and set URLs or sockets. API keys stay in environment variables.
        </p>

        {error ? <p className="mt-4 text-sm text-bad">{error}</p> : null}
        {message ? <p className="mt-4 text-sm text-good">{message}</p> : null}

        {!settings ? (
          <p className="mt-10 text-sm text-muted">Loading…</p>
        ) : (
          <form onSubmit={onSubmit} className="mt-7 space-y-9">
            <section className="space-y-3.5">
              <h2 className="text-sm font-semibold text-ink">General</h2>
              <label className="block">
                <span className="text-xs text-muted">Server name</span>
                <input
                  value={serverName}
                  onChange={(e) => setServerName(e.target.value)}
                  className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-ink outline-none transition focus:border-ink/30"
                />
              </label>
              <label className="block">
                <span className="text-xs text-muted">Refresh interval (seconds)</span>
                <input
                  type="number"
                  min={5}
                  max={3600}
                  value={refreshSeconds}
                  onChange={(e) => setRefreshSeconds(Number(e.target.value))}
                  className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-ink outline-none transition focus:border-ink/30"
                />
              </label>
            </section>

            <section className="space-y-3">
              <h2 className="text-sm font-semibold text-ink">Services</h2>
              <div className="divide-y divide-border-subtle rounded-2xl border border-border bg-surface/60">
                {implemented.map((service) => (
                  <ServiceRow
                    key={service.id}
                    service={service}
                    checked={enabled[service.id] ?? false}
                    url={urls[service.id] ?? ""}
                    socket={sockets[service.id] ?? ""}
                    onToggle={(value) => setEnabled((prev) => ({ ...prev, [service.id]: value }))}
                    onUrlChange={(value) => setUrls((prev) => ({ ...prev, [service.id]: value }))}
                    onSocketChange={(value) =>
                      setSockets((prev) => ({ ...prev, [service.id]: value }))
                    }
                  />
                ))}
              </div>
            </section>

            <section className="space-y-3">
              <h2 className="text-sm font-semibold text-ink">Coming later</h2>
              <p className="text-xs text-muted">Reserved for future adapters.</p>
              <div className="divide-y divide-border-subtle rounded-2xl border border-border bg-surface/30">
                {future.map((service) => (
                  <div
                    key={service.id}
                    className="flex items-center justify-between gap-3 px-4 py-3 opacity-55"
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <input type="checkbox" disabled checked={false} className="accent-good" />
                      <ServiceIcon name={service.icon} className="h-4 w-4 text-faint" />
                      <div className="min-w-0">
                        <div className="text-sm text-ink">{service.name}</div>
                        <div className="text-xs text-faint">{service.description}</div>
                      </div>
                    </div>
                    <span className="text-[11px] text-faint">Not configured</span>
                  </div>
                ))}
              </div>
            </section>

            <button
              type="submit"
              disabled={saving}
              className="rounded-xl bg-ink px-4 py-2.5 text-sm font-medium text-canvas transition hover:bg-white disabled:opacity-60"
            >
              {saving ? "Saving…" : "Save settings"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

interface ServiceRowProps {
  service: ServiceDefinition;
  checked: boolean;
  url: string;
  socket: string;
  onToggle: (value: boolean) => void;
  onUrlChange: (value: string) => void;
  onSocketChange: (value: string) => void;
}

function ServiceRow({
  service,
  checked,
  url,
  socket,
  onToggle,
  onUrlChange,
  onSocketChange,
}: ServiceRowProps) {
  return (
    <div className="px-4 py-4">
      <label className="flex min-w-0 cursor-pointer items-start gap-3">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onToggle(e.target.checked)}
          className="mt-1 accent-good"
        />
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <ServiceIcon name={service.icon} className="h-4 w-4 text-muted" />
            <span className="text-sm font-medium text-ink">{service.name}</span>
          </div>
          <p className="mt-1 text-xs text-muted">{service.description}</p>
          {!service.configured && service.configurable ? (
            <p className="mt-1 text-xs text-faint">Not configured</p>
          ) : null}
          {service.id === "jellyfin" ? (
            <p className="mt-1 text-xs text-faint">
              API key via <code className="font-mono">JELLYFIN_API_KEY</code>
              {service.has_secret ? " · set" : " · missing"}
            </p>
          ) : null}
          {service.id === "docker" ? (
            <p className="mt-1 text-xs text-faint">
              Mounting the Docker socket is powerful. Monitoring is read-only.
            </p>
          ) : null}
        </div>
      </label>
      {service.configurable && service.config_kind === "socket" ? (
        <label className="mt-3 block">
          <span className="text-xs text-muted">Docker socket</span>
          <input
            value={socket}
            onChange={(e) => onSocketChange(e.target.value)}
            placeholder="/var/run/docker.sock"
            className="mt-1.5 w-full rounded-xl border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none transition focus:border-ink/30"
          />
        </label>
      ) : null}
      {service.configurable && service.config_kind !== "socket" ? (
        <input
          value={url}
          onChange={(e) => onUrlChange(e.target.value)}
          placeholder={`${service.name} URL`}
          className="mt-3 w-full rounded-xl border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none transition focus:border-ink/30"
        />
      ) : null}
    </div>
  );
}
