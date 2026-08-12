export type ServiceStatus =
  | "online"
  | "offline"
  | "degraded"
  | "unknown"
  | "not_configured";

export type SystemHealthLevel = "operational" | "attention" | "critical" | "unknown";

export interface StorageMount {
  mountpoint: string;
  device: string | null;
  fstype: string | null;
  total_bytes: number;
  used_bytes: number;
  free_bytes: number;
  percent: number;
  total_display: string;
  used_display: string;
  free_display: string;
  summary: string;
  tone: "good" | "warn" | "bad" | string;
}

export interface PlaybackSession {
  id: string;
  user: string;
  title: string;
  subtitle: string | null;
  progress: string | null;
  paused: boolean;
  artwork_url: string | null;
}

export interface Metric {
  key: string;
  label: string;
  value: string | number | null;
  display: string;
  unit: string | null;
  available: boolean;
  primary?: boolean;
  detail?: string | null;
}

export interface ServiceSnapshot {
  id: string;
  name: string;
  description: string;
  icon: string;
  status: ServiceStatus;
  status_label: string;
  metrics: Metric[];
  version: string | null;
  uptime: string | null;
  url: string | null;
  href: string | null;
  open_label: string | null;
  now_playing: PlaybackSession[] | null;
  last_updated: string;
  last_success_at: string | null;
  configured: boolean;
  error: string | null;
}

export interface OverviewMetric {
  key: string;
  label: string;
  value: string | number | null;
  display: string;
  unit: string | null;
  available: boolean;
  bar: number | null;
  detail?: string | null;
  tone?: "good" | "warn" | "bad" | "muted" | string | null;
}

export interface SystemHealth {
  level: SystemHealthLevel;
  label: string;
  online_count: number;
  attention_count: number;
  offline_count: number;
  not_configured_count: number;
  total_enabled: number;
}

export interface WeatherInfo {
  available: boolean;
  location: string;
  temperature_c: number | null;
  feels_like_c: number | null;
  high_c: number | null;
  low_c: number | null;
  condition: string | null;
  icon: string | null;
  rain_probability: number | null;
  error: string | null;
}

export interface QuickLink {
  id: string;
  label: string;
  url: string;
}

export interface DashboardResponse {
  server_name: string;
  generated_at: string;
  refresh_interval_seconds: number;
  system_health: SystemHealth;
  overview: OverviewMetric[];
  storage: StorageMount[];
  services: ServiceSnapshot[];
  activity: ActivityItem[];
  weather?: WeatherInfo | null;
  quick_links?: QuickLink[];
}

export interface ActivityItem {
  tone: "good" | "warn" | "bad" | "muted" | string;
  text: string;
}

export interface ServiceDefinition {
  id: string;
  name: string;
  description: string;
  icon: string;
  enabled: boolean;
  configured: boolean;
  configurable: boolean;
  implemented: boolean;
  url: string | null;
  socket: string | null;
  config_kind: "url" | "socket" | string;
  has_secret: boolean;
}

export interface SettingsResponse {
  server_name: string;
  refresh_interval_seconds: number;
  services: ServiceDefinition[];
}

export interface SettingsUpdateRequest {
  server_name?: string;
  refresh_interval_seconds?: number;
  services?: Record<
    string,
    {
      enabled?: boolean;
      url?: string | null;
      socket?: string | null;
    }
  >;
}

export interface DockerPort {
  private_port: number;
  public_port: number | null;
  type: string;
  ip: string | null;
  display: string;
}

export interface DockerContainer {
  id: string;
  name: string;
  image: string;
  state: string;
  status: string;
  status_tone: "good" | "warn" | "bad" | "muted" | string;
  uptime: string | null;
  cpu_percent: number | null;
  cpu_display: string;
  memory_usage: number | null;
  memory_limit: number | null;
  memory_display: string;
  restart_count: number | null;
  ports: DockerPort[];
  exit_code: number | null;
}

export interface DockerOverview {
  daemon_status: string;
  version: string | null;
  api_version: string | null;
  running: number;
  stopped: number;
  restarting: number;
  paused: number;
  total: number;
  images: number | null;
  volumes: number | null;
  containers_from_info: number | null;
}

export interface DockerDetailResponse {
  available: boolean;
  configured: boolean;
  generated_at: string;
  error: string | null;
  overview: DockerOverview | null;
  containers: DockerContainer[];
}
