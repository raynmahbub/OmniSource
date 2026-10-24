function metricLabel(key: string): string {
  const words = key
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .trim()
    .toLowerCase();
  return words ? words[0].toUpperCase() + words.slice(1) : key;
}

/** Consistent, readable operational metrics instead of raw JSON key rows. */
export default function MetricGrid({ metrics }: { metrics: Record<string, string | number> }) {
  return (
    <dl className="os-metric-grid">
      {Object.entries(metrics).map(([key, value]) => (
        <div key={key} className="os-metric">
          <dt>{metricLabel(key)}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
