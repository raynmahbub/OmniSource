import MetricGrid from "@/components/MetricGrid";
import PageHeader from "@/components/PageHeader";
import { getSecurity } from "@/lib/data";
import { getLangDict } from "@/lib/lang";

interface Finding {
  severity?: string;
  check?: string;
  id?: string;
  detail?: string;
}

const SEV: Record<string, string> = {
  critical: "bg-red-600 text-white",
  high: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200",
  medium: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  low: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
};

export default async function SecurityPage() {
  const { dict } = await getLangDict();
  const doc = getSecurity() as {
    verdict?: string;
    generatedAt?: string;
    downloadSnapshotAt?: string;
    summary?: Record<string, number>;
    findings?: Finding[];
    duplicateBinaries?: Array<{ sha256?: string; bundles?: string[] }>;
  };
  const summary = doc.summary ?? {};
  const findings = Array.isArray(doc.findings) ? doc.findings : [];
  const dupes = Array.isArray(doc.duplicateBinaries) ? doc.duplicateBinaries : [];
  return (
    <div className="space-y-6">
      <PageHeader title={dict.sections.securityTitle} description={dict.sections.securitySubtitle} />
      <p className="text-sm text-zinc-600 dark:text-zinc-400">Automated metadata checks are not a malware scan or a safety guarantee. Download observations: {doc.downloadSnapshotAt || "not recorded"}; report generated: {doc.generatedAt || "not recorded"}.</p>
      <div className="os-panel flex items-center gap-3 p-5">
        <span className="font-semibold">Checks verdict:</span>
        <span
          className={`rounded-full px-4 py-1 font-bold ${
            doc.verdict === "pass"
              ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200"
              : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
          }`}
        >
          {doc.verdict ?? "unknown"}
        </span>
      </div>
      <MetricGrid metrics={summary} />
      {!!dupes.length && (
        <div className="rounded-2xl border border-amber-300 bg-amber-50 p-5 dark:border-amber-800 dark:bg-amber-950">
          <h2 className="font-bold">Duplicate binaries ({dupes.length})</h2>
          <ul className="mt-2 space-y-1 font-mono text-xs">
            {dupes.map((d, i) => (
              <li key={i}>
                {d.sha256?.slice(0, 16)}… → {(d.bundles ?? []).join(", ")}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="os-panel os-table-wrap">
        <table className="w-full text-left text-sm">
          <thead className="bg-zinc-50 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
            <tr>
              <th className="px-4 py-2 font-semibold">Severity</th>
              <th className="px-4 py-2 font-semibold">Check</th>
              <th className="px-4 py-2 font-semibold">App</th>
              <th className="px-4 py-2 font-semibold">Detail</th>
            </tr>
          </thead>
          <tbody>
            {findings.map((f, i) => (
              <tr key={i} className="border-t border-zinc-100 dark:border-zinc-800">
                <td className="px-4 py-2">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${SEV[f.severity ?? "low"] ?? SEV.low}`}>
                    {f.severity}
                  </span>
                </td>
                <td className="px-4 py-2 font-mono text-xs">{f.check}</td>
                <td className="px-4 py-2 font-medium">{f.id}</td>
                <td className="px-4 py-2 text-zinc-500">{f.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!findings.length && <p className="p-4 text-sm text-zinc-500">No findings from these checks; untested risks may remain.</p>}
      </div>
    </div>
  );
}
