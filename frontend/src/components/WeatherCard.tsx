import type { WeatherInfo } from "../types";

interface WeatherCardProps {
  weather: WeatherInfo | null | undefined;
}

export function WeatherCard({ weather }: WeatherCardProps) {
  const location = weather?.location || "Thetford, Norfolk, UK";

  if (!weather || !weather.available) {
    return (
      <section className="px-4 sm:px-6 lg:px-8">
        <div className="mb-3">
          <h2 className="text-sm font-semibold tracking-tight text-ink">Weather</h2>
        </div>
        <article className="rounded-xl border border-border/70 bg-surface/55 px-3.5 py-3">
          <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-faint">
            {location}
          </p>
          <p className="mt-2 text-sm text-faint">Weather unavailable</p>
        </article>
      </section>
    );
  }

  return (
    <section className="px-4 sm:px-6 lg:px-8">
      <div className="mb-3">
        <h2 className="text-sm font-semibold tracking-tight text-ink">Weather</h2>
      </div>
      <article className="rounded-xl border border-border/70 bg-surface/55 px-3.5 py-3">
        <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-faint">
          {weather.location}
        </p>
        <div className="mt-2 flex items-baseline gap-2">
          <span className="text-2xl leading-none" aria-hidden>
            {weather.icon || "🌤"}
          </span>
          <span className="font-mono text-2xl tabular-nums tracking-tight text-ink">
            {weather.temperature_c != null ? `${Math.round(weather.temperature_c)}°C` : "—"}
          </span>
          {weather.condition ? (
            <span className="text-sm text-muted">{weather.condition}</span>
          ) : null}
        </div>
        <div className="mt-2 space-y-1 text-sm text-muted">
          {weather.feels_like_c != null ? (
            <p>Feels like {Math.round(weather.feels_like_c)}°C</p>
          ) : null}
          <p className="font-mono tabular-nums text-ink/90">
            {weather.high_c != null ? `H ${Math.round(weather.high_c)}°` : "H —"}
            {"  "}
            {weather.low_c != null ? `L ${Math.round(weather.low_c)}°` : "L —"}
          </p>
          {weather.rain_probability != null ? (
            <p>Rain {weather.rain_probability}%</p>
          ) : null}
        </div>
      </article>
    </section>
  );
}
