import Link from "next/link";
import EmptyState from "@/components/EmptyState";
import PageHeader from "@/components/PageHeader";
import { getAppsWithIds, getDevelopers } from "@/lib/data";
import { getLangDict } from "@/lib/lang";

export default async function DevelopersPage() {
  const { dict } = await getLangDict();
  const developers = getDevelopers();
  const apps = getAppsWithIds();
  const byDeveloper = new Map<string, Array<{ id: string; name: string }>>();
  for (const { id, app } of apps) {
    const name = app.developerName?.trim() || "Unknown developer";
    const list = byDeveloper.get(name) ?? [];
    list.push({ id, name: app.name });
    byDeveloper.set(name, list);
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title={dict.nav.developers ?? "Developers"}
        description="Publishers represented in the validated catalog, with source-backed app records."
      />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {developers.map((developer) => (
          <article key={developer.name} className="os-card p-5">
            <h2 className="font-bold">{developer.name}</h2>
            <p className="mt-1 text-sm text-zinc-500">
              {developer.appCount} {dict.common.apps} · {developer.sourceCount} {dict.common.sources}
            </p>
            <ul className="mt-3 space-y-1 text-sm">
              {(byDeveloper.get(developer.name) ?? []).slice(0, 8).map((app) => (
                <li key={app.id}>
                  <Link className="text-violet-700 hover:underline dark:text-violet-300" href={`/apps/${encodeURIComponent(app.id)}`}>
                    {app.name}
                  </Link>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
      {!developers.length && <EmptyState>{dict.common.noResults}</EmptyState>}
    </div>
  );
}
