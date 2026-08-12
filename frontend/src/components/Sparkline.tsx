interface SparklineProps {
  values: number[];
  className?: string;
  stroke?: string;
}

/** Tiny SVG sparkline from an in-memory rolling window. */
export function Sparkline({
  values,
  className = "h-8 w-full",
  stroke = "currentColor",
}: SparklineProps) {
  if (values.length < 2) {
    return (
      <div className={`flex items-end ${className}`}>
        <span className="text-[10px] tracking-wide text-faint">Collecting data…</span>
      </div>
    );
  }

  const width = 120;
  const height = 28;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / span) * (height - 6) - 3;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      preserveAspectRatio="none"
      aria-hidden
    >
      <polyline
        fill="none"
        stroke={stroke}
        strokeWidth="1.25"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
        opacity="0.7"
      />
    </svg>
  );
}
