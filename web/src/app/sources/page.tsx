import Link from "next/link";
import PageHeader from "@/components/PageHeader";
import { getSources } from "@/lib/data";
import { getLangDict } from "@/lib/lang";

const BADGE: Record<string, string> = {
  Verified: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200",
  "Community Verified": "bg-sky-100 text-sky-800 dark:bg-sky-900 dark:text-sky-200",
  Maintained: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  Warning: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  Inactive: "bg-zinc-200 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300",
  Deprecated: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

export default async function SourcesPage() {
  const { dict } = await getLangDict();
  const sources = [...getSources()].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  return (
    <div className="space-y-6">
      <PageHeader title={dict.sections.sourcesTitle} description={dict.sections.sourcesSubtitle} />
      <div className="grid gap-3 md:grid-cols-2">
        {sources.map((s) => (
          <Link
            key={s.id}
            href={`/sources/${encodeURIComponent(s.id)}`}
            className="os-card block p-4"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-bold">{s.source}</span>
              {typeof s.score === "number" && (
                <span className="shrink-0 rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-semibold dark:bg-zinc-800">
                  {dict.common.score} {s.score}
                </span>
              )}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              {s.status && (
                <span className={`rounded-full px-2 py-0.5 font-semibold ${BADGE[s.status] ?? BADGE.Maintained}`}>
                  {s.status}
                </span>
              )}
              <span className="text-zinc-500">
                {(s.appCount ?? s.apps?.length ?? 0)} {dict.common.apps}
              </span>
              {s.lastUpdate && <span className="text-zinc-500">· {dict.common.updated} {s.lastUpdate}</span>}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
