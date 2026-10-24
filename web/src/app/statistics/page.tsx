import MetricGrid from "@/components/MetricGrid";
import PageHeader from "@/components/PageHeader";
import { getAnalytics, getAnalyticsRollup } from "@/lib/data";
import { getLangDict } from "@/lib/lang";

interface Window {
  date?: string;
  week?: string;
  month?: string;
  days?: number;
  metrics?: Record<string, number>;
  averages?: Record<string, number>;
}

function WindowTable({ title, rows }: { title: string; rows: Window[] }) {
  const keys = [...new Set(rows.flatMap((r) => Object.keys(r.metrics ?? r.averages ?? {})))].slice(0, 6);
  return (
    <div className="os-panel os-table-wrap">
      <h2 className="border-b border-zinc-100 px-4 py-3 font-bold dark:border-zinc-800">{title}</h2>
      <table className="w-full text-left text-sm">
        <thead className="bg-zinc-50 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
          <tr>
            <th className="px-4 py-2 font-semibold">Period</th>
            {keys.map((k) => (
              <th key={k} className="px-4 py-2 text-right font-semibold">
                {k}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-zinc-100 dark:border-zinc-800">
              <td className="px-4 py-2 font-mono text-xs">{r.date ?? r.week ?? r.month}</td>
              {keys.map((k) => (
                <td key={k} className="px-4 py-2 text-right tabular-nums">
                  {(r.metrics ?? r.averages ?? {})[k] ?? "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <p className="p-4 text-sm text-zinc-500">No data yet.</p>}
    </div>
  );
}

export default async function StatisticsPage() {
  const { dict } = await getLangDict();
  const analytics = getAnalytics() as { totals?: Record<string, number> };
  const rollup = getAnalyticsRollup() as { daily?: Window[]; weekly?: Window[]; monthly?: Window[] };
  return (
    <div className="space-y-6">
      <PageHeader title={dict.sections.statisticsTitle} description={dict.sections.statisticsSubtitle} />
      <MetricGrid metrics={analytics.totals ?? {}} />
      <WindowTable title="Daily (30 days)" rows={rollup.daily ?? []} />
      <WindowTable title="Weekly (12 weeks)" rows={rollup.weekly ?? []} />
      <WindowTable title="Monthly (12 months)" rows={rollup.monthly ?? []} />
    </div>
  );
}
