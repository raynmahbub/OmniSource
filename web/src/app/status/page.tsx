import MetricGrid from "@/components/MetricGrid";
import PageHeader from "@/components/PageHeader";
import { getMonitoring, getStatus } from "@/lib/data";
import { getLangDict } from "@/lib/lang";

interface SourceState {
  id?: string;
  slug?: string;
  status?: string;
  latencyMs?: number | null;
  checkedAt?: string;
}

const DOT: Record<string, string> = {
  healthy: "bg-emerald-500",
  online: "bg-emerald-500",
  degraded: "bg-amber-500",
  unavailable: "bg-red-500",
  offline: "bg-red-500",
  unknown: "bg-zinc-400",
};

export default async function StatusPage() {
  const { dict } = await getLangDict();
  const doc = getStatus() as {
    overall?: string;
    generatedAt?: string;
    totals?: Record<string, number>;
    pipeline?: Record<string, unknown>;
    sources?: SourceState[];
  };
  const sources = Array.isArray(doc.sources) ? doc.sources : [];
  const totals = doc.totals ?? {};
  const monitoring = getMonitoring();
  const summary = monitoring.summary ?? {};
  const downloadMetrics = {
    downloadsChecked: Number(summary.downloads ?? 0),
    lastSeenReachable: Number(summary.downloadsOk ?? 0),
    lastProbeFailed: Number(summary.downloads ?? 0) - Number(summary.downloadsOk ?? 0),
  };
  return (
    <div className="space-y-6">
      <PageHeader title={dict.sections.statusTitle} description={dict.sections.statusSubtitle} />
      <section className="space-y-3" aria-labelledby="download-monitoring">
        <h2 id="download-monitoring" className="text-lg font-bold">Download monitoring</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">Snapshot checked: {monitoring.generatedAt || "not recorded"}. Results are historical observations and can change; a failed probe does not prove a file is permanently unavailable.</p>
        <MetricGrid metrics={downloadMetrics} />
      </section>
      <section className="space-y-3" aria-labelledby="feed-status">
        <h2 id="feed-status" className="text-lg font-bold">Feed pipeline observations</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">Feed built: {doc.generatedAt || "not recorded"}. Individual checks below may be older or unknown.</p>
        <MetricGrid metrics={totals} />
      </section>
      <div className="os-panel os-table-wrap">
        <table className="w-full text-left text-sm">
          <thead className="bg-zinc-50 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
            <tr>
              <th className="px-4 py-2 font-semibold">{dict.common.source}</th>
              <th className="px-4 py-2 font-semibold">{dict.nav.status}</th>
              <th className="px-4 py-2 font-semibold">Last checked</th>
              <th className="px-4 py-2 font-semibold">Latency</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((s, i) => (
              <tr key={s.id ?? s.slug ?? i} className="border-t border-zinc-100 dark:border-zinc-800">
                <td className="px-4 py-2 font-medium">{s.id ?? s.slug}</td>
                <td className="px-4 py-2">
                  <span className="inline-flex items-center gap-1.5">
                    <span className={`h-2.5 w-2.5 rounded-full ${DOT[s.status ?? "unknown"] ?? DOT.unknown}`} />
                    {s.status ?? "unknown"}
                  </span>
                </td>
                <td className="px-4 py-2 text-zinc-500">{s.checkedAt || "Not recorded"}</td>
                <td className="px-4 py-2 text-zinc-500">{s.latencyMs == null ? "—" : `${s.latencyMs} ms`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
